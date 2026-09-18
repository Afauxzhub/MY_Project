# -*- coding: utf-8 -*-
"""
Fix Max->FBX scale curve corruption where ScaleXYZ percentage keys are written
as (percent * 10) instead of (percent / 100).

Example:
  Max Curve Editor: 100 .. 180  (percent)
  Expected FBX:     1.0 .. 1.8
  Broken FBX:       1.0 .. 1800   (≈ percent * 10 on keyed frames)

Fix for values with abs(v) > threshold: v = v / 1000.0
  because (percent * 10) / 1000 = percent / 100.

Only touches AnimationCurve nodes connected to Lcl Scaling.

Compatible with 3ds Max embedded Python (2.7 / 3.x): always normalize input
to bytearray so indexing yields ints (avoids int+str TypeError).
"""
from __future__ import print_function
import argparse
import os
import shutil
import struct
import sys
import zlib

try:
    _RANGE = xrange  # noqa: F821  # py2
except NameError:
    _RANGE = range


class Prop(object):
    def __init__(self, typecode, value):
        self.typecode = typecode
        self.value = value


class Node(object):
    def __init__(self, name, props, children):
        self.name = name
        self.props = props
        self.children = children


def _as_bytearray(data):
    """Ensure binary buffer indexes to int on both Py2 and Py3."""
    if isinstance(data, bytearray):
        return data
    return bytearray(data)


def _b2s(raw):
    """Decode ascii/utf-8 bytes/bytearray/str to unicode/str."""
    if raw is None:
        return u""
    if isinstance(raw, bytearray):
        raw = bytes(raw)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return raw


def is_visibility_scale_model(model):
    """Return True for scale channels owned by visibility helper controls."""
    text = _b2s(model).replace("\\", "/")
    leaf = text.rsplit("|", 1)[-1].rsplit(":", 1)[-1].lower()
    return leaf.startswith(("bone_ctrl", "ctrl_bone"))


def is_weapon_or_attachment_model(model):
    """Link-constrained weapons/attachments: local T can jump on retarget."""
    text = _b2s(model).replace("\\", "/")
    leaf = text.rsplit("|", 1)[-1].rsplit(":", 1)[-1].lower()
    return leaf.startswith(("mask_", "attachment_", "weapon", "wp_"))


def is_foot_toe_model(model):
    text = _b2s(model).replace("\\", "/")
    leaf = text.rsplit("|", 1)[-1].rsplit(":", 1)[-1].lower()
    return ("foot" in leaf) or ("toe" in leaf)


def read_array(data, pos, elem_fmt):
    length, encoding, comp_len = struct.unpack_from("<III", data, pos)
    pos += 12
    raw = bytes(data[pos : pos + comp_len])
    pos += comp_len
    if encoding == 1:
        raw = zlib.decompress(raw)
    vals = list(struct.unpack_from("<" + elem_fmt * length, raw, 0)) if length else []
    return vals, pos, (length, encoding, comp_len)


def read_prop(data, pos):
    t = chr(data[pos])
    pos += 1
    meta = None
    if t == "Y":
        v = struct.unpack_from("<h", data, pos)[0]
        pos += 2
    elif t == "C":
        v = data[pos]
        pos += 1
    elif t == "I":
        v = struct.unpack_from("<i", data, pos)[0]
        pos += 4
    elif t == "F":
        v = struct.unpack_from("<f", data, pos)[0]
        pos += 4
    elif t == "D":
        v = struct.unpack_from("<d", data, pos)[0]
        pos += 8
    elif t == "L":
        v = struct.unpack_from("<q", data, pos)[0]
        pos += 8
    elif t in ("S", "R"):
        n = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        v = bytes(data[pos : pos + n])
        pos += n
    elif t == "f":
        v, pos, meta = read_array(data, pos, "f")
    elif t == "d":
        v, pos, meta = read_array(data, pos, "d")
    elif t == "i":
        v, pos, meta = read_array(data, pos, "i")
    elif t == "l":
        v, pos, meta = read_array(data, pos, "q")
    elif t == "b":
        length, encoding, comp_len = struct.unpack_from("<III", data, pos)
        pos += 12 + comp_len
        v = None
        meta = (length, encoding, comp_len)
    else:
        raise RuntimeError("Unknown prop type %r at %d" % (t, pos - 1))
    prop = Prop(t, v)
    prop._array_meta = meta
    return prop, pos


def read_node(data, pos, is64):
    node_start = pos
    if is64:
        end, nprops, plen = struct.unpack_from("<QQQ", data, pos)
        pos += 24
        end = int(end)
        nprops = int(nprops)
        plen = int(plen)
    else:
        end, nprops, plen = struct.unpack_from("<III", data, pos)
        pos += 12
        end = int(end)
        nprops = int(nprops)
        plen = int(plen)
    namelen = int(data[pos])
    pos += 1
    if end == 0:
        return None, pos
    name = _b2s(bytes(data[pos : pos + namelen]))
    pos += namelen
    props = []
    prop_end = pos + plen
    for _ in _RANGE(nprops):
        prop, pos = read_prop(data, pos)
        props.append(prop)
    pos = prop_end
    children = []
    while pos < end:
        child, pos = read_node(data, pos, is64)
        if child is None:
            break
        children.append(child)
    node = Node(name, props, children)
    node._file_start = int(node_start)
    node._file_end = int(end)
    return node, end


def dec_str(v):
    if isinstance(v, (bytes, bytearray)):
        raw = bytes(v)
        return raw.split(b"\x00")[0].decode("utf-8", "replace")
    return v


def parse_fbx(data):
    data = _as_bytearray(data)
    version = struct.unpack_from("<I", data, 23)[0]
    is64 = version >= 7500
    pos = 27
    roots = []
    while pos < len(data):
        node, pos2 = read_node(data, pos, is64)
        if node is None:
            break
        roots.append(node)
        pos = pos2
    return version, is64, roots


def _collect_scene_maps(roots):
    objects = connections = None
    for n in roots:
        if n.name == "Objects":
            objects = n
        elif n.name == "Connections":
            connections = n
    models = {}
    anim_curves = {}
    anim_curve_nodes = {}
    for c in objects.children:
        if not c.props:
            continue
        oid = c.props[0].value
        if c.name == "Model":
            models[oid] = dec_str(c.props[1].value)
        elif c.name == "AnimationCurve":
            anim_curves[oid] = c
        elif c.name == "AnimationCurveNode":
            anim_curve_nodes[oid] = (dec_str(c.props[1].value), c)

    conns = []
    for c in connections.children:
        if c.name == "C":
            conns.append([dec_str(p.value) for p in c.props])
    return models, anim_curves, anim_curve_nodes, conns


def collect_curves_by_prop(roots, prop_substr):
    """
    Return dict: curve_id -> (model_name, prop_name, channel, curve_node)
    for AnimationCurve nodes connected through AnimationCurveNode to Model.prop.
    """
    models, anim_curves, anim_curve_nodes, conns = _collect_scene_maps(roots)
    prop_nodes = {}
    for nv in conns:
        if len(nv) < 4:
            continue
        child, parent, prop = nv[1], nv[2], nv[3]
        if parent in models and child in anim_curve_nodes and prop_substr in str(prop):
            prop_nodes[child] = (models[parent], prop)

    curves = {}
    for nv in conns:
        if len(nv) < 3:
            continue
        child, parent = nv[1], nv[2]
        channel = nv[3] if len(nv) > 3 else "?"
        if parent in prop_nodes and child in anim_curves:
            model, prop = prop_nodes[parent]
            curves[child] = (model, prop, channel, anim_curves[child])
    return curves


def collect_scale_curve_ids(roots):
    return collect_curves_by_prop(roots, "Scal")


def _find_take_local_time(roots):
    for root in roots:
        if root.name != "Takes":
            continue
        for take in root.children:
            if take.name != "Take":
                continue
            for child in take.children:
                if child.name == "LocalTime" and len(child.props) >= 2:
                    return int(child.props[0].value), int(child.props[1].value)
    return None


def _curve_key_times(curve):
    for child in curve.children:
        if child.name == "KeyTime" and child.props:
            return [int(value) for value in child.props[0].value]
    return []


def validate_fbx_transform_curves_within_take(fbx_path):
    """Hard-check that Model PRS curves contain no keys outside the FBX Take."""
    with open(fbx_path, "rb") as stream:
        data = stream.read()
    if _as_bytearray(data)[:18] != bytearray(b"Kaydara FBX Binary"):
        return False, ["FAIL task-local PRS validation requires binary FBX"]

    _version, _is64, roots = parse_fbx(data)
    take_range = _find_take_local_time(roots)
    if take_range is None:
        return False, ["FAIL task-local PRS validation missing Take LocalTime"]
    start_tick, end_tick = take_range

    failures = []
    checked_ids = set()
    checked_curve_count = 0
    for prop_substr in ("Transl", "Rotat", "Scal"):
        curves = collect_curves_by_prop(roots, prop_substr)
        for curve_id, (model_name, prop_name, channel, curve) in curves.items():
            if curve_id in checked_ids:
                continue
            checked_ids.add(curve_id)
            times = _curve_key_times(curve)
            if not times:
                continue
            checked_curve_count += 1
            outside = [value for value in times if value < start_tick or value > end_tick]
            if outside:
                failures.append(
                    "FAIL task-local PRS curve outside Take: %s %s %s outside=%d keys=%d take=%d..%d keyRange=%d..%d"
                    % (
                        dec_str(model_name),
                        dec_str(prop_name),
                        dec_str(channel),
                        len(outside),
                        len(times),
                        start_tick,
                        end_tick,
                        min(times),
                        max(times),
                    )
                )

    if failures:
        return False, failures
    return True, [
        "OK task-local PRS curves=%d take=%d..%d" %
        (checked_curve_count, start_tick, end_tick)
    ]


def find_keyvalue_array_file_pos(curve_node):
    for ch in curve_node.children:
        if ch.name != "KeyValueFloat" or not ch.props:
            continue
        prop = ch.props[0]
        if prop.typecode != "f" or not prop._array_meta:
            continue
        length, encoding, comp_len = prop._array_meta
        return prop.value, ch, length, encoding, comp_len
    return None, None, 0, 0, 0


def locate_float_payload(data, child_node, length, encoding, comp_len):
    data = _as_bytearray(data)
    target = bytearray(b"KeyValueFloat")
    for hdr_size in (12, 24):
        try_pos = int(child_node._file_start)
        if hdr_size == 24:
            end, nprops, plen = struct.unpack_from("<QQQ", data, try_pos)
        else:
            end, nprops, plen = struct.unpack_from("<III", data, try_pos)
        end = int(end)
        namelen = int(data[try_pos + hdr_size])
        name = data[try_pos + hdr_size + 1 : try_pos + hdr_size + 1 + namelen]
        if name == target and end == int(child_node._file_end):
            prop_start = try_pos + hdr_size + 1 + namelen
            if int(data[prop_start]) != ord("f"):
                continue
            arr_hdr = prop_start + 1
            l2, e2, c2 = struct.unpack_from("<III", data, arr_hdr)
            if (int(l2), int(e2), int(c2)) != (int(length), int(encoding), int(comp_len)):
                continue
            return arr_hdr + 12, int(encoding)
    raise RuntimeError("Could not locate KeyValueFloat payload")


def _is_finite(fv):
    """math.isfinite is Py3-only; Max may run Py2.7."""
    import math

    try:
        return math.isfinite(fv)
    except AttributeError:
        return (not math.isnan(fv)) and (not math.isinf(fv))


def curve_has_percent_times10_signature(values, near1=(0.5, 2.0), bad=(500.0, 2500.0)):
    """
    Detect Max ScaleXYZ percent exported as percent*10.

    Real signature seen in broken exports:
      - many keys stay near factor 1.0
      - other keys jump into ~[500, 2500] (e.g. 180% -> 1800)
    Sparse channels may only have 1-2 bad keys (R Calf_1 Y/Z); still match.
    Cascade garbage (millions) must NOT match this signature alone.
    """
    if not values or len(values) < 4:
        return False
    n_near = 0
    n_bad = 0
    for v in values:
        fv = abs(float(v))
        if not _is_finite(fv):
            continue
        if near1[0] <= fv <= near1[1]:
            n_near += 1
        if bad[0] <= fv <= bad[1]:
            n_bad += 1
    return (n_near >= 3) and (n_bad >= 1)


def curve_has_inverse_scale_signature(
    values, near1=(0.5, 2.0), tiny_lo=1e-4, tiny_hi=0.01
):
    """
    Child bones compensating a parent percent*10 scale often get local scale
    keys near 1/1000 (e.g. 0.00055) mixed with normal ~1.0 keys.

    Ignore underflow noise below tiny_lo so Thigh/etc. FP dust does not match.
    """
    if not values or len(values) < 4:
        return False
    n_near = 0
    n_tiny = 0
    for v in values:
        fv = abs(float(v))
        if not _is_finite(fv):
            continue
        if near1[0] <= fv <= near1[1]:
            n_near += 1
        if float(tiny_lo) <= fv < float(tiny_hi):
            n_tiny += 1
    return (n_near >= 3) and (n_tiny >= 3)


def detect_max_scale_percent_bug(scale_curves):
    """
    Returns (hit, models) where models are bone names showing either
    percent*10 keys or inverse 1/1000 compensation keys.
    """
    hit_models = []
    for cid, (model, prop, channel, curve) in scale_curves.items():
        if is_visibility_scale_model(model):
            continue
        values, _child, _l, _e, _c = find_keyvalue_array_file_pos(curve)
        if not values:
            continue
        if curve_has_percent_times10_signature(values) or curve_has_inverse_scale_signature(
            values
        ):
            if model not in hit_models:
                hit_models.append(model)
    return (len(hit_models) > 0), hit_models


def fix_scale_values(
    values, threshold=10.0, divisor=1000.0, max_reasonable=10000.0, tiny=0.01
):
    """
    Only safe after detect_max_scale_percent_bug() is True.
    - large (threshold, max_reasonable]: percent*10 -> /divisor
    - tiny (0, tiny): inverse compensation (~1/1800) -> *divisor
    - non-finite / > max_reasonable: reset to 1.0
    """
    changed = 0
    out = []
    for v in values:
        fv = float(v)
        if (not _is_finite(fv)) or abs(fv) > float(max_reasonable):
            out.append(1.0)
            changed += 1
        elif abs(fv) > float(threshold):
            out.append(fv / float(divisor))
            changed += 1
        elif 1e-4 <= abs(fv) < float(tiny):
            out.append(fv * float(divisor))
            changed += 1
        else:
            out.append(fv)
    return out, changed


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return 0.5 * (float(s[mid - 1]) + float(s[mid]))


def fix_translation_outliers(values, soft_limit=50.0, hard_limit=1000.0):
    """
    Parent scale bake corruption leaves ~43 frames with huge local translations
    while the rest stay near bind pose (~bone length).

    Prefer the dominant near-bind cluster (|v| <= soft_limit). Fall back to
    hard_limit only when that cluster is too sparse.
    """
    core = []
    wide = []
    for v in values:
        fv = float(v)
        if not _is_finite(fv):
            continue
        if abs(fv) <= float(soft_limit):
            core.append(fv)
        if abs(fv) <= float(hard_limit):
            wide.append(fv)

    use = core
    limit = float(soft_limit)
    if len(core) < max(3, len(values) // 4):
        use = wide
        limit = float(hard_limit)
    if not use:
        return list(values), 0

    fallback = _median(use)
    # Keep a little headroom around the bind cluster for real motion.
    limit = max(limit, abs(fallback) * 4.0 + 5.0)
    changed = 0
    out = []
    for v in values:
        fv = float(v)
        if (not _is_finite(fv)) or abs(fv) > limit:
            out.append(fallback)
            changed += 1
        else:
            out.append(fv)
    return out, changed


def fix_insane_translation_values(values, insane=5.0e3, sane_cap=1.0e3):
    """
    Gated translation repair for explode spikes on bind-length channels.

    Triggers when:
      - abs max >= insane (5e3+), or
      - bind-length spike: median >= 1 (bone axis ~16cm) AND max > 10*median
        AND a majority of keys sit in the near-median cluster

    Near-zero channels (median < 1) are only repaired at insane magnitudes so
    real lateral motion is not flattened.
    """
    if not values:
        return values, 0
    finite = []
    for v in values:
        fv = float(v)
        if _is_finite(fv):
            finite.append(fv)
    if not finite:
        return values, 0
    abs_finite = [abs(v) for v in finite]
    vmax = max(abs_finite)
    med = _median(abs_finite)

    hard = vmax >= float(insane)
    bind_spike = (
        (med >= 1.0)
        and (vmax > 100.0)
        and (vmax > 8.0 * med)
    )
    # Near-zero axis with rare explode spikes (Toe Z med~0, max~900).
    n_near0 = sum(1 for a in abs_finite if a <= 5.0)
    zero_spike = (
        (med < 1.0)
        and (vmax > 100.0)
        and (n_near0 >= max(3, int(0.55 * len(finite))))
    )
    if (not hard) and (not bind_spike) and (not zero_spike):
        return values, 0

    if zero_spike:
        soft = 5.0
    else:
        soft = max(50.0, med * 4.0 + 5.0)
        if soft > float(sane_cap):
            soft = float(sane_cap)
    sane = [v for v in finite if abs(v) <= soft]
    # Require a dominant near-bind cluster for spike mode (not hard insane).
    if (not hard) and len(sane) < max(3, int(0.55 * len(finite))):
        return values, 0
    if len(sane) < 3:
        sane = [v for v in finite if abs(v) <= float(sane_cap)]
    if len(sane) < 3:
        sane = [v for v in finite if abs(v) < float(insane)]
    if not sane:
        return values, 0
    fallback = _median(sane)
    if zero_spike:
        limit = 5.0
    else:
        limit = max(soft, abs(fallback) * 5.0 + 20.0)
    changed = 0
    out = []
    for v in values:
        fv = float(v)
        if (not _is_finite(fv)) or abs(fv) > limit:
            out.append(fallback)
            changed += 1
        else:
            out.append(fv)
    return out, changed


def fix_fbx_insane_translations_only(fbx_path, dry_run=False):
    """Publish safety net for Foot/Toe translation explode / bind-length spikes."""
    with open(fbx_path, "rb") as f:
        data = f.read()
    head = _as_bytearray(data)[:18]
    if head != bytearray(b"Kaydara FBX Binary"):
        return 0, ["not a binary FBX"]

    total = 0
    all_reports = []
    # Two passes: first cuts e3/e9 spikes; second cleans leftovers just above 8*med.
    for _pass in range(2):
        _version, _is64, roots = parse_fbx(data)
        data = _as_bytearray(data)
        trans_curves = collect_curves_by_prop(roots, "Translat")

        targets = {}
        for cid, meta in trans_curves.items():
            model, prop, channel, curve = meta
            if is_weapon_or_attachment_model(model):
                continue
            values, _c, _l, _e, _cl = find_keyvalue_array_file_pos(curve)
            if not values:
                continue
            finite_abs = [
                abs(float(v)) for v in values if _is_finite(float(v))
            ]
            if not finite_abs:
                continue
            vmax = max(finite_abs)
            # bind_spike (~100 vs median ~3) is for Foot/Toe explode, not for
            # Link Constraint retarget (hand->head local T on mask_01).
            if (not is_foot_toe_model(model)) and vmax < 5.0e3:
                continue
            _probe, chg = fix_insane_translation_values(values)
            if chg > 0:
                targets[cid] = meta

        if not targets:
            if _pass == 0:
                return 0, ["skip: no insane translation curves"]
            break

        def _fixer(values):
            return fix_insane_translation_values(values)

        data, reports, n = patch_curve_map(
            data, targets, _fixer, "TRANS", dry_run=dry_run
        )
        all_reports.extend(reports)
        total += n
        if n <= 0:
            break

    if total > 0 and not dry_run:
        with open(fbx_path, "wb") as f:
            f.write(bytes(data) if sys.version_info[0] >= 3 else data)
    return total, all_reports


# backward-compatible alias
def fix_values(values, threshold=10.0, divisor=1000.0, max_reasonable=10000.0):
    return fix_scale_values(values, threshold, divisor, max_reasonable)


def _write_curve_values(data, model, prop, channel, curve, new_vals, dry_run):
    """
    Returns (data, ok, skip_reason).
    """
    values, child, length, encoding, comp_len = find_keyvalue_array_file_pos(curve)
    if not values or child is None:
        return data, False, "missing KeyValueFloat"
    payload_off, enc = locate_float_payload(data, child, length, encoding, comp_len)
    if enc != 0:
        return data, False, "compressed encoding=%d" % enc
    packed = struct.pack("<" + ("f" * len(new_vals)), *new_vals)
    if len(packed) != int(comp_len):
        return data, False, "size mismatch"
    if not dry_run:
        data[payload_off : payload_off + int(comp_len)] = bytearray(packed)
    return data, True, ""


def patch_curve_map(data, curves, fixer, kind_label, dry_run=False):
    data = _as_bytearray(data)
    reports = []
    total_changed = 0
    items = list(curves.items())
    try:
        items.sort(key=lambda x: (str(x[1][0]), str(x[1][1]), str(x[1][2])))
    except Exception:
        pass
    for cid, (model, prop, channel, curve) in items:
        values, child, length, encoding, comp_len = find_keyvalue_array_file_pos(curve)
        if not values:
            continue
        new_vals, changed = fixer(values)
        if changed <= 0:
            continue
        old_max = max(abs(float(v)) for v in values)
        new_max = max(abs(float(v)) for v in new_vals)
        data, ok, reason = _write_curve_values(
            data, model, prop, channel, curve, new_vals, dry_run
        )
        if not ok:
            reports.append(
                "SKIP %s %s %s %s (%s)" % (kind_label, model, prop, channel, reason)
            )
            continue
        total_changed += changed
        reports.append(
            "FIX-%s %s %s %s keys_changed=%d max %.6g -> %.6g"
            % (kind_label, model, prop, channel, changed, old_max, new_max)
        )
    return data, reports, total_changed


def patch_file(data, scale_curves, threshold=10.0, divisor=1000.0, dry_run=False):
    """Legacy API: only large scale /divisor."""

    def _fixer(values):
        return fix_scale_values(values, threshold=threshold, divisor=divisor)

    return patch_curve_map(data, scale_curves, _fixer, "SCALE", dry_run=dry_run)


def inspect_fbx_scale_ranges(fbx_path, model_names=None):
    """Return per-model XYZ scale min/max/key-count from a binary FBX."""
    with open(fbx_path, "rb") as f:
        data = f.read()
    if _as_bytearray(data)[:18] != bytearray(b"Kaydara FBX Binary"):
        raise ValueError("not a binary FBX")

    _version, _is64, roots = parse_fbx(data)
    targets = None
    if model_names:
        targets = set(_b2s(name).lower() for name in model_names)
    stats = {}
    for _cid, (model, _prop, channel, curve) in collect_curves_by_prop(roots, "Scal").items():
        model_text = _b2s(model)
        model_key = model_text.lower()
        if targets is not None and model_key not in targets:
            continue
        values, _c, _l, _e, _cl = find_keyvalue_array_file_pos(curve)
        finite = [float(v) for v in (values or []) if _is_finite(float(v))]
        if not finite:
            continue
        axis = _b2s(channel).split("|")[-1].upper()
        if axis not in ("X", "Y", "Z"):
            continue
        row = stats.setdefault(model_key, {"name": model_text, "axes": {}})
        old = row["axes"].get(axis)
        current = {"min": min(finite), "max": max(finite), "keys": len(finite)}
        if old:
            current["min"] = min(old["min"], current["min"])
            current["max"] = max(old["max"], current["max"])
            current["keys"] += old["keys"]
        row["axes"][axis] = current
    return stats


def validate_fbx_hide_scale_expectations(
    fbx_path, expectations, threshold=0.5, tolerance=0.002
):
    """Hard semantic gate for evaluated bone_ctrl/ctrl_bone scale export."""
    expectations = expectations or {}
    reports = []
    if not expectations:
        return True, ["skip: no hide-scale expectations"]
    try:
        stats = inspect_fbx_scale_ranges(fbx_path, expectations.keys())
    except Exception as ex:
        return False, ["FAIL hide-scale inspect: %s" % ex]

    for node_name in sorted(expectations.keys(), key=lambda value: _b2s(value).lower()):
        expected = expectations[node_name]
        model_key = _b2s(node_name).lower()
        actual = stats.get(model_key)
        expected_axes = expected.get("axes", expected)
        if actual is None:
            expected_all_unit = all(
                axis not in expected_axes
                or (
                    abs(float(expected_axes[axis]["min"]) - 1.0) <= tolerance
                    and abs(float(expected_axes[axis]["max"]) - 1.0) <= tolerance
                )
                for axis in ("X", "Y", "Z")
            )
            if expected_all_unit:
                continue
            reports.append("FAIL hide-scale curve missing: %s" % _b2s(node_name))
            continue
        for axis in ("X", "Y", "Z"):
            exp = expected_axes.get(axis)
            got = actual["axes"].get(axis)
            if exp is None:
                continue
            exp_min = float(exp["min"])
            exp_max = float(exp["max"])
            if got is None:
                if (
                    abs(exp_min - 1.0) <= tolerance
                    and abs(exp_max - 1.0) <= tolerance
                ):
                    continue
                reports.append("FAIL hide-scale axis missing: %s %s" % (_b2s(node_name), axis))
                continue
            got_min = float(got["min"])
            got_max = float(got["max"])
            exp_hidden = exp_min <= threshold
            exp_visible = exp_max > threshold
            got_hidden = got_min <= threshold
            got_visible = got_max > threshold
            state_mismatch = (exp_hidden != got_hidden) or (exp_visible != got_visible)
            range_mismatch = (
                abs(exp_min - got_min) > tolerance
                or abs(exp_max - got_max) > tolerance
            )
            if state_mismatch or range_mismatch:
                reports.append(
                    "FAIL hide-scale mismatch: %s %s source=[%.6g,%.6g] fbx=[%.6g,%.6g]"
                    % (_b2s(node_name), axis, exp_min, exp_max, got_min, got_max)
                )
    failures = [line for line in reports if line.startswith("FAIL")]
    if failures:
        return False, reports
    reports.append("ok: hide-scale curves match evaluated Max ranges")
    return True, reports


def validate_fbx_scale_export(fbx_path):
    """
    Read-only validation used by the publish pipeline.
    Never rewrites the file.

    Returns (ok, reports):
      ok=False when percent*10 signature or 1800-class scale peaks are found.
    """
    reports = []
    if not fbx_path or not os.path.isfile(fbx_path):
        return False, ["missing file"]
    with open(fbx_path, "rb") as f:
        data = f.read()
    head = _as_bytearray(data)[:18]
    if head != bytearray(b"Kaydara FBX Binary"):
        return False, ["not a binary FBX"]

    _version, _is64, roots = parse_fbx(data)
    scale_curves = collect_curves_by_prop(roots, "Scal")
    hit, hit_models = detect_max_scale_percent_bug(scale_curves)
    if hit:
        reports.append(
            "FAIL percent*10 / inverse-scale signature on: %s"
            % (", ".join(hit_models))
        )

    peak_hits = []
    hide_leg_hits = []
    for cid, (model, prop, channel, curve) in scale_curves.items():
        values, _c, _l, _e, _cl = find_keyvalue_array_file_pos(curve)
        if not values:
            continue
        finite_abs = [
            abs(float(v)) for v in values if _is_finite(float(v))
        ]
        if not finite_abs:
            continue
        vmax = max(finite_abs)
        vmin = min(finite_abs)
        if vmax >= 200.0:
            peak_hits.append("%s %s max=%.3f" % (model, channel, vmax))
        # Intentional hide-leg style: name looks like Thigh and stays near 0.1
        mlow = _b2s(model).lower()
        if "thigh" in mlow:
            near_hide = sum(1 for a in finite_abs if 0.05 <= a <= 0.2)
            near_one = sum(1 for a in finite_abs if 0.8 <= a <= 1.2)
            if near_hide >= 3:
                hide_leg_hits.append(
                    "%s %s hide-scale keys=%d (ok ~0.1)" % (model, channel, near_hide)
                )
            elif near_one >= 3 and vmin > 0.5:
                hide_leg_hits.append(
                    "%s %s NOTE: Thigh scale stays near 1.0 (not ~0.1)" % (model, channel)
                )

    if peak_hits:
        reports.append("FAIL high scale peaks: %s" % ("; ".join(peak_hits[:12])))

    # Translation explode check (mesh fly-apart). Scale-only OK is not enough.
    trans_curves = collect_curves_by_prop(roots, "Translat")
    trans_hits = []
    for cid, (model, prop, channel, curve) in trans_curves.items():
        if is_weapon_or_attachment_model(model):
            continue
        if not is_foot_toe_model(model):
            values, _c, _l, _e, _cl = find_keyvalue_array_file_pos(curve)
            if not values:
                continue
            finite_abs = [abs(float(v)) for v in values if _is_finite(float(v))]
            if not finite_abs:
                continue
            if max(finite_abs) < 5.0e3:
                continue
        values, _c, _l, _e, _cl = find_keyvalue_array_file_pos(curve)
        if not values:
            continue
        finite_abs = [abs(float(v)) for v in values if _is_finite(float(v))]
        if not finite_abs:
            continue
        vmax = max(finite_abs)
        med = _median(finite_abs)
        bind_spike = (med >= 1.0) and (vmax > 100.0) and (vmax > 8.0 * med)
        n_near0 = sum(1 for a in finite_abs if a <= 5.0)
        zero_spike = (
            (med < 1.0)
            and (vmax > 100.0)
            and (n_near0 >= max(3, int(0.55 * len(finite_abs))))
        )
        if vmax >= 5.0e3 or bind_spike or zero_spike:
            trans_hits.append("%s %s max=%.3g med=%.3g" % (model, channel, vmax, med))
    if trans_hits:
        reports.append(
            "FAIL insane translation peaks: %s" % ("; ".join(trans_hits[:12]))
        )

    for line in hide_leg_hits[:12]:
        reports.append(line)

    if not reports:
        reports.append("ok: no percent*10 signature, no 1800-class scale peaks")
        return True, reports
    # Hide-leg notes alone are not failures
    hard_fail = any(r.startswith("FAIL") for r in reports)
    return (not hard_fail), reports


def fix_percent_times10_values(values, bad=(500.0, 2500.0), divisor=1000.0):
    """
    Repair Max scale export inflation back to factors:
      - [500, 2500] / 1000      -> e.g. 1820 -> 1.82
      - [5e5, 5e6] / 1e6       -> e.g. 1.82e6 -> 1.82 (percent*10 then *1000)
      - [5e3, 5e5) / 1000      -> only if result in [0.05, 5]
    Never multiplies tiny values (protects hide-leg 0.1).
    """
    changed = 0
    out = []
    for v in values:
        fv = float(v)
        if not _is_finite(fv):
            out.append(fv)
            continue
        af = abs(fv)
        if bad[0] <= af <= bad[1]:
            out.append(fv / float(divisor))
            changed += 1
        elif 5.0e5 <= af <= 5.0e6:
            cand = fv / 1.0e6
            if 0.05 <= abs(cand) <= 5.0:
                out.append(cand)
                changed += 1
            else:
                out.append(fv)
        elif 5.0e3 <= af < 5.0e5:
            cand = fv / float(divisor)
            if 0.05 <= abs(cand) <= 5.0:
                out.append(cand)
                changed += 1
            else:
                out.append(fv)
        else:
            out.append(fv)
    return out, changed


def fix_cascade_garbage_values(values, lo=0.5, hi=2.5):
    """
    Reset child-scale cascade garbage left by parent percent*10 export.
    Keeps values in [lo, hi] (covers stretch ~1.8). Outside -> 1.0.
    Protects intentional hide-leg keys in [0.05, 0.25] when present.

    If a curve has extreme peaks (abs > 100), treat the whole curve as
    cascade garbage and flatten outliers harder (still keep hide-leg band).
    """
    if not values:
        return values, 0
    absv = [abs(float(v)) for v in values if _is_finite(float(v))]
    if not absv:
        return values, 0
    vmax = max(absv)
    n_hide = sum(1 for a in absv if 0.008 <= a <= 0.25)
    # Extreme cascade: keep only near-1 and hide-leg; everything else -> 1
    extreme = vmax > 100.0
    n_out = 0
    for a in absv:
        if n_hide >= 3 and 0.008 <= a <= 0.25:
            continue
        if extreme:
            if not (0.5 <= a <= float(hi)):
                n_out += 1
        elif a < float(lo) or a > float(hi):
            n_out += 1
    if n_out < 1:
        return values, 0

    changed = 0
    out = []
    for v in values:
        fv = float(v)
        af = abs(fv)
        if not _is_finite(fv):
            out.append(1.0)
            changed += 1
            continue
        if n_hide >= 3 and 0.008 <= af <= 0.25:
            out.append(fv)
            continue
        if extreme:
            if 0.5 <= af <= float(hi):
                out.append(fv)
            else:
                out.append(1.0)
                changed += 1
        elif af < float(lo) or af > float(hi):
            out.append(1.0)
            changed += 1
        else:
            out.append(fv)
    return out, changed


def fix_fbx_percent_times10_only(fbx_path, dry_run=False):
    """
    Publish-safe safety net (single write pass):
      Only divide true percent*10 peaks (e.g. 1800 -> 1.8).
      Never cascade-flatten small scales to 1.0 (hide / mask / attachments).
      Visibility helpers and weapon/attachment/mask bones are excluded.
    """
    with open(fbx_path, "rb") as f:
        data = f.read()
    head = _as_bytearray(data)[:18]
    if head != bytearray(b"Kaydara FBX Binary"):
        return 0, ["not a binary FBX"]

    _version, _is64, roots = parse_fbx(data)
    data = _as_bytearray(data)
    scale_curves = collect_curves_by_prop(roots, "Scal")

    hit_models = []
    visibility_models = []
    for cid, meta in scale_curves.items():
        model, prop, channel, curve = meta
        if is_visibility_scale_model(model) or is_weapon_or_attachment_model(model):
            if is_visibility_scale_model(model) and model not in visibility_models:
                visibility_models.append(model)
            continue
        values, _c, _l, _e, _cl = find_keyvalue_array_file_pos(curve)
        if values and curve_has_percent_times10_signature(values):
            if model not in hit_models:
                hit_models.append(model)
    hit_set = set(hit_models)

    targets = {}
    for cid, meta in scale_curves.items():
        model, prop, channel, curve = meta
        if is_visibility_scale_model(model) or is_weapon_or_attachment_model(model):
            continue
        values, _c, _l, _e, _cl = find_keyvalue_array_file_pos(curve)
        if not values:
            continue
        need = (model in hit_set)
        if (not need) and curve_has_percent_times10_signature(values):
            need = True
        # Do not cascade-flatten small scales to 1.0 (destroys hide / mask / attachments).
        if need:
            targets[cid] = meta

    if not targets:
        reports = []
        if visibility_models:
            reports.append(
                "skip visibility-scale models=%s" % (", ".join(visibility_models))
            )
        reports.append("skip: no percent*10 / cascade scale curves")
        return 0, reports

    reports = []
    if visibility_models:
        reports.append(
            "skip visibility-scale models=%s" % (", ".join(visibility_models))
        )
    if hit_models:
        reports.append("percent*10-only models=%s" % (", ".join(hit_models)))

    def _publish_scale_fix(values):
        return fix_percent_times10_values(values)

    data, patch_reports, total = patch_curve_map(
        data, targets, _publish_scale_fix, "SCALE", dry_run=dry_run
    )
    reports.extend(patch_reports)

    if total > 0 and not dry_run:
        with open(fbx_path, "wb") as f:
            f.write(bytes(data) if sys.version_info[0] >= 3 else data)
    return total, reports


def fix_fbx_file(fbx_path, threshold=10.0, divisor=1000.0, dry_run=False, force=False):
    """
    OFFLINE / MANUAL legacy safety-net. Prefer fix_fbx_percent_times10_only
    for publish. This broader path can still touch inverse/tiny/trans and must
    not be the default publish fixer.
    """
    with open(fbx_path, "rb") as f:
        data = f.read()
    head = _as_bytearray(data)[:18]
    if head != bytearray(b"Kaydara FBX Binary"):
        return 0, ["not a binary FBX"]

    _version, _is64, roots = parse_fbx(data)
    data = _as_bytearray(data)
    all_reports = []
    total = 0

    scale_curves = collect_curves_by_prop(roots, "Scal")
    hit, hit_models = detect_max_scale_percent_bug(scale_curves)
    if not hit and not force:
        return 0, [
            "skip: no Max ScaleXYZ percent*10 signature "
            "(safe no-op for normal FBX files)"
        ]

    all_reports.append(
        "signature-hit models=%s" % (", ".join(hit_models) if hit_models else "<force>")
    )

    # Strict by default even in legacy API: only percent*10 signature curves.
    signed_scale = {}
    for cid, meta in scale_curves.items():
        model, prop, channel, curve = meta
        if is_visibility_scale_model(model):
            continue
        values, _c, _l, _e, _cl = find_keyvalue_array_file_pos(curve)
        if not values:
            continue
        if curve_has_percent_times10_signature(values):
            signed_scale[cid] = meta

    def _scale_fixer(values):
        return fix_percent_times10_values(values, divisor=divisor)

    data, reports, n = patch_curve_map(
        data, signed_scale, _scale_fixer, "SCALE", dry_run=dry_run
    )
    all_reports.extend(reports)
    total += n

    # Legacy force path may still clean insane translations; default publish
    # should call fix_fbx_percent_times10_only instead (no TRANS).
    if force:
        trans_curves = collect_curves_by_prop(roots, "Translat")

        def _trans_fixer(values):
            insane = 0
            for v in values:
                fv = float(v)
                if (not _is_finite(fv)) or abs(fv) > 1000.0:
                    insane += 1
            if insane < 3:
                return list(values), 0
            return fix_translation_outliers(values, soft_limit=50.0, hard_limit=1000.0)

        data, reports, n = patch_curve_map(
            data, trans_curves, _trans_fixer, "TRANS", dry_run=dry_run
        )
        all_reports.extend(reports)
        total += n

    if total > 0 and not dry_run:
        with open(fbx_path, "wb") as f:
            f.write(bytes(data) if sys.version_info[0] >= 3 else data)
    return total, all_reports


def main():
    ap = argparse.ArgumentParser(description="Fix Max FBX scale percent*10 corruption")
    ap.add_argument("fbx", help="input FBX path")
    ap.add_argument("-o", "--output", help="output FBX (default: overwrite with .bak)")
    ap.add_argument("--threshold", type=float, default=10.0)
    ap.add_argument("--divisor", type=float, default=1000.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--inspect", action="store_true", help="only list bad scale curves")
    args = ap.parse_args()

    in_path = args.fbx
    with open(in_path, "rb") as f:
        data = f.read()
    data_ba = _as_bytearray(data)
    if data_ba[:18] != bytearray(b"Kaydara FBX Binary"):
        print("Only binary FBX is supported.", file=sys.stderr)
        return 2

    version, is64, roots = parse_fbx(data_ba)
    print("FBX version", version, "64bit", is64)
    scale_curves = collect_scale_curve_ids(roots)
    print("scale curves:", len(scale_curves))

    bad = []
    for cid, (model, prop, channel, curve) in scale_curves.items():
        values, child, length, encoding, comp_len = find_keyvalue_array_file_pos(curve)
        if not values:
            continue
        vmax = max(abs(v) for v in values)
        vmin = min(values)
        if vmax > args.threshold:
            bad.append((model, prop, channel, vmin, vmax, length))
            print(
                "BAD %s | %s | %s | min=%.6g max=%.6g keys=%d"
                % (model, prop, channel, vmin, vmax, length)
            )
    if args.inspect or not bad:
        print("bad curves:", len(bad))
        return 0

    out_data, reports, total = patch_file(
        data_ba, scale_curves, args.threshold, args.divisor, dry_run=args.dry_run
    )
    for line in reports:
        print(line)
    print("total keys changed:", total)

    if args.dry_run:
        print("dry-run: no file written")
        return 0

    out_path = args.output
    if not out_path:
        bak = in_path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(in_path, bak)
            print("backup:", bak)
        out_path = in_path
    with open(out_path, "wb") as f:
        f.write(bytes(out_data) if sys.version_info[0] >= 3 else out_data)
    print("wrote:", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

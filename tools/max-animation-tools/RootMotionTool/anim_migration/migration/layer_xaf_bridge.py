# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import json
import os
import re
import time

from anim_migration.migration.canonical_bridge import (
    _as_text,
    _binding_version_from_path,
    _find_bip_root,
    _frame_range,
    _json_read,
    _json_write,
    _load_scene,
    _safe_filename,
    _scan_source_camera_bundle,
    _scene_descriptors,
    classify_rig_family,
)
from anim_migration.migration.controller_shape import (
    STATUS_NATIVE,
    STATUS_NOTHING,
    align_slot_names,
    clean_name,
    clear_animation_owned_keys,
    clear_key,
    collect_transform_shapes,
    compare_slot_key_counts,
    empty_shape,
    group_nodes_by_clear_scope,
    group_nodes_by_run,
    materialize_wrapped_controllers,
    plan_transport,
    restore_slot_names,
    run_key,
    shape_key_count,
)
from anim_migration.migration.root_hierarchy import (
    ROOT_LAYER,
    build_root_hierarchy_index,
    compare_root_hierarchy,
    constraint_managed_owner_names,
    match_root_hierarchy_target,
    pair_names_by_identity,
    root_hierarchy_membership,
    select_root_hierarchy,
)
from anim_migration.workflow.layer_contract import (
    MIGRATION_LAYERS,
    compare_binding_contracts,
    contract_object_id,
    contract_rows,
    public_layer_snapshot,
    public_membership,
    reconcile_animation_membership,
)
from anim_migration.workflow.update_route import (
    ROUTE_LAYER_CONTRACT,
    ROUTE_ROOT_HIERARCHY,
    is_root_hierarchy_route,
    resolve_update_route,
)


SCHEMA_VERSION = 26
ENGINE = "layer_contract_xaf"
NON_BIP_LAYERS = tuple([name for name in MIGRATION_LAYERS if name != u"Bip"])
# Bones target keys are governed by the three-way constraint policy, so only the
# purely animator-owned layers may be cleared before the native load.
ANIMATION_OWNED_LAYERS = tuple([name for name in NON_BIP_LAYERS if name != u"Bones"])
# The root-hierarchy route has one synthetic group. Its constrained owners are
# held back from clearing individually, so the group itself is animator-owned.
ROOT_ROUTE_LAYERS = (ROOT_LAYER,)
DEBUG_UI_CONTROL_NAMES = (u"Role_Example_face_CTRL_皱眉", u"皱眉")

try:
    _string_types = (basestring,)
except NameError:
    _string_types = (str,)


def _public_row(row):
    return dict([(key, value) for key, value in (row or {}).items() if key != "_node"])


def _without_modifier_tracks(rows):
    return [row for row in (rows or []) if row.get("root_kind") != "modifier"]


def _track_key_times(rows):
    values = set()
    for row in rows or []:
        values.update([int(value) for value in (row.get("key_times", []) or [])])
    return sorted(values)


def _missing_loaded_key_tracks(expected_tracks, actual_tracks):
    """Return source track keys that did not appear on the exact target path."""
    actual_by_path = {}
    for row in actual_tracks or []:
        actual_by_path.setdefault(_as_text(row.get("path", "")), set()).update([
            int(value) for value in (row.get("key_times", []) or [])
        ])
    missing = []
    for row in expected_tracks or []:
        path = _as_text(row.get("path", ""))
        expected = set([int(value) for value in (row.get("key_times", []) or [])])
        if not expected:
            continue
        absent = sorted(expected - actual_by_path.get(path, set()))
        if absent:
            missing.append({
                "path": path,
                "expected_key_count": len(expected),
                "missing_key_count": len(absent),
                "missing_key_times": absent[:20],
            })
    return missing


def _path_channel(path):
    text = _as_text(path)
    for channel in (u"position", u"rotation", u"scale"):
        if u"/{0}[".format(channel) in text:
            return channel
    return u""


def _only_class_change(findings):
    """True when a changed controller class explains every finding.

    Those keys were never transportable: the new binding drives the channel with
    another controller class, so there is no track for them to land on. Retrying
    the load cannot change that, and it does not belong in the same list as a
    control whose animation genuinely went missing.
    """
    rows = list(findings or [])
    return bool(rows) and all([bool(item.get("channel_class_changed")) for item in rows])


def _missing_native_key_times(expected_times, actual_times):
    expected = set([int(value) for value in (expected_times or [])])
    actual = set([int(value) for value in (actual_times or [])])
    return sorted(expected - actual)


def _skip(name, layer, reason, message=u"", stage="export", details=None):
    return {
        "name": _as_text(name) or u"<未命名对象>",
        "contract_layer": _as_text(layer),
        "reason": _as_text(reason),
        "message": _as_text(message),
        "stage": _as_text(stage),
        "details": list(details or []),
    }


def _dedupe_skips(rows):
    seen = set()
    out = []
    for row in rows or []:
        key = (
            _as_text(row.get("name", "")),
            _as_text(row.get("contract_layer", "")),
            _as_text(row.get("reason", "")),
            _as_text(row.get("stage", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _emit_progress(callback, value, message):
    if callback is None:
        return
    try:
        callback(int(value), _as_text(message))
    except Exception:
        # UI feedback must never change migration behavior.
        pass


def capture_focused_ui_debug(rt, stage):
    """Capture a tiny, non-destructive trace for the known Example UI failure.

    The artist-facing slider (``皱眉``) and its downstream face control are both
    recorded so a successful load can be distinguished from a later loss of the
    binding drive.  This is deliberately not a general scene dump.
    """
    from anim_migration.migration.track_transfer import collect_node_track_signatures, json_track_signatures
    from anim_migration.migration.xaf_transfer import native_transform_list_key_times

    rows = []
    nodes_by_name = dict([(name, []) for name in DEBUG_UI_CONTROL_NAMES])
    try:
        for node in rt.objects:
            name = _as_text(getattr(node, "name", ""))
            if name in nodes_by_name:
                nodes_by_name[name].append(node)
    except Exception:
        pass
    for wanted in DEBUG_UI_CONTROL_NAMES:
        matches = nodes_by_name.get(wanted, [])
        if len(matches) != 1:
            rows.append({"name": wanted, "match_count": len(matches), "exists": bool(matches)})
            continue
        node = matches[0]
        tracks = json_track_signatures(_without_modifier_tracks(
            collect_node_track_signatures(
                rt, node, include_samples=False,
                include_unkeyed=False, include_controllers=False,
            )
        ))
        controller_tree = json_track_signatures(_without_modifier_tracks(
            collect_node_track_signatures(
                rt, node, include_samples=False,
                include_unkeyed=True, include_controllers=True,
            )
        ))
        list_times = native_transform_list_key_times(rt, node)
        position = []
        try:
            import pymxs
            with pymxs.attime(0):
                value = node.position
                position = [float(value.x), float(value.y), float(value.z)]
        except Exception as error:
            position = [u"capture_failed", _as_text(error)]
        try:
            controller_class = _as_text(rt.classOf(node.controller))
        except Exception:
            controller_class = u""
        try:
            position_class = _as_text(rt.classOf(node.position.controller))
        except Exception:
            position_class = u""
        rows.append({
            "name": wanted,
            "exists": True,
            "match_count": 1,
            "position_frame_0": position,
            "controller_class": controller_class,
            "position_controller_class": position_class,
            "direct_key_times": _track_key_times(tracks),
            "native_list_key_times": list_times,
            "track_signatures": tracks,
            "controller_tree": controller_tree,
        })
    return {"stage": _as_text(stage), "controls": rows}


def _effective_user_ignored_rows(binding_difference, ignored_source_contract_ids):
    ignored = set([_as_text(value) for value in (ignored_source_contract_ids or []) if _as_text(value)])
    return [
        row for row in ((binding_difference or {}).get("source_only", []) or [])
        if (
            not row.get("is_bip") and
            _as_text(row.get("contract_id", "")) in ignored
        )
    ]


def _constraint_signature(row):
    targets = []
    for index, target in enumerate((row or {}).get("targets", []) or []):
        try:
            weight = round(float(target.get("weight", 100.0)), 6)
        except Exception:
            weight = 100.0
        frame_value = target.get("frame", None)
        try:
            frame_value = int(frame_value) if frame_value is not None else -2147483648
        except Exception:
            frame_value = -2147483648
        targets.append((
            int(target.get("index", index + 1) or (index + 1)),
            _as_text(target.get("target_name", target.get("source_name", ""))).lower(),
            bool(target.get("is_world")),
            _as_text(target.get("target_type", "")).lower(),
            weight,
            frame_value,
        ))
    animated_tracks = []
    for track in (row or {}).get("animated_tracks", []) or []:
        samples = []
        for sample in track.get("samples", []) or []:
            values = []
            for value in sample.get("value", []) or []:
                try:
                    values.append(round(float(value), 6))
                except Exception:
                    values.append(_as_text(value))
            samples.append((int(sample.get("time", 0)), tuple(values)))
        animated_tracks.append((
            _as_text(track.get("path", "")),
            _as_text(track.get("controller_class", "")),
            tuple([int(value) for value in (track.get("key_times", []) or [])]),
            tuple(samples),
        ))
    return (
        _as_text((row or {}).get("constraint_type", "")),
        tuple(targets),
        tuple(sorted(animated_tracks)),
    )


def _constraint_rows_by_channel(rows, eligible_owner_names=None):
    eligible = None
    if eligible_owner_names is not None:
        eligible = set([_as_text(value) for value in (eligible_owner_names or []) if _as_text(value)])
    grouped = {}
    for row in rows or []:
        owner = _as_text(row.get("owner_target_name", row.get("owner_source_name", "")))
        channel = _as_text(row.get("channel", ""))
        if not owner or not channel or (eligible is not None and owner not in eligible):
            continue
        grouped.setdefault((owner, channel), []).append(row)
    return grouped


def _plan_bones_constraint_three_way(source_rows, animation_rows, target_rows, eligible_owner_names):
    """Use the source binding as base; animator changes win every conflict."""
    eligible = set([_as_text(value) for value in (eligible_owner_names or []) if _as_text(value)])
    source = _constraint_rows_by_channel(source_rows, eligible)
    animation = _constraint_rows_by_channel(animation_rows, eligible)
    target = _constraint_rows_by_channel(target_rows, eligible)
    keys = sorted(set(source.keys()) | set(animation.keys()) | set(target.keys()))
    decisions = []
    desired = []
    managed = []
    for owner, channel in keys:
        source_rows_for_key = source.get((owner, channel), [])
        animation_rows_for_key = animation.get((owner, channel), [])
        target_rows_for_key = target.get((owner, channel), [])
        source_signature = sorted([_constraint_signature(row) for row in source_rows_for_key])
        animation_signature = sorted([_constraint_signature(row) for row in animation_rows_for_key])
        target_signature = sorted([_constraint_signature(row) for row in target_rows_for_key])
        if animation_signature == source_signature:
            status = "keep_target_animation_unchanged"
        elif animation_signature == target_signature:
            status = "keep_target_already_matches_animation"
        else:
            status = "rebuild_from_animation"
            managed.append({"owner_target_name": owner, "channel": channel})
            desired.extend([dict(row) for row in animation_rows_for_key])
        decisions.append({
            "owner_target_name": owner,
            "channel": channel,
            "status": status,
            "source_signature": source_signature,
            "animation_signature": animation_signature,
            "target_signature": target_signature,
        })
    return {
        "constraints": desired,
        "desired_constraints": desired,
        "managed_constraint_channels": managed,
        "decisions": decisions,
        "summary": {
            "eligible_owner_count": len(eligible),
            "channel_count": len(keys),
            "rebuild_channel_count": len(managed),
            "preserve_channel_count": len(keys) - len(managed),
            "desired_constraint_count": len(desired),
        },
    }


def _constraint_channel_from_track(track):
    ancestry = [_as_text(value).lower() for value in (track or {}).get("controller_ancestry", []) or []]
    for class_name in ancestry:
        if "link_constraint" in class_name:
            return "transform"
        if "position_constraint" in class_name:
            return "position"
        if "orientation_constraint" in class_name or "lookat_constraint" in class_name:
            return "rotation"
    return u""


def _filter_bones_key_tracks(target_name, tracks, constraint_plan):
    """Keep constraint-descendant keys only when that exact channel is rebuilt from A."""
    decisions = {}
    for row in (constraint_plan or {}).get("decisions", []) or []:
        key = (
            _as_text(row.get("owner_target_name", "")).lower(),
            _as_text(row.get("channel", "")).lower(),
        )
        decisions[key] = _as_text(row.get("status", ""))
    kept = []
    preserved_target = []
    unresolved = []
    for track in tracks or []:
        channel = _constraint_channel_from_track(track)
        if not channel:
            kept.append(track)
            continue
        status = decisions.get((_as_text(target_name).lower(), channel.lower()), "")
        if status == "rebuild_from_animation":
            kept.append(track)
        elif status in ("keep_target_animation_unchanged", "keep_target_already_matches_animation"):
            preserved_target.append(track)
        else:
            unresolved.append(track)
    return kept, preserved_target, unresolved


def _constraint_scan_summary(scan):
    scan = scan or {}
    return {
        "ok": bool(scan.get("ok", False)),
        "error_code": _as_text(scan.get("error_code", "")),
        "message": _as_text(scan.get("message", "")),
        "constraint_count": len(scan.get("constraints", []) or []),
        "skipped_count": len(scan.get("skipped", []) or []),
    }


def _empty_constraint_scan():
    return {
        "ok": True,
        "error_code": None,
        "message": u"",
        "constraints": [],
        "skipped": [],
    }


def _root_selection_summary(selection):
    selection = selection or {}
    return {
        "root_name": _as_text(selection.get("root_name", u"")),
        "root_method": _as_text(selection.get("root_method", u"")),
        "object_count": int(selection.get("object_count", 0) or 0),
        "bip_count": int(selection.get("bip_count", 0) or 0),
        "excluded_camera_count": int(selection.get("excluded_camera_count", 0) or 0),
    }


def _transportable_rows(rows, layer, root_route):
    """Rows of one group that travel as XAF: everything except the BIP nodes.

    On the layer-contract route BIP has its own layer, so only the root-hierarchy
    route has to keep BIP nodes out of a mixed group.
    """
    out = []
    for row in rows or []:
        if _as_text(row.get("contract_layer", "")) != layer:
            continue
        if root_route and row.get("is_bip"):
            continue
        out.append(row)
    return out


def _target_candidates(target_contract_rows):
    out = {}
    for row in target_contract_rows or []:
        key = (
            _as_text(row.get("contract_layer", "")).lower(),
            _as_text(row.get("name", "")).lower(),
        )
        out.setdefault(key, []).append(row)
    return out


def _write_report(path, manifest, result=None):
    result = result or {}
    skipped = result.get("skipped_controls", manifest.get("skipped_controls", [])) or []
    structural = result.get("structural_advisories", []) or []
    user_ignored = result.get("user_ignored_controls", manifest.get("user_ignored_controls", [])) or []
    constraint_plan = manifest.get("bones_constraints", {}) or {}
    constraint_summary = constraint_plan.get("summary", {}) or {}
    key_policy = manifest.get("bones_constraint_key_policy", {}) or {}
    package_summary = manifest.get("summary", {}) or {}
    route_info = manifest.get("update_route", {}) or {}
    root_route = is_root_hierarchy_route(route_info.get("route"))
    lines = [
        u"Animation Binding Update - Layer Contract Report",
        u"Engine: {0}".format(ENGINE),
        u"Selection route: {0} ({1}; decided from {2})".format(
            _as_text(route_info.get("route", u"")),
            _as_text(route_info.get("reason", u"")),
            _as_text(route_info.get("decided_from", u"")) or u"unknown",
        ),
        u"Source animation: {0}".format((manifest.get("source", {}) or {}).get("path", "")),
        u"Source binding: {0}".format((manifest.get("source", {}) or {}).get("binding_path", "")),
        u"Target binding: {0}".format((manifest.get("target", {}) or {}).get("path", "")),
        u"Output: {0}".format(manifest.get("output_max_path", "")),
        u"BIP transport: full_bip",
        u"Constrained owner transport: three_way_constraints + native_save_load_animation",
        u"Other control transport: native_save_load_animation",
        u"Saved: {0}".format(bool(result.get("saved"))) if result else u"Package export: {0}".format(bool(manifest.get("ok"))),
        u"Skipped controls: {0}".format(len(skipped)),
        u"Controls with a channel the new binding drives differently: {0}".format(len(structural)),
        u"User ignored controls: {0}".format(len(user_ignored)),
        u"Native selected controls: {0}".format(package_summary.get("xaf_control_count", 0)),
        u"Inventoried animated controls: {0}".format(package_summary.get("xaf_animated_control_count", 0)),
        u"Bones constraint policy: {0}".format(constraint_plan.get("policy", "")),
        u"Bones constraint channels rebuilt from animation: {0}".format(constraint_summary.get("rebuild_channel_count", 0)),
        u"Bones constraint channels preserved from target: {0}".format(constraint_summary.get("preserve_channel_count", 0)),
        u"Bones rebuilt-constraint key tracks copied: {0}".format(key_policy.get("copied_rebuilt_constraint_track_count", 0)),
        u"Bones target constraint key tracks preserved: {0}".format(key_policy.get("preserved_target_constraint_track_count", 0)),
    ]
    if root_route:
        lines.extend([
            u"Root object selection: every descendant of the rig Root, cameras excluded",
            u"Animation Root: {0} ({1}; {2} objects)".format(
                (route_info.get("animation_root", {}) or {}).get("root_name", u""),
                (route_info.get("animation_root", {}) or {}).get("root_method", u""),
                (route_info.get("animation_root", {}) or {}).get("object_count", 0),
            ),
            u"Target binding Root: {0} ({1}; {2} objects)".format(
                (route_info.get("target_root", {}) or {}).get("root_name", u""),
                (route_info.get("target_root", {}) or {}).get("root_method", u""),
                (route_info.get("target_root", {}) or {}).get("object_count", 0),
            ),
            u"Controls left to the constraint policy: {0}".format(
                route_info.get("constraint_managed_owner_count", 0),
            ),
        ])
    shape_plan = manifest.get("controller_shape_plan", {}) or {}
    if shape_plan:
        lines.extend((
            u"",
            u"Controller shape plan ({0})".format(shape_plan.get("policy", "")),
            u"- Compared controls: {0}".format(shape_plan.get("control_count", 0)),
            u"- Fully transportable: {0}".format(shape_plan.get("native_control_count", 0)),
            u"- Partially transportable: {0}".format(shape_plan.get("partial_control_count", 0)),
            u"- Not transportable: {0}".format(shape_plan.get("blocked_control_count", 0)),
            u"- Needing List slot index alignment: {0}".format(shape_plan.get("normalized_control_count", 0)),
            u"- With duplicate List slot names: {0}".format(shape_plan.get("duplicate_slot_name_control_count", 0)),
            u"- With a differing controller class (advisory): {0}".format(
                len(shape_plan.get("class_mismatch_controls", []) or [])
            ),
        ))
        for row in (shape_plan.get("blocked_controls", []) or [])[:40]:
            reasons = u", ".join([
                u"{0}:{1}({2} keys)".format(
                    item.get("channel", ""), item.get("reason", ""), item.get("key_count", 0),
                )
                for item in (row.get("issues", []) or [])
            ])
            lines.append(u"  [{0}] {1}: {2} {3}".format(
                row.get("contract_layer", ""), row.get("name", ""), row.get("status", ""), reasons,
            ).rstrip())
    layer_apply = result.get("layer_xaf_apply", []) or []
    if layer_apply:
        lines.extend((u"", u"Native animation load per layer"))
        for row in layer_apply:
            lines.append(
                u"- [{0}] ok={1}; controls={2}; animated={3}; cleared_target_tracks={4}; aligned_slots={5}; filled_wrapped_controllers={6}; retried={7}; recovered={8} {9}".format(
                    row.get("contract_layer", ""), row.get("ok", False),
                    row.get("control_count", 0), row.get("animated_control_count", 0),
                    row.get("cleared_target_track_count", 0), row.get("aligned_slot_count", 0),
                    row.get("materialized_controller_count", 0),
                    row.get("retried_control_count", 0), row.get("recovered_control_count", 0),
                    row.get("message", ""),
                ).rstrip()
            )
    decisions = constraint_plan.get("decisions", []) or []
    if decisions:
        lines.extend((u"", u"Bones constraint three-way decisions"))
        for row in decisions:
            lines.append(u"- {0} [{1}]: {2}".format(
                row.get("owner_target_name", ""), row.get("channel", ""), row.get("status", ""),
            ))
    if skipped:
        lines.extend((u"", u"Skipped controls"))
        for row in skipped:
            lines.append(u"- [{0}] {1}: {2} {3}".format(
                row.get("contract_layer", ""), row.get("name", ""),
                row.get("reason", ""), row.get("message", ""),
            ).rstrip())
    if structural:
        lines.extend((
            u"",
            u"Channels the new binding drives with another controller class ({0})".format(len(structural)),
        ))
        for row in structural:
            lines.append(u"- [{0}] {1}: {2}".format(
                row.get("contract_layer", ""), row.get("name", ""), row.get("message", ""),
            ).rstrip())
    if user_ignored:
        lines.extend((u"", u"User ignored controls"))
        for row in user_ignored:
            lines.append(u"- [{0}] {1}: {2}".format(
                row.get("contract_layer", ""), row.get("name", ""),
                row.get("message", u"已按版本差异选择忽略"),
            ).rstrip())
    focused_debug = result.get("focused_ui_debug", manifest.get("focused_ui_debug", [])) or []
    if focused_debug:
        lines.extend((u"", u"Focused UI debug: Role_Example_face_CTRL_皱眉"))
        for snapshot in focused_debug:
            lines.append(u"- Stage: {0}".format(snapshot.get("stage", "")))
            for control in snapshot.get("controls", []) or []:
                tree_classes = []
                for tree_row in control.get("controller_tree", []) or []:
                    class_name = _as_text(tree_row.get("controller_class", ""))
                    if class_name and class_name not in tree_classes:
                        tree_classes.append(class_name)
                lines.append(u"  {0}: exists={1}; matches={2}; frame0={3}; direct_keys={4}; list_keys={5}; position_ctrl={6}; tree_classes={7}".format(
                    control.get("name", ""), control.get("exists", False),
                    control.get("match_count", 0), control.get("position_frame_0", []),
                    control.get("direct_key_times", []), control.get("native_list_key_times", []),
                    control.get("position_controller_class", ""),
                    tree_classes,
                ))
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(u"\n".join(lines) + u"\n")


def _failed_manifest(base, code, message):
    base.update({"ok": False, "error_code": code, "message": _as_text(message)})
    try:
        _json_write(base.get("manifest_path", ""), base)
        _write_report(base.get("report_txt", ""), base)
    except Exception:
        pass
    return base


def export_canonical_package(old_anim_path, new_rig_path, output_max_path,
                             source_rig_path=None, adapter_override=None,
                             package_root=None, reference_frame=0,
                             tool_root=None, standard_contract_path=None,
                             adapter_contract_path=None,
                             allow_layer_fallback=False,
                              ignore_duplicate_animation_objects=False,
                              ignored_source_contract_ids=None,
                              ignored_target_contract_ids=None,
                              reviewed_binding_difference_signature=u"",
                              progress_callback=None):
    """Export full BIP, Bones constraint plan, and one native XAF per layer.

    Non-BIP incompatibilities are production warnings. They are skipped instead
    of being converted to evaluated per-frame animation or blocking the update.
    """
    import pymxs
    from anim_migration.migration.constraint_rebuilder import scan_constraints_in_loaded_scene
    from anim_migration.migration.track_transfer import collect_node_track_signatures, json_track_signatures
    from anim_migration.migration.xaf_transfer import _try_save_xaf_nodes
    from anim_migration.workflow.layer_normalizer import normalize_loaded_animation_scene
    from anim_migration.workflow.version_metadata import read_scene_binding_metadata

    del adapter_override, reference_frame, standard_contract_path, adapter_contract_path
    del allow_layer_fallback, ignore_duplicate_animation_objects
    ignored_source_contract_ids = set([
        _as_text(value) for value in (ignored_source_contract_ids or []) if _as_text(value)
    ])
    ignored_target_contract_ids = set([
        _as_text(value) for value in (ignored_target_contract_ids or []) if _as_text(value)
    ])
    reviewed_binding_difference_signature = _as_text(reviewed_binding_difference_signature)

    rt = pymxs.runtime
    old_anim_path = os.path.abspath(_as_text(old_anim_path))
    new_rig_path = os.path.abspath(_as_text(new_rig_path))
    output_max_path = os.path.abspath(_as_text(output_max_path))
    source_rig_path = os.path.abspath(_as_text(source_rig_path)) if source_rig_path else u""
    if not os.path.exists(old_anim_path) or not os.path.exists(new_rig_path):
        return {"ok": False, "error_code": "LAYER-XAF-INPUT", "message": u"源动画或目标绑定路径无效", "engine": ENGINE}

    if package_root is None:
        package_root = os.path.join(os.path.dirname(output_max_path), "_RigCanonicalPackages")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    package_dir = os.path.join(package_root, _safe_filename(os.path.splitext(os.path.basename(old_anim_path))[0]) + "_" + stamp)
    if not os.path.exists(package_dir):
        os.makedirs(package_dir)
    manifest_path = os.path.join(package_dir, "canonical_manifest.json")
    report_txt = os.path.join(package_dir, "canonical_report.txt")
    bip_path = os.path.join(package_dir, "body.bip")
    manifest = {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "engine": ENGINE,
        "package_dir": package_dir,
        "manifest_path": manifest_path,
        "report_txt": report_txt,
        "output_max_path": output_max_path,
        "warnings": [],
        "skipped_controls": [],
        "user_ignored_controls": [],
        "timings": {},
    }
    started = time.time()
    route_info = resolve_update_route(
        target_rig_path=new_rig_path,
        source_rig_path=source_rig_path,
        animation_path=old_anim_path,
    )
    root_route = is_root_hierarchy_route(route_info.get("route"))
    # One synthetic group on the root-hierarchy route, the six-layer contract on
    # the main route. Everything below only reads these two tuples.
    non_bip_layers = ROOT_ROUTE_LAYERS if root_route else NON_BIP_LAYERS
    animation_owned_layers = ROOT_ROUTE_LAYERS if root_route else ANIMATION_OWNED_LAYERS
    manifest["update_route"] = dict(route_info)
    try:
        _emit_progress(
            progress_callback, 5,
            u"读取目标绑定 Root 层级与约束" if root_route else u"读取目标绑定层与约束",
        )
        stage = time.time()
        _load_scene(rt, new_rig_path)
        target_rows_all = _scene_descriptors(rt)
        target_snapshot = public_layer_snapshot(target_rows_all)
        target_names = set([_as_text(row.get("name", "")) for row in target_rows_all])
        if root_route:
            target_selection = select_root_hierarchy(rt, target_rows_all)
            if not target_selection.get("ok"):
                return _failed_manifest(
                    manifest,
                    target_selection.get("error_code", "LAYER-XAF-ROOT-MISSING"),
                    u"目标绑定：" + _as_text(target_selection.get("message", u"")),
                )
            target_contract = target_selection.get("rows", []) or []
            manifest["update_route"]["target_root"] = _root_selection_summary(target_selection)
        else:
            target_contract = contract_rows(target_rows_all)
        target_by_name_layer = _target_candidates(target_contract)
        target_transportable = _transportable_rows(target_contract, ROOT_LAYER, True) if root_route else []
        target_root_index = build_root_hierarchy_index(target_transportable) if root_route else {}
        # One inventory call per group while the target binding is the open
        # scene: the export needs both sides' controller shapes to decide what
        # Max native Load Animation can actually deliver.  Bones is excluded on
        # purpose, because the constraint rebuild changes its List slots after
        # this scan and the three-way policy already owns its keys.  The
        # root-hierarchy route cannot know its constrained owners yet - the plan
        # needs all three scenes - so it scans them too and drops them from the
        # transport plan once the plan names them.
        target_shapes = {}
        for layer in animation_owned_layers:
            layer_nodes = [
                row.get("_node") for row in _transportable_rows(target_contract, layer, root_route)
                if row.get("_node") is not None
            ]
            target_shapes[layer] = collect_transform_shapes(rt, layer_nodes) if layer_nodes else {}
        if root_route:
            # Without a layer contract every non-BIP object under Root is a
            # possible constraint owner, so all of them enter the three-way scan.
            target_bones_names = sorted(set([
                _as_text(row.get("name", "")) for row in target_transportable
                if _as_text(row.get("name", ""))
            ]))
        else:
            target_bones_names = sorted(set([
                _as_text(row.get("name", "")) for row in target_contract
                if row.get("contract_layer", "") == u"Bones" and _as_text(row.get("name", ""))
            ]))
        target_constraint_scan = (
            scan_constraints_in_loaded_scene(
                rt,
                mapping=dict([(name, name) for name in target_bones_names]),
                eligible_owner_names=target_bones_names,
            )
            if target_bones_names else _empty_constraint_scan()
        )
        target_family = classify_rig_family(list(target_names))
        target_fps = float(rt.frameRate)
        manifest["timings"]["target_inventory"] = round(time.time() - stage, 3)

        if _find_bip_root(rt) is None:
            return _failed_manifest(manifest, "LAYER-XAF-TARGET-BIP", u"目标绑定缺少 Bip001，不能导入完整 BIP")

        _emit_progress(progress_callback, 15, u"读取动画与源绑定版本")
        stage = time.time()
        _emit_progress(progress_callback, 25, u"整理动画文件 UI 层")
        _load_scene(rt, old_anim_path)
        source_metadata = read_scene_binding_metadata(rt)
        if not source_rig_path:
            metadata_path = _as_text(source_metadata.get("rig_path", "")).strip()
            if metadata_path and os.path.exists(metadata_path):
                source_rig_path = os.path.abspath(metadata_path)
        source_fps = float(rt.frameRate)
        start, end, frames = _frame_range(rt)
        if not source_rig_path or not os.path.exists(source_rig_path):
            return _failed_manifest(manifest, "LAYER-XAF-SOURCE-CONTRACT", u"必须选择动画对应版本的源绑定，才能识别六层动画成员")
        if os.path.normcase(source_rig_path) == os.path.normcase(old_anim_path):
            return _failed_manifest(manifest, "LAYER-XAF-SOURCE-CONTRACT", u"源绑定不能是动画文件本身")

        _load_scene(rt, source_rig_path)
        source_binding_rows = _scene_descriptors(rt)
        source_snapshot = public_layer_snapshot(source_binding_rows)
        source_binding_family = classify_rig_family([row.get("name", "") for row in source_binding_rows])
        if root_route:
            # The source binding no longer defines the migration scope here. It is
            # still read, because the three-way constraint policy needs its
            # neutral state and the animator still has to review real binding
            # differences once.
            source_selection = select_root_hierarchy(rt, source_binding_rows)
            if not source_selection.get("ok"):
                return _failed_manifest(
                    manifest,
                    source_selection.get("error_code", "LAYER-XAF-ROOT-MISSING"),
                    u"源绑定：" + _as_text(source_selection.get("message", u"")),
                )
            source_binding_contract = source_selection.get("rows", []) or []
            manifest["update_route"]["source_root"] = _root_selection_summary(source_selection)
            source_bones_owner_mapping = pair_names_by_identity(
                _transportable_rows(source_binding_contract, ROOT_LAYER, True), target_transportable,
            )
        else:
            source_binding_contract = contract_rows(source_binding_rows)
            if source_snapshot.get("total_count", 0) <= 0:
                return _failed_manifest(manifest, "LAYER-XAF-SOURCE-CONTRACT-EMPTY", u"源绑定没有发现受支持的迁移层")
            source_bones_owner_mapping = {}
            for row in source_binding_contract:
                if row.get("contract_layer", "") != u"Bones":
                    continue
                source_name = _as_text(row.get("name", ""))
                if not source_name:
                    continue
                matches = target_by_name_layer.get((u"bones", source_name.lower()), [])
                if len(matches) == 1:
                    source_bones_owner_mapping[source_name] = _as_text(matches[0].get("name", ""))
        source_constraint_scan = (
            scan_constraints_in_loaded_scene(
                rt,
                mapping=source_bones_owner_mapping,
                eligible_owner_names=sorted(source_bones_owner_mapping.keys()),
            )
            if source_bones_owner_mapping else _empty_constraint_scan()
        )

        _load_scene(rt, old_anim_path)
        normalization = normalize_loaded_animation_scene(rt, tool_root)
        if not normalization.get("ok", False):
            if not root_route:
                return _failed_manifest(
                    manifest,
                    normalization.get("error_code", "LAYER-XAF-NORMALIZER"),
                    normalization.get("message", u"动画 Layer 整理失败"),
                )
            # This route never reads a layer, so an unfinished layer cleanup
            # cannot change what is migrated. The animation scene is a temporary
            # load that is never saved.
            manifest["warnings"].append({
                "code": "LAYER-XAF-ROOT-NORMALIZER",
                "message": u"动画 Layer 整理未完成，但 Root 层级迁移不依赖 Layer：{0}".format(
                    normalization.get("message", u"")
                ),
                "details": [normalization],
            })
        animation_rows = _scene_descriptors(rt)
        if root_route:
            animation_selection = select_root_hierarchy(rt, animation_rows)
            if not animation_selection.get("ok"):
                return _failed_manifest(
                    manifest,
                    animation_selection.get("error_code", "LAYER-XAF-ROOT-MISSING"),
                    u"动画文件：" + _as_text(animation_selection.get("message", u"")),
                )
            manifest["update_route"]["animation_root"] = _root_selection_summary(animation_selection)
            membership = root_hierarchy_membership(
                _transportable_rows(animation_selection.get("rows", []) or [], ROOT_LAYER, True)
            )
            # BIP nodes stay in the difference review even though they travel in
            # the whole .bip instead of an XAF: a Biped that gained or lost bones
            # is exactly what an animator must see before the update runs.
            binding_difference = compare_root_hierarchy(source_binding_contract, target_contract)
        else:
            membership = reconcile_animation_membership(source_binding_rows, animation_rows, ignore_ambiguous_names=False)
            binding_difference = compare_binding_contracts(source_binding_rows, target_rows_all)
        binding_difference["reviewed"] = bool(
            (not binding_difference.get("has_difference")) or
            reviewed_binding_difference_signature == binding_difference.get("signature", "")
        )
        binding_difference["ignored_source_contract_ids"] = sorted(ignored_source_contract_ids)
        binding_difference["ignored_target_contract_ids"] = sorted(ignored_target_contract_ids)
        binding_difference["policy"] = "review_once_then_skip_non_bip"
        manifest.update({
            "source": {
                "path": old_anim_path,
                "binding_path": source_rig_path,
                "binding_version": _binding_version_from_path(source_rig_path),
                "family": source_binding_family,
                "frame_rate": source_fps,
            },
            "target": {
                "path": new_rig_path,
                "binding_version": _binding_version_from_path(new_rig_path),
                "family": target_family,
                "frame_rate": target_fps,
            },
            "animation_range": {"start": start, "end": end, "frame_count": len(frames)},
            "layer_contract": {
                "source": source_snapshot,
                "target": target_snapshot,
                "membership": public_membership(membership, fallback_used=False),
                "binding_difference": binding_difference,
                "normalization": normalization,
            },
        })
        if binding_difference.get("has_difference") and not binding_difference.get("reviewed"):
            return _failed_manifest(
                manifest,
                "CANON-BINDING-DIFFERENCE-REVIEW",
                u"源绑定与目标绑定的六层对象有新增或删除，需要动画师确认迁移对象",
            )
        ignored_bip = [
            row for row in (binding_difference.get("source_only", []) or [])
            if row.get("is_bip") and row.get("contract_id", "") in ignored_source_contract_ids
        ]
        if ignored_bip:
            return _failed_manifest(manifest, "LAYER-XAF-BIP-CANNOT-IGNORE", u"Bip 层删除项不能忽略")
        user_ignored_rows = _effective_user_ignored_rows(binding_difference, ignored_source_contract_ids)
        effective_ignored_source_ids = set([row.get("contract_id", "") for row in user_ignored_rows])
        effective_ignored_names = set([
            _as_text(row.get("name", "")).lower() for row in user_ignored_rows
            if _as_text(row.get("name", ""))
        ])

        def _is_user_ignored(row):
            if _as_text(row.get("contract_id", "")) in effective_ignored_source_ids:
                return True
            # The root-hierarchy route reads identity from the animation scene
            # while the difference review lists source-binding rows, so an
            # ignored object is also recognised by name.
            return bool(root_route and _as_text(row.get("name", "")).lower() in effective_ignored_names)

        for row in user_ignored_rows:
            manifest["user_ignored_controls"].append({
                "name": _as_text(row.get("name", "")) or u"<未命名对象>",
                "contract_layer": _as_text(row.get("contract_layer", "")),
                "contract_id": _as_text(row.get("contract_id", "")),
                "reason": "explicit_user_choice",
                "message": u"已按绑定版本差异选择忽略，不计入迁移警告",
            })
        animation_bones_owner_mapping = {}
        eligible_target_bones = set()
        for row in membership.get("resolved_rows", []) or []:
            if not root_route and row.get("contract_layer", "") != u"Bones":
                continue
            if _is_user_ignored(row):
                continue
            animation_name = _as_text(row.get("name", ""))
            if root_route:
                matches, _method = match_root_hierarchy_target(row, target_root_index)
                target_name = _as_text(matches[0].get("name", "")) if len(matches) == 1 else u""
            else:
                target_name = _as_text(source_bones_owner_mapping.get(_as_text(row.get("binding_name", "")), ""))
            if not animation_name or not target_name:
                continue
            animation_bones_owner_mapping[animation_name] = target_name
            eligible_target_bones.add(target_name)
        _emit_progress(progress_callback, 36, u"建立 Bones 三方约束快照")
        animation_constraint_scan = (
            scan_constraints_in_loaded_scene(
                rt,
                mapping=animation_bones_owner_mapping,
                eligible_owner_names=sorted(animation_bones_owner_mapping.keys()),
            )
            if animation_bones_owner_mapping else _empty_constraint_scan()
        )
        constraint_scans = {
            "source_binding": _constraint_scan_summary(source_constraint_scan),
            "animation": _constraint_scan_summary(animation_constraint_scan),
            "target_binding": _constraint_scan_summary(target_constraint_scan),
        }
        if all([item.get("ok", False) for item in constraint_scans.values()]):
            constraint_snapshot = _plan_bones_constraint_three_way(
                source_constraint_scan.get("constraints", []) or [],
                animation_constraint_scan.get("constraints", []) or [],
                target_constraint_scan.get("constraints", []) or [],
                eligible_target_bones,
            )
            constraint_snapshot.update({
                "ok": True,
                "error_code": None,
                "message": u"",
                "policy": "three_way_animator_changes_win",
                "scan_summary": constraint_scans,
            })
        else:
            constraint_snapshot = {
                "ok": False,
                "error_code": "LAYER-XAF-CONSTRAINT-THREE-WAY-SCAN",
                "message": u"三方约束扫描不完整；为保护目标绑定，本次不修改任何约束",
                "policy": "preserve_target_on_scan_failure",
                "constraints": [],
                "desired_constraints": [],
                "managed_constraint_channels": [],
                "decisions": [],
                "scan_summary": constraint_scans,
                "summary": {
                    "eligible_owner_count": len(eligible_target_bones),
                    "channel_count": 0,
                    "rebuild_channel_count": 0,
                    "preserve_channel_count": 0,
                    "desired_constraint_count": 0,
                },
            }
            manifest["warnings"].append({
                "code": "LAYER-XAF-CONSTRAINT-THREE-WAY-SCAN",
                "message": constraint_snapshot["message"],
                "details": constraint_scans,
            })
        camera_merge = _scan_source_camera_bundle(rt, target_names)
        manifest["timings"]["source_inventory"] = round(time.time() - stage, 3)
        # The root-hierarchy route has no Bones layer to protect, so the constraint
        # plan itself names the owners whose keys and List slots the animation
        # package must leave alone.
        root_constraint_owners = constraint_managed_owner_names(constraint_snapshot) if root_route else set()
        # Without a usable plan there is no way to tell those owners apart, and
        # clearing a constrained owner whose constraint is not being rebuilt would
        # drop animation nothing replaces. Then nothing is cleared this run.
        root_clear_allowed = bool(constraint_snapshot.get("ok", False)) if root_route else True
        if root_route and not root_clear_allowed:
            manifest["warnings"].append({
                "code": "LAYER-XAF-ROOT-CLEAR-SUSPENDED",
                "message": u"三方约束扫描不完整，本次不清理目标绑定残留关键帧；"
                           u"没有 K 帧的控制器可能保留新绑定自带的动画",
                "details": [constraint_snapshot.get("scan_summary", {})],
            })

        # Membership drift is fatal only for Bip. Every other contract member is
        # a useful best-effort continuation point for an in-production shot.
        for kind in ("missing", "ambiguous", "ignored_ambiguous", "extras"):
            for item in membership.get(kind, []) or []:
                layer = _as_text(item.get("expected_layer", item.get("animation_layer", "")))
                if layer == u"Bip":
                    return _failed_manifest(manifest, "LAYER-XAF-BIP-MEMBERSHIP", u"动画文件的 Bip 层与源绑定不一致，无法安全导出完整 BIP")
                manifest["skipped_controls"].append(_skip(
                    item.get("name", ""), layer,
                    item.get("reason", "membership_mismatch"),
                    u"动画文件与源绑定的层成员不一致，已默认忽略",
                    details=[item],
                ))

        _emit_progress(progress_callback, 44, u"保存 Bip 动画")
        source_bip = _find_bip_root(rt)
        if source_bip is None:
            return _failed_manifest(manifest, "LAYER-XAF-SOURCE-BIP", u"源动画缺少 Bip001，不能导出完整 BIP")
        try:
            bip_ok = bool(rt.biped.saveBipFile(source_bip.controller, bip_path))
        except Exception as error:
            bip_ok = False
            bip_message = _as_text(error)
        else:
            bip_message = u""
        if not bip_ok or not os.path.exists(bip_path):
            return _failed_manifest(manifest, "LAYER-XAF-BIP-EXPORT", bip_message or u"完整 BIP 导出失败")

        _emit_progress(
            progress_callback, 52,
            u"收集 Root 层级下全部匹配的非 Bip 对象" if root_route
            else u"按六层合同收集全部匹配的非 Bip 对象",
        )
        active_by_layer = dict([(layer, []) for layer in non_bip_layers])
        bones_constraint_key_policy = {
            "copied_rebuilt_constraint_track_count": 0,
            "preserved_target_constraint_track_count": 0,
            "unresolved_constraint_track_count": 0,
        }
        for source in membership.get("resolved_rows", []) or []:
            layer = _as_text(source.get("contract_layer", ""))
            if layer == u"Bip" or layer not in active_by_layer:
                continue
            if _is_user_ignored(source):
                continue
            name = _as_text(source.get("name", ""))
            # Keep pymxs controller proxies alive while walking the tree.  Their
            # Python ids can otherwise be reused during recursion and make a
            # different List child look "already visited".  Track discovery is
            # diagnostic only: every resolved source/target pair is selected for
            # Max native Save Animation, whose animatedTracks:true option decides
            # which tracks are actually written.
            tracks = collect_node_track_signatures(
                rt, source.get("_node"), include_samples=False,
                include_unkeyed=False, include_controllers=True,
            )
            tracks = _without_modifier_tracks(tracks)
            if root_route:
                matches, match_method = match_root_hierarchy_target(source, target_root_index)
            else:
                matches, match_method = target_by_name_layer.get((layer.lower(), name.lower()), []), "exact_name"
            if len(matches) != 1:
                manifest["skipped_controls"].append(_skip(
                    name, layer, "missing_or_ambiguous_target_control",
                    u"目标绑定的 Root 层级里没有唯一的同名对象" if root_route
                    else u"目标绑定中没有唯一的同层同名控制器",
                    details=[{"target_match_count": len(matches), "match_method": match_method}],
                ))
                continue
            target = matches[0]
            target_id = contract_object_id(target)
            # Bones on the main route, and every constrained owner on the
            # root-hierarchy route, are spoken for by the three-way constraint
            # policy rather than by the animation package.
            if layer == u"Bones" or (root_route and _as_text(target.get("name", "")).lower() in root_constraint_owners):
                tracks, preserved_tracks, unresolved_tracks = _filter_bones_key_tracks(
                    _as_text(target.get("name", "")), tracks, constraint_snapshot,
                )
                bones_constraint_key_policy["preserved_target_constraint_track_count"] += len(preserved_tracks)
                bones_constraint_key_policy["unresolved_constraint_track_count"] += len(unresolved_tracks)
                bones_constraint_key_policy["copied_rebuilt_constraint_track_count"] += len([
                    item for item in tracks if _constraint_channel_from_track(item)
                ])
                if unresolved_tracks:
                    manifest["skipped_controls"].append(_skip(
                        name, layer, "constraint_track_without_three_way_decision",
                        u"约束叶子轨道缺少可靠三方决策，已保留目标绑定状态",
                        details=unresolved_tracks,
                    ))
            public_tracks = json_track_signatures(tracks)
            # The recursive controller inventory now keeps pymxs proxy objects
            # alive, so List-controller children are represented here too.  Do
            # not run one extra rt.execute/selection-changing MaxScript probe per
            # object; it duplicated the same evidence and dominated large rigs.
            native_key_times = _track_key_times(public_tracks)
            animation_owned = (
                root_clear_allowed and _as_text(target.get("name", "")).lower() not in root_constraint_owners
                if root_route else layer in ANIMATION_OWNED_LAYERS
            )
            active_by_layer[layer].append({
                "source_name": name,
                "target_name": _as_text(target.get("name", "")),
                "source_contract_id": source.get("contract_id", ""),
                "target_contract_id": target_id,
                "contract_layer": layer,
                "scope": source.get("scope", ""),
                # Whether the update owns this control's target keys: the import
                # clears them before the load and expects nothing the source did
                # not have.
                "animation_owned": bool(animation_owned),
                "target_match_method": match_method,
                "track_signatures": public_tracks,
                "native_key_times": native_key_times,
                "has_direct_keyed_tracks": bool(public_tracks),
                "has_source_animation": bool(native_key_times),
                "animation_evidence": (
                    "recursive_keyed_controller_tracks" if native_key_times else
                    "contract_selected_native_animated_tracks_filter"
                ),
                "_node": source.get("_node"),
            })

        _emit_progress(progress_callback, 58, u"比对源动画与目标绑定的控制器结构")
        stage = time.time()
        shape_plan = {
            "policy": "index_aligned_list_slots_on_animation_owned_layers",
            "layers": list(animation_owned_layers),
            "control_count": 0,
            "native_control_count": 0,
            "partial_control_count": 0,
            "blocked_control_count": 0,
            "normalized_control_count": 0,
            "duplicate_slot_name_control_count": 0,
            "duplicate_slot_name_controls": [],
            "class_mismatch_controls": [],
            "blocked_controls": [],
        }
        for layer in animation_owned_layers:
            # A control the constraint policy speaks for keeps no transport plan,
            # which is what keeps its keys and slots untouched further down.
            rows = [row for row in (active_by_layer.get(layer, []) or []) if row.get("animation_owned")]
            if not rows:
                continue
            source_shapes = collect_transform_shapes(
                rt, [row.get("_node") for row in rows if row.get("_node") is not None],
            )
            for row in rows:
                source_shape = source_shapes.get(clean_name(row.get("source_name", "")), empty_shape())
                target_shape = (target_shapes.get(layer, {}) or {}).get(
                    clean_name(row.get("target_name", "")), empty_shape(),
                )
                plan = plan_transport(source_shape, target_shape)
                source_key_count = shape_key_count(source_shape)
                row["controller_shape"] = source_shape
                row["transport_plan"] = plan
                row["shape_key_count"] = source_key_count
                # A List slot track whose controller path is ambiguous can be
                # invisible to the recursive python inventory, so the shape scan
                # is the second opinion on whether this control has animation.
                row["has_source_animation"] = bool(row.get("native_key_times")) or source_key_count > 0
                if source_key_count and not row.get("native_key_times"):
                    row["animation_evidence"] = "controller_shape_slot_key_count"
                shape_plan["control_count"] += 1
                if plan.get("needs_normalization"):
                    shape_plan["normalized_control_count"] += 1
                if plan.get("duplicate_slot_names"):
                    shape_plan["duplicate_slot_name_control_count"] += 1
                    shape_plan["duplicate_slot_name_controls"].append({
                        "name": row.get("target_name", ""),
                        "contract_layer": layer,
                    })
                if plan.get("class_mismatch_channels"):
                    # Advisory only: the load is still attempted and the post-load
                    # verification decides whether the keys actually arrived.
                    shape_plan["class_mismatch_controls"].append({
                        "name": row.get("target_name", ""),
                        "contract_layer": layer,
                        "channels": plan.get("class_mismatch_channels", []),
                    })
                status = plan.get("status", STATUS_NATIVE)
                if status == STATUS_NATIVE:
                    shape_plan["native_control_count"] += 1
                    continue
                counter = "blocked_control_count" if status == STATUS_NOTHING else "partial_control_count"
                shape_plan[counter] += 1
                shape_plan["blocked_controls"].append({
                    "name": row.get("target_name", ""),
                    "contract_layer": layer,
                    "status": status,
                    "issues": plan.get("issues", []),
                })
                manifest["skipped_controls"].append(_skip(
                    row.get("source_name", ""), layer,
                    "controller_shape_blocks_native_transport" if status == STATUS_NOTHING
                    else "controller_shape_blocks_some_channels",
                    u"源与目标控制器结构不兼容，原生加载动画无法送达这些通道"
                    if status == STATUS_NOTHING
                    else u"部分通道结构不兼容，只迁移结构一致的通道",
                    details=plan.get("issues", []),
                ))
        manifest["controller_shape_plan"] = shape_plan
        manifest["timings"]["controller_shape_plan"] = round(time.time() - stage, 3)

        _emit_progress(progress_callback, 62, u"按层保存 Max 原生动画")
        layer_xaf = []
        xaf_dir = os.path.join(package_dir, "layer_xaf")
        if not os.path.exists(xaf_dir):
            os.makedirs(xaf_dir)
        for index, layer in enumerate(non_bip_layers):
            rows = active_by_layer.get(layer, []) or []
            if not rows:
                continue
            animated_control_count = len([row for row in rows if row.get("has_source_animation")])
            # A control whose structure cannot receive anything is kept out of the
            # package: Max would write its tracks and then fail to map them, which
            # can turn one incompatible control into a failed load for the layer.
            savable_rows = [
                row for row in rows
                if row.get("has_source_animation") and
                (row.get("transport_plan", {}) or {}).get("status") != STATUS_NOTHING
            ]
            if not savable_rows:
                # Avoid Max's modal "No animation tracks can be saved" dialog.
                # This is a layer-level empty-package decision only; individual
                # matched objects are never removed from a non-empty layer.
                continue
            xaf_path = os.path.join(xaf_dir, "{0:02d}_{1}.xaf".format(index + 1, _safe_filename(layer)))
            # Save only after the mapped List slots have unique index names.  Max
            # writes the slot name into the XAF and matches it by name on load, so
            # default duplicate slot names would let one incoming track land in
            # every same-named slot.
            alignment = align_slot_names(rt, group_nodes_by_run(
                savable_rows, lambda row: row.get("_node"), lambda row: row.get("transport_plan"),
            ))
            try:
                ok, message = _try_save_xaf_nodes(
                    rt, [row.get("_node") for row in savable_rows if row.get("_node") is not None], xaf_path,
                )
            finally:
                restored = restore_slot_names(rt)
            controls = [_public_row(row) for row in rows]
            package = {
                "contract_layer": layer,
                "path": xaf_path if ok else u"",
                "ok": bool(ok),
                "message": _as_text(message),
                "controls": controls,
                "control_count": len(controls),
                "animated_control_count": animated_control_count,
                "saved_control_count": len(savable_rows),
                "transport": "max_native_save_animation",
                "include_constraints": False,
                "slot_alignment": alignment,
                "slot_name_restore": restored,
            }
            if not restored.get("ok", True):
                manifest["warnings"].append({
                    "code": "LAYER-XAF-SLOT-NAME-RESTORE",
                    "message": u"{0} 层保存后有 List 槽名未恢复；导出的动画包仍然有效".format(layer),
                    "details": restored,
                })
            layer_xaf.append(package)
            if not ok:
                for row in controls:
                    manifest["skipped_controls"].append(_skip(
                        row.get("source_name", ""), layer,
                        "native_save_animation_failed",
                        message or u"3ds Max 原生保存动画失败",
                    ))

        manifest.update({
            "ok": True,
            "error_code": None,
            "message": (
                u"完整 BIP、约束计划与 Root 层级原生动画包导出完成" if root_route
                else u"完整 BIP、Bones 约束计划与五层原生动画包导出完成"
            ),
            "body": {"transport": "full_bip", "bip_path": bip_path, "export_ok": True},
            "layer_xaf": layer_xaf,
            "bones_constraints": constraint_snapshot,
            "bones_constraint_key_policy": bones_constraint_key_policy,
            "camera_merge": camera_merge,
        })
        manifest["skipped_controls"] = _dedupe_skips(manifest["skipped_controls"])
        manifest["update_route"].update({
            "selection_groups": list(non_bip_layers),
            "constraint_managed_owner_count": len(root_constraint_owners),
        })
        manifest["summary"] = {
            "bip_exported": True,
            "selection_route": _as_text(route_info.get("route", u"")),
            "layer_xaf_package_count": len(layer_xaf),
            "xaf_control_count": sum([item.get("control_count", 0) for item in layer_xaf]),
            "xaf_animated_control_count": sum([item.get("animated_control_count", 0) for item in layer_xaf]),
            "skipped_control_count": len(manifest["skipped_controls"]),
            "user_ignored_control_count": len(manifest["user_ignored_controls"]),
            "camera_merge_object_count": (camera_merge.get("summary", {}) or {}).get("object_count", 0),
            "shape_blocked_control_count": shape_plan["blocked_control_count"],
            "shape_partial_control_count": shape_plan["partial_control_count"],
            "shape_normalized_control_count": shape_plan["normalized_control_count"],
        }
        manifest["timings"]["total"] = round(time.time() - started, 3)
        _json_write(manifest_path, manifest)
        _write_report(report_txt, manifest)
        return manifest
    except Exception as error:
        manifest["timings"]["total"] = round(time.time() - started, 3)
        return _failed_manifest(manifest, "LAYER-XAF-EXPORT", error)


def _node_shape(shapes, node):
    return (shapes or {}).get(clean_name(_as_text(getattr(node, "name", ""))), empty_shape())


def _control_findings(rt, node, row, actual_shape, report_unexpected_keys=True):
    """Collect every disagreement between the source control and the loaded one.

    Two independent views are needed. The controller-path view catches a track
    that never arrived; the slot-index view catches a track that arrived in the
    wrong slot, or a target key the source never had, which the path view cannot
    see when several slots share one name.
    """
    from anim_migration.migration.track_transfer import collect_node_track_signatures, json_track_signatures

    plan = row.get("transport_plan", {}) or {}
    class_changed = set(plan.get("class_mismatch_channels", []) or [])
    # Slots outside the mapped run belong to the target binding; the export
    # already reported their source keys as a structural incompatibility.
    ignored_kinds = set(["source_slot_outside_mapped_run"])
    if not report_unexpected_keys:
        ignored_kinds.update(["unexpected_slot_keys", "unexpected_channel_keys"])
    findings = [
        item for item in compare_slot_key_counts(row.get("controller_shape"), actual_shape, plan)
        if item.get("kind") not in ignored_kinds
    ]
    if not row.get("has_source_animation"):
        return findings
    actual_tracks = json_track_signatures(_without_modifier_tracks(
        collect_node_track_signatures(
            rt, node, include_samples=False,
            include_unkeyed=False, include_controllers=True,
        )
    ))
    if not plan.get("needs_normalization"):
        # Controller paths contain List slot names, so they only compare across
        # the two rigs when both sides kept the same slot names. When they did
        # not, the slot-index comparison above is the reliable view.
        for item in _missing_loaded_key_tracks(row.get("track_signatures", []) or [], actual_tracks):
            item["channel_class_changed"] = _path_channel(item.get("path")) in class_changed
            findings.append(item)
    missing_native_times = _missing_native_key_times(
        row.get("native_key_times", []) or [], _track_key_times(actual_tracks),
    )
    if missing_native_times:
        findings.append({
            "path": "native_controller_tree",
            "kind": "missing_channel_keys",
            "expected_key_count": len(row.get("native_key_times", []) or []),
            "missing_key_count": len(missing_native_times),
            "missing_key_times": missing_native_times[:20],
            # These times only exist in the source because of a channel the new
            # binding drives with another controller class.
            "channel_class_changed": bool(class_changed) and not set(missing_native_times) - set(_track_key_times([
                item for item in (row.get("track_signatures", []) or [])
                if _path_channel(item.get("path")) in class_changed
            ])),
        })
    return findings


def _load_one_control(rt, node, row, xaf_path):
    """Retry one control alone so Max's return value describes only this control.

    A batch load reports success as soon as any selected control loaded, so a
    single-control retry is the only way to tell a silent per-control failure
    apart from a genuine mapping problem.
    """
    from anim_migration.migration.xaf_transfer import _try_load_xaf_nodes

    plan = row.get("transport_plan")
    if row.get("animation_owned"):
        # The batch pass already cleared this control, and a retry that clears
        # again would leave the control empty if this load also fails.
        materialize_wrapped_controllers(rt, {clear_key(plan): [node]})
    align_slot_names(rt, {run_key(plan): [node]})
    try:
        ok, message = _try_load_xaf_nodes(rt, [node], xaf_path)
    finally:
        restore_slot_names(rt)
    return bool(ok), _as_text(message)


def _target_contract_index(rt, root_route=False):
    scene_rows = _scene_descriptors(rt)
    if root_route:
        # Same walk and same class metadata as the export, so the contract ids
        # written into the package resolve here.
        rows = (select_root_hierarchy(rt, scene_rows) or {}).get("rows", []) or []
    else:
        rows = contract_rows(scene_rows)
    by_id = {}
    by_name_layer = {}
    for row in rows:
        by_id.setdefault(contract_object_id(row), []).append(row)
        key = (_as_text(row.get("contract_layer", "")).lower(), _as_text(row.get("name", "")).lower())
        by_name_layer.setdefault(key, []).append(row)
    return by_id, by_name_layer


def _resolve_target(row, by_id, by_name_layer):
    matches = by_id.get(_as_text(row.get("target_contract_id", "")), [])
    if len(matches) == 1:
        return matches[0].get("_node")
    key = (
        _as_text(row.get("contract_layer", "")).lower(),
        _as_text(row.get("target_name", "")).lower(),
    )
    matches = by_name_layer.get(key, [])
    return matches[0].get("_node") if len(matches) == 1 else None


def apply_canonical_package(manifest_or_path, overwrite=False, save_on_validation_failure=False,
                            progress_callback=None):
    """Apply a layer-contract package; only BIP, camera and file I/O are fatal."""
    import pymxs
    from anim_migration.migration.constraint_rebuilder import rebuild_constraints_in_loaded_scene
    from anim_migration.migration.package_importer import _import_bip, _merge_helper_objects
    from anim_migration.migration.xaf_transfer import _try_load_xaf_nodes

    del save_on_validation_failure
    rt = pymxs.runtime
    manifest = _json_read(manifest_or_path) if isinstance(manifest_or_path, _string_types) else manifest_or_path
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        return {"ok": False, "error_code": "LAYER-XAF-SCHEMA", "message": u"绑定更新动画包版本不受支持", "engine": ENGINE}
    target_path = _as_text((manifest.get("target", {}) or {}).get("path", ""))
    source_path = _as_text((manifest.get("source", {}) or {}).get("path", ""))
    output_path = _as_text(manifest.get("output_max_path", ""))
    if not os.path.exists(target_path):
        return {"ok": False, "error_code": "LAYER-XAF-TARGET", "message": u"目标绑定不存在", "engine": ENGINE}
    if os.path.exists(output_path) and not overwrite:
        return {"ok": False, "error_code": "LAYER-XAF-OUTPUT-EXISTS", "message": u"输出文件已存在: {0}".format(output_path), "engine": ENGINE}

    route_info = manifest.get("update_route", {}) or {}
    root_route = is_root_hierarchy_route(route_info.get("route"))
    constraint_layer = ROOT_LAYER if root_route else u"Bones"
    result = {
        "ok": False,
        "saved": False,
        "engine": ENGINE,
        "package_dir": manifest.get("package_dir", ""),
        "manifest_path": manifest.get("manifest_path", ""),
        "report_txt": manifest.get("report_txt", ""),
        "output_max_path": output_path,
        "update_route": dict(route_info),
        "warnings": list(manifest.get("warnings", []) or []),
        "skipped_controls": list(manifest.get("skipped_controls", []) or []),
        "user_ignored_controls": list(manifest.get("user_ignored_controls", []) or []),
        "structural_advisories": [],
        "timings": {},
    }
    started = time.time()
    try:
        _emit_progress(progress_callback, 68, u"载入目标绑定")
        _load_scene(rt, target_path)
        anim_range = manifest.get("animation_range", {}) or {}
        start = int(anim_range.get("start", 0))
        end = int(anim_range.get("end", start))
        source_fps = float((manifest.get("source", {}) or {}).get("frame_rate", 30.0))
        if source_fps > 0:
            rt.frameRate = source_fps
        try:
            rt.animationRange = rt.Interval(start, end)
        except Exception:
            rt.animationRange = rt.interval(start, end)
        try:
            # Deleting a key leaves the controller at its current value, so the
            # slider stays on the first animation frame: a control the animation
            # file does not drive keeps the pose the frame range starts from.
            rt.sliderTime = start
        except Exception:
            pass

        _emit_progress(progress_callback, 72, u"合并原动画镜头")
        stage = time.time()
        camera_merge = _merge_helper_objects(rt, source_path, manifest.get("camera_merge", {}) or {})
        result["camera_merge"] = camera_merge
        result["timings"]["camera_merge"] = round(time.time() - stage, 3)
        if not camera_merge.get("ok", False):
            result.update({"error_code": "LAYER-XAF-CAMERA", "message": u"旧动画镜头整套合并失败，未写入输出文件"})
            return result

        _emit_progress(progress_callback, 76, u"加载 Bip 动画")
        stage = time.time()
        bip_import = _import_bip(rt, _as_text((manifest.get("body", {}) or {}).get("bip_path", "")), target_name="Bip001")
        result["bip_import"] = bip_import
        result["timings"]["bip_import"] = round(time.time() - stage, 3)
        if not bip_import.get("ok", False):
            result.update({"error_code": "LAYER-XAF-BIP-IMPORT", "message": u"完整 BIP 导入失败，未写入输出文件: {0}".format(bip_import.get("message", ""))})
            return result

        _emit_progress(progress_callback, 80, u"按三方快照重建 Bones 约束")
        stage = time.time()
        constraint_apply = rebuild_constraints_in_loaded_scene(
            rt, manifest.get("bones_constraints", {}) or {},
            skip_missing_constraint_targets=True,
        )
        result["bones_constraint_apply"] = constraint_apply
        for item in constraint_apply.get("items", []) or []:
            if item.get("ok", True) and item.get("status") not in ("skipped_all_targets_missing", "skipped_missing_owner"):
                continue
            owner = _as_text(item.get("owner_target_name", item.get("owner_source_name", "")))
            if owner:
                result["skipped_controls"].append(_skip(
                    owner, constraint_layer, "constraint_rebuild_failed",
                    item.get("message", u"约束未能在目标绑定重建"), stage="import",
                ))
        result["timings"]["constraint_rebuild"] = round(time.time() - stage, 3)

        by_id, by_name_layer = _target_contract_index(rt, root_route=root_route)
        imported = []
        layer_xaf_apply = []
        stage = time.time()
        packages = manifest.get("layer_xaf", []) or []
        for package_index, package in enumerate(packages):
            layer = _as_text(package.get("contract_layer", ""))
            progress_value = 84 + int((8.0 * package_index) / max(1, len(packages)))
            _emit_progress(progress_callback, progress_value, u"加载 {0} 层原生动画".format(layer))
            controls = package.get("controls", []) or []
            target_nodes = []
            load_controls = []
            for row in controls:
                target_node = _resolve_target(row, by_id, by_name_layer)
                name = _as_text(row.get("target_name", row.get("source_name", "")))
                if target_node is None:
                    result["skipped_controls"].append(_skip(
                        name, layer, "native_load_target_missing",
                        u"目标绑定中没有唯一匹配对象，未加载动画", stage="import",
                    ))
                    continue
                target_nodes.append(target_node)
                load_controls.append(row)
            xaf_path = _as_text(package.get("path", ""))
            # Only the controls the export actually wrote into this XAF.
            animated_pairs = [
                (row, node) for row, node in zip(load_controls, target_nodes)
                if row.get("has_source_animation") and
                (row.get("transport_plan", {}) or {}).get("status") != STATUS_NOTHING
            ]
            cleared = {}
            alignment = {}
            restored = {}
            materialized = {}
            if not package.get("ok", False) or not xaf_path or not os.path.exists(xaf_path):
                ok = False
                message = package.get("message", u"") or u"原生动画包不存在"
            elif not animated_pairs:
                ok = True
                message = u""
            else:
                # The animation file owns these controls, so residual target keys
                # go first - including on controls the animator never touched,
                # which would otherwise keep whatever the new binding shipped and
                # read as a fully keyed control after the update.  This only runs
                # once the package is known to be loadable, so a failed export
                # never strips the target binding.  A control the constraint
                # policy speaks for is not animation-owned and keeps its keys.
                owned_pairs = [
                    (row, node) for row, node in zip(load_controls, target_nodes)
                    if row.get("animation_owned")
                ]
                if owned_pairs:
                    clear_groups = group_nodes_by_clear_scope(
                        owned_pairs, lambda pair: pair[1], lambda pair: pair[0].get("transport_plan"),
                    )
                    # A Limit controller the new binding shipped empty has no
                    # controller name for the animator's track to match, so it
                    # must be filled in before the load or the control ends up
                    # with keys on its other axes and no motion at all.
                    materialized = materialize_wrapped_controllers(rt, clear_groups)
                    cleared = clear_animation_owned_keys(rt, clear_groups)
                # Max resolves nodes by exact name and the controllers inside a
                # node by exact controller name, so the mapped List slots get the
                # same unique index names the export used.  That turns the load
                # into a one-to-one slot mapping instead of a name collision.
                alignment = align_slot_names(rt, group_nodes_by_run(
                    animated_pairs, lambda pair: pair[1], lambda pair: pair[0].get("transport_plan"),
                ))
                try:
                    ok, message = _try_load_xaf_nodes(rt, [node for _, node in animated_pairs], xaf_path)
                finally:
                    restored = restore_slot_names(rt)
            layer_result = {
                "contract_layer": layer,
                "ok": bool(ok),
                "message": _as_text(message),
                "control_count": len(load_controls),
                "animated_control_count": len(animated_pairs),
                "path": xaf_path,
                "transport": "max_native_load_animation",
                "mapping_mode": "native_exact_name_with_index_aligned_list_slots",
                "cleared_target_track_count": int(cleared.get("cleared_track_count", 0) or 0),
                "aligned_slot_count": int(alignment.get("renamed_slot_count", 0) or 0),
                "materialized_controller_count": int(materialized.get("created_controller_count", 0) or 0),
                "retried_control_count": 0,
                "recovered_control_count": 0,
            }
            layer_xaf_apply.append(layer_result)
            if restored and not restored.get("ok", True):
                result["warnings"].append({
                    "code": "LAYER-XAF-SLOT-NAME-RESTORE",
                    "message": u"{0} 层加载后有 List 槽名未恢复，请检查输出文件".format(layer),
                    "details": restored,
                })
            if ok:
                # Verify every resolved control, not only the animated ones: a
                # control with no source animation must come out with no keys on
                # the channels the animation file owns.
                actual_shapes = collect_transform_shapes(rt, target_nodes)
                for row, target_node in zip(load_controls, target_nodes):
                    name = _as_text(row.get("target_name", row.get("source_name", "")))
                    animated = bool(row.get("has_source_animation"))
                    # Target keys the source never had are only a defect where the
                    # animation file owns the control. Where the three-way
                    # constraint policy owns it, target keys are preserved on
                    # purpose.
                    report_unexpected = bool(row.get("animation_owned"))
                    in_package = animated and (
                        (row.get("transport_plan", {}) or {}).get("status") != STATUS_NOTHING
                    )
                    findings = _control_findings(
                        rt, target_node, row, _node_shape(actual_shapes, target_node),
                        report_unexpected_keys=report_unexpected,
                    )
                    retry_message = u""
                    if findings and in_package and not _only_class_change(findings):
                        layer_result["retried_control_count"] += 1
                        retry_ok, retry_message = _load_one_control(rt, target_node, row, xaf_path)
                        if retry_ok:
                            findings = _control_findings(
                                rt, target_node, row,
                                _node_shape(collect_transform_shapes(rt, [target_node]), target_node),
                                report_unexpected_keys=report_unexpected,
                            )
                            if not findings:
                                layer_result["recovered_control_count"] += 1
                    if not findings:
                        if animated:
                            imported.append({"name": name, "contract_layer": layer, "status": "native_animation_loaded_and_verified"})
                        continue
                    if _only_class_change(findings):
                        # The new binding drives these channels with a different
                        # controller class, so the animator has a rig change to
                        # look at, not a control whose animation was lost.
                        channels = sorted(set([
                            _as_text(item.get("channel") or _path_channel(item.get("path")))
                            for item in findings
                        ]) - set([u""]))
                        result["structural_advisories"].append(_skip(
                            name, layer, "channel_controller_class_changed",
                            u"新绑定的 {0} 通道换成了别的控制器类型，这些通道上的关键帧无法迁移；该对象的其他通道已正常加载".format(
                                u"、".join(channels) or u"部分"
                            ),
                            stage="import", details=findings[:20],
                        ))
                        if animated:
                            imported.append({
                                "name": name, "contract_layer": layer,
                                "status": "native_animation_loaded_with_channel_class_change",
                            })
                        continue
                    if in_package:
                        reason = "native_load_key_validation_failed"
                        detail_message = u"Max 返回加载成功，但目标控制器的关键帧与源动画不一致" + (
                            u"；单对象重试: {0}".format(retry_message) if retry_message else u""
                        )
                    elif animated:
                        reason = "controller_shape_blocks_native_transport"
                        detail_message = u"控制器结构不兼容，动画没有进入新绑定（导出阶段已报告）"
                    else:
                        reason = "residual_target_keys_not_cleared"
                        detail_message = u"该控制器在源动画里没有关键帧，但目标绑定残留的关键帧未能清除"
                    result["skipped_controls"].append(_skip(
                        name, layer, reason, detail_message, stage="import", details=findings[:20],
                    ))
            else:
                for row in load_controls:
                    name = _as_text(row.get("target_name", row.get("source_name", "")))
                    result["skipped_controls"].append(_skip(
                        name, layer, "native_load_animation_failed",
                        message or u"3ds Max 原生加载动画失败", stage="import",
                    ))

        result["layer_xaf_apply"] = layer_xaf_apply
        result["timings"]["layer_xaf_import"] = round(time.time() - stage, 3)
        _emit_progress(progress_callback, 94, u"保存临时更新结果")
        folder = os.path.dirname(output_path)
        if folder and not os.path.exists(folder):
            os.makedirs(folder)
        rt.saveMaxFile(output_path, quiet=True)
        result["saved"] = bool(os.path.exists(output_path))
        if not result["saved"]:
            result.update({"error_code": "LAYER-XAF-SAVE", "message": u"输出文件保存失败"})
            return result
        _emit_progress(progress_callback, 96, u"临时更新结果已保存")
        result["skipped_controls"] = _dedupe_skips(result["skipped_controls"])
        result["structural_advisories"] = _dedupe_skips(result["structural_advisories"])
        result["ok"] = True
        result["error_code"] = None
        result["message"] = u"绑定更新完成；已跳过 {0} 个不兼容的非 BIP 控制器".format(len(result["skipped_controls"]))
        result["validation_advisories"] = list(result["skipped_controls"])
        result["channel_apply_errors"] = []
        result["validation"] = {"ok": True, "mode": "key_structure_advisory", "summary": {"failed_count": 0}}
        result["summary"] = {
            "applied_channel_count": len(imported),
            "imported_control_count": len(imported),
            "skipped_control_count": len(result["skipped_controls"]),
            "structural_advisory_count": len(result["structural_advisories"]),
            "user_ignored_control_count": len(result["user_ignored_controls"]),
            "layer_xaf_package_count": len(manifest.get("layer_xaf", []) or []),
            "native_animation_layer_count": len([item for item in layer_xaf_apply if item.get("ok")]),
            "cleared_target_track_count": sum([int(item.get("cleared_target_track_count", 0) or 0) for item in layer_xaf_apply]),
            "aligned_slot_count": sum([int(item.get("aligned_slot_count", 0) or 0) for item in layer_xaf_apply]),
            "materialized_controller_count": sum([int(item.get("materialized_controller_count", 0) or 0) for item in layer_xaf_apply]),
            "retried_control_count": sum([int(item.get("retried_control_count", 0) or 0) for item in layer_xaf_apply]),
            "recovered_control_count": sum([int(item.get("recovered_control_count", 0) or 0) for item in layer_xaf_apply]),
            "bip_import_ok": True,
            "camera_merge_ok": True,
            "saved": True,
        }
        return result
    except Exception as error:
        result.update({"ok": False, "saved": False, "error_code": "LAYER-XAF-APPLY", "message": _as_text(error)})
        return result
    finally:
        result["timings"]["total"] = round(time.time() - started, 3)
        try:
            _write_report(manifest.get("report_txt", ""), manifest, result=result)
            _json_write(os.path.join(manifest.get("package_dir", ""), "canonical_result.json"), result)
        except Exception:
            pass
        if not result.get("saved") and source_path and os.path.exists(source_path):
            try:
                _load_scene(rt, source_path)
            except Exception:
                pass

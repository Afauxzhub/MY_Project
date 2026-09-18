# -*- coding: utf-8 -*-
from __future__ import print_function
import datetime
import hashlib
import io
import json
import os
import re
import time

from anim_migration.migration.constraint_rebuilder import SUPPORTED_CONSTRAINTS, _get_target, _get_target_count, _iter_candidate_controllers
from anim_migration.migration.layer_mapping import build_layer_mapping, scene_layer_inventory
from anim_migration.migration.local_object_transfer import _collect_key_times, _node_transform_controllers, _safe_controller
from anim_migration.migration.track_transfer import aggregate_track_counts, build_morph_payload, collect_node_track_signatures, json_track_signatures, morph_target_paths, prepare_morph_signatures, sample_track_signature_groups, suspended_scene_redraw, unsupported_extra_tracks
from anim_migration.migration.xaf_transfer import _try_save_xaf, _try_save_xaf_nodes
from anim_migration.workflow.max_dialogs import SilentFileDialogs
from anim_migration.workflow.version_metadata import normalize_version, read_scene_binding_metadata

# Below this count, try a single batch XAF first (stable on typical skill clips).
# At or above, skip batch and use chunked/per-node export directly.
XAF_BATCH_DIRECT_THRESHOLD = 300
# Chunk size when batch export fails or object count is large.
XAF_CHUNK_EXPORT_SIZE = 40

try:
    _text_type = unicode
except NameError:
    _text_type = str


ANIMATOR_NAME_TOKENS = (
    "weapon", "prop", "locator", "loc", "target", "socket", "attach", "ik",
    "dummy", "point", "helper", "cam", "camera", u"武器", u"道具", u"目标", u"相机",
)


def _as_text(value):
    if value is None:
        return u""
    # Py2: json.dumps(ensure_ascii=False) may return UTF-8 bytes; decode safely.
    try:
        if (not isinstance(value, _text_type)) and isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except Exception:
                try:
                    return value.decode("gbk")
                except Exception:
                    return value.decode("utf-8", "replace")
    except Exception:
        pass
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _json_clean(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return dict([(_as_text(k), _json_clean(v)) for k, v in value.items()])
    if isinstance(value, (list, tuple)):
        return [_json_clean(x) for x in value]
    return _as_text(value)


def _mxs_escape(text):
    return _as_text(text).replace('"', '\\"')


def _json_write(path, data):
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(_as_text(json.dumps(_json_clean(data), ensure_ascii=False, indent=2)))
    return path


def _write_stage_status(package_dir, stage, detail=u""):
    try:
        _json_write(os.path.join(package_dir, "stage_status.json"), {
            "stage": _as_text(stage),
            "detail": _as_text(detail),
            "timestamp": _timestamp(),
        })
    except Exception:
        pass


def _timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_filename(name):
    text = _as_text(name) or "unnamed"
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = re.sub(r"\s+", "_", text)
    return text[:120]


def _binding_version_from_path(path):
    match = re.search(r"(?i)_v(\d{1,3})(?=\.max$)", os.path.basename(_as_text(path)))
    return normalize_version(match.group(1)) if match else u""


def _node_name(node):
    try:
        return _as_text(node.name)
    except Exception:
        return u""


def _class_name(rt, value):
    try:
        return _as_text(rt.classOf(value))
    except Exception:
        return u""


def _is_bip_node(rt, node):
    name = _node_name(node).lower()
    cls = _class_name(rt, node).lower()
    return name.startswith("bip") or "biped" in cls


def _user_prop(rt, node, name):
    try:
        value = rt.getProperty(node, rt.Name(name))
        if value is not None:
            return _as_text(value)
    except Exception:
        pass
    try:
        value = getattr(node, name)
        if value is not None:
            return _as_text(value)
    except Exception:
        pass
    try:
        value = rt.getUserProp(node, name)
        return _as_text(value)
    except Exception:
        return u""


def _reference_rig_metadata(rt, node):
    stable_text = _user_prop(rt, node, "rrStable").strip().lower()
    return {
        "rrGuid": _user_prop(rt, node, "rrGuid").strip(),
        "rrRole": _user_prop(rt, node, "rrRole").strip(),
        "rrStable": stable_text in ("true", "1", "yes", "on"),
        "rrReplacePolicy": _user_prop(rt, node, "rrReplacePolicy").strip().lower(),
        "rrParentGuid": _user_prop(rt, node, "rrParentGuid").strip(),
    }


def _is_animator_constraint_candidate(rt, node, has_keys):
    metadata = _reference_rig_metadata(rt, node)
    policy = metadata.get("rrReplacePolicy", "")
    if policy == "reconnect_constraint":
        return True
    if policy in ("reference_only", "ignore"):
        return False
    name = _node_name(node).lower()
    cls = _class_name(rt, node).lower()
    if any(token in name for token in ANIMATOR_NAME_TOKENS):
        return True
    if "camera" in cls:
        return True
    return False


def _scene_name_counts(rt):
    counts = {}
    for node in list(rt.objects):
        name = _node_name(node)
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _target_rig_inventory(rt, new_rig_path):
    with SilentFileDialogs(rt):
        rt.loadMaxFile(new_rig_path, quiet=True, useFileUnits=True)
    name_counts = _scene_name_counts(rt)
    guid_to_names = {}
    morph_paths = {}
    for node in list(rt.objects):
        name = _node_name(node)
        if not name:
            continue
        metadata = _reference_rig_metadata(rt, node)
        guid = metadata.get("rrGuid", "")
        if guid:
            guid_to_names.setdefault(guid, []).append(name)
        try:
            paths = morph_target_paths(rt, node)
        except Exception:
            paths = []
        if paths:
            morph_paths.setdefault(name, []).extend(paths)
    return {
        "names": set(name_counts.keys()),
        "name_counts": name_counts,
        "guid_to_names": guid_to_names,
        "morph_paths": dict([(name, sorted(set(paths))) for name, paths in morph_paths.items()]),
        "layer_inventory": scene_layer_inventory(rt),
        "has_adv_pelvis_marker": name_counts.get("Bone_Skin_Bip001 Pelvis", 0) == 1,
    }


def _node_by_name(rt, name):
    name = _as_text(name)
    for node in list(rt.objects):
        try:
            if _as_text(node.name) == name:
                return node
        except Exception:
            pass
    return None


def _normalize_name_for_auto_map(name):
    text = _as_text(name).lower()
    return re.sub(r"\s+", "", text)


def _resolve_name(name, mapping, new_names=None):
    source = _as_text(name)
    if source in (mapping or {}):
        return _as_text((mapping or {}).get(source)), "explicit"
    if new_names is not None:
        if source in new_names:
            return source, "same_name"
        normalized = _normalize_name_for_auto_map(source)
        matches = [x for x in new_names if _normalize_name_for_auto_map(x) == normalized]
        if len(matches) == 1:
            return matches[0], "auto_whitespace"
    return source, "unmapped"


def _resolve_node_target(rt, node, mapping, target_inventory):
    source = _node_name(node)
    metadata = _reference_rig_metadata(rt, node)
    guid = metadata.get("rrGuid", "")
    if guid:
        guid_matches = (target_inventory.get("guid_to_names", {}) or {}).get(guid, []) or []
        if len(guid_matches) == 1:
            return guid_matches[0], "rrGuid", metadata
        if len(guid_matches) > 1:
            return u"", "ambiguous_rrGuid", metadata
    auto_layer_mapping = target_inventory.get("auto_layer_mapping", {}) or {}
    if source in auto_layer_mapping:
        return _as_text(auto_layer_mapping.get(source)), "auto_layer", metadata
    target_name, method = _resolve_name(source, mapping, target_inventory.get("names", set()))
    return target_name, method, metadata


def _mapped_name(name, mapping, new_names=None):
    return _resolve_name(name, mapping, new_names)[0]


def _get_max_file_names(rt, file_path):
    names = []
    try:
        with SilentFileDialogs(rt):
            raw = rt.getMAXFileObjectNames(file_path)
        for i in range(1, int(raw.count) + 1):
            names.append(_as_text(raw[i]))
    except Exception:
        try:
            with SilentFileDialogs(rt):
                raw = rt.getMAXFileObjectNames(file_path)
            names = [_as_text(x) for x in raw]
        except Exception:
            names = []
    return set([x for x in names if x])


def _scan_source_scene_objects(rt, mapping, new_names):
    rows = []
    seen = set()
    for node in list(rt.objects):
        name = _node_name(node)
        if (not name) or name in seen:
            continue
        seen.add(name)
        target_name, mapping_method = _resolve_name(name, mapping, new_names)
        rows.append({
            "source_name": name,
            "target_name": target_name,
            "mapping_method": mapping_method,
            "target_exists": target_name in new_names,
            "class_name": _class_name(rt, node),
            "is_bip": _is_bip_node(rt, node),
        })
    return rows


def _animation_range(rt):
    try:
        return {
            "start": int(rt.animationRange.start),
            "end": int(rt.animationRange.end),
            "current": int(rt.sliderTime),
        }
    except Exception:
        return {"start": 0, "end": 0, "current": 0}


def _sample_frames(anim_range):
    start = int(anim_range.get("start", 0))
    end = int(anim_range.get("end", start))
    mid = start + int((end - start) / 2)
    return sorted(set([start, mid, end]))


def _detect_bip_root(rt):
    node = _node_by_name(rt, "Bip001")
    if node is not None:
        return node
    for item in list(rt.objects):
        if _is_bip_node(rt, item):
            try:
                if item.parent is None:
                    return item
            except Exception:
                return item
    return None


def _has_any_keys(rt, node):
    try:
        return bool(_key_times(rt, node))
    except Exception:
        return False


def _is_camera_like(rt, node):
    name = _node_name(node).lower()
    cls = _class_name(rt, node).lower()
    try:
        super_cls = _as_text(rt.superClassOf(node)).lower()
    except Exception:
        super_cls = u""
    return ("camera" in cls) or ("camera" in super_cls) or ("camera" in name) or ("cam" in name)


def _walk_descendants(node):
    out = []
    stack = []
    try:
        stack = list(node.children)
    except Exception:
        stack = []
    while stack:
        child = stack.pop(0)
        out.append(child)
        try:
            stack.extend(list(child.children))
        except Exception:
            pass
    return out


def _walk_parents(node):
    out = []
    cur = node
    while cur is not None:
        try:
            cur = cur.parent
        except Exception:
            cur = None
        if cur is not None:
            out.append(cur)
    return out


def _add_unique_node(nodes, node):
    if node is None:
        return
    try:
        if node not in nodes:
            nodes.append(node)
    except Exception:
        nodes.append(node)


def _scan_merge_helper_objects(rt, new_names):
    new_names = set(new_names or [])
    allowed = {}
    for node in list(rt.objects):
        name = _node_name(node)
        if not name:
            continue
        reasons = []
        if name.startswith(u"Ref_"):
            reasons.append("ref_prefix")
        if _is_camera_like(rt, node):
            reasons.append("camera")
            camera_related = []
            camera_constraint_targets = []
            camera_parent_nodes = _walk_parents(node)
            camera_descendants = _walk_descendants(node)
            for related in camera_parent_nodes + camera_descendants:
                _add_unique_node(camera_related, related)
            # Camera rigs often keep animation/controllers on the top rig root
            # while actual camera nodes live deeper in the hierarchy.
            # Merge the full subtree below camera parents so roots such as
            # Global_Rig_Root do not arrive without their sibling helpers.
            for parent_node in camera_parent_nodes:
                for related in _walk_descendants(parent_node):
                    _add_unique_node(camera_related, related)
            for owner in [node] + camera_related:
                for ctrl in _iter_candidate_controllers(rt, owner):
                    try:
                        for i in range(1, _get_target_count(ctrl) + 1):
                            target = _get_target(ctrl, i)
                            if target is not None:
                                _add_unique_node(camera_constraint_targets, target)
                                _add_unique_node(camera_related, target)
                    except Exception:
                        pass
            for related in camera_related:
                related_name = _node_name(related)
                if related_name:
                    row = allowed.setdefault(related_name, {"name": related_name, "reasons": [], "has_keys": _has_any_keys(rt, related), "exists_in_new": related_name in new_names})
                    if related in camera_constraint_targets and related not in camera_parent_nodes + camera_descendants:
                        reason = "camera_constraint_target"
                    elif related not in camera_parent_nodes + camera_descendants:
                        reason = "camera_parent_hierarchy"
                    else:
                        reason = "camera_hierarchy"
                    if reason not in row["reasons"]:
                        row["reasons"].append(reason)
        if reasons:
            row = allowed.setdefault(name, {"name": name, "reasons": [], "has_keys": _has_any_keys(rt, node), "exists_in_new": name in new_names})
            for reason in reasons:
                if reason not in row["reasons"]:
                    row["reasons"].append(reason)
    rows = []
    for name in sorted(allowed.keys(), key=lambda x: x.lower()):
        row = allowed[name]
        if row.get("exists_in_new"):
            row["merge_status"] = "skipped_exists_in_new"
        else:
            row["merge_status"] = "pending"
        rows.append(row)
    return {"objects": rows}


def _sample_node_z(rt, node, frames):
    samples = []
    for frame in frames:
        try:
            rt.sliderTime = int(frame)
            tm = node.transform
            samples.append({"frame": int(frame), "world_z": float(tm.row4.z)})
        except Exception as e:
            samples.append({"frame": int(frame), "error": _as_text(e)})
    return samples


def _controller_for_channel(rt, node, channel):
    try:
        if channel == "transform":
            return node.controller
        return rt.getPropertyController(node, channel)
    except Exception:
        return None


def _constraint_channel(rt, owner, controller):
    try:
        if owner.controller == controller:
            return "transform"
    except Exception:
        pass
    for channel in ("position", "rotation"):
        try:
            if _controller_for_channel(rt, owner, channel) == controller:
                return channel
        except Exception:
            pass
    return "unknown"


def _iter_constraint_controllers(rt, node):
    controllers = []
    try:
        if node.controller is not None:
            controllers.append(node.controller)
    except Exception:
        pass
    for channel in ("position", "rotation"):
        ctrl = _controller_for_channel(rt, node, channel)
        if ctrl is not None:
            controllers.append(ctrl)
    return controllers


def _constraint_target_count(controller):
    try:
        return int(controller.getNumTargets())
    except Exception:
        return 0


def _constraint_target(controller, index):
    try:
        return controller.getNode(index)
    except Exception:
        pass
    try:
        return controller.getTarget(index)
    except Exception:
        return None


def _constraint_weight(controller, index):
    try:
        return float(controller.getWeight(index))
    except Exception:
        return 100.0


def _constraint_frame(controller, index):
    try:
        return int(controller.getFrameNo(index))
    except Exception:
        return int(index)


def _key_times(rt, node):
    out = []
    for ctrl in _node_transform_controllers(rt, node):
        out.extend(_collect_key_times(rt, ctrl))
    return sorted(set([int(x) for x in out]))


def _channel_key_counts(rt, node):
    out = {}
    for channel in ("position", "rotation", "scale", "visibility", "transform"):
        ctrl = _safe_controller(node, channel, rt)
        times = _collect_key_times(rt, ctrl) if ctrl is not None else []
        out[channel] = len(sorted(set([int(x) for x in times])))
    return out


def _controller_profile(rt, node):
    profile = {}
    for channel in ("transform", "position", "rotation", "scale", "visibility"):
        ctrl = _safe_controller(node, channel, rt)
        if ctrl is None and channel == "transform":
            try:
                ctrl = node.controller
            except Exception:
                ctrl = None
        profile[channel] = _class_name(rt, ctrl) if ctrl is not None else u""
        if channel in ("position", "rotation", "scale") and not profile[channel]:
            profile[channel] = _controller_class_from_prs_subcontroller(rt, node, channel)
    return profile


def _controller_class_from_prs_subcontroller(rt, node, channel):
    name = _node_name(node)
    if not name:
        return u""
    script = u'''(
        local n = getNodeByName "{0}"
        if n == undefined then "" else
        (
            local c = undefined
            try(c = n.{1}.controller)catch()
            if c == undefined do try(c = n.controller.{1}.controller)catch()
            if c == undefined do try(c = getPropertyController n #{1})catch()
            if c == undefined then "" else ((classof c) as string)
        )
    )'''.format(_mxs_escape(name), channel)
    try:
        return _as_text(rt.execute(script))
    except Exception:
        return u""


def _scan_ik_rows(rt, mapping, new_names, animated_names):
    rows = []
    for node in list(rt.objects):
        name = _node_name(node)
        if not name:
            continue
        low = name.lower()
        if not any(token in low for token in ("ik", "knee", "elbow", "ankle", "wrist")):
            continue
        target_name, mapping_method = _resolve_name(name, mapping, new_names)
        rows.append({
            "source_name": name,
            "target_name": target_name,
            "mapping_method": mapping_method,
            "target_exists": target_name in new_names,
            "has_animation": name in animated_names,
            "status": "matched" if target_name in new_names else "skipped_missing_object",
        })
    return rows


def _scan_constraints(rt, mapping, new_names, animated_names):
    rows = []
    for node in list(rt.objects):
        if _is_bip_node(rt, node):
            continue
        owner_name = _node_name(node)
        if not owner_name:
            continue
        owner_target_name, owner_mapping_method = _resolve_name(owner_name, mapping, new_names)
        has_keys = owner_name in animated_names
        should_rebuild_owner = _is_animator_constraint_candidate(rt, node, has_keys)
        for ctrl in _iter_constraint_controllers(rt, node):
            cls = _class_name(rt, ctrl)
            if cls not in SUPPORTED_CONSTRAINTS:
                continue
            targets = []
            missing_targets = []
            for i in range(1, _constraint_target_count(ctrl) + 1):
                target_node = _constraint_target(ctrl, i)
                is_world_target = (cls == "Link_Constraint" and target_node is None)
                source_target = u"World" if is_world_target else (_node_name(target_node) if target_node is not None else u"")
                mapped_target, target_mapping_method = _resolve_name(source_target, mapping, new_names)
                if is_world_target:
                    mapped_target = u"World"
                    target_mapping_method = "world"
                if (not is_world_target) and ((not mapped_target) or mapped_target not in new_names):
                    missing_targets.append(mapped_target or source_target or "<missing>")
                targets.append({
                    "index": i,
                    "source_name": source_target,
                    "target_name": mapped_target,
                    "mapping_method": target_mapping_method,
                    "target_exists": True if is_world_target else (mapped_target in new_names),
                    "target_type": "world" if is_world_target else "node",
                    "is_world": bool(is_world_target),
                    "weight": _constraint_weight(ctrl, i),
                    "frame": _constraint_frame(ctrl, i) if cls == "Link_Constraint" else None,
                })
            if owner_target_name not in new_names:
                status = "skipped_missing_owner"
            elif not should_rebuild_owner:
                status = "preserved_binding_internal"
            elif missing_targets:
                status = "skipped_missing_target"
            else:
                status = "ready"
            rows.append({
                "owner_source_name": owner_name,
                "owner_target_name": owner_target_name,
                "owner_mapping_method": owner_mapping_method,
                "owner_target_exists": owner_target_name in new_names,
                "owner_has_animation": has_keys,
                "reference_rig_metadata": _reference_rig_metadata(rt, node),
                "constraint_type": cls,
                "channel": _constraint_channel(rt, node, ctrl),
                "targets": targets,
                "missing_targets": missing_targets,
                "status": status,
                "should_rebuild": status == "ready",
            })
    return rows


def _xaf_path_for_source(xaf_dir, source_name):
    text = _as_text(source_name)
    try:
        raw = text.encode("utf-8")
    except Exception:
        raw = _as_text(text).encode("utf-8", "replace")
    digest = hashlib.md5(raw).hexdigest()[:12]
    ascii_prefix = re.sub(r"[^A-Za-z0-9_]+", "_", text.encode("ascii", "ignore").decode("ascii"))
    ascii_prefix = ascii_prefix.strip("_")[:40] or "node"
    return os.path.join(xaf_dir, "{0}_{1}.xaf".format(ascii_prefix, digest))


def _apply_xaf_row_result(row, ok, xaf_path, message, export_mode):
    row["xaf_export_status"] = "succeeded" if ok else "failed"
    row["xaf_path"] = xaf_path if ok else None
    row["xaf_export_mode"] = export_mode
    row["message"] = _as_text(message) if not ok else u""


def _export_xaf_chunked_fallback(rt, batch_nodes, batch_sources, rows, xaf_dir, package_dir=None):
    """Export XAF in small chunks; per-node fallback when a chunk fails."""
    row_by_source = dict([(_as_text(r.get("source_name", "")), r) for r in rows])
    pairs = list(zip(batch_sources, batch_nodes))
    chunks_meta = []
    succeeded = 0
    failed = 0

    if package_dir:
        _write_stage_status(
            package_dir,
            "export_xaf_chunked",
            u"nodes={0} chunk_size={1}".format(len(pairs), XAF_CHUNK_EXPORT_SIZE),
        )

    for chunk_index in range(0, len(pairs), XAF_CHUNK_EXPORT_SIZE):
        chunk_pairs = pairs[chunk_index:chunk_index + XAF_CHUNK_EXPORT_SIZE]
        chunk_sources = [p[0] for p in chunk_pairs]
        chunk_nodes = [p[1] for p in chunk_pairs]
        chunk_no = (chunk_index // XAF_CHUNK_EXPORT_SIZE) + 1
        chunk_path = os.path.join(xaf_dir, "chunk_{0:04d}.xaf".format(chunk_no))
        ok, msg = _try_save_xaf_nodes(rt, chunk_nodes, chunk_path)
        chunk_info = {
            "index": chunk_no,
            "xaf_path": chunk_path,
            "source_names": chunk_sources,
            "count": len(chunk_sources),
            "status": "succeeded" if ok else "failed",
            "message": msg if not ok else u"",
            "export_mode": "chunk",
        }
        if ok:
            chunks_meta.append(chunk_info)
            for source_name in chunk_sources:
                row = row_by_source.get(source_name)
                if row is not None:
                    _apply_xaf_row_result(row, True, chunk_path, u"", "chunk")
                    succeeded += 1
            continue

        chunk_info["export_mode"] = "chunk_failed_per_node"
        chunks_meta.append(chunk_info)
        for source_name, node in chunk_pairs:
            node_path = _xaf_path_for_source(xaf_dir, source_name)
            ok_one, msg_one = _try_save_xaf(rt, node, node_path)
            row = row_by_source.get(source_name)
            if row is None:
                continue
            _apply_xaf_row_result(row, ok_one, node_path if ok_one else None, msg_one, "single")
            if ok_one:
                succeeded += 1
            else:
                failed += 1

    if failed == 0 and succeeded == len(pairs):
        status = "succeeded"
    elif succeeded > 0:
        status = "partial"
    else:
        status = "failed"

    return {
        "status": status,
        "message": u"分块/逐对象导出：成功 {0}，失败 {1}".format(succeeded, failed),
        "export_strategy": "chunked",
        "chunk_size": XAF_CHUNK_EXPORT_SIZE,
        "chunks": chunks_meta,
        "succeeded_count": succeeded,
        "failed_count": failed,
    }


def _finalize_batch_xaf_export(rt, batch_nodes, batch_sources, rows, xaf_dir, package_dir=None):
    batch_xaf_path = os.path.join(xaf_dir, "non_bip_batch.xaf")
    count = len(batch_sources)
    batch = {
        "xaf_path": batch_xaf_path,
        "source_names": batch_sources,
        "count": count,
        "status": "skipped",
        "message": u"",
        "export_strategy": "none",
        "threshold": XAF_BATCH_DIRECT_THRESHOLD,
        "chunk_size": XAF_CHUNK_EXPORT_SIZE,
        "chunks": [],
        "batch_attempt": None,
    }
    if not batch_nodes:
        return rows, batch

    row_by_source = set(batch_sources)
    use_batch_first = count < XAF_BATCH_DIRECT_THRESHOLD
    batch_ok = False
    batch_msg = u""

    if use_batch_first:
        if package_dir:
            _write_stage_status(package_dir, "export_xaf_batch", u"nodes={0} mode=batch".format(count))
        batch_ok, batch_msg = _try_save_xaf_nodes(rt, batch_nodes, batch_xaf_path)
        batch["export_strategy"] = "batch"
        batch["batch_attempt"] = {"ok": batch_ok, "message": batch_msg}
        if batch_ok:
            batch["status"] = "succeeded"
            batch["message"] = u""
            for row in rows:
                if row.get("source_name") in row_by_source:
                    _apply_xaf_row_result(row, True, batch_xaf_path, u"", "batch")
            return rows, batch

    if count >= XAF_BATCH_DIRECT_THRESHOLD:
        batch["export_strategy"] = "chunked_direct"
        batch["batch_skipped"] = True
        batch["message"] = u"对象数 {0} >= {1}，跳过批量导出".format(count, XAF_BATCH_DIRECT_THRESHOLD)
    elif not batch_ok:
        batch["export_strategy"] = "batch_then_chunked"
        batch["message"] = batch_msg

    chunked = _export_xaf_chunked_fallback(rt, batch_nodes, batch_sources, rows, xaf_dir, package_dir=package_dir)
    batch["status"] = chunked.get("status", "failed")
    batch["message"] = chunked.get("message", batch.get("message", u""))
    batch["export_strategy"] = chunked.get("export_strategy", batch.get("export_strategy", "chunked"))
    batch["chunks"] = chunked.get("chunks", [])
    batch["succeeded_count"] = chunked.get("succeeded_count", 0)
    batch["failed_count"] = chunked.get("failed_count", 0)
    if batch["status"] == "succeeded":
        batch["xaf_path"] = batch_xaf_path if use_batch_first and batch_ok else None
    return rows, batch


def _has_nonzero_key_time(track):
    return any([int(value) != 0 for value in (track.get("key_times", []) or [])])


def _ignore_missing_morpher_for_target(target_inventory):
    # Only the exact ADV pelvis marker opts into the legacy-Morpher exception.
    # Generic and other similarly named/non-ADV rigs keep the hard blocker.
    return bool((target_inventory or {}).get("has_adv_pelvis_marker"))


def _is_morph_signature(track):
    return (
        track.get("root_kind") == "modifier" and
        "morph" in _as_text(track.get("root_class", "")).lower()
    )


def _preflight_override_policy(bip_ok, blockers, allow_preflight_blockers):
    blockers = blockers or []
    hard_blockers = [item for item in blockers if item.get("reason") == "xaf_export_failed"]
    continued_blockers = blockers if allow_preflight_blockers and not hard_blockers else []
    ok = bool(bip_ok) and (not blockers or bool(continued_blockers))
    return {
        "ok": ok,
        "hard_blockers": hard_blockers,
        "continued_blockers": continued_blockers,
    }


def _scan_non_bip_animation(rt, mapping, target_inventory, xaf_dir, allowed_missing_names=None, package_dir=None):
    rows = []
    animated_names = set()
    batch_nodes = []
    batch_sources = []
    blockers = []
    warnings = []
    morph_objects = []
    ignored_frame0_only_nodes = 0
    ignored_frame0_only_tracks = 0
    target_name_counts = target_inventory.get("name_counts", {}) or {}
    target_morph_paths = target_inventory.get("morph_paths", {}) or {}
    source_name_counts = _scene_name_counts(rt)
    allowed_missing_names = set(allowed_missing_names or [])
    seen = set()
    scan_entries = []
    batch_xaf_path = os.path.join(xaf_dir, "non_bip_batch.xaf")
    for node in list(rt.objects):
        if _is_bip_node(rt, node):
            continue
        name = _node_name(node)
        if not name or name in seen:
            continue
        seen.add(name)
        all_tracks = collect_node_track_signatures(
            rt,
            node,
            include_samples=False,
            include_unkeyed=False,
            include_controllers=True,
        )
        if not all_tracks:
            continue
        tracks = [track for track in all_tracks if _has_nonzero_key_time(track)]
        ignored_frame0_only_tracks += len(all_tracks) - len(tracks)
        if not tracks:
            ignored_frame0_only_nodes += 1
            continue

        scan_entries.append((node, name, tracks))

    sampling = sample_track_signature_groups(rt, [entry[2] for entry in scan_entries])
    for node, name, tracks in scan_entries:

        track_signatures = json_track_signatures(tracks)
        class_name = _class_name(rt, node)
        target_name, mapping_method, metadata = _resolve_node_target(rt, node, mapping, target_inventory)
        target_exists = bool(target_name) and target_name_counts.get(target_name, 0) == 1
        node_blockers = []
        node_warnings = []
        if source_name_counts.get(name, 0) != 1:
            node_blockers.append({"reason": "ambiguous_source_name", "count": source_name_counts.get(name, 0)})
        if mapping_method == "ambiguous_rrGuid":
            node_blockers.append({"reason": "ambiguous_target_rrGuid", "rrGuid": metadata.get("rrGuid", "")})
        if target_name and target_name_counts.get(target_name, 0) > 1:
            node_blockers.append({"reason": "ambiguous_target_name", "count": target_name_counts.get(target_name, 0)})
        for extra in unsupported_extra_tracks(track_signatures):
            node_blockers.append({"reason": extra.get("reason"), "path": extra.get("path", "")})

        if any([_is_morph_signature(item) for item in tracks]):
            with suspended_scene_redraw(rt):
                morph_payload = build_morph_payload(rt, node, tracks=tracks)
        else:
            morph_payload = {"source_name": name, "channels": []}
        morph_channels = morph_payload.get("channels", []) or []
        expected_signatures = prepare_morph_signatures(track_signatures, morph_channels)
        if morph_channels:
            target_paths = set(target_morph_paths.get(target_name, []) or [])
            missing_morph_paths = [
                item.get("path", "") for item in morph_channels
                if item.get("path", "") not in target_paths
            ]
            if missing_morph_paths:
                if _ignore_missing_morpher_for_target(target_inventory):
                    missing_path_set = set(missing_morph_paths)
                    morph_channels = [item for item in morph_channels if item.get("path", "") not in missing_path_set]
                    expected_signatures = [item for item in expected_signatures if item.get("path", "") not in missing_path_set]
                    morph_payload["channels"] = morph_channels
                    node_warnings.append({
                        "reason": "ignored_obsolete_morpher",
                        "paths": missing_morph_paths,
                        "message": u"目标绑定使用精确 ADV 骨盆标记；源文件中目标不存在的旧 Morpher 通道已按过时设计忽略",
                    })
                    if any([not _is_morph_signature(item) for item in expected_signatures]):
                        node_blockers.append({
                            "reason": "obsolete_morpher_mixed_with_transfer_tracks",
                            "paths": missing_morph_paths,
                            "message": u"同一对象还包含其他动画轨道，XAF 无法证明会排除旧 Morpher；为避免暗中导入已忽略通道，已阻止迁移",
                        })
                else:
                    node_blockers.append({
                        "reason": "unsupported_face_rig_conversion",
                        "paths": missing_morph_paths,
                        "message": u"源 Morpher 通道在目标绑定中不存在；非 ADV 目标禁止猜测表情语义映射",
                    })
            morph_payload["target_name"] = target_name
            if morph_payload.get("channels"):
                morph_objects.append(morph_payload)

        keys = sorted(set([
            int(time_value)
            for track in expected_signatures
            for time_value in (track.get("key_times", []) or [])
        ]))
        channel_counts = aggregate_track_counts(expected_signatures)
        ignored_obsolete_only = bool(node_warnings) and not expected_signatures
        morph_bake_only = bool(expected_signatures) and all([_is_morph_signature(item) for item in expected_signatures])
        if expected_signatures:
            animated_names.add(name)
        if (not target_exists) and name not in allowed_missing_names:
            node_blockers.append({"reason": "missing_target_node", "target_name": target_name})
        if ignored_obsolete_only:
            node_blockers = []
        for blocker in node_blockers:
            blocker.update({"source_name": name, "target_name": target_name})
            blockers.append(blocker)
        for warning in node_warnings:
            warning.update({"source_name": name, "target_name": target_name})
            warnings.append(warning)
        deferred_merge = (not target_exists) and name in allowed_missing_names and not node_blockers
        ready_for_xaf = target_exists and not node_blockers and not ignored_obsolete_only and not morph_bake_only
        row = {
            "source_name": name,
            "target_name": target_name,
            "mapping_method": mapping_method,
            "target_exists": target_exists,
            "class_name": class_name,
            "key_times": keys,
            "key_count": len(keys),
            "channel_key_counts": channel_counts,
            "track_signatures": expected_signatures,
            "track_count": len(expected_signatures),
            "reference_rig_metadata": metadata,
            "blockers": node_blockers,
            "warnings": node_warnings,
            "controller_profile": _controller_profile(rt, node),
            "xaf_path": batch_xaf_path if ready_for_xaf else None,
            "xaf_export_status": (
                "ignored_obsolete_tracks" if ignored_obsolete_only else
                ("morph_bake_only" if morph_bake_only and target_exists and not node_blockers else
                ("pending" if ready_for_xaf else
                 ("deferred_merge_source_object" if deferred_merge else "blocked_preflight")))
            ),
            "message": u"",
        }
        if ready_for_xaf:
            batch_nodes.append(node)
            batch_sources.append(name)
        rows.append(row)

    rows, batch = _finalize_batch_xaf_export(
        rt,
        batch_nodes,
        batch_sources,
        rows,
        xaf_dir,
        package_dir=package_dir,
    )
    return rows, animated_names, batch, {"objects": morph_objects}, blockers, warnings, {
        "ignored_frame0_only_node_count": ignored_frame0_only_nodes,
        "ignored_frame0_only_track_count": ignored_frame0_only_tracks,
        "sampling": sampling,
    }


def export_old_migration_package(
    old_anim_path,
    new_rig_path,
    output_max_path,
    mapping=None,
    package_root=None,
    allow_preflight_blockers=False,
):
    import pymxs

    rt = pymxs.runtime
    export_started = time.time()
    timings = {}
    old_anim_path = os.path.abspath(_as_text(old_anim_path))
    new_rig_path = os.path.abspath(_as_text(new_rig_path))
    output_max_path = os.path.abspath(_as_text(output_max_path)) if output_max_path else u""
    mapping = mapping or {}
    if package_root is None:
        package_root = os.path.join(os.path.dirname(old_anim_path), "_RigUpdatePackages")
    package_dir = os.path.join(package_root, "{0}.migration_{1}".format(_safe_filename(os.path.splitext(os.path.basename(old_anim_path))[0]), _timestamp()))
    bip_dir = os.path.join(package_dir, "bip")
    xaf_dir = os.path.join(package_dir, "xaf")
    for folder in (package_dir, bip_dir, xaf_dir):
        if not os.path.exists(folder):
            os.makedirs(folder)

    _write_stage_status(package_dir, "read_new_rig_names", new_rig_path)
    restore = _as_text(rt.maxFilePath) + _as_text(rt.maxFileName)
    restore = restore if restore and os.path.exists(restore) else None
    _write_stage_status(package_dir, "load_new_rig_inventory", new_rig_path)
    stage_started = time.time()
    target_inventory = _target_rig_inventory(rt, new_rig_path)
    timings["load_target_inventory"] = round(time.time() - stage_started, 3)
    new_names = target_inventory.get("names", set())
    try:
        _write_stage_status(package_dir, "load_old_anim", old_anim_path)
        stage_started = time.time()
        with SilentFileDialogs(rt):
            rt.loadMaxFile(old_anim_path, quiet=True, useFileUnits=True)
        timings["load_source_animation"] = round(time.time() - stage_started, 3)
        source_binding_metadata = read_scene_binding_metadata(rt)
        if not source_binding_metadata.get("version"):
            source_binding_metadata["version"] = _binding_version_from_path(source_binding_metadata.get("rig_path", ""))
        source_layer_inventory = scene_layer_inventory(rt)
        layer_mapping = build_layer_mapping(
            source_layer_inventory,
            target_inventory.get("layer_inventory", {}),
            explicit_mapping=mapping,
        )
        layer_mapping["meta"] = {
            "source_animation": old_anim_path,
            "source_binding_version": source_binding_metadata.get("version", ""),
            "source_binding_rig_path": source_binding_metadata.get("rig_path", ""),
            "target_binding_path": new_rig_path,
            "target_binding_version": _binding_version_from_path(new_rig_path),
            "rule": "unique_same_layer_high_confidence",
        }
        effective_mapping = dict(mapping)
        effective_mapping.update(layer_mapping.get("objects", {}) or {})
        mapping = effective_mapping
        target_inventory["auto_layer_mapping"] = layer_mapping.get("objects", {}) or {}
        _write_stage_status(package_dir, "export_bip", old_anim_path)
        stage_started = time.time()
        anim_range = _animation_range(rt)
        bip_root = _detect_bip_root(rt)
        frames = _sample_frames(anim_range)
        bip_path = os.path.join(bip_dir, "Bip001.bip")
        bip_export = {"ok": False, "path": bip_path, "message": u""}
        com_height = {"bip_root": _node_name(bip_root), "animation_range": anim_range, "samples": []}
        if bip_root is not None:
            com_height["samples"] = _sample_node_z(rt, bip_root, frames)
            try:
                ok = bool(rt.biped.saveBipFile(bip_root.controller, bip_path))
                bip_export["ok"] = ok and os.path.exists(bip_path)
                bip_export["message"] = u"BIP 导出成功" if bip_export["ok"] else u"BIP 导出返回失败"
            except Exception as e:
                bip_export["message"] = _as_text(e)
        else:
            bip_export["message"] = u"未找到 BIP 根"

        timings["export_bip"] = round(time.time() - stage_started, 3)
        _write_stage_status(package_dir, "scan_merge_helpers", old_anim_path)
        stage_started = time.time()
        merge_helpers = _scan_merge_helper_objects(rt, new_names)
        timings["scan_merge_helpers"] = round(time.time() - stage_started, 3)
        allowed_missing_names = set([
            row.get("name", "") for row in (merge_helpers.get("objects", []) or [])
            if row.get("merge_status") == "pending"
        ])
        _write_stage_status(package_dir, "scan_non_bip_animation", old_anim_path)
        stage_started = time.time()
        non_bip_rows, animated_names, non_bip_batch, morph_animation, blockers, warnings, scan_summary = _scan_non_bip_animation(
            rt,
            mapping,
            target_inventory,
            xaf_dir,
            allowed_missing_names=allowed_missing_names,
            package_dir=package_dir,
        )
        timings["scan_and_export_non_bip"] = round(time.time() - stage_started, 3)
        for row in non_bip_rows:
            if row.get("xaf_export_status") == "failed":
                blockers.append({
                    "reason": "xaf_export_failed",
                    "source_name": row.get("source_name", ""),
                    "target_name": row.get("target_name", ""),
                    "message": row.get("message", ""),
                })
        _write_stage_status(package_dir, "scan_constraints", old_anim_path)
        stage_started = time.time()
        constraints = _scan_constraints(rt, mapping, new_names, animated_names)
        source_scene_objects = _scan_source_scene_objects(rt, mapping, new_names)
        ik_rows = _scan_ik_rows(rt, mapping, new_names, animated_names)
        timings["scan_constraints_and_ik"] = round(time.time() - stage_started, 3)

        paths = {
            "package_dir": package_dir,
            "bip_path": bip_path,
            "com_height_json": os.path.join(bip_dir, "com_height.json"),
            "bip_ik_json": os.path.join(package_dir, "bip_ik.json"),
            "constraints_json": os.path.join(package_dir, "constraints.json"),
            "non_bip_animation_json": os.path.join(package_dir, "non_bip_animation.json"),
            "morph_animation_json": os.path.join(package_dir, "morph_animation.json"),
            "layer_mapping_json": os.path.join(package_dir, "layer_mapping.json"),
            "merge_helpers_json": os.path.join(package_dir, "merge_helpers.json"),
            "manifest_json": os.path.join(package_dir, "manifest.json"),
        }
        stage_started = time.time()
        _json_write(paths["com_height_json"], com_height)
        _json_write(paths["bip_ik_json"], {"objects": ik_rows})
        _json_write(paths["constraints_json"], {
            "constraints": constraints,
            "source_scene_objects": source_scene_objects,
        })
        _json_write(paths["non_bip_animation_json"], {"objects": non_bip_rows, "batch_xaf": non_bip_batch})
        _json_write(paths["morph_animation_json"], morph_animation)
        _json_write(paths["layer_mapping_json"], layer_mapping)
        _json_write(paths["merge_helpers_json"], merge_helpers)
        timings["write_package_payloads"] = round(time.time() - stage_started, 3)
        timings["elapsed_before_manifest_write"] = round(time.time() - export_started, 3)
        override_policy = _preflight_override_policy(
            bip_export.get("ok"),
            blockers,
            allow_preflight_blockers,
        )
        hard_blockers = override_policy.get("hard_blockers", [])
        continued_blockers = override_policy.get("continued_blockers", [])
        manifest_ok = bool(override_policy.get("ok"))
        if continued_blockers:
            manifest_message = u"迁移预检发现 {0} 个问题；已按用户选择跳过对应非 BIP 对象并继续".format(len(continued_blockers))
        elif blockers:
            manifest_message = u"迁移预检发现 {0} 个会导致动画丢失或错绑的问题，已停止且未写入目标文件".format(len(blockers))
        else:
            manifest_message = u""
        manifest = {
            "ok": manifest_ok,
            "error_code": None if manifest_ok else ("PKG-BIP-EXPORT" if not bip_export.get("ok") else "PKG-PREFLIGHT-BLOCKED"),
            "message": manifest_message,
            "blockers": blockers,
            "continued_blockers": continued_blockers,
            "warnings": warnings,
            "package_dir": package_dir,
            "input": {
                "old_anim_path": old_anim_path,
                "new_rig_path": new_rig_path,
                "output_max_path": output_max_path,
            },
            "animation_range": anim_range,
            "bip": bip_export,
            "options": {
                "allow_preflight_blockers": bool(allow_preflight_blockers),
            },
            "paths": paths,
            "timings_seconds": timings,
            "summary": {
                "non_bip_animated_count": len(non_bip_rows),
                "track_count": sum([int(x.get("track_count", 0)) for x in non_bip_rows]),
                "morph_channel_count": sum([len(x.get("channels", []) or []) for x in morph_animation.get("objects", []) or []]),
                "preflight_blocker_count": len(blockers),
                "continued_preflight_blocker_count": len(continued_blockers),
                "hard_preflight_blocker_count": len(hard_blockers),
                "preflight_warning_count": len(warnings),
                "ignored_obsolete_morpher_count": len([x for x in warnings if x.get("reason") == "ignored_obsolete_morpher"]),
                "ignored_frame0_only_node_count": scan_summary.get("ignored_frame0_only_node_count", 0),
                "ignored_frame0_only_track_count": scan_summary.get("ignored_frame0_only_track_count", 0),
                "non_bip_sampling": scan_summary.get("sampling", {}),
                "layer_mapping_accepted_count": (layer_mapping.get("summary", {}) or {}).get("accepted_count", 0),
                "layer_mapping_ambiguous_count": (layer_mapping.get("summary", {}) or {}).get("ambiguous_count", 0),
                "layer_mapping_hierarchy_parent_count": (layer_mapping.get("summary", {}) or {}).get("hierarchy_parent_count", 0),
                "layer_mapping_insufficient_hierarchy_count": (layer_mapping.get("summary", {}) or {}).get("insufficient_hierarchy_count", 0),
                "source_binding_version": source_binding_metadata.get("version", ""),
                "target_binding_version": _binding_version_from_path(new_rig_path),
                "target_has_adv_pelvis_marker": bool(target_inventory.get("has_adv_pelvis_marker")),
                "xaf_export_strategy": non_bip_batch.get("export_strategy", ""),
                "xaf_batch_threshold": XAF_BATCH_DIRECT_THRESHOLD,
                "xaf_chunk_size": XAF_CHUNK_EXPORT_SIZE,
                "xaf_export_succeeded": len([x for x in non_bip_rows if x.get("xaf_export_status") == "succeeded"]),
                "xaf_export_failed": len([x for x in non_bip_rows if x.get("xaf_export_status") == "failed"]),
                "constraint_count": len(constraints),
                "source_scene_object_count": len(source_scene_objects),
                "constraint_ready_count": len([x for x in constraints if x.get("should_rebuild")]),
                "constraint_skipped_missing_owner": len([x for x in constraints if x.get("status") == "skipped_missing_owner"]),
                "constraint_skipped_missing_target": len([x for x in constraints if x.get("status") == "skipped_missing_target"]),
                "constraint_preserved_binding_internal": len([x for x in constraints if x.get("status") == "preserved_binding_internal"]),
                "mapping_explicit_count": len([x for x in non_bip_rows if x.get("mapping_method") == "explicit"]) + len([x for x in constraints if x.get("owner_mapping_method") == "explicit"]),
                "mapping_auto_whitespace_count": len([x for x in non_bip_rows if x.get("mapping_method") == "auto_whitespace"]) + len([x for x in constraints if x.get("owner_mapping_method") == "auto_whitespace"]),
                "mapping_auto_layer_count": len([x for x in non_bip_rows if x.get("mapping_method") == "auto_layer"]),
                "ik_object_count": len(ik_rows),
                "merge_helper_count": len(merge_helpers.get("objects", []) or []),
                "merge_helper_pending_count": len([x for x in merge_helpers.get("objects", []) or [] if x.get("merge_status") == "pending"]),
            },
        }
        _json_write(paths["manifest_json"], manifest)
        _write_stage_status(package_dir, "export_done", old_anim_path)
        return manifest
    except Exception as e:
        return {"ok": False, "error_code": "PKG-EXPORT-001", "message": _as_text(e), "package_dir": package_dir}
    finally:
        try:
            if restore and os.path.abspath(restore) != old_anim_path:
                with SilentFileDialogs(rt):
                    rt.loadMaxFile(restore, quiet=True, useFileUnits=True)
        except Exception:
            pass

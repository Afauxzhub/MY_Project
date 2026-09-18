# -*- coding: utf-8 -*-
from __future__ import division
import io
import os
import time

import pymxs
from core.rm_ik_ui_clear import (
    get_remaining_ik_nodes,
    prepare_manual_ik_ui,
)
from core.rm_scene import get_all_descendants

rt = pymxs.runtime

try:
    _text_type = unicode
except NameError:
    _text_type = str

_PUBLISH_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    u"publish_debug.log",
)


def _log_weapon_mapping_line(msg):
    try:
        with io.open(_PUBLISH_LOG, u"a", encoding=u"utf-8") as f:
            f.write(u"[weapon-mapping] " + _text_type(msg) + u"\n")
    except Exception:
        pass


_BACKEND_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, u"maxscript", u"rm_indoor_backend.ms")
)
_HIDE_SCALE_LIB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, u"maxscript", u"hide_scale_bake.ms")
)
_ADV_FBX_LIB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, u"maxscript", u"adv_fbx_export_v25.ms")
)

_HIDE_SCALE_PREFIXES = (u"bone_ctrl", u"ctrl_bone")


def _to_mxs_split_data(split_data):
    arr = rt.Array()
    for item in (split_data or []):
        joiner = u"_"
        try:
            if len(item) >= 5:
                _, name, start_f, end_f, joiner = item
            else:
                name, start_f, end_f = item
        except Exception:
            continue
        sub = rt.Array()
        rt.append(sub, name)
        rt.append(sub, int(start_f))
        rt.append(sub, int(end_f))
        rt.append(sub, joiner)
        rt.append(arr, sub)
    return arr


def _hide_scale_targets(root_node):
    if root_node is None or not rt.isValidNode(root_node):
        return []
    result = []
    seen_names = set()
    for node in [root_node] + get_all_descendants(root_node):
        if node is None or not rt.isValidNode(node):
            continue
        name = _text_type(node.name)
        if not name.lower().startswith(_HIDE_SCALE_PREFIXES):
            continue
        key = name.lower()
        if key in seen_names:
            raise RuntimeError(u"Duplicate hide-scale node name: {0}".format(name))
        seen_names.add(key)
        result.append(node)
    return result


def _hide_scale_export_tasks(settings, base_fbx_name):
    if bool(getattr(settings, "only_cam", False)):
        return []
    base = os.path.splitext(os.path.basename(_text_type(base_fbx_name)))[0]
    split_data = getattr(settings, "split_data", None) or []
    if not split_data:
        return [
            (
                base,
                int(rt.animationRange.start.frame),
                int(rt.animationRange.end.frame),
            )
        ]
    tasks = []
    for item in split_data:
        joiner = u"_"
        try:
            if len(item) >= 5:
                _label, suffix, start_f, end_f, joiner = item[:5]
            else:
                suffix, start_f, end_f = item[:3]
        except Exception:
            continue
        task_stem = base + ((joiner + _text_type(suffix)) if suffix else u"")
        tasks.append((task_stem, int(start_f), int(end_f)))
    return tasks


def _capture_hide_scale_expectations(settings, base_fbx_name, include_unit_targets=False):
    capture_started = time.time()
    targets = _hide_scale_targets(getattr(settings, "root_obj", None))
    if not targets:
        return {}
    task_rows = []
    for task_stem, start_f, end_f in _hide_scale_export_tasks(settings, base_fbx_name):
        start_f = int(start_f)
        end_f = int(end_f)
        if end_f < start_f:
            start_f, end_f = end_f, start_f
        nodes = {}
        for node in targets:
            nodes[_text_type(node.name)] = {
                "axes": {
                    "X": {"min": None, "max": None},
                    "Y": {"min": None, "max": None},
                    "Z": {"min": None, "max": None},
                }
            }
        task_rows.append(
            {
                "stem": _text_type(task_stem).lower(),
                "start": start_f,
                "end": end_f,
                "nodes": nodes,
            }
        )
    if not task_rows:
        return {}

    # Entering pymxs.attime forces a full scene/controller evaluation.  The old
    # task->node->frame loop entered it once per node sample (thousands of full
    # evaluations on production rigs), making Max look hung and consume ~2 GB.
    # Sample every target in one frame evaluation, then distribute that sample
    # to all export segments containing the frame.  Values and segment boundary
    # semantics remain identical; only evaluation order changes.
    first_frame = min(row["start"] for row in task_rows)
    last_frame = max(row["end"] for row in task_rows)
    for frame in range(first_frame, last_frame + 1):
        active_rows = [
            row for row in task_rows if row["start"] <= frame <= row["end"]
        ]
        if not active_rows:
            continue
        frame_samples = []
        with pymxs.attime(frame):
            for node in targets:
                try:
                    scale = node.scale
                    values = (float(scale.x), float(scale.y), float(scale.z))
                except Exception as ex:
                    raise RuntimeError(
                        u"Cannot evaluate hide-scale node {0} frame {1}: {2}".format(
                            _text_type(node.name), frame, _text_type(ex)
                        )
                    )
                frame_samples.append((_text_type(node.name), values))
        for row in active_rows:
            for node_name, values in frame_samples:
                axes = row["nodes"][node_name]["axes"]
                for axis, value in zip(("X", "Y", "Z"), values):
                    axis_row = axes[axis]
                    axis_row["min"] = (
                        value
                        if axis_row["min"] is None
                        else min(axis_row["min"], value)
                    )
                    axis_row["max"] = (
                        value
                        if axis_row["max"] is None
                        else max(axis_row["max"], value)
                    )

    expectations = {}
    for row in task_rows:
        task_nodes = {}
        for node_name, node_data in row["nodes"].items():
            axes = node_data["axes"]
            non_unit = any(
                axes[axis]["min"] is not None
                and (
                    abs(axes[axis]["min"] - 1.0) > 0.0001
                    or abs(axes[axis]["max"] - 1.0) > 0.0001
                )
                for axis in ("X", "Y", "Z")
            )
            if non_unit or include_unit_targets:
                task_nodes[node_name] = node_data
        if task_nodes:
            expectations[row["stem"]] = task_nodes
    _log_weapon_mapping_line(
        u"hide-scale preflight frame-major targets={0} frames={1}-{2} tasks={3} seconds={4:.3f}".format(
            len(targets),
            first_frame,
            last_frame,
            len(task_rows),
            time.time() - capture_started,
        )
    )
    return expectations


def _to_mxs_wallhit_segments(split_data):
    from core.rm_wallhit import collect_wallhit_segments, ordered_wallhit_segments

    segments, errors = collect_wallhit_segments(split_data)
    if errors:
        raise ValueError(u"WallHit split validation failed: {0}".format(u"; ".join(errors)))
    arr = rt.Array()
    for key, start_f, end_f in ordered_wallhit_segments(segments):
        sub = rt.Array()
        rt.append(sub, key)
        rt.append(sub, int(start_f))
        rt.append(sub, int(end_f))
        rt.append(arr, sub)
    return arr


def _ensure_backend_loaded():
    if not os.path.exists(_BACKEND_PATH):
        raise IOError(u"MaxScript backend not found: {0}".format(_BACKEND_PATH))
    if not os.path.exists(_HIDE_SCALE_LIB_PATH):
        raise IOError(u"HideScaleBake library not found: {0}".format(_HIDE_SCALE_LIB_PATH))
    if not os.path.exists(_ADV_FBX_LIB_PATH):
        raise IOError(u"ADV FBX library not found: {0}".format(_ADV_FBX_LIB_PATH))
    rt.fileIn(_HIDE_SCALE_LIB_PATH)
    rt.fileIn(_ADV_FBX_LIB_PATH)
    rt.fileIn(_BACKEND_PATH)
    if not hasattr(rt, u"RMTool_IndoorBackend_PrepareIK"):
        raise RuntimeError(u"Failed to load MaxScript backend")
    if not hasattr(rt, u"RMTool_ADV_ExportRootHierarchy"):
        raise RuntimeError(u"Failed to load ADV FBX library")
    for symbol in (
        u"RMTool_HideScale_CaptureNodes",
        u"RMTool_HideScale_ContextHasNonUnit",
        u"RMTool_HideScale_ApplyToSourceNodes",
        u"RMTool_HideScale_RestoreSourceNodes",
        u"RMTool_HideScale_ApplyToBakeNodes",
    ):
        if not hasattr(rt, symbol):
            raise RuntimeError(u"Failed to load HideScaleBake library: {0}".format(symbol))


def prepare_indoor_ik(bip_obj, only_cam):
    _ensure_backend_loaded()
    try:
        return int(rt.RMTool_IndoorBackend_PrepareIK(bip_obj, bool(only_cam)))
    except Exception:
        return 0


def get_remaining_indoor_ik_nodes(bip_obj, only_cam):
    result = []
    try:
        result = get_remaining_ik_nodes(bip_obj, bool(only_cam))
    except Exception:
        result = []
    return [(_text_type(node.name), _text_type(status)) for node, status in result]


def prepare_manual_indoor_ik_ui(bip_obj, node_name):
    try:
        nodes = get_remaining_ik_nodes(bip_obj, False)
    except Exception:
        nodes = []
    picked = None
    for node, _status in nodes:
        if _text_type(node.name) == _text_type(node_name):
            picked = node
            break
    if picked is None and nodes:
        picked = nodes[0][0]
    if picked is None:
        return False
    try:
        return bool(prepare_manual_ik_ui(picked))
    except Exception:
        return False


def run_indoor_export(
    settings,
    base_fbx_name,
    orig_file_full,
    temp_max_file,
    is_batch=False,
    export_weapon_mapping=True,
    weapon_helper_ctx=None,
):
    _ensure_backend_loaded()
    hide_scale_expectations = _capture_hide_scale_expectations(settings, base_fbx_name)
    mxs_split_data = _to_mxs_split_data(getattr(settings, "split_data", []))
    wallhit_root_motion = bool(getattr(settings, "wallhit_root_motion", False))
    mxs_wallhit_segments = (
        _to_mxs_wallhit_segments(getattr(settings, "split_data", []))
        if wallhit_root_motion else rt.Array()
    )
    created_weapon_helper_ctx = weapon_helper_ctx
    weapon_root_name_hint = None
    weapon_bip_name_hint = None
    use_adv = False
    try:
        ro = getattr(settings, "root_obj", None)
        if ro is not None and rt.isValidNode(ro):
            weapon_root_name_hint = _text_type(ro.name)
    except Exception:
        weapon_root_name_hint = None
    try:
        bp = getattr(settings, "bip_obj", None)
        if bp is not None and rt.isValidNode(bp):
            weapon_bip_name_hint = _text_type(bp.name)
    except Exception:
        weapon_bip_name_hint = None
    try:
        if created_weapon_helper_ctx is None and export_weapon_mapping and not bool(getattr(settings, "only_cam", False)):
            try:
                from core.rm_weapon_state_mapping import prepare_temporary_weapon_helpers
                split_data = getattr(settings, "split_data", None) or []
                if split_data:
                    starts = []
                    ends = []
                    for item in split_data:
                        try:
                            if len(item) >= 5:
                                _label, _suffix, s, e, _joiner = item[:5]
                            else:
                                _suffix, s, e = item[:3]
                            starts.append(int(s))
                            ends.append(int(e))
                        except Exception:
                            pass
                    start_frame = min(starts) if starts else int(rt.animationRange.start.frame)
                    end_frame = max(ends) if ends else int(rt.animationRange.end.frame)
                else:
                    start_frame = int(rt.animationRange.start.frame)
                    end_frame = int(rt.animationRange.end.frame)
                max_name = os.path.basename(orig_file_full) if orig_file_full else u""
                created_weapon_helper_ctx = prepare_temporary_weapon_helpers(
                    settings.root_obj,
                    getattr(settings, "bip_obj", None),
                    u"indoor",
                    _text_type(max_name),
                    start_frame,
                    end_frame,
                    action_role_name=_text_type(base_fbx_name),
                )
                _log_weapon_mapping_line(created_weapon_helper_ctx.get(u"message", u""))
            except Exception as ex:
                _log_weapon_mapping_line(u"prepare helpers failed: " + _text_type(ex))

        use_adv = False
        try:
            from core.rm_exporter import _uses_skin_pelvis_export_branch
            use_adv = bool(_uses_skin_pelvis_export_branch(getattr(settings, "root_obj", None)))
        except Exception:
            use_adv = False

        result = rt.RMTool_IndoorBackend_RunExport(
            settings.bip_obj,
            settings.root_obj,
            base_fbx_name,
            settings.fbx_folder,
            orig_file_full,
            temp_max_file,
            bool(getattr(settings, "delete_temp", True)),
            bool(is_batch),
            bool(settings.enable_pos),
            bool(settings.follow_x),
            bool(settings.follow_y),
            bool(settings.follow_z),
            float(settings.z_thres_cm),
            float(settings.z_weight),
            bool(settings.z_limit_range),
            int(settings.z_limit_start),
            int(settings.z_limit_end),
            bool(settings.z_hover),
            float(settings.z_hover_height_cm),
            int(settings.z_hover_start),
            int(settings.z_hover_end),
            bool(settings.use_smooth),
            float(settings.filter_val),
            int(settings.smooth_str),
            bool(settings.smooth_limit_range),
            int(settings.smooth_limit_start),
            int(settings.smooth_limit_end),
            float(settings.offset_x),
            float(settings.offset_y),
            float(settings.offset_z),
            bool(settings.enable_rot),
            bool(settings.force_keys),
            bool(settings.fix_rot),
            bool(settings.remove_initial_z),
            bool(settings.unlock),
            bool(settings.exp_timeline_cam),
            bool(settings.exp_ingame_cam),
            bool(settings.only_cam),
            bool(getattr(settings, "pos_rm_limit_range", False)),
            int(getattr(settings, "pos_rm_start", 0)),
            int(getattr(settings, "pos_rm_end", 100)),
            bool(getattr(settings, "root_motion_debug_log", False)),
            wallhit_root_motion,
            mxs_wallhit_segments,
            mxs_split_data,
            bool(getattr(settings, "rot_custom_angle", False)),
            float(getattr(settings, "rot_custom_degrees", 180.0) or 0.0),
            _text_type(getattr(settings, "rot_custom_dir", u"auto") or u"auto"),
            bool(getattr(settings, "rot_limit_range", False)),
            int(getattr(settings, "rot_limit_start", 0)),
            int(getattr(settings, "rot_limit_end", 100)),
        )
    finally:
        if created_weapon_helper_ctx:
            try:
                from core.rm_weapon_state_mapping import cleanup_temporary_weapon_helpers
                cleanup_temporary_weapon_helpers(created_weapon_helper_ctx)
            except Exception:
                pass
    out_paths = [_text_type(p) for p in result]
    # Official Biped direct export: do not rewrite scale/translation in FBX.
    try:
        from core.rm_exporter import (
            _fix_fbx_percent_times10_only,
            _validate_fbx_scale_export,
        )
        for p in out_paths:
            if p and _text_type(p).lower().endswith(u".fbx") and os.path.isfile(p):
                if not use_adv:
                    _fix_fbx_percent_times10_only(p)
                _validate_fbx_scale_export(p)
    except Exception as ex:
        _log_weapon_mapping_line(u"scale-validate failed: " + _text_type(ex))

    if hide_scale_expectations:
        from core.fix_fbx_scale_curves import validate_fbx_hide_scale_expectations

        failures = []
        validated_stems = set()
        for p in out_paths:
            if not p or not _text_type(p).lower().endswith(u".fbx"):
                continue
            stem = os.path.splitext(os.path.basename(_text_type(p)))[0].lower()
            expected = hide_scale_expectations.get(stem)
            if not expected:
                continue
            validated_stems.add(stem)
            ok, reports = validate_fbx_hide_scale_expectations(p, expected)
            for line in reports:
                _log_weapon_mapping_line(u"hide-scale-validate: " + _text_type(line))
            if not ok:
                failures.extend([_text_type(line) for line in reports if line.startswith("FAIL")])
        missing = sorted(set(hide_scale_expectations.keys()) - validated_stems)
        if missing:
            failures.append(u"missing character FBX validation targets: " + u", ".join(missing))
        if failures:
            raise RuntimeError(u"HideScale FBX validation failed: " + u" | ".join(failures))

    if export_weapon_mapping:
        if created_weapon_helper_ctx and created_weapon_helper_ctx.get(u"doc"):
            try:
                from core.rm_weapon_state_mapping import (
                    build_indoor_character_fbx_stems,
                    write_mapping_doc_for_stems,
                )
                stems = build_indoor_character_fbx_stems(
                    base_fbx_name,
                    getattr(settings, "split_data", None) or [],
                    bool(getattr(settings, "only_cam", False)),
                )
                added = write_mapping_doc_for_stems(
                    created_weapon_helper_ctx.get(u"doc"),
                    _text_type(settings.fbx_folder),
                    stems,
                )
                out_paths.extend(added)
                for p in added:
                    _log_weapon_mapping_line(u"written " + p)
                return out_paths
            except Exception as ex:
                _log_weapon_mapping_line(u"write helper snapshot failed: " + _text_type(ex))
        try:
            from core.rm_weapon_state_mapping import (
                try_export_indoor_weapon_mapping_splits,
            )
        except Exception:
            try_export_indoor_weapon_mapping_splits = None
        # 局内后端末尾会 loadMaxFile，root/bip 引用失效；用导出前记录的名称重新解析。
        if try_export_indoor_weapon_mapping_splits and (
            weapon_root_name_hint
            or weapon_bip_name_hint
            or getattr(settings, "root_obj", None) is not None
            or getattr(settings, "bip_obj", None) is not None
        ):
            try:
                max_name = os.path.basename(orig_file_full) if orig_file_full else u""
                added, _msg = try_export_indoor_weapon_mapping_splits(
                    settings.root_obj,
                    getattr(settings, "bip_obj", None),
                    _text_type(settings.fbx_folder),
                    _text_type(base_fbx_name),
                    getattr(settings, "split_data", None) or [],
                    bool(getattr(settings, "only_cam", False)),
                    True,
                    _text_type(max_name),
                    root_name_hint=weapon_root_name_hint,
                    bip_name_hint=weapon_bip_name_hint,
                    action_role_name=_text_type(base_fbx_name),
                )
                out_paths.extend(added)
                for p in added:
                    _log_weapon_mapping_line(u"written " + p)
                if not added and _msg:
                    _log_weapon_mapping_line(_msg)
            except Exception as ex:
                _log_weapon_mapping_line(_text_type(ex))
    return out_paths

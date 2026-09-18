# -*- coding: utf-8 -*-
"""
Indoor export runner — BASELAYER parallel entry.

Calls RMTool_IndoorBackend_RunExport_BaseLayer.
No-layer COM restore does not need IK Object detect / IK→FK / clear / pause.
Does not alter the legacy RM_Fix path in rm_indoor_ms_runner.py.
"""
from __future__ import division
import os

import pymxs

from core.rm_indoor_ms_runner import (
    _ADV_FBX_LIB_PATH,
    _BACKEND_PATH,
    _HIDE_SCALE_LIB_PATH,
    _capture_hide_scale_expectations,
    _log_weapon_mapping_line,
    _to_mxs_split_data,
    _to_mxs_wallhit_segments,
)

rt = pymxs.runtime

try:
    _text_type = unicode
except NameError:
    _text_type = str

_BASELAYER_BACKEND_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        u"maxscript",
        u"rm_indoor_backend_baselayer.ms",
    )
)
_PROXY_EXPORT_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        u"maxscript",
        u"rm_proxy_fbx_export.ms",
    )
)

_MXS_DEBUGGER_SAFE_VALUES = (
    (u"allowBreakOnThrow", False),
    (u"breakOnError", False),
    (u"breakOnException", False),
    (u"defaultBreakOnThrow", False),
    (u"ignoreCaughtThrows", True),
    (u"ignoreCaughtErrors", True),
    (u"ignoreCaughtExceptions", True),
)

BINDING_HIERARCHY_WARNING = u"绑定层级被修改，无法导出，请检查文件后重新尝试。"


class BindingHierarchyExportError(RuntimeError):
    pass


def _suspend_mxs_debugger_breaks():
    """Prevent a caught publish error from suspending Max's main thread."""
    try:
        debugger = rt.MXSDebugger
    except Exception:
        return None
    state = []
    for prop_name, safe_value in _MXS_DEBUGGER_SAFE_VALUES:
        try:
            old_value = bool(getattr(debugger, prop_name))
            setattr(debugger, prop_name, safe_value)
            state.append((prop_name, old_value))
        except Exception:
            pass
    if state:
        _log_weapon_mapping_line(
            u"[baselayer] MAXScript debugger breaks suspended during publish"
        )
    return debugger, state


def _restore_mxs_debugger_breaks(state):
    if not state:
        return
    debugger, values = state
    for prop_name, old_value in reversed(values):
        try:
            setattr(debugger, prop_name, old_value)
        except Exception:
            pass


def _preflight_binding_hierarchy(root_obj, use_adv_export):
    """Block clean-name path collisions without throwing inside MAXScript."""
    if not bool(use_adv_export):
        return
    duplicates = rt.RMTool_Proxy_FindDuplicateExportHierarchyPathsForScene(
        root_obj, True
    )
    duplicate_paths = [_text_type(path) for path in duplicates]
    if not duplicate_paths:
        return
    _log_weapon_mapping_line(
        u"[baselayer] binding hierarchy preflight failed: {0}".format(
            u", ".join(duplicate_paths)
        )
    )
    raise BindingHierarchyExportError(BINDING_HIERARCHY_WARNING)


def _ensure_baselayer_backend_loaded():
    if not os.path.exists(_BACKEND_PATH):
        raise IOError(u"MaxScript backend not found: {0}".format(_BACKEND_PATH))
    if not os.path.exists(_BASELAYER_BACKEND_PATH):
        raise IOError(
            u"Baselayer MaxScript backend not found: {0}".format(_BASELAYER_BACKEND_PATH)
        )
    if not os.path.exists(_PROXY_EXPORT_PATH):
        raise IOError(u"Proxy Root exporter not found: {0}".format(_PROXY_EXPORT_PATH))
    if not os.path.exists(_HIDE_SCALE_LIB_PATH):
        raise IOError(u"HideScaleBake library not found: {0}".format(_HIDE_SCALE_LIB_PATH))
    if not os.path.exists(_ADV_FBX_LIB_PATH):
        raise IOError(u"ADV FBX library not found: {0}".format(_ADV_FBX_LIB_PATH))
    rt.fileIn(_HIDE_SCALE_LIB_PATH)
    rt.fileIn(_ADV_FBX_LIB_PATH)
    rt.fileIn(_BACKEND_PATH)
    rt.fileIn(_PROXY_EXPORT_PATH)
    rt.fileIn(_BASELAYER_BACKEND_PATH)
    if not hasattr(rt, u"RMTool_IndoorBackend_RunExport_BaseLayer"):
        raise RuntimeError(u"Failed to load Baselayer RunExport_BaseLayer")
    for symbol in (
        u"RMTool_Proxy_BuildDesiredRootTransforms",
        u"RMTool_Proxy_CreateContext",
        u"RMTool_Proxy_ExportContext",
        u"RMTool_Proxy_CleanupContext",
        u"RMTool_Proxy_RunInPlaceExport",
        u"RMTool_Proxy_FindDuplicateExportHierarchyPathsForScene",
    ):
        if not hasattr(rt, symbol):
            raise RuntimeError(u"Failed to load Proxy Root library: {0}".format(symbol))
    try:
        _ver = _text_type(rt.RMTool_Baselayer_BackendVersion)
    except Exception:
        _ver = u"unknown"
    _log_weapon_mapping_line(
        u"[baselayer] loaded backend={0} proxy={1} path={2}".format(
            _ver,
            _text_type(getattr(rt, u"RMTool_Proxy_BackendVersion", u"unknown")),
            _BASELAYER_BACKEND_PATH,
        )
    )
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


def run_indoor_export_baselayer(
    settings,
    base_fbx_name,
    orig_file_full,
    temp_max_file,
    is_batch=False,
    export_weapon_mapping=True,
    weapon_helper_ctx=None,
):
    """Same surface as run_indoor_export; MaxScript entry is RunExport_BaseLayer."""
    debugger_state = _suspend_mxs_debugger_breaks()
    try:
        _ensure_baselayer_backend_loaded()
    finally:
        _restore_mxs_debugger_breaks(debugger_state)
    raw_sample_rate = getattr(settings, "proxy_sample_rate_hz", 30) or 30
    try:
        sample_rate_hz = int(raw_sample_rate)
    except Exception:
        sample_rate_hz = 30
    if sample_rate_hz not in (30, 60, 120):
        _log_weapon_mapping_line(
            u"[baselayer] invalid sample rate {0}; fallback to 30Hz".format(
                _text_type(raw_sample_rate)
            )
        )
        sample_rate_hz = 30
    hide_scale_expectations = _capture_hide_scale_expectations(
        settings, base_fbx_name, include_unit_targets=True
    )
    mxs_split_data = _to_mxs_split_data(getattr(settings, "split_data", []))
    wallhit_root_motion = bool(getattr(settings, "wallhit_root_motion", False))
    mxs_wallhit_segments = (
        _to_mxs_wallhit_segments(getattr(settings, "split_data", []))
        if wallhit_root_motion
        else rt.Array()
    )
    created_weapon_helper_ctx = weapon_helper_ctx
    weapon_root_name_hint = None
    weapon_bip_name_hint = None
    use_adv = False
    result = []
    debugger_state = _suspend_mxs_debugger_breaks()
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
        if (
            created_weapon_helper_ctx is None
            and export_weapon_mapping
            and not bool(getattr(settings, "only_cam", False))
        ):
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
                    start_frame = (
                        min(starts) if starts else int(rt.animationRange.start.frame)
                    )
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

            use_adv = bool(
                _uses_skin_pelvis_export_branch(getattr(settings, "root_obj", None))
            )
        except Exception:
            use_adv = False

        _log_weapon_mapping_line(
            u"[baselayer] calling RunExport_BaseLayer sampleRate={0}Hz".format(
                sample_rate_hz
            )
        )
        _preflight_binding_hierarchy(settings.root_obj, use_adv)
        result = rt.RMTool_IndoorBackend_RunExport_BaseLayer(
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
            sample_rate_hz,
        )
    finally:
        try:
            rt.RMTool_Proxy_ProgressHide()
        except Exception:
            pass
        if created_weapon_helper_ctx:
            try:
                from core.rm_weapon_state_mapping import cleanup_temporary_weapon_helpers

                cleanup_temporary_weapon_helpers(created_weapon_helper_ctx)
            except Exception:
                pass
        _restore_mxs_debugger_breaks(debugger_state)

    out_paths = [_text_type(p) for p in result]
    from core.fix_fbx_scale_curves import validate_fbx_transform_curves_within_take

    task_curve_failures = []
    for p in out_paths:
        if not p or not _text_type(p).lower().endswith(u".fbx") or not os.path.isfile(p):
            continue
        task_curve_ok, task_curve_reports = validate_fbx_transform_curves_within_take(p)
        for line in task_curve_reports:
            _log_weapon_mapping_line(u"task-local-PRS: " + _text_type(line))
        if not task_curve_ok:
            task_curve_failures.extend(
                [_text_type(line) for line in task_curve_reports if line.startswith("FAIL")]
            )
    if task_curve_failures:
        raise RuntimeError(
            u"FBX 分段曲线越界，已阻止发布: " + u" | ".join(task_curve_failures)
        )

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
                failures.extend(
                    [_text_type(line) for line in reports if line.startswith("FAIL")]
                )
        missing = sorted(set(hide_scale_expectations.keys()) - validated_stems)
        if missing:
            failures.append(
                u"missing character FBX validation targets: " + u", ".join(missing)
            )
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


__all__ = [
    u"BINDING_HIERARCHY_WARNING",
    u"BindingHierarchyExportError",
    u"_preflight_binding_hierarchy",
    u"run_indoor_export_baselayer",
]

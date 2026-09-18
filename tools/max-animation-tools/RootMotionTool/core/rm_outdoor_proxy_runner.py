# -*- coding: utf-8 -*-
"""Shared ProxyRoot character export for the official outdoor publisher.

The outdoor UI keeps its naming, multi-character, Morpher, weapon and camera
workflow.  Only the character FBX build/export stage is delegated to the same
ProxyRoot backend used by the official indoor publisher.
"""
from __future__ import division

import os

import pymxs

from core.rm_indoor_ms_runner import (
    _capture_hide_scale_expectations,
    _log_weapon_mapping_line,
)
from core.rm_indoor_ms_runner_baselayer import (
    _ensure_baselayer_backend_loaded,
    _preflight_binding_hierarchy,
    _restore_mxs_debugger_breaks,
    _suspend_mxs_debugger_breaks,
)


rt = pymxs.runtime

try:
    _text_type = unicode
except NameError:
    _text_type = str


class _OutdoorHideScaleSettings(object):
    def __init__(self, root_obj):
        self.root_obj = root_obj
        self.split_data = []
        self.only_cam = False


def _to_mxs_array(nodes):
    result = rt.Array()
    for node in nodes or []:
        if node is None:
            continue
        try:
            if rt.isValidNode(node):
                rt.append(result, node)
        except Exception:
            pass
    return result


def _normalize_sample_rate(value):
    try:
        sample_rate = int(value)
    except Exception:
        sample_rate = 30
    if sample_rate not in (30, 60, 120):
        raise ValueError(
            u"ProxyRoot sample rate must be 30, 60, or 120 Hz; got {0}".format(
                _text_type(value)
            )
        )
    return sample_rate


def _validate_exported_hide_scale(fbx_path, expectations):
    if not expectations:
        return
    from core.fix_fbx_scale_curves import validate_fbx_hide_scale_expectations

    stem = os.path.splitext(os.path.basename(_text_type(fbx_path)))[0].lower()
    expected = expectations.get(stem)
    if not expected:
        raise RuntimeError(
            u"HideScale FBX validation target missing for outdoor proxy: {0}".format(
                stem
            )
        )
    ok, reports = validate_fbx_hide_scale_expectations(fbx_path, expected)
    failures = []
    report_lines = []
    for line in reports:
        line = _text_type(line)
        report_lines.append(line)
        _log_weapon_mapping_line(u"outdoor-proxy hide-scale-validate: " + line)
        if line.startswith(u"FAIL"):
            failures.append(line)
    if not ok:
        raise RuntimeError(
            u"HideScale FBX validation failed: " + u" | ".join(failures or report_lines)
        )


def export_outdoor_character_proxy(
    root_obj,
    bip_obj,
    fbx_path,
    start_f,
    end_f,
    sample_rate_hz=30,
    use_adv_export=False,
    extra_nodes=None,
    morph_nodes=None,
    progress_title=u"",
):
    """Export one outdoor character through the shared ProxyRoot FBX kernel."""
    if root_obj is None or not rt.isValidNode(root_obj):
        raise RuntimeError(u"局外 ProxyRoot 发布找不到有效的 Root/Bip 根节点")
    if bip_obj is None or not rt.isValidNode(bip_obj):
        raise RuntimeError(u"局外 ProxyRoot 发布找不到有效的 Bip001")
    if int(rt.frameRate) != 30:
        raise RuntimeError(
            u"ProxyRoot 发布要求 Max 场景为 30 FPS；当前为 {0} FPS。"
            u"请先改为 30 FPS，并重新检查镜头、事件和动画帧范围。".format(
                int(rt.frameRate)
            )
        )

    sample_rate_hz = _normalize_sample_rate(sample_rate_hz)
    start_f = int(start_f)
    end_f = int(end_f)
    if end_f < start_f:
        raise ValueError(u"局外 ProxyRoot 发布帧范围无效：{0}-{1}".format(start_f, end_f))

    out_dir = os.path.dirname(_text_type(fbx_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    # Capture the source visibility contract before any temporary proxy node is
    # created.  This mirrors the indoor post-FBX hard validation.
    expectations = _capture_hide_scale_expectations(
        _OutdoorHideScaleSettings(root_obj),
        os.path.basename(_text_type(fbx_path)),
        include_unit_targets=True,
    )

    debugger_state = _suspend_mxs_debugger_breaks()
    try:
        _ensure_baselayer_backend_loaded()
    finally:
        _restore_mxs_debugger_breaks(debugger_state)
    if not hasattr(rt, u"RMTool_Proxy_RunInPlaceExport"):
        raise RuntimeError(u"ProxyRoot shared outdoor exporter failed to load")
    _preflight_binding_hierarchy(root_obj, use_adv_export)

    _log_weapon_mapping_line(
        u"[outdoor-proxy] export sampleRate={0}Hz useAdv={1} path={2}".format(
            sample_rate_hz,
            bool(use_adv_export),
            _text_type(fbx_path),
        )
    )
    debugger_state = _suspend_mxs_debugger_breaks()
    try:
        ok = rt.RMTool_Proxy_RunInPlaceExport(
            root_obj,
            bip_obj,
            _text_type(fbx_path),
            start_f,
            end_f,
            sample_rate_hz,
            extraNodes=_to_mxs_array(extra_nodes),
            morphMeshes=_to_mxs_array(morph_nodes),
            autoMorph=False,
            isBatch=False,
            progressTitle=_text_type(progress_title or os.path.basename(fbx_path)),
            useAdvExport=bool(use_adv_export),
        )
        if not bool(ok):
            raise RuntimeError(u"ProxyRoot shared outdoor exporter returned false")
    finally:
        try:
            rt.RMTool_Proxy_ProgressHide()
        except Exception:
            pass
        _restore_mxs_debugger_breaks(debugger_state)

    if not os.path.isfile(fbx_path):
        raise RuntimeError(u"局外 ProxyRoot 发布未生成 FBX：{0}".format(fbx_path))

    from core.rm_exporter import _validate_fbx_scale_export

    _validate_fbx_scale_export(fbx_path)
    _validate_exported_hide_scale(fbx_path, expectations)
    return _text_type(fbx_path)


__all__ = [u"export_outdoor_character_proxy"]

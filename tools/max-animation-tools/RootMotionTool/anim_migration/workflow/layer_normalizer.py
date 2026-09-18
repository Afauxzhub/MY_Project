# -*- coding: utf-8 -*-
from __future__ import print_function

import os


NORMALIZER_VERSION = "0.3-integrated"
CORE_SCRIPT_NAME = "ADVLayerRefreshCore.ms"

_MOVE_LABELS = (
    "dum",
    "ui_controls",
    "ui_text",
    "ui_frame",
    "ui_helper",
    "body_ctrl",
    "body_helper",
)

_LEGACY_LABELS = (
    "legacy_bs_ui",
    "legacy_visibility_ui",
    "legacy_layer_002",
)


try:
    _text_type = unicode
except NameError:
    _text_type = str


def _text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _items(value):
    if value is None:
        return []
    try:
        return list(value)
    except Exception:
        return []


def _integer(value):
    try:
        return int(value)
    except Exception:
        return 0


def _count_map(labels, values):
    values = _items(values)
    return dict([
        (label, _integer(values[index]) if index < len(values) else 0)
        for index, label in enumerate(labels)
    ])


def _public_result(raw):
    values = _items(raw)
    moved = _count_map(_MOVE_LABELS, values[0] if len(values) > 0 else [])
    legacy = _count_map(_LEGACY_LABELS, values[1] if len(values) > 1 else [])
    warnings = [_text(value) for value in _items(values[2] if len(values) > 2 else [])]
    log = [_text(value) for value in _items(values[3] if len(values) > 3 else [])]
    deleted = _integer(values[4]) if len(values) > 4 else 0
    failures = [_text(value) for value in _items(values[5] if len(values) > 5 else [])]
    return {
        "moved": moved,
        "moved_total": sum(moved.values()),
        "legacy_input": legacy,
        "warnings": warnings,
        "log": log,
        "deleted_legacy_layer_count": deleted,
        "failures": failures,
    }


def normalizer_core_path(tool_root):
    return os.path.join(os.path.abspath(_text(tool_root)), "maxscript", CORE_SCRIPT_NAME)


class _suspended_redraw(object):
    def __init__(self, rt):
        self.rt = rt
        self.disabled = False

    def __enter__(self):
        try:
            self.rt.disableSceneRedraw()
            self.disabled = True
        except Exception:
            self.disabled = False
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.disabled:
            try:
                self.rt.enableSceneRedraw()
            except Exception:
                pass
        return False


def _run(rt, apply_changes):
    expression = "OP_RigLayerRefresh_run applyChanges:{0}".format(
        "true" if apply_changes else "false"
    )
    return _public_result(rt.execute(expression))


def normalize_loaded_animation_scene(rt, tool_root):
    """Analyze, normalize, and verify Layers in the currently loaded animation.

    The caller owns the loaded Max scene. This function never saves a file.
    """
    core_path = normalizer_core_path(tool_root)
    result = {
        "ok": False,
        "version": NORMALIZER_VERSION,
        "core_path": core_path,
        "analysis": {},
        "apply": {},
        "verification": {},
        "message": u"",
    }
    if not os.path.exists(core_path):
        result["error_code"] = "CANON-LAYER-NORMALIZER-MISSING"
        result["message"] = u"缺少动画 Layer 整理核心: {0}".format(core_path)
        return result

    try:
        rt.fileIn(core_path)
        with _suspended_redraw(rt):
            result["analysis"] = _run(rt, False)
            result["apply"] = _run(rt, True)
            result["verification"] = _run(rt, False)
    except Exception as error:
        result["error_code"] = "CANON-LAYER-NORMALIZER-EXECUTION"
        result["message"] = u"动画 Layer 整理执行失败: {0}".format(_text(error))
        return result

    apply_failures = result["apply"].get("failures", []) or []
    verification = result["verification"]
    remaining_moves = int(verification.get("moved_total", 0) or 0)
    remaining_warnings = verification.get("warnings", []) or []
    verification_failures = verification.get("failures", []) or []
    if apply_failures or verification_failures:
        result["error_code"] = "CANON-LAYER-NORMALIZER-FAILED"
        result["message"] = u"动画 Layer 整理有 {0} 个执行失败项".format(
            len(apply_failures) + len(verification_failures)
        )
        return result
    if remaining_moves:
        result["error_code"] = "CANON-LAYER-NORMALIZER-NOT-CONVERGED"
        result["message"] = u"动画 Layer 整理后仍有 {0} 个对象需要移动".format(remaining_moves)
        return result
    if remaining_warnings:
        result["error_code"] = "CANON-LAYER-NORMALIZER-UNCLASSIFIED"
        result["message"] = u"动画 Layer 整理后仍有 {0} 个旧 UI 节点无法分类".format(
            len(remaining_warnings)
        )
        return result

    result["ok"] = True
    result["error_code"] = None
    result["message"] = u"动画 Layer 分析、整理和复检完成"
    return result

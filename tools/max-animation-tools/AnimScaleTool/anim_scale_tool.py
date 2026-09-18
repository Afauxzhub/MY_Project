# -*- coding: utf-8 -*-
"""缩放值工具 — 3ds Max 入口。"""
from __future__ import print_function
import os
import sys

_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_INSTALL_ROOT = os.path.dirname(_TOOL_DIR)
_RM_TOOL_DIR = os.path.join(_INSTALL_ROOT, u"RootMotionTool")
_AFM_DIR = os.path.join(_INSTALL_ROOT, u"AnimFileManager")
_WINDOW = None


def _norm_path(path):
    return os.path.normcase(os.path.abspath(path or ""))


def _ensure_tool_path():
    tool_dir = _norm_path(_TOOL_DIR)
    while tool_dir in sys.path:
        sys.path.remove(tool_dir)
    sys.path.insert(0, tool_dir)
    return tool_dir


def _purge_conflicting_modules():
    tool_dir = _norm_path(_TOOL_DIR)
    rm_dir = _norm_path(_RM_TOOL_DIR)
    afm_dir = _norm_path(_AFM_DIR)
    prefixes = (u"ui", u"core", u"pipeline", u"anim_migration", u"anim_fm_tool")
    for name in list(sys.modules.keys()):
        hit = any(
            name == prefix or name.startswith(prefix + u".") for prefix in prefixes
        )
        if not hit:
            continue
        mod = sys.modules.get(name)
        mod_file = getattr(mod, u"__file__", u"") or u""
        if not mod_file:
            try:
                del sys.modules[name]
            except Exception:
                pass
            continue
        mod_norm = _norm_path(mod_file)
        if mod_norm.startswith(tool_dir + os.sep):
            continue
        if mod_norm.startswith(rm_dir + os.sep) or mod_norm.startswith(afm_dir + os.sep):
            try:
                del sys.modules[name]
            except Exception:
                pass


def _cleanup_stale_windows():
    try:
        from PySide2 import QtWidgets
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        for widget in list(app.allWidgets()):
            try:
                if widget.windowTitle() != u"缩放值":
                    continue
                timer = getattr(widget, u"_selection_timer", None)
                if timer is not None:
                    try:
                        timer.stop()
                    except Exception:
                        pass
                widget.close()
                widget.deleteLater()
            except Exception:
                pass
    except Exception:
        pass


def show():
    global _WINDOW
    _ensure_tool_path()
    _purge_conflicting_modules()
    _cleanup_stale_windows()
    _WINDOW = None

    if _WINDOW is not None:
        try:
            _WINDOW.raise_()
            _WINDOW.activateWindow()
            _WINDOW.showNormal()
            return _WINDOW
        except Exception:
            _WINDOW = None

    try:
        from scale_value_window import ScaleValueWindow
        _WINDOW = ScaleValueWindow(parent=None)
        _WINDOW.show()
        return _WINDOW
    except Exception:
        import traceback
        traceback.print_exc()
        _WINDOW = None
        return None


def close():
    global _WINDOW
    if _WINDOW is not None:
        try:
            _WINDOW.close()
        except Exception:
            pass
        _WINDOW = None

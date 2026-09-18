# -*- coding: utf-8 -*-
"""
动画文件管理器 — 3ds Max 入口
"""
from __future__ import print_function
import sys
import os

_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_INSTALL_ROOT = os.path.dirname(_TOOL_DIR)
_RM_TOOL_DIR = os.path.join(_INSTALL_ROOT, u"RootMotionTool")
_WINDOW = None

_CLASH_PREFIXES = (
    "ui",
    "core",
)


def _norm_path(path):
    return os.path.normcase(os.path.abspath(path or ""))


def _ensure_tool_path():
    tool_dir = _norm_path(_TOOL_DIR)
    while tool_dir in sys.path:
        sys.path.remove(tool_dir)
    sys.path.insert(0, tool_dir)
    return tool_dir


def _purge_afm_modules():
    """
    清除 AnimFileManager 与 RootMotionTool 之间冲突的 ui/core 缓存。
    两个工具都使用 ui/core 包名，必须全部移除后重新从 AFM 目录加载。
    """
    tool_dir = _norm_path(_TOOL_DIR)
    rm_dir = _norm_path(_RM_TOOL_DIR)
    for name in list(sys.modules.keys()):
        hit = False
        for prefix in _CLASH_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                hit = True
                break
        if not hit:
            continue
        mod = sys.modules.get(name)
        mod_file = getattr(mod, "__file__", "") or ""
        if not mod_file:
            try:
                del sys.modules[name]
            except Exception:
                pass
            continue
        mod_norm = _norm_path(mod_file)
        if mod_norm.startswith(tool_dir + os.sep) or mod_norm.startswith(rm_dir + os.sep):
            try:
                del sys.modules[name]
            except Exception:
                pass


def show():
    global _WINDOW
    tool_dir = _ensure_tool_path()

    if _WINDOW is not None:
        try:
            if _WINDOW.isVisible():
                _WINDOW.raise_()
                _WINDOW.activateWindow()
                _WINDOW.showNormal()
                return _WINDOW
        except Exception:
            pass
        _WINDOW = None

    _purge_afm_modules()
    try:
        from ui.afm_main_window import AnimFileManagerWindow
        _WINDOW = AnimFileManagerWindow(parent=None)
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
            if _WINDOW.isVisible():
                _WINDOW.close()
        except Exception:
            pass
    _WINDOW = None

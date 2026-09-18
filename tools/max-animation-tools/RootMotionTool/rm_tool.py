# -*- coding: utf-8 -*-
"""
Animation 动作工具 (引用 + Root Motion FBX 发布 + 武器约束绑定) — Entry Point
Max 2020 / Python 2.7 / PySide2

Launch from MAXScript Listener:
    Method A (recommended):
        Drag `install_animation_tools.ms` into 3ds Max once to install.
        Then drag the registered macro from Customize UI to a toolbar.

    Method B (development / portable):
        Drag `launch_rm_tool.ms` directly into 3ds Max.

    Method C (manual, two steps):
        Step 1 (once per Max session):
            python.Execute "import sys; sys.path.insert(0, r'<your_tool_dir>')"
        Step 2 (each time):
            python.Execute "import rm_tool; rm_tool.show()"

    DO NOT use python.ExecuteFile - it passes file content as a Unicode
    string which conflicts with coding declarations in Python 2.

CRASH NOTES:
    - Never create QApplication inside Max (Max already owns Qt event loop)
    - Use qtmax.GetQMaxMainWindow() for parent (Max 2020+)
    - Never pass getMAXHWND() to shiboken2.wrapInstance (HWND != C++ ptr)
"""
from __future__ import print_function
import sys
import os

_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_INSTALL_ROOT = os.path.dirname(_TOOL_DIR)
_AFM_DIR = os.path.join(_INSTALL_ROOT, u"AnimFileManager")
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)

_WINDOW_INSTANCE = None
_PUBLISH_WINDOW = None
_PUBLISH_LEGACY_WINDOW = None


def _norm_path(path):
    return os.path.normcase(os.path.abspath(path or ""))


def _purge_conflicting_modules(tool_dir, prefixes, also_from_dir=None):
    tool_dir = _norm_path(tool_dir)
    extra_dirs = []
    if also_from_dir:
        extra_dirs.append(_norm_path(also_from_dir))
    for name in list(sys.modules.keys()):
        hit = False
        for prefix in prefixes:
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
        dirs = [tool_dir] + extra_dirs
        if any(mod_norm.startswith(d + os.sep) for d in dirs):
            try:
                del sys.modules[name]
            except Exception:
                pass


def show(mode=u"full"):
    """Launch or focus the main window (singleton). mode: full | publish_only"""
    global _WINDOW_INSTANCE
    if mode == u"publish_only":
        return show_publish_only()

    if _WINDOW_INSTANCE is not None:
        try:
            _WINDOW_INSTANCE.raise_()
            _WINDOW_INSTANCE.activateWindow()
            _WINDOW_INSTANCE.showNormal()
            try:
                _WINDOW_INSTANCE._refresh_publish_state_from_scene()
            except Exception:
                pass
            return _WINDOW_INSTANCE
        except Exception:
            _WINDOW_INSTANCE = None

    try:
        _prepare_rm_env()
        from ui.rm_main_window import MainWindow
    except Exception:
        import traceback
        traceback.print_exc()
        return None

    try:
        _WINDOW_INSTANCE = MainWindow(
            parent=None, mode=u"full", com_restore_engine=u"baselayer"
        )
        _WINDOW_INSTANCE.show()
        return _WINDOW_INSTANCE
    except Exception:
        import traceback
        traceback.print_exc()
        return None


def show_publish_only():
    """正式发布入口：仅打开 ProxyRoot 发布动画界面。"""
    global _PUBLISH_WINDOW
    if _PUBLISH_WINDOW is not None:
        try:
            _PUBLISH_WINDOW.raise_()
            _PUBLISH_WINDOW.activateWindow()
            _PUBLISH_WINDOW.showNormal()
            try:
                _PUBLISH_WINDOW._refresh_publish_state_from_scene()
            except Exception:
                pass
            return _PUBLISH_WINDOW
        except Exception:
            _PUBLISH_WINDOW = None
    try:
        _prepare_rm_env()
        from ui.rm_main_window import MainWindow
        _PUBLISH_WINDOW = MainWindow(
            parent=None, mode=u"publish_only", com_restore_engine=u"baselayer"
        )
        _PUBLISH_WINDOW.show()
        try:
            _PUBLISH_WINDOW._auto_select_publish_type_from_scene()
        except Exception:
            pass
        try:
            _PUBLISH_WINDOW._refresh_publish_state_from_scene()
        except Exception:
            pass
        return _PUBLISH_WINDOW
    except Exception:
        import traceback
        traceback.print_exc()
        return None


def show_publish_baselayer():
    """兼容旧实验调用名；当前与正式 ProxyRoot 发布入口相同。"""
    return show_publish_only()


def show_publish_legacy():
    """隐藏的 Legacy/RM_Fix 备份入口，不注册到动画师界面。"""
    global _PUBLISH_LEGACY_WINDOW
    if _PUBLISH_LEGACY_WINDOW is not None:
        try:
            _PUBLISH_LEGACY_WINDOW.raise_()
            _PUBLISH_LEGACY_WINDOW.activateWindow()
            _PUBLISH_LEGACY_WINDOW.showNormal()
            try:
                _PUBLISH_LEGACY_WINDOW._refresh_publish_state_from_scene()
            except Exception:
                pass
            return _PUBLISH_LEGACY_WINDOW
        except Exception:
            _PUBLISH_LEGACY_WINDOW = None
    try:
        _prepare_rm_env()
        from ui.rm_main_window import MainWindow
        _PUBLISH_LEGACY_WINDOW = MainWindow(
            parent=None, mode=u"publish_only", com_restore_engine=u"legacy"
        )
        _PUBLISH_LEGACY_WINDOW.show()
        try:
            _PUBLISH_LEGACY_WINDOW._auto_select_publish_type_from_scene()
        except Exception:
            pass
        try:
            _PUBLISH_LEGACY_WINDOW._refresh_publish_state_from_scene()
        except Exception:
            pass
        return _PUBLISH_LEGACY_WINDOW
    except Exception:
        import traceback
        traceback.print_exc()
        return None


def _prepare_rm_env():
    tool_dir = _norm_path(_TOOL_DIR)
    while tool_dir in sys.path:
        sys.path.remove(tool_dir)
    sys.path.insert(0, tool_dir)
    _purge_conflicting_modules(
        tool_dir,
        ("rm_tool", "ui", "core", "pipeline", "anim_migration"),
        also_from_dir=_AFM_DIR,
    )
    return tool_dir


def show_weapon():
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_weapon_panel()


def show_binding_update():
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_binding_update()


def show_shot_assist():
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_shot_assist()


def show_publish_from_scene():
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_publish_from_scene()


def show_publish_baselayer_from_scene():
    """兼容旧实验调用名；当前与正式入口相同。"""
    return show_publish_from_scene()


def show_publish_legacy_from_scene():
    """按当前文件名打开隐藏的 Legacy/RM_Fix 备份发布器。"""
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_publish_legacy_from_scene()


def _get_max_parent():
    """Get Max main window as Qt parent widget.

    Max 2020+ uses qtmax; MaxPlus is deprecated but kept as fallback.
    The shiboken2/HWND approach is intentionally removed: getMAXHWND()
    returns a Windows HWND token, NOT a C++ object pointer - passing it
    to wrapInstance causes an immediate Access Violation crash.
    """
    # Primary: qtmax (Max 2019+ official replacement for MaxPlus)
    try:
        import qtmax
        return qtmax.GetQMaxMainWindow()
    except Exception:
        pass

    # Secondary: MaxPlus (deprecated in Max 2019, may still work in 2020)
    try:
        import MaxPlus
        parent = MaxPlus.GetQMaxMainWindow()
        if parent is not None:
            return parent
    except Exception:
        pass

    # No valid parent found - window opens as standalone (still usable)
    return None


def close():
    """Close the tool window."""
    global _WINDOW_INSTANCE, _PUBLISH_WINDOW, _PUBLISH_LEGACY_WINDOW
    if _WINDOW_INSTANCE is not None:
        try:
            _WINDOW_INSTANCE.close()
        except Exception:
            pass
        _WINDOW_INSTANCE = None
    if _PUBLISH_WINDOW is not None:
        try:
            _PUBLISH_WINDOW.close()
        except Exception:
            pass
        _PUBLISH_WINDOW = None
    if _PUBLISH_LEGACY_WINDOW is not None:
        try:
            _PUBLISH_LEGACY_WINDOW.close()
        except Exception:
            pass
        _PUBLISH_LEGACY_WINDOW = None

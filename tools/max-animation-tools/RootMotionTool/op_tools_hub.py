# -*- coding: utf-8 -*-
"""
动画工具菜单 — Python 动作中枢
供 MaxScript 菜单宏调用。
"""
from __future__ import print_function
import os
import sys

_HUB_DIR = os.path.dirname(os.path.abspath(__file__))
_INSTALL_ROOT = os.path.dirname(_HUB_DIR)
_RM_TOOL_DIR = os.path.join(_INSTALL_ROOT, u"RootMotionTool")
_AFM_DIR = os.path.join(_INSTALL_ROOT, u"AnimFileManager")
_ANIM_SCALE_DIR = os.path.join(_INSTALL_ROOT, u"AnimScaleTool")
_VIS_CTRL_SCALE_FIX_MS = os.path.join(
    _INSTALL_ROOT, u"maxscript", u"VisCtrlScaleBatchFix.ms"
)
_ANIM_LIB_DIR = os.path.join(_INSTALL_ROOT, u"AnimationLibrary")

_ANIM_LIB_CANDIDATES = [
    _ANIM_LIB_DIR,
    os.path.join(
        os.environ.get(u"USERPROFILE", u""),
        u"AppData", u"Local", u"Autodesk", u"3dsMax", u"2020 - 64bit", u"ENU",
        u"scripts", u"Max_AI_Tools",
    ),
    os.path.join(
        os.environ.get(u"USERPROFILE", u""),
        u"AppData", u"Local", u"Autodesk", u"3dsMax", u"2020 - 64bit", u"CHS",
        u"scripts", u"Max_AI_Tools",
    ),
]


def _norm_dir(path):
    return os.path.normcase(os.path.abspath(path or ""))


def _move_tool_dir_to_front(tool_dir):
    tool_dir = _norm_dir(tool_dir)
    while tool_dir in sys.path:
        sys.path.remove(tool_dir)
    sys.path.insert(0, tool_dir)
    return tool_dir


def _purge_tool_modules(tool_dir, prefixes, also_from_dir=None):
    tool_dir = _norm_dir(tool_dir)
    extra_dirs = []
    if also_from_dir:
        extra_dirs.append(_norm_dir(also_from_dir))
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
        mod_norm = _norm_dir(mod_file)
        dirs = [tool_dir] + extra_dirs
        if any(mod_norm.startswith(d + os.sep) for d in dirs):
            try:
                del sys.modules[name]
            except Exception:
                pass


def _prepare_afm_env():
    tool_dir = _move_tool_dir_to_front(_AFM_DIR)
    _purge_tool_modules(
        tool_dir,
        ("anim_fm_tool", "ui", "core"),
        also_from_dir=_RM_TOOL_DIR,
    )
    return tool_dir


def _prepare_rm_env():
    tool_dir = _move_tool_dir_to_front(_RM_TOOL_DIR)
    _purge_tool_modules(
        tool_dir,
        (
            "rm_tool",
            "ui",
            "core",
            "pipeline",
            "anim_migration",
        ),
        also_from_dir=_AFM_DIR,
    )
    return tool_dir


def _prepare_scale_env():
    tool_dir = _move_tool_dir_to_front(_ANIM_SCALE_DIR)
    _purge_tool_modules(
        tool_dir,
        (
            "anim_scale_tool",
            "scale_value_window",
            "scale_keys",
            "ui",
            "core",
        ),
        also_from_dir=_RM_TOOL_DIR,
    )
    return tool_dir


def open_file_manager():
    _prepare_afm_env()
    import anim_fm_tool
    return anim_fm_tool.show()


def open_new_file_tool():
    _prepare_rm_env()
    from ui import rm_new_file_dialog
    return rm_new_file_dialog.show()


def open_publish_tool():
    """正式发布入口：ProxyRoot（局内/局外角色统一）。"""
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_publish_from_scene()


def open_publish_baselayer_tool():
    """兼容旧实验调用名；当前与正式发布入口相同。"""
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_publish_from_scene()


def open_publish_legacy_tool():
    """隐藏的 Legacy/RM_Fix 备份入口，不注册到动画师菜单。"""
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_publish_legacy_from_scene()


def open_weapon_tool():
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_weapon_panel()


def open_binding_update():
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_binding_update()


def open_shot_assist():
    _prepare_rm_env()
    from ui import rm_tool_windows
    return rm_tool_windows.show_shot_assist()


def open_anim_scale_tool():
    _prepare_scale_env()
    import anim_scale_tool
    return anim_scale_tool.show()


def open_vis_ctrl_scale_fix_tool():
    if not os.path.isfile(_VIS_CTRL_SCALE_FIX_MS):
        raise IOError(u"Visibility Ctrl scale fix script not found: {0}".format(
            _VIS_CTRL_SCALE_FIX_MS
        ))
    import pymxs
    pymxs.runtime.fileIn(_VIS_CTRL_SCALE_FIX_MS)
    return True


def open_anim_library():
    for root in _ANIM_LIB_CANDIDATES:
        launch_py = os.path.join(root, u"launch_plugin.py")
        if os.path.isfile(launch_py):
            try:
                g = {u"__file__": launch_py, u"__name__": u"__main__"}
                with open(launch_py, u"r") as f:
                    code = compile(f.read(), launch_py, u"exec")
                exec(code, g, g)
                return True
            except Exception:
                import traceback
                traceback.print_exc()
    try:
        import pymxs
        pymxs.runtime.macros.run(u"Max AI Tools", u"AnimationLibraryLauncher")
        return True
    except Exception:
        pass
    from PySide2 import QtWidgets
    QtWidgets.QMessageBox.warning(
        None,
        u"动作库",
        u"未找到动作库文件。请执行 Animation Tools Update 或重新拖入 install_animation_tools.ms 安装/更新工具。",
    )
    return False


def is_dev_machine():
    _prepare_rm_env()
    from ui.rm_main_window import MainWindow
    probe = MainWindow(parent=None, mode=u"publish_only")
    try:
        return probe._is_dev_machine_install()
    finally:
        try:
            probe.close()
        except Exception:
            pass


def upload_tools():
    _prepare_rm_env()
    from ui.rm_main_window import MainWindow
    helper = MainWindow(parent=None, mode=u"full")
    try:
        helper._upload_update_to_public()
    finally:
        try:
            helper.close()
        except Exception:
            pass

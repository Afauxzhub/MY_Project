# -*- coding: utf-8 -*-
"""
独立工具窗口：武器约束 / 绑定更新 / 镜头辅助
以及发布工具按模式打开。
"""
from __future__ import print_function
import os
import sys

from PySide2 import QtWidgets, QtCore

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)

_WINDOWS = {}

try:
    _text_type = unicode
except NameError:
    _text_type = str


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return _text_type(repr(value))


def _get_rt():
    import pymxs
    return pymxs.runtime


def _base_dialog(title, min_size=(520, 640)):
    from ui.rm_theme import apply_dark_theme

    dlg = QtWidgets.QDialog(parent=None)
    dlg.setWindowTitle(_as_text(title))
    dlg.setMinimumSize(*min_size)
    dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
    apply_dark_theme(dlg)
    return dlg


def _add_tool_toolbar(layout, title, on_settings=None):
    toolbar = QtWidgets.QHBoxLayout()
    title_lbl = QtWidgets.QLabel(_as_text(title))
    title_lbl.setStyleSheet(u"font-size: 13px; font-weight: bold;")
    toolbar.addWidget(title_lbl)
    toolbar.addStretch()
    if on_settings is not None:
        settings_btn = QtWidgets.QPushButton(u"设置")
        settings_btn.clicked.connect(on_settings)
        toolbar.addWidget(settings_btn)
    layout.addLayout(toolbar)
    return toolbar


def _open_tool_settings(parent, dialog_cls, on_saved=None):
    from ui.rm_config_io import load_config, save_config

    cfg = load_config()
    dlg = dialog_cls(cfg, parent=parent)
    if dlg.exec_() != QtWidgets.QDialog.Accepted:
        return None
    new_cfg = dlg.get_config()
    if not save_config(new_cfg):
        QtWidgets.QMessageBox.warning(parent, u"保存失败", u"设置已修改，但写入配置文件失败。")
        return None
    if on_saved is not None:
        on_saved(new_cfg)
    return new_cfg


def _show_singleton(key, factory):
    win = _WINDOWS.get(key)
    if win is not None:
        try:
            win.raise_()
            win.activateWindow()
            win.showNormal()
            return win
        except Exception:
            _WINDOWS.pop(key, None)
    win = factory()
    _WINDOWS[key] = win
    win.show()
    return win


def show_weapon_panel():
    def _build():
        from ui.rm_weapon_state_panel import WeaponStatePanel
        from ui.rm_tool_settings import WeaponStateSettingsDialog

        dlg = _base_dialog(u"武器约束")
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        def _open_settings():
            _open_tool_settings(dlg, WeaponStateSettingsDialog)

        _add_tool_toolbar(lay, u"武器约束", on_settings=_open_settings)
        panel = WeaponStatePanel(dlg)
        lay.addWidget(panel, 1)
        rt = _get_rt()
        panel.bind_runtime(rt)
        return dlg

    return _show_singleton(u"weapon", _build)


def show_binding_update():
    def _build():
        from anim_migration.ui.tab_binding_update import BindingUpdateTab, UI_VERSION
        from ui.rm_config_io import load_config
        from ui.rm_tool_settings import BindingUpdateSettingsDialog

        title = u"绑定更新 {0}".format(UI_VERSION) if UI_VERSION else u"绑定更新"
        dlg = _base_dialog(title, (720, 760))
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        panel = BindingUpdateTab(dlg, rt=_get_rt())
        cfg = load_config()
        panel.on_config_updated(cfg)

        def _open_settings():
            def _on_saved(new_cfg):
                panel.on_config_updated(new_cfg)

            _open_tool_settings(dlg, BindingUpdateSettingsDialog, on_saved=_on_saved)

        _add_tool_toolbar(lay, title, on_settings=_open_settings)
        lay.addWidget(panel, 1)
        return dlg

    return _show_singleton(u"binding", _build)


def show_shot_assist():
    def _build():
        from ui.rm_shot_assist_panel import ShotAssistPanel
        from ui.rm_tool_settings import ShotAssistSettingsDialog

        dlg = _base_dialog(u"相机功能", (480, 720))
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        def _open_settings():
            _open_tool_settings(dlg, ShotAssistSettingsDialog)

        _add_tool_toolbar(lay, u"相机功能", on_settings=_open_settings)
        panel = ShotAssistPanel(dlg)
        lay.addWidget(panel, 1)
        panel.bind_runtime(_get_rt())
        return dlg

    return _show_singleton(u"shot", _build)


def show_publish_tool(anim_type=None):
    """
    打开正式发布工具（仅 FBX 发布页，ProxyRoot）。
    anim_type: 'indoor' / 'outdoor' / None（按当前文件名自动判断）
    """
    from ui.rm_main_window import MainWindow
    win = _show_singleton(
        u"publish",
        lambda: MainWindow(
            parent=None, mode=u"publish_only", com_restore_engine=u"baselayer"
        ),
    )
    try:
        if anim_type == u"indoor":
            win._type_indoor.setChecked(True)
        elif anim_type == u"outdoor":
            win._type_outdoor.setChecked(True)
        else:
            win._auto_select_publish_type_from_scene()
    except Exception:
        pass
    try:
        win._refresh_publish_state_from_scene()
    except Exception:
        pass
    return win


def show_publish_baselayer_tool(anim_type=None):
    """兼容旧实验调用名；当前与正式 ProxyRoot 发布入口相同。"""
    return show_publish_tool(anim_type)


def show_publish_legacy_tool(anim_type=None):
    """隐藏的 Legacy/RM_Fix 备份入口，不注册到动画师菜单。"""
    from ui.rm_main_window import MainWindow
    win = _show_singleton(
        u"publish_legacy",
        lambda: MainWindow(
            parent=None, mode=u"publish_only", com_restore_engine=u"legacy"
        ),
    )
    try:
        if anim_type == u"indoor":
            win._type_indoor.setChecked(True)
        elif anim_type == u"outdoor":
            win._type_outdoor.setChecked(True)
        else:
            win._auto_select_publish_type_from_scene()
    except Exception:
        pass
    try:
        win._refresh_publish_state_from_scene()
    except Exception:
        pass
    return win


def detect_publish_type_from_filename(filename, config=None):
    """根据文件名判断局内/局外。"""
    from pipeline.rm_naming import validate_indoor_name, validate_outdoor_name
    name = _as_text(filename)
    if not name:
        return None
    base = os.path.splitext(name)[0]
    cfg = config or {}
    ok_in, _, _ = validate_indoor_name(base, cfg.get(u"category_folder_map"))
    if ok_in:
        return u"indoor"
    ok_out, _, _ = validate_outdoor_name(
        base,
        cfg.get(u"module_folder_map"),
        cfg.get(u"outdoor_type_folder_map"),
        cfg.get(u"outdoor_asset_types"),
        cfg.get(u"category_folder_map"),
    )
    if ok_out:
        return u"outdoor"
    return None


def show_publish_from_scene():
    rt = _get_rt()
    filename = _as_text(rt.maxFileName) if rt is not None else u""
    cfg = {}
    try:
        from ui.rm_config_io import load_config
        cfg = load_config() or {}
    except Exception:
        cfg = {}
    anim_type = detect_publish_type_from_filename(filename, cfg)
    return show_publish_tool(anim_type)


def show_publish_baselayer_from_scene():
    """兼容旧实验调用名；当前与正式入口相同。"""
    return show_publish_from_scene()


def show_publish_legacy_from_scene():
    """按当前文件名打开隐藏的 Legacy/RM_Fix 备份发布器。"""
    rt = _get_rt()
    filename = _as_text(rt.maxFileName) if rt is not None else u""
    cfg = {}
    try:
        from ui.rm_config_io import load_config
        cfg = load_config() or {}
    except Exception:
        cfg = {}
    anim_type = detect_publish_type_from_filename(filename, cfg)
    return show_publish_legacy_tool(anim_type)

# -*- coding: utf-8 -*-
"""各独立工具的专属设置弹窗。"""
from __future__ import print_function
from PySide2 import QtWidgets, QtCore

from ui.rm_theme import apply_dark_theme

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
        return u""


class _BaseToolSettingsDialog(QtWidgets.QDialog):
    def __init__(self, config, title, parent=None):
        super(_BaseToolSettingsDialog, self).__init__(parent)
        self.setWindowTitle(_as_text(title))
        self.setMinimumSize(480, 320)
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self._config = dict(config or {})
        self._build_ui()
        apply_dark_theme(self)
        self._load_to_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self._body = QtWidgets.QVBoxLayout()
        self._body.setSpacing(10)
        layout.addLayout(self._body, 1)
        self._populate_body(self._body)
        layout.addStretch(0)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet(u"color: #444;")
        layout.addWidget(sep)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QtWidgets.QPushButton(u"取消")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QtWidgets.QPushButton(u"保存设置")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(
            u"QPushButton {"
            u"  background: #2d4a6a; color: white;"
            u"  padding: 7px 18px; border-radius: 4px;"
            u"}"
            u"QPushButton:hover { background: #3d5a8a; }"
        )
        ok_btn.clicked.connect(self._on_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _populate_body(self, layout):
        raise NotImplementedError

    def _load_to_ui(self):
        raise NotImplementedError

    def _on_save(self):
        raise NotImplementedError

    def _make_check_group(self, title, widgets):
        group = QtWidgets.QGroupBox(title)
        lay = QtWidgets.QVBoxLayout(group)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        for widget in widgets:
            lay.addWidget(widget)
        return group

    def _browse_dir(self, line_edit):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, u"选择路径", line_edit.text()
        )
        if path:
            line_edit.setText(path)

    def get_config(self):
        return self._config


class BindingUpdateSettingsDialog(_BaseToolSettingsDialog):
    def __init__(self, config, parent=None):
        super(BindingUpdateSettingsDialog, self).__init__(
            config, u"绑定更新设置", parent=parent
        )
        self.setMinimumSize(520, 380)

    def _populate_body(self, layout):
        hint = QtWidgets.QLabel(
            u"这些选项只影响绑定更新流程，保存后写入本机 rm_config.json。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(u"color: #aaa; font-size: 11px;")
        layout.addWidget(hint)

        path_group = QtWidgets.QGroupBox(u"路径")
        path_lay = QtWidgets.QFormLayout(path_group)
        path_lay.setSpacing(10)
        path_lay.setContentsMargins(12, 12, 12, 12)
        row = QtWidgets.QHBoxLayout()
        self._character_rig_root_edit = QtWidgets.QLineEdit()
        browse = QtWidgets.QPushButton(u"浏览…")
        browse.setFixedWidth(88)
        browse.clicked.connect(lambda: self._browse_dir(self._character_rig_root_edit))
        row.addWidget(self._character_rig_root_edit)
        row.addWidget(browse)
        path_lay.addRow(u"角色/绑定资源根路径：", row)
        layout.addWidget(path_group)

        self._rig_update_cleanup_chk = QtWidgets.QCheckBox(u"绑定更新成功后清理迁移包")
        self._rig_update_keep_reports_chk = QtWidgets.QCheckBox(u"清理迁移包前保留报告到备份旁")
        layout.addWidget(self._make_check_group(u"绑定更新", [
            self._rig_update_cleanup_chk,
            self._rig_update_keep_reports_chk,
        ]))

    def _load_to_ui(self):
        self._character_rig_root_edit.setText(
            self._config.get(
                u"character_rig_root",
                self._config.get(
                    u"rig_bindings_root",
                    u"",
                ),
            )
        )
        self._rig_update_cleanup_chk.setChecked(
            self._config.get(u"rig_update_cleanup_packages", False)
        )
        self._rig_update_keep_reports_chk.setChecked(
            self._config.get(u"rig_update_keep_reports", True)
        )

    def _on_save(self):
        self._config[u"character_rig_root"] = _as_text(
            self._character_rig_root_edit.text()
        ).strip()
        self._config[u"rig_update_cleanup_packages"] = bool(
            self._rig_update_cleanup_chk.isChecked()
        )
        self._config[u"rig_update_keep_reports"] = bool(
            self._rig_update_keep_reports_chk.isChecked()
        )
        self.accept()


class WeaponStateSettingsDialog(_BaseToolSettingsDialog):
    def __init__(self, config, parent=None):
        super(WeaponStateSettingsDialog, self).__init__(
            config, u"武器约束设置", parent=parent
        )
        self.setMinimumSize(480, 260)

    def _populate_body(self, layout):
        hint = QtWidgets.QLabel(
            u"武器状态相关选项。导出映射会在发布 FBX 时同步写出 JSON，"
            u"供 Unity WeaponConstraintConfig 使用。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(u"color: #aaa; font-size: 11px;")
        layout.addWidget(hint)

        self._adv_weapon_map_chk = QtWidgets.QCheckBox(
            u"导出 FBX 时同步写出武器状态映射 JSON（与 Unity WeaponConstraintConfig 配套）"
        )
        layout.addWidget(self._make_check_group(u"武器状态", [
            self._adv_weapon_map_chk,
        ]))

    def _load_to_ui(self):
        self._adv_weapon_map_chk.setChecked(
            self._config.get(u"adv_export_weapon_state_mapping", True)
        )

    def _on_save(self):
        self._config[u"adv_export_weapon_state_mapping"] = bool(
            self._adv_weapon_map_chk.isChecked()
        )
        self.accept()


class ShotAssistSettingsDialog(_BaseToolSettingsDialog):
    def __init__(self, config, parent=None):
        super(ShotAssistSettingsDialog, self).__init__(
            config, u"相机功能设置", parent=parent
        )
        self.setMinimumSize(420, 220)

    def _populate_body(self, layout):
        hint = QtWidgets.QLabel(
            u"构图辅助线的类型、距离、透明度等参数在主界面直接调整。\n"
            u"当前无需额外持久化设置。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(u"color: #aaa; font-size: 11px;")
        layout.addWidget(hint)

    def _load_to_ui(self):
        pass

    def _on_save(self):
        self.accept()

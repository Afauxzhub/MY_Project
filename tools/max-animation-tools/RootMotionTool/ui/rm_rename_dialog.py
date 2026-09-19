# -*- coding: utf-8 -*-
"""
命名修复弹窗
当文件名不符合规范时弹出，动画师可实时修改并通过校验后继续导出。
"""
from __future__ import print_function
from PySide2 import QtWidgets, QtCore, QtGui

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


class RenameDialog(QtWidgets.QDialog):
    """
    命名不合规弹窗。
    accept() → 用户确认了合法名称
    reject() → 用户取消导出
    """

    def __init__(
        self,
        current_name,
        anim_type,
        parent=None,
        module_folder_map=None,
        category_folder_map=None,
        outdoor_type_folder_map=None,
        outdoor_asset_types=None,
    ):
        """
        current_name : 当前（不合规的）文件名，不含扩展名
        anim_type    : 'indoor' 或 'outdoor'
        其余映射参数来自工具设置，用于实时校验与提示。
        """
        super(RenameDialog, self).__init__(parent)
        self.setWindowTitle(u"命名不规范 — 请修改后继续")
        self.setMinimumWidth(520)
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self._anim_type = anim_type
        self._module_folder_map = module_folder_map
        self._category_folder_map = category_folder_map
        self._outdoor_type_folder_map = outdoor_type_folder_map
        self._outdoor_asset_types = outdoor_asset_types
        self._result_name = current_name
        self._build_ui(current_name)
        self._validate(current_name)

    # ── UI 构建 ───────────────────────────────────────────────────

    def _build_ui(self, current_name):
        from pipeline.rm_naming import (
            indoor_categories_from_map,
            merge_module_folder_map,
            merge_type_folder_map,
            normalize_outdoor_asset_types,
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # 警告标题
        warn = QtWidgets.QLabel(
            u"⚠  当前文件名不符合命名规范，请修改后点击「确认继续导出」"
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(
            u"color: #e8a000; font-weight: bold; "
            u"background: #2a2200; padding: 8px; border-radius: 4px;"
        )
        layout.addWidget(warn)

        # 原文件名展示
        orig_row = QtWidgets.QHBoxLayout()
        orig_row.addWidget(QtWidgets.QLabel(u"原文件名："))
        orig_lbl = QtWidgets.QLabel(current_name)
        orig_lbl.setStyleSheet(u"color: #888; font-family: Consolas;")
        orig_row.addWidget(orig_lbl)
        orig_row.addStretch()
        layout.addLayout(orig_row)

        # 输入区
        input_group = QtWidgets.QGroupBox(u"新文件名（不含扩展名）")
        input_layout = QtWidgets.QVBoxLayout(input_group)

        self._name_edit = QtWidgets.QLineEdit(current_name)
        self._name_edit.setFont(QtGui.QFont(u"Consolas", 11))
        self._name_edit.setPlaceholderText(u"在此输入修改后的文件名")
        self._name_edit.textChanged.connect(self._validate)
        input_layout.addWidget(self._name_edit)

        # 错误信息行
        self._error_lbl = QtWidgets.QLabel()
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setMinimumHeight(20)
        input_layout.addWidget(self._error_lbl)

        # 格式提示（读当前设置白名单）
        if self._anim_type == u"indoor":
            cats = indoor_categories_from_map(self._category_folder_map)
            hint_text = (
                u"个人格式：<b>角色_动作集_动作</b>，动作集可省略。<br>"
                u"示例：Player_Unarmed_Run　|　Player_Sword_Idle　|　Wolf_Run<br>"
                u"动作集不限制为 Unarmed/Armed；武器类型按需要命名。分类与制作阶段不进入个人名称。<br>"
                u"旧格式仍兼容 分类_角色_动作(_阶段)，保留分类：{0}"
            ).format(u"、".join(cats))
        else:
            modules = sorted(merge_module_folder_map(self._module_folder_map).keys())
            types = sorted(set(
                list(merge_type_folder_map(self._outdoor_type_folder_map).keys())
                + list(indoor_categories_from_map(self._category_folder_map))
            ))
            assets = normalize_outdoor_asset_types(self._outdoor_asset_types)
            hint_text = (
                u"局外格式：<b>模块_类型或分类_角色/场次_镜头或资产类型</b><br>"
                u"示例：UL_Role_Hero_Cam01　|　CS_Monster_Creature_Cam　|　EN_Chap01_SC01_Char<br>"
                u"模块（设置→局外模块映射）：{0}<br>"
                u"类型/分类（另支持 Chap01…）：{1}<br>"
                u"镜头/资产类型：Cam01… 或 {2}"
            ).format(u"、".join(modules), u"、".join(types), u"、".join(assets))
        hint = QtWidgets.QLabel(hint_text)
        hint.setWordWrap(True)
        hint.setStyleSheet(u"color: #777; font-size: 11px;")
        input_layout.addWidget(hint)

        layout.addWidget(input_group)

        # 按钮
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QtWidgets.QPushButton(u"取消导出")
        cancel_btn.setStyleSheet(
            u"QPushButton { padding: 7px 18px; border-radius: 4px; }"
        )
        cancel_btn.clicked.connect(self.reject)

        self._ok_btn = QtWidgets.QPushButton(u"确认继续导出")
        self._ok_btn.setDefault(True)
        self._ok_btn.setStyleSheet(
            u"QPushButton {"
            u"  background: #2d6a2d; color: white;"
            u"  padding: 7px 18px; border-radius: 4px;"
            u"}"
            u"QPushButton:hover   { background: #3d8a3d; }"
            u"QPushButton:disabled { background: #3a3a3a; color: #666; }"
        )
        self._ok_btn.clicked.connect(self._on_accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._ok_btn)
        layout.addLayout(btn_row)

    # ── 校验逻辑 ─────────────────────────────────────────────────

    def _validate(self, text=None):
        if text is None:
            text = self._name_edit.text()

        from pipeline.rm_naming import validate_indoor_name, validate_outdoor_name
        if self._anim_type == u"indoor":
            is_valid, msg, _ = validate_indoor_name(
                text, self._category_folder_map
            )
        else:
            is_valid, msg, _ = validate_outdoor_name(
                text,
                self._module_folder_map,
                self._outdoor_type_folder_map,
                self._outdoor_asset_types,
                self._category_folder_map,
            )

        if is_valid:
            self._name_edit.setStyleSheet(
                u"border: 2px solid #3d8a3d; border-radius: 4px;"
                u"padding: 4px; color: #6dcc6d; font-family: Consolas;"
            )
            self._error_lbl.setText(u"✓  命名合规")
            self._error_lbl.setStyleSheet(u"color: #6dcc6d;")
            self._ok_btn.setEnabled(True)
            self._result_name = text
        else:
            self._name_edit.setStyleSheet(
                u"border: 2px solid #cc3d3d; border-radius: 4px;"
                u"padding: 4px; color: #ff9090; font-family: Consolas;"
            )
            self._error_lbl.setText(u"✗  " + msg)
            self._error_lbl.setStyleSheet(u"color: #ff6060;")
            self._ok_btn.setEnabled(False)

    def _on_accept(self):
        self._result_name = self._name_edit.text()
        self.accept()

    # ── 公开接口 ─────────────────────────────────────────────────

    def get_new_name(self):
        """返回用户确认的合规文件名（不含扩展名）"""
        return self._result_name

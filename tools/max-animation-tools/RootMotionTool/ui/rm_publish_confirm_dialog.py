# -*- coding: utf-8 -*-
"""角色级发布阶段选择与风险二次确认弹窗。"""
from __future__ import division
from PySide2 import QtWidgets, QtCore

from pipeline.publish_public_lookup import (
    build_review_version_options,
    classify_publish_stage,
    make_stage_state,
)


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


def _risk_message(risk, selected_label, character_label):
    if risk == u"earlier":
        reason = u"当前发布动作选择的阶段早于公盘中该角色的最新阶段。"
    elif risk == u"too_far_ahead":
        reason = u"当前发布动作比公盘中该角色的最新阶段晚两个或两个以上阶段。"
    else:
        reason = u"公盘中尚无该角色的动作，首次发布通常应从初版开始。"
    return (
        u"{0}\n\n"
        u"当前动作选择：{1}\n"
        u"当前角色阶段：{2}\n\n"
        u"请确认本次发布方式。"
    ).format(reason, selected_label, character_label)


def ask_stage_risk_confirmation(parent, risk, selected_state, character_stage):
    """风险阶段的三选一确认；返回 selected / character / cancel。"""
    character_target = character_stage or make_stage_state(u"初版")
    selected_label = selected_state[u"label"]
    character_label = (
        character_stage[u"label"] if character_stage else u"尚未发布（应从初版开始）"
    )

    dlg = QtWidgets.QMessageBox(parent)
    dlg.setWindowTitle(u"发布阶段风险确认")
    dlg.setIcon(QtWidgets.QMessageBox.Warning)
    dlg.setText(_risk_message(risk, selected_label, character_label))
    selected_btn = dlg.addButton(
        u"忽略警告，按 {0} 发布".format(selected_label),
        QtWidgets.QMessageBox.AcceptRole,
    )
    character_btn = dlg.addButton(
        u"改为 {0} 并发布".format(character_target[u"label"]),
        QtWidgets.QMessageBox.ActionRole,
    )
    cancel_btn = dlg.addButton(u"取消发布", QtWidgets.QMessageBox.RejectRole)
    dlg.setDefaultButton(cancel_btn)
    dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
    dlg.exec_()
    clicked = dlg.clickedButton()
    if clicked is selected_btn:
        return u"selected"
    if clicked is character_btn:
        return u"character"
    return u"cancel"


class PublishStageDialog(QtWidgets.QDialog):
    """显示角色阶段，并允许在发布前修改当前动作阶段。"""

    def __init__(
        self,
        selected_stage=u"初版",
        selected_version=u"",
        character_stage=None,
        parent=None,
    ):
        super(PublishStageDialog, self).__init__(parent)
        self._character_stage = character_stage
        self._result_stage = u""
        self._result_version = u""
        self.setWindowTitle(u"确认发布阶段")
        self.setMinimumWidth(470)
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self._build_ui(selected_stage, selected_version)

    def _build_ui(self, selected_stage, selected_version):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)

        character_label = (
            self._character_stage[u"label"]
            if self._character_stage else u"尚未发布"
        )
        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        row_font = self.font()
        row_font.setPointSize(10)
        row_height = 30

        self._character_stage_label = QtWidgets.QLabel(u"当前角色阶段：")
        self._character_stage_label.setFont(row_font)
        self._character_stage_label.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        self._character_stage_value = QtWidgets.QLabel(character_label)
        self._character_stage_value.setFont(row_font)
        self._character_stage_value.setMinimumHeight(row_height)
        self._character_stage_value.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        form.addRow(self._character_stage_label, self._character_stage_value)

        self._publish_stage_label = QtWidgets.QLabel(u"本次发布阶段：")
        self._publish_stage_label.setFont(row_font)
        self._publish_stage_label.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        self._stage_combo = QtWidgets.QComboBox()
        self._stage_combo.setFont(row_font)
        self._stage_combo.setMinimumHeight(row_height)
        self._stage_combo.addItems([u"初版", u"终版", u"监修"])
        form.addRow(self._publish_stage_label, self._stage_combo)

        self._version_label = QtWidgets.QLabel(u"监修子版本号：")
        self._version_label.setFont(row_font)
        self._version_label.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        self._version_combo = QtWidgets.QComboBox()
        self._version_combo.setFont(row_font)
        self._version_combo.setMinimumHeight(row_height)
        self._version_combo.setEditable(False)
        self._version_combo.addItems(build_review_version_options())
        form.addRow(self._version_label, self._version_combo)
        layout.addLayout(form)

        stage_idx = self._stage_combo.findText(_as_text(selected_stage).strip())
        self._stage_combo.setCurrentIndex(stage_idx if stage_idx >= 0 else 0)
        version_idx = self._version_combo.findText(_as_text(selected_version).strip())
        self._version_combo.setCurrentIndex(version_idx if version_idx >= 0 else 0)
        self._stage_combo.currentIndexChanged.connect(self._update_version_ui)
        self._update_version_ui()

        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(12)
        button_row.addStretch(1)
        cancel_btn = QtWidgets.QPushButton(u"取消")
        cancel_btn.setMinimumSize(96, 32)
        cancel_btn.clicked.connect(self.reject)
        publish_btn = QtWidgets.QPushButton(u"发布")
        publish_btn.setMinimumSize(96, 32)
        publish_btn.setDefault(True)
        publish_btn.clicked.connect(self._on_publish)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(publish_btn)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    def _update_version_ui(self, *args):
        is_review = self._stage_combo.currentText() == u"监修"
        self._version_label.setEnabled(is_review)
        self._version_combo.setEnabled(is_review)
        if is_review:
            if self._version_combo.currentIndex() < 0:
                self._version_combo.setCurrentIndex(0)
        else:
            self._version_combo.setCurrentIndex(-1)

    def _selected_state(self):
        stage = _as_text(self._stage_combo.currentText()).strip() or u"初版"
        version = (
            _as_text(self._version_combo.currentText()).strip()
            if stage == u"监修" else u""
        )
        return make_stage_state(stage, version)

    def _accept_state(self, state):
        self._result_stage = state[u"stage"]
        self._result_version = state[u"version"]
        self.accept()

    def _on_publish(self):
        selected = self._selected_state()
        risk = classify_publish_stage(
            selected[u"stage"], selected[u"version"], self._character_stage
        )
        if risk == u"normal":
            self._accept_state(selected)
            return

        action = ask_stage_risk_confirmation(
            self, risk, selected, self._character_stage
        )
        if action == u"selected":
            self._accept_state(selected)
        elif action == u"character":
            self._accept_state(self._character_stage or make_stage_state(u"初版"))
        else:
            self.reject()

    def get_stage(self):
        return self._result_stage, self._result_version


def ask_publish_confirm(
    parent,
    selected_stage=u"初版",
    selected_version=u"",
    character_stage=None,
):
    """返回 (accepted, stage, version)。"""
    dlg = PublishStageDialog(
        selected_stage=selected_stage,
        selected_version=selected_version,
        character_stage=character_stage,
        parent=parent,
    )
    if dlg.exec_() != QtWidgets.QDialog.Accepted:
        return False, u"", u""
    stage, version = dlg.get_stage()
    return True, stage, version

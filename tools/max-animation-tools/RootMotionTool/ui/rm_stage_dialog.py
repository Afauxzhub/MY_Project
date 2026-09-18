# -*- coding: utf-8 -*-
"""
公盘备份阶段选择弹窗
兼容阶段选择弹窗；监修阶段只允许选择整数递增子版本。
"""
from __future__ import print_function
from PySide2 import QtWidgets, QtCore


class StageDialog(QtWidgets.QDialog):
    """
    阶段选择弹窗。
    accept() → 用户确认备份
    reject() → 用户跳过本次公盘备份
    """

    def __init__(self, auto_detected_stage=None, parent=None):
        """
        auto_detected_stage : '初版' / '终版' / None（无法识别时）
        """
        super(StageDialog, self).__init__(parent)
        self.setWindowTitle(u"选择公盘备份阶段")
        self.setMinimumWidth(340)
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self._build_ui(auto_detected_stage)

    # ── UI 构建 ───────────────────────────────────────────────────

    def _build_ui(self, auto_stage):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # 提示说明
        title = QtWidgets.QLabel(u"请选择本次 MAX 文件备份到公盘的制作阶段：")
        title.setStyleSheet(u"font-weight: bold;")
        layout.addWidget(title)

        if auto_stage:
            hint = QtWidgets.QLabel(
                u"（已根据文件名自动识别为：<b>{0}</b>，可手动修改）".format(auto_stage)
            )
            hint.setStyleSheet(u"color: #aaa; font-size: 11px;")
            layout.addWidget(hint)

        # 单选组
        self._btn_group = QtWidgets.QButtonGroup(self)
        self._r_initial = QtWidgets.QRadioButton(u"初版（仅保留最新，直接覆盖同名文件）")
        self._r_final   = QtWidgets.QRadioButton(u"终版（仅保留最新，直接覆盖同名文件）")
        self._r_review  = QtWidgets.QRadioButton(u"监修（按版本号建立子文件夹，分版本存档）")

        self._btn_group.addButton(self._r_initial)
        self._btn_group.addButton(self._r_final)
        self._btn_group.addButton(self._r_review)

        layout.addWidget(self._r_initial)
        layout.addWidget(self._r_final)
        layout.addWidget(self._r_review)

        # 监修版本号行（仅监修时可用）
        version_widget = QtWidgets.QWidget()
        version_layout = QtWidgets.QHBoxLayout(version_widget)
        version_layout.setContentsMargins(24, 0, 0, 0)
        self._version_label = QtWidgets.QLabel(u"监修子版本：")
        version_layout.addWidget(self._version_label)
        from pipeline.publish_public_lookup import build_review_version_options
        self._version_combo = QtWidgets.QComboBox()
        self._version_combo.setEditable(False)
        self._version_combo.addItems(build_review_version_options())
        self._version_combo.setEnabled(False)
        version_layout.addWidget(self._version_combo)
        version_layout.addStretch()
        layout.addWidget(version_widget)

        self._r_review.toggled.connect(self._update_version_ui)

        # 分割线
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet(u"color: #444;")
        layout.addWidget(sep)

        # 按钮行
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        skip_btn = QtWidgets.QPushButton(u"跳过备份")
        skip_btn.setStyleSheet(u"QPushButton { padding: 7px 16px; border-radius: 4px; }")
        skip_btn.clicked.connect(self.reject)

        ok_btn = QtWidgets.QPushButton(u"确认备份到公盘")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(
            u"QPushButton {"
            u"  background: #2d4a6a; color: white;"
            u"  padding: 7px 16px; border-radius: 4px;"
            u"}"
            u"QPushButton:hover { background: #3d5a8a; }"
        )
        ok_btn.clicked.connect(self._on_accept)

        btn_row.addWidget(skip_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        # 预填自动识别阶段
        if auto_stage == u"初版":
            self._r_initial.setChecked(True)
        elif auto_stage == u"终版":
            self._r_final.setChecked(True)
        else:
            self._r_initial.setChecked(True)
        self._update_version_ui(self._r_review.isChecked())

    # ── 槽函数 ────────────────────────────────────────────────────

    def _update_version_ui(self, is_review):
        self._version_label.setEnabled(bool(is_review))
        self._version_combo.setEnabled(bool(is_review))
        if is_review:
            if self._version_combo.currentIndex() < 0:
                self._version_combo.setCurrentIndex(0)
        else:
            self._version_combo.setCurrentIndex(-1)

    def _on_accept(self):
        if self._r_review.isChecked():
            version = self._version_combo.currentText().strip()
            if not version:
                QtWidgets.QMessageBox.warning(
                    self, u"提示", u"请选择监修子版本（如 1.0、2.0）"
                )
                return
        self.accept()

    # ── 公开接口 ─────────────────────────────────────────────────

    def get_stage(self):
        """
        返回 (stage, version)
          stage   : '初版' / '终版' / '监修'
          version : 监修版本号字符串（如 '2.0'），初版/终版时为 None
        """
        if self._r_initial.isChecked():
            return u"初版", None
        elif self._r_final.isChecked():
            return u"终版", None
        else:
            return u"监修", self._version_combo.currentText().strip()

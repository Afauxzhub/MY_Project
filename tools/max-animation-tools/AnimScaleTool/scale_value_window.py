# -*- coding: utf-8 -*-
"""缩放值工具界面。"""
from __future__ import division
import os

from PySide2 import QtCore, QtWidgets

import scale_keys

try:
    _text_type = unicode
except NameError:
    _text_type = str

_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_CHECKBOX_CHECKED_ICON = os.path.join(_TOOL_DIR, u"icons", u"checkbox_checked.svg").replace(u"\\", u"/")


class ScaleValueWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(ScaleValueWindow, self).__init__(parent)
        self.setWindowTitle(u"缩放值")
        self.setMinimumWidth(420)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self._build_ui()
        self._apply_styles()
        self._selection_timer = QtCore.QTimer(self)
        self._selection_timer.setInterval(500)
        self._selection_timer.timeout.connect(self._refresh_selection_label)
        self._selection_timer.start()
        self._refresh_selection_label()

    def _apply_styles(self):
        self.setStyleSheet(
            u"QDialog, QWidget { background:#2b2b2b; color:#e0e0e0; }"
            u"QLabel { color:#d8d8d8; }"
            u"QLineEdit, QSpinBox, QDoubleSpinBox {"
            u"  background:#3a3a3a; color:#f0f0f0; border:1px solid #666;"
            u"  padding:2px 6px; min-height:20px; }"
            u"QSpinBox::up-button, QSpinBox::down-button { width:16px; }"
            u"QCheckBox, QRadioButton { color:#e0e0e0; spacing:8px; }"
            u"QCheckBox::indicator { width:14px; height:14px; }"
            u"QCheckBox::indicator:unchecked {"
            u"  border:1px solid #888; background:#353535; }"
            u"QCheckBox::indicator:checked { border:none; image:url(" + _CHECKBOX_CHECKED_ICON + u"); }"
            u"QRadioButton::indicator {"
            u"  width:14px; height:14px; border:1px solid #888; background:#353535;"
            u"  border-radius:8px; }"
            u"QRadioButton::indicator:checked {"
            u"  border:1px solid #bbb; background:#e0e0e0; }"
            u"QPushButton { background:#3d3d3d; color:#e0e0e0; border:1px solid #666; padding:6px 16px; }"
            u"QPushButton:hover { background:#4d4d4d; }"
            u"QPushButton#startButton {"
            u"  background:#2f6f9f; color:#ffffff; border:1px solid #3d84b8;"
            u"  padding:8px 32px; font-weight:bold; min-width:96px; }"
            u"QPushButton#startButton:hover { background:#3a84b8; }"
            u"QPushButton#startButton:pressed { background:#255a80; }"
        )

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self._object_label = QtWidgets.QLabel(u"（未选中对象）")
        self._object_label.setWordWrap(True)
        self._object_label.setStyleSheet(u"font-weight:bold; color:#f0f0f0;")
        root.addWidget(self._object_label)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFormAlignment(QtCore.Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)

        self._percent_spn = self._make_percent_spinbox()
        form.addRow(u"缩放值", self._left_align_widget(self._percent_spn))

        type_wrap = QtWidgets.QHBoxLayout()
        type_wrap.setSpacing(16)
        self._pos_chk = QtWidgets.QCheckBox(u"位移")
        self._rot_chk = QtWidgets.QCheckBox(u"旋转")
        self._scl_chk = QtWidgets.QCheckBox(u"缩放")
        self._pos_chk.setChecked(True)
        for chk in (self._pos_chk, self._rot_chk, self._scl_chk):
            type_wrap.addWidget(chk)
        type_wrap.addStretch()
        form.addRow(u"缩放类型", self._wrap_row(type_wrap))

        axis_wrap = QtWidgets.QHBoxLayout()
        axis_wrap.setSpacing(16)
        self._axis_x_chk = QtWidgets.QCheckBox(u"X")
        self._axis_y_chk = QtWidgets.QCheckBox(u"Y")
        self._axis_z_chk = QtWidgets.QCheckBox(u"Z")
        for chk in (self._axis_x_chk, self._axis_y_chk, self._axis_z_chk):
            chk.setChecked(True)
            axis_wrap.addWidget(chk)
        axis_wrap.addStretch()
        form.addRow(u"缩放轴向", self._wrap_row(axis_wrap))

        pivot_wrap = QtWidgets.QHBoxLayout()
        pivot_wrap.setSpacing(12)
        self._pivot_mid_radio = QtWidgets.QRadioButton(u"中值")
        self._pivot_frame_radio = QtWidgets.QRadioButton(u"指定帧")
        self._pivot_mid_radio.setChecked(True)
        self._pivot_frame_spn = self._make_frame_spinbox()
        self._pivot_frame_spn.setEnabled(False)
        pivot_wrap.addWidget(self._pivot_mid_radio)
        pivot_wrap.addWidget(self._pivot_frame_radio)
        pivot_wrap.addWidget(self._pivot_frame_spn)
        pivot_wrap.addWidget(QtWidgets.QLabel(u"帧数值"))
        pivot_wrap.addStretch()
        self._pivot_group = QtWidgets.QButtonGroup(self)
        self._pivot_group.setExclusive(True)
        self._pivot_group.addButton(self._pivot_mid_radio)
        self._pivot_group.addButton(self._pivot_frame_radio)
        self._pivot_mid_radio.toggled.connect(self._on_pivot_mode_changed)
        self._pivot_frame_spn.valueChanged.connect(self._on_pivot_frame_spin_changed)
        form.addRow(u"缩放基准", self._wrap_row(pivot_wrap))

        range_wrap = QtWidgets.QHBoxLayout()
        range_wrap.setSpacing(8)
        self._start_spn = self._make_frame_spinbox()
        self._end_spn = self._make_frame_spinbox()
        range_wrap.addWidget(QtWidgets.QLabel(u"开始"))
        range_wrap.addWidget(self._start_spn)
        range_wrap.addSpacing(8)
        range_wrap.addWidget(QtWidgets.QLabel(u"结束"))
        range_wrap.addWidget(self._end_spn)
        range_wrap.addStretch()
        form.addRow(u"缩放区间", self._wrap_row(range_wrap))

        root.addLayout(form)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        start_btn = QtWidgets.QPushButton(u"开始")
        start_btn.setObjectName(u"startButton")
        start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(start_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

    def _spinbox_content_width(self, sample_text):
        metrics = QtWidgets.QApplication.fontMetrics()
        return metrics.width(sample_text) + 34

    def _make_percent_spinbox(self):
        spn = QtWidgets.QSpinBox()
        spn.setRange(0, 100)
        spn.setValue(100)
        spn.setAlignment(QtCore.Qt.AlignRight)
        spn.setFixedWidth(self._spinbox_content_width(u"100"))
        spn.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed,
            QtWidgets.QSizePolicy.Fixed,
        )
        return spn

    def _make_frame_spinbox(self):
        spn = QtWidgets.QSpinBox()
        spn.setRange(-999999, 999999)
        spn.setValue(0)
        spn.setAlignment(QtCore.Qt.AlignRight)
        spn.setFixedWidth(self._spinbox_content_width(u"-999999"))
        spn.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed,
            QtWidgets.QSizePolicy.Fixed,
        )
        return spn

    def _left_align_widget(self, widget):
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(widget)
        row.addStretch()
        return self._wrap_row(row)

    def _wrap_row(self, layout):
        wrap = QtWidgets.QWidget()
        wrap.setLayout(layout)
        return wrap

    def _on_pivot_mode_changed(self):
        use_frame = self._pivot_frame_radio.isChecked()
        self._pivot_frame_spn.setEnabled(use_frame)

    def _on_pivot_frame_spin_changed(self, *_):
        if not self._pivot_frame_radio.isChecked():
            self._pivot_frame_radio.setChecked(True)

    def _refresh_selection_label(self):
        try:
            get_nodes = getattr(scale_keys, "get_selected_nodes", None)
            get_name = getattr(scale_keys, "get_display_object_name", None)
            if not callable(get_nodes) or not callable(get_name):
                return
            nodes = get_nodes()
            self._object_label.setText(
                u"选中对象：{0}".format(get_name(nodes))
            )
        except Exception:
            # Selection polling must never spam the listener.
            pass

    def _collect_axes(self):
        axes = []
        if self._axis_x_chk.isChecked():
            axes.append(u"X")
        if self._axis_y_chk.isChecked():
            axes.append(u"Y")
        if self._axis_z_chk.isChecked():
            axes.append(u"Z")
        return axes

    def _collect_options(self):
        return {
            u"percent": int(self._percent_spn.value()),
            u"start_frame": int(self._start_spn.value()),
            u"end_frame": int(self._end_spn.value()),
            u"pivot_mode": u"frame" if self._pivot_frame_radio.isChecked() else u"mid",
            u"pivot_frame": int(self._pivot_frame_spn.value()),
            u"position": self._pos_chk.isChecked(),
            u"rotation": self._rot_chk.isChecked(),
            u"scale": self._scl_chk.isChecked(),
            u"axes": self._collect_axes(),
        }

    def _on_start(self):
        options = self._collect_options()
        ok, message = scale_keys.apply_scale(options)
        if ok:
            QtWidgets.QMessageBox.information(self, u"完成", message)
        else:
            QtWidgets.QMessageBox.warning(self, u"无法执行", message)

    def closeEvent(self, event):
        try:
            if self._selection_timer is not None:
                self._selection_timer.stop()
                self._selection_timer.deleteLater()
                self._selection_timer = None
        except Exception:
            pass
        super(ScaleValueWindow, self).closeEvent(event)

# -*- coding: utf-8 -*-
"""Standalone PySide2 front end for the Arc Run Creator backend."""
from __future__ import print_function

import os

from PySide2 import QtCore, QtWidgets

try:
    _text_type = unicode
except NameError:
    _text_type = str

_WINDOW = None
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_INSTALL_ROOT = os.path.dirname(_TOOL_DIR)
_BACKEND_MS = os.path.join(
    _INSTALL_ROOT, u"maxscript", u"ArcRunCreatorBackend.ms"
)


def _as_text(value):
    if value is None:
        return u""
    try:
        return _text_type(value)
    except Exception:
        return _text_type(repr(value))


class ArcRunCreatorWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(ArcRunCreatorWindow, self).__init__(parent)
        self._rt = None
        self._backend_loaded = False
        self.setObjectName("OP_ArcRunCreatorWindow")
        self.setWindowTitle(u"直跑转弧线跑")
        self.setMinimumWidth(460)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        contract = QtWidgets.QLabel(
            u"30 FPS｜自动识别源速度｜时长不限｜前进=世界 -Y"
        )
        layout.addWidget(contract)
        layout.addWidget(QtWidgets.QLabel(
            u"第一步：只选择 Biped COM，然后生成辅助 Root"
        ))

        create_row = QtWidgets.QHBoxLayout()
        self.left_btn = QtWidgets.QPushButton(u"生成左弧线跑步")
        self.right_btn = QtWidgets.QPushButton(u"生成右弧线跑步")
        self.left_btn.setMinimumHeight(38)
        self.right_btn.setMinimumHeight(38)
        create_row.addWidget(self.left_btn)
        create_row.addWidget(self.right_btn)
        layout.addLayout(create_row)

        self.edit_group = QtWidgets.QGroupBox(u"辅助 Root 路径设置")
        edit_layout = QtWidgets.QVBoxLayout(self.edit_group)
        self.helper_label = QtWidgets.QLabel(u"请选择 Left_Root 或 Right_Root")
        edit_layout.addWidget(self.helper_label)
        self.read_helper_btn = QtWidgets.QPushButton(u"读取当前辅助 Root")
        edit_layout.addWidget(self.read_helper_btn)

        param_row = QtWidgets.QHBoxLayout()
        param_row.addWidget(QtWidgets.QLabel(u"弧线半径（米）"))
        self.radius_spin = QtWidgets.QDoubleSpinBox()
        self.radius_spin.setRange(0.5, 100.0)
        self.radius_spin.setDecimals(2)
        self.radius_spin.setSingleStep(0.1)
        self.radius_spin.setValue(5.0)
        param_row.addWidget(self.radius_spin)
        param_row.addSpacing(16)
        param_row.addWidget(QtWidgets.QLabel(u"整体倾斜（度）"))
        self.lean_spin = QtWidgets.QDoubleSpinBox()
        self.lean_spin.setRange(0.0, 60.0)
        self.lean_spin.setDecimals(1)
        self.lean_spin.setSingleStep(0.5)
        self.lean_spin.setValue(8.0)
        param_row.addWidget(self.lean_spin)
        edit_layout.addLayout(param_row)

        self.update_btn = QtWidgets.QPushButton(u"生成 / 更新弧线路径")
        edit_layout.addWidget(self.update_btn)
        finish_row = QtWidgets.QHBoxLayout()
        self.collapse_btn = QtWidgets.QPushButton(u"塌陷回 BIP")
        self.cancel_btn = QtWidgets.QPushButton(u"取消并恢复直跑")
        finish_row.addWidget(self.collapse_btn)
        finish_row.addWidget(self.cancel_btn)
        edit_layout.addLayout(finish_row)
        layout.addWidget(self.edit_group)

        self.status_label = QtWidgets.QLabel(u"就绪。")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.left_btn.clicked.connect(lambda: self._generate("left"))
        self.right_btn.clicked.connect(lambda: self._generate("right"))
        self.read_helper_btn.clicked.connect(self.refresh_selection)
        self.update_btn.clicked.connect(self._update_path)
        self.collapse_btn.clicked.connect(self._collapse)
        self.cancel_btn.clicked.connect(self._cancel)

    def _backend(self):
        rt = self._runtime()
        if not self._backend_loaded:
            if not os.path.isfile(_BACKEND_MS):
                raise RuntimeError(u"弧线跑后端文件不存在：" + _BACKEND_MS)
            rt.fileIn(_BACKEND_MS)
            self._backend_loaded = True
        backend = getattr(rt, "OPArcRunCreatorBackend", None)
        if backend is None:
            raise RuntimeError(u"弧线跑 MaxScript 后端加载失败。")
        return backend

    def _runtime(self):
        if self._rt is None:
            import pymxs
            self._rt = pymxs.runtime
        return self._rt

    def _selected_helper(self):
        helper = self._backend().selectedHelper()
        if helper is None:
            return None
        try:
            if not self._runtime().isValidNode(helper):
                return None
        except Exception:
            return None
        return helper

    def _user_float(self, node, name, fallback):
        try:
            value = self._runtime().getUserProp(node, name)
            return float(value)
        except Exception:
            return float(fallback)

    def _show_error(self, exc):
        text = _as_text(exc)
        self.status_label.setText(u"失败：" + text)
        QtWidgets.QMessageBox.warning(self, u"直跑转弧线跑", text)

    def refresh_selection(self):
        try:
            helper = self._selected_helper()
            enabled = helper is not None
            self.edit_group.setEnabled(enabled)
            if not enabled:
                self.helper_label.setText(u"请选择 Left_Root 或 Right_Root")
                return
            speed_mps = self._user_float(
                helper, u"OPArcRunSourceSpeedCmPerSecond", 0.0
            ) / 100.0
            if speed_mps > 0.0:
                self.helper_label.setText(
                    u"{0}｜源速度 {1:.2f} m/s".format(
                        _as_text(helper.name), speed_mps
                    )
                )
            else:
                self.helper_label.setText(_as_text(helper.name))
            if not self.radius_spin.hasFocus():
                self.radius_spin.setValue(self._user_float(
                    helper, u"OPArcRunRadiusM", 5.0
                ))
            if not self.lean_spin.hasFocus():
                self.lean_spin.setValue(self._user_float(
                    helper, u"OPArcRunLeanDeg", 8.0
                ))
        except Exception:
            self.edit_group.setEnabled(False)

    def _generate(self, direction):
        self.status_label.setText(u"正在生成辅助 Root 和临时还原层……")
        try:
            rt = self._runtime()
            helper = self._backend().generateHelper(rt.Name(direction))
            self.refresh_selection()
            speed_mps = self._user_float(
                helper, u"OPArcRunSourceSpeedCmPerSecond", 0.0
            ) / 100.0
            self.status_label.setText(
                u"{0} 已生成，识别源速度 {1:.2f} m/s，可以继续调整半径和倾斜。".format(
                    _as_text(helper.name), speed_mps
                )
            )
        except Exception as exc:
            self._show_error(exc)

    def _update_path(self):
        try:
            helper = self._selected_helper()
            if helper is None:
                raise RuntimeError(u"请先选择 Left_Root 或 Right_Root。")
            self._backend().updateHelper(
                helper, self.radius_spin.value(), self.lean_spin.value()
            )
            self.status_label.setText(
                u"路径已更新：半径 {0:.2f}m，倾斜 {1:.1f}°。".format(
                    self.radius_spin.value(), self.lean_spin.value()
                )
            )
        except Exception as exc:
            self._show_error(exc)

    def _collapse(self):
        helper = None
        try:
            helper = self._selected_helper()
        except Exception as exc:
            self._show_error(exc)
            return
        if helper is None:
            self._show_error(RuntimeError(u"请先选择 Left_Root 或 Right_Root。"))
            return
        answer = QtWidgets.QMessageBox.question(
            self, u"直跑转弧线跑",
            u"将辅助 Root 轨迹塌陷回 Biped COM，并删除辅助 Root。是否继续？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            self._backend().collapseHelper(helper)
            self.refresh_selection()
            self.status_label.setText(u"塌陷完成，仅使用原 COM 关键帧并集。")
        except Exception as exc:
            self._show_error(exc)

    def _cancel(self):
        helper = None
        try:
            helper = self._selected_helper()
        except Exception as exc:
            self._show_error(exc)
            return
        if helper is None:
            self._show_error(RuntimeError(u"请先选择 Left_Root 或 Right_Root。"))
            return
        answer = QtWidgets.QMessageBox.question(
            self, u"直跑转弧线跑",
            u"删除辅助 Root 和临时层，恢复原始直线跑。是否继续？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            self._backend().cancelHelper(helper)
            self.refresh_selection()
            self.status_label.setText(u"已取消，Biped 恢复为原始直线跑。")
        except Exception as exc:
            self._show_error(exc)


def _clear_window(*_args):
    global _WINDOW
    _WINDOW = None


def show():
    global _WINDOW
    if _WINDOW is not None:
        try:
            _WINDOW.showNormal()
            _WINDOW.raise_()
            _WINDOW.activateWindow()
            return _WINDOW
        except Exception:
            _WINDOW = None
    _WINDOW = ArcRunCreatorWindow(parent=None)
    _WINDOW.destroyed.connect(_clear_window)
    _WINDOW.show()
    _WINDOW.raise_()
    _WINDOW.activateWindow()
    return _WINDOW

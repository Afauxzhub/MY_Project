# -*- coding: utf-8 -*-
"""发布历史查看窗口。"""
from __future__ import division
import os

from PySide2 import QtWidgets, QtCore

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


class PublishHistoryDialog(QtWidgets.QDialog):
    open_requested = QtCore.Signal(str)

    def __init__(self, file_path, rows, parent=None):
        super(PublishHistoryDialog, self).__init__(parent)
        self.setWindowTitle(u"查看历史文件")
        self.setMinimumSize(900, 460)
        self.resize(1100, 560)
        self.setWindowFlags(
            self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint
        )
        self._file_path = _as_text(file_path)
        self._rows = list(rows or [])
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel(
            u"文件：{0}".format(os.path.basename(self._file_path))
        )
        layout.addWidget(title)

        self._table = QtWidgets.QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels([
            u"发布次数", u"发布日期", u"负责人", u"阶段", u"状态", u"文件路径"
        ])
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.cellDoubleClicked.connect(self._open_row)
        layout.addWidget(self._table, 1)

        for row_index, row in enumerate(self._rows):
            self._table.insertRow(row_index)
            values = [
                row.get(u"publish_revision_label", u""),
                row.get(u"published_at", u""),
                row.get(u"publisher", u""),
                row.get(u"stage_label", u""),
                u"可打开" if row.get(u"available") else u"文件不存在",
                row.get(u"open_path") or row.get(u"backup_path") or row.get(u"public_path"),
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(_as_text(value))
                item.setData(QtCore.Qt.UserRole, _as_text(row.get(u"open_path", u"")))
                self._table.setItem(row_index, column, item)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.Stretch)
        if self._rows:
            self._table.selectRow(0)
        else:
            empty_hint = QtWidgets.QLabel(
                u"暂无已同步到公盘的发布历史。"
            )
            empty_hint.setStyleSheet(u"color:#999;")
            layout.addWidget(empty_hint)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        open_btn = QtWidgets.QPushButton(u"打开选中历史文件")
        open_btn.clicked.connect(self._open_selected)
        close_btn = QtWidgets.QPushButton(u"关闭")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(open_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _selected_path(self):
        row = self._table.currentRow()
        if row < 0:
            return u""
        item = self._table.item(row, 0)
        return _as_text(item.data(QtCore.Qt.UserRole)) if item is not None else u""

    def _open_selected(self):
        path = self._selected_path()
        if not path or not os.path.isfile(path):
            QtWidgets.QMessageBox.warning(
                self, u"无法打开", u"该历史文件当前不存在或无法访问。"
            )
            return
        self.accept()
        self.open_requested.emit(path)

    def _open_row(self, row, column):
        self._table.selectRow(row)
        self._open_selected()

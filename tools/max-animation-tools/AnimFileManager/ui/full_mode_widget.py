# -*- coding: utf-8 -*-
"""完整显示模式：Windows 风格树，仅 .max 文件。"""
from __future__ import division
import os

from PySide2 import QtWidgets, QtCore, QtGui

from core.file_scanner import list_full_dir_entries

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


class FullModeWidget(QtWidgets.QWidget):
    file_activated = QtCore.Signal(str)
    file_context = QtCore.Signal(str, object)

    def __init__(self, parent=None):
        super(FullModeWidget, self).__init__(parent)
        self._root_path = u""
        self._build_ui()

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        bar = QtWidgets.QHBoxLayout()
        self._path_edit = QtWidgets.QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText(u"选择根目录…")
        browse_btn = QtWidgets.QPushButton(u"浏览…")
        browse_btn.clicked.connect(self._browse_root)
        bar.addWidget(self._path_edit, 1)
        bar.addWidget(browse_btn)
        lay.addLayout(bar)

        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderLabels(
            [u"名称", u"发布日期", u"负责人", u"发布版本", u"发布次数", u"类型"]
        )
        self._tree.setColumnWidth(0, 520)
        self._tree.setColumnWidth(1, 110)
        self._tree.setColumnWidth(2, 100)
        self._tree.setColumnWidth(3, 110)
        self._tree.setColumnWidth(4, 80)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self._tree, 1)

    def set_root_path(self, path):
        self._root_path = _as_text(path)
        self._path_edit.setText(self._root_path)
        self._reload()

    def _browse_root(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, u"选择根目录", self._root_path or u"")
        if path:
            self.set_root_path(path)

    def _reload(self):
        self._tree.clear()
        if not self._root_path:
            return
        root = {
            u"name": os.path.basename(self._root_path) or self._root_path,
            u"path": self._root_path,
            u"type": u"folder",
            u"children": [],
        }
        self._add_node(None, root)

    def _add_node(self, parent_item, node):
        item = QtWidgets.QTreeWidgetItem(parent_item or self._tree)
        metadata = node.get(u"metadata", {}) or {}
        is_file = node.get(u"type") == u"file"
        raw_name = _as_text(node.get(u"name", u""))
        item.setText(0, os.path.splitext(raw_name)[0] if is_file else raw_name)
        item.setText(1, _as_text(metadata.get(u"date_label", u"")))
        item.setText(2, _as_text(metadata.get(u"publisher", u"")))
        item.setText(3, _as_text(metadata.get(u"version_label", u"")))
        item.setText(4, _as_text(metadata.get(u"publish_revision_label", u"")))
        item.setText(5, u"MAX" if is_file else u"文件夹")
        for column in (1, 2):
            item.setTextAlignment(
                column, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
            )
        item.setTextAlignment(
            3, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        item.setTextAlignment(
            4, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
        )
        if is_file:
            item.setToolTip(
                0, _as_text(metadata.get(u"display_name", raw_name))
            )
        item.setData(0, QtCore.Qt.UserRole, _as_text(node.get(u"path", u"")))
        item.setData(0, QtCore.Qt.UserRole + 1, _as_text(node.get(u"type", u"")))
        if is_file:
            item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
        else:
            item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
            item.setData(0, QtCore.Qt.UserRole + 2, False)
            placeholder = QtWidgets.QTreeWidgetItem(item)
            placeholder.setData(0, QtCore.Qt.UserRole + 3, True)
        return item

    def _on_item_expanded(self, item):
        kind = _as_text(item.data(0, QtCore.Qt.UserRole + 1))
        if kind != u"folder" or bool(item.data(0, QtCore.Qt.UserRole + 2)):
            return
        path = _as_text(item.data(0, QtCore.Qt.UserRole))
        item.takeChildren()
        for child in list_full_dir_entries(path):
            self._add_node(item, child)
        item.setData(0, QtCore.Qt.UserRole + 2, True)

    def _on_item_double_clicked(self, item, column):
        path = _as_text(item.data(0, QtCore.Qt.UserRole))
        kind = _as_text(item.data(0, QtCore.Qt.UserRole + 1))
        if kind == u"file" and path:
            self.file_activated.emit(path)

    def _on_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return
        path = _as_text(item.data(0, QtCore.Qt.UserRole))
        kind = _as_text(item.data(0, QtCore.Qt.UserRole + 1))
        if kind != u"file" or not path:
            return
        self.file_context.emit(path, self._tree.mapToGlobal(pos))

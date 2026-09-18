# -*- coding: utf-8 -*-
"""
Left Panel - Folder Tree Widget

Industrial-grade asset tree for multiple libraries with dual view modes:
  - Physical View: mirrors real folders on disk
  - Category View: shows virtual category tree stored in JSON
"""

import json
import io
import os
import shutil
import time
import uuid

from ..utils import preview_utils

from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QTreeView, QAbstractItemView, QFileDialog, QMenu, QAction,
    QInputDialog, QLineEdit, QMessageBox, QRubberBand, QApplication
)
from PySide2.QtCore import (
    Qt, Signal, QTimer, QModelIndex, QItemSelectionModel,
    QItemSelection, QPoint, QRect
)
from PySide2.QtGui import QStandardItemModel, QStandardItem, QColor, QFont


VIEW_PHYSICAL = "physical"
VIEW_CATEGORY = "category"

NODE_LIBRARY = "library"
NODE_PHYSICAL = "physical_folder"
NODE_CATEGORY = "virtual_category"

CATEGORY_FILENAME = ".anim_categories.json"
INVALID_PATH_CHARS = r'\/:*?"<>|'
ANIMATION_EXTENSIONS = frozenset({".bip", ".xaf", ".json", ".animx"})

ROLE_NODE_TYPE = Qt.UserRole + 1
ROLE_NODE_DATA = Qt.UserRole + 2
ROLE_NODE_KEY = Qt.UserRole + 3

AUTO_REFRESH_DEBOUNCE_MS = 250
AUTO_REFRESH_MIN_INTERVAL_SECONDS = 2.0
STATUS_MESSAGE_DURATION_MS = 3000

try:
    text_type = unicode
except NameError:
    text_type = str

try:
    PermissionError
except NameError:
    PermissionError = OSError


def _normalize_path(path):
    path = _to_text(path or u"")
    return os.path.normcase(os.path.normpath(path))


def _to_text(value):
    if isinstance(value, text_type):
        return value
    if value is None:
        return text_type()
    try:
        return value.decode("utf-8")
    except Exception:
        try:
            return value.decode("mbcs")
        except Exception:
            return text_type(value)


def _json_to_text(data):
    payload = json.dumps(data, indent=4, ensure_ascii=False)
    if isinstance(payload, text_type):
        return payload
    return payload.decode("utf-8")


def _format_text(template, *args):
    template = _to_text(template)
    normalized_args = []
    for value in args:
        if isinstance(value, bytes):
            normalized_args.append(_to_text(value))
        else:
            normalized_args.append(value)
    return template.format(*normalized_args)


def _safe_print(*parts):
    values = []
    for part in parts:
        try:
            values.append(repr(part))
        except Exception:
            values.append("<unprintable>")
    print(" ".join(values))


def _sanitize_name(name):
    value = _to_text(name or u"").strip()
    for char in INVALID_PATH_CHARS:
        value = value.replace(char, "_")
    return value.strip()


def _unique_library_id():
    return u"library_" + uuid.uuid4().hex[:8]


class FolderTreeView(QTreeView):
    """Tree view with hotkeys and custom drag/drop hooks."""

    item_drop_requested = Signal(object, object)
    external_files_drop_requested = Signal(list, object)
    key_action_requested = Signal(str)

    def __init__(self, parent=None):
        super(FolderTreeView, self).__init__(parent)
        self._dragged_node_data = None
        self._dragged_node_payload = []
        self._selection_anchor_key = None
        self._blank_press_active = False
        self._rubber_band_active = False
        self._rubber_band_origin = QPoint()
        self._right_click_selected_keys = set()
        self._right_click_index_key = None
        self._rubber_band = QRubberBand(QRubberBand.Rectangle, self.viewport())
        self._rubber_band.hide()
        self._drop_target_index = QModelIndex()
        self._drop_target_band = QRubberBand(QRubberBand.Rectangle, self.viewport())
        self._drop_target_band.setStyleSheet(
            "border: 2px solid #4aa3ff; background-color: rgba(74, 163, 255, 32);"
        )
        self._drop_target_band.hide()
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAnimated(True)
        self.setIndentation(15)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setHeaderHidden(True)

    def startDrag(self, supported_actions):
        index = self.currentIndex()
        selected_indexes = []
        if self.selectionModel():
            selected_indexes = list(self.selectionModel().selectedRows())

        if index.isValid() and selected_indexes and index in selected_indexes:
            payload_indexes = selected_indexes
        elif index.isValid():
            payload_indexes = [index]
        else:
            payload_indexes = []

        self._dragged_node_payload = []
        for payload_index in payload_indexes:
            node_data = payload_index.data(ROLE_NODE_DATA)
            if node_data:
                self._dragged_node_payload.append(node_data)

        self._dragged_node_data = self._dragged_node_payload[0] if self._dragged_node_payload else None
        super(FolderTreeView, self).startDrag(supported_actions)

    def dragEnterEvent(self, event):
        if event.source() is self or event.mimeData().hasUrls():
            self._clear_drop_target_highlight()
            event.acceptProposedAction()
            return
        super(FolderTreeView, self).dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.source() is self or event.mimeData().hasUrls():
            target_index = self.indexAt(event.pos())
            target_data = target_index.data(ROLE_NODE_DATA) if target_index.isValid() else None
            if self._is_valid_drop_target(event, target_data):
                self._show_drop_target_highlight(target_index)
                event.acceptProposedAction()
            else:
                self._clear_drop_target_highlight()
                event.ignore()
            return
        super(FolderTreeView, self).dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._clear_drop_target_highlight()
        super(FolderTreeView, self).dragLeaveEvent(event)

    def dropEvent(self, event):
        target_index = self.indexAt(event.pos())
        target_data = target_index.data(ROLE_NODE_DATA) if target_index.isValid() else None

        if event.source() is self:
            payload = self._dragged_node_payload or ([self._dragged_node_data] if self._dragged_node_data else [])
            if payload and target_data:
                self.item_drop_requested.emit(payload, target_data)
                self._dragged_node_data = None
                self._dragged_node_payload = []
                self._clear_drop_target_highlight()
                event.acceptProposedAction()
                return
            self._dragged_node_data = None
            self._dragged_node_payload = []
            self._clear_drop_target_highlight()
            event.ignore()
            return

        if event.mimeData().hasUrls() and target_data:
            paths = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    paths.append(os.path.normpath(url.toLocalFile()))
            if paths:
                self.external_files_drop_requested.emit(paths, target_data)
                self._clear_drop_target_highlight()
                event.acceptProposedAction()
                return

        self._clear_drop_target_highlight()
        super(FolderTreeView, self).dropEvent(event)

    def _is_valid_drop_target(self, event, target_data):
        if not target_data:
            return False

        host = self.parent()
        view_mode = getattr(host, "view_mode", VIEW_PHYSICAL)

        if event.source() is self:
            return True

        if not event.mimeData().hasUrls():
            return False

        node_type = target_data.get("node_type")
        if view_mode == VIEW_PHYSICAL:
            return node_type in (NODE_LIBRARY, NODE_PHYSICAL)
        if view_mode == VIEW_CATEGORY:
            return node_type == NODE_CATEGORY
        return False

    def _show_drop_target_highlight(self, index):
        if not index.isValid():
            self._clear_drop_target_highlight()
            return

        self._drop_target_index = index
        rect = self.visualRect(index)
        if not rect.isValid():
            self._clear_drop_target_highlight()
            return

        rect.setLeft(0)
        rect.setWidth(self.viewport().width())
        self._drop_target_band.setGeometry(rect)
        self._drop_target_band.show()

    def _clear_drop_target_highlight(self):
        self._drop_target_index = QModelIndex()
        self._drop_target_band.hide()

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if event.button() == Qt.RightButton:
            self._right_click_selected_keys = self._selected_key_set()
            self._right_click_index_key = index.data(ROLE_NODE_KEY) if index.isValid() else None

        if event.button() == Qt.LeftButton:
            if index.isValid() and (event.modifiers() & Qt.ShiftModifier):
                self._select_visible_range_to(index)
                event.accept()
                return

            if index.isValid() and (event.modifiers() & Qt.AltModifier):
                self._remove_index_from_selection(index)
                event.accept()
                return

            if not index.isValid() and event.modifiers() == Qt.NoModifier:
                self._clear_all_selection()
                self._blank_press_active = True
                self._rubber_band_active = False
                self._rubber_band_origin = event.pos()
                self._rubber_band.setGeometry(QRect(self._rubber_band_origin, self._rubber_band_origin))
                event.accept()
                return

        super(FolderTreeView, self).mousePressEvent(event)

        if event.button() == Qt.LeftButton and index.isValid() and not (event.modifiers() & Qt.ShiftModifier):
            self._selection_anchor_key = index.data(ROLE_NODE_KEY)

    def mouseMoveEvent(self, event):
        if self._blank_press_active:
            if not (event.buttons() & Qt.LeftButton):
                self._finish_blank_drag_selection()
                event.accept()
                return

            if not self._rubber_band_active:
                distance = (event.pos() - self._rubber_band_origin).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    self._rubber_band_active = True
                    self._rubber_band.show()

            if self._rubber_band_active:
                rect = QRect(self._rubber_band_origin, event.pos()).normalized()
                self._rubber_band.setGeometry(rect)
                self._update_rubber_band_selection(rect)
                event.accept()
                return

        super(FolderTreeView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._blank_press_active:
            if self._rubber_band_active:
                self._update_rubber_band_selection(self._rubber_band.geometry())
            self._finish_blank_drag_selection()
            event.accept()
            return

        super(FolderTreeView, self).mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.pos())
        if event.button() == Qt.LeftButton and index.isValid() and self.model() and self.model().rowCount(index) > 0:
            self._select_index_subtree(index)
            event.accept()
            return
        super(FolderTreeView, self).mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._clear_all_selection()
            event.accept()
            return
        if event.key() == Qt.Key_F2:
            self.key_action_requested.emit("rename")
            event.accept()
            return
        if event.key() == Qt.Key_Delete:
            self.key_action_requested.emit("delete")
            event.accept()
            return
        if event.key() == Qt.Key_F5:
            self.key_action_requested.emit("refresh")
            event.accept()
            return
        super(FolderTreeView, self).keyPressEvent(event)

    def _clear_all_selection(self):
        selection_model = self.selectionModel()
        if selection_model:
            selection_model.clearSelection()
            selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.NoUpdate)
        self._selection_anchor_key = None

    def _remove_index_from_selection(self, index):
        selection_model = self.selectionModel()
        if not selection_model or not index.isValid():
            return

        selection_model.select(index, QItemSelectionModel.Deselect | QItemSelectionModel.Rows)
        current_index = selection_model.currentIndex()
        if current_index == index:
            selected_rows = selection_model.selectedRows()
            next_index = selected_rows[0] if selected_rows else QModelIndex()
            selection_model.setCurrentIndex(next_index, QItemSelectionModel.NoUpdate)
        self._selection_anchor_key = index.data(ROLE_NODE_KEY)

    def _finish_blank_drag_selection(self):
        self._blank_press_active = False
        self._rubber_band_active = False
        self._rubber_band.hide()

    def _update_rubber_band_selection(self, rect):
        selection_model = self.selectionModel()
        if not selection_model or not self.model():
            return

        visible_indexes = self._visible_indexes()
        hit_indexes = []
        for index in visible_indexes:
            row_rect = self.visualRect(index)
            row_rect.setLeft(0)
            row_rect.setWidth(self.viewport().width())
            if row_rect.intersects(rect):
                hit_indexes.append(index)

        selection = QItemSelection()
        for index in hit_indexes:
            selection.select(index, index)

        selection_model.clearSelection()
        if not hit_indexes:
            selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.NoUpdate)
            self._selection_anchor_key = None
            return

        selection_model.select(selection, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        current_index = hit_indexes[0]
        selection_model.setCurrentIndex(current_index, QItemSelectionModel.NoUpdate)
        self._selection_anchor_key = current_index.data(ROLE_NODE_KEY)

    def _visible_indexes(self):
        result = []
        if not self.model():
            return result

        def walk(parent_index):
            row_count = self.model().rowCount(parent_index)
            for row in range(row_count):
                index = self.model().index(row, 0, parent_index)
                result.append(index)
                if self.isExpanded(index):
                    walk(index)

        walk(QModelIndex())
        return result

    def _select_index_subtree(self, root_index):
        selection_model = self.selectionModel()
        if not selection_model or not root_index.isValid() or not self.model():
            return

        selection = QItemSelection()

        def walk(index):
            self.expand(index)
            selection.select(index, index)
            row_count = self.model().rowCount(index)
            for row in range(row_count):
                walk(self.model().index(row, 0, index))

        walk(root_index)
        selection_model.clearSelection()
        selection_model.select(selection, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        selection_model.setCurrentIndex(root_index, QItemSelectionModel.NoUpdate)
        self._selection_anchor_key = root_index.data(ROLE_NODE_KEY)

    def _select_visible_range_to(self, target_index):
        selection_model = self.selectionModel()
        if not selection_model or not target_index.isValid():
            return

        anchor_index = QModelIndex()
        if self._selection_anchor_key:
            anchor_index = self._index_for_key(self._selection_anchor_key)
        if not anchor_index.isValid():
            anchor_index = self.currentIndex()
        if not anchor_index.isValid():
            anchor_index = target_index

        visible_indexes = self._visible_indexes()
        anchor_pos = -1
        target_pos = -1
        for pos, index in enumerate(visible_indexes):
            if index == anchor_index:
                anchor_pos = pos
            if index == target_index:
                target_pos = pos

        if anchor_pos < 0 or target_pos < 0:
            selection_model.clearSelection()
            selection_model.select(target_index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            selection_model.setCurrentIndex(target_index, QItemSelectionModel.NoUpdate)
            self._selection_anchor_key = target_index.data(ROLE_NODE_KEY)
            return

        start = min(anchor_pos, target_pos)
        end = max(anchor_pos, target_pos)
        selection = QItemSelection()
        for visible_index in visible_indexes[start:end + 1]:
            selection.select(visible_index, visible_index)

        selection_model.clearSelection()
        selection_model.select(selection, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        selection_model.setCurrentIndex(target_index, QItemSelectionModel.NoUpdate)

    def _selected_key_set(self):
        result = set()
        selection_model = self.selectionModel()
        if not selection_model:
            return result

        for index in selection_model.selectedRows():
            key = index.data(ROLE_NODE_KEY)
            if key:
                result.add(key)
        return result

    def _index_for_key(self, node_key):
        if not node_key or not self.model():
            return QModelIndex()

        def walk(parent_index):
            row_count = self.model().rowCount(parent_index)
            for row in range(row_count):
                index = self.model().index(row, 0, parent_index)
                if index.data(ROLE_NODE_KEY) == node_key:
                    return index
                result = walk(index)
                if result.isValid():
                    return result
            return QModelIndex()

        return walk(QModelIndex())

class FolderTreeWidget(QWidget):
    """
    Container widget for multi-library physical/category asset trees.

    Emits folder_selected(str) for physical folders.
    Emits category_selected(dict) for virtual category selections.
    """

    folder_selected = Signal(str)
    category_selected = Signal(dict)
    root_path_changed = Signal(str)
    libraries_changed = Signal(list)
    status_message_requested = Signal(object, int)
    selection_cleared = Signal()
    new_asset_requested = Signal(object, object)

    def __init__(self, root_path="", settings=None):
        super(FolderTreeWidget, self).__init__()
        self.settings = settings
        self.root_path = root_path
        self.view_mode = VIEW_PHYSICAL
        self.library_specs = []
        self.model = None
        self.category_configs = {}
        self._pending_auto_refresh_library_id = None
        self._last_refresh_at = 0.0
        self._suspend_selection_sync = False
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setSingleShot(True)
        self._auto_refresh_timer.timeout.connect(self._run_auto_refresh)

        self._init_state()
        self._init_ui()
        self._rebuild_model(keep_state=False, emit_selection=False)

    # ------------------------------------------------------------------ #
    #  State bootstrap                                                    #
    # ------------------------------------------------------------------ #

    def _init_state(self):
        should_persist_migration = False
        if self.settings:
            self.library_specs = self.settings.get_libraries()
            self.view_mode = self.settings.get_folder_tree_view_mode()
            raw_libraries = self.settings.get("libraries", None)
            should_persist_migration = not raw_libraries and bool(self.library_specs)
        elif self.root_path and os.path.isdir(self.root_path):
            self.library_specs = [self._make_library_spec("Animation Library", self.root_path, False)]
        else:
            self.library_specs = []

        self.library_specs = [self._normalize_library_spec(spec) for spec in self.library_specs]

        if self.view_mode not in (VIEW_PHYSICAL, VIEW_CATEGORY):
            self.view_mode = VIEW_PHYSICAL

        if should_persist_migration:
            self._save_widget_state()

    def _make_library_spec(self, name, root_path, is_network):
        name = _to_text(name)
        root_path = os.path.normpath(_to_text(root_path))
        return {
            "id": _unique_library_id(),
            "name": name,
            "root_path": root_path,
            "is_network": bool(is_network),
            "watch_enabled": not bool(is_network),
            "category_file": os.path.join(root_path, CATEGORY_FILENAME),
        }

    def _normalize_library_spec(self, spec):
        root_path = os.path.normpath(_to_text(spec.get("root_path", u"")))
        is_network = bool(spec.get("is_network", False))
        return {
            "id": spec.get("id") or _unique_library_id(),
            "name": _to_text(spec.get("name") or os.path.basename(root_path) or u"Library"),
            "root_path": root_path,
            "is_network": is_network,
            "watch_enabled": bool(spec.get("watch_enabled", not is_network)),
            "category_file": spec.get("category_file") or os.path.join(root_path, CATEGORY_FILENAME),
        }

    # ------------------------------------------------------------------ #
    #  UI construction                                                    #
    # ------------------------------------------------------------------ #

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        self.add_library_btn = QPushButton("Add Library")
        self.add_library_btn.setToolTip("Add a local or shared animation library")
        self.add_library_btn.clicked.connect(self.on_add_library)
        toolbar.addWidget(self.add_library_btn)

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem("Physical View", VIEW_PHYSICAL)
        self.view_mode_combo.addItem("Category View", VIEW_CATEGORY)
        combo_index = self.view_mode_combo.findData(self.view_mode)
        if combo_index >= 0:
            self.view_mode_combo.setCurrentIndex(combo_index)
        self.view_mode_combo.currentIndexChanged.connect(self._on_view_mode_changed)
        toolbar.addWidget(self.view_mode_combo)

        layout.addLayout(toolbar)

        self.tree_view = FolderTreeView(self)
        self.tree_view.setStyleSheet("""
            QTreeView::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QTreeView::item:selected:active {
                background-color: #094771;
                color: #ffffff;
            }
            QTreeView::item:selected:!active {
                background-color: #094771;
                color: #ffffff;
            }
        """)
        self.tree_view.customContextMenuRequested.connect(self._on_context_menu)
        self.tree_view.item_drop_requested.connect(self._on_item_drop_requested)
        self.tree_view.external_files_drop_requested.connect(self._on_external_files_dropped)
        self.tree_view.key_action_requested.connect(self._on_key_action_requested)
        layout.addWidget(self.tree_view)

    # ------------------------------------------------------------------ #
    #  Model construction                                                 #
    # ------------------------------------------------------------------ #

    def _rebuild_model(self, keep_state=True, focus_key=None, emit_selection=True):
        state = self._capture_view_state() if keep_state else {
            "expanded": set(),
            "selected_keys": set(),
            "current_key": None,
            "preserve_empty_selection": False,
        }

        self.model = QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels(["Libraries"])

        for spec in self.library_specs:
            library_item = self._build_library_item(spec)
            self.model.appendRow(library_item)

            if self.view_mode == VIEW_PHYSICAL:
                self._populate_physical_children(spec, library_item, spec["root_path"])
            else:
                self._populate_category_children(spec, library_item)

        self.tree_view.setModel(self.model)
        self._bind_selection_model()
        self._restore_view_state(state, focus_key=focus_key, emit_selection=emit_selection)
        self.tree_view.expandToDepth(0)

    def _build_library_item(self, spec):
        node_data = {
            "id": spec["id"],
            "name": spec["name"],
            "library_id": spec["id"],
            "node_type": NODE_LIBRARY,
            "view_mode": self.view_mode,
            "root_path": spec["root_path"],
            "path": spec["root_path"],
            "is_network": spec["is_network"],
            "watch_enabled": spec["watch_enabled"],
            "category_file": spec["category_file"],
            "relative_path": "",
            "is_root_library_node": True,
        }
        return self._make_item(spec["name"], NODE_LIBRARY, node_data, self._make_node_key(node_data))

    def _populate_physical_children(self, spec, parent_item, parent_path):
        if not os.path.isdir(parent_path):
            return

        try:
            entries = os.listdir(parent_path)
        except Exception as exc:
            _safe_print("Folder tree scan failed:", exc)
            return

        child_dirs = []
        for entry in entries:
            child_path = os.path.join(parent_path, entry)
            if os.path.isdir(child_path):
                child_dirs.append((entry, child_path))

        for entry_name, child_path in sorted(child_dirs, key=lambda item: item[0].lower()):
            relative_path = os.path.relpath(child_path, spec["root_path"])
            node_data = {
                "id": self._physical_node_id(spec["id"], relative_path),
                "name": entry_name,
                "library_id": spec["id"],
                "node_type": NODE_PHYSICAL,
                "view_mode": VIEW_PHYSICAL,
                "root_path": spec["root_path"],
                "path": child_path,
                "parent_path": parent_path,
                "relative_path": relative_path,
                "is_root_library_node": False,
            }
            item = self._make_item(entry_name, NODE_PHYSICAL, node_data, self._make_node_key(node_data))
            parent_item.appendRow(item)
            self._populate_physical_children(spec, item, child_path)

    def _populate_category_children(self, spec, parent_item):
        config = self._load_category_config(spec)
        categories = config.get("categories", {})
        root_order = list(config.get("root_order", []))
        category_stats = self._build_category_stats(config, spec["root_path"])

        for category_id in categories.keys():
            if not categories[category_id].get("parent_id") and category_id not in root_order:
                root_order.append(category_id)

        visited = set()
        for category_id in root_order:
            self._append_category_item(spec, parent_item, categories, category_id, visited, category_stats)

    def _append_category_item(self, spec, parent_item, categories, category_id, visited, category_stats):
        if category_id in visited or category_id not in categories:
            return

        visited.add(category_id)
        category = categories[category_id]
        stats = category_stats.get(category["id"], {"count": 0, "is_empty": True})
        node_data = {
            "id": category["id"],
            "name": category["name"],
            "library_id": spec["id"],
            "node_type": NODE_CATEGORY,
            "view_mode": VIEW_CATEGORY,
            "root_path": spec["root_path"],
            "category_file": spec["category_file"],
            "category_id": category["id"],
            "parent_category_id": category.get("parent_id"),
            "children_ids": list(category.get("children", [])),
            "asset_paths": list(category.get("asset_paths", [])),
            "asset_count": stats.get("count", 0),
            "is_empty_category": bool(stats.get("is_empty", True)),
        }
        item = self._make_item(
            self._format_category_label(category["name"], stats),
            NODE_CATEGORY,
            node_data,
            self._make_node_key(node_data)
        )
        parent_item.appendRow(item)

        for child_id in category.get("children", []):
            self._append_category_item(spec, item, categories, child_id, visited, category_stats)

    def _make_item(self, text, node_type, node_data, node_key):
        item = QStandardItem(text)
        item.setEditable(False)
        item.setData(node_type, ROLE_NODE_TYPE)
        item.setData(node_data, ROLE_NODE_DATA)
        item.setData(node_key, ROLE_NODE_KEY)
        item.setDropEnabled(True)
        item.setDragEnabled(node_type in (NODE_PHYSICAL, NODE_CATEGORY))
        self._apply_item_style(item, node_type, node_data)
        return item

    def _apply_item_style(self, item, node_type, node_data):
        font = item.font() or QFont()
        tooltip = ""

        if node_type == NODE_LIBRARY:
            font.setBold(True)
            item.setFont(font)
            item.setForeground(QColor("#d8d8d8"))
            tooltip = _to_text(node_data.get("root_path", u""))
        elif node_type == NODE_CATEGORY:
            font.setBold(True)
            item.setFont(font)
            if node_data.get("is_empty_category"):
                font.setItalic(True)
                item.setFont(font)
                item.setForeground(QColor("#8f8f8f"))
                tooltip = "Virtual category (empty)"
            else:
                item.setForeground(QColor("#8ec5ff"))
                tooltip = _format_text("Virtual category ({0} assets)", node_data.get("asset_count", 0))
        else:
            item.setForeground(QColor("#cccccc"))
            tooltip = _to_text(node_data.get("path", u""))

        if tooltip:
            item.setToolTip(tooltip)

    # ------------------------------------------------------------------ #
    #  Settings / persistence                                             #
    # ------------------------------------------------------------------ #

    def _save_widget_state(self):
        if not self.settings:
            return
        normalized_specs = [self._normalize_library_spec(spec) for spec in self.library_specs]
        self.library_specs = normalized_specs
        self.settings.set_libraries(normalized_specs)
        self.settings.set_folder_tree_view_mode(self.view_mode)
        save_ok = self.settings.save_config()
        if normalized_specs:
            self.root_path = normalized_specs[0]["root_path"]
            self.root_path_changed.emit(normalized_specs[0]["root_path"])
        else:
            self.root_path = ""
        self.libraries_changed.emit(normalized_specs)
        if not save_ok:
            QMessageBox.warning(
                self,
                "Config Save Failed",
                "Library changes could not be written to config.\n"
                "The tree may reset next time the plugin opens.\n\n"
                "Target path:\n{0}\n\n"
                "Error:\n{1}".format(
                    getattr(self.settings, "config_file", "Unknown"),
                    getattr(self.settings, "last_save_error", "Unknown error")
                )
            )

    def _load_category_config(self, spec):
        cache_key = spec["id"]
        if cache_key in self.category_configs:
            return self.category_configs[cache_key]

        category_file = spec["category_file"]
        config = {"version": 1, "categories": {}, "root_order": []}
        if os.path.isfile(category_file):
            try:
                with io.open(category_file, "r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    config["version"] = loaded.get("version", 1)
                    config["categories"] = loaded.get("categories", {}) or {}
                    config["root_order"] = loaded.get("root_order", []) or []
            except Exception as exc:
                _safe_print("Category config load failed:", exc)

        self.category_configs[cache_key] = config
        return config

    def _save_category_config(self, spec, config):
        category_file = spec["category_file"]
        root_dir = os.path.dirname(category_file)
        if not os.path.isdir(root_dir):
            os.makedirs(root_dir)
        with io.open(category_file, "w", encoding="utf-8") as handle:
            handle.write(_json_to_text(config))
        self.category_configs[spec["id"]] = config

    # ------------------------------------------------------------------ #
    #  View state restore                                                 #
    # ------------------------------------------------------------------ #

    def _capture_view_state(self):
        if not self.model:
            return {
                "expanded": set(),
                "selected_keys": set(),
                "current_key": None,
                "preserve_empty_selection": True,
            }

        expanded_keys = set()
        index_map = self._build_index_map()
        for key, index in index_map.items():
            if self.tree_view.isExpanded(index):
                expanded_keys.add(key)

        selected_keys = set()
        selection_model = self.tree_view.selectionModel()
        if selection_model:
            for index in selection_model.selectedRows():
                key = index.data(ROLE_NODE_KEY)
                if key:
                    selected_keys.add(key)

        current_index = self.tree_view.currentIndex()
        current_key = current_index.data(ROLE_NODE_KEY) if current_index.isValid() else None
        return {
            "expanded": expanded_keys,
            "selected_keys": selected_keys,
            "current_key": current_key,
            "preserve_empty_selection": True,
        }

    def _restore_view_state(self, state, focus_key=None, emit_selection=True, extra_expand_keys=None):
        index_map = self._build_index_map()
        self.tree_view.collapseAll()

        expanded_keys = set(state.get("expanded", set()))
        if extra_expand_keys:
            expanded_keys.update(extra_expand_keys)
        for key, index in index_map.items():
            if key in expanded_keys:
                self.tree_view.expand(index)

        if not expanded_keys and self.model:
            for row in range(self.model.rowCount()):
                self.tree_view.expand(self.model.index(row, 0))

        selected_keys = set(state.get("selected_keys", set()) or set())
        valid_selected_indexes = [index_map[key] for key in selected_keys if key in index_map]
        target_key = focus_key or state.get("current_key")

        if not valid_selected_indexes and not target_key:
            if state.get("preserve_empty_selection", False):
                self._suspend_selection_sync = True
                try:
                    if self.tree_view.selectionModel():
                        self.tree_view.selectionModel().clearSelection()
                        self.tree_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.NoUpdate)
                finally:
                    self._suspend_selection_sync = False
                if emit_selection:
                    self._emit_selection_cleared()
                return
            if self.model and self.model.rowCount() > 0:
                target_key = self.model.index(0, 0).data(ROLE_NODE_KEY)

        if target_key and target_key in index_map and target_key not in selected_keys:
            valid_selected_indexes.append(index_map[target_key])

        if valid_selected_indexes:
            selection_model = self.tree_view.selectionModel()
            self._suspend_selection_sync = True
            try:
                selection_model.clearSelection()
                for index in valid_selected_indexes:
                    selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)

                current_index = index_map[target_key] if target_key in index_map else valid_selected_indexes[0]
                self._expand_index_ancestors(current_index)
                selection_model.setCurrentIndex(current_index, QItemSelectionModel.NoUpdate)
            finally:
                self._suspend_selection_sync = False

            self.tree_view.setFocus()
            self.tree_view.scrollTo(current_index)
            if emit_selection:
                self._emit_selection_for_index(current_index)
            return

        if not target_key or target_key not in index_map:
            if emit_selection:
                self._emit_selection_cleared()
            return

        index = index_map[target_key]
        self._suspend_selection_sync = True
        try:
            self._expand_index_ancestors(index)
            self.tree_view.selectionModel().setCurrentIndex(
                index,
                QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            )
        finally:
            self._suspend_selection_sync = False
        self.tree_view.setFocus()
        self.tree_view.scrollTo(index)
        if emit_selection:
            self._emit_selection_for_index(index)

    def _expand_index_ancestors(self, index):
        current = index
        while current.isValid():
            self.tree_view.expand(current)
            current = current.parent()

    def _build_index_map(self):
        index_map = {}
        if not self.model:
            return index_map

        def walk(parent_index):
            rows = self.model.rowCount(parent_index)
            for row in range(rows):
                index = self.model.index(row, 0, parent_index)
                key = index.data(ROLE_NODE_KEY)
                if key:
                    index_map[key] = index
                walk(index)

        walk(QModelIndex())
        return index_map

    # ------------------------------------------------------------------ #
    #  Library management                                                 #
    # ------------------------------------------------------------------ #

    def on_add_library(self):
        start_dir = self.library_specs[0]["root_path"] if self.library_specs else ""
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Animation Library Root Folder",
            start_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if not chosen:
            return

        chosen = os.path.normpath(chosen)
        for spec in self.library_specs:
            if _normalize_path(spec["root_path"]) == _normalize_path(chosen):
                QMessageBox.information(self, "Library Exists", "This library path is already connected.")
                return

        default_name = os.path.basename(chosen) or "Library"
        name, ok = QInputDialog.getText(
            self,
            "Library Name",
            "Display name:",
            QLineEdit.Normal,
            default_name
        )
        if not ok:
            return

        name = (name or "").strip() or default_name

        answer = QMessageBox.question(
            self,
            "Library Type",
            "Is this a shared/network library?\n\n"
            "Choose Yes for shared/public storage.\n"
            "Choose No for a local WIP library.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        is_network = (answer == QMessageBox.Yes)

        spec = self._make_library_spec(name, chosen, is_network)
        self.library_specs.append(spec)
        self._save_widget_state()
        self._rebuild_model(keep_state=True, focus_key=self._make_node_key({
            "node_type": NODE_LIBRARY,
            "library_id": spec["id"],
        }))

    # ------------------------------------------------------------------ #
    #  Selection                                                          #
    # ------------------------------------------------------------------ #

    def _bind_selection_model(self):
        selection_model = self.tree_view.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._on_tree_selection_changed)

    def _on_tree_selection_changed(self, selected, deselected):
        if self._suspend_selection_sync:
            return

        selection_model = self.tree_view.selectionModel()
        if not selection_model:
            self._emit_selection_cleared()
            return

        selected_rows = selection_model.selectedRows()
        if len(selected_rows) > 1:
            # Keep the tree multi-selection for batch folder operations, but the
            # middle file panel only responds to a single selected source.
            self._emit_selection_cleared()
            return

        current_index = selection_model.currentIndex()
        if current_index.isValid() and selection_model.isSelected(current_index):
            self._emit_selection_for_index(current_index)
            return

        if len(selected_rows) == 1:
            only_index = selected_rows[0]
            selection_model.setCurrentIndex(only_index, QItemSelectionModel.NoUpdate)
            self._emit_selection_for_index(only_index)
            return

        self._emit_selection_cleared()

    def _emit_selection_cleared(self):
        self.selection_cleared.emit()

    def _emit_selection_for_index(self, index):
        if not index.isValid():
            self._emit_selection_cleared()
            return

        node_data = index.data(ROLE_NODE_DATA) or {}
        node_type = node_data.get("node_type")

        if self.view_mode == VIEW_PHYSICAL:
            folder_path = node_data.get("path") or node_data.get("root_path")
            if folder_path:
                self.folder_selected.emit(folder_path)
            return

        if node_type not in (NODE_LIBRARY, NODE_CATEGORY):
            return

        payload = self._build_category_selection_payload(node_data)
        self.category_selected.emit(payload)

    def _build_category_selection_payload(self, node_data):
        library = self._find_library(node_data.get("library_id"))
        asset_paths = []
        if library and node_data.get("node_type") == NODE_CATEGORY:
            config = self._load_category_config(library)
            asset_paths = self._collect_category_asset_paths(
                config,
                node_data.get("category_id"),
                library["root_path"]
            )

        return {
            "library_id": node_data.get("library_id"),
            "library_name": library["name"] if library else "",
            "root_path": library["root_path"] if library else "",
            "category_id": node_data.get("category_id"),
            "category_name": node_data.get("name"),
            "is_library_root": node_data.get("node_type") == NODE_LIBRARY,
            "asset_paths": asset_paths,
        }

    def _get_selected_indexes(self):
        selection_model = self.tree_view.selectionModel()
        if not selection_model:
            return []
        return list(selection_model.selectedRows())

    def _indexes_to_node_data(self, indexes):
        nodes = []
        for index in indexes:
            if not index.isValid():
                continue
            node_data = index.data(ROLE_NODE_DATA)
            if node_data:
                nodes.append(node_data)
        return nodes

    def _is_node_covered_by_parent(self, node_data, selected_keys):
        current_index = self._index_for_node(node_data)
        if not current_index.isValid():
            return False

        parent_index = current_index.parent()
        while parent_index.isValid():
            parent_key = parent_index.data(ROLE_NODE_KEY)
            if parent_key in selected_keys:
                return True
            parent_index = parent_index.parent()
        return False

    def _get_effective_selected_indexes(self, fallback_node_data=None):
        selected_indexes = self._get_selected_indexes()
        if not selected_indexes and fallback_node_data:
            fallback_index = self._index_for_node(fallback_node_data)
            if fallback_index.isValid():
                selected_indexes = [fallback_index]

        selected_keys = set()
        for index in selected_indexes:
            key = index.data(ROLE_NODE_KEY)
            if key:
                selected_keys.add(key)

        effective = []
        for index in selected_indexes:
            node_data = index.data(ROLE_NODE_DATA) or {}
            if not self._is_node_covered_by_parent(node_data, selected_keys):
                effective.append(index)
        return effective

    def _get_effective_selected_nodes(self, fallback_node_data=None):
        return self._indexes_to_node_data(self._get_effective_selected_indexes(fallback_node_data))

    def _selection_is_all_physical_deletable(self, node_list):
        if not node_list:
            return False
        for node_data in node_list:
            if node_data.get("node_type") != NODE_PHYSICAL:
                return False
            if node_data.get("is_root_library_node"):
                return False
        return True

    def _selection_is_all_categories(self, node_list):
        if not node_list:
            return False
        for node_data in node_list:
            if node_data.get("node_type") != NODE_CATEGORY:
                return False
        return True

    def _index_for_node(self, node_data):
        node_key = self._make_node_key(node_data)
        if not node_key:
            return QModelIndex()
        return self._index_for_key(node_key)

    def _index_for_key(self, node_key):
        return self._build_index_map().get(node_key, QModelIndex())

    def _refresh_selected_libraries(self, fallback_node_data=None):
        targets = self._get_effective_selected_nodes(fallback_node_data)
        library_ids = []
        for node_data in targets:
            library_id = node_data.get("library_id")
            if library_id and library_id not in library_ids:
                library_ids.append(library_id)

        if not library_ids and fallback_node_data:
            library_id = fallback_node_data.get("library_id")
            if library_id:
                library_ids.append(library_id)

        if not library_ids:
            self.refresh_tree()
            return

        if len(library_ids) == 1:
            focus_key = self._make_node_key(targets[0]) if targets else None
            self.refresh_tree(library_ids[0], focus_key=focus_key)
            return

        focus_key = self._make_node_key(targets[0]) if targets else None
        self.refresh_tree(focus_key=focus_key)

    def _apply_selection_keys(self, selected_keys, current_key=None):
        index_map = self._build_index_map()
        valid_indexes = [index_map[key] for key in selected_keys if key in index_map]

        self._suspend_selection_sync = True
        try:
            selection_model = self.tree_view.selectionModel()
            if not selection_model:
                return

            selection_model.clearSelection()
            for index in valid_indexes:
                selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)

            current_index = index_map.get(current_key, QModelIndex())
            if not current_index.isValid() and valid_indexes:
                current_index = valid_indexes[0]

            selection_model.setCurrentIndex(current_index, QItemSelectionModel.NoUpdate)
        finally:
            self._suspend_selection_sync = False

    # ------------------------------------------------------------------ #
    #  Context menu / actions                                             #
    # ------------------------------------------------------------------ #

    def _on_context_menu(self, pos):
        index = self.tree_view.indexAt(pos)
        if not index.isValid():
            return

        clicked_key = index.data(ROLE_NODE_KEY)
        preselected_keys = set(getattr(self.tree_view, "_right_click_selected_keys", set()) or set())
        preselected_hit = bool(clicked_key and clicked_key in preselected_keys)

        if preselected_hit:
            self._apply_selection_keys(preselected_keys, current_key=clicked_key)
        else:
            self._apply_selection_keys(set([clicked_key]) if clicked_key else set(), current_key=clicked_key)

        self.tree_view._right_click_selected_keys = set()
        self.tree_view._right_click_index_key = None
        self.tree_view.setFocus()

        selected_indexes = self._get_selected_indexes()
        selected_count = len(selected_indexes)
        effective_indexes = self._get_effective_selected_indexes()
        effective_nodes = self._indexes_to_node_data(effective_indexes)
        effective_count = len(effective_nodes)
        node_data = index.data(ROLE_NODE_DATA) or {}
        node_type = node_data.get("node_type")

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #cccccc;
                border: 1px solid #555555;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 6px 28px 6px 16px;
                background-color: transparent;
                color: #cccccc;
            }
            QMenu::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #666666;
            }
        """)

        is_library_node = (node_type == NODE_LIBRARY)
        has_single_target = (effective_count == 1)
        has_single_visual_target = (selected_count == 1)

        if self.view_mode == VIEW_PHYSICAL:
            new_label = "New Folder"
            refresh_label = "Refresh Selected" if selected_count > 1 else "Refresh"
            reveal_allowed = has_single_visual_target and has_single_target
            rename_allowed = has_single_visual_target and has_single_target and (node_type in (NODE_LIBRARY, NODE_PHYSICAL))
            delete_allowed = self._selection_is_all_physical_deletable(effective_nodes)
            remove_library_allowed = has_single_visual_target and has_single_target and is_library_node
            create_allowed = has_single_visual_target and has_single_target
        else:
            new_label = "New Category"
            refresh_label = "Refresh Selected" if selected_count > 1 else "Refresh"
            reveal_allowed = has_single_visual_target and has_single_target and is_library_node
            rename_allowed = has_single_visual_target and has_single_target and (node_type in (NODE_LIBRARY, NODE_CATEGORY))
            delete_allowed = self._selection_is_all_categories(effective_nodes)
            remove_library_allowed = has_single_visual_target and has_single_target and is_library_node
            create_allowed = has_single_visual_target and has_single_target

        if self.view_mode == VIEW_PHYSICAL:
            new_asset_menu = menu.addMenu("New")
            new_asset_menu.setEnabled(create_allowed)
            new_asset_menu.addAction(
                self._make_action(menu, "Animation", lambda: self._request_new_asset(node_data, "animation_local"))
            )
            new_asset_menu.addAction(
                self._make_action(menu, "Template", lambda: self._request_new_asset(node_data, "animation_full_biped"))
            )
            new_asset_menu.addAction(
                self._make_action(menu, "Pose", lambda: self._request_new_asset(node_data, "pose"))
            )
            menu.addSeparator()

        create_action = self._make_action(menu, new_label, lambda: self._create_child(node_data))
        create_action.setEnabled(create_allowed)
        menu.addAction(create_action)

        if rename_allowed:
            rename_label = "Rename Library" if is_library_node else "Rename"
            menu.addAction(self._make_action(menu, rename_label, lambda: self._rename_node(node_data)))

        if is_library_node:
            move_up_action = self._make_action(menu, "Move Library Up", lambda: self._move_library(node_data, -1))
            move_down_action = self._make_action(menu, "Move Library Down", lambda: self._move_library(node_data, 1))
            move_up_action.setEnabled(has_single_visual_target and has_single_target and self._can_move_library(node_data.get("library_id"), -1))
            move_down_action.setEnabled(has_single_visual_target and has_single_target and self._can_move_library(node_data.get("library_id"), 1))
            menu.addAction(move_up_action)
            menu.addAction(move_down_action)

        if delete_allowed:
            menu.addAction(self._make_action(menu, "Delete", lambda: self._delete_node(node_data)))

        if self.view_mode == VIEW_CATEGORY:
            if node_type == NODE_CATEGORY:
                import_files_action = self._make_action(menu, "Import Folder Files...", lambda: self._import_folder_files(node_data))
                import_tree_action = self._make_action(menu, "Import Folder Tree...", lambda: self._import_folder_tree(node_data))
                import_files_action.setEnabled(has_single_visual_target and has_single_target)
                import_tree_action.setEnabled(has_single_visual_target and has_single_target)
                menu.addAction(import_files_action)
                menu.addAction(import_tree_action)
                clean_action = self._make_action(menu, "Clean Invalid References", lambda: self._clean_invalid_category_refs(node_data))
                clean_action.setEnabled(self._selection_is_all_categories(effective_nodes))
                menu.addAction(clean_action)
            elif is_library_node:
                import_as_category_action = self._make_action(menu, "Import Folder as New Category...", lambda: self._import_folder_as_category(node_data))
                import_as_category_action.setEnabled(has_single_visual_target and has_single_target)
                menu.addAction(import_as_category_action)

        if remove_library_allowed:
            menu.addAction(self._make_action(menu, "Remove Library", lambda: self._remove_library(node_data)))

        reveal_action = self._make_action(menu, "Reveal in Explorer", lambda: self._reveal_in_explorer(node_data))
        reveal_action.setEnabled(reveal_allowed)
        menu.addAction(reveal_action)

        menu.addAction(self._make_action(menu, refresh_label, lambda: self._refresh_selected_libraries(node_data)))
        global_pos = self.tree_view.viewport().mapToGlobal(pos)
        menu.exec_(global_pos)

    def _make_action(self, parent, text, callback):
        action = QAction(text, parent)
        action.triggered.connect(callback)
        return action

    def _request_new_asset(self, node_data, asset_type):
        if self.view_mode != VIEW_PHYSICAL:
            return

        effective_nodes = self._get_effective_selected_nodes(node_data)
        if len(effective_nodes) != 1:
            return

        node_data = effective_nodes[0]
        folder_path = node_data.get("path") or node_data.get("root_path")
        if not folder_path:
            return
        self.new_asset_requested.emit(asset_type, folder_path)

    def _on_key_action_requested(self, action_name):
        index = self.tree_view.currentIndex()
        if not index.isValid():
            selected_indexes = self._get_selected_indexes()
            index = selected_indexes[0] if selected_indexes else QModelIndex()
        if not index.isValid():
            return
        node_data = index.data(ROLE_NODE_DATA) or {}

        if action_name == "rename":
            self._rename_node(node_data)
        elif action_name == "delete":
            self._delete_node(node_data)
        elif action_name == "refresh":
            self._refresh_selected_libraries(node_data)

    # ------------------------------------------------------------------ #
    #  Physical tree actions                                              #
    # ------------------------------------------------------------------ #

    def _create_child(self, node_data):
        if self.view_mode == VIEW_PHYSICAL:
            self._create_physical_folder(node_data)
        else:
            self._create_category(node_data)

    def _rename_node(self, node_data):
        effective_nodes = self._get_effective_selected_nodes(node_data)
        if len(effective_nodes) != 1:
            QMessageBox.information(self, "Rename Not Supported", "Batch rename is not supported in the tree.")
            return
        node_data = effective_nodes[0]
        if node_data.get("node_type") == NODE_LIBRARY:
            self._rename_library(node_data)
            return
        if self.view_mode == VIEW_PHYSICAL:
            self._rename_physical_folder(node_data)
        else:
            self._rename_category(node_data)

    def _delete_node(self, node_data):
        if self.view_mode == VIEW_PHYSICAL:
            self._delete_selected_physical_folders(node_data)
        else:
            self._delete_selected_categories(node_data)

    def _remove_library(self, node_data):
        library_id = node_data.get("library_id")
        library = self._find_library(library_id)
        if not library:
            return

        answer = QMessageBox.question(
            self,
            "Remove Library",
            "This will remove the library from the tree only.\n"
            "It will NOT delete the real folder on disk.\n\n"
            "Library:\n{0}\n\n"
            u"Do you want to continue?".format(_to_text(library.get("name", u""))),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return

        self.library_specs = [spec for spec in self.library_specs if spec.get("id") != library_id]
        self._save_widget_state()
        self._rebuild_model(keep_state=False, emit_selection=True)

    def _rename_library(self, node_data):
        library = self._find_library(node_data.get("library_id"))
        if not library:
            return

        current_name = _to_text(library.get("name", u"")).strip()
        name, ok = QInputDialog.getText(
            self,
            "Rename Library",
            "Display name:",
            QLineEdit.Normal,
            current_name
        )
        if not ok:
            return

        name = _to_text(name or u"").strip()
        if not name or name == current_name:
            return

        library["name"] = name
        focus_key = self._make_node_key({
            "node_type": NODE_LIBRARY,
            "library_id": library["id"],
        })
        self._save_widget_state()
        self._rebuild_model(keep_state=False, focus_key=focus_key, emit_selection=True)
        self._announce_status(_format_text("Renamed library to '{0}'", name))

    def _can_move_library(self, library_id, offset):
        index = self._library_index(library_id)
        if index < 0:
            return False
        target_index = index + offset
        return 0 <= target_index < len(self.library_specs)

    def _move_library(self, node_data, offset):
        library_id = node_data.get("library_id")
        index = self._library_index(library_id)
        if index < 0:
            return

        target_index = index + offset
        if target_index < 0 or target_index >= len(self.library_specs):
            return

        spec = self.library_specs.pop(index)
        self.library_specs.insert(target_index, spec)
        self._save_widget_state()
        self._rebuild_model(
            keep_state=False,
            focus_key=self._make_node_key({
                "node_type": NODE_LIBRARY,
                "library_id": library_id,
            }),
            emit_selection=True
        )
        self._announce_status(_format_text("Moved library '{0}'", _to_text(spec.get("name", u"Library"))))

    def _create_physical_folder(self, node_data):
        parent_path = node_data.get("path") or node_data.get("root_path")
        if not parent_path:
            return

        name, ok = QInputDialog.getText(
            self,
            "New Folder",
            "Folder name:",
            QLineEdit.Normal,
            "New Folder"
        )
        if not ok:
            return

        name = _sanitize_name(name)
        if not name:
            return

        new_path = os.path.join(parent_path, name)
        if os.path.exists(new_path):
            QMessageBox.warning(self, "Folder Exists", "A folder with this name already exists.")
            return

        focus_key = self._make_node_key({
            "node_type": NODE_PHYSICAL,
            "library_id": node_data.get("library_id"),
            "relative_path": os.path.relpath(new_path, node_data.get("root_path")),
        })
        try:
            os.makedirs(new_path)
            self.refresh_tree(
                node_data.get("library_id"),
                focus_key=focus_key,
                extra_expand_keys=[self._make_node_key(node_data)]
            )
        except Exception as exc:
            self._show_filesystem_error("Could not create folder", exc)

    def _rename_physical_folder(self, node_data):
        if node_data.get("is_root_library_node"):
            QMessageBox.information(self, "Rename Blocked", "Library root folders cannot be renamed from the tree.")
            return

        old_path = node_data.get("path")
        if not old_path:
            return

        current_name = os.path.basename(old_path)
        name, ok = QInputDialog.getText(
            self,
            "Rename Folder",
            "Folder name:",
            QLineEdit.Normal,
            current_name
        )
        if not ok:
            return

        name = _sanitize_name(name)
        if not name or name == current_name:
            return

        new_path = os.path.join(os.path.dirname(old_path), name)
        if os.path.exists(new_path):
            QMessageBox.warning(self, "Folder Exists", "A folder with this name already exists.")
            return

        focus_key = self._make_node_key({
            "node_type": NODE_PHYSICAL,
            "library_id": node_data.get("library_id"),
            "relative_path": os.path.relpath(new_path, node_data.get("root_path")),
        })
        try:
            os.rename(old_path, new_path)
            self.refresh_tree(node_data.get("library_id"), focus_key=focus_key)
        except Exception as exc:
            self._show_filesystem_error("Could not rename folder", exc)

    def _delete_physical_folder(self, node_data):
        if node_data.get("is_root_library_node"):
            QMessageBox.information(self, "Delete Blocked", "Library root folders cannot be deleted from the tree.")
            return

        folder_path = node_data.get("path")
        if not folder_path:
            return

        answer = QMessageBox.warning(
            self,
            "Delete Folder",
            "This will permanently delete the real folder on disk and all files inside it.\n\n"
            "Folder:\n{0}\n\n"
            "This operation is dangerous and cannot be undone.\n"
            u"Do you want to continue?".format(_to_text(folder_path)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return

        parent_path = os.path.dirname(folder_path)
        relative_parent = os.path.relpath(parent_path, node_data.get("root_path"))
        focus_key = self._make_node_key({
            "node_type": NODE_LIBRARY if relative_parent == "." else NODE_PHYSICAL,
            "library_id": node_data.get("library_id"),
            "relative_path": "" if relative_parent == "." else relative_parent,
        })
        try:
            shutil.rmtree(folder_path)
            self.refresh_tree(node_data.get("library_id"), focus_key=focus_key)
        except Exception as exc:
            self._show_filesystem_error("Could not delete folder", exc)

    def _reveal_in_explorer(self, node_data):
        effective_nodes = self._get_effective_selected_nodes(node_data)
        if len(effective_nodes) != 1:
            QMessageBox.information(
                self,
                "Reveal Not Supported",
                "Reveal in Explorer only supports a single selected node."
            )
            return

        node_data = effective_nodes[0]
        path = node_data.get("path") or node_data.get("root_path")
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Path Missing", "The folder no longer exists on disk.")
            return

        try:
            os.startfile(path)
        except Exception as exc:
            self._show_filesystem_error("Could not open Explorer", exc)

    def _delete_selected_physical_folders(self, node_data):
        targets = self._get_effective_selected_nodes(node_data)
        if not self._selection_is_all_physical_deletable(targets):
            return

        if len(targets) == 1:
            self._delete_physical_folder(targets[0])
            return

        lines = []
        for target in targets[:12]:
            lines.append(_to_text(target.get("path", u"")))
        extra_count = len(targets) - len(lines)
        if extra_count > 0:
            lines.append(_format_text("... and {0} more", extra_count))

        answer = QMessageBox.warning(
            self,
            "Delete Folders",
            _format_text(
                "This will permanently delete the selected real folders on disk and all files inside them.\n\n"
                "{0}\n\n"
                "Covered child selections are already ignored.\n"
                "This operation is dangerous and cannot be undone.\n"
                "Do you want to continue?",
                u"\n".join(lines)
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return

        deleted_count = 0
        focus_key = None
        library_ids = []
        for target in targets:
            folder_path = target.get("path")
            if not folder_path or not os.path.isdir(folder_path):
                continue

            parent_path = os.path.dirname(folder_path)
            relative_parent = os.path.relpath(parent_path, target.get("root_path"))
            if focus_key is None:
                focus_key = self._make_node_key({
                    "node_type": NODE_LIBRARY if relative_parent == "." else NODE_PHYSICAL,
                    "library_id": target.get("library_id"),
                    "relative_path": "" if relative_parent == "." else relative_parent,
                })

            try:
                shutil.rmtree(folder_path)
                deleted_count += 1
                library_id = target.get("library_id")
                if library_id and library_id not in library_ids:
                    library_ids.append(library_id)
            except Exception as exc:
                self._show_filesystem_error("Could not delete folder", exc)
                return

        if deleted_count <= 0:
            return

        if len(library_ids) == 1:
            self.refresh_tree(library_ids[0], focus_key=focus_key)
        else:
            self.refresh_tree(focus_key=focus_key)
        self._announce_status(_format_text("Deleted {0} folder(s)", deleted_count))

    # ------------------------------------------------------------------ #
    #  Category actions                                                   #
    # ------------------------------------------------------------------ #

    def _create_category(self, node_data):
        library = self._find_library(node_data.get("library_id"))
        if not library:
            return

        name, ok = QInputDialog.getText(
            self,
            "New Category",
            "Category name:",
            QLineEdit.Normal,
            "New Category"
        )
        if not ok:
            return

        name = _sanitize_name(name)
        if not name:
            return

        config = self._load_category_config(library)
        category_id = self._make_unique_category_id(config, name)
        category = {
            "id": category_id,
            "name": name,
            "parent_id": node_data.get("category_id") if node_data.get("node_type") == NODE_CATEGORY else None,
            "children": [],
            "asset_paths": [],
        }
        config["categories"][category_id] = category

        if category["parent_id"]:
            parent_category = config["categories"].get(category["parent_id"])
            if parent_category is not None:
                parent_category.setdefault("children", []).append(category_id)
        else:
            config.setdefault("root_order", []).append(category_id)

        focus_key = self._make_node_key({
            "node_type": NODE_CATEGORY,
            "library_id": library["id"],
            "category_id": category_id,
        })
        try:
            self._save_category_config(library, config)
            self.refresh_tree(library["id"], focus_key=focus_key)
        except Exception as exc:
            self._show_filesystem_error("Could not save category config", exc)

    def _rename_category(self, node_data):
        library = self._find_library(node_data.get("library_id"))
        category_id = node_data.get("category_id")
        if not library or not category_id:
            return

        config = self._load_category_config(library)
        category = config["categories"].get(category_id)
        if not category:
            return

        name, ok = QInputDialog.getText(
            self,
            "Rename Category",
            "Category name:",
            QLineEdit.Normal,
            category.get("name", "")
        )
        if not ok:
            return

        name = _sanitize_name(name)
        if not name or name == category.get("name"):
            return

        category["name"] = name
        focus_key = self._make_node_key(node_data)
        try:
            self._save_category_config(library, config)
            self.refresh_tree(library["id"], focus_key=focus_key)
        except Exception as exc:
            self._show_filesystem_error("Could not save category config", exc)

    def _delete_category(self, node_data):
        library = self._find_library(node_data.get("library_id"))
        category_id = node_data.get("category_id")
        if not library or not category_id:
            return

        answer = QMessageBox.warning(
            self,
            "Delete Category",
            "This will delete the virtual category and its child categories.\n"
            "Real folders and real animation files on disk will NOT be deleted.\n\n"
            "Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return

        config = self._load_category_config(library)
        self._remove_category_subtree(config, category_id)

        focus_key = self._make_node_key({
            "node_type": NODE_LIBRARY,
            "library_id": library["id"],
        })
        try:
            self._save_category_config(library, config)
            self.refresh_tree(library["id"], focus_key=focus_key)
        except Exception as exc:
            self._show_filesystem_error("Could not save category config", exc)

    def _delete_selected_categories(self, node_data):
        targets = self._get_effective_selected_nodes(node_data)
        if not self._selection_is_all_categories(targets):
            return

        if len(targets) == 1:
            self._delete_category(targets[0])
            return

        answer = QMessageBox.warning(
            self,
            "Delete Categories",
            "This will delete the selected virtual categories and their child categories.\n"
            "Real folders and real animation files on disk will NOT be deleted.\n\n"
            "Covered child selections are already ignored.\n"
            "Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return

        targets_by_library = {}
        for target in targets:
            targets_by_library.setdefault(target.get("library_id"), []).append(target)

        first_focus_key = None
        deleted_count = 0
        saved_library_ids = []
        for library_id, library_targets in targets_by_library.items():
            library = self._find_library(library_id)
            if not library:
                continue

            config = self._load_category_config(library)
            for target in library_targets:
                if first_focus_key is None:
                    first_focus_key = self._make_node_key({
                        "node_type": NODE_LIBRARY,
                        "library_id": library["id"],
                    })
                if config.get("categories", {}).get(target.get("category_id")):
                    self._remove_category_subtree(config, target.get("category_id"))
                    deleted_count += 1

            try:
                self._save_category_config(library, config)
                saved_library_ids.append(library_id)
            except Exception as exc:
                self._show_filesystem_error("Could not save category config", exc)
                return

        if deleted_count <= 0:
            return

        if len(saved_library_ids) == 1:
            self.refresh_tree(saved_library_ids[0], focus_key=first_focus_key)
        else:
            self.refresh_tree(focus_key=first_focus_key)
        self._announce_status(_format_text("Deleted {0} category node(s)", deleted_count))

    def _import_folder_files(self, node_data):
        """Import animation files from a chosen folder (non-recursive) into category."""
        library = self._find_library(node_data.get("library_id"))
        if not library or node_data.get("node_type") != NODE_CATEGORY:
            return

        start_dir = library.get("root_path", "")
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Folder (files only, no subfolders)",
            start_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if not chosen:
            return

        refs = self._collect_animation_refs_from_folder(chosen, library["root_path"], recursive=False)
        if not refs:
            self._announce_status("No animation files found in folder.", STATUS_MESSAGE_DURATION_MS)
            return

        config = self._load_category_config(library)
        category = config["categories"].get(node_data.get("category_id"))
        if not category:
            return

        existing = set(category.get("asset_paths", []))
        category["asset_paths"] = sorted(existing.union(refs), key=lambda v: v.lower())

        try:
            self._save_category_config(library, config)
            self.refresh_tree(library["id"], focus_key=self._make_node_key(node_data))
            self._announce_status(_format_text("Added {0} file(s) to '{1}'", len(refs), _to_text(category.get("name", u""))))
        except Exception as exc:
            self._show_filesystem_error("Could not save category config", exc)

    def _import_folder_tree(self, node_data):
        """Import animation files from a chosen folder recursively into category."""
        library = self._find_library(node_data.get("library_id"))
        if not library or node_data.get("node_type") != NODE_CATEGORY:
            return

        start_dir = library.get("root_path", "")
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Folder (includes subfolders)",
            start_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if not chosen:
            return

        refs = self._collect_animation_refs_from_folder(chosen, library["root_path"], recursive=True)
        if not refs:
            self._announce_status("No animation files found in folder tree.", STATUS_MESSAGE_DURATION_MS)
            return

        config = self._load_category_config(library)
        category = config["categories"].get(node_data.get("category_id"))
        if not category:
            return

        existing = set(category.get("asset_paths", []))
        category["asset_paths"] = sorted(existing.union(refs), key=lambda v: v.lower())

        try:
            self._save_category_config(library, config)
            self.refresh_tree(library["id"], focus_key=self._make_node_key(node_data))
            self._announce_status(_format_text("Added {0} file(s) to '{1}'", len(refs), _to_text(category.get("name", u""))))
        except Exception as exc:
            self._show_filesystem_error("Could not save category config", exc)

    def _import_folder_as_category(self, node_data):
        """Create a new virtual category from a physical folder and import its files recursively."""
        library = self._find_library(node_data.get("library_id"))
        if not library or node_data.get("node_type") != NODE_LIBRARY:
            return

        start_dir = library.get("root_path", "")
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Import as New Category",
            start_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if not chosen:
            return

        normalized = _normalize_path(chosen)
        root = _normalize_path(library["root_path"])
        if normalized == root or not normalized.startswith(root + os.sep):
            QMessageBox.warning(
                self,
                "Folder Outside Library",
                "The selected folder must be inside this library."
            )
            return

        refs = self._collect_animation_refs_from_folder(chosen, library["root_path"], recursive=True)
        name = os.path.basename(chosen) or "Imported"

        config = self._load_category_config(library)
        category_id = self._make_unique_category_id(config, name)
        category = {
            "id": category_id,
            "name": name,
            "parent_id": None,
            "children": [],
            "asset_paths": sorted(refs, key=lambda v: v.lower()),
        }
        config["categories"][category_id] = category
        config.setdefault("root_order", []).append(category_id)

        focus_key = self._make_node_key({
            "node_type": NODE_CATEGORY,
            "library_id": library["id"],
            "category_id": category_id,
        })
        try:
            self._save_category_config(library, config)
            self.refresh_tree(library["id"], focus_key=focus_key)
            self._announce_status(_format_text("Created category '{0}' with {1} file(s)", name, len(refs)))
        except Exception as exc:
            self._show_filesystem_error("Could not save category config", exc)

    def _clean_invalid_category_refs(self, node_data):
        """Remove references to missing files from selected category subtrees."""
        targets = self._get_effective_selected_nodes(node_data)
        if not self._selection_is_all_categories(targets):
            return

        first_focus_key = self._make_node_key(targets[0]) if targets else None
        total_removed = 0
        saved_library_ids = []
        targets_by_library = {}
        for target in targets:
            targets_by_library.setdefault(target.get("library_id"), []).append(target)

        for library_id, library_targets in targets_by_library.items():
            library = self._find_library(library_id)
            if not library:
                continue

            config = self._load_category_config(library)
            removed_for_library = 0
            for target in library_targets:
                removed_for_library += self._clean_invalid_refs_in_category_subtree(
                    config,
                    target.get("category_id"),
                    library["root_path"]
                )

            if removed_for_library <= 0:
                continue

            try:
                self._save_category_config(library, config)
                saved_library_ids.append(library_id)
                total_removed += removed_for_library
            except Exception as exc:
                self._show_filesystem_error("Could not save category config", exc)
                return

        if total_removed <= 0:
            self._announce_status("No invalid references found.", STATUS_MESSAGE_DURATION_MS)
            return

        if len(saved_library_ids) == 1:
            self.refresh_tree(saved_library_ids[0], focus_key=first_focus_key)
        else:
            self.refresh_tree(focus_key=first_focus_key)
        self._announce_status(_format_text("Removed {0} invalid reference(s)", total_removed))

    def _clean_invalid_refs_in_category_subtree(self, config, category_id, root_path):
        category = config.get("categories", {}).get(category_id)
        if not category:
            return 0

        removed = 0
        valid = []
        for rel_path in list(category.get("asset_paths", [])):
            full_path = os.path.normpath(os.path.join(root_path, rel_path))
            if os.path.isfile(full_path):
                valid.append(rel_path)
            else:
                removed += 1
        category["asset_paths"] = sorted(valid, key=lambda v: v.lower())

        for child_id in category.get("children", []):
            removed += self._clean_invalid_refs_in_category_subtree(config, child_id, root_path)
        return removed

    def _collect_animation_refs_from_folder(self, folder_path, library_root, recursive=False):
        """Collect relative paths of animation files in folder. Returns list of rel paths."""
        refs = []
        root_norm = _normalize_path(library_root)

        def scan(current):
            try:
                entries = os.listdir(current)
            except Exception:
                return
            for entry in entries:
                path = os.path.join(current, entry)
                if os.path.isfile(path):
                    ext = os.path.splitext(entry)[1].lower()
                    if ext in ANIMATION_EXTENSIONS:
                        norm = _normalize_path(path)
                        if norm.startswith(root_norm + os.sep) or norm == root_norm:
                            refs.append(os.path.relpath(path, library_root))
                elif recursive and os.path.isdir(path):
                    scan(path)

        scan(folder_path)
        return refs

    # ------------------------------------------------------------------ #
    #  Drag and drop                                                      #
    # ------------------------------------------------------------------ #

    def _on_item_drop_requested(self, source_data, target_data):
        if not source_data or not target_data:
            return

        source_nodes = source_data if isinstance(source_data, list) else [source_data]
        if self.view_mode == VIEW_PHYSICAL:
            self._move_physical_folders(source_nodes, target_data)
        else:
            if len(source_nodes) > 1:
                QMessageBox.information(
                    self,
                    "Move Not Supported",
                    "Batch move is not supported for Category View in this version."
                )
                return
            self._move_category_node(source_nodes[0], target_data)

    def _on_external_files_dropped(self, file_paths, target_data):
        if self.view_mode == VIEW_PHYSICAL:
            self._move_dropped_files_to_physical_folder(file_paths, target_data)
            return

        if self.view_mode != VIEW_CATEGORY:
            return
        if not target_data or target_data.get("node_type") != NODE_CATEGORY:
            return

        library = self._find_library(target_data.get("library_id"))
        if not library:
            return

        config = self._load_category_config(library)
        category = config["categories"].get(target_data.get("category_id"))
        if not category:
            return

        accepted_refs = []
        rejected_paths = []
        for path in file_paths:
            normalized = _normalize_path(path)
            root = _normalize_path(library["root_path"])
            if not normalized.startswith(root + os.sep) and normalized != root:
                rejected_paths.append(path)
                continue
            if not os.path.isfile(path):
                rejected_paths.append(path)
                continue
            accepted_refs.append(os.path.relpath(path, library["root_path"]))

        if not accepted_refs:
            QMessageBox.warning(
                self,
                "Drop Rejected",
                "Only files inside the same library can be assigned to a virtual category."
            )
            return

        existing = set(category.get("asset_paths", []))
        category["asset_paths"] = sorted(existing.union(accepted_refs), key=lambda value: value.lower())

        try:
            self._save_category_config(library, config)
            self.refresh_tree(library["id"], focus_key=self._make_node_key(target_data))
        except Exception as exc:
            self._show_filesystem_error("Could not save category config", exc)
            return

        message = _format_text(
            "Added {0} asset(s) to '{1}'",
            len(accepted_refs),
            _to_text(category.get("name", u"Category"))
        )
        if rejected_paths:
            message += _format_text(". {0} ignored outside this library.", len(rejected_paths))
        self._announce_status(message, 4500 if rejected_paths else STATUS_MESSAGE_DURATION_MS)

    def _move_dropped_files_to_physical_folder(self, file_paths, target_data):
        if not target_data or target_data.get("node_type") not in (NODE_LIBRARY, NODE_PHYSICAL):
            return

        library = self._find_library(target_data.get("library_id"))
        if not library:
            return

        target_folder = target_data.get("path") or target_data.get("root_path")
        if not target_folder or not os.path.isdir(target_folder):
            return

        root_norm = _normalize_path(library["root_path"])
        move_plan = []
        rejected_paths = []
        planned_destinations = set()

        for path in file_paths or []:
            if not path or not os.path.isfile(path):
                rejected_paths.append(path)
                continue

            ext = os.path.splitext(path)[1].lower()
            if ext not in ANIMATION_EXTENSIONS:
                rejected_paths.append(path)
                continue

            source_norm = _normalize_path(path)
            if not self._path_is_under_root(source_norm, root_norm):
                rejected_paths.append(path)
                continue

            destination_path = os.path.join(target_folder, os.path.basename(path))
            destination_norm = _normalize_path(destination_path)
            if destination_norm == source_norm:
                continue
            if destination_norm in planned_destinations or os.path.exists(destination_path):
                rejected_paths.append(path)
                continue

            planned_destinations.add(destination_norm)
            move_plan.append((path, destination_path))

        if not move_plan:
            QMessageBox.warning(
                self,
                "Drop Rejected",
                "Only animation files inside the same library can be moved to a physical folder,\n"
                "and the target cannot already contain files with the same names."
            )
            return

        moved_pairs = []
        failed = []
        preview_failures = []
        for source_path, destination_path in move_plan:
            try:
                shutil.move(source_path, destination_path)
                moved_pairs.append((source_path, destination_path))
                try:
                    preview_utils.move_preview(source_path, destination_path)
                except Exception as exc:
                    preview_failures.append((source_path, exc))
            except Exception as exc:
                failed.append((source_path, exc))

        if moved_pairs:
            try:
                self._replace_asset_references_for_moves_in_library(library, moved_pairs)
            except Exception as exc:
                self._show_filesystem_error("Could not save category config", exc)
                return

            self.refresh_tree(
                library["id"],
                focus_key=self._make_node_key({
                    "node_type": target_data.get("node_type"),
                    "library_id": target_data.get("library_id"),
                    "relative_path": target_data.get("relative_path", ""),
                })
            )

        moved_count = len(moved_pairs)
        if moved_count:
            message = _format_text(
                "Moved {0} file(s) to '{1}'",
                moved_count,
                _to_text(target_data.get("name") or os.path.basename(target_folder) or u"Folder")
            )
            if rejected_paths:
                message += _format_text(". {0} skipped.", len(rejected_paths))
            if failed:
                message += _format_text(". {0} failed.", len(failed))
            self._announce_status(message, 4500 if rejected_paths or failed else STATUS_MESSAGE_DURATION_MS)

        if failed:
            details = []
            for path, exc in failed[:5]:
                details.append("{0}\n{1}".format(_to_text(os.path.basename(path)), _to_text(exc)))
            if len(failed) > len(details):
                details.append(_format_text("... and {0} more", len(failed) - len(details)))
            QMessageBox.warning(
                self,
                "Move Failed",
                "Some files could not be moved:\n\n{0}".format("\n\n".join(details))
            )

        if preview_failures:
            details = []
            for path, exc in preview_failures[:5]:
                details.append("{0}\n{1}".format(_to_text(os.path.basename(path)), _to_text(exc)))
            if len(preview_failures) > len(details):
                details.append(_format_text("... and {0} more", len(preview_failures) - len(details)))
            QMessageBox.warning(
                self,
                "Preview Move Failed",
                "Some preview images could not be moved:\n\n{0}".format("\n\n".join(details))
            )

    def _replace_asset_references_for_moves_in_library(self, spec, path_pairs):
        root_path = spec.get("root_path")
        if not root_path or not path_pairs:
            return 0

        root_norm = _normalize_path(root_path)
        replacements = {}
        for old_path, new_path in path_pairs:
            old_norm = _normalize_path(old_path)
            new_norm = _normalize_path(new_path)
            if not self._path_is_under_root(old_norm, root_norm):
                continue
            if not self._path_is_under_root(new_norm, root_norm):
                continue
            replacements[old_norm] = os.path.relpath(new_path, root_path)

        if not replacements:
            return 0

        config = self._load_category_config(spec)
        replaced = 0
        changed = False

        for category in config.get("categories", {}).values():
            refs = list(category.get("asset_paths", []))
            if not refs:
                continue

            updated_refs = []
            category_changed = False
            for rel_path in refs:
                full_path = os.path.normpath(os.path.join(root_path, rel_path))
                new_rel = replacements.get(_normalize_path(full_path))
                if new_rel is not None:
                    updated_refs.append(new_rel)
                    replaced += 1
                    category_changed = True
                else:
                    updated_refs.append(rel_path)

            if category_changed:
                category["asset_paths"] = sorted(set(updated_refs), key=lambda value: value.lower())
                changed = True

        if changed:
            self._save_category_config(spec, config)
        return replaced

    def _move_physical_folder(self, source_data, target_data):
        if source_data.get("node_type") != NODE_PHYSICAL:
            return
        if target_data.get("node_type") not in (NODE_LIBRARY, NODE_PHYSICAL):
            return
        if source_data.get("library_id") != target_data.get("library_id"):
            QMessageBox.warning(self, "Cross-Library Move Blocked", "Folders cannot be moved across different libraries.")
            return

        source_path = source_data.get("path")
        target_path = target_data.get("path") or target_data.get("root_path")
        if not source_path or not target_path:
            return

        normalized_source = _normalize_path(source_path)
        normalized_target = _normalize_path(target_path)
        if normalized_target == normalized_source:
            return
        if normalized_target.startswith(normalized_source + os.sep):
            QMessageBox.warning(self, "Move Blocked", "A folder cannot be moved into itself or its own child folder.")
            return

        destination_path = os.path.join(target_path, os.path.basename(source_path))
        if _normalize_path(destination_path) == normalized_source:
            return
        if os.path.exists(destination_path):
            QMessageBox.warning(self, "Folder Exists", "The target location already contains a folder with the same name.")
            return

        library = self._find_library(source_data.get("library_id"))
        if not library:
            return

        new_relative_path = os.path.relpath(destination_path, library["root_path"])
        focus_key = self._make_node_key({
            "node_type": NODE_PHYSICAL,
            "library_id": library["id"],
            "relative_path": new_relative_path,
        })
        target_expand_key = self._make_node_key(target_data)
        try:
            shutil.move(source_path, target_path)
            self._schedule_refresh_tree(
                library["id"],
                focus_key=focus_key,
                extra_expand_keys=[target_expand_key],
                delay_ms=80
            )
            self._announce_status(
                _format_text("Moved folder '{0}'", _to_text(os.path.basename(source_path))),
                STATUS_MESSAGE_DURATION_MS
            )
        except Exception as exc:
            self._show_filesystem_error("Could not move folder", exc)

    def _move_physical_folders(self, source_nodes, target_data):
        targets = self._get_effective_nodes_for_drag(source_nodes)
        if not targets:
            return

        if len(targets) == 1:
            self._move_physical_folder(targets[0], target_data)
            return

        if target_data.get("node_type") not in (NODE_LIBRARY, NODE_PHYSICAL):
            return

        library_ids = []
        normalized_target = _normalize_path(target_data.get("path") or target_data.get("root_path"))
        destination_names = set()
        move_plan = []

        for source_data in targets:
            if source_data.get("node_type") != NODE_PHYSICAL:
                QMessageBox.information(self, "Move Blocked", "Batch move only supports physical folders.")
                return

            library_id = source_data.get("library_id")
            if library_id not in library_ids:
                library_ids.append(library_id)
            if library_id != target_data.get("library_id"):
                QMessageBox.warning(self, "Cross-Library Move Blocked", "Folders cannot be moved across different libraries.")
                return

            source_path = source_data.get("path")
            target_path = target_data.get("path") or target_data.get("root_path")
            if not source_path or not target_path:
                return

            normalized_source = _normalize_path(source_path)
            if normalized_target == normalized_source:
                continue
            if normalized_target.startswith(normalized_source + os.sep):
                QMessageBox.warning(self, "Move Blocked", "A folder cannot be moved into itself or its own child folder.")
                return

            folder_name = os.path.basename(source_path)
            destination_path = os.path.join(target_path, folder_name)
            normalized_destination = _normalize_path(destination_path)
            if normalized_destination == normalized_source:
                continue
            if folder_name.lower() in destination_names or os.path.exists(destination_path):
                QMessageBox.warning(self, "Folder Exists", "The target location already contains a folder with the same name.")
                return

            destination_names.add(folder_name.lower())
            move_plan.append((source_data, source_path, target_path, destination_path))

        if not move_plan:
            return

        library = self._find_library(target_data.get("library_id"))
        if not library:
            return

        moved_count = 0
        focus_key = None
        target_expand_key = self._make_node_key(target_data)
        for source_data, source_path, target_path, destination_path in move_plan:
            try:
                shutil.move(source_path, target_path)
                moved_count += 1
                if focus_key is None:
                    focus_key = self._make_node_key({
                        "node_type": NODE_PHYSICAL,
                        "library_id": library["id"],
                        "relative_path": os.path.relpath(destination_path, library["root_path"]),
                    })
            except Exception as exc:
                self._show_filesystem_error("Could not move folder", exc)
                return

        self._schedule_refresh_tree(
            library["id"],
            focus_key=focus_key,
            extra_expand_keys=[target_expand_key],
            delay_ms=80
        )
        self._announce_status(_format_text("Moved {0} folder(s)", moved_count), STATUS_MESSAGE_DURATION_MS)

    def _move_category_node(self, source_data, target_data):
        if source_data.get("node_type") != NODE_CATEGORY:
            return
        if target_data.get("node_type") not in (NODE_LIBRARY, NODE_CATEGORY):
            return
        if source_data.get("library_id") != target_data.get("library_id"):
            QMessageBox.warning(self, "Cross-Library Move Blocked", "Categories cannot be moved across different libraries.")
            return

        library = self._find_library(source_data.get("library_id"))
        if not library:
            return

        config = self._load_category_config(library)
        source_id = source_data.get("category_id")
        target_id = target_data.get("category_id") if target_data.get("node_type") == NODE_CATEGORY else None
        if source_id == target_id:
            return
        if target_id and self._category_is_descendant(config, source_id, target_id):
            QMessageBox.warning(self, "Move Blocked", "A category cannot be moved into itself or its own child category.")
            return

        source_category = config["categories"].get(source_id)
        if not source_category:
            return

        old_parent_id = source_category.get("parent_id")
        if old_parent_id:
            old_parent = config["categories"].get(old_parent_id)
            if old_parent:
                old_parent["children"] = [cid for cid in old_parent.get("children", []) if cid != source_id]
        else:
            config["root_order"] = [cid for cid in config.get("root_order", []) if cid != source_id]

        source_category["parent_id"] = target_id
        if target_id:
            target_category = config["categories"].get(target_id)
            if target_category is not None and source_id not in target_category.get("children", []):
                target_category.setdefault("children", []).append(source_id)
        else:
            config.setdefault("root_order", []).append(source_id)

        try:
            self._save_category_config(library, config)
            self._schedule_refresh_tree(
                library["id"],
                focus_key=self._make_node_key(source_data),
                extra_expand_keys=[self._make_node_key(target_data)]
            )
            self._announce_status(
                _format_text("Moved category '{0}'", _to_text(source_category.get("name", u"Category"))),
                STATUS_MESSAGE_DURATION_MS
            )
        except Exception as exc:
            self._show_filesystem_error("Could not save category config", exc)

    def _get_effective_nodes_for_drag(self, source_nodes):
        if not source_nodes:
            return []

        selected_indexes = self._get_selected_indexes()
        if selected_indexes:
            selected_keys = set()
            for index in selected_indexes:
                key = index.data(ROLE_NODE_KEY)
                if key:
                    selected_keys.add(key)

            effective = []
            for source_data in source_nodes:
                if not self._is_node_covered_by_parent(source_data, selected_keys):
                    effective.append(source_data)
            return effective

        selected_keys = set()
        for source_data in source_nodes:
            key = self._make_node_key(source_data)
            if key:
                selected_keys.add(key)

        effective = []
        for source_data in source_nodes:
            if not self._is_node_covered_by_parent(source_data, selected_keys):
                effective.append(source_data)
        return effective

    # ------------------------------------------------------------------ #
    #  Refresh                                                            #
    # ------------------------------------------------------------------ #

    def refresh_tree(self, library_id=None, focus_key=None, extra_expand_keys=None):
        state = self._capture_view_state()
        if library_id:
            self.category_configs.pop(library_id, None)
            refreshed = self._refresh_library_branch(library_id)
        else:
            self.category_configs = {}
            refreshed = False

        if not refreshed:
            self.category_configs = {} if library_id is None else self.category_configs
            self._rebuild_model(keep_state=False, emit_selection=False)

        self._restore_view_state(
            state,
            focus_key=focus_key,
            emit_selection=True,
            extra_expand_keys=extra_expand_keys
        )
        self._last_refresh_at = time.time()

    def _schedule_refresh_tree(self, library_id=None, focus_key=None, extra_expand_keys=None, delay_ms=0):
        QTimer.singleShot(
            int(delay_ms),
            lambda: self.refresh_tree(
                library_id=library_id,
                focus_key=focus_key,
                extra_expand_keys=extra_expand_keys
            )
        )

    def request_window_activation_refresh(self):
        library_id = self._get_active_library_id()
        if not library_id:
            return

        now = time.time()
        if now - self._last_refresh_at < AUTO_REFRESH_MIN_INTERVAL_SECONDS:
            return

        self._pending_auto_refresh_library_id = library_id
        self._auto_refresh_timer.start(AUTO_REFRESH_DEBOUNCE_MS)

    def _run_auto_refresh(self):
        library_id = self._pending_auto_refresh_library_id
        self._pending_auto_refresh_library_id = None
        if not library_id:
            return

        try:
            self.refresh_tree(library_id=library_id)
        except Exception as exc:
            _safe_print("Window activation refresh failed:", exc)

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _find_library(self, library_id):
        for spec in self.library_specs:
            if spec["id"] == library_id:
                return spec
        return None

    def _library_index(self, library_id):
        for index, spec in enumerate(self.library_specs):
            if spec.get("id") == library_id:
                return index
        return -1

    def _get_active_library_id(self):
        index = self.tree_view.currentIndex()
        if index.isValid():
            node_data = index.data(ROLE_NODE_DATA) or {}
            library_id = node_data.get("library_id")
            if library_id:
                return library_id
        if self.library_specs:
            return self.library_specs[0].get("id")
        return None

    def _refresh_library_branch(self, library_id):
        library = self._find_library(library_id)
        if not library or not self.model:
            return False

        library_item = None
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            node_data = item.data(ROLE_NODE_DATA) or {}
            if node_data.get("node_type") == NODE_LIBRARY and node_data.get("library_id") == library_id:
                library_item = item
                break

        if library_item is None:
            return False

        node_data = dict(library_item.data(ROLE_NODE_DATA) or {})
        node_data.update({
            "id": library["id"],
            "name": library["name"],
            "library_id": library["id"],
            "node_type": NODE_LIBRARY,
            "view_mode": self.view_mode,
            "root_path": library["root_path"],
            "path": library["root_path"],
            "is_network": library["is_network"],
            "watch_enabled": library["watch_enabled"],
            "category_file": library["category_file"],
            "relative_path": "",
            "is_root_library_node": True,
        })
        library_item.setText(library["name"])
        library_item.setData(node_data, ROLE_NODE_DATA)
        library_item.setData(self._make_node_key(node_data), ROLE_NODE_KEY)
        self._apply_item_style(library_item, NODE_LIBRARY, node_data)

        if library_item.rowCount():
            library_item.removeRows(0, library_item.rowCount())

        if self.view_mode == VIEW_PHYSICAL:
            self._populate_physical_children(library, library_item, library["root_path"])
        else:
            self._populate_category_children(library, library_item)
        return True

    def _build_category_stats(self, config, root_path):
        categories = config.get("categories", {})
        memo = {}

        def collect_asset_refs(category_id):
            if category_id in memo:
                return memo[category_id]

            category = categories.get(category_id) or {}
            asset_refs = set()
            for rel_path in category.get("asset_paths", []):
                full_path = os.path.normpath(os.path.join(root_path, rel_path))
                if os.path.isfile(full_path):
                    asset_refs.add(_normalize_path(full_path))

            for child_id in category.get("children", []):
                asset_refs.update(collect_asset_refs(child_id))

            memo[category_id] = asset_refs
            return asset_refs

        stats = {}
        for category_id in categories.keys():
            refs = collect_asset_refs(category_id)
            stats[category_id] = {
                "count": len(refs),
                "is_empty": len(refs) == 0,
            }
        return stats

    def _format_category_label(self, name, stats):
        count = int(stats.get("count", 0))
        if count <= 0:
            return _format_text("{0} (Empty)", name)
        return _format_text("{0} ({1})", name, count)

    def _announce_status(self, message, timeout_ms=STATUS_MESSAGE_DURATION_MS):
        if not message:
            return

        try:
            self.status_message_requested.emit(_to_text(message), int(timeout_ms))
        except Exception as exc:
            _safe_print("Status message failed:", exc)

    def _show_filesystem_error(self, title, exc):
        title_text = _to_text(title)
        exc_text = _to_text(exc)
        if isinstance(exc, PermissionError):
            message = (
                title_text + ":\n\n"
                "Permission denied. The shared folder may be read-only,\n"
                "the directory may be locked by another user, or files inside it are still in use.\n\n"
                "System message:\n" + exc_text
            )
        else:
            message = title_text + ":\n\n" + exc_text
        QMessageBox.critical(self, "Error", message)

    def _make_unique_category_id(self, config, name):
        base = "".join(char.lower() if char.isalnum() else "_" for char in name).strip("_") or "category"
        candidate = base
        counter = 1
        categories = config.get("categories", {})
        while candidate in categories:
            counter += 1
            candidate = u"{0}_{1}".format(base, counter)
        return candidate

    def _remove_category_subtree(self, config, category_id):
        category = config["categories"].get(category_id)
        if not category:
            return

        for child_id in list(category.get("children", [])):
            self._remove_category_subtree(config, child_id)

        parent_id = category.get("parent_id")
        if parent_id:
            parent_category = config["categories"].get(parent_id)
            if parent_category:
                parent_category["children"] = [cid for cid in parent_category.get("children", []) if cid != category_id]
        else:
            config["root_order"] = [cid for cid in config.get("root_order", []) if cid != category_id]

        config["categories"].pop(category_id, None)

    def _collect_category_asset_paths(self, config, category_id, root_path):
        if not category_id or category_id not in config.get("categories", {}):
            return []

        result = []
        seen = set()

        def walk(current_id):
            category = config["categories"].get(current_id)
            if not category:
                return
            for rel_path in category.get("asset_paths", []):
                full_path = os.path.normpath(os.path.join(root_path, rel_path))
                key = _normalize_path(full_path)
                if key not in seen and os.path.isfile(full_path):
                    seen.add(key)
                    result.append(full_path)
            for child_id in category.get("children", []):
                walk(child_id)

        walk(category_id)
        return sorted(result, key=lambda value: os.path.basename(value).lower())

    def _category_is_descendant(self, config, source_id, maybe_descendant_id):
        category = config["categories"].get(source_id)
        if not category:
            return False

        for child_id in category.get("children", []):
            if child_id == maybe_descendant_id:
                return True
            if self._category_is_descendant(config, child_id, maybe_descendant_id):
                return True
        return False

    def _physical_node_id(self, library_id, relative_path):
        return u"physical::{0}::{1}".format(_to_text(library_id), _normalize_path(relative_path))

    def _make_node_key(self, node_data):
        node_type = node_data.get("node_type")
        library_id = node_data.get("library_id")
        if node_type == NODE_LIBRARY:
            return u"library::{0}".format(_to_text(library_id))
        if node_type == NODE_PHYSICAL:
            return u"physical::{0}::{1}".format(
                _to_text(library_id),
                _normalize_path(node_data.get("relative_path", ""))
            )
        if node_type == NODE_CATEGORY:
            return u"category::{0}::{1}".format(_to_text(library_id), _to_text(node_data.get("category_id")))
        return u""

    # ------------------------------------------------------------------ #
    #  Public helpers                                                     #
    # ------------------------------------------------------------------ #

    def _on_view_mode_changed(self):
        self.view_mode = self.view_mode_combo.currentData()
        if self.view_mode not in (VIEW_PHYSICAL, VIEW_CATEGORY):
            self.view_mode = VIEW_PHYSICAL
        self._save_widget_state()
        self._rebuild_model(keep_state=True, emit_selection=True)

    def set_root_path(self, path):
        """Backward-compatible helper: replace libraries with one local library."""
        if not path:
            return
        path = os.path.normpath(path)
        self.library_specs = [self._make_library_spec(os.path.basename(path) or "Animation Library", path, False)]
        self.root_path = path
        self._save_widget_state()
        self._rebuild_model(keep_state=False, emit_selection=False)

    def get_current_folder(self):
        """Return the currently selected physical folder path, or None."""
        index = self.tree_view.currentIndex()
        if not index.isValid():
            return self.library_specs[0]["root_path"] if self.library_specs else None

        node_data = index.data(ROLE_NODE_DATA) or {}
        if self.view_mode != VIEW_PHYSICAL:
            return None
        return node_data.get("path") or node_data.get("root_path")

    def replace_asset_reference(self, old_path, new_path):
        """Update category asset references after a file rename."""
        if not old_path or not new_path:
            return 0

        total_replaced = 0
        refreshed_library_ids = []
        for spec in self.library_specs:
            try:
                replaced = self._replace_asset_reference_in_library(spec, old_path, new_path)
            except Exception as exc:
                self._show_filesystem_error("Could not save category config", exc)
                return total_replaced

            if replaced > 0:
                total_replaced += replaced
                refreshed_library_ids.append(spec["id"])

        if refreshed_library_ids:
            if len(refreshed_library_ids) == 1:
                self.refresh_tree(refreshed_library_ids[0])
            else:
                self.refresh_tree()
            self._announce_status(_format_text("Updated {0} category reference(s)", total_replaced))

        return total_replaced

    def remove_asset_references(self, file_paths):
        """Remove category asset references after files are deleted."""
        targets = [path for path in (file_paths or []) if path]
        if not targets:
            return 0

        total_removed = 0
        refreshed_library_ids = []
        for spec in self.library_specs:
            try:
                removed = self._remove_asset_references_in_library(spec, targets)
            except Exception as exc:
                self._show_filesystem_error("Could not save category config", exc)
                return total_removed

            if removed > 0:
                total_removed += removed
                refreshed_library_ids.append(spec["id"])

        if refreshed_library_ids:
            if len(refreshed_library_ids) == 1:
                self.refresh_tree(refreshed_library_ids[0])
            else:
                self.refresh_tree()
            self._announce_status(_format_text("Removed {0} category reference(s)", total_removed))

        return total_removed

    def _replace_asset_reference_in_library(self, spec, old_path, new_path):
        root_path = spec.get("root_path")
        if not root_path:
            return 0

        old_norm = _normalize_path(old_path)
        new_norm = _normalize_path(new_path)
        root_norm = _normalize_path(root_path)
        if not self._path_is_under_root(old_norm, root_norm):
            return 0
        if not self._path_is_under_root(new_norm, root_norm):
            return 0

        rel_old = os.path.relpath(old_path, root_path)
        rel_new = os.path.relpath(new_path, root_path)
        if _normalize_path(rel_old) == _normalize_path(rel_new):
            return 0

        config = self._load_category_config(spec)
        replaced = 0
        changed = False

        for category in config.get("categories", {}).values():
            refs = list(category.get("asset_paths", []))
            if not refs:
                continue

            updated_refs = []
            category_changed = False
            for rel_path in refs:
                full_path = os.path.normpath(os.path.join(root_path, rel_path))
                if _normalize_path(full_path) == old_norm:
                    updated_refs.append(rel_new)
                    replaced += 1
                    category_changed = True
                else:
                    updated_refs.append(rel_path)

            if category_changed:
                category["asset_paths"] = sorted(set(updated_refs), key=lambda value: value.lower())
                changed = True

        if changed:
            self._save_category_config(spec, config)
        return replaced

    def _remove_asset_references_in_library(self, spec, file_paths):
        root_path = spec.get("root_path")
        if not root_path:
            return 0

        root_norm = _normalize_path(root_path)
        target_norms = set()
        for path in file_paths:
            path_norm = _normalize_path(path)
            if self._path_is_under_root(path_norm, root_norm):
                target_norms.add(path_norm)

        if not target_norms:
            return 0

        config = self._load_category_config(spec)
        removed = 0
        changed = False

        for category in config.get("categories", {}).values():
            refs = list(category.get("asset_paths", []))
            if not refs:
                continue

            updated_refs = []
            category_removed = 0
            for rel_path in refs:
                full_path = os.path.normpath(os.path.join(root_path, rel_path))
                if _normalize_path(full_path) in target_norms:
                    category_removed += 1
                else:
                    updated_refs.append(rel_path)

            if category_removed > 0:
                removed += category_removed
                category["asset_paths"] = sorted(updated_refs, key=lambda value: value.lower())
                changed = True

        if changed:
            self._save_category_config(spec, config)
        return removed

    def _path_is_under_root(self, path_norm, root_norm):
        if not path_norm or not root_norm:
            return False
        return path_norm == root_norm or path_norm.startswith(root_norm + os.sep)

# -*- coding: utf-8 -*-
"""
Middle Panel - Animation Grid Widget
Displays animations in a grid layout using QListWidget in IconMode.

Rules:
  - Only shows files with extensions: .bip, .xaf, .json
  - If no matching files exist the grid is empty (no placeholder items)
  - Each item stores its full file path in Qt.UserRole
"""

import os
import subprocess
import json
import zipfile

from PySide2.QtWidgets import (
    QListWidget, QListWidgetItem, QAbstractItemView, QMenu, QAction,
    QMessageBox, QInputDialog, QLineEdit, QApplication, QRubberBand
)
from PySide2.QtCore import Qt, Signal, QSize, QMimeData, QUrl, QModelIndex, QItemSelectionModel, QRect, QItemSelection
from PySide2.QtGui import QIcon, QPixmap, QColor, QPainter, QFont, QPen
from ..utils import preview_utils

try:
    text_type = unicode
except NameError:
    text_type = str


def _safe_print(*parts):
    values = []
    for part in parts:
        try:
            values.append(repr(part))
        except Exception:
            values.append("<unprintable>")
    print(" ".join(values))


# Only these extensions are shown in the grid
ANIMATION_EXTENSIONS = {'.bip', '.xaf', '.json', '.animx'}

# Short label drawn on the placeholder thumbnail, keyed by extension
_EXT_LABELS = {
    '.bip':   'BIP',
    '.xaf':   'XAF',
    '.json':  'JSON',
    '.animx': 'ANIMX',
}

# Background colours for placeholder thumbnails
_EXT_COLORS = {
    '.bip':   QColor(60,  90, 130),   # steel blue  - Biped legacy
    '.xaf':   QColor(80, 120,  60),   # olive green - XAF
    '.json':  QColor(120, 100, 50),   # amber       - pose
    '.animx': QColor(100,  55, 145),  # purple      - unified package
}

_ICON_SIZE_MIN = 64
_ICON_SIZE_MAX = 256
_ICON_SIZE_STEP = 16
_FILTER_ALL = "all"
_TYPE_ANIMATION = "animation"
_TYPE_POSE = "pose"
_TYPE_COLORS = {
    _TYPE_ANIMATION: QColor(135, 135, 135),
    _TYPE_POSE: QColor(135, 135, 135),
}
_ANIMATION_MODE_LOCAL = "local"
_ANIMATION_MODE_LIMB = "limb"
_ANIMATION_MODE_FULL_BIPED = "full_biped"
_ANIMATION_MODE_BADGES = {
    _ANIMATION_MODE_LOCAL: "AN",
    _ANIMATION_MODE_LIMB: "AN",
    _ANIMATION_MODE_FULL_BIPED: "TP",
}
_BADGE_FALLBACK = {
    '.json': 'PS',
    '.bip': 'TP',
    '.xaf': 'AN',
    '.animx': 'AN',
}


def _display_name_from_path(path):
    filename = os.path.basename(path or "")
    name = os.path.splitext(filename)[0]
    if name.lower().endswith("_pose"):
        name = name[:-5]
    return name


def _file_type_from_ext(ext):
    ext = (ext or "").lower()
    if ext == '.json':
        return _TYPE_POSE
    return _TYPE_ANIMATION


def _load_animx_manifest(path):
    if os.path.splitext(path or "")[1].lower() != '.animx':
        return None
    try:
        archive = zipfile.ZipFile(path, 'r')
    except Exception:
        return None
    try:
        manifest_bytes = archive.read("manifest.json")
    except Exception:
        archive.close()
        return None
    archive.close()
    try:
        return json.loads(manifest_bytes.decode('utf-8'))
    except Exception:
        return None


class AnimationGridWidget(QListWidget):
    """Animation grid view component"""

    # Emits list of full file paths for selected items
    animation_selected = Signal(list)
    status_message_requested = Signal(object, int)
    files_deleted = Signal(list)
    file_renamed = Signal(object, object)
    new_asset_requested = Signal(object, object)

    def __init__(self, icon_size=128):
        super(AnimationGridWidget, self).__init__()
        self.icon_size = self._clamp_icon_size(icon_size)
        self.current_folder = None
        self._loaded_paths = []
        self._source_name = "Category"
        self._type_filter = _FILTER_ALL
        self._blank_press_active = False
        self._rubber_band_active = False
        self._rubber_band_origin = None
        self._rubber_band_selection_rows = None
        self._init_ui()
        # Grid starts empty - no placeholder data

    def _init_ui(self):
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(self.icon_size, self.icon_size))
        self.setSpacing(self._spacing_for_icon_size(self.icon_size))
        self.setGridSize(self._grid_item_size())
        self.setResizeMode(QListWidget.Adjust)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        if hasattr(self, "setSelectionRectVisible"):
            try:
                self.setSelectionRectVisible(False)
            except Exception:
                pass
        self._rubber_band = QRubberBand(QRubberBand.Rectangle, self.viewport())
        self._rubber_band.hide()
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def _clamp_icon_size(self, value):
        try:
            value = int(value)
        except Exception:
            value = 128
        return max(_ICON_SIZE_MIN, min(_ICON_SIZE_MAX, value))

    def _spacing_for_icon_size(self, icon_size):
        return max(8, int(icon_size / 10))

    def _grid_item_size(self):
        horizontal_padding = max(16, int(self.icon_size / 6))
        text_height = max(22, int(self.icon_size / 5))
        bottom_padding = max(10, int(self.icon_size / 12))
        cell_width = self.icon_size + horizontal_padding
        cell_height = self.icon_size + text_height + bottom_padding
        return QSize(cell_width, cell_height)

    def set_type_filter(self, filter_key):
        filter_key = text_type(filter_key or _FILTER_ALL).lower()
        if filter_key not in (_FILTER_ALL, _TYPE_ANIMATION, _TYPE_POSE):
            filter_key = _FILTER_ALL
        if filter_key == self._type_filter:
            return

        selected_paths = self.get_selected_paths()
        self._type_filter = filter_key
        self._refresh_view(select_paths=selected_paths, announce=False)
        self._announce_status("Filter: {0}".format(filter_key.title()))

    def _matches_type_filter(self, ext):
        if self._type_filter == _FILTER_ALL:
            return True
        return _file_type_from_ext(ext) == self._type_filter

    # ------------------------------------------------------------------ #
    #  Load from folder                                                   #
    # ------------------------------------------------------------------ #

    def load_animations(self, folder_path):
        """
        Scan *folder_path* and populate the grid with .bip / .xaf / .json files.
        If none are found the grid is left empty.

        Args:
            folder_path: absolute path to the selected library folder.
        """
        self.current_folder = folder_path
        self._loaded_paths = []
        self._source_name = folder_path or "Folder"
        self.clear()

        if not os.path.isdir(folder_path):
            _safe_print("Folder not found:", folder_path)
            return

        try:
            all_files = os.listdir(folder_path)
        except Exception as e:
            _safe_print("Cannot list folder:", e)
            return

        anim_files = sorted([
            f for f in all_files
            if os.path.isfile(os.path.join(folder_path, f))
            and os.path.splitext(f)[1].lower() in ANIMATION_EXTENSIONS
            and self._matches_type_filter(os.path.splitext(f)[1].lower())
        ])

        for filename in anim_files:
            full_path = os.path.join(folder_path, filename)
            display_name = _display_name_from_path(full_path)
            ext = os.path.splitext(filename)[1].lower()
            self._add_item(display_name, full_path, ext)

        _safe_print("Loaded animation files from folder:", folder_path, "count=", len(anim_files))

    def load_animation_paths(self, file_paths, source_name="Category"):
        """
        Populate the grid from an explicit list of file paths.

        Args:
            file_paths: iterable of absolute file paths.
            source_name: debug label for logging.
        """
        self.current_folder = None
        self._loaded_paths = [os.path.normpath(path) for path in (file_paths or []) if path]
        self._source_name = source_name or "Category"
        self.clear()

        valid_paths = []
        for path in file_paths or []:
            ext = os.path.splitext(path)[1].lower()
            if os.path.isfile(path) and ext in ANIMATION_EXTENSIONS and self._matches_type_filter(ext):
                valid_paths.append(os.path.normpath(path))

        for full_path in sorted(valid_paths, key=lambda value: os.path.basename(value).lower()):
            display_name = _display_name_from_path(full_path)
            filename = os.path.basename(full_path)
            ext = os.path.splitext(filename)[1].lower()
            self._add_item(display_name, full_path, ext)

        _safe_print("Loaded animation files from selection:", source_name, "count=", len(valid_paths))

    # ------------------------------------------------------------------ #
    #  Item factory                                                       #
    # ------------------------------------------------------------------ #

    def _add_item(self, display_name, full_path, ext):
        badge_text = self._asset_badge_text(full_path, ext)
        icon = self._make_icon(full_path, ext, badge_text=badge_text)
        item = QListWidgetItem(icon, display_name)
        item.setData(Qt.UserRole, full_path)
        item.setForeground(QColor(220, 220, 220))
        item.setSizeHint(self._grid_item_size())
        self.addItem(item)

    def _asset_badge_text(self, full_path, ext):
        if _file_type_from_ext(ext) == _TYPE_POSE:
            return "PS"
        if ext == '.bip':
            return _ANIMATION_MODE_BADGES[_ANIMATION_MODE_FULL_BIPED]
        manifest = _load_animx_manifest(full_path)
        if isinstance(manifest, dict):
            animation_mode = text_type(
                manifest.get("animation_mode") or _ANIMATION_MODE_LOCAL
            ).strip().lower()
            if animation_mode not in _ANIMATION_MODE_BADGES:
                if manifest.get("bipeds") and not manifest.get("biped_partial"):
                    animation_mode = _ANIMATION_MODE_FULL_BIPED
                else:
                    animation_mode = _ANIMATION_MODE_LOCAL
            return _ANIMATION_MODE_BADGES.get(animation_mode, "ANIM")
        return _BADGE_FALLBACK.get(ext, "FILE")

    def _draw_badge(self, painter, badge_text):
        if not badge_text:
            return
        font_size = max(6, int(self.icon_size / 18))
        badge_font = QFont("Arial", font_size, QFont.Bold)
        painter.setFont(badge_font)
        metrics = painter.fontMetrics()
        badge_rect = QRect(6, 4, max(18, int(self.icon_size / 4)), metrics.height() + 2)
        painter.setPen(QColor(235, 235, 235))
        painter.drawText(badge_rect, Qt.AlignLeft | Qt.AlignVCenter, badge_text)

    def _make_icon(self, full_path, ext, badge_text=None):
        """Generate a coloured thumbnail with a short text label."""
        preview_icon = self._make_preview_icon(full_path, badge_text=badge_text)
        if preview_icon is not None:
            return preview_icon

        label = _EXT_LABELS.get(ext, ext.upper().lstrip('.') or 'FILE')
        bg = QColor(58, 58, 58)
        frame_color = _TYPE_COLORS.get(_file_type_from_ext(ext), QColor(120, 120, 120))

        pixmap = QPixmap(self.icon_size, self.icon_size)
        pixmap.fill(bg)
        painter = QPainter(pixmap)
        painter.setFont(QFont("Arial", 22, QFont.Bold))
        painter.setPen(QColor(220, 220, 220))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, label)
        painter.setPen(QPen(frame_color, max(1, int(self.icon_size / 64))))
        painter.drawRect(pixmap.rect().adjusted(1, 1, -2, -2))
        self._draw_badge(painter, badge_text)
        painter.end()
        return QIcon(pixmap)

    def _make_preview_icon(self, full_path, badge_text=None):
        preview_path = preview_utils.get_preview_path(full_path)
        if not os.path.isfile(preview_path):
            return None

        source = QPixmap(preview_path)
        if source.isNull():
            return None

        ext = os.path.splitext(full_path)[1].lower()
        frame_color = _TYPE_COLORS.get(_file_type_from_ext(ext), QColor(120, 120, 120))
        canvas = QPixmap(self.icon_size, self.icon_size)
        canvas.fill(QColor(50, 50, 50))
        painter = QPainter(canvas)
        scaled = source.scaled(
            self.icon_size,
            self.icon_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        x = int((self.icon_size - scaled.width()) / 2)
        y = int((self.icon_size - scaled.height()) / 2)
        painter.drawPixmap(x, y, scaled)
        painter.setPen(QPen(frame_color, max(1, int(self.icon_size / 64))))
        painter.drawRect(canvas.rect().adjusted(1, 1, -2, -2))
        self._draw_badge(painter, badge_text)
        painter.end()
        return QIcon(canvas)

    # ------------------------------------------------------------------ #
    #  Selection                                                          #
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self):
        """Emit full file paths of selected items."""
        selected_items = self.selectedItems()
        paths = []
        for item in selected_items:
            path = item.data(Qt.UserRole)
            if path:
                paths.append(path)
        _safe_print("Animation selected:", [item.text() for item in selected_items])
        self.animation_selected.emit(paths)

    def mousePressEvent(self, event):
        if self._blank_press_active or self._rubber_band_active:
            self._finish_blank_drag_selection()

        clicked_item = self.itemAt(event.pos())
        if (
            event.button() == Qt.LeftButton and
            clicked_item is not None and
            (event.modifiers() & Qt.AltModifier)
        ):
            self._remove_item_from_selection(clicked_item)
            event.accept()
            return

        if (
            event.button() == Qt.LeftButton and
            clicked_item is None and
            event.modifiers() == Qt.NoModifier
        ):
            self._finish_blank_drag_selection()
            self._clear_selection()
            self._blank_press_active = True
            self._rubber_band_active = False
            self._rubber_band_origin = event.pos()
            self._rubber_band.setGeometry(QRect(self._rubber_band_origin, self._rubber_band_origin))
            event.accept()
            return
        super(AnimationGridWidget, self).mousePressEvent(event)

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
                self._update_rubber_band_selection(rect, emit_signal=False)
                event.accept()
                return

        super(AnimationGridWidget, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._blank_press_active:
            selection_rect = self._rubber_band.geometry() if self._rubber_band_active else QRect()
            should_apply_selection = self._rubber_band_active
            self._finish_blank_drag_selection()
            if should_apply_selection:
                self._rubber_band_selection_rows = None
                self._update_rubber_band_selection(selection_rect, emit_signal=True)
            self.viewport().update()
            event.accept()
            return
        super(AnimationGridWidget, self).mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = 0
            try:
                delta = event.angleDelta().y()
            except Exception:
                try:
                    delta = event.delta()
                except Exception:
                    delta = 0

            if delta > 0:
                self._change_icon_size(_ICON_SIZE_STEP)
            elif delta < 0:
                self._change_icon_size(-_ICON_SIZE_STEP)

            event.accept()
            return

        super(AnimationGridWidget, self).wheelEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self._finish_blank_drag_selection()
            self._clear_selection()
            event.accept()
            return
        if key == Qt.Key_F2:
            self._rename_selected_file()
            event.accept()
            return
        if key == Qt.Key_Delete:
            self._delete_selected_files()
            event.accept()
            return
        if key == Qt.Key_F5:
            self._refresh_view()
            event.accept()
            return
        super(AnimationGridWidget, self).keyPressEvent(event)

    def contextMenuEvent(self, event):
        clicked_item = self.itemAt(event.pos())
        if clicked_item is not None and not clicked_item.isSelected():
            self._select_single_item(clicked_item)

        selected_paths = self.get_selected_paths()
        selected_count = len(selected_paths)
        has_single = (selected_count == 1)
        has_selection = (selected_count > 0)
        can_refresh = bool(self.current_folder or self._loaded_paths or self.count() > 0)

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

        if self.current_folder:
            new_menu = menu.addMenu("New")
            new_menu.addAction(self._make_action(menu, "Animation", lambda: self._request_new_asset("animation_local")))
            new_menu.addAction(self._make_action(menu, "Template", lambda: self._request_new_asset("animation_full_biped")))
            new_menu.addAction(self._make_action(menu, "Pose", lambda: self._request_new_asset("pose")))
            menu.addSeparator()

        rename_action = self._make_action(menu, "Rename", self._rename_selected_file)
        rename_action.setEnabled(has_single)
        menu.addAction(rename_action)

        delete_action = self._make_action(menu, "Delete", self._delete_selected_files)
        delete_action.setEnabled(has_selection)
        menu.addAction(delete_action)

        reveal_action = self._make_action(menu, "Reveal in Explorer", self._reveal_selected_file)
        reveal_action.setEnabled(has_single)
        menu.addAction(reveal_action)

        refresh_action = self._make_action(menu, "Refresh", self._refresh_view)
        refresh_action.setEnabled(can_refresh)
        menu.addAction(refresh_action)

        menu.exec_(self.viewport().mapToGlobal(event.pos()))

    def _clear_selection(self):
        selection_model = self.selectionModel()
        if selection_model:
            selection_model.clearSelection()
            selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.NoUpdate)
        self._rubber_band_selection_rows = None

    def _finish_blank_drag_selection(self):
        self._blank_press_active = False
        self._rubber_band_active = False
        self._rubber_band_origin = None
        self._rubber_band.setGeometry(QRect())
        self._rubber_band.hide()
        self._rubber_band_selection_rows = None
        self.viewport().update()

    def _update_rubber_band_selection(self, rect, emit_signal):
        selection_model = self.selectionModel()
        if not selection_model:
            return

        hit_indexes = []
        hit_rows = []
        for row in range(self.count()):
            item = self.item(row)
            item_rect = self.visualItemRect(item)
            if item_rect.intersects(rect):
                hit_indexes.append(self.indexFromItem(item))
                hit_rows.append(row)

        row_signature = tuple(hit_rows)
        if row_signature == self._rubber_band_selection_rows:
            return
        self._rubber_band_selection_rows = row_signature

        selection = QItemSelection()
        for index in hit_indexes:
            selection.select(index, index)

        was_blocked = self.signalsBlocked()
        if not emit_signal:
            self.blockSignals(True)
        try:
            selection_model.select(selection, QItemSelectionModel.ClearAndSelect)
            if hit_indexes:
                selection_model.setCurrentIndex(hit_indexes[0], QItemSelectionModel.NoUpdate)
            else:
                selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.NoUpdate)
        finally:
            if not emit_signal and not was_blocked:
                self.blockSignals(False)

    def focusOutEvent(self, event):
        self._finish_blank_drag_selection()
        super(AnimationGridWidget, self).focusOutEvent(event)

    def hideEvent(self, event):
        self._finish_blank_drag_selection()
        super(AnimationGridWidget, self).hideEvent(event)

    def _select_single_item(self, item):
        if item is None:
            return
        self.clearSelection()
        item.setSelected(True)
        self.setCurrentItem(item)

    def _remove_item_from_selection(self, item):
        if item is None:
            return

        selection_model = self.selectionModel()
        if not selection_model:
            return

        index = self.indexFromItem(item)
        if not index.isValid():
            return

        selection_model.select(index, QItemSelectionModel.Deselect)
        current_index = selection_model.currentIndex()
        if current_index == index:
            selected_indexes = selection_model.selectedRows()
            next_index = selected_indexes[0] if selected_indexes else QModelIndex()
            selection_model.setCurrentIndex(next_index, QItemSelectionModel.NoUpdate)

    def get_selected_paths(self):
        """Return list of full paths for currently selected items."""
        result = []
        for item in self.selectedItems():
            path = item.data(Qt.UserRole)
            if path:
                result.append(path)
        return result

    # Backward-compat alias
    def get_selected_animations(self):
        return self.get_selected_paths()

    # ------------------------------------------------------------------ #
    #  Misc                                                               #
    # ------------------------------------------------------------------ #

    def clear_animations(self):
        self.clear()
        self.current_folder = None
        self._loaded_paths = []
        self._source_name = "Category"

    def _change_icon_size(self, delta):
        new_size = self._clamp_icon_size(self.icon_size + delta)
        if new_size == self.icon_size:
            return

        selected_paths = self.get_selected_paths()
        self.icon_size = new_size
        self.setIconSize(QSize(self.icon_size, self.icon_size))
        self.setSpacing(self._spacing_for_icon_size(self.icon_size))
        self.setGridSize(self._grid_item_size())
        self._refresh_view(select_paths=selected_paths)
        self._announce_status("Thumbnail size: {0}".format(self.icon_size))

    def _make_action(self, parent, text, callback):
        action = QAction(text, parent)
        action.triggered.connect(callback)
        return action

    def _request_new_asset(self, asset_type):
        if not self.current_folder:
            return
        self.new_asset_requested.emit(asset_type, self.current_folder)

    def _selected_single_path(self):
        paths = self.get_selected_paths()
        if len(paths) != 1:
            return None
        return paths[0]

    def _refresh_view(self, select_paths=None, announce=True):
        target_paths = [os.path.normpath(path) for path in (select_paths or []) if path]
        if self.current_folder:
            folder = self.current_folder
            self.load_animations(folder)
        else:
            self.load_animation_paths(self._loaded_paths, self._source_name)

        if target_paths:
            self._select_paths(target_paths)

        if announce:
            self._announce_status("File list refreshed.")

    def _select_paths(self, target_paths):
        if not target_paths:
            return

        normalized_targets = set([os.path.normpath(path) for path in target_paths])
        self.clearSelection()
        first_item = None
        for row in range(self.count()):
            item = self.item(row)
            path = item.data(Qt.UserRole)
            if path and os.path.normpath(path) in normalized_targets:
                item.setSelected(True)
                if first_item is None:
                    first_item = item

        if first_item is not None:
            self.setCurrentItem(first_item)

    def _rename_selected_file(self):
        old_path = self._selected_single_path()
        if not old_path:
            return

        if not os.path.isfile(old_path):
            QMessageBox.warning(self, "File Missing", "The selected file no longer exists on disk.")
            self._refresh_view()
            return

        folder_path = os.path.dirname(old_path)
        old_filename = os.path.basename(old_path)
        old_name, ext = os.path.splitext(old_filename)

        new_name, ok = QInputDialog.getText(
            self,
            "Rename File",
            "New file name:",
            QLineEdit.Normal,
            old_name
        )
        if not ok:
            return

        new_name = text_type(new_name).strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "File name cannot be empty.")
            return
        if any(token in new_name for token in ('\\', '/', ':', '*', '?', '"', '<', '>', '|')):
            QMessageBox.warning(self, "Invalid Name", "File name contains invalid characters.")
            return
        if new_name in ('.', '..'):
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid file name.")
            return

        new_filename = new_name + ext
        new_path = os.path.join(folder_path, new_filename)
        if os.path.normcase(os.path.normpath(new_path)) == os.path.normcase(os.path.normpath(old_path)):
            return
        if os.path.exists(new_path):
            QMessageBox.warning(self, "File Exists", "A file with the same name already exists.")
            return

        try:
            os.rename(old_path, new_path)
        except Exception as exc:
            QMessageBox.warning(self, "Rename Failed", "Could not rename file:\n\n{0}".format(text_type(exc)))
            return

        try:
            preview_utils.rename_preview(old_path, new_path)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Preview Rename Failed",
                "The main file was renamed, but the preview image could not be renamed:\n\n{0}".format(text_type(exc))
            )

        self._replace_loaded_path(old_path, new_path)
        self._refresh_view(select_paths=[new_path])
        self.file_renamed.emit(old_path, new_path)
        self._announce_status("Renamed file to {0}".format(new_filename))

    def _delete_selected_files(self):
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return

        names = [_display_name_from_path(path) for path in selected_paths]
        if len(names) == 1:
            message = (
                "This will permanently delete the selected file from disk.\n\n"
                "{0}\n\n"
                "This operation cannot be undone.\n"
                "Do you want to continue?"
            ).format(names[0])
            title = "Delete File"
        else:
            preview = names[:12]
            if len(names) > len(preview):
                preview.append("... and {0} more".format(len(names) - len(preview)))
            message = (
                "This will permanently delete the selected files from disk.\n\n"
                "{0}\n\n"
                "Batch delete is supported.\n"
                "This operation cannot be undone.\n"
                "Do you want to continue?"
            ).format("\n".join(preview))
            title = "Delete Files"

        answer = QMessageBox.warning(
            self,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return

        deleted = []
        failed = []
        preview_failures = []
        for path in selected_paths:
            try:
                if os.path.isfile(path):
                    os.remove(path)
                deleted.append(path)
                try:
                    preview_utils.delete_preview(path)
                except Exception as exc:
                    preview_failures.append((path, exc))
            except Exception as exc:
                failed.append((path, exc))

        if deleted:
            self._remove_loaded_paths(deleted)
            self._refresh_view()
            self.files_deleted.emit(deleted)
            self._announce_status("Deleted {0} file(s).".format(len(deleted)))

        if failed:
            details = []
            for path, exc in failed[:5]:
                details.append("{0}\n{1}".format(_display_name_from_path(path), text_type(exc)))
            if len(failed) > len(details):
                details.append("... and {0} more".format(len(failed) - len(details)))
            QMessageBox.warning(
                self,
                "Delete Failed",
                "Some files could not be deleted:\n\n{0}".format("\n\n".join(details))
            )

        if preview_failures:
            details = []
            for path, exc in preview_failures[:5]:
                details.append("{0}\n{1}".format(_display_name_from_path(path), text_type(exc)))
            if len(preview_failures) > len(details):
                details.append("... and {0} more".format(len(preview_failures) - len(details)))
            QMessageBox.warning(
                self,
                "Preview Delete Failed",
                "Some preview images could not be deleted:\n\n{0}".format("\n\n".join(details))
            )

    def _reveal_selected_file(self):
        path = self._selected_single_path()
        if not path:
            return

        if not os.path.exists(path):
            QMessageBox.warning(self, "Path Missing", "The selected file no longer exists on disk.")
            self._refresh_view()
            return

        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except Exception:
            try:
                os.startfile(os.path.dirname(path))
            except Exception as exc:
                QMessageBox.warning(self, "Reveal Failed", "Could not open Explorer:\n\n{0}".format(text_type(exc)))
                return

        self._announce_status("Opened file location in Explorer.")

    def _replace_loaded_path(self, old_path, new_path):
        old_norm = os.path.normcase(os.path.normpath(old_path))
        replaced = False
        updated = []
        for path in self._loaded_paths:
            path_norm = os.path.normcase(os.path.normpath(path))
            if path_norm == old_norm:
                updated.append(os.path.normpath(new_path))
                replaced = True
            else:
                updated.append(path)
        if not replaced and self.current_folder is None:
            updated.append(os.path.normpath(new_path))
        self._loaded_paths = updated

    def _remove_loaded_paths(self, deleted_paths):
        deleted_norms = set([os.path.normcase(os.path.normpath(path)) for path in deleted_paths])
        self._loaded_paths = [
            path for path in self._loaded_paths
            if os.path.normcase(os.path.normpath(path)) not in deleted_norms
        ]

    def _announce_status(self, message, timeout_ms=3000):
        if not message:
            return
        try:
            self.status_message_requested.emit(text_type(message), int(timeout_ms))
        except Exception:
            pass

    def mimeData(self, items):
        mime_data = super(AnimationGridWidget, self).mimeData(items)
        if mime_data is None:
            mime_data = QMimeData()

        paths = []
        urls = []
        for item in items:
            path = item.data(Qt.UserRole)
            if path:
                normalized = os.path.normpath(path)
                paths.append(normalized)
                urls.append(QUrl.fromLocalFile(normalized))

        if urls:
            mime_data.setUrls(urls)
        if paths:
            mime_data.setText("\n".join(paths))
        return mime_data

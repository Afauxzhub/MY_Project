# -*- coding: utf-8 -*-
"""
Main window class.
Integrates the left folder tree, middle animation grid, and right operation panel.
"""

from PySide2.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QToolButton, QMenu, QActionGroup, QMessageBox
from PySide2.QtCore import Qt, QSize, QTimer

from .folder_tree_widget import FolderTreeWidget
from .animation_grid_widget import AnimationGridWidget
from .operation_panel_widget import OperationPanelWidget
from ..config.settings import get_settings


class AnimationLibraryWindow(QMainWindow):
    """Animation Action Library main window."""

    def __init__(self, parent=None):
        super(AnimationLibraryWindow, self).__init__(parent)
        self.settings = get_settings()
        self._current_type_filter = "all"
        self._pending_save_type = None
        self._save_folder = None
        self._init_ui()
        self._apply_dark_theme()
        self._connect_signals()
        self._restore_geometry()

    # ------------------------------------------------------------------ #
    #  UI construction                                                    #
    # ------------------------------------------------------------------ #

    def _init_ui(self):
        self.setWindowTitle("Animation Library")
        self.setMinimumSize(QSize(1000, 600))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        # Left column: folder tree (now a QWidget container)
        self.folder_tree = FolderTreeWidget(settings=self.settings)
        splitter.addWidget(self.folder_tree)

        # Middle column: filter bar + animation grid
        self.middle_panel = QWidget()
        middle_layout = QVBoxLayout(self.middle_panel)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(4)

        middle_toolbar = QWidget()
        toolbar_layout = QHBoxLayout(middle_toolbar)
        toolbar_layout.setContentsMargins(6, 6, 6, 0)
        toolbar_layout.setSpacing(4)
        toolbar_layout.addStretch()

        self.middle_filter_button = QToolButton()
        self.middle_filter_button.setPopupMode(QToolButton.InstantPopup)
        self.middle_filter_button.setArrowType(Qt.DownArrow)
        self.middle_filter_button.setFixedSize(26, 24)
        self.middle_filter_button.setToolTip("Filter: All")
        toolbar_layout.addWidget(self.middle_filter_button, 0, Qt.AlignRight)

        self.middle_filter_menu = QMenu(self.middle_filter_button)
        self.middle_filter_action_group = QActionGroup(self)
        self.middle_filter_action_group.setExclusive(True)
        self.middle_filter_all_action = self._create_middle_filter_action("All", "all")
        self.middle_filter_animation_action = self._create_middle_filter_action("Animation", "animation")
        self.middle_filter_pose_action = self._create_middle_filter_action("Pose", "pose")
        self.middle_filter_button.setMenu(self.middle_filter_menu)

        self.animation_grid = AnimationGridWidget()
        middle_layout.addWidget(middle_toolbar)
        middle_layout.addWidget(self.animation_grid, 1)
        splitter.addWidget(self.middle_panel)

        # Right column: operation panel
        self.operation_panel = OperationPanelWidget()
        splitter.addWidget(self.operation_panel)

        # Set initial widths
        sizes = self.settings.get_splitter_sizes()
        splitter.setSizes([
            sizes["left_width"],
            sizes["middle_width"],
            sizes["right_width"]
        ])

        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)

        main_layout.addWidget(splitter)
        self.splitter = splitter
        self.statusBar().setSizeGripEnabled(False)

    def _connect_signals(self):
        # Folder tree: folder clicked -> load grid
        self.folder_tree.folder_selected.connect(self._on_folder_selected)
        self.folder_tree.category_selected.connect(self._on_category_selected)
        self.folder_tree.selection_cleared.connect(self._on_tree_selection_cleared)
        self.folder_tree.status_message_requested.connect(self._show_status_message)
        self.folder_tree.new_asset_requested.connect(self._on_new_asset_requested)

        # Grid: selection changed -> update apply button
        self.animation_grid.animation_selected.connect(self._on_animation_selected)
        self.animation_grid.status_message_requested.connect(self._show_status_message)
        self.animation_grid.files_deleted.connect(self._on_grid_files_deleted)
        self.animation_grid.file_renamed.connect(self._on_grid_file_renamed)
        self.animation_grid.new_asset_requested.connect(self._on_new_asset_requested)

        # Operation panel: operation done -> handle result
        self.operation_panel.operation_triggered.connect(self._on_operation_triggered)

    # ------------------------------------------------------------------ #
    #  Signal handlers                                                    #
    # ------------------------------------------------------------------ #

    def _on_folder_selected(self, folder_path):
        """User clicked a folder in the tree."""
        self._pending_save_type = None
        self._save_folder = folder_path
        self.operation_panel.set_current_folder(folder_path)
        self.animation_grid.load_animations(folder_path)
        self.operation_panel.set_selected_animations([])
        self._refresh_operation_panel()

    def _on_root_path_changed(self, new_path):
        """User chose a new library root via 'Set Library Path'."""
        self.settings.set_library_path(new_path)
        self.settings.save_config()

        # Clear the grid and reset the operation panel
        self.animation_grid.clear_animations()
        self._pending_save_type = None
        self._save_folder = None
        self.operation_panel.set_current_folder(None)
        self.operation_panel.set_selected_animations([])
        self._refresh_operation_panel()

    def _on_category_selected(self, payload):
        """User selected a virtual category in Category View."""
        self._pending_save_type = None
        self._save_folder = None
        self.operation_panel.set_current_folder(None)
        self.animation_grid.load_animation_paths(
            payload.get("asset_paths", []),
            payload.get("category_name") or payload.get("library_name") or "Category"
        )
        self.operation_panel.set_selected_animations([])
        self._refresh_operation_panel()

    def _on_tree_selection_cleared(self):
        """Tree selection cleared by blank click, rubber-band miss, or Esc."""
        self.animation_grid.clear_animations()
        self._pending_save_type = None
        self._save_folder = None
        self.operation_panel.set_current_folder(None)
        self.operation_panel.set_selected_animations([])
        self._refresh_operation_panel()

    def _on_animation_selected(self, paths):
        """
        Grid selection changed.

        Args:
            paths: list of full file paths (empty when nothing is selected)
        """
        if paths:
            self._pending_save_type = None
        self.operation_panel.set_selected_animations(paths)
        self._refresh_operation_panel()

    def _on_grid_files_deleted(self, paths):
        if paths:
            self.folder_tree.remove_asset_references(paths)

    def _on_grid_file_renamed(self, old_path, new_path):
        if old_path and new_path:
            self.folder_tree.replace_asset_reference(old_path, new_path)

    def _on_operation_triggered(self, operation_type, params):
        """
        React to completed operations.

        After a successful save the grid is refreshed so the new .bip
        file appears immediately without requiring the user to re-click.
        """
        if operation_type == "save_animation":
            folder = params.get("folder")
            if folder:
                self._save_folder = folder
                self.animation_grid.load_animations(folder)
                self.animation_grid.clearSelection()
                self.operation_panel.set_selected_animations([])
        elif operation_type == "save_pose":
            folder = params.get("folder")
            if folder:
                self._save_folder = folder
                self.animation_grid.load_animations(folder)
                self.animation_grid.clearSelection()
                self.operation_panel.set_selected_animations([])
        self._refresh_operation_panel()

    def _on_new_asset_requested(self, asset_type, folder_path):
        if not folder_path:
            QMessageBox.warning(self, "No Folder Selected", "Please choose a physical folder first.")
            return
        if not self.operation_panel.has_scene_selection():
            QMessageBox.warning(self, "No Scene Selection", "Please select one or more scene objects first.")
            return

        self._pending_save_type = asset_type
        self._save_folder = folder_path
        self.operation_panel.set_current_folder(folder_path)
        self.animation_grid.load_animations(folder_path)
        self.animation_grid.clearSelection()
        self.operation_panel.set_selected_animations([])
        self.operation_panel.start_new_asset(asset_type, folder_path=folder_path)
        self._refresh_operation_panel()

    def _refresh_operation_panel(self):
        selected_paths = self.animation_grid.get_selected_paths()
        if len(selected_paths) == 1:
            self.operation_panel.show_apply_panel(selected_paths[0])
            return
        if self._pending_save_type and self._save_folder and self.operation_panel.has_scene_selection():
            self.operation_panel.show_save_panel(self._pending_save_type, folder_path=self._save_folder)
            return
        self.operation_panel.show_empty_panel()

    def _show_status_message(self, message, timeout_ms=3000):
        if not message:
            return

        try:
            self.statusBar().showMessage(message, int(timeout_ms))
        except Exception:
            try:
                self.statusBar().showMessage(str(message), int(timeout_ms))
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  Theme / geometry                                                   #
    # ------------------------------------------------------------------ #

    def _apply_dark_theme(self):
        self.setStyleSheet("""
        QMainWindow { background-color: #2b2b2b; color: #cccccc; }
        QWidget     { background-color: #2b2b2b; color: #cccccc; }

        QTreeView {
            background-color: #3c3c3c; color: #cccccc;
            border: 1px solid #555555;
            selection-background-color: #094771;
        }
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
        QListWidget {
            background-color: #3c3c3c; color: #cccccc;
            border: 1px solid #555555;
            selection-background-color: #094771;
        }
        QGroupBox {
            color: #cccccc; border: 1px solid #555555;
            border-radius: 4px; margin-top: 8px; padding-top: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px;
            font-size: 22px; font-weight: bold;
        }
        QPushButton {
            background-color: #3c3c3c; color: #cccccc;
            border: 1px solid #555555; border-radius: 4px;
            padding: 6px 12px; font-weight: bold;
        }
        QPushButton:hover   { background-color: #4c4c4c; border: 1px solid #666666; }
        QPushButton:pressed { background-color: #2c2c2c; }
        QPushButton:disabled {
            background-color: #2c2c2c; color: #666666; border: 1px solid #444444;
        }
        QSpinBox {
            background-color: #3c3c3c; color: #cccccc;
            border: 1px solid #555555; border-radius: 4px; padding: 4px;
        }
        QSpinBox::up-button, QSpinBox::down-button { background-color: #555555; border: none; }
        QLabel  { color: #cccccc; }
        QScrollArea { background-color: #2b2b2b; border: none; }
        QStatusBar {
            background-color: #2b2b2b;
            color: #b8c7d9;
            border-top: 1px solid #444444;
        }
        QScrollBar:vertical {
            background-color: #3c3c3c; width: 12px; border: none;
        }
        QScrollBar::handle:vertical {
            background-color: #555555; border-radius: 6px; min-height: 20px;
        }
        QScrollBar::handle:vertical:hover { background-color: #666666; }
        QSplitter::handle       { background-color: #555555; }
        QSplitter::handle:hover { background-color: #666666; }
        """)

    def _restore_geometry(self):
        geo = self.settings.get_window_geometry()
        self.resize(geo["width"], geo["height"])
        self.move(geo["x"], geo["y"])

    def _persist_window_state(self):
        """Best-effort config save for host environments with fragile shutdown events."""
        try:
            geo = self.geometry()
            self.settings.set_window_geometry(geo.width(), geo.height(), geo.x(), geo.y())
        except Exception:
            pass

        try:
            sizes = self.splitter.sizes()
            if len(sizes) >= 3:
                self.settings.set_splitter_sizes(sizes[0], sizes[1], sizes[2])
        except Exception:
            pass

        try:
            self.settings.save_config()
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            if hasattr(self.operation_panel, "cleanup"):
                self.operation_panel.cleanup()
        except Exception:
            pass
        self._persist_window_state()
        try:
            if event is not None and hasattr(event, "accept") and callable(event.accept):
                event.accept()
        except Exception:
            pass

    def cleanup(self):
        try:
            if hasattr(self.operation_panel, "cleanup"):
                self.operation_panel.cleanup()
        except Exception:
            pass

    def _create_middle_filter_action(self, label, filter_key):
        action = self.middle_filter_menu.addAction(label)
        action.setCheckable(True)
        action.setData(filter_key)
        self.middle_filter_action_group.addAction(action)
        action.triggered.connect(lambda _checked=False, key=filter_key: self._set_middle_type_filter(key))
        if filter_key == "all":
            action.setChecked(True)
        return action

    def _set_middle_type_filter(self, filter_key):
        self._current_type_filter = filter_key or "all"
        self.middle_filter_all_action.setChecked(self._current_type_filter == "all")
        self.middle_filter_animation_action.setChecked(self._current_type_filter == "animation")
        self.middle_filter_pose_action.setChecked(self._current_type_filter == "pose")
        self.middle_filter_button.setToolTip("Filter: {0}".format(self._current_type_filter.title()))
        self.animation_grid.set_type_filter(self._current_type_filter)

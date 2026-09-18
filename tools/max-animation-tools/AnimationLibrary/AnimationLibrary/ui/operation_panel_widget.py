# -*- coding: utf-8 -*-
"""
Context-aware right-side operation panel.

The panel now has 3 exclusive modes:
    - empty
    - save
    - apply
"""

import json
import os
import time
import zipfile

from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QPushButton, QLabel,
    QMessageBox, QStackedWidget, QLineEdit, QTextEdit, QSizePolicy, QDialog, QSpinBox,
    QCheckBox, QSplitter, QRadioButton
)
from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QPixmap, QPainter, QColor, QFont, QPen

from ..utils import max_utils
from ..utils import preview_utils
from ..utils.anim_manager import AnimManager


_MODE_EMPTY = "empty"
_MODE_SAVE = "save"
_MODE_APPLY = "apply"
_TYPE_ANIMATION = "animation"
_TYPE_ANIMATION_LOCAL = "animation_local"
_TYPE_ANIMATION_LIMB = "animation_limb"
_TYPE_ANIMATION_FULL_BIPED = "animation_full_biped"
_TYPE_POSE = "pose"
_PREVIEW_MIN_SIZE = 220
_PREVIEW_SPLITTER_TOP = 260
_PREVIEW_BG = QColor(45, 45, 45)
_TYPE_COLORS = {
    _TYPE_ANIMATION: QColor(135, 135, 135),
    _TYPE_POSE: QColor(135, 135, 135),
}
_PREVIEW_EXT_COLORS = {
    '.bip': QColor(58, 58, 58),
    '.xaf': QColor(58, 58, 58),
    '.json': QColor(58, 58, 58),
    '.animx': QColor(58, 58, 58),
}
_PREVIEW_EXT_LABELS = {
    '.bip': 'BIP',
    '.xaf': 'XAF',
    '.json': 'POSE',
    '.animx': 'ANIM',
}
_ANIMATION_MODE_LOCAL = "local"
_ANIMATION_MODE_LIMB = "limb"
_ANIMATION_MODE_FULL_BIPED = "full_biped"
_ANIMATION_MODE_LABELS = {
    _ANIMATION_MODE_LOCAL: "Animation",
    _ANIMATION_MODE_LIMB: "Animation",
    _ANIMATION_MODE_FULL_BIPED: "Template",
}
_ANIMATION_MODE_BADGES = {
    _ANIMATION_MODE_LOCAL: "AN",
    _ANIMATION_MODE_LIMB: "AN",
    _ANIMATION_MODE_FULL_BIPED: "TP",
}

try:
    text_type = unicode
except NameError:
    text_type = str


def _is_animation_asset_type(asset_type):
    return asset_type in (
        _TYPE_ANIMATION,
        _TYPE_ANIMATION_LOCAL,
        _TYPE_ANIMATION_LIMB,
        _TYPE_ANIMATION_FULL_BIPED,
    )


def _animation_mode_from_asset_type(asset_type):
    if asset_type == _TYPE_ANIMATION_LIMB:
        return _ANIMATION_MODE_LIMB
    if asset_type == _TYPE_ANIMATION_FULL_BIPED:
        return _ANIMATION_MODE_FULL_BIPED
    return _ANIMATION_MODE_LOCAL


def _animation_title_from_asset_type(asset_type):
    if asset_type == _TYPE_POSE:
        return "Pose"
    return _ANIMATION_MODE_LABELS.get(
        _animation_mode_from_asset_type(asset_type),
        "Animation"
    )


def _is_template_animation_mode(animation_mode):
    return text_type(animation_mode or "").strip().lower() == _ANIMATION_MODE_FULL_BIPED


class PreviewCaptureDialog(QDialog):
    """Stable manual preview capture dialog."""

    preview_confirmed = Signal(object)

    def __init__(self, parent=None, asset_type=_TYPE_ANIMATION, selected_objects=None):
        super(PreviewCaptureDialog, self).__init__(parent)
        self._asset_type = asset_type
        self._selected_objects = list(selected_objects or [])
        self._preview_path = None
        self._init_ui()
        self._refresh_preview()

    def _init_ui(self):
        self.setWindowTitle("Capture Preview")
        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        self.resize(560, 660)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        hint = QLabel(
            "Adjust the 3ds Max viewport, then click Refresh.\n"
            "When the preview looks right, click Confirm."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #bdbdbd; font-size: 16px;")
        layout.addWidget(hint)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(420, 420)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet(
            "background-color: #2d2d2d; border: 1px solid #555555; border-radius: 4px;"
        )
        layout.addWidget(self.preview_label, 1)

        button_row = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setMinimumHeight(40)
        self.refresh_button.clicked.connect(self._refresh_preview)
        button_row.addWidget(self.refresh_button)

        self.confirm_button = QPushButton("Confirm")
        self.confirm_button.setMinimumHeight(40)
        self.confirm_button.clicked.connect(self._confirm_preview)
        button_row.addWidget(self.confirm_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.clicked.connect(self.close)
        button_row.addWidget(self.cancel_button)

        layout.addLayout(button_row)

    def _refresh_preview(self):
        preview_path = preview_utils.capture_temp_preview(
            rt=max_utils.rt if getattr(max_utils, "PYMXS_AVAILABLE", False) else None,
            selected_objects=self._selected_objects,
            safe_print=None
        )
        if not preview_path or not os.path.isfile(preview_path):
            QMessageBox.warning(self, "Capture Failed", "Could not capture the current viewport preview.")
            return

        if self._preview_path and self._preview_path != preview_path:
            try:
                if os.path.exists(self._preview_path):
                    os.remove(self._preview_path)
            except Exception:
                pass

        self._preview_path = preview_path
        pixmap = QPixmap(preview_path)
        if pixmap.isNull():
            return

        canvas = QPixmap(max(self.preview_label.width(), 420), max(self.preview_label.height(), 420))
        canvas.fill(_PREVIEW_BG)
        painter = QPainter(canvas)
        scaled = pixmap.scaled(canvas.width(), canvas.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = int((canvas.width() - scaled.width()) / 2)
        y = int((canvas.height() - scaled.height()) / 2)
        painter.drawPixmap(x, y, scaled)
        painter.setPen(QPen(_TYPE_COLORS.get(self._asset_type, QColor(120, 120, 120)), 2))
        painter.drawRect(canvas.rect().adjusted(1, 1, -2, -2))
        painter.end()
        self.preview_label.setPixmap(canvas)

    def _confirm_preview(self):
        if not self._preview_path or not os.path.isfile(self._preview_path):
            QMessageBox.warning(self, "No Preview", "Please capture a preview first.")
            return
        confirmed_path = self._preview_path
        self._preview_path = None
        self.preview_confirmed.emit(confirmed_path)
        self.close()

    def closeEvent(self, event):
        try:
            if self._preview_path and os.path.exists(self._preview_path):
                os.remove(self._preview_path)
        except Exception:
            pass
        self._preview_path = None
        self._selected_objects = []
        super(PreviewCaptureDialog, self).closeEvent(event)


def _display_name_from_path(path):
    filename = os.path.basename(path or "")
    name = os.path.splitext(filename)[0]
    if name.lower().endswith("_pose"):
        name = name[:-5]
    return name


def _file_type_from_path(path):
    ext = os.path.splitext(path or "")[1].lower()
    if ext == '.json':
        return _TYPE_POSE
    return _TYPE_ANIMATION


class OperationPanelWidget(QWidget):
    """Operation panel widget on the right side."""

    operation_triggered = Signal(str, dict)

    def __init__(self):
        super(OperationPanelWidget, self).__init__()
        self._selected_paths = []
        self._current_folder = None
        self._mode = _MODE_EMPTY
        self._save_asset_type = None
        self._manual_preview_path = None
        self._capture_dialog = None
        self._apply_range_asset_path = None
        self._init_ui()
        self.show_empty_panel()

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def set_current_folder(self, folder_path):
        self._current_folder = folder_path

    def get_current_folder(self):
        return self._current_folder

    def set_selected_animations(self, paths):
        self._selected_paths = list(paths or [])
        if self._mode == _MODE_APPLY:
            self._refresh_apply_page()

    def update_frame_ranges(self):
        if self._mode == _MODE_SAVE:
            self._sync_save_range_to_scene()
        elif self._mode == _MODE_APPLY:
            self._sync_apply_range_to_scene()

    def get_scene_selection_count(self):
        try:
            if getattr(max_utils, "PYMXS_AVAILABLE", False):
                return len(list(max_utils.rt.selection))
        except Exception:
            pass

        try:
            return len(max_utils.get_selected_objects())
        except Exception:
            return 0

    def has_scene_selection(self):
        return self.get_scene_selection_count() > 0

    def show_empty_panel(self):
        self._mode = _MODE_EMPTY
        self.stack.setCurrentWidget(self.empty_page)

    def show_save_panel(self, asset_type, folder_path=None):
        self._mode = _MODE_SAVE
        self._save_asset_type = asset_type
        if folder_path:
            self._current_folder = folder_path
        self._refresh_save_page(reset_inputs=False)
        self.stack.setCurrentWidget(self.save_page)

    def show_apply_panel(self, file_path):
        self._mode = _MODE_APPLY
        if file_path:
            self._selected_paths = [file_path]
        self._refresh_apply_page()
        self.stack.setCurrentWidget(self.apply_page)

    def start_new_asset(self, asset_type, folder_path=None):
        self._save_asset_type = asset_type
        if folder_path:
            self._current_folder = folder_path
        self._clear_manual_preview()
        self._refresh_save_page(reset_inputs=True)
        self.show_save_panel(asset_type, folder_path=folder_path)

    # ------------------------------------------------------------------ #
    #  UI                                                                 #
    # ------------------------------------------------------------------ #

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.empty_page = self._create_empty_page()
        self.save_page = self._create_save_page()
        self.apply_page = self._create_apply_page()

        self.stack.addWidget(self.empty_page)
        self.stack.addWidget(self.save_page)
        self.stack.addWidget(self.apply_page)
        main_layout.addWidget(self.stack)

    def _create_empty_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        return page

    def _create_save_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.save_preview_group = QGroupBox("Preview")
        save_preview_layout = QVBoxLayout(self.save_preview_group)
        save_preview_layout.setContentsMargins(10, 10, 10, 10)
        save_preview_layout.setSpacing(8)
        self.save_preview_label = self._create_preview_label()
        save_preview_layout.addWidget(self.save_preview_label)

        capture_row = QHBoxLayout()
        capture_row.addStretch()
        self.capture_preview_button = QPushButton("Capture Preview")
        self.capture_preview_button.setMinimumHeight(32)
        self.capture_preview_button.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.capture_preview_button.clicked.connect(self._open_capture_preview_dialog)
        capture_row.addWidget(self.capture_preview_button)
        save_preview_layout.addLayout(capture_row)

        self.save_preview_hint_label = QLabel(
            "A preview will be captured automatically on save.\n"
            "Use Capture Preview when you want to override it."
        )
        self.save_preview_hint_label.setWordWrap(True)
        self.save_preview_hint_label.setStyleSheet("color: #9a9a9a; font-size: 13px;")
        save_preview_layout.addWidget(self.save_preview_hint_label)

        self.save_form_group = QGroupBox("Save")
        form_layout = QVBoxLayout(self.save_form_group)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(8)
        name_row.addWidget(self._create_field_title("Name"), 0)
        self.save_name_edit = QLineEdit()
        self.save_name_edit.setMinimumHeight(34)
        self.save_name_edit.setPlaceholderText("Enter animation name")
        self.save_name_edit.setStyleSheet(self._input_style(font_size=16))
        name_row.addWidget(self.save_name_edit, 1)
        form_layout.addLayout(name_row)

        self.save_frame_range_widget = QWidget()
        frame_range_layout = QVBoxLayout(self.save_frame_range_widget)
        frame_range_layout.setContentsMargins(0, 0, 0, 0)
        frame_range_layout.setSpacing(6)
        save_range_title_row = QHBoxLayout()
        save_range_title_row.setContentsMargins(0, 0, 0, 0)
        save_range_title_row.setSpacing(8)
        save_range_title_row.addWidget(self._create_field_title("Frame Range"), 0)

        self.save_start_frame_spin = self._create_frame_spinbox()
        self.save_end_frame_spin = self._create_frame_spinbox()
        self.save_start_frame_spin.setToolTip("Start frame")
        self.save_end_frame_spin.setToolTip("End frame")
        self.save_start_frame_spin.setFixedWidth(76)
        self.save_end_frame_spin.setFixedWidth(76)
        save_range_title_row.addWidget(self.save_start_frame_spin, 0)
        save_range_title_row.addWidget(self._create_range_separator_label(), 0)
        save_range_title_row.addWidget(self.save_end_frame_spin, 0)

        self.save_use_scene_range_button = QPushButton("...")
        self.save_use_scene_range_button.setToolTip("Use Scene Range")
        self.save_use_scene_range_button.setFixedSize(32, 30)
        self.save_use_scene_range_button.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.save_use_scene_range_button.clicked.connect(self._sync_save_range_to_scene)
        save_range_title_row.addWidget(self.save_use_scene_range_button)
        save_range_title_row.addStretch()
        frame_range_layout.addLayout(save_range_title_row)

        self.save_scene_range_info_label = QLabel("")
        self.save_scene_range_info_label.setWordWrap(True)
        self.save_scene_range_info_label.setStyleSheet("color: #9a9a9a; font-size: 14px;")
        frame_range_layout.addWidget(self.save_scene_range_info_label)
        form_layout.addWidget(self.save_frame_range_widget)

        form_layout.addWidget(self._create_field_title("Comment"))
        self.save_comment_edit = QTextEdit()
        self.save_comment_edit.setFixedHeight(120)
        self.save_comment_edit.setAcceptRichText(False)
        self.save_comment_edit.setPlaceholderText("Optional notes for this asset")
        self.save_comment_edit.setStyleSheet(self._input_style(font_size=15))
        form_layout.addWidget(self.save_comment_edit)

        self.save_selection_info_label = QLabel("")
        self.save_selection_info_label.setWordWrap(True)
        self.save_selection_info_label.setStyleSheet("color: #a9a9a9; font-size: 14px;")
        form_layout.addWidget(self.save_selection_info_label)

        self.save_submit_button = QPushButton("Save")
        self.save_submit_button.setMinimumHeight(42)
        self.save_submit_button.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
            "background-color: #1296f3; color: #ffffff; border: 1px solid #0d77c5;"
        )
        self.save_submit_button.clicked.connect(self._on_submit_save)
        form_layout.addWidget(self.save_submit_button)

        self.save_bottom_panel = QWidget()
        self.save_bottom_layout = QVBoxLayout(self.save_bottom_panel)
        self.save_bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.save_bottom_layout.setSpacing(0)
        self.save_bottom_layout.addWidget(self.save_form_group)
        self.save_bottom_layout.addStretch()

        self.save_splitter = self._create_panel_splitter(
            self.save_preview_group,
            self.save_bottom_panel
        )
        self.save_splitter.splitterMoved.connect(self._on_save_splitter_moved)
        layout.addWidget(self.save_splitter)
        return page

    def _create_apply_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.apply_preview_group = QGroupBox("Preview")
        apply_preview_layout = QVBoxLayout(self.apply_preview_group)
        apply_preview_layout.setContentsMargins(8, 8, 8, 8)
        self.apply_preview_label = self._create_preview_label()
        apply_preview_layout.addWidget(self.apply_preview_label)

        self.apply_info_group = QGroupBox("Info")
        info_layout = QGridLayout(self.apply_info_group)
        info_layout.setContentsMargins(12, 12, 12, 12)
        info_layout.setHorizontalSpacing(10)
        info_layout.setVerticalSpacing(12)
        info_layout.setColumnMinimumWidth(0, 96)
        info_layout.setColumnStretch(1, 1)

        self.apply_name_title_label = self._create_info_title_label("Name:")
        self.apply_name_value_label = self._create_info_value_label("No file selected", 18, True)
        info_layout.addWidget(self.apply_name_title_label, 0, 0, Qt.AlignLeft | Qt.AlignTop)
        info_layout.addWidget(self.apply_name_value_label, 0, 1)

        self.apply_type_title_label = self._create_info_title_label("Type:")
        self.apply_type_value_label = self._create_info_value_label("-")
        info_layout.addWidget(self.apply_type_title_label, 1, 0, Qt.AlignLeft | Qt.AlignTop)
        info_layout.addWidget(self.apply_type_value_label, 1, 1)

        self.apply_objects_title_label = self._create_info_title_label("Objects:")
        self.apply_objects_value_label = self._create_info_value_label("-")
        info_layout.addWidget(self.apply_objects_title_label, 2, 0, Qt.AlignLeft | Qt.AlignTop)
        info_layout.addWidget(self.apply_objects_value_label, 2, 1)

        self.apply_frames_title_label = self._create_info_title_label("Frames:")
        self.apply_frames_value_label = self._create_info_value_label("-")
        info_layout.addWidget(self.apply_frames_title_label, 3, 0, Qt.AlignLeft | Qt.AlignTop)
        info_layout.addWidget(self.apply_frames_value_label, 3, 1)

        self.apply_modified_title_label = self._create_info_title_label("Modified:")
        self.apply_modified_value_label = self._create_info_value_label("-")
        info_layout.addWidget(self.apply_modified_title_label, 4, 0, Qt.AlignLeft | Qt.AlignTop)
        info_layout.addWidget(self.apply_modified_value_label, 4, 1)

        self.apply_animation_options_group = QGroupBox("Apply")
        apply_options_layout = QVBoxLayout(self.apply_animation_options_group)
        apply_options_layout.setContentsMargins(10, 10, 10, 10)
        apply_options_layout.setSpacing(8)

        apply_range_title_row = QHBoxLayout()
        apply_range_title_row.setContentsMargins(0, 0, 0, 0)
        apply_range_title_row.setSpacing(8)
        apply_range_title_row.addWidget(self._create_field_title("Frame Range"), 0)

        self.apply_start_frame_spin = self._create_frame_spinbox()
        self.apply_end_frame_spin = self._create_frame_spinbox()
        self.apply_start_frame_spin.setToolTip("Start frame")
        self.apply_end_frame_spin.setToolTip("End frame")
        self.apply_start_frame_spin.setFixedWidth(76)
        self.apply_end_frame_spin.setFixedWidth(76)
        apply_range_title_row.addWidget(self.apply_start_frame_spin, 0)
        apply_range_title_row.addWidget(self._create_range_separator_label(), 0)
        apply_range_title_row.addWidget(self.apply_end_frame_spin, 0)

        self.apply_use_scene_range_button = QPushButton("...")
        self.apply_use_scene_range_button.setToolTip("Use Scene Range")
        self.apply_use_scene_range_button.setFixedSize(32, 30)
        self.apply_use_scene_range_button.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.apply_use_scene_range_button.clicked.connect(self._sync_apply_range_to_scene)
        apply_range_title_row.addWidget(self.apply_use_scene_range_button)
        apply_range_title_row.addStretch()
        self.apply_range_row_widget = QWidget()
        self.apply_range_row_widget.setLayout(apply_range_title_row)
        apply_options_layout.addWidget(self.apply_range_row_widget)

        apply_option_row = QHBoxLayout()
        apply_option_row.setContentsMargins(0, 0, 0, 0)
        apply_option_row.setSpacing(8)
        self.apply_bake_checkbox = self._create_option_checkbox("Bake")
        apply_option_row.addWidget(self.apply_bake_checkbox, 0, Qt.AlignLeft)
        apply_option_row.addStretch()
        self.apply_bake_row_widget = QWidget()
        self.apply_bake_row_widget.setLayout(apply_option_row)
        apply_options_layout.addWidget(self.apply_bake_row_widget)

        self.apply_pose_space_widget = QWidget()
        pose_space_layout = QHBoxLayout(self.apply_pose_space_widget)
        pose_space_layout.setContentsMargins(0, 0, 0, 0)
        pose_space_layout.setSpacing(8)
        pose_space_layout.addWidget(self._create_field_title("COM Mode"), 0)
        self.apply_pose_world_radio = QRadioButton("World")
        self.apply_pose_world_radio.setChecked(True)
        self.apply_pose_world_radio.setStyleSheet("color: #d8d8d8; font-size: 15px;")
        pose_space_layout.addWidget(self.apply_pose_world_radio, 0, Qt.AlignLeft)
        self.apply_pose_local_radio = QRadioButton("Local")
        self.apply_pose_local_radio.setStyleSheet("color: #d8d8d8; font-size: 15px;")
        pose_space_layout.addWidget(self.apply_pose_local_radio, 0, Qt.AlignLeft)
        pose_space_layout.addStretch()
        apply_options_layout.addWidget(self.apply_pose_space_widget)

        self.apply_scene_range_info_label = QLabel("")
        self.apply_scene_range_info_label.setWordWrap(True)
        self.apply_scene_range_info_label.setStyleSheet("color: #9a9a9a; font-size: 14px;")
        apply_options_layout.addWidget(self.apply_scene_range_info_label)
        self.apply_bottom_panel = QWidget()
        self.apply_bottom_layout = QVBoxLayout(self.apply_bottom_panel)
        self.apply_bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.apply_bottom_layout.setSpacing(10)
        self.apply_bottom_layout.addWidget(self.apply_info_group)
        self.apply_bottom_layout.addWidget(self.apply_animation_options_group)

        self.apply_comment_group = QGroupBox("Comment")
        comment_layout = QVBoxLayout(self.apply_comment_group)
        comment_layout.setContentsMargins(10, 10, 10, 10)
        self.apply_comment_edit = QTextEdit()
        self.apply_comment_edit.setReadOnly(True)
        self.apply_comment_edit.setMinimumHeight(120)
        self.apply_comment_edit.setStyleSheet(self._input_style(font_size=15))
        comment_layout.addWidget(self.apply_comment_edit)
        self.apply_bottom_layout.addWidget(self.apply_comment_group)

        self.apply_submit_button = QPushButton("Apply")
        self.apply_submit_button.setMinimumHeight(42)
        self.apply_submit_button.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
            "background-color: #1296f3; color: #ffffff; border: 1px solid #0d77c5;"
        )
        self.apply_submit_button.clicked.connect(self._on_submit_apply)
        self.apply_bottom_layout.addWidget(self.apply_submit_button)
        self.apply_bottom_layout.addStretch()

        self.apply_splitter = self._create_panel_splitter(
            self.apply_preview_group,
            self.apply_bottom_panel
        )
        self.apply_splitter.splitterMoved.connect(self._on_apply_splitter_moved)
        layout.addWidget(self.apply_splitter)
        return page

    def _create_preview_label(self):
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumSize(_PREVIEW_MIN_SIZE, _PREVIEW_MIN_SIZE)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        label.setStyleSheet("background-color: #2d2d2d; border: 1px solid #555555; border-radius: 4px;")
        return label

    def _create_field_title(self, text):
        label = QLabel(text)
        label.setStyleSheet("color: #b0b0b0; font-size: 16px; font-weight: bold;")
        return label

    def _create_frame_spinbox(self):
        spin_box = QSpinBox()
        spin_box.setRange(-1000000, 1000000)
        spin_box.setMinimumHeight(30)
        spin_box.setAlignment(Qt.AlignCenter)
        spin_box.setButtonSymbols(QSpinBox.NoButtons)
        spin_box.setStyleSheet(self._input_style(font_size=15, padding="5px 8px"))
        return spin_box

    def _create_range_separator_label(self):
        label = QLabel("-")
        label.setAlignment(Qt.AlignCenter)
        label.setFixedWidth(14)
        label.setStyleSheet("color: #a0a0a0; font-size: 16px; font-weight: bold;")
        return label

    def _create_option_checkbox(self, text):
        checkbox = QCheckBox(text)
        checkbox.setStyleSheet(
            "QCheckBox { color: #d8d8d8; font-size: 15px; spacing: 8px; }"
            "QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #8a8a8a; "
            "background-color: #2f2f2f; border-radius: 3px; }"
            "QCheckBox::indicator:checked { background-color: #1296f3; border: 1px solid #0d77c5; }"
        )
        return checkbox

    def _create_panel_splitter(self, top_widget, bottom_widget):
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([_PREVIEW_SPLITTER_TOP, 480])
        return splitter

    def _input_style(self, font_size=15, padding="6px 8px"):
        return (
            "background-color: #3a3a3a;"
            "color: #e0e0e0;"
            "border: 1px solid #5a5a5a;"
            "border-radius: 4px;"
            "padding: {1};"
            "font-size: {0}px;"
        ).format(int(font_size), padding)

    def _create_info_title_label(self, text):
        label = QLabel(text)
        label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        label.setStyleSheet("color: #9a9a9a; font-size: 16px; font-weight: bold;")
        return label

    def _create_info_value_label(self, text, font_size=16, bold=False):
        label = QLabel(text)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setWordWrap(True)
        label.setStyleSheet(
            "color: #dddddd; font-size: {0}px; font-weight: {1};".format(
                font_size, "bold" if bold else "normal"
            )
        )
        return label

    # ------------------------------------------------------------------ #
    #  Mode refresh                                                       #
    # ------------------------------------------------------------------ #

    def _refresh_save_page(self, reset_inputs):
        asset_type = self._save_asset_type or _TYPE_ANIMATION
        title = "Save {0}".format(_animation_title_from_asset_type(asset_type))
        self.save_form_group.setTitle(title)
        self.save_submit_button.setText("Save")
        self.save_name_edit.setPlaceholderText(
            "Enter pose name" if asset_type == _TYPE_POSE else "Enter animation name"
        )
        self.save_frame_range_widget.setVisible(_is_animation_asset_type(asset_type))
        self._refresh_save_preview()
        self._update_scene_range_label()
        self.save_selection_info_label.setText(self._build_save_selection_text(asset_type))

        if reset_inputs:
            self.save_name_edit.setText(self._default_save_name())
            self.save_comment_edit.clear()
            self._clear_manual_preview()
            self._sync_save_range_to_scene()
            self._refresh_save_preview()

    def _refresh_apply_page(self):
        path = self._selected_single_path()
        if not path:
            self._apply_range_asset_path = None
            self.apply_bake_checkbox.setChecked(False)
            self.apply_pose_world_radio.setChecked(True)
            self.apply_preview_label.setPixmap(self._make_placeholder_preview("PREVIEW"))
            self._set_apply_info({
                "name": "No file selected",
                "type": "-",
                "objects": "-",
                "frames": "-",
                "modified": "-",
                "comment": "",
                "show_frames": False,
            })
            self.apply_animation_options_group.setVisible(False)
            self.apply_comment_group.setVisible(False)
            return

        self.apply_preview_label.setPixmap(self._make_asset_preview(path))
        info = self._build_apply_metadata(path)
        self._set_apply_info(info)
        asset_type = _file_type_from_path(path)
        is_animation = (asset_type == _TYPE_ANIMATION)
        is_pose = (asset_type == _TYPE_POSE)
        animation_mode = text_type(info.get("animation_mode") or "").strip().lower()
        is_template_animation = bool(is_animation and _is_template_animation_mode(animation_mode))
        self.apply_animation_options_group.setVisible(is_animation or is_pose)
        self.apply_range_row_widget.setVisible(bool(is_animation and not is_template_animation))
        self.apply_bake_row_widget.setVisible(bool(is_animation and not is_template_animation))
        self.apply_scene_range_info_label.setVisible(is_animation)
        self.apply_pose_space_widget.setVisible(is_pose)
        if is_animation:
            self._sync_apply_range_to_asset(path, info=info)
        else:
            self._apply_range_asset_path = None

    def _set_apply_info(self, info):
        self._set_elided_label_text(self.apply_name_value_label, text_type(info.get("name", "")))
        self.apply_type_value_label.setText(text_type(info.get("type", "-")))
        self.apply_objects_value_label.setText(text_type(info.get("objects", "-")))
        self.apply_modified_value_label.setText(text_type(info.get("modified", "-")))

        show_frames = bool(info.get("show_frames"))
        self.apply_frames_title_label.setVisible(show_frames)
        self.apply_frames_value_label.setVisible(show_frames)
        if show_frames:
            self.apply_frames_value_label.setText(text_type(info.get("frames", "-")))

        comment_text = text_type(info.get("comment", "") or "").strip()
        self.apply_comment_group.setVisible(bool(comment_text))
        self.apply_comment_edit.setPlainText(comment_text)

    def _set_elided_label_text(self, label, text_value):
        text_value = text_type(text_value or "")
        label.setToolTip(text_value)
        width = max(label.width() - 4, 20)
        try:
            metrics = label.fontMetrics()
            elided = metrics.elidedText(text_value, Qt.ElideRight, width)
        except Exception:
            elided = text_value
        label.setText(elided)

    # ------------------------------------------------------------------ #
    #  Actions                                                            #
    # ------------------------------------------------------------------ #

    def _on_submit_save(self):
        if not self._current_folder:
            QMessageBox.warning(self, "No Folder Selected", "Please select a physical folder first.")
            return
        if not self.has_scene_selection():
            QMessageBox.warning(self, "No Scene Selection", "Please select one or more scene objects first.")
            return

        name_text = text_type(self.save_name_edit.text()).strip()
        if not name_text:
            QMessageBox.warning(self, "Invalid Name", "Please enter a file name.")
            return

        comment_text = text_type(self.save_comment_edit.toPlainText()).strip()
        save_path = None
        operation_type = None

        if self._save_asset_type == _TYPE_POSE:
            save_path = AnimManager.save_pose(
                target_folder=self._current_folder,
                parent_widget=self,
                pose_name=name_text,
                comment=comment_text
            )
            operation_type = "save_pose"
        else:
            start_frame = int(self.save_start_frame_spin.value())
            end_frame = int(self.save_end_frame_spin.value())
            if start_frame > end_frame:
                QMessageBox.warning(self, "Invalid Frame Range", "Start frame cannot be greater than end frame.")
                return
            save_path = AnimManager.save_animation(
                target_folder=self._current_folder,
                parent_widget=self,
                start_frame=start_frame,
                end_frame=end_frame,
                clip_name=name_text,
                comment=comment_text,
                animation_mode=_animation_mode_from_asset_type(self._save_asset_type)
            )
            operation_type = "save_animation"

        if save_path:
            if self._manual_preview_path:
                preview_utils.save_preview_from_image(self._manual_preview_path, save_path)
            self.save_name_edit.setText(self._default_save_name())
            self.save_comment_edit.clear()
            self._clear_manual_preview()
            self._sync_save_range_to_scene()
            self._refresh_save_preview()
            self.operation_triggered.emit(operation_type, {
                "save_path": save_path,
                "folder": self._current_folder,
            })

    def _on_submit_apply(self):
        path = self._selected_single_path()
        if not path:
            QMessageBox.warning(self, "Selection Required", "Please select one file in the grid first.")
            return
        if not self.has_scene_selection():
            QMessageBox.warning(self, "No Scene Selection", "Please select one or more scene objects first.")
            return

        asset_type = _file_type_from_path(path)
        if asset_type == _TYPE_POSE:
            pose_space_mode = "local" if self.apply_pose_local_radio.isChecked() else "world"
            success = AnimManager.apply_pose(
                pose_file_path=path,
                parent_widget=self,
                biped_root_space_mode=pose_space_mode
            )
            self.operation_triggered.emit("apply_pose", {"pose_path": path, "success": success})
        else:
            metadata = self._build_apply_metadata(path)
            if _is_template_animation_mode(metadata.get("animation_mode")):
                start_frame = None
                end_frame = None
            else:
                start_frame = int(self.apply_start_frame_spin.value())
                end_frame = int(self.apply_end_frame_spin.value())
                if start_frame > end_frame:
                    QMessageBox.warning(self, "Invalid Frame Range", "Start frame cannot be greater than end frame.")
                    return
            success = AnimManager.apply_animation(
                bip_file_path=path,
                parent_widget=self,
                start_frame=start_frame,
                end_frame=end_frame,
                bake_keys=(
                    False if _is_template_animation_mode(metadata.get("animation_mode"))
                    else self.apply_bake_checkbox.isChecked()
                )
            )
            self.operation_triggered.emit("apply_animation", {"anim_path": path, "success": success})

    # ------------------------------------------------------------------ #
    #  Metadata helpers                                                   #
    # ------------------------------------------------------------------ #

    def _selected_single_path(self):
        if len(self._selected_paths) != 1:
            return None
        return self._selected_paths[0]

    def _default_save_name(self):
        try:
            if getattr(max_utils, "PYMXS_AVAILABLE", False):
                file_name = text_type(max_utils.rt.maxFileName or u"")
                base_name = os.path.splitext(file_name)[0]
                if base_name:
                    return base_name
        except Exception:
            pass
        return u"NewAsset"

    def _scene_anim_range(self):
        try:
            start_frame, end_frame = max_utils.get_timeline_range()
            return int(start_frame), int(end_frame)
        except Exception:
            return 0, 100

    def _build_save_selection_text(self, asset_type):
        count = self.get_scene_selection_count()
        if asset_type == _TYPE_POSE:
            return "{0} object(s) selected for saving".format(count)
        if asset_type == _TYPE_ANIMATION_LIMB:
            return (
                "{0} object(s) selected for saving\n"
                "Legacy limb-chain mode.\n"
                "Existing limb assets remain supported, but new saving is hidden from the main UI."
            ).format(count)
        if asset_type == _TYPE_ANIMATION_FULL_BIPED:
            return (
                "{0} object(s) selected for saving\n"
                "Saves the whole character as a fixed-range template.\n"
                "Template always reapplies at the saved frames and cannot be retimed or stitched."
            ).format(count)
        return (
            "{0} object(s) selected for saving\n"
            "Recommended default mode for reusable clips.\n"
            "Use this when you want to apply the animation to a different frame range."
        ).format(count)

    def _update_scene_range_label(self):
        start_frame, end_frame = self._scene_anim_range()
        self.save_scene_range_info_label.setText(
            "Scene range: {0} - {1}".format(start_frame, end_frame)
        )
        self.apply_scene_range_info_label.setText(
            "Scene range: {0} - {1}".format(start_frame, end_frame)
        )

    def _sync_save_range_to_scene(self):
        start_frame, end_frame = self._scene_anim_range()
        self.save_start_frame_spin.setValue(start_frame)
        self.save_end_frame_spin.setValue(end_frame)
        self._update_scene_range_label()
        print("[OperationPanel] Save range synced to scene: {0}-{1}".format(start_frame, end_frame))

    def _sync_apply_range_to_scene(self):
        start_frame, end_frame = self._scene_anim_range()
        self.apply_start_frame_spin.setValue(start_frame)
        self.apply_end_frame_spin.setValue(end_frame)
        self._update_scene_range_label()
        print("[OperationPanel] Apply range synced to scene: {0}-{1}".format(start_frame, end_frame))

    def _sync_apply_range_to_asset(self, path, info=None):
        if not path:
            return
        if self._apply_range_asset_path == path:
            self._update_scene_range_label()
            return
        self._apply_range_asset_path = path
        self.apply_bake_checkbox.setChecked(False)
        metadata = info or self._build_apply_metadata(path)
        start_frame = metadata.get("start_frame")
        end_frame = metadata.get("end_frame")
        if start_frame is None or end_frame is None:
            start_frame, end_frame = self._scene_anim_range()
        self.apply_start_frame_spin.setValue(int(start_frame))
        self.apply_end_frame_spin.setValue(int(end_frame))
        is_template_animation = _is_template_animation_mode(
            metadata.get("animation_mode")
        )
        if is_template_animation:
            self.apply_bake_checkbox.setChecked(False)
        self.apply_start_frame_spin.setEnabled(not is_template_animation)
        self.apply_end_frame_spin.setEnabled(not is_template_animation)
        self.apply_use_scene_range_button.setEnabled(not is_template_animation)
        self.apply_bake_checkbox.setEnabled(not is_template_animation)
        scene_start, scene_end = self._scene_anim_range()
        if is_template_animation:
            self.apply_scene_range_info_label.setText(
                "Template range: {0} - {1}\nAlways applies at the saved frames.\nScene range: {2} - {3}".format(
                    int(start_frame), int(end_frame), scene_start, scene_end
                )
            )
        else:
            self.apply_scene_range_info_label.setText(
                "Clip range: {0} - {1}\nScene range: {2} - {3}".format(
                    int(start_frame), int(end_frame), scene_start, scene_end
                )
            )

    def _build_apply_metadata(self, path):
        info = {
            "name": _display_name_from_path(path),
            "type": "Pose" if _file_type_from_path(path) == _TYPE_POSE else "Animation",
            "objects": "Unknown",
            "frames": "-",
            "start_frame": None,
            "end_frame": None,
            "modified": "Unknown",
            "comment": "",
            "show_frames": (_file_type_from_path(path) == _TYPE_ANIMATION),
        }
        if not path or not os.path.isfile(path):
            info["modified"] = "File not found"
            return info

        asset_meta = self._read_asset_metadata(path)
        if _file_type_from_path(path) == _TYPE_ANIMATION:
            info["type"] = asset_meta.get("type_label", "Animation")
        info["objects"] = asset_meta.get("object_count", "Unknown")
        info["frames"] = asset_meta.get("frame_length", "Unknown")
        info["start_frame"] = asset_meta.get("start_frame")
        info["end_frame"] = asset_meta.get("end_frame")
        info["comment"] = asset_meta.get("comment", "")
        try:
            info["modified"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
        except Exception:
            pass
        return info

    def _read_asset_metadata(self, path):
        if _file_type_from_path(path) == _TYPE_POSE:
            return self._read_pose_metadata(path)
        return self._read_animation_metadata(path)

    def _read_pose_metadata(self, path):
        result = {"object_count": "Unknown", "comment": ""}
        data = self._load_json_from_file(path)
        if not isinstance(data, dict):
            return result

        nodes = data.get("nodes")
        if isinstance(nodes, dict):
            result["object_count"] = len(nodes)
        result["comment"] = data.get("comment", "") or ""
        return result

    def _read_animation_metadata(self, path):
        result = {
            "object_count": "Unknown",
            "frame_length": "Unknown",
            "start_frame": None,
            "end_frame": None,
            "comment": "",
            "animation_mode": _ANIMATION_MODE_LOCAL,
            "type_label": _ANIMATION_MODE_LABELS[_ANIMATION_MODE_LOCAL],
        }

        ext = os.path.splitext(path)[1].lower()
        if ext == '.bip':
            result["animation_mode"] = _ANIMATION_MODE_FULL_BIPED
            result["type_label"] = _ANIMATION_MODE_LABELS[_ANIMATION_MODE_FULL_BIPED]
            return result
        if ext != '.animx':
            return result

        try:
            archive = zipfile.ZipFile(path, 'r')
        except Exception:
            return result

        try:
            manifest_bytes = archive.read("manifest.json")
        except Exception:
            archive.close()
            return result

        archive.close()
        manifest = self._load_json_bytes(manifest_bytes)
        if not isinstance(manifest, dict):
            return result

        animation_mode = text_type(
            manifest.get("animation_mode") or _ANIMATION_MODE_LOCAL
        ).strip().lower()
        if animation_mode not in _ANIMATION_MODE_LABELS:
            if manifest.get("bipeds") and not manifest.get("biped_partial"):
                animation_mode = _ANIMATION_MODE_FULL_BIPED
            else:
                animation_mode = _ANIMATION_MODE_LOCAL
        result["animation_mode"] = animation_mode
        result["type_label"] = _ANIMATION_MODE_LABELS.get(animation_mode, "Animation")

        object_names = list(manifest.get("generic_objects", []) or [])
        for entry in manifest.get("bipeds", []) or []:
            if isinstance(entry, dict) and entry.get("root_name"):
                object_names.append(entry.get("root_name"))

        unique_names = set([text_type(name) for name in object_names if name])
        partial_node_count = 0
        for entry in manifest.get("biped_partial", []) or []:
            try:
                partial_node_count += int(entry.get("node_count", 0))
            except Exception:
                pass
        total_count = len(unique_names) + partial_node_count
        if total_count:
            result["object_count"] = total_count

        start_frame = manifest.get("start_frame")
        end_frame = manifest.get("end_frame")
        result["start_frame"] = start_frame
        result["end_frame"] = end_frame
        try:
            result["frame_length"] = max(0, int(end_frame) - int(start_frame) + 1)
        except Exception:
            pass

        result["comment"] = manifest.get("comment", "") or ""
        return result

    def _load_json_from_file(self, path):
        try:
            handle = open(path, 'rb')
        except Exception:
            return None

        try:
            payload = handle.read()
        except Exception:
            handle.close()
            return None

        handle.close()
        return self._load_json_bytes(payload)

    def _load_json_bytes(self, payload):
        if payload is None:
            return None

        try:
            if not isinstance(payload, text_type):
                payload = payload.decode("utf-8")
        except Exception:
            try:
                payload = payload.decode("mbcs")
            except Exception:
                pass

        try:
            return json.loads(payload)
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Preview helpers                                                    #
    # ------------------------------------------------------------------ #

    def _preview_canvas_size(self, target_label):
        width = max(target_label.width(), _PREVIEW_MIN_SIZE)
        height = max(target_label.height(), _PREVIEW_MIN_SIZE)
        return width, height

    def _asset_badge_text(self, asset_type=None, file_path=None, metadata=None):
        if asset_type == _TYPE_POSE:
            return "PS"

        if metadata is None and file_path:
            metadata = self._read_asset_metadata(file_path)
        animation_mode = None
        if metadata:
            animation_mode = metadata.get("animation_mode")

        if animation_mode in _ANIMATION_MODE_BADGES:
            return _ANIMATION_MODE_BADGES[animation_mode]

        if asset_type and _is_animation_asset_type(asset_type):
            return _ANIMATION_MODE_BADGES.get(
                _animation_mode_from_asset_type(asset_type),
                "ANIM"
            )
        return "ANIM"

    def _draw_preview_badge(self, painter, canvas_rect, badge_text):
        if not badge_text:
            return
        font_size = max(11, int(min(canvas_rect.width(), canvas_rect.height()) / 16))
        badge_font = QFont("Arial", font_size, QFont.Bold)
        painter.setFont(badge_font)
        metrics = painter.fontMetrics()
        try:
            badge_text_width = metrics.horizontalAdvance(badge_text)
        except Exception:
            badge_text_width = metrics.width(badge_text)
        badge_width = badge_text_width + 16
        badge_height = metrics.height() + 8
        badge_rect = canvas_rect.adjusted(10, 10, -(canvas_rect.width() - badge_width - 10),
                                          -(canvas_rect.height() - badge_height - 10))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(18, 18, 18, 220))
        painter.drawRoundedRect(badge_rect, 5, 5)
        painter.setPen(QPen(QColor(210, 210, 210), 1))
        painter.drawRoundedRect(badge_rect, 5, 5)
        painter.setPen(QColor(235, 235, 235))
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

    def _make_placeholder_preview(self, text_value, asset_type=None, target_label=None):
        target = target_label or self.save_preview_label
        width, height = self._preview_canvas_size(target)
        frame_color = _TYPE_COLORS.get(asset_type or _TYPE_ANIMATION, QColor(120, 120, 120))
        pixmap = QPixmap(width, height)
        pixmap.fill(_PREVIEW_BG)
        painter = QPainter(pixmap)
        painter.setPen(QColor(160, 160, 160))
        painter.setFont(QFont("Arial", 20, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text_value)
        painter.setPen(QPen(frame_color, max(2, int(min(width, height) / 60))))
        painter.drawRect(pixmap.rect().adjusted(1, 1, -2, -2))
        self._draw_preview_badge(painter, pixmap.rect(), self._asset_badge_text(asset_type=asset_type))
        painter.end()
        return pixmap

    def _refresh_save_preview(self):
        if self._manual_preview_path and os.path.isfile(self._manual_preview_path):
            source = QPixmap(self._manual_preview_path)
            if not source.isNull():
                canvas = self._scale_preview_pixmap(source, self.save_preview_label)
                painter = QPainter(canvas)
                self._draw_preview_badge(
                    painter, canvas.rect(),
                    self._asset_badge_text(asset_type=self._save_asset_type or _TYPE_ANIMATION)
                )
                painter.end()
                self.save_preview_label.setPixmap(canvas)
                return
        self.save_preview_label.setPixmap(
            self._make_placeholder_preview("SAVE", self._save_asset_type or _TYPE_ANIMATION, self.save_preview_label)
        )

    def _scale_preview_pixmap(self, source, target_label):
        width, height = self._preview_canvas_size(target_label)
        canvas = QPixmap(width, height)
        canvas.fill(_PREVIEW_BG)
        painter = QPainter(canvas)
        scaled = source.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = int((width - scaled.width()) / 2)
        y = int((height - scaled.height()) / 2)
        painter.drawPixmap(x, y, scaled)
        painter.end()
        return canvas

    def _open_capture_preview_dialog(self):
        if not self.has_scene_selection():
            QMessageBox.warning(self, "No Scene Selection", "Please select one or more scene objects first.")
            return

        dialog = PreviewCaptureDialog(
            parent=self,
            asset_type=self._save_asset_type or _TYPE_ANIMATION,
            selected_objects=max_utils.get_selected_objects()
        )
        dialog.preview_confirmed.connect(self._on_manual_preview_confirmed)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._capture_dialog = dialog

    def _on_manual_preview_confirmed(self, preview_path):
        self._clear_manual_preview()
        self._manual_preview_path = preview_path
        self._refresh_save_preview()

    def _clear_manual_preview(self):
        try:
            if self._manual_preview_path and os.path.exists(self._manual_preview_path):
                os.remove(self._manual_preview_path)
        except Exception:
            pass
        self._manual_preview_path = None

    def cleanup(self):
        try:
            if self._capture_dialog is not None:
                try:
                    self._capture_dialog.preview_confirmed.disconnect(self._on_manual_preview_confirmed)
                except Exception:
                    pass
                try:
                    self._capture_dialog.close()
                except Exception:
                    pass
        except Exception:
            pass
        self._capture_dialog = None
        self._clear_manual_preview()

    def _make_asset_preview(self, file_path):
        target = self.apply_preview_label
        width, height = self._preview_canvas_size(target)
        metadata = self._read_asset_metadata(file_path)
        frame_color = _TYPE_COLORS.get(_file_type_from_path(file_path), QColor(120, 120, 120))
        preview_path = preview_utils.get_preview_path(file_path)
        if os.path.isfile(preview_path):
            source = QPixmap(preview_path)
            if not source.isNull():
                canvas = QPixmap(width, height)
                canvas.fill(_PREVIEW_BG)
                painter = QPainter(canvas)
                scaled = source.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = int((width - scaled.width()) / 2)
                y = int((height - scaled.height()) / 2)
                painter.drawPixmap(x, y, scaled)
                painter.setPen(QPen(frame_color, max(2, int(min(width, height) / 60))))
                painter.drawRect(canvas.rect().adjusted(1, 1, -2, -2))
                self._draw_preview_badge(
                    painter, canvas.rect(),
                    self._asset_badge_text(file_path=file_path, metadata=metadata)
                )
                painter.end()
                return canvas

        ext = os.path.splitext(file_path)[1].lower()
        label = _PREVIEW_EXT_LABELS.get(ext, ext.upper().lstrip('.') or 'FILE')
        bg = _PREVIEW_EXT_COLORS.get(ext, QColor(70, 70, 70))
        pixmap = QPixmap(width, height)
        pixmap.fill(bg)
        painter = QPainter(pixmap)
        painter.setPen(QColor(220, 220, 220))
        painter.setFont(QFont("Arial", 28, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, label)
        painter.setPen(QPen(frame_color, max(2, int(min(width, height) / 60))))
        painter.drawRect(pixmap.rect().adjusted(1, 1, -2, -2))
        self._draw_preview_badge(
            painter, pixmap.rect(),
            self._asset_badge_text(file_path=file_path, metadata=metadata)
        )
        painter.end()
        return pixmap

    def _on_save_splitter_moved(self, _pos, _index):
        self._refresh_save_preview()

    def _on_apply_splitter_moved(self, _pos, _index):
        if self._mode == _MODE_APPLY:
            self._refresh_apply_page()

    def resizeEvent(self, event):
        if self._mode == _MODE_SAVE:
            self._refresh_save_page(reset_inputs=False)
        elif self._mode == _MODE_APPLY:
            self._refresh_apply_page()
        super(OperationPanelWidget, self).resizeEvent(event)

    def closeEvent(self, event):
        self.cleanup()
        super(OperationPanelWidget, self).closeEvent(event)

    # ------------------------------------------------------------------ #
    #  Backward-compat shim                                               #
    # ------------------------------------------------------------------ #

    def set_enabled(self, enabled):
        pass

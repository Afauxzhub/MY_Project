# -*- coding: utf-8 -*-
"""动画工具：从角色 LOD 绑定创建新的局内动画文件。"""
from __future__ import print_function

import os
import shutil
import tempfile

from PySide2 import QtCore, QtWidgets

from pipeline.new_file_service import (
    build_camera_options,
    build_chapter_options,
    build_indoor_destination,
    build_outdoor_destination,
    build_scene_options,
    binding_category_from_path,
    compose_indoor_filename,
    compose_outdoor_dialogue_filename,
    compose_outdoor_role_filename,
    copy_binding_to_destination,
    find_indoor_binding_files,
    find_outdoor_binding_files,
    load_anim_file_manager_config,
    normalize_name_part,
    validate_name_part,
)
from pipeline.publish_public_lookup import build_review_version_options
from pipeline.rm_naming import (
    MODULE_TAG_ROLE_SUPPORT,
    MODULE_TAG_STORY_DIALOGUE,
    indoor_categories_from_map,
    merge_module_folder_map,
    merge_module_tag_map,
    merge_type_folder_map,
    module_codes_for_tag,
    validate_indoor_name,
    validate_outdoor_name,
)
from ui.rm_config_io import load_config as load_publish_config
from ui.rm_theme import apply_dark_theme
from pipeline.personal_naming import (
    PURPOSES, compose_name, parse_name, source_characters_root, source_destination,
)

try:
    _text_type = unicode
except NameError:
    _text_type = str


_WINDOW = None

_ROLE_MODULE_LABELS = {
    u"UL": u"Ultimate",
    u"GA": u"Gacha",
    u"DE": u"Development",
    u"ER": u"Enrage",
}


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


class NewFileDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(NewFileDialog, self).__init__(parent)
        self.setWindowTitle(u"新建文件")
        self.setMinimumSize(900, 520)
        self.resize(1080, 600)
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self._install_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self._publish_config = {}
        self._local_root = u""
        self._rig_items = []
        self._last_auto_filename = u""
        self._last_auto_path = u""
        self._out_rig_items = []
        self._last_out_auto_filename = u""
        self._last_out_auto_path = u""
        self._dialogue_rig_items = []
        self._last_dialogue_auto_filename = u""
        self._last_dialogue_auto_path = u""
        self._rig_timer = QtCore.QTimer(self)
        self._rig_timer.setSingleShot(True)
        self._rig_timer.setInterval(450)
        self._rig_timer.timeout.connect(self._refresh_rigs)
        self._out_rig_timer = QtCore.QTimer(self)
        self._out_rig_timer.setSingleShot(True)
        self._out_rig_timer.setInterval(450)
        self._out_rig_timer.timeout.connect(self._refresh_outdoor_rigs)
        self._dialogue_rig_timer = QtCore.QTimer(self)
        self._dialogue_rig_timer.setSingleShot(True)
        self._dialogue_rig_timer.setInterval(450)
        self._dialogue_rig_timer.timeout.connect(self._refresh_dialogue_rigs)
        self._build_ui()
        apply_dark_theme(self)
        self._reload_shared_settings(force_path=True)

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self._tabs = QtWidgets.QTabWidget()
        self._tabs.addTab(self._build_indoor_page(), u"局内")
        self._tabs.addTab(self._build_outdoor_page(), u"局外")
        root.addWidget(self._tabs, 1)

    def _build_indoor_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(16)

        choice_group = QtWidgets.QGroupBox(u"文件名与绑定文件")
        choice_layout = QtWidgets.QFormLayout(choice_group)
        choice_layout.setContentsMargins(16, 18, 16, 16)
        choice_layout.setHorizontalSpacing(12)
        choice_layout.setVerticalSpacing(14)
        choice_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self._naming_mode = QtWidgets.QComboBox()
        self._naming_mode.addItems([u"个人短命名", u"旧分类格式（兼容）"])
        self._naming_mode.currentIndexChanged.connect(self._on_naming_mode_changed)
        choice_layout.addRow(u"命名规则：", self._naming_mode)

        self._category_combo = QtWidgets.QComboBox()
        self._category_combo.currentIndexChanged.connect(self._on_fields_changed)
        choice_layout.addRow(u"角色分类：", self._category_combo)

        self._character_edit = QtWidgets.QLineEdit()
        self._character_edit.setPlaceholderText(u"例如 Player、Wolf、Merchant")
        self._character_edit.textChanged.connect(self._on_character_changed)
        self._character_edit.editingFinished.connect(self._normalize_character)
        choice_layout.addRow(u"角色名称：", self._character_edit)

        self._action_set_edit = QtWidgets.QLineEdit(u"Unarmed")
        self._action_set_edit.setPlaceholderText(u"可空；例如 Unarmed、Sword、Spear")
        self._action_set_edit.textChanged.connect(self._on_fields_changed)
        choice_layout.addRow(u"动作集：", self._action_set_edit)
        self._purpose_combo = QtWidgets.QComboBox()
        self._purpose_combo.addItems(list(PURPOSES))
        self._purpose_combo.currentIndexChanged.connect(self._on_fields_changed)
        choice_layout.addRow(u"目录分类：", self._purpose_combo)

        rig_row = QtWidgets.QHBoxLayout()
        self._rig_combo = QtWidgets.QComboBox()
        self._rig_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLength)
        self._rig_combo.setMinimumContentsLength(28)
        refresh_btn = QtWidgets.QPushButton(u"刷新")
        refresh_btn.setFixedWidth(68)
        refresh_btn.clicked.connect(self._refresh_rigs)
        choose_rig_btn = QtWidgets.QPushButton(u"选择…")
        choose_rig_btn.clicked.connect(self._choose_personal_rig)
        rig_row.addWidget(self._rig_combo, 1)
        rig_row.addWidget(refresh_btn)
        rig_row.addWidget(choose_rig_btn)
        choice_layout.addRow(u"绑定文件：", rig_row)

        self._action_edit = QtWidgets.QLineEdit()
        self._action_edit.setPlaceholderText(u"例如 Idle、Run、Attack01")
        self._action_edit.textChanged.connect(self._on_fields_changed)
        self._action_edit.editingFinished.connect(self._normalize_action)
        choice_layout.addRow(u"动作名称：", self._action_edit)

        self._stage_combo = QtWidgets.QComboBox()
        self._stage_combo.addItems([u"初版", u"终版", u"监修"])
        self._stage_combo.setCurrentIndex(0)
        self._stage_combo.currentIndexChanged.connect(self._on_stage_changed)
        choice_layout.addRow(u"文件阶段：", self._stage_combo)

        self._version_combo = QtWidgets.QComboBox()
        self._version_combo.addItems(build_review_version_options())
        self._version_combo.currentIndexChanged.connect(self._on_fields_changed)
        choice_layout.addRow(u"监修版本：", self._version_combo)

        self._rig_status = QtWidgets.QLabel(u"")
        self._rig_status.setWordWrap(True)
        self._rig_status.setStyleSheet(u"color:#8ea0b8; font-size:11px;")
        choice_layout.addRow(u"", self._rig_status)

        preview_group = QtWidgets.QGroupBox(u"新建文件预览")
        preview_layout = QtWidgets.QFormLayout(preview_group)
        preview_layout.setContentsMargins(16, 18, 16, 16)
        preview_layout.setHorizontalSpacing(12)
        preview_layout.setVerticalSpacing(14)
        preview_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self._filename_edit = QtWidgets.QLineEdit()
        self._filename_edit.setToolTip(u"可修改文件名；修改后文件路径会同步更新。")
        self._filename_edit.textEdited.connect(self._on_filename_edited)
        self._filename_edit.editingFinished.connect(self._finish_filename_edit)
        preview_layout.addRow(u"文件名称：", self._filename_edit)

        path_row = QtWidgets.QHBoxLayout()
        self._path_edit = QtWidgets.QLineEdit()
        self._path_edit.setPlaceholderText(u"由 Unity Assets 路径推导，或手动选择源文件保存位置")
        browse_btn = QtWidgets.QPushButton(u"浏览…")
        browse_btn.setFixedWidth(76)
        browse_btn.clicked.connect(self._browse_destination)
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse_btn)
        preview_layout.addRow(u"文件路径：", path_row)

        self._stage_preview = QtWidgets.QLineEdit()
        self._stage_preview.setReadOnly(True)
        preview_layout.addRow(u"文件阶段：", self._stage_preview)

        self._author_edit = QtWidgets.QLineEdit()
        self._author_edit.setReadOnly(True)
        preview_layout.addRow(u"文件作者：", self._author_edit)

        self._settings_status = QtWidgets.QLabel(u"")
        self._settings_status.setWordWrap(True)
        self._settings_status.setStyleSheet(u"color:#d5a84b; font-size:11px;")
        preview_layout.addRow(u"", self._settings_status)

        preview_layout.addItem(
            QtWidgets.QSpacerItem(
                10, 10, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
            )
        )
        self._create_btn = QtWidgets.QPushButton(u"确认创建")
        self._create_btn.setMinimumHeight(42)
        self._create_btn.setDefault(True)
        self._create_btn.clicked.connect(self._create_file)
        preview_layout.addRow(u"", self._create_btn)

        layout.addWidget(choice_group, 5)
        layout.addWidget(preview_group, 6)
        self._personal_choice_layout = choice_layout
        self._on_naming_mode_changed()
        self._on_stage_changed()
        return page

    def _build_outdoor_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        self._outdoor_tabs = QtWidgets.QTabWidget()
        self._outdoor_tabs.addTab(self._build_outdoor_role_page(), u"角色配套")

        self._outdoor_tabs.addTab(self._build_outdoor_dialogue_page(), u"剧情对话")

        layout.addWidget(self._outdoor_tabs, 1)
        return page

    def _build_outdoor_role_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(16)

        choice_group = QtWidgets.QGroupBox(u"角色配套与 CS 绑定")
        form = QtWidgets.QFormLayout(choice_group)
        form.setContentsMargins(16, 18, 16, 16)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self._out_module_combo = QtWidgets.QComboBox()
        self._out_module_combo.currentIndexChanged.connect(self._on_outdoor_fields_changed)
        form.addRow(u"模块名称：", self._out_module_combo)

        self._out_category_combo = QtWidgets.QComboBox()
        self._out_category_combo.currentIndexChanged.connect(self._on_outdoor_fields_changed)
        form.addRow(u"角色分类：", self._out_category_combo)

        self._out_character_edit = QtWidgets.QLineEdit()
        self._out_character_edit.setPlaceholderText(u"例如 Hero")
        self._out_character_edit.textChanged.connect(self._on_outdoor_character_changed)
        self._out_character_edit.editingFinished.connect(self._normalize_outdoor_character)
        form.addRow(u"角色名称：", self._out_character_edit)

        rig_row = QtWidgets.QHBoxLayout()
        self._out_rig_combo = QtWidgets.QComboBox()
        self._out_rig_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLength)
        self._out_rig_combo.setMinimumContentsLength(28)
        refresh_btn = QtWidgets.QPushButton(u"刷新")
        refresh_btn.setFixedWidth(68)
        refresh_btn.clicked.connect(self._refresh_outdoor_rigs)
        rig_row.addWidget(self._out_rig_combo, 1)
        rig_row.addWidget(refresh_btn)
        form.addRow(u"CS 绑定：", rig_row)

        self._camera_combo = QtWidgets.QComboBox()
        self._camera_combo.addItems(build_camera_options())
        self._camera_combo.currentIndexChanged.connect(self._on_outdoor_fields_changed)
        form.addRow(u"镜头编号：", self._camera_combo)

        self._out_stage_combo = QtWidgets.QComboBox()
        self._out_stage_combo.addItems([u"初版", u"终版", u"监修"])
        self._out_stage_combo.currentIndexChanged.connect(self._on_outdoor_stage_changed)
        form.addRow(u"文件阶段：", self._out_stage_combo)

        self._out_version_combo = QtWidgets.QComboBox()
        self._out_version_combo.addItems(build_review_version_options())
        self._out_version_combo.currentIndexChanged.connect(self._on_outdoor_fields_changed)
        form.addRow(u"监修版本：", self._out_version_combo)

        self._out_rig_status = QtWidgets.QLabel(u"")
        self._out_rig_status.setWordWrap(True)
        self._out_rig_status.setStyleSheet(u"color:#8ea0b8; font-size:11px;")
        form.addRow(u"", self._out_rig_status)

        preview_group = QtWidgets.QGroupBox(u"新建文件预览")
        preview = QtWidgets.QFormLayout(preview_group)
        preview.setContentsMargins(16, 18, 16, 16)
        preview.setHorizontalSpacing(12)
        preview.setVerticalSpacing(14)
        preview.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self._out_filename_edit = QtWidgets.QLineEdit()
        self._out_filename_edit.setToolTip(u"可修改文件名；修改后文件路径会同步更新。")
        self._out_filename_edit.textEdited.connect(self._on_outdoor_filename_edited)
        self._out_filename_edit.editingFinished.connect(
            self._finish_outdoor_filename_edit
        )
        preview.addRow(u"文件名称：", self._out_filename_edit)

        path_row = QtWidgets.QHBoxLayout()
        self._out_path_edit = QtWidgets.QLineEdit()
        self._out_path_edit.setPlaceholderText(u"请先在打开文件工具中设置本地路径")
        browse_btn = QtWidgets.QPushButton(u"浏览…")
        browse_btn.setFixedWidth(76)
        browse_btn.clicked.connect(self._browse_outdoor_destination)
        path_row.addWidget(self._out_path_edit, 1)
        path_row.addWidget(browse_btn)
        preview.addRow(u"文件路径：", path_row)

        self._out_stage_preview = QtWidgets.QLineEdit()
        self._out_stage_preview.setReadOnly(True)
        preview.addRow(u"文件阶段：", self._out_stage_preview)

        self._out_author_edit = QtWidgets.QLineEdit()
        self._out_author_edit.setReadOnly(True)
        preview.addRow(u"文件作者：", self._out_author_edit)

        self._out_settings_status = QtWidgets.QLabel(u"")
        self._out_settings_status.setWordWrap(True)
        self._out_settings_status.setStyleSheet(u"color:#d5a84b; font-size:11px;")
        preview.addRow(u"", self._out_settings_status)
        preview.addItem(QtWidgets.QSpacerItem(
            10, 10, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        ))

        create_btn = QtWidgets.QPushButton(u"确认创建")
        create_btn.setMinimumHeight(42)
        create_btn.clicked.connect(self._create_outdoor_file)
        preview.addRow(u"", create_btn)

        layout.addWidget(choice_group, 5)
        layout.addWidget(preview_group, 6)
        self._on_outdoor_stage_changed()
        return page

    def _build_outdoor_dialogue_page(self):
        page = QtWidgets.QWidget()
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        content = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(content)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(16)

        choice_group = QtWidgets.QGroupBox(u"剧情编号与角色 CS 绑定")
        choice_layout = QtWidgets.QVBoxLayout(choice_group)
        choice_layout.setContentsMargins(16, 18, 16, 16)
        choice_layout.setSpacing(10)
        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self._dialogue_module_combo = QtWidgets.QComboBox()
        self._dialogue_module_combo.currentIndexChanged.connect(
            self._on_dialogue_fields_changed
        )
        form.addRow(u"模块名称：", self._dialogue_module_combo)

        self._chapter_combo = QtWidgets.QComboBox()
        self._chapter_combo.addItems(build_chapter_options())
        self._chapter_combo.currentIndexChanged.connect(self._on_dialogue_fields_changed)
        form.addRow(u"章节编号：", self._chapter_combo)

        self._scene_combo = QtWidgets.QComboBox()
        self._scene_combo.addItems(build_scene_options())
        self._scene_combo.currentIndexChanged.connect(self._on_dialogue_fields_changed)
        form.addRow(u"场次编号：", self._scene_combo)

        self._dialogue_camera_combo = QtWidgets.QComboBox()
        self._dialogue_camera_combo.addItems(build_camera_options())
        self._dialogue_camera_combo.currentIndexChanged.connect(
            self._on_dialogue_fields_changed
        )
        form.addRow(u"镜头编号：", self._dialogue_camera_combo)

        self._dialogue_stage_combo = QtWidgets.QComboBox()
        self._dialogue_stage_combo.addItems([u"初版", u"终版", u"监修"])
        self._dialogue_stage_combo.currentIndexChanged.connect(
            self._on_dialogue_stage_changed
        )
        form.addRow(u"文件阶段：", self._dialogue_stage_combo)

        self._dialogue_version_combo = QtWidgets.QComboBox()
        self._dialogue_version_combo.addItems(build_review_version_options())
        self._dialogue_version_combo.currentIndexChanged.connect(
            self._on_dialogue_fields_changed
        )
        form.addRow(u"监修版本：", self._dialogue_version_combo)
        choice_layout.addLayout(form)

        role_group = QtWidgets.QGroupBox(u"添加角色")
        role_layout = QtWidgets.QFormLayout(role_group)
        role_layout.setContentsMargins(12, 16, 12, 12)
        role_layout.setHorizontalSpacing(10)
        role_layout.setVerticalSpacing(8)
        role_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self._dialogue_category_combo = QtWidgets.QComboBox()
        self._dialogue_category_combo.currentIndexChanged.connect(
            self._on_dialogue_role_fields_changed
        )
        role_layout.addRow(u"角色分类：", self._dialogue_category_combo)

        self._dialogue_character_edit = QtWidgets.QLineEdit()
        self._dialogue_character_edit.setPlaceholderText(u"例如 Hero")
        self._dialogue_character_edit.textChanged.connect(
            self._on_dialogue_character_changed
        )
        self._dialogue_character_edit.editingFinished.connect(
            self._normalize_dialogue_character
        )
        role_layout.addRow(u"角色名称：", self._dialogue_character_edit)

        rig_row = QtWidgets.QHBoxLayout()
        self._dialogue_rig_combo = QtWidgets.QComboBox()
        self._dialogue_rig_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLength
        )
        self._dialogue_rig_combo.setMinimumContentsLength(24)
        refresh_btn = QtWidgets.QPushButton(u"刷新")
        refresh_btn.setFixedWidth(68)
        refresh_btn.clicked.connect(self._refresh_dialogue_rigs)
        rig_row.addWidget(self._dialogue_rig_combo, 1)
        rig_row.addWidget(refresh_btn)
        role_layout.addRow(u"CS 绑定：", rig_row)

        add_btn = QtWidgets.QPushButton(u"添加角色")
        add_btn.clicked.connect(self._add_dialogue_role)
        role_layout.addRow(u"", add_btn)
        self._dialogue_rig_status = QtWidgets.QLabel(u"")
        self._dialogue_rig_status.setWordWrap(True)
        self._dialogue_rig_status.setStyleSheet(u"color:#8ea0b8; font-size:11px;")
        role_layout.addRow(u"", self._dialogue_rig_status)
        choice_layout.addWidget(role_group)

        self._dialogue_roles_table = QtWidgets.QTableWidget(0, 3)
        self._dialogue_roles_table.setHorizontalHeaderLabels(
            [u"分类", u"角色", u"绑定文件"]
        )
        self._dialogue_roles_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows
        )
        self._dialogue_roles_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection
        )
        self._dialogue_roles_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers
        )
        self._dialogue_roles_table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Stretch
        )
        self._dialogue_roles_table.setMinimumHeight(100)
        choice_layout.addWidget(self._dialogue_roles_table, 1)
        remove_btn = QtWidgets.QPushButton(u"移除选中角色")
        remove_btn.clicked.connect(self._remove_dialogue_role)
        choice_layout.addWidget(remove_btn)

        preview_group = QtWidgets.QGroupBox(u"新建文件预览")
        preview = QtWidgets.QFormLayout(preview_group)
        preview.setContentsMargins(16, 18, 16, 16)
        preview.setHorizontalSpacing(12)
        preview.setVerticalSpacing(14)
        preview.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self._dialogue_filename_edit = QtWidgets.QLineEdit()
        self._dialogue_filename_edit.setToolTip(
            u"可修改文件名；修改后文件路径会同步更新。"
        )
        self._dialogue_filename_edit.textEdited.connect(
            self._on_dialogue_filename_edited
        )
        self._dialogue_filename_edit.editingFinished.connect(
            self._finish_dialogue_filename_edit
        )
        preview.addRow(u"文件名称：", self._dialogue_filename_edit)

        path_row = QtWidgets.QHBoxLayout()
        self._dialogue_path_edit = QtWidgets.QLineEdit()
        self._dialogue_path_edit.setPlaceholderText(u"请先在打开文件工具中设置本地路径")
        browse_btn = QtWidgets.QPushButton(u"浏览…")
        browse_btn.setFixedWidth(76)
        browse_btn.clicked.connect(self._browse_dialogue_destination)
        path_row.addWidget(self._dialogue_path_edit, 1)
        path_row.addWidget(browse_btn)
        preview.addRow(u"文件路径：", path_row)

        self._dialogue_stage_preview = QtWidgets.QLineEdit()
        self._dialogue_stage_preview.setReadOnly(True)
        preview.addRow(u"文件阶段：", self._dialogue_stage_preview)

        self._dialogue_author_edit = QtWidgets.QLineEdit()
        self._dialogue_author_edit.setReadOnly(True)
        preview.addRow(u"文件作者：", self._dialogue_author_edit)

        self._dialogue_settings_status = QtWidgets.QLabel(u"")
        self._dialogue_settings_status.setWordWrap(True)
        self._dialogue_settings_status.setStyleSheet(
            u"color:#d5a84b; font-size:11px;"
        )
        preview.addRow(u"", self._dialogue_settings_status)
        preview.addItem(QtWidgets.QSpacerItem(
            10, 10, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        ))
        create_btn = QtWidgets.QPushButton(u"确认创建并合并角色")
        create_btn.setMinimumHeight(42)
        create_btn.clicked.connect(self._create_dialogue_file)
        preview.addRow(u"", create_btn)

        layout.addWidget(choice_group, 6)
        layout.addWidget(preview_group, 5)
        content.setMinimumHeight(max(600, content.sizeHint().height()))
        scroll.setWidget(content)
        page_layout.addWidget(scroll, 1)
        self._on_dialogue_stage_changed()
        return page

    def showEvent(self, event):
        self._reload_shared_settings(force_path=False)
        super(NewFileDialog, self).showEvent(event)

    def _reload_shared_settings(self, force_path=False):
        self._publish_config = load_publish_config()
        afm_config = load_anim_file_manager_config(self._install_root)
        self._local_root = _as_text(afm_config.get(u"local_root", u"")).strip()

        selected = _as_text(self._category_combo.currentText())
        categories = indoor_categories_from_map(
            self._publish_config.get(u"category_folder_map")
        )
        self._category_combo.blockSignals(True)
        try:
            self._category_combo.clear()
            self._category_combo.addItems(categories)
            index = self._category_combo.findText(selected)
            self._category_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self._category_combo.blockSignals(False)

        author = _as_text(self._publish_config.get(u"publisher_name", u"")).strip()
        self._author_edit.setText(author or u"未设置")
        messages = []
        if self._is_personal():
            if not source_characters_root(self._publish_config.get(u"unity_root", u"")):
                messages.append(u"在发布设置中选择个人工程 Client/Assets；也可手动指定源文件保存位置。")
        elif not self._local_root:
            messages.append(u"请先在“打开文件”工具中设置本地路径。")
        if not self._is_personal() and not author:
            messages.append(u"请先在发布工具设置中填写发布负责人。")
        self._settings_status.setText(u"\n".join(messages))
        self._update_preview(force_path=force_path)
        self._reload_outdoor_options(force_path=force_path)

    def _reload_outdoor_options(self, force_path=False):
        selected_module = _as_text(self._out_module_combo.currentData()).strip()
        module_map = merge_module_folder_map(
            self._publish_config.get(u"module_folder_map")
        )
        tag_map = merge_module_tag_map(
            self._publish_config.get(u"module_folder_map"),
            self._publish_config.get(u"module_tag_map"),
        )
        module_codes = module_codes_for_tag(
            self._publish_config.get(u"module_folder_map"),
            tag_map,
            MODULE_TAG_ROLE_SUPPORT,
        )
        preferred = [u"UL", u"GA", u"DE", u"ER"]
        module_codes = [code for code in preferred if code in module_codes] + sorted([
            code for code in module_codes if code not in preferred
        ])
        self._out_module_combo.blockSignals(True)
        try:
            self._out_module_combo.clear()
            for code in module_codes:
                label = _ROLE_MODULE_LABELS.get(
                    code, module_map.get(code, code)
                )
                self._out_module_combo.addItem(label, code)
            index = self._out_module_combo.findData(selected_module)
            self._out_module_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self._out_module_combo.blockSignals(False)

        selected_category = _as_text(self._out_category_combo.currentText())
        categories = indoor_categories_from_map(
            self._publish_config.get(u"category_folder_map")
        )
        self._out_category_combo.blockSignals(True)
        try:
            self._out_category_combo.clear()
            self._out_category_combo.addItems(categories)
            index = self._out_category_combo.findText(selected_category)
            self._out_category_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self._out_category_combo.blockSignals(False)

        author = _as_text(self._publish_config.get(u"publisher_name", u"")).strip()
        self._out_author_edit.setText(author or u"未设置")
        messages = []
        if not self._local_root:
            messages.append(u"请先在“打开文件”工具中设置本地路径。")
        if not author:
            messages.append(u"请先在发布工具设置中填写发布负责人。")
        if not module_codes:
            messages.append(u"发布工具中没有标记为“角色配套”的局外模块。")
        self._out_settings_status.setText(u"\n".join(messages))
        self._update_outdoor_preview(force_path=force_path)
        if self._out_character_edit.text().strip():
            self._refresh_outdoor_rigs()
        self._reload_dialogue_options(force_path=force_path)

    def _reload_dialogue_options(self, force_path=False):
        selected_module = _as_text(
            self._dialogue_module_combo.currentData()
        ).strip()
        module_map = merge_module_folder_map(
            self._publish_config.get(u"module_folder_map")
        )
        tag_map = merge_module_tag_map(
            self._publish_config.get(u"module_folder_map"),
            self._publish_config.get(u"module_tag_map"),
        )
        module_codes = module_codes_for_tag(
            self._publish_config.get(u"module_folder_map"),
            tag_map,
            MODULE_TAG_STORY_DIALOGUE,
        )
        preferred = [u"EN", u"RE", u"CS", u"QTE", u"DI"]
        module_codes = [code for code in preferred if code in module_codes] + sorted([
            code for code in module_codes if code not in preferred
        ])
        self._dialogue_module_combo.blockSignals(True)
        try:
            self._dialogue_module_combo.clear()
            for code in module_codes:
                self._dialogue_module_combo.addItem(module_map.get(code, code), code)
            index = self._dialogue_module_combo.findData(selected_module)
            self._dialogue_module_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self._dialogue_module_combo.blockSignals(False)

        selected_category = _as_text(
            self._dialogue_category_combo.currentText()
        )
        categories = indoor_categories_from_map(
            self._publish_config.get(u"category_folder_map")
        )
        self._dialogue_category_combo.blockSignals(True)
        try:
            self._dialogue_category_combo.clear()
            self._dialogue_category_combo.addItems(categories)
            index = self._dialogue_category_combo.findText(selected_category)
            self._dialogue_category_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self._dialogue_category_combo.blockSignals(False)

        author = _as_text(self._publish_config.get(u"publisher_name", u"")).strip()
        self._dialogue_author_edit.setText(author or u"未设置")
        messages = []
        if not self._local_root:
            messages.append(u"请先在“打开文件”工具中设置本地路径。")
        if not author:
            messages.append(u"请先在发布工具设置中填写发布负责人。")
        if not module_codes:
            messages.append(u"发布工具中没有标记为“剧情对话”的局外模块。")
        self._dialogue_settings_status.setText(u"\n".join(messages))
        self._update_dialogue_preview(force_path=force_path)
        if self._dialogue_character_edit.text().strip():
            self._refresh_dialogue_rigs()

    def _normalize_character(self):
        value = normalize_name_part(self._character_edit.text())
        if value != self._character_edit.text():
            self._character_edit.setText(value)
        self._refresh_rigs()

    def _normalize_action(self):
        value = normalize_name_part(self._action_edit.text())
        if value != self._action_edit.text():
            self._action_edit.setText(value)
        self._update_preview()

    def _on_character_changed(self, *args):
        self._rig_timer.start()
        self._on_fields_changed()

    def _on_fields_changed(self, *args):
        self._update_preview()
        if self.sender() is self._category_combo and self._character_edit.text().strip():
            self._refresh_rigs()

    def _is_personal(self):
        return self._naming_mode.currentIndex() == 0

    def _on_naming_mode_changed(self, *args):
        if not hasattr(self, "_personal_choice_layout"):
            return
        personal = self._is_personal()
        for widget in (self._category_combo, self._stage_combo, self._version_combo):
            widget.setVisible(not personal)
            label = self._personal_choice_layout.labelForField(widget)
            if label is not None:
                label.setVisible(not personal)
        for widget in (self._action_set_edit, self._purpose_combo):
            widget.setVisible(personal)
            self._personal_choice_layout.labelForField(widget).setVisible(personal)
        self._filename_edit.clear()
        self._update_preview(force_path=True)
        self._refresh_rigs()

    def _choose_personal_rig(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, u"选择个人绑定源文件", u"", u"3ds Max (*.max)"
        )
        if path:
            self._manual_rig_character = normalize_name_part(self._character_edit.text())
            self._rig_combo.addItem(os.path.basename(path), path)
            self._rig_combo.setCurrentIndex(self._rig_combo.count() - 1)
            self._rig_status.setText(u"使用手动选择的绑定；不要求旧 LOD 文件命名。")

    def _on_stage_changed(self, *args):
        is_review = self._stage_combo.currentText() == u"监修"
        self._version_combo.setEnabled(is_review)
        self._update_preview()

    def _stage_state(self):
        stage = _as_text(self._stage_combo.currentText()) or u"初版"
        version = _as_text(self._version_combo.currentText()) if stage == u"监修" else u""
        label = stage + version if stage == u"监修" else stage
        return stage, version, label

    def _set_generated_filename(self, editor, generated, state_name):
        current = _as_text(editor.text()).strip()
        previous = _as_text(getattr(self, state_name, u"")).strip()
        if not current or current == previous:
            editor.setText(generated)
            current = generated
        setattr(self, state_name, generated)
        return current

    def _sync_filename_to_path(self, filename, path_editor, path_state_name):
        filename = _as_text(filename).strip()
        current_path = _as_text(path_editor.text()).strip()
        if (
            not filename
            or not current_path
            or os.path.basename(filename) != filename
            or u"/" in filename
            or u"\\" in filename
        ):
            return
        previous_auto = _as_text(getattr(self, path_state_name, u"")).strip()
        updated_path = os.path.normpath(
            os.path.join(os.path.dirname(current_path), filename)
        )
        path_editor.setText(updated_path)
        if current_path == previous_auto:
            setattr(self, path_state_name, updated_path)

    def _finish_filename(self, editor, path_editor, path_state_name):
        filename = _as_text(editor.text()).strip()
        if filename and not filename.lower().endswith(u".max"):
            filename += u".max"
        editor.setText(filename)
        self._sync_filename_to_path(filename, path_editor, path_state_name)

    def _on_filename_edited(self, filename):
        self._sync_filename_to_path(filename, self._path_edit, u"_last_auto_path")
        self._update_preview()

    def _finish_filename_edit(self):
        self._finish_filename(
            self._filename_edit, self._path_edit, u"_last_auto_path"
        )
        self._update_preview()

    def _on_outdoor_filename_edited(self, filename):
        self._sync_filename_to_path(
            filename, self._out_path_edit, u"_last_out_auto_path"
        )
        self._update_outdoor_preview()

    def _finish_outdoor_filename_edit(self):
        self._finish_filename(
            self._out_filename_edit,
            self._out_path_edit,
            u"_last_out_auto_path",
        )
        self._update_outdoor_preview()

    def _on_dialogue_filename_edited(self, filename):
        self._sync_filename_to_path(
            filename, self._dialogue_path_edit, u"_last_dialogue_auto_path"
        )
        self._update_dialogue_preview()

    def _finish_dialogue_filename_edit(self):
        self._finish_filename(
            self._dialogue_filename_edit,
            self._dialogue_path_edit,
            u"_last_dialogue_auto_path",
        )
        self._update_dialogue_preview()

    def _validate_preview_filename(self, editor, outdoor=False):
        filename = _as_text(editor.text()).strip()
        if not filename:
            return False, u"文件名称不能为空", u""
        if os.path.basename(filename) != filename or u"/" in filename or u"\\" in filename:
            return False, u"文件名称不能包含路径", u""
        if not filename.lower().endswith(u".max"):
            return False, u"文件名称必须以 .max 结尾", u""
        stem = filename[:-4]
        if outdoor:
            ok, message, _ = validate_outdoor_name(
                stem,
                self._publish_config.get(u"module_folder_map"),
                self._publish_config.get(u"outdoor_type_folder_map"),
                self._publish_config.get(u"outdoor_asset_types"),
                self._publish_config.get(u"category_folder_map"),
            )
        else:
            if self._is_personal():
                ok, message, _ = parse_name(stem)
            else:
                ok, message, parsed = validate_indoor_name(
                    stem, self._publish_config.get(u"category_folder_map")
                )
                if ok and parsed.get(u"naming_scheme") == u"personal":
                    ok, message = False, u"短命名请切换到个人模式。"
        if not ok:
            return False, u"文件名称不符合发布规范：{0}".format(message), u""
        return True, u"", filename

    def _update_preview(self, force_path=False):
        category = _as_text(self._category_combo.currentText()).strip()
        character = normalize_name_part(self._character_edit.text())
        action = normalize_name_part(self._action_edit.text())
        generated_filename = u""
        if self._is_personal():
            try:
                generated_filename = compose_name(
                    character, action, normalize_name_part(self._action_set_edit.text())
                ) + u".max"
            except ValueError:
                pass
        elif category and character and action:
            generated_filename = compose_indoor_filename(category, character, action)
        filename = self._set_generated_filename(
            self._filename_edit, generated_filename, u"_last_auto_filename"
        )
        stage, version, stage_label = self._stage_state()
        self._stage_preview.setText(u"由版本控制管理，不进入名称或目录" if self._is_personal() else stage_label)

        auto_path = u""
        if self._is_personal() and filename:
            valid, _, parsed = validate_indoor_name(filename[:-4])
            if valid and parsed.get(u"naming_scheme") == u"personal":
                try:
                    auto_path = source_destination(
                        self._publish_config.get(u"unity_root", u""), parsed[u"char_name"],
                        _as_text(self._purpose_combo.currentText()), filename
                    )
                except ValueError:
                    pass
        elif self._local_root and filename:
            path_category = category
            path_character = character
            if filename.lower().endswith(u".max"):
                valid, _, parsed = validate_indoor_name(
                    filename[:-4], self._publish_config.get(u"category_folder_map")
                )
                if valid:
                    path_category = parsed.get(u"category", path_category)
                    path_character = parsed.get(u"char_name", path_character)
            auto_path = build_indoor_destination(
                self._local_root,
                path_category,
                path_character,
                stage,
                version,
                filename,
            )
        current = _as_text(self._path_edit.text()).strip()
        if force_path or not current or current == self._last_auto_path:
            self._path_edit.setText(auto_path)
        self._last_auto_path = auto_path

    def _refresh_rigs(self):
        if self._is_personal():
            character = normalize_name_part(self._character_edit.text())
            root = source_characters_root(self._publish_config.get(u"unity_root", u""))
            current = _as_text(self._rig_combo.currentData())
            self._rig_combo.clear()
            # Restrict discovery to this character's personal Rig directory.
            if character and root and validate_name_part(character, u"角色")[0]:
                rig_dir = os.path.join(root, character, u"Rig")
                if os.path.isdir(rig_dir):
                    for folder, _, files in os.walk(rig_dir):
                        for name in sorted(files):
                            if name.lower().endswith(u".max"):
                                path = os.path.join(folder, name)
                                self._rig_combo.addItem(os.path.relpath(path, rig_dir), path)
            index = self._rig_combo.findData(current)
            if (index < 0 and current and os.path.isfile(current)
                    and getattr(self, "_manual_rig_character", u"") == character):
                self._rig_combo.addItem(os.path.basename(current), current)
                index = self._rig_combo.count() - 1
            if index >= 0:
                self._rig_combo.setCurrentIndex(index)
            self._rig_status.setText(u"个人绑定可放在 ArtSource/Characters/<角色>/Rig；也可手动选择。")
            return
        character = normalize_name_part(self._character_edit.text())
        self._rig_combo.clear()
        self._rig_items = []
        if not character:
            self._rig_status.setText(u"输入角色名称后将自动查找局内 LOD 绑定。")
            return
        root = _as_text(self._publish_config.get(u"character_rig_root", u"")).strip()
        category = _as_text(self._category_combo.currentText()).strip()
        self._rig_items = find_indoor_binding_files(character, root, category=category)
        for item in self._rig_items:
            path = _as_text(item.get(u"path", u""))
            self._rig_combo.addItem(os.path.basename(path), path)
            self._rig_combo.setItemData(
                self._rig_combo.count() - 1, path, QtCore.Qt.ToolTipRole
            )
        if self._rig_items:
            has_exact = any(
                binding_category_from_path(item.get(u"path", u"")).lower()
                == category.lower()
                for item in self._rig_items
            )
            if has_exact:
                message = u"找到 {0} 个 {1} LOD 绑定，较新版本排在上方。".format(
                    len(self._rig_items), category
                )
            else:
                message = (
                    u"未找到 {0}_{1} 的 LOD 绑定，已显示该角色其他分类的 {2} 个绑定。"
                ).format(category, character, len(self._rig_items))
            self._rig_status.setText(message)
        else:
            self._rig_status.setText(u"未找到与 {0} 对应的局内 LOD 绑定。".format(character))

    def _browse_destination(self):
        filename = _as_text(self._filename_edit.text()).strip() or u"新建文件.max"
        start = _as_text(self._path_edit.text()).strip()
        if not start:
            start = os.path.join(self._local_root, filename) if self._local_root else filename
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, u"选择新建文件路径", start, u"3ds Max 文件 (*.max)"
        )
        if selected:
            if not selected.lower().endswith(u".max"):
                selected += u".max"
            self._filename_edit.setText(os.path.basename(selected))
            self._path_edit.setText(selected)

    def _normalize_outdoor_character(self):
        value = normalize_name_part(self._out_character_edit.text())
        if value != self._out_character_edit.text():
            self._out_character_edit.setText(value)
        self._refresh_outdoor_rigs()

    def _on_outdoor_character_changed(self, *args):
        self._out_rig_timer.start()
        self._on_outdoor_fields_changed()

    def _on_outdoor_fields_changed(self, *args):
        self._update_outdoor_preview()
        if (
            self.sender() is self._out_category_combo
            and self._out_character_edit.text().strip()
        ):
            self._refresh_outdoor_rigs()

    def _on_outdoor_stage_changed(self, *args):
        is_review = self._out_stage_combo.currentText() == u"监修"
        self._out_version_combo.setEnabled(is_review)
        self._update_outdoor_preview()

    def _outdoor_stage_state(self):
        stage = _as_text(self._out_stage_combo.currentText()) or u"初版"
        version = (
            _as_text(self._out_version_combo.currentText())
            if stage == u"监修" else u""
        )
        label = stage + version if stage == u"监修" else stage
        return stage, version, label

    def _update_outdoor_preview(self, force_path=False):
        module_code = _as_text(self._out_module_combo.currentData()).strip()
        category = _as_text(self._out_category_combo.currentText()).strip()
        character = normalize_name_part(self._out_character_edit.text())
        camera_name = _as_text(self._camera_combo.currentText()).strip()
        generated_filename = compose_outdoor_role_filename(
            module_code, category, character, camera_name
        )
        if not (module_code and category and character and camera_name):
            generated_filename = u""
        filename = self._set_generated_filename(
            self._out_filename_edit,
            generated_filename,
            u"_last_out_auto_filename",
        )

        stage, version, stage_label = self._outdoor_stage_state()
        self._out_stage_preview.setText(stage_label)
        auto_path = u""
        if self._local_root and filename:
            module_map = merge_module_folder_map(
                self._publish_config.get(u"module_folder_map")
            )
            type_map = merge_type_folder_map(
                self._publish_config.get(u"outdoor_type_folder_map")
            )
            module_folder = module_map.get(module_code, module_code)
            type_folder = type_map.get(category, category)
            character_folder = character
            if filename.lower().endswith(u".max"):
                valid, _, parsed = validate_outdoor_name(
                    filename[:-4],
                    self._publish_config.get(u"module_folder_map"),
                    self._publish_config.get(u"outdoor_type_folder_map"),
                    self._publish_config.get(u"outdoor_asset_types"),
                    self._publish_config.get(u"category_folder_map"),
                )
                if valid:
                    module_folder = parsed.get(u"module_folder", module_folder)
                    type_folder = parsed.get(u"type_folder", type_folder)
                    character_folder = parsed.get(u"char_folder", character_folder)
            auto_path = build_outdoor_destination(
                self._local_root,
                module_folder,
                type_folder,
                character_folder,
                stage,
                version,
                filename,
            )
        current = _as_text(self._out_path_edit.text()).strip()
        if force_path or not current or current == self._last_out_auto_path:
            self._out_path_edit.setText(auto_path)
        self._last_out_auto_path = auto_path

    def _refresh_outdoor_rigs(self):
        character = normalize_name_part(self._out_character_edit.text())
        self._out_rig_combo.clear()
        self._out_rig_items = []
        if not character:
            self._out_rig_status.setText(u"输入角色名称后将自动查找局外 CS 绑定。")
            return
        root = _as_text(self._publish_config.get(u"character_rig_root", u"")).strip()
        category = _as_text(self._out_category_combo.currentText()).strip()
        self._out_rig_items = find_outdoor_binding_files(
            character, root, category=category
        )
        for item in self._out_rig_items:
            path = _as_text(item.get(u"path", u""))
            self._out_rig_combo.addItem(os.path.basename(path), path)
            self._out_rig_combo.setItemData(
                self._out_rig_combo.count() - 1, path, QtCore.Qt.ToolTipRole
            )
        if self._out_rig_items:
            has_exact = any(
                binding_category_from_path(item.get(u"path", u"")).lower()
                == category.lower()
                for item in self._out_rig_items
            )
            if has_exact:
                message = u"找到 {0} 个 {1} CS 绑定，较新版本排在上方。".format(
                    len(self._out_rig_items), category
                )
            else:
                message = (
                    u"未找到 {0}_{1} 的 CS 绑定，已显示该角色其他分类的 {2} 个绑定。"
                ).format(category, character, len(self._out_rig_items))
            self._out_rig_status.setText(message)
        else:
            self._out_rig_status.setText(
                u"未找到与 {0}_{1} 对应的局外 CS 绑定。".format(
                    category, character
                )
            )

    def _browse_outdoor_destination(self):
        filename = _as_text(self._out_filename_edit.text()).strip() or u"新建文件.max"
        start = _as_text(self._out_path_edit.text()).strip()
        if not start:
            start = os.path.join(self._local_root, filename) if self._local_root else filename
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, u"选择新建文件路径", start, u"3ds Max 文件 (*.max)"
        )
        if selected:
            if not selected.lower().endswith(u".max"):
                selected += u".max"
            self._out_filename_edit.setText(os.path.basename(selected))
            self._out_path_edit.setText(selected)

    def _validate_outdoor_create(self):
        module_code = _as_text(self._out_module_combo.currentData()).strip()
        if not module_code:
            return False, u"请选择标记为“角色配套”的局外模块"
        category = _as_text(self._out_category_combo.currentText()).strip()
        if not category:
            return False, u"请选择角色分类"
        ok, message, character = validate_name_part(
            self._out_character_edit.text(), u"角色名称"
        )
        if not ok:
            return False, message
        if not self._local_root:
            return False, u"请先在“打开文件”工具中设置本地路径"
        author = _as_text(self._publish_config.get(u"publisher_name", u"")).strip()
        if not author:
            return False, u"请先在发布工具设置中填写发布负责人"
        source = _as_text(self._out_rig_combo.currentData()).strip()
        if not source:
            return False, u"请选择有效的 CS 绑定文件"
        ok, message, filename = self._validate_preview_filename(
            self._out_filename_edit, outdoor=True
        )
        if not ok:
            return False, message
        destination = os.path.normpath(_as_text(self._out_path_edit.text()).strip())
        if not os.path.isabs(destination):
            return False, u"文件路径必须是完整的绝对路径"
        if os.path.basename(destination).lower() != filename.lower():
            return False, u"文件路径末尾必须与文件名称一致：{0}".format(filename)
        return True, {u"source": source, u"destination": destination}

    def _create_outdoor_file(self):
        ok, result = self._validate_outdoor_create()
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"无法创建", result)
            return
        ok, copied = copy_binding_to_destination(
            result[u"source"], result[u"destination"]
        )
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"创建失败", copied)
            return
        self._open_created_file(copied)

    def _on_dialogue_fields_changed(self, *args):
        self._update_dialogue_preview()

    def _on_dialogue_stage_changed(self, *args):
        is_review = self._dialogue_stage_combo.currentText() == u"监修"
        self._dialogue_version_combo.setEnabled(is_review)
        self._update_dialogue_preview()

    def _dialogue_stage_state(self):
        stage = _as_text(self._dialogue_stage_combo.currentText()) or u"初版"
        version = (
            _as_text(self._dialogue_version_combo.currentText())
            if stage == u"监修" else u""
        )
        label = stage + version if stage == u"监修" else stage
        return stage, version, label

    def _update_dialogue_preview(self, force_path=False):
        module_code = _as_text(self._dialogue_module_combo.currentData()).strip()
        chapter_label = _as_text(self._chapter_combo.currentText()).strip()
        scene_label = _as_text(self._scene_combo.currentText()).strip()
        camera_name = _as_text(self._dialogue_camera_combo.currentText()).strip()
        generated_filename = compose_outdoor_dialogue_filename(
            module_code, chapter_label, scene_label, camera_name
        )
        filename = self._set_generated_filename(
            self._dialogue_filename_edit,
            generated_filename,
            u"_last_dialogue_auto_filename",
        )

        stage, version, stage_label = self._dialogue_stage_state()
        self._dialogue_stage_preview.setText(stage_label)
        auto_path = u""
        if self._local_root and filename:
            module_map = merge_module_folder_map(
                self._publish_config.get(u"module_folder_map")
            )
            module_folder = module_map.get(module_code, module_code)
            type_folder = chapter_label
            scene_folder = scene_label
            if filename.lower().endswith(u".max"):
                valid, _, parsed = validate_outdoor_name(
                    filename[:-4],
                    self._publish_config.get(u"module_folder_map"),
                    self._publish_config.get(u"outdoor_type_folder_map"),
                    self._publish_config.get(u"outdoor_asset_types"),
                    self._publish_config.get(u"category_folder_map"),
                )
                if valid:
                    module_folder = parsed.get(u"module_folder", module_folder)
                    type_folder = parsed.get(u"type_folder", type_folder)
                    scene_folder = parsed.get(u"char_folder", scene_folder)
            auto_path = build_outdoor_destination(
                self._local_root,
                module_folder,
                type_folder,
                scene_folder,
                stage,
                version,
                filename,
            )
        current = _as_text(self._dialogue_path_edit.text()).strip()
        if force_path or not current or current == self._last_dialogue_auto_path:
            self._dialogue_path_edit.setText(auto_path)
        self._last_dialogue_auto_path = auto_path

    def _normalize_dialogue_character(self):
        value = normalize_name_part(self._dialogue_character_edit.text())
        if value != self._dialogue_character_edit.text():
            self._dialogue_character_edit.setText(value)
        self._refresh_dialogue_rigs()

    def _on_dialogue_character_changed(self, *args):
        self._dialogue_rig_timer.start()

    def _on_dialogue_role_fields_changed(self, *args):
        if self._dialogue_character_edit.text().strip():
            self._refresh_dialogue_rigs()

    def _refresh_dialogue_rigs(self):
        character = normalize_name_part(self._dialogue_character_edit.text())
        self._dialogue_rig_combo.clear()
        self._dialogue_rig_items = []
        if not character:
            self._dialogue_rig_status.setText(
                u"输入角色名称后将自动查找局外 CS 绑定。"
            )
            return
        root = _as_text(self._publish_config.get(u"character_rig_root", u"")).strip()
        category = _as_text(self._dialogue_category_combo.currentText()).strip()
        self._dialogue_rig_items = find_outdoor_binding_files(
            character, root, category=category
        )
        for item in self._dialogue_rig_items:
            path = _as_text(item.get(u"path", u""))
            self._dialogue_rig_combo.addItem(os.path.basename(path), path)
            self._dialogue_rig_combo.setItemData(
                self._dialogue_rig_combo.count() - 1, path, QtCore.Qt.ToolTipRole
            )
        if self._dialogue_rig_items:
            has_exact = any(
                binding_category_from_path(item.get(u"path", u"")).lower()
                == category.lower()
                for item in self._dialogue_rig_items
            )
            if has_exact:
                message = u"找到 {0} 个 {1} CS 绑定，较新版本排在上方。".format(
                    len(self._dialogue_rig_items), category
                )
            else:
                message = (
                    u"未找到 {0}_{1} 的 CS 绑定，已显示该角色其他分类的 {2} 个绑定。"
                ).format(category, character, len(self._dialogue_rig_items))
            self._dialogue_rig_status.setText(message)
        else:
            self._dialogue_rig_status.setText(
                u"未找到与 {0}_{1} 对应的局外 CS 绑定。".format(
                    category, character
                )
            )

    def _add_dialogue_role(self):
        category = _as_text(self._dialogue_category_combo.currentText()).strip()
        ok, message, character = validate_name_part(
            self._dialogue_character_edit.text(), u"角色名称"
        )
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"无法添加角色", message)
            return
        source = _as_text(self._dialogue_rig_combo.currentData()).strip()
        if not source or not os.path.isfile(source):
            QtWidgets.QMessageBox.warning(
                self, u"无法添加角色", u"请选择有效的 CS 绑定文件"
            )
            return
        normalized_source = os.path.normcase(os.path.normpath(source))
        for row in range(self._dialogue_roles_table.rowCount()):
            item = self._dialogue_roles_table.item(row, 2)
            existing = _as_text(item.data(QtCore.Qt.UserRole)) if item else u""
            if os.path.normcase(os.path.normpath(existing)) == normalized_source:
                QtWidgets.QMessageBox.information(
                    self, u"角色已添加", u"该 CS 绑定已经在角色清单中。"
                )
                return

        row = self._dialogue_roles_table.rowCount()
        self._dialogue_roles_table.insertRow(row)
        self._dialogue_roles_table.setItem(
            row, 0, QtWidgets.QTableWidgetItem(category)
        )
        self._dialogue_roles_table.setItem(
            row, 1, QtWidgets.QTableWidgetItem(character)
        )
        binding_item = QtWidgets.QTableWidgetItem(os.path.basename(source))
        binding_item.setData(QtCore.Qt.UserRole, source)
        binding_item.setToolTip(source)
        self._dialogue_roles_table.setItem(row, 2, binding_item)
        self._dialogue_character_edit.clear()
        self._dialogue_rig_status.setText(
            u"已添加 {0}_{1}；可继续添加其他角色。".format(category, character)
        )

    def _remove_dialogue_role(self):
        row = self._dialogue_roles_table.currentRow()
        if row >= 0:
            self._dialogue_roles_table.removeRow(row)

    def _dialogue_sources(self):
        sources = []
        for row in range(self._dialogue_roles_table.rowCount()):
            item = self._dialogue_roles_table.item(row, 2)
            source = _as_text(item.data(QtCore.Qt.UserRole)) if item else u""
            if source:
                sources.append(source)
        return sources

    def _browse_dialogue_destination(self):
        filename = _as_text(
            self._dialogue_filename_edit.text()
        ).strip() or u"新建文件.max"
        start = _as_text(self._dialogue_path_edit.text()).strip()
        if not start:
            start = os.path.join(self._local_root, filename) if self._local_root else filename
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, u"选择新建文件路径", start, u"3ds Max 文件 (*.max)"
        )
        if selected:
            if not selected.lower().endswith(u".max"):
                selected += u".max"
            self._dialogue_filename_edit.setText(os.path.basename(selected))
            self._dialogue_path_edit.setText(selected)

    def _validate_dialogue_create(self):
        module_code = _as_text(self._dialogue_module_combo.currentData()).strip()
        if not module_code:
            return False, u"请选择标记为“剧情对话”的局外模块"
        if not self._local_root:
            return False, u"请先在“打开文件”工具中设置本地路径"
        author = _as_text(self._publish_config.get(u"publisher_name", u"")).strip()
        if not author:
            return False, u"请先在发布工具设置中填写发布负责人"
        sources = self._dialogue_sources()
        if not sources:
            return False, u"请至少添加一个角色的 CS 绑定"
        for source in sources:
            if not os.path.isfile(source):
                return False, u"角色绑定文件不存在：{0}".format(source)
        ok, message, filename = self._validate_preview_filename(
            self._dialogue_filename_edit, outdoor=True
        )
        if not ok:
            return False, message
        destination = os.path.normpath(
            _as_text(self._dialogue_path_edit.text()).strip()
        )
        if not os.path.isabs(destination):
            return False, u"文件路径必须是完整的绝对路径"
        if os.path.basename(destination).lower() != filename.lower():
            return False, u"文件路径末尾必须与文件名称一致：{0}".format(filename)
        if os.path.exists(destination):
            return False, u"目标文件已存在，不会覆盖：{0}".format(destination)
        return True, {u"sources": sources, u"destination": destination}

    @staticmethod
    def _maxscript_verbatim_path(path):
        return u'@"{0}"'.format(_as_text(path).replace(u'"', u'""'))

    def _create_dialogue_file(self):
        ok, result = self._validate_dialogue_create()
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"无法创建", result)
            return

        destination = result[u"destination"]
        sources = result[u"sources"]
        folder = os.path.dirname(destination)
        temp_path = u""
        try:
            import pymxs
            runtime = pymxs.runtime
            if runtime.checkForSave() is False:
                return
            if not os.path.isdir(folder):
                os.makedirs(folder)
            handle, temp_path = tempfile.mkstemp(
                prefix=".op_dialogue_", suffix=".max", dir=folder
            )
            os.close(handle)
            shutil.copy2(sources[0], temp_path)
            runtime.loadMaxFile(temp_path, quiet=True, useFileUnits=True)
            for source in sources[1:]:
                script = u"""(
                    local beforeCount = objects.count
                    local mergeOk = false
                    try (mergeOk = mergeMAXFile {0} #select #autoRenameDups quiet:true)
                    catch (mergeOk = false)
                    (mergeOk == true) or (objects.count > beforeCount)
                )""".format(self._maxscript_verbatim_path(source))
                if not runtime.execute(script):
                    raise RuntimeError(u"合并角色绑定失败：{0}".format(source))
            runtime.saveMaxFile(destination, quiet=True)
            if not os.path.isfile(destination):
                raise RuntimeError(u"3ds Max 未生成目标文件")
        except Exception as exc:
            if os.path.isfile(destination):
                try:
                    os.remove(destination)
                except Exception:
                    pass
            recovery = (
                u"\n\n当前场景可能保留了已合并内容，可手动另存。"
                if temp_path else u""
            )
            QtWidgets.QMessageBox.warning(
                self, u"创建失败", u"{0}{1}".format(_as_text(exc), recovery)
            )
            return
        if temp_path and os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        self.accept()

    def _validate_create(self):
        category = _as_text(self._category_combo.currentText()).strip()
        if not self._is_personal() and not category:
            return False, u"请选择角色分类"
        ok, message, character = validate_name_part(
            self._character_edit.text(), u"角色名称"
        )
        if not ok:
            return False, message
        ok, message, action = validate_name_part(self._action_edit.text(), u"动作名称")
        if not ok:
            return False, message
        if self._is_personal():
            action_set = normalize_name_part(self._action_set_edit.text())
            if action_set and not validate_name_part(action_set, u"动作集")[0]:
                return False, u"动作集只能使用字母数字，以字母开头；也可以留空。"
        elif not self._local_root:
            return False, u"请先在“打开文件”工具中设置本地路径"
        author = _as_text(self._publish_config.get(u"publisher_name", u"")).strip()
        if not self._is_personal() and not author:
            return False, u"请先在发布工具设置中填写发布负责人"
        source = _as_text(self._rig_combo.currentData()).strip()
        if not source:
            return False, u"请选择有效的绑定 .max 文件"
        ok, message, filename = self._validate_preview_filename(
            self._filename_edit, outdoor=False
        )
        if not ok:
            return False, message
        destination = os.path.normpath(_as_text(self._path_edit.text()).strip())
        if not os.path.isabs(destination):
            return False, u"文件路径必须是完整的绝对路径"
        if os.path.basename(destination).lower() != filename.lower():
            return False, u"文件路径末尾必须与文件名称一致：{0}".format(filename)
        return True, {
            u"source": source,
            u"destination": destination,
            u"character": character,
            u"action": action,
        }

    def _create_file(self):
        ok, result = self._validate_create()
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"无法创建", result)
            return
        ok, copied = copy_binding_to_destination(
            result[u"source"], result[u"destination"]
        )
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"创建失败", copied)
            return
        self._open_created_file(copied)

    def _open_created_file(self, copied):
        try:
            import pymxs
            runtime = pymxs.runtime
            runtime.checkForSave()
            runtime.loadMaxFile(copied, quiet=False, useFileUnits=True)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self,
                u"文件已创建，但打开失败",
                u"文件已创建：\n{0}\n\n打开失败：{1}".format(copied, _as_text(exc)),
            )
            return False
        self.accept()
        return True


def show():
    global _WINDOW
    if _WINDOW is not None:
        try:
            if _WINDOW.isVisible():
                _WINDOW._reload_shared_settings(force_path=False)
                _WINDOW.raise_()
                _WINDOW.activateWindow()
                _WINDOW.showNormal()
                return _WINDOW
        except Exception:
            pass
    _WINDOW = NewFileDialog(parent=None)
    _WINDOW.show()
    return _WINDOW

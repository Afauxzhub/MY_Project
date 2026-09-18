# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re

from PySide2 import QtCore, QtWidgets

from anim_migration.service.scan_service import run_readonly_scan
from anim_migration.service.migrate_service import run_canonical_migration, run_canonical_rig_update_workflow
from anim_migration.workflow.backup import list_backups, restore_backup
from anim_migration.workflow.context import detect_file_context
from anim_migration.workflow.max_dialogs import SilentFileDialogs
from anim_migration.workflow.rig_locator import find_source_binding_rig, find_target_in_game_rig, find_target_out_game_rig, is_skin_binding_file
from anim_migration.workflow.rig_update_choices import load_pair_choice, save_pair_choice
from anim_migration.workflow.update_route import ROUTE_ROOT_HIERARCHY, resolve_update_route
from anim_migration.workflow.version_metadata import read_scene_binding_metadata, read_scene_binding_version

UI_VERSION = u"V0.80"


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
        try:
            b = str(value)
            try:
                return b.decode("utf-8")
            except Exception:
                return b.decode("gbk", "replace")
        except Exception:
            return u""


def _normalize_for_mapping(name):
    return re.sub(r"\s+", "", _as_text(name).lower())


class MappingEditorDialog(QtWidgets.QDialog):
    def __init__(self, old_names, new_names, existing_mapping=None, parent=None):
        super(MappingEditorDialog, self).__init__(parent)
        self.setWindowTitle(u"生成对象映射")
        self.resize(900, 650)
        self._old_names = sorted([_as_text(x) for x in old_names if _as_text(x)], key=lambda x: x.lower())
        self._new_names = sorted([_as_text(x) for x in new_names if _as_text(x)], key=lambda x: x.lower())
        self._new_set = set(self._new_names)
        self._existing_mapping = dict(existing_mapping or {})
        self._combos = []
        self._build_ui()
        self._populate()

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(u"只需要处理红/黄行：红色=新绑定中没有同名对象；黄色=工具按忽略空格找到唯一候选。右侧下拉选择新绑定对象后保存。")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        row = QtWidgets.QHBoxLayout()
        self._filter_edit = QtWidgets.QLineEdit()
        self._filter_edit.setPlaceholderText(u"搜索旧对象或新对象")
        self._filter_edit.textChanged.connect(self._apply_filter)
        self._needs_only_check = QtWidgets.QCheckBox(u"只显示需要映射的对象")
        self._needs_only_check.setChecked(True)
        self._needs_only_check.stateChanged.connect(self._apply_filter)
        row.addWidget(self._filter_edit)
        row.addWidget(self._needs_only_check)
        lay.addLayout(row)

        self._table = QtWidgets.QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels([u"旧对象", u"新对象", u"建议", u"状态"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        lay.addWidget(self._table)

        btn_row = QtWidgets.QHBoxLayout()
        auto_btn = QtWidgets.QPushButton(u"应用全部空格建议")
        auto_btn.clicked.connect(self._apply_all_auto_suggestions)
        clear_btn = QtWidgets.QPushButton(u"清空选择")
        clear_btn.clicked.connect(self._clear_selected)
        btn_row.addWidget(auto_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        ok_btn = QtWidgets.QPushButton(u"保存映射")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QtWidgets.QPushButton(u"取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    def _auto_whitespace_suggestion(self, old_name):
        normalized = _normalize_for_mapping(old_name)
        matches = [x for x in self._new_names if _normalize_for_mapping(x) == normalized]
        return matches[0] if len(matches) == 1 else u""

    def _status_for(self, old_name, selected, suggestion):
        if old_name in self._new_set:
            return u"同名存在"
        if selected:
            return u"已映射"
        if suggestion:
            return u"空格差异建议"
        return u"缺少同名"

    def _populate(self):
        self._table.setRowCount(0)
        self._combos = []
        for old_name in self._old_names:
            suggestion = self._auto_whitespace_suggestion(old_name)
            selected = _as_text(self._existing_mapping.get(old_name, ""))
            if not selected and suggestion:
                selected = suggestion
            row = self._table.rowCount()
            self._table.insertRow(row)
            old_item = QtWidgets.QTableWidgetItem(old_name)
            self._table.setItem(row, 0, old_item)

            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            combo.addItem(u"")
            combo.addItems(self._new_names)
            if selected:
                idx = combo.findText(selected)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setEditText(selected)
            combo.currentTextChanged.connect(self._refresh_row_status)
            self._table.setCellWidget(row, 1, combo)
            self._combos.append(combo)

            self._table.setItem(row, 2, QtWidgets.QTableWidgetItem(suggestion))
            self._table.setItem(row, 3, QtWidgets.QTableWidgetItem(self._status_for(old_name, selected, suggestion)))
        self._apply_filter()
        self._table.resizeColumnsToContents()

    def _refresh_row_status(self):
        for row, combo in enumerate(self._combos):
            old_item = self._table.item(row, 0)
            suggestion_item = self._table.item(row, 2)
            status_item = self._table.item(row, 3)
            if old_item and status_item:
                old_name = old_item.text()
                selected = combo.currentText().strip()
                suggestion = suggestion_item.text() if suggestion_item else u""
                status_item.setText(self._status_for(old_name, selected, suggestion))
        self._apply_filter()

    def _row_needs_mapping(self, row):
        old_item = self._table.item(row, 0)
        status_item = self._table.item(row, 3)
        if not old_item or not status_item:
            return False
        return status_item.text() != u"同名存在"

    def _apply_filter(self):
        text = _as_text(self._filter_edit.text()).lower()
        needs_only = self._needs_only_check.isChecked()
        for row, combo in enumerate(self._combos):
            old_item = self._table.item(row, 0)
            suggestion_item = self._table.item(row, 2)
            status_item = self._table.item(row, 3)
            hay = u" ".join([
                old_item.text() if old_item else u"",
                combo.currentText(),
                suggestion_item.text() if suggestion_item else u"",
                status_item.text() if status_item else u"",
            ]).lower()
            hide = bool(text and text not in hay)
            if needs_only and not self._row_needs_mapping(row):
                hide = True
            self._table.setRowHidden(row, hide)

    def _apply_all_auto_suggestions(self):
        for row, combo in enumerate(self._combos):
            suggestion_item = self._table.item(row, 2)
            suggestion = suggestion_item.text() if suggestion_item else u""
            if suggestion:
                idx = combo.findText(suggestion)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setEditText(suggestion)
        self._refresh_row_status()

    def _clear_selected(self):
        for idx in self._table.selectionModel().selectedRows():
            row = idx.row()
            if 0 <= row < len(self._combos):
                self._combos[row].setCurrentIndex(0)
        self._refresh_row_status()

    def mapping(self):
        out = {}
        for row, combo in enumerate(self._combos):
            old_item = self._table.item(row, 0)
            if not old_item:
                continue
            old_name = old_item.text()
            new_name = combo.currentText().strip()
            if new_name and old_name != new_name:
                out[old_name] = new_name
        return out


class BindingDifferenceDialog(QtWidgets.QDialog):
    def __init__(self, layer_contract, saved_choice=None, parent=None):
        super(BindingDifferenceDialog, self).__init__(parent)
        self.setWindowTitle(u"确认绑定版本差异")
        self.resize(1040, 680)
        self._layer_contract = layer_contract or {}
        self._saved_choice = saved_choice or {}
        self._source_items = []
        self._target_items = []
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(
            u"左侧是源绑定存在、目标绑定缺少的对象：勾选=尝试迁移，取消勾选=明确忽略。"
            u"右侧是目标绑定新增对象：更新时保留目标默认状态。Bip 删除项不能忽略。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        if (self._layer_contract.get("binding_difference", {}) or {}).get("scope") == "root_hierarchy":
            scope_hint = QtWidgets.QLabel(
                u"本次走支线（Root 层级）：对比范围是 Root 骨骼下的全部对象，"
                u"不只是六层里的控制器，所以条目会比角色绑定多。"
            )
            scope_hint.setWordWrap(True)
            scope_hint.setStyleSheet(u"color:#7fb3d5;")
            layout.addWidget(scope_hint)

        membership = self._layer_contract.get("membership", {}) or {}
        ambiguous = membership.get("ambiguous", []) or []
        missing = membership.get("missing", []) or []
        self._ignore_duplicates = QtWidgets.QCheckBox(
            u"忽略动画文件中的重名对象（这些重名对象的动画全部不导）"
        )
        self._ignore_duplicates.setChecked(bool(
            self._saved_choice.get("ignore_duplicate_animation_objects", False)
        ))
        self._ignore_duplicates.setVisible(bool(ambiguous))
        layout.addWidget(self._ignore_duplicates)
        if ambiguous:
            duplicate_label = QtWidgets.QLabel(
                u"重名对象：{0}".format(u"、".join([
                    _as_text(row.get("name", "")) or u"<未命名>" for row in ambiguous[:30]
                ]))
            )
            duplicate_label.setWordWrap(True)
            duplicate_label.setStyleSheet(u"color:#e2a85b;")
            layout.addWidget(duplicate_label)
        if missing:
            missing_label = QtWidgets.QLabel(
                u"仍缺失且无法定位：{0}。必须先修复，当前选择不能继续。".format(u"、".join([
                    _as_text(row.get("name", "")) or u"<未命名>" for row in missing[:30]
                ]))
            )
            missing_label.setWordWrap(True)
            missing_label.setStyleSheet(u"color:#ef6b6b;")
            layout.addWidget(missing_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        source_panel, self._source_tree, self._source_items = self._make_difference_panel(
            u"源绑定删除项（左）",
            ((self._layer_contract.get("binding_difference", {}) or {}).get("source_only", []) or []),
            set(self._saved_choice.get("ignored_source_contract_ids", []) or []),
            source_side=True,
        )
        target_panel, self._target_tree, self._target_items = self._make_difference_panel(
            u"目标绑定新增项（右）",
            ((self._layer_contract.get("binding_difference", {}) or {}).get("target_only", []) or []),
            set(self._saved_choice.get("ignored_target_contract_ids", []) or []),
            source_side=False,
        )
        splitter.addWidget(source_panel)
        splitter.addWidget(target_panel)
        splitter.setSizes([520, 520])
        layout.addWidget(splitter, 1)

        buttons = QtWidgets.QDialogButtonBox()
        self._continue_btn = buttons.addButton(u"按当前选择更新", QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton(u"取消", QtWidgets.QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if missing:
            self._continue_btn.setEnabled(False)

    def _make_difference_panel(self, title, rows, ignored_ids, source_side):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        title_label = QtWidgets.QLabel(u"{0}：{1}".format(title, len(rows)))
        title_label.setStyleSheet(u"font-weight:bold;")
        layout.addWidget(title_label)
        tree = QtWidgets.QTreeWidget()
        tree.setColumnCount(3)
        tree.setHeaderLabels([u"迁移", u"层 / 对象", u"父级"])
        items = []
        for row in rows:
            name = _as_text(row.get("name", "")) or u"<未命名>"
            layer = _as_text(row.get("contract_layer", ""))
            item = QtWidgets.QTreeWidgetItem([u"", u"[{0}] {1}".format(layer, name), _as_text(row.get("parent_name", ""))])
            contract_id = _as_text(row.get("contract_id", ""))
            item.setData(0, QtCore.Qt.UserRole, contract_id)
            item.setCheckState(0, QtCore.Qt.Unchecked if contract_id in ignored_ids else QtCore.Qt.Checked)
            if source_side and row.get("is_bip"):
                item.setCheckState(0, QtCore.Qt.Checked)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsUserCheckable)
                item.setToolTip(1, u"Bip 删除项不能忽略")
            tree.addTopLevelItem(item)
            items.append(item)
        tree.resizeColumnToContents(0)
        tree.resizeColumnToContents(1)
        layout.addWidget(tree, 1)
        row_layout = QtWidgets.QHBoxLayout()
        all_btn = QtWidgets.QPushButton(u"全部勾选")
        none_btn = QtWidgets.QPushButton(u"全部忽略")
        all_btn.clicked.connect(lambda: self._set_all(items, True, source_side))
        none_btn.clicked.connect(lambda: self._set_all(items, False, source_side))
        row_layout.addWidget(all_btn)
        row_layout.addWidget(none_btn)
        row_layout.addStretch()
        layout.addLayout(row_layout)
        return panel, tree, items

    def _set_all(self, items, checked, source_side):
        for item in items:
            if source_side and not bool(item.flags() & QtCore.Qt.ItemIsUserCheckable):
                continue
            item.setCheckState(0, QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)

    def _ignored_ids(self, items):
        return [
            _as_text(item.data(0, QtCore.Qt.UserRole))
            for item in items if item.checkState(0) != QtCore.Qt.Checked
        ]

    def choice(self):
        difference = self._layer_contract.get("binding_difference", {}) or {}
        return {
            "binding_difference_signature": _as_text(difference.get("signature", "")),
            "ignore_duplicate_animation_objects": bool(self._ignore_duplicates.isChecked()),
            "ignored_source_contract_ids": self._ignored_ids(self._source_items),
            "ignored_target_contract_ids": self._ignored_ids(self._target_items),
        }


class PathCombo(QtWidgets.QComboBox):
    def __init__(self, parent=None):
        super(PathCombo, self).__init__(parent)
        self.setEditable(False)
        self.setMinimumWidth(270)
        self.setMaximumWidth(360)

    def _display_name(self, path):
        text = _as_text(path)
        return os.path.basename(text) if text else u""

    def setPath(self, path):
        path = _as_text(path)
        self.clear()
        if path:
            self.addItem(self._display_name(path), path)
            self.setCurrentIndex(0)

    def setDisplayPath(self, display, path):
        path = _as_text(path)
        self.clear()
        if path:
            self.addItem(_as_text(display) or self._display_name(path), path)
            self.setCurrentIndex(0)

    def addPath(self, path):
        path = _as_text(path)
        if not path:
            return
        for i in range(self.count()):
            if _as_text(self.itemData(i)) == path:
                return
        self.addItem(self._display_name(path), path)

    def path(self):
        data = self.currentData()
        return _as_text(data) if data else u""

    def text(self):
        return self.path()

    def setText(self, path):
        self.setPath(path)


class BindingCollapsibleGroup(QtWidgets.QWidget):
    def __init__(self, title, parent=None, expanded=False):
        super(BindingCollapsibleGroup, self).__init__(parent)
        self.setObjectName(u"rmGroup")
        self._title = _as_text(title)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(0)
        self._toggle = QtWidgets.QPushButton((u"▼  " if expanded else u"▶  ") + self._title, self)
        self._toggle.setObjectName(u"rmGroupToggle")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._body = QtWidgets.QWidget(self)
        self._body.setObjectName(u"rmGroupBody")
        self._body.setVisible(expanded)
        layout.addWidget(self._toggle)
        layout.addWidget(self._body)
        self._toggle.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked):
        self._body.setVisible(checked)
        self._toggle.setText((u"▼  " if checked else u"▶  ") + self._title)

    def body_widget(self):
        return self._body


class BindingUpdateTab(QtWidgets.QWidget):
    def __init__(self, parent=None, rt=None):
        super(BindingUpdateTab, self).__init__(parent)
        self._rt = rt
        self._config = {}
        self._last_report = None
        self._last_migrate_report = None
        self._context = {}
        self._rig_lookup = {}
        self._max_names_cache = {}
        self._rig_lookup_cache = {}
        self._current_binding_version_override = u""
        self._last_anim_path = u""
        self._source_rig_manual = False
        self._migration_progress_dialog = None
        self._viewport_redraw_suspended = False
        self._build_ui()
        self.refresh_current_anim_path()

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(10)

        self._old_anim_edit = PathCombo()
        self._source_rig_edit = PathCombo()
        self._new_rig_edit = PathCombo()
        self._new_rig_edit.currentIndexChanged.connect(self._on_target_rig_changed)
        # Retained as a non-UI compatibility value for the legacy manual-output
        # method.  Production binding updates always back up and overwrite the
        # current animation, so this is no longer exposed as a setting.
        self._output_edit = QtWidgets.QLineEdit()
        self._status_label = QtWidgets.QLabel(u"状态: 未检查")
        self._status_light = QtWidgets.QLabel(u"●")
        self._status_light.setStyleSheet(u"color:#777;font-size:20px;")
        self._context_label = QtWidgets.QLabel(u"文件识别：-")
        self._context_label.setWordWrap(True)
        self._context_label.setStyleSheet(u"color:#aeb8c8;")

        status_row = QtWidgets.QHBoxLayout()
        status_row.addWidget(self._context_label, 1)
        status_row.addStretch()
        status_row.addWidget(self._status_label)
        status_row.addWidget(self._status_light)
        lay.addLayout(status_row)

        self._settings_group = BindingCollapsibleGroup(u"绑定更新设定", parent=self, expanded=False)
        settings_body_lay = QtWidgets.QVBoxLayout(self._settings_group.body_widget())
        settings_body_lay.setContentsMargins(10, 8, 10, 10)
        settings_body_lay.setSpacing(8)

        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        form.addRow(u"当前绑定版本", self._old_anim_edit)
        form.addRow(u"源绑定参考", self._source_rig_edit)
        form.addRow(u"目标绑定版本", self._new_rig_edit)
        settings_body_lay.addLayout(form)
        btn_row = QtWidgets.QHBoxLayout()
        self._source_rig_btn = QtWidgets.QPushButton(u"选择源绑定参考")
        self._source_rig_btn.clicked.connect(self._pick_source_rig)
        self._target_rig_btn = QtWidgets.QPushButton(u"选择目标绑定")
        self._target_rig_btn.clicked.connect(self._show_target_rig_dropdown)
        self._open_migrate_report_btn = QtWidgets.QPushButton(u"打开迁移报告")
        self._open_migrate_report_btn.clicked.connect(self._open_migrate_report)
        btn_row.addWidget(self._source_rig_btn)
        btn_row.addWidget(self._target_rig_btn)
        btn_row.addWidget(self._open_migrate_report_btn)
        btn_row.addStretch()
        settings_body_lay.addLayout(btn_row)
        lay.addWidget(self._settings_group)

        self._outgame_group = QtWidgets.QGroupBox(u"局外多角色更新")
        outgame_lay = QtWidgets.QVBoxLayout(self._outgame_group)
        outgame_lay.addWidget(QtWidgets.QLabel(u"局外文件请手动选择角色绑定后更新；迁移范围按 _Root / _Ctrl 向下处理。"))
        self._outgame_char_combo = QtWidgets.QComboBox()
        self._outgame_char_combo.setEditable(True)
        self._outgame_char_combo.currentIndexChanged.connect(self._on_outgame_character_changed)
        if self._outgame_char_combo.lineEdit() is not None:
            self._outgame_char_combo.lineEdit().editingFinished.connect(self._on_outgame_character_changed)
        outgame_lay.addWidget(self._outgame_char_combo)
        lay.addWidget(self._outgame_group)
        self._migrate_btn = QtWidgets.QPushButton(u"更新动画（结果迁移）")
        self._migrate_btn.clicked.connect(self._run_migration)
        self._migrate_btn.setMinimumHeight(48)
        self._migrate_btn.setStyleSheet(
            u"QPushButton { background:#b94141; color:white; font-size:15px; font-weight:bold; border-radius:5px; padding:10px 22px; }"
            u"QPushButton:hover { background:#cf4d4d; }"
            u"QPushButton:disabled { background:#6b3a3a; color:#aaa; }"
        )
        self._rollback_btn = QtWidgets.QPushButton(u"回滚备份")
        self._rollback_btn.clicked.connect(self._rollback_backup)
        self._rollback_btn.setMinimumHeight(42)
        self._rollback_btn.setStyleSheet(
            u"QPushButton { background:#2d4a6a; color:white; font-size:13px; font-weight:bold; border-radius:5px; padding:8px 22px; }"
            u"QPushButton:hover { background:#3d5a8a; }"
            u"QPushButton:disabled { background:#303845; color:#888; }"
        )
        lay.addWidget(self._migrate_btn)
        lay.addWidget(self._rollback_btn)
        lay.addStretch()

    def _row_widget(self, row_layout):
        w = QtWidgets.QWidget()
        w.setLayout(row_layout)
        return w

    def _version_num(self, text):
        m = re.search(r"(\d+)", _as_text(text))
        return int(m.group(1)) if m else 1

    def _version_from_rig_path(self, path):
        m = re.search(r"(?i)(?:^|_)v(\d{1,3})(?=\.max$|_)", os.path.basename(_as_text(path)))
        return u"v{0:02d}".format(int(m.group(1))) if m else u""

    def _target_rig_mode(self):
        return "in_game" if self._context.get("is_in_game") else "out_game"

    def _selected_character(self):
        if self._context.get("is_in_game"):
            return _as_text(self._context.get("character", u""))
        if hasattr(self, "_outgame_char_combo"):
            return _as_text(self._outgame_char_combo.currentText()).strip()
        return u""

    def _is_valid_target_rig_file(self, path):
        mode = self._target_rig_mode()
        character = self._selected_character()
        return is_skin_binding_file(path, mode=mode, character=character)

    def _target_rig_rule_text(self):
        if self._context.get("is_in_game"):
            return u"局内目标绑定文件名必须为 角色类型_角色名_lod_skin_版本，例如 Role_Hero_lod_skin_V01.max。"
        return u"局外目标绑定文件名必须为 角色类型_角色名_cs_skin_版本，例如 Role_Hero_cs_skin_V01.max。"

    def _target_rig_dir(self):
        new_rig = self._new_rig_edit.text().strip()
        if new_rig:
            return os.path.dirname(new_rig)
        if self._rig_lookup.get("path"):
            return os.path.dirname(_as_text(self._rig_lookup.get("path")))
        return self._get_rig_bindings_root()

    def _rig_files_in_target_dir(self):
        folder = self._target_rig_dir()
        try:
            if not folder or not os.path.isdir(folder):
                return []
            mode = self._target_rig_mode()
            candidates = self._rig_lookup.get("candidates") or []
            if candidates:
                return [_as_text(x.get("path", u"")) for x in candidates if _as_text(x.get("path", u""))]
            character = self._selected_character()
            files = [
                os.path.join(folder, x)
                for x in os.listdir(folder)
                if is_skin_binding_file(x, mode=mode, character=character)
            ]
            files.sort(key=lambda p: self._version_num(self._version_from_rig_path(p)), reverse=True)
            return files
        except Exception:
            return []

    def _current_binding_display_path(self):
        current_version = self._current_binding_version()
        rig_dir = self._target_rig_dir()
        if rig_dir and current_version:
            for path in self._rig_files_in_target_dir():
                if self._version_from_rig_path(path).lower() == current_version.lower():
                    return path
        return current_version

    def _current_binding_version(self):
        if self._current_binding_version_override:
            return self._current_binding_version_override
        scene_version = self._scene_binding_version()
        if scene_version:
            return scene_version
        return self._context.get("old_version", u"v01")

    def _scene_binding_version(self):
        try:
            if self._rt is None:
                import pymxs
                self._rt = pymxs.runtime
            return read_scene_binding_version(self._rt)
        except Exception:
            return u""

    def _set_current_binding_field(self, old_anim):
        display_path = self._current_binding_display_path()
        display = os.path.basename(display_path) if display_path else self._current_binding_version()
        self._old_anim_edit.setDisplayPath(display, old_anim)

    def _scene_binding_metadata(self):
        try:
            if self._rt is None:
                import pymxs
                self._rt = pymxs.runtime
            return read_scene_binding_metadata(self._rt)
        except Exception:
            return {"version": u"", "rig_path": u""}

    def _refresh_source_rig_reference(self):
        current = self._source_rig_edit.text().strip()
        if self._source_rig_manual and current and os.path.exists(current):
            return
        old_anim = self._old_anim_edit.text().strip()
        metadata = self._scene_binding_metadata()
        metadata_path = _as_text(metadata.get("rig_path", u"")).strip()
        if metadata_path and os.path.exists(metadata_path):
            if not old_anim or os.path.normcase(os.path.abspath(metadata_path)) != os.path.normcase(os.path.abspath(old_anim)):
                self._source_rig_edit.setText(metadata_path)
                return
        lookup = find_source_binding_rig(
            self._selected_character(),
            metadata.get("version") or self._current_binding_version(),
            mode=self._target_rig_mode(),
            character_rig_root=(self._config or {}).get(u"character_rig_root") or None,
            target_rig_path=self._new_rig_edit.text().strip() or None,
        )
        self._source_rig_edit.setText(lookup.get("path", u"") if lookup.get("ok") else u"")

    def _current_route(self):
        return resolve_update_route(
            target_rig_path=self._new_rig_edit.text().strip(),
            source_rig_path=self._source_rig_edit.text().strip(),
            animation_path=self._old_anim_edit.text().strip(),
        )

    def _refresh_context_label(self):
        if self._context.get("is_skin_binding"):
            self._context_label.setText(u"当前文件是绑定文件，已跳过动画自动更新。")
            return
        route = self._current_route()
        route_text = u" / 迁移路线 {0}".format(_as_text(route.get("label", u"")))
        if self._context.get("is_in_game"):
            self._context_label.setText(
                u"局内 {0} / 角色 {1} / 当前绑定 {2} / 目标绑定 {3}{4}".format(
                    self._context.get("type", u""),
                    self._context.get("character", u""),
                    self._current_binding_version(),
                    self._version_from_rig_path(self._new_rig_edit.text().strip()) or self._rig_lookup.get("version", u"未找到"),
                    route_text,
                )
            )
        else:
            character = self._selected_character() or u"未识别"
            self._context_label.setText(
                u"局外 / 角色 {0} / 当前绑定 {1} / 目标绑定 {2}{3}".format(
                    character,
                    self._current_binding_version(),
                    self._version_from_rig_path(self._new_rig_edit.text().strip()) or self._rig_lookup.get("version", u"未找到"),
                    route_text,
                )
            )

    def refresh_current_anim_path(self):
        try:
            if self._rt is None:
                import pymxs

                self._rt = pymxs.runtime
            file_path = _as_text(self._rt.maxFilePath)
            file_name = _as_text(self._rt.maxFileName)
            full = file_path + file_name
            if (not full) and file_name:
                full = os.path.abspath(file_name)
            if full:
                if self._last_anim_path and os.path.abspath(full) != os.path.abspath(self._last_anim_path):
                    self._current_binding_version_override = u""
                    self._source_rig_manual = False
                    self._source_rig_edit.setText(u"")
                self._last_anim_path = full
                if not self._output_edit.text().strip():
                    self._output_edit.setText(self._default_output_for(full))
                self._refresh_context(full)
                self._set_current_binding_field(full)
                self._refresh_source_rig_reference()
            else:
                self._old_anim_edit.setText(u"")
        except Exception:
            pass

    def _refresh_context(self, old_anim=None):
        old_anim = old_anim or self._old_anim_edit.text().strip()
        self._context = detect_file_context(old_anim)
        cfg = self._config or {}
        char_root = cfg.get(u"character_rig_root", u"")
        self._rig_lookup = {}
        if self._context.get("is_in_game"):
            current_version = self._current_binding_version()
            lookup_key = (
                self._context.get("character", u""),
                current_version,
                char_root or u"",
            )
            if lookup_key in self._rig_lookup_cache:
                self._rig_lookup = self._rig_lookup_cache.get(lookup_key) or {}
            else:
                self._rig_lookup = find_target_in_game_rig(
                    self._context.get("character", u""),
                    current_version,
                    character_rig_root=char_root or None,
                )
                self._rig_lookup_cache[lookup_key] = dict(self._rig_lookup)
            if self._rig_lookup.get("ok"):
                self._new_rig_edit.setText(self._rig_lookup.get("path", u""))
            self._refresh_source_rig_reference()
            self._refresh_context_label()
            self._outgame_group.setVisible(False)
        else:
            self._outgame_group.setVisible(True)
            self._populate_outgame_characters()
            self._refresh_outgame_rig_lookup()
            self._refresh_context_label()

    def _populate_outgame_characters(self):
        current = self._outgame_char_combo.currentText() if hasattr(self, "_outgame_char_combo") else u""
        self._outgame_char_combo.blockSignals(True)
        self._outgame_char_combo.clear()
        chars = []
        for item in self._scene_outgame_characters():
            if item not in chars:
                chars.append(item)
        for item in self._config.get(u"rig_update_outgame_characters", []) or []:
            item = _as_text(item)
            if item and item not in chars:
                chars.append(item)
        for item in chars:
            self._outgame_char_combo.addItem(_as_text(item))
        if current:
            self._outgame_char_combo.setEditText(current)
        elif chars:
            self._outgame_char_combo.setCurrentIndex(0)
        self._outgame_char_combo.blockSignals(False)

    def _scene_outgame_characters(self):
        chars = set()
        try:
            if self._rt is None:
                import pymxs
                self._rt = pymxs.runtime
            for node in list(self._rt.objects):
                name = _as_text(getattr(node, "name", u""))
                m = re.match(r"(?i)^(.+?)_(?:root|ctrl)$", name)
                if m:
                    chars.add(m.group(1))
        except Exception:
            pass
        return sorted(chars, key=lambda x: x.lower())

    def _on_outgame_character_changed(self, *args):
        if self._context.get("is_in_game"):
            return
        self._refresh_outgame_rig_lookup()
        self._refresh_context_label()
        old_anim = self._old_anim_edit.text().strip()
        if old_anim:
            self._set_current_binding_field(old_anim)

    def _refresh_outgame_rig_lookup(self):
        character = self._selected_character()
        self._rig_lookup = {}
        if not character:
            self._new_rig_edit.setText(u"")
            return
        current_version = self._current_binding_version()
        lookup = find_target_out_game_rig(
            character,
            current_version,
            character_rig_root=(self._config or {}).get(u"character_rig_root") or None,
        )
        self._rig_lookup = dict(lookup or {})
        if self._rig_lookup.get("ok"):
            self._new_rig_edit.setText(self._rig_lookup.get("path", u""))
            self._refresh_source_rig_reference()
        else:
            self._new_rig_edit.setText(u"")

    def _get_rig_bindings_root(self):
        default = u""
        try:
            cfg = self._config or {}
            if not cfg:
                parent = self.parent()
                if parent is not None and hasattr(parent, "_config"):
                    cfg = getattr(parent, "_config") or {}
            return cfg.get(u"character_rig_root", cfg.get(u"rig_bindings_root", default)) or default
        except Exception:
            return default

    def on_config_updated(self, config):
        self._config = dict(config or {})
        self._rig_lookup_cache = {}
        self._refresh_context()

    def _on_target_rig_changed(self, *args):
        rig_path = self._new_rig_edit.text().strip()
        if not rig_path:
            return
        version = self._version_from_rig_path(rig_path)
        if version:
            self._rig_lookup["version"] = version
            self._rig_lookup["path"] = rig_path
        self._refresh_source_rig_reference()
        self._refresh_context_label()
        old_anim = self._old_anim_edit.text().strip()
        if old_anim:
            self._set_current_binding_field(old_anim)

    def _show_target_rig_dropdown(self):
        current = self._new_rig_edit.text().strip()
        files = self._rig_files_in_target_dir()
        if not files:
            self._pick_new_rig()
            return
        self._new_rig_edit.blockSignals(True)
        self._new_rig_edit.clear()
        for path in files:
            self._new_rig_edit.addPath(path)
        if current:
            for i in range(self._new_rig_edit.count()):
                if _as_text(self._new_rig_edit.itemData(i)) == current:
                    self._new_rig_edit.setCurrentIndex(i)
                    break
        self._new_rig_edit.blockSignals(False)
        self._new_rig_edit.showPopup()

    def _pick_new_rig(self):
        start_dir = self._get_rig_bindings_root()
        if self._new_rig_edit.text().strip():
            start_dir = os.path.dirname(self._new_rig_edit.text().strip())
        p, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            u"选择目标绑定文件",
            start_dir,
            u"Max Files (*.max);;All Files (*)",
        )
        if p:
            if not self._is_valid_target_rig_file(p):
                QtWidgets.QMessageBox.warning(self, u"绑定文件不符合规则", self._target_rig_rule_text())
                return
            self._new_rig_edit.setText(p)

    def _pick_source_rig(self):
        start = self._source_rig_edit.text().strip()
        start_dir = os.path.dirname(start) if start else self._target_rig_dir()
        p, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, u"选择源绑定参考文件", start_dir,
            u"Max Files (*.max);;All Files (*)",
        )
        if p:
            old_anim = self._old_anim_edit.text().strip()
            if old_anim and os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath(old_anim)):
                QtWidgets.QMessageBox.warning(self, u"源绑定参考无效", u"源绑定参考必须是中性 Skin 绑定，不能选择当前动画文件。")
                return
            self._source_rig_manual = True
            self._source_rig_edit.setText(p)

    def _max_file_object_names(self, path):
        try:
            cache_key = (os.path.abspath(path), os.path.getmtime(path) if os.path.exists(path) else 0)
            if cache_key in self._max_names_cache:
                return list(self._max_names_cache.get(cache_key) or [])
            if self._rt is None:
                import pymxs
                self._rt = pymxs.runtime
            with SilentFileDialogs(self._rt):
                raw = self._rt.getMAXFileObjectNames(path)
            names = []
            try:
                count = int(raw.count)
                for i in range(1, count + 1):
                    try:
                        names.append(_as_text(raw[i]))
                    except Exception:
                        names.append(_as_text(raw[i - 1]))
            except Exception:
                names = [_as_text(x) for x in raw]
            names = [x for x in names if x]
            self._max_names_cache[cache_key] = list(names)
            return names
        except Exception as e:
            raise RuntimeError(_as_text(e))

    def _pick_output(self):
        start = self._output_edit.text().strip()
        old_anim = self._old_anim_edit.text().strip()
        if not start and old_anim:
            start = self._default_output_for(old_anim)
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, u"选择迁移输出文件", start, u"Max Files (*.max);;All Files (*)")
        if p:
            self._output_edit.setText(p)

    def _default_output_for(self, old_anim):
        try:
            import re
            stem, _ = os.path.splitext(old_anim)
            base_stem = re.sub(r"_RigUpdate_v\d{3}$", "", stem, flags=re.IGNORECASE)
            cand = base_stem + u"_RigUpdate_v001.max"
            if not os.path.exists(cand):
                return cand
            for i in range(2, 1000):
                c2 = base_stem + u"_RigUpdate_v{0:03d}.max".format(i)
                if not os.path.exists(c2):
                    return c2
            return base_stem + u"_RigUpdate.max"
        except Exception:
            return u""

    def _set_status(self, light, msg):
        color = {"red": "#d9534f", "yellow": "#f0ad4e", "green": "#5cb85c"}.get(light, "#777")
        self._status_light.setStyleSheet(u"color:{0};font-size:20px;".format(color))
        self._status_label.setText(u"状态: {0}".format(msg))

    def _set_migration_progress(self, value, message):
        value = max(0, min(100, int(value)))
        if self._migration_progress_dialog is None:
            dialog = QtWidgets.QProgressDialog(self.window())
            dialog.setWindowTitle(u"绑定更新")
            dialog.setWindowModality(QtCore.Qt.WindowModal)
            dialog.setCancelButton(None)
            dialog.setRange(0, 100)
            dialog.setMinimumDuration(0)
            dialog.setAutoClose(False)
            dialog.setAutoReset(False)
            dialog.setMinimumWidth(460)
            self._migration_progress_dialog = dialog
            dialog.show()
        self._migration_progress_dialog.setLabelText(_as_text(message))
        self._migration_progress_dialog.setValue(value)
        self._set_status("green" if value >= 100 else "yellow", _as_text(message))
        QtWidgets.QApplication.processEvents()

    def _close_migration_progress(self):
        dialog = self._migration_progress_dialog
        self._migration_progress_dialog = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
            QtWidgets.QApplication.processEvents()

    def _suspend_viewport_redraw(self):
        self._viewport_redraw_suspended = False
        try:
            if self._rt is None:
                import pymxs
                self._rt = pymxs.runtime
            self._rt.disableSceneRedraw()
            self._viewport_redraw_suspended = True
        except Exception:
            pass

    def _resume_viewport_redraw(self):
        if not self._viewport_redraw_suspended:
            return
        self._viewport_redraw_suspended = False
        try:
            self._rt.enableSceneRedraw()
            self._rt.redrawViews()
        except Exception:
            pass

    def _show_reportable_error(self, title, message, error=None,
                               context=None, attachments=None):
        from ui.op_error_report_dialog import show_reportable_error

        # Keep the upload/close buttons unobstructed by the migration progress
        # window.  The shared error dialog writes locally first and uploads only
        # when the animator explicitly clicks “上传报错”.
        self._close_migration_progress()
        self._resume_viewport_redraw()

        report_paths = []
        if isinstance(self._last_report, dict):
            for key in ("report_txt_path", "report_json_path"):
                value = _as_text(self._last_report.get(key, u""))
                if value:
                    report_paths.append(value)
        last_migrate = _as_text(self._last_migrate_report)
        if last_migrate:
            report_paths.append(last_migrate)
            base, ext = os.path.splitext(last_migrate)
            json_path = base + u".json" if ext.lower() == u".txt" else u""
            if json_path and os.path.exists(json_path):
                report_paths.append(json_path)
        for path in attachments or []:
            if path:
                report_paths.append(path)
        unique_report_paths = []
        seen_report_paths = set()
        for path in report_paths:
            normalized = os.path.normcase(os.path.abspath(_as_text(path)))
            if normalized in seen_report_paths:
                continue
            seen_report_paths.add(normalized)
            unique_report_paths.append(path)

        binding_context = {
            u"operation": u"binding-update",
            u"animation_file": self._old_anim_edit.text().strip(),
            u"source_binding": self._source_rig_edit.text().strip(),
            u"target_binding": self._new_rig_edit.text().strip(),
        }
        binding_context.update(context or {})
        return show_reportable_error(
            parent=self,
            title=title,
            message=message,
            tool_id=u"binding-update",
            tool_name=u"Animation 绑定更新工具",
            config=self._config,
            exception=error,
            context=binding_context,
            attachments=unique_report_paths,
            tool_version=UI_VERSION,
        )

    def _run_scan(self):
        self.refresh_current_anim_path()
        old_anim = self._old_anim_edit.text().strip()
        new_rig = self._new_rig_edit.text().strip()
        if not old_anim or (not os.path.exists(old_anim)):
            QtWidgets.QMessageBox.warning(self, u"错误", u"当前动画文件路径无效")
            return
        if not new_rig or (not os.path.exists(new_rig)):
            QtWidgets.QMessageBox.warning(self, u"错误", u"目标绑定文件路径无效")
            return
        try:
            report = run_readonly_scan(old_anim, new_rig, mapping_path=None)
        except Exception as e:
            self._show_reportable_error(
                u"检查失败",
                _as_text(e),
                error=e,
                context={u"phase": u"readonly-scan"},
            )
            self._set_status("red", u"检查失败")
            return
        self._last_report = report
        light = report.get("summary", {}).get("status_light", "red")
        self._set_status(light, u"完成：E{0} W{1} I{2}".format(report["summary"]["error_count"], report["summary"]["warning_count"], report["summary"]["info_count"]))
        QtWidgets.QMessageBox.information(self, u"检查完成", u"报告已生成:\n{0}".format(report.get("report_txt_path", "")))

    def _open_report(self):
        if not self._last_report:
            QtWidgets.QMessageBox.information(self, u"提示", u"还没有可打开的检查报告，请先执行“检查”。")
            return
        path = self._last_report.get("report_txt_path") or self._last_report.get("report_json_path")
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            QtWidgets.QMessageBox.information(self, u"提示", u"报告文件不存在，请先重新执行“检查”。")

    def _open_migrate_report(self):
        if self._last_migrate_report and os.path.exists(self._last_migrate_report):
            os.startfile(self._last_migrate_report)
        else:
            QtWidgets.QMessageBox.information(self, u"提示", u"还没有可打开的迁移报告，请先执行“执行迁移(BIP+约束+已有对象动画)”。")

    def _as_kv_dict(self, ms_kv):
        out = {}
        if ms_kv is None:
            return out

        def _normalize_key(k):
            t = _as_text(k).strip()
            if t.startswith("#"):
                t = t[1:]
            if t.startswith("name:"):
                t = t[5:]
            return t

        try:
            count = int(ms_kv.count)
        except Exception:
            try:
                count = len(ms_kv)
            except Exception:
                count = 0

        i = 1
        while i <= count - 1:
            try:
                key = _normalize_key(ms_kv[i])
                out[key] = ms_kv[i + 1]
            except Exception:
                # fallback for python-style index collections
                try:
                    key = _normalize_key(ms_kv[i - 1])
                    out[key] = ms_kv[i]
                except Exception:
                    pass
            i += 2
        return out

    def _as_bool(self, value):
        if isinstance(value, bool):
            return value
        txt = _as_text(value).strip().lower()
        return txt in ("true", "1", "yes", "ok")

    def _safe_count(self, value):
        if value is None:
            return 0
        try:
            return int(value.count)
        except Exception:
            pass
        try:
            return int(len(value))
        except Exception:
            pass
        try:
            c = getattr(value, "count", None)
            if callable(c):
                return int(c())
        except Exception:
            pass
        return 0

    def _find_latest_migrate_report(self, old_anim):
        try:
            report_root = os.path.join(os.path.dirname(old_anim), "_RigUpdateReports")
            if not os.path.isdir(report_root):
                return u""
            txts = []
            for name in os.listdir(report_root):
                low = name.lower()
                if low.endswith(".txt") and ".migration_" in low:
                    txts.append(os.path.join(report_root, name))
            if not txts:
                return u""
            txts.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return txts[0]
        except Exception:
            return u""

    def _prompt_binding_difference_review(self, data, saved_choice=None):
        manifest = data.get("package_manifest", {}) or {}
        layer_contract = manifest.get("layer_contract", {}) or {}
        dialog = BindingDifferenceDialog(layer_contract, saved_choice=saved_choice, parent=self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return None
        return dialog.choice()

    def _prompt_layer_membership_drift(self, data):
        manifest = data.get("package_manifest", {}) or {}
        layer_contract = manifest.get("layer_contract", {}) or {}
        membership = layer_contract.get("membership", {}) or {}
        summary = membership.get("summary", {}) or {}
        recoverable = bool(membership.get("recoverable", False))
        detail_lines = [
            u"源绑定预期对象: {0}".format(summary.get("expected_count", 0)),
            u"成功定位对象: {0}".format(summary.get("resolved_count", 0)),
            u"移层对象: {0}".format(summary.get("moved_count", 0)),
            u"缺失对象: {0}".format(summary.get("missing_count", 0)),
            u"歧义对象: {0}".format(summary.get("ambiguous_count", 0)),
            u"误入六层对象: {0}".format(summary.get("extra_count", 0)),
            u"",
        ]
        for title, key in (
            (u"移层", "moved"), (u"缺失", "missing"),
            (u"歧义", "ambiguous"), (u"额外", "extras"),
        ):
            rows = membership.get(key, []) or []
            if not rows:
                continue
            detail_lines.append(u"[{0}]".format(title))
            for row in rows[:30]:
                detail_lines.append(u"- {0} | 绑定层={1} | 动画层={2}".format(
                    _as_text(row.get("name", "")),
                    _as_text(row.get("expected_layer", "")),
                    _as_text(row.get("animation_layer", "")),
                ))
        while True:
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle(u"检测到迁移层被修改")
            box.setIcon(QtWidgets.QMessageBox.Warning)
            if recoverable:
                box.setText(u"动画文件的六层成员与对应版本源绑定不一致，但所有绑定成员仍能唯一定位。")
                box.setInformativeText(u"建议取消并修复层；也可以按源绑定层清单继续，动画文件当前层归属将被忽略。")
            else:
                box.setText(u"动画文件的六层成员与对应版本源绑定不一致，并包含缺失或歧义对象。")
                box.setInformativeText(u"当前差异无法安全保底，请取消并修复动画文件或重新选择正确的源绑定。")
            box.setDetailedText(u"\n".join(detail_lines))
            fix_btn = box.addButton(u"取消并修复", QtWidgets.QMessageBox.RejectRole)
            fallback_btn = box.addButton(u"按源绑定清单继续（保底）", QtWidgets.QMessageBox.AcceptRole)
            report_btn = box.addButton(u"打开差异报告", QtWidgets.QMessageBox.ActionRole)
            fallback_btn.setEnabled(recoverable)
            box.setDefaultButton(fix_btn)
            box.exec_()
            clicked = box.clickedButton()
            if clicked == report_btn:
                self._open_migrate_report()
                continue
            return clicked == fallback_btn and recoverable

    def _tool_root(self):
        # RootMotionTool/anim_migration/ui -> RootMotionTool -> Animation Tools
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    def _load_migrate_service(self):
        try:
            import pymxs

            rt = pymxs.runtime
            core = os.path.join(self._tool_root(), "maxscript", "ReferenceRigCore.ms")
            if not os.path.exists(core):
                raise RuntimeError(u"未找到迁移核心脚本: {0}".format(core))
            rt.fileIn(core)
            if not hasattr(rt, "RR_MigrateService"):
                raise RuntimeError(u"迁移服务未加载: RR_MigrateService")
            return rt
        except Exception as e:
            raise RuntimeError(_as_text(e))

    def _run_manual_output_migration(self):
        self.refresh_current_anim_path()
        old_anim = self._old_anim_edit.text().strip()
        source_rig = self._source_rig_edit.text().strip()
        new_rig = self._new_rig_edit.text().strip()
        output = self._output_edit.text().strip()
        if not old_anim or (not os.path.exists(old_anim)):
            QtWidgets.QMessageBox.warning(self, u"错误", u"当前动画文件路径无效")
            return
        if not new_rig or (not os.path.exists(new_rig)):
            QtWidgets.QMessageBox.warning(self, u"错误", u"目标绑定文件路径无效")
            return
        if not output:
            output = self._default_output_for(old_anim)
            self._output_edit.setText(output)

        self._set_status("yellow", u"迁移处理中...")
        self._migrate_btn.setEnabled(False)
        try:
            data = run_canonical_migration(
                old_anim_path=old_anim,
                new_rig_path=new_rig,
                output_max_path=output,
                source_rig_path=source_rig or None,
                overwrite=False,
            )
            ok = bool(data.get("ok", False))
            report_txt = _as_text(data.get("report_txt", u"") or data.get("report_txt_path", u""))
            if (not report_txt) or (not os.path.exists(report_txt)):
                report_txt = self._find_latest_migrate_report(old_anim)
            self._last_migrate_report = report_txt
            self._open_migrate_report_btn.setEnabled(bool(report_txt and os.path.exists(report_txt)))

            if ok:
                phase4 = data.get("phase4_constraints", {}) or {}
                phase5 = data.get("phase5_non_bip_animation", {}) or {}
                package_manifest = data.get("package_manifest", {}) or {}
                package_warnings = package_manifest.get("warnings", []) or []
                ignored_preflight = len(package_manifest.get("continued_blockers", []) or [])
                warn_count = len(phase4.get("warnings", []) or []) + len(phase5.get("warnings", []) or []) + len(package_warnings) + ignored_preflight
                self._set_status("yellow" if warn_count > 0 else "green", u"迁移成功 W{0}".format(warn_count))
                QtWidgets.QMessageBox.information(
                    self,
                    u"迁移完成",
                    u"输出文件:\n{0}\n\n迁移包:\n{1}\n\n报告:\n{2}".format(
                        _as_text(data.get("output_max_path", output)),
                        _as_text(data.get("package_dir", u"")),
                        report_txt,
                    ),
                )
            else:
                self._set_status("red", u"迁移失败/阻断")
                msg = _as_text(data.get("message", u""))
                if not msg:
                    msg = u"迁移失败（未返回详细信息）。\n请查看迁移报告；若有新输出文件，通常表示主流程成功但返回解析异常。"
                self._show_reportable_error(
                    u"迁移失败",
                    msg,
                    context={
                        u"phase": u"manual-output-migration",
                        u"error_code": data.get("error_code", u""),
                    },
                    attachments=[report_txt],
                )
        except Exception as e:
            self._set_status("red", u"迁移失败")
            self._show_reportable_error(
                u"迁移失败",
                _as_text(e),
                error=e,
                context={u"phase": u"manual-output-migration"},
            )
        finally:
            self._migrate_btn.setEnabled(True)

    def _run_migration(self):
        self.refresh_current_anim_path()
        old_anim = self._old_anim_edit.text().strip()
        source_rig = self._source_rig_edit.text().strip()
        new_rig = self._new_rig_edit.text().strip()
        if not old_anim or (not os.path.exists(old_anim)):
            QtWidgets.QMessageBox.warning(self, u"错误", u"当前动画文件路径无效")
            return
        if not new_rig or (not os.path.exists(new_rig)):
            QtWidgets.QMessageBox.warning(self, u"错误", u"目标绑定文件路径无效")
            return
        route = self._current_route()
        root_route = _as_text(route.get("route")) == ROUTE_ROOT_HIERARCHY
        if not source_rig or (not os.path.exists(source_rig)):
            QtWidgets.QMessageBox.warning(
                self, u"缺少源绑定参考",
                u"未找到当前动画版本对应的中性 Skin 绑定。请点击“选择源绑定参考”，"
                + (
                    u"用于三方约束比对和绑定版本差异确认。" if root_route
                    else u"用于识别当前动画应迁移的六层对象。"
                ),
            )
            return
        if not self._is_valid_target_rig_file(new_rig):
            QtWidgets.QMessageBox.warning(self, u"绑定文件不符合规则", self._target_rig_rule_text())
            return
        msg = u"将使用目标绑定更新当前动画，并在覆盖前自动备份。\n\n迁移路线:\n{0}（{1}）\n\n当前文件:\n{2}\n\n源绑定参考:\n{3}\n\n目标绑定:\n{4}\n\n是否继续？".format(
            _as_text(route.get("label", u"")), _as_text(route.get("message", u"")),
            old_anim, source_rig, new_rig,
        )
        if QtWidgets.QMessageBox.question(self, u"确认绑定更新", msg) != QtWidgets.QMessageBox.Yes:
            return
        self._set_status("yellow", u"更新处理中...")
        self._set_migration_progress(1, u"准备绑定更新")
        self._migrate_btn.setEnabled(False)
        self._suspend_viewport_redraw()
        try:
            saved_choice = load_pair_choice(self._tool_root(), source_rig, new_rig)
            pending_choice = None
            data = run_canonical_rig_update_workflow(
                old_anim_path=old_anim,
                new_rig_path=new_rig,
                source_rig_path=source_rig,
                cleanup_packages=bool(self._config.get(u"rig_update_cleanup_packages", False)),
                keep_reports=bool(self._config.get(u"rig_update_keep_reports", True)),
                tool_root=self._tool_root(),
                context=self._context,
                # A saved version-pair review never authorizes unrelated layer
                # edits in another animation file. Those still prompt per file.
                allow_layer_fallback=False,
                ignore_duplicate_animation_objects=bool(saved_choice.get("ignore_duplicate_animation_objects", False)),
                ignored_source_contract_ids=saved_choice.get("ignored_source_contract_ids", []) or [],
                ignored_target_contract_ids=saved_choice.get("ignored_target_contract_ids", []) or [],
                reviewed_binding_difference_signature=saved_choice.get("binding_difference_signature", u""),
                progress_callback=self._set_migration_progress,
            )
            if data.get("error_code") in (
                "CANON-LAYER-MEMBERSHIP-DRIFT",
                "CANON-LAYER-MEMBERSHIP-UNRECOVERABLE",
                "CANON-BINDING-DIFFERENCE-REVIEW",
            ):
                drift_report = _as_text(data.get("report_txt", u"") or data.get("report_txt_path", u""))
                self._last_migrate_report = drift_report
                self._open_migrate_report_btn.setEnabled(bool(drift_report and os.path.exists(drift_report)))
                layer_contract = ((data.get("package_manifest", {}) or {}).get("layer_contract", {}) or {})
                membership = layer_contract.get("membership", {}) or {}
                difference = layer_contract.get("binding_difference", {}) or {}
                needs_difference_dialog = bool(
                    difference.get("has_difference") or
                    (membership.get("ambiguous", []) or [])
                )
                if needs_difference_dialog:
                    pending_choice = self._prompt_binding_difference_review(data, saved_choice=saved_choice)
                    continue_selected = pending_choice is not None
                else:
                    continue_selected = self._prompt_layer_membership_drift(data)
                    if continue_selected:
                        pending_choice = {
                            "binding_difference_signature": _as_text(difference.get("signature", "")),
                            "ignore_duplicate_animation_objects": False,
                            "ignored_source_contract_ids": [],
                            "ignored_target_contract_ids": [],
                        }
                if continue_selected:
                    self._set_status("yellow", u"按源绑定清单保底迁移...")
                    data = run_canonical_rig_update_workflow(
                        old_anim_path=old_anim,
                        new_rig_path=new_rig,
                        source_rig_path=source_rig,
                        cleanup_packages=bool(self._config.get(u"rig_update_cleanup_packages", False)),
                        keep_reports=bool(self._config.get(u"rig_update_keep_reports", True)),
                        tool_root=self._tool_root(),
                        context=self._context,
                        allow_layer_fallback=True,
                        ignore_duplicate_animation_objects=bool(pending_choice.get("ignore_duplicate_animation_objects", False)),
                        ignored_source_contract_ids=pending_choice.get("ignored_source_contract_ids", []) or [],
                        ignored_target_contract_ids=pending_choice.get("ignored_target_contract_ids", []) or [],
                        reviewed_binding_difference_signature=pending_choice.get("binding_difference_signature", u""),
                        progress_callback=self._set_migration_progress,
                    )
                else:
                    self._set_status("yellow", u"已取消，原文件未修改")
                    return
            ok = bool(data.get("ok", False))
            report_txt = _as_text(data.get("report_txt", u"") or data.get("report_txt_path", u""))
            self._last_migrate_report = report_txt
            self._open_migrate_report_btn.setEnabled(bool(report_txt and os.path.exists(report_txt)))
            if ok:
                choice_save_warning = u""
                if pending_choice is not None:
                    saved_ok, saved_value = save_pair_choice(
                        self._tool_root(), source_rig, new_rig, pending_choice
                    )
                    if not saved_ok:
                        choice_save_warning = u"\n\n版本差异选择保存失败：{0}".format(_as_text(saved_value))
                target_version = self._version_from_rig_path(new_rig) or self._rig_lookup.get("version", u"")
                if target_version:
                    self._current_binding_version_override = target_version
                    self._source_rig_manual = False
                    self._source_rig_edit.setText(new_rig)
                    self._refresh_context_label()
                    self._set_current_binding_field(old_anim)
                package_manifest = data.get("package_manifest", {}) or {}
                package_warnings = package_manifest.get("warnings", []) or []
                phase4 = data.get("phase4_constraints", {}) or {}
                ignored_preflight = len(package_manifest.get("continued_blockers", []) or [])
                skipped_controls = data.get("skipped_controls", []) or []
                user_ignored_controls = data.get("user_ignored_controls", []) or []
                warn_count = len(package_warnings) + len(phase4.get("warnings", []) or []) + ignored_preflight + len(skipped_controls)
                self._set_status("yellow" if warn_count else "green", u"更新完成 W{0}".format(warn_count))
                self._set_migration_progress(100, u"绑定更新完成")
                self._close_migration_progress()
                self._resume_viewport_redraw()
                skipped_lines = []
                for item in skipped_controls[:50]:
                    skipped_lines.append(u"[{0}] {1}：{2}".format(
                        _as_text(item.get("contract_layer", u"")),
                        _as_text(item.get("name", u"<未命名对象>")),
                        _as_text(item.get("message", u"")) or _as_text(item.get("reason", u"已跳过")),
                    ))
                skipped_text = u""
                if skipped_lines:
                    skipped_text = u"\n\n未迁移控制器（{0} 个）：\n{1}".format(
                        len(skipped_controls), u"\n".join(skipped_lines)
                    )
                    if len(skipped_controls) > len(skipped_lines):
                        skipped_text += u"\n……其余 {0} 个请查看报告。".format(len(skipped_controls) - len(skipped_lines))
                # A channel the new binding drives with another controller class
                # was never transportable, so it is a rig difference to read once
                # rather than one warning per control.
                structural_text = u""
                structural_advisories = data.get("structural_advisories", []) or []
                if structural_advisories:
                    layers = sorted(set([
                        _as_text(item.get("contract_layer", u"")) for item in structural_advisories
                    ]) - set([u""]))
                    structural_text = (
                        u"\n\n{0} 个对象的部分通道在新绑定里换了控制器类型（{1} 层），"
                        u"这些通道的关键帧无法迁移，其他通道已正常加载；明细见报告。"
                    ).format(len(structural_advisories), u"、".join(layers) or u"非 BIP")
                ignored_text = u""
                if user_ignored_controls:
                    ignored_text = u"\n\n已按版本差异选择忽略 {0} 个对象（不计入警告）。".format(
                        len(user_ignored_controls)
                    )
                QtWidgets.QMessageBox.information(
                    self,
                    u"更新完成（有跳过项）" if skipped_controls else u"更新完成",
                    u"更新完成；迁移警告 {0} 条。{1}{2}{3}\n\n报告:\n{4}{5}".format(
                        warn_count, skipped_text, structural_text, ignored_text, report_txt, choice_save_warning
                    ),
                )
            else:
                self._set_status("red", u"更新失败")
                detail = _as_text(data.get("message", u""))
                if report_txt:
                    detail = u"{0}\n\n报告:\n{1}".format(detail, report_txt)
                package_manifest = data.get("package_manifest", {}) or {}
                self._show_reportable_error(
                    u"更新失败",
                    detail,
                    context={
                        u"phase": u"canonical-rig-update",
                        u"error_code": data.get("error_code", u""),
                    },
                    attachments=[
                        report_txt,
                        _as_text(data.get("report_json", u"")),
                        _as_text(package_manifest.get("manifest_path", u"")),
                    ],
                )
        except Exception as e:
            self._set_status("red", u"更新失败")
            self._show_reportable_error(
                u"更新失败",
                _as_text(e),
                error=e,
                context={u"phase": u"canonical-rig-update"},
            )
        finally:
            self._resume_viewport_redraw()
            self._close_migration_progress()
            self._migrate_btn.setEnabled(True)

    def _rollback_backup(self):
        self.refresh_current_anim_path()
        old_anim = self._old_anim_edit.text().strip()
        backups = list_backups(old_anim)
        if not backups:
            QtWidgets.QMessageBox.information(self, u"提示", u"没有找到当前文件的绑定更新备份。")
            return
        labels = [os.path.basename(x) for x in backups]
        item, ok = QtWidgets.QInputDialog.getItem(self, u"选择回滚备份", u"备份文件：", labels, 0, False)
        if not ok or not item:
            return
        backup_path = backups[labels.index(item)]
        if QtWidgets.QMessageBox.question(self, u"确认回滚", u"将用备份替换当前文件：\n{0}".format(backup_path)) != QtWidgets.QMessageBox.Yes:
            return
        try:
            restore_backup(old_anim, backup_path)
            if self._rt is None:
                import pymxs
                self._rt = pymxs.runtime
            with SilentFileDialogs(self._rt):
                self._rt.loadMaxFile(old_anim, quiet=True, useFileUnits=True)
            self._current_binding_version_override = u""
            self._source_rig_manual = False
            self._source_rig_edit.setText(u"")
            self.refresh_current_anim_path()
            self._set_status("green", u"已回滚")
            QtWidgets.QMessageBox.information(self, u"回滚完成", u"已恢复备份:\n{0}".format(backup_path))
        except Exception as e:
            self._set_status("red", u"回滚失败")
            self._show_reportable_error(
                u"回滚失败",
                _as_text(e),
                error=e,
                context={u"phase": u"rollback-backup"},
            )

    def _update_tools_from_public(self):
        try:
            rt = self._load_migrate_service()
            launcher = os.path.join(self._tool_root(), "maxscript", "ReferenceRigLauncher.ms")
            if not os.path.exists(launcher):
                raise RuntimeError(u"未找到更新脚本: {0}".format(launcher))
            rt.fileIn(launcher)
            if not hasattr(rt, "RR_Launcher"):
                raise RuntimeError(u"更新服务未加载: RR_Launcher")
            ok = bool(rt.RR_Launcher.updateFromSource())
            if ok:
                QtWidgets.QMessageBox.information(self, u"更新完成", u"本地工具已从公盘同步。\n请关闭并重新打开工具界面。")
            else:
                self._show_reportable_error(
                    u"更新失败",
                    u"更新未成功，请查看 Max 提示信息。",
                    context={u"phase": u"update-tools-from-public"},
                )
        except Exception as e:
            self._show_reportable_error(
                u"更新失败",
                _as_text(e),
                error=e,
                context={u"phase": u"update-tools-from-public"},
            )

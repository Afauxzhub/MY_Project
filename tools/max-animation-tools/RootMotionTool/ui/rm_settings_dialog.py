# -*- coding: utf-8 -*-
"""
发布工具设置弹窗（五个 Tab）
  Tab 1 — 路径 & 发布选项
  Tab 2 — 局内分类映射（同时作为发布白名单）
  Tab 3 — 局外模块映射
  Tab 4 — 局外类型 / 资产类型（发布白名单）
  Tab 5 — 高级设置（发布后处理、导出预处理、开发机）

武器约束 / 绑定更新设置已拆到各独立工具窗口右上角「设置」。
"""
from __future__ import print_function
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
        try:
            return str(value).decode("utf-8")
        except Exception:
            return u""


class SettingsDialog(QtWidgets.QDialog):

    def __init__(self, config, parent=None):
        """
        config : dict（已加载的配置，对话框会对其副本操作，accept 后调用 get_config() 取回）
        """
        super(SettingsDialog, self).__init__(parent)
        self.setWindowTitle(u"工具设置")
        self.setMinimumSize(580, 480)
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self._config = dict(config)
        self._build_ui()
        self._apply_styles()
        self._load_to_ui()

    # ── UI 构建 ───────────────────────────────────────────────────

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs, 1)

        # ── Tab 1: 路径 & 发布 ──────────────────────────────────
        path_tab    = QtWidgets.QWidget()
        path_layout = QtWidgets.QFormLayout(path_tab)
        path_layout.setSpacing(12)
        path_layout.setContentsMargins(16, 16, 16, 16)

        # Unity 根路径
        unity_row = QtWidgets.QHBoxLayout()
        self._unity_path_edit = QtWidgets.QLineEdit()
        self._unity_path_edit.setPlaceholderText(
            u"例：D:\\MyUnityProject\\Assets"
        )
        browse_unity = QtWidgets.QPushButton(u"浏览…")
        browse_unity.setFixedWidth(88)
        browse_unity.clicked.connect(
            lambda: self._browse_dir(self._unity_path_edit)
        )
        unity_row.addWidget(self._unity_path_edit)
        unity_row.addWidget(browse_unity)
        path_layout.addRow(u"Unity 项目路径\n（到 Assets）：", unity_row)

        # 公盘路径
        nas_row = QtWidgets.QHBoxLayout()
        self._nas_path_edit = QtWidgets.QLineEdit()
        browse_nas = QtWidgets.QPushButton(u"浏览…")
        browse_nas.setFixedWidth(88)
        browse_nas.clicked.connect(
            lambda: self._browse_dir(self._nas_path_edit)
        )
        nas_row.addWidget(self._nas_path_edit)
        nas_row.addWidget(browse_nas)
        path_layout.addRow(u"公盘动作资产根路径：", nas_row)

        error_report_row = QtWidgets.QHBoxLayout()
        self._error_report_path_edit = QtWidgets.QLineEdit()
        self._error_report_path_edit.setPlaceholderText(
            u"留空时使用公盘动作资产根路径同级的“OP Tools报错报告”"
        )
        browse_error_report = QtWidgets.QPushButton(u"浏览…")
        browse_error_report.setFixedWidth(88)
        browse_error_report.clicked.connect(
            lambda: self._browse_dir(self._error_report_path_edit)
        )
        error_report_row.addWidget(self._error_report_path_edit)
        error_report_row.addWidget(browse_error_report)
        path_layout.addRow(u"报错报告公盘目录：", error_report_row)

        self._publisher_name_edit = QtWidgets.QLineEdit()
        self._publisher_name_edit.setPlaceholderText(u"例：测试者（保存在当前机器的发布配置中）")
        path_layout.addRow(u"发布负责人：", self._publisher_name_edit)

        self._backup_stage_combo = QtWidgets.QComboBox()
        self._backup_stage_combo.addItems([u"初版", u"终版", u"监修"])
        path_layout.addRow(u"发布阶段：", self._backup_stage_combo)

        from pipeline.publish_public_lookup import build_review_version_options
        self._backup_version_combo = QtWidgets.QComboBox()
        self._backup_version_combo.setEditable(False)
        self._backup_version_combo.addItems(build_review_version_options())
        self._backup_version_label = QtWidgets.QLabel(u"监修子版本：")
        path_layout.addRow(self._backup_version_label, self._backup_version_combo)
        self._backup_stage_combo.currentIndexChanged.connect(self._update_backup_stage_ui)

        tabs.addTab(path_tab, u"路径 & 发布")

        # ── Tab 2: 局内分类映射 ─────────────────────────────────
        cat_tab    = QtWidgets.QWidget()
        cat_layout = QtWidgets.QVBoxLayout(cat_tab)
        cat_layout.setContentsMargins(12, 12, 12, 12)

        cat_hint = QtWidgets.QLabel(
            u"配置局内动画文件名第一字段（分类）对应 Unity 下的文件夹名。\n"
            u"此表左侧「分类名」同时作为发布命名白名单：新增分类后即可正常发布。\n"
            u"多个分类可映射到同一文件夹（如将 Elite 和 Boss 都映射到 Boss）。"
        )
        cat_hint.setWordWrap(True)
        cat_hint.setStyleSheet(u"color: #aaa; font-size: 11px; margin-bottom: 6px;")
        cat_layout.addWidget(cat_hint)

        self._cat_table = QtWidgets.QTableWidget(0, 2)
        self._cat_table.setHorizontalHeaderLabels([u"分类名（第一字段）", u"Unity 文件夹名"])
        self._cat_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self._cat_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._cat_table.setMinimumHeight(180)
        cat_layout.addWidget(self._cat_table)

        cat_btn_row = QtWidgets.QHBoxLayout()
        add_cat = QtWidgets.QPushButton(u"＋ 添加行")
        add_cat.clicked.connect(self._add_cat_row)
        del_cat = QtWidgets.QPushButton(u"－ 删除选中行")
        del_cat.clicked.connect(self._del_cat_row)
        reset_cat = QtWidgets.QPushButton(u"↺ 还原默认")
        reset_cat.clicked.connect(self._reset_cat_table)
        cat_btn_row.addWidget(add_cat)
        cat_btn_row.addWidget(del_cat)
        cat_btn_row.addWidget(reset_cat)
        cat_btn_row.addStretch()
        cat_layout.addLayout(cat_btn_row)

        tabs.addTab(cat_tab, u"局内分类映射")

        # ── Tab 3: 局外模块映射 ─────────────────────────────────
        mod_tab    = QtWidgets.QWidget()
        mod_layout = QtWidgets.QVBoxLayout(mod_tab)
        mod_layout.setContentsMargins(12, 12, 12, 12)

        mod_hint = QtWidgets.QLabel(
            u"局外过场动画模块缩写与 Unity/公盘文件夹名的对应关系。\n"
            u"此表同时作为局外模块发布白名单；模块标签决定它显示在新建文件的"
            u"“角色配套”或“剧情对话”页签。"
        )
        mod_hint.setWordWrap(True)
        mod_hint.setStyleSheet(u"color: #aaa; font-size: 11px; margin-bottom: 6px;")
        mod_layout.addWidget(mod_hint)

        self._mod_table = QtWidgets.QTableWidget(0, 3)
        self._mod_table.setHorizontalHeaderLabels(
            [u"模块缩写", u"文件夹名", u"模块标签"]
        )
        self._mod_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self._mod_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._mod_table.setMinimumHeight(180)
        mod_layout.addWidget(self._mod_table)

        mod_btn_row = QtWidgets.QHBoxLayout()
        add_mod = QtWidgets.QPushButton(u"＋ 添加行")
        add_mod.clicked.connect(self._add_mod_row)
        del_mod = QtWidgets.QPushButton(u"－ 删除选中行")
        del_mod.clicked.connect(self._del_mod_row)
        reset_mod = QtWidgets.QPushButton(u"↺ 还原默认")
        reset_mod.clicked.connect(self._reset_mod_table)
        mod_btn_row.addWidget(add_mod)
        mod_btn_row.addWidget(del_mod)
        mod_btn_row.addWidget(reset_mod)
        mod_btn_row.addStretch()
        mod_layout.addLayout(mod_btn_row)

        tabs.addTab(mod_tab, u"局外模块映射")

        # ── Tab 4: 局外类型 / 资产类型 ───────────────────────────
        type_tab = QtWidgets.QWidget()
        type_layout = QtWidgets.QVBoxLayout(type_tab)
        type_layout.setContentsMargins(12, 12, 12, 12)

        type_hint = QtWidgets.QLabel(
            u"局外文件名第二字段（类型）→ 文件夹映射，同时作为发布白名单。\n"
            u"Chap01、Chap02 等章节类型仍由内置规则支持，无需写入此表。\n"
            u"下方资产类型列表用于校验第三段后的 Char/Prop/Cam 等字段。"
        )
        type_hint.setWordWrap(True)
        type_hint.setStyleSheet(u"color: #aaa; font-size: 11px; margin-bottom: 6px;")
        type_layout.addWidget(type_hint)

        self._type_table = QtWidgets.QTableWidget(0, 2)
        self._type_table.setHorizontalHeaderLabels([u"类型码", u"文件夹名"])
        self._type_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self._type_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._type_table.setMinimumHeight(140)
        type_layout.addWidget(self._type_table)

        type_btn_row = QtWidgets.QHBoxLayout()
        add_type = QtWidgets.QPushButton(u"＋ 添加行")
        add_type.clicked.connect(self._add_type_row)
        del_type = QtWidgets.QPushButton(u"－ 删除选中行")
        del_type.clicked.connect(self._del_type_row)
        reset_type = QtWidgets.QPushButton(u"↺ 还原默认")
        reset_type.clicked.connect(self._reset_type_table)
        type_btn_row.addWidget(add_type)
        type_btn_row.addWidget(del_type)
        type_btn_row.addWidget(reset_type)
        type_btn_row.addStretch()
        type_layout.addLayout(type_btn_row)

        asset_row = QtWidgets.QHBoxLayout()
        asset_row.addWidget(QtWidgets.QLabel(u"资产类型白名单（逗号分隔）："))
        self._asset_types_edit = QtWidgets.QLineEdit()
        self._asset_types_edit.setPlaceholderText(u"Char, Prop, Cam")
        asset_row.addWidget(self._asset_types_edit, 1)
        type_layout.addLayout(asset_row)

        tabs.addTab(type_tab, u"局外类型映射")

        # ── Tab 5: 高级设置 ─────────────────────────────────────
        adv_tab    = QtWidgets.QWidget()
        adv_layout = QtWidgets.QVBoxLayout(adv_tab)
        adv_layout.setContentsMargins(16, 16, 16, 16)
        adv_layout.setSpacing(10)

        adv_hint = QtWidgets.QLabel(
            u"这些选项会作为默认行为保存下来，按使用场景分类管理。"
        )
        adv_hint.setWordWrap(True)
        adv_hint.setStyleSheet(u"color: #aaa; font-size: 11px;")
        adv_layout.addWidget(adv_hint)

        self._adv_force_keys_chk = QtWidgets.QCheckBox(u"强制首尾 K 帧")
        self._adv_fix_rot_chk = QtWidgets.QCheckBox(u"Root 预处理归零")
        self._adv_remove_init_z_chk = QtWidgets.QCheckBox(u"去除初始空中高度（Z 轴）")
        self._adv_unlock_chk = QtWidgets.QCheckBox(u"自动解冻/取消隐藏节点")
        self._adv_delete_temp_chk = QtWidgets.QCheckBox(u"导出后还原源文件并删除临时文件")
        self._adv_root_motion_debug_log_chk = QtWidgets.QCheckBox(
            u"发布日志记录根运动逐帧调试数据（Bip001 原始/Root 添加/Bip001 计算后）"
        )
        self._auto_unity_chk = QtWidgets.QCheckBox(u"导出后自动拷贝 FBX 到 Unity 目录")
        self._auto_nas_chk = QtWidgets.QCheckBox(u"发布后自动备份 MAX 文件到公盘")
        self._auto_focus_chk = QtWidgets.QCheckBox(u"拷贝完成后自动唤起 Unity 触发刷新")
        self._open_folder_chk = QtWidgets.QCheckBox(u"发布完成后在 Unity Project 窗口定位动画目录")

        publish_group = self._make_check_group(u"发布后处理", [
            self._auto_unity_chk,
            self._auto_nas_chk,
            self._auto_focus_chk,
            self._open_folder_chk,
        ])
        export_group = self._make_check_group(u"导出预处理", [
            self._adv_force_keys_chk,
            self._adv_fix_rot_chk,
            self._adv_remove_init_z_chk,
            self._adv_unlock_chk,
            self._adv_delete_temp_chk,
            self._adv_root_motion_debug_log_chk,
        ])

        dev_group = QtWidgets.QGroupBox(u"开发机（本机 rm_config，公盘同步不会覆盖）")
        dev_lay = QtWidgets.QVBoxLayout(dev_group)
        dev_lay.setContentsMargins(12, 10, 12, 10)
        dev_lay.setSpacing(6)
        dev_hint = QtWidgets.QLabel(
            u"保底：在本地工程根目录（含 install_animation_tools.ms 与 maxscript\\ReferenceRigLauncher.ms）"
            u"放置下方文件名的空文件，本机即视为开发机并显示「上传更新」。"
            u"换机或重装后只要工程里仍有该文件即可恢复。\n"
            u"也可设置环境变量 ANIMATION_TOOLS_PROJECT_ROOT 指向工程根；"
            u"「可选工程根」用于标记不在默认扫描路径时的额外目录。"
        )
        dev_hint.setWordWrap(True)
        dev_hint.setStyleSheet(u"color: #aaa; font-size: 11px;")
        dev_lay.addWidget(dev_hint)
        self._dev_marker_filename_edit = QtWidgets.QLineEdit()
        self._dev_marker_filename_edit.setPlaceholderText(u"默认 AnimationTools_DevMachine.flag")
        self._dev_project_override_edit = QtWidgets.QLineEdit()
        self._dev_project_override_edit.setPlaceholderText(u"可选，例如 D:\\...\\Animation Tools")
        dev_form = QtWidgets.QFormLayout()
        dev_form.setSpacing(8)
        dev_form.addRow(u"开发机标记文件名：", self._dev_marker_filename_edit)
        dev_form.addRow(u"可选工程根目录：", self._dev_project_override_edit)
        dev_lay.addLayout(dev_form)

        adv_layout.addWidget(publish_group)
        adv_layout.addWidget(export_group)
        adv_layout.addWidget(dev_group)

        adv_layout.addStretch()
        tabs.addTab(adv_tab, u"高级设置")

        # ── 底部按钮 ─────────────────────────────────────────────
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet(u"color: #444;")
        layout.addWidget(sep)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QtWidgets.QPushButton(u"取消")
        cancel_btn.setStyleSheet(u"QPushButton { padding: 7px 18px; border-radius: 4px; }")
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QtWidgets.QPushButton(u"保存设置")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(
            u"QPushButton {"
            u"  background: #2d4a6a; color: white;"
            u"  padding: 7px 18px; border-radius: 4px;"
            u"}"
            u"QPushButton:hover { background: #3d5a8a; }"
        )
        ok_btn.clicked.connect(self._on_save)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _make_check_group(self, title, widgets):
        group = QtWidgets.QGroupBox(title)
        lay = QtWidgets.QVBoxLayout(group)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        for widget in widgets:
            lay.addWidget(widget)
        return group

    # ── 数据加载 ──────────────────────────────────────────────────

    def _load_to_ui(self):
        from pipeline.rm_naming import (
            DEFAULT_CATEGORY_FOLDER_MAP,
            DEFAULT_MODULE_TAG_MAP,
            DEFAULT_OUTDOOR_ASSET_TYPES,
            MODULE_FOLDER_MAP,
            TYPE_FOLDER_MAP,
            merge_module_tag_map,
        )

        self._unity_path_edit.setText(self._config.get(u"unity_root", u""))
        self._nas_path_edit.setText(
            self._config.get(u"nas_base", u"")
        )
        self._error_report_path_edit.setText(
            self._config.get(u"error_report_root", u"")
        )
        self._auto_unity_chk.setChecked(self._config.get(u"auto_copy_unity",   True))
        self._auto_nas_chk.setChecked(  self._config.get(u"auto_backup_nas",   True))
        self._auto_focus_chk.setChecked(self._config.get(u"auto_focus_unity",  True))
        self._open_folder_chk.setChecked(self._config.get(u"open_folder_after_export", True))
        stage_text = self._config.get(u"backup_stage", u"初版")
        stage_idx = self._backup_stage_combo.findText(stage_text)
        if stage_idx < 0:
            stage_idx = 0
        self._backup_stage_combo.setCurrentIndex(stage_idx)
        version_text = _as_text(self._config.get(u"backup_version", u"1.0")).strip()
        version_idx = self._backup_version_combo.findText(version_text)
        self._backup_version_combo.setCurrentIndex(version_idx if version_idx >= 0 else 0)
        self._update_backup_stage_ui()
        self._publisher_name_edit.setText(self._config.get(u"publisher_name", u""))
        self._adv_force_keys_chk.setChecked(self._config.get(u"adv_force_keys", True))
        self._adv_fix_rot_chk.setChecked(self._config.get(u"adv_fix_rot", True))
        self._adv_remove_init_z_chk.setChecked(self._config.get(u"adv_remove_initial_z", True))
        self._adv_unlock_chk.setChecked(self._config.get(u"adv_unlock_nodes", True))
        self._adv_delete_temp_chk.setChecked(self._config.get(u"adv_delete_temp_file", True))
        self._adv_root_motion_debug_log_chk.setChecked(
            self._config.get(u"adv_root_motion_debug_log", False)
        )
        marker_default = self._config.get(u"dev_machine_marker_filename", u"AnimationTools_DevMachine.flag")
        self._dev_marker_filename_edit.setText(_as_text(marker_default))
        self._dev_project_override_edit.setText(
            _as_text(self._config.get(u"dev_machine_project_override", u""))
        )

        # 分类映射表
        self._cat_table.setRowCount(0)
        cat_map = self._config.get(u"category_folder_map", DEFAULT_CATEGORY_FOLDER_MAP)
        for k, v in cat_map.items():
            self._add_cat_row(k, v)

        # 模块映射表
        self._mod_table.setRowCount(0)
        mod_map = self._config.get(u"module_folder_map", MODULE_FOLDER_MAP)
        mod_tags = merge_module_tag_map(
            mod_map, self._config.get(u"module_tag_map", DEFAULT_MODULE_TAG_MAP)
        )
        for k, v in mod_map.items():
            self._add_mod_row(k, v, mod_tags.get(k))

        # 局外类型映射表
        self._type_table.setRowCount(0)
        type_map = self._config.get(u"outdoor_type_folder_map", TYPE_FOLDER_MAP)
        for k, v in type_map.items():
            self._add_type_row(k, v)

        asset_types = self._config.get(u"outdoor_asset_types", DEFAULT_OUTDOOR_ASSET_TYPES)
        self._asset_types_edit.setText(u", ".join([_as_text(x) for x in asset_types]))

        self._update_backup_stage_ui()

    # ── 表格操作 ──────────────────────────────────────────────────

    def _add_cat_row(self, key=u"", val=u""):
        row = self._cat_table.rowCount()
        self._cat_table.insertRow(row)
        self._cat_table.setItem(row, 0, QtWidgets.QTableWidgetItem(key))
        self._cat_table.setItem(row, 1, QtWidgets.QTableWidgetItem(val))

    def _del_cat_row(self):
        row = self._cat_table.currentRow()
        if row >= 0:
            self._cat_table.removeRow(row)

    def _reset_cat_table(self):
        from pipeline.rm_naming import DEFAULT_CATEGORY_FOLDER_MAP
        self._cat_table.setRowCount(0)
        for k, v in DEFAULT_CATEGORY_FOLDER_MAP.items():
            self._add_cat_row(k, v)

    def _add_mod_row(self, key=u"", val=u"", tag=u"角色配套"):
        from pipeline.rm_naming import MODULE_TAGS, normalize_module_tag

        row = self._mod_table.rowCount()
        self._mod_table.insertRow(row)
        self._mod_table.setItem(row, 0, QtWidgets.QTableWidgetItem(key))
        self._mod_table.setItem(row, 1, QtWidgets.QTableWidgetItem(val))
        tag_combo = QtWidgets.QComboBox()
        tag_combo.addItems(list(MODULE_TAGS))
        selected = normalize_module_tag(tag, default=u"角色配套")
        tag_index = tag_combo.findText(selected)
        tag_combo.setCurrentIndex(tag_index if tag_index >= 0 else 0)
        self._mod_table.setCellWidget(row, 2, tag_combo)

    def _del_mod_row(self):
        row = self._mod_table.currentRow()
        if row >= 0:
            self._mod_table.removeRow(row)

    def _reset_mod_table(self):
        from pipeline.rm_naming import MODULE_FOLDER_MAP, DEFAULT_MODULE_TAG_MAP
        self._mod_table.setRowCount(0)
        for k, v in MODULE_FOLDER_MAP.items():
            self._add_mod_row(k, v, DEFAULT_MODULE_TAG_MAP.get(k))

    def _add_type_row(self, key=u"", val=u""):
        row = self._type_table.rowCount()
        self._type_table.insertRow(row)
        self._type_table.setItem(row, 0, QtWidgets.QTableWidgetItem(key))
        self._type_table.setItem(row, 1, QtWidgets.QTableWidgetItem(val))

    def _del_type_row(self):
        row = self._type_table.currentRow()
        if row >= 0:
            self._type_table.removeRow(row)

    def _reset_type_table(self):
        from pipeline.rm_naming import TYPE_FOLDER_MAP
        self._type_table.setRowCount(0)
        for k, v in TYPE_FOLDER_MAP.items():
            self._add_type_row(k, v)

    def _parse_asset_types_text(self, text):
        result = []
        seen = set()
        for part in _as_text(text).replace(u"；", u",").split(u","):
            item = part.strip()
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    # ── 浏览目录 ──────────────────────────────────────────────────

    def _browse_dir(self, line_edit):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, u"选择路径", line_edit.text()
        )
        if path:
            line_edit.setText(path)

    def _update_backup_stage_ui(self, *args):
        is_review = self._backup_stage_combo.currentText() == u"监修"
        self._backup_version_label.setEnabled(is_review)
        self._backup_version_combo.setEnabled(is_review)
        if is_review:
            if self._backup_version_combo.currentIndex() < 0:
                self._backup_version_combo.setCurrentIndex(0)
        else:
            self._backup_version_combo.setCurrentIndex(-1)

    # ── 保存 ─────────────────────────────────────────────────────

    def _on_save(self):
        if self._backup_stage_combo.currentText() == u"监修":
            version = self._backup_version_combo.currentText().strip()
            if not version:
                QtWidgets.QMessageBox.warning(
                    self, u"提示", u"发布阶段为“监修”时，请选择监修子版本。"
                )
                return

        # 读取分类映射
        cat_map = {}
        for row in range(self._cat_table.rowCount()):
            k_item = self._cat_table.item(row, 0)
            v_item = self._cat_table.item(row, 1)
            if k_item and v_item and k_item.text().strip():
                cat_map[_as_text(k_item.text()).strip()] = _as_text(v_item.text()).strip()

        # 读取模块映射
        mod_map = {}
        mod_tag_map = {}
        for row in range(self._mod_table.rowCount()):
            k_item = self._mod_table.item(row, 0)
            v_item = self._mod_table.item(row, 1)
            if k_item and v_item and k_item.text().strip():
                module_code = _as_text(k_item.text()).strip()
                mod_map[module_code] = _as_text(v_item.text()).strip()
                tag_combo = self._mod_table.cellWidget(row, 2)
                mod_tag_map[module_code] = _as_text(
                    tag_combo.currentText() if tag_combo is not None else u"剧情对话"
                ).strip()

        # 读取局外类型映射
        type_map = {}
        for row in range(self._type_table.rowCount()):
            k_item = self._type_table.item(row, 0)
            v_item = self._type_table.item(row, 1)
            if k_item and v_item and k_item.text().strip():
                type_map[_as_text(k_item.text()).strip()] = _as_text(v_item.text()).strip()

        asset_types = self._parse_asset_types_text(self._asset_types_edit.text())
        if not asset_types:
            QtWidgets.QMessageBox.warning(
                self, u"提示", u"资产类型白名单不能为空，请至少填写一项（如 Char）。"
            )
            return
        if not cat_map:
            QtWidgets.QMessageBox.warning(
                self, u"提示", u"局内分类映射不能为空，请至少保留一个分类。"
            )
            return

        self._config[u"unity_root"]              = _as_text(self._unity_path_edit.text()).strip()
        self._config[u"nas_base"]                = _as_text(self._nas_path_edit.text()).strip()
        self._config[u"error_report_root"]       = _as_text(self._error_report_path_edit.text()).strip()
        self._config[u"auto_copy_unity"]         = bool(self._auto_unity_chk.isChecked())
        self._config[u"auto_backup_nas"]         = bool(self._auto_nas_chk.isChecked())
        self._config[u"auto_focus_unity"]        = bool(self._auto_focus_chk.isChecked())
        self._config[u"open_folder_after_export"]= bool(self._open_folder_chk.isChecked())
        self._config[u"backup_stage"]            = _as_text(self._backup_stage_combo.currentText())
        self._config[u"backup_version"]          = (
            _as_text(self._backup_version_combo.currentText()).strip()
            if self._backup_stage_combo.currentText() == u"监修" else u""
        )
        self._config[u"publisher_name"]          = _as_text(self._publisher_name_edit.text()).strip()
        self._config[u"adv_force_keys"]          = bool(self._adv_force_keys_chk.isChecked())
        self._config[u"adv_fix_rot"]             = bool(self._adv_fix_rot_chk.isChecked())
        self._config[u"adv_remove_initial_z"]    = bool(self._adv_remove_init_z_chk.isChecked())
        self._config[u"adv_unlock_nodes"]        = bool(self._adv_unlock_chk.isChecked())
        self._config[u"adv_delete_temp_file"]    = bool(self._adv_delete_temp_chk.isChecked())
        self._config[u"adv_root_motion_debug_log"] = bool(
            self._adv_root_motion_debug_log_chk.isChecked()
        )
        self._config.pop(u"rig_update_auto_on_file_open", None)
        marker_fn = _as_text(self._dev_marker_filename_edit.text()).strip()
        self._config[u"dev_machine_marker_filename"] = marker_fn or u"AnimationTools_DevMachine.flag"
        self._config[u"dev_machine_project_override"] = _as_text(self._dev_project_override_edit.text()).strip()
        self._config[u"category_folder_map"]     = cat_map
        self._config[u"module_folder_map"]       = mod_map
        self._config[u"module_tag_map"]          = mod_tag_map
        self._config[u"outdoor_type_folder_map"] = type_map
        self._config[u"outdoor_asset_types"]     = asset_types

        self.accept()

    def _apply_styles(self):
        self.setStyleSheet(
            u"""
            QDialog {
                background: #141922;
                color: #e6ebf2;
            }
            QLabel {
                color: #dbe2ea;
            }
            QTabWidget::pane {
                border: 1px solid #2b3445;
                border-radius: 10px;
                background: #1b2230;
                top: -1px;
            }
            QTabBar::tab {
                background: #202a39;
                color: #c8d1dd;
                border: 1px solid #31405a;
                padding: 8px 14px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #3f6ed8;
                color: white;
            }
            QPushButton {
                background: #273244;
                color: #eef3fb;
                border: 1px solid #384861;
                border-radius: 8px;
                padding: 7px 12px;
            }
            QPushButton:hover {
                background: #31415b;
            }
            QLineEdit, QTableWidget {
                background: #0f141d;
                color: #edf2f8;
                border: 1px solid #303a4c;
                border-radius: 8px;
                padding: 6px 8px;
            }
            QHeaderView::section {
                background: #202a39;
                color: #dbe2ea;
                border: none;
                padding: 6px;
            }
            QCheckBox {
                spacing: 8px;
                padding: 4px 0px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #5d6f8c;
                background: #101620;
            }
            QCheckBox::indicator:checked {
                background: #4c7bf0;
                border: 1px solid #4c7bf0;
            }
            """
        )

    # ── 公开接口 ─────────────────────────────────────────────────

    def get_config(self):
        """返回保存后的配置字典"""
        return self._config

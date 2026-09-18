# -*- coding: utf-8 -*-
"""动画文件管理器主窗口。"""
from __future__ import division
import os

from PySide2 import QtWidgets, QtCore, QtGui

from core.config_store import load_config, save_config
from core.max_ops import open_max_file, delete_max_file, rename_max_file, open_file_folder
from core.paths import NAS_BASE
from core.public_updates import public_choice_label
from ui.simple_mode_widget import SimpleModeWidget, COMBAT_TABS, CONTEXT_MENU_STYLE
from ui.full_mode_widget import FullModeWidget

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


class AnimFileManagerWindow(QtWidgets.QDialog):
    """动画文件管理器：完整显示 / 简略显示。"""

    def __init__(self, parent=None):
        super(AnimFileManagerWindow, self).__init__(parent)
        self.setWindowTitle(u"动画文件管理器")
        self.setMinimumSize(720, 480)
        self._resize_for_available_screen()
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self._config = load_config()
        self._build_ui()
        self._apply_styles()
        self._restore_state()

    def _resize_for_available_screen(self):
        """按当前显示器工作区设置首次尺寸，窗口仍可由用户自由拉伸。"""
        geometry = None
        # Max 2020 可能把应用实例包装成 QCoreApplication；不能从该实例
        # 调用 desktop()，所以这里始终使用 Qt 的静态屏幕 API。
        try:
            desktop = QtWidgets.QApplication.desktop()
            if desktop is not None:
                try:
                    geometry = desktop.availableGeometry(self)
                except Exception:
                    geometry = desktop.availableGeometry()
        except Exception:
            geometry = None
        if geometry is None:
            try:
                screen = QtGui.QGuiApplication.primaryScreen()
                if screen is not None:
                    geometry = screen.availableGeometry()
            except Exception:
                geometry = None
        if geometry is None or geometry.width() <= 0 or geometry.height() <= 0:
            self.resize(1280, 800)
            return
        width = max(720, min(1600, int(geometry.width() * 0.84)))
        height = max(480, min(1000, int(geometry.height() * 0.84)))
        self.resize(width, height)
        self.move(
            geometry.x() + max(0, (geometry.width() - width) // 2),
            geometry.y() + max(0, (geometry.height() - height) // 2),
        )

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        toolbar = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(u"动画文件管理器")
        title.setObjectName(u"afmMainTitle")
        toolbar.addWidget(title)

        self._set_local_btn = QtWidgets.QPushButton(u"设置本地路径")
        self._set_local_btn.clicked.connect(self._on_set_local_root)
        toolbar.addWidget(self._set_local_btn)

        self._settings_btn = QtWidgets.QPushButton(u"设置")
        self._settings_menu = QtWidgets.QMenu(self)
        self._settings_menu.setStyleSheet(CONTEXT_MENU_STYLE)
        self._sync_on_open_act = self._settings_menu.addAction(
            u"打开公盘文件时同步到本地"
        )
        self._sync_on_open_act.setCheckable(True)
        self._sync_on_open_act.setChecked(
            bool(self._config.get(u"open_public_sync_to_local", False))
        )
        self._sync_on_open_act.triggered.connect(self._on_toggle_sync_on_open)
        self._settings_btn.setMenu(self._settings_menu)
        toolbar.addWidget(self._settings_btn)
        toolbar.addStretch()

        self._mode_full = QtWidgets.QRadioButton(u"完整显示")
        self._mode_simple = QtWidgets.QRadioButton(u"简略显示")
        self._mode_simple.setChecked(True)
        self._mode_full.toggled.connect(self._on_mode_changed)
        toolbar.addWidget(self._mode_full)
        toolbar.addWidget(self._mode_simple)
        root.addLayout(toolbar)

        self._stack = QtWidgets.QStackedWidget()

        self._simple_page = QtWidgets.QWidget()
        simple_lay = QtWidgets.QVBoxLayout(self._simple_page)
        simple_lay.setContentsMargins(0, 0, 0, 0)
        simple_lay.setSpacing(4)

        self._combat_bar = QtWidgets.QTabBar()
        self._combat_bar.setObjectName(u"afmCombatBar")
        self._combat_bar.setDrawBase(False)
        self._combat_bar.addTab(u"局内战斗")
        self._combat_bar.addTab(u"局外演出")
        self._combat_bar.currentChanged.connect(self._on_combat_tab_changed)
        simple_lay.addWidget(self._combat_bar)

        self._simple_widget = SimpleModeWidget()
        self._simple_widget.set_config(self._config, reload_categories=False)
        self._simple_widget.file_activated.connect(self._open_file)
        self._simple_widget.file_context.connect(self._show_file_menu)
        self._simple_widget.config_changed.connect(self._on_simple_config_changed)
        self._simple_widget.status_message.connect(self._set_status)
        simple_lay.addWidget(self._simple_widget, 1)

        self._source_bar = QtWidgets.QTabBar()
        self._source_bar.setObjectName(u"afmSourceBar")
        self._source_bar.setDrawBase(False)
        try:
            self._source_bar.setExpanding(True)
        except Exception:
            pass
        self._source_bar.addTab(u"公盘文件")
        self._source_bar.addTab(u"本地文件")
        self._source_bar.currentChanged.connect(self._on_source_tab_changed)
        simple_lay.addWidget(self._source_bar)

        self._stack.addWidget(self._simple_page)

        self._full_widget = FullModeWidget()
        self._full_widget.file_activated.connect(self._open_file)
        self._full_widget.file_context.connect(self._show_file_menu)
        self._stack.addWidget(self._full_widget)

        root.addWidget(self._stack, 1)

        self._status = QtWidgets.QLabel(u"")
        self._status.setStyleSheet(u"color:#888; font-size:11px;")
        root.addWidget(self._status)

    def _restore_state(self):
        mode = _as_text(self._config.get(u"display_mode", u"simple"))
        if mode == u"full":
            self._mode_full.setChecked(True)
        else:
            self._mode_simple.setChecked(True)

        source = _as_text(self._config.get(u"last_source_tab", u"public"))
        combat = _as_text(self._config.get(u"last_combat_tab", u"indoor"))

        self._source_bar.blockSignals(True)
        self._combat_bar.blockSignals(True)
        try:
            self._source_bar.setCurrentIndex(1 if source == u"local" else 0)
            self._combat_bar.setCurrentIndex(1 if combat == u"outdoor" else 0)
        finally:
            self._source_bar.blockSignals(False)
            self._combat_bar.blockSignals(False)

        self._on_mode_changed()

    def _on_mode_changed(self):
        is_full = self._mode_full.isChecked()
        self._stack.setCurrentWidget(self._full_widget if is_full else self._simple_page)
        self._config[u"display_mode"] = u"full" if is_full else u"simple"
        save_config(self._config)
        if is_full:
            self._full_widget.set_root_path(NAS_BASE)
        else:
            self._simple_widget.set_view_context(
                self._config.get(u"last_source_tab", u"public"),
                self._config.get(u"last_combat_tab", u"indoor"),
                reload_categories=True,
            )

    def _on_source_tab_changed(self, index):
        key = u"local" if index == 1 else u"public"
        self._config[u"last_source_tab"] = key
        save_config(self._config)
        self._simple_widget.set_source_tab(key)

    def _on_combat_tab_changed(self, index):
        key = COMBAT_TABS[index][0] if 0 <= index < len(COMBAT_TABS) else u"indoor"
        self._config[u"last_combat_tab"] = key
        save_config(self._config)
        self._simple_widget.set_combat_tab(key)

    def _on_set_local_root(self):
        self._simple_widget.set_local_root()

    def _on_simple_config_changed(self):
        self._config = self._simple_widget.get_config()
        save_config(self._config)

    def _set_status(self, msg):
        self._status.setText(_as_text(msg))

    def _on_toggle_sync_on_open(self, checked):
        self._config[u"open_public_sync_to_local"] = bool(checked)
        save_config(self._config)

    def _switch_to_local_tab_keep_nav(self):
        self._config[u"last_source_tab"] = u"local"
        save_config(self._config)
        self._source_bar.blockSignals(True)
        try:
            self._source_bar.setCurrentIndex(1)
        finally:
            self._source_bar.blockSignals(False)
        self._simple_widget.set_source_tab(u"local", keep_navigation=True)

    def _open_file(self, path):
        path = _as_text(path)
        open_path = path
        synced_from_public = False

        if (
            self._config.get(u"open_public_sync_to_local")
            and self._stack.currentWidget() == self._simple_page
            and self._simple_widget.get_source_tab() == u"public"
        ):
            ok, result = self._simple_widget.sync_file_to_local(path)
            if not ok:
                QtWidgets.QMessageBox.warning(self, u"同步失败", result)
                return
            local_path = _as_text(result)
            if not local_path or not os.path.isfile(local_path):
                QtWidgets.QMessageBox.warning(self, u"打开失败", u"本地文件未生成")
                return
            open_path = local_path
            self._switch_to_local_tab_keep_nav()
            synced_from_public = True

        ok, err = open_max_file(open_path)
        if ok:
            msg = u"已打开: {0}".format(os.path.basename(open_path))
            if synced_from_public:
                msg += u"（已从公盘同步到本地）"
            self._set_status(msg)
        else:
            QtWidgets.QMessageBox.warning(self, u"打开失败", err)

    def _show_file_menu(self, path, global_pos):
        path = _as_text(path)
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        open_act = menu.addAction(u"打开")
        open_folder_act = menu.addAction(u"打开文件夹")
        history_act = menu.addAction(u"查看历史文件")
        public_update = None
        open_public_latest_act = None
        if (
            self._stack.currentWidget() == self._simple_page
            and self._simple_widget.get_source_tab() == u"local"
        ):
            public_update = self._simple_widget.public_update_for_local_file(path)
            if public_update:
                open_public_latest_act = menu.addAction(u"打开公盘最新版本")
        sync_act = None
        if (
            self._stack.currentWidget() == self._simple_page
            and self._simple_widget.get_source_tab() == u"public"
        ):
            sync_act = menu.addAction(u"同步到本地")
        rename_act = menu.addAction(u"重命名")
        delete_act = menu.addAction(u"删除")
        action = menu.exec_(global_pos)
        if action == open_act:
            self._open_file(path)
        elif action == open_folder_act:
            ok, err = open_file_folder(path)
            if ok:
                self._set_status(u"已打开文件夹: {0}".format(os.path.dirname(path)))
            else:
                QtWidgets.QMessageBox.warning(self, u"打开失败", err)
        elif action == history_act:
            self._show_publish_history(path)
        elif (
            open_public_latest_act is not None
            and action == open_public_latest_act
        ):
            self._open_public_update(public_update)
        elif sync_act is not None and action == sync_act:
            ok, result = self._simple_widget.sync_file_to_local(path)
            if ok:
                self._set_status(
                    u"已同步到本地: {0}".format(os.path.basename(_as_text(result)))
                )
            else:
                QtWidgets.QMessageBox.warning(self, u"同步失败", result)
        elif action == rename_act:
            self._rename_file(path)
        elif action == delete_act:
            self._delete_file(path)

    def _show_publish_history(self, path):
        from core.publish_history import load_publish_history
        from ui.history_dialog import PublishHistoryDialog

        rows = load_publish_history(path)
        dialog = PublishHistoryDialog(path, rows, parent=self)
        dialog.open_requested.connect(self._open_history_file)
        dialog.exec_()

    def _open_history_file(self, path):
        path = _as_text(path)
        ok, err = open_max_file(path)
        if ok:
            self._set_status(u"已打开历史文件: {0}".format(os.path.basename(path)))
        else:
            QtWidgets.QMessageBox.warning(self, u"打开失败", err)

    def _rename_file(self, path):
        old_name = os.path.basename(path)
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, u"重命名", u"新文件名：", text=old_name
        )
        if not ok:
            return
        success, result = rename_max_file(path, new_name)
        if success:
            self._set_status(u"已重命名为: {0}".format(os.path.basename(result)))
            self._simple_widget._reload_files()
            self._full_widget._reload()
        else:
            QtWidgets.QMessageBox.warning(self, u"重命名失败", result)

    def _delete_file(self, path):
        answer = QtWidgets.QMessageBox.question(
            self,
            u"删除确认",
            u"确定删除文件？\n{0}".format(path),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        ok, err = delete_max_file(path)
        if ok:
            self._set_status(u"已删除")
            self._simple_widget._reload_files()
            self._full_widget._reload()
        else:
            QtWidgets.QMessageBox.warning(self, u"删除失败", err)

    def _select_public_update_path(self, update):
        update = update or {}
        stage_latest = update.get(u"stage_latest") or {}
        date_latest = update.get(u"date_latest") or {}
        if not update.get(u"conflict"):
            return _as_text(stage_latest.get(u"path", u""))

        choices = [
            public_choice_label(u"阶段最新", stage_latest),
            public_choice_label(u"日期最新", date_latest),
        ]
        selected, ok = QtWidgets.QInputDialog.getItem(
            self,
            u"选择公盘最新版本",
            u"公盘的阶段最新文件与日期最新文件不同，请选择要打开的文件：",
            choices,
            0,
            False,
        )
        if not ok:
            return u""
        index = choices.index(_as_text(selected))
        target = stage_latest if index == 0 else date_latest
        return _as_text(target.get(u"path", u""))

    def _open_public_update(self, update):
        public_path = self._select_public_update_path(update)
        if not public_path:
            return
        if not os.path.isfile(public_path):
            QtWidgets.QMessageBox.warning(
                self, u"打开失败", u"公盘文件不存在或当前无法访问：\n{0}".format(public_path)
            )
            return

        open_path = public_path
        synced_from_public = False
        if self._config.get(u"open_public_sync_to_local"):
            ok, result = self._simple_widget.sync_file_to_local(public_path)
            if not ok:
                QtWidgets.QMessageBox.warning(self, u"同步失败", result)
                return
            open_path = _as_text(result)
            if not open_path or not os.path.isfile(open_path):
                QtWidgets.QMessageBox.warning(self, u"打开失败", u"本地文件未生成")
                return
            self._switch_to_local_tab_keep_nav()
            synced_from_public = True

        ok, err = open_max_file(open_path)
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"打开失败", err)
            return
        if synced_from_public:
            self._set_status(
                u"已同步并打开公盘最新版本: {0}".format(os.path.basename(open_path))
            )
        else:
            self._set_status(
                u"已打开公盘最新版本: {0}".format(os.path.basename(open_path))
            )

    def _apply_styles(self):
        self.setStyleSheet(
            u"QDialog, QWidget { background:#2b2b2b; color:#d8d8d8; }"
            u"QLabel#afmMainTitle { font-size:14px; font-weight:bold; color:#d8d8d8; }"
            u"QFrame#afmColumnBody { background:#1e1e1e; border:1px solid #555555; }"
            u"QTabBar#afmSourceBar { background:transparent; }"
            u"QTabBar#afmSourceBar::tab {"
            u"  background:#3a3a3a; color:#c8c8c8; font-size:14px;"
            u"  min-width:180px; min-height:36px; padding:6px 28px; margin:4px 8px 2px 0;"
            u"  border:1px solid #777777; border-radius:4px;"
            u"}"
            u"QTabBar#afmSourceBar::tab:hover {"
            u"  background:#454545; color:#e8e8e8; border:1px solid #999999;"
            u"}"
            u"QTabBar#afmSourceBar::tab:selected {"
            u"  background:#5a5a5a; color:#ffffff; font-size:17px; font-weight:bold;"
            u"  border:2px solid #bbbbbb; border-radius:4px;"
            u"}"
            u"QTabBar#afmCombatBar { background:transparent; }"
            u"QTabBar#afmCombatBar::tab {"
            u"  background:#3a3a3a; color:#c8c8c8; font-size:11px;"
            u"  padding:4px 14px; margin-right:6px;"
            u"  border:1px solid #777777; border-radius:3px;"
            u"}"
            u"QTabBar#afmCombatBar::tab:hover {"
            u"  background:#454545; color:#e8e8e8; border:1px solid #999999;"
            u"}"
            u"QTabBar#afmCombatBar::tab:selected {"
            u"  background:#5a5a5a; color:#ffffff; font-size:11px; font-weight:bold;"
            u"  border:2px solid #bbbbbb; border-radius:3px;"
            u"}"
            u"QListWidget { background:transparent; border:none; outline:none; }"
            u"QListWidget::item {"
            u"  background:transparent; color:#f0f0f0;"
            u"  border:1px solid transparent; padding:3px 6px;"
            u"}"
            u"QListWidget::item:selected {"
            u"  background:#353535; color:#f0f0f0;"
            u"  border:1px solid #888888; border-radius:2px;"
            u"}"
            u"QListWidget::item:hover { background:#2a2a2a; }"
            u"QPushButton { background:#3d3d3d; color:#d8d8d8; border:1px solid #666; padding:4px 10px; border-radius:3px; }"
            u"QPushButton:hover { background:#4d4d4d; }"
            u"QMenu { background:#3a3a3a; color:#f0f0f0; border:1px solid #666666; padding:4px 0; }"
            u"QMenu::item { background:transparent; color:#f0f0f0; padding:6px 28px; }"
            u"QMenu::item:selected { background:#5a5a5a; color:#ffffff; }"
            u"QMenu::item:disabled { color:#777777; }"
            u"QMenu::separator { height:1px; background:#555555; margin:4px 8px; }"
            u"QRadioButton { color:#d8d8d8; spacing:6px; }"
            u"QTreeWidget { background:#1e1e1e; border:1px solid #555; color:#d8d8d8; }"
            u"QTreeWidget::item { background:transparent; border:1px solid transparent; }"
            u"QTreeWidget::item:selected { background:#353535; color:#f0f0f0; border:1px solid #888888; }"
            u"QSplitter#afmColumnSplitter::handle { background:transparent; width:6px; }"
            u"QScrollBar:vertical { background:#3d3d3d; width:10px; margin:0; border:none; }"
            u"QScrollBar:horizontal { background:#3d3d3d; height:10px; margin:0; border:none; }"
            u"QScrollBar::handle:vertical { background:#4a8fd4; min-height:28px; border-radius:4px; margin:1px; }"
            u"QScrollBar::handle:horizontal { background:#4a8fd4; min-width:28px; border-radius:4px; margin:1px; }"
            u"QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background:#6eb5ff; }"
            u"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,"
            u"QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:#3d3d3d; }"
            u"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,"
            u"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { background:#3d3d3d; border:none; }"
        )

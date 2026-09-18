# -*- coding: utf-8 -*-
"""简略显示模式：公盘/本地 + 局内/局外 + 三列导航。"""
from __future__ import division
import os

from PySide2 import QtWidgets, QtCore, QtGui

from core.paths import NAS_BASE, NAS_INDOOR_FOLDER, NAS_OUTDOOR_FOLDER
from core.file_scanner import (
    list_subdirs,
    get_character_files,
    list_local_categories,
    list_local_characters,
)
from core.local_sync import (
    sync_character_folder,
    sync_single_file,
    make_local_char_path,
    make_public_char_path,
    local_path_for_public_file,
)
from core.config_store import mark_character_refreshed
from core.public_updates import (
    UPDATE_MARKER,
    annotate_local_files_with_public_updates,
)

try:
    _text_type = unicode
except NameError:
    _text_type = str

COMBAT_TABS = (
    (u"indoor", u"局内战斗", NAS_INDOOR_FOLDER),
    (u"outdoor", u"局外演出", NAS_OUTDOOR_FOLDER),
)

BG_COLUMN_EMPTY = u"#1e1e1e"
BG_COLUMN_FILLED = u"#3c3c3c"
TEXT_COLUMN_EMPTY = u"#777777"
TEXT_COLUMN_FILLED = u"#f0f0f0"
TEXT_COLUMN_HINT = u"#999999"

FILE_NAME_ROLE = QtCore.Qt.UserRole + 10
FILE_DATE_ROLE = QtCore.Qt.UserRole + 11
FILE_OWNER_ROLE = QtCore.Qt.UserRole + 12
FILE_VERSION_ROLE = QtCore.Qt.UserRole + 13
FILE_REVISION_ROLE = QtCore.Qt.UserRole + 14
FILE_UPDATE_ROLE = QtCore.Qt.UserRole + 15

CONTEXT_MENU_STYLE = (
    u"QMenu { background:#3a3a3a; color:#f0f0f0; border:1px solid #666666; padding:4px 0; }"
    u"QMenu::item { background:transparent; color:#f0f0f0; padding:6px 28px; }"
    u"QMenu::item:selected { background:#5a5a5a; color:#ffffff; }"
    u"QMenu::item:disabled { color:#777777; }"
    u"QMenu::separator { height:1px; background:#555555; margin:4px 8px; }"
)


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return _text_type(repr(value))


class _ColumnList(QtWidgets.QListWidget):
    """单列列表，仅选中项高亮。"""

    def __init__(self, parent=None):
        super(_ColumnList, self).__init__(parent)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(False)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)


class _FileRowDelegate(QtWidgets.QStyledItemDelegate):
    """左侧文件名可截断，发布日期/负责人/版本固定在右侧对齐。"""

    def __init__(self, parent=None):
        super(_FileRowDelegate, self).__init__(parent)
        self._date_width = 0
        self._owner_width = 0
        self._version_width = 0
        self._revision_width = 0
        self._update_width = 0

    def _text_width(self, metrics, text):
        try:
            return metrics.horizontalAdvance(_as_text(text))
        except Exception:
            return metrics.width(_as_text(text))

    def set_field_texts(self, updates, dates, owners, versions, revisions):
        widget = self.parent()
        metrics = widget.fontMetrics() if widget is not None else QtGui.QFontMetrics(QtGui.QFont())
        self._update_width = max([self._text_width(metrics, x) for x in updates] or [0])
        self._date_width = max([self._text_width(metrics, x) for x in dates] or [0])
        self._owner_width = max([self._text_width(metrics, x) for x in owners] or [0])
        self._version_width = max([self._text_width(metrics, x) for x in versions] or [0])
        self._revision_width = max([self._text_width(metrics, x) for x in revisions] or [0])
        if widget is not None:
            widget.viewport().update()

    def _elide_filename(self, metrics, text, width):
        text = _as_text(text)
        width = max(0, int(width))
        if self._text_width(metrics, text) <= width:
            return text
        ellipsis = u"..."
        ellipsis_width = self._text_width(metrics, ellipsis)
        if width < ellipsis_width:
            return u""
        available = width - ellipsis_width
        low = 0
        high = len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self._text_width(metrics, text[:middle]) <= available:
                low = middle
            else:
                high = middle - 1
        return text[:low] + ellipsis

    def paint(self, painter, option, index):
        file_name = _as_text(index.data(FILE_NAME_ROLE))
        date_text = _as_text(index.data(FILE_DATE_ROLE))
        owner_text = _as_text(index.data(FILE_OWNER_ROLE))
        version_text = _as_text(index.data(FILE_VERSION_ROLE))
        revision_text = _as_text(index.data(FILE_REVISION_ROLE))
        update_text = _as_text(index.data(FILE_UPDATE_ROLE))
        if not file_name or not (
            update_text or date_text or owner_text or version_text or revision_text
        ):
            super(_FileRowDelegate, self).paint(painter, option, index)
            return

        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = u""
        widget = opt.widget or self.parent()
        style = widget.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, widget)
        text_rect = style.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemText, opt, widget
        )

        painter.save()
        painter.setFont(opt.font)
        color_role = (
            QtGui.QPalette.HighlightedText
            if opt.state & QtWidgets.QStyle.State_Selected
            else QtGui.QPalette.Text
        )
        painter.setPen(opt.palette.color(color_role))
        align_right = QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
        align_left = QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter

        right = text_rect.right() + 1
        revision_rect = QtCore.QRect(
            right - self._revision_width,
            text_rect.top(),
            self._revision_width,
            text_rect.height(),
        )
        right = revision_rect.left()
        version_rect = QtCore.QRect(
            right - self._version_width,
            text_rect.top(),
            self._version_width,
            text_rect.height(),
        )
        right = version_rect.left()
        owner_rect = QtCore.QRect(
            right - self._owner_width,
            text_rect.top(),
            self._owner_width,
            text_rect.height(),
        )
        right = owner_rect.left()
        date_rect = QtCore.QRect(
            right - self._date_width,
            text_rect.top(),
            self._date_width,
            text_rect.height(),
        )
        right = date_rect.left()
        update_rect = QtCore.QRect(
            right - self._update_width,
            text_rect.top(),
            self._update_width,
            text_rect.height(),
        )
        gap_width = self._text_width(opt.fontMetrics, u"  ")
        name_width = max(0, update_rect.left() - gap_width - text_rect.left())
        name_rect = QtCore.QRect(
            text_rect.left(), text_rect.top(), name_width, text_rect.height()
        )

        painter.drawText(update_rect, align_right, update_text)
        painter.drawText(date_rect, align_right, date_text)
        painter.drawText(owner_rect, align_right, owner_text)
        # 版本字段内部左对齐：初版/终版/监修从同一位置开始，
        # 监修版本号占用短阶段名右侧的预留空间。
        painter.drawText(version_rect, align_left, version_text)
        painter.drawText(revision_rect, align_right, revision_text)
        painter.drawText(
            name_rect,
            align_left,
            self._elide_filename(opt.fontMetrics, file_name, name_width),
        )
        painter.restore()


class SimpleModeWidget(QtWidgets.QWidget):
    file_activated = QtCore.Signal(str)
    file_context = QtCore.Signal(str, object)
    config_changed = QtCore.Signal()
    status_message = QtCore.Signal(str)

    def __init__(self, parent=None):
        super(SimpleModeWidget, self).__init__(parent)
        self._config = {}
        self._source_tab = u"public"
        self._combat_key = u"indoor"
        self._combat_folder = NAS_INDOOR_FOLDER
        self._selected_category = u""
        self._selected_character = u""
        self._column_bodies = []
        self._public_update_map = {}
        self._build_ui()

    def get_source_tab(self):
        return self._source_tab

    def set_config(self, cfg, reload_categories=True):
        self._config = dict(cfg or {})
        if reload_categories:
            self._reload_categories()

    def set_view_context(self, source_tab, combat_key, reload_categories=True):
        """一次恢复来源/战斗页签，避免启动时重复访问公盘。"""
        self._source_tab = u"local" if source_tab == u"local" else u"public"
        for key, label, folder in COMBAT_TABS:
            if key == combat_key:
                self._combat_key = key
                self._combat_folder = folder
                break
        self._selected_category = u""
        self._selected_character = u""
        if reload_categories:
            self._reload_categories()
        else:
            self._category_list.clear()
            self._character_list.clear()
            self._file_list.clear()
            self._sync_all_column_fills()
        self._update_local_path_status()

    def get_config(self):
        return dict(self._config)

    def set_source_tab(self, tab_key, keep_navigation=False):
        self._source_tab = tab_key
        if keep_navigation:
            category = self._selected_category
            character = self._selected_character
            self._reload_categories()
            self.restore_navigation(category, character)
            self._update_local_path_status()
            return
        self._selected_category = u""
        self._selected_character = u""
        self._reload_categories()
        self._update_local_path_status()

    def set_combat_tab(self, combat_key):
        for key, label, folder in COMBAT_TABS:
            if key == combat_key:
                self._combat_key = key
                self._combat_folder = folder
                break
        self._selected_category = u""
        self._selected_character = u""
        self._reload_categories()

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setObjectName(u"afmColumnSplitter")
        splitter.setHandleWidth(6)

        self._category_list = _ColumnList()
        self._category_list.setObjectName(u"afmCategoryList")
        self._category_list.currentItemChanged.connect(self._on_category_changed)
        self._category_body = self._wrap_list_body(self._category_list)
        splitter.addWidget(self._category_body)

        self._character_list = _ColumnList()
        self._character_list.setObjectName(u"afmCharacterList")
        self._character_list.currentItemChanged.connect(self._on_character_changed)
        self._character_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._character_list.customContextMenuRequested.connect(
            self._on_character_context_menu
        )
        self._character_body = self._wrap_list_body(self._character_list)
        splitter.addWidget(self._character_body)

        self._file_list = _ColumnList()
        self._file_list.setObjectName(u"afmFileList")
        self._file_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._file_delegate = _FileRowDelegate(self._file_list)
        self._file_list.setItemDelegate(self._file_delegate)
        self._file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
        self._file_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._file_list.customContextMenuRequested.connect(self._on_file_context_menu)
        self._file_body = self._wrap_list_body(self._file_list)
        splitter.addWidget(self._file_body)

        self._column_bodies = (
            (self._category_body, self._category_list),
            (self._character_body, self._character_list),
            (self._file_body, self._file_list),
        )

        splitter.setSizes([180, 180, 360])
        lay.addWidget(splitter, 1)
        self._update_local_path_status()
        self._sync_all_column_fills()

    def _wrap_list_body(self, list_widget):
        body = QtWidgets.QFrame()
        body.setObjectName(u"afmColumnBody")
        body_lay = QtWidgets.QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        body_lay.addWidget(list_widget, 1)
        return body

    def _list_has_content(self, list_widget):
        if list_widget.count() <= 0:
            return False
        if list_widget.count() == 1:
            item = list_widget.item(0)
            if item is not None and not (item.flags() & QtCore.Qt.ItemIsSelectable):
                return False
        return True

    def _column_has_visible_content(self, list_widget):
        if list_widget.objectName() == u"afmCategoryList" and list_widget.count() > 0:
            return True
        return self._list_has_content(list_widget)

    def _apply_column_fill(self, body, list_widget):
        has_content = self._column_has_visible_content(list_widget)
        bg = BG_COLUMN_FILLED if has_content else BG_COLUMN_EMPTY
        text_color = TEXT_COLUMN_FILLED if has_content else TEXT_COLUMN_EMPTY
        body.setStyleSheet(
            u"QFrame#afmColumnBody { background:%s; border:1px solid #555555; }"
            u"QListWidget { background:%s; border:none; outline:none; color:%s; }"
            u"QListWidget::item {"
            u"  background:transparent; color:%s;"
            u"  border:1px solid transparent; padding:3px 6px;"
            u"}"
            u"QListWidget::item:selected {"
            u"  background:#353535; color:#ffffff;"
            u"  border:1px solid #888888; border-radius:2px;"
            u"}"
            u"QListWidget::item:hover { background:#2a2a2a; }"
            % (bg, bg, text_color, text_color)
        )

    def _sync_all_column_fills(self):
        for body, list_widget in self._column_bodies:
            self._apply_column_fill(body, list_widget)

    def _update_local_path_status(self):
        local_root = self._local_root()
        if self._source_tab == u"local" and not local_root:
            self.status_message.emit(u"本地根路径：未设置")
        elif self._source_tab == u"local":
            self.status_message.emit(u"本地根路径：{0}".format(local_root))

    def set_local_root(self):
        start = _as_text(self._config.get(u"local_root", u""))
        path = QtWidgets.QFileDialog.getExistingDirectory(self, u"选择本地动作资产根目录", start)
        if path:
            self._config[u"local_root"] = path
            for _, _, folder in COMBAT_TABS:
                try:
                    os.makedirs(os.path.join(path, folder))
                except Exception:
                    pass
            self.config_changed.emit()
            self._update_local_path_status()
            self._reload_categories()

    def _public_combat_path(self):
        return os.path.join(NAS_BASE, self._combat_folder)

    def _local_root(self):
        return _as_text(self._config.get(u"local_root", u""))

    def _combat_path(self):
        """公盘标签读公盘；本地标签读本地已同步目录。"""
        if self._source_tab == u"local":
            local_root = self._local_root()
            if not local_root:
                return u""
            return os.path.join(local_root, self._combat_folder)
        return self._public_combat_path()

    def _list_categories(self):
        combat_path = self._combat_path()
        if not combat_path or not os.path.isdir(combat_path):
            return []
        if self._source_tab == u"local":
            return list_local_categories(combat_path)
        return list_subdirs(combat_path)

    def _list_characters(self, category):
        category = _as_text(category)
        if not category:
            return []
        category_path = os.path.join(self._combat_path(), category)
        if not os.path.isdir(category_path):
            return []
        if self._source_tab == u"local":
            return list_local_characters(category_path)
        return list_subdirs(category_path)

    def _char_path(self):
        if not self._selected_category or not self._selected_character:
            return u""
        if self._source_tab == u"public":
            return os.path.join(
                self._public_combat_path(),
                self._selected_category,
                self._selected_character,
            )
        local_root = self._local_root()
        if not local_root:
            return u""
        return make_local_char_path(
            local_root,
            self._combat_folder,
            self._selected_category,
            self._selected_character,
        )

    def _reload_categories(self):
        self._category_list.blockSignals(True)
        self._character_list.blockSignals(True)
        self._file_list.blockSignals(True)
        self._category_list.clear()
        self._character_list.clear()
        self._file_list.clear()
        self._category_list.blockSignals(False)
        self._character_list.blockSignals(False)
        self._file_list.blockSignals(False)

        combat_path = self._combat_path()
        if self._source_tab == u"local" and not self._local_root():
            self.status_message.emit(u"请先设置本地根路径")
            self._sync_all_column_fills()
            return
        if self._source_tab == u"local" and (
            not combat_path or not os.path.isdir(combat_path)
        ):
            self.status_message.emit(u"暂无本地同步文件")
            self._sync_all_column_fills()
            return
        if self._source_tab == u"public" and (
            not combat_path or not os.path.isdir(combat_path)
        ):
            self._sync_all_column_fills()
            return

        for name in self._list_categories():
            item = QtWidgets.QListWidgetItem(name)
            item.setData(QtCore.Qt.UserRole, name)
            self._category_list.addItem(item)
        self._sync_all_column_fills()

    def _on_category_changed(self, current, previous):
        self._character_list.clear()
        self._file_list.clear()
        if current is None:
            self._selected_category = u""
            self._sync_all_column_fills()
            return
        self._selected_category = _as_text(current.data(QtCore.Qt.UserRole))
        for name in self._list_characters(self._selected_category):
            item = QtWidgets.QListWidgetItem(name)
            item.setData(QtCore.Qt.UserRole, name)
            self._character_list.addItem(item)
        self._sync_all_column_fills()

    def _on_character_changed(self, current, previous):
        self._file_list.clear()
        if current is None:
            self._selected_character = u""
            self._sync_all_column_fills()
            return
        self._selected_character = _as_text(current.data(QtCore.Qt.UserRole))
        self._reload_files()

    def _reload_files(self):
        self._file_list.clear()
        self._public_update_map = {}
        self._file_delegate.set_field_texts([], [], [], [], [])
        if self._source_tab == u"local" and not self._local_root():
            self._sync_all_column_fills()
            return
        char_path = self._char_path()
        if not char_path or not os.path.isdir(char_path):
            if self._source_tab == u"local" and self._selected_character:
                hint = QtWidgets.QListWidgetItem(u"（右键角色 → 同步公盘文件）")
                hint.setFlags(QtCore.Qt.NoItemFlags)
                hint.setForeground(QtGui.QBrush(QtGui.QColor(TEXT_COLUMN_HINT)))
                self._file_list.addItem(hint)
            self._sync_all_column_fills()
            return
        files = get_character_files(char_path, allow_files=True)
        if self._source_tab == u"local":
            public_char_path = make_public_char_path(
                NAS_BASE,
                self._combat_folder,
                self._selected_category,
                self._selected_character,
            )
            files = annotate_local_files_with_public_updates(
                files, public_char_path
            )
        if not files and self._source_tab == u"local":
            hint = QtWidgets.QListWidgetItem(u"（右键角色 → 同步公盘文件）")
            hint.setFlags(QtCore.Qt.NoItemFlags)
            hint.setForeground(QtGui.QBrush(QtGui.QColor(TEXT_COLUMN_HINT)))
            self._file_list.addItem(hint)
            self._sync_all_column_fills()
            return
        update_texts = [
            u"[{0}]".format(UPDATE_MARKER)
            if x.get(u"public_update_available") else u""
            for x in files
        ]
        date_texts = [u"[{0}]".format(_as_text(x.get(u"date_label", u""))) for x in files]
        owner_texts = [u"[{0}]".format(_as_text(x.get(u"publisher", u""))) for x in files]
        version_texts = [u"[{0}]".format(_as_text(x.get(u"version_label", u""))) for x in files]
        revision_texts = [
            u"[{0}]".format(_as_text(x.get(u"publish_revision_label", u"")))
            if _as_text(x.get(u"publish_revision_label", u"")) else u""
            for x in files
        ]
        self._file_delegate.set_field_texts(
            update_texts, date_texts, owner_texts, version_texts, revision_texts
        )
        for index, info in enumerate(files):
            file_name = os.path.splitext(_as_text(info[u"name"]))[0]
            label = u"{0}{1}{2}{3}{4}{5}".format(
                file_name,
                update_texts[index],
                date_texts[index],
                owner_texts[index],
                version_texts[index],
                revision_texts[index],
            )
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, info[u"path"])
            item.setData(FILE_NAME_ROLE, file_name)
            item.setData(FILE_UPDATE_ROLE, update_texts[index])
            item.setData(FILE_DATE_ROLE, date_texts[index])
            item.setData(FILE_OWNER_ROLE, owner_texts[index])
            item.setData(FILE_VERSION_ROLE, version_texts[index])
            item.setData(FILE_REVISION_ROLE, revision_texts[index])
            item.setToolTip(_as_text(label))
            self._file_list.addItem(item)
            if info.get(u"public_update_available"):
                key = os.path.normcase(os.path.abspath(_as_text(info[u"path"])))
                self._public_update_map[key] = info.get(u"public_update")
        self._sync_all_column_fills()

    def public_update_for_local_file(self, local_file_path):
        """返回本地列表缓存的公盘更新候选；其他来源始终为空。"""
        if self._source_tab != u"local":
            return None
        try:
            key = os.path.normcase(os.path.abspath(_as_text(local_file_path)))
        except Exception:
            return None
        return self._public_update_map.get(key)

    def sync_file_to_local(self, public_file_path):
        local_root = self._local_root()
        if not local_root:
            return False, u"请先设置本地根路径"
        if not self._selected_category or not self._selected_character:
            return False, u"请先选择分类和角色"
        ok, result = sync_single_file(
            public_file_path,
            local_root,
            self._combat_folder,
            self._selected_category,
            self._selected_character,
        )
        if ok:
            self._config = mark_character_refreshed(
                self._config,
                self._combat_folder,
                self._selected_category,
                self._selected_character,
            )
            self.config_changed.emit()
            if self._source_tab == u"local":
                category = self._selected_category
                character = self._selected_character
                self._reload_categories()
                self.restore_navigation(category, character)
        return ok, result

    def local_path_for_public_file(self, public_file_path):
        return local_path_for_public_file(
            public_file_path,
            self._local_root(),
            self._combat_folder,
            self._selected_category,
            self._selected_character,
        )

    def _select_list_item_by_role(self, list_widget, role_value):
        role_value = _as_text(role_value)
        if not role_value:
            return False
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item is None:
                continue
            if _as_text(item.data(QtCore.Qt.UserRole)) == role_value:
                list_widget.setCurrentItem(item)
                return True
        return False

    def restore_navigation(self, category, character):
        category = _as_text(category)
        character = _as_text(character)
        self._category_list.blockSignals(True)
        self._character_list.blockSignals(True)
        try:
            self._select_list_item_by_role(self._category_list, category)
            self._selected_category = category
            if category:
                self._character_list.clear()
                self._file_list.clear()
                for name in self._list_characters(category):
                    item = QtWidgets.QListWidgetItem(name)
                    item.setData(QtCore.Qt.UserRole, name)
                    self._character_list.addItem(item)
            self._select_list_item_by_role(self._character_list, character)
            self._selected_character = character
        finally:
            self._category_list.blockSignals(False)
            self._character_list.blockSignals(False)
        self._reload_files()
        self._sync_all_column_fills()

    def sync_character_from_public(self, category=None, character=None):
        category = _as_text(category or self._selected_category)
        character = _as_text(character or self._selected_character)
        local_root = self._local_root()
        if not local_root:
            return False, u"请先设置本地根路径"
        if not category or not character:
            return False, u"请先选择分类和角色"
        public_path = make_public_char_path(
            NAS_BASE,
            self._combat_folder,
            category,
            character,
        )
        local_path = make_local_char_path(
            local_root,
            self._combat_folder,
            category,
            character,
        )
        ok, msg = sync_character_folder(public_path, local_path)
        if ok:
            self._selected_category = category
            self._selected_character = character
            self._config = mark_character_refreshed(
                self._config,
                self._combat_folder,
                category,
                character,
            )
            self.config_changed.emit()
            if self._source_tab == u"local":
                self._reload_categories()
                self.restore_navigation(category, character)
            else:
                self._reload_files()
        return ok, msg

    def _on_character_context_menu(self, pos):
        item = self._character_list.itemAt(pos)
        if item is None:
            return
        self._character_list.setCurrentItem(item)
        character = _as_text(item.data(QtCore.Qt.UserRole))
        if not self._selected_category or not character:
            return
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        sync_act = menu.addAction(u"同步公盘文件")
        action = menu.exec_(self._character_list.mapToGlobal(pos))
        if action == sync_act:
            ok, msg = self.sync_character_from_public(
                self._selected_category, character
            )
            if ok:
                self.status_message.emit(msg)
            else:
                QtWidgets.QMessageBox.warning(self, u"同步失败", msg)

    def _on_file_double_clicked(self, item):
        path = _as_text(item.data(QtCore.Qt.UserRole))
        if path:
            self.file_activated.emit(path)

    def _on_file_context_menu(self, pos):
        item = self._file_list.itemAt(pos)
        if item is None:
            return
        path = _as_text(item.data(QtCore.Qt.UserRole))
        if path:
            self.file_context.emit(path, self._file_list.mapToGlobal(pos))

    def current_file_path(self):
        item = self._file_list.currentItem()
        if item is None:
            return u""
        return _as_text(item.data(QtCore.Qt.UserRole))

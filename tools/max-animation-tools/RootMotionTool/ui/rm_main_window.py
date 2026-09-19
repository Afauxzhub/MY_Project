# -*- coding: utf-8 -*-
"""
主窗口
动态折叠布局（QScrollArea）+ 局内/局外双模式切换
"""
from __future__ import print_function, division
import os
import io
import json
import glob
import subprocess
import tempfile
import datetime
import shutil
import hashlib
import traceback

from PySide2 import QtWidgets, QtCore, QtGui

# ── 崩溃诊断日志（崩溃后文件仍在，可读取） ─────────────────────────
_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DBG_LOG = os.path.join(_TOOL_DIR, u"crash_debug.log")
_PUBLISH_LOG = os.path.join(_TOOL_DIR, u"publish_debug.log")

def _dbg(msg):
    try:
        with open(_DBG_LOG, "a") as _f:
            _f.write(msg + "\n")
            _f.flush()
    except Exception:
        pass


def _publog(msg):
    try:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with io.open(_PUBLISH_LOG, "a", encoding="utf-8") as _f:
            _f.write(u"[{0}] {1}\n".format(_as_text(stamp), _as_text(msg)))
            _f.flush()
    except Exception:
        pass

# pymxs 延迟初始化：避免模块导入时立即触发 Max API 调用
# （在部分 Max 版本中，过早调用 pymxs.runtime 会导致崩溃）
def _get_rt():
    import pymxs
    return pymxs.runtime

rt = None  # 在 MainWindow.__init__ 中初始化

try:
    _text_type = unicode
except NameError:
    _text_type = str


def _as_text(value):
    """转为 unicode 文本；Python 2 下勿对 Exception 等直接 str()，否则会触发 ascii 编码错误。"""
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    import sys
    if sys.version_info[0] < 3 and isinstance(value, str):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("gbk", "replace")
    if sys.version_info[0] >= 3:
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return value.decode("utf-8", "replace")
        try:
            return str(value)
        except Exception:
            return repr(value)
    if isinstance(value, BaseException):
        parts = []
        for arg in getattr(value, "args", ()) or ():
            parts.append(_as_text(arg))
        return _text_type(value.__class__.__name__) + u": " + u", ".join(parts)
    try:
        return _text_type(value)
    except UnicodeEncodeError:
        try:
            return repr(value).decode("utf-8", "replace")
        except Exception:
            return u"<unprintable>"
    except Exception:
        pass
    try:
        b = str(value)
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return b.decode("gbk", "replace")
    except UnicodeEncodeError:
        try:
            return repr(value).decode("utf-8", "replace")
        except Exception:
            return u"<unprintable>"
    except Exception:
        return u"<unprintable>"


def _as_fs_path(path):
    """路径统一为 unicode，避免 Py2 下 os.path.join(unicode, str) 对中文路径报 UnicodeDecodeError。"""
    return _as_text(path)


_BINDING_HIERARCHY_WARNING = u"绑定层级被修改，无法导出，请检查文件后重新尝试。"


def _is_binding_hierarchy_export_error(error):
    """Recognize both the current friendly throw and older cached backend text."""
    text = _as_text(error)
    return (
        _BINDING_HIERARCHY_WARNING in text
        or u"ProxyRoot duplicate export hierarchy paths" in text
    )


def _format_proxy_transform_export_error(error):
    """Translate an existing ProxyRoot hard failure; never adds a new gate."""
    try:
        from core.rm_export_error_formatter import format_proxy_transform_restore_error
        position_tolerance = 0.01
        try:
            if rt is not None:
                position_tolerance = float(rt.units.decodeValue(u"0.01cm"))
        except Exception:
            pass
        return format_proxy_transform_restore_error(
            _as_text(error), position_tolerance=position_tolerance
        )
    except Exception:
        return None


def _format_task_local_curve_export_error(error):
    """Summarize an existing split-FBX curve gate without changing the gate."""
    try:
        from core.rm_export_error_formatter import format_task_local_curve_export_error
        return format_task_local_curve_export_error(_as_text(error))
    except Exception:
        return None


def _format_publish_filename_too_long_error(error, max_file_path):
    """Summarize an existing public-backup path failure without adding a gate."""
    try:
        from core.rm_export_error_formatter import format_publish_filename_too_long_error
        return format_publish_filename_too_long_error(
            error, _as_text(max_file_path)
        )
    except Exception:
        return None


def _show_publish_error(parent, title, message, error=None, context=None,
                        traceback_text=None, warning=False):
    from ui.op_error_report_dialog import show_reportable_error

    publish_context = {
        u"operation": u"publish",
        u"window_mode": getattr(parent, u"_window_mode", u""),
        u"publish_engine": getattr(parent, u"_com_restore_engine", u""),
    }
    publish_context.update(context or {})
    return show_reportable_error(
        parent=parent,
        title=title,
        message=message,
        tool_id=u"publish",
        tool_name=u"Animation FBX 发布工具",
        config=getattr(parent, u"_config", {}) or {},
        exception=error,
        traceback_text=traceback_text,
        context=publish_context,
        attachments=[_PUBLISH_LOG, _DBG_LOG],
        tool_version=getattr(parent, u"_com_restore_engine", u""),
        warning=warning,
    )


def _show_animation_data_export_error(parent, message, error=None,
                                      traceback_text=None, context=None):
    return _show_publish_error(
        parent,
        u"动画数据错误，无法导出",
        message,
        error=error,
        traceback_text=traceback_text,
        context=context,
        warning=True,
    )

# ──────────────────────────────────────────────────────────────────
# 默认配置
# ──────────────────────────────────────────────────────────────────

DEFAULT_DEV_MARKER_FILENAME = u"AnimationTools_DevMachine.flag"

DEFAULT_CONFIG = {
    u"unity_root": u"",
    u"nas_base":   u"",
    u"error_report_root": u"",
    u"character_rig_root": u"",
    u"rig_update_cleanup_packages": False,
    u"rig_update_keep_reports": True,
    u"rig_update_ignore_non_bip_errors": False,
    u"rig_update_skip_missing_constraint_targets": False,
    u"rig_update_allow_preflight_blockers": False,
    u"rig_update_outgame_characters": [],
    u"dev_machine_marker_filename": DEFAULT_DEV_MARKER_FILENAME,
    u"dev_machine_project_override": u"",
    u"auto_copy_unity":          True,
    u"auto_backup_nas":          True,
    u"auto_focus_unity":         True,
    u"open_folder_after_export": True,
    u"backup_stage":             u"初版",
    u"backup_version":           u"",
    u"publisher_name":           u"",
    u"adv_force_keys":           True,
    u"adv_fix_rot":              True,
    u"adv_remove_initial_z":     True,
    u"adv_unlock_nodes":         True,
    u"adv_delete_temp_file":     True,
    u"adv_root_motion_debug_log": False,
    u"adv_export_weapon_state_mapping": True,
    u"category_folder_map": {
        u"Role":    u"Role",
        u"Monster": u"Monster",
        u"Elite":   u"Elite",
        u"Boss":    u"Boss",
        u"Npc":     u"Npc",
        u"Scene":   u"Scene",
    },
    u"module_folder_map": {
        u"UL":  u"Ultimate_skill",
        u"EN":  u"Entrance",
        u"RE":  u"Result",
        u"GA":  u"Gacha",
        u"DE":  u"Development",
        u"ER":  u"Enrage",
        u"CS":  u"Cinematic",
        u"QTE": u"QTE",
        u"DI":  u"Dialogue",
    },
    u"module_tag_map": {
        u"UL": u"角色配套",
        u"GA": u"角色配套",
        u"DE": u"角色配套",
        u"ER": u"角色配套",
        u"EN": u"剧情对话",
        u"RE": u"剧情对话",
        u"CS": u"剧情对话",
        u"QTE": u"剧情对话",
        u"DI": u"剧情对话",
    },
    u"outdoor_type_folder_map": {
        u"Role":    u"Role",
        u"Monster": u"Monster",
    },
    u"outdoor_asset_types": [u"Char", u"Prop", u"Cam"],
}

AIRHIT_SEGMENT_RANGES = {
    u"Rise_Start": (0, 4),
    u"Rise_End": (4, 10),
    u"Fall_Start": (10, 24),
    u"Fall_Loop": (150, 170),
    u"Bounce_Start": (24, 31),
    u"Bounce_End": (31, 38),
    u"Bounce_Loop": (180, 200),
    u"Land_Start": (38, 56),
    u"Land_Loop": (56, 76),
    u"Land_End": (76, 115),
}


# ──────────────────────────────────────────────────────────────────
# 可折叠分组组件
# ──────────────────────────────────────────────────────────────────

class CollapsibleGroup(QtWidgets.QWidget):
    """带折叠/展开按钮的分组容器"""

    def __init__(self, title, parent=None, expanded=False):
        super(CollapsibleGroup, self).__init__(parent)
        self.setObjectName(u"rmGroup")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(0)

        self._toggle = QtWidgets.QPushButton(
            (u"▼  " if expanded else u"▶  ") + title,
            self
        )
        self._toggle.setObjectName(u"rmGroupToggle")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)

        self._body = QtWidgets.QWidget(self)
        self._body.setObjectName(u"rmGroupBody")
        self._body.setVisible(expanded)

        layout.addWidget(self._toggle)
        layout.addWidget(self._body)

        self._title = title
        self._toggle.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked):
        self._body.setVisible(checked)
        self._toggle.setText((u"▼  " if checked else u"▶  ") + self._title)

    def body_widget(self):
        """Expose the body QWidget so callers can create layouts with it as
        parent, ensuring Qt immediately owns the layout and all its children.
        This prevents PySide2 Python 2.7 from GC-collecting C++ layout objects
        that Qt still holds (heap corruption / non-deterministic crash)."""
        return self._body

    def set_body_layout(self, body_layout):
        self._body.setLayout(body_layout)

    def is_expanded(self):
        return self._toggle.isChecked()


# ──────────────────────────────────────────────────────────────────
# 局外角色列表组件
# ──────────────────────────────────────────────────────────────────

class CharacterListWidget(QtWidgets.QWidget):
    """局外多角色勾选列表，支持一键重新扫描"""

    changed = QtCore.Signal()

    def __init__(self, parent=None):
        _dbg("[CHARLIST] 1 - start")
        super(CharacterListWidget, self).__init__(parent)
        _dbg("[CHARLIST] 2 - super init OK")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        _dbg("[CHARLIST] 3 - layout OK")

        self._list = QtWidgets.QListWidget()
        self._list.setObjectName(u"rmCharList")
        _dbg("[CHARLIST] 6 - QListWidget created")
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self._list.setAlternatingRowColors(False)
        self._list.setSpacing(2)
        self._list.setUniformItemSizes(True)
        self._list.setMouseTracking(True)
        self._list.setFocusPolicy(QtCore.Qt.NoFocus)
        self._list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.itemClicked.connect(self._clear_current_item)
        _dbg("[CHARLIST] 7 - setSelectionMode OK")
        self._list.setMinimumHeight(44)
        layout.addWidget(self._list)

        footer_widget = QtWidgets.QWidget(self)
        footer = QtWidgets.QHBoxLayout(footer_widget)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addStretch()
        self._refresh_btn = QtWidgets.QPushButton(u"刷新")
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.clicked.connect(self.refresh)
        footer.addWidget(self._refresh_btn)
        layout.addWidget(footer_widget)
        _dbg("[CHARLIST] 8 - done")

        self._char_data = []
        self._show_empty_state()

    def refresh(self):
        from core.rm_scene import collect_character_roots
        _dbg("[CHARLIST] refresh start")
        self._list.clear()
        try:
            self._char_data = collect_character_roots()
        except Exception as exc:
            self._char_data = []
            _dbg("[CHARLIST] refresh error: {0}".format(exc))
        _dbg("[CHARLIST] refresh count={0}".format(len(self._char_data)))
        for char in self._char_data:
            item = QtWidgets.QListWidgetItem(char[u"name"])
            item.setFlags(
                QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsUserCheckable
            )
            item.setForeground(QtGui.QColor(u"#dbe2ea"))
            item.setSizeHint(QtCore.QSize(0, 26))
            item.setCheckState(QtCore.Qt.Checked)
            item.setToolTip(u"Biped: {0}".format(char[u"bip"].name))
            self._list.addItem(item)
            _dbg("[CHARLIST] item: {0}".format(char[u"name"]))
        if not self._char_data:
            self._show_empty_state()
        self._update_list_height()
        self._clear_current_item()
        self.changed.emit()

    def get_checked_names(self):
        names = []
        for i in range(min(self._list.count(), len(self._char_data))):
            item = self._list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                names.append(self._char_data[i][u"name"])
        return names

    def get_selected_chars(self):
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == QtCore.Qt.Checked and i < len(self._char_data):
                result.append(self._char_data[i])
        return result

    def _show_empty_state(self):
        item = QtWidgets.QListWidgetItem(u"None")
        item.setFlags(QtCore.Qt.ItemIsEnabled)
        item.setForeground(QtGui.QColor(u"#8b93a6"))
        item.setSizeHint(QtCore.QSize(0, 26))
        self._list.addItem(item)
        self._update_list_height()

    def _update_list_height(self):
        row_count = max(1, self._list.count())
        visible_rows = min(row_count, 5)
        row_height = 30
        frame_padding = 14
        self._list.setMinimumHeight(frame_padding + visible_rows * row_height)
        self._list.setMaximumHeight(frame_padding + visible_rows * row_height)

    def _on_item_changed(self, item):
        if self._char_data:
            self.changed.emit()

    def _clear_current_item(self, *args):
        self._list.setCurrentRow(-1)


# ──────────────────────────────────────────────────────────────────
# 局外 Morpher / 变形器勾选列表
# ──────────────────────────────────────────────────────────────────

class MorpherListWidget(QtWidgets.QWidget):
    """扫描场景中含 Morpher 的模型，供局外导出手动勾选。"""

    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super(MorpherListWidget, self).__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        hint = QtWidgets.QLabel(u"勾选后将随当前局外动作一起导出 Shape/变形器动画。")
        hint.setWordWrap(True)
        hint.setStyleSheet(u"color: #98a2b3; font-size: 11px;")
        layout.addWidget(hint)

        self._list = QtWidgets.QListWidget()
        self._list.setObjectName(u"rmMorphList")
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self._list.setAlternatingRowColors(False)
        self._list.setSpacing(2)
        self._list.setUniformItemSizes(True)
        self._list.setMouseTracking(True)
        self._list.setFocusPolicy(QtCore.Qt.NoFocus)
        self._list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.itemClicked.connect(self._clear_current_item)
        self._list.setMinimumHeight(44)
        layout.addWidget(self._list)

        footer_widget = QtWidgets.QWidget(self)
        footer = QtWidgets.QHBoxLayout(footer_widget)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addStretch()
        self._refresh_btn = QtWidgets.QPushButton(u"刷新")
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.clicked.connect(self.refresh)
        footer.addWidget(self._refresh_btn)
        layout.addWidget(footer_widget)

        self._morph_data = []
        self._pending_checked_names = None
        self._show_empty_state()

    def refresh(self, preferred_checked_names=None):
        from core.rm_exporter import scan_scene_morpher_meshes

        if preferred_checked_names is None:
            preferred_checked_names = self.get_checked_names()
            if self._pending_checked_names is not None:
                preferred_checked_names = list(self._pending_checked_names)
        checked_set = set([_as_text(n) for n in (preferred_checked_names or [])])

        self._list.clear()
        try:
            self._morph_data = scan_scene_morpher_meshes()
        except Exception as exc:
            self._morph_data = []
            _dbg("[MORPHLIST] refresh error: {0}".format(exc))

        for entry in self._morph_data:
            name = _as_text(entry.get(u"name", u""))
            item = QtWidgets.QListWidgetItem(name)
            item.setFlags(
                QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsUserCheckable
            )
            item.setForeground(QtGui.QColor(u"#dbe2ea"))
            item.setSizeHint(QtCore.QSize(0, 26))
            # 默认不勾选，需动画师手动选择；恢复设置时按名字勾选。
            item.setCheckState(
                QtCore.Qt.Checked if name in checked_set else QtCore.Qt.Unchecked
            )
            item.setToolTip(u"Morpher: {0}".format(name))
            self._list.addItem(item)

        if not self._morph_data:
            self._show_empty_state()
        self._pending_checked_names = None
        self._update_list_height()
        self._clear_current_item()
        self.changed.emit()

    def set_pending_checked_names(self, names):
        self._pending_checked_names = [_as_text(n) for n in (names or [])]

    def get_checked_names(self):
        names = []
        for i in range(min(self._list.count(), len(self._morph_data))):
            item = self._list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                names.append(_as_text(self._morph_data[i].get(u"name", u"")))
        return names

    def get_selected_nodes(self):
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == QtCore.Qt.Checked and i < len(self._morph_data):
                node = self._morph_data[i].get(u"node")
                if node is not None:
                    result.append(node)
        return result

    def _show_empty_state(self):
        item = QtWidgets.QListWidgetItem(u"场景中未发现 Morpher 模型")
        item.setFlags(QtCore.Qt.ItemIsEnabled)
        item.setForeground(QtGui.QColor(u"#8b93a6"))
        item.setSizeHint(QtCore.QSize(0, 26))
        self._list.addItem(item)
        self._update_list_height()

    def _update_list_height(self):
        row_count = max(1, self._list.count())
        visible_rows = min(row_count, 5)
        row_height = 30
        frame_padding = 14
        self._list.setMinimumHeight(frame_padding + visible_rows * row_height)
        self._list.setMaximumHeight(frame_padding + visible_rows * row_height)

    def _on_item_changed(self, item):
        if self._morph_data:
            self.changed.emit()

    def _clear_current_item(self, *args):
        self._list.setCurrentRow(-1)


# ──────────────────────────────────────────────────────────────────
# 主窗口
# ──────────────────────────────────────────────────────────────────

_CONFIG_PATH = os.path.join(_TOOL_DIR, u"config", u"rm_config.json")
_INSTALL_ROOT = os.path.dirname(_TOOL_DIR)
_INSTALL_INI_PATH = os.path.join(_INSTALL_ROOT, u"ReferenceRigInstall.ini")


class MainWindow(QtWidgets.QDialog):

    def __init__(self, parent=None, mode=u"full", com_restore_engine=u"baselayer"):
        _dbg("=== MainWindow.__init__ START ===")
        self._window_mode = _as_text(mode or u"full")
        # baselayer/ProxyRoot is the official publisher. legacy is a hidden
        # emergency backup and must only be requested through its explicit API.
        engine = _as_text(com_restore_engine or u"baselayer").strip().lower()
        if engine not in (u"legacy", u"baselayer"):
            engine = u"baselayer"
        self._com_restore_engine = engine
        super(MainWindow, self).__init__(parent)
        self.setObjectName(u"rmWindow")
        _dbg("INIT-1: super().__init__ done")

        try:
            from anim_migration.ui.tab_binding_update import UI_VERSION as binding_ui_version
        except Exception:
            binding_ui_version = u""
        title_version = u" {0}".format(binding_ui_version) if binding_ui_version else u""
        self.setWindowTitle(u"Animation 动作工具{0} (Root Motion + 武器约束 + 绑定更新)".format(title_version))
        _dbg("INIT-2: setWindowTitle done")
        self.setMinimumSize(560, 760)
        _dbg("INIT-3: setMinimumWidth done")
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowStaysOnTopHint
        )
        _dbg("INIT-4: setWindowFlags done")

        self._config    = self._load_config()
        _dbg("INIT-5: _load_config done")
        self._bip_obj   = None
        self._root_obj  = None
        self._split_data = []
        self._segment_form_sync = False
        self._indoor_resume_pending = False
        self._indoor_resume_ctx = None
        self._wallhit_root_motion_active = False
        self._scene_signature = u""
        self._loading_publish_settings = False
        self._scene_watch_timer = None
        self._outdoor_panel = None
        self._outdoor_host = None
        self._char_list = None
        self._morpher_list = None
        self._outdoor_built = False
        _dbg("INIT-6: member vars set")

        self._build_ui()
        self._apply_window_mode()
        self._apply_styles()
        _dbg("INIT-7: _build_ui done")
        QtCore.QTimer.singleShot(0, self._deferred_max_init)
        _dbg("INIT-8: QTimer.singleShot done  -- __init__ complete")

    def _deferred_max_init(self):
        """Called once after show() via QTimer - safe point for pymxs init."""
        global rt
        rt = _get_rt()
        try:
            self._weapon_panel.bind_runtime(rt)
        except Exception:
            pass
        self._refresh_publish_state_from_scene()
        self._scene_watch_timer = QtCore.QTimer(self)
        self._scene_watch_timer.setInterval(1000)
        self._scene_watch_timer.timeout.connect(self._poll_scene_change)
        self._scene_watch_timer.start()
        self._refresh_dev_upload_button_visibility()

    def _refresh_publish_state_from_scene(self):
        """每次打开/聚焦发布工具时，按当前 max 重新检测并读取发布设置。"""
        global rt
        if rt is None:
            try:
                rt = _get_rt()
            except Exception:
                return False
        self._sync_scene_frame_ranges()
        self._auto_detect()
        self._apply_indoor_motion_defaults_from_scene_name()
        loaded = self._load_publish_settings_for_current_scene()
        self._apply_wallhit_root_motion_mode(self._is_wallhit_scene())
        self._update_preview()
        self._scene_signature = self._current_scene_signature()
        return loaded

    def _apply_window_mode(self):
        if self._window_mode != u"publish_only":
            return
        if self._com_restore_engine == u"baselayer":
            self.setWindowTitle(u"Animation FBX 发布工具")
        else:
            self.setWindowTitle(u"Animation FBX 发布工具（Legacy 备份）")
        for widget in (getattr(self, "_weapon_panel", None), getattr(self, "_binding_update_tab", None)):
            if widget is None:
                continue
            idx = self._main_tab.indexOf(widget)
            if idx >= 0:
                self._main_tab.removeTab(idx)
        if hasattr(self, "_publish_page"):
            self._main_tab.setCurrentWidget(self._publish_page)
        if hasattr(self, "_upload_update_btn") and self._upload_update_btn is not None:
            self._upload_update_btn.setVisible(False)

    def _auto_select_publish_type_from_scene(self):
        if rt is None:
            return
        from pipeline.rm_naming import validate_indoor_name, validate_outdoor_name
        filename = _as_text(getattr(rt, "maxFileName", u""))
        if not filename:
            return
        base = os.path.splitext(filename)[0]
        ok_in, _, _ = validate_indoor_name(
            base, self._config.get(u"category_folder_map")
        )
        if ok_in:
            self._type_indoor.setChecked(True)
            return
        ok_out, _, _ = validate_outdoor_name(
            base,
            self._config.get(u"module_folder_map"),
            self._config.get(u"outdoor_type_folder_map"),
            self._config.get(u"outdoor_asset_types"),
            self._config.get(u"category_folder_map"),
        )
        if ok_out:
            self._type_outdoor.setChecked(True)

    def _current_scene_signature(self):
        if rt is None:
            return u""
        return u"{0}|{1}".format(_as_text(rt.maxFilePath), _as_text(rt.maxFileName))

    def _poll_scene_change(self):
        if rt is None or self._indoor_resume_pending:
            return
        current_signature = self._current_scene_signature()
        if not self._scene_signature:
            self._scene_signature = current_signature
            return
        if current_signature != self._scene_signature:
            self._scene_signature = current_signature
            self._reset()

    def showEvent(self, event):
        super(MainWindow, self).showEvent(event)
        self._refresh_dev_upload_button_visibility()

    # ── 配置 I/O ─────────────────────────────────────────────────

    def _load_config(self):
        try:
            if os.path.exists(_CONFIG_PATH):
                with io.open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    cfg    = dict(DEFAULT_CONFIG)
                    cfg.update(loaded)
                    return cfg
        except Exception as e:
            print(u"[RMTool] 配置读取失败，使用默认配置: {0}".format(_as_text(e)))
            pass
        return dict(DEFAULT_CONFIG)

    def _save_config(self):
        try:
            config_dir = os.path.dirname(_CONFIG_PATH)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            tmp_path = _CONFIG_PATH + u".tmp"
            data = json.dumps(self._config, ensure_ascii=False, indent=2)
            with io.open(tmp_path, "w", encoding="utf-8") as f:
                f.write(_as_text(data))
            if os.path.exists(_CONFIG_PATH):
                os.remove(_CONFIG_PATH)
            os.rename(tmp_path, _CONFIG_PATH)
            return True
        except Exception as e:
            print(u"[RMTool] 配置保存失败: {0}".format(_as_text(e)))
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return False

    def _read_install_ini_value(self, key, default=u""):
        try:
            if rt is not None and os.path.exists(_INSTALL_INI_PATH):
                value = rt.getINISetting(_INSTALL_INI_PATH, "AnimationTools", key)
                return _as_text(value) if value not in (None, u"") else default
        except Exception:
            pass
        try:
            if not os.path.exists(_INSTALL_INI_PATH):
                return default
            current_section = u""
            with io.open(_INSTALL_INI_PATH, "r", encoding="utf-8") as f:
                for raw in f:
                    line = _as_text(raw).strip()
                    if not line or line.startswith(";"):
                        continue
                    if line.startswith("[") and line.endswith("]"):
                        current_section = line[1:-1]
                        continue
                    if current_section == u"AnimationTools" and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip().lower() == _as_text(key).lower():
                            return v.strip()
        except Exception:
            pass
        return default

    def _norm_path_for_compare(self, path):
        return os.path.normcase(os.path.normpath(_as_text(path).rstrip("\\/")))

    def _public_tool_root(self):
        return self._read_install_ini_value(
            "FixedPublicSource",
            u"",
        )

    def _ini_source_root(self):
        root = self._read_install_ini_value("SourceRoot", u"")
        return os.path.abspath(root) if root else u""

    def _is_valid_tool_package_dir(self, root):
        root = _as_text(root)
        if not root or not os.path.isdir(root):
            return False
        if not os.path.isfile(os.path.join(root, "install_animation_tools.ms")):
            return False
        if not os.path.isfile(os.path.join(root, "maxscript", "ReferenceRigLauncher.ms")):
            return False
        return True

    def _dev_marker_basename(self):
        name = _as_text((self._config or {}).get(u"dev_machine_marker_filename", DEFAULT_DEV_MARKER_FILENAME)).strip()
        return name or DEFAULT_DEV_MARKER_FILENAME

    def _dev_marker_candidate_roots(self):
        roots = []
        override = _as_text((self._config or {}).get(u"dev_machine_project_override", u"")).strip()
        if override:
            roots.append(os.path.abspath(override))
        env_root = os.environ.get("ANIMATION_TOOLS_PROJECT_ROOT", u"")
        if env_root:
            roots.append(os.path.abspath(_as_text(env_root)))
        ini_src = self._ini_source_root()
        if ini_src:
            roots.append(ini_src)
        if _INSTALL_ROOT:
            roots.append(os.path.abspath(_INSTALL_ROOT))
        seen = set()
        out = []
        for r in roots:
            if not r:
                continue
            key = self._norm_path_for_compare(r)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def _find_dev_marker_project_root(self):
        public = self._public_tool_root()
        marker = self._dev_marker_basename()
        for root in self._dev_marker_candidate_roots():
            if not self._is_valid_tool_package_dir(root):
                continue
            if self._norm_path_for_compare(root) == self._norm_path_for_compare(public):
                continue
            marker_path = os.path.join(root, marker)
            if os.path.isfile(marker_path):
                return root
        return u""

    def _resolve_dev_upload_source_root(self):
        public = self._public_tool_root()
        ini_src = self._ini_source_root()
        if (
            ini_src
            and self._is_valid_tool_package_dir(ini_src)
            and self._norm_path_for_compare(ini_src) != self._norm_path_for_compare(public)
        ):
            return ini_src
        marker_root = self._find_dev_marker_project_root()
        if marker_root:
            return marker_root
        return u""

    def _dev_upload_paths(self):
        source = self._resolve_dev_upload_source_root()
        public = self._public_tool_root()
        return source, public

    def _is_dev_machine_install(self):
        return bool(self._resolve_dev_upload_source_root())

    def _refresh_dev_upload_button_visibility(self):
        try:
            if hasattr(self, "_upload_update_btn") and self._upload_update_btn is not None:
                self._upload_update_btn.setVisible(self._is_dev_machine_install())
        except Exception:
            pass

    def _should_skip_dev_upload_dir(self, dirname):
        return _as_fs_path(dirname) in (
            u".git", u".cursor", u"__pycache__", u"plans",
            u"_RigUpdateBackup", u"_RigUpdateReports", u"_RigUpdatePackages",
        )

    def _should_skip_dev_upload_file(self, filename):
        name = _as_fs_path(filename)
        return (
            name.endswith(u".plan.md")
            or name == u"ReferenceRigInstall.ini"
            or name == u"config.json"
        )

    def _file_hash(self, path):
        h = hashlib.md5()
        with open(_as_fs_path(path), "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _collect_dev_upload_files(self, root):
        root = os.path.abspath(_as_fs_path(root))
        files = set()
        for current, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if not self._should_skip_dev_upload_dir(d)]
            rel_dir = _as_fs_path(os.path.relpath(current, root))
            for name in names:
                name = _as_fs_path(name)
                if self._should_skip_dev_upload_file(name):
                    continue
                rel = name if rel_dir == u"." else os.path.join(rel_dir, name)
                files.add(rel)
        return files

    def _verify_dev_upload(self, source, target):
        source = _as_fs_path(source)
        target = _as_fs_path(target)
        failed = []
        for rel in [
            os.path.join(u"RootMotionTool", u"anim_migration", u"ui", u"tab_binding_update.py"),
            os.path.join(u"RootMotionTool", u"anim_migration", u"workflow", u"context.py"),
            os.path.join(u"RootMotionTool", u"ui", u"rm_main_window.py"),
            os.path.join(u"RootMotionTool", u"op_tools_hub.py"),
            os.path.join(u"AnimationLibrary", u"launch_plugin.py"),
            os.path.join(u"maxscript", u"ReferenceRigLauncher.ms"),
            os.path.join(u"maxscript", u"PiToolsMenu.ms"),
            os.path.join(u"install_pi_tools_menu.ms"),
        ]:
            src_file = os.path.join(source, rel)
            dst_file = os.path.join(target, rel)
            if not os.path.exists(src_file):
                continue
            if not os.path.exists(dst_file):
                failed.append(rel)
                continue
            try:
                if self._file_hash(src_file) != self._file_hash(dst_file):
                    failed.append(rel)
            except Exception:
                failed.append(rel)
        if failed:
            raise RuntimeError(u"上传后校验失败，以下文件公盘版本与本地工程不一致:\n{0}".format(
                u"\n".join(failed)
            ))

    def _copy_dev_tool_folder(self, source, target):
        source = os.path.abspath(_as_fs_path(source))
        target = _as_fs_path(target)
        if not os.path.isdir(source):
            raise RuntimeError(u"本地工程目录不存在: {0}".format(source))
        if self._norm_path_for_compare(source) == self._norm_path_for_compare(target):
            raise RuntimeError(u"本地工程目录和公盘目录相同，已取消。")
        if not os.path.isdir(target):
            os.makedirs(target)
        source_files = self._collect_dev_upload_files(source)
        target_files = self._collect_dev_upload_files(target) if os.path.isdir(target) else set()
        copied = 0
        deleted = 0
        for current, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if not self._should_skip_dev_upload_dir(d)]
            rel = _as_fs_path(os.path.relpath(current, source))
            target_dir = target if rel == u"." else os.path.join(target, rel)
            if not os.path.isdir(target_dir):
                os.makedirs(target_dir)
            for name in files:
                name = _as_fs_path(name)
                if self._should_skip_dev_upload_file(name):
                    continue
                src_file = os.path.join(_as_fs_path(current), name)
                dst_file = os.path.join(target_dir, name)
                if os.path.exists(dst_file):
                    os.remove(dst_file)
                shutil.copy2(src_file, dst_file)
                copied += 1
        for rel in sorted(target_files - source_files, reverse=True):
            target_file = os.path.join(target, _as_fs_path(rel))
            try:
                if os.path.exists(target_file):
                    os.remove(target_file)
                    deleted += 1
            except Exception:
                pass
        self._verify_dev_upload(source, target)
        return copied, deleted

    # ── UI 构建 ───────────────────────────────────────────────────

    def _build_ui(self):
        _dbg("[BUILD_UI] A - start")
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setSpacing(6)
        root_layout.setContentsMargins(8, 8, 8, 8)
        self._root_layout = root_layout  # keep Python ref

        # ── 顶部工具栏 ──────────────────────────────────────────
        toolbar = QtWidgets.QHBoxLayout()
        self._toolbar_layout = toolbar  # keep Python ref
        try:
            from anim_migration.ui.tab_binding_update import UI_VERSION as binding_ui_version
        except Exception:
            binding_ui_version = u""
        title_text = u"Animation 动作工具 {0}".format(binding_ui_version) if binding_ui_version else u"Animation 动作工具"
        title   = QtWidgets.QLabel(title_text)
        title.setStyleSheet(u"font-size: 13px; font-weight: bold;")
        toolbar.addWidget(title)
        toolbar.addStretch()

        upload_update_btn = QtWidgets.QPushButton(u"上传更新")
        upload_update_btn.clicked.connect(self._upload_update_to_public)
        upload_update_btn.setStyleSheet(
            u"QPushButton { background:#6a3d2d; color:white; padding:6px 14px; border-radius:4px; }"
            u"QPushButton:hover { background:#8a523d; }"
        )
        self._upload_update_btn = upload_update_btn
        settings_btn = QtWidgets.QPushButton(u"设置")
        settings_btn.clicked.connect(self._open_settings)
        reset_btn    = QtWidgets.QPushButton(u"重置")
        reset_btn.clicked.connect(self._on_reset_clicked)
        toolbar.addWidget(upload_update_btn)
        toolbar.addWidget(settings_btn)
        toolbar.addWidget(reset_btn)
        root_layout.addLayout(toolbar)
        self._refresh_dev_upload_button_visibility()
        _dbg("[BUILD_UI] B - toolbar OK")

        # ── 顶栏：FBX 发布 | 武器约束绑定 | 绑定更新 ───────────────
        self._main_tab = QtWidgets.QTabWidget()
        self._main_tab.setObjectName(u"rmMainTabWidget")
        root_layout.addWidget(self._main_tab, 1)

        from ui.rm_weapon_state_panel import WeaponStatePanel
        from anim_migration.ui.tab_binding_update import BindingUpdateTab
        self._weapon_panel = WeaponStatePanel(self)
        self._binding_update_tab = BindingUpdateTab(self, rt=rt)
        try:
            self._binding_update_tab.on_config_updated(self._config)
        except Exception:
            pass

        self._publish_page = QtWidgets.QWidget()
        pub_lay = QtWidgets.QVBoxLayout(self._publish_page)
        pub_lay.setContentsMargins(0, 0, 0, 0)
        pub_lay.setSpacing(6)

        # ── 动画类型切换 ─────────────────────────────────────────
        type_frame  = QtWidgets.QGroupBox(u"导出模式")
        type_frame.setObjectName(u"rmTypeFrame")
        type_layout = QtWidgets.QHBoxLayout(type_frame)
        self._type_indoor   = QtWidgets.QRadioButton(u"局内")
        self._type_outdoor  = QtWidgets.QRadioButton(u"局外")
        self._type_indoor.setChecked(True)
        type_layout.addWidget(self._type_indoor)
        type_layout.addWidget(self._type_outdoor)
        type_layout.addStretch()
        self._type_indoor.toggled.connect(self._on_type_changed)
        pub_lay.addWidget(type_frame)
        _dbg("[BUILD_UI] C - type_frame OK")

        # ── 可滚动内容区 ─────────────────────────────────────────
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll_content  = QtWidgets.QWidget()
        scroll_content.setObjectName(u"rmScrollContent")
        self._scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        self._scroll_layout.setSpacing(4)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_content = scroll_content
        scroll.setWidget(scroll_content)
        pub_lay.addWidget(scroll, 1)
        _dbg("[BUILD_UI] D - scroll area OK")

        self._build_indoor_panel()
        _dbg("[BUILD_UI] E - indoor panel OK")
        self._outdoor_host = QtWidgets.QWidget(scroll_content)
        self._outdoor_host.setVisible(False)
        self._scroll_layout.addWidget(self._outdoor_host)
        self._scroll_layout.addStretch()

        # ── 预览名 ───────────────────────────────────────────────
        preview_frame = QtWidgets.QFrame()
        preview_frame.setObjectName(u"rmPreviewFrame")
        preview_layout = QtWidgets.QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(10, 8, 10, 8)
        preview_layout.setSpacing(6)
        preview_title = QtWidgets.QLabel(u"预览文件名")
        preview_title.setStyleSheet(u"font-size: 12px; font-weight: bold;")
        preview_layout.addWidget(preview_title)
        self._preview_text = QtWidgets.QPlainTextEdit()
        self._preview_text.setObjectName(u"rmPreviewText")
        self._preview_text.setReadOnly(True)
        self._preview_text.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self._preview_text.setMinimumHeight(72)
        self._preview_text.setMaximumHeight(116)
        preview_layout.addWidget(self._preview_text)
        pub_lay.addWidget(preview_frame)

        # ── 导出按钮 ─────────────────────────────────────────────
        self._export_btn = QtWidgets.QPushButton(u"发布")
        self._export_btn.setMinimumHeight(42)
        self._export_btn.setStyleSheet(
            u"QPushButton {"
            u"  background: #2d6a2d; color: white;"
            u"  font-size: 13px; font-weight: bold; border-radius: 4px;"
            u"}"
            u"QPushButton:hover    { background: #3d8a3d; }"
            u"QPushButton:disabled { background: #3a3a3a; color: #666; }"
        )
        self._export_btn.clicked.connect(self._on_export)
        pub_lay.addWidget(self._export_btn)

        self._batch_btn = QtWidgets.QPushButton(u"选择文件夹批量导出（仅局内）")
        self._batch_btn.setStyleSheet(
            u"QPushButton { background: #2d4a6a; color: white; border-radius: 4px; padding: 6px; }"
            u"QPushButton:hover { background: #3d5a8a; }"
        )
        self._batch_btn.clicked.connect(self._on_batch_export)
        pub_lay.addWidget(self._batch_btn)

        self._main_tab.addTab(self._publish_page, u"FBX 发布")
        self._main_tab.addTab(self._weapon_panel, u"武器约束绑定")
        self._main_tab.addTab(self._binding_update_tab, u"绑定更新")
        self._main_tab.currentChanged.connect(self._on_main_tab_changed)

    def _on_main_tab_changed(self, idx):
        try:
            widget = self._main_tab.widget(idx)
        except Exception:
            return
        if widget is self._binding_update_tab:
            self._binding_update_tab.refresh_current_anim_path()

    # ── 局内面板 ──────────────────────────────────────────────────

    def _build_indoor_panel(self):
        _dbg("[INDOOR] 1 - start")
        self._indoor_panel = QtWidgets.QWidget()
        self._indoor_panel.setObjectName(u"rmPagePanel")
        pl = QtWidgets.QVBoxLayout(self._indoor_panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)

        # ── 对象拾取 ────────────────────────────────────────────
        _dbg("[INDOOR] 2 - before CollapsibleGroup")
        pick_grp = CollapsibleGroup(u"对象拾取", parent=self._indoor_panel, expanded=True)
        pick_body = QtWidgets.QVBoxLayout(pick_grp.body_widget())
        pick_body.setContentsMargins(10, 8, 10, 10)

        self._manual_pick_chk = QtWidgets.QCheckBox(u"手动拾取对象（不使用自动检测）")
        pick_body.addWidget(self._manual_pick_chk)

        self._pick_btns = QtWidgets.QWidget()
        pb_row = QtWidgets.QHBoxLayout(self._pick_btns)
        pb_row.setContentsMargins(0, 0, 0, 0)
        self._bip_btn  = QtWidgets.QPushButton(u"拾取 Bip001")
        self._root_btn = QtWidgets.QPushButton(u"拾取 Root 骨骼")
        pb_row.addWidget(self._bip_btn)
        pb_row.addWidget(self._root_btn)
        self._pick_btns.setVisible(False)
        pick_body.addWidget(self._pick_btns)

        self._obj_status = QtWidgets.QLabel(u"状态：自动检测中…")
        self._obj_status.setStyleSheet(u"color: #aaa; font-size: 11px; padding: 2px 0;")
        pick_body.addWidget(self._obj_status)

        pl.addWidget(pick_grp)

        self._manual_pick_chk.toggled.connect(self._pick_btns.setVisible)
        self._bip_btn.clicked.connect(self._pick_bip)
        self._root_btn.clicked.connect(self._pick_root)
        _dbg("[INDOOR] 3 - pick_grp OK")

        sample_grp = QtWidgets.QGroupBox(u"FBX 发布采样精度")
        sample_lay = QtWidgets.QVBoxLayout(sample_grp)
        sample_lay.setContentsMargins(10, 8, 10, 10)
        sample_row = QtWidgets.QHBoxLayout()
        sample_row.addWidget(QtWidgets.QLabel(u"FBX 采样率"))
        self._proxy_sample_rate_ddl = QtWidgets.QComboBox()
        self._proxy_sample_rate_ddl.addItem(u"30 Hz（默认 / 推荐）", 30)
        self._proxy_sample_rate_ddl.addItem(u"60 Hz（精度补偿）", 60)
        self._proxy_sample_rate_ddl.addItem(u"120 Hz（最高精度 / 高内存）", 120)
        self._proxy_sample_rate_ddl.setCurrentIndex(0)
        self._proxy_sample_rate_ddl.setToolTip(
            u"默认使用 30 Hz。仅当导入 Unity 后出现可见抖动或精度不足时，"
            u"先尝试 60 Hz；120 Hz 只作为最后的高精度选项。"
        )
        sample_row.addWidget(self._proxy_sample_rate_ddl, 1)
        sample_lay.addLayout(sample_row)
        sample_hint = QtWidgets.QLabel(
            u"30 Hz 内存最低；60 Hz 约为 30 Hz 的 1.8 倍；120 Hz 约为 3.3 倍。"
        )
        sample_hint.setWordWrap(True)
        sample_hint.setStyleSheet(u"color: #d7b56d; font-size: 11px;")
        sample_lay.addWidget(sample_hint)
        sample_grp.setVisible(self._com_restore_engine == u"baselayer")
        self._proxy_sample_rate_group = sample_grp
        pl.addWidget(sample_grp)

        # ── 位移提取 ─────────────────────────────────────────────
        pos_grp  = CollapsibleGroup(u"位移 Root Motion", parent=self._indoor_panel, expanded=True)
        pos_body = QtWidgets.QVBoxLayout(pos_grp.body_widget())
        pos_body.setContentsMargins(10, 8, 10, 10)

        self._wallhit_mode_hint = QtWidgets.QLabel(
            u"已进入 _WallHit 专用根运动分支：根运动将按九个动画拆分片段自动计算，"
            u"下方通用根运动选项不会参与计算。"
        )
        self._wallhit_mode_hint.setWordWrap(True)
        self._wallhit_mode_hint.setStyleSheet(
            u"color: #ffd27a; background: #4a3b20; border: 1px solid #8a6a2d;"
            u"border-radius: 4px; padding: 8px;"
        )
        self._wallhit_mode_hint.setVisible(False)
        pos_body.addWidget(self._wallhit_mode_hint)

        self._enable_pos_chk = QtWidgets.QCheckBox(u"启用位移根运动")
        self._enable_pos_chk.setChecked(True)
        pos_body.addWidget(self._enable_pos_chk)

        self._pos_detail_wrap = QtWidgets.QWidget(pos_grp.body_widget())
        pos_detail = QtWidgets.QVBoxLayout(self._pos_detail_wrap)
        pos_detail.setContentsMargins(6, 4, 6, 0)
        pos_detail.setSpacing(10)

        self._axis_settings_wrap = QtWidgets.QFrame(pos_grp.body_widget())
        self._axis_settings_wrap.setObjectName(u"rmPosSectionCard")
        axis_section = QtWidgets.QVBoxLayout(self._axis_settings_wrap)
        axis_section.setContentsMargins(12, 10, 12, 10)
        axis_section.setSpacing(6)
        axis_title = QtWidgets.QLabel(u"基础轴向")
        axis_title.setObjectName(u"rmPosSectionTitle")
        axis_section.addWidget(axis_title)
        axis_hint = QtWidgets.QLabel(u"先决定 Root Motion 跟随哪些轴向，后面的附加设置会基于这里的选择生效。")
        axis_hint.setObjectName(u"rmPosSectionHint")
        axis_hint.setWordWrap(True)
        axis_section.addWidget(axis_hint)

        axis_row_widget = QtWidgets.QWidget(self._axis_settings_wrap)
        axis_row = QtWidgets.QHBoxLayout(axis_row_widget)
        axis_row.setContentsMargins(0, 2, 0, 0)
        self._follow_x_chk = QtWidgets.QCheckBox(u"X轴位移")
        self._follow_y_chk = QtWidgets.QCheckBox(u"Y轴位移")
        self._follow_z_chk = QtWidgets.QCheckBox(u"Z轴位移")
        self._follow_y_chk.setChecked(True)
        axis_row.addWidget(self._follow_x_chk)
        axis_row.addWidget(self._follow_y_chk)
        axis_row.addWidget(self._follow_z_chk)
        axis_row.addStretch()
        axis_section.addWidget(axis_row_widget)
        pos_detail.addWidget(self._axis_settings_wrap)

        self._z_settings_wrap = QtWidgets.QFrame(pos_grp.body_widget())
        self._z_settings_wrap.setObjectName(u"rmPosSectionCard")
        z_settings = QtWidgets.QVBoxLayout(self._z_settings_wrap)
        z_settings.setContentsMargins(12, 10, 12, 10)
        z_settings.setSpacing(6)
        z_title = QtWidgets.QLabel(u"Z轴附加设置")
        z_title.setObjectName(u"rmPosSectionTitle")
        z_settings.addWidget(z_title)
        z_hint = QtWidgets.QLabel(u"仅在勾选 Z轴位移 时启用，用于控制离地判定、有效区间和悬停锁高。")
        z_hint.setObjectName(u"rmPosSectionHint")
        z_hint.setWordWrap(True)
        z_settings.addWidget(z_hint)

        self._z_ground_wrap = QtWidgets.QFrame(self._z_settings_wrap)
        self._z_ground_wrap.setObjectName(u"rmPosSubSectionCard")
        z_ground_layout = QtWidgets.QVBoxLayout(self._z_ground_wrap)
        z_ground_layout.setContentsMargins(10, 8, 10, 8)
        z_ground_layout.setSpacing(6)
        z_ground_title = QtWidgets.QLabel(u"离地判定")
        z_ground_title.setObjectName(u"rmPosSubSectionTitle")
        z_ground_layout.addWidget(z_ground_title)

        z_top_row = QtWidgets.QWidget(self._z_ground_wrap)
        z_top_layout = QtWidgets.QHBoxLayout(z_top_row)
        z_top_layout.setContentsMargins(0, 2, 0, 0)
        z_top_layout.addWidget(QtWidgets.QLabel(u"离地判定:"))
        self._z_thres_spn  = QtWidgets.QDoubleSpinBox()
        self._z_thres_spn.setRange(0, 9999)
        self._z_thres_spn.setValue(50.0)
        self._z_thres_spn.setSuffix(u" cm")
        self._z_thres_spn.setMinimumWidth(120)
        self._z_thres_spn.setToolTip(u"当前腾空段双脚最高点需超过此值，整段才计算 Z 轴跟随")
        z_top_layout.addWidget(self._z_thres_spn)
        z_top_layout.addSpacing(8)
        z_top_layout.addWidget(QtWidgets.QLabel(u"位移比例:"))
        self._z_weight_spn = QtWidgets.QDoubleSpinBox()
        self._z_weight_spn.setRange(0, 1)
        self._z_weight_spn.setValue(1.0)
        self._z_weight_spn.setSingleStep(0.1)
        self._z_weight_spn.setMinimumWidth(110)
        self._z_weight_spn.setToolTip(u"1.0 = 完全跟随质心，0.5 = 只抬升一半高度")
        z_top_layout.addWidget(self._z_weight_spn)
        z_top_layout.addStretch()
        z_ground_layout.addWidget(z_top_row)
        z_settings.addWidget(self._z_ground_wrap)

        self._z_limit_section = QtWidgets.QFrame(self._z_settings_wrap)
        self._z_limit_section.setObjectName(u"rmPosSubSectionCard")
        z_limit_section_layout = QtWidgets.QVBoxLayout(self._z_limit_section)
        z_limit_section_layout.setContentsMargins(10, 8, 10, 8)
        z_limit_section_layout.setSpacing(6)
        z_limit_title = QtWidgets.QLabel(u"区间限制")
        z_limit_title.setObjectName(u"rmPosSubSectionTitle")
        z_limit_section_layout.addWidget(z_limit_title)

        self._z_limit_chk = QtWidgets.QCheckBox(u"限制Z轴区间")
        z_limit_section_layout.addWidget(self._z_limit_chk)

        self._z_limit_wrap = QtWidgets.QWidget(self._z_limit_section)
        z_limit_row = QtWidgets.QHBoxLayout(self._z_limit_wrap)
        z_limit_row.setContentsMargins(18, 0, 0, 0)
        z_limit_row.addWidget(QtWidgets.QLabel(u"Start:"))
        self._z_limit_start_spn = QtWidgets.QSpinBox()
        self._z_limit_start_spn.setRange(-99999, 99999)
        self._z_limit_start_spn.setMinimumWidth(110)
        z_limit_row.addWidget(self._z_limit_start_spn)
        z_limit_row.addSpacing(8)
        z_limit_row.addWidget(QtWidgets.QLabel(u"End:"))
        self._z_limit_end_spn = QtWidgets.QSpinBox()
        self._z_limit_end_spn.setRange(-99999, 99999)
        self._z_limit_end_spn.setMinimumWidth(110)
        z_limit_row.addWidget(self._z_limit_end_spn)
        z_limit_row.addStretch()
        z_limit_section_layout.addWidget(self._z_limit_wrap)
        z_settings.addWidget(self._z_limit_section)

        self._z_hover_section = QtWidgets.QFrame(self._z_settings_wrap)
        self._z_hover_section.setObjectName(u"rmPosSubSectionCard")
        z_hover_section_layout = QtWidgets.QVBoxLayout(self._z_hover_section)
        z_hover_section_layout.setContentsMargins(10, 8, 10, 8)
        z_hover_section_layout.setSpacing(6)
        z_hover_title = QtWidgets.QLabel(u"悬停锁高")
        z_hover_title.setObjectName(u"rmPosSubSectionTitle")
        z_hover_section_layout.addWidget(z_hover_title)

        self._z_hover_chk = QtWidgets.QCheckBox(u"强制锁定滞空高度 (Z轴悬停)")
        z_hover_section_layout.addWidget(self._z_hover_chk)

        self._z_hover_wrap = QtWidgets.QWidget(self._z_hover_section)
        z_hover_layout = QtWidgets.QVBoxLayout(self._z_hover_wrap)
        z_hover_layout.setContentsMargins(18, 0, 0, 0)
        z_hover_layout.setSpacing(6)

        z_hover_height_row = QtWidgets.QWidget(self._z_hover_wrap)
        z_hover_height_layout = QtWidgets.QHBoxLayout(z_hover_height_row)
        z_hover_height_layout.setContentsMargins(0, 0, 0, 0)
        z_hover_height_layout.addWidget(QtWidgets.QLabel(u"目标高度(cm):"))
        self._z_hover_height_spn = QtWidgets.QDoubleSpinBox()
        self._z_hover_height_spn.setRange(-99999.0, 99999.0)
        self._z_hover_height_spn.setValue(150.0)
        self._z_hover_height_spn.setMinimumWidth(120)
        z_hover_height_layout.addWidget(self._z_hover_height_spn)
        z_hover_height_layout.addStretch()
        z_hover_layout.addWidget(z_hover_height_row)

        z_hover_range_row = QtWidgets.QWidget(self._z_hover_wrap)
        z_hover_range_layout = QtWidgets.QHBoxLayout(z_hover_range_row)
        z_hover_range_layout.setContentsMargins(0, 0, 0, 0)
        z_hover_range_layout.addWidget(QtWidgets.QLabel(u"Start:"))
        self._z_hover_start_spn = QtWidgets.QSpinBox()
        self._z_hover_start_spn.setRange(-99999, 99999)
        self._z_hover_start_spn.setMinimumWidth(110)
        z_hover_range_layout.addWidget(self._z_hover_start_spn)
        z_hover_range_layout.addSpacing(8)
        z_hover_range_layout.addWidget(QtWidgets.QLabel(u"End:"))
        self._z_hover_end_spn = QtWidgets.QSpinBox()
        self._z_hover_end_spn.setRange(-99999, 99999)
        self._z_hover_end_spn.setMinimumWidth(110)
        z_hover_range_layout.addWidget(self._z_hover_end_spn)
        z_hover_range_layout.addStretch()
        z_hover_layout.addWidget(z_hover_range_row)
        z_hover_section_layout.addWidget(self._z_hover_wrap)
        z_settings.addWidget(self._z_hover_section)

        pos_detail.addWidget(self._z_settings_wrap)

        self._offset_settings_wrap = QtWidgets.QFrame(pos_grp.body_widget())
        self._offset_settings_wrap.setObjectName(u"rmPosSectionCard")
        offset_section = QtWidgets.QVBoxLayout(self._offset_settings_wrap)
        offset_section.setContentsMargins(12, 10, 12, 10)
        offset_section.setSpacing(6)
        offset_title = QtWidgets.QLabel(u"全局偏移")
        offset_title.setObjectName(u"rmPosSectionTitle")
        offset_section.addWidget(offset_title)
        offset_hint = QtWidgets.QLabel(u"用于在导出时整体补偿角色质心位移，不依赖 Z轴附加设置。")
        offset_hint.setObjectName(u"rmPosSectionHint")
        offset_hint.setWordWrap(True)
        offset_section.addWidget(offset_hint)

        self._enable_offset_chk = QtWidgets.QCheckBox(u"启用全局偏移")
        offset_section.addWidget(self._enable_offset_chk)

        self._offset_controls_wrap = QtWidgets.QWidget(self._offset_settings_wrap)
        offset_controls = QtWidgets.QVBoxLayout(self._offset_controls_wrap)
        offset_controls.setContentsMargins(0, 0, 0, 0)
        offset_controls.setSpacing(0)

        offset_row_widget = QtWidgets.QWidget(self._offset_controls_wrap)
        offset_row = QtWidgets.QHBoxLayout(offset_row_widget)
        offset_row.setContentsMargins(0, 2, 0, 0)
        offset_row.addWidget(QtWidgets.QLabel(u"全局偏移:"))
        self._offset_x_spn = QtWidgets.QDoubleSpinBox()
        self._offset_x_spn.setRange(-99999, 99999)
        self._offset_x_spn.setPrefix(u"X: ")
        self._offset_x_spn.setMinimumWidth(120)
        self._offset_y_spn = QtWidgets.QDoubleSpinBox()
        self._offset_y_spn.setRange(-99999, 99999)
        self._offset_y_spn.setPrefix(u"Y: ")
        self._offset_y_spn.setMinimumWidth(120)
        self._offset_z_spn = QtWidgets.QDoubleSpinBox()
        self._offset_z_spn.setRange(-99999, 99999)
        self._offset_z_spn.setPrefix(u"Z: ")
        self._offset_z_spn.setMinimumWidth(120)
        offset_row.addWidget(self._offset_x_spn)
        offset_row.addWidget(self._offset_y_spn)
        offset_row.addWidget(self._offset_z_spn)
        offset_row.addStretch()
        offset_controls.addWidget(offset_row_widget)
        offset_section.addWidget(self._offset_controls_wrap)
        pos_detail.addWidget(self._offset_settings_wrap)

        self._smooth_settings_wrap = QtWidgets.QFrame(pos_grp.body_widget())
        self._smooth_settings_wrap.setObjectName(u"rmPosSectionCard")
        smooth_settings = QtWidgets.QVBoxLayout(self._smooth_settings_wrap)
        smooth_settings.setContentsMargins(12, 10, 12, 10)
        smooth_settings.setSpacing(6)
        smooth_title = QtWidgets.QLabel(u"XY死区与平滑")
        smooth_title.setObjectName(u"rmPosSectionTitle")
        smooth_settings.addWidget(smooth_title)
        smooth_hint = QtWidgets.QLabel(u"用于过滤 XY 抖动和做轨迹平滑，可额外限制只在指定帧区间内生效。")
        smooth_hint.setObjectName(u"rmPosSectionHint")
        smooth_hint.setWordWrap(True)
        smooth_settings.addWidget(smooth_hint)

        self._use_smooth_chk = QtWidgets.QCheckBox(u"启用死区与平滑 (仅XY)")
        smooth_settings.addWidget(self._use_smooth_chk)

        self._smooth_controls_wrap = QtWidgets.QWidget(self._smooth_settings_wrap)
        smooth_controls = QtWidgets.QVBoxLayout(self._smooth_controls_wrap)
        smooth_controls.setContentsMargins(0, 0, 0, 0)
        smooth_controls.setSpacing(6)

        smooth_row_widget = QtWidgets.QWidget(self._smooth_controls_wrap)
        smooth_row = QtWidgets.QHBoxLayout(smooth_row_widget)
        smooth_row.setContentsMargins(0, 2, 0, 0)
        smooth_row.addWidget(QtWidgets.QLabel(u"死区:"))
        self._filter_spn = QtWidgets.QDoubleSpinBox()
        self._filter_spn.setRange(0, 9999)
        self._filter_spn.setValue(10.0)
        self._filter_spn.setSuffix(u" cm")
        self._filter_spn.setMinimumWidth(120)
        smooth_row.addWidget(self._filter_spn)
        smooth_row.addSpacing(8)
        smooth_row.addWidget(QtWidgets.QLabel(u"平滑:"))
        self._smooth_str_spn = QtWidgets.QSpinBox()
        self._smooth_str_spn.setRange(0, 20)
        self._smooth_str_spn.setValue(1)
        self._smooth_str_spn.setMinimumWidth(100)
        smooth_row.addWidget(self._smooth_str_spn)
        smooth_row.addStretch()
        smooth_controls.addWidget(smooth_row_widget)

        self._smooth_limit_chk = QtWidgets.QCheckBox(u"限制平滑区间")
        smooth_controls.addWidget(self._smooth_limit_chk)

        self._smooth_limit_wrap = QtWidgets.QWidget(self._smooth_controls_wrap)
        smooth_limit_row = QtWidgets.QHBoxLayout(self._smooth_limit_wrap)
        smooth_limit_row.setContentsMargins(18, 0, 0, 0)
        smooth_limit_row.addWidget(QtWidgets.QLabel(u"Start:"))
        self._smooth_limit_start_spn = QtWidgets.QSpinBox()
        self._smooth_limit_start_spn.setRange(-99999, 99999)
        self._smooth_limit_start_spn.setMinimumWidth(110)
        smooth_limit_row.addWidget(self._smooth_limit_start_spn)
        smooth_limit_row.addSpacing(8)
        smooth_limit_row.addWidget(QtWidgets.QLabel(u"End:"))
        self._smooth_limit_end_spn = QtWidgets.QSpinBox()
        self._smooth_limit_end_spn.setRange(-99999, 99999)
        self._smooth_limit_end_spn.setMinimumWidth(110)
        smooth_limit_row.addWidget(self._smooth_limit_end_spn)
        smooth_limit_row.addStretch()
        smooth_controls.addWidget(self._smooth_limit_wrap)
        smooth_settings.addWidget(self._smooth_controls_wrap)

        pos_detail.addWidget(self._smooth_settings_wrap)

        self._pos_rm_range_wrap = QtWidgets.QFrame(pos_grp.body_widget())
        self._pos_rm_range_wrap.setObjectName(u"rmPosSectionCard")
        pos_rm_layout = QtWidgets.QVBoxLayout(self._pos_rm_range_wrap)
        pos_rm_layout.setContentsMargins(12, 10, 12, 10)
        pos_rm_layout.setSpacing(6)
        pos_rm_title = QtWidgets.QLabel(u"指定根运动区间")
        pos_rm_title.setObjectName(u"rmPosSectionTitle")
        pos_rm_layout.addWidget(pos_rm_title)
        pos_rm_hint = QtWidgets.QLabel(
            u"勾选后，位移根运动仅在所填帧区间内生效；区间外不应用位移提取结果（Root 位移为 0）。"
            u"不影响旋转根运动。"
        )
        pos_rm_hint.setObjectName(u"rmPosSectionHint")
        pos_rm_hint.setWordWrap(True)
        pos_rm_layout.addWidget(pos_rm_hint)
        self._pos_rm_limit_chk = QtWidgets.QCheckBox(u"指定根运动起止帧")
        pos_rm_layout.addWidget(self._pos_rm_limit_chk)
        self._pos_rm_limit_wrap = QtWidgets.QWidget(self._pos_rm_range_wrap)
        pos_rm_row = QtWidgets.QHBoxLayout(self._pos_rm_limit_wrap)
        pos_rm_row.setContentsMargins(18, 0, 0, 0)
        pos_rm_row.addWidget(QtWidgets.QLabel(u"起始帧:"))
        self._pos_rm_start_spn = QtWidgets.QSpinBox()
        self._pos_rm_start_spn.setRange(-99999, 99999)
        self._pos_rm_start_spn.setMinimumWidth(110)
        pos_rm_row.addWidget(self._pos_rm_start_spn)
        pos_rm_row.addSpacing(8)
        pos_rm_row.addWidget(QtWidgets.QLabel(u"结束帧:"))
        self._pos_rm_end_spn = QtWidgets.QSpinBox()
        self._pos_rm_end_spn.setRange(-99999, 99999)
        self._pos_rm_end_spn.setMinimumWidth(110)
        pos_rm_row.addWidget(self._pos_rm_end_spn)
        pos_rm_row.addStretch()
        pos_rm_layout.addWidget(self._pos_rm_limit_wrap)
        pos_detail.addWidget(self._pos_rm_range_wrap)

        pos_body.addWidget(self._pos_detail_wrap)

        pl.addWidget(pos_grp)
        _dbg("[INDOOR] 4 - pos_grp OK")

        # ── 旋转提取 ─────────────────────────────────────────────
        rot_grp  = CollapsibleGroup(u"旋转 Root Motion", parent=self._indoor_panel)
        rot_body = QtWidgets.QVBoxLayout(rot_grp.body_widget())
        rot_body.setContentsMargins(10, 8, 10, 10)
        rot_body.setSpacing(8)
        self._enable_rot_chk = QtWidgets.QCheckBox(u"启用旋转根运动（偏航角提取，S 曲线缓动）")
        rot_body.addWidget(self._enable_rot_chk)

        self._rot_detail_wrap = QtWidgets.QWidget(rot_grp.body_widget())
        rot_detail = QtWidgets.QVBoxLayout(self._rot_detail_wrap)
        rot_detail.setContentsMargins(0, 4, 0, 0)
        rot_detail.setSpacing(8)

        # 自定义 Root 旋转角度/方向
        self._rot_custom_wrap = QtWidgets.QFrame(self._rot_detail_wrap)
        self._rot_custom_wrap.setObjectName(u"rmPosSectionCard")
        rot_custom_layout = QtWidgets.QVBoxLayout(self._rot_custom_wrap)
        rot_custom_layout.setContentsMargins(12, 10, 12, 10)
        rot_custom_layout.setSpacing(6)
        rot_custom_title = QtWidgets.QLabel(u"自定义 Root 旋转")
        rot_custom_title.setObjectName(u"rmPosSectionTitle")
        rot_custom_layout.addWidget(rot_custom_title)
        rot_custom_hint = QtWidgets.QLabel(
            u"开启后使用自定义角度；方向默认跟随质心旋转方向，也可手动改左转/右转。"
        )
        rot_custom_hint.setObjectName(u"rmPosSectionHint")
        rot_custom_hint.setWordWrap(True)
        rot_custom_layout.addWidget(rot_custom_hint)
        self._rot_custom_angle_chk = QtWidgets.QCheckBox(u"自定义 Root 旋转角度与方向")
        rot_custom_layout.addWidget(self._rot_custom_angle_chk)
        self._rot_custom_controls_wrap = QtWidgets.QWidget(self._rot_custom_wrap)
        rot_custom_row = QtWidgets.QHBoxLayout(self._rot_custom_controls_wrap)
        rot_custom_row.setContentsMargins(18, 0, 0, 0)
        rot_custom_row.addWidget(QtWidgets.QLabel(u"角度:"))
        self._rot_custom_degrees_spn = QtWidgets.QDoubleSpinBox()
        self._rot_custom_degrees_spn.setRange(0.0, 720.0)
        self._rot_custom_degrees_spn.setDecimals(1)
        self._rot_custom_degrees_spn.setSingleStep(1.0)
        self._rot_custom_degrees_spn.setValue(180.0)
        self._rot_custom_degrees_spn.setSuffix(u" °")
        self._rot_custom_degrees_spn.setMinimumWidth(110)
        rot_custom_row.addWidget(self._rot_custom_degrees_spn)
        rot_custom_row.addSpacing(8)
        rot_custom_row.addWidget(QtWidgets.QLabel(u"方向:"))
        self._rot_custom_dir_ddl = QtWidgets.QComboBox()
        self._rot_custom_dir_ddl.addItem(u"跟随质心", u"auto")
        self._rot_custom_dir_ddl.addItem(u"左转 (+)", u"left")
        self._rot_custom_dir_ddl.addItem(u"右转 (-)", u"right")
        self._rot_custom_dir_ddl.setMinimumWidth(130)
        self._rot_custom_dir_ddl.setToolTip(
            u"默认跟随质心累计偏航方向；需要时可手动改为左转/右转。"
        )
        rot_custom_row.addWidget(self._rot_custom_dir_ddl)
        rot_custom_row.addStretch()
        rot_custom_layout.addWidget(self._rot_custom_controls_wrap)
        rot_detail.addWidget(self._rot_custom_wrap)

        # 指定旋转跟随起止帧
        self._rot_range_wrap = QtWidgets.QFrame(self._rot_detail_wrap)
        self._rot_range_wrap.setObjectName(u"rmPosSectionCard")
        rot_range_layout = QtWidgets.QVBoxLayout(self._rot_range_wrap)
        rot_range_layout.setContentsMargins(12, 10, 12, 10)
        rot_range_layout.setSpacing(6)
        rot_range_title = QtWidgets.QLabel(u"指定旋转跟随区间")
        rot_range_title.setObjectName(u"rmPosSectionTitle")
        rot_range_layout.addWidget(rot_range_title)
        rot_range_hint = QtWidgets.QLabel(
            u"开启后在指定帧区间内用 S 曲线完成 Root 旋转；区间前为 0，区间后锁满目标角度。"
        )
        rot_range_hint.setObjectName(u"rmPosSectionHint")
        rot_range_hint.setWordWrap(True)
        rot_range_layout.addWidget(rot_range_hint)
        self._rot_limit_chk = QtWidgets.QCheckBox(u"指定旋转跟随起止帧")
        rot_range_layout.addWidget(self._rot_limit_chk)
        self._rot_limit_wrap = QtWidgets.QWidget(self._rot_range_wrap)
        rot_limit_row = QtWidgets.QHBoxLayout(self._rot_limit_wrap)
        rot_limit_row.setContentsMargins(18, 0, 0, 0)
        rot_limit_row.addWidget(QtWidgets.QLabel(u"起始帧:"))
        self._rot_limit_start_spn = QtWidgets.QSpinBox()
        self._rot_limit_start_spn.setRange(-99999, 99999)
        self._rot_limit_start_spn.setMinimumWidth(110)
        rot_limit_row.addWidget(self._rot_limit_start_spn)
        rot_limit_row.addSpacing(8)
        rot_limit_row.addWidget(QtWidgets.QLabel(u"结束帧:"))
        self._rot_limit_end_spn = QtWidgets.QSpinBox()
        self._rot_limit_end_spn.setRange(-99999, 99999)
        self._rot_limit_end_spn.setMinimumWidth(110)
        rot_limit_row.addWidget(self._rot_limit_end_spn)
        rot_limit_row.addStretch()
        rot_range_layout.addWidget(self._rot_limit_wrap)
        rot_detail.addWidget(self._rot_range_wrap)

        rot_body.addWidget(self._rot_detail_wrap)
        pl.addWidget(rot_grp)
        _dbg("[INDOOR] 5 - rot_grp OK")

        # ── 分段导出 ─────────────────────────────────────────────
        split_grp  = CollapsibleGroup(u"分段导出", parent=self._indoor_panel)
        split_body = QtWidgets.QVBoxLayout(split_grp.body_widget())
        split_body.setContentsMargins(10, 8, 10, 10)
        _dbg("[INDOOR-SPLIT] 1 - split layout OK")

        self._enable_split_chk = QtWidgets.QCheckBox(u"启用 动画拆分")
        split_body.addWidget(self._enable_split_chk)
        _dbg("[INDOOR-SPLIT] 2 - enable checkbox OK")

        self._split_editor_wrap = QtWidgets.QWidget(split_grp.body_widget())
        split_editor = QtWidgets.QVBoxLayout(self._split_editor_wrap)
        split_editor.setContentsMargins(0, 2, 0, 0)
        split_editor.setSpacing(8)

        self._seg_input_widget = QtWidgets.QWidget(split_grp.body_widget())
        self._seg_input_row = QtWidgets.QHBoxLayout(self._seg_input_widget)
        self._seg_input_row.setContentsMargins(0, 0, 0, 0)
        self._seg_input_row.addWidget(QtWidgets.QLabel(u"后缀:"))
        self._seg_suffix_edit = QtWidgets.QLineEdit(u"Start")
        self._seg_suffix_edit.setPlaceholderText(u"无需输入下划线")
        self._seg_suffix_edit.setMinimumWidth(120)
        self._seg_input_row.addWidget(self._seg_suffix_edit)
        self._seg_preset_ddl  = QtWidgets.QComboBox()
        self._seg_preset_ddl.addItems(
            [
                u"Start", u"Loop", u"End", u"Process", u"Ultra",
                u"Rise_Start", u"Rise_End", u"Fall_Start", u"Fall_Loop",
                u"Bounce_Start", u"Bounce_End", u"Bounce_Loop",
                u"Land_Start", u"Land_Loop", u"Land_End"
            ]
        )
        self._seg_preset_ddl.setMinimumWidth(180)
        self._seg_preset_ddl.currentIndexChanged.connect(self._sync_seg_suffix_from_preset)
        self._seg_input_row.addWidget(self._seg_preset_ddl)
        self._seg_input_row.addStretch()
        split_editor.addWidget(self._seg_input_widget)
        _dbg("[INDOOR-SPLIT] 3 - suffix row OK")

        self._seg_range_widget = QtWidgets.QWidget(split_grp.body_widget())
        self._seg_range_row = QtWidgets.QHBoxLayout(self._seg_range_widget)
        self._seg_range_row.setContentsMargins(0, 0, 0, 0)
        self._seg_range_row.addWidget(QtWidgets.QLabel(u"Start:"))
        self._seg_start_spn = QtWidgets.QSpinBox()
        self._seg_start_spn.setRange(-99999, 99999)
        self._seg_start_spn.setMinimumWidth(110)
        self._seg_range_row.addWidget(self._seg_start_spn)
        self._seg_range_row.addSpacing(8)
        self._seg_range_row.addWidget(QtWidgets.QLabel(u"End:"))
        self._seg_end_spn   = QtWidgets.QSpinBox()
        self._seg_end_spn.setRange(-99999, 99999)
        self._seg_end_spn.setValue(100)
        self._seg_end_spn.setMinimumWidth(110)
        self._seg_start_spn.editingFinished.connect(self._commit_selected_segment_range)
        self._seg_end_spn.editingFinished.connect(self._commit_selected_segment_range)
        self._seg_range_row.addWidget(self._seg_end_spn)
        self._seg_range_row.addStretch()
        split_editor.addWidget(self._seg_range_widget)
        _dbg("[INDOOR-SPLIT] 4 - range row OK")

        self._seg_btn_widget = QtWidgets.QWidget(split_grp.body_widget())
        self._seg_btn_row = QtWidgets.QHBoxLayout(self._seg_btn_widget)
        self._seg_btn_row.setContentsMargins(0, 0, 0, 0)
        add_seg_btn = QtWidgets.QPushButton(u"添加动画片段")
        add_seg_btn.clicked.connect(self._add_segment)
        del_seg_btn = QtWidgets.QPushButton(u"删除动画片段")
        del_seg_btn.clicked.connect(self._del_segment)
        self._seg_btn_row.addWidget(add_seg_btn)
        self._seg_btn_row.addWidget(del_seg_btn)
        self._seg_btn_row.addStretch()
        split_editor.addWidget(self._seg_btn_widget)
        _dbg("[INDOOR-SPLIT] 5 - button row OK")

        self._seg_list_header = QtWidgets.QWidget(split_grp.body_widget())
        seg_list_header_row = QtWidgets.QHBoxLayout(self._seg_list_header)
        seg_list_header_row.setContentsMargins(0, 0, 0, 0)
        seg_list_header_row.addWidget(QtWidgets.QLabel(u"列表:"))
        self._seg_show_full_name_chk = QtWidgets.QCheckBox(u"显示完整文件名")
        seg_list_header_row.addWidget(self._seg_show_full_name_chk)
        seg_list_header_row.addStretch()
        split_editor.addWidget(self._seg_list_header)

        self._seg_list = QtWidgets.QListWidget()
        self._seg_list.setMinimumHeight(110)
        self._seg_list.setMaximumHeight(140)
        self._seg_list.setStyleSheet(
            u"""
            QListWidget::item:selected {
                background: #5f6368;
                color: #ffffff;
            }
            """
        )
        self._seg_list.currentRowChanged.connect(self._on_segment_row_changed)
        split_editor.addWidget(self._seg_list)
        _dbg("[INDOOR-SPLIT] 6 - list OK")

        split_body.addWidget(self._split_editor_wrap)

        pl.addWidget(split_grp)
        _dbg("[INDOOR] 6 - split_grp OK")

        # ── 相机导出 ─────────────────────────────────────────────
        cam_grp  = CollapsibleGroup(u"相机导出", parent=self._indoor_panel)
        cam_body = QtWidgets.QVBoxLayout(cam_grp.body_widget())
        cam_body.setContentsMargins(10, 8, 10, 10)

        cam_hint = QtWidgets.QLabel(
            u"局内页签仅导出游戏内相机（_Cam），需要时可只导出相机文件。"
        )
        cam_hint.setWordWrap(True)
        cam_hint.setStyleSheet(u"color: #98a2b3; font-size: 11px;")
        cam_body.addWidget(cam_hint)

        self._indoor_export_cam_chk = QtWidgets.QCheckBox(u"导出局内相机")
        self._indoor_only_cam_chk   = QtWidgets.QCheckBox(u"仅导出摄像机")
        cam_body.addWidget(self._indoor_export_cam_chk)
        cam_body.addWidget(self._indoor_only_cam_chk)
        self._enable_pos_chk.toggled.connect(self._update_indoor_pos_ui)
        self._follow_z_chk.toggled.connect(self._update_indoor_pos_ui)
        self._z_limit_chk.toggled.connect(self._update_indoor_pos_ui)
        self._z_hover_chk.toggled.connect(self._update_indoor_pos_ui)
        self._enable_offset_chk.toggled.connect(self._update_indoor_pos_ui)
        self._use_smooth_chk.toggled.connect(self._update_indoor_pos_ui)
        self._smooth_limit_chk.toggled.connect(self._update_indoor_pos_ui)
        self._pos_rm_limit_chk.toggled.connect(self._update_indoor_pos_ui)
        self._enable_rot_chk.toggled.connect(self._update_indoor_rot_ui)
        self._rot_custom_angle_chk.toggled.connect(self._update_indoor_rot_ui)
        self._rot_limit_chk.toggled.connect(self._update_indoor_rot_ui)
        self._enable_split_chk.toggled.connect(self._update_split_ui)
        self._seg_show_full_name_chk.toggled.connect(self._refresh_segments_list)
        self._enable_split_chk.toggled.connect(self._update_preview)
        self._indoor_export_cam_chk.toggled.connect(self._update_preview)
        self._indoor_only_cam_chk.toggled.connect(self._sync_indoor_camera_state)
        self._indoor_only_cam_chk.toggled.connect(self._update_preview)
        self._update_indoor_pos_ui()
        self._update_indoor_rot_ui()
        self._update_split_ui()
        self._refresh_segments_list()

        pl.addWidget(cam_grp)
        _dbg("[INDOOR] 7 - cam_grp OK")

        self._scroll_layout.addWidget(self._indoor_panel)
        _dbg("[INDOOR] 8 - done")

    # ── 局外面板 ──────────────────────────────────────────────────

    def _build_outdoor_panel(self):
        _dbg("[OUTDOOR] 1 - start")
        self._outdoor_panel = self._outdoor_host
        self._outdoor_panel.setObjectName(u"rmPagePanel")
        self._outdoor_panel.setVisible(False)
        pl = QtWidgets.QVBoxLayout(self._outdoor_panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(4)
        _dbg("[OUTDOOR] 2 - panel widget OK")

        # 角色列表
        char_grp  = CollapsibleGroup(u"角色清单", parent=self._outdoor_panel, expanded=True)
        _dbg("[OUTDOOR] 3 - char_grp created")
        char_body = QtWidgets.QVBoxLayout(char_grp.body_widget())
        char_body.setContentsMargins(0, 0, 0, 0)
        _dbg("[OUTDOOR] 4 - before CharacterListWidget")
        self._char_list = CharacterListWidget(parent=char_grp.body_widget())
        _dbg("[OUTDOOR] 5 - CharacterListWidget OK")
        char_body.addWidget(self._char_list)
        pl.addWidget(char_grp)
        _dbg("[OUTDOOR] 6 - char_grp added")

        morph_grp = CollapsibleGroup(u"变形器清单", parent=self._outdoor_panel, expanded=True)
        morph_body = QtWidgets.QVBoxLayout(morph_grp.body_widget())
        morph_body.setContentsMargins(0, 0, 0, 0)
        self._morpher_list = MorpherListWidget(parent=morph_grp.body_widget())
        morph_body.addWidget(self._morpher_list)
        pl.addWidget(morph_grp)
        _dbg("[OUTDOOR] 6B - morph_grp added")

        outdoor_sample_grp = QtWidgets.QGroupBox(u"FBX 发布采样精度")
        outdoor_sample_lay = QtWidgets.QVBoxLayout(outdoor_sample_grp)
        outdoor_sample_lay.setContentsMargins(10, 8, 10, 10)
        outdoor_sample_row = QtWidgets.QHBoxLayout()
        outdoor_sample_row.addWidget(QtWidgets.QLabel(u"FBX 采样率"))
        self._outdoor_proxy_sample_rate_ddl = QtWidgets.QComboBox()
        self._outdoor_proxy_sample_rate_ddl.addItem(u"30 Hz（默认 / 推荐）", 30)
        self._outdoor_proxy_sample_rate_ddl.addItem(u"60 Hz（精度补偿）", 60)
        self._outdoor_proxy_sample_rate_ddl.addItem(u"120 Hz（最高精度 / 高内存）", 120)
        self._outdoor_proxy_sample_rate_ddl.setCurrentIndex(0)
        self._outdoor_proxy_sample_rate_ddl.setToolTip(
            u"局外角色使用与局内相同的 ProxyRoot 发布。默认 30 Hz；"
            u"仅在 Unity 中仍有可见抖动时提高到 60/120 Hz。"
        )
        outdoor_sample_row.addWidget(self._outdoor_proxy_sample_rate_ddl, 1)
        outdoor_sample_lay.addLayout(outdoor_sample_row)
        outdoor_sample_hint = QtWidgets.QLabel(
            u"仅影响角色 FBX；局外相机保持原有相机导出规则。"
        )
        outdoor_sample_hint.setWordWrap(True)
        outdoor_sample_hint.setStyleSheet(u"color: #d7b56d; font-size: 11px;")
        outdoor_sample_lay.addWidget(outdoor_sample_hint)
        outdoor_sample_grp.setVisible(self._com_restore_engine == u"baselayer")
        self._outdoor_proxy_sample_rate_group = outdoor_sample_grp
        pl.addWidget(outdoor_sample_grp)

        # 命名信息
        meta_grp  = CollapsibleGroup(u"命名设置", parent=self._outdoor_panel, expanded=True)
        _dbg("[OUTDOOR] 7 - meta_grp created")
        meta_body = QtWidgets.QFormLayout(meta_grp.body_widget())
        meta_body.setContentsMargins(10, 8, 10, 10)
        _dbg("[OUTDOOR] 8 - QFormLayout OK")

        self._module_ddl = QtWidgets.QComboBox()
        from pipeline.rm_naming import (
            merge_module_folder_map,
            merge_type_folder_map,
            normalize_outdoor_asset_types,
        )
        module_items = sorted(merge_module_folder_map(self._config.get(u"module_folder_map")).keys())
        self._module_ddl.addItems(module_items or [u"UL"])
        meta_body.addRow(u"模块:", self._module_ddl)
        _dbg("[OUTDOOR] 9 - module_ddl OK")

        self._type_ddl = QtWidgets.QComboBox()
        _dbg("[OUTDOOR] 10 - type_ddl created")
        self._type_ddl.setEditable(True)
        _dbg("[OUTDOOR] 11 - setEditable OK")
        type_items = sorted(merge_type_folder_map(self._config.get(u"outdoor_type_folder_map")).keys())
        if u"Chap01" not in type_items:
            type_items.append(u"Chap01")
        self._type_ddl.addItems(type_items)
        meta_body.addRow(u"类型:", self._type_ddl)
        _dbg("[OUTDOOR] 12 - type_ddl added")

        self._asset_type_ddl = QtWidgets.QComboBox()
        asset_items = [
            x for x in normalize_outdoor_asset_types(self._config.get(u"outdoor_asset_types"))
            if x != u"Cam"
        ] or [u"Char", u"Prop"]
        self._asset_type_ddl.addItems(asset_items)
        meta_body.addRow(u"资产类型:", self._asset_type_ddl)
        _dbg("[OUTDOOR] 13 - asset_type_ddl OK")

        pl.addWidget(meta_grp)
        _dbg("[OUTDOOR] 14 - meta_grp added")

        cam_grp  = CollapsibleGroup(u"相机导出", parent=self._outdoor_panel)
        cam_body = QtWidgets.QVBoxLayout(cam_grp.body_widget())
        cam_body.setContentsMargins(10, 8, 10, 10)

        cam_hint = QtWidgets.QLabel(
            u"局外页签会按勾选角色批量生成角色 FBX，也可同时导出对应命名的相机文件。"
        )
        cam_hint.setWordWrap(True)
        cam_hint.setStyleSheet(u"color: #98a2b3; font-size: 11px;")
        cam_body.addWidget(cam_hint)

        self._outdoor_export_cam_chk = QtWidgets.QCheckBox(u"导出局外相机")
        self._outdoor_only_cam_chk   = QtWidgets.QCheckBox(u"仅导出摄像机")
        cam_body.addWidget(self._outdoor_export_cam_chk)
        cam_body.addWidget(self._outdoor_only_cam_chk)
        self._char_list.changed.connect(self._update_preview)
        self._morpher_list.changed.connect(self._update_preview)
        self._module_ddl.currentIndexChanged.connect(self._update_preview)
        self._asset_type_ddl.currentIndexChanged.connect(self._update_preview)
        self._outdoor_export_cam_chk.toggled.connect(self._update_preview)
        self._outdoor_only_cam_chk.toggled.connect(self._sync_outdoor_camera_state)
        self._outdoor_only_cam_chk.toggled.connect(self._update_preview)
        if self._type_ddl.lineEdit() is not None:
            self._type_ddl.lineEdit().textChanged.connect(self._update_preview)
        self._type_ddl.currentIndexChanged.connect(self._update_preview)

        pl.addWidget(cam_grp)
        _dbg("[OUTDOOR] 14B - cam_grp added")

        _dbg("[OUTDOOR] 15 - done")
        self._outdoor_built = True
        if self._morpher_list is not None:
            self._morpher_list.refresh()

    def _ensure_outdoor_panel(self):
        if self._outdoor_built:
            return
        self._build_outdoor_panel()
        _dbg("[BUILD_UI] F - outdoor panel OK")

    # ── 事件处理 ──────────────────────────────────────────────────

    def _on_type_changed(self):
        is_indoor = self._type_indoor.isChecked()
        self._indoor_panel.setVisible(is_indoor)
        if not is_indoor:
            self._ensure_outdoor_panel()
        if self._outdoor_panel is not None:
            self._outdoor_panel.setVisible(not is_indoor)
        self._batch_btn.setEnabled(is_indoor)
        if not is_indoor and self._char_list is not None:
            self._char_list.refresh()
        if not is_indoor and self._morpher_list is not None:
            self._morpher_list.refresh()
        self._update_preview()

    def _auto_detect(self):
        try:
            from core.rm_scene import auto_detect_scene_objects
            self._bip_obj, self._root_obj = auto_detect_scene_objects()
        except Exception as e:
            print(u"[RMTool] 自动检测失败: {0}".format(e))
            self._bip_obj  = None
            self._root_obj = None
        self._update_obj_status()

    def _get_current_indoor_action_name(self):
        action_name = u""
        if rt is not None:
            try:
                from pipeline.rm_naming import validate_indoor_name
                max_name = os.path.splitext(_as_text(rt.maxFileName))[0]
                ok, _, parsed = validate_indoor_name(
                    max_name, self._config.get(u"category_folder_map")
                )
                if ok:
                    action_name = parsed.get(u"action_name", u"")
            except Exception:
                action_name = u""
        return action_name

    def _is_wallhit_scene(self):
        if rt is None:
            return False
        try:
            from core.rm_wallhit import is_wallhit_filename
            return is_wallhit_filename(_as_text(rt.maxFileName))
        except Exception:
            return False

    def _apply_wallhit_root_motion_mode(self, active):
        """让面板明确切换到 WallHit 分段算法，并锁住会被忽略的通用选项。"""
        active = bool(active and self._type_indoor.isChecked())
        self._wallhit_root_motion_active = active
        if not hasattr(self, "_wallhit_mode_hint"):
            return

        self._wallhit_mode_hint.setVisible(active)
        if active:
            self._set_checked(self._enable_pos_chk, True)
            self._set_checked(self._follow_x_chk, False)
            self._set_checked(self._follow_y_chk, True)
            self._set_checked(self._follow_z_chk, True)
            self._set_checked(self._enable_rot_chk, False)
            self._set_checked(self._enable_offset_chk, False)
            self._set_checked(self._use_smooth_chk, False)
            self._set_checked(self._z_limit_chk, False)
            self._set_checked(self._z_hover_chk, False)
            self._set_checked(self._smooth_limit_chk, False)
            self._set_checked(self._pos_rm_limit_chk, False)
            self._set_checked(self._enable_split_chk, True)
            if hasattr(self, "_rot_custom_angle_chk"):
                self._set_checked(self._rot_custom_angle_chk, False)
                self._set_checked(self._rot_limit_chk, False)

        self._enable_pos_chk.setEnabled(not active)
        self._pos_detail_wrap.setEnabled(not active)
        self._enable_rot_chk.setEnabled(not active)
        if hasattr(self, "_rot_detail_wrap"):
            self._rot_detail_wrap.setEnabled(not active)
        self._enable_split_chk.setEnabled(not active)
        self._update_indoor_pos_ui()
        self._update_indoor_rot_ui()
        self._update_split_ui()

    def _apply_indoor_motion_defaults_from_scene_name(self):
        """按当前文件名为局内 Root Motion 设置默认勾选。"""
        action_name = self._get_current_indoor_action_name()

        # 通用基线：默认只开 Y 轴位移，其他额外项全部关闭。
        self._enable_pos_chk.setChecked(True)
        self._follow_x_chk.setChecked(False)
        self._follow_y_chk.setChecked(True)
        self._follow_z_chk.setChecked(False)
        self._enable_rot_chk.setChecked(False)
        self._enable_offset_chk.setChecked(False)
        self._use_smooth_chk.setChecked(False)
        self._z_limit_chk.setChecked(False)
        self._z_hover_chk.setChecked(False)
        self._smooth_limit_chk.setChecked(False)
        self._pos_rm_limit_chk.setChecked(False)
        if hasattr(self, "_rot_custom_angle_chk"):
            self._rot_custom_angle_chk.setChecked(False)
            self._rot_limit_chk.setChecked(False)

        action_lower = action_name.lower()
        if u"idle" in action_lower:
            self._enable_pos_chk.setChecked(False)
            self._follow_x_chk.setChecked(False)
            self._follow_y_chk.setChecked(False)
            self._follow_z_chk.setChecked(False)
            self._enable_rot_chk.setChecked(False)
            _dbg("[INDOOR] apply motion default: Idle -> disable pos/rot")
        elif u"turn" in action_lower:
            self._enable_pos_chk.setChecked(False)
            self._follow_x_chk.setChecked(False)
            self._follow_y_chk.setChecked(False)
            self._follow_z_chk.setChecked(False)
            self._enable_rot_chk.setChecked(True)
            _dbg("[INDOOR] apply motion default: Turn -> rot only")
        else:
            _dbg("[INDOOR] apply motion default: generic -> Y pos only")

        self._apply_wallhit_root_motion_mode(self._is_wallhit_scene())
        self._update_indoor_pos_ui()
        self._update_indoor_rot_ui()

    def _update_obj_status(self):
        if self._bip_obj and self._root_obj:
            self._obj_status.setText(
                u"✓  Bip: {0}   Root: {1}".format(
                    self._bip_obj.name, self._root_obj.name
                )
            )
            self._obj_status.setStyleSheet(u"color: #6dcc6d; font-size: 11px;")
        elif self._bip_obj:
            self._obj_status.setText(u"⚠  已找到 Bip，未找到 Root 骨骼")
            self._obj_status.setStyleSheet(u"color: #e8a000; font-size: 11px;")
        else:
            self._obj_status.setText(u"✗  未检测到 Biped 对象")
            self._obj_status.setStyleSheet(u"color: #ff6060; font-size: 11px;")

    def _pick_bip(self):
        obj = rt.pickObject(message=u"请拾取 Biped 根骨骼（Bip001）")
        if obj and rt.classof(obj) == rt.Biped_Object:
            self._bip_obj = obj
            self._bip_btn.setText(u"Bip: " + obj.name)
            self._update_obj_status()
        else:
            QtWidgets.QMessageBox.warning(self, u"错误", u"请选择一个 Biped 对象")

    def _pick_root(self):
        obj = rt.pickObject(message=u"请拾取 Root 骨骼")
        if obj:
            self._root_obj = obj
            self._root_btn.setText(u"Root: " + obj.name)
            if rt.classof(obj.rotation.controller) != rt.Euler_XYZ:
                obj.rotation.controller = rt.Euler_XYZ()
            self._update_obj_status()

    def _add_segment(self):
        preset = self._seg_preset_ddl.currentText().strip()
        name = self._seg_suffix_edit.text().strip().lstrip(u"_")
        s = self._seg_start_spn.value()
        e = self._seg_end_spn.value()
        if s >= e:
            QtWidgets.QMessageBox.warning(self, u"错误", u"开始帧必须小于结束帧")
            return

        if preset == u"Ultra":
            insert_row = len(self._split_data)
            self._split_data.append(self._make_segment(u"Ultra - Pre", u"Pre", s, e, u""))
            self._split_data.append(self._make_segment(u"Ultra - 无后缀", u"", s, e, u""))
            self._refresh_segments_list(select_row=-1)
        else:
            if not name:
                QtWidgets.QMessageBox.warning(self, u"错误", u"后缀不能为空")
                return
            self._split_data.append(self._make_segment(name, name, s, e, u"_"))
            self._refresh_segments_list(select_row=-1)

        self._seg_start_spn.setValue(e)
        self._update_preview()

    def _del_segment(self):
        row = self._seg_list.currentRow()
        if row >= 0:
            del self._split_data[row]
            next_row = min(row, len(self._split_data) - 1)
            self._refresh_segments_list(select_row=next_row)
            self._update_preview()

    def _update_preview(self):
        try:
            if self._type_indoor.isChecked():
                entries = self._build_indoor_preview_entries()
            else:
                entries = self._build_outdoor_preview_entries()
            self._set_preview_entries(entries)
        except Exception:
            self._set_preview_entries([])

    def _sync_seg_suffix_from_preset(self, *args):
        if hasattr(self, "_seg_suffix_edit") and hasattr(self, "_seg_preset_ddl"):
            preset = self._seg_preset_ddl.currentText()
            is_ultra = (preset == u"Ultra")
            self._seg_suffix_edit.setEnabled(not is_ultra)
            if is_ultra:
                self._seg_suffix_edit.setText(u"Ultra")
            else:
                self._seg_suffix_edit.setText(preset)
                self._apply_airhit_segment_range_from_preset(preset)

    def _apply_airhit_segment_range_from_preset(self, preset):
        if not self._type_indoor.isChecked():
            return
        if self._get_current_indoor_action_name().lower() != u"airhit":
            return
        frame_range = AIRHIT_SEGMENT_RANGES.get(_as_text(preset).strip())
        if not frame_range:
            return

        start_f, end_f = frame_range
        self._segment_form_sync = True
        try:
            self._seg_start_spn.setValue(int(start_f))
            self._seg_end_spn.setValue(int(end_f))
        finally:
            self._segment_form_sync = False

    def _update_indoor_pos_ui(self, *args):
        enabled = self._enable_pos_chk.isChecked()
        detail_open = enabled
        self._pos_detail_wrap.setVisible(detail_open)

        show_z = detail_open and self._follow_z_chk.isChecked()
        self._z_settings_wrap.setVisible(show_z)
        self._z_limit_wrap.setVisible(show_z and self._z_limit_chk.isChecked())
        self._z_hover_wrap.setVisible(show_z and self._z_hover_chk.isChecked())

        show_offset_block = detail_open
        self._offset_settings_wrap.setVisible(show_offset_block)
        self._offset_controls_wrap.setVisible(
            show_offset_block and self._enable_offset_chk.isChecked()
        )

        show_smooth_block = detail_open
        self._smooth_settings_wrap.setVisible(show_smooth_block)
        self._smooth_controls_wrap.setVisible(
            show_smooth_block and self._use_smooth_chk.isChecked()
        )
        self._smooth_limit_wrap.setVisible(
            show_smooth_block
            and self._use_smooth_chk.isChecked()
            and self._smooth_limit_chk.isChecked()
        )

        self._pos_rm_range_wrap.setVisible(detail_open)
        self._pos_rm_limit_wrap.setVisible(
            detail_open and self._pos_rm_limit_chk.isChecked()
        )

    def _update_indoor_rot_ui(self, *args):
        if not hasattr(self, "_rot_detail_wrap"):
            return
        enabled = self._enable_rot_chk.isChecked()
        self._rot_detail_wrap.setVisible(enabled)
        self._rot_custom_controls_wrap.setVisible(
            enabled and self._rot_custom_angle_chk.isChecked()
        )
        self._rot_limit_wrap.setVisible(
            enabled and self._rot_limit_chk.isChecked()
        )

    def _get_rot_custom_dir(self):
        if not hasattr(self, "_rot_custom_dir_ddl"):
            return u"auto"
        data = self._rot_custom_dir_ddl.currentData()
        if data is None:
            text = _as_text(self._rot_custom_dir_ddl.currentText())
            if u"右" in text:
                return u"right"
            if u"左" in text:
                return u"left"
            return u"auto"
        want = _as_text(data).lower()
        if want in (u"auto", u"left", u"right"):
            return want
        return u"auto"

    def _set_rot_custom_dir(self, direction):
        if not hasattr(self, "_rot_custom_dir_ddl"):
            return
        want = _as_text(direction or u"auto").lower()
        if want not in (u"auto", u"left", u"right"):
            want = u"auto"
        for i in range(self._rot_custom_dir_ddl.count()):
            if _as_text(self._rot_custom_dir_ddl.itemData(i)) == want:
                self._rot_custom_dir_ddl.setCurrentIndex(i)
                return
        self._rot_custom_dir_ddl.setCurrentIndex(0)

    def _get_proxy_sample_rate(self):
        combo = getattr(self, "_proxy_sample_rate_ddl", None)
        if combo is None:
            return 30
        try:
            value = int(combo.currentData())
        except Exception:
            try:
                value = int(_as_text(combo.currentText()).split()[0])
            except Exception:
                value = 30
        return value if value in (30, 60, 120) else 30

    def _set_proxy_sample_rate(self, value):
        combo = getattr(self, "_proxy_sample_rate_ddl", None)
        if combo is None:
            return
        try:
            want = int(value)
        except Exception:
            want = 30
        if want not in (30, 60, 120):
            want = 30
        for i in range(combo.count()):
            try:
                if int(combo.itemData(i)) == want:
                    combo.setCurrentIndex(i)
                    return
            except Exception:
                pass
        combo.setCurrentIndex(0)

    def _get_outdoor_proxy_sample_rate(self):
        combo = getattr(self, "_outdoor_proxy_sample_rate_ddl", None)
        if combo is None:
            return 30
        try:
            value = int(combo.currentData())
        except Exception:
            try:
                value = int(_as_text(combo.currentText()).split()[0])
            except Exception:
                value = 30
        return value if value in (30, 60, 120) else 30

    def _set_outdoor_proxy_sample_rate(self, value):
        combo = getattr(self, "_outdoor_proxy_sample_rate_ddl", None)
        if combo is None:
            return
        try:
            want = int(value)
        except Exception:
            want = 30
        if want not in (30, 60, 120):
            want = 30
        for i in range(combo.count()):
            try:
                if int(combo.itemData(i)) == want:
                    combo.setCurrentIndex(i)
                    return
            except Exception:
                pass
        combo.setCurrentIndex(0)

    def _update_split_ui(self, *args):
        enabled = self._enable_split_chk.isChecked()
        self._split_editor_wrap.setVisible(enabled)
        if not enabled:
            self._seg_list.clearSelection()
            self._on_segment_row_changed(-1)

    def _make_segment(self, label, export_suffix, start_f, end_f, joiner=u"_"):
        return (label, export_suffix, int(start_f), int(end_f), joiner)

    def _get_segment_parts(self, seg):
        if len(seg) >= 5:
            return seg[0], seg[1], seg[2], seg[3], seg[4]
        if len(seg) == 3:
            seg_name, start_f, end_f = seg
            return seg_name, seg_name, start_f, end_f, u"_"
        raise ValueError(u"invalid split segment data")

    def _build_segment_export_suffix(self, seg):
        _, export_suffix, _, _, joiner = self._get_segment_parts(seg)
        if not export_suffix:
            return u""
        return joiner + export_suffix

    def _build_segment_full_name(self, base_name, seg):
        return base_name + self._build_segment_export_suffix(seg)

    def _on_segment_row_changed(self, row):
        has_row = (row is not None and row >= 0 and row < len(self._split_data))
        if not has_row:
            return
        _, _, start_f, end_f, _ = self._get_segment_parts(self._split_data[row])
        self._segment_form_sync = True
        try:
            self._seg_start_spn.setValue(int(start_f))
            self._seg_end_spn.setValue(int(end_f))
        finally:
            self._segment_form_sync = False

    def _commit_selected_segment_range(self):
        if self._segment_form_sync:
            return
        row = self._seg_list.currentRow()
        if row < 0 or row >= len(self._split_data):
            return
        s = self._seg_start_spn.value()
        e = self._seg_end_spn.value()
        if s >= e:
            self._on_segment_row_changed(row)
            return
        label, export_suffix, _, _, joiner = self._get_segment_parts(self._split_data[row])
        old_seg = self._split_data[row]
        new_seg = self._make_segment(label, export_suffix, s, e, joiner)
        if new_seg != old_seg:
            self._split_data[row] = new_seg
            self._refresh_segments_list(select_row=row)
            self._update_preview()

    def _refresh_segments_list(self, *args, **kwargs):
        current_row = kwargs.get("select_row", self._seg_list.currentRow())
        self._seg_list.clear()
        base_name = u""
        if rt is not None:
            try:
                from pipeline.rm_naming import clean_string_native
                base_name = clean_string_native(
                    os.path.splitext(_as_text(rt.maxFileName))[0],
                    u""
                )
            except Exception:
                base_name = u""
        show_full_name = self._seg_show_full_name_chk.isChecked()
        for seg in self._split_data:
            label, _, start_f, end_f, _ = self._get_segment_parts(seg)
            if show_full_name and base_name:
                text = u"{0}  [{1} ~ {2}]".format(
                    self._build_segment_full_name(base_name, seg), start_f, end_f
                )
            else:
                text = u"{0}  [{1} ~ {2}]".format(label, start_f, end_f)
            self._seg_list.addItem(text)
        if self._split_data and current_row is not None and current_row >= 0:
            self._seg_list.setCurrentRow(min(current_row, len(self._split_data) - 1))
        else:
            self._seg_list.setCurrentRow(-1)
            self._on_segment_row_changed(-1)

    def _sync_scene_frame_ranges(self):
        if rt is None:
            return
        start_f = int(rt.animationRange.start.frame)
        end_f = int(rt.animationRange.end.frame)
        for widget in [
            self._seg_start_spn,
            self._z_limit_start_spn,
            self._smooth_limit_start_spn,
            self._z_hover_start_spn,
            self._pos_rm_start_spn,
            self._rot_limit_start_spn,
        ]:
            widget.setValue(start_f)
        for widget in [
            self._seg_end_spn,
            self._z_limit_end_spn,
            self._smooth_limit_end_spn,
            self._z_hover_end_spn,
            self._pos_rm_end_spn,
            self._rot_limit_end_spn,
        ]:
            widget.setValue(end_f)

    def _sync_indoor_camera_state(self, checked):
        if checked:
            self._indoor_export_cam_chk.setChecked(True)

    def _sync_outdoor_camera_state(self, checked):
        if checked and self._outdoor_built:
            self._outdoor_export_cam_chk.setChecked(True)

    def _set_combo_text(self, combo, text):
        blocked = combo.blockSignals(True)
        try:
            if combo.isEditable():
                combo.setEditText(text)
                return
            idx = combo.findText(text)
            if idx < 0:
                combo.addItem(text)
                idx = combo.findText(text)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        finally:
            combo.blockSignals(blocked)

    def _get_outdoor_asset_type(self):
        return self._asset_type_ddl.currentText().strip() or u"Char"

    def _get_outdoor_source_info(self, sync_widgets=True):
        if rt is None:
            return None
        from pipeline.rm_naming import parse_outdoor_source_name

        ok, _, parsed = parse_outdoor_source_name(
            _as_text(rt.maxFileName),
            self._config.get(u"module_folder_map"),
            self._config.get(u"outdoor_type_folder_map"),
        )
        if not ok:
            return None
        if sync_widgets and self._outdoor_built:
            self._set_combo_text(self._module_ddl, parsed[u"module_code"])
            self._set_combo_text(self._type_ddl, parsed[u"type_code"])
        return parsed

    def _refresh_outdoor_state_from_scene(self):
        if not self._outdoor_built:
            return
        self._get_outdoor_source_info(sync_widgets=True)
        if self._char_list is not None:
            self._char_list.refresh()

    def _set_preview_entries(self, entries):
        if not entries:
            self._preview_text.setPlainText(u"None")
            return
        self._preview_text.setPlainText(u"\n".join(entries))

    def _apply_styles(self):
        self.setStyleSheet(
            u"""
            QDialog#rmWindow {
                background: #141922;
                color: #e6ebf2;
            }
            QWidget#rmScrollContent, QWidget#rmPagePanel {
                background: transparent;
            }
            QLabel {
                color: #dbe2ea;
                background: transparent;
            }
            QGroupBox#rmTypeFrame {
                border: 1px solid #2b3445;
                border-radius: 10px;
                margin-top: 12px;
                padding: 10px 10px 8px 10px;
                font-weight: bold;
                background: #1b2230;
            }
            QGroupBox#rmTypeFrame::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
                color: #8ea0b8;
            }
            QRadioButton {
                spacing: 0px;
                padding: 8px 14px;
                border: 1px solid #33405a;
                border-radius: 8px;
                background: #202a39;
                color: #c8d1dd;
                font-weight: bold;
            }
            QRadioButton::indicator {
                width: 0px;
                height: 0px;
            }
            QRadioButton:checked {
                background: #3f6ed8;
                border: 1px solid #4d7bee;
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
            QPushButton:pressed {
                background: #223047;
            }
            QLineEdit, QComboBox, QPlainTextEdit, QListWidget {
                background: #0f141d;
                color: #edf2f8;
                border: 1px solid #303a4c;
                border-radius: 8px;
                padding: 6px 8px;
                selection-background-color: #3f6ed8;
            }
            QSpinBox, QDoubleSpinBox {
                background: #0f141d;
                color: #edf2f8;
                border: 1px solid #303a4c;
                border-radius: 8px;
                padding: 4px 6px;
                min-height: 24px;
                selection-background-color: #3f6ed8;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                width: 18px;
                border: none;
                background: transparent;
            }
            QCheckBox {
                spacing: 8px;
                padding: 4px 0px;
                background: transparent;
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
            QCheckBox::indicator:hover {
                border: 1px solid #7e94b8;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QTabWidget#rmMainTabWidget::pane {
                border: 1px solid #2b3445;
                border-radius: 10px;
                background: #1b2230;
                top: 6px;
                padding: 4px;
            }
            QTabWidget#rmMainTabWidget QTabBar::tab {
                min-width: 128px;
                padding: 10px 14px;
                margin-right: 4px;
                background: #202a39;
                color: #c8d1dd;
                border: 1px solid #31405a;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabWidget#rmMainTabWidget QTabBar::tab:selected {
                background: #3f6ed8;
                color: white;
                border: 1px solid #4d7bee;
            }
            QWidget#rmGroupBody {
                background: #1b2230;
                border: 1px solid #2d394d;
                border-top: none;
                border-radius: 0 0 12px 12px;
            }
            QFrame#rmPosSectionCard {
                background: #151c28;
                border: 1px solid #2e394d;
                border-radius: 10px;
            }
            QFrame#rmPosSubSectionCard {
                background: #101722;
                border: 1px solid #263246;
                border-radius: 8px;
            }
            QLabel#rmPosSectionTitle {
                color: #edf2f8;
                font-size: 12px;
                font-weight: bold;
            }
            QLabel#rmPosSectionHint {
                color: #8fa0b8;
                font-size: 11px;
            }
            QLabel#rmPosSubSectionTitle {
                color: #dbe6f7;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#rmGroupToggle {
                background: #212c3d;
                border: 1px solid #31405a;
                border-radius: 12px 12px 0 0;
                text-align: left;
                padding: 9px 12px;
                font-weight: bold;
            }
            QPushButton#rmGroupToggle:hover {
                background: #273449;
            }
            QPushButton#rmGroupToggle:checked {
                background: #25344d;
            }
            QFrame#rmPreviewFrame {
                background: #18202d;
                border: 1px solid #2e3a4f;
                border-radius: 12px;
            }
            QPlainTextEdit#rmPreviewText {
                font-family: Consolas;
                background: #0f141d;
                color: #7ddc8a;
            }
            QListWidget::item {
                min-height: 24px;
                padding: 2px 6px;
                color: #dbe2ea;
                background: transparent;
            }
            QListWidget::item:hover {
                background: #283246;
            }
            QListWidget::item:selected {
                background: #3f6ed8;
                color: #ffffff;
            }
            QListWidget#opWeaponStateList {
                outline: none;
                padding: 2px;
            }
            QListWidget#opWeaponStateList::item {
                min-height: 28px;
                padding: 4px 10px;
                color: #edf2f8;
                background: transparent;
            }
            QListWidget#opWeaponStateList::item:hover {
                background: #2a3548;
            }
            QListWidget#opWeaponStateList::item:selected {
                background: #3f6ed8;
                color: #ffffff;
            }
            QListWidget#opWeaponStateList::item:selected:active {
                background: #3562c4;
                color: #ffffff;
            }
            QListWidget#rmCharList {
                padding: 4px;
            }
            QListWidget#rmCharList::item {
                min-height: 26px;
                padding: 2px 6px;
                border-radius: 6px;
                background: transparent;
                color: #dbe2ea;
            }
            QListWidget#rmCharList::item:hover {
                background: #313a49;
            }
            QListWidget#rmCharList::item:selected {
                background: transparent;
                color: #dbe2ea;
            }
            QListWidget#rmCharList::item:selected:hover {
                background: #313a49;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 6px 2px 6px 2px;
            }
            QScrollBar::handle:vertical {
                background: #5e6f8b;
                border-radius: 4px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover {
                background: #7c90b2;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
                height: 0px;
            }
            """
        )

    def _build_indoor_preview_entries(self):
        if rt is None:
            return []
        from pipeline.rm_naming import clean_string_native

        max_name = os.path.splitext(_as_text(rt.maxFileName))[0]
        suffixes = [u""]
        if self._enable_split_chk.isChecked() and self._split_data:
            suffixes = [self._build_segment_export_suffix(seg) for seg in self._split_data]

        entries = []
        for suffix in suffixes:
            base_name = clean_string_native(max_name, suffix) or u"Untitled"
            if not self._indoor_only_cam_chk.isChecked():
                entries.append(base_name + u".fbx")
            if self._indoor_export_cam_chk.isChecked() or self._indoor_only_cam_chk.isChecked():
                entries.append(base_name + u"_Cam.fbx")
        return self._dedupe_entries(entries)

    def _build_outdoor_preview_entries(self):
        if not self._outdoor_built or self._char_list is None:
            return []
        from pipeline.rm_naming import (
            build_outdoor_camera_export_name,
            build_outdoor_character_export_name,
        )

        source_info = self._get_outdoor_source_info(sync_widgets=True)
        if source_info is None:
            return []

        asset_type = self._get_outdoor_asset_type()
        selected_chars = self._char_list.get_selected_chars()

        entries = []
        if not self._outdoor_only_cam_chk.isChecked():
            for char in selected_chars:
                entries.append(
                    build_outdoor_character_export_name(
                        source_info, char[u"name"], asset_type
                    ) + u".fbx"
                )
        if self._outdoor_export_cam_chk.isChecked() or self._outdoor_only_cam_chk.isChecked():
            entries.append(build_outdoor_camera_export_name(source_info) + u".fbx")
        return self._dedupe_entries(entries)

    def _dedupe_entries(self, entries):
        seen = set()
        result = []
        for entry in entries:
            if entry in seen:
                continue
            seen.add(entry)
            result.append(entry)
        return result

    def _open_settings(self):
        from ui.rm_settings_dialog import SettingsDialog
        dlg = SettingsDialog(self._config, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self._config = dlg.get_config()
            if not self._save_config():
                QtWidgets.QMessageBox.critical(
                    self,
                    u"保存设置失败",
                    u"设置没有成功写入配置文件，请检查工具目录权限或配置文件是否被占用。",
                )
                return
            try:
                self._binding_update_tab.on_config_updated(self._config)
            except Exception:
                pass
            self._update_preview()
            self._refresh_dev_upload_button_visibility()

    def _upload_update_to_public(self):
        if not self._is_dev_machine_install():
            QtWidgets.QMessageBox.warning(
                self,
                u"不可用",
                u"此功能仅在开发机可用：\n"
                u"1）安装配置里 SourceRoot 指向本地工程且与公盘不同；或\n"
                u"2）在本地工程根目录放置开发机标记文件（见设置 → 高级设置 → 开发机）。",
            )
            return
        source, public = self._dev_upload_paths()
        msg = (
            u"将把本地工程目录中的所有工具文件复制到公盘工具目录，同名文件会直接覆盖。\n\n"
            u"本地工程:\n{0}\n\n"
            u"公盘目录:\n{1}\n\n"
            u"确认上传？"
        ).format(source, public)
        if QtWidgets.QMessageBox.question(self, u"上传工具更新", msg) != QtWidgets.QMessageBox.Yes:
            return
        try:
            copied, deleted = self._copy_dev_tool_folder(source, public)
            QtWidgets.QMessageBox.information(
                self,
                u"上传完成",
                u"已上传工具更新，共复制 {0} 个文件，删除 {1} 个公盘旧文件。\n关键文件校验通过，同事可重新安装或点击更新获取新版本。".format(copied, deleted),
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, u"上传失败", _as_text(e))

    def _on_reset_clicked(self):
        self._reset(reload_publish_settings=False)

    def _reset(self, reload_publish_settings=True):
        if self._indoor_resume_pending and self._indoor_resume_ctx:
            try:
                orig_full = self._indoor_resume_ctx.get(u"orig_full", u"")
                temp_path = self._indoor_resume_ctx.get(u"temp_path", u"")
                if orig_full:
                    rt.loadMaxFile(orig_full, quiet=True)
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
        self._bip_obj    = None
        self._root_obj   = None
        self._split_data = []
        self._indoor_resume_pending = False
        self._indoor_resume_ctx = None
        self._seg_list.clear()
        self._manual_pick_chk.setChecked(False)
        self._enable_split_chk.setChecked(False)
        self._z_hover_chk.setChecked(False)
        self._seg_show_full_name_chk.setChecked(False)
        self._indoor_export_cam_chk.setChecked(False)
        self._indoor_only_cam_chk.setChecked(False)
        if self._outdoor_built:
            self._outdoor_export_cam_chk.setChecked(False)
            self._outdoor_only_cam_chk.setChecked(False)
        self._z_thres_spn.setValue(50.0)
        self._z_weight_spn.setValue(1.0)
        self._z_hover_height_spn.setValue(150.0)
        self._filter_spn.setValue(10.0)
        self._smooth_str_spn.setValue(1)
        self._set_proxy_sample_rate(30)
        self._set_outdoor_proxy_sample_rate(30)
        self._seg_preset_ddl.setCurrentIndex(0)
        self._seg_suffix_edit.setText(u"Start")
        self._export_btn.setText(u"发布")
        self._refresh_segments_list()
        self._sync_scene_frame_ranges()
        self._apply_indoor_motion_defaults_from_scene_name()
        self._refresh_outdoor_state_from_scene()
        self._update_indoor_pos_ui()
        self._update_split_ui()
        self._auto_detect()
        if reload_publish_settings:
            self._load_publish_settings_for_current_scene()
        self._update_preview()
        self._scene_signature = self._current_scene_signature()

    # ── 发布设置持久化 ──────────────────────────────────────────────

    def _current_max_full_path(self):
        if rt is None:
            return u""
        return _as_text(rt.maxFilePath) + _as_text(rt.maxFileName)

    def _node_name(self, node):
        try:
            if rt is not None and node is not None and rt.isValidNode(node):
                return _as_text(node.name)
        except Exception:
            pass
        return u""

    def _node_by_name(self, name):
        name = _as_text(name).strip()
        if rt is None or not name:
            return None
        try:
            node = rt.getNodeByName(name)
            if node is not None and rt.isValidNode(node):
                return node
        except Exception:
            pass
        return None

    def _set_checked(self, widget, value):
        blocked = widget.blockSignals(True)
        try:
            widget.setChecked(bool(value))
        finally:
            widget.blockSignals(blocked)

    def _set_value(self, widget, value):
        blocked = widget.blockSignals(True)
        try:
            widget.setValue(value)
        except Exception:
            pass
        finally:
            widget.blockSignals(blocked)

    def _serialize_split_data(self):
        result = []
        for seg in self._split_data:
            try:
                label, export_suffix, start_f, end_f, joiner = self._get_segment_parts(seg)
                result.append({
                    u"label": _as_text(label),
                    u"export_suffix": _as_text(export_suffix),
                    u"start": int(start_f),
                    u"end": int(end_f),
                    u"joiner": _as_text(joiner),
                })
            except Exception:
                pass
        return result

    def _deserialize_split_data(self, raw_items):
        result = []
        for item in raw_items or []:
            try:
                if isinstance(item, dict):
                    label = item.get(u"label", item.get(u"name", u""))
                    export_suffix = item.get(u"export_suffix", label)
                    start_f = item.get(u"start", item.get(u"start_f", 0))
                    end_f = item.get(u"end", item.get(u"end_f", 0))
                    joiner = item.get(u"joiner", u"_")
                else:
                    label, export_suffix, start_f, end_f, joiner = self._get_segment_parts(item)
                result.append(self._make_segment(label, export_suffix, start_f, end_f, joiner))
            except Exception:
                pass
        return result

    def _collect_publish_settings_data(self):
        data = {
            u"publish_type": u"indoor" if self._type_indoor.isChecked() else u"outdoor",
            u"indoor": {
                u"manual_pick": self._manual_pick_chk.isChecked(),
                u"bip_name": self._node_name(self._bip_obj),
                u"root_name": self._node_name(self._root_obj),
                u"enable_pos": self._enable_pos_chk.isChecked(),
                u"follow_x": self._follow_x_chk.isChecked(),
                u"follow_y": self._follow_y_chk.isChecked(),
                u"follow_z": self._follow_z_chk.isChecked(),
                u"z_thres_cm": self._z_thres_spn.value(),
                u"z_weight": self._z_weight_spn.value(),
                u"z_limit_range": self._z_limit_chk.isChecked(),
                u"z_limit_start": self._z_limit_start_spn.value(),
                u"z_limit_end": self._z_limit_end_spn.value(),
                u"z_hover": self._z_hover_chk.isChecked(),
                u"z_hover_height_cm": self._z_hover_height_spn.value(),
                u"z_hover_start": self._z_hover_start_spn.value(),
                u"z_hover_end": self._z_hover_end_spn.value(),
                u"enable_offset": self._enable_offset_chk.isChecked(),
                u"offset_x": self._offset_x_spn.value(),
                u"offset_y": self._offset_y_spn.value(),
                u"offset_z": self._offset_z_spn.value(),
                u"use_smooth": self._use_smooth_chk.isChecked(),
                u"filter_val": self._filter_spn.value(),
                u"smooth_str": self._smooth_str_spn.value(),
                u"smooth_limit_range": self._smooth_limit_chk.isChecked(),
                u"smooth_limit_start": self._smooth_limit_start_spn.value(),
                u"smooth_limit_end": self._smooth_limit_end_spn.value(),
                u"pos_rm_limit_range": self._pos_rm_limit_chk.isChecked(),
                u"pos_rm_start": self._pos_rm_start_spn.value(),
                u"pos_rm_end": self._pos_rm_end_spn.value(),
                u"enable_rot": self._enable_rot_chk.isChecked(),
                u"rot_custom_angle": self._rot_custom_angle_chk.isChecked(),
                u"rot_custom_degrees": self._rot_custom_degrees_spn.value(),
                u"rot_custom_dir": self._get_rot_custom_dir(),
                u"rot_limit_range": self._rot_limit_chk.isChecked(),
                u"rot_limit_start": self._rot_limit_start_spn.value(),
                u"rot_limit_end": self._rot_limit_end_spn.value(),
                u"enable_split": self._enable_split_chk.isChecked(),
                u"split_data": self._serialize_split_data(),
                u"show_split_full_name": self._seg_show_full_name_chk.isChecked(),
                u"segment_preset": self._seg_preset_ddl.currentText(),
                u"segment_suffix": self._seg_suffix_edit.text(),
                u"export_cam": self._indoor_export_cam_chk.isChecked(),
                u"only_cam": self._indoor_only_cam_chk.isChecked(),
                u"proxy_sample_rate_hz": self._get_proxy_sample_rate(),
            },
        }
        if self._outdoor_built and self._char_list is not None:
            data[u"outdoor"] = {
                u"module": self._module_ddl.currentText(),
                u"type_code": self._type_ddl.currentText(),
                u"asset_type": self._asset_type_ddl.currentText(),
                u"export_cam": self._outdoor_export_cam_chk.isChecked(),
                u"only_cam": self._outdoor_only_cam_chk.isChecked(),
                u"proxy_sample_rate_hz": self._get_outdoor_proxy_sample_rate(),
                u"checked_char_names": self._char_list.get_checked_names(),
                u"checked_morpher_names": (
                    self._morpher_list.get_checked_names()
                    if self._morpher_list is not None
                    else []
                ),
            }
        return data

    def _save_publish_settings_for_current_scene(self, max_path=None, data=None):
        max_path = _as_text(max_path) or self._current_max_full_path()
        if not max_path:
            return False
        try:
            from pipeline.publish_settings import merge_publish_settings_data, save_publish_settings
            payload = data if isinstance(data, dict) else self._collect_publish_settings_data()
            payload = merge_publish_settings_data(max_path, payload)
            ok, msg = save_publish_settings(max_path, payload)
            if ok:
                _publog(u"publish settings saved: {0}".format(msg))
            else:
                _publog(u"publish settings save failed: {0}".format(msg))
            return bool(ok)
        except Exception as e:
            _publog(u"publish settings save exception: {0}".format(_as_text(e)))
        return False

    def _load_publish_settings_for_current_scene(self):
        max_path = self._current_max_full_path()
        if not max_path:
            return False
        try:
            from pipeline.publish_settings import load_publish_settings
            data = load_publish_settings(max_path)
        except Exception as e:
            _publog(u"publish settings load exception: {0}".format(_as_text(e)))
            return False
        if not isinstance(data, dict):
            return False
        try:
            self._apply_publish_settings_data(data)
            _publog(u"publish settings loaded for: {0}".format(max_path))
            return True
        except Exception as e:
            import traceback
            _publog(u"publish settings apply failed: {0}".format(_as_text(e)))
            _publog(_as_text(traceback.format_exc()))
        return False

    def _apply_publish_settings_data(self, data):
        self._loading_publish_settings = True
        try:
            publish_type = _as_text(data.get(u"publish_type", u""))
            if publish_type == u"outdoor":
                self._ensure_outdoor_panel()
                self._type_outdoor.setChecked(True)
            elif publish_type == u"indoor":
                self._type_indoor.setChecked(True)

            indoor = data.get(u"indoor", {}) or {}
            self._set_checked(self._manual_pick_chk, indoor.get(u"manual_pick", False))
            saved_bip = self._node_by_name(indoor.get(u"bip_name", u""))
            saved_root = self._node_by_name(indoor.get(u"root_name", u""))
            if saved_bip is not None:
                self._bip_obj = saved_bip
                self._bip_btn.setText(u"Bip: " + _as_text(saved_bip.name))
            if saved_root is not None:
                self._root_obj = saved_root
                self._root_btn.setText(u"Root: " + _as_text(saved_root.name))
            self._update_obj_status()

            self._set_checked(self._enable_pos_chk, indoor.get(u"enable_pos", self._enable_pos_chk.isChecked()))
            self._set_checked(self._follow_x_chk, indoor.get(u"follow_x", False))
            self._set_checked(self._follow_y_chk, indoor.get(u"follow_y", True))
            self._set_checked(self._follow_z_chk, indoor.get(u"follow_z", False))
            self._set_value(self._z_thres_spn, indoor.get(u"z_thres_cm", self._z_thres_spn.value()))
            self._set_value(self._z_weight_spn, indoor.get(u"z_weight", self._z_weight_spn.value()))
            self._set_checked(self._z_limit_chk, indoor.get(u"z_limit_range", False))
            self._set_value(self._z_limit_start_spn, indoor.get(u"z_limit_start", self._z_limit_start_spn.value()))
            self._set_value(self._z_limit_end_spn, indoor.get(u"z_limit_end", self._z_limit_end_spn.value()))
            self._set_checked(self._z_hover_chk, indoor.get(u"z_hover", False))
            self._set_value(self._z_hover_height_spn, indoor.get(u"z_hover_height_cm", self._z_hover_height_spn.value()))
            self._set_value(self._z_hover_start_spn, indoor.get(u"z_hover_start", self._z_hover_start_spn.value()))
            self._set_value(self._z_hover_end_spn, indoor.get(u"z_hover_end", self._z_hover_end_spn.value()))
            self._set_checked(self._enable_offset_chk, indoor.get(u"enable_offset", False))
            self._set_value(self._offset_x_spn, indoor.get(u"offset_x", self._offset_x_spn.value()))
            self._set_value(self._offset_y_spn, indoor.get(u"offset_y", self._offset_y_spn.value()))
            self._set_value(self._offset_z_spn, indoor.get(u"offset_z", self._offset_z_spn.value()))
            self._set_checked(self._use_smooth_chk, indoor.get(u"use_smooth", False))
            self._set_value(self._filter_spn, indoor.get(u"filter_val", self._filter_spn.value()))
            self._set_value(self._smooth_str_spn, indoor.get(u"smooth_str", self._smooth_str_spn.value()))
            self._set_checked(self._smooth_limit_chk, indoor.get(u"smooth_limit_range", False))
            self._set_value(self._smooth_limit_start_spn, indoor.get(u"smooth_limit_start", self._smooth_limit_start_spn.value()))
            self._set_value(self._smooth_limit_end_spn, indoor.get(u"smooth_limit_end", self._smooth_limit_end_spn.value()))
            self._set_checked(self._pos_rm_limit_chk, indoor.get(u"pos_rm_limit_range", False))
            self._set_value(self._pos_rm_start_spn, indoor.get(u"pos_rm_start", self._pos_rm_start_spn.value()))
            self._set_value(self._pos_rm_end_spn, indoor.get(u"pos_rm_end", self._pos_rm_end_spn.value()))
            self._set_checked(self._enable_rot_chk, indoor.get(u"enable_rot", self._enable_rot_chk.isChecked()))
            self._set_checked(self._rot_custom_angle_chk, indoor.get(u"rot_custom_angle", False))
            self._set_value(
                self._rot_custom_degrees_spn,
                indoor.get(u"rot_custom_degrees", self._rot_custom_degrees_spn.value()),
            )
            self._set_rot_custom_dir(indoor.get(u"rot_custom_dir", u"auto"))
            self._set_checked(self._rot_limit_chk, indoor.get(u"rot_limit_range", False))
            self._set_value(
                self._rot_limit_start_spn,
                indoor.get(u"rot_limit_start", self._rot_limit_start_spn.value()),
            )
            self._set_value(
                self._rot_limit_end_spn,
                indoor.get(u"rot_limit_end", self._rot_limit_end_spn.value()),
            )

            self._split_data = self._deserialize_split_data(indoor.get(u"split_data", []))
            self._set_checked(
                self._enable_split_chk,
                indoor.get(u"enable_split", bool(self._split_data))
            )
            self._set_checked(self._seg_show_full_name_chk, indoor.get(u"show_split_full_name", False))
            preset = indoor.get(u"segment_preset", u"")
            if preset:
                self._set_combo_text(self._seg_preset_ddl, preset)
            suffix = indoor.get(u"segment_suffix", u"")
            if suffix:
                self._seg_suffix_edit.setText(_as_text(suffix))
            self._set_checked(self._indoor_export_cam_chk, indoor.get(u"export_cam", False))
            self._set_checked(self._indoor_only_cam_chk, indoor.get(u"only_cam", False))
            self._set_proxy_sample_rate(indoor.get(u"proxy_sample_rate_hz", 30))
            if self._indoor_only_cam_chk.isChecked():
                self._set_checked(self._indoor_export_cam_chk, True)

            outdoor = data.get(u"outdoor", {}) or {}
            if outdoor:
                self._ensure_outdoor_panel()
                self._set_combo_text(self._module_ddl, outdoor.get(u"module", u""))
                self._set_combo_text(self._type_ddl, outdoor.get(u"type_code", u""))
                self._set_combo_text(self._asset_type_ddl, outdoor.get(u"asset_type", u""))
                self._set_checked(self._outdoor_export_cam_chk, outdoor.get(u"export_cam", False))
                self._set_checked(self._outdoor_only_cam_chk, outdoor.get(u"only_cam", False))
                self._set_outdoor_proxy_sample_rate(outdoor.get(u"proxy_sample_rate_hz", 30))
                if self._outdoor_only_cam_chk.isChecked():
                    self._set_checked(self._outdoor_export_cam_chk, True)
                if self._char_list is not None:
                    checked = set([_as_text(n) for n in outdoor.get(u"checked_char_names", [])])
                    if checked:
                        for i in range(self._char_list._list.count()):
                            item = self._char_list._list.item(i)
                            if i < len(self._char_list._char_data):
                                name = _as_text(self._char_list._char_data[i].get(u"name", u""))
                                item.setCheckState(QtCore.Qt.Checked if name in checked else QtCore.Qt.Unchecked)
                if self._morpher_list is not None:
                    morph_checked = [
                        _as_text(n) for n in outdoor.get(u"checked_morpher_names", [])
                    ]
                    self._morpher_list.set_pending_checked_names(morph_checked)
                    self._morpher_list.refresh(preferred_checked_names=morph_checked)

            self._refresh_segments_list()
            self._apply_wallhit_root_motion_mode(self._is_wallhit_scene())
            self._update_indoor_pos_ui()
            self._update_indoor_rot_ui()
            self._update_split_ui()
            self._update_preview()
        finally:
            self._loading_publish_settings = False

    # ── 导出逻辑 ──────────────────────────────────────────────────

    def _build_indoor_settings(self):
        from core.rm_exporter import ExportSettings
        s = ExportSettings()
        s.bip_obj   = self._bip_obj
        s.root_obj  = self._root_obj
        s.enable_pos  = self._enable_pos_chk.isChecked()
        s.follow_x    = self._follow_x_chk.isChecked()
        s.follow_y    = self._follow_y_chk.isChecked()
        s.follow_z    = self._follow_z_chk.isChecked()
        s.z_thres_cm  = self._z_thres_spn.value()
        s.z_weight    = self._z_weight_spn.value()
        s.z_limit_range = self._z_limit_chk.isChecked()
        s.z_limit_start = self._z_limit_start_spn.value()
        s.z_limit_end = self._z_limit_end_spn.value()
        s.z_hover = self._z_hover_chk.isChecked()
        s.z_hover_height_cm = self._z_hover_height_spn.value()
        s.z_hover_start = self._z_hover_start_spn.value()
        s.z_hover_end = self._z_hover_end_spn.value()
        s.use_smooth  = self._use_smooth_chk.isChecked()
        s.filter_val  = self._filter_spn.value()
        s.smooth_str  = self._smooth_str_spn.value()
        s.smooth_limit_range = self._smooth_limit_chk.isChecked()
        s.smooth_limit_start = self._smooth_limit_start_spn.value()
        s.smooth_limit_end = self._smooth_limit_end_spn.value()
        s.pos_rm_limit_range = self._pos_rm_limit_chk.isChecked()
        s.pos_rm_start = self._pos_rm_start_spn.value()
        s.pos_rm_end = self._pos_rm_end_spn.value()
        if self._enable_offset_chk.isChecked():
            s.offset_x = self._offset_x_spn.value()
            s.offset_y = self._offset_y_spn.value()
            s.offset_z = self._offset_z_spn.value()
        else:
            s.offset_x = 0.0
            s.offset_y = 0.0
            s.offset_z = 0.0
        s.enable_rot  = self._enable_rot_chk.isChecked()
        s.rot_custom_angle = self._rot_custom_angle_chk.isChecked()
        s.rot_custom_degrees = float(self._rot_custom_degrees_spn.value())
        s.rot_custom_dir = self._get_rot_custom_dir()
        s.rot_limit_range = self._rot_limit_chk.isChecked()
        s.rot_limit_start = self._rot_limit_start_spn.value()
        s.rot_limit_end = self._rot_limit_end_spn.value()
        s.force_keys  = self._config.get(u"adv_force_keys", True)
        s.fix_rot     = self._config.get(u"adv_fix_rot", True)
        s.remove_initial_z  = self._config.get(u"adv_remove_initial_z", True)
        s.unlock      = self._config.get(u"adv_unlock_nodes", True)
        s.delete_temp = self._config.get(u"adv_delete_temp_file", True)
        s.exp_timeline_cam  = False
        s.exp_ingame_cam    = self._indoor_export_cam_chk.isChecked()
        s.only_cam    = self._indoor_only_cam_chk.isChecked()
        s.wallhit_root_motion = bool(self._is_wallhit_scene())
        s.proxy_sample_rate_hz = self._get_proxy_sample_rate()
        if self._enable_split_chk.isChecked():
            s.split_data = list(self._split_data)
        return s

    def _validate_wallhit_export_settings(self, settings):
        if not getattr(settings, "wallhit_root_motion", False):
            return True
        from core.rm_wallhit import collect_wallhit_segments

        scene_start = int(rt.animationRange.start.frame)
        scene_end = int(rt.animationRange.end.frame)
        _segments, errors = collect_wallhit_segments(
            settings.split_data, scene_start=scene_start, scene_end=scene_end
        )
        if not errors:
            return True
        QtWidgets.QMessageBox.warning(
            self,
            u"WallHit 分段设置不完整",
            u"_WallHit 专用根运动需要九个拆分片段，当前无法安全发布：\n\n{0}".format(
                u"\n".join([u"• " + _as_text(msg) for msg in errors])
            ),
        )
        return False

    def _clear_indoor_resume_state(self):
        self._indoor_resume_pending = False
        self._indoor_resume_ctx = None
        self._export_btn.setText(u"发布")

    def _pause_indoor_for_manual_ik(self, ctx, remaining_nodes, prep_manual_ui):
        self._indoor_resume_pending = True
        self._indoor_resume_ctx = ctx
        self._export_btn.setText(u"继续发布")

        first_node = u""
        if remaining_nodes:
            first_node = remaining_nodes[0][0]
        if first_node:
            try:
                prep_manual_ui(ctx["settings"].bip_obj, first_node)
            except Exception:
                pass

        detail_lines = []
        for node_name, _status in remaining_nodes:
            detail_lines.append(node_name)
        detail_text = u"\n".join(detail_lines) if detail_lines else u"(未读取到具体节点)"

        QtWidgets.QMessageBox.information(
            self,
            u"需要手动清理 IK Object",
            u"已挂起本次发布。\n\n"
            u"请手动清理以下骨骼的 IK Object：\n\n{0}\n\n"
            u"保持当前场景不关闭，清理完成后直接点击“继续发布”。".format(detail_text)
        )

    def _validate_and_rename(self, filename, anim_type):
        """
        校验命名，不合规则弹重命名窗口。
        返回 (final_name, ok)；ok=False 表示用户取消导出。
        """
        from pipeline.rm_naming import validate_indoor_name, validate_outdoor_name
        from ui.rm_rename_dialog import RenameDialog

        cat_map = self._config.get(u"category_folder_map")
        mod_map = self._config.get(u"module_folder_map")
        type_map = self._config.get(u"outdoor_type_folder_map")
        asset_types = self._config.get(u"outdoor_asset_types")

        if anim_type == u"indoor":
            is_valid, _, _ = validate_indoor_name(filename, cat_map)
        else:
            is_valid, _, _ = validate_outdoor_name(
                filename, mod_map, type_map, asset_types, cat_map
            )

        if is_valid:
            return filename, True

        dlg = RenameDialog(
            filename,
            anim_type,
            parent=self,
            module_folder_map=mod_map,
            category_folder_map=cat_map,
            outdoor_type_folder_map=type_map,
            outdoor_asset_types=asset_types,
        )
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            return dlg.get_new_name(), True
        return filename, False

    def _run_pipeline(self, fbx_paths, max_file_path, anim_type, parsed_info):
        """
        导出完成后的 Pipeline：Unity 拷贝 + 公盘备份 + Unity 唤醒
        """
        from pipeline.rm_file_io import (
            copy_fbx_to_unity, publish_max_to_nas_indoor, publish_max_to_nas_outdoor,
            get_unity_indoor_path, get_unity_outdoor_path,
            get_unity_indoor_clip_open_path, get_unity_outdoor_clip_open_path,
            get_unity_clip_asset_path,
        )
        from pipeline.rm_unity_bridge import (
            focus_unity_and_trigger_refresh,
            write_project_window_request,
        )

        unity_root   = self._config.get(u"unity_root", u"")
        nas_base     = self._config.get(u"nas_base",   u"")
        auto_unity   = self._config.get(u"auto_copy_unity",   True)
        auto_nas     = self._config.get(u"auto_backup_nas",   True)
        if (parsed_info or {}).get(u"naming_scheme") == u"personal":
            auto_nas = False  # Personal assets use the repository, not legacy public stage folders.
        auto_focus   = self._config.get(u"auto_focus_unity",  True)
        open_folder  = self._config.get(u"open_folder_after_export", True)
        backup_stage = self._config.get(u"backup_stage", u"初版")
        backup_ver   = self._config.get(u"backup_version", u"")
        publisher    = self._config.get(u"publisher_name", u"")
        cat_map      = self._config.get(u"category_folder_map", {})
        copied_unity = False
        unity_dir    = u""
        open_dir     = u""
        open_asset_path = u""
        request_written = False

        _publog(u"=== Pipeline Start ===")
        _publog(u"anim_type={0}".format(anim_type))
        _publog(u"max_file_path={0}".format(max_file_path))
        _publog(u"fbx_paths={0}".format(u" | ".join([_as_text(p) for p in fbx_paths])))
        _publog(
            u"config unity_root={0} auto_unity={1} auto_focus={2} open_folder={3} auto_nas={4}".format(
                unity_root, auto_unity, auto_focus, open_folder, auto_nas
            )
        )
        _publog(u"parsed_info={0}".format(_as_text(parsed_info)))

        # A 路：FBX → Unity
        if unity_root and parsed_info:
            if anim_type == u"indoor":
                if parsed_info.get(u"naming_scheme") == u"personal":
                    from pipeline.personal_naming import unity_destination
                    unity_dir = unity_destination(unity_root, parsed_info, max_file_path)
                else:
                    unity_dir = get_unity_indoor_path(
                        unity_root, cat_map,
                        parsed_info[u"category"], parsed_info[u"char_name"]
                    )
                open_dir = get_unity_indoor_clip_open_path(
                    unity_root,
                    parsed_info[u"category"],
                    parsed_info[u"char_name"]
                )
            else:
                unity_dir = get_unity_outdoor_path(
                    unity_root,
                    parsed_info[u"module_folder"],
                    parsed_info[u"type_folder"],
                    parsed_info[u"char_folder"],
                )
                open_dir = get_unity_outdoor_clip_open_path(
                    unity_root,
                    parsed_info[u"module_folder"],
                    parsed_info[u"type_folder"],
                    parsed_info[u"char_folder"],
                )
        else:
            if not unity_root:
                _publog(u"skip unity path build: unity_root is empty")
            if not parsed_info:
                _publog(u"skip unity path build: parsed_info is empty")

        _publog(u"unity_dir={0}".format(unity_dir or u"<empty>"))
        _publog(u"open_dir={0}".format(open_dir or u"<empty>"))
        if open_dir and fbx_paths:
            if parsed_info.get(u"naming_scheme") == u"personal" and unity_dir:
                imported_path = os.path.join(unity_dir, os.path.basename(fbx_paths[0]))
                open_asset_path = get_unity_clip_asset_path(
                    open_dir, imported_path, os.path.join(unity_root, u"Art", u"Animations")
                )
            else:
                open_asset_path = get_unity_clip_asset_path(open_dir, fbx_paths[0])
        _publog(u"open_asset_path={0}".format(open_asset_path or u"<empty>"))
        if unity_dir:
            _publog(u"unity_dir exists={0}".format(os.path.exists(unity_dir)))
        if open_dir:
            _publog(u"open_dir exists={0}".format(os.path.exists(open_dir)))
        if open_asset_path:
            _publog(u"open_asset_exists={0}".format(os.path.exists(open_asset_path)))

        if auto_unity and unity_dir:
            for fbx_path in fbx_paths:
                if not fbx_path or not os.path.exists(fbx_path):
                    _publog(u"skip copy missing fbx: {0}".format(fbx_path))
                    continue
                try:
                    try:
                        from core.rm_exporter import _validate_fbx_scale_export
                        if _as_text(fbx_path).lower().endswith(u".fbx"):
                            # ADV custom-rig FBX must not be rewritten here.
                            # Official path already applied percent*10 in exporter.
                            _validate_fbx_scale_export(fbx_path)
                    except Exception as scale_ex:
                        _publog(u"scale-validate before unity copy failed: {0}".format(_as_text(scale_ex)))
                    dest_path = copy_fbx_to_unity(fbx_path, unity_dir)
                    copied_unity = True
                    _publog(u"copied to unity: {0}".format(dest_path))
                except Exception as e:
                    _publog(u"copy to unity failed: {0}".format(_as_text(e)))
                    _show_publish_error(
                        self,
                        u"拷贝到 Unity 失败",
                        u"拷贝到 Unity 失败：\n{0}".format(_as_text(e)),
                        error=e,
                        context={
                            u"phase": u"copy-to-unity",
                            u"animation_type": anim_type,
                            u"fbx_path": fbx_path,
                            u"unity_dir": unity_dir,
                        },
                        warning=True,
                    )
        elif auto_unity:
            _publog(u"skip copy to unity: unity_dir unavailable")
        else:
            _publog(u"skip copy to unity: auto_unity disabled")

        if open_folder and open_asset_path and unity_root:
            try:
                req_path, asset_path = write_project_window_request(open_asset_path, unity_root)
                request_written = True
                _publog(u"write unity project request: {0}".format(req_path))
                _publog(u"unity project asset path: {0}".format(asset_path))
            except Exception as e:
                _publog(u"write unity project request failed: {0}".format(_as_text(e)))
        elif open_folder:
            _publog(u"skip unity project request: open_asset_path or unity_root unavailable")

        if auto_focus and (copied_unity or request_written):
            try:
                focused = focus_unity_and_trigger_refresh()
                _publog(u"focus unity result={0}".format(focused))
                if not focused:
                    print(u"[RMTool] Unity 未运行，跳过自动唤起")
            except Exception as e:
                _publog(u"focus unity failed: {0}".format(_as_text(e)))
        elif copied_unity or request_written:
            _publog(u"skip focus unity: auto_focus disabled")

        # B 路：MAX → 公盘
        if auto_nas and os.path.exists(max_file_path) and parsed_info:
            try:
                version = backup_ver if backup_stage == u"监修" else None
                if anim_type == u"indoor":
                    publish_result = publish_max_to_nas_indoor(
                        max_file_path,
                        parsed_info[u"category"], parsed_info[u"char_name"],
                        backup_stage, version, nas_base=nas_base or None,
                        publisher=publisher,
                    )
                else:
                    publish_result = publish_max_to_nas_outdoor(
                        max_file_path,
                        parsed_info[u"module_folder"],
                        parsed_info[u"type_folder"],
                        parsed_info[u"char_folder"],
                        backup_stage, version, nas_base=nas_base or None,
                        publisher=publisher,
                    )
                _publog(
                    u"backup max success: stage={0} version={1} publish_revision={2}".format(
                        backup_stage,
                        version or u"<none>",
                        publish_result.get(u"publish_revision_label", u""),
                    )
                )
                if publish_result.get(u"archived_path"):
                    _publog(u"archived previous public max: {0}".format(
                        publish_result.get(u"archived_path")
                    ))
                if not publish_result.get(u"local_settings_saved", True):
                    _publog(u"local publish settings update failed: {0}".format(
                        publish_result.get(u"local_settings_result", u"")
                    ))
            except Exception as e:
                _publog(u"backup max failed: {0}".format(_as_text(e)))
                filename_error_message = _format_publish_filename_too_long_error(
                    e, max_file_path
                )
                _show_publish_error(
                    self,
                    (
                        u"源文件名过长"
                        if filename_error_message else u"公盘备份失败"
                    ),
                    filename_error_message or u"公盘备份失败：\n{0}".format(_as_text(e)),
                    error=e,
                    context={
                        u"phase": u"publish-max-to-public",
                        u"animation_type": anim_type,
                        u"max_file": max_file_path,
                    },
                    warning=True,
                )
        elif auto_nas:
            _publog(u"skip backup: max file missing or parsed_info unavailable")
        else:
            _publog(u"skip backup: auto_nas disabled")

        if open_folder and not request_written:
            _publog(u"skip unity project locate: request not written")
        elif not open_folder:
            _publog(u"skip unity project locate: option disabled")

        _publog(u"=== Pipeline End ===")

    def _get_publish_stage_label_from_config(self):
        from pipeline.publish_public_lookup import format_publish_stage_label

        stage = self._config.get(u"backup_stage", u"初版")
        version = self._config.get(u"backup_version", u"")
        return format_publish_stage_label(stage, version)

    def _confirm_publish_version(self, anim_type, parsed_info=None, match_key=None):
        """按角色全部公盘动作确认本次阶段；match_key 仅保留调用兼容。"""
        if (parsed_info or {}).get(u"naming_scheme") == u"personal":
            # Personal source files are versioned in Git, not public stage directories.
            return True
        from pipeline.publish_public_lookup import (
            build_indoor_char_root,
            build_outdoor_char_root,
            find_latest_character_stage,
        )
        from ui.rm_publish_confirm_dialog import ask_publish_confirm

        selected_stage = self._config.get(u"backup_stage", u"初版")
        selected_version = self._config.get(u"backup_version", u"")
        character_stage = None
        char_root = u""
        nas_base = self._config.get(u"nas_base", u"")

        if anim_type == u"indoor" and parsed_info:
            char_root = build_indoor_char_root(
                nas_base,
                parsed_info.get(u"category", u""),
                parsed_info.get(u"char_name", u""),
            )
        elif anim_type == u"outdoor" and parsed_info:
            char_root = build_outdoor_char_root(
                nas_base,
                parsed_info.get(u"module_folder", u""),
                parsed_info.get(u"type_folder", u""),
                parsed_info.get(u"char_folder", u""),
            )

        if char_root:
            try:
                character_stage = find_latest_character_stage(char_root)
                _publog(
                    u"character publish stage root={0} latest={1}".format(
                        char_root,
                        character_stage.get(u"label", u"")
                        if character_stage else u"<unpublished>",
                    )
                )
            except Exception as e:
                _publog(u"character stage lookup failed: {0}".format(_as_text(e)))
                character_stage = None

        accepted, stage, version = ask_publish_confirm(
            self,
            selected_stage=selected_stage,
            selected_version=selected_version,
            character_stage=character_stage,
        )
        if not accepted:
            return False

        changed = (
            stage != self._config.get(u"backup_stage", u"初版")
            or version != self._config.get(u"backup_version", u"")
        )
        self._config[u"backup_stage"] = stage
        self._config[u"backup_version"] = version if stage == u"监修" else u""
        if changed and not self._save_config():
            QtWidgets.QMessageBox.warning(
                self,
                u"设置保存失败",
                u"本次会按弹窗选择的阶段发布，但未能保存为下次默认值。",
            )
        return True

    def _on_export(self):
        if self._type_indoor.isChecked():
            self._do_indoor_export()
        else:
            self._do_outdoor_export()

    def _do_indoor_export(self, is_batch=False):
        """局内导出主流程"""
        use_baselayer = getattr(self, u"_com_restore_engine", u"baselayer") == u"baselayer"
        if use_baselayer:
            from core.rm_indoor_ms_runner_baselayer import (
                run_indoor_export_baselayer as run_indoor_export,
            )
        else:
            from core.rm_indoor_ms_runner import (
                get_remaining_indoor_ik_nodes,
                prepare_indoor_ik,
                prepare_manual_indoor_ik_ui,
                run_indoor_export,
            )
        from pipeline.rm_naming import validate_indoor_name, clean_string_native

        _publog(
            u"--- Indoor Export Request engine={0} sampleRate={1}Hz ---".format(
                getattr(self, u"_com_restore_engine", u"baselayer"),
                self._get_proxy_sample_rate() if use_baselayer else 30,
            )
        )
        if use_baselayer and self._indoor_resume_pending:
            self._clear_indoor_resume_state()
        resume_ctx = None
        if self._indoor_resume_pending and self._indoor_resume_ctx:
            resume_ctx = self._indoor_resume_ctx
            max_file_path = _as_text(rt.maxFilePath)
            max_file_name = _as_text(rt.maxFileName)
            _publog(u"resume indoor export after manual IK cleanup")
            _publog(u"max={0}{1}".format(max_file_path, max_file_name))
            settings = resume_ctx["settings"]
            publish_settings_data = resume_ctx.get(u"publish_settings_data")
            final_name = resume_ctx["final_name"]
            is_valid = resume_ctx["is_valid"]
            parsed_info = resume_ctx["parsed_info"]
            orig_full = resume_ctx["orig_full"]
            temp_path = resume_ctx["temp_path"]
        else:
            max_file_path = _as_text(rt.maxFilePath)
            max_file_name = _as_text(rt.maxFileName)
            _publog(u"max={0}{1}".format(max_file_path, max_file_name))

            # 文件检查
            if not max_file_path:
                QtWidgets.QMessageBox.warning(self, u"错误", u"请先保存当前 Max 文件")
                return []

            # 对象检查
            if not rt.isValidNode(self._bip_obj) or not rt.isValidNode(self._root_obj):
                self._auto_detect()
            if not rt.isValidNode(self._bip_obj) or not rt.isValidNode(self._root_obj):
                QtWidgets.QMessageBox.warning(self, u"错误", u"未找到 Biped 或 Root 对象，请检查场景")
                return []

            # 命名校验
            raw_name   = os.path.splitext(max_file_name)[0]
            clean_name = clean_string_native(raw_name, u"")
            from pipeline.rm_naming import indoor_categories_from_map
            if raw_name.split(u"_")[0] not in indoor_categories_from_map(self._config.get(u"category_folder_map")):
                # New personal names must not silently lose a suffix / field in legacy cleanup.
                clean_name = raw_name
            final_name, ok = self._validate_and_rename(clean_name, u"indoor")
            if not ok:
                return []

            is_valid, _, parsed_info = validate_indoor_name(
                final_name, self._config.get(u"category_folder_map")
            )

            if parsed_info.get(u"naming_scheme") == u"personal" and (
                (self._enable_split_chk.isChecked() and self._split_data)
                or self._indoor_export_cam_chk.isChecked() or self._indoor_only_cam_chk.isChecked()
            ):
                QtWidgets.QMessageBox.warning(
                    self, u"个人动画发布范围",
                    u"个人短命名当前采用一个动作一个 FBX。请关闭分段与相机导出；"
                    u"分段动作请分别保存为独立动作名（例如 RunStart、RunStop）。旧格式的分段 / 相机流程不变。"
                )
                return []

            if not is_batch:
                if not self._confirm_publish_version(
                    u"indoor", parsed_info=parsed_info, match_key=final_name
                ):
                    return []

            settings = self._build_indoor_settings()
            publish_settings_data = self._collect_publish_settings_data()
            if not self._validate_wallhit_export_settings(settings):
                return []

            # 保存临时文件
            orig_full  = max_file_path + max_file_name
            temp_path  = os.path.join(tempfile.gettempdir(),
                                      u"RM_Temp_" + max_file_name)
            if not rt.saveMaxFile(temp_path, clearNeedSaveFlag=True):
                QtWidgets.QMessageBox.warning(self, u"错误", u"无法保存临时文件，终止导出")
                return []

            settings.orig_file_path = max_file_path
            settings.orig_file_name = max_file_name
            settings.fbx_folder     = os.path.join(max_file_path, u"FBX")
            settings.delete_temp   = self._config.get(u"adv_delete_temp_file", True)

        fbx_paths = []
        finished_backend = False
        paused_for_manual = False
        try:
            export_cam = settings.exp_timeline_cam or settings.exp_ingame_cam or settings.only_cam
            if export_cam:
                target_cam = rt.getNodeByName(u"Main_Camera")
                if target_cam is None or not rt.isValidNode(target_cam):
                    QtWidgets.QMessageBox.warning(
                        self, u"错误", u"勾选了导出相机，但场景中找不到 Main_Camera"
                    )
                    return []

            if not resume_ctx:
                # ProxyRoot samples the live source and bakes an isolated export
                # hierarchy (no RM_Fix and no source COM write).  IK Object /
                # manual remaining-IK pauses belong to the old layer path, so the
                # official path performs its own IK->FK bake inside the backend.
                if use_baselayer:
                    _publog(
                        u"ProxyRoot: no source COM write / no manual pause; "
                        u"IK->FK bake runs inside RunExport_BaseLayer before proxy build"
                    )
                else:
                    ik_processed = prepare_indoor_ik(
                        settings.bip_obj, settings.only_cam
                    )
                    if ik_processed > 0:
                        _publog(u"indoor IK bake count={0}".format(ik_processed))

                    remaining_ik_nodes = get_remaining_indoor_ik_nodes(
                        settings.bip_obj, settings.only_cam
                    )
                    if remaining_ik_nodes:
                        _publog(
                            u"indoor export paused for manual IK cleanup: {0}".format(
                                u" | ".join(
                                    [
                                        u"{0}:{1}".format(n, s)
                                        for n, s in remaining_ik_nodes
                                    ]
                                )
                            )
                        )
                        paused_for_manual = True
                        self._pause_indoor_for_manual_ik(
                            {
                                u"settings": settings,
                                u"publish_settings_data": publish_settings_data,
                                u"final_name": final_name,
                                u"is_valid": is_valid,
                                u"parsed_info": parsed_info,
                                u"orig_full": orig_full,
                                u"temp_path": temp_path,
                            },
                            remaining_ik_nodes,
                            prepare_manual_indoor_ik_ui,
                        )
                        return []

            fbx_paths = run_indoor_export(
                settings,
                final_name,
                orig_full,
                temp_path,
                is_batch,
                export_weapon_mapping=self._config.get(
                    u"adv_export_weapon_state_mapping", True
                ),
            )
            finished_backend = True

        except Exception as e:
            _publog(u"indoor export failed: {0}".format(_as_text(e)))
            traceback_text = _as_text(traceback.format_exc())
            _publog(traceback_text)
            transform_error_message = _format_proxy_transform_export_error(e)
            split_curve_error_message = _format_task_local_curve_export_error(e)
            if _is_binding_hierarchy_export_error(e):
                _show_publish_error(
                    self,
                    u"绑定层级错误，无法导出",
                    _BINDING_HIERARCHY_WARNING,
                    error=e,
                    traceback_text=traceback_text,
                    context={u"phase": u"indoor-export", u"animation_type": u"indoor"},
                    warning=True,
                )
            elif transform_error_message:
                _show_animation_data_export_error(
                    self,
                    transform_error_message,
                    error=e,
                    traceback_text=traceback_text,
                    context={u"phase": u"indoor-export", u"animation_type": u"indoor"},
                )
            elif split_curve_error_message:
                _show_animation_data_export_error(
                    self,
                    split_curve_error_message,
                    error=e,
                    traceback_text=traceback_text,
                    context={u"phase": u"indoor-export", u"animation_type": u"indoor"},
                )
            else:
                _show_publish_error(
                    self,
                    u"导出错误",
                    u"导出过程中发生错误：\n{0}".format(_as_text(e)),
                    error=e,
                    traceback_text=traceback_text,
                    context={u"phase": u"indoor-export", u"animation_type": u"indoor"},
                )
        finally:
            if finished_backend:
                self._auto_detect()
                self._clear_indoor_resume_state()
            else:
                if not paused_for_manual:
                    if self._config.get(u"adv_delete_temp_file", True) or is_batch:
                        rt.loadMaxFile(orig_full, quiet=True)
                        if os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
                    self._auto_detect()

        if fbx_paths and not is_batch:
            _publog(u"indoor export success count={0}".format(len(fbx_paths)))
            for _path in fbx_paths:
                _publog(u"generated fbx: {0} exists={1}".format(_path, os.path.exists(_path)))
            self._save_publish_settings_for_current_scene(orig_full, publish_settings_data)
            QtWidgets.QMessageBox.information(
                self, u"发布完成",
                u"发布完成！共生成 {0} 个 FBX 文件。\n关闭此窗口后继续同步 Unity / 公盘。".format(len(fbx_paths))
            )
            self._run_pipeline(fbx_paths, orig_full, u"indoor",
                               parsed_info if is_valid else None)
        elif not fbx_paths:
            _publog(u"indoor export produced no fbx")

        return fbx_paths

    def _do_outdoor_export(self):
        """局外导出主流程（无 Root Motion，无 IK）"""
        from core.rm_exporter import run_cutscene_export
        from pipeline.rm_naming import (
            build_outdoor_camera_export_name,
            build_outdoor_character_export_name,
            clean_string_native,
            parse_outdoor_source_name,
        )

        max_file_path = _as_text(rt.maxFilePath)
        max_file_name = _as_text(rt.maxFileName)
        _publog(u"--- Outdoor Export Request ---")
        _publog(u"max={0}{1}".format(max_file_path, max_file_name))

        if not max_file_path:
            QtWidgets.QMessageBox.warning(self, u"错误", u"请先保存当前 Max 文件")
            return

        ok, msg, source_info = parse_outdoor_source_name(
            max_file_name,
            self._config.get(u"module_folder_map"),
            self._config.get(u"outdoor_type_folder_map"),
        )
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"错误", msg)
            return

        outdoor_match_key = clean_string_native(
            os.path.splitext(max_file_name)[0], u""
        )
        if not self._confirm_publish_version(
            u"outdoor", parsed_info=source_info, match_key=outdoor_match_key
        ):
            return

        chars = self._char_list.get_selected_chars()
        morph_nodes = (
            self._morpher_list.get_selected_nodes()
            if self._morpher_list is not None
            else []
        )
        asset_type = self._get_outdoor_asset_type()
        export_cam  = self._outdoor_export_cam_chk.isChecked() or self._outdoor_only_cam_chk.isChecked()
        only_cam    = self._outdoor_only_cam_chk.isChecked()
        use_proxy_export = (
            getattr(self, u"_com_restore_engine", u"baselayer") == u"baselayer"
        )
        outdoor_sample_rate = self._get_outdoor_proxy_sample_rate()
        publish_settings_data = self._collect_publish_settings_data()
        start_f     = int(rt.animationRange.start.frame)
        end_f       = int(rt.animationRange.end.frame)
        fbx_folder  = os.path.join(max_file_path, u"FBX")

        self._get_outdoor_source_info(sync_widgets=True)

        if not only_cam and not chars:
            QtWidgets.QMessageBox.warning(self, u"错误", u"请勾选至少一个角色进行导出")
            return

        if use_proxy_export and not only_cam:
            try:
                source_fps = int(rt.frameRate)
            except Exception:
                source_fps = 0
            if source_fps != 30:
                QtWidgets.QMessageBox.critical(
                    self,
                    u"场景帧率不符合发布要求",
                    u"局内/局外共享 ProxyRoot 发布要求 Max 场景为 30 FPS；当前为 {0} FPS。\n"
                    u"请先在时间配置中改为 30 FPS，并重新检查镜头、事件和动画帧范围后再发布。".format(
                        source_fps
                    ),
                )
                return
            _publog(
                u"outdoor ProxyRoot sampleRate={0}Hz chars={1}".format(
                    outdoor_sample_rate, len(chars)
                )
            )

        if export_cam:
            target_cam = rt.getNodeByName(u"Main_Camera")
            if target_cam is None or not rt.isValidNode(target_cam):
                QtWidgets.QMessageBox.warning(
                    self, u"错误", u"勾选了导出相机，但场景中找不到 Main_Camera"
                )
                return

        exported     = []
        last_parsed  = source_info
        if morph_nodes:
            _publog(
                u"outdoor morpher selected count={0} names={1}".format(
                    len(morph_nodes),
                    u",".join(self._morpher_list.get_checked_names() if self._morpher_list else []),
                )
            )

        if not only_cam:
            for char in chars:
                export_name = build_outdoor_character_export_name(
                    source_info, char[u"name"], asset_type
                )
                try:
                    outdoor_root_hint = None
                    outdoor_bip_hint = None
                    try:
                        if (
                            rt is not None
                            and char.get(u"root") is not None
                            and rt.isValidNode(char[u"root"])
                        ):
                            outdoor_root_hint = _as_text(char[u"root"].name)
                    except Exception:
                        outdoor_root_hint = None
                    try:
                        if (
                            rt is not None
                            and char.get(u"bip") is not None
                            and rt.isValidNode(char[u"bip"])
                        ):
                            outdoor_bip_hint = _as_text(char[u"bip"].name)
                    except Exception:
                        outdoor_bip_hint = None
                    paths = run_cutscene_export(
                        char,
                        fbx_folder,
                        export_name,
                        start_f,
                        end_f,
                        export_camera=False,
                        only_camera=False,
                        morph_nodes=morph_nodes,
                        use_proxy_export=use_proxy_export,
                        proxy_sample_rate_hz=outdoor_sample_rate,
                    )
                    if paths:
                        exported.extend(paths)
                        if self._config.get(
                            u"adv_export_weapon_state_mapping", True
                        ) and char.get(u"root"):
                            try:
                                from core.rm_weapon_state_mapping import (
                                    try_export_beside_fbx,
                                )

                                j_added, j_msg = try_export_beside_fbx(
                                    char[u"root"],
                                    fbx_folder,
                                    export_name,
                                    True,
                                    max_file_name,
                                    root_name_hint=outdoor_root_hint,
                                    bip_obj=char.get(u"bip"),
                                    bip_name_hint=outdoor_bip_hint,
                                )
                                for jp in j_added:
                                    _publog(u"weapon mapping: {0}".format(jp))
                                if j_msg and not j_added:
                                    _publog(u"weapon mapping skip: {0}".format(j_msg))
                            except Exception as ex:
                                _publog(
                                    u"weapon mapping export error: {0}".format(
                                        _as_text(ex)
                                    )
                                )
                except Exception as e:
                    _publog(
                        u"outdoor export failed character={0}: {1}".format(
                            char.get(u"name", u""), _as_text(e)
                        )
                    )
                    traceback_text = _as_text(traceback.format_exc())
                    _publog(traceback_text)
                    transform_error_message = _format_proxy_transform_export_error(e)
                    split_curve_error_message = _format_task_local_curve_export_error(e)
                    error_context = {
                        u"phase": u"outdoor-character-export",
                        u"animation_type": u"outdoor",
                        u"character": char.get(u"name", u""),
                        u"export_name": export_name,
                    }
                    if _is_binding_hierarchy_export_error(e):
                        _show_publish_error(
                            self,
                            u"绑定层级错误，无法导出",
                            _BINDING_HIERARCHY_WARNING,
                            error=e,
                            traceback_text=traceback_text,
                            context=error_context,
                            warning=True,
                        )
                    elif transform_error_message:
                        _show_animation_data_export_error(
                            self,
                            transform_error_message,
                            error=e,
                            traceback_text=traceback_text,
                            context=error_context,
                        )
                    elif split_curve_error_message:
                        _show_animation_data_export_error(
                            self,
                            split_curve_error_message,
                            error=e,
                            traceback_text=traceback_text,
                            context=error_context,
                        )
                    else:
                        _show_publish_error(
                            self,
                            u"角色导出错误",
                            u"导出 {0} 时出错：\n{1}".format(char[u"name"], _as_text(e)),
                            error=e,
                            traceback_text=traceback_text,
                            context=error_context,
                            warning=True,
                        )

        if export_cam:
            camera_name = build_outdoor_camera_export_name(source_info)
            try:
                _publog(u"outdoor camera export: {0}".format(camera_name))
                paths = run_cutscene_export(
                    None,
                    fbx_folder,
                    u"",
                    start_f,
                    end_f,
                    export_camera=True,
                    only_camera=True,
                    camera_fbx_name=camera_name,
                )
                if paths:
                    exported.extend(paths)
            except Exception as e:
                _publog(u"outdoor camera export failed: {0}".format(_as_text(e)))
                _show_publish_error(
                    self,
                    u"相机导出错误",
                    u"导出相机时出错：\n{0}".format(_as_text(e)),
                    error=e,
                    context={
                        u"phase": u"outdoor-camera-export",
                        u"animation_type": u"outdoor",
                        u"camera_export_name": camera_name,
                    },
                    warning=True,
                )

        if exported:
            orig_full = max_file_path + max_file_name
            _publog(u"outdoor export success count={0}".format(len(exported)))
            for _path in exported:
                _publog(u"generated fbx: {0} exists={1}".format(_path, os.path.exists(_path)))
            self._save_publish_settings_for_current_scene(orig_full, publish_settings_data)
            QtWidgets.QMessageBox.information(
                self, u"发布完成",
                u"局外发布完成！共生成 {0} 个 FBX 文件。\n关闭此窗口后继续同步 Unity / 公盘。".format(len(exported))
            )
            self._run_pipeline(exported, orig_full, u"outdoor", last_parsed)
        else:
            _publog(u"outdoor export produced no fbx")

    def _on_batch_export(self):
        """批量导出（仅局内）"""
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, u"选择包含 .max 文件的文件夹", _as_text(rt.maxFilePath)
        )
        if not dir_path:
            return

        max_files = glob.glob(os.path.join(dir_path, u"*.max"))
        if not max_files:
            QtWidgets.QMessageBox.warning(self, u"提示", u"所选文件夹内没有 .max 文件")
            return

        success = 0
        for f in max_files:
            try:
                rt.loadMaxFile(f, useFileUnits=True, quiet=True)
                self._auto_detect()
                if rt.isValidNode(self._bip_obj) and rt.isValidNode(self._root_obj):
                    paths = self._do_indoor_export(is_batch=True)
                    if paths:
                        success += 1
            except Exception as e:
                print(u"[RMTool] 批量跳过 {0}: {1}".format(f, e))

        QtWidgets.QMessageBox.information(
            self, u"批量完成",
            u"批量导出完成！成功处理 {0} / {1} 个文件。".format(success, len(max_files))
        )

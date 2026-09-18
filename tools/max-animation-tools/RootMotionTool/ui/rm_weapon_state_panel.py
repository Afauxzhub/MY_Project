# -*- coding: utf-8 -*-
"""
武器状态 Custom Attribute — 发布工具内嵌页（PySide2 + pymxs 调 op_weapon_state_lib.ms）
"""
from __future__ import print_function, division
import os

from PySide2 import QtCore, QtWidgets

try:
    _text_type = unicode
except NameError:
    _text_type = str


def _weapon_lib_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, u"maxscript", u"op_weapon_state_lib.ms")


def ensure_weapon_state_lib_loaded(rt):
    """fileIn 核心库；返回 (ok, message)。"""
    p = _weapon_lib_path()
    if not os.path.exists(p):
        return False, u"未找到: " + p
    try:
        rt.fileIn(p)
        return True, p
    except Exception as e:
        return False, _text_type(e)


def _state_list_to_mxs_array(rt, names):
    arr = rt.Array()
    for n in names:
        rt.append(arr, _text_type(n))
    return arr


class WeaponStatePanel(QtWidgets.QWidget):
    """武器约束绑定页：与独立 Max 对话框逻辑一致。"""

    def __init__(self, parent=None):
        super(WeaponStatePanel, self).__init__(parent)
        self._rt = None
        self._last_mapping_items = []
        self._build_ui()

    def bind_runtime(self, rt):
        self._rt = rt

    def showEvent(self, event):
        """切换回「武器约束绑定」页签时补一次重绘，避免 Max 内嵌 Qt 漏画。"""
        super(WeaponStatePanel, self).showEvent(event)
        QtCore.QTimer.singleShot(0, self._touch_list_repaint)

    def _ensure_rt(self):
        if self._rt is None:
            import pymxs
            self._rt = pymxs.runtime
        return self._rt

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        hint = QtWidgets.QLabel(
            u"选中武器根骨骼后更新映射；工具会读取基础 Link Constraint 目标，\n"
            u"并自动按 Link Constraint 帧号生成武器状态 ID 曲线（Step）。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(u"color: #aab4c8; font-size: 11px;")
        lay.addWidget(hint)

        form = QtWidgets.QFormLayout()
        self._attr_edit = QtWidgets.QLineEdit(u"WeaponState")
        self._param_edit = QtWidgets.QLineEdit(u"State_Weapon")
        form.addRow(u"折叠菜单名 (CA 块名)", self._attr_edit)
        form.addRow(u"引擎参数名 (曲线名)", self._param_edit)
        self._mode_tabs = QtWidgets.QTabWidget()
        self._mode_tabs.addTab(QtWidgets.QWidget(), u"局内 (_lod)")
        self._mode_tabs.addTab(QtWidgets.QWidget(), u"局外 (_CS)")
        self._mode_tabs.setMaximumHeight(34)
        lay.addWidget(self._mode_tabs)
        self._character_edit = QtWidgets.QLineEdit()
        self._character_edit.setPlaceholderText(u"可选；留空时自动识别角色名")
        form.addRow(u"角色名覆盖", self._character_edit)
        self._current_info = QtWidgets.QLabel(u"当前: 未更新")
        self._current_info.setWordWrap(True)
        self._current_info.setStyleSheet(u"color: #aab4c8; font-size: 11px;")
        form.addRow(u"识别结果", self._current_info)
        lay.addLayout(form)

        self._btn_update_map = QtWidgets.QPushButton(u"更新当前武器约束状态 / 映射表")
        self._btn_update_map.clicked.connect(self._on_update_mapping)
        lay.addWidget(self._btn_update_map)

        self._list = QtWidgets.QListWidget()
        self._list.setObjectName(u"opWeaponStateList")
        self._list.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self._list.setAlternatingRowColors(False)
        self._list.setUniformItemSizes(True)
        self._list.setWordWrap(False)
        self._list.setTextElideMode(QtCore.Qt.ElideNone)
        self._list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._list.setMinimumHeight(160)
        lay.addWidget(self._list, 1)

        self._btn_del = QtWidgets.QPushButton(u"[危险] 清除选中骨骼上的该属性")
        self._btn_del.setStyleSheet(u"color: #e07070;")
        self._btn_del.clicked.connect(self._on_delete_attr)
        lay.addWidget(self._btn_del)

    def _touch_list_repaint(self):
        """Max 内嵌 Qt 下 QListWidget 子项文字偶发不重绘，强制布局与视口刷新。"""
        try:
            self._list.doItemsLayout()
        except Exception:
            pass
        try:
            self._list.viewport().update()
            self._list.update()
        except Exception:
            pass

    def _state_names(self):
        if self._last_mapping_items:
            return [x.get(u"targetBone", u"") for x in self._last_mapping_items]
        out = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            out.append(item.data(QtCore.Qt.UserRole) or item.text())
        return out

    def _current_mode(self):
        return u"indoor" if self._mode_tabs.currentIndex() == 0 else u"outdoor"

    def _refresh_mapping_list(self, info):
        self._list.clear()
        self._last_mapping_items = []
        weapon = info.get(u"weapon", {}) if isinstance(info, dict) else {}
        items = weapon.get(u"items", []) if isinstance(weapon, dict) else []
        for item in items:
            self._last_mapping_items.append(item)
            sid = int(item.get(u"id", 0))
            target = item.get(u"targetBone", u"")
            constraint = item.get(u"constraintNode", u"")
            row = QtWidgets.QListWidgetItem(u"{0:02d}  {1}  ->  {2}".format(sid, target, constraint))
            row.setData(QtCore.Qt.UserRole, target)
            row.setData(QtCore.Qt.UserRole + 1, sid)
            self._list.addItem(row)
        character = info.get(u"character", u"")
        action_type = info.get(u"actionType", u"")
        weapon_node = info.get(u"weaponNode", u"")
        map_path = info.get(u"mapPath", u"")
        self._current_info.setText(
            u"角色: {0}  类型: {1}\n武器: {2}\n映射表: {3}".format(
                character, action_type, weapon_node, map_path
            )
        )
        self._touch_list_repaint()

    def _on_update_mapping(self):
        rt = self._ensure_rt()
        ok, msg = ensure_weapon_state_lib_loaded(rt)
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"武器状态", u"无法加载核心库：\n" + msg)
            return
        try:
            from core.rm_weapon_state_mapping import update_selected_weapon_mapping
            mode = self._current_mode()
            character_override = self._character_edit.text().strip()
            ok, text, info = update_selected_weapon_mapping(
                mode,
                self._attr_edit.text(),
                self._param_edit.text(),
                character_override or None,
            )
            if info:
                self._refresh_mapping_list(info)
            if ok:
                QtWidgets.QMessageBox.information(self, u"武器状态", text)
            else:
                QtWidgets.QMessageBox.warning(self, u"武器状态", text)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, u"武器状态", _text_type(e))

    def _on_set_state_key(self):
        row = self._list.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, u"武器状态", u"请先在列表中选择一个约束 ID。")
            return
        item = self._list.item(row)
        state_id = item.data(QtCore.Qt.UserRole + 1)
        if not state_id:
            state_id = row + 1
        try:
            from core.rm_weapon_state_mapping import set_selected_weapon_state_key
            ok, msg = set_selected_weapon_state_key(
                self._attr_edit.text(),
                self._param_edit.text(),
                int(state_id),
            )
            if ok:
                QtWidgets.QMessageBox.information(self, u"武器状态", msg or u"完成")
            else:
                QtWidgets.QMessageBox.warning(self, u"武器状态", msg or u"失败")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, u"武器状态", _text_type(e))

    def _on_apply(self):
        rt = self._ensure_rt()
        ok, msg = ensure_weapon_state_lib_loaded(rt)
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"武器状态", u"无法加载核心库：\n" + msg)
            return
        names = self._state_names()
        if not names:
            QtWidgets.QMessageBox.warning(self, u"武器状态", u"请至少保留一个状态。")
            return
        arr = _state_list_to_mxs_array(rt, names)
        try:
            r = rt.OP_WS_Apply(self._attr_edit.text(), self._param_edit.text(), arr)
            code = int(r[0])
            text = _text_type(r[1]) if len(r) > 1 else u""
            if code == 0:
                QtWidgets.QMessageBox.information(self, u"武器状态", text or u"完成")
            else:
                QtWidgets.QMessageBox.warning(self, u"武器状态", text or u"失败")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, u"武器状态", _text_type(e))

    def _on_fix_step(self):
        rt = self._ensure_rt()
        ok, msg = ensure_weapon_state_lib_loaded(rt)
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"武器状态", u"无法加载核心库：\n" + msg)
            return
        try:
            r = rt.OP_WS_FixStep(self._attr_edit.text(), self._param_edit.text())
            code = int(r[0])
            text = _text_type(r[1]) if len(r) > 1 else u""
            if code == 0:
                QtWidgets.QMessageBox.information(self, u"武器状态", text or u"完成")
            else:
                QtWidgets.QMessageBox.warning(self, u"武器状态", text or u"提示")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, u"武器状态", _text_type(e))

    def _on_export_json(self):
        rt = self._ensure_rt()
        ok, msg = ensure_weapon_state_lib_loaded(rt)
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"武器状态", u"无法加载核心库：\n" + msg)
            return
        names = self._state_names()
        if not names:
            QtWidgets.QMessageBox.warning(self, u"武器状态", u"请先添加状态。")
            return
        try:
            mf = _text_type(rt.maxFileName) if rt.maxFileName else u""
            base = os.path.splitext(mf)[0] + u"_WeaponStateMapping.json" if mf else u"WeaponStateMapping.json"
        except Exception:
            base = u"WeaponStateMapping.json"
        path, _filt = QtWidgets.QFileDialog.getSaveFileName(
            self, u"保存映射 JSON", base, u"JSON (*.json)"
        )
        if not path:
            return
        arr = _state_list_to_mxs_array(rt, names)
        try:
            mf_full = _text_type(rt.maxFileName) if rt.maxFileName else u""
            okw = bool(
                rt.OP_WS_WriteMappingJson(
                    path,
                    self._attr_edit.text(),
                    self._param_edit.text(),
                    arr,
                    mf_full,
                )
            )
            if okw:
                QtWidgets.QMessageBox.information(self, u"武器状态", u"已导出:\n" + path)
            else:
                QtWidgets.QMessageBox.warning(self, u"武器状态", u"写入失败。")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, u"武器状态", _text_type(e))

    def _on_delete_attr(self):
        ans = QtWidgets.QMessageBox.question(
            self,
            u"确认",
            u"将删除当前折叠菜单名对应的 Custom Attribute 及关键帧，不可恢复。\n是否继续？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if ans != QtWidgets.QMessageBox.Yes:
            return
        rt = self._ensure_rt()
        ok, msg = ensure_weapon_state_lib_loaded(rt)
        if not ok:
            QtWidgets.QMessageBox.warning(self, u"武器状态", u"无法加载核心库：\n" + msg)
            return
        try:
            r = rt.OP_WS_DeleteAttr(self._attr_edit.text())
            text = _text_type(r[1]) if len(r) > 1 else u""
            QtWidgets.QMessageBox.information(self, u"武器状态", text or u"完成")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, u"武器状态", _text_type(e))

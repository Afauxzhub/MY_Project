# -*- coding: utf-8 -*-
"""
扫描「武器挂点数据」EmptyModifier 的 Custom Attribute，
从 CA 定义源码解析 stateNames 与曲线参数名（#float 或 #integer），写出 Unity 可读的武器状态映射 JSON。

采集范围：Root 子树 + Biped 子树（武器常挂在 Bip 骨骼上）；仍无数据时再全场景回退。
局内动画拆分时，为每个角色 FBX 片段各写一份同名 stem 的 *_WeaponStateMapping.json。

与 Max 侧 op_weapon_state_lib.ms 生成的 CA 格式配套。
"""
from __future__ import print_function, division

import io
import json
import os
import re

import pymxs

rt = pymxs.runtime

try:
    _text_type = unicode
except NameError:
    _text_type = str

_MODIFIER_NAME = u"\u6b66\u5668\u6302\u70b9\u6570\u636e"  # 武器挂点数据
_PUBLIC_CHARACTER_ROOT = u""
_MAP_FOLDER_NAME = u"WeaponConstraintMaps"
_MAP_FILE_NAME = u"weapon_constraint_map.json"
_ATTACHMENT_PREFIX = u"Attachment"
_TEMP_HELPER_MARK = u"OP_WS_TEMP_ATTACHMENT"

_OP_WS_LIB_MS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir, u"maxscript", u"op_weapon_state_lib.ms")
)
_op_weapon_lib_loaded_once = False


def _as_unicode(s):
    if s is None:
        return u""
    if isinstance(s, _text_type):
        return s
    try:
        return _text_type(s)
    except Exception:
        return u""


def _safe_name(s):
    text = _as_unicode(s).strip()
    if not text:
        return u"Node"
    out = []
    for ch in text:
        if ch.isalnum() or ch == u"_":
            out.append(ch)
        else:
            out.append(u"_")
    safe = u"".join(out).strip(u"_")
    return safe or u"Node"


def _class_name(obj):
    try:
        return _as_unicode(rt.classof(obj))
    except Exception:
        return u""


def _split_action_role_name(name_or_path):
    stem = os.path.splitext(os.path.basename(_as_unicode(name_or_path)))[0]
    parts = [p for p in stem.split(u"_") if p]
    if len(parts) >= 2:
        return parts[0], parts[1], parts[0] + u"_" + parts[1]
    if len(parts) == 1:
        return u"Role", parts[0], parts[0]
    return u"Role", u"", u""


def _find_case_insensitive_child(parent, child_name):
    if not parent or not child_name:
        return u""
    try:
        items = os.listdir(parent)
    except Exception:
        return u""
    wanted = child_name.lower()
    for item in items:
        if item.lower() == wanted:
            return os.path.join(parent, item)
    return u""


def _find_character_resource_dir(character_name):
    if not character_name:
        return u""
    direct = _find_case_insensitive_child(_PUBLIC_CHARACTER_ROOT, character_name)
    if direct:
        return direct
    return os.path.join(_PUBLIC_CHARACTER_ROOT, character_name)


def _find_variant_dir(character_name, action_type, export_mode):
    char_dir = _find_character_resource_dir(character_name)
    suffix = u"_lod" if export_mode == u"indoor" else u"_cs"
    preferred = (action_type or u"Role") + u"_" + character_name + suffix
    direct = _find_case_insensitive_child(char_dir, preferred)
    if direct:
        return direct

    target_tail = (u"_" + character_name + suffix).lower()
    try:
        items = sorted(os.listdir(char_dir))
    except Exception:
        return os.path.join(char_dir, preferred)
    for item in items:
        full = os.path.join(char_dir, item)
        if os.path.isdir(full) and item.lower().endswith(target_tail):
            return full
    return os.path.join(char_dir, preferred)


def _mapping_dir_for(character_name, action_type, export_mode):
    variant_dir = _find_variant_dir(character_name, action_type, export_mode)
    return os.path.join(variant_dir, u"wip", u"max", _MAP_FOLDER_NAME)


def _mapping_file_for(character_name, action_type, export_mode):
    return os.path.join(
        _mapping_dir_for(character_name, action_type, export_mode), _MAP_FILE_NAME
    )


def _load_mapping_file(path):
    if not path or not os.path.exists(path):
        return {u"version": 1, u"weapons": {}}
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    data.setdefault(u"version", 1)
    data.setdefault(u"weapons", {})
    return data


def _save_mapping_file(path, data):
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    with io.open(path, u"w", encoding=u"utf-8") as f:
        f.write(_text_type(json.dumps(data, ensure_ascii=False, indent=2)))


def _detect_top_root_for_node(node):
    cur = node
    last = node
    while cur is not None and rt.isValidNode(cur):
        parent = None
        try:
            parent = cur.parent
        except Exception:
            parent = None
        if parent is None:
            break
        last = parent
        cur = parent
    return last


def _character_from_top_root(node):
    root = _detect_top_root_for_node(node)
    name = _as_unicode(getattr(root, u"name", u""))
    low = name.lower()
    if low.endswith(u"_root"):
        return name[:-5]
    return name


def detect_character_context(export_mode, source_name=None, selected_node=None, action_role_name=None, character_override=None):
    if character_override:
        action_type, _unused, action_role = _split_action_role_name(character_override)
        return action_type, character_override, action_role

    if action_role_name:
        action_type, character_name, action_role = _split_action_role_name(action_role_name)
        return action_type, character_name, action_role

    if export_mode == u"indoor":
        action_type, character_name, action_role = _split_action_role_name(source_name or rt.maxFileName)
        return action_type, character_name, action_role

    character_name = _character_from_top_root(selected_node) if selected_node is not None else u""
    if not character_name:
        _a, character_name, _r = _split_action_role_name(source_name or rt.maxFileName)
    return u"Role", character_name, character_name


def _ensure_op_weapon_lib():
    global _op_weapon_lib_loaded_once
    if _op_weapon_lib_loaded_once:
        return hasattr(rt, "OP_WS_GetCACustDefSource")
    if not os.path.isfile(_OP_WS_LIB_MS):
        return False
    try:
        rt.fileIn(_OP_WS_LIB_MS)
    except Exception:
        return False
    _op_weapon_lib_loaded_once = True
    return hasattr(rt, "OP_WS_GetCACustDefSource")


def _parse_attribute_block_name(source):
    m = re.search(r'attributes\s+"([^"]+)"', source, re.IGNORECASE)
    return m.group(1) if m else u""


def _parse_curve_param_names(source):
    """返回 CA parameters 块中作为曲线导出的数值型参数名（#float 或 #integer，通常含 State_Weapon）。"""
    return re.findall(
        r"([A-Za-z0-9_]+)\s+type:\s*#(?:float|integer)",
        source,
        flags=re.IGNORECASE,
    )


def _parse_state_names_from_source(source):
    """
    解析 rollout 中 stateNames 数组；兼容 Max 紧凑格式、有无 local 关键字。
    """
    if not source or not source.strip():
        return []
    patterns = [
        r"local\s+stateNames\s*=\s*#\(([^)]*)\)",
        r"\bstateNames\s*=\s*#\(([^)]*)\)",
    ]
    inner = None
    for pat in patterns:
        m = re.search(pat, source, re.DOTALL | re.IGNORECASE)
        if m:
            inner = m.group(1)
            break
    if inner is None:
        return []
    parts = re.findall(r'"((?:\\.|[^"\\])*)"', inner)
    return [_text_type(p).replace(u"\\n", u"\n").replace(u'\\"', u'"') for p in parts]


def _pick_curve_param(param_names, preferred=None):
    if not param_names:
        return u""
    if preferred and preferred in param_names:
        return preferred
    for n in param_names:
        if n.lower().startswith(u"state"):
            return n
    return param_names[0]


def _iter_candidate_controllers(node):
    out = []
    try:
        if node.controller is not None:
            out.append(node.controller)
    except Exception:
        pass
    for channel in (u"transform", u"position", u"rotation"):
        try:
            ctrl = rt.getPropertyController(node, channel)
            if ctrl is not None:
                out.append(ctrl)
        except Exception:
            pass
    return out


def _link_controller_for(node):
    if node is None or not rt.isValidNode(node):
        return None
    for ctrl in _iter_candidate_controllers(node):
        if _class_name(ctrl) == u"Link_Constraint":
            return ctrl
    return None


def _constraint_target_count(controller):
    try:
        return int(controller.getNumTargets())
    except Exception:
        return 0


def _constraint_target(controller, index):
    try:
        return controller.getNode(index)
    except Exception:
        pass
    try:
        return controller.getTarget(index)
    except Exception:
        return None


def _constraint_frame(controller, index):
    try:
        return int(controller.getFrameNo(index))
    except Exception:
        return int(index)


def link_targets_for_weapon(weapon_node):
    ctrl = _link_controller_for(weapon_node)
    if ctrl is None:
        return []
    rows = []
    seen = set()
    for i in range(1, _constraint_target_count(ctrl) + 1):
        target = _constraint_target(ctrl, i)
        if target is None or not rt.isValidNode(target):
            continue
        name = _as_unicode(getattr(target, u"name", u""))
        if not name or name in seen:
            continue
        seen.add(name)
        rows.append({
            u"index": i,
            u"frame": _constraint_frame(ctrl, i),
            u"targetNode": target,
            u"targetBone": name,
        })
    rows.sort(key=lambda r: (int(r.get(u"frame", 0)), int(r.get(u"index", 0))))
    return rows


def link_key_rows_for_weapon(weapon_node):
    ctrl = _link_controller_for(weapon_node)
    if ctrl is None:
        return []
    rows = []
    for i in range(1, _constraint_target_count(ctrl) + 1):
        target = _constraint_target(ctrl, i)
        if target is None or not rt.isValidNode(target):
            continue
        name = _as_unicode(getattr(target, u"name", u""))
        if not name:
            continue
        rows.append({
            u"index": i,
            u"frame": _constraint_frame(ctrl, i),
            u"targetBone": name,
        })
    rows.sort(key=lambda r: (int(r.get(u"frame", 0)), int(r.get(u"index", 0))))
    return rows


def _ensure_weapon_mapping(data, character_name, action_type, export_mode, weapon_node_name, link_targets):
    data[u"character"] = character_name
    data[u"actionType"] = action_type
    data[u"exportMode"] = export_mode
    weapons = data.setdefault(u"weapons", {})
    weapon = weapons.setdefault(weapon_node_name, {})
    weapon[u"weaponNode"] = weapon_node_name
    items = weapon.setdefault(u"items", [])

    max_id = 0
    by_target = {}
    used_attachments = set()
    for item in items:
        try:
            item_id = int(item.get(u"id", 0))
        except Exception:
            item_id = 0
        max_id = max(max_id, item_id)
        target = _as_unicode(item.get(u"targetBone", u""))
        if target:
            by_target[target] = item
        attachment = _as_unicode(item.get(u"constraintNode", u""))
        if attachment:
            used_attachments.add(attachment)

    safe_weapon = _safe_name(weapon_node_name)
    changed = False
    for row in link_targets:
        target = _as_unicode(row.get(u"targetBone", u""))
        if not target:
            continue
        if target in by_target:
            continue
        max_id += 1
        attachment = u"{0}_{1}_{2:02d}".format(_ATTACHMENT_PREFIX, safe_weapon, max_id)
        while attachment in used_attachments:
            max_id += 1
            attachment = u"{0}_{1}_{2:02d}".format(_ATTACHMENT_PREFIX, safe_weapon, max_id)
        item = {
            u"id": max_id,
            u"targetBone": target,
            u"constraintNode": attachment,
        }
        items.append(item)
        by_target[target] = item
        used_attachments.add(attachment)
        changed = True

    items.sort(key=lambda it: int(it.get(u"id", 0)))
    return weapon, changed


def _state_names_from_weapon_mapping(weapon):
    out = []
    for item in weapon.get(u"items", []):
        out.append(_as_unicode(item.get(u"targetBone", u"")))
    return out


def update_selected_weapon_mapping(export_mode=u"indoor", attr_name=u"WeaponState", param_name=u"State_Weapon", character_override=None):
    if not _ensure_op_weapon_lib():
        return False, u"无法加载武器状态 MaxScript 核心库。", {}
    selected = []
    try:
        selected = list(rt.selection)
    except Exception:
        selected = []
    if not selected:
        try:
            count = int(rt.selection.count)
            for i in range(1, count + 1):
                selected.append(rt.selection[i])
        except Exception:
            selected = []
    if not selected:
        return False, u"请先选中武器根骨骼。", {}
    weapon_node = selected[0]

    weapon_node_name = _as_unicode(getattr(weapon_node, u"name", u""))
    action_type, character_name, action_role = detect_character_context(
        export_mode,
        source_name=rt.maxFileName,
        selected_node=weapon_node,
        character_override=character_override,
    )
    if not character_name:
        return False, u"无法识别角色名，请在面板中手动填写。", {}

    targets = link_targets_for_weapon(weapon_node)
    key_rows = link_key_rows_for_weapon(weapon_node)
    if not targets:
        return False, u"未在选中武器上找到基础 Link Constraint 目标。", {}

    map_path = _mapping_file_for(character_name, action_type, export_mode)
    data = _load_mapping_file(map_path)
    weapon, _changed = _ensure_weapon_mapping(
        data, character_name, action_type, export_mode, weapon_node_name, targets
    )
    _save_mapping_file(map_path, data)

    state_names = _state_names_from_weapon_mapping(weapon)
    arr = rt.Array()
    for name in state_names:
        rt.append(arr, name)
    result = rt.OP_WS_Apply(attr_name, param_name, arr)
    code = int(result[0])
    msg = _as_unicode(result[1]) if len(result) > 1 else u""
    info = {
        u"character": character_name,
        u"actionType": action_type,
        u"actionRole": action_role,
        u"weaponNode": weapon_node_name,
        u"mapPath": map_path,
        u"weapon": weapon,
    }
    if code != 0:
        return False, msg or u"生成武器状态属性失败。", info
    written = _write_state_keys_from_link_rows(attr_name, param_name, weapon, key_rows)
    return True, u"已更新 {0} / {1}，共 {2} 个约束目标，自动写入 {3} 个状态 Key。".format(character_name, weapon_node_name, len(state_names), written), info


def set_selected_weapon_state_key(attr_name, param_name, state_id):
    if not _ensure_op_weapon_lib():
        return False, u"无法加载武器状态 MaxScript 核心库。"
    try:
        result = rt.OP_WS_SetStateKey(attr_name, param_name, int(state_id))
        code = int(result[0])
        msg = _as_unicode(result[1]) if len(result) > 1 else u""
        return code == 0, msg
    except Exception as e:
        return False, _as_unicode(e)


def _write_state_keys_from_link_rows(attr_name, param_name, weapon, key_rows):
    by_target = {}
    for item in weapon.get(u"items", []):
        target = _as_unicode(item.get(u"targetBone", u""))
        if target:
            by_target[target] = item
    old_time = None
    written = 0
    try:
        old_time = rt.sliderTime
    except Exception:
        old_time = None
    try:
        for row in key_rows:
            target = _as_unicode(row.get(u"targetBone", u""))
            item = by_target.get(target)
            if not item:
                continue
            try:
                state_id = int(item.get(u"id", 0))
                frame = int(row.get(u"frame", 0))
            except Exception:
                continue
            try:
                rt.sliderTime = frame
            except Exception:
                pass
            ok, _msg = set_selected_weapon_state_key(attr_name, param_name, state_id)
            if ok:
                written += 1
        try:
            rt.OP_WS_FixStep(attr_name, param_name)
        except Exception:
            pass
    finally:
        if old_time is not None:
            try:
                rt.sliderTime = old_time
            except Exception:
                pass
    return written


def _iter_modifiers(node):
    """
    pymxs 下 node.modifiers 为 1-based Max 数组，list(node.modifiers) 常得到空列表。
    """
    if not rt.isValidNode(node):
        return
    try:
        stack = node.modifiers
        try:
            cnt = int(stack.count)
        except Exception:
            cnt = int(getattr(stack, u"Count", 0))
    except Exception:
        return
    for i in range(1, cnt + 1):
        try:
            yield stack[i]
        except Exception:
            continue


def _is_empty_modifier(mod):
    try:
        return rt.classof(mod) == rt.EmptyModifier
    except Exception:
        pass
    try:
        cn = _as_unicode(rt.classof(mod))
        return cn.endswith(u"EmptyModifier") or cn.endswith(u"Empty_Modifier")
    except Exception:
        return False


def _get_ca_def_source(mod, ca_index):
    src = u""
    try:
        dfn = rt.custAttributes.getDef(mod, int(ca_index))
        if dfn is not None:
            src = _as_unicode(getattr(dfn, "source", u""))
    except Exception:
        pass
    if src.strip():
        return src
    if _ensure_op_weapon_lib():
        try:
            return _as_unicode(rt.OP_WS_GetCACustDefSource(mod, int(ca_index)))
        except Exception:
            pass
    return u""


def resolve_node_by_hint(node, name_hint):
    if node is not None and rt.isValidNode(node):
        return node
    if not name_hint:
        return None
    try:
        n = rt.getNodeByName(name_hint, ignoreCase=True)
    except Exception:
        n = None
    if n is not None and rt.isValidNode(n):
        return n
    return None


def resolve_root_for_weapon_mapping(root_obj, root_name_hint=None):
    return resolve_node_by_hint(root_obj, root_name_hint)


def _build_scan_node_list(root_obj, bip_obj):
    """Root 子树 ∪ Bip 子树，去重。"""
    from core.rm_scene import get_all_descendants

    nodes = []
    seen = set()

    def push(n):
        if not rt.isValidNode(n):
            return
        try:
            h = int(rt.getHandleByAnim(n))
        except Exception:
            h = id(n)
        if h in seen:
            return
        seen.add(h)
        nodes.append(n)

    for base in (root_obj, bip_obj):
        if base is None or not rt.isValidNode(base):
            continue
        push(base)
        for d in get_all_descendants(base):
            push(d)
    return nodes


def _append_weapon_entries_from_nodes(nodes, seen_keys, out_entries):
    for node in nodes:
        if not rt.isValidNode(node):
            continue
        for m in _iter_modifiers(node):
            try:
                if not _is_empty_modifier(m):
                    continue
                if _as_unicode(m.name) != _MODIFIER_NAME:
                    continue
            except Exception:
                continue

            try:
                ca_count = int(rt.custAttributes.count(m))
            except Exception:
                ca_count = 0
            for idx in range(1, ca_count + 1):
                try:
                    src = _get_ca_def_source(m, idx)
                except Exception:
                    src = u""
                if not src.strip():
                    continue
                state_labels = _parse_state_names_from_source(src)
                if not state_labels:
                    continue
                curve_params = _parse_curve_param_names(src)
                curve = _pick_curve_param(curve_params)
                attr_block = _parse_attribute_block_name(src)
                bone = _as_unicode(node.name)
                key = (bone, curve, attr_block, tuple(state_labels))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                states = []
                for i, label in enumerate(state_labels):
                    states.append(
                        {
                            u"id": i + 1,
                            u"displayName": label,
                            u"constraintNode": u"",
                        }
                    )
                out_entries.append(
                    {
                        u"boneName": bone,
                        u"weaponNode": u"",
                        u"attributeBlockName": attr_block,
                        u"curveParameterName": curve,
                        u"states": states,
                        u"segments": [],
                    }
                )


def _normalize_entries_from_maxscript_json(arr):
    """将 MaxScript 输出的 JSON 数组规范为与 Python 一致的 entries 结构。"""
    out = []
    if not isinstance(arr, list):
        return out
    for e in arr:
        if not isinstance(e, dict):
            continue
        raw_states = e.get(u"states") or e.get("states") or []
        states = []
        if isinstance(raw_states, list):
            for st in raw_states:
                if not isinstance(st, dict):
                    continue
                sid = st.get(u"id", st.get("id", 0))
                try:
                    sid = int(sid)
                except Exception:
                    sid = 0
                states.append(
                    {
                        u"id": sid,
                        u"displayName": _as_unicode(
                            st.get(u"displayName", st.get("displayName", u""))
                        ),
                        u"constraintNode": _as_unicode(
                            st.get(u"constraintNode", st.get("constraintNode", u""))
                        ),
                    }
                )
        out.append(
            {
                u"boneName": _as_unicode(e.get(u"boneName", e.get("boneName", u""))),
                u"weaponNode": _as_unicode(
                    e.get(u"weaponNode", e.get("weaponNode", u""))
                ),
                u"attributeBlockName": _as_unicode(
                    e.get(u"attributeBlockName", e.get("attributeBlockName", u""))
                ),
                u"curveParameterName": _as_unicode(
                    e.get(u"curveParameterName", e.get("curveParameterName", u""))
                ),
                u"states": states,
                u"segments": e.get(u"segments", e.get("segments", [])) or [],
            }
        )
    return out


def _apply_link_segments_to_entries(entries, start_frame, end_frame):
    try:
        export_start = int(start_frame)
        export_end = int(end_frame)
    except Exception:
        return entries
    if export_end < export_start:
        export_start, export_end = export_end, export_start

    for entry in entries:
        weapon_name = _as_unicode(entry.get(u"weaponNode") or entry.get(u"boneName") or u"")
        weapon_node = _find_node_by_name(weapon_name)
        if weapon_node is None or not rt.isValidNode(weapon_node):
            continue

        state_by_target = {}
        for state in entry.get(u"states", []):
            target = _as_unicode(state.get(u"displayName", u""))
            if not target:
                continue
            try:
                state_id = int(state.get(u"id", 0))
            except Exception:
                state_id = 0
            state_by_target[target] = {
                u"id": state_id,
                u"constraintNode": _as_unicode(state.get(u"constraintNode", u"")),
            }

        link_rows = link_key_rows_for_weapon(weapon_node)
        if not link_rows:
            continue

        segments = []
        row_count = len(link_rows)
        for i, row in enumerate(link_rows):
            target = _as_unicode(row.get(u"targetBone", u""))
            state = state_by_target.get(target)
            if not state:
                continue
            constraint_node = _as_unicode(state.get(u"constraintNode", u""))
            if not constraint_node:
                continue
            try:
                row_frame = int(row.get(u"frame", 0))
            except Exception:
                continue
            if i + 1 < row_count:
                try:
                    next_frame = int(link_rows[i + 1].get(u"frame", row_frame + 1))
                except Exception:
                    next_frame = row_frame + 1
                seg_end = min(next_frame - 1, export_end)
            else:
                seg_end = export_end
            seg_start = max(row_frame, export_start)
            if seg_end < seg_start:
                continue
            segments.append({
                u"start": seg_start - export_start,
                u"end": seg_end - export_start,
                u"stateId": int(state.get(u"id", 0)),
                u"constraintNode": constraint_node,
            })

        if segments:
            entry[u"segments"] = segments
    return entries


def _collect_weapon_state_entries_pymxs(root_obj, bip_obj=None, scene_fallback=True):
    from core.rm_scene import iter_scene_nodes

    entries = []
    seen = set()
    roots = _build_scan_node_list(root_obj, bip_obj)
    _append_weapon_entries_from_nodes(roots, seen, entries)
    if not entries and scene_fallback:
        try:
            scene_nodes = iter_scene_nodes()
        except Exception:
            scene_nodes = []
        _append_weapon_entries_from_nodes(scene_nodes, seen, entries)
    return entries


def collect_weapon_state_entries(root_obj, bip_obj=None, scene_fallback=True):
    """
    优先在 MaxScript 内扫描（for m in obj.modifiers + d.source），与发布前场景一致；
    失败时再回退到 pymxs 扫描。
    """
    rr = root_obj if (root_obj is not None and rt.isValidNode(root_obj)) else None
    bb = bip_obj if (bip_obj is not None and rt.isValidNode(bip_obj)) else None
    if _ensure_op_weapon_lib() and hasattr(rt, "OP_WS_BuildWeaponMappingEntriesJsonString"):
        try:
            js = rt.OP_WS_BuildWeaponMappingEntriesJsonString(
                rr, bb, bool(scene_fallback)
            )
            t = _as_unicode(js).strip()
            if t and t not in (u"[]", "[]"):
                arr = json.loads(t)
                norm = _normalize_entries_from_maxscript_json(arr)
                if norm:
                    return norm
        except Exception:
            pass
    return _collect_weapon_state_entries_pymxs(
        root_obj, bip_obj=bip_obj, scene_fallback=scene_fallback
    )


def _mapping_context_from_export(export_mode, source_max_file=u"", action_role_name=None, selected_node=None):
    action_type, character_name, action_role = detect_character_context(
        export_mode,
        source_name=source_max_file,
        selected_node=selected_node,
        action_role_name=action_role_name,
    )
    map_path = _mapping_file_for(character_name, action_type, export_mode) if character_name else u""
    data = _load_mapping_file(map_path) if map_path else {u"weapons": {}}
    return action_type, character_name, action_role, map_path, data


def _apply_mapping_to_entries(entries, export_mode, source_max_file=u"", action_role_name=None):
    action_type, character_name, action_role, map_path, data = _mapping_context_from_export(
        export_mode, source_max_file=source_max_file, action_role_name=action_role_name
    )
    weapons = data.get(u"weapons", {})
    hierarchy = []
    hierarchy_keys = set()
    for entry in entries:
        weapon_node = _as_unicode(entry.get(u"weaponNode") or entry.get(u"boneName") or u"")
        entry[u"weaponNode"] = weapon_node
        weapon_map = weapons.get(weapon_node, {})
        by_id = {}
        for item in weapon_map.get(u"items", []):
            try:
                by_id[int(item.get(u"id", 0))] = item
            except Exception:
                pass
        for state in entry.get(u"states", []):
            try:
                sid = int(state.get(u"id", 0))
            except Exception:
                sid = 0
            mapped = by_id.get(sid)
            if not mapped:
                continue
            target_bone = _as_unicode(mapped.get(u"targetBone", u""))
            constraint_node = _as_unicode(mapped.get(u"constraintNode", u""))
            if target_bone:
                state[u"displayName"] = target_bone
            if constraint_node:
                state[u"constraintNode"] = constraint_node
            if target_bone and constraint_node:
                key = (constraint_node, target_bone)
                if key not in hierarchy_keys:
                    hierarchy_keys.add(key)
                    hierarchy.append({u"nodeName": constraint_node, u"parentName": target_bone})
    return entries, hierarchy, {
        u"actionType": action_type,
        u"character": character_name,
        u"actionRole": action_role,
        u"mapPath": map_path,
    }


def build_mapping_document(entries, source_max_file=u"", hierarchy_nodes=None, export_mode=u"", action_role_name=u"", character_name=u""):
    return {
        u"formatVersion": 2,
        u"sourceMaxFile": source_max_file,
        u"exportMode": export_mode,
        u"actionRoleName": action_role_name,
        u"characterName": character_name,
        u"entries": entries,
        u"hierarchyNodes": hierarchy_nodes or [],
    }


def _write_mapping_doc_to_path(doc, json_path):
    folder = os.path.dirname(json_path)
    if folder and not os.path.exists(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    with io.open(json_path, u"w", encoding=u"utf-8") as f:
        f.write(_text_type(text))


def write_mapping_doc_for_stems(doc, fbx_folder, stems):
    paths_out = []
    if not doc or not fbx_folder:
        return paths_out
    for stem in stems or []:
        if not stem:
            continue
        out = os.path.join(fbx_folder, _as_unicode(stem) + u"_WeaponStateMapping.json")
        _write_mapping_doc_to_path(doc, out)
        paths_out.append(out)
    return paths_out


def write_weapon_state_mapping_json(
    root_obj,
    json_path,
    source_max_file=None,
    bip_obj=None,
    scene_fallback=True,
    export_mode=u"",
    action_role_name=None,
):
    """
    若场景中存在武器状态 CA，则写入 json_path。
    返回 (written: bool, message: unicode)
    """
    if source_max_file is None:
        try:
            source_max_file = _as_unicode(rt.maxFileName)
        except Exception:
            source_max_file = u""
    entries = collect_weapon_state_entries(
        root_obj, bip_obj=bip_obj, scene_fallback=scene_fallback
    )
    if not entries:
        return (
            False,
            u"未找到「武器挂点数据」或无法解析状态列表（请确认已点「生成属性」；"
            u"若挂在 Bip 骨骼上，请确保工具已识别 Biped/Root）。",
        )
    if export_mode:
        entries, hierarchy, ctx = _apply_mapping_to_entries(
            entries, export_mode, source_max_file=source_max_file, action_role_name=action_role_name
        )
    else:
        hierarchy = []
        ctx = {}
    doc = build_mapping_document(
        entries,
        source_max_file,
        hierarchy,
        export_mode,
        ctx.get(u"actionRole", action_role_name or u""),
        ctx.get(u"character", u""),
    )
    try:
        _write_mapping_doc_to_path(doc, json_path)
    except Exception as e:
        return False, u"写入失败: {0}".format(_as_unicode(e))
    return True, u"已写入 {0}（共 {1} 条骨骼映射）。".format(
        json_path, len(entries)
    )


def _find_node_by_name(name):
    if not name:
        return None
    try:
        return rt.getNodeByName(name, ignoreCase=False)
    except Exception:
        pass
    try:
        return rt.getNodeByName(name, ignoreCase=True)
    except Exception:
        return None


def _delete_nodes_by_names(names):
    for name in names or []:
        node = _find_node_by_name(name)
        if node is not None and rt.isValidNode(node):
            try:
                rt.delete(node)
            except Exception:
                pass


def _ensure_point_helper(name, parent):
    existing = _find_node_by_name(name)
    if existing is not None and rt.isValidNode(existing):
        try:
            rt.delete(existing)
        except Exception:
            pass
    helper = rt.Point()
    helper.name = name
    try:
        helper.size = 5
    except Exception:
        pass
    try:
        helper.box = True
    except Exception:
        pass
    helper.parent = parent
    try:
        helper.position.controller = rt.Position_XYZ()
        helper.rotation.controller = rt.Euler_XYZ()
        helper.scale.controller = rt.ScaleXYZ()
    except Exception:
        pass
    try:
        rt.setUserProp(helper, u"OPWeaponTemp", _TEMP_HELPER_MARK)
    except Exception:
        pass
    return helper


def _safe_axis(value, fallback):
    try:
        if rt.length(value) > 0.00001:
            return rt.normalize(value)
    except Exception:
        pass
    return fallback


def _world_no_scale_matrix(node):
    tm = node.transform
    return rt.matrix3(
        _safe_axis(tm.row1, rt.Point3(1.0, 0.0, 0.0)),
        _safe_axis(tm.row2, rt.Point3(0.0, 1.0, 0.0)),
        _safe_axis(tm.row3, rt.Point3(0.0, 0.0, 1.0)),
        tm.row4,
    )


def cleanup_temporary_weapon_helpers(context):
    names = []
    if isinstance(context, dict):
        names = context.get(u"created", [])
    _delete_nodes_by_names(names)


def prepare_temporary_weapon_helpers(root_obj, bip_obj, export_mode, source_max_file, start_frame, end_frame, action_role_name=None):
    entries = collect_weapon_state_entries(root_obj, bip_obj=bip_obj, scene_fallback=True)
    if not entries:
        return {u"created": [], u"doc": None, u"message": u"未找到武器状态属性。"}
    entries, hierarchy, ctx = _apply_mapping_to_entries(
        entries, export_mode, source_max_file=source_max_file, action_role_name=action_role_name
    )
    entries = _apply_link_segments_to_entries(entries, start_frame, end_frame)
    doc = build_mapping_document(
        entries,
        source_max_file,
        hierarchy,
        export_mode,
        ctx.get(u"actionRole", action_role_name or u""),
        ctx.get(u"character", u""),
    )

    created = []
    for entry in entries:
        weapon_name = _as_unicode(entry.get(u"weaponNode") or entry.get(u"boneName") or u"")
        weapon_node = _find_node_by_name(weapon_name)
        if weapon_node is None or not rt.isValidNode(weapon_node):
            continue
        for state in entry.get(u"states", []):
            attach_name = _as_unicode(state.get(u"constraintNode", u""))
            if not attach_name:
                continue
            parent_name = u""
            for rec in hierarchy:
                if rec.get(u"nodeName") == attach_name:
                    parent_name = _as_unicode(rec.get(u"parentName", u""))
                    break
            parent_node = _find_node_by_name(parent_name)
            if parent_node is None or not rt.isValidNode(parent_node):
                continue
            helper = _ensure_point_helper(attach_name, parent_node)
            created.append(attach_name)
            try:
                with pymxs.animate(True):
                    for frame in range(int(start_frame), int(end_frame) + 1):
                        with pymxs.attime(frame):
                            helper.transform = _world_no_scale_matrix(weapon_node)
                            try:
                                helper.scale = rt.Point3(1.0, 1.0, 1.0)
                            except Exception:
                                pass
            except Exception:
                pass

    return {
        u"created": created,
        u"doc": doc,
        u"message": u"已创建并烘焙 {0} 个临时武器挂点。".format(len(created)),
    }


def build_indoor_character_fbx_stems(base_fbx_name, split_data, only_cam):
    """
    与 rm_indoor_backend.ms 中 taskBaseName 命名一致（仅角色 FBX，不含仅相机导出）。
    """
    if only_cam:
        return []
    stem = os.path.splitext(os.path.basename(_text_type(base_fbx_name)))[0]
    if not split_data:
        return [stem]
    out = []
    for item in split_data:
        joiner = u"_"
        export_suffix = u""
        try:
            if len(item) >= 5:
                _, export_suffix, _s, _e, joiner = item[:5]
            elif len(item) >= 3:
                export_suffix, _s, _e = item[0], item[1], item[2]
                joiner = u"_"
        except Exception:
            continue
        suf = (joiner + export_suffix) if export_suffix else u""
        out.append(stem + _as_unicode(suf))
    return out if out else [stem]


def try_export_indoor_weapon_mapping_splits(
    root_obj,
    bip_obj,
    fbx_folder,
    base_fbx_name,
    split_data,
    only_cam,
    enabled,
    source_max_file=None,
    root_name_hint=None,
    bip_name_hint=None,
    action_role_name=None,
):
    """
    局内发布：按动画拆分片段为每个 stem 各写一份相同内容的映射 JSON（与 FBX 文件名对齐）。
    """
    if not enabled:
        return [], u""
    if not fbx_folder or not base_fbx_name:
        return [], u""
    resolved_root = resolve_node_by_hint(root_obj, root_name_hint)
    resolved_bip = resolve_node_by_hint(bip_obj, bip_name_hint)
    if resolved_root is None and resolved_bip is None:
        return [], (
            u"武器映射未导出：导出后无法解析 Root/Bip 节点（场景已重载）。"
            u"请确认骨骼名称唯一。"
        )
    entries = collect_weapon_state_entries(
        resolved_root, bip_obj=resolved_bip, scene_fallback=True
    )
    if not entries:
        return [], (
            u"未找到「武器挂点数据」或无法解析状态列表（请确认已点「生成属性」；"
            u"若挂在 Bip 骨骼上，本版已支持 Root+Bip 双树扫描）。"
        )
    if source_max_file is None:
        try:
            source_max_file = _as_unicode(rt.maxFileName)
        except Exception:
            source_max_file = u""
    entries, hierarchy, ctx = _apply_mapping_to_entries(
        entries,
        u"indoor",
        source_max_file=source_max_file,
        action_role_name=action_role_name or base_fbx_name,
    )
    doc = build_mapping_document(
        entries,
        source_max_file,
        hierarchy,
        u"indoor",
        ctx.get(u"actionRole", action_role_name or base_fbx_name),
        ctx.get(u"character", u""),
    )
    stems = build_indoor_character_fbx_stems(base_fbx_name, split_data, only_cam)
    if not stems:
        if only_cam:
            return [], u""
        stems = [os.path.splitext(os.path.basename(_text_type(base_fbx_name)))[0]]
    paths_out = []
    try:
        for st in stems:
            out = os.path.join(fbx_folder, st + u"_WeaponStateMapping.json")
            _write_mapping_doc_to_path(doc, out)
            paths_out.append(out)
    except Exception as e:
        return [], u"写入失败: {0}".format(_as_unicode(e))
    msg = u"已写入 {0} 个映射文件（共 {1} 条骨骼映射）。".format(
        len(paths_out), len(entries)
    )
    return paths_out, msg


def try_export_beside_fbx(
    root_obj,
    fbx_folder,
    file_stem,
    enabled,
    source_max_file=None,
    root_name_hint=None,
    bip_obj=None,
    bip_name_hint=None,
    export_mode=u"outdoor",
    action_role_name=None,
):
    """
    单 stem 导出（局外等）：``{fbx_folder}/{file_stem}_WeaponStateMapping.json``。
    """
    if not enabled:
        return [], u""
    if not fbx_folder or not file_stem:
        return [], u""
    stem = os.path.splitext(os.path.basename(file_stem))[0]
    out = os.path.join(fbx_folder, stem + u"_WeaponStateMapping.json")
    resolved_root = resolve_node_by_hint(root_obj, root_name_hint)
    resolved_bip = resolve_node_by_hint(bip_obj, bip_name_hint)
    if resolved_root is None and resolved_bip is None:
        return [], (
            u"武器映射未导出：无法解析 Root/Bip 节点。"
            u"请确认骨骼名称唯一。"
        )
    ok, msg = write_weapon_state_mapping_json(
        resolved_root,
        out,
        source_max_file,
        bip_obj=resolved_bip,
        scene_fallback=True,
        export_mode=export_mode,
        action_role_name=action_role_name or file_stem,
    )
    if ok:
        return [out], msg
    return [], msg

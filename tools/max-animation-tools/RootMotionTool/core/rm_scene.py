# -*- coding: utf-8 -*-
"""
场景对象操作封装：自动检测 Biped/Root、多角色扫描、节点工具函数
"""
from __future__ import division
import pymxs

rt = pymxs.runtime


# ──────────────────────────────────────────────────────────────────
# 节点工具
# ──────────────────────────────────────────────────────────────────


def _node_identity(node):
    """Stable identity for cycle-safe traversal of pymxs node wrappers."""
    try:
        return int(rt.getHandleByAnim(node))
    except Exception:
        return id(node)


def get_all_descendants(root_node):
    """获取所有子孙节点（不含自身），按节点句柄去重并防止层级回环。"""
    result = []
    if root_node is None or not rt.isValidNode(root_node):
        return result
    stack = [root_node]
    seen = set([_node_identity(root_node)])
    while stack:
        curr = stack.pop()
        try:
            children = list(curr.children)
        except Exception:
            children = []
        for child in children:
            try:
                if child is None or not rt.isValidNode(child):
                    continue
            except Exception:
                continue
            child_key = _node_identity(child)
            if child_key in seen:
                continue
            seen.add(child_key)
            stack.append(child)
            result.append(child)
    return result


def iter_scene_nodes():
    """递归遍历场景中的全部节点，避免仅依赖 rt.objects 漏掉某些辅助节点。"""
    result = []
    try:
        roots = list(rt.rootNode.children)
    except Exception:
        roots = []

    stack = list(roots)
    seen = set()
    while stack:
        node = stack.pop()
        try:
            if node is None or not rt.isValidNode(node):
                continue
        except Exception:
            continue
        node_key = _node_identity(node)
        if node_key in seen:
            continue
        seen.add(node_key)
        result.append(node)
        try:
            children = list(node.children)
        except Exception:
            children = []
        for child in children:
            stack.append(child)
    return result


def is_biped_root(node):
    if node is None or not rt.isValidNode(node):
        return False
    try:
        if rt.classof(node) == rt.Biped_Object and node.isRoot:
            return True
    except Exception:
        pass
    try:
        name = node.name or u""
        parent = node.parent
        if name.lower() == u"bip001" and parent is not None and rt.classof(parent) != rt.Biped_Object:
            return True
    except Exception:
        pass
    return False


def get_node_key(node):
    return _node_identity(node)


def unlock_nodes(node_list):
    """解除节点冻结和隐藏，同时处理所在图层"""
    for o in node_list:
        if not rt.isValidNode(o):
            continue
        if o.isFrozen:
            o.isFrozen = False
        if o.isHidden:
            o.isHidden = False
        layer = o.layer
        if layer is not None:
            try:
                if layer.isHidden:
                    layer.isHidden = False
                if layer.isFrozen:
                    layer.isFrozen = False
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────
# 局内：单 Biped 自动检测
# ──────────────────────────────────────────────────────────────────

def auto_detect_scene_objects():
    """
    自动检测场景中的 Biped 根节点和 Root 骨骼。
    检测逻辑与原 MaxScript autoDetectObjects 保持一致。
    返回 (bip_obj, root_obj)，未找到时返回 None。
    """
    bip_obj  = None
    root_obj = None

    # 先按名称找 Root
    root_obj = rt.getNodeByName(u"root", ignoreCase=True)

    # 找 Bip001
    bip_obj = rt.getNodeByName(u"Bip001", ignoreCase=True)
    if bip_obj is None:
        for o in rt.objects:
            if rt.classof(o) == rt.Biped_Object and o.isRoot:
                bip_obj = o
                break

    # 如果按名找不到 Root，尝试从 Bip001 父级推断
    if root_obj is None and bip_obj is not None:
        root_obj = find_root_for_biped(bip_obj)

    return bip_obj, root_obj


def find_root_for_biped(bip_obj):
    """
    从 Bip001 向上找到第一个非 Biped_Object 的父节点作为 Root 骨骼。
    适用于高模（LOD0）场景：Root 骨骼直接命名为角色名。
    """
    if bip_obj is None:
        return None
    parent = bip_obj.parent
    if parent is not None and rt.classof(parent) != rt.Biped_Object:
        return parent
    return None


def resolve_outdoor_character_name(root_bone, bip_obj=None):
    """
    局外角色名来自 Bip001 的父级 Root Bone。
    若根骨骼以 _Root 结尾，仅去掉这个后缀；否则保留完整名称。
    """
    try:
        raw_name = root_bone.name if root_bone is not None else bip_obj.name
    except Exception:
        raw_name = u""
    if raw_name and raw_name.lower().endswith(u"_root"):
        stripped = raw_name[:-5]
        return stripped or raw_name
    return raw_name


# ──────────────────────────────────────────────────────────────────
# 局外：多角色扫描
# ──────────────────────────────────────────────────────────────────

def collect_character_roots():
    """
    扫描场景中所有 Biped 根节点，找到每个 Bip001 的父级 Root Bone。
    适用于局外多角色场景，用于生成角色勾选列表。

    返回 list of dict：
        [{'name': 角色名(str), 'bip': Biped_Object, 'root': BoneNode}, ...]
    """
    results   = []
    seen_bips = set()

    for o in iter_scene_nodes():
        if not is_biped_root(o):
            continue
        obj_id = get_node_key(o)
        if obj_id in seen_bips:
            continue
        seen_bips.add(obj_id)

        root_bone = find_root_for_biped(o)
        char_name = resolve_outdoor_character_name(root_bone, o)

        results.append({
            u"name": char_name,
            u"bip":  o,
            u"root": root_bone,
        })

    return results

# -*- coding: utf-8 -*-
"""
IK 全自动静默斩断：三阶段算法
解决旧版脚本中 IK Object 依赖导致 Root Motion 循环报错、必须手动介入的核心痛点。

三阶段流程：
  Pass 1 — biped.setKey：将 IK 帧段的 Biped 姿势烘焙为世界空间关键帧
  Pass 2 — biped.setFreeKey：将关键帧转为自由 FK 关键帧
  Pass 3 — biped.setIKObject(node, undefined) + ikBlend 归零：
           彻底斩断 IK Object 指针，切断控制器求值依赖链
"""
from __future__ import division
import pymxs

rt = pymxs.runtime


def _get_transform_controller(node):
    try:
        return node.controller
    except Exception:
        pass
    try:
        return rt.getPropertyController(node, rt.Name("transform"))
    except Exception:
        pass
    try:
        return rt.getPropertyController(node, u"transform")
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────────────────────────
# 内部：检测带 IK 帧的肢体节点
# ──────────────────────────────────────────────────────────────────

def _detect_ik_ranges(bip_obj):
    """
    遍历四肢末端节点，检测存在 IK 帧段的节点和帧范围。
    返回 list of (node, [(start_f, end_f), ...])
    """
    # 四肢末端：手腕/脚踝（link=4）
    limb_defs = [
        (rt.Name("larm"), 4),
        (rt.Name("rarm"), 4),
        (rt.Name("lleg"), 4),
        (rt.Name("rleg"), 4),
    ]

    nodes_to_bake = []

    for (limb_id, link) in limb_defs:
        node = None
        try:
            node = rt.biped.getNode(bip_obj, limb_id, link=link)
        except Exception:
            pass
        if node is None:
            continue

        ctrl   = _get_transform_controller(node)
        if ctrl is None:
            continue
        n_keys = rt.numKeys(ctrl)
        if n_keys == 0:
            continue

        ik_ranges = []
        in_range  = False
        start_f   = None

        for i in range(1, n_keys + 1):
            try:
                k     = rt.biped.getKey(ctrl, i)
                is_ik = (k.ikSpace == 1 and k.ikBlend > 0.0)
            except Exception:
                is_ik = False

            if is_ik:
                if not in_range:
                    in_range = True
                    start_f  = k.time
            else:
                if in_range:
                    in_range = False
                    try:
                        end_f = rt.biped.getKey(ctrl, i - 1).time
                        if end_f > start_f:
                            ik_ranges.append((start_f, end_f))
                    except Exception:
                        pass

        # 处理最后一个未闭合的 IK 段
        if in_range and n_keys > 0:
            try:
                end_f = rt.biped.getKey(ctrl, n_keys).time
                if end_f > start_f:
                    ik_ranges.append((start_f, end_f))
            except Exception:
                pass

        if ik_ranges:
            nodes_to_bake.append((node, ik_ranges))

    return nodes_to_bake


# ──────────────────────────────────────────────────────────────────
# 内部：双通道 IK → FK 烘焙
# ──────────────────────────────────────────────────────────────────

def _bake_ik_to_fk(node, ik_ranges):
    """
    Pass 1 + Pass 2：
      Pass 1 — biped.setKey 烘焙世界空间姿势
      Pass 2 — biped.setFreeKey 转为自由 FK 关键帧
    需要先 select 节点，Biped 函数依赖当前选择。
    """
    rt.select(node)
    rt.disableSceneRedraw()
    try:
        with pymxs.animate(True):
            # Pass 1：逐帧烘焙 IK 姿势
            for (start_f, end_f) in ik_ranges:
                for t in range(int(start_f), int(end_f) + 1):
                    with pymxs.attime(t):
                        rt.biped.setKey(node, True, True, True)

            # Pass 2：转为自由 FK 关键帧
            for (start_f, end_f) in ik_ranges:
                for t in range(int(start_f), int(end_f) + 1):
                    with pymxs.attime(t):
                        rt.biped.setFreeKey(node)
    finally:
        rt.enableSceneRedraw()


# ──────────────────────────────────────────────────────────────────
# 内部：斩断 IK Object 指针（核心）
# ──────────────────────────────────────────────────────────────────

def _sever_ik_object(node):
    """
    Pass 3：彻底切断 IK Object 依赖链。
      a) biped.setIKObject(node, undefined) — 清空 IK Object 槽位引用
      b) 遍历所有 Key，将 ikBlend 归零、ikSpace 归零 — 双保险
    两步合用，确保控制器求值不再触发 IK 依赖。
    """
    # a) 清空 IK Object 槽位
    try:
        rt.biped.setIKObject(node, rt.undefined)
    except Exception:
        pass

    # b) 遍历所有 Key 归零 ikBlend
    ctrl   = _get_transform_controller(node)
    if ctrl is None:
        return
    n_keys = rt.numKeys(ctrl)
    for i in range(1, n_keys + 1):
        try:
            k         = rt.biped.getKey(ctrl, i)
            k.ikBlend = 0.0
            k.ikSpace = 0
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────────────────────────

def break_all_ik(bip_obj):
    """
    主入口：检测并全自动静默处理所有 IK。
    无弹窗、无用户介入、全程静默。

    返回处理的节点数量（0 表示场景中没有 IK，无需处理）。
    """
    rt.setCommandPanelTaskMode(rt.Name("motion"))

    nodes_to_bake = _detect_ik_ranges(bip_obj)
    if not nodes_to_bake:
        return 0

    for (node, ik_ranges) in nodes_to_bake:
        _bake_ik_to_fk(node, ik_ranges)
        _sever_ik_object(node)

    rt.clearSelection()
    return len(nodes_to_bake)


def bake_all_ik_to_fk(bip_obj):
    """
    只执行 IK -> FK 双通道烘焙，不尝试清除 IK Object。
    用于在自动拾取失败、需要挂起手动处理前，确保场景已经处于 bake 后状态。
    返回处理的节点数量。
    """
    rt.setCommandPanelTaskMode(rt.Name("motion"))

    nodes_to_bake = _detect_ik_ranges(bip_obj)
    if not nodes_to_bake:
        return 0

    for (node, ik_ranges) in nodes_to_bake:
        _bake_ik_to_fk(node, ik_ranges)

    rt.clearSelection()
    return len(nodes_to_bake)

# -*- coding: utf-8 -*-
from __future__ import print_function


def _issue(
    severity,
    category,
    object_name,
    reason,
    possible_symptom,
    suggested_fix,
    can_resolve_by_mapping,
    controller_path=None,
    constraint_type=None,
    old_target=None,
    new_target=None,
    old_value=None,
    new_value=None,
    confidence=None,
    possible_causes=None,
    frame=None,
):
    return {
        "severity": severity,
        "category": category,
        "object_name": object_name or "",
        "controller_path": controller_path,
        "constraint_type": constraint_type,
        "old_target": old_target,
        "new_target": new_target,
        "old_value": old_value,
        "new_value": new_value,
        "confidence": confidence,
        "possible_causes": possible_causes or [],
        "frame": frame,
        "reason": reason,
        "possible_symptom": possible_symptom,
        "suggested_fix": suggested_fix,
        "can_resolve_by_mapping": bool(can_resolve_by_mapping),
    }


def _to_name_set(rows, key):
    return set([r.get(key) for r in rows if r.get(key)])


def build_diff(old_snapshot, new_snapshot, mapping=None):
    mapping = mapping or {}
    out = {
        "bip_check": {"issues": []},
        "ik_check": {"issues": []},
        "controller_diff": {"issues": []},
        "constraint_diff": {"issues": []},
        "local_object_diff": {"issues": []},
        "morph_diff": {"issues": []},
        "high_risk_items": [],
        "scan_errors": (old_snapshot.get("scan_errors", []) + new_snapshot.get("scan_errors", [])),
        "next_actions": [],
    }

    old_bip = old_snapshot.get("bip", {})
    new_bip = new_snapshot.get("bip", {})
    if old_bip.get("root_name") != new_bip.get("root_name"):
        out["bip_check"]["issues"].append(
            _issue(
                "warning",
                "bip_root_name_changed",
                old_bip.get("root_name") or "",
                "BIP 根节点命名不一致",
                "RootMotion 载体可能错位",
                "统一 BIP 根命名或配置 mapping",
                True,
                confidence="medium",
                possible_causes=["新旧文件 BIP 根命名规范不一致"],
            )
        )

    old_ik = _to_name_set(old_snapshot.get("ik", {}).get("objects", []), "name")
    new_ik = _to_name_set(new_snapshot.get("ik", {}).get("objects", []), "name")
    for missing in sorted(list(old_ik - new_ik)):
        issue = _issue(
            "error",
            "ik_missing_in_new_rig",
            missing,
            "旧动画 IK 对象在新绑定中缺失",
            "IK 端点丢失或漂移",
            "在新绑定补齐对象，或提供 mapping",
            True,
            confidence="high",
            possible_causes=["对象在新绑定中被删除", "对象被重命名但未提供映射"],
        )
        out["ik_check"]["issues"].append(issue)
        out["high_risk_items"].append(dict(issue, **{"category": "high_risk_unmapped"}))

    old_ctrl = {r.get("name"): r for r in old_snapshot.get("controllers", {}).get("controllers", [])}
    new_ctrl = {r.get("name"): r for r in new_snapshot.get("controllers", {}).get("controllers", [])}
    for name in sorted(list(set(old_ctrl.keys()) & set(new_ctrl.keys()))):
        old_type = old_ctrl[name].get("controller_type")
        new_type = new_ctrl[name].get("controller_type")
        if old_type != new_type:
            out["controller_diff"]["issues"].append(
                _issue(
                    "warning",
                    "controller_type_changed",
                    name,
                    "该对象的主控制器类型发生变化",
                    "该骨骼/挂点在动画播放时可能出现姿态差异",
                    "确认该对象在新绑定中应使用的控制器类型，并复查关键动作帧",
                    True,
                    controller_path=name + "/controller",
                    old_value=old_type,
                    new_value=new_type,
                    confidence="high",
                    possible_causes=["绑定控制器方案升级", "对象被技术动画修改过控制器类型"],
                )
            )

    old_cons = _to_name_set(old_snapshot.get("constraints", {}).get("constraints", []), "owner")
    new_cons = _to_name_set(new_snapshot.get("constraints", {}).get("constraints", []), "owner")
    for owner in sorted(list(old_cons - new_cons)):
        out["constraint_diff"]["issues"].append(
            _issue(
                "warning",
                "constraint_missing",
                owner,
                "该对象在旧文件有链接/约束关系，但在新绑定中找不到对应对象",
                "该对象原本跟随关系可能失效（不等于整根骨骼必然缺失）",
                "请在新绑定里确认同名对象是否存在，或通过映射指向正确对象",
                True,
                confidence="low",
                possible_causes=[
                    "同名对象改名/改层级",
                    "约束实现方式变更导致识别差异",
                    "对象确实不存在（需人工确认）",
                ],
            )
        )

    old_local = _to_name_set(old_snapshot.get("local_objects", {}).get("objects", []), "name")
    new_local = _to_name_set(new_snapshot.get("local_objects", {}).get("objects", []), "name")
    for name in sorted(list(old_local - new_local)):
        out["local_object_diff"]["issues"].append(
            _issue(
                "info",
                "local_object_missing",
                name,
                "本地辅助对象在新绑定缺失",
                "道具挂点或 locator 行为不一致",
                "按项目需求决定是否补齐",
                False,
                confidence="medium",
                possible_causes=["新绑定清理了局部 helper", "对象改名未映射"],
            )
        )

    old_morph = set(old_snapshot.get("morph", {}).get("channels", []))
    new_morph = set(new_snapshot.get("morph", {}).get("channels", []))
    for ch in sorted(list(old_morph - new_morph)):
        out["morph_diff"]["issues"].append(
            _issue(
                "warning",
                "morph_channel_missing",
                ch,
                "Morph/表情通道缺失",
                "表情通道丢失或失效",
                "统一 channel 名称或 mapping",
                True,
                confidence="medium",
                possible_causes=["通道改名", "通道被删除", "扫描识别不到目标通道"],
            )
        )

    out["next_actions"] = [
        "先修复 error 与 high_risk_unmapped，再评估 warning。",
        "若存在命名差异，补充 mapping 后重新扫描。",
    ]
    return out

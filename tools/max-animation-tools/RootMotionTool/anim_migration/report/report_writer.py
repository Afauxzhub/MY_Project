# -*- coding: utf-8 -*-
from __future__ import print_function
import io
import json
import os

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
        return value.decode("utf-8")
    except Exception:
        try:
            return value.decode("gbk", "replace")
        except Exception:
            try:
                return _text_type(value)
            except Exception:
                return u""


def _normalize_data(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out[_as_text(k)] = _normalize_data(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_normalize_data(x) for x in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _as_text(value)


def write_json_report(report, out_path):
    folder = os.path.dirname(out_path)
    if folder and (not os.path.exists(folder)):
        os.makedirs(folder)
    normalized = _normalize_data(report)
    payload = json.dumps(normalized, ensure_ascii=False, indent=2)
    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(_as_text(payload))
    return out_path


def _iter_issues(report):
    keys = [
        "bip_check",
        "ik_check",
        "controller_diff",
        "constraint_diff",
        "local_object_diff",
        "morph_diff",
    ]
    for key in keys:
        for issue in report.get(key, {}).get("issues", []):
            yield key, issue


def _severity_rank(sev):
    return {"error": 0, "warning": 1, "info": 2}.get(_as_text(sev).lower(), 9)


def _severity_cn(sev):
    s = _as_text(sev).lower()
    if s == "error":
        return u"阻断"
    if s == "warning":
        return u"注意"
    return u"提示"


def _section_cn(sec):
    return {
        "bip_check": u"BIP 检查",
        "ik_check": u"IK 对象检查",
        "controller_diff": u"控制器差异",
        "constraint_diff": u"约束差异",
        "local_object_diff": u"本地辅助对象差异",
        "morph_diff": u"Morph/表情差异",
    }.get(_as_text(sec), _as_text(sec))


def _artist_reason(sec, issue):
    category = _as_text(issue.get("category", ""))
    if category == "constraint_missing":
        return u"旧动画里这个对象有“链接参数/约束关系”，但新绑定中没找到对应对象。"
    if category == "controller_type_changed":
        old_v = _as_text(issue.get("old_value", "")) or u"未知"
        new_v = _as_text(issue.get("new_value", "")) or u"未知"
        return u"该对象控制器类型由 {0} 变为 {1}。".format(old_v, new_v)
    return _as_text(issue.get("reason", ""))


def _artist_impact(sec, issue):
    category = _as_text(issue.get("category", ""))
    if category == "constraint_missing":
        return u"常见表现是挂点不跟随、道具漂移或跟随错误（不一定代表骨骼本体缺失）。"
    if category == "controller_type_changed":
        return u"常见表现是同一动作在新绑定上姿态/轨迹不完全一致。"
    return _as_text(issue.get("possible_symptom", ""))


def _artist_fix(sec, issue):
    category = _as_text(issue.get("category", ""))
    if category == "constraint_missing":
        return u"在新绑定中确认该对象是否存在且命名一致；若改名，请在映射里指定旧名->新名。"
    if category == "controller_type_changed":
        old_v = _as_text(issue.get("old_value", "")) or u"未知"
        new_v = _as_text(issue.get("new_value", "")) or u"未知"
        return u"确认这个变化是否符合绑定设计（{0} -> {1}）；不符合时让绑定同学回退或提供映射规则。".format(old_v, new_v)
    return _as_text(issue.get("suggested_fix", ""))


def _status_cn(light):
    x = _as_text(light).lower()
    if x == "red":
        return u"红灯（阻断，先处理）"
    if x == "yellow":
        return u"黄灯（可继续，但建议先确认）"
    if x == "green":
        return u"绿灯（当前无阻断）"
    return u"未知"


def _confidence_cn(level):
    x = _as_text(level).lower()
    return {"high": u"高", "medium": u"中", "low": u"低"}.get(x, u"未标注")


def write_text_report(report, out_path):
    report = _normalize_data(report)
    folder = os.path.dirname(out_path)
    if folder and (not os.path.exists(folder)):
        os.makedirs(folder)
    lines = []
    summary = report.get("summary", {})
    input_data = report.get("input", {})
    all_issues = list(_iter_issues(report))
    all_issues.sort(key=lambda x: _severity_rank(x[1].get("severity")))

    lines.append(u"=== 动画绑定更新检查报告（动画师版） ===")
    lines.append(u"检查时间：{0}".format(_as_text(report.get("timestamp", ""))))
    lines.append(u"检查结论：{0}".format(_status_cn(summary.get("status_light", "unknown"))))
    lines.append(u"问题统计：阻断 {0} | 注意 {1} | 提示 {2}".format(summary.get("error_count", 0), summary.get("warning_count", 0), summary.get("info_count", 0)))
    lines.append(u"")

    phase3 = report.get("phase3_local_objects", {}) or {}
    if phase3.get("enabled"):
        summary3 = phase3.get("summary", {}) or {}
        lines.append(u"【Phase 3 本地对象迁移】")
        lines.append(u"- 状态：{0}".format(_as_text(phase3.get("status", "unknown"))))
        lines.append(
            u"- 统计：扫描 {0} | 计划 {1} | 成功 {2} | 失败 {3}".format(
                summary3.get("scanned_count_old", 0),
                summary3.get("planned_count", 0),
                summary3.get("migrated_count", 0),
                summary3.get("failed_count", 0),
            )
        )
        v = phase3.get("validation", {}) or {}
        v_sum = v.get("summary", {}) or {}
        lines.append(
            u"- 校验：样本 {0} | 超阈值 {1}".format(
                v_sum.get("sample_count", 0),
                v_sum.get("exceeded_count", 0),
            )
        )
        lines.append(u"")
    phase3_existing = report.get("phase3_existing_object_prepare", {}) or {}
    if phase3_existing.get("enabled"):
        s = phase3_existing.get("summary", {}) or {}
        lines.append(u"【Phase 3 已存在对象准备】")
        lines.append(u"- 状态：{0}".format(_as_text(phase3_existing.get("status", "unknown"))))
        lines.append(u"- 匹配：成功 {0} | mapping {1} | 同名 {2} | 缺失跳过 {3}".format(
            s.get("matched", 0),
            s.get("mapping_used", 0),
            s.get("same_name_used", 0),
            s.get("skipped_missing_object", 0),
        ))
        lines.append(u"")
    phase4 = report.get("phase4_constraints", {}) or {}
    if phase4.get("enabled"):
        s = phase4.get("summary", {}) or {}
        lines.append(u"【Phase 4 约束重建】")
        lines.append(u"- 状态：{0}".format(_as_text(phase4.get("status", "unknown"))))
        lines.append(u"- 统计：扫描 {0} | 重建 {1} | owner缺失 {2} | target缺失 {3} | 不支持 {4} | 失败 {5}".format(
            s.get("scanned_count", 0),
            s.get("rebuilt_count", 0),
            s.get("skipped_missing_owner", 0),
            s.get("skipped_missing_target", 0),
            s.get("skipped_unsupported_constraint", 0),
            s.get("failed_count", 0),
        ))
        lines.append(u"")
    phase5 = report.get("phase5_non_bip_animation", {}) or {}
    if phase5.get("enabled"):
        s = phase5.get("summary", {}) or {}
        lines.append(u"【Phase 5 非 BIP 动画】")
        lines.append(u"- 状态：{0}".format(_as_text(phase5.get("status", "unknown"))))
        lines.append(u"- XAF：尝试 {0} | 成功 {1} | 失败 {2}".format(
            s.get("xaf_attempted", 0),
            s.get("xaf_succeeded", 0),
            s.get("xaf_failed", 0),
        ))
        lines.append(u"- TRS fallback：尝试 {0} | 成功 {1} | 约束owner跳过 {2} | 校验超阈值 {3}".format(
            s.get("trs_fallback_attempted", 0),
            s.get("trs_fallback_succeeded", 0),
            s.get("skipped_constrained_owner", 0),
            s.get("validation_exceeded", 0),
        ))
        lines.append(u"")
    lines.append(u"【检查文件】")
    lines.append(u"- 当前动画：{0}".format(_as_text(input_data.get("old_anim_path", ""))))
    lines.append(u"- 新版绑定：{0}".format(_as_text(input_data.get("new_rig_path", ""))))
    lines.append(u"- 映射配置：{0}".format(_as_text(input_data.get("mapping_path", u"未提供")) or u"未提供"))
    lines.append(u"")
    lines.append(u"【建议处理顺序】")
    if summary.get("error_count", 0) > 0:
        lines.append(u"1) 先处理全部“阻断”项（不处理会导致迁移风险高）。")
    if summary.get("warning_count", 0) > 0:
        lines.append(u"2) 再确认“注意”项（可能出现姿态偏差、约束抖动）。")
    lines.append(u"3) 最后检查“提示”项（按项目需求决定是否处理）。")
    lines.append(u"")

    lines.append(u"【问题明细】")
    if not all_issues:
        lines.append(u"- 未发现差异问题。")
    for idx, pair in enumerate(all_issues):
        sec, issue = pair
        lines.append(u"{0}. [{1}] {2} - {3}".format(idx + 1, _severity_cn(issue.get("severity", "info")), _section_cn(sec), _as_text(issue.get("object_name", u"<未命名对象>"))))
        lines.append(u"   - 现象：{0}".format(_artist_reason(sec, issue)))
        lines.append(u"   - 影响：{0}".format(_artist_impact(sec, issue)))
        lines.append(u"   - 建议：{0}".format(_artist_fix(sec, issue)))
        lines.append(u"   - 可用映射修复：{0}".format(u"是" if issue.get("can_resolve_by_mapping") else u"否"))
        lines.append(u"   - 判定置信度：{0}".format(_confidence_cn(issue.get("confidence"))))
        causes = issue.get("possible_causes") or []
        if causes:
            lines.append(u"   - 可能原因：{0}".format(u"；".join([_as_text(x) for x in causes])))
        if issue.get("controller_path"):
            lines.append(u"   - 控制器路径：{0}".format(_as_text(issue.get("controller_path"))))
        if issue.get("old_value") or issue.get("new_value"):
            lines.append(u"   - 类型变化：{0} -> {1}".format(_as_text(issue.get("old_value", "")), _as_text(issue.get("new_value", ""))))
        if issue.get("constraint_type"):
            lines.append(u"   - 约束类型：{0}".format(_as_text(issue.get("constraint_type"))))
        if issue.get("old_target") or issue.get("new_target"):
            lines.append(u"   - 目标变化：{0} -> {1}".format(_as_text(issue.get("old_target", "")), _as_text(issue.get("new_target", ""))))
        lines.append(u"")

    if report.get("scan_errors"):
        lines.append(u"【扫描异常（工具侧）】")
        for e in report.get("scan_errors", []):
            lines.append(u"- {0}：{1}".format(_as_text(e.get("category", "scan_error")), _as_text(e.get("reason", ""))))
        lines.append(u"")

    lines.append(u"【下一步建议】")
    for item in report.get("next_actions", []):
        lines.append(u"- {0}".format(_as_text(item)))
    if not report.get("next_actions"):
        lines.append(
            u"- 根据问题明细先修复阻断项，再重新执行一次只读检查确认状态变更。"
        )
    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(u"\n".join(lines))
    return out_path

# -*- coding: utf-8 -*-
from __future__ import print_function
import datetime
import io
import json
import os
import uuid

from anim_migration.scanner.scene_snapshot import build_scene_snapshot
from anim_migration.compare.diff_engine import build_diff
from anim_migration.report.report_schema import base_report
from anim_migration.report.report_writer import write_json_report, write_text_report


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
            b = str(value)
            try:
                return b.decode("utf-8")
            except Exception:
                return b.decode("gbk", "replace")
        except Exception:
            return u""


def _now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _load_mapping(mapping_path):
    if not mapping_path:
        return None
    if not os.path.exists(mapping_path):
        raise RuntimeError(u"mapping_path does not exist: {0}".format(_as_text(mapping_path)))
    with io.open(mapping_path, "r", encoding="utf-8") as f:
        return json.loads(f.read())


def _collect_issue_counts(report):
    error_count = 0
    warning_count = 0
    info_count = 0
    for key in ("bip_check", "ik_check", "controller_diff", "constraint_diff", "local_object_diff", "morph_diff"):
        for issue in report.get(key, {}).get("issues", []):
            sev = issue.get("severity", "info")
            if sev == "error":
                error_count += 1
            elif sev == "warning":
                warning_count += 1
            else:
                info_count += 1
    for issue in report.get("scan_errors", []):
        sev = issue.get("severity", "error")
        if sev == "error":
            error_count += 1
        elif sev == "warning":
            warning_count += 1
        else:
            info_count += 1
    return error_count, warning_count, info_count


def _status_light(report):
    high_risk = report.get("high_risk_items", [])
    has_unmapped = any([x.get("category") == "high_risk_unmapped" for x in high_risk])
    if report["summary"]["error_count"] > 0 or has_unmapped:
        return "red"
    if report["summary"]["warning_count"] > 0:
        return "yellow"
    return "green"


def run_readonly_scan(old_anim_path, new_rig_path, mapping_path=None, out_dir=None):
    report = base_report()
    report["session_id"] = "scan_{0}".format(uuid.uuid4().hex[:12])
    report["timestamp"] = _now_iso()
    report["input"] = {
        "old_anim_path": _as_text(old_anim_path),
        "new_rig_path": _as_text(new_rig_path),
        "mapping_path": _as_text(mapping_path) if mapping_path else None,
    }

    try:
        mapping = _load_mapping(mapping_path)
    except Exception as e:
        # mapping 在 Phase 1 为可选输入，读取失败不阻断，只提示结果可能放大。
        report["scan_errors"].append(
            {
                "severity": "warning",
                "category": "mapping_load_error",
                "object_name": "",
                "controller_path": None,
                "constraint_type": None,
                "old_target": None,
                "new_target": None,
                "frame": None,
                "reason": _as_text(e),
                "possible_symptom": "映射未生效，差异可能放大",
                "suggested_fix": "修复 mapping 文件路径或 JSON 格式",
                "can_resolve_by_mapping": False,
            }
        )
        mapping = None

    old_snapshot = build_scene_snapshot(old_anim_path)
    new_snapshot = build_scene_snapshot(new_rig_path)
    diff = build_diff(old_snapshot, new_snapshot, mapping)
    report.update(diff)
    report["scan_errors"] = report.get("scan_errors", []) + diff.get("scan_errors", [])

    e, w, i = _collect_issue_counts(report)
    report["summary"]["error_count"] = e
    report["summary"]["warning_count"] = w
    report["summary"]["info_count"] = i
    report["summary"]["status_light"] = _status_light(report)
    report["summary"]["pass_block"] = report["summary"]["status_light"] == "red"

    if not out_dir:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reports")
        out_dir = os.path.abspath(out_dir)
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    base = "readonly_scan_{0}".format(report["session_id"])
    json_path = os.path.join(out_dir, base + ".json")
    txt_path = os.path.join(out_dir, base + ".txt")
    report["report_json_path"] = write_json_report(report, json_path)
    report["report_txt_path"] = write_text_report(report, txt_path)
    return report

# -*- coding: utf-8 -*-
from __future__ import print_function
import io
import json
import os
import shutil

from anim_migration.migration.package_exporter import export_old_migration_package
from anim_migration.migration.package_importer import apply_package_to_new_rig
from anim_migration.migration.layer_xaf_bridge import (
    export_canonical_package,
    apply_canonical_package,
    _write_report as _write_canonical_report,
)
from anim_migration.migration.canonical_bridge import _json_write
from anim_migration.workflow.backup import create_backup
from anim_migration.workflow.max_dialogs import SilentFileDialogs
from anim_migration.workflow.version_metadata import normalize_version, write_scene_binding_version

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
        return u""


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return _as_text(value).strip().lower() in ("true", "1", "yes", "ok")


def _as_kv_dict(ms_kv):
    out = {}
    if ms_kv is None:
        return out
    def _normalize_key(key):
        text = _as_text(key).strip()
        if text.startswith("#"):
            text = text[1:]
        if text.startswith("name:"):
            text = text[5:]
        return text
    def _looks_like_key(key):
        text = _normalize_key(key)
        return text in (
            "ok",
            "output_max_path",
            "report_json",
            "report_txt",
            "warnings",
            "message",
            "input_paths",
            "output_paths",
            "precheck",
            "export",
            "import",
            "save",
            "postcheck",
            "blockers",
            "info",
            "next_actions",
        )
    try:
        count = int(ms_kv.count)
    except Exception:
        try:
            count = len(ms_kv)
        except Exception:
            count = 0

    # pymxs may expose Max arrays as either 0-based or 1-based depending on
    # access path. Walk both safely and only accept recognized key tokens.
    for start in (0, 1):
        i = start
        while i <= count - 1:
            try:
                raw_key = ms_kv[i]
                if _looks_like_key(raw_key):
                    out[_normalize_key(raw_key)] = ms_kv[i + 1]
                    i += 2
                    continue
            except Exception:
                pass
            i += 1

    if out:
        return out

    i = 1
    while i <= count - 1:
        try:
            key = _normalize_key(ms_kv[i])
            out[key] = ms_kv[i + 1]
        except Exception:
            try:
                key = _normalize_key(ms_kv[i - 1])
                out[key] = ms_kv[i]
            except Exception:
                pass
        i += 2
    return out


def _append_phase3_text_report(txt_path, phase3_report):
    if (not txt_path) or (not os.path.exists(txt_path)):
        return
    summary = phase3_report.get("summary", {}) or {}
    validation = phase3_report.get("validation", {}) or {}
    validation_summary = validation.get("summary", {}) or {}
    lines = [
        u"",
        u"Phase 3 Local Objects",
        u"Status: {0}".format(_as_text(phase3_report.get("status", ""))),
        u"Scanned Old: {0}".format(summary.get("scanned_count_old", 0)),
        u"Planned: {0}".format(summary.get("planned_count", 0)),
        u"Migrated: {0}".format(summary.get("migrated_count", 0)),
        u"Skipped: {0}".format(summary.get("skipped_count", 0)),
        u"Failed: {0}".format(summary.get("failed_count", 0)),
        u"Validation Samples: {0}".format(validation_summary.get("sample_count", 0)),
        u"Validation Exceeded: {0}".format(validation_summary.get("exceeded_count", 0)),
    ]
    warnings = phase3_report.get("warnings", []) or []
    errors = phase3_report.get("errors", []) or []
    if warnings:
        lines.append(u"Warnings ({0}):".format(len(warnings)))
        for item in warnings[:20]:
            lines.append(u"  - {0} frame {1}".format(_as_text(item.get("object_name", "")), item.get("frame", "")))
    if errors:
        lines.append(u"Errors ({0}):".format(len(errors)))
        for item in errors[:20]:
            lines.append(u"  - {0}: {1}".format(_as_text(item.get("name", item.get("object_name", ""))), _as_text(item.get("message", ""))))
    with io.open(txt_path, "a", encoding="utf-8") as f:
        f.write(u"\n".join(lines))
        f.write(u"\n")


def _append_phase_report_summary(txt_path, title, report):
    if (not txt_path) or (not os.path.exists(txt_path)):
        return
    summary = (report or {}).get("summary", {}) or {}
    lines = [
        u"",
        _as_text(title),
        u"Status: {0}".format(_as_text((report or {}).get("status", ""))),
    ]
    for key in sorted(summary.keys()):
        lines.append(u"{0}: {1}".format(_as_text(key), summary.get(key)))
    warnings = (report or {}).get("warnings", []) or []
    errors = (report or {}).get("errors", []) or []
    if warnings:
        lines.append(u"Warnings ({0})".format(len(warnings)))
    if errors:
        lines.append(u"Errors ({0})".format(len(errors)))
    with io.open(txt_path, "a", encoding="utf-8") as f:
        f.write(u"\n".join(lines))
        f.write(u"\n")


def _update_phase3_json_report(json_path, phase3_report):
    if (not json_path) or (not os.path.exists(json_path)):
        return
    try:
        with io.open(json_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
    except Exception:
        data = {}
    data["phase3_local_objects"] = phase3_report
    with io.open(json_path, "w", encoding="utf-8") as f:
        f.write(_as_text(json.dumps(data, ensure_ascii=False, indent=2)))


def _update_json_report_sections(json_path, sections):
    if (not json_path) or (not os.path.exists(json_path)):
        return
    try:
        with io.open(json_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
    except Exception:
        data = {}
    for key, value in (sections or {}).items():
        data[key] = value
    with io.open(json_path, "w", encoding="utf-8") as f:
        f.write(_as_text(json.dumps(data, ensure_ascii=False, indent=2)))


def _write_phase3_reports(bip_data, phase3_report):
    txt_path = _as_text(bip_data.get("report_txt", ""))
    json_path = _as_text(bip_data.get("report_json", ""))
    try:
        _append_phase3_text_report(txt_path, phase3_report)
    except Exception:
        pass
    try:
        _update_phase3_json_report(json_path, phase3_report)
    except Exception:
        pass


def _write_phase_reports(bip_data, sections):
    txt_path = _as_text(bip_data.get("report_txt", ""))
    json_path = _as_text(bip_data.get("report_json", ""))
    title_map = {
        "phase3_existing_object_prepare": u"Phase 3 Existing Object Prepare",
        "phase4_constraints": u"Phase 4 Constraints",
        "phase5_non_bip_animation": u"Phase 5 Non-BIP Animation",
    }
    try:
        for key, report in (sections or {}).items():
            _append_phase_report_summary(txt_path, title_map.get(key, key), report)
    except Exception:
        pass
    try:
        _update_json_report_sections(json_path, sections)
    except Exception:
        pass


def _load_mapping(mapping_path):
    if not mapping_path:
        return {}
    with io.open(mapping_path, "r", encoding="utf-8") as f:
        data = json.loads(f.read())
    if isinstance(data, dict):
        for key in ("objects", "mapping", "name_map", "nameMap"):
            value = data.get(key)
            if isinstance(value, dict):
                return value
        pairs = data.get("pairs")
        if isinstance(pairs, list):
            out = {}
            for item in pairs:
                if isinstance(item, dict):
                    src = item.get("source") or item.get("old") or item.get("from")
                    dst = item.get("target") or item.get("new") or item.get("to")
                    if src and dst:
                        out[_as_text(src)] = _as_text(dst)
            return out
        return data
    if isinstance(data, list):
        out = {}
        for item in data:
            if isinstance(item, dict):
                src = item.get("source") or item.get("old") or item.get("from")
                dst = item.get("target") or item.get("new") or item.get("to")
                if src and dst:
                    out[_as_text(src)] = _as_text(dst)
        return out
    return {}


def _load_family_adapter_override(path):
    """Load a family-level semantic exception file, never a version-pair map."""
    if not path:
        return {}
    with io.open(path, "r", encoding="utf-8") as stream:
        data = json.loads(stream.read())
    if not isinstance(data, dict) or data.get("kind") != "binding_family_adapter_override":
        raise RuntimeError(
            u"版本对版本骨骼映射已停用；这里只接受 kind=binding_family_adapter_override 的家族级兼容规则"
        )
    if not _as_text(data.get("source_family", "")).strip() or not _as_text(data.get("target_family", "")).strip():
        raise RuntimeError(u"家族级兼容规则缺少 source_family 或 target_family")
    objects = data.get("objects", {})
    if not isinstance(objects, dict):
        raise RuntimeError(u"家族级兼容规则 objects 必须是对象")
    return objects


def _load_migrate_service(rt, tool_root):
    core = os.path.join(tool_root, "maxscript", "ReferenceRigCore.ms")
    if not os.path.exists(core):
        raise RuntimeError(u"未找到迁移核心脚本: {0}".format(core))
    rt.fileIn(core)
    if not hasattr(rt, "RR_MigrateService"):
        raise RuntimeError(u"迁移服务未加载: RR_MigrateService")


def _default_output_for(old_anim_path):
    stem, _ = os.path.splitext(old_anim_path)
    import re
    base_stem = re.sub(r"_RigUpdate_v\d{3}$", "", stem, flags=re.IGNORECASE)
    cand = base_stem + u"_RigUpdate_v001.max"
    if not os.path.exists(cand):
        return cand
    for i in range(2, 1000):
        c2 = base_stem + u"_RigUpdate_v{0:03d}.max".format(i)
        if not os.path.exists(c2):
            return c2
    return base_stem + u"_RigUpdate.max"


def _next_available_output_path(output_path):
    output_path = _as_text(output_path)
    if not output_path or not os.path.exists(output_path):
        return output_path
    return _default_output_for(output_path)


def _write_package_text_report(report, txt_path):
    folder = os.path.dirname(txt_path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    export_summary = ((report.get("package_manifest", {}) or {}).get("summary", {}) or {})
    export_blockers = ((report.get("package_manifest", {}) or {}).get("blockers", []) or [])
    export_warnings = ((report.get("package_manifest", {}) or {}).get("warnings", []) or [])
    package_paths = ((report.get("package_manifest", {}) or {}).get("paths", {}) or {})
    import_report = report.get("import_report", {}) or {}
    phase4 = import_report.get("phase4_constraints", {}) or {}
    phase4_summary = phase4.get("summary", {}) or {}
    phase5 = import_report.get("phase5_non_bip_animation", {}) or {}
    phase5_summary = phase5.get("summary", {}) or {}
    channel_warning_items = phase5.get("channel_key_warnings", []) or []
    merge_helpers = import_report.get("merge_helpers", {}) or {}
    merge_summary = merge_helpers.get("summary", {}) or {}
    xaf_items = phase5.get("items", []) or []
    xaf_fail_samples = [x for x in xaf_items if x.get("xaf_import_status") in ("skipped_export_failed", "failed")][:10]
    bip_com = import_report.get("bip_com_height", {}) or {}
    anim_range = import_report.get("animation_range", {}) or {}
    cleanup = import_report.get("target_rig_key_cleanup", {}) or {}
    lines = [
        u"=== Animation 动画迁移报告（迁移包版） ===",
        u"Overall OK: {0}".format(report.get("ok", False)),
        u"Message: {0}".format(_as_text(report.get("message", ""))),
        u"Ignore Non-BIP Errors: {0}".format(bool(import_report.get("ignore_non_bip_errors", False))),
        u"Continue Past Preflight Blockers: {0}".format(bool(import_report.get("allow_preflight_blockers", False))),
        u"Skip Missing Constraint Targets: {0}".format(
            bool(import_report.get("skip_missing_constraint_targets", False))
        ),
        u"Loaded Scene: {0}".format(_as_text(import_report.get("loaded_scene_path", ""))),
        u"",
        u"Backup: {0}".format(_as_text(((report.get("workflow", {}) or {}).get("backup_path", "")))),
        u"Overwrite Original: {0}".format(((report.get("workflow", {}) or {}).get("overwrote_original", False))),
        u"",
        u"Package: {0}".format(_as_text(report.get("package_dir", ""))),
        u"Output: {0}".format(_as_text(report.get("output_max_path", ""))),
        u"Animation Range: {0} -> {1}".format(anim_range.get("start", ""), anim_range.get("end", "")),
        u"Target Rig Key Cleanup: {0} keys_deleted={1} zero_keys_added={2}".format(
            _as_text(cleanup.get("status", "")),
            cleanup.get("keys_deleted", 0),
            cleanup.get("zero_keys_added", 0),
        ),
        u"Skipped Script/Expression Controllers: {0}".format(
            cleanup.get("skipped_script_expression_controllers", 0)
        ),
        u"",
        u"[BIP]",
        u"Export OK: {0}".format((((report.get("package_manifest", {}) or {}).get("bip", {}) or {}).get("ok", False))),
        u"Import OK: {0}".format(((import_report.get("bip_import", {}) or {}).get("ok", False))),
        u"COM Height: {0} delta_z={1} max_error={2}".format(_as_text(bip_com.get("status", "")), bip_com.get("delta_z", 0.0), bip_com.get("max_abs_error", 0.0)),
        u"",
        u"[Export Package]",
        u"Binding Version: {0} -> {1}".format(
            _as_text(export_summary.get("source_binding_version", "")) or u"unknown",
            _as_text(export_summary.get("target_binding_version", "")) or u"unknown",
        ),
        u"Non-BIP Animated: {0}".format(export_summary.get("non_bip_animated_count", 0)),
        u"Complete Animation Tracks: {0}".format(export_summary.get("track_count", 0)),
        u"Morph Channels: {0}".format(export_summary.get("morph_channel_count", 0)),
        u"Preflight Blockers: {0}".format(export_summary.get("preflight_blocker_count", 0)),
        u"Ignored Preflight Blockers: {0}".format(export_summary.get("continued_preflight_blocker_count", 0)),
        u"Preflight Warnings: {0}".format(export_summary.get("preflight_warning_count", 0)),
        u"Ignored Obsolete Morpher: {0}".format(export_summary.get("ignored_obsolete_morpher_count", 0)),
        u"Ignored Frame-0-only Nodes/Tracks: {0}/{1}".format(
            export_summary.get("ignored_frame0_only_node_count", 0),
            export_summary.get("ignored_frame0_only_track_count", 0),
        ),
        u"XAF Export Strategy: {0} (batch threshold {1}, chunk size {2})".format(
            _as_text(export_summary.get("xaf_export_strategy", "")),
            export_summary.get("xaf_batch_threshold", 0),
            export_summary.get("xaf_chunk_size", 0),
        ),
        u"XAF Export Succeeded: {0}".format(export_summary.get("xaf_export_succeeded", 0)),
        u"XAF Export Failed (export stage): {0}".format(export_summary.get("xaf_export_failed", 0)),
        u"Constraints: {0} ready {1} skipped_owner {2} skipped_target {3} skipped_internal {4}".format(
            export_summary.get("constraint_count", 0),
            export_summary.get("constraint_ready_count", 0),
            export_summary.get("constraint_skipped_missing_owner", 0),
            export_summary.get("constraint_skipped_missing_target", 0),
            export_summary.get("constraint_preserved_binding_internal", 0),
        ),
        u"Mapping: explicit {0} | auto_whitespace {1} | auto_layer {2}".format(
            export_summary.get("mapping_explicit_count", 0),
            export_summary.get("mapping_auto_whitespace_count", 0),
            export_summary.get("mapping_auto_layer_count", 0),
        ),
        u"Layer Mapping Table: accepted {0} | inferred parents {1} | ambiguous {2} | insufficient hierarchy {3}".format(
            export_summary.get("layer_mapping_accepted_count", 0),
            export_summary.get("layer_mapping_hierarchy_parent_count", 0),
            export_summary.get("layer_mapping_ambiguous_count", 0),
            export_summary.get("layer_mapping_insufficient_hierarchy_count", 0),
        ),
        u"Layer Mapping JSON: {0}".format(_as_text(package_paths.get("layer_mapping_json", ""))),
        u"IK Objects: {0}".format(export_summary.get("ik_object_count", 0)),
        u"",
        u"[Constraints]",
        u"Removed Absent In Old Animation: {0}".format(phase4_summary.get("removed_absent_count", 0)),
        u"Rebuilt: {0}".format(phase4_summary.get("rebuilt_count", 0)),
        u"Preserved Missing Targets: {0}".format(phase4_summary.get("preserved_new_binding_missing_targets_count", 0)),
        u"Skipped All Targets Missing: {0}".format(phase4_summary.get("skipped_all_targets_missing_count", 0)),
        u"Missing Owner: {0}".format(phase4_summary.get("skipped_missing_owner", 0)),
        u"Missing Target: {0}".format(phase4_summary.get("skipped_missing_target", 0)),
        u"Unsupported/Skipped: {0}".format(phase4_summary.get("skipped_unsupported_constraint", 0)),
        u"Failed: {0}".format(phase4_summary.get("failed_count", 0)),
        u"",
        u"[Non-BIP XAF]",
        u"Candidates: {0}".format(phase5_summary.get("candidate_count", 0)),
        u"XAF Export Failed: {0}".format(phase5_summary.get("xaf_export_failed", 0)),
        u"XAF Import Succeeded: {0}".format(phase5_summary.get("xaf_import_succeeded", 0)),
        u"XAF Import Failed: {0}".format(phase5_summary.get("xaf_import_failed", 0)),
        u"Missing Object: {0}".format(phase5_summary.get("skipped_missing_object", 0)),
        u"Skipped Missing Constraint Target: {0}".format(
            phase5_summary.get("skipped_missing_constraint_target", 0)
        ),
        u"Ignored Obsolete Tracks: {0}".format(phase5_summary.get("ignored_obsolete_tracks", 0)),
        u"Ignored Preflight Objects: {0}".format(phase5_summary.get("ignored_preflight_blockers", 0)),
        u"Morph Bake Only (XAF skipped): {0}".format(phase5_summary.get("morph_bake_only", 0)),
        u"Channel Key Warnings: {0}".format(phase5_summary.get("channel_key_warning_count", 0)),
        u"Controller Synced: {0} warnings {1}".format(
            phase5_summary.get("controller_synced_count", 0),
            phase5_summary.get("controller_sync_warning_count", 0),
        ),
        u"Target Track Prepare: cleared {0} | unresolved {1} | failed {2}".format(
            phase5_summary.get("target_track_controllers_cleared", 0),
            phase5_summary.get("target_track_prepare_unresolved", 0),
            phase5_summary.get("target_track_prepare_failed", 0),
        ),
        u"Track Validation Failed: {0}".format(phase5_summary.get("track_validation_failed", 0)),
        u"Track Validation Semantic Warnings: objects {0} | tracks {1}".format(
            phase5_summary.get("track_validation_warning_objects", 0),
            phase5_summary.get("semantic_equivalent_track_count", 0),
        ),
        u"Morph Baked: {0} failed {1}".format(
            phase5_summary.get("morph_baked_count", 0),
            phase5_summary.get("morph_failed_count", 0),
        ),
        u"Hard Errors: {0}".format(phase5_summary.get("hard_error_count", 0)),
        u"Bake Used: {0}".format(phase5_summary.get("bake_used", False)),
        u"",
        u"[Allowed Missing Object Merge]",
        u"Merged: {0}".format(merge_summary.get("merged_count", 0)),
        u"Failed: {0}".format(merge_summary.get("failed_count", 0)),
    ]
    if export_blockers:
        lines.append(u"")
        lines.append(u"[Preflight Blockers]")
        for item in export_blockers[:50]:
            lines.append(u"- {0} -> {1}: {2} {3}".format(
                _as_text(item.get("source_name", "")),
                _as_text(item.get("target_name", "")),
                _as_text(item.get("reason", "")),
                _as_text(item.get("message", "")),
            ))
    if export_warnings:
        lines.append(u"")
        lines.append(u"[Preflight Warnings]")
        for item in export_warnings[:50]:
            lines.append(u"- {0} -> {1}: {2} {3}".format(
                _as_text(item.get("source_name", "")),
                _as_text(item.get("target_name", "")),
                _as_text(item.get("reason", "")),
                _as_text(item.get("message", "")),
            ))
    non_bip_step_errors = import_report.get("non_bip_step_errors", []) or []
    if non_bip_step_errors:
        lines.append(u"")
        lines.append(u"[Ignored Non-BIP Step Errors]")
        for item in non_bip_step_errors[:20]:
            lines.append(u"- {0}: {1}".format(_as_text(item.get("step", "")), _as_text(item.get("message", ""))))
    if xaf_fail_samples:
        lines.append(u"")
        lines.append(u"[XAF Failure Samples]")
        for item in xaf_fail_samples:
            lines.append(u"- {0}: {1}".format(_as_text(item.get("source_name", "")), _as_text(item.get("message", ""))))
    if channel_warning_items:
        lines.append(u"")
        lines.append(u"[Channel Key Warning Samples]")
        for item in channel_warning_items[:30]:
            mismatches = item.get("channel_key_mismatches", []) or []
            desc = u", ".join([
                u"{0} old={1} new={2}".format(
                    _as_text(x.get("channel", "")),
                    x.get("source_key_count", 0),
                    x.get("target_key_count", 0),
                )
                for x in mismatches
            ])
            lines.append(u"- {0} -> {1}: {2}".format(
                _as_text(item.get("source_name", "")),
                _as_text(item.get("target_name", "")),
                desc,
            ))
    with io.open(txt_path, "w", encoding="utf-8") as f:
        f.write(u"\n".join(lines))
    return txt_path


def _write_package_reports(report):
    package_dir = _as_text(report.get("package_dir", ""))
    if not package_dir:
        return report
    json_path = os.path.join(package_dir, "migration_report.json")
    txt_path = os.path.join(package_dir, "migration_report.txt")
    with io.open(json_path, "w", encoding="utf-8") as f:
        f.write(_as_text(json.dumps(report, ensure_ascii=False, indent=2)))
    _write_package_text_report(report, txt_path)
    report["report_json"] = json_path
    report["report_txt"] = txt_path
    return report


def _remove_tree(path):
    path = _as_text(path)
    if path and os.path.isdir(path):
        shutil.rmtree(path)


def _remove_empty_package_root(package_dir):
    package_dir = _as_text(package_dir)
    parent = os.path.dirname(package_dir)
    try:
        if parent and os.path.basename(parent) == "_RigUpdatePackages" and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    except Exception:
        pass


def _remove_temp_output(temp_output, old_anim_path):
    temp_output = os.path.abspath(_as_text(temp_output)) if temp_output else u""
    old_anim_path = os.path.abspath(_as_text(old_anim_path)) if old_anim_path else u""
    if temp_output and temp_output != old_anim_path and os.path.exists(temp_output):
        os.remove(temp_output)


def _package_root_for(package_dir):
    package_dir = os.path.abspath(_as_text(package_dir)) if package_dir else u""
    if not package_dir:
        return u""
    package_markers = ("_RigUpdatePackages", "OP_RigUpdatePackages")
    if os.path.basename(package_dir) in package_markers:
        return package_dir
    parent = os.path.dirname(package_dir)
    if os.path.basename(parent) in package_markers:
        return parent
    # 临时目录布局: .../OP_RigUpdatePackages/<session>/<migration>
    grand = os.path.dirname(parent) if parent else u""
    if grand and os.path.basename(grand) in package_markers:
        return parent
    return package_dir


def _remove_rigupdate_max_artifacts(old_anim_path, temp_output):
    import re
    old_anim_path = os.path.abspath(_as_text(old_anim_path)) if old_anim_path else u""
    temp_output = os.path.abspath(_as_text(temp_output)) if temp_output else u""
    folder = os.path.dirname(old_anim_path)
    if not folder or not os.path.isdir(folder):
        return []
    old_stem = os.path.splitext(os.path.basename(old_anim_path))[0]
    base_stem = re.sub(r"(?i)_RigUpdate(?:_v\d{3})?$", "", old_stem)
    removed = []
    for name in os.listdir(folder):
        low = name.lower()
        path = os.path.abspath(os.path.join(folder, name))
        if path == old_anim_path:
            continue
        should_remove = False
        if temp_output and path == temp_output:
            should_remove = True
        elif low.endswith(".max") and low.startswith(base_stem.lower() + "_rigupdate"):
            should_remove = True
        if should_remove and os.path.isfile(path):
            try:
                os.remove(path)
                removed.append(path)
            except Exception:
                pass
    return removed


def _remove_local_max_backup_file(max_path):
    max_path = os.path.abspath(_as_text(max_path)) if max_path else u""
    folder = os.path.dirname(max_path)
    if not folder or not os.path.isdir(folder):
        return []
    stem, ext = os.path.splitext(os.path.basename(max_path))
    if not ext:
        ext = ".max"
    candidates = [
        os.path.join(folder, stem + u"_backup" + ext),
        os.path.join(folder, stem + u"_backup.max"),
    ]
    removed = []
    seen = set()
    for path in candidates:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed.append(path)
            except Exception:
                pass
    return removed


def _cleanup_rigupdate_package_artifacts(report):
    package_dir = _as_text(report.get("package_dir", ""))
    package_root = _package_root_for(package_dir)
    if package_root and os.path.isdir(package_root):
        _remove_tree(package_root)
    elif package_dir and os.path.isdir(package_dir):
        _remove_tree(package_dir)
    return {
        "package_dir": package_dir,
        "package_root": package_root,
    }


def _strict_cleanup_rig_update_artifacts(report, old_anim_path, temp_output):
    package_dir = _as_text(report.get("package_dir", ""))
    package_root = _package_root_for(package_dir)
    removed_max = _remove_rigupdate_max_artifacts(old_anim_path, temp_output)
    package_cleanup = _cleanup_rigupdate_package_artifacts(report)
    return {
        "package_dir": package_cleanup.get("package_dir", package_dir),
        "package_root": package_cleanup.get("package_root", package_root),
        "removed_rigupdate_max_files": removed_max,
    }


def _version_from_rig_path(path):
    import re
    match = re.search(r"(?i)_v(\d{1,3})(?=\.max$)", os.path.basename(_as_text(path)))
    return normalize_version(match.group(1)) if match else u""


def _copy_reports_to_backup(report):
    workflow = report.get("workflow", {}) or {}
    backup_path = _as_text(workflow.get("backup_path", ""))
    report_txt = _as_text(report.get("report_txt", ""))
    report_json = _as_text(report.get("report_json", ""))
    package_paths = ((report.get("package_manifest", {}) or {}).get("paths", {}) or {})
    layer_mapping_json = _as_text(package_paths.get("layer_mapping_json", ""))
    copied = {}
    if not backup_path:
        return copied
    try:
        base = os.path.splitext(backup_path)[0]
        if report_txt and os.path.exists(report_txt):
            txt_dst = base + u"_migration_report.txt"
            shutil.copy2(report_txt, txt_dst)
            copied["report_txt"] = txt_dst
        if report_json and os.path.exists(report_json):
            json_dst = base + u"_migration_report.json"
            shutil.copy2(report_json, json_dst)
            copied["report_json"] = json_dst
        if layer_mapping_json and os.path.exists(layer_mapping_json):
            mapping_dst = base + u"_layer_mapping.json"
            shutil.copy2(layer_mapping_json, mapping_dst)
            copied["layer_mapping_json"] = mapping_dst
    except Exception:
        pass
    return copied


def _phase3_fail(error_code, message, bip_data):
    return {
        "ok": False,
        "error_code": error_code,
        "message": message,
        "bip_phase": bip_data,
        "phase3_local_objects": {
            "enabled": True,
            "status": "failed",
            "errors": [{"error_code": error_code, "message": message}],
        },
        "phase3_existing_object_prepare": {
            "enabled": True,
            "status": "failed",
            "errors": [{"error_code": error_code, "message": message}],
        },
    }


def run_canonical_migration(
    old_anim_path,
    new_rig_path,
    output_max_path=None,
    source_rig_path=None,
    adapter_override_path=None,
    standard_contract_path=None,
    tool_root=None,
    mapping_path=None,
    overwrite=False,
    package_root=None,
    save_on_validation_failure=False,
    allow_layer_fallback=False,
    ignore_duplicate_animation_objects=False,
    ignored_source_contract_ids=None,
    ignored_target_contract_ids=None,
    reviewed_binding_difference_signature=u"",
    progress_callback=None,
):
    """Migrate animation through full BIP plus contract-layer XAF packages.

    The source binding's tracked-layer membership is authoritative. Version-
    pair node maps are deliberately rejected; optional overrides are family-
    level exceptions only. Non-BIP incompatibilities are skipped and reported
    after a successful update instead of being baked or treated as blockers.
    """
    old_anim_path = os.path.abspath(_as_text(old_anim_path)) if old_anim_path else u""
    new_rig_path = os.path.abspath(_as_text(new_rig_path)) if new_rig_path else u""
    output_max_path = os.path.abspath(_as_text(output_max_path or "")) if output_max_path else u""
    package_root = os.path.abspath(_as_text(package_root)) if package_root else None
    source_rig_path = os.path.abspath(_as_text(source_rig_path)) if source_rig_path else None
    if (not old_anim_path) or (not os.path.exists(old_anim_path)):
        return {"ok": False, "error_code": "CANON-INPUT-OLD", "message": u"当前动画文件路径无效"}
    if (not new_rig_path) or (not os.path.exists(new_rig_path)):
        return {"ok": False, "error_code": "CANON-INPUT-RIG", "message": u"新版绑定文件路径无效"}
    if not output_max_path:
        output_max_path = _default_output_for(old_anim_path)
    elif os.path.exists(output_max_path) and not overwrite:
        output_max_path = _next_available_output_path(output_max_path)
    if mapping_path:
        return {
            "ok": False,
            "error_code": "CANON-VERSION-PAIR-MAPPING-DISABLED",
            "message": u"Vxx-Vyy 两两骨骼映射已停用。请清空旧映射，使用源绑定参考和绑定家族适配器。",
            "output_max_path": output_max_path,
        }
    try:
        adapter_override = _load_family_adapter_override(adapter_override_path)
    except Exception as error:
        return {
            "ok": False,
            "error_code": "CANON-FAMILY-OVERRIDE",
            "message": _as_text(error),
            "output_max_path": output_max_path,
        }
    manifest = export_canonical_package(
        old_anim_path=old_anim_path,
        new_rig_path=new_rig_path,
        output_max_path=output_max_path,
        source_rig_path=source_rig_path,
        adapter_override=adapter_override,
        package_root=package_root,
        tool_root=tool_root,
        standard_contract_path=standard_contract_path,
        adapter_contract_path=adapter_override_path,
        allow_layer_fallback=bool(allow_layer_fallback),
        ignore_duplicate_animation_objects=bool(ignore_duplicate_animation_objects),
        ignored_source_contract_ids=ignored_source_contract_ids,
        ignored_target_contract_ids=ignored_target_contract_ids,
        reviewed_binding_difference_signature=reviewed_binding_difference_signature,
        progress_callback=progress_callback,
    )
    if not manifest.get("ok", False):
        return {
            "ok": False,
            "error_code": manifest.get("error_code", "CANON-EXPORT"),
            "message": manifest.get("message", u"标准动画包导出失败"),
            "engine": "layer_contract_xaf",
            "package_manifest": manifest,
            "package_dir": manifest.get("package_dir", ""),
            "report_txt": manifest.get("report_txt", ""),
            "output_max_path": output_max_path,
        }
    result = apply_canonical_package(
        manifest,
        overwrite=bool(overwrite),
        save_on_validation_failure=bool(save_on_validation_failure),
        progress_callback=progress_callback,
    )
    result["package_manifest"] = manifest
    result["package_dir"] = manifest.get("package_dir", "")
    result["report_txt"] = manifest.get("report_txt", "")
    result["report_json"] = os.path.join(manifest.get("package_dir", ""), "canonical_result.json")
    result["phase5_non_bip_animation"] = {
        "enabled": True,
        "engine": "layer_contract_xaf",
        "status": "passed" if result.get("ok") else "failed",
        "warnings": result.get("validation_advisories", []),
        "errors": [],
        "summary": {
            "candidate_count": (
                (manifest.get("summary", {}) or {}).get("xaf_control_count", 0) +
                (manifest.get("summary", {}) or {}).get("skipped_control_count", 0) +
                (manifest.get("summary", {}) or {}).get("user_ignored_control_count", 0)
            ),
            "canonical_applied_count": (result.get("summary", {}) or {}).get("applied_channel_count", 0),
            "skipped_control_count": len(result.get("skipped_controls", []) or []),
            "user_ignored_control_count": len(result.get("user_ignored_controls", []) or []),
            "canonical_validation_failed": 0,
            "canonical_validation_advisory": len(result.get("validation_advisories", []) or []),
        },
    }
    return result


def run_bip_and_local_migration(
    old_anim_path,
    new_rig_path,
    output_max_path=None,
    mapping_path=None,
    overwrite=False,
    strict_ik=True,
    local_rules=None,
    validate_threshold=None,
    validation_mode="warn",
    tool_root=None,
    ignore_non_bip_errors=False,
    package_root=None,
    skip_missing_constraint_targets=False,
    allow_preflight_blockers=False,
):
    old_anim_path = os.path.abspath(_as_text(old_anim_path)) if old_anim_path else u""
    new_rig_path = os.path.abspath(_as_text(new_rig_path)) if new_rig_path else u""
    output_max_path = os.path.abspath(_as_text(output_max_path or "")) if output_max_path else u""
    package_root = os.path.abspath(_as_text(package_root)) if package_root else None

    if (not old_anim_path) or (not os.path.exists(old_anim_path)) or (not new_rig_path) or (not os.path.exists(new_rig_path)):
        return _phase3_fail("P3-INPUT-001", u"输入路径无效", {})
    if not output_max_path:
        output_max_path = _default_output_for(old_anim_path)
    elif os.path.exists(output_max_path) and not overwrite:
        output_max_path = _next_available_output_path(output_max_path)

    try:
        mapping = _load_mapping(mapping_path)
    except Exception:
        mapping = {}

    package_manifest = export_old_migration_package(
        old_anim_path=old_anim_path,
        new_rig_path=new_rig_path,
        output_max_path=output_max_path,
        mapping=mapping,
        package_root=package_root,
        allow_preflight_blockers=bool(allow_preflight_blockers),
    )
    if not package_manifest.get("ok", False):
        report = {
            "ok": False,
            "error_code": package_manifest.get("error_code", "PKG-EXPORT-001"),
            "message": package_manifest.get("message", u"迁移包导出失败"),
            "package_manifest": package_manifest,
            "package_dir": package_manifest.get("package_dir", ""),
            "output_max_path": output_max_path,
        }
        return _write_package_reports(report)

    import_report = apply_package_to_new_rig(
        package_manifest,
        overwrite=overwrite,
        ignore_non_bip_errors=bool(ignore_non_bip_errors),
        skip_missing_constraint_targets=bool(skip_missing_constraint_targets),
    )
    ok = bool(import_report.get("ok", False))
    msg = import_report.get("message", u"") or u"迁移成功。"
    if not ok:
        msg = import_report.get("message", u"迁移未完全成功，请查看迁移包报告")
    elif ignore_non_bip_errors and (import_report.get("non_bip_step_errors", []) or []):
        msg = import_report.get("message", u"迁移成功（仅 BIP）；非 BIP 步骤异常已忽略。")
    elif allow_preflight_blockers and (package_manifest.get("continued_blockers", []) or []):
        msg = u"迁移完成；已按用户选择跳过 {0} 个预检阻断对象，请检查飘带和其他非 BIP 动画。".format(
            len(package_manifest.get("continued_blockers", []) or [])
        )
    elif ((import_report.get("bip_com_height", {}) or {}).get("status") == "bip_com_height_mismatch"):
        msg = u"迁移完成，但 BIP 质心高度校验不一致，请复核。"

    report = {
        "ok": ok,
        "error_code": None if ok else import_report.get("error_code", "PKG-IMPORT-001"),
        "message": msg,
        "package_dir": package_manifest.get("package_dir", ""),
        "package_manifest": package_manifest,
        "import_report": import_report,
        "phase4_constraints": import_report.get("phase4_constraints", {}),
        "phase5_non_bip_animation": import_report.get("phase5_non_bip_animation", {}),
        "bip_ik": import_report.get("bip_ik", {}),
        "merge_helpers": import_report.get("merge_helpers", {}),
        "bip_com_height": import_report.get("bip_com_height", {}),
        "report_txt": "",
        "report_json": "",
        "output_max_path": output_max_path,
    }
    return _write_package_reports(report)


def run_rig_update_workflow(
    old_anim_path,
    new_rig_path,
    mapping_path=None,
    cleanup_packages=False,
    keep_reports=True,
    tool_root=None,
    context=None,
    ignore_non_bip_errors=False,
    skip_missing_constraint_targets=False,
    allow_preflight_blockers=False,
):
    import tempfile
    import time

    old_anim_path = os.path.abspath(_as_text(old_anim_path)) if old_anim_path else u""
    new_rig_path = os.path.abspath(_as_text(new_rig_path)) if new_rig_path else u""
    if (not old_anim_path) or (not os.path.exists(old_anim_path)):
        return _phase3_fail("WF-INPUT-OLD", u"当前动画文件路径无效", {})
    if (not new_rig_path) or (not os.path.exists(new_rig_path)):
        return _phase3_fail("WF-INPUT-RIG", u"新版绑定文件路径无效", {})

    temp_output = _default_output_for(old_anim_path)
    backup_path = u""
    package_root = None
    if cleanup_packages:
        # 勾选清理时，迁移包写到系统临时目录，避免落在动画文件同目录
        package_root = os.path.join(
            tempfile.gettempdir(),
            u"OP_RigUpdatePackages",
            u"{0}_{1}".format(
                os.path.splitext(os.path.basename(old_anim_path))[0],
                time.strftime("%Y%m%d_%H%M%S"),
            ),
        )
    try:
        backup_path = create_backup(old_anim_path)
    except Exception as e:
        return {
            "ok": False,
            "error_code": "WF-BACKUP-001",
            "message": u"备份失败，已停止更新: {0}".format(_as_text(e)),
            "workflow": {"backup_path": backup_path, "overwrote_original": False},
            "output_max_path": temp_output,
        }

    report = run_bip_and_local_migration(
        old_anim_path=old_anim_path,
        new_rig_path=new_rig_path,
        output_max_path=temp_output,
        mapping_path=mapping_path,
        overwrite=False,
        strict_ik=True,
        validation_mode="warn",
        tool_root=tool_root,
        ignore_non_bip_errors=bool(ignore_non_bip_errors),
        package_root=package_root,
        skip_missing_constraint_targets=bool(skip_missing_constraint_targets),
        allow_preflight_blockers=bool(allow_preflight_blockers),
    )
    workflow = {
        "mode": "overwrite_original",
        "backup_path": backup_path,
        "temp_output_path": temp_output,
        "overwrote_original": False,
        "context": context or {},
        "cleanup_packages": bool(cleanup_packages),
        "keep_reports": bool(keep_reports),
        "package_root": package_root or u"",
        "skip_missing_constraint_targets": bool(skip_missing_constraint_targets),
        "allow_preflight_blockers": bool(allow_preflight_blockers),
    }
    report["workflow"] = workflow
    if not report.get("ok", False):
        report["message"] = report.get("message") or u"迁移失败，原文件未覆盖，可从备份恢复。"
        return _write_package_reports(report)

    try:
        shutil.copy2(temp_output, old_anim_path)
        try:
            import pymxs
            with SilentFileDialogs(pymxs.runtime):
                pymxs.runtime.loadMaxFile(old_anim_path, quiet=True, useFileUnits=True)
            target_version = _version_from_rig_path(new_rig_path)
            metadata_ok = write_scene_binding_version(pymxs.runtime, target_version, rig_path=new_rig_path)
            workflow["binding_version"] = target_version
            workflow["binding_version_written"] = bool(metadata_ok)
            if metadata_ok:
                pymxs.runtime.saveMaxFile(old_anim_path, quiet=True)
        except Exception:
            workflow["binding_version_warning"] = u"绑定版本信息写入失败"
        workflow["overwrote_original"] = True
        report["output_max_path"] = old_anim_path
        try:
            removed_rig_backups = _remove_local_max_backup_file(new_rig_path)
            if removed_rig_backups:
                workflow["removed_rig_local_backup_files"] = removed_rig_backups
        except Exception as e:
            workflow["rig_local_backup_cleanup_warning"] = _as_text(e)
        import_report = report.get("import_report", {}) or {}
        if allow_preflight_blockers and ((report.get("package_manifest", {}) or {}).get("continued_blockers", []) or []):
            ignored_count = len(((report.get("package_manifest", {}) or {}).get("continued_blockers", []) or []))
            workflow["ignored_preflight_blocker_count"] = ignored_count
            report["message"] = u"绑定更新完成；已忽略 {0} 个预检阻断对象。飘带等未映射对象保持目标绑定默认状态。".format(ignored_count)
        elif import_report.get("ignore_non_bip_errors"):
            ignored_count = len(import_report.get("non_bip_step_errors", []) or [])
            workflow["ignore_non_bip_errors"] = True
            workflow["ignored_non_bip_step_error_count"] = ignored_count
            if ignored_count:
                report["message"] = u"绑定更新完成（仅 BIP 模式，{0} 个非 BIP 步骤异常已忽略），原文件已备份并覆盖。".format(ignored_count)
            else:
                report["message"] = u"绑定更新完成（仅 BIP 模式），原文件已备份并覆盖。"
        else:
            report["message"] = u"绑定更新完成，原文件已备份并覆盖。"
    except Exception as e:
        report["ok"] = False
        report["error_code"] = "WF-OVERWRITE-001"
        report["message"] = u"迁移成功但覆盖原文件失败: {0}".format(_as_text(e))
        return _write_package_reports(report)

    try:
        removed_rigupdate_files = _remove_rigupdate_max_artifacts(old_anim_path, temp_output)
        workflow["cleaned_rigupdate_max_files"] = removed_rigupdate_files
        workflow["cleaned_temp_output_path"] = temp_output
    except Exception as e:
        workflow["temp_max_cleanup_warning"] = _as_text(e)

    if cleanup_packages:
        report = _write_package_reports(report)
        try:
            if keep_reports:
                copied_reports = _copy_reports_to_backup(report)
                if copied_reports.get("report_txt"):
                    workflow["backup_report_txt"] = copied_reports.get("report_txt")
                    report["report_txt"] = copied_reports.get("report_txt")
                if copied_reports.get("report_json"):
                    workflow["backup_report_json"] = copied_reports.get("report_json")
                    report["report_json"] = copied_reports.get("report_json")
                if copied_reports.get("layer_mapping_json"):
                    workflow["backup_layer_mapping_json"] = copied_reports.get("layer_mapping_json")
                    package_paths = ((report.get("package_manifest", {}) or {}).get("paths", {}) or {})
                    package_paths["layer_mapping_json"] = copied_reports.get("layer_mapping_json")
            cleanup_result = _cleanup_rigupdate_package_artifacts(report)
            workflow["strict_cleanup"] = True
            workflow["cleaned_package_dir"] = cleanup_result.get("package_dir", u"")
            workflow["cleaned_package_root"] = cleanup_result.get("package_root", u"")
            # 顺带清理动画目录下历史残留的 _RigUpdatePackages
            leftover_root = os.path.join(os.path.dirname(old_anim_path), u"_RigUpdatePackages")
            if os.path.isdir(leftover_root):
                _remove_tree(leftover_root)
                workflow["cleaned_leftover_package_root"] = leftover_root
            if not keep_reports:
                report["report_txt"] = u""
                report["report_json"] = u""
        except Exception as e:
            workflow["cleanup_warning"] = _as_text(e)
    else:
        report = _write_package_reports(report)
        copied_reports = _copy_reports_to_backup(report) if keep_reports else {}
        if copied_reports.get("report_txt"):
            workflow["backup_report_txt"] = copied_reports.get("report_txt")
            report["report_txt"] = copied_reports.get("report_txt")
        if copied_reports.get("report_json"):
            workflow["backup_report_json"] = copied_reports.get("report_json")
            report["report_json"] = copied_reports.get("report_json")
        if copied_reports.get("layer_mapping_json"):
            workflow["backup_layer_mapping_json"] = copied_reports.get("layer_mapping_json")
    return report


def _copy_canonical_reports_to_backup(report):
    workflow = report.get("workflow", {}) or {}
    backup_path = _as_text(workflow.get("backup_path", ""))
    if not backup_path:
        return {}
    base = os.path.splitext(backup_path)[0]
    copied = {}
    sources = (
        ("report_txt", _as_text(report.get("report_txt", "")), base + u"_canonical_report.txt"),
        ("report_json", _as_text(report.get("report_json", "")), base + u"_canonical_result.json"),
        ("manifest_json", _as_text((report.get("package_manifest", {}) or {}).get("manifest_path", "")), base + u"_canonical_manifest.json"),
    )
    for key, source, destination in sources:
        try:
            if source and os.path.exists(source):
                shutil.copy2(source, destination)
                copied[key] = destination
        except Exception:
            pass
    return copied


def run_canonical_rig_update_workflow(
    old_anim_path,
    new_rig_path,
    source_rig_path=None,
    adapter_override_path=None,
    standard_contract_path=None,
    mapping_path=None,
    cleanup_packages=False,
    keep_reports=True,
    tool_root=None,
    context=None,
    allow_layer_fallback=False,
    ignore_duplicate_animation_objects=False,
    ignored_source_contract_ids=None,
    ignored_target_contract_ids=None,
    reviewed_binding_difference_signature=u"",
    progress_callback=None,
):
    """Backup and overwrite workflow for full BIP plus layer-grouped XAF."""
    import tempfile
    import time

    old_anim_path = os.path.abspath(_as_text(old_anim_path)) if old_anim_path else u""
    new_rig_path = os.path.abspath(_as_text(new_rig_path)) if new_rig_path else u""
    if (not old_anim_path) or (not os.path.exists(old_anim_path)):
        return {"ok": False, "error_code": "CANON-WF-OLD", "message": u"当前动画文件路径无效"}
    if (not new_rig_path) or (not os.path.exists(new_rig_path)):
        return {"ok": False, "error_code": "CANON-WF-RIG", "message": u"新版绑定文件路径无效"}

    temp_output = _default_output_for(old_anim_path)
    package_root = None
    if cleanup_packages:
        package_root = os.path.join(
            tempfile.gettempdir(),
            u"OP_RigCanonicalPackages",
            u"{0}_{1}".format(os.path.splitext(os.path.basename(old_anim_path))[0], time.strftime("%Y%m%d_%H%M%S")),
        )
    report = run_canonical_migration(
        old_anim_path=old_anim_path,
        new_rig_path=new_rig_path,
        output_max_path=temp_output,
        source_rig_path=source_rig_path,
        adapter_override_path=adapter_override_path,
        standard_contract_path=standard_contract_path,
        tool_root=tool_root,
        mapping_path=mapping_path,
        overwrite=False,
        package_root=package_root,
        allow_layer_fallback=bool(allow_layer_fallback),
        ignore_duplicate_animation_objects=bool(ignore_duplicate_animation_objects),
        ignored_source_contract_ids=ignored_source_contract_ids,
        ignored_target_contract_ids=ignored_target_contract_ids,
        reviewed_binding_difference_signature=reviewed_binding_difference_signature,
        progress_callback=progress_callback,
    )
    workflow = {
        "mode": "canonical_overwrite_original",
        "engine": "layer_contract_xaf",
        "backup_path": u"",
        "temp_output_path": temp_output,
        "overwrote_original": False,
        "context": context or {},
        "cleanup_packages": bool(cleanup_packages),
        "keep_reports": bool(keep_reports),
        "allow_layer_fallback": bool(allow_layer_fallback),
        "ignore_duplicate_animation_objects": bool(ignore_duplicate_animation_objects),
        "ignored_source_contract_ids": list(ignored_source_contract_ids or []),
        "ignored_target_contract_ids": list(ignored_target_contract_ids or []),
        "reviewed_binding_difference_signature": _as_text(reviewed_binding_difference_signature),
    }
    report["workflow"] = workflow
    if not report.get("ok", False):
        report["message"] = report.get("message") or u"标准动画迁移失败，原文件未覆盖。"
        return report

    # The migration writes only to a temporary output. Back up the original
    # after the full BIP/camera hard steps and temporary save succeed.
    try:
        if progress_callback is not None:
            progress_callback(97, u"备份原动画并覆盖")
        backup_path = create_backup(old_anim_path)
        workflow["backup_path"] = backup_path
    except Exception as error:
        report["ok"] = False
        report["error_code"] = "CANON-WF-BACKUP"
        report["message"] = u"迁移结果已通过，但覆盖前备份失败，已停止更新: {0}".format(_as_text(error))
        return report

    try:
        shutil.copy2(temp_output, old_anim_path)
        try:
            import pymxs
            with SilentFileDialogs(pymxs.runtime):
                pymxs.runtime.loadMaxFile(old_anim_path, quiet=True, useFileUnits=True)
            if progress_callback is not None:
                progress_callback(99, u"写入绑定版本并保存最终文件")
            target_version = _version_from_rig_path(new_rig_path)
            metadata_ok = write_scene_binding_version(pymxs.runtime, target_version, rig_path=new_rig_path)
            workflow["binding_version"] = target_version
            workflow["binding_version_written"] = bool(metadata_ok)
            if metadata_ok:
                pymxs.runtime.saveMaxFile(old_anim_path, quiet=True)
        except Exception:
            workflow["binding_version_warning"] = u"绑定版本信息写入失败"
        workflow["overwrote_original"] = True
        report["output_max_path"] = old_anim_path
        skipped_count = len(report.get("skipped_controls", []) or [])
        report["message"] = u"绑定更新完成，原文件已备份并覆盖；{0} 个不兼容的非 BIP 控制器已跳过并写入报告。".format(skipped_count)
        try:
            result_json = _as_text(report.get("report_json", ""))
            if result_json:
                _json_write(result_json, report)
            _write_canonical_report(
                _as_text(report.get("report_txt", "")),
                report.get("package_manifest", {}) or {},
                result=report,
            )
        except Exception:
            workflow["final_report_write_warning"] = u"最终阶段报告写入失败"
    except Exception as error:
        report["ok"] = False
        report["error_code"] = "CANON-WF-OVERWRITE"
        report["message"] = u"迁移成功但覆盖原文件失败: {0}".format(_as_text(error))
        return report

    if keep_reports:
        copied = _copy_canonical_reports_to_backup(report)
        workflow["backup_reports"] = copied
        if copied.get("report_txt"):
            report["report_txt"] = copied["report_txt"]
        if copied.get("report_json"):
            report["report_json"] = copied["report_json"]
    if temp_output != old_anim_path and os.path.exists(temp_output):
        try:
            os.remove(temp_output)
            workflow["cleaned_temp_output_path"] = temp_output
        except Exception as error:
            workflow["temp_output_cleanup_warning"] = _as_text(error)
    if cleanup_packages:
        package_dir = _as_text(report.get("package_dir", ""))
        try:
            if package_dir and os.path.isdir(package_dir):
                _remove_tree(package_dir)
                workflow["cleaned_package_dir"] = package_dir
        except Exception as error:
            workflow["cleanup_warning"] = _as_text(error)
    if progress_callback is not None:
        progress_callback(100, u"绑定更新完成")
    return report

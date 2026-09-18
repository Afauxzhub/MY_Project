# -*- coding: utf-8 -*-
from __future__ import print_function


def base_report():
    return {
        "session_id": "",
        "timestamp": "",
        "tool_version": "rm_anim_migration_phase1_v0.1",
        "input": {
            "old_anim_path": "",
            "new_rig_path": "",
            "mapping_path": None,
        },
        "summary": {
            "pass_block": False,
            "status_light": "green",
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
        },
        "bip_check": {"issues": []},
        "ik_check": {"issues": []},
        "controller_diff": {"issues": []},
        "constraint_diff": {"issues": []},
        "local_object_diff": {"issues": []},
        "phase3_local_objects": {
            "enabled": False,
            "status": "skipped",
            "summary": {},
            "categories": {},
            "plan_items": [],
            "apply_results": [],
            "validation": {},
            "errors": [],
            "warnings": [],
        },
        "phase3_existing_object_prepare": {
            "enabled": False,
            "status": "skipped",
            "summary": {},
            "matched_items": [],
            "skipped_missing_object": [],
            "skipped": [],
        },
        "phase4_constraints": {
            "enabled": False,
            "status": "skipped",
            "summary": {},
            "items": [],
            "errors": [],
            "warnings": [],
        },
        "phase5_non_bip_animation": {
            "enabled": False,
            "status": "skipped",
            "summary": {},
            "xaf_results": [],
            "trs_fallback_results": [],
            "validation": {},
            "errors": [],
            "warnings": [],
        },
        "morph_diff": {"issues": []},
        "high_risk_items": [],
        "scan_errors": [],
        "next_actions": [],
    }

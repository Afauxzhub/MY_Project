# -*- coding: utf-8 -*-
from __future__ import print_function


def build_phase3_local_objects_report(old_snapshot, plan, apply_result, validate_result, validation_mode):
    old_snapshot = old_snapshot or {}
    plan = plan or {}
    apply_result = apply_result or {}
    validate_result = validate_result or {}

    apply_rows = apply_result.get("results", [])
    failed_rows = [x for x in apply_rows if not x.get("ok", False)]
    exceeded_rows = validate_result.get("exceeded_items", [])

    status = "passed"
    if failed_rows:
        status = "failed"
    elif exceeded_rows:
        status = "blocked" if validation_mode == "block" else "warning"

    category_counter = {}
    for item in plan.get("items", []):
        key = item.get("kind", "Helper")
        category_counter[key] = category_counter.get(key, 0) + 1

    return {
        "enabled": True,
        "status": status,
        "summary": {
            "scanned_count_old": len(old_snapshot.get("objects", [])),
            "candidate_count": len(old_snapshot.get("objects", [])),
            "planned_count": len(plan.get("items", [])),
            "migrated_count": len([x for x in apply_rows if x.get("ok", False)]),
            "skipped_count": int((plan.get("summary") or {}).get("skipped_count", 0)),
            "failed_count": len(failed_rows),
            "validation_warning_count": len(exceeded_rows) if validation_mode != "block" else 0,
            "validation_block_count": len(exceeded_rows) if validation_mode == "block" else 0,
        },
        "categories": category_counter,
        "plan_items": plan.get("items", []),
        "apply_results": apply_rows,
        "validation": validate_result,
        "errors": failed_rows,
        "warnings": exceeded_rows,
    }


def build_phase3_existing_object_prepare_report(old_snapshot, new_snapshot, plan):
    old_snapshot = old_snapshot or {}
    new_snapshot = new_snapshot or {}
    plan = plan or {}
    skipped = plan.get("skipped", []) or []
    items = plan.get("items", []) or []
    mapping_used = [x for x in items if x.get("source_name") != x.get("target_name")]
    same_name_used = [x for x in items if x.get("source_name") == x.get("target_name")]
    return {
        "enabled": True,
        "status": "passed",
        "summary": {
            "old_object_count": len(old_snapshot.get("objects", []) or []),
            "new_object_count": len(new_snapshot.get("objects", []) or []),
            "matched": len(items),
            "mapping_used": len(mapping_used),
            "same_name_used": len(same_name_used),
            "skipped_missing_object": len([x for x in skipped if x.get("reason") == "skipped_missing_object"]),
        },
        "matched_items": items,
        "skipped_missing_object": [x for x in skipped if x.get("reason") == "skipped_missing_object"],
        "skipped": skipped,
    }

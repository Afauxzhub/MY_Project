# -*- coding: utf-8 -*-
from __future__ import print_function

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


def build_local_transfer_plan(old_local_snapshot, new_scene_snapshot, mapping=None):
    mapping = mapping or {}
    old_rows = (old_local_snapshot or {}).get("objects", [])
    new_rows = (new_scene_snapshot or {}).get("objects", [])
    new_names = set([_as_text(x.get("name", "")) for x in new_rows if x.get("name")])

    items = []
    skipped = []
    for row in old_rows:
        source_name = _as_text(row.get("name", ""))
        if not source_name:
            continue
        target_name = _as_text(mapping.get(source_name, source_name))
        parent_name = _as_text(row.get("parent_name", "")) or None
        if parent_name:
            parent_name = _as_text(mapping.get(parent_name, parent_name)) or None
        if target_name not in new_names:
            skipped.append(
                {
                    "source_name": source_name,
                    "target_name": target_name,
                    "reason": "skipped_missing_object",
                    "message": u"新文件中不存在匹配对象，按规则跳过且不创建对象",
                    "kind": _as_text(row.get("kind", "Helper")),
                    "class_name": _as_text(row.get("class_name", "")),
                    "key_times": [int(x) for x in row.get("key_times", [])],
                    "has_animation": bool(row.get("key_times", [])),
                }
            )
            continue
        items.append(
            {
                "source_name": source_name,
                "target_name": target_name,
                "target_exists": target_name in new_names,
                "action": "update_existing",
                "parent_name": parent_name,
                "kind": _as_text(row.get("kind", "Helper")),
                "class_name": _as_text(row.get("class_name", "")),
                "key_times": [int(x) for x in row.get("key_times", [])],
                "has_animation": bool(row.get("key_times", [])),
                "copy_trs": True,
                "copy_visibility": True,
            }
        )

    return {
        "ok": True,
        "error_code": None,
        "message": u"",
        "source_scene_path": _as_text((old_local_snapshot or {}).get("scene_path", "")),
        "target_scene_path": _as_text((new_scene_snapshot or {}).get("scene_path", "")),
        "items": items,
        "summary": {
            "scanned_count_old": len(old_rows),
            "scanned_count_new": len(new_rows),
            "planned_count": len(items),
            "skipped_count": len(skipped),
        },
        "skipped": skipped,
    }

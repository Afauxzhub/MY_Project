# -*- coding: utf-8 -*-
from __future__ import print_function


IK_HINTS = ("ik", "knee", "elbow", "ankle", "wrist")


def scan_ik_objects(rt):
    rows = []
    for node in list(rt.objects):
        try:
            name = str(node.name)
            low = name.lower()
        except Exception:
            continue
        if not any(h in low for h in IK_HINTS):
            continue
        parent_name = None
        try:
            if node.parent:
                parent_name = str(node.parent.name)
        except Exception:
            parent_name = None
        rows.append({"name": name, "parent": parent_name})
    return {"objects": sorted(rows, key=lambda x: x["name"].lower())}

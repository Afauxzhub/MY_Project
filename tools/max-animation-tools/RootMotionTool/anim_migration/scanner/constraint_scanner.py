# -*- coding: utf-8 -*-
from __future__ import print_function


CONSTRAINT_TOKENS = ("constraint", "lookat", "orientation", "position", "path")


def scan_constraints(rt):
    rows = []
    for node in list(rt.objects):
        try:
            owner_name = str(node.name)
            ctrl = node.controller
            ctrl_type = str(rt.classOf(ctrl))
        except Exception:
            continue
        low = ctrl_type.lower()
        if not any(t in low for t in CONSTRAINT_TOKENS):
            continue
        rows.append(
            {
                "owner": owner_name,
                "constraint_type": ctrl_type,
                "targets": [],
                "target_weight_keys_available": False,
            }
        )
    return {"constraints": sorted(rows, key=lambda x: x["owner"].lower())}

# -*- coding: utf-8 -*-
from __future__ import print_function


def _safe_class_name(rt, obj):
    try:
        return str(rt.classOf(obj))
    except Exception:
        return None


def scan_controllers(rt):
    rows = []
    for node in list(rt.objects):
        try:
            name = str(node.name)
        except Exception:
            continue
        try:
            ctrl = node.controller
        except Exception:
            ctrl = None
        rows.append(
            {
                "name": name,
                "controller_type": _safe_class_name(rt, ctrl),
                "position_controller_type": _safe_class_name(rt, getattr(node, "position", None)),
                "rotation_controller_type": _safe_class_name(rt, getattr(node, "rotation", None)),
            }
        )
    return {"controllers": sorted(rows, key=lambda x: x["name"].lower())}

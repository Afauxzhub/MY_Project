# -*- coding: utf-8 -*-
from __future__ import print_function


LOCAL_HINTS = ("dummy", "point", "helper", "locator", "weapon", "prop")


def scan_local_objects(rt):
    rows = []
    for node in list(rt.objects):
        try:
            name = str(node.name)
            cls = str(rt.classOf(node))
        except Exception:
            continue
        token = (name + "|" + cls).lower()
        if any(k in token for k in LOCAL_HINTS):
            rows.append({"name": name, "type": cls})
    return {"objects": sorted(rows, key=lambda x: x["name"].lower())}

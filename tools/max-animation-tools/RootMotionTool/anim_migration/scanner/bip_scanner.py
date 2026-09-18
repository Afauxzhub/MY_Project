# -*- coding: utf-8 -*-
from __future__ import print_function


def scan_bip(rt):
    result = {
        "root_name": None,
        "bip_nodes": [],
        "has_biped": False,
        "structure_signature": [],
    }
    for node in list(rt.objects):
        try:
            name = str(node.name)
        except Exception:
            continue
        low = name.lower()
        if low.startswith("bip") or low.startswith("bip001"):
            result["bip_nodes"].append(name)
            if result["root_name"] is None and (" " not in low or low == "bip001"):
                result["root_name"] = name
    result["bip_nodes"] = sorted(list(set(result["bip_nodes"])))
    result["has_biped"] = len(result["bip_nodes"]) > 0
    result["structure_signature"] = result["bip_nodes"][:20]
    return result

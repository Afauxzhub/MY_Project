# -*- coding: utf-8 -*-
from __future__ import print_function


def scan_morph(rt):
    # Max 侧 Morph 通道读取在不同插件版本差异较大；Phase 1 保守采集可见命名信息。
    channels = []
    for node in list(rt.objects):
        try:
            name = str(node.name)
        except Exception:
            continue
        if "morph" in name.lower() or "face" in name.lower():
            channels.append(name)
    return {"channels": sorted(list(set(channels)))}

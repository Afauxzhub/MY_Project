# -*- coding: utf-8 -*-
from __future__ import print_function
import math


def _dist3(a, b):
    return math.sqrt(
        (float(a[0]) - float(b[0])) ** 2 +
        (float(a[1]) - float(b[1])) ** 2 +
        (float(a[2]) - float(b[2])) ** 2
    )


def _quat_dot(a, b):
    return (
        float(a[0]) * float(b[0]) +
        float(a[1]) * float(b[1]) +
        float(a[2]) * float(b[2]) +
        float(a[3]) * float(b[3])
    )


def _quat_angle_deg(a, b):
    dot = max(-1.0, min(1.0, abs(_quat_dot(a, b))))
    return math.degrees(2.0 * math.acos(dot))


def _default_threshold():
    return {
        "position": 0.01,
        "rotation_deg": 0.5,
        "scale": 0.01,
        "visibility": 0.001,
    }


def validate_local_object_transforms(pre_data, post_data, threshold):
    t = _default_threshold()
    if isinstance(threshold, dict):
        t.update(threshold)

    exceeded = []
    sample_count = 0
    max_pos = 0.0
    max_rot = 0.0
    max_scale = 0.0
    max_vis = 0.0

    pre_data = pre_data or {}
    post_data = post_data or {}
    for source_name, pre_row in pre_data.items():
        post_row = post_data.get(source_name) or post_data.get(source_name.replace("|src", "")) or {}
        pre_samples = pre_row.get("samples", {})
        post_samples = post_row.get("samples", {})
        for frame, pre_sample in pre_samples.items():
            frame_key = int(frame)
            post_sample = post_samples.get(frame_key) or post_samples.get(str(frame_key))
            if not post_sample:
                continue
            sample_count += 1
            p_d = _dist3(pre_sample.get("position", [0, 0, 0]), post_sample.get("position", [0, 0, 0]))
            r_d = _quat_angle_deg(pre_sample.get("rotation", [0, 0, 0, 1]), post_sample.get("rotation", [0, 0, 0, 1]))
            s_d = _dist3(pre_sample.get("scale", [1, 1, 1]), post_sample.get("scale", [1, 1, 1]))
            v_d = abs(float(pre_sample.get("visibility", 1.0)) - float(post_sample.get("visibility", 1.0)))

            max_pos = max(max_pos, p_d)
            max_rot = max(max_rot, r_d)
            max_scale = max(max_scale, s_d)
            max_vis = max(max_vis, v_d)

            if p_d > t["position"] or r_d > t["rotation_deg"] or s_d > t["scale"] or v_d > t["visibility"]:
                exceeded.append(
                    {
                        "object_name": source_name,
                        "frame": frame_key,
                        "position_delta": p_d,
                        "rotation_delta_deg": r_d,
                        "scale_delta": s_d,
                        "visibility_delta": v_d,
                    }
                )

    return {
        "ok": len(exceeded) == 0,
        "summary": {
            "sample_count": sample_count,
            "exceeded_count": len(exceeded),
            "max_position_delta": max_pos,
            "max_rotation_delta_deg": max_rot,
            "max_scale_delta": max_scale,
            "max_visibility_delta": max_vis,
        },
        "threshold": t,
        "exceeded_items": exceeded,
    }

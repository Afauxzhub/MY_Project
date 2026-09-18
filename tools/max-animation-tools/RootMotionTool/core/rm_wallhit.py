# -*- coding: utf-8 -*-
"""WallHit 专用根运动的命名与分段校验（不依赖 pymxs，可独立测试）。"""
from __future__ import print_function

import os


WALLHIT_REQUIRED_SEGMENTS = (
    u"rise_start",
    u"rise_end",
    u"fall_start",
    u"land_start",
    u"land_loop",
    u"land_end",
    u"wallhit_loop",
    u"fall_loop",
    u"rise_loop",
)

WALLHIT_SEGMENT_LABELS = {
    u"rise_start": u"Rise_Start",
    u"rise_end": u"Rise_End",
    u"fall_start": u"Fall_Start",
    u"land_start": u"Land_Start",
    u"land_loop": u"Land_Loop",
    u"land_end": u"Land_End",
    u"wallhit_loop": u"Loop",
    u"fall_loop": u"Fall_Loop",
    u"rise_loop": u"Rise_Loop",
}


def _text(value):
    if value is None:
        return u""
    try:
        return unicode(value)
    except NameError:
        return str(value)


def is_wallhit_filename(filename):
    """文件名（不含路径也可）只要包含 `_WallHit` 即进入专用分支。"""
    stem = os.path.splitext(os.path.basename(_text(filename)))[0]
    return u"_wallhit" in stem.lower()


def normalize_wallhit_segment_name(name):
    """把拆分后缀或完整片段名归一成后端使用的稳定 key。"""
    value = _text(name).strip().lstrip(u"_").lower()
    if not value:
        return None

    # 先匹配更具体的 Loop，避免被最后的通用 Loop 吞掉。
    suffix_map = (
        (u"fall_loop", u"fall_loop"),
        (u"rise_loop", u"rise_loop"),
        (u"land_loop", u"land_loop"),
        (u"rise_start", u"rise_start"),
        (u"rise_end", u"rise_end"),
        (u"fall_start", u"fall_start"),
        (u"land_start", u"land_start"),
        (u"land_end", u"land_end"),
        (u"wallhit_loop", u"wallhit_loop"),
    )
    for suffix, key in suffix_map:
        if value == suffix or value.endswith(u"_" + suffix):
            return key
    if value == u"loop":
        return u"wallhit_loop"
    return None


def _segment_parts(item):
    if isinstance(item, dict):
        name = item.get(u"export_suffix", item.get(u"label", item.get(u"name", u"")))
        start_f = item.get(u"start", item.get(u"start_f"))
        end_f = item.get(u"end", item.get(u"end_f"))
        return name, start_f, end_f
    if len(item) >= 5:
        _label, name, start_f, end_f, _joiner = item[:5]
        return name, start_f, end_f
    name, start_f, end_f = item[:3]
    return name, start_f, end_f


def collect_wallhit_segments(split_data, scene_start=None, scene_end=None):
    """
    返回 ({canonical_key: (start, end)}, [中文错误...])。

    不依赖片段在 UI 列表里的顺序；导出后缀决定每段采用哪条规则。
    """
    segments = {}
    errors = []

    for item in split_data or []:
        try:
            name, start_f, end_f = _segment_parts(item)
            key = normalize_wallhit_segment_name(name)
            if key is None:
                continue
            start_f = int(start_f)
            end_f = int(end_f)
        except Exception:
            errors.append(u"存在无法读取的动画拆分项")
            continue

        if start_f >= end_f:
            errors.append(
                u"{0} 的开始帧必须小于结束帧".format(
                    WALLHIT_SEGMENT_LABELS.get(key, key)
                )
            )
            continue
        if key in segments:
            errors.append(
                u"{0} 出现了重复片段".format(WALLHIT_SEGMENT_LABELS.get(key, key))
            )
            continue
        if scene_start is not None and start_f < int(scene_start):
            errors.append(
                u"{0} 的开始帧超出场景范围".format(
                    WALLHIT_SEGMENT_LABELS.get(key, key)
                )
            )
        if scene_end is not None and end_f > int(scene_end):
            errors.append(
                u"{0} 的结束帧超出场景范围".format(
                    WALLHIT_SEGMENT_LABELS.get(key, key)
                )
            )
        segments[key] = (start_f, end_f)

    missing = [key for key in WALLHIT_REQUIRED_SEGMENTS if key not in segments]
    if missing:
        errors.append(
            u"缺少片段: {0}".format(
                u", ".join([WALLHIT_SEGMENT_LABELS[key] for key in missing])
            )
        )

    range_owners = {}
    for key in WALLHIT_REQUIRED_SEGMENTS:
        if key not in segments:
            continue
        frame_range = segments[key]
        previous_key = range_owners.get(frame_range)
        if previous_key is not None:
            errors.append(
                u"{0} 与 {1} 使用了相同帧范围 {2}-{3}，请修正后再发布".format(
                    WALLHIT_SEGMENT_LABELS.get(previous_key, previous_key),
                    WALLHIT_SEGMENT_LABELS.get(key, key),
                    frame_range[0],
                    frame_range[1],
                )
            )
        else:
            range_owners[frame_range] = key

    if u"fall_start" in segments:
        fall_start, fall_end = segments[u"fall_start"]
        if fall_end - fall_start < 1:
            errors.append(u"Fall_Start 至少需要两帧，才能读取末段下落速度")

    return segments, errors


def ordered_wallhit_segments(segments):
    """按稳定顺序返回 [(key, start, end), ...]，供 pymxs 转 MaxScript Array。"""
    result = []
    for key in WALLHIT_REQUIRED_SEGMENTS:
        if key in segments:
            start_f, end_f = segments[key]
            result.append((key, int(start_f), int(end_f)))
    return result

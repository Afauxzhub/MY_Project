# -*- coding: utf-8 -*-
"""读取每个 MAX 旁车中的公盘发布历史。"""
from __future__ import division
import datetime
import io
import json
import os

from core.publish_metadata import (
    settings_path_for_max,
    format_stage_label,
    read_publish_metadata,
)

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
        return _text_type(repr(value))


def _load_settings(max_path):
    path = settings_path_for_max(max_path)
    if not path or not os.path.isfile(path):
        return {}
    try:
        with io.open(path, u"r", encoding=u"utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _revision(value):
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def load_publish_history(max_path):
    """返回按新到旧排序的历史记录，并解析当前可打开的文件路径。"""
    max_path = _as_text(max_path)
    data = _load_settings(max_path)
    current_meta = data.get(u"publish_metadata", {}) or {}
    current_revision = _revision(current_meta.get(u"publish_revision", 0))
    rows = []
    for raw in data.get(u"publish_history", []) or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        revision = _revision(item.get(u"publish_revision", 0))
        label = _as_text(item.get(u"publish_revision_label", u""))
        if not label:
            label = u"V{0:03d}".format(revision) if revision > 0 else u"旧版"
        stage = _as_text(item.get(u"stage", u""))
        stage_version = _as_text(item.get(u"stage_version", u""))
        backup_path = _as_text(item.get(u"backup_path", u""))
        public_path = _as_text(item.get(u"public_path", u""))
        open_path = u""
        if backup_path and os.path.isfile(backup_path):
            open_path = backup_path
        elif public_path and os.path.isfile(public_path):
            open_path = public_path
        elif revision > 0 and revision == current_revision and os.path.isfile(max_path):
            open_path = max_path
        rows.append({
            u"publish_revision": revision,
            u"publish_revision_label": label,
            u"published_at": _as_text(item.get(u"published_at", u"")),
            u"publisher": _as_text(item.get(u"publisher", u"")) or u"未设置",
            u"stage": stage,
            u"stage_version": stage_version,
            u"stage_label": format_stage_label(stage, stage_version),
            u"public_path": public_path,
            u"backup_path": backup_path,
            u"open_path": open_path,
            u"available": bool(open_path),
        })
    if not any([row[u"publish_revision"] > 0 for row in rows]) and os.path.isfile(max_path):
        metadata = read_publish_metadata(max_path)
        published_at = _as_text(metadata.get(u"published_at", u""))
        if not published_at:
            try:
                published_at = datetime.datetime.fromtimestamp(
                    os.path.getmtime(max_path)
                ).strftime(u"%Y-%m-%dT%H:%M:%S")
            except Exception:
                published_at = u""
        rows.append({
            u"publish_revision": 1,
            u"publish_revision_label": u"V001",
            u"published_at": published_at,
            u"publisher": metadata.get(u"publisher", u"未设置"),
            u"stage": metadata.get(u"stage", u""),
            u"stage_version": metadata.get(u"stage_version", u""),
            u"stage_label": metadata.get(u"version_label", u"未标记版本"),
            u"public_path": max_path,
            u"backup_path": u"",
            u"open_path": max_path,
            u"available": True,
            u"implicit_legacy": True,
        })
    rows.sort(key=lambda x: (
        _as_text(x.get(u"published_at")),
        _revision(x.get(u"publish_revision", 0)),
    ), reverse=True)
    return rows

# -*- coding: utf-8 -*-
"""读取发布设置旁车中的展示元数据，并兼容旧文件。"""
from __future__ import division
import datetime
import io
import json
import os

from core.paths import PUBLISH_SETTINGS_FOLDER, STAGE_FOLDERS

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


def settings_path_for_max(max_path):
    max_path = _as_text(max_path)
    stem = os.path.splitext(os.path.basename(max_path))[0]
    if not max_path or not stem:
        return u""
    return os.path.join(
        os.path.dirname(max_path), PUBLISH_SETTINGS_FOLDER, stem + u".json"
    )


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


def _path_stage(max_path, char_root=None):
    path = _as_text(max_path)
    if char_root:
        try:
            path = os.path.relpath(path, _as_text(char_root))
        except Exception:
            pass
    parts = [p for p in path.replace(u"\\", u"/").split(u"/") if p]
    for index, part in enumerate(parts):
        if part not in STAGE_FOLDERS:
            continue
        version = u""
        if part == u"监修" and index + 1 < len(parts) - 1:
            version = _as_text(parts[index + 1]).strip()
        return part, version
    return u"", u""


def _parse_published_at(value):
    text = _as_text(value).strip()
    if not text:
        return None
    normalized = text.replace(u"Z", u"").replace(u"/", u"-")
    for fmt in (u"%Y-%m-%dT%H:%M:%S", u"%Y-%m-%d %H:%M:%S", u"%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(normalized[:19], fmt)
        except Exception:
            pass
    return None


def _mtime_datetime(max_path):
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(max_path))
    except Exception:
        return None


def format_stage_label(stage, stage_version=u""):
    stage = _as_text(stage).strip()
    version = _as_text(stage_version).strip()
    if stage == u"监修" and version:
        return stage + version
    return stage or u"未标记版本"


def read_publish_metadata(max_path, char_root=None):
    """返回负责人、发布日期、发布版本以及完整文件展示名。"""
    max_path = _as_text(max_path)
    data = _load_settings(max_path)
    stored = data.get(u"publish_metadata", {}) or {}
    if not isinstance(stored, dict):
        stored = {}

    path_stage, path_version = _path_stage(max_path, char_root)
    stage = _as_text(stored.get(u"stage", u"")).strip() or path_stage
    stage_version = (
        _as_text(stored.get(u"stage_version", u"")).strip() or path_version
    )
    publisher = _as_text(stored.get(u"publisher", u"")).strip() or u"未设置"

    published_dt = _parse_published_at(stored.get(u"published_at", u""))
    if published_dt is None:
        published_dt = _mtime_datetime(max_path)
    date_label = (
        published_dt.strftime(u"%y.%m.%d")
        if published_dt is not None
        else u"日期未知"
    )
    published_sort = (
        float((published_dt - datetime.datetime(1970, 1, 1)).total_seconds())
        if published_dt is not None
        else 0.0
    )
    version_label = format_stage_label(stage, stage_version)
    publish_revision = 0
    try:
        publish_revision = max(0, int(stored.get(u"publish_revision", 0) or 0))
    except Exception:
        publish_revision = 0
    implicit_publish_revision = publish_revision <= 0
    if implicit_publish_revision:
        publish_revision = 1
    revision_label = _as_text(
        stored.get(u"publish_revision_label", u"")
    ).strip()
    if implicit_publish_revision or not revision_label:
        revision_label = u"V{0:03d}".format(publish_revision)
    stem = os.path.splitext(os.path.basename(max_path))[0]
    display_name = u"{0}[{1}][{2}][{3}]".format(
        stem, date_label, publisher, version_label
    )
    if revision_label:
        display_name += u"[{0}]".format(revision_label)
    return {
        u"publisher": publisher,
        u"published_at": _as_text(stored.get(u"published_at", u"")),
        u"published_sort": published_sort,
        u"date_label": date_label,
        u"stage": stage,
        u"stage_version": stage_version,
        u"version_label": version_label,
        u"publish_revision": publish_revision,
        u"publish_revision_label": revision_label,
        u"implicit_publish_revision": implicit_publish_revision,
        u"display_name": display_name,
    }

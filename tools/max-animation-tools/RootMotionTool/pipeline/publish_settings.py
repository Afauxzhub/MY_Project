# -*- coding: utf-8 -*-
"""
每个动画文件的发布设置持久化。

规则：
  - 设置文件与 .max 文件同目录下的「发布设置」子文件夹内
  - 文件名与 max 文件名关联：Role_Generic_Idle.max → 发布设置/Role_Generic_Idle.json
  - 永远只有一份，保存时直接覆盖
  - 缺失/损坏时静默返回 None，调用方使用默认设置
"""
from __future__ import division
import datetime
import io
import json
import os

PUBLISH_SETTINGS_FOLDER = u"发布设置"
SETTINGS_VERSION = 3

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
    """max 文件对应的发布设置 json 路径（不检查存在性）。"""
    max_path = _as_text(max_path)
    if not max_path:
        return u""
    folder = os.path.dirname(max_path)
    stem = os.path.splitext(os.path.basename(max_path))[0]
    if not stem:
        return u""
    return os.path.join(folder, PUBLISH_SETTINGS_FOLDER, stem + u".json")


def load_publish_settings(max_path):
    """读取发布设置。不存在或解析失败返回 None（静默）。"""
    path = settings_path_for_max(max_path)
    if not path or not os.path.isfile(path):
        return None
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def merge_publish_settings_data(max_path, data):
    """用新的面板选项更新设置，同时保留已有发布元数据和历史。"""
    payload = dict(load_publish_settings(max_path) or {})
    payload.update(dict(data or {}))
    return payload


def attach_publish_metadata(
    data,
    publisher,
    stage,
    stage_version=u"",
    published_at=None,
    publish_revision=0,
    public_path=u"",
):
    """返回带本次成功发布信息的设置副本。"""
    payload = dict(data or {})
    stage = _as_text(stage).strip() or u"初版"
    version = _as_text(stage_version).strip() if stage == u"监修" else u""
    timestamp = _as_text(published_at).strip()
    if not timestamp:
        timestamp = datetime.datetime.now().strftime(u"%Y-%m-%dT%H:%M:%S")
    payload[u"publish_metadata"] = {
        u"publisher": _as_text(publisher).strip(),
        u"published_at": timestamp,
        u"stage": stage,
        u"stage_version": version,
        u"publish_revision": int(publish_revision or 0),
        u"publish_revision_label": (
            u"V{0:03d}".format(int(publish_revision))
            if int(publish_revision or 0) > 0 else u""
        ),
        u"public_path": _as_text(public_path),
    }
    return payload


def save_publish_settings(max_path, data):
    """写入发布设置，直接覆盖。返回 (ok, settings_path_or_error)。"""
    path = settings_path_for_max(max_path)
    if not path:
        return False, u"无效的 max 路径"
    payload = dict(data or {})
    payload[u"version"] = SETTINGS_VERSION
    payload[u"max_file"] = os.path.basename(_as_text(max_path))
    try:
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        with io.open(path, u"w", encoding=u"utf-8") as f:
            f.write(_as_text(text))
        return True, path
    except Exception as e:
        return False, _as_text(e)


def copy_settings_alongside(src_max_path, dest_max_path):
    """
    将 src max 的发布设置文件复制到 dest max 对应位置。
    无设置文件时静默跳过。返回 (copied, message)。
    """
    import shutil

    src_json = settings_path_for_max(src_max_path)
    if not src_json or not os.path.isfile(src_json):
        return False, u""
    dest_json = settings_path_for_max(dest_max_path)
    if not dest_json:
        return False, u""
    try:
        folder = os.path.dirname(dest_json)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        shutil.copy2(src_json, dest_json)
        return True, dest_json
    except Exception as e:
        return False, _as_text(e)

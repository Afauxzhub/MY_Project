# -*- coding: utf-8 -*-
"""公盘与本地路径常量。"""
from __future__ import division
import os
import re

NAS_BASE = os.environ.get("ANIMATION_TOOLS_PUBLIC_ROOT", u"")
NAS_INDOOR_FOLDER = u"局内战斗备份"
NAS_OUTDOOR_FOLDER = u"局外演出备份"

STAGE_FOLDERS = (u"初版", u"终版", u"监修")

MAX_EXT = u".max"

# 每个动画文件的发布设置所在子文件夹（与发布工具约定一致）
PUBLISH_SETTINGS_FOLDER = u"发布设置"
PUBLISH_BACKUP_FOLDER = u"发布备份"
RIG_UPDATE_BACKUP_FOLDER = u"_RigUpdateBackup"

# 备份文件命名：*_YYYYMMDD_HHMMSS.max
_TIMESTAMP_MAX_SUFFIX_RE = re.compile(r"_\d{8}_\d{6}\.max$", re.IGNORECASE)

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


def is_hidden_scan_folder(folder_name):
    """浏览目录时跳过的文件夹名。"""
    name = _as_text(folder_name)
    return name in (
        PUBLISH_SETTINGS_FOLDER, PUBLISH_BACKUP_FOLDER, RIG_UPDATE_BACKUP_FOLDER
    )


def is_hidden_max_file(file_path):
    """是否在文件管理工具中隐藏该 .max 文件。"""
    path = _as_text(file_path)
    if not path:
        return True
    parts = path.replace(u"\\", u"/").split(u"/")
    if RIG_UPDATE_BACKUP_FOLDER in parts:
        return True
    base = os.path.basename(path)
    return _TIMESTAMP_MAX_SUFFIX_RE.search(base) is not None

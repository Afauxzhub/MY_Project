# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import shutil
import time

from anim_migration.workflow.context import detect_file_context

try:
    _text_type = unicode
except NameError:
    _text_type = str


BACKUP_FOLDER_NAME = u"_RigUpdateBackup"


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _character_root_for(max_path):
    max_path = os.path.abspath(_as_text(max_path))
    ctx = detect_file_context(max_path)
    anim_type = _as_text(ctx.get("type", ""))
    character = _as_text(ctx.get("character", ""))
    if not anim_type or not character:
        return os.path.dirname(max_path)
    parts = max_path.split(os.sep)
    for i in range(0, len(parts) - 1):
        if parts[i] == anim_type and i + 1 < len(parts) and parts[i + 1] == character:
            return os.sep.join(parts[:i + 2])
    return os.path.dirname(max_path)


def backup_root_for(max_path):
    return os.path.join(_character_root_for(max_path), BACKUP_FOLDER_NAME)


def timestamped_backup_path(max_path):
    root = backup_root_for(max_path)
    stem, ext = os.path.splitext(os.path.basename(_as_text(max_path)))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = os.path.join(root, u"{0}_{1}{2}".format(stem, stamp, ext or ".max"))
    if not os.path.exists(candidate):
        return candidate
    for i in range(1, 1000):
        alt = os.path.join(root, u"{0}_{1}_{2:03d}{3}".format(stem, stamp, i, ext or ".max"))
        if not os.path.exists(alt):
            return alt
    raise RuntimeError(u"无法生成不重复的备份文件名")


def create_backup(max_path):
    max_path = os.path.abspath(_as_text(max_path))
    if not os.path.exists(max_path):
        raise RuntimeError(u"源文件不存在，无法备份: {0}".format(max_path))
    root = backup_root_for(max_path)
    if not os.path.exists(root):
        os.makedirs(root)
    backup_path = timestamped_backup_path(max_path)
    shutil.copy2(max_path, backup_path)
    return backup_path


def list_backups(max_path):
    root = backup_root_for(max_path)
    if not os.path.isdir(root):
        return []
    stem = os.path.splitext(os.path.basename(_as_text(max_path)))[0]
    rows = []
    for name in os.listdir(root):
        if name.lower().endswith(".max") and name.startswith(stem + "_"):
            path = os.path.join(root, name)
            rows.append(path)
    rows.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return rows


def restore_backup(current_path, backup_path):
    current_path = os.path.abspath(_as_text(current_path))
    backup_path = os.path.abspath(_as_text(backup_path))
    if not os.path.exists(backup_path):
        raise RuntimeError(u"备份文件不存在: {0}".format(backup_path))
    folder = os.path.dirname(current_path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    if os.path.exists(current_path):
        os.remove(current_path)
    shutil.copy2(backup_path, current_path)
    return current_path

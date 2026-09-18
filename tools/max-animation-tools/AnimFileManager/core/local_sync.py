# -*- coding: utf-8 -*-
"""公盘 → 本地单向同步（按角色文件夹）。"""
from __future__ import division
import os
import shutil

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


def _ensure_dir(path):
    if path and not os.path.isdir(path):
        os.makedirs(path)


def publish_settings_path_for_max(max_path):
    """max 文件对应的发布设置 json 路径（同目录「发布设置」文件夹内）。"""
    from core.paths import PUBLISH_SETTINGS_FOLDER

    max_path = _as_text(max_path)
    if not max_path:
        return u""
    folder = os.path.dirname(max_path)
    stem = os.path.splitext(os.path.basename(max_path))[0]
    if not stem:
        return u""
    return os.path.join(folder, PUBLISH_SETTINGS_FOLDER, stem + u".json")


def _sync_companion_settings(src_max_path, dest_max_path):
    """同步 max 对应的发布设置文件；源不存在或失败时静默跳过。"""
    src_json = publish_settings_path_for_max(src_max_path)
    if not src_json or not os.path.isfile(src_json):
        return
    dest_json = publish_settings_path_for_max(dest_max_path)
    if not dest_json:
        return
    try:
        _ensure_dir(os.path.dirname(dest_json))
        shutil.copy2(src_json, dest_json)
    except Exception:
        pass


def _copy_tree(src, dst):
    """递归复制 src 到 dst，覆盖同名文件。"""
    src = _as_text(src)
    dst = _as_text(dst)
    if not os.path.isdir(src):
        raise IOError(u"公盘角色目录不存在: {0}".format(src))
    _ensure_dir(dst)
    for current, dirs, files in os.walk(src):
        from core.paths import PUBLISH_BACKUP_FOLDER
        dirs[:] = [d for d in dirs if d != PUBLISH_BACKUP_FOLDER]
        rel = os.path.relpath(current, src)
        target_dir = dst if rel == u"." else os.path.join(dst, rel)
        _ensure_dir(target_dir)
        for name in files:
            s = os.path.join(current, name)
            d = os.path.join(target_dir, name)
            shutil.copy2(s, d)


def local_path_for_public_file(public_file_path, local_root, combat_folder, category, character):
    """计算公盘文件对应的本地路径（不执行复制）。"""
    from core.paths import NAS_BASE

    public_file_path = _as_text(public_file_path)
    local_root = _as_text(local_root)
    if not public_file_path or not local_root:
        return u""
    public_char_path = make_public_char_path(
        NAS_BASE, combat_folder, category, character
    )
    local_char_path = make_local_char_path(
        local_root, combat_folder, category, character
    )
    try:
        rel = os.path.relpath(public_file_path, public_char_path)
    except ValueError:
        return u""
    if rel.startswith(u".."):
        return u""
    return os.path.join(local_char_path, rel)


def sync_single_file(public_file_path, local_root, combat_folder, category, character):
    """将公盘单个文件同步到本地，保留相对目录结构。成功时返回本地路径。"""
    from core.paths import NAS_BASE

    public_file_path = _as_text(public_file_path)
    local_root = _as_text(local_root)
    if not public_file_path or not os.path.isfile(public_file_path):
        return False, u"公盘文件不存在: {0}".format(public_file_path)
    if not local_root:
        return False, u"请先设置本地根路径"
    local_dest = local_path_for_public_file(
        public_file_path, local_root, combat_folder, category, character
    )
    if not local_dest:
        return False, u"无法解析文件相对路径"
    try:
        _ensure_dir(os.path.dirname(local_dest))
        shutil.copy2(public_file_path, local_dest)
        _sync_companion_settings(public_file_path, local_dest)
        return True, local_dest
    except Exception as e:
        return False, _as_text(e)


def sync_character_folder(public_char_path, local_char_path):
    """
  将公盘角色文件夹完整同步到本地对应路径。
  返回 (copied_ok, message)
    """
    public_char_path = _as_text(public_char_path)
    local_char_path = _as_text(local_char_path)
    if not public_char_path or not os.path.isdir(public_char_path):
        return False, u"公盘角色目录不可访问: {0}".format(public_char_path)
    try:
        _copy_tree(public_char_path, local_char_path)
        return True, u"已同步: {0}".format(os.path.basename(local_char_path))
    except Exception as e:
        return False, _as_text(e)


def make_local_char_path(local_root, combat_folder, category, character):
    """根据本地根路径拼出角色目录。"""
    return os.path.join(
        _as_text(local_root),
        _as_text(combat_folder),
        _as_text(category),
        _as_text(character),
    )


def make_public_char_path(public_root, combat_folder, category, character):
    return os.path.join(
        _as_text(public_root),
        _as_text(combat_folder),
        _as_text(category),
        _as_text(character),
    )

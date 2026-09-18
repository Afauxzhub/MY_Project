# -*- coding: utf-8 -*-
"""目录扫描：仅 .max 文件，完整/简略模式共用。"""
from __future__ import division
import os

from core.paths import MAX_EXT, is_hidden_max_file, is_hidden_scan_folder
from core.version_resolver import resolve_latest_max_files
from core.publish_metadata import read_publish_metadata

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


def list_subdirs(path):
    path = _as_text(path)
    if not path or not os.path.isdir(path):
        return []
    names = []
    try:
        for name in os.listdir(path):
            full = os.path.join(path, name)
            if os.path.isdir(full):
                names.append(name)
    except Exception:
        return []
    names.sort(key=lambda x: x.lower())
    return names


def dir_has_max_files(path):
    """目录自身或子目录中是否包含 .max 文件。"""
    path = _as_text(path)
    if not path or not os.path.isdir(path):
        return False
    try:
        for current, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not is_hidden_scan_folder(d)]
            for name in files:
                if name.lower().endswith(MAX_EXT) and not is_hidden_max_file(
                    os.path.join(current, name)
                ):
                    return True
    except Exception:
        return False
    return False


def list_local_categories(combat_local_path):
    """本地局内/局外目录下，仅返回含已同步动作文件的角色所属分类。"""
    combat_local_path = _as_text(combat_local_path)
    categories = []
    for category in list_subdirs(combat_local_path):
        category_path = os.path.join(combat_local_path, category)
        for character in list_subdirs(category_path):
            char_path = os.path.join(category_path, character)
            if dir_has_max_files(char_path):
                categories.append(category)
                break
    return categories


def list_local_characters(category_path):
    """本地分类目录下，仅返回含已同步动作文件的角色。"""
    category_path = _as_text(category_path)
    characters = []
    for character in list_subdirs(category_path):
        char_path = os.path.join(category_path, character)
        if dir_has_max_files(char_path):
            characters.append(character)
    return characters


def list_max_files_in_dir(path):
    """列出目录下直接的 .max 文件（不递归）。"""
    path = _as_text(path)
    if not path or not os.path.isdir(path):
        return []
    files = []
    try:
        for name in os.listdir(path):
            if name.lower().endswith(MAX_EXT) and not is_hidden_max_file(
                os.path.join(path, name)
            ):
                files.append(name)
    except Exception:
        return []
    files.sort(key=lambda x: x.lower())
    return files


def list_full_dir_entries(path):
    """完整模式按需读取单层目录，不递归访问子文件夹。"""
    path = _as_text(path)
    if not path or not os.path.isdir(path):
        return []
    try:
        entries = os.listdir(path)
    except Exception:
        return []

    dirs = []
    files = []
    for name in entries:
        full = os.path.join(path, name)
        if os.path.isdir(full):
            if not is_hidden_scan_folder(name):
                dirs.append(name)
        elif name.lower().endswith(MAX_EXT) and not is_hidden_max_file(full):
            files.append(name)

    result = []
    for name in sorted(dirs, key=lambda x: x.lower()):
        result.append({
            u"name": name,
            u"path": os.path.join(path, name),
            u"type": u"folder",
            u"children": [],
        })
    for name in sorted(files, key=lambda x: x.lower()):
        file_path = os.path.join(path, name)
        result.append({
            u"name": name,
            u"path": file_path,
            u"type": u"file",
            u"children": [],
            u"metadata": read_publish_metadata(file_path),
        })
    return result


def build_full_tree(root_path, max_depth=32):
    """
    构建完整显示模式的树结构。
    仅包含文件夹与 .max 文件；其他文件类型跳过。
    若文件夹内无 .max 子项且自身也无 .max，仍保留空文件夹节点。
    """
    root_path = _as_text(root_path)
    if not root_path or not os.path.isdir(root_path):
        return None

    def _walk(current, depth):
        node = {
            u"name": os.path.basename(current) or current,
            u"path": current,
            u"type": u"folder",
            u"children": [],
        }
        if depth <= 0:
            return node
        try:
            entries = os.listdir(current)
        except Exception:
            return node
        dirs = []
        files = []
        for name in entries:
            full = os.path.join(current, name)
            if os.path.isdir(full):
                if is_hidden_scan_folder(name):
                    continue
                dirs.append(name)
            elif name.lower().endswith(MAX_EXT):
                if not is_hidden_max_file(full):
                    files.append(name)
        for name in sorted(dirs, key=lambda x: x.lower()):
            child = _walk(os.path.join(current, name), depth - 1)
            node[u"children"].append(child)
        for name in sorted(files, key=lambda x: x.lower()):
            file_path = os.path.join(current, name)
            metadata = read_publish_metadata(file_path, root_path)
            node[u"children"].append({
                u"name": name,
                u"path": file_path,
                u"type": u"file",
                u"children": [],
                u"metadata": metadata,
            })
        return node

    return _walk(root_path, max_depth)


def get_character_files(char_path, allow_files=True):
    """
    简略模式右侧文件列。
    allow_files=False 时（本地未刷新角色）返回空列表。
    """
    if not allow_files:
        return []
    return resolve_latest_max_files(char_path)

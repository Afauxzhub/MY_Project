# -*- coding: utf-8 -*-
"""
角色文件夹内多阶段版本解析。

规则：
  - 阶段优先级：监修 > 终版 > 初版
  - 阶段内若存在数字子文件夹（如 1.0、2.0），数字越大越新
  - 同名 .max 保留“版本最新”和“发布日期最新”的候选并集
"""
from __future__ import division
import os
import re

from core.paths import STAGE_FOLDERS, is_hidden_max_file, is_hidden_scan_folder
from core.publish_metadata import read_publish_metadata

try:
    _text_type = unicode
except NameError:
    _text_type = str

_STAGE_RANK = {
    u"初版": 1,
    u"终版": 2,
    u"监修": 3,
}

_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return _text_type(repr(value))


def _parse_version_number(folder_name):
    """从文件夹名提取版本号，无法解析时返回 0。"""
    name = _as_text(folder_name).strip()
    if not name:
        return 0.0
    if name.replace(u".", u"", 1).isdigit():
        try:
            return float(name)
        except Exception:
            return 0.0
    match = _NUM_RE.search(name)
    if match:
        try:
            return float(match.group(1))
        except Exception:
            return 0.0
    return 0.0


def _score_file_path(char_root, file_path):
    """
    计算文件版本得分 (stage_rank, version_num, mtime)。
    char_root 为角色文件夹根路径。
    """
    rel = os.path.relpath(file_path, char_root)
    parts = [_as_text(p) for p in rel.replace(u"\\", u"/").split(u"/") if p]
    if not parts:
        return (0, 0.0, 0.0)

    stage_rank = 0
    version_num = 0.0
    if len(parts) > 1 and parts[0] in _STAGE_RANK:
        stage_rank = _STAGE_RANK[parts[0]]
        if len(parts) > 2:
            version_num = _parse_version_number(parts[1])
    try:
        mtime = os.path.getmtime(file_path)
    except Exception:
        mtime = 0.0
    return (stage_rank, version_num, mtime)


def _iter_max_files_under(root):
    """递归收集 root 下所有 .max 文件（跳过隐藏备份文件/目录）。"""
    if not root or not os.path.isdir(root):
        return
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not is_hidden_scan_folder(d)]
        for name in files:
            if not name.lower().endswith(u".max"):
                continue
            file_path = os.path.join(current, name)
            if is_hidden_max_file(file_path):
                continue
            yield file_path


def collect_max_file_candidates(char_root):
    """按文件名收集角色目录中的全部有效候选，供展示和更新检查共用。"""
    char_root = _as_text(char_root)
    if not char_root or not os.path.isdir(char_root):
        return {}

    grouped = {}
    for file_path in _iter_max_files_under(char_root):
        base = os.path.basename(file_path)
        key = base.lower()
        score = _score_file_path(char_root, file_path)
        metadata = read_publish_metadata(file_path, char_root)
        item = {
            u"score": score,
            u"version_score": (
                score[0], score[1], metadata.get(u"publish_revision", 0),
                metadata.get(u"published_sort", 0.0), score[2]
            ),
            u"date_score": (
                metadata.get(u"published_sort", 0.0), score[0], score[1],
                metadata.get(u"publish_revision", 0)
            ),
            u"name": base,
            u"path": file_path,
            u"display_stage": metadata.get(u"stage", u""),
        }
        item.update(metadata)
        grouped.setdefault(key, []).append(item)
    return grouped


def select_latest_candidate_pair(candidates):
    """返回（阶段最新，日期最新）；无候选时返回（None, None）。"""
    candidates = list(candidates or [])
    if not candidates:
        return None, None
    latest_version = max(candidates, key=lambda x: x[u"version_score"])
    latest_date = max(candidates, key=lambda x: x[u"date_score"])
    return latest_version, latest_date


def resolve_latest_max_files(char_root):
    """
    解析角色文件夹，返回最新版本 .max 文件列表。

    返回 list[dict]:
      - name: 文件名
      - path: 绝对路径
      - display_stage: 来源阶段（用于状态提示）
    """
    grouped = collect_max_file_candidates(char_root)

    items = []
    for candidates in grouped.values():
        latest_version, latest_date = select_latest_candidate_pair(candidates)
        items.append(latest_version)
        if latest_date[u"path"].lower() != latest_version[u"path"].lower():
            items.append(latest_date)
    items.sort(key=lambda x: (x[u"name"].lower(), -x[u"published_sort"]))
    return items

# -*- coding: utf-8 -*-
"""
发布前查询公盘角色目录的最新阶段。

版本新旧规则与 AnimFileManager（打开文件工具）一致：
  - 阶段优先级：监修 > 终版 > 初版
  - 监修子目录数字越大越新
  - 同阶段同版本按 mtime 比较
"""
from __future__ import division
import os
import re

from pipeline.rm_file_io import NAS_DEFAULT_BASE, NAS_INDOOR_FOLDER, NAS_OUTDOOR_FOLDER
from pipeline.rm_naming import clean_string_native

try:
    _text_type = unicode
except NameError:
    _text_type = str

STAGE_FOLDERS = (u"初版", u"终版", u"监修")
_STAGE_RANK = {
    u"初版": 1,
    u"终版": 2,
    u"监修": 3,
}
_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")
_HIDDEN_SCAN_FOLDERS = (u"发布设置", u"发布备份", u"_RigUpdateBackup")
_TIMESTAMP_MAX_SUFFIX_RE = re.compile(r"_\d{8}_\d{6}\.max$", re.IGNORECASE)
MAX_REVIEW_VERSION = 99


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return _text_type(repr(value))


def format_publish_stage_label(stage, version=None):
    """将设置中的阶段格式化为展示标签，如 初版 / 终版 / 监修1.0。"""
    stage = _as_text(stage).strip() or u"初版"
    version = _as_text(version).strip()
    if stage == u"监修":
        if version:
            return u"监修" + version
        return u"监修（未填写版本号）"
    return stage


def build_review_version_options(max_version=MAX_REVIEW_VERSION):
    """返回只读监修子版本选项：1.0、2.0、3.0……。"""
    try:
        maximum = max(1, int(max_version))
    except Exception:
        maximum = MAX_REVIEW_VERSION
    return [u"{0}.0".format(index) for index in range(1, maximum + 1)]


def make_stage_state(stage, version=u"", path=u""):
    """构建供 UI/比较使用的标准阶段状态。"""
    stage = _as_text(stage).strip() or u"初版"
    if stage not in STAGE_FOLDERS:
        stage = u"初版"
    version = _as_text(version).strip() if stage == u"监修" else u""
    return {
        u"stage": stage,
        u"version": version,
        u"label": format_publish_stage_label(stage, version),
        u"path": _as_text(path),
    }


def stage_sequence_position(stage, version=u""):
    """映射到连续阶段轴：初版0、终版1、监修1.0起为2。"""
    stage = _as_text(stage).strip() or u"初版"
    if stage == u"终版":
        return 1.0
    if stage == u"监修":
        return 1.0 + max(1.0, _parse_version_number(version))
    return 0.0


def classify_publish_stage(selected_stage, selected_version=u"", character_stage=None):
    """
    返回 normal / earlier / too_far_ahead / unpublished_non_initial。

    角色未发布时只有初版无需警告；已有阶段时，向后退任意一级或
    向前跨两级及以上都需要二次确认。
    """
    selected = make_stage_state(selected_stage, selected_version)
    if not character_stage:
        if selected[u"stage"] == u"初版":
            return u"normal"
        return u"unpublished_non_initial"
    current = make_stage_state(
        character_stage.get(u"stage", u"初版"),
        character_stage.get(u"version", u""),
    )
    delta = stage_sequence_position(
        selected[u"stage"], selected[u"version"]
    ) - stage_sequence_position(current[u"stage"], current[u"version"])
    if delta < 0.0:
        return u"earlier"
    if delta >= 2.0:
        return u"too_far_ahead"
    return u"normal"


def build_indoor_char_root(nas_base, category, char_name):
    base = _as_text(nas_base).strip() or NAS_DEFAULT_BASE
    return os.path.join(base, NAS_INDOOR_FOLDER, _as_text(category), _as_text(char_name))


def build_outdoor_char_root(nas_base, module_folder, type_folder, char_folder):
    base = _as_text(nas_base).strip() or NAS_DEFAULT_BASE
    return os.path.join(
        base,
        NAS_OUTDOOR_FOLDER,
        _as_text(module_folder),
        _as_text(type_folder),
        _as_text(char_folder),
    )


def _is_hidden_scan_folder(folder_name):
    return _as_text(folder_name) in _HIDDEN_SCAN_FOLDERS


def _is_hidden_max_file(file_path):
    path = _as_text(file_path)
    if not path:
        return True
    parts = path.replace(u"\\", u"/").split(u"/")
    if u"_RigUpdateBackup" in parts:
        return True
    base = os.path.basename(path)
    return _TIMESTAMP_MAX_SUFFIX_RE.search(base) is not None


def _parse_version_number(folder_name):
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


def _stage_label_from_rel_path(char_root, file_path):
    rel = os.path.relpath(file_path, char_root)
    parts = [_as_text(p) for p in rel.replace(u"\\", u"/").split(u"/") if p]
    if not parts or parts[0] not in STAGE_FOLDERS:
        return None
    if parts[0] == u"监修" and len(parts) > 2:
        return u"监修" + parts[1]
    return parts[0]


def _stage_state_from_rel_path(char_root, file_path):
    rel = os.path.relpath(file_path, char_root)
    parts = [_as_text(p) for p in rel.replace(u"\\", u"/").split(u"/") if p]
    if not parts or parts[0] not in STAGE_FOLDERS:
        return None
    version = parts[1] if parts[0] == u"监修" and len(parts) > 2 else u""
    return make_stage_state(parts[0], version, file_path)


def _iter_max_files_under(root):
    root = _as_text(root)
    if not root or not os.path.isdir(root):
        return
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not _is_hidden_scan_folder(d)]
        for name in files:
            if not name.lower().endswith(u".max"):
                continue
            file_path = os.path.join(current, name)
            if _is_hidden_max_file(file_path):
                continue
            yield file_path


def find_latest_public_stage_label(char_root, match_key):
    """
    在公盘角色目录中查找与 match_key 同名的最新 .max 阶段标签。

    match_key 应为发布合规后的文件名（不含扩展名）。
    未找到时返回 None。
    """
    char_root = _as_text(char_root)
    match_key = clean_string_native(_as_text(match_key), u"").lower()
    if not char_root or not match_key or not os.path.isdir(char_root):
        return None

    best_label = None
    best_score = None
    for file_path in _iter_max_files_under(char_root):
        stem = os.path.splitext(os.path.basename(file_path))[0]
        file_key = clean_string_native(stem, u"").lower()
        if file_key != match_key:
            continue
        score = _score_file_path(char_root, file_path)
        if best_score is None or score > best_score:
            best_score = score
            best_label = _stage_label_from_rel_path(char_root, file_path)
    return best_label


def find_latest_character_stage(char_root):
    """
    扫描角色目录下所有动作，返回角色所处的最新阶段状态。

    不按当前动作文件名过滤。不同动作分布在不同阶段时，阶段最高、
    监修数字最大的任意一个动作决定当前角色阶段。没有文件返回 None。
    """
    char_root = _as_text(char_root)
    if not char_root or not os.path.isdir(char_root):
        return None

    best_state = None
    best_score = None
    for file_path in _iter_max_files_under(char_root):
        state = _stage_state_from_rel_path(char_root, file_path)
        if state is None:
            continue
        score = _score_file_path(char_root, file_path)
        if best_score is None or score > best_score:
            best_score = score
            best_state = state
    return best_state

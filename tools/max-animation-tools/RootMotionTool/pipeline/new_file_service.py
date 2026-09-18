# -*- coding: utf-8 -*-
"""“新建文件”工具的纯文件与命名逻辑。"""
from __future__ import print_function

import io
import json
import os
import re
import shutil

from anim_migration.workflow.rig_locator import (
    find_in_game_rigs,
    find_out_game_rigs,
    is_skin_binding_file,
)

try:
    _text_type = unicode
except NameError:
    _text_type = str


LOCAL_INDOOR_FOLDER = u"局内战斗备份"
LOCAL_OUTDOOR_FOLDER = u"局外演出备份"
VALID_STAGES = (u"初版", u"终版", u"监修")
_NAME_PART_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_VERSION_RE = re.compile(r"(\d+)")
_RIG_VERSION_RE = re.compile(r"(?i)(?:^|_)v(\d{1,3})(?=\.max$|_)")


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def normalize_name_part(value):
    """去除首尾空白，并把第一个英文字母改为大写。"""
    text = _as_text(value).strip()
    if not text:
        return u""
    return text[0].upper() + text[1:]


def validate_name_part(value, label):
    text = normalize_name_part(value)
    if not text:
        return False, u"{0}不能为空".format(label), u""
    if not _NAME_PART_RE.match(text):
        return (
            False,
            u"{0}只能使用英文字母和数字，并且必须以英文字母开头".format(label),
            text,
        )
    return True, u"", text


def compose_indoor_filename(category, character, action):
    return u"{0}_{1}_{2}.max".format(
        _as_text(category).strip(),
        normalize_name_part(character),
        normalize_name_part(action),
    )


def compose_outdoor_role_filename(module_code, category, character, camera_name):
    return u"{0}_{1}_{2}_{3}.max".format(
        _as_text(module_code).strip(),
        _as_text(category).strip(),
        normalize_name_part(character),
        _as_text(camera_name).strip(),
    )


def build_chapter_options(maximum=99):
    try:
        maximum = max(1, int(maximum))
    except Exception:
        maximum = 99
    return [u"Chapter{0:02d}".format(index) for index in range(1, maximum + 1)]


def build_scene_options(maximum=99):
    try:
        maximum = max(1, int(maximum))
    except Exception:
        maximum = 99
    return [u"Scene{0:02d}".format(index) for index in range(1, maximum + 1)]


def chapter_code_from_label(value):
    text = _as_text(value).strip()
    match = re.match(r"^Chapter(\d{2,})$", text)
    return u"Chap{0}".format(match.group(1)) if match else u""


def scene_code_from_label(value):
    text = _as_text(value).strip()
    match = re.match(r"^Scene(\d{2,})$", text)
    return u"SC{0}".format(match.group(1)) if match else u""


def compose_outdoor_dialogue_filename(
    module_code, chapter_label, scene_label, camera_name
):
    chapter_code = chapter_code_from_label(chapter_label)
    scene_code = scene_code_from_label(scene_label)
    camera_name = _as_text(camera_name).strip()
    if not (
        _as_text(module_code).strip()
        and chapter_code
        and scene_code
        and re.match(r"^Cam\d{2,}$", camera_name)
    ):
        return u""
    return u"{0}_{1}_{2}_{3}.max".format(
        _as_text(module_code).strip(), chapter_code, scene_code, camera_name
    )


def build_camera_options(maximum=99):
    try:
        maximum = max(1, int(maximum))
    except Exception:
        maximum = 99
    return [u"Cam{0:02d}".format(index) for index in range(1, maximum + 1)]


def split_stage_label(stage_label):
    label = _as_text(stage_label).strip() or u"初版"
    if label.startswith(u"监修"):
        return u"监修", label[len(u"监修"):].strip()
    if label in (u"初版", u"终版"):
        return label, u""
    return u"初版", u""


def build_indoor_destination(
    local_root, category, character, stage, version, filename
):
    stage = _as_text(stage).strip()
    if stage not in VALID_STAGES:
        stage = u"初版"
    parts = [
        _as_text(local_root).strip(),
        LOCAL_INDOOR_FOLDER,
        _as_text(category).strip(),
        normalize_name_part(character),
        stage,
    ]
    if stage == u"监修":
        parts.append(_as_text(version).strip())
    parts.append(_as_text(filename).strip())
    return os.path.normpath(os.path.join(*parts))


def build_outdoor_destination(
    local_root,
    module_folder,
    type_folder,
    character,
    stage,
    version,
    filename,
):
    stage = _as_text(stage).strip()
    if stage not in VALID_STAGES:
        stage = u"初版"
    parts = [
        _as_text(local_root).strip(),
        LOCAL_OUTDOOR_FOLDER,
        _as_text(module_folder).strip(),
        _as_text(type_folder).strip(),
        normalize_name_part(character),
        stage,
    ]
    if stage == u"监修":
        parts.append(_as_text(version).strip())
    parts.append(_as_text(filename).strip())
    return os.path.normpath(os.path.join(*parts))


def _load_json(path):
    try:
        if path and os.path.isfile(path):
            with io.open(path, u"r", encoding=u"utf-8") as stream:
                value = json.load(stream)
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def load_anim_file_manager_config(install_root):
    """只读打开文件工具的持久配置；用户配置优先于旧配置。"""
    root = _as_text(install_root)
    legacy_path = os.path.join(
        root, u"AnimFileManager", u"config", u"afm_config.json"
    )
    user_path = os.path.join(root, u"afm_user_config.json")
    config = {u"local_root": u""}
    config.update(_load_json(legacy_path))
    config.update(_load_json(user_path))
    return config


def _version_number(value):
    match = _VERSION_RE.search(_as_text(value))
    return int(match.group(1)) if match else 0


def binding_category_from_path(path):
    """从 Type_Character_lod/cs_skin_Vxx.max 的第一段读取绑定分类。"""
    name = os.path.basename(_as_text(path))
    return name.split(u"_")[0] if u"_" in name else u""


def _prefer_exact_category(rigs, category):
    """有精确分类时仅保留精确项，否则返回该角色的全部分类绑定。"""
    category_lower = _as_text(category).strip().lower()
    if not category_lower:
        return rigs
    exact = [
        item for item in rigs
        if binding_category_from_path(item.get(u"path", u"")).lower()
        == category_lower
    ]
    return exact if exact else rigs


def find_indoor_binding_files(character, character_rig_root, category=u""):
    """返回局内 LOD 绑定；版本高优先，同版本按更新时间新优先。"""
    character = normalize_name_part(character)
    if not character:
        return []
    category = _as_text(category).strip()
    try:
        rigs = find_in_game_rigs(
            character, character_rig_root=character_rig_root or None
        )
    except Exception:
        rigs = []

    # 共享绑定定位器只枚举内置分类。这里限定扫描当前角色目录，补齐所有
    # 自定义分类，以便精确分类不存在时能够真正显示该角色的全部分类绑定。
    if character_rig_root:
        character_dir = os.path.join(_as_text(character_rig_root), character)
        try:
            existing = set([
                os.path.normcase(os.path.normpath(_as_text(item.get(u"path", u""))))
                for item in rigs
            ])
            for folder_name in (
                os.listdir(character_dir) if os.path.isdir(character_dir) else []
            ):
                max_dir = os.path.join(character_dir, folder_name, u"wip", u"max")
                if not os.path.isdir(max_dir):
                    continue
                for name in os.listdir(max_dir):
                    if not is_skin_binding_file(
                        name, mode="in_game", character=character
                    ):
                        continue
                    path = os.path.join(max_dir, name)
                    key = os.path.normcase(os.path.normpath(path))
                    if key in existing:
                        continue
                    match = _RIG_VERSION_RE.search(name)
                    version = (
                        u"v{0:02d}".format(int(match.group(1))) if match else u""
                    )
                    rigs.append({u"path": path, u"version": version})
                    existing.add(key)
        except Exception:
            pass

    rigs = _prefer_exact_category(rigs, category)

    def _sort_key(item):
        path = _as_text(item.get(u"path", u""))
        try:
            modified = os.path.getmtime(path)
        except Exception:
            modified = 0
        return (_version_number(item.get(u"version", u"")), modified)

    return sorted(rigs, key=_sort_key, reverse=True)


def find_outdoor_binding_files(character, character_rig_root, category=u""):
    """返回角色目录中的 CS 绑定；输入错误时不回退扫描整个角色资源根目录。"""
    character = normalize_name_part(character)
    root = _as_text(character_rig_root).strip()
    if not character or not root or not os.path.isdir(os.path.join(root, character)):
        return []
    try:
        rigs = find_out_game_rigs(character, character_rig_root=root)
    except Exception:
        rigs = []

    rigs = _prefer_exact_category(rigs, category)

    def _sort_key(item):
        path = _as_text(item.get(u"path", u""))
        try:
            modified = os.path.getmtime(path)
        except Exception:
            modified = 0
        return (_version_number(item.get(u"version", u"")), modified)

    return sorted(rigs, key=_sort_key, reverse=True)


def copy_binding_to_destination(source_path, destination_path):
    source = os.path.normpath(_as_text(source_path).strip())
    destination = os.path.normpath(_as_text(destination_path).strip())
    if not source or not os.path.isfile(source):
        return False, u"绑定文件不存在：{0}".format(source)
    if not destination or not destination.lower().endswith(u".max"):
        return False, u"文件路径必须以 .max 结尾"
    if os.path.exists(destination):
        return False, u"目标文件已存在，不会覆盖：{0}".format(destination)
    try:
        folder = os.path.dirname(destination)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        shutil.copy2(source, destination)
        return True, destination
    except Exception as exc:
        return False, _as_text(exc)

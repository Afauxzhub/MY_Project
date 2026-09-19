# -*- coding: utf-8 -*-
"""Personal character animation contract; pure Python 2.7/3 compatible helpers.

Identity: Character_Action or Character_Set_Action. Folder purpose is not state.
Legacy category and cinematic prefixes are reserved for their existing parsers.
"""
from __future__ import unicode_literals
import os
import re

PURPOSES = ("Locomotion", "Attacks", "Reactions", "Interactions", "Common")
LEGACY_PREFIXES = ("Role", "Monster", "Elite", "Boss", "Npc", "Scene")
CINEMATIC_PREFIXES = ("UL", "EN", "RE", "GA", "DE", "ER", "CS", "QTE", "DI")
PART = re.compile(r"\A[A-Z][A-Za-z0-9]*\Z")


def parse_name(name, reserved=()):
    parts = name.split("_")
    if (len(parts) not in (2, 3) or
            parts[0] in LEGACY_PREFIXES + CINEMATIC_PREFIXES + tuple(reserved) or
            not all(PART.match(part) for part in parts)):
        return False, "格式：角色_动作 或 角色_动作集_动作；字段以大写字母开头，仅含字母数字。", {}
    return True, "", {
        "naming_scheme": "personal",
        "char_name": parts[0],
        "action_set": parts[1] if len(parts) == 3 else "",
        "action_name": parts[-1],
        # Compatibility fields for older panels; never route a personal asset by category.
        "category": "",
        "stage": "",
    }


def compose_name(character, action, action_set=""):
    parts = [character, action_set, action] if action_set else [character, action]
    name = "_".join(parts)
    ok, message, _ = parse_name(name)
    if not ok:
        raise ValueError(message)
    return name


def source_characters_root(unity_assets):
    if not unity_assets:
        return ""
    path = os.path.normpath(unity_assets)
    if os.path.basename(path).lower() != "assets" or not os.path.isabs(path):
        return ""
    return os.path.join(os.path.dirname(os.path.dirname(path)), "ArtSource", "Characters")


def source_destination(unity_assets, character, purpose, filename):
    root = source_characters_root(unity_assets)
    ok, _, parsed = parse_name(os.path.splitext(filename)[0])
    if not root or not ok or parsed["char_name"] != character or purpose not in PURPOSES:
        raise ValueError("请设置 Unity Assets 路径，并使用有效的角色 / 动作分类 / 文件名。")
    if os.path.basename(filename) != filename or not filename.lower().endswith(".max"):
        raise ValueError("必须使用不带路径的 .max 文件名。")
    return os.path.join(root, character, "Animations", purpose, filename)


def purpose_from_source(max_path):
    parts = max_path.replace("\\", "/").split("/")
    # Only the explicit Animations/<purpose> directory has routing meaning.
    for index in range(len(parts) - 2, -1, -1):
        if parts[index] == "Animations" and parts[index + 1] in PURPOSES:
            return parts[index + 1]
    return "Common"


def unity_destination(unity_assets, parsed, max_path):
    return os.path.join(unity_assets, "Art", "Animations", parsed["char_name"],
                        purpose_from_source(max_path))


def clip_path_from_fbx(clip_root, fbx_path, source_root):
    """Mirror the imported FBX's relative parent, rejecting paths outside source root."""
    source = os.path.normcase(os.path.abspath(source_root))
    fbx = os.path.normcase(os.path.abspath(fbx_path))
    if not fbx.startswith(source.rstrip(os.sep) + os.sep):
        raise ValueError("FBX is outside the configured animation source root")
    relative = os.path.relpath(os.path.abspath(fbx_path), os.path.abspath(source_root))
    return os.path.join(clip_root, os.path.splitext(relative)[0] + ".anim")

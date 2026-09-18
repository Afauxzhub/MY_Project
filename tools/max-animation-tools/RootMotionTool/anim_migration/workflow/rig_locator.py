# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re

from anim_migration.workflow.context import INGAME_TYPES

try:
    _text_type = unicode
except NameError:
    _text_type = str


DEFAULT_CHARACTER_RIG_ROOT = u""


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _version_number(version):
    match = re.search(r"(\d+)", _as_text(version))
    return int(match.group(1)) if match else 1


def _parse_rig_version(path):
    match = re.search(r"(?i)(?:^|_)v(\d{1,3})(?=\.max$|_)", os.path.basename(_as_text(path)))
    return u"v{0:02d}".format(int(match.group(1))) if match else u""


def _name_tokens(path_or_name):
    stem = os.path.splitext(os.path.basename(_as_text(path_or_name)))[0]
    return [x.lower() for x in stem.split("_") if x]


def is_skin_binding_file(path_or_name, mode=None, character=None):
    name = os.path.basename(_as_text(path_or_name))
    if not name.lower().endswith(".max"):
        return False
    tokens = _name_tokens(name)
    character = _as_text(character).lower()
    if len(tokens) < 5 or tokens[-1][0:1] != "v" or tokens[-2] != "skin":
        return False
    if character and tokens[1] != character:
        return False
    if mode == "in_game":
        return tokens[2] == "lod" and bool(_parse_rig_version(name))
    if mode == "out_game":
        return tokens[2] == "cs" and bool(_parse_rig_version(name))
    if tokens[2] not in ("lod", "cs"):
        return False
    return bool(_parse_rig_version(name))


def _in_game_rig_wip_max_dirs(character, character_rig_root=None):
    """Candidate .../<lod_folder>/wip/max paths: legacy Character_lod and Type_Character_lod (e.g. Monster_Character_lod, Role_Hero_lod)."""
    root = character_rig_root or DEFAULT_CHARACTER_RIG_ROOT
    character = _as_text(character)
    if not character:
        return []
    base = os.path.join(root, character)
    ordered = []
    seen_lower = set()

    def _add(folder_name):
        p = os.path.join(base, folder_name, u"wip", u"max")
        key = p.lower()
        if key not in seen_lower:
            seen_lower.add(key)
            ordered.append(p)

    _add(character + u"_lod")
    for t in sorted(INGAME_TYPES):
        _add(u"{0}_{1}_lod".format(_as_text(t), character))
    return ordered


def in_game_rig_dir(character, character_rig_root=None):
    """First existing candidate rig folder, else legacy path (even if missing)."""
    for p in _in_game_rig_wip_max_dirs(character, character_rig_root):
        if os.path.isdir(p):
            return p
    root = character_rig_root or DEFAULT_CHARACTER_RIG_ROOT
    character = _as_text(character)
    return os.path.join(root, character, character + u"_lod", u"wip", u"max")


def out_game_character_root(character, character_rig_root=None):
    root = character_rig_root or DEFAULT_CHARACTER_RIG_ROOT
    character = _as_text(character)
    return os.path.join(root, character)


def find_in_game_rigs(character, character_rig_root=None):
    out = []
    seen_path_lower = set()
    for folder in _in_game_rig_wip_max_dirs(character, character_rig_root):
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if not is_skin_binding_file(name, mode="in_game", character=character):
                continue
            path = os.path.join(folder, name)
            key = path.lower()
            if key in seen_path_lower:
                continue
            seen_path_lower.add(key)
            out.append({"path": path, "version": _parse_rig_version(path)})
    out.sort(key=lambda x: _version_number(x.get("version")), reverse=True)
    return out


def find_out_game_rigs(character, character_rig_root=None):
    character = _as_text(character)
    if not character:
        return []
    root = out_game_character_root(character, character_rig_root)
    if not os.path.isdir(root):
        root = character_rig_root or DEFAULT_CHARACTER_RIG_ROOT
    if not os.path.isdir(root):
        return []
    out = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", ".cursor", "_RigUpdateBackup", "_RigUpdatePackages", "_RigUpdateReports")]
        for name in files:
            if is_skin_binding_file(name, mode="out_game", character=character):
                path = os.path.join(current, name)
                out.append({"path": path, "version": _parse_rig_version(path)})
    out.sort(key=lambda x: _version_number(x.get("version")), reverse=True)
    return out


def find_target_in_game_rig(character, old_version=u"v01", character_rig_root=None):
    rigs = find_in_game_rigs(character, character_rig_root)
    if not rigs:
        return {"ok": False, "message": u"未找到角色绑定目录或绑定文件", "path": u"", "version": u"", "candidates": []}
    old_num = _version_number(old_version)
    newer = [x for x in rigs if _version_number(x.get("version")) > old_num]
    chosen = newer[0] if newer else rigs[0]
    return {
        "ok": True,
        "message": u"",
        "path": chosen.get("path", u""),
        "version": chosen.get("version", u""),
        "candidates": rigs,
    }


def find_target_out_game_rig(character, old_version=u"v01", character_rig_root=None):
    rigs = find_out_game_rigs(character, character_rig_root)
    if not rigs:
        return {"ok": False, "message": u"未找到局外角色绑定文件", "path": u"", "version": u"", "candidates": []}
    old_num = _version_number(old_version)
    newer = [x for x in rigs if _version_number(x.get("version")) > old_num]
    chosen = newer[0] if newer else rigs[0]
    return {
        "ok": True,
        "message": u"",
        "path": chosen.get("path", u""),
        "version": chosen.get("version", u""),
        "candidates": rigs,
    }


def _archived_skin_binding_file(path_or_name, mode=None, character=None):
    name = os.path.basename(_as_text(path_or_name))
    lower = name.lower()
    if not lower.endswith(".max") or "_skin_v" not in lower:
        return False
    character = _as_text(character).lower()
    tokens = _name_tokens(name)
    if character and (len(tokens) < 2 or tokens[1] != character):
        return False
    if mode == "in_game" and "_lod_skin_v" not in lower:
        return False
    if mode == "out_game" and "_cs_skin_v" not in lower:
        return False
    return bool(_parse_rig_version(name))


def find_source_binding_rig(character, version, mode=None, character_rig_root=None,
                            target_rig_path=None):
    """Find the neutral binding for an animation's recorded version.

    Active WIP bindings are preferred.  Timestamped copies under
    _RigUpdateBackup are accepted so an old animation can be retargeted without
    asking artists to maintain a Vxx-Vyy mapping file.
    """
    wanted = _as_text(version).lower()
    if not character or not wanted:
        return {"ok": False, "path": u"", "version": version, "candidates": []}

    roots = []
    if target_rig_path:
        target_dir = os.path.dirname(os.path.abspath(_as_text(target_rig_path)))
        roots.extend([target_dir, os.path.join(target_dir, "_RigUpdateBackup")])
    if mode == "in_game":
        for folder in _in_game_rig_wip_max_dirs(character, character_rig_root):
            roots.extend([folder, os.path.join(folder, "_RigUpdateBackup")])
    else:
        roots.append(out_game_character_root(character, character_rig_root))

    seen_roots = set()
    candidates = []
    seen_paths = set()
    for root in roots:
        root = os.path.abspath(_as_text(root))
        root_key = root.lower()
        if root_key in seen_roots or not os.path.isdir(root):
            continue
        seen_roots.add(root_key)
        for current, dirs, files in os.walk(root):
            dirs[:] = [item for item in dirs if item not in (".git", ".cursor", "_RigUpdatePackages", "_RigUpdateReports")]
            for name in files:
                path = os.path.join(current, name)
                if not _archived_skin_binding_file(path, mode=mode, character=character):
                    continue
                if _parse_rig_version(path).lower() != wanted:
                    continue
                key = os.path.normcase(os.path.abspath(path))
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                lower = path.lower()
                score = 0
                if "_rigupdatebackup" not in lower:
                    score += 100
                if "opstd" not in lower:
                    score += 20
                try:
                    modified = os.path.getmtime(path)
                except Exception:
                    modified = 0.0
                candidates.append({"path": path, "version": _parse_rig_version(path), "score": score, "modified": modified})

    candidates.sort(key=lambda item: (item.get("score", 0), item.get("modified", 0.0)), reverse=True)
    chosen = candidates[0] if candidates else {}
    return {
        "ok": bool(chosen),
        "path": chosen.get("path", u""),
        "version": chosen.get("version", version),
        "candidates": candidates,
        "message": u"" if chosen else u"未找到当前动画版本对应的中性绑定参考",
    }

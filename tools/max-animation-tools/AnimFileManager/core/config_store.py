# -*- coding: utf-8 -*-
"""配置读写：本地路径、已刷新角色。"""
from __future__ import division
import io
import json
import os

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INSTALL_ROOT = os.path.dirname(_TOOL_DIR)
_USER_CONFIG_NAME = u"afm_user_config.json"
_LEGACY_CONFIG_PATH = os.path.join(_TOOL_DIR, u"config", u"afm_config.json")

DEFAULT_CONFIG = {
    u"local_root": u"",
    u"refreshed_characters": [],
    u"display_mode": u"simple",
    u"last_source_tab": u"public",
    u"last_combat_tab": u"indoor",
    u"open_public_sync_to_local": False,
}

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


def _user_config_path():
    """用户配置放在安装根目录，避免开发同步覆盖。"""
    return os.path.join(_INSTALL_ROOT, _USER_CONFIG_NAME)


def _read_json(path):
    cfg = {}
    try:
        if os.path.exists(path):
            with io.open(path, u"r", encoding=u"utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    cfg = loaded
    except Exception:
        pass
    return cfg


def _migrate_legacy_config(user_path):
    if os.path.isfile(user_path):
        return
    legacy = _read_json(_LEGACY_CONFIG_PATH)
    if not legacy:
        return
    try:
        data = json.dumps(legacy, ensure_ascii=False, indent=2)
        with io.open(user_path, u"w", encoding=u"utf-8") as f:
            f.write(_as_text(data))
    except Exception:
        pass


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    user_path = _user_config_path()
    _migrate_legacy_config(user_path)
    loaded = _read_json(user_path)
    if loaded:
        cfg.update(loaded)
    return cfg


def save_config(cfg):
    user_path = _user_config_path()
    try:
        data = json.dumps(cfg, ensure_ascii=False, indent=2)
        with io.open(user_path, u"w", encoding=u"utf-8") as f:
            f.write(_as_text(data))
        return True
    except Exception:
        return False


def char_refresh_key(combat_folder, category, character):
    return u"{0}|{1}|{2}".format(
        _as_text(combat_folder), _as_text(category), _as_text(character)
    )


def is_character_refreshed(cfg, combat_folder, category, character):
    key = char_refresh_key(combat_folder, category, character)
    return key in (cfg.get(u"refreshed_characters") or [])


def mark_character_refreshed(cfg, combat_folder, category, character):
    key = char_refresh_key(combat_folder, category, character)
    refreshed = list(cfg.get(u"refreshed_characters") or [])
    if key not in refreshed:
        refreshed.append(key)
    cfg[u"refreshed_characters"] = refreshed
    save_config(cfg)
    return cfg

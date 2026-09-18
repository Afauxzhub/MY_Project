# -*- coding: utf-8 -*-
"""共享 rm_config.json 读写，供独立工具窗口与主窗口共用。"""
from __future__ import print_function
import io
import json
import os

try:
    _text_type = unicode
except NameError:
    _text_type = str

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_TOOL_DIR, u"config", u"rm_config.json")

DEFAULT_CONFIG = {
    u"unity_root": u"",
    u"nas_base": u"",
    u"error_report_root": u"",
    u"character_rig_root": u"",
    u"rig_update_cleanup_packages": False,
    u"rig_update_keep_reports": True,
    u"rig_update_ignore_non_bip_errors": False,
    u"rig_update_skip_missing_constraint_targets": False,
    u"rig_update_allow_preflight_blockers": False,
    u"rig_update_outgame_characters": [],
    u"dev_machine_marker_filename": u"AnimationTools_DevMachine.flag",
    u"dev_machine_project_override": u"",
    u"auto_copy_unity": True,
    u"auto_backup_nas": False,
    u"auto_focus_unity": True,
    u"open_folder_after_export": True,
    u"backup_stage": u"初版",
    u"backup_version": u"",
    u"publisher_name": u"",
    u"adv_force_keys": True,
    u"adv_fix_rot": True,
    u"adv_remove_initial_z": True,
    u"adv_unlock_nodes": True,
    u"adv_delete_temp_file": True,
    u"adv_root_motion_debug_log": False,
    u"adv_export_weapon_state_mapping": True,
    u"category_folder_map": {
        u"Role": u"Role",
        u"Monster": u"Monster",
        u"Elite": u"Elite",
        u"Boss": u"Boss",
        u"Npc": u"Npc",
        u"Scene": u"Scene",
    },
    u"module_folder_map": {
        u"UL": u"Ultimate_skill",
        u"EN": u"Entrance",
        u"RE": u"Result",
        u"GA": u"Gacha",
        u"DE": u"Development",
        u"ER": u"Enrage",
        u"CS": u"Cinematic",
        u"QTE": u"QTE",
        u"DI": u"Dialogue",
    },
    u"module_tag_map": {
        u"UL": u"角色配套",
        u"GA": u"角色配套",
        u"DE": u"角色配套",
        u"ER": u"角色配套",
        u"EN": u"剧情对话",
        u"RE": u"剧情对话",
        u"CS": u"剧情对话",
        u"QTE": u"剧情对话",
        u"DI": u"剧情对话",
    },
    u"outdoor_type_folder_map": {
        u"Role": u"Role",
        u"Monster": u"Monster",
    },
    u"outdoor_asset_types": [u"Char", u"Prop", u"Cam"],
}


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_PATH):
            with io.open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cfg.update(loaded)
    except Exception as e:
        print(u"[RMTool] 配置读取失败，使用默认配置: {0}".format(_as_text(e)))
    return cfg


def save_config(config):
    try:
        config_dir = os.path.dirname(CONFIG_PATH)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        tmp_path = CONFIG_PATH + u".tmp"
        data = json.dumps(config, ensure_ascii=False, indent=2)
        with io.open(tmp_path, "w", encoding="utf-8") as f:
            f.write(_as_text(data))
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)
        os.rename(tmp_path, CONFIG_PATH)
        return True
    except Exception as e:
        print(u"[RMTool] 配置保存失败: {0}".format(_as_text(e)))
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False

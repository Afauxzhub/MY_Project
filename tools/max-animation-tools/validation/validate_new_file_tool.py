# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RM_ROOT = os.path.join(ROOT, "RootMotionTool")
if RM_ROOT not in sys.path:
    sys.path.insert(0, RM_ROOT)

from pipeline.new_file_service import (
    build_camera_options,
    build_chapter_options,
    build_indoor_destination,
    build_outdoor_destination,
    build_scene_options,
    chapter_code_from_label,
    compose_indoor_filename,
    compose_outdoor_dialogue_filename,
    compose_outdoor_role_filename,
    copy_binding_to_destination,
    find_indoor_binding_files,
    find_outdoor_binding_files,
    load_anim_file_manager_config,
    normalize_name_part,
    scene_code_from_label,
    validate_name_part,
)
from pipeline.rm_naming import (
    MODULE_TAG_ROLE_SUPPORT,
    MODULE_TAG_STORY_DIALOGUE,
    build_outdoor_camera_export_name,
    build_outdoor_character_export_name,
    merge_module_tag_map,
    module_codes_for_tag,
    parse_outdoor_source_name,
    validate_indoor_name,
    validate_outdoor_name,
)


def _write(path, text=u""):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(text.decode("utf-8") if isinstance(text, bytes) else text)


def main():
    assert normalize_name_part(u" hero ") == u"Hero"
    assert validate_name_part(u"skill01", u"动作名称")[0]
    assert not validate_name_part(u"Skill_01", u"动作名称")[0]
    assert compose_indoor_filename(u"Role", u"hero", u"skill01") == (
        u"Role_Hero_Skill01.max"
    )
    assert build_camera_options(3) == [u"Cam01", u"Cam02", u"Cam03"]
    assert build_chapter_options(3) == [u"Chapter01", u"Chapter02", u"Chapter03"]
    assert build_scene_options(3) == [u"Scene01", u"Scene02", u"Scene03"]
    assert chapter_code_from_label(u"Chapter01") == u"Chap01"
    assert scene_code_from_label(u"Scene01") == u"SC01"
    assert compose_outdoor_dialogue_filename(
        u"DI", u"Chapter01", u"Scene01", u"Cam01"
    ) == u"DI_Chap01_SC01_Cam01.max"
    assert compose_outdoor_role_filename(
        u"UL", u"Role", u"hero", u"Cam01"
    ) == u"UL_Role_Hero_Cam01.max"
    expected = os.path.normpath(
        os.path.join(
            u"D:\\AnimWork", u"局内战斗备份", u"Role", u"Hero",
            u"监修", u"2.0", u"Role_Hero_Skill01.max"
        )
    )
    assert build_indoor_destination(
        u"D:\\AnimWork", u"Role", u"hero", u"监修", u"2.0",
        u"Role_Hero_Skill01.max"
    ) == expected
    valid, _, renamed_indoor = validate_indoor_name(
        u"Elite_CreatureMinionA_Jump", {u"Elite": u"Elite"}
    )
    assert valid and renamed_indoor[u"char_name"] == u"CreatureMinionA"
    renamed_expected = os.path.normpath(os.path.join(
        u"D:\\AnimWork", u"局内战斗备份", u"Elite",
        u"CreatureMinionA", u"初版",
        u"Elite_CreatureMinionA_Jump.max"
    ))
    assert build_indoor_destination(
        u"D:\\AnimWork",
        renamed_indoor[u"category"],
        renamed_indoor[u"char_name"],
        u"初版",
        u"",
        u"Elite_CreatureMinionA_Jump.max",
    ) == renamed_expected
    outdoor_expected = os.path.normpath(os.path.join(
        u"D:\\AnimWork", u"局外演出备份", u"Ultimate_skill", u"Role",
        u"Hero", u"初版", u"UL_Role_Hero_Cam01.max"
    ))
    assert build_outdoor_destination(
        u"D:\\AnimWork", u"Ultimate_skill", u"Role", u"hero", u"初版", u"",
        u"UL_Role_Hero_Cam01.max"
    ) == outdoor_expected
    dialogue_expected = os.path.normpath(os.path.join(
        u"D:\\AnimWork", u"局外演出备份", u"Dialogue", u"Chapter01",
        u"Scene01", u"初版", u"DI_Chap01_SC01_Cam01.max"
    ))
    assert build_outdoor_destination(
        u"D:\\AnimWork", u"Dialogue", u"Chapter01", u"Scene01",
        u"初版", u"", u"DI_Chap01_SC01_Cam01.max"
    ) == dialogue_expected

    module_map = {u"UL": u"Ultimate_skill", u"DI": u"Dialogue"}
    tags = merge_module_tag_map(module_map, {})
    assert u"UL" in module_codes_for_tag(
        module_map, tags, MODULE_TAG_ROLE_SUPPORT
    )
    assert u"DI" in module_codes_for_tag(
        module_map, tags, MODULE_TAG_STORY_DIALOGUE
    )
    valid, _, parsed = validate_outdoor_name(
        u"UL_Boss_Hero_Cam01", module_map, {}, [u"Char", u"Cam"],
        {u"Boss": u"Boss"}
    )
    assert valid and parsed[u"shot_name"] == u"Cam01"
    valid, _, parsed = validate_outdoor_name(
        u"DI_Chap01_SC01_Cam01", module_map
    )
    assert valid and parsed[u"compact_dialogue"] and parsed[u"shot_name"] == u"Cam01"
    valid, _, source_info = parse_outdoor_source_name(
        u"DI_Chap01_SC01_Cam01.max", module_map
    )
    assert valid and source_info[u"type_folder"] == u"Chapter01"
    assert source_info[u"char_folder"] == u"Scene01"
    assert build_outdoor_character_export_name(
        source_info, u"Hero", u"Char"
    ) == u"DI_Chap01_SC01_Hero_Cam01"
    assert build_outdoor_character_export_name(
        source_info, u"Rival", u"Char"
    ) == u"DI_Chap01_SC01_Rival_Cam01"
    assert build_outdoor_camera_export_name(source_info) == (
        u"DI_Chap01_SC01_Cam_Cam01"
    )
    valid, _, old_compact = parse_outdoor_source_name(
        u"DI_Chap01_SC01.max", module_map
    )
    assert valid and old_compact[u"compact_dialogue"]
    valid, _, legacy_dialogue = parse_outdoor_source_name(
        u"DI_Chap02_SC01_Mihawk_Idle01.max", module_map
    )
    assert valid and legacy_dialogue[u"dialogue_character"] == u"Mihawk"
    assert build_outdoor_character_export_name(
        legacy_dialogue, u"Mihawk", u"Char"
    ) == u"DI_Chap02_SC01_Mihawk_Idle01"

    temp_root = tempfile.mkdtemp(prefix="op_new_file_")
    try:
        legacy = os.path.join(temp_root, "AnimFileManager", "config", "afm_config.json")
        user = os.path.join(temp_root, "afm_user_config.json")
        _write(legacy, json.dumps({"local_root": "D:/Legacy"}, ensure_ascii=False))
        _write(user, json.dumps({"local_root": "D:/Current"}, ensure_ascii=False))
        assert load_anim_file_manager_config(temp_root)["local_root"] == "D:/Current"

        rig_dir = os.path.join(
            temp_root, "Hero", "Role_Hero_lod", "wip", "max"
        )
        _write(os.path.join(rig_dir, "Role_Hero_lod_skin_V01.max"), u"v1")
        _write(os.path.join(rig_dir, "Role_Hero_lod_skin_V02.max"), u"v2")
        rigs = find_indoor_binding_files(u"hero", temp_root, category=u"Role")
        assert [item["version"] for item in rigs] == [u"v02", u"v01"]
        fallback_rigs = find_indoor_binding_files(u"hero", temp_root, category=u"Boss")
        assert [item["version"] for item in fallback_rigs] == [u"v02", u"v01"]
        boss_dir = os.path.join(
            temp_root, "Hero", "Boss_Hero_lod", "wip", "max"
        )
        _write(os.path.join(boss_dir, "Boss_Hero_lod_skin_V01.max"), u"boss")
        boss_rigs = find_indoor_binding_files(u"hero", temp_root, category=u"Boss")
        assert len(boss_rigs) == 1
        assert os.path.basename(boss_rigs[0]["path"]).startswith("Boss_Hero_")
        custom_dir = os.path.join(
            temp_root, "Hero", "Hero_Hero_lod", "wip", "max"
        )
        _write(os.path.join(custom_dir, "Hero_Hero_lod_skin_V03.max"), u"v3")
        custom_rigs = find_indoor_binding_files(
            u"hero", temp_root, category=u"Hero"
        )
        assert [item["version"] for item in custom_rigs] == [u"v03"]
        all_category_rigs = find_indoor_binding_files(
            u"hero", temp_root, category=u"Npc"
        )
        assert set([
            os.path.basename(item["path"]).split("_")[0]
            for item in all_category_rigs
        ]) == set(["Role", "Boss", "Hero"])

        cs_dir = os.path.join(temp_root, "Hero", "Role_Hero_cs", "wip", "max")
        _write(os.path.join(cs_dir, "Role_Hero_cs_skin_V01.max"), u"v1")
        _write(os.path.join(cs_dir, "Role_Hero_cs_skin_V04.max"), u"v4")
        cs_rigs = find_outdoor_binding_files(u"hero", temp_root, category=u"Role")
        assert [item["version"] for item in cs_rigs] == [u"v04", u"v01"]
        cs_fallback = find_outdoor_binding_files(u"hero", temp_root, category=u"Npc")
        assert [item["version"] for item in cs_fallback] == [u"v04", u"v01"]
        npc_cs_dir = os.path.join(temp_root, "Hero", "Npc_Hero_cs", "wip", "max")
        _write(os.path.join(npc_cs_dir, "Npc_Hero_cs_skin_V02.max"), u"npc")
        npc_cs = find_outdoor_binding_files(u"hero", temp_root, category=u"Npc")
        assert len(npc_cs) == 1
        assert os.path.basename(npc_cs[0]["path"]).startswith("Npc_Hero_")

        source = os.path.join(temp_root, "source.max")
        destination = os.path.join(temp_root, "new", "Role_Hero_Run.max")
        _write(source, u"binding")
        ok, result = copy_binding_to_destination(source, destination)
        assert ok and result == destination and os.path.isfile(destination)
        ok, message = copy_binding_to_destination(source, destination)
        assert not ok and u"不会覆盖" in message
    finally:
        shutil.rmtree(temp_root)

    menu_path = os.path.join(ROOT, "maxscript", "PiToolsMenu.ms")
    hub_path = os.path.join(ROOT, "RootMotionTool", "op_tools_hub.py")
    with io.open(menu_path, "r", encoding="utf-8-sig") as stream:
        menu_source = stream.read()
    with io.open(hub_path, "r", encoding="utf-8-sig") as stream:
        hub_source = stream.read()
    dialog_path = os.path.join(
        ROOT, "RootMotionTool", "ui", "rm_new_file_dialog.py"
    )
    with io.open(dialog_path, "r", encoding="utf-8-sig") as stream:
        dialog_source = stream.read()
    new_item = u'("PiTools_NewFile", "新建文件", "open_new_file_tool")'
    open_item = u'("PiTools_OpenFile", "打开文件", "open_file_manager")'
    assert new_item in menu_source and menu_source.index(new_item) < menu_source.index(open_item)
    assert "def open_new_file_tool():" in hub_source
    for required_text in (
        u"局内", u"局外", u"角色分类：", u"角色名称：", u"绑定文件：",
        u"动作名称：", u"文件阶段：", u"文件路径：", u"文件作者：", u"确认创建",
        u"角色配套", u"剧情对话", u"模块名称：", u"CS 绑定：", u"镜头编号：",
        u"章节编号：", u"场次编号：", u"添加角色", u"移除选中角色",
        u"确认创建并合并角色", u"mergeMAXFile", u"#autoRenameDups",
        u"QScrollArea", u"ScrollBarAsNeeded",
        u"setMinimumHeight(max(600, content.sizeHint().height()))",
        u"_dialogue_camera_combo",
    ):
        assert required_text in dialog_source
    assert u"新建日期" not in dialog_source
    for editable_name in (
        u"self._filename_edit", u"self._out_filename_edit",
        u"self._dialogue_filename_edit",
    ):
        assert editable_name + u".setReadOnly(True)" not in dialog_source
    for required_logic in (
        u"_set_generated_filename", u"_sync_filename_to_path",
        u"_validate_preview_filename", u"文件路径末尾必须与文件名称一致",
        u'parsed.get(u"char_name", path_character)',
        u'parsed.get(u"char_folder", character_folder)',
    ):
        assert required_logic in dialog_source
    for module_label in (u"Ultimate", u"Gacha", u"Development", u"Enrage"):
        assert u'": u"{0}"'.format(module_label) in dialog_source
    for removed_label in (
        u"奥义 Ultimate - UL", u"抽卡 Gacha - GA",
        u"养成 Development - DE", u"Boss转阶段 Enrage - ER",
    ):
        assert removed_label not in dialog_source
    settings_path = os.path.join(
        ROOT, "RootMotionTool", "ui", "rm_settings_dialog.py"
    )
    with io.open(settings_path, "r", encoding="utf-8-sig") as stream:
        settings_source = stream.read()
    assert u"模块标签" in settings_source
    assert u'module_tag_map' in settings_source
    print("NEW_FILE_TOOL_VALIDATION_OK")


if __name__ == "__main__":
    main()

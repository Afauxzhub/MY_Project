# -*- coding: utf-8 -*-
"""角色级发布阶段扫描、跨度规则和 UI 契约静态回归。"""
from __future__ import print_function
import io
import os
import shutil
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RM_ROOT = os.path.join(ROOT, "RootMotionTool")


def _write(path, text=u""):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(text)


def _read(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return stream.read()


def main():
    sys.path.insert(0, RM_ROOT)
    from pipeline.publish_public_lookup import (
        build_review_version_options,
        classify_publish_stage,
        find_latest_character_stage,
        make_stage_state,
    )

    options = build_review_version_options()
    assert options[:4] == [u"1.0", u"2.0", u"3.0", u"4.0"]
    assert options[-1] == u"99.0"

    assert classify_publish_stage(u"初版", u"", None) == u"normal"
    assert classify_publish_stage(u"终版", u"", None) == u"unpublished_non_initial"
    assert classify_publish_stage(u"监修", u"1.0", None) == u"unpublished_non_initial"

    initial = make_stage_state(u"初版")
    final = make_stage_state(u"终版")
    review_one = make_stage_state(u"监修", u"1.0")
    review_two = make_stage_state(u"监修", u"2.0")
    review_three = make_stage_state(u"监修", u"3.0")
    assert classify_publish_stage(u"终版", u"", initial) == u"normal"
    assert classify_publish_stage(u"监修", u"1.0", final) == u"normal"
    assert classify_publish_stage(u"监修", u"2.0", final) == u"too_far_ahead"
    assert classify_publish_stage(u"监修", u"2.0", review_one) == u"normal"
    assert classify_publish_stage(u"监修", u"3.0", review_one) == u"too_far_ahead"
    assert classify_publish_stage(u"监修", u"2.0", review_three) == u"earlier"
    assert classify_publish_stage(u"终版", u"", review_two) == u"earlier"

    temp_root = tempfile.mkdtemp(prefix="op_publish_stage_")
    try:
        char_root = os.path.join(temp_root, "Role", "Hero")
        assert find_latest_character_stage(char_root) is None
        _write(os.path.join(char_root, u"初版", "Role_Hero_Idle.max"))
        assert find_latest_character_stage(char_root)[u"label"] == u"初版"
        _write(os.path.join(char_root, u"终版", "Role_Hero_Run.max"))
        assert find_latest_character_stage(char_root)[u"label"] == u"终版"
        _write(os.path.join(char_root, u"监修", u"1.0", "Role_Hero_Skill01.max"))
        assert find_latest_character_stage(char_root)[u"label"] == u"监修1.0"
        _write(os.path.join(char_root, u"监修", u"3.0", "Role_Hero_Skill02.max"))
        assert find_latest_character_stage(char_root)[u"label"] == u"监修3.0"
        _write(os.path.join(
            char_root, u"监修", u"99.0", u"发布备份", "Role_Hero_Old.max"
        ))
        assert find_latest_character_stage(char_root)[u"label"] == u"监修3.0"
    finally:
        shutil.rmtree(temp_root)

    settings_source = _read(os.path.join(RM_ROOT, "ui", "rm_settings_dialog.py"))
    confirm_source = _read(os.path.join(RM_ROOT, "ui", "rm_publish_confirm_dialog.py"))
    legacy_stage_source = _read(os.path.join(RM_ROOT, "ui", "rm_stage_dialog.py"))
    main_source = _read(os.path.join(RM_ROOT, "ui", "rm_main_window.py"))
    assert "_backup_version_edit" not in settings_source
    assert "_backup_version_combo.setEditable(False)" in settings_source
    assert "_backup_version_combo.setCurrentIndex(-1)" in settings_source
    assert "_version_combo.setEditable(False)" in confirm_source
    assert u"当前角色阶段" in confirm_source
    assert u"角色阶段按公盘该角色目录中所有动作" not in confirm_source
    assert "color: #4fc3f7" not in confirm_source
    assert u"本次发布阶段：" in confirm_source
    assert u"监修子版本号：" in confirm_source
    assert "form.setVerticalSpacing(8)" in confirm_source
    assert "row_font.setPointSize(10)" in confirm_source
    assert "form.setLabelAlignment(QtCore.Qt.AlignLeft" in confirm_source
    assert u'QtWidgets.QPushButton(u"取消")' in confirm_source
    assert u'QtWidgets.QPushButton(u"发布")' in confirm_source
    assert "button_row.addStretch(1)" in confirm_source
    assert u"忽略警告" in confirm_source
    assert u"取消发布" in confirm_source
    assert "_version_combo.setEditable(False)" in legacy_stage_source
    assert "_version_combo.setCurrentIndex(-1)" in legacy_stage_source
    assert "find_latest_character_stage(char_root)" in main_source
    assert "find_latest_public_stage_label(char_root, match_key)" not in main_source

    for rel in (
        "pipeline/publish_public_lookup.py",
        "ui/rm_settings_dialog.py",
        "ui/rm_publish_confirm_dialog.py",
        "ui/rm_stage_dialog.py",
        "ui/rm_main_window.py",
    ):
        path = os.path.join(RM_ROOT, rel.replace("/", os.sep))
        compile(_read(path).encode("utf-8"), path, "exec")

    print("PUBLISH_STAGE_POLICY_VALIDATION_OK")


if __name__ == "__main__":
    main()

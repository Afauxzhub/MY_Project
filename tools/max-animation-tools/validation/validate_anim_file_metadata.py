# -*- coding: utf-8 -*-
"""动画文件管理器发布元数据与双候选解析静态回归。"""
from __future__ import print_function
import io
import json
import os
import shutil
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AFM_ROOT = os.path.join(ROOT, "AnimFileManager")
RM_ROOT = os.path.join(ROOT, "RootMotionTool")


def _write(path, text=u""):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(text)


def _write_settings(
    max_path, publisher, published_at, stage, stage_version=u"",
    publish_revision=0,
):
    stem = os.path.splitext(os.path.basename(max_path))[0]
    path = os.path.join(os.path.dirname(max_path), u"发布设置", stem + u".json")
    data = {
        u"publish_metadata": {
            u"publisher": publisher,
            u"published_at": published_at,
            u"stage": stage,
            u"stage_version": stage_version,
            u"publish_revision": publish_revision,
        }
    }
    _write(path, json.dumps(data, ensure_ascii=False, indent=2))


def main():
    sys.path.insert(0, AFM_ROOT)
    from core.publish_history import load_publish_history
    from core.public_updates import (
        annotate_local_files_with_public_updates,
        public_choice_label,
    )
    from core.version_resolver import resolve_latest_max_files
    from core.file_scanner import build_full_tree, list_full_dir_entries

    temp_root = tempfile.mkdtemp(prefix="op_afm_metadata_")
    try:
        char_root = os.path.join(temp_root, "Role", "Hero")
        final_path = os.path.join(char_root, u"终版", "Role_Hero_Skill01.max")
        review_path = os.path.join(char_root, u"监修", "2.0", "Role_Hero_Skill01.max")
        _write(final_path)
        _write(review_path)
        _write_settings(final_path, u"测试者", u"2026-09-01T12:00:00", u"终版")
        _write_settings(review_path, u"李明", u"2026-08-01T12:00:00", u"监修", u"2.0")

        rows = resolve_latest_max_files(char_root)
        assert len(rows) == 2, rows
        assert set([row[u"path"] for row in rows]) == set([final_path, review_path])
        final_row = [row for row in rows if row[u"path"] == final_path][0]
        assert final_row[u"display_name"] == u"Role_Hero_Skill01[26.09.01][测试者][终版][V001]"

        _write_settings(review_path, u"李明", u"2026-09-02T12:00:00", u"监修", u"2.0")
        rows = resolve_latest_max_files(char_root)
        assert len(rows) == 1, rows
        assert rows[0][u"path"] == review_path
        assert rows[0][u"version_label"] == u"监修2.0"

        legacy_path = os.path.join(char_root, u"初版", "Role_Hero_Idle.max")
        _write(legacy_path)
        legacy_rows = [
            row for row in resolve_latest_max_files(char_root)
            if row[u"path"] == legacy_path
        ]
        assert len(legacy_rows) == 1
        assert legacy_rows[0][u"publisher"] == u"未设置"
        assert legacy_rows[0][u"version_label"] == u"初版"
        assert not legacy_rows[0][u"date_label"].startswith(u"V")
        assert legacy_rows[0][u"publish_revision_label"] == u"V001"
        assert legacy_rows[0][u"implicit_publish_revision"] is True
        legacy_history = load_publish_history(legacy_path)
        assert len(legacy_history) == 1
        assert legacy_history[0][u"publish_revision_label"] == u"V001"
        assert legacy_history[0][u"implicit_legacy"] is True
        assert legacy_history[0][u"open_path"] == legacy_path

        tree = build_full_tree(char_root)
        stack = [tree]
        file_nodes = []
        while stack:
            node = stack.pop()
            if node.get(u"type") == u"file":
                file_nodes.append(node)
            stack.extend(node.get(u"children", []))
        assert len(file_nodes) == 3
        assert all([node.get(u"metadata", {}).get(u"publisher") for node in file_nodes])

        review_entries = list_full_dir_entries(os.path.dirname(review_path))
        assert len(review_entries) == 1
        assert review_entries[0][u"metadata"][u"version_label"] == u"监修2.0"

        # 本地更新提示：阶段最新和日期最新分别命中不同公盘文件。
        local_char = os.path.join(temp_root, "local", "Role", "Hero")
        public_char = os.path.join(temp_root, "public", "Role", "Hero")
        local_conflict = os.path.join(
            local_char, u"监修", u"2.0", "Role_Hero_Conflict.max"
        )
        public_stage_latest = os.path.join(
            public_char, u"监修", u"3.0", "Role_Hero_Conflict.max"
        )
        public_date_latest = os.path.join(
            public_char, u"初版", "Role_Hero_Conflict.max"
        )
        for path in (local_conflict, public_stage_latest, public_date_latest):
            _write(path)
        _write_settings(
            local_conflict, u"本地", u"2026-08-20T10:00:00", u"监修", u"2.0", 1
        )
        _write_settings(
            public_stage_latest, u"甲", u"2026-08-10T09:00:00", u"监修", u"3.0", 2
        )
        _write_settings(
            public_date_latest, u"乙", u"2026-09-01T12:30:00", u"初版", u"", 3
        )
        local_rows = resolve_latest_max_files(local_char)
        annotate_local_files_with_public_updates(
            local_rows, public_char
        )
        conflict_update = local_rows[0][u"public_update"]
        assert local_rows[0][u"public_update_available"] is True
        assert conflict_update[u"conflict"] is True
        assert conflict_update[u"stage_latest"][u"path"] == public_stage_latest
        assert conflict_update[u"date_latest"][u"path"] == public_date_latest
        assert u"2026-08-10 09:00:00" in public_choice_label(
            u"阶段最新", conflict_update[u"stage_latest"]
        )
        assert u"[监修3.0]" in public_choice_label(
            u"阶段最新", conflict_update[u"stage_latest"]
        )

        # 同阶段日期更新时只有一个默认候选；完全相同则不提示。
        local_direct = os.path.join(local_char, u"初版", "Role_Hero_Direct.max")
        public_direct = os.path.join(public_char, u"初版", "Role_Hero_Direct.max")
        local_same = os.path.join(local_char, u"终版", "Role_Hero_Same.max")
        public_same = os.path.join(public_char, u"终版", "Role_Hero_Same.max")
        for path in (local_direct, public_direct, local_same, public_same):
            _write(path)
        _write_settings(local_direct, u"甲", u"2026-09-01T08:00:00", u"初版", u"", 1)
        _write_settings(public_direct, u"乙", u"2026-09-02T08:00:00", u"初版", u"", 2)
        _write_settings(local_same, u"甲", u"2026-09-03T08:00:00", u"终版", u"", 2)
        _write_settings(public_same, u"甲", u"2026-09-03T08:00:00", u"终版", u"", 2)
        local_rows = resolve_latest_max_files(local_char)
        annotate_local_files_with_public_updates(
            local_rows, public_char
        )
        by_name = dict([(x[u"name"], x) for x in local_rows])
        assert by_name[u"Role_Hero_Direct.max"][u"public_update_available"] is True
        assert by_name[u"Role_Hero_Direct.max"][u"public_update"][u"conflict"] is False
        assert by_name[u"Role_Hero_Same.max"][u"public_update_available"] is False

        # 公盘低阶段但日期更新仍提示；公盘高阶段但日期更旧也提示。
        local_lower_date = os.path.join(
            local_char, u"监修", u"2.0", "Role_Hero_LowerDate.max"
        )
        public_lower_date = os.path.join(
            public_char, u"初版", "Role_Hero_LowerDate.max"
        )
        local_higher_stage = os.path.join(
            local_char, u"初版", "Role_Hero_HigherStage.max"
        )
        public_higher_stage = os.path.join(
            public_char, u"终版", "Role_Hero_HigherStage.max"
        )
        for path in (
            local_lower_date, public_lower_date,
            local_higher_stage, public_higher_stage,
        ):
            _write(path)
        _write_settings(
            local_lower_date, u"甲", u"2026-08-20T10:00:00", u"监修", u"2.0", 1
        )
        _write_settings(
            public_lower_date, u"乙", u"2026-09-01T10:00:00", u"初版", u"", 1
        )
        _write_settings(
            local_higher_stage, u"甲", u"2026-09-01T10:00:00", u"初版", u"", 1
        )
        _write_settings(
            public_higher_stage, u"乙", u"2026-08-01T10:00:00", u"终版", u"", 1
        )
        local_rows = resolve_latest_max_files(local_char)
        annotate_local_files_with_public_updates(local_rows, public_char)
        by_name = dict([(x[u"name"], x) for x in local_rows])
        assert by_name[u"Role_Hero_LowerDate.max"][u"public_update_available"] is True
        assert by_name[u"Role_Hero_HigherStage.max"][u"public_update_available"] is True

        # 新发布设置结构不依赖 Max/PySide，可在普通 Python 下验证。
        sys.path.insert(0, RM_ROOT)
        from pipeline.publish_settings import attach_publish_metadata
        payload = attach_publish_metadata(
            {u"publish_type": u"indoor"},
            u"测试者",
            u"监修",
            u"2.0",
            published_at=u"2026-09-01T09:30:00",
        )
        assert payload[u"publish_metadata"][u"publisher"] == u"测试者"
        assert payload[u"publish_metadata"][u"stage_version"] == u"2.0"

        main_ui_path = os.path.join(AFM_ROOT, "ui", "afm_main_window.py")
        with io.open(main_ui_path, "r", encoding="utf-8") as stream:
            main_ui_source = stream.read()
        assert u"setMinimumSize(720, 480)" in main_ui_source
        assert u"setMinimumSize(1920, 1240)" not in main_ui_source
        assert u"QApplication.instance()" not in main_ui_source
        assert u"QApplication.desktop()" in main_ui_source
        full_ui_path = os.path.join(AFM_ROOT, "ui", "full_mode_widget.py")
        with io.open(full_ui_path, "r", encoding="utf-8") as stream:
            full_ui_source = stream.read()
        assert u"build_full_tree" not in full_ui_source
        assert u"itemExpanded.connect" in full_ui_source
        assert u"os.path.isdir(self._root_path)" not in full_ui_source
        simple_ui_path = os.path.join(AFM_ROOT, "ui", "simple_mode_widget.py")
        with io.open(simple_ui_path, "r", encoding="utf-8") as stream:
            simple_ui_source = stream.read()
        assert u"def set_view_context" in simple_ui_source
        assert u"reload_categories=False" in main_ui_source
        assert u"class _FileRowDelegate" in simple_ui_source
        assert u"ScrollBarAlwaysOff" in simple_ui_source
        assert u"ellipsis = u\"...\"" in simple_ui_source
        assert u"FILE_DATE_ROLE" in simple_ui_source
        assert u"FILE_OWNER_ROLE" in simple_ui_source
        assert u"FILE_VERSION_ROLE" in simple_ui_source
        assert u"FILE_REVISION_ROLE" in simple_ui_source
        assert u"FILE_UPDATE_ROLE" in simple_ui_source
        assert u"[公盘存在新版]" not in simple_ui_source
        assert u"UPDATE_MARKER" in simple_ui_source
        assert u"打开公盘最新版本" in main_ui_source
        assert u"阶段最新" in main_ui_source
        assert u"日期最新" in main_ui_source
        assert u"gap_width" in simple_ui_source
        assert u"setTextAlignment" in full_ui_source
        assert u"painter.drawText(version_rect, align_left" in simple_ui_source
        assert u"3, QtCore.Qt.AlignLeft" in full_ui_source
        print("ANIM_FILE_METADATA_VALIDATION_OK")
    finally:
        shutil.rmtree(temp_root)


if __name__ == "__main__":
    main()

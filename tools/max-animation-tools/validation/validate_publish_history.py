# -*- coding: utf-8 -*-
"""公盘发布次数、阶段计数、覆盖前备份与历史元数据回归。"""
from __future__ import print_function
import io
import os
import shutil
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RM_ROOT = os.path.join(ROOT, "RootMotionTool")
AFM_ROOT = os.path.join(ROOT, "AnimFileManager")


def _write(path, text):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(text)


def main():
    sys.path.insert(0, RM_ROOT)
    from pipeline.publish_settings import (
        load_publish_settings,
        merge_publish_settings_data,
        save_publish_settings,
    )
    from pipeline.rm_file_io import publish_max_to_nas_indoor

    temp_root = tempfile.mkdtemp(prefix="op_publish_history_")
    try:
        source = os.path.join(temp_root, "work", "Role_Hero_Run.max")
        nas_root = os.path.join(temp_root, "nas")
        _write(source, u"source-v1")
        ok, _msg = save_publish_settings(
            source, {u"publish_type": u"indoor", u"indoor": {u"enable_pos": True}}
        )
        assert ok

        first = publish_max_to_nas_indoor(
            source, u"Role", u"Hero", u"初版",
            nas_base=nas_root, publisher=u"测试者",
            published_at=u"2026-09-01T09:00:00",
        )
        assert first[u"publish_revision_label"] == u"V001"
        assert not first[u"archived_path"]
        first_payload = load_publish_settings(source)
        assert first_payload[u"publish_metadata"][u"publish_revision"] == 1
        assert len(first_payload[u"publish_history"]) == 1

        _write(source, u"source-v2")
        second = publish_max_to_nas_indoor(
            source, u"Role", u"Hero", u"初版",
            nas_base=nas_root, publisher=u"李明",
            published_at=u"2026-09-02T10:00:00",
        )
        assert second[u"publish_revision_label"] == u"V002"
        assert os.path.isfile(second[u"archived_path"])
        with io.open(second[u"archived_path"], "r", encoding="utf-8") as stream:
            assert stream.read() == u"source-v1"
        second_payload = load_publish_settings(source)
        assert len(second_payload[u"publish_history"]) == 2
        old_entry = [
            x for x in second_payload[u"publish_history"]
            if x[u"publish_revision"] == 1 and x[u"stage_scope"] == u"初版"
        ][0]
        assert old_entry[u"backup_path"] == second[u"archived_path"]

        final = publish_max_to_nas_indoor(
            source, u"Role", u"Hero", u"终版",
            nas_base=nas_root, publisher=u"李明",
            published_at=u"2026-09-03T10:00:00",
        )
        assert final[u"publish_revision_label"] == u"V001"

        monitor_results = []
        for index in range(1, 4):
            _write(source, u"monitor-1-{0}".format(index))
            monitor_results.append(publish_max_to_nas_indoor(
                source, u"Role", u"Hero", u"监修", version=u"1.0",
                nas_base=nas_root, publisher=u"测试者",
                published_at=u"2026-09-0{0}T12:00:00".format(index + 3),
            ))
        assert [x[u"publish_revision_label"] for x in monitor_results] == [
            u"V001", u"V002", u"V003"
        ]
        monitor_two = publish_max_to_nas_indoor(
            source, u"Role", u"Hero", u"监修", version=u"2.0",
            nas_base=nas_root, publisher=u"测试者",
            published_at=u"2026-09-07T12:00:00",
        )
        assert monitor_two[u"publish_revision_label"] == u"V004"

        # 本地保存面板选项只保留已有编号，不产生新的发布次数。
        before = load_publish_settings(source)[u"publish_metadata"][u"publish_revision"]
        panel_payload = merge_publish_settings_data(
            source, {u"indoor": {u"enable_pos": False}}
        )
        ok, _msg = save_publish_settings(source, panel_payload)
        assert ok
        after = load_publish_settings(source)[u"publish_metadata"][u"publish_revision"]
        assert before == after == 4

        # 用 AFM 读取最终展示，日期无 V 前缀并带独立发布次数。
        sys.path.insert(0, AFM_ROOT)
        from core.publish_metadata import read_publish_metadata
        from core.publish_history import load_publish_history
        metadata = read_publish_metadata(source)
        assert metadata[u"date_label"] == u"26.09.07"
        assert metadata[u"publish_revision_label"] == u"V004"
        assert metadata[u"display_name"].endswith(u"[V004]")
        history_rows = load_publish_history(source)
        assert len([x for x in history_rows if x[u"publish_revision"] > 0]) == 7
        assert any([
            x[u"publish_revision_label"] == u"V003" and x[u"available"]
            for x in history_rows
        ])

        # 新编号启用前的公盘同名文件视作 V001；更新时备份并发布 V002。
        legacy_source = os.path.join(temp_root, "work", "Role_Hero_Idle.max")
        legacy_dest = os.path.join(
            nas_root, u"局内战斗备份", u"Role", u"Hero", u"初版",
            "Role_Hero_Idle.max",
        )
        _write(legacy_source, u"new-idle")
        _write(legacy_dest, u"legacy-idle")
        legacy_result = publish_max_to_nas_indoor(
            legacy_source, u"Role", u"Hero", u"初版",
            nas_base=nas_root, publisher=u"测试者",
            published_at=u"2026-09-08T12:00:00",
        )
        assert legacy_result[u"publish_revision_label"] == u"V002"
        assert u"发布备份" in legacy_result[u"archived_path"]
        with io.open(legacy_result[u"archived_path"], "r", encoding="utf-8") as stream:
            assert stream.read() == u"legacy-idle"
        legacy_payload = load_publish_settings(legacy_source)
        legacy_v1 = [
            x for x in legacy_payload[u"publish_history"]
            if x[u"publish_revision"] == 1
        ][0]
        assert legacy_v1[u"backup_path"] == legacy_result[u"archived_path"]
        assert legacy_v1.get(u"implicit_legacy") is True

        # 旧监修跨子版本仍共享大阶段计数：1.0 的隐式 V001 后，2.0 为 V002。
        legacy_monitor_source = os.path.join(
            temp_root, "work", "Role_Hero_Jump.max"
        )
        legacy_monitor_v1 = os.path.join(
            nas_root, u"局内战斗备份", u"Role", u"Hero", u"监修", u"1.0",
            "Role_Hero_Jump.max",
        )
        _write(legacy_monitor_source, u"new-jump")
        _write(legacy_monitor_v1, u"legacy-jump")
        legacy_monitor_result = publish_max_to_nas_indoor(
            legacy_monitor_source, u"Role", u"Hero", u"监修", version=u"2.0",
            nas_base=nas_root, publisher=u"测试者",
            published_at=u"2026-09-09T12:00:00",
        )
        assert legacy_monitor_result[u"publish_revision_label"] == u"V002"
        assert not legacy_monitor_result[u"archived_path"]
        print("PUBLISH_HISTORY_VALIDATION_OK")
    finally:
        shutil.rmtree(temp_root)


if __name__ == "__main__":
    main()

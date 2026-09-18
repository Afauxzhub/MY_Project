# -*- coding: utf-8 -*-
"""本地动作与公盘同名动作的阶段/发布日期更新检查。"""
from __future__ import division
import datetime
import os

from core.version_resolver import (
    collect_max_file_candidates,
    select_latest_candidate_pair,
)

try:
    _text_type = unicode
except NameError:
    _text_type = str


UPDATE_MARKER = u"公盘存在新版"


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return _text_type(repr(value))


def _same_path(left, right):
    try:
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
            os.path.abspath(right)
        )
    except Exception:
        return _as_text(left).lower() == _as_text(right).lower()


def _stage_key(item):
    score = item.get(u"score", (0, 0.0, 0.0))
    return score[0], score[1]


def _revision(item):
    try:
        return max(0, int(item.get(u"publish_revision", 0) or 0))
    except Exception:
        return 0


def _date_value(item):
    try:
        return float(item.get(u"published_sort", 0.0) or 0.0)
    except Exception:
        return 0.0


def _candidate_is_newer(local_item, stage_latest, date_latest):
    if stage_latest is None or date_latest is None:
        return False
    if _stage_key(stage_latest) > _stage_key(local_item):
        return True
    public_date = _date_value(date_latest)
    local_date = _date_value(local_item)
    if public_date > local_date:
        return True
    if (
        public_date == local_date
        and _stage_key(date_latest) == _stage_key(local_item)
        and _revision(date_latest) > _revision(local_item)
    ):
        return True
    return False


def annotate_local_files_with_public_updates(local_files, public_char_root):
    """为本地展示项附加公盘更新信息；公盘离线时保持无提示。"""
    local_files = list(local_files or [])
    public_groups = collect_max_file_candidates(public_char_root)
    for local_item in local_files:
        local_item[u"public_update_available"] = False
        local_item[u"public_update"] = None
        key = _as_text(local_item.get(u"name", u"")).lower()
        stage_latest, date_latest = select_latest_candidate_pair(
            public_groups.get(key, [])
        )
        if not _candidate_is_newer(local_item, stage_latest, date_latest):
            continue
        conflict = not _same_path(
            stage_latest.get(u"path", u""), date_latest.get(u"path", u"")
        )
        update = {
            u"stage_latest": stage_latest,
            u"date_latest": date_latest,
            u"conflict": conflict,
        }
        local_item[u"public_update_available"] = True
        local_item[u"public_update"] = update
    return local_files


def public_choice_label(prefix, item):
    """构建冲突选择项：文件名后显示精确时间、阶段和发布次数。"""
    item = item or {}
    published_at = _as_text(item.get(u"published_at", u"")).strip()
    if published_at:
        published_at = published_at.replace(u"T", u" ")[:19]
    else:
        try:
            date_value = _date_value(item)
            if date_value <= 0.0:
                raise ValueError("unknown date")
            published_at = datetime.datetime.fromtimestamp(date_value).strftime(
                u"%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            published_at = _as_text(item.get(u"date_label", u"日期未知"))
    stem = os.path.splitext(_as_text(item.get(u"name", u"")))[0]
    stage = _as_text(item.get(u"version_label", u"未标记版本"))
    revision = _as_text(item.get(u"publish_revision_label", u""))
    suffix = u"[{0}][{1}]".format(published_at, stage)
    if revision:
        suffix += u"[{0}]".format(revision)
    return u"{0}：{1}{2}".format(_as_text(prefix), stem, suffix)

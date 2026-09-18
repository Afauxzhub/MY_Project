# -*- coding: utf-8 -*-
"""公盘 MAX 发布事务：阶段计数、历史元数据和覆盖前备份。"""
from __future__ import division
import datetime
import io
import os
import re
import shutil
import time

from pipeline.publish_settings import (
    PUBLISH_SETTINGS_FOLDER,
    attach_publish_metadata,
    load_publish_settings,
    save_publish_settings,
    settings_path_for_max,
)

PUBLISH_BACKUP_FOLDER = u"发布备份"

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


def _ensure_dir(path):
    if path and not os.path.isdir(path):
        os.makedirs(path)


def _stage_scope(stage):
    stage = _as_text(stage).strip() or u"初版"
    return u"监修" if stage == u"监修" else stage


def _timestamp(value=None):
    text = _as_text(value).strip()
    return text or datetime.datetime.now().strftime(u"%Y-%m-%dT%H:%M:%S")


def _timestamp_slug(value):
    text = _as_text(value).replace(u"-", u"").replace(u":", u"")
    text = text.replace(u"T", u"_").replace(u" ", u"_")
    return text[:15] or datetime.datetime.now().strftime(u"%Y%m%d_%H%M%S")


def _safe_revision(value):
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _normalize_entry(entry):
    if not isinstance(entry, dict):
        return None
    result = dict(entry)
    result[u"stage"] = _as_text(result.get(u"stage", u"")).strip()
    result[u"stage_version"] = _as_text(
        result.get(u"stage_version", u"")
    ).strip()
    result[u"stage_scope"] = _stage_scope(
        result.get(u"stage_scope", u"") or result[u"stage"]
    )
    result[u"publish_revision"] = _safe_revision(
        result.get(u"publish_revision", 0)
    )
    revision = result[u"publish_revision"]
    result[u"publish_revision_label"] = (
        u"V{0:03d}".format(revision) if revision > 0 else u"旧版"
    )
    for key in (u"publisher", u"published_at", u"public_path", u"backup_path"):
        result[key] = _as_text(result.get(key, u""))
    return result


def _entry_key(entry):
    revision = _safe_revision(entry.get(u"publish_revision", 0))
    if revision > 0:
        return (u"revision", _stage_scope(entry.get(u"stage_scope")), revision)
    return (
        u"legacy",
        _as_text(entry.get(u"backup_path") or entry.get(u"public_path")),
        _as_text(entry.get(u"published_at")),
    )


def merge_histories(payloads):
    """合并多个旁车中的历史，同一阶段编号优先保留带备份路径的数据。"""
    merged = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for raw in payload.get(u"publish_history", []) or []:
            entry = _normalize_entry(raw)
            if entry is None:
                continue
            key = _entry_key(entry)
            previous = merged.get(key)
            if previous is None or (
                entry.get(u"backup_path") and not previous.get(u"backup_path")
            ):
                merged[key] = entry
    rows = list(merged.values())
    rows.sort(key=lambda x: (
        _as_text(x.get(u"published_at")),
        _stage_scope(x.get(u"stage_scope")),
        _safe_revision(x.get(u"publish_revision")),
    ))
    return rows


def _iter_matching_public_settings(scope_root, max_filename):
    json_name = os.path.splitext(os.path.basename(max_filename))[0] + u".json"
    if not scope_root or not os.path.isdir(scope_root):
        return
    for current, dirs, files in os.walk(scope_root):
        dirs[:] = [
            d for d in dirs
            if d not in (PUBLISH_BACKUP_FOLDER, u"_RigUpdateBackup")
        ]
        if os.path.basename(current) != PUBLISH_SETTINGS_FOLDER:
            continue
        if json_name not in files:
            continue
        max_path = os.path.join(os.path.dirname(current), os.path.basename(max_filename))
        payload = load_publish_settings(max_path)
        if isinstance(payload, dict):
            yield payload


def _stage_from_public_path(scope_root, max_path):
    """从角色公盘根目录解析阶段，避免依赖旧旁车是否完整。"""
    try:
        relative = os.path.relpath(max_path, scope_root)
    except Exception:
        return u"", u""
    parts = [
        _as_text(x).strip()
        for x in relative.replace(u"\\", u"/").split(u"/")
        if _as_text(x).strip()
    ]
    if not parts:
        return u"", u""
    stage = parts[0]
    if stage == u"监修":
        return stage, (parts[1] if len(parts) > 2 else u"")
    if stage in (u"初版", u"终版"):
        return stage, u""
    return u"", u""


def _iter_matching_public_max_files(scope_root, max_filename, stage):
    """枚举同一动作、同一大阶段已有的公盘 MAX（包含旧资产）。"""
    wanted_name = _as_text(os.path.basename(max_filename)).lower()
    wanted_scope = _stage_scope(stage)
    if not scope_root or not os.path.isdir(scope_root):
        return
    for current, dirs, files in os.walk(scope_root):
        dirs[:] = [
            d for d in dirs
            if d not in (
                PUBLISH_BACKUP_FOLDER,
                PUBLISH_SETTINGS_FOLDER,
                u"_RigUpdateBackup",
            )
        ]
        for name in files:
            if _as_text(name).lower() != wanted_name:
                continue
            path = os.path.join(current, name)
            path_stage, stage_version = _stage_from_public_path(scope_root, path)
            if _stage_scope(path_stage) != wanted_scope:
                continue
            yield path, path_stage, stage_version


def _stage_version_key(value):
    text = _as_text(value).strip()
    if re.match(r"^\d+(?:\.\d+)*$", text):
        return (1, tuple([int(x) for x in text.split(u".")]), u"")
    return (0, tuple(), text)


def _same_path(left, right):
    try:
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
            os.path.abspath(right)
        )
    except Exception:
        return _as_text(left) == _as_text(right)


def _implicit_legacy_entry(path, stage, stage_version):
    payload = load_publish_settings(path) or {}
    meta = payload.get(u"publish_metadata", {}) or {}
    published_at = _as_text(meta.get(u"published_at", u""))
    if not published_at:
        try:
            published_at = datetime.datetime.fromtimestamp(
                os.path.getmtime(path)
            ).strftime(u"%Y-%m-%dT%H:%M:%S")
        except Exception:
            published_at = u""
    entry = _normalize_entry({
        u"publish_revision": 1,
        u"publisher": _as_text(meta.get(u"publisher", u"")) or u"未设置",
        u"published_at": published_at,
        u"stage": stage,
        u"stage_version": stage_version,
        u"public_path": path,
        u"backup_path": u"",
        u"implicit_legacy": True,
    })
    return entry


def _seed_implicit_legacy_revision(history, scope_root, max_filename, stage):
    """无新式历史的已有动作视作基线 V001，下一次发布从 V002 开始。"""
    scope = _stage_scope(stage)
    if any([
        _safe_revision(x.get(u"publish_revision", 0)) > 0
        and _stage_scope(x.get(u"stage_scope") or x.get(u"stage")) == scope
        for x in history
    ]):
        return
    candidates = list(_iter_matching_public_max_files(
        scope_root, max_filename, stage
    ))
    if not candidates:
        return

    def _candidate_key(item):
        path, path_stage, stage_version = item
        try:
            modified = float(os.path.getmtime(path))
        except Exception:
            modified = 0.0
        version_key = (
            _stage_version_key(stage_version)
            if path_stage == u"监修"
            else (0, tuple(), u"")
        )
        return version_key, modified, os.path.normcase(path)

    path, path_stage, stage_version = max(candidates, key=_candidate_key)
    history.append(_implicit_legacy_entry(path, path_stage, stage_version))


def _next_revision(history, stage):
    scope = _stage_scope(stage)
    values = [
        _safe_revision(x.get(u"publish_revision", 0))
        for x in history
        if _stage_scope(x.get(u"stage_scope") or x.get(u"stage")) == scope
    ]
    return max(values or [0]) + 1


def _unique_backup_path(dest_path, revision_label, published_at):
    backup_dir = os.path.join(os.path.dirname(dest_path), PUBLISH_BACKUP_FOLDER)
    _ensure_dir(backup_dir)
    stem, ext = os.path.splitext(os.path.basename(dest_path))
    base = u"{0}_{1}_{2}".format(
        stem, _as_text(revision_label) or u"旧版", _timestamp_slug(published_at)
    )
    candidate = os.path.join(backup_dir, base + (ext or u".max"))
    index = 2
    while os.path.exists(candidate):
        candidate = os.path.join(
            backup_dir, u"{0}_{1}{2}".format(base, index, ext or u".max")
        )
        index += 1
    return candidate


def _legacy_entry(dest_path, backup_path, payload):
    meta = (payload or {}).get(u"publish_metadata", {}) or {}
    published_at = _as_text(meta.get(u"published_at", u""))
    if not published_at:
        try:
            published_at = datetime.datetime.fromtimestamp(
                os.path.getmtime(dest_path)
            ).strftime(u"%Y-%m-%dT%H:%M:%S")
        except Exception:
            published_at = u""
    return _normalize_entry({
        u"publish_revision": 0,
        u"publisher": _as_text(meta.get(u"publisher", u"")) or u"未设置",
        u"published_at": published_at,
        u"stage": _as_text(meta.get(u"stage", u"")),
        u"stage_version": _as_text(meta.get(u"stage_version", u"")),
        u"public_path": dest_path,
        u"backup_path": backup_path,
    })


def _archive_current(
    dest_path, history, existing_payload, published_at, stage, stage_version
):
    if not os.path.isfile(dest_path):
        return u""
    meta = (existing_payload or {}).get(u"publish_metadata", {}) or {}
    revision = _safe_revision(meta.get(u"publish_revision", 0))
    label = _as_text(meta.get(u"publish_revision_label", u""))
    matched_entry = None
    if revision <= 0:
        scope = _stage_scope(stage)
        for entry in history:
            if (
                _stage_scope(entry.get(u"stage_scope") or entry.get(u"stage")) == scope
                and _safe_revision(entry.get(u"publish_revision", 0)) == 1
                and _same_path(entry.get(u"public_path", u""), dest_path)
            ):
                revision = 1
                matched_entry = entry
                break
    if not label:
        label = u"V{0:03d}".format(revision) if revision > 0 else u"旧版"
    backup_path = _unique_backup_path(dest_path, label, published_at)
    shutil.copy2(dest_path, backup_path)

    existing_json = settings_path_for_max(dest_path)
    if existing_json and os.path.isfile(existing_json):
        backup_json = settings_path_for_max(backup_path)
        _ensure_dir(os.path.dirname(backup_json))
        shutil.copy2(existing_json, backup_json)

    matched = matched_entry is not None
    if matched_entry is not None:
        matched_entry[u"backup_path"] = backup_path
    if revision > 0:
        scope = _stage_scope(meta.get(u"stage", u""))
        if not scope or scope == u"初版" and stage != u"初版":
            scope = _stage_scope(stage)
        for entry in history:
            if (
                _stage_scope(entry.get(u"stage_scope") or entry.get(u"stage")) == scope
                and _safe_revision(entry.get(u"publish_revision", 0)) == revision
            ):
                entry[u"backup_path"] = backup_path
                matched = True
                break
    if not matched:
        history.append(_legacy_entry(dest_path, backup_path, existing_payload))
    return backup_path


def _lock_path(scope_root, max_filename, stage):
    lock_dir = os.path.join(scope_root, PUBLISH_SETTINGS_FOLDER)
    _ensure_dir(lock_dir)
    stem = os.path.splitext(os.path.basename(max_filename))[0]
    safe_stage = _stage_scope(stage).replace(os.sep, u"_")
    return os.path.join(lock_dir, u".{0}.{1}.publish.lock".format(stem, safe_stage))


def _acquire_lock(path, timeout_seconds=5.0):
    started = time.time()
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(descriptor, _as_text(os.getpid()).encode("ascii"))
            finally:
                os.close(descriptor)
            return
        except OSError:
            try:
                if time.time() - os.path.getmtime(path) > 300.0:
                    os.remove(path)
                    continue
            except Exception:
                pass
            if time.time() - started >= timeout_seconds:
                raise IOError(u"另一个发布任务正在更新同一文件，请稍后重试")
            time.sleep(0.1)


def publish_max_to_public(
    max_path,
    dest_path,
    scope_root,
    stage,
    stage_version=u"",
    publisher=u"",
    published_at=None,
):
    """执行一次公盘发布；成功时恰好分配一个阶段内发布编号。"""
    max_path = _as_text(max_path)
    dest_path = _as_text(dest_path)
    scope_root = _as_text(scope_root)
    stage = _as_text(stage).strip() or u"初版"
    stage_version = _as_text(stage_version).strip() if stage == u"监修" else u""
    published_at = _timestamp(published_at)
    lock_path = _lock_path(scope_root, os.path.basename(dest_path), stage)
    _acquire_lock(lock_path)
    try:
        local_payload = load_publish_settings(max_path) or {}
        existing_payload = load_publish_settings(dest_path) or {}
        payloads = [local_payload, existing_payload]
        payloads.extend(list(_iter_matching_public_settings(
            scope_root, os.path.basename(dest_path)
        )))
        history = merge_histories(payloads)
        _seed_implicit_legacy_revision(
            history, scope_root, os.path.basename(dest_path), stage
        )
        archived_path = _archive_current(
            dest_path,
            history,
            existing_payload,
            published_at,
            stage,
            stage_version,
        )
        revision = _next_revision(history, stage)
        revision_label = u"V{0:03d}".format(revision)

        _ensure_dir(os.path.dirname(dest_path))
        if os.path.normcase(os.path.abspath(max_path)) != os.path.normcase(
            os.path.abspath(dest_path)
        ):
            shutil.copy2(max_path, dest_path)

        entry = _normalize_entry({
            u"publish_revision": revision,
            u"publisher": _as_text(publisher).strip() or u"未设置",
            u"published_at": published_at,
            u"stage": stage,
            u"stage_version": stage_version,
            u"public_path": dest_path,
            u"backup_path": u"",
        })
        history.append(entry)
        payload = attach_publish_metadata(
            local_payload,
            entry[u"publisher"],
            stage,
            stage_version,
            published_at=published_at,
            publish_revision=revision,
            public_path=dest_path,
        )
        payload[u"publish_history"] = history

        ok_public, public_result = save_publish_settings(dest_path, payload)
        if not ok_public:
            raise IOError(u"公盘发布设置写入失败：{0}".format(public_result))
        ok_local, local_result = save_publish_settings(max_path, payload)
        return {
            u"dest_path": dest_path,
            u"archived_path": archived_path,
            u"publish_revision": revision,
            u"publish_revision_label": revision_label,
            u"published_at": published_at,
            u"publisher": entry[u"publisher"],
            u"local_settings_saved": bool(ok_local),
            u"local_settings_result": local_result,
        }
    finally:
        try:
            os.remove(lock_path)
        except Exception:
            pass

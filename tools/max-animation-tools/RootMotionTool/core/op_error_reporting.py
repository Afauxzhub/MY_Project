# -*- coding: utf-8 -*-
"""Animation Tools shared error-report creation and public-share upload.

This module deliberately has no Qt dependency.  Tool UIs create a local report
first and only call :func:`upload_report` after the animator clicks Upload.
"""
from __future__ import print_function

import datetime
import getpass
import io
import json
import os
import platform
import shutil
import socket
import sys
import tempfile
import traceback
import uuid


try:
    _text_type = unicode
except NameError:
    _text_type = str


SCHEMA_VERSION = 1
DEFAULT_PUBLIC_REPORT_ROOT = u""
LOCAL_REPORT_FOLDER = u"AnimationTools_ErrorReports"
MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    if sys.version_info[0] < 3 and isinstance(value, str):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("gbk", "replace")
    if sys.version_info[0] >= 3 and isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    try:
        return _text_type(value)
    except Exception:
        try:
            return _text_type(repr(value))
        except Exception:
            return u"<unprintable>"


def _json_safe(value, depth=0):
    if depth > 8:
        return u"<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out[_as_text(key)] = _json_safe(item, depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, depth + 1) for item in value]
    return _as_text(value)


def _safe_filename(value, fallback=u"item"):
    text = _as_text(value).strip()
    bad = u'<>:"/\\|?*\r\n\t'
    for char in bad:
        text = text.replace(char, u"_")
    text = text.strip(u" ._")
    return (text or fallback)[:100]


def _write_json(path, data):
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    temp_path = path + u".tmp"
    payload = json.dumps(_json_safe(data), ensure_ascii=False, indent=2)
    with io.open(temp_path, "w", encoding="utf-8") as stream:
        stream.write(_as_text(payload))
    if os.path.exists(path):
        os.remove(path)
    os.rename(temp_path, path)


def _default_local_root():
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(_as_text(base), LOCAL_REPORT_FOLDER, u"pending")


def resolve_public_report_root(config=None):
    config = config or {}
    explicit = _as_text(config.get(u"error_report_root", u"")).strip()
    if explicit:
        return os.path.normpath(explicit)
    nas_base = _as_text(config.get(u"nas_base", u"")).strip()
    if nas_base:
        parent = os.path.dirname(os.path.normpath(nas_base.rstrip(u"\\/")))
        if parent:
            return os.path.join(parent, u"OP Tools报错报告")
    return os.path.normpath(DEFAULT_PUBLIC_REPORT_ROOT)


def _current_max_context():
    context = {}
    try:
        import pymxs

        rt = pymxs.runtime
        context[u"max_file"] = os.path.join(
            _as_text(rt.maxFilePath), _as_text(rt.maxFileName)
        )
        context[u"frame_rate"] = int(rt.frameRate)
        context[u"animation_range"] = {
            u"start": float(rt.animationRange.start.frame),
            u"end": float(rt.animationRange.end.frame),
        }
        try:
            context[u"max_version"] = _as_text(rt.maxVersion())
        except Exception:
            pass
    except Exception:
        pass
    return context


def _copy_attachment(source_path, attachments_dir, used_names):
    source_path = _as_text(source_path).strip()
    if not source_path or not os.path.isfile(source_path):
        return None
    base_name = _safe_filename(os.path.basename(source_path), u"attachment")
    stem, ext = os.path.splitext(base_name)
    target_name = base_name
    suffix = 2
    while target_name.lower() in used_names:
        target_name = u"{0}_{1}{2}".format(stem, suffix, ext)
        suffix += 1
    used_names.add(target_name.lower())
    target_path = os.path.join(attachments_dir, target_name)
    original_size = os.path.getsize(source_path)
    truncated = original_size > MAX_ATTACHMENT_BYTES
    with open(source_path, "rb") as source:
        if truncated:
            source.seek(max(0, original_size - MAX_ATTACHMENT_BYTES))
        content = source.read(MAX_ATTACHMENT_BYTES)
    with open(target_path, "wb") as target:
        target.write(content)
    return {
        u"name": target_name,
        u"original_path": source_path,
        u"original_size": original_size,
        u"copied_size": len(content),
        u"tail_truncated": bool(truncated),
        u"relative_path": u"attachments/{0}".format(target_name),
    }


def _write_summary(path, report):
    tool = report.get(u"tool", {})
    error = report.get(u"error", {})
    context = report.get(u"context", {})
    lines = [
        u"Animation Tools 报错报告",
        u"报告编号: {0}".format(report.get(u"report_id", u"")),
        u"时间: {0}".format(report.get(u"created_at", u"")),
        u"工具: {0} ({1})".format(tool.get(u"name", u""), tool.get(u"id", u"")),
        u"版本: {0}".format(tool.get(u"version", u"")),
        u"错误类型: {0}".format(error.get(u"type", u"")),
        u"错误信息: {0}".format(error.get(u"message", u"")),
        u"场景: {0}".format(context.get(u"max_file", u"")),
        u"",
        u"详细信息请查看 report.json；附件位于 attachments 文件夹。",
    ]
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(u"\n".join(lines))


def create_error_report(tool_id, tool_name, message, config=None,
                        exception=None, traceback_text=None, context=None,
                        attachments=None, tool_version=u"", local_root=None):
    """Create one immutable local report folder and return its descriptor."""
    now = datetime.datetime.now()
    now_utc = datetime.datetime.utcnow()
    report_id = u"{0}_{1}".format(
        now.strftime("%Y%m%d_%H%M%S"), _as_text(uuid.uuid4().hex[:8])
    )
    tool_id = _safe_filename(tool_id, u"unknown-tool").lower()
    root = _as_text(local_root or _default_local_root())
    report_dir = os.path.join(root, report_id)
    os.makedirs(report_dir)
    attachments_dir = os.path.join(report_dir, u"attachments")
    os.makedirs(attachments_dir)

    tb_text = _as_text(traceback_text)
    if not tb_text and exception is not None:
        tb_text = _as_text(traceback.format_exc())
        if tb_text.strip() == u"NoneType: None":
            tb_text = u""

    merged_context = _current_max_context()
    merged_context.update(_json_safe(context or {}))
    attachment_rows = []
    used_names = set()
    for source_path in attachments or []:
        try:
            row = _copy_attachment(source_path, attachments_dir, used_names)
            if row:
                attachment_rows.append(row)
        except Exception as attachment_error:
            attachment_rows.append({
                u"original_path": _as_text(source_path),
                u"copy_error": _as_text(attachment_error),
            })

    report = {
        u"schema_version": SCHEMA_VERSION,
        u"report_id": report_id,
        u"created_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        u"created_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        u"tool": {
            u"id": tool_id,
            u"name": _as_text(tool_name),
            u"version": _as_text(tool_version),
        },
        u"error": {
            u"type": _as_text(exception.__class__.__name__) if exception is not None else u"ReportedFailure",
            u"message": _as_text(message),
            u"traceback": tb_text,
        },
        u"context": merged_context,
        u"environment": {
            u"user": _as_text(getpass.getuser()),
            u"machine": _as_text(socket.gethostname()),
            u"python": _as_text(sys.version),
            u"platform": _as_text(platform.platform()),
        },
        u"attachments": attachment_rows,
    }
    report_json = os.path.join(report_dir, u"report.json")
    _write_json(report_json, report)
    _write_summary(os.path.join(report_dir, u"summary.txt"), report)
    return {
        u"report_id": report_id,
        u"tool_id": tool_id,
        u"created_at": report[u"created_at"],
        u"local_dir": report_dir,
        u"report_json": report_json,
        u"public_root": resolve_public_report_root(config),
    }


def upload_report(descriptor, public_root=None):
    """Copy a prepared report to the public share using a temp-folder rename."""
    local_dir = _as_text(descriptor.get(u"local_dir", u""))
    report_id = _safe_filename(descriptor.get(u"report_id", u""), u"report")
    tool_id = _safe_filename(descriptor.get(u"tool_id", u"unknown-tool"), u"unknown-tool")
    created_at = _as_text(descriptor.get(u"created_at", u""))
    if not local_dir or not os.path.isdir(local_dir):
        raise IOError(u"本机报错报告不存在: {0}".format(local_dir))
    root = _as_text(public_root or descriptor.get(u"public_root", u"")).strip()
    if not root:
        raise IOError(u"未配置报错报告公盘目录")
    month = created_at[:7] if len(created_at) >= 7 else datetime.datetime.now().strftime("%Y-%m")
    parent = os.path.join(root, month, tool_id)
    if not os.path.exists(parent):
        os.makedirs(parent)
    destination = os.path.join(parent, report_id)
    if os.path.exists(destination):
        return destination
    temp_destination = destination + u".uploading-{0}".format(_as_text(uuid.uuid4().hex[:8]))
    try:
        shutil.copytree(local_dir, temp_destination)
        os.rename(temp_destination, destination)
    except Exception:
        try:
            if os.path.isdir(temp_destination):
                shutil.rmtree(temp_destination)
        except Exception:
            pass
        raise
    receipt = {
        u"report_id": report_id,
        u"uploaded_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        u"destination": destination,
    }
    try:
        _write_json(os.path.join(local_dir, u"upload_receipt.json"), receipt)
    except Exception:
        pass
    return destination

# -*- coding: utf-8 -*-
"""Artist-facing summaries for known ProxyRoot export failures.

This module only translates an error after the exporter has already failed.  It
must not be used as a preflight or as an additional export gate.
"""
from __future__ import unicode_literals

import re


try:
    _text_type = unicode
except NameError:
    _text_type = str


_POST_SCALE_MARKER = u"ProxyRoot post-scale world hard validation failed."
_TASK_LOCAL_CURVE_MARKER = u"FBX 分段曲线越界，已阻止发布:"
_TASK_LOCAL_CURVE_ENTRY = re.compile(
    r"FAIL task-local PRS curve outside Take:\s+"
    r"(.*?)\s+Lcl\s+(Translation|Rotation|Scaling)\s+"
    r"[^\s]+\s+outside=",
    re.UNICODE,
)
_WINDOWS_PATH_ERROR_MARKERS = (
    u"No such file or directory",
    u"The filename or extension is too long",
    u"The system cannot find the path specified",
    u"文件名或扩展名太长",
    u"系统找不到指定的路径",
)
_LONG_SOURCE_FILENAME_UNITS = 120


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _utf16_units(value):
    """Return the Windows UTF-16 code-unit count without a BOM."""
    try:
        return len(_as_text(value).encode("utf-16-le")) // 2
    except Exception:
        return len(_as_text(value))


def format_publish_filename_too_long_error(
        error, max_file_path, minimum_filename_units=_LONG_SOURCE_FILENAME_UNITS):
    """Translate an existing Windows path failure caused by an overlong source name.

    This is presentation-only.  It deliberately does not preflight, rename, shorten,
    or otherwise change the public backup transaction.
    """
    text = _as_text(error)
    filename = _as_text(max_file_path).replace(u"/", u"\\").rsplit(u"\\", 1)[-1]
    if not filename or _utf16_units(filename) < int(minimum_filename_units):
        return None

    error_number = getattr(error, "errno", None)
    is_path_error = error_number in (2, 3, 206)
    if not is_path_error:
        lowered = text.lower()
        is_path_error = any(
            marker.lower() in lowered for marker in _WINDOWS_PATH_ERROR_MARKERS
        )
    if not is_path_error:
        return None

    return (
        u"源文件名过长，公盘备份路径超出 Windows 限制，无法发布。\n\n"
        u"请缩短源 Max 文件名后重新尝试。"
    )


def _parse_metric(text, prefix):
    pattern = (
        re.escape(prefix) +
        r"Node=(.*?)\s+" +
        re.escape(prefix) +
        r"Frame=([^\s]+)\s+" +
        re.escape(prefix) +
        r"Err=([^\s]+)"
    )
    match = re.search(pattern, text)
    if match is None:
        return None
    try:
        error_value = float(match.group(3))
    except (TypeError, ValueError):
        return None
    return {
        u"node": match.group(1).strip(),
        u"frame": match.group(2).strip(),
        u"error": error_value,
    }


def _format_frame(value):
    try:
        number = float(value)
        rounded = int(round(number))
        if abs(number - rounded) < 0.000001:
            return _text_type(rounded)
        return (u"{0:.3f}".format(number)).rstrip(u"0").rstrip(u".")
    except (TypeError, ValueError):
        return _as_text(value)


def _clean_export_node_name(value):
    text = _as_text(value).strip()
    marker = u"__OPProxySource_"
    if marker in text:
        text = text.split(marker, 1)[0]
    return text


def format_task_local_curve_export_error(error, preview_limit=6):
    """Summarize an existing split-Take FBX curve failure for artists."""
    text = _as_text(error)
    if _TASK_LOCAL_CURVE_MARKER not in text:
        return None

    nodes = []
    seen = set()
    for match in _TASK_LOCAL_CURVE_ENTRY.finditer(text):
        node = _clean_export_node_name(match.group(1))
        key = node.lower()
        if node and key not in seen:
            seen.add(key)
            nodes.append(node)

    message = [u"分段 FBX 中仍包含片段范围外的动画曲线，已停止发布。"]
    if nodes:
        limit = max(1, int(preview_limit))
        preview = nodes[:limit]
        suffix = u"" if len(nodes) <= limit else u" 等"
        message.append(
            u"涉及节点：{0}{1}（共 {2} 个）".format(
                u"、".join(preview), suffix, len(nodes)
            )
        )
    message.append(u"请点击“上传报错”交由 TD 处理。")
    return u"\n\n".join(message)


def format_proxy_transform_restore_error(
        error,
        position_tolerance,
        axis_tolerance=0.002,
        scale_tolerance=0.001):
    """Return a concise Chinese summary, or ``None`` for unrelated errors."""
    text = _as_text(error)
    if _POST_SCALE_MARKER not in text:
        return None

    definitions = (
        (u"worldPos", u"位置", float(position_tolerance)),
        (u"worldAxis", u"旋转", float(axis_tolerance)),
        (u"worldScale", u"缩放", float(scale_tolerance)),
    )
    issues = []
    for prefix, label, tolerance in definitions:
        metric = _parse_metric(text, prefix)
        if metric is not None and metric[u"error"] > tolerance:
            metric[u"label"] = label
            issues.append(metric)

    if not issues:
        return (
            u"检测到骨骼缩放写回后的变换还原失败，已停止导出。\n\n"
            u"请点击“上传报错”交由 TD 处理。"
        )

    blocks = [u"检测到骨骼缩放写回后的变换还原失败，已停止导出。"]
    for issue in issues:
        blocks.append(
            u"骨骼：{0}\n帧：{1}\n问题：{2}数据无法正确还原".format(
                issue[u"node"],
                _format_frame(issue[u"frame"]),
                issue[u"label"],
            )
        )
    blocks.append(u"请点击“上传报错”交由 TD 处理。")
    return u"\n\n".join(blocks)

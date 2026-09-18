# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re

try:
    _text_type = unicode
except NameError:
    _text_type = str


INGAME_TYPES = set([u"Role", u"Monster", u"Elite", u"Boss", u"Npc", u"Scene", u"Prop"])
AUTO_UPDATE_SKIP_DIRS = set([u"_RigUpdateBackup", u"_RigUpdatePackages", u"_RigUpdateReports"])


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _parse_version(text, default=u"v01"):
    match = re.search(r"(?i)(?:^|[_\-\s])v(\d{1,3})(?:$|[_\-\s])", _as_text(text))
    if not match:
        return default
    return u"v{0:02d}".format(int(match.group(1)))


def _strip_version_token(text):
    return re.sub(r"(?i)([_\-\s])v\d{1,3}(?=$|[_\-\s])", "", _as_text(text)).strip("_- ")


def _has_name_token(path_or_name, token):
    stem = os.path.splitext(os.path.basename(_as_text(path_or_name)))[0]
    token = _as_text(token).lower()
    return token in [x.lower() for x in stem.split("_") if x]


def is_skin_binding_name(path_or_name):
    return _has_name_token(path_or_name, "skin")


def is_auto_update_skip_path(path):
    parts = []
    cur = os.path.abspath(_as_text(path))
    while True:
        head, tail = os.path.split(cur)
        if tail:
            parts.append(tail)
        if not head or head == cur:
            break
        cur = head
    return bool([x for x in parts if x in AUTO_UPDATE_SKIP_DIRS])


def detect_file_context(max_path):
    max_path = os.path.abspath(_as_text(max_path)) if max_path else u""
    stem = os.path.splitext(os.path.basename(max_path))[0]
    parts = stem.split("_")
    is_skin_binding = is_skin_binding_name(max_path)
    result = {
        "path": max_path,
        "stem": stem,
        "kind": "binding" if is_skin_binding else "out_game",
        "is_in_game": False,
        "type": u"",
        "character": u"",
        "animation": stem,
        "old_version": _parse_version(stem, default=u"v01"),
        "is_skin_binding": is_skin_binding,
        "skip_auto_update": is_auto_update_skip_path(max_path) or is_skin_binding,
    }
    if is_skin_binding:
        return result
    if len(parts) >= 3 and parts[0] in INGAME_TYPES:
        result.update({
            "kind": "in_game",
            "is_in_game": True,
            "type": parts[0],
            "character": parts[1],
            "animation": _strip_version_token(u"_".join(parts[2:])),
        })
    return result

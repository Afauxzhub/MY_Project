# -*- coding: utf-8 -*-
from __future__ import print_function
import io
import json
import os
import re

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
        return u""


def _safe_name(text):
    return re.sub(r"[^\w\-.]+", "_", _as_text(text), flags=re.UNICODE).strip("_") or u"Mapping"


def binding_dir_for_rig(rig_path):
    rig_dir = os.path.dirname(os.path.abspath(_as_text(rig_path)))
    if os.path.basename(rig_dir).lower() == "max":
        rig_dir = os.path.dirname(rig_dir)
    return os.path.join(rig_dir, u"Binding")


def mapping_filename(character, old_version, new_version):
    return u"{0}_{1}-{2}.json".format(_safe_name(character), _as_text(old_version) or u"v01", _as_text(new_version) or u"v02")


def versioned_mapping_path(rig_path, character, old_version, new_version):
    return os.path.join(binding_dir_for_rig(rig_path), mapping_filename(character, old_version, new_version))


def load_mapping(path):
    if not path or not os.path.exists(path):
        return {}
    with io.open(path, "r", encoding="utf-8") as f:
        data = json.loads(f.read())
    if isinstance(data, dict):
        for key in ("objects", "mapping", "name_map", "nameMap"):
            if isinstance(data.get(key), dict):
                return data.get(key)
        return data
    return {}


def save_mapping(path, mapping, meta=None):
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    payload = {"objects": mapping or {}}
    if meta:
        payload["meta"] = meta
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(_as_text(json.dumps(payload, ensure_ascii=False, indent=2)))
    return path

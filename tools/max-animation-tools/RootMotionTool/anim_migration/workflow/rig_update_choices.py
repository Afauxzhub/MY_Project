# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import json
import os
import re
import time


SCHEMA_VERSION = 1

try:
    _text_type = unicode
except NameError:
    _text_type = str


def _text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _version(path):
    match = re.search(r"(?i)(?:^|_)v(\d{1,3})(?=\.max$|_)", os.path.basename(_text(path)))
    return u"v{0:02d}".format(int(match.group(1))) if match else u""


def _identity(path):
    stem = os.path.splitext(os.path.basename(_text(path)))[0]
    match = re.match(r"(?i)^(?:Role|Monster|Elite|Boss|Npc)_([^_]+)_(lod|cs)_skin_", stem)
    if match:
        return _text(match.group(1)).lower(), _text(match.group(2)).lower()
    return stem.lower(), u"unknown"


def pair_key(source_rig_path, target_rig_path):
    source_identity = _identity(source_rig_path)
    target_identity = _identity(target_rig_path)
    identity = source_identity if source_identity == target_identity else (
        source_identity[0] + u"_to_" + target_identity[0],
        source_identity[1] + u"_to_" + target_identity[1],
    )
    return u"{0}|{1}|{2}|{3}".format(
        identity[0], identity[1], _version(source_rig_path), _version(target_rig_path)
    )


def choice_store_path(tool_root):
    return os.path.join(os.path.abspath(_text(tool_root)), "RootMotionTool", "config", "rig_update_pair_choices.json")


def load_pair_choice(tool_root, source_rig_path, target_rig_path):
    path = choice_store_path(tool_root)
    try:
        if not os.path.exists(path):
            return {}
        with io.open(path, "r", encoding="utf-8") as stream:
            data = json.loads(stream.read())
        if not isinstance(data, dict) or int(data.get("schema_version", 0)) != SCHEMA_VERSION:
            return {}
        value = (data.get("choices", {}) or {}).get(pair_key(source_rig_path, target_rig_path), {})
        return dict(value) if isinstance(value, dict) else {}
    except Exception:
        return {}


def save_pair_choice(tool_root, source_rig_path, target_rig_path, choice):
    path = choice_store_path(tool_root)
    folder = os.path.dirname(path)
    try:
        if not os.path.exists(folder):
            os.makedirs(folder)
        data = {"schema_version": SCHEMA_VERSION, "choices": {}}
        if os.path.exists(path):
            try:
                with io.open(path, "r", encoding="utf-8") as stream:
                    loaded = json.loads(stream.read())
                if isinstance(loaded, dict) and int(loaded.get("schema_version", 0)) == SCHEMA_VERSION:
                    data = loaded
            except Exception:
                pass
        saved = dict(choice or {})
        saved["source_rig_path"] = os.path.abspath(_text(source_rig_path))
        saved["target_rig_path"] = os.path.abspath(_text(target_rig_path))
        saved["source_version"] = _version(source_rig_path)
        saved["target_version"] = _version(target_rig_path)
        saved["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        data.setdefault("choices", {})[pair_key(source_rig_path, target_rig_path)] = saved
        temp_path = path + ".tmp"
        with io.open(temp_path, "w", encoding="utf-8") as stream:
            stream.write(_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)))
        if os.path.exists(path):
            os.remove(path)
        os.rename(temp_path, path)
        return True, path
    except Exception as error:
        try:
            if os.path.exists(path + ".tmp"):
                os.remove(path + ".tmp")
        except Exception:
            pass
        return False, _text(error)

# -*- coding: utf-8 -*-
from __future__ import print_function
import datetime
import re

try:
    _text_type = unicode
except NameError:
    _text_type = str


VERSION_PROP = u"OP_RigUpdate_CurrentVersion"
RIG_PROP = u"OP_RigUpdate_CurrentRig"
UPDATED_AT_PROP = u"OP_RigUpdate_UpdatedAt"


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _mxs_escape(text):
    return _as_text(text).replace("\\", "\\\\").replace('"', '\\"')


def normalize_version(version):
    match = re.search(r"(\d+)", _as_text(version))
    return u"v{0:02d}".format(int(match.group(1))) if match else u""


def read_scene_binding_version(rt):
    script = u'''(
        local value = ""
        try(value = getUserProp rootNode "{0}")catch()
        if value == undefined then "" else (value as string)
    )'''.format(_mxs_escape(VERSION_PROP))
    try:
        return normalize_version(rt.execute(script))
    except Exception:
        return u""


def read_scene_binding_metadata(rt):
    script = u'''(
        local versionValue = ""
        local rigValue = ""
        try(versionValue = getUserProp rootNode "{0}")catch()
        try(rigValue = getUserProp rootNode "{1}")catch()
        if versionValue == undefined do versionValue = ""
        if rigValue == undefined do rigValue = ""
        #((versionValue as string), (rigValue as string))
    )'''.format(_mxs_escape(VERSION_PROP), _mxs_escape(RIG_PROP))
    try:
        raw = rt.execute(script)
        try:
            version_value = _as_text(raw[0])
            rig_value = _as_text(raw[1])
        except Exception:
            version_value = _as_text(raw[1])
            rig_value = _as_text(raw[2])
        return {
            "version": normalize_version(version_value),
            "rig_path": rig_value,
        }
    except Exception:
        return {"version": u"", "rig_path": u""}


def write_scene_binding_version(rt, version, rig_path=u""):
    version = normalize_version(version)
    if not version:
        return False
    updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script = u'''(
        try(setUserProp rootNode "{0}" "{1}")catch()
        try(setUserProp rootNode "{2}" "{3}")catch()
        try(setUserProp rootNode "{4}" "{5}")catch()
        local value = undefined
        try(value = getUserProp rootNode "{0}")catch()
        value != undefined and ((value as string) == "{1}")
    )'''.format(
        _mxs_escape(VERSION_PROP),
        _mxs_escape(version),
        _mxs_escape(RIG_PROP),
        _mxs_escape(rig_path),
        _mxs_escape(UPDATED_AT_PROP),
        _mxs_escape(updated_at),
    )
    try:
        return bool(rt.execute(script))
    except Exception:
        return False

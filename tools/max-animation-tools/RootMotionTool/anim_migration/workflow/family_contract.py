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


def _text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def rig_identity_from_path(path):
    stem = os.path.splitext(os.path.basename(_text(path)))[0]
    tokens = [token for token in stem.split("_") if token]
    character = tokens[1] if len(tokens) > 1 else u""
    lower = [token.lower() for token in tokens]
    category = "lod" if "lod" in lower else "cs" if "cs" in lower else "unknown"
    return {"character": character, "category": category}


def _safe_token(value):
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", _text(value)).strip("_")


def _read_json(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return json.loads(stream.read())


def find_standard_contract(tool_root, rig_path):
    identity = rig_identity_from_path(rig_path)
    base = os.path.join(tool_root, "manifests", "standard_rigs")
    candidates = [
        os.path.join(base, "{0}_{1}.json".format(_safe_token(identity["character"]), identity["category"].upper())),
        os.path.join(base, "{0}.json".format(_safe_token(identity["character"]))),
    ]
    return next((path for path in candidates if os.path.exists(path)), u"")


def load_standard_contract(path):
    if not path:
        return {}
    data = _read_json(path)
    if not isinstance(data, dict) or data.get("schema_version") not in (1, 2):
        raise RuntimeError(u"OP_STD 标准契约格式不受支持: {0}".format(path))
    if not isinstance(data.get("entries"), list):
        raise RuntimeError(u"OP_STD 标准契约缺少 entries: {0}".format(path))
    return data


def find_family_adapter_contract(tool_root, rig_path, source_family, target_family):
    identity = rig_identity_from_path(rig_path)
    base = os.path.join(tool_root, "manifests", "rig_adapters")
    route = "{0}_to_{1}".format(_safe_token(source_family), _safe_token(target_family))
    candidates = [
        os.path.join(base, "{0}_{1}_{2}.json".format(_safe_token(identity["character"]), identity["category"].upper(), route)),
        os.path.join(base, route + ".json"),
    ]
    return next((path for path in candidates if os.path.exists(path)), u"")


def load_family_adapter_contract(path, source_family=u"", target_family=u""):
    if not path:
        return {}
    data = _read_json(path)
    if not isinstance(data, dict) or data.get("kind") != "binding_family_adapter_override":
        raise RuntimeError(u"家族适配器必须声明 kind=binding_family_adapter_override: {0}".format(path))
    declared_source = _text(data.get("source_family", ""))
    declared_target = _text(data.get("target_family", ""))
    if source_family and declared_source != source_family:
        raise RuntimeError(u"家族适配器 source_family 不匹配")
    if target_family and declared_target != target_family:
        raise RuntimeError(u"家族适配器 target_family 不匹配")
    if not isinstance(data.get("objects", {}), dict):
        raise RuntimeError(u"家族适配器 objects 必须是对象")
    return data


def _normalized_identity(name):
    value = _text(name).strip()
    if value.lower().startswith("bone_skin_"):
        value = value[len("Bone_Skin_"):]
    return value.lower()


def _unique_index(rows, key_fn):
    grouped = {}
    for row in rows:
        key = key_fn(row)
        if key:
            grouped.setdefault(key, []).append(row)
    return dict([(key, values[0]) for key, values in grouped.items() if len(values) == 1])


def _resolve_entry(entry, rows):
    by_guid = _unique_index(rows, lambda row: _text(row.get("rr_guid", "")))
    by_name = _unique_index(rows, lambda row: _text(row.get("name", "")))
    by_identity = _unique_index(rows, lambda row: _normalized_identity(row.get("name", "")))
    guid = _text(entry.get("source_rr_guid", ""))
    if guid and guid in by_guid:
        return by_guid[guid], "rr_guid"
    name = _text(entry.get("source_name", ""))
    if name and name in by_name:
        return by_name[name], "exact_name"
    identity = _normalized_identity(entry.get("source_identity", ""))
    if identity and identity in by_identity:
        return by_identity[identity], "normalized_identity"
    return None, "unresolved"


def resolve_standard_roles(contract, source_rows, target_rows):
    resolved = []
    for entry in contract.get("entries", []) if contract else []:
        source, source_method = _resolve_entry(entry, source_rows)
        target, target_method = _resolve_entry(entry, target_rows)
        resolved.append({
            "role_id": entry.get("role_id", ""),
            "scope": entry.get("scope", ""),
            "required": bool(entry.get("required", False)),
            "source_name": source.get("name", "") if source else "",
            "target_name": target.get("name", "") if target else "",
            "source_method": source_method,
            "target_method": target_method,
            "status": "mapped" if source is not None and target is not None else "unresolved",
        })
    return resolved

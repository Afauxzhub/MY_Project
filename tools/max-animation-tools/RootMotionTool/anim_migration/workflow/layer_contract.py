# -*- coding: utf-8 -*-
from __future__ import print_function

import hashlib
import json


MIGRATION_LAYERS = (
    u"Bip",
    u"Bones",
    u"UI",
    u"面部控制器不参与输出",
    u"Ctrl",
    u"Body_Ctrl",
)

LAYER_SCOPES = {
    u"Bip": "bip",
    u"Bones": "bones",
    u"UI": "ui",
    u"面部控制器不参与输出": "face_control",
    u"Ctrl": "ctrl",
    u"Body_Ctrl": "body_ctrl",
}

# These are normalized panel/helper layers. Their contents are never animation
# interfaces and therefore must not participate in identity, duplicate, drift,
# or source/target difference checks. BS_UI is a legacy normalization input,
# not a post-normalization migration layer.
IGNORED_ANIMATION_LAYERS = (
    u"UI_Text",
    u"UI_Frame",
    u"UI_Helper",
    u"Dum",
    u"no1ctrl",
    u"Face_Helper",
    u"Body_Helper",
)
_IGNORED_ANIMATION_LAYER_KEYS = frozenset([name.lower() for name in IGNORED_ANIMATION_LAYERS])

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


def canonical_layer_name(value):
    wanted = _text(value).strip().lower()
    for name in MIGRATION_LAYERS:
        if name.lower() == wanted:
            return name
    return u""


def layer_scope(value):
    return LAYER_SCOPES.get(canonical_layer_name(value), u"")


def is_ignored_animation_layer(value):
    wanted = _text(value).strip().lower()
    return wanted in _IGNORED_ANIMATION_LAYER_KEYS


def is_ignored_animation_row(row):
    layer_name = _text(row.get("layer_name", "")).strip()
    # A node assigned directly to UI is an animation interface. Any descendant
    # Layer under UI is panel/decorative ownership regardless of its layer name.
    if canonical_layer_name(layer_name) == u"UI":
        return False
    if is_ignored_animation_layer(layer_name):
        return True
    ancestors = row.get("layer_ancestor_names", []) or []
    return any([_text(name).strip().lower() == u"ui" for name in ancestors])


def _is_line_control(row):
    class_name = _text(row.get("class_name", "")).lower()
    superclass_name = _text(row.get("superclass_name", "")).lower()
    if "text" in class_name:
        return False
    return (
        class_name in ("line", "splineshape", "editable_spline") or
        "spline" in class_name or
        ("shape" in superclass_name and "line" in class_name)
    )


def is_contract_member(row):
    layer = canonical_layer_name(row.get("layer_name", ""))
    if not layer:
        return False
    if layer == u"Bip":
        return bool(row.get("is_bip"))
    if layer == u"面部控制器不参与输出":
        return _is_line_control(row)
    return True


def contract_rows(rows):
    out = []
    for row in rows or []:
        if not is_contract_member(row):
            continue
        item = dict(row)
        layer = canonical_layer_name(item.get("layer_name", ""))
        item["contract_layer"] = layer
        item["scope"] = layer_scope(layer)
        out.append(item)
    return out


def public_layer_snapshot(rows):
    layers = dict([(name, []) for name in MIGRATION_LAYERS])
    for row in contract_rows(rows):
        layers[row["contract_layer"]].append({
            "name": _text(row.get("name", "")),
            "rr_guid": _text(row.get("rr_guid", "")),
            "class_name": _text(row.get("class_name", "")),
            "superclass_name": _text(row.get("superclass_name", "")),
            "parent_name": _text(row.get("parent_name", "")),
            "contract_layer": row["contract_layer"],
            "scope": row["scope"],
            "is_bip": bool(row.get("is_bip")),
        })
    present = [name for name in MIGRATION_LAYERS if layers[name]]
    return {
        "allowed_layers": list(MIGRATION_LAYERS),
        "present_layers": present,
        "layers": layers,
        "counts": dict([(name, len(layers[name])) for name in MIGRATION_LAYERS]),
        "total_count": sum([len(layers[name]) for name in MIGRATION_LAYERS]),
    }


def _unique_index(rows, key_name):
    grouped = {}
    for row in rows or []:
        key = _text(row.get(key_name, ""))
        if key:
            grouped.setdefault(key, []).append(row)
    return grouped


def _structural_key(row):
    return u"|".join((
        canonical_layer_name(row.get("layer_name", row.get("contract_layer", ""))).lower(),
        _text(row.get("class_name", "")).strip().lower(),
        _text(row.get("superclass_name", "")).strip().lower(),
        _text(row.get("parent_name", "")).strip().lower(),
    ))


def contract_object_id(row):
    layer = canonical_layer_name(row.get("layer_name", row.get("contract_layer", "")))
    guid = _text(row.get("rr_guid", "")).strip()
    if guid:
        identity = u"guid:{0}".format(guid.lower())
    else:
        identity = u"name:{0}|class:{1}|parent:{2}".format(
            _text(row.get("name", "")).strip().lower(),
            _text(row.get("class_name", "")).strip().lower(),
            _text(row.get("parent_name", "")).strip().lower(),
        )
    return u"{0}|{1}".format(layer.lower(), identity)


def _public_contract_row(row):
    return {
        "contract_id": contract_object_id(row),
        "name": _text(row.get("name", "")),
        "rr_guid": _text(row.get("rr_guid", "")),
        "class_name": _text(row.get("class_name", "")),
        "superclass_name": _text(row.get("superclass_name", "")),
        "parent_name": _text(row.get("parent_name", "")),
        "contract_layer": canonical_layer_name(row.get("layer_name", row.get("contract_layer", ""))),
        "scope": _text(row.get("scope", "")) or layer_scope(row.get("layer_name", row.get("contract_layer", ""))),
        "is_bip": bool(row.get("is_bip")),
    }


def compare_binding_contracts(source_rows, target_rows):
    """Return source-only and target-only members of the six-layer contract."""
    source = contract_rows(source_rows)
    target = contract_rows(target_rows)
    target_by_guid = _unique_index(target, "rr_guid")
    target_by_name_layer = {}
    target_by_structure = {}
    for row in target:
        name_key = (row.get("contract_layer", "").lower(), _text(row.get("name", "")).lower())
        if name_key[1]:
            target_by_name_layer.setdefault(name_key, []).append(row)
        target_by_structure.setdefault(_structural_key(row), []).append(row)

    claimed = set()
    source_only = []
    for row in source:
        matches = []
        guid = _text(row.get("rr_guid", ""))
        name = _text(row.get("name", ""))
        if guid:
            matches = target_by_guid.get(guid, [])
        if len(matches) != 1 and name:
            matches = target_by_name_layer.get((row.get("contract_layer", "").lower(), name.lower()), [])
        if len(matches) != 1 and not name:
            matches = target_by_structure.get(_structural_key(row), [])
        if len(matches) == 1 and id(matches[0]) not in claimed:
            claimed.add(id(matches[0]))
        else:
            source_only.append(_public_contract_row(row))

    target_only = [
        _public_contract_row(row) for row in target if id(row) not in claimed
    ]
    signature_payload = {
        "source_only": sorted([row["contract_id"] for row in source_only]),
        "target_only": sorted([row["contract_id"] for row in target_only]),
    }
    serialized = json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)
    if isinstance(serialized, _text_type):
        serialized = serialized.encode("utf-8")
    signature = hashlib.sha1(serialized).hexdigest()
    return {
        "source_only": source_only,
        "target_only": target_only,
        "signature": signature,
        "has_difference": bool(source_only or target_only),
        "summary": {
            "source_only_count": len(source_only),
            "target_only_count": len(target_only),
        },
    }


def reconcile_animation_membership(binding_rows, animation_rows,
                                   ignore_ambiguous_names=False):
    """Resolve animation nodes from the source binding's authoritative layers.

    The normalized contract layer is the first identity boundary. Objects in
    known panel/helper layers never enter any identity index. A node moved to an
    otherwise unlisted layer remains recoverable through rrGuid or a unique
    exact name. Missing and ambiguous binding members cannot use the fallback.
    """
    expected = contract_rows(binding_rows)
    # Keep the original row objects so claimed identity also excludes them from
    # the later extra-member pass. contract_rows() intentionally returns copies.
    strict_rows = [row for row in (animation_rows or []) if is_contract_member(row)]
    fallback_rows = [
        row for row in (animation_rows or [])
        if not is_ignored_animation_row(row)
    ]
    fallback_by_guid = _unique_index(fallback_rows, "rr_guid")
    fallback_by_name = _unique_index(fallback_rows, "name")
    strict_by_guid_layer = {}
    strict_by_name_layer = {}
    for row in strict_rows:
        name = _text(row.get("name", ""))
        guid = _text(row.get("rr_guid", ""))
        layer = canonical_layer_name(row.get("layer_name", ""))
        if guid and layer:
            strict_by_guid_layer.setdefault((layer.lower(), guid), []).append(row)
        if name and layer:
            strict_by_name_layer.setdefault((layer.lower(), name), []).append(row)
    by_structure = {}
    for row in strict_rows:
        by_structure.setdefault(_structural_key(row), []).append(row)
    resolved = []
    moved = []
    missing = []
    ambiguous = []
    ignored_ambiguous = []
    claimed_ids = set()

    for source in expected:
        matches = []
        method = u""
        guid = _text(source.get("rr_guid", ""))
        name = _text(source.get("name", ""))
        source_layer = source.get("contract_layer", "")
        if guid:
            matches = strict_by_guid_layer.get((source_layer.lower(), guid), [])
            if len(matches) == 1:
                method = "same_contract_layer_rr_guid"
        if len(matches) != 1:
            matches = strict_by_name_layer.get((source_layer.lower(), name), []) if name else []
            method = "same_contract_layer_exact_name" if len(matches) == 1 else u""
        # Some legacy panels contain one genuinely unnamed Line.  A unique
        # layer/class/parent match is stable enough to recover it without
        # pretending that the parent itself was the failing object.
        if len(matches) != 1 and not name:
            matches = by_structure.get(_structural_key(source), [])
            method = "unique_layer_class_parent" if len(matches) == 1 else u""
        # The fallback remains available for animator-moved controls, but known
        # panel/helper layers were removed before these indices were built.
        if not matches and guid:
            matches = fallback_by_guid.get(guid, [])
            method = "moved_rr_guid" if len(matches) == 1 else u""
        if not matches and name:
            matches = fallback_by_name.get(name, [])
            method = "moved_exact_name" if len(matches) == 1 else u""
        if not matches:
            missing.append({
                "name": name,
                "rr_guid": guid,
                "expected_layer": source.get("contract_layer", ""),
                "reason": "missing_animation_object",
                "contract_id": contract_object_id(source),
            })
            continue
        if len(matches) != 1:
            item = {
                "name": name,
                "rr_guid": guid,
                "expected_layer": source.get("contract_layer", ""),
                "match_count": len(matches),
                "reason": "ambiguous_animation_object",
                "contract_id": contract_object_id(source),
                "ambiguity_kind": "duplicate_name" if name and not guid else "identity_collision",
            }
            if ignore_ambiguous_names and item["ambiguity_kind"] == "duplicate_name":
                item["reason"] = "ignored_duplicate_animation_name"
                ignored_ambiguous.append(item)
                for match in matches:
                    claimed_ids.add(id(match))
            else:
                ambiguous.append(item)
            continue
        animation = matches[0]
        claimed_ids.add(id(animation))
        item = dict(animation)
        item["contract_layer"] = source.get("contract_layer", "")
        item["scope"] = source.get("scope", "")
        item["membership_method"] = method
        item["binding_name"] = name
        item["binding_class_name"] = source.get("class_name", "")
        item["contract_id"] = contract_object_id(source)
        current_layer = canonical_layer_name(animation.get("layer_name", ""))
        if current_layer != source.get("contract_layer", ""):
            moved.append({
                "name": _text(animation.get("name", "")),
                "rr_guid": guid,
                "expected_layer": source.get("contract_layer", ""),
                "animation_layer": _text(animation.get("layer_name", "")),
                "method": method,
            })
        resolved.append(item)

    extras = []
    for row in animation_rows or []:
        if not is_contract_member(row) or id(row) in claimed_ids:
            continue
        current_layer = canonical_layer_name(row.get("layer_name", ""))
        extras.append({
            "name": _text(row.get("name", "")),
            "rr_guid": _text(row.get("rr_guid", "")),
            "animation_layer": current_layer,
            "reason": "not_in_source_binding_contract",
            "contract_id": contract_object_id(row),
        })

    drift = bool(moved or missing or ambiguous or ignored_ambiguous or extras)
    recoverable = not bool(missing or ambiguous)
    return {
        "ok": not drift,
        "drift": drift,
        "recoverable": recoverable,
        "requires_layer_fallback": bool(moved or extras),
        "fallback_mode": "source_binding_membership",
        "resolved_rows": resolved,
        "moved": moved,
        "missing": missing,
        "ambiguous": ambiguous,
        "ignored_ambiguous": ignored_ambiguous,
        "extras": extras,
        "summary": {
            "expected_count": len(expected),
            "resolved_count": len(resolved),
            "moved_count": len(moved),
            "missing_count": len(missing),
            "ambiguous_count": len(ambiguous),
            "ignored_ambiguous_count": len(ignored_ambiguous),
            "extra_count": len(extras),
        },
    }


def public_membership(result, fallback_used=False):
    result = result or {}
    out = dict([(key, value) for key, value in result.items() if key != "resolved_rows"])
    out["fallback_used"] = bool(fallback_used)
    out["resolved"] = [
        {
            "name": _text(row.get("name", "")),
            "binding_name": _text(row.get("binding_name", "")),
            "rr_guid": _text(row.get("rr_guid", "")),
            "expected_layer": _text(row.get("contract_layer", "")),
            "animation_layer": _text(row.get("layer_name", "")),
            "method": _text(row.get("membership_method", "")),
            "contract_id": _text(row.get("contract_id", "")),
        }
        for row in (result.get("resolved_rows", []) or [])
    ]
    return out

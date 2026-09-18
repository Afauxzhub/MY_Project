# -*- coding: utf-8 -*-
"""Object selection for the root-hierarchy binding-update route.

Simple mobs and other non-performance models never got a complete six-layer
contract, so their animator interface cannot be read from layer membership.
Everything under the rig Root is migrated instead: BIP nodes travel in the whole
``.bip`` exactly as on the layer-contract route, and every other descendant goes
through the same native Save/Load Animation transport.

The selected objects report one synthetic contract layer, :data:`ROOT_LAYER`, so
every downstream consumer - transport plans, key clearing, verification, skip
reports - keeps working on the grouping it already understands.
"""
from __future__ import print_function

import hashlib
import json

from anim_migration.migration.canonical_bridge import (
    _as_text,
    _class_name,
    _find_bip_root,
    _node_name,
    _superclass_name,
    semantic_scope,
)
from anim_migration.workflow.layer_contract import contract_object_id

ROOT_LAYER = u"Root"
ROOT_NODE_NAME = u"Root"
# Cameras stay source-owned shot data: the camera bundle merge carries them.
EXCLUDED_SCOPES = ("camera",)


def _node_handle(rt, node):
    try:
        return int(rt.getHandleByAnim(node))
    except Exception:
        return None


def _children(node):
    try:
        return list(node.children)
    except Exception:
        return []


def _top_ancestor(node):
    seen = set()
    current = node
    while True:
        try:
            parent = current.parent
        except Exception:
            return current
        if parent is None:
            return current
        key = _as_text(getattr(parent, "name", u""))
        if key in seen:
            return current
        seen.add(key)
        current = parent


def resolve_root_node(rt):
    """Find the rig Root: the node named ``Root``, else Bip001's top ancestor."""
    try:
        node = rt.getNodeByName(ROOT_NODE_NAME, ignoreCase=True)
    except Exception:
        node = None
    if node is not None:
        return node, "named_root_node", _node_name(node)
    bip = _find_bip_root(rt)
    if bip is None:
        return None, "not_found", u""
    top = _top_ancestor(bip)
    return top, "bip_top_ancestor", _node_name(top)


def root_descendant_handles(rt, root_node):
    """Handles of the Root and everything under it, safe against parent cycles."""
    seen = set()
    stack = [root_node]
    while stack:
        node = stack.pop()
        handle = _node_handle(rt, node)
        if handle is None or handle in seen:
            continue
        seen.add(handle)
        stack.extend(_children(node))
    return seen


def select_root_hierarchy(rt, rows):
    """Return the Root hierarchy rows, re-tagged onto the synthetic Root layer.

    ``rows`` are scene descriptors. Their class metadata is only filled in for
    the six tracked layers, and this route needs it for both camera detection and
    the stable contract id, so it is read here for the selected nodes only.
    """
    root_node, method, root_name = resolve_root_node(rt)
    if root_node is None:
        return {
            "ok": False,
            "error_code": "LAYER-XAF-ROOT-MISSING",
            "message": u"场景里找不到 Root 骨骼，也找不到 Bip001，无法按 Root 层级迁移",
            "root_name": u"",
            "root_method": method,
            "rows": [],
        }
    handles = root_descendant_handles(rt, root_node)
    selected = []
    excluded = []
    for row in rows or []:
        node = row.get("_node")
        if node is None or _node_handle(rt, node) not in handles:
            continue
        row = dict(row)
        if not _as_text(row.get("class_name", u"")):
            row["class_name"] = _class_name(rt, node)
            row["superclass_name"] = _superclass_name(rt, node)
        row["scope"] = semantic_scope(
            _as_text(row.get("name", u"")),
            _as_text(row.get("layer_name", u"")),
            _as_text(row.get("class_name", u"")),
            _as_text(row.get("superclass_name", u"")),
        )
        row["contract_layer"] = ROOT_LAYER
        row["selection_route"] = "root_hierarchy"
        if row["scope"] in EXCLUDED_SCOPES:
            excluded.append(row)
            continue
        selected.append(row)
    return {
        "ok": True,
        "error_code": None,
        "message": u"",
        "root_name": root_name,
        "root_method": method,
        "rows": selected,
        "object_count": len(selected),
        "bip_count": len([row for row in selected if row.get("is_bip")]),
        "excluded_camera_count": len(excluded),
    }


def build_root_hierarchy_index(rows):
    """Index the target rows by rrGuid and by lowered name."""
    index = {"by_guid": {}, "by_name": {}}
    for row in rows or []:
        guid = _as_text(row.get("rr_guid", u"")).strip()
        if guid:
            index["by_guid"].setdefault(guid, []).append(row)
        name = _as_text(row.get("name", u"")).strip().lower()
        if name:
            index["by_name"].setdefault(name, []).append(row)
    return index


def match_root_hierarchy_target(row, index):
    """Resolve one source row against the target index: rrGuid, then exact name.

    Returns the candidate list and the method that produced it, so the caller can
    report an ambiguous name the same way the layer-contract route does.
    """
    index = index or {}
    guid = _as_text((row or {}).get("rr_guid", u"")).strip()
    if guid:
        matches = (index.get("by_guid", {}) or {}).get(guid, [])
        if len(matches) == 1:
            return matches, "rr_guid"
    name = _as_text((row or {}).get("name", u"")).strip().lower()
    return (index.get("by_name", {}) or {}).get(name, []), "exact_name"


def pair_names_by_identity(source_rows, target_rows):
    """``{source_name: target_name}`` for uniquely resolved pairs."""
    index = build_root_hierarchy_index(target_rows)
    mapping = {}
    for row in source_rows or []:
        name = _as_text(row.get("name", u""))
        if not name:
            continue
        matches, _method = match_root_hierarchy_target(row, index)
        if len(matches) == 1:
            mapping[name] = _as_text(matches[0].get("name", u""))
    return mapping


def _public_row(row):
    return {
        "contract_id": contract_object_id(row),
        "name": _as_text(row.get("name", u"")),
        "rr_guid": _as_text(row.get("rr_guid", u"")),
        "class_name": _as_text(row.get("class_name", u"")),
        "superclass_name": _as_text(row.get("superclass_name", u"")),
        "parent_name": _as_text(row.get("parent_name", u"")),
        "contract_layer": ROOT_LAYER,
        "scope": _as_text(row.get("scope", u"")),
        "is_bip": bool(row.get("is_bip")),
    }


def root_hierarchy_membership(rows):
    """Membership view for this route: the Root hierarchy is the scope itself.

    The layer-contract route reconciles the animation against the source
    binding's contract. Here the animation scene's own Root hierarchy is
    authoritative, so nothing can drift out of it; the pairing against the target
    binding is what reports a control that cannot travel.
    """
    resolved = []
    for row in rows or []:
        item = dict(row)
        item["contract_layer"] = ROOT_LAYER
        item["membership_method"] = "root_hierarchy_descendant"
        item["binding_name"] = _as_text(row.get("name", u""))
        item["binding_class_name"] = _as_text(row.get("class_name", u""))
        item["contract_id"] = contract_object_id(item)
        resolved.append(item)
    return {
        "ok": True,
        "drift": False,
        "recoverable": True,
        "requires_layer_fallback": False,
        "fallback_mode": "root_hierarchy",
        "resolved_rows": resolved,
        "moved": [],
        "missing": [],
        "ambiguous": [],
        "ignored_ambiguous": [],
        "extras": [],
        "summary": {
            "expected_count": len(resolved),
            "resolved_count": len(resolved),
            "moved_count": 0,
            "missing_count": 0,
            "ambiguous_count": 0,
            "ignored_ambiguous_count": 0,
            "extra_count": 0,
        },
    }


def compare_root_hierarchy(source_rows, target_rows):
    """Diff two bindings' Root hierarchies, shaped like the contract diff.

    The animator still confirms real binding differences once, so the payload
    matches :func:`compare_binding_contracts` exactly, including the signature the
    review dialog remembers.
    """
    index = build_root_hierarchy_index(target_rows)
    claimed = set()
    source_only = []
    for row in source_rows or []:
        matches, _method = match_root_hierarchy_target(row, index)
        if len(matches) == 1 and id(matches[0]) not in claimed:
            claimed.add(id(matches[0]))
            continue
        source_only.append(_public_row(row))
    target_only = [
        _public_row(row) for row in (target_rows or []) if id(row) not in claimed
    ]
    payload = {
        "source_only": sorted([row["contract_id"] for row in source_only]),
        "target_only": sorted([row["contract_id"] for row in target_only]),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if not isinstance(serialized, bytes):
        serialized = serialized.encode("utf-8")
    return {
        "source_only": source_only,
        "target_only": target_only,
        "signature": hashlib.sha1(serialized).hexdigest(),
        "has_difference": bool(source_only or target_only),
        "scope": "root_hierarchy",
        "summary": {
            "source_only_count": len(source_only),
            "target_only_count": len(target_only),
        },
    }


def constraint_managed_owner_names(constraint_plan):
    """Target owners the three-way constraint policy speaks for.

    Their List slots are rewritten by the constraint rebuild after the target
    shape scan, so this route must leave their keys and slots alone exactly like
    the layer-contract route leaves the ``Bones`` layer alone.
    """
    names = set()
    for row in (constraint_plan or {}).get("decisions", []) or []:
        name = _as_text(row.get("owner_target_name", u"")).strip().lower()
        if name:
            names.add(name)
    return names

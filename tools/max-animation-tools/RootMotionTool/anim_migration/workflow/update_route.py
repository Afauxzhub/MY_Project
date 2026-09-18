# -*- coding: utf-8 -*-
"""Which object-selection route a binding update takes.

Both routes share one transport: full BIP, three-way Bones constraints, and Max
native Save/Load Animation per group. They differ only in how the animator
interface is discovered.

``layer_contract``
    The source binding's six layers are the contract. This is the production
    route for character rigs, where the layer contract is maintained.

``root_hierarchy``
    Everything under the rig Root is migrated, without consulting the layer
    contract. Simple mobs and other non-performance models never got a complete
    six-layer contract, so filtering by layer would silently drop their
    controls.

A rig stays on the layer-contract route when its type token is ``Role`` (a
playable character, in-game or out-of-game alike) or when the binding is an
out-of-game ``cs`` rig, because those are the files performance shots are
authored in. Everything else - a non-``Role`` in-game ``lod`` binding - takes the
root-hierarchy route.
"""
from __future__ import print_function

import os

from anim_migration.workflow.context import INGAME_TYPES

try:
    _text_type = unicode
except NameError:
    _text_type = str


ROUTE_LAYER_CONTRACT = u"layer_contract"
ROUTE_ROOT_HIERARCHY = u"root_hierarchy"

# Playable characters keep the layer contract even for in-game actions.
LAYER_CONTRACT_TYPE_TOKENS = (u"role",)
# Out-of-game bindings are performance rigs whatever their type token is.
LAYER_CONTRACT_BINDING_CATEGORIES = (u"cs",)
BINDING_CATEGORIES = (u"lod", u"cs")

ROUTE_LABELS = {
    ROUTE_LAYER_CONTRACT: u"主线（六层合同）",
    ROUTE_ROOT_HIERARCHY: u"支线（Root 层级）",
}

_REASON_MESSAGES = {
    "role_character_rig": u"角色绑定（Role），按六层合同迁移",
    "out_game_cs_binding": u"局外演出绑定（cs），按六层合同迁移",
    "in_game_non_role_rig": u"非 Role 的局内绑定，按 Root 层级迁移",
    "unclassified_default_layer_contract": u"文件名无法判定类型，按六层合同迁移",
}


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _name_tokens(path_or_name):
    stem = os.path.splitext(os.path.basename(_as_text(path_or_name)))[0]
    return [token for token in stem.split("_") if token]


def binding_identity(path_or_name):
    """Read type/character/category out of ``Type_Char_{lod|cs}_skin_Vnn.max``."""
    tokens = _name_tokens(path_or_name)
    identity = {"type_token": u"", "character": u"", "binding_category": u""}
    if len(tokens) < 3:
        return identity
    category = tokens[2].lower()
    if category not in BINDING_CATEGORIES:
        return identity
    identity.update({
        "type_token": tokens[0],
        "character": tokens[1],
        "binding_category": category,
    })
    return identity


def animation_identity(path_or_name):
    """Read the type token out of an in-game animation name, if it has one.

    Only in-game animations carry a type token in the first field, so a name that
    parses here belongs to an ``lod`` binding. Out-of-game animations lead with a
    module code instead and stay unclassified for the target binding to decide.
    """
    tokens = _name_tokens(path_or_name)
    identity = {"type_token": u"", "character": u"", "binding_category": u""}
    if len(tokens) >= 3 and tokens[0] in INGAME_TYPES:
        identity.update({
            "type_token": tokens[0],
            "character": tokens[1],
            "binding_category": u"lod",
        })
    return identity


def resolve_update_route(target_rig_path=u"", source_rig_path=u"", animation_path=u""):
    """Decide the selection route for one binding update.

    The target binding names both the rig type and the in/out-of-game category,
    so it decides. The source binding and then the animation file only stand in
    when the target name does not parse.
    """
    identity = {"type_token": u"", "character": u"", "binding_category": u""}
    decided_from = u""
    for source_name, path, reader in (
        (u"target_binding", target_rig_path, binding_identity),
        (u"source_binding", source_rig_path, binding_identity),
        (u"animation", animation_path, animation_identity),
    ):
        if not _as_text(path):
            continue
        candidate = reader(path)
        if candidate.get("type_token") or candidate.get("binding_category"):
            identity = candidate
            decided_from = source_name
            break

    type_token = _as_text(identity.get("type_token", u""))
    category = _as_text(identity.get("binding_category", u""))
    if type_token.lower() in LAYER_CONTRACT_TYPE_TOKENS:
        route, reason = ROUTE_LAYER_CONTRACT, "role_character_rig"
    elif category in LAYER_CONTRACT_BINDING_CATEGORIES:
        route, reason = ROUTE_LAYER_CONTRACT, "out_game_cs_binding"
    elif category in BINDING_CATEGORIES and type_token:
        route, reason = ROUTE_ROOT_HIERARCHY, "in_game_non_role_rig"
    else:
        # An unreadable name must not silently widen the migration scope, so it
        # falls back to the stricter contract route.
        route, reason = ROUTE_LAYER_CONTRACT, "unclassified_default_layer_contract"
    return {
        "route": route,
        "reason": reason,
        "message": _REASON_MESSAGES.get(reason, u""),
        "label": ROUTE_LABELS.get(route, u""),
        "type_token": type_token,
        "character": _as_text(identity.get("character", u"")),
        "binding_category": category,
        "decided_from": decided_from,
    }


def is_root_hierarchy_route(route):
    return _as_text(route) == ROUTE_ROOT_HIERARCHY

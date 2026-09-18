# -*- coding: utf-8 -*-
from __future__ import print_function

import difflib
import re


try:
    _text_type = unicode
except NameError:
    _text_type = str


MIN_ACCEPT_SCORE = 72.0
MIN_SCORE_MARGIN = 12.0
GENERIC_LAYER_NAMES = set((
    "bone", "bones", "help", "helper", "helpers", "ctrl", "control", "controls",
    "rig", "skin", u"骨骼", u"辅助", u"控制器",
))


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _class_name(rt, value):
    try:
        return _as_text(rt.classOf(value))
    except Exception:
        return u""


def _node_name(node):
    try:
        return _as_text(node.name)
    except Exception:
        return u""


def _layer_name(node):
    try:
        return _as_text(node.layer.name)
    except Exception:
        return u""


def _layer_path(node):
    names = []
    try:
        layer = node.layer
    except Exception:
        layer = None
    visited = set()
    while layer is not None and len(names) < 32:
        try:
            identity = id(layer)
            if identity in visited:
                break
            visited.add(identity)
        except Exception:
            pass
        try:
            name = _as_text(layer.name)
        except Exception:
            name = u""
        if name:
            names.insert(0, name)
        try:
            layer = layer.getParent()
        except Exception:
            layer = None
    return u"/".join(names)


def _parent_name(node):
    try:
        return _node_name(node.parent) if node.parent is not None else u""
    except Exception:
        return u""


def _child_count(node):
    try:
        return len(list(node.children))
    except Exception:
        return 0


def scene_layer_inventory(rt):
    rows = []
    name_counts = {}
    for node in list(rt.objects):
        name = _node_name(node)
        if not name:
            continue
        name_counts[name] = name_counts.get(name, 0) + 1
        rows.append({
            "name": name,
            "class_name": _class_name(rt, node),
            "layer_name": _layer_name(node),
            "layer_path": _layer_path(node),
            "parent_name": _parent_name(node),
            "child_count": _child_count(node),
        })
    return {"nodes": rows, "name_counts": name_counts}


def _normalize(value):
    text = _as_text(value).lower()
    return re.sub(r"[\s_\-\.:/\\]+", u"", text)


def _class_family(value):
    text = _normalize(value)
    if "biped" in text or "bone" in text:
        return "bone"
    if any(token in text for token in ("dummy", "point", "helper")):
        return "helper"
    if any(token in text for token in ("circle", "line", "rectangle", "spline", "shape")):
        return "control_shape"
    return text


def _is_mappable(row):
    layer = _normalize(row.get("layer_path", "") or row.get("layer_name", ""))
    if not layer or layer in ("0", "default", u"默认"):
        return False
    return _class_family(row.get("class_name", "")) in ("bone", "helper", "control_shape")


def _has_specific_layer(row):
    layer_name = _normalize(row.get("layer_name", ""))
    return bool(layer_name) and layer_name not in GENERIC_LAYER_NAMES


def _side_token(value):
    text = _as_text(value).lower()
    left = bool(re.search(r"(^|[_\-.\s])(l|left)(?=$|[_\-.\s\d])", text)) or u"左" in text
    right = bool(re.search(r"(^|[_\-.\s])(r|right)(?=$|[_\-.\s\d])", text)) or u"右" in text
    if left and not right:
        return "L"
    if right and not left:
        return "R"
    return ""


def _index_token(value):
    matches = re.findall(r"(\d+)", _as_text(value))
    return int(matches[-1]) if matches else None


def _ratio(left, right):
    left = _normalize(left)
    right = _normalize(right)
    if not left or not right:
        return 0.0
    return float(difflib.SequenceMatcher(None, left, right).ratio())


def _same_layer(source, target):
    source_path = _normalize(source.get("layer_path", ""))
    target_path = _normalize(target.get("layer_path", ""))
    if source_path and source_path == target_path:
        return True, "layer_path"
    source_name = _normalize(source.get("layer_name", ""))
    target_name = _normalize(target.get("layer_name", ""))
    return bool(source_name and source_name == target_name), "layer_name"


def score_layer_candidate(source, target):
    same_layer, layer_method = _same_layer(source, target)
    if not same_layer:
        return None
    source_family = _class_family(source.get("class_name", ""))
    target_family = _class_family(target.get("class_name", ""))
    if source_family != target_family:
        return None
    source_side = _side_token(source.get("name", ""))
    target_side = _side_token(target.get("name", ""))
    if source_side and target_side and source_side != target_side:
        return None
    source_index = _index_token(source.get("name", ""))
    target_index = _index_token(target.get("name", ""))
    if source_index is not None and target_index is not None and source_index != target_index:
        return None
    name_ratio = _ratio(source.get("name", ""), target.get("name", ""))
    parent_ratio = _ratio(source.get("parent_name", ""), target.get("parent_name", ""))
    score = 40.0
    score += 15.0
    if source_side and target_side:
        score += 10.0
    elif not source_side and not target_side:
        score += 4.0
    if source_index is not None and target_index is not None:
        score += 20.0
    elif source_index is None and target_index is None:
        score += 5.0
    score += 25.0 * name_ratio
    score += 8.0 * parent_ratio
    if int(source.get("child_count", 0)) == int(target.get("child_count", 0)):
        score += 3.0
    return {
        "score": round(score, 3),
        "layer_match": layer_method,
        "name_similarity": round(name_ratio, 4),
        "parent_similarity": round(parent_ratio, 4),
        "class_family": source_family,
    }


def build_layer_mapping(source_inventory, target_inventory, explicit_mapping=None):
    explicit_mapping = explicit_mapping or {}
    source_rows = (source_inventory or {}).get("nodes", []) or []
    target_rows = (target_inventory or {}).get("nodes", []) or []
    source_counts = (source_inventory or {}).get("name_counts", {}) or {}
    target_counts = (target_inventory or {}).get("name_counts", {}) or {}
    source_by_name = dict([(_as_text(row.get("name", "")), row) for row in source_rows if _as_text(row.get("name", ""))])
    target_by_name = dict([(_as_text(row.get("name", "")), row) for row in target_rows if _as_text(row.get("name", ""))])
    reserved_targets = set([
        _as_text(target_name)
        for target_name in explicit_mapping.values()
        if _as_text(target_name)
    ])
    reserved_targets.update([
        source_name for source_name in source_counts.keys()
        if source_counts.get(source_name, 0) == 1 and target_counts.get(source_name, 0) == 1
    ])
    proposals = []
    audit = []
    for source in source_rows:
        source_name = _as_text(source.get("name", ""))
        if not source_name or source_counts.get(source_name, 0) != 1:
            continue
        if source_name in explicit_mapping:
            audit.append({"source_name": source_name, "target_name": explicit_mapping.get(source_name), "status": "explicit_mapping", "method": "explicit"})
            continue
        if target_counts.get(source_name, 0) == 1:
            audit.append({"source_name": source_name, "target_name": source_name, "status": "same_name", "method": "same_name"})
            continue
        if not _is_mappable(source):
            continue
        candidates = []
        for target in target_rows:
            target_name = _as_text(target.get("name", ""))
            if not target_name or target_counts.get(target_name, 0) != 1:
                continue
            if target_name in reserved_targets:
                continue
            detail = score_layer_candidate(source, target)
            if detail is None:
                continue
            item = dict(detail)
            item["source_name"] = source_name
            item["target_name"] = target_name
            item["source_layer"] = source.get("layer_path", "") or source.get("layer_name", "")
            item["target_layer"] = target.get("layer_path", "") or target.get("layer_name", "")
            item["source_parent"] = source.get("parent_name", "")
            item["target_parent"] = target.get("parent_name", "")
            candidates.append(item)
        candidates.sort(key=lambda row: (-float(row.get("score", 0.0)), _as_text(row.get("target_name", "")).lower()))
        if not candidates:
            audit.append({"source_name": source_name, "target_name": u"", "status": "no_same_layer_candidate", "method": "auto_layer"})
            continue
        best = candidates[0]
        second_score = float(candidates[1].get("score", 0.0)) if len(candidates) > 1 else 0.0
        best["score_margin"] = round(float(best.get("score", 0.0)) - second_score, 3)
        best["candidate_count"] = len(candidates)
        if float(best.get("score", 0.0)) < MIN_ACCEPT_SCORE:
            best["status"] = "low_confidence"
            audit.append(best)
            continue
        if len(candidates) > 1 and best["score_margin"] < MIN_SCORE_MARGIN:
            best["status"] = "ambiguous"
            best["alternatives"] = candidates[1:4]
            audit.append(best)
            continue
        best["status"] = "proposed"
        proposals.append(best)

    target_claims = {}
    for proposal in proposals:
        target_claims.setdefault(proposal.get("target_name", ""), []).append(proposal)
    unique_proposals = []
    for proposal in proposals:
        claims = target_claims.get(proposal.get("target_name", ""), [])
        if len(claims) != 1:
            item = dict(proposal)
            item["status"] = "ambiguous_target_claim"
            item["claiming_sources"] = sorted([row.get("source_name", "") for row in claims])
            audit.append(item)
            continue
        unique_proposals.append(dict(proposal))

    anchors = {}
    for source_name, target_name in explicit_mapping.items():
        anchors[_as_text(source_name)] = _as_text(target_name)
    for source_name in source_counts.keys():
        if source_counts.get(source_name, 0) == 1 and target_counts.get(source_name, 0) == 1:
            anchors[source_name] = source_name

    proposal_by_source = dict([(row.get("source_name", ""), row) for row in unique_proposals])
    adjacency = dict([(row.get("source_name", ""), set()) for row in unique_proposals])
    for proposal in unique_proposals:
        source_name = proposal.get("source_name", "")
        source_parent = proposal.get("source_parent", "")
        target_parent = proposal.get("target_parent", "")
        parent_proposal = proposal_by_source.get(source_parent)
        if parent_proposal is not None and parent_proposal.get("target_name", "") == target_parent:
            adjacency[source_name].add(source_parent)
            adjacency[source_parent].add(source_name)
    sibling_groups = {}
    for proposal in unique_proposals:
        source_parent = _as_text(proposal.get("source_parent", ""))
        target_parent = _as_text(proposal.get("target_parent", ""))
        if source_parent and target_parent:
            sibling_groups.setdefault((source_parent, target_parent), []).append(proposal.get("source_name", ""))
    for sibling_names in sibling_groups.values():
        # A pair of numbered siblings can still be accidental on generic Bone/Help
        # layers. Three or more consistent pairs establish a usable family pattern.
        if len(sibling_names) < 3:
            continue
        first = sibling_names[0]
        for sibling_name in sibling_names[1:]:
            adjacency[first].add(sibling_name)
            adjacency[sibling_name].add(first)

    components = []
    visited = set()
    for source_name in sorted(adjacency.keys(), key=lambda value: _as_text(value).lower()):
        if source_name in visited:
            continue
        stack = [source_name]
        component = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            stack.extend(sorted(adjacency.get(current, set()) - visited))
        components.append(component)

    accepted = {}
    accepted_targets = set(reserved_targets)
    inferred_rows = []
    for component in components:
        component_set = set(component)
        component_rows = [proposal_by_source[name] for name in component]
        conflict = False
        incomplete_parent_evidence = False
        head_rows = []
        for row in component_rows:
            source_parent = _as_text(row.get("source_parent", ""))
            target_parent = _as_text(row.get("target_parent", ""))
            if source_parent in component_set:
                continue
            head_rows.append(row)
            anchored_parent = anchors.get(source_parent)
            if anchored_parent and anchored_parent != target_parent:
                conflict = True
            elif bool(source_parent) != bool(target_parent):
                conflict = True
            elif source_parent and target_parent:
                if source_parent not in source_by_name or target_parent not in target_by_name:
                    incomplete_parent_evidence = True
                elif target_parent in accepted_targets and anchored_parent != target_parent:
                    conflict = True

        hierarchy_supported = len(component_rows) >= 2 and not conflict and not incomplete_parent_evidence
        for row in component_rows:
            specific_layer = _has_specific_layer(source_by_name.get(row.get("source_name", ""), {}))
            semantic_supported = (
                float(row.get("name_similarity", 0.0)) >= 0.72 and
                float(row.get("parent_similarity", 0.0)) >= 0.5
            )
            if not conflict and (hierarchy_supported or specific_layer or semantic_supported):
                item = dict(row)
                item["status"] = "accepted"
                item["hierarchy_component_size"] = len(component_rows)
                audit.append(item)
                accepted[item.get("source_name")] = item.get("target_name")
                accepted_targets.add(item.get("target_name"))
            else:
                item = dict(row)
                item["status"] = "parent_conflict" if conflict else "insufficient_hierarchy_evidence"
                item["hierarchy_component_size"] = len(component_rows)
                audit.append(item)

        if not hierarchy_supported:
            continue
        for head in head_rows:
            source_parent = _as_text(head.get("source_parent", ""))
            target_parent = _as_text(head.get("target_parent", ""))
            if not source_parent or not target_parent:
                continue
            if source_parent in anchors or source_parent in proposal_by_source or source_parent in accepted:
                continue
            if target_parent in accepted_targets:
                continue
            source_parent_row = source_by_name.get(source_parent)
            target_parent_row = target_by_name.get(target_parent)
            if source_parent_row is None or target_parent_row is None:
                continue
            if _class_family(source_parent_row.get("class_name", "")) != _class_family(target_parent_row.get("class_name", "")):
                continue
            accepted[source_parent] = target_parent
            accepted_targets.add(target_parent)
            inferred_rows.append({
                "source_name": source_parent,
                "target_name": target_parent,
                "source_parent": source_parent_row.get("parent_name", ""),
                "target_parent": target_parent_row.get("parent_name", ""),
                "source_layer": source_parent_row.get("layer_path", "") or source_parent_row.get("layer_name", ""),
                "target_layer": target_parent_row.get("layer_path", "") or target_parent_row.get("layer_name", ""),
                "class_family": _class_family(source_parent_row.get("class_name", "")),
                "status": "accepted_hierarchy_parent",
                "method": "auto_layer_hierarchy_parent",
                "evidence_child": head.get("source_name", ""),
                "hierarchy_component_size": len(component_rows),
            })
    audit.extend(inferred_rows)

    return {
        "objects": accepted,
        "items": audit,
        "summary": {
            "accepted_count": len(accepted),
            "ambiguous_count": len([row for row in audit if _as_text(row.get("status", "")).startswith("ambiguous")]),
            "low_confidence_count": len([row for row in audit if row.get("status") == "low_confidence"]),
            "insufficient_hierarchy_count": len([row for row in audit if row.get("status") in ("insufficient_hierarchy_evidence", "parent_conflict")]),
            "hierarchy_parent_count": len(inferred_rows),
            "no_candidate_count": len([row for row in audit if row.get("status") == "no_same_layer_candidate"]),
            "source_node_count": len(source_rows),
            "target_node_count": len(target_rows),
            "min_accept_score": MIN_ACCEPT_SCORE,
            "min_score_margin": MIN_SCORE_MARGIN,
        },
    }

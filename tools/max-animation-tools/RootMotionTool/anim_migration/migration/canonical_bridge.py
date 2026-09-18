# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import json
import math
import os
import re
import time

from anim_migration.workflow.layer_contract import canonical_layer_name, compare_binding_contracts, contract_object_id, contract_rows, layer_scope, public_layer_snapshot, public_membership, reconcile_animation_membership


SCHEMA_VERSION = 7

POSITION_TOLERANCE = 0.25
ROTATION_TOLERANCE_DEGREES = 1.0
SCALE_TOLERANCE = 0.02
VISIBILITY_TOLERANCE = 0.001
FOV_TOLERANCE = 0.001

_SECONDARY_TOKENS = (
    "ribbon", "cloth", "hair", "cape", "skirt", "tail", "physics",
    u"飘带", u"布料", u"头发", u"披风", u"裙", u"物理",
)
_FACE_TOKENS = (
    "face", "brow", "eye", "mouth", "lip", "jaw", "cheek", "nose",
    u"面部", u"表情", u"眉", u"眼", u"嘴", u"唇", u"下巴", u"脸",
)
_PROP_TOKENS = (
    "weapon", "sword", "knife", "blade", "attachment", "attach", "socket",
    "prop", "wp_", "hp_", u"武器", u"刀", u"剑", u"挂点", u"附件", u"道具",
)
_CONTROL_TOKENS = ("ctrl", "control", "controller", u"控制器", u"控制")
_FACE_OUTPUT_LAYER_TOKENS = (u"面部骨骼参与输出", "face_output", "face bone output")
_DRIVEN_NODE_PREFIXES = (
    "bone_", "skinmaster_", "drv_", "hlp_", "pivot_", "zro_",
    "op_std_",
)
_DEFORM_OUTPUT_PREFIXES = (
    "bone_corr_", "bone_twist_", "skinmaster_",
)
TRANSFER_LOCAL_DELTA = "local_delta_matrix"
TRANSFER_WORLD = "world_matrix"
TRANSFER_VALIDATE_ONLY = "validate_only"
TRANSFER_TARGET_OWNED = "target_owned"


try:
    _text_type = unicode
    _string_types = (basestring,)
except NameError:
    _text_type = str
    _string_types = (str,)


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _json_write(path, value):
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(_as_text(json.dumps(value, ensure_ascii=False, indent=2)))


def _json_read(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return json.loads(stream.read())


def _safe_filename(value):
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", _as_text(value))
    return text.strip("._")[:120] or "migration"


def _binding_version_from_path(path):
    match = re.search(r"(?i)(?:^|_)v(\d{1,3})(?=\.max$|_)", os.path.basename(_as_text(path)))
    return u"v{0:02d}".format(int(match.group(1))) if match else u""


def _node_name(node):
    try:
        return _as_text(node.name)
    except Exception:
        return u""


def _class_name(rt, value):
    try:
        return _as_text(rt.classOf(value))
    except Exception:
        return u""


def _superclass_name(rt, value):
    try:
        return _as_text(rt.superClassOf(value))
    except Exception:
        return u""


def _layer_name(node):
    try:
        return _as_text(node.layer.name)
    except Exception:
        return u""


def _layer_ancestor_names(node):
    result = []
    try:
        layer = node.layer
    except Exception:
        return result
    # Layer nesting is an Explorer-only hierarchy. Keep a small hard limit to
    # guard malformed/cyclic third-party layer data in old scenes.
    for _index in range(32):
        try:
            layer = layer.getParent()
        except Exception:
            break
        if layer is None:
            break
        try:
            name = _as_text(layer.name)
        except Exception:
            name = u""
        if not name or name in result:
            break
        result.append(name)
    return result


def _parent_name(node):
    try:
        return _node_name(node.parent) if node.parent is not None else u""
    except Exception:
        return u""


def _is_bip_node(rt, node):
    name = _node_name(node).lower()
    return name.startswith("bip001")


def _has_any(text, tokens):
    lower = _as_text(text).lower()
    return any([token.lower() in lower for token in tokens])


def classify_rig_family(names):
    lower = set([_as_text(name).strip().lower() for name in names if _as_text(name).strip()])
    if "bone_skin_bip001 pelvis" in lower:
        return "cbt2"
    if any([name.startswith("bip001") for name in lower]):
        return "cbt1"
    return "unknown"


def semantic_scope(name, layer_name, class_name=u"", superclass_name=u""):
    combined = u"{0}|{1}|{2}|{3}".format(name, layer_name, class_name, superclass_name).lower()
    if "camera" in class_name.lower() or "camera" in superclass_name.lower() or _has_any(combined, ("camera", "cam_", "camera", u"镜头", u"相机")):
        return "camera"
    return layer_scope(layer_name)


def _is_face_output_layer(layer_name):
    return _has_any(layer_name, _FACE_OUTPUT_LAYER_TOKENS)


def _user_prop(rt, node, name):
    try:
        value = rt.getUserProp(node, name)
        return _as_text(value).strip()
    except Exception:
        return u""


def _node_descriptor(rt, node):
    name = _node_name(node)
    layer = _layer_name(node)
    # classOf/superClassOf on thousands of pymxs nodes produces a very noisy
    # MXSWrapperBase __class__ warning stream in Max 2020.  Name and layer are
    # the fast discovery contract; query metadata only for the small interface
    # candidate set.
    tracked_layer = canonical_layer_name(layer)
    class_name = _class_name(rt, node) if tracked_layer else u""
    superclass_name = _superclass_name(rt, node) if tracked_layer else u""
    scope = semantic_scope(name, layer, class_name, superclass_name)
    return {
        "name": name,
        "class_name": class_name,
        "superclass_name": superclass_name,
        "layer_name": layer,
        "layer_ancestor_names": _layer_ancestor_names(node),
        "parent_name": _parent_name(node),
        # rrGuid must also be read outside the six tracked layers so the
        # source-binding fallback can recover a controller moved by an animator.
        "rr_guid": _user_prop(rt, node, "rrGuid"),
        "rr_role": _user_prop(rt, node, "rrRole") if scope else u"",
        "scope": scope,
        "is_bip": _is_bip_node(rt, node),
        "is_face_output": False,
        "transfer_hint": _user_prop(rt, node, "rrTransferMode"),
        "_node": node,
    }


def _scene_descriptors(rt):
    return [_node_descriptor(rt, node) for node in list(rt.objects)]


def _public_descriptor(row):
    return dict([(key, value) for key, value in row.items() if key != "_node"])


def _name_index(rows):
    result = {}
    for row in rows:
        result.setdefault(_as_text(row.get("name", "")), []).append(row)
    return result


def _guid_index(rows):
    result = {}
    for row in rows:
        guid = _as_text(row.get("rr_guid", ""))
        if guid:
            result.setdefault(guid, []).append(row)
    return result


def _prop_alias(value):
    text = re.sub(r"\s+", "", _as_text(value).lower())
    text = re.sub(r"0*1$", "", text)
    return text


def _transfer_mode(source, target=None):
    explicit = _as_text(source.get("transfer_hint", "")).strip().lower()
    scope = source.get("scope", "")
    # Secondary simulation is authored animation once it has been solved in the
    # source shot.  Bake the evaluated output densely into the new binding.
    # A binding author may still mark a solver-internal helper validate_only.
    if scope == "secondary":
        return TRANSFER_VALIDATE_ONLY if explicit == TRANSFER_VALIDATE_ONLY else TRANSFER_LOCAL_DELTA
    if explicit in (TRANSFER_LOCAL_DELTA, TRANSFER_WORLD, TRANSFER_VALIDATE_ONLY, TRANSFER_TARGET_OWNED):
        return explicit
    if source.get("is_face_output"):
        return TRANSFER_VALIDATE_ONLY
    if scope == "camera":
        # Cameras are shot-owned and travel through the legacy whole-rig merge,
        # never through canonical sampled channels.
        return TRANSFER_TARGET_OWNED
    if scope in ("bones", "ui", "face_control", "ctrl", "body_ctrl"):
        return TRANSFER_LOCAL_DELTA
    name = _as_text(source.get("name", "")).strip().lower()
    rr_role = _as_text(source.get("rr_role", "")).strip().lower()
    if rr_role in ("standard_bridge", "driven_output", "deform_output"):
        return TRANSFER_VALIDATE_ONLY
    if name.startswith(_DRIVEN_NODE_PREFIXES) and not name.startswith("ctrl_"):
        return TRANSFER_VALIDATE_ONLY
    if scope in ("face", "control", "prop"):
        return TRANSFER_LOCAL_DELTA
    return TRANSFER_VALIDATE_ONLY


def _is_deform_output(source):
    return source.get("scope") == "deform_output"


def build_adapter_mapping(source_rows, target_rows, explicit_mapping=None,
                          source_family=u"", target_family=u""):
    explicit_mapping = explicit_mapping or {}
    target_names = _name_index(target_rows)
    target_guids = _guid_index(target_rows)
    prop_aliases = {}
    for row in target_rows:
        if row.get("scope") == "prop" and "_old_" not in row.get("name", "").lower():
            prop_aliases.setdefault(_prop_alias(row.get("name", "")), []).append(row)

    mapping = {}
    audit = []
    claimed = set()
    for source in source_rows:
        source_name = _as_text(source.get("name", ""))
        if not source_name or source.get("is_bip"):
            continue
        target = None
        method = u""
        requested = _as_text(explicit_mapping.get(source_name, ""))
        if requested:
            candidates = target_names.get(requested, [])
            if len(candidates) == 1:
                target = candidates[0]
                method = "explicit"
        if target is None and source.get("rr_guid"):
            candidates = [
                row for row in target_guids.get(source.get("rr_guid"), [])
                if row.get("contract_layer", "") == source.get("contract_layer", "")
            ]
            if len(candidates) == 1:
                target = candidates[0]
                method = "rr_guid"
        if target is None:
            candidates = [
                row for row in target_names.get(source_name, [])
                if "_old_" not in row.get("name", "").lower()
                and row.get("contract_layer", "") == source.get("contract_layer", "")
            ]
            if len(candidates) == 1:
                target = candidates[0]
                method = "exact_name"
        if target is None and source.get("scope") == "prop":
            candidates = prop_aliases.get(_prop_alias(source_name), [])
            if len(candidates) == 1:
                target = candidates[0]
                method = "unique_prop_alias"

        if target is None:
            audit.append({"source_name": source_name, "target_name": u"", "scope": source.get("scope", ""), "status": "unresolved"})
            continue
        target_name = _as_text(target.get("name", ""))
        if target_name in claimed:
            audit.append({"source_name": source_name, "target_name": target_name, "scope": source.get("scope", ""), "status": "duplicate_target"})
            continue
        claimed.add(target_name)
        mapping[source_name] = target_name
        audit.append({
            "source_name": source_name,
            "target_name": target_name,
            "source_contract_id": source.get("contract_id", ""),
            "target_contract_id": contract_object_id(target),
            "source_rr_guid": source.get("rr_guid", ""),
            "target_rr_guid": target.get("rr_guid", ""),
            "source_contract_layer": source.get("contract_layer", ""),
            "target_contract_layer": target.get("contract_layer", ""),
            "scope": source.get("scope", ""),
            "status": "mapped",
            "method": method,
            "transfer_mode": _transfer_mode(source, target),
            "source_parent": source.get("parent_name", ""),
            "target_parent": target.get("parent_name", ""),
        })
    return {
        "kind": "binding_family_adapter",
        "source_family": _as_text(source_family),
        "target_family": _as_text(target_family),
        "objects": mapping,
        "audit": audit,
    }


def _property_controller(rt, node, prop_name):
    for value in (prop_name, rt.Name(prop_name)):
        try:
            controller = rt.getPropertyController(node, value)
            if controller is not None:
                return controller
        except Exception:
            pass
    return None


def _node_controllers(rt, node, include_fov=False):
    result = []
    for name in ("transform", "position", "rotation", "scale", "visibility"):
        controller = _property_controller(rt, node, name)
        if controller is not None:
            result.append(controller)
    if include_fov:
        controller = _property_controller(rt, node, "fov")
        if controller is not None:
            result.append(controller)
    try:
        if node.controller is not None:
            result.append(node.controller)
    except Exception:
        pass
    return result


def _controller_key_times(rt, controller, visited=None, depth=0):
    if controller is None or depth > 5:
        return []
    if visited is None:
        visited = set()
    try:
        identity = id(controller)
        if identity in visited:
            return []
        visited.add(identity)
    except Exception:
        pass

    result = []
    try:
        count = int(controller.numKeys)
    except Exception:
        count = 0
    for index in range(1, count + 1):
        try:
            result.append(int(rt.getKey(controller, index).time))
        except Exception:
            pass
    try:
        sub_count = int(controller.numSubs)
    except Exception:
        sub_count = 0
    for index in range(1, sub_count + 1):
        child = None
        try:
            sub_anim = rt.getSubAnim(controller, index)
            child = sub_anim.controller
        except Exception:
            pass
        if child is not None:
            result.extend(_controller_key_times(rt, child, visited, depth + 1))
    return result


def _key_times_for_node(rt, node, include_fov=False):
    values = []
    visited = set()
    for controller in _node_controllers(rt, node, include_fov=include_fov):
        values.extend(_controller_key_times(rt, controller, visited=visited))
    return sorted(set([int(value) for value in values]))


def _matrix_to_list(matrix):
    return [
        [float(matrix.row1.x), float(matrix.row1.y), float(matrix.row1.z)],
        [float(matrix.row2.x), float(matrix.row2.y), float(matrix.row2.z)],
        [float(matrix.row3.x), float(matrix.row3.y), float(matrix.row3.z)],
        [float(matrix.row4.x), float(matrix.row4.y), float(matrix.row4.z)],
    ]


def _list_to_matrix(rt, value):
    return rt.matrix3(
        rt.Point3(float(value[0][0]), float(value[0][1]), float(value[0][2])),
        rt.Point3(float(value[1][0]), float(value[1][1]), float(value[1][2])),
        rt.Point3(float(value[2][0]), float(value[2][1]), float(value[2][2])),
        rt.Point3(float(value[3][0]), float(value[3][1]), float(value[3][2])),
    )


def _mat3_inverse(value):
    a, b, c = [float(item) for item in value[0]]
    d, e, f = [float(item) for item in value[1]]
    g, h, i = [float(item) for item in value[2]]
    determinant = (
        a * (e * i - f * h) -
        b * (d * i - f * g) +
        c * (d * h - e * g)
    )
    if abs(determinant) <= 1e-12:
        raise ValueError("matrix is singular")
    inverse_det = 1.0 / determinant
    return [
        [(e * i - f * h) * inverse_det, (c * h - b * i) * inverse_det, (b * f - c * e) * inverse_det],
        [(f * g - d * i) * inverse_det, (a * i - c * g) * inverse_det, (c * d - a * f) * inverse_det],
        [(d * h - e * g) * inverse_det, (b * g - a * h) * inverse_det, (a * e - b * d) * inverse_det],
    ]


def _row_vector_multiply(vector, matrix):
    return [
        sum([float(vector[index]) * float(matrix[index][column]) for index in range(3)])
        for column in range(3)
    ]


def _affine_multiply(left, right):
    left_rotation = [[float(value) for value in row] for row in left[:3]]
    right_rotation = [[float(value) for value in row] for row in right[:3]]
    rotation = _mat3_multiply(left_rotation, right_rotation)
    translated = _row_vector_multiply(left[3], right_rotation)
    translation = [translated[index] + float(right[3][index]) for index in range(3)]
    return rotation + [translation]


def _affine_inverse(value):
    rotation_inverse = _mat3_inverse(value[:3])
    translation = _row_vector_multiply([-float(item) for item in value[3]], rotation_inverse)
    return rotation_inverse + [translation]


def _retarget_local_matrix(source_reference, target_reference, source_animated):
    """Move source bind-relative local PRS into the target bind space.

    3ds Max matrix3 uses row-vector composition.  The portable semantic value is
    inverse(source_reference) * source_animated; applying it after the target
    reference preserves target zero groups, parent changes, axes, and scale.
    """
    delta = _affine_multiply(_affine_inverse(source_reference), source_animated)
    return _affine_multiply(target_reference, delta)


def _reference_pose_index(rt, rows, frame=0):
    """Sample neutral poses only for authoritative six-layer interfaces.

    The same display name may legally exist in ignored UI panel/helper layers.
    Those rows must never make a real animation controller's reference pose
    ambiguous. Identity is therefore scoped by the binding contract rather
    than by the scene-wide node name.
    """
    result = {
        "by_contract_id": {},
        "by_guid_layer": {},
        "by_name_layer": {},
    }
    rt.sliderTime = int(frame)
    for row in contract_rows(rows):
        if row.get("is_bip"):
            continue
        name = _as_text(row.get("name", ""))
        if not name:
            continue
        try:
            local_matrix = _sample_value(
                rt, row.get("_node"), include_matrix=False,
                include_local_matrix=True, include_visibility=False,
                include_fov=False,
            ).get("local_matrix")
        except Exception:
            local_matrix = None
        layer = canonical_layer_name(row.get("contract_layer", row.get("layer_name", "")))
        guid = _as_text(row.get("rr_guid", ""))
        entry = {
            "name": name,
            "rr_guid": guid,
            "contract_layer": layer,
            "contract_id": contract_object_id(row),
            "parent_name": row.get("parent_name", ""),
            "local_matrix": local_matrix,
        }
        result["by_contract_id"].setdefault(entry["contract_id"], []).append(entry)
        if guid and layer:
            result["by_guid_layer"].setdefault((layer.lower(), guid.lower()), []).append(entry)
        if layer:
            result["by_name_layer"].setdefault((layer.lower(), name.lower()), []).append(entry)
    return result


def _unique_reference(reference_index, row, name=u""):
    """Resolve one neutral pose without crossing a migration-layer boundary."""
    row = row or {}
    contract_id = _as_text(row.get("contract_id", ""))
    if contract_id:
        matches = (reference_index.get("by_contract_id", {}) or {}).get(contract_id, []) or []
        if len(matches) == 1:
            return matches[0]
    layer = canonical_layer_name(row.get("contract_layer", row.get("layer_name", "")))
    guid = _as_text(row.get("rr_guid", ""))
    if layer and guid:
        matches = (reference_index.get("by_guid_layer", {}) or {}).get(
            (layer.lower(), guid.lower()), []
        ) or []
        if len(matches) == 1:
            return matches[0]
    wanted_name = _as_text(name or row.get("binding_name", "") or row.get("name", ""))
    if layer and wanted_name:
        matches = (reference_index.get("by_name_layer", {}) or {}).get(
            (layer.lower(), wanted_name.lower()), []
        ) or []
        if len(matches) == 1:
            return matches[0]
    return None


def _camera_only_merge_inventory(scan_result):
    """Keep only the legacy scanner's complete camera rig bundle."""
    rows = []
    for row in (scan_result or {}).get("objects", []) or []:
        reasons = list(row.get("reasons", []) or [])
        if not any([_as_text(reason).startswith("camera") for reason in reasons]):
            continue
        rows.append(dict(row))
    return {
        "transport": "merge_source_camera_bundle",
        "objects": rows,
        "summary": {
            "object_count": len(rows),
            "pending_count": len([row for row in rows if row.get("merge_status") == "pending"]),
            "skipped_existing_count": len([row for row in rows if row.get("merge_status") != "pending"]),
        },
    }


def _scan_source_camera_bundle(rt, target_names):
    from anim_migration.migration.package_exporter import _scan_merge_helper_objects
    return _camera_only_merge_inventory(_scan_merge_helper_objects(rt, target_names))


def _sample_value(rt, node, include_matrix=True, include_local_matrix=False,
                  include_visibility=True, include_fov=False):
    value = {}
    if include_matrix:
        value["matrix"] = _matrix_to_list(node.transform)
    if include_local_matrix:
        local_matrix = node.transform
        try:
            if node.parent is not None:
                local_matrix = node.transform * rt.inverse(node.parent.transform)
        except Exception:
            local_matrix = node.transform
        value["local_matrix"] = _matrix_to_list(local_matrix)
    if include_visibility:
        try:
            value["visibility"] = float(node.visibility)
        except Exception:
            pass
    if include_fov:
        try:
            value["fov"] = float(node.fov)
        except Exception:
            pass
    return value


class suspended_scene_redraw(object):
    def __init__(self, rt):
        self.rt = rt
        self.disabled = False

    def __enter__(self):
        try:
            self.rt.disableSceneRedraw()
            self.disabled = True
        except Exception:
            self.disabled = False
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.disabled:
            try:
                self.rt.enableSceneRedraw()
            except Exception:
                pass
        return False


def _sample_rows(rt, rows, frames):
    for row in rows:
        row["samples"] = []
    with suspended_scene_redraw(rt):
        for frame in frames:
            rt.sliderTime = int(frame)
            for row in rows:
                node = row.get("_node")
                if node is None:
                    continue
                try:
                    value = _sample_value(
                        rt, node,
                        include_matrix=bool(row.get("include_matrix", True)),
                        include_local_matrix=bool(row.get("include_local_matrix", False)),
                        include_visibility=bool(row.get("include_visibility", False)),
                        include_fov=bool(row.get("include_fov", False)),
                    )
                    value["frame"] = int(frame)
                    row["samples"].append(value)
                except Exception as error:
                    row.setdefault("sample_errors", []).append({"frame": int(frame), "message": _as_text(error)})
    for row in rows:
        row.pop("_node", None)
    return rows


def _samples_change(samples, tolerance=1e-5):
    if len(samples or []) < 2:
        return False
    first = samples[0]
    for sample in samples[1:]:
        for matrix_key in ("matrix", "local_matrix"):
            if matrix_key not in first or matrix_key not in sample:
                continue
            for row in range(4):
                for column in range(3):
                    if abs(float(first[matrix_key][row][column]) - float(sample[matrix_key][row][column])) > tolerance:
                        return True
        if "visibility" in first and "visibility" in sample and abs(float(first["visibility"]) - float(sample["visibility"])) > tolerance:
            return True
        if "fov" in first and "fov" in sample and abs(float(first["fov"]) - float(sample["fov"])) > tolerance:
            return True
    return False


def _frame_range(rt):
    start = int(rt.animationRange.start)
    end = int(rt.animationRange.end)
    if end < start:
        end = start
    return start, end, list(range(start, end + 1))


def _find_bip_root(rt):
    try:
        node = rt.getNodeByName("Bip001", exact=True)
        if node is not None:
            return node
    except Exception:
        pass
    for node in list(rt.objects):
        if _is_bip_node(rt, node):
            try:
                if node.parent is None:
                    return node
            except Exception:
                return node
    return None


def _direct_controller_key_count(rt, node):
    try:
        return max(0, int(rt.numKeys(node.controller)))
    except Exception:
        return 0


def _direct_controller_key_times(rt, controller, start, end):
    frames = set()
    try:
        count = max(0, int(rt.numKeys(controller)))
    except Exception:
        count = 0
    for index in range(1, count + 1):
        frame = None
        try:
            frame = int(rt.getKeyTime(controller, index))
        except Exception:
            try:
                frame = int(rt.biped.getKey(controller, index).time)
            except Exception:
                frame = None
        if frame is not None and int(start) <= frame <= int(end):
            frames.add(frame)
    return frames


def _biped_node_key_times(rt, node, start, end):
    name = _node_name(node)
    frames = set()
    try:
        controller = node.controller
    except Exception:
        controller = None
    frames.update(_direct_controller_key_times(rt, controller, start, end))
    if name == "Bip001" and controller is not None:
        for getter_name in ("getHorizontalControl", "getVerticalControl", "getTurnControl"):
            try:
                getter = getattr(rt.biped, getter_name)
                frames.update(_direct_controller_key_times(rt, getter(controller), start, end))
            except Exception:
                pass
    return sorted(frames)


def _bip_structure_signature(rows):
    return sorted([
        (_as_text(row.get("name", "")), _as_text(row.get("parent_name", "")))
        for row in rows
        if row.get("is_bip") and row.get("name") != "Bip001 Footsteps"
    ])


def _selected_bip_tracks(rt, source_rows, target_name_set):
    """Return the complete common Biped hierarchy and position/rotation tracks."""
    unique_names = []
    track_names = []
    nodes = []
    indices = []
    active_names = []
    excluded = []
    for row in source_rows:
        if not row.get("is_bip"):
            continue
        name = _as_text(row.get("name", ""))
        if not name or name == "Bip001 Footsteps":
            continue
        key_count = _direct_controller_key_count(rt, row.get("_node"))
        if name not in target_name_set:
            excluded.append({
                "name": name,
                "reason": "missing_in_target",
                "direct_key_count": key_count,
            })
            continue
        unique_names.append(name)
        if name == "Bip001" or key_count > 0:
            active_names.append(name)
        track_indices = [1]
        if name == "Bip001" or name.endswith(" Hand") or name.endswith(" Foot"):
            track_indices.insert(0, 0)
        for index in track_indices:
            track_names.append(name)
            nodes.append(row.get("_node"))
            indices.append(index)
    return unique_names, track_names, nodes, indices, active_names, excluded


def _load_scene(rt, path):
    if not rt.loadMaxFile(path, quiet=True, useFileUnits=True):
        raise RuntimeError(u"无法加载 Max 文件: {0}".format(path))


def _body_target_name(source_name, target_name_set, target_family):
    # Both CBT1 and CBT2 publish the animation body through the Bip layer.
    # Bone_Skin_* ADV outputs are target-owned and outside the six-layer input
    # contract.
    return source_name if source_name in target_name_set else u""


def _channel_is_required(scope):
    # Writable animation interfaces are production-critical.  Driven helpers
    # never enter the channel list (their transfer mode is validate_only), so
    # every channel that does reach this gate must pass apply and result checks.
    return scope in (
        "bones", "ui", "face_control", "ctrl", "body_ctrl",
    )


def _write_text_report(path, manifest, result=None):
    result = result or {}
    source = manifest.get("source", {}) or {}
    target = manifest.get("target", {}) or {}
    summary = manifest.get("summary", {}) or {}
    validation = result.get("validation", {}) or {}
    lines = [
        u"=== Animation 六层动画迁移报告 ===",
        u"Schema: {0}".format(manifest.get("schema_version", "")),
        u"Source: {0}".format(source.get("path", "")),
        u"Source Binding Reference: {0}".format(source.get("binding_reference_path", "")),
        u"Source Family: {0}".format(source.get("family", "")),
        u"Target: {0}".format(target.get("path", "")),
        u"Target Family: {0}".format(target.get("family", "")),
        u"Animation Range: {0} -> {1}".format((manifest.get("animation_range", {}) or {}).get("start", ""), (manifest.get("animation_range", {}) or {}).get("end", "")),
        u"BIP Export: {0}".format((manifest.get("body", {}) or {}).get("export_ok", False)),
        u"Canonical Channels: {0}".format(summary.get("channel_count", 0)),
        u"Body Validation Nodes: {0}".format(summary.get("body_validation_count", 0)),
        u"Face Output Validation Nodes: {0}".format(summary.get("face_validation_count", 0)),
        u"Deform Output Validation Nodes: {0}".format(summary.get("deform_validation_count", 0)),
        u"Camera Transport: {0}".format((manifest.get("camera_merge", {}) or {}).get("transport", "none")),
        u"Camera Merge Objects: {0} (pending {1})".format(
            summary.get("camera_merge_object_count", 0),
            summary.get("camera_merge_pending_count", 0),
        ),
        u"Tracked Layers: {0}".format(summary.get("tracked_layer_count", 0)),
        u"Layer Fallback Used: {0}".format(summary.get("layer_fallback_used", False)),
        u"Transfer: six-layer contract + bind-relative local PRS (version-pair mapping disabled)",
        u"OP_STD Contract: {0}".format((manifest.get("standard_contract", {}) or {}).get("path", u"普通 CBT1/CBT2 路线不要求")),
    ]
    layer_normalization = manifest.get("layer_normalization", {}) or {}
    if layer_normalization:
        normalization_analysis = layer_normalization.get("analysis", {}) or {}
        normalization_apply = layer_normalization.get("apply", {}) or {}
        normalization_verification = layer_normalization.get("verification", {}) or {}
        lines.extend([
            u"Layer Normalization: {0}".format(layer_normalization.get("ok", False)),
            u"Layer Normalize Planned/Applied/Remaining: {0}/{1}/{2}".format(
                normalization_analysis.get("moved_total", 0),
                normalization_apply.get("moved_total", 0),
                normalization_verification.get("moved_total", 0),
            ),
            u"Layer Normalize Unclassified: {0}".format(
                len(normalization_verification.get("warnings", []) or [])
            ),
        ])
    layer_membership = ((manifest.get("layer_contract", {}) or {}).get("membership", {}) or {})
    if layer_membership:
        layer_summary = layer_membership.get("summary", {}) or {}
        lines.extend([
            u"Layer Membership Drift: {0}".format(layer_membership.get("drift", False)),
            u"Layer Drift Moved/Missing/Ambiguous/Extra: {0}/{1}/{2}/{3}".format(
                layer_summary.get("moved_count", 0), layer_summary.get("missing_count", 0),
                layer_summary.get("ambiguous_count", 0), layer_summary.get("extra_count", 0),
            ),
        ])
    binding_difference = ((manifest.get("layer_contract", {}) or {}).get("binding_difference", {}) or {})
    if binding_difference:
        difference_summary = binding_difference.get("summary", {}) or {}
        lines.extend([
            u"Binding Difference Reviewed: {0}".format(binding_difference.get("reviewed", False)),
            u"Binding Source-only/Target-only: {0}/{1}".format(
                difference_summary.get("source_only_count", 0),
                difference_summary.get("target_only_count", 0),
            ),
            u"Ignored Source/Target Difference: {0}/{1}".format(
                len(binding_difference.get("ignored_source_contract_ids", []) or []),
                len(binding_difference.get("ignored_target_contract_ids", []) or []),
            ),
        ])
    if result:
        lines.extend([
            u"",
            u"Apply OK: {0}".format(result.get("ok", False)),
            u"Output: {0}".format(result.get("output_max_path", "")),
            u"BIP Import: {0}".format((result.get("bip_import", {}) or {}).get("ok", False)),
            u"Bones Constraints: {0} missing_targets={1}".format(
                (result.get("bones_constraint_apply", {}) or {}).get("ok", False),
                (result.get("bones_constraint_apply", {}) or {}).get("missing_target_count", 0),
            ),
            u"Layer XAF: {0} failed={1}".format(
                (result.get("xaf_apply", {}) or {}).get("ok", False),
                (result.get("xaf_apply", {}) or {}).get("failed_count", 0),
            ),
            u"Applied Channels: {0}".format((result.get("summary", {}) or {}).get("applied_channel_count", 0)),
            u"Validation: {0}".format(validation.get("status", "")),
            u"Validation Passed/Failed: {0}/{1}".format((validation.get("summary", {}) or {}).get("passed_count", 0), (validation.get("summary", {}) or {}).get("failed_count", 0)),
            u"Validation Advisories: {0}".format((result.get("summary", {}) or {}).get("advisory_count", 0)),
        ])
    warnings = (result.get("warnings", []) or []) if result else (manifest.get("warnings", []) or [])
    if warnings:
        lines.append(u"")
        lines.append(u"Warnings ({0})".format(len(warnings)))
        for item in warnings[:100]:
            lines.append(u"- {0}".format(_as_text(item.get("message", item))))
    failures = (validation.get("failures", []) or [])
    if failures:
        lines.append(u"")
        lines.append(u"Validation Failures ({0})".format(len(failures)))
        for item in failures[:100]:
            lines.append(u"- {0} -> {1}: pos={2:.4f} rot={3:.4f} scale={4:.4f} frame={5}".format(
                item.get("source_name", ""), item.get("target_name", ""),
                float(item.get("max_position_error", 0.0)), float(item.get("max_rotation_error_degrees", 0.0)),
                float(item.get("max_scale_error", 0.0)), item.get("worst_frame", ""),
            ))
    advisories = result.get("validation_advisories", []) or []
    if advisories:
        lines.append(u"")
        lines.append(u"Validation Advisories ({0})".format(len(advisories)))
        for item in advisories[:100]:
            lines.append(u"- {0} -> {1} [{2}]: {3}".format(
                item.get("source_name", ""), item.get("target_name", ""),
                item.get("scope", ""), item.get("message", u"超过建议容差"),
            ))
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(u"\n".join(lines) + u"\n")


def export_canonical_package(old_anim_path, new_rig_path, output_max_path,
                             source_rig_path=None, adapter_override=None,
                             package_root=None, reference_frame=0,
                             tool_root=None, standard_contract_path=None,
                             adapter_contract_path=None,
                             allow_layer_fallback=False,
                             ignore_duplicate_animation_objects=False,
                             ignored_source_contract_ids=None,
                             ignored_target_contract_ids=None,
                             reviewed_binding_difference_signature=u""):
    import pymxs
    from anim_migration.workflow.version_metadata import read_scene_binding_metadata
    from anim_migration.workflow.layer_normalizer import normalize_loaded_animation_scene
    from anim_migration.workflow.family_contract import find_family_adapter_contract, find_standard_contract, load_family_adapter_contract, load_standard_contract, resolve_standard_roles
    from anim_migration.migration.constraint_rebuilder import scan_constraints_in_loaded_scene
    from anim_migration.migration.xaf_transfer import _try_save_xaf
    from anim_migration.migration.track_transfer import collect_node_track_signatures, json_track_signatures

    rt = pymxs.runtime
    old_anim_path = os.path.abspath(_as_text(old_anim_path))
    new_rig_path = os.path.abspath(_as_text(new_rig_path))
    output_max_path = os.path.abspath(_as_text(output_max_path))
    source_rig_path = os.path.abspath(_as_text(source_rig_path)) if source_rig_path else u""
    tool_root = os.path.abspath(_as_text(tool_root)) if tool_root else os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if not os.path.exists(old_anim_path) or not os.path.exists(new_rig_path):
        return {"ok": False, "error_code": "CANON-INPUT", "message": u"源动画或目标绑定路径无效"}
    if package_root is None:
        package_root = os.path.join(os.path.dirname(output_max_path), "_RigCanonicalPackages")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    package_dir = os.path.join(package_root, _safe_filename(os.path.splitext(os.path.basename(old_anim_path))[0]) + "_" + stamp)
    if not os.path.exists(package_dir):
        os.makedirs(package_dir)
    manifest_path = os.path.join(package_dir, "canonical_manifest.json")
    report_txt = os.path.join(package_dir, "canonical_report.txt")
    bip_path = os.path.join(package_dir, "body.bip")
    xaf_dir = os.path.join(package_dir, "layer_xaf")
    if not os.path.exists(xaf_dir):
        os.makedirs(xaf_dir)
    timings = {}
    warnings = []
    ignored_source_contract_ids = set([
        _as_text(value) for value in (ignored_source_contract_ids or []) if _as_text(value)
    ])
    ignored_target_contract_ids = set([
        _as_text(value) for value in (ignored_target_contract_ids or []) if _as_text(value)
    ])
    reviewed_binding_difference_signature = _as_text(reviewed_binding_difference_signature)

    started = time.time()
    _load_scene(rt, new_rig_path)
    target_rows = _scene_descriptors(rt)
    target_reference_index = _reference_pose_index(rt, target_rows, reference_frame)
    target_names = [_as_text(row.get("name", "")) for row in target_rows]
    target_name_set = set(target_names)
    target_family = classify_rig_family(target_names)
    try:
        target_frame_rate = float(rt.frameRate)
    except Exception:
        target_frame_rate = 30.0
    timings["load_target_inventory"] = round(time.time() - started, 3)

    stage = time.time()
    _load_scene(rt, old_anim_path)
    source_metadata = read_scene_binding_metadata(rt)
    if not source_rig_path:
        metadata_rig = _as_text(source_metadata.get("rig_path", "")).strip()
        if metadata_rig and os.path.exists(metadata_rig):
            source_rig_path = os.path.abspath(metadata_rig)
    try:
        source_frame_rate = float(rt.frameRate)
    except Exception:
        source_frame_rate = 30.0
    start, end, frames = _frame_range(rt)
    source_reference_index = {}
    source_reference_rows = []
    source_reference_family = u""
    source_reference_error = u""
    if source_rig_path:
        if os.path.normcase(source_rig_path) == os.path.normcase(old_anim_path):
            source_reference_error = u"源绑定参考不能是动画文件本身"
            source_rig_path = u""
        elif not os.path.exists(source_rig_path):
            source_reference_error = u"源绑定参考不存在: {0}".format(source_rig_path)
            source_rig_path = u""
    if source_rig_path:
        try:
            _load_scene(rt, source_rig_path)
            source_reference_rows = _scene_descriptors(rt)
            source_reference_names = [_as_text(row.get("name", "")) for row in source_reference_rows]
            source_reference_family = classify_rig_family(source_reference_names)
            source_reference_index = _reference_pose_index(rt, source_reference_rows, reference_frame)
        except Exception as error:
            source_reference_error = _as_text(error)
            source_reference_index = {}
            source_reference_family = u""

    # Reload the animation after reading the neutral source binding.  Scene node
    # wrappers from a previous Max file are not safe to sample after a load.
    _load_scene(rt, old_anim_path)
    normalization_stage = time.time()
    layer_normalization = normalize_loaded_animation_scene(rt, tool_root)
    timings["normalize_source_animation_layers"] = round(time.time() - normalization_stage, 3)
    animation_rows_all = _scene_descriptors(rt)
    source_names = [_as_text(row.get("name", "")) for row in animation_rows_all]
    animation_family = classify_rig_family(source_names)
    source_family = source_reference_family or animation_family
    start, end, frames = _frame_range(rt)
    timings["load_source_and_references"] = round(time.time() - stage, 3)

    source_layer_snapshot = public_layer_snapshot(source_reference_rows)
    target_layer_rows = contract_rows(target_rows)
    target_layer_snapshot = public_layer_snapshot(target_rows)
    membership = reconcile_animation_membership(
        source_reference_rows,
        animation_rows_all,
        ignore_ambiguous_names=bool(ignore_duplicate_animation_objects),
    )
    binding_difference = compare_binding_contracts(source_reference_rows, target_rows)
    binding_difference["reviewed"] = bool(
        (not binding_difference.get("has_difference")) or
        reviewed_binding_difference_signature == binding_difference.get("signature", "")
    )
    binding_difference["ignored_source_contract_ids"] = sorted(ignored_source_contract_ids)
    binding_difference["ignored_target_contract_ids"] = sorted(ignored_target_contract_ids)
    camera_merge = _scan_source_camera_bundle(rt, target_name_set)
    anonymous_interface_rows = [
        row for row in (membership.get("resolved_rows", []) or [])
        if not _as_text(row.get("name", "")).strip()
    ]
    source_rows = [
        row for row in (membership.get("resolved_rows", []) or [])
        if (
            row.get("contract_id", "") not in ignored_source_contract_ids and
            _as_text(row.get("name", "")).strip()
        )
    ]
    if anonymous_interface_rows:
        warnings.append({
            "code": "CANON-UNNAMED-PANEL-LINE-IGNORED",
            "message": u"{0} 个无名称 Line 已按层、类型和父级确认结构一致，但没有稳定动画通道名，因此作为面板构件忽略。".format(
                len(anonymous_interface_rows)
            ),
        })

    layer_failure_code = u""
    layer_failure_message = u""
    if not layer_normalization.get("ok", False):
        layer_failure_code = layer_normalization.get("error_code", "CANON-LAYER-NORMALIZER-FAILED")
        layer_failure_message = layer_normalization.get("message", u"动画 Layer 整理失败")
    elif not source_reference_rows:
        layer_failure_code = "CANON-SOURCE-LAYER-CONTRACT-REQUIRED"
        layer_failure_message = u"无法读取动画对应版本的源绑定六层清单"
    elif source_layer_snapshot.get("total_count", 0) <= 0:
        layer_failure_code = "CANON-SOURCE-LAYER-CONTRACT-EMPTY"
        layer_failure_message = u"源绑定没有发现任何受支持迁移层；六个层可以不完整，但至少应存在一个"
    elif membership.get("drift") and not membership.get("recoverable"):
        layer_failure_code = "CANON-LAYER-MEMBERSHIP-UNRECOVERABLE"
        layer_failure_message = u"动画文件的迁移层成员与源绑定不一致，并包含缺失或歧义对象，无法使用保底路径"
    elif binding_difference.get("has_difference") and not binding_difference.get("reviewed"):
        layer_failure_code = "CANON-BINDING-DIFFERENCE-REVIEW"
        layer_failure_message = u"源绑定与目标绑定的六层对象有新增或删除，需要动画师确认迁移对象"
    elif membership.get("requires_layer_fallback") and not allow_layer_fallback:
        layer_failure_code = "CANON-LAYER-MEMBERSHIP-DRIFT"
        layer_failure_message = u"动画文件的迁移层成员与源绑定不一致；可由动画师选择按源绑定层清单继续"

    if layer_failure_code:
        manifest = {
            "ok": False,
            "error_code": layer_failure_code,
            "message": layer_failure_message,
            "schema_version": SCHEMA_VERSION,
            "engine": "layer_contract_bridge",
            "package_dir": package_dir,
            "manifest_path": manifest_path,
            "report_txt": report_txt,
            "output_max_path": output_max_path,
            "source": {
                "path": old_anim_path,
                "binding_reference_path": source_rig_path,
                "binding_version": source_metadata.get("version", ""),
                "family": source_family,
            },
            "target": {"path": new_rig_path, "family": target_family},
            "layer_contract": {
                "allowed_layers": list(source_layer_snapshot.get("allowed_layers", [])),
                "source_binding": source_layer_snapshot,
                "target_binding": target_layer_snapshot,
                "membership": public_membership(membership, fallback_used=allow_layer_fallback),
                "binding_difference": binding_difference,
            },
            "layer_normalization": layer_normalization,
            "warnings": warnings,
            "timings": timings,
            "summary": {},
        }
        _json_write(manifest_path, manifest)
        _write_text_report(report_txt, manifest)
        # Layer normalization is an in-memory preprocessing step. Restore the
        # source file when preflight stops so the open scene is not left dirty.
        try:
            _load_scene(rt, old_anim_path)
        except Exception:
            pass
        return manifest

    contract_errors = []
    if source_family == "unknown" or target_family == "unknown":
        contract_errors.append({
            "code": "CANON-CBT-FAMILY-UNKNOWN",
            "message": u"源或目标绑定缺少可识别的 Bip 骨架，无法判定 CBT1/CBT2 路线",
            "source_family": source_family,
            "target_family": target_family,
        })
    if source_reference_family and source_reference_family != animation_family:
        contract_errors.append({
            "code": "CANON-SOURCE-FAMILY-MISMATCH",
            "message": u"源绑定参考家族与当前动画场景不一致",
            "animation_family": animation_family,
            "reference_family": source_reference_family,
        })
    recorded_version = _as_text(source_metadata.get("version", "")).lower()
    reference_version = _binding_version_from_path(source_rig_path).lower() if source_rig_path else u""
    if recorded_version and reference_version and recorded_version != reference_version:
        contract_errors.append({
            "code": "CANON-SOURCE-VERSION-MISMATCH",
            "message": u"源绑定参考版本与动画记录版本不一致",
            "animation_version": recorded_version,
            "reference_version": reference_version,
        })
    if membership.get("requires_layer_fallback") and allow_layer_fallback:
        warnings.append({
            "code": "CANON-LAYER-FALLBACK-USED",
            "message": u"动画文件层成员与源绑定不一致；已按动画师选择使用源绑定六层清单识别迁移对象",
        })
    if membership.get("ignored_ambiguous"):
        warnings.append({
            "code": "CANON-DUPLICATE-ANIMATION-IGNORED",
            "message": u"已按动画师选择忽略 {0} 个重名对象的动画。".format(
                len(membership.get("ignored_ambiguous", []) or [])
            ),
        })
    if ignored_source_contract_ids:
        warnings.append({
            "code": "CANON-SOURCE-DIFFERENCE-IGNORED",
            "message": u"已按版本差异设置忽略 {0} 个源绑定对象。".format(len(ignored_source_contract_ids)),
        })
    source_bip_names = set([
        row.get("name", "") for row in contract_rows(source_reference_rows)
        if row.get("scope") == "bip"
    ])
    target_bip_names = set([
        row.get("name", "") for row in target_layer_rows
        if row.get("scope") == "bip"
    ])
    missing_target_bip = sorted([name for name in source_bip_names if name not in target_bip_names])
    if missing_target_bip:
        contract_errors.append({
            "code": "CANON-BIP-SOURCE-NOT-SUBSET",
            "message": u"目标绑定缺少源绑定 Bip 层骨骼；Bip 版本只允许新增，不允许删减",
            "missing_target_bip": missing_target_bip,
        })
    ignored_bip_rows = [
        row for row in binding_difference.get("source_only", []) or []
        if row.get("is_bip") and row.get("contract_id", "") in ignored_source_contract_ids
    ]
    if ignored_bip_rows:
        contract_errors.append({
            "code": "CANON-BIP-DIFFERENCE-CANNOT-IGNORE",
            "message": u"Bip 层删除项不能取消迁移",
            "objects": ignored_bip_rows,
        })
    standard_contract_path = _as_text(standard_contract_path).strip() or find_standard_contract(tool_root, new_rig_path)
    standard_contract = {}
    standard_roles = []
    if standard_contract_path:
        try:
            standard_contract = load_standard_contract(standard_contract_path)
            standard_roles = resolve_standard_roles(standard_contract, source_rows, target_rows)
            for role in standard_roles:
                if role.get("required") and role.get("status") != "mapped":
                    contract_errors.append({
                        "code": "CANON-STANDARD-ROLE-UNRESOLVED",
                        "role_id": role.get("role_id", ""),
                        "scope": role.get("scope", ""),
                        "message": u"必需 OP_STD 角色未能在源/目标绑定中唯一解析",
                    })
        except Exception as error:
            contract_errors.append({"code": "CANON-STANDARD-CONTRACT", "message": _as_text(error)})
    # CBT1 and CBT2 both expose the authoritative BIP layer. OP_STD remains an
    # optional exceptional-character adapter, not a normal CBT1->CBT2 gate.

    adapter_contract_path = _as_text(adapter_contract_path).strip() or find_family_adapter_contract(
        tool_root, new_rig_path, source_family, target_family
    )
    adapter_contract = {}
    effective_override = dict(adapter_override or {})
    if adapter_contract_path:
        try:
            adapter_contract = load_family_adapter_contract(
                adapter_contract_path, source_family=source_family,
                target_family=target_family,
            )
            effective_override.update(adapter_contract.get("objects", {}) or {})
        except Exception as error:
            contract_errors.append({"code": "CANON-FAMILY-CONTRACT", "message": _as_text(error)})

    # OP_STD roles are stable semantic identities.  Socket roles may supply a
    # family-level name adaptation; face output roles are consumed below for
    # validation and are never written as controls.
    for role in standard_roles:
        if role.get("status") == "mapped" and role.get("scope") == "socket":
            effective_override.setdefault(role.get("source_name", ""), role.get("target_name", ""))

    adapter = build_adapter_mapping(
        source_rows, target_layer_rows,
        explicit_mapping=effective_override,
        source_family=source_family,
        target_family=target_family,
    )
    mapped = adapter.get("objects", {}) or {}
    resolved_by_contract_id = dict([
        (row.get("contract_id", ""), row)
        for row in (membership.get("resolved_rows", []) or [])
        if row.get("contract_id", "")
    ])
    for difference_row in binding_difference.get("source_only", []) or []:
        contract_id = difference_row.get("contract_id", "")
        if difference_row.get("is_bip") or contract_id in ignored_source_contract_ids:
            continue
        animation_row = resolved_by_contract_id.get(contract_id, {})
        animation_name = animation_row.get("name", difference_row.get("name", ""))
        if not mapped.get(animation_name, ""):
            contract_errors.append({
                "code": "CANON-BINDING-SOURCE-OBJECT-REQUIRED",
                "message": u"源绑定删除项被勾选为需要迁移，但目标绑定没有映射对象",
                "source_name": difference_row.get("name", ""),
                "contract_id": contract_id,
                "scope": difference_row.get("scope", ""),
            })
    target_index = _name_index(target_rows)

    bones_source_names = [
        row.get("name", "") for row in source_rows if row.get("scope") == "bones"
    ]
    bones_constraints = scan_constraints_in_loaded_scene(
        rt, mapping=mapped, eligible_owner_names=bones_source_names
    )
    # Limit removal/rebuild ownership to the authoritative Bones layer.  The
    # generic constraint rebuilder uses this inventory to preserve every
    # target-binding constraint whose owner is outside the migration contract.
    bones_constraints["source_scene_objects"] = [
        {
            "source_name": source_name,
            "target_name": mapped.get(source_name, source_name),
            "target_exists": bool(mapped.get(source_name, "")),
        }
        for source_name in bones_source_names
    ]
    if not bones_constraints.get("ok", False):
        contract_errors.append({
            "code": "CANON-BONES-CONSTRAINT-SCAN",
            "message": bones_constraints.get("message", u"Bones 层约束扫描失败"),
        })
    constrained_bones = set([
        row.get("owner_source_name", "")
        for row in (bones_constraints.get("constraints", []) or [])
    ])
    xaf_channels = []
    xaf_source_names = set()
    for index, source in enumerate(source_rows):
        source_name = source.get("name", "")
        scope = source.get("scope", "")
        if not mapped.get(source_name):
            continue
        if source_name not in constrained_bones:
            continue
        track_signatures = collect_node_track_signatures(
            rt, source.get("_node"), include_samples=True,
            include_unkeyed=False, include_controllers=False,
        )
        # The six-layer contract transfers node/custom-attribute controller
        # animation only. Modifiers (including obsolete Morpher data) are not
        # part of the constrained Bones transport.
        track_signatures = json_track_signatures([
            row for row in track_signatures
            if row.get("root_kind") != "modifier"
        ])
        key_times = sorted(set([
            int(key_time)
            for row in track_signatures
            for key_time in (row.get("key_times", []) or [])
        ]))
        if not key_times:
            continue
        xaf_path = os.path.join(xaf_dir, "{0:04d}_{1}.xaf".format(index, _safe_filename(source_name)))
        xaf_ok, xaf_message = _try_save_xaf(rt, source.get("_node"), xaf_path)
        xaf_channels.append({
            "source_name": source_name,
            "target_name": mapped.get(source_name, ""),
            "scope": scope,
            "xaf_path": xaf_path if xaf_ok else u"",
            "key_times": key_times,
            "track_signatures": track_signatures,
            "ok": bool(xaf_ok),
            "message": xaf_message,
        })
        if xaf_ok:
            xaf_source_names.add(source_name)
        else:
            contract_errors.append({
                "code": "CANON-LAYER-XAF-EXPORT",
                "source_name": source_name,
                "scope": scope,
                "message": xaf_message or u"六层控制器 XAF 导出失败",
            })

    body_root = _find_bip_root(rt)
    selected_bip_names, selected_bip_track_names, selected_bip_nodes, selected_bip_indices, active_bip_names, excluded_bip = (
        _selected_bip_tracks(rt, source_rows, target_name_set)
    )
    bip_ok = False
    bip_message = u""
    if body_root is not None:
        try:
            if selected_bip_nodes:
                bip_ok = bool(rt.biped.saveBipFile(
                    body_root.controller,
                    bip_path,
                    rt.Name("saveSelectedSubAnimControllers"),
                    rt.Array(*selected_bip_nodes),
                    rt.Array(*selected_bip_indices),
                )) and os.path.exists(bip_path)
            bip_message = u"BIP 共同动画子轨导出成功" if bip_ok else u"BIP 共同动画子轨导出返回失败"
        except Exception as error:
            bip_message = _as_text(error)
    else:
        bip_message = u"未找到 Bip001 根"

    adapter_audit_by_source = dict([
        (item.get("source_name", ""), item)
        for item in adapter.get("audit", [])
        if item.get("status") == "mapped"
    ])
    candidate_rows = []
    secondary = []
    for source in source_rows:
        scope = source.get("scope", "")
        if source.get("is_bip") or source.get("is_face_output") or scope not in (
            "bones", "ui", "face_control", "ctrl", "body_ctrl",
        ):
            continue
        source_name = source.get("name", "")
        target_name = mapped.get(source_name, "")
        if not target_name:
            continue
        adapter_item = adapter_audit_by_source.get(source_name, {})
        transfer_mode = adapter_item.get("transfer_mode", _transfer_mode(source))
        if transfer_mode in (TRANSFER_VALIDATE_ONLY, TRANSFER_TARGET_OWNED):
            continue
        source_reference_name = source.get("binding_name", "") or source_name
        source_reference = _unique_reference(source_reference_index, source, source_reference_name)
        target_reference_identity = {
            "contract_id": adapter_item.get("target_contract_id", ""),
            "rr_guid": adapter_item.get("target_rr_guid", ""),
            "contract_layer": adapter_item.get("target_contract_layer", source.get("contract_layer", "")),
            "name": target_name,
        }
        target_reference = _unique_reference(target_reference_index, target_reference_identity, target_name)
        candidate_rows.append({
            "source_name": source_name,
            "target_name": target_name,
            "scope": scope,
            "mapping_method": adapter_item.get("method", ""),
            "transfer_mode": transfer_mode,
            "source_layer": source.get("layer_name", ""),
            "source_class": source.get("class_name", ""),
            "source_parent": source.get("parent_name", ""),
            "target_parent": adapter_item.get("target_parent", ""),
            "source_reference_local_matrix": (source_reference or {}).get("local_matrix"),
            "target_reference_local_matrix": (target_reference or {}).get("local_matrix"),
            "create_kind": u"",
            "key_times": [],
            "transport": (
                "xaf_constraint"
                if source_name in xaf_source_names and source_name in constrained_bones
                else "xaf_plus_bind_relative_local_prs"
                if source_name in xaf_source_names
                else "bind_relative_local_prs"
            ),
            "xaf_path": next((row.get("xaf_path", "") for row in xaf_channels if row.get("source_name") == source_name), u""),
            "required": _channel_is_required(scope),
            "replace_transform_controller": False,
            "include_matrix": transfer_mode == TRANSFER_WORLD,
            "include_local_matrix": transfer_mode == TRANSFER_LOCAL_DELTA,
            "include_visibility": True,
            "include_fov": False,
            "_node": source.get("_node"),
        })

    body_validation = []
    for source in source_rows:
        if not source.get("is_bip"):
            continue
        source_name = source.get("name", "")
        if source_name not in active_bip_names:
            continue
        target_name = _body_target_name(source_name, target_name_set, target_family)
        if not target_name:
            continue
        key_times = _biped_node_key_times(rt, source.get("_node"), start, end)
        dense_apply = (
            source_name == "Bip001" or
            source_name.endswith(" Hand") or
            source_name.endswith(" Foot")
        )
        body_validation.append({
            "source_name": source_name,
            "target_name": target_name,
            "scope": "body_output",
            "required": True,
            "validation_mode": "motion_activity",
            "activity_mode": "position" if source_name == "Bip001" else "rotation",
            "validate_position": source_name == "Bip001",
            "validate_rotation": True,
            "validate_scale": False,
            "position_tolerance": 1.0,
            "rotation_tolerance_degrees": 3.0,
            "apply_target_name": source_name,
            "apply_position": dense_apply,
            "apply_rotation": True,
            "apply_dense": dense_apply,
            "key_times": key_times,
            "include_matrix": True,
            "include_visibility": False,
            "include_fov": False,
            "_node": source.get("_node"),
        })

    face_role_targets = dict([
        (role.get("source_name", ""), role.get("target_name", ""))
        for role in standard_roles
        if role.get("status") == "mapped" and role.get("scope") == "face_output"
    ])
    face_validation = []
    missing_face_probe_rows = []
    for source in source_rows:
        source_name = source.get("name", "")
        if not source.get("is_face_output"):
            continue
        target_name = face_role_targets.get(source_name, source_name)
        if len(target_index.get(target_name, [])) != 1:
            missing_face_probe_rows.append({
                "source_name": source_name,
                "target_name": target_name,
                "scope": "face_output",
                "include_matrix": False,
                "include_local_matrix": True,
                "include_visibility": False,
                "include_fov": False,
                "_node": source.get("_node"),
            })
            continue
        source_reference = _unique_reference(source_reference_index, source, source_name)
        target_reference = _unique_reference(target_reference_index, {
            "contract_layer": source.get("contract_layer", ""),
            "name": target_name,
        }, target_name)
        face_validation.append({
            "source_name": source_name,
            "target_name": target_name,
            "scope": "face_output",
            "required": True,
            "validation_mode": "absolute",
            "transfer_mode": TRANSFER_VALIDATE_ONLY,
            "validate_position": True,
            "validate_rotation": True,
            "validate_scale": True,
            "source_reference_local_matrix": (source_reference or {}).get("local_matrix"),
            "target_reference_local_matrix": (target_reference or {}).get("local_matrix"),
            "include_matrix": False,
            "include_local_matrix": True,
            "include_visibility": False,
            "include_fov": False,
            "_node": source.get("_node"),
        })

    deform_validation = []
    missing_deform_probe_rows = []
    for source in source_rows:
        if not _is_deform_output(source):
            continue
        source_name = source.get("name", "")
        if len(target_index.get(source_name, [])) != 1:
            missing_deform_probe_rows.append({
                "source_name": source_name,
                "target_name": source_name,
                "scope": "deform_output",
                "include_matrix": False,
                "include_local_matrix": True,
                "include_visibility": False,
                "include_fov": False,
                "_node": source.get("_node"),
            })
            continue
        source_reference = _unique_reference(source_reference_index, source, source_name)
        target_reference = _unique_reference(target_reference_index, {
            "contract_layer": source.get("contract_layer", ""),
            "name": source_name,
        }, source_name)
        deform_validation.append({
            "source_name": source_name,
            "target_name": source_name,
            "scope": "deform_output",
            "required": True,
            "validation_mode": "absolute",
            "transfer_mode": TRANSFER_VALIDATE_ONLY,
            "validate_position": True,
            "validate_rotation": True,
            "validate_scale": True,
            "position_tolerance": 0.5,
            "rotation_tolerance_degrees": 3.0,
            "scale_tolerance": 0.02,
            "source_reference_local_matrix": (source_reference or {}).get("local_matrix"),
            "target_reference_local_matrix": (target_reference or {}).get("local_matrix"),
            "include_matrix": False,
            "include_local_matrix": True,
            "include_visibility": False,
            "include_fov": False,
            "_node": source.get("_node"),
        })

    source_rows_by_name = _name_index(source_rows)
    unresolved_probe_rows = []
    for item in adapter.get("audit", []):
        if item.get("status") != "unresolved" or item.get("scope") not in (
            "bones", "ui", "face_control", "ctrl", "body_ctrl",
        ):
            continue
        matches = source_rows_by_name.get(item.get("source_name", ""), [])
        if len(matches) != 1 or matches[0].get("is_face_output"):
            continue
        source = matches[0]
        transfer_mode = _transfer_mode(source)
        unresolved_probe_rows.append({
            "source_name": source.get("name", ""),
            "target_name": u"",
            "scope": source.get("scope", ""),
            "transfer_mode": transfer_mode,
            "include_matrix": transfer_mode == TRANSFER_WORLD,
            "include_local_matrix": transfer_mode != TRANSFER_WORLD,
            "include_visibility": True,
            "include_fov": False,
            "_node": source.get("_node"),
        })

    sample_rows = candidate_rows + body_validation + face_validation + deform_validation + unresolved_probe_rows + missing_face_probe_rows + missing_deform_probe_rows
    stage = time.time()
    _sample_rows(rt, sample_rows, frames)
    timings["sample_canonical_outputs"] = round(time.time() - stage, 3)
    # Some legacy face rigs animate Reaction/constraint networks without keys on
    # the visible node controllers.  Keep evaluated local motion as the portable
    # interface, while face output bones remain the hard acceptance contract.
    candidate_rows = [
        row for row in candidate_rows
        if (
            row.get("source_name", "") in xaf_source_names or
            _samples_change(row.get("samples", []))
        )
    ]
    adapter_errors = list(contract_errors)
    for row in unresolved_probe_rows:
        if _samples_change(row.get("samples", [])):
            adapter_errors.append({
                "code": "CANON-ACTIVE-INTERFACE-UNRESOLVED",
                "source_name": row.get("source_name", ""),
                "target_name": u"",
                "scope": row.get("scope", ""),
                "message": u"活动动画接口未能通过绑定家族适配器唯一解析",
            })
    for row in missing_face_probe_rows:
        source_activity = _sample_activity_total(row.get("samples", []), "local_matrix", "combined")
        if source_activity >= 5.0:
            adapter_errors.append({
                "code": "CANON-ACTIVE-FACE-OUTPUT-UNRESOLVED",
                "source_name": row.get("source_name", ""),
                "target_name": row.get("target_name", ""),
                "scope": "face_output",
                "source_activity_total": source_activity,
                "message": u"有效表情输出未能在目标绑定或 OP_STD 契约中解析",
            })
    for row in missing_deform_probe_rows:
        source_activity = _sample_activity_total(row.get("samples", []), "local_matrix", "combined")
        if source_activity >= 0.1:
            adapter_errors.append({
                "code": "CANON-ACTIVE-DEFORM-OUTPUT-UNRESOLVED",
                "source_name": row.get("source_name", ""),
                "target_name": row.get("target_name", ""),
                "scope": "deform_output",
                "source_activity_total": source_activity,
                "message": u"活动修形/扭转输出在目标绑定中不存在或不唯一",
            })
    for row in candidate_rows:
        row["required"] = True
        if row.get("transfer_mode") != TRANSFER_LOCAL_DELTA:
            continue
        source_reference = row.get("source_reference_local_matrix")
        target_reference = row.get("target_reference_local_matrix")
        if source_reference is None or target_reference is None:
            adapter_errors.append({
                "code": "CANON-SOURCE-REFERENCE-REQUIRED",
                "source_name": row.get("source_name", ""),
                "target_name": row.get("target_name", ""),
                "scope": row.get("scope", ""),
                "message": u"活动控制器缺少源/目标绑定参考姿态，已停止，不能退回绝对局部矩阵复制",
            })
            continue
        for sample in row.get("samples", []) or []:
            source_local = sample.get("local_matrix")
            if source_local is None:
                continue
            sample["source_local_matrix"] = source_local
            try:
                sample["local_matrix"] = _retarget_local_matrix(
                    source_reference, target_reference, source_local
                )
            except Exception as error:
                adapter_errors.append({
                    "code": "CANON-LOCAL-DELTA-FAILED",
                    "source_name": row.get("source_name", ""),
                    "target_name": row.get("target_name", ""),
                    "scope": row.get("scope", ""),
                    "frame": sample.get("frame", 0),
                    "message": _as_text(error),
                })
                break
    # Face output bones are driven results, never migration inputs.  Validate
    # only outputs that actually move in local space in this clip.
    face_validation = [
        row for row in face_validation
        if _samples_change(row.get("samples", []))
    ]
    for row in face_validation:
        source_activity = _sample_activity_total(
            row.get("samples", []), "local_matrix", "combined"
        )
        row["source_activity_total"] = source_activity
        # Extremely small legacy output motion is commonly constraint noise or
        # a secondary helper response.  Keep it in the report, but do not fail
        # an otherwise complete facial transfer on that signal alone.
        row["required"] = source_activity >= 5.0
        source_reference = row.get("source_reference_local_matrix")
        target_reference = row.get("target_reference_local_matrix")
        if row.get("required") and (source_reference is None or target_reference is None):
            adapter_errors.append({
                "code": "CANON-FACE-REFERENCE-REQUIRED",
                "source_name": row.get("source_name", ""),
                "target_name": row.get("target_name", ""),
                "scope": row.get("scope", ""),
                "message": u"有效表情输出缺少源/目标绑定参考姿态",
            })
            continue
        if source_reference is not None and target_reference is not None:
            for sample in row.get("samples", []) or []:
                source_local = sample.get("local_matrix")
                if source_local is None:
                    continue
                sample["source_local_matrix"] = source_local
                sample["local_matrix"] = _retarget_local_matrix(
                    source_reference, target_reference, source_local
                )
    deform_validation = [
        row for row in deform_validation
        if _samples_change(row.get("samples", []))
    ]
    for row in deform_validation:
        source_reference = row.get("source_reference_local_matrix")
        target_reference = row.get("target_reference_local_matrix")
        if source_reference is None or target_reference is None:
            adapter_errors.append({
                "code": "CANON-DEFORM-REFERENCE-REQUIRED",
                "source_name": row.get("source_name", ""),
                "target_name": row.get("target_name", ""),
                "scope": "deform_output",
                "message": u"活动修形/扭转输出缺少源/目标绑定参考姿态",
            })
            continue
        for sample in row.get("samples", []) or []:
            source_local = sample.get("local_matrix")
            if source_local is None:
                continue
            sample["source_local_matrix"] = source_local
            sample["local_matrix"] = _retarget_local_matrix(
                source_reference, target_reference, source_local
            )
    body_channels = []
    for row in body_validation:
        channel = dict(row)
        selected_frames = set(frames if row.get("apply_dense") else (row.get("key_times", []) or []))
        if not selected_frames:
            continue
        channel["samples"] = [
            sample for sample in (row.get("samples", []) or [])
            if int(sample.get("frame", 0)) in selected_frames
        ]
        if channel["samples"]:
            body_channels.append(channel)

    unresolved_active = []
    for item in adapter.get("audit", []):
        if item.get("status") == "unresolved" and item.get("scope") in (
            "bones", "ui", "face_control", "ctrl", "body_ctrl",
        ):
            unresolved_active.append(item)
    if unresolved_active:
        warnings.append({"code": "CANON-UNRESOLVED-INTERFACE", "message": u"{0} 个六层接口节点未建立映射；只有实际含动画的节点才会影响结果。".format(len(unresolved_active))})
    if source_reference_error:
        warnings.append({"code": "CANON-SOURCE-REFERENCE", "message": source_reference_error})
    if adapter_errors:
        warnings.append({"code": "CANON-ADAPTER-BLOCKED", "message": u"{0} 个活动接口无法建立安全的参考姿态差值，已停止迁移。".format(len(adapter_errors))})

    manifest_ok = bool(bip_ok) and not adapter_errors
    manifest = {
        "ok": manifest_ok,
        "error_code": None if manifest_ok else ("CANON-FAMILY-ADAPTER" if adapter_errors else "CANON-BIP-EXPORT"),
        "message": u"六层动画包导出成功" if manifest_ok else (u"六层契约存在无法安全迁移的对象" if adapter_errors else bip_message),
        "schema_version": SCHEMA_VERSION,
        "engine": "layer_contract_bridge",
        "package_dir": package_dir,
        "manifest_path": manifest_path,
        "report_txt": report_txt,
        "output_max_path": output_max_path,
        "source": {
            "path": old_anim_path,
            "family": source_family,
            "animation_family": animation_family,
            "binding_reference_path": source_rig_path,
            "binding_version": source_metadata.get("version", ""),
            "object_count": len(source_rows),
            "frame_rate": source_frame_rate,
        },
        "target": {"path": new_rig_path, "family": target_family, "object_count": len(target_rows), "frame_rate": target_frame_rate},
        "animation_range": {"start": start, "end": end, "frame_count": len(frames)},
        "body": {
            "transport": (
                "selected_bip_subanims"
                if _bip_structure_signature(source_rows) == _bip_structure_signature(target_rows)
                else "sparse_biped_results"
            ),
            "bip_path": bip_path,
            "export_ok": bool(bip_ok),
            "message": bip_message,
            "selected_node_names": selected_bip_names,
            "selected_track_names": selected_bip_track_names,
            "selected_subanim_indices": selected_bip_indices,
            "selected_track_count": len(selected_bip_indices),
            "excluded_nodes": excluded_bip,
            "structure_match": _bip_structure_signature(source_rows) == _bip_structure_signature(target_rows),
            "channels": body_channels,
            "validation": body_validation,
        },
        "channels": candidate_rows,
        "face_validation": face_validation,
        "deform_validation": deform_validation,
        "bones_constraints": bones_constraints,
        "xaf_channels": xaf_channels,
        "camera_merge": camera_merge,
        "adapter": {
            "kind": "binding_family_adapter",
            "source_family": source_family,
            "target_family": target_family,
            "mapping": mapped,
            "audit": adapter.get("audit", []),
            "errors": adapter_errors,
            "uses_version_pair_mapping": False,
            "reference_frame": int(reference_frame),
        },
        "standard_contract": {
            "path": standard_contract_path,
            "required_for_route": False,
            "loaded": bool(standard_contract),
            "roles": standard_roles,
        },
        "family_adapter_contract": {
            "path": adapter_contract_path,
            "loaded": bool(adapter_contract),
            "kind": adapter_contract.get("kind", "") if adapter_contract else "",
        },
        "layer_contract": {
            "allowed_layers": list(source_layer_snapshot.get("allowed_layers", [])),
            "source_binding": source_layer_snapshot,
            "target_binding": target_layer_snapshot,
            "membership": public_membership(membership, fallback_used=allow_layer_fallback),
            "binding_difference": binding_difference,
            "selection_policy": "source_binding_authoritative",
            "unlisted_layers": "ignored",
        },
        "layer_normalization": layer_normalization,
        "warnings": warnings,
        "timings": timings,
        "summary": {
            "channel_count": len(candidate_rows),
            "body_validation_count": len(body_validation),
            "face_validation_count": len(face_validation),
            "deform_validation_count": len(deform_validation),
            "camera_merge_object_count": (camera_merge.get("summary", {}) or {}).get("object_count", 0),
            "camera_merge_pending_count": (camera_merge.get("summary", {}) or {}).get("pending_count", 0),
            "tracked_layer_count": len(source_layer_snapshot.get("present_layers", [])),
            "layer_fallback_used": bool(allow_layer_fallback and membership.get("requires_layer_fallback")),
            "mapped_count": len(mapped),
            "adapter_error_count": len(adapter_errors),
            "delta_channel_count": len([row for row in candidate_rows if row.get("transfer_mode") == TRANSFER_LOCAL_DELTA]),
        },
    }
    _json_write(manifest_path, manifest)
    _write_text_report(report_txt, manifest)
    if not manifest_ok:
        try:
            _load_scene(rt, old_anim_path)
        except Exception:
            pass
    return manifest


def _target_node(rt, name):
    matches = []
    for node in list(rt.objects):
        if _node_name(node) == name and "_old_" not in _node_name(node).lower():
            matches.append(node)
    return matches[0] if len(matches) == 1 else None


def _target_node_index(rt):
    index = {}
    for node in list(rt.objects):
        name = _node_name(node)
        if name and "_old_" not in name.lower():
            index.setdefault(name, []).append(node)
    return dict([(name, nodes[0] if len(nodes) == 1 else None) for name, nodes in index.items()])


def _node_depth(node):
    depth = 0
    current = node
    visited = set()
    while current is not None and depth < 128:
        try:
            identity = id(current)
            if identity in visited:
                break
            visited.add(identity)
            current = current.parent
            if current is not None:
                depth += 1
        except Exception:
            break
    return depth


def _apply_sparse_biped_channels(rt, channels, node_index=None):
    """Apply evaluated Biped keys frame-major, preserving the target structure."""
    node_index = node_index or _target_node_index(rt)
    prepared = []
    errors = []
    for channel in channels or []:
        target_name = channel.get("apply_target_name", channel.get("source_name", ""))
        node = node_index.get(target_name)
        if node is None or not _is_bip_node(rt, node):
            errors.append({
                "source_name": channel.get("source_name", ""),
                "target_name": target_name,
                "scope": "body",
                "required": True,
                "message": u"目标 Biped 节点不存在或不唯一",
            })
            continue
        sample_by_frame = dict([
            (int(sample.get("frame", 0)), sample)
            for sample in channel.get("samples", []) or []
        ])
        prepared.append((_node_depth(node), channel, node, sample_by_frame))
    prepared.sort(key=lambda item: (item[0], item[1].get("source_name", "")))

    frames = sorted(set([
        frame
        for _depth, _channel, _node, samples in prepared
        for frame in samples.keys()
    ]))
    with suspended_scene_redraw(rt):
        for frame in frames:
            rt.sliderTime = int(frame)
            for _depth, channel, node, sample_by_frame in prepared:
                sample = sample_by_frame.get(int(frame))
                if not sample or "matrix" not in sample:
                    continue
                try:
                    matrix = _list_to_matrix(rt, sample["matrix"])
                    if channel.get("apply_position"):
                        rt.biped.setTransform(node, rt.Name("pos"), matrix.pos, True)
                    if channel.get("apply_rotation", True):
                        rt.biped.setTransform(node, rt.Name("rotation"), matrix.rotation, True)
                except Exception as error:
                    errors.append({
                        "source_name": channel.get("source_name", ""),
                        "target_name": channel.get("apply_target_name", channel.get("source_name", "")),
                        "scope": "body",
                        "required": True,
                        "frame": int(frame),
                        "message": _as_text(error),
                    })
    return prepared, errors


def _apply_channels(rt, channels, frames, node_index=None):
    import pymxs

    node_index = node_index or _target_node_index(rt)
    prepared = []
    errors = []
    for channel in channels:
        # A rebuilt Bones constraint owns the transform. Its animated
        # controller data is restored by XAF and must not then be overwritten
        # with sampled matrices. Other XAF channels still receive the
        # bind-relative matrix pass so target-neutral offsets are preserved.
        if channel.get("transport") == "xaf_constraint":
            continue
        target_name = channel.get("target_name", "")
        node = node_index.get(target_name)
        if node is None:
            errors.append({"source_name": channel.get("source_name", ""), "target_name": target_name, "scope": channel.get("scope", ""), "required": channel.get("required", False), "message": u"目标节点不存在或不唯一"})
            continue
        if channel.get("replace_transform_controller"):
            try:
                current_transform = node.transform
                node.controller = rt.PRS()
                node.transform = current_transform
            except Exception as error:
                errors.append({
                    "source_name": channel.get("source_name", ""),
                    "target_name": target_name,
                    "scope": channel.get("scope", ""),
                    "required": channel.get("required", False),
                    "message": u"六层动画节点无法切换为烘焙 PRS 控制器: {0}".format(_as_text(error)),
                })
                continue
        sample_by_frame = dict([(int(sample.get("frame", 0)), sample) for sample in channel.get("samples", [])])
        prepared.append((channel, node, sample_by_frame))

    with suspended_scene_redraw(rt):
        with pymxs.animate(True):
            for frame in frames:
                rt.sliderTime = int(frame)
                for channel, node, sample_by_frame in prepared:
                    sample = sample_by_frame.get(int(frame))
                    if not sample:
                        continue
                    try:
                        if "local_matrix" in sample:
                            local_matrix = _list_to_matrix(rt, sample["local_matrix"])
                            try:
                                if node.parent is not None:
                                    node.transform = local_matrix * node.parent.transform
                                else:
                                    node.transform = local_matrix
                            except Exception:
                                node.transform = local_matrix
                        elif "matrix" in sample:
                            node.transform = _list_to_matrix(rt, sample["matrix"])
                        if "visibility" in sample:
                            node.visibility = float(sample["visibility"])
                        if "fov" in sample:
                            node.fov = float(sample["fov"])
                    except Exception as error:
                        errors.append({"source_name": channel.get("source_name", ""), "target_name": channel.get("target_name", ""), "scope": channel.get("scope", ""), "required": channel.get("required", False), "frame": int(frame), "message": _as_text(error)})
    return prepared, errors


def _vector_length(value):
    return math.sqrt(sum([float(component) * float(component) for component in value]))


def _matrix_error(expected, actual):
    pos = math.sqrt(sum([(float(expected[3][i]) - float(actual[3][i])) ** 2 for i in range(3)]))
    rotation = 0.0
    scale = 0.0
    for row in range(3):
        e = expected[row]
        a = actual[row]
        e_len = _vector_length(e)
        a_len = _vector_length(a)
        scale = max(scale, abs(e_len - a_len))
        if e_len > 1e-8 and a_len > 1e-8:
            dot = sum([float(e[i]) * float(a[i]) for i in range(3)]) / (e_len * a_len)
            dot = max(-1.0, min(1.0, dot))
            rotation = max(rotation, math.degrees(math.acos(dot)))
    return pos, rotation, scale


def _rotation_rows(matrix):
    rows = []
    for index in range(3):
        row = [float(value) for value in matrix[index]]
        length = _vector_length(row)
        if length <= 1e-8:
            rows.append([1.0 if index == column else 0.0 for column in range(3)])
        else:
            rows.append([value / length for value in row])
    return rows


def _mat3_transpose(value):
    return [[float(value[column][row]) for column in range(3)] for row in range(3)]


def _mat3_multiply(left, right):
    return [[
        sum([float(left[row][index]) * float(right[index][column]) for index in range(3)])
        for column in range(3)
    ] for row in range(3)]


def _rotation_rows_error(expected, actual):
    error = 0.0
    for row in range(3):
        e = expected[row]
        a = actual[row]
        dot = max(-1.0, min(1.0, sum([float(e[index]) * float(a[index]) for index in range(3)])))
        error = max(error, math.degrees(math.acos(dot)))
    return error


def _motion_delta_matrix_error(expected_first, actual_first, expected, actual,
                               validate_position=True, validate_rotation=True,
                               validate_scale=False):
    position = 0.0
    if validate_position:
        expected_delta = [float(expected[3][i]) - float(expected_first[3][i]) for i in range(3)]
        actual_delta = [float(actual[3][i]) - float(actual_first[3][i]) for i in range(3)]
        position = math.sqrt(sum([(expected_delta[i] - actual_delta[i]) ** 2 for i in range(3)]))

    rotation = 0.0
    if validate_rotation:
        expected_rot = _rotation_rows(expected)
        actual_rot = _rotation_rows(actual)
        expected_first_rot = _rotation_rows(expected_first)
        actual_first_rot = _rotation_rows(actual_first)

        # Bone and ADV output axes can have a fixed pre- or post-rotation.  Fit
        # that bind offset from the first sample, then compare only motion.
        right_correction = _mat3_multiply(_mat3_transpose(actual_first_rot), expected_first_rot)
        right_aligned = _mat3_multiply(actual_rot, right_correction)
        left_correction = _mat3_multiply(expected_first_rot, _mat3_transpose(actual_first_rot))
        left_aligned = _mat3_multiply(left_correction, actual_rot)
        rotation = min(
            _rotation_rows_error(expected_rot, right_aligned),
            _rotation_rows_error(expected_rot, left_aligned),
        )

    scale = 0.0
    if validate_scale:
        for row in range(3):
            expected_delta = _vector_length(expected[row]) - _vector_length(expected_first[row])
            actual_delta = _vector_length(actual[row]) - _vector_length(actual_first[row])
            scale = max(scale, abs(expected_delta - actual_delta))
    return position, rotation, scale


def _motion_activity_step(previous, current, mode="rotation"):
    position = math.sqrt(sum([
            (float(current[3][index]) - float(previous[3][index])) ** 2
            for index in range(3)
        ]))
    rotation = _rotation_rows_error(_rotation_rows(previous), _rotation_rows(current))
    if mode == "position":
        return position
    if mode == "combined":
        return position + rotation
    return rotation


def _sample_activity_total(samples, matrix_key="matrix", mode="rotation"):
    total = 0.0
    previous = None
    for sample in samples or []:
        current = sample.get(matrix_key)
        if current is None:
            continue
        if previous is not None:
            total += _motion_activity_step(previous, current, mode=mode)
        previous = current
    return total


def _pearson_correlation(left, right):
    if len(left) != len(right) or len(left) < 2:
        return 1.0
    left_mean = sum(left) / float(len(left))
    right_mean = sum(right) / float(len(right))
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum([value * value for value in left_delta]) *
        sum([value * value for value in right_delta])
    )
    if denominator <= 1e-8:
        return 1.0 if max(left or [0.0]) - min(left or [0.0]) <= 1e-5 else 0.0
    return sum([left_delta[index] * right_delta[index] for index in range(len(left))]) / denominator


def validate_canonical_outputs(rt, rows, node_index=None):
    node_index = node_index or _target_node_index(rt)
    results = []
    failures = []
    rows_by_frame = {}
    for row in rows:
        node = node_index.get(row.get("target_name", ""))
        if node is None:
            item = {
                "source_name": row.get("source_name", ""), "target_name": row.get("target_name", ""),
                "scope": row.get("scope", ""), "required": row.get("required", False),
                "ok": False, "message": u"目标验收节点不存在或不唯一",
                "max_position_error": 0.0, "max_rotation_error_degrees": 0.0, "max_scale_error": 0.0,
            }
            results.append(item)
            if item["required"]:
                failures.append(item)
            continue
        for sample in row.get("samples", []):
            rows_by_frame.setdefault(int(sample.get("frame", 0)), []).append((row, node, sample))

    aggregates = {}
    with suspended_scene_redraw(rt):
        for frame in sorted(rows_by_frame.keys()):
            rt.sliderTime = int(frame)
            for row, node, expected in rows_by_frame[frame]:
                key = (row.get("source_name", ""), row.get("target_name", ""), row.get("scope", ""))
                item = aggregates.setdefault(key, {
                    "source_name": key[0], "target_name": key[1], "scope": key[2],
                    "required": row.get("required", False), "ok": True, "message": u"",
                    "max_position_error": 0.0, "max_rotation_error_degrees": 0.0,
                    "max_scale_error": 0.0, "max_visibility_error": 0.0, "max_fov_error": 0.0,
                    "worst_frame": frame,
                    "validation_mode": row.get("validation_mode", "absolute"),
                    "activity_curve": row.get("activity_curve", "cumulative"),
                    "allow_amplitude_remap": bool(row.get("allow_amplitude_remap", False)),
                    "position_tolerance": float(row.get("position_tolerance", POSITION_TOLERANCE)),
                    "rotation_tolerance_degrees": float(row.get("rotation_tolerance_degrees", ROTATION_TOLERANCE_DEGREES)),
                    "scale_tolerance": float(row.get("scale_tolerance", SCALE_TOLERANCE)),
                })
                actual = _sample_value(
                    rt, node,
                    include_matrix="matrix" in expected,
                    include_local_matrix="local_matrix" in expected,
                    include_visibility="visibility" in expected,
                    include_fov="fov" in expected,
                )
                matrix_key = "matrix" if "matrix" in expected else "local_matrix" if "local_matrix" in expected else ""
                if matrix_key:
                    expected_matrix = expected[matrix_key]
                    actual_matrix = actual[matrix_key]
                    if item.get("validation_mode") == "motion_activity":
                        if "_expected_first_matrix" not in item:
                            item["_expected_first_matrix"] = expected_matrix
                            item["_actual_first_matrix"] = actual_matrix
                            item["_expected_previous_matrix"] = expected_matrix
                            item["_actual_previous_matrix"] = actual_matrix
                            item["_expected_activity_total"] = 0.0
                            item["_actual_activity_total"] = 0.0
                            item["_expected_activity"] = []
                            item["_actual_activity"] = []
                            item["_activity_frames"] = []
                        activity_mode = row.get("activity_mode")
                        if not activity_mode:
                            activity_mode = "position" if row.get("validate_position", False) else "rotation"
                        expected_step = _motion_activity_step(
                            item["_expected_previous_matrix"], expected_matrix, mode=activity_mode
                        )
                        actual_step = _motion_activity_step(
                            item["_actual_previous_matrix"], actual_matrix, mode=activity_mode
                        )
                        item["_expected_activity_total"] += expected_step
                        item["_actual_activity_total"] += actual_step
                        item["_expected_previous_matrix"] = expected_matrix
                        item["_actual_previous_matrix"] = actual_matrix
                        if item.get("activity_curve") == "per_step":
                            item["_expected_activity"].append(expected_step)
                            item["_actual_activity"].append(actual_step)
                        else:
                            item["_expected_activity"].append(item["_expected_activity_total"])
                            item["_actual_activity"].append(item["_actual_activity_total"])
                        item["_activity_frames"].append(int(frame))
                        p_err, r_err, s_err = 0.0, 0.0, 0.0
                    elif item.get("validation_mode") == "motion_delta":
                        if "_expected_first_matrix" not in item:
                            item["_expected_first_matrix"] = expected_matrix
                            item["_actual_first_matrix"] = actual_matrix
                        p_err, r_err, s_err = _motion_delta_matrix_error(
                            item["_expected_first_matrix"], item["_actual_first_matrix"],
                            expected_matrix, actual_matrix,
                            validate_position=bool(row.get("validate_position", True)),
                            validate_rotation=bool(row.get("validate_rotation", True)),
                            validate_scale=bool(row.get("validate_scale", False)),
                        )
                    else:
                        p_err, r_err, s_err = _matrix_error(expected_matrix, actual_matrix)
                    pos_tol = max(float(item.get("position_tolerance", POSITION_TOLERANCE)), 1e-8)
                    rot_tol = max(float(item.get("rotation_tolerance_degrees", ROTATION_TOLERANCE_DEGREES)), 1e-8)
                    scale_tol = max(float(item.get("scale_tolerance", SCALE_TOLERANCE)), 1e-8)
                    if max(p_err / pos_tol, r_err / rot_tol, s_err / scale_tol) > max(
                        item["max_position_error"] / pos_tol,
                        item["max_rotation_error_degrees"] / rot_tol,
                        item["max_scale_error"] / scale_tol,
                    ):
                        item["worst_frame"] = frame
                    item["max_position_error"] = max(item["max_position_error"], p_err)
                    item["max_rotation_error_degrees"] = max(item["max_rotation_error_degrees"], r_err)
                    item["max_scale_error"] = max(item["max_scale_error"], s_err)
                if "visibility" in expected:
                    item["max_visibility_error"] = max(item["max_visibility_error"], abs(float(expected["visibility"]) - float(actual.get("visibility", 1.0))))
                if "fov" in expected:
                    item["max_fov_error"] = max(item["max_fov_error"], abs(float(expected["fov"]) - float(actual.get("fov", 0.0))))

    for item in aggregates.values():
        if item.get("validation_mode") == "motion_activity":
            expected_activity = item.pop("_expected_activity", [])
            actual_activity = item.pop("_actual_activity", [])
            activity_frames = item.pop("_activity_frames", [])
            source_span = float(item.get("_expected_activity_total", 0.0))
            target_span = float(item.get("_actual_activity_total", 0.0))
            source_step_range = (max(expected_activity) - min(expected_activity)) if expected_activity else 0.0
            target_step_range = (max(actual_activity) - min(actual_activity)) if actual_activity else 0.0
            correlation = _pearson_correlation(expected_activity, actual_activity)
            source_peak_index = expected_activity.index(max(expected_activity)) if expected_activity else 0
            target_peak_index = actual_activity.index(max(actual_activity)) if actual_activity else 0
            source_peak_frame = activity_frames[source_peak_index] if activity_frames else 0
            target_peak_frame = activity_frames[target_peak_index] if activity_frames else 0
            duration = max(1, (max(activity_frames) - min(activity_frames)) if activity_frames else 1)
            peak_delta = abs(int(source_peak_frame) - int(target_peak_frame))
            range_ratio = target_span / max(source_span, 1e-8)
            if source_span <= 0.1:
                activity_ok = target_span <= 5.0
            elif item.get("allow_amplitude_remap"):
                activity_ok = (
                    range_ratio >= 0.02 and
                    correlation >= 0.20 and
                    peak_delta <= max(2, int(duration * 0.25))
                )
            else:
                activity_ok = (
                    range_ratio >= 0.10 and range_ratio <= 10.0 and
                    correlation >= 0.75
                )
            item.update({
                "source_activity_span": source_span,
                "target_activity_span": target_span,
                "source_activity_step_range": source_step_range,
                "target_activity_step_range": target_step_range,
                "activity_range_ratio": range_ratio,
                "activity_correlation": correlation,
                "source_peak_frame": source_peak_frame,
                "target_peak_frame": target_peak_frame,
                "activity_peak_frame_delta": peak_delta,
                "activity_ok": bool(activity_ok),
            })
        item.pop("_expected_first_matrix", None)
        item.pop("_actual_first_matrix", None)
        item.pop("_expected_previous_matrix", None)
        item.pop("_actual_previous_matrix", None)
        item.pop("_expected_activity_total", None)
        item.pop("_actual_activity_total", None)
        if item.get("validation_mode") == "motion_activity":
            item["ok"] = bool(item.get("activity_ok"))
        else:
            item["ok"] = (
                item["max_position_error"] <= float(item.get("position_tolerance", POSITION_TOLERANCE)) and
                item["max_rotation_error_degrees"] <= float(item.get("rotation_tolerance_degrees", ROTATION_TOLERANCE_DEGREES)) and
                item["max_scale_error"] <= float(item.get("scale_tolerance", SCALE_TOLERANCE)) and
                item["max_visibility_error"] <= VISIBILITY_TOLERANCE and
                item["max_fov_error"] <= FOV_TOLERANCE
            )
        if not item["ok"]:
            item["message"] = u"最终评估结果超过容差"
            if item.get("required"):
                failures.append(item)
        results.append(item)
    return {
        "status": "passed" if not failures else "failed",
        "ok": not failures,
        "items": results,
        "failures": failures,
        "summary": {
            "item_count": len(results),
            "passed_count": len([item for item in results if item.get("ok")]),
            "failed_count": len(failures),
        },
        "tolerances": {
            "position": POSITION_TOLERANCE,
            "rotation_degrees": ROTATION_TOLERANCE_DEGREES,
            "scale": SCALE_TOLERANCE,
            "visibility": VISIBILITY_TOLERANCE,
            "fov": FOV_TOLERANCE,
        },
    }


def apply_canonical_package(manifest_or_path, overwrite=False, save_on_validation_failure=False):
    import pymxs
    from anim_migration.migration.constraint_rebuilder import rebuild_constraints_in_loaded_scene
    from anim_migration.migration.xaf_transfer import _try_load_xaf
    from anim_migration.migration.track_transfer import collect_node_track_signatures, json_track_signatures, validate_track_signatures
    from anim_migration.migration.package_importer import _merge_helper_objects

    rt = pymxs.runtime
    manifest = _json_read(manifest_or_path) if isinstance(manifest_or_path, _string_types) else manifest_or_path
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        return {"ok": False, "error_code": "CANON-SCHEMA", "message": u"标准动画包版本不受支持"}
    target_path = _as_text((manifest.get("target", {}) or {}).get("path", ""))
    source_path = _as_text((manifest.get("source", {}) or {}).get("path", ""))
    output_path = _as_text(manifest.get("output_max_path", ""))
    if not os.path.exists(target_path):
        return {"ok": False, "error_code": "CANON-TARGET", "message": u"目标绑定不存在"}
    if os.path.exists(output_path) and not overwrite:
        return {"ok": False, "error_code": "CANON-OUTPUT-EXISTS", "message": u"输出文件已存在: {0}".format(output_path)}

    result = {
        "ok": False,
        "engine": "layer_contract_bridge",
        "package_dir": manifest.get("package_dir", ""),
        "manifest_path": manifest.get("manifest_path", ""),
        "report_txt": manifest.get("report_txt", ""),
        "output_max_path": output_path,
        "warnings": list(manifest.get("warnings", []) or []),
        "timings": {},
    }
    start_time = time.time()
    try:
        _load_scene(rt, target_path)
        anim_range = manifest.get("animation_range", {}) or {}
        start = int(anim_range.get("start", 0))
        end = int(anim_range.get("end", start))
        source_frame_rate = float((manifest.get("source", {}) or {}).get("frame_rate", 30.0))
        if source_frame_rate > 0.0:
            rt.frameRate = source_frame_rate
        rt.animationRange = rt.Interval(start, end)

        camera_stage = time.time()
        camera_merge = _merge_helper_objects(
            rt, source_path, manifest.get("camera_merge", {}) or {}
        )
        result["camera_merge"] = camera_merge
        result["timings"]["merge_source_camera_bundle"] = round(time.time() - camera_stage, 3)

        body_manifest = manifest.get("body", {}) or {}
        body_transport = _as_text(body_manifest.get("transport", "selected_bip_subanims"))
        bip_path = _as_text(body_manifest.get("bip_path", ""))
        root = _find_bip_root(rt)
        selected_names = list(body_manifest.get("selected_node_names", []) or [])
        selected_track_names = list(body_manifest.get("selected_track_names", []) or [])
        selected_indices = list(body_manifest.get("selected_subanim_indices", []) or [])
        expanded_names = []
        if len(selected_track_names) == len(selected_indices):
            expanded_names = selected_track_names
        elif len(selected_indices) == len(selected_names) * 2:
            for name in selected_names:
                expanded_names.extend((name, name))
        elif len(selected_indices) == len(selected_names):
            expanded_names = selected_names
        node_index = _target_node_index(rt)
        if body_transport == "sparse_biped_results":
            prepared_body, body_errors = _apply_sparse_biped_channels(
                rt, body_manifest.get("channels", []) or [], node_index=node_index
            )
            bip_import = {
                "ok": not body_errors,
                "message": u"Biped 稀疏最终结果烘焙成功" if not body_errors else u"Biped 稀疏最终结果烘焙存在错误",
                "transport": body_transport,
                "applied_node_count": len(prepared_body),
                "apply_error_count": len(body_errors),
                "errors": body_errors,
            }
        elif root is None or not os.path.exists(bip_path) or not expanded_names:
            bip_import = {"ok": False, "message": u"目标 Bip001 或 BIP 载荷不存在", "transport": body_transport}
        else:
            try:
                # Load only animated tracks shared by both structures.  This
                # avoids Biped's structure-mismatch dialog and leaves target-
                # only ADV joints (for example a third spine link) intact.
                ok = bool(rt.biped.loadBipFile(
                    root.controller,
                    bip_path,
                    rt.Name("noRedraw"),
                    rt.Name("loadSelectedSubAnimControllers"),
                    rt.Array(*expanded_names),
                    rt.Array(*selected_indices),
                ))
                bip_import = {
                    "ok": ok,
                    "message": u"BIP 共同动画子轨导入成功" if ok else u"BIP 共同动画子轨导入返回失败",
                    "transport": "selected_bip_subanims",
                    "selected_track_count": len(selected_indices),
                }
            except Exception as error:
                bip_import = {"ok": False, "message": _as_text(error), "transport": "selected_bip_subanims"}
        result["bip_import"] = bip_import
        result["timings"]["load_target_and_bip"] = round(time.time() - start_time, 3)

        frames = list(range(start, end + 1))

        stage = time.time()
        constraint_apply = rebuild_constraints_in_loaded_scene(
            rt,
            manifest.get("bones_constraints", {}) or {},
            skip_missing_constraint_targets=False,
        )
        missing_constraint_targets = [
            row for row in (constraint_apply.get("items", []) or [])
            if row.get("removed_missing_targets")
        ]
        if missing_constraint_targets:
            constraint_apply["ok"] = False
            constraint_apply["error_code"] = "CANON-BONES-CONSTRAINT-TARGET-MISSING"
            constraint_apply["message"] = u"Bones 层约束在目标绑定中缺少 Target，已阻止保存"
        constraint_apply["missing_target_count"] = sum([
            len(row.get("removed_missing_targets", []) or [])
            for row in missing_constraint_targets
        ])
        result["bones_constraint_apply"] = constraint_apply
        result["timings"]["rebuild_bones_constraints"] = round(time.time() - stage, 3)

        stage = time.time()
        xaf_apply = []
        for row in manifest.get("xaf_channels", []) or []:
            target_name = _as_text(row.get("target_name", ""))
            target_node = node_index.get(target_name)
            xaf_path = _as_text(row.get("xaf_path", ""))
            if target_node is None:
                ok = False
                message = u"目标六层控制器不存在或不唯一"
            elif not xaf_path or not os.path.exists(xaf_path):
                ok = False
                message = u"六层控制器 XAF 载荷不存在"
            else:
                ok, message = _try_load_xaf(rt, target_node, xaf_path)
            track_validation = {"ok": False, "errors": []}
            if ok and target_node is not None:
                target_tracks = collect_node_track_signatures(
                    rt, target_node, include_samples=True,
                    include_unkeyed=False, include_controllers=False,
                )
                target_tracks = json_track_signatures([
                    track for track in target_tracks
                    if track.get("root_kind") != "modifier"
                ])
                track_validation = validate_track_signatures(
                    row.get("track_signatures", []) or [], target_tracks
                )
                if not track_validation.get("ok", False):
                    ok = False
                    message = u"XAF 导入后控制器轨道验收失败"
            xaf_apply.append({
                "source_name": row.get("source_name", ""),
                "target_name": target_name,
                "scope": row.get("scope", ""),
                "transport": next((
                    channel.get("transport", "")
                    for channel in (manifest.get("channels", []) or [])
                    if channel.get("source_name", "") == row.get("source_name", "")
                ), "xaf"),
                "ok": bool(ok),
                "required": True,
                "message": message,
                "track_validation": track_validation,
            })
        result["xaf_apply"] = {
            "ok": not any([not row.get("ok") for row in xaf_apply]),
            "items": xaf_apply,
            "failed_count": len([row for row in xaf_apply if not row.get("ok")]),
        }
        result["timings"]["apply_layer_xaf"] = round(time.time() - stage, 3)

        stage = time.time()
        prepared, apply_errors = _apply_channels(
            rt, manifest.get("channels", []) or [], frames, node_index=node_index
        )
        result["channel_apply_errors"] = apply_errors
        result["timings"]["apply_canonical_channels"] = round(time.time() - stage, 3)

        validation_rows = []
        validation_rows.extend(((manifest.get("body", {}) or {}).get("validation", []) or []))
        validation_rows.extend(manifest.get("face_validation", []) or [])
        validation_rows.extend(manifest.get("deform_validation", []) or [])
        validation_rows.extend(manifest.get("channels", []) or [])
        stage = time.time()
        validation = validate_canonical_outputs(rt, validation_rows, node_index=node_index)
        result["validation"] = validation
        result["validation_advisories"] = [
            item for item in (validation.get("items", []) or [])
            if not item.get("ok") and not item.get("required")
        ]
        result["timings"]["validate_canonical_outputs"] = round(time.time() - stage, 3)

        required_apply_errors = [item for item in apply_errors if item.get("required")]
        hard_ok = (
            bool(bip_import.get("ok")) and
            bool(camera_merge.get("ok")) and
            bool(constraint_apply.get("ok")) and
            bool(result.get("xaf_apply", {}).get("ok")) and
            not required_apply_errors and
            bool(validation.get("ok"))
        )
        if hard_ok or save_on_validation_failure:
            folder = os.path.dirname(output_path)
            if folder and not os.path.exists(folder):
                os.makedirs(folder)
            rt.saveMaxFile(output_path, quiet=True)
            result["saved"] = True
        else:
            result["saved"] = False
        result["ok"] = bool(hard_ok)
        result["error_code"] = None if hard_ok else ("CANON-CAMERA-MERGE" if not camera_merge.get("ok") else "CANON-VALIDATION")
        result["message"] = u"六层动画与旧镜头整套迁移成功" if hard_ok else (u"旧动画镜头整套合并失败，未写入输出文件" if not camera_merge.get("ok") else u"六层动画迁移或最终验收未通过，未写入输出文件")
        result["summary"] = {
            "applied_channel_count": len(prepared),
            "apply_error_count": len(apply_errors),
            "required_apply_error_count": len(required_apply_errors),
            "bones_constraint_ok": bool(constraint_apply.get("ok")),
            "camera_merge_ok": bool(camera_merge.get("ok")),
            "camera_merged_count": (camera_merge.get("summary", {}) or {}).get("merged_count", 0),
            "camera_merge_failed_count": (camera_merge.get("summary", {}) or {}).get("failed_count", 0),
            "xaf_applied_count": len([row for row in xaf_apply if row.get("ok")]),
            "xaf_failed_count": len([row for row in xaf_apply if not row.get("ok")]),
            "advisory_count": len(result.get("validation_advisories", []) or []),
            "saved": bool(result["saved"]),
        }
    except Exception as error:
        result.update({"ok": False, "saved": False, "error_code": "CANON-APPLY", "message": _as_text(error)})
    finally:
        result["timings"]["total"] = round(time.time() - start_time, 3)
        try:
            _write_text_report(manifest.get("report_txt", ""), manifest, result=result)
            _json_write(os.path.join(manifest.get("package_dir", ""), "canonical_result.json"), result)
        except Exception:
            pass
        if not result.get("saved") and source_path and os.path.exists(source_path):
            try:
                _load_scene(rt, source_path)
            except Exception:
                pass
    return result

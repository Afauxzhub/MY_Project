# -*- coding: utf-8 -*-
from __future__ import print_function
import os

try:
    _text_type = unicode
except NameError:
    _text_type = str


DEFAULT_LOCAL_RULES = {
    "class_tokens": ("dummy", "point", "helper", "expose", "tape", "grid"),
    "superclass_tokens": ("helper",),
    "exclude_class_tokens": ("rectangle", "circle", "line", "spline", "editable spline"),
    "exclude_superclass_tokens": ("shape",),
    "name_tokens": (
        "dummy",
        "point",
        "helper",
        "weapon",
        "wp",
        "prop",
        "locator",
        "loc",
        "target",
        "temp",
        "cam",
        "camera",
        "fx",
        "socket",
        "attach",
        u"武器",
        u"道具",
        u"挂点",
        u"定位",
        u"临时",
        u"镜头",
        u"相机",
        u"目标",
    ),
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


def _safe_name(node):
    try:
        return _as_text(node.name)
    except Exception:
        return u""


def _node_kind(node, rt):
    cls_name = _as_text(rt.classOf(node))
    lower = cls_name.lower()
    name = _safe_name(node).lower()
    if "dummy" in lower:
        return "Dummy"
    if "point" in lower:
        return "Point"
    if "helper" in lower:
        return "Helper"
    if "locator" in name:
        return "Locator"
    if "weapon" in name or "prop" in name or "wp" in name or u"武器" in name or u"道具" in name:
        return "WeaponProp"
    if "target" in name or u"目标" in name:
        return "TempTarget"
    if "cam" in name or "camera" in name or u"镜头" in name or u"相机" in name:
        return "CameraLevelObject"
    return "Helper"


def _safe_class_name(node, rt):
    try:
        return _as_text(rt.classOf(node))
    except Exception:
        return u""


def _safe_superclass_name(node, rt):
    try:
        return _as_text(rt.superClassOf(node))
    except Exception:
        return u""


def _is_local_object(node, rt, rules):
    name = _safe_name(node).lower()
    cls_name = _safe_class_name(node, rt).lower()
    superclass_name = _safe_superclass_name(node, rt).lower()
    class_tokens = tuple([x.lower() for x in rules.get("class_tokens", ())])
    superclass_tokens = tuple([x.lower() for x in rules.get("superclass_tokens", ())])
    exclude_class_tokens = tuple([x.lower() for x in rules.get("exclude_class_tokens", ())])
    exclude_superclass_tokens = tuple([x.lower() for x in rules.get("exclude_superclass_tokens", ())])
    name_tokens = tuple([x.lower() for x in rules.get("name_tokens", ())])
    if any([token in cls_name for token in exclude_class_tokens]):
        return False
    if any([token in superclass_name for token in exclude_superclass_tokens]):
        return False
    if any([token in cls_name for token in class_tokens]):
        return True
    if any([token in superclass_name for token in superclass_tokens]):
        return True
    if any([token in name for token in name_tokens]):
        return True
    return False


def _max_name(rt, value):
    try:
        return rt.Name(value)
    except Exception:
        pass
    try:
        return rt.name(value)
    except Exception:
        pass
    return value


def _safe_property_controller(rt, node, prop_name):
    candidates = [prop_name, _max_name(rt, prop_name)]
    for prop in candidates:
        try:
            ctrl = rt.getPropertyController(node, prop)
            if ctrl is not None:
                return ctrl
        except Exception:
            pass
    return None


def _safe_controller(node, attr_name, rt=None):
    if rt is not None:
        aliases = {
            "position": ("position", "pos"),
            "rotation": ("rotation", "rotation"),
            "scale": ("scale", "scaling"),
            "visibility": ("visibility",),
            "transform": ("transform",),
        }.get(attr_name, (attr_name,))
        for alias in aliases:
            ctrl = _safe_property_controller(rt, node, alias)
            if ctrl is not None:
                return ctrl
    try:
        value = getattr(node, attr_name)
    except Exception:
        return None
    try:
        return value.controller
    except Exception:
        return None


def _node_transform_controllers(rt, node):
    controllers = []
    for attr_name in ("position", "rotation", "scale", "visibility", "transform"):
        ctrl = _safe_controller(node, attr_name, rt)
        if ctrl is not None:
            controllers.append(ctrl)
    try:
        ctrl = node.controller
        if ctrl is not None:
            controllers.append(ctrl)
    except Exception:
        pass
    return controllers


def _safe_parent_name(node):
    try:
        parent = node.parent
    except Exception:
        parent = None
    if parent is None:
        return u""
    return _safe_name(parent)


def _collect_key_times(rt, ctrl, visited=None, depth=0):
    if visited is None:
        visited = set()
    out = []
    if ctrl is None or depth > 6:
        return out
    try:
        ident = id(ctrl)
        if ident in visited:
            return out
        visited.add(ident)
    except Exception:
        pass

    try:
        num = int(ctrl.numKeys)
    except Exception:
        num = 0
    for i in range(1, num + 1):
        try:
            key = rt.getKey(ctrl, i)
            t = int(key.time)
            out.append(t)
        except Exception:
            pass

    try:
        keys = ctrl.keys
        count = int(keys.count)
    except Exception:
        count = 0
    for i in range(1, count + 1):
        try:
            key = keys[i]
            out.append(int(key.time))
        except Exception:
            try:
                key = keys[i - 1]
                out.append(int(key.time))
            except Exception:
                pass

    try:
        sub_count = int(ctrl.numSubs)
    except Exception:
        sub_count = 0
    for i in range(1, sub_count + 1):
        sub_ctrl = None
        try:
            sub_anim = rt.getSubAnim(ctrl, i)
            sub_ctrl = sub_anim.controller
        except Exception:
            pass
        if sub_ctrl is None:
            try:
                sub_ctrl = ctrl[i].controller
            except Exception:
                pass
        if sub_ctrl is not None:
            out.extend(_collect_key_times(rt, sub_ctrl, visited, depth + 1))

    return out


def _frame_from_time(rt):
    try:
        return int(rt.currentTime)
    except Exception:
        return 0


def _sample_transform(rt, node, frames):
    samples = {}
    for f in frames:
        try:
            rt.sliderTime = f
            samples[int(f)] = {
                "position": [float(node.position.x), float(node.position.y), float(node.position.z)],
                "rotation": [float(node.rotation.x), float(node.rotation.y), float(node.rotation.z), float(node.rotation.w)],
                "scale": [float(node.scale.x), float(node.scale.y), float(node.scale.z)],
                "visibility": float(node.visibility),
            }
        except Exception:
            continue
    return samples


def _scan_loaded_scene(rt, scene_path, rules):
    rows = []
    skipped = []
    for node in list(rt.objects):
        try:
            if not _is_local_object(node, rt, rules):
                continue
            name = _safe_name(node)
            if not name:
                continue
            parent_name = _safe_parent_name(node)
            key_times = []
            for ctrl in _node_transform_controllers(rt, node):
                key_times.extend(_collect_key_times(rt, ctrl))
            key_times = sorted(set(key_times))
            rows.append({
                "name": name,
                "parent_name": parent_name or None,
                "class_name": _safe_class_name(node, rt),
                "superclass_name": _safe_superclass_name(node, rt),
                "kind": _node_kind(node, rt),
                "key_times": key_times,
                "has_animation": bool(key_times),
                "samples": _sample_transform(rt, node, key_times),
            })
        except Exception as e:
            skipped.append({"name": _safe_name(node), "reason": _as_text(e)})
    return {
        "scene_path": scene_path,
        "objects": sorted(rows, key=lambda x: x.get("name", "").lower()),
        "skipped": skipped,
    }


def scan_local_objects_from_scene(scene_path, rules=None):
    import pymxs

    rt = pymxs.runtime
    merged_rules = dict(DEFAULT_LOCAL_RULES)
    if isinstance(rules, dict):
        merged_rules.update(rules)

    abs_path = os.path.abspath(_as_text(scene_path)) if scene_path else u""
    if (not abs_path) or (not os.path.exists(abs_path)):
        return {
            "ok": False,
            "error_code": "P3-INPUT-001",
            "message": u"scene_path 无效: {0}".format(abs_path),
            "scene_path": abs_path,
            "objects": [],
        }

    restore = _as_text(rt.maxFilePath) + _as_text(rt.maxFileName)
    restore = restore if restore and os.path.exists(restore) else None
    try:
        rt.loadMaxFile(abs_path, quiet=True, useFileUnits=True)
        result = _scan_loaded_scene(rt, abs_path, merged_rules)
        result["ok"] = True
        result["error_code"] = None
        result["message"] = u""
        return result
    except Exception as e:
        return {
            "ok": False,
            "error_code": "P3-LOCAL-001",
            "message": _as_text(e),
            "scene_path": abs_path,
            "objects": [],
        }
    finally:
        try:
            if restore and os.path.abspath(restore) != abs_path:
                rt.loadMaxFile(restore, quiet=True, useFileUnits=True)
        except Exception:
            pass


def _node_by_name(rt, name):
    for node in list(rt.objects):
        try:
            if _as_text(node.name) == name:
                return node
        except Exception:
            pass
    return None


def _apply_node_samples(rt, node, samples, key_times):
    import pymxs

    def _set_key(controller):
        try:
            if controller is not None:
                rt.setKey(controller)
        except Exception:
            pass

    try:
        ctx = pymxs.animate(True)
    except Exception:
        ctx = None

    if ctx is not None:
        ctx.__enter__()
    try:
        for f in key_times:
            data = samples.get(f) or samples.get(int(f))
            if not data:
                continue
            try:
                rt.sliderTime = int(f)
                p = data.get("position", [0.0, 0.0, 0.0])
                r = data.get("rotation", [0.0, 0.0, 0.0, 1.0])
                s = data.get("scale", [1.0, 1.0, 1.0])
                node.position = rt.Point3(float(p[0]), float(p[1]), float(p[2]))
                node.rotation = rt.Quat(float(r[0]), float(r[1]), float(r[2]), float(r[3]))
                node.scale = rt.Point3(float(s[0]), float(s[1]), float(s[2]))
                node.visibility = float(data.get("visibility", 1.0))
                for ctrl in _node_transform_controllers(rt, node):
                    _set_key(ctrl)
            except Exception:
                continue
    finally:
        if ctx is not None:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass


def apply_local_transfer_plan(plan, animation_range=None):
    import pymxs

    rt = pymxs.runtime
    if not isinstance(plan, dict):
        return {"ok": False, "error_code": "P3-LOCAL-002", "message": u"plan 类型错误", "results": []}

    target_scene_path = _as_text(plan.get("target_scene_path", ""))
    source_scene_path = _as_text(plan.get("source_scene_path", ""))
    if (not source_scene_path) or (not os.path.exists(source_scene_path)):
        return {"ok": False, "error_code": "P3-INPUT-001", "message": u"source_scene_path 无效", "results": []}
    if (not target_scene_path) or (not os.path.exists(target_scene_path)):
        return {"ok": False, "error_code": "P3-INPUT-001", "message": u"target_scene_path 无效", "results": []}

    results = []
    pre_data = {}
    post_data = {}
    restore = _as_text(rt.maxFilePath) + _as_text(rt.maxFileName)
    restore = restore if restore and os.path.exists(restore) else None

    try:
        # Stage A: capture old data by item name.
        rt.loadMaxFile(source_scene_path, quiet=True, useFileUnits=True)
        source_cache = {}
        for item in plan.get("items", []):
            name = _as_text(item.get("source_name", ""))
            if not name:
                continue
            node = _node_by_name(rt, name)
            if node is None:
                results.append({"name": name, "ok": False, "error_code": "P3-LOCAL-003", "message": u"源对象不存在"})
                continue
            key_times = [int(x) for x in item.get("key_times", [])]
            if animation_range and isinstance(animation_range, (list, tuple)) and len(animation_range) == 2:
                start_f = int(animation_range[0])
                end_f = int(animation_range[1])
                key_times = [x for x in key_times if start_f <= x <= end_f]
            samples = _sample_transform(rt, node, key_times)
            source_cache[name] = {"key_times": key_times, "samples": samples, "parent_name": item.get("parent_name"), "kind": item.get("kind")}
            pre_data[name] = {"frames": key_times, "samples": samples}

        # Stage B: verify targets. This stage intentionally never creates old-only objects.
        rt.loadMaxFile(target_scene_path, quiet=True, useFileUnits=True)
        for item in plan.get("items", []):
            source_name = _as_text(item.get("source_name", ""))
            target_name = _as_text(item.get("target_name", source_name))
            cache = source_cache.get(source_name)
            if not cache:
                continue
            try:
                node = _node_by_name(rt, target_name)
                if node is None:
                    results.append({"name": target_name, "source_name": source_name, "ok": False, "error_code": "P3-MISSING-OBJECT", "message": u"目标对象不存在，已跳过且未创建"})
            except Exception as e:
                results.append({"name": target_name, "ok": False, "error_code": "P3-LOCAL-003", "message": _as_text(e)})

        # Stage C: keep existing hierarchy untouched; do not recreate old-file parenting.
        for item in plan.get("items", []):
            source_name = _as_text(item.get("source_name", ""))
            target_name = _as_text(item.get("target_name", source_name))
            parent_name = _as_text(item.get("parent_name", ""))
            if not parent_name:
                continue
            child = _node_by_name(rt, target_name)
            parent = _node_by_name(rt, parent_name)
            if child is None or parent is None:
                continue
            try:
                pass
            except Exception:
                pass

        # Stage D: apply sampled animation only to existing matched objects.
        for item in plan.get("items", []):
            source_name = _as_text(item.get("source_name", ""))
            target_name = _as_text(item.get("target_name", source_name))
            cache = source_cache.get(source_name)
            if not cache:
                continue
            try:
                node = _node_by_name(rt, target_name)
                if node is None:
                    results.append({"name": target_name, "ok": False, "error_code": "P3-LOCAL-004", "message": u"目标对象不存在"})
                    continue
                if not cache.get("key_times"):
                    results.append({"name": target_name, "ok": True, "error_code": None, "message": u"源对象无动画 key，未写入动画"})
                    continue
                _apply_node_samples(rt, node, cache.get("samples", {}), cache.get("key_times", []))
                results.append({"name": target_name, "ok": True, "error_code": None, "message": u""})
            except Exception as e:
                results.append({"name": target_name, "ok": False, "error_code": "P3-LOCAL-003", "message": _as_text(e)})

        rt.saveMaxFile(target_scene_path, quiet=True)

        # Stage E: collect post data for validation.
        for item in plan.get("items", []):
            source_name = _as_text(item.get("source_name", ""))
            target_name = _as_text(item.get("target_name", source_name))
            node = _node_by_name(rt, target_name)
            cache = source_cache.get(source_name) or {}
            if node is None:
                continue
            key_times = cache.get("key_times", [])
            samples = _sample_transform(rt, node, key_times)
            post_data[target_name] = {"frames": key_times, "samples": samples}

        ok = not any([not x.get("ok", False) for x in results if x.get("error_code")])
        return {
            "ok": ok,
            "error_code": None if ok else "P3-LOCAL-003",
            "message": u"" if ok else u"部分本地对象迁移失败",
            "results": results,
            "pre_data": pre_data,
            "post_data": post_data,
            "output_scene_path": target_scene_path,
        }
    except Exception as e:
        return {"ok": False, "error_code": "P3-LOCAL-003", "message": _as_text(e), "results": results}
    finally:
        try:
            if restore and os.path.abspath(restore) != os.path.abspath(target_scene_path):
                rt.loadMaxFile(restore, quiet=True, useFileUnits=True)
        except Exception:
            pass

# -*- coding: utf-8 -*-
from __future__ import print_function
import os
from anim_migration.workflow.max_dialogs import SilentFileDialogs

try:
    _text_type = unicode
except NameError:
    _text_type = str


SUPPORTED_CONSTRAINTS = (
    "Position_Constraint",
    "Orientation_Constraint",
    "LookAt_Constraint",
    "Link_Constraint",
)


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _node_by_name(rt, name):
    name = _as_text(name)
    for node in list(rt.objects):
        try:
            if _as_text(node.name) == name:
                return node
        except Exception:
            pass
    return None


def _safe_class_name(rt, value):
    try:
        return _as_text(rt.classOf(value))
    except Exception:
        return u""


def _mxs_escape(value):
    text = _as_text(value)
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    return text


def _constraint_channel(owner, controller):
    try:
        if owner.controller == controller:
            return "transform"
    except Exception:
        pass
    try:
        if owner.controller.position == controller:
            return "position"
    except Exception:
        pass
    try:
        if owner.controller.rotation == controller:
            return "rotation"
    except Exception:
        pass
    return "unknown"


def _get_target_count(controller):
    try:
        return int(controller.getNumTargets())
    except Exception:
        return 0


def _get_target(controller, index):
    try:
        return controller.getNode(index)
    except Exception:
        pass
    try:
        return controller.getTarget(index)
    except Exception:
        return None


def _get_weight(controller, index):
    try:
        return float(controller.getWeight(index))
    except Exception:
        return 100.0


def _get_link_frame(controller, index):
    try:
        return int(controller.getFrameNo(index))
    except Exception:
        return int(index)


def _is_world_target_row(row):
    return bool(row.get("is_world")) or _as_text(row.get("target_type", "")).lower() == "world" or _as_text(row.get("target_name", "")).lower() == "world"


def _iter_candidate_controllers(rt, node):
    out = []
    try:
        if node.controller is not None:
            out.append(node.controller)
    except Exception:
        pass
    for prop in ("position", "rotation"):
        try:
            ctrl = rt.getPropertyController(node, prop)
            if ctrl is not None:
                out.append(ctrl)
        except Exception:
            pass
    return out


def scan_constraints_in_loaded_scene(rt, mapping=None, eligible_owner_names=None):
    from anim_migration.migration.track_transfer import _controller_tracks, json_track_signatures, sample_track_signature_groups

    mapping = mapping or {}
    eligible_owner_names = set([_as_text(x) for x in (eligible_owner_names or []) if _as_text(x)])
    rows = []
    skipped = []
    constraint_track_groups = []
    try:
        for node in list(rt.objects):
            owner_name = _as_text(getattr(node, "name", ""))
            if not owner_name:
                continue
            if eligible_owner_names and owner_name not in eligible_owner_names:
                continue
            for ctrl in _iter_candidate_controllers(rt, node):
                cls = _safe_class_name(rt, ctrl)
                if cls not in SUPPORTED_CONSTRAINTS:
                    continue
                count = _get_target_count(ctrl)
                targets = []
                for i in range(1, count + 1):
                    target_node = _get_target(ctrl, i)
                    is_world_target = (cls == "Link_Constraint" and target_node is None)
                    target_name = u"World" if is_world_target else (_as_text(getattr(target_node, "name", "")) if target_node is not None else u"")
                    targets.append({
                        "index": i,
                        "source_name": target_name,
                        "target_name": u"World" if is_world_target else (_as_text(mapping.get(target_name, target_name)) if target_name else u""),
                        "target_type": "world" if is_world_target else "node",
                        "is_world": bool(is_world_target),
                        "weight": _get_weight(ctrl, i),
                        "frame": _get_link_frame(ctrl, i) if cls == "Link_Constraint" else None,
                    })
                animated_track_rows = _controller_tracks(
                    rt, ctrl, "constraint", cls, "constraint",
                    include_samples=False, include_unkeyed=False,
                    include_controllers=True,
                )
                constraint_track_groups.append(animated_track_rows)
                rows.append({
                    "owner_source_name": owner_name,
                    "owner_target_name": _as_text(mapping.get(owner_name, owner_name)),
                    "constraint_type": cls,
                    "channel": _constraint_channel(node, ctrl),
                    "targets": targets,
                    "_animated_track_rows": animated_track_rows,
                })
        sample_track_signature_groups(rt, constraint_track_groups)
        for row in rows:
            row["animated_tracks"] = json_track_signatures(row.pop("_animated_track_rows", []))
        return {"ok": True, "error_code": None, "message": u"", "constraints": rows, "skipped": skipped}
    except Exception as e:
        return {"ok": False, "error_code": "P4-SCAN-001", "message": _as_text(e), "constraints": rows, "skipped": skipped}


def scan_constraints_from_scene(scene_path, mapping=None, eligible_owner_names=None):
    import pymxs

    rt = pymxs.runtime
    mapping = mapping or {}
    eligible_owner_names = set([_as_text(x) for x in (eligible_owner_names or []) if _as_text(x)])
    abs_path = os.path.abspath(_as_text(scene_path)) if scene_path else u""
    if (not abs_path) or (not os.path.exists(abs_path)):
        return {"ok": False, "error_code": "P4-INPUT-001", "message": u"scene_path 无效", "constraints": []}

    restore = _as_text(rt.maxFilePath) + _as_text(rt.maxFileName)
    restore = restore if restore and os.path.exists(restore) else None
    rows = []
    skipped = []
    try:
        with SilentFileDialogs(rt):
            rt.loadMaxFile(abs_path, quiet=True, useFileUnits=True)
        return scan_constraints_in_loaded_scene(
            rt, mapping=mapping, eligible_owner_names=eligible_owner_names
        )
    except Exception as e:
        return {"ok": False, "error_code": "P4-SCAN-001", "message": _as_text(e), "constraints": rows, "skipped": skipped}
    finally:
        try:
            if restore and os.path.abspath(restore) != abs_path:
                with SilentFileDialogs(rt):
                    rt.loadMaxFile(restore, quiet=True, useFileUnits=True)
        except Exception:
            pass


def _make_constraint_controller(rt, constraint_type):
    if constraint_type == "Position_Constraint":
        return rt.Position_Constraint()
    if constraint_type == "Orientation_Constraint":
        return rt.Orientation_Constraint()
    if constraint_type == "LookAt_Constraint":
        return rt.LookAt_Constraint()
    if constraint_type == "Link_Constraint":
        return rt.Link_Constraint()
    return None


def _assign_controller(rt, owner, channel, controller):
    if channel == "position":
        for prop in ("position", "pos"):
            try:
                rt.setPropertyController(owner, rt.Name(prop), controller)
                return True
            except Exception:
                pass
            try:
                rt.setPropertyController(owner, prop, controller)
                return True
            except Exception:
                pass
        return False
    if channel == "rotation":
        try:
            rt.setPropertyController(owner, rt.Name("rotation"), controller)
            return True
        except Exception:
            pass
        try:
            rt.setPropertyController(owner, "rotation", controller)
            return True
        except Exception:
            return False
    if channel == "transform":
        try:
            owner.controller = controller
            return True
        except Exception:
            return False
    return False


def _add_target(rt, controller, constraint_type, target, weight, frame):
    if constraint_type == "Link_Constraint":
        try:
            controller.addTarget(target, rt.Time(frame))
        except Exception:
            controller.addTarget(target, frame)
        return True
    try:
        controller.appendTarget(target, float(weight))
        return True
    except Exception:
        pass
    try:
        controller.addTarget(target, float(weight))
        return True
    except Exception:
        return False


def _capture_transform(owner):
    try:
        return owner.transform
    except Exception:
        return None


def _restore_transform(owner, tm):
    if tm is None:
        return
    try:
        owner.transform = tm
    except Exception:
        pass


def _read_mxs_result_triplet(value):
    for indices in ((0, 1, 2), (1, 2, 3)):
        try:
            a = value[indices[0]]
            b = value[indices[1]]
            c = value[indices[2]]
            a_text = _as_text(a).lower()
            if isinstance(a, bool) or a_text in ("true", "false"):
                ok = bool(a) if isinstance(a, bool) else a_text == "true"
                return ok, _as_text(b), _as_text(c)
        except Exception:
            pass
    try:
        return bool(value), u"", u""
    except Exception:
        return False, _as_text(value), u""


def _rebuild_row_with_maxscript(rt, row):
    constraint_type = _as_text(row.get("constraint_type", ""))
    owner_name = _mxs_escape(row.get("owner_target_name", ""))
    channel = _as_text(row.get("channel", ""))
    if constraint_type not in SUPPORTED_CONSTRAINTS:
        return False, u"不支持的约束类型"

    if constraint_type == "Link_Constraint":
        assign_line = "owner.controller = ctrl"
        add_lines = []
        for target_row in row.get("targets", []):
            frame = int(target_row.get("frame", target_row.get("index", 0)) or 0)
            if _is_world_target_row(target_row):
                add_lines.append('ctrl.addWorld frameNo:{0}'.format(frame))
            else:
                target_name = _mxs_escape(target_row.get("target_name", ""))
                add_lines.append(
                    'local t = getNodeByName "{0}"\nif t == undefined then throw "target missing: {0}"\nctrl.addTarget t {1}f'.format(target_name, frame)
                )
    else:
        if channel == "position":
            assign_line = "owner.position.controller = ctrl"
        elif channel == "rotation":
            assign_line = "owner.rotation.controller = ctrl"
        elif channel == "transform":
            assign_line = "owner.controller = ctrl"
        else:
            return False, u"不支持的约束通道"
        add_lines = []
        for target_row in row.get("targets", []):
            target_name = _mxs_escape(target_row.get("target_name", ""))
            weight = float(target_row.get("weight", 100.0))
            add_lines.append(
                'local t = getNodeByName "{0}"\nif t == undefined then throw "target missing: {0}"\ntry (ctrl.appendTarget t {1}) catch (ctrl.addTarget t {1})'.format(target_name, weight)
            )

    code = (
        '(\n'
        'try (\n'
        '  local owner = getNodeByName "{0}"\n'
        '  if owner == undefined then throw "owner missing: {0}"\n'
        '  local preTM = owner.transform\n'
        '  local ctrl = {1}()\n'
        '  {2}\n'
        '  {3}\n'
        '  try(owner.transform = preTM)catch()\n'
        '  #(true, ctrl.getNumTargets() as string, classOf ctrl as string)\n'
        ') catch (#(false, getCurrentException(), ""))'
        '\n)'
    ).format(owner_name, constraint_type, assign_line, "\n  ".join(add_lines))
    try:
        res = rt.execute(code)
        ok, count_text, class_text = _read_mxs_result_triplet(res)
        if ok:
            expected = len(row.get("targets", []) or [])
            count = int(count_text)
            if count < expected:
                return False, u"target 数量不足: {0}/{1}".format(count, expected)
            return True, class_text
        return False, count_text
    except Exception as e:
        return False, _as_text(e)


def _constraint_identity(row):
    return (
        _as_text(row.get("owner_target_name", "")),
        _as_text(row.get("channel", "")),
        _as_text(row.get("constraint_type", "")),
    )


def _source_owner_target_names(constraint_snapshot):
    source_rows = (constraint_snapshot or {}).get("source_scene_objects", None)
    if source_rows is None:
        return None
    names = set()
    for row in source_rows or []:
        if not row.get("target_exists", False):
            continue
        target_name = _as_text(row.get("target_name", ""))
        if target_name:
            names.add(target_name)
    return names


def _managed_owner_channel_keys(constraint_snapshot):
    rows = (constraint_snapshot or {}).get("managed_constraint_channels", None)
    if rows is None:
        return None
    return set([
        (
            _as_text(row.get("owner_target_name", "")),
            _as_text(row.get("channel", "")),
        )
        for row in (rows or [])
        if _as_text(row.get("owner_target_name", "")) and _as_text(row.get("channel", ""))
    ])


def _scan_loaded_supported_constraints(rt):
    rows = []
    for node in list(rt.objects):
        owner_name = _as_text(getattr(node, "name", ""))
        if not owner_name:
            continue
        for ctrl in _iter_candidate_controllers(rt, node):
            cls = _safe_class_name(rt, ctrl)
            if cls not in SUPPORTED_CONSTRAINTS:
                continue
            targets = []
            count = _get_target_count(ctrl)
            for i in range(1, count + 1):
                target_node = _get_target(ctrl, i)
                is_world_target = (cls == "Link_Constraint" and target_node is None)
                target_name = u"World" if is_world_target else (_as_text(getattr(target_node, "name", "")) if target_node is not None else u"")
                targets.append({
                    "index": i,
                    "source_name": target_name,
                    "target_name": target_name,
                    "target_type": "world" if is_world_target else "node",
                    "is_world": bool(is_world_target),
                    "weight": _get_weight(ctrl, i),
                    "frame": _get_link_frame(ctrl, i) if cls == "Link_Constraint" else None,
                })
            rows.append({
                "owner_source_name": owner_name,
                "owner_target_name": owner_name,
                "constraint_type": cls,
                "channel": _constraint_channel(node, ctrl),
                "targets": targets,
            })
    return rows


def _remove_constraint_with_maxscript(rt, row):
    owner_name = _mxs_escape(row.get("owner_target_name", ""))
    channel = _as_text(row.get("channel", ""))
    if channel == "position":
        assign_line = "owner.position.controller = Position_XYZ()"
    elif channel == "rotation":
        assign_line = "owner.rotation.controller = Euler_XYZ()"
    elif channel == "transform":
        assign_line = "owner.controller = PRS()"
    else:
        return False, u"不支持的约束通道"
    code = (
        '(\n'
        'try (\n'
        '  local owner = getNodeByName "{0}"\n'
        '  if owner == undefined then throw "owner missing: {0}"\n'
        '  local preTM = owner.transform\n'
        '  {1}\n'
        '  try(owner.transform = preTM)catch()\n'
        '  #(true, "removed", "")\n'
        ') catch (#(false, getCurrentException(), ""))'
        '\n)'
    ).format(owner_name, assign_line)
    try:
        res = rt.execute(code)
        ok, message, _class_text = _read_mxs_result_triplet(res)
        return ok, message
    except Exception as e:
        return False, _as_text(e)


def remove_constraints_absent_from_snapshot(rt, constraint_snapshot):
    desired = set()
    desired_rows = (constraint_snapshot or {}).get("desired_constraints", None)
    if desired_rows is None:
        desired_rows = (constraint_snapshot or {}).get("constraints", []) or []
    for row in desired_rows or []:
        desired.add(_constraint_identity(row))

    source_owner_names = _source_owner_target_names(constraint_snapshot)
    managed_owner_channels = _managed_owner_channel_keys(constraint_snapshot)
    items = []
    for row in _scan_loaded_supported_constraints(rt):
        if _constraint_identity(row) in desired:
            continue
        owner_name = _as_text(row.get("owner_target_name", ""))
        owner_channel = (owner_name, _as_text(row.get("channel", "")))
        if managed_owner_channels is not None and owner_channel not in managed_owner_channels:
            item = dict(row)
            item.update({
                "status": "preserved_outside_managed_constraint_channel",
                "ok": True,
                "message": u"不属于动画师修改的 Bones owner/通道，保留目标绑定约束",
            })
            items.append(item)
            continue
        if source_owner_names is not None and owner_name not in source_owner_names:
            item = dict(row)
            item.update({
                "status": "preserved_new_binding_owner_absent_in_old_anim",
                "ok": True,
                "message": u"旧动画中不存在该 owner，保留新绑定自带约束",
            })
            items.append(item)
            continue
        ok, message = _remove_constraint_with_maxscript(rt, row)
        item = dict(row)
        item.update({
            "status": "removed_absent_in_old_anim" if ok else "failed_remove_absent",
            "ok": bool(ok),
            "message": message,
        })
        items.append(item)
    failed = [x for x in items if not x.get("ok")]
    return {
        "ok": len(failed) == 0,
        "items": items,
        "removed_count": len([x for x in items if x.get("status") == "removed_absent_in_old_anim"]),
        "failed_count": len(failed),
    }


def rebuild_constraints_in_loaded_scene(rt, constraint_snapshot, skip_missing_constraint_targets=False):
    items = []
    try:
        removal_result = remove_constraints_absent_from_snapshot(rt, constraint_snapshot)
        items.extend(removal_result.get("items", []) or [])
        for row in (constraint_snapshot or {}).get("constraints", []):
            owner_name = _as_text(row.get("owner_target_name", ""))
            owner = _node_by_name(rt, owner_name)
            if owner is None:
                items.append(dict(row, **{"status": "skipped_missing_owner", "ok": True, "message": u"owner 在新文件中不存在"}))
                continue
            missing_targets = []
            resolved_targets = []
            applied_targets = []
            for target_row in row.get("targets", []):
                if _is_world_target_row(target_row):
                    applied_targets.append(target_row)
                    continue
                target_name = _as_text(target_row.get("target_name", ""))
                target = _node_by_name(rt, target_name)
                if target is None:
                    missing_targets.append(target_name)
                else:
                    resolved_targets.append((target_row, target))
                    applied_targets.append(target_row)
            # Target 全丢时不要覆盖新绑定自带约束（空 Link 会导致 Twist 等驱动断链）
            if skip_missing_constraint_targets and missing_targets and (not applied_targets):
                items.append(dict(row, **{
                    "status": "skipped_all_targets_missing",
                    "ok": True,
                    "message": u"跳过约束目标重建：全部 Target 在新绑定缺失，保留新绑定约束 ({0})".format(
                        u", ".join([x or "<missing>" for x in missing_targets])
                    ),
                    "removed_missing_targets": missing_targets,
                    "applied_target_count": 0,
                }))
                continue
            apply_row = dict(row)
            apply_row["targets"] = applied_targets
            native_ok, native_msg = _rebuild_row_with_maxscript(rt, apply_row)
            if native_ok:
                message = native_msg
                if missing_targets:
                    message = u"已按旧动画删除缺失 target: {0}".format(u", ".join([x or "<missing>" for x in missing_targets]))
                elif not applied_targets:
                    message = u"已按旧动画保留空约束 target 列表"
                item = dict(row)
                item.update({
                    "status": "rebuilt",
                    "ok": True,
                    "message": message,
                    "applied_target_count": len(applied_targets),
                    "removed_missing_targets": missing_targets,
                })
                items.append(item)
                continue
            if _as_text(row.get("constraint_type", "")) == "Link_Constraint":
                items.append(dict(row, **{"status": "failed", "ok": False, "message": u"MaxScript 原生 Link_Constraint 重建失败: {0}".format(native_msg)}))
                continue
            ctrl = _make_constraint_controller(rt, _as_text(row.get("constraint_type", "")))
            if ctrl is None:
                items.append(dict(row, **{"status": "skipped_unsupported_constraint", "ok": True, "message": u"不支持的约束类型"}))
                continue
            try:
                pre_transform = _capture_transform(owner)
                if not _assign_controller(rt, owner, _as_text(row.get("channel", "")), ctrl):
                    items.append(dict(row, **{"status": "skipped_unsupported_constraint", "ok": True, "message": u"不支持的约束通道"}))
                    continue
                add_failed = []
                for target_row, target in resolved_targets:
                    added = _add_target(rt, ctrl, _as_text(row.get("constraint_type", "")), target, target_row.get("weight", 100.0), target_row.get("frame", target_row.get("index", 1)))
                    if not added:
                        add_failed.append(_as_text(target_row.get("target_name", "")))
                if add_failed:
                    items.append(dict(row, **{"status": "failed", "ok": False, "message": u"约束 target 添加失败: {0}".format(u", ".join(add_failed))}))
                    continue
                target_count = _get_target_count(ctrl)
                if target_count < len(resolved_targets):
                    items.append(dict(row, **{"status": "failed", "ok": False, "message": u"约束 target 数量校验失败: {0}/{1}".format(target_count, len(resolved_targets))}))
                    continue
                _restore_transform(owner, pre_transform)
                items.append(dict(row, **{"status": "rebuilt", "ok": True, "message": u""}))
            except Exception as e:
                items.append(dict(row, **{"status": "failed", "ok": False, "message": _as_text(e)}))
        failed = [x for x in items if not x.get("ok", True)]
        return {"ok": len(failed) == 0, "error_code": None if not failed else "P4-APPLY-001", "message": u"" if not failed else u"部分约束重建失败", "items": items}
    except Exception as e:
        return {"ok": False, "error_code": "P4-APPLY-001", "message": _as_text(e), "items": items}


def rebuild_constraints_in_scene(target_scene_path, constraint_snapshot):
    import pymxs

    rt = pymxs.runtime
    abs_path = os.path.abspath(_as_text(target_scene_path)) if target_scene_path else u""
    if (not abs_path) or (not os.path.exists(abs_path)):
        return {"ok": False, "error_code": "P4-INPUT-001", "message": u"target_scene_path 无效", "items": []}

    restore = _as_text(rt.maxFilePath) + _as_text(rt.maxFileName)
    restore = restore if restore and os.path.exists(restore) else None
    items = []
    try:
        with SilentFileDialogs(rt):
            rt.loadMaxFile(abs_path, quiet=True, useFileUnits=True)
        for row in (constraint_snapshot or {}).get("constraints", []):
            owner_name = _as_text(row.get("owner_target_name", ""))
            owner = _node_by_name(rt, owner_name)
            if owner is None:
                items.append(dict(row, **{"status": "skipped_missing_owner", "ok": True, "message": u"owner 在新文件中不存在"}))
                continue
            missing_targets = []
            resolved_targets = []
            applied_targets = []
            for target_row in row.get("targets", []):
                if _is_world_target_row(target_row):
                    applied_targets.append(target_row)
                    continue
                target_name = _as_text(target_row.get("target_name", ""))
                target = _node_by_name(rt, target_name)
                if target is None:
                    missing_targets.append(target_name)
                else:
                    resolved_targets.append((target_row, target))
                    applied_targets.append(target_row)
            apply_row = dict(row)
            apply_row["targets"] = applied_targets
            native_ok, native_msg = _rebuild_row_with_maxscript(rt, apply_row)
            if native_ok:
                message = native_msg
                if missing_targets:
                    message = u"已按旧动画删除缺失 target: {0}".format(u", ".join([x or "<missing>" for x in missing_targets]))
                elif not applied_targets:
                    message = u"已按旧动画保留空约束 target 列表"
                item = dict(row)
                item.update({
                    "status": "rebuilt",
                    "ok": True,
                    "message": message,
                    "applied_target_count": len(applied_targets),
                    "removed_missing_targets": missing_targets,
                })
                items.append(item)
                continue
            if _as_text(row.get("constraint_type", "")) == "Link_Constraint":
                items.append(dict(row, **{"status": "failed", "ok": False, "message": u"MaxScript 原生 Link_Constraint 重建失败: {0}".format(native_msg)}))
                continue
            ctrl = _make_constraint_controller(rt, _as_text(row.get("constraint_type", "")))
            if ctrl is None:
                items.append(dict(row, **{"status": "skipped_unsupported_constraint", "ok": True, "message": u"不支持的约束类型"}))
                continue
            try:
                pre_transform = _capture_transform(owner)
                if not _assign_controller(rt, owner, _as_text(row.get("channel", "")), ctrl):
                    items.append(dict(row, **{"status": "skipped_unsupported_constraint", "ok": True, "message": u"不支持的约束通道"}))
                    continue
                add_failed = []
                for target_row, target in resolved_targets:
                    added = _add_target(rt, ctrl, _as_text(row.get("constraint_type", "")), target, target_row.get("weight", 100.0), target_row.get("frame", target_row.get("index", 1)))
                    if not added:
                        add_failed.append(_as_text(target_row.get("target_name", "")))
                if add_failed:
                    items.append(dict(row, **{"status": "failed", "ok": False, "message": u"约束 target 添加失败: {0}".format(u", ".join(add_failed))}))
                    continue
                target_count = _get_target_count(ctrl)
                if target_count < len(resolved_targets):
                    items.append(dict(row, **{"status": "failed", "ok": False, "message": u"约束 target 数量校验失败: {0}/{1}".format(target_count, len(resolved_targets))}))
                    continue
                _restore_transform(owner, pre_transform)
                items.append(dict(row, **{"status": "rebuilt", "ok": True, "message": u""}))
            except Exception as e:
                items.append(dict(row, **{"status": "failed", "ok": False, "message": _as_text(e)}))
        rt.saveMaxFile(abs_path, quiet=True)
        try:
            with SilentFileDialogs(rt):
                rt.loadMaxFile(abs_path, quiet=True, useFileUnits=True)
            verified = scan_constraints_from_scene(
                abs_path,
                mapping={},
                eligible_owner_names=[_as_text(x.get("owner_target_name", "")) for x in items if x.get("status") == "rebuilt"],
            )
            verified_keys = set()
            for row in verified.get("constraints", []) or []:
                target_names = tuple([_as_text(t.get("target_name", "")) for t in row.get("targets", [])])
                verified_keys.add((_as_text(row.get("owner_target_name", "")), _as_text(row.get("channel", "")), _as_text(row.get("constraint_type", "")), target_names))
            for item in items:
                if item.get("status") != "rebuilt":
                    continue
                target_names = tuple([_as_text(t.get("target_name", "")) for t in item.get("targets", [])])
                key = (_as_text(item.get("owner_target_name", "")), _as_text(item.get("channel", "")), _as_text(item.get("constraint_type", "")), target_names)
                if key not in verified_keys:
                    item["status"] = "failed"
                    item["ok"] = False
                    item["message"] = u"保存后重新扫描未找到该约束，未计为重建成功"
        except Exception as e:
            for item in items:
                if item.get("status") == "rebuilt":
                    item["status"] = "failed"
                    item["ok"] = False
                    item["message"] = u"约束保存后验证失败: {0}".format(_as_text(e))
        failed = [x for x in items if x.get("status") == "failed"]
        return {"ok": len(failed) == 0, "error_code": None if not failed else "P4-APPLY-001", "message": u"" if not failed else u"部分约束重建失败", "items": items}
    except Exception as e:
        return {"ok": False, "error_code": "P4-APPLY-001", "message": _as_text(e), "items": items}
    finally:
        try:
            if restore and os.path.abspath(restore) != abs_path:
                with SilentFileDialogs(rt):
                    rt.loadMaxFile(restore, quiet=True, useFileUnits=True)
        except Exception:
            pass


def build_phase4_constraints_report(scan_result, apply_result):
    scan_result = scan_result or {}
    apply_result = apply_result or {}
    items = apply_result.get("items", []) or []
    scanned_rows = scan_result.get("desired_constraints", scan_result.get("constraints", [])) or []
    def _count(status):
        return len([x for x in items if x.get("status") == status])
    return {
        "enabled": True,
        "status": "failed" if not apply_result.get("ok", False) else "passed",
        "summary": {
            "scanned_count": len(scan_result.get("constraints", []) or []),
            "preserved_binding_internal_count": len([x for x in scanned_rows if x.get("status") == "preserved_binding_internal"]),
            "removed_absent_count": _count("removed_absent_in_old_anim"),
            "preserved_new_binding_absent_owner_count": _count("preserved_new_binding_owner_absent_in_old_anim"),
            "preserved_new_binding_missing_targets_count": _count("preserved_new_binding_missing_targets"),
            "skipped_all_targets_missing_count": _count("skipped_all_targets_missing"),
            "rebuilt_count": _count("rebuilt"),
            "skipped_missing_owner": _count("skipped_missing_owner"),
            "skipped_missing_target": _count("skipped_missing_target"),
            "skipped_unsupported_constraint": _count("skipped_unsupported_constraint"),
            "failed_count": len([x for x in items if not x.get("ok", True)]),
        },
        "items": items,
        "errors": [x for x in items if not x.get("ok", True)],
        "warnings": [x for x in items if _as_text(x.get("status", "")).startswith("skipped_")],
    }

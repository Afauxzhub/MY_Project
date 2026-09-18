# -*- coding: utf-8 -*-
from __future__ import print_function
import io
import json
import os
import shutil
import tempfile
import time

from anim_migration.migration.constraint_rebuilder import build_phase4_constraints_report, rebuild_constraints_in_loaded_scene
from anim_migration.migration.local_object_transfer import _collect_key_times, _safe_controller
from anim_migration.migration.package_exporter import _as_text, _get_max_file_names, _json_write
from anim_migration.migration.track_transfer import apply_morph_payload, clear_matching_track_keys, collect_node_track_signatures, sample_track_signature_groups, suspended_scene_redraw, validate_track_signatures
from anim_migration.migration.xaf_transfer import _try_load_xaf_nodes
from anim_migration.workflow.max_dialogs import SilentFileDialogs


def _json_read(path, default=None):
    if not path or not os.path.exists(path):
        return default if default is not None else {}
    with io.open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read())


def _node_by_name(rt, name):
    name = _as_text(name)
    for node in list(rt.objects):
        try:
            if _as_text(node.name) == name:
                return node
        except Exception:
            pass
    return None


def _loaded_scene_names(rt):
    names = []
    for node in list(rt.objects):
        try:
            name = _as_text(node.name)
        except Exception:
            name = u""
        if name:
            names.append(name)
    return set(names)


def _legacy_source_scene_objects(rt, old_anim_path):
    old_names = _get_max_file_names(rt, old_anim_path)
    new_names = _loaded_scene_names(rt)
    return [
        {
            "source_name": name,
            "target_name": name,
            "mapping_method": "legacy_exact_name",
            "target_exists": name in new_names,
        }
        for name in sorted(old_names, key=lambda x: x.lower())
    ]


def _mxs_escape(text):
    return _as_text(text).replace('"', '\\"')


def _mxs_string_literal(text):
    return _as_text(text).replace("\\", "\\\\").replace('"', '\\"')


def _mxs_array_values(value):
    if value is None:
        return []
    try:
        count = int(value.count)
        return [value[i] for i in range(1, count + 1)]
    except Exception:
        pass
    try:
        return list(value)
    except Exception:
        return []


def _clear_target_rig_animation_keys(rt):
    # Destructive scene-wide cleanup used to remove authored facial/control
    # animation from the new rig before the transfer had proved compatibility.
    # Keep the callable for old manifests, but make the operation a no-op.
    return {
        "ok": True,
        "status": "disabled_preserve_target_rig",
        "keys_deleted": 0,
        "message": u"已禁用目标绑定全局删键；仅替换通过同构校验的动画轨道",
    }

    # Legacy implementation retained below for audit/history; unreachable.
    """Clear animation keys carried by the target rig, preserving/adding only frame 0 keys."""
    script = u'''(
        local visited = #()
        local controllersSeen = 0
        local controllersWithKeys = 0
        local skippedScriptControllers = 0
        local keysBefore = 0
        local keysDeleted = 0
        local zeroKeysAdded = 0
        local errorCount = 0

        fn _OP_RU_isZeroTime t =
        (
            try((t as integer) == 0)catch(false)
        )

        fn _OP_RU_isProceduralController c =
        (
            local cls = ""
            try(cls = toLower ((classof c) as string))catch(cls = "")
            matchPattern cls pattern:"*script*" ignoreCase:true or
            matchPattern cls pattern:"*expression*" ignoreCase:true
        )

        fn _OP_RU_walkController c =
        (
            if c == undefined then return false
            if (findItem visited c) > 0 then return false
            append visited c
            controllersSeen += 1
            if _OP_RU_isProceduralController c do
            (
                skippedScriptControllers += 1
                return false
            )

            local keyCount = 0
            try(keyCount = numKeys c)catch(keyCount = 0)
            if keyCount > 0 do
            (
                controllersWithKeys += 1
                keysBefore += keyCount

                local hasZeroKey = false
                sliderTime = 0f
                for i = 1 to keyCount do
                (
                    try
                    (
                        local k = getKey c i
                        if k != undefined and (_OP_RU_isZeroTime k.time) do hasZeroKey = true
                    )
                    catch()
                )
                if not hasZeroKey do
                (
                    try(addNewKey c 0f; zeroKeysAdded += 1)catch()
                )

                try(keyCount = numKeys c)catch()
                for i = keyCount to 1 by -1 do
                (
                    local shouldDelete = false
                    try
                    (
                        local k = getKey c i
                        shouldDelete = (k != undefined and not (_OP_RU_isZeroTime k.time))
                    )
                    catch(shouldDelete = false)
                    if shouldDelete do
                    (
                        try(deleteKey c i; keysDeleted += 1)catch(errorCount += 1)
                    )
                )
            )

            local subCount = 0
            try(subCount = c.numSubs)catch(subCount = 0)
            for si = 1 to subCount do
            (
                local subAnim = undefined
                local subCtrl = undefined
                try(subAnim = getSubAnim c si)catch()
                try(subCtrl = subAnim.controller)catch()
                if subCtrl != undefined do _OP_RU_walkController subCtrl
            )
            true
        )

        sliderTime = 0f
        for n in objects do
        (
            try(_OP_RU_walkController n.controller)catch(errorCount += 1)
            local vc = undefined
            try(vc = getPropertyController n #visibility)catch()
            if vc != undefined do try(_OP_RU_walkController vc)catch(errorCount += 1)
        )
        #(controllersSeen, controllersWithKeys, keysBefore, keysDeleted, zeroKeysAdded, errorCount, skippedScriptControllers)
    )'''
    try:
        raw = rt.execute(script)
        return {
            "ok": True,
            "status": "cleared" if int(raw[1]) > 0 else "no_animation_keys",
            "controllers_scanned": int(raw[0]),
            "controllers_with_keys": int(raw[1]),
            "keys_before": int(raw[2]),
            "keys_deleted": int(raw[3]),
            "zero_keys_added": int(raw[4]),
            "error_count": int(raw[5]),
            "skipped_script_expression_controllers": int(raw[6]),
            "preserved_frame": 0,
        }
    except Exception as e:
        return {
            "ok": False,
            "status": "failed",
            "message": _as_text(e),
            "preserved_frame": 0,
        }


def _channel_key_counts(rt, node):
    out = {}
    for channel in ("position", "rotation", "scale", "visibility", "transform"):
        ctrl = _safe_controller(node, channel, rt)
        times = _collect_key_times(rt, ctrl) if ctrl is not None else []
        out[channel] = len(sorted(set([int(x) for x in times])))
    return out


def _channel_mismatches(source_counts, target_counts):
    rows = []
    for channel in ("position", "rotation", "scale", "visibility", "transform"):
        src = int((source_counts or {}).get(channel, 0) or 0)
        dst = int((target_counts or {}).get(channel, 0) or 0)
        if src > 0 and dst == 0:
            rows.append({"channel": channel, "source_key_count": src, "target_key_count": dst})
    return rows


def _controller_profile(rt, node):
    profile = {}
    for channel in ("transform", "position", "rotation", "scale", "visibility"):
        ctrl = _safe_controller(node, channel, rt)
        if ctrl is None and channel == "transform":
            try:
                ctrl = node.controller
            except Exception:
                ctrl = None
        profile[channel] = _as_text(rt.classOf(ctrl)) if ctrl is not None else u""
        if channel in ("position", "rotation", "scale") and not profile[channel]:
            profile[channel] = _controller_class_from_prs_subcontroller(rt, node, channel)
    return profile


def _controller_class_from_prs_subcontroller(rt, node, channel):
    name = u""
    try:
        name = _as_text(node.name)
    except Exception:
        pass
    if not name:
        return u""
    script = u'''(
        local n = getNodeByName "{0}"
        if n == undefined then "" else
        (
            local c = undefined
            try(c = n.{1}.controller)catch()
            if c == undefined do try(c = n.controller.{1}.controller)catch()
            if c == undefined do try(c = getPropertyController n #{1})catch()
            if c == undefined then "" else ((classof c) as string)
        )
    )'''.format(_mxs_escape(name), channel)
    try:
        return _as_text(rt.execute(script))
    except Exception:
        return u""


def _is_tcb_controller(class_name):
    return "tcb" in _as_text(class_name).lower()


def _make_tcb_controller(rt, channel):
    def _make(names):
        last_error = u""
        for name in names:
            try:
                return getattr(rt, name)()
            except Exception as e:
                last_error = _as_text(e)
            try:
                return rt.execute("{0}()".format(name))
            except Exception as e:
                last_error = _as_text(e)
        raise RuntimeError(last_error or u"无法创建 TCB 控制器")
    if channel == "position":
        return _make(("TCB_Position", "TCB_position"))
    if channel == "rotation":
        return _make(("TCB_Rotation", "TCB_rotation"))
    return None


def _set_channel_controller(rt, node, channel, controller):
    if controller is None:
        return False, u"controller is None"
    attempts = []
    try:
        attempts.append(lambda: rt.setPropertyController(node, rt.Name(channel), controller))
    except Exception:
        pass
    attempts.append(lambda: rt.setPropertyController(node, channel, controller))
    if channel == "position":
        attempts.append(lambda: setattr(node.position, "controller", controller))
    elif channel == "rotation":
        attempts.append(lambda: setattr(node.rotation, "controller", controller))
    else:
        return False, u"unsupported channel"

    messages = []
    for fn in attempts:
        try:
            fn()
            current = _controller_profile(rt, node).get(channel, u"")
            if _is_tcb_controller(current):
                return True, u""
            messages.append(u"控制器替换后复查仍为 {0}".format(current))
        except Exception as e:
            messages.append(_as_text(e))
    return False, u"; ".join([x for x in messages if x]) or u"控制器替换失败"


def _set_tcb_channel_controller_via_mxs(rt, node, channel):
    name = u""
    try:
        name = _as_text(node.name)
    except Exception:
        pass
    if not name:
        return False, u"节点名为空"
    ctor = "TCB_Position" if channel == "position" else "TCB_Rotation"
    script = u'''(
        local n = getNodeByName "{0}"
        if n == undefined then #(false, "missing node", "") else
        (
            local ok = false
            local msg = ""
            try(n.{1}.controller = {2}(); ok = true)catch(msg += (getCurrentException() + "; "))
            if not ok do try(n.controller.{1}.controller = {2}(); ok = true)catch(msg += (getCurrentException() + "; "))
            if not ok do try(setPropertyController n #{1} ({2}()); ok = true)catch(msg += (getCurrentException() + "; "))
            local c = undefined
            try(c = n.{1}.controller)catch()
            if c == undefined do try(c = n.controller.{1}.controller)catch()
            if c == undefined do try(c = getPropertyController n #{1})catch()
            local cls = if c == undefined then "" else ((classof c) as string)
            #(ok, msg, cls)
        )
    )'''.format(_mxs_escape(name), channel, ctor)
    try:
        raw = rt.execute(script)
        try:
            ok = bool(raw[1])
            msg = _as_text(raw[2])
            cls = _as_text(raw[3])
        except Exception:
            ok = bool(raw[0])
            msg = _as_text(raw[1])
            cls = _as_text(raw[2])
        if _is_tcb_controller(cls):
            return True, u""
        return False, msg or u"控制器替换后复查仍为 {0}".format(cls)
    except Exception as e:
        return False, _as_text(e)


def _sync_supported_controller_profile(rt, node, row, constrained_names):
    target_name = _as_text(row.get("target_name", row.get("source_name", "")))
    source_profile = row.get("controller_profile", {}) or {}
    before = _controller_profile(rt, node)
    result = {
        "status": "skipped",
        "changed": False,
        "message": u"",
        "before": before,
        "after": before,
        "changes": [],
    }
    if target_name in constrained_names:
        result["message"] = u"目标对象有约束，跳过控制器同步"
        return result
    for channel in ("position", "rotation"):
        source_class = _as_text(source_profile.get(channel, ""))
        target_class = _as_text(before.get(channel, ""))
        if not _is_tcb_controller(source_class):
            continue
        if _is_tcb_controller(target_class):
            continue
        try:
            controller = _make_tcb_controller(rt, channel)
            ok, set_message = _set_channel_controller(rt, node, channel, controller)
            if not ok:
                ok, set_message = _set_tcb_channel_controller_via_mxs(rt, node, channel)
            if ok:
                result["changes"].append({
                    "channel": channel,
                    "from": target_class,
                    "to": source_class,
                    "method": "tcb_controller_sync",
                })
            else:
                result["changes"].append({
                    "channel": channel,
                    "from": target_class,
                    "to": source_class,
                    "error": set_message,
                })
        except Exception as e:
            result["changes"].append({
                "channel": channel,
                "from": target_class,
                "to": source_class,
                "error": _as_text(e),
            })
    result["after"] = _controller_profile(rt, node)
    changed = bool([x for x in result["changes"] if not x.get("error")])
    failed = bool([x for x in result["changes"] if x.get("error")])
    result["changed"] = changed
    if failed:
        result["status"] = "warning"
        result["message"] = u"部分控制器同步失败"
    elif changed:
        result["status"] = "synced"
        result["message"] = u"已同步 TCB 控制器"
    else:
        result["status"] = "unchanged"
        result["message"] = u"无需同步控制器"
    return result


def _merge_helper_objects(rt, old_anim_path, helpers_data):
    rows = (helpers_data or {}).get("objects", []) or []
    result_rows = []
    names = []
    for row in rows:
        name = _as_text(row.get("name", ""))
        if not name:
            continue
        if row.get("merge_status") != "pending":
            result_rows.append(dict(row, **{"import_status": "skipped"}))
            continue
        if _node_by_name(rt, name) is not None:
            result_rows.append(dict(row, **{"import_status": "skipped_exists_in_scene"}))
            continue
        names.append(name)
    if not names:
        return {"ok": True, "summary": {"merged_count": 0, "failed_count": 0}, "items": result_rows}
    if not old_anim_path or not os.path.exists(old_anim_path):
        msg = u"旧动画文件不存在，无法合并缺失对象: {0}".format(_as_text(old_anim_path))
        for name in names:
            result_rows.append({"name": name, "import_status": "failed", "message": msg})
        return {"ok": False, "summary": {"merged_count": 0, "failed_count": len(names)}, "items": result_rows}

    name_items = u", ".join([u'"{0}"'.format(_mxs_escape(x)) for x in names])
    script = u'''(
        local oldFile = "{0}"
        local wanted = #({1})
        local ok = false
        local msg = ""
        local selectedNames = #()
        local newNames = #()
        local beforeNodes = for n in objects collect n
        try
        (
            clearSelection()
            ok = mergeMAXFile oldFile wanted #select #autoRenameDups quiet:true
        )
        catch
        (
            msg = getCurrentException()
            ok = false
        )
        try(for n in selection do append selectedNames n.name)catch()
        try(for n in objects where (findItem beforeNodes n) == 0 do append newNames n.name)catch()
        #(ok, msg, selectedNames, newNames)
    )'''.format(_mxs_string_literal(old_anim_path), name_items)
    ok = False
    msg = u""
    selected_names = []
    new_names = []
    try:
        raw = rt.execute(script)
        try:
            ok = bool(raw[1])
            msg = _as_text(raw[2])
            selected_names = [_as_text(x) for x in _mxs_array_values(raw[3])]
            new_names = [_as_text(x) for x in _mxs_array_values(raw[4])]
        except Exception:
            ok = bool(raw[0])
            msg = _as_text(raw[1])
            selected_names = [_as_text(x) for x in _mxs_array_values(raw[2])]
            new_names = [_as_text(x) for x in _mxs_array_values(raw[3])]
    except Exception as e:
        ok = False
        msg = _as_text(e)

    merged = 0
    failed = 0
    for name in names:
        exists = _node_by_name(rt, name) is not None
        status = "merged" if exists else "failed"
        if status == "merged":
            merged += 1
            row_msg = msg
            if not ok and not row_msg:
                row_msg = u"mergeMAXFile 返回失败，但对象已存在于场景，按实际存在判定为已合并"
        else:
            failed += 1
            row_msg = msg
            if not row_msg:
                detail = []
                if selected_names:
                    detail.append(u"selection: {0}".format(u", ".join(selected_names)))
                if new_names:
                    detail.append(u"new_nodes: {0}".format(u", ".join(new_names)))
                if not detail:
                    detail.append(u"mergeMAXFile 未返回错误信息，且目标对象未出现在场景")
                row_msg = u"; ".join(detail)
        result_rows.append({"name": name, "import_status": status, "message": row_msg})
    return {"ok": failed == 0, "summary": {"merged_count": merged, "failed_count": failed}, "items": result_rows}


def _set_animation_range(rt, anim_range):
    start = int((anim_range or {}).get("start", 0))
    end = int((anim_range or {}).get("end", start))
    try:
        rt.animationRange = rt.interval(rt.Time(start), rt.Time(end))
    except Exception:
        try:
            rt.animationRange = rt.interval(start, end)
        except Exception:
            pass
    try:
        rt.sliderTime = start
    except Exception:
        pass
    return {"start": start, "end": end}


def _sample_node_z(rt, node, samples):
    rows = []
    for sample in samples or []:
        frame = int(sample.get("frame", 0))
        try:
            rt.sliderTime = frame
            rows.append({"frame": frame, "world_z": float(node.transform.row4.z)})
        except Exception as e:
            rows.append({"frame": frame, "error": _as_text(e)})
    return rows


def _first_valid_z(samples):
    for item in samples or []:
        if "world_z" in item:
            return float(item.get("world_z", 0.0))
    return None


def _apply_bip_com_height(rt, com_data, tolerance=0.1):
    result = {
        "ok": True,
        "applied": False,
        "delta_z": 0.0,
        "status": "skipped",
        "message": u"",
        "before_samples": [],
        "after_samples": [],
        "max_abs_error": 0.0,
    }
    root_name = _as_text((com_data or {}).get("bip_root", "Bip001")) or "Bip001"
    node = _node_by_name(rt, root_name) or _node_by_name(rt, "Bip001")
    if node is None:
        result.update({"ok": False, "status": "failed", "message": u"新文件中找不到 BIP 根，无法校正质心高度"})
        return result

    old_samples = (com_data or {}).get("samples", []) or []
    before = _sample_node_z(rt, node, old_samples)
    old_start_z = _first_valid_z(old_samples)
    new_start_z = _first_valid_z(before)
    result["before_samples"] = before
    if old_start_z is None or new_start_z is None:
        result.update({"status": "skipped", "message": u"缺少有效高度采样，未校正"})
        return result

    delta = float(old_start_z) - float(new_start_z)
    result["delta_z"] = delta
    if abs(delta) <= tolerance:
        result.update({"status": "passed", "message": u"质心高度差在阈值内"})
    else:
        # This is a single offset on the imported BIP root, not a frame-by-frame bake.
        try:
            start = int(((com_data or {}).get("animation_range", {}) or {}).get("start", 0))
            rt.sliderTime = start
            pos = node.position
            node.position = rt.Point3(float(pos.x), float(pos.y), float(pos.z) + delta)
            result["applied"] = True
            result["status"] = "corrected"
            result["message"] = u"已按首帧质心高度差做整体 Z 偏移"
        except Exception as e:
            result.update({"ok": False, "status": "failed", "message": _as_text(e)})
            return result

    after = _sample_node_z(rt, node, old_samples)
    result["after_samples"] = after
    errors = []
    old_by_frame = dict([(int(x.get("frame", 0)), x) for x in old_samples if "world_z" in x])
    for item in after:
        frame = int(item.get("frame", 0))
        if "world_z" not in item or frame not in old_by_frame:
            continue
        errors.append(abs(float(item["world_z"]) - float(old_by_frame[frame]["world_z"])))
    result["max_abs_error"] = max(errors) if errors else 0.0
    if result["max_abs_error"] > tolerance:
        result["ok"] = False
        result["status"] = "bip_com_height_mismatch"
        result["message"] = u"质心高度不是稳定整体偏移，已写入报告，请人工复核"
    return result


def _import_bip(rt, bip_path, target_name="Bip001"):
    target = _node_by_name(rt, target_name)
    if target is None:
        return {"ok": False, "status": "failed", "message": u"新绑定缺少目标 BIP 根: {0}".format(target_name)}
    if not bip_path or not os.path.exists(bip_path):
        return {"ok": False, "status": "failed", "message": u"BIP 文件不存在: {0}".format(_as_text(bip_path))}
    try:
        ok = bool(rt.biped.loadBipFile(target.controller, bip_path))
        return {"ok": ok, "status": "succeeded" if ok else "failed", "message": u"BIP 导入成功" if ok else u"BIP 导入返回失败", "bip_path": bip_path}
    except Exception as e:
        return {"ok": False, "status": "failed", "message": _as_text(e), "bip_path": bip_path}


def _append_xaf_import_results(results, rows, nodes, ok, msg, constrained_names, rt):
    controller_sync_by_name = {}
    for row, node in zip(rows, nodes):
        target_name = _as_text(row.get("target_name", row.get("source_name", "")))
        controller_sync_by_name[target_name] = _sync_supported_controller_profile(rt, node, row, constrained_names)
    for row, node in zip(rows, nodes):
        target_name = _as_text(row.get("target_name", row.get("source_name", "")))
        target_counts = _channel_key_counts(rt, node) if node is not None else {}
        source_counts = row.get("channel_key_counts", {}) or {}
        mismatches = _channel_mismatches(source_counts, target_counts) if ok else []
        results.append(dict(row, **{
            "xaf_import_status": "succeeded" if ok else "failed",
            "message": msg,
            "target_channel_key_counts": target_counts,
            "channel_key_mismatches": mismatches,
            "channel_key_status": "warning" if mismatches else ("passed" if ok else "failed"),
            "controller_sync": controller_sync_by_name.get(target_name, {"status": "skipped"}),
            "xaf_import_mode": row.get("xaf_export_mode", ""),
        }))


def _import_xaf_rows(
    rt,
    non_bip_data,
    constrained_names=None,
    skip_owner_names=None,
    allow_preflight_blockers=False,
):
    rows = (non_bip_data or {}).get("objects", []) or []
    constrained_names = set([_as_text(x) for x in (constrained_names or []) if _as_text(x)])
    skip_owner_names = set([_as_text(x) for x in (skip_owner_names or []) if _as_text(x)])
    batch = (non_bip_data or {}).get("batch_xaf", {}) or {}
    batch_path = _as_text(batch.get("xaf_path", ""))
    results = []
    groups = []
    group_paths = []
    path_index = {}

    for row in rows or []:
        source = _as_text(row.get("source_name", ""))
        target_name = _as_text(row.get("target_name", source))
        if row.get("xaf_export_status") == "ignored_obsolete_tracks":
            results.append(dict(row, **{
                "xaf_import_status": "ignored_obsolete_tracks",
                "message": u"旧 Morpher 轨道已由导出预检按 ADV 过时设计忽略",
            }))
            continue
        if row.get("xaf_export_status") == "morph_bake_only":
            results.append(dict(row, **{
                "xaf_import_status": "morph_bake_only",
                "message": u"该对象仅含 Morpher 动画，跳过 XAF 并使用逐通道烘焙",
            }))
            continue
        if row.get("xaf_export_status") == "blocked_preflight" and allow_preflight_blockers:
            results.append(dict(row, **{
                "xaf_import_status": "ignored_preflight_blocker",
                "message": u"用户选择忽略预检错误；该对象未导入，目标绑定保持原状",
            }))
            continue
        if row.get("xaf_export_status") == "deferred_merge_source_object":
            results.append(dict(row, **{"xaf_import_status": "deferred_merge_source_object", "message": u"等待合并源场景相机或 Ref_ 辅助对象"}))
            continue
        if row.get("xaf_export_status") != "succeeded":
            results.append(dict(row, **{"xaf_import_status": "skipped_export_failed", "message": row.get("message", "")}))
            continue
        if target_name in skip_owner_names or source in skip_owner_names:
            results.append(dict(row, **{
                "xaf_import_status": "skipped_missing_constraint_target",
                "message": u"跳过约束目标重建：保留新绑定约束，不导入该对象 XAF",
            }))
            continue
        node = _node_by_name(rt, target_name)
        if node is None:
            results.append(dict(row, **{"xaf_import_status": "skipped_missing_object", "message": u"目标对象不存在"}))
            continue
        xaf_path = _as_text(row.get("xaf_path", "")) or batch_path
        if not xaf_path:
            results.append(dict(row, **{"xaf_import_status": "failed", "message": u"缺少 XAF 路径"}))
            continue
        target_track_prepare = clear_matching_track_keys(
            rt,
            node,
            row.get("track_signatures", []) or [],
        )
        prepared_row = dict(row, **{"target_track_prepare": target_track_prepare})
        if not target_track_prepare.get("ok", False):
            results.append(dict(prepared_row, **{
                "xaf_import_status": "failed",
                "message": u"清理匹配目标轨道失败，未执行 XAF 导入",
            }))
            continue
        if xaf_path not in path_index:
            path_index[xaf_path] = len(groups)
            group_paths.append(xaf_path)
            groups.append({"rows": [], "nodes": []})
        bucket = groups[path_index[xaf_path]]
        bucket["rows"].append(prepared_row)
        bucket["nodes"].append(node)

    for xaf_path, bucket in zip(group_paths, groups):
        load_rows = bucket["rows"]
        load_nodes = bucket["nodes"]
        if not os.path.exists(xaf_path):
            for row in load_rows:
                results.append(dict(row, **{"xaf_import_status": "failed", "message": u"XAF 文件不存在: {0}".format(xaf_path)}))
            continue
        ok, msg = _try_load_xaf_nodes(rt, load_nodes, xaf_path)
        _append_xaf_import_results(results, load_rows, load_nodes, ok, msg, constrained_names, rt)
    return results


def _relink_bip_ik_rows(rows):
    # Keep this explicit for now: no object creation and no guessed Biped IK API writes.
    out = []
    for row in rows or []:
        if not row.get("target_exists"):
            out.append(dict(row, **{"relink_status": "skipped_missing_object"}))
        else:
            out.append(dict(row, **{"relink_status": "recorded_only", "message": u"IK 对象已记录；未执行不确定的 API 重链"}))
    return out


def _read_mxs_ok_message(raw):
    try:
        ok = bool(raw[0])
        msg = _as_text(raw[1])
        return ok, msg
    except Exception:
        pass
    try:
        ok = bool(raw[1])
        msg = _as_text(raw[2])
        return ok, msg
    except Exception:
        return False, _as_text(raw)


def _load_max_file_safe(rt, file_path):
    abs_path = os.path.abspath(_as_text(file_path))
    if (not abs_path) or (not os.path.exists(abs_path)):
        return False, u"文件不存在: {0}".format(abs_path), u""

    def _try_load(path_to_load):
        path_lit = _mxs_string_literal(path_to_load)
        script = u'''(
            local p = "{0}"
            local ok = false
            local msg = ""
            try (
                loadMaxFile p quiet:true useFileUnits:true missingExtFiles:#autoSearch resetMaxFile:true
                ok = true
            ) catch (msg = getCurrentException())
            if not ok do (
                try (
                    loadMaxFile p quiet:true useFileUnits:true missingExtFiles:#autoSearch
                    ok = true
                    msg = ""
                ) catch (msg = getCurrentException())
            )
            #(ok, msg as string)
        )'''.format(path_lit)
        with SilentFileDialogs(rt):
            raw = rt.execute(script)
        return _read_mxs_ok_message(raw)

    ok, msg = _try_load(abs_path)
    if ok:
        return True, u"", abs_path

    try:
        with SilentFileDialogs(rt):
            rt.loadMaxFile(abs_path, quiet=True, useFileUnits=True)
        return True, u"", abs_path
    except Exception as e:
        pymxs_msg = _as_text(e)

    if abs_path.startswith(u"\\\\"):
        try:
            temp_dir = os.path.join(tempfile.gettempdir(), "op_rig_update_load")
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            temp_path = os.path.join(temp_dir, os.path.basename(abs_path))
            shutil.copy2(abs_path, temp_path)
            ok, msg = _try_load(temp_path)
            if ok:
                return True, u"已通过本地临时副本载入: {0}".format(temp_path), temp_path
        except Exception as e:
            pymxs_msg = u"{0}; 临时副本载入失败: {1}".format(pymxs_msg, _as_text(e))

    detail = msg or pymxs_msg or u"Unknown MAXScript exception raised."
    return False, detail, abs_path


def _empty_phase4_report():
    return {
        "enabled": True,
        "status": "skipped",
        "summary": {},
        "items": [],
        "errors": [],
        "warnings": [],
    }


def _empty_phase5_report():
    return {
        "enabled": True,
        "status": "skipped",
        "summary": {},
        "items": [],
        "channel_key_warnings": [],
        "controller_sync_items": [],
        "controller_sync_warnings": [],
        "hard_errors": [],
        "warnings": [],
    }


def _record_non_bip_step_error(errors, step, exc):
    errors.append({
        "step": _as_text(step),
        "message": _as_text(exc),
        "ok": False,
    })


def _run_optional_import_step(step, ignore_non_bip_errors, fn, default=None, errors=None):
    try:
        return fn(), None
    except Exception as e:
        if ignore_non_bip_errors:
            if errors is not None:
                _record_non_bip_step_error(errors, step, e)
            return default, e
        raise


def _validate_non_bip_tracks(rt, xaf_results):
    validation_items = []
    hard_errors = []
    pending = []
    for row in xaf_results or []:
        status = _as_text(row.get("xaf_import_status", ""))
        source_name = _as_text(row.get("source_name", ""))
        target_name = _as_text(row.get("target_name", source_name))
        if status in ("ignored_obsolete_tracks", "ignored_preflight_blocker"):
            validation_items.append({
                "source_name": source_name,
                "target_name": target_name,
                "status": status,
                "ok": True,
            })
            continue
        if status == "skipped_missing_constraint_target":
            validation_items.append({"source_name": source_name, "target_name": target_name, "status": "skipped_by_explicit_constraint_policy", "ok": True})
            continue
        node = _node_by_name(rt, target_name)
        if node is None and status == "deferred_merge_source_object":
            node = _node_by_name(rt, source_name)
            target_name = source_name
        if node is None:
            item = {"source_name": source_name, "target_name": target_name, "status": "failed_missing_target_node", "ok": False}
        else:
            target_tracks = collect_node_track_signatures(rt, node, include_samples=False, include_unkeyed=False, include_controllers=True)
            pending.append((row, source_name, target_name, status, target_tracks))
            continue
        validation_items.append(item)
        if not item.get("ok", False):
            hard_errors.append(item)

    sampling = sample_track_signature_groups(rt, [entry[4] for entry in pending])
    for row, source_name, target_name, status, target_tracks in pending:
        result = validate_track_signatures(row.get("track_signatures", []) or [], target_tracks)
        item = dict(result, **{"source_name": source_name, "target_name": target_name, "xaf_import_status": status})
        if status == "deferred_merge_source_object" and result.get("ok"):
            item["status"] = "passed_after_source_merge"
        validation_items.append(item)
        if not item.get("ok", False):
            hard_errors.append(item)
    return validation_items, hard_errors, sampling


def _build_phase5_report(non_bip_data, xaf_results, morph_result=None, validation_items=None, validation_errors=None):
    morph_result = morph_result or {"ok": True, "items": [], "failed_count": 0, "baked_count": 0}
    validation_items = validation_items or []
    validation_errors = validation_errors or []
    channel_warning_items = [x for x in xaf_results if x.get("channel_key_mismatches")]
    controller_sync_items = [x for x in xaf_results if (x.get("controller_sync", {}) or {}).get("status") == "synced"]
    controller_sync_warnings = [x for x in xaf_results if (x.get("controller_sync", {}) or {}).get("status") == "warning"]
    validation_warning_items = [x for x in validation_items if x.get("warnings")]
    ignored_preflight_items = [x for x in xaf_results if x.get("xaf_import_status") == "ignored_preflight_blocker"]
    xaf_hard_errors = [x for x in xaf_results if x.get("xaf_import_status") in ("failed", "skipped_export_failed", "skipped_missing_object")]
    morph_hard_errors = [x for x in (morph_result.get("items", []) or []) if not x.get("ok", False)]
    hard_errors = xaf_hard_errors + morph_hard_errors + validation_errors
    warnings = ignored_preflight_items + channel_warning_items + controller_sync_warnings + validation_warning_items
    return {
        "enabled": True,
        "status": "passed" if not hard_errors else "failed",
        "summary": {
            "candidate_count": len(non_bip_data.get("objects", []) or []),
            "xaf_export_failed": len([x for x in xaf_results if x.get("xaf_import_status") == "skipped_export_failed"]),
            "xaf_import_succeeded": len([x for x in xaf_results if x.get("xaf_import_status") == "succeeded"]),
            "xaf_import_failed": len([x for x in xaf_results if x.get("xaf_import_status") == "failed"]),
            "skipped_missing_object": len([x for x in xaf_results if x.get("xaf_import_status") == "skipped_missing_object"]),
            "skipped_missing_constraint_target": len([
                x for x in xaf_results if x.get("xaf_import_status") == "skipped_missing_constraint_target"
            ]),
            "ignored_obsolete_tracks": len([
                x for x in xaf_results if x.get("xaf_import_status") == "ignored_obsolete_tracks"
            ]),
            "morph_bake_only": len([
                x for x in xaf_results if x.get("xaf_import_status") == "morph_bake_only"
            ]),
            "ignored_preflight_blockers": len(ignored_preflight_items),
            "channel_key_warning_count": len(channel_warning_items),
            "controller_synced_count": len(controller_sync_items),
            "controller_sync_warning_count": len(controller_sync_warnings),
            "target_track_controllers_cleared": sum([
                int((x.get("target_track_prepare", {}) or {}).get("cleared_controller_count", 0))
                for x in xaf_results
            ]),
            "target_track_prepare_unresolved": sum([
                len((x.get("target_track_prepare", {}) or {}).get("unresolved_paths", []) or [])
                for x in xaf_results
            ]),
            "target_track_prepare_failed": len([
                x for x in xaf_results
                if (x.get("target_track_prepare", {}) or {}).get("failed_paths")
            ]),
            "track_validation_failed": len(validation_errors),
            "track_validation_warning_objects": len(validation_warning_items),
            "semantic_equivalent_track_count": sum([
                int(x.get("semantic_equivalent_track_count", 0)) for x in validation_items
            ]),
            "morph_baked_count": int(morph_result.get("baked_count", 0)),
            "morph_failed_count": int(morph_result.get("failed_count", 0)),
            "hard_error_count": len(hard_errors),
            "bake_used": bool(morph_result.get("baked_count", 0)),
        },
        "items": xaf_results,
        "track_validation_items": validation_items,
        "morph_transfer": morph_result,
        "hard_errors": hard_errors,
        "warnings": warnings,
        "channel_key_warnings": channel_warning_items,
        "controller_sync_items": controller_sync_items,
        "controller_sync_warnings": controller_sync_warnings,
        "track_validation_warnings": validation_warning_items,
    }


def apply_package_to_new_rig(
    package_manifest,
    overwrite=False,
    ignore_non_bip_errors=False,
    skip_missing_constraint_targets=False,
):
    import pymxs

    rt = pymxs.runtime
    import_started = time.time()
    timings = {}
    manifest = package_manifest or {}
    allow_preflight_blockers = bool((manifest.get("options", {}) or {}).get("allow_preflight_blockers", False))
    paths = manifest.get("paths", {}) or {}
    input_data = manifest.get("input", {}) or {}
    new_rig_path = os.path.abspath(_as_text(input_data.get("new_rig_path", "")))
    output_max_path = os.path.abspath(_as_text(input_data.get("output_max_path", "")))
    if not new_rig_path or not os.path.exists(new_rig_path):
        return {"ok": False, "error_code": "PKG-IMPORT-INPUT", "message": u"新版绑定文件无效"}
    if output_max_path and os.path.exists(output_max_path) and not overwrite:
        return {"ok": False, "error_code": "PKG-IMPORT-OUTPUT", "message": u"输出文件已存在，未覆盖: {0}".format(output_max_path)}

    non_bip_step_errors = []
    load_ok = False
    load_msg = u""
    loaded_path = new_rig_path
    # Use the robust loader for all rig updates, not only BIP-only mode.
    # Some freshly-authored/legacy Max files fail through pymxs.loadMaxFile but
    # open after a reset/scripted load or from a local temp copy.
    stage_started = time.time()
    load_ok, load_msg, loaded_path = _load_max_file_safe(rt, new_rig_path)
    timings["load_target_rig"] = round(time.time() - stage_started, 3)
    if not load_ok:
        return {
            "ok": False,
            "error_code": "PKG-IMPORT-LOAD",
            "message": u"载入新绑定失败: {0}".format(load_msg),
            "ignore_non_bip_errors": bool(ignore_non_bip_errors),
            "skip_missing_constraint_targets": bool(skip_missing_constraint_targets),
            "load_attempt": {
                "new_rig_path": new_rig_path,
                "error": load_msg,
            },
        }

    stage_started = time.time()
    target_rig_key_cleanup, _ = _run_optional_import_step(
        "target_rig_key_cleanup",
        ignore_non_bip_errors,
        lambda: _clear_target_rig_animation_keys(rt),
        default={"ok": False, "status": "skipped", "message": u"非 BIP 步骤失败，已跳过"},
        errors=non_bip_step_errors,
    )

    range_result, _ = _run_optional_import_step(
        "animation_range",
        ignore_non_bip_errors,
        lambda: _set_animation_range(rt, manifest.get("animation_range", {})),
        default={},
        errors=non_bip_step_errors,
    )
    timings["prepare_target_rig"] = round(time.time() - stage_started, 3)

    stage_started = time.time()
    try:
        bip_result = _import_bip(rt, (manifest.get("bip", {}) or {}).get("path", ""))
    except Exception as e:
        bip_result = {"ok": False, "status": "failed", "message": _as_text(e)}
    timings["import_bip"] = round(time.time() - stage_started, 3)

    if not bip_result.get("ok"):
        import_report = {
            "ok": False,
            "error_code": "PKG-IMPORT-BIP",
            "message": bip_result.get("message", u"BIP 导入失败"),
            "ignore_non_bip_errors": bool(ignore_non_bip_errors),
            "skip_missing_constraint_targets": bool(skip_missing_constraint_targets),
            "non_bip_step_errors": non_bip_step_errors,
            "output_max_path": output_max_path,
            "animation_range": range_result,
            "target_rig_key_cleanup": target_rig_key_cleanup,
            "bip_import": bip_result,
            "timings_seconds": timings,
        }
        package_dir = manifest.get("package_dir") or paths.get("package_dir")
        if package_dir:
            import_report["report_json"] = _json_write(os.path.join(package_dir, "import_report.json"), import_report)
        return import_report

    stage_started = time.time()
    com_result, _ = _run_optional_import_step(
        "bip_com_height",
        ignore_non_bip_errors,
        lambda: _apply_bip_com_height(rt, _json_read(paths.get("com_height_json"), {})),
        default={"ok": True, "status": "skipped", "message": u"非 BIP 步骤失败，已跳过"},
        errors=non_bip_step_errors,
    )
    timings["apply_bip_com_height"] = round(time.time() - stage_started, 3)

    constraint_apply = {"ok": True, "items": [], "message": u""}
    phase4_report = _empty_phase4_report()
    ready_constraints = []
    skip_xaf_owner_names = set()

    def _run_constraints():
        constraints_data = _json_read(paths.get("constraints_json"), {"constraints": []})
        source_scene_objects = constraints_data.get("source_scene_objects", None)
        if source_scene_objects is None:
            source_scene_objects = _legacy_source_scene_objects(rt, input_data.get("old_anim_path", ""))
        all_rows = constraints_data.get("constraints", []) or []
        ready = []
        preserved_missing_target = []
        for x in all_rows:
            is_missing_target = (
                x.get("status") == "skipped_missing_target"
                or (not x.get("should_rebuild") and (x.get("missing_targets") or []))
            )
            if skip_missing_constraint_targets and is_missing_target:
                preserved = dict(x)
                preserved.update({
                    "status": "preserved_new_binding_missing_targets",
                    "ok": True,
                    "message": u"跳过约束目标重建：Target 在新绑定缺失，保留新绑定约束",
                })
                preserved_missing_target.append(preserved)
                owner_name = _as_text(x.get("owner_target_name", "") or x.get("owner_source_name", ""))
                if owner_name:
                    skip_xaf_owner_names.add(owner_name)
                continue
            if x.get("should_rebuild") or x.get("status") == "skipped_missing_target":
                ready.append(x)
        snapshot = {
            "constraints": ready,
            "desired_constraints": all_rows,
            "source_scene_objects": source_scene_objects,
            "skip_missing_constraint_targets": bool(skip_missing_constraint_targets),
        }
        if not output_max_path:
            apply_result = {"ok": False, "items": [], "message": u"缺少输出路径"}
        else:
            apply_result = rebuild_constraints_in_loaded_scene(
                rt,
                snapshot,
                skip_missing_constraint_targets=bool(skip_missing_constraint_targets),
            )
        if preserved_missing_target:
            apply_items = list(apply_result.get("items", []) or [])
            apply_items.extend(preserved_missing_target)
            apply_result = dict(apply_result)
            apply_result["items"] = apply_items
        return ready, apply_result, build_phase4_constraints_report(snapshot, apply_result)

    stage_started = time.time()
    constraint_bundle, _ = _run_optional_import_step(
        "phase4_constraints",
        ignore_non_bip_errors,
        _run_constraints,
        default=([], {"ok": False, "items": [], "message": u"非 BIP 步骤失败，已跳过"}, _empty_phase4_report()),
        errors=non_bip_step_errors,
    )
    ready_constraints, constraint_apply, phase4_report = constraint_bundle
    timings["rebuild_constraints"] = round(time.time() - stage_started, 3)

    # Owners skipped for missing-target rebuild must also stay out of XAF,
    # otherwise LoadXAF can re-apply the broken Link Constraint.
    for item in (constraint_apply.get("items", []) or []):
        status = _as_text(item.get("status", ""))
        if status in (
            "preserved_new_binding_missing_targets",
            "skipped_all_targets_missing",
        ):
            owner_name = _as_text(item.get("owner_target_name", "") or item.get("owner_source_name", ""))
            if owner_name:
                skip_xaf_owner_names.add(owner_name)

    non_bip_data = _json_read(paths.get("non_bip_animation_json"), {"objects": []})
    constrained_names = set([_as_text(x.get("owner_target_name", "")) for x in ready_constraints])
    constrained_names.update(skip_xaf_owner_names)

    def _run_xaf():
        with suspended_scene_redraw(rt):
            return _import_xaf_rows(
                rt,
                non_bip_data,
                constrained_names=constrained_names,
                skip_owner_names=skip_xaf_owner_names if skip_missing_constraint_targets else None,
                allow_preflight_blockers=allow_preflight_blockers,
            )

    stage_started = time.time()
    xaf_results, _ = _run_optional_import_step(
        "phase5_non_bip_xaf",
        ignore_non_bip_errors,
        _run_xaf,
        default=[],
        errors=non_bip_step_errors,
    )
    timings["import_non_bip_xaf"] = round(time.time() - stage_started, 3)
    stage_started = time.time()
    morph_data = _json_read(paths.get("morph_animation_json"), {"objects": []})

    def _run_morph_bake():
        with suspended_scene_redraw(rt):
            return apply_morph_payload(rt, morph_data, lambda name: _node_by_name(rt, name))

    morph_result, _ = _run_optional_import_step(
        "phase5_morph_bake",
        False,
        _run_morph_bake,
        default={"ok": False, "items": [], "failed_count": 1, "baked_count": 0},
        errors=non_bip_step_errors,
    )

    def _run_ik():
        ik_data = _json_read(paths.get("bip_ik_json"), {"objects": []})
        return _relink_bip_ik_rows(ik_data.get("objects", []))

    ik_results, _ = _run_optional_import_step(
        "bip_ik",
        ignore_non_bip_errors,
        _run_ik,
        default=[],
        errors=non_bip_step_errors,
    )

    def _run_merge_helpers():
        merge_helpers_data = _json_read(paths.get("merge_helpers_json"), {"objects": []})
        return _merge_helper_objects(rt, input_data.get("old_anim_path", ""), merge_helpers_data)

    merge_helpers_result, _ = _run_optional_import_step(
        "merge_helpers",
        ignore_non_bip_errors,
        _run_merge_helpers,
        default={"ok": True, "summary": {"merged_count": 0, "failed_count": 0}, "items": []},
        errors=non_bip_step_errors,
    )
    timings["morph_ik_and_merge_helpers"] = round(time.time() - stage_started, 3)

    stage_started = time.time()
    validation_items, validation_errors, validation_sampling = _validate_non_bip_tracks(rt, xaf_results)
    timings["validate_non_bip_tracks"] = round(time.time() - stage_started, 3)
    phase5_report = _build_phase5_report(
        non_bip_data,
        xaf_results,
        morph_result=morph_result,
        validation_items=validation_items,
        validation_errors=validation_errors,
    )

    stage_started = time.time()
    _, _ = _run_optional_import_step(
        "animation_range_finalize",
        ignore_non_bip_errors,
        lambda: _set_animation_range(rt, manifest.get("animation_range", {})),
        default={},
        errors=non_bip_step_errors,
    )
    timings["finalize_animation_range"] = round(time.time() - stage_started, 3)

    hard_gate_ok = bool(constraint_apply.get("ok", True)) and phase5_report.get("status") == "passed" and not non_bip_step_errors
    save_error = None
    save_skipped_reason = u""
    if not hard_gate_ok:
        save_skipped_reason = u"约束、非 BIP 动画或完整轨道校验未通过；为防止动画损坏，未保存输出文件"
    elif output_max_path:
        stage_started = time.time()
        try:
            rt.saveMaxFile(output_max_path, quiet=True)
        except Exception as e:
            save_error = e
            if not ignore_non_bip_errors:
                raise
        timings["save_output_max"] = round(time.time() - stage_started, 3)

    import_ok = bool(bip_result.get("ok")) and hard_gate_ok and (save_error is None or not output_max_path)

    message = u""
    if save_skipped_reason:
        message = save_skipped_reason
    elif save_error is not None:
        message = u"保存输出文件失败: {0}".format(_as_text(save_error))
    elif ignore_non_bip_errors and non_bip_step_errors:
        message = u"BIP 已导入；{0} 个非 BIP 步骤失败已忽略".format(len(non_bip_step_errors))
    elif ignore_non_bip_errors:
        message = u"BIP 已导入（仅 BIP 模式）"

    timings["total_import"] = round(time.time() - import_started, 3)
    import_report = {
        "ok": import_ok,
        "error_code": None if import_ok else "PKG-IMPORT-001",
        "message": message,
        "ignore_non_bip_errors": bool(ignore_non_bip_errors),
        "allow_preflight_blockers": allow_preflight_blockers,
        "skip_missing_constraint_targets": bool(skip_missing_constraint_targets),
        "loaded_scene_path": loaded_path,
        "load_message": load_msg,
        "timings_seconds": timings,
        "validation_sampling": validation_sampling,
        "non_bip_step_errors": non_bip_step_errors,
        "output_max_path": output_max_path,
        "animation_range": range_result,
        "target_rig_key_cleanup": target_rig_key_cleanup,
        "bip_import": bip_result,
        "bip_com_height": com_result,
        "phase4_constraints": phase4_report,
        "phase5_non_bip_animation": phase5_report,
        "bip_ik": {
            "enabled": True,
            "summary": {
                "recorded_count": len(ik_results),
                "recorded_only": len([x for x in ik_results if x.get("relink_status") == "recorded_only"]),
                "skipped_missing_object": len([x for x in ik_results if x.get("relink_status") == "skipped_missing_object"]),
            },
            "items": ik_results,
        },
        "merge_helpers": merge_helpers_result,
        "save_output": {
            "ok": bool(hard_gate_ok and save_error is None),
            "status": "saved" if hard_gate_ok and save_error is None else ("blocked_by_validation" if not hard_gate_ok else "failed"),
            "message": save_skipped_reason if save_skipped_reason else (u"" if save_error is None else _as_text(save_error)),
        },
    }
    package_dir = manifest.get("package_dir") or paths.get("package_dir")
    if package_dir:
        import_report["report_json"] = _json_write(os.path.join(package_dir, "import_report.json"), import_report)
    return import_report

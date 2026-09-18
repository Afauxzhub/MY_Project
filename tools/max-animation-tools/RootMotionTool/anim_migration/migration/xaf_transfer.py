# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import shutil
import tempfile

from anim_migration.migration.local_object_transfer import apply_local_transfer_plan
from anim_migration.validate.local_transform_validator import validate_local_object_transforms

try:
    _text_type = unicode
except NameError:
    _text_type = str


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


def _mxs_escape(value):
    text = _as_text(value)
    text = text.replace('"', '\\"')
    return text


def _ascii_temp_xaf_path():
    fd, path = tempfile.mkstemp(prefix="OP_XAF_", suffix=".xaf")
    try:
        os.close(fd)
    except Exception:
        pass
    try:
        os.remove(path)
    except Exception:
        pass
    return path


def native_transform_list_key_times(rt, node):
    """Return sparse key times stored in transform List slots.

    Normal tracks are inventoried by ``collect_node_track_signatures``.  Max
    2020 does not expose every Position/Rotation/Scale List slot reliably through
    the pymxs subAnim walk, so use the same focused MAXScript access pattern that
    successfully identified the production Example facial controls.  ``None``
    means the scan failed; an empty list means the scan succeeded and found no
    List-slot keys.  Frame 0 is intentionally retained.
    """
    _select_nodes(rt, [node])
    code = (
        '(\n'
        'local n = if selection.count == 1 then selection[1] else undefined\n'
        'local foundTimes = #()\n'
        'fn addTime value =\n'
        '(\n'
        '  local t = try (value as integer) catch (undefined)\n'
        '  if t != undefined and (findItem foundTimes t) == 0 do append foundTimes t\n'
        ')\n'
        'fn collectControllerKeys ctrl =\n'
        '(\n'
        '  if ctrl == undefined then return false\n'
        '  local keyCount = try (numKeys ctrl) catch (0)\n'
        '  for keyIndex = 1 to keyCount do\n'
        '  (\n'
        '    local keyTime = try ((getKey ctrl keyIndex).time) catch (undefined)\n'
        '    if keyTime != undefined do addTime keyTime\n'
        '  )\n'
        '  true\n'
        ')\n'
        'if n != undefined do\n'
        '(\n'
        '  for prop in #(#position, #rotation, #scale) do\n'
        '  (\n'
        '    local listCtrl = case prop of\n'
        '    (\n'
        '      #position: (try (n.position.controller) catch (undefined))\n'
        '      #rotation: (try (n.rotation.controller) catch (undefined))\n'
        '      #scale: (try (n.scale.controller) catch (undefined))\n'
        '    )\n'
        '    local isList = listCtrl != undefined and ((classof listCtrl == Position_List) or (classof listCtrl == Rotation_List) or (classof listCtrl == Scale_List))\n'
        '    if isList do\n'
        '    (\n'
        '      for slotIndex = 1 to listCtrl.count do\n'
        '      (\n'
        '        collectControllerKeys (try (listCtrl[slotIndex].controller) catch (undefined))\n'
        '        collectControllerKeys (try (listCtrl.weight[slotIndex].controller) catch (undefined))\n'
        '      )\n'
        '    )\n'
        '  )\n'
        ')\n'
        'sort foundTimes\n'
        'local answer = ""\n'
        'for t in foundTimes do answer += (if answer == "" then (t as string) else (";" + (t as string)))\n'
        'answer\n'
        ')'
    )
    try:
        value = _as_text(rt.execute(code))
    except Exception:
        return None
    out = []
    for item in value.split(u";"):
        try:
            out.append(int(item))
        except Exception:
            pass
    return sorted(set(out))


def _run_xaf_script(rt, node, path, mode):
    xaf_path = _mxs_escape(path)
    try:
        rt.select(node)
    except Exception:
        pass
    if mode == "save":
        code = (
            '(\n'
            'local n = if selection.count > 0 then selection[1] else undefined\n'
            'if n == undefined then false else\n'
            '(\n'
            '  local nodes = #(n)\n'
            '  local attrs = #()\n'
            '  local vals = #()\n'
            '  try (LoadSaveAnimation.saveAnimation @"{0}" &nodes &attrs &vals animatedTracks:true includeConstraints:false keyableTracks:false saveSegment:false) catch (getCurrentException())\n'
            ')'
            '\n)'
        ).format(xaf_path)
    else:
        code = (
            '(\n'
            'local n = if selection.count > 0 then selection[1] else undefined\n'
            'if n == undefined then false else\n'
            '(\n'
            '  local nodes = #(n)\n'
            '  try (LoadSaveAnimation.loadAnimation @"{0}" &nodes relative:false insert:false insertTime:0f stripLayers:false useMapFile:false) catch (getCurrentException())\n'
            ')'
            '\n)'
        ).format(xaf_path)
    try:
        res = rt.execute(code)
        if isinstance(res, bool):
            return res, u"" if res else u"LoadSaveAnimation 返回 false"
        text = _as_text(res)
        return False, text or u"LoadSaveAnimation 返回非布尔值"
    except Exception as e:
        return False, _as_text(e)


def _run_xaf_selection_script(rt, path, mode, map_path=None):
    xaf_path = _mxs_escape(path)
    if mode == "save":
        code = (
            '(\n'
            'local nodes = selection as array\n'
            'if nodes.count == 0 then false else\n'
            '(\n'
            '  local attrs = #()\n'
            '  local vals = #()\n'
            '  try (LoadSaveAnimation.saveAnimation @"{0}" &nodes &attrs &vals animatedTracks:true includeConstraints:false keyableTracks:false saveSegment:false) catch (getCurrentException())\n'
            ')'
            '\n)'
        ).format(xaf_path)
    elif map_path:
        map_value = _mxs_escape(map_path)
        code = (
            '(\n'
            'local nodes = selection as array\n'
            'if nodes.count == 0 then false else\n'
            '(\n'
            '  local attrs = #()\n'
            '  local vals = #()\n'
            '  local retarget = #()\n'
            '  local mapOK = try (LoadSaveAnimation.createMapFile @"{1}" &nodes @"{0}" &attrs &vals &retarget nodeMapType:#matchExactNodeName matchControllerExactName:true matchControllerType:false stripLayers:false) catch (false)\n'
            '  if not mapOK then false else\n'
            '    try (LoadSaveAnimation.loadAnimation @"{0}" &nodes relative:false insert:false insertTime:0f stripLayers:false useMapFile:true mapFileName:@"{1}") catch (getCurrentException())\n'
            ')'
            '\n)'
        ).format(xaf_path, map_value)
    else:
        code = (
            '(\n'
            'local nodes = selection as array\n'
            'if nodes.count == 0 then false else\n'
            '(\n'
            '  try (LoadSaveAnimation.loadAnimation @"{0}" &nodes relative:false insert:false insertTime:0f stripLayers:false useMapFile:false) catch (getCurrentException())\n'
            ')'
            '\n)'
        ).format(xaf_path)
    try:
        res = rt.execute(code)
        if isinstance(res, bool):
            return res, u"" if res else u"LoadSaveAnimation 返回 false"
        text = _as_text(res)
        return False, text or u"LoadSaveAnimation 返回非布尔值"
    except Exception as e:
        return False, _as_text(e)


def _select_nodes(rt, nodes):
    try:
        rt.clearSelection()
    except Exception:
        pass
    for node in nodes or []:
        try:
            rt.selectMore(node)
        except Exception:
            try:
                rt.select(node)
            except Exception:
                pass


def _capture_selected_list_base_controllers(rt):
    """Cache slot 1 of selected transform-list controllers inside Max."""
    code = (
        '(\n'
        'global OP_XAF_UI_LIST_BASE_CACHE\n'
        'OP_XAF_UI_LIST_BASE_CACHE = #()\n'
        'local props = #(#position, #rotation, #scale)\n'
        'try\n'
        '(\n'
        '  for n in selection do\n'
        '  (\n'
        '    for p in props do\n'
        '    (\n'
        '      local c = case p of\n'
        '      (\n'
        '        #position: (try (n.position.controller) catch (undefined))\n'
        '        #rotation: (try (n.rotation.controller) catch (undefined))\n'
        '        #scale: (try (n.scale.controller) catch (undefined))\n'
        '      )\n'
        '      if c != undefined and ((classof c == Position_List) or (classof c == Rotation_List) or (classof c == Scale_List)) and c.count >= 1 do\n'
        '      (\n'
        '        local baseController = try (copy c[1].controller) catch (undefined)\n'
        '        local activeIndex = try (c.getActive()) catch (1)\n'
        '        if baseController != undefined do append OP_XAF_UI_LIST_BASE_CACHE #(n, p, baseController, activeIndex)\n'
        '      )\n'
        '    )\n'
        '  )\n'
        '  OP_XAF_UI_LIST_BASE_CACHE.count\n'
        ')\n'
        'catch (-1)\n'
        ')'
    )
    try:
        return int(rt.execute(code))
    except Exception:
        return -1


def _restore_selected_list_base_controllers(rt):
    """Restore cached slot-1 controllers and return the failure count."""
    code = (
        '(\n'
        'global OP_XAF_UI_LIST_BASE_CACHE\n'
        'local failed = 0\n'
        'if OP_XAF_UI_LIST_BASE_CACHE != undefined do\n'
        '(\n'
        '  for item in OP_XAF_UI_LIST_BASE_CACHE do\n'
        '  (\n'
        '    local restored = false\n'
        '    try\n'
        '    (\n'
        '      local n = item[1]\n'
        '      local p = item[2]\n'
        '      local baseController = item[3]\n'
        '      local activeIndex = item[4]\n'
        '      if isValidNode n do\n'
        '      (\n'
        '        local c = case p of\n'
        '        (\n'
        '          #position: (try (n.position.controller) catch (undefined))\n'
        '          #rotation: (try (n.rotation.controller) catch (undefined))\n'
        '          #scale: (try (n.scale.controller) catch (undefined))\n'
        '        )\n'
        '        if c != undefined and ((classof c == Position_List) or (classof c == Rotation_List) or (classof c == Scale_List)) and c.count >= 1 do\n'
        '        (\n'
        '          try (c.setActive 1) catch ()\n'
        '          c[1].controller = baseController\n'
        '          try (c.setActive activeIndex) catch ()\n'
        '          restored = true\n'
        '        )\n'
        '      )\n'
        '    )\n'
        '    catch (restored = false)\n'
        '    if not restored do failed += 1\n'
        '  )\n'
        ')\n'
        'OP_XAF_UI_LIST_BASE_CACHE = #()\n'
        'failed\n'
        ')'
    )
    try:
        return int(rt.execute(code))
    except Exception:
        return -1


def _try_save_xaf_nodes(rt, nodes, path):
    temp_path = _ascii_temp_xaf_path()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    _select_nodes(rt, nodes)
    ok, msg = _run_xaf_selection_script(rt, temp_path, "save")
    try:
        if ok and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            folder = os.path.dirname(path)
            if folder and not os.path.exists(folder):
                os.makedirs(folder)
            shutil.copyfile(temp_path, path)
            return True, u""
        return False, msg or u"LoadSaveAnimation.saveAnimation 批量保存失败"
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def _try_load_xaf_nodes(rt, nodes, path, preserve_list_base=False, use_exact_map=False):
    temp_path = _ascii_temp_xaf_path()
    map_path = _ascii_temp_xaf_path()[:-4] + ".xmm" if use_exact_map else None
    try:
        shutil.copyfile(path, temp_path)
    except Exception as e:
        return False, _as_text(e)
    try:
        _select_nodes(rt, nodes)
        if preserve_list_base and _capture_selected_list_base_controllers(rt) < 0:
            return False, u"保存目标 UI List 控制器基准层失败"
        ok, message = _run_xaf_selection_script(rt, temp_path, "load", map_path=map_path)
        restore_failed = 0
        if preserve_list_base:
            restore_failed = _restore_selected_list_base_controllers(rt)
        if restore_failed != 0:
            return False, u"恢复目标 UI List 控制器基准层失败（{0} 项）".format(restore_failed)
        return ok, message
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def _animated_later_list_properties(rt, node):
    """Return transform-list properties whose slot 2+ contains keyed data."""
    try:
        rt.select(node)
    except Exception:
        return []
    code = (
        '(\n'
        'local n = if selection.count > 0 then selection[1] else undefined\n'
        'local answer = ""\n'
        'if n != undefined do\n'
        '(\n'
        '  for item in #(#("position", #position), #("rotation", #rotation), #("scale", #scale)) do\n'
        '  (\n'
        '    local p = item[2]\n'
        '    local c = case p of\n'
        '    (\n'
        '      #position: (try (n.position.controller) catch (undefined))\n'
        '      #rotation: (try (n.rotation.controller) catch (undefined))\n'
        '      #scale: (try (n.scale.controller) catch (undefined))\n'
        '    )\n'
        '    if c != undefined and ((classof c == Position_List) or (classof c == Rotation_List) or (classof c == Scale_List)) and c.count >= 2 do\n'
        '    (\n'
        '      local keyed = false\n'
        '      for i = 2 to c.count while not keyed do\n'
        '      (\n'
        '        keyed = (try (numKeys c[i].controller) catch (0)) > 0\n'
        '        if not keyed do keyed = (try (numKeys c.weight[i].controller) catch (0)) > 0\n'
        '      )\n'
        '      if keyed do answer += (if answer == "" then item[1] else (";" + item[1]))\n'
        '    )\n'
        '  )\n'
        ')\n'
        'answer\n'
        ')'
    )
    try:
        value = _as_text(rt.execute(code))
    except Exception:
        return []
    return [item for item in value.split(u";") if item]


def _create_ui_list_helper(rt, node, prop_name, helper_name):
    if _node_by_name(rt, helper_name) is not None:
        return None
    _select_nodes(rt, [node])
    prop_name = _as_text(prop_name)
    helper_name = _mxs_escape(helper_name)
    code = (
        '(\n'
        'local n = if selection.count > 0 then selection[1] else undefined\n'
        'if n == undefined then undefined else\n'
        '(\n'
        '  local h = point name:"{0}" size:1\n'
        '  try\n'
        '  (\n'
        '    case "{1}" of\n'
        '    (\n'
        '      "position": (h.position.controller = copy n.position.controller)\n'
        '      "rotation": (h.rotation.controller = copy n.rotation.controller)\n'
        '      "scale": (h.scale.controller = copy n.scale.controller)\n'
        '    )\n'
        '    h\n'
        '  )\n'
        '  catch (delete h; undefined)\n'
        ')\n'
        ')'
    ).format(helper_name, _mxs_escape(prop_name))
    try:
        return rt.execute(code)
    except Exception:
        return None


def export_ui_list_slot_package(rt, rows, path):
    """Store keyed UI list slots 2+ in native Max helper controllers."""
    entries = []
    helpers = []
    temp_path = _ascii_temp_xaf_path()[:-4] + ".max"
    try:
        for row in rows or []:
            node = row.get("_node")
            if node is None:
                continue
            for prop_name in _animated_later_list_properties(rt, node):
                helper_name = "OP_RIGUPDATE_UI_LIST_{0:04d}".format(len(entries) + 1)
                helper = _create_ui_list_helper(rt, node, prop_name, helper_name)
                if helper is None:
                    return {"ok": False, "message": u"创建 UI List 原生中转对象失败", "path": path, "entries": entries}
                helpers.append(helper)
                entries.append({
                    "helper_name": helper_name,
                    "property": prop_name,
                    "contract_layer": u"UI",
                    "source_contract_id": row.get("source_contract_id", ""),
                    "target_contract_id": row.get("target_contract_id", ""),
                    "source_name": row.get("source_name", ""),
                    "target_name": row.get("target_name", ""),
                })
        if not entries:
            return {"ok": True, "message": u"", "path": u"", "entries": []}
        _select_nodes(rt, helpers)
        save_code = (
            '(try (saveNodes selection @"{0}" quiet:true; true) catch (false))'
        ).format(_mxs_escape(temp_path))
        if not bool(rt.execute(save_code)) or not os.path.exists(temp_path):
            return {"ok": False, "message": u"UI List 原生中转包保存失败", "path": path, "entries": entries}
        folder = os.path.dirname(path)
        if folder and not os.path.exists(folder):
            os.makedirs(folder)
        shutil.copyfile(temp_path, path)
        return {"ok": True, "message": u"", "path": path, "entries": entries}
    except Exception as error:
        return {"ok": False, "message": _as_text(error), "path": path, "entries": entries}
    finally:
        for helper in helpers:
            try:
                if rt.isValidNode(helper):
                    rt.delete(helper)
            except Exception:
                pass
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        try:
            if map_path and os.path.exists(map_path):
                os.remove(map_path)
        except Exception:
            pass


def _copy_ui_list_later_slots(rt, target_node, helper_node, prop_name):
    _select_nodes(rt, [target_node, helper_node])
    code = (
        '(\n'
        'if selection.count != 2 then "selection_error" else\n'
        '(\n'
        '  local targetNode = selection[1]\n'
        '  local helperNode = selection[2]\n'
        '  local targetCtrl = undefined\n'
        '  local sourceCtrl = undefined\n'
        '  case "{0}" of\n'
        '  (\n'
        '    "position": (targetCtrl = targetNode.position.controller; sourceCtrl = helperNode.position.controller)\n'
        '    "rotation": (targetCtrl = targetNode.rotation.controller; sourceCtrl = helperNode.rotation.controller)\n'
        '    "scale": (targetCtrl = targetNode.scale.controller; sourceCtrl = helperNode.scale.controller)\n'
        '  )\n'
        '  if targetCtrl == undefined or sourceCtrl == undefined then "controller_missing" else if classof targetCtrl != classof sourceCtrl then "list_class_mismatch" else if targetCtrl.count != sourceCtrl.count then "slot_count_mismatch" else\n'
        '  (\n'
        '    local compatible = true\n'
        '    for i = 2 to sourceCtrl.count while compatible do\n'
        '      if classof targetCtrl[i].controller != classof sourceCtrl[i].controller do compatible = false\n'
        '    if not compatible then "slot_class_mismatch" else\n'
        '    (\n'
        '      for i = 2 to sourceCtrl.count do\n'
        '      (\n'
        '        deleteKeys targetCtrl[i].controller #allKeys\n'
        '        copyKeys sourceCtrl[i].controller targetCtrl[i].controller\n'
        '        local sourceWeight = try (sourceCtrl.weight[i].controller) catch (undefined)\n'
        '        local targetWeight = try (targetCtrl.weight[i].controller) catch (undefined)\n'
        '        if sourceWeight != undefined and targetWeight != undefined and classof sourceWeight == classof targetWeight do\n'
        '        (\n'
        '          deleteKeys targetWeight #allKeys\n'
        '          copyKeys sourceWeight targetWeight\n'
        '        )\n'
        '      )\n'
        '      "ok"\n'
        '    )\n'
        '  )\n'
        ')\n'
        ')'
    ).format(_mxs_escape(prop_name))
    try:
        message = _as_text(rt.execute(code))
    except Exception as error:
        message = _as_text(error)
    return message == u"ok", message


def apply_ui_list_slot_package(rt, assignments, path):
    """Merge native helpers and copy slots 2+ onto resolved target controls."""
    results = []
    helpers = []
    if not assignments:
        return {"ok": True, "items": results, "message": u""}
    if not path or not os.path.exists(path):
        return {"ok": False, "items": results, "message": u"UI List 原生中转包不存在"}
    for item in assignments:
        if _node_by_name(rt, item.get("helper_name", "")) is not None:
            return {"ok": False, "items": results, "message": u"场景中存在保留的 UI List 中转对象名"}
    temp_path = _ascii_temp_xaf_path()[:-4] + ".max"
    try:
        shutil.copyfile(path, temp_path)
        merge_code = (
            '(try (mergeMAXFile @"{0}" #select #autoRenameDups quiet:true) catch (false))'
        ).format(_mxs_escape(temp_path))
        merge_ok = bool(rt.execute(merge_code))
        for item in assignments:
            helper = _node_by_name(rt, item.get("helper_name", ""))
            if helper is not None:
                helpers.append(helper)
        if not merge_ok and len(helpers) != len(assignments):
            return {"ok": False, "items": results, "message": u"UI List 原生中转包合并失败"}
        for item in assignments:
            helper = _node_by_name(rt, item.get("helper_name", ""))
            target = item.get("_target_node")
            public_item = dict([(key, value) for key, value in item.items() if key != "_target_node"])
            if helper is None or target is None:
                results.append({"ok": False, "entry": public_item, "message": u"中转对象或目标控制器不存在"})
                continue
            ok, message = _copy_ui_list_later_slots(rt, target, helper, item.get("property", ""))
            results.append({"ok": ok, "entry": public_item, "message": message})
        return {"ok": all([item.get("ok", False) for item in results]), "items": results, "message": u""}
    except Exception as error:
        return {"ok": False, "items": results, "message": _as_text(error)}
    finally:
        for helper in helpers:
            try:
                if rt.isValidNode(helper):
                    rt.delete(helper)
            except Exception:
                pass
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def _leaf_key_tracks(rows):
    """Return deepest keyed controller rows so container controllers stay target-owned."""
    keyed = [row for row in (rows or []) if row.get("key_times")]
    paths = set([_as_text(row.get("path", "")) for row in keyed])
    out = []
    for row in keyed:
        path = _as_text(row.get("path", ""))
        prefix = path + u"/"
        if any([other.startswith(prefix) for other in paths if other != path]):
            continue
        out.append(row)
    return out


def _key_helper_property(rt, controller):
    """Choose a Point property that can safely host a copied leaf controller."""
    class_name = _as_text(rt.classOf(controller)).lower()
    if any([token in class_name for token in ("wire", "reaction", "script", "constraint", "list")]):
        return ""
    try:
        value = controller.value
    except Exception:
        value = None
    if "rotation" in class_name or "quaternion" in class_name:
        return "rotation"
    if "scale" in class_name:
        return "scale"
    components = []
    for attr in ("x", "y", "z", "w"):
        try:
            components.append(float(getattr(value, attr)))
        except Exception:
            break
    if len(components) == 4:
        return "rotation"
    if len(components) == 3:
        return "position"
    try:
        float(value)
        return "visibility"
    except Exception:
        return ""


def _assign_helper_controller(rt, helper, prop_name, controller):
    """Attach a controller through Max's animatable-property API and verify it stuck.

    Assigning ``helper.position.controller`` through pymxs can succeed as a
    Python attribute write without replacing the node's actual sub-anim.  The
    resulting helper then saves with its default controller and imports as a
    missing source handle.  ``setPropertyController`` is the native Max API for
    all four properties used by the key package, so use it consistently and
    require a readable controller before accepting the helper.
    """
    try:
        copied = rt.copy(controller)
    except Exception:
        copied = None
    if copied is None:
        return False
    property_name = {
        "visibility": "visibility",
        "position": "position",
        "rotation": "rotation",
        "scale": "scale",
    }.get(prop_name)
    if not property_name:
        return False
    for value in (copied, controller):
        try:
            try:
                rt.setPropertyController(helper, rt.Name(property_name), value)
            except Exception:
                rt.setPropertyController(helper, property_name, value)
            if _helper_controller(rt, helper, prop_name) is not None:
                return True
        except Exception:
            pass
    return False


def _helper_controller(rt, helper, prop_name):
    property_name = {
        "visibility": "visibility",
        "position": "position",
        "rotation": "rotation",
        "scale": "scale",
    }.get(prop_name)
    if not property_name:
        return None
    try:
        try:
            controller = rt.getPropertyController(helper, rt.Name(property_name))
        except Exception:
            controller = rt.getPropertyController(helper, property_name)
        if controller is not None:
            return controller
    except Exception:
        pass
    # Max 2020 occasionally exposes an animatable node property through direct
    # MAXScript syntax even when pymxs getPropertyController returns None.
    try:
        rt.select(helper)
        return rt.execute(
            '(if selection.count == 1 then try(selection[1].{0}.controller) '
            'catch(undefined) else undefined)'.format(property_name)
        )
    except Exception:
        return None


def export_key_only_package(rt, rows, path):
    """Save keyed leaf controllers without saving/replacing any rig controller tree."""
    from anim_migration.migration.track_transfer import collect_node_track_signatures, json_track_signatures

    entries = []
    skipped = []
    helpers = []
    temp_path = _ascii_temp_xaf_path()[:-4] + ".max"
    try:
        for row in rows or []:
            node = row.get("_node")
            if node is None:
                continue
            expected_paths = set([
                _as_text(item.get("path", ""))
                for item in (row.get("track_signatures", []) or [])
                if item.get("root_kind") != "modifier"
            ])
            tracks = collect_node_track_signatures(
                rt, node, include_samples=False,
                include_unkeyed=False, include_controllers=True,
            )
            tracks = _leaf_key_tracks([
                item for item in tracks
                if item.get("root_kind") != "modifier" and
                _as_text(item.get("path", "")) in expected_paths
            ])
            for track in tracks:
                controller = track.get("_controller")
                prop_name = _key_helper_property(rt, controller)
                helper_name = "OP_RIGUPDATE_KEY_{0:05d}".format(len(entries) + 1)
                try:
                    helper = rt.execute('point name:"{0}" size:1'.format(_mxs_escape(helper_name)))
                except Exception:
                    helper = None
                if helper is None or not prop_name or not _assign_helper_controller(rt, helper, prop_name, controller):
                    if helper is not None:
                        try:
                            rt.delete(helper)
                        except Exception:
                            pass
                    skipped.append({
                        "source_name": row.get("source_name", ""),
                        "target_name": row.get("target_name", ""),
                        "contract_layer": row.get("contract_layer", ""),
                        "path": track.get("path", ""),
                        "reason": "key_helper_controller_unsupported",
                    })
                    continue
                helpers.append(helper)
                public_track = json_track_signatures([track])[0]
                entries.append({
                    "helper_name": helper_name,
                    "helper_property": prop_name,
                    "contract_layer": row.get("contract_layer", ""),
                    "source_contract_id": row.get("source_contract_id", ""),
                    "target_contract_id": row.get("target_contract_id", ""),
                    "source_name": row.get("source_name", ""),
                    "target_name": row.get("target_name", ""),
                    "track": public_track,
                })
        if not entries:
            return {"ok": True, "message": u"", "path": u"", "entries": [], "skipped": skipped}
        _select_nodes(rt, helpers)
        save_code = (
            '(try (saveNodes selection @"{0}" quiet:true; true) catch (false))'
        ).format(_mxs_escape(temp_path))
        if not bool(rt.execute(save_code)) or not os.path.exists(temp_path):
            return {"ok": False, "message": u"关键帧原生中转包保存失败", "path": path, "entries": entries, "skipped": skipped}
        folder = os.path.dirname(path)
        if folder and not os.path.exists(folder):
            os.makedirs(folder)
        shutil.copyfile(temp_path, path)
        return {"ok": True, "message": u"", "path": path, "entries": entries, "skipped": skipped}
    except Exception as error:
        return {"ok": False, "message": _as_text(error), "path": path, "entries": entries, "skipped": skipped}
    finally:
        for helper in helpers:
            try:
                if rt.isValidNode(helper):
                    rt.delete(helper)
            except Exception:
                pass
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def _copy_controller_keys_preserving_target(rt, source_controller, target_controller, expected_times):
    """Copy keys transactionally; never assign a replacement target controller."""
    from anim_migration.migration.track_transfer import _clear_controller_keys, _direct_key_times

    try:
        backup = rt.copy(target_controller)
    except Exception:
        backup = None
    try:
        if not _clear_controller_keys(rt, target_controller):
            raise RuntimeError(u"清理目标轨道关键帧失败")
        rt.copyKeys(source_controller, target_controller)
        actual_times = _direct_key_times(rt, target_controller)
        if sorted(set([int(value) for value in (expected_times or [])])) != actual_times:
            raise RuntimeError(u"copyKeys 后关键帧时间不一致")
        return True, u"", actual_times
    except Exception as error:
        if backup is not None:
            try:
                _clear_controller_keys(rt, target_controller)
                rt.copyKeys(backup, target_controller)
            except Exception:
                pass
        return False, _as_text(error), []


def apply_key_only_package(rt, assignments, path):
    """Copy native keys into existing target leaf controllers and preserve rig wiring."""
    from anim_migration.migration.track_transfer import collect_node_track_signatures

    results = []
    helpers = []
    if not assignments:
        return {"ok": True, "items": results, "message": u""}
    if not path or not os.path.exists(path):
        return {"ok": False, "items": results, "message": u"关键帧原生中转包不存在"}
    temp_path = _ascii_temp_xaf_path()[:-4] + ".max"
    try:
        shutil.copyfile(path, temp_path)
        merge_code = (
            '(try (mergeMAXFile @"{0}" #select #autoRenameDups quiet:true) catch (false))'
        ).format(_mxs_escape(temp_path))
        merge_ok = bool(rt.execute(merge_code))
        for item in assignments:
            helper = _node_by_name(rt, item.get("helper_name", ""))
            if helper is not None:
                helpers.append(helper)
        if not merge_ok and len(helpers) != len(assignments):
            return {"ok": False, "items": results, "message": u"关键帧原生中转包合并失败"}

        target_cache = {}
        for item in assignments:
            public_item = dict([(key, value) for key, value in item.items() if key != "_target_node"])
            helper = _node_by_name(rt, item.get("helper_name", ""))
            target = item.get("_target_node")
            track = item.get("track", {}) or {}
            path_value = _as_text(track.get("path", ""))
            if helper is None or target is None:
                results.append({"ok": False, "entry": public_item, "message": u"中转对象或目标控制器不存在"})
                continue
            cache_key = id(target)
            if cache_key not in target_cache:
                target_tracks = collect_node_track_signatures(
                    rt, target, include_samples=False,
                    include_unkeyed=True, include_controllers=True,
                )
                by_path = {}
                for target_track in target_tracks:
                    if target_track.get("root_kind") == "modifier":
                        continue
                    by_path.setdefault(_as_text(target_track.get("path", "")), []).append(target_track)
                target_cache[cache_key] = by_path
            matches = target_cache[cache_key].get(path_value, [])
            if len(matches) != 1:
                results.append({"ok": False, "entry": public_item, "message": u"目标叶子轨道不存在或不唯一"})
                continue
            target_controller = matches[0].get("_controller")
            source_controller = _helper_controller(rt, helper, item.get("helper_property", ""))
            source_class = _as_text(track.get("controller_class", ""))
            target_class = _as_text(matches[0].get("controller_class", ""))
            if source_controller is None or target_controller is None:
                results.append({
                    "ok": False, "entry": public_item,
                    "message": u"源或目标叶子控制器句柄不存在",
                    "source_controller_missing": bool(source_controller is None),
                    "target_controller_missing": bool(target_controller is None),
                    "source_controller_class": source_class,
                    "target_controller_class": target_class,
                })
                continue
            source_domain = _as_text(item.get("helper_property", ""))
            target_domain = _key_helper_property(rt, target_controller)
            if not source_domain or source_domain != target_domain:
                results.append({
                    "ok": False, "entry": public_item,
                    "message": u"源/目标叶子控制器值域不兼容",
                    "source_controller_class": source_class,
                    "target_controller_class": target_class,
                    "source_value_domain": source_domain,
                    "target_value_domain": target_domain,
                })
                continue
            target_identity = id(target_controller)
            ok, message, actual_times = _copy_controller_keys_preserving_target(
                rt, source_controller, target_controller, track.get("key_times", []) or [],
            )
            if ok and id(matches[0].get("_controller")) != target_identity:
                ok = False
                message = u"目标控制器实例发生变化"
            results.append({
                "ok": ok,
                "entry": public_item,
                "message": message,
                "actual_key_times": actual_times,
                "target_controller_preserved": bool(ok),
                "source_controller_class": source_class,
                "target_controller_class": target_class,
                "controller_class_conversion": bool(source_class.lower() != target_class.lower()),
            })
        return {"ok": all([item.get("ok", False) for item in results]), "items": results, "message": u""}
    except Exception as error:
        return {"ok": False, "items": results, "message": _as_text(error)}
    finally:
        for helper in helpers:
            try:
                if rt.isValidNode(helper):
                    rt.delete(helper)
            except Exception:
                pass
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


def _try_save_xaf(rt, node, path):
    temp_path = _ascii_temp_xaf_path()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    try:
        rt.select(node)
    except Exception:
        pass
    attempts = (
        lambda: _run_xaf_script(rt, node, temp_path, "save"),
    )
    last_error = u""
    for fn in attempts:
        try:
            res = fn()
            if isinstance(res, tuple):
                ok, msg = res
                if not ok:
                    last_error = msg
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                folder = os.path.dirname(path)
                if folder and not os.path.exists(folder):
                    os.makedirs(folder)
                shutil.copyfile(temp_path, path)
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
                return True, u""
        except Exception as e:
            last_error = _as_text(e)
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception:
        pass
    return False, last_error or u"LoadSaveAnimation.saveAnimation 不可用"


def _try_load_xaf(rt, node, path):
    temp_path = _ascii_temp_xaf_path()
    try:
        shutil.copyfile(path, temp_path)
    except Exception as e:
        return False, _as_text(e)
    try:
        rt.select(node)
    except Exception:
        pass
    attempts = (
        lambda: _run_xaf_script(rt, node, temp_path, "load"),
    )
    last_error = u""
    for fn in attempts:
        try:
            res = fn()
            if isinstance(res, tuple):
                ok, msg = res
                if ok:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                    return True, u""
                last_error = msg
            else:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass
                return True, u""
        except Exception as e:
            last_error = _as_text(e)
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception:
        pass
    return False, last_error or u"loadAnimation 不可用"


def _attempt_xaf_items(source_scene_path, target_scene_path, items):
    import pymxs

    rt = pymxs.runtime
    source_scene_path = os.path.abspath(_as_text(source_scene_path))
    target_scene_path = os.path.abspath(_as_text(target_scene_path))
    results = []
    restore = _as_text(rt.maxFilePath) + _as_text(rt.maxFileName)
    restore = restore if restore and os.path.exists(restore) else None

    candidates = [x for x in items if x.get("has_animation")]
    if not candidates:
        return {"ok": True, "results": results, "fallback_items": []}

    try:
        xaf_cache = {}
        rt.loadMaxFile(source_scene_path, quiet=True, useFileUnits=True)
        for item in candidates:
            source_name = _as_text(item.get("source_name", ""))
            node = _node_by_name(rt, source_name)
            if node is None:
                results.append({"source_name": source_name, "target_name": item.get("target_name"), "method": "xaf", "status": "failed", "message": u"源对象不存在"})
                continue
            fd, xaf_path = tempfile.mkstemp(prefix="OP_AnimMigration_", suffix=".xaf")
            try:
                os.close(fd)
            except Exception:
                pass
            ok, msg = _try_save_xaf(rt, node, xaf_path)
            if ok:
                xaf_cache[source_name] = xaf_path
            else:
                results.append({"source_name": source_name, "target_name": item.get("target_name"), "method": "xaf", "status": "failed", "message": msg})

        rt.loadMaxFile(target_scene_path, quiet=True, useFileUnits=True)
        for item in candidates:
            source_name = _as_text(item.get("source_name", ""))
            target_name = _as_text(item.get("target_name", source_name))
            xaf_path = xaf_cache.get(source_name)
            if not xaf_path:
                continue
            node = _node_by_name(rt, target_name)
            if node is None:
                results.append({"source_name": source_name, "target_name": target_name, "method": "xaf", "status": "failed", "message": u"目标对象不存在"})
                continue
            ok, msg = _try_load_xaf(rt, node, xaf_path)
            results.append({"source_name": source_name, "target_name": target_name, "method": "xaf", "status": "succeeded" if ok else "failed", "message": msg})

        rt.saveMaxFile(target_scene_path, quiet=True)
        succeeded_sources = set([_as_text(x.get("source_name", "")) for x in results if x.get("method") == "xaf" and x.get("status") == "succeeded"])
        fallback_items = [x for x in candidates if _as_text(x.get("source_name", "")) not in succeeded_sources]
        return {"ok": True, "results": results, "fallback_items": fallback_items}
    except Exception as e:
        return {"ok": False, "results": results, "fallback_items": candidates, "message": _as_text(e)}
    finally:
        try:
            for path in list(locals().get("xaf_cache", {}).values()):
                if path and os.path.exists(path):
                    os.remove(path)
        except Exception:
            pass
        try:
            if restore and os.path.abspath(restore) != target_scene_path:
                rt.loadMaxFile(restore, quiet=True, useFileUnits=True)
        except Exception:
            pass


def transfer_non_bip_animation(plan, validate_threshold=None, validation_mode="warn", excluded_source_names=None, use_xaf=False):
    plan = dict(plan or {})
    excluded_source_names = set([_as_text(x) for x in (excluded_source_names or []) if _as_text(x)])
    skipped_constrained = [x for x in plan.get("items", []) if _as_text(x.get("source_name", "")) in excluded_source_names]
    items = [x for x in plan.get("items", []) if x.get("has_animation") and _as_text(x.get("source_name", "")) not in excluded_source_names]
    run_plan = dict(plan)
    run_plan["items"] = items
    if use_xaf:
        xaf_result = _attempt_xaf_items(run_plan.get("source_scene_path", ""), run_plan.get("target_scene_path", ""), items)
    else:
        xaf_result = {"ok": True, "results": [], "fallback_items": items, "message": u"XAF 默认安全关闭，当前使用 TRS fallback"}

    fallback_items = xaf_result.get("fallback_items", []) or []
    fallback_plan = dict(run_plan)
    fallback_plan["items"] = fallback_items
    fallback_result = {"ok": True, "results": [], "pre_data": {}, "post_data": {}}
    if fallback_items:
        fallback_result = apply_local_transfer_plan(fallback_plan, animation_range=None)

    post_data_renamed = {}
    for item in fallback_items:
        src = _as_text(item.get("source_name", ""))
        dst = _as_text(item.get("target_name", src))
        if dst in fallback_result.get("post_data", {}):
            post_data_renamed[src] = fallback_result["post_data"][dst]
    validation = validate_local_object_transforms(fallback_result.get("pre_data", {}), post_data_renamed, validate_threshold or {})

    return build_phase5_non_bip_report(run_plan, xaf_result, fallback_result, validation, validation_mode, skipped_constrained, use_xaf)


def build_phase5_non_bip_report(plan, xaf_result, fallback_result, validation, validation_mode, skipped_constrained=None, use_xaf=False):
    plan = plan or {}
    xaf_rows = xaf_result.get("results", []) if isinstance(xaf_result, dict) else []
    fallback_rows = fallback_result.get("results", []) if isinstance(fallback_result, dict) else []
    validation = validation or {}
    exceeded = validation.get("exceeded_items", []) or []
    return {
        "enabled": True,
        "status": "blocked" if exceeded and validation_mode == "block" else ("warning" if exceeded else "passed"),
        "summary": {
            "candidate_count": len([x for x in plan.get("items", []) if x.get("has_animation")]),
            "xaf_enabled": bool(use_xaf),
            "xaf_attempted": len(xaf_rows),
            "xaf_succeeded": len([x for x in xaf_rows if x.get("status") == "succeeded"]),
            "xaf_failed": len([x for x in xaf_rows if x.get("status") == "failed"]),
            "trs_fallback_attempted": len([x for x in fallback_rows if x.get("error_code") != "P3-MISSING-OBJECT"]),
            "trs_fallback_succeeded": len([x for x in fallback_rows if x.get("ok", False)]),
            "skipped_missing_object": len([x for x in (plan.get("skipped", []) or []) if x.get("reason") == "skipped_missing_object"]),
            "skipped_constrained_owner": len(skipped_constrained or []),
            "validation_exceeded": len(exceeded),
        },
        "message": _as_text(xaf_result.get("message", "")) if isinstance(xaf_result, dict) else u"",
        "xaf_results": xaf_rows,
        "trs_fallback_results": fallback_rows,
        "validation": validation,
        "skipped_constrained_owner": skipped_constrained or [],
        "errors": [x for x in xaf_rows if x.get("status") == "failed"] + [x for x in fallback_rows if not x.get("ok", False)],
        "warnings": exceeded,
    }

# -*- coding: utf-8 -*-
"""Transform controller shape inspection, List slot alignment, and key clearing.

Max's native Load Animation resolves nodes by exact node name, but it resolves
the controllers inside a node by exact controller name.  Rig List slots very
often keep Max's default localized slot name, so several slots of one control
share a single name.  An incoming slot track is then written into every
identically named target slot: the rig base slot gains keys it never had and the
animator's own slot is overwritten by the base slot data.  A slot rename in the
new binding has the opposite effect and makes the whole load a silent no-op.

These helpers inspect both sides, align the mapped slots by index for the load
window only, restore the original slot names afterwards, and clear target keys
on the channels the animation file owns.
"""
from __future__ import print_function


try:
    _text_type = unicode
except NameError:
    _text_type = str


CHANNELS = (u"position", u"rotation", u"scale")
SLOT_NAME_PREFIX = u"OP_XSLOT_"
MAX_SLOT_DEPTH = 4

# Slot names come from rig authors, so the payload separators must not appear in
# them. MAXScript strips these tokens from every emitted name.
_SLOT_SEP = u"@@"
_SUB_SEP = u"##"

STATUS_NATIVE = "native"
STATUS_PARTIAL = "partial_channels_not_transportable"
STATUS_NOTHING = "no_transportable_animation"


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def clean_name(value):
    """Match the name normalization the MAXScript payload applies."""
    text = _as_text(value)
    for token in (_SLOT_SEP, _SUB_SEP, u"\t", u"\n"):
        text = text.replace(token, u"_" if token in (_SLOT_SEP, _SUB_SEP) else u" ")
    return text


def _key_count(row):
    """Key counts are never negative; Max answers -1 for keyless controllers."""
    try:
        return max(0, int((row or {}).get("key_count", 0) or 0))
    except Exception:
        return 0


def shape_key_count(shape):
    return sum([
        int(((shape or {}).get(channel, {}) or {}).get("key_count", 0) or 0)
        for channel in CHANNELS
    ])


def _select_nodes(rt, nodes):
    try:
        rt.clearSelection()
    except Exception:
        pass
    count = 0
    for node in nodes or []:
        if node is None:
            continue
        try:
            rt.selectMore(node)
            count += 1
        except Exception:
            try:
                rt.select(node)
                count += 1
            except Exception:
                pass
    return count


def _channel_case_block(indent):
    """Return the MAXScript case expression that reads one channel controller."""
    return (
        indent + u'local c = case prop of\n' +
        indent + u'(\n' +
        indent + u'  #position: (try (n.position.controller) catch (undefined))\n' +
        indent + u'  #rotation: (try (n.rotation.controller) catch (undefined))\n' +
        indent + u'  #scale: (try (n.scale.controller) catch (undefined))\n' +
        indent + u')\n'
    )


_IS_LIST_FN = (
    u'fn opIsTransformList c =\n'
    u'(\n'
    u'  local answer = false\n'
    u'  try (answer = (classof c == Position_List) or (classof c == Rotation_List) or (classof c == Scale_List)) catch (answer = false)\n'
    u'  answer\n'
    u')\n'
)

_KEY_COUNT_FN = (
    u'fn opKeyCount c =\n'
    u'(\n'
    u'  local total = 0\n'
    u'  if c != undefined do total = try (numKeys c) catch 0\n'
    u'  -- Controllers without a key interface, such as script, wire and\n'
    u'  -- constraint controllers, answer -1 here. That is "no keys", not a\n'
    u'  -- negative expectation the verification could subtract later.\n'
    u'  if total < 0 do total = 0\n'
    u'  total\n'
    u')\n'
)

# A subanim without a controller of its own is a parameter block, not a track:
# the Limit controller keeps its limit values there. Those values belong to the
# rig, so neither side counts them and no load is expected to deliver them.
_KEY_TOTAL_FN = _KEY_COUNT_FN + (
    u'fn opKeyTotal a depth =\n'
    u'(\n'
    u'  local total = 0\n'
    u'  if a != undefined and depth <= {0} do\n'
    u'  (\n'
    u'    local subs = 0\n'
    u'    try (subs = a.numSubs) catch (subs = 0)\n'
    u'    for i = 1 to subs do\n'
    u'    (\n'
    u'      local sa = try (getSubAnim a i) catch (undefined)\n'
    u'      if sa != undefined do\n'
    u'      (\n'
    u'        local c = try (sa.controller) catch (undefined)\n'
    u'        if c != undefined do\n'
    u'        (\n'
    u'          total += opKeyCount c\n'
    u'          total += opKeyTotal sa (depth + 1)\n'
    u'        )\n'
    u'      )\n'
    u'    )\n'
    u'  )\n'
    u'  total\n'
    u')\n'
).format(MAX_SLOT_DEPTH)


def _shape_script():
    return (
        u'(\n' +
        _IS_LIST_FN +
        _KEY_TOTAL_FN +
        u'fn opCleanName value =\n'
        u'(\n'
        u'  local text = value as string\n'
        u'  text = substituteString text "' + _SLOT_SEP + u'" "_"\n'
        u'  text = substituteString text "' + _SUB_SEP + u'" "_"\n'
        u'  text = substituteString text "\\t" " "\n'
        u'  text = substituteString text "\\n" " "\n'
        u'  text\n'
        u')\n'
        u'fn opChannelInfo c =\n'
        u'(\n'
        u'  if c == undefined then "none' + _SUB_SEP + u'0' + _SUB_SEP + u'0' + _SUB_SEP + u'0' + _SUB_SEP + u'" else\n'
        u'  (\n'
        u'    local isList = opIsTransformList c\n'
        u'    local slotCount = if isList then c.count else 0\n'
        u'    local activeSlot = if isList then (try (c.getActive()) catch 0) else 0\n'
        u'    local channelKeys = (opKeyCount c) + (opKeyTotal c 1)\n'
        u'    local text = ((classof c) as string) + "' + _SUB_SEP + u'" + (slotCount as string) + "' + _SUB_SEP + u'"\n'
        u'    text += (activeSlot as string) + "' + _SUB_SEP + u'" + (channelKeys as string) + "' + _SUB_SEP + u'"\n'
        u'    if isList do\n'
        u'    (\n'
        u'      for i = 1 to c.count do\n'
        u'      (\n'
        u'        if i > 1 do text += "' + _SLOT_SEP + u'"\n'
        u'        local slot = try (c[i].controller) catch (undefined)\n'
        u'        local slotKeys = 0\n'
        u'        if slot != undefined do slotKeys = (opKeyCount slot) + (opKeyTotal slot 1)\n'
        u'        local weightKeys = try (opKeyCount (c.weight[i].controller)) catch 0\n'
        u'        text += (opCleanName (try (c.getName i) catch "?")) + "' + _SUB_SEP + u'"\n'
        u'        text += (if slot == undefined then "none" else ((classof slot) as string)) + "' + _SUB_SEP + u'"\n'
        u'        text += (slotKeys as string) + "' + _SUB_SEP + u'" + (weightKeys as string)\n'
        u'      )\n'
        u'    )\n'
        u'    text\n'
        u'  )\n'
        u')\n'
        u'local out = ""\n'
        u'for n in selection do\n'
        u'(\n'
        u'  out += "N\\t" + (opCleanName n.name) + "\\t"\n'
        u'  out += (opChannelInfo (try (n.position.controller) catch (undefined))) + "\\t"\n'
        u'  out += (opChannelInfo (try (n.rotation.controller) catch (undefined))) + "\\t"\n'
        u'  out += (opChannelInfo (try (n.scale.controller) catch (undefined))) + "\\n"\n'
        u')\n'
        u'out\n'
        u')'
    )


def _parse_channel(text):
    # The slot tail reuses the field separator, so the head must be split with a
    # fixed field count and the remainder kept whole.
    parts = _as_text(text).split(_SUB_SEP, 4)
    channel = {
        "class": parts[0] if parts else u"none",
        "is_list": False,
        "slot_count": 0,
        "active_slot": 0,
        "key_count": 0,
        "slots": [],
    }
    for index, key in enumerate(("slot_count", "active_slot", "key_count"), start=1):
        try:
            channel[key] = int(parts[index])
        except Exception:
            channel[key] = 0
    channel["is_list"] = channel["slot_count"] > 0 or channel["class"].lower().endswith(u"_list")
    tail = parts[4] if len(parts) > 4 else u""
    if not channel["is_list"] or not tail:
        return channel
    for slot_text in tail.split(_SLOT_SEP):
        fields = slot_text.split(_SUB_SEP)
        slot = {
            "name": fields[0] if fields else u"",
            "class": fields[1] if len(fields) > 1 else u"",
            "key_count": 0,
            "weight_key_count": 0,
        }
        for index, key in enumerate(("key_count", "weight_key_count"), start=2):
            try:
                slot[key] = int(fields[index])
            except Exception:
                slot[key] = 0
        channel["slots"].append(slot)
    return channel


def collect_transform_shapes(rt, nodes):
    """Return {node_name: {channel: shape}} for the given nodes in one Max call.

    Node names inside one contract layer are unique by the time this runs, so a
    name-keyed result is stable. The whole inventory is a single ``rt.execute``
    call because a per-object probe dominates runtime on production rigs.
    """
    shapes = {}
    if not _select_nodes(rt, nodes):
        return shapes
    try:
        payload = _as_text(rt.execute(_shape_script()))
    except Exception:
        return shapes
    for line in payload.split(u"\n"):
        if not line.startswith(u"N\t"):
            continue
        fields = line.split(u"\t")
        if len(fields) < 5:
            continue
        shapes[fields[1]] = {
            u"position": _parse_channel(fields[2]),
            u"rotation": _parse_channel(fields[3]),
            u"scale": _parse_channel(fields[4]),
        }
    return shapes


def empty_shape():
    return dict([
        (channel, {
            "class": u"unknown",
            "is_list": False,
            "slot_count": 0,
            "active_slot": 0,
            "key_count": 0,
            "slots": [],
        })
        for channel in CHANNELS
    ])


def _slot_names(channel):
    return [_as_text(slot.get("name", u"")) for slot in (channel or {}).get("slots", []) or []]


def _is_known_class(class_name):
    """A shape lookup that failed must never be treated as a plain controller."""
    return _as_text(class_name).lower() not in (u"", u"unknown", u"none")


def has_duplicate_slot_names(shape):
    for channel in CHANNELS:
        names = _slot_names((shape or {}).get(channel, {}))
        if len(names) != len(set(names)):
            return True
    return False


def plan_transport(source_shape, target_shape):
    """Decide how one control can travel through native Save/Load Animation.

    The plan is per channel: how many leading List slots can be aligned by
    index, whether the slot names must be normalized for the load, and which
    keyed source slots or channels cannot arrive at all.
    """
    source_shape = source_shape or empty_shape()
    target_shape = target_shape or empty_shape()
    channels = {}
    runs = {}
    issues = []
    transportable_keys = 0
    blocked_keys = 0
    needs_normalization = False
    for channel in CHANNELS:
        source = source_shape.get(channel, {}) or {}
        target = target_shape.get(channel, {}) or {}
        source_names = _slot_names(source)
        target_names = _slot_names(target)
        source_keys = int(source.get("key_count", 0) or 0)
        row = {
            "source_class": _as_text(source.get("class", u"")),
            "target_class": _as_text(target.get("class", u"")),
            "source_slot_count": int(source.get("slot_count", 0) or 0),
            "target_slot_count": int(target.get("slot_count", 0) or 0),
            "source_key_count": source_keys,
            "mapped_slot_run": 0,
            "needs_normalization": False,
            "duplicate_source_slot_names": len(source_names) != len(set(source_names)),
            "duplicate_target_slot_names": len(target_names) != len(set(target_names)),
            "blocked": False,
            "blocked_reason": u"",
            "blocked_key_count": 0,
            "class_mismatch": False,
        }
        source_is_list = bool(source.get("is_list"))
        target_is_list = bool(target.get("is_list"))
        row["target_is_list"] = target_is_list
        if source_is_list and target_is_list:
            run = min(row["source_slot_count"], row["target_slot_count"])
            row["mapped_slot_run"] = run
            row["needs_normalization"] = bool(
                row["duplicate_source_slot_names"] or
                row["duplicate_target_slot_names"] or
                source_names[:run] != target_names[:run]
            )
            outside = [
                {"slot_index": index + 1, "name": source_names[index], "key_count": source["slots"][index].get("key_count", 0)}
                for index in range(run, row["source_slot_count"])
                if source["slots"][index].get("key_count", 0)
            ]
            if outside:
                row["blocked"] = True
                row["blocked_reason"] = "source_keyed_slot_beyond_target_slot_count"
                row["blocked_key_count"] = sum([item["key_count"] for item in outside])
                row["blocked_slots"] = outside
        elif source_is_list != target_is_list:
            if source_keys:
                row["blocked"] = True
                row["blocked_reason"] = (
                    "source_list_target_plain_controller" if source_is_list
                    else "source_plain_controller_target_list"
                )
                row["blocked_key_count"] = source_keys
        elif (
            row["source_class"].lower() != row["target_class"].lower() and
            _is_known_class(row["source_class"]) and _is_known_class(row["target_class"])
        ):
            # Two different plain controller classes may still exchange tracks by
            # subanim name, so this is an advisory: attempt the load and let the
            # post-load verification decide.
            row["class_mismatch"] = True
        # Clearing follows what can actually arrive: the mapped List slots, or a
        # whole plain channel, and nothing at all where the load cannot deliver.
        if target_is_list:
            row["clear_scope"] = row["mapped_slot_run"]
        elif row["blocked"] or not (_is_known_class(row["source_class"]) and _is_known_class(row["target_class"])):
            row["clear_scope"] = 0
        else:
            row["clear_scope"] = -1
        needs_normalization = needs_normalization or row["needs_normalization"]
        runs[channel] = row["mapped_slot_run"]
        blocked_keys += row["blocked_key_count"]
        transportable_keys += max(0, source_keys - row["blocked_key_count"])
        if row["blocked"]:
            issues.append({
                "channel": channel,
                "reason": row["blocked_reason"],
                "source_class": row["source_class"],
                "target_class": row["target_class"],
                "source_slot_count": row["source_slot_count"],
                "target_slot_count": row["target_slot_count"],
                "key_count": row["blocked_key_count"],
            })
        channels[channel] = row
    if blocked_keys and not transportable_keys:
        status = STATUS_NOTHING
    elif blocked_keys:
        status = STATUS_PARTIAL
    else:
        status = STATUS_NATIVE
    return {
        "status": status,
        "needs_normalization": needs_normalization,
        "mapped_slot_runs": runs,
        "transportable_key_count": transportable_keys,
        "blocked_key_count": blocked_keys,
        "issues": issues,
        "channels": channels,
        "class_mismatch_channels": [
            channel for channel in CHANNELS if channels[channel]["class_mismatch"]
        ],
        "duplicate_slot_names": bool(
            has_duplicate_slot_names(source_shape) or has_duplicate_slot_names(target_shape)
        ),
    }


def run_key(plan):
    """Slot-alignment group key: only the mapped slot run matters per channel."""
    runs = (plan or {}).get("mapped_slot_runs", {}) or {}
    return tuple([int(runs.get(channel, 0) or 0) for channel in CHANNELS])


def clear_key(plan):
    """Key-clearing group key: mapped slot count, -1 for a whole plain channel."""
    channels = (plan or {}).get("channels", {}) or {}
    return tuple([
        int((channels.get(channel, {}) or {}).get("clear_scope", 0) or 0)
        for channel in CHANNELS
    ])


def group_nodes(rows, node_getter, plan_getter, key_getter):
    """Return {key: [nodes]} so every group needs exactly one Max call."""
    groups = {}
    for row in rows or []:
        node = node_getter(row)
        if node is None:
            continue
        groups.setdefault(key_getter(plan_getter(row)), []).append(node)
    return groups


def group_nodes_by_run(rows, node_getter, plan_getter):
    return group_nodes(rows, node_getter, plan_getter, run_key)


def group_nodes_by_clear_scope(rows, node_getter, plan_getter):
    return group_nodes(rows, node_getter, plan_getter, clear_key)


def _normalize_script(runs):
    return (
        u'(\n'
        u'global OP_XSLOT_NAME_CACHE\n'
        u'if OP_XSLOT_NAME_CACHE == undefined do OP_XSLOT_NAME_CACHE = #()\n' +
        _IS_LIST_FN +
        u'local renamed = 0\n'
        u'for n in selection do\n'
        u'(\n'
        u'  for item in #(#(#position, {0}, "P"), #(#rotation, {1}, "R"), #(#scale, {2}, "S")) do\n'
        u'  (\n'
        u'    local prop = item[1]\n'
        u'    local run = item[2]\n'
        u'    local tag = item[3]\n' +
        _channel_case_block(u'    ') +
        u'    if run > 0 and (opIsTransformList c) do\n'
        u'    (\n'
        u'      local last = if run < c.count then run else c.count\n'
        u'      for i = 1 to last do\n'
        u'      (\n'
        u'        local previous = try (c.getName i) catch ""\n'
        u'        append OP_XSLOT_NAME_CACHE #(n, prop, i, previous)\n'
        u'        try (c.setName i ("' + SLOT_NAME_PREFIX + u'" + tag + (i as string)); renamed += 1) catch ()\n'
        u'      )\n'
        u'    )\n'
        u'  )\n'
        u')\n'
        u'renamed\n'
        u')'
    ).format(int(runs[0]), int(runs[1]), int(runs[2]))


_RESTORE_SCRIPT = (
    u'(\n'
    u'global OP_XSLOT_NAME_CACHE\n' +
    _IS_LIST_FN +
    u'local failed = 0\n'
    u'if OP_XSLOT_NAME_CACHE != undefined do\n'
    u'(\n'
    u'  for item in OP_XSLOT_NAME_CACHE do\n'
    u'  (\n'
    u'    local restored = false\n'
    u'    try\n'
    u'    (\n'
    u'      local n = item[1]\n'
    u'      local prop = item[2]\n'
    u'      if isValidNode n do\n'
    u'      (\n' +
    _channel_case_block(u'        ') +
    u'        if (opIsTransformList c) and c.count >= item[3] do\n'
    u'        (\n'
    u'          c.setName item[3] item[4]\n'
    u'          restored = true\n'
    u'        )\n'
    u'      )\n'
    u'    )\n'
    u'    catch (restored = false)\n'
    u'    if not restored do failed += 1\n'
    u'  )\n'
    u')\n'
    u'OP_XSLOT_NAME_CACHE = #()\n'
    u'failed\n'
    u')'
)


def align_slot_names(rt, groups):
    """Rename mapped List slots to unique index names on the current scene.

    Both the source save and the target load use the same scheme, so Max's
    exact controller-name matching becomes a one-to-one slot-index mapping.
    """
    result = {"ok": True, "renamed_slot_count": 0, "group_count": 0, "failures": []}
    for runs, nodes in sorted((groups or {}).items()):
        if not any(runs) or not nodes:
            continue
        if not _select_nodes(rt, nodes):
            continue
        result["group_count"] += 1
        try:
            result["renamed_slot_count"] += int(rt.execute(_normalize_script(runs)))
        except Exception as error:
            result["ok"] = False
            result["failures"].append({"runs": list(runs), "message": _as_text(error)})
    return result


def restore_slot_names(rt):
    """Restore every slot name cached by :func:`align_slot_names`."""
    try:
        failed = int(rt.execute(_RESTORE_SCRIPT))
    except Exception as error:
        return {"ok": False, "failed_count": -1, "message": _as_text(error)}
    return {"ok": failed == 0, "failed_count": failed, "message": u"" if failed == 0 else u"{0} 个 List 槽名未能恢复".format(failed)}


def _materialize_script(scopes):
    """Build the payload that fills empty wrapped controller slots.

    A Limit controller keeps the controller it limits in its own subanim, and
    that subanim is named after the assigned controller class. A new binding
    ships the limit with nothing assigned yet, so the subanim carries Max's
    placeholder name and the animator's track has no name to match. Assigning
    the same controller class the animator used restores the name and leaves the
    evaluated value untouched.
    """
    return (
        u'(\n' +
        _IS_LIST_FN +
        u'fn opFillWrapped a depth =\n'
        u'(\n'
        u'  local created = 0\n'
        u'  if a != undefined and depth <= {3} do\n'
        u'  (\n'
        u'    local subs = 0\n'
        u'    try (subs = a.numSubs) catch (subs = 0)\n'
        u'    for i = 1 to subs do\n'
        u'    (\n'
        u'      local sa = try (getSubAnim a i) catch (undefined)\n'
        u'      if sa != undefined do\n'
        u'      (\n'
        u'        local c = try (sa.controller) catch (undefined)\n'
        u'        if c != undefined do\n'
        u'        (\n'
        u'          if (superClassOf c) == floatController do\n'
        u'          (\n'
        u'            local iface = try (getInterface c #limits) catch (undefined)\n'
        u'            if iface != undefined do\n'
        u'            (\n'
        u'              local wrapped = try (iface.GetLimitedControl()) catch (undefined)\n'
        u'              if wrapped == undefined do\n'
        u'              (\n'
        u'                local before = try (sa.value) catch (undefined)\n'
        u'                local fresh = bezier_float()\n'
        u'                local ok = false\n'
        u'                try (iface.SetLimitedControl fresh; ok = true) catch (ok = false)\n'
        u'                if ok do\n'
        u'                (\n'
        u'                  created += 1\n'
        u'                  if before != undefined do try (fresh.value = before) catch ()\n'
        u'                )\n'
        u'              )\n'
        u'            )\n'
        u'          )\n'
        u'          created += opFillWrapped sa (depth + 1)\n'
        u'        )\n'
        u'      )\n'
        u'    )\n'
        u'  )\n'
        u'  created\n'
        u')\n'
        u'local created = 0\n'
        u'for n in selection do\n'
        u'(\n'
        u'  for item in #(#(#position, {0}), #(#rotation, {1}), #(#scale, {2})) do\n'
        u'  (\n'
        u'    local prop = item[1]\n'
        u'    local run = item[2]\n' +
        _channel_case_block(u'    ') +
        u'    if c != undefined and run != 0 do\n'
        u'    (\n'
        u'      if (opIsTransformList c) then\n'
        u'      (\n'
        u'        if run > 0 do\n'
        u'        (\n'
        u'          local last = if run < c.count then run else c.count\n'
        u'          for i = 1 to last do created += opFillWrapped (c[i]) 1\n'
        u'        )\n'
        u'      )\n'
        u'      else\n'
        u'      (\n'
        u'        if run < 0 do created += opFillWrapped c 1\n'
        u'      )\n'
        u'    )\n'
        u'  )\n'
        u')\n'
        u'created\n'
        u')'
    ).format(int(scopes[0]), int(scopes[1]), int(scopes[2]), MAX_SLOT_DEPTH)


def materialize_wrapped_controllers(rt, groups):
    """Assign the missing inner controller of every reachable Limit controller.

    Without this the animator's track has no controller name to land on, so Max
    reports a successful load while the control keeps a static value: keys arrive
    on the neighbouring axes and the control never moves.
    """
    result = {"ok": True, "created_controller_count": 0, "group_count": 0, "failures": []}
    for scopes, nodes in sorted((groups or {}).items()):
        if not any(scopes) or not nodes:
            continue
        if not _select_nodes(rt, nodes):
            continue
        result["group_count"] += 1
        try:
            result["created_controller_count"] += int(rt.execute(_materialize_script(scopes)))
        except Exception as error:
            result["ok"] = False
            result["failures"].append({"clear_scopes": list(scopes), "message": _as_text(error)})
    return result


def _clear_script(scopes):
    """Build the clearing payload. Scope: 0 skip, -1 whole plain channel, n slots."""
    return (
        u'(\n' +
        _IS_LIST_FN +
        u'fn opClearTree a depth =\n'
        u'(\n'
        u'  local cleared = 0\n'
        u'  if a != undefined and depth <= {3} do\n'
        u'  (\n'
        u'    local subs = 0\n'
        u'    try (subs = a.numSubs) catch (subs = 0)\n'
        u'    for i = 1 to subs do\n'
        u'    (\n'
        u'      local sa = try (getSubAnim a i) catch (undefined)\n'
        u'      if sa != undefined do\n'
        u'      (\n'
        u'        local c = try (sa.controller) catch (undefined)\n'
        u'        if c != undefined do\n'
        u'        (\n'
        u'          if (try (numKeys c) catch 0) > 0 do\n'
        u'            try (deleteKeys c #allKeys; cleared += 1) catch ()\n'
        u'          cleared += opClearTree sa (depth + 1)\n'
        u'        )\n'
        u'      )\n'
        u'    )\n'
        u'  )\n'
        u'  cleared\n'
        u')\n'
        u'local cleared = 0\n'
        u'for n in selection do\n'
        u'(\n'
        u'  for item in #(#(#position, {0}), #(#rotation, {1}), #(#scale, {2})) do\n'
        u'  (\n'
        u'    local prop = item[1]\n'
        u'    local run = item[2]\n' +
        _channel_case_block(u'    ') +
        u'    if c != undefined and run != 0 do\n'
        u'    (\n'
        u'      if (opIsTransformList c) then\n'
        u'      (\n'
        u'        if run > 0 do\n'
        u'        (\n'
        u'          local last = if run < c.count then run else c.count\n'
        u'          for i = 1 to last do\n'
        u'          (\n'
        u'            local slot = try (c[i].controller) catch (undefined)\n'
        u'            if slot != undefined do\n'
        u'            (\n'
        u'              if (try (numKeys slot) catch 0) > 0 do try (deleteKeys slot #allKeys; cleared += 1) catch ()\n'
        u'              cleared += opClearTree slot 1\n'
        u'            )\n'
        u'          )\n'
        u'        )\n'
        u'      )\n'
        u'      else\n'
        u'      (\n'
        u'        if run < 0 do\n'
        u'        (\n'
        u'          if (try (numKeys c) catch 0) > 0 do try (deleteKeys c #allKeys; cleared += 1) catch ()\n'
        u'          cleared += opClearTree c 1\n'
        u'        )\n'
        u'      )\n'
        u'    )\n'
        u'  )\n'
        u')\n'
        u'cleared\n'
        u')'
    ).format(int(scopes[0]), int(scopes[1]), int(scopes[2]), MAX_SLOT_DEPTH)


def clear_animation_owned_keys(rt, groups):
    """Delete target keys on the channels and slots the animation file owns.

    Slots outside the mapped run stay untouched: those belong to the target
    binding. Without this step a control that carries no animation in the source
    file keeps whatever the new binding shipped, which reads as an unexplained
    fully keyed control after the update. A channel the load cannot reach is left
    alone, because clearing it would drop data nothing is going to replace.
    """
    result = {"ok": True, "cleared_track_count": 0, "group_count": 0, "failures": []}
    for scopes, nodes in sorted((groups or {}).items()):
        if not any(scopes) or not nodes:
            continue
        if not _select_nodes(rt, nodes):
            continue
        result["group_count"] += 1
        try:
            result["cleared_track_count"] += int(rt.execute(_clear_script(scopes)))
        except Exception as error:
            result["ok"] = False
            result["failures"].append({"clear_scopes": list(scopes), "message": _as_text(error)})
    return result


def compare_slot_key_counts(source_shape, target_shape, plan):
    """Compare per-slot and per-channel key counts after a load.

    Duplicate slot names make controller paths ambiguous, so the path/time based
    check cannot see a track that was written into the wrong slot of the same
    name. Slot indexes can.
    """
    source_shape = source_shape or empty_shape()
    target_shape = target_shape or empty_shape()
    runs = (plan or {}).get("mapped_slot_runs", {}) or {}
    findings = []
    for channel in CHANNELS:
        source = source_shape.get(channel, {}) or {}
        target = target_shape.get(channel, {}) or {}
        row = ((plan or {}).get("channels", {}) or {}).get(channel, {}) or {}
        run = int(runs.get(channel, 0) or 0)
        if not source.get("is_list") or not target.get("is_list"):
            expected = _key_count(source)
            actual = _key_count(target)
            blocked = int(row.get("blocked_key_count", 0) or 0)
            if actual > expected:
                findings.append({
                    "channel": channel,
                    "kind": "unexpected_channel_keys",
                    "expected_key_count": expected,
                    "actual_key_count": actual,
                })
            elif actual < expected - blocked:
                findings.append({
                    "channel": channel,
                    "kind": "missing_channel_keys",
                    "expected_key_count": expected - blocked,
                    "actual_key_count": actual,
                    # The new binding drives this channel with another controller
                    # class, so its tracks have nowhere to land. That is a rig
                    # change to report, not a load that went wrong.
                    "channel_class_changed": bool(row.get("class_mismatch")),
                })
            continue
        source_slots = source.get("slots", []) or []
        target_slots = target.get("slots", []) or []
        for index in range(max(len(source_slots), len(target_slots))):
            expected = _key_count(source_slots[index]) if index < len(source_slots) else 0
            actual = _key_count(target_slots[index]) if index < len(target_slots) else 0
            if index >= run:
                # Outside the mapped run the target binding owns the slot, so
                # only report source keys that could not travel.
                if expected:
                    findings.append({
                        "channel": channel,
                        "slot_index": index + 1,
                        "kind": "source_slot_outside_mapped_run",
                        "expected_key_count": expected,
                        "actual_key_count": actual,
                    })
                continue
            if actual == expected:
                continue
            findings.append({
                "channel": channel,
                "slot_index": index + 1,
                "kind": "unexpected_slot_keys" if actual > expected else "missing_slot_keys",
                "expected_key_count": expected,
                "actual_key_count": actual,
            })
    return findings

# -*- coding: utf-8 -*-
"""选中对象动画关键帧幅度缩放（支持 Biped / Euler / TCB / Quaternion）。"""
from __future__ import division
import math

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
        return _text_type(repr(value))


def _get_rt():
    import pymxs
    return pymxs.runtime


def _class_name(obj):
    try:
        return _as_text(_get_rt().classOf(obj))
    except Exception:
        return u""


def _class_tag(obj):
    name = _class_name(obj).lower()
    for ch in (u" ", u"_", u":"):
        name = name.replace(ch, u"")
    return name


def _is_valid_node(node):
    rt = _get_rt()
    try:
        return node is not None and rt.isValidNode(node)
    except Exception:
        return False


def get_selected_nodes():
    rt = _get_rt()
    nodes = []
    try:
        for node in rt.selection:
            if _is_valid_node(node):
                nodes.append(node)
    except Exception:
        pass
    return nodes


def get_display_object_name(nodes):
    nodes = [n for n in (nodes or []) if _is_valid_node(n)]
    if not nodes:
        return u"（未选中对象）"
    if len(nodes) == 1:
        return _as_text(nodes[0].name)
    ancestor = _outermost_common_parent(nodes)
    if ancestor is not None:
        return _as_text(ancestor.name)
    return _as_text(nodes[0].name)


def _outermost_common_parent(nodes):
    rt = _get_rt()
    chains = []
    for node in nodes:
        chain = []
        cur = node
        while cur is not None:
            try:
                chain.append(cur)
                cur = cur.parent
            except Exception:
                break
        chains.append(chain)
    if not chains:
        return None
    common = None
    shortest = min(chains, key=len)
    for candidate in reversed(shortest):
        if all(candidate in chain for chain in chains):
            common = candidate
            break
    if common is None:
        return None
    if common in nodes:
        parent = common.parent
        while parent is not None:
            try:
                if rt.isValidNode(parent):
                    common = parent
                    parent = parent.parent
                else:
                    break
            except Exception:
                break
    return common


def _is_biped_root(node):
    return _class_name(getattr(node, u"controller", None)) == u"Biped_Object"


def _is_biped_slave(node):
    return _class_name(getattr(node, u"controller", None)) == u"BipSlave_Control"


def _get_biped_root(node):
    rt = _get_rt()
    cur = node
    while cur is not None:
        try:
            if _is_biped_root(cur) and bool(cur.isRoot):
                return cur
            cur = cur.parent
        except Exception:
            break
    return None


def _time_frame(t):
    try:
        return int(t.frame)
    except Exception:
        return int(_get_rt().Float(t))


def _make_time(frame):
    return _get_rt().timeFromFrame(int(frame))


def _iter_float_keys(float_ctrl, start_f, end_f):
    rt = _get_rt()
    if float_ctrl is None:
        return
    try:
        n = int(rt.numKeys(float_ctrl))
    except Exception:
        return
    for i in range(1, n + 1):
        try:
            t = rt.getKeyTime(float_ctrl, i)
            f = _time_frame(t)
            if start_f <= f <= end_f:
                val = float(rt.getKeyValue(float_ctrl, i))
                yield i, f, val
        except Exception:
            continue


def _read_float_at_frame(float_ctrl, frame):
    rt = _get_rt()
    if float_ctrl is None:
        return None
    try:
        with pymxs_attime(frame):
            return float(float_ctrl.value)
    except Exception:
        return None


def _write_float_key(float_ctrl, key_index, new_value):
    rt = _get_rt()
    try:
        rt.setKeyValue(float_ctrl, key_index, float(new_value))
        return True
    except Exception:
        pass
    try:
        key = rt.getKey(float_ctrl, key_index)
        key.value = float(new_value)
        return True
    except Exception:
        return False


def pymxs_attime(frame):
    import pymxs
    return pymxs.attime(_make_time(frame))


def _scale_float_controller(float_ctrl, start_f, end_f, pivot_frame, use_mid_pivot, factor, enabled):
    if not enabled or float_ctrl is None:
        return 0
    keys = list(_iter_float_keys(float_ctrl, start_f, end_f))
    if not keys:
        return 0
    if use_mid_pivot:
        pivot = sum(v for _, _, v in keys) / float(len(keys))
    else:
        pivot = _read_float_at_frame(float_ctrl, pivot_frame)
        if pivot is None:
            pivot = keys[0][2]
    changed = 0
    for key_index, _, value in keys:
        new_val = pivot + (value - pivot) * factor
        if abs(new_val - value) > 1e-7 and _write_float_key(float_ctrl, key_index, new_val):
            changed += 1
    return changed


def _unwrap_controller(track):
    if track is None:
        return None
    try:
        ctrl = track.controller
        if ctrl is not None:
            return ctrl
    except Exception:
        pass
    return track


def _get_sub_controller(ctrl, names, indexes):
    for name in names:
        try:
            sub = getattr(ctrl, name)
            sub = _unwrap_controller(sub)
            if sub is not None:
                return sub
        except Exception:
            pass
        try:
            sub = ctrl[name]
            sub = _unwrap_controller(sub)
            if sub is not None:
                return sub
        except Exception:
            pass
    for idx in indexes:
        try:
            sub = ctrl[idx]
            sub = _unwrap_controller(sub)
            if sub is not None:
                return sub
        except Exception:
            pass
    return None


def _get_channel_controller(node, channel):
    """获取 position / rotation / scale 控制器（兼容 PRS / Biped）。"""
    rt = _get_rt()
    prop_map = {
        u"position": (u"position", u"pos"),
        u"rotation": (u"rotation",),
        u"scale": (u"scale", u"scaling"),
    }
    prop_names = prop_map.get(channel, (channel,))

    for prop in prop_names:
        for name_arg in (rt.Name(prop), prop):
            try:
                ctrl = rt.getPropertyController(node, name_arg)
                if ctrl is not None:
                    return ctrl
            except Exception:
                pass

    try:
        tm_ctrl = node.controller
    except Exception:
        tm_ctrl = None
    if tm_ctrl is not None:
        for prop in prop_names:
            try:
                sub_track = getattr(tm_ctrl, prop)
                ctrl = sub_track.controller
                if ctrl is not None:
                    return ctrl
            except Exception:
                pass
        index_map = {u"position": 0, u"rotation": 1, u"scale": 2}
        idx = index_map.get(channel)
        if idx is not None:
            try:
                ctrl = tm_ctrl[idx].controller
                if ctrl is not None:
                    return ctrl
            except Exception:
                pass

    attr_map = {
        u"position": (u"pos", u"position"),
        u"scale": (u"scale",),
    }
    for attr in attr_map.get(channel, ()):
        try:
            track = getattr(node, attr)
            ctrl = track.controller
            if ctrl is not None:
                return ctrl
        except Exception:
            pass
    return None


def _get_rotation_controller(node):
    return _get_channel_controller(node, u"rotation")


def _get_position_axis_ctrls(node):
    ctrl = _get_channel_controller(node, u"position")
    result = {}
    if ctrl is None:
        return result
    tag = _class_tag(ctrl)
    if u"positionxyz" in tag or u"bezierposition" in tag:
        result[u"X"] = _get_sub_controller(ctrl, (u"X_Position", u"X Position"), (1, 0))
        result[u"Y"] = _get_sub_controller(ctrl, (u"Y_Position", u"Y Position"), (2, 1))
        result[u"Z"] = _get_sub_controller(ctrl, (u"Z_Position", u"Z Position"), (3, 2))
    result = dict((k, v) for k, v in result.items() if v is not None)
    return result


def _get_scale_axis_ctrls(node):
    ctrl = _get_channel_controller(node, u"scale")
    result = {}
    if ctrl is None:
        return result
    tag = _class_tag(ctrl)
    if u"scalexyz" in tag:
        result[u"X"] = _get_sub_controller(ctrl, (u"X_Scale", u"X Scale"), (1, 0))
        result[u"Y"] = _get_sub_controller(ctrl, (u"Y_Scale", u"Y Scale"), (2, 1))
        result[u"Z"] = _get_sub_controller(ctrl, (u"Z_Scale", u"Z Scale"), (3, 2))
    result = dict((k, v) for k, v in result.items() if v is not None)
    return result


def _rotation_controller_kind(rot_ctrl):
    tag = _class_tag(rot_ctrl)
    if u"euler" in tag:
        return u"euler"
    if u"tcb" in tag:
        return u"tcb"
    if u"quat" in tag or u"quaternion" in tag:
        return u"quaternion"
    return u"unknown"


def _get_euler_axis_ctrls(rot_ctrl):
    result = {}
    for axis in (u"X", u"Y", u"Z"):
        idx0 = {u"X": 0, u"Y": 1, u"Z": 2}[axis]
        idx1 = idx0 + 1
        result[axis] = _get_sub_controller(
            rot_ctrl,
            (u"{0}_Rotation".format(axis), u"{0} Rotation".format(axis)),
            (idx1, idx0),
        )
    result = dict((k, v) for k, v in result.items() if v is not None)
    return result


def _quat_normalize(q):
    x, y, z, w = q
    mag = math.sqrt(x * x + y * y + z * z + w * w)
    if mag <= 1e-8:
        return (0.0, 0.0, 0.0, 1.0)
    return (x / mag, y / mag, z / mag, w / mag)


def _quat_multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quat_conjugate(q):
    return (-q[0], -q[1], -q[2], q[3])


def _quat_slerp(a, b, t):
    ax, ay, az, aw = _quat_normalize(a)
    bx, by, bz, bw = _quat_normalize(b)
    dot = ax * bx + ay * by + az * bz + aw * bw
    if dot < 0.0:
        bx, by, bz, bw = -bx, -by, -bz, -bw
        dot = -dot
    if dot > 0.9995:
        rx = ax + t * (bx - ax)
        ry = ay + t * (by - ay)
        rz = az + t * (bz - az)
        rw = aw + t * (bw - aw)
        return _quat_normalize((rx, ry, rz, rw))
    theta0 = math.acos(max(-1.0, min(1.0, dot)))
    sin0 = math.sin(theta0)
    theta = theta0 * t
    s0 = math.sin(theta0 - theta) / sin0
    s1 = math.sin(theta) / sin0
    return (
        s0 * ax + s1 * bx,
        s0 * ay + s1 * by,
        s0 * az + s1 * bz,
        s0 * aw + s1 * bw,
    )


def _node_rotation_quat(node, frame):
    rt = _get_rt()
    with pymxs_attime(frame):
        try:
            q = node.rotation
            return (float(q.x), float(q.y), float(q.z), float(q.w))
        except Exception:
            pass
        try:
            tm = node.transform
            q = rt.quatToEuler(tm.rotation)
            return None
        except Exception:
            return None


def _set_node_rotation_quat(node, frame, quat):
    import pymxs
    rt = _get_rt()
    q = rt.Quat(quat[0], quat[1], quat[2], quat[3])
    with pymxs_attime(frame):
        with pymxs.animate(True):
            node.rotation = q
    return True


def _iter_rotation_key_frames(rot_ctrl, start_f, end_f):
    rt = _get_rt()
    frames = set()
    try:
        n = int(rt.numKeys(rot_ctrl))
        for i in range(1, n + 1):
            f = _time_frame(rt.getKeyTime(rot_ctrl, i))
            if start_f <= f <= end_f:
                frames.add(f)
    except Exception:
        pass
    return sorted(frames)


def _scale_quaternion_rotation(node, rot_ctrl, start_f, end_f, pivot_frame, use_mid_pivot, factor):
    frames = _iter_rotation_key_frames(rot_ctrl, start_f, end_f)
    if not frames:
        return 0
    if use_mid_pivot:
        qs = [_node_rotation_quat(node, f) for f in frames]
        qs = [q for q in qs if q is not None]
        if not qs:
            return 0
        pivot = qs[0]
        for q in qs[1:]:
            pivot = _quat_slerp(pivot, q, 0.5)
    else:
        pivot = _node_rotation_quat(node, pivot_frame)
        if pivot is None:
            pivot = _node_rotation_quat(node, frames[0])
    if pivot is None:
        return 0
    identity = (0.0, 0.0, 0.0, 1.0)
    changed = 0
    for frame in frames:
        current = _node_rotation_quat(node, frame)
        if current is None:
            continue
        delta = _quat_multiply(_quat_conjugate(pivot), current)
        scaled_delta = _quat_slerp(identity, delta, factor)
        new_q = _quat_multiply(pivot, scaled_delta)
        if _set_node_rotation_quat(node, frame, new_q):
            changed += 1
    return changed


def _scale_tcb_rotation(node, rot_ctrl, start_f, end_f, pivot_frame, use_mid_pivot, factor, axes):
  # TCB 控制器优先尝试 XYZ 浮点子控制器；否则按整体四元数处理
    axis_ctrls = _get_euler_axis_ctrls(rot_ctrl)
    if len(axis_ctrls) == 3:
        changed = 0
        for axis in (u"X", u"Y", u"Z"):
            changed += _scale_float_controller(
                axis_ctrls.get(axis),
                start_f,
                end_f,
                pivot_frame,
                use_mid_pivot,
                factor,
                axis in axes,
            )
        return changed
    return _scale_quaternion_rotation(node, rot_ctrl, start_f, end_f, pivot_frame, use_mid_pivot, factor)


def _scale_biped_horizontal_com(bip_root, start_f, end_f, pivot_frame, use_mid_pivot, factor, axes):
    rt = _get_rt()
    if not (_is_biped_root(bip_root) and bip_root.isRoot):
        return 0
    try:
        horiz = rt.biped.getNode(bip_root, rt.Name("horizontal"))
    except Exception:
        horiz = None
    if horiz is None or not rt.isValidNode(horiz):
        return 0
    axis_ctrls = _get_position_axis_ctrls(horiz)
    if not axis_ctrls:
        return 0
    changed = 0
    for axis in (u"X", u"Y", u"Z"):
        changed += _scale_float_controller(
            axis_ctrls.get(axis),
            start_f,
            end_f,
            pivot_frame,
            use_mid_pivot,
            factor,
            axis in axes,
        )
    return changed


def _validate_rotation_axes(node, axes):
    rot_ctrl = _get_rotation_controller(node)
    kind = _rotation_controller_kind(rot_ctrl)
    if kind == u"euler":
        return None
    if len(axes) == 3:
        return None
    name = _as_text(node.name)
    if rot_ctrl is None or kind == u"unknown":
        return u"对象 {0} 的旋转控制器类型无法识别；非 Euler 控制器不支持只缩放部分轴向。".format(name)
    return (
        u"对象 {0} 的旋转控制器为 {1}，不支持只缩放部分轴向（请勾选 X/Y/Z 全部轴向，"
        u"或将控制器改回 Euler）。".format(name, kind)
    )


def _scale_node(node, options):
    rt = _get_rt()
    start_f = int(options[u"start_frame"])
    end_f = int(options[u"end_frame"])
    factor = float(options[u"percent"]) / 100.0
    use_mid_pivot = options[u"pivot_mode"] == u"mid"
    pivot_frame = int(options[u"pivot_frame"])
    axes = set(options.get(u"axes") or [])
    do_pos = bool(options.get(u"position"))
    do_rot = bool(options.get(u"rotation"))
    do_scl = bool(options.get(u"scale"))

    bip_root = _get_biped_root(node)
    changed = 0

    if do_pos:
        if bip_root is not None and node == bip_root:
            changed += _scale_biped_horizontal_com(
                bip_root, start_f, end_f, pivot_frame, use_mid_pivot, factor, axes
            )
        axis_ctrls = _get_position_axis_ctrls(node)
        if axis_ctrls:
            for axis in (u"X", u"Y", u"Z"):
                changed += _scale_float_controller(
                    axis_ctrls.get(axis),
                    start_f,
                    end_f,
                    pivot_frame,
                    use_mid_pivot,
                    factor,
                    axis in axes,
                )

    if do_rot:
        rot_ctrl = _get_rotation_controller(node)
        kind = _rotation_controller_kind(rot_ctrl)
        if kind == u"euler":
            axis_ctrls = _get_euler_axis_ctrls(rot_ctrl)
            for axis in (u"X", u"Y", u"Z"):
                changed += _scale_float_controller(
                    axis_ctrls.get(axis),
                    start_f,
                    end_f,
                    pivot_frame,
                    use_mid_pivot,
                    factor,
                    axis in axes,
                )
        elif kind == u"tcb" or (_is_biped_slave(node) and kind != u"euler"):
            changed += _scale_tcb_rotation(
                node, rot_ctrl, start_f, end_f, pivot_frame, use_mid_pivot, factor, axes
            )
        elif kind == u"quaternion":
            changed += _scale_quaternion_rotation(
                node, rot_ctrl, start_f, end_f, pivot_frame, use_mid_pivot, factor
            )

    if do_scl:
        axis_ctrls = _get_scale_axis_ctrls(node)
        for axis in (u"X", u"Y", u"Z"):
            changed += _scale_float_controller(
                axis_ctrls.get(axis),
                start_f,
                end_f,
                pivot_frame,
                use_mid_pivot,
                factor,
                axis in axes,
            )
    return None, changed


def apply_scale(options):
    """
    执行缩放。options:
      percent, start_frame, end_frame,
      pivot_mode: 'mid' | 'frame', pivot_frame,
      position/rotation/scale: bool,
      axes: ['X','Y','Z']
    返回 (ok, message)
    """
    nodes = get_selected_nodes()
    if not nodes:
        return False, u"请先选中要缩放的对象"
    if not options.get(u"position") and not options.get(u"rotation") and not options.get(u"scale"):
        return False, u"请至少勾选一个缩放类型"
    axes = list(options.get(u"axes") or [])
    if not axes:
        return False, u"请至少勾选一个缩放轴向"
    start_f = int(options[u"start_frame"])
    end_f = int(options[u"end_frame"])
    percent = int(options[u"percent"])
    if end_f < start_f:
        return False, u"结束帧不能小于开始帧"
    if start_f == 0 and end_f == 0:
        return False, u"请先设置缩放区间（开始帧与结束帧不能均为 0）"
    if percent == 100:
        return False, u"缩放值为 100 时会保持原动画不变；请输入小于 100 的数值。"

    if options.get(u"rotation"):
        for node in nodes:
            err = _validate_rotation_axes(node, axes)
            if err:
                return False, err

    import pymxs

    fail_message = [None]
    changed_count = [0]
    with pymxs.undo(True, u"缩放值"):
        for node in nodes:
            err, changed = _scale_node(node, options)
            if err:
                fail_message[0] = err
                break
            changed_count[0] += int(changed or 0)
        if fail_message[0]:
            raise RuntimeError(fail_message[0])

    if fail_message[0]:
        return False, fail_message[0]
    if changed_count[0] <= 0:
        return False, (
            u"没有修改到任何关键帧。请确认：\n"
            u"1. 缩放区间内有关键帧；\n"
            u"2. 勾选的类型/轴向与对象动画通道一致；\n"
            u"3. 缩放值不是 100。"
        )
    return True, u"已对 {0} 个对象的 {1} 个关键帧完成缩放".format(
        len(nodes), changed_count[0]
    )

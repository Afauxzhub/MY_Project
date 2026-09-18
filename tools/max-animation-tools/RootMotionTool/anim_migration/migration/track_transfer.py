# -*- coding: utf-8 -*-
from __future__ import print_function
from contextlib import contextmanager
import time


try:
    _text_type = unicode
except NameError:
    _text_type = str


MAX_TRACK_DEPTH = 16
DEFAULT_VALUE_TOLERANCE = 1e-4


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
    if value is None:
        return u""
    try:
        return _as_text(rt.classOf(value))
    except Exception:
        return u""


def _node_name(node):
    try:
        return _as_text(node.name)
    except Exception:
        return u""


def _subanim_name(rt, owner, index):
    try:
        return _as_text(rt.getSubAnimName(owner, index)) or u"sub_{0}".format(index)
    except Exception:
        return u"sub_{0}".format(index)


def _subanim_controller(rt, owner, index):
    try:
        sub_anim = rt.getSubAnim(owner, index)
        return sub_anim.controller
    except Exception:
        return None


def _direct_key_times(rt, controller):
    if controller is None:
        return []
    try:
        count = int(controller.numKeys)
    except Exception:
        count = 0
    out = []
    for index in range(1, count + 1):
        try:
            out.append(int(rt.getKey(controller, index).time))
        except Exception:
            pass
    if out:
        return sorted(set(out))
    try:
        keys = controller.keys
        count = int(keys.count)
    except Exception:
        count = 0
    for index in range(1, count + 1):
        try:
            out.append(int(keys[index].time))
        except Exception:
            try:
                out.append(int(keys[index - 1].time))
            except Exception:
                pass
    return sorted(set(out))


def _numeric_components(value):
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return [float(value)]
    components = []
    for attr in ("x", "y", "z", "w"):
        try:
            components.append(float(getattr(value, attr)))
        except Exception:
            break
    if components:
        return components
    try:
        scale_value = value.s
        return [float(scale_value.x), float(scale_value.y), float(scale_value.z)]
    except Exception:
        pass
    try:
        return [float(value)]
    except Exception:
        return None


def _sample_times_from_keys(key_times):
    key_times = sorted(set([int(x) for x in (key_times or [])]))
    out = list(key_times)
    for left, right in zip(key_times, key_times[1:]):
        if right > left + 1:
            out.append(left + int((right - left) / 2))
    return sorted(set(out))


def _sample_controller(rt, controller, sample_times):
    samples = []
    try:
        restore_time = int(rt.sliderTime)
    except Exception:
        restore_time = None
    try:
        for time_value in sample_times or []:
            try:
                rt.sliderTime = int(time_value)
                components = _numeric_components(controller.value)
            except Exception:
                components = None
            if components is not None:
                samples.append({"time": int(time_value), "value": components})
    finally:
        if restore_time is not None:
            try:
                rt.sliderTime = restore_time
            except Exception:
                pass
    return samples


@contextmanager
def suspended_scene_redraw(rt):
    """Suspend viewport redraw for a bounded scene-evaluation operation."""
    redraw_disabled = False
    state = {"disabled": False}
    try:
        already_disabled = False
        for getter in (
            lambda: bool(rt.isSceneRedrawDisabled()),
            lambda: bool(rt.execute("isSceneRedrawDisabled()")),
        ):
            try:
                already_disabled = getter()
                break
            except Exception:
                pass
        state["disabled"] = already_disabled
        if not already_disabled:
            try:
                rt.disableSceneRedraw()
                redraw_disabled = True
                state["disabled"] = True
            except Exception:
                try:
                    rt.execute("disableSceneRedraw()")
                    redraw_disabled = True
                    state["disabled"] = True
                except Exception:
                    pass
        yield state
    finally:
        if redraw_disabled:
            try:
                rt.enableSceneRedraw()
            except Exception:
                try:
                    rt.execute("enableSceneRedraw()")
                except Exception:
                    pass
            try:
                rt.redrawViews()
            except Exception:
                pass


def sample_track_signature_groups(rt, track_groups):
    """Populate samples for many tracks with one slider change per unique time."""
    started = time.time()
    schedule = {}
    requested_sample_count = 0
    for tracks in track_groups or []:
        for row in tracks or []:
            row["samples"] = []
            controller = row.get("_controller")
            if controller is None or not row.get("key_times"):
                continue
            for time_value in row.get("sample_times", []) or []:
                time_value = int(time_value)
                schedule.setdefault(time_value, []).append((row, controller))
                requested_sample_count += 1

    try:
        restore_time = int(rt.sliderTime)
    except Exception:
        restore_time = None
    captured_sample_count = 0
    slider_change_count = 0
    redraw_state = {"disabled": False}
    with suspended_scene_redraw(rt) as redraw_state:
        try:
            for time_value in sorted(schedule):
                try:
                    rt.sliderTime = int(time_value)
                    slider_change_count += 1
                except Exception:
                    continue
                for row, controller in schedule[time_value]:
                    try:
                        components = _numeric_components(controller.value)
                    except Exception:
                        components = None
                    if components is not None:
                        row["samples"].append({"time": int(time_value), "value": components})
                        captured_sample_count += 1
        finally:
            if restore_time is not None:
                try:
                    rt.sliderTime = restore_time
                    slider_change_count += 1
                except Exception:
                    pass
    return {
        "strategy": "frame_major_batch",
        "track_group_count": len(track_groups or []),
        "unique_time_count": len(schedule),
        "requested_sample_count": requested_sample_count,
        "captured_sample_count": captured_sample_count,
        "slider_change_count": slider_change_count,
        "viewport_redraw_suspended": bool(redraw_state.get("disabled", False)),
        "elapsed_seconds": round(time.time() - started, 3),
    }


def _anim_identity(rt, controller):
    """Return Max's stable handle for an animatable, or None when unavailable.

    Every pymxs attribute read builds a fresh wrapper object, so ``id()`` only
    describes that wrapper. CPython reuses the address as soon as the previous
    wrapper is released, which makes a sibling subanim look like an already
    visited controller and drops its whole branch from the scan. Max's animatable
    handle identifies the controller itself.
    """
    try:
        handle = int(rt.getHandleByAnim(controller))
    except Exception:
        return None
    return handle or None


def _controller_tracks(
    rt,
    controller,
    root_kind,
    root_class,
    path,
    include_samples,
    include_unkeyed,
    include_controllers,
    visited=None,
    depth=0,
    controller_ancestry=None,
):
    if controller is None or depth > MAX_TRACK_DEPTH:
        return []
    if visited is None:
        visited = set()
    if controller_ancestry is None:
        controller_ancestry = []
    identity = _anim_identity(rt, controller)
    if identity is not None:
        if identity in visited:
            return []
        visited.add(identity)

    try:
        sub_count = int(controller.numSubs)
    except Exception:
        sub_count = 0
    key_times = _direct_key_times(rt, controller)
    rows = []
    controller_class = _class_name(rt, controller)
    ancestry = list(controller_ancestry) + [controller_class]
    if key_times or (include_unkeyed and sub_count == 0):
        sample_times = _sample_times_from_keys(key_times)
        row = {
            "path": _as_text(path),
            "root_kind": _as_text(root_kind),
            "root_class": _as_text(root_class),
            "controller_class": controller_class,
            "controller_ancestry": ancestry,
            "key_times": key_times,
            "sample_times": sample_times,
            "samples": _sample_controller(rt, controller, sample_times) if include_samples and key_times else [],
        }
        if include_controllers:
            row["_controller"] = controller
        rows.append(row)

    for index in range(1, sub_count + 1):
        sub_controller = _subanim_controller(rt, controller, index)
        if sub_controller is None:
            continue
        sub_name = _subanim_name(rt, controller, index)
        sub_path = u"{0}/{1}[{2}]".format(path, sub_name, index)
        rows.extend(
            _controller_tracks(
                rt,
                sub_controller,
                root_kind,
                root_class,
                sub_path,
                include_samples,
                include_unkeyed,
                include_controllers,
                visited=visited,
                depth=depth + 1,
                controller_ancestry=ancestry,
            )
        )
    return rows


def _animatable_tracks(
    rt,
    animatable,
    root_kind,
    root_class,
    root_path,
    include_samples,
    include_unkeyed,
    include_controllers,
):
    if animatable is None:
        return []
    rows = []
    visited = set()
    try:
        direct_controller = animatable.controller
    except Exception:
        direct_controller = None
    if direct_controller is not None:
        rows.extend(
            _controller_tracks(
                rt,
                direct_controller,
                root_kind,
                root_class,
                root_path,
                include_samples,
                include_unkeyed,
                include_controllers,
                visited=visited,
            )
        )
    try:
        sub_count = int(animatable.numSubs)
    except Exception:
        sub_count = 0
    for index in range(1, sub_count + 1):
        controller = _subanim_controller(rt, animatable, index)
        if controller is None:
            continue
        sub_name = _subanim_name(rt, animatable, index)
        path = u"{0}/{1}[{2}]".format(root_path, sub_name, index)
        rows.extend(
            _controller_tracks(
                rt,
                controller,
                root_kind,
                root_class,
                path,
                include_samples,
                include_unkeyed,
                include_controllers,
                visited=visited,
            )
        )
    return rows


def _modifier_entries(rt, node):
    entries = []
    class_counts = {}
    try:
        modifiers = list(node.modifiers)
    except Exception:
        modifiers = []
    for modifier in modifiers:
        class_name = _class_name(rt, modifier)
        key = class_name.lower()
        occurrence = class_counts.get(key, 0) + 1
        class_counts[key] = occurrence
        entries.append((modifier, class_name, occurrence))
    return entries


def _custom_attribute_entries(rt, node):
    entries = []
    class_counts = {}
    try:
        count = int(rt.custAttributes.count(node))
    except Exception:
        count = 0
    for index in range(1, count + 1):
        try:
            attribute = rt.custAttributes.get(node, index)
        except Exception:
            attribute = None
        if attribute is None:
            continue
        class_name = _class_name(rt, attribute)
        key = class_name.lower()
        occurrence = class_counts.get(key, 0) + 1
        class_counts[key] = occurrence
        entries.append((attribute, class_name, occurrence))
    return entries


def collect_node_track_signatures(rt, node, include_samples=True, include_unkeyed=False, include_controllers=False):
    rows = []
    try:
        node_controller = node.controller
    except Exception:
        node_controller = None
    rows.extend(
        _controller_tracks(
            rt,
            node_controller,
            "node_controller",
            _class_name(rt, node_controller),
            "node_controller",
            include_samples,
            include_unkeyed,
            include_controllers,
        )
    )
    try:
        visibility = rt.getPropertyController(node, rt.Name("visibility"))
    except Exception:
        try:
            visibility = rt.getPropertyController(node, "visibility")
        except Exception:
            visibility = None
    rows.extend(
        _controller_tracks(
            rt,
            visibility,
            "visibility",
            _class_name(rt, visibility),
            "visibility",
            include_samples,
            include_unkeyed,
            include_controllers,
        )
    )
    for modifier, class_name, occurrence in _modifier_entries(rt, node):
        root_path = u"modifier:{0}[{1}]".format(class_name, occurrence)
        rows.extend(
            _animatable_tracks(
                rt,
                modifier,
                "modifier",
                class_name,
                root_path,
                include_samples,
                include_unkeyed,
                include_controllers,
            )
        )
    for attribute, class_name, occurrence in _custom_attribute_entries(rt, node):
        root_path = u"custom_attribute:{0}[{1}]".format(class_name, occurrence)
        rows.extend(
            _animatable_tracks(
                rt,
                attribute,
                "custom_attribute",
                class_name,
                root_path,
                include_samples,
                include_unkeyed,
                include_controllers,
            )
        )
    return rows


def json_track_signatures(rows):
    out = []
    for row in rows or []:
        item = dict(row)
        item.pop("_controller", None)
        out.append(item)
    return out


def aggregate_track_counts(rows):
    buckets = {
        "node_controller": set(),
        "visibility": set(),
        "modifier": set(),
        "custom_attribute": set(),
    }
    for row in rows or []:
        kind = _as_text(row.get("root_kind", ""))
        if kind not in buckets:
            continue
        buckets[kind].update([int(x) for x in (row.get("key_times", []) or [])])
    return dict([(key, len(value)) for key, value in buckets.items()])


def unsupported_extra_tracks(rows):
    blockers = []
    for row in rows or []:
        kind = _as_text(row.get("root_kind", ""))
        root_class = _as_text(row.get("root_class", ""))
        if kind == "custom_attribute":
            blockers.append(dict(row, reason="animated_custom_attribute"))
        elif kind == "modifier" and "morph" not in root_class.lower():
            blockers.append(dict(row, reason="unsupported_animated_modifier"))
    return blockers


def _ticks_per_frame(rt):
    for getter in (
        lambda: int(rt.ticksPerFrame),
        lambda: int(rt.execute("ticksPerFrame")),
    ):
        try:
            value = getter()
            if value > 0:
                return value
        except Exception:
            pass
    return 160


def _frame_bake_times(rt, key_times):
    key_times = sorted(set([int(x) for x in (key_times or [])]))
    if not key_times:
        return []
    step = _ticks_per_frame(rt)
    start = key_times[0]
    end = key_times[-1]
    frame_start = int(start / step) * step
    if frame_start < start:
        frame_start += step
    out = list(range(frame_start, end + 1, step)) if end >= frame_start else []
    out.extend(key_times)
    return sorted(set(out))


def build_morph_payload(rt, node, tracks=None):
    if tracks is None:
        tracks = collect_node_track_signatures(
            rt,
            node,
            include_samples=False,
            include_unkeyed=False,
            include_controllers=True,
        )
    channels = []
    for row in tracks or []:
        if row.get("root_kind") != "modifier" or "morph" not in _as_text(row.get("root_class", "")).lower():
            continue
        controller = row.get("_controller")
        if controller is None or not row.get("key_times"):
            continue
        bake_times = _frame_bake_times(rt, row.get("key_times", []))
        samples = _sample_controller(rt, controller, bake_times)
        item = json_track_signatures([row])[0]
        item["transfer_mode"] = "morph_bake"
        item["source_key_times"] = list(item.get("key_times", []))
        item["key_times"] = bake_times
        item["sample_times"] = bake_times
        item["samples"] = samples
        channels.append(item)
    return {
        "source_name": _node_name(node),
        "channels": channels,
    }


def _clear_controller_keys(rt, controller):
    try:
        rt.deleteKeys(controller, rt.Name("allKeys"))
        return True
    except Exception:
        pass
    try:
        count = int(controller.numKeys)
    except Exception:
        count = 0
    ok = True
    for index in range(count, 0, -1):
        try:
            rt.deleteKey(controller, index)
        except Exception:
            ok = False
    return ok


def clear_matching_track_keys(rt, node, expected_tracks):
    """Clear only uniquely resolved destination controllers owned by the transfer."""
    target_tracks = collect_node_track_signatures(
        rt,
        node,
        include_samples=False,
        include_unkeyed=True,
        include_controllers=True,
    )
    target_by_path = {}
    for row in target_tracks:
        target_by_path.setdefault(_as_text(row.get("path", "")), []).append(row)
    controller_rows = []
    unresolved = []
    seen_ids = set()
    for expected in expected_tracks or []:
        path = _as_text(expected.get("path", ""))
        matches = target_by_path.get(path, [])
        if len(matches) != 1:
            unresolved.append({"path": path, "target_match_count": len(matches)})
            continue
        controller = matches[0].get("_controller")
        if controller is None:
            unresolved.append({"path": path, "target_match_count": 1, "reason": "missing_controller_handle"})
            continue
        identity = _anim_identity(rt, controller)
        if identity is not None:
            if identity in seen_ids:
                continue
            seen_ids.add(identity)
        controller_rows.append((path.count("/"), path, controller))
    candidate_paths = set([item[1] for item in controller_rows])
    controllers = []
    for depth, path, controller in controller_rows:
        prefix = path + "/"
        if any([other.startswith(prefix) for other in candidate_paths if other != path]):
            continue
        controllers.append((depth, path, controller))
    controllers.sort(key=lambda item: (-item[0], item[1]))
    cleared = []
    failed = []
    for depth, path, controller in controllers:
        if _clear_controller_keys(rt, controller):
            cleared.append(path)
        else:
            failed.append(path)
    return {
        "ok": not failed,
        "cleared_controller_count": len(cleared),
        "cleared_paths": cleared,
        "unresolved_paths": unresolved,
        "failed_paths": failed,
    }


def apply_morph_payload(rt, payload, node_lookup):
    import pymxs

    results = []
    try:
        restore_time = int(rt.sliderTime)
    except Exception:
        restore_time = None
    for node_row in (payload or {}).get("objects", []) or []:
        source_name = _as_text(node_row.get("source_name", ""))
        target_name = _as_text(node_row.get("target_name", source_name))
        node = node_lookup(target_name)
        if node is None:
            for channel in node_row.get("channels", []) or []:
                results.append({
                    "source_name": source_name,
                    "target_name": target_name,
                    "path": channel.get("path", ""),
                    "status": "failed_missing_target_node",
                    "ok": False,
                })
            continue
        target_tracks = collect_node_track_signatures(
            rt,
            node,
            include_samples=False,
            include_unkeyed=True,
            include_controllers=True,
        )
        by_path = {}
        for row in target_tracks:
            by_path.setdefault(_as_text(row.get("path", "")), []).append(row)
        for channel in node_row.get("channels", []) or []:
            path = _as_text(channel.get("path", ""))
            matches = by_path.get(path, [])
            if len(matches) != 1:
                results.append({
                    "source_name": source_name,
                    "target_name": target_name,
                    "path": path,
                    "status": "failed_missing_or_ambiguous_target_track",
                    "ok": False,
                    "target_match_count": len(matches),
                })
                continue
            target_row = matches[0]
            if _as_text(target_row.get("controller_class", "")) != _as_text(channel.get("controller_class", "")):
                results.append({
                    "source_name": source_name,
                    "target_name": target_name,
                    "path": path,
                    "status": "failed_controller_type_mismatch",
                    "ok": False,
                    "source_controller_class": channel.get("controller_class", ""),
                    "target_controller_class": target_row.get("controller_class", ""),
                })
                continue
            controller = target_row.get("_controller")
            _clear_controller_keys(rt, controller)
            try:
                context = pymxs.animate(True)
            except Exception:
                context = None
            try:
                if context is not None:
                    context.__enter__()
                for sample in channel.get("samples", []) or []:
                    values = sample.get("value", []) or []
                    if len(values) != 1:
                        raise RuntimeError(u"Morpher 通道不是标量控制器: {0}".format(path))
                    rt.sliderTime = int(sample.get("time", 0))
                    controller.value = float(values[0])
                results.append({
                    "source_name": source_name,
                    "target_name": target_name,
                    "path": path,
                    "status": "baked",
                    "ok": True,
                    "sample_count": len(channel.get("samples", []) or []),
                })
            except Exception as exc:
                results.append({
                    "source_name": source_name,
                    "target_name": target_name,
                    "path": path,
                    "status": "failed_apply",
                    "ok": False,
                    "message": _as_text(exc),
                })
            finally:
                if context is not None:
                    try:
                        context.__exit__(None, None, None)
                    except Exception:
                        pass
    if restore_time is not None:
        try:
            rt.sliderTime = restore_time
        except Exception:
            pass
    return {
        "ok": not [x for x in results if not x.get("ok", False)],
        "items": results,
        "failed_count": len([x for x in results if not x.get("ok", False)]),
        "baked_count": len([x for x in results if x.get("status") == "baked"]),
    }


def _sample_map(rows):
    return dict([(int(row.get("time", 0)), row.get("value", [])) for row in (rows or [])])


def _max_value_error(source_values, target_values):
    if len(source_values or []) != len(target_values or []):
        return None
    if not source_values:
        return 0.0
    return max([abs(float(a) - float(b)) for a, b in zip(source_values, target_values)])


def _track_samples_match(source, target, value_tolerance):
    if _as_text(source.get("controller_class", "")) != _as_text(target.get("controller_class", "")):
        return False
    source_times = sorted(set([int(x) for x in (source.get("key_times", []) or [])]))
    target_times = sorted(set([int(x) for x in (target.get("key_times", []) or [])]))
    if source_times != target_times:
        return False
    source_samples = _sample_map(source.get("samples", []))
    target_samples = _sample_map(target.get("samples", []))
    if not source_samples:
        return False
    if set(source_samples) != set(target_samples):
        return False
    for time_value, source_value in source_samples.items():
        error = _max_value_error(source_value, target_samples.get(time_value, []))
        if error is None or error > float(value_tolerance):
            return False
    return True


def _matching_ancestor_path(source, source_by_path, target_by_path, value_tolerance):
    path = _as_text(source.get("path", ""))
    parts = path.split("/")
    for count in range(len(parts) - 1, 0, -1):
        ancestor_path = u"/".join(parts[:count])
        source_matches = source_by_path.get(ancestor_path, [])
        target_matches = target_by_path.get(ancestor_path, [])
        if len(source_matches) != 1 or len(target_matches) != 1:
            continue
        if _track_samples_match(source_matches[0], target_matches[0], value_tolerance):
            return ancestor_path
    return u""


def _default_node_track_kind(source, value_tolerance):
    if _as_text(source.get("root_kind", "")) != "node_controller":
        return u""
    path = _as_text(source.get("path", "")).lower()
    samples = source.get("samples", []) or []
    values = [row.get("value", []) or [] for row in samples]
    if not values or any([not row for row in values]):
        return u""
    tolerance = float(value_tolerance)
    if "position[" in path or "_position[" in path:
        if all([all([abs(float(value)) <= tolerance for value in row]) for row in values]):
            return "zero_position"
    if "rotation[" in path or "_rotation[" in path:
        is_default = True
        for row in values:
            if len(row) == 4:
                if not (
                    all([abs(float(value)) <= tolerance for value in row[:3]]) and
                    abs(abs(float(row[3])) - 1.0) <= tolerance
                ):
                    is_default = False
                    break
            elif not all([abs(float(value)) <= tolerance for value in row]):
                is_default = False
                break
        if is_default:
            return "identity_rotation"
    if "scale[" in path or "_scale[" in path:
        if all([all([abs(float(value) - 1.0) <= tolerance for value in row]) for row in values]):
            return "unit_scale"
    return u""


def validate_track_signatures(source_tracks, target_tracks, value_tolerance=DEFAULT_VALUE_TOLERANCE):
    source_by_path = {}
    for row in source_tracks or []:
        source_by_path.setdefault(_as_text(row.get("path", "")), []).append(row)
    target_by_path = {}
    for row in target_tracks or []:
        target_by_path.setdefault(_as_text(row.get("path", "")), []).append(row)
    errors = []
    warnings = []
    checked = 0
    semantic_equivalent = 0
    for source in source_tracks or []:
        path = _as_text(source.get("path", ""))
        matches = target_by_path.get(path, [])
        if len(matches) != 1:
            if not matches:
                ancestor_path = _matching_ancestor_path(
                    source,
                    source_by_path,
                    target_by_path,
                    value_tolerance,
                )
                if ancestor_path:
                    warnings.append({
                        "path": path,
                        "status": "missing_descendant_but_parent_matches",
                        "matching_ancestor_path": ancestor_path,
                        "target_match_count": 0,
                    })
                    semantic_equivalent += 1
                    continue
                default_kind = _default_node_track_kind(source, value_tolerance)
                if default_kind:
                    warnings.append({
                        "path": path,
                        "status": "missing_default_value_track",
                        "default_kind": default_kind,
                        "target_match_count": 0,
                    })
                    semantic_equivalent += 1
                    continue
            errors.append({
                "path": path,
                "status": "missing_or_ambiguous_target_track",
                "target_match_count": len(matches),
            })
            continue
        target = matches[0]
        checked += 1
        if _as_text(source.get("controller_class", "")) != _as_text(target.get("controller_class", "")):
            errors.append({
                "path": path,
                "status": "controller_type_mismatch",
                "source_controller_class": source.get("controller_class", ""),
                "target_controller_class": target.get("controller_class", ""),
            })
            continue
        expected_times = sorted(set([int(x) for x in (source.get("key_times", []) or [])]))
        target_times = sorted(set([int(x) for x in (target.get("key_times", []) or [])]))
        if expected_times != target_times:
            errors.append({
                "path": path,
                "status": "key_times_mismatch",
                "source_key_times": expected_times,
                "target_key_times": target_times,
            })
            continue
        source_samples = _sample_map(source.get("samples", []))
        target_samples = _sample_map(target.get("samples", []))
        for time_value, source_value in source_samples.items():
            if time_value not in target_samples:
                errors.append({
                    "path": path,
                    "status": "missing_target_sample",
                    "time": time_value,
                })
                continue
            error = _max_value_error(source_value, target_samples[time_value])
            if error is None or error > float(value_tolerance):
                errors.append({
                    "path": path,
                    "status": "sample_value_mismatch",
                    "time": time_value,
                    "max_error": error,
                    "tolerance": float(value_tolerance),
                })
    return {
        "ok": not errors,
        "status": ("passed_with_semantic_warnings" if warnings else "passed") if not errors else "failed",
        "checked_track_count": checked,
        "semantic_equivalent_track_count": semantic_equivalent,
        "source_track_count": len(source_tracks or []),
        "errors": errors,
        "warnings": warnings,
    }


def morph_target_paths(rt, node):
    rows = []
    for modifier, class_name, occurrence in _modifier_entries(rt, node):
        if "morph" not in _as_text(class_name).lower():
            continue
        rows.extend(
            _animatable_tracks(
                rt,
                modifier,
                "modifier",
                class_name,
                u"modifier:{0}[{1}]".format(class_name, occurrence),
                include_samples=False,
                include_unkeyed=True,
                include_controllers=False,
            )
        )
    return sorted(set([
        _as_text(row.get("path", ""))
        for row in rows
        if row.get("root_kind") == "modifier" and "morph" in _as_text(row.get("root_class", "")).lower()
    ]))


def prepare_morph_signatures(track_signatures, morph_channels):
    morph_by_path = dict([(_as_text(row.get("path", "")), row) for row in (morph_channels or [])])
    out = []
    for row in track_signatures or []:
        path = _as_text(row.get("path", ""))
        if path in morph_by_path:
            out.append(dict(morph_by_path[path]))
        else:
            out.append(dict(row))
    return out

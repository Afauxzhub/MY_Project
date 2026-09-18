# -*- coding: utf-8 -*-
"""
Animation Manager Module
Handles saving and loading of animation data for different skeleton types.

Architecture:
  AnimManager        - Dispatcher: detects skeleton type and delegates to correct handler
  BipedAnimHandler   - Handles Biped (.bip) save/load via rt.biped
  PoseHandler        - Handles local pose save/load as JSON
  (Future) XAFAnimHandler - Will handle standard bone (.xaf) save/load
"""

import os
import io
import json
import zipfile
import tempfile
import shutil
import copy

from .animation_asset_ops import save_animation as _save_animation_op
from .animation_asset_ops import apply_animation as _apply_animation_op
from .pose_ops import save_pose as _save_pose_op
from .pose_ops import apply_pose as _apply_pose_op
from . import preview_utils
from . import max_utils

try:
    from pymxs import runtime as rt
    PYMXS_AVAILABLE = True
except ImportError:
    PYMXS_AVAILABLE = False

try:
    from PySide2.QtWidgets import (
        QApplication, QInputDialog, QMessageBox, QLineEdit, QProgressDialog
    )
    PYSIDE2_AVAILABLE = True
except ImportError:
    PYSIDE2_AVAILABLE = False

try:
    text_type = unicode
except NameError:
    text_type = str


# ---------------------------------------------------------------------------
# Safe print helper
# ---------------------------------------------------------------------------

def _safe_print(msg):
    """
    Print *msg* without ever raising UnicodeEncodeError / UnicodeDecodeError.

    Python 2 behaviour: repr() of a unicode object produces ASCII-only bytes,
    so the old repr() fallback was safe.
    Python 3 behaviour: repr() of a str can still contain non-ASCII characters
    (e.g. repr("中文") == "'中文'"), so we must explicitly encode to ASCII after
    calling repr(), using backslashreplace to keep the information readable.
    """
    try:
        print(msg)
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            if isinstance(msg, bytes):
                fallback = msg.decode('ascii', errors='replace')
            else:
                # encode to pure ASCII; non-ASCII chars become \xNN / \uNNNN
                fallback = repr(msg).encode(
                    'ascii', errors='backslashreplace'
                ).decode('ascii')
            print(fallback)
        except Exception:
            try:
                print("[unprintable log message]")
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Unified animation package constants
# ---------------------------------------------------------------------------

ANIMX_EXT = ".animx"
_ANIMX_VERSION = 2
_ENABLE_ANIM_DIAGNOSTICS = False
_SCENE_EVAL_REDRAW_STRIDE = 8
_scene_eval_state = {"count": 0}


def _sanitize_filename(name):
    """Replace characters that are illegal in filenames with underscores."""
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(ch, "_")
    return name


def _anim_asset_filename(clip_name, animation_mode, ext):
    """Build a save filename that keeps Template distinct from Animation."""
    base_name = text_type(clip_name or "").strip() or "NewAsset"
    mode_name = text_type(animation_mode or "").strip().lower()
    if mode_name == "full_biped":
        lowered = base_name.lower()
        if not lowered.endswith("_template"):
            base_name += "_template"
    return base_name + text_type(ext or "")


def _diag_print(msg):
    """Print verbose animation diagnostics only when explicitly enabled."""
    if _ENABLE_ANIM_DIAGNOSTICS:
        _safe_print(msg)


def _reset_scene_evaluation_state():
    """Reset redraw throttling between long animation operations."""
    _scene_eval_state["count"] = 0


def _safe_node_name(obj):
    """
    Return a node's name as a genuine Python str/unicode, safe for both
    Python 2 (3ds Max ≤ 2020) and Python 3 (3ds Max ≥ 2021).

    In some Max/pymxs versions obj.name is a C-extension wrapper whose
    __str__ (and __format__) internally encode to ASCII, raising
    UnicodeEncodeError for non-ASCII (e.g. Chinese) names.  This function
    always returns a real Python str so .format() and json.dump() work safely.

    Priority:
      1. isinstance check — already a Python str/bytes, handle directly.
      2. str(raw)          — works for ASCII names and modern Max Python 3.
      3. encode→decode     — extracts the unicode content from a Python 2
                             unicode or a pymxs wrapper that supports .encode().
      4. repr(raw)         — last resort; produces a safe ASCII representation.
    """
    try:
        raw = obj.name
    except AttributeError:
        return '<?>'

    # Already a native Python str (Python 3) or bytes
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bytes):
        return raw.decode('utf-8', errors='replace')

    # Try str() — works for ASCII names in all versions
    try:
        return str(raw)
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    except Exception:
        pass

    # For pymxs wrappers / Python 2 unicode: use encode→decode round-trip
    # to produce a real Python str/unicode without going through __str__.
    if hasattr(raw, 'encode'):
        try:
            return raw.encode('utf-8', errors='replace').decode('utf-8')
        except Exception:
            pass

    # Absolute last resort: repr always returns an ASCII-safe str
    try:
        return repr(raw)
    except Exception:
        return '<?>'


def _safe_runtime_identity(value):
    """
    Return a stable, ASCII-safe identity string for pymxs runtime objects.

    `repr()` on some Max wrappers can internally force ASCII encoding of node /
    controller names, which explodes on Chinese names in Max 2020. We therefore
    prefer runtime handles when available and only fall back to Python object id.
    """
    if value is None:
        return "none"

    if PYMXS_AVAILABLE:
        try:
            handle = rt.getHandleByAnim(value)
            return "anim:{0}".format(int(handle))
        except Exception:
            pass

    try:
        return "py:{0}".format(int(id(value)))
    except Exception:
        return "py:unknown"


def _format_frame_list(frames, limit=24):
    """Format a frame list for compact diagnostics."""
    if not frames:
        return "(none)"
    ordered = []
    for frame in frames:
        try:
            ordered.append(int(frame))
        except Exception:
            pass
    if not ordered:
        return "(none)"
    ordered = sorted(set(ordered))
    if len(ordered) <= limit:
        return u", ".join(str(f) for f in ordered)
    head_count = max(1, limit // 2)
    tail_count = max(1, limit - head_count)
    head = ordered[:head_count]
    tail = ordered[-tail_count:]
    return u"{0} ... {1} (total={2})".format(
        u", ".join(str(f) for f in head),
        u", ".join(str(f) for f in tail),
        len(ordered)
    )


def _frame_range_from_list(frames, default_start=None, default_end=None):
    """Return (start, end) from a frame list, falling back when empty."""
    ordered = []
    for frame in frames or []:
        try:
            ordered.append(int(frame))
        except Exception:
            pass
    if ordered:
        ordered = sorted(set(ordered))
        return ordered[0], ordered[-1]
    return default_start, default_end


def _coerce_frame_int(value):
    """Return value as int when possible, otherwise None."""
    try:
        return int(value)
    except Exception:
        return None


def _resolve_apply_frame_window(source_start, source_end,
                                target_start=None, target_end=None):
    """
    Resolve source and destination windows for animation apply.

    Semantics:
      - The saved clip keeps its original timing spacing.
      - The clip is shifted so saved `source_start` lands on `target_start`.
      - If the requested target range is shorter than the saved clip, the tail
        is cropped.
      - If the requested target range is longer than the saved clip, the clip
        simply ends at its natural length.
    """
    source_start = _coerce_frame_int(source_start)
    source_end = _coerce_frame_int(source_end)
    target_start = _coerce_frame_int(target_start)
    target_end = _coerce_frame_int(target_end)

    if source_start is None:
        source_start = target_start if target_start is not None else 0
    if source_end is None or source_end < source_start:
        source_end = source_start
    if target_start is None:
        target_start = source_start

    max_target_end = target_start + max(0, source_end - source_start)
    if target_end is None:
        target_end = max_target_end
    else:
        target_end = min(target_end, max_target_end)

    return source_start, source_end, target_start, target_end


def _map_source_frame_to_target(source_frame, source_start,
                                target_start, target_end=None):
    """Map one saved frame into the resolved destination window."""
    source_frame = _coerce_frame_int(source_frame)
    source_start = _coerce_frame_int(source_start)
    target_start = _coerce_frame_int(target_start)
    target_end = _coerce_frame_int(target_end)
    if source_frame is None or source_start is None or target_start is None:
        return None

    target_frame = target_start + (source_frame - source_start)
    if target_end is not None and target_frame > target_end:
        return None
    return target_frame


def _run_temp_maxscript(ms_content, log_prefix):
    """Execute temporary MAXScript content and return its boolean result."""
    tmp_ms = None
    try:
        handle, tmp_ms = tempfile.mkstemp(prefix="animlib_ms_", suffix=".ms")
        os.close(handle)
        with open(tmp_ms, 'w') as f:
            f.write(ms_content)
        result = bool(rt.fileIn(tmp_ms))
        if not result:
            _safe_print("[{0}] MAXScript returned false: {1}".format(log_prefix, repr(tmp_ms)))
            try:
                _safe_print("[{0}] MAXScript content:\\n{1}".format(log_prefix, ms_content))
            except Exception:
                pass
        return result
    except Exception as e:
        _safe_print("[{0}] MAXScript run FAILED: {1}".format(log_prefix, repr(e)))
        return False
    finally:
        if tmp_ms:
            try:
                os.remove(tmp_ms)
            except Exception:
                pass


def _run_biped_controller_script(bip_root, action_ms, log_prefix):
    """Run a MAXScript action against all controllers of one Biped root."""
    node_name = _safe_node_name(bip_root)
    if not node_name:
        return False

    ms_content = (
        '(\n'
        '    fn _animlibGetBipRoot n =\n'
        '    (\n'
        '        local c = n\n'
        '        while (c != undefined and c.parent != undefined and classof c.parent == Biped_Object) do\n'
        '            c = c.parent\n'
        '        c\n'
        '    )\n'
        '    fn _animlibAppendUnique arr item =\n'
        '    (\n'
        '        if item != undefined and (findItem arr item) == 0 do append arr item\n'
        '    )\n'
        '    fn _animlibCollectCtrls rootNode =\n'
        '    (\n'
        '        local ctrls = #()\n'
        '        if rootNode == undefined then return ctrls\n'
        '        try(_animlibAppendUnique ctrls rootNode.controller.vertical.controller)catch()\n'
        '        try(_animlibAppendUnique ctrls rootNode.controller.horizontal.controller)catch()\n'
        '        try(_animlibAppendUnique ctrls rootNode.controller.turning.controller)catch()\n'
        '        for obj in objects where (classof obj == Biped_Object) do\n'
        '        (\n'
        '            if (_animlibGetBipRoot obj) == rootNode do\n'
        '                try(_animlibAppendUnique ctrls obj.controller)catch()\n'
        '        )\n'
        '        ctrls\n'
        '    )\n'
        '    local _root = getNodeByName "{node}"\n'
        '    if _root == undefined then\n'
        '    (\n'
        '        false\n'
        '    )\n'
        '    else\n'
        '    (\n'
        '        local _ctrls = _animlibCollectCtrls _root\n'
        '        local _ok = true\n'
        '{action}'
        '        _ok\n'
        '    )\n'
        ')\n'
    ).format(
        node=node_name.replace('"', r'\"'),
        action=action_ms
    )
    return _run_temp_maxscript(ms_content, log_prefix)


def _clear_biped_animation_keys(bip_root):
    """Delete all authored keys on a Biped root and its body-part controllers."""
    action_ms = (
        '        for c in _ctrls do\n'
        '        (\n'
        '            local _keyCount = 0\n'
        '            try(_keyCount = numKeys c)catch(_keyCount = 0)\n'
        '            if _keyCount > 0 do try(biped.deleteKeys c #allKeys)catch()\n'
        '        )\n'
    )
    return _run_biped_controller_script(
        bip_root,
        action_ms,
        "BipedAnimHandler.clearKeys"
    )


def _move_all_biped_keys(bip_root, frame_offset):
    """Move all current Biped keys by a frame offset."""
    frame_offset = _coerce_frame_int(frame_offset)
    if frame_offset in (None, 0):
        return True
    action_ms = (
        '        for c in _ctrls do\n'
        '        (\n'
        '            try(deselectKeys c)catch()\n'
        '            try(selectKeys c)catch()\n'
        '            try(moveKeys c {offset}f #selection)catch()\n'
        '            try(sortKeys c)catch()\n'
        '            try(deselectKeys c)catch()\n'
        '        )\n'
    ).format(offset=int(frame_offset))
    return _run_biped_controller_script(
        bip_root,
        action_ms,
        "BipedAnimHandler.moveKeys"
    )


def _trim_biped_keys_to_window(bip_root, keep_start, keep_end):
    """Delete any Biped keys that fall outside the requested keep window."""
    keep_start = _coerce_frame_int(keep_start)
    keep_end = _coerce_frame_int(keep_end)
    if keep_start is None or keep_end is None or keep_end < keep_start:
        return False

    action_ms = (
        '        for c in _ctrls do\n'
        '        (\n'
        '            local _keyCount = 0\n'
        '            local _selCount = 0\n'
        '            try(_keyCount = numKeys c)catch(_keyCount = 0)\n'
        '            for i = 1 to _keyCount do\n'
        '            (\n'
        '                local k = undefined\n'
        '                try(k = biped.getKey c i)catch(k = undefined)\n'
        '                if k != undefined do try(k.selected = false)catch()\n'
        '            )\n'
        '            for i = 1 to _keyCount do\n'
        '            (\n'
        '                local k = undefined\n'
        '                try(k = biped.getKey c i)catch(k = undefined)\n'
        '                if k != undefined do\n'
        '                (\n'
        '                    try\n'
        '                    (\n'
        '                        if (k.time < {keep_start}f) or (k.time > {keep_end}f) do k.selected = true\n'
        '                    )\n'
        '                    catch()\n'
        '                )\n'
        '            )\n'
        '            for i = 1 to _keyCount do\n'
        '            (\n'
        '                local k = undefined\n'
        '                try(k = biped.getKey c i)catch(k = undefined)\n'
        '                if k != undefined do try(if k.selected do _selCount += 1)catch()\n'
        '            )\n'
        '            if _selCount > 0 do try(biped.deleteKeys c #selection)catch()\n'
        '            try(deselectKeys c)catch()\n'
        '        )\n'
    ).format(
        keep_start=int(keep_start),
        keep_end=int(keep_end)
    )
    return _run_biped_controller_script(
        bip_root,
        action_ms,
        "BipedAnimHandler.trimKeys"
    )


def _delete_biped_keys_in_window(bip_root, delete_start, delete_end):
    """Delete authored Biped keys that fall inside one frame window."""
    delete_start = _coerce_frame_int(delete_start)
    delete_end = _coerce_frame_int(delete_end)
    if delete_start is None or delete_end is None or delete_end < delete_start:
        return False

    action_ms = (
        '        for c in _ctrls do\n'
        '        (\n'
        '            local _keyCount = 0\n'
        '            local _selCount = 0\n'
        '            try(_keyCount = numKeys c)catch(_keyCount = 0)\n'
        '            for i = 1 to _keyCount do\n'
        '            (\n'
        '                local k = undefined\n'
        '                try(k = biped.getKey c i)catch(k = undefined)\n'
        '                if k != undefined do try(k.selected = false)catch()\n'
        '            )\n'
        '            for i = 1 to _keyCount do\n'
        '            (\n'
        '                local k = undefined\n'
        '                try(k = biped.getKey c i)catch(k = undefined)\n'
        '                if k != undefined do\n'
        '                (\n'
        '                    try\n'
        '                    (\n'
        '                        if (k.time >= {delete_start}f) and (k.time <= {delete_end}f) do k.selected = true\n'
        '                    )\n'
        '                    catch()\n'
        '                )\n'
        '            )\n'
        '            for i = 1 to _keyCount do\n'
        '            (\n'
        '                local k = undefined\n'
        '                try(k = biped.getKey c i)catch(k = undefined)\n'
        '                if k != undefined do try(if k.selected do _selCount += 1)catch()\n'
        '            )\n'
        '            if _selCount > 0 do try(biped.deleteKeys c #selection)catch()\n'
        '            try(deselectKeys c)catch()\n'
        '        )\n'
    ).format(
        delete_start=int(delete_start),
        delete_end=int(delete_end)
    )
    return _run_biped_controller_script(
        bip_root,
        action_ms,
        "BipedAnimHandler.deleteWindow"
    )


def _get_biped_key_range(bip_root, start_frame=None, end_frame=None):
    """
    Return the authored Biped key range for one skeleton as (start, end).

    This is used by full-BIP splice apply so we only restore the original
    motion that truly existed outside the incoming clip window.
    """
    if not PYMXS_AVAILABLE or bip_root is None:
        return None, None

    start_frame = _coerce_frame_int(start_frame)
    end_frame = _coerce_frame_int(end_frame)
    if start_frame is None or end_frame is None:
        # Probe authored keys across a very wide window instead of the current
        # animation range. During apply, users often set animationRange to the
        # target window (e.g. 60-110), but the original Biped motion we need to
        # preserve may live outside that interval (e.g. 0-50).
        start_frame = -100000
        end_frame = 100000
    if end_frame < start_frame:
        return None, None

    frames = set()
    visited = set()
    root_identity = _safe_runtime_identity(bip_root)

    try:
        ctrl = BipedAnimHandler.get_biped_controller(bip_root)
    except Exception:
        ctrl = None

    if ctrl is not None:
        for getter_name in ("getHorizontalControl", "getVerticalControl", "getTurnControl"):
            sub_ctrl = None
            try:
                getter = getattr(rt.biped, getter_name)
                sub_ctrl = getter(ctrl)
            except Exception:
                sub_ctrl = None
            if sub_ctrl is not None:
                GenericAnimHandler._collect_controller_key_times(
                    sub_ctrl, start_frame, end_frame, frames, visited
                )

    try:
        scene_objects = list(rt.objects)
    except Exception:
        scene_objects = []

    for obj in scene_objects:
        try:
            if not BipedAnimHandler.is_biped_object(obj):
                continue
            obj_root = BipedAnimHandler.get_biped_root(obj)
            if obj_root is None:
                continue
            if _safe_runtime_identity(obj_root) != root_identity:
                continue
            obj_ctrl = obj.controller
        except Exception:
            obj_ctrl = None
        if obj_ctrl is not None:
            GenericAnimHandler._collect_controller_key_times(
                obj_ctrl, start_frame, end_frame, frames, visited
            )

    return _frame_range_from_list(frames, None, None)


def _log_biped_key_range(log_prefix, bip_root, start_frame=None, end_frame=None):
    """Print the current authored Biped key range for diagnostics."""
    try:
        key_start, key_end = _get_biped_key_range(bip_root, start_frame, end_frame)
        _safe_print(
            "[{0}] key_range root={1} window={2}-{3} result={4}-{5}".format(
                log_prefix,
                _safe_node_name(bip_root),
                _coerce_frame_int(start_frame),
                _coerce_frame_int(end_frame),
                key_start,
                key_end
            )
        )
    except Exception as e:
        _safe_print(
            "[{0}] key_range FAILED root={1}: {2}".format(
                log_prefix,
                _safe_node_name(bip_root),
                repr(e)
            )
        )


def _collect_biped_nodes_for_root(bip_root):
    """Return all Biped nodes that belong to one root skeleton."""
    nodes = []
    if not PYMXS_AVAILABLE or bip_root is None:
        return nodes

    root_identity = _safe_runtime_identity(bip_root)
    try:
        scene_objects = list(rt.objects)
    except Exception:
        scene_objects = []

    for obj in scene_objects:
        try:
            if not BipedAnimHandler.is_biped_object(obj):
                continue
            obj_root = BipedAnimHandler.get_biped_root(obj)
            if obj_root is None:
                continue
            if _safe_runtime_identity(obj_root) != root_identity:
                continue
            nodes.append(obj)
        except Exception:
            pass

    nodes.sort(key=lambda node: _safe_node_name(node).lower())
    return nodes


def _capture_biped_partial_range(bip_root, range_start, range_end, bake_keys=True):
    """Capture one full-Biped range as internal partial snapshot data."""
    range_start = _coerce_frame_int(range_start)
    range_end = _coerce_frame_int(range_end)
    if bip_root is None or range_start is None or range_end is None or range_end < range_start:
        return {}

    nodes = _collect_biped_nodes_for_root(bip_root)
    if not nodes:
        return {}

    root_name = _safe_node_name(bip_root)
    partial_roots = {
        root_name: {
            "root": bip_root,
            "root_name": root_name,
            "nodes": nodes,
        }
    }
    return BipedPartialAnimHandler.capture_keys(
        partial_roots,
        range_start,
        range_end,
        bake_keys=bake_keys
    )


def _set_biped_mixer_mode(bip_root, enabled):
    """Toggle Motion Mixer mode on the target Biped."""
    if not PYMXS_AVAILABLE or bip_root is None:
        return False
    try:
        ctrl = BipedAnimHandler.get_biped_controller(bip_root)
        ctrl.mixerMode = bool(enabled)
        return True
    except Exception as e:
        _safe_print(
            "[BipedMixer] set mixerMode FAILED root={0} enabled={1}: {2}".format(
                _safe_node_name(bip_root),
                bool(enabled),
                repr(e)
            )
        )
        return False


def _build_biped_capture_frame_list(*frame_ranges):
    """Return sorted unique capture frames for the non-overlapping splice windows."""
    frames = set()
    for frame_range in frame_ranges:
        if not frame_range or len(frame_range) < 2:
            continue
        range_start = _coerce_frame_int(frame_range[0])
        range_end = _coerce_frame_int(frame_range[1])
        if range_start is None or range_end is None or range_end < range_start:
            continue
        frames.update(range(int(range_start), int(range_end) + 1))
    return sorted(frames)


def _capture_biped_visible_result(bip_root, start_frame, end_frame, frame_list=None):
    """Capture the currently visible Biped animation result frame-by-frame."""
    start_frame = _coerce_frame_int(start_frame)
    end_frame = _coerce_frame_int(end_frame)
    if bip_root is None or start_frame is None or end_frame is None or end_frame < start_frame:
        return {}

    import pymxs

    nodes = _collect_biped_nodes_for_root(bip_root)
    if not nodes:
        return {}

    root_name = _safe_node_name(bip_root)
    node_names = [_safe_node_name(node) for node in nodes]
    frames_data = {}
    if frame_list:
        frames_to_capture = []
        seen_frames = set()
        for frame in frame_list:
            frame = _coerce_frame_int(frame)
            if frame is None or frame < start_frame or frame > end_frame or frame in seen_frames:
                continue
            seen_frames.add(frame)
            frames_to_capture.append(int(frame))
    else:
        frames_to_capture = list(range(int(start_frame), int(end_frame) + 1))

    previous_time = None
    try:
        previous_time = int(rt.currentTime)
    except Exception:
        previous_time = None

    try:
        for frame in frames_to_capture:
            try:
                with pymxs.attime(frame):
                    try:
                        rt.sliderTime = frame
                    except Exception:
                        pass
                    PoseHandler._refresh_scene_evaluation(force=True)
                frame_nodes = PoseHandler.capture_pose_snapshot(nodes, frame)
            except Exception as e:
                _safe_print(
                    "[BipedMixerBake] visible capture failed frame={0}: {1}".format(
                        frame,
                        repr(e)
                    )
                )
                frame_nodes = {}
            if frame_nodes:
                frames_data[str(frame)] = {"nodes": frame_nodes}
    finally:
        if previous_time is not None:
            try:
                rt.sliderTime = previous_time
            except Exception:
                pass
            try:
                PoseHandler._refresh_scene_evaluation(force=True)
            except Exception:
                pass

    if not frames_data:
        return {}

    return {
        "version": 1,
        "start_frame": int(start_frame),
        "end_frame": int(end_frame),
        "bipeds": {
            root_name: {
                "root_name": root_name,
                "node_names": node_names,
                "frames": frames_data,
                "object_keyframes": dict(
                    (node_name, list(frames_to_capture))
                    for node_name in node_names
                ),
            }
        }
    }


def _inject_biped_hold_frame(snapshot_data, source_frame, hold_frame):
    """Duplicate one captured pose onto a later frame to prevent gap interpolation."""
    source_frame = _coerce_frame_int(source_frame)
    hold_frame = _coerce_frame_int(hold_frame)
    if source_frame is None or hold_frame is None or hold_frame <= source_frame:
        return 0

    inserted = 0
    bipeds = (snapshot_data or {}).get("bipeds") or {}
    for payload in bipeds.values():
        frames_data = payload.get("frames") or {}
        source_payload = frames_data.get(str(source_frame))
        if not source_payload:
            continue
        if str(hold_frame) in frames_data:
            continue
        try:
            frames_data[str(hold_frame)] = copy.deepcopy(source_payload)
        except Exception:
            frames_data[str(hold_frame)] = source_payload
        object_keyframes = payload.get("object_keyframes") or {}
        for node_name, frame_list in object_keyframes.items():
            try:
                if int(hold_frame) not in frame_list:
                    frame_list.append(int(hold_frame))
                    frame_list.sort()
            except Exception:
                object_keyframes[node_name] = sorted(
                    set((frame_list or []) + [int(hold_frame)])
                )
        inserted += 1
    return inserted


def _describe_biped_snapshot_motion(snapshot_data, root_name, start_frame, end_frame):
    """Summarise whether captured frames actually contain changing root motion."""
    bipeds = (snapshot_data or {}).get("bipeds") or {}
    payload = bipeds.get(root_name) or {}
    frames_data = payload.get("frames") or {}
    start_frame = _coerce_frame_int(start_frame)
    end_frame = _coerce_frame_int(end_frame)
    if start_frame is None or end_frame is None or end_frame < start_frame:
        return "range=invalid"
    if not frames_data:
        return "range={0}-{1} captured=0".format(start_frame, end_frame)

    def _pose_signature(node_payload):
        world_pos = node_payload.get("world_pos") or []
        world_rot_q = node_payload.get("world_rot_q") or []
        pos_sig = tuple(round(float(v), 4) for v in world_pos[:3])
        rot_sig = tuple(round(float(v), 4) for v in world_rot_q[:4])
        return pos_sig, rot_sig

    distinct_pos = set()
    distinct_rot = set()
    sample_points = []
    sample_frames = [start_frame]
    if end_frame > start_frame:
        sample_frames.append(int((int(start_frame) + int(end_frame)) / 2))
        sample_frames.append(end_frame)

    seen_sample_frames = []
    for frame in sample_frames:
        if frame not in seen_sample_frames:
            seen_sample_frames.append(frame)

    for frame in range(int(start_frame), int(end_frame) + 1):
        frame_payload = frames_data.get(str(frame)) or {}
        node_payload = (frame_payload.get("nodes") or {}).get(root_name)
        if not node_payload:
            continue
        pos_sig, rot_sig = _pose_signature(node_payload)
        distinct_pos.add(pos_sig)
        distinct_rot.add(rot_sig)
        if frame in seen_sample_frames:
            sample_points.append(
                "{0}:pos={1},rot={2}".format(frame, pos_sig, rot_sig)
            )

    return (
        "range={0}-{1} distinctRootPos={2} distinctRootRot={3} samples=[{4}]".format(
            start_frame,
            end_frame,
            len(distinct_pos),
            len(distinct_rot),
            "; ".join(sample_points)
        )
    )


def _apply_biped_visible_result(snapshot_data, bip_root):
    """Bake a captured visible Biped result back to authored keys."""
    bipeds = (snapshot_data or {}).get("bipeds") or {}
    if not bipeds or bip_root is None:
        return 0

    selected_biped_node_map = {}
    for node in _collect_biped_nodes_for_root(bip_root):
        selected_biped_node_map[_safe_node_name(node)] = node
    if not selected_biped_node_map:
        return 0

    applied_names = set()
    apply_session_state = {}
    for root_name in sorted(bipeds.keys()):
        payload = bipeds.get(root_name) or {}
        frames_data = payload.get("frames") or {}
        for frame_str in sorted(frames_data.keys(), key=lambda value: int(value)):
            target_frame = int(frame_str)
            frame_payload = frames_data.get(frame_str) or {}
            nodes_payload = frame_payload.get("nodes") or {}
            if not nodes_payload:
                continue
            frame_applied_names = []
            try:
                PoseHandler.apply_pose_snapshot(
                    nodes_payload,
                    target_frame,
                    node_lookup=selected_biped_node_map,
                    applied_names_out=frame_applied_names,
                    session_state=apply_session_state,
                    force_bake_keys=True,
                    direct_root_keys=True
                )
                applied_names.update(frame_applied_names)
            except Exception as e:
                _safe_print(
                    "[BipedMixerBake] visible-result apply failed frame={0}: {1}".format(
                        target_frame,
                        repr(e)
                    )
                )
    return len(applied_names)


def _apply_biped_partial_range(partial_data, bip_root, range_start=None, range_end=None):
    """Apply previously captured internal Biped partial snapshot data."""
    if not partial_data:
        return 0

    selected_node_map = {}
    for node in _collect_biped_nodes_for_root(bip_root):
        selected_node_map[_safe_node_name(node)] = node
    if not selected_node_map:
        return 0

    return BipedPartialAnimHandler.apply_keys(
        partial_data,
        selected_node_map,
        start_frame=range_start,
        end_frame=range_end
    )


def _restore_biped_backup(bip_root, backup_bip_path):
    """Restore a full Biped backup file after a failed splice attempt."""
    if not backup_bip_path or not os.path.isfile(backup_bip_path):
        return False
    _clear_biped_animation_keys(bip_root)
    return BipedAnimHandler.load_bip(bip_root, backup_bip_path)


def _save_biped_mixer_output_to_bip(bip_root, save_path, start_frame=None, end_frame=None):
    """Save the currently visible Motion Mixer result to a BIP file."""
    if not PYMXS_AVAILABLE or bip_root is None:
        return False

    if not save_path:
        return False

    start_frame = _coerce_frame_int(start_frame)
    end_frame = _coerce_frame_int(end_frame)
    try:
        node_name = _safe_node_name(bip_root)
    except Exception:
        node_name = ""
    if not node_name:
        return False

    fwd_path = save_path.replace("\\", "/")
    if start_frame is None or end_frame is None:
        try:
            start_frame = int(rt.animationRange.start)
            end_frame = int(rt.animationRange.end)
        except Exception:
            start_frame = 0
            end_frame = 100

    ms_content = '''(
    local _saved = false
    local _bip = getNodeByName "__NODE_NAME__"
    if _bip == undefined then
    (
        format "[BipedMixerBake] target biped not found\\n"
        false
    )
    else
    (
        local _oldRange = animationRange
        local _oldMode = false
        try(_oldMode = _bip.controller.mixerMode)catch(_oldMode = false)
        try(_bip.controller.mixerMode = on)catch()
        try(animationRange = interval __START__f __END__f)catch()
        format "[BipedMixerBake] mixerModeOn=true range=__START__-__END__\\n"
        try
        (
            biped.saveBipFile _bip.controller @"__SAVE_PATH__"
            _saved = true
        )
        catch()
        try(animationRange = _oldRange)catch()
        try(_bip.controller.mixerMode = _oldMode)catch()
        format "[BipedMixerBake] save result=%\\n" _saved
        _saved
    )
)'''
    ms_content = ms_content.replace("__NODE_NAME__", node_name.replace('"', r'\"'))
    ms_content = ms_content.replace("__SAVE_PATH__", fwd_path)
    ms_content = ms_content.replace("__START__", str(int(start_frame)))
    ms_content = ms_content.replace("__END__", str(int(end_frame)))
    return _run_temp_maxscript(ms_content, "BipedMixerBake")


def _splice_biped_clip_with_mixer(bip_root, clip_bip_path, backup_bip_path,
                                  source_start, source_end,
                                  target_start, target_end,
                                  scene_start=None, scene_end=None,
                                  original_anim_start=None, original_anim_end=None):
    """
    Motion Mixer proof-of-concept splice path for full BIP animation.

    Strategy:
      1. Build a temp BIP clip already remapped into the target window using the
         existing stable "clear -> load -> move -> trim" flow.
      2. Restore the original scene animation.
      3. Ask Motion Mixer to combine the original full clip with the remapped
         clip and copy the mixdown back to the live Biped.

    This intentionally only replaces the previously unstable multi-load merge
    path when old animation must be preserved.
    """
    source_start, source_end, target_start, target_end = _resolve_apply_frame_window(
        source_start, source_end, target_start, target_end
    )
    scene_start = _coerce_frame_int(scene_start)
    scene_end = _coerce_frame_int(scene_end)
    if scene_start is None or scene_end is None:
        try:
            scene_start = int(rt.animationRange.start)
            scene_end = int(rt.animationRange.end)
        except Exception:
            scene_start = target_start
            scene_end = target_end

    effective_target_end = min(
        int(target_end),
        int(target_start) + max(0, int(source_end) - int(source_start))
    )
    original_anim_start = _coerce_frame_int(original_anim_start)
    original_anim_end = _coerce_frame_int(original_anim_end)
    if original_anim_start is None or original_anim_end is None:
        original_anim_start, original_anim_end = _get_biped_key_range(bip_root)

    node_name = _safe_node_name(bip_root)
    if not node_name:
        _safe_print("[BipedMixer] START FAILED: empty Biped node name")
        return False

    _safe_print(
        "[BipedMixer] START root={0} source={1}-{2} target={3}-{4} effective={5}-{6} "
        "scene={7}-{8} original={9}-{10} clip={11} backup={12}".format(
            node_name,
            source_start,
            source_end,
            target_start,
            target_end,
            target_start,
            effective_target_end,
            scene_start,
            scene_end,
            original_anim_start,
            original_anim_end,
            repr(clip_bip_path),
            repr(backup_bip_path)
        )
    )
    _log_biped_key_range("BipedMixer.before", bip_root)

    mapped_clip_bip_path = None
    try:
        handle, mapped_clip_bip_path = tempfile.mkstemp(
            prefix="animlib_mixer_mapped_bip_",
            suffix=".bip"
        )
        os.close(handle)

        if not _clear_biped_animation_keys(bip_root):
            raise RuntimeError("Could not clear current Biped keys for mixer mapping.")
        _safe_print("[BipedMixer] cleared scene before mapped clip build")

        if not BipedAnimHandler.load_bip(
            bip_root,
            clip_bip_path,
            start_frame=source_start,
            end_frame=source_end
        ):
            raise RuntimeError("Could not load source clip for mixer mapping.")
        _safe_print("[BipedMixer] loaded source clip for mapping")

        if not _move_all_biped_keys(bip_root, int(target_start) - int(source_start)):
            raise RuntimeError("Could not move source clip into target window.")
        _safe_print(
            "[BipedMixer] moved mapped clip offset={0}".format(
                int(target_start) - int(source_start)
            )
        )

        if not _trim_biped_keys_to_window(bip_root, target_start, effective_target_end):
            raise RuntimeError("Could not trim mapped clip to target window.")
        _safe_print(
            "[BipedMixer] trimmed mapped clip keep={0}-{1}".format(
                target_start, effective_target_end
            )
        )
        _log_biped_key_range("BipedMixer.mappedClipOnRig", bip_root)

        if not BipedAnimHandler.save_bip(bip_root, mapped_clip_bip_path):
            raise RuntimeError("Could not save mapped clip for mixer.")
        _safe_print(
            "[BipedMixer] saved mapped clip path={0}".format(repr(mapped_clip_bip_path))
        )

        if not _restore_biped_backup(bip_root, backup_bip_path):
            raise RuntimeError("Could not restore original Biped before mixer.")
        _safe_print("[BipedMixer] restored original backup before mixer")
        _log_biped_key_range("BipedMixer.afterRestoreBackup", bip_root)

        ms_content = '''(
    fn _animlibLog msg = (format "%\\n" msg)
    fn _animlibBoolString value = (if value then "true" else "false")
    fn _animlibAppendSummary summary label value =
    (
        local prefix = ""
        if summary != "" do prefix = summary + "; "
        prefix + label + "=" + value
    )
    fn _animlibProps obj =
    (
        if obj == undefined then return "undefined"
        local out = ""
        try
        (
            local p = getPropNames obj
            out = p as string
        )
        catch
        (
            try(out = (classof obj) as string)catch(out = "<?>")
        )
        out
    )
    fn _animlibAddClip track clipPath =
    (
        local clip = undefined
        local added = false
        local beforeCount = 0
        if track == undefined then return clip
        try(beforeCount = track.numClips)catch(beforeCount = 0)
        try(added = appendClip track clipPath true 5)catch()
        if not added do try(added = track.appendClip clipPath true 5)catch()
        if not added do try(added = appendClip track clipPath)catch()
        if not added do try(added = track.appendClip clipPath)catch()
        if not added do try(added = appendMaxClip track clipPath undefined 5)catch()
        if not added do try(added = track.appendMaxClip clipPath undefined 5)catch()
        if not added do try(added = addClip track clipPath)catch()
        if not added do try(added = track.addClip clipPath)catch()
        if added do
        (
            try
            (
                if track.numClips > beforeCount do clip = getClip track track.numClips
            )
            catch()
        )
        if clip == undefined do
        (
            try
            (
                if track.numClips > 0 do clip = getClip track track.numClips
            )
            catch()
        )
        clip
    )
    fn _animlibEnsureTrackgroup mixer bipRoot =
    (
        local tg = undefined
        if mixer == undefined then return tg
        try(if mixer.numTrackgroups > 0 do tg = getTrackgroup mixer 1)catch()
        if tg == undefined do try(tg = appendTrackgroup mixer bipRoot)catch()
        if tg == undefined do try(tg = appendTrackgroup mixer bipRoot.controller)catch()
        if tg == undefined do try(tg = mixer.appendTrackgroup bipRoot)catch()
        if tg == undefined do try(tg = mixer.appendTrackgroup bipRoot.controller)catch()
        if tg == undefined do try(if mixer.numTrackgroups > 0 do tg = getTrackgroup mixer 1)catch()
        tg
    )
    fn _animlibEnsureTrack tg index =
    (
        local tr = undefined
        if tg == undefined then return tr
        try(if tg.numTracks >= index do tr = getTrack8 tg index)catch()
        if tr == undefined do try(if tg.numTracks >= index do tr = getTrack tg index)catch()
        while tr == undefined do
        (
            local created = undefined
            try(if tg.insertTrack index 0 do created = true)catch()
            if created == undefined do try(if InsertTrack tg index 0 do created = true)catch()
            if created == undefined do try(created = appendTrack tg)catch()
            if created == undefined do try(created = tg.appendTrack())catch()
            if created == undefined do exit
            try(if tg.numTracks >= index do tr = getTrack8 tg index)catch()
            if tr == undefined do try(if tg.numTracks >= index do tr = getTrack tg index)catch()
            if tr == undefined do tr = created
        )
        tr
    )
    fn _animlibTrySetClipRange clip startF endF label =
    (
        if clip == undefined then return false
        _animlibLog ("[BipedMixer] " + label + " props=" + _animlibProps clip)
        try(clip.globstart = startF)catch()
        try(clip.globend = endF)catch()
        try(clip.start = startF)catch()
        try(clip.end = endF)catch()
        try(setProperty clip #start startF)catch()
        try(setProperty clip #globstart startF)catch()
        try(setProperty clip #globend endF)catch()
        try(setProperty clip #end endF)catch()
        true
    )
    local _ok = false
    local _didMixdown = false
    local _didCopy = false
    local _bip = getNodeByName "__NODE_NAME__"
    local _mx = undefined
    local _tg = undefined
    local _oldTrack = undefined
    local _newTrack = undefined
    local _oldClip = undefined
    local _newClip = undefined
    local _oldPath = @"__OLD_BIP_PATH__"
    local _newPath = @"__NEW_BIP_PATH__"
    local _summary = ""
    _animlibLog "[BipedMixer] wrapper entered"
    if _bip == undefined then
    (
        _animlibLog "[BipedMixer] target biped not found"
        false
    )
    else
    (
        try(macros.run "Animation Tools" "MotionMixer")catch()
        try(macros.run "Graph Editors" "MotionMixer")catch()
        try(_mx = _bip.transform.controller.mixer)catch()
        if _mx == undefined do try(_mx = _bip.controller.mixer)catch()
        if _mx == undefined do
        (
            try
            (
                if theMixer != undefined and theMixer.numMaxMixers() > 0 do
                    _mx = theMixer.getMaxMixer 1
            )
            catch()
        )
        _animlibLog ("[BipedMixer] mixer=" + _animlibProps _mx)
        _tg = _animlibEnsureTrackgroup _mx _bip
        _animlibLog ("[BipedMixer] trackgroup=" + _animlibProps _tg)
        _oldTrack = _animlibEnsureTrack _tg 1
        _newTrack = _animlibEnsureTrack _tg 2
        if _newTrack == undefined do _newTrack = _oldTrack
        _animlibLog ("[BipedMixer] oldTrack=" + _animlibProps _oldTrack)
        _animlibLog ("[BipedMixer] newTrack=" + _animlibProps _newTrack)
        _summary = _animlibAppendSummary _summary "mixer" (_animlibBoolString (_mx != undefined))
        _summary = _animlibAppendSummary _summary "trackgroup" (_animlibBoolString (_tg != undefined))
        _summary = _animlibAppendSummary _summary "oldTrack" (_animlibBoolString (_oldTrack != undefined))
        _summary = _animlibAppendSummary _summary "newTrack" (_animlibBoolString (_newTrack != undefined))
        _oldClip = _animlibAddClip _oldTrack _oldPath
        _animlibLog ("[BipedMixer] old clip added=" + _animlibBoolString (_oldClip != undefined))
        _newClip = _animlibAddClip _newTrack _newPath
        _animlibLog ("[BipedMixer] new clip added=" + _animlibBoolString (_newClip != undefined))
        _summary = _animlibAppendSummary _summary "oldClip" (_animlibBoolString (_oldClip != undefined))
        _summary = _animlibAppendSummary _summary "newClip" (_animlibBoolString (_newClip != undefined))
        try(_animlibLog ("[BipedMixer] oldTrack numClips=" + ((_oldTrack.numClips) as string)))catch()
        try(_animlibLog ("[BipedMixer] newTrack numClips=" + ((_newTrack.numClips) as string)))catch()
        try(_summary = _animlibAppendSummary _summary "oldTrackClips" ((_oldTrack.numClips) as string))catch()
        try(_summary = _animlibAppendSummary _summary "newTrackClips" ((_newTrack.numClips) as string))catch()
        if _oldClip != undefined do
            _animlibTrySetClipRange _oldClip __OLD_START__f __OLD_END__f "oldClip"
        if _newClip != undefined do
            _animlibTrySetClipRange _newClip __NEW_START__f __NEW_END__f "newClip"
        try
        (
            if _mx != undefined do
            (
                _mx.mixdown()
                _didMixdown = true
            )
        )
        catch()
        if not _didMixdown do
        (
            try
            (
                mixdown _mx
                _didMixdown = true
            )
            catch()
        )
        _animlibLog ("[BipedMixer] mixdown result=" + _animlibBoolString _didMixdown)
        _summary = _animlibAppendSummary _summary "mixdown" (_animlibBoolString _didMixdown)
        try
        (
            if _mx != undefined do
            (
                _mx.copyMixdownToBiped()
                _didCopy = true
            )
        )
        catch()
        if not _didCopy do
        (
            try
            (
                copyMixdownToBiped _mx
                _didCopy = true
            )
            catch()
        )
        _animlibLog ("[BipedMixer] copy back result=" + _animlibBoolString _didCopy)
        _summary = _animlibAppendSummary _summary "copyBack" (_animlibBoolString _didCopy)
        _ok = (_oldClip != undefined and _newClip != undefined and (_didMixdown or _didCopy))
        _animlibLog ("[BipedMixer] final result=" + _animlibBoolString _ok)
        _summary = _animlibAppendSummary _summary "final" (_animlibBoolString _ok)
        if not _ok do _animlibLog ("[BipedMixer] summary: " + _summary)
        _ok
    )
)'''
        ms_content = ms_content.replace("__NODE_NAME__", node_name.replace('"', r'\"'))
        ms_content = ms_content.replace("__OLD_BIP_PATH__", backup_bip_path.replace("\\", "/"))
        ms_content = ms_content.replace("__NEW_BIP_PATH__", mapped_clip_bip_path.replace("\\", "/"))
        old_mix_start = original_anim_start if original_anim_start is not None else scene_start
        old_mix_end = original_anim_end if original_anim_end is not None else scene_end
        ms_content = ms_content.replace("__OLD_START__", str(int(old_mix_start)))
        ms_content = ms_content.replace("__OLD_END__", str(int(old_mix_end)))
        ms_content = ms_content.replace("__NEW_START__", str(int(target_start)))
        ms_content = ms_content.replace("__NEW_END__", str(int(effective_target_end)))

        mixer_ok = _run_temp_maxscript(ms_content, "BipedMixer")
        _safe_print("[BipedMixer] MAXScript result={0}".format(mixer_ok))
        _log_biped_key_range("BipedMixer.afterMixer", bip_root)
        if not mixer_ok:
            raise RuntimeError("Motion Mixer MAXScript returned false.")

        mix_bake_start = original_anim_start if original_anim_start is not None else scene_start
        mix_bake_end = max(
            int(effective_target_end),
            int(original_anim_end if original_anim_end is not None else scene_end)
        )
        capture_frames = _build_biped_capture_frame_list(
            (original_anim_start, original_anim_end),
            (target_start, effective_target_end)
        )
        mixer_mode_ok = _set_biped_mixer_mode(bip_root, True)
        _safe_print(
            "[BipedMixer] mixerMode enabled for visible capture={0}".format(
                mixer_mode_ok
            )
        )
        visible_result_data = _capture_biped_visible_result(
            bip_root,
            mix_bake_start,
            mix_bake_end,
            frame_list=capture_frames
        )
        hold_frame_inserts = 0
        if (
            original_anim_end is not None and
            target_start is not None and
            int(original_anim_end) < (int(target_start) - 1)
        ):
            hold_frame_inserts += _inject_biped_hold_frame(
                visible_result_data,
                original_anim_end,
                int(target_start) - 1
            )
        visible_frame_count = 0
        try:
            for payload in (visible_result_data.get("bipeds") or {}).values():
                visible_frame_count += len((payload.get("frames") or {}).keys())
        except Exception:
            visible_frame_count = 0
        _safe_print(
            "[BipedMixer] captured visible mixer result frames={0} range={1}-{2} requestedCaptureFrames={3} holdFrameInserts={4}".format(
                visible_frame_count,
                mix_bake_start,
                mix_bake_end,
                len(capture_frames),
                hold_frame_inserts
            )
        )
        _safe_print(
            "[BipedMixer] visible target motion {0}".format(
                _describe_biped_snapshot_motion(
                    visible_result_data,
                    node_name,
                    target_start,
                    effective_target_end
                )
            )
        )
        _set_biped_mixer_mode(bip_root, False)
        if not visible_frame_count:
            raise RuntimeError("Could not capture visible Motion Mixer result.")

        if not _clear_biped_animation_keys(bip_root):
            raise RuntimeError("Could not clear Biped before applying visible mixer result.")

        applied_count = _apply_biped_visible_result(
            visible_result_data,
            bip_root
        )
        _safe_print(
            "[BipedMixer] applied visible mixer result nodes={0}".format(applied_count)
        )
        _log_biped_key_range("BipedMixer.afterVisibleBakeApply", bip_root)
        if not applied_count:
            raise RuntimeError("Could not apply captured Motion Mixer result.")

        _safe_print("[BipedMixer] SUCCESS root={0}".format(node_name))
        return True
    except Exception as e:
        _safe_print("[BipedMixer] FAILED: " + repr(e))
        restore_ok = _restore_biped_backup(bip_root, backup_bip_path)
        _safe_print("[BipedMixer] rollback result={0}".format(restore_ok))
        return False
    finally:
        for tmp_path in (mapped_clip_bip_path,):
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


def _splice_biped_clip_into_range(bip_root, clip_bip_path, backup_bip_path,
                                  source_start, source_end,
                                  target_start, target_end,
                                  scene_start=None, scene_end=None,
                                  original_anim_start=None, original_anim_end=None):
    """
    Apply a BIP clip into a target range without deleting unrelated animation.

    Workflow:
      1. Backup current motion.
      2. Clear current keys.
      3. Load the incoming clip in its saved source range.
      4. Move/trim the new clip into the requested target window.
      5. Restore old animation outside the new clip's effective target window.
    """
    source_start, source_end, target_start, target_end = _resolve_apply_frame_window(
        source_start, source_end, target_start, target_end
    )
    scene_start = _coerce_frame_int(scene_start)
    scene_end = _coerce_frame_int(scene_end)
    if scene_start is None or scene_end is None:
        try:
            scene_start = int(rt.animationRange.start)
            scene_end = int(rt.animationRange.end)
        except Exception:
            scene_start = target_start
            scene_end = target_end

    effective_target_end = min(
        int(target_end),
        int(target_start) + max(0, int(source_end) - int(source_start))
    )
    original_anim_start = _coerce_frame_int(original_anim_start)
    original_anim_end = _coerce_frame_int(original_anim_end)
    if original_anim_start is None or original_anim_end is None:
        original_anim_start, original_anim_end = _get_biped_key_range(bip_root)

    _safe_print(
        "[BipedSplice] START root={0} source={1}-{2} target={3}-{4} effective={5}-{6} "
        "scene={7}-{8} original={9}-{10} clip={11} backup={12}".format(
            _safe_node_name(bip_root),
            source_start,
            source_end,
            target_start,
            target_end,
            target_start,
            effective_target_end,
            scene_start,
            scene_end,
            original_anim_start,
            original_anim_end,
            repr(clip_bip_path),
            repr(backup_bip_path)
        )
    )
    _log_biped_key_range("BipedSplice.before", bip_root, scene_start, scene_end)

    restore_prefix_start = None
    restore_prefix_end = None
    restore_suffix_start = None
    restore_suffix_end = None
    prefix_bip_path = None
    suffix_bip_path = None

    try:
        has_original_anim = bool(
            original_anim_start is not None and original_anim_end is not None
        )
        _safe_print(
            "[BipedSplice] has_original_anim={0}".format(has_original_anim)
        )
        if has_original_anim:
            restore_prefix_start = int(original_anim_start)
            restore_prefix_end = min(int(original_anim_end), int(target_start) - 1)
            if restore_prefix_end >= restore_prefix_start:
                handle, prefix_bip_path = tempfile.mkstemp(
                    prefix="animlib_prefix_bip_",
                    suffix=".bip"
                )
                os.close(handle)
                if not BipedAnimHandler.save_bip(
                    bip_root,
                    prefix_bip_path,
                    start_frame=restore_prefix_start,
                    end_frame=restore_prefix_end
                ):
                    raise RuntimeError(
                        "Could not save original prefix BIP segment {0}-{1}.".format(
                            restore_prefix_start, restore_prefix_end
                        )
                    )
                _safe_print(
                    "[BipedSplice] saved prefix restore bip range={0}-{1} path={2}".format(
                        restore_prefix_start,
                        restore_prefix_end,
                        repr(prefix_bip_path)
                    )
                )
            else:
                restore_prefix_start = None
                restore_prefix_end = None

            restore_suffix_start = max(int(original_anim_start), int(effective_target_end) + 1)
            restore_suffix_end = int(original_anim_end)
            if restore_suffix_end >= restore_suffix_start:
                handle, suffix_bip_path = tempfile.mkstemp(
                    prefix="animlib_suffix_bip_",
                    suffix=".bip"
                )
                os.close(handle)
                if not BipedAnimHandler.save_bip(
                    bip_root,
                    suffix_bip_path,
                    start_frame=restore_suffix_start,
                    end_frame=restore_suffix_end
                ):
                    raise RuntimeError(
                        "Could not save original suffix BIP segment {0}-{1}.".format(
                            restore_suffix_start, restore_suffix_end
                        )
                    )
                _safe_print(
                    "[BipedSplice] saved suffix restore bip range={0}-{1} path={2}".format(
                        restore_suffix_start,
                        restore_suffix_end,
                        repr(suffix_bip_path)
                    )
                )
            else:
                restore_suffix_start = None
                restore_suffix_end = None

        if not _clear_biped_animation_keys(bip_root):
            raise RuntimeError("Could not clear current Biped keys.")
        _safe_print("[BipedSplice] cleared current keys")
        _log_biped_key_range("BipedSplice.afterClear", bip_root, scene_start, scene_end)

        if not BipedAnimHandler.load_bip(
            bip_root,
            clip_bip_path,
            start_frame=source_start,
            end_frame=source_end
        ):
            raise RuntimeError("Could not load incoming BIP clip.")
        _safe_print(
            "[BipedSplice] loaded incoming clip segment source={0}-{1}".format(
                source_start, source_end
            )
        )
        _log_biped_key_range("BipedSplice.afterLoadIncoming", bip_root, scene_start, scene_end)

        if not _move_all_biped_keys(bip_root, int(target_start) - int(source_start)):
            raise RuntimeError("Could not move loaded BIP keys to target range.")
        _safe_print(
            "[BipedSplice] moved incoming keys offset={0}".format(
                int(target_start) - int(source_start)
            )
        )
        _log_biped_key_range("BipedSplice.afterMove", bip_root, scene_start, scene_end)

        if not _trim_biped_keys_to_window(bip_root, target_start, effective_target_end):
            raise RuntimeError("Could not trim loaded BIP keys to target range.")
        _safe_print(
            "[BipedSplice] trimmed incoming keys keep={0}-{1}".format(
                target_start, effective_target_end
            )
        )
        _log_biped_key_range("BipedSplice.afterTrim", bip_root, scene_start, scene_end)

        if has_original_anim:
            if prefix_bip_path:
                if not BipedAnimHandler.load_bip(
                    bip_root,
                    prefix_bip_path,
                    start_frame=restore_prefix_start,
                    end_frame=restore_prefix_end
                ):
                    raise RuntimeError(
                        "Could not restore original prefix BIP segment {0}-{1}.".format(
                            restore_prefix_start, restore_prefix_end
                        )
                    )
                _safe_print(
                    "[BipedSplice] restored prefix bip range={0}-{1}".format(
                        restore_prefix_start,
                        restore_prefix_end
                    )
                )
                _log_biped_key_range("BipedSplice.afterRestorePrefix", bip_root)

            if suffix_bip_path:
                if not BipedAnimHandler.load_bip(
                    bip_root,
                    suffix_bip_path,
                    start_frame=restore_suffix_start,
                    end_frame=restore_suffix_end
                ):
                    raise RuntimeError(
                        "Could not restore original suffix BIP segment {0}-{1}.".format(
                            restore_suffix_start, restore_suffix_end
                        )
                    )
                _safe_print(
                    "[BipedSplice] restored suffix bip range={0}-{1}".format(
                        restore_suffix_start,
                        restore_suffix_end
                    )
                )
                _log_biped_key_range("BipedSplice.afterRestoreSuffix", bip_root)

        _safe_print("[BipedSplice] SUCCESS root={0}".format(_safe_node_name(bip_root)))
        return True
    except Exception as e:
        _safe_print("[BipedAnimHandler] splice clip FAILED: " + repr(e))
        restore_ok = _restore_biped_backup(bip_root, backup_bip_path)
        if not restore_ok:
            _safe_print("[BipedAnimHandler] splice rollback FAILED for: {0}".format(
                _safe_node_name(bip_root)
            ))
        return False
    finally:
        for tmp_path in (prefix_bip_path, suffix_bip_path):
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


def _describe_constraint_binding(binding, fallback_start=None, fallback_end=None):
    """Return a single-line diagnostic summary for a saved/restored constraint."""
    if not binding:
        return "none"

    cls_name = binding.get("class", "")
    targets = []
    target_frames = []
    for target in binding.get("targets", []):
        if cls_name == "Link_Constraint":
            frame = int(target.get("frame", 0))
            if target.get("world"):
                targets.append(u"World@{0}".format(frame))
            else:
                target_name = target.get("name", "")
                targets.append(u"{0}@{1}".format(target_name, frame))
            target_frames.append(frame)
        else:
            target_name = target.get("name", "")
            weight = float(target.get("weight", 100.0))
            targets.append(u"{0}(w={1})".format(target_name, weight))

    start_frame, end_frame = _frame_range_from_list(
        target_frames, fallback_start, fallback_end
    )
    return u"class={0}, range={1}-{2}, targets=[{3}]".format(
        cls_name or "?",
        start_frame if start_frame is not None else "?",
        end_frame if end_frame is not None else "?",
        u", ".join(targets) if targets else ""
    )


def _write_json_utf8(file_path, data, indent=None):
    """
    Write JSON as UTF-8 text in a way that works in both Python 2 and 3.

    Python 2's json.dump() can emit a byte str even when writing to an
    io.open(..., encoding='utf-8') text stream, which then raises:
        TypeError: write() argument 1 must be unicode, not str

    To avoid that, serialise first, then ensure we are writing a real text
    string (unicode in Py2 / str in Py3).
    """
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='replace')
    with io.open(file_path, 'w', encoding='utf-8') as f:
        f.write(text)


def _collect_output_names(container, names):
    """Append or merge node names into list/set style output containers."""
    if container is None:
        return
    ordered = [name for name in (names or []) if name]
    if not ordered:
        return
    try:
        if hasattr(container, "extend"):
            container.extend(ordered)
            return
        if hasattr(container, "update"):
            container.update(ordered)
            return
        if hasattr(container, "append"):
            for name in ordered:
                container.append(name)
    except Exception:
        pass


def _bake_animation_node_map(node_lookup, start_frame, end_frame):
    """Bake currently evaluated motion onto explicit keys for every frame."""
    if not PYMXS_AVAILABLE or not node_lookup:
        return 0

    try:
        start_frame = int(start_frame)
        end_frame = int(end_frame)
    except Exception:
        return 0
    if start_frame > end_frame:
        return 0

    nodes = [node_lookup[name] for name in sorted(node_lookup.keys()) if node_lookup.get(name) is not None]
    if not nodes:
        return 0

    baked_names = set()
    for frame in range(start_frame, end_frame + 1):
        try:
            frame_nodes = PoseHandler.capture_pose_snapshot(nodes, frame)
            if not frame_nodes:
                continue
            applied_names = []
            PoseHandler.apply_pose_snapshot(
                frame_nodes,
                frame,
                node_lookup=node_lookup,
                applied_names_out=applied_names,
                force_bake_keys=True
            )
            baked_names.update(applied_names)
        except Exception as e:
            _safe_print(
                u"[AnimManager] Dense bake failed at frame {0}: {1}".format(frame, repr(e))
            )
    if baked_names:
        _safe_print(
            u"[AnimManager] Dense baked {0} node(s) across frames {1}-{2}.".format(
                len(baked_names), start_frame, end_frame
            )
        )
    return len(baked_names)


# ---------------------------------------------------------------------------
# Helper: scene filename
# ---------------------------------------------------------------------------

def _get_max_scene_filename():
    """Return the current Max scene filename (without extension) as default clip name."""
    if not PYMXS_AVAILABLE:
        return "Untitled"
    try:
        file_path = str(rt.maxFilePath)
        file_name = str(rt.maxFileName)
        full = file_path + file_name
        if full.strip():
            base = os.path.splitext(os.path.basename(full))[0]
            return base if base else "Untitled"
    except Exception:
        pass
    return "Untitled"


# ---------------------------------------------------------------------------
# Helper: dialogs
# ---------------------------------------------------------------------------

def _show_input_dialog(title, label, default_text, parent=None):
    """Show a text-input dialog. Returns (text, ok)."""
    if not PYSIDE2_AVAILABLE:
        return default_text, True
    text, ok = QInputDialog.getText(
        parent, title, label,
        QLineEdit.Normal, default_text
    )
    return text, ok


def _show_error(title, message, parent=None):
    if not PYSIDE2_AVAILABLE:
        _safe_print("[ERROR] " + title + ": " + message)
        return
    try:
        QMessageBox.critical(parent, title, message)
    except Exception as e:
        _safe_print("[ERROR dialog failed] " + repr(e))


def _show_info(title, message, parent=None):
    if not PYSIDE2_AVAILABLE:
        _safe_print("[INFO] " + title + ": " + message)
        return
    try:
        QMessageBox.information(parent, title, message)
    except Exception as e:
        _safe_print("[INFO dialog failed] " + repr(e))


def _create_progress_dialog(title, maximum, parent=None):
    """Create a lightweight modal progress dialog when PySide2 is available."""
    if not PYSIDE2_AVAILABLE:
        return None
    try:
        dlg = QProgressDialog("", None, 0, max(1, int(maximum)), parent)
        dlg.setWindowTitle(title)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setCancelButton(None)
        dlg.setValue(0)
        dlg.show()
        QApplication.processEvents()
        return dlg
    except Exception:
        return None


def _update_progress_dialog(progress_dialog, value, label_text=None):
    """Update progress UI and keep the host app responsive."""
    if progress_dialog is None:
        return
    try:
        if label_text is not None:
            progress_dialog.setLabelText(label_text)
        progress_dialog.setValue(int(value))
        QApplication.processEvents()
    except Exception:
        pass


def _close_progress_dialog(progress_dialog):
    """Close progress dialog safely."""
    if progress_dialog is None:
        return
    try:
        progress_dialog.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Biped Handler
# ---------------------------------------------------------------------------

class BipedAnimHandler(object):
    """
    Handles Biped skeleton animation save/load.
    Uses rt.biped.saveBipFile / rt.biped.loadBipFile.
    """

    @staticmethod
    def is_biped_object(obj):
        """Return True if obj is a Biped_Object node."""
        if not PYMXS_AVAILABLE:
            return False
        try:
            return rt.classOf(obj) == rt.Biped_Object
        except Exception:
            return False

    @staticmethod
    def get_biped_root(obj):
        """
        Walk up the parent chain to find the topmost Biped_Object (COM node).
        rt.biped API functions require the COM/root node.
        """
        if not PYMXS_AVAILABLE:
            return None
        try:
            current = obj
            while True:
                parent = current.parent
                if parent is None:
                    break
                if rt.classOf(parent) == rt.Biped_Object:
                    current = parent
                else:
                    break
            return current
        except Exception as e:
            _safe_print("[BipedAnimHandler] get_biped_root error: " + repr(e))
            return None

    @staticmethod
    def get_biped_controller(bip_root):
        """
        Return the Biped controller from the root node.

        rt.biped.saveBipFile / loadBipFile accept the Biped controller object.
        In pymxs, bip_root.controller on the COM node returns that controller
        directly.  If that call fails we fall back to the node itself, which
        some Max versions also accept.
        """
        if not PYMXS_AVAILABLE:
            return None
        try:
            ctrl = bip_root.controller
            if ctrl is not None:
                return ctrl
            _safe_print("[BipedAnimHandler] bip_root.controller returned None; "
                        "falling back to node: " + repr(bip_root))
        except Exception as e:
            _safe_print("[BipedAnimHandler] get_biped_controller error: " + repr(e))
        return bip_root

    @staticmethod
    def save_bip(bip_root, save_path, start_frame=None, end_frame=None):
        """
        Save the Biped animation to a .bip file.

        Args:
            bip_root   : COM/root Biped_Object node
            save_path  : full destination path (str), must end with .bip
            start_frame: (int or None) segment start frame; None = save all
            end_frame  : (int or None) segment end frame;   None = save all
        Returns:
            True on success, False on failure

        NOTE on pymxs named-parameter syntax:
            pymxs translates Python **kwargs into MAXScript #keys arrays, NOT
            into MAXScript named (keyword) arguments.  To pass named args we
            must execute the call as a MAXScript string via rt.execute().
        """
        if not PYMXS_AVAILABLE:
            _safe_print("[BipedAnimHandler] pymxs not available - cannot save .bip")
            return False
        try:
            _safe_print("[BipedAnimHandler.save_bip] VERSION=FILEIN start={0} end={1}".format(start_frame, end_frame))
            save_dir = os.path.dirname(save_path)
            if save_dir and not os.path.isdir(save_dir):
                os.makedirs(save_dir)

            ctrl = BipedAnimHandler.get_biped_controller(bip_root)
            fwd_full = save_path.replace("\\", "/")

            if start_frame is not None and end_frame is not None:
                try:
                    scene_start = int(rt.animationRange.start)
                    scene_end = int(rt.animationRange.end)
                except Exception:
                    scene_start = None
                    scene_end = None

                # A full-range save is the safest path for 3ds Max 2020 Biped.
                # Avoid segment flags when the requested range already matches
                # the scene animation range.
                if (
                    scene_start is not None and scene_end is not None and
                    int(start_frame) == scene_start and int(end_frame) == scene_end
                ):
                    rt.biped.saveBipFile(ctrl, fwd_full)
                    _safe_print(
                        "[BipedAnimHandler] Saved full-range BIP without segment flags: {0}".format(
                            repr(save_path)
                        )
                    )
                    return True

                # ----------------------------------------------------------
                # Segment save via a temporary .ms script file.
                #
                # 3ds Max Biped saveBipFile syntax is version-sensitive here.
                # In Max 2020 the `keyPerFrame:false` form can fail with:
                # "unrecognized saveBipFile flag, got: ##keys".
                #
                # Keep the segment workflow, but try the most conservative
                # syntax first and verify the file was actually written.
                # ----------------------------------------------------------
                try:
                    node_name = str(bip_root.name)
                except Exception:
                    node_name = ""

                if node_name:
                    try:
                        if os.path.isfile(save_path):
                            os.remove(save_path)
                    except Exception:
                        pass
                    # Write a temp MAXScript file
                    tmp_ms = os.path.join(
                        os.path.dirname(save_path),
                        "__animlib_tmp_save.ms"
                    )
                    ms_content = (
                        '(\n'
                        '    local _saved = false\n'
                        '    local _oldRange = animationRange\n'
                        '    local _bip = getNodeByName "{node}"\n'
                        '    if _bip != undefined do\n'
                        '    (\n'
                        '        try(animationRange = interval {start}f {end}f)catch()\n'
                        '        try\n'
                        '        (\n'
                        '            biped.saveBipFile _bip.controller @"{path}" #saveSegment segStart:{start}f segEnd:{end}f\n'
                        '            _saved = true\n'
                        '        )\n'
                        '        catch()\n'
                        '        if not _saved do\n'
                        '        (\n'
                        '            try\n'
                        '            (\n'
                        '                biped.saveBipFile _bip.controller @"{path}" saveSegment:true segStart:{start}f segEnd:{end}f\n'
                        '                _saved = true\n'
                        '            )\n'
                        '            catch()\n'
                        '        )\n'
                        '    )\n'
                        '    try(animationRange = _oldRange)catch()\n'
                        '    _saved\n'
                        ')\n'
                    ).format(
                        node=node_name.replace('"', r'\"'),
                        path=fwd_full,
                        start=int(start_frame),
                        end=int(end_frame)
                    )
                    with open(tmp_ms, 'w') as f:
                        f.write(ms_content)

                    _safe_print("[BipedAnimHandler] tmp_ms content:\n" + ms_content)
                    _safe_print("[BipedAnimHandler] tmp_ms path: " + repr(tmp_ms))

                    # fileIn executes the script in MAXScript's own context
                    rt.fileIn(tmp_ms)

                    # Clean up temp file
                    try:
                        os.remove(tmp_ms)
                    except Exception:
                        pass

                    if not os.path.isfile(save_path):
                        _safe_print(
                            "[BipedAnimHandler] Segment save produced no file. "
                            "Requested range: {0}-{1}".format(int(start_frame), int(end_frame))
                        )
                        return False

                    _safe_print(
                        "[BipedAnimHandler] Saved segment [{0}-{1}]: {2}".format(
                            start_frame, end_frame, repr(save_path)
                        )
                    )
                else:
                    # No node name — fall back to full save
                    rt.biped.saveBipFile(ctrl, str(save_path))
                    _safe_print("[BipedAnimHandler] Saved (full, no-name fallback): " + repr(save_path))
            else:
                # Full animation save (no segment).
                rt.biped.saveBipFile(ctrl, fwd_full)
                _safe_print("[BipedAnimHandler] Saved (full): " + repr(save_path))

            return True
        except Exception as e:
            _safe_print("[BipedAnimHandler] save_bip primary path FAILED: " + repr(e))
            if start_frame is not None and end_frame is not None:
                _safe_print(
                    "[BipedAnimHandler] Segment save FAILED without full-save fallback: {0}".format(
                        repr(save_path)
                    )
                )
            _safe_print("[BipedAnimHandler] save_bip FAILED: " + repr(e))
            return False

    @staticmethod
    def load_bip(bip_root, bip_path, start_frame=None, end_frame=None):
        """
        Load a .bip file onto the given Biped root node.

        Args:
            bip_root   : COM/root Biped_Object node
            bip_path   : full path to the .bip file (str)
            start_frame: (int or None) load only from this frame; None = load all
            end_frame  : (int or None) load only up to this frame;  None = load all
        Returns:
            True on success, False on failure

        NOTE on pymxs named-parameter syntax:
            Same issue as save_bip — use rt.execute() for named args.
        """
        if not PYMXS_AVAILABLE:
            _safe_print("[BipedAnimHandler] pymxs not available - cannot load .bip")
            return False
        if not os.path.isfile(bip_path):
            _safe_print("[BipedAnimHandler] .bip file not found: " + repr(bip_path))
            return False
        try:
            ctrl = BipedAnimHandler.get_biped_controller(bip_root)
            fwd_full = bip_path.replace("\\", "/")

            if start_frame is not None and end_frame is not None:
                try:
                    scene_start = int(rt.animationRange.start)
                    scene_end = int(rt.animationRange.end)
                except Exception:
                    scene_start = None
                    scene_end = None

                # Keep full-range root-only .bip apply on the safest Max 2020
                # path. When the requested range already matches the current
                # scene range, do not call segment-load syntax at all.
                if (
                    scene_start is not None and scene_end is not None and
                    int(start_frame) == scene_start and int(end_frame) == scene_end
                ):
                    rt.biped.loadBipFile(ctrl, fwd_full)
                    _safe_print(
                        "[BipedAnimHandler] Loaded full-range BIP without segment flags: {0}".format(
                            repr(bip_path)
                        )
                    )
                    return True

                # ----------------------------------------------------------
                # Segment load strategy:
                # Same problem as save_bip with named args.
                # loadBipFile loads the whole file, then we set the timeline
                # to [start, end] so only that range is active.
                # For a true segment load, temporarily set animationRange,
                # load, then restore — matches how Max's own UI works.
                # ----------------------------------------------------------
                try:
                    node_name = str(bip_root.name)
                except Exception:
                    node_name = ""

                if node_name:
                    tmp_ms = os.path.join(
                        os.path.dirname(bip_path),
                        "__animlib_tmp_load.ms"
                    )
                    # All named args MUST be on the same line in MAXScript.
                    # Use the 'f' frame suffix for time values (same reason as
                    # save_bip — bare integers are ticks, not frames).
                    ms_content = (
                        '(\n'
                        '    local _loaded = false\n'
                        '    local _oldRange = animationRange\n'
                        '    local _bip = getNodeByName "{node}"\n'
                        '    if _bip != undefined do\n'
                        '    (\n'
                        '        try(animationRange = interval {start}f {end}f)catch()\n'
                        '        try\n'
                        '        (\n'
                        '            biped.loadBipFile _bip.controller @"{path}"\n'
                        '            _loaded = true\n'
                        '        )\n'
                        '        catch()\n'
                        '        if not _loaded do\n'
                        '        (\n'
                        '            try\n'
                        '            (\n'
                        '                biped.loadBipFile _bip.controller @"{path}" loadSegment:true segStart:{start}f segEnd:{end}f\n'
                        '                _loaded = true\n'
                        '            )\n'
                        '            catch()\n'
                        '        )\n'
                        '    )\n'
                        '    try(animationRange = _oldRange)catch()\n'
                        '    _loaded\n'
                        ')\n'
                    ).format(
                        node=node_name.replace('"', r'\"'),
                        path=fwd_full,
                        start=int(start_frame),
                        end=int(end_frame)
                    )
                    with open(tmp_ms, 'w') as f:
                        f.write(ms_content)

                    _safe_print(
                        "[BipedAnimHandler] Segment load request range={0}-{1} scene_before={2}-{3}".format(
                            int(start_frame),
                            int(end_frame),
                            scene_start,
                            scene_end
                        )
                    )
                    loaded = bool(rt.fileIn(tmp_ms))

                    try:
                        os.remove(tmp_ms)
                    except Exception:
                        pass

                    if not loaded:
                        raise RuntimeError(
                            "Biped segment load returned false for range {0}-{1}".format(
                                int(start_frame), int(end_frame)
                            )
                        )

                    _safe_print(
                        "[BipedAnimHandler] Loaded segment [{0}-{1}]: {2}".format(
                            start_frame, end_frame, repr(bip_path)
                        )
                    )
                else:
                    rt.biped.loadBipFile(ctrl, str(bip_path))
                    _safe_print("[BipedAnimHandler] Loaded (full, no-name fallback): " + repr(bip_path))
            else:
                # Full animation load (no segment).
                rt.biped.loadBipFile(ctrl, fwd_full)
                _safe_print("[BipedAnimHandler] Loaded (full): " + repr(bip_path))

            return True
        except Exception as e:
            _safe_print("[BipedAnimHandler] load_bip FAILED: " + repr(e))
            return False


class BipedPartialAnimHandler(object):
    """Save/apply selected Biped nodes as partial frame-range animation."""

    @staticmethod
    def _is_biped_root_node(node):
        """Return True when *node* is the top COM/root object of a Biped."""
        if not PYMXS_AVAILABLE or node is None:
            return False
        try:
            root = BipedAnimHandler.get_biped_root(node)
            if root is None:
                return False
            return _safe_runtime_identity(root) == _safe_runtime_identity(node)
        except Exception:
            return False

    @staticmethod
    def _collect_biped_com_key_frames(node, start_frame, end_frame):
        """
        Collect COM/root key frames from the dedicated horizontal / vertical /
        turning controls. Regular controller walks often miss these tracks.
        """
        frames = set()
        if not BipedPartialAnimHandler._is_biped_root_node(node):
            return frames

        ctrl = BipedAnimHandler.get_biped_controller(node)
        if ctrl is None:
            return frames

        getter_specs = (
            ("horizontal", "getHorizontalControl"),
            ("vertical", "getVerticalControl"),
            ("turn", "getTurnControl"),
        )
        for label, getter_name in getter_specs:
            sub_ctrl = None
            try:
                getter = getattr(rt.biped, getter_name)
                sub_ctrl = getter(ctrl)
            except Exception:
                sub_ctrl = None
            if sub_ctrl is None:
                continue

            before_count = len(frames)
            try:
                GenericAnimHandler._collect_controller_key_times(
                    sub_ctrl, start_frame, end_frame, frames
                )
            except Exception:
                pass

            try:
                key_count = int(rt.numKeys(sub_ctrl))
            except Exception:
                key_count = 0
            for i in range(1, key_count + 1):
                try:
                    frame = int(rt.getKeyTime(sub_ctrl, i))
                    if int(start_frame) <= frame <= int(end_frame):
                        frames.add(frame)
                except Exception:
                    pass

            if len(frames) != before_count:
                _diag_print(
                    u"[BipedPartialAnimHandler][SaveDiag] COM {0} keys {1}: {2}".format(
                        label, _safe_node_name(node), _format_frame_list(sorted(frames))
                    )
                )

        return frames

    @staticmethod
    def _get_node_key_frames(node, start_frame, end_frame, bake_keys=False):
        """
        Return sparse key frames for one partial Biped node.

        COM/root nodes need an extra pass over Biped's dedicated
        horizontal/vertical/turn controls; if those cannot be queried, fall
        back to dense frame sampling for that node only so root motion still
        saves correctly.
        """
        if bake_keys:
            return list(range(int(start_frame), int(end_frame) + 1))

        frames = set(
            GenericAnimHandler._get_object_key_frames(node, start_frame, end_frame)
        )
        frames.update(
            BipedPartialAnimHandler._collect_biped_com_key_frames(
                node, start_frame, end_frame
            )
        )

        if not frames and BipedPartialAnimHandler._is_biped_root_node(node):
            frames.update(range(int(start_frame), int(end_frame) + 1))
            _safe_print(
                u"[BipedPartialAnimHandler] COM key detection fell back to dense "
                u"sampling for {0} in range {1}-{2}.".format(
                    _safe_node_name(node), int(start_frame), int(end_frame)
                )
            )

        return sorted(
            frame for frame in frames
            if int(start_frame) <= int(frame) <= int(end_frame)
        )

    @staticmethod
    def _get_direct_biped_children(node):
        """Return direct child nodes that belong to the same Biped."""
        children = []
        if not PYMXS_AVAILABLE or node is None:
            return children
        try:
            for child in list(node.children):
                if BipedAnimHandler.is_biped_object(child):
                    children.append(child)
        except Exception:
            pass
        return children

    @staticmethod
    def _biped_name_family_tokens(node):
        """Return limb family tokens inferred from a standard Biped node name."""
        name = _safe_node_name(node).lower()
        family_specs = (
            ("arm", ("clavicle", "upperarm", "forearm", "hand")),
            ("leg", ("thigh", "calf", "foot", "toe")),
            ("finger", ("finger", "thumb", "phalange")),
            ("spine", ("spine", "neck", "head")),
            ("tail", ("tail", "ponytail")),
        )
        for family_name, tokens in family_specs:
            for token in tokens:
                if token in name:
                    return family_name, set(tokens)
        return None, set()

    @staticmethod
    def _get_named_limb_chain(node):
        """
        Expand one Biped node to a named limb chain based on standard Biped
        bone labels such as UpperArm/Forearm/Hand or Thigh/Calf/Foot.
        """
        family_name, tokens = BipedPartialAnimHandler._biped_name_family_tokens(node)
        if not family_name or not tokens:
            return []

        def _matches_family(candidate):
            candidate_name = _safe_node_name(candidate).lower()
            for token in tokens:
                if token in candidate_name:
                    return True
            return False

        ordered = []
        seen = set()

        current = node
        while current is not None:
            if not BipedAnimHandler.is_biped_object(current):
                break
            if BipedPartialAnimHandler._is_biped_root_node(current):
                break
            if not _matches_family(current):
                break
            current_key = _safe_runtime_identity(current)
            if current_key not in seen:
                ordered.insert(0, current)
                seen.add(current_key)
            try:
                current = current.parent
            except Exception:
                current = None

        def _walk_descendants(parent_node):
            matching_children = []
            for child in BipedPartialAnimHandler._get_direct_biped_children(parent_node):
                if _matches_family(child):
                    matching_children.append(child)

            if len(matching_children) > 1:
                # Finger chains frequently branch under the hand. Keep limb mode
                # focused on a single contiguous chain instead of exploding to
                # every branch.
                matching_children.sort(key=lambda child: _safe_node_name(child).lower())
                matching_children = matching_children[:1]

            for child in matching_children:
                child_key = _safe_runtime_identity(child)
                if child_key in seen:
                    continue
                ordered.append(child)
                seen.add(child_key)
                _walk_descendants(child)

        if ordered:
            _walk_descendants(ordered[-1])
        return ordered

    @staticmethod
    def _get_linear_limb_chain(node):
        """
        Expand one Biped node to its local linear limb chain.

        This is intentionally conservative:
        - walk upward only through single-child Biped ancestors
        - walk downward only through single-child Biped descendants
        - stop before COM/root and before branching children like fingers
        """
        if not BipedAnimHandler.is_biped_object(node):
            return [node]
        if BipedPartialAnimHandler._is_biped_root_node(node):
            return [node]

        named_chain = BipedPartialAnimHandler._get_named_limb_chain(node)
        if named_chain:
            return named_chain

        head = node
        while True:
            try:
                parent = head.parent
            except Exception:
                parent = None
            if parent is None:
                break
            if not BipedAnimHandler.is_biped_object(parent):
                break
            if BipedPartialAnimHandler._is_biped_root_node(parent):
                break
            parent_children = BipedPartialAnimHandler._get_direct_biped_children(parent)
            if len(parent_children) != 1:
                break
            head = parent

        chain = [head]
        current = head
        while True:
            direct_children = BipedPartialAnimHandler._get_direct_biped_children(current)
            if len(direct_children) != 1:
                break
            current = direct_children[0]
            chain.append(current)

        return chain

    @staticmethod
    def expand_selected_nodes(selected_objects, expand_limb_chains=False):
        """Optionally expand selected Biped nodes to their local limb chains."""
        expanded = []
        seen = set()

        for obj in selected_objects or []:
            if expand_limb_chains and BipedAnimHandler.is_biped_object(obj):
                candidates = BipedPartialAnimHandler._get_linear_limb_chain(obj)
            else:
                candidates = [obj]

            for candidate in candidates:
                candidate_key = _safe_runtime_identity(candidate)
                if candidate_key in seen:
                    continue
                seen.add(candidate_key)
                expanded.append(candidate)

        return expanded

    @staticmethod
    def split_selected_nodes(selected_objects):
        """
        Split selected Biped nodes into:
          - full_roots: root-only selections that should keep legacy full .bip save
          - partial_roots: grouped selected child/root nodes for partial animx save
        """
        full_roots = {}
        grouped = {}

        for obj in selected_objects or []:
            if not BipedAnimHandler.is_biped_object(obj):
                continue

            root = BipedAnimHandler.get_biped_root(obj)
            if root is None:
                continue

            root_key = _safe_runtime_identity(root)
            payload = grouped.setdefault(root_key, {
                "root": root,
                "root_name": _safe_node_name(root),
                "nodes": [],
                "node_keys": set(),
            })

            node_key = _safe_runtime_identity(obj)
            if node_key in payload["node_keys"]:
                continue
            payload["node_keys"].add(node_key)
            payload["nodes"].append(obj)

        partial_roots = {}
        for root_key, payload in grouped.items():
            root = payload["root"]
            nodes = list(payload.get("nodes") or [])
            nodes.sort(key=lambda node: _safe_node_name(node).lower())
            payload["nodes"] = nodes

            root_name = payload["root_name"]
            is_root_only = (
                len(nodes) == 1 and
                _safe_runtime_identity(nodes[0]) == _safe_runtime_identity(root)
            )
            if is_root_only:
                full_roots[root_key] = root
            else:
                partial_roots[root_name] = {
                    "root": root,
                    "root_name": root_name,
                    "nodes": nodes,
                }

        return full_roots, partial_roots

    @staticmethod
    def capture_keys(partial_roots, start_frame, end_frame, bake_keys=False):
        """Capture sparse keyed snapshots for selected Biped nodes."""
        if not PYMXS_AVAILABLE:
            return {}

        result = {
            "version": 1,
            "start_frame": int(start_frame),
            "end_frame": int(end_frame),
            "bipeds": {},
        }

        total_root_count = 0
        total_node_count = 0
        for root_name in sorted((partial_roots or {}).keys()):
            payload = partial_roots.get(root_name) or {}
            nodes = list(payload.get("nodes") or [])
            if not nodes:
                continue

            node_names = [_safe_node_name(node) for node in nodes]
            object_frame_map = {}
            frame_object_map = {}
            frames_data = {}
            for node in nodes:
                node_name = _safe_node_name(node)
                key_frames = BipedPartialAnimHandler._get_node_key_frames(
                    node, start_frame, end_frame, bake_keys=bake_keys
                )
                if not key_frames:
                    _safe_print(
                        u"[BipedPartialAnimHandler] Node has no detected keys in range {0}-{1}: {2}".format(
                            int(start_frame), int(end_frame), node_name
                        )
                    )
                    continue
                if bake_keys:
                    channel_frames = {}
                else:
                    channel_frames = GenericAnimHandler._get_object_channel_key_frames(
                        node, start_frame, end_frame
                    )
                object_frame_map[node_name] = {
                    "object": node,
                    "frames": key_frames,
                    "channel_frames": channel_frames,
                }
                for frame in key_frames:
                    frame_object_map.setdefault(frame, []).append(node)

            for frame in sorted(frame_object_map.keys()):
                try:
                    frame_nodes = PoseHandler.capture_pose_snapshot(frame_object_map[frame], frame)
                    if frame_nodes:
                        for node in frame_object_map[frame]:
                            node_name = _safe_node_name(node)
                            node_payload = frame_nodes.get(node_name)
                            if node_payload is None:
                                continue
                            channel_frames = (
                                object_frame_map.get(node_name, {}).get("channel_frames") or {}
                            )
                            keyed_channels = GenericAnimHandler._get_frame_keyed_channels(
                                channel_frames, frame
                            )
                            if keyed_channels:
                                node_payload["keyed_channels"] = keyed_channels
                        frames_data[str(frame)] = {"nodes": frame_nodes}
                except Exception as e:
                    _safe_print(
                        u"[BipedPartialAnimHandler] Capture failed for root {0} at frame {1}: {2}".format(
                            root_name, frame, repr(e)
                        )
                    )

            if not frames_data:
                _safe_print(
                    u"[BipedPartialAnimHandler] No frame data captured for root: {0}".format(root_name)
                )
                continue

            result["bipeds"][root_name] = {
                "root_name": root_name,
                "node_names": node_names,
                "frames": frames_data,
                "object_keyframes": dict(
                    (name, payload["frames"]) for name, payload in object_frame_map.items()
                ),
            }
            total_root_count += 1
            total_node_count += len(node_names)
            _safe_print(
                u"[BipedPartialAnimHandler] Captured root {0}: {1} node(s), {2} frame(s).".format(
                    root_name, len(node_names), len(frames_data)
                )
            )

        if not result["bipeds"]:
            return {}

        _safe_print(
            u"[BipedPartialAnimHandler] Captured {0} root(s), {1} node(s) in range {2}-{3}.".format(
                total_root_count, total_node_count, int(start_frame), int(end_frame)
            )
        )
        return result

    @staticmethod
    def apply_keys(partial_data, selected_node_map, start_frame=None, end_frame=None,
                   applied_names_out=None):
        """Apply partial Biped data only to matching currently selected nodes."""
        if not PYMXS_AVAILABLE:
            return 0

        bipeds = (partial_data or {}).get("bipeds") or {}
        if not bipeds:
            return 0

        selected_biped_node_map = {}
        for node_name, node in (selected_node_map or {}).items():
            if BipedAnimHandler.is_biped_object(node):
                selected_biped_node_map[node_name] = node

        if not selected_biped_node_map:
            return 0

        applied_names = set()
        selected_names = set(selected_biped_node_map.keys())
        apply_session_state = {}
        partial_source_start, partial_source_end, partial_target_start, partial_target_end = (
            _resolve_apply_frame_window(
                (partial_data or {}).get("start_frame"),
                (partial_data or {}).get("end_frame"),
                start_frame,
                end_frame
            )
        )
        effective_target_end = min(
            int(partial_target_end),
            int(partial_target_start) + max(0, int(partial_source_end) - int(partial_source_start))
        )

        for root_name in sorted(bipeds.keys()):
            payload = bipeds.get(root_name) or {}
            file_node_names = set(payload.get("node_names") or [])
            apply_names = file_node_names & selected_names
            if not apply_names:
                _safe_print(
                    u"[BipedPartialAnimHandler] Root {0} has no selected matching nodes — skipped.".format(
                        root_name
                    )
                )
                continue

            clear_root = selected_biped_node_map.get(root_name)
            selected_root_nodes = []
            if clear_root is None:
                for node_name in sorted(apply_names):
                    node = selected_biped_node_map.get(node_name)
                    if node is None:
                        continue
                    maybe_root = BipedAnimHandler.get_biped_root(node)
                    if maybe_root is not None:
                        clear_root = maybe_root
                        break
            if clear_root is not None:
                root_identity = _safe_runtime_identity(clear_root)
                for node in selected_biped_node_map.values():
                    try:
                        if _safe_runtime_identity(BipedAnimHandler.get_biped_root(node)) == root_identity:
                            selected_root_nodes.append(node)
                    except Exception:
                        pass
            should_clear_full_root = False
            if clear_root is not None:
                all_root_nodes = _collect_biped_nodes_for_root(clear_root)
                selected_root_keys = set(
                    _safe_runtime_identity(node) for node in selected_root_nodes if node is not None
                )
                all_root_keys = set(
                    _safe_runtime_identity(node) for node in all_root_nodes if node is not None
                )
                should_clear_full_root = bool(all_root_keys) and selected_root_keys.issuperset(all_root_keys)
            if should_clear_full_root:
                _delete_biped_keys_in_window(
                    clear_root,
                    partial_target_start,
                    effective_target_end
                )

            frames_data = payload.get("frames") or {}
            for frame_str in sorted(frames_data.keys(), key=lambda value: int(value)):
                source_frame = int(frame_str)
                target_frame = _map_source_frame_to_target(
                    source_frame,
                    partial_source_start,
                    partial_target_start,
                    partial_target_end
                )
                if target_frame is None:
                    continue
                frame_payload = frames_data.get(frame_str) or {}
                nodes_payload = frame_payload.get("nodes") or {}
                filtered_nodes = dict(
                    (node_name, node_data)
                    for node_name, node_data in nodes_payload.items()
                    if node_name in apply_names
                )
                if not filtered_nodes:
                    continue

                frame_applied_names = []
                try:
                    PoseHandler.apply_pose_snapshot(
                        filtered_nodes,
                        target_frame,
                        node_lookup=selected_biped_node_map,
                        applied_names_out=frame_applied_names,
                        session_state=apply_session_state,
                        direct_root_keys=True
                    )
                    applied_names.update(frame_applied_names)
                except Exception as e:
                    _safe_print(
                        u"[BipedPartialAnimHandler] Apply failed for root {0} frame {1}: {2}".format(
                            root_name, frame_str, repr(e)
                        )
                    )

            _safe_print(
                u"[BipedPartialAnimHandler] Applied root {0} to {1} selected node(s).".format(
                    root_name, len(apply_names)
                )
            )

        _collect_output_names(applied_names_out, sorted(applied_names))
        return len(applied_names)


# ---------------------------------------------------------------------------
# Generic Animation Handler
# ---------------------------------------------------------------------------

class GenericAnimHandler(object):
    """
    Handles animation save/apply for non-Biped scene nodes
    (BoneGeometry, Dummy, Point, helpers, etc.) via per-frame world-transform
    sampling.

    Save  → captures world Matrix3 at every integer frame in the given range
            and serialises it as a JSON-compatible list of four row-vectors.
    Apply → recreates Auto Key keys at each saved frame by assigning
            node.transform inside pymxs.animate(True) / pymxs.attime(frame).
    """

    @staticmethod
    def get_anim_range():
        """Return (start_frame, end_frame) from the 3ds Max animation range."""
        try:
            start, end = max_utils.get_timeline_range()
            return start, end
        except Exception:
            return 0, 100

    @staticmethod
    def _rows_to_matrix3(rows):
        """Build a native Matrix3 from serialized row data."""
        if not rows or len(rows) != 4:
            return None
        try:
            return rt.Matrix3(
                rt.Point3(float(rows[0][0]), float(rows[0][1]), float(rows[0][2])),
                rt.Point3(float(rows[1][0]), float(rows[1][1]), float(rows[1][2])),
                rt.Point3(float(rows[2][0]), float(rows[2][1]), float(rows[2][2])),
                rt.Point3(float(rows[3][0]), float(rows[3][1]), float(rows[3][2]))
            )
        except Exception:
            return None

    @staticmethod
    def _collect_controller_key_times(ctrl, start_frame, end_frame,
                                      out_frames=None, visited=None):
        """Recursively collect keyed frames from a controller tree."""
        if ctrl is None:
            return set() if out_frames is None else out_frames
        if out_frames is None:
            out_frames = set()
        if visited is None:
            visited = set()

        ctrl_key = _safe_runtime_identity(ctrl)
        if ctrl_key in visited:
            return out_frames
        visited.add(ctrl_key)

        try:
            key_count = int(rt.numKeys(ctrl))
        except Exception:
            key_count = 0

        for i in range(1, key_count + 1):
            try:
                key_time = rt.getKeyTime(ctrl, i)
                frame = int(key_time)
                if start_frame <= frame <= end_frame:
                    out_frames.add(frame)
            except Exception:
                pass

        # Link Constraint switch frames are critical sparse events, but some
        # scenes do not expose them consistently through numKeys/getKeyTime.
        if PoseHandler._controller_class_name(ctrl) == "Link_Constraint":
            try:
                target_count = int(ctrl.getNumTargets())
            except Exception:
                try:
                    target_count = int(rt.getNumTargets(ctrl))
                except Exception:
                    target_count = 0
            for i in range(1, target_count + 1):
                try:
                    frame = int(PoseHandler._get_constraint_target_frame(ctrl, i))
                    if start_frame <= frame <= end_frame:
                        out_frames.add(frame)
                except Exception:
                    pass

        try:
            sub_count = int(rt.getNumSubControllers(ctrl))
        except Exception:
            sub_count = 0

        for i in range(1, sub_count + 1):
            try:
                sub = rt.getSubController(ctrl, i)
            except Exception:
                sub = None
            GenericAnimHandler._collect_controller_key_times(
                sub, start_frame, end_frame, out_frames, visited
            )

        return out_frames

    @staticmethod
    def _get_object_key_frames(obj, start_frame, end_frame):
        """
        Return sparse key frames for one generic object.

        We collect keys from:
        - transform controller
        - position / rotation / scale controllers
        - constraint-driven controllers discovered by PoseHandler
        - upstream driver nodes (scene parent + constraint targets)

        The last point is critical for constrained objects: many constraint
        controllers do not own meaningful authored keys themselves, because the
        visible motion is driven by animated targets. If we only inspect the
        constrained node's own controllers, it appears to have "no keys" and we
        fall back to dense full-frame sampling during save. By recursively
        inheriting sparse keys from its drivers, we can preserve the original
        sparse timing and avoid baking on apply.
        """
        def _collect_link_constraint_frames(node, out_frames):
            """Collect sparse keys from Link Constraint internals."""
            if node is None:
                return
            ctrl = None
            try:
                ctrl = PoseHandler._get_primary_constraint_controller(node.controller)
            except Exception:
                ctrl = None
            if ctrl is None:
                return

            out_frames.add(int(start_frame))
            GenericAnimHandler._collect_controller_key_times(
                ctrl, start_frame, end_frame, out_frames
            )
            for prop_name in ("position", "rotation", "scale"):
                sub_ctrl = PoseHandler._get_link_constraint_param_controller(ctrl, prop_name)
                if sub_ctrl is not None:
                    GenericAnimHandler._collect_controller_key_times(
                        sub_ctrl, start_frame, end_frame, out_frames
                    )

        def _collect_object_frames(node, out_frames, visited_nodes, include_upstream=True):
            if node is None:
                return

            node_key = _safe_runtime_identity(node)
            if node_key in visited_nodes:
                return
            visited_nodes.add(node_key)

            controllers = []
            try:
                controllers.append(node.controller)
            except Exception:
                pass

            for prop_name in ("position", "rotation", "scale"):
                ctrl = PoseHandler._get_property_controller(node, prop_name)
                if ctrl is not None:
                    controllers.append(ctrl)

            for ctrl in PoseHandler._get_constraint_driven_controllers(node).values():
                if ctrl is not None:
                    controllers.append(ctrl)

            for ctrl in controllers:
                GenericAnimHandler._collect_controller_key_times(
                    ctrl, start_frame, end_frame, out_frames
                )

            if include_upstream:
                upstream_nodes = []
                try:
                    if node.parent is not None:
                        upstream_nodes.append(node.parent)
                except Exception:
                    pass

                for target in PoseHandler._get_constraint_target_nodes(node):
                    if target is not None:
                        upstream_nodes.append(target)

                for upstream in upstream_nodes:
                    _collect_object_frames(upstream, out_frames, visited_nodes, True)

        frames = set()
        root_constraint_binding = PoseHandler._capture_constraint_binding(obj)
        include_upstream = True
        try:
            transform_binding = (root_constraint_binding or {}).get("transform") or {}
            if transform_binding.get("class") == "Link_Constraint":
                _collect_link_constraint_frames(obj, frames)
                _diag_print(
                    u"[GenericAnimHandler][SaveDiag] LinkConstraintFrames {0}: {1}".format(
                        _safe_node_name(obj),
                        _format_frame_list(frames)
                    )
                )
                return sorted(
                    frame for frame in frames
                    if int(start_frame) <= int(frame) <= int(end_frame)
                )
            include_upstream = True
        except Exception:
            include_upstream = True
        _collect_object_frames(obj, frames, set(), include_upstream)
        return sorted(frames)

    @staticmethod
    def _collect_direct_controller_key_times(ctrl, start_frame, end_frame):
        """Collect only direct keys on a controller, excluding subcontrollers."""
        frames = set()
        if ctrl is None:
            return frames
        try:
            key_count = int(rt.numKeys(ctrl))
        except Exception:
            key_count = 0

        for i in range(1, key_count + 1):
            try:
                frame = int(rt.getKeyTime(ctrl, i))
                if start_frame <= frame <= end_frame:
                    frames.add(frame)
            except Exception:
                pass
        return frames

    @staticmethod
    def _get_object_channel_key_frames(obj, start_frame, end_frame):
        """
        Return per-channel keyed frames for regular object PRS preservation.

        This keeps track-bar key colors intact by remembering which transform
        channels were originally keyed on each frame.
        """
        if BipedPartialAnimHandler._is_biped_root_node(obj):
            com_channel_frames = {
                "position": set(),
                "rotation": set(),
            }
            ctrl = BipedAnimHandler.get_biped_controller(obj)
            if ctrl is not None:
                getter_specs = (
                    ("position", "getHorizontalControl"),
                    ("position", "getVerticalControl"),
                    ("rotation", "getTurnControl"),
                )
                for channel_name, getter_name in getter_specs:
                    sub_ctrl = None
                    try:
                        getter = getattr(rt.biped, getter_name)
                        sub_ctrl = getter(ctrl)
                    except Exception:
                        sub_ctrl = None
                    if sub_ctrl is None:
                        continue
                    try:
                        GenericAnimHandler._collect_controller_key_times(
                            sub_ctrl, start_frame, end_frame, com_channel_frames[channel_name]
                        )
                    except Exception:
                        pass
                    try:
                        key_count = int(rt.numKeys(sub_ctrl))
                    except Exception:
                        key_count = 0
                    for i in range(1, key_count + 1):
                        try:
                            frame = int(rt.getKeyTime(sub_ctrl, i))
                            if int(start_frame) <= frame <= int(end_frame):
                                com_channel_frames[channel_name].add(frame)
                        except Exception:
                            pass
            return dict(
                (channel_name, sorted(frames))
                for channel_name, frames in com_channel_frames.items()
                if frames
            )

        channel_frames = {
            "transform": set(),
            "position": set(),
            "rotation": set(),
            "scale": set(),
        }

        try:
            transform_ctrl = obj.controller
        except Exception:
            transform_ctrl = None
        channel_frames["transform"] = GenericAnimHandler._collect_direct_controller_key_times(
            transform_ctrl, start_frame, end_frame
        )

        link_transform_ctrl = PoseHandler._get_primary_constraint_controller(transform_ctrl)
        if PoseHandler._controller_class_name(link_transform_ctrl) == "Link_Constraint":
            for channel_name in ("position", "rotation", "scale"):
                sub_ctrl = PoseHandler._get_link_constraint_param_controller(
                    link_transform_ctrl, channel_name
                )
                channel_frames[channel_name] = set(
                    GenericAnimHandler._collect_controller_key_times(
                        sub_ctrl, start_frame, end_frame
                    )
                )
            return dict(
                (channel_name, sorted(frames))
                for channel_name, frames in channel_frames.items()
                if frames
            )

        for channel_name, prop_name in (
            ("position", "position"),
            ("rotation", "rotation"),
            ("scale", "scale"),
        ):
            ctrl = PoseHandler._get_property_controller(obj, prop_name)
            channel_frames[channel_name] = set(
                GenericAnimHandler._collect_controller_key_times(
                    ctrl, start_frame, end_frame
                )
            )

        return dict(
            (channel_name, sorted(frames))
            for channel_name, frames in channel_frames.items()
            if frames
        )

    @staticmethod
    def _get_frame_keyed_channels(channel_frames, frame):
        """Return which transform channels are keyed at one frame."""
        keyed = []
        for channel_name in ("transform", "position", "rotation", "scale"):
            frames = channel_frames.get(channel_name) or []
            if int(frame) in frames:
                keyed.append(channel_name)
        return keyed

    @staticmethod
    def _apply_world_transform_key(node, frame, rows):
        """
        Apply one world-space transform key to *node* at *frame*.

        We intentionally nest `attime` outside `animate(True)` to match the
        pattern already proven reliable in PoseHandler.
        """
        if node is None:
            return False

        import pymxs

        native_tm = GenericAnimHandler._rows_to_matrix3(rows)
        if native_tm is None:
            return False

        try:
            with pymxs.attime(frame):
                with pymxs.animate(True):
                    node.transform = native_tm
            return True
        except Exception:
            pass

        # Fallback: write PRS channels explicitly if full transform assignment
        # is rejected by this node/controller type.
        try:
            with pymxs.attime(frame):
                with pymxs.animate(True):
                    node.position = native_tm.pos
                    node.rotation = native_tm.rotation
                    node.scale = native_tm.scale
            return True
        except Exception:
            return False

    @staticmethod
    def capture_keys(objects, start_frame, end_frame, bake_keys=False):
        """
        Sample the world transform every integer frame for each node in
        *objects*.

        Args:
            objects     : iterable of pymxs scene nodes (non-Biped)
            start_frame : int – first frame to sample (inclusive)
            end_frame   : int – last frame to sample (inclusive)

        Returns:
            dict keyed by node name suitable for the "objects" section of
            generic_keys.json::

                {
                    "<node_name>": {
                        "node_class":  "BoneGeometry",
                        "start_frame": 0,
                        "end_frame":   100,
                        "frames": {
                            "0":   {"world_tm": [[r1x,r1y,r1z], ...]},
                            "1":   {...},
                            ...
                        }
                    }
                }
        """
        if not PYMXS_AVAILABLE:
            return {}

        object_names = []
        object_frame_map = {}
        frames_data = {}
        zero_key_objects = []

        for obj in objects:
            obj_name = _safe_node_name(obj)
            if bake_keys:
                key_frames = list(range(int(start_frame), int(end_frame) + 1))
                channel_frames = {}
            else:
                key_frames = GenericAnimHandler._get_object_key_frames(
                    obj, start_frame, end_frame
                )
                if not key_frames:
                    zero_key_objects.append(obj_name)
                    continue
                channel_frames = GenericAnimHandler._get_object_channel_key_frames(
                    obj, start_frame, end_frame
                )
            object_names.append(obj_name)
            object_frame_map[obj_name] = {
                "object": obj,
                "frames": key_frames,
                "channel_frames": channel_frames,
            }
            _diag_print(
                u"[GenericAnimHandler][SaveDiag] Object {0}: sparseFrames={1} range={2}-{3}".format(
                    obj_name,
                    _format_frame_list(key_frames),
                    key_frames[0] if key_frames else "?",
                    key_frames[-1] if key_frames else "?"
                )
            )
            if channel_frames:
                _diag_print(
                    u"[GenericAnimHandler][SaveDiag] ObjectChannels {0}: transform=[{1}] position=[{2}] rotation=[{3}] scale=[{4}]".format(
                        obj_name,
                        _format_frame_list(channel_frames.get("transform", [])),
                        _format_frame_list(channel_frames.get("position", [])),
                        _format_frame_list(channel_frames.get("rotation", [])),
                        _format_frame_list(channel_frames.get("scale", []))
                    )
                )

        frame_object_map = {}
        for obj_name, payload in object_frame_map.items():
            obj = payload["object"]
            for frame in payload["frames"]:
                frame_object_map.setdefault(frame, []).append(obj)

        if zero_key_objects:
            preview = u", ".join(zero_key_objects[:20])
            _safe_print(
                u"[GenericAnimHandler] Objects with no detected controller keys ({0} shown/{1} total): {2}".format(
                    min(len(zero_key_objects), 20), len(zero_key_objects), preview
                )
            )
            if len(zero_key_objects) > 20:
                _safe_print(u"[GenericAnimHandler] ... more zero-key objects omitted from log.")

        for frame in sorted(frame_object_map.keys()):
            try:
                frame_nodes = PoseHandler.capture_pose_snapshot(
                    frame_object_map[frame], frame
                )
                if frame_nodes:
                    for obj in frame_object_map[frame]:
                        obj_name = _safe_node_name(obj)
                        node_payload = frame_nodes.get(obj_name)
                        if node_payload is None:
                            continue
                        channel_frames = (
                            object_frame_map.get(obj_name, {}).get("channel_frames") or {}
                        )
                        keyed_channels = GenericAnimHandler._get_frame_keyed_channels(
                            channel_frames, frame
                        )
                        if keyed_channels:
                            node_payload["keyed_channels"] = keyed_channels
                    frames_data[str(frame)] = {"nodes": frame_nodes}
            except Exception as e:
                _safe_print(
                    u"[GenericAnimHandler] Capture failed at frame {0}: {1}".format(
                        frame, repr(e)
                    )
                )

        if not frames_data:
            _safe_print(
                u"[GenericAnimHandler] No sparse controller keys detected in range {0}-{1}; "
                u"falling back to dense sampling for all {2} object(s).".format(
                    start_frame, end_frame, len(objects)
                )
            )
            object_names = [_safe_node_name(obj) for obj in objects]
            object_frame_map = {}
            for obj in objects:
                object_frame_map[_safe_node_name(obj)] = {
                    "object": obj,
                    "frames": list(range(start_frame, end_frame + 1)),
                }

            frame_object_map = {}
            for obj_name, payload in object_frame_map.items():
                obj = payload["object"]
                for frame in payload["frames"]:
                    frame_object_map.setdefault(frame, []).append(obj)

            for frame in sorted(frame_object_map.keys()):
                try:
                    frame_nodes = PoseHandler.capture_pose_snapshot(
                        frame_object_map[frame], frame
                    )
                    if frame_nodes:
                        frames_data[str(frame)] = {"nodes": frame_nodes}
                except Exception as e:
                    _safe_print(
                        u"[GenericAnimHandler] Dense capture failed at frame {0}: {1}".format(
                            frame, repr(e)
                        )
                    )

        if not frames_data:
            _safe_print(u"[GenericAnimHandler] Capture produced no frame data after sparse+dense attempts.")
            return {}

        _safe_print(
            u"[GenericAnimHandler] Captured {0} frame(s) for {1} object(s).".format(
                len(frames_data), len(object_names)
            )
        )
        preview = u", ".join(object_names[:20])
        if preview:
            _safe_print(
                u"[GenericAnimHandler] Saved generic object names ({0} shown/{1} total): {2}".format(
                    min(len(object_names), 20), len(object_names), preview
                )
            )
        if len(object_names) > 20:
            _safe_print(u"[GenericAnimHandler] ... more generic object names omitted from log.")
        keyframe_preview = [
            u"{0}:{1}".format(name, len(payload["frames"]))
            for name, payload in sorted(object_frame_map.items())
        ]
        if keyframe_preview:
            _diag_print(
                u"[GenericAnimHandler] Generic saved key counts ({0} shown/{1} objects): {2}".format(
                    min(len(keyframe_preview), 20),
                    len(keyframe_preview),
                    u", ".join(keyframe_preview[:20])
                )
            )
            if len(keyframe_preview) > 20:
                _diag_print(u"[GenericAnimHandler] ... more generic key counts omitted from log.")

        constraint_bindings = PoseHandler.capture_constraint_bindings(
            objects, clip_start=start_frame, clip_end=end_frame
        )
        for obj_name in sorted(object_names):
            binding_map = constraint_bindings.get(obj_name, {})
            if not binding_map:
                _diag_print(
                    u"[GenericAnimHandler][SaveDiag] Constraint {0}: (none)".format(obj_name)
                )
                continue
            frame_list = object_frame_map.get(obj_name, {}).get("frames", [])
            obj_start, obj_end = _frame_range_from_list(frame_list, start_frame, end_frame)
            for slot_name, binding in sorted(binding_map.items()):
                _diag_print(
                    u"[GenericAnimHandler][SaveDiag] Constraint {0}.{1}: {2}".format(
                        obj_name,
                        slot_name,
                        _describe_constraint_binding(binding, obj_start, obj_end)
                    )
                )

        return {
            "version": 3,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "object_names": object_names,
            "frames": frames_data,
            "constraint_bindings": constraint_bindings,
            "object_keyframes": dict(
                (name, payload["frames"]) for name, payload in object_frame_map.items()
            ),
        }

    @staticmethod
    def apply_keys(generic_data, selected_node_map, parent_widget=None, show_error=None,
                   start_frame=None, end_frame=None, applied_names_out=None):
        """
        Apply keyframe data to matching scene nodes (strict intersection).

        Intersection rule:
          - Objects in the file that are NOT in *selected_node_map* → silently skipped.
          - Names in *selected_node_map* that have no data in the file → silently skipped.
          - Only the intersection receives new keys.

        Args:
            generic_data   : full dict loaded from generic_keys.json
                             {"version": 1, "objects": {...}}
            selected_node_map : dict[str, node] – currently selected scene nodes,
                                keyed by their safe node names

        Returns:
            Number of nodes successfully written (int).
        """
        if not PYMXS_AVAILABLE:
            return 0

        import pymxs

        version = int(generic_data.get("version", 1))

        # ------------------------------------------------------------------
        # Version 2: frame-centric pose snapshots (reuses PoseHandler logic)
        # ------------------------------------------------------------------
        if version >= 2 and "frames" in generic_data:
            frames_data = generic_data.get("frames", {})
            if not frames_data:
                return 0

            selected_names = set(selected_node_map.keys())
            file_names = set(generic_data.get("object_names", []))
            if not file_names:
                for frame_payload in frames_data.values():
                    file_names.update((frame_payload.get("nodes") or {}).keys())

            selected_preview = u", ".join(sorted(selected_names)[:20])
            file_preview = u", ".join(sorted(file_names)[:20])
            apply_preview = u", ".join(sorted(file_names & selected_names)[:20])
            if file_preview:
                _safe_print(
                    u"[GenericAnimHandler] File generic names ({0} shown/{1} total): {2}".format(
                        min(len(file_names), 20), len(file_names), file_preview
                    )
                )
            if selected_preview:
                _safe_print(
                    u"[GenericAnimHandler] Selected generic names ({0} shown/{1} total): {2}".format(
                        min(len(selected_names), 20), len(selected_names), selected_preview
                    )
                )
            if apply_preview:
                _safe_print(
                    u"[GenericAnimHandler] Matched generic names ({0} shown/{1} total): {2}".format(
                        min(len(file_names & selected_names), 20),
                        len(file_names & selected_names),
                        apply_preview
                    )
                )
            else:
                _safe_print(u"[GenericAnimHandler] Matched generic names: (none)")

            apply_names = file_names & selected_names
            skip_not_sel = file_names - selected_names
            skip_not_file = selected_names - file_names

            constraint_bindings = generic_data.get("constraint_bindings", {}) or {}
            object_keyframes = generic_data.get("object_keyframes", {}) or {}
            incoming_start_map = {}
            incoming_end_map = {}
            default_start, default_end = _frame_range_from_list(
                frames_data.keys(),
                generic_data.get("start_frame", 0),
                generic_data.get("end_frame", generic_data.get("start_frame", 0))
            )
            default_start = int(default_start)
            default_end = int(default_end)
            clip_source_start, clip_source_end, clip_target_start, clip_target_end = (
                _resolve_apply_frame_window(
                    default_start,
                    default_end,
                    start_frame,
                    end_frame
                )
            )
            for node_name in apply_names:
                frames = object_keyframes.get(node_name) or []
                if frames:
                    try:
                        incoming_start_map[node_name] = int(min(frames))
                        incoming_end_map[node_name] = int(max(frames))
                    except Exception:
                        incoming_start_map[node_name] = default_start
                        incoming_end_map[node_name] = default_end
                else:
                    incoming_start_map[node_name] = default_start
                    incoming_end_map[node_name] = default_end
            incoming_target_start_map = {}
            incoming_target_end_map = {}
            for node_name in apply_names:
                incoming_target_start = _map_source_frame_to_target(
                    incoming_start_map.get(node_name, default_start),
                    clip_source_start,
                    clip_target_start,
                    clip_target_end
                )
                incoming_target_end = _map_source_frame_to_target(
                    incoming_end_map.get(node_name, default_start),
                    clip_source_start,
                    clip_target_start,
                    clip_target_end
                )
                if incoming_target_start is not None:
                    incoming_target_start_map[node_name] = incoming_target_start
                if incoming_target_end is None and incoming_target_start is not None:
                    incoming_target_end = clip_target_end
                if incoming_target_end is not None:
                    incoming_target_end_map[node_name] = incoming_target_end

            _diag_print(
                u"[GenericAnimHandler][ApplyDiag] Clip frame range: source={0}-{1}, target={2}-{3}, savedFrameCount={4}".format(
                    clip_source_start,
                    clip_source_end,
                    clip_target_start,
                    clip_target_end,
                    len(frames_data)
                )
            )
            for node_name in sorted(apply_names):
                saved_frames = object_keyframes.get(node_name) or []
                _diag_print(
                    u"[GenericAnimHandler][ApplyDiag] Object {0}: savedFrames={1} sourceRange={2}-{3} targetRange={4}-{5}".format(
                        node_name,
                        _format_frame_list(saved_frames),
                        incoming_start_map.get(node_name, default_start),
                        incoming_end_map.get(node_name, default_end),
                        incoming_target_start_map.get(node_name, "(skip)"),
                        incoming_target_end_map.get(node_name, "(skip)")
                    )
                )
                binding = constraint_bindings.get(node_name) or {}
                if not binding:
                    _diag_print(
                        u"[GenericAnimHandler][ApplyDiag] Constraint {0}: (none)".format(node_name)
                    )
                else:
                    for slot_name, slot_binding in sorted(binding.items()):
                        _diag_print(
                            u"[GenericAnimHandler][ApplyDiag] Constraint {0}.{1}: {2}".format(
                                node_name,
                                slot_name,
                                _describe_constraint_binding(
                                    slot_binding,
                                    incoming_target_start_map.get(node_name, clip_target_start),
                                    incoming_target_end_map.get(node_name, clip_target_end)
                                )
                            )
                        )
            if constraint_bindings:
                binding_subset = {}
                for node_name in apply_names:
                    binding = constraint_bindings.get(node_name)
                    if (
                        binding and
                        node_name in incoming_target_start_map and
                        node_name in incoming_target_end_map
                    ):
                        binding_subset[node_name] = binding
                if binding_subset:
                    PoseHandler.ensure_constraint_bindings(
                        binding_subset,
                        node_lookup=selected_node_map,
                        incoming_start_map=incoming_target_start_map,
                        incoming_end_map=incoming_target_end_map,
                        parent_widget=parent_widget,
                        show_error=show_error
                    )

            if skip_not_sel:
                _safe_print(
                    "[GenericAnimHandler] {0} object(s) in file but not selected - skipped.".format(
                        len(skip_not_sel)))
            if skip_not_file:
                _safe_print(
                    "[GenericAnimHandler] {0} selected object(s) not in file - skipped.".format(
                        len(skip_not_file)))

            mapped_frame_keys = []
            for frame_key in sorted(frames_data.keys(), key=lambda x: int(x)):
                target_frame = _map_source_frame_to_target(
                    int(frame_key),
                    clip_source_start,
                    clip_target_start,
                    clip_target_end
                )
                if target_frame is None:
                    continue
                mapped_frame_keys.append((frame_key, target_frame))
            progress_dialog = _create_progress_dialog(
                "Applying Animation", len(mapped_frame_keys), parent_widget
            )
            applied_nodes = set()
            object_frame_counts = dict((name, 0) for name in apply_names)
            object_diagnostics = {}
            apply_session_state = {}
            try:
                for frame_index, frame_pair in enumerate(mapped_frame_keys, 1):
                    frame_str, target_frame = frame_pair
                    frame_payload = frames_data[frame_str] or {}
                    frame_nodes_all = frame_payload.get("nodes", {})
                    frame_nodes = {}
                    for node_name, node_data in frame_nodes_all.items():
                        if node_name in selected_node_map:
                            frame_nodes[node_name] = node_data

                    _update_progress_dialog(
                        progress_dialog,
                        frame_index - 1,
                        u"Applying frame {0}/{1}".format(frame_index, len(mapped_frame_keys))
                    )

                    if not frame_nodes:
                        continue

                    try:
                        source_frame = int(frame_str)
                        _diag_print(
                            u"[GenericAnimHandler][ApplyDiag] Frame {0}->{1}: fileNodes={2}, matchedNodes={3}".format(
                                source_frame,
                                target_frame,
                                len(frame_nodes_all),
                                u", ".join(sorted(frame_nodes.keys())) if frame_nodes else "(none)"
                            )
                        )
                        for diag_node_name in sorted(frame_nodes.keys()):
                            _diag_print(
                                u"[GenericAnimHandler][ApplyDiag] Frame {0}->{1}: node={2}, keyedChannels={3}".format(
                                    source_frame,
                                    target_frame,
                                    diag_node_name,
                                    u", ".join(frame_nodes[diag_node_name].get("keyed_channels", [])) or "(all)"
                                )
                            )
                        applied_names_this_frame = []
                        applied_count = PoseHandler.apply_pose_snapshot(
                            frame_nodes, target_frame,
                            node_lookup=selected_node_map,
                            applied_names_out=applied_names_this_frame,
                            diagnostics_out=object_diagnostics,
                            session_state=apply_session_state
                        )
                        if applied_count > 0:
                            _diag_print(
                                u"[GenericAnimHandler][ApplyDiag] Frame {0}->{1}: appliedNodes={2}".format(
                                    source_frame,
                                    target_frame,
                                    u", ".join(applied_names_this_frame)
                                )
                            )
                            applied_nodes.update(applied_names_this_frame)
                            for applied_name in applied_names_this_frame:
                                object_frame_counts[applied_name] = (
                                    object_frame_counts.get(applied_name, 0) + 1
                                )
                        else:
                            _diag_print(
                                u"[GenericAnimHandler][ApplyDiag] Frame {0}->{1}: no nodes applied.".format(
                                    source_frame,
                                    target_frame
                                )
                            )
                    except Exception as e:
                        _safe_print(
                            u"[GenericAnimHandler] Frame {0} apply failed: {1}".format(
                                frame_str, repr(e)
                            )
                        )
            finally:
                _update_progress_dialog(
                    progress_dialog,
                    len(mapped_frame_keys),
                    u"Finalizing animation..."
                )
                _close_progress_dialog(progress_dialog)

            success_preview_items = [
                u"{0}:{1}".format(name, count)
                for name, count in sorted(object_frame_counts.items())
                if count > 0
            ]
            zero_frame_names = [
                name for name, count in sorted(object_frame_counts.items())
                if count == 0
            ]
            if success_preview_items:
                _diag_print(
                    u"[GenericAnimHandler] Generic apply success counts ({0} shown/{1} matched): {2}".format(
                        min(len(success_preview_items), 20),
                        len(object_frame_counts),
                        u", ".join(success_preview_items[:20])
                    )
                )
                if len(success_preview_items) > 20:
                    _diag_print(u"[GenericAnimHandler] ... more success counts omitted from log.")
            else:
                _diag_print(u"[GenericAnimHandler] Generic apply success counts: (none)")

            if zero_frame_names:
                _diag_print(
                    u"[GenericAnimHandler] Generic objects with 0 applied frames ({0} shown/{1} total): {2}".format(
                        min(len(zero_frame_names), 20),
                        len(zero_frame_names),
                        u", ".join(zero_frame_names[:20])
                    )
                )
                if len(zero_frame_names) > 20:
                    _diag_print(u"[GenericAnimHandler] ... more zero-frame generic objects omitted from log.")

            diag_names = sorted(object_diagnostics.keys())[:20]
            for diag_name in diag_names:
                diag = object_diagnostics.get(diag_name, {})
                _diag_print(
                    u"[GenericAnimHandler] Controller diag {0}: node={1}, pos={2}, rot={3}, scale={4}, prs={5}, fallback={6}, constrained={7}, biped={8}, errors={9}".format(
                        diag_name,
                        diag.get("node_class", ""),
                        diag.get("position_ctrl", ""),
                        diag.get("rotation_ctrl", ""),
                        diag.get("scale_ctrl", ""),
                        diag.get("prs_frames", 0),
                        diag.get("transform_fallback_frames", 0),
                        diag.get("constrained_frames", 0),
                        diag.get("biped_frames", 0),
                        diag.get("error_frames", 0)
                    )
                )
                _diag_print(
                    u"[GenericAnimHandler][ApplyDiag] Frames {0}: applied=[{1}] constrained=[{2}] prs=[{3}] fallback=[{4}]".format(
                        diag_name,
                        _format_frame_list(diag.get("applied_frames", [])),
                        _format_frame_list(diag.get("constrained_frame_list", [])),
                        _format_frame_list(diag.get("prs_frame_list", [])),
                        _format_frame_list(diag.get("fallback_frame_list", []))
                    )
                )
                if diag.get("last_error"):
                    _diag_print(
                        u"[GenericAnimHandler] Controller diag last error for {0}: {1}".format(
                            diag_name, diag.get("last_error")
                        )
                    )
            if len(object_diagnostics) > 20:
                _diag_print(u"[GenericAnimHandler] ... more controller diagnostics omitted from log.")

            _collect_output_names(applied_names_out, sorted(applied_nodes))
            return len(applied_nodes)

        # ------------------------------------------------------------------
        # Version 1: object-centric world_tm data (legacy fallback)
        # ------------------------------------------------------------------
        objects_data = generic_data.get("objects", {})
        if not objects_data:
            return 0

        selected_names = set(selected_node_map.keys())
        file_names     = set(objects_data.keys())
        apply_names    = file_names & selected_names
        skip_not_sel   = file_names - selected_names
        skip_not_file  = selected_names - file_names

        if skip_not_sel:
            _safe_print(
                "[GenericAnimHandler] {0} object(s) in file but not selected — skipped.".format(
                    len(skip_not_sel)))
        if skip_not_file:
            _safe_print(
                "[GenericAnimHandler] {0} selected object(s) not in file — skipped.".format(
                    len(skip_not_file)))

        applied = 0
        all_saved_frames = []
        for obj_payload in objects_data.values():
            all_saved_frames.extend((obj_payload.get("frames") or {}).keys())
        default_start, default_end = _frame_range_from_list(
            all_saved_frames,
            generic_data.get("start_frame", 0),
            generic_data.get("end_frame", generic_data.get("start_frame", 0))
        )
        default_start = int(default_start)
        default_end = int(default_end)
        clip_source_start, clip_source_end, clip_target_start, clip_target_end = (
            _resolve_apply_frame_window(
                default_start,
                default_end,
                start_frame,
                end_frame
            )
        )
        for name in sorted(apply_names):
            node = selected_node_map.get(name)
            if node is None:
                _safe_print(u"[GenericAnimHandler] Node not found in scene: {0}".format(name))
                continue

            frames_dict = objects_data[name].get("frames", {})
            frame_count = 0
            for frame_str in sorted(frames_dict.keys(), key=lambda x: int(x)):
                fdata = frames_dict[frame_str]
                try:
                    source_frame = int(frame_str)
                    target_frame = _map_source_frame_to_target(
                        source_frame,
                        clip_source_start,
                        clip_target_start,
                        clip_target_end
                    )
                    if target_frame is None:
                        continue
                    rows  = fdata["world_tm"]
                    if GenericAnimHandler._apply_world_transform_key(node, target_frame, rows):
                        frame_count += 1
                    else:
                        _safe_print(
                            u"[GenericAnimHandler] Frame {0} for '{1}' could not be applied.".format(
                                frame_str, name)
                        )
                except Exception as e:
                    _safe_print(u"[GenericAnimHandler] Frame {0} for '{1}': {2}".format(
                        frame_str, name, repr(e)))

            try:
                rt.redrawViews()
            except Exception:
                pass

            _safe_print(u"[GenericAnimHandler] Applied {0} frame(s) to: {1}".format(
                frame_count, name))
            if frame_count > 0:
                applied += 1

        if applied:
            _collect_output_names(applied_names_out, sorted(apply_names))
        return applied


# ---------------------------------------------------------------------------
# AnimManager  (main dispatcher)
# ---------------------------------------------------------------------------

class AnimManager(object):
    """
    Central animation manager / dispatcher.

    Currently supports:
        Biped (.bip) via BipedAnimHandler
        Pose  (.json) via PoseHandler

    Designed for easy extension:
        - Add XAFAnimHandler and wire it into save_animation / apply_animation.
        - Frame range (start_frame / end_frame) parameters are already accepted
          by save_animation and apply_animation and passed through to
          BipedAnimHandler.  Expose them in the UI when segment save/load
          is needed; the underlying MAXScript implementation is already in place.
    """

    # ------------------------------------------------------------------ #
    #  Save Animation  (unified: Biped + Generic → .animx package)       #
    # ------------------------------------------------------------------ #

    @classmethod
    def get_anim_range(cls):
        """Return the current scene animation range for UI helpers."""
        return GenericAnimHandler.get_anim_range()

    @classmethod
    def save_animation(cls, target_folder, parent_widget=None,
                       start_frame=None, end_frame=None,
                       clip_name=None, comment=u"", bake_keys=False,
                       expand_biped_limb=False, animation_mode="local"):
        """Facade entry: delegates animation-save workflow to `animation_asset_ops.py`."""
        return _save_animation_op(
            cls, target_folder, parent_widget,
            start_frame, end_frame,
            PYMXS_AVAILABLE, rt,
            _show_error, _show_input_dialog, _safe_print,
            _get_max_scene_filename, _sanitize_filename,
            clip_name=clip_name, comment=comment, bake_keys=False,
            expand_biped_limb=expand_biped_limb,
            animation_mode=animation_mode
        )

    @classmethod
    def _save_animx(cls, selected_objects, target_folder, clip_name,
                    start_frame, end_frame, parent_widget, comment=u"", bake_keys=False,
                    expand_biped_limb=False, animation_mode="local"):
        """
        Internal: build and write a .animx ZIP package to target_folder.

        Separates selected_objects into:
          - Biped roots (deduplicated by root node) → one .bip per skeleton
          - Generic nodes                           → sampled world-transform keys

        Frame-range semantics
          start_frame/end_frame = None  → Biped: full save (saveBipFile, no segment);
                                          Generic: sample full rt.animationRange.
          start_frame/end_frame = int   → both handlers receive that range.
        """
        # Resolve concrete frame range used for generic objects and manifest
        if start_frame is None or end_frame is None:
            gen_start, gen_end = GenericAnimHandler.get_anim_range()
        else:
            gen_start, gen_end = int(start_frame), int(end_frame)
        scene_start, scene_end = GenericAnimHandler.get_anim_range()

        animation_mode = text_type(animation_mode or "local").strip().lower()
        expand_limb_chains = bool(expand_biped_limb) or (animation_mode == "limb")
        selected_objects = BipedPartialAnimHandler.expand_selected_nodes(
            selected_objects,
            expand_limb_chains=expand_limb_chains
        )
        if animation_mode == "full_biped":
            normalized_selection = []
            seen_root_keys = set()
            for obj in selected_objects or []:
                if BipedAnimHandler.is_biped_object(obj):
                    root = BipedAnimHandler.get_biped_root(obj)
                    if root is None:
                        continue
                    root_key = _safe_runtime_identity(root)
                    if root_key in seen_root_keys:
                        continue
                    seen_root_keys.add(root_key)
                    normalized_selection.append(root)
                else:
                    normalized_selection.append(obj)
            selected_objects = normalized_selection

        # ---- Partition selection ----------------------------------------
        biped_roots, biped_partial_roots = BipedPartialAnimHandler.split_selected_nodes(selected_objects)
        if animation_mode != "full_biped" and (gen_start, gen_end) != (scene_start, scene_end):
            for root in biped_roots.values():
                root_name = _safe_node_name(root)
                biped_partial_roots[root_name] = {
                    "root": root,
                    "root_name": root_name,
                    "nodes": [root],
                }
            biped_roots = {}
        elif animation_mode != "full_biped" and bake_keys:
            for root in biped_roots.values():
                root_name = _safe_node_name(root)
                biped_partial_roots[root_name] = {
                    "root": root,
                    "root_name": root_name,
                    "nodes": [root],
                }
            biped_roots = {}
        generic_objects = []   # non-Biped nodes

        for obj in selected_objects:
            if BipedAnimHandler.is_biped_object(obj):
                continue
            generic_objects.append(obj)

        if not biped_roots and not biped_partial_roots and not generic_objects:
            _show_error("Nothing to Save",
                        "No supported objects found in selection.",
                        parent_widget)
            return None

        # ---- Work inside a temp directory --------------------------------
        tmp_dir = tempfile.mkdtemp(prefix="animx_save_")
        save_path = None
        manifest_bipeds   = []
        manifest_biped_partial = []
        bip_files_on_disk = {}   # root_name → (bip_filename, bip_full_path)
        biped_partial_data = {}
        generic_data      = {}

        try:
            # Save each unique Biped skeleton
            for root in biped_roots.values():
                try:
                    root_name    = _safe_node_name(root)
                    bip_filename = "biped_" + _sanitize_filename(root_name) + ".bip"
                    bip_path     = os.path.join(tmp_dir, bip_filename)
                    ok = BipedAnimHandler.save_bip(
                        root, bip_path,
                        start_frame=start_frame,
                        end_frame=end_frame
                    )
                    if ok:
                        bip_files_on_disk[root_name] = (bip_filename, bip_path)
                        manifest_bipeds.append({
                            "root_name": root_name,
                            "bip_file":  bip_filename,
                        })
                        _safe_print("[AnimManager] Biped saved: " + root_name)
                    else:
                        _safe_print("[AnimManager] Biped save FAILED: " + root_name)
                except Exception as e:
                    _safe_print("[AnimManager] Biped error: " + repr(e))

            # Save selected child/root Biped nodes as partial animation data
            if biped_partial_roots:
                biped_partial_data = BipedPartialAnimHandler.capture_keys(
                    biped_partial_roots, gen_start, gen_end, bake_keys=bake_keys
                )
                for root_name in sorted((biped_partial_data.get("bipeds") or {}).keys()):
                    entry = (biped_partial_data.get("bipeds") or {}).get(root_name) or {}
                    manifest_biped_partial.append({
                        "root_name": root_name,
                        "node_count": len(entry.get("node_names") or []),
                        "mode": "partial",
                    })

            # Capture generic keyframes
            if generic_objects:
                generic_data = GenericAnimHandler.capture_keys(
                    generic_objects, gen_start, gen_end, bake_keys=bake_keys
                )

            if not manifest_bipeds and not manifest_biped_partial and not generic_data:
                _show_error(
                    "Save Failed",
                    "No animation data could be captured.\n"
                    "Check the 3ds Max Listener for details.",
                    parent_widget
                )
                return None

            # Build manifest.json
            manifest = {
                "version":         _ANIMX_VERSION,
                "format":          "animx",
                "animation_mode":  animation_mode,
                "clip_name":       clip_name,
                "comment":         comment or u"",
                "start_frame":     gen_start,
                "end_frame":       gen_end,
                "bipeds":          manifest_bipeds,
                "biped_partial":   manifest_biped_partial,
                "generic_objects": list(generic_data.get("object_names", [])),
            }
            manifest_path = os.path.join(tmp_dir, "manifest.json")
            _write_json_utf8(manifest_path, manifest, indent=2)

            # Write generic_keys.json (omitted when empty)
            generic_path = None
            if generic_data:
                generic_path = os.path.join(tmp_dir, "generic_keys.json")
                _write_json_utf8(generic_path, generic_data)

            biped_partial_path = None
            if biped_partial_data:
                biped_partial_path = os.path.join(tmp_dir, "biped_partial_keys.json")
                _write_json_utf8(biped_partial_path, biped_partial_data)

            # Pack everything into a ZIP with .animx extension
            save_filename = _anim_asset_filename(clip_name, animation_mode, ANIMX_EXT)
            save_path = os.path.join(target_folder, save_filename)
            with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(manifest_path, "manifest.json")
                for root_name, (bip_filename, bip_path) in bip_files_on_disk.items():
                    zf.write(bip_path, bip_filename)
                if generic_path:
                    zf.write(generic_path, "generic_keys.json")
                if biped_partial_path:
                    zf.write(biped_partial_path, "biped_partial_keys.json")

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        if save_path is None:
            return None

        try:
            preview_utils.capture_asset_preview(
                save_path,
                rt=rt if PYMXS_AVAILABLE else None,
                selected_objects=selected_objects,
                safe_print=_safe_print
            )
        except Exception as exc:
            _safe_print("[Preview] Animation preview hook failed: {0}".format(repr(exc)))

        # ---- Success report ---------------------------------------------
        n_bip = len(manifest_bipeds)
        n_bip_partial = 0
        for entry in manifest_biped_partial:
            try:
                n_bip_partial += int(entry.get("node_count", 0))
            except Exception:
                pass
        n_gen = len(generic_data.get("object_names", []))
        parts = []
        if n_bip:
            parts.append("{0} Biped skeleton(s)".format(n_bip))
        if n_bip_partial:
            parts.append("{0} Biped partial node(s)".format(n_bip_partial))
        if n_gen:
            parts.append("{0} generic object(s)".format(n_gen))

        if start_frame is not None and end_frame is not None:
            range_str = " [frames {0}-{1}]".format(start_frame, end_frame)
        else:
            range_str = " [frames {0}-{1}]".format(gen_start, gen_end)

        try:
            display_path = save_path.encode('ascii', 'replace').decode('ascii')
        except Exception:
            display_path = repr(save_path)

        _show_info(
            "Animation Saved",
            "Saved {0}{1} to:\n{2}".format(
                ", ".join(parts), range_str, display_path),
            parent_widget
        )
        return save_path

    # ------------------------------------------------------------------ #
    #  Apply Animation                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def apply_animation(cls, bip_file_path, parent_widget=None,
                        start_frame=None, end_frame=None, bake_keys=False,
                        expand_biped_limb=False):
        """Facade entry: delegates animation-apply workflow to `animation_asset_ops.py`."""
        return _apply_animation_op(
            cls, bip_file_path, parent_widget,
            start_frame, end_frame,
            PYMXS_AVAILABLE, rt, ANIMX_EXT, _show_error, bake_keys=bake_keys,
            expand_biped_limb=expand_biped_limb
        )

    @classmethod
    def _apply_animx(cls, animx_path, parent_widget, start_frame=None, end_frame=None,
                     bake_keys=False, expand_biped_limb=False):
        """
        Internal: apply a .animx package to the current scene selection.

        Algorithm (strict intersection):
          1. Read manifest.json and generic_keys.json from the ZIP in-memory.
          2. Build selection sets:
               selected_names      – all selected node names
               selected_biped_roots – Biped root names reachable from selection
          3. Biped apply:
               Intersection of manifest.bipeds ∩ selected_biped_roots.
               Extract each matching .bip to a temp dir, call load_bip.
          4. Generic apply:
               Intersection of generic_keys.objects ∩ selected_names.
               Assign world transforms frame-by-frame via Auto Key.
          5. Clean up temp dir.
        """
        # ---- Read package contents (manifest + generic keys in-memory) --
        try:
            with zipfile.ZipFile(animx_path, 'r') as zf:
                names_in_zip = zf.namelist()
                manifest = json.loads(
                    zf.read("manifest.json").decode('utf-8')
                )
                generic_data = None
                biped_partial_data = None
                if "generic_keys.json" in names_in_zip:
                    generic_data = json.loads(
                        zf.read("generic_keys.json").decode('utf-8')
                    )
                    # Backward compatibility: older broken saves wrapped the
                    # version-2 generic payload inside {"version": 1, "objects": ...}.
                    wrapped = generic_data.get("objects")
                    if (
                        isinstance(wrapped, dict) and
                        "frames" in wrapped and
                        "object_names" in wrapped
                    ):
                        generic_data = wrapped
                if "biped_partial_keys.json" in names_in_zip:
                    biped_partial_data = json.loads(
                        zf.read("biped_partial_keys.json").decode('utf-8')
                    )
        except Exception as e:
            _show_error(
                "Read Failed",
                "Could not read animation package:\n" + repr(e),
                parent_widget
            )
            return False

        animation_mode = text_type(manifest.get("animation_mode") or "local").strip().lower()
        if animation_mode == "full_biped":
            start_frame = manifest.get("start_frame")
            end_frame = manifest.get("end_frame")
            _safe_print(
                "[AnimManager][TemplateApply] forcing saved range={0}-{1}".format(
                    start_frame,
                    end_frame
                )
            )

        # ---- Scene selection --------------------------------------------
        selected = list(rt.selection)
        selected = BipedPartialAnimHandler.expand_selected_nodes(
            selected,
            expand_limb_chains=(bool(expand_biped_limb) or animation_mode == "limb")
        )
        if not selected:
            _show_error(
                "No Selection",
                "Please select one or more objects in the scene before applying.",
                parent_widget
            )
            return False

        selected_node_map = {}
        for obj in selected:
            selected_node_map[_safe_node_name(obj)] = obj
        selected_names = set(selected_node_map.keys())

        # Collect unique Biped roots reachable from the selection
        selected_biped_roots = {}   # root_name → root_node
        for obj in selected:
            if BipedAnimHandler.is_biped_object(obj):
                root = BipedAnimHandler.get_biped_root(obj)
                if root is not None:
                    selected_biped_roots[_safe_node_name(root)] = root

        # ---- Biped partial apply (strict selected-node intersection) ----
        biped_partial_applied = 0
        partial_roots_in_file = set(
            (biped_partial_data.get("bipeds") or {}).keys()
        ) if biped_partial_data else set()
        partial_applied_names = set()
        if biped_partial_data:
            biped_partial_applied = BipedPartialAnimHandler.apply_keys(
                biped_partial_data,
                selected_node_map,
                start_frame=start_frame,
                end_frame=end_frame,
                applied_names_out=partial_applied_names
            )

        # ---- Legacy full-BIP apply (strict root intersection) ----------
        bip_applied      = 0
        manifest_bipeds  = manifest.get("bipeds", [])
        file_biped_names = {e["root_name"] for e in manifest_bipeds}
        apply_biped_names = (set(selected_biped_roots.keys()) & file_biped_names) - partial_roots_in_file
        clip_start = manifest.get("start_frame")
        clip_end = manifest.get("end_frame")
        clip_source_start, clip_source_end, clip_target_start, clip_target_end = (
            _resolve_apply_frame_window(
                clip_start,
                clip_end,
                start_frame,
                end_frame
            )
        )
        effective_target_end = min(
            int(clip_target_end),
            int(clip_target_start) + max(0, int(clip_source_end) - int(clip_source_start))
        )
        requires_bip_time_remap = bool(
            int(clip_target_start) != int(clip_source_start) or
            int(effective_target_end) != int(clip_source_end)
        )
        if animation_mode == "full_biped":
            requires_bip_time_remap = False
        try:
            scene_start, scene_end = GenericAnimHandler.get_anim_range()
        except Exception:
            scene_start = clip_target_start
            scene_end = clip_target_end

        skip_bip_not_sel  = len(file_biped_names - set(selected_biped_roots.keys()))
        skip_bip_not_file = len(set(selected_biped_roots.keys()) - file_biped_names)
        if skip_bip_not_sel:
            _safe_print("[AnimManager] {0} Biped(s) in file but not selected — skipped.".format(
                skip_bip_not_sel))
        if skip_bip_not_file:
            _safe_print("[AnimManager] {0} selected Biped(s) not in file — skipped.".format(
                skip_bip_not_file))

        if apply_biped_names:
            tmp_dir = tempfile.mkdtemp(prefix="animx_apply_")
            try:
                with zipfile.ZipFile(animx_path, 'r') as zf:
                    for entry in manifest_bipeds:
                        root_name = entry["root_name"]
                        if root_name not in apply_biped_names:
                            continue
                        bip_filename = entry["bip_file"]
                        zf.extract(bip_filename, tmp_dir)
                        tmp_bip = os.path.join(tmp_dir, bip_filename)
                        root    = selected_biped_roots[root_name]
                        original_anim_start, original_anim_end = _get_biped_key_range(root)
                        has_original_outside_target = bool(
                            original_anim_start is not None and
                            original_anim_end is not None and
                            (
                                int(original_anim_start) < int(clip_target_start) or
                                int(original_anim_end) > int(effective_target_end)
                            )
                        )
                        if animation_mode == "full_biped":
                            has_original_outside_target = False
                        needs_bip_splice = bool(
                            requires_bip_time_remap or has_original_outside_target
                        )
                        _safe_print(
                            "[AnimManager][FullBipApply] root={0} clip_source={1}-{2} "
                            "requested_target={3}-{4} effective_target={5}-{6} "
                            "scene={7}-{8} original={9}-{10} requires_time_remap={11} "
                            "has_original_outside_target={12} needs_splice={13} bip={14}".format(
                                root_name,
                                clip_source_start,
                                clip_source_end,
                                clip_target_start,
                                clip_target_end,
                                clip_target_start,
                                effective_target_end,
                                scene_start,
                                scene_end,
                                original_anim_start,
                                original_anim_end,
                                requires_bip_time_remap,
                                has_original_outside_target,
                                needs_bip_splice,
                                repr(tmp_bip)
                            )
                        )
                        _log_biped_key_range(
                            "AnimManager.FullBip.beforeApply",
                            root,
                            scene_start,
                            scene_end
                        )
                        if not needs_bip_splice:
                            ok = BipedAnimHandler.load_bip(
                                root,
                                tmp_bip,
                                start_frame=(
                                    clip_source_start if animation_mode == "full_biped" else None
                                ),
                                end_frame=(
                                    clip_source_end if animation_mode == "full_biped" else None
                                )
                            )
                            _safe_print(
                                "[AnimManager][FullBipApply] direct_full_load ok={0} root={1}".format(
                                    ok,
                                    root_name
                                )
                            )
                        else:
                            backup_bip = os.path.join(
                                tmp_dir,
                                "__animlib_backup_{0}.bip".format(
                                    _sanitize_filename(root_name)
                                )
                            )
                            backup_ok = BipedAnimHandler.save_bip(root, backup_bip)
                            if not backup_ok:
                                _safe_print(
                                    "[AnimManager] Biped backup FAILED before splice: {0}".format(
                                        root_name
                                    )
                                )
                                ok = False
                            else:
                                if has_original_outside_target:
                                    _safe_print(
                                        "[AnimManager][FullBipApply] splice path=BipedMixer root={0}".format(
                                            root_name
                                        )
                                    )
                                    ok = _splice_biped_clip_with_mixer(
                                        root,
                                        tmp_bip,
                                        backup_bip,
                                        clip_source_start,
                                        clip_source_end,
                                        clip_target_start,
                                        clip_target_end,
                                        scene_start=scene_start,
                                        scene_end=scene_end,
                                        original_anim_start=original_anim_start,
                                        original_anim_end=original_anim_end
                                    )
                                else:
                                    _safe_print(
                                        "[AnimManager][FullBipApply] splice path=legacyRemap root={0}".format(
                                            root_name
                                        )
                                    )
                                    ok = _splice_biped_clip_into_range(
                                        root,
                                        tmp_bip,
                                        backup_bip,
                                        clip_source_start,
                                        clip_source_end,
                                        clip_target_start,
                                        clip_target_end,
                                        scene_start=scene_start,
                                        scene_end=scene_end,
                                        original_anim_start=original_anim_start,
                                        original_anim_end=original_anim_end
                                    )
                        if ok:
                            bip_applied += 1
                            _safe_print("[AnimManager] Biped applied: " + root_name)
                            _log_biped_key_range(
                                "AnimManager.FullBip.afterApply",
                                root,
                                scene_start,
                                scene_end
                            )
                        else:
                            _safe_print("[AnimManager] Biped apply FAILED: " + root_name)
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        # ---- Generic apply (strict intersection) ------------------------
        gen_applied = 0
        generic_applied_names = set()
        if generic_data:
            gen_applied = GenericAnimHandler.apply_keys(
                generic_data,
                selected_node_map,
                parent_widget=parent_widget,
                show_error=_show_error,
                start_frame=start_frame,
                end_frame=end_frame,
                applied_names_out=generic_applied_names
            )
            if apply_biped_names:
                for root_name in sorted(apply_biped_names):
                    root = selected_biped_roots.get(root_name)
                    if root is not None:
                        _log_biped_key_range(
                            "AnimManager.FullBip.afterGenericApply",
                            root,
                            scene_start,
                            scene_end
                        )

        if bake_keys:
            bake_node_map = {}
            for node_name in partial_applied_names | generic_applied_names:
                node = selected_node_map.get(node_name)
                if node is not None:
                    bake_node_map[node_name] = node
            if apply_biped_names:
                for node_name, node in selected_node_map.items():
                    try:
                        if not BipedAnimHandler.is_biped_object(node):
                            continue
                        root = BipedAnimHandler.get_biped_root(node)
                        if root is None:
                            continue
                        if _safe_node_name(root) in apply_biped_names:
                            bake_node_map[node_name] = node
                    except Exception:
                        pass

            _, _, bake_start, bake_end = _resolve_apply_frame_window(
                clip_start,
                clip_end,
                start_frame,
                end_frame
            )
            if bake_start is not None and bake_end is not None:
                _bake_animation_node_map(bake_node_map, bake_start, bake_end)

        total = bip_applied + biped_partial_applied + gen_applied

        # ---- Error if nothing was written --------------------------------
        if total == 0:
            file_generic_names = set()
            if generic_data:
                file_generic_names.update(generic_data.get("object_names") or [])
                file_generic_names.update((generic_data.get("objects") or {}).keys())
                if not file_generic_names:
                    for frame_payload in (generic_data.get("frames") or {}).values():
                        file_generic_names.update((frame_payload.get("nodes") or {}).keys())
            partial_match_names = set()
            if biped_partial_data:
                for payload in (biped_partial_data.get("bipeds") or {}).values():
                    partial_match_names.update(payload.get("node_names") or [])
            any_match = bool(apply_biped_names) or bool(partial_match_names & selected_names) or bool(
                file_generic_names & selected_names
            )
            if not any_match:
                _show_error(
                    "No Match",
                    "None of the selected objects match the animation data in this file.\n"
                    "Make sure you select the same objects that were used when saving.",
                    parent_widget
                )
            else:
                _show_error(
                    "Apply Failed",
                    "Matched objects were found but animation could not be applied.\n"
                    "Check the 3ds Max Listener for details.",
                    parent_widget
                )
            return False

        # ---- Success report ---------------------------------------------
        parts = []
        if bip_applied:
            parts.append("{0} Biped skeleton(s)".format(bip_applied))
        if biped_partial_applied:
            parts.append("{0} Biped partial node(s)".format(biped_partial_applied))
        if gen_applied:
            parts.append("{0} generic object(s)".format(gen_applied))

        clip_name = manifest.get("clip_name", os.path.splitext(
            os.path.basename(animx_path))[0])
        _show_info(
            "Animation Applied",
            "Applied '{0}' to {1}.".format(clip_name, ", ".join(parts)),
            parent_widget
        )
        return True

    @classmethod
    def _apply_biped_animation(cls, obj, bip_path, parent_widget,
                               start_frame=None, end_frame=None, bake_keys=False):
        """Internal: apply a .bip file to a Biped object with optional frame range."""
        if not BipedAnimHandler.is_biped_object(obj):
            try:
                obj_name = str(obj.name)
            except Exception:
                obj_name = "(unknown)"
            _show_error(
                "Unsupported Object",
                "Selected object '" + obj_name + "' is not a Biped.\n"
                "Cannot apply a .bip file to a non-Biped object.",
                parent_widget
            )
            return False

        bip_root = BipedAnimHandler.get_biped_root(obj)
        if bip_root is None:
            _show_error("Error", "Could not find the Biped root (COM) node.", parent_widget)
            return False

        success = BipedAnimHandler.load_bip(
            bip_root, bip_path,
            start_frame=start_frame,
            end_frame=end_frame
        )
        if success:
            if bake_keys and start_frame is not None and end_frame is not None:
                bake_nodes = {}
                try:
                    for node in list(rt.selection):
                        if BipedAnimHandler.is_biped_object(node):
                            bake_nodes[_safe_node_name(node)] = node
                except Exception:
                    bake_nodes = {}
                _bake_animation_node_map(bake_nodes, start_frame, end_frame)
            try:
                display_path = bip_path.encode('ascii', 'replace').decode('ascii')
            except Exception:
                display_path = repr(bip_path)

            if start_frame is not None and end_frame is not None:
                msg = (
                    "Biped animation (frames {0}-{1}) loaded from:\n{2}".format(
                        start_frame, end_frame, display_path
                    )
                )
            else:
                msg = "Biped animation loaded from:\n" + display_path

            _show_info("Applied", msg, parent_widget)
            return True

        _show_error(
            "Apply Failed",
            "Failed to load Biped animation.\n"
            "Check the 3ds Max Listener for details.",
            parent_widget
        )
        return False

    # ------------------------------------------------------------------ #
    #  Pose Methods                                                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def save_pose(cls, target_folder, parent_widget=None, pose_name=None, comment=u""):
        """Facade entry: delegates pose-save workflow to `pose_ops.py`."""
        return _save_pose_op(
            target_folder, parent_widget,
            PYMXS_AVAILABLE, rt,
            _show_error, _show_info, _show_input_dialog, _safe_print,
            _get_max_scene_filename, _sanitize_filename, PoseHandler,
            pose_name=pose_name, comment=comment
        )

    @classmethod
    def apply_pose(cls, pose_file_path, parent_widget=None, biped_root_space_mode="world"):
        """Facade entry: delegates pose-apply workflow to `pose_ops.py`."""
        return _apply_pose_op(
            pose_file_path, parent_widget,
            PYMXS_AVAILABLE, _show_error, _show_info, PoseHandler,
            biped_root_space_mode=biped_root_space_mode
        )


# ---------------------------------------------------------------------------
# Pose Handler  (JSON local pose save / apply)
# ---------------------------------------------------------------------------

class PoseHandler(object):
    """
    Saves and applies local-space poses as JSON files.

    Each pose file records the position, rotation and scale of every
    selected node **in local space** so the data is rig-agnostic.

    File naming convention:  <clip_name>_pose.json
    JSON schema:
    {
        "version": 1,
        "nodes": {
            "<node_name>": {
                "pos":   [x, y, z],
                "rot":   [x, y, z, w],   -- quaternion
                "scale": [x, y, z]
            },
            ...
        }
    }
    """

    POSE_SUFFIX = "_pose.json"

    # ------------------------------------------------------------------
    #  Save
    # ------------------------------------------------------------------

    @staticmethod
    def _is_biped_node(node):
        """Return True if *node* is a Biped_Object."""
        try:
            return rt.classOf(node) == rt.Biped_Object
        except Exception:
            return False

    @staticmethod
    def _matrix3_to_rows(matrix_value):
        """Serialize a Matrix3 into four Point3 row lists."""
        try:
            return [
                [float(matrix_value.row1.x), float(matrix_value.row1.y), float(matrix_value.row1.z)],
                [float(matrix_value.row2.x), float(matrix_value.row2.y), float(matrix_value.row2.z)],
                [float(matrix_value.row3.x), float(matrix_value.row3.y), float(matrix_value.row3.z)],
                [float(matrix_value.row4.x), float(matrix_value.row4.y), float(matrix_value.row4.z)],
            ]
        except Exception:
            return None

    @staticmethod
    def _rows_to_matrix3(rows):
        """Rebuild a native Matrix3 from serialized row data."""
        if not rows or len(rows) != 4:
            return None
        try:
            return rt.Matrix3(
                rt.Point3(float(rows[0][0]), float(rows[0][1]), float(rows[0][2])),
                rt.Point3(float(rows[1][0]), float(rows[1][1]), float(rows[1][2])),
                rt.Point3(float(rows[2][0]), float(rows[2][1]), float(rows[2][2])),
                rt.Point3(float(rows[3][0]), float(rows[3][1]), float(rows[3][2]))
            )
        except Exception:
            return None

    @staticmethod
    def _resolve_saved_world_transform(node, local_tm, saved_world_tm=None,
                                       saved_world_pos=None, saved_world_rot_q=None,
                                       saved_world_scale=None):
        """
        Resolve the desired world transform and its PR components from snapshot
        data, preferring explicitly saved world-space values when present.
        """
        world_tm = None
        if saved_world_tm is not None:
            world_tm = saved_world_tm
        elif saved_world_pos is not None:
            w_rot_mat = rt.matrix3(1)
            w_rot_mat.rotation = saved_world_rot_q
            wr1 = rt.Point3(w_rot_mat.row1.x * saved_world_scale.x,
                            w_rot_mat.row1.y * saved_world_scale.x,
                            w_rot_mat.row1.z * saved_world_scale.x)
            wr2 = rt.Point3(w_rot_mat.row2.x * saved_world_scale.y,
                            w_rot_mat.row2.y * saved_world_scale.y,
                            w_rot_mat.row2.z * saved_world_scale.y)
            wr3 = rt.Point3(w_rot_mat.row3.x * saved_world_scale.z,
                            w_rot_mat.row3.y * saved_world_scale.z,
                            w_rot_mat.row3.z * saved_world_scale.z)
            world_tm = rt.matrix3(wr1, wr2, wr3, saved_world_pos)
        elif node is not None and node.parent is not None:
            world_tm = local_tm * node.parent.transform
        else:
            world_tm = local_tm

        try:
            world_pos = world_tm.pos
        except Exception:
            world_pos = saved_world_pos
        try:
            world_rot_q = world_tm.rotation
        except Exception:
            world_rot_q = saved_world_rot_q
        try:
            world_scale = world_tm.scale
        except Exception:
            world_scale = saved_world_scale

        return world_tm, world_pos, world_rot_q, world_scale

    @staticmethod
    def _offset_world_matrix(matrix_value, offset_vec):
        """Return a copy of *matrix_value* translated by *offset_vec*."""
        if matrix_value is None or offset_vec is None:
            return matrix_value
        try:
            return rt.matrix3(
                matrix_value.row1,
                matrix_value.row2,
                matrix_value.row3,
                rt.Point3(
                    float(matrix_value.row4.x) + float(offset_vec.x),
                    float(matrix_value.row4.y) + float(offset_vec.y),
                    float(matrix_value.row4.z) + float(offset_vec.z)
                )
            )
        except Exception:
            return matrix_value

    @staticmethod
    def _offset_world_point(point_value, offset_vec):
        """Return a translated Point3 copy."""
        if point_value is None or offset_vec is None:
            return point_value
        try:
            return rt.Point3(
                float(point_value.x) + float(offset_vec.x),
                float(point_value.y) + float(offset_vec.y),
                float(point_value.z) + float(offset_vec.z)
            )
        except Exception:
            return point_value

    @staticmethod
    def _offset_constraint_value(value, offset_vec):
        """Translate Point3/Matrix3 constraint outputs by *offset_vec*."""
        if value is None or offset_vec is None:
            return value
        matrix_rows = PoseHandler._matrix3_to_rows(value)
        if matrix_rows is not None:
            return PoseHandler._offset_world_matrix(value, offset_vec)
        try:
            if (
                hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z") and
                not hasattr(value, "w")
            ):
                return PoseHandler._offset_world_point(value, offset_vec)
        except Exception:
            pass
        return value

    @staticmethod
    def _to_mxs_point3(value):
        """Serialize a Point3-like value into MAXScript source."""
        if value is None:
            return None
        try:
            return "point3 {0} {1} {2}".format(
                repr(float(value.x)),
                repr(float(value.y)),
                repr(float(value.z))
            )
        except Exception:
            return None

    @staticmethod
    def _to_mxs_quat(value):
        """Serialize a quat-like value into MAXScript source."""
        if value is None:
            return None
        try:
            return "(quat {0} {1} {2} {3})".format(
                repr(float(value.x)),
                repr(float(value.y)),
                repr(float(value.z)),
                repr(float(value.w))
            )
        except Exception:
            return None

    @staticmethod
    def _set_biped_transform_component(node, transform_name, value, set_key,
                                       limb_node=None):
        """
        Apply one Biped transform component.

        Keep the direct pymxs path as the primary route because it is the most
        reliable in Max 2020. A more restrictive limb-specific path can be added
        later, but it must never block normal key application.
        """
        try:
            rt.biped.setTransform(node, rt.Name(transform_name), value, bool(set_key))
            return
        except Exception as direct_error:
            if limb_node is None:
                raise direct_error

        node_handle = int(rt.getHandleByAnim(node))
        limb_handle = int(rt.getHandleByAnim(limb_node))
        if transform_name == "pos":
            value_expr = PoseHandler._to_mxs_point3(value)
        elif transform_name == "rotation":
            value_expr = PoseHandler._to_mxs_quat(value)
        else:
            value_expr = None

        if not value_expr:
            raise RuntimeError(
                "Unsupported Biped transform payload for {0}".format(transform_name)
            )

        mxs = (
            "(\n"
            "    local _n = maxOps.getNodeByHandle {node_handle}\n"
            "    local _limb = maxOps.getNodeByHandle {limb_handle}\n"
            "    if _n == undefined or _limb == undefined then false\n"
            "    else\n"
            "    (\n"
            "        biped.setTransform _n #{transform_name} {value_expr} {set_key} limb:_limb\n"
            "        true\n"
            "    )\n"
            ")"
        ).format(
            node_handle=node_handle,
            limb_handle=limb_handle,
            transform_name=transform_name,
            value_expr=value_expr,
            set_key="true" if set_key else "false"
        )
        if not bool(rt.execute(mxs)):
            raise RuntimeError(
                "MAXScript limb setTransform failed for {0}".format(transform_name)
            )

    @staticmethod
    def _apply_biped_world_transform(node, world_tm, world_pos, world_rot_q,
                                     use_com_keying=False, force_bake_keys=False,
                                     apply_position=True, apply_rotation=True,
                                     limb_node=None, com_key_channels=None,
                                     force_component_keys=False,
                                     force_position_key=False,
                                     force_rotation_key=False):
        """
        Apply a Biped transform using Biped's world-space API instead of plain
        node.transform assignment. COM/root nodes need explicit key creation on
        their horizontal / vertical / turning tracks.
        """
        applied = False
        last_error = None
        com_key_channels = set(com_key_channels or [])

        try:
            if apply_position and world_pos is not None:
                PoseHandler._set_biped_transform_component(
                    node, "pos", world_pos,
                    (
                        (not use_com_keying) or force_bake_keys or
                        force_component_keys or force_position_key
                    )
                    , limb_node=limb_node
                )
                applied = True
        except Exception as exc:
            last_error = exc

        try:
            if apply_rotation and world_rot_q is not None:
                PoseHandler._set_biped_transform_component(
                    node, "rotation", world_rot_q,
                    (
                        (not use_com_keying) or force_bake_keys or
                        force_component_keys or force_rotation_key
                    )
                    , limb_node=limb_node
                )
                applied = True
        except Exception as exc:
            last_error = exc

        if use_com_keying and applied and not force_bake_keys and not force_component_keys:
            try:
                wants_all_channels = (not com_key_channels) or ("transform" in com_key_channels)
                copy_position = bool(
                    apply_position and (wants_all_channels or "position" in com_key_channels)
                )
                copy_rotation = bool(
                    apply_rotation and (wants_all_channels or "rotation" in com_key_channels)
                )
                if force_position_key:
                    copy_position = False
                if force_rotation_key:
                    copy_rotation = False
                if not copy_position and not copy_rotation:
                    if (not force_rotation_key) and apply_rotation and world_rot_q is not None:
                        copy_rotation = True
                    elif (not force_position_key) and apply_position and world_pos is not None:
                        copy_position = True
                if copy_position or copy_rotation:
                    node_handle = int(rt.getHandleByAnim(node))
                    rt.execute(
                        "(local _n = maxOps.getNodeByHandle {0}; "
                        "if _n != undefined do biped.setKey _n copyHor:{1} copyVer:{1} copyTrn:{2})".format(
                            node_handle,
                            "true" if copy_position else "false",
                            "true" if copy_rotation else "false"
                        )
                    )
            except Exception as exc:
                last_error = exc

        if applied:
            return True

        if apply_position:
            native_tm = PoseHandler._to_native_matrix3(world_tm)
            if native_tm is not None:
                try:
                    node.transform = native_tm
                    return True
                except Exception as exc:
                    last_error = exc

            try:
                node.transform = world_tm
                return True
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        return False

    @staticmethod
    def _to_native_matrix3(matrix_value):
        """Convert any matrix-like value to a native rt.Matrix3."""
        if matrix_value is None:
            return None
        try:
            return rt.Matrix3(
                rt.Point3(float(matrix_value.row1.x), float(matrix_value.row1.y), float(matrix_value.row1.z)),
                rt.Point3(float(matrix_value.row2.x), float(matrix_value.row2.y), float(matrix_value.row2.z)),
                rt.Point3(float(matrix_value.row3.x), float(matrix_value.row3.y), float(matrix_value.row3.z)),
                rt.Point3(float(matrix_value.row4.x), float(matrix_value.row4.y), float(matrix_value.row4.z))
            )
        except Exception:
            return None

    @staticmethod
    def _controller_class_name(ctrl):
        """Return the MAXScript class name of a controller/object."""
        if ctrl is None:
            return ""
        try:
            return str(rt.classOf(ctrl))
        except Exception:
            return ""

    @staticmethod
    def _ctrl_is_constrained(ctrl, visited=None):
        """Return True if ctrl is a constraint or a list containing one."""
        if not PYMXS_AVAILABLE or ctrl is None:
            return False
        if visited is None:
            visited = set()

        cls_name = PoseHandler._controller_class_name(ctrl)
        if not cls_name:
            return False

        ctrl_key = _safe_runtime_identity(ctrl)
        if ctrl_key in visited:
            return False
        visited.add(ctrl_key)

        constraint_classes = {
            "Position_Constraint",
            "Orientation_Constraint",
            "LookAt_Constraint",
            "Path_Constraint",
            "Surface_Constraint",
            "Attachment_Constraint",
            "Link_Constraint",
        }
        list_classes = {
            "Position_List",
            "Rotation_List",
            "Scale_List",
            "Transform_List",
        }

        if cls_name in constraint_classes or "Constraint" in cls_name:
            return True

        if cls_name in list_classes:
            try:
                count = int(rt.getNumSubControllers(ctrl))
                for i in range(1, count + 1):
                    sub = rt.getSubController(ctrl, i)
                    if PoseHandler._ctrl_is_constrained(sub, visited):
                        return True
            except Exception:
                pass

        return False

    @staticmethod
    def _get_property_controller(node, prop_name):
        """Get a node property controller safely."""
        if not PYMXS_AVAILABLE or node is None:
            return None
        try:
            return rt.getPropertyController(node.controller, rt.Name(prop_name))
        except Exception:
            pass
        try:
            prop_value = getattr(node, prop_name)
            return prop_value.controller
        except Exception:
            return None

    @staticmethod
    def _get_constraint_driven_controllers(node):
        """
        Return the node controllers that are constraint-driven.

        Keys can include: transform, position, rotation, scale.
        """
        controllers = {}
        if not PYMXS_AVAILABLE or node is None:
            return controllers

        try:
            transform_ctrl = node.controller
            if PoseHandler._ctrl_is_constrained(transform_ctrl):
                controllers["transform"] = transform_ctrl
        except Exception:
            pass

        for prop_name in ("position", "rotation", "scale"):
            ctrl = PoseHandler._get_property_controller(node, prop_name)
            if PoseHandler._ctrl_is_constrained(ctrl):
                controllers[prop_name] = ctrl

        return controllers

    @staticmethod
    def _serialize_controller_value(value):
        """Serialize a controller output value to JSON-safe data."""
        if value is None:
            return None

        matrix_rows = PoseHandler._matrix3_to_rows(value)
        if matrix_rows is not None:
            return {"kind": "matrix3", "value": matrix_rows}

        try:
            if hasattr(value, "w"):
                return {
                    "kind": "quat",
                    "value": [
                        float(value.x), float(value.y),
                        float(value.z), float(value.w)
                    ]
                }
        except Exception:
            pass

        try:
            if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
                return {
                    "kind": "point3",
                    "value": [float(value.x), float(value.y), float(value.z)]
                }
        except Exception:
            pass

        try:
            return {"kind": "float", "value": float(value)}
        except Exception:
            return None

    @staticmethod
    def _deserialize_controller_value(data):
        """Deserialize JSON-safe controller data."""
        if not data or not isinstance(data, dict):
            return None

        kind = data.get("kind")
        value = data.get("value")

        if kind == "matrix3":
            return PoseHandler._rows_to_matrix3(value)
        if kind == "quat" and value and len(value) == 4:
            return rt.quat(
                float(value[0]), float(value[1]),
                float(value[2]), float(value[3])
            )
        if kind == "point3" and value and len(value) == 3:
            return rt.Point3(float(value[0]), float(value[1]), float(value[2]))
        if kind == "float":
            try:
                return float(value)
            except Exception:
                return None
        return None

    @staticmethod
    def _get_controller_value(ctrl):
        """Read a controller's evaluated value."""
        if ctrl is None:
            return None
        try:
            return ctrl.value
        except Exception:
            pass
        try:
            return rt.getProperty(ctrl, rt.Name("value"))
        except Exception:
            return None

    @staticmethod
    def _set_controller_value(ctrl, value):
        """Write a controller value at current time and try to force a key."""
        if ctrl is None or value is None:
            return False

        try:
            rt.addNewKey(ctrl, rt.currentTime)
        except Exception:
            pass

        try:
            ctrl.value = value
            return True
        except Exception:
            pass

        try:
            rt.setProperty(ctrl, rt.Name("value"), value)
            return True
        except Exception:
            return False

    @staticmethod
    def _delete_key_at_current_time(ctrl):
        """Delete a key on *ctrl* at the current frame, if one exists."""
        if ctrl is None:
            return False

        try:
            current_frame = int(rt.currentTime)
        except Exception:
            current_frame = None
        if current_frame is None:
            return False

        deleted = False
        try:
            key_count = int(rt.numKeys(ctrl))
        except Exception:
            key_count = 0

        for i in range(key_count, 0, -1):
            try:
                key_frame = int(rt.getKeyTime(ctrl, i))
            except Exception:
                continue
            if key_frame != current_frame:
                continue
            try:
                rt.deleteKey(ctrl, i)
                deleted = True
                continue
            except Exception:
                pass
            try:
                deleteItem = getattr(ctrl, "keys", None)
                if deleteItem is not None:
                    rt.deleteItem(ctrl.keys, i)
                    deleted = True
            except Exception:
                pass

        return deleted

    @staticmethod
    def _cleanup_link_constraint_channel_keys(link_ctrl, keyed_channels):
        """
        Remove unwanted link_params channel keys at current time.

        We first let Max solve the object into the correct world pose, then
        strip any auto-authored link_params keys that were not present in the
        source animation so the track-bar colors stay faithful.
        """
        if link_ctrl is None:
            return
        keyed_channels = set(keyed_channels or [])
        for channel_name in ("position", "rotation", "scale"):
            if channel_name in keyed_channels:
                continue
            sub_ctrl = PoseHandler._get_link_constraint_param_controller(
                link_ctrl, channel_name
            )
            PoseHandler._delete_key_at_current_time(sub_ctrl)

    @staticmethod
    def _add_interpolated_key(ctrl):
        """
        Add a key at current time using the controller's evaluated value.

        This is safer for constraint controllers than writing ctrl.value back,
        because chained constraints can expose internal values that do not map
        1:1 to the final solved transform.
        """
        if ctrl is None:
            return False

        try:
            rt.addNewKey(ctrl, rt.currentTime, rt.Name("interpolate"))
            return True
        except Exception:
            pass

        try:
            rt.addNewKey(ctrl, rt.currentTime)
            return True
        except Exception:
            return False

    @staticmethod
    def _get_constraint_target_nodes_from_ctrl(ctrl, visited=None):
        """Collect direct target nodes referenced by a constraint controller."""
        targets = []
        if ctrl is None:
            return targets
        if visited is None:
            visited = set()

        ctrl_key = _safe_runtime_identity(ctrl)
        if ctrl_key in visited:
            return targets
        visited.add(ctrl_key)

        cls_name = PoseHandler._controller_class_name(ctrl)
        if not cls_name:
            return targets

        if "Constraint" in cls_name:
            num_targets = 0
            try:
                num_targets = int(ctrl.getNumTargets())
            except Exception:
                try:
                    num_targets = int(rt.getNumTargets(ctrl))
                except Exception:
                    num_targets = 0

            for i in range(1, num_targets + 1):
                target = None
                try:
                    target = ctrl.getNode(i)
                except Exception:
                    pass
                if target is None:
                    try:
                        target = rt.getNode(ctrl, i)
                    except Exception:
                        target = None
                if target is not None:
                    targets.append(target)
            return targets

        if cls_name in {"Position_List", "Rotation_List", "Scale_List", "Transform_List"}:
            try:
                count = int(rt.getNumSubControllers(ctrl))
                for i in range(1, count + 1):
                    sub = rt.getSubController(ctrl, i)
                    targets.extend(
                        PoseHandler._get_constraint_target_nodes_from_ctrl(sub, visited)
                    )
            except Exception:
                pass

        return targets

    @staticmethod
    def _get_constraint_target_nodes(node):
        """Collect unique constraint targets for the given node."""
        unique = []
        seen = set()
        for ctrl in PoseHandler._get_constraint_driven_controllers(node).values():
            for target in PoseHandler._get_constraint_target_nodes_from_ctrl(ctrl):
                if target is None:
                    continue
                key = _safe_runtime_identity(target)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(target)
        return unique

    @staticmethod
    def _get_primary_constraint_controller(ctrl, visited=None):
        """Return the concrete constraint controller inside a list/controller tree."""
        if ctrl is None:
            return None
        if visited is None:
            visited = set()

        ctrl_key = _safe_runtime_identity(ctrl)
        if ctrl_key in visited:
            return None
        visited.add(ctrl_key)

        cls_name = PoseHandler._controller_class_name(ctrl)
        if not cls_name:
            return None
        if "Constraint" in cls_name:
            return ctrl
        if cls_name in {"Position_List", "Rotation_List", "Scale_List", "Transform_List"}:
            try:
                count = int(rt.getNumSubControllers(ctrl))
            except Exception:
                count = 0
            for i in range(1, count + 1):
                try:
                    sub = rt.getSubController(ctrl, i)
                except Exception:
                    sub = None
                resolved = PoseHandler._get_primary_constraint_controller(sub, visited)
                if resolved is not None:
                    return resolved
        return None

    @staticmethod
    def _get_constraint_target_weight(ctrl, target_index):
        """Best-effort read of a target weight from a constraint controller."""
        try:
            return float(ctrl.getWeight(target_index))
        except Exception:
            pass
        try:
            return float(rt.getWeight(ctrl, target_index))
        except Exception:
            return 100.0

    @staticmethod
    def _get_constraint_target_frame(ctrl, target_index):
        """Best-effort read of a Link Constraint target frame."""
        try:
            return int(ctrl.getFrameNo(target_index))
        except Exception:
            pass
        try:
            return int(rt.getFrameNo(ctrl, target_index))
        except Exception:
            return 0

    @staticmethod
    def _get_link_constraint_param_controller(link_ctrl, prop_name):
        """Return a Link Constraint link_params sub-controller if available."""
        if link_ctrl is None:
            return None

        link_ctrl = PoseHandler._get_primary_constraint_controller(link_ctrl)
        if link_ctrl is None:
            return None
        if PoseHandler._controller_class_name(link_ctrl) != "Link_Constraint":
            return None

        link_params = None
        try:
            link_params = link_ctrl.link_params
        except Exception:
            pass
        if link_params is None:
            try:
                link_params = rt.getProperty(link_ctrl, rt.Name("link_params"))
            except Exception:
                link_params = None
        if link_params is None:
            return None

        name_candidates = (prop_name, prop_name.capitalize())
        for candidate in name_candidates:
            try:
                ctrl = rt.getPropertyController(link_params, rt.Name(candidate))
                if ctrl is not None:
                    return ctrl
            except Exception:
                pass
            try:
                prop_value = getattr(link_params, candidate)
                ctrl = prop_value.controller
                if ctrl is not None:
                    return ctrl
            except Exception:
                pass
        return None

    @staticmethod
    def _capture_constraint_binding_from_ctrl(ctrl, clip_start=None, clip_end=None):
        """Serialize the relation data of one concrete constraint controller."""
        ctrl = PoseHandler._get_primary_constraint_controller(ctrl)
        if ctrl is None:
            return None

        cls_name = PoseHandler._controller_class_name(ctrl)
        if not cls_name:
            return None

        binding = {
            "class": cls_name,
            "targets": [],
        }

        num_targets = 0
        try:
            num_targets = int(ctrl.getNumTargets())
        except Exception:
            try:
                num_targets = int(rt.getNumTargets(ctrl))
            except Exception:
                num_targets = 0

        link_targets = []
        for i in range(1, num_targets + 1):
            target = None
            try:
                target = ctrl.getNode(i)
            except Exception:
                pass
            if target is None:
                try:
                    target = rt.getNode(ctrl, i)
                except Exception:
                    target = None
            if target is None:
                continue

            if cls_name == "Link_Constraint":
                link_targets.append({
                    "name": _safe_node_name(target),
                    "frame": PoseHandler._get_constraint_target_frame(ctrl, i)
                })
            else:
                target_payload = {
                    "name": _safe_node_name(target),
                }
                target_payload["weight"] = PoseHandler._get_constraint_target_weight(ctrl, i)
                binding["targets"].append(target_payload)

        if cls_name == "Link_Constraint":
            link_targets = sorted(
                link_targets,
                key=lambda item: int(item.get("frame", 0))
            )
            binding["targets"].extend(link_targets)

        return binding

    @staticmethod
    def _capture_constraint_binding(node, clip_start=None, clip_end=None):
        """Capture constraint relation metadata for one node."""
        bindings = {}
        controllers = PoseHandler._get_constraint_driven_controllers(node)
        for slot_name, ctrl in controllers.items():
            binding = PoseHandler._capture_constraint_binding_from_ctrl(
                ctrl, clip_start=clip_start, clip_end=clip_end
            )
            if binding is not None:
                bindings[slot_name] = binding
        return bindings

    @staticmethod
    def capture_constraint_bindings(nodes, clip_start=None, clip_end=None):
        """Capture per-node constraint relation metadata for animation saves."""
        captured = {}
        for node in nodes:
            if node is None:
                continue
            try:
                node_name = _safe_node_name(node)
            except Exception:
                continue
            binding = PoseHandler._capture_constraint_binding(
                node, clip_start=clip_start, clip_end=clip_end
            )
            if binding:
                captured[node_name] = binding
        return captured

    @staticmethod
    def _build_constraint_controller(class_name):
        """Instantiate a constraint controller by MAXScript class name."""
        if not class_name:
            return None

        alias_names = {
            "Transform_List": ("transform_list",),
            "Position_List": ("position_list",),
            "Rotation_List": ("rotation_list",),
            "Scale_List": ("scale_list",),
            "PRS": ("PRS", "prs"),
            "Position_XYZ": ("Position_XYZ", "position_xyz"),
            "Euler_XYZ": ("Euler_XYZ", "euler_xyz"),
            "Bezier_Scale": ("Bezier_Scale", "bezier_scale"),
        }

        ctor_names = [class_name]
        for alias in alias_names.get(class_name, ()):
            if alias not in ctor_names:
                ctor_names.append(alias)

        for ctor_name in ctor_names:
            ctor = getattr(rt, ctor_name, None)
            if ctor is not None:
                try:
                    return ctor()
                except Exception:
                    pass

        for ctor_name in ctor_names:
            try:
                return rt.execute(ctor_name + "()")
            except Exception:
                pass

        ctor = getattr(rt, class_name, None)
        if ctor is not None:
            try:
                return ctor()
            except Exception:
                pass

        return None

    @staticmethod
    def _assign_constraint_controller(node, slot_name, ctrl):
        """Assign a newly created constraint controller to the requested slot."""
        if node is None or ctrl is None:
            return False

        try:
            if slot_name == "transform":
                node.controller = ctrl
            else:
                rt.setPropertyController(node.controller, rt.Name(slot_name), ctrl)
            return True
        except Exception:
            return False

    @staticmethod
    def _append_constraint_target(ctrl, class_name, target_node, target_payload):
        """Append one target to a newly created constraint controller."""
        if ctrl is None:
            return False

        if class_name == "Link_Constraint":
            frame_no = int(target_payload.get("frame", 0))
            if target_payload.get("world"):
                try:
                    result = ctrl.addWorld(frameNo=frame_no)
                    return bool(result or result == 0)
                except Exception:
                    try:
                        result = ctrl.addWorld(frame_no)
                        return bool(result or result == 0)
                    except Exception:
                        return False
            if target_node is None:
                return False
            try:
                return bool(ctrl.addTarget(target_node, frame_no))
            except Exception:
                try:
                    return bool(rt.addTarget(ctrl, target_node, frame_no))
                except Exception:
                    return False

        if target_node is None:
            return False
        weight = float(target_payload.get("weight", 100.0))
        try:
            ctrl.appendTarget(target_node, weight)
            return True
        except Exception:
            try:
                rt.appendTarget(ctrl, target_node, weight)
                return True
            except Exception:
                return False

    @staticmethod
    def _constraint_binding_signature(binding):
        """Return a comparable signature for a serialized/current binding."""
        if not binding:
            return None
        cls_name = binding.get("class", "")
        targets = []
        for target in binding.get("targets", []):
            if cls_name == "Link_Constraint":
                if target.get("world"):
                    targets.append(("__WORLD__", int(target.get("frame", 0))))
                else:
                    targets.append((
                        target.get("name", ""),
                        int(target.get("frame", 0))
                    ))
            else:
                targets.append((
                    target.get("name", ""),
                    float(target.get("weight", 100.0))
                ))
        return (cls_name, tuple(targets))

    @staticmethod
    def _get_slot_controller(node, slot_name):
        """Return the anim controller currently assigned to one transform slot."""
        if node is None:
            return None
        if slot_name == "transform":
            try:
                return node.controller
            except Exception:
                return None
        return PoseHandler._get_property_controller(node, slot_name)

    @staticmethod
    def _get_slot_list_class_name(slot_name):
        """Map transform slot names to their weighted list controller classes."""
        return {
            "transform": "Transform_List",
            "position": "Position_List",
            "rotation": "Rotation_List",
            "scale": "Scale_List",
        }.get(slot_name, "")

    @staticmethod
    def _is_slot_list_controller(ctrl, slot_name):
        """Return True if ctrl is already the expected weighted list class."""
        if ctrl is None:
            return False
        return (
            PoseHandler._controller_class_name(ctrl) ==
            PoseHandler._get_slot_list_class_name(slot_name)
        )

    @staticmethod
    def _get_list_count(list_ctrl):
        """Return number of layers in a list controller."""
        if list_ctrl is None:
            return 0
        try:
            return int(list_ctrl.getCount())
        except Exception:
            try:
                return int(list_ctrl.count)
            except Exception:
                return 0

    @staticmethod
    def _get_list_layer_controller(list_ctrl, index):
        """Return the concrete controller stored in one list layer."""
        if list_ctrl is None or index < 1:
            return None
        try:
            layer = list_ctrl[index]
        except Exception:
            return None
        try:
            return layer.controller
        except Exception:
            return None

    @staticmethod
    def _find_list_layer_index_by_binding(list_ctrl, binding):
        """Locate the layer index whose constraint signature matches *binding*."""
        desired_sig = PoseHandler._constraint_binding_signature(binding)
        if desired_sig is None:
            return None

        count = PoseHandler._get_list_count(list_ctrl)
        for index in range(1, count + 1):
            ctrl = PoseHandler._get_list_layer_controller(list_ctrl, index)
            current_binding = PoseHandler._capture_constraint_binding_from_ctrl(ctrl)
            if PoseHandler._constraint_binding_signature(current_binding) == desired_sig:
                return index
        return None

    @staticmethod
    def _ensure_list_controller(node, slot_name):
        """Wrap the slot in a weighted list controller if needed."""
        current_ctrl = PoseHandler._get_slot_controller(node, slot_name)
        if PoseHandler._is_slot_list_controller(current_ctrl, slot_name):
            return current_ctrl

        list_class_name = PoseHandler._get_slot_list_class_name(slot_name)
        list_ctrl = PoseHandler._build_constraint_controller(list_class_name)
        if list_ctrl is None:
            return None
        if not PoseHandler._assign_constraint_controller(node, slot_name, list_ctrl):
            return None
        return PoseHandler._get_slot_controller(node, slot_name)

    @staticmethod
    def _append_controller_to_list(list_ctrl, ctrl, layer_name=None):
        """Append a controller to a weighted list and return its new index."""
        if list_ctrl is None or ctrl is None:
            return None
        try:
            list_ctrl.available.controller = ctrl
            new_index = PoseHandler._get_list_count(list_ctrl)
            if layer_name:
                try:
                    list_ctrl.setName(new_index, layer_name)
                except Exception:
                    pass
            return new_index
        except Exception:
            return None

    @staticmethod
    def _build_offset_controller_for_slot(slot_name):
        """Create a default writable controller for one transform slot."""
        class_name = {
            "transform": "PRS",
            "position": "Position_XYZ",
            "rotation": "Euler_XYZ",
            "scale": "Bezier_Scale",
        }.get(slot_name, "")
        return PoseHandler._build_constraint_controller(class_name)

    @staticmethod
    def _ensure_transform_offset_list_layer(node):
        """
        Ensure a constrained transform slot has a writable non-constraint layer.

        Returns: (transform_list_ctrl, offset_layer_index)
        """
        current_ctrl = PoseHandler._get_slot_controller(node, "transform")
        if current_ctrl is None:
            return None, None

        if PoseHandler._is_slot_list_controller(current_ctrl, "transform"):
            layer_index = PoseHandler._find_non_constraint_list_layer(current_ctrl)
            if layer_index is not None:
                return current_ctrl, layer_index
            offset_ctrl = PoseHandler._build_offset_controller_for_slot("transform")
            if offset_ctrl is None:
                return current_ctrl, None
            layer_index = PoseHandler._append_controller_to_list(
                current_ctrl, offset_ctrl, layer_name="Pose Local Offset"
            )
            if layer_index is None:
                return current_ctrl, None
            try:
                PoseHandler._set_list_weight(current_ctrl, layer_index, rt.currentTime, 100.0)
            except Exception:
                pass
            try:
                current_ctrl.setActive(layer_index)
            except Exception:
                pass
            return current_ctrl, layer_index

        list_ctrl = PoseHandler._build_constraint_controller("Transform_List")
        if list_ctrl is None:
            _safe_print(
                u"[PoseHandler][ApplyDiag] LocalConstrained {0}.transform: failed to build Transform_List".format(
                    _safe_node_name(node)
                )
            )
            return None, None
        if not PoseHandler._assign_constraint_controller(node, "transform", list_ctrl):
            _safe_print(
                u"[PoseHandler][ApplyDiag] LocalConstrained {0}.transform: failed to assign Transform_List".format(
                    _safe_node_name(node)
                )
            )
            return None, None

        list_ctrl = PoseHandler._get_slot_controller(node, "transform")
        if list_ctrl is None:
            _safe_print(
                u"[PoseHandler][ApplyDiag] LocalConstrained {0}.transform: assigned Transform_List but controller readback failed".format(
                    _safe_node_name(node)
                )
            )
            return None, None
        base_index = PoseHandler._append_controller_to_list(
            list_ctrl, current_ctrl, layer_name="Constraint Base"
        )
        offset_ctrl = PoseHandler._build_offset_controller_for_slot("transform")
        if offset_ctrl is None:
            _safe_print(
                u"[PoseHandler][ApplyDiag] LocalConstrained {0}.transform: failed to build PRS offset controller".format(
                    _safe_node_name(node)
                )
            )
            return list_ctrl, None
        offset_index = PoseHandler._append_controller_to_list(
            list_ctrl, offset_ctrl, layer_name="Pose Local Offset"
        )
        if offset_index is None:
            _safe_print(
                u"[PoseHandler][ApplyDiag] LocalConstrained {0}.transform: failed to append PRS offset controller".format(
                    _safe_node_name(node)
                )
            )
        try:
            if base_index is not None:
                PoseHandler._set_list_weight(list_ctrl, base_index, rt.currentTime, 100.0)
            if offset_index is not None:
                PoseHandler._set_list_weight(list_ctrl, offset_index, rt.currentTime, 100.0)
        except Exception:
            pass
        try:
            if offset_index is not None:
                list_ctrl.setActive(offset_index)
        except Exception:
            pass
        return list_ctrl, offset_index

    @staticmethod
    def _set_list_weight(list_ctrl, layer_index, frame, value):
        """Set one weighted-list layer's weight at a specific frame."""
        if list_ctrl is None or layer_index is None or frame is None:
            return False
        try:
            frame = int(frame)
            value = float(value)
        except Exception:
            return False

        import pymxs

        try:
            with pymxs.attime(frame):
                with pymxs.animate(True):
                    list_ctrl.weight[layer_index] = value
            return True
        except Exception:
            return False

    @staticmethod
    def _get_list_weight(list_ctrl, layer_index):
        """Best-effort read of one weighted-list layer value."""
        if list_ctrl is None or layer_index is None:
            return None
        try:
            return float(list_ctrl.weight[layer_index])
        except Exception:
            pass
        try:
            layer = list_ctrl[layer_index]
            return float(layer.weight)
        except Exception:
            return None

    @staticmethod
    def _get_active_list_layer_index(list_ctrl):
        """Best-effort read of the active layer index."""
        if list_ctrl is None:
            return None
        try:
            return int(list_ctrl.getActive())
        except Exception:
            pass
        try:
            return int(list_ctrl.active)
        except Exception:
            return None

    @staticmethod
    def _find_non_constraint_list_layer(list_ctrl):
        """Return the first list layer index that is not a constraint."""
        if list_ctrl is None:
            return None
        count = PoseHandler._get_list_count(list_ctrl)
        for index in range(1, count + 1):
            layer_ctrl = PoseHandler._get_list_layer_controller(list_ctrl, index)
            if layer_ctrl is None:
                continue
            if not PoseHandler._ctrl_is_constrained(layer_ctrl):
                return index
        return None

    @staticmethod
    def _write_list_layer_value(list_ctrl, layer_index, value):
        """Write a value to a specific list layer controller."""
        if list_ctrl is None or layer_index is None or value is None:
            return False
        layer_ctrl = PoseHandler._get_list_layer_controller(list_ctrl, layer_index)
        if layer_ctrl is None:
            return False
        try:
            list_ctrl.setActive(layer_index)
        except Exception:
            pass
        return PoseHandler._set_controller_value(layer_ctrl, value)

    @staticmethod
    def _splice_constraint_with_existing(node, slot_name, existing_binding,
                                         new_ctrl, incoming_start):
        """
        Keep the old controller before *incoming_start*, then let the new
        constraint take over from *incoming_start* onward.
        """
        list_ctrl = PoseHandler._ensure_list_controller(node, slot_name)
        if list_ctrl is None:
            return False

        old_index = PoseHandler._find_list_layer_index_by_binding(list_ctrl, existing_binding)
        if old_index is None:
            old_index = 1 if PoseHandler._get_list_count(list_ctrl) >= 1 else None
        if old_index is None:
            return False

        new_index = PoseHandler._append_controller_to_list(
            list_ctrl, new_ctrl, layer_name="Imported Constraint"
        )
        if new_index is None:
            return False

        scene_start, _scene_end = GenericAnimHandler.get_anim_range()
        switch_frame = max(int(scene_start), int(incoming_start))

        PoseHandler._set_list_weight(list_ctrl, old_index, scene_start, 100.0)
        PoseHandler._set_list_weight(list_ctrl, new_index, scene_start, 0.0)
        PoseHandler._set_list_weight(list_ctrl, old_index, switch_frame, 0.0)
        PoseHandler._set_list_weight(list_ctrl, new_index, switch_frame, 100.0)
        try:
            list_ctrl.setActive(new_index)
        except Exception:
            pass
        _diag_print(
            u"[PoseHandler][ApplyDiag] Splice {0}.{1}: switchFrame={2}, oldBinding={3}, newLayerIndex={4}".format(
                _safe_node_name(node),
                slot_name,
                switch_frame,
                _describe_constraint_binding(existing_binding, scene_start, switch_frame - 1),
                new_index
            )
        )
        return True

    @staticmethod
    def ensure_constraint_bindings(binding_map, node_lookup=None,
                                   incoming_start_map=None,
                                   incoming_end_map=None,
                                   parent_widget=None, show_error=None):
        """
        Ensure selected nodes have the saved constraint relationships.

        Missing constraints are created before animation keys are applied so
        dependency ordering and controller writes behave as if the source rig's
        constraint graph were already present in the scene.
        """
        if not PYMXS_AVAILABLE or not binding_map:
            return 0

        created = 0
        if incoming_start_map is None:
            incoming_start_map = {}
        if incoming_end_map is None:
            incoming_end_map = {}
        if show_error is None:
            show_error = _show_error

        for node_name, slot_bindings in binding_map.items():
            node = None
            if node_lookup is not None:
                node = node_lookup.get(node_name)
            if node is None:
                node = rt.getNodeByName(node_name)
            if node is None:
                continue

            for slot_name, desired_binding in slot_bindings.items():
                current_ctrl = PoseHandler._get_slot_controller(node, slot_name)
                current_binding = PoseHandler._capture_constraint_binding_from_ctrl(current_ctrl)
                if (
                    PoseHandler._constraint_binding_signature(current_binding) ==
                    PoseHandler._constraint_binding_signature(desired_binding)
                ):
                    _diag_print(
                        u"[PoseHandler][ApplyDiag] Constraint already matches {0}.{1}: {2}".format(
                            node_name,
                            slot_name,
                            _describe_constraint_binding(
                                desired_binding,
                                incoming_start_map.get(node_name),
                                incoming_end_map.get(node_name)
                            )
                        )
                    )
                    continue

                class_name = desired_binding.get("class", "")
                incoming_start = int(incoming_start_map.get(node_name, 0))
                incoming_end = int(incoming_end_map.get(node_name, incoming_start))
                _diag_print(
                    u"[PoseHandler][ApplyDiag] Restore request {0}.{1}: incomingRange={2}-{3}, desired={4}, current={5}".format(
                        node_name,
                        slot_name,
                        incoming_start,
                        incoming_end,
                        _describe_constraint_binding(desired_binding, incoming_start, incoming_end),
                        _describe_constraint_binding(current_binding)
                    )
                )
                resolved_targets = []
                missing_target_found = False
                for target_payload in desired_binding.get("targets", []):
                    if target_payload.get("world"):
                        resolved_targets.append((None, target_payload))
                        continue

                    target_name = target_payload.get("name")
                    if not target_name:
                        continue

                    target_node = None
                    if node_lookup is not None:
                        target_node = node_lookup.get(target_name)
                    if target_node is None:
                        target_node = rt.getNodeByName(target_name)
                    if target_node is None:
                        try:
                            show_error(
                                "Constraint Target Missing",
                                u"Could not restore constraint for '{0}.{1}'.\nMissing target: {2}".format(
                                    node_name, slot_name, target_name
                                ),
                                parent_widget
                            )
                        except Exception:
                            pass
                        _safe_print(
                            u"[PoseHandler] Constraint target not found for {0}.{1}: {2}".format(
                                node_name, slot_name, target_name
                            )
                        )
                        missing_target_found = True
                        continue
                    resolved_targets.append((target_node, target_payload))

                if missing_target_found:
                    _safe_print(
                        u"[PoseHandler] Skipping constraint restore for {0}.{1} because one or more targets are missing.".format(
                            node_name, slot_name
                        )
                    )
                    continue

                if not resolved_targets:
                    _safe_print(
                        u"[PoseHandler] No valid constraint targets to restore for {0}.{1}: {2}".format(
                            node_name, slot_name, class_name
                        )
                    )
                    continue

                new_ctrl = PoseHandler._build_constraint_controller(class_name)
                if new_ctrl is None:
                    _safe_print(
                        u"[PoseHandler] Unsupported constraint class for restore on {0}.{1}: {2}".format(
                            node_name, slot_name, class_name
                        )
                    )
                    continue

                appended_any = False
                for target_node, target_payload in resolved_targets:
                    if PoseHandler._append_constraint_target(
                        new_ctrl, class_name, target_node, target_payload
                    ):
                        appended_any = True
                    else:
                        _safe_print(
                            u"[PoseHandler] Failed to append constraint target for {0}.{1}: {2}".format(
                                node_name, slot_name, target_payload.get("name", "")
                            )
                        )
                if not appended_any:
                    _diag_print(
                        u"[PoseHandler][ApplyDiag] Restore request {0}.{1}: no targets appended.".format(
                            node_name, slot_name
                        )
                    )
                    continue

                if current_binding:
                    if not PoseHandler._splice_constraint_with_existing(
                        node, slot_name, current_binding, new_ctrl, incoming_start
                    ):
                        _safe_print(
                            u"[PoseHandler] Failed to splice constraint on {0}.{1}; falling back to overwrite.".format(
                                node_name, slot_name
                            )
                        )
                        if not PoseHandler._assign_constraint_controller(node, slot_name, new_ctrl):
                            _safe_print(
                                u"[PoseHandler] Failed to assign constraint controller on {0}.{1}: {2}".format(
                                    node_name, slot_name, class_name
                                )
                            )
                            continue
                else:
                    if not PoseHandler._assign_constraint_controller(node, slot_name, new_ctrl):
                        _safe_print(
                            u"[PoseHandler] Failed to assign constraint controller on {0}.{1}: {2}".format(
                                node_name, slot_name, class_name
                            )
                        )
                        continue

                created += 1
                _safe_print(
                    u"[PoseHandler] Restored constraint on {0}.{1}: {2}".format(
                        node_name, slot_name, class_name
                    )
                )
                _diag_print(
                    u"[PoseHandler][ApplyDiag] Restored {0}.{1}: incomingRange={2}-{3}, desired={4}".format(
                        node_name,
                        slot_name,
                        incoming_start,
                        incoming_end,
                        _describe_constraint_binding(desired_binding, incoming_start, incoming_end)
                    )
                )
                PoseHandler._refresh_scene_evaluation(force=True)

        return created

    @staticmethod
    def _add_current_value_key(ctrl):
        """
        Add a key and explicitly assign the controller's current evaluated value.

        This avoids default addNewKey behavior that can duplicate the previous
        key's value on some constraint controllers.
        """
        if ctrl is None:
            return False

        live_value = PoseHandler._get_controller_value(ctrl)
        key = None
        try:
            key = rt.addNewKey(ctrl, rt.currentTime)
        except Exception:
            key = None

        if key is not None and live_value is not None:
            try:
                key.value = live_value
                return True
            except Exception:
                pass

        return PoseHandler._add_interpolated_key(ctrl)

    @staticmethod
    def _refresh_scene_evaluation(force=False):
        """
        Force 3ds Max to re-evaluate controller / constraint chains.

        Multi-level constrained bones can otherwise read stale target values
        during the same paste operation.
        """
        if not PYMXS_AVAILABLE:
            return
        _scene_eval_state["count"] += 1
        if (not force and
                (_scene_eval_state["count"] % _SCENE_EVAL_REDRAW_STRIDE) != 0):
            return
        try:
            rt.redrawViews()
        except Exception:
            pass
        if force:
            try:
                rt.completeRedraw()
            except Exception:
                pass

    @staticmethod
    def _capture_constraint_values(node):
        """Capture evaluated outputs of constraint-driven controllers."""
        captured = {}
        controllers = PoseHandler._get_constraint_driven_controllers(node)
        for key, ctrl in controllers.items():
            value = PoseHandler._get_controller_value(ctrl)
            serialized = PoseHandler._serialize_controller_value(value)
            if serialized is not None:
                captured[key] = {
                    "class": PoseHandler._controller_class_name(ctrl),
                    "value": serialized
                }
        return captured

    @staticmethod
    def _capture_link_constraint_values(node):
        """Capture raw Link Constraint link_params PRS values."""
        captured = {}
        if node is None:
            return captured

        transform_ctrl = PoseHandler._get_slot_controller(node, "transform")
        primary_ctrl = PoseHandler._get_primary_constraint_controller(transform_ctrl)
        if PoseHandler._controller_class_name(primary_ctrl) != "Link_Constraint":
            return captured

        for slot_name in ("position", "rotation", "scale"):
            ctrl = PoseHandler._get_link_constraint_param_controller(primary_ctrl, slot_name)
            if ctrl is None:
                continue
            value = PoseHandler._get_controller_value(ctrl)
            serialized = PoseHandler._serialize_controller_value(value)
            if serialized is not None:
                captured[slot_name] = {
                    "class": PoseHandler._controller_class_name(ctrl),
                    "value": serialized
                }
        return captured

    @staticmethod
    def _restore_link_constraint_values(node, link_constraint_values, keyed_channels=None):
        """Restore raw Link Constraint link_params PRS values."""
        if node is None or not link_constraint_values:
            return False

        keyed_channels = set(keyed_channels or [])
        use_saved_channel_filter = bool(keyed_channels)
        restored = False

        transform_ctrl = PoseHandler._get_slot_controller(node, "transform")
        primary_ctrl = PoseHandler._get_primary_constraint_controller(transform_ctrl)
        if PoseHandler._controller_class_name(primary_ctrl) != "Link_Constraint":
            return False

        for slot_name, payload in (link_constraint_values or {}).items():
            if use_saved_channel_filter and slot_name not in keyed_channels:
                continue
            ctrl = PoseHandler._get_link_constraint_param_controller(primary_ctrl, slot_name)
            if ctrl is None:
                continue
            value = PoseHandler._deserialize_controller_value(
                (payload or {}).get("value")
            )
            if value is None:
                continue
            restored = PoseHandler._set_controller_value(ctrl, value) or restored

        if restored:
            PoseHandler._refresh_scene_evaluation(force=True)
        return restored

    @staticmethod
    def _is_link_constraint_node(node):
        """Return True if the node's primary transform constraint is Link Constraint."""
        if node is None:
            return False
        transform_ctrl = PoseHandler._get_slot_controller(node, "transform")
        primary_ctrl = PoseHandler._get_primary_constraint_controller(transform_ctrl)
        return PoseHandler._controller_class_name(primary_ctrl) == "Link_Constraint"

    @staticmethod
    def _restore_constraint_values(node, constraint_values, keyed_channels=None,
                                   world_offset=None):
        """Restore saved outputs onto a node's constraint-driven controllers."""
        if node is None or not constraint_values:
            return False

        controllers = PoseHandler._get_constraint_driven_controllers(node)
        keyed_channels = set(keyed_channels or [])
        use_saved_channel_filter = bool(keyed_channels)
        restored = False

        for slot_name, payload in (constraint_values or {}).items():
            if use_saved_channel_filter:
                if slot_name == "transform":
                    if "transform" not in keyed_channels:
                        continue
                elif slot_name not in keyed_channels and "transform" not in keyed_channels:
                    continue

            ctrl = controllers.get(slot_name)
            if ctrl is None:
                continue
            value = PoseHandler._deserialize_controller_value(
                (payload or {}).get("value")
            )
            value = PoseHandler._offset_constraint_value(value, world_offset)
            if value is None:
                continue
            restored = PoseHandler._set_controller_value(ctrl, value) or restored

        if restored:
            PoseHandler._refresh_scene_evaluation(force=True)
        return restored

    @staticmethod
    def _key_current_constraint_values(node, keyed_channels=None):
        """Key the node's current solved constraint outputs."""
        if node is None:
            return False

        controllers = PoseHandler._get_constraint_driven_controllers(node)
        keyed_channels = set(keyed_channels or [])
        use_saved_channel_filter = bool(keyed_channels)
        keyed_any = False

        for slot_name, ctrl in controllers.items():
            if use_saved_channel_filter:
                if slot_name == "transform":
                    if "transform" not in keyed_channels:
                        continue
                elif slot_name not in keyed_channels and "transform" not in keyed_channels:
                    continue
            primary_ctrl = PoseHandler._get_primary_constraint_controller(ctrl)
            if primary_ctrl is not None:
                keyed_any = PoseHandler._add_current_value_key(primary_ctrl) or keyed_any
            else:
                keyed_any = PoseHandler._add_current_value_key(ctrl) or keyed_any

        if keyed_any:
            PoseHandler._refresh_scene_evaluation(force=True)
        return keyed_any

    @staticmethod
    def _capture_constraint_offset_values(node):
        """
        Capture evaluated values on all non-constraint list layers per slot
        (offset / self-animation on top of Position_List, Transform_List,
        etc.).
        """
        captured = {}
        if node is None:
            return captured

        for slot_name, ctrl in PoseHandler._get_constraint_driven_controllers(node).items():
            if not PoseHandler._is_slot_list_controller(ctrl, slot_name):
                continue
            slot_layers = []
            for layer_index in range(1, PoseHandler._get_list_count(ctrl) + 1):
                layer_ctrl = PoseHandler._get_list_layer_controller(ctrl, layer_index)
                if layer_ctrl is None or PoseHandler._ctrl_is_constrained(layer_ctrl):
                    continue
                value = PoseHandler._get_controller_value(layer_ctrl)
                serialized = PoseHandler._serialize_controller_value(value)
                if serialized is None:
                    continue
                slot_layers.append({
                    "index": int(layer_index),
                    "class": PoseHandler._controller_class_name(layer_ctrl),
                    "value": serialized,
                    "weight": PoseHandler._get_list_weight(ctrl, layer_index),
                    "active": (
                        PoseHandler._get_active_list_layer_index(ctrl) == int(layer_index)
                    )
                })
            if slot_layers:
                captured[slot_name] = slot_layers
        return captured

    @staticmethod
    def _restore_constraint_offset_values(node, offset_values, keyed_channels=None):
        """Restore offset-layer values from _capture_constraint_offset_values."""
        if node is None or not offset_values:
            return False

        keyed_channels = set(keyed_channels or [])
        use_saved_channel_filter = bool(keyed_channels)
        restored = False

        for slot_name, payload in (offset_values or {}).items():
            if use_saved_channel_filter:
                if slot_name == "transform":
                    if "transform" not in keyed_channels:
                        continue
                elif slot_name not in keyed_channels and "transform" not in keyed_channels:
                    continue
            list_ctrl = PoseHandler._get_slot_controller(node, slot_name)
            if (
                list_ctrl is None or
                not PoseHandler._is_slot_list_controller(list_ctrl, slot_name)
            ):
                continue
            payload_items = payload if isinstance(payload, list) else [payload]
            for layer_payload in payload_items:
                if not isinstance(layer_payload, dict):
                    continue
                layer_index = layer_payload.get("index")
                if layer_index is None:
                    layer_index = PoseHandler._find_non_constraint_list_layer(list_ctrl)
                try:
                    layer_index = int(layer_index)
                except Exception:
                    continue
                value = PoseHandler._deserialize_controller_value(
                    (layer_payload or {}).get("value")
                )
                if value is None:
                    continue
                restored = (
                    PoseHandler._write_list_layer_value(list_ctrl, layer_index, value) or
                    restored
                )
                layer_weight = layer_payload.get("weight")
                if layer_weight is not None:
                    try:
                        PoseHandler._set_list_weight(
                            list_ctrl,
                            layer_index,
                            rt.currentTime,
                            float(layer_weight)
                        )
                    except Exception:
                        pass
                if layer_payload.get("active"):
                    try:
                        list_ctrl.setActive(layer_index)
                    except Exception:
                        pass

        if restored:
            PoseHandler._refresh_scene_evaluation(force=True)
        return restored

    @staticmethod
    def _apply_local_values_to_constrained_node(node, local_tm, local_pos,
                                                local_rot_q, local_scale,
                                                keyed_channels=None,
                                                skip_offset_list_slots=None,
                                                diag_node_name=None,
                                                allow_link_params=False):
        """
        Write saved local values into non-constraint layers when present.

        skip_offset_list_slots: set of slot names ("transform", "position", …)
        for which list offset layers were already restored (e.g. from
        constraint_offset_values); those list layers are skipped but
        unconstrained PRS controllers are still updated.
        """
        if node is None:
            return False

        keyed_channels = set(keyed_channels or [])
        skip_offset_list_slots = set(skip_offset_list_slots or [])
        use_saved_channel_filter = bool(keyed_channels)
        wrote = False

        transform_ctrl = PoseHandler._get_slot_controller(node, "transform")
        primary_transform_ctrl = PoseHandler._get_primary_constraint_controller(
            transform_ctrl
        )
        primary_constraint_class = PoseHandler._controller_class_name(
            primary_transform_ctrl
        )
        if diag_node_name is not None:
            _safe_print(
                u"[PoseHandler][ApplyDiag] LocalConstrained {0}: transformCtrl={1}, primaryConstraint={2}, keyedChannels={3}".format(
                    diag_node_name,
                    PoseHandler._controller_class_name(transform_ctrl) or "(none)",
                    primary_constraint_class or "(none)",
                    u", ".join(sorted(keyed_channels)) if keyed_channels else "(all)"
                )
            )
        if (
            transform_ctrl is not None and
            primary_constraint_class != "Link_Constraint" and
            not PoseHandler._is_slot_list_controller(transform_ctrl, "transform") and
            PoseHandler._ctrl_is_constrained(transform_ctrl)
        ):
            ensured_ctrl, ensured_layer = PoseHandler._ensure_transform_offset_list_layer(node)
            if diag_node_name is not None:
                _safe_print(
                    u"[PoseHandler][ApplyDiag] LocalConstrained {0}.transform: ensureOffsetLayer layer={1}, ctrl={2}".format(
                        diag_node_name,
                        "(none)" if ensured_layer is None else int(ensured_layer),
                        PoseHandler._controller_class_name(ensured_ctrl) or "(unknown)"
                    )
                )
            transform_ctrl = ensured_ctrl
        if (
            transform_ctrl is not None and
            PoseHandler._is_slot_list_controller(transform_ctrl, "transform")
        ):
            if (not use_saved_channel_filter) or ("transform" in keyed_channels):
                if "transform" not in skip_offset_list_slots:
                    layer_index = PoseHandler._find_non_constraint_list_layer(
                        transform_ctrl
                    )
                    if layer_index is not None:
                        transform_write_ok = PoseHandler._write_list_layer_value(
                            transform_ctrl, layer_index, local_tm
                        )
                        wrote = transform_write_ok or wrote
                        if diag_node_name is not None:
                            _safe_print(
                                u"[PoseHandler][ApplyDiag] LocalConstrained {0}.transform: layer={1}, write={2}, ctrl={3}".format(
                                    diag_node_name,
                                    int(layer_index),
                                    bool(transform_write_ok),
                                    PoseHandler._controller_class_name(
                                        PoseHandler._get_list_layer_controller(transform_ctrl, layer_index)
                                    ) or "(unknown)"
                                )
                            )
                    elif diag_node_name is not None:
                        _safe_print(
                            u"[PoseHandler][ApplyDiag] LocalConstrained {0}.transform: no non-constraint layer".format(
                                diag_node_name
                            )
                        )
                elif diag_node_name is not None:
                    _safe_print(
                        u"[PoseHandler][ApplyDiag] LocalConstrained {0}.transform: skipped by restored offset layer".format(
                            diag_node_name
                        )
                    )

        slot_values = (
            ("position", local_pos),
            ("rotation", local_rot_q),
            ("scale", local_scale),
        )
        for slot_name, slot_value in slot_values:
            if use_saved_channel_filter and slot_name not in keyed_channels:
                continue
            slot_ctrl = PoseHandler._get_slot_controller(node, slot_name)
            if (
                slot_ctrl is None and
                allow_link_params and
                use_saved_channel_filter and
                primary_constraint_class == "Link_Constraint"
            ):
                slot_ctrl = PoseHandler._get_link_constraint_param_controller(
                    primary_transform_ctrl, slot_name
                )
                if diag_node_name is not None and slot_ctrl is not None:
                    _safe_print(
                        u"[PoseHandler][ApplyDiag] LocalConstrained {0}.{1}: using link_params ctrl={2}".format(
                            diag_node_name,
                            slot_name,
                            PoseHandler._controller_class_name(slot_ctrl) or "(unknown)"
                        )
                    )
            if slot_ctrl is None:
                if diag_node_name is not None:
                    _safe_print(
                        u"[PoseHandler][ApplyDiag] LocalConstrained {0}.{1}: missing slot controller".format(
                            diag_node_name, slot_name
                        )
                    )
                continue
            if PoseHandler._is_slot_list_controller(slot_ctrl, slot_name):
                if slot_name in skip_offset_list_slots:
                    if diag_node_name is not None:
                        _safe_print(
                            u"[PoseHandler][ApplyDiag] LocalConstrained {0}.{1}: skipped by restored offset layer".format(
                                diag_node_name, slot_name
                            )
                        )
                    continue
                layer_index = PoseHandler._find_non_constraint_list_layer(slot_ctrl)
                if layer_index is not None:
                    slot_write_ok = PoseHandler._write_list_layer_value(
                        slot_ctrl, layer_index, slot_value
                    )
                    wrote = slot_write_ok or wrote
                    if diag_node_name is not None:
                        _safe_print(
                            u"[PoseHandler][ApplyDiag] LocalConstrained {0}.{1}: layer={2}, write={3}, ctrl={4}".format(
                                diag_node_name,
                                slot_name,
                                int(layer_index),
                                bool(slot_write_ok),
                                PoseHandler._controller_class_name(
                                    PoseHandler._get_list_layer_controller(slot_ctrl, layer_index)
                                ) or "(unknown)"
                            )
                        )
                elif diag_node_name is not None:
                    _safe_print(
                        u"[PoseHandler][ApplyDiag] LocalConstrained {0}.{1}: no non-constraint layer".format(
                            diag_node_name, slot_name
                        )
                    )
            elif not PoseHandler._ctrl_is_constrained(slot_ctrl):
                slot_write_ok = PoseHandler._set_controller_value(slot_ctrl, slot_value)
                wrote = slot_write_ok or wrote
                if diag_node_name is not None:
                    _safe_print(
                        u"[PoseHandler][ApplyDiag] LocalConstrained {0}.{1}: directWrite={2}, ctrl={3}".format(
                            diag_node_name,
                            slot_name,
                            bool(slot_write_ok),
                            PoseHandler._controller_class_name(slot_ctrl) or "(unknown)"
                        )
                    )
            elif diag_node_name is not None:
                _safe_print(
                    u"[PoseHandler][ApplyDiag] LocalConstrained {0}.{1}: constrained slot controller skipped ({2})".format(
                        diag_node_name,
                        slot_name,
                        PoseHandler._controller_class_name(slot_ctrl) or "(unknown)"
                    )
                )

        if wrote:
            PoseHandler._refresh_scene_evaluation(force=True)
        elif diag_node_name is not None:
            _safe_print(
                u"[PoseHandler][ApplyDiag] LocalConstrained {0}: no local writes applied.".format(
                    diag_node_name
                )
            )
        return wrote

    @staticmethod
    def _has_transform_constraint(node):
        """Return True if node is driven by any transform-related constraint."""
        return bool(PoseHandler._get_constraint_driven_controllers(node))

    @staticmethod
    def capture_pose_snapshot(selected_objects, frame):
        """
        Capture pose data for *selected_objects* at a specific frame.

        Returns the same per-node payload schema used by pose JSON files, but
        as an in-memory {node_name: node_data} dict.
        """
        if not PYMXS_AVAILABLE:
            return {}

        import pymxs

        nodes_data = {}
        for obj in selected_objects:
            try:
                name = _safe_node_name(obj)
                with pymxs.attime(frame):
                    world_tm = obj.transform

                    if obj.parent is not None:
                        local_tm = world_tm * rt.inverse(obj.parent.transform)
                    else:
                        local_tm = world_tm

                    pos = local_tm.pos
                    rot_q = local_tm.rotation
                    scale = local_tm.scale

                    world_pos = world_tm.pos
                    world_rot_q = world_tm.rotation
                    world_scale = world_tm.scale
                    local_tm_rows = PoseHandler._matrix3_to_rows(local_tm)
                    world_tm_rows = PoseHandler._matrix3_to_rows(world_tm)
                    constraint_values = PoseHandler._capture_constraint_values(obj)
                    link_constraint_values = PoseHandler._capture_link_constraint_values(obj)
                    channel_frames = GenericAnimHandler._get_object_channel_key_frames(
                        obj, frame, frame
                    )
                    keyed_channels = GenericAnimHandler._get_frame_keyed_channels(
                        channel_frames, frame
                    )

                node_entry = {
                    "pos": [float(pos.x), float(pos.y), float(pos.z)],
                    "rot_q": [float(rot_q.x), float(rot_q.y), float(rot_q.z), float(rot_q.w)],
                    "scale": [float(scale.x), float(scale.y), float(scale.z)],
                    "world_pos": [float(world_pos.x), float(world_pos.y), float(world_pos.z)],
                    "world_rot_q": [
                        float(world_rot_q.x), float(world_rot_q.y),
                        float(world_rot_q.z), float(world_rot_q.w)
                    ],
                    "world_scale": [float(world_scale.x), float(world_scale.y), float(world_scale.z)],
                    "local_tm_rows": local_tm_rows,
                    "world_tm_rows": world_tm_rows,
                    "constraint_values": constraint_values,
                    "is_biped": bool(PoseHandler._is_biped_node(obj)),
                    "is_biped_root": bool(BipedPartialAnimHandler._is_biped_root_node(obj)),
                }
                if link_constraint_values:
                    node_entry["link_constraint_values"] = link_constraint_values
                if keyed_channels:
                    node_entry["keyed_channels"] = keyed_channels
                if PoseHandler._has_transform_constraint(obj):
                    node_entry["constraint_offset_values"] = (
                        PoseHandler._capture_constraint_offset_values(obj)
                    )
                nodes_data[name] = node_entry
            except Exception as e:
                _safe_print(
                    u"[PoseHandler] Snapshot capture failed at frame {0}: {1}".format(
                        frame, repr(e)
                    )
                )
        return nodes_data

    @staticmethod
    def apply_pose_snapshot(nodes_data, frame, node_lookup=None, applied_names_out=None,
                            diagnostics_out=None, force_bake_keys=False,
                            biped_root_space_mode="world", session_state=None,
                            direct_root_keys=False):
        """
        Apply in-memory pose snapshot data to nodes at the given frame.

        Args:
            nodes_data   : {node_name: node_pose_data}
            frame        : target frame
            node_lookup  : optional dict[str, node] used instead of scene-wide
                           rt.getNodeByName lookups. This is ideal for strict
                           selected-only animation application.

        Returns:
            Number of nodes successfully updated.
        """
        if not PYMXS_AVAILABLE or not nodes_data:
            return 0

        import pymxs
        _reset_scene_evaluation_state()
        if session_state is None:
            session_state = {}
        try:
            local_root_position_seeded = session_state.setdefault(
                "local_root_position_seeded", set()
            )
        except Exception:
            local_root_position_seeded = set()

        def _node_depth(node):
            depth = 0
            n = node
            while n.parent is not None:
                depth += 1
                n = n.parent
            return depth

        node_map = {}
        for node_name, tdata in nodes_data.items():
            node = None
            if node_lookup is not None:
                node = node_lookup.get(node_name)
            else:
                node = rt.getNodeByName(node_name)
            if node is None:
                _safe_print(u"[PoseHandler] Snapshot skipped (not found): {0}".format(node_name))
                continue
            node_map[node_name] = (node, tdata)

        root_space_mode = text_type(
            biped_root_space_mode or "world"
        ).strip().lower()
        local_root_offset = None
        if root_space_mode == "local":
            for _root_name, (root_node, root_tdata) in node_map.items():
                try:
                    is_root = bool(root_tdata.get("is_biped_root"))
                except Exception:
                    is_root = False
                if not is_root:
                    try:
                        is_root = BipedPartialAnimHandler._is_biped_root_node(root_node)
                    except Exception:
                        is_root = False
                if not is_root:
                    continue
                try:
                    current_root_pos = root_node.transform.pos
                except Exception:
                    current_root_pos = None
                try:
                    saved_root_pos_data = root_tdata.get("world_pos") or []
                    if len(saved_root_pos_data) >= 3:
                        saved_root_pos = rt.Point3(
                            float(saved_root_pos_data[0]),
                            float(saved_root_pos_data[1]),
                            float(saved_root_pos_data[2])
                        )
                    else:
                        saved_root_pos = None
                except Exception:
                    saved_root_pos = None
                if current_root_pos is not None and saved_root_pos is not None:
                    local_root_offset = rt.Point3(
                        float(current_root_pos.x) - float(saved_root_pos.x),
                        float(current_root_pos.y) - float(saved_root_pos.y),
                        float(current_root_pos.z) - float(saved_root_pos.z)
                    )
                    break

        def _dependency_rank(node_name, cache=None, stack=None):
            if cache is None:
                cache = {}
            if stack is None:
                stack = set()
            if node_name in cache:
                return cache[node_name]
            if node_name in stack:
                return 0

            stack.add(node_name)
            node, _tdata = node_map[node_name]

            dependencies = []
            if node.parent is not None:
                parent_name = _safe_node_name(node.parent)
                if parent_name in node_map:
                    dependencies.append(parent_name)

            for target in PoseHandler._get_constraint_target_nodes(node):
                try:
                    target_name = _safe_node_name(target)
                except Exception:
                    continue
                if target_name in node_map:
                    dependencies.append(target_name)

            rank = 0
            for dep_name in dependencies:
                rank = max(rank, _dependency_rank(dep_name, cache, stack) + 1)

            stack.remove(node_name)
            cache[node_name] = rank
            return rank

        rank_cache = {}
        ordered = []
        for node_name, (node, tdata) in node_map.items():
            dep_rank = _dependency_rank(node_name, rank_cache, set())
            ordered.append((dep_rank, _node_depth(node), node_name, node, tdata))

        ordered.sort(key=lambda x: (x[0], x[1], x[2]))

        applied_count = 0
        for _dep_rank, _depth, node_name, node, tdata in ordered:
            try:
                obj_diag = None
                if diagnostics_out is not None:
                    obj_diag = diagnostics_out.setdefault(node_name, {
                        "node_class": "",
                        "position_ctrl": "",
                        "rotation_ctrl": "",
                        "scale_ctrl": "",
                        "biped_frames": 0,
                        "constrained_frames": 0,
                        "prs_frames": 0,
                        "transform_fallback_frames": 0,
                        "error_frames": 0,
                        "last_error": "",
                        "applied_frames": [],
                        "constrained_frame_list": [],
                        "prs_frame_list": [],
                        "fallback_frame_list": [],
                    })
                    try:
                        obj_diag["node_class"] = str(rt.classOf(node))
                    except Exception:
                        obj_diag["node_class"] = "Unknown"
                    obj_diag["position_ctrl"] = PoseHandler._controller_class_name(
                        PoseHandler._get_property_controller(node, "position")
                    )
                    obj_diag["rotation_ctrl"] = PoseHandler._controller_class_name(
                        PoseHandler._get_property_controller(node, "rotation")
                    )
                    obj_diag["scale_ctrl"] = PoseHandler._controller_class_name(
                        PoseHandler._get_property_controller(node, "scale")
                    )
                PoseHandler._refresh_scene_evaluation()

                px, py, pz = tdata["pos"]
                sx, sy, sz = tdata["scale"]

                local_pos = rt.Point3(float(px), float(py), float(pz))
                local_scale = rt.Point3(float(sx), float(sy), float(sz))

                if "rot_q" in tdata:
                    qx, qy, qz, qw = tdata["rot_q"]
                    local_rot_q = rt.quat(float(qx), float(qy), float(qz), float(qw))
                else:
                    rx, ry, rz = tdata["rot"]
                    local_rot_q = rt.eulerToQuat(
                        rt.eulerAngles(float(rx), float(ry), float(rz))
                    )

                saved_local_tm = PoseHandler._rows_to_matrix3(tdata.get("local_tm_rows"))
                saved_world_tm = PoseHandler._rows_to_matrix3(tdata.get("world_tm_rows"))

                has_world_data = (
                    "world_pos" in tdata and
                    "world_rot_q" in tdata and
                    "world_scale" in tdata
                )
                if has_world_data:
                    wpx, wpy, wpz = tdata["world_pos"]
                    wqx, wqy, wqz, wqw = tdata["world_rot_q"]
                    wsx, wsy, wsz = tdata["world_scale"]
                    saved_world_pos = rt.Point3(float(wpx), float(wpy), float(wpz))
                    saved_world_rot_q = rt.quat(
                        float(wqx), float(wqy), float(wqz), float(wqw)
                    )
                    saved_world_scale = rt.Point3(float(wsx), float(wsy), float(wsz))
                else:
                    saved_world_pos = None
                    saved_world_rot_q = None
                    saved_world_scale = None

                is_biped = PoseHandler._is_biped_node(node)
                is_constrained = PoseHandler._has_transform_constraint(node)

                def _ancestor_is_constrained(n):
                    p = n.parent
                    while p is not None:
                        if PoseHandler._has_transform_constraint(p):
                            return True
                        p = p.parent
                    return False

                parent_constrained = (not is_biped and _ancestor_is_constrained(node))
                keyed_channels = set(tdata.get("keyed_channels") or [])
                use_saved_channel_filter = bool(keyed_channels)
                constraint_values = tdata.get("constraint_values") or {}
                link_constraint_values = tdata.get("link_constraint_values") or {}

                def _apply(node=node, local_pos=local_pos,
                            local_rot_q=local_rot_q, local_scale=local_scale,
                            is_biped=is_biped, is_constrained=is_constrained,
                            parent_constrained=parent_constrained,
                            node_name=node_name,
                            keyed_channels=keyed_channels,
                            use_saved_channel_filter=use_saved_channel_filter,
                            saved_local_tm=saved_local_tm,
                            saved_world_tm=saved_world_tm,
                            saved_world_pos=saved_world_pos,
                            saved_world_rot_q=saved_world_rot_q,
                            saved_world_scale=saved_world_scale,
                            constraint_values=constraint_values,
                            link_constraint_values=link_constraint_values,
                            force_bake_keys=force_bake_keys,
                            root_space_mode=root_space_mode,
                            local_root_offset=local_root_offset,
                            direct_root_keys=direct_root_keys):
                    if saved_local_tm is not None:
                        local_tm = saved_local_tm
                    else:
                        rot_mat = rt.matrix3(1)
                        rot_mat.rotation = local_rot_q
                        row1 = rt.Point3(rot_mat.row1.x * local_scale.x,
                                         rot_mat.row1.y * local_scale.x,
                                         rot_mat.row1.z * local_scale.x)
                        row2 = rt.Point3(rot_mat.row2.x * local_scale.y,
                                         rot_mat.row2.y * local_scale.y,
                                         rot_mat.row2.z * local_scale.y)
                        row3 = rt.Point3(rot_mat.row3.x * local_scale.z,
                                         rot_mat.row3.y * local_scale.z,
                                         rot_mat.row3.z * local_scale.z)
                        local_tm = rt.matrix3(row1, row2, row3, local_pos)

                    if is_biped:
                        if obj_diag is not None:
                            obj_diag["biped_frames"] += 1
                        is_biped_root = BipedPartialAnimHandler._is_biped_root_node(node)
                        root_space_mode = text_type(
                            biped_root_space_mode or "world"
                        ).strip().lower()
                        if is_biped_root and root_space_mode == "local":
                            current_root_pos = None
                            try:
                                current_root_pos = node.transform.pos
                            except Exception:
                                current_root_pos = None
                            if current_root_pos is None:
                                current_root_pos = rt.Point3(0.0, 0.0, 0.0)

                            base_world_tm = saved_world_tm
                            base_world_rot_q = saved_world_rot_q
                            base_world_scale = saved_world_scale

                            if base_world_tm is None and saved_world_pos is not None:
                                try:
                                    w_rot_mat = rt.matrix3(1)
                                    w_rot_mat.rotation = saved_world_rot_q
                                    wr1 = rt.Point3(w_rot_mat.row1.x * saved_world_scale.x,
                                                    w_rot_mat.row1.y * saved_world_scale.x,
                                                    w_rot_mat.row1.z * saved_world_scale.x)
                                    wr2 = rt.Point3(w_rot_mat.row2.x * saved_world_scale.y,
                                                    w_rot_mat.row2.y * saved_world_scale.y,
                                                    w_rot_mat.row2.z * saved_world_scale.y)
                                    wr3 = rt.Point3(w_rot_mat.row3.x * saved_world_scale.z,
                                                    w_rot_mat.row3.y * saved_world_scale.z,
                                                    w_rot_mat.row3.z * saved_world_scale.z)
                                    base_world_tm = rt.matrix3(wr1, wr2, wr3, saved_world_pos)
                                except Exception:
                                    base_world_tm = None
                            if base_world_tm is None and saved_local_tm is not None:
                                base_world_tm = saved_local_tm
                            if base_world_scale is None:
                                base_world_scale = local_scale

                            if base_world_tm is not None:
                                world_tm = rt.matrix3(
                                    base_world_tm.row1,
                                    base_world_tm.row2,
                                    base_world_tm.row3,
                                    current_root_pos
                                )
                            else:
                                rot_mat = rt.matrix3(1)
                                rot_mat.rotation = base_world_rot_q or local_rot_q
                                row1 = rt.Point3(rot_mat.row1.x * base_world_scale.x,
                                                 rot_mat.row1.y * base_world_scale.x,
                                                 rot_mat.row1.z * base_world_scale.x)
                                row2 = rt.Point3(rot_mat.row2.x * base_world_scale.y,
                                                 rot_mat.row2.y * base_world_scale.y,
                                                 rot_mat.row2.z * base_world_scale.y)
                                row3 = rt.Point3(rot_mat.row3.x * base_world_scale.z,
                                                 rot_mat.row3.y * base_world_scale.z,
                                                 rot_mat.row3.z * base_world_scale.z)
                                world_tm = rt.matrix3(row1, row2, row3, current_root_pos)
                            world_pos = current_root_pos
                            if base_world_rot_q is not None:
                                world_rot_q = base_world_rot_q
                            else:
                                try:
                                    world_rot_q = world_tm.rotation
                                except Exception:
                                    world_rot_q = local_rot_q
                            _world_scale = base_world_scale
                        elif is_biped_root:
                            world_tm, world_pos, world_rot_q, _world_scale = (
                                PoseHandler._resolve_saved_world_transform(
                                    node,
                                    local_tm,
                                    saved_world_tm=saved_world_tm,
                                    saved_world_pos=saved_world_pos,
                                    saved_world_rot_q=saved_world_rot_q,
                                    saved_world_scale=saved_world_scale
                                )
                            )
                        else:
                            # Selected Only for regular Biped limbs should
                            # preserve the saved LOCAL relation to the current
                            # parent, not the old saved world-space pose.
                            world_tm, world_pos, world_rot_q, _world_scale = (
                                PoseHandler._resolve_saved_world_transform(
                                    node,
                                    local_tm
                                )
                            )
                        # For regular Biped limbs, writing world position causes
                        # Biped IK to solve the full limb and can drag parents
                        # (e.g. selecting only a forearm rotates the upper arm).
                        # Keep Selected Only semantics by authoring rotation only
                        # on non-root Biped nodes. COM/root still needs position
                        # and rotation for root motion.
                        apply_biped_position = bool(is_biped_root)
                        apply_biped_rotation = True
                        com_key_channels = set()
                        if is_biped_root and root_space_mode == "local":
                            if not use_saved_channel_filter:
                                com_key_channels.update(("position", "rotation"))
                            if use_saved_channel_filter:
                                if "transform" in keyed_channels:
                                    com_key_channels.update(("position", "rotation"))
                                if "position" in keyed_channels:
                                    com_key_channels.add("position")
                                if "rotation" in keyed_channels:
                                    com_key_channels.add("rotation")
                                apply_biped_position = ("position" in com_key_channels)
                                apply_biped_rotation = ("rotation" in com_key_channels)
                            apply_biped_position = False
                            if node_name not in local_root_position_seeded:
                                apply_biped_position = True
                                com_key_channels.add("position")
                                try:
                                    local_root_position_seeded.add(node_name)
                                except Exception:
                                    pass
                        try:
                            PoseHandler._apply_biped_world_transform(
                                node,
                                world_tm,
                                world_pos,
                                world_rot_q,
                                use_com_keying=is_biped_root,
                                force_bake_keys=force_bake_keys,
                                apply_position=apply_biped_position,
                                apply_rotation=apply_biped_rotation,
                                limb_node=None,
                                com_key_channels=com_key_channels,
                                force_component_keys=bool(
                                    is_biped_root and root_space_mode == "local"
                                ),
                                force_position_key=bool(
                                    is_biped_root and root_space_mode == "local"
                                ),
                                force_rotation_key=bool(
                                    is_biped_root and (
                                        root_space_mode == "local" or direct_root_keys
                                    )
                                )
                            )
                        except Exception:
                            if apply_biped_position:
                                native_tm = PoseHandler._to_native_matrix3(world_tm)
                                if native_tm is not None:
                                    node.transform = native_tm
                                else:
                                    node.transform = world_tm

                    elif is_constrained:
                        if obj_diag is not None:
                            obj_diag["constrained_frames"] += 1
                            obj_diag["constrained_frame_list"].append(int(frame))
                        PoseHandler._refresh_scene_evaluation()

                        transform_ctrl = None
                        try:
                            transform_ctrl = node.controller
                        except Exception:
                            transform_ctrl = None
                        primary_constraint_ctrl = PoseHandler._get_primary_constraint_controller(
                            transform_ctrl
                        )
                        primary_constraint_class = PoseHandler._controller_class_name(
                            primary_constraint_ctrl
                        )

                        restored_constraints = False
                        if root_space_mode == "local":
                            restored_constraints = PoseHandler._key_current_constraint_values(
                                node,
                                keyed_channels=keyed_channels
                            )
                            is_link_constraint_node = PoseHandler._is_link_constraint_node(node)
                            restored_link_constraints = PoseHandler._restore_link_constraint_values(
                                node,
                                link_constraint_values,
                                keyed_channels=keyed_channels
                            )
                            restored_constraints = (
                                restored_constraints or restored_link_constraints
                            )
                            if "constraint_offset_values" not in tdata:
                                local_write_ok = PoseHandler._apply_local_values_to_constrained_node(
                                    node,
                                    local_tm,
                                    local_pos,
                                    local_rot_q,
                                    local_scale,
                                    keyed_channels=keyed_channels,
                                    diag_node_name=node_name,
                                    allow_link_params=False
                                )
                                if is_link_constraint_node and restored_link_constraints:
                                    local_write_ok = False
                                restored_constraints = restored_constraints or local_write_ok
                            else:
                                offset_payload = tdata.get("constraint_offset_values") or {}
                                restored_offsets = PoseHandler._restore_constraint_offset_values(
                                    node,
                                    offset_payload,
                                    keyed_channels=keyed_channels
                                )
                                restored_constraints = (
                                    restored_constraints or restored_offsets
                                )
                                local_write_ok = PoseHandler._apply_local_values_to_constrained_node(
                                    node,
                                    local_tm,
                                    local_pos,
                                    local_rot_q,
                                    local_scale,
                                    keyed_channels=keyed_channels,
                                    skip_offset_list_slots=set(offset_payload.keys()),
                                    diag_node_name=node_name,
                                    allow_link_params=False
                                )
                                if is_link_constraint_node and restored_link_constraints:
                                    local_write_ok = False
                                restored_constraints = restored_constraints or local_write_ok
                        else:
                            restored_constraints = PoseHandler._restore_constraint_values(
                                node,
                                constraint_values,
                                keyed_channels=keyed_channels,
                                world_offset=None
                            )
                        if restored_constraints:
                            if (
                                primary_constraint_class == "Link_Constraint" and
                                use_saved_channel_filter
                            ):
                                PoseHandler._cleanup_link_constraint_channel_keys(
                                    primary_constraint_ctrl, keyed_channels
                                )
                            PoseHandler._refresh_scene_evaluation(force=True)
                        else:
                            effective_saved_world_tm = saved_world_tm
                            effective_saved_world_pos = saved_world_pos
                            if root_space_mode == "local" and local_root_offset is not None:
                                effective_saved_world_tm = PoseHandler._offset_world_matrix(
                                    saved_world_tm, local_root_offset
                                )
                                effective_saved_world_pos = PoseHandler._offset_world_point(
                                    saved_world_pos, local_root_offset
                                )

                            if effective_saved_world_tm is not None:
                                desired_world_tm = effective_saved_world_tm
                            elif effective_saved_world_pos is not None:
                                w_rot_mat = rt.matrix3(1)
                                w_rot_mat.rotation = saved_world_rot_q
                                wr1 = rt.Point3(w_rot_mat.row1.x * saved_world_scale.x,
                                                w_rot_mat.row1.y * saved_world_scale.x,
                                                w_rot_mat.row1.z * saved_world_scale.x)
                                wr2 = rt.Point3(w_rot_mat.row2.x * saved_world_scale.y,
                                                w_rot_mat.row2.y * saved_world_scale.y,
                                                w_rot_mat.row2.z * saved_world_scale.y)
                                wr3 = rt.Point3(w_rot_mat.row3.x * saved_world_scale.z,
                                                w_rot_mat.row3.y * saved_world_scale.z,
                                                w_rot_mat.row3.z * saved_world_scale.z)
                                desired_world_tm = rt.matrix3(wr1, wr2, wr3, effective_saved_world_pos)
                            elif node.parent is not None:
                                desired_world_tm = local_tm * node.parent.transform
                            else:
                                desired_world_tm = local_tm

                            native_tm = PoseHandler._to_native_matrix3(desired_world_tm)
                            if native_tm is not None:
                                try:
                                    node.transform = native_tm
                                    if (
                                        primary_constraint_class == "Link_Constraint" and
                                        use_saved_channel_filter
                                    ):
                                        PoseHandler._cleanup_link_constraint_channel_keys(
                                            primary_constraint_ctrl, keyed_channels
                                        )
                                    PoseHandler._refresh_scene_evaluation()
                                except Exception:
                                    controllers = PoseHandler._get_constraint_driven_controllers(node)
                                    transform_ctrl = controllers.get("transform")
                                    PoseHandler._add_current_value_key(transform_ctrl)
                                    if "position" in controllers:
                                        PoseHandler._add_current_value_key(controllers["position"])
                                    if "rotation" in controllers:
                                        PoseHandler._add_current_value_key(controllers["rotation"])
                                    if "scale" in controllers:
                                        PoseHandler._add_current_value_key(controllers["scale"])
                                    PoseHandler._refresh_scene_evaluation()

                    else:
                        # Prefer explicit PRS controller keys for regular objects.
                        # This is more reliable for Dummy / Point / helpers than
                        # relying on implicit key creation from node.transform.
                        transform_only = (use_saved_channel_filter and keyed_channels == {"transform"})
                        if transform_only:
                            if obj_diag is not None:
                                obj_diag["transform_fallback_frames"] += 1
                                obj_diag["fallback_frame_list"].append(int(frame))
                            effective_saved_world_tm = saved_world_tm
                            effective_saved_world_pos = saved_world_pos
                            if root_space_mode == "local" and local_root_offset is not None:
                                effective_saved_world_tm = PoseHandler._offset_world_matrix(
                                    saved_world_tm, local_root_offset
                                )
                                effective_saved_world_pos = PoseHandler._offset_world_point(
                                    saved_world_pos, local_root_offset
                                )
                            if (
                                parent_constrained and
                                root_space_mode != "local" and
                                effective_saved_world_tm is not None
                            ):
                                world_tm = effective_saved_world_tm
                            elif (
                                parent_constrained and
                                root_space_mode != "local" and
                                effective_saved_world_pos is not None
                            ):
                                w_rot_mat = rt.matrix3(1)
                                w_rot_mat.rotation = saved_world_rot_q
                                wr1 = rt.Point3(w_rot_mat.row1.x * saved_world_scale.x,
                                                w_rot_mat.row1.y * saved_world_scale.x,
                                                w_rot_mat.row1.z * saved_world_scale.x)
                                wr2 = rt.Point3(w_rot_mat.row2.x * saved_world_scale.y,
                                                w_rot_mat.row2.y * saved_world_scale.y,
                                                w_rot_mat.row2.z * saved_world_scale.y)
                                wr3 = rt.Point3(w_rot_mat.row3.x * saved_world_scale.z,
                                                w_rot_mat.row3.y * saved_world_scale.z,
                                                w_rot_mat.row3.z * saved_world_scale.z)
                                world_tm = rt.matrix3(wr1, wr2, wr3, effective_saved_world_pos)
                            else:
                                if node.parent is not None:
                                    world_tm = local_tm * node.parent.transform
                                else:
                                    world_tm = local_tm

                            native_tm = rt.Matrix3(
                                rt.Point3(float(world_tm.row1.x), float(world_tm.row1.y), float(world_tm.row1.z)),
                                rt.Point3(float(world_tm.row2.x), float(world_tm.row2.y), float(world_tm.row2.z)),
                                rt.Point3(float(world_tm.row3.x), float(world_tm.row3.y), float(world_tm.row3.z)),
                                rt.Point3(float(world_tm.row4.x), float(world_tm.row4.y), float(world_tm.row4.z))
                            )
                            node.transform = native_tm
                            return

                        prs_written = False
                        pos_ctrl = PoseHandler._get_property_controller(node, "position")
                        rot_ctrl = PoseHandler._get_property_controller(node, "rotation")
                        scl_ctrl = PoseHandler._get_property_controller(node, "scale")

                        if pos_ctrl is not None and (
                            not use_saved_channel_filter or "position" in keyed_channels
                        ):
                            prs_written = PoseHandler._set_controller_value(pos_ctrl, local_pos) or prs_written
                        if rot_ctrl is not None and (
                            not use_saved_channel_filter or "rotation" in keyed_channels
                        ):
                            prs_written = PoseHandler._set_controller_value(rot_ctrl, local_rot_q) or prs_written
                        if scl_ctrl is not None and (
                            not use_saved_channel_filter or "scale" in keyed_channels
                        ):
                            try:
                                prs_written = PoseHandler._set_controller_value(scl_ctrl, local_scale) or prs_written
                            except Exception:
                                pass

                        if prs_written:
                            if obj_diag is not None:
                                obj_diag["prs_frames"] += 1
                                obj_diag["prs_frame_list"].append(int(frame))
                            PoseHandler._refresh_scene_evaluation()
                        else:
                            if obj_diag is not None:
                                obj_diag["transform_fallback_frames"] += 1
                                obj_diag["fallback_frame_list"].append(int(frame))
                            effective_saved_world_tm = saved_world_tm
                            effective_saved_world_pos = saved_world_pos
                            if root_space_mode == "local" and local_root_offset is not None:
                                effective_saved_world_tm = PoseHandler._offset_world_matrix(
                                    saved_world_tm, local_root_offset
                                )
                                effective_saved_world_pos = PoseHandler._offset_world_point(
                                    saved_world_pos, local_root_offset
                                )
                            if (
                                parent_constrained and
                                root_space_mode != "local" and
                                effective_saved_world_tm is not None
                            ):
                                world_tm = effective_saved_world_tm
                            elif (
                                parent_constrained and
                                root_space_mode != "local" and
                                effective_saved_world_pos is not None
                            ):
                                w_rot_mat = rt.matrix3(1)
                                w_rot_mat.rotation = saved_world_rot_q
                                wr1 = rt.Point3(w_rot_mat.row1.x * saved_world_scale.x,
                                                w_rot_mat.row1.y * saved_world_scale.x,
                                                w_rot_mat.row1.z * saved_world_scale.x)
                                wr2 = rt.Point3(w_rot_mat.row2.x * saved_world_scale.y,
                                                w_rot_mat.row2.y * saved_world_scale.y,
                                                w_rot_mat.row2.z * saved_world_scale.y)
                                wr3 = rt.Point3(w_rot_mat.row3.x * saved_world_scale.z,
                                                w_rot_mat.row3.y * saved_world_scale.z,
                                                w_rot_mat.row3.z * saved_world_scale.z)
                                world_tm = rt.matrix3(wr1, wr2, wr3, effective_saved_world_pos)
                            else:
                                if node.parent is not None:
                                    world_tm = local_tm * node.parent.transform
                                else:
                                    world_tm = local_tm

                            native_tm = rt.Matrix3(
                                rt.Point3(float(world_tm.row1.x), float(world_tm.row1.y), float(world_tm.row1.z)),
                                rt.Point3(float(world_tm.row2.x), float(world_tm.row2.y), float(world_tm.row2.z)),
                                rt.Point3(float(world_tm.row3.x), float(world_tm.row3.y), float(world_tm.row3.z)),
                                rt.Point3(float(world_tm.row4.x), float(world_tm.row4.y), float(world_tm.row4.z))
                            )
                            node.transform = native_tm

                with pymxs.attime(frame):
                    with pymxs.animate(True):
                        _apply()

                applied_count += 1
                if obj_diag is not None:
                    obj_diag["applied_frames"].append(int(frame))
                if applied_names_out is not None:
                    applied_names_out.append(node_name)
            except Exception as e:
                if diagnostics_out is not None:
                    obj_diag = diagnostics_out.setdefault(node_name, {
                        "node_class": "",
                        "position_ctrl": "",
                        "rotation_ctrl": "",
                        "scale_ctrl": "",
                        "biped_frames": 0,
                        "constrained_frames": 0,
                        "prs_frames": 0,
                        "transform_fallback_frames": 0,
                        "error_frames": 0,
                        "last_error": "",
                        "applied_frames": [],
                        "constrained_frame_list": [],
                        "prs_frame_list": [],
                        "fallback_frame_list": [],
                    })
                    obj_diag["error_frames"] += 1
                    obj_diag["last_error"] = repr(e)
                _safe_print(
                    u"[PoseHandler] Snapshot apply failed for {0} at frame {1}: {2}".format(
                        node_name, frame, repr(e)
                    )
                )
                continue

        PoseHandler._refresh_scene_evaluation(force=True)
        return applied_count

    @staticmethod
    def save_pose(selected_objects, save_path, comment=u""):
        """
        Capture **local-space** transforms of *selected_objects* at the current
        timeline frame and write to save_path.

        Local space = node world transform * inverse(parent world transform).
        For root nodes (no parent) the world transform IS the local transform.

        Rotation is stored as a quaternion [x, y, z, w] to avoid gimbal lock.

        Args:
            selected_objects : iterable of pymxs scene nodes
            save_path        : destination file path (e.g. "hand_pose.json")

        Returns:
            True on success, False on failure.
        """
        if not PYMXS_AVAILABLE:
            _safe_print("[PoseHandler] pymxs not available - cannot save pose")
            return False

        try:
            current_frame = int(rt.currentTime)
        except Exception:
            current_frame = 0
        _safe_print("[PoseHandler] Saving pose at frame: {0}".format(current_frame))

        pose_data = {"version": 6, "frame": current_frame, "comment": comment or u"", "nodes": {}}

        import pymxs
        for obj in selected_objects:
            try:
                name = str(obj.name)
                with pymxs.attime(current_frame):
                    world_tm = obj.transform

                    if obj.parent is not None:
                        # local = world * inverse(parent_world)
                        local_tm = world_tm * rt.inverse(obj.parent.transform)
                    else:
                        local_tm = world_tm

                    # Decompose local matrix
                    pos   = local_tm.pos
                    rot_q = local_tm.rotation   # quaternion
                    scale = local_tm.scale

                    # Also capture world transform for robust apply
                    # (needed when parent has a constraint and its world
                    #  transform may not yet be updated in apply context)
                    world_pos   = world_tm.pos
                    world_rot_q = world_tm.rotation
                    world_scale = world_tm.scale
                    local_tm_rows = PoseHandler._matrix3_to_rows(local_tm)
                    world_tm_rows = PoseHandler._matrix3_to_rows(world_tm)
                    constraint_values = PoseHandler._capture_constraint_values(obj)
                    link_constraint_values = PoseHandler._capture_link_constraint_values(obj)
                    channel_frames = GenericAnimHandler._get_object_channel_key_frames(
                        obj, current_frame, current_frame
                    )
                    keyed_channels = GenericAnimHandler._get_frame_keyed_channels(
                        channel_frames, current_frame
                    )

                node_pose = {
                    "pos":   [float(pos.x),   float(pos.y),   float(pos.z)],
                    # Store quaternion [x, y, z, w]
                    "rot_q": [float(rot_q.x), float(rot_q.y),
                              float(rot_q.z), float(rot_q.w)],
                    "scale": [float(scale.x), float(scale.y), float(scale.z)],
                    # World-space snapshot — used as fallback when parent
                    # has a constraint whose driven transform may not have
                    # propagated yet during apply.
                    "world_pos":   [float(world_pos.x),   float(world_pos.y),   float(world_pos.z)],
                    "world_rot_q": [float(world_rot_q.x), float(world_rot_q.y),
                                    float(world_rot_q.z), float(world_rot_q.w)],
                    "world_scale": [float(world_scale.x), float(world_scale.y), float(world_scale.z)],
                    "is_biped": bool(PoseHandler._is_biped_node(obj)),
                    "is_biped_root": bool(BipedPartialAnimHandler._is_biped_root_node(obj)),
                    # Exact matrices are more stable than PRS decomposition for
                    # constrained rigs because list/constraint controllers can
                    # produce transforms that are lossy when rebuilt from PRS.
                    "local_tm_rows": local_tm_rows,
                    "world_tm_rows": world_tm_rows,
                    # Constraint-driven nodes also need their controller outputs
                    # captured so paste can create a correct key on this frame.
                    "constraint_values": constraint_values,
                }
                if link_constraint_values:
                    node_pose["link_constraint_values"] = link_constraint_values
                if keyed_channels:
                    node_pose["keyed_channels"] = keyed_channels
                if PoseHandler._has_transform_constraint(obj):
                    node_pose["constraint_offset_values"] = (
                        PoseHandler._capture_constraint_offset_values(obj)
                    )
                pose_data["nodes"][name] = node_pose
                _safe_print("[PoseHandler] Captured (local+world): " + name)
            except Exception as e:
                _safe_print("[PoseHandler] Failed to capture node: " + repr(e))
                continue

        if not pose_data["nodes"]:
            _safe_print("[PoseHandler] No node data captured — save aborted.")
            return False

        try:
            save_dir = os.path.dirname(save_path)
            if save_dir and not os.path.isdir(save_dir):
                os.makedirs(save_dir)
            with open(save_path, 'w') as f:
                json.dump(pose_data, f, indent=4)
            _safe_print("[PoseHandler] Pose saved to: " + repr(save_path))
            return True
        except Exception as e:
            _safe_print("[PoseHandler] File write FAILED: " + repr(e))
            return False

    # ------------------------------------------------------------------
    #  Apply
    # ------------------------------------------------------------------

    @staticmethod
    def apply_pose(pose_file_path, biped_root_space_mode="world"):
        """
        Apply pose data from *pose_file_path* to matching scene nodes at the
        **current time slider frame**, creating a key via Auto Key.

        Strategy per node:
          1. Reconstruct the local matrix from saved pos / rot_q / scale.
          2. Convert to world space: world = local * parent_world.
          3a. Regular node  → assign node.transform directly.
          3b. Biped node    → use rt.biped.setTransform so the Biped controller
                              accepts the value (direct .transform assignment is
                              often ignored by Biped).

        Nodes not found in the scene are silently skipped.

        Args:
            pose_file_path : path to the .json pose file (str)

        Returns:
            True if at least one node was updated, False otherwise.
        """
        if not PYMXS_AVAILABLE:
            _safe_print("[PoseHandler] pymxs not available - cannot apply pose")
            return False

        if not os.path.isfile(pose_file_path):
            _safe_print("[PoseHandler] Pose file not found: " + repr(pose_file_path))
            return False

        try:
            with open(pose_file_path, 'r') as f:
                pose_data = json.load(f)
        except Exception as e:
            _safe_print("[PoseHandler] Failed to read pose file: " + repr(e))
            return False

        nodes_data = pose_data.get("nodes", {})
        if not nodes_data:
            _safe_print("[PoseHandler] Pose file contains no node data.")
            return False

        try:
            current_frame = int(rt.currentTime)
        except Exception:
            current_frame = 0
        _safe_print("[PoseHandler] Applying pose at frame: {0}".format(current_frame))

        # If the user has an active scene selection, only apply to those nodes.
        # This matches the tool behavior expectation:
        # - save pose: save exactly the selected nodes
        # - apply pose: apply only to currently selected nodes
        node_lookup = None
        try:
            selected_nodes = list(rt.selection)
        except Exception:
            selected_nodes = []
        if selected_nodes:
            node_lookup = {}
            for node in selected_nodes:
                try:
                    node_lookup[str(node.name)] = node
                except Exception:
                    # Fallback: let snapshot resolver handle name mismatches.
                    pass

        applied_names = []
        applied_count = PoseHandler.apply_pose_snapshot(
            nodes_data,
            current_frame,
            node_lookup=node_lookup,
            applied_names_out=applied_names,
            biped_root_space_mode=biped_root_space_mode,
            direct_root_keys=True
        )
        _safe_print("[PoseHandler] Pose applied to {0}/{1} nodes.".format(
            applied_count, len(nodes_data)))
        return applied_count > 0

        import pymxs

        # ------------------------------------------------------------------
        # Step 1: Resolve node objects and sort by dependency order.
        #
        # Dependencies include BOTH:
        #   A) scene parent nodes
        #   B) constraint target nodes
        #
        # WHY: Multi-layer constraint chains often do not match the scene
        # hierarchy:
        #   Bone1 constrained to Bone0
        #   Bone2 constrained to Bone1
        #
        # Bone2 must be processed after Bone1 even if they are siblings in the
        # scene. Sorting only by parent depth is not enough.
        # ------------------------------------------------------------------

        def _node_depth(node):
            """Return the depth of *node* in the scene hierarchy (root = 0)."""
            depth = 0
            n = node
            while n.parent is not None:
                depth += 1
                n = n.parent
            return depth

        node_map = {}
        for node_name, tdata in nodes_data.items():
            node = rt.getNodeByName(node_name)
            if node is None:
                _safe_print("[PoseHandler] Skipped (not found): " + node_name)
                continue
            node_map[node_name] = (node, tdata)

        def _dependency_rank(node_name, cache=None, stack=None):
            """Return a topological-like rank from parent + constraint deps."""
            if cache is None:
                cache = {}
            if stack is None:
                stack = set()
            if node_name in cache:
                return cache[node_name]
            if node_name in stack:
                return 0

            stack.add(node_name)
            node, _tdata = node_map[node_name]

            dependencies = []
            if node.parent is not None:
                parent_name = str(node.parent.name)
                if parent_name in node_map:
                    dependencies.append(parent_name)

            for target in PoseHandler._get_constraint_target_nodes(node):
                try:
                    target_name = str(target.name)
                except Exception:
                    continue
                if target_name in node_map:
                    dependencies.append(target_name)

            rank = 0
            for dep_name in dependencies:
                rank = max(rank, _dependency_rank(dep_name, cache, stack) + 1)

            stack.remove(node_name)
            cache[node_name] = rank
            return rank

        rank_cache = {}
        ordered = []
        for node_name, (node, tdata) in node_map.items():
            dep_rank = _dependency_rank(node_name, rank_cache, set())
            ordered.append((dep_rank, _node_depth(node), node_name, node, tdata))

        # Targets / parents first, then dependents.
        ordered.sort(key=lambda x: (x[0], x[1], x[2]))

        # ------------------------------------------------------------------
        # Step 2: Apply transforms in depth order
        # ------------------------------------------------------------------

        applied_count = 0

        for _dep_rank, _depth, node_name, node, tdata in ordered:
            try:
                # Always refresh before processing the next node so any parent
                # keys written by the previous iteration have propagated through
                # the constraint graph.
                PoseHandler._refresh_scene_evaluation()

                px, py, pz = tdata["pos"]
                sx, sy, sz = tdata["scale"]

                local_pos   = rt.Point3(float(px), float(py), float(pz))
                local_scale = rt.Point3(float(sx), float(sy), float(sz))

                # Prefer quaternion (version 2/3); fall back to euler (version 1)
                if "rot_q" in tdata:
                    qx, qy, qz, qw = tdata["rot_q"]
                    local_rot_q = rt.quat(float(qx), float(qy),
                                          float(qz), float(qw))
                else:
                    rx, ry, rz = tdata["rot"]
                    local_rot_q = rt.eulerToQuat(
                        rt.eulerAngles(float(rx), float(ry), float(rz))
                    )

                # Prefer exact Matrix3 rows when available (version 4+).
                saved_local_tm = PoseHandler._rows_to_matrix3(
                    tdata.get("local_tm_rows")
                )
                saved_world_tm = PoseHandler._rows_to_matrix3(
                    tdata.get("world_tm_rows")
                )

                # Extract saved world transform if available (version 3+)
                has_world_data = ("world_pos" in tdata and
                                  "world_rot_q" in tdata and
                                  "world_scale" in tdata)
                if has_world_data:
                    wpx, wpy, wpz = tdata["world_pos"]
                    wqx, wqy, wqz, wqw = tdata["world_rot_q"]
                    wsx, wsy, wsz = tdata["world_scale"]
                    saved_world_pos   = rt.Point3(float(wpx), float(wpy), float(wpz))
                    saved_world_rot_q = rt.quat(float(wqx), float(wqy),
                                                float(wqz), float(wqw))
                    saved_world_scale = rt.Point3(float(wsx), float(wsy), float(wsz))
                else:
                    saved_world_pos   = None
                    saved_world_rot_q = None
                    saved_world_scale = None

                is_biped = PoseHandler._is_biped_node(node)
                is_constrained = PoseHandler._has_transform_constraint(node)

                # Detect whether any ancestor in the chain (up to scene root)
                # carries a constraint.  If so, the ancestor's world transform
                # may not have propagated yet inside the attime/animate context,
                # making "local * parent.transform" unreliable for this node.
                #
                # IMPORTANT: This must also cover deeply nested cases, e.g.:
                #   Bone0 (constrained) <- Bone1 (constrained) <- Bone2 (regular)
                #
                # In such chains, Bone1 and Bone0 are SKIPPED during apply
                # (is_constrained branch).  When we later process Bone2, its
                # parent.transform (Bone1) was never updated — it still holds the
                # pre-pose value.  Multiplying local_tm * stale_parent.transform
                # will place Bone2 in the wrong position.
                #
                # Fix: If ANY ancestor in the hierarchy is constrained (regardless
                # of whether the IMMEDIATE parent is constrained), we must fall
                # back to the saved world-space snapshot.
                def _ancestor_is_constrained(n):
                    """Return True if any parent in the hierarchy is constrained."""
                    p = n.parent
                    while p is not None:
                        if PoseHandler._has_transform_constraint(p):
                            return True
                        p = p.parent
                    return False

                # For the purpose of choosing the world-tm strategy we need to
                # know whether *any* ancestor is constrained (not just the
                # immediate parent).  The existing helper already does a full
                # walk, so re-use it directly.
                #
                # We intentionally do NOT exclude is_constrained nodes here:
                # a constrained node is skipped (no write), so checking
                # parent_constrained for it is harmless — the whole _apply()
                # closure for that node is never called in practice because it
                # hits the `elif is_constrained` branch first.
                parent_constrained = (not is_biped and
                                      _ancestor_is_constrained(node))

                def _apply(node=node, local_pos=local_pos,
                            local_rot_q=local_rot_q, local_scale=local_scale,
                            is_biped=is_biped, is_constrained=is_constrained,
                            parent_constrained=parent_constrained,
                            saved_local_tm=saved_local_tm,
                            saved_world_tm=saved_world_tm,
                            saved_world_pos=saved_world_pos,
                            saved_world_rot_q=saved_world_rot_q,
                            saved_world_scale=saved_world_scale):
                    if saved_local_tm is not None:
                        local_tm = saved_local_tm
                    else:
                        # Build local matrix: scale → rotate → translate
                        rot_mat = rt.matrix3(1)
                        rot_mat.rotation = local_rot_q

                        # Bake scale into the rotation rows
                        row1 = rt.Point3(rot_mat.row1.x * local_scale.x,
                                         rot_mat.row1.y * local_scale.x,
                                         rot_mat.row1.z * local_scale.x)
                        row2 = rt.Point3(rot_mat.row2.x * local_scale.y,
                                         rot_mat.row2.y * local_scale.y,
                                         rot_mat.row2.z * local_scale.y)
                        row3 = rt.Point3(rot_mat.row3.x * local_scale.z,
                                         rot_mat.row3.y * local_scale.z,
                                         rot_mat.row3.z * local_scale.z)
                        local_tm = rt.matrix3(row1, row2, row3, local_pos)

                    if is_biped:
                        # --------------------------------------------------
                        # Biped controller ignores direct .transform assignment;
                        # use biped.setTransform instead.
                        # --------------------------------------------------
                        if node.parent is not None:
                            world_tm = local_tm * node.parent.transform
                        else:
                            world_tm = local_tm
                        try:
                            ctrl = node.controller
                            rt.biped.setTransform(
                                ctrl, rt.Name("transform"), world_tm, False
                            )
                        except Exception as be:
                            _safe_print("[PoseHandler] biped.setTransform failed, "
                                        "falling back: " + repr(be))
                            node.transform = world_tm

                    elif is_constrained:
                        # --------------------------------------------------
                        # Constrained bone:
                        # Apply the saved WORLD transform directly after all its
                        # targets have been restored. In Max, moving a
                        # constrained node at the current frame updates the
                        # constraint's driven offset / result for this frame,
                        # which is exactly what we want for pose paste.
                        #
                        # This is more reliable for multi-layer chains than
                        # trying to author the internal constraint-controller
                        # value, because child constraints often keep using the
                        # previous key's offset unless the node itself is moved
                        # to the desired solved world transform.
                        # --------------------------------------------------
                        PoseHandler._refresh_scene_evaluation()
                        if saved_world_tm is not None:
                            desired_world_tm = saved_world_tm
                        elif saved_world_pos is not None:
                            w_rot_mat = rt.matrix3(1)
                            w_rot_mat.rotation = saved_world_rot_q
                            wr1 = rt.Point3(w_rot_mat.row1.x * saved_world_scale.x,
                                            w_rot_mat.row1.y * saved_world_scale.x,
                                            w_rot_mat.row1.z * saved_world_scale.x)
                            wr2 = rt.Point3(w_rot_mat.row2.x * saved_world_scale.y,
                                            w_rot_mat.row2.y * saved_world_scale.y,
                                            w_rot_mat.row2.z * saved_world_scale.y)
                            wr3 = rt.Point3(w_rot_mat.row3.x * saved_world_scale.z,
                                            w_rot_mat.row3.y * saved_world_scale.z,
                                            w_rot_mat.row3.z * saved_world_scale.z)
                            desired_world_tm = rt.matrix3(wr1, wr2, wr3, saved_world_pos)
                        elif node.parent is not None:
                            desired_world_tm = local_tm * node.parent.transform
                        else:
                            desired_world_tm = local_tm

                        native_tm = PoseHandler._to_native_matrix3(desired_world_tm)
                        if native_tm is not None:
                            try:
                                node.transform = native_tm
                                PoseHandler._refresh_scene_evaluation()
                                _safe_print(
                                    "[PoseHandler] Constrained bone applied via world transform: "
                                    + str(node.name)
                                )
                            except Exception as ce:
                                _safe_print(
                                    "[PoseHandler] Constrained world apply failed for {0}: {1}".format(
                                        str(node.name), repr(ce)
                                    )
                                )
                                # Fallback: if direct transform is rejected,
                                # at least key the current solved constraint
                                # result so this frame does not inherit the
                                # previous pose.
                                applied_ctrls = []
                                controllers = PoseHandler._get_constraint_driven_controllers(node)
                                transform_ctrl = controllers.get("transform")
                                if PoseHandler._add_current_value_key(transform_ctrl):
                                    applied_ctrls.append("transform")
                                if "position" in controllers:
                                    if PoseHandler._add_current_value_key(controllers["position"]):
                                        applied_ctrls.append("position")
                                if "rotation" in controllers:
                                    if PoseHandler._add_current_value_key(controllers["rotation"]):
                                        applied_ctrls.append("rotation")
                                if "scale" in controllers:
                                    if PoseHandler._add_current_value_key(controllers["scale"]):
                                        applied_ctrls.append("scale")
                                if applied_ctrls:
                                    PoseHandler._refresh_scene_evaluation()
                        else:
                            _safe_print(
                                "[PoseHandler] Constrained bone has no valid world matrix: " + str(node.name)
                            )

                    else:
                        # --------------------------------------------------
                        # Regular bone / object (no constraint).
                        #
                        # Two strategies for computing world_tm:
                        #
                        # A) Normal case (no constrained ancestor):
                        #      world_tm = local_tm * node.parent.transform
                        #    Parent has been processed already (depth sort),
                        #    so its transform is current.
                        #
                        # B) Constrained-ancestor case:
                        #    A constrained parent (e.g. a bone driven by a
                        #    Biped Orientation_Constraint) may not have
                        #    propagated its new world transform yet inside the
                        #    pymxs.attime/animate context.  Using the stale
                        #    parent.transform would place this bone at the
                        #    wrong world position.
                        #
                        #    Fix: use the world-space snapshot saved at
                        #    capture time (world_pos / world_rot_q /
                        #    world_scale).  That snapshot was taken when
                        #    the constraint was fully evaluated, so it is
                        #    the ground truth for where this bone should be.
                        # --------------------------------------------------
                        if parent_constrained and saved_world_tm is not None:
                            world_tm = saved_world_tm
                            _safe_print(
                                "[PoseHandler] Using saved world matrix (constrained ancestor): "
                                + str(node.name)
                            )
                        elif parent_constrained and saved_world_pos is not None:
                            # Backward compatibility for old pose files that only
                            # stored world PRS data.
                            w_rot_mat = rt.matrix3(1)
                            w_rot_mat.rotation = saved_world_rot_q
                            wr1 = rt.Point3(w_rot_mat.row1.x * saved_world_scale.x,
                                            w_rot_mat.row1.y * saved_world_scale.x,
                                            w_rot_mat.row1.z * saved_world_scale.x)
                            wr2 = rt.Point3(w_rot_mat.row2.x * saved_world_scale.y,
                                            w_rot_mat.row2.y * saved_world_scale.y,
                                            w_rot_mat.row2.z * saved_world_scale.y)
                            wr3 = rt.Point3(w_rot_mat.row3.x * saved_world_scale.z,
                                            w_rot_mat.row3.y * saved_world_scale.z,
                                            w_rot_mat.row3.z * saved_world_scale.z)
                            world_tm = rt.matrix3(wr1, wr2, wr3, saved_world_pos)
                            _safe_print(
                                "[PoseHandler] Using saved world PRS (constrained ancestor): "
                                + str(node.name)
                            )
                        else:
                            # Normal: derive world from local * parent
                            if node.parent is not None:
                                world_tm = local_tm * node.parent.transform
                            else:
                                world_tm = local_tm

                        try:
                            # Re-construct a guaranteed native rt.Matrix3 from
                            # the four row vectors of world_tm.
                            native_tm = rt.Matrix3(
                                rt.Point3(float(world_tm.row1.x),
                                          float(world_tm.row1.y),
                                          float(world_tm.row1.z)),
                                rt.Point3(float(world_tm.row2.x),
                                          float(world_tm.row2.y),
                                          float(world_tm.row2.z)),
                                rt.Point3(float(world_tm.row3.x),
                                          float(world_tm.row3.y),
                                          float(world_tm.row3.z)),
                                rt.Point3(float(world_tm.row4.x),
                                          float(world_tm.row4.y),
                                          float(world_tm.row4.z))
                            )
                            node.transform = native_tm
                        except Exception as e:
                            _safe_print(
                                u"[PoseHandler] \u9aa8\u9abc {name} \u5e94\u7528\u8df3\u8fc7: {err}".format(
                                    name=node.name, err=repr(e)
                                )
                            )

                with pymxs.attime(current_frame):
                    with pymxs.animate(True):
                        _apply()

                _safe_print("[PoseHandler] Applied (depth={0}): {1}".format(
                    _depth, node_name))
                applied_count += 1
            except Exception as e:
                _safe_print("[PoseHandler] Failed to apply to "
                            + node_name + ": " + repr(e))
                continue

        _safe_print("[PoseHandler] Pose applied to {0}/{1} nodes.".format(
            applied_count, len(nodes_data)))
        return applied_count > 0

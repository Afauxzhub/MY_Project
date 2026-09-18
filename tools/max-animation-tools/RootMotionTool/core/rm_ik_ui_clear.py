# -*- coding: utf-8 -*-
from __future__ import division, print_function

import io
import os
import time
import ctypes

import pymxs

rt = pymxs.runtime

try:
    text_type = unicode
except NameError:
    text_type = str

_LOG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, u"publish_debug.log")
)

_BM_CLICK = 245
_WM_MOUSEMOVE = 0x0200
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP = 0x0202
_MK_LBUTTON = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004

user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


def _as_text(value):
    try:
        return text_type(value)
    except Exception:
        try:
            return text_type(str(value))
        except Exception:
            return u""


def _log(msg):
    line = u"[RMTool IK] {0}".format(_as_text(msg))
    try:
        fh = io.open(_LOG_PATH, "a", encoding="utf-8")
    except Exception:
        fh = None
    if fh is not None:
        try:
            fh.write(line + u"\n")
        finally:
            fh.close()
    try:
        print(line)
    except Exception:
        try:
            print(line.encode("utf-8"))
        except Exception:
            pass


def _mxs_item(seq, primary_idx):
    for idx in (primary_idx, primary_idx + 1):
        try:
            return seq[idx]
        except Exception:
            pass
    raise IndexError(primary_idx)


def _iter_child_hwnds(hwnd):
    try:
        items = rt.windows.getChildrenHWND(hwnd)
    except Exception:
        return []
    result = []
    for item in items:
        try:
            result.append(int(_mxs_item(item, 0)))
        except Exception:
            pass
    return result


def _find_descendant_by_rid(hwnd, rid, depth=0, max_depth=5):
    if not hwnd or depth > max_depth:
        return None
    for child in _iter_child_hwnds(hwnd):
        try:
            child_rid = int(rt.UIAccessor.GetWindowResourceID(child))
        except Exception:
            child_rid = -1
        if child_rid == rid:
            return child
        found = _find_descendant_by_rid(child, rid, depth + 1, max_depth)
        if found:
            return found
    return None


def _get_root_hwnds():
    try:
        items = rt.windows.getChildrenHWND(rt.Name("max"))
    except Exception:
        try:
            items = rt.windows.getChildrenHWND(rt.windows.getMAXHWND())
        except Exception:
            items = []
    result = []
    for item in items:
        try:
            result.append(int(_mxs_item(item, 0)))
        except Exception:
            pass
    return result


def _get_max_hwnd():
    try:
        return int(rt.windows.getMAXHWND())
    except Exception:
        return None


def _iter_descendant_hwnds(hwnd, depth=0, max_depth=6):
    if not hwnd or depth > max_depth:
        return
    for child in _iter_child_hwnds(hwnd):
        yield child
        for grand_child in _iter_descendant_hwnds(child, depth + 1, max_depth):
            yield grand_child


def _find_ik_dialog():
    for root_hwnd in _get_root_hwnds():
        status_hwnd = _find_descendant_by_rid(root_hwnd, 1099)
        object_btn = _find_descendant_by_rid(root_hwnd, 1100)
        picker_btn = _find_descendant_by_rid(root_hwnd, 1435)
        if status_hwnd and object_btn and picker_btn:
            return root_hwnd
    return None


def _get_window_text(hwnd):
    if not hwnd:
        return u""
    try:
        return _as_text(rt.UIAccessor.GetWindowText(hwnd))
    except Exception:
        return u""


def _press_button(hwnd):
    if not hwnd:
        return False
    try:
        rt.UIAccessor.PressButton(hwnd)
        return True
    except Exception:
        pass
    try:
        rt.windows.sendMessage(hwnd, _BM_CLICK, 0, 0)
        return True
    except Exception:
        return False


def _get_window_rect(hwnd):
    if not hwnd:
        return None
    rect = RECT()
    if not user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
        return None
    return rect


def _get_client_rect(hwnd):
    if not hwnd:
        return None
    rect = RECT()
    if not user32.GetClientRect(int(hwnd), ctypes.byref(rect)):
        return None
    return rect


def _get_client_origin(hwnd):
    if not hwnd:
        return None
    pt = POINT()
    if not user32.ClientToScreen(int(hwnd), ctypes.byref(pt)):
        return None
    return (int(pt.x), int(pt.y))


def _get_parent_hwnd(hwnd):
    if not hwnd:
        return None
    parent = int(user32.GetParent(int(hwnd)))
    return parent or None


def _get_class_name(hwnd):
    if not hwnd:
        return u""
    buf = ctypes.create_unicode_buffer(256)
    try:
        user32.GetClassNameW(int(hwnd), buf, 255)
    except Exception:
        return u""
    return _as_text(buf.value)


def _get_cursor_pos():
    pt = POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        return None
    return (int(pt.x), int(pt.y))


def _set_foreground(hwnd):
    if not hwnd:
        return False
    try:
        user32.ShowWindow(int(hwnd), 5)
    except Exception:
        pass
    try:
        user32.SetForegroundWindow(int(hwnd))
        return True
    except Exception:
        return False


def _pack_lparam(x, y):
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


def _get_viewport_hwnd():
    capture = int(user32.GetCapture())
    focus = int(user32.GetFocus())
    _log(u"ikCaptureHwnd={0}".format(capture))
    _log(u"ikFocusHwnd={0}".format(focus))
    return capture or focus or None


def _find_active_viewpanel_hwnd(local_x, local_y):
    max_hwnd = _get_max_hwnd()
    if not max_hwnd:
        return None

    candidates = []
    for hwnd in _iter_descendant_hwnds(max_hwnd):
        cls = _get_class_name(hwnd)
        if cls != u"ViewPanel":
            continue
        client_rect = _get_client_rect(hwnd)
        origin = _get_client_origin(hwnd)
        if client_rect is None or origin is None:
            continue
        width = int(client_rect.right - client_rect.left)
        height = int(client_rect.bottom - client_rect.top)
        if width > int(local_x) and height > int(local_y) and width > 200 and height > 200:
            candidates.append((origin[1], origin[0], hwnd, width, height))

    if not candidates:
        return None

    candidates.sort()
    try:
        active_idx = int(rt.viewport.activeViewport)
    except Exception:
        active_idx = 1
    if active_idx < 1:
        active_idx = 1
    pick_idx = active_idx - 1
    if pick_idx >= len(candidates):
        pick_idx = 0

    chosen = candidates[pick_idx][2]
    chosen_meta = candidates[pick_idx]
    _log(
        u"ikActiveViewportIndex={0} chosenViewPanel={1} origin={2},{3}".format(
            active_idx, int(chosen), chosen_meta[1], chosen_meta[0]
        )
    )
    return chosen


def _click_window_center(hwnd):
    client_rect = _get_client_rect(hwnd)
    client_origin = _get_client_origin(hwnd)
    if client_rect is None or client_origin is None:
        return False
    width = int(client_rect.right - client_rect.left)
    height = int(client_rect.bottom - client_rect.top)
    local_x = max(1, width // 2)
    local_y = max(1, height // 2)
    abs_x = int(client_origin[0]) + local_x
    abs_y = int(client_origin[1]) + local_y
    old_pos = _get_cursor_pos()
    try:
        _set_foreground(hwnd)
        try:
            user32.SetFocus(int(hwnd))
        except Exception:
            pass
        user32.SetCursorPos(abs_x, abs_y)
        time.sleep(0.03)
        lparam = _pack_lparam(local_x, local_y)
        try:
            rt.windows.sendMessage(hwnd, _WM_MOUSEMOVE, 0, lparam)
        except Exception:
            pass
        user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        try:
            rt.windows.sendMessage(hwnd, _WM_LBUTTONDOWN, _MK_LBUTTON, lparam)
            rt.windows.sendMessage(hwnd, _WM_LBUTTONUP, 0, lparam)
        except Exception:
            pass
        return True
    finally:
        time.sleep(0.03)
        if old_pos:
            try:
                user32.SetCursorPos(old_pos[0], old_pos[1])
            except Exception:
                pass


def _resolve_viewport_hwnd(seed_hwnd, local_x, local_y):
    hwnd = seed_hwnd
    visited = set()
    while hwnd and hwnd not in visited:
        visited.add(hwnd)
        cls = _get_class_name(hwnd)
        client_rect = _get_client_rect(hwnd)
        width = 0
        height = 0
        if client_rect is not None:
            width = int(client_rect.right - client_rect.left)
            height = int(client_rect.bottom - client_rect.top)
        _log(
            u"ikViewportCandidate={0} class={1} client={2}x{3}".format(
                int(hwnd), cls, width, height
            )
        )
        if width > int(local_x) and height > int(local_y) and width > 200 and height > 200:
            return hwnd
        hwnd = _get_parent_hwnd(hwnd)
    return seed_hwnd


def _project_node_to_viewport(node):
    try:
        rt.redrawViews()
    except Exception:
        pass
    try:
        rt.gw.setTransform(rt.Matrix3(1))
    except Exception:
        try:
            rt.execute(u"gw.setTransform (Matrix3 1)")
        except Exception:
            return None
    try:
        world_pos = node.transform.pos
        screen_pt = rt.gw.transPoint(world_pos)
        x = int(round(float(screen_pt.x)))
        y = int(round(float(screen_pt.y)))
        _log(u"ikLocalPoint={0},{1}".format(x, y))
        return (x, y)
    except Exception as exc:
        _log(u"ikProjectError={0}".format(_as_text(exc)))
        return None


def _click_viewport(hwnd, local_x, local_y):
    client_rect = _get_client_rect(hwnd)
    client_origin = _get_client_origin(hwnd)
    if client_rect is None or client_origin is None:
        _log(u"ikViewportClient=<not found>")
        return False

    client_w = int(client_rect.right - client_rect.left)
    client_h = int(client_rect.bottom - client_rect.top)
    abs_x = int(client_origin[0]) + int(local_x)
    abs_y = int(client_origin[1]) + int(local_y)
    _log(
        u"ikViewportClient={0},{1} size={2}x{3}".format(
            int(client_origin[0]), int(client_origin[1]), client_w, client_h
        )
    )
    _log(u"ikScreenPoint={0},{1}".format(abs_x, abs_y))

    old_pos = _get_cursor_pos()
    try:
        user32.SetCursorPos(abs_x, abs_y)
        time.sleep(0.03)
        lparam = _pack_lparam(local_x, local_y)
        try:
            rt.windows.sendMessage(hwnd, _WM_MOUSEMOVE, 0, lparam)
        except Exception:
            pass
        user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        try:
            rt.windows.sendMessage(hwnd, _WM_LBUTTONDOWN, _MK_LBUTTON, lparam)
            rt.windows.sendMessage(hwnd, _WM_LBUTTONUP, 0, lparam)
        except Exception:
            pass
        return True
    finally:
        time.sleep(0.03)
        if old_pos:
            try:
                user32.SetCursorPos(old_pos[0], old_pos[1])
            except Exception:
                pass


def _get_limb_nodes(bip_obj):
    limb_defs = [
        (rt.Name("larm"), 4),
        (rt.Name("rarm"), 4),
        (rt.Name("lleg"), 4),
        (rt.Name("rleg"), 4),
    ]
    result = []
    for limb_id, link in limb_defs:
        try:
            node = rt.biped.getNode(bip_obj, limb_id, link=link)
        except Exception:
            node = None
        if node is not None:
            result.append(node)
    return result


def _poll_status(status_hwnd, tag):
    last_text = u""
    logged = []
    for _ in range(8):
        time.sleep(0.08)
        try:
            rt.completeRedraw()
        except Exception:
            pass
        last_text = _get_window_text(status_hwnd)
        if last_text not in logged:
            _log(u"{0}={1}".format(tag, last_text))
            logged.append(last_text)
        if not last_text:
            break
    return last_text


def _attempt_clear_for_node(node):
    try:
        rt.setCommandPanelTaskMode(rt.Name("motion"))
    except Exception:
        pass
    try:
        rt.select(node)
    except Exception:
        return False
    time.sleep(0.05)
    try:
        rt.completeRedraw()
    except Exception:
        pass

    dlg = _find_ik_dialog()
    if not dlg:
        _log(u"ikPythonDialog=<not found>")
        return False

    status_hwnd = _find_descendant_by_rid(dlg, 1099)
    object_btn = _find_descendant_by_rid(dlg, 1100)
    picker_btn = _find_descendant_by_rid(dlg, 1435)
    status_before = _get_window_text(status_hwnd)
    _log(u"ikPythonDialog={0}".format(int(dlg)))
    _log(u"ikPythonStatusBefore={0}".format(status_before))

    if not status_before:
        return True

    _set_foreground(dlg)

    if object_btn:
        _click_window_center(object_btn)
        _press_button(object_btn)
        time.sleep(0.05)

    targets = [node]
    try:
        if node.parent is not None:
            targets.append(node.parent)
    except Exception:
        pass
    try:
        if node.parent is not None and node.parent.parent is not None:
            targets.append(node.parent.parent)
    except Exception:
        pass
    # Status text often names the IK Object (e.g. Attachment_RH_03). Prefer picking it
    # first so Object-space binding can be reassigned / cleared via the dialog.
    if status_before:
        try:
            named = rt.getNodeByName(status_before, exact=True)
        except Exception:
            named = None
        if named is None:
            try:
                named = rt.getNodeByName(status_before)
            except Exception:
                named = None
        if named is not None:
            targets = [named] + [t for t in targets if t != named]
            _log(u"ikPythonResolvedObject={0}".format(_as_text(named.name)))

    for target in targets:
        target_name = _as_text(getattr(target, "name", u""))
        _log(u"ikPythonPickTarget={0}".format(target_name))
        if not picker_btn:
            _log(u"ikPythonPickerPressFailed")
            return False
        _click_window_center(picker_btn)
        if not _press_button(picker_btn):
            _log(u"ikPythonPickerPressFailed")
            return False
        time.sleep(0.08)
        _log(u"ikCaptureAfterPicker={0}".format(int(user32.GetCapture())))
        _log(u"ikFocusAfterPicker={0}".format(int(user32.GetFocus())))

        viewport_hwnd = _get_viewport_hwnd()
        if not viewport_hwnd:
            _log(u"ikViewportHwnd=<not found>")
            return False

        local_point = _project_node_to_viewport(target)
        if not local_point:
            continue
        active_viewpanel = _find_active_viewpanel_hwnd(local_point[0], local_point[1])
        if active_viewpanel:
            viewport_hwnd = active_viewpanel
        else:
            viewport_hwnd = _resolve_viewport_hwnd(
                viewport_hwnd, local_point[0], local_point[1]
            )
        _log(u"ikViewportHwnd={0}".format(int(viewport_hwnd)))
        if not _click_viewport(viewport_hwnd, local_point[0], local_point[1]):
            continue

        status_after = _poll_status(status_hwnd, u"ikPythonStatusAfterPick")
        if not status_after:
            final_text = _get_window_text(status_hwnd)
            _log(u"ikPythonStatusFinal={0}".format(final_text))
            return True

    final_text = _get_window_text(status_hwnd)
    _log(u"ikPythonStatusFinal={0}".format(final_text))
    return not final_text


def _get_node_ik_status(node):
    if node is None:
        return u""
    try:
        rt.setCommandPanelTaskMode(rt.Name("motion"))
    except Exception:
        pass
    try:
        rt.select(node)
    except Exception:
        return u""
    time.sleep(0.05)
    try:
        rt.completeRedraw()
    except Exception:
        pass
    dlg = _find_ik_dialog()
    if not dlg:
        return u""
    status_hwnd = _find_descendant_by_rid(dlg, 1099)
    return _get_window_text(status_hwnd)


def get_remaining_ik_nodes(bip_obj, only_cam):
    if only_cam or bip_obj is None:
        return []
    result = []
    for node in _get_limb_nodes(bip_obj):
        status = _get_node_ik_status(node)
        if status:
            result.append((node, status))
    try:
        rt.clearSelection()
    except Exception:
        pass
    return result


def prepare_manual_ik_ui(node):
    if node is None:
        return False
    try:
        rt.setCommandPanelTaskMode(rt.Name("motion"))
    except Exception:
        pass
    try:
        rt.select(node)
    except Exception:
        return False
    time.sleep(0.05)
    try:
        rt.completeRedraw()
    except Exception:
        pass
    _log(u"ikManualNode={0}".format(_as_text(getattr(node, "name", u""))))
    return True


def clear_remaining_ik_objects(bip_obj, only_cam):
    if only_cam or bip_obj is None:
        return 0

    cleared = 0
    for node in _get_limb_nodes(bip_obj):
        if _attempt_clear_for_node(node):
            cleared += 1

    try:
        rt.clearSelection()
    except Exception:
        pass
    return cleared

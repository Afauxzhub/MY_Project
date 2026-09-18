# -*- coding: utf-8 -*-
"""
Unity 桥接：
  1. 将 Unity 窗口切到前台
  2. 给 Unity Editor 写入“Project 窗口定位目录”请求
"""
from __future__ import print_function
import os
import io
import json
import ctypes
import ctypes.wintypes


def _get_bridge_root_dir():
    local_appdata = os.environ.get("LOCALAPPDATA", u"")
    if local_appdata:
        return os.path.join(
            local_appdata,
            u"Afauxzhub",
            u"AnimationPipeline",
        )
    return os.path.join(
        os.path.expanduser(u"~"),
        u"Afauxzhub",
        u"AnimationPipeline",
    )


def get_unity_bridge_request_path():
    bridge_dir = _get_bridge_root_dir()
    if not os.path.exists(bridge_dir):
        os.makedirs(bridge_dir)
    return os.path.join(bridge_dir, u"unity_bridge_request.json")


def build_unity_asset_path(abs_path, unity_assets_dir):
    abs_norm = os.path.normpath(abs_path).replace("\\", "/")
    assets_norm = os.path.normpath(unity_assets_dir).replace("\\", "/")
    if abs_norm != assets_norm and not abs_norm.startswith(assets_norm.rstrip("/") + "/"):
        return u""
    rel = abs_norm[len(assets_norm):].lstrip("/")
    if rel:
        return u"Assets/" + rel.replace("\\", "/")
    return u"Assets"


def write_project_window_request(abs_path, unity_assets_dir):
    asset_path = build_unity_asset_path(abs_path, unity_assets_dir)
    if not asset_path:
        raise ValueError(u"无法将路径转换为 Unity Asset 路径：{0}".format(abs_path))

    req_path = get_unity_bridge_request_path()
    payload = {
        u"asset_path": asset_path,
        u"absolute_path": abs_path.replace("\\", "/"),
    }
    with io.open(req_path, "w", encoding="utf-8") as f:
        f.write(unicode(json.dumps(payload, ensure_ascii=False, indent=2)))
    return req_path, asset_path


def _find_unity_hwnd():
    """
    枚举所有可见窗口，找到标题中含 ' - Unity ' 的窗口句柄。
    返回 hwnd（整数）或 None。
    """
    user32 = ctypes.windll.user32
    found  = [None]

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPARAM,
    )

    def _callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if u" - Unity " in buf.value:
            found[0] = hwnd
            return False   # 停止枚举
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    return found[0]


def focus_unity_and_trigger_refresh():
    """
    将 Unity 编辑器窗口强行置于前台。
    切换焦点会自动触发 Unity 的 AssetDatabase.Refresh()。

    返回 True  — 成功找到并唤起 Unity 窗口
    返回 False — 未找到 Unity 窗口（Unity 未运行）
    """
    hwnd = _find_unity_hwnd()
    if hwnd is None:
        return False

    user32   = ctypes.windll.user32

    # SW_RESTORE = 9：恢复最小化/还原窗口
    user32.ShowWindow(hwnd, 9)

    # 绕过 Windows 前台窗口切换限制（AttachThreadInput 技巧）
    fg_hwnd = user32.GetForegroundWindow()
    if fg_hwnd and fg_hwnd != hwnd:
        fg_tid  = user32.GetWindowThreadProcessId(fg_hwnd,  None)
        tgt_tid = user32.GetWindowThreadProcessId(hwnd,     None)
        user32.AttachThreadInput(fg_tid, tgt_tid, True)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(fg_tid, tgt_tid, False)
    else:
        user32.SetForegroundWindow(hwnd)

    return True


def is_unity_running():
    """检测 Unity 编辑器是否正在运行"""
    return _find_unity_hwnd() is not None

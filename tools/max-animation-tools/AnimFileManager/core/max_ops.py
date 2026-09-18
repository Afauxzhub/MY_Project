# -*- coding: utf-8 -*-
"""在 3ds Max 中打开/删除/重命名 .max 文件，及打开所在文件夹。"""
from __future__ import division
import os

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


def open_max_file(path, use_max_check=True):
    """在 Max 中打开 .max 文件。"""
    path = _as_text(path)
    if not path or not os.path.isfile(path):
        return False, u"文件不存在: {0}".format(path)
    rt = _get_rt()
    try:
        if use_max_check:
            rt.checkForSave()
        rt.loadMaxFile(path, quiet=False, useFileUnits=True)
        return True, u""
    except Exception as e:
        return False, _as_text(e)


def _visible_explorer_hwnds():
    """收集当前可见的资源管理器窗口句柄。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnds = set()
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in (u"CabinetWClass", u"ExploreWClass"):
            hwnds.add(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(_callback), 0)
    return hwnds


def _foreground_new_explorer(before_hwnds):
    """将新打开的资源管理器窗口置于最前。"""
    import time
    import ctypes

    user32 = ctypes.windll.user32
    try:
        user32.AllowSetForegroundWindow(ctypes.c_uint(0xFFFFFFFF).value)
    except Exception:
        pass

    for _ in range(20):
        time.sleep(0.05)
        after = _visible_explorer_hwnds()
        new_hwnds = [hwnd for hwnd in after if hwnd not in before_hwnds]
        if new_hwnds:
            target = new_hwnds[-1]
            user32.ShowWindow(target, 9)
            user32.SetForegroundWindow(target)
            return True

    if after:
        target = list(after)[-1]
        user32.ShowWindow(target, 9)
        user32.SetForegroundWindow(target)
        return True
    return False


def open_file_folder(path):
    """在资源管理器中打开文件所在文件夹，并选中该文件。"""
    import ctypes

    path = _as_text(path)
    if not path:
        return False, u"路径无效"
    path = os.path.normpath(path)
    folder = os.path.dirname(path)
    if not folder or not os.path.isdir(folder):
        return False, u"文件夹不存在: {0}".format(folder)

    target_path = path if os.path.isfile(path) else folder
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILCreateFromPathW.argtypes = [ctypes.c_wchar_p]
    shell32.ILFree.argtypes = [ctypes.c_void_p]
    shell32.SHOpenFolderAndSelectItems.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long

    pidl = shell32.ILCreateFromPathW(target_path)
    if not pidl:
        return False, u"无法解析路径: {0}".format(target_path)

    before_hwnds = _visible_explorer_hwnds()
    ole32.CoInitialize(None)
    try:
        hr = shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
        if hr < 0:
            return False, u"无法打开资源管理器 (错误码 {0})".format(hr)
    finally:
        shell32.ILFree(pidl)
        ole32.CoUninitialize()

    _foreground_new_explorer(before_hwnds)
    return True, u""


def _companion_settings_path(max_path):
    """max 文件对应的发布设置 json 路径。"""
    from core.local_sync import publish_settings_path_for_max
    return publish_settings_path_for_max(max_path)


def delete_max_file(path):
    path = _as_text(path)
    if not path or not os.path.isfile(path):
        return False, u"文件不存在"
    try:
        os.remove(path)
    except Exception as e:
        return False, _as_text(e)
    try:
        settings_json = _companion_settings_path(path)
        if settings_json and os.path.isfile(settings_json):
            os.remove(settings_json)
    except Exception:
        pass
    return True, u""


def rename_max_file(path, new_name):
    path = _as_text(path)
    new_name = _as_text(new_name).strip()
    if not path or not os.path.isfile(path):
        return False, u"文件不存在"
    if not new_name:
        return False, u"新文件名不能为空"
    if not new_name.lower().endswith(u".max"):
        new_name += u".max"
    dst = os.path.join(os.path.dirname(path), new_name)
    if os.path.exists(dst):
        return False, u"目标文件已存在"
    try:
        os.rename(path, dst)
    except Exception as e:
        return False, _as_text(e)
    try:
        old_json = _companion_settings_path(path)
        new_json = _companion_settings_path(dst)
        if old_json and new_json and os.path.isfile(old_json):
            if os.path.isfile(new_json):
                os.remove(new_json)
            os.rename(old_json, new_json)
    except Exception:
        pass
    return True, dst

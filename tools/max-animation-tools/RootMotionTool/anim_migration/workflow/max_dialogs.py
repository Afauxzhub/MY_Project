# -*- coding: utf-8 -*-
from __future__ import print_function

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


def install_silent_file_dialog_handler(rt):
    """Auto-dismiss common modal dialogs that quiet:true does not suppress."""
    try:
        script = u'''
        (
            global OP_RigUpdate_DialogSuppress
            fn OP_RigUpdate_DialogSuppress =
            (
                local hwnd = DialogMonitorOPS.GetWindowHandle()
                if hwnd == 0 do return true
                local title = UIAccessor.GetWindowText hwnd
                local lowTitle = toLower title
                local shouldClose = (
                    (findString title "缺少 DLL" != undefined) or
                    (findString lowTitle "missing dll" != undefined) or
                    (findString title "缺少外部文件" != undefined) or
                    (findString lowTitle "missing external" != undefined) or
                    (findString lowTitle "missing map" != undefined) or
                    (findString lowTitle "missing files" != undefined)
                )
                if shouldClose then
                (
                    local buttons = UIAccessor.GetChildWindows hwnd
                    local clicked = false
                    local preferred = #("打开", "Open", "继续", "Continue", "确定", "OK", "是", "Yes")
                    local fallback = #("取消", "Cancel", "否", "No")
                    for label in preferred while not clicked do
                    (
                        for b in buttons while not clicked do
                        (
                            if (UIAccessor.GetWindowText b) == label then
                            (
                                UIAccessor.PressButton b
                                clicked = true
                            )
                        )
                    )
                    for label in fallback while not clicked do
                    (
                        for b in buttons while not clicked do
                        (
                            if (UIAccessor.GetWindowText b) == label then
                            (
                                UIAccessor.PressButton b
                                clicked = true
                            )
                        )
                    )
                    if not clicked do UIAccessor.CloseDialog hwnd
                )
                true
            )
            try(DialogMonitorOPS.UnRegisterNotification id:#OP_RigUpdate_DialogSuppress)catch()
            DialogMonitorOPS.RegisterNotification OP_RigUpdate_DialogSuppress id:#OP_RigUpdate_DialogSuppress
            DialogMonitorOPS.Enabled = true
            true
        )
        '''
        rt.execute(script)
    except Exception:
        pass


def uninstall_silent_file_dialog_handler(rt):
    try:
        rt.execute(u'''
        (
            try(DialogMonitorOPS.UnRegisterNotification id:#OP_RigUpdate_DialogSuppress)catch()
            try(DialogMonitorOPS.Enabled = false)catch()
            true
        )
        ''')
    except Exception:
        pass


class SilentFileDialogs(object):
    def __init__(self, rt):
        self._rt = rt

    def __enter__(self):
        install_silent_file_dialog_handler(self._rt)
        return self

    def __exit__(self, exc_type, exc, tb):
        uninstall_silent_file_dialog_handler(self._rt)
        return False

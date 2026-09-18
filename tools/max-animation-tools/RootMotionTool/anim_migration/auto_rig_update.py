# -*- coding: utf-8 -*-
from __future__ import print_function
import os

try:
    _text_type = unicode
except NameError:
    _text_type = str


CALLBACK_ID = "OP_RigUpdateAuto"
STARTUP_SCRIPT_NAME = "OP_RigUpdateAuto.ms"


def _as_text(value):
    if value is None:
        return u""
    if isinstance(value, _text_type):
        return value
    try:
        return _text_type(value)
    except Exception:
        return u""


def _log(message):
    try:
        print(u"[RMTool][AutoRigUpdate] {0}".format(_as_text(message)))
    except Exception:
        pass


def _startup_script_path(rt):
    folder = _as_text(rt.getDir(rt.Name("userStartupScripts")))
    return os.path.join(folder, STARTUP_SCRIPT_NAME)


def _remove_legacy_timer(rt):
    try:
        rt.execute(u'''
        (
            global OP_RigUpdateAutoTimer
            try(if OP_RigUpdateAutoTimer != undefined do OP_RigUpdateAutoTimer.Stop())catch()
            try(dotNet.removeAllEventHandlers OP_RigUpdateAutoTimer)catch()
            OP_RigUpdateAutoTimer = undefined
        )
        ''')
    except Exception:
        pass


def check_current_file(auto=True):
    _log(u"自动更新已移除，跳过检查。")
    return {"ok": False, "skipped": True, "message": u"自动更新已移除"}


def unregister_callback():
    import pymxs
    rt = pymxs.runtime
    try:
        rt.callbacks.removeScripts(id=rt.Name(CALLBACK_ID))
    except Exception:
        pass
    _remove_legacy_timer(rt)
    return True


def register_callback():
    _log(u"自动更新已移除，执行注销清理。")
    return unregister_callback()


def sync_from_config():
    _log(u"自动更新已移除，执行注销清理。")
    return unregister_callback()


def install_startup_callback(enabled=True):
    import pymxs
    rt = pymxs.runtime
    path = _startup_script_path(rt)
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    unregister_callback()
    return path

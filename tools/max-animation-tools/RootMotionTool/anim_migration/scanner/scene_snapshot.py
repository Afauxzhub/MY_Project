# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import traceback

from anim_migration.scanner.bip_scanner import scan_bip
from anim_migration.scanner.ik_scanner import scan_ik_objects
from anim_migration.scanner.controller_scanner import scan_controllers
from anim_migration.scanner.constraint_scanner import scan_constraints
from anim_migration.scanner.local_object_scanner import scan_local_objects
from anim_migration.scanner.morph_scanner import scan_morph


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
        try:
            b = str(value)
            try:
                return b.decode("utf-8")
            except Exception:
                return b.decode("gbk", "replace")
        except Exception:
            return u""


def _scan_guard(scan_errors, category, fn):
    try:
        return fn()
    except Exception as e:
        scan_errors.append(
            {
                "severity": "error",
                "category": category,
                "object_name": "",
                "controller_path": None,
                "constraint_type": None,
                "old_target": None,
                "new_target": None,
                "frame": None,
                "reason": _as_text(e),
                "possible_symptom": "该类别扫描结果缺失",
                "suggested_fix": "检查场景对象有效性并重试",
                "can_resolve_by_mapping": False,
                "traceback": _as_text(traceback.format_exc()),
            }
        )
        return {}


def build_scene_snapshot(scene_path):
    import pymxs

    rt = pymxs.runtime
    scan_errors = []
    abs_path = os.path.abspath(_as_text(scene_path)) if scene_path else u""
    current_path = _as_text(rt.maxFilePath) + _as_text(rt.maxFileName)
    restore_path = current_path if current_path and os.path.exists(current_path) else None

    loaded = False
    try:
        if (not abs_path) or (not os.path.exists(abs_path)):
            scan_errors.append(
                {
                    "severity": "error",
                    "category": "scene_path_invalid",
                    "object_name": "",
                    "controller_path": None,
                    "constraint_type": None,
                    "old_target": None,
                    "new_target": None,
                    "frame": None,
                    "reason": u"scene_path does not exist: {0}".format(_as_text(abs_path)),
                    "possible_symptom": "该场景未参与扫描",
                    "suggested_fix": "检查输入路径并重试",
                    "can_resolve_by_mapping": False,
                }
            )
            return {"scene_path": abs_path, "scene_loaded": False, "scan_errors": scan_errors}
        rt.loadMaxFile(abs_path, quiet=True, useFileUnits=True)
        loaded = True
        snapshot = {
            "scene_path": abs_path,
            "scene_loaded": loaded,
            "bip": _scan_guard(scan_errors, "bip_scan_error", lambda: scan_bip(rt)),
            "ik": _scan_guard(scan_errors, "ik_scan_error", lambda: scan_ik_objects(rt)),
            "controllers": _scan_guard(scan_errors, "controller_scan_error", lambda: scan_controllers(rt)),
            "constraints": _scan_guard(scan_errors, "constraint_scan_error", lambda: scan_constraints(rt)),
            "local_objects": _scan_guard(scan_errors, "local_object_scan_error", lambda: scan_local_objects(rt)),
            "morph": _scan_guard(scan_errors, "morph_scan_error", lambda: scan_morph(rt)),
            "scan_errors": scan_errors,
        }
        return snapshot
    finally:
        try:
            if restore_path and abs_path and os.path.abspath(restore_path) != abs_path:
                rt.loadMaxFile(restore_path, quiet=True, useFileUnits=True)
        except Exception:
            pass

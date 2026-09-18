# -*- coding: utf-8 -*-
"""局外相机导出：fileIn MaxScript，执行与 RootMotionExporterTool.ms 相同的 Timeline 相机逻辑。"""
from __future__ import division
import os

import pymxs

rt = pymxs.runtime

_MS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, u"maxscript", u"rm_outdoor_cutscene_camera_export.ms")
)


def _ensure_outdoor_camera_ms():
    if getattr(rt, u"RM_ExportOutdoorTimelineCamera", None) is not None:
        return
    if not os.path.isfile(_MS_PATH):
        raise IOError(u"局外相机 MaxScript 未找到: {0}".format(_MS_PATH))
    rt.fileIn(_MS_PATH)
    if getattr(rt, u"RM_ExportOutdoorTimelineCamera", None) is None:
        raise RuntimeError(u"fileIn 后仍未注册 RM_ExportOutdoorTimelineCamera")


def export_outdoor_timeline_camera_ms(fbx_abs_path, start_f, end_f):
    """
    导出 Main_Camera（世界空间烘焙），fbx_abs_path 为完整路径（含 .fbx）。
    成功返回 fbx_abs_path；失败抛出异常。
    """
    _ensure_outdoor_camera_ms()
    path = os.path.normpath(fbx_abs_path)
    ok = rt.RM_ExportOutdoorTimelineCamera(path, int(start_f), int(end_f))
    if not ok:
        raise RuntimeError(
            u"局外相机 MaxScript 返回失败（请确认 Main_Camera 存在且可克隆导出）。"
        )
    if not os.path.isfile(fbx_abs_path):
        raise RuntimeError(u"局外相机 FBX 未写入: {0}".format(fbx_abs_path))
    return fbx_abs_path

# -*- coding: utf-8 -*-
"""
FBX 导出引擎
  局内：Root Motion 提取（位移+旋转烘焙）+ Biped 层补偿 + FBX 导出
  局外：直接 FBX 导出（无 Root Motion，无 IK），支持多角色
完整移植并重构自 MaxScript FinalizeExport
"""
from __future__ import division
import os
import pymxs

from core.rm_math import (
    smooth_step, decode_cm,
    process_root_trajectory,
    extract_cumulative_yaw,
    detect_foot_grounding,
)
from core.rm_scene import get_all_descendants, unlock_nodes
from core.rm_outdoor_camera_ms import export_outdoor_timeline_camera_ms

rt = pymxs.runtime

_SKIN_PELVIS_NAME = u"Bone_Skin_Bip001 Pelvis"
_BIP_ROOT_NAME = u"Bip001"
_HIDE_SCALE_LIB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, u"maxscript", u"hide_scale_bake.ms")
)
_ADV_FBX_LIB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, u"maxscript", u"adv_fbx_export_v25.ms")
)


def _node_name(node):
    try:
        return unicode(node.name)
    except NameError:
        try:
            return str(node.name)
        except Exception:
            return u""
    except Exception:
        return u""


def _same_node_name(node, expected):
    return _node_name(node).lower() == expected.lower()


def _has_descendant_named(root_node, expected_name):
    if root_node is None or not rt.isValidNode(root_node):
        return False
    if _same_node_name(root_node, expected_name):
        return True
    for node in get_all_descendants(root_node):
        if rt.isValidNode(node) and _same_node_name(node, expected_name):
            return True
    return False


def _find_bip_root_under(root_node, fallback_bip=None):
    if fallback_bip is not None and rt.isValidNode(fallback_bip):
        return fallback_bip
    if root_node is None or not rt.isValidNode(root_node):
        return None
    if _same_node_name(root_node, _BIP_ROOT_NAME):
        return root_node
    for node in get_all_descendants(root_node):
        if rt.isValidNode(node) and _same_node_name(node, _BIP_ROOT_NAME):
            return node
    return None


def _filter_bip_hierarchy_for_skin_pelvis_branch(objs_to_export, root_node, fallback_bip=None):
    if not _has_descendant_named(root_node, _SKIN_PELVIS_NAME):
        return objs_to_export
    bip_root = _find_bip_root_under(root_node, fallback_bip)
    if bip_root is None or not rt.isValidNode(bip_root):
        return objs_to_export
    excluded = set()
    for node in [bip_root] + get_all_descendants(bip_root):
        try:
            excluded.add(rt.getHandleByAnim(node))
        except Exception:
            pass
    filtered = []
    for node in objs_to_export:
        try:
            handle = rt.getHandleByAnim(node)
        except Exception:
            handle = None
        if handle not in excluded:
            filtered.append(node)
    return filtered


def _uses_skin_pelvis_export_branch(root_node):
    return _has_descendant_named(root_node, _SKIN_PELVIS_NAME)


def _ensure_adv_fbx_export_lib():
    if not os.path.exists(_HIDE_SCALE_LIB_PATH):
        raise IOError(u"HideScaleBake library not found: {0}".format(_HIDE_SCALE_LIB_PATH))
    if not os.path.exists(_ADV_FBX_LIB_PATH):
        raise IOError(u"ADV FBX library not found: {0}".format(_ADV_FBX_LIB_PATH))
    rt.fileIn(_HIDE_SCALE_LIB_PATH)
    rt.fileIn(_ADV_FBX_LIB_PATH)
    for symbol in (
        u"RMTool_HideScale_CaptureNodes",
        u"RMTool_HideScale_ContextHasNonUnit",
        u"RMTool_HideScale_ApplyToBakeNodes",
    ):
        if not hasattr(rt, symbol):
            raise RuntimeError(u"Failed to load HideScaleBake library: {0}".format(symbol))
    if not hasattr(rt, u"RMTool_ADV_ExportRootHierarchy"):
        raise RuntimeError(u"Failed to load ADV FBX library")


def _ensure_clean_baked_export_helper():
    # Legacy embedded clean-bake removed; custom-rig path uses ADV V2.5.
    _ensure_adv_fbx_export_lib()


def _to_mxs_array(nodes):
    arr = rt.Array()
    for node in nodes:
        if node is not None:
            try:
                if rt.isValidNode(node):
                    rt.append(arr, node)
            except Exception:
                pass
    return arr


def _export_clean_baked_hierarchy(
    objs_to_export,
    out_path,
    start_f,
    end_f,
    total_offset=None,
    extra_nodes=None,
    morph_nodes=None,
    auto_morph=True,
):
    """
    Custom Skin/Twist rig export via ADV V2.5 (Local Matrix3 bake + Bip001 rename).
    objs_to_export[0] must be Root. Extra nodes (e.g. weapon helpers outside Root)
    are merged into the ADV export set.
    morph_nodes: explicit Morpher meshes (局外勾选). When empty and auto_morph,
    ADV scans the full scene (局内).
    """
    _ensure_adv_fbx_export_lib()
    if not objs_to_export:
        raise RuntimeError(u"ADV FBX export: empty node list")
    root_node = objs_to_export[0]
    if root_node is None or not rt.isValidNode(root_node):
        raise RuntimeError(u"ADV FBX export: invalid Root")
    if total_offset is None:
        total_offset = rt.Point3(0.0, 0.0, 0.0)
    extras = []
    if extra_nodes:
        extras.extend(list(extra_nodes))
    # Nodes appended after Root (e.g. outdoor weapon temps) that sit outside Root.
    morph_set = set()
    for n in morph_nodes or []:
        try:
            morph_set.add(int(rt.getHandleByAnim(n)))
        except Exception:
            morph_set.add(id(n))
    for n in objs_to_export[1:]:
        if n is None:
            continue
        try:
            if not rt.isValidNode(n):
                continue
        except Exception:
            continue
        try:
            handle = int(rt.getHandleByAnim(n))
        except Exception:
            handle = id(n)
        if handle in morph_set:
            # Morpher meshes must not enter ADV bake bone set.
            continue
        p = n
        under_root = False
        while p is not None:
            if p == root_node:
                under_root = True
                break
            try:
                p = p.parent
            except Exception:
                break
        if not under_root and n not in extras:
            extras.append(n)
    ok = bool(
        rt.RMTool_ADV_ExportRootHierarchy(
            root_node,
            out_path,
            int(start_f),
            int(end_f),
            excludeBiped=True,
            strictValidate=False,
            keepBake=False,
            totalOffset=total_offset,
            extraNodes=_to_mxs_array(extras),
            morphMeshes=_to_mxs_array(list(morph_nodes or [])),
            autoMorph=bool(auto_morph),
        )
    )
    if not ok:
        raise RuntimeError(u"ADV FBX export failed: {0}".format(out_path))



def _validate_fbx_scale_export(fbx_path):
    """
    Read-only check after export. Never rewrites FBX.
    Warns if ScaleXYZ percent*10 signature (~1.0 mixed with 200..5000) reappears,
    or if scale peaks look like 1800-class corruption.
    """
    if not fbx_path or not os.path.isfile(fbx_path):
        return False
    try:
        from core.fix_fbx_scale_curves import validate_fbx_scale_export
    except Exception:
        try:
            from fix_fbx_scale_curves import validate_fbx_scale_export
        except Exception as ex:
            print(u"[RMTool] scale-validate import failed: {0}".format(ex))
            return False
    try:
        ok, reports = validate_fbx_scale_export(fbx_path)
        for line in reports:
            print(u"[RMTool] scale-validate: {0}".format(line))
        if not ok:
            print(u"[RMTool] scale-validate WARN: {0}".format(fbx_path))
        return ok
    except Exception as ex:
        import traceback
        print(u"[RMTool] scale-validate failed: {0}".format(ex))
        print(u"[RMTool] scale-validate traceback:\n{0}".format(traceback.format_exc()))
        return False


def _fix_fbx_percent_times10_only(fbx_path):
    """Official direct-export: never rewrite scale or translation.

    This path is only used for simple/controllable clips. Hide-scale and
    percent*10 repairs used to mutate authored curves (e.g. mask 0.01 -> 1).
    """
    return False


def _get_transform_controller(node):
    try:
        return node.controller
    except Exception:
        pass
    try:
        return rt.getPropertyController(node, rt.Name("transform"))
    except Exception:
        pass
    try:
        return rt.getPropertyController(node, u"transform")
    except Exception:
        pass
    return None


def _normalize_prop_name(prop_name):
    if prop_name in (u"pos", u"position"):
        return u"position"
    if prop_name in (u"rotation", u"scale", u"transform"):
        return prop_name
    return prop_name


def _get_property_controller(node, prop_name):
    prop_name = _normalize_prop_name(prop_name)
    if prop_name == u"transform":
        return _get_transform_controller(node)
    try:
        return rt.getPropertyController(node, rt.Name(prop_name))
    except Exception:
        pass
    try:
        return rt.getPropertyController(node, prop_name)
    except Exception:
        pass
    return None


def _set_property_controller(node, prop_name, controller):
    prop_name = _normalize_prop_name(prop_name)
    try:
        rt.setPropertyController(node, rt.Name(prop_name), controller)
        return True
    except Exception:
        pass
    try:
        rt.setPropertyController(node, prop_name, controller)
        return True
    except Exception:
        pass
    return False


def _ensure_property_controller(node, prop_name, expected_class, controller_factory):
    ctrl = _get_property_controller(node, prop_name)
    if ctrl is not None and rt.classof(ctrl) == expected_class:
        return ctrl
    if _set_property_controller(node, prop_name, controller_factory()):
        ctrl = _get_property_controller(node, prop_name)
    return ctrl


def _to_euler_angles(rot_value):
    if rot_value is None:
        return rt.eulerangles(0.0, 0.0, 0.0)
    rot_class = rt.classof(rot_value)
    if rot_class == rt.EulerAngles:
        return rot_value
    if rot_class == rt.Quat:
        try:
            return rt.execute(
                u"((quat {0} {1} {2} {3}) as eulerangles)".format(
                    repr(float(rot_value.x)),
                    repr(float(rot_value.y)),
                    repr(float(rot_value.z)),
                    repr(float(rot_value.w)),
                )
            )
        except Exception:
            pass
    try:
        return rt.execute(u"({0} as eulerangles)".format(rot_value))
    except Exception:
        return rt.eulerangles(0.0, 0.0, 0.0)


# ──────────────────────────────────────────────────────────────────
# 导出参数数据类
# ──────────────────────────────────────────────────────────────────

class ExportSettings(object):
    """局内导出的全部参数，由主窗口填充后传入 run_export()"""

    def __init__(self):
        # 场景对象
        self.bip_obj  = None
        self.root_obj = None

        # 位移提取
        self.enable_pos        = True
        self.follow_x          = False
        self.follow_y          = True
        self.follow_z          = False
        self.z_thres_cm        = 50.0
        self.z_weight          = 1.0
        self.z_limit_range     = False
        self.z_limit_start     = 0
        self.z_limit_end       = 100
        self.z_hover           = False
        self.z_hover_height_cm = 150.0
        self.z_hover_start     = 0
        self.z_hover_end       = 30
        self.use_smooth        = False
        self.filter_val        = 10.0
        self.smooth_str        = 1
        self.smooth_limit_range  = False
        self.smooth_limit_start  = 0
        self.smooth_limit_end    = 100
        # 位移根运动：仅在此帧区间内应用提取结果（区间外 Root 位移为 0；不影响旋转根运动）
        self.pos_rm_limit_range = False
        self.pos_rm_start       = 0
        self.pos_rm_end         = 100
        self.offset_x          = 0.0
        self.offset_y          = 0.0
        self.offset_z          = 0.0

        # 旋转提取
        self.enable_rot = False
        # 自定义 Root 旋转目标角度（不跟质心累计偏航）
        self.rot_custom_angle = False
        self.rot_custom_degrees = 180.0
        self.rot_custom_dir = u"auto"  # auto=跟随质心符号 / left=+ / right=-
        # 指定旋转跟随起止帧（区间内 S 曲线）
        self.rot_limit_range = False
        self.rot_limit_start = 0
        self.rot_limit_end = 100

        # 高级
        self.force_keys      = True
        self.fix_rot         = True
        self.remove_initial_z = True
        self.unlock          = True

        # 摄像机导出
        self.exp_timeline_cam = False
        self.exp_ingame_cam   = False
        self.only_cam         = False

        # 分段导出 [(name, start_f, end_f), ...]
        self.split_data = []
        self.wallhit_root_motion = False
        # Experimental Proxy Root publisher only. Legacy RM_Fix ignores this.
        self.proxy_sample_rate_hz = 30

        # 文件路径
        self.orig_file_path = u""
        self.orig_file_name = u""
        self.fbx_folder     = u""


# ──────────────────────────────────────────────────────────────────
# 内部：工具函数
# ──────────────────────────────────────────────────────────────────

def _get_all_transforms(bip_obj, start_f, end_f):
    """逐帧采集 Biped 变换列表（在 IK 斩断之后调用，保证纯 FK）"""
    transforms = []
    for i in range(start_f, end_f + 1):
        with pymxs.attime(i):
            transforms.append(bip_obj.transform)
    return transforms


def _fix_root_rotation(root_obj):
    """
    预处理 Root 节点：确保位置为原点，X 轴旋转为 90°。
    对应原脚本 chk_fixRot 逻辑。
    """
    p  = root_obj.pos
    cur_rot = _to_euler_angles(root_obj.rotation)
    rx = cur_rot.x
    ry = cur_rot.y
    rz = cur_rot.z

    needs_fix = (
        rt.distance(p, rt.Point3(0, 0, 0)) > 0.01
        or abs(rx - 90.0) > 0.1
        or abs(ry)        > 0.1
        or abs(rz)        > 0.1
    )
    if not needs_fix:
        return

    children = list(root_obj.children)
    for c in children:
        c.parent = None
    root_ctrl = _get_transform_controller(root_obj)
    if root_ctrl is not None:
        rt.deleteKeys(root_ctrl, rt.Name("allKeys"))
    root_obj.pos = rt.Point3(0, 0, 0)
    root_obj.rotation = rt.eulerangles(90.0, 0.0, 0.0)
    for c in children:
        c.parent = root_obj


def _try_load_official_fbx_preset():
    """Load Autodesk Media & Entertainment preset when present (2014/2016 style)."""
    candidates = []
    for getter, rels in (
        (u"maxData", (
            u"FBX\\export presets\\Autodesk Media & Entertainment.fbxexportpreset",
            u"FBX\\export presets\\Autodesk Media and Entertainment.fbxexportpreset",
        )),
        (u"maxRoot", (
            u"plugcfg_ln\\FBX\\export presets\\Autodesk Media & Entertainment.fbxexportpreset",
            u"plugcfg\\FBX\\export presets\\Autodesk Media & Entertainment.fbxexportpreset",
        )),
    ):
        try:
            base = rt.getDir(rt.Name(getter))
        except Exception:
            base = u""
        if not base:
            continue
        try:
            base_s = u"{0}".format(base)
        except Exception:
            base_s = str(base)
        for rel in rels:
            candidates.append(os.path.join(base_s, rel))
    for path in candidates:
        try:
            if path and os.path.isfile(path):
                rt.FBXExporterSetParam(u"LoadExportPresetFile", path)
                print(u"[RMTool] loaded FBX export preset: {0}".format(path))
                return True
        except Exception:
            continue
    return False


def _set_fbx_params(s, e, cameras=False):
    """官方 Media & Entertainment 预设为底，再覆盖项目必需项。"""
    _try_load_official_fbx_preset()
    rt.FBXExporterSetParam(u"Animation",    True)
    rt.FBXExporterSetParam(u"BakeAnimation", True)
    rt.FBXExporterSetParam(u"BakeFrameStart", s)
    rt.FBXExporterSetParam(u"BakeFrameEnd",   e)
    rt.FBXExporterSetParam(u"UpAxis",       u"Y")
    rt.FBXExporterSetParam(u"ShowWarnings", False)
    if cameras:
        rt.FBXExporterSetParam(u"Cameras", True)
    else:
        # Morpher / blend-shape animation (harmless when selection has no Morpher).
        try:
            rt.FBXExporterSetParam(u"Shape", True)
        except Exception:
            pass


def _node_has_morpher(node):
    if node is None:
        return False
    try:
        if not rt.isValidNode(node):
            return False
    except Exception:
        return False
    try:
        for m in list(node.modifiers):
            try:
                if rt.classOf(m) == rt.Morpher:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _node_handle(node):
    try:
        return int(rt.getHandleByAnim(node))
    except Exception:
        return id(node)


def scan_scene_morpher_meshes():
    """Scan whole scene for Morpher meshes. Returns [{'name': str, 'node': node}, ...]."""
    result = []
    seen = set()
    try:
        objects = list(rt.objects)
    except Exception:
        objects = []
    for n in objects:
        if not _node_has_morpher(n):
            continue
        key = _node_handle(n)
        if key in seen:
            continue
        seen.add(key)
        try:
            name = unicode(n.name)
        except NameError:
            name = str(n.name)
        except Exception:
            name = u"<unnamed>"
        result.append({u"name": name, u"node": n})
    result.sort(key=lambda x: x[u"name"].lower())
    return result


def _collect_morpher_meshes(root_node=None, scene_wide=False, morph_nodes=None):
    """
    Collect Morpher meshes.
    - morph_nodes: explicit list (局外勾选)
    - scene_wide: full scene (局内)
    - else: legacy under root/parent (unused; prefer scene_wide / morph_nodes)
    """
    result = []
    seen = set()

    def _add(n):
        if n is None:
            return
        try:
            if not rt.isValidNode(n):
                return
        except Exception:
            return
        if not _node_has_morpher(n):
            return
        key = _node_handle(n)
        if key in seen:
            return
        seen.add(key)
        result.append(n)

    if morph_nodes is not None:
        for n in morph_nodes:
            _add(n)
        return result

    if scene_wide or root_node is None:
        try:
            for n in list(rt.objects):
                _add(n)
        except Exception:
            pass
        return result

    def _gather_under(node):
        if node is None:
            return
        try:
            if not rt.isValidNode(node):
                return
        except Exception:
            return
        _add(node)
        try:
            for d in get_all_descendants(node):
                _add(d)
        except Exception:
            pass

    _gather_under(root_node)
    try:
        parent = root_node.parent
    except Exception:
        parent = None
    if parent is not None:
        _gather_under(parent)
    return result


def _merge_morpher_meshes(objs_to_export, root_node=None, morph_nodes=None, scene_wide=False):
    out = []
    seen = set()

    def _add(n):
        if n is None:
            return
        try:
            if not rt.isValidNode(n):
                return
        except Exception:
            return
        key = _node_handle(n)
        if key in seen:
            return
        seen.add(key)
        out.append(n)

    for n in objs_to_export or []:
        _add(n)
    morphs = _collect_morpher_meshes(
        root_node=root_node, scene_wide=scene_wide, morph_nodes=morph_nodes
    )
    if morphs:
        print(u"[RMTool] Morpher include shape meshes={0}".format(len(morphs)))
        for n in morphs:
            _add(n)
    return out


def _weapon_temp_attachment_nodes():
    out = []
    try:
        objects = list(rt.objects)
    except Exception:
        objects = []
    for node in objects:
        if not rt.isValidNode(node):
            continue
        mark = u""
        try:
            mark = rt.getUserProp(node, u"OPWeaponTemp")
        except Exception:
            pass
        if mark == u"OP_WS_TEMP_ATTACHMENT":
            out.append(node)
    return out


# ──────────────────────────────────────────────────────────────────
# 内部：Root Motion 烘焙（局内核心）
# ──────────────────────────────────────────────────────────────────

def _bake_root_motion(root_obj, bip_obj, settings, total_start_f, total_end_f, original_transforms):
    """
    将 Biped 的世界运动烘焙到 Root 节点，并在 Biped 层上做反向补偿。
    返回 raw_root_pos_list（供后续归零偏移使用）。
    """
    # 清空 Root 上的旧 Key
    rot_ctrl = _get_property_controller(root_obj, u"rotation")
    pos_ctrl = _get_property_controller(root_obj, u"position")
    if rot_ctrl is not None:
        rt.deleteKeys(rot_ctrl, rt.Name("allKeys"))
    if pos_ctrl is not None:
        rt.deleteKeys(pos_ctrl, rt.Name("allKeys"))
    try:
        scale_ctrl = _get_property_controller(root_obj, u"scale")
        if scale_ctrl is not None:
            rt.deleteKeys(scale_ctrl, rt.Name("allKeys"))
    except Exception:
        pass

    # 记录基础旋转（以起始帧为准）
    with pymxs.attime(total_start_f):
        base_rot = _to_euler_angles(root_obj.rotation)
    base_x = base_rot.x
    base_y = base_rot.y
    base_z = base_rot.z

    count              = len(original_transforms)
    raw_root_pos_list  = []

    # ── 构建原始位置列表 ────────────────────────────────────────
    if settings.enable_pos:
        is_gnd, com_z_arr = detect_foot_grounding(
            bip_obj, total_start_f, total_end_f, settings.z_thres_cm
        )

        for tm in original_transforms:
            p = rt.Point3(0.0, 0.0, 0.0)
            if settings.follow_x:
                p.x = tm.pos.x
            if settings.follow_y:
                p.y = tm.pos.y
            raw_root_pos_list.append(p)

        # 轨迹平滑（仅 XY）
        if settings.use_smooth:
            idx_start = 0
            idx_end   = count - 1
            if settings.smooth_limit_range:
                idx_start = max(0, settings.smooth_limit_start - total_start_f)
                idx_end   = min(count - 1, settings.smooth_limit_end - total_start_f)
            if idx_end > idx_start:
                sub     = raw_root_pos_list[idx_start : idx_end + 1]
                smoothed = process_root_trajectory(sub, settings.smooth_str, settings.filter_val)
                for k, v in enumerate(smoothed):
                    raw_root_pos_list[idx_start + k] = v

        # Z 轴处理（入场动画负值免归零特判在归零偏移阶段处理）
        for i in range(count):
            current_frame = total_start_f + i
            if settings.follow_z:
                in_range = True
                if settings.z_limit_range:
                    if current_frame < settings.z_limit_start or current_frame > settings.z_limit_end:
                        in_range = False
                if in_range:
                    if is_gnd[i]:
                        raw_root_pos_list[i].z = 0.0
                    else:
                        ref_com_z = None
                        for j in range(i, -1, -1):
                            if is_gnd[j]:
                                ref_com_z = com_z_arr[j]
                                break
                        if ref_com_z is None:
                            for j in range(i, count):
                                if is_gnd[j]:
                                    ref_com_z = com_z_arr[j]
                                    break
                        if ref_com_z is not None:
                            calc_z = (com_z_arr[i] - ref_com_z) * settings.z_weight
                        else:
                            calc_z = (com_z_arr[i] - com_z_arr[0]) * settings.z_weight
                        raw_root_pos_list[i].z = max(0.0, calc_z)
                else:
                    raw_root_pos_list[i].z = 0.0
            else:
                raw_root_pos_list[i].z = 0.0

        # Z 悬停覆盖
        if settings.follow_z and settings.z_hover:
            hover_z = decode_cm(settings.z_hover_height_cm)
            for i in range(count):
                f = total_start_f + i
                if settings.z_hover_start <= f <= settings.z_hover_end:
                    raw_root_pos_list[i].z = hover_z

        if getattr(settings, u"pos_rm_limit_range", False):
            ps = int(getattr(settings, u"pos_rm_start", 0))
            pe = int(getattr(settings, u"pos_rm_end", 0))
            if ps > pe:
                ps, pe = pe, ps
            for i in range(count):
                f = total_start_f + i
                if f < ps or f > pe:
                    raw_root_pos_list[i] = rt.Point3(0.0, 0.0, 0.0)

    # ── 旋转计算 ────────────────────────────────────────────────
    target_angle  = 0.0
    rot_start     = total_start_f
    rot_end       = total_end_f
    rot_duration  = 1.0

    if settings.enable_rot:
        use_custom_angle = bool(getattr(settings, u"rot_custom_angle", False))
        use_custom_range = bool(getattr(settings, u"rot_limit_range", False))
        yaw_arr = None

        if use_custom_angle:
            degrees = abs(float(getattr(settings, u"rot_custom_degrees", 180.0) or 0.0))
            direction = u"{0}".format(getattr(settings, u"rot_custom_dir", u"auto") or u"auto").lower()
            if direction in (u"right", u"cw", u"-", u"clockwise"):
                target_angle = -degrees
            elif direction in (u"left", u"ccw", u"+", u"counterclockwise"):
                target_angle = degrees
            else:
                # auto: 跟随质心累计偏航方向
                yaw_arr = extract_cumulative_yaw(original_transforms)
                com_yaw = yaw_arr[-1] if yaw_arr else 0.0
                if com_yaw < 0.0:
                    target_angle = -degrees
                else:
                    target_angle = degrees
        else:
            yaw_arr = extract_cumulative_yaw(original_transforms)
            target_angle = yaw_arr[-1] if yaw_arr else 0.0

        if use_custom_range:
            rot_start = int(getattr(settings, u"rot_limit_start", total_start_f))
            rot_end = int(getattr(settings, u"rot_limit_end", total_end_f))
            if rot_start > rot_end:
                rot_start, rot_end = rot_end, rot_start
            if rot_end <= rot_start:
                rot_end = rot_start + 1
            rot_duration = float(rot_end - rot_start)
        elif use_custom_angle:
            # 自定义角度但无帧区间：整段动画做 S 曲线，避免按质心 5%~95% 误判窗口。
            rot_start = total_start_f
            rot_end = total_end_f
            if rot_end <= rot_start:
                rot_end = rot_start + 1
            rot_duration = float(rot_end - rot_start)
        elif abs(target_angle) > 2.0:
            if yaw_arr is None:
                yaw_arr = extract_cumulative_yaw(original_transforms)
            t_start  = target_angle * 0.05
            t_end    = target_angle * 0.95
            s_found  = False
            for i, yaw in enumerate(yaw_arr):
                if not s_found and abs(yaw) >= abs(t_start):
                    rot_start = total_start_f + i
                    s_found   = True
                if abs(yaw) <= abs(t_end):
                    rot_end = total_start_f + i
            if rot_end <= rot_start:
                rot_end = rot_start + 1
            rot_duration = float(rot_end - rot_start)

    # ── 烘焙旋转到 Root ─────────────────────────────────────────
    if settings.enable_rot:
        with pymxs.animate(True):
            for i in range(total_start_f, total_end_f + 1):
                with pymxs.attime(i):
                    added = 0.0
                    if i >= rot_end:
                        added = target_angle
                    elif i > rot_start:
                        prog  = smooth_step(float(i - rot_start) / rot_duration)
                        added = target_angle * prog
                    root_obj.rotation = rt.eulerangles(base_x, base_y, base_z + added)

    # ── 烘焙位移到 Root ─────────────────────────────────────────
    if settings.enable_pos and raw_root_pos_list:
        with pymxs.animate(True):
            for i in range(total_start_f, total_end_f + 1):
                with pymxs.attime(i):
                    idx = i - total_start_f
                    if idx < len(raw_root_pos_list):
                        root_obj.pos = raw_root_pos_list[idx]

    # ── Biped 层反向补偿 ─────────────────────────────────────────
    if (settings.enable_rot or settings.enable_pos) and not settings.only_cam:
        bip_ctrl  = _get_transform_controller(bip_obj)
        if bip_ctrl is not None:
            layer_idx = rt.biped.numLayers(bip_ctrl) + 1
            rt.biped.createLayer(bip_ctrl, layer_idx, u"RM_Fix")
            rt.biped.setCurrentLayer(bip_ctrl, layer_idx)

            custom_offset = rt.Point3(settings.offset_x, settings.offset_y, settings.offset_z)
            with pymxs.animate(True):
                for i in range(total_start_f, total_end_f + 1):
                    with pymxs.attime(i):
                        idx = i - total_start_f
                        if idx < len(original_transforms):
                            tm = original_transforms[idx]
                            rt.biped.setTransform(bip_obj, rt.Name("pos"),
                                                  rt.Point3(tm.pos.x + custom_offset.x,
                                                            tm.pos.y + custom_offset.y,
                                                            tm.pos.z + custom_offset.z), True)
                            rt.biped.setTransform(bip_obj, rt.Name("rotation"), tm.rotation, True)

    return raw_root_pos_list


# ──────────────────────────────────────────────────────────────────
# 内部：单片段 FBX 导出
# ──────────────────────────────────────────────────────────────────

def _export_fbx_segment(settings, task_name, s, e, raw_root_pos_list):
    """
    导出单个时间片段的 FBX。
    包含：摄像机克隆烘焙、归零偏移（含入场特判）、FBX 写入、偏移恢复。
    返回导出的 FBX 完整路径列表。
    """
    from pipeline.rm_naming import clean_string_native

    rt.animationRange = rt.interval(s, e)

    # ── 摄像机克隆与烘焙 ────────────────────────────────────────
    target_cam      = rt.getNodeByName(u"Main_Camera")
    cam_nodes_world = []
    cam_nodes_local = []
    orig_cam_names  = []

    if (settings.exp_timeline_cam or settings.exp_ingame_cam) and target_cam is not None:
        nodes_to_clone = [target_cam] + get_all_descendants(target_cam)
        for n in nodes_to_clone:
            orig_cam_names.append(n.name)

        if settings.exp_timeline_cam:
            new_nodes = rt.Array()
            rt.maxOps.CloneNodes(
                rt.Array(*nodes_to_clone), cloneType=rt.Name("copy"),
                newNodes=new_nodes, offset=rt.Point3(0, 0, 0), expandHierarchy=False
            )
            cam_nodes_world = list(new_nodes)
            br = cam_nodes_world[0]
            br.parent = None
            try:
                _set_property_controller(br, u"position", rt.Position_XYZ())
                _set_property_controller(br, u"rotation", rt.Euler_XYZ())
            except Exception:
                pass
            with pymxs.animate(True):
                for t in range(s, e + 1):
                    with pymxs.attime(t):
                        tm = target_cam.transform
                        br.transform = rt.matrix3(
                            rt.normalize(tm.row1),
                            rt.normalize(tm.row2),
                            rt.normalize(tm.row3),
                            tm.row4,
                        )

        if settings.exp_ingame_cam:
            new_nodes = rt.Array()
            rt.maxOps.CloneNodes(
                rt.Array(*nodes_to_clone), cloneType=rt.Name("copy"),
                newNodes=new_nodes, offset=rt.Point3(0, 0, 0), expandHierarchy=False
            )
            cam_nodes_local = list(new_nodes)
            br = cam_nodes_local[0]
            br.parent = None
            try:
                _set_property_controller(br, u"position", rt.Position_XYZ())
                _set_property_controller(br, u"rotation", rt.Euler_XYZ())
            except Exception:
                pass
            with pymxs.animate(True):
                for t in range(s, e + 1):
                    with pymxs.attime(t):
                        cam_tm   = target_cam.transform
                        root_tm  = settings.root_obj.transform
                        virt_tm  = rt.preRotateX(root_tm, -90.0)
                        final_tm = cam_tm * rt.inverse(virt_tm)
                        br.transform = rt.matrix3(
                            rt.normalize(final_tm.row1),
                            rt.normalize(final_tm.row2),
                            rt.normalize(final_tm.row3),
                            final_tm.row4,
                        )

    # ── 归零偏移（含入场动画负值免归零特判）───────────────────────
    actual_suffix = (u"_" + task_name) if task_name else u""
    base_name     = clean_string_native(
        os.path.splitext(settings.orig_file_name)[0], actual_suffix
    )

    with pymxs.attime(s):
        root_start = rt.Point3(settings.root_obj.pos.x,
                               settings.root_obj.pos.y,
                               settings.root_obj.pos.z)
    with pymxs.attime(e):
        root_end = rt.Point3(settings.root_obj.pos.x,
                             settings.root_obj.pos.y,
                             settings.root_obj.pos.z)

    offset_x = root_start.x if settings.follow_x else 0.0

    # Y 轴入场特判：起始帧 Y < -5cm 且末帧 |Y| < 5cm → 不归零
    offset_y = 0.0
    if settings.follow_y:
        thres_neg = decode_cm(-5.0)
        thres_pos = decode_cm(5.0)
        is_entrance = (root_start.y < thres_neg) and (abs(root_end.y) < thres_pos)
        if not is_entrance:
            offset_y = root_start.y

    offset_z = root_start.z if (settings.remove_initial_z and settings.follow_z) else 0.0

    total_offset = rt.Point3(-offset_x, -offset_y, -offset_z)
    use_clean_bake_export = False
    if not settings.only_cam:
        use_clean_bake_export = _uses_skin_pelvis_export_branch(settings.root_obj)
    moved_live_root = False
    # ADV offsets TEMP bake root only; do not move live Root on custom-rig path.
    if (not use_clean_bake_export) and rt.length(total_offset) > 0.001:
        with pymxs.animate(False):
            rt.move(settings.root_obj, total_offset)
        moved_live_root = True

    # ── 导出角色 FBX ────────────────────────────────────────────
    exported_paths = []
    char_path = os.path.join(settings.fbx_folder, base_name + u".fbx")

    if not settings.only_cam:
        objs = [settings.root_obj] + get_all_descendants(settings.root_obj)
        objs = _filter_bip_hierarchy_for_skin_pelvis_branch(
            objs,
            settings.root_obj,
            getattr(settings, "bip_obj", None),
        )
        weapon_extras = _weapon_temp_attachment_nodes()
        objs.extend(weapon_extras)
        if settings.unlock:
            unlock_nodes(objs)

        if use_clean_bake_export:
            _export_clean_baked_hierarchy(
                objs, char_path, s, e, total_offset=total_offset, extra_nodes=weapon_extras
            )
        else:
            objs = _merge_morpher_meshes(objs, settings.root_obj, scene_wide=True)
            rt.select(objs)

            if settings.force_keys:
                for o in objs:
                    if not rt.isValidNode(o):
                        continue
                    if rt.classof(o) == rt.Biped_Object:
                        continue
                    cls = rt.classof(o)
                    if cls in (rt.BoneGeometry, rt.Dummy, rt.Point, rt.Bone) or o == settings.root_obj:
                        for attr in (u"position", u"rotation", u"scale"):
                            try:
                                ctrl = _get_property_controller(o, attr)
                                if ctrl is not None:
                                    rt.addNewKey(ctrl, s)
                                    rt.addNewKey(ctrl, e)
                            except Exception:
                                pass

            _set_fbx_params(s, e)
            rt.exportFile(char_path, rt.Name("noPrompt"), selectedOnly=True, using=rt.FBXEXP)
        if not use_clean_bake_export:
            _fix_fbx_percent_times10_only(char_path)
        _validate_fbx_scale_export(char_path)
        exported_paths.append(char_path)

    # ── 导出摄像机 FBX ───────────────────────────────────────────
    for cam_nodes, suffix in [(cam_nodes_world, u"_Cam_CS"), (cam_nodes_local, u"_Cam")]:
        if not cam_nodes:
            continue
        for k, node in enumerate(cam_nodes):
            node.name = orig_cam_names[k] + u"001"
        rt.select(cam_nodes)
        cam_path = os.path.join(settings.fbx_folder, base_name + suffix + u".fbx")
        _set_fbx_params(s, e, cameras=True)
        rt.exportFile(cam_path, rt.Name("noPrompt"), selectedOnly=True, using=rt.FBXEXP)
        rt.delete(cam_nodes)
        exported_paths.append(cam_path)

    # ── 恢复归零偏移 ─────────────────────────────────────────────
    if moved_live_root:
        with pymxs.animate(False):
            rt.move(settings.root_obj, rt.Point3(-total_offset.x, -total_offset.y, -total_offset.z))

    return exported_paths


# ──────────────────────────────────────────────────────────────────
# 公开接口：局内导出
# ──────────────────────────────────────────────────────────────────

def run_export(settings):
    """
    局内主导出流程：
      1. IK 已在调用方（主窗口）斩断
      2. 采集 Biped 变换 → Root Motion 烘焙
      3. 逐片段 FBX 导出
    返回导出的 FBX 路径列表。
    """
    total_start_f  = int(rt.animationRange.start.frame)
    total_end_f    = int(rt.animationRange.end.frame)
    original_range = rt.animationRange

    tasks = settings.split_data if settings.split_data else [(u"", total_start_f, total_end_f)]

    use_rm             = settings.enable_pos or settings.enable_rot
    raw_root_pos_list  = []

    if use_rm:
        if settings.fix_rot:
            _fix_root_rotation(settings.root_obj)

        original_transforms = _get_all_transforms(settings.bip_obj, total_start_f, total_end_f)
        raw_root_pos_list   = _bake_root_motion(
            settings.root_obj, settings.bip_obj, settings,
            total_start_f, total_end_f, original_transforms
        )

    if not os.path.exists(settings.fbx_folder):
        os.makedirs(settings.fbx_folder)

    exported_paths = []
    for (task_name, s, e) in tasks:
        exported_paths.extend(
            _export_fbx_segment(settings, task_name, s, e, raw_root_pos_list)
        )

    rt.animationRange = original_range
    return exported_paths


# ──────────────────────────────────────────────────────────────────
# 公开接口：局外导出
# ──────────────────────────────────────────────────────────────────

def run_cutscene_export(
    char_info,
    fbx_folder,
    fbx_name,
    start_f,
    end_f,
    export_camera=False,
    only_camera=False,
    camera_fbx_name=u"",
    morph_nodes=None,
    use_proxy_export=False,
    proxy_sample_rate_hz=30,
):
    """
    局外导出流程（无 Root Motion，无 IK 处理）。

    char_info : {'name': str, 'bip': Biped_Object, 'root': BoneNode} 或 None
    fbx_name  : 完整 FBX 文件名（不含扩展名），已通过命名校验
    morph_nodes : 发布页签勾选的 Morpher 模型列表（不自动全场景）
    use_proxy_export : 正式入口下，角色 FBX 使用与局内相同的 ProxyRoot 内核
    proxy_sample_rate_hz : ProxyRoot 输出采样率（30/60/120）
    返回      : 导出的 FBX 完整路径列表
    """
    exported_paths = []
    objs_to_export = []
    use_clean_bake_export = False
    selected_morphs = list(morph_nodes or [])
    if not only_camera:
        if char_info is None:
            raise ValueError(u"角色导出时缺少 char_info")
        export_root = char_info.get(u"root") or char_info.get(u"bip")
        use_clean_bake_export = _uses_skin_pelvis_export_branch(export_root)
        if char_info[u"root"] is not None and rt.isValidNode(char_info[u"root"]):
            objs_to_export = [char_info[u"root"]] + get_all_descendants(char_info[u"root"])
        elif char_info[u"bip"] is not None and rt.isValidNode(char_info[u"bip"]):
            objs_to_export = [char_info[u"bip"]] + get_all_descendants(char_info[u"bip"])
        objs_to_export = _filter_bip_hierarchy_for_skin_pelvis_branch(
            objs_to_export,
            export_root,
            char_info.get(u"bip"),
        )
        objs_to_export.extend(_weapon_temp_attachment_nodes())
        if not use_clean_bake_export and selected_morphs:
            objs_to_export = _merge_morpher_meshes(
                objs_to_export, export_root, morph_nodes=selected_morphs, scene_wide=False
            )

    rt.animationRange = rt.interval(start_f, end_f)

    if not os.path.exists(fbx_folder):
        os.makedirs(fbx_folder)

    if objs_to_export:
        out_path = os.path.join(fbx_folder, fbx_name + u".fbx")
        if use_proxy_export:
            from core.rm_outdoor_proxy_runner import export_outdoor_character_proxy

            proxy_root = char_info.get(u"root") or char_info.get(u"bip")
            export_outdoor_character_proxy(
                proxy_root,
                char_info.get(u"bip"),
                out_path,
                start_f,
                end_f,
                sample_rate_hz=proxy_sample_rate_hz,
                use_adv_export=use_clean_bake_export,
                extra_nodes=_weapon_temp_attachment_nodes(),
                morph_nodes=selected_morphs,
                progress_title=fbx_name,
            )
        elif use_clean_bake_export:
            _export_clean_baked_hierarchy(
                objs_to_export,
                out_path,
                start_f,
                end_f,
                morph_nodes=selected_morphs,
                auto_morph=False,
            )
        else:
            rt.select(objs_to_export)
            _set_fbx_params(start_f, end_f)
            rt.exportFile(out_path, rt.Name("noPrompt"), selectedOnly=True, using=rt.FBXEXP)
        if not use_proxy_export and not use_clean_bake_export:
            _fix_fbx_percent_times10_only(out_path)
        if not use_proxy_export:
            _validate_fbx_scale_export(out_path)
        exported_paths.append(out_path)

    if export_camera:
        cam_name = camera_fbx_name or (fbx_name + u"_Cam")
        cam_path = os.path.join(fbx_folder, cam_name + u".fbx")
        export_outdoor_timeline_camera_ms(cam_path, start_f, end_f)
        exported_paths.append(cam_path)

    return exported_paths

# -*- coding: utf-8 -*-
"""
数学内核：轨迹处理、平滑、偏航角提取、足部落地检测
完整移植自 MaxScript RootMotionExporterTool v6.62607015
"""
from __future__ import division
import math
import pymxs

rt = pymxs.runtime  # pymxs 在 Max 内部导入时安全，core 模块只在 Max 环境下运行


def smooth_step(val):
    """三次平滑插值 S 曲线：val * val * (3 - 2 * val)"""
    return val * val * (3.0 - 2.0 * val)


def decode_cm(value_cm):
    """将厘米数值解码为 Max 内部单位"""
    return rt.units.decodeValue(u"{0}cm".format(value_cm))


def process_root_trajectory(raw_pos_list, smooth_str, input_thres_cm):
    """
    轨迹三阶管线处理：
      阶段1 — 距离阈值过滤（锁定微小抖动帧）
      阶段2 — 移动平均平滑
      阶段3 — 末端漂移补偿（将平滑误差按移动权重分摊回去）

    raw_pos_list : list of Point3
    smooth_str   : int，平滑窗口半径
    input_thres_cm : float，距离过滤阈值（厘米）
    返回         : list of Point3（与输入等长）
    """
    count = len(raw_pos_list)
    if count < 2:
        return list(raw_pos_list)

    real_thres = decode_cm(input_thres_cm)

    # ── 阶段1：距离过滤 ──────────────────────────────────────────
    filtered = list(raw_pos_list)
    if real_thres > 0.00001:
        anchor = raw_pos_list[0]
        filtered[0] = anchor
        for i in range(1, count):
            dist = rt.distance(raw_pos_list[i], anchor)
            if dist < real_thres:
                filtered[i] = anchor
            else:
                filtered[i] = raw_pos_list[i]
                anchor = raw_pos_list[i]

    # ── 阶段2：移动平均平滑 ──────────────────────────────────────
    smoothed = list(filtered)
    if smooth_str > 0:
        for i in range(1, count - 1):
            start_k = max(0, i - smooth_str)
            end_k   = min(count - 1, i + smooth_str)
            sum_pos     = rt.Point3(0.0, 0.0, 0.0)
            sample_count = 0.0
            for k in range(start_k, end_k + 1):
                sum_pos.x    += filtered[k].x
                sum_pos.y    += filtered[k].y
                sum_pos.z    += filtered[k].z
                sample_count += 1.0
            smoothed[i] = rt.Point3(
                sum_pos.x / sample_count,
                sum_pos.y / sample_count,
                sum_pos.z / sample_count,
            )

    # 强制首帧与原始一致
    smoothed[0] = raw_pos_list[0]

    # ── 阶段3：末端漂移补偿 ──────────────────────────────────────
    target_end  = raw_pos_list[count - 1]
    current_end = smoothed[count - 1]
    err = rt.Point3(
        target_end.x - current_end.x,
        target_end.y - current_end.y,
        target_end.z - current_end.z,
    )

    frame_dists = [0.0]
    total_move  = 0.0
    for i in range(1, count):
        d = rt.distance(smoothed[i], smoothed[i - 1])
        if d < 0.001:
            d = 0.0
        frame_dists.append(d)
        total_move += d

    accum = 0.0
    for i in range(count):
        accum += frame_dists[i]
        if total_move > 0.0001:
            weight = accum / total_move
        else:
            weight = float(i) / float(count - 1) if count > 1 else 0.0
        if i == count - 1:
            weight = 1.0
        smoothed[i] = rt.Point3(
            smoothed[i].x + err.x * weight,
            smoothed[i].y + err.y * weight,
            smoothed[i].z + err.z * weight,
        )

    return smoothed


def extract_cumulative_yaw(transforms):
    """
    从变换列表中提取累计偏航角列表（度），用于旋转根运动。
    transforms : list of Matrix3（每帧 Biped 变换）
    返回       : list of float，与 transforms 等长
    """
    yaw_arr    = []
    cumulative = 0.0
    last_yaw   = None

    for tm in transforms:
        row2 = tm.row2
        fwd  = rt.normalize(rt.Point3(row2.x, row2.y, 0.0))
        current_yaw = math.degrees(math.atan2(fwd.y, fwd.x))

        if last_yaw is not None:
            delta = current_yaw - last_yaw
            if delta >  180.0:
                delta -= 360.0
            if delta < -180.0:
                delta += 360.0
            cumulative += delta

        yaw_arr.append(cumulative)
        last_yaw = current_yaw

    return yaw_arr


def detect_foot_grounding(bip_obj, start_f, end_f, jump_thres_cm):
    """
    检测每帧双足是否接地，并处理跳跃高度未达阈值的空中段。

    返回 (is_gnd, com_z_arr)
      is_gnd    : list of bool，长度 = end_f - start_f + 1
      com_z_arr : list of float，对应每帧 Biped COM 的 Z 高度
    """
    l_foot = None
    r_foot = None
    try:
        l_foot = rt.biped.getNode(bip_obj, rt.Name("lleg"), link=3)
    except Exception:
        pass
    try:
        r_foot = rt.biped.getNode(bip_obj, rt.Name("rleg"), link=3)
    except Exception:
        pass
    if l_foot is None:
        l_foot = bip_obj
    if r_foot is None:
        r_foot = bip_obj

    hidden_thres = decode_cm(2.0)
    jump_thres   = decode_cm(jump_thres_cm)

    # 找全局地板高度
    floor_z = float("inf")
    for i in range(start_f, end_f + 1):
        with pymxs.attime(i):
            z1 = l_foot.transform.pos.z
            z2 = r_foot.transform.pos.z
        floor_z = min(floor_z, z1, z2)

    # 逐帧采集
    com_z_arr    = []
    foot_min_z_arr = []
    is_gnd_raw   = []

    for i in range(start_f, end_f + 1):
        with pymxs.attime(i):
            z1    = l_foot.transform.pos.z
            z2    = r_foot.transform.pos.z
            com_z = bip_obj.transform.pos.z
        min_foot_z = min(z1, z2)
        is_gnd_raw.append(min_foot_z <= (floor_z + hidden_thres))
        com_z_arr.append(com_z)
        foot_min_z_arr.append(min_foot_z)

    # 合并跳跃高度不足的空中段
    is_gnd = list(is_gnd_raw)
    i = 0
    while i < len(is_gnd_raw):
        if not is_gnd_raw[i]:
            seg_start = i
            seg_end   = i
            max_z     = foot_min_z_arr[i]
            while seg_end + 1 < len(is_gnd_raw) and not is_gnd_raw[seg_end + 1]:
                seg_end += 1
                if foot_min_z_arr[seg_end] > max_z:
                    max_z = foot_min_z_arr[seg_end]
            if (max_z - floor_z) < jump_thres:
                for k in range(seg_start, seg_end + 1):
                    is_gnd[k] = True
            i = seg_end + 1
        else:
            i += 1

    return is_gnd, com_z_arr

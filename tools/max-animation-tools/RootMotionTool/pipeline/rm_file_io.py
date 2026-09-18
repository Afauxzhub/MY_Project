# -*- coding: utf-8 -*-
"""
双路输出 Pipeline：
  A 路 — 拷贝 FBX 到 Unity 项目对应目录
  B 路 — 备份 MAX 文件到公盘 NAS（按局内/局外、类别/角色/阶段分层）
"""
from __future__ import division
import os
import shutil

# 公盘根路径与分类文件夹名称（固定，可在设置中覆盖）
NAS_DEFAULT_BASE   = u""
NAS_INDOOR_FOLDER  = u"局内战斗备份"
NAS_OUTDOOR_FOLDER = u"局外演出备份"


# ──────────────────────────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────────────────────────

def _ensure_dir(path):
    """递归创建目录，已存在则跳过"""
    if path and not os.path.exists(path):
        os.makedirs(path)


# ──────────────────────────────────────────────────────────────────
# Unity 路径构建
# ──────────────────────────────────────────────────────────────────

def get_unity_indoor_path(unity_root, category_folder_map, category, char_name):
    """
    构建局内 FBX 的 Unity 目标目录。
    结构：{unity_root}/Art/Animations/{category_folder}/{category}_{char_name}/

    category_folder_map : dict，形如 {'Role': 'Role', 'Boss': 'Boss', ...}
                          支持多个分类映射到同一文件夹
    """
    folder = category_folder_map.get(category, category)
    char_folder = u"{0}_{1}".format(category, char_name)
    return os.path.join(
        unity_root, u"Art", u"Animations", folder, char_folder
    )


def get_unity_outdoor_path(unity_root, module_folder, type_folder, char_folder):
    """
    构建局外 FBX 的 Unity 目标目录。
    结构：{unity_root}/Art/Animations/Cutscenes/{module_folder}/{type_folder}/{char_folder}/
    """
    return os.path.join(
        unity_root, u"Art", u"Animations", u"Cutscenes", module_folder, type_folder, char_folder
    )


def get_unity_indoor_clip_open_path(unity_root, category, char_name):
    """
    构建局内发布后需要打开的动画目录。
    返回 Unity Package 的通用动画片段输出根目录。
    """
    return os.path.join(unity_root, u"Generated", u"AnimationClips")


def get_unity_outdoor_clip_open_path(unity_root, module_folder, type_folder, char_folder):
    """
    构建局外发布后需要打开的动画目录。
    返回 Unity Package 的通用动画片段输出根目录。
    """
    return os.path.join(unity_root, u"Generated", u"AnimationClips")


def get_unity_clip_asset_path(clip_dir, fbx_path):
    """
    根据导出的 FBX 文件名，推导 Unity 动画片段的绝对路径。
    规则：动画片段与 FBX 同名，扩展名为 .anim。
    """
    if not clip_dir or not fbx_path:
        return u""
    stem = os.path.splitext(os.path.basename(fbx_path))[0]
    parts = stem.split(u"_")
    group = u"_".join(parts[:2]) if len(parts) >= 2 else stem
    return os.path.join(clip_dir, group, stem + u".anim")


# ──────────────────────────────────────────────────────────────────
# FBX 拷贝到 Unity
# ──────────────────────────────────────────────────────────────────

def copy_fbx_to_unity(fbx_path, unity_dest_dir):
    """
    拷贝 FBX 文件到 Unity 目录，目录不存在时自动创建。
    返回目标完整路径。
    抛出 IOError / OSError（调用方负责处理并提示用户）。
    """
    _ensure_dir(unity_dest_dir)
    dest = os.path.join(unity_dest_dir, os.path.basename(fbx_path))
    shutil.copy2(fbx_path, dest)
    return dest


# ──────────────────────────────────────────────────────────────────
# 公盘阶段目录解析
# ──────────────────────────────────────────────────────────────────

def _resolve_stage_folder(stage, version=None):
    """
    将阶段和版本号转换为公盘阶段目录名。
    stage   : '初版' / '终版' / '监修'
    version : 监修阶段的版本号字符串，如 '1.0'
    返回相对路径段，如 '初版' 或 '监修\\1.0'
    """
    if stage == u"监修":
        if not version:
            raise ValueError(u"监修阶段必须提供版本号")
        return os.path.join(u"监修", version)
    return stage


# ──────────────────────────────────────────────────────────────────
# MAX 备份到公盘
# ──────────────────────────────────────────────────────────────────

def _copy_publish_settings_alongside(src_max_path, dest_max_path):
    """备份 max 时一并复制发布设置文件；无设置文件或失败时静默跳过。"""
    try:
        from pipeline.publish_settings import copy_settings_alongside
        copy_settings_alongside(src_max_path, dest_max_path)
    except Exception:
        pass


def backup_max_to_nas_indoor(max_path, category, char_name,
                              stage, version=None,
                              nas_base=None):
    """
    备份局内 MAX 文件到公盘。
    目录结构：
      {nas_base}/局内战斗备份/{category}/{char_name}/{阶段}/
      监修：{nas_base}/局内战斗备份/{category}/{char_name}/监修/{版本号}/

    初版/终版 只保留最新文件（同名直接覆盖）。
    同时把 max 对应的发布设置文件复制到目标目录的「发布设置」文件夹。
    返回目标完整路径。
    """
    base        = nas_base or NAS_DEFAULT_BASE
    stage_dir   = _resolve_stage_folder(stage, version)
    dest_dir    = os.path.join(base, NAS_INDOOR_FOLDER, category, char_name, stage_dir)
    _ensure_dir(dest_dir)
    dest = os.path.join(dest_dir, os.path.basename(max_path))
    shutil.copy2(max_path, dest)
    _copy_publish_settings_alongside(max_path, dest)
    return dest


def backup_max_to_nas_outdoor(max_path, module_folder, type_folder, char_folder,
                               stage, version=None,
                               nas_base=None):
    """
    备份局外 MAX 文件到公盘。
    目录结构：
      {nas_base}/局外演出备份/{module_folder}/{type_folder}/{char_folder}/{阶段}/
    同时把 max 对应的发布设置文件复制到目标目录的「发布设置」文件夹（若存在）。
    返回目标完整路径。
    """
    base      = nas_base or NAS_DEFAULT_BASE
    stage_dir = _resolve_stage_folder(stage, version)
    dest_dir  = os.path.join(
        base, NAS_OUTDOOR_FOLDER,
        module_folder, type_folder, char_folder, stage_dir
    )
    _ensure_dir(dest_dir)
    dest = os.path.join(dest_dir, os.path.basename(max_path))
    shutil.copy2(max_path, dest)
    _copy_publish_settings_alongside(max_path, dest)
    return dest


def publish_max_to_nas_indoor(
    max_path,
    category,
    char_name,
    stage,
    version=None,
    nas_base=None,
    publisher=u"",
    published_at=None,
):
    """带发布编号、历史记录与覆盖前备份的局内公盘发布。"""
    from pipeline.publish_history import publish_max_to_public

    base = nas_base or NAS_DEFAULT_BASE
    scope_root = os.path.join(base, NAS_INDOOR_FOLDER, category, char_name)
    stage_dir = _resolve_stage_folder(stage, version)
    dest = os.path.join(scope_root, stage_dir, os.path.basename(max_path))
    return publish_max_to_public(
        max_path,
        dest,
        scope_root,
        stage,
        stage_version=version or u"",
        publisher=publisher,
        published_at=published_at,
    )


def publish_max_to_nas_outdoor(
    max_path,
    module_folder,
    type_folder,
    char_folder,
    stage,
    version=None,
    nas_base=None,
    publisher=u"",
    published_at=None,
):
    """带发布编号、历史记录与覆盖前备份的局外公盘发布。"""
    from pipeline.publish_history import publish_max_to_public

    base = nas_base or NAS_DEFAULT_BASE
    scope_root = os.path.join(
        base, NAS_OUTDOOR_FOLDER, module_folder, type_folder, char_folder
    )
    stage_dir = _resolve_stage_folder(stage, version)
    dest = os.path.join(scope_root, stage_dir, os.path.basename(max_path))
    return publish_max_to_public(
        max_path,
        dest,
        scope_root,
        stage,
        stage_version=version or u"",
        publisher=publisher,
        published_at=published_at,
    )

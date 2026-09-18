# -*- coding: utf-8 -*-
"""
命名校验与解析：局内战斗动画 + 局外演出动画（过场）
依据：
  局内 — 角色预制体与动画资源命名规范
  局外 — 过场动画命名规范

白名单/映射优先读取工具设置（rm_config），缺省回退到下方内置默认值。
"""
from __future__ import division
import re

# ──────────────────────────────────────────────────────────────────
# 默认常量表（可被 rm_config 覆盖/追加）
# ──────────────────────────────────────────────────────────────────

# 局内动画分类（第一字段）默认白名单；实际校验优先用 category_folder_map 的 key
INDOOR_CATEGORIES = [u"Role", u"Monster", u"Elite", u"Boss", u"Npc", u"Scene"]

DEFAULT_CATEGORY_FOLDER_MAP = {
    u"Role":    u"Role",
    u"Monster": u"Monster",
    u"Elite":   u"Elite",
    u"Boss":    u"Boss",
    u"Npc":     u"Npc",
    u"Scene":   u"Scene",
}

# 局外模块：缩写 → Unity/公盘文件夹名
MODULE_FOLDER_MAP = {
    u"UL":  u"Ultimate_skill",
    u"EN":  u"Entrance",
    u"RE":  u"Result",
    u"GA":  u"Gacha",
    u"DE":  u"Development",
    u"ER":  u"Enrage",
    u"CS":  u"Cinematic",
    u"QTE": u"QTE",
    u"DI":  u"Dialogue",
}

MODULE_TAG_ROLE_SUPPORT = u"角色配套"
MODULE_TAG_STORY_DIALOGUE = u"剧情对话"
MODULE_TAGS = (MODULE_TAG_ROLE_SUPPORT, MODULE_TAG_STORY_DIALOGUE)

# 模块标签只决定“新建文件”局外页签中的分组，不改变现有发布路径或命名。
DEFAULT_MODULE_TAG_MAP = {
    u"UL": MODULE_TAG_ROLE_SUPPORT,
    u"GA": MODULE_TAG_ROLE_SUPPORT,
    u"DE": MODULE_TAG_ROLE_SUPPORT,
    u"ER": MODULE_TAG_ROLE_SUPPORT,
    u"EN": MODULE_TAG_STORY_DIALOGUE,
    u"RE": MODULE_TAG_STORY_DIALOGUE,
    u"CS": MODULE_TAG_STORY_DIALOGUE,
    u"QTE": MODULE_TAG_STORY_DIALOGUE,
    u"DI": MODULE_TAG_STORY_DIALOGUE,
}

# 局外类型：缩写 → 文件夹名（Chap+数字单独处理，始终允许）
TYPE_FOLDER_MAP = {
    u"Role":    u"Role",
    u"Monster": u"Monster",
}

# 局外资产类型默认列表
DEFAULT_OUTDOOR_ASSET_TYPES = [u"Char", u"Prop", u"Cam"]

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


def merge_category_folder_map(user_map=None):
    """
    以内置 DEFAULT_CATEGORY_FOLDER_MAP 为底，再用设置里的 category_folder_map 覆盖/追加。
    该表的 key 同时作为局内发布分类白名单。
    """
    out = dict(DEFAULT_CATEGORY_FOLDER_MAP)
    if not user_map:
        return out
    for k, v in user_map.items():
        ks = _as_text(k).strip()
        if not ks:
            continue
        if v is None:
            continue
        vs = _as_text(v).strip()
        if vs:
            out[ks] = vs
    return out


def indoor_categories_from_map(category_folder_map=None):
    """返回用于局内校验的分类白名单（有序）。"""
    cat_map = merge_category_folder_map(category_folder_map)
    keys = list(cat_map.keys())
    if keys:
        return keys
    return list(INDOOR_CATEGORIES)


def merge_module_folder_map(user_map=None):
    """
    以内置 MODULE_FOLDER_MAP 为底，再用设置里的 module_folder_map 覆盖/追加。
    user_map 来自 rm_config.json 的「局外模块映射」表（左列缩写 → 右列文件夹名）。
    """
    out = dict(MODULE_FOLDER_MAP)
    if not user_map:
        return out
    for k, v in user_map.items():
        ks = _as_text(k).strip()
        if not ks:
            continue
        if v is None:
            continue
        vs = _as_text(v).strip()
        if vs:
            out[ks] = vs
    return out


def normalize_module_tag(value, default=MODULE_TAG_STORY_DIALOGUE):
    value = _as_text(value).strip()
    return value if value in MODULE_TAGS else default


def merge_module_tag_map(module_folder_map=None, user_map=None):
    """为当前模块表补齐角色配套/剧情对话标签；旧配置无需迁移即可使用。"""
    modules = merge_module_folder_map(module_folder_map)
    user_map = user_map or {}
    result = {}
    for code in modules.keys():
        fallback = DEFAULT_MODULE_TAG_MAP.get(code, MODULE_TAG_STORY_DIALOGUE)
        result[code] = normalize_module_tag(user_map.get(code), fallback)
    return result


def module_codes_for_tag(module_folder_map, module_tag_map, tag):
    tag = normalize_module_tag(tag)
    tags = merge_module_tag_map(module_folder_map, module_tag_map)
    return [code for code in tags.keys() if tags.get(code) == tag]


def merge_type_folder_map(user_map=None):
    """
    以内置 TYPE_FOLDER_MAP 为底，再用设置里的 outdoor_type_folder_map 覆盖/追加。
    Chap+数字类型始终由内置规则处理，不必写进此表。
    """
    out = dict(TYPE_FOLDER_MAP)
    if not user_map:
        return out
    for k, v in user_map.items():
        ks = _as_text(k).strip()
        if not ks:
            continue
        if v is None:
            continue
        vs = _as_text(v).strip()
        if vs:
            out[ks] = vs
    return out


def normalize_outdoor_asset_types(user_list=None):
    """返回局外资产类型白名单。空/无效时回退默认。"""
    result = []
    seen = set()
    for item in (user_list or []):
        text = _as_text(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    if result:
        return result
    return list(DEFAULT_OUTDOOR_ASSET_TYPES)


# ──────────────────────────────────────────────────────────────────
# 正则
# ──────────────────────────────────────────────────────────────────

_OUTDOOR_SCENE_RE = re.compile(r'^SC\d+$')
_CHAP_TYPE_RE = re.compile(r'^Chap\d+$')


# ──────────────────────────────────────────────────────────────────
# 局内校验
# ──────────────────────────────────────────────────────────────────

def validate_indoor_name(name, category_folder_map=None):
    """
    校验局内动画文件名（不含扩展名）。
    返回 (is_valid: bool, error_msg: str, parsed: dict)
    parsed 在合法时包含 category / char_name / action_name / stage

    category_folder_map : 可选，来自工具设置「局内分类映射」；其 key 作为分类白名单。
    """
    categories = indoor_categories_from_map(category_folder_map)
    parts = name.split(u"_")
    if len(parts) >= 3:
        parsed = {
            u"category":    parts[0],
            u"char_name":   parts[1],
            u"action_name": parts[2],
            u"stage":       parts[3] if len(parts) >= 4 else u"",
        }
        errors = []

        # 字段1：分类
        if not parts[0]:
            errors.append(u"第一字段（分类）不能为空")
        elif not parts[0][0].isupper():
            errors.append(u"第一字段「{0}」首字母必须大写".format(parts[0]))
        elif parts[0] not in categories:
            hint = u"、".join(categories)
            errors.append(u"第一字段「{0}」不是有效分类，有效值：{1}".format(parts[0], hint))

        # 字段2：角色名
        if not parts[1]:
            errors.append(u"第二字段（角色名）不能为空")
        else:
            if not parts[1][0].isupper():
                errors.append(u"第二字段（角色名）「{0}」首字母必须大写".format(parts[1]))
            if not re.match(r'^[A-Za-z0-9]+$', parts[1]):
                errors.append(u"第二字段（角色名）只允许英文字母和数字")

        # 字段3：动作名
        if not parts[2]:
            errors.append(u"第三字段（动作名）不能为空")
        else:
            if not parts[2][0].isupper():
                errors.append(u"第三字段（动作名）「{0}」首字母必须大写".format(parts[2]))
            if not re.match(r'^[A-Za-z0-9]+$', parts[2]):
                errors.append(u"第三字段（动作名）只允许英文字母和数字")

        # 字段4：可选扩展字段
        if len(parts) >= 4 and parts[3]:
            if not parts[3][0].isupper():
                errors.append(u"第四字段「{0}」首字母必须大写".format(parts[3]))
            if not re.match(r'^[A-Za-z0-9]+$', parts[3]):
                errors.append(u"第四字段只允许英文字母和数字")

        if not errors:
            return True, u"", parsed

        return False, u"；".join(errors), {}

    if len(parts) < 3:
        return False, u"字段数量不足，至少需要三段：分类_角色名_动作名", {}
    return False, u"命名格式不符合规范，正确格式：分类_角色名_动作名(_第四字段...)", {}


# ──────────────────────────────────────────────────────────────────
# 局外校验
# ──────────────────────────────────────────────────────────────────

def validate_outdoor_name(
    name,
    module_folder_map=None,
    outdoor_type_folder_map=None,
    outdoor_asset_types=None,
    category_folder_map=None,
):
    """
    校验局外动画文件名（不含扩展名）。
    返回 (is_valid: bool, error_msg: str, parsed: dict)
    parsed 在合法时包含：
        module_code / module_folder / type_code / type_folder /
        char_name / char_folder / asset_type

    module_folder_map / outdoor_type_folder_map / outdoor_asset_types /
    category_folder_map
    均可来自工具设置；与内置默认合并后再校验。
    """
    m = merge_module_folder_map(module_folder_map)
    type_map = merge_type_folder_map(outdoor_type_folder_map)
    asset_types = normalize_outdoor_asset_types(outdoor_asset_types)
    parts = name.split(u"_")
    if len(parts) == 3:
        module_code, type_code, scene_name = parts
        errors = []
        if module_code not in m:
            hint = u"、".join(sorted(m.keys()))
            errors.append(u"模块字段「{0}」无效，有效值：{1}".format(module_code, hint))
        if not _CHAP_TYPE_RE.match(type_code):
            errors.append(u"剧情章节字段「{0}」无效，需要 Chap01、Chap02 等".format(type_code))
        if not is_outdoor_scene_name(scene_name):
            errors.append(u"剧情场次字段「{0}」无效，需要 SC01、SC02 等".format(scene_name))
        if not errors:
            return True, u"", {
                u"module_code": module_code,
                u"module_folder": m[module_code],
                u"type_code": type_code,
                u"type_folder": _resolve_outdoor_type_folder(type_code, type_map),
                u"char_name": scene_name,
                u"char_folder": _resolve_outdoor_char_folder(scene_name),
                u"asset_type": u"Char",
                u"shot_name": scene_name,
                u"is_dialogue": True,
                u"compact_dialogue": True,
            }
        return False, u"；".join(errors), {}

    if (
        len(parts) == 4
        and _CHAP_TYPE_RE.match(parts[1])
        and is_outdoor_scene_name(parts[2])
    ):
        module_code, type_code, scene_name, camera_name = parts
        errors = []
        if module_code not in m:
            hint = u"、".join(sorted(m.keys()))
            errors.append(u"模块字段「{0}」无效，有效值：{1}".format(module_code, hint))
        if not re.match(r"^Cam\d{2,}$", camera_name):
            errors.append(u"剧情镜头字段「{0}」无效，需要 Cam01、Cam02 等".format(camera_name))
        if not errors:
            return True, u"", {
                u"module_code": module_code,
                u"module_folder": m[module_code],
                u"type_code": type_code,
                u"type_folder": _resolve_outdoor_type_folder(type_code, type_map),
                u"char_name": scene_name,
                u"char_folder": _resolve_outdoor_char_folder(scene_name),
                u"asset_type": u"Char",
                u"shot_name": camera_name,
                u"is_dialogue": True,
                u"compact_dialogue": True,
            }
        return False, u"；".join(errors), {}

    if len(parts) >= 5 and parts[0] == u"DI":
        module_code = parts[0]
        type_code = parts[1]
        scene_name = parts[2]
        char_name = parts[3]
        action_name = u"_".join(parts[4:])

        errors = []
        if module_code not in m:
            hint = u"、".join(sorted(m.keys()))
            errors.append(u"模块字段「{0}」无效，有效值：{1}".format(module_code, hint))
        if not _CHAP_TYPE_RE.match(type_code):
            errors.append(u"对话类型字段「{0}」无效，需要 Chap01、Chap02 等".format(type_code))
        if not is_outdoor_scene_name(scene_name):
            errors.append(u"对话场次字段「{0}」无效，需要 SC01、SC02 等".format(scene_name))
        if not char_name or not re.match(r'^[A-Za-z0-9]+$', char_name):
            errors.append(u"对话角色字段只允许英文字母和数字")
        if not action_name or not re.match(r'^[A-Za-z0-9_]+$', action_name):
            errors.append(u"对话动作字段只允许英文字母、数字和下划线")

        if not errors:
            parsed = {
                u"module_code": module_code,
                u"module_folder": m[module_code],
                u"type_code": type_code,
                u"type_folder": _resolve_outdoor_type_folder(type_code, type_map),
                u"char_name": scene_name,
                u"char_folder": _resolve_outdoor_char_folder(scene_name),
                u"asset_type": u"Char",
                u"dialogue_character": char_name,
                u"dialogue_action": action_name,
                u"is_dialogue": True,
            }
            return True, u"", parsed

        return False, u"；".join(errors), {}

    if len(parts) >= 4:
        module_code = parts[0]
        type_code = parts[1]
        char_name = parts[2]
        asset_type = parts[3]

        errors = []
        if module_code not in m:
            hint = u"、".join(sorted(m.keys()))
            errors.append(u"模块字段「{0}」无效，有效值：{1}".format(module_code, hint))

        indoor_categories = indoor_categories_from_map(category_folder_map)
        valid_type = (
            type_code in type_map
            or type_code in indoor_categories
            or _CHAP_TYPE_RE.match(type_code)
        )
        if not valid_type:
            hint = u"、".join(sorted(type_map.keys()))
            errors.append(
                u"类型字段「{0}」无效，有效值：{1}、Chap01 等".format(type_code, hint)
            )

        if not char_name:
            errors.append(u"角色/场次字段不能为空")
        else:
            if not char_name[0].isupper():
                errors.append(u"角色/场次字段「{0}」首字母必须大写".format(char_name))
            if not re.match(r'^[A-Za-z0-9]+$', char_name):
                errors.append(u"角色/场次字段只允许英文字母和数字")

        is_camera_shot = bool(re.match(r'^Cam\d{2,}$', asset_type))
        if asset_type not in asset_types and not is_camera_shot:
            hint = u"、".join(asset_types)
            errors.append(
                u"资产类型/镜头字段「{0}」无效，有效值：{1}、Cam01 等".format(
                    asset_type, hint
                )
            )

        if not errors:
            type_folder = _resolve_outdoor_type_folder(type_code, type_map)
            char_folder = _resolve_outdoor_char_folder(char_name)
            parsed = {
                u"module_code":   module_code,
                u"module_folder": m[module_code],
                u"type_code":     type_code,
                u"type_folder":   type_folder,
                u"char_name":     char_name,
                u"char_folder":   char_folder,
                u"asset_type":    asset_type,
                u"shot_name":     asset_type,
            }
            return True, u"", parsed

        return False, u"；".join(errors), {}

    return False, (
        u"局外文件名格式不符合规范。角色配套例：UL_Role_Hero_Cam01；"
        u"剧情对话例：DI_Chap02_SC01_Cam01"
    ), {}


# ──────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────

def build_cutscene_fbx_name(module_code, type_code, char_name, asset_type):
    """拼合局外 FBX 文件名（不含扩展名）"""
    return u"{0}_{1}_{2}_{3}".format(module_code, type_code, char_name, asset_type)


def build_cutscene_camera_name(module_code, type_code, char_name):
    """拼合局外相机 FBX 文件名（不含扩展名）"""
    return build_cutscene_fbx_name(module_code, type_code, char_name, u"Cam")


def is_outdoor_scene_name(value):
    return bool(value and _OUTDOOR_SCENE_RE.match(value))


def _resolve_outdoor_type_folder(type_code, type_folder_map=None):
    type_map = merge_type_folder_map(type_folder_map)
    if type_code in type_map:
        return type_map[type_code]
    if _CHAP_TYPE_RE.match(type_code):
        return u"Chapter" + type_code[4:]
    return type_code


def _resolve_outdoor_char_folder(char_name):
    if is_outdoor_scene_name(char_name):
        return u"Scene" + char_name[2:]
    return char_name


def parse_outdoor_source_name(
    filename,
    module_folder_map=None,
    outdoor_type_folder_map=None,
):
    """
    从局外 Max 文件名中提取前四段：
      模块_类型_角色或场次_镜号(_其余后缀忽略)
    返回 (is_valid, error_msg, parsed)

    module_folder_map / outdoor_type_folder_map : 可选，与 validate_outdoor_name 一致。
    """
    if not filename:
        return False, u"当前 Max 文件名为空", {}

    name = filename
    if name.lower().endswith(u".max"):
        name = name[:-4]

    parts = [p for p in name.split(u"_") if p]
    if len(parts) < 3:
        return False, u"局外 Max 文件名至少需要三段：模块_章节/类型_场次/角色", {}

    module_code = parts[0]
    m = merge_module_folder_map(module_folder_map)
    type_map = merge_type_folder_map(outdoor_type_folder_map)

    if len(parts) == 3:
        type_code = parts[1]
        scene_name = parts[2]
        if module_code not in m:
            return False, u"剧情文件模块字段无效：{0}".format(module_code), {}
        if not _CHAP_TYPE_RE.match(type_code):
            return False, u"剧情文件第二字段需要是 Chap01、Chap02 等", {}
        if not is_outdoor_scene_name(scene_name):
            return False, u"剧情文件第三字段需要是 SC01、SC02 等", {}
        return True, u"", {
            u"source_name": name,
            u"module_code": module_code,
            u"module_folder": m.get(module_code, module_code),
            u"type_code": type_code,
            u"type_folder": _resolve_outdoor_type_folder(type_code, type_map),
            u"char_name": scene_name,
            u"char_folder": _resolve_outdoor_char_folder(scene_name),
            u"shot_name": scene_name,
            u"is_dialogue": True,
            u"compact_dialogue": True,
        }

    if (
        len(parts) == 4
        and _CHAP_TYPE_RE.match(parts[1])
        and is_outdoor_scene_name(parts[2])
    ):
        type_code = parts[1]
        scene_name = parts[2]
        camera_name = parts[3]
        if module_code not in m:
            return False, u"剧情文件模块字段无效：{0}".format(module_code), {}
        if not re.match(r"^Cam\d{2,}$", camera_name):
            return False, u"剧情文件第四字段需要是 Cam01、Cam02 等", {}
        return True, u"", {
            u"source_name": name,
            u"module_code": module_code,
            u"module_folder": m.get(module_code, module_code),
            u"type_code": type_code,
            u"type_folder": _resolve_outdoor_type_folder(type_code, type_map),
            u"char_name": scene_name,
            u"char_folder": _resolve_outdoor_char_folder(scene_name),
            u"shot_name": camera_name,
            u"is_dialogue": True,
            u"compact_dialogue": True,
        }

    if module_code == u"DI":
        if len(parts) < 5:
            return False, u"对话文件名至少需要五段：DI_Chap02_SC01_角色_动作名", {}
        type_code = parts[1]
        scene_name = parts[2]
        dialogue_character = parts[3]
        dialogue_action = u"_".join(parts[4:])
        if not _CHAP_TYPE_RE.match(type_code):
            return False, u"对话文件第二字段需要是 Chap01、Chap02 等", {}
        if not is_outdoor_scene_name(scene_name):
            return False, u"对话文件第三字段需要是 SC01、SC02 等", {}
        parsed = {
            u"source_name": name,
            u"module_code": module_code,
            u"module_folder": m.get(module_code, module_code),
            u"type_code": type_code,
            u"type_folder": _resolve_outdoor_type_folder(type_code, type_map),
            u"char_name": scene_name,
            u"char_folder": _resolve_outdoor_char_folder(scene_name),
            u"shot_name": dialogue_action,
            u"dialogue_character": dialogue_character,
            u"dialogue_action": dialogue_action,
            u"is_dialogue": True,
        }
        return True, u"", parsed

    type_code = parts[1]
    char_name = parts[2]
    shot_name = parts[3]

    parsed = {
        u"source_name": name,
        u"module_code": module_code,
        u"module_folder": m.get(module_code, module_code),
        u"type_code": type_code,
        u"type_folder": _resolve_outdoor_type_folder(type_code, type_map),
        u"char_name": char_name,
        u"char_folder": _resolve_outdoor_char_folder(char_name),
        u"shot_name": shot_name,
        u"is_dialogue": False,
    }
    return True, u"", parsed


def resolve_outdoor_asset_name(source_info, selected_char_name, asset_type):
    """
    解析局外导出的“资产字段”：
      1. 第三段是角色名时：使用 Char/Prop
      2. 第三段是 SCxx 场次时：
         - Prop -> Prop
         - 其他 -> 使用勾选角色名
    """
    asset_type = (asset_type or u"Char").strip() or u"Char"
    if is_outdoor_scene_name(source_info.get(u"char_name", u"")):
        if asset_type == u"Prop":
            return u"Prop"
        return selected_char_name
    return asset_type


def build_outdoor_character_export_name(source_info, selected_char_name, asset_type):
    if source_info.get(u"is_dialogue"):
        if source_info.get(u"compact_dialogue"):
            shot_name = source_info.get(u"shot_name", u"")
            if re.match(r"^Cam\d{2,}$", shot_name):
                return u"{0}_{1}_{2}_{3}_{4}".format(
                    source_info[u"module_code"],
                    source_info[u"type_code"],
                    source_info[u"char_name"],
                    selected_char_name,
                    shot_name,
                )
            return u"{0}_{1}".format(
                source_info.get(u"source_name", u""), selected_char_name
            )
        return source_info.get(u"source_name", u"")
    asset_name = resolve_outdoor_asset_name(source_info, selected_char_name, asset_type)
    return u"{0}_{1}_{2}_{3}_{4}".format(
        source_info[u"module_code"],
        source_info[u"type_code"],
        source_info[u"char_name"],
        asset_name,
        source_info[u"shot_name"],
    )


def build_outdoor_camera_export_name(source_info):
    if source_info.get(u"is_dialogue"):
        if source_info.get(u"compact_dialogue"):
            shot_name = source_info.get(u"shot_name", u"")
            if re.match(r"^Cam\d{2,}$", shot_name):
                return u"{0}_{1}_{2}_{3}_{4}".format(
                    source_info[u"module_code"],
                    source_info[u"type_code"],
                    source_info[u"char_name"],
                    u"Cam",
                    shot_name,
                )
        return u"{0}_Cam".format(source_info.get(u"source_name", u""))
    return u"{0}_{1}_{2}_{3}_{4}".format(
        source_info[u"module_code"],
        source_info[u"type_code"],
        source_info[u"char_name"],
        u"Cam",
        source_info[u"shot_name"],
    )


def detect_stage_from_filename(filename):
    """
    从文件名关键词自动识别备份阶段。
    返回 u'初版' / u'终版' / None（无法识别）
    """
    upper = filename.upper()
    for kw in (u"BK", u"BLOCKING", u"LAYOUT"):
        if kw in upper:
            return u"初版"
    if u"ANI" in upper:
        return u"终版"
    return None


def clean_string_native(raw_name, suffix=u""):
    """
    清理 Max 文件名，用于预览和 FBX 命名。
    移植自原 MaxScript cleanStringNative：
      1. 去除括号内容
      2. 非法字符替换为下划线
      3. 剔除常见废话后缀（ani/bk/v01 等）
    """
    if not raw_name:
        return u"Untitled"

    # 1. 去除括号内容
    out   = u""
    depth = 0
    for c in raw_name:
        if c in u"([":
            depth += 1
        elif c in u")]":
            depth -= 1
        elif depth == 0:
            out += c
    raw_name = out

    # 2. 只保留合法字符
    valid    = set(u"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    raw_name = u"".join(c if c in valid else u"_" for c in raw_name)

    # 3. 剔除废话后缀
    parts = [p for p in raw_name.split(u"_") if p]
    if not parts:
        return u"Untitled"

    BAD = {
        u"ani", u"animation", u"bk", u"blocking", u"layout",
        u"step", u"wip", u"final", u"test", u"demo", u"bak",
        u"copy", u"v01", u"v02", u"v03", u"01", u"02",
    }

    cut = len(parts)
    while cut > 0:
        p = parts[cut - 1].lower()
        should_remove = (
            p in BAD
            or p == u""
            or p.isdigit()
            or (len(p) >= 2 and p[0] == u"v" and p[1:].isdigit())
        )
        if should_remove:
            cut -= 1
        else:
            break

    if cut == 0:
        return raw_name + suffix
    return u"_".join(parts[:cut]) + suffix

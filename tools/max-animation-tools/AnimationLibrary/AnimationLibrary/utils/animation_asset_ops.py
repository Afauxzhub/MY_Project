# -*- coding: utf-8 -*-
"""
Animation asset save/apply operations.

This module isolates the unified animation-asset workflows from pose
workflows. It intentionally stays stateless and receives all dependencies
through parameters so `anim_manager.py` can remain the compatibility facade.
"""

import os

from PySide2.QtWidgets import QMessageBox


def _display_name(name):
    value = os.path.splitext(name or "")[0]
    if value.lower().endswith("_pose"):
        value = value[:-5]
    return value


def _animation_save_filename(clip_name, animation_mode):
    """Match the animx filename rule used by `anim_manager.py`."""
    base_name = clip_name or ""
    mode_name = (animation_mode or "").strip().lower()
    if mode_name == "full_biped":
        if not base_name.lower().endswith("_template"):
            base_name += "_template"
    return base_name + ".animx"


def save_animation(manager_cls, target_folder, parent_widget,
                   start_frame, end_frame,
                   pymxs_available, rt,
                   show_error, show_input_dialog, safe_print,
                   get_max_scene_filename, sanitize_filename,
                   clip_name=None, comment=u"", bake_keys=False,
                   expand_biped_limb=False, animation_mode="local"):
    """Shared implementation for `AnimManager.save_animation()`."""
    if not pymxs_available:
        show_error("Error", "pymxs is not available.", parent_widget)
        return None

    selected = list(rt.selection)
    if not selected:
        show_error(
            "No Selection",
            "Please select one or more objects in the scene before saving.",
            parent_widget
        )
        return None

    if clip_name is None:
        default_name = get_max_scene_filename()
        clip_name, ok = show_input_dialog(
            "Save Animation",
            "Enter animation clip name:",
            default_name,
            parent_widget
        )
        if not ok or not clip_name.strip():
            safe_print("[AnimManager] Save cancelled by user.")
            return None

    clip_name = sanitize_filename(clip_name.strip())
    save_path = os.path.join(
        target_folder,
        _animation_save_filename(clip_name, animation_mode)
    )
    if os.path.exists(save_path):
        answer = QMessageBox.warning(
            parent_widget,
            "Overwrite Animation?",
            "An animation named '{0}' already exists.\n\nReplace the existing file?".format(
                _display_name(os.path.basename(save_path))
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            safe_print("[AnimManager] Save cancelled by overwrite protection.")
            return None

    return manager_cls._save_animx(
        selected, target_folder, clip_name,
        start_frame, end_frame, parent_widget,
        comment=comment, bake_keys=False,
        expand_biped_limb=expand_biped_limb,
        animation_mode=animation_mode
    )


def apply_animation(manager_cls, bip_file_path, parent_widget,
                    start_frame, end_frame,
                    pymxs_available, rt, animx_ext, show_error, bake_keys=False,
                    expand_biped_limb=False):
    """Shared implementation for `AnimManager.apply_animation()`."""
    if not pymxs_available:
        show_error("Error", "pymxs is not available.", parent_widget)
        return False

    if not bip_file_path:
        show_error(
            "No Animation Selected",
            "Please select an animation clip in the grid before applying.",
            parent_widget
        )
        return False

    if not os.path.isfile(bip_file_path):
        show_error(
            "File Not Found",
            "Animation file not found:\n" + bip_file_path,
            parent_widget
        )
        return False

    ext = os.path.splitext(bip_file_path)[1].lower()

    if ext == animx_ext:
        return manager_cls._apply_animx(
            bip_file_path,
            parent_widget,
            start_frame=start_frame,
            end_frame=end_frame,
            bake_keys=bake_keys,
            expand_biped_limb=expand_biped_limb
        )

    if ext == ".bip":
        selected = list(rt.selection)
        if not selected:
            show_error(
                "No Selection",
                "Please select a Biped object in the scene before applying.",
                parent_widget
            )
            return False
        return manager_cls._apply_biped_animation(
            selected[0], bip_file_path, parent_widget,
            start_frame=start_frame, end_frame=end_frame,
            bake_keys=bake_keys
        )

    try:
        fname = os.path.basename(bip_file_path)
    except Exception:
        fname = repr(bip_file_path)

    show_error(
        "Unsupported Format",
        "File '{0}' has unsupported extension '{1}'.\n"
        "Supported formats: {2}, .bip".format(fname, ext, animx_ext),
        parent_widget
    )
    return False

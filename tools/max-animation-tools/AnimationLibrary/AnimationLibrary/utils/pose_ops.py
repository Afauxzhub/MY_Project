# -*- coding: utf-8 -*-
"""
Pose save/apply operations.

This module isolates pose workflows from animation-asset workflows while
keeping `AnimManager` as the existing facade used by the UI.
"""

import os

from PySide2.QtWidgets import QMessageBox

from . import preview_utils


def _display_name(name):
    value = os.path.splitext(name or "")[0]
    if value.lower().endswith("_pose"):
        value = value[:-5]
    return value


def save_pose(target_folder, parent_widget,
              pymxs_available, rt,
              show_error, show_info, show_input_dialog, safe_print,
              get_max_scene_filename, sanitize_filename, pose_handler,
              pose_name=None, comment=u""):
    """Shared implementation for `AnimManager.save_pose()`."""
    if not pymxs_available:
        show_error("Error", "pymxs is not available.", parent_widget)
        return None

    selected = list(rt.selection)
    if not selected:
        show_error(
            "No Selection",
            "Please select one or more objects in the scene before saving a pose.",
            parent_widget
        )
        return None

    if pose_name is None:
        default_name = get_max_scene_filename()
        pose_name, ok = show_input_dialog(
            "Save Pose",
            "Enter pose name:",
            default_name,
            parent_widget
        )
        if not ok or not pose_name.strip():
            safe_print("[AnimManager] Save pose cancelled by user.")
            return None

    pose_name = sanitize_filename(pose_name.strip())

    if not pose_name.lower().endswith("_pose.json"):
        save_path = os.path.join(target_folder, pose_name + pose_handler.POSE_SUFFIX)
    else:
        save_path = os.path.join(target_folder, pose_name)

    if os.path.exists(save_path):
        answer = QMessageBox.warning(
            parent_widget,
            "Overwrite Pose?",
            "A pose named '{0}' already exists.\n\nReplace the existing file?".format(
                _display_name(os.path.basename(save_path))
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            safe_print("[AnimManager] Save pose cancelled by overwrite protection.")
            return None

    success = pose_handler.save_pose(selected, save_path, comment=comment)
    if success:
        try:
            preview_utils.capture_asset_preview(
                save_path,
                rt=rt if pymxs_available else None,
                selected_objects=selected,
                safe_print=safe_print
            )
        except Exception as exc:
            try:
                safe_print("[Preview] Pose preview hook failed: {0}".format(repr(exc)))
            except Exception:
                pass
        try:
            display_path = save_path.encode('ascii', 'replace').decode('ascii')
        except Exception:
            display_path = repr(save_path)
        show_info(
            "Pose Saved",
            "Pose saved ({0} node(s)) to:\n{1}".format(len(selected), display_path),
            parent_widget
        )
        return save_path

    show_error(
        "Save Failed",
        "Failed to save pose.\nCheck the 3ds Max Listener for details.",
        parent_widget
    )
    return None


def apply_pose(pose_file_path, parent_widget,
               pymxs_available, show_error, show_info, pose_handler,
               biped_root_space_mode="world"):
    """Shared implementation for `AnimManager.apply_pose()`."""
    if not pymxs_available:
        show_error("Error", "pymxs is not available.", parent_widget)
        return False

    if not pose_file_path:
        show_error(
            "No Pose Selected",
            "Please select a .json pose file in the grid before applying.",
            parent_widget
        )
        return False

    if not os.path.isfile(pose_file_path):
        show_error(
            "File Not Found",
            "Pose file not found:\n" + pose_file_path,
            parent_widget
        )
        return False

    success = pose_handler.apply_pose(
        pose_file_path,
        biped_root_space_mode=biped_root_space_mode
    )
    if success:
        try:
            display_path = pose_file_path.encode('ascii', 'replace').decode('ascii')
        except Exception:
            display_path = repr(pose_file_path)
        show_info(
            "Pose Applied",
            "Pose applied to current frame from:\n" + display_path,
            parent_widget
        )
        return True

    show_error(
        "Apply Failed",
        "Failed to apply pose.\nCheck the 3ds Max Listener for details.",
        parent_widget
    )
    return False

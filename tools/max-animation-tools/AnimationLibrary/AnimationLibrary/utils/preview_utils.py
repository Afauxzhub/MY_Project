# -*- coding: utf-8 -*-
"""
Preview thumbnail helpers for animation library assets.

Phase 1 intentionally stays simple:
    - store thumbnails as JPG sidecar files next to the asset
    - capture the currently active viewport after save
    - hide common rig helper / bone style objects during capture
"""

import os
import shutil
import tempfile

try:
    from PySide2.QtCore import Qt
    from PySide2.QtGui import QImage
    PYSIDE2_AVAILABLE = True
except ImportError:
    PYSIDE2_AVAILABLE = False


THUMB_SUFFIX = ".thumb.jpg"
THUMB_MAX_SIZE = 384
THUMB_QUALITY = 90


try:
    text_type = unicode
except NameError:
    text_type = str


def get_preview_path(asset_path):
    """Return the JPG sidecar thumbnail path for an asset file."""
    base, _ext = os.path.splitext(asset_path or "")
    return base + THUMB_SUFFIX


def delete_preview(asset_path):
    """Delete an asset preview sidecar. Best-effort, returns bool."""
    preview_path = get_preview_path(asset_path)
    if not os.path.isfile(preview_path):
        return False
    os.remove(preview_path)
    return True


def rename_preview(old_asset_path, new_asset_path):
    """Rename an asset preview sidecar if it exists. Returns new path or None."""
    old_preview = get_preview_path(old_asset_path)
    if not os.path.isfile(old_preview):
        return None

    new_preview = get_preview_path(new_asset_path)
    if os.path.normcase(os.path.normpath(old_preview)) == os.path.normcase(os.path.normpath(new_preview)):
        return new_preview

    if os.path.exists(new_preview):
        os.remove(new_preview)
    os.rename(old_preview, new_preview)
    return new_preview


def move_preview(old_asset_path, new_asset_path):
    """Move an asset preview sidecar along with the asset file."""
    return rename_preview(old_asset_path, new_asset_path)


def capture_asset_preview(asset_path, rt, selected_objects=None, safe_print=None):
    """
    Capture the current active viewport to a low-resolution JPG thumbnail.

    This is deliberately best-effort: save must succeed even if preview capture fails.
    Returns the preview path on success, or None on failure.
    """
    if not asset_path or rt is None:
        return None

    preview_path = get_preview_path(asset_path)
    return _capture_preview_to_path(
        preview_path,
        rt,
        selected_objects=selected_objects,
        safe_print=safe_print
    )


def capture_temp_preview(rt, selected_objects=None, safe_print=None):
    """
    Capture the current viewport to a temporary JPG preview file.

    Used by the manual preview confirmation flow in the save panel.
    """
    if rt is None:
        return None

    fd = None
    temp_preview_path = None
    try:
        fd, temp_preview_path = tempfile.mkstemp(prefix="animlib_preview_", suffix=".jpg")
        os.close(fd)
        fd = None
        if os.path.exists(temp_preview_path):
            os.remove(temp_preview_path)
    except Exception:
        try:
            if fd is not None:
                os.close(fd)
        except Exception:
            pass
        return None

    result = _capture_preview_to_path(
        temp_preview_path,
        rt,
        selected_objects=selected_objects,
        safe_print=safe_print
    )
    if result and os.path.isfile(result):
        return result
    try:
        if temp_preview_path and os.path.exists(temp_preview_path):
            os.remove(temp_preview_path)
    except Exception:
        pass
    return None


def save_preview_from_image(source_image_path, asset_path):
    """
    Write a confirmed custom preview image to the asset's sidecar thumbnail path.
    """
    if not source_image_path or not asset_path or not os.path.isfile(source_image_path):
        return None

    preview_path = get_preview_path(asset_path)
    if _downscale_to_thumbnail(source_image_path, preview_path):
        return preview_path if os.path.isfile(preview_path) else None

    try:
        if os.path.exists(preview_path):
            os.remove(preview_path)
    except Exception:
        pass

    try:
        shutil.copyfile(source_image_path, preview_path)
    except Exception:
        return None
    return preview_path if os.path.isfile(preview_path) else None


def _capture_preview_to_path(preview_path, rt, selected_objects=None, safe_print=None):
    if not preview_path or rt is None:
        return None

    tmp_path = preview_path + ".capture.bmp"
    hidden_nodes = []
    overlay_state = None
    grid_state = None
    selection_state = None
    bmp = None
    dib = None

    try:
        _force_viewport_redraw(rt)
        overlay_state = _capture_and_disable_viewport_overlays(rt)
        grid_state = _capture_and_hide_viewport_grid(rt)
        hidden_nodes = _hide_preview_noise(rt, selected_objects=selected_objects)
        selection_state = _capture_and_clear_selection(rt, selected_objects=selected_objects)
        _force_viewport_redraw(rt)

        view_size = rt.getViewSize()
        width = max(int(getattr(view_size, "x", 0) or 0), 1)
        height = max(int(getattr(view_size, "y", 0) or 0), 1)

        dib = rt.gw.getViewportDib()
        if dib is None:
            raise RuntimeError("gw.getViewportDib() returned None")

        bmp = rt.bitmap(width, height, filename=tmp_path)
        rt.copy(dib, bmp)
        rt.save(bmp)
        _close_bitmap_safe(rt, bmp)
        bmp = None

        if not os.path.isfile(tmp_path):
            raise RuntimeError("Viewport capture file was not written")

        if not _downscale_to_thumbnail(tmp_path, preview_path):
            if os.path.exists(preview_path):
                os.remove(preview_path)
            os.rename(tmp_path, preview_path)
        else:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        return preview_path if os.path.isfile(preview_path) else None
    except Exception as exc:
        _safe_log(safe_print, "[Preview] Capture failed: {0}".format(_to_text(exc)))
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return None
    finally:
        try:
            _restore_viewport_overlays(rt, overlay_state)
        except Exception as exc:
            _safe_log(safe_print, "[Preview] Overlay restore failed: {0}".format(_to_text(exc)))
        try:
            _restore_viewport_grid(rt, grid_state)
        except Exception as exc:
            _safe_log(safe_print, "[Preview] Grid restore failed: {0}".format(_to_text(exc)))
        try:
            _restore_hidden_nodes(rt, hidden_nodes)
        except Exception as exc:
            _safe_log(safe_print, "[Preview] Restore failed: {0}".format(_to_text(exc)))
        try:
            _restore_scene_selection(rt, selection_state)
            _force_viewport_redraw(rt)
        except Exception as exc:
            _safe_log(safe_print, "[Preview] Selection restore failed: {0}".format(_to_text(exc)))
        try:
            restore_viewport_overlay_defaults(
                rt,
                force_transform_gizmo=True,
                force_selection_brackets=None
            )
        except Exception as exc:
            _safe_log(safe_print, "[Preview] Overlay default recovery failed: {0}".format(_to_text(exc)))
        try:
            if bmp is not None:
                _close_bitmap_safe(rt, bmp)
        except Exception:
            pass
        try:
            if dib is not None:
                _close_bitmap_safe(rt, dib)
        except Exception:
            pass


def _downscale_to_thumbnail(source_path, output_path):
    if not PYSIDE2_AVAILABLE:
        return False

    image = QImage(source_path)
    if image.isNull():
        return False

    crop_size = min(image.width(), image.height())
    if crop_size <= 0:
        return False

    x = int((image.width() - crop_size) / 2)
    y = int((image.height() - crop_size) / 2)
    image = image.copy(x, y, crop_size, crop_size)

    image = image.scaled(
        THUMB_MAX_SIZE,
        THUMB_MAX_SIZE,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation
    )
    return bool(image.save(output_path, "JPG", THUMB_QUALITY))


def _hide_preview_noise(rt, selected_objects=None):
    hidden_nodes = []
    seen = set()

    try:
        all_nodes = list(rt.objects)
    except Exception:
        all_nodes = []

    for node in all_nodes:
        try:
            key = int(rt.getHandleByAnim(node))
        except Exception:
            key = id(node)
        if key in seen:
            continue
        seen.add(key)

        if not _should_hide_for_preview(rt, node):
            continue

        try:
            was_hidden = bool(node.isHidden)
        except Exception:
            try:
                was_hidden = bool(rt.isHidden(node))
            except Exception:
                was_hidden = False

        if was_hidden:
            continue

        try:
            node.isHidden = True
            hidden_nodes.append(node)
        except Exception:
            try:
                rt.hide(node)
                hidden_nodes.append(node)
            except Exception:
                pass

    return hidden_nodes


def _capture_and_clear_selection(rt, selected_objects=None):
    nodes = []
    seen = set()

    try:
        source_nodes = list(selected_objects or list(rt.selection))
    except Exception:
        source_nodes = []

    for node in source_nodes:
        try:
            key = int(rt.getHandleByAnim(node))
        except Exception:
            key = id(node)
        if key in seen:
            continue
        seen.add(key)
        nodes.append(node)

    if not nodes:
        return None

    try:
        rt.clearSelection()
    except Exception:
        return None

    return nodes


def _restore_scene_selection(rt, selection_state):
    if not selection_state:
        return

    try:
        rt.clearSelection()
    except Exception:
        pass

    first_selected = False
    for node in selection_state:
        try:
            if not first_selected:
                rt.select(node)
                first_selected = True
            else:
                rt.selectMore(node)
        except Exception:
            pass


def _capture_and_hide_viewport_grid(rt):
    script = """
    (
        local gridState = undefined
        local mode = "none"
        local stateText = "none"

        try(gridState = viewport.getGridVisibility())catch()
        if gridState == undefined do try(gridState = viewport.GetGridVisibility())catch()

        if gridState != undefined then
        (
            stateText = if gridState then "true" else "false"
            try(viewport.setGridVisibility false)catch(try(viewport.SetGridVisibility false)catch())
            mode = "api"
        )
        else
        (
            try
            (
                max grid
                mode = "toggle"
            )
            catch()
        )

        mode + "|" + stateText
    )
    """

    try:
        result = _to_text(rt.execute(script))
    except Exception:
        return None

    if not result or "|" not in result:
        return None

    mode, state_text = result.split("|", 1)
    return {
        "mode": mode,
        "state": state_text,
    }


def _restore_viewport_grid(rt, grid_state):
    if not grid_state:
        return

    mode = grid_state.get("mode")
    state_text = grid_state.get("state")

    if mode == "api":
        if state_text == "true":
            rt.execute("""
            (
                try(viewport.setGridVisibility true)catch(try(viewport.SetGridVisibility true)catch())
            )
            """)
        elif state_text == "false":
            rt.execute("""
            (
                try(viewport.setGridVisibility false)catch(try(viewport.SetGridVisibility false)catch())
            )
            """)
    elif mode == "toggle":
        rt.execute("max grid")


def _capture_and_disable_viewport_overlays(rt):
    state = {
        "selection_brackets": None,
        "use_transform_gizmos": None,
        "tm_gizmo": None,
    }

    try:
        state["selection_brackets"] = bool(rt.selectionBrackets)
        rt.selectionBrackets = False
    except Exception:
        pass

    try:
        state["use_transform_gizmos"] = bool(rt.preferences.useTransformGizmos)
        rt.preferences.useTransformGizmos = False
    except Exception:
        pass

    try:
        state["tm_gizmo"] = bool(rt.tmGizmos.useGizmo)
        rt.tmGizmos.useGizmo = False
    except Exception:
        pass

    _force_viewport_redraw(rt)
    return state


def _restore_viewport_overlays(rt, state):
    if not state:
        return

    try:
        if state.get("selection_brackets") is not None:
            rt.selectionBrackets = state["selection_brackets"]
    except Exception:
        pass

    try:
        if state.get("use_transform_gizmos") is not None:
            rt.preferences.useTransformGizmos = state["use_transform_gizmos"]
    except Exception:
        pass

    try:
        if state.get("tm_gizmo") is not None:
            rt.tmGizmos.useGizmo = state["tm_gizmo"]
    except Exception:
        pass

    _force_viewport_redraw(rt)


def restore_viewport_overlay_defaults(rt, force_transform_gizmo=True, force_selection_brackets=None):
    """
    Best-effort recovery for viewport overlays after preview capture.

    This is intentionally stronger than `_restore_viewport_overlays()` and is
    safe to call when opening the plugin window to recover from stale host
    state after exceptions or hot reloads.
    """
    if rt is None:
        return False

    restored = False

    try:
        if force_selection_brackets is not None:
            rt.selectionBrackets = bool(force_selection_brackets)
            restored = True
    except Exception:
        pass

    if force_transform_gizmo:
        try:
            rt.preferences.useTransformGizmos = True
            restored = True
        except Exception:
            pass

        try:
            rt.tmGizmos.useGizmo = True
            restored = True
        except Exception:
            pass

        try:
            rt.execute("try(preferences.useTransformGizmos = true)catch()")
            restored = True
        except Exception:
            pass

        try:
            rt.execute("try(tmGizmos.useGizmo = true)catch()")
            restored = True
        except Exception:
            pass

    _force_viewport_redraw(rt)
    return restored


def _restore_hidden_nodes(rt, hidden_nodes):
    for node in hidden_nodes or []:
        try:
            node.isHidden = False
        except Exception:
            try:
                rt.unhide(node)
            except Exception:
                pass


def _should_hide_for_preview(rt, node):
    class_name = _lower_text(_class_name(rt, node))
    super_name = _lower_text(_super_class_name(rt, node))

    if not class_name and not super_name:
        return False

    if any(token in super_name for token in ("helper", "shape", "camera", "light", "spacewarp")):
        return True

    if any(token in class_name for token in (
        "bone", "dummy", "point", "biped", "expose", "gizmo", "manip", "helper"
    )):
        return True

    try:
        if hasattr(node, "boneEnable") and bool(node.boneEnable):
            return True
    except Exception:
        pass

    return False


def _class_name(rt, node):
    try:
        return _to_text(rt.classOf(node))
    except Exception:
        return u""


def _super_class_name(rt, node):
    try:
        return _to_text(rt.superClassOf(node))
    except Exception:
        return u""


def _force_viewport_redraw(rt):
    try:
        rt.completeRedraw()
    except Exception:
        pass
    try:
        rt.redrawViews()
    except Exception:
        pass


def _close_bitmap_safe(rt, bitmap_value):
    try:
        rt.close(bitmap_value)
    except Exception:
        pass


def _lower_text(value):
    return _to_text(value).lower()


def _to_text(value):
    if isinstance(value, text_type):
        return value
    if value is None:
        return text_type()
    try:
        return value.decode("utf-8")
    except Exception:
        try:
            return value.decode("mbcs")
        except Exception:
            try:
                return text_type(value)
            except Exception:
                return u""


def _safe_log(safe_print, message):
    if not safe_print:
        return
    try:
        safe_print(message)
    except Exception:
        pass

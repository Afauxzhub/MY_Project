"""
3ds Max Utility Functions Module
Placeholder functions for interacting with 3ds Max
"""

try:
    from pymxs import runtime as rt
    PYMXS_AVAILABLE = True
except ImportError:
    PYMXS_AVAILABLE = False
    print("Warning: pymxs not available, some features will be disabled")


def _to_int_frame(value):
    try:
        return int(value)
    except Exception:
        return None


def _parse_interval_text(value):
    try:
        text = str(value)
    except Exception:
        return None
    text = text.strip()
    if not text:
        return None

    parts = []
    token = ""
    for ch in text:
        if ch in "-0123456789":
            token += ch
        else:
            if token:
                try:
                    parts.append(int(token))
                except Exception:
                    pass
                token = ""
    if token:
        try:
            parts.append(int(token))
        except Exception:
            pass
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def get_selected_objects():
    """Get selected objects in 3ds Max"""
    if not PYMXS_AVAILABLE:
        print("[Placeholder] get_selected_objects - pymxs not available")
        return []
    try:
        selected = rt.selection
        print("[Placeholder] get_selected_objects: " + str(len(selected)) + " objects")
        return list(selected)
    except Exception as e:
        print("[Placeholder] get_selected_objects failed: " + str(e))
        return []


def get_timeline_range():
    """Get 3ds Max timeline range"""
    if not PYMXS_AVAILABLE:
        print("[Placeholder] get_timeline_range - pymxs not available")
        return (0, 100)
    candidates = []
    candidate_labels = []

    def _add_candidate(source_name, start_value, end_value):
        start_value = _to_int_frame(start_value)
        end_value = _to_int_frame(end_value)
        if start_value is None or end_value is None:
            return
        candidates.append((source_name, start_value, end_value))
        candidate_labels.append("{0}={1}-{2}".format(source_name, start_value, end_value))

    try:
        _add_candidate(
            "python_frame_property",
            getattr(rt.animationRange.start, "frame", None),
            getattr(rt.animationRange.end, "frame", None)
        )
    except Exception:
        pass

    try:
        _add_candidate("python_direct", rt.animationRange.start, rt.animationRange.end)
    except Exception:
        pass

    try:
        _add_candidate(
            "mxs_frame_property",
            rt.execute("(animationRange.start.frame as integer)"),
            rt.execute("(animationRange.end.frame as integer)")
        )
    except Exception:
        pass

    try:
        _add_candidate(
            "mxs_integer",
            rt.execute("(animationRange.start as integer)"),
            rt.execute("(animationRange.end as integer)")
        )
    except Exception:
        pass

    try:
        interval_text = rt.execute("animationRange as string")
        parsed = _parse_interval_text(interval_text)
        if parsed is not None:
            _add_candidate("mxs_interval_string", parsed[0], parsed[1])
    except Exception:
        pass

    try:
        start_text = rt.execute("(animationRange.start as string)")
        end_text = rt.execute("(animationRange.end as string)")
        start = _parse_interval_text(start_text)
        end = _parse_interval_text(end_text)
        if start and end:
            _add_candidate("mxs_start_end_string", start[0], end[-1])
        else:
            start_value = _to_int_frame(start_text)
            end_value = _to_int_frame(end_text)
            _add_candidate("mxs_start_end_string_int", start_value, end_value)
    except Exception:
        pass

    if candidates:
        preferred_sources = (
            "python_frame_property",
            "mxs_frame_property",
            "mxs_interval_string",
            "mxs_start_end_string",
            "python_direct",
            "mxs_start_end_string_int",
            "mxs_integer",
        )
        chosen = None
        for source_name in preferred_sources:
            for candidate in candidates:
                if candidate[0] == source_name:
                    chosen = candidate
                    break
            if chosen is not None:
                break

        if chosen is None:
            chosen = candidates[0]

        source_name, start, end = chosen
        print("[Placeholder] get_timeline_range: " + str(start) + " - " + str(end))
        print("[Placeholder] get_timeline_range chosen: " + source_name)
        if candidate_labels:
            print("[Placeholder] get_timeline_range sources: " + "; ".join(candidate_labels))
        return (start, end)

    print("[Placeholder] get_timeline_range failed: no valid range source")
    return (0, 100)


def save_animation_placeholder(animation_name, start_frame, end_frame):
    """Save animation - placeholder function"""
    selected = get_selected_objects()
    print("\n[Placeholder] SAVE ANIMATION")
    print("  Name: " + str(animation_name))
    print("  Range: " + str(start_frame) + " - " + str(end_frame))
    print("  Selected objects: " + str(len(selected)))
    print("  -- Not yet implemented --\n")


def apply_animation_placeholder(animation_name, start_frame, end_frame):
    """Apply animation - placeholder function"""
    selected = get_selected_objects()
    print("\n[Placeholder] APPLY ANIMATION")
    print("  Name: " + str(animation_name))
    print("  Range: " + str(start_frame) + " - " + str(end_frame))
    print("  Selected objects: " + str(len(selected)))
    print("  -- Not yet implemented --\n")


def apply_pose_placeholder(animation_name, frame_number):
    """Apply pose - placeholder function"""
    selected = get_selected_objects()
    print("\n[Placeholder] APPLY POSE")
    print("  Name: " + str(animation_name))
    print("  Frame: " + str(frame_number))
    print("  Selected objects: " + str(len(selected)))
    print("  -- Not yet implemented --\n")


def mirror_pose_placeholder(animation_name, frame_number):
    """Mirror pose - placeholder function"""
    selected = get_selected_objects()
    print("\n[Placeholder] MIRROR POSE")
    print("  Name: " + str(animation_name))
    print("  Frame: " + str(frame_number))
    print("  Selected objects: " + str(len(selected)))
    print("  -- Not yet implemented --\n")


def mirror_animation_placeholder(animation_name, start_frame, end_frame):
    """Mirror animation - placeholder function"""
    selected = get_selected_objects()
    print("\n[Placeholder] MIRROR ANIMATION")
    print("  Name: " + str(animation_name))
    print("  Range: " + str(start_frame) + " - " + str(end_frame))
    print("  Selected objects: " + str(len(selected)))
    print("  -- Not yet implemented --\n")

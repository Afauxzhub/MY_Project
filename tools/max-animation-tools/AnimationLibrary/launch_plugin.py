"""
3ds Max Animation Library Plugin - Quick Launch Script.

This launcher is portable: it resolves the plugin root from its own file path,
so the whole package can be installed to a fixed Max scripts directory without
hard-coded machine-specific paths.
"""

import sys
import os
from PySide2.QtWidgets import QApplication

try:
    import shiboken2
except ImportError:
    shiboken2 = None

# Step 1: Add plugin path
plugin_path = os.path.dirname(os.path.abspath(__file__))
if plugin_path not in sys.path:
    sys.path.insert(0, plugin_path)

def _iter_top_level_widgets():
    """Return top-level widgets safely across Max host variants."""
    try:
        widgets = QApplication.topLevelWidgets()
        if widgets is not None:
            return list(widgets)
    except Exception:
        pass

    try:
        app = QApplication.instance()
        if app is not None and hasattr(app, "topLevelWidgets"):
            widgets = app.topLevelWidgets()
            if widgets is not None:
                return list(widgets)
    except Exception:
        pass

    return []


def _neutralize_window_class(widget):
    """Patch stale window classes so they stop running old event handlers."""
    if widget is None:
        return

    try:
        cls = widget.__class__
        if cls is None:
            return
        if getattr(cls, "__name__", "") != "AnimationLibraryWindow":
            return

        def _safe_event(self, event):
            return False

        def _safe_close_event(self, event):
            try:
                if event is not None and hasattr(event, "accept") and callable(event.accept):
                    event.accept()
            except Exception:
                pass

        cls.event = _safe_event
        cls.closeEvent = _safe_close_event
    except Exception:
        pass


def _dispose_window(widget):
    """Remove a window without invoking stale overridden close/event handlers."""
    if widget is None:
        return

    _neutralize_window_class(widget)

    try:
        if hasattr(widget, "cleanup") and callable(widget.cleanup):
            widget.cleanup()
    except Exception:
        pass

    for action in (
        lambda: widget.blockSignals(True),
        lambda: widget.hide(),
        lambda: widget.setParent(None),
        lambda: widget.deleteLater(),
    ):
        try:
            action()
        except Exception:
            pass


# Step 2: Close any stale plugin windows created by older code
for widget in _iter_top_level_widgets():
    try:
        if widget and widget.windowTitle() == "Animation Library":
            _dispose_window(widget)
    except Exception:
        pass

# Step 3: Remove cached modules so we always get a fresh import
keys_to_remove = [key for key in sys.modules if key == 'AnimationLibrary' or key.startswith('AnimationLibrary.')]
for key in keys_to_remove:
    del sys.modules[key]

# Step 4: Import plugin fresh
import AnimationLibrary

print("Plugin loaded: version " + AnimationLibrary.__version__)

# Step 5: Show window
window = AnimationLibrary.show_window()
print("Window opened!")

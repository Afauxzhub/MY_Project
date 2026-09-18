"""
Animation Library Plugin - Main Entry Point
Manages window creation and display, integrates with 3ds Max
"""

import sys

try:
    from importlib import reload as _reload_module
except ImportError:
    _reload_module = reload

try:
    from pymxs import runtime as rt
    PYMXS_AVAILABLE = True
except ImportError:
    PYMXS_AVAILABLE = False

from PySide2.QtWidgets import QApplication
from .utils import preview_utils

try:
    import shiboken2
except ImportError:
    shiboken2 = None

# Global window instance
_window_instance = None


def get_max_main_window():
    """Get the 3ds Max main window handle"""
    try:
        import MaxPlus
        return MaxPlus.GetQMaxMainWindow()
    except ImportError:
        try:
            from qtmax import GetQMaxMainWindow
            return GetQMaxMainWindow()
        except ImportError:
            app = QApplication.instance()
            if app:
                return app.activeWindow()
            return None


def _load_window_class(force_reload=True):
    """Load the main window class lazily so UI edits can be reloaded."""
    package_name = __package__ or "AnimationLibrary"
    module_names = [
        package_name + ".ui.folder_tree_widget",
        package_name + ".ui.animation_grid_widget",
        package_name + ".ui.operation_panel_widget",
        package_name + ".ui.main_window",
    ]

    loaded_modules = {}
    for module_name in module_names:
        if module_name in sys.modules:
            module = sys.modules[module_name]
            if force_reload:
                module = _reload_module(module)
        else:
            module = __import__(module_name, fromlist=["*"])
        loaded_modules[module_name] = module

    main_window_module = loaded_modules[module_names[-1]]
    return main_window_module.AnimationLibraryWindow


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
    """Remove a window without relying on closeEvent from older hot-reloaded classes."""
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


def _close_stale_windows():
    """Close orphaned Animation Library windows left from older module loads."""
    for widget in _iter_top_level_widgets():
        try:
            if widget is None or widget is _window_instance:
                continue
            if widget.windowTitle() == "Animation Library":
                _dispose_window(widget)
        except Exception:
            pass


def show_window(force_reload=True):
    """Show or activate the Animation Library window"""
    global _window_instance

    try:
        if PYMXS_AVAILABLE:
            preview_utils.restore_viewport_overlay_defaults(
                rt,
                force_transform_gizmo=True,
                force_selection_brackets=None
            )
    except Exception:
        pass

    _close_stale_windows()

    if _window_instance is not None:
        try:
            if force_reload:
                _dispose_window(_window_instance)
                _window_instance = None
            else:
                _window_instance.show()
                _window_instance.raise_()
                _window_instance.activateWindow()
                print("Animation Library window activated")
                return _window_instance
        except RuntimeError:
            _window_instance = None

    print("Getting 3ds Max main window...")
    parent = get_max_main_window()
    print("Parent window: " + str(parent))

    print("Creating Animation Library window...")
    AnimationLibraryWindow = _load_window_class(force_reload=force_reload)
    _window_instance = AnimationLibraryWindow(parent)
    print("Window created: " + str(_window_instance))

    print("Showing window...")
    _window_instance.show()
    _window_instance.raise_()
    _window_instance.activateWindow()

    print("Animation Library window created and shown")
    return _window_instance


def close_window():
    """Close the Animation Library window"""
    global _window_instance

    if _window_instance is not None:
        try:
            _dispose_window(_window_instance)
            _window_instance = None
            print("Animation Library window closed")
        except RuntimeError:
            _window_instance = None


if __name__ == "__main__":
    show_window()

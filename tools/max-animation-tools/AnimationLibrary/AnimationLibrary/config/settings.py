"""
Settings Management Module
Handles loading, saving and managing plugin configuration
"""

import io
import json
import os
import sys

try:
    text_type = unicode
except NameError:
    text_type = str


def _to_text(value):
    if isinstance(value, text_type):
        return value
    if value is None:
        return text_type("")
    try:
        return value.decode("utf-8")
    except Exception:
        try:
            return value.decode(sys.getfilesystemencoding() or "utf-8")
        except Exception:
            return text_type(value)


def _json_to_text(data):
    payload = json.dumps(data, indent=4, ensure_ascii=False)
    if isinstance(payload, text_type):
        return payload
    return payload.decode("utf-8")


class Settings(object):
    """Configuration manager class"""

    DEFAULT_CONFIG = {
        "library_path": "D:/AnimLibrary",
        "libraries": [],
        "folder_tree": {
            "view_mode": "physical"
        },
        "window": {
            "width": 1200,
            "height": 700,
            "x": 100,
            "y": 100
        },
        "splitter": {
            "left_width": 300,
            "middle_width": 480,
            "right_width": 420
        },
        "grid": {
            "icon_size": 128,
            "spacing": 10
        },
        "theme": "dark"
    }

    def __init__(self, config_file=None):
        self.legacy_config_file = None
        self.last_save_error = ""
        if config_file is None:
            # __file__ is AnimationLibrary/config/settings.py
            # parent = AnimationLibrary/config
            # parent.parent = AnimationLibrary
            plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.legacy_config_file = os.path.join(plugin_dir, "config.json")
            appdata_dir = os.environ.get("APPDATA")
            if appdata_dir:
                config_file = os.path.join(appdata_dir, "MaxAI_Tools", "AnimationLibrary", "config.json")
            else:
                config_file = self.legacy_config_file

        self.config_file = config_file
        self.config = {}
        self._deep_copy(self.DEFAULT_CONFIG, self.config)
        self.load_config()

    def _deep_copy(self, source, target):
        for key, value in source.items():
            if isinstance(value, dict):
                target[key] = {}
                self._deep_copy(value, target[key])
            else:
                target[key] = value

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with io.open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self._merge_config(self.config, loaded)
                print("Config loaded: " + str(self.config_file))
            except Exception as e:
                print("Config load failed: " + str(e) + ", using defaults")
        elif self.legacy_config_file and os.path.exists(self.legacy_config_file):
            try:
                with io.open(self.legacy_config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self._merge_config(self.config, loaded)
                print("Legacy config loaded: " + str(self.legacy_config_file))
                self.save_config()
            except Exception as e:
                print("Legacy config load failed: " + str(e) + ", using defaults")
        else:
            self.save_config()

    def save_config(self):
        try:
            config_dir = os.path.dirname(self.config_file)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            with io.open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(_json_to_text(self.config))
            print("Config saved: " + str(self.config_file))
            self.last_save_error = ""
            return True
        except Exception as e:
            self.last_save_error = str(e)
            print("Config save failed: " + str(e))
            return False

    def _merge_config(self, target, source):
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                self._merge_config(target[key], value)
            else:
                target[key] = value

    def get(self, key, default=None):
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key, value):
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def get_library_path(self):
        return self.get("library_path", self.DEFAULT_CONFIG["library_path"])

    def set_library_path(self, path):
        self.set("library_path", path)

    def get_libraries(self):
        libraries = self.get("libraries", [])
        if libraries:
            return libraries

        legacy_path = self.get_library_path()
        if legacy_path:
            return [{
                "id": "legacy_default",
                "name": os.path.basename(os.path.normpath(legacy_path)) or "Animation Library",
                "root_path": legacy_path,
                "is_network": False,
                "watch_enabled": True,
                "category_file": os.path.join(legacy_path, ".anim_categories.json"),
            }]
        return []

    def set_libraries(self, libraries):
        self.set("libraries", libraries)
        if libraries:
            self.set_library_path(libraries[0].get("root_path", self.DEFAULT_CONFIG["library_path"]))

    def get_folder_tree_view_mode(self):
        return self.get("folder_tree.view_mode", self.DEFAULT_CONFIG["folder_tree"]["view_mode"])

    def set_folder_tree_view_mode(self, view_mode):
        self.set("folder_tree.view_mode", view_mode)

    def get_window_geometry(self):
        return self.get("window", self.DEFAULT_CONFIG["window"])

    def set_window_geometry(self, width, height, x, y):
        self.set("window.width", width)
        self.set("window.height", height)
        self.set("window.x", x)
        self.set("window.y", y)

    def get_splitter_sizes(self):
        return self.get("splitter", self.DEFAULT_CONFIG["splitter"])

    def set_splitter_sizes(self, left, middle, right):
        self.set("splitter.left_width", left)
        self.set("splitter.middle_width", middle)
        self.set("splitter.right_width", right)


_settings_instance = None


def get_settings():
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

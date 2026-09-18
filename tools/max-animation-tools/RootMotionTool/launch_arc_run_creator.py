# -*- coding: utf-8 -*-
"""Dedicated launcher that intentionally bypasses op_tools_hub."""
from __future__ import print_function

import imp
import os
import sys

_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_WINDOW_FILE = os.path.join(_TOOL_DIR, u"op_arc_run_creator.py")
_MODULE_NAME = "op_arc_run_creator_dedicated"

module = sys.modules.get(_MODULE_NAME)
module_file = os.path.normcase(os.path.abspath(
    getattr(module, "__file__", u"") or u""
)) if module is not None else u""
window = getattr(module, "_WINDOW", None) if module is not None else None
if (module is None or
        module_file != os.path.normcase(os.path.abspath(_WINDOW_FILE)) or
        window is None):
    module = imp.load_source(_MODULE_NAME, _WINDOW_FILE)

# Opening the window performs no MaxScript/Biped work. The backend is loaded
# only after the animator presses an operation button.
module.show()

# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import sys
import traceback

import pymxs


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL_ROOT = os.path.join(ROOT, "RootMotionTool")
if TOOL_ROOT not in sys.path:
    sys.path.insert(0, TOOL_ROOT)

from anim_migration.migration.track_transfer import collect_node_track_signatures, json_track_signatures
from anim_migration.migration.xaf_transfer import export_key_only_package, apply_key_only_package


rt = pymxs.runtime
package_path = os.path.join(ROOT, "validation", "_target_owned_keys_test.max")
result_path = os.path.join(ROOT, "validation", "_target_owned_keys_test_result.txt")


def _x_controller(node):
    return rt.getSubAnim(node.position.controller, 1).controller


def main():
    if len(list(rt.objects)) != 0:
        raise RuntimeError("validation requires an empty scene and will not reset the current file")
    source = rt.Point(name="OP_KeySource", size=5)
    with pymxs.animate(True):
        with pymxs.attime(0):
            source.position.x = 1.0
        with pymxs.attime(10):
            source.position.x = 12.5
    tracks = collect_node_track_signatures(
        rt, source, include_samples=False,
        include_unkeyed=False, include_controllers=False,
    )
    row = {
        "source_name": "OP_KeySource",
        "target_name": "OP_KeyTarget",
        "source_contract_id": "ui:source",
        "target_contract_id": "ui:target",
        "contract_layer": "UI",
        "track_signatures": json_track_signatures(tracks),
        "_node": source,
    }
    exported = export_key_only_package(rt, [row], package_path)
    if not exported.get("ok") or not exported.get("entries"):
        raise RuntimeError("export failed: {0}".format(exported))

    target = rt.Point(name="OP_KeyTarget", size=5)
    driven = rt.Point(name="OP_KeyDriven", size=5)
    connected = bool(rt.execute(
        'paramWire.connect $OP_KeyTarget.position.controller[#X_Position] '
        '$OP_KeyDriven.position.controller[#X_Position] "X_Position*2"'
    ))
    if not connected:
        raise RuntimeError("wire setup failed")
    target_controller = _x_controller(target)
    identity_before = id(target_controller)
    dependents_before = len(list(rt.refs.dependents(target_controller)))

    assignments = []
    for entry in exported.get("entries", []):
        assignment = dict(entry)
        assignment["_target_node"] = target
        assignments.append(assignment)
    applied = apply_key_only_package(rt, assignments, package_path)
    if not applied.get("ok"):
        raise RuntimeError("apply failed: {0}".format(applied))

    target_controller_after = _x_controller(target)
    dependents_after = len(list(rt.refs.dependents(target_controller_after)))
    rt.sliderTime = 10
    target_value = float(target.position.x)
    driven_value = float(driven.position.x)
    assert id(target_controller_after) == identity_before
    assert dependents_after >= dependents_before
    assert abs(target_value - 12.5) < 0.001
    assert abs(driven_value - 25.0) < 0.001
    message = "TARGET_OWNED_KEY_TRANSFER_MAX_OK identity=1 deps={0}->{1} target={2} driven={3}".format(
        dependents_before, dependents_after, target_value, driven_value,
    )
    with open(result_path, "w") as stream:
        stream.write(message + "\n")
    print(message)


try:
    main()
except Exception:
    with open(result_path, "w") as stream:
        stream.write(traceback.format_exc())
    raise
finally:
    try:
        if os.path.exists(package_path):
            os.remove(package_path)
    except Exception:
        pass

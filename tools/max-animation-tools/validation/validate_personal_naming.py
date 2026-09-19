# -*- coding: utf-8 -*-
"""Run with Python 2.7/3, or inside Max. Does not touch production files."""
from __future__ import print_function, unicode_literals
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, "RootMotionTool"))
from pipeline import personal_naming as personal
from pipeline.rm_naming import validate_indoor_name, parse_outdoor_source_name, clean_string_native
from pipeline.rm_file_io import get_unity_clip_asset_path, get_unity_indoor_path


def main(fixture_path=None):
    fixture_path = fixture_path or os.environ.get("ANIMATION_NAMING_FIXTURE")
    if fixture_path is None:
        fixture_path = os.path.join(ROOT, "..", "..", "tests", "fixtures", "animation-naming.json")
    with io.open(fixture_path, encoding="utf-8") as stream:
        fixture = json.load(stream)
    assets = os.path.abspath(os.path.join(ROOT, "..", "..", ".validation-temp", "Contract", "Client", "Assets"))
    source_root = os.path.join(assets, "Art", "Animations")
    clip_root = os.path.join(assets, "Generated", "AnimationClips")
    outputs = set()
    for case in fixture["personal"]:
        name = case["name"]
        valid, message, parsed = validate_indoor_name(name)
        assert valid, (name, message)
        assert parsed["char_name"] == case["character"]
        assert parsed["action_set"] == case["set"]
        assert parsed["action_name"] == case["action"]
        assert personal.compose_name(case["character"], case["action"], case["set"]) == name
        assert clean_string_native(name) == name
        purpose = case["folder"].split("/")[1]
        source = personal.source_destination(assets, case["character"], purpose, name + ".max")
        assert os.path.join("ArtSource", "Characters", case["character"], "Animations", purpose) in source
        dest = personal.unity_destination(assets, parsed, source)
        assert dest == os.path.join(source_root, *case["folder"].split("/"))
        clip = get_unity_clip_asset_path(clip_root, os.path.join(dest, name + ".fbx"), source_root)
        assert clip == os.path.join(clip_root, *case["folder"].split("/")) + os.sep + name + ".anim"
        assert clip not in outputs
        outputs.add(clip)
    for name in fixture["invalid"]:
        assert not validate_indoor_name(name)[0], name
    for name in fixture["legacy"]:
        assert validate_indoor_name(name)[0], name
        assert not personal.parse_name(name)[0], name
        expected = os.path.join(clip_root, "_".join(name.split("_")[:2]), name + ".anim")
        assert get_unity_clip_asset_path(clip_root, name + ".fbx") == expected
    for name in fixture["cinematic"]:
        assert not validate_indoor_name(name)[0], name
        assert parse_outdoor_source_name(name + ".max")[0], name
    assert get_unity_indoor_path(assets, {"Role": "Role"}, "Role", "Player") == os.path.join(source_root, "Role", "Role_Player")
    assert personal.purpose_from_source("D:/Outside/Player_Unarmed_Run.max") == "Common"
    assert personal.purpose_from_source("D:/Unarmed/Animations/Attacks/Player_Sword_Attack01.max") == "Attacks"
    try:
        personal.clip_path_from_fbx(clip_root, os.path.join(source_root, "..", "Elsewhere", "Player_Run.fbx"), source_root)
        raise AssertionError("Path escape was accepted")
    except ValueError:
        pass
    print("PERSONAL_NAMING_CONTRACT_PASS: 7 personal, 9 invalid, 3 legacy, 2 cinematic; routing and collision checks")


if __name__ == "__main__":
    main()

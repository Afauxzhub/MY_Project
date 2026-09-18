# -*- coding: utf-8 -*-
"""One-shot generator: copy RunExport into BaseLayer variant. Not part of runtime."""
from __future__ import print_function
import io
import os

SRC = os.path.join(os.path.dirname(__file__), "rm_indoor_backend.ms")
OUT = os.path.join(os.path.dirname(__file__), "rm_indoor_backend_baselayer.ms")

HEADER = u'''/*
  Indoor backend BASELAYER variant (parallel experimental entry).
  - Does NOT modify RMTool_IndoorBackend_RunExport / RM_Fix path.
  - Caller must fileIn rm_indoor_backend.ms first for shared helpers.
  - COM restore: biped.setTransform onto layer 0 (no createLayer "RM_Fix").
  - WallHit adjust: likewise onto layer 0 (no "WallHit_Adjust" layer).
  - PrepareIK_FullBreak = existing IK->FK bake + clear IK Object refs.
*/
global RMTool_IndoorBackend_PrepareIK_FullBreak
global RMTool_IndoorBackend_RunExport_BaseLayer
global RMTool_Backend_ApplyWallHitBipMotion_BaseLayer
global RMTool_Baselayer_ClearIKObjectHard
global RMTool_Baselayer_BackendVersion
RMTool_Baselayer_BackendVersion = "V1.1-BaseLayerCOM"

fn RMTool_Backend_ApplyWallHitBipMotion_BaseLayer bipObj sourceTransforms totalStartF wallHitSegments =
(
    -- Same math as RMTool_Backend_ApplyWallHitBipMotion; write to base layer 0.
    local riseStart = RMTool_Backend_FindWallHitSegment wallHitSegments "rise_start"
    local riseEnd = RMTool_Backend_FindWallHitSegment wallHitSegments "rise_end"
    local fallStart = RMTool_Backend_FindWallHitSegment wallHitSegments "fall_start"
    local landEnd = RMTool_Backend_FindWallHitSegment wallHitSegments "land_end"
    local wallLoop = RMTool_Backend_FindWallHitSegment wallHitSegments "wallhit_loop"
    local fallLoop = RMTool_Backend_FindWallHitSegment wallHitSegments "fall_loop"
    local riseLoop = RMTool_Backend_FindWallHitSegment wallHitSegments "rise_loop"
    if riseStart == undefined or riseEnd == undefined or fallStart == undefined or landEnd == undefined or wallLoop == undefined or fallLoop == undefined or riseLoop == undefined do
        throw "WallHit segment data incomplete"

    local adjustedPos = #()
    for tm in sourceTransforms do append adjustedPos [tm.pos.x, tm.pos.y, tm.pos.z]

    local rsStartIdx = RMTool_Backend_WallHitFrameIndex riseStart[2] totalStartF adjustedPos.count
    local rsEndIdx = RMTool_Backend_WallHitFrameIndex riseStart[3] totalStartF adjustedPos.count
    local reStartIdx = RMTool_Backend_WallHitFrameIndex riseEnd[2] totalStartF adjustedPos.count
    local reEndIdx = RMTool_Backend_WallHitFrameIndex riseEnd[3] totalStartF adjustedPos.count
    local fsEndIdx = RMTool_Backend_WallHitFrameIndex fallStart[3] totalStartF adjustedPos.count
    local leEndIdx = RMTool_Backend_WallHitFrameIndex landEnd[3] totalStartF adjustedPos.count
    if rsStartIdx == 0 or rsEndIdx == 0 or reStartIdx == 0 or reEndIdx == 0 or fsEndIdx == 0 or leEndIdx == 0 do
        throw "WallHit main segment range outside animation range"

    local riseStartPos = adjustedPos[rsStartIdx]
    for idx = rsStartIdx to rsEndIdx do adjustedPos[idx] = [riseStartPos.x, riseStartPos.y, riseStartPos.z]

    local mainStartIdx = reStartIdx
    if riseEnd[2] <= riseStart[3] do mainStartIdx = rsEndIdx + 1
    local sourceAnchorY = sourceTransforms[reStartIdx].pos.y
    for idx = mainStartIdx to leEndIdx do
    (
        local sourcePos = sourceTransforms[idx].pos
        adjustedPos[idx] = [sourcePos.x, sourcePos.y - sourceAnchorY, sourcePos.z]
    )

    local wallRefPos = adjustedPos[reEndIdx]
    local wallStartIdx = RMTool_Backend_WallHitFrameIndex wallLoop[2] totalStartF adjustedPos.count
    local wallEndIdx = RMTool_Backend_WallHitFrameIndex wallLoop[3] totalStartF adjustedPos.count
    if wallStartIdx == 0 or wallEndIdx == 0 do throw "WallHit Loop range outside animation range"
    for idx = wallStartIdx to wallEndIdx do adjustedPos[idx] = [wallRefPos.x, wallRefPos.y, wallRefPos.z]

    if fsEndIdx <= 1 do throw "WallHit Fall_Start requires at least two frames"
    local fallRefPos = adjustedPos[fsEndIdx]
    local fallVelocity = sourceTransforms[fsEndIdx].pos - sourceTransforms[fsEndIdx - 1].pos
    local fallLoopStartIdx = RMTool_Backend_WallHitFrameIndex fallLoop[2] totalStartF adjustedPos.count
    local fallLoopEndIdx = RMTool_Backend_WallHitFrameIndex fallLoop[3] totalStartF adjustedPos.count
    if fallLoopStartIdx == 0 or fallLoopEndIdx == 0 do throw "WallHit Fall_Loop range outside animation range"
    for idx = fallLoopStartIdx to fallLoopEndIdx do
    (
        local step = idx - fallLoopStartIdx
        adjustedPos[idx] = [fallRefPos.x, fallRefPos.y + fallVelocity.y * step, fallRefPos.z + fallVelocity.z * step]
    )

    local riseRefPos = adjustedPos[rsEndIdx]
    local riseLoopStartIdx = RMTool_Backend_WallHitFrameIndex riseLoop[2] totalStartF adjustedPos.count
    local riseLoopEndIdx = RMTool_Backend_WallHitFrameIndex riseLoop[3] totalStartF adjustedPos.count
    if riseLoopStartIdx == 0 or riseLoopEndIdx == 0 do throw "WallHit Rise_Loop range outside animation range"
    for idx = riseLoopStartIdx to riseLoopEndIdx do adjustedPos[idx] = [riseRefPos.x, riseRefPos.y, riseRefPos.z]

    local bipCtrl = bipObj.controller
    try (biped.setCurrentLayer bipCtrl 0) catch ()
    animate on
    (
        for idx = 1 to adjustedPos.count do
        (
            sliderTime = totalStartF + idx - 1
            biped.setTransform bipObj #pos adjustedPos[idx] true
        )
    )
    adjustedPos
)

fn RMTool_Baselayer_ForceZeroIKBlend node =
(
    if node == undefined or (not isValidNode node) do return false
    try
    (
        local ctrl = node.controller
        local nKeys = numKeys ctrl
        for i = 1 to nKeys do
        (
            local k = biped.getKey ctrl i
            try(k.ikBlend = 0.0)catch()
            try(k.ikSpace = 0)catch()
        )
        true
    )
    catch (false)
)

fn RMTool_Baselayer_ClearIKObjectHard node =
(
    if node == undefined or (not isValidNode node) do return false
    local ok = false
    try (ok = RMTool_Backend_ClearIKReferences node) catch (ok = false)
    if ok do
    (
        RMTool_Baselayer_ForceZeroIKBlend node
        return true
    )
    setCommandPanelTaskMode #motion
    select node
    completeRedraw()
    local statusTxt = try (RMTool_Backend_GetIKStatusText()) catch (undefined)
    local cycleTargets = #()
    append cycleTargets node
    try(if node.parent != undefined do append cycleTargets node.parent)catch()
    try(if node.parent != undefined and node.parent.parent != undefined do append cycleTargets node.parent.parent)catch()
    if statusTxt != undefined and statusTxt != "" do
    (
        local ikObj = undefined
        try (ikObj = getNodeByName statusTxt exact:true) catch ()
        if ikObj == undefined do try (ikObj = getNodeByName statusTxt) catch ()
        if ikObj != undefined do
        (
            insertItem ikObj cycleTargets 1
            RMTool_Backend_Log ("[Baselayer] resolved IK object=" + ikObj.name)
            try
            (
                local ctrl = node.controller
                local nKeys = numKeys ctrl
                for i = 1 to nKeys do
                (
                    local k = biped.getKey ctrl i
                    local t = k.time
                    at time t
                    (
                        sliderTime = t
                        try(k.ikSpace = 1)catch()
                        try(k.ikBlend = 1.0)catch()
                        RMTool_Backend_TrySetIKObjectVariants node ctrl k ikObj
                        RMTool_Backend_TrySetIKObjectVariants node ctrl k undefined
                    )
                    try(k.ikBlend = 0.0)catch()
                    try(k.ikSpace = 0)catch()
                )
            )
            catch ()
        )
    )
    local dlgOk = false
    try (dlgOk = RMTool_Backend_TryDriveIKDialog node cycleTargets) catch (dlgOk = false)
    RMTool_Baselayer_ForceZeroIKBlend node
    select node
    completeRedraw()
    local afterTxt = try (RMTool_Backend_GetIKStatusText()) catch (undefined)
    if afterTxt != undefined do RMTool_Backend_Log ("[Baselayer] ikStatusAfterHard=" + afterTxt)
    if dlgOk or afterTxt == undefined or afterTxt == "" do return true
    false
)

fn RMTool_IndoorBackend_PrepareIK_FullBreak bipObj onlyCam =
(
    local bakedCount = RMTool_IndoorBackend_PrepareIK bipObj onlyCam
    if onlyCam do return bakedCount
    if bipObj == undefined or (not isValidNode bipObj) do return bakedCount
    local limbsToClear = #()
    try(append limbsToClear (biped.getNode bipObj #larm link:4))catch()
    try(append limbsToClear (biped.getNode bipObj #rarm link:4))catch()
    try(append limbsToClear (biped.getNode bipObj #lleg link:4))catch()
    try(append limbsToClear (biped.getNode bipObj #rleg link:4))catch()
    local cleared = 0
    for node in limbsToClear where node != undefined do
    (
        local ok = false
        try (ok = RMTool_Baselayer_ClearIKObjectHard node) catch (ok = false)
        if ok do cleared += 1
    )
    RMTool_Backend_Log ("[Baselayer] PrepareIK_FullBreak baked=" + (bakedCount as string) + " clearedIK=" + (cleared as string))
    bakedCount
)

'''


def extract_balanced(text, start_paren):
    depth = 0
    i = start_paren
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start_paren : i + 1]
        i += 1
    raise RuntimeError("unbalanced paren")


def main():
    with io.open(SRC, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    marker = "fn RMTool_IndoorBackend_RunExport "
    start = text.find(marker)
    if start < 0:
        raise SystemExit("RunExport not found")
    eq = text.find("=", start)
    body_start = text.find("(", eq)
    fn_src = text[start:body_start] + extract_balanced(text, body_start)

    fn_src = fn_src.replace(
        "fn RMTool_IndoorBackend_RunExport ",
        "fn RMTool_IndoorBackend_RunExport_BaseLayer ",
        1,
    )
    fn_src = fn_src.replace(
        "RMTool_Backend_ApplyWallHitBipMotion bipObj sourceTransforms totalStartF wallHitSegments",
        "RMTool_Backend_ApplyWallHitBipMotion_BaseLayer bipObj sourceTransforms totalStartF wallHitSegments",
    )

    old_rm = (
        "            local bipCtrl = bipObj.controller\n"
        "            local layerIdxRM = biped.numLayers bipCtrl + 1\n"
        '            biped.createLayer bipCtrl layerIdxRM "RM_Fix"\n'
        "            biped.setCurrentLayer bipCtrl layerIdxRM\n"
        "            local customOffset = [offsetX, offsetY, offsetZ]"
    )
    new_rm = (
        "            -- Baselayer COM restore: write world pose onto layer 0 (no RM_Fix layer).\n"
        "            local bipCtrl = bipObj.controller\n"
        "            try (biped.setCurrentLayer bipCtrl 0) catch ()\n"
        "            local customOffset = [offsetX, offsetY, offsetZ]"
    )
    if old_rm not in fn_src:
        raise SystemExit("RM_Fix block not found")
    fn_src = fn_src.replace(old_rm, new_rm, 1)

    needle = "local rotDirMode = toLower (rotCustomDirMode as string)"
    insert = (
        needle
        + '\n    RMTool_Backend_Log ("[Baselayer] RunExport_BaseLayer backend=" + (RMTool_Baselayer_BackendVersion as string))'
    )
    if needle not in fn_src:
        raise SystemExit("rotDirMode log insert point missing")
    fn_src = fn_src.replace(needle, insert, 1)

    if not isinstance(fn_src, type(u"")):
        fn_src = fn_src.decode("utf-8")
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEADER)
        f.write(u"\n")
        f.write(fn_src)
        f.write(u"\n")

    check = io.open(OUT, encoding="utf-8").read()
    assert u"RunExport_BaseLayer" in check
    assert u'createLayer bipCtrl layerIdxRM "RM_Fix"' not in check
    assert u"Baselayer COM restore" in check
    assert u"PrepareIK_FullBreak" in check
    print("Wrote", OUT, "size", os.path.getsize(OUT))


if __name__ == "__main__":
    main()

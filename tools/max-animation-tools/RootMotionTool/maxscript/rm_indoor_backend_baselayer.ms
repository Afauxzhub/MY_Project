/*
  Indoor backend PROXY ROOT variant (official publisher; historical filename).
  - Does NOT modify RMTool_IndoorBackend_RunExport / RM_Fix path.
  - Caller must fileIn rm_indoor_backend.ms first for shared helpers.
  - The live Biped is evaluation-only. No Biped layer and no setTransform.
  - Root motion and compensated rigid world TMs are baked parent-first to an
    ordinary temporary proxy hierarchy by rm_proxy_fbx_export.ms.
  - WallHit offsets are computed into proxy target matrices only.
  - Source Root/Biped/IK controllers remain read-only throughout publishing.
*/
global RMTool_IndoorBackend_PrepareIK_FullBreak
global RMTool_IndoorBackend_RunExport_BaseLayer
global RMTool_IndoorBackend_PrepareIK
global RMTool_Backend_ApplyWallHitBipMotion_BaseLayer
global RMTool_Baselayer_ClearIKObjectHard
global RMTool_Baselayer_ForceLimbFKEval
global RMTool_Baselayer_ForceZeroIKBlend
global RMTool_Baselayer_ClearCOMTracks
global RMTool_Baselayer_COMTrackKeyCount
global RMTool_Baselayer_RestoreCOMWorld
global RMTool_Baselayer_BackendVersion
global RMTool_Proxy_BuildDesiredRootTransforms
global RMTool_Proxy_CreateContext
global RMTool_Proxy_ExportContext
global RMTool_Proxy_CleanupContext
global RMTool_Proxy_ScanAndCleanResidue
global RMTool_ADV_ToCleanBakeExportName
RMTool_Baselayer_BackendVersion = "V3.18-NearZeroScaleWorldReconcile"

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

    local adjustedTransforms = #()
    for idx = 1 to sourceTransforms.count do
    (
        local adjustedTM = copy sourceTransforms[idx]
        adjustedTM.pos = adjustedPos[idx]
        append adjustedTransforms adjustedTM
    )
    adjustedTransforms
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

fn RMTool_Baselayer_ForceLimbFKEval bipObj =
(
    -- Zero ikBlend on limb keys so COM setTransform is not fought by live IK.
    -- Does NOT clear IK Object (no dialog / no manual pause).
    if bipObj == undefined or (not isValidNode bipObj) do return 0
    local limbs = #()
    try(append limbs (biped.getNode bipObj #larm link:4))catch()
    try(append limbs (biped.getNode bipObj #rarm link:4))catch()
    try(append limbs (biped.getNode bipObj #lleg link:4))catch()
    try(append limbs (biped.getNode bipObj #rleg link:4))catch()
    local n = 0
    for node in limbs where node != undefined do
    (
        if RMTool_Baselayer_ForceZeroIKBlend node do n += 1
    )
    n
)

fn RMTool_Baselayer_COMTrackKeyCount bipObj =
(
    if bipObj == undefined or (not isValidNode bipObj) do return 0
    local ctrl = bipObj.controller
    local n = 0
    try (n += numKeys ctrl.horizontal) catch ()
    try (n += numKeys ctrl.vertical) catch ()
    try (n += numKeys ctrl.turning) catch ()
    n
)

fn RMTool_Baselayer_ClearCOMTracks bipObj =
(
    -- Wipe COM horizontal/vertical/turn keys on layer 0 only. Limb keys stay.
    -- Do NOT delete bipObj.pos/rotation controllers: that can detach Biped VHT
    -- and leave COM as a regular child that follows Root.
    if bipObj == undefined or (not isValidNode bipObj) do return 0
    local ctrl = bipObj.controller
    try (biped.setCurrentLayer ctrl 0) catch ()
    local keysBefore = RMTool_Baselayer_COMTrackKeyCount bipObj
    local cleared = 0
    local tracks = #()
    try(append tracks ctrl.horizontal)catch()
    try(append tracks ctrl.vertical)catch()
    try(append tracks ctrl.turning)catch()
    for tr in tracks where tr != undefined do
    (
        try (deleteKeys tr #allKeys; cleared += 1) catch ()
        try (deleteKeys tr.controller #allKeys; cleared += 1) catch ()
    )
    local keysAfter = RMTool_Baselayer_COMTrackKeyCount bipObj
    RMTool_Backend_Log ("[Baselayer] cleared COM VHT ops=" + (cleared as string) + " keys=" + (keysBefore as string) + "->" + (keysAfter as string))
    cleared
)

fn RMTool_Baselayer_RestoreCOMWorld bipObj originalTransforms totalStartF totalEndF customOffset rootMotionDebugLog rootObj enablePos rawRootPosList rootAddedYawList =
(
    -- Why RM_Fix can write original WORLD coords: createLayer stores a world-space
    -- offset, so node.world == target even while Root is moving.
    -- Layer 0 has no offset track. setTransform writes COM VHT; Max then parents
    -- Bip001 under Root, so node.world ~= writtenPos + root.pos.
    -- Writing original world on layer 0 therefore doubles Root travel (COM follows
    -- Root). Writing inverse(Root)*original also undoes bind Rx90 -> character lies
    -- down (V1.7 tgt[0,0,112] -> write[0,112,0]).
    -- Layer 0 must write originalPos - root.pos and keep original world rotation.
    if bipObj == undefined or (not isValidNode bipObj) do return 0.0
    if originalTransforms == undefined or originalTransforms.count == 0 do return 0.0
    if rootObj == undefined or (not isValidNode rootObj) do return 0.0

    local bipCtrl = bipObj.controller
    try (biped.setCurrentLayer bipCtrl 0) catch ()
    setCommandPanelTaskMode #motion
    select bipObj
    try (disableSceneRedraw()) catch ()

    animate on
    (
        for i = totalStartF to totalEndF do
        (
            sliderTime = i
            local idx = ((i - totalStartF) as integer) + 1
            if idx <= originalTransforms.count do
            (
                local srcTM = originalTransforms[idx]
                local desiredPos = srcTM.pos + customOffset
                local writePos = desiredPos - rootObj.pos
                local writeRot = srcTM.rotation
                if rootAddedYawList != undefined and idx <= rootAddedYawList.count do
                (
                    local yaw = rootAddedYawList[idx] as float
                    if abs yaw > 0.0001 do
                    (
                        local yawQ = (eulerangles 0 0 yaw) as quat
                        writeRot = (inverse yawQ) * writeRot
                    )
                )
                try (biped.addNewKey bipCtrl sliderTime) catch ()
                biped.setTransform bipObj #pos writePos true
                biped.setTransform bipObj #rotation writeRot true
                try (biped.setKey bipObj true true true) catch ()
            )
        )
    )
    try (enableSceneRedraw()) catch ()

    local restoreErrMax = 0.0
    local sampleText = ""
    for i = totalStartF to totalEndF do
    (
        sliderTime = i
        local idx = ((i - totalStartF) as integer) + 1
        if idx <= originalTransforms.count do
        (
            local srcTM = originalTransforms[idx]
            local desiredPos = srcTM.pos + customOffset
            local err = distance bipObj.transform.pos desiredPos
            if err > restoreErrMax do restoreErrMax = err
            if i == totalStartF or i == totalEndF or ((mod (idx - 1) 20) == 0) do
            (
                local writePos = desiredPos - rootObj.pos
                sampleText += " f" + (i as string) + "{tgt=" + (RMTool_Backend_VecToDebugString desiredPos) + " root=" + (RMTool_Backend_VecToDebugString rootObj.pos) + " write=" + (RMTool_Backend_VecToDebugString writePos) + " bip=" + (RMTool_Backend_VecToDebugString bipObj.transform.pos) + " err=" + (err as string) + "}"
            )
            if rootMotionDebugLog do
            (
                local rootPosDbg = try(rootObj.pos)catch(undefined)
                local rootRotXDbg = try(rootObj.rotation.controller.x_rotation)catch(undefined)
                local rootRotYDbg = try(rootObj.rotation.controller.y_rotation)catch(undefined)
                local rootRotZDbg = try(rootObj.rotation.controller.z_rotation)catch(undefined)
                local rootAddedPosDbg = [0.0, 0.0, 0.0]
                if enablePos and rawRootPosList != undefined and idx <= rawRootPosList.count do rootAddedPosDbg = rawRootPosList[idx]
                local yawDbg = 0.0
                if rootAddedYawList != undefined and idx <= rootAddedYawList.count do yawDbg = rootAddedYawList[idx]
                local bipOriginalText = RMTool_Backend_TMToDebugString srcTM
                local rootAddedPosText = RMTool_Backend_VecToDebugString rootAddedPosDbg
                local rootPosText = RMTool_Backend_VecToDebugString rootPosDbg
                local bipAfterText = RMTool_Backend_TMToDebugString bipObj.transform
                RMTool_Backend_Log ("[RootMotionDebug] frame=" + (i as string) + " | bipOriginal={" + bipOriginalText + "} | rootAdd={pos=" + rootAddedPosText + ", yawZ=" + (yawDbg as string) + "} | rootState={pos=" + rootPosText + ", rotXYZ=[" + (rootRotXDbg as string) + "," + (rootRotYDbg as string) + "," + (rootRotZDbg as string) + "]} | bipAfter={" + bipAfterText + "} | comErr=" + (err as string))
            )
        )
    )
    RMTool_Backend_Log ("[Baselayer] COM restore posMinusRoot worldErrMax=" + (restoreErrMax as string) + sampleText)
    restoreErrMax
)

fn RMTool_Baselayer_ClearIKObjectHard node =
(
    -- Stronger clear than legacy ClearIKReferences alone:
    -- 1) API clear  2) resolve named Attachment from status UI  3) dialog Body/Object drive
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
    -- Pass A: existing Smart IK->FK bake.
    local bakedCount = RMTool_IndoorBackend_PrepareIK bipObj onlyCam
    if onlyCam do return bakedCount
    if bipObj == undefined or (not isValidNode bipObj) do return bakedCount

    -- Pass B: sever IK Object references on limb tips (hard clear).
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


fn RMTool_IndoorBackend_RunExport_BaseLayer bipObj rootObj baseFbxName fbxFolder origFileFullName tempMaxFile deleteTemp isBatch enablePos followX followY followZ zThresCM zWeight zLimitRange zLimitStart zLimitEnd zHover zHoverHeight zHoverStart zHoverEnd useSmooth filterVal smoothStr smoothLimitRange smoothLimitStart smoothLimitEnd offsetX offsetY offsetZ enableRot forceKeys fixRot removeInitialZ unlockNodes expTimelineCam expIngameCam onlyCam posRmLimitRange posRmStart posRmEnd rootMotionDebugLog wallHitRootMotion wallHitSegments splitData rotCustomAngle rotCustomDegrees rotCustomDirMode rotLimitRange rotLimitStart rotLimitEnd proxySampleRate =
(
    if bipObj == undefined or (not isValidNode bipObj) do throw "Bip node missing"
    if rootObj == undefined or (not isValidNode rootObj) do throw "Root node missing"
    if rotCustomAngle == undefined do rotCustomAngle = false
    if rotCustomDegrees == undefined do rotCustomDegrees = 180.0
    if rotCustomDirMode == undefined do rotCustomDirMode = "auto"
    if rotLimitRange == undefined do rotLimitRange = false
    if rotLimitStart == undefined do rotLimitStart = 0
    if rotLimitEnd == undefined do rotLimitEnd = 100
    if proxySampleRate == undefined do proxySampleRate = 30
    proxySampleRate = proxySampleRate as integer
    if (findItem #(30, 60, 120) proxySampleRate) == 0 do throw ("ProxyRoot sample rate must be 30, 60, or 120 Hz; got " + (proxySampleRate as string))
    if frameRate != 30 do throw ("ProxyRoot 发布要求 Max 场景为 30 FPS；当前为 " + (frameRate as string) + " FPS。请先在时间配置中改为 30 FPS，并重新检查分段、旋转和位移帧范围后再发布。") debugBreak:false
    local proxySampleMultiplier = (proxySampleRate / 30) as integer
    local rotDirMode = toLower (rotCustomDirMode as string)
    RMTool_Backend_Log ("[Baselayer] RunExport_BaseLayer backend=" + (RMTool_Baselayer_BackendVersion as string) + " sourceBiped=sampleOnly proxyRoot=true sampleRate=" + (proxySampleRate as string) + "Hz")

    -- Show progress before residue cleanup/save.  Previously the window was
    -- created only after both operations but still displayed their label,
    -- making later Biped sampling look like a save-stage hang.
    if RMTool_Proxy_ProgressShow != undefined do RMTool_Proxy_ProgressShow ("FBX 发布 - " + (baseFbxName as string))
    if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.002 "清理上次发布残留..."

    -- Crash-residue self-heal: a Max-level crash during a previous publish can
    -- skip every restore path, leaving temp proxy bones and renamed source
    -- nodes behind. Clean them before touching anything else.
    if RMTool_Proxy_ScanAndCleanResidue != undefined do
    (
        try (RMTool_Proxy_ScanAndCleanResidue())
        catch (RMTool_Backend_Log ("[Baselayer] residue scan failed: " + (getCurrentException() as string)))
    )
    -- Save guard: publishing must never strand unsaved scene work. If Max dies
    -- mid-export the recovered file is exactly this saved state.
    if getSaveRequired() do
    (
        if maxFileName == "" do throw "Publish requires a saved scene: please save the max file once before publishing"
        local currentMaxFile = (maxFilePath + maxFileName)
        RMTool_Backend_Log ("[Baselayer] unsaved changes detected; saving before publish: " + currentMaxFile)
        if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.005 "保存当前场景..."
        saveMaxFile currentMaxFile quiet:true
    )

    if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.01 "采样质心并计算根运动..."

    local exportedPaths = #()
    local totalStartF = animationRange.start.frame as integer
    local totalEndF = animationRange.end.frame as integer
    local exportTasks = #()
    if splitData != undefined and splitData.count > 0 then
        exportTasks = splitData
    else
        append exportTasks #("", totalStartF, totalEndF)

    local originalRange = animationRange
    local finalFbxFolder = fbxFolder
    local useAdvExport = (not onlyCam) and (RMTool_Backend_HasDescendantNamed rootObj "Bone_Skin_Bip001 Pelvis")
    local proxyContext = undefined
    local proxyDesiredRootTransforms = #()
    local proxySourceBipTransforms = #()
    local proxyPoseBipTransforms = #()
    local proxyBaseRootTM = at time totalStartF (copy rootObj.transform)
    local proxyBaseX = 0.0
    local proxyBaseY = 0.0
    local proxyBaseZ = 0.0
    if wallHitRootMotion do
    (
        enablePos = true
        followX = false
        followY = true
        followZ = true
        enableRot = false
        useSmooth = false
        zLimitRange = false
        zHover = false
        posRmLimitRange = false
        offsetX = 0.0
        offsetY = 0.0
        offsetZ = 0.0
    )
    local useRootMotion = (enablePos or enableRot or wallHitRootMotion)

    -- The live Biped/Root are sample-only on every publish, with or without
    -- root motion: no IK bake, no layer, no COM key write.
    RMTool_Backend_Log "[Baselayer] live Biped/Root are sample-only; no IK bake, no layer, no COM key write"
    if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.012 "采样质心世界轨迹..."
    for i = totalStartF to totalEndF do at time i (append proxySourceBipTransforms (copy bipObj.transform))
    proxyPoseBipTransforms = for tm in proxySourceBipTransforms collect (copy tm)

    if useRootMotion do
    (
        local baseRot = at time totalStartF rootObj.rotation
        if classof baseRot == Quat do baseRot = baseRot as eulerangles
        proxyBaseX = baseRot.x
        proxyBaseY = baseRot.y
        proxyBaseZ = baseRot.z
        if fixRot do
        (
            local p = proxyBaseRootTM.pos
            local needsFix = (distance p [0,0,0] > 0.01) or (abs(proxyBaseX - 90.0) > 0.1) or (abs(proxyBaseY) > 0.1) or (abs(proxyBaseZ) > 0.1)
            if needsFix do
            (
                proxyBaseX = 90.0
                proxyBaseY = 0.0
                proxyBaseZ = 0.0
                local fixedQ = (eulerangles proxyBaseX proxyBaseY proxyBaseZ) as quat
                proxyBaseRootTM = fixedQ as matrix3
                proxyBaseRootTM.pos = [0,0,0]
            )
        )
        if wallHitRootMotion do
        (
            proxyPoseBipTransforms = RMTool_Backend_ApplyWallHitBipMotion_BaseLayer bipObj proxySourceBipTransforms totalStartF wallHitSegments
        )

        local rawRootPosList = #()

        if wallHitRootMotion then
        (
            rawRootPosList = RMTool_Backend_BuildWallHitRootPositions bipObj proxyPoseBipTransforms totalStartF wallHitSegments
        )
        else if enablePos then
        (
            local lFoot = try(biped.getNode bipObj #lleg link:3)catch(undefined)
            local rFoot = try(biped.getNode bipObj #rleg link:3)catch(undefined)
            if lFoot == undefined do lFoot = bipObj
            if rFoot == undefined do rFoot = bipObj

            local hiddenFootThres = units.decodeValue "2.0cm"
            local jumpHeightThres = RMTool_Backend_DecodeCM zThresCM
            local floorZ = 999999.0

            for i = totalStartF to totalEndF do
            (
                local z1 = at time i lFoot.transform.pos.z
                local z2 = at time i rFoot.transform.pos.z
                if z1 < floorZ do floorZ = z1
                if z2 < floorZ do floorZ = z2
            )

            local isGndArrRaw = #()
            local comZArr = #()
            local footMaxZArr = #()
            for i = totalStartF to totalEndF do
            (
                local z1 = at time i lFoot.transform.pos.z
                local z2 = at time i rFoot.transform.pos.z
                local minFootZ = amin z1 z2
                local grounded = minFootZ <= (floorZ + hiddenFootThres)
                append isGndArrRaw grounded
                append comZArr (at time i bipObj.transform.pos.z)
                append footMaxZArr minFootZ
            )

            local isGndArr = deepCopy isGndArrRaw
            local g = 1
            while g <= isGndArrRaw.count do
            (
                if isGndArrRaw[g] == false then
                (
                    local segStart = g
                    local segEnd = g
                    local maxZInSeg = footMaxZArr[g]
                    while (segEnd + 1 <= isGndArrRaw.count) and (isGndArrRaw[segEnd + 1] == false) do
                    (
                        segEnd += 1
                        if footMaxZArr[segEnd] > maxZInSeg do maxZInSeg = footMaxZArr[segEnd]
                    )
                    if (maxZInSeg - floorZ) < jumpHeightThres do
                    (
                        for k = segStart to segEnd do isGndArr[k] = true
                    )
                    g = segEnd + 1
                )
                else
                    g += 1
            )

            for i = 1 to proxyPoseBipTransforms.count do
            (
                local originalTM = proxyPoseBipTransforms[i]
                local tempPos = [0.0, 0.0, 0.0]
                if followX do tempPos.x = originalTM.pos.x
                if followY do tempPos.y = originalTM.pos.y
                append rawRootPosList tempPos
            )

            if useSmooth do
            (
                local idxStart = 1
                local idxEnd = rawRootPosList.count
                if smoothLimitRange do
                (
                    idxStart = smoothLimitStart - totalStartF + 1
                    idxEnd = smoothLimitEnd - totalStartF + 1
                    if idxStart < 1 do idxStart = 1
                    if idxEnd > rawRootPosList.count do idxEnd = rawRootPosList.count
                )
                if idxEnd > idxStart then
                (
                    local subList = for k = idxStart to idxEnd collect rawRootPosList[k]
                    local smoothedSubList = RMTool_Backend_ProcessRootTrajectory subList smoothStr filterVal
                    for k = 1 to smoothedSubList.count do rawRootPosList[idxStart + k - 1] = smoothedSubList[k]
                )
            )

            for i = 1 to proxyPoseBipTransforms.count do
            (
                local currentFrame = totalStartF + i - 1
                if followZ then
                (
                    local inRange = true
                    if zLimitRange do
                    (
                        if currentFrame < zLimitStart or currentFrame > zLimitEnd do inRange = false
                    )

                    if inRange then
                    (
                        if isGndArr[i] then
                            rawRootPosList[i].z = 0.0
                        else
                        (
                            local refCOMZ = undefined
                            for j = i to 1 by -1 do if isGndArr[j] do (refCOMZ = comZArr[j]; exit)
                            if refCOMZ == undefined do
                            (
                                for j = i to proxyPoseBipTransforms.count do if isGndArr[j] do (refCOMZ = comZArr[j]; exit)
                            )
                            local calcZ = 0.0
                            if refCOMZ != undefined then calcZ = (comZArr[i] - refCOMZ) * zWeight
                            else calcZ = (comZArr[i] - comZArr[1]) * zWeight
                            if calcZ < 0.0 do calcZ = 0.0
                            rawRootPosList[i].z = calcZ
                        )
                    )
                    else
                        rawRootPosList[i].z = 0.0
                )
                else
                    rawRootPosList[i].z = 0.0
            )

            if followZ and zHover do
            (
                local hoverTargetZ = RMTool_Backend_DecodeCM zHoverHeight
                for i = 1 to proxyPoseBipTransforms.count do
                (
                    local currentFrame = totalStartF + i - 1
                    if currentFrame >= zHoverStart and currentFrame <= zHoverEnd do rawRootPosList[i].z = hoverTargetZ
                )
            )

            if posRmLimitRange do
            (
                local ps = posRmStart as integer
                local pe = posRmEnd as integer
                if ps > pe do ( local tmp = ps; ps = pe; pe = tmp )
                for i = 1 to rawRootPosList.count do
                (
                    local cf = totalStartF + i - 1
                    if cf < ps or cf > pe do rawRootPosList[i] = [0.0, 0.0, 0.0]
                )
            )
        )

        local targetAngle = 0.0
        local rotStart = totalStartF
        local rotEnd = totalEndF
        local rotDuration = 1.0

        if enableRot do
        (
            local yawArr = #()
            if rotCustomAngle then
            (
                local degrees = abs (rotCustomDegrees as float)
                if rotDirMode == "right" or rotDirMode == "cw" or rotDirMode == "-" then
                    targetAngle = -degrees
                else if rotDirMode == "left" or rotDirMode == "ccw" or rotDirMode == "+" then
                    targetAngle = degrees
                else
                (
                    -- auto: follow COM cumulative yaw sign
                    local cumulativeYaw = 0.0
                    local lastYaw = undefined
                    for i = 1 to proxyPoseBipTransforms.count do
                    (
                        local tm = proxyPoseBipTransforms[i]
                        local fwd = normalize [tm.row2.x, tm.row2.y, 0]
                        local currentYaw = atan2 fwd.y fwd.x
                        if lastYaw != undefined do
                        (
                            local delta = currentYaw - lastYaw
                            if delta > 180.0 do delta -= 360.0
                            if delta < -180.0 do delta += 360.0
                            cumulativeYaw += delta
                        )
                        append yawArr cumulativeYaw
                        lastYaw = currentYaw
                    )
                    if cumulativeYaw < 0.0 then
                        targetAngle = -degrees
                    else
                        targetAngle = degrees
                )
            )
            else
            (
                local cumulativeYaw = 0.0
                local lastYaw = undefined
                for i = 1 to proxyPoseBipTransforms.count do
                (
                    local tm = proxyPoseBipTransforms[i]
                    local fwd = normalize [tm.row2.x, tm.row2.y, 0]
                    local currentYaw = atan2 fwd.y fwd.x
                    if lastYaw != undefined do
                    (
                        local delta = currentYaw - lastYaw
                        if delta > 180.0 do delta -= 360.0
                        if delta < -180.0 do delta += 360.0
                        cumulativeYaw += delta
                    )
                    append yawArr cumulativeYaw
                    lastYaw = currentYaw
                )
                if yawArr.count > 0 do targetAngle = yawArr[yawArr.count]
            )

            if rotLimitRange then
            (
                rotStart = rotLimitStart as integer
                rotEnd = rotLimitEnd as integer
                if rotStart > rotEnd do ( local tmp = rotStart; rotStart = rotEnd; rotEnd = tmp )
                if rotEnd <= rotStart do rotEnd = rotStart + 1
                rotDuration = (rotEnd - rotStart) as float
            )
            else if rotCustomAngle then
            (
                -- Custom angle without frame range: ease over full animation range.
                rotStart = totalStartF
                rotEnd = totalEndF
                if rotEnd <= rotStart do rotEnd = rotStart + 1
                rotDuration = (rotEnd - rotStart) as float
            )
            else if abs(targetAngle) > 2.0 then
            (
                local tStart = targetAngle * 0.05
                local tEnd = targetAngle * 0.95
                local sFound = false
                for i = 1 to yawArr.count do
                (
                    if (not sFound) and (abs(yawArr[i]) >= abs(tStart)) do
                    (
                        rotStart = totalStartF + i - 1
                        sFound = true
                    )
                    if abs(yawArr[i]) <= abs(tEnd) do rotEnd = totalStartF + i - 1
                )
                if rotEnd <= rotStart do rotEnd = rotStart + 1
                rotDuration = (rotEnd - rotStart) as float
            )
        )

        local rootAddedYawList = #()
        for i = totalStartF to totalEndF do
        (
            local addedVal = 0.0
            if enableRot do
            (
                if i >= rotEnd then
                    addedVal = targetAngle
                else if i > rotStart then
                    addedVal = targetAngle * (RMTool_Backend_SmoothStep (((i - rotStart) as float) / rotDuration))
            )
            append rootAddedYawList addedVal
        )

        if rootMotionDebugLog do
        (
            RMTool_Backend_Log ("[RootMotionDebug] begin base=" + (baseFbxName as string) + " frames=" + (totalStartF as string) + "-" + (totalEndF as string) + " enablePos=" + (enablePos as string) + " enableRot=" + (enableRot as string) + " targetAngle=" + (targetAngle as string) + " rotStart=" + (rotStart as string) + " rotEnd=" + (rotEnd as string) + " rotCustomAngle=" + (rotCustomAngle as string) + " rotLimitRange=" + (rotLimitRange as string))
        )

        if RMTool_Proxy_BuildDesiredRootTransforms == undefined do throw "ProxyRoot library not loaded"
        proxyDesiredRootTransforms = RMTool_Proxy_BuildDesiredRootTransforms proxyBaseRootTM proxyBaseX proxyBaseY proxyBaseZ rawRootPosList rootAddedYawList totalStartF totalEndF enablePos enableRot
        if proxyDesiredRootTransforms.count != (totalEndF - totalStartF + 1) do throw "ProxyRoot desired Root bake failed"
    )

    -- In-place publish (no root motion): the desired Root is simply the live
    -- sampled Root so the proxy reproduces the source pose exactly. Comping
    -- offsets belong to root motion and must not shift an in-place character.
    if not useRootMotion do
    (
        proxyDesiredRootTransforms = for i = totalStartF to totalEndF collect at time i (copy rootObj.transform)
    )

    -- Every character export goes through the proxy bone rebuild now; the
    -- ADV/official fallbacks only remain in the legacy publisher.
    if not onlyCam do
    (
        local proxyCustomOffset = if useRootMotion then [offsetX, offsetY, offsetZ] else [0,0,0]
        local proxyExtraNodes = RMTool_Backend_GetWeaponTempAttachmentNodes()
        if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.015 "构建并校验 ProxyRoot..."
        proxyContext = RMTool_Proxy_CreateContext rootObj bipObj proxySourceBipTransforms proxyPoseBipTransforms proxyDesiredRootTransforms totalStartF totalEndF proxyCustomOffset wallHitRootMotion useAdvExport proxyExtraNodes proxySampleMultiplier
        if proxyContext == undefined do throw "ProxyRoot context build failed"

        -- Numeric validation gates no longer abort inside CreateContext; they
        -- are collected as warnings. Interactive publish asks the user whether
        -- to export anyway; unattended batch must never ship unreviewed
        -- failures, so it still aborts with the full details.
        local proxyValidationWarnings = if proxyContext.count >= 25 and proxyContext[25] != undefined then proxyContext[25] else #()
        if proxyValidationWarnings.count > 0 do
        (
            local warnText = ""
            for w in proxyValidationWarnings do warnText += ("- " + (w as string) + "\n")
            RMTool_Backend_Log ("[Baselayer] numeric validation warnings (" + (proxyValidationWarnings.count as string) + "):\n" + warnText)
            if isBatch then
            (
                try (RMTool_Proxy_CleanupContext proxyContext) catch ()
                proxyContext = undefined
                throw ("ProxyRoot numeric validation failed; batch export aborted. Details:\n" + warnText)
            )
            else
            (
                local warnDialogText = "以下数值校验未通过：\n\n" + warnText + "\n仍要导出吗？（FBX 会照常导出，但可能包含姿态/缩放偏差；中止则清理临时骨骼且不产出文件）"
                local proceedWithWarnings = if RMTool_Proxy_TopMostQuery != undefined then (RMTool_Proxy_TopMostQuery warnDialogText "发布校验警告") else (queryBox warnDialogText title:"发布校验警告" beep:true)
                if not proceedWithWarnings do
                (
                    try (RMTool_Proxy_CleanupContext proxyContext) catch ()
                    proxyContext = undefined
                    throw "Publish aborted by user after validation warning"
                )
                RMTool_Backend_Log "[Baselayer] user chose to export despite validation warnings"
            )
        )
    )

    makeDir fbxFolder

    if RMTool_ADV_ToCleanBakeExportName == undefined do
        throw "ADV FBX helper library not loaded (fileIn adv_fbx_export_v25.ms first)"

    local exportTaskIndex = 0
    for task in exportTasks do
    (
        exportTaskIndex += 1
        local taskName = task[1]
        local s = task[2]
        local e = task[3]
        local taskJoiner = "_"
        if task.count >= 4 do taskJoiner = task[4]
        animationRange = interval s e
        if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.97 ("写出 FBX " + (exportTaskIndex as string) + "/" + (exportTasks.count as string) + "：" + (baseFbxName as string) + (if taskName != "" then "_" + (taskName as string) else "") + " ...")

        local targetCam = getNodeByName "Main_Camera"
        local camNodesWorld = #()
        local camNodesLocal = #()
        local origCamNames = #()

        if (expTimelineCam or expIngameCam) and targetCam != undefined do
        (
            local nodesToClone = #(targetCam)
            join nodesToClone (RMTool_Backend_GetAllDescendants targetCam)
            for n in nodesToClone do append origCamNames n.name

            if expTimelineCam do
            (
                maxOps.CloneNodes nodesToClone cloneType:#copy newNodes:&camNodesWorld offset:[0,0,0] expandHierarchy:false
                local bakedRoot = camNodesWorld[1]
                bakedRoot.parent = undefined
                try(bakedRoot.position.controller = Position_XYZ())catch()
                try(bakedRoot.rotation.controller = Euler_XYZ())catch()
                animate on
                (
                    for t = s to e do at time t
                    (
                        local tm = targetCam.transform
                        local p = tm.row4
                        local v1 = normalize tm.row1
                        local v2 = normalize tm.row2
                        local v3 = normalize tm.row3
                        bakedRoot.transform = matrix3 v1 v2 v3 p
                    )
                )
            )

            if expIngameCam do
            (
                maxOps.CloneNodes nodesToClone cloneType:#copy newNodes:&camNodesLocal offset:[0,0,0] expandHierarchy:false
                local bakedRoot = camNodesLocal[1]
                bakedRoot.parent = undefined
                try(bakedRoot.position.controller = Position_XYZ())catch()
                try(bakedRoot.rotation.controller = Euler_XYZ())catch()
                animate on
                (
                    for t = s to e do at time t
                    (
                        local camTM = targetCam.transform
                        local rootTM = rootObj.transform
                        local rootFrameIndex = t - totalStartF + 1
                        if proxyDesiredRootTransforms != undefined and rootFrameIndex > 0 and rootFrameIndex <= proxyDesiredRootTransforms.count do rootTM = proxyDesiredRootTransforms[rootFrameIndex]
                        local virtualRootTM = preRotateX rootTM -90
                        local finalTM = camTM * (inverse virtualRootTM)
                        local p = finalTM.row4
                        local v1 = normalize finalTM.row1
                        local v2 = normalize finalTM.row2
                        local v3 = normalize finalTM.row3
                        bakedRoot.transform = matrix3 v1 v2 v3 p
                    )
                )
            )
        )

        local tempXOffset = 0.0
        local tempYOffset = 0.0
        local tempZOffset = 0.0
        local rootStartPos = at time s rootObj.pos
        local rootEndPos = at time e rootObj.pos
        local rootStartIndex = s - totalStartF + 1
        local rootEndIndex = e - totalStartF + 1
        if proxyDesiredRootTransforms != undefined and rootStartIndex > 0 and rootStartIndex <= proxyDesiredRootTransforms.count do rootStartPos = proxyDesiredRootTransforms[rootStartIndex].pos
        if proxyDesiredRootTransforms != undefined and rootEndIndex > 0 and rootEndIndex <= proxyDesiredRootTransforms.count do rootEndPos = proxyDesiredRootTransforms[rootEndIndex].pos

        if followX do tempXOffset = rootStartPos.x
        if followY do
        (
            local isEntranceY = (rootStartPos.y < (units.decodeValue "-5.0cm")) and (abs(rootEndPos.y) < (units.decodeValue "5.0cm"))
            if not isEntranceY do tempYOffset = rootStartPos.y
        )
        if removeInitialZ and followZ do tempZOffset = rootStartPos.z

        local totalOffset = [-tempXOffset, -tempYOffset, -tempZOffset]
        -- totalOffset is applied to the temporary proxy Root only. The live
        -- rootObj never moves: moving it breaks Pos/Ori constraints to CTRLs
        -- outside Root.

        local actualTaskName = taskName
        if taskName != "" do actualTaskName = taskJoiner + taskName
        local taskBaseName = baseFbxName + actualTaskName

        if not onlyCam do
        (
            local charExportPath = fbxFolder + "\\" + taskBaseName + ".fbx"
            if proxyContext == undefined do throw "ProxyRoot context missing for character export"
            RMTool_Proxy_ExportContext proxyContext charExportPath s e totalOffset
            append exportedPaths charExportPath
        )

        if camNodesWorld.count > 0 do
        (
            for k = 1 to camNodesWorld.count do camNodesWorld[k].name = origCamNames[k] + "001"
            select camNodesWorld
            local camExportPath = fbxFolder + "\\" + taskBaseName + "_Cam_CS.fbx"
            RMTool_Backend_SetFbxParams s e cameras:true
            exportFile camExportPath #noPrompt selectedOnly:true using:FBXEXP
            append exportedPaths camExportPath
            delete camNodesWorld
        )

        if camNodesLocal.count > 0 do
        (
            for k = 1 to camNodesLocal.count do camNodesLocal[k].name = origCamNames[k] + "001"
            select camNodesLocal
            local camExportPath = fbxFolder + "\\" + taskBaseName + "_Cam.fbx"
            RMTool_Backend_SetFbxParams s e cameras:true
            exportFile camExportPath #noPrompt selectedOnly:true using:FBXEXP
            append exportedPaths camExportPath
            delete camNodesLocal
        )
    )

    animationRange = originalRange
    if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 1.0 "清理临时骨骼..."
    if proxyContext != undefined do
    (
        RMTool_Proxy_CleanupContext proxyContext
        proxyContext = undefined
    )

    if deleteTemp or isBatch do
    (
        if origFileFullName != undefined and origFileFullName != "" do loadMaxFile origFileFullName quiet:true
        if tempMaxFile != undefined and tempMaxFile != "" do deleteFile tempMaxFile
    )

    if RMTool_Proxy_ProgressHide != undefined do RMTool_Proxy_ProgressHide()
    exportedPaths
)

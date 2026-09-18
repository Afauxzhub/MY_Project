global RMTool_IndoorBackend_PrepareIK
global RMTool_IndoorBackend_RunExport
global RMTool_Backend_LogFile

RMTool_Backend_LogFile =
(
    local sourceFile = getSourceFileName()
    if sourceFile == undefined then undefined
    else pathConfig.appendPath (getFilenamePath sourceFile) @"..\publish_debug.log"
)

fn RMTool_Backend_Log msg =
(
    local f = undefined
    try
    (
        if RMTool_Backend_LogFile != undefined do
            f = openFile RMTool_Backend_LogFile mode:"a"
    )
    catch()
    if f != undefined do
    (
        format "[RMTool IK] %\n" msg to:f
        close f
    )
    try(format "[RMTool IK] %\n" msg)catch()
)

fn RMTool_Backend_VecToDebugString v =
(
    if v == undefined then
        "<undefined>"
    else
        ("[" + (v.x as string) + "," + (v.y as string) + "," + (v.z as string) + "]")
)

fn RMTool_Backend_RotToDebugString r =
(
    if r == undefined then return "<undefined>"
    local e = undefined
    try(e = r as eulerangles)catch()
    if e == undefined then
        (r as string)
    else
        ("euler=[" + (e.x as string) + "," + (e.y as string) + "," + (e.z as string) + "], quat=" + (r as string))
)

fn RMTool_Backend_TMToDebugString tm =
(
    if tm == undefined then
        "<undefined>"
    else
    (
        local posText = RMTool_Backend_VecToDebugString tm.pos
        local rotText = RMTool_Backend_RotToDebugString tm.rotation
        "pos=" + posText + ", rot=" + rotText
    )
)

fn RMTool_Backend_GetWindowTextSafe hwnd =
(
    local txt = ""
    if hwnd == undefined do return txt
    try(txt = UIAccessor.GetWindowText hwnd)catch()
    txt
)

fn RMTool_Backend_PressWindowSafe hwnd =
(
    if hwnd == undefined do return false
    try
    (
        UIAccessor.PressButton hwnd
        return true
    )
    catch()
    try
    (
        windows.sendMessage hwnd 245 0 0
        return true
    )
    catch()
    false
)

fn RMTool_Backend_FindDescendantByRID hwnd targetRID depth maxDepth =
(
    if hwnd == undefined or depth > maxDepth do return undefined
    local items = #()
    try(items = windows.getChildrenHWND hwnd)catch(items = #())
    for it in items do
    (
        local h = it[1]
        local rid = -1
        try(rid = UIAccessor.GetWindowResourceID h)catch()
        if rid == targetRID do return h
        local found = RMTool_Backend_FindDescendantByRID h targetRID (depth + 1) maxDepth
        if found != undefined do return found
    )
    undefined
)

fn RMTool_Backend_FindIKInfoDialog =
(
    local items = #()
    try(items = windows.getChildrenHWND #max)catch(items = #())
    for it in items do
    (
        local rootHwnd = it[1]
        local statusHwnd = RMTool_Backend_FindDescendantByRID rootHwnd 1099 0 4
        local objectBtn = RMTool_Backend_FindDescendantByRID rootHwnd 1100 0 4
        local pickerBtn = RMTool_Backend_FindDescendantByRID rootHwnd 1435 0 4
        if statusHwnd != undefined and objectBtn != undefined and pickerBtn != undefined do return rootHwnd
    )
    undefined
)

fn RMTool_Backend_GetIKStatusText =
(
    local dlg = RMTool_Backend_FindIKInfoDialog()
    if dlg == undefined do return undefined
    local statusHwnd = RMTool_Backend_FindDescendantByRID dlg 1099 0 4
    if statusHwnd == undefined do return undefined
    RMTool_Backend_GetWindowTextSafe statusHwnd
)

fn RMTool_Backend_TryDriveIKDialog node cycleTargets =
(
    local dlg = RMTool_Backend_FindIKInfoDialog()
    if dlg == undefined do
    (
        RMTool_Backend_Log ("ikDialog=<not found>")
        return false
    )

    local statusHwnd = RMTool_Backend_FindDescendantByRID dlg 1099 0 4
    local bodyBtn = RMTool_Backend_FindDescendantByRID dlg 1097 0 4
    local objectBtn = RMTool_Backend_FindDescendantByRID dlg 1100 0 4
    local pickerBtn = RMTool_Backend_FindDescendantByRID dlg 1435 0 4
    local beforeTxt = RMTool_Backend_GetWindowTextSafe statusHwnd

    RMTool_Backend_Log ("ikDialog=" + (dlg as string))
    RMTool_Backend_Log ("ikStatusHwnd=" + (statusHwnd as string) + " | text=" + beforeTxt)
    RMTool_Backend_Log ("ikBodyBtn=" + (bodyBtn as string))
    RMTool_Backend_Log ("ikObjectBtn=" + (objectBtn as string))
    RMTool_Backend_Log ("ikPickerBtn=" + (pickerBtn as string))

    if beforeTxt == "" do return true

    if objectBtn != undefined do
    (
        RMTool_Backend_PressWindowSafe objectBtn
        completeRedraw()
    )

    local cleared = false
    for target in cycleTargets where target != undefined do
    (
        if not cleared do
        (
            try(select target)catch()
            completeRedraw()
            RMTool_Backend_Log ("ikPickTarget=" + target.name)
            if pickerBtn != undefined do RMTool_Backend_PressWindowSafe pickerBtn
            completeRedraw()
            local currentTxt = RMTool_Backend_GetWindowTextSafe statusHwnd
            RMTool_Backend_Log ("ikStatusAfterPick=" + currentTxt)
            if currentTxt == "" do cleared = true
        )
    )

    if (not cleared) and bodyBtn != undefined do
    (
        RMTool_Backend_PressWindowSafe bodyBtn
        completeRedraw()
        local bodyTxt = RMTool_Backend_GetWindowTextSafe statusHwnd
        RMTool_Backend_Log ("ikStatusAfterBody=" + bodyTxt)
        if bodyTxt == "" do cleared = true
    )

    try(select node)catch()
    completeRedraw()
    local finalTxt = RMTool_Backend_GetWindowTextSafe statusHwnd
    RMTool_Backend_Log ("ikStatusFinal=" + finalTxt)
    (cleared or finalTxt == "")
)

fn RMTool_Backend_SmoothStep val =
(
    val * val * (3 - 2 * val)
)

fn RMTool_Backend_DecodeCM val =
(
    (val as float) * (units.decodeValue "1cm")
)

fn RMTool_Backend_ProcessRootTrajectory rawPosList smoothStr inputThresCM =
(
    local count = rawPosList.count
    if count < 2 do return rawPosList

    local realThres = RMTool_Backend_DecodeCM inputThresCM
    local filteredList = deepCopy rawPosList

    if realThres > 0.00001 do
    (
        local currentAnchor = rawPosList[1]
        filteredList[1] = currentAnchor
        for i = 2 to count do
        (
            local dist = distance rawPosList[i] currentAnchor
            if dist < realThres then filteredList[i] = currentAnchor
            else
            (
                filteredList[i] = rawPosList[i]
                currentAnchor = rawPosList[i]
            )
        )
    )

    local smoothedList = deepCopy filteredList
    if smoothStr > 0 do
    (
        for i = 2 to (count - 1) do
        (
            local sumPos = [0, 0, 0]
            local sampleCount = 0.0
            local startK = i - smoothStr
            local endK = i + smoothStr
            if startK < 1 do startK = 1
            if endK > count do endK = count
            for k = startK to endK do
            (
                sumPos += filteredList[k]
                sampleCount += 1.0
            )
            smoothedList[i] = sumPos / sampleCount
        )
    )

    smoothedList[1] = rawPosList[1]
    local targetEndPos = rawPosList[count]
    local currentEndPos = smoothedList[count]
    local totalErrorVec = targetEndPos - currentEndPos
    local frameDists = #(0.0)
    local totalMoveDist = 0.0

    for i = 2 to count do
    (
        local d = distance smoothedList[i] smoothedList[i - 1]
        if d < 0.001 do d = 0.0
        append frameDists d
        totalMoveDist += d
    )

    local currentAccumDist = 0.0
    for i = 1 to count do
    (
        currentAccumDist += frameDists[i]
        local weight = 0.0
        if totalMoveDist > 0.0001 then
            weight = currentAccumDist / totalMoveDist
        else
            weight = (i - 1) as float / ((count - 1) as float)
        if i == count do weight = 1.0
        smoothedList[i] = smoothedList[i] + (totalErrorVec * weight)
    )

    smoothedList
)

fn RMTool_Backend_GetAllDescendants rootNode =
(
    local result = #()
    if isValidNode rootNode do
    (
        local stack = #(rootNode)
        while stack.count > 0 do
        (
            local curr = stack[stack.count]
            stack.count = stack.count - 1
            for c in curr.children do
            (
                append stack c
                append result c
            )
        )
    )
    result
)

-- Morpher / Shape (blend shape) support for character FBX export.
fn RMTool_Backend_NodeHasMorpher node =
(
    if node == undefined or (not isValidNode node) do return false
    try
    (
        for m in node.modifiers where ((classof m) == Morpher) do return true
    )
    catch ()
    false
)

fn RMTool_Backend_AppendUniqueNode arr node =
(
    if node == undefined or (not isValidNode node) do return arr
    local found = false
    for n in arr where (isValidNode n) and (n == node) do found = true
    if not found do append arr node
    arr
)

-- 局内：全场景扫描含 Morpher 的模型。
fn RMTool_Backend_CollectMorpherMeshes rootNode:undefined =
(
    local result = #()
    try
    (
        for n in objects do
        (
            if (RMTool_Backend_NodeHasMorpher n) do
                result = RMTool_Backend_AppendUniqueNode result n
        )
    )
    catch ()
    result
)

fn RMTool_Backend_MergeMorpherMeshesIntoExportList objsToExport rootNode:undefined =
(
    local out = #()
    if objsToExport != undefined do
    (
        for n in objsToExport do out = RMTool_Backend_AppendUniqueNode out n
    )
    local morphMeshes = RMTool_Backend_CollectMorpherMeshes()
    if morphMeshes.count > 0 do
    (
        for n in morphMeshes do out = RMTool_Backend_AppendUniqueNode out n
        RMTool_Backend_Log ("[Morpher] include shape meshes=" + (morphMeshes.count as string))
    )
    out
)

fn RMTool_Backend_SameNodeName node expectedName =
(
    if node == undefined or not (isValidNode node) then false
    else ((toLower node.name) == (toLower expectedName))
)

fn RMTool_Backend_HasDescendantNamed rootNode expectedName =
(
    if rootNode == undefined or not (isValidNode rootNode) do return false
    if RMTool_Backend_SameNodeName rootNode expectedName do return true
    local descendants = RMTool_Backend_GetAllDescendants rootNode
    for n in descendants do
    (
        if RMTool_Backend_SameNodeName n expectedName do return true
    )
    false
)

fn RMTool_Backend_FindBipRootUnder rootNode fallbackBip =
(
    if fallbackBip != undefined and (isValidNode fallbackBip) do return fallbackBip
    if rootNode == undefined or not (isValidNode rootNode) do return undefined
    if RMTool_Backend_SameNodeName rootNode "Bip001" do return rootNode
    local descendants = RMTool_Backend_GetAllDescendants rootNode
    for n in descendants do
    (
        if RMTool_Backend_SameNodeName n "Bip001" do return n
    )
    undefined
)

fn RMTool_Backend_FilterBipHierarchyForSkinPelvisBranch objsToExport rootNode fallbackBip =
(
    if not (RMTool_Backend_HasDescendantNamed rootNode "Bone_Skin_Bip001 Pelvis") do return objsToExport
    local bipRoot = RMTool_Backend_FindBipRootUnder rootNode fallbackBip
    if bipRoot == undefined or not (isValidNode bipRoot) do return objsToExport
    local excluded = #(bipRoot)
    join excluded (RMTool_Backend_GetAllDescendants bipRoot)
    local filtered = #()
    for n in objsToExport do
    (
        if (findItem excluded n) == 0 do append filtered n
    )
    filtered
)

fn RMTool_Backend_FindNodeIndexByName nodes nodeName =
(
    for i = 1 to nodes.count do
    (
        if RMTool_Backend_SameNodeName nodes[i] nodeName do return i
    )
    0
)

fn RMTool_Backend_CollectSourceSubtreeIndices sourceNodes rootIndex =
(
    local indices = #()
    if rootIndex <= 0 or rootIndex > sourceNodes.count do return indices
    append indices rootIndex
    local stack = #(sourceNodes[rootIndex])
    while stack.count > 0 do
    (
        local curr = stack[stack.count]
        stack.count = stack.count - 1
        for c in curr.children do
        (
            local idx = findItem sourceNodes c
            if idx > 0 do
            (
                append indices idx
                append stack c
            )
        )
    )
    indices
)

fn RMTool_Backend_UnwrapEulerAngle currentValue previousValue =
(
    local value = currentValue
    while (value - previousValue) > 180.0 do value -= 360.0
    while (value - previousValue) < -180.0 do value += 360.0
    value
)

-- World TM with scale/shear removed (rigid pose). Baking full TM that still
-- contains parent scale makes Max write Foot/Toe local translations of 1e6..1e10.
fn RMTool_Backend_TMNoScale tm =
(
    local p = tm.pos
    local r1 = normalize tm.row1
    local r2 = tm.row2
    local r3 = normalize (cross r1 r2)
    if (length r3) < 0.00001 do r3 = normalize tm.row3
    r2 = normalize (cross r3 r1)
    matrix3 r1 r2 r3 p
)

-- Max sometimes yields matrix row lengths as percent (182) or percent*10 (1820).
-- Bake/FBX must receive factors (1.82). Hide-leg 0.1 stays unchanged.
fn RMTool_Backend_AsScaleFactor v =
(
    local a = abs v
    if a > 100.0 then (v / 1000.0)
    else if a > 8.0 then (v / 100.0)
    else v
)

fn RMTool_Backend_LocalScaleFactors node =
(
    if node == undefined or (not isValidNode node) do return [1, 1, 1]
    local tm = node.transform
    local p = node.parent
    local localTM = if p != undefined then (tm * (inverse p.transform)) else tm
    local sx = RMTool_Backend_AsScaleFactor (length localTM.row1)
    local sy = RMTool_Backend_AsScaleFactor (length localTM.row2)
    local sz = RMTool_Backend_AsScaleFactor (length localTM.row3)
    [sx, sy, sz]
)

-- "Bip001 L Thigh_1" -> "Bip001 L Thigh" (only strip trailing _<digits>)
fn RMTool_Backend_StripTrailingUnderscoreIndex name =
(
    local n = name as string
    local us = findString n "_"
    if us == undefined do return n
    local lastUs = 0
    local i = 1
    while i <= n.count do
    (
        if n[i] == "_" do lastUs = i
        i += 1
    )
    if lastUs == 0 do return n
    local suffix = substring n (lastUs + 1) -1
    local allDigits = (suffix.count > 0)
    for j = 1 to suffix.count do
    (
        local ch = suffix[j]
        if ch < "0" or ch > "9" do allDigits = false
    )
    if allDigits then (substring n 1 (lastUs - 1)) else n
)

-- Hide/stretch often lives on CTRL_Joint_* (outside Root), not on bone.scale.
fn RMTool_Backend_FindScaleDriverNode srcNode =
(
    if srcNode == undefined or (not isValidNode srcNode) do return undefined
    local bip = RMTool_Backend_ToCleanBakeExportName srcNode.name
    local base = RMTool_Backend_StripTrailingUnderscoreIndex bip
    local candidates = #(
        ("CTRL_Joint_" + base),
        ("CTRL_Joint_" + bip),
        ("CTRL_Corr_" + base),
        ("CTRL_Corr_" + bip)
    )
    local c
    for c in candidates do
    (
        local n = getNodeByName c exact:true
        if n != undefined and isValidNode n do return n
    )
    undefined
)

fn RMTool_Backend_ScaleDeviation sc =
(
    local dx = abs (sc.x - 1.0)
    local dy = abs (sc.y - 1.0)
    local dz = abs (sc.z - 1.0)
    local m = dx
    if dy > m do m = dy
    if dz > m do m = dz
    m
)

-- Bone matrix scale, overridden by CTRL driver when driver leaves 1.0 more
-- (covers hide-leg 0.1 / stretch 1.8 authored on CTRL_Joint).
fn RMTool_Backend_BakeScaleFactors srcNode =
(
    local sc = RMTool_Backend_LocalScaleFactors srcNode
    local drv = RMTool_Backend_FindScaleDriverNode srcNode
    if drv != undefined do
    (
        local ds = drv.scale
        -- Point3 literals must stay on one line in MaxScript (multi-line [ ] => "eol, expected ,").
        ds = point3 (RMTool_Backend_AsScaleFactor ds.x) (RMTool_Backend_AsScaleFactor ds.y) (RMTool_Backend_AsScaleFactor ds.z)
        if (RMTool_Backend_ScaleDeviation ds) > (RMTool_Backend_ScaleDeviation sc) do
            sc = ds
    )
    sc
)

fn RMTool_Backend_LocalScaleIsIntentional node s e =
(
    if node == undefined or (not isValidNode node) do return false
    local t
    for t = s to e do at time t
    (
        local sc = RMTool_Backend_BakeScaleFactors node
        if (RMTool_Backend_ScaleDeviation sc) > 0.05 do return true
    )
    false
)

-- Clean-bake FBX names only: strip anything before "Bip" so engine sees
-- legacy Bip names (Bone_Skin_Bip001 Pelvis -> Bip001 Pelvis). Names without
-- Bip stay unchanged. Does not touch the live scene Bone_Skin / controller Bip.
fn RMTool_Backend_ToCleanBakeExportName srcName =
(
    local name = srcName as string
    local idx = findString (toLower name) "bip"
    if idx == undefined then name
    else substring name idx -1
)

fn RMTool_Backend_TemporarilyFreeExportNames bakeNodes exportNames tempSuffix =
(
    local conflictNodes = #()
    local conflictOrigNames = #()
    local reserved = #()
    for n in exportNames do append reserved (toLower (n as string))

    for o in objects do
    (
        if isValidNode o and (findItem bakeNodes o) == 0 do
        (
            local key = toLower (o.name as string)
            if (findItem reserved key) > 0 do
            (
                append conflictNodes o
                append conflictOrigNames o.name
                o.name = o.name + tempSuffix
            )
        )
    )
    if conflictNodes.count > 0 do
        RMTool_Backend_Log (
            "[CleanBake] temporarily renamed " +
            (conflictNodes.count as string) +
            " live scene node(s) that owned export Bip names"
        )
    #(conflictNodes, conflictOrigNames)
)

fn RMTool_Backend_RestoreTemporarilyFreedNames conflictData =
(
    if conflictData == undefined do return false
    local conflictNodes = conflictData[1]
    local conflictOrigNames = conflictData[2]
    if conflictNodes == undefined do return false
    for i = 1 to conflictNodes.count do
    (
        try(if isValidNode conflictNodes[i] do conflictNodes[i].name = conflictOrigNames[i])catch()
    )
    true
)

fn RMTool_Backend_EulerFilterBakedNodes bakeNodes sourceNodes s e =
(
    local pelvisIdx = RMTool_Backend_FindNodeIndexByName sourceNodes "Bone_Skin_Bip001 Pelvis"
    local filterIndices = RMTool_Backend_CollectSourceSubtreeIndices sourceNodes pelvisIdx
    if filterIndices.count == 0 do return false

    for idx in filterIndices do
    (
        if idx > 0 and idx <= bakeNodes.count and isValidNode bakeNodes[idx] do
        (
            local prevEuler = undefined
            with animate on
            (
                for t = s to e do at time t
                (
                    local eul = bakeNodes[idx].rotation as eulerangles
                    if prevEuler != undefined do
                    (
                        eul.x = RMTool_Backend_UnwrapEulerAngle eul.x prevEuler.x
                        eul.y = RMTool_Backend_UnwrapEulerAngle eul.y prevEuler.y
                        eul.z = RMTool_Backend_UnwrapEulerAngle eul.z prevEuler.z
                    )
                    bakeNodes[idx].rotation = eul
                    prevEuler = eul
                )
            )
        )
    )
    true
)

fn RMTool_Backend_SourceHasIntentionalScale node s e =
(
    if node == undefined or (not isValidNode node) do return false
    local t
    for t = s to e do at time t
    (
        local sc = node.scale
        if (abs (sc.x - 1.0) > 0.05) or (abs (sc.y - 1.0) > 0.05) or (abs (sc.z - 1.0) > 0.05) do
            return true
    )
    false
)

-- Normalize temp-bone scale onto bezier_scale factor keys.
-- IMPORTANT: sample bakeNode.scale AFTER transform bake, NOT source.scale.
-- Overwriting with source.scale on the full chain re-breaks local PRS and
-- cascades parent percent*10 (Calf_1 ~1800) into Calf_2/Foot/Toe (millions).
fn RMTool_Backend_RebakeNodeScaleAsFactor bakeNode sourceNode s e =
(
    if bakeNode == undefined or (not isValidNode bakeNode) do return false
    -- sourceNode kept for call-site compatibility; values come from bakeNode.

    local samples = #()
    local t
    for t = s to e do at time t
    (
        append samples bakeNode.scale
    )
    if samples.count == 0 do return false

    -- Max 2020 ctor is bezier_scale (bare scale() is NOT the controller).
    local ctrlOk = false
    try
    (
        bakeNode.scale.controller = bezier_scale()
        ctrlOk = true
    )
    catch ()
    if not ctrlOk do
    (
        try
        (
            bakeNode.scale.controller = Bezier_Scale()
            ctrlOk = true
        )
        catch ()
    )
    if not ctrlOk do
    (
        local curClass = try(classOf bakeNode.scale.controller)catch(undefined)
        if curClass == bezier_scale or curClass == Bezier_Scale then
            ctrlOk = true
        else
        (
            RMTool_Backend_Log (
                "[CleanBake] bezier_scale controller unavailable on " +
                (bakeNode.name as string) + " class=" + (curClass as string)
            )
            return false
        )
    )
    try (deleteKeys bakeNode.scale.controller #allKeys) catch()

    with animate on
    (
        local i
        for i = 1 to samples.count do at time (s + i - 1)
        (
            bakeNode.scale = samples[i]
        )
    )
    true
)

fn RMTool_Backend_RebakeAllScalesAsFactor bakeNodes sourceNodes s e =
(
    -- Legacy name kept for callers; delegates to controller ensure pass.
    RMTool_Backend_EnsureBezierScaleControllers bakeNodes s e
)

-- Ensure temp bones use bezier_scale and re-key current baked local scale.
-- Does not read source.scale (avoids cascade). Safe after PRS freeze.
fn RMTool_Backend_EnsureBezierScaleControllers bakeNodes s e =
(
    if bakeNodes == undefined do return 0
    local fixedCount = 0
    local i
    for i = 1 to bakeNodes.count do
    (
        if RMTool_Backend_RebakeNodeScaleAsFactor bakeNodes[i] undefined s e do
            fixedCount += 1
    )
    if fixedCount > 0 do
        RMTool_Backend_Log (
            "[CleanBake] ensure bezier_scale on " +
            (fixedCount as string) + " temp bone(s)"
        )
    fixedCount
)

fn RMTool_Backend_CreateCleanBakedHierarchyContext objsToExport bakeStart bakeEnd =
(
    local sourceNodes = #()
    for n in objsToExport do
    (
        if isValidNode n do append sourceNodes n
    )
    if sourceNodes.count == 0 do return undefined

    local origNames = #()
    local bakeNodes = #()
    local bakeTempNames = #()
    local tempSuffix = "__OPExportOld_" + ((random 100000 999999) as string)
    local ctx = undefined

    try
    (
        for n in sourceNodes do append origNames n.name

        -- Create clean ordinary bones with temporary names first. Source names stay
        -- untouched during baking so expressions/constraints that reference names
        -- keep evaluating correctly.
        for i = 1 to sourceNodes.count do
        (
            local src = sourceNodes[i]
            local bn = BoneSys.createBone [0,0,0] [10,0,0] [0,0,1]
            bn.name = ("__OPCleanBake_" + (i as string) + "_" + ((random 100000 999999) as string))
            append bakeTempNames bn.name
            try(bn.boneEnable = true)catch()
            try(bn.boneAutoAlign = false)catch()
            try(bn.boneFreezeLength = true)catch()
            try(bn.boneScaleType = #none)catch()
            try(bn.rotation.controller = Euler_XYZ())catch()
            try(bn.scale.controller = bezier_scale())catch()
            bn.transform = src.transform
            append bakeNodes bn
        )

        -- Rebuild hierarchy + parent index (skip non-exported ancestors).
        local parentIdxOf = #()
        for i = 1 to sourceNodes.count do
        (
            local p = sourceNodes[i].parent
            local parentIdx = 0
            while p != undefined and parentIdx == 0 do
            (
                parentIdx = findItem sourceNodes p
                if parentIdx == 0 do p = p.parent
            )
            append parentIdxOf parentIdx
            if parentIdx > 0 do bakeNodes[i].parent = bakeNodes[parentIdx]
        )

        -- Parent-before-child bake order (depth ascending).
        local bakeOrder = #()
        local depths = #()
        for i = 1 to sourceNodes.count do
        (
            local d = 0
            local pidx = parentIdxOf[i]
            while pidx > 0 do
            (
                d += 1
                pidx = parentIdxOf[pidx]
                if d > 512 do pidx = 0
            )
            append depths d
            append bakeOrder i
        )
        for a = 1 to (bakeOrder.count - 1) do
        (
            for b = 1 to (bakeOrder.count - a) do
            (
                if depths[bakeOrder[b]] > depths[bakeOrder[b + 1]] do
                (
                    local tmp = bakeOrder[b]
                    bakeOrder[b] = bakeOrder[b + 1]
                    bakeOrder[b + 1] = tmp
                )
            )
        )

        -- 1) Rigid world pose only (no scale in TM). Keeps Foot/Toe local T sane.
        -- 2) Then key local scale factors only on bones that actually stretch/hide.
        local scaleIdx = #()
        for i = 1 to sourceNodes.count do
        (
            if RMTool_Backend_LocalScaleIsIntentional sourceNodes[i] bakeStart bakeEnd do
                append scaleIdx i
        )

        disableSceneRedraw()
        with animate on
        (
            for t = bakeStart to bakeEnd do at time t
            (
                for k = 1 to bakeOrder.count do
                (
                    local i = bakeOrder[k]
                    bakeNodes[i].transform = RMTool_Backend_TMNoScale sourceNodes[i].transform
                )
            )
        )
        for i = 1 to bakeNodes.count do
        (
            try (deleteKeys bakeNodes[i].scale.controller #allKeys) catch()
            animate off (bakeNodes[i].scale = [1, 1, 1])
        )
        local ctrlScaleCount = 0
        if scaleIdx.count > 0 do
        (
            for k = 1 to scaleIdx.count do
            (
                if (RMTool_Backend_FindScaleDriverNode sourceNodes[scaleIdx[k]]) != undefined do
                    ctrlScaleCount += 1
            )
            with animate on
            (
                for t = bakeStart to bakeEnd do at time t
                (
                    for k = 1 to scaleIdx.count do
                    (
                        local i = scaleIdx[k]
                        bakeNodes[i].scale = RMTool_Backend_BakeScaleFactors sourceNodes[i]
                    )
                )
            )
        )
        enableSceneRedraw()

        RMTool_Backend_EulerFilterBakedNodes bakeNodes sourceNodes bakeStart bakeEnd
        RMTool_Backend_Log (
            "[CleanBake] backend=2026-07-20-rigidTM-ctrlScale bones=" +
            (bakeNodes.count as string) + " scaleBones=" + (scaleIdx.count as string) +
            " ctrlDriven=" + (ctrlScaleCount as string)
        )

        ctx = #(sourceNodes, bakeNodes, origNames, bakeTempNames, tempSuffix)
    )
    catch
    (
        try(enableSceneRedraw())catch()
        RMTool_Backend_Log ("[CleanBakeContext] failed: " + (getCurrentException() as string))
        try(delete bakeNodes)catch()
    )

    ctx
)

fn RMTool_Backend_CleanupCleanBakedHierarchyContext ctx =
(
    if ctx == undefined do return false
    local sourceNodes = ctx[1]
    local bakeNodes = ctx[2]
    local origNames = ctx[3]
    for i = 1 to sourceNodes.count do
    (
        try
        (
            if isValidNode sourceNodes[i] do sourceNodes[i].name = origNames[i]
        )catch()
    )
    try(delete bakeNodes)catch()
    true
)

fn RMTool_Backend_ExportCleanBakedHierarchyFromContext ctx fbxPath s e totalOffset =
(
    if ctx == undefined do return false
    local sourceNodes = ctx[1]
    local bakeNodes = ctx[2]
    local origNames = ctx[3]
    local bakeTempNames = ctx[4]
    local tempSuffix = ctx[5]
    if bakeNodes == undefined or bakeNodes.count == 0 do return false
    local movedRoot = false
    local renamedForExport = false
    local conflictData = undefined
    local ok = false
    try
    (
        local exportNames = #()
        for i = 1 to origNames.count do
            append exportNames (RMTool_Backend_ToCleanBakeExportName origNames[i])

        -- Hard-fail on export-name collisions (two sources -> one Bip name).
        local coll = 0
        local i
        for i = 1 to exportNames.count do
        (
            local j
            for j = (i + 1) to exportNames.count do
            (
                if (toLower exportNames[i]) == (toLower exportNames[j]) do
                (
                    coll += 1
                    RMTool_Backend_Log (
                        "[CleanBake] COLLISION " + exportNames[i] + " <= " +
                        origNames[i] + " | " + origNames[j]
                    )
                )
            )
        )
        if coll > 0 do throw ("CleanBake export-name collisions=" + (coll as string))

        -- CRITICAL: do NOT rename all source Bone_Skin_/Bone_Twist_ nodes.
        -- Export names are stripped Bip001_* and normally do not collide with
        -- Bone_Skin_Bip001_*. Mass-renaming sources breaks CTRL constraints /
        -- wires / script controllers that resolve targets by name.
        -- Only suffix-rename a source when its exact name is needed by export.
        local reserved = #()
        for n in exportNames do append reserved (toLower (n as string))
        local renamedSrcCount = 0
        for i = 1 to sourceNodes.count do
        (
            local key = toLower (origNames[i] as string)
            if (findItem reserved key) > 0 do
            (
                sourceNodes[i].name = origNames[i] + tempSuffix
                renamedSrcCount += 1
            )
        )
        renamedForExport = true
        if renamedSrcCount > 0 do
            RMTool_Backend_Log (
                "[CleanBake] renamed " + (renamedSrcCount as string) +
                "/" + (sourceNodes.count as string) +
                " source node(s) for export-name clash"
            )

        -- Free live scene nodes that already own Bip001_* (excluded Biped tree).
        conflictData = RMTool_Backend_TemporarilyFreeExportNames bakeNodes exportNames tempSuffix
        for i = 1 to bakeNodes.count do bakeNodes[i].name = exportNames[i]

        if (length totalOffset) > 0.001 and isValidNode bakeNodes[1] do
        (
            animate off (move bakeNodes[1] totalOffset)
            movedRoot = true
        )
        local morphRootHint = undefined
        if sourceNodes.count > 0 and (isValidNode sourceNodes[1]) do morphRootHint = sourceNodes[1]
        local morphMeshes = RMTool_Backend_CollectMorpherMeshes rootNode:morphRootHint
        clearSelection()
        select bakeNodes
        if morphMeshes.count > 0 do
        (
            selectMore morphMeshes
            RMTool_Backend_Log ("[CleanBake] Morpher meshes=" + (morphMeshes.count as string))
        )
        -- Keys already baked; BakeAnimation OFF avoids percent*10 re-sample.
        RMTool_Backend_SetFbxParams s e bakeAnimation:false
        exportFile fbxPath #noPrompt selectedOnly:true using:FBXEXP
        ok = true
    )
    catch
    (
        RMTool_Backend_Log ("[CleanBakeExport] failed: " + (getCurrentException() as string))
    )
    if movedRoot do
    (
        try(animate off (move bakeNodes[1] -totalOffset))catch()
    )
    if renamedForExport do
    (
        for i = 1 to bakeNodes.count do
        (
            try(if isValidNode bakeNodes[i] do bakeNodes[i].name = bakeTempNames[i])catch()
        )
        RMTool_Backend_RestoreTemporarilyFreedNames conflictData
        for i = 1 to sourceNodes.count do
        (
            try(if isValidNode sourceNodes[i] do sourceNodes[i].name = origNames[i])catch()
        )
    )
    ok
)

fn RMTool_Backend_ExportCleanBakedHierarchy objsToExport fbxPath s e =
(
    local oldTime = sliderTime
    local oldSelection = selection as array
    local ctx = RMTool_Backend_CreateCleanBakedHierarchyContext objsToExport s e
    local ok = false
    if ctx != undefined do
    (
        ok = RMTool_Backend_ExportCleanBakedHierarchyFromContext ctx fbxPath s e [0,0,0]
        RMTool_Backend_CleanupCleanBakedHierarchyContext ctx
    )
    try(select oldSelection)catch()
    try(sliderTime = oldTime)catch()
    ok
)

fn RMTool_Backend_GetWeaponTempAttachmentNodes =
(
    local result = #()
    for o in objects do
    (
        if isValidNode o do
        (
            local mark = ""
            try(mark = getUserProp o "OPWeaponTemp")catch(mark = "")
            if mark == "OP_WS_TEMP_ATTACHMENT" do append result o
        )
    )
    result
)

fn RMTool_Backend_TryLoadOfficialFbxPreset =
(
    -- Align with Max stock Autodesk Media & Entertainment 2014/2016 style presets.
    local candidates = #(
        (getDir #maxData) + "\\FBX\\export presets\\Autodesk Media & Entertainment.fbxexportpreset",
        (getDir #maxData) + "\\FBX\\export presets\\Autodesk Media and Entertainment.fbxexportpreset",
        (getDir #maxRoot) + "\\plugcfg_ln\\FBX\\export presets\\Autodesk Media & Entertainment.fbxexportpreset",
        (getDir #maxRoot) + "\\plugcfg\\FBX\\export presets\\Autodesk Media & Entertainment.fbxexportpreset"
    )
    local i
    for i = 1 to candidates.count do
    (
        local p = candidates[i]
        if p != undefined and p != "" and (doesFileExist p) do
        (
            try
            (
                FBXExporterSetParam "LoadExportPresetFile" p
                RMTool_Backend_Log ("[FBX] loaded export preset: " + p)
                return true
            )
            catch()
        )
    )
    false
)

fn RMTool_Backend_EnsureFbxExporter =
(
    if FBXEXP == undefined do
    (
        try(pluginManager.loadClass FBXEXP)catch()
    )
    FBXEXP != undefined
)

fn RMTool_Backend_SetFbxParams s e cameras:false bakeAnimation:true =
(
    -- Base: official Media & Entertainment preset when available, then project overrides.
    if not (RMTool_Backend_EnsureFbxExporter()) do
        throw "FBXEXP plugin not loaded"
    RMTool_Backend_TryLoadOfficialFbxPreset()
    FBXExporterSetParam "Animation" true
    -- Clean-bake already froze constraints into keys. Leaving BakeAnimation ON can
    -- re-sample ScaleXYZ-style percent*10 (180 -> 1800). Pass bakeAnimation:false
    -- for clean-bake exports; keep true for live-rig / camera paths.
    FBXExporterSetParam "BakeAnimation" bakeAnimation
    FBXExporterSetParam "BakeFrameStart" s
    FBXExporterSetParam "BakeFrameEnd" e
    FBXExporterSetParam "UpAxis" "Y"
    FBXExporterSetParam "ShowWarnings" false
    if cameras do FBXExporterSetParam "Cameras" true
    -- Morpher / blend-shape animation (harmless when no Morpher in selection).
    -- Camera-only exports do not need Shape; leave default/preset for those.
    if not cameras do
    (
        try (FBXExporterSetParam "Shape" true) catch ()
    )
)

fn RMTool_Backend_ExportOfficialWithHideScale objsToExport fbxPath s e =
(
    global RMTool_HideScale_CaptureNodes
    global RMTool_HideScale_ApplyToSourceNodes
    global RMTool_HideScale_RestoreSourceNodes
    if RMTool_HideScale_CaptureNodes == undefined or RMTool_HideScale_ApplyToSourceNodes == undefined or RMTool_HideScale_RestoreSourceNodes == undefined do throw "HideScaleBake library not loaded"

    local hideContext = RMTool_HideScale_CaptureNodes objsToExport s e
    local exportOK = false
    local errorText = ""
    try
    (
        local appliedCount = RMTool_HideScale_ApplyToSourceNodes hideContext
        if appliedCount != hideContext.count do throw ("HideScaleBake apply failed: " + (appliedCount as string) + "/" + (hideContext.count as string))
        if appliedCount > 0 do RMTool_Backend_Log ("[HideScaleBake] official nodes=" + (appliedCount as string) + " frames=" + (s as string) + "-" + (e as string))
        RMTool_Backend_SetFbxParams s e
        local result = exportFile fbxPath #noPrompt selectedOnly:true using:FBXEXP
        if result == false do throw ("FBXExporter returned false: " + fbxPath)
        exportOK = true
    )
    catch(errorText = getCurrentException() as string)

    local restoredCount = RMTool_HideScale_RestoreSourceNodes hideContext
    if restoredCount != hideContext.count do
    (
        local restoreError = "HideScaleBake restore failed: " + (restoredCount as string) + "/" + (hideContext.count as string)
        if errorText == "" then errorText = restoreError else errorText += " | " + restoreError
        exportOK = false
    )
    if not exportOK do throw errorText
    true
)

fn RMTool_Backend_TrySetIKObjectVariants node ctrl keyObj target =
(
    local ok = false
    try( biped.setIKObject node target; ok = true )catch()
    try( biped.setIKObject node ctrl target; ok = true )catch()
    try( biped.setIKObject ctrl target; ok = true )catch()
    try( biped.setIKObject keyObj target; ok = true )catch()
    try( biped.setIKObject node keyObj target; ok = true )catch()
    ok
)

fn RMTool_Backend_ClearIKReferences node =
(
    if node == undefined or (not isValidNode node) do return false
    local cleared = false
    local cycleTargets = #()
    append cycleTargets node
    try(if node.parent != undefined do append cycleTargets node.parent)catch()
    try(if node.parent != undefined and node.parent.parent != undefined do append cycleTargets node.parent.parent)catch()

    RMTool_Backend_Log ("--- IK Clear Begin: node=" + node.name + " ---")
    try(if node.parent != undefined do RMTool_Backend_Log ("parent=" + node.parent.name))catch()
    try(if node.parent != undefined and node.parent.parent != undefined do RMTool_Backend_Log ("grandparent=" + node.parent.parent.name))catch()

    setCommandPanelTaskMode #motion
    select node
    completeRedraw()

    local statusBefore = RMTool_Backend_GetIKStatusText()
    if statusBefore != undefined do RMTool_Backend_Log ("ikStatusBefore=" + statusBefore)

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
                for target in cycleTargets where target != undefined do
                (
                    RMTool_Backend_TrySetIKObjectVariants node ctrl k target
                )
                RMTool_Backend_TrySetIKObjectVariants node ctrl k undefined
            )
            try(k.ikBlend = 0.0)catch()
            try(k.ikSpace = 0)catch()
        )
    )
    catch()

    for target in cycleTargets where target != undefined do
    (
        try
        (
            at time sliderTime
            (
                RMTool_Backend_TrySetIKObjectVariants node node.controller undefined target
            )
        )
        catch()
    )
    try
    (
        at time sliderTime
        (
            RMTool_Backend_TrySetIKObjectVariants node node.controller undefined undefined
        )
    )
    catch()

    local statusAfterAPI = RMTool_Backend_GetIKStatusText()
    if statusAfterAPI != undefined do RMTool_Backend_Log ("ikStatusAfterAPI=" + statusAfterAPI)
    if statusAfterAPI == "" do cleared = true

    clearSelection()
    cleared
)

fn RMTool_IndoorBackend_PrepareIK bipObj onlyCam =
(
    if onlyCam do return 0
    if bipObj == undefined or (not isValidNode bipObj) do throw "Bip node missing"

    local nodesToBake = #()
    local limbsToCheck = #()
    local bakedCount = 0
    try(append limbsToCheck (biped.getNode bipObj #larm link:4))catch()
    try(append limbsToCheck (biped.getNode bipObj #rarm link:4))catch()
    try(append limbsToCheck (biped.getNode bipObj #lleg link:4))catch()
    try(append limbsToCheck (biped.getNode bipObj #rleg link:4))catch()

    for node in limbsToCheck where node != undefined do
    (
        local ctrl = node.controller
        local ikRanges = #()
        local inRange = false
        local startF = undefined
        local nKeys = numKeys ctrl

        for i = 1 to nKeys do
        (
            local k = biped.getKey ctrl i
            local isIK = (k.ikSpace == 1 and k.ikBlend > 0.0)
            if isIK then
            (
                if not inRange then
                (
                    inRange = true
                    startF = k.time
                )
            )
            else if inRange then
            (
                inRange = false
                local endF = (biped.getKey ctrl (i - 1)).time
                if endF > startF do append ikRanges #(startF, endF)
            )
        )

        if inRange do
        (
            local endF = (biped.getKey ctrl nKeys).time
            if endF > startF do append ikRanges #(startF, endF)
        )

        if ikRanges.count > 0 do append nodesToBake #(node, ikRanges)
    )

    if nodesToBake.count > 0 do
    (
        bakedCount = nodesToBake.count
        setCommandPanelTaskMode #motion
        undo "Smart IK to FK Two-Pass" on
        (
            with redraw off
            (
                for item in nodesToBake do
                (
                    local node = item[1]
                    local ranges = item[2]
                    select node
                    with animate on
                    (
                        for r in ranges do for t = r[1] to r[2] do
                        (
                            sliderTime = t
                            biped.setKey node true true true
                        )
                        for r in ranges do for t = r[1] to r[2] do
                        (
                            sliderTime = t
                            biped.setFreeKey node
                        )
                    )
                )
            )
        )
    )
    clearSelection()
    bakedCount
)

fn RMTool_Backend_FindWallHitSegment wallHitSegments segmentKey =
(
    if wallHitSegments == undefined do return undefined
    for seg in wallHitSegments do
    (
        if seg != undefined and seg.count >= 3 and seg[1] == segmentKey do return seg
    )
    undefined
)

fn RMTool_Backend_WallHitFrameIndex frameValue totalStartF itemCount =
(
    local idx = (frameValue - totalStartF + 1) as integer
    if idx < 1 or idx > itemCount then 0 else idx
)

fn RMTool_Backend_ApplyWallHitBipMotion bipObj sourceTransforms totalStartF wallHitSegments =
(
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

    -- Rise_Start：质心完全原地，移除原动画的水平和垂直位移。
    local riseStartPos = adjustedPos[rsStartIdx]
    for idx = rsStartIdx to rsEndIdx do adjustedPos[idx] = [riseStartPos.x, riseStartPos.y, riseStartPos.z]

    -- Rise_End 之后的完整表现保留原轨迹，但把 Y 原点移回撞墙动作的局部原点。
    -- 两段共享的边界帧归 Rise_Start；从下一个独立帧开始恢复原始高度。
    local mainStartIdx = reStartIdx
    if riseEnd[2] <= riseStart[3] do mainStartIdx = rsEndIdx + 1
    local sourceAnchorY = sourceTransforms[reStartIdx].pos.y
    for idx = mainStartIdx to leEndIdx do
    (
        local sourcePos = sourceTransforms[idx].pos
        adjustedPos[idx] = [sourcePos.x, sourcePos.y - sourceAnchorY, sourcePos.z]
    )

    -- 贴墙 Loop：位置固定为 Rise_End 末帧，只保留肢体循环。
    local wallRefPos = adjustedPos[reEndIdx]
    local wallStartIdx = RMTool_Backend_WallHitFrameIndex wallLoop[2] totalStartF adjustedPos.count
    local wallEndIdx = RMTool_Backend_WallHitFrameIndex wallLoop[3] totalStartF adjustedPos.count
    if wallStartIdx == 0 or wallEndIdx == 0 do throw "WallHit Loop range outside animation range"
    for idx = wallStartIdx to wallEndIdx do adjustedPos[idx] = [wallRefPos.x, wallRefPos.y, wallRefPos.z]

    -- 下落 Loop：从 Fall_Start 末帧接起，按末两帧的 Y/Z 速度做线性延伸。
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

    -- 上升 Loop：固定为 Rise_Start 末帧的局部原地位置。
    local riseRefPos = adjustedPos[rsEndIdx]
    local riseLoopStartIdx = RMTool_Backend_WallHitFrameIndex riseLoop[2] totalStartF adjustedPos.count
    local riseLoopEndIdx = RMTool_Backend_WallHitFrameIndex riseLoop[3] totalStartF adjustedPos.count
    if riseLoopStartIdx == 0 or riseLoopEndIdx == 0 do throw "WallHit Rise_Loop range outside animation range"
    for idx = riseLoopStartIdx to riseLoopEndIdx do adjustedPos[idx] = [riseRefPos.x, riseRefPos.y, riseRefPos.z]

    local bipCtrl = bipObj.controller
    local layerIdx = biped.numLayers bipCtrl + 1
    biped.createLayer bipCtrl layerIdx "WallHit_Adjust"
    biped.setCurrentLayer bipCtrl layerIdx
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

fn RMTool_Backend_GetWallHitPoseNodePosition node bipObj adjustedTransforms frameIndex totalStartF =
(
    if node == undefined or bipObj == undefined do throw "WallHit pose-node evaluation missing node"
    if adjustedTransforms == undefined or frameIndex < 1 or frameIndex > adjustedTransforms.count do
        throw "WallHit pose-node frame outside adjusted transform range"
    local sourceFrame = totalStartF + frameIndex - 1
    local sourceBipTM = undefined
    local sourceNodeTM = undefined
    at time sourceFrame
    (
        sourceBipTM = copy bipObj.transform
        sourceNodeTM = copy node.transform
    )
    local targetNodeTM = try (sourceNodeTM * (inverse sourceBipTM) * adjustedTransforms[frameIndex]) catch (undefined)
    if targetNodeTM == undefined do throw ("WallHit cannot evaluate target pose node. node=" + (node.name as string) + " frame=" + (sourceFrame as string))
    copy targetNodeTM.pos
)

fn RMTool_Backend_BuildWallHitRootPositions bipObj adjustedTransforms totalStartF wallHitSegments =
(
    local riseStart = RMTool_Backend_FindWallHitSegment wallHitSegments "rise_start"
    local riseEnd = RMTool_Backend_FindWallHitSegment wallHitSegments "rise_end"
    local fallStart = RMTool_Backend_FindWallHitSegment wallHitSegments "fall_start"
    local landStart = RMTool_Backend_FindWallHitSegment wallHitSegments "land_start"
    local landLoop = RMTool_Backend_FindWallHitSegment wallHitSegments "land_loop"
    local landEnd = RMTool_Backend_FindWallHitSegment wallHitSegments "land_end"
    local wallLoop = RMTool_Backend_FindWallHitSegment wallHitSegments "wallhit_loop"
    local fallLoop = RMTool_Backend_FindWallHitSegment wallHitSegments "fall_loop"
    local riseLoop = RMTool_Backend_FindWallHitSegment wallHitSegments "rise_loop"
    local result = for tm in adjustedTransforms collect [0.0, 0.0, 0.0]

    local rsStartIdx = RMTool_Backend_WallHitFrameIndex riseStart[2] totalStartF result.count
    local rsEndIdx = RMTool_Backend_WallHitFrameIndex riseStart[3] totalStartF result.count
    local reStartIdx = RMTool_Backend_WallHitFrameIndex riseEnd[2] totalStartF result.count
    local reEndIdx = RMTool_Backend_WallHitFrameIndex riseEnd[3] totalStartF result.count
    local fsEndIdx = RMTool_Backend_WallHitFrameIndex fallStart[3] totalStartF result.count
    local lsStartIdx = RMTool_Backend_WallHitFrameIndex landStart[2] totalStartF result.count
    local lsEndIdx = RMTool_Backend_WallHitFrameIndex landStart[3] totalStartF result.count

    for idx = rsStartIdx to rsEndIdx do
        result[idx] = [0.0, adjustedTransforms[idx].pos.y, 0.0]

    -- Rise_End 首个独立帧：保持与 Rise_Start 末帧相同的 Root-to-Head 高度差。
    local headNode = try(biped.getNode bipObj #head)catch(undefined)
    if headNode == undefined do headNode = bipObj
    local peakIdx = reStartIdx
    if riseEnd[2] <= riseStart[3] do peakIdx = rsEndIdx + 1
    if peakIdx > fsEndIdx do throw "WallHit Rise_End/Fall_Start range invalid"
    -- Legacy builds a temporary Biped layer before reading Head. ProxyRoot keeps
    -- the live Biped read-only, so reconstruct the same target Head world pose
    -- from source Head relative to source Bip and the adjusted target Bip TM.
    local headRefPos = RMTool_Backend_GetWallHitPoseNodePosition headNode bipObj adjustedTransforms rsEndIdx totalStartF
    local peakHeadPos = RMTool_Backend_GetWallHitPoseNodePosition headNode bipObj adjustedTransforms peakIdx totalStartF
    local headRefZ = headRefPos.z
    local peakZ = peakHeadPos.z - headRefZ
    if peakZ < 0.0 do peakZ = 0.0
    local fallDuration = amax 1 (fsEndIdx - peakIdx)

    for idx = reStartIdx to fsEndIdx do
    (
        local zValue = 0.0
        if idx >= peakIdx do
        (
            local remain = ((fsEndIdx - idx) as float) / fallDuration
            if remain < 0.0 do remain = 0.0
            -- 4/3 次幂复现手工样例“前段快速释放、落地前收缓”的自然下降。
            zValue = peakZ * (remain ^ 1.333333)
        )
        result[idx] = [0.0, adjustedTransforms[idx].pos.y, zValue]
    )

    for idx = lsStartIdx to lsEndIdx do
        result[idx] = [0.0, adjustedTransforms[idx].pos.y, 0.0]

    -- Land_Loop 保持无根运动；Land_End 为衔接 Idle，Y 轴继续跟随质心，Z 轴保持为 0。
    local landRootRef = result[lsEndIdx]
    local landLoopStartIdx = RMTool_Backend_WallHitFrameIndex landLoop[2] totalStartF result.count
    local landLoopEndIdx = RMTool_Backend_WallHitFrameIndex landLoop[3] totalStartF result.count
    for idx = landLoopStartIdx to landLoopEndIdx do
        result[idx] = [landRootRef.x, landRootRef.y, landRootRef.z]

    local landEndStartIdx = RMTool_Backend_WallHitFrameIndex landEnd[2] totalStartF result.count
    local landEndEndIdx = RMTool_Backend_WallHitFrameIndex landEnd[3] totalStartF result.count
    for idx = landEndStartIdx to landEndEndIdx do
        result[idx] = [0.0, adjustedTransforms[idx].pos.y, 0.0]

    local wallRootRef = result[reEndIdx]
    local wallStartIdx = RMTool_Backend_WallHitFrameIndex wallLoop[2] totalStartF result.count
    local wallEndIdx = RMTool_Backend_WallHitFrameIndex wallLoop[3] totalStartF result.count
    for idx = wallStartIdx to wallEndIdx do
        result[idx] = [wallRootRef.x, wallRootRef.y, wallRootRef.z]

    -- Fall_Loop Root 跟随 Y/Z，始终保持 Fall_Start 末帧的质心高度差。
    local fallBipRefZ = adjustedTransforms[fsEndIdx].pos.z
    local fallLoopStartIdx = RMTool_Backend_WallHitFrameIndex fallLoop[2] totalStartF result.count
    local fallLoopEndIdx = RMTool_Backend_WallHitFrameIndex fallLoop[3] totalStartF result.count
    for idx = fallLoopStartIdx to fallLoopEndIdx do
    (
        result[idx] = [0.0, adjustedTransforms[idx].pos.y, adjustedTransforms[idx].pos.z - fallBipRefZ]
    )

    local riseRootRef = result[rsEndIdx]
    local riseLoopStartIdx = RMTool_Backend_WallHitFrameIndex riseLoop[2] totalStartF result.count
    local riseLoopEndIdx = RMTool_Backend_WallHitFrameIndex riseLoop[3] totalStartF result.count
    for idx = riseLoopStartIdx to riseLoopEndIdx do
        result[idx] = [riseRootRef.x, riseRootRef.y, riseRootRef.z]

    result
)

fn RMTool_IndoorBackend_RunExport bipObj rootObj baseFbxName fbxFolder origFileFullName tempMaxFile deleteTemp isBatch enablePos followX followY followZ zThresCM zWeight zLimitRange zLimitStart zLimitEnd zHover zHoverHeight zHoverStart zHoverEnd useSmooth filterVal smoothStr smoothLimitRange smoothLimitStart smoothLimitEnd offsetX offsetY offsetZ enableRot forceKeys fixRot removeInitialZ unlockNodes expTimelineCam expIngameCam onlyCam posRmLimitRange posRmStart posRmEnd rootMotionDebugLog wallHitRootMotion wallHitSegments splitData rotCustomAngle rotCustomDegrees rotCustomDirMode rotLimitRange rotLimitStart rotLimitEnd =
(
    if bipObj == undefined or (not isValidNode bipObj) do throw "Bip node missing"
    if rootObj == undefined or (not isValidNode rootObj) do throw "Root node missing"
    if rotCustomAngle == undefined do rotCustomAngle = false
    if rotCustomDegrees == undefined do rotCustomDegrees = 180.0
    if rotCustomDirMode == undefined do rotCustomDirMode = "auto"
    if rotLimitRange == undefined do rotLimitRange = false
    if rotLimitStart == undefined do rotLimitStart = 0
    if rotLimitEnd == undefined do rotLimitEnd = 100
    local rotDirMode = toLower (rotCustomDirMode as string)

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

    if useRootMotion do
    (
        if classof rootObj.rotation.controller != Euler_XYZ do rootObj.rotation.controller = Euler_XYZ()
        if classof rootObj.position.controller != Position_XYZ do rootObj.position.controller = Position_XYZ()

        if fixRot do
        (
            local p = rootObj.pos
            local rx = rootObj.rotation.controller.x_rotation
            local ry = rootObj.rotation.controller.y_rotation
            local rz = rootObj.rotation.controller.z_rotation
            local needsFix = (distance p [0,0,0] > 0.01) or (abs(rx - 90.0) > 0.1) or (abs(ry) > 0.1) or (abs(rz) > 0.1)
            if needsFix do
            (
                local rootChildren = for c in rootObj.children collect c
                for c in rootChildren do c.parent = undefined
                deleteKeys rootObj.controller #allKeys
                rootObj.pos = [0,0,0]
                rootObj.rotation.controller.x_rotation = 90.0
                rootObj.rotation.controller.y_rotation = 0.0
                rootObj.rotation.controller.z_rotation = 0.0
                for c in rootChildren do c.parent = rootObj
            )
        )

        local baseRot = at time totalStartF rootObj.rotation.controller.value
        if classof baseRot == Quat do baseRot = baseRot as eulerangles
        local baseX = baseRot.x
        local baseY = baseRot.y
        local baseZ = baseRot.z

        local sourceTransforms = #()
        for i = totalStartF to totalEndF do at time i (append sourceTransforms bipObj.transform)
        local originalTransforms = sourceTransforms
        if wallHitRootMotion do
        (
            RMTool_Backend_ApplyWallHitBipMotion bipObj sourceTransforms totalStartF wallHitSegments
            originalTransforms = #()
            for i = totalStartF to totalEndF do at time i (append originalTransforms bipObj.transform)
        )

        deleteKeys rootObj.rotation.controller #allKeys
        deleteKeys rootObj.position.controller #allKeys
        try(deleteKeys rootObj.scale.controller #allKeys)catch()

        local rawRootPosList = #()

        if wallHitRootMotion then
        (
            rawRootPosList = RMTool_Backend_BuildWallHitRootPositions bipObj originalTransforms totalStartF wallHitSegments
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

            for i = 1 to originalTransforms.count do
            (
                local originalTM = originalTransforms[i]
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

            for i = 1 to originalTransforms.count do
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
                                for j = i to originalTransforms.count do if isGndArr[j] do (refCOMZ = comZArr[j]; exit)
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
                for i = 1 to originalTransforms.count do
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
                    for i = 1 to originalTransforms.count do
                    (
                        local tm = originalTransforms[i]
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
                for i = 1 to originalTransforms.count do
                (
                    local tm = originalTransforms[i]
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

        animate on
        (
            if enableRot then
            (
                for i = totalStartF to totalEndF do
                (
                    sliderTime = i
                    local idx = ((i - totalStartF) as integer) + 1
                    local addedVal = rootAddedYawList[idx]
                    rootObj.rotation.controller.x_rotation = baseX
                    rootObj.rotation.controller.y_rotation = baseY
                    rootObj.rotation.controller.z_rotation = baseZ + addedVal
                )
            )

            for i = totalStartF to totalEndF do
            (
                sliderTime = i
                local idx = ((i - totalStartF) as integer) + 1
                if enablePos and idx <= rawRootPosList.count do rootObj.pos = rawRootPosList[idx]
            )
        )

        if (enableRot or enablePos) and (not onlyCam) do
        (
            local bipCtrl = bipObj.controller
            local layerIdxRM = biped.numLayers bipCtrl + 1
            biped.createLayer bipCtrl layerIdxRM "RM_Fix"
            biped.setCurrentLayer bipCtrl layerIdxRM
            local customOffset = [offsetX, offsetY, offsetZ]

            animate on
            (
                for i = totalStartF to totalEndF do
                (
                    sliderTime = i
                    local idx = ((i - totalStartF) as integer) + 1
                    if idx <= originalTransforms.count do
                    (
                        local targetTM = originalTransforms[idx]
                        biped.setTransform bipObj #pos (targetTM.pos + customOffset) true
                        biped.setTransform bipObj #rotation targetTM.rotation true
                        if rootMotionDebugLog do
                        (
                            local rootPosDbg = try(rootObj.pos)catch(undefined)
                            local rootRotXDbg = try(rootObj.rotation.controller.x_rotation)catch(undefined)
                            local rootRotYDbg = try(rootObj.rotation.controller.y_rotation)catch(undefined)
                            local rootRotZDbg = try(rootObj.rotation.controller.z_rotation)catch(undefined)
                            local rootAddedPosDbg = [0.0, 0.0, 0.0]
                            if enablePos and idx <= rawRootPosList.count do rootAddedPosDbg = rawRootPosList[idx]
                            local bipOriginalText = RMTool_Backend_TMToDebugString targetTM
                            local rootAddedPosText = RMTool_Backend_VecToDebugString rootAddedPosDbg
                            local rootPosText = RMTool_Backend_VecToDebugString rootPosDbg
                            local bipAfterText = RMTool_Backend_TMToDebugString bipObj.transform
                            RMTool_Backend_Log ("[RootMotionDebug] frame=" + (i as string) + " | bipOriginal={" + bipOriginalText + "} | rootAdd={pos=" + rootAddedPosText + ", yawZ=" + (rootAddedYawList[idx] as string) + "} | rootState={pos=" + rootPosText + ", rotXYZ=[" + (rootRotXDbg as string) + "," + (rootRotYDbg as string) + "," + (rootRotZDbg as string) + "]} | bipAfter={" + bipAfterText + "}")
                        )
                    )
                )
            )
        )
    )

    makeDir fbxFolder

    -- Custom Skin/Twist rig: ADV V2.5 Local-TM bake + Bip001 rename (not old clean-bake).
    global RMTool_ADV_ExportRootHierarchy
    global RMTool_ADV_BackendVersion
    local useAdvExport = (not onlyCam) and (RMTool_Backend_HasDescendantNamed rootObj "Bone_Skin_Bip001 Pelvis")
    if useAdvExport do
    (
        if RMTool_ADV_ExportRootHierarchy == undefined do
            throw "ADV FBX library not loaded (fileIn adv_fbx_export_v25.ms first)"
        RMTool_Backend_Log ("[ADV] backend=" + (try (RMTool_ADV_BackendVersion as string) catch ("V2.6-HideScaleBake+BipRename")))
        if unlockNodes do
        (
            local unlockObjs = #(rootObj)
            join unlockObjs (RMTool_Backend_GetAllDescendants rootObj)
            join unlockObjs (RMTool_Backend_GetWeaponTempAttachmentNodes())
            for o in unlockObjs do
            (
                if isValidNode o do
                (
                    if o.isFrozen do o.isFrozen = false
                    if o.isHidden do o.isHidden = false
                    local oLayer = o.layer
                    if oLayer != undefined do
                    (
                        if oLayer.isHidden do oLayer.isHidden = false
                        if oLayer.isFrozen do oLayer.isFrozen = false
                    )
                )
            )
        )
    )

    for task in exportTasks do
    (
        local taskName = task[1]
        local s = task[2]
        local e = task[3]
        local taskJoiner = "_"
        if task.count >= 4 do taskJoiner = task[4]
        animationRange = interval s e

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

        if followX do tempXOffset = rootStartPos.x
        if followY do
        (
            local isEntranceY = (rootStartPos.y < (units.decodeValue "-5.0cm")) and (abs(rootEndPos.y) < (units.decodeValue "5.0cm"))
            if not isEntranceY do tempYOffset = rootStartPos.y
        )
        if removeInitialZ and followZ do tempZOffset = rootStartPos.z

        local totalOffset = [-tempXOffset, -tempYOffset, -tempZOffset]
        -- ADV offsets TEMP bake root only. Moving live rootObj breaks Pos/Ori
        -- constraints to CTRLs outside Root. Only move live root on official path.
        local movedLiveRoot = false
        if (not useAdvExport) and (length totalOffset) > 0.001 do
        (
            animate off (move rootObj totalOffset)
            movedLiveRoot = true
        )

        local actualTaskName = taskName
        if taskName != "" do actualTaskName = taskJoiner + taskName
        local taskBaseName = baseFbxName + actualTaskName

        if not onlyCam do
        (
            local charExportPath = fbxFolder + "\\" + taskBaseName + ".fbx"
            if useAdvExport then
            (
                local weaponExtra = RMTool_Backend_GetWeaponTempAttachmentNodes()
                if not (RMTool_ADV_ExportRootHierarchy rootObj charExportPath s e excludeBiped:true strictValidate:false keepBake:false totalOffset:totalOffset extraNodes:weaponExtra) do
                    throw ("ADV FBX export failed: " + charExportPath)
            )
            else
            (
                local objsToExport = #(rootObj)
                join objsToExport (RMTool_Backend_GetAllDescendants rootObj)
                objsToExport = RMTool_Backend_FilterBipHierarchyForSkinPelvisBranch objsToExport rootObj bipObj
                local normalWeaponTempNodes = RMTool_Backend_GetWeaponTempAttachmentNodes()
                join objsToExport normalWeaponTempNodes
                objsToExport = RMTool_Backend_MergeMorpherMeshesIntoExportList objsToExport rootNode:rootObj
                if unlockNodes do
                (
                    for o in objsToExport do
                    (
                        if isValidNode o do
                        (
                            if o.isFrozen do o.isFrozen = false
                            if o.isHidden do o.isHidden = false
                            local oLayer = o.layer
                            if oLayer != undefined do
                            (
                                if oLayer.isHidden do oLayer.isHidden = false
                                if oLayer.isFrozen do oLayer.isFrozen = false
                            )
                        )
                    )
                )

                select objsToExport
                if forceKeys do
                (
                    local objectsToKey = #()
                    for o in objsToExport do
                    (
                        if isValidNode o do
                        (
                            local cls = classof o
                            if cls != Biped_Object then
                            (
                                if cls == BoneGeometry or cls == Dummy or cls == Point or cls == Bone or o == rootObj do append objectsToKey o
                            )
                        )
                    )

                    for o in objectsToKey do
                    (
                        try(addNewKey o.pos.controller s)catch()
                        try(addNewKey o.rotation.controller s)catch()
                        try(addNewKey o.scale.controller s)catch()
                        try(addNewKey o.pos.controller e)catch()
                        try(addNewKey o.rotation.controller e)catch()
                        try(addNewKey o.scale.controller e)catch()
                    )
                )

                RMTool_Backend_ExportOfficialWithHideScale objsToExport charExportPath s e
            )
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

        if movedLiveRoot do animate off (move rootObj -totalOffset)
    )

    animationRange = originalRange

    if deleteTemp or isBatch do
    (
        if origFileFullName != undefined and origFileFullName != "" do loadMaxFile origFileFullName quiet:true
        if tempMaxFile != undefined and tempMaxFile != "" do deleteFile tempMaxFile
    )

    exportedPaths
)

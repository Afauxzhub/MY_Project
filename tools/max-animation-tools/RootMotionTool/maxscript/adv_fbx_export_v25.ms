/*
  RMTool ADV FBX Export V2.5 library (no UI)
  Source: ADV_FBX_Export_V2_5_ZeroScaleSafe_FullTRS_GBK.ms
  Publish integration: exclude Root direct Biped tree; bake Local Matrix3 TRS;
  export bake bones renamed via ToCleanBakeExportName (Bip001...).
  Path comes from caller. Defaults: excludeBiped=true, strictValidate=false, keepBake=false.
*/

global RMTool_ADV_ExportRootHierarchy
global RMTool_ADV_ToCleanBakeExportName
global RMTool_ADV_BackendVersion
global RMTool_HideScale_CaptureNodes
global RMTool_HideScale_ContextHasNonUnit
global RMTool_HideScale_ApplyToBakeNodes

RMTool_ADV_BackendVersion = "V2.6-HideScaleBake+BipRename+MorphShape"

fn RMTool_ADV_Log msg =
(
    try (format "[RMTool] ADV-FBX %\n" (msg as string)) catch ()
)

fn RMTool_ADV_ToCleanBakeExportName srcName =
(
    local name = srcName as string
    local idx = findString (toLower name) "bip"
    if idx == undefined then name
    else substring name idx -1
)

fn RMTool_ADV_GetAllChildren n arr =
(
    append arr n
    for c in n.children do RMTool_ADV_GetAllChildren c arr
)

fn RMTool_ADV_IsBipedNode n =
(
    local nm = toLower n.name
    local nodeClassText = try (toLower ((classOf n) as string)) catch ("")
    local baseClassText = try (toLower ((classOf n.baseObject) as string)) catch ("")
    local tmControllerText = try (toLower ((classOf n.transform.controller) as string)) catch ("")

    local nameStartsWithBip = (nm.count >= 3 and (substring nm 1 3) == "bip")
    local classSaysBiped =
        (findString nodeClassText "biped" != undefined) or
        (findString baseClassText "biped" != undefined) or
        (findString tmControllerText "biped" != undefined)

    nameStartsWithBip or classSaysBiped
)

fn RMTool_ADV_CollectExportNodesExceptBipedBranches selectedRoot excludeBiped excludedBranchRoots =
(
    local result = #(selectedRoot)
    for childNode in selectedRoot.children do
    (
        if excludeBiped and (RMTool_ADV_IsBipedNode childNode) then
            append excludedBranchRoots childNode
        else
            RMTool_ADV_GetAllChildren childNode result
    )
    result
)

fn RMTool_ADV_CountBranchNodes branchRoot =
(
    local branchNodes = #()
    RMTool_ADV_GetAllChildren branchRoot branchNodes
    branchNodes.count
)

fn RMTool_ADV_JoinStrings arr separator =
(
    local result = ""
    for i = 1 to arr.count do
    (
        result += arr[i]
        if i < arr.count do result += separator
    )
    result
)

fn RMTool_ADV_FindDuplicateNodeNames nodes =
(
    local seen = #()
    local duplicates = #()
    for n in nodes do
    (
        local key = toLower n.name
        if (findItem seen key) == 0 then
            append seen key
        else if (findItem duplicates n.name) == 0 do
            append duplicates n.name
    )
    duplicates
)

fn RMTool_ADV_MatrixDet3 tm =
(
    dot tm.row1 (cross tm.row2 tm.row3)
)

fn RMTool_ADV_Max2 a b = if a > b then a else b

fn RMTool_ADV_MatrixAxisError tmA tmB =
(
    local e1 = distance tmA.row1 tmB.row1
    local e2 = distance tmA.row2 tmB.row2
    local e3 = distance tmA.row3 tmB.row3
    RMTool_ADV_Max2 e1 (RMTool_ADV_Max2 e2 e3)
)

fn RMTool_ADV_MatrixHasShear tm tolerance:0.0001 degenerateDetTolerance:0.00000001 =
(
    local sx = length tm.row1
    local sy = length tm.row2
    local sz = length tm.row3
    local detValue = RMTool_ADV_MatrixDet3 tm
    if (abs detValue) < degenerateDetTolerance or sx < 0.0000001 or sy < 0.0000001 or sz < 0.0000001 then
        false
    else
    (
        local xAxis = tm.row1 / sx
        local yAxis = tm.row2 / sy
        local zAxis = tm.row3 / sz
        ((abs (dot xAxis yAxis)) > tolerance) or
        ((abs (dot xAxis zAxis)) > tolerance) or
        ((abs (dot yAxis zAxis)) > tolerance)
    )
)

fn RMTool_ADV_GetControllerLocalTM n =
(
    local tm = try (copy n.transform.controller.value) catch (undefined)
    if tm != undefined and (classOf tm == Matrix3) then tm else undefined
)

fn RMTool_ADV_GetParentIndices nodes =
(
    local result = #()
    for i = 1 to nodes.count do
    (
        local idx = 0
        if i > 1 then
        (
            local p = nodes[i].parent
            while p != undefined and idx == 0 do
            (
                idx = findItem nodes p
                if idx == 0 do p = p.parent
            )
            if idx == 0 do idx = 1
        )
        append result idx
    )
    result
)

fn RMTool_ADV_GetStartFrameWorldTMs nodes startFrame =
(
    local result = #()
    at time startFrame
    (
        for n in nodes do append result (copy n.transform)
    )
    result
)

fn RMTool_ADV_GetDisplayBoneLength nodeIndex parentIndices startWorldTMs =
(
    local childIndex = 0
    for i = 1 to parentIndices.count do
    (
        if parentIndices[i] == nodeIndex and childIndex == 0 do childIndex = i
    )
    if childIndex > 0 then
    (
        local parentTM = startWorldTMs[nodeIndex]
        local detValue = RMTool_ADV_MatrixDet3 parentTM
        if (abs detValue) < 0.00000001 then
            1.0
        else
        (
            local childLocalTM = startWorldTMs[childIndex] * (inverse parentTM)
            local result = length childLocalTM.row4
            if result < 0.1 then 0.1 else result
        )
    )
    else
    (
        local parentIndex = parentIndices[nodeIndex]
        if parentIndex > 0 then
        (
            local parentTM = startWorldTMs[parentIndex]
            local detValue = RMTool_ADV_MatrixDet3 parentTM
            if (abs detValue) < 0.00000001 then
                1.0
            else
            (
                local localTM = startWorldTMs[nodeIndex] * (inverse parentTM)
                local result = (length localTM.row4) * 0.35
                if result < 0.1 then 0.1 else result
            )
        )
        else
            1.0
    )
)

fn RMTool_ADV_CreateBakeBone tempName displayLength =
(
    local bn = BoneSys.createBone [0,0,0] [1,0,0] [0,0,1]
    bn.name = tempName
    try (bn.boneEnable = false) catch ()
    try (bn.boneAutoAlign = false) catch ()
    try (bn.boneFreezeLength = false) catch ()
    try (bn.boneScaleType = #scale) catch ()
    try (bn.length = displayLength) catch ()
    try (bn.width = displayLength * 0.12) catch ()
    try (bn.height = displayLength * 0.12) catch ()
    try (bn.renderable = false) catch ()
    try (bn.wireColor = (color 0 200 255)) catch ()
    bn
)

fn RMTool_ADV_CaptureFBXSettings paramNames =
(
    local saved = #()
    for p in paramNames do
    (
        local oldValue = try (FBXExporterGetParam p) catch (unsupplied)
        if oldValue != unsupplied do append saved #(p, oldValue)
    )
    saved
)

fn RMTool_ADV_RestoreFBXSettings saved =
(
    for item in saved do
    (
        try (FBXExporterSetParam item[1] item[2]) catch ()
    )
)

fn RMTool_ADV_SetFBXParamSafe paramName paramValue =
(
    local result = try (FBXExporterSetParam paramName paramValue) catch (unsupplied)
    if result == unsupplied do format "[RMTool] ADV-FBX unsupported FBX param: %\n" paramName
    result
)

fn RMTool_ADV_TemporarilyFreeExportNames bakeNodes exportNames tempSuffix =
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
        RMTool_ADV_Log ("temporarily renamed " + (conflictNodes.count as string) + " live nodes owning export Bip names")
    #(conflictNodes, conflictOrigNames)
)

fn RMTool_ADV_RestoreTemporarilyFreedNames conflictData =
(
    if conflictData == undefined do return false
    local conflictNodes = conflictData[1]
    local conflictOrigNames = conflictData[2]
    if conflictNodes == undefined do return false
    for i = 1 to conflictNodes.count do
    (
        try (if isValidNode conflictNodes[i] do conflictNodes[i].name = conflictOrigNames[i]) catch ()
    )
    true
)

fn RMTool_ADV_MergeExtraNodes baseNodes extraNodes =
(
    if extraNodes == undefined do return baseNodes
    local result = for n in baseNodes collect n
    for n in extraNodes do
    (
        if isValidNode n and (findItem result n) == 0 do append result n
    )
    result
)

fn RMTool_ADV_NodeHasMorpher node =
(
    if node == undefined or (not isValidNode node) do return false
    try
    (
        for m in node.modifiers where ((classof m) == Morpher) do return true
    )
    catch ()
    false
)

-- Morpher meshes: full-scene scan (局内默认).
fn RMTool_ADV_CollectMorpherMeshesScene =
(
    local result = #()
    try
    (
        for n in objects do
        (
            if (RMTool_ADV_NodeHasMorpher n) and (findItem result n) == 0 do append result n
        )
    )
    catch ()
    result
)

-- Backward-compatible alias; indoor ADV always uses full scene.
fn RMTool_ADV_CollectMorpherMeshes rootNode =
(
    RMTool_ADV_CollectMorpherMeshesScene()
)

fn RMTool_ADV_ResolveMorpherMeshes morphMeshes autoMorph =
(
    local result = #()
    if morphMeshes != undefined do
    (
        for n in morphMeshes do
        (
            if isValidNode n and (RMTool_ADV_NodeHasMorpher n) and (findItem result n) == 0 do
                append result n
        )
    )
    if result.count == 0 and autoMorph do
        result = RMTool_ADV_CollectMorpherMeshesScene()
    result
)

fn RMTool_ADV_ExportRootHierarchy rootNode outPath startF endF excludeBiped:true strictValidate:false keepBake:false totalOffset:[0,0,0] extraNodes:#() morphMeshes:#() autoMorph:true =
(
    if rootNode == undefined or (not isValidNode rootNode) do
    (
        RMTool_ADV_Log "root missing"
        return false
    )
    if outPath == undefined or outPath == "" do
    (
        RMTool_ADV_Log "outPath empty"
        return false
    )
    if (toLower (getFilenameType outPath)) != ".fbx" do outPath += ".fbx"

    local startFrame = startF as integer
    local endFrame = endF as integer
    local frameCount = endFrame - startFrame + 1
    if frameCount < 1 do
    (
        RMTool_ADV_Log "invalid frame range"
        return false
    )

    local oldTime = sliderTime
    local oldSelection = getCurrentSelection()
    local oldTaskMode = getCommandPanelTaskMode()

    local excludedBipedBranchRoots = #()
    local allExportNodes = RMTool_ADV_CollectExportNodesExceptBipedBranches rootNode excludeBiped excludedBipedBranchRoots
    allExportNodes = RMTool_ADV_MergeExtraNodes allExportNodes extraNodes
    -- Morpher meshes must stay as live geometry (not baked to bones) so Shape export works.
    local morphMeshesResolved = RMTool_ADV_ResolveMorpherMeshes morphMeshes autoMorph
    if morphMeshesResolved.count > 0 do
    (
        local filtered = #()
        for n in allExportNodes do
        (
            if (findItem morphMeshesResolved n) == 0 do append filtered n
        )
        allExportNodes = filtered
        RMTool_ADV_Log ("excludedMorpherFromBake=" + (morphMeshesResolved.count as string))
    )
    if RMTool_HideScale_CaptureNodes == undefined or RMTool_HideScale_ContextHasNonUnit == undefined or RMTool_HideScale_ApplyToBakeNodes == undefined do
    (
        RMTool_ADV_Log "HideScaleBake library missing"
        return false
    )
    local hideScaleContext = RMTool_HideScale_CaptureNodes allExportNodes startFrame endFrame
    local preserveHideScale = RMTool_HideScale_ContextHasNonUnit hideScaleContext

    local ignoredNodeCount = 0
    for branchRoot in excludedBipedBranchRoots do
        ignoredNodeCount += RMTool_ADV_CountBranchNodes branchRoot

    if allExportNodes.count <= 1 do
    (
        RMTool_ADV_Log "no exportable non-Biped branches under Root"
        return false
    )

    local duplicateNames = RMTool_ADV_FindDuplicateNodeNames allExportNodes
    if duplicateNames.count > 0 do
    (
        RMTool_ADV_Log ("duplicate source names: " + (RMTool_ADV_JoinStrings duplicateNames ", "))
        return false
    )

    local parentIndices = RMTool_ADV_GetParentIndices allExportNodes
    local startWorldTMs = RMTool_ADV_GetStartFrameWorldTMs allExportNodes startFrame
    local originalNames = for n in allExportNodes collect n.name
    local bakeBones = #()
    local bakeTempNames = #()
    local savedFBXSettings = #()
    local editingSuspended = false
    local redrawDisabled = false
    local namesSwapped = false
    local exportSucceeded = false
    local movedBakeRoot = false
    local conflictData = undefined
    local tempSuffix = "__OPAdvExport_" + ((random 100000 999999) as string)
    local errorText = ""
    local currentStage = "init"
    local currentNodeName = rootNode.name
    local currentFrame = startFrame

    local worstPositionError = 0.0
    local worstAxisError = 0.0
    local worstWorldPositionError = 0.0
    local worstWorldAxisError = 0.0
    local worstWorldNodeName = ""
    local worstWorldFrame = startFrame
    local shearCount = 0
    local firstShearNode = ""
    local firstShearFrame = startFrame
    local nearZeroScaleCount = 0
    local firstNearZeroScaleNode = ""
    local firstNearZeroScaleFrame = startFrame
    local firstNearZeroScaleAxes = [1,1,1]
    local controllerLocalFallbackCount = 0
    local negativeDetCount = 0

    local fbxParamsToSave = #(
        "Animation", "AxisConversionMethod", "BakeAnimation",
        "BakeFrameStart", "BakeFrameEnd", "BakeFrameStep",
        "BakeResampleAnimation", "Cameras", "Lights", "Shape",
        "Skin", "EmbedTextures", "PointCache", "GeomAsBone",
        "FilterKeyReducer", "Removesinglekeys", "UpAxis",
        "ShowWarnings", "GenerateLog"
    )

    try
    (
        currentStage = "outdir"
        local outputDir = getFilenamePath outPath
        if outputDir != "" and not (doesDirectoryExist outputDir) do
        (
            if not (makeDir outputDir) do throw ("cannot create out dir: " + outputDir)
        )

        setCommandPanelTaskMode #create
        disableSceneRedraw()
        redrawDisabled = true
        suspendEditing()
        editingSuspended = true

        currentStage = "createBakeBones"
        for i = 1 to allExportNodes.count do
        (
            local displayLength = RMTool_ADV_GetDisplayBoneLength i parentIndices startWorldTMs
            local tempName = uniqueName "__ADV_BAKE__"
            local bn = RMTool_ADV_CreateBakeBone tempName displayLength
            append bakeBones bn
            append bakeTempNames bn.name
        )

        currentStage = "relink"
        for i = 1 to bakeBones.count do
        (
            local parentIndex = parentIndices[i]
            if parentIndex > 0 do bakeBones[i].parent = bakeBones[parentIndex]
        )

        currentStage = "bakeLocalTM"
        for f = startFrame to endFrame do
        (
            currentFrame = f
            at time f
            (
                local frameWorldTMs = #()
                local frameLocalTMs = #()

                for n in allExportNodes do append frameWorldTMs (copy n.transform)

                for i = 1 to allExportNodes.count do
                (
                    currentNodeName = allExportNodes[i].name
                    local parentIndex = parentIndices[i]
                    local localTM = undefined

                    if parentIndex > 0 then
                    (
                        local parentDet = RMTool_ADV_MatrixDet3 frameWorldTMs[parentIndex]
                        if (abs parentDet) >= 0.00000001 then
                            localTM = frameWorldTMs[i] * (inverse frameWorldTMs[parentIndex])
                        else
                        (
                            localTM = RMTool_ADV_GetControllerLocalTM allExportNodes[i]
                            if localTM == undefined do
                                throw (
                                    "parent scale ~0 and cannot read child controller Local TM. parent=" +
                                    allExportNodes[parentIndex].name + " child=" + allExportNodes[i].name +
                                    " frame=" + (f as string)
                                )
                            controllerLocalFallbackCount += 1
                        )
                    )
                    else
                        localTM = frameWorldTMs[i]

                    local localDet = RMTool_ADV_MatrixDet3 localTM
                    if (abs localDet) < 0.00000001 do
                    (
                        nearZeroScaleCount += 1
                        if firstNearZeroScaleNode == "" do
                        (
                            firstNearZeroScaleNode = allExportNodes[i].name
                            firstNearZeroScaleFrame = f
                            firstNearZeroScaleAxes = [length localTM.row1, length localTM.row2, length localTM.row3]
                        )
                    )
                    if localDet < 0.0 do negativeDetCount += 1
                    if RMTool_ADV_MatrixHasShear localTM do
                    (
                        shearCount += 1
                        if firstShearNode == "" do
                        (
                            firstShearNode = allExportNodes[i].name
                            firstShearFrame = f
                        )
                    )
                    append frameLocalTMs localTM
                )

                animate on
                (
                    for i = 1 to bakeBones.count do
                    (
                        currentNodeName = allExportNodes[i].name
                        bakeBones[i].transform.controller.value = frameLocalTMs[i]
                    )
                )

                for i = 1 to bakeBones.count do
                (
                    currentNodeName = allExportNodes[i].name
                    local bakedLocalTM = try (copy bakeBones[i].transform.controller.value) catch (undefined)
                    if bakedLocalTM == undefined or (classOf bakedLocalTM != Matrix3) do
                        throw ("cannot read bake Local TM: " + bakeBones[i].name + " f=" + (f as string))

                    local posError = distance frameLocalTMs[i].row4 bakedLocalTM.row4
                    local axisError = RMTool_ADV_MatrixAxisError frameLocalTMs[i] bakedLocalTM
                    if posError > worstPositionError do worstPositionError = posError
                    if axisError > worstAxisError do worstAxisError = axisError

                    local bakedWorldTM = bakeBones[i].transform
                    local worldPosError = distance frameWorldTMs[i].row4 bakedWorldTM.row4
                    local worldAxisError = RMTool_ADV_MatrixAxisError frameWorldTMs[i] bakedWorldTM
                    if worldPosError > worstWorldPositionError or worldAxisError > worstWorldAxisError do
                    (
                        if worldPosError > worstWorldPositionError do worstWorldPositionError = worldPosError
                        if worldAxisError > worstWorldAxisError do worstWorldAxisError = worldAxisError
                        worstWorldNodeName = allExportNodes[i].name
                        worstWorldFrame = f
                    )
                )
            )
        )

        currentStage = "hideScaleBake"
        local hideScaleApplied = RMTool_HideScale_ApplyToBakeNodes hideScaleContext allExportNodes bakeBones
        if hideScaleApplied != hideScaleContext.count do
            throw ("HideScaleBake ADV apply failed: " + (hideScaleApplied as string) + "/" + (hideScaleContext.count as string))

        currentStage = "strictValidate"
        if strictValidate and (shearCount > 0 or worstWorldPositionError > 0.001 or worstWorldAxisError > 0.001) do
        (
            throw (
                "strict matrix validate failed. node=" + worstWorldNodeName +
                " frame=" + (worstWorldFrame as string) +
                " shearCount=" + (shearCount as string) +
                " worldPosErr=" + (worstWorldPositionError as string) +
                " worldAxisErr=" + (worstWorldAxisError as string)
            )
        )

        currentStage = "bipRename"
        local exportNames = #()
        for i = 1 to originalNames.count do
            append exportNames (RMTool_ADV_ToCleanBakeExportName originalNames[i])

        local coll = 0
        for i = 1 to exportNames.count do
        (
            for j = (i + 1) to exportNames.count do
            (
                if (toLower exportNames[i]) == (toLower exportNames[j]) do
                (
                    coll += 1
                    RMTool_ADV_Log ("COLLISION " + exportNames[i] + " <= " + originalNames[i] + " | " + originalNames[j])
                )
            )
        )
        if coll > 0 do throw ("export-name collisions=" + (coll as string))

        namesSwapped = true
        local reserved = #()
        for n in exportNames do append reserved (toLower (n as string))
        for i = 1 to allExportNodes.count do
        (
            local key = toLower (originalNames[i] as string)
            if (findItem reserved key) > 0 do
                allExportNodes[i].name = originalNames[i] + tempSuffix
        )
        conflictData = RMTool_ADV_TemporarilyFreeExportNames bakeBones exportNames tempSuffix
        for i = 1 to bakeBones.count do bakeBones[i].name = exportNames[i]

        if totalOffset != undefined and (length totalOffset) > 0.001 and isValidNode bakeBones[1] do
        (
            animate off (move bakeBones[1] totalOffset)
            movedBakeRoot = true
        )

        resumeEditing()
        editingSuspended = false
        enableSceneRedraw()
        redrawDisabled = false
        setCommandPanelTaskMode oldTaskMode
        completeRedraw()

        clearSelection()
        select bakeBones
        local morphMeshes = morphMeshesResolved
        if morphMeshes.count > 0 do
        (
            selectMore morphMeshes
            RMTool_ADV_Log ("morpherMeshes=" + (morphMeshes.count as string))
        )

        currentStage = "fbxExport"
        pluginManager.loadClass FBXEXPORTER
        savedFBXSettings = RMTool_ADV_CaptureFBXSettings fbxParamsToSave

        RMTool_ADV_SetFBXParamSafe "Animation" true
        RMTool_ADV_SetFBXParamSafe "AxisConversionMethod" "Animation"
        RMTool_ADV_SetFBXParamSafe "BakeAnimation" (not preserveHideScale)
        RMTool_ADV_SetFBXParamSafe "BakeFrameStart" startFrame
        RMTool_ADV_SetFBXParamSafe "BakeFrameEnd" endFrame
        RMTool_ADV_SetFBXParamSafe "BakeFrameStep" 1
        RMTool_ADV_SetFBXParamSafe "BakeResampleAnimation" (not preserveHideScale)
        RMTool_ADV_SetFBXParamSafe "FilterKeyReducer" false
        RMTool_ADV_SetFBXParamSafe "Removesinglekeys" false
        RMTool_ADV_SetFBXParamSafe "Cameras" false
        RMTool_ADV_SetFBXParamSafe "Lights" false
        -- Shape/Morpher: enable when Morpher meshes are in the selection.
        -- GeomAsBone must be OFF for those meshes or Morph channels are dropped.
        local exportMorphShapes = (morphMeshes.count > 0)
        RMTool_ADV_SetFBXParamSafe "Shape" true
        if exportMorphShapes then
        (
            RMTool_ADV_SetFBXParamSafe "Skin" true
            RMTool_ADV_SetFBXParamSafe "GeomAsBone" false
        )
        else
        (
            RMTool_ADV_SetFBXParamSafe "Skin" false
            RMTool_ADV_SetFBXParamSafe "GeomAsBone" true
        )
        RMTool_ADV_SetFBXParamSafe "EmbedTextures" false
        RMTool_ADV_SetFBXParamSafe "PointCache" false
        RMTool_ADV_SetFBXParamSafe "UpAxis" "Y"
        RMTool_ADV_SetFBXParamSafe "ShowWarnings" false
        RMTool_ADV_SetFBXParamSafe "GenerateLog" false

        RMTool_ADV_Log (
            "backend=" + RMTool_ADV_BackendVersion +
            " bones=" + (allExportNodes.count as string) +
            " morphMeshes=" + (morphMeshes.count as string) +
            " excludedBipedNodes=" + (ignoredNodeCount as string) +
            " hideScaleNodes=" + (hideScaleContext.count as string) +
            " hideScaleNoResample=" + (preserveHideScale as string) +
            " nearZeroScaleSamples=" + (nearZeroScaleCount as string) +
            " ctrlLocalFallback=" + (controllerLocalFallbackCount as string) +
            " shearSamples=" + (shearCount as string)
        )
        if firstNearZeroScaleNode != "" do
            RMTool_ADV_Log (
                "firstNearZeroScale node=" + firstNearZeroScaleNode +
                " frame=" + (firstNearZeroScaleFrame as string) +
                " axes=" + (firstNearZeroScaleAxes as string)
            )

        local exportResult = exportFile outPath #noPrompt selectedOnly:true using:FBXEXP
        if exportResult == false do throw "FBXExporter returned false"
        exportSucceeded = true
    )
    catch
    (
        errorText = getCurrentException() as string
        RMTool_ADV_Log ("FAILED stage=" + currentStage + " node=" + currentNodeName + " frame=" + (currentFrame as string) + " err=" + errorText)
        try (format "ADV stack: %\n" (getCurrentExceptionStackTrace())) catch ()
    )

    try (RMTool_ADV_RestoreFBXSettings savedFBXSettings) catch ()
    if movedBakeRoot do
    (
        try (animate off (move bakeBones[1] -totalOffset)) catch ()
    )
    if editingSuspended do
    (
        try (resumeEditing()) catch ()
        editingSuspended = false
    )
    if redrawDisabled do
    (
        try (enableSceneRedraw()) catch ()
        redrawDisabled = false
    )
    try (setCommandPanelTaskMode oldTaskMode) catch ()

    if namesSwapped do
    (
        for i = 1 to bakeBones.count do
        (
            try (if isValidNode bakeBones[i] do bakeBones[i].name = bakeTempNames[i]) catch ()
        )
        RMTool_ADV_RestoreTemporarilyFreedNames conflictData
        for i = 1 to allExportNodes.count do
        (
            try (if isValidNode allExportNodes[i] do allExportNodes[i].name = originalNames[i]) catch ()
        )
    )

    try (sliderTime = oldTime) catch ()

    if exportSucceeded and keepBake then
    (
        for i = 1 to bakeBones.count do
        (
            try (bakeBones[i].name = uniqueName (originalNames[i] + "_ADV_BAKED_")) catch ()
        )
        clearSelection()
        select bakeBones
    )
    else
    (
        try
        (
            disableSceneRedraw()
            delete bakeBones
            enableSceneRedraw()
        )
        catch
        (
            try (enableSceneRedraw()) catch ()
        )
        clearSelection()
        try (select oldSelection) catch (try (select rootNode) catch ())
    )

    try (completeRedraw()) catch ()
    exportSucceeded
)

RMTool_ADV_Log ("library loaded " + RMTool_ADV_BackendVersion)
true

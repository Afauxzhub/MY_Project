/* Shared evaluated-scale bake helpers for bone_ctrl / ctrl_bone FBX export. */

global RMTool_HideScale_IsTargetNode
global RMTool_HideScale_CaptureNodes
global RMTool_HideScale_ContextHasNonUnit
global RMTool_HideScale_ApplyToSourceNodes
global RMTool_HideScale_RestoreSourceNodes
global RMTool_HideScale_ApplyToBakeNodes
global RMTool_HideScale_ApplySamplesVerified
global RMTool_HideScale_ApplyToBakeNodesVerified

fn RMTool_HideScale_ScaleAxisDiff a b =
(
    local d = abs (a.x - b.x)
    local d2 = abs (a.y - b.y)
    if d2 > d do d = d2
    d2 = abs (a.z - b.z)
    if d2 > d do d = d2
    d
)

fn RMTool_HideScale_IsTargetNode node =
(
    if node == undefined or not (isValidNode node) do return false
    local nm = try(toLower (node.name as string))catch("")
    (matchPattern nm pattern:"bone_ctrl*") or (matchPattern nm pattern:"ctrl_bone*")
)

fn RMTool_HideScale_InstallBezierController node =
(
    if node == undefined or not (isValidNode node) do return false
    local ok = false
    try(node.scale.controller = bezier_scale(); ok = true)catch()
    if not ok do try(node.scale.controller = Bezier_Scale(); ok = true)catch()
    if not ok do
    (
        local cls = try(classOf node.scale.controller)catch(undefined)
        if cls == bezier_scale or cls == Bezier_Scale do ok = true
    )
    ok
)

fn RMTool_HideScale_CaptureNodes nodes startFrame endFrame =
(
    local context = #()
    if nodes == undefined do return context
    local s = startFrame as integer
    local e = endFrame as integer
    if e < s do throw "HideScaleBake invalid frame range"
    local targets = #()
    for node in nodes do if RMTool_HideScale_IsTargetNode node and (findItem targets node) == 0 do append targets node
    for node in targets do
    (
        local originalController = try(node.scale.controller)catch(undefined)
        if originalController == undefined do throw ("HideScaleBake missing scale controller: " + (node.name as string))
        local samples = #()
        local t
        for t = s to e do at time t
        (
            local sc = try(copy node.scale)catch(undefined)
            if sc == undefined do throw ("HideScaleBake cannot evaluate scale: " + (node.name as string) + " frame=" + (t as string))
            append samples (point3 sc.x sc.y sc.z)
        )
        append context #(node, originalController, samples, (node.name as string), s, e)
    )
    context
)

fn RMTool_HideScale_ContextHasNonUnit context tolerance:0.0001 =
(
    if context == undefined do return false
    for entry in context do for sc in entry[3] do
    (
        if (abs (sc.x - 1.0)) > tolerance or (abs (sc.y - 1.0)) > tolerance or (abs (sc.z - 1.0)) > tolerance do return true
    )
    false
)

fn RMTool_HideScale_ApplySamples node samples startFrame =
(
    if node == undefined or not (isValidNode node) do return false
    if samples == undefined or samples.count == 0 do return false
    if not (RMTool_HideScale_InstallBezierController node) do return false
    try(deleteKeys node.scale.controller #allKeys)catch()
    with animate on
    (
        local i
        for i = 1 to samples.count do at time (startFrame + i - 1) (node.scale = samples[i])
    )
    true
)

fn RMTool_HideScale_ApplyToSourceNodes context =
(
    if context == undefined do return 0
    local applied = 0
    for entry in context do if RMTool_HideScale_ApplySamples entry[1] entry[3] entry[5] do applied += 1
    applied
)

fn RMTool_HideScale_RestoreSourceNodes context =
(
    if context == undefined do return 0
    local restored = 0
    for entry in context do
    (
        try
        (
            if isValidNode entry[1] and entry[2] != undefined do
            (
                entry[1].scale.controller = entry[2]
                restored += 1
            )
        )
        catch()
    )
    restored
)

fn RMTool_HideScale_ApplyToBakeNodes context sourceNodes bakeNodes =
(
    if context == undefined or sourceNodes == undefined or bakeNodes == undefined do return 0
    local applied = 0
    for entry in context do
    (
        local sourceIndex = findItem sourceNodes entry[1]
        if sourceIndex > 0 and sourceIndex <= bakeNodes.count do
        (
            if RMTool_HideScale_ApplySamples bakeNodes[sourceIndex] entry[3] entry[5] do applied += 1
        )
    )
    applied
)

-- Verified variant: writes dense keys at key level, then reads the controller
-- curve back frame by frame. Both write and readback bypass the node .scale
-- property on purpose: on BoneSys chains that property can carry parent-scale
-- accumulation/compensation semantics, while the FBX exporter reads only the
-- keyed local curve. addNewKey + key.value stores exactly that curve; any
-- frame whose readback differs is rewritten once (self-heal).
-- Returns #(ok, maxErr, worstFrame, worstActual, worstExpected, keyCount, ctrlClass).
fn RMTool_HideScale_ApplySamplesVerified node samples startFrame tolerance:0.0001 =
(
    if node == undefined or not (isValidNode node) do return #(false, 999999.0, startFrame, [0,0,0], [0,0,0], -1, "invalidNode")
    if samples == undefined or samples.count == 0 do return #(false, 999999.0, startFrame, [0,0,0], [0,0,0], -1, "noSamples")
    if not (RMTool_HideScale_InstallBezierController node) do return #(false, 999999.0, startFrame, [0,0,0], [0,0,0], -1, "noBezierCtrl")
    local ctrl = try (node.scale.controller) catch (undefined)
    if ctrl == undefined do return #(false, 999999.0, startFrame, [0,0,0], [0,0,0], -1, "noScaleCtrl")
    try (deleteKeys ctrl #allKeys) catch ()
    for i = 1 to samples.count do
    (
        local t = startFrame + i - 1
        try
        (
            local k = addNewKey ctrl t
            if k != undefined do
            (
                k.value = point3 samples[i].x samples[i].y samples[i].z
                try (k.inTangentType = #linear) catch ()
                try (k.outTangentType = #linear) catch ()
            )
        )
        catch ()
    )
    local maxErr = 0.0
    local worstFrame = startFrame
    local worstActual = [1,1,1]
    local worstExpected = [1,1,1]
    for i = 1 to samples.count do
    (
        local t = startFrame + i - 1
        local expected = point3 samples[i].x samples[i].y samples[i].z
        local actual = at time t (try (copy ctrl.value) catch (undefined))
        if actual == undefined do return #(false, 999999.0, t, [0,0,0], expected, (try (numKeys ctrl) catch (-1)), ((try (classOf ctrl) catch (undefined)) as string))
        local err = RMTool_HideScale_ScaleAxisDiff actual expected
        if err > tolerance do
        (
            try
            (
                local k = addNewKey ctrl t
                if k != undefined do k.value = expected
            )
            catch ()
            actual = at time t (try (copy ctrl.value) catch (undefined))
            if actual != undefined then err = RMTool_HideScale_ScaleAxisDiff actual expected
            else err = 999999.0
        )
        if err > maxErr do
        (
            maxErr = err
            worstFrame = t
            worstActual = actual
            worstExpected = expected
        )
    )
    #(maxErr <= tolerance, maxErr, worstFrame, worstActual, worstExpected, (try (numKeys ctrl) catch (-1)), ((try (classOf ctrl) catch (undefined)) as string))
)

-- Batch wrapper over ApplySamplesVerified.
-- Returns #(appliedCount, maxErr, worstNodeName, worstFrame, worstActual, worstExpected, keyCount, ctrlClass).
fn RMTool_HideScale_ApplyToBakeNodesVerified context sourceNodes bakeNodes tolerance:0.0001 =
(
    if context == undefined or sourceNodes == undefined or bakeNodes == undefined do return #(0, 999999.0, "", 0, [0,0,0], [0,0,0], -1, "badArgs")
    local applied = 0
    local maxErr = 0.0
    local worstNodeName = ""
    local worstFrame = 0
    local worstActual = [0,0,0]
    local worstExpected = [0,0,0]
    local worstKeyCount = -1
    local worstCtrlClass = ""
    for entry in context do
    (
        local sourceIndex = findItem sourceNodes entry[1]
        if sourceIndex > 0 and sourceIndex <= bakeNodes.count do
        (
            local r = RMTool_HideScale_ApplySamplesVerified bakeNodes[sourceIndex] entry[3] entry[5] tolerance:tolerance
            if r[1] do applied += 1
            if r[2] > maxErr do
            (
                maxErr = r[2]
                worstNodeName = entry[4]
                worstFrame = r[3]
                worstActual = r[4]
                worstExpected = r[5]
                worstKeyCount = r[6]
                worstCtrlClass = r[7]
            )
        )
    )
    #(applied, maxErr, worstNodeName, worstFrame, worstActual, worstExpected, worstKeyCount, worstCtrlClass)
)

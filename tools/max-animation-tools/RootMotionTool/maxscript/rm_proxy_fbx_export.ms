/*
  Root Motion proxy hierarchy exporter (official publisher).

  The live Biped is evaluation-only.  Root motion is written to ordinary
  temporary bones from rigid sampled world matrices. Authored non-unit scale
  is restored separately after the rigid pose bake. This avoids Biped layers,
  biped.setTransform, inherited scale/shear and IK clamp.

  Load order:
    hide_scale_bake.ms
    adv_fbx_export_v25.ms
    rm_indoor_backend.ms
    rm_proxy_fbx_export.ms
    rm_indoor_backend_baselayer.ms
*/

global RMTool_Proxy_BackendVersion
global RMTool_Proxy_BuildDesiredRootTransforms
global RMTool_Proxy_CreateContext
global RMTool_Proxy_ExportContext
global RMTool_Proxy_CleanupContext
global RMTool_Proxy_ExportDenseWithHideScale
global RMTool_Proxy_CaptureTaskLocalTransformControllers
global RMTool_Proxy_RestoreTaskLocalTransformControllers
global RMTool_Proxy_CollectLiveSkinDependencyNodes
global RMTool_Proxy_FilterCopyableTaskLocalTransformNodes
global RMTool_Proxy_GetAdaptivePositionTolerance
global RMTool_Proxy_GetParentFirstOrder
global RMTool_Proxy_IsDescendantOrSelf
global RMTool_Proxy_IsPoseDomainTarget
global RMTool_Proxy_CollectPoseConstraintDescriptors
global RMTool_Proxy_BuildExternalPoseConstraintData
global RMTool_Proxy_GetNodePoseTranslationInfluence
global RMTool_Proxy_ApplyPoseTranslationInfluences
global RMTool_Proxy_BuildTranslationOnlyPoseTarget
global RMTool_Proxy_CreateRigidBakeBone
global RMTool_Proxy_CapturePreservedScaleNodes
global RMTool_Proxy_EvaluateLocalScale
global RMTool_Proxy_SignedScaleAxis
global RMTool_Proxy_NormalizedWorldAxisError
global RMTool_Proxy_IsWorldTransformSingular
global RMTool_Proxy_ScanAndCleanResidue
global RMTool_Proxy_BuildHierarchyPaths
global RMTool_Proxy_FindDuplicateHierarchyPaths
global RMTool_Proxy_FindDuplicateExportHierarchyPathsForScene
global RMTool_Proxy_RunInPlaceExport
global RMTool_HideScale_ApplyToBakeNodesVerified

RMTool_Proxy_BackendVersion = "V3.30-WallHitTranslationOnlyPoseSample"

fn RMTool_Proxy_Log msg =
(
    try (RMTool_Backend_Log ("[ProxyRoot] " + (msg as string))) catch
    (
        try (format "[RMTool] ProxyRoot %\n" (msg as string)) catch ()
    )
)

-- Export progress window + topmost dialogs. The publish tool Qt window runs
-- with WindowStaysOnTopHint, so native messageBox/queryBox can end up hidden
-- beneath it: the export then looks frozen while it is actually waiting on a
-- dialog nobody can see. Every publish dialog therefore goes through a dotNet
-- MessageBox owned by an invisible TopMost form, and the long export shows a
-- TopMost progress window. Painting uses .Refresh() (synchronous) instead of
-- Application.DoEvents so no user input can re-enter the scene mid-export.
global RMTool_Proxy_ProgressForm
global RMTool_Proxy_ProgressLabel
global RMTool_Proxy_ProgressBar

fn RMTool_Proxy_ProgressHide =
(
    if RMTool_Proxy_ProgressForm != undefined do
    try
    (
        RMTool_Proxy_ProgressForm.Close()
        RMTool_Proxy_ProgressForm.Dispose()
    )
    catch ()
    RMTool_Proxy_ProgressForm = undefined
    RMTool_Proxy_ProgressLabel = undefined
    RMTool_Proxy_ProgressBar = undefined
)

fn RMTool_Proxy_ProgressShow titleText =
(
    RMTool_Proxy_ProgressHide()
    try
    (
        local bgColor = (dotNetClass "System.Drawing.Color").FromArgb 45 45 45
        local textColor = (dotNetClass "System.Drawing.Color").FromArgb 219 226 234
        local hintColor = (dotNetClass "System.Drawing.Color").FromArgb 152 162 179
        local trackColor = (dotNetClass "System.Drawing.Color").FromArgb 30 30 30
        local fillColor = (dotNetClass "System.Drawing.Color").FromArgb 61 138 61
        local form = dotNetObject "System.Windows.Forms.Form"
        form.Text = titleText
        form.TopMost = true
        form.ShowInTaskbar = false
        form.ControlBox = false
        form.FormBorderStyle = (dotNetClass "System.Windows.Forms.FormBorderStyle").FixedToolWindow
        form.StartPosition = (dotNetClass "System.Windows.Forms.FormStartPosition").CenterScreen
        form.Size = dotNetObject "System.Drawing.Size" 440 178
        form.BackColor = bgColor
        form.ForeColor = textColor
        local lbl = dotNetObject "System.Windows.Forms.Label"
        lbl.AutoSize = false
        lbl.Size = dotNetObject "System.Drawing.Size" 404 22
        lbl.Location = dotNetObject "System.Drawing.Point" 12 12
        lbl.Text = "正在准备导出..."
        lbl.ForeColor = textColor
        lbl.BackColor = bgColor
        form.Controls.Add lbl
        local track = dotNetObject "System.Windows.Forms.Panel"
        track.Size = dotNetObject "System.Drawing.Size" 404 12
        track.Location = dotNetObject "System.Drawing.Point" 12 46
        track.BackColor = trackColor
        form.Controls.Add track
        local bar = dotNetObject "System.Windows.Forms.Panel"
        bar.Size = dotNetObject "System.Drawing.Size" 0 12
        bar.Location = dotNetObject "System.Drawing.Point" 0 0
        bar.BackColor = fillColor
        track.Controls.Add bar
        local hint = dotNetObject "System.Windows.Forms.Label"
        hint.AutoSize = false
        hint.Size = dotNetObject "System.Drawing.Size" 404 22
        hint.Location = dotNetObject "System.Drawing.Point" 12 72
        hint.Text = "请勿操作3ds Max，等待发布完成。"
        hint.ForeColor = hintColor
        hint.BackColor = bgColor
        form.Controls.Add hint
        RMTool_Proxy_ProgressForm = form
        RMTool_Proxy_ProgressLabel = lbl
        RMTool_Proxy_ProgressBar = bar
        form.Show()
        form.Refresh()
    )
    catch ()
)

fn RMTool_Proxy_ProgressUpdate fraction stageText =
(
    if RMTool_Proxy_ProgressForm == undefined do return false
    try
    (
        if stageText != undefined do
        (
            RMTool_Proxy_ProgressLabel.Text = stageText
            RMTool_Proxy_ProgressLabel.Refresh()
        )
        if fraction != undefined do
        (
            local f = fraction as float
            if f < 0.0 do f = 0.0
            if f > 1.0 do f = 1.0
            RMTool_Proxy_ProgressBar.Width = (f * 404.0) as integer
            RMTool_Proxy_ProgressBar.Refresh()
        )
    )
    catch ()
    true
)

fn RMTool_Proxy_TopMostQuery text caption =
(
    -- Yes/No dialog that can never hide behind the topmost publish window.
    -- Falls back to the native queryBox if dotNet is unavailable.
    local result = false
    local shown = false
    try
    (
        local owner = dotNetObject "System.Windows.Forms.Form"
        owner.TopMost = true
        owner.ShowInTaskbar = false
        owner.FormBorderStyle = (dotNetClass "System.Windows.Forms.FormBorderStyle").None
        owner.StartPosition = (dotNetClass "System.Windows.Forms.FormStartPosition").CenterScreen
        owner.Size = dotNetObject "System.Drawing.Size" 0 0
        owner.Show()
        owner.Activate()
        local dlgResult = (dotNetClass "System.Windows.Forms.MessageBox").Show owner text caption (dotNetClass "System.Windows.Forms.MessageBoxButtons").YesNo (dotNetClass "System.Windows.Forms.MessageBoxIcon").Warning (dotNetClass "System.Windows.Forms.MessageBoxDefaultButton").Button2
        result = (dlgResult == (dotNetClass "System.Windows.Forms.DialogResult").Yes)
        shown = true
        try (owner.Close()) catch ()
        try (owner.Dispose()) catch ()
    )
    catch ()
    if not shown do result = queryBox text title:caption beep:true
    result
)

-- Self-healing cleanup for crash residue left by aborted publishes: leftover
-- temp bake bones (__OP_RM_PROXY__* / __ADV_BAKE__*) are deleted, and source
-- nodes still carrying the temporary rename suffix (__OPProxySource_* /
-- __OPAdvExport_*) get their original names back. Max permits duplicate node
-- names, so residue recovery must restore every duplicate. Collection and
-- rename are separate passes because mutating names while iterating `objects`
-- can invalidate Max's live collection iterator.
-- Called at the start of every publish so a crashed run can never poison the
-- next one. Returns #(deletedTempBones, restoredNames).
fn RMTool_Proxy_ScanAndCleanResidue =
(
    local deletedTempBones = 0
    local restoredNames = 0
    local leftoverBones = #()
    local renameNodes = #()
    local renameOriginalNames = #()
    for n in objects do
    (
        if isValidNode n do
        (
            local nm = n.name as string
            if (matchPattern nm pattern:"__OP_RM_PROXY__*") or (matchPattern nm pattern:"__ADV_BAKE__*") do append leftoverBones n
        )
    )
    for n in leftoverBones do
    (
        try ( if isValidNode n do (delete n; deletedTempBones += 1) ) catch ()
    )
    for n in objects do
    (
        if isValidNode n do
        (
            local nm = n.name as string
            local suffixIndex = findString nm "__OPProxySource_"
            if suffixIndex == undefined do suffixIndex = findString nm "__OPAdvExport_"
            if suffixIndex != undefined and suffixIndex > 1 do
            (
                append renameNodes n
                append renameOriginalNames (substring nm 1 (suffixIndex - 1))
            )
        )
    )
    for i = 1 to renameNodes.count do try ( if isValidNode renameNodes[i] do (renameNodes[i].name = renameOriginalNames[i]; restoredNames += 1) ) catch ()
    if deletedTempBones > 0 or restoredNames > 0 do
        RMTool_Proxy_Log ("crash residue cleaned: deletedTempBones=" + (deletedTempBones as string) + " restoredNames=" + (restoredNames as string))
    #(deletedTempBones, restoredNames)
)

fn RMTool_Proxy_ScaleAxisError a b =
(
    local dx = abs (a.x - b.x)
    local dy = abs (a.y - b.y)
    local dz = abs (a.z - b.z)
    local result = dx
    if dy > result do result = dy
    if dz > result do result = dz
    result
)

fn RMTool_Proxy_NormalizedWorldAxisError tmA tmB =
(
    local e1 = distance (normalize tmA.row1) (normalize tmB.row1)
    local e2 = distance (normalize tmA.row2) (normalize tmB.row2)
    local e3 = distance (normalize tmA.row3) (normalize tmB.row3)
    RMTool_ADV_Max2 e1 (RMTool_ADV_Max2 e2 e3)
)

fn RMTool_Proxy_SignedScaleAxis magnitude rawAxis =
(
    local factor = try (RMTool_Backend_AsScaleFactor magnitude) catch
    (
        if (abs magnitude) > 100.0 then (magnitude / 1000.0)
        else if (abs magnitude) > 10.0 then (magnitude / 100.0)
        else magnitude
    )
    if rawAxis != undefined and rawAxis < 0.0 then -factor
    else if rawAxis != undefined and (abs rawAxis) < 0.00000001 then 0.0
    else factor
)

fn RMTool_Proxy_EvaluateLocalScale node exportParentNode:undefined =
(
    if node == undefined or not (isValidNode node) do return undefined
    local rawScale = undefined
    local scaleCtrl = try (node.scale.controller) catch (undefined)
    if scaleCtrl != undefined do
    (
        local ctrlValue = try (copy scaleCtrl.value) catch (undefined)
        if ctrlValue != undefined and (classOf ctrlValue) == point3 do rawScale = point3 ctrlValue.x ctrlValue.y ctrlValue.z
    )

    -- Capture the authored source Scale controller exactly. The proxy first
    -- receives these samples so ordinary scale and singular visibility frames
    -- are retained; the later full-world reconciliation converts Max-only
    -- no-inherit chains into portable FBX-local Scale keys.
    if rawScale != undefined do return rawScale

    -- Controllerless helpers fall back to their evaluated parent-relative
    -- matrix. This path retains static non-unit scale without forcing a missing
    -- controller error.
    local nodeTM = try (copy node.transform) catch (undefined)
    local parentNode = exportParentNode
    if parentNode == undefined do parentNode = try (node.parent) catch (undefined)
    local exportLocalTM = nodeTM
    if nodeTM != undefined and parentNode != undefined and isValidNode parentNode do exportLocalTM = try (nodeTM * (inverse parentNode.transform)) catch (undefined)
    if exportLocalTM != undefined do
    (
        local exportScaleX = RMTool_Proxy_SignedScaleAxis (length exportLocalTM.row1) undefined
        local exportScaleY = RMTool_Proxy_SignedScaleAxis (length exportLocalTM.row2) undefined
        local exportScaleZ = RMTool_Proxy_SignedScaleAxis (length exportLocalTM.row3) undefined
        return point3 exportScaleX exportScaleY exportScaleZ
    )

    local directScale = try (copy node.scale) catch (undefined)
    if directScale != undefined do return (point3 directScale.x directScale.y directScale.z)
    if nodeTM == undefined do return undefined
    local localTM = nodeTM
    if parentNode != undefined and isValidNode parentNode do localTM = try (nodeTM * (inverse parentNode.transform)) catch (undefined)
    if localTM == undefined do return undefined
    point3 (length localTM.row1) (length localTM.row2) (length localTM.row3)
)

-- Scan every non-Root/Bip source in frame-major order so Biped is evaluated
-- once per frame instead of once per node per frame. Only numerically unit
-- tracks are omitted; any real non-unit value (0.98, 1.3, visibility, stretch)
-- is retained and densely written to the proxy. unitEpsilon is numerical-noise
-- suppression, not an animation-scale threshold.
fn RMTool_Proxy_CapturePreservedScaleNodes nodes startFrame endFrame excludedNodes:#() unitEpsilon:0.00001 scanStats:undefined includeKeyedUnitTracks:false parentIndices:undefined =
(
    local context = #()
    if nodes == undefined do return context
    local s = startFrame as integer
    local e = endFrame as integer
    if e < s do throw "ProxyRoot preserved-scale invalid frame range"
    local captureNodes = #()
    local originalControllers = #()
    local captureParentNodes = #()
    local sampleSets = #()
    local activeFlags = #()
    local keyedFlags = #()
    local denseFlags = #()
    local boneStretchFlags = #()
    local controllerlessCount = 0
    for nodeIndex = 1 to nodes.count do
    (
        local node = nodes[nodeIndex]
        if node != undefined and isValidNode node and (findItem captureNodes node) == 0 and (findItem excludedNodes node) == 0 do
        (
            local originalController = try (node.scale.controller) catch (undefined)
            local usesBoneStretch = try (node.boneEnable == true) catch (false)
            local exportParentNode = try (node.parent) catch (undefined)
            if parentIndices != undefined and nodeIndex <= parentIndices.count do
            (
                local exportParentIndex = parentIndices[nodeIndex]
                if exportParentIndex > 0 and exportParentIndex <= nodes.count do exportParentNode = nodes[exportParentIndex]
            )
            if originalController == undefined do controllerlessCount += 1
            append captureNodes node
            append originalControllers originalController
            append captureParentNodes exportParentNode
            append sampleSets (#())
            append activeFlags false
            append keyedFlags ((try (numKeys originalController) catch (0)) > 0)
            append denseFlags ((originalController != undefined) or usesBoneStretch)
            append boneStretchFlags usesBoneStretch
        )
    )
    local unitScale = [1,1,1]
    -- A controllerless Biped child has no authored local Scale track. Reading
    -- node.scale across every frame nevertheless forces an expensive full
    -- Biped evaluation (over 100 seconds for ~70 nodes in MarineA_Break).
    -- Screen these nodes once at the range start: unit values need no exported
    -- local curve; a real static/non-unit value is promoted to the exact dense
    -- path below. Nodes with a Scale controller always remain densely sampled.
    at time s
    (
        for i = 1 to captureNodes.count where not denseFlags[i] do
        (
            local startScale = RMTool_Proxy_EvaluateLocalScale captureNodes[i] exportParentNode:captureParentNodes[i]
            if startScale == undefined do throw ("ProxyRoot cannot evaluate controllerless scale: " + (captureNodes[i].name as string) + " frame=" + (s as string))
            if (RMTool_Proxy_ScaleAxisError startScale unitScale) > unitEpsilon do (denseFlags[i] = true; activeFlags[i] = true)
        )
    )
    local t
    for t = s to e do at time t
    (
        for i = 1 to captureNodes.count where denseFlags[i] do
        (
            local sc = RMTool_Proxy_EvaluateLocalScale captureNodes[i] exportParentNode:captureParentNodes[i]
            if sc == undefined do throw ("ProxyRoot cannot evaluate preserved scale: " + (captureNodes[i].name as string) + " frame=" + (t as string))
            local sample = point3 sc.x sc.y sc.z
            append sampleSets[i] sample
            if (RMTool_Proxy_ScaleAxisError sample unitScale) > unitEpsilon do activeFlags[i] = true
        )
    )
    for i = 1 to captureNodes.count do if activeFlags[i] or (includeKeyedUnitTracks and keyedFlags[i]) do append context #(captureNodes[i], originalControllers[i], sampleSets[i], (captureNodes[i].name as string), s, e)
    if scanStats != undefined do
    (
        while scanStats.count > 0 do deleteItem scanStats scanStats.count
        append scanStats captureNodes.count
        append scanStats context.count
        append scanStats controllerlessCount
    )
    context
)

fn RMTool_Proxy_CopyTM tm =
(
    if tm == undefined then undefined else copy tm
)

fn RMTool_Proxy_UnwrapEulerAngle value reference =
(
    local result = value
    while (result - reference) > 180.0 do result -= 360.0
    while (result - reference) < -180.0 do result += 360.0
    result
)

fn RMTool_Proxy_NormalizeEulerAngle value =
(
    local result = value
    while result > 180.0 do result -= 360.0
    while result < -180.0 do result += 360.0
    result
)

-- A usable rigid Local target must be orthonormal, not merely have unit-length
-- rows and a non-zero determinant. Exact-zero Scale Wire nodes can produce
-- tiny cross-product noise; normalizing that noise yields an arbitrary axis
-- and determinants such as 0.838, which the old >0.5 test accepted as a valid
-- rotation reference. Reject shear/non-orthogonality so hidden nodes hold a
-- real neighbouring rotation (or identity when hidden for the whole clip).
fn RMTool_Proxy_IsValidRigidRotationTM tm =
(
    if tm == undefined do return false
    if (length tm.row1) <= 0.5 or (length tm.row2) <= 0.5 or (length tm.row3) <= 0.5 do return false
    local r1 = normalize tm.row1
    local r2 = normalize tm.row2
    local r3 = normalize tm.row3
    local det = RMTool_ADV_MatrixDet3 tm
    if (abs (det - 1.0)) > 0.01 do return false
    if (abs (dot r1 r2)) > 0.01 or (abs (dot r1 r3)) > 0.01 or (abs (dot r2 r3)) > 0.01 do return false
    true
)

-- Scale magnitude and matrix invertibility are different contracts. Authored
-- 0.01/0.001 scale remains mathematically reversible and must still participate
-- in the portable FBX world-TM reconciliation. Only an actually collapsed axis
-- (or a collapsed normalized basis) is singular. Keep this predicate shared by
-- source-rotation capture, scale reconciliation and final validation so those
-- stages cannot disagree at a threshold boundary.
fn RMTool_Proxy_IsWorldTransformSingular tm axisEpsilon:0.000001 basisEpsilon:0.000001 =
(
    if tm == undefined do return true
    local row1Length = length tm.row1
    local row2Length = length tm.row2
    local row3Length = length tm.row3
    if row1Length <= axisEpsilon or row2Length <= axisEpsilon or row3Length <= axisEpsilon do return true
    local r1 = normalize tm.row1
    local r2 = normalize tm.row2
    local r3 = normalize tm.row3
    (abs (dot r1 (cross r2 r3))) <= basisEpsilon
)

-- Inspect the unstripped source world matrix before TMNoScale can amplify
-- floating-point noise from a truly singular matrix into a seemingly valid
-- unit axis. Small but invertible authored scale retains its real rotation.
fn RMTool_Proxy_IsSourceRotationDefined tm =
(
    not (RMTool_Proxy_IsWorldTransformSingular tm)
)

fn RMTool_Proxy_CreateRigidBakeBone tempName displayLength =
(
    local bn = BoneSys.createBone [0,0,0] [1,0,0] [0,0,1]
    bn.name = tempName
    -- A live Max Bone stretch transform can skew the evaluated world axes even
    -- when the keyed PRS is rigid. Export it as geometry-as-bone instead, as the
    -- established ADV path does. FBX must receive continuous Euler tracks rather
    -- than re-solving TCB quaternion keys independently at Euler singularities.
    local noStretchOK = try (bn.boneEnable = false; bn.boneEnable == false) catch (false)
    try (bn.boneAutoAlign = false) catch ()
    try (bn.boneFreezeLength = false) catch ()
    try (bn.boneScaleType = #scale) catch ()
    local eulerControllerOK = try (bn.rotation.controller = Euler_XYZ(); (classOf bn.rotation.controller) == Euler_XYZ) catch (false)
    try (bn.scale.controller = bezier_scale()) catch ()
    try (bn.length = displayLength) catch ()
    try (bn.width = displayLength * 0.12) catch ()
    try (bn.height = displayLength * 0.12) catch ()
    try (bn.renderable = false) catch ()
    try (bn.wireColor = (color 0 200 255)) catch ()
    if not noStretchOK or not eulerControllerOK do
    (
        try (delete bn) catch ()
        throw ("ProxyRoot cannot create no-stretch Euler bake bone. noStretch=" + (noStretchOK as string) + " eulerController=" + (eulerControllerOK as string))
    )
    bn
)

fn RMTool_Proxy_GetParentFirstOrder parentIndices =
(
    local result = #()
    local depths = #()
    for i = 1 to parentIndices.count do
    (
        local depth = 0
        local parentIndex = parentIndices[i]
        while parentIndex > 0 and depth <= parentIndices.count do
        (
            depth += 1
            parentIndex = parentIndices[parentIndex]
        )
        append depths depth
        append result i
    )
    if result.count > 1 do
    (
        for a = 1 to (result.count - 1) do
        (
            for b = 1 to (result.count - a) do
            (
                if depths[result[b]] > depths[result[b + 1]] do
                (
                    local swapIndex = result[b]
                    result[b] = result[b + 1]
                    result[b + 1] = swapIndex
                )
            )
        )
    )
    result
)

fn RMTool_Proxy_GetAdaptivePositionTolerance nodeIndex parentIndices worldTMs worldAxisErrors minimumTolerance absoluteCap propagationFactor =
(
    local propagatedTolerance = 0.0
    local currentIndex = nodeIndex
    local guard = 0
    while currentIndex > 0 and currentIndex <= parentIndices.count and parentIndices[currentIndex] > 0 and guard < parentIndices.count do
    (
        local parentIndex = parentIndices[currentIndex]
        local linkLength = distance worldTMs[currentIndex].pos worldTMs[parentIndex].pos
        local parentAxisError = if parentIndex <= worldAxisErrors.count then worldAxisErrors[parentIndex] else 0.0
        propagatedTolerance += linkLength * ((parentAxisError * propagationFactor) + 0.000001)
        currentIndex = parentIndex
        guard += 1
    )
    local result = if propagatedTolerance > minimumTolerance then propagatedTolerance else minimumTolerance
    if result > absoluteCap do result = absoluteCap
    result
)

fn RMTool_Proxy_IsDescendantOrSelf node ancestor =
(
    if node == undefined or ancestor == undefined do return false
    local current = node
    while current != undefined do
    (
        if current == ancestor do return true
        current = current.parent
    )
    false
)

fn RMTool_Proxy_OffsetTM tm offset =
(
    local result = copy tm
    result.pos = result.pos + offset
    result
)

fn RMTool_Proxy_IsPoseDomainTarget targetNode bodyRoots =
(
    if targetNode == undefined do return false
    local targetValid = try (isValidNode targetNode) catch (false)
    if not targetValid do return false
    for bodyRoot in bodyRoots where bodyRoot != undefined and (try (isValidNode bodyRoot) catch (false)) do
    (
        if RMTool_Proxy_IsDescendantOrSelf targetNode bodyRoot do return true
    )
    false
)

fn RMTool_Proxy_GetConstraintTarget ctrl targetIndex =
(
    local targetNode = try (ctrl.getNode targetIndex) catch (undefined)
    if targetNode == undefined do targetNode = try (ctrl.getTarget targetIndex) catch (undefined)
    targetNode
)

-- descriptor = #(positionConstraints, lookAtConstraints, unsupportedPositionConstraints, labels)
-- Each supported constraint entry is #(kind, controller, nestedInList).
-- Multi-target Link/Position controllers are evaluated at every dense sample.
-- Multiple stacked position constraints are deliberately rejected: silently
-- guessing List-controller blend weights would recreate the weapon drift this
-- compensation is intended to prevent.
fn RMTool_Proxy_CollectPoseConstraintDescriptors ctrl descriptor visited channelHint depth nestedInList bodyRoots sourceNodes =
(
    if ctrl == undefined or depth > 8 do return false
    if (findItem visited ctrl) > 0 do return true
    append visited ctrl

    local classText = toLower ((try ((classOf ctrl) as string) catch ("")))
    local isListController = (findString classText "_list" != undefined) or (findString classText "list_controller" != undefined)
    local isLink = findString classText "link_constraint" != undefined
    local isPosition = findString classText "position_constraint" != undefined
    local isOrientation = findString classText "orientation_constraint" != undefined
    local isLookAt = findString classText "lookat_constraint" != undefined
    local targetCount = try (ctrl.getNumTargets()) catch (0)

    if isLink or isPosition or isLookAt do
    (
        local kind = if isLink then "link" else if isPosition then "position" else "lookat"
        local entry = #(kind, ctrl, nestedInList)
        if isLookAt then append descriptor[2] entry else append descriptor[1] entry
        local targetLabels = #()
        for targetIndex = 1 to targetCount do
        (
            local targetNode = RMTool_Proxy_GetConstraintTarget ctrl targetIndex
            append targetLabels (if targetNode != undefined and (try (isValidNode targetNode) catch (false)) then (targetNode.name as string) else "World")
        )
        append descriptor[4] (((try ((classOf ctrl) as string) catch ("Constraint"))) + "[" + (RMTool_ADV_JoinStrings targetLabels ",") + "]")
        return true
    )

    if targetCount > 0 and (channelHint == 1 or channelHint == 3) and not isOrientation do
    (
        local poseRelevant = false
        for targetIndex = 1 to targetCount while not poseRelevant do
        (
            local targetNode = RMTool_Proxy_GetConstraintTarget ctrl targetIndex
            local targetSourceIndex = if targetNode != undefined then (findItem sourceNodes targetNode) else 0
            if RMTool_Proxy_IsPoseDomainTarget targetNode bodyRoots or targetSourceIndex > 1 do poseRelevant = true
        )
        if poseRelevant do
        (
            append descriptor[3] ctrl
            append descriptor[4] ((try ((classOf ctrl) as string) catch ("UnsupportedConstraint")))
        )
        return true
    )

    -- PRS exposes its Position/Rotation controllers as sub-anims; the caller
    -- inspects those channels directly, so recursing through PRS would duplicate
    -- the same constraint. List wrappers are traversed and explicitly tagged.
    if classText != "prs" do
    (
        local subCount = try (numSubs ctrl) catch (0)
        for subIndex = 1 to subCount do
        (
            local subAnimValue = try (getSubAnim ctrl subIndex) catch (undefined)
            local subCtrl = try (subAnimValue.controller) catch (undefined)
            if subCtrl != undefined do RMTool_Proxy_CollectPoseConstraintDescriptors subCtrl descriptor visited channelHint (depth + 1) (nestedInList or isListController) bodyRoots sourceNodes
        )
    )
    true
)

fn RMTool_Proxy_BuildExternalPoseConstraintData sourceNodes poseBranchRoot bipObj poseMayDiffer =
(
    local bodyRoots = #()
    if bipObj != undefined and (try (isValidNode bipObj) catch (false)) do append bodyRoots bipObj
    if poseBranchRoot != undefined and (try (isValidNode poseBranchRoot) catch (false)) and (findItem bodyRoots poseBranchRoot) == 0 do append bodyRoots poseBranchRoot

    local descriptors = #()
    local constrainedLabels = #()
    for node in sourceNodes do
    (
        local descriptor = #(#(), #(), #(), #())
        if node != undefined and (try (isValidNode node) catch (false)) and not (RMTool_Proxy_IsDescendantOrSelf node poseBranchRoot) do
        (
            local visited = #()
            RMTool_Proxy_CollectPoseConstraintDescriptors node.transform.controller descriptor visited 3 0 false bodyRoots sourceNodes
            RMTool_Proxy_CollectPoseConstraintDescriptors node.position.controller descriptor visited 1 0 false bodyRoots sourceNodes
            RMTool_Proxy_CollectPoseConstraintDescriptors node.rotation.controller descriptor visited 2 0 false bodyRoots sourceNodes
            if descriptor[1].count > 0 or descriptor[2].count > 0 or descriptor[3].count > 0 do append constrainedLabels (node.name as string)
            if poseMayDiffer do
            (
                if descriptor[3].count > 0 do throw ("ProxyRoot unsupported position constraint. node=" + (node.name as string) + " controllers=" + (RMTool_ADV_JoinStrings descriptor[4] "; ")) debugBreak:false
                if descriptor[1].count > 1 do throw ("ProxyRoot stacked position constraints are ambiguous. node=" + (node.name as string) + " controllers=" + (RMTool_ADV_JoinStrings descriptor[4] "; ")) debugBreak:false
                if descriptor[1].count == 1 and descriptor[1][1][3] do throw ("ProxyRoot position constraint inside List controller requires explicit blend support. node=" + (node.name as string) + " controller=" + descriptor[4][1]) debugBreak:false
            )
        )
        append descriptors descriptor
    )
    #(descriptors, bodyRoots, constrainedLabels)
)

fn RMTool_Proxy_GetTargetPoseTranslationInfluence targetNode sourceNodes parentIndices poseBranchRoot bodyRoots descriptors sampleFrame cache visiting =
(
    if targetNode == undefined do return 0.0 -- Link-to-World does not follow COM.
    if not (try (isValidNode targetNode) catch (false)) do return 0.0
    if RMTool_Proxy_IsPoseDomainTarget targetNode bodyRoots do return 1.0
    local targetIndex = findItem sourceNodes targetNode
    if targetIndex > 0 do return (RMTool_Proxy_GetNodePoseTranslationInfluence targetIndex sourceNodes parentIndices poseBranchRoot bodyRoots descriptors sampleFrame cache visiting)
    0.0
)

fn RMTool_Proxy_GetNodePoseTranslationInfluence nodeIndex sourceNodes parentIndices poseBranchRoot bodyRoots descriptors sampleFrame cache visiting =
(
    if nodeIndex <= 0 or nodeIndex > sourceNodes.count do return 0.0
    if cache[nodeIndex] != undefined do return cache[nodeIndex]
    if visiting[nodeIndex] do throw ("ProxyRoot constraint dependency cycle. node=" + (sourceNodes[nodeIndex].name as string) + " frame=" + (sampleFrame as string)) debugBreak:false
    visiting[nodeIndex] = true

    local node = sourceNodes[nodeIndex]
    local result = 0.0
    if RMTool_Proxy_IsDescendantOrSelf node poseBranchRoot then
        result = 1.0
    else if nodeIndex == 1 then
        result = 0.0
    else
    (
        local parentIndex = parentIndices[nodeIndex]
        local parentInfluence = if parentIndex > 0 then (RMTool_Proxy_GetNodePoseTranslationInfluence parentIndex sourceNodes parentIndices poseBranchRoot bodyRoots descriptors sampleFrame cache visiting) else 0.0
        local positionConstraints = descriptors[nodeIndex][1]
        if positionConstraints.count == 0 then
            result = parentInfluence
        else
        (
            local entry = positionConstraints[1]
            local kind = entry[1]
            local ctrl = entry[2]
            local targetCount = try (ctrl.getNumTargets()) catch (0)
            if kind == "link" then
            (
                local activeFound = false
                local activeTarget = undefined
                local activeFrame = -1.0e20
                for targetIndex = 1 to targetCount do
                (
                    local linkFrame = try ((ctrl.getFrameNo targetIndex) as float) catch ((targetIndex - 1) as float)
                    if linkFrame <= sampleFrame and (not activeFound or linkFrame >= activeFrame) do
                    (
                        activeFound = true
                        activeFrame = linkFrame
                        activeTarget = RMTool_Proxy_GetConstraintTarget ctrl targetIndex
                    )
                )
                -- Before the first scheduled Link target, Max evaluates the
                -- controller in World space rather than under the first target.
                result = if activeFound then (RMTool_Proxy_GetTargetPoseTranslationInfluence activeTarget sourceNodes parentIndices poseBranchRoot bodyRoots descriptors sampleFrame cache visiting) else 0.0
            )
            else if kind == "position" then
            (
                local totalWeight = 0.0
                local weightedInfluence = 0.0
                for targetIndex = 1 to targetCount do
                (
                    local targetWeight = try ((ctrl.getWeight targetIndex) as float) catch (100.0)
                    if targetWeight > 0.000001 do
                    (
                        local targetNode = RMTool_Proxy_GetConstraintTarget ctrl targetIndex
                        local targetInfluence = RMTool_Proxy_GetTargetPoseTranslationInfluence targetNode sourceNodes parentIndices poseBranchRoot bodyRoots descriptors sampleFrame cache visiting
                        totalWeight += targetWeight
                        weightedInfluence += targetWeight * targetInfluence
                    )
                )
                result = if totalWeight > 0.000001 then (weightedInfluence / totalWeight) else parentInfluence
            )
        )
    )

    if result < 0.0 do result = 0.0
    if result > 1.0 do result = 1.0
    cache[nodeIndex] = result
    visiting[nodeIndex] = false
    result
)

fn RMTool_Proxy_ApplyPoseTranslationInfluences sourceWorldTMs targetWorldTMs sourceBipTM targetBipTM sourceNodes parentIndices poseBranchRoot bodyRoots descriptors sampleFrame =
(
    local poseAxisError = RMTool_ADV_MatrixAxisError sourceBipTM targetBipTM
    local poseOffset = targetBipTM.pos - sourceBipTM.pos
    local poseOffsetLength = length poseOffset
    if poseAxisError > 0.00001 do
    (
        for nodeIndex = 1 to sourceNodes.count where not (RMTool_Proxy_IsDescendantOrSelf sourceNodes[nodeIndex] poseBranchRoot) do
        (
            if descriptors[nodeIndex][1].count > 0 or descriptors[nodeIndex][2].count > 0 do
                throw ("ProxyRoot external constraint compensation supports translation-only body pose deltas. node=" + (sourceNodes[nodeIndex].name as string) + " frame=" + (sampleFrame as string) + " axisErr=" + (poseAxisError as string)) debugBreak:false
        )
        return targetWorldTMs
    )
    if poseOffsetLength <= 0.000001 do return targetWorldTMs

    local cache = for node in sourceNodes collect undefined
    local visiting = for node in sourceNodes collect false
    for nodeIndex = 1 to sourceNodes.count do
    (
        local influence = RMTool_Proxy_GetNodePoseTranslationInfluence nodeIndex sourceNodes parentIndices poseBranchRoot bodyRoots descriptors sampleFrame cache visiting
        if not (RMTool_Proxy_IsDescendantOrSelf sourceNodes[nodeIndex] poseBranchRoot) and influence > 0.000001 do
        (
            local adjustedTM = copy targetWorldTMs[nodeIndex]
            adjustedTM.pos = sourceWorldTMs[nodeIndex].pos + (poseOffset * influence)
            targetWorldTMs[nodeIndex] = adjustedTM
        )
    )

    -- A LookAt source rotation stays valid only when owner and every effective
    -- target translate by the same amount. Mixed influences change the aim
    -- vector and require a dedicated rotational reconstruction, so fail loudly.
    for nodeIndex = 1 to sourceNodes.count where descriptors[nodeIndex][2].count > 0 do
    (
        local ownerInfluence = cache[nodeIndex]
        for entry in descriptors[nodeIndex][2] do
        (
            local ctrl = entry[2]
            local targetCount = try (ctrl.getNumTargets()) catch (0)
            for targetIndex = 1 to targetCount do
            (
                local targetWeight = try ((ctrl.getWeight targetIndex) as float) catch (100.0)
                if targetWeight > 0.000001 do
                (
                    local targetNode = RMTool_Proxy_GetConstraintTarget ctrl targetIndex
                    local targetInfluence = RMTool_Proxy_GetTargetPoseTranslationInfluence targetNode sourceNodes parentIndices poseBranchRoot bodyRoots descriptors sampleFrame cache visiting
                    if (abs (targetInfluence - ownerInfluence)) > 0.00001 do throw ("ProxyRoot LookAt target has different body translation influence. node=" + (sourceNodes[nodeIndex].name as string) + " frame=" + (sampleFrame as string)) debugBreak:false
                )
            )
        )
    )
    targetWorldTMs
)

fn RMTool_Proxy_InterpolateTM tmA tmB alpha =
(
    if alpha <= 0.0 do return (copy tmA)
    if alpha >= 1.0 do return (copy tmB)
    local posA = tmA.pos
    local posB = tmB.pos
    local scaleA = [length tmA.row1, length tmA.row2, length tmA.row3]
    local scaleB = [length tmB.row1, length tmB.row2, length tmB.row3]
    local interpPos = posA + ((posB - posA) * alpha)
    local interpScale = scaleA + ((scaleB - scaleA) * alpha)
    local quatA = tmA.rotation
    local quatB = tmB.rotation
    local quatDot = (quatA.x * quatB.x) + (quatA.y * quatB.y) + (quatA.z * quatB.z) + (quatA.w * quatB.w)
    if quatDot < 0.0 do quatB = -quatB
    local interpRot = slerp quatA quatB alpha
    local result = interpRot as matrix3
    result.row1 *= interpScale.x
    result.row2 *= interpScale.y
    result.row3 *= interpScale.z
    result.pos = interpPos
    result
)

fn RMTool_Proxy_SampleTMArray transforms totalStartF sampleFrame =
(
    if transforms == undefined or transforms.count == 0 do return undefined
    local relativeFrame = (sampleFrame as float) - totalStartF
    local lowerOffset = floor relativeFrame
    local lowerIndex = (lowerOffset as integer) + 1
    if lowerIndex < 1 do lowerIndex = 1
    if lowerIndex >= transforms.count do return (copy transforms[transforms.count])
    local alpha = relativeFrame - lowerOffset
    RMTool_Proxy_InterpolateTM transforms[lowerIndex] transforms[lowerIndex + 1] alpha
)

-- WallHit changes only the Biped/COM trajectory position.  Sampling the full
-- integer-frame target matrices with generic quaternion slerp can disagree with
-- Biped's native sub-frame interpolation and manufacture a rotational delta at
-- 0.5/0.25 frames.  Keep the exact live source axes/scale for this sample and
-- take only the adjusted WallHit position from the target trajectory.
fn RMTool_Proxy_BuildTranslationOnlyPoseTarget sourceBipTM poseBipTransforms totalStartF sampleFrame =
(
    if sourceBipTM == undefined do throw ("ProxyRoot translation-only pose source Bip TM missing at frame " + (sampleFrame as string)) debugBreak:false
    local sampledPoseTM = RMTool_Proxy_SampleTMArray poseBipTransforms totalStartF sampleFrame
    if sampledPoseTM == undefined do throw ("ProxyRoot translation-only pose target Bip TM missing at frame " + (sampleFrame as string)) debugBreak:false
    local targetBipTM = copy sourceBipTM
    targetBipTM.pos = sampledPoseTM.pos
    targetBipTM
)

fn RMTool_Proxy_TrimAxisControllerKeys axisController startF endF =
(
    if axisController == undefined do return 0
    local removedCount = 0
    local keyCount = try (numKeys axisController) catch (0)
    for keyIndex = keyCount to 1 by -1 do
    (
        local keyTime = try ((getKey axisController keyIndex).time) catch (undefined)
        if keyTime == undefined or keyTime < startF or keyTime > endF do
        (
            deleteKey axisController keyIndex
            removedCount += 1
        )
    )
    removedCount
)

fn RMTool_Proxy_CollectLiveSkinDependencyNodes morphMeshes excludedNodes:#() =
(
    -- A selected live Morpher mesh may also carry Skin. FBX selected-only export
    -- then pulls the Skin bones and their parent chain into the file even though
    -- those source nodes were not selected. With BakeAnimation=false their full
    -- native controllers would leak outside a split Take, so return the complete
    -- live Skin hierarchy for task-local PRS isolation.
    local result = #()
    local skinModifierCount = 0
    local skinBoneCount = 0
    if morphMeshes == undefined do morphMeshes = #()
    if excludedNodes == undefined do excludedNodes = #()
    for morphMesh in morphMeshes where morphMesh != undefined and isValidNode morphMesh do
    (
        local modifierCount = try (morphMesh.modifiers.count) catch (0)
        for modifierIndex = 1 to modifierCount do
        (
            local skinModifier = try (morphMesh.modifiers[modifierIndex]) catch (undefined)
            local isSkinModifier = try ((classOf skinModifier) == Skin) catch (false)
            if isSkinModifier do
            (
                skinModifierCount += 1
                local skinBones = try (skinOps.GetBoneNodes skinModifier) catch (#())
                if skinBones == undefined do skinBones = #()
                skinBoneCount += skinBones.count
                for skinBone in skinBones where skinBone != undefined and isValidNode skinBone do
                (
                    local current = skinBone
                    while current != undefined and isValidNode current do
                    (
                        if (findItem excludedNodes current) == 0 and (findItem result current) == 0 do append result current
                        current = try (current.parent) catch (undefined)
                    )
                )
            )
        )
    )
    if skinModifierCount > 0 do
        RMTool_Proxy_Log ("task-local live Skin dependencies modifiers=" + (skinModifierCount as string) + " bones=" + (skinBoneCount as string) + " hierarchyNodes=" + (result.count as string))
    result
)

fn RMTool_Proxy_FilterCopyableTaskLocalTransformNodes nodes =
(
    -- Ordinary Bone/Helper PRS controllers can be copied and trimmed safely.
    -- Biped/List/custom controllers that cannot expose XYZ copies are left live;
    -- the post-FBX curve gate remains authoritative and will block any leak.
    local result = #()
    local skippedNames = #()
    if nodes == undefined do return result
    for node in nodes where node != undefined and isValidNode node do
    (
        local originalPositionController = try (node.position.controller) catch (undefined)
        local originalRotationController = try (node.rotation.controller) catch (undefined)
        local originalScaleController = try (node.scale.controller) catch (undefined)
        local taskPositionController = try (copy originalPositionController) catch (undefined)
        local taskRotationController = try (copy originalRotationController) catch (undefined)
        local taskScaleController = try (copy originalScaleController) catch (undefined)
        local positionAxes = try (getXYZControllers taskPositionController) catch (undefined)
        local rotationAxes = try (getXYZControllers taskRotationController) catch (undefined)
        local copyable =
            originalPositionController != undefined and originalRotationController != undefined and originalScaleController != undefined and
            taskPositionController != undefined and taskRotationController != undefined and taskScaleController != undefined and
            positionAxes != undefined and positionAxes.count == 3 and
            rotationAxes != undefined and rotationAxes.count == 3
        if copyable then append result node else append skippedNames (node.name as string)
    )
    if skippedNames.count > 0 do
    (
        local previewNames = #()
        local previewCount = if skippedNames.count < 8 then skippedNames.count else 8
        for i = 1 to previewCount do append previewNames skippedNames[i]
        RMTool_Proxy_Log ("task-local live dependency controllers skipped=" + (skippedNames.count as string) + " examples=" + (RMTool_ADV_JoinStrings previewNames ", "))
    )
    result
)

fn RMTool_Proxy_CaptureTaskLocalTransformControllers nodes startF endF =
(
    -- BakeAnimation=false preserves the carefully selected Euler order and
    -- dense linear keys, but FBX then ignores BakeFrameStart/End for native
    -- controllers. Export each split task through temporary Position/Rotation
    -- controller copies containing only this task's keys. The full ProxyRoot
    -- controllers stay available for the following tasks and are restored
    -- immediately after every export.
    local context = #()
    local errorText = ""
    local removedKeyCount = 0
    try
    (
        for node in nodes do
        (
            if node == undefined or not isValidNode node do throw "ProxyRoot task-local transform node invalid"
            local originalPositionController = try (node.position.controller) catch (undefined)
            local originalRotationController = try (node.rotation.controller) catch (undefined)
            local originalScaleController = try (node.scale.controller) catch (undefined)
            if originalPositionController == undefined or originalRotationController == undefined or originalScaleController == undefined do
                throw ("ProxyRoot task-local transform controller missing: " + (node.name as string))

            local taskPositionController = try (copy originalPositionController) catch (undefined)
            local taskRotationController = try (copy originalRotationController) catch (undefined)
            local taskScaleController = try (copy originalScaleController) catch (undefined)
            if taskPositionController == undefined or taskRotationController == undefined or taskScaleController == undefined do
                throw ("ProxyRoot task-local transform controller copy failed: " + (node.name as string))

            append context #(node, originalPositionController, originalRotationController, originalScaleController)
            node.position.controller = taskPositionController
            node.rotation.controller = taskRotationController
            node.scale.controller = taskScaleController

            local positionAxes = try (getXYZControllers node.position.controller) catch (undefined)
            local rotationAxes = try (getXYZControllers node.rotation.controller) catch (undefined)
            if positionAxes == undefined or positionAxes.count != 3 do
                throw ("ProxyRoot task-local Position axes unavailable: " + (node.name as string))
            if rotationAxes == undefined or rotationAxes.count != 3 do
                throw ("ProxyRoot task-local Rotation axes unavailable: " + (node.name as string))
            for axisController in positionAxes do removedKeyCount += RMTool_Proxy_TrimAxisControllerKeys axisController startF endF
            for axisController in rotationAxes do removedKeyCount += RMTool_Proxy_TrimAxisControllerKeys axisController startF endF
            local scaleAxes = try (getXYZControllers node.scale.controller) catch (undefined)
            if scaleAxes != undefined and scaleAxes.count == 3 then
            (
                for axisController in scaleAxes do removedKeyCount += RMTool_Proxy_TrimAxisControllerKeys axisController startF endF
            )
            else
            (
                removedKeyCount += RMTool_Proxy_TrimAxisControllerKeys node.scale.controller startF endF
            )
        )
    )
    catch (errorText = getCurrentException() as string)

    if errorText != "" do
    (
        RMTool_Proxy_RestoreTaskLocalTransformControllers context
        throw errorText
    )
    RMTool_Proxy_Log ("task-local PRS range=" + (startF as string) + "-" + (endF as string) + " nodes=" + (context.count as string) + " removedPosRotKeys=" + (removedKeyCount as string))
    context
)

fn RMTool_Proxy_RestoreTaskLocalTransformControllers context =
(
    local restoredCount = 0
    if context == undefined do return restoredCount
    for entry in context do
    (
        local node = entry[1]
        if node != undefined and isValidNode node do
        (
            local restored = try
            (
                node.position.controller = entry[2]
                node.rotation.controller = entry[3]
                node.scale.controller = entry[4]
                true
            )
            catch (false)
            if restored do restoredCount += 1
        )
    )
    restoredCount
)

fn RMTool_Proxy_ExportDenseWithHideScale objsToExport fbxPath s e sampleMultiplier excludedScaleNodes:#() morphMeshes:#() taskLocalScale:true =
(
    if sampleMultiplier == undefined do sampleMultiplier = 1
    sampleMultiplier = sampleMultiplier as integer
    if (findItem #(1, 2, 4) sampleMultiplier) == 0 do throw ("ProxyRoot invalid sample multiplier: " + (sampleMultiplier as string))
    if morphMeshes == undefined do morphMeshes = #()
    local exportMorphShapes = (morphMeshes.count > 0)
    -- BakeAnimation is intentionally disabled so FBX does not percent*10 scale
    -- keys. In that mode BakeFrameStart/End do not crop native controller keys.
    -- Every keyed proxy scale track must therefore be replaced temporarily with
    -- a task-local controller containing only s..e, then restored after export.
    -- includeKeyedUnitTracks also isolates the inverse case: unit in this task,
    -- non-unit elsewhere on the full proxy timeline.
    local scaleExportNodes = for node in objsToExport collect node
    for morphMesh in morphMeshes do if morphMesh != undefined and isValidNode morphMesh and (findItem scaleExportNodes morphMesh) == 0 do append scaleExportNodes morphMesh
    local scaleScanStats = #()
    local preservedScaleContext = RMTool_Proxy_CapturePreservedScaleNodes scaleExportNodes s e excludedNodes:excludedScaleNodes scanStats:scaleScanStats includeKeyedUnitTracks:true
    local expectedPreservedScaleCount = 0
    for node in scaleExportNodes do if node != undefined and isValidNode node and (findItem excludedScaleNodes node) == 0 do expectedPreservedScaleCount += 1
    if scaleScanStats.count < 3 or scaleScanStats[1] != expectedPreservedScaleCount do throw ("ProxyRoot preserved-scale export scan incomplete: " + (if scaleScanStats.count > 0 then (scaleScanStats[1] as string) else "0") + "/" + (expectedPreservedScaleCount as string))
    local savedFBXSettings = #()
    local exportOK = false
    local errorText = ""
    local originalFrameRate = frameRate
    local exportFrameRate = originalFrameRate * sampleMultiplier
    local fbxParamsToSave = #("Animation", "AxisConversionMethod", "BakeAnimation", "BakeFrameStart", "BakeFrameEnd", "BakeFrameStep", "BakeResampleAnimation", "Cameras", "Lights", "Shape", "Skin", "EmbedTextures", "PointCache", "GeomAsBone", "FilterKeyReducer", "Removesinglekeys", "UpAxis", "ShowWarnings", "GenerateLog")
    try
    (
        if originalFrameRate != 30 do throw ("ProxyRoot requires a 30 FPS Max scene; current FPS=" + (originalFrameRate as string))
        if taskLocalScale do
        (
            if RMTool_HideScale_ApplySamplesVerified == undefined do throw "ProxyRoot task-local scale writer missing"
            local appliedCount = 0
            for entry in preservedScaleContext do
            (
                local applyResult = RMTool_HideScale_ApplySamplesVerified entry[1] entry[3] entry[5] tolerance:0.0001
                if not applyResult[1] do throw ("ProxyRoot task-local scale apply failed. node=" + entry[4] + " frame=" + (applyResult[3] as string) + " err=" + (applyResult[2] as string) + " actual=" + (applyResult[4] as string) + " expected=" + (applyResult[5] as string) + " keys=" + (applyResult[6] as string) + " ctrl=" + applyResult[7])
                appliedCount += 1
            )
            if appliedCount != preservedScaleContext.count do throw ("ProxyRoot task-local scale apply incomplete: " + (appliedCount as string) + "/" + (preservedScaleContext.count as string))
        )
        RMTool_Proxy_Log ("dense FBX sampleRate=" + (exportFrameRate as string) + "Hz nativeKeysPerFrame=" + (sampleMultiplier as string) + " range=" + (s as string) + "-" + (e as string) + " morphMeshes=" + (morphMeshes.count as string) + " taskLocalScale=" + (taskLocalScale as string) + " taskScaleTracks=" + (preservedScaleContext.count as string))
        pluginManager.loadClass FBXEXPORTER
        savedFBXSettings = RMTool_ADV_CaptureFBXSettings fbxParamsToSave
        frameRate = exportFrameRate
        RMTool_ADV_SetFBXParamSafe "Animation" true
        RMTool_ADV_SetFBXParamSafe "AxisConversionMethod" "Animation"
        RMTool_ADV_SetFBXParamSafe "BakeAnimation" false
        RMTool_ADV_SetFBXParamSafe "BakeFrameStart" (s * sampleMultiplier)
        RMTool_ADV_SetFBXParamSafe "BakeFrameEnd" (e * sampleMultiplier)
        RMTool_ADV_SetFBXParamSafe "BakeFrameStep" 1
        RMTool_ADV_SetFBXParamSafe "BakeResampleAnimation" false
        RMTool_ADV_SetFBXParamSafe "FilterKeyReducer" false
        RMTool_ADV_SetFBXParamSafe "Removesinglekeys" false
        RMTool_ADV_SetFBXParamSafe "Cameras" false
        RMTool_ADV_SetFBXParamSafe "Lights" false
        -- Shape/Morpher: with Morpher meshes in the selection, Shape must be on
        -- and GeomAsBone must be off or the Morph channels are dropped (same
        -- convention as the ADV path).
        RMTool_ADV_SetFBXParamSafe "Shape" exportMorphShapes
        RMTool_ADV_SetFBXParamSafe "Skin" exportMorphShapes
        if exportMorphShapes then
            RMTool_ADV_SetFBXParamSafe "GeomAsBone" false
        else
            RMTool_ADV_SetFBXParamSafe "GeomAsBone" true
        RMTool_ADV_SetFBXParamSafe "EmbedTextures" false
        RMTool_ADV_SetFBXParamSafe "PointCache" false
        RMTool_ADV_SetFBXParamSafe "UpAxis" "Y"
        RMTool_ADV_SetFBXParamSafe "ShowWarnings" false
        RMTool_ADV_SetFBXParamSafe "GenerateLog" false
        local result = exportFile fbxPath #noPrompt selectedOnly:true using:FBXEXP
        if result == false do throw ("FBXExporter returned false: " + fbxPath)
        exportOK = true
    )
    catch (errorText = getCurrentException() as string)
    try (frameRate = originalFrameRate) catch
    (
        local restoreFrameRateError = "ProxyRoot failed to restore Max frame rate to " + (originalFrameRate as string)
        if errorText == "" then errorText = restoreFrameRateError else errorText += " | " + restoreFrameRateError
        exportOK = false
    )
    try (RMTool_ADV_RestoreFBXSettings savedFBXSettings) catch ()
    if taskLocalScale do
    (
        local restoredCount = RMTool_HideScale_RestoreSourceNodes preservedScaleContext
        if restoredCount != preservedScaleContext.count do
        (
            local restoreError = "ProxyRoot task-local scale restore failed: " + (restoredCount as string) + "/" + (preservedScaleContext.count as string)
            if errorText == "" then errorText = restoreError else errorText += " | " + restoreError
            exportOK = false
        )
    )
    if not exportOK do throw errorText
    true
)

fn RMTool_Proxy_BuildDesiredRootTransforms baseRootTM baseX baseY baseZ rawRootPosList rootAddedYawList totalStartF totalEndF enablePos enableRot =
(
    local result = #()
    local frameCount = totalEndF - totalStartF + 1
    if frameCount < 1 do return result

    local baseSX = length baseRootTM.row1
    local baseSY = length baseRootTM.row2
    local baseSZ = length baseRootTM.row3
    if baseSX < 0.0000001 do baseSX = 1.0
    if baseSY < 0.0000001 do baseSY = 1.0
    if baseSZ < 0.0000001 do baseSZ = 1.0

    for idx = 1 to frameCount do
    (
        local desiredTM = copy baseRootTM
        if enableRot do
        (
            local addedYaw = 0.0
            if rootAddedYawList != undefined and idx <= rootAddedYawList.count do addedYaw = rootAddedYawList[idx] as float
            local rotQ = (eulerangles baseX baseY (baseZ + addedYaw)) as quat
            local rotTM = rotQ as matrix3
            rotTM.row1 *= baseSX
            rotTM.row2 *= baseSY
            rotTM.row3 *= baseSZ
            rotTM.pos = desiredTM.pos
            desiredTM = rotTM
        )
        if enablePos and rawRootPosList != undefined and idx <= rawRootPosList.count do desiredTM.pos = rawRootPosList[idx]
        append result desiredTM
    )
    result
)

fn RMTool_Proxy_FindNodeIndex nodes targetNode =
(
    if targetNode == undefined do return 0
    findItem nodes targetNode
)

-- FBX/Unity animation bindings are hierarchy-path based. Duplicate leaf names
-- are therefore legal when their parent paths differ; only an identical full
-- exported path is ambiguous. Build paths from the already identity-based
-- parent index table instead of using getNodeByName.
fn RMTool_Proxy_BuildHierarchyPaths nodeNames parentIndices =
(
    if nodeNames == undefined or parentIndices == undefined or nodeNames.count != parentIndices.count do throw "ProxyRoot hierarchy path input mismatch" debugBreak:false
    local paths = for i = 1 to nodeNames.count collect undefined
    local unresolved = nodeNames.count
    for passIndex = 1 to nodeNames.count do
    (
        if unresolved > 0 do
        (
            for i = 1 to nodeNames.count where paths[i] == undefined do
            (
                local parentIndex = parentIndices[i]
                if parentIndex == 0 then
                (
                    paths[i] = toLower (nodeNames[i] as string)
                    unresolved -= 1
                )
                else if parentIndex > 0 and parentIndex <= nodeNames.count and paths[parentIndex] != undefined do
                (
                    paths[i] = paths[parentIndex] + "/" + (toLower (nodeNames[i] as string))
                    unresolved -= 1
                )
            )
        )
    )
    if unresolved > 0 do throw ("ProxyRoot hierarchy path build unresolved nodes=" + (unresolved as string)) debugBreak:false
    paths
)

fn RMTool_Proxy_FindDuplicateHierarchyPaths nodeNames parentIndices =
(
    local paths = RMTool_Proxy_BuildHierarchyPaths nodeNames parentIndices
    local seen = #()
    local duplicates = #()
    for pathText in paths do
    (
        local key = toLower (pathText as string)
        if (findItem seen key) == 0 then append seen key
        else if (findItem duplicates key) == 0 do append duplicates key
    )
    duplicates
)

fn RMTool_Proxy_FindDuplicateExportHierarchyPathsForScene rootObj useAdvExport =
(
    -- Read-only preflight used by Python before the export backend starts.
    -- Returning the paths instead of throwing prevents the MAXScript debugger
    -- from interrupting artists for this known binding-authoring error.
    if rootObj == undefined or (not isValidNode rootObj) do return #()
    local excludedBipedRoots = #()
    local sourceNodes = RMTool_ADV_CollectExportNodesExceptBipedBranches rootObj useAdvExport excludedBipedRoots
    local parentIndices = RMTool_ADV_GetParentIndices sourceNodes
    local exportNames = #()
    for node in sourceNodes do
    (
        if useAdvExport then append exportNames (RMTool_ADV_ToCleanBakeExportName node.name)
        else append exportNames node.name
    )
    local duplicates = RMTool_Proxy_FindDuplicateHierarchyPaths exportNames parentIndices
    if duplicates.count > 0 do RMTool_Proxy_Log ("preflight duplicate export hierarchy paths: " + (RMTool_ADV_JoinStrings duplicates ", "))
    duplicates
)

fn RMTool_Proxy_CreateContext rootObj bipObj sourceBipTransforms poseBipTransforms desiredRootTransforms totalStartF totalEndF customOffset usePoseTransformOverride useAdvExport extraNodes sampleMultiplier morphMeshes:#() autoMorph:true =
(
    local phaseTimestamp = timeStamp()
    if rootObj == undefined or (not isValidNode rootObj) do throw "ProxyRoot root missing"
    if desiredRootTransforms == undefined do throw "ProxyRoot desired Root transforms missing"
    local frameCount = totalEndF - totalStartF + 1
    if frameCount < 1 or desiredRootTransforms.count != frameCount do throw "ProxyRoot desired Root frame count mismatch"

    local excludedBipedRoots = #()
    local sourceNodes = RMTool_ADV_CollectExportNodesExceptBipedBranches rootObj useAdvExport excludedBipedRoots
    sourceNodes = RMTool_ADV_MergeExtraNodes sourceNodes extraNodes

    -- Morpher meshes stay as live geometry (only they can carry Shape curves);
    -- they are excluded from the proxy bone rebuild and re-attached to the
    -- export selection in ExportContext, mirroring the ADV path convention.
    if morphMeshes == undefined do morphMeshes = #()
    local resolvedMorphMeshes = RMTool_ADV_ResolveMorpherMeshes morphMeshes autoMorph
    if resolvedMorphMeshes.count > 0 do
    (
        for n in sourceNodes do
        (
            local parentNode = try (n.parent) catch (undefined)
            if parentNode != undefined and (findItem resolvedMorphMeshes parentNode) > 0 do
                throw ("ProxyRoot Morpher mesh has exported child nodes; unsupported hierarchy: " + (parentNode.name as string) + " -> " + (n.name as string))
        )
        local filteredSourceNodes = #()
        for n in sourceNodes do if (findItem resolvedMorphMeshes n) == 0 do append filteredSourceNodes n
        sourceNodes = filteredSourceNodes
        RMTool_Proxy_Log ("morpher meshes excluded from proxy bake, exported live: " + (resolvedMorphMeshes.count as string))
    )
    if sourceNodes.count < 2 do throw "ProxyRoot export hierarchy is empty"

    local parentIndices = RMTool_ADV_GetParentIndices sourceNodes
    local duplicateNames = RMTool_ADV_FindDuplicateNodeNames sourceNodes
    if duplicateNames.count > 0 do RMTool_Proxy_Log ("accepted duplicate leaf names with distinct hierarchy paths: " + (RMTool_ADV_JoinStrings duplicateNames ", "))
    local sourceNames = for n in sourceNodes collect n.name
    local sourceInheritanceFlags = for n in sourceNodes collect (try (getInheritanceFlags n) catch (#{1..9}))
    local duplicateSourcePaths = RMTool_Proxy_FindDuplicateHierarchyPaths sourceNames parentIndices
    if duplicateSourcePaths.count > 0 do throw ("ProxyRoot duplicate source hierarchy paths: " + (RMTool_ADV_JoinStrings duplicateSourcePaths ", ")) debugBreak:false

    local bakeOrder = RMTool_Proxy_GetParentFirstOrder parentIndices
    local startWorldTMs = RMTool_ADV_GetStartFrameWorldTMs sourceNodes totalStartF
    local originalNames = for n in sourceNodes collect n.name
    local excludedSourceScaleNodes = #(rootObj, bipObj)
    local scaleScanStats = #()
    local preservedScaleContext = RMTool_Proxy_CapturePreservedScaleNodes sourceNodes totalStartF totalEndF excludedNodes:excludedSourceScaleNodes scanStats:scaleScanStats parentIndices:parentIndices
    RMTool_Proxy_Log ("phase scaleCapture ms=" + ((timeStamp() - phaseTimestamp) as string)); phaseTimestamp = timeStamp()
    local expectedPreservedScaleCount = 0
    for node in sourceNodes do if node != undefined and isValidNode node and (findItem excludedSourceScaleNodes node) == 0 do expectedPreservedScaleCount += 1
    if scaleScanStats.count < 3 or scaleScanStats[1] != expectedPreservedScaleCount do throw ("ProxyRoot preserved-scale source scan incomplete: " + (if scaleScanStats.count > 0 then (scaleScanStats[1] as string) else "0") + "/" + (expectedPreservedScaleCount as string))
    local controllerlessScaleSourceCount = scaleScanStats[3]
    local proxyNodes = #()
    local proxyTempNames = #()
    local bipIndex = RMTool_Proxy_FindNodeIndex sourceNodes bipObj
    -- ADV rigs intentionally exclude the live Biped branch and export the
    -- Bone_Skin_Bip001 Pelvis hierarchy instead.  WallHit pose compensation
    -- must therefore be applied to that exported branch with the live Bip001
    -- world TM as its reference.  Previously bipIndex was 0 on ADV rigs, so
    -- Some legacy rigs kept the unadjusted COM travel while Root used the split
    -- WallHit trajectory; Rise_Start consequently sent the body away from Root.
    local poseBranchIndex = bipIndex
    if poseBranchIndex == 0 and useAdvExport do
    (
        for i = 1 to sourceNodes.count while poseBranchIndex == 0 do
        (
            if (toLower (sourceNodes[i].name as string)) == "bone_skin_bip001 pelvis" do poseBranchIndex = i
        )
    )
    local poseBranchRoot = if poseBranchIndex > 0 then sourceNodes[poseBranchIndex] else undefined
    if usePoseTransformOverride and poseBranchIndex == 0 do
        throw "ProxyRoot WallHit COM pose branch missing (expected Bip001 or Bone_Skin_Bip001 Pelvis)" debugBreak:false
    local poseMayDiffer = usePoseTransformOverride or (customOffset != undefined and (length customOffset) > 0.000001)
    local externalPoseConstraintData = RMTool_Proxy_BuildExternalPoseConstraintData sourceNodes poseBranchRoot bipObj poseMayDiffer
    local externalPoseConstraintDescriptors = externalPoseConstraintData[1]
    local externalPoseBodyRoots = externalPoseConstraintData[2]
    local externalPoseConstraintLabels = externalPoseConstraintData[3]
    if externalPoseConstraintLabels.count > 0 do RMTool_Proxy_Log ("constraint-aware external pose nodes: " + (RMTool_ADV_JoinStrings externalPoseConstraintLabels ", "))
    local oldSelection = getCurrentSelection()
    local oldTaskMode = getCommandPanelTaskMode()
    local redrawDisabled = false
    local editingSuspended = false
    local maxPositionError = 0.0
    local maxAxisError = 0.0
    local maxRootPositionError = 0.0
    local maxRootAxisError = 0.0
    local maxBipPositionError = 0.0
    local maxBipAxisError = 0.0
    local worstPositionNodeName = rootObj.name
    local worstPositionFrame = totalStartF
    local worstAxisNodeName = rootObj.name
    local worstAxisFrame = totalStartF
    local maxHierarchyPositionRatio = 0.0
    local worstHierarchyRatioNodeName = rootObj.name
    local worstHierarchyRatioFrame = totalStartF
    local worstHierarchyPositionTolerance = 0.0
    local rigidWorldWriteSampleCount = 0
    local maxEulerQuatRatio = 0.0
    local worstEulerRatioNodeName = rootObj.name
    local worstEulerRatioFrame = totalStartF
    local maxMidpointLocalAxisError = 0.0
    local worstMidpointNodeName = rootObj.name
    local worstMidpointFrame = totalStartF
    local maxSourceMidpointLocalAxisError = 0.0
    local worstSourceMidpointNodeName = rootObj.name
    local worstSourceMidpointFrame = totalStartF
    local preservedScaleAppliedCount = 0
    local maxPreservedScaleError = 0.0
    local worstPreservedScaleNodeName = rootObj.name
    local worstPreservedScaleFrame = totalStartF
    local currentStage = "init"
    local currentNodeName = rootObj.name
    local currentFrame = totalStartF
    local context = undefined
    -- Numeric-gate failures are collected here instead of throwing; the caller
    -- decides (interactive: user override dialog; batch: hard abort). Structural
    -- errors still throw immediately.
    local validationWarnings = #()
    local criticalPositionTolerance = units.decodeValue "0.01cm"
    local criticalAxisTolerance = 0.001
    -- Hierarchy gate stays proportional to the measured parent axis errors, so
    -- long bone chains (chain-ball weapons) still pass when their actual angular
    -- drift is small; the floor/cap/factor only got tighter, not the formula.
    local hierarchyMinimumPositionTolerance = units.decodeValue "0.2cm"
    local hierarchyAbsolutePositionCap = units.decodeValue "0.6cm"
    local hierarchyPropagationFactor = 1.5
    local hierarchyAxisTolerance = 0.002
    local midpointLocalAxisTolerance = 0.5
    if sampleMultiplier == undefined do sampleMultiplier = 1
    sampleMultiplier = sampleMultiplier as integer
    if (findItem #(1, 2, 4) sampleMultiplier) == 0 do throw ("ProxyRoot invalid sample multiplier: " + (sampleMultiplier as string))
    local totalSamples = (totalEndF - totalStartF) * sampleMultiplier
    local bakedFullWorldTargets = #()
    local bakedWorldTargets = #()
    local bakedLocalTargets = #()
    local sourceRotationDefinedFrameFlags = #()

    try
    (
        currentStage = "createProxyBones"
        RMTool_Proxy_ProgressUpdate 0.02 ("创建 proxy 骨骼（" + (sourceNodes.count as string) + " 根）...")
        setCommandPanelTaskMode #create
        disableSceneRedraw()
        redrawDisabled = true
        suspendEditing()
        editingSuspended = true

        for i = 1 to sourceNodes.count do
        (
            local displayLength = RMTool_ADV_GetDisplayBoneLength i parentIndices startWorldTMs
            local tempName = uniqueName "__OP_RM_PROXY__"
            local proxyNode = RMTool_Proxy_CreateRigidBakeBone tempName displayLength
            append proxyNodes proxyNode
            append proxyTempNames proxyNode.name
        )

        currentStage = "relink"
        for i = 1 to proxyNodes.count do
        (
            local parentIndex = parentIndices[i]
            if parentIndex > 0 do proxyNodes[i].parent = proxyNodes[parentIndex]
        )

        currentStage = "normalizeFbxScaleInheritance"
        for i = 1 to proxyNodes.count do
        (
            currentNodeName = sourceNodes[i].name
            local inheritanceOK = true
            if parentIndices[i] > 0 do inheritanceOK = try
            (
                local proxyFlags = getInheritanceFlags proxyNodes[i]
                -- FBX/Unity cannot reproduce Max's per-axis "do not inherit
                -- parent scale" flags consistently. Bake the source world pose
                -- into a conventional hierarchy whose scale inheritance is on;
                -- the later full-TM reconciliation derives FBX-local Scale keys.
                for flagIndex = 7 to 9 do proxyFlags[flagIndex] = true
                setInheritanceFlags proxyNodes[i] proxyFlags keepPos:true
                local appliedFlags = getInheritanceFlags proxyNodes[i]
                local scaleFlagsMatch = true
                for flagIndex = 7 to 9 where not appliedFlags[flagIndex] do scaleFlagsMatch = false
                scaleFlagsMatch
            )
            catch (false)
            if not inheritanceOK do throw ("ProxyRoot cannot normalize FBX scale-inheritance flags. node=" + currentNodeName)
        )

        currentStage = "sampleRigidWorldTargets"
        for sampleIndex = 0 to totalSamples do
        (
            RMTool_Proxy_ProgressUpdate (0.05 + 0.25 * (sampleIndex as float) / totalSamples) ("采样源动画世界矩阵 " + (sampleIndex as string) + "/" + (totalSamples as string) + "...")
            local sampleFrame = totalStartF + ((sampleIndex as float) / sampleMultiplier)
            currentFrame = sampleFrame
            at time sampleFrame
            (
                local sourceWorldTMs = #()
                local targetWorldTMs = #()
                for node in sourceNodes do append sourceWorldTMs (copy node.transform)
                for tm in sourceWorldTMs do append targetWorldTMs (copy tm)

                targetWorldTMs[1] = RMTool_Proxy_SampleTMArray desiredRootTransforms totalStartF sampleFrame

                if poseBranchIndex > 0 do
                (
                    local sourceBipTM = if bipIndex > 0 then sourceWorldTMs[bipIndex] else RMTool_Proxy_SampleTMArray sourceBipTransforms totalStartF sampleFrame
                    local targetBipTM = copy sourceBipTM
                    if usePoseTransformOverride do targetBipTM = RMTool_Proxy_BuildTranslationOnlyPoseTarget sourceBipTM poseBipTransforms totalStartF sampleFrame
                    targetBipTM = RMTool_Proxy_OffsetTM targetBipTM customOffset
                    local sourceBipDet = RMTool_ADV_MatrixDet3 sourceBipTM
                    if (abs sourceBipDet) < 0.00000001 do throw ("ProxyRoot source Bip transform is singular at frame " + (currentFrame as string))
                    local inverseSourceBipTM = inverse sourceBipTM
                    for i = 1 to sourceNodes.count do
                    (
                        if RMTool_Proxy_IsDescendantOrSelf sourceNodes[i] poseBranchRoot then
                            targetWorldTMs[i] = sourceWorldTMs[i] * inverseSourceBipTM * targetBipTM
                    )
                    targetWorldTMs = RMTool_Proxy_ApplyPoseTranslationInfluences sourceWorldTMs targetWorldTMs sourceBipTM targetBipTM sourceNodes parentIndices poseBranchRoot externalPoseBodyRoots externalPoseConstraintDescriptors sampleFrame
                )

                local sourceRotationDefinedFlags = #()
                for tm in targetWorldTMs do append sourceRotationDefinedFlags (RMTool_Proxy_IsSourceRotationDefined tm)
                append sourceRotationDefinedFrameFlags sourceRotationDefinedFlags
                local fullTargetWorldTMs = for tm in targetWorldTMs collect (copy tm)
                append bakedFullWorldTargets fullTargetWorldTMs
                local rigidTargetWorldTMs = #()
                for tm in targetWorldTMs do append rigidTargetWorldTMs (RMTool_Backend_TMNoScale tm)
                append bakedWorldTargets rigidTargetWorldTMs
            )
        )
        RMTool_Proxy_Log ("phase sampleRigidWorldTargets ms=" + ((timeStamp() - phaseTimestamp) as string)); phaseTimestamp = timeStamp()

        currentStage = "deriveRigidLocalTargets"
        for frameIndex = 1 to bakedWorldTargets.count do
        (
        local frameWorldTMs = bakedWorldTargets[frameIndex]
        local frameLocalTMs = #()
            for i = 1 to sourceNodes.count do
            (
                local parentIndex = parentIndices[i]
                local localTM = if parentIndex > 0 then (frameWorldTMs[i] * (inverse frameWorldTMs[parentIndex])) else (copy frameWorldTMs[i])
                localTM = RMTool_Backend_TMNoScale localTM
                append frameLocalTMs localTM
            )
            append bakedLocalTargets frameLocalTMs
        )
        RMTool_Proxy_Log ("phase deriveRigidLocalTargets ms=" + ((timeStamp() - phaseTimestamp) as string)); phaseTimestamp = timeStamp()

        -- bone_ctrl* / ctrl_bone* visibility bones key their scale to exact zero
        -- to hide; a zero-scale axis leaves the local target with zero-length
        -- rows whose rotation is undefined, so no Euler order can decompose it
        -- (probe fails with ~90 deg error even far from gimbal lock). The bone
        -- is invisible at that instant: hold the nearest valid rotation (the
        -- position row4 stays untouched) so the dense curves stay continuous.
        currentStage = "repairDegenerateLocalRotations"
        local degenerateRotationRepairCount = 0
        local degenerateRotationNodeNames = #()
        -- Per-node per-frame flags marking rotations substituted from the
        -- nearest valid frame. The world-axis validation must skip exactly
        -- these (node, frame) pairs: the substituted rotation is intentional
        -- (bone invisible at zero scale) and comparing it against the real
        -- target only yields meaningless 90-degree false positives.
        local degenerateRepairedFrameFlags = #()
        for i = 1 to sourceNodes.count do
        (
            local firstValidTM = undefined
            for frameIndex = 1 to bakedLocalTargets.count while firstValidTM == undefined do
            (
                local probeTM = bakedLocalTargets[frameIndex][i]
                if sourceRotationDefinedFrameFlags[frameIndex][i] and RMTool_Proxy_IsValidRigidRotationTM probeTM do firstValidTM = probeTM
            )
            if firstValidTM == undefined do firstValidTM = matrix3 1
            local lastValidTM = firstValidTM
            local nodeRepairCount = 0
            local nodeRepairedFlags = #()
            for frameIndex = 1 to bakedLocalTargets.count do append nodeRepairedFlags false
            for frameIndex = 1 to bakedLocalTargets.count do
            (
                local localTM = bakedLocalTargets[frameIndex][i]
                if sourceRotationDefinedFrameFlags[frameIndex][i] and RMTool_Proxy_IsValidRigidRotationTM localTM then
                (
                    lastValidTM = localTM
                )
                else
                (
                    local repairSourceTM = if frameIndex > 1 then lastValidTM else firstValidTM
                    bakedLocalTargets[frameIndex][i] = matrix3 repairSourceTM.row1 repairSourceTM.row2 repairSourceTM.row3 localTM.row4
                    nodeRepairCount += 1
                    nodeRepairedFlags[frameIndex] = true
                )
            )
            append degenerateRepairedFrameFlags nodeRepairedFlags
            if nodeRepairCount > 0 do
            (
                degenerateRotationRepairCount += nodeRepairCount
                append degenerateRotationNodeNames ((originalNames[i] as string) + "x" + (nodeRepairCount as string))
            )
        )
        if degenerateRotationRepairCount > 0 do RMTool_Proxy_Log ("degenerate local rotations repaired (zero-scale visibility frames hold nearest valid): count=" + (degenerateRotationRepairCount as string) + " nodes=" + (RMTool_ADV_JoinStrings degenerateRotationNodeNames ", "))

        -- Pick the Euler order independently for every proxy. XYZ is unsafe when
        -- its middle axis reaches +/-90 degrees: Max 2020's matrix decomposition
        -- can already change the keyed pose before FBX sees it. Probe all six
        -- Tait-Bryan orders against the actual Local matrices and choose the valid
        -- order with the largest worst-case distance from its gimbal singularity.
        currentStage = "selectAdaptiveEulerOrders"
        local eulerSubControllerTracks = #()
        local selectedEulerOrders = #()
        local nonXYZOrderCount = 0
        local minimumSelectedGimbalMargin = 180.0
        local maximumSelectedDecomposeAxisError = 0.0
        for i = 1 to proxyNodes.count do
        (
            RMTool_Proxy_ProgressUpdate (0.34 + 0.14 * (i as float) / proxyNodes.count) ("选择稳定欧拉序 " + (i as string) + "/" + (proxyNodes.count as string) + " ...")
            currentNodeName = sourceNodes[i].name
            local eulerSubControllers = try (getXYZControllers proxyNodes[i].rotation.controller) catch (undefined)
            if eulerSubControllers == undefined or eulerSubControllers.count != 3 do throw ("ProxyRoot adaptive Euler subcontrollers unavailable. node=" + currentNodeName)
            append eulerSubControllerTracks eulerSubControllers
            local bestOrder = 0
            local bestGimbalMargin = -1.0
            local bestAxisError = 999999.0
            for candidateOrder = 1 to 6 do
            (
                local orderSetOK = try (proxyNodes[i].rotation.controller.axisOrder = candidateOrder; proxyNodes[i].rotation.controller.axisOrder == candidateOrder) catch (false)
                if orderSetOK do
                (
                    local candidateMaxAxisError = 0.0
                    local candidateMinGimbalMargin = 180.0
                    for frameIndex = 1 to bakedLocalTargets.count do
                    (
                        local sampleFrame = totalStartF + (((frameIndex - 1) as float) / sampleMultiplier)
                        currentFrame = sampleFrame
                        local targetLocalTM = bakedLocalTargets[frameIndex][i]
                        local actualLocalTM = undefined
                        local middleAngle = 0.0
                        at time sampleFrame animate off
                        (
                            proxyNodes[i].transform.controller.value = targetLocalTM
                            actualLocalTM = RMTool_Backend_TMNoScale (copy proxyNodes[i].transform.controller.value)
                            middleAngle = case candidateOrder of
                            (
                                1: radToDeg eulerSubControllers[2].value
                                2: radToDeg eulerSubControllers[3].value
                                3: radToDeg eulerSubControllers[3].value
                                4: radToDeg eulerSubControllers[1].value
                                5: radToDeg eulerSubControllers[1].value
                                6: radToDeg eulerSubControllers[2].value
                            )
                        )
                        local candidateAxisError = RMTool_ADV_MatrixAxisError actualLocalTM targetLocalTM
                        if candidateAxisError > candidateMaxAxisError do candidateMaxAxisError = candidateAxisError
                        local normalizedMiddleAngle = RMTool_Proxy_NormalizeEulerAngle middleAngle
                        local gimbalMargin = abs (90.0 - (abs normalizedMiddleAngle))
                        if gimbalMargin < candidateMinGimbalMargin do candidateMinGimbalMargin = gimbalMargin
                    )
                    local candidatePoseValid = candidateMaxAxisError <= criticalAxisTolerance
                    local bestPoseValid = bestOrder > 0 and bestAxisError <= criticalAxisTolerance
                    if (candidatePoseValid and ((not bestPoseValid) or candidateMinGimbalMargin > bestGimbalMargin)) or ((not candidatePoseValid) and (not bestPoseValid) and candidateMaxAxisError < bestAxisError) do
                    (
                        bestOrder = candidateOrder
                        bestGimbalMargin = candidateMinGimbalMargin
                        bestAxisError = candidateMaxAxisError
                    )
                )
            )
            if bestOrder == 0 or bestAxisError > criticalAxisTolerance do
            (
                local minTargetRowLen = 999999.0
                local minTargetAbsDet = 999999.0
                local nearFailFrame = totalStartF
                for frameIndex = 1 to bakedLocalTargets.count do
                (
                    local diagTM = bakedLocalTargets[frameIndex][i]
                    local minRowLen = (length diagTM.row1)
                    if (length diagTM.row2) < minRowLen do minRowLen = length diagTM.row2
                    if (length diagTM.row3) < minRowLen do minRowLen = length diagTM.row3
                    local absDet = abs (RMTool_ADV_MatrixDet3 diagTM)
                    if minRowLen < minTargetRowLen do minTargetRowLen = minRowLen
                    if absDet < minTargetAbsDet do (minTargetAbsDet = absDet; nearFailFrame = totalStartF + (((frameIndex - 1) as float) / sampleMultiplier))
                )
                throw ("ProxyRoot no stable Euler order. node=" + currentNodeName + " bestOrder=" + (bestOrder as string) + " axisErr=" + (bestAxisError as string) + " gimbalMargin=" + (bestGimbalMargin as string) + " minTargetRowLen=" + (minTargetRowLen as string) + " minTargetAbsDet=" + (minTargetAbsDet as string) + " nearFrame=" + (nearFailFrame as string))
            )
            proxyNodes[i].rotation.controller.axisOrder = bestOrder
            append selectedEulerOrders bestOrder
            if bestOrder != 1 do nonXYZOrderCount += 1
            if bestGimbalMargin < minimumSelectedGimbalMargin do minimumSelectedGimbalMargin = bestGimbalMargin
            if bestAxisError > maximumSelectedDecomposeAxisError do maximumSelectedDecomposeAxisError = bestAxisError
        )
        RMTool_Proxy_Log ("phase selectAdaptiveEulerOrders ms=" + ((timeStamp() - phaseTimestamp) as string)); phaseTimestamp = timeStamp()

        currentStage = "bakeExactEulerLocalTargets"
        for sampleIndex = 0 to totalSamples do
        (
            RMTool_Proxy_ProgressUpdate (0.50 + 0.28 * (sampleIndex as float) / totalSamples) ("烘焙欧拉关键帧 " + (sampleIndex as string) + "/" + (totalSamples as string) + "...")
            local frameIndex = sampleIndex + 1
            local sampleFrame = totalStartF + ((sampleIndex as float) / sampleMultiplier)
            local frameLocalTMs = bakedLocalTargets[frameIndex]
            currentFrame = sampleFrame
            at time sampleFrame animate on
            (
                for orderIndex = 1 to bakeOrder.count do
                (
                    local i = bakeOrder[orderIndex]
                    currentNodeName = sourceNodes[i].name
                    local localWriteOK = try
                    (
                        proxyNodes[i].transform.controller.value = frameLocalTMs[i]
                        true
                    )
                    catch (false)
                    if not localWriteOK do throw ("ProxyRoot exact Euler Local write failed. node=" + currentNodeName + " frame=" + (currentFrame as string))
                    rigidWorldWriteSampleCount += 1
                )
            )
        )
        RMTool_Proxy_Log ("phase bakeExactEulerLocalTargets ms=" + ((timeStamp() - phaseTimestamp) as string)); phaseTimestamp = timeStamp()

        -- The chosen middle axis stays away from gimbal. Canonical Max angles can
        -- now only wrap by whole revolutions, so per-channel +/-360 unwrapping is
        -- pose-exact and does not require a quaternion/order conversion.
        currentStage = "unwrapAdaptiveEulerTracks"
        local smoothEulerTracks = #()
        for i = 1 to proxyNodes.count do
        (
            currentNodeName = sourceNodes[i].name
            local smoothEulers = #()
            local previousEuler = undefined
            for frameIndex = 1 to bakedLocalTargets.count do
            (
                local sampleFrame = totalStartF + (((frameIndex - 1) as float) / sampleMultiplier)
                currentFrame = sampleFrame
                local canonicalEuler = at time sampleFrame (eulerangles (radToDeg eulerSubControllerTracks[i][1].value) (radToDeg eulerSubControllerTracks[i][2].value) (radToDeg eulerSubControllerTracks[i][3].value))
                if previousEuler != undefined do
                (
                    canonicalEuler.x = RMTool_Proxy_UnwrapEulerAngle canonicalEuler.x previousEuler.x
                    canonicalEuler.y = RMTool_Proxy_UnwrapEulerAngle canonicalEuler.y previousEuler.y
                    canonicalEuler.z = RMTool_Proxy_UnwrapEulerAngle canonicalEuler.z previousEuler.z
                )
                append smoothEulers canonicalEuler
                previousEuler = copy canonicalEuler
            )
            append smoothEulerTracks smoothEulers
        )
        currentStage = "writeAdaptiveEulerTracks"
        for sampleIndex = 0 to totalSamples do
        (
            local frameIndex = sampleIndex + 1
            local sampleFrame = totalStartF + ((sampleIndex as float) / sampleMultiplier)
            currentFrame = sampleFrame
            at time sampleFrame animate on
            (
                for i = 1 to proxyNodes.count do
                (
                    currentNodeName = sourceNodes[i].name
                    local eul = smoothEulerTracks[i][frameIndex]
                    local eulerWriteOK = try
                    (
                        eulerSubControllerTracks[i][1].value = degToRad eul.x
                        eulerSubControllerTracks[i][2].value = degToRad eul.y
                        eulerSubControllerTracks[i][3].value = degToRad eul.z
                        true
                    )
                    catch (false)
                    if not eulerWriteOK do throw ("ProxyRoot adaptive Euler write failed. node=" + currentNodeName + " frame=" + (currentFrame as string))
                )
            )
        )
        currentStage = "setAdaptiveEulerLinearTangents"
        for i = 1 to eulerSubControllerTracks.count do
        (
            currentNodeName = sourceNodes[i].name
            for axisController in eulerSubControllerTracks[i] do
            (
                for keyIndex = 1 to (numKeys axisController) do
                (
                    local eulerKey = getKey axisController keyIndex
                    try (eulerKey.inTangentType = #linear) catch ()
                    try (eulerKey.outTangentType = #linear) catch ()
                )
            )
        )
        RMTool_Proxy_Log ("phase unwrapAndWriteEulerTracks ms=" + ((timeStamp() - phaseTimestamp) as string)); phaseTimestamp = timeStamp()

        currentStage = "postBakeHardValidation"
        RMTool_Proxy_ProgressUpdate 0.80 "姿态数值校验中..."
        local validationFrameIndex = 0
        local degenerateAxisSkipCount = 0
        for sampleIndex = 0 to totalSamples do
        (
            validationFrameIndex += 1
            local sampleFrame = totalStartF + ((sampleIndex as float) / sampleMultiplier)
            currentFrame = sampleFrame
            local targetWorldTMs = bakedWorldTargets[validationFrameIndex]
            at time sampleFrame
            (
                local framePositionErrors = #()
                local frameAxisErrors = #()
                -- Zero-scale visibility frames (bone_ctrl*/ctrl_bone* hidden via
                -- scale=0) make the target world matrix singular: rotation is
                -- undefined there and descendants inherit zero volume, so the
                -- axis comparison is skipped for the whole subtree at that
                -- frame. The position row4 stays meaningful and is still checked.
                local frameAxisSkip = #()
                for i = 1 to proxyNodes.count do append frameAxisSkip false
                for orderIndex = 1 to bakeOrder.count do
                (
                    local skipIndex = bakeOrder[orderIndex]
                    local targetWorldTM = targetWorldTMs[skipIndex]
                    local skipAxis = (length targetWorldTM.row1) < 0.5 or (length targetWorldTM.row2) < 0.5 or (length targetWorldTM.row3) < 0.5
                    local skipParentIndex = parentIndices[skipIndex]
                    if not skipAxis and skipParentIndex > 0 and frameAxisSkip[skipParentIndex] do skipAxis = true
                    if not skipAxis and degenerateRepairedFrameFlags[skipIndex][validationFrameIndex] do skipAxis = true
                    frameAxisSkip[skipIndex] = skipAxis
                )
                for i = 1 to proxyNodes.count do
                (
                    currentNodeName = sourceNodes[i].name
                    local actualWorldTM = RMTool_Backend_TMNoScale proxyNodes[i].transform
                    local positionError = distance actualWorldTM.pos targetWorldTMs[i].pos
                    local axisError = RMTool_ADV_MatrixAxisError actualWorldTM targetWorldTMs[i]
                    if frameAxisSkip[i] do (axisError = 0.0; degenerateAxisSkipCount += 1)
                    append framePositionErrors positionError
                    append frameAxisErrors axisError
                    if positionError > maxPositionError do
                    (
                        maxPositionError = positionError
                        worstPositionNodeName = currentNodeName
                        worstPositionFrame = currentFrame
                    )
                    if axisError > maxAxisError do
                    (
                        maxAxisError = axisError
                        worstAxisNodeName = currentNodeName
                        worstAxisFrame = currentFrame
                    )
                    if i == 1 do
                    (
                        if positionError > maxRootPositionError do maxRootPositionError = positionError
                        if axisError > maxRootAxisError do maxRootAxisError = axisError
                    )
                    if i == poseBranchIndex do
                    (
                        if positionError > maxBipPositionError do maxBipPositionError = positionError
                        if axisError > maxBipAxisError do maxBipAxisError = axisError
                    )
                )

                for i = 1 to proxyNodes.count do
                (
                    local adaptivePositionTolerance = RMTool_Proxy_GetAdaptivePositionTolerance i parentIndices targetWorldTMs frameAxisErrors hierarchyMinimumPositionTolerance hierarchyAbsolutePositionCap hierarchyPropagationFactor
                    local hierarchyPositionRatio = if adaptivePositionTolerance > 0.0 then framePositionErrors[i] / adaptivePositionTolerance else 999999.0
                    if hierarchyPositionRatio > maxHierarchyPositionRatio do
                    (
                        maxHierarchyPositionRatio = hierarchyPositionRatio
                        worstHierarchyRatioNodeName = sourceNodes[i].name
                        worstHierarchyRatioFrame = currentFrame
                        worstHierarchyPositionTolerance = adaptivePositionTolerance
                    )
                )
            )
        )
        RMTool_Proxy_Log ("phase postBakeHardValidation ms=" + ((timeStamp() - phaseTimestamp) as string)); phaseTimestamp = timeStamp()

        if degenerateAxisSkipCount > 0 do RMTool_Proxy_Log ("axis validation skipped degenerate zero-scale world frames: " + (degenerateAxisSkipCount as string))

        currentStage = "midpointContinuityValidation"
        RMTool_Proxy_ProgressUpdate 0.90 "连续性校验中..."
        if totalSamples > 0 do
        (
            for sampleIndex = 0 to (totalSamples - 1) do
            (
                local midpointFrame = totalStartF + (((sampleIndex as float) + 0.5) / sampleMultiplier)
                currentFrame = midpointFrame
                at time midpointFrame
                (
                    local midpointSourceWorldTMs = #()
                    local midpointTargetWorldTMs = #()
                    for node in sourceNodes do append midpointSourceWorldTMs (copy node.transform)
                    for tm in midpointSourceWorldTMs do append midpointTargetWorldTMs (copy tm)
                    midpointTargetWorldTMs[1] = RMTool_Proxy_SampleTMArray desiredRootTransforms totalStartF midpointFrame
                    if poseBranchIndex > 0 do
                    (
                        local midpointSourceBipTM = if bipIndex > 0 then midpointSourceWorldTMs[bipIndex] else RMTool_Proxy_SampleTMArray sourceBipTransforms totalStartF midpointFrame
                        local midpointTargetBipTM = copy midpointSourceBipTM
                        if usePoseTransformOverride do midpointTargetBipTM = RMTool_Proxy_BuildTranslationOnlyPoseTarget midpointSourceBipTM poseBipTransforms totalStartF midpointFrame
                        midpointTargetBipTM = RMTool_Proxy_OffsetTM midpointTargetBipTM customOffset
                        local midpointSourceBipDet = RMTool_ADV_MatrixDet3 midpointSourceBipTM
                        if (abs midpointSourceBipDet) < 0.00000001 do throw ("ProxyRoot midpoint source Bip transform is singular at frame " + (currentFrame as string))
                        local midpointInverseSourceBipTM = inverse midpointSourceBipTM
                        for i = 1 to sourceNodes.count do
                        (
                            if RMTool_Proxy_IsDescendantOrSelf sourceNodes[i] poseBranchRoot then
                                midpointTargetWorldTMs[i] = midpointSourceWorldTMs[i] * midpointInverseSourceBipTM * midpointTargetBipTM
                        )
                        midpointTargetWorldTMs = RMTool_Proxy_ApplyPoseTranslationInfluences midpointSourceWorldTMs midpointTargetWorldTMs midpointSourceBipTM midpointTargetBipTM sourceNodes parentIndices poseBranchRoot externalPoseBodyRoots externalPoseConstraintDescriptors midpointFrame
                    )
                    local midpointRigidWorldTMs = #()
                    for tm in midpointTargetWorldTMs do append midpointRigidWorldTMs (RMTool_Backend_TMNoScale tm)
                    for i = 1 to proxyNodes.count do
                    (
                        currentNodeName = sourceNodes[i].name
                        local parentIndex = parentIndices[i]
                        local expectedMidLocalTM = if parentIndex > 0 then (midpointRigidWorldTMs[i] * (inverse midpointRigidWorldTMs[parentIndex])) else (copy midpointRigidWorldTMs[i])
                        expectedMidLocalTM = RMTool_Backend_TMNoScale expectedMidLocalTM
                        local expectedNoFlipLocalTM = RMTool_Proxy_InterpolateTM bakedLocalTargets[sampleIndex + 1][i] bakedLocalTargets[sampleIndex + 2][i] 0.5
                        local actualMidLocalTM = try (RMTool_Backend_TMNoScale (copy proxyNodes[i].transform.controller.value)) catch (undefined)
                        if actualMidLocalTM == undefined do throw ("ProxyRoot midpoint Local TM unavailable. node=" + currentNodeName + " frame=" + (currentFrame as string))
                        local sourceMidpointAxisError = RMTool_ADV_MatrixAxisError actualMidLocalTM expectedMidLocalTM
                        if sourceMidpointAxisError > maxSourceMidpointLocalAxisError do
                        (
                            maxSourceMidpointLocalAxisError = sourceMidpointAxisError
                            worstSourceMidpointNodeName = currentNodeName
                            worstSourceMidpointFrame = currentFrame
                        )
                        local midpointAxisError = RMTool_ADV_MatrixAxisError actualMidLocalTM expectedNoFlipLocalTM
                        if midpointAxisError > maxMidpointLocalAxisError do
                        (
                            maxMidpointLocalAxisError = midpointAxisError
                            worstMidpointNodeName = currentNodeName
                            worstMidpointFrame = currentFrame
                        )
                    )
                )
            )
        )
        RMTool_Proxy_Log ("phase midpointContinuityValidation ms=" + ((timeStamp() - phaseTimestamp) as string)); phaseTimestamp = timeStamp()

        local criticalGateFailed = maxRootPositionError > criticalPositionTolerance or maxRootAxisError > criticalAxisTolerance or maxBipPositionError > criticalPositionTolerance or maxBipAxisError > criticalAxisTolerance
        local hierarchyGateFailed = maxHierarchyPositionRatio > 1.0 or maxAxisError > hierarchyAxisTolerance
        local continuityGateFailed = maxMidpointLocalAxisError > midpointLocalAxisTolerance
        if criticalGateFailed or hierarchyGateFailed or continuityGateFailed do
        (
            local gateLabels = #()
            if criticalGateFailed do append gateLabels "RootBip-critical"
            if hierarchyGateFailed do append gateLabels "hierarchy"
            if continuityGateFailed do append gateLabels "midpoint-continuity"
            append validationWarnings ("rigid/hierarchy/continuity gate [" + (RMTool_ADV_JoinStrings gateLabels "+") + "] failed. worldPosNode=" + worstPositionNodeName + " worldPosFrame=" + (worstPositionFrame as string) + " worldPosErr=" + (maxPositionError as string) + " hierarchyRatioNode=" + worstHierarchyRatioNodeName + " hierarchyRatioFrame=" + (worstHierarchyRatioFrame as string) + " hierarchyPosAllowed=" + (worstHierarchyPositionTolerance as string) + " hierarchyPosRatio=" + (maxHierarchyPositionRatio as string) + " worldAxisNode=" + worstAxisNodeName + " worldAxisFrame=" + (worstAxisFrame as string) + " worldAxisErr=" + (maxAxisError as string) + " rootPosErr=" + (maxRootPositionError as string) + " rootAxisErr=" + (maxRootAxisError as string) + " bipPosErr=" + (maxBipPositionError as string) + " bipAxisErr=" + (maxBipAxisError as string) + " eulerRatioNode=" + worstEulerRatioNodeName + " eulerRatioFrame=" + (worstEulerRatioFrame as string) + " eulerQuatRatio=" + (maxEulerQuatRatio as string) + " noFlipMidpointNode=" + worstMidpointNodeName + " noFlipMidpointFrame=" + (worstMidpointFrame as string) + " noFlipMidpointAxisErr=" + (maxMidpointLocalAxisError as string) + " sourceMidpointNode=" + worstSourceMidpointNodeName + " sourceMidpointFrame=" + (worstSourceMidpointFrame as string) + " sourceMidpointAxisErr=" + (maxSourceMidpointLocalAxisError as string) + " rigidWorldWriteSamples=" + (rigidWorldWriteSampleCount as string))
        )

        currentStage = "enforceInactiveUnitScale"
        local preservedScaleSourceNodes = for entry in preservedScaleContext collect entry[1]
        local inactiveUnitProxyNodes = #()
        for i = 1 to proxyNodes.count do if (findItem preservedScaleSourceNodes sourceNodes[i]) == 0 do append inactiveUnitProxyNodes proxyNodes[i]
        for proxyNode in inactiveUnitProxyNodes do
        (
            try (deleteKeys proxyNode.scale.controller #allKeys) catch ()
            animate off (proxyNode.scale = [1,1,1])
        )

        currentStage = "applyPreservedScale"
        RMTool_Proxy_ProgressUpdate 0.95 "写回缩放轨道..."
        -- Verified dense write: each frame is read back immediately after the
        -- write and self-healed at key level once if it deviates. The detailed
        -- result doubles as the diagnostics payload for the hard gate below.
        local preservedApplyDiagnostics = #(0, 0.0, "", 0, [0,0,0], [0,0,0], -1, "none")
        if RMTool_HideScale_ApplyToBakeNodesVerified != undefined then
        (
            preservedApplyDiagnostics = RMTool_HideScale_ApplyToBakeNodesVerified preservedScaleContext sourceNodes proxyNodes tolerance:0.0001
            preservedScaleAppliedCount = preservedApplyDiagnostics[1]
        )
        else
        (
            preservedScaleAppliedCount = RMTool_HideScale_ApplyToBakeNodes preservedScaleContext sourceNodes proxyNodes
        )
        if preservedScaleAppliedCount != preservedScaleContext.count do throw ("ProxyRoot preserved scale apply failed. applied=" + (preservedScaleAppliedCount as string) + " expected=" + (preservedScaleContext.count as string) + " node=" + (preservedApplyDiagnostics[3] as string) + " frame=" + (preservedApplyDiagnostics[4] as string) + " actual=" + (preservedApplyDiagnostics[5] as string) + " expected=" + (preservedApplyDiagnostics[6] as string) + " keys=" + (preservedApplyDiagnostics[7] as string) + " ctrl=" + (preservedApplyDiagnostics[8] as string))

        -- Decompose the retained full source world matrix through the normalized
        -- FBX hierarchy. This converts Max-only scale-inheritance behavior into
        -- portable local PRS keys: e.g. a no-inherit twist chain with repeated
        -- 1.155 source controllers becomes 1.155, 1.0, 1.0 in FBX while retaining
        -- the exact same world pose. Root/Bip keep their scale exclusion. Hidden
        -- zero-scale parent subtrees are skipped only at truly singular frames;
        -- legal near-zero values such as 0.01/0.001 are fully reconciled.
        currentStage = "reconcileScaledWorldTransforms"
        local scalePositionCompensatedSamples = 0
        for sampleIndex = 0 to totalSamples do
        (
            local frameIndex = sampleIndex + 1
            local sampleFrame = totalStartF + ((sampleIndex as float) / sampleMultiplier)
            local targetWorldTMs = bakedFullWorldTargets[frameIndex]
            currentFrame = sampleFrame
            at time sampleFrame animate on
            (
                local frameScaleSingular = #()
                for i = 1 to proxyNodes.count do append frameScaleSingular false
                for orderIndex = 1 to bakeOrder.count do
                (
                    local i = bakeOrder[orderIndex]
                    currentNodeName = sourceNodes[i].name
                    local parentIndex = parentIndices[i]
                    local parentSingular = parentIndex > 0 and frameScaleSingular[parentIndex]
                    local targetTM = targetWorldTMs[i]
                    local ownSingular = RMTool_Proxy_IsWorldTransformSingular targetTM
                    frameScaleSingular[i] = parentSingular or ownSingular
                    if not parentSingular do
                    (
                        local worldWriteOK = try
                        (
                            if i != 1 and i != bipIndex and not ownSingular do proxyNodes[i].transform = targetTM
                            -- BoneSys world-TM assignment can retain its length-
                            -- based child offset under non-uniform scale. Force the
                            -- world position last, after rotation/scale have been
                            -- decomposed, so the exported local Position cancels it.
                            proxyNodes[i].pos = targetTM.pos
                            true
                        )
                        catch (false)
                        if not worldWriteOK do throw ("ProxyRoot scaled world-transform reconciliation failed. node=" + currentNodeName + " frame=" + (currentFrame as string))
                        scalePositionCompensatedSamples += 1
                    )
                )
            )
        )
        -- Dense position keys must interpolate linearly between 30/60/120 Hz
        -- samples; auto Bezier tangents can otherwise reintroduce midpoint drift.
        for i = 1 to proxyNodes.count do
        (
            local positionAxisControllers = try (getXYZControllers proxyNodes[i].position.controller) catch (undefined)
            if positionAxisControllers != undefined do for axisController in positionAxisControllers do for keyIndex = 1 to (numKeys axisController) do
            (
                local positionKey = getKey axisController keyIndex
                try (positionKey.inTangentType = #linear) catch ()
                try (positionKey.outTangentType = #linear) catch ()
            )
        )

        -- Full-TM decomposition can create dense Scale keys whose only content
        -- is floating-point noise around [1,1,1]. Drop a track only when every
        -- final sample stays within the same numerical-unit epsilon used during
        -- source capture. Real 0.98/0.3/visibility/animated scale remains keyed.
        currentStage = "pruneConvertedUnitScaleTracks"
        local convertedUnitScalePrunedCount = 0
        local convertedUnitScaleEpsilon = 0.00001
        for i = 1 to proxyNodes.count where i != 1 and i != bipIndex do
        (
            currentNodeName = sourceNodes[i].name
            local scaleCtrl = try (proxyNodes[i].scale.controller) catch (undefined)
            if scaleCtrl != undefined do
            (
                local maxConvertedScaleDeviation = 0.0
                for sampleIndex = 0 to totalSamples while maxConvertedScaleDeviation <= convertedUnitScaleEpsilon do
                (
                    local sampleFrame = totalStartF + ((sampleIndex as float) / sampleMultiplier)
                    local convertedScale = at time sampleFrame (try (copy scaleCtrl.value) catch (undefined))
                    if convertedScale == undefined then maxConvertedScaleDeviation = 999999.0
                    else
                    (
                        local convertedDeviation = RMTool_Proxy_ScaleAxisError convertedScale [1,1,1]
                        if convertedDeviation > maxConvertedScaleDeviation do maxConvertedScaleDeviation = convertedDeviation
                    )
                )
                if maxConvertedScaleDeviation <= convertedUnitScaleEpsilon do
                (
                    try (deleteKeys scaleCtrl #allKeys) catch ()
                    animate off (scaleCtrl.value = [1,1,1])
                    convertedUnitScalePrunedCount += 1
                )
            )
        )

        currentStage = "postScaleHardValidation"
        local worstPreservedScaleActual = [0,0,0]
        local worstPreservedScaleExpected = [0,0,0]
        local maxPostScaleWorldPositionError = 0.0
        local worstPostScaleWorldPositionNodeName = ""
        local worstPostScaleWorldPositionFrame = totalStartF
        local maxPostScaleWorldAxisError = 0.0
        local worstPostScaleWorldAxisNodeName = ""
        local worstPostScaleWorldAxisFrame = totalStartF
        local maxPostScaleWorldRowLengthError = 0.0
        local worstPostScaleWorldRowLengthNodeName = ""
        local worstPostScaleWorldRowLengthFrame = totalStartF
        local preservedSourceIndices = #()
        for entry in preservedScaleContext do append preservedSourceIndices (findItem sourceNodes entry[1])
        for entryIndex = 1 to preservedScaleContext.count do
        (
            local entry = preservedScaleContext[entryIndex]
            currentNodeName = entry[4]
            local sourceIndex = preservedSourceIndices[entryIndex]
            if sourceIndex <= 0 or sourceIndex > proxyNodes.count do throw ("ProxyRoot preserved-scale validation mapping missing: " + currentNodeName)
            local proxyScaleCtrl = try (proxyNodes[sourceIndex].scale.controller) catch (undefined)
            if proxyScaleCtrl == undefined do throw ("ProxyRoot preserved-scale validation controller missing: " + currentNodeName)
            for sampleIndex = 1 to entry[3].count do
            (
                currentFrame = entry[5] + sampleIndex - 1
                at time currentFrame
                (
                    -- Raw bookkeeping gate: proxy keyed FBX-local curve vs the
                    -- captured authored Scale controller value. Controllerless
                    -- helpers use the parent-relative matrix fallback captured
                    -- before the proxy hierarchy is built.
                    local proxyScale = try (copy proxyScaleCtrl.value) catch (undefined)
                    if proxyScale == undefined do throw ("ProxyRoot preserved-scale validation unavailable: " + currentNodeName + " frame=" + (currentFrame as string))
                    local sampleScale = entry[3][sampleIndex]
                    -- Raw Scale equality is meaningful only when Max and FBX use
                    -- the same parent-scale inheritance. For Max no-inherit nodes,
                    -- the portable FBX-local value is intentionally different and
                    -- the full world row-length gate below is authoritative.
                    local rawScaleMustMatch = parentIndices[sourceIndex] <= 0 or (sourceInheritanceFlags[sourceIndex][7] and sourceInheritanceFlags[sourceIndex][8] and sourceInheritanceFlags[sourceIndex][9])
                    local scaleError = if rawScaleMustMatch then (RMTool_Proxy_ScaleAxisError proxyScale sampleScale) else 0.0
                    if scaleError > maxPreservedScaleError do
                    (
                        maxPreservedScaleError = scaleError
                        worstPreservedScaleNodeName = currentNodeName
                        worstPreservedScaleFrame = currentFrame
                        worstPreservedScaleActual = proxyScale
                        worstPreservedScaleExpected = sampleScale
                    )
                )
            )
        )
        -- Validate the final, scaled hierarchy rather than the earlier rigid-only
        -- pose. This catches both scale accumulation and descendant position or
        -- axis changes caused by parent scale inheritance before FBX is written.
        for sampleIndex = 0 to totalSamples do
        (
            local frameIndex = sampleIndex + 1
            local sampleFrame = totalStartF + ((sampleIndex as float) / sampleMultiplier)
            -- Compare against the full source world matrices. bakedWorldTargets
            -- intentionally strips scale for the rigid rotation/position bake;
            -- using it here would reject every correctly restored non-unit scale
            -- (and can skew normalized BoneSys axes after non-uniform scaling).
            local targetWorldTMs = bakedFullWorldTargets[frameIndex]
            currentFrame = sampleFrame
            at time sampleFrame
            (
                local frameScaleSingular = #()
                for i = 1 to proxyNodes.count do append frameScaleSingular false
                for orderIndex = 1 to bakeOrder.count do
                (
                    local i = bakeOrder[orderIndex]
                    currentNodeName = sourceNodes[i].name
                    local parentIndex = parentIndices[i]
                    local parentSingular = parentIndex > 0 and frameScaleSingular[parentIndex]
                    -- Classify singularity from the expected source world matrix,
                    -- never from the current proxy local Scale. Otherwise a wrong
                    -- collapsed proxy could exempt itself from the hard gate.
                    local ownSingular = RMTool_Proxy_IsWorldTransformSingular targetWorldTMs[i]
                    frameScaleSingular[i] = parentSingular or ownSingular
                    local actualWorldTM = copy proxyNodes[i].transform
                    if not parentSingular do
                    (
                        local positionError = distance actualWorldTM.pos targetWorldTMs[i].pos
                        if positionError > maxPostScaleWorldPositionError do
                        (
                            maxPostScaleWorldPositionError = positionError
                            worstPostScaleWorldPositionNodeName = currentNodeName
                            worstPostScaleWorldPositionFrame = currentFrame
                        )
                    )
                    if not frameScaleSingular[i] and sourceRotationDefinedFrameFlags[frameIndex][i] do
                    (
                        local axisError = RMTool_Proxy_NormalizedWorldAxisError actualWorldTM targetWorldTMs[i]
                        if axisError > maxPostScaleWorldAxisError do
                        (
                            maxPostScaleWorldAxisError = axisError
                            worstPostScaleWorldAxisNodeName = currentNodeName
                            worstPostScaleWorldAxisFrame = currentFrame
                        )
                        local actualWorldRowLengths = point3 (length actualWorldTM.row1) (length actualWorldTM.row2) (length actualWorldTM.row3)
                        local targetWorldRowLengths = point3 (length targetWorldTMs[i].row1) (length targetWorldTMs[i].row2) (length targetWorldTMs[i].row3)
                        local rowLengthError = RMTool_Proxy_ScaleAxisError actualWorldRowLengths targetWorldRowLengths
                        if rowLengthError > maxPostScaleWorldRowLengthError do
                        (
                            maxPostScaleWorldRowLengthError = rowLengthError
                            worstPostScaleWorldRowLengthNodeName = currentNodeName
                            worstPostScaleWorldRowLengthFrame = currentFrame
                        )
                    )
                )
            )
        )
        if maxPreservedScaleError > 0.0001 do append validationWarnings ("preserved-scale gate failed. node=" + worstPreservedScaleNodeName + " frame=" + (worstPreservedScaleFrame as string) + " scaleErr=" + (maxPreservedScaleError as string) + " proxy=" + (worstPreservedScaleActual as string) + " sample=" + (worstPreservedScaleExpected as string) + " applyKeys=" + (preservedApplyDiagnostics[7] as string) + " applyCtrl=" + (preservedApplyDiagnostics[8] as string) + " applyWorstNode=" + (preservedApplyDiagnostics[3] as string) + " applyWorstErr=" + (preservedApplyDiagnostics[2] as string))
        if maxPostScaleWorldPositionError > criticalPositionTolerance or maxPostScaleWorldAxisError > hierarchyAxisTolerance or maxPostScaleWorldRowLengthError > 0.001 do
        (
            local diagnosticIndex = findItem sourceNames worstPostScaleWorldAxisNodeName
            if diagnosticIndex > 0 do at time worstPostScaleWorldAxisFrame
            (
                local diagnosticFrameIndex = (((worstPostScaleWorldAxisFrame - totalStartF) * sampleMultiplier) as integer) + 1
                RMTool_Proxy_Log ("post-scale diagnostic node=" + worstPostScaleWorldAxisNodeName + " frame=" + (worstPostScaleWorldAxisFrame as string) + " sourceTM=" + (bakedFullWorldTargets[diagnosticFrameIndex][diagnosticIndex] as string) + " proxyTM=" + (proxyNodes[diagnosticIndex].transform as string) + " sourceScale=" + ((try (sourceNodes[diagnosticIndex].scale.controller.value) catch (sourceNodes[diagnosticIndex].scale)) as string) + " proxyScale=" + ((try (proxyNodes[diagnosticIndex].scale.controller.value) catch (proxyNodes[diagnosticIndex].scale)) as string) + " sourceInherit=" + (sourceInheritanceFlags[diagnosticIndex] as string) + " proxyInherit=" + ((getInheritanceFlags proxyNodes[diagnosticIndex]) as string) + " sourceBoneEnable=" + ((try (sourceNodes[diagnosticIndex].boneEnable) catch (undefined)) as string) + " proxyBoneEnable=" + ((try (proxyNodes[diagnosticIndex].boneEnable) catch (undefined)) as string))
            )
            throw ("ProxyRoot post-scale world hard validation failed. worldPosNode=" + worstPostScaleWorldPositionNodeName + " worldPosFrame=" + (worstPostScaleWorldPositionFrame as string) + " worldPosErr=" + (maxPostScaleWorldPositionError as string) + " worldAxisNode=" + worstPostScaleWorldAxisNodeName + " worldAxisFrame=" + (worstPostScaleWorldAxisFrame as string) + " worldAxisErr=" + (maxPostScaleWorldAxisError as string) + " worldScaleNode=" + worstPostScaleWorldRowLengthNodeName + " worldScaleFrame=" + (worstPostScaleWorldRowLengthFrame as string) + " worldScaleErr=" + (maxPostScaleWorldRowLengthError as string)) debugBreak:false
        )
        RMTool_Proxy_Log ("phase scaleApplyAndValidation ms=" + ((timeStamp() - phaseTimestamp) as string)); phaseTimestamp = timeStamp()

        context = #(sourceNodes, proxyNodes, originalNames, proxyTempNames, parentIndices, bipIndex, totalStartF, totalEndF, maxPositionError, maxAxisError, maxBipPositionError, useAdvExport, sampleMultiplier, rigidWorldWriteSampleCount, preservedScaleAppliedCount, maxRootPositionError, maxRootAxisError, maxBipAxisError, maxHierarchyPositionRatio, maxEulerQuatRatio, maxMidpointLocalAxisError, maxSourceMidpointLocalAxisError, maxPreservedScaleError, resolvedMorphMeshes, validationWarnings, poseBranchIndex)
        RMTool_Proxy_Log ("built backend=" + RMTool_Proxy_BackendVersion + " nodes=" + (proxyNodes.count as string) + " frames=" + (totalStartF as string) + "-" + (totalEndF as string) + " samplesPerFrame=" + (sampleMultiplier as string) + " useAdv=" + (useAdvExport as string) + " poseBranch=" + (if poseBranchRoot != undefined then (poseBranchRoot.name as string) else "none") + " externalPoseConstraintNodes=" + (externalPoseConstraintLabels.count as string) + " worldPosErr=" + (maxPositionError as string) + " hierarchyPosRatio=" + (maxHierarchyPositionRatio as string) + " worldAxisErr=" + (maxAxisError as string) + " rootPosErr=" + (maxRootPositionError as string) + " rootAxisErr=" + (maxRootAxisError as string) + " bipPosErr=" + (maxBipPositionError as string) + " bipAxisErr=" + (maxBipAxisError as string) + " noFlipMidpointAxisErr=" + (maxMidpointLocalAxisError as string) + " sourceMidpointAxisErr=" + (maxSourceMidpointLocalAxisError as string) + " adaptiveEulerOrders=" + (nonXYZOrderCount as string) + " minGimbalMargin=" + (minimumSelectedGimbalMargin as string) + " maxDecomposeAxisErr=" + (maximumSelectedDecomposeAxisError as string) + " rigidWorldWriteSamples=" + (rigidWorldWriteSampleCount as string) + " scaleScannedNodes=" + (scaleScanStats[1] as string) + " preservedScaleNodes=" + (preservedScaleAppliedCount as string) + " controllerlessScaleSources=" + (controllerlessScaleSourceCount as string) + " prunedUnitScaleTracks=" + (convertedUnitScalePrunedCount as string) + " preservedScaleErr=" + (maxPreservedScaleError as string) + " scalePosWrites=" + (scalePositionCompensatedSamples as string) + " postScaleWorldPosErr=" + (maxPostScaleWorldPositionError as string) + " postScaleWorldAxisErr=" + (maxPostScaleWorldAxisError as string) + " postScaleWorldScaleErr=" + (maxPostScaleWorldRowLengthError as string) + " degenerateRotRepaired=" + (degenerateRotationRepairCount as string) + " validationWarnings=" + (validationWarnings.count as string))
        if maxPositionError > criticalPositionTolerance or maxAxisError > criticalAxisTolerance do RMTool_Proxy_Log ("secondary hierarchy numerical drift accepted worldPosNode=" + worstPositionNodeName + " frame=" + (worstPositionFrame as string) + " posErr=" + (maxPositionError as string) + " worldAxisNode=" + worstAxisNodeName + " frame=" + (worstAxisFrame as string) + " axisErr=" + (maxAxisError as string))
    )
    catch
    (
        local errorText = getCurrentException() as string
        try (delete proxyNodes) catch ()
        context = undefined
        RMTool_Proxy_Log ("build failed stage=" + currentStage + " node=" + currentNodeName + " frame=" + (currentFrame as string) + " error=" + errorText)
        if editingSuspended do try (resumeEditing()) catch ()
        if redrawDisabled do try (enableSceneRedraw()) catch ()
        try (setCommandPanelTaskMode oldTaskMode) catch ()
        try (select oldSelection) catch ()
        throw
    )

    if editingSuspended do try (resumeEditing()) catch ()
    if redrawDisabled do try (enableSceneRedraw()) catch ()
    try (setCommandPanelTaskMode oldTaskMode) catch ()
    try (select oldSelection) catch ()
    context
)

fn RMTool_Proxy_ExportContext context fbxPath startF endF totalOffset =
(
    if context == undefined do throw "ProxyRoot context missing"
    local sourceNodes = context[1]
    local proxyNodes = context[2]
    local originalNames = context[3]
    local proxyTempNames = context[4]
    local parentIndices = context[5]
    local useAdvExport = context[12]
    local sampleMultiplier = context[13]
    local bipIndex = context[6]
    local morphMeshes = if context.count >= 24 and context[24] != undefined then context[24] else #()
    if proxyNodes == undefined or proxyNodes.count == 0 do throw "ProxyRoot proxy hierarchy missing"

    local exportNames = #()
    for name in originalNames do
    (
        if useAdvExport then append exportNames (RMTool_ADV_ToCleanBakeExportName name)
        else append exportNames name
    )

    local duplicateExportPaths = RMTool_Proxy_FindDuplicateHierarchyPaths exportNames parentIndices
    if duplicateExportPaths.count > 0 do
    (
        -- Keep the full structural evidence in the Listener/log for TDs, but
        -- show artists one stable corrective message through the Qt caller.
        RMTool_Proxy_Log ("duplicate export hierarchy paths: " + (RMTool_ADV_JoinStrings duplicateExportPaths ", "))
        throw "绑定层级被修改，无法导出，请检查文件后重新尝试。" debugBreak:false
    )

    local oldSelection = getCurrentSelection()
    local tempSuffix = "__OPProxySource_" + ((random 100000 999999) as string)
    local conflictData = undefined
    local movedRoot = false
    local exportOK = false
    local errorText = ""
    local morphVisibilityState = #()
    local taskTransformContext = #()
    local liveDependencyTransformContext = #()
    try
    (
        conflictData = RMTool_ADV_TemporarilyFreeExportNames proxyNodes exportNames tempSuffix
        for i = 1 to proxyNodes.count do proxyNodes[i].name = exportNames[i]

        if totalOffset != undefined and (length totalOffset) > 0.001 do
        (
            animate off (move proxyNodes[1] totalOffset)
            movedRoot = true
        )

        local taskLocalModelNodes = for node in proxyNodes collect node
        for morphMesh in morphMeshes do if morphMesh != undefined and isValidNode morphMesh and (findItem taskLocalModelNodes morphMesh) == 0 do append taskLocalModelNodes morphMesh
        taskTransformContext = RMTool_Proxy_CaptureTaskLocalTransformControllers taskLocalModelNodes startF endF

        local liveDependencyNodes = RMTool_Proxy_CollectLiveSkinDependencyNodes morphMeshes excludedNodes:taskLocalModelNodes
        liveDependencyNodes = RMTool_Proxy_FilterCopyableTaskLocalTransformNodes liveDependencyNodes
        if liveDependencyNodes.count > 0 do
            liveDependencyTransformContext = RMTool_Proxy_CaptureTaskLocalTransformControllers liveDependencyNodes startF endF
        local taskLocalScaleNodes = for node in taskLocalModelNodes collect node
        for dependencyNode in liveDependencyNodes do if (findItem taskLocalScaleNodes dependencyNode) == 0 do append taskLocalScaleNodes dependencyNode

        -- Morpher meshes are exported as live geometry; the FBX exporter drops
        -- hidden/frozen nodes, so lift that state for the duration of the export.
        for m in morphMeshes do
        (
            if isValidNode m do
            (
                local mLayer = try (m.layer) catch (undefined)
                local layerHidden = if mLayer != undefined then (try (mLayer.isHidden) catch (false)) else false
                append morphVisibilityState #(m, m.isHidden, m.isFrozen, mLayer, layerHidden)
                if m.isHidden do m.isHidden = false
                if m.isFrozen do m.isFrozen = false
                if layerHidden do try (mLayer.isHidden = false) catch ()
            )
        )

        clearSelection()
        select proxyNodes
        if morphMeshes.count > 0 do selectMore morphMeshes
        local excludedScaleNodes = #(proxyNodes[1])
        if bipIndex > 0 and bipIndex <= proxyNodes.count and bipIndex != 1 do append excludedScaleNodes proxyNodes[bipIndex]
        RMTool_Proxy_ExportDenseWithHideScale taskLocalScaleNodes fbxPath startF endF sampleMultiplier excludedScaleNodes:excludedScaleNodes morphMeshes:morphMeshes taskLocalScale:true
        exportOK = true
    )
    catch (errorText = getCurrentException() as string)

    for st in morphVisibilityState do
    (
        try ( if isValidNode st[1] do (st[1].isHidden = st[2]; st[1].isFrozen = st[3]) ) catch ()
        try ( if st[4] != undefined and st[5] do st[4].isHidden = st[5] ) catch ()
    )
    local restoredLiveDependencyCount = RMTool_Proxy_RestoreTaskLocalTransformControllers liveDependencyTransformContext
    if restoredLiveDependencyCount != liveDependencyTransformContext.count do
    (
        local restoreLiveDependencyError = "ProxyRoot task-local live dependency restore failed: " + (restoredLiveDependencyCount as string) + "/" + (liveDependencyTransformContext.count as string)
        if errorText == "" then errorText = restoreLiveDependencyError else errorText += " | " + restoreLiveDependencyError
        exportOK = false
    )
    local restoredTaskTransformCount = RMTool_Proxy_RestoreTaskLocalTransformControllers taskTransformContext
    if restoredTaskTransformCount != taskTransformContext.count do
    (
        local restoreTransformError = "ProxyRoot task-local transform restore failed: " + (restoredTaskTransformCount as string) + "/" + (taskTransformContext.count as string)
        if errorText == "" then errorText = restoreTransformError else errorText += " | " + restoreTransformError
        exportOK = false
    )
    if movedRoot do try (animate off (move proxyNodes[1] (-totalOffset))) catch ()
    for i = 1 to proxyNodes.count do try (if isValidNode proxyNodes[i] do proxyNodes[i].name = proxyTempNames[i]) catch ()
    try (RMTool_ADV_RestoreTemporarilyFreedNames conflictData) catch ()
    try (select oldSelection) catch ()

    if not exportOK do
    (
        RMTool_Proxy_CleanupContext context
        throw ("ProxyRoot FBX export failed: " + errorText)
    )
    RMTool_Proxy_Log ("exported path=" + fbxPath + " frames=" + (startF as string) + "-" + (endF as string) + " offset=" + (totalOffset as string))
    true
)

fn RMTool_Proxy_CleanupContext context =
(
    if context == undefined do return false
    local proxyNodes = context[2]
    try (delete proxyNodes) catch ()
    true
)

-- Shared character FBX kernel for the official indoor/outdoor publisher.
-- Outdoor publishing supplies the live Root as the desired Root trajectory, so
-- no root-motion extraction or Biped write is performed.  The same ProxyRoot
-- hierarchy, adaptive Euler bake, scale preservation and FBX settings are used
-- by both modes; naming, multi-character iteration and camera export stay in
-- their existing Python pipelines.
fn RMTool_Proxy_RunInPlaceExport rootObj bipObj fbxPath startF endF proxySampleRate extraNodes:#() morphMeshes:#() autoMorph:false isBatch:false progressTitle:"" useAdvExport:false =
(
    if rootObj == undefined or (not isValidNode rootObj) do throw "ProxyRoot outdoor Root node missing" debugBreak:false
    if bipObj == undefined or (not isValidNode bipObj) do throw "ProxyRoot outdoor Bip node missing" debugBreak:false
    if fbxPath == undefined or fbxPath == "" do throw "ProxyRoot outdoor FBX path missing" debugBreak:false

    local s = startF as integer
    local e = endF as integer
    if e < s do throw ("ProxyRoot outdoor invalid frame range: " + (s as string) + "-" + (e as string)) debugBreak:false
    if proxySampleRate == undefined do proxySampleRate = 30
    proxySampleRate = proxySampleRate as integer
    if (findItem #(30, 60, 120) proxySampleRate) == 0 do throw ("ProxyRoot sample rate must be 30, 60, or 120 Hz; got " + (proxySampleRate as string)) debugBreak:false
    -- Match the official indoor contract. Never retime a cutscene silently:
    -- frame-numbered camera, split and event data would change meaning.
    if frameRate != 30 do throw ("ProxyRoot 发布要求 Max 场景为 30 FPS；当前为 " + (frameRate as string) + " FPS。请先在时间配置中改为 30 FPS，并重新检查镜头、事件和动画帧范围后再发布。") debugBreak:false

    if extraNodes == undefined do extraNodes = #()
    if morphMeshes == undefined do morphMeshes = #()
    local sampleMultiplier = (proxySampleRate / 30) as integer
    local titleText = if progressTitle != undefined and progressTitle != "" then progressTitle else (getFilenameFile fbxPath)
    local saveRequiredBefore = try (getSaveRequired()) catch (true)
    local proxyContext = undefined
    local exportOK = false
    local errorText = ""

    if RMTool_Proxy_ProgressShow != undefined do RMTool_Proxy_ProgressShow ("FBX 发布 - " + (titleText as string))
    if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.002 "清理上次发布残留..."

    try
    (
        if RMTool_Proxy_ScanAndCleanResidue != undefined do RMTool_Proxy_ScanAndCleanResidue()

        local sourceBipTransforms = #()
        local poseBipTransforms = #()
        local desiredRootTransforms = #()
        if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.012 "采样局外角色世界轨迹..."
        for f = s to e do at time f
        (
            append sourceBipTransforms (copy bipObj.transform)
            append desiredRootTransforms (copy rootObj.transform)
        )
        poseBipTransforms = for tm in sourceBipTransforms collect (copy tm)

        if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.015 "构建并校验 ProxyRoot..."
        proxyContext = RMTool_Proxy_CreateContext rootObj bipObj sourceBipTransforms poseBipTransforms desiredRootTransforms s e [0,0,0] false useAdvExport extraNodes sampleMultiplier morphMeshes:morphMeshes autoMorph:autoMorph
        if proxyContext == undefined do throw "ProxyRoot outdoor context build failed" debugBreak:false

        local validationWarnings = if proxyContext.count >= 25 and proxyContext[25] != undefined then proxyContext[25] else #()
        if validationWarnings.count > 0 do
        (
            local warningText = ""
            for w in validationWarnings do warningText += ("- " + (w as string) + "\n")
            RMTool_Proxy_Log ("outdoor numeric validation warnings (" + (validationWarnings.count as string) + "):\n" + warningText)
            if isBatch then
                throw ("ProxyRoot numeric validation failed; batch export aborted. Details:\n" + warningText) debugBreak:false
            else
            (
                local dialogText = "以下数值校验未通过：\n\n" + warningText + "\n仍要导出吗？（FBX 会照常导出，但可能包含姿态/缩放偏差；中止则清理临时骨骼且不产出文件）"
                local proceed = if RMTool_Proxy_TopMostQuery != undefined then (RMTool_Proxy_TopMostQuery dialogText "发布校验警告") else (queryBox dialogText title:"发布校验警告" beep:true)
                if not proceed do throw "Publish aborted by user after validation warning" debugBreak:false
                RMTool_Proxy_Log "outdoor user chose to export despite validation warnings"
            )
        )

        if RMTool_Proxy_ProgressUpdate != undefined do RMTool_Proxy_ProgressUpdate 0.97 ("写出局外角色 FBX：" + (getFilenameFile fbxPath) + " ...")
        RMTool_Proxy_ExportContext proxyContext fbxPath s e [0,0,0]
        exportOK = true
    )
    catch (errorText = getCurrentException() as string)

    if proxyContext != undefined do
    (
        try (RMTool_Proxy_CleanupContext proxyContext) catch ()
        proxyContext = undefined
    )
    if not saveRequiredBefore do try (setSaveRequired false) catch ()
    if RMTool_Proxy_ProgressHide != undefined do RMTool_Proxy_ProgressHide()

    if not exportOK do throw ("ProxyRoot outdoor export failed: " + errorText) debugBreak:false
    RMTool_Proxy_Log ("outdoor in-place export completed sampleRate=" + (proxySampleRate as string) + "Hz path=" + fbxPath)
    true
)

/*
    ADV scene Layer normalization core for Binding Update.
    Derived from ADV scene Layer batch organizer v0.3, without rollout/UI.

    Safety boundary:
    - Changes Layer membership and Layer Explorer parenting only.
    - Does not rename/delete scene nodes.
    - Does not modify node Parent, Transform, Controller, Wire, Reaction, or Skin.
    - Deletes only known legacy Layers after this tool has emptied them.
*/

global OP_RigLayerRefresh_Version = "0.3-integrated"
global OP_RigLayerRefresh_Log = #()
global OP_RigLayerRefresh_Failures = #()
global OP_RigLayerRefresh_LastResult = undefined

fn OP_RigLayerRefresh_isNode value =
(
    local result = false
    try (result = isValidNode value) catch()
    result
)

fn OP_RigLayerRefresh_lower value =
(
    local result = ""
    try (result = toLower (value as string)) catch()
    result
)

fn OP_RigLayerRefresh_appendLog textValue =
(
    append OP_RigLayerRefresh_Log textValue
)

fn OP_RigLayerRefresh_appendFailure textValue =
(
    append OP_RigLayerRefresh_Failures textValue
    OP_RigLayerRefresh_appendLog ("[失败] " + textValue)
)

fn OP_RigLayerRefresh_getLayer layerName createIfMissing:false =
(
    local result = undefined
    try (result = LayerManager.getLayerFromName layerName) catch()
    if result == undefined and createIfMissing do
    (
        try (result = LayerManager.newLayerFromName layerName) catch (result = undefined)
        if result == undefined do OP_RigLayerRefresh_appendFailure ("无法创建目标 Layer：" + layerName)
    )
    result
)

fn OP_RigLayerRefresh_getRole nodeValue =
(
    local result = ""
    try
    (
        local raw = getUserProp nodeValue "ADV_GenericFaceRole"
        if raw != undefined do result = raw as string
    )
    catch()
    result
)

fn OP_RigLayerRefresh_layerNodes layerName =
(
    local result = #()
    local sourceLayer = OP_RigLayerRefresh_getLayer layerName
    if sourceLayer != undefined do
        try (sourceLayer.nodes &result) catch
        (
            result = #()
            OP_RigLayerRefresh_appendFailure ("无法读取 Layer 节点：" + layerName)
        )
    result
)

fn OP_RigLayerRefresh_targetForRole roleValue =
(
    case roleValue of
    (
        "FixedUIControl": "UI"
        "PresetMaster": "UI"
        "MorpherMaster": "UI"

        "UILabel": "UI_Text"

        "FixedUIPanel": "UI_Frame"
        "PresetCategoryPanel": "UI_Frame"
        "PresetFrame": "UI_Frame"
        "PresetTrack": "UI_Frame"
        "MorpherPanel": "UI_Frame"
        "MorpherFrame": "UI_Frame"
        "MorpherTrack": "UI_Frame"

        "UIOffset": "UI_Helper"
        "UIOrient": "UI_Helper"
        "UIAnchor": "UI_Helper"
        "PresetAnchor": "UI_Helper"
        "MorpherAnchor": "UI_Helper"
        default: ""
    )
)

fn OP_RigLayerRefresh_isTextNode nodeValue =
(
    OP_RigLayerRefresh_lower (classOf nodeValue) == "text"
)

fn OP_RigLayerRefresh_isPointOrDummy nodeValue =
(
    local classText = OP_RigLayerRefresh_lower (classOf nodeValue)
    classText == "point" or classText == "dummy"
)

fn OP_RigLayerRefresh_isFrameNode nodeValue =
(
    local classText = OP_RigLayerRefresh_lower (classOf nodeValue)
    local nameText = OP_RigLayerRefresh_lower nodeValue.name
    classText == "rectangle" or
    matchPattern nameText pattern:"rectangle*" or
    matchPattern nameText pattern:"adv_*frame*" or
    matchPattern nameText pattern:"adv_*track*" or
    matchPattern nameText pattern:"*_bg_*" or
    matchPattern nameText pattern:"ui_track_*"
)

fn OP_RigLayerRefresh_isLegacyBSLayer layerName =
(
    local sourceLower = OP_RigLayerRefresh_lower layerName
    findItem #("bs_ui","变形控制器","mouth_ctrl","mouth_ui") sourceLower > 0
)

fn OP_RigLayerRefresh_bodyTarget nodeValue =
(
    local nameLower = OP_RigLayerRefresh_lower nodeValue.name
    local classLower = OP_RigLayerRefresh_lower (classOf nodeValue)

    if matchPattern nameLower pattern:"ctrl_bip*twist*" then return "Body_Ctrl"
    if classLower == "exposetm" and matchPattern nameLower pattern:"exposetm_twist_bip*" then return "Body_Helper"
    ""
)

fn OP_RigLayerRefresh_legacyUITarget nodeValue sourceLayerName =
(
    local bodyTarget = OP_RigLayerRefresh_bodyTarget nodeValue
    if bodyTarget != "" then return bodyTarget

    local roleTarget = OP_RigLayerRefresh_targetForRole (OP_RigLayerRefresh_getRole nodeValue)
    if roleTarget != "" then return roleTarget

    if OP_RigLayerRefresh_isTextNode nodeValue then return "UI_Text"
    if OP_RigLayerRefresh_isPointOrDummy nodeValue then return "UI_Helper"
    if OP_RigLayerRefresh_isFrameNode nodeValue then return "UI_Frame"

    local sourceLower = OP_RigLayerRefresh_lower sourceLayerName
    local classLower = OP_RigLayerRefresh_lower (classOf nodeValue)

    if OP_RigLayerRefresh_isLegacyBSLayer sourceLayerName do
    (
        if classLower == "circle" or classLower == "ngon" or classLower == "splineshape" or classLower == "line" then return "UI"
        return ""
    )

    if sourceLower == "yingcang_ctrl" do
    (
        if classLower == "line" then return "UI_Frame"
        if classLower == "ngon" or classLower == "circle" or classLower == "splineshape" then return "UI"
        return ""
    )

    if sourceLower == "ui" then "UI" else ""
)

fn OP_RigLayerRefresh_moveNode nodeValue targetLayerName applyChanges movedCounts =
(
    if not OP_RigLayerRefresh_isNode nodeValue or targetLayerName == "" then return false

    local currentLayerName = try (nodeValue.layer.name as string) catch ("")
    if OP_RigLayerRefresh_lower currentLayerName == OP_RigLayerRefresh_lower targetLayerName then return false

    if applyChanges do
    (
        local targetLayer = OP_RigLayerRefresh_getLayer targetLayerName createIfMissing:true
        if targetLayer == undefined then return false

        local moveOK = true
        try (targetLayer.addNode nodeValue) catch (moveOK = false)
        if not moveOK then
        (
            OP_RigLayerRefresh_appendFailure ("无法移动节点：" + nodeValue.name + " -> " + targetLayerName)
            return false
        )
    )

    local countIndex = case targetLayerName of
    (
        "Dum": 1
        "UI": 2
        "UI_Text": 3
        "UI_Frame": 4
        "UI_Helper": 5
        "Body_Ctrl": 6
        "Body_Helper": 7
        default: 0
    )
    if countIndex > 0 do movedCounts[countIndex] += 1
    true
)

fn OP_RigLayerRefresh_setLayerParent childLayer parentLayer childName parentName =
(
    if childLayer == undefined or parentLayer == undefined then return false
    local setOK = true
    try (if childLayer.getParent() != parentLayer do childLayer.setParent parentLayer) catch (setOK = false)
    if not setOK do OP_RigLayerRefresh_appendFailure ("无法设置 Layer 父级：" + childName + " -> " + parentName)
    setOK
)

fn OP_RigLayerRefresh_prepareTargetLayers applyChanges =
(
    if not applyChanges then return true

    local uiLayer = OP_RigLayerRefresh_getLayer "UI" createIfMissing:true
    local textLayer = OP_RigLayerRefresh_getLayer "UI_Text" createIfMissing:true
    local frameLayer = OP_RigLayerRefresh_getLayer "UI_Frame" createIfMissing:true
    local helperLayer = OP_RigLayerRefresh_getLayer "UI_Helper" createIfMissing:true
    local dumLayer = OP_RigLayerRefresh_getLayer "Dum" createIfMissing:true
    local no1ctrlLayer = OP_RigLayerRefresh_getLayer "no1ctrl" createIfMissing:true
    local faceHelperLayer = OP_RigLayerRefresh_getLayer "Face_Helper" createIfMissing:true

    OP_RigLayerRefresh_setLayerParent textLayer uiLayer "UI_Text" "UI"
    OP_RigLayerRefresh_setLayerParent frameLayer uiLayer "UI_Frame" "UI"
    OP_RigLayerRefresh_setLayerParent helperLayer uiLayer "UI_Helper" "UI"
    OP_RigLayerRefresh_setLayerParent dumLayer faceHelperLayer "Dum" "Face_Helper"
    OP_RigLayerRefresh_setLayerParent no1ctrlLayer faceHelperLayer "no1ctrl" "Face_Helper"

    local uiHidden = if uiLayer != undefined then uiLayer.isHidden else false
    try (uiLayer.isFrozen = false) catch()
    try (textLayer.isHidden = uiHidden; textLayer.isFrozen = true) catch()
    try (frameLayer.isHidden = uiHidden; frameLayer.isFrozen = true) catch()
    try (helperLayer.isHidden = true; helperLayer.isFrozen = true) catch()
    try (dumLayer.isHidden = true) catch()
    try (no1ctrlLayer.isHidden = true) catch()
    try (faceHelperLayer.isHidden = true) catch()
    true
)

fn OP_RigLayerRefresh_finalizeBodyLayers applyChanges =
(
    if not applyChanges then return true

    local bodyCtrlLayer = OP_RigLayerRefresh_getLayer "Body_Ctrl"
    local bodyHelperLayer = OP_RigLayerRefresh_getLayer "Body_Helper"
    if bodyCtrlLayer != undefined do
    (
        try (bodyCtrlLayer.isHidden = false) catch()
        try (bodyCtrlLayer.isFrozen = false) catch()
    )
    if bodyHelperLayer != undefined do
    (
        try (bodyHelperLayer.isHidden = true) catch()
        try (bodyHelperLayer.isFrozen = true) catch()
    )
    true
)

fn OP_RigLayerRefresh_deleteEmptyLegacyLayer layerName applyChanges =
(
    local oldLayer = OP_RigLayerRefresh_getLayer layerName
    if oldLayer == undefined then return 0

    local oldNodes = #()
    try (oldLayer.nodes &oldNodes) catch
    (
        OP_RigLayerRefresh_appendFailure ("无法读取旧 Layer：" + layerName)
        return 0
    )
    if oldNodes.count > 0 then
    (
        OP_RigLayerRefresh_appendLog ("[保留] 旧 Layer 仍有节点：" + layerName + " | " + oldNodes.count as string)
        return 0
    )

    if not applyChanges then return 1

    local deleted = false
    try (deleted = LayerManager.deleteLayerByName layerName) catch (deleted = false)
    if deleted then
    (
        OP_RigLayerRefresh_appendLog ("[删除空层] " + layerName)
        1
    )
    else
    (
        OP_RigLayerRefresh_appendFailure ("无法删除旧空 Layer：" + layerName)
        0
    )
)

fn OP_RigLayerRefresh_run applyChanges:true =
(
    OP_RigLayerRefresh_Log = #()
    OP_RigLayerRefresh_Failures = #()
    local movedCounts = #(0,0,0,0,0,0,0)
    local optionalCounts = #(0,0,0)
    local warnings = #()
    local deletedLayerCount = 0
    local processedNodes = #()

    OP_RigLayerRefresh_appendLog ("=== ADV Layer 整理 v" + OP_RigLayerRefresh_Version + " ===")
    OP_RigLayerRefresh_appendLog (if applyChanges then "模式：执行整理" else "模式：只分析")

    OP_RigLayerRefresh_prepareTargetLayers applyChanges

    for oldDumLayerName in #("上眼皮","下眼皮","眼睛","左右眼","眼角","眉毛") do
    (
        local oldDumNodes = OP_RigLayerRefresh_layerNodes oldDumLayerName
        for nodeValue in oldDumNodes do
            OP_RigLayerRefresh_moveNode nodeValue "Dum" applyChanges movedCounts
    )

    for nodeValue in objects where OP_RigLayerRefresh_isNode nodeValue do
    (
        local bodyTarget = OP_RigLayerRefresh_bodyTarget nodeValue
        if bodyTarget != "" do
        (
            OP_RigLayerRefresh_moveNode nodeValue bodyTarget applyChanges movedCounts
            appendIfUnique processedNodes nodeValue
        )
    )

    for nodeValue in objects where OP_RigLayerRefresh_isNode nodeValue do
    (
        local roleTarget = OP_RigLayerRefresh_targetForRole (OP_RigLayerRefresh_getRole nodeValue)
        if roleTarget != "" do
        (
            OP_RigLayerRefresh_moveNode nodeValue roleTarget applyChanges movedCounts
            appendIfUnique processedNodes nodeValue
        )
    )

    local sourceLayers = #("UI","层002","BS_UI","变形控制器","mouth_ctrl","mouth_UI","yingcang_ctrl")
    for sourceLayerName in sourceLayers do
    (
        local sourceNodes = OP_RigLayerRefresh_layerNodes sourceLayerName
        if OP_RigLayerRefresh_isLegacyBSLayer sourceLayerName do optionalCounts[1] += sourceNodes.count
        if OP_RigLayerRefresh_lower sourceLayerName == "yingcang_ctrl" do optionalCounts[2] = sourceNodes.count
        if sourceLayerName == "层002" do optionalCounts[3] = sourceNodes.count

        for nodeValue in sourceNodes do
        (
            if findItem processedNodes nodeValue == 0 do
            (
                local targetName = if sourceLayerName == "层002" then "UI_Helper" else OP_RigLayerRefresh_legacyUITarget nodeValue sourceLayerName
                if targetName != "" then
                (
                    OP_RigLayerRefresh_moveNode nodeValue targetName applyChanges movedCounts
                    appendIfUnique processedNodes nodeValue
                )
                else
                    append warnings (sourceLayerName + " | " + nodeValue.name + " | " + ((classOf nodeValue) as string))
            )
        )
    )

    OP_RigLayerRefresh_finalizeBodyLayers applyChanges

    OP_RigLayerRefresh_appendLog ("Dum 合并：" + movedCounts[1] as string)
    OP_RigLayerRefresh_appendLog ("UI 动画控件：" + movedCounts[2] as string)
    OP_RigLayerRefresh_appendLog ("UI 文字：" + movedCounts[3] as string)
    OP_RigLayerRefresh_appendLog ("UI 外框/轨道：" + movedCounts[4] as string)
    OP_RigLayerRefresh_appendLog ("UI 内部节点：" + movedCounts[5] as string)
    OP_RigLayerRefresh_appendLog ("身体动画控件纠正：" + movedCounts[6] as string)
    OP_RigLayerRefresh_appendLog ("身体辅助节点纠正：" + movedCounts[7] as string)
    OP_RigLayerRefresh_appendLog ("检测到旧 BS UI 节点：" + optionalCounts[1] as string)
    OP_RigLayerRefresh_appendLog ("检测到显隐 UI 节点：" + optionalCounts[2] as string)
    OP_RigLayerRefresh_appendLog ("检测到旧层002节点：" + optionalCounts[3] as string)

    if warnings.count > 0 then
    (
        OP_RigLayerRefresh_appendLog ("未分类节点：" + warnings.count as string)
        for warningText in warnings do OP_RigLayerRefresh_appendLog ("  " + warningText)
    )
    else
        OP_RigLayerRefresh_appendLog "未分类节点：0"

    for oldLayerName in #("上眼皮","下眼皮","眼睛","左右眼","眼角","眉毛","层002","BS_UI","变形控制器","mouth_ctrl","mouth_UI","yingcang_ctrl") do
        deletedLayerCount += OP_RigLayerRefresh_deleteEmptyLegacyLayer oldLayerName applyChanges

    OP_RigLayerRefresh_appendLog ("删除废弃空 Layer：" + deletedLayerCount as string)
    OP_RigLayerRefresh_appendLog "=== 完成 ==="

    OP_RigLayerRefresh_LastResult = #(movedCounts,optionalCounts,warnings,OP_RigLayerRefresh_Log,deletedLayerCount,OP_RigLayerRefresh_Failures)
    OP_RigLayerRefresh_LastResult
)

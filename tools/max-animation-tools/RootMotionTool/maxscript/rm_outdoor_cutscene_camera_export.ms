-- 局外 Timeline 相机导出：与 RootMotionExporterTool.ms FinalizeExport 中
-- chk_expTimelineCam + camNodesWorld 分支一致（世界空间烘焙 + 001 命名 + FBX）。
-- 由 Python fileIn 后调用 RM_ExportOutdoorTimelineCamera <完整fbx路径> <startF> <endF>

fn _RM_OCC_getAllDescendants rootNode =
(
    local result = #()
    if isValidNode rootNode do (
        local stack = #(rootNode)
        while stack.count > 0 do (
            local curr = stack[stack.count]
            stack.count = stack.count - 1
            for c in curr.children do (
                append stack c
                append result c
            )
        )
    )
    return result
)

global RM_ExportOutdoorTimelineCamera
fn RM_ExportOutdoorTimelineCamera fbxPath s e =
(
    local targetCam = getNodeByName "Main_Camera"
    if targetCam == undefined do return false

    local origRange = animationRange
    animationRange = interval s e

    local nodesToClone = #(targetCam)
    join nodesToClone (_RM_OCC_getAllDescendants targetCam)

    local origCamNames = #()
    for n in nodesToClone do append origCamNames n.name

    local camNodesWorld = #()
    maxOps.CloneNodes nodesToClone cloneType:#copy newNodes:&camNodesWorld offset:[0,0,0] expandHierarchy:false

    if camNodesWorld.count == 0 then (
        animationRange = origRange
        return false
    )

    local bakedRoot = camNodesWorld[1]
    bakedRoot.parent = undefined
    try ( bakedRoot.position.controller = Position_XYZ() ) catch()
    try ( bakedRoot.rotation.controller = Euler_XYZ() ) catch()

    animate on (
        for t = s to e do at time t (
            local tm = targetCam.transform
            local p = tm.row4
            local v1 = normalize tm.row1
            local v2 = normalize tm.row2
            local v3 = normalize tm.row3
            bakedRoot.transform = matrix3 v1 v2 v3 p
        )
    )

    for k = 1 to camNodesWorld.count do camNodesWorld[k].name = origCamNames[k] + "001"
    select camNodesWorld

    FBXExporterSetParam "Animation" true
    FBXExporterSetParam "BakeAnimation" true
    FBXExporterSetParam "BakeFrameStart" s
    FBXExporterSetParam "BakeFrameEnd" e
    FBXExporterSetParam "Cameras" true
    FBXExporterSetParam "UpAxis" "Y"
    FBXExporterSetParam "ShowWarnings" false
    exportFile fbxPath #noPrompt selectedOnly:true using:FBXEXP

    delete camNodesWorld
    animationRange = origRange
    true
)

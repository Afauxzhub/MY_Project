/*
手动：对选中物体把缩放重键为 Bezier Scale 因子（与 clean-bake 发布规则一致）。
发布管线已对临时骨自动执行同等逻辑；本脚本仅供排查/手工修复场景。

用法：选中骨骼 → fileIn 本脚本 → 确认后执行。
*/

global OP_RMTool_RebakeNodeScaleAsFactor
global OP_RMTool_RebakeSelectedScaleForFbx

fn OP_RMTool_RebakeNodeScaleAsFactor bakeNode sourceNode s e =
(
    if bakeNode == undefined or sourceNode == undefined do return false
    if (not isValidNode bakeNode) or (not isValidNode sourceNode) do return false

    local samples = #()
    local t
    for t = s to e do at time t
    (
        -- Prefer baked/local node scale; sourceNode may equal bakeNode for manual use.
        append samples bakeNode.scale
    )
    if samples.count == 0 do return false

    local ctrlOk = false
    try (bakeNode.scale.controller = bezier_scale(); ctrlOk = true) catch()
    if not ctrlOk do try (bakeNode.scale.controller = Bezier_Scale(); ctrlOk = true) catch()
    if not ctrlOk do
    (
        local curClass = try(classOf bakeNode.scale.controller)catch(undefined)
        if curClass == bezier_scale or curClass == Bezier_Scale then ctrlOk = true
        else
        (
            format "[rebake_scale_for_fbx] bezier_scale failed on % class=%\n" bakeNode.name curClass
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

fn OP_RMTool_RebakeSelectedScaleForFbx s: e: =
(
    local startF = if s == unsupplied then (animationRange.start as integer) else (s as integer)
    local endF = if e == unsupplied then (animationRange.end as integer) else (e as integer)
    local nodes = selection as array
    if nodes.count == 0 do
    (
        messageBox "请先选中需要重烘焙缩放的骨骼/物体。" title:"rebake_scale_for_fbx"
        return 0
    )

    local fixedCount = 0
    disableSceneRedraw()
    try
    (
        local n
        for n in nodes where isValidNode n do
        (
            if OP_RMTool_RebakeNodeScaleAsFactor n n startF endF do
                fixedCount += 1
        )
    )
    catch
    (
        format "[rebake_scale_for_fbx] failed: %\n" (getCurrentException() as string)
    )
    enableSceneRedraw()
    redrawViews()

    format "[rebake_scale_for_fbx] rebaked % node(s) in %-%\n" fixedCount startF endF
    messageBox ("已重烘焙 " + (fixedCount as string) + " 个物体的缩放键（Bezier Scale / 因子）。") title:"rebake_scale_for_fbx"
    fixedCount
)

(
    if selection.count > 0 then
    (
        if queryBox "对当前选中物体重烘焙缩放键（Bezier Scale 因子，含 0.1 藏腿）？\n会修改当前场景，建议先另存。" title:"rebake_scale_for_fbx" then
            OP_RMTool_RebakeSelectedScaleForFbx()
    )
    else
    (
        format "[rebake_scale_for_fbx] loaded. Select nodes then run: OP_RMTool_RebakeSelectedScaleForFbx()\n"
    )
)

/*
诊断 Bone_Twist 缩放：对比 Max 百分比 / node.scale / affineParts / 控制器原始值。
用法：
  1. 打开 Role_Example_Skill02.max
  2. 选中 Bone_Twist_Bip001 R Calf_1（或不选则自动找 Calf_1 Twist）
  3. 拖入本脚本执行，或 MAXScript Listener 里 fileIn
*/
(
    fn findTwistCalfNodes =
    (
        local result = #()
        for o in objects where (isValidNode o) do
        (
            local n = o.name as string
            if (matchPattern n pattern:"*Twist*Calf_1*") do append result o
        )
        result
    )

    fn getScaleXYZFloats node =
    (
        local out = #(undefined, undefined, undefined)
        try
        (
            local sc = node.scale.controller
            if sc != undefined do
            (
                -- ScaleXYZ 常见子控制器名
                local names = #("X_Scale", "Y_Scale", "Z_Scale", "X Scale", "Y Scale", "Z Scale")
                for i = 1 to 3 do
                (
                    try (out[i] = sc[i].value) catch()
                )
                if out[1] == undefined do
                (
                    for i = 1 to names.count do
                    (
                        try
                        (
                            local subc = sc[names[i]]
                            if subc != undefined do
                            (
                                local idx = ((i - 1) / 2) + 1
                                if out[idx] == undefined do out[idx] = subc.value
                            )
                        )
                        catch()
                    )
                )
            )
        )
        catch()
        out
    )

    fn getAffineScale node =
    (
        local ap = undefined
        try (ap = affineParts node.transform) catch()
        if ap == undefined then undefined else ap.scale
    )

    local nodes = selection as array
    if nodes.count == 0 do nodes = findTwistCalfNodes()
    if nodes.count == 0 do
    (
        messageBox "未找到 Twist Calf_1 骨骼，请先选中目标骨骼。" title:"diagnose_twist_scale"
        return false
    )

    local s = (animationRange.start as integer)
    local e = (animationRange.end as integer)
    format "\n========== diagnose_twist_scale ==========\n"
    format "range % - %\n" s e
    try (format "systemUnitScale=% %\n" units.SystemScale units.SystemType) catch()
    try (format "displayUnit=%\n" units.DisplayType) catch()

    for node in nodes do
    (
        format "\n--- % ---\n" node.name
        try (format "class=% boneLength=% boneScaleType=%\n" (classof node) node.length node.boneScaleType) catch()
        format "frame | UI%~node.scale | ctrlXYZ | affineScale | scale*100 | ctrl/10 | ctrl/100\n"

        local maxNodeScale = [1,1,1]
        local maxCtrl = [100,100,100]
        for t = s to e do at time t
        (
            local ns = node.scale
            local ctrl = getScaleXYZFloats node
            local aff = getAffineScale node
            local cx = if ctrl[1] == undefined then 0 else ctrl[1]
            local cy = if ctrl[2] == undefined then 0 else ctrl[2]
            local cz = if ctrl[3] == undefined then 0 else ctrl[3]

            if abs (ns.x - 1.0) > 0.02 or abs (cx - 100.0) > 2.0 then
            (
                format "% | % | [% % %] | % | % | [% % %] | [% % %]\n" \
                    t ns cx cy cz aff (ns * 100.0) (cx/10.0) (cy/10.0) (cz/10.0) (cx/100.0) (cy/100.0) (cz/100.0)
            )
            if abs ns.x > abs maxNodeScale.x do maxNodeScale = ns
            if abs cx > abs maxCtrl.x do maxCtrl = [cx, cy, cz]
        )
        format "peak node.scale=%  peak ctrlXYZ=%\n" maxNodeScale maxCtrl
        format "HINT: FBX 正确值应约等于 node.scale（或 ctrl/100）。\n"
        format "      若导出 FBX ≈ ctrl*10 或 node.scale*1000，即命中本 bug。\n"
    )
    format "========== done ==========\n"
    true
)

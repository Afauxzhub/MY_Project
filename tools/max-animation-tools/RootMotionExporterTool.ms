-- =======================================================
-- Root Motion Tool v6.62607015 (普朗克究极版 - 纯净映射版 + 相机极速整合)
-- =======================================================

try(destroyDialog rlt_RM_Tool_v6_62607015)catch()

global rlt_RM_Tool_v6_62607015

fn smoothStep val = ( return val * val * (3 - 2 * val) )

fn isAllDigits str = (
    if str == "" do return false
    for k=1 to str.count do if (findString "0123456789" (substring str k 1)) == undefined do return false
    true
)

fn isVerStr str = (
    if str.count < 2 do return false
    if (toLower (substring str 1 1)) != "v" do return false
    isAllDigits (substring str 2 -1)
)

fn cleanStringNative rawName suffix =
(
    if rawName == undefined do return "Untitled"
    local outStr = ""
    local depth = 0
    for i = 1 to rawName.count do (
        local c = substring rawName i 1
        if c == "(" or c == "[" then depth += 1
        else if c == ")" or c == "]" then depth -= 1
        else if depth == 0 do outStr += c
    )
    rawName = outStr
    local cleanStr = ""
    local validChars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    for i = 1 to rawName.count do (
        local c = substring rawName i 1
        if (findString validChars c) != undefined then cleanStr += c else cleanStr += "_"
    )
    rawName = cleanStr
    local parts = filterString rawName "_"
    if parts.count == 0 do return "Untitled"
    local badSuffixes = #("ani", "animation", "bk", "blocking", "layout", "step", "wip", "final", "test", "demo", "bak", "copy", "v01", "v02", "v03", "01", "02")
    local cutIndex = parts.count
    while cutIndex > 0 do (
        local part = toLower parts[cutIndex]
        local shouldRemove = false
        if (findItem badSuffixes part) > 0 do shouldRemove = true
        if (isAllDigits parts[cutIndex]) do shouldRemove = true
        if (isVerStr parts[cutIndex]) do shouldRemove = true
        if part == "" do shouldRemove = true
        if shouldRemove then cutIndex -= 1 else exit
    )
    if cutIndex == 0 then return rawName + suffix
    local finalName = ""
    for i = 1 to cutIndex do ( finalName += parts[i]; if i < cutIndex do finalName += "_" )
    return finalName + suffix
)

fn fn_ProcessRootTrajectory rawPosList smoothStr inputThresCM =
(
    local count = rawPosList.count
    if count < 2 do return rawPosList
    local realThres = units.decodeValue ((inputThresCM as string) + "cm")
    local filteredList = deepCopy rawPosList
    if realThres > 0.00001 do
    (
        local currentAnchor = rawPosList[1]
        filteredList[1] = currentAnchor
        for i = 2 to count do
        (
            local dist = distance rawPosList[i] currentAnchor
            if dist < realThres then filteredList[i] = currentAnchor
            else ( filteredList[i] = rawPosList[i]; currentAnchor = rawPosList[i] )
        )
    )
    local smoothedList = deepCopy filteredList
    if smoothStr > 0 do
    (
        for i = 2 to (count - 1) do
        (
            local sumPos = [0,0,0]
            local sampleCount = 0.0
            local startK = i - smoothStr; local endK = i + smoothStr
            if startK < 1 do startK = 1; if endK > count do endK = count
            for k = startK to endK do ( sumPos += filteredList[k]; sampleCount += 1.0 )
            smoothedList[i] = sumPos / sampleCount
        )
    )
    smoothedList[1] = rawPosList[1]
    local targetEndPos = rawPosList[count]
    local currentEndPos = smoothedList[count]
    local totalErrorVec = targetEndPos - currentEndPos
    local frameDists = #(0.0)
    local totalMoveDist = 0.0
    for i = 2 to count do (
        local d = distance smoothedList[i] smoothedList[i-1]
        if d < 0.001 do d = 0.0
        append frameDists d
        totalMoveDist += d
    )
    local currentAccumDist = 0.0
    for i = 1 to count do (
        currentAccumDist += frameDists[i]
        local weight = 0.0
        if totalMoveDist > 0.0001 then ( weight = currentAccumDist / totalMoveDist )
        else ( weight = (i - 1) as float / ((count - 1) as float) )
        if i == count do weight = 1.0
        smoothedList[i] = smoothedList[i] + (totalErrorVec * weight)
    )
    return smoothedList
)

fn getAllDescendants rootNode =
(
    local result = #()
    if isValidNode rootNode do ( local stack = #(rootNode); while stack.count > 0 do ( local curr = stack[stack.count]; stack.count = stack.count - 1; for c in curr.children do ( append stack c; append result c ) ) )
    return result
)

fn autoDetectObjects = (
    local foundBip = undefined; local foundRoot = undefined
    foundRoot = getNodeByName "root" ignoreCase:true
    foundBip = getNodeByName "Bip001" ignoreCase:true
    if foundBip == undefined do ( for o in objects where classof o == Biped_Object and o.isRoot do ( foundBip = o; exit ) )
    return #(foundBip, foundRoot)
)

fn fn_GetParentFbxFolder pathStr =
(
    if pathStr == undefined or pathStr == "" do return ""
    local pathParts = filterString pathStr "\\"
    local parentPath = ""
    if pathParts.count > 1 then (
        for i = 1 to (pathParts.count - 1) do parentPath += pathParts[i] + "\\"
    ) else ( parentPath = pathStr )
    return (parentPath + "FBX\\")
)

rollout rlt_RM_Tool_v6_62607015 "Root Motion 工具 (v6.62607015 + Camera)" width:320 height:750
(
    -- ==================== 状态机全局变量 ====================
    local exportState = 0
    local state_origFileFullName = ""
    local state_origFilePath = ""
    local state_origFileName = ""
    local state_tempMaxFile = ""
    local state_isBatchMode = false

    local bipObj = undefined
    local rootObj = undefined
    local splitData = #()
    local isExpOpen = false
    local isPosOpen = false
    -- =======================================================

    button btn_reset "重置工具 / 清除状态机" pos:[10,10] width:300 height:30

    checkbox chk_manualPick "手动拾取对象" checked:false pos:[20,55]

    groupBox grp_setup "对象拾取" pos:[10,80] width:300 height:90 visible:false
    pickbutton btn_pickBip "拾取 Bip质心 (Bip001)" pos:[20,100] width:280 height:30 autoDisplay:true visible:false
    pickbutton btn_pickRoot "拾取 Root骨骼" pos:[20,135] width:280 height:30 autoDisplay:true visible:false

    checkbox chk_enablePos "启用位移根运动" checked:true pos:[20,80]

    button btn_togglePos "▼ 位移详细参数" pos:[10,105] width:300 height:25 visible:false
    groupBox grp_pos_settings "详细设置"pos:[10,135] width:300 height:100 visible:false

    checkbox chk_followX "X轴位移" checked:false pos:[25,175] width:60 visible:true
    checkbox chk_followY "Y轴位移" checked:true pos:[130,175] width:60 visible:true
    checkbox chk_followZ "Z轴位移" checked:false pos:[220,175] width:60 visible:true

    label lbl_zThres "离地判定:" pos:[25,202] visible:false
    spinner spn_zThres "" range:[0.0, 999.0, 50.0] type:#float fieldWidth:35 pos:[125,200] tooltip:"当前腾空段双脚最高点需超过此值，整段才计算Z轴跟随（过滤抬脚与缓冲）" visible:false
    label lbl_zWeight "位移比例:" pos:[170,202] visible:false
    spinner spn_zWeight "" range:[0.0, 1.0, 1.0] type:#float fieldWidth:35 pos:[245,200] tooltip:"1.0=完全跟随质心，0.5=只抬升一半高度" visible:false

    checkbox chk_zLimitRange "限制Z轴区间" pos:[40,225] visible:false tooltip:"勾选后，Z轴位移只在指定帧数区间内生效，区间外强制为0"
    spinner spn_zLimitStart "Start:" range:[-99999,99999,0] type:#integer fieldWidth:40 pos:[60,245] visible:false
    spinner spn_zLimitEnd "End:" range:[-99999,99999,100] type:#integer fieldWidth:40 pos:[140,245] visible:false

    checkbox chk_zHover "强制锁定滞空高度 (Z轴悬停)" checked:false pos:[40,265] visible:false tooltip:"针对空中连击段：强行抹平区间内的Z轴波动，将Root锁定在指定高度。"
    spinner spn_zHoverHeight "目标高度(cm): " range:[-99999.0, 99999.0, 150.0] type:#float fieldWidth:45 pos:[135, 285] visible:false
    spinner spn_zHoverStart "锁定区间 - Start: " range:[-99999, 99999, 10] type:#integer fieldWidth:40 pos:[145, 305] visible:false
    spinner spn_zHoverEnd " End: " range:[-99999, 99999, 30] type:#integer fieldWidth:40 pos:[230, 305] visible:false

    label lbl_offset "全局偏移:" pos:[25,200] visible:false
    spinner spn_offsetX "X:" range:[-99999.0, 99999.0, 0.0] type:#float fieldWidth:40 pos:[80,200] visible:false
    spinner spn_offsetY "Y:" range:[-99999.0, 99999.0, 0.0] type:#float fieldWidth:40 pos:[150,200] visible:false
    spinner spn_offsetZ "Z:" range:[-99999.0, 99999.0, 0.0] type:#float fieldWidth:40 pos:[220,200] visible:false

    checkbox chk_useSmooth "启用死区与平滑 (仅XY)" checked:false pos:[85,155] visible:false

    label lbl_filter "死区:" pos:[55,180] width:35 visible:false enabled:false
    spinner spn_filterVal "" range:[0.0, 9999.0, 10.0] type:#float fieldWidth:35 pos:[90,178] tooltip:"锚点锁定范围 (单位:cm)" visible:false enabled:false
    label lbl_smooth "平滑:" pos:[155,180] width:35 visible:false enabled:false
    spinner spn_smoothStr "" range:[0,20,1] type:#integer fieldWidth:30 pos:[190,178] tooltip:"强度" visible:false enabled:false

    checkbox chk_smoothLimitRange "限制平滑区间" pos:[40,225] visible:false enabled:false tooltip:"勾选后，死区与平滑仅在区间内生效"
    spinner spn_smoothLimitStart "Start:" range:[-99999,99999,0] type:#integer fieldWidth:40 pos:[60,245] visible:false enabled:false
    spinner spn_smoothLimitEnd "End:" range:[-99999,99999,100] type:#integer fieldWidth:40 pos:[140,245] visible:false enabled:false

    checkbox chk_posRmLimitRange "指定根运动区间" checked:false pos:[40,245] visible:false tooltip:"勾选后，位移根运动仅在指定帧区间内生效；区间外 Root 位移为 0（旋转根运动不受影响）。"
    spinner spn_posRmStart "位移区间 Start:" range:[-99999,99999,0] type:#integer fieldWidth:45 pos:[40,265] visible:false
    spinner spn_posRmEnd "End:" range:[-99999,99999,100] type:#integer fieldWidth:45 pos:[230,265] visible:false

    checkbox chk_enableRot "启用旋转根运动" checked:false pos:[20,220]
    checkbox chk_enableSplit "启用 动画拆分" checked:false pos:[20,240]

    -- === 全新拆分列表 UI ===
    groupBox grp_split "拆分控制台" pos:[10,265] width:300 height:260 visible:false
    label lbl_suffix "后缀:" pos:[25,195] visible:false
    edittext edt_suffix "" pos:[55,193] width:75 text:"Start" visible:false tooltip:"无需输入下划线"
    dropdownlist ddl_presets "" pos:[140,192] width:145 items:#("Start", "Loop", "End", "Process", "RiseStart", "Rise", "FallStart", "FallLoop", "BounceRise", "BounceFall", "BounceFallLoop", "Land", "LandLoop", "DownToIdleUp") visible:false
    spinner spn_segStart "Start:" pos:[50,225] fieldWidth:45 type:#integer range:[-99999,99999,0] visible:false
    spinner spn_segEnd "End:" pos:[170,225] fieldWidth:45 type:#integer range:[-99999,99999,100] visible:false
    button btn_addSeg "添加动画片段" pos:[40,255] width:100 visible:false
    button btn_delSeg "删除动画片段" pos:[160,255] width:100 visible:false
    label lbl_list "列表:" pos:[20,285] visible:false
    checkbox chk_showFullName "显示完整文件名" checked:false pos:[60,285] visible:false
    listbox lb_segments "" pos:[20,305] width:260 visible:false

    button btn_toggleExp "▼ 导出与高级设置" pos:[10,540] width:300 height:25

    -- 高级设置UI完全改为纵向单列排布
    groupBox grp_exp "高级设置" pos:[10,570] width:300 height:140 visible:false
    checkbox chk_forceKeys "强制首尾K帧" checked:true pos:[20,590] visible:false
    checkbox chk_fixRot "Root预设归零" checked:true pos:[20,610] width:200 visible:false
    checkbox chk_removeInitialZ "剔除初始悬空高度" checked:true pos:[20,630] visible:false
    checkbox chk_deleteTemp "导出完成退回源文件并删除临时副本" checked:true pos:[20,650] visible:false
    checkbox chk_unlock "自动解冻/取消隐藏" checked:true pos:[20,670] visible:false

    -- 相机导出选项单列排布
    checkbox chk_expTimelineCam "导出 Timeline 相机" checked:false pos:[20,690] visible:false tooltip:"同时导出一份世界坐标的 _Cam_CS"
    checkbox chk_expIngameCam "导出 局内相机" checked:false pos:[20,710] visible:false tooltip:"同时导出一份相对 Root 的 _Cam"
    checkbox chk_onlyCam "仅导出相机动画" checked:false pos:[20,730] visible:false tooltip:"勾选后跳过角色模型导出"

    label lbl_previewName "预览: (未保存)" pos:[20,760] height:16 visible:false
    checkbox chk_openFolder "导出后打开文件夹" checked:true pos:[20,780] visible:false width:120
    button btn_openTarget "打开输出目录" pos:[160,778] width:100 height:22 visible:false

    button btn_export "开始导出 (FBX)" pos:[20,820] width:280 height:45
    button btn_cancelExport "取消操作并退回原文件" pos:[20,870] width:280 height:25 visible:false

    groupBox grp_batch "批量处理" pos:[10,905] width:300 height:60
    button btn_batch "选择文件夹并批量导出" pos:[20,925] width:280 height:30

    fn updateNamePreview = (
        local suffix = ""
        if splitData.count > 0 and splitData[1][1] != "" do suffix = "_" + splitData[1][1]
        lbl_previewName.text = "预览: " + (cleanStringNative (getFilenameFile maxFileName) suffix) + ".fbx"
    )

    fn refreshSegmentsList = (
        local items = #()
        local baseName = cleanStringNative (getFilenameFile maxFileName) ""
        for seg in splitData do (
            local segName = seg[1]; local s = seg[2]; local e = seg[3]
            local displayStr = ""
            local nameLabel = segName
            if nameLabel == "" do nameLabel = "(无后缀)"
            if chk_showFullName.checked then (
                local fullName = baseName
                if segName != "" do fullName += "_" + segName
                displayStr = fullName + "  [" + (s as string) + " ~ " + (e as string) + "]"
            )
            else displayStr = nameLabel + "  [" + (s as string) + " ~ " + (e as string) + "]"
            append items displayStr
        )
        lb_segments.items = items
    )

    fn autoDetect = (
        local found = autoDetectObjects()
        bipObj = found[1]; rootObj = found[2]
        if bipObj != undefined do btn_pickBip.text = "自动: " + bipObj.name
        if rootObj != undefined do btn_pickRoot.text = "自动: " + rootObj.name
    )

    fn updateLayout =
    (
        local isMan = chk_manualPick.checked
        local isPos = chk_enablePos.checked
        local isRot = chk_enableRot.checked
        local isSplit = chk_enableSplit.checked
        local curY = 80

        if isMan then (
            grp_setup.visible = true; grp_setup.pos = [10, curY]
            btn_pickBip.visible = true; btn_pickBip.pos = [20, curY+20]
            btn_pickRoot.visible = true; btn_pickRoot.pos = [20, curY+55]
            curY += 100
        ) else ( grp_setup.visible = false; btn_pickBip.visible = false; btn_pickRoot.visible = false )

        chk_enablePos.pos = [20, curY]; curY += 25

        if isPos then (
            btn_togglePos.visible = true; btn_togglePos.pos = [10, curY]; curY += 30
            if isPosOpen then (
                btn_togglePos.text = "▲ 位移详细参数"
                grp_pos_settings.visible = true; grp_pos_settings.pos = [10, curY]

                local innerY = curY + 20

                chk_followX.visible = true; chk_followX.pos = [20, innerY]; innerY += 20
                chk_followY.visible = true; chk_followY.pos = [20, innerY]; innerY += 20
                chk_followZ.visible = true; chk_followZ.pos = [20, innerY]; innerY += 20

                if chk_followZ.checked then (
                    lbl_zThres.visible = true; lbl_zThres.pos = [40, innerY+2]
                    spn_zThres.visible = true; spn_zThres.pos = [100, innerY]; innerY += 22

                    lbl_zWeight.visible = true; lbl_zWeight.pos = [40, innerY+2]
                    spn_zWeight.visible = true; spn_zWeight.pos = [100, innerY]; innerY += 22

                    chk_zLimitRange.visible = true; chk_zLimitRange.pos = [40, innerY]; innerY += 20
                    if chk_zLimitRange.checked then (
                        spn_zLimitStart.visible = true; spn_zLimitStart.pos = [120, innerY]
                        spn_zLimitEnd.visible = true; spn_zLimitEnd.pos = [220, innerY]; innerY += 22
                    ) else (
                        spn_zLimitStart.visible = false; spn_zLimitEnd.visible = false
                    )

                    chk_zHover.visible = true; chk_zHover.pos = [40, innerY]; innerY += 20
                    if chk_zHover.checked then (
                        spn_zHoverHeight.visible = true; spn_zHoverHeight.pos = [135, innerY]; innerY += 22
                        spn_zHoverStart.visible = true; spn_zHoverStart.pos = [145, innerY]
                        spn_zHoverEnd.visible = true; spn_zHoverEnd.pos = [230, innerY]; innerY += 22
                    ) else (
                        spn_zHoverHeight.visible = false
                        spn_zHoverStart.visible = false
                        spn_zHoverEnd.visible = false
                    )

                ) else (
                    lbl_zThres.visible = false; spn_zThres.visible = false; lbl_zWeight.visible = false; spn_zWeight.visible = false
                    chk_zLimitRange.visible = false; spn_zLimitStart.visible = false; spn_zLimitEnd.visible = false
                    chk_zHover.visible = false; spn_zHoverHeight.visible = false
                    spn_zHoverStart.visible = false; spn_zHoverEnd.visible = false
                )

                lbl_offset.visible = true; lbl_offset.pos = [20, innerY]; innerY += 20
                spn_offsetX.visible = true; spn_offsetX.pos = [90, innerY]
                spn_offsetY.visible = true; spn_offsetY.pos = [170, innerY]
                spn_offsetZ.visible = true; spn_offsetZ.pos = [250, innerY]; innerY += 22

                chk_useSmooth.visible = true; chk_useSmooth.pos = [20, innerY]; innerY += 22

                lbl_filter.visible = true; lbl_filter.pos = [40, innerY+2]
                spn_filterVal.visible = true; spn_filterVal.pos = [100, innerY]
                lbl_smooth.visible = true; lbl_smooth.pos = [160, innerY+2]
                spn_smoothStr.visible = true; spn_smoothStr.pos = [220, innerY]; innerY += 22

                chk_smoothLimitRange.visible = true; chk_smoothLimitRange.pos = [40, innerY]; innerY += 20
                if chk_smoothLimitRange.checked then (
                    spn_smoothLimitStart.visible = true; spn_smoothLimitStart.pos = [120, innerY]
                    spn_smoothLimitEnd.visible = true; spn_smoothLimitEnd.pos = [220, innerY]; innerY += 22
                ) else (
                    spn_smoothLimitStart.visible = false; spn_smoothLimitEnd.visible = false
                )

                chk_posRmLimitRange.visible = true; chk_posRmLimitRange.pos = [20, innerY]; innerY += 20
                if chk_posRmLimitRange.checked then (
                    spn_posRmStart.visible = true; spn_posRmStart.pos = [40, innerY]
                    spn_posRmEnd.visible = true; spn_posRmEnd.pos = [200, innerY]; innerY += 22
                ) else (
                    spn_posRmStart.visible = false; spn_posRmEnd.visible = false
                )

                grp_pos_settings.height = (innerY - curY + 5)
                curY = innerY + 15
            ) else (
                btn_togglePos.text = "▼ 位移详细参数"
                grp_pos_settings.visible = false; chk_useSmooth.visible = false
                lbl_filter.visible = false; spn_filterVal.visible = false; lbl_smooth.visible = false; spn_smoothStr.visible = false
                chk_followX.visible = false; chk_followY.visible = false; chk_followZ.visible = false
                lbl_zThres.visible = false; spn_zThres.visible = false; lbl_zWeight.visible = false; spn_zWeight.visible = false
                lbl_offset.visible = false; spn_offsetX.visible = false; spn_offsetY.visible = false; spn_offsetZ.visible = false
                chk_zLimitRange.visible = false; spn_zLimitStart.visible = false; spn_zLimitEnd.visible = false
                chk_smoothLimitRange.visible = false; spn_smoothLimitStart.visible = false; spn_smoothLimitEnd.visible = false
                chk_posRmLimitRange.visible = false; spn_posRmStart.visible = false; spn_posRmEnd.visible = false
                chk_zHover.visible = false; spn_zHoverHeight.visible = false
                spn_zHoverStart.visible = false; spn_zHoverEnd.visible = false
            )
        ) else (
            btn_togglePos.visible = false
            grp_pos_settings.visible = false; chk_useSmooth.visible = false
            lbl_filter.visible = false; spn_filterVal.visible = false; lbl_smooth.visible = false; spn_smoothStr.visible = false
            chk_followX.visible = false; chk_followY.visible = false; chk_followZ.visible = false
            lbl_zThres.visible = false; spn_zThres.visible = false; lbl_zWeight.visible = false; spn_zWeight.visible = false
            lbl_offset.visible = false; spn_offsetX.visible = false; spn_offsetY.visible = false; spn_offsetZ.visible = false
            chk_zLimitRange.visible = false; spn_zLimitStart.visible = false; spn_zLimitEnd.visible = false
            chk_smoothLimitRange.visible = false; spn_smoothLimitStart.visible = false; spn_smoothLimitEnd.visible = false
            chk_posRmLimitRange.visible = false; spn_posRmStart.visible = false; spn_posRmEnd.visible = false
            chk_zHover.visible = false; spn_zHoverHeight.visible = false
            spn_zHoverStart.visible = false; spn_zHoverEnd.visible = false
        )

        chk_enableRot.pos = [20, curY]; curY += 25
        chk_enableSplit.pos = [20, curY]; curY += 25

        if isSplit then (
            grp_split.visible = true; grp_split.pos = [10, curY]
            lbl_suffix.visible = true; lbl_suffix.pos = [25, curY + 25]
            edt_suffix.visible = true; edt_suffix.pos = [60, curY + 23]
            ddl_presets.visible = true; ddl_presets.pos = [145, curY + 22]
            spn_segStart.visible = true; spn_segStart.pos = [120, curY + 50]
            spn_segEnd.visible = true; spn_segEnd.pos = [230, curY + 50]
            btn_addSeg.visible = true; btn_addSeg.pos = [40, curY + 80]
            btn_delSeg.visible = true; btn_delSeg.pos = [160, curY + 80]
            lbl_list.visible = true; lbl_list.pos = [20, curY + 115]
            chk_showFullName.visible = true; chk_showFullName.pos = [60, curY + 115]
            lb_segments.visible = true; lb_segments.pos = [20, curY + 135]
            grp_split.height = 250; curY += 265
        ) else (
            grp_split.visible = false; lbl_suffix.visible = false; edt_suffix.visible = false; ddl_presets.visible = false
            spn_segStart.visible = false; spn_segEnd.visible = false; btn_addSeg.visible = false; btn_delSeg.visible = false
            lbl_list.visible = false; chk_showFullName.visible = false; lb_segments.visible = false
        )

        btn_toggleExp.pos = [10, curY]; curY += 30
        if isExpOpen then (
            btn_toggleExp.text = "▲ 导出与高级设置"
            grp_exp.visible = true; grp_exp.pos = [10, curY]

            -- 全局纵向单列排布：所有复选框保持 X = 20
            chk_forceKeys.visible = true; chk_forceKeys.pos = [20, curY+20]
            chk_fixRot.visible = true; chk_fixRot.pos = [20, curY+40]
            chk_removeInitialZ.visible = true; chk_removeInitialZ.pos = [20, curY+60]
            chk_deleteTemp.visible = true; chk_deleteTemp.pos = [20, curY+80]
            chk_unlock.visible = true; chk_unlock.pos = [20, curY+100]

            -- 相机选项紧随其后
            chk_expTimelineCam.visible = true; chk_expTimelineCam.pos = [20, curY+120]
            chk_expIngameCam.visible = true; chk_expIngameCam.pos = [20, curY+140]
            chk_onlyCam.visible = true; chk_onlyCam.pos = [20, curY+160]

            -- 预览和打开文件夹选项
            lbl_previewName.visible = true; lbl_previewName.pos = [20, curY+190]
            chk_openFolder.visible = true; chk_openFolder.pos = [20, curY+210]
            btn_openTarget.visible = true; btn_openTarget.pos = [160, curY+208]

            -- 自适应拉高组框
            grp_exp.height = 240; curY += 250
        ) else (
            btn_toggleExp.text = "▼ 导出与高级设置 (默认推荐)"
            grp_exp.visible = false; chk_forceKeys.visible = false
            chk_fixRot.visible = false; chk_deleteTemp.visible = false; chk_unlock.visible = false
            chk_removeInitialZ.visible = false
            chk_expTimelineCam.visible = false; chk_expIngameCam.visible = false; chk_onlyCam.visible = false
            lbl_previewName.visible = false; chk_openFolder.visible = false; btn_openTarget.visible = false
        )

        btn_export.pos = [20, curY + 10]
        btn_cancelExport.pos = [20, curY + 60]
        curY += 100
        grp_batch.pos = [10, curY]
        btn_batch.pos = [20, curY + 20]
        rlt_RM_Tool_v6_62607015.height = curY + 70
    )

    on chk_useSmooth changed state do (
        spn_smoothStr.enabled = state; spn_filterVal.enabled = state
        lbl_filter.enabled = state; lbl_smooth.enabled = state
        chk_smoothLimitRange.enabled = state
        spn_smoothLimitStart.enabled = state; spn_smoothLimitEnd.enabled = state
    )

    on chk_enablePos changed state do ( updateLayout() )
    on btn_togglePos pressed do ( isPosOpen = not isPosOpen; updateLayout() )
    on chk_followZ changed state do updateLayout()
    on chk_zLimitRange changed state do updateLayout()
    on chk_zHover changed state do updateLayout()
    on chk_smoothLimitRange changed state do updateLayout()
    on chk_posRmLimitRange changed state do updateLayout()
    on btn_toggleExp pressed do ( isExpOpen = not isExpOpen; updateLayout() )
    on ddl_presets selected itm do ( edt_suffix.text = ddl_presets.items[itm] )
    on chk_showFullName changed state do ( refreshSegmentsList() )

    on btn_openTarget pressed do (
        if maxFilePath == "" then messageBox "文件未保存，无法定位目录"
        else (
            local targetDir = fn_GetParentFbxFolder maxFilePath
            if doesFileExist targetDir then shellLaunch targetDir ""
            else (
                local parts = filterString maxFilePath "\\"
                if parts.count > 1 then (
                    local parent = ""
                    for i = 1 to (parts.count - 1) do parent += parts[i] + "\\"
                    if queryBox ("FBX文件夹不存在:\n" + targetDir + "\n\n打开父目录?") do shellLaunch parent ""
                ) else ( shellLaunch maxFilePath "" )
            )
        )
    )

    on btn_addSeg pressed do (
        local segName = edt_suffix.text
        if segName.count > 0 and segName[1] == "_" do segName = substring segName 2 -1
        local s = spn_segStart.value; local e = spn_segEnd.value
        if s >= e then (messageBox "开始帧必须小于结束帧"; return())
        append splitData #(segName, s, e)
        refreshSegmentsList()
        updateNamePreview()
        spn_segStart.value = e
    )

    on btn_delSeg pressed do (
        local idx = lb_segments.selection
        if idx > 0 do ( deleteItem splitData idx; refreshSegmentsList(); updateNamePreview() )
    )

    fn resetExportUIState = (
        exportState = 0
        state_origFileFullName = ""
        state_origFilePath = ""
        state_origFileName = ""
        state_tempMaxFile = ""
        state_isBatchMode = false
        btn_export.text = "开始导出 (FBX)"
        btn_cancelExport.visible = false
        grp_batch.enabled = true
    )

    fn resetTool = (
        resetExportUIState()
        bipObj = undefined; rootObj = undefined
        btn_pickBip.text = "拾取 Bip质心"; btn_pickRoot.text = "拾取 Root骨骼"
        chk_manualPick.checked = false; chk_enableRot.checked = false; chk_enableSplit.checked = false
        chk_enablePos.checked = true
        chk_useSmooth.checked = false; spn_smoothStr.value = 1; spn_filterVal.value = 10.0
        spn_offsetX.value = 0.0; spn_offsetY.value = 0.0; spn_offsetZ.value = 0.0
        isPosOpen = false
        chk_followX.checked = false; chk_followY.checked = true; chk_followZ.checked = false
        chk_zLimitRange.checked = false; chk_smoothLimitRange.checked = false
        chk_posRmLimitRange.checked = false
        chk_removeInitialZ.checked = true
        chk_zHover.checked = false

        -- 相机状态重置
        chk_expTimelineCam.checked = false
        chk_expIngameCam.checked = false
        chk_onlyCam.checked = false

        chk_enablePos.enabled = true; chk_enableRot.enabled = true
        splitData = #(); lb_segments.items = #()
        spn_segStart.value = animationRange.start; spn_segEnd.value = animationRange.end
        spn_zLimitStart.value = animationRange.start; spn_zLimitEnd.value = animationRange.end
        spn_smoothLimitStart.value = animationRange.start; spn_smoothLimitEnd.value = animationRange.end
        spn_posRmStart.value = animationRange.start; spn_posRmEnd.value = animationRange.end
        spn_zHoverStart.value = animationRange.start; spn_zHoverEnd.value = animationRange.end
        spn_zHoverHeight.value = 150.0
        spn_zThres.value = 50.0
        edt_suffix.text = "Start"
        autoDetect()
        updateNamePreview(); updateLayout()
    )

    on rlt_RM_Tool_v6_62607015 open do (
        autoDetect()
        spn_posRmStart.value = animationRange.start.frame as integer
        spn_posRmEnd.value = animationRange.end.frame as integer
        updateNamePreview(); updateLayout()
    )
    on btn_reset pressed do ( resetTool() )
    on chk_manualPick changed state do ( updateLayout() )
    on chk_enableRot changed state do ( updateLayout() )
    on chk_enableSplit changed state do ( updateLayout() )
    on btn_pickBip picked obj do ( if (classof obj == Biped_Object) then (bipObj = obj; btn_pickBip.text = "Bip: " + obj.name) else messageBox "请选择 Biped" )
    on btn_pickRoot picked obj do ( rootObj = obj; btn_pickRoot.text = "Root: " + obj.name; if classof obj.rotation.controller != Euler_XYZ do obj.rotation.controller = Euler_XYZ() )

    -- =======================================================
    -- [状态机 核心流程拆分]
    -- =======================================================
    fn FinalizeExport =
    (
        local totalStartF = animationRange.start.frame as integer
        local totalEndF = animationRange.end.frame as integer
        local exportTasks = #(); if chk_enableSplit.checked and splitData.count > 0 then exportTasks = splitData else append exportTasks #("", totalStartF, totalEndF)
        local originalRange = animationRange

        local finalFbxFolder = fn_GetParentFbxFolder state_origFilePath
        local useRootMotion = (chk_enablePos.checked or chk_enableRot.checked)

        if useRootMotion do (
            if classof rootObj.rotation.controller != Euler_XYZ do rootObj.rotation.controller = Euler_XYZ()
            if classof rootObj.position.controller != Position_XYZ do rootObj.position.controller = Position_XYZ()

            if chk_fixRot.checked do (
                local p = rootObj.pos
                local rx = rootObj.rotation.controller.x_rotation
                local ry = rootObj.rotation.controller.y_rotation
                local rz = rootObj.rotation.controller.z_rotation

                local needsFix = (distance p [0,0,0] > 0.01) or (abs(rx - 90.0) > 0.1) or (abs(ry) > 0.1) or (abs(rz) > 0.1)
                if needsFix do (
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
            local baseX = baseRot.x; local baseY = baseRot.y; local baseZ = baseRot.z

            local startOffset = (at time totalStartF bipObj.transform.pos)
            local originalTransforms = #()
            for i = totalStartF to totalEndF do ( at time i (append originalTransforms bipObj.transform) )

            deleteKeys rootObj.rotation.controller #allKeys
            deleteKeys rootObj.position.controller #allKeys
            try(deleteKeys rootObj.scale.controller #allKeys)catch()

            local rawRootPosList = #()

            if chk_enablePos.checked then (
                local lFoot = try(biped.getNode bipObj #lleg link:3)catch(undefined)
                local rFoot = try(biped.getNode bipObj #rleg link:3)catch(undefined)
                if lFoot == undefined do lFoot = bipObj
                if rFoot == undefined do rFoot = bipObj

                local hiddenFootThres = units.decodeValue "2.0cm"
                local jumpHeightThres = units.decodeValue ((spn_zThres.value as string) + "cm")

                local floorZ = 999999.0
                for i = totalStartF to totalEndF do (
                    local z1 = at time i lFoot.transform.pos.z
                    local z2 = at time i rFoot.transform.pos.z
                    if z1 < floorZ do floorZ = z1
                    if z2 < floorZ do floorZ = z2
                )

                local isGndArr_raw = #()
                local comZArr = #()
                local footMaxZArr = #()
                for i = totalStartF to totalEndF do (
                    local z1 = at time i lFoot.transform.pos.z
                    local z2 = at time i rFoot.transform.pos.z
                    local minFootZ = amin z1 z2
                    local grounded = minFootZ <= (floorZ + hiddenFootThres)
                    append isGndArr_raw grounded
                    append comZArr (at time i bipObj.transform.pos.z)
                    append footMaxZArr minFootZ
                )

                local isGndArr = deepCopy isGndArr_raw
                local i = 1
                while i <= isGndArr_raw.count do (
                    if isGndArr_raw[i] == false then (
                        local segStart = i
                        local segEnd = i
                        local maxZInSeg = footMaxZArr[i]

                        while (segEnd + 1 <= isGndArr_raw.count) and (isGndArr_raw[segEnd + 1] == false) do (
                            segEnd += 1
                            if footMaxZArr[segEnd] > maxZInSeg do maxZInSeg = footMaxZArr[segEnd]
                        )

                        if (maxZInSeg - floorZ) < jumpHeightThres do (
                            for k = segStart to segEnd do isGndArr[k] = true
                        )
                        i = segEnd + 1
                    ) else (
                        i += 1
                    )
                )

                -- 【步骤1：构建完全贴合的纯净轨迹】
                for i = 1 to originalTransforms.count do (
                    local originalTM = originalTransforms[i]
                    local tempPos = [0.0, 0.0, 0.0]
                    if chk_followX.checked do tempPos.x = originalTM.pos.x
                    if chk_followY.checked do tempPos.y = originalTM.pos.y
                    append rawRootPosList tempPos
                )

                if chk_useSmooth.checked do (
                    local idxStart = 1
                    local idxEnd = rawRootPosList.count

                    if chk_smoothLimitRange.checked do (
                        idxStart = spn_smoothLimitStart.value - totalStartF + 1
                        idxEnd = spn_smoothLimitEnd.value - totalStartF + 1
                        if idxStart < 1 do idxStart = 1
                        if idxEnd > rawRootPosList.count do idxEnd = rawRootPosList.count
                    )

                    if idxEnd > idxStart then (
                        local subList = for k = idxStart to idxEnd collect rawRootPosList[k]
                        local smoothedSubList = fn_ProcessRootTrajectory subList spn_smoothStr.value spn_filterVal.value
                        for k = 1 to smoothedSubList.count do (
                            rawRootPosList[idxStart + k - 1] = smoothedSubList[k]
                        )
                    )
                )

                for i = 1 to originalTransforms.count do (
                    local currentFrame = totalStartF + i - 1
                    if chk_followZ.checked then (
                        local inRange = true
                        if chk_zLimitRange.checked do (
                            if currentFrame < spn_zLimitStart.value or currentFrame > spn_zLimitEnd.value do inRange = false
                        )

                        if inRange then (
                            if isGndArr[i] then (
                                rawRootPosList[i].z = 0.0
                            ) else (
                                local refCOMZ = undefined
                                for j = i to 1 by -1 do if isGndArr[j] do ( refCOMZ = comZArr[j]; exit )
                                if refCOMZ == undefined do (
                                    for j = i to originalTransforms.count do if isGndArr[j] do ( refCOMZ = comZArr[j]; exit )
                                )
                                local calcZ = 0.0
                                if refCOMZ != undefined then calcZ = (comZArr[i] - refCOMZ) * spn_zWeight.value
                                else calcZ = (comZArr[i] - comZArr[1]) * spn_zWeight.value
                                if calcZ < 0.0 do calcZ = 0.0
                                rawRootPosList[i].z = calcZ
                            )
                        ) else (
                            rawRootPosList[i].z = 0.0
                        )
                    ) else (
                        rawRootPosList[i].z = 0.0
                    )
                )

                if chk_followZ.checked and chk_zHover.checked do (
                    local hoverTargetZ = units.decodeValue ((spn_zHoverHeight.value as string) + "cm")
                    local hoverStartF = spn_zHoverStart.value
                    local hoverEndF = spn_zHoverEnd.value
                    for i = 1 to originalTransforms.count do (
                        local currentFrame = totalStartF + i - 1
                        if currentFrame >= hoverStartF and currentFrame <= hoverEndF do (
                            rawRootPosList[i].z = hoverTargetZ
                        )
                    )
                )
                if chk_posRmLimitRange.checked do (
                    local ps = spn_posRmStart.value as integer
                    local pe = spn_posRmEnd.value as integer
                    if ps > pe do ( local tmp = ps; ps = pe; pe = tmp )
                    for i = 1 to rawRootPosList.count do (
                        local cf = totalStartF + i - 1
                        if cf < ps or cf > pe do rawRootPosList[i] = [0.0, 0.0, 0.0]
                    )
                )
            )

            local targetAngle = 0.0
            local rotStart = totalStartF
            local rotEnd = totalEndF
            local rotDuration = 1.0

            if chk_enableRot.checked do (
                local yawArr = #()
                local cumulativeYaw = 0.0
                local lastYaw = undefined
                for i = 1 to originalTransforms.count do (
                    local tm = originalTransforms[i]
                    local fwd = normalize [tm.row2.x, tm.row2.y, 0]
                    local currentYaw = atan2 fwd.y fwd.x
                    if lastYaw != undefined do (
                        local delta = currentYaw - lastYaw
                        if delta > 180.0 do delta -= 360.0
                        if delta < -180.0 do delta += 360.0
                        cumulativeYaw += delta
                    )
                    append yawArr cumulativeYaw
                    lastYaw = currentYaw
                )
                targetAngle = yawArr[yawArr.count]

                if abs(targetAngle) > 2.0 then (
                    local tStart = targetAngle * 0.05
                    local tEnd = targetAngle * 0.95
                    local sFound = false
                    for i = 1 to yawArr.count do (
                        if not sFound and (abs(yawArr[i]) >= abs(tStart)) do ( rotStart = totalStartF + i - 1; sFound = true )
                        if abs(yawArr[i]) <= abs(tEnd) do ( rotEnd = totalStartF + i - 1 )
                    )
                    if rotEnd <= rotStart do rotEnd = rotStart + 1
                    rotDuration = (rotEnd - rotStart) as float
                )
            )

            animate on (
                if chk_enableRot.checked then (
                    for i = totalStartF to totalEndF do (
                        sliderTime = i
                        local addedVal = 0.0
                        if i >= rotEnd then addedVal = targetAngle
                        else if i > rotStart then (
                            local prog = smoothStep (((i - rotStart) as float) / rotDuration)
                            addedVal = targetAngle * prog
                        )
                        rootObj.rotation.controller.x_rotation = baseX
                        rootObj.rotation.controller.y_rotation = baseY
                        rootObj.rotation.controller.z_rotation = baseZ + addedVal
                    )
                )
                for i = totalStartF to totalEndF do (
                    sliderTime = i
                    local idx = ((i - totalStartF) as integer) + 1
                    if chk_enablePos.checked and idx <= rawRootPosList.count do ( rootObj.pos = rawRootPosList[idx] )
                )
            )

            -- 【极速优化 1】：如果仅导出相机，跳过 Biped 的反向还原修复，极大节省计算时间
            if (chk_enableRot.checked or chk_enablePos.checked) and (not chk_onlyCam.checked) do (
                local bipCtrl = bipObj.controller
                local layerIdxRM = biped.numLayers bipCtrl + 1
                biped.createLayer bipCtrl layerIdxRM "RM_Fix"
                biped.setCurrentLayer bipCtrl layerIdxRM

                local customOffset = [spn_offsetX.value, spn_offsetY.value, spn_offsetZ.value]

                animate on (
                    for i = totalStartF to totalEndF do (
                        sliderTime = i
                        local idx = ((i - totalStartF) as integer) + 1
                        if idx <= originalTransforms.count do (
                            local targetTM = originalTransforms[idx]
                            biped.setTransform bipObj #pos (targetTM.pos + customOffset) true
                            biped.setTransform bipObj #rotation targetTM.rotation true
                        )
                    )
                )
            )
        )

        for task in exportTasks do (
            local taskName = task[1]; local s = task[2]; local e = task[3]
            animationRange = interval s e

            -- =======================================================
            -- [新增] 核心相机烘焙：在发生任何全场景偏移前执行，以抓取最纯净坐标
            -- =======================================================
            local targetCam = getNodeByName "Main_Camera"
            local camNodesWorld = #()
            local camNodesLocal = #()
            local origCamNames = #() -- 用于缓存相机的真实原名

            if (chk_expTimelineCam.checked or chk_expIngameCam.checked) and targetCam != undefined do (
                local nodesToClone = #(targetCam)
                join nodesToClone (getAllDescendants targetCam)

                -- 把所有原名记录下来
                for n in nodesToClone do append origCamNames n.name

                -- 烘焙 Timeline 相机 (世界坐标)
                if chk_expTimelineCam.checked do (
                    maxOps.CloneNodes nodesToClone cloneType:#copy newNodes:&camNodesWorld offset:[0,0,0] expandHierarchy:false

                    local bakedRoot = camNodesWorld[1]
                    bakedRoot.parent = undefined
                    try ( bakedRoot.position.controller = Position_XYZ() ) catch()
                    try ( bakedRoot.rotation.controller = Euler_XYZ() ) catch()

                    animate on (
                        for t = s to e do at time t (
                            local tm = targetCam.transform
                            local p = tm.row4
                            local v1 = normalize tm.row1, v2 = normalize tm.row2, v3 = normalize tm.row3
                            bakedRoot.transform = matrix3 v1 v2 v3 p
                        )
                    )
                )

                -- 烘焙 局内相机 (抵消 RootMotion 后的相对坐标)
                if chk_expIngameCam.checked do (
                    maxOps.CloneNodes nodesToClone cloneType:#copy newNodes:&camNodesLocal offset:[0,0,0] expandHierarchy:false

                    local bakedRoot = camNodesLocal[1]
                    bakedRoot.parent = undefined
                    try ( bakedRoot.position.controller = Position_XYZ() ) catch()
                    try ( bakedRoot.rotation.controller = Euler_XYZ() ) catch()

                    animate on (
                        for t = s to e do at time t (
                            local camTM = targetCam.transform
                            local rootTM = rootObj.transform

                            -- 抵消 Root 骨骼在 Max 里自带的 X 轴 90 度旋转
                            local virtualRootTM = preRotateX rootTM -90
                            local finalTM = camTM * (inverse virtualRootTM)

                            local p = finalTM.row4
                            local v1 = normalize finalTM.row1, v2 = normalize finalTM.row2, v3 = normalize finalTM.row3
                            bakedRoot.transform = matrix3 v1 v2 v3 p
                        )
                    )
                )
            )

            -- === 核心黑科技：全轴向智能首帧归零 & 入场特判 ===
            local tempXOffset = 0.0
            local tempYOffset = 0.0
            local tempZOffset = 0.0

            local rootStartPos = at time s rootObj.pos
            local rootEndPos = at time e rootObj.pos

            -- X轴跟随：默认归零
            if chk_followX.checked do tempXOffset = rootStartPos.x

            -- Y轴跟随：入场特判 (首帧负值，尾帧归零，则免除归零)
            if chk_followY.checked do (
                local isEntranceY = (rootStartPos.y < (units.decodeValue "-5.0cm")) and (abs(rootEndPos.y) < (units.decodeValue "5.0cm"))
                if not isEntranceY do tempYOffset = rootStartPos.y
            )

            -- Z轴跟随：剔除初始高度
            if chk_removeInitialZ.checked and chk_followZ.checked do (
                tempZOffset = rootStartPos.z
            )

            -- 合并偏移量并执行整体平移
            local totalOffset = [-tempXOffset, -tempYOffset, -tempZOffset]
            if (length totalOffset) > 0.001 do (
                animate off ( move rootObj totalOffset )
            )

            local actualTaskName = taskName
            if chk_enableSplit.checked and taskName != "" then actualTaskName = "_" + taskName
            local baseFbxName = cleanStringNative (getFilenameFile state_origFileName) actualTaskName
            local fbxFolder = fn_GetParentFbxFolder state_origFilePath
            makeDir fbxFolder

            -- =======================================================
            -- 1. 导出角色动作
            -- =======================================================
            if not chk_onlyCam.checked do (
                local objsToExport = #(rootObj)
                join objsToExport (getAllDescendants rootObj)

                if chk_unlock.checked do (
                    for o in objsToExport do (
                        if isValidNode o do (
                            if o.isFrozen do o.isFrozen = false
                            if o.isHidden do o.isHidden = false
                            local oLayer = o.layer
                            if oLayer != undefined do (
                                if oLayer.isHidden do oLayer.isHidden = false
                                if oLayer.isFrozen do oLayer.isFrozen = false
                            )
                        )
                    )
                )
                select objsToExport

                if chk_forceKeys.checked do (
                    local objectsToKey = #()
                    for o in objsToExport do (
                        if isValidNode o do (
                            local cls = classof o
                            if cls != Biped_Object then (
                                if cls == BoneGeometry or cls == Dummy or cls == Point or cls == Bone or o == rootObj do (
                                    append objectsToKey o
                                )
                            )
                        )
                    )

                    for o in objectsToKey do (
                        try(addNewKey o.pos.controller s)catch()
                        try(addNewKey o.rotation.controller s)catch()
                        try(addNewKey o.scale.controller s)catch()
                        try(addNewKey o.pos.controller e)catch()
                        try(addNewKey o.rotation.controller e)catch()
                        try(addNewKey o.scale.controller e)catch()
                    )
                )

                local charExportPath = fbxFolder + baseFbxName + ".fbx"
                FBXExporterSetParam "Animation" true; FBXExporterSetParam "BakeAnimation" true
                FBXExporterSetParam "BakeFrameStart" s; FBXExporterSetParam "BakeFrameEnd" e
                FBXExporterSetParam "UpAxis" "Y"; FBXExporterSetParam "ShowWarnings" false
                exportFile charExportPath #noPrompt selectedOnly:true using:FBXEXP
            )

            -- =======================================================
            -- 2. 导出刚刚烘焙完成的相机节点
            -- =======================================================
            if camNodesWorld.count > 0 do (
                -- 【重点卡位】：在导出前一刻赋予 001 后缀
                for k = 1 to camNodesWorld.count do camNodesWorld[k].name = origCamNames[k] + "001"

                select camNodesWorld
                local camExportPath = fbxFolder + baseFbxName + "_Cam_CS.fbx"

                FBXExporterSetParam "Animation" true; FBXExporterSetParam "BakeAnimation" true
                FBXExporterSetParam "BakeFrameStart" s; FBXExporterSetParam "BakeFrameEnd" e
                FBXExporterSetParam "Cameras" true; FBXExporterSetParam "UpAxis" "Y"; FBXExporterSetParam "ShowWarnings" false
                exportFile camExportPath #noPrompt selectedOnly:true using:FBXEXP

                -- 导出完成后立刻删除，彻底释放 001 的占位！
                delete camNodesWorld
            )

            if camNodesLocal.count > 0 do (
                -- 【重点卡位】：因为前面世界坐标的 001 已经被删了，所以这里放心用 001，绝不会被 Max 改成 002
                for k = 1 to camNodesLocal.count do camNodesLocal[k].name = origCamNames[k] + "001"

                select camNodesLocal
                local camExportPath = fbxFolder + baseFbxName + "_Cam.fbx"

                FBXExporterSetParam "Animation" true; FBXExporterSetParam "BakeAnimation" true
                FBXExporterSetParam "BakeFrameStart" s; FBXExporterSetParam "BakeFrameEnd" e
                FBXExporterSetParam "Cameras" true; FBXExporterSetParam "UpAxis" "Y"; FBXExporterSetParam "ShowWarnings" false
                exportFile camExportPath #noPrompt selectedOnly:true using:FBXEXP

                delete camNodesLocal
            )

            -- === 核心黑科技：导出完成后，无痕恢复现场！ ===
            if (length totalOffset) > 0.001 do (
                animate off ( move rootObj -totalOffset )
            )
        )
        animationRange = originalRange

        if chk_deleteTemp.checked or state_isBatchMode then (
            loadMaxFile state_origFileFullName quiet:true
            deleteFile state_tempMaxFile
            if not state_isBatchMode do (
                messageBox "导出完美完成！\n已自动切回原文件并无痕清理临时文件。"
                if chk_openFolder.checked and finalFbxFolder != "" do shellLaunch finalFbxFolder ""
            )
        ) else (
            if not state_isBatchMode do (
                messageBox "导出完成！\n\n【排错保留模式】\n你现在停留在 RM_Temp 副本文件中供检查位移表现。\n检查完毕后请手动打开你的原文件！"
                if chk_openFolder.checked and finalFbxFolder != "" do shellLaunch finalFbxFolder ""
            )
        )

        resetExportUIState()
    )

    on btn_cancelExport pressed do (
        loadMaxFile state_origFileFullName quiet:true
        deleteFile state_tempMaxFile
        resetExportUIState()
        messageBox "已取消本次导出并安全切回原文件。"
    )

    on btn_export pressed do (
        if exportState == 1 do (
            FinalizeExport()
            return OK
        )

        if (not isValidNode bipObj) or (not isValidNode rootObj) do autoDetect()
        if (not isValidNode bipObj) or (not isValidNode rootObj) do ( messageBox "对象未找到！"; return false )
        if maxFilePath == "" do ( messageBox "请先保存当前 Max 文件！"; return false )

        -- 新增：导出前的安全检查
        if (chk_expTimelineCam.checked or chk_expIngameCam.checked) do (
            if (getNodeByName "Main_Camera") == undefined do (
                messageBox "勾选了导出相机，但场景中找不到 'Main_Camera'！" title:"警告"
                return false
            )
        )

        state_isBatchMode = false
        state_origFilePath = maxFilePath
        state_origFileName = maxFileName
        state_origFileFullName = state_origFilePath + state_origFileName
        state_tempMaxFile = (getDir #temp) + "\\RM_Temp_" + state_origFileName

        local saveSuccess = saveMaxFile state_tempMaxFile clearNeedSaveFlag:true
        if not saveSuccess do ( messageBox "无法创建临时副本文件，导出已终止！"; return false )

        local nodesToBake = #()

        -- 【极速优化 2】：如果仅导出相机，完全跳过 IK 烘焙检查，不再弹窗打断工作流！
        if not chk_onlyCam.checked do (
            local limbsToCheck = #()
            try(append limbsToCheck (biped.getNode bipObj #larm link:4))catch()
            try(append limbsToCheck (biped.getNode bipObj #rarm link:4))catch()
            try(append limbsToCheck (biped.getNode bipObj #lleg link:4))catch()
            try(append limbsToCheck (biped.getNode bipObj #rleg link:4))catch()

            for node in limbsToCheck where node != undefined do (
                local ctrl = node.controller
                local ikRanges = #()
                local inRange = false
                local startF = undefined
                local nKeys = numKeys ctrl

                for i = 1 to nKeys do (
                    local k = biped.getKey ctrl i
                    local isIK = (k.ikSpace == 1 and k.ikBlend > 0.0)
                    if isIK then (
                        if not inRange then ( inRange = true; startF = k.time )
                    ) else (
                        if inRange then (
                            inRange = false
                            local endF = (biped.getKey ctrl (i-1)).time
                            if endF > startF do append ikRanges #(startF, endF)
                        )
                    )
                )
                if inRange do (
                    local endF = (biped.getKey ctrl nKeys).time
                    if endF > startF do append ikRanges #(startF, endF)
                )
                if ikRanges.count > 0 do append nodesToBake #(node, ikRanges)
            )
        )

        if nodesToBake.count > 0 then (
            setCommandPanelTaskMode #motion

            undo "Smart IK to FK Two-Pass" on (
                with redraw off (
                    for item in nodesToBake do (
                        local node = item[1]; local ranges = item[2]
                        select node

                        with animate on (
                            for r in ranges do for t = r[1] to r[2] do (
                                sliderTime = t
                                biped.setKey node true true true
                            )
                            for r in ranges do for t = r[1] to r[2] do (
                                sliderTime = t
                                biped.setFreeKey node
                            )
                        )
                    )
                )
            )
            clearSelection()

            exportState = 1
            btn_export.text = "步骤2：已烘焙！手动解除 IK 后点击继续"
            btn_cancelExport.visible = true
            grp_batch.enabled = false

            local msg = "发现影响 Root Motion 的循环 IK 依赖！\n\n"
            msg += "脚本已将带有 IK 的肢体通过纯净双轨算法完美烘焙为原生 FK 以保护动画。\n"
            msg += "目前你处于隔离副本中，脚本已挂起等待你的操作。\n\n"
            msg += "请现在手动去运动面板：\n点击 IK 槽位右侧箭头，拾取该手臂自身触发【重定位报错】以清空对象槽位。\n\n"
            msg += "完成后，点击面板上变红的【继续】按钮即可！"
            messageBox msg title:"请执行人工介入"
            return OK
        ) else (
            FinalizeExport()
        )
    )

    on btn_batch pressed do (
        local dir = getSavePath caption:"选择批量文件夹" initialDir:maxFilePath
        if dir != undefined do (
            local files = getFiles (dir + "\\*.max")
            if files.count > 0 do (
                state_isBatchMode = true
                for f in files do (
                    try (
                        loadMaxFile f useFileUnits:true quiet:true
                        bipObj = undefined; rootObj = undefined
                        autoDetect()
                        if (isValidNode bipObj) and (isValidNode rootObj) do (
                            state_origFilePath = maxFilePath
                            state_origFileName = maxFileName
                            state_origFileFullName = state_origFilePath + state_origFileName
                            state_tempMaxFile = (getDir #temp) + "\\RM_Temp_" + state_origFileName
                            saveMaxFile state_tempMaxFile clearNeedSaveFlag:true
                            FinalizeExport()
                        )
                    ) catch()
                )
                messageBox "批量导出完成"
                state_isBatchMode = false
            )
        )
    )
)
createDialog rlt_RM_Tool_v6_62607015

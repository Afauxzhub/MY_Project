try(destroyDialog VisCtrlScaleBatchFixUI)catch()

rollout VisCtrlScaleBatchFixUI "显隐Ctrl缩放XYZ批量修复" width:440 height:280
(
    edittext et_path "文件夹:" width:315 pos:[10,15]
    button btn_browse "浏览..." width:85 pos:[335,15]
    progressBar pb_fix "" width:410 pos:[10,50]
    button btn_runCurrent "修复当前场景" width:200 height:36 pos:[10,85]
    button btn_runFolder "批量修复文件夹内所有Max" width:200 height:36 pos:[220,85]
    label lbl_status "就绪" pos:[10,135] width:410
    label lbl_hint "保持 ScaleXYZ，只连接 X_Scale / Y_Scale / Z_Scale" pos:[10,160] width:410
    label lbl_value "显示=1.0；隐藏 factor=0.001（Max 界面可显示为 0.1）" pos:[10,185] width:410

    local LAYER_NAME = "yingcang_ctrl"

    fn getDefaultFolder =
    (
        if maxFileName != "" then getFilenamePath maxFileName else getDir #maxRoot
    )

    fn isOnLayer obj layerName =
    (
        try
        (
            obj != undefined and obj.layer != undefined and (obj.layer.name as string) == layerName
        )
        catch(false)
    )

    fn isInLayerHierarchy obj layerName =
    (
        local current = obj
        while current != undefined do
        (
            if isOnLayer current layerName then return true
            current = current.parent
        )
        false
    )

    fn getUIXMaster uiObj =
    (
        try
        (
            local posCtrl = uiObj.pos.controller
            if posCtrl == undefined or classof posCtrl != Position_XYZ then return undefined
            posCtrl[#X_Position]
        )
        catch(undefined)
    )

    fn getLayerUISliders layerName =
    (
        local sliders = #()
        for o in objects do
        (
            if isInLayerHierarchy o layerName and
               matchPattern o.name pattern:"UI_Slider_*" and
               getUIXMaster o != undefined do append sliders o
        )
        -- 老场景的滑块名称可能是 changbing、jianjia_you 等，并非 UI_Slider_*。
        if sliders.count == 0 then
        (
            for o in objects do
            (
                if isInLayerHierarchy o layerName and getUIXMaster o != undefined do append sliders o
            )
        )
        sliders
    )

    fn sortNodesByName nodes =
    (
        local names = for n in nodes collect n.name
        sort names
        local result = #()
        for nm in names do
        (
            for n in nodes where n.name == nm do append result n
        )
        result
    )

    fn getBoneScaleTarget boneCtrl =
    (
        try(boneCtrl[#Transform][#Scale])catch(undefined)
    )

    -- 返回 #(Wire控制器, Wire索引, 表达式)。
    fn getDirectWireInfo anim wireKind =
    (
        if anim == undefined then return undefined

        local ctrl = undefined
        try(ctrl = anim.controller)catch()
        if ctrl == undefined then return undefined

        local classOK = case wireKind of
        (
            #scale: (classof ctrl == Scale_Wire)
            #float: (classof ctrl == Float_Wire)
            default: false
        )
        if not classOK then return undefined

        local wireCount = 0
        try(wireCount = ctrl.numWires)catch(wireCount = 0)
        if wireCount < 1 then return undefined

        local expr = undefined
        try(expr = ctrl.getExprText 1)catch()
        #(ctrl, 1, expr)
    )

    -- 从现有 Wire 中取回真正的滑块 X 轴 SubAnim。
    fn getWireSourceParam wireInfo =
    (
        if wireInfo == undefined then return undefined
        try
        (
            local sourceParent = wireInfo[1].getWireParent wireInfo[2]
            local sourceSubNum = wireInfo[1].getWireSubnum wireInfo[2]
            local sourceParam = sourceParent[sourceSubNum]
            local sourceName = sourceParam.name as string
            -- 实测 Max 2020 返回 x_position（小写），不能使用区分大小写的 "X" 过滤。
            if sourceName == undefined or sourceName == "" then return undefined
            if classof sourceParent != Position_XYZ or sourceSubNum != 1 then return undefined
            sourceParam
        )
        catch(undefined)
    )

    fn getWireVarName master =
    (
        if master == undefined then return undefined
        try
        (
            local nm = master.name as string
            if nm == undefined or nm == "" then return undefined
            substituteString nm " " "_"
        )
        catch(undefined)
    )

    fn makeAxisExpr master =
    (
        local varName = getWireVarName master
        if varName == undefined then return undefined
        "if " + varName + " > 10 then 1.0 else 0.001"
    )

    fn exprIsHiddenValue expr =
    (
        expr != undefined and (findString expr "0.001") != undefined
    )

    fn getAxisTargets xyzController =
    (
        try(#(xyzController[#X_Scale], xyzController[#Y_Scale], xyzController[#Z_Scale]))catch(#())
    )

    fn getExistingScaleMaster scaleTarget =
    (
        local wholeWire = getDirectWireInfo scaleTarget #scale
        local master = getWireSourceParam wholeWire
        if master != undefined then return master

        local scaleCtrl = undefined
        try(scaleCtrl = scaleTarget.controller)catch()
        if scaleCtrl != undefined and classof scaleCtrl == ScaleXYZ then
        (
            local axes = getAxisTargets scaleCtrl
            for axisTarget in axes do
            (
                master = getWireSourceParam (getDirectWireInfo axisTarget #float)
                if master != undefined then return master
            )
        )
        undefined
    )

    -- 将整个 Transform.Scale 上的 Scale_Wire 断开。
    -- Max 2020 实测会恢复 Bezier_Scale，因此必须通过节点显式创建 ScaleXYZ。
    fn restoreScaleXYZ boneCtrl scaleTarget =
    (
        local wholeWire = getDirectWireInfo scaleTarget #scale
        if wholeWire == undefined then
        (
            local currentCtrl = undefined
            try(currentCtrl = scaleTarget.controller)catch()
            return (currentCtrl != undefined and classof currentCtrl == ScaleXYZ)
        )

        local disconnected = try(paramWire.disconnect wholeWire[1])catch(false)
        if not disconnected then return false

        local restoredCtrl = undefined
        try(restoredCtrl = scaleTarget.controller)catch()

        if restoredCtrl == undefined or classof restoredCtrl != ScaleXYZ then
        (
            local restoredValue = try(scaleTarget.value)catch([1,1,1])
            try(boneCtrl.scale.controller = ScaleXYZ())catch()
            try(restoredCtrl = boneCtrl.scale.controller)catch()

            if restoredCtrl != undefined and classof restoredCtrl == ScaleXYZ do
            (
                try(restoredCtrl[#X_Scale].controller.value = restoredValue.x)catch()
                try(restoredCtrl[#Y_Scale].controller.value = restoredValue.y)catch()
                try(restoredCtrl[#Z_Scale].controller.value = restoredValue.z)catch()
            )
        )

        restoredCtrl != undefined and classof restoredCtrl == ScaleXYZ
    )

    -- 只修改/建立单个 X、Y、Z 标量 Wire；绝不替换顶层 ScaleXYZ。
    -- 返回 #(成功, 是否发生改写)。
    fn setAxisWire axisTarget fallbackMaster =
    (
        local wireInfo = getDirectWireInfo axisTarget #float
        local master = getWireSourceParam wireInfo
        if master == undefined then master = fallbackMaster
        if master == undefined then return #(false, false)

        local newExpr = makeAxisExpr master
        if newExpr == undefined then return #(false, false)

        if wireInfo != undefined then
        (
            if wireInfo[3] == newExpr then return #(true, false)
            local updated = false
            try
            (
                wireInfo[1].setExprText wireInfo[2] newExpr
                local savedExpr = wireInfo[1].getExprText wireInfo[2]
                updated = exprIsHiddenValue savedExpr
            )
            catch(updated = false)
            #(updated, updated)
        )
        else
        (
            local connected = try(paramWire.connect master axisTarget newExpr)catch(false)
            local newWire = getDirectWireInfo axisTarget #float
            local verified = connected and newWire != undefined and exprIsHiddenValue newWire[3]
            #(verified, verified)
        )
    )

    fn verifyScaleXYZWires scaleTarget =
    (
        local scaleCtrl = undefined
        try(scaleCtrl = scaleTarget.controller)catch()
        if scaleCtrl == undefined or classof scaleCtrl != ScaleXYZ then return false

        local axes = getAxisTargets scaleCtrl
        if axes.count != 3 then return false

        for axisTarget in axes do
        (
            local wireInfo = getDirectWireInfo axisTarget #float
            if wireInfo == undefined or not (exprIsHiddenValue wireInfo[3]) then return false
        )
        true
    )

    -- 返回 #(实际改写, 找到来源, 验证通过)。
    fn fixBoneCtrlScaleXYZ boneCtrl fallbackMaster =
    (
        if boneCtrl == undefined then return #(false, false, false)

        local scaleTarget = getBoneScaleTarget boneCtrl
        if scaleTarget == undefined then return #(false, false, false)

        local wholeWire = getDirectWireInfo scaleTarget #scale
        local master = getExistingScaleMaster scaleTarget
        if master == undefined then master = fallbackMaster
        if master == undefined then return #(false, false, false)

        local changed = false
        if wholeWire != undefined then
        (
            if not (restoreScaleXYZ boneCtrl scaleTarget) then return #(false, true, false)
            changed = true
        )

        local scaleCtrl = undefined
        try(scaleCtrl = scaleTarget.controller)catch()
        if scaleCtrl == undefined or classof scaleCtrl != ScaleXYZ then return #(false, true, false)

        local axes = getAxisTargets scaleCtrl
        if axes.count != 3 then return #(false, true, false)

        local allOK = true
        for axisTarget in axes do
        (
            local axisResult = setAxisWire axisTarget master
            if not axisResult[1] then allOK = false
            if axisResult[2] then changed = true
        )

        local verified = allOK and verifyScaleXYZWires scaleTarget
        #(changed and verified, true, verified)
    )

    fn fixCurrentScene =
    (
        local boneCtrls = for o in objects where
            ((matchPattern o.name pattern:"bone_ctrl*") or
             (matchPattern o.name pattern:"ctrl_bone*")) collect o
        boneCtrls = sortNodesByName boneCtrls

        local uiSliders = sortNodesByName (getLayerUISliders LAYER_NAME)
        local changedCount = 0
        local sourceCount = 0
        local verifiedCount = 0
        local failedCount = 0

        for i = 1 to boneCtrls.count do
        (
            local fallbackMaster = undefined
            if i <= uiSliders.count do fallbackMaster = getUIXMaster uiSliders[i]

            local result = fixBoneCtrlScaleXYZ boneCtrls[i] fallbackMaster
            if result[1] then changedCount += 1
            if result[2] then sourceCount += 1
            if result[3] then verifiedCount += 1
            if result[2] and not result[3] then failedCount += 1
        )

        #(changedCount, boneCtrls.count, sourceCount, uiSliders.count, verifiedCount, failedCount)
    )

    fn fixMaxFile filePath =
    (
        loadMaxFile filePath useFileUnits:true quiet:true
        local result = fixCurrentScene()
        -- 只保存完全验证通过的文件，失败文件保持原文件不变。
        if result[1] > 0 and result[6] == 0 do saveMaxFile filePath
        result
    )

    on VisCtrlScaleBatchFixUI open do et_path.text = getDefaultFolder()

    on btn_browse pressed do
    (
        local dir = getSavePath caption:"选择Max文件夹" initialDir:et_path.text
        if dir != undefined do et_path.text = dir
    )

    on btn_runCurrent pressed do
    (
        undo "修复显隐Ctrl缩放XYZ" on
        (
            local result = fixCurrentScene()
            local resultMsg = "处理完成！  "
            resultMsg += "bone_ctrl/ctrl_bone: " + (result[2] as string) + " "
            resultMsg += "层内UI滑块: " + (result[4] as string) + " "
            resultMsg += "找到滑块来源: " + (result[3] as string) + " "
            resultMsg += "本次转换/改写: " + (result[1] as string) + " "
            resultMsg += "ScaleXYZ三轴验证通过: " + (result[5] as string) + " "
            resultMsg += "失败: " + (result[6] as string)
            messageBox resultMsg title:"当前场景"
        )
    )

    on btn_runFolder pressed do
    (
        local srcPath = et_path.text
        if srcPath == "" do (messageBox "路径无效" title:"提示"; return false)


        local maxFiles = getFiles (pathConfig.appendPath srcPath "*.max")
        if maxFiles.count == 0 do (messageBox "无 Max 文件" title:"提示"; return false)
        if not (queryBox ("处理 " + (maxFiles.count as string) + " 个文件？") title:"确认") do return false

        setQuietMode true
        suspendEditing()

        local totalChanged = 0
        local totalBones = 0
        local totalVerified = 0
        local totalFailed = 0
        local savedFiles = 0

        for fileIndex = 1 to maxFiles.count do
        (
            try
            (
                local result = fixMaxFile maxFiles[fileIndex]
                totalChanged += result[1]
                totalBones += result[2]
                totalVerified += result[5]
                totalFailed += result[6]
                if result[1] > 0 and result[6] == 0 then savedFiles += 1
            )
            catch(totalFailed += 1)

            pb_fix.value = 100.0 * fileIndex / maxFiles.count
            lbl_status.text = "处理中: " + (fileIndex as string) + " / " + (maxFiles.count as string)
        )

        resumeEditing()
        setQuietMode false
        lbl_status.text = "完成"

        local batchMsg = "批量处理完成！  "
        batchMsg += "Max文件: " + (maxFiles.count as string) + " "
        batchMsg += "bone_ctrl/ctrl_bone: " + (totalBones as string) + " "
        batchMsg += "转换/改写: " + (totalChanged as string) + " "
        batchMsg += "ScaleXYZ三轴验证通过: " + (totalVerified as string) + " "
        batchMsg += "失败: " + (totalFailed as string) + " "
        batchMsg += "保存文件: " + (savedFiles as string)
        messageBox batchMsg title:"完成"
    )
)

createDialog VisCtrlScaleBatchFixUI style:#(#style_toolwindow, #style_sysmenu)

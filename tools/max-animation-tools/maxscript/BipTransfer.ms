/*
Reference Rig - BIP transfer helpers for migration MVP
*/

global RR_BipTransfer

struct RR_BipTransferLib
(
    fn _result okValue codeValue messageValue blockers:#() warnings:#() info:#() data:undefined =
    (
        local payload = if data == undefined then #() else data
        #(
            #ok, okValue,
            #code, codeValue,
            #message, messageValue,
            #blockers, blockers,
            #warnings, warnings,
            #info, info,
            #data, payload
        )
    ),

    fn _kvGet payload key defaultValue =
    (
        local idx = findItem payload key
        if idx > 0 and (idx + 1) <= payload.count then payload[idx + 1] else defaultValue
    ),

    fn _scenePath =
    (
        if maxFileName == "" then "" else (maxFilePath + maxFileName)
    ),

    fn _detectBipRootName preferred:"Bip001" =
    (
        local preferredNode = getNodeByName preferred
        if preferredNode != undefined then return preferredNode.name

        for node in objects do
        (
            local cls = classof node as string
            if matchPattern cls pattern:"*Biped*" ignoreCase:true and node.parent == undefined do return node.name
        )

        ""
    ),

    fn _collectIkNodeNames =
    (
        local names = #()
        for node in objects do
        (
            if matchPattern node.name pattern:"*IK*" ignoreCase:true do append names node.name
        )
        makeUniqueArray names
    ),

    fn _joinStrings values sep:", " =
    (
        if values.count == 0 then return ""
        local s = values[1] as string
        for i = 2 to values.count do s += sep + (values[i] as string)
        s
    ),

    fn _checkIkByNames ikNames strict:true =
    (
        local missing = #()
        for nameValue in ikNames where getNodeByName nameValue == undefined do append missing nameValue

        local blockers = #()
        local warnings = #()
        if missing.count > 0 then
        (
            local missingText = RR_BipTransfer._joinStrings missing sep:", "
            if strict then append blockers ("IK 关键对象缺失: " + missingText)
            else append warnings ("IK 关键对象缺失: " + missingText)
        )

        #(
            #ok, (missing.count == 0 or (not strict)),
            #missing, missing,
            #blockers, blockers,
            #warnings, warnings,
            #checkedCount, ikNames.count
        )
    ),

    fn _safeLoadScene filePath =
    (
        if filePath == "" or not doesFileExist filePath then return RR_BipTransfer._result false "PRECHECK_FILE_NOT_FOUND" ("文件不存在: " + filePath)
        try
        (
            local loaded = loadMaxFile filePath quiet:true useFileUnits:true
            if loaded then RR_BipTransfer._result true "OK" "场景加载成功" data:#(#scenePath, filePath)
            else RR_BipTransfer._result false "RUNTIME_LOAD_FAILED" ("场景加载失败: " + filePath)
        )
        catch
        (
            RR_BipTransfer._result false "RUNTIME_LOAD_EXCEPTION" (getCurrentException())
        )
    ),

    fn validate_bip_precheck oldAnimPath newRigPath mappingPath:undefined strictIK:true =
    (
        local blockers = #()
        local warnings = #()
        local info = #()
        local data = #()

        local oldLoad = RR_BipTransfer._safeLoadScene oldAnimPath
        if not RR_BipTransfer._kvGet oldLoad #ok false do
        (
            append blockers (RR_BipTransfer._kvGet oldLoad #message "旧场景加载失败")
            return RR_BipTransfer._result false "PRECHECK_OLD_LOAD_FAILED" "迁移前检查失败" blockers:blockers warnings:warnings info:info data:data
        )

        local oldBipRoot = RR_BipTransfer._detectBipRootName preferred:"Bip001"
        if oldBipRoot == "" then append blockers "旧动画文件未识别到 BIP 根（优先 Bip001）。"
        append data #(#old_bip_root, oldBipRoot)

        local ikNames = RR_BipTransfer._collectIkNodeNames()
        append data #(#ik_source_names, ikNames)
        append info ("旧场景 IK 抽样对象数: " + (ikNames.count as string))

        local newLoad = RR_BipTransfer._safeLoadScene newRigPath
        if not RR_BipTransfer._kvGet newLoad #ok false do
        (
            append blockers (RR_BipTransfer._kvGet newLoad #message "新绑定加载失败")
            return RR_BipTransfer._result false "PRECHECK_NEW_LOAD_FAILED" "迁移前检查失败" blockers:blockers warnings:warnings info:info data:data
        )

        local newBip = getNodeByName "Bip001"
        if newBip == undefined then append blockers "新绑定场景不存在同名 Bip001。"

        local ikCheck = RR_BipTransfer._checkIkByNames ikNames strict:strictIK
        join blockers (RR_BipTransfer._kvGet ikCheck #blockers #())
        join warnings (RR_BipTransfer._kvGet ikCheck #warnings #())
        append data #(#ik_missing, RR_BipTransfer._kvGet ikCheck #missing #())
        append data #(#ik_checked_count, RR_BipTransfer._kvGet ikCheck #checkedCount 0)

        local okValue = blockers.count == 0
        local codeValue = if okValue then "OK" else "PRECHECK_BLOCKED"
        local messageValue = if okValue then "迁移前检查通过" else "迁移前检查未通过"
        RR_BipTransfer._result okValue codeValue messageValue blockers:blockers warnings:warnings info:info data:data
    ),

    fn export_bip_from_old_scene oldAnimPath bipTempPath =
    (
        local blockers = #()
        local info = #()
        local loadResult = RR_BipTransfer._safeLoadScene oldAnimPath
        if not RR_BipTransfer._kvGet loadResult #ok false do return RR_BipTransfer._result false "EXPORT_OLD_LOAD_FAILED" (RR_BipTransfer._kvGet loadResult #message "加载旧动画失败")

        local bipNode = getNodeByName "Bip001"
        if bipNode == undefined do bipNode = getNodeByName (RR_BipTransfer._detectBipRootName())
        if bipNode == undefined then
        (
            append blockers "旧动画场景缺少可导出的 BIP 根。"
            return RR_BipTransfer._result false "EXPORT_NO_BIP" "BIP 导出失败" blockers:blockers
        )

        try
        (
            local parentDir = getFilenamePath bipTempPath
            if parentDir != "" do makeDir parentDir all:true
            local exported = biped.saveBipFile bipNode.controller bipTempPath
            if exported and doesFileExist bipTempPath then
            (
                append info ("BIP 导出成功: " + bipTempPath)
                RR_BipTransfer._result true "OK" "BIP 导出成功" info:info data:#(#bip_root, bipNode.name, #bip_temp_path, bipTempPath)
            )
            else
            (
                RR_BipTransfer._result false "EXPORT_BIP_FAILED" "BIP 导出返回失败状态。"
            )
        )
        catch
        (
            RR_BipTransfer._result false "EXPORT_BIP_EXCEPTION" (getCurrentException())
        )
    ),

    fn import_bip_to_new_scene newRigPath bipTempPath targetBipRootName:"Bip001" =
    (
        local loadResult = RR_BipTransfer._safeLoadScene newRigPath
        if not RR_BipTransfer._kvGet loadResult #ok false do return RR_BipTransfer._result false "IMPORT_NEW_LOAD_FAILED" (RR_BipTransfer._kvGet loadResult #message "加载新绑定失败")

        if not doesFileExist bipTempPath do return RR_BipTransfer._result false "IMPORT_BIP_NOT_FOUND" ("未找到 BIP 文件: " + bipTempPath)

        local targetNode = getNodeByName targetBipRootName
        if targetNode == undefined then return RR_BipTransfer._result false "IMPORT_TARGET_BIP_MISSING" ("新绑定场景缺少目标 BIP 根: " + targetBipRootName)

        try
        (
            local imported = biped.loadBipFile targetNode.controller bipTempPath
            if imported then
                RR_BipTransfer._result true "OK" "BIP 导入成功" data:#(#target_bip_root, targetNode.name, #bip_temp_path, bipTempPath)
            else
                RR_BipTransfer._result false "IMPORT_BIP_FAILED" "BIP 导入返回失败状态。"
        )
        catch
        (
            RR_BipTransfer._result false "IMPORT_BIP_EXCEPTION" (getCurrentException())
        )
    ),

    fn _floatIsFinite value =
    (
        (value == value) and (abs value < 1e+30)
    ),

    fn _matrixIsReasonable tm =
    (
        local r1 = tm.row1
        local r2 = tm.row2
        local r3 = tm.row3
        local r4 = tm.row4

        local finite = RR_BipTransfer._floatIsFinite r1.x and RR_BipTransfer._floatIsFinite r1.y and RR_BipTransfer._floatIsFinite r1.z and
            RR_BipTransfer._floatIsFinite r2.x and RR_BipTransfer._floatIsFinite r2.y and RR_BipTransfer._floatIsFinite r2.z and
            RR_BipTransfer._floatIsFinite r3.x and RR_BipTransfer._floatIsFinite r3.y and RR_BipTransfer._floatIsFinite r3.z and
            RR_BipTransfer._floatIsFinite r4.x and RR_BipTransfer._floatIsFinite r4.y and RR_BipTransfer._floatIsFinite r4.z

        local nonDegenerate = (length r1) > 1e-6 and (length r2) > 1e-6 and (length r3) > 1e-6
        finite and nonDegenerate
    ),

    fn postcheck_basic targetBipRootName:"Bip001" =
    (
        local warnings = #()
        local blockers = #()
        local sampleRows = #()

        local bipRoot = getNodeByName targetBipRootName
        if bipRoot == undefined then return RR_BipTransfer._result false "POSTCHECK_BIP_MISSING" "导入后检查失败：缺少 Bip001。" blockers:#("导入后未找到 Bip001")

        local t0 = animationRange.start
        local t2 = animationRange.end
        local t1 = t0 + ((t2 - t0) / 2)
        local samples = #(t0, t1, t2)

        for t in samples do
        (
            at time t
            (
                local okTm = RR_BipTransfer._matrixIsReasonable bipRoot.transform
                append sampleRows #(#time, (t as string), #ok, okTm)
                if not okTm do append warnings ("姿态抽样异常: " + (t as string))
            )
        )

        local okValue = warnings.count == 0
        local codeValue = if okValue then "OK" else "POSTCHECK_WARNING"
        local messageValue = if okValue then "迁移后抽样检查通过" else "迁移后抽样检查存在警告"
        RR_BipTransfer._result okValue codeValue messageValue blockers:blockers warnings:warnings data:#(#samples, sampleRows)
    ),

    fn save_migrated_scene outputMaxPath overwrite:false =
    (
        if outputMaxPath == "" then return RR_BipTransfer._result false "SAVE_OUTPUT_EMPTY" "输出路径为空。"
        if (not overwrite) and doesFileExist outputMaxPath then return RR_BipTransfer._result false "SAVE_OUTPUT_EXISTS" ("输出文件已存在: " + outputMaxPath)
        try
        (
            local dirPath = getFilenamePath outputMaxPath
            if dirPath != "" do makeDir dirPath all:true
            local saved = saveMaxFile outputMaxPath quiet:true
            if saved and doesFileExist outputMaxPath then
                RR_BipTransfer._result true "OK" "迁移场景保存成功" data:#(#output_max_path, outputMaxPath)
            else
                RR_BipTransfer._result false "SAVE_OUTPUT_FAILED" "保存迁移文件失败。"
        )
        catch
        (
            RR_BipTransfer._result false "SAVE_OUTPUT_EXCEPTION" (getCurrentException())
        )
    )
)

RR_BipTransfer = RR_BipTransferLib()

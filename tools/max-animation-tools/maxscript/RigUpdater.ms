/*
Reference Rig - Update orchestration
Requires: RigManifest.ms, RigScanner.ms, BipValidator.ms, ConstraintRelinker.ms
*/

global RR_Updater

struct RR_UpdateSettings
(
    oldManifestPath = "",
    newManifestPath = "",
    newRigPath = "",
    backupRoot = "",
    reportRoot = "",
    dryRun = false,
    saveAfterUpdate = false
)

struct RR_UpdateResult
(
    ok = true,
    backupFile = "",
    reportFile = "",
    scanReport = undefined,
    bipValidation = undefined,
    relinkReport = undefined,
    messages = #()
)

struct RR_UpdaterLib
(
    fn _timestamp =
    (
        local nowValue = dotNetClass "System.DateTime"
        nowValue.Now.ToString "yyyyMMdd_HHmmss"
    ),

    fn _ensureDir dirPath =
    (
        if dirPath == "" then return false
        makeDir dirPath all:true
        true
    ),

    fn _defaultBackupRoot =
    (
        if maxFilePath == "" then (getDir #temp + "\\ReferenceRigBackups") else (maxFilePath + "_RigUpdateBackup")
    ),

    fn _defaultReportRoot =
    (
        if maxFilePath == "" then (getDir #temp + "\\ReferenceRigReports") else (maxFilePath + "_RigUpdateReports")
    ),

    fn _safeSceneName =
    (
        local nameValue = maxFileName
        if nameValue == "" then nameValue = "untitled.max"
        substituteString nameValue ".max" ""
    ),

    fn createBackup oldVersion:"unknown" backupRoot:"" =
    (
        local root = if backupRoot == "" then RR_Updater._defaultBackupRoot() else backupRoot
        RR_Updater._ensureDir root

        local fileName = RR_Updater._safeSceneName() + ".beforeRigUpdate_" + oldVersion + "_" + RR_Updater._timestamp() + ".max"
        local backupPath = root + "\\" + fileName
        saveMaxFile backupPath quiet:true
        backupPath
    ),

    fn _createReportFile reportRoot:"" =
    (
        local root = if reportRoot == "" then RR_Updater._defaultReportRoot() else reportRoot
        RR_Updater._ensureDir root
        root + "\\" + RR_Updater._safeSceneName() + ".rigUpdate_" + RR_Updater._timestamp() + ".txt"
    ),

    fn _writeSingleFileHeader result settings rigObjectNames =
    (
        local stream = if doesFileExist result.reportFile then openFile result.reportFile mode:"a" else createFile result.reportFile
        format "单文件绑定更新报告\n" to:stream
        format "当前动画文件: %\n" (maxFilePath + maxFileName) to:stream
        format "新版绑定文件: %\n" settings.newRigPath to:stream
        format "仅检查模式: %\n" settings.dryRun to:stream
        format "成功后保存: %\n" settings.saveAfterUpdate to:stream
        format "新版绑定对象数量: %\n\n" rigObjectNames.count to:stream
        close stream
    ),

    fn _appendMessages result =
    (
        local stream = openFile result.reportFile mode:"a"
        format "\nUpdate Messages\n" to:stream
        for message in result.messages do format "  - %\n" message to:stream
        close stream
    ),

    fn _getMaxFileObjectNames filePath =
    (
        local names = #()
        try names = getMAXFileObjectNames filePath catch names = #()
        names
    ),

    fn _mergeRigFileConservative filePath =
    (
        local beforeNodes = for node in objects collect node
        local mergedNodes = #()

        try
        (
            clearSelection()
            mergeMAXFile filePath #select #autoRenameDups quiet:true
            mergedNodes = selection as array
        )
        catch
        (
            mergedNodes = #()
        )

        if mergedNodes.count == 0 do
        (
            mergedNodes = for node in objects where (findItem beforeNodes node) == 0 collect node
        )

        #(mergedNodes.count > 0, mergedNodes)
    ),

    fn importNewInterfaceNodes oldManifest newManifest =
    (
        local imported = #()
        for record in newManifest.nodes do
        (
            local oldRecord = RR_Manifest.findRecordByGuid oldManifest record.guid
            local existing = RR_Manifest.findNodeByGuid record.guid

            if oldRecord == undefined and existing == undefined do
            (
                /*
                Placeholder behavior for MVP:
                Actual rig-node import should be done from the published rig file
                after the studio decides the final node-level replacement rules.
                The report still lists missing additive nodes.
                */
                append imported record.name
            )
        )
        imported
    ),

    fn runUpdate settings =
    (
        local result = RR_UpdateResult()
        local oldManifest = RR_Manifest.readManifest settings.oldManifestPath
        local newManifest = RR_Manifest.readManifest settings.newManifestPath

        local oldVersion = if oldManifest.rigVersion == "" then "unknown" else oldManifest.rigVersion

        if not settings.dryRun do
        (
            result.backupFile = RR_Updater.createBackup oldVersion:oldVersion backupRoot:settings.backupRoot
            append result.messages ("Backup created: " + result.backupFile)
        )

        result.reportFile = RR_Updater._createReportFile reportRoot:settings.reportRoot

        result.scanReport = RR_Scanner.scanScene includeReferenced:false
        RR_Scanner.writeReport result.scanReport result.reportFile

        result.bipValidation = RR_BipValidator.validate result.scanReport manifest:oldManifest
        RR_BipValidator.appendToReport result.bipValidation result.reportFile

        if not result.bipValidation.ok do
        (
            result.ok = false
            append result.messages "BIP validation failed; relink/update was not executed."
            RR_Updater._appendMessages result
            return result
        )

        local additive = RR_Updater.importNewInterfaceNodes oldManifest newManifest
        for nodeName in additive do append result.messages ("Additive node not present in current shot and should come from updated rig: " + nodeName)

        result.relinkReport = RR_ConstraintRelinker.relinkScene oldManifest newManifest dryRun:settings.dryRun
        RR_ConstraintRelinker.writeReport result.relinkReport result.reportFile

        if result.relinkReport.errors.count > 0 do
        (
            result.ok = false
            append result.messages "One or more constraints could not be safely relinked."
        )

        RR_Manifest.stampSceneVersion newManifest

        if result.ok and settings.saveAfterUpdate and not settings.dryRun do
        (
            saveMaxFile (maxFilePath + maxFileName) quiet:true
            append result.messages "Scene saved after successful rig update."
        )

        RR_Updater._appendMessages result
        result
    ),

    fn runSingleRigFileUpdate settings =
    (
        local result = RR_UpdateResult()
        result.reportFile = RR_Updater._createReportFile reportRoot:settings.reportRoot

        if settings.newRigPath == "" or not doesFileExist settings.newRigPath then
        (
            result.ok = false
            RR_Updater._writeSingleFileHeader result settings #()
            append result.messages "未找到新版绑定文件，请先定位有效的 .max 绑定文件。"
            RR_Updater._appendMessages result
            return result
        )

        local rigObjectNames = RR_Updater._getMaxFileObjectNames settings.newRigPath
        RR_Updater._writeSingleFileHeader result settings rigObjectNames

        result.scanReport = RR_Scanner.scanScene includeReferenced:false
        RR_Scanner.writeReport result.scanReport result.reportFile
        RR_Updater._writeSingleFileHeader result settings rigObjectNames

        result.bipValidation = RR_BipValidator.validate result.scanReport manifest:undefined
        RR_BipValidator.appendToReport result.bipValidation result.reportFile

        if not result.bipValidation.ok do
        (
            result.ok = false
            append result.messages "当前文件未通过 BIP 检查，已停止更新。"
            RR_Updater._appendMessages result
            return result
        )

        if settings.dryRun then
        (
            append result.messages "仅检查模式：未写入当前动画文件。"
            append result.messages "当前版本支持单文件流程的路径定位、备份、BIP/约束扫描和报告。"
            append result.messages "正式替换会保留当前动画文件中的 BIP 动画，不会重建主体 BIP。"
            RR_Updater._appendMessages result
            return result
        )

        result.backupFile = RR_Updater.createBackup oldVersion:"singleFile" backupRoot:settings.backupRoot
        append result.messages ("已创建备份: " + result.backupFile)

        local mergeResult = RR_Updater._mergeRigFileConservative settings.newRigPath
        if mergeResult[1] then
        (
            append result.messages ("已将新版绑定文件导入当前场景，导入对象数量: " + (mergeResult[2].count as string))
            append result.messages "注意：当前为安全导入模式，会保留旧动画绑定，避免直接破坏动画。正式节点级替换需要基于稳定命名/GUID 做进一步映射。"
        )
        else
        (
            result.ok = false
            append result.messages "新版绑定文件导入失败，当前动画文件未完成更新。"
        )

        if result.ok and settings.saveAfterUpdate do
        (
            saveMaxFile (maxFilePath + maxFileName) quiet:true
            append result.messages "已按设置保存当前动画文件。"
        )

        RR_Updater._appendMessages result
        result
    ),

    fn validateOnly manifestPath reportRoot:"" =
    (
        local settings = RR_UpdateSettings()
        settings.oldManifestPath = manifestPath
        settings.newManifestPath = manifestPath
        settings.reportRoot = reportRoot
        settings.dryRun = true
        RR_Updater.runUpdate settings
    )
)

RR_Updater = RR_UpdaterLib()

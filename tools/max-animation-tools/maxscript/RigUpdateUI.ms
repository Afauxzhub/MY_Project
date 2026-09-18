/*
Reference Rig - Animator UI
Requires: RigUpdater.ms and dependencies.
*/

global RR_RigUpdateRollout
global RR_RigUpdateUI_SourceFile
global RR_RigUpdateUI_ScriptDir
global RR_LastReferenceRigFile

try destroyDialog RR_RigUpdateRollout catch()

RR_RigUpdateUI_SourceFile = getSourceFileName()
RR_RigUpdateUI_ScriptDir = getFilenamePath RR_RigUpdateUI_SourceFile

rollout RR_RigUpdateRollout "引用绑定更新工具" width:620 height:470
(
    groupBox grpRigFile "新版绑定文件" pos:[10,10] width:600 height:72
    editText edtRigFile "路径" pos:[22,36] width:500 height:18 text:""
    button btnRigFile "定位..." pos:[532,34] width:65 height:24

    groupBox grpOptions "更新设置" pos:[10,92] width:600 height:68
    checkbox chkDryRun "仅检查，不写入文件" pos:[22,120] width:155 checked:true
    checkbox chkSaveAfter "更新成功后自动保存" pos:[200,120] width:170 checked:false
    button btnUpdateTools "从公盘更新工具" pos:[430,113] width:150 height:32

    button btnCheck "检查当前文件" pos:[22,175] width:130 height:32
    button btnUpdate "更新绑定" pos:[168,175] width:130 height:32
    button btnOpenReport "打开报告" pos:[314,175] width:130 height:32 enabled:false

    groupBox grpMigration "BIP 迁移 MVP (Phase 2)" pos:[10,220] width:600 height:95
    editText edtOutputPath "输出" pos:[22,246] width:500 height:18 text:""
    button btnPickOutput "选择..." pos:[532,244] width:65 height:24
    button btnMigrate "执行迁移(BIP MVP)" pos:[22,274] width:180 height:28
    button btnOpenMigrateReport "打开迁移报告" pos:[214,274] width:130 height:28 enabled:false

    groupBox grpStatus "状态" pos:[10,325] width:600 height:130
    label lblScene "当前文件：" pos:[22,350] width:570 height:16
    label lblResult "结果：等待操作" pos:[22,373] width:570 height:16
    label lblBackup "备份：-" pos:[22,396] width:570 height:16
    label lblReport "报告：-" pos:[22,419] width:570 height:16
    label lblMigrate "迁移：等待操作" pos:[22,442] width:570 height:16

    local lastReport = ""
    local lastMigrateReportTxt = ""
    if RR_LastReferenceRigFile == undefined do RR_LastReferenceRigFile = ""
    local fixedPublicSource = @""
    local defaultRigSource = @""

    fn _pickRigFile currentValue =
    (
        local initialDir = maxFilePath
        if currentValue != "" then
        (
            initialDir = getFilenamePath currentValue
        )
        else if doesDirectoryExist defaultRigSource then
        (
            initialDir = defaultRigSource
        )
        getOpenFileName caption:"选择新版绑定 Max 文件" filename:(initialDir + "\\*.max") types:"3ds Max (*.max)|*.max|All Files (*.*)|*.*|"
    )

    fn _installRoot =
    (
        local dirInfo = dotNetObject "System.IO.DirectoryInfo" RR_RigUpdateUI_ScriptDir
        dirInfo.Parent.FullName + "\\"
    )

    fn _isValidSourceRoot pathValue =
    (
        pathValue != undefined and
        pathValue != "" and
        doesDirectoryExist pathValue and
        doesFileExist (pathValue + "\\install_animation_tools.ms") and
        doesFileExist (pathValue + "\\maxscript\\ReferenceRig.ms")
    )

    fn _copyFolder sourceDir targetDir =
    (
        if toLower (trimRight sourceDir "\\/") == toLower (trimRight targetDir "\\/") then return true
        makeDir targetDir all:true

        for filePath in getFiles (sourceDir + "\\*") do
        (
            local fileName = filenameFromPath filePath
            if not (matchPattern fileName pattern:"*.plan.md" ignoreCase:true) do
            (
                copyFile filePath (targetDir + "\\" + fileName)
            )
        )

        for dirPath in getDirectories (sourceDir + "\\*") do
        (
            local dirName = getFilenameFile (trimRight dirPath "\\/")
            if dirName != ".git" and dirName != ".cursor" and dirName != "_RigUpdateBackup" and dirName != "_RigUpdateReports" do
            (
                _copyFolder dirPath (targetDir + "\\" + dirName)
            )
        )

        true
    )

    fn _updateToolsFromPublic =
    (
        if not (_isValidSourceRoot fixedPublicSource) then
        (
            messageBox ("公盘工具目录不可用或不完整：\n" + fixedPublicSource + "\n\n目录内必须包含 install_animation_tools.ms 和 maxscript\\ReferenceRig.ms。") title:"引用绑定更新工具"
            return false
        )

        local dst = _installRoot()
        _copyFolder fixedPublicSource dst
        messageBox ("工具脚本已从公盘更新：\n" + fixedPublicSource + "\n\n请关闭并重新打开此工具界面，以使用新脚本。") title:"引用绑定更新工具"
        true
    )

    fn _makeSettings dryRunValue =
    (
        local settings = RR_UpdateSettings()
        settings.newRigPath = edtRigFile.text
        settings.dryRun = dryRunValue
        settings.saveAfterUpdate = chkSaveAfter.checked
        settings
    )

    fn _defaultMigrateOutputPath =
    (
        if maxFileName == "" then ""
        else RR_MigrateService._defaultOutputPath (maxFilePath + maxFileName)
    )

    fn _pickOutputPath currentValue =
    (
        local initialDir = maxFilePath
        local defaultName = if maxFileName == "" then "Migrated_RigUpdate_v001.max" else (getFilenameFile maxFileName + "_RigUpdate_v001.max")
        if currentValue != "" then
        (
            initialDir = getFilenamePath currentValue
            defaultName = filenameFromPath currentValue
        )
        getSaveFileName caption:"选择迁移输出 Max 文件" filename:(initialDir + defaultName) types:"3ds Max (*.max)|*.max|All Files (*.*)|*.*|"
    )

    fn _kvGet payload key defaultValue =
    (
        local idx = findItem payload key
        if idx > 0 and (idx + 1) <= payload.count then payload[idx + 1] else defaultValue
    )

    fn _showResult result =
    (
        lastReport = result.reportFile
        btnOpenReport.enabled = doesFileExist lastReport
        lblResult.text = "结果：" + (if result.ok then "通过" else "需要检查")
        lblBackup.text = "备份：" + (if result.backupFile == "" then "-" else result.backupFile)
        lblReport.text = "报告：" + result.reportFile
    )

    on RR_RigUpdateRollout open do
    (
        lblScene.text = "当前文件：" + (if maxFileName == "" then "未保存文件" else (maxFilePath + maxFileName))
        if RR_LastReferenceRigFile != undefined and RR_LastReferenceRigFile != "" do edtRigFile.text = RR_LastReferenceRigFile
        edtOutputPath.text = _defaultMigrateOutputPath()
    )

    on btnRigFile pressed do
    (
        local filePath = _pickRigFile edtRigFile.text
        if filePath != undefined do
        (
            edtRigFile.text = filePath
            RR_LastReferenceRigFile = filePath
        )
    )

    on btnPickOutput pressed do
    (
        local outputPath = _pickOutputPath edtOutputPath.text
        if outputPath != undefined do edtOutputPath.text = outputPath
    )

    on btnCheck pressed do
    (
        if edtRigFile.text == "" then
        (
            messageBox "请先定位新版绑定 Max 文件。"
        )
        else
        (
            local settings = _makeSettings true
            local result = RR_Updater.runSingleRigFileUpdate settings
            _showResult result
        )
    )

    on btnUpdate pressed do
    (
        if edtRigFile.text == "" then
        (
            messageBox "更新前请先定位新版绑定 Max 文件。"
        )
        else
        (
            RR_LastReferenceRigFile = edtRigFile.text
            local result = RR_Updater.runSingleRigFileUpdate (_makeSettings chkDryRun.checked)
            _showResult result
            if result.ok then
            (
                messageBox "绑定更新流程完成。正式保存前建议先查看报告并检查动画。"
            )
            else
            (
                messageBox "绑定更新存在需要检查的项目，请打开报告查看详情。"
            )
        )
    )

    on btnOpenReport pressed do
    (
        if doesFileExist lastReport then shellLaunch lastReport ""
    )

    on btnMigrate pressed do
    (
        if maxFileName == "" then
        (
            messageBox "请先保存当前旧动画文件，再执行迁移。"
            return()
        )
        if edtRigFile.text == "" then
        (
            messageBox "迁移前请先定位新版绑定 Max 文件。"
            return()
        )
        if edtOutputPath.text == "" then
        (
            edtOutputPath.text = _defaultMigrateOutputPath()
        )
        if edtOutputPath.text == "" then
        (
            messageBox "请设置有效的迁移输出路径。"
            return()
        )

        local oldAnimPath = maxFilePath + maxFileName
        RR_LastReferenceRigFile = edtRigFile.text
        lblMigrate.text = "迁移：处理中..."
        btnMigrate.enabled = false

        local result = RR_MigrateService.run_bip_migration_mvp oldAnimPath edtRigFile.text edtOutputPath.text overwrite:false strict_ik:true

        btnMigrate.enabled = true
        lastMigrateReportTxt = _kvGet result #report_txt ""
        btnOpenMigrateReport.enabled = doesFileExist lastMigrateReportTxt

        if _kvGet result #ok false then
        (
            local warnCount = (_kvGet result #warnings #()).count
            lblMigrate.text = if warnCount > 0 then ("迁移：成功（警告 " + (warnCount as string) + "）") else "迁移：成功"
            lblReport.text = "报告：" + lastMigrateReportTxt
            messageBox ("BIP MVP 迁移完成。\n输出文件: " + (_kvGet result #output_max_path "") + "\n请打开迁移报告复核。")
        )
        else
        (
            lblMigrate.text = "迁移：阻断/失败"
            lblReport.text = "报告：" + (if lastMigrateReportTxt == "" then "-" else lastMigrateReportTxt)
            messageBox ("BIP MVP 迁移未完成。\n原因: " + (_kvGet result #message "未知错误") + "\n请打开迁移报告查看阻断项。")
        )
    )

    on btnOpenMigrateReport pressed do
    (
        if doesFileExist lastMigrateReportTxt then shellLaunch lastMigrateReportTxt ""
    )

    on btnUpdateTools pressed do
    (
        _updateToolsFromPublic()
    )
)

createDialog RR_RigUpdateRollout

/*
Reference Rig - migration service orchestration for BIP MVP
*/

global RR_MigrateService

struct RR_MigrateServiceLib
(
    fn _timestamp =
    (
        (dotNetClass "System.DateTime").Now.ToString "yyyyMMdd_HHmmss"
    ),

    fn _safeSceneName pathValue =
    (
        local nameValue = getFilenameFile pathValue
        if nameValue == "" then nameValue = "untitled"
        nameValue
    ),

    fn _defaultOutputPath oldAnimPath =
    (
        local dirPath = getFilenamePath oldAnimPath
        local baseName = RR_MigrateService._safeSceneName oldAnimPath
        local candidate = dirPath + baseName + "_RigUpdate_v001.max"
        if not doesFileExist candidate then return candidate

        for i = 2 to 999 do
        (
            local suffix = formattedPrint i format:"03d"
            local nextPath = dirPath + baseName + "_RigUpdate_v" + suffix + ".max"
            if not doesFileExist nextPath do return nextPath
        )
        dirPath + baseName + "_RigUpdate_" + RR_MigrateService._timestamp() + ".max"
    ),

    fn _reportRoot oldAnimPath =
    (
        local root = getFilenamePath oldAnimPath + "_RigUpdateReports"
        makeDir root all:true
        root
    ),

    fn _makeReportPaths oldAnimPath =
    (
        local root = RR_MigrateService._reportRoot oldAnimPath
        local stem = RR_MigrateService._safeSceneName oldAnimPath + ".migration_" + RR_MigrateService._timestamp()
        #(
            #report_json, (root + "\\" + stem + ".json"),
            #report_txt, (root + "\\" + stem + ".txt"),
            #bip_temp_path, ((getDir #temp) + "\\RR_BipMigration_" + stem + ".bip")
        )
    ),

    fn _kvGet payload key defaultValue =
    (
        local idx = findItem payload key
        if idx > 0 and (idx + 1) <= payload.count then payload[idx + 1] else defaultValue
    ),

    fn run_bip_migration_mvp old_anim_path new_rig_path output_max_path mapping_path:undefined overwrite:false strict_ik:true =
    (
        local reportPaths = RR_MigrateService._makeReportPaths old_anim_path
        local bipTempPath = RR_MigrateService._kvGet reportPaths #bip_temp_path ""
        local reportJsonPath = RR_MigrateService._kvGet reportPaths #report_json ""
        local reportTxtPath = RR_MigrateService._kvGet reportPaths #report_txt ""

        local outputPath = if output_max_path == "" then RR_MigrateService._defaultOutputPath old_anim_path else output_max_path

        local payload = #(
            #ok, false,
            #input_paths, #(#old_anim_path, old_anim_path, #new_rig_path, new_rig_path, #mapping_path, (if mapping_path == undefined then "" else mapping_path)),
            #output_paths, #(#output_max_path, outputPath, #bip_temp_path, bipTempPath, #report_json, reportJsonPath, #report_txt, reportTxtPath),
            #precheck, #(),
            #export, #(),
            #import, #(),
            #save, #(),
            #postcheck, #(),
            #blockers, #(),
            #warnings, #(),
            #info, #(),
            #next_actions, #("进入 Phase 3 本地对象迁移")
        )

        local precheck = RR_BipTransfer.validate_bip_precheck old_anim_path new_rig_path mappingPath:mapping_path strictIK:strict_ik
        payload[(findItem payload #precheck) + 1] = precheck
        join payload[(findItem payload #blockers) + 1] (RR_MigrateService._kvGet precheck #blockers #())
        join payload[(findItem payload #warnings) + 1] (RR_MigrateService._kvGet precheck #warnings #())
        join payload[(findItem payload #info) + 1] (RR_MigrateService._kvGet precheck #info #())

        local precheckData = RR_MigrateService._kvGet precheck #data #()
        local ikSummary = #(
            #checked_count, RR_MigrateService._kvGet precheckData #ik_checked_count 0,
            #missing, RR_MigrateService._kvGet precheckData #ik_missing #(),
            #strict, strict_ik
        )
        append payload[(findItem payload #precheck) + 1] #ik_summary
        append payload[(findItem payload #precheck) + 1] ikSummary

        if not RR_MigrateService._kvGet precheck #ok false then
        (
            RR_MigrateReportWriter.write_json payload reportJsonPath
            RR_MigrateReportWriter.write_txt payload reportTxtPath
            return #(#ok, false, #report_json, reportJsonPath, #report_txt, reportTxtPath, #message, "迁移前检查阻断。")
        )

        local exportRes = RR_BipTransfer.export_bip_from_old_scene old_anim_path bipTempPath
        payload[(findItem payload #export) + 1] = exportRes
        if not RR_MigrateService._kvGet exportRes #ok false then
        (
            append payload[(findItem payload #blockers) + 1] (RR_MigrateService._kvGet exportRes #message "BIP 导出失败")
            RR_MigrateReportWriter.write_json payload reportJsonPath
            RR_MigrateReportWriter.write_txt payload reportTxtPath
            return #(#ok, false, #report_json, reportJsonPath, #report_txt, reportTxtPath, #message, "BIP 导出失败。")
        )

        local importRes = RR_BipTransfer.import_bip_to_new_scene new_rig_path bipTempPath targetBipRootName:"Bip001"
        payload[(findItem payload #import) + 1] = importRes
        if not RR_MigrateService._kvGet importRes #ok false then
        (
            append payload[(findItem payload #blockers) + 1] (RR_MigrateService._kvGet importRes #message "BIP 导入失败")
            RR_MigrateReportWriter.write_json payload reportJsonPath
            RR_MigrateReportWriter.write_txt payload reportTxtPath
            return #(#ok, false, #report_json, reportJsonPath, #report_txt, reportTxtPath, #message, "BIP 导入失败。")
        )

        local postcheckRes = RR_BipTransfer.postcheck_basic targetBipRootName:"Bip001"
        payload[(findItem payload #postcheck) + 1] = postcheckRes
        join payload[(findItem payload #warnings) + 1] (RR_MigrateService._kvGet postcheckRes #warnings #())

        local saveRes = RR_BipTransfer.save_migrated_scene outputPath overwrite:overwrite
        payload[(findItem payload #save) + 1] = saveRes
        if not RR_MigrateService._kvGet saveRes #ok false then
        (
            append payload[(findItem payload #blockers) + 1] (RR_MigrateService._kvGet saveRes #message "迁移文件保存失败")
            RR_MigrateReportWriter.write_json payload reportJsonPath
            RR_MigrateReportWriter.write_txt payload reportTxtPath
            return #(#ok, false, #report_json, reportJsonPath, #report_txt, reportTxtPath, #message, "迁移保存失败。")
        )

        payload[(findItem payload #ok) + 1] = true
        append payload[(findItem payload #info) + 1] "BIP MVP 迁移流程完成。"
        RR_MigrateReportWriter.write_json payload reportJsonPath
        RR_MigrateReportWriter.write_txt payload reportTxtPath

        #(
            #ok, true,
            #output_max_path, outputPath,
            #report_json, reportJsonPath,
            #report_txt, reportTxtPath,
            #warnings, payload[(findItem payload #warnings) + 1],
            #message, "迁移成功。"
        )
    )
)

RR_MigrateService = RR_MigrateServiceLib()

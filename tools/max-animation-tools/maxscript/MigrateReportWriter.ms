/*
Reference Rig - migration report writer for BIP MVP
*/

global RR_MigrateReportWriter

struct RR_MigrateReportWriterLib
(
    fn _escapeJson textValue =
    (
        local s = textValue as string
        s = substituteString s "\\" "\\\\"
        s = substituteString s "\"" "\\\""
        s = substituteString s "\r" "\\r"
        s = substituteString s "\n" "\\n"
        s = substituteString s "\t" "\\t"
        s
    ),

    fn _writeArray stream key values indent:"  " =
    (
        format "%\"%\": [\n" indent key to:stream
        for i = 1 to values.count do
        (
            local comma = if i < values.count then "," else ""
            format "%  \"%\"%\n" indent (RR_MigrateReportWriter._escapeJson values[i]) comma to:stream
        )
        format "%],\n" indent to:stream
    ),

    fn _kvGet payload key defaultValue =
    (
        local idx = findItem payload key
        if idx > 0 and (idx + 1) <= payload.count then payload[idx + 1] else defaultValue
    ),

    fn _appendLine stream label value =
    (
        format "%: %\n" label value to:stream
    ),

    fn write_json reportData jsonPath =
    (
        local parent = getFilenamePath jsonPath
        if parent != "" do makeDir parent all:true
        local stream = createFile jsonPath

        local inputPaths = RR_MigrateReportWriter._kvGet reportData #input_paths #()
        local outputPaths = RR_MigrateReportWriter._kvGet reportData #output_paths #()
        local precheck = RR_MigrateReportWriter._kvGet reportData #precheck #()
        local exportRes = RR_MigrateReportWriter._kvGet reportData #export #()
        local importRes = RR_MigrateReportWriter._kvGet reportData #import #()
        local saveRes = RR_MigrateReportWriter._kvGet reportData #save #()
        local postcheck = RR_MigrateReportWriter._kvGet reportData #postcheck #()
        local blockers = RR_MigrateReportWriter._kvGet reportData #blockers #()
        local warnings = RR_MigrateReportWriter._kvGet reportData #warnings #()
        local info = RR_MigrateReportWriter._kvGet reportData #info #()
        local nextActions = RR_MigrateReportWriter._kvGet reportData #next_actions #()
        local overallOk = RR_MigrateReportWriter._kvGet reportData #ok false

        format "{\n" to:stream
        format "  \"ok\": %,\n" (if overallOk then "true" else "false") to:stream
        format "  \"input_paths\": {\n" to:stream
        format "    \"old_anim_path\": \"%\",\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet inputPaths #old_anim_path "")) to:stream
        format "    \"new_rig_path\": \"%\",\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet inputPaths #new_rig_path "")) to:stream
        format "    \"mapping_path\": \"%\"\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet inputPaths #mapping_path "")) to:stream
        format "  },\n" to:stream

        format "  \"output_paths\": {\n" to:stream
        format "    \"output_max_path\": \"%\",\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet outputPaths #output_max_path "")) to:stream
        format "    \"bip_temp_path\": \"%\",\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet outputPaths #bip_temp_path "")) to:stream
        format "    \"report_json\": \"%\",\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet outputPaths #report_json "")) to:stream
        format "    \"report_txt\": \"%\"\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet outputPaths #report_txt "")) to:stream
        format "  },\n" to:stream

        format "  \"precheck\": {\n" to:stream
        format "    \"ok\": %,\n" (if RR_MigrateReportWriter._kvGet precheck #ok false then "true" else "false") to:stream
        format "    \"code\": \"%\",\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet precheck #code "")) to:stream
        format "    \"message\": \"%\",\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet precheck #message "")) to:stream
        RR_MigrateReportWriter._writeArray stream "blockers" (RR_MigrateReportWriter._kvGet precheck #blockers #()) indent:"    "
        RR_MigrateReportWriter._writeArray stream "warnings" (RR_MigrateReportWriter._kvGet precheck #warnings #()) indent:"    "
        format "    \"ik_check\": {\n" to:stream
        format "      \"checked_count\": %,\n" (RR_MigrateReportWriter._kvGet (RR_MigrateReportWriter._kvGet precheck #ik_summary #()) #checked_count 0) to:stream
        RR_MigrateReportWriter._writeArray stream "missing" (RR_MigrateReportWriter._kvGet (RR_MigrateReportWriter._kvGet precheck #ik_summary #()) #missing #()) indent:"      "
        format "      \"strict\": %\n" (if RR_MigrateReportWriter._kvGet (RR_MigrateReportWriter._kvGet precheck #ik_summary #()) #strict true then "true" else "false") to:stream
        format "    }\n" to:stream
        format "  },\n" to:stream

        format "  \"steps\": {\n" to:stream
        format "    \"export\": {\"ok\": %, \"code\": \"%\", \"message\": \"%\"},\n" (if RR_MigrateReportWriter._kvGet exportRes #ok false then "true" else "false") (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet exportRes #code "")) (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet exportRes #message "")) to:stream
        format "    \"import\": {\"ok\": %, \"code\": \"%\", \"message\": \"%\"},\n" (if RR_MigrateReportWriter._kvGet importRes #ok false then "true" else "false") (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet importRes #code "")) (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet importRes #message "")) to:stream
        format "    \"save\": {\"ok\": %, \"code\": \"%\", \"message\": \"%\"}\n" (if RR_MigrateReportWriter._kvGet saveRes #ok false then "true" else "false") (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet saveRes #code "")) (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet saveRes #message "")) to:stream
        format "  },\n" to:stream

        format "  \"postcheck\": {\n" to:stream
        format "    \"ok\": %,\n" (if RR_MigrateReportWriter._kvGet postcheck #ok false then "true" else "false") to:stream
        format "    \"code\": \"%\",\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet postcheck #code "")) to:stream
        format "    \"message\": \"%\"\n" (RR_MigrateReportWriter._escapeJson (RR_MigrateReportWriter._kvGet postcheck #message "")) to:stream
        format "  },\n" to:stream

        RR_MigrateReportWriter._writeArray stream "blockers" blockers indent:"  "
        RR_MigrateReportWriter._writeArray stream "warnings" warnings indent:"  "
        RR_MigrateReportWriter._writeArray stream "info" info indent:"  "
        RR_MigrateReportWriter._writeArray stream "next_actions" nextActions indent:"  "
        format "  \"_end\": \"eof\"\n" to:stream
        format "}\n" to:stream
        close stream
        jsonPath
    ),

    fn write_txt reportData txtPath =
    (
        local parent = getFilenamePath txtPath
        if parent != "" do makeDir parent all:true
        local stream = createFile txtPath

        local inputPaths = RR_MigrateReportWriter._kvGet reportData #input_paths #()
        local outputPaths = RR_MigrateReportWriter._kvGet reportData #output_paths #()
        local precheck = RR_MigrateReportWriter._kvGet reportData #precheck #()
        local exportRes = RR_MigrateReportWriter._kvGet reportData #export #()
        local importRes = RR_MigrateReportWriter._kvGet reportData #import #()
        local saveRes = RR_MigrateReportWriter._kvGet reportData #save #()
        local postcheck = RR_MigrateReportWriter._kvGet reportData #postcheck #()
        local blockers = RR_MigrateReportWriter._kvGet reportData #blockers #()
        local warnings = RR_MigrateReportWriter._kvGet reportData #warnings #()
        local info = RR_MigrateReportWriter._kvGet reportData #info #()
        local nextActions = RR_MigrateReportWriter._kvGet reportData #next_actions #()

        format "BIP Migration MVP Report\n\n" to:stream
        RR_MigrateReportWriter._appendLine stream "Overall OK" (RR_MigrateReportWriter._kvGet reportData #ok false)
        format "\nInput/Output\n" to:stream
        RR_MigrateReportWriter._appendLine stream "Old Anim" (RR_MigrateReportWriter._kvGet inputPaths #old_anim_path "")
        RR_MigrateReportWriter._appendLine stream "New Rig" (RR_MigrateReportWriter._kvGet inputPaths #new_rig_path "")
        RR_MigrateReportWriter._appendLine stream "Output Max" (RR_MigrateReportWriter._kvGet outputPaths #output_max_path "")
        RR_MigrateReportWriter._appendLine stream "BIP Temp" (RR_MigrateReportWriter._kvGet outputPaths #bip_temp_path "")

        format "\nPrecheck\n" to:stream
        RR_MigrateReportWriter._appendLine stream "OK" (RR_MigrateReportWriter._kvGet precheck #ok false)
        RR_MigrateReportWriter._appendLine stream "Code" (RR_MigrateReportWriter._kvGet precheck #code "")
        RR_MigrateReportWriter._appendLine stream "Message" (RR_MigrateReportWriter._kvGet precheck #message "")

        format "\nSteps\n" to:stream
        RR_MigrateReportWriter._appendLine stream "Export" (RR_MigrateReportWriter._kvGet exportRes #message "")
        RR_MigrateReportWriter._appendLine stream "Import" (RR_MigrateReportWriter._kvGet importRes #message "")
        RR_MigrateReportWriter._appendLine stream "Save" (RR_MigrateReportWriter._kvGet saveRes #message "")

        format "\nPostcheck\n" to:stream
        RR_MigrateReportWriter._appendLine stream "OK" (RR_MigrateReportWriter._kvGet postcheck #ok false)
        RR_MigrateReportWriter._appendLine stream "Code" (RR_MigrateReportWriter._kvGet postcheck #code "")
        RR_MigrateReportWriter._appendLine stream "Message" (RR_MigrateReportWriter._kvGet postcheck #message "")

        format "\nBlockers (%):\n" blockers.count to:stream
        for item in blockers do format "  - %\n" item to:stream
        format "\nWarnings (%):\n" warnings.count to:stream
        for item in warnings do format "  - %\n" item to:stream
        format "\nInfo (%):\n" info.count to:stream
        for item in info do format "  - %\n" item to:stream
        format "\nNext Actions (%):\n" nextActions.count to:stream
        for item in nextActions do format "  - %\n" item to:stream

        close stream
        txtPath
    )
)

RR_MigrateReportWriter = RR_MigrateReportWriterLib()

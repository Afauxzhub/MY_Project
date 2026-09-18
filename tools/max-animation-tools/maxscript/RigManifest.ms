/*
Reference Rig - Manifest and node metadata helpers
Target: 3ds Max 2020 / MaxScript

Load this file before scanner, relinker, updater, or UI modules.
*/

global RR_MetaCA
global RR_Manifest

attributes RR_MetaCA
(
    parameters main rollout:params
    (
        rrGuid type:#string default:""
        rrRole type:#string default:""
        rrVersionIntroduced type:#string default:""
        rrStable type:#boolean default:false
        rrReplacePolicy type:#string default:"ignore"
        rrParentGuid type:#string default:""
    )

    rollout params "Reference Rig Metadata"
    (
        editText edtGuid "Guid" text:rrGuid readOnly:true
        editText edtRole "Role" text:rrRole readOnly:true
        editText edtVersion "Introduced" text:rrVersionIntroduced readOnly:true
        checkbox chkStable "Stable" checked:rrStable enabled:false
        editText edtPolicy "Policy" text:rrReplacePolicy readOnly:true
        editText edtParent "Parent Guid" text:rrParentGuid readOnly:true
    )
)

struct RR_NodeRecord
(
    guid = "",
    name = "",
    role = "",
    stable = false,
    parentGuid = "",
    replacePolicy = "ignore"
)

struct RR_MigrationRecord
(
    fromVersion = "",
    toVersion = "",
    oldGuid = "",
    newGuid = "",
    reason = ""
)

struct RR_ManifestData
(
    schema = "referenceRigManifest.v1",
    character = "",
    rigVersion = "",
    maxVersion = "2020",
    rigFile = "",
    modelFile = "",
    bipCorePolicy = "preserve_anim_no_replace",
    nodes = #(),
    migrations = #()
)

struct RR_ManifestLib
(
    fn _readAllText filePath =
    (
        if not doesFileExist filePath then
        (
            throw ("Manifest file does not exist: " + filePath)
        )

        local stream = openFile filePath mode:"r"
        local text = readChars stream (getFileSize filePath)
        close stream
        text
    ),

    fn _serializer =
    (
        try(dotNet.loadAssembly "System.Web.Extensions")catch()
        dotNetObject "System.Web.Script.Serialization.JavaScriptSerializer"
    ),

    fn _getValue dict key defaultValue =
    (
        if dict == undefined then return defaultValue
        if dict.ContainsKey key then dict.Item[key] else defaultValue
    ),

    fn _asBool value =
    (
        case classOf value of
        (
            BooleanClass: value
            String: (toLower value == "true")
            default: false
        )
    ),

    fn readManifest filePath =
    (
        local jsonText = RR_Manifest._readAllText filePath
        local data = (RR_Manifest._serializer()).DeserializeObject jsonText
        local manifest = RR_ManifestData()

        manifest.schema = RR_Manifest._getValue data "schema" manifest.schema
        manifest.character = RR_Manifest._getValue data "character" ""
        manifest.rigVersion = RR_Manifest._getValue data "rigVersion" ""
        manifest.maxVersion = RR_Manifest._getValue data "maxVersion" "2020"
        manifest.rigFile = RR_Manifest._getValue data "rigFile" ""
        manifest.modelFile = RR_Manifest._getValue data "modelFile" ""

        local compatibility = RR_Manifest._getValue data "compatibility" undefined
        manifest.bipCorePolicy = RR_Manifest._getValue compatibility "bipCorePolicy" "preserve_anim_no_replace"

        local nodeArray = RR_Manifest._getValue data "nodes" #()
        for nodeDict in nodeArray do
        (
            local record = RR_NodeRecord()
            record.guid = RR_Manifest._getValue nodeDict "guid" ""
            record.name = RR_Manifest._getValue nodeDict "name" ""
            record.role = RR_Manifest._getValue nodeDict "role" ""
            record.stable = RR_Manifest._asBool (RR_Manifest._getValue nodeDict "stable" false)
            record.parentGuid = RR_Manifest._getValue nodeDict "parentGuid" ""
            record.replacePolicy = RR_Manifest._getValue nodeDict "replacePolicy" "ignore"
            append manifest.nodes record
        )

        local migrationArray = RR_Manifest._getValue data "migrations" #()
        for migrationDict in migrationArray do
        (
            local maps = RR_Manifest._getValue migrationDict "nodeMap" #()
            for mapDict in maps do
            (
                local migration = RR_MigrationRecord()
                migration.fromVersion = RR_Manifest._getValue migrationDict "fromVersion" ""
                migration.toVersion = RR_Manifest._getValue migrationDict "toVersion" ""
                migration.oldGuid = RR_Manifest._getValue mapDict "oldGuid" ""
                migration.newGuid = RR_Manifest._getValue mapDict "newGuid" ""
                migration.reason = RR_Manifest._getValue mapDict "reason" ""
                append manifest.migrations migration
            )
        )

        manifest
    ),

    fn ensureMeta node =
    (
        if node == undefined then return false
        if not (isProperty node #rrGuid) do
        (
            custAttributes.add node RR_MetaCA
        )
        true
    ),

    fn applyRecordToNode node record version:"" =
    (
        if not (RR_Manifest.ensureMeta node) then return false
        node.rrGuid = record.guid
        node.rrRole = record.role
        node.rrStable = record.stable
        node.rrReplacePolicy = record.replacePolicy
        node.rrParentGuid = record.parentGuid
        node.rrVersionIntroduced = if version == "" then "unknown" else version
        true
    ),

    fn getNodeGuid node =
    (
        if node == undefined then return ""
        if isProperty node #rrGuid then node.rrGuid else ""
    ),

    fn getNodeRole node =
    (
        if node == undefined then return ""
        if isProperty node #rrRole then node.rrRole else ""
    ),

    fn getNodeStable node =
    (
        if node == undefined then return false
        if isProperty node #rrStable then node.rrStable else false
    ),

    fn findNodeByGuid guid nodesToSearch:objects =
    (
        for node in nodesToSearch where (RR_Manifest.getNodeGuid node) == guid do return node
        undefined
    ),

    fn findRecordByGuid manifest guid =
    (
        for record in manifest.nodes where record.guid == guid do return record
        undefined
    ),

    fn findRecordByName manifest nodeName =
    (
        for record in manifest.nodes where record.name == nodeName do return record
        undefined
    ),

    fn findMigration manifest oldGuid =
    (
        for migration in manifest.migrations where migration.oldGuid == oldGuid do return migration
        undefined
    ),

    fn buildNodeMap oldManifest newManifest =
    (
        local map = dotNetObject "System.Collections.Generic.Dictionary[String,String]"

        for oldRecord in oldManifest.nodes do
        (
            local newRecord = RR_Manifest.findRecordByGuid newManifest oldRecord.guid
            if newRecord != undefined then
            (
                map.Item[oldRecord.guid] = newRecord.guid
            )
            else
            (
                local migration = RR_Manifest.findMigration newManifest oldRecord.guid
                if migration != undefined do map.Item[oldRecord.guid] = migration.newGuid
            )
        )

        map
    ),

    fn stampSceneVersion manifest =
    (
        setUserProp rootNode "ReferenceRigCharacter" manifest.character
        setUserProp rootNode "ReferenceRigVersion" manifest.rigVersion
        setUserProp rootNode "ReferenceRigManifest" manifest.schema
        true
    ),

    fn getSceneRigVersion =
    (
        local value = getUserProp rootNode "ReferenceRigVersion"
        if value == undefined then "" else value
    )
)

RR_Manifest = RR_ManifestLib()

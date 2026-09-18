/*
Reference Rig - BIP validator
Requires: RigManifest.ms, RigScanner.ms
*/

global RR_BipValidator

struct RR_BipValidationResult
(
    ok = true,
    mode = "unknown",
    bipRootName = "",
    bipNodeCount = 0,
    warnings = #(),
    errors = #()
)

struct RR_BipValidatorLib
(
    fn _looksLikeBipRoot node =
    (
        if node == undefined then return false
        matchPattern node.name pattern:"Bip*" ignoreCase:true and node.parent == undefined
    ),

    fn _detectMode bipRoot =
    (
        local mode = "freeform_or_unknown"

        try
        (
            local footstepCount = biped.getNumFootsteps bipRoot.controller
            if footstepCount > 0 then mode = "footstep"
        )
        catch
        (
            mode = "freeform_or_unknown"
        )

        mode
    ),

    fn validate report manifest:undefined =
    (
        local result = RR_BipValidationResult()
        result.bipNodeCount = report.bipNodes.count

        if report.bipNodes.count == 0 then
        (
            result.ok = false
            append result.errors "No BIP nodes found. The updater must not continue."
            return result
        )

        local rootNode = undefined
        for info in report.bipNodes while rootNode == undefined do
        (
            local node = getNodeByName info.nodeName
            if RR_BipValidator._looksLikeBipRoot node do rootNode = node
        )

        if rootNode == undefined then
        (
            append result.warnings "BIP root was not confidently detected; continuing with node-count validation only."
        )
        else
        (
            result.bipRootName = rootNode.name
            result.mode = RR_BipValidator._detectMode rootNode
        )

        if manifest != undefined do
        (
            for record in manifest.nodes where record.role == "bip_core" and record.stable do
            (
                local node = getNodeByName record.name
                if node == undefined do
                (
                    result.ok = false
                    append result.errors ("Missing stable BIP node: " + record.name + " / " + record.guid)
                )
            )
        )

        result
    ),

    fn appendToReport validation filePath =
    (
        local stream = openFile filePath mode:"a"
        format "\nBIP Validation\n" to:stream
        format "OK: %\n" validation.ok to:stream
        format "Mode: %\n" validation.mode to:stream
        format "Root: %\n" validation.bipRootName to:stream
        format "Node Count: %\n" validation.bipNodeCount to:stream

        format "Warnings: %\n" validation.warnings.count to:stream
        for item in validation.warnings do format "  - %\n" item to:stream

        format "Errors: %\n" validation.errors.count to:stream
        for item in validation.errors do format "  - %\n" item to:stream

        close stream
        filePath
    )
)

RR_BipValidator = RR_BipValidatorLib()

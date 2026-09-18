/*
Reference Rig - Constraint target relinker
Requires: RigManifest.ms, RigScanner.ms

The relinker is intentionally conservative. It preserves existing controllers and
only replaces target node references. If the active controller does not expose a
safe in-place target replacement API, the item is reported instead of rebuilt.
*/

global RR_ConstraintRelinker

struct RR_RelinkItem
(
    ownerName = "",
    controllerPath = "",
    constraintClass = "",
    targetIndex = 0,
    oldTargetName = "",
    oldGuid = "",
    newTargetName = "",
    newGuid = "",
    status = "pending",
    message = ""
)

struct RR_RelinkReport
(
    attempted = 0,
    changed = 0,
    skipped = 0,
    errors = #(),
    items = #()
)

struct RR_ConstraintRelinkerLib
(
    fn _className value =
    (
        if value == undefined then "" else (classOf value as string)
    ),

    fn _isSupported controller =
    (
        if controller == undefined then return false
        local cls = RR_ConstraintRelinker._className controller
        findItem #("Position_Constraint", "Orientation_Constraint", "LookAt_Constraint", "Link_Constraint", "Parent_Constraint") cls > 0
    ),

    fn _getConstraintTargetCount controller =
    (
        local countValue = 0
        try countValue = controller.getNumTargets() catch countValue = 0
        countValue
    ),

    fn _getConstraintTarget controller index =
    (
        local targetNode = undefined
        try targetNode = controller.getNode index catch targetNode = undefined
        if targetNode == undefined do
        (
            try targetNode = controller.getTarget index catch targetNode = undefined
        )
        targetNode
    ),

    fn _replaceTargetInPlace controller index newTarget =
    (
        local replaced = false

        try
        (
            controller.setNode index newTarget
            replaced = true
        )
        catch replaced = false

        if not replaced do
        (
            try
            (
                controller.setTarget index newTarget
                replaced = true
            )
            catch replaced = false
        )

        if not replaced do
        (
            try
            (
                controller.targets[index].target = newTarget
                replaced = true
            )
            catch replaced = false
        )

        replaced
    ),

    fn _resolveGuid oldGuid oldManifest newManifest nodeMap =
    (
        if oldGuid == "" then return ""

        if nodeMap != undefined and nodeMap.ContainsKey oldGuid do
        (
            return nodeMap.Item[oldGuid]
        )

        local oldRecord = RR_Manifest.findRecordByGuid oldManifest oldGuid
        if oldRecord != undefined do
        (
            local byGuid = RR_Manifest.findRecordByGuid newManifest oldGuid
            if byGuid != undefined do return byGuid.guid

            local byName = RR_Manifest.findRecordByName newManifest oldRecord.name
            if byName != undefined and byName.stable do return byName.guid
        )

        ""
    ),

    fn _resolveNewNode oldTarget oldManifest newManifest nodeMap =
    (
        local oldGuid = RR_Manifest.getNodeGuid oldTarget
        local newGuid = RR_ConstraintRelinker._resolveGuid oldGuid oldManifest newManifest nodeMap

        if newGuid != "" do
        (
            local byGuid = RR_Manifest.findNodeByGuid newGuid
            if byGuid != undefined do return #(byGuid, newGuid)
        )

        if oldTarget != undefined do
        (
            local newRecord = RR_Manifest.findRecordByName newManifest oldTarget.name
            if newRecord != undefined and newRecord.stable do
            (
                local byName = getNodeByName newRecord.name
                if byName != undefined do return #(byName, newRecord.guid)
            )
        )

        #(undefined, newGuid)
    ),

    fn _processController report owner controller channel oldManifest newManifest nodeMap dryRun:false =
    (
        if not (RR_ConstraintRelinker._isSupported controller) then return false

        local countValue = RR_ConstraintRelinker._getConstraintTargetCount controller

        for i = 1 to countValue do
        (
            local oldTarget = RR_ConstraintRelinker._getConstraintTarget controller i
            local oldGuid = RR_Manifest.getNodeGuid oldTarget
            local oldStable = RR_Manifest.getNodeStable oldTarget

            if oldGuid == "" and not oldStable then
            (
                report.skipped += 1
            )
            else
            (
                report.attempted += 1
                local resolved = RR_ConstraintRelinker._resolveNewNode oldTarget oldManifest newManifest nodeMap
                local newTarget = resolved[1]
                local newGuid = resolved[2]

                local item = RR_RelinkItem()
                item.ownerName = owner.name
                item.controllerPath = owner.name + "." + channel
                item.constraintClass = RR_ConstraintRelinker._className controller
                item.targetIndex = i
                item.oldTargetName = if oldTarget == undefined then "<missing>" else oldTarget.name
                item.oldGuid = oldGuid
                item.newTargetName = if newTarget == undefined then "<missing>" else newTarget.name
                item.newGuid = newGuid

                if newTarget == undefined then
                (
                    item.status = "error"
                    item.message = "No safe target mapping found."
                    append report.errors (item.controllerPath + " target " + (i as string) + ": " + item.message)
                )
                else if oldTarget == newTarget then
                (
                    item.status = "skipped"
                    item.message = "Target already points at the current node."
                    report.skipped += 1
                )
                else if dryRun then
                (
                    item.status = "dryRun"
                    item.message = "Target can be relinked."
                )
                else
                (
                    local replaced = RR_ConstraintRelinker._replaceTargetInPlace controller i newTarget
                    if replaced then
                    (
                        item.status = "changed"
                        item.message = "Target node reference replaced in place."
                        report.changed += 1
                    )
                    else
                    (
                        item.status = "error"
                        item.message = "Controller does not expose safe in-place target replacement."
                        append report.errors (item.controllerPath + " target " + (i as string) + ": " + item.message)
                    )
                )

                append report.items item
            )
        )

        true
    ),

    fn relinkScene oldManifest newManifest dryRun:false =
    (
        local report = RR_RelinkReport()
        local nodeMap = RR_Manifest.buildNodeMap oldManifest newManifest

        for node in objects do
        (
            local transformController = node.controller

            RR_ConstraintRelinker._processController report node transformController "transform" oldManifest newManifest nodeMap dryRun:dryRun

            if isProperty transformController #position do
            (
                RR_ConstraintRelinker._processController report node transformController.position "position" oldManifest newManifest nodeMap dryRun:dryRun
            )

            if isProperty transformController #rotation do
            (
                RR_ConstraintRelinker._processController report node transformController.rotation "rotation" oldManifest newManifest nodeMap dryRun:dryRun
            )

            if isProperty transformController #scale do
            (
                RR_ConstraintRelinker._processController report node transformController.scale "scale" oldManifest newManifest nodeMap dryRun:dryRun
            )
        )

        report
    ),

    fn writeReport report filePath =
    (
        local stream = openFile filePath mode:"a"
        format "\nConstraint Relink Report\n" to:stream
        format "Attempted: %\n" report.attempted to:stream
        format "Changed: %\n" report.changed to:stream
        format "Skipped: %\n" report.skipped to:stream
        format "Errors: %\n" report.errors.count to:stream
        for item in report.errors do format "  - %\n" item to:stream

        format "\nItems:\n" to:stream
        for item in report.items do
        (
            format "  - % [%] target[%] % -> % | % | %\n" item.controllerPath item.constraintClass item.targetIndex item.oldTargetName item.newTargetName item.status item.message to:stream
        )

        close stream
        filePath
    )
)

RR_ConstraintRelinker = RR_ConstraintRelinkerLib()

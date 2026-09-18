/*
Reference Rig - Read-only scene scanner
Requires: RigManifest.ms
*/

global RR_Scanner

struct RR_ConstraintTargetInfo
(
    ownerName = "",
    controllerPath = "",
    constraintClass = "",
    targetIndex = 0,
    targetName = "",
    targetGuid = "",
    targetRole = "",
    isStableTarget = false,
    status = "ok"
)

struct RR_NodeScanInfo
(
    nodeName = "",
    nodeClass = "",
    guid = "",
    role = "",
    stable = false,
    replacePolicy = "",
    isBip = false,
    isReferenced = false
)

struct RR_ScanReport
(
    sceneFile = "",
    rigVersion = "",
    bipNodes = #(),
    interfaceNodes = #(),
    constraints = #(),
    warnings = #(),
    errors = #()
)

struct RR_ScannerLib
(
    supportedConstraintClasses = #("Position_Constraint", "Orientation_Constraint", "LookAt_Constraint", "Link_Constraint", "Attachment_Constraint", "Path_Constraint", "Parent_Constraint"),

    fn _className value =
    (
        if value == undefined then "" else (classOf value as string)
    ),

    fn _isBipNode node =
    (
        local cls = RR_Scanner._className node
        matchPattern cls pattern:"*Biped*" ignoreCase:true or matchPattern node.name pattern:"Bip*" ignoreCase:true
    ),

    fn _isReferencedNode node =
    (
        false
    ),

    fn _addNodeInfo report node =
    (
        local info = RR_NodeScanInfo()
        info.nodeName = node.name
        info.nodeClass = RR_Scanner._className node
        info.guid = RR_Manifest.getNodeGuid node
        info.role = RR_Manifest.getNodeRole node
        info.stable = RR_Manifest.getNodeStable node
        info.replacePolicy = if isProperty node #rrReplacePolicy then node.rrReplacePolicy else ""
        info.isBip = RR_Scanner._isBipNode node
        info.isReferenced = RR_Scanner._isReferencedNode node

        if info.isBip do append report.bipNodes info
        if info.guid != "" do append report.interfaceNodes info
        info
    ),

    fn _controllerIsConstraint controller =
    (
        if controller == undefined then return false
        local cls = RR_Scanner._className controller
        for supported in RR_Scanner.supportedConstraintClasses where cls == supported do return true
        false
    ),

    fn _controllerPath owner channel =
    (
        owner.name + "." + channel
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

    fn _scanConstraintController report owner controller channel =
    (
        local countValue = RR_Scanner._getConstraintTargetCount controller

        if countValue == 0 then
        (
            append report.warnings ("Constraint has no readable targets: " + owner.name + " / " + channel)
        )
        else
        (
            for i = 1 to countValue do
            (
                local targetNode = RR_Scanner._getConstraintTarget controller i
                local targetGuid = RR_Manifest.getNodeGuid targetNode
                local targetRole = RR_Manifest.getNodeRole targetNode
                local isStable = RR_Manifest.getNodeStable targetNode

                local targetInfo = RR_ConstraintTargetInfo()
                targetInfo.ownerName = owner.name
                targetInfo.controllerPath = RR_Scanner._controllerPath owner channel
                targetInfo.constraintClass = RR_Scanner._className controller
                targetInfo.targetIndex = i
                targetInfo.targetName = if targetNode == undefined then "<missing>" else targetNode.name
                targetInfo.targetGuid = targetGuid
                targetInfo.targetRole = targetRole
                targetInfo.isStableTarget = isStable
                targetInfo.status = if targetNode == undefined then "missing" else "ok"
                append report.constraints targetInfo
            )
        )
    ),

    fn _scanNodeControllers report node =
    (
        local transformController = node.controller

        if RR_Scanner._controllerIsConstraint transformController do
        (
            RR_Scanner._scanConstraintController report node transformController "transform"
        )

        if isProperty transformController #position and RR_Scanner._controllerIsConstraint transformController.position do
        (
            RR_Scanner._scanConstraintController report node transformController.position "position"
        )

        if isProperty transformController #rotation and RR_Scanner._controllerIsConstraint transformController.rotation do
        (
            RR_Scanner._scanConstraintController report node transformController.rotation "rotation"
        )

        if isProperty transformController #scale and RR_Scanner._controllerIsConstraint transformController.scale do
        (
            RR_Scanner._scanConstraintController report node transformController.scale "scale"
        )
    ),

    fn scanScene includeReferenced:false =
    (
        local report = RR_ScanReport()
        report.sceneFile = maxFilePath
        report.rigVersion = RR_Manifest.getSceneRigVersion()

        for node in objects do
        (
            local info = RR_Scanner._addNodeInfo report node
            if includeReferenced or not info.isReferenced do
            (
                RR_Scanner._scanNodeControllers report node
            )
        )

        if report.bipNodes.count == 0 do append report.errors "No BIP/Biped nodes were found."
        report
    ),

    fn writeReport report filePath =
    (
        local stream = createFile filePath
        format "Reference Rig Scan Report\n" to:stream
        format "Scene: %\n" report.sceneFile to:stream
        format "Rig Version: %\n\n" report.rigVersion to:stream

        format "BIP Nodes: %\n" report.bipNodes.count to:stream
        for item in report.bipNodes do format "  - % [%]\n" item.nodeName item.nodeClass to:stream

        format "\nInterface Nodes: %\n" report.interfaceNodes.count to:stream
        for item in report.interfaceNodes do format "  - % | % | % | stable:%\n" item.nodeName item.guid item.role item.stable to:stream

        format "\nConstraints: %\n" report.constraints.count to:stream
        for item in report.constraints do
        (
            format "  - % target[%] -> % guid:% status:%\n" item.controllerPath item.targetIndex item.targetName item.targetGuid item.status to:stream
        )

        format "\nWarnings: %\n" report.warnings.count to:stream
        for item in report.warnings do format "  - %\n" item to:stream

        format "\nErrors: %\n" report.errors.count to:stream
        for item in report.errors do format "  - %\n" item to:stream

        close stream
        filePath
    )
)

RR_Scanner = RR_ScannerLib()

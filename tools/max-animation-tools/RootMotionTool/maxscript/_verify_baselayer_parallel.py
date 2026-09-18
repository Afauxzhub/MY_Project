# -*- coding: utf-8 -*-
"""Static verification for the parallel Proxy Root entry (no 3ds Max required)."""
from __future__ import print_function, unicode_literals
import io
import os
import re
import sys

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)
INSTALL = os.path.dirname(ROOT)


def read(path):
    return io.open(path, encoding="utf-8").read()


def main():
    checks = []
    legacy_ms = read(os.path.join(ROOT, "maxscript", "rm_indoor_backend.ms"))
    checks.append(
        (
            "legacy has createLayer RM_Fix",
            'biped.createLayer bipCtrl layerIdxRM "RM_Fix"' in legacy_ms,
        )
    )
    checks.append(
        ("legacy still has RunExport fn", "fn RMTool_IndoorBackend_RunExport " in legacy_ms)
    )
    checks.append(
        ("legacy has NO RunExport_BaseLayer", "RunExport_BaseLayer" not in legacy_ms)
    )

    bl = read(os.path.join(ROOT, "maxscript", "rm_indoor_backend_baselayer.ms"))
    checks.append(
        (
            "baselayer has RunExport_BaseLayer",
            "fn RMTool_IndoorBackend_RunExport_BaseLayer " in bl,
        )
    )
    checks.append(("baselayer version", 'RMTool_Baselayer_BackendVersion = "V3.18-NearZeroScaleWorldReconcile"' in bl))
    checks.append(("WallHit no-layer Head height uses adjusted Bip pose", "fn RMTool_Backend_GetWallHitPoseNodePosition" in legacy_ms and "sourceNodeTM * (inverse sourceBipTM) * adjustedTransforms[frameIndex]" in legacy_ms and "RMTool_Backend_GetWallHitPoseNodePosition headNode bipObj adjustedTransforms rsEndIdx totalStartF" in legacy_ms and "RMTool_Backend_GetWallHitPoseNodePosition headNode bipObj adjustedTransforms peakIdx totalStartF" in legacy_ms))
    proxy = read(os.path.join(ROOT, "maxscript", "rm_proxy_fbx_export.ms"))
    hide_scale = read(os.path.join(ROOT, "maxscript", "hide_scale_bake.ms"))
    checks.append(("export progress UI and topmost dialogs in ms", "fn RMTool_Proxy_ProgressShow" in proxy and "fn RMTool_Proxy_ProgressUpdate" in proxy and "fn RMTool_Proxy_ProgressHide" in proxy and "fn RMTool_Proxy_TopMostQuery" in proxy and "RMTool_Proxy_ProgressShow" in bl and "RMTool_Proxy_ProgressHide" in bl and "RMTool_Proxy_TopMostQuery" in bl and "TopMost = true" in proxy and ").DoEvents" not in proxy))
    checks.append(("proxy version", 'RMTool_Proxy_BackendVersion = "V3.30-WallHitTranslationOnlyPoseSample"' in proxy))
    checks.append(("ADV WallHit applies COM pose delta to exported Skin Pelvis branch", '"bone_skin_bip001 pelvis"' in proxy and "local poseBranchIndex = bipIndex" in proxy and "sourceBipTransforms totalStartF sampleFrame" in proxy and "RMTool_Proxy_IsDescendantOrSelf sourceNodes[i] poseBranchRoot" in proxy and "WallHit COM pose branch missing" in proxy and "poseBranch=" in proxy))
    checks.append(("current WallHit COM override remains translation-only", "local adjustedTM = copy sourceTransforms[idx]" in bl and "adjustedTM.pos = adjustedPos[idx]" in bl and "append adjustedTransforms adjustedTM" in bl and "external constraint compensation supports translation-only body pose deltas" in proxy))
    checks.append(("WallHit sub-frame target preserves live Biped rotation and scale", "fn RMTool_Proxy_BuildTranslationOnlyPoseTarget" in proxy and "local targetBipTM = copy sourceBipTM" in proxy and "targetBipTM.pos = sampledPoseTM.pos" in proxy and proxy.count("if usePoseTransformOverride do targetBipTM = RMTool_Proxy_BuildTranslationOnlyPoseTarget sourceBipTM poseBipTransforms totalStartF sampleFrame") == 1 and proxy.count("if usePoseTransformOverride do midpointTargetBipTM = RMTool_Proxy_BuildTranslationOnlyPoseTarget midpointSourceBipTM poseBipTransforms totalStartF midpointFrame") == 1))
    checks.append(("non-WallHit and outdoor contexts keep pose override disabled", "proxyCustomOffset wallHitRootMotion useAdvExport" in bl and "desiredRootTransforms s e [0,0,0] false useAdvExport" in proxy))
    checks.append(("proxy resolves multi-target Link and weighted Position constraints per sample", "fn RMTool_Proxy_CollectPoseConstraintDescriptors" in proxy and "fn RMTool_Proxy_GetNodePoseTranslationInfluence" in proxy and "ctrl.getFrameNo targetIndex" in proxy and "ctrl.getWeight targetIndex" in proxy and "weightedInfluence / totalWeight" in proxy and "Link-to-World does not follow COM" in proxy and "constraint-aware external pose nodes" in proxy))
    checks.append(("proxy applies recursive translation influence to dense and midpoint samples", "fn RMTool_Proxy_ApplyPoseTranslationInfluences" in proxy and "poseOffset * influence" in proxy and "RMTool_Proxy_ApplyPoseTranslationInfluences sourceWorldTMs targetWorldTMs" in proxy and "RMTool_Proxy_ApplyPoseTranslationInfluences midpointSourceWorldTMs midpointTargetWorldTMs" in proxy and "externalPoseConstraintNodes=" in proxy))
    checks.append(("proxy gates ambiguous constraint reconstructions only while pose can differ", "poseMayDiffer = usePoseTransformOverride" in proxy and "stacked position constraints are ambiguous" in proxy and "position constraint inside List controller requires explicit blend support" in proxy and "unsupported position constraint" in proxy and "supports translation-only body pose deltas" in proxy and "LookAt target has different body translation influence" in proxy))
    checks.append(("proxy split export isolates task-local Model PRS", "fn RMTool_Proxy_CaptureTaskLocalTransformControllers" in proxy and "copy originalPositionController" in proxy and "copy originalRotationController" in proxy and "copy originalScaleController" in proxy and "local taskLocalModelNodes = for node in proxyNodes collect node" in proxy and "for morphMesh in morphMeshes" in proxy and "RMTool_Proxy_TrimAxisControllerKeys axisController startF endF" in proxy and "RMTool_Proxy_RestoreTaskLocalTransformControllers taskTransformContext" in proxy and proxy.index("RMTool_Proxy_RestoreTaskLocalTransformControllers taskTransformContext") < proxy.index("if movedRoot do try (animate off (move proxyNodes[1] (-totalOffset)))")))
    checks.append(("proxy split export isolates auto-included live Skin hierarchy PRS", "fn RMTool_Proxy_CollectLiveSkinDependencyNodes" in proxy and "skinOps.GetBoneNodes skinModifier" in proxy and "while current != undefined and isValidNode current" in proxy and "fn RMTool_Proxy_FilterCopyableTaskLocalTransformNodes" in proxy and "liveDependencyTransformContext = RMTool_Proxy_CaptureTaskLocalTransformControllers" in proxy and "local taskLocalScaleNodes = for node in taskLocalModelNodes collect node" in proxy and "for dependencyNode in liveDependencyNodes" in proxy and "RMTool_Proxy_ExportDenseWithHideScale taskLocalScaleNodes" in proxy and "RMTool_Proxy_RestoreTaskLocalTransformControllers liveDependencyTransformContext" in proxy and proxy.index("RMTool_Proxy_RestoreTaskLocalTransformControllers liveDependencyTransformContext") < proxy.index("RMTool_Proxy_RestoreTaskLocalTransformControllers taskTransformContext")))
    checks.append(("duplicate export paths keep hard gate with artist-facing hierarchy warning", "duplicate export hierarchy paths:" in proxy and 'throw "绑定层级被修改，无法导出，请检查文件后重新尝试。" debugBreak:false' in proxy))
    checks.append(("duplicate hierarchy has non-throwing preflight before backend export", "fn RMTool_Proxy_FindDuplicateExportHierarchyPathsForScene" in proxy and "Read-only preflight used by Python before the export backend starts" in proxy and "preflight duplicate export hierarchy paths:" in proxy))
    checks.append(("proxy permits duplicate leaf names but rejects duplicate hierarchy paths", "accepted duplicate leaf names with distinct hierarchy paths" in proxy and "RMTool_Proxy_FindDuplicateHierarchyPaths sourceNames parentIndices" in proxy and "duplicate source hierarchy paths" in proxy and "duplicate export hierarchy paths" in proxy and "ProxyRoot duplicate source names:" not in proxy and "export-name collisions=" not in proxy))
    checks.append(("proxy axis validation skips rotation-repaired frames", "degenerateRepairedFrameFlags" in proxy and "nodeRepairedFlags[frameIndex] = true" in proxy and "degenerateRepairedFrameFlags[skipIndex][validationFrameIndex]" in proxy))
    checks.append(("progress window dark themed with full hint", "请勿操作3ds Max，等待发布完成。" in proxy and "FromArgb 45 45 45" in proxy and "FromArgb 61 138 61" in proxy and "440 178" in proxy))
    checks.append(("proxy repairs degenerate local rotations from zero-scale visibility frames", 'currentStage = "repairDegenerateLocalRotations"' in proxy and "degenerate local rotations repaired" in proxy and "matrix3 repairSourceTM.row1 repairSourceTM.row2 repairSourceTM.row3 localTM.row4" in proxy and "degenerateRotRepaired=" in proxy and "minTargetRowLen=" in proxy and "minTargetAbsDet=" in proxy))
    checks.append(("proxy rejects sheared zero-scale rotation references", "fn RMTool_Proxy_IsValidRigidRotationTM" in proxy and "abs (det - 1.0)" in proxy and "abs (dot r1 r2)" in proxy and "RMTool_Proxy_IsValidRigidRotationTM probeTM" in proxy and "RMTool_Proxy_IsValidRigidRotationTM localTM" in proxy))
    checks.append(("proxy records source rotation validity before scale stripping", "fn RMTool_Proxy_IsSourceRotationDefined" in proxy and "not (RMTool_Proxy_IsWorldTransformSingular tm)" in proxy and "sourceRotationDefinedFrameFlags" in proxy and proxy.index("RMTool_Proxy_IsSourceRotationDefined tm") < proxy.index("RMTool_Backend_TMNoScale tm") and "sourceRotationDefinedFrameFlags[frameIndex][i] and RMTool_Proxy_IsValidRigidRotationTM" in proxy))
    checks.append(("proxy axis validation skips degenerate zero-scale subtrees", "local frameAxisSkip = #()" in proxy and "frameAxisSkip[skipParentIndex]" in proxy and "degenerateAxisSkipCount" in proxy and "axis validation skipped degenerate zero-scale world frames" in proxy and "bakeOrder[orderIndex]" in proxy))
    checks.append(("numeric gates soft-fail into validationWarnings", "local validationWarnings = #()" in proxy and "append validationWarnings" in proxy and "validationWarnings=" in proxy and "proxyContext.count >= 25" in bl and "queryBox" in bl and "batch export aborted" in bl and "RMTool_Proxy_CleanupContext proxyContext" in bl and "user chose to export despite validation warnings" in bl))
    checks.append(("proxy adaptive hierarchy position gate", 'hierarchyMinimumPositionTolerance = units.decodeValue "0.2cm"' in proxy and 'hierarchyAbsolutePositionCap = units.decodeValue "0.6cm"' in proxy and "hierarchyPropagationFactor = 1.5" in proxy and "RMTool_Proxy_GetAdaptivePositionTolerance" in proxy and "maxHierarchyPositionRatio > 1.0" in proxy))
    checks.append(("proxy hierarchy axis gate", "hierarchyAxisTolerance = 0.002" in proxy and "maxAxisError > hierarchyAxisTolerance" in proxy))
    checks.append(("proxy Root/Bip critical gate", 'criticalPositionTolerance = units.decodeValue "0.01cm"' in proxy and "criticalGateFailed" in proxy and "maxBipAxisError" in proxy))
    checks.append(("proxy creates no-stretch Euler bake bones", "RMTool_Proxy_CreateRigidBakeBone" in proxy and "bn.boneEnable = false" in proxy and "bn.boneFreezeLength = false" in proxy and "bn.boneScaleType = #scale" in proxy and "bn.rotation.controller = Euler_XYZ()" in proxy and "ProxyRoot cannot create no-stretch Euler bake bone" in proxy and "TCB_Rotation()" not in proxy))
    checks.append(("proxy derives rigid Local targets parent-first", "RMTool_Proxy_GetParentFirstOrder parentIndices" in proxy and "for orderIndex = 1 to bakeOrder.count" in proxy and "frameWorldTMs[i] * (inverse frameWorldTMs[parentIndex])" in proxy and "proxyNodes[i].transform.controller.value = frameLocalTMs[i]" in proxy))
    checks.append(("proxy strips scale and shear from pose matrices", "for tm in targetWorldTMs do append rigidTargetWorldTMs (RMTool_Backend_TMNoScale tm)" in proxy and "RMTool_Backend_TMNoScale proxyNodes[i].transform" in proxy))
    checks.append(("proxy selects and unwraps stable Euler orders", 'currentStage = "selectAdaptiveEulerOrders"' in proxy and "for candidateOrder = 1 to 6" in proxy and "RMTool_Proxy_NormalizeEulerAngle middleAngle" in proxy and "candidateMinGimbalMargin" in proxy and "ProxyRoot no stable Euler order" in proxy and 'currentStage = "unwrapAdaptiveEulerTracks"' in proxy and "RMTool_Proxy_UnwrapEulerAngle canonicalEuler.x previousEuler.x" in proxy and 'currentStage = "writeAdaptiveEulerTracks"' in proxy and "eulerSubControllerTracks[i][1].value = degToRad eul.x" in proxy and 'currentStage = "setAdaptiveEulerLinearTangents"' in proxy and "eulerKey.inTangentType = #linear" in proxy and "eulerKey.outTangentType = #linear" in proxy and "quatArrayToEulerArray" not in proxy and "rotation.controller = tcb_rotation()" not in proxy))
    checks.append(("proxy validates no-flip and diagnoses source midpoint", 'currentStage = "midpointContinuityValidation"' in proxy and "midpointSourceWorldTMs" in proxy and "midpointTargetWorldTMs" in proxy and "midpointRigidWorldTMs" in proxy and "expectedNoFlipLocalTM" in proxy and "midpointLocalAxisTolerance = 0.5" in proxy and "maxMidpointLocalAxisError" in proxy and "maxSourceMidpointLocalAxisError" in proxy and "continuityGateFailed" in proxy))
    checks.append(("proxy interpolation uses shortest quaternion hemisphere", "local quatDot =" in proxy and "if quatDot < 0.0 do quatB = -quatB" in proxy and "slerp quatA quatB alpha" in proxy))
    checks.append(("proxy keeps controller Local fallback out of rigid pose implementation", "RMTool_ADV_GetControllerLocalTM sourceNodes[i]" not in proxy and "derivedLocalTM" not in proxy))
    checks.append(("proxy normalizes Max scale inheritance into portable FBX hierarchy", "sourceInheritanceFlags" in proxy and 'currentStage = "normalizeFbxScaleInheritance"' in proxy and "for flagIndex = 7 to 9 do proxyFlags[flagIndex] = true" in proxy and "setInheritanceFlags proxyNodes[i] proxyFlags keepPos:true" in proxy and "cannot normalize FBX scale-inheritance flags" in proxy))
    checks.append(("proxy removes semantic scale filtering", "fn RMTool_Proxy_CapturePreservedScaleNodes" in proxy and "maximumDeviation" not in proxy and "authoredTolerance" not in proxy and "RMTool_HideScale_IsTargetNode node" not in proxy))
    checks.append(("proxy scans scale frame-major", "for t = s to e do at time t" in proxy and "for i = 1 to captureNodes.count do" in proxy and proxy.index("for t = s to e do at time t") < proxy.index("for i = 1 to captureNodes.count do")))
    checks.append(("proxy source capture remains sparse by default", "unitEpsilon:0.00001" in proxy and "includeKeyedUnitTracks:false" in proxy and "RMTool_Proxy_ScaleAxisError sample unitScale" in proxy and "activeFlags[i] = true" in proxy and "if activeFlags[i] or (includeKeyedUnitTracks and keyedFlags[i])" in proxy))
    checks.append(("proxy proves every non-excluded node was scanned", "preserved-scale source scan incomplete" in proxy and "preserved-scale export scan incomplete" in proxy and "scaleScannedNodes=" in proxy))
    checks.append(("proxy accepts controllerless Biped scale sources", "RMTool_Proxy_EvaluateLocalScale node" in proxy and "preserved-scale missing controller" not in proxy and "controllerlessScaleSourceCount" in proxy and "controllerlessScaleSources=" in proxy))
    checks.append(("proxy screens controllerless unit scale once except required BoneSys validation", "append denseFlags ((originalController != undefined) or usesBoneStretch)" in proxy and "for i = 1 to captureNodes.count where not denseFlags[i]" in proxy and "for i = 1 to captureNodes.count where denseFlags[i]" in proxy and "denseFlags[i] = true; activeFlags[i] = true" in proxy))
    checks.append(("proxy has Local-TM scale fallback", "nodeTM * (inverse parentNode.transform)" in proxy and "point3 (length localTM.row1) (length localTM.row2) (length localTM.row3)" in proxy))
    checks.append(("proxy excludes Root/Bip scale in source and FBX stages", "excludedSourceScaleNodes = #(rootObj, bipObj)" in proxy and "local excludedScaleNodes = #(proxyNodes[1])" in proxy and "append excludedScaleNodes proxyNodes[bipIndex]" in proxy))
    checks.append(("proxy resets only proven inactive unit scale", 'currentStage = "normalizeRigidScale"' not in proxy and 'currentStage = "enforceInactiveUnitScale"' in proxy and "preservedScaleSourceNodes" in proxy and "inactiveUnitProxyNodes" in proxy))
    checks.append(("proxy reapplies all preserved scale after rigid validation", 'currentStage = "applyPreservedScale"' in proxy and "RMTool_HideScale_ApplyToBakeNodes preservedScaleContext sourceNodes proxyNodes" in proxy and "preservedScaleNodes=" in proxy))
    checks.append(("proxy verified scale write with key-level self-heal", "RMTool_HideScale_ApplyToBakeNodesVerified preservedScaleContext sourceNodes proxyNodes" in proxy and "preservedApplyDiagnostics" in proxy and "addNewKey ctrl t" in hide_scale and "k.value = expected" in hide_scale))
    checks.append(("proxy captures every authored scale controller before FBX-local conversion", "local ctrlValue = try (copy scaleCtrl.value)" in proxy and "(classOf ctrlValue) == point3" in proxy and "if rawScale != undefined do return rawScale" in proxy and "portable FBX-local Scale keys" in proxy))
    checks.append(("proxy uses evaluated parent-relative scale only for controllerless nodes", "fn RMTool_Proxy_SignedScaleAxis" in proxy and "exportParentNode:undefined" in proxy and "nodeTM * (inverse parentNode.transform)" in proxy and "length exportLocalTM.row1" in proxy and "parentIndices:undefined" in proxy and "parentIndices:parentIndices" in proxy))
    checks.append(("proxy retains full source world matrices for post-scale validation", "local bakedFullWorldTargets = #()" in proxy and "append bakedFullWorldTargets fullTargetWorldTMs" in proxy and "bakedFullWorldTargets[frameIndex]" in proxy))
    checks.append(("proxy reconciles final local PRS from full scaled world targets", 'currentStage = "reconcileScaledWorldTransforms"' in proxy and "proxyNodes[i].transform = targetTM" in proxy and "proxyNodes[i].pos = targetTM.pos" in proxy and "scalePositionCompensatedSamples" in proxy and "positionKey.inTangentType = #linear" in proxy))
    checks.append(("proxy treats authored near-zero scale as reversible", "fn RMTool_Proxy_IsWorldTransformSingular tm axisEpsilon:0.000001 basisEpsilon:0.000001" in proxy and "row1Length <= axisEpsilon" in proxy and "abs (dot r1 (cross r2 r3))) <= basisEpsilon" in proxy and "local ownSingular = RMTool_Proxy_IsWorldTransformSingular targetTM" in proxy and "local ownSingular = RMTool_Proxy_IsWorldTransformSingular targetWorldTMs[i]" in proxy and "(abs proxyScale.x) < 0.01" not in proxy and "(length targetTM.row1) < 0.01" not in proxy))
    singular_epsilon_match = re.search(
        r"RMTool_Proxy_IsWorldTransformSingular tm axisEpsilon:([0-9.]+)",
        proxy,
    )
    singular_epsilon = float(singular_epsilon_match.group(1)) if singular_epsilon_match else 1.0
    source_world_scale = (0.01, 0.01, 0.01)
    portable_local_scale = (
        source_world_scale[0],
        source_world_scale[1] / source_world_scale[0],
        source_world_scale[2] / source_world_scale[1],
    )
    checks.append((
        "near-zero no-inherit chain regression model",
        singular_epsilon < 0.001
        and all(value > singular_epsilon for value in source_world_scale)
        and portable_local_scale == (0.01, 1.0, 1.0),
    ))
    checks.append(("proxy prunes only converted numerical-unit scale tracks", 'currentStage = "pruneConvertedUnitScaleTracks"' in proxy and "convertedUnitScaleEpsilon = 0.00001" in proxy and "maxConvertedScaleDeviation <= convertedUnitScaleEpsilon" in proxy and "deleteKeys scaleCtrl #allKeys" in proxy and "prunedUnitScaleTracks=" in proxy))
    checks.append(("proxy hard-validates final scaled world pose", "maxPostScaleWorldPositionError" in proxy and "maxPostScaleWorldAxisError" in proxy and "post-scale world hard validation failed" in proxy and "postScaleWorldPosErr=" in proxy and "postScaleWorldAxisErr=" in proxy))
    checks.append(("proxy writes scale keys at key level without .scale setter", "local k = addNewKey ctrl t" in hide_scale and "k.value = point3 samples[i].x samples[i].y samples[i].z" in hide_scale and "try (k.inTangentType = #linear)" in hide_scale and "at time t (try (copy ctrl.value) catch (undefined))" in hide_scale))
    checks.append(("proxy hard-validates compatible raw scale and every final full world matrix", 'currentStage = "postScaleHardValidation"' in proxy and "rawScaleMustMatch" in proxy and "sourceInheritanceFlags[sourceIndex][7]" in proxy and "RMTool_Proxy_ScaleAxisError proxyScale sampleScale" in proxy and "copy proxyScaleCtrl.value" in proxy and "maxPreservedScaleError > 0.0001" in proxy and "preserved-scale gate failed" in proxy and "applyKeys=" in proxy and "applyCtrl=" in proxy and "maxPostScaleWorldRowLengthError > 0.001" in proxy and "post-scale world hard validation failed" in proxy and "postScaleWorldScaleErr=" in proxy and "preservedSourceIndices" in proxy))
    checks.append(("proxy FBX export recaptures all non-Root/Bip Model scale", "local scaleExportNodes = for node in objsToExport collect node" in proxy and "for morphMesh in morphMeshes" in proxy and "RMTool_Proxy_CapturePreservedScaleNodes scaleExportNodes s e excludedNodes:excludedScaleNodes" in proxy and "RMTool_HideScale_ApplySamplesVerified entry[1] entry[3] entry[5]" in proxy and "RMTool_HideScale_RestoreSourceNodes preservedScaleContext" in proxy))
    checks.append(("proxy FBX export isolates task-local keyed scale", "includeKeyedUnitTracks:true" in proxy and "taskLocalScale:true" in proxy and "if taskLocalScale do" in proxy and "taskScaleTracks=" in proxy))
    checks.append(("proxy exports explicit/automatic Morpher meshes as live geometry", "RMTool_ADV_ResolveMorpherMeshes morphMeshes autoMorph" in proxy and "resolvedMorphMeshes" in proxy and "morpher meshes excluded from proxy bake" in proxy and "selectMore morphMeshes" in proxy and 'RMTool_ADV_SetFBXParamSafe "Shape" exportMorphShapes' in proxy and "morphMeshes:morphMeshes" in proxy))
    checks.append(("shared outdoor in-place ProxyRoot wrapper", "fn RMTool_Proxy_RunInPlaceExport" in proxy and "desiredRootTransforms" in proxy and "RMTool_Proxy_CreateContext rootObj bipObj" in proxy and "RMTool_Proxy_ExportContext proxyContext" in proxy and "outdoor in-place export completed" in proxy))
    checks.append(("outdoor wrapper has FPS/progress/warning/cleanup gates", "重新检查镜头、事件和动画帧范围" in proxy and "RMTool_Proxy_ProgressShow" in proxy and "outdoor numeric validation warnings" in proxy and "RMTool_Proxy_CleanupContext proxyContext" in proxy and "setSaveRequired false" in proxy))
    checks.append(("proxy crash residue cleaner", "fn RMTool_Proxy_ScanAndCleanResidue" in proxy and "__OP_RM_PROXY__*" in proxy and "__OPProxySource_" in proxy and "__ADV_BAKE__*" in proxy and "__OPAdvExport_" in proxy and "local renameNodes = #()" in proxy and "append renameOriginalNames" in proxy and "renameNodes[i].name = renameOriginalNames[i]" in proxy and "getNodeByName originalName" not in proxy))
    checks.append(("baselayer save guard and residue scan", "getSaveRequired()" in bl and "saveMaxFile currentMaxFile quiet:true" in bl and "RMTool_Proxy_ScanAndCleanResidue()" in bl))
    checks.append(("baselayer rejects non-30 FPS before scene mutation", "if frameRate != 30 do throw" in bl and "重新检查分段、旋转和位移帧范围" in bl and bl.index("if frameRate != 30 do throw") < bl.index("RMTool_Proxy_ScanAndCleanResidue()")))
    checks.append(("baselayer progress labels actual prebuild stages", bl.index('RMTool_Proxy_ProgressShow ("FBX 发布 - "') < bl.index("RMTool_Proxy_ScanAndCleanResidue()") and '0.005 "保存当前场景..."' in bl and '0.012 "采样质心世界轨迹..."' in bl and '0.015 "构建并校验 ProxyRoot..."' in bl and "准备导出（清理残留 / 保存场景）" not in bl))
    checks.append(("baselayer always builds proxy context", "if not useRootMotion do" in bl and "proxyDesiredRootTransforms = for i = totalStartF to totalEndF collect at time i (copy rootObj.transform)" in bl and "RMTool_Backend_ExportOfficialWithHideScale" not in bl and "RMTool_ADV_ExportRootHierarchy rootObj" not in bl and "movedLiveRoot" not in bl))
    checks.append(("proxy selectable dense sampling", "#(1, 2, 4)" in proxy and "((sampleIndex as float) / sampleMultiplier)" in proxy))
    checks.append(("proxy post-bake rigid Euler validation collects warnings", 'currentStage = "postBakeHardValidation"' in proxy and "rigid/hierarchy/continuity gate [" in proxy and "hierarchyPosAllowed=" in proxy and "criticalGateFailed" in proxy and "continuityGateFailed" in proxy))
    checks.append(("proxy FBX preserves native dense keys", 'RMTool_ADV_SetFBXParamSafe "BakeAnimation" false' in proxy and 'RMTool_ADV_SetFBXParamSafe "BakeResampleAnimation" false' in proxy))
    checks.append(("proxy declares selected FBX frame rate", "frameRate = exportFrameRate" in proxy and "frameRate = originalFrameRate" in proxy))
    checks.append(("baselayer creates proxy context", "RMTool_Proxy_CreateContext rootObj bipObj" in bl))
    checks.append(("baselayer exports proxy context", "RMTool_Proxy_ExportContext proxyContext" in bl))
    checks.append(("active path does not call COM restore", bl.count("RMTool_Baselayer_RestoreCOMWorld bipObj originalTransforms") == 1))
    checks.append(
        (
            "baselayer no RM_Fix createLayer",
            "createLayer bipCtrl layerIdxRM" not in bl,
        )
    )
    checks.append(
        (
            "baselayer WallHit write no createLayer WallHit_Adjust",
            'createLayer bipCtrl layerIdx "WallHit_Adjust"' not in bl,
        )
    )

    for rel in (
        "core/rm_indoor_ms_runner_baselayer.py",
        "core/rm_indoor_ms_runner.py",
        "core/rm_wallhit.py",
        "core/rm_outdoor_proxy_runner.py",
        "core/rm_exporter.py",
        "core/rm_export_error_formatter.py",
        "pipeline/publish_public_lookup.py",
        "rm_tool.py",
        "op_tools_hub.py",
        "ui/rm_tool_windows.py",
        "ui/rm_main_window.py",
        "ui/rm_publish_confirm_dialog.py",
        "ui/rm_stage_dialog.py",
        "ui/rm_settings_dialog.py",
    ):
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        try:
            source = read(p).encode("utf-8")
            compile(source, p, "exec")
            checks.append(("syntax " + rel, True))
        except Exception as e:
            checks.append(("syntax " + rel + " ERR " + str(e), False))

    rm = read(os.path.join(ROOT, "rm_tool.py"))
    checks.append(
        (
            "official toolbar entry uses ProxyRoot",
            "def show_publish_only" in rm
            and 'mode=u"publish_only", com_restore_engine=u"baselayer"' in rm,
        )
    )
    checks.append(
        (
            "historical baselayer API aliases official entry",
            "def show_publish_baselayer" in rm
            and "return show_publish_only()" in rm,
        )
    )
    checks.append(
        (
            "hidden rm_tool legacy backup is explicit",
            "def show_publish_legacy" in rm
            and '_PUBLISH_LEGACY_WINDOW = MainWindow(' in rm
            and 'com_restore_engine=u"legacy"' in rm
            and "global _WINDOW_INSTANCE, _PUBLISH_WINDOW, _PUBLISH_LEGACY_WINDOW" in rm
            and "_PUBLISH_LEGACY_WINDOW.close()" in rm,
        )
    )
    hub = read(os.path.join(ROOT, "op_tools_hub.py"))
    checks.append(
        (
            "hub official and hidden legacy routes",
            "def open_publish_tool" in hub
            and "return rm_tool_windows.show_publish_from_scene()" in hub
            and "def open_publish_legacy_tool" in hub
            and "return rm_tool_windows.show_publish_legacy_from_scene()" in hub,
        )
    )
    menu = read(os.path.join(INSTALL, "maxscript", "PiToolsMenu.ms"))
    checks.append(
        (
            "artist menu has one official publisher only",
            '#("PiTools_PublishAnim", "发布动画", "open_publish_tool")' in menu
            and "PiTools_PublishAnimBaseLayer" not in menu
            and "open_publish_baselayer_tool" not in menu
            and u"基轨还原·实验" not in menu,
        )
    )
    mw = read(os.path.join(ROOT, "ui", "rm_main_window.py"))
    error_formatter = read(os.path.join(ROOT, "core", "rm_export_error_formatter.py"))
    checks.append(
        (
            "post-scale hard failures use shared artist-facing transform summary",
            "def format_proxy_transform_restore_error" in error_formatter
            and "def format_task_local_curve_export_error" in error_formatter
            and "This module only translates an error after the exporter has already failed" in error_formatter
            and 'u"worldPos", u"位置"' in error_formatter
            and 'u"worldAxis", u"旋转"' in error_formatter
            and 'u"worldScale", u"缩放"' in error_formatter
            and u"检测到骨骼缩放写回后的变换还原失败" in error_formatter
            and u"请点击“上传报错”交由 TD 处理。" in error_formatter
            and "def _format_proxy_transform_export_error" in mw
            and "def _format_task_local_curve_export_error" in mw
            and mw.count("_format_proxy_transform_export_error(e)") >= 2
            and mw.count("_format_task_local_curve_export_error(e)") >= 2
            and "def _show_animation_data_export_error" in mw
            and "def _show_publish_error" in mw
            and 'tool_id=u"publish"' in mw
            and 'u"上传报错"' in read(os.path.join(ROOT, "ui", "op_error_report_dialog.py")),
        )
    )
    checks.append(
        (
            "MainWindow defaults and invalid fallback to ProxyRoot",
            'com_restore_engine=u"baselayer"' in mw
            and 'engine = _as_text(com_restore_engine or u"baselayer")' in mw
            and 'engine = u"baselayer"' in mw,
        )
    )
    checks.append(
        (
            "duplicate hierarchy failure uses exact artist warning in indoor and outdoor UI",
            '_BINDING_HIERARCHY_WARNING = u"绑定层级被修改，无法导出，请检查文件后重新尝试。"' in mw
            and "def _is_binding_hierarchy_export_error" in mw
            and 'u"ProxyRoot duplicate export hierarchy paths"' in mw
            and mw.count("_is_binding_hierarchy_export_error(e)") >= 2
            and mw.count("_BINDING_HIERARCHY_WARNING,") >= 2
            and mw.count('u"绑定层级错误，无法导出"') >= 2,
        )
    )
    windows = read(os.path.join(ROOT, "ui", "rm_tool_windows.py"))
    checks.append(
        (
            "scene window route is official with hidden legacy backup",
            "def show_publish_tool" in windows
            and 'mode=u"publish_only", com_restore_engine=u"baselayer"' in windows
            and "def show_publish_legacy_tool" in windows
            and 'mode=u"publish_only", com_restore_engine=u"legacy"' in windows,
        )
    )
    readme = read(os.path.join(ROOT, "README.md"))
    checks.append(
        (
            "publisher README documents official and backup APIs",
            "rm_tool.show_publish_only()" in readme
            and "op_tools_hub.open_publish_tool()" in readme
            and "rm_tool.show_publish_legacy()" in readme
            and u"不注册到动画师工具栏和菜单" in readme
            and u"缩放只允许排除 Root/Bip" in readme,
        )
    )
    checks.append(
        (
            "publisher README documents modified binding hierarchy hard stop",
            u"视为绑定层级已被修改" in readme
            and u"绑定层级被修改，无法导出，请检查文件后重新尝试。" in readme
            and u"不自动改名或兼容" in readme,
        )
    )
    checks.append(
        ("indoor export branches baselayer", "rm_indoor_ms_runner_baselayer" in mw)
    )
    checks.append(("baselayer UI defaults to 30 Hz", u'addItem(u"30 Hz（默认 / 推荐）", 30)' in mw and "setCurrentIndex(0)" in mw))
    checks.append(("baselayer UI keeps 60/120 Hz", u'addItem(u"60 Hz（精度补偿）", 60)' in mw and u'addItem(u"120 Hz（最高精度 / 高内存）", 120)' in mw))
    checks.append(("official outdoor UI persists selectable sampling", "_outdoor_proxy_sample_rate_ddl" in mw and 'u"proxy_sample_rate_hz": self._get_outdoor_proxy_sample_rate()' in mw and "self._set_outdoor_proxy_sample_rate(outdoor.get(u\"proxy_sample_rate_hz\", 30))" in mw))
    checks.append(("official outdoor route passes shared ProxyRoot mode", "use_proxy_export = (" in mw and "use_proxy_export=use_proxy_export" in mw and "proxy_sample_rate_hz=outdoor_sample_rate" in mw and "outdoor ProxyRoot" in mw))
    runner = read(os.path.join(ROOT, "core", "rm_indoor_ms_runner_baselayer.py"))
    checks.append(("runner validates selectable rates", "sample_rate_hz not in (30, 60, 120)" in runner))
    checks.append(("runner hides progress window in finally", "rt.RMTool_Proxy_ProgressHide()" in runner))
    checks.append(("runner hard-validates FBX task-local PRS curve bounds", "validate_fbx_transform_curves_within_take" in runner and u"FBX 分段曲线越界，已阻止发布" in runner))
    fbx_fix = read(os.path.join(ROOT, "core", "fix_fbx_scale_curves.py"))
    checks.append(("FBX validator rejects Model PRS keys outside Take", "def validate_fbx_transform_curves_within_take" in fbx_fix and "_find_take_local_time" in fbx_fix and 'for prop_substr in ("Transl", "Rotat", "Scal")' in fbx_fix and "value < start_tick or value > end_tick" in fbx_fix))
    wallhit = read(os.path.join(ROOT, "core", "rm_wallhit.py"))
    checks.append(("WallHit rejects identical ranges assigned to different segments", "range_owners = {}" in wallhit and u"使用了相同帧范围" in wallhit and "range_owners[frame_range] = key" in wallhit))
    checks.append(("runner suppresses and restores MAXScript debugger breaks", "_MXS_DEBUGGER_SAFE_VALUES" in runner and "breakOnError" in runner and "ignoreCaughtThrows" in runner and "_suspend_mxs_debugger_breaks()" in runner and "_restore_mxs_debugger_breaks(debugger_state)" in runner))
    checks.append(("runner preflights invalid binding hierarchy without MAXScript throw", 'BINDING_HIERARCHY_WARNING = u"绑定层级被修改，无法导出，请检查文件后重新尝试。"' in runner and "class BindingHierarchyExportError" in runner and "def _preflight_binding_hierarchy" in runner and "RMTool_Proxy_FindDuplicateExportHierarchyPathsForScene" in runner and runner.index("_preflight_binding_hierarchy(settings.root_obj, use_adv)") < runner.index("result = rt.RMTool_IndoorBackend_RunExport_BaseLayer")))
    outdoor_runner = read(os.path.join(ROOT, "core", "rm_outdoor_proxy_runner.py"))
    checks.append(("outdoor runner shares backend/debugger safety", "_ensure_baselayer_backend_loaded" in outdoor_runner and "_suspend_mxs_debugger_breaks" in outdoor_runner and "_restore_mxs_debugger_breaks" in outdoor_runner and "RMTool_Proxy_RunInPlaceExport" in outdoor_runner and "_preflight_binding_hierarchy(root_obj, use_adv_export)" in outdoor_runner))
    checks.append(("outdoor runner validates post-FBX visibility scale", "_capture_hide_scale_expectations" in outdoor_runner and "validate_fbx_hide_scale_expectations" in outdoor_runner and "include_unit_targets=True" in outdoor_runner))
    exporter = read(os.path.join(ROOT, "core", "rm_exporter.py"))
    checks.append(("outdoor official branch skips legacy FBX scale rewrite", "if use_proxy_export:" in exporter and "export_outdoor_character_proxy" in exporter and "if not use_proxy_export and not use_clean_bake_export" in exporter))
    scene = read(os.path.join(ROOT, "core", "rm_scene.py"))
    checks.append(("scene descendant traversals are cycle-safe", "def _node_identity" in scene and "seen = set([_node_identity(root_node)])" in scene and "if child_key in seen" in scene and "node_key = _node_identity(node)" in scene and "if node_key in seen" in scene))
    legacy_py = read(os.path.join(ROOT, "core", "rm_indoor_ms_runner.py"))
    checks.append(("official runner validates unit visibility targets", "include_unit_targets=True" in runner and "if non_unit or include_unit_targets" in legacy_py))
    checks.append(("hide-scale preflight samples frame-major", "with pymxs.attime(frame):" in legacy_py and "frame_samples = []" in legacy_py and "for row in active_rows:" in legacy_py and legacy_py.index("with pymxs.attime(frame):") < legacy_py.index("for row in active_rows:")))
    checks.append(
        ("legacy runner untouched default", "RunExport_BaseLayer" not in legacy_py)
    )
    adv = read(os.path.join(ROOT, "maxscript", "adv_fbx_export_v25.ms"))
    checks.append(("shared visibility scale target remains name-routed", 'pattern:"bone_ctrl*"' in hide_scale and 'pattern:"ctrl_bone*"' in hide_scale))
    checks.append(("legacy and ADV do not use ProxyRoot authored-scale capture", "RMTool_Proxy_CapturePreservedScaleNodes" not in legacy_ms and "RMTool_Proxy_CapturePreservedScaleNodes" not in adv))

    fail = 0
    for name, ok in checks:
        print(("OK" if ok else "FAIL"), "-", name)
        if not ok:
            fail += 1
    print("TOTAL", len(checks), "FAIL", fail)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())

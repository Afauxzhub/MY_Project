/* Asset-specific Max 2020 builder. Run on a fresh copy of the inspected 1.max.
   Never saves over the loaded source. Output path comes from this script.
   Original vertex weights are transferred exactly, not auto-weighted. */
global KYBuildLog
global KYBuildDir
global KYBuildResult
global KYDrive
global KYFitSegment
global KYGet
global KYLog
global KYControls
global KYDeformBones
global KYMaps
global KYAdditionalControlsOK

fn KYLog msg = (format "%\n" msg; if KYBuildLog != undefined do (format "%\n" msg to:KYBuildLog; flush KYBuildLog))
fn KYGet nameValue = (
    local n=getNodeByName nameValue exact:true
    if n == undefined do throw ("Missing required node: "+nameValue)
    n
)
fn KYLayer label = (
    local l=LayerManager.getLayerFromName label
    if l == undefined do l=LayerManager.newLayerFromName label
    l
)
fn KYPoint n = n.transform.row4
fn KYFitSegment boneNode targetEnd sideHint:[0,-1,0] = (
    local startP=KYPoint boneNode
    local axisX=normalize (targetEnd-startP)
    local axisY=sideHint-axisX*(dot sideHint axisX)
    if length axisY < 0.001 do axisY=[1,0,0]-axisX*(dot [1,0,0] axisX)
    axisY=normalize axisY
    local axisZ=normalize (cross axisX axisY)
    local desired=matrix3 axisX axisY axisZ startP
    -- Figure-mode clavicles retain an internal rest offset in Max 2020.
    -- Correct against the evaluated matrix rather than assuming one assignment fits.
    local inputRot=desired.rotation as matrix3
    for iteration=1 to 3 do (
        biped.setTransform boneNode #rotation inputRot.rotation false
        local actualRot=boneNode.transform.rotation as matrix3
        inputRot=inputRot*(inverse actualRot)*(desired.rotation as matrix3)
    )
    local sc=biped.getTransform boneNode #scale
    sc.x=distance startP targetEnd
    biped.setTransform boneNode #scale sc false
)
fn KYDrive nodeValue driver = (
    local reference=copy nodeValue.transform
    local offset=reference*(inverse driver.transform)
    local ctrl=transform_script()
    ctrl.addNode "driver" driver
    ctrl.addConstant "bindOffset" offset
    local expr="bindOffset * driver.transform"
    if nodeValue.parent != undefined do (
        ctrl.addNode "parentNode" nodeValue.parent
        expr += " * inverse parentNode.transform"
    )
    ctrl.setExpression expr
    nodeValue.controller=ctrl
    setUserProp nodeValue "KY_Driver" driver.name
    nodeValue
)
fn KYControl nodeValue category controlSize = (
    local ctrl=circle radius:controlSize steps:8 name:("CTRL_"+nodeValue.name) wireColor:(color 255 185 55)
    ctrl.parent=nodeValue.parent
    ctrl.transform=nodeValue.transform
    ctrl.renderable=false
    ctrl.displayByLayer=false
    ctrl.position.controller=Position_XYZ()
    ctrl.rotation.controller=Euler_XYZ()
    setUserProp ctrl "KY_Role" "Control"
    setUserProp ctrl "KY_Category" category
    setUserProp ctrl "KY_RestLocal" ((ctrl.transform*(inverse ctrl.parent.transform)) as string)
    (KYLayer ("CTRL_"+category)).addNode ctrl
    append KYControls ctrl
    KYDrive nodeValue ctrl
    ctrl
)
fn KYMap originalName bipedName = (
    local n=KYGet originalName
    local d=KYGet bipedName
    append KYMaps #(n,d)
    KYDrive n d
)
fn KYIsHeadDescendant nodeValue headNode = (
    local p=nodeValue
    while p != undefined do (if p == headNode do return true; p=p.parent)
    false
)

KYBuildDir=getFilenamePath (getSourceFileName())
KYBuildResult=false
KYControls=#()
KYMaps=#()
(
    local scratchDir=KYBuildDir+"../../../../../.validation-temp/ky-rig-build/"
    makeDir scratchDir all:true
    KYBuildLog=createFile (scratchDir+"build-report.txt")
    try (
        if maxFileName != "1.max" do throw "Run this builder only on the original 1.max in a separate Max session."
        if doesFileExist (KYBuildDir+"Player_BipedRig.max") do throw "Output already exists. Preserve the prior rig before rebuilding."
        local sourceDir=maxFilePath
        local meshNode=KYGet "Object001"
        local skinOld=meshNode.modifiers[1]
        if classOf skinOld != Skin do throw "Expected exactly the inspected Skin mesh."
        sliderTime=0f
        local oldMesh=snapshotAsMesh meshNode
        local oldPoints=for i=1 to oldMesh.numverts collect ((getVert oldMesh i)*meshNode.objectTransform)
        local bbox=nodeGetBoundingBox meshNode (matrix3 1)
        local factor=1.8/(bbox[2].z-bbox[1].z)
        local boneNodes=for i=1 to skinOps.GetNumberBones skinOld collect KYGet (skinOps.GetBoneName skinOld i 0)
        local dqEnabled=skinOld.enableDQ
        local oldBoneLimit=skinOld.bone_Limit
        local dqValues=#()
        local weightIds=#(); local weightValues=#()
        for v=1 to skinOps.GetNumberVertices skinOld do (
            local ids=#(); local vals=#()
            for j=1 to skinOps.GetVertexWeightCount skinOld v do (
                append ids (skinOps.GetVertexWeightBoneID skinOld v j)
                append vals (skinOps.GetVertexWeight skinOld v j)
            )
            append weightIds ids; append weightValues vals
            append dqValues (skinOps.getVertexDQWeight skinOld v)
        )
        KYDeformBones=for n in objects where classOf n == BoneGeometry collect n
        if KYDeformBones.count != 609 do throw "Source bone count differs from inspected asset."
        local restTms=for n in KYDeformBones collect copy n.transform
        local originalNames=for n in KYDeformBones collect n.name
        KYLog ("CAPTURE vertices="+oldPoints.count as string+" bones="+KYDeformBones.count as string+" scale="+factor as string)
        -- Collapse only the unanimated evaluated reference mesh, retaining UVs/material.
        -- This avoids this source Skin's 31 cm rest-pose error under rescaleWorldUnits.
        convertToMesh meshNode
        for v=1 to oldPoints.count do setVert meshNode v (oldPoints[v]*factor)
        meshNode.transform=matrix3 1
        update meshNode
        for i=1 to KYDeformBones.count do (
            local n=KYDeformBones[i]
            n.boneEnable=false
            n.boneAutoAlign=false
            n.boneFreezeLength=false
            local tm=copy restTms[i]; tm.row4 *= factor
            n.transform=tm
            try(n.length *= factor; n.width *= factor; n.height *= factor)catch()
            if matchPattern n.name pattern:"G_*" do n.name=substring n.name 3 -1
            setUserProp n "KY_Role" "Deform"
            setUserProp n "KY_SourceName" originalNames[i]
            setUserProp n "KY_ExportParent" (if n.parent == undefined then "Root" else n.parent.name)
        )
        -- Reapply world matrices parent-first after all bone lengths changed.
        for i=1 to KYDeformBones.count do (
            local tm=copy restTms[i]; tm.row4 *= factor
            KYDeformBones[i].transform=tm
        )
        for n in KYDeformBones do setUserProp n "KY_ExportParent" (if n.parent == undefined then "Root" else n.parent.name)
        local root=circle name:"Root" radius:0.45 steps:24 wirecolor:(color 255 210 30)
        root.renderable=false; root.displayByLayer=false
        setUserProp root "KY_Role" "Root"
        (KYGet "body_root").parent=root
        local bp=biped.createNew 1.8 -90 [0,0,0] arms:true neckLinks:1 spineLinks:3 fingers:5 fingerLinks:3 toes:1 toeLinks:1 triangleNeck:true
        bp.controller.rootName="Bip001"
        bp.controller.figureMode=true
        bp.controller.triangleNeck=true
        local hipP=((KYPoint (KYGet "thigh_L"))+(KYPoint (KYGet "thigh_R")))/2
        biped.setTransform bp #pos hipP false
        local pelvis=KYGet "Bip001 Pelvis"
        local pelvisScale=biped.getTransform pelvis #scale
        pelvisScale.z=distance (KYPoint (KYGet "thigh_L")) (KYPoint (KYGet "thigh_R"))
        biped.setTransform pelvis #scale pelvisScale false
        biped.setTransform (KYGet "Bip001 Spine") #pos (KYPoint (KYGet "waist")) false
        KYFitSegment (KYGet "Bip001 Spine") (KYPoint (KYGet "stomach"))
        KYFitSegment (KYGet "Bip001 Spine1") (KYPoint (KYGet "chest"))
        KYFitSegment (KYGet "Bip001 Spine2") (KYPoint (KYGet "neck"))
        KYFitSegment (KYGet "Bip001 Neck") (KYPoint (KYGet "Head_Attach"))
        biped.setTransform (KYGet "Bip001 Head") #scale [0.20,0.16,0.15] false
        for side in #("L","R") do (
            local prefix="Bip001 "+side+" "
            local hint=[0,1,0]
            local cl=KYGet (prefix+"Clavicle")
            biped.setTransform cl #pos (KYPoint (KYGet ("shoulder_"+side))) false
            KYFitSegment cl (KYPoint (KYGet ("uparm_"+side))) sideHint:hint
            KYFitSegment (KYGet (prefix+"UpperArm")) (KYPoint (KYGet ("lowarm_"+side))) sideHint:hint
            KYFitSegment (KYGet (prefix+"Forearm")) (KYPoint (KYGet ("hand_"+side))) sideHint:hint
            local hand=KYGet (prefix+"Hand")
            KYFitSegment hand (KYPoint (KYGet ("fng_"+side+"_c1_"))) sideHint:hint
            for f=0 to 4 do (
                local letter=substring "abcde" (f+1) 1
                for j=1 to 3 do (
                    local fingerName=prefix+"Finger"+f as string+(if j==1 then "" else (j-1) as string)
                    local bn=KYGet fingerName
                    local src=KYGet ("fng_"+side+"_"+letter+j as string+"_")
                    if j==1 do biped.setTransform bn #pos (KYPoint src) false
                    local endP=if j<3 then KYPoint (KYGet ("fng_"+side+"_"+letter+(j+1) as string+"_")) else ((KYPoint src)+normalize src.transform.row1*(amax 0.009 src.length))
                    KYFitSegment bn endP sideHint:src.transform.row2
                )
            )
            local kneeP=copy (KYPoint (KYGet ("calf_"+side)))
            kneeP.y -= 0.002
            KYFitSegment (KYGet (prefix+"Thigh")) kneeP
            KYFitSegment (KYGet (prefix+"Calf")) (KYPoint (KYGet ("foot_"+side)))
            local foot=KYGet (prefix+"Foot")
            local toeP=KYPoint (KYGet ("toe_"+side))
            local footP=KYPoint foot
            local footTM=matrix3 [0,0,-1] [0,-1,0] [-1,0,0] footP
            biped.setTransform foot #rotation footTM.rotation false
            biped.setTransform foot #scale [(footP.z-toeP.z),((footP.y-toeP.y)/0.8),0.095] false
            KYFitSegment (KYGet (prefix+"Toe0")) (KYPoint (KYGet ("toe_out_"+side))) sideHint:[0,0,1]
        )
        bp.controller.figureMode=false
        bp.parent=root
        for side in #("L","R") do for pair in #(#("uparm_","UpperArm"),#("lowarm_","Forearm"),#("hand_","Hand"),#("foot_","Foot")) do (
            local gap=distance (KYPoint (KYGet (pair[1]+side))) (KYPoint (KYGet ("Bip001 "+side+" "+pair[2])))
            if gap>0.001 do throw ("Biped joint fitting failed: "+pair[1]+side+" error="+gap as string)
        )
        KYLog "BIPED_FIT_COMPLETE"
        KYMap "pelvis" "Bip001 Pelvis"
        KYMap "waist" "Bip001 Spine"
        KYMap "stomach" "Bip001 Spine1"
        KYMap "chest" "Bip001 Spine2"
        KYMap "neck" "Bip001 Neck"
        KYMap "Head_Attach" "Bip001 Head"
        for side in #("L","R") do (
            local prefix="Bip001 "+side+" "
            for pair in #(#("shoulder_","Clavicle"),#("clavicle_","Clavicle"),#("uparm_","UpperArm"),#("lowarm_","Forearm"),#("hand_","Hand"),#("thigh_","Thigh"),#("calf_","Calf"),#("foot_","Foot"),#("toe_","Toe0")) do KYMap (pair[1]+side) (prefix+pair[2])
            for f=0 to 4 do for j=1 to 3 do (
                local src="fng_"+side+"_"+(substring "abcde" (f+1) 1)+j as string+"_"
                KYMap src (prefix+"Finger"+f as string+(if j==1 then "" else (j-1) as string))
            )
        )
        local mappedNodes=for p in KYMaps collect p[1]
        local headAttach=KYGet "Head_Attach"
        for n in KYDeformBones where (findItem mappedNodes n)==0 and n.name!="body_root" do (
            local category="Correctives"
            local sizeValue=0.014
            if matchPattern n.name pattern:"hair*" then (category="Hair"; sizeValue=0.012)
            else if matchPattern n.name pattern:"cape*" or matchPattern n.name pattern:"*collar*" or matchPattern n.name pattern:"belt*" then (category="Cloth"; sizeValue=0.018)
            else if KYIsHeadDescendant n headAttach then (category="Face"; sizeValue=0.008)
            if n.name!="head_root" and not matchPattern n.name pattern:"*SP*" do KYControl n category sizeValue
        )
        fileIn (KYBuildDir+"AddControls.ms")
        if not KYAdditionalControlsOK do throw "Additional control construction failed."
        local bonePositionError=0.0
        for i=1 to KYDeformBones.count do bonePositionError=amax bonePositionError (distance KYDeformBones[i].transform.row4 (restTms[i].row4*factor))
        KYLog ("BONE_REFERENCE_ERROR="+bonePositionError as string)
        if bonePositionError>0.00002 do throw "Deform bone rest positions changed."
        -- New Skin receives exactly the existing weights on the exact scaled reference.
        local skinNew=Skin()
        skinNew.enableDQ=dqEnabled
        skinNew.bone_Limit=oldBoneLimit
        addModifier meshNode skinNew
        select meshNode
        max modify mode
        modPanel.setCurrentObject skinNew
        for i=1 to boneNodes.count do skinOps.addBone skinNew boneNodes[i] (if i==boneNodes.count then 1 else 0)
        if (skinOps.GetNumberBones skinNew)!=boneNodes.count do throw "Skin bone count mismatch."
        for i=1 to boneNodes.count do if (skinOps.GetBoneName skinNew i 0)!=boneNodes[i].name do throw "Skin bone order mismatch."
        for v=1 to weightIds.count do (
            skinOps.ReplaceVertexWeights skinNew v weightIds[v] weightValues[v]
            skinOps.setVertexDQWeight skinNew v dqValues[v]
        )
        local weightError=0.0
        local dqError=0.0
        for v=1 to weightIds.count do (
            if skinOps.GetVertexWeightCount skinNew v != weightIds[v].count do throw "Skin influence count mismatch."
            for j=1 to weightIds[v].count do (
                if skinOps.GetVertexWeightBoneID skinNew v j != weightIds[v][j] do throw "Skin bone influence identity mismatch."
                weightError=amax weightError (abs ((skinOps.GetVertexWeight skinNew v j)-weightValues[v][j]))
            )
            dqError=amax dqError (abs ((skinOps.getVertexDQWeight skinNew v)-dqValues[v]))
        )
        local checkMesh=snapshotAsMesh meshNode
        local vertexError=0.0
        for i=1 to oldPoints.count do vertexError=amax vertexError (distance ((getVert checkMesh i)*meshNode.objectTransform) (oldPoints[i]*factor))
        KYLog ("REST_VALIDATION vertexError="+vertexError as string+" weightError="+weightError as string+" dqError="+dqError as string+" dqEnabled="+dqEnabled as string)
        if vertexError>0.00002 or weightError>0.000001 or dqError>0.000001 do throw "Reference/weights validation failed. No rig saved."
        meshNode.name="PlayerMesh"
        (KYLayer "Meshes").addNode meshNode
        (KYLayer "Root").addNode root
        for n in KYDeformBones do ((KYLayer "Deform").addNode n; n.isHidden=true; n.isFrozen=true)
        local bipNodes=for n in objects where classOf n==Biped_Object collect n
        for n in bipNodes do ((KYLayer "Bip").addNode n; n.displayByLayer=false)
        for c in KYControls do c.isHidden=true
        selectionSets["Body_Biped"]=bipNodes
        selectionSets["Export_Deform"]=KYDeformBones
        for category in #("Face","Hair","Cloth","Correctives") do selectionSets[category+"_Controls"]=(for c in objects where (getUserProp c "KY_Category")==category collect c)
        setUserProp root "KY_RigVersion" "1"
        setUserProp root "KY_HeightMeters" 1.8
        setUserProp root "KY_ExportRoot" "body_root"
        setUserProp root "KY_SourceFile" "1.max"
        setUserProp root "KY_HeadDriver" "Head_Attach"
        setUserProp root "KY_Units" "meters"
        for tex in getClassInstances Bitmaptexture do (
            local localTex=sourceDir+filenameFromPath tex.filename
            if doesFileExist localTex do tex.filename=localTex
        )
        biped.saveBipFile bp.controller (KYBuildDir+"Player_Reference.bip")
        bp.controller.figureMode=true
        biped.saveFigFile bp.controller (KYBuildDir+"Player_Reference.fig")
        bp.controller.figureMode=false
        select bp
        max tool zoomextents all
        saveMaxFile (KYBuildDir+"Player_BipedRig.max") quiet:true
        KYLog ("KY_BUILD_OK controls="+KYControls.count as string+" maps="+KYMaps.count as string+" output="+KYBuildDir+"Player_BipedRig.max")
        KYBuildResult=true
    )catch(
        KYLog ("KY_BUILD_FAILED "+getCurrentException())
    )
    close KYBuildLog
    KYBuildLog=undefined
)

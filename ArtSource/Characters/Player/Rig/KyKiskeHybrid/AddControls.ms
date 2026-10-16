/* Additional automatic following, with editable FK controls on top.
   Load once into the newly built rig; all controller dependencies are stored in MAX. */
global KYAdditionalControlsOK=false
fn KYAGet label = (local n=getNodeByName label exact:true; if n==undefined do throw ("Missing "+label); n)
fn KYAAutoGroup controlNode = (
    local parentNode=controlNode.parent
    local ref=copy controlNode.transform
    local group=point name:("AUTO_"+controlNode.name) size:0.005 cross:false box:false
    group.parent=parentNode; group.transform=ref
    controlNode.parent=group; controlNode.transform=ref
    setUserProp group "KY_Role" "Auto"
    group.isHidden=true; group.renderable=false
    local layer=LayerManager.getLayerFromName "Auto"
    if layer==undefined do layer=LayerManager.newLayerFromName "Auto"
    layer.addNode group
    setUserProp controlNode "KY_RestLocal" ((controlNode.transform*inverse group.transform) as string)
    group
)
fn KYABlend ctrlName aName bName amount = (
    local controlNode=KYAGet ctrlName
    local a=KYAGet aName; local b=KYAGet bName
    local autoNode=KYAAutoGroup controlNode
    local c=transform_script()
    c.addNode "a" a; c.addNode "b" b; c.addNode "parentNode" autoNode.parent
    c.addConstant "offsetA" (autoNode.transform*inverse a.transform)
    c.addConstant "offsetB" (autoNode.transform*inverse b.transform)
    c.addConstant "blendWeight" amount
    c.setExpression "local ta=offsetA*a.transform; local tb=offsetB*b.transform; local result=(slerp ta.rotation tb.rotation blendWeight) as matrix3; result.row4=ta.row4; result*inverse parentNode.transform"
    autoNode.controller=c
)
(
    if getNodeByName "CTRL_FaceSettings" != undefined do throw "Additional controls already exist."
    for side in #("L","R") do (
        KYABlend ("CTRL_lowarmup_"+side) ("lowarm_"+side) ("hand_"+side) 0.15
        KYABlend ("CTRL_lowarmmid_"+side) ("lowarm_"+side) ("hand_"+side) 0.5
        KYABlend ("CTRL_lowarmlow_"+side) ("lowarm_"+side) ("hand_"+side) 0.85
        KYABlend ("CTRL_wrist_"+side) ("lowarm_"+side) ("hand_"+side) 1.0
        KYABlend ("CTRL_shldrhalf_"+side) ("uparm_"+side) ("clavicle_"+side) 0.5
        KYABlend ("CTRL_elbow_"+side) ("uparm_"+side) ("lowarm_"+side) 0.5
        KYABlend ("CTRL_knee_"+side) ("thigh_"+side) ("calf_"+side) 0.5
        KYABlend ("CTRL_ankle_half_"+side) ("calf_"+side) ("foot_"+side) 0.5
    )
    KYABlend "CTRL_neck_half" "chest" "neck" 0.5
    local head=KYAGet "Head_Attach"
    local face=circle name:"CTRL_FaceSettings" radius:0.06 wirecolor:(color 60 240 150)
    face.parent=head
    face.transform=matrix3 1
    face.pos=head.transform.row4+[0.25,0,0.06]
    face.renderable=false
    setUserProp face "KY_Role" "Control"
    setUserProp face "KY_Category" "Face"
    setUserProp face "KY_RestLocal" ((face.transform*inverse head.transform) as string)
    (LayerManager.getLayerFromName "CTRL_Face").addNode face
    local faceAttributes=attributes KYFaceSettings version:1 (
        parameters values rollout:faceRollout (
            blinkL type:#float default:0 animatable:true ui:blinkLUI
            blinkR type:#float default:0 animatable:true ui:blinkRUI
            jawOpen type:#float default:0 animatable:true ui:jawUI
            lookLR type:#float default:0 animatable:true ui:lookLRUI
            lookUD type:#float default:0 animatable:true ui:lookUDUI
        )
        rollout faceRollout "Face Controls" (
            spinner blinkLUI "Blink L %" range:[0,100,0] type:#float
            spinner blinkRUI "Blink R %" range:[0,100,0] type:#float
            spinner jawUI "Jaw open" range:[0,25,0] type:#float
            spinner lookLRUI "Look L / R" range:[-1,1,0] type:#float scale:0.05
            spinner lookUDUI "Look down / up" range:[-1,1,0] type:#float scale:0.05
        )
    )
    custAttributes.add face faceAttributes
    for propertyName in #(#blinkL,#blinkR,#jawOpen,#lookLR,#lookUD) do
        setPropertyController face.KYFaceSettings propertyName (bezier_float())
    for side in #("L","R") do (
        local up=KYAGet ("eyelid_"+side+"up")
        local low=KYAGet ("eyelid_"+side+"low")
        local delta=low.transform.row4-up.transform.row4
        for part in #(#("up",0.8),#("low",-0.2)) do (
            local ctrl=KYAGet ("CTRL_eyelid_"+side+part[1])
            local a=KYAAutoGroup ctrl
            local invParent=inverse a.parent.transform
            local localDelta=(delta*part[2])*invParent-[0,0,0]*invParent
            local c=transform_script()
            c.addTarget "blinkValue" (getPropertyController face.KYFaceSettings (("blink"+side) as name))
            c.addConstant "bindLocal" (a.transform*invParent)
            c.addConstant "blinkDelta" localDelta
            c.setExpression "local result=copy bindLocal; result.row4 += blinkDelta*(blinkValue/100.0); result"
            a.controller=c
        )
        local p=KYAAutoGroup (KYAGet ("CTRL_pupil_"+side))
        local invP=inverse p.parent.transform
        local c=transform_script()
        c.addTarget "lookLR" (getPropertyController face.KYFaceSettings #lookLR)
        c.addTarget "lookUD" (getPropertyController face.KYFaceSettings #lookUD)
        c.addConstant "bindLocal" (p.transform*invP)
        c.addConstant "horizontal" ([0.005,0,0]*invP-[0,0,0]*invP)
        c.addConstant "vertical" ([0,0,0.004]*invP-[0,0,0]*invP)
        c.setExpression "local result=copy bindLocal; result.row4 += horizontal*lookLR+vertical*lookUD; result"
        p.controller=c
    )
    local jaw=KYAAutoGroup (KYAGet "CTRL_ago")
    local c=transform_script()
    c.addTarget "jawOpen" (getPropertyController face.KYFaceSettings #jawOpen)
    c.addNode "head" head; c.addNode "parentNode" jaw.parent
    c.addConstant "bindLocal" (jaw.transform*inverse jaw.parent.transform)
    c.setExpression "local base=bindLocal*parentNode.transform; local rot=(base.rotation as matrix3)*((quat jawOpen (normalize head.transform.row2)) as matrix3); rot.row4=base.row4; rot*inverse parentNode.transform"
    jaw.controller=c
    -- The source lower lip, lower teeth and tongue are a sibling of the jaw.
    local lowerLip=KYAAutoGroup (KYAGet "CTRL_LowLIPS")
    local jawBone=KYAGet "ago"
    local lowerFollow=transform_script()
    lowerFollow.addNode "jawBone" jawBone
    lowerFollow.addNode "parentNode" lowerLip.parent
    lowerFollow.addConstant "bindOffset" (lowerLip.transform*inverse jawBone.transform)
    lowerFollow.setExpression "bindOffset*jawBone.transform*inverse parentNode.transform"
    lowerLip.controller=lowerFollow
    selectionSets["Face_Controls"]=(for n in objects where getUserProp n "KY_Category"=="Face" collect n)
    face.isHidden=true
    setUserProp (KYAGet "Root") "KY_AutoCorrectives" 17
    setUserProp (KYAGet "Root") "KY_FaceSettings" "CTRL_FaceSettings"
    KYAdditionalControlsOK=true
    format "KY_ADDITIONAL_CONTROLS_OK\n"
)

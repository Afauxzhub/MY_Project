/* Arc Run Creator backend: 30 FPS, automatic source speed, arbitrary duration, world -Y. */
global OPArcRunCreatorBackend

struct OPArcRunCreatorBackendLib
(
    toolVersion="2.5", requiredFPS=30,
    defaultRadiusM=5.0, defaultLeanDeg=8.0,
    helperMarker="OP_StraightRunToArcRun",

    fn appendUniqueValue values value = (if value != undefined and findItem values value == 0 do append values value; values),
    fn joinValues values separator =
    (
        local result=""
        for i=1 to values.count do (if i > 1 do result += separator; result += values[i] as string)
        result
    ),
    fn parseIntegerValues textValue =
    (
        local result=#()
        if textValue == undefined do return result
        for token in (filterString (textValue as string) ",") where token != "" do append result (token as integer)
        result
    ),
    fn parseFloatValues textValue =
    (
        local result=#()
        if textValue == undefined do return result
        for token in (filterString (textValue as string) ",") where token != "" do append result (token as float)
        result
    ),
    fn formatFloatValues values =
    (
        local parts=#()
        for value in values do append parts (formattedPrint value format:".9g")
        OPArcRunCreatorBackend.joinValues parts ","
    ),
    fn nodeHandle node = (try(node.inode.handle as integer)catch(0)),
    fn nodeFromHandle handleValue =
    (
        if handleValue == undefined or handleValue == 0 do return undefined
        local result=undefined
        try(result=maxOps.getNodeByHandle handleValue)catch(result=undefined)
        result
    ),
    fn isBipedCOM node =
    (
        if node == undefined or not isValidNode node do return false
        if classof node != Biped_Object do return false
        local rootState=false
        try(rootState=node.isRoot)catch(rootState=false)
        if rootState do return true
        -- Some Max 2020 Biped builds report false for .isRoot on a valid COM.
        -- The body controller's H/V/Turning controls are a safer COM-only fallback.
        local horizontalControl=undefined
        local verticalControl=undefined
        local turningControl=undefined
        try(horizontalControl=biped.getHorizontalControl node.controller)catch(horizontalControl=undefined)
        try(verticalControl=biped.getVerticalControl node.controller)catch(verticalControl=undefined)
        try(turningControl=biped.getTurnControl node.controller)catch(turningControl=undefined)
        horizontalControl != undefined and verticalControl != undefined and turningControl != undefined
    ),
    fn selectedCOM = (if selection.count == 1 and OPArcRunCreatorBackend.isBipedCOM selection[1] then selection[1] else undefined),

    fn collectTrackCandidates bipObj =
    (
        local tracks=#(); local ctrl=bipObj.controller
        try(OPArcRunCreatorBackend.appendUniqueValue tracks ctrl.horizontal)catch()
        try(OPArcRunCreatorBackend.appendUniqueValue tracks ctrl.horizontal.controller)catch()
        try(OPArcRunCreatorBackend.appendUniqueValue tracks ctrl.vertical)catch()
        try(OPArcRunCreatorBackend.appendUniqueValue tracks ctrl.vertical.controller)catch()
        try(OPArcRunCreatorBackend.appendUniqueValue tracks ctrl.turning)catch()
        try(OPArcRunCreatorBackend.appendUniqueValue tracks ctrl.turning.controller)catch()
        try(OPArcRunCreatorBackend.appendUniqueValue tracks (biped.getHorizontalControl ctrl))catch()
        try(OPArcRunCreatorBackend.appendUniqueValue tracks (biped.getVerticalControl ctrl))catch()
        try(OPArcRunCreatorBackend.appendUniqueValue tracks (biped.getTurnControl ctrl))catch()
        tracks
    ),
    fn collectCOMKeyFrames bipObj startFrame endFrame =
    (
        local keyFrames=#()
        for track in (OPArcRunCreatorBackend.collectTrackCandidates bipObj) where track != undefined do
        (
            local keyCount=try(numKeys track)catch(0)
            for keyIndex=1 to keyCount do
            (
                local keyTime=try(getKeyTime track keyIndex)catch(undefined)
                if keyTime == undefined do keyTime=try((biped.getKey track keyIndex).time)catch(undefined)
                if keyTime != undefined do
                (
                    local keyFrame=keyTime.frame as integer
                    if keyFrame >= startFrame and keyFrame <= endFrame do OPArcRunCreatorBackend.appendUniqueValue keyFrames keyFrame
                )
            )
        )
        sort keyFrames; keyFrames
    ),
    fn rotationErrorDegrees expectedRotation actualRotation = (try(abs(((inverse expectedRotation)*actualRotation).angle))catch(9999.0)),
    fn validateBaseSource bipObj keyFrames startFrame endFrame =
    (
        if frameRate != OPArcRunCreatorBackend.requiredFPS do throw ("场景必须为30 FPS，当前为"+(frameRate as string)+" FPS。")
        if endFrame <= startFrame do throw "动画区间至少需要1帧。"
        if biped.numLayers bipObj.controller != 0 do throw "源Biped必须只有基础层（Layer 0）。请先处理或塌陷现有动画层。"
        if bipObj.parent == undefined do throw "COM没有原始Root父对象，无法建立辅助Root。"
        if keyFrames.count == 0 do throw "基础层没有找到COM的Horizontal / Vertical / Turning关键帧。"
        if findItem keyFrames startFrame == 0 do throw "动画首帧没有COM关键帧，请先在首帧给质心K帧。"
        if findItem keyFrames endFrame == 0 do throw "动画尾帧没有COM关键帧，请先在尾帧给质心K帧。"
        local parentStartTM=undefined; local parentEndTM=undefined
        at time startFrame (parentStartTM=bipObj.parent.transform)
        at time endFrame (parentEndTM=bipObj.parent.transform)
        if distance parentStartTM.pos parentEndTM.pos > 0.01 or OPArcRunCreatorBackend.rotationErrorDegrees parentStartTM.rotation parentEndTM.rotation > 0.01 do throw "COM原始Root在动画区间内发生移动或旋转。当前版本要求原始Root保持静止。"
        true
    ),
    fn helperDirection helper =
    (
        local directionText=try(getUserProp helper "OPArcRunDirection")catch(undefined)
        if directionText == "left" then #left else if directionText == "right" then #right else undefined
    ),
    fn isArcHelper node =
    (
        if node == undefined or not isValidNode node do return false
        -- Do not probe user properties on arbitrary production nodes/Biped COM.
        -- Max 2020 can raise a native access violation for some controller states.
        if node.name != "Left_Root" and node.name != "Right_Root" do return false
        local marker=try(getUserProp node "OPArcRunMarker")catch(undefined)
        marker == OPArcRunCreatorBackend.helperMarker and OPArcRunCreatorBackend.helperDirection node != undefined
    ),
    fn selectedHelper = (if selection.count == 1 and OPArcRunCreatorBackend.isArcHelper selection[1] then selection[1] else undefined),
    fn resolveHelperNodes helper =
    (
        if not OPArcRunCreatorBackend.isArcHelper helper do throw "当前选择不是本工具生成的弧线辅助Root。"
        local bipObj=OPArcRunCreatorBackend.nodeFromHandle (try((getUserProp helper "OPArcRunCOMHandle") as integer)catch(0))
        local originalParent=OPArcRunCreatorBackend.nodeFromHandle (try((getUserProp helper "OPArcRunParentHandle") as integer)catch(0))
        if not OPArcRunCreatorBackend.isBipedCOM bipObj do throw "辅助Root记录的Biped COM已经不存在。"
        if originalParent == undefined or not isValidNode originalParent do throw "辅助Root记录的原始Root已经不存在。"
        if bipObj.parent != helper do throw "COM层级已被修改：当前COM不在辅助Root下面。"
        #(bipObj,originalParent)
    ),
    fn readHelperRange helper =
    (
        local startFrame=try((getUserProp helper "OPArcRunStartFrame") as integer)catch(0)
        local endFrame=try((getUserProp helper "OPArcRunEndFrame") as integer)catch(-1)
        if (animationRange.start.frame as integer) != startFrame or (animationRange.end.frame as integer) != endFrame do throw ("动画区间已改变。请恢复为"+(startFrame as string)+"-"+(endFrame as string)+"帧后再操作。")
        #(startFrame,endFrame)
    ),
    fn makeHelperBone helperName originalParent startFrame =
    (
        if getNodeByName helperName exact:true != undefined do throw ("场景中已存在同名对象："+helperName+"。请先处理它再生成。")
        local helper=BoneSys.createBone [0,0,0] [20,0,0] [0,0,1]
        helper.name=helperName; helper.boneEnable=false; helper.boneAutoAlign=false
        helper.boneFreezeLength=false; helper.boneScaleType=#scale
        helper.length=20.0; helper.width=4.0; helper.height=4.0; helper.renderable=false
        helper.wireColor=color 255 170 0; helper.parent=originalParent
        at time startFrame (helper.transform=originalParent.transform)
        helper
    ),
    fn storeHelperMetadata helper direction bipObj originalParent keyFrames startFrame endFrame distances restoreLayer radiusM leanDeg sourceSpeedCmPerSecond =
    (
        setUserProp helper "OPArcRunMarker" OPArcRunCreatorBackend.helperMarker
        setUserProp helper "OPArcRunVersion" OPArcRunCreatorBackend.toolVersion
        setUserProp helper "OPArcRunDirection" (if direction == #left then "left" else "right")
        setUserProp helper "OPArcRunCOMHandle" (OPArcRunCreatorBackend.nodeHandle bipObj)
        setUserProp helper "OPArcRunParentHandle" (OPArcRunCreatorBackend.nodeHandle originalParent)
        setUserProp helper "OPArcRunKeyFrames" (OPArcRunCreatorBackend.joinValues keyFrames ",")
        setUserProp helper "OPArcRunStartFrame" startFrame; setUserProp helper "OPArcRunEndFrame" endFrame
        setUserProp helper "OPArcRunDistances" (OPArcRunCreatorBackend.formatFloatValues distances)
        setUserProp helper "OPArcRunRestoreLayer" restoreLayer
        setUserProp helper "OPArcRunRadiusM" radiusM; setUserProp helper "OPArcRunLeanDeg" leanDeg
        setUserProp helper "OPArcRunSourceSpeedCmPerSecond" sourceSpeedCmPerSecond
        true
    ),
    fn setStraightHelperPath helper originalParent startFrame distances =
    (
        local parentStartTM=undefined
        at time startFrame (parentStartTM=originalParent.transform)
        deleteKeys helper.position.controller #allKeys; deleteKeys helper.rotation.controller #allKeys
        animate on
        (
            for frameIndex=1 to distances.count do
            (
                local frameNumber=startFrame+frameIndex-1
                at time frameNumber
                (
                    helper.rotation=parentStartTM.rotation
                    -- Bone rotation can rewrite parent-space position compensation.
                    -- Position must be the final assignment to keep world Z unchanged.
                    helper.pos=parentStartTM.pos+[0,-distances[frameIndex],0]
                )
            )
        )
        true
    ),
    fn setHelperPath helper radiusM leanDeg =
    (
        if radiusM <= 0.0 do throw "弧线半径必须大于0。"
        if leanDeg < 0.0 or leanDeg > 60.0 do throw "倾斜角度必须在0-60度之间。"
        local nodes=OPArcRunCreatorBackend.resolveHelperNodes helper
        local originalParent=nodes[2]; local frameRange=OPArcRunCreatorBackend.readHelperRange helper
        local startFrame=frameRange[1]; local endFrame=frameRange[2]
        local distances=OPArcRunCreatorBackend.parseFloatValues (getUserProp helper "OPArcRunDistances")
        if distances.count != endFrame-startFrame+1 do throw "辅助Root保存的逐帧路程数据不完整，无法更新。"
        local sideSign=if OPArcRunCreatorBackend.helperDirection helper == #left then 1.0 else -1.0
        local radiusCm=radiusM*100.0; local parentStartTM=undefined
        at time startFrame (parentStartTM=originalParent.transform)
        deleteKeys helper.position.controller #allKeys; deleteKeys helper.rotation.controller #allKeys
        animate on
        (
            for frameIndex=1 to distances.count do
            (
                local frameNumber=startFrame+frameIndex-1; local pathDistance=distances[frameIndex]
                local arcDegrees=(pathDistance/radiusCm)*180.0/pi
                local offsetX=sideSign*radiusCm*(1.0-cos arcDegrees); local offsetY=-radiusCm*sin arcDegrees
                local yawQuat=(angleaxis (sideSign*arcDegrees) [0,0,1]) as quat
                local tangentAxis=normalize [sideSign*sin arcDegrees,-cos arcDegrees,0]
                local bankQuat=(angleaxis (-sideSign*leanDeg) tangentAxis) as quat
                at time frameNumber
                (
                    helper.rotation=bankQuat*yawQuat*parentStartTM.rotation
                    -- Keep the arc on the source world-height plane even when the
                    -- original Root uses a -90 degree Biped axis conversion.
                    helper.pos=parentStartTM.pos+[offsetX,offsetY,0]
                )
            )
        )
        setUserProp helper "OPArcRunRadiusM" radiusM; setUserProp helper "OPArcRunLeanDeg" leanDeg
        completeRedraw(); true
    ),
    fn generateHelper direction =
    (
        if direction != #left and direction != #right do throw "无效的弧线方向。"
        local bipObj=OPArcRunCreatorBackend.selectedCOM()
        if bipObj == undefined do throw "请只选择角色的Biped COM（质心），再点击生成按钮。"
        local bipCtrl=bipObj.controller; local startFrame=(animationRange.start.frame as integer)
        local endFrame=(animationRange.end.frame as integer); local oldTime=sliderTime
        local originalParent=bipObj.parent; local keyFrames=#(); local sourceTMs=#(); local distances=#()
        local helper=undefined; local restoreLayerCreated=false; local restoreLayer=1
        local baseLayerSelected=false
        try(biped.setCurrentLayer bipCtrl 0; baseLayerSelected=true)catch(baseLayerSelected=false)
        if not baseLayerSelected do throw "无法切换到Biped基础层。"
        keyFrames=OPArcRunCreatorBackend.collectCOMKeyFrames bipObj startFrame endFrame
        OPArcRunCreatorBackend.validateBaseSource bipObj keyFrames startFrame endFrame
        for frameNumber=startFrame to endFrame do at time frameNumber (append sourceTMs bipObj.transform)
        local firstY=sourceTMs[1].pos.y
        for sourceTM in sourceTMs do append distances (firstY-sourceTM.pos.y)
        local actualDistance=distances[distances.count]
        if actualDistance <= 0.0 do throw "COM尾帧没有沿世界-Y方向前进。"
        local durationSeconds=((endFrame-startFrame) as float)/OPArcRunCreatorBackend.requiredFPS
        local sourceSpeedCmPerSecond=actualDistance/durationSeconds
        local helperName=if direction == #left then "Left_Root" else "Right_Root"
        try
        (
            undo "Generate Arc Run Helper" on
            (
                helper=OPArcRunCreatorBackend.makeHelperBone helperName originalParent startFrame
                OPArcRunCreatorBackend.setStraightHelperPath helper originalParent startFrame distances
                bipObj.parent=helper
                biped.createLayer bipCtrl restoreLayer "ArcRun_Restore"; restoreLayerCreated=true
                biped.setCurrentLayer bipCtrl restoreLayer
                animate on
                (
                    for frameIndex=1 to sourceTMs.count do
                    (
                        sliderTime=startFrame+frameIndex-1
                        biped.setTransform bipObj #pos sourceTMs[frameIndex].pos true
                        biped.setTransform bipObj #rotation sourceTMs[frameIndex].rotation true
                    )
                )
                OPArcRunCreatorBackend.storeHelperMetadata helper direction bipObj originalParent keyFrames startFrame endFrame distances restoreLayer OPArcRunCreatorBackend.defaultRadiusM OPArcRunCreatorBackend.defaultLeanDeg sourceSpeedCmPerSecond
                OPArcRunCreatorBackend.setHelperPath helper OPArcRunCreatorBackend.defaultRadiusM OPArcRunCreatorBackend.defaultLeanDeg
                select helper
            )
        )
        catch
        (
            try(biped.setCurrentLayer bipCtrl 0)catch(); if restoreLayerCreated do try(biped.deleteLayer bipCtrl restoreLayer)catch()
            try(bipObj.parent=originalParent)catch(); if helper != undefined and isValidNode helper do try(delete helper)catch()
            sliderTime=oldTime
            throw
        )
        sliderTime=oldTime; completeRedraw(); helper
    ),
    fn updateHelper helper radiusM leanDeg = (undo "Update Arc Run Path" on OPArcRunCreatorBackend.setHelperPath helper radiusM leanDeg; true),
    fn collapseHelper helper =
    (
        local nodes=OPArcRunCreatorBackend.resolveHelperNodes helper; local bipObj=nodes[1]; local originalParent=nodes[2]
        local bipCtrl=bipObj.controller; local frameRange=OPArcRunCreatorBackend.readHelperRange helper
        local startFrame=frameRange[1]; local endFrame=frameRange[2]
        local keyFrames=OPArcRunCreatorBackend.parseIntegerValues (getUserProp helper "OPArcRunKeyFrames")
        local restoreLayer=try((getUserProp helper "OPArcRunRestoreLayer") as integer)catch(1); local oldTime=sliderTime
        if keyFrames.count == 0 do throw "辅助Root没有保存原COM关键帧。"
        if biped.numLayers bipCtrl != 1 do throw "Biped动画层数量已改变。塌陷前必须只有基础层和ArcRun_Restore层。"
        local targetTMs=#(); for keyFrame in keyFrames do at time keyFrame (append targetTMs bipObj.transform)
        undo "Collapse Arc Run To Biped" on
        (
            biped.setCurrentLayer bipCtrl 0; biped.deleteLayer bipCtrl restoreLayer; bipObj.parent=originalParent
            biped.createLayer bipCtrl 1 "ArcRun_Bake"; biped.setCurrentLayer bipCtrl 1
            animate on
            (
                for keyIndex=1 to keyFrames.count do
                (
                    sliderTime=keyFrames[keyIndex]
                    biped.setTransform bipObj #pos targetTMs[keyIndex].pos true
                    biped.setTransform bipObj #rotation targetTMs[keyIndex].rotation true
                )
            )
            biped.collapseAtLayer bipCtrl 0; biped.setCurrentLayer bipCtrl 0; delete helper; select bipObj
        )
        local maxPositionError=0.0; local maxRotationError=0.0
        for keyIndex=1 to keyFrames.count do at time keyFrames[keyIndex]
        (
            local actualTM=bipObj.transform
            local positionError=distance actualTM.pos targetTMs[keyIndex].pos
            local rotationError=OPArcRunCreatorBackend.rotationErrorDegrees targetTMs[keyIndex].rotation actualTM.rotation
            if positionError > maxPositionError do maxPositionError=positionError
            if rotationError > maxRotationError do maxRotationError=rotationError
        )
        local finalKeyFrames=OPArcRunCreatorBackend.collectCOMKeyFrames bipObj startFrame endFrame
        for frameNumber in finalKeyFrames where findItem keyFrames frameNumber == 0 do throw ("塌陷后COM出现了原关键帧并集之外的关键帧：F"+(frameNumber as string)+"。请立即撤销并反馈。")
        sliderTime=oldTime; completeRedraw(); #(keyFrames.count,maxPositionError,maxRotationError)
    ),
    fn cancelHelper helper =
    (
        local nodes=OPArcRunCreatorBackend.resolveHelperNodes helper; local bipObj=nodes[1]; local originalParent=nodes[2]
        local bipCtrl=bipObj.controller; local restoreLayer=try((getUserProp helper "OPArcRunRestoreLayer") as integer)catch(1)
        if biped.numLayers bipCtrl != 1 do throw "Biped动画层数量已改变，无法安全取消。"
        undo "Cancel Arc Run Helper" on
        (
            biped.setCurrentLayer bipCtrl 0; biped.deleteLayer bipCtrl restoreLayer
            bipObj.parent=originalParent; delete helper; select bipObj
        )
        completeRedraw(); true
    )
)

OPArcRunCreatorBackend=OPArcRunCreatorBackendLib()

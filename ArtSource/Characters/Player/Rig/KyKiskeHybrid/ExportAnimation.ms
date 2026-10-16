/* Selected deform hierarchy bake, independent of the legacy rig-name detector.
   Does not extract Root motion from COM: animate Root explicitly for this first rig.
   Definition only: call KYExportAnimation path firstFrame lastFrame. */
global KYExportAnimation
fn KYExportAnimation outputPath firstFrame lastFrame = (
    if lastFrame<firstFrame do throw "Invalid animation interval."
    local root=getNodeByName "Root" exact:true
    if root==undefined or getUserProp root "KY_RigVersion"==undefined do throw "Expected Player hybrid rig."
    local sourceNodes=#(root)
    join sourceNodes (for n in objects where getUserProp n "KY_Role"=="Deform" collect n)
    local oldSelection=getCurrentSelection()
    local oldTime=sliderTime
    local oldRange=animationRange
    local baked=#(); local exportOK=false
    local savedSettings=false
    local failure=undefined
    try (
        local names=for n in sourceNodes collect n.name
        local parentIndices=#(0)
        for i=2 to sourceNodes.count do (
            local pName=getUserProp sourceNodes[i] "KY_ExportParent"
            local pi=findItem names pName
            if pi==0 do throw ("Unresolved export parent: "+sourceNodes[i].name)
            append parentIndices pi
        )
        local samples=for frame=firstFrame to lastFrame collect (
            sliderTime=frame
            at time frame (for n in sourceNodes collect copy n.transform)
        )
        for i=1 to sourceNodes.count do (
            local boneNode=BoneSys.createBone [0,0,0] [0.01,0,0] [0,0,1]
            boneNode.name="__KY_EXPORT_"+i as string
            boneNode.boneEnable=false; boneNode.boneAutoAlign=false; boneNode.boneFreezeLength=false
            boneNode.rotation.controller=Euler_XYZ()
            boneNode.isHidden=true
            append baked boneNode
        )
        for i=1 to baked.count where parentIndices[i]>0 do baked[i].parent=baked[parentIndices[i]]
        -- The source hierarchy is parent-first; enforce that assumption explicitly.
        for i=1 to baked.count where parentIndices[i]>=i do throw "Export hierarchy is not parent-first."
        for sampleIndex=1 to samples.count do at time (firstFrame+sampleIndex-1) with animate on (
            for i=1 to baked.count do (
                local localTM=copy samples[sampleIndex][i]
                if parentIndices[i]>0 do localTM=localTM*inverse samples[sampleIndex][parentIndices[i]]
                baked[i].controller.value=localTM
            )
        )
        local maxError=0.0
        for sampleIndex=1 to samples.count do at time (firstFrame+sampleIndex-1) (
            for i=1 to baked.count do (
                local actual=baked[i].transform; local expected=samples[sampleIndex][i]
                for row=1 to 4 do maxError=amax maxError (distance actual[row] expected[row])
            )
        )
        if maxError>0.00005 do throw ("Bake validation failed: "+maxError as string)
        for i=1 to baked.count do baked[i].name=names[i]
        animationRange=interval firstFrame lastFrame
        select baked
        pluginManager.loadClass FBXEXP
        FBXExporterSetParam "PushSettings"
        savedSettings=true
        FBXExporterSetParam "Animation" true
        FBXExporterSetParam "BakeAnimation" true
        FBXExporterSetParam "BakeFrameStart" firstFrame
        FBXExporterSetParam "BakeFrameEnd" lastFrame
        FBXExporterSetParam "BakeFrameStep" 1
        FBXExporterSetParam "Cameras" false
        FBXExporterSetParam "Lights" false
        FBXExporterSetParam "UpAxis" "Y"
        FBXExporterSetParam "AxisConversionMethod" "Animation"
        FBXExporterSetParam "ScaleFactor" 1.0
        FBXExporterSetParam "ConvertUnit" "m"
        if not (exportFile outputPath #noPrompt selectedOnly:true using:FBXEXP) do throw "FBX export failed."
        exportOK=doesFileExist outputPath
        if not exportOK do throw "FBX exporter did not create the requested file."
        format "KY_EXPORT_OK nodes=% frames=% error=% file=%\n" baked.count samples.count maxError outputPath
    )catch(failure=getCurrentException())
    if savedSettings do FBXExporterSetParam "PopSettings"
    if baked.count>0 do delete baked
    sliderTime=oldTime; animationRange=oldRange
    select oldSelection
    if failure!=undefined do throw failure
    exportOK
)

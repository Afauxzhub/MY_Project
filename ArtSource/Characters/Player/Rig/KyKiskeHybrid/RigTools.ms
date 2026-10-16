/* Run Script to open. No startup hooks or external runtime dependencies. */
global KYRigPanel
try(destroyDialog KYRigPanel)catch()
fn KYRigShow category = (
    for n in objects where getUserProp n "KY_Role"=="Control" do n.isHidden=((getUserProp n "KY_Category")!=category)
    redrawViews()
)
fn KYRigSelectCategory category rootsOnly:false = (
    local controls=for n in objects where getUserProp n "KY_Role"=="Control" and getUserProp n "KY_Category"==category collect n
    if rootsOnly do controls=for n in controls where (
        local src=getNodeByName (substring n.name 6 -1) exact:true
        src!=undefined and (src.parent==undefined or getUserProp src.parent "KY_Driver"==undefined or not matchPattern (getUserProp src.parent "KY_Driver") pattern:"CTRL_*")
    ) collect n
    select controls
)
rollout KYRigPanel "Player Biped Hybrid" width:260 (
    label info "Body: animate Bip. Extras: show a group." align:#left
    button body "Select Bip / hide extras" width:238
    dropdownlist groups "Extra controls" items:#("Face","Hair","Cloth","Correctives") width:238
    button selectGroup "Select shown controls" width:238
    button faceSettings "Select face settings (Modify panel)" width:238
    button head "Select Bip head" width:116 across:2
    button root "Select Root" width:116
    checkbox meshXray "Mesh see-through" checked:false
    button resetSelected "Key selected extras to rest here" width:238
    label storage "Save the .max to retain ALL controls." align:#left
    label exportNote "Use ExportAnimation.ms for this rig." align:#left
    on body pressed do (
        KYRigShow ""
        select (for n in objects where classof n==Biped_Object and not matchPattern n.name pattern:"*Footsteps*" collect n)
    )
    on groups selected i do KYRigShow groups.items[i]
    on selectGroup pressed do KYRigSelectCategory groups.items[groups.selection]
    on faceSettings pressed do (
        KYRigShow "Face"
        local n=getNodeByName "CTRL_FaceSettings"
        if n!=undefined do (select n; max modify mode)
    )
    on head pressed do select (getNodeByName "Bip001 Head")
    on root pressed do select (getNodeByName "Root")
    on meshXray changed value do (local n=getNodeByName "PlayerMesh"; if n!=undefined do n.xray=value)
    on resetSelected pressed do (
        undo "Key extras to rest" on with animate on (
            for n in selection where getUserProp n "KY_Role"=="Control" do (
                local rest=getUserProp n "KY_RestLocal"
                if rest!=undefined do n.transform=(execute rest)*n.parent.transform
            )
        )
    )
)
createDialog KYRigPanel

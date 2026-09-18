/*
  武器状态工具 — 独立 MaxScript 对话框（可选）
  安装后位于 plugins\RootMotionTool\maxscript\
  也可由「Scripts\Weapon\WeaponConstraintState.ms」转发 fileIn 本文件打开。
*/
try(destroyDialog OPWeaponStateDlg)catch()

local _lib = pathConfig.appendPath (getFilenamePath (getSourceFileName)) "op_weapon_state_lib.ms"
if doesFileExist _lib then fileIn _lib else ( messageBox ("缺少核心库：\n" + _lib) title:"武器状态工具"; return() )

rollout OPWeaponStateDlg "武器状态工具" width:360 height:630
(
    groupBox grp_base "1. 基础命名" pos:[10,10] width:340 height:110
    label lbl_attrName "折叠菜单名:" pos:[20,30] width:80
    edittext edt_attrName "" text:"WeaponState" pos:[100,28] width:230

    label lbl_paramName "引擎参数名:" pos:[20,60] width:80
    edittext edt_paramName "" text:"State_Weapon" pos:[100,58] width:230

    label lbl_weaponNode "Unity武器Mesh短名:" pos:[20,90] width:110
    edittext edt_weaponNode "" text:"" pos:[130,88] width:200

    groupBox grp_states "2. 状态列表 (顺序即引擎ID 1,2,3...)" pos:[10,130] width:340 height:240
    label lbl_newState "单个状态名:" pos:[20,150] width:70
    edittext edt_newState "" pos:[90,148] width:170
    button btn_addState "添加" pos:[270,147] width:70

    listbox lbx_states "" pos:[20,180] width:320 height:8 items:#("右手", "左手", "背后", "空中")

    button btn_removeState "删除选中项" pos:[20,325] width:160 height:30
    button btn_clearStates "清空所有" pos:[190,325] width:160 height:30

    button btn_apply "3. 生成属性 (自动挂载至修改器)" pos:[10,365] width:340 height:38
    button btn_fixStep "4. [导出前点击] 一键转为阶梯帧 (Step)" pos:[10,410] width:340 height:34

    groupBox grp_export "6. Max→Unity 武器状态映射表" pos:[10,452] width:340 height:88
    button btn_exportJson "导出 JSON (含父子级 hierarchyNodes)" pos:[20,475] width:320 height:28
    label lbl_jsonHint "导出前须选中骨骼层级；JSON 内 nodeName/parentName 与 Max 一致" pos:[20,508] width:320 height:28

    button btn_deleteAttr "5. [危险] 一键清除选中骨骼的挂点属性" pos:[10,550] width:340 height:34

    on btn_addState pressed do ( if edt_newState.text != "" do ( local currentItems = lbx_states.items; append currentItems edt_newState.text; lbx_states.items = currentItems; edt_newState.text = "" ) )
    on edt_newState entered txt do ( if txt != "" do ( local currentItems = lbx_states.items; append currentItems txt; lbx_states.items = currentItems; edt_newState.text = "" ) )
    on btn_removeState pressed do ( if lbx_states.selection > 0 do ( local currentItems = lbx_states.items; deleteItem currentItems lbx_states.selection; lbx_states.items = currentItems ) )
    on btn_clearStates pressed do ( lbx_states.items = #() )

    on btn_apply pressed do
    (
        local r = OP_WS_Apply edt_attrName.text edt_paramName.text lbx_states.items
        if r[1] == 0 then messageBox r[2] title:"成功" else messageBox r[2] title:"提示"
    )

    on btn_fixStep pressed do
    (
        local r = OP_WS_FixStep edt_attrName.text edt_paramName.text
        if r[1] == 0 then messageBox r[2] title:"成功" else messageBox r[2] title:"提示"
    )

    on btn_exportJson pressed do
    (
        if lbx_states.items.count == 0 do ( messageBox "请至少添加一个状态后再导出。" title:"提示"; return() )
        if selection.count < 1 do ( messageBox "请先选中要导出父子级的骨骼/挂点层级（可多选根），以便写入 hierarchyNodes。" title:"提示"; return() )
        local defName = if maxFileName != undefined and maxFileName != "" then ((getFilenameFile maxFileName) + "_WeaponStateMapping.json") else "WeaponStateMapping.json"
        local p = getSaveFileName caption:"保存武器状态映射 JSON" types:"JSON文件(*.json)|*.json|所有文件|*.*|" filename:defName
        if p == undefined do return()
        if OP_WS_WriteMappingJson p edt_attrName.text edt_paramName.text lbx_states.items maxFileName edt_weaponNode.text then
            messageBox ("已导出:\n" + p) title:"完成"
        else
            messageBox "写入失败，请检查路径权限。" title:"错误"
    )

    on btn_deleteAttr pressed do
    (
        if selection.count == 0 do ( messageBox "请先选中骨骼！" title:"提示"; return() )
        local attrName = edt_attrName.text
        if queryBox ("确定删除属性 [" + attrName + "] 吗？\n\n警告：关键帧将丢失，不可恢复！") title:"确认" do
        (
            local r = OP_WS_DeleteAttr attrName
            messageBox r[2] title:"结果"
        )
    )
)

createDialog OPWeaponStateDlg style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

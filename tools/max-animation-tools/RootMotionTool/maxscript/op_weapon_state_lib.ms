/*
  Animation 武器状态 Custom Attribute — 核心逻辑（无 UI）
  由 Python 发布工具「武器约束绑定」页或 op_weapon_state_dialog.ms 调用。
  修改器显示名固定为「武器挂点数据」。
*/

global OP_WS_ModifierDisplayName
OP_WS_ModifierDisplayName = "武器挂点数据"

-- pymxs 下 custAttributes.getDef(...).source 常为空，供 Python 侧回退读取 CA 定义文本
fn OP_WS_GetCACustDefSource mod caIndex =
(
    local d = undefined
    try ( d = custAttributes.getDef mod caIndex ) catch()
    if d == undefined then ""
    else (
        local s = undefined
        try ( s = d.source ) catch()
        if s != undefined then (s as string) else ""
    )
)

fn OP_WS_JsonEscape s =
(
    if s == undefined do s = ""
    local r = substituteString (s as string) "\\" "\\\\"
    r = substituteString r "\"" "\\\""
    r = substituteString r "\r" "\\r"
    r = substituteString r "\n" "\\n"
    r
)

fn OP_WS_BuildCAdef attrName pName stateNames =
(
    local stateCount = stateNames.count
    if stateCount < 1 do return undefined
    local arrStr = "#("
    for i = 1 to stateCount do
    (
        arrStr += "\"" + stateNames[i] + "\""
        if i < stateCount do arrStr += ","
    )
    arrStr += ")"
    local scriptStr = ""
    scriptStr += "attributes \"" + attrName + "\"\n"
    scriptStr += "(\n"
    scriptStr += "  parameters main rollout:paramsRollout\n"
    scriptStr += "  (\n"
    scriptStr += "      " + pName + " type:#integer ui:sld_state default:1\n"
    scriptStr += "  )\n"
    scriptStr += "  rollout paramsRollout \"" + attrName + "\"\n"
    scriptStr += "  (\n"
    scriptStr += "      local stateNames = " + arrStr + "\n"
    scriptStr += "      label lbl_current \"当前状态: \" align:#left\n"
    scriptStr += "      slider sld_state \"\" range:[1," + (stateCount as string) + ",1] type:#integer ticks:0\n"
    scriptStr += "      fn updateUI val = ( local iv = val as integer; if iv < 1 do iv = 1; if iv > stateNames.count do iv = stateNames.count; lbl_current.text = \"当前挂点 [ID:\" + (iv as string) + \"] --> \" + stateNames[iv] )\n"
    scriptStr += "      on paramsRollout open do updateUI " + pName + "\n"
    scriptStr += "      on sld_state changed val do updateUI val\n"
    scriptStr += "  )\n"
    scriptStr += ")\n"
    execute scriptStr
)

fn OP_WS_Apply attrName pName stateNames =
(
    if selection.count == 0 do ( return #(-1, "请先选中骨骼！") )
    if stateNames == undefined or stateNames.count == 0 do ( return #(-1, "请至少添加一个状态！") )
    local newDef = OP_WS_BuildCAdef attrName pName stateNames
    if newDef == undefined do ( return #(-1, "生成属性定义失败。") )
    for obj in selection do
    (
        local targetMod = undefined
        for m in obj.modifiers do ( if classOf m == EmptyModifier and m.name == OP_WS_ModifierDisplayName do targetMod = m )
        if targetMod == undefined do
        (
            targetMod = EmptyModifier name:OP_WS_ModifierDisplayName
            addModifier obj targetMod
        )
        local existingIndex = 0
        local count = custAttributes.count targetMod
        for i = 1 to count do
        (
            local def = custAttributes.getDef targetMod i
            if def.name == attrName then existingIndex = i
        )
        if existingIndex > 0 then
            ( custAttributes.redefine (custAttributes.getDef targetMod existingIndex) newDef.source )
        else
            ( custAttributes.add targetMod newDef )
    )
    #(0, "生成成功！请去修改面板查看，属性已挂载到「武器挂点数据」修改器。")
)

fn OP_WS_FixStep attrName pName =
(
    if selection.count == 0 do ( return #(-1, "请先选中骨骼。") )
    local fixedCount = 0
    for obj in selection do
    (
        try
        (
            local targetMod = undefined
            for m in obj.modifiers do ( if classOf m == EmptyModifier and m.name == OP_WS_ModifierDisplayName do targetMod = m )
            if targetMod != undefined do
            (
                local theCtrl = getPropertyController (getProperty targetMod attrName) pName
                if theCtrl != undefined and theCtrl.keys.count > 0 then
                (
                    for k in theCtrl.keys do
                    (
                        try ( k.value = floor (k.value + 0.5) ) catch()
                        k.inTangentType = #step
                        k.outTangentType = #step
                    )
                    fixedCount += 1
                )
            )
        ) catch()
    )
    if fixedCount > 0 then #(0, "转阶梯帧成功！") else #(-1, "未找到帧数据。")
)

fn OP_WS_SetStateKey attrName pName stateId =
(
    if selection.count == 0 do ( return #(-1, "请先选中武器骨骼。") )
    local keyCount = 0
    for obj in selection do
    (
        try
        (
            local targetMod = undefined
            for m in obj.modifiers do ( if classOf m == EmptyModifier and m.name == OP_WS_ModifierDisplayName do targetMod = m )
            if targetMod != undefined do
            (
                local ca = getProperty targetMod attrName
                if ca != undefined do
                (
                    animate on
                    (
                        setProperty ca pName (stateId as integer)
                    )
                    local theCtrl = getPropertyController ca pName
                    if theCtrl != undefined do
                    (
                        try(addNewKey theCtrl sliderTime)catch()
                        for k in theCtrl.keys do
                        (
                            try ( k.inTangentType = #step ) catch()
                            try ( k.outTangentType = #step ) catch()
                        )
                        keyCount += 1
                    )
                )
            )
        ) catch()
    )
    if keyCount > 0 then #(0, ("已在当前帧写入武器约束 ID=" + (stateId as string) + "。")) else #(-1, "未找到可写入的武器状态属性，请先更新武器约束状态。")
)

fn OP_WS_DeleteAttr attrName =
(
    if selection.count == 0 do ( return #(-1, "请先选中要清理的骨骼。") )
    local deletedCount = 0
    for obj in selection do
    (
        for i = (custAttributes.count obj) to 1 by -1 do
        (
            if (custAttributes.getDef obj i).name == attrName do
            (
                custAttributes.delete obj i
                deletedCount += 1
            )
        )
        for m in obj.modifiers do
        (
            for i = (custAttributes.count m) to 1 by -1 do
            (
                if (custAttributes.getDef m i).name == attrName do
                (
                    custAttributes.delete m i
                    deletedCount += 1
                )
            )
            if classOf m == EmptyModifier and m.name == OP_WS_ModifierDisplayName and (custAttributes.count m) == 0 do
                deleteModifier obj m
        )
    )
    #(0, ("清理完毕，共 " + (deletedCount as string) + " 处。"))
)

-- ── 发布流程：在 MaxScript 内扫描场景（for m in obj.modifiers + d.source），
--    供 pymxs 调用；避免 Python 侧 list(node.modifiers)/dfn.source 取不到数据的问题。

fn OP_WS_GetAllDescendants rootNode =
(
    local result = #()
    if isValidNode rootNode do
    (
        local stack = #(rootNode)
        while stack.count > 0 do
        (
            local curr = stack[stack.count]
            stack.count = stack.count - 1
            for c in curr.children do
            (
                append stack c
                append result c
            )
        )
    )
    result
)

fn OP_WS_GetAllSceneNodesBFS =
(
    local out = #()
    local stack = #()
    for c in rootNode.children do append stack c
    while stack.count > 0 do
    (
        local curr = stack[stack.count]
        stack.count = stack.count - 1
        append out curr
        for ch in curr.children do append stack ch
    )
    out
)

fn OP_WS_RegexFirstGroup pat txt =
(
    if txt == undefined or pat == undefined do return undefined
    try
    (
        local R = dotNetClass "System.Text.RegularExpressions.Regex"
        local RO = dotNetClass "System.Text.RegularExpressions.RegexOptions"
        local r = dotNetObject "System.Text.RegularExpressions.Regex" pat (RO.IgnoreCase)
        local m = r.Match txt
        if m.Success then m.Groups.item[1].value else undefined
    )
    catch undefined
)

fn OP_WS_ParseStateLabelsFromSrc src =
(
    if src == undefined or src == "" then return #()
    local inner = OP_WS_RegexFirstGroup @"local\s+stateNames\s*=\s*#\(([^)]*)\)" src
    if inner == undefined do inner = OP_WS_RegexFirstGroup @"\bstateNames\s*=\s*#\(([^)]*)\)" src
    if inner == undefined do return #()
    local out = #()
    local s = inner as string
    local i = 1
    while i <= s.count do
    (
        if (substring s i 1) == "\"" then
        (
            local j = i + 1
            local buf = ""
            while j <= s.count and (substring s j 1) != "\"" do ( buf += (substring s j 1); j += 1 )
            append out buf
            i = j + 1
        )
        else i += 1
    )
    out
)

fn OP_WS_ParseAttrBlockName src =
(
    if src == undefined or src == "" then return ""
    local tok = "attributes \""
    local p = findString (toLower src) (toLower tok)
    if p == undefined do return ""
    local startPos = p + tok.count
    local rest = substring src startPos 999999
    local q = findString rest "\""
    if q == undefined or q < 1 do return ""
    substring rest 1 (q - 1)
)

fn OP_WS_ParseCurveParamName src =
(
    if src == undefined or src == "" then return ""
    try
    (
        local R = dotNetClass "System.Text.RegularExpressions.Regex"
        local RO = dotNetClass "System.Text.RegularExpressions.RegexOptions"
        local r = dotNetObject "System.Text.RegularExpressions.Regex" @"([A-Za-z0-9_]+)\s+type:\s*#(?:float|integer)" (RO.IgnoreCase)
        local ms = r.Matches src
        local best = undefined
        local first = undefined
        local k = 0
        while k < ms.count do
        (
            local name = (ms.item[k]).Groups.item[1].value
            if first == undefined do first = name
            if best == undefined and (matchPattern (toLower name) pattern:"state*") do best = name
            k += 1
        )
        if best != undefined then best else ( if first != undefined then first else "" )
    )
    catch ""
)

fn OP_WS_AppendUniqueNodes targetArr handleArr node =
(
    if not isValidNode node do return()
    local h = getHandleByAnim node
    if findItem handleArr h > 0 do return()
    append handleArr h
    append targetArr node
)

fn OP_WS_BuildScanNodeList rootObj bipObj sceneWide =
(
    local nodes = #()
    local handles = #()
    if isValidNode rootObj do
    (
        OP_WS_AppendUniqueNodes nodes handles rootObj
        for d in (OP_WS_GetAllDescendants rootObj) do OP_WS_AppendUniqueNodes nodes handles d
    )
    if isValidNode bipObj do
    (
        OP_WS_AppendUniqueNodes nodes handles bipObj
        for d in (OP_WS_GetAllDescendants bipObj) do OP_WS_AppendUniqueNodes nodes handles d
    )
    if sceneWide do
    (
        for o in (OP_WS_GetAllSceneNodesBFS()) do OP_WS_AppendUniqueNodes nodes handles o
    )
    nodes
)

fn OP_WS_StatesKey labels =
(
    local s = ""
    for i = 1 to labels.count do
    (
        if i > 1 do s += "|"
        s += labels[i] as string
    )
    s
)

fn OP_WS_BuildWeaponMappingEntriesJsonString rootObj bipObj sceneWide =
(
    local nodes = OP_WS_BuildScanNodeList rootObj bipObj sceneWide
    local seenKeys = #()
    local parts = #()
    for obj in nodes do
    (
        if not isValidNode obj do continue
        for m in obj.modifiers do
        (
            if (classOf m != EmptyModifier) or (m.name != OP_WS_ModifierDisplayName) do continue
            local cc = custAttributes.count m
            for ci = 1 to cc do
            (
                local src = OP_WS_GetCACustDefSource m ci
                if src == undefined or src == "" do continue
                local labels = OP_WS_ParseStateLabelsFromSrc src
                if labels.count == 0 do continue
                local curve = OP_WS_ParseCurveParamName src
                local attrNm = OP_WS_ParseAttrBlockName src
                local bone = obj.name as string
                local sk = bone + "\t" + attrNm + "\t" + curve + "\t" + (OP_WS_StatesKey labels)
                if findItem seenKeys sk > 0 do continue
                append seenKeys sk
                local jb = OP_WS_JsonEscape bone
                local ja = OP_WS_JsonEscape attrNm
                local jc = OP_WS_JsonEscape curve
                local one = "{\"boneName\":\"" + jb + "\",\"weaponNode\":\"\",\"attributeBlockName\":\"" + ja + "\",\"curveParameterName\":\"" + jc + "\",\"states\":["
                for si = 1 to labels.count do
                (
                    if si > 1 do one += ","
                    one += "{\"id\":" + (si as string) + ",\"displayName\":\"" + (OP_WS_JsonEscape labels[si]) + "\",\"constraintNode\":\"\"}"
                )
                one += "]}"
                append parts one
            )
        )
    )
    local body = ""
    for pi = 1 to parts.count do
    (
        if pi > 1 do body += ","
        body += parts[pi]
    )
    "[" + body + "]"
)

-- 从当前选择收集层级：选中根及其子树内每个节点一条 { nodeName, parentName }，名称与 Max 完全一致（供 Unity 1:1 复刻）。
fn OP_WS_CollectHierarchyRecordsFromSelection =
(
    local records = #()
    if selection.count < 1 do return records
    local nodes = #()
    local handles = #()
    for si = 1 to selection.count do
    (
        local sel = selection[si]
        if isValidNode sel do OP_WS_AppendUniqueNodes nodes handles sel
        for d in (OP_WS_GetAllDescendants sel) do OP_WS_AppendUniqueNodes nodes handles d
    )
    for n in nodes do
    (
        local nm = n.name as string
        local pname = ""
        if isValidNode n.parent do pname = n.parent.name as string
        append records #(nm, pname)
    )
    records
)

fn OP_WS_WriteMappingJson outPath attrName pName stateItems maxBaseName weaponNodeStr =
(
    if stateItems == undefined or stateItems.count == 0 do return false
    if weaponNodeStr == undefined do weaponNodeStr = ""
    local fs = createFile outPath
    if fs == undefined do return false
    local hier = OP_WS_CollectHierarchyRecordsFromSelection()
    format "{\n" to:fs
    format "  \"formatVersion\": 2,\n" to:fs
    format "  \"sourceMaxFile\": \"%\",\n" (OP_WS_JsonEscape maxBaseName) to:fs
    format "  \"entries\": [\n" to:fs
    format "    {\n" to:fs
    format "      \"boneName\": \"\",\n" to:fs
    format "      \"weaponNode\": \"%\",\n" (OP_WS_JsonEscape weaponNodeStr) to:fs
    format "      \"attributeBlockName\": \"%\",\n" (OP_WS_JsonEscape attrName) to:fs
    format "      \"curveParameterName\": \"%\",\n" (OP_WS_JsonEscape pName) to:fs
    format "      \"states\": [\n" to:fs
    for i = 1 to stateItems.count do
    (
        format "        { \"id\": %, \"displayName\": \"%\", \"constraintNode\": \"\" }" i (OP_WS_JsonEscape stateItems[i]) to:fs
        if i < stateItems.count then format ",\n" to:fs else format "\n" to:fs
    )
    format "      ]\n" to:fs
    format "    }\n" to:fs
    format "  ],\n" to:fs
    format "  \"hierarchyNodes\": [\n" to:fs
    if hier.count > 0 then
    (
        for hi = 1 to hier.count do
        (
            format "    { \"nodeName\": \"%\", \"parentName\": \"%\" }" (OP_WS_JsonEscape hier[hi][1]) (OP_WS_JsonEscape hier[hi][2]) to:fs
            if hi < hier.count then format ",\n" to:fs else format "\n" to:fs
        )
    )
    format "  ]\n" to:fs
    format "}\n" to:fs
    close fs
    true
)

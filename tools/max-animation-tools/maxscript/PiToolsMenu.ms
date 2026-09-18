/*
PiTools main menu registration for 3ds Max 2020.
Loaded by install_animation_tools.ms and AnimationToolsMenuStartup.ms.
*/

global PiTools_Menu

struct PiToolsMenuLib
(
    menuCategory = "PiTools",
    menuTitle = "动画工具",
    hubRelative = "RootMotionTool\\op_tools_hub.py",
    startupScriptName = "AnimationToolsMenuStartup.ms",
    menuContextId = 0x50495430,

    fn escapeForString value =
    (
        substituteString (value as string) "\"" "\\\""
    ),

    fn writeTextFileUtf8 filePath content =
    (
        -- Max 2020 MaxScript 无法访问 Encoding.UTF8，改用 UTF8Encoding 实例。
        local utf8 = dotNetObject "System.Text.UTF8Encoding" true
        (dotNetClass "System.IO.File").WriteAllText filePath (content as string) utf8
        true
    ),

    fn installRoot =
    (
        if RR_Launcher != undefined then
            RR_Launcher.installRoot()
        else
            (getDir #userScripts) + "\\AnimationTools\\"
    ),

    fn hubPath =
    (
        PiTools_Menu.installRoot() + PiTools_Menu.hubRelative
    ),

    fn findMenuByTitle title =
    (
        local mainBar = menuMan.getMainMenuBar()
        if mainBar == undefined then return undefined
        local i
        for i = 1 to mainBar.numItems() do
        (
            local item = mainBar.getItem i
            if item != undefined then
            (
                local subMenu = item.getSubMenu()
                if subMenu != undefined and subMenu.getTitle() == title then
                    return subMenu
            )
        )
        undefined
    ),

    fn clearMenuItems targetMenu =
    (
        if targetMenu == undefined then return false
        while targetMenu.numItems() > 0 do
        (
            local item = targetMenu.getItem 1
            if item == undefined then exit
            targetMenu.removeItem item
        )
        true
    ),

    fn _reloadLauncher =
    (
        local launcherFile = PiTools_Menu.installRoot() + "maxscript\\ReferenceRigLauncher.ms"
        if doesFileExist launcherFile do fileIn launcherFile
        RR_Launcher != undefined
    ),

    fn _ensureAutoSync =
    (
        PiTools_Menu._reloadLauncher()
        if RR_Launcher != undefined do RR_Launcher.autoSyncLocalInstall silent:true
        true
    ),

    fn runHub methodName =
    (
        PiTools_Menu._ensureAutoSync()
        local hubFile = PiTools_Menu.hubPath()
        if not doesFileExist hubFile then
        (
            messageBox ("Tool hub not found:\n" + hubFile) title:"PiTools"
            return false
        )
        local py =
            "import sys\n" + \
            "hub = r'" + (PiTools_Menu.escapeForString hubFile) + "'\n" + \
            "import imp\n" + \
            "mod = imp.load_source('op_tools_hub', hub)\n" + \
            "getattr(mod, '" + methodName + "')()\n"
        try
        (
            python.Execute py
            true
        )
        catch
        (
            messageBox ("Run failed:\n" + methodName + "\n\n" + (getCurrentException() as string)) title:"PiTools"
            false
        )
    ),

    fn isDevMachine =
    (
        PiTools_Menu._reloadLauncher()
        if RR_Launcher == undefined then return false
        RR_Launcher.ensureConfigDefaults()
        local src = RR_Launcher.readIni "SourceRoot" ""
        local pub = RR_Launcher.readIni "FixedPublicSource" RR_Launcher.fixedPublicSource
        if not (RR_Launcher.isValidSourceRoot src) then return false
        (toLower (trimRight src "\\/")) != (toLower (trimRight pub "\\/"))
    ),

    fn writeMacro macroName buttonText toolTip methodName =
    (
        local macroPath = (getDir #userMacros) + "\\" + macroName + ".mcr"
        local menuPath = PiTools_Menu.installRoot() + "maxscript\\PiToolsMenu.ms"
        local launcherPath = PiTools_Menu.installRoot() + "maxscript\\ReferenceRigLauncher.ms"

        local content = ""
        content += "macroScript " + macroName + "\n"
        content += "category:\"" + PiTools_Menu.menuCategory + "\"\n"
        content += "toolTip:\"" + (PiTools_Menu.escapeForString toolTip) + "\"\n"
        content += "buttonText:\"" + (PiTools_Menu.escapeForString buttonText) + "\"\n"
        content += "(\n"
        content += "    global RR_Launcher\n"
        content += "    global PiTools_Menu\n"
        content += "    local launcherFile = @\"" + (PiTools_Menu.escapeForString launcherPath) + "\"\n"
        content += "    if doesFileExist launcherFile do fileIn launcherFile\n"
        content += "    if RR_Launcher != undefined do RR_Launcher.autoSyncLocalInstall silent:true\n"
        content += "    fileIn @\"" + (PiTools_Menu.escapeForString menuPath) + "\"\n"
        content += "    if PiTools_Menu != undefined do PiTools_Menu.runHub \"" + methodName + "\"\n"
        content += ")\n"

        if not (PiTools_Menu.writeTextFileUtf8 macroPath content) then
            throw ("Cannot write macro file: " + macroPath)

        try (fileIn macroPath) catch()
        macroPath
    ),

    fn writeUpdateMacro =
    (
        local macroPath = (getDir #userMacros) + "\\PiTools_Update.mcr"
        local launcherPath = PiTools_Menu.installRoot() + "maxscript\\ReferenceRigLauncher.ms"

        local content = ""
        content += "macroScript PiTools_Update\n"
        content += "category:\"" + PiTools_Menu.menuCategory + "\"\n"
        content += "toolTip:\"更新工具\"\n"
        content += "buttonText:\"更新工具\"\n"
        content += "(\n"
        content += "    global RR_Launcher\n"
        content += "    fileIn @\"" + (PiTools_Menu.escapeForString launcherPath) + "\"\n"
        content += "    if RR_Launcher != undefined do RR_Launcher.updateFromSource()\n"
        content += ")\n"

        if not (PiTools_Menu.writeTextFileUtf8 macroPath content) then
            throw ("Cannot write update macro file: " + macroPath)

        try (fileIn macroPath) catch()
        macroPath
    ),

    fn writeArcRunCreatorMacro =
    (
        local macroPath = (getDir #userMacros) + "\\PiTools_ArcRunCreator.mcr"
        local launcherPath = PiTools_Menu.installRoot() + "RootMotionTool\\launch_arc_run_creator.py"

        local content = ""
        content += "macroScript PiTools_ArcRunCreator\n"
        content += "category:\"" + PiTools_Menu.menuCategory + "\"\n"
        content += "toolTip:\"直跑转弧线跑\"\n"
        content += "buttonText:\"直跑转弧线跑\"\n"
        content += "(\n"
        content += "    local launcherPath = @\"" + (PiTools_Menu.escapeForString launcherPath) + "\"\n"
        content += "    if not doesFileExist launcherPath then\n"
        content += "        messageBox (\"Arc Run Creator launcher not found:\\n\" + launcherPath) title:\"直跑转弧线跑\"\n"
        content += "    else\n"
        content += "    (\n"
        content += "        local py = \"import imp\\nimp.load_source('op_arc_run_creator_launcher', r'\" + (PiTools_Menu.escapeForString launcherPath) + \"')\\n\"\n"
        content += "        try (python.Execute py)\n"
        content += "        catch (messageBox (getCurrentException() as string) title:\"直跑转弧线跑\")\n"
        content += "    )\n"
        content += ")\n"

        if not (PiTools_Menu.writeTextFileUtf8 macroPath content) then
            throw "Cannot write Arc Run Creator macro."
        try (fileIn macroPath) catch()
        macroPath
    ),

    fn addActionToMenu targetMenu macroName =
    (
        if targetMenu == undefined then return false
        local act = menuMan.createActionItem macroName PiTools_Menu.menuCategory
        if act == undefined then
        (
            throw ("Cannot create menu action: " + macroName)
        )
        targetMenu.addItem act -1
        true
    ),

    fn registerMainMenu =
    (
        try (menuMan.unRegisterMenuContext PiTools_Menu.menuContextId) catch()
        menuMan.registerMenuContext PiTools_Menu.menuContextId

        local mainBar = menuMan.getMainMenuBar()
        if mainBar == undefined then
        (
            throw "Cannot get main menu bar."
        )

        local targetMenu = PiTools_Menu.findMenuByTitle PiTools_Menu.menuTitle
        if targetMenu == undefined then
        (
            targetMenu = menuMan.createMenu "动画工具"
            if targetMenu == undefined then
            (
                throw "Cannot create PiTools menu."
            )
            local subMenuItem = menuMan.createSubMenuItem "动画工具" targetMenu
            if subMenuItem == undefined then
            (
                throw "Cannot create submenu item."
            )
            mainBar.addItem subMenuItem -1
        )

        PiTools_Menu.clearMenuItems targetMenu

        local items = #(
            #("PiTools_NewFile", "新建文件", "open_new_file_tool"),
            #("PiTools_OpenFile", "打开文件", "open_file_manager"),
            #("PiTools_PublishAnim", "发布动画", "open_publish_tool"),
            #("PiTools_WeaponTool", "武器约束", "open_weapon_tool"),
            #("PiTools_BindingUpdate", "绑定更新", "open_binding_update"),
            #("PiTools_AnimLibrary", "动作库", "open_anim_library"),
            #("PiTools_ShotAssist", "相机功能", "open_shot_assist")
        )

        for entry in items do
        (
            PiTools_Menu.writeMacro entry[1] entry[2] entry[2] entry[3]
            PiTools_Menu.addActionToMenu targetMenu entry[1]
        )

        PiTools_Menu.writeArcRunCreatorMacro()
        PiTools_Menu.addActionToMenu targetMenu "PiTools_ArcRunCreator"

        local convenienceMenu = menuMan.createMenu "便利性工具"
        if convenienceMenu == undefined then
        (
            throw "Cannot create convenience submenu."
        )
        PiTools_Menu.writeMacro "PiTools_AnimScale" "缩放值" "缩放值" "open_anim_scale_tool"
        PiTools_Menu.addActionToMenu convenienceMenu "PiTools_AnimScale"
        PiTools_Menu.writeMacro "PiTools_VisCtrlScaleFix" "显隐Ctrl缩放修复" "显隐Ctrl缩放修复" "open_vis_ctrl_scale_fix_tool"
        PiTools_Menu.addActionToMenu convenienceMenu "PiTools_VisCtrlScaleFix"
        local convenienceItem = menuMan.createSubMenuItem "便利性工具" convenienceMenu
        if convenienceItem == undefined then
        (
            throw "Cannot create convenience submenu item."
        )
        targetMenu.addItem convenienceItem -1

        PiTools_Menu.writeMacro "PiTools_Upload" "上传工具" "上传工具" "upload_tools"
        PiTools_Menu.writeUpdateMacro()

        if PiTools_Menu.isDevMachine() then
            PiTools_Menu.addActionToMenu targetMenu "PiTools_Upload"
        else
            PiTools_Menu.addActionToMenu targetMenu "PiTools_Update"

        menuMan.updateMenuBar()
        true
    ),

    fn menuIsRegistered =
    (
        (PiTools_Menu.findMenuByTitle PiTools_Menu.menuTitle) != undefined
    ),

    fn installStartupHook =
    (
        local startupDir = getDir #userStartupScripts
        if startupDir == undefined or startupDir == "" then
            throw "Cannot resolve userStartupScripts directory."

        local startupPath = startupDir + "\\" + PiTools_Menu.startupScriptName
        local menuFile = PiTools_Menu.installRoot() + "maxscript\\PiToolsMenu.ms"
        local launcherFile = PiTools_Menu.installRoot() + "maxscript\\ReferenceRigLauncher.ms"

        local content = ""
        content += "-- Auto-generated by Animation Tools\n"
        content += "try\n(\n"
        content += "    global RR_Launcher\n"
        content += "    global PiTools_Menu\n"
        content += "    local menuFile = @\"" + (PiTools_Menu.escapeForString menuFile) + "\"\n"
        content += "    local launcherFile = @\"" + (PiTools_Menu.escapeForString launcherFile) + "\"\n"
        content += "    if doesFileExist launcherFile do fileIn launcherFile\n"
        content += "    if RR_Launcher != undefined do RR_Launcher.autoSyncLocalInstall silent:true\n"
        content += "    if doesFileExist menuFile then\n"
        content += "    (\n"
        content += "        PiTools_Menu = undefined\n"
        content += "        fileIn menuFile\n"
        content += "        if PiTools_Menu != undefined do PiTools_Menu.doInstall true\n"
        content += "    )\n"
        content += ")\n"
        content += "catch()\n"

        if doesFileExist startupPath do
        (
            try (deleteFile startupPath) catch()
        )

        if not (PiTools_Menu.writeTextFileUtf8 startupPath content) then
            throw ("Cannot write startup script: " + startupPath)

        true
    ),

    fn doInstall isQuiet =
    (
        try
        (
            PiTools_Menu.registerMainMenu()
            if not (PiTools_Menu.menuIsRegistered()) then
                throw "PiTools menu was not attached to the main menu bar."
            PiTools_Menu.installStartupHook()
            if not isQuiet do
                format "PiTools menu installed.\n"
            true
        )
        catch
        (
            local err = getCurrentException() as string
            format "PiTools menu install failed: %\n" err
            if not isQuiet do
                messageBox ("PiTools menu failed:\n\n" + err) title:"PiTools"
            false
        )
    ),

    fn install =
    (
        PiTools_Menu.doInstall false
    )
)

PiTools_Menu = PiToolsMenuLib()

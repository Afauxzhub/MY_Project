/*
Animation Tools installer

Drag this file into 3ds Max 2020 to install/update the local Animation tools.
It installs to the current user's default scripts folder and creates 2 actions:
1) Open Animation Tools
2) Update Animation Tools
*/

global RR_Installer

struct RR_InstallerLib
(
    toolFolderName = "AnimationTools",
    macroCategory = "Animation Tools",
    openMacroFileName = "Animation_Tools_Open.mcr",
    updateMacroFileName = "Animation_Tools_Update.mcr",
    fixedPublicSource = @"",

    fn isValidSourceRoot pathValue =
    (
        pathValue != undefined and
        pathValue != "" and
        doesDirectoryExist pathValue and
        doesFileExist (pathValue + "\\install_animation_tools.ms") and
        doesFileExist (pathValue + "\\maxscript\\ReferenceRigLauncher.ms") and
        doesFileExist (pathValue + "\\maxscript\\PiToolsMenu.ms") and
        doesFileExist (pathValue + "\\RootMotionTool\\op_tools_hub.py") and
        doesFileExist (pathValue + "\\AnimationLibrary\\launch_plugin.py")
    ),

    fn isProtectedRelativePath relPath =
    (
        local rel = toLower (substituteString (relPath as string) "/" "\\")
        local protected = #(
            "maxscript\\pitoolsmenu.ms",
            "install_pi_tools_menu.ms",
            "rootmotiontool\\op_tools_hub.py"
        )
        (findItem protected rel) > 0
    ),

    fn sourceRoot =
    (
        local sourceFile = getSourceFileName()
        local localSource = ""

        if sourceFile != undefined and sourceFile != "" do
        (
            localSource = getFilenamePath sourceFile
        )

        if RR_Installer.isValidSourceRoot RR_Installer.fixedPublicSource then
        (
            RR_Installer.fixedPublicSource
        )
        else if RR_Installer.isValidSourceRoot localSource then
        (
            localSource
        )
        else
        (
            messageBox ("Animation Tools source was not found.\n\nLocal installer folder is not a complete package, and the fixed public source is unavailable:\n" + RR_Installer.fixedPublicSource) title:"Animation Tools Installer"
            undefined
        )
    ),

    fn installRoot =
    (
        (getDir #userScripts) + "\\" + RR_Installer.toolFolderName
    ),

    fn openMacroFile =
    (
        (getDir #userMacros) + "\\" + RR_Installer.openMacroFileName
    ),

    fn updateMacroFile =
    (
        (getDir #userMacros) + "\\" + RR_Installer.updateMacroFileName
    ),

    fn ensureDir dirPath =
    (
        if dirPath != "" do makeDir dirPath all:true
    ),

    fn shouldSkipFile fileName =
    (
        matchPattern fileName pattern:"*.plan.md" ignoreCase:true or
        matchPattern fileName pattern:"rm_config.json" ignoreCase:true or
        matchPattern fileName pattern:"afm_config.json" ignoreCase:true or
        matchPattern fileName pattern:"afm_user_config.json" ignoreCase:true or
        matchPattern fileName pattern:"config.json" ignoreCase:true
    ),

    fn shouldSkipDir dirName =
    (
        dirName == ".git" or dirName == ".cursor" or dirName == "__pycache__" or dirName == "plans" or dirName == "_RigUpdateBackup" or dirName == "_RigUpdateReports" or dirName == "_RigUpdatePackages"
    ),

    fn _collectRelativeFiles rootDir currentDir:undefined =
    (
        local normalizedRoot = trimRight rootDir "\\/"
        local current = if currentDir == undefined then normalizedRoot else currentDir
        local rels = #()
        local files = getFiles (current + "\\*")
        for filePath in files do
        (
            local rel = substituteString filePath (normalizedRoot + "\\") ""
            local fileName = filenameFromPath filePath
            if not (RR_Installer.shouldSkipFile fileName) do append rels rel
        )

        local dirs = getDirectories (current + "\\*")
        for dirPath in dirs do
        (
            local dirName = getFilenameFile (trimRight dirPath "\\/")
            if not (RR_Installer.shouldSkipDir dirName) do join rels (RR_Installer._collectRelativeFiles rootDir currentDir:dirPath)
        )
        rels
    ),

    fn copyFolder sourceDir targetDir =
    (
        if sourceDir == undefined or sourceDir == "" or not doesDirectoryExist sourceDir then
        (
            throw ("Reference Rig source folder does not exist: " + (sourceDir as string))
        )

        if toLower (trimRight sourceDir "\\/") == toLower (trimRight targetDir "\\/") then
        (
            return true
        )

        RR_Installer.ensureDir targetDir

        local files = getFiles (sourceDir + "\\*")
        for filePath in files do
        (
            local fileName = filenameFromPath filePath
            if not (RR_Installer.shouldSkipFile fileName) do
            (
                local targetFile = targetDir + "\\" + fileName
                if doesFileExist targetFile do deleteFile targetFile
                copyFile filePath targetFile
            )
        )

        local dirs = getDirectories (sourceDir + "\\*")
        for dirPath in dirs do
        (
            local dirName = getFilenameFile (trimRight dirPath "\\/")
            if not (RR_Installer.shouldSkipDir dirName) do
            (
                RR_Installer.copyFolder dirPath (targetDir + "\\" + dirName)
            )
        )

        true
    ),

    fn syncFolder sourceDir targetDir =
    (
        RR_Installer.copyFolder sourceDir targetDir
        local sourceRels = RR_Installer._collectRelativeFiles sourceDir
        local targetRels = RR_Installer._collectRelativeFiles targetDir

        for relPath in targetRels do
        (
            if (findItem sourceRels relPath) == 0 do
            (
                if RR_Installer.isProtectedRelativePath relPath then continue
                local targetFile = targetDir + "\\" + relPath
                if doesFileExist targetFile do deleteFile targetFile
            )
        )
        true
    ),

    fn writeConfig sourceDir targetDir =
    (
        local mainEntry = "maxscript\\ReferenceRig.ms"
        local autoSyncOnOpen = "false"
        if doesFileExist (targetDir + "\\RootMotionTool\\launch_rm_tool.ms") then
        (
            mainEntry = "RootMotionTool\\launch_rm_tool.ms"
        )
        if toLower (trimRight sourceDir "\\/") != toLower (trimRight RR_Installer.fixedPublicSource "\\/") then
        (
            autoSyncOnOpen = "true"
        )

        local configPath = targetDir + "\\ReferenceRigInstall.ini"
        setINISetting configPath "AnimationTools" "SourceRoot" sourceDir
        setINISetting configPath "AnimationTools" "FixedPublicSource" RR_Installer.fixedPublicSource
        setINISetting configPath "AnimationTools" "InstallRoot" targetDir
        setINISetting configPath "AnimationTools" "InstalledAt" ((dotNetClass "System.DateTime").Now.ToString "yyyy-MM-dd HH:mm:ss")
        setINISetting configPath "AnimationTools" "MaxUserScripts" (getDir #userScripts)
        setINISetting configPath "AnimationTools" "MainEntryRelative" mainEntry
        setINISetting configPath "AnimationTools" "AutoSyncOnOpen" autoSyncOnOpen
        configPath
    ),

    fn escapeForString value =
    (
        substituteString value "\"" "\\\""
    ),

    fn writeOpenMacro targetDir =
    (
        local macroPath = RR_Installer.openMacroFile()
        local launcherPath = targetDir + "\\maxscript\\ReferenceRigLauncher.ms"
        local stream = createFile macroPath

        format "macroScript Animation_Tools_Open\n" to:stream
        format "category:%\n" ("\"" + RR_Installer.macroCategory + "\"") to:stream
        format "toolTip:%\n" ("\"OP Tools\"") to:stream
        format "buttonText:%\n" ("\"OP Tools\"") to:stream
        format "(\n" to:stream
        format "    global RR_Animation_LauncherFile\n" to:stream
        format "    global RR_Launcher\n" to:stream
        format "    RR_Animation_LauncherFile = @\"%\"\n" (RR_Installer.escapeForString launcherPath) to:stream
        format "    if doesFileExist RR_Animation_LauncherFile then\n" to:stream
        format "    (\n" to:stream
        format "        fileIn RR_Animation_LauncherFile\n" to:stream
        format "        if RR_Launcher != undefined then\n" to:stream
        format "        (\n" to:stream
        format "            local ok = RR_Launcher.openMainTool()\n" to:stream
        format "            if not ok do messageBox \"Animation Tools 打开失败，请先重新安装。\"\n" to:stream
        format "        )\n" to:stream
        format "        else\n" to:stream
        format "        (\n" to:stream
        format "            messageBox \"ReferenceRigLauncher.ms 加载失败，请重新拖入 install_animation_tools.ms。\"\n" to:stream
        format "        )\n" to:stream
        format "    )\n" to:stream
        format "    else\n" to:stream
        format "    (\n" to:stream
        format "        messageBox (\"Animation launcher was not found:\\n\" + RR_Animation_LauncherFile)\n" to:stream
        format "    )\n" to:stream
        format ")\n" to:stream

        close stream
        fileIn macroPath
        macroPath
    ),

    fn writeUpdateMacro targetDir =
    (
        local macroPath = RR_Installer.updateMacroFile()
        local launcherPath = targetDir + "\\maxscript\\ReferenceRigLauncher.ms"
        local stream = createFile macroPath

        format "macroScript Animation_Tools_Update\n" to:stream
        format "category:%\n" ("\"" + RR_Installer.macroCategory + "\"") to:stream
        format "toolTip:%\n" ("\"Animation Tools Update\"") to:stream
        format "buttonText:%\n" ("\"Animation Tools Update\"") to:stream
        format "(\n" to:stream
        format "    global RR_Animation_LauncherFile\n" to:stream
        format "    global RR_Launcher\n" to:stream
        format "    RR_Animation_LauncherFile = @\"%\"\n" (RR_Installer.escapeForString launcherPath) to:stream
        format "    if doesFileExist RR_Animation_LauncherFile then\n" to:stream
        format "    (\n" to:stream
        format "        fileIn RR_Animation_LauncherFile\n" to:stream
        format "        if RR_Launcher != undefined then\n" to:stream
        format "        (\n" to:stream
        format "            local ok = RR_Launcher.updateFromSource()\n" to:stream
        format "            if not ok do messageBox \"Animation Tools 更新失败，请查看弹窗详情。\"\n" to:stream
        format "        )\n" to:stream
        format "        else\n" to:stream
        format "        (\n" to:stream
        format "            messageBox \"ReferenceRigLauncher.ms 加载失败，请重新拖入 install_animation_tools.ms。\"\n" to:stream
        format "        )\n" to:stream
        format "    )\n" to:stream
        format "    else\n" to:stream
        format "    (\n" to:stream
        format "        messageBox (\"Animation launcher was not found:\\n\" + RR_Animation_LauncherFile)\n" to:stream
        format "    )\n" to:stream
        format ")\n" to:stream

        close stream
        fileIn macroPath
        macroPath
    ),

    fn showResult sourceDir targetDir openMacroPath updateMacroPath =
    (
        local message = "Animation Tools installed.\n\n"
        message += "Source:\n" + sourceDir + "\n\n"
        message += "Local install:\n" + targetDir + "\n\n"
        message += "Fixed public source:\n" + RR_Installer.fixedPublicSource + "\n\n"
        message += "Macro actions:\nAnimation Tools > OP Tools\nAnimation Tools > Animation Tools Update\n\n"
        message += "Main menu: 动画工具\n\n"
        message += "To make permanent toolbar buttons, open Customize > Customize User Interface > Toolbars, choose category Animation Tools, then drag both actions onto a toolbar."
        messageBox message title:"Animation Tools Installer"
    ),

    fn run =
    (
        local src = RR_Installer.sourceRoot()
        if src == undefined or src == "" then
        (
            return false
        )

        local dst = RR_Installer.installRoot()
        RR_Installer.syncFolder src dst
        RR_Installer.writeConfig src dst
        local openMacroPath = RR_Installer.writeOpenMacro dst
        local updateMacroPath = RR_Installer.writeUpdateMacro dst
        local menuFile = dst + "\\maxscript\\PiToolsMenu.ms"
        if doesFileExist menuFile then
        (
            try
            (
                fileIn menuFile
                if PiTools_Menu != undefined do PiTools_Menu.doInstall false
            )
            catch
            (
                messageBox ("动画工具菜单注册失败:\n\n" + (getCurrentException() as string) + "\n\n可拖入 install_pi_tools_menu.ms 单独修复。") title:"Animation Tools Installer"
            )
        )
        RR_Installer.showResult src dst openMacroPath updateMacroPath

        local launcherFilePath = dst + "\\maxscript\\ReferenceRigLauncher.ms"
        if doesFileExist launcherFilePath then
        (
            fileIn launcherFilePath
            if RR_Launcher != undefined do RR_Launcher.openMainTool()
        )
        true
    )
)

RR_Installer = RR_InstallerLib()
RR_Installer.run()

/*
Reference Rig - installed launcher

This file is copied into the local 3ds Max user scripts folder by
install_animation_tools.ms. It opens the main Animation tools entry and can update
the local install from the configured source folder.
*/

global RR_Launcher

struct RR_LauncherLib
(
    toolName = "AnimationTools",
    fixedPublicSource = @"",

    fn _scriptDir =
    (
        getFilenamePath (getSourceFileName())
    ),

    fn installRoot =
    (
        local dirInfo = dotNetObject "System.IO.DirectoryInfo" (RR_Launcher._scriptDir())
        dirInfo.Parent.FullName + "\\"
    ),

    fn configPath =
    (
        (RR_Launcher.installRoot()) + "ReferenceRigInstall.ini"
    ),

    fn readIni key defaultValue =
    (
        local value = getINISetting (RR_Launcher.configPath()) "AnimationTools" key
        if value == undefined or value == "" then defaultValue else value
    ),

    fn writeIni key value =
    (
        setINISetting (RR_Launcher.configPath()) "AnimationTools" key (value as string)
        true
    ),

    fn _normPath pathValue =
    (
        toLower (trimRight (pathValue as string) "\\/")
    ),

    fn readIniBool key defaultValue =
    (
        local defaultString = "false"
        if defaultValue do defaultString = "true"
        local raw = RR_Launcher.readIni key defaultString
        local v = toLower (raw as string)
        (v == "true" or v == "1" or v == "yes" or v == "on")
    ),

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

    fn isDevLikeSource pathValue =
    (
        if not (RR_Launcher.isValidSourceRoot pathValue) then
        (
            return false
        )
        if (RR_Launcher._normPath pathValue) == (RR_Launcher._normPath (RR_Launcher.installRoot())) then
        (
            return false
        )
        if (RR_Launcher._normPath pathValue) != (RR_Launcher._normPath RR_Launcher.fixedPublicSource) then
        (
            return true
        )
        doesFileExist (pathValue + "\\AnimationTools_DevMachine.flag")
    ),

    fn resolveAutoSyncSource =
    (
        local candidates = #()
        local devRoot = RR_Launcher.readIni "DevProjectRoot" ""
        if devRoot != "" do append candidates devRoot

        local envRoot = (dotNetClass "System.Environment").GetEnvironmentVariable "ANIMATION_TOOLS_PROJECT_ROOT"
        if envRoot != undefined and envRoot != "" do append candidates envRoot


        local iniSrc = RR_Launcher.readIni "SourceRoot" ""
        if iniSrc != "" do append candidates iniSrc

        for pathValue in candidates do
        (
            if pathValue == undefined or pathValue == "" then continue
            if RR_Launcher.isDevLikeSource pathValue then return pathValue
        )
        undefined
    ),

    fn autoSyncLocalInstall silent:true =
    (
        RR_Launcher.ensureConfigDefaults()
        local dst = RR_Launcher.installRoot()
        local src = RR_Launcher.resolveAutoSyncSource()
        if src == undefined then return false
        if (RR_Launcher._normPath src) == (RR_Launcher._normPath dst) then return true

        try
        (
            RR_Launcher.syncFolder src dst
            RR_Launcher.writeIni "SourceRoot" src
            RR_Launcher.writeIni "AutoSyncOnOpen" "true"
            RR_Launcher.ensureToolbarMacros()
            local autoTs = (dotNetClass "System.DateTime").Now.ToString "yyyy-MM-dd HH:mm:ss"
            RR_Launcher.writeIni "LastAutoSyncedAt" autoTs
            if not silent do format "Animation Tools synced from %\n" src
            true
        )
        catch
        (
            if not silent do
                messageBox ("Animation Tools 自动同步失败:\n" + src + "\n\n" + (getCurrentException() as string)) title:"Animation Tools Launcher"
            false
        )
    ),

    fn sourceRoot =
    (
        local preferred = RR_Launcher.readIni "SourceRoot" ""
        if RR_Launcher.isValidSourceRoot preferred then
        (
            preferred
        )
        else
        (
            local fallback = RR_Launcher.readIni "FixedPublicSource" (RR_Launcher.fixedPublicSource)
            if RR_Launcher.isValidSourceRoot fallback then fallback else RR_Launcher.fixedPublicSource
        )
    ),

    fn mainEntryRelative =
    (
        local rel = RR_Launcher.readIni "MainEntryRelative" ""
        if rel != "" then
        (
            rel
        )
        else
        (
            if doesFileExist ((RR_Launcher.installRoot()) + "RootMotionTool\\launch_rm_tool.ms") then
                "RootMotionTool\\launch_rm_tool.ms"
            else
                "maxscript\\ReferenceRig.ms"
        )
    ),

    fn ensureConfigDefaults =
    (
        RR_Launcher.writeIni "FixedPublicSource" (RR_Launcher.fixedPublicSource)
        RR_Launcher.writeIni "InstallRoot" (RR_Launcher.installRoot())
        RR_Launcher.writeIni "MaxUserScripts" (getDir #userScripts)

        local rel = RR_Launcher.readIni "MainEntryRelative" ""
        if rel == "" then
        (
            if doesFileExist ((RR_Launcher.installRoot()) + "RootMotionTool\\launch_rm_tool.ms") then
                rel = "RootMotionTool\\launch_rm_tool.ms"
            else
                rel = "maxscript\\ReferenceRig.ms"
            RR_Launcher.writeIni "MainEntryRelative" rel
        )

        local src = RR_Launcher.readIni "SourceRoot" ""
        if src == "" then
        (
            local resolvedSrc = RR_Launcher.sourceRoot()
            RR_Launcher.writeIni "SourceRoot" resolvedSrc
            src = resolvedSrc
        )

        local autoSyncRaw = RR_Launcher.readIni "AutoSyncOnOpen" ""
        if autoSyncRaw == "" then
        (
            local isDevLike = false
            if RR_Launcher.isValidSourceRoot src do
            (
                isDevLike = (RR_Launcher._normPath src) != (RR_Launcher._normPath RR_Launcher.fixedPublicSource)
            )
            if isDevLike then
                RR_Launcher.writeIni "AutoSyncOnOpen" "true"
            else
                RR_Launcher.writeIni "AutoSyncOnOpen" "false"
        )
        true
    ),

    fn escapeForString value =
    (
        substituteString (value as string) "\"" "\\\""
    ),

    fn _writeOpenMacro =
    (
        local macroPath = (getDir #userMacros) + "\\Animation_Tools_Open.mcr"
        local launcherPath = (RR_Launcher.installRoot()) + "maxscript\\ReferenceRigLauncher.ms"
        local stream = createFile macroPath
        format "macroScript Animation_Tools_Open\n" to:stream
        format "category:\"Animation Tools\"\n" to:stream
        format "toolTip:\"OP Tools\"\n" to:stream
        format "buttonText:\"OP Tools\"\n" to:stream
        format "(\n" to:stream
        format "    global RR_Animation_LauncherFile\n" to:stream
        format "    global RR_Launcher\n" to:stream
        format "    RR_Animation_LauncherFile = @\"%\"\n" (RR_Launcher.escapeForString launcherPath) to:stream
        format "    if doesFileExist RR_Animation_LauncherFile then\n" to:stream
        format "    (\n" to:stream
        format "        fileIn RR_Animation_LauncherFile\n" to:stream
        format "        if RR_Launcher != undefined then\n" to:stream
        format "        (\n" to:stream
        format "            local ok = RR_Launcher.openMainTool()\n" to:stream
        format "            if not ok do messageBox \"Animation Tools 打开失败，请查看弹窗详情。\"\n" to:stream
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
        true
    ),

    fn _writeUpdateMacro =
    (
        local macroPath = (getDir #userMacros) + "\\Animation_Tools_Update.mcr"
        local launcherPath = (RR_Launcher.installRoot()) + "maxscript\\ReferenceRigLauncher.ms"
        local stream = createFile macroPath
        format "macroScript Animation_Tools_Update\n" to:stream
        format "category:\"Animation Tools\"\n" to:stream
        format "toolTip:\"Animation Tools Update\"\n" to:stream
        format "buttonText:\"Animation Tools Update\"\n" to:stream
        format "(\n" to:stream
        format "    global RR_Animation_LauncherFile\n" to:stream
        format "    global RR_Launcher\n" to:stream
        format "    RR_Animation_LauncherFile = @\"%\"\n" (RR_Launcher.escapeForString launcherPath) to:stream
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
        true
    ),

    fn ensurePiToolsMenu isQuiet:true =
    (
        local menuFile = (RR_Launcher.installRoot()) + "maxscript\\PiToolsMenu.ms"
        if not doesFileExist menuFile then
        (
            format "PiTools menu file missing: %\n" menuFile
            if not isQuiet do
                messageBox ("未找到动画工具菜单脚本:\n" + menuFile + "\n\n公盘包可能不完整。请重新安装 Animation Tools，或拖入 install_pi_tools_menu.ms 修复。") title:"Animation Tools"
            return false
        )
        try
        (
            PiTools_Menu = undefined
            fileIn menuFile
            if PiTools_Menu == undefined then
                throw "PiTools_Menu is undefined after fileIn."
            PiTools_Menu.doInstall isQuiet
        )
        catch
        (
            local err = getCurrentException() as string
            format "PiTools menu install failed: %\n" err
            if not isQuiet do
                messageBox ("动画工具菜单注册失败:\n\n" + err + "\n\n可拖入 install_pi_tools_menu.ms 单独修复。") title:"Animation Tools"
            false
        )
    ),

    fn ensureToolbarMacros =
    (
        RR_Launcher._writeOpenMacro()
        RR_Launcher._writeUpdateMacro()
        RR_Launcher.ensurePiToolsMenu isQuiet:true
        true
    ),

    fn ensureDir dirPath =
    (
        if dirPath != undefined and dirPath != "" do makeDir dirPath all:true
    ),

    fn shouldSkipFile fileName =
    (
        matchPattern fileName pattern:"*.plan.md" ignoreCase:true or
        matchPattern fileName pattern:"ReferenceRigInstall.ini" ignoreCase:true or
        matchPattern fileName pattern:"rm_config.json" ignoreCase:true or
        matchPattern fileName pattern:"afm_config.json" ignoreCase:true or
        matchPattern fileName pattern:"afm_user_config.json" ignoreCase:true or
        matchPattern fileName pattern:"config.json" ignoreCase:true
    ),

    fn shouldSkipDir dirName =
    (
        dirName == ".git" or dirName == ".cursor" or dirName == "__pycache__" or dirName == "plans" or dirName == "_RigUpdateBackup" or dirName == "_RigUpdateReports" or dirName == "_RigUpdatePackages"
    ),

    fn _collectRelativeFiles rootDir currentDir =
    (
        local normalizedRoot = trimRight rootDir "\\/"
        local current = currentDir
        if current == undefined or current == "" do current = normalizedRoot
        local rels = #()
        local files = getFiles (current + "\\*")
        for filePath in files do
        (
            local rel = substituteString filePath (normalizedRoot + "\\") ""
            local fileName = filenameFromPath filePath
            if not (RR_Launcher.shouldSkipFile fileName) do append rels rel
        )

        local dirs = getDirectories (current + "\\*")
        for dirPath in dirs do
        (
            local dirName = getFilenameFile (trimRight dirPath "\\/")
            if not (RR_Launcher.shouldSkipDir dirName) do join rels (RR_Launcher._collectRelativeFiles rootDir dirPath)
        )
        rels
    ),

    fn copyFolder sourceDir targetDir =
    (
        if sourceDir == undefined or sourceDir == "" or not doesDirectoryExist sourceDir then
        (
            throw ("Source folder does not exist: " + (sourceDir as string))
        )

        if (RR_Launcher._normPath sourceDir) == (RR_Launcher._normPath targetDir) then
        (
            return true
        )

        RR_Launcher.ensureDir targetDir

        local files = getFiles (sourceDir + "\\*")
        for filePath in files do
        (
            local fileName = filenameFromPath filePath
            if not (RR_Launcher.shouldSkipFile fileName) do
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
            if not (RR_Launcher.shouldSkipDir dirName) do
            (
                RR_Launcher.copyFolder dirPath (targetDir + "\\" + dirName)
            )
        )
        true
    ),

    fn syncFolder sourceDir targetDir =
    (
        RR_Launcher.copyFolder sourceDir targetDir
        local sourceRels = RR_Launcher._collectRelativeFiles sourceDir ""
        local targetRels = RR_Launcher._collectRelativeFiles targetDir ""
        for relPath in targetRels do
        (
            if (findItem sourceRels relPath) == 0 do
            (
                if RR_Launcher.isProtectedRelativePath relPath then continue
                local targetFile = targetDir + "\\" + relPath
                if doesFileExist targetFile do deleteFile targetFile
            )
        )
        true
    ),

    fn openMainTool =
    (
        RR_Launcher.autoSyncLocalInstall silent:true
        RR_Launcher.ensurePiToolsMenu isQuiet:true

        local dst = RR_Launcher.installRoot()
        local rel = RR_Launcher.mainEntryRelative()
        local toolFile = dst + rel
        if doesFileExist toolFile then
        (
            try
            (
                fileIn toolFile
                true
            )
            catch
            (
                messageBox ("打开主工具失败:\n" + toolFile + "\n\n" + (getCurrentException() as string)) title:"Animation Tools Launcher"
                false
            )
        )
        else
        (
            messageBox ("Animation main tool was not found:\n" + toolFile + "\n\n请重新拖入 install_animation_tools.ms 安装。") title:"Animation Tools Launcher"
            false
        )
    ),

    fn updateFromSource =
    (
        local src = RR_Launcher.fixedPublicSource
        if not (RR_Launcher.isValidSourceRoot src) then
        (
            messageBox ("工具源目录不可用或不完整:\n" + src + "\n\n目录内必须包含 install_animation_tools.ms、maxscript\\ReferenceRigLauncher.ms、maxscript\\PiToolsMenu.ms 和 RootMotionTool\\op_tools_hub.py。") title:"Animation Tools Launcher"
            return false
        )

        local dst = RR_Launcher.installRoot()
        RR_Launcher.syncFolder src dst
        RR_Launcher.ensureConfigDefaults()
        RR_Launcher.ensureToolbarMacros()
        local menuOk = RR_Launcher.ensurePiToolsMenu isQuiet:false
        local updateTs = (dotNetClass "System.DateTime").Now.ToString "yyyy-MM-dd HH:mm:ss"
        RR_Launcher.writeIni "LastUpdated" updateTs
        local message = "Animation Tools 已更新到本地。\n更新来源:\n" + src + "\n\n请重新打开工具界面。"
        if not menuOk then
            message += "\n\n注意：动画工具菜单未成功注册。请拖入 install_pi_tools_menu.ms 修复，或重启 3ds Max 后再试。"
        messageBox message title:"Animation Tools Launcher"
        true
    ),

    fn openInstallFolder =
    (
        shellLaunch (RR_Launcher.installRoot()) ""
    ),

    fn openSourceFolder =
    (
        local src = RR_Launcher.sourceRoot()
        if RR_Launcher.isValidSourceRoot src then shellLaunch src "" else messageBox ("工具源目录不可用:\n" + src)
    )
)

RR_Launcher = RR_LauncherLib()

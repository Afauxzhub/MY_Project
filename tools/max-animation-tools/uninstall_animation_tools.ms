/*
OP Tools — 完全卸载（本机）

用途：删除本机已安装的 Animation / OP Tools 相关文件，便于同事在「装错版本 / 重启后又变旧」时彻底清干净后再重装。

用法：在 3ds Max 里将本脚本拖入视口执行（或 File > Run Script）。

会删除：
  - userScripts\AnimationTools\ 整个目录（含 ReferenceRigInstall.ini、Python 工具等）
  - userMacros\Animation_Tools_Open.mcr、Animation_Tools_Update.mcr（自定义界面里的宏动作来源）
  - userStartupScripts\OP_RigUpdateAuto.ms（若存在）
  - userStartupScripts\AnimationToolsMenuStartup.ms（若存在）
  - userMacros\PiTools_*.mcr（动画工具菜单宏）
  - 尝试注销 OP_RigUpdateAuto 相关回调与计时器（若曾注册）

说明：工具栏上已拖出的按钮可能仍显示为「失效项」，需在「自定义用户界面」里删掉旧按钮，或重启 Max 后重新拖入新宏。
*/

global OP_Uninstall_Run

struct AnimationToolsUninstallLib
(
    fn installDir =
    (
        (getDir #userScripts) + "\\AnimationTools"
    ),

    fn deleteFileIfExists fp =
    (
        if fp != undefined and fp != "" and doesFileExist fp do
        (
            try (deleteFile fp) catch ()
        )
        true
    ),

    fn deleteDirRecursive dirPath =
    (
        if dirPath == undefined or dirPath == "" then return false
        if not doesDirectoryExist dirPath then return true
        try
        (
            (dotNetClass "System.IO.Directory").Delete dirPath true
            true
        )
        catch
        (
            local msg = "递归删除目录失败（可能被占用或无权限）：\n" + dirPath + "\n\n" + (getCurrentException() as string)
            messageBox msg title:"OP Tools 卸载"
            false
        )
    ),

    fn removeAutoRigCallbacks =
    (
        try (callbacks.removeScripts id:#OP_RigUpdateAuto) catch ()
        try
        (
            global OP_RigUpdateAutoTimer
            if OP_RigUpdateAutoTimer != undefined do OP_RigUpdateAutoTimer.Stop()
        )
        catch ()
        try
        (
            dotNet.removeAllEventHandlers OP_RigUpdateAutoTimer
        )
        catch ()
        try (OP_RigUpdateAutoTimer = undefined) catch ()
        true
    ),

    fn run =
    (
        local ok = queryBox "将删除本机 OP / Animation Tools 安装目录与相关宏文件。\n\n确定继续？" title:"OP Tools 卸载" beep:false
        if not ok then return false

        removeAutoRigCallbacks()

        local macroOpen = (getDir #userMacros) + "\\Animation_Tools_Open.mcr"
        local macroUpdate = (getDir #userMacros) + "\\Animation_Tools_Update.mcr"
        deleteFileIfExists macroOpen
        deleteFileIfExists macroUpdate

        for m in #(
            "PiTools_OpenFile.mcr",
            "PiTools_PublishAnim.mcr",
            "PiTools_WeaponTool.mcr",
            "PiTools_BindingUpdate.mcr",
            "PiTools_AnimLibrary.mcr",
            "PiTools_ShotAssist.mcr",
            "PiTools_AnimScale.mcr",
            "PiTools_Upload.mcr",
            "PiTools_Update.mcr"
        ) do
        (
            deleteFileIfExists ((getDir #userMacros) + "\\" + m)
        )

        local startupAuto = (getDir #userStartupScripts) + "\\OP_RigUpdateAuto.ms"
        deleteFileIfExists startupAuto
        local startupMenu = (getDir #userStartupScripts) + "\\AnimationToolsMenuStartup.ms"
        deleteFileIfExists startupMenu

        local inst = installDir()
        local delOk = deleteDirRecursive inst

        try (global RR_Launcher = undefined) catch ()
        try (global RR_Installer = undefined) catch ()

        if delOk then
        (
            messageBox "卸载完成。\n\n已删除：\n- userScripts\\AnimationTools\\\n- 两个 Animation_Tools_*.mcr 宏文件\n- OP_RigUpdateAuto.ms（若存在）\n\n请重启 3ds Max，并在「自定义用户界面」中移除工具栏上的旧按钮（如有），再拖入公盘 install_animation_tools.ms 重装。" title:"OP Tools 卸载"
        )
        else
        (
            messageBox "卸载未完全成功，请查看上一个错误提示，或手动删除目录：\n" + inst title:"OP Tools 卸载"
        )
        true
    )
)

OP_Uninstall_Run = AnimationToolsUninstallLib()
OP_Uninstall_Run.run()

-- 动画文件管理器启动脚本
(
    local sourceFile = getSourceFileName()
    if sourceFile == undefined then
    (
        messageBox "无法确定 launch_anim_file_manager.ms 所在目录。" title:"动画文件管理器"
    )
    else
    (
        local toolDir = trimRight (getFilenamePath sourceFile) "\\/"
        local pyCmd =
            "import sys\n" + \
            "tool_dir = r'" + toolDir + "'\n" + \
            "while tool_dir in sys.path:\n" + \
            "    sys.path.remove(tool_dir)\n" + \
            "sys.path.insert(0, tool_dir)\n" + \
            "old = sys.modules.get('anim_fm_tool')\n" + \
            "if old is not None:\n" + \
            "    try:\n" + \
            "        old.close()\n" + \
            "    except Exception:\n" + \
            "        pass\n" + \
            "purge = []\n" + \
            "for name in list(sys.modules.keys()):\n" + \
            "    if name == 'anim_fm_tool' or name == 'ui' or name == 'core' or name.startswith('ui.') or name.startswith('core.'):\n" + \
            "        purge.append(name)\n" + \
            "for name in purge:\n" + \
            "    try:\n" + \
            "        del sys.modules[name]\n" + \
            "    except Exception:\n" + \
            "        pass\n" + \
            "import anim_fm_tool\n" + \
            "anim_fm_tool.show()\n"
        python.Execute pyCmd
    )
)

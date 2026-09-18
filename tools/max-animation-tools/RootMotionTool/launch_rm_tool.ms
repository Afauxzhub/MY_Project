-- Root Motion 导出工具 启动 / 刷新脚本
-- 用法：
--   1. 直接把本文件拖进 3ds Max 启动工具
--   2. 后续代码更新后，关闭当前工具窗口，再拖一次本文件即可刷新
--   3. 脚本会自动尝试关闭旧窗口并清理模块缓存

(
	local sourceFile = getSourceFileName()
	if sourceFile == undefined then
	(
		messageBox "无法确定 launch_rm_tool.ms 所在目录，请从文件直接拖入 3ds Max 执行。" title:"Root Motion Tool"
	)
	else
	(
		local toolDir = trimRight (getFilenamePath sourceFile) "\\/"

		local pyCmd =
			"import sys\n" + \
			"tool_dir = r'" + toolDir + "'\n" + \
			"if tool_dir not in sys.path:\n" + \
			"    sys.path.insert(0, tool_dir)\n" + \
			"old_rm_tool = sys.modules.get('rm_tool')\n" + \
			"if old_rm_tool is not None:\n" + \
			"    try:\n" + \
			"        old_rm_tool.close()\n" + \
			"    except Exception:\n" + \
			"        pass\n" + \
			"reload_names = []\n" + \
			"for name in list(sys.modules.keys()):\n" + \
			"    if name == 'rm_tool' or name in ('ui', 'core', 'pipeline', 'anim_migration') or name.startswith('ui.') or name.startswith('core.') or name.startswith('pipeline.') or name.startswith('anim_migration.'):\n" + \
			"        reload_names.append(name)\n" + \
			"for name in reload_names:\n" + \
			"    try:\n" + \
			"        del sys.modules[name]\n" + \
			"    except Exception:\n" + \
			"        pass\n" + \
            "import rm_tool\n" + \
            "rm_tool.show_publish_only()\n"

		python.Execute pyCmd
	)
)

# Root Motion / FBX Publisher

## 正式入口

- Python：`rm_tool.show_publish_only()`
- 菜单中枢：`op_tools_hub.open_publish_tool()`

正式入口使用 BaseLayer COM 恢复链。`rm_tool.show_publish_legacy()` 及 `op_tools_hub.open_publish_legacy_tool()` 只用于故障回退，不注册到动画师工具栏和菜单。

## 导出硬门禁

- 缩放只允许排除 Root/Bip；其他绑定或动画节点异常必须报告，不得静默跳过。
- 重复的导出层级路径视为绑定层级已被修改。
- 出现该问题时必须提示：`绑定层级被修改，无法导出，请检查文件后重新尝试。`
- 不自动改名或兼容有歧义的绑定层级。

## Unity 输出

个人版默认把 FBX 复制到 Unity `Assets/Art/Animations` 下，并与仓库中的 `com.afauxzhub.animation-pipeline` 配合，将动画片段输出到 `Assets/Generated/AnimationClips`。

Max 与 Unity 通过 `%LOCALAPPDATA%/Afauxzhub/AnimationPipeline/unity_bridge_request.json` 发送 Project 窗口定位请求。

## 配置与兼容

真实设置保存在 `config/rm_config.json`，不提交 Git。以 `config/rm_config.example.json` 为起点，在工具设置窗口中选择个人工程路径。

`op_tools_hub.py`、部分 `op_` 和 `PiTools` 名称是现有 MaxScript/Python 导入链的兼容标识；修改这些名称前必须同时检查安装器、菜单宏、启动脚本和静态验证。

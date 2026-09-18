# Max Animation Tools

这是从现有动画生产工具中整理出的个人可复用版本，目标环境为 **3ds Max 2020 / Python 2.7 / PySide2 / MaxScript**。

## 安装

1. 下载或克隆本仓库。
2. 把 `install_animation_tools.ms` 拖入 3ds Max 2020 视口。
3. 安装器会复制工具到当前用户的 `userScripts/AnimationTools`，并注册“动画工具”菜单。
4. 首次使用发布功能时，在设置中填写个人 Unity 工程的 `Assets` 路径。

安装器只从当前下载目录更新，不再连接任何固定服务器。用户配置不会随更新覆盖。

## 模块

- `RootMotionTool`：Root Motion、FBX 发布、武器状态、绑定迁移及 Max→Unity 定位桥。
- `AnimFileManager`：本地/共享动画文件浏览和版本记录。共享根目录通过环境变量 `ANIMATION_TOOLS_PUBLIC_ROOT` 配置；不使用时可留空。
- `AnimationLibrary`：动作和 Pose 资源库；个人设置保存在用户 AppData。
- `AnimScaleTool`：动画缩放工具。
- `maxscript`：绑定、约束、迁移及菜单脚本。
- `validation`：无需打开 Max 的静态验证，以及需要在 Max 中执行的验收清单。

## 配置

仓库只保存示例配置：

- `RootMotionTool/config/rm_config.example.json`
- `AnimFileManager/config/afm_user_config.example.json`

真实配置、日志、报告、缓存和临时导出不进入 Git。工具首次保存设置时会在安装目录创建实际配置。

## Unity 联动

配套 Unity Package 位于仓库的：

`packages/com.afauxzhub.animation-pipeline`

Max 与 Unity 使用 `%LOCALAPPDATA%/Afauxzhub/AnimationPipeline/unity_bridge_request.json` 传递 Project 窗口定位请求。

## 迁移边界

- 已移除固定内网地址、本机工程绝对路径和组织专属配置。
- 默认关闭共享盘自动备份；需要时由使用者明确配置。
- 保留部分 `op_`、`PiTools` 文件名和宏名作为内部兼容标识，避免破坏已有导入与菜单调用；这些名称不再对应外部工程或服务。
- 不包含 `.max`、FBX、贴图、预制体或其他项目资产。

## 验证边界

仓库静态检查只能证明脚本可解析、敏感路径已移除和配套文件齐全。正式使用前仍需在 3ds Max 2020 与目标 Unity 版本中完成一次安装、FBX 发布、`.anim` 导出和定位桥验收。

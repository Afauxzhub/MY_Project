# Afauxzhub Animation Pipeline

这是一个不依赖项目业务框架的 Unity Editor Package，用于承接 3ds Max 动画发布结果。

## 功能

- 对指定目录下的 FBX 应用通用动画导入设置。
- 从选中的 FBX 中提取一个或多个 `AnimationClip` 为独立 `.anim`。
- 可选自动导出以及曲线数值归一、冗余关键帧简化。
- 接收 Max 工具写入的定位请求，刷新 Unity 并在 Project 窗口中选中导出结果。
- 读取 Max 武器状态导出的 `*_WeaponStateMapping.json`，并提供导出后扩展事件供个人项目接入运行时配置。
- 所有路径和导入选项都保存在当前 Unity 工程的 `ProjectSettings` 中。

## 安装

把本目录复制到 Unity 工程的 `Packages/com.afauxzhub.animation-pipeline`，或者在 Package Manager 中选择 **Add package from disk** 并选中 `package.json`。

安装后打开：

`Tools > Animation Pipeline > Settings`

默认约定：

- FBX 来源目录：`Assets/Art/Animations`
- `.anim` 输出目录：`Assets/Generated/AnimationClips`
- 默认关闭自动导出，避免刚安装就改动现有工程资源。

`ProjectSettings/AfauxzhubAnimationPipelineSettings.asset` 可作为项目共享配置提交（仅使用相对资产路径）。`AnimationPipelineSettings` 提供只读设置供项目校验工具使用。FBX 动画压缩可配置，包默认保持 Optimal；新骨架的原始数据验收建议使用 Off，并暂时关闭导出后曲线优化。Root/Motion 节点须依据真实导出骨架配置。

当前 `.anim` 按 FBX 文件名前两段分组，例如 `Role_Player_LocomotionRunForward.fbx` 输出到 `Assets/Generated/AnimationClips/Role_Player/Role_Player_LocomotionRunForward.anim`。重新导出会更新已有 Clip、保留其 GUID，同时覆盖 Clip 内的手工修改；项目动作元数据应独立保存。

可选启用“个人短命名镜像 FBX 子目录”（包默认关闭，本项目开启）：`Player_Unarmed_Idle` / `Wolf_Run` 等 `角色_[动作集_]动作` 命名将按来源根的相对子目录输出。例如 `Assets/Art/Animations/Player/Locomotion/Player_Sword_Idle.fbx` → `Assets/Generated/AnimationClips/Player/Locomotion/Player_Sword_Idle.anim`。动作集不等于文件夹或状态机。已有分类和过场前缀保留旧的分组行为。

## 手动导出

1. 在 Project 窗口选中一个或多个 FBX。
2. 执行 `Assets > Animation Pipeline > Export Selected FBX Clips`。
3. 工具会按设置配置 FBX Importer、重新导入，并生成独立 `.anim`。

## 与 Max 联动

Max 端与 Unity 端通过以下本机临时请求文件通信：

`%LOCALAPPDATA%/Afauxzhub/AnimationPipeline/unity_bridge_request.json`

请求只允许定位当前 Unity 工程 `Assets/` 下的路径，不传输动画或工程数据。

## 边界

本包不包含战斗数据序列化、武器运行时配置、角色资源规范或公司工程目录约定。此类逻辑应由个人项目通过自己的导入后处理器扩展。

项目可订阅 `AnimationPipelineHooks.ClipExported`，在不修改包源码的情况下生成自己的战斗数据或武器配置。

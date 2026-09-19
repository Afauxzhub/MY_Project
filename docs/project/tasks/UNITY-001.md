# UNITY-001：建立 Unity 工程并验证现有包

| 字段 | 内容 |
| --- | --- |
| 状态 | Done |
| 类型 | 工程基础 |
| 里程碑 | M0：Unity 开发基线 |
| 负责人 | 当前主任务 Agent |
| 创建日期 | 2026-09-19 |
| 最近更新 | 2026-09-19 |

## 目标

在仓库根目录建立 Unity 6000.3.24f1 工程，使现有三个本地 Unity 包能够被工程引用、完成程序集编译，并通过最小编辑器运行检查。工程完成后，任何新任务都能从仓库恢复相同 Unity 版本和包依赖。

## 范围

本次包含：

- 创建最小 Unity 工程结构和 `ProjectSettings/ProjectVersion.txt`。
- 使用 Unity 6000.3.24f1。
- 通过工程 `Packages/manifest.json` 引用仓库中的三个本地包。
- 核对包声明的最低 Unity 版本与 Unity 6.3 的实际导入、API 和程序集兼容性。
- 打开工程、完成首次导入、检查 Console 和程序集编译结果。
- 建立一个最小可保存、可重新打开的工程场景或等价运行基线。
- 记录所有真实发现的兼容性问题，并把独立修复拆成后续任务。

本次不包含：

- 玩家战斗灰盒实现。
- 正式角色、动画、场景、美术或游戏内容。
- 移动手感、技能效果或 Max 发布链的完整验收。
- 为消除警告而无依据升级包架构或改变战斗规则。

## 权威依据

- `AGENTS.md`
- `docs/project/overview.md`
- `docs/architecture/company-reference-reuse-review.md`
- `docs/tools/animation-tools-porting.md`
- 各包的 `README.md` 和 `package.json`

涉及 Timeline 战斗边界时，必须同时遵守：

- `docs/design/combat/player-combat-spec.md`
- `docs/design/combat/integration-contracts.md`

## 依赖

- [x] Unity 6000.3.24f1 已安装并由本机系统记录确认。
- [x] 三个 Unity 包源码已存在于 `packages/`。
- [x] 开始任务时确认 Git 工作区状态并记录实际 Unity Editor 路径。

## 验收条件

- [x] `ProjectSettings/ProjectVersion.txt` 记录 Unity 6000.3.24f1。
- [x] 工程 manifest 使用可移植的相对本地包引用，不包含本机绝对路径。
- [x] 三个本地包均被 Unity Package Manager 识别。
- [x] 编辑器完成导入和程序集编译，Console 无编译错误。
- [x] 最小场景可以保存、关闭并重新打开。
- [x] 重新打开工程后依赖仍可解析，未提交 Library、Logs、Temp 或用户配置。
- [x] 实际验证结果、警告和兼容性问题记录在本任务卡。
- [x] `overview.md` 与 `tasks.md` 状态已同步。

## 实施与验证结论

- Unity Editor 已从仓库内的临时安装位置迁移到 `E:/GameDev/UnityEditors/6000.3.24f1`。编辑器安装不属于仓库内容。
- Unity 工程根目录为 `Client/`；本地包使用 `file:../../packages/...` 相对引用。
- 三个包在 Unity 6000.3.24f1 中均能完成注册和程序集编译。Unity 为包源码生成的 `.meta` 文件需要提交，以保持资产 GUID 稳定。
- `ProjectBaselineValidation` 提供可重复的菜单和批处理验证入口。
- 日志出现 Licensing Client 签名验证和访问令牌更新消息，但随后成功解析 Unity Personal 授权，未阻止工程导入、编译或退出。当前作为非阻塞环境日志记录。
- 本任务只证明包导入和编译兼容；Timeline 资产编译、移动手感、动画导入操作和实际玩法仍需后续运行验收。

## 验证记录

| 日期 | 环境 | 检查 | 结果 | 证据/备注 |
| --- | --- | --- | --- | --- |
| 2026-09-19 | Windows | 系统卸载信息检查 | 已确认 | 安装记录为 Unity 6000.3.24f1；安装路径尚待启动任务时核验 |
| 2026-09-19 | Windows | Editor 可执行文件检查 | 已确认 | 初始位置为 `Client/6000.3.24f1/Editor/Unity.exe`；将迁移到仓库外的本机工具目录 |
| 2026-09-19 | Unity 6000.3.24f1 | 工程创建与版本写入 | 通过 | `Client/ProjectSettings/ProjectVersion.txt` 已写入完整版本和 revision |
| 2026-09-19 | Unity Package Manager | 三个本地包解析 | 通过 | `packages-lock.json` 记录三个相对路径包和 `com.unity.timeline` 1.7.7 |
| 2026-09-19 | Unity Batchmode | 程序集编译 | 通过 | Tundra build success；无 C# 编译错误 |
| 2026-09-19 | Unity Batchmode | 场景创建、保存与重新打开 | 通过 | 两次运行均输出 `[MY_Project Baseline] PASS`，退出码为 0 |

## 交接

- 已完成：Unity 工程、相对本地包依赖、Bootstrap 场景和可重复基线检查已经建立。
- 已验证：Unity 版本、包解析、程序集编译、场景保存和重新打开。
- 尚未验证：三个包各自的功能性运行流程、实际角色移动、Timeline 资产工作流、动画导入和 Max 联动。
- 下一步：按 M1 灰盒依赖拆分并开始首项实现任务，建议从 `MOVE-001` 开始。
- 相关提交：待完成后填写。

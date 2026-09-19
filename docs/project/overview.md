# MY_Project 项目总览

| 字段 | 当前状态 |
| --- | --- |
| 项目阶段 | 最小第三人称移动闭环已实现；等待 Play Mode 人工验收 |
| 当前里程碑 | M1：玩家战斗最小灰盒（MOVE-001 等待运行验收） |
| Unity 基线 | Unity 6000.3.24f1（Unity 6.3 LTS） |
| 任务索引 | [`tasks.md`](tasks.md) |
| Agent 工作方式 | [`agent-workflow.md`](agent-workflow.md) |
| 最近更新 | 2026-09-19 |

## 项目目标

制作第三人称动作游戏，并先通过最小灰盒验证玩家战斗循环。当前阶段优先建立稳定工程、接入已有通用包、验证基础运行链，再进入完整战斗灰盒。

玩家战斗设计以 `docs/design/combat/player-combat-spec.md` 为唯一权威来源。程序、动画、Boss 和 AI 需求通过规则 ID 引用该规范，不在本文件复制完整设计。

## 已具备的基础

- 玩家战斗规范、集成契约、维护规则和项目级 `combat-design` Skill。
- `com.afauxzhub.character-locomotion`：相机相对移动意图与朝向数学层，已完成源码静态检查。
- `com.afauxzhub.timeline-abilities`：Timeline 技能编排和运行指令骨架，已完成源码静态检查。
- `com.afauxzhub.animation-pipeline`：Unity 动画导入、Clip 导出、曲线处理与 Max 定位桥接。
- `tools/max-animation-tools`：个人 3ds Max 动画工具源码、安装脚本和静态验证脚本。

以上源码存在不等于已经完成 Unity 或 3ds Max 运行验收。

## 当前边界

- Unity 工程位于 `Client/`，版本由 `Client/ProjectSettings/ProjectVersion.txt` 固定为 6000.3.24f1。
- 三个本地包已经完成 Unity Package Manager 导入和程序集编译；其具体玩法、编辑器工作流与运行时行为仍需分别验收。
- `Bootstrap.unity` 已完成创建、保存和批处理重开验证，目前只提供工程运行基线。
- `LocomotionGreybox.unity` 已通过可重复批处理创建、保存、重开和结构验证；真人键盘、碰撞与移动手感尚待 Play Mode 验收。
- 玩家战斗目前处于进入灰盒验证前；`PROTO-01` 至 `PROTO-07` 尚未形成可运行闭环。
- 完整技能、BD、生产系统、正式 Boss 和正式内容生产不属于当前里程碑。

## 里程碑

### M0：Unity 开发基线（已完成）

目标：创建 Unity 6000.3.24f1 工程，接入已有本地包，完成无错误编译和最小运行检查，并记录真实兼容性问题。

完成记录见 `UNITY-001` 任务卡。

### M1：玩家战斗最小灰盒（当前）

目标：按 `PROTO-01` 至 `PROTO-07` 建立可测试的玩家与敌人闭环，优先验证资源循环和应对选择，不追求正式美术内容。

进入条件：M0 完成，Unity 工程和基础包能够稳定编译运行。

### 后续范围

移动手感、技能联动、动画生产链、Boss、BD 与生产系统在前置灰盒给出证据后逐步拆分。未进入当前里程碑的内容保留在任务索引中，不提前细化成大量任务。

## 下一项工作

按 `MOVE-001` 任务卡的四步流程完成 Play Mode 人工验收；通过后关闭该任务，再按灰盒依赖安排 Timeline 技能验证和战斗循环实现。

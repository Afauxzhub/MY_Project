# MOVE-001：接通最小第三人称移动闭环

| 字段 | 内容 |
| --- | --- |
| 状态 | In Progress |
| 类型 | 功能开发 |
| 里程碑 | M1：玩家战斗最小灰盒 |
| 负责人 | MOVE-001 Codex 任务 |
| 创建日期 | 2026-09-19 |
| 最近更新 | 2026-09-19 |

## 目标

在 `Client` Unity 工程中建立可运行的最小第三人称移动闭环：玩家使用胶囊体占位角色，通过项目输入适配器提交二维移动输入，以当前相机水平朝向为参考生成移动方向，由 `com.afauxzhub.character-locomotion` 求解朝向意图，最后只由一个碰撞 Motor 写入角色位置与旋转。

完成后，开发者能够在 Unity Play Mode 中验证静止、直线移动、连续转向、停止和碰撞阻挡，并能观察关键移动意图输出。

## 范围

本次包含：

- 在项目代码中建立输入、相机参考、Locomotion Brain、Motor 和占位表现之间的清晰适配边界。
- 复用 `CameraRelativeMovement`、`HeadingSolver`、`LocomotionIntent` 和 `LocomotionProfile`，不在项目代码复制其数学逻辑。
- 使用胶囊体、简单地面和基础碰撞建立灰盒场景。
- 支持至少键盘二维输入；如果采用 Unity Input System，保持输入实现可替换并记录包依赖。
- 建立简单的第三人称观察相机或固定跟随相机，只提供本任务需要的参考轴和可观察性。
- 提供可重复创建或验证灰盒场景的 Editor 工具，避免依赖手工场景步骤。
- 显示或记录速度、目标方向、求解方向、转向意图等必要调试信息。

本次不包含：

- 最终自由镜头、锁定镜头或自动跟随手感。
- 正式动画、起步动作、小转向动作、急转、冲刺或 Root Motion。
- 战斗输入、攻击、闪避、资源、锁敌或战斗移动覆盖。
- 网络、导航、公司工程类型或第三方动画框架。
- 把灰盒数值固化为最终参数。

## 权威依据

- `AGENTS.md`
- `docs/architecture/company-reference-reuse-review.md`
- `docs/architecture/locomotion-framework.md`
- `packages/com.afauxzhub.character-locomotion/README.md`
- `packages/com.afauxzhub.character-locomotion/Runtime/`
- `docs/project/tasks/UNITY-001.md`

## 架构约束

- 每帧只有 Motor 可以写角色最终位置和旋转。
- 输入层只提交输入意图；相机层只提供参考轴；Solver 不读取输入设备、不播放动画、不控制相机。
- Root Motion、正式动画和战斗策略保持在本次任务之外。
- 项目适配器放在 `Client/Assets`，通用数学继续留在包内。
- 所有灰盒速度、转弯和镜头值可调，并明确属于灰盒配置。

## 依赖

- [x] `UNITY-001` 完成。
- [x] Unity 6000.3.24f1 工程可重新打开并编译。
- [x] `com.afauxzhub.character-locomotion` 已由 Package Manager 注册。

## 验收条件

- [ ] Bootstrap 或独立灰盒场景中存在胶囊玩家、地面、碰撞障碍和可观察相机。
- [ ] 键盘输入可驱动角色按相机水平轴移动；无输入时角色停止。
- [ ] 角色连续转向由 `HeadingSolver` 输出驱动，不瞬间复制目标方向。
- [ ] 位置和旋转只有 Motor 写入，碰撞不会被 Transform 直写绕过。
- [ ] 关键 `LocomotionIntent` 值可通过 Inspector、Gizmo 或明确日志观察。
- [ ] 场景或必需资产可通过项目 Editor 工具重复创建/验证。
- [ ] Unity 程序集编译无错误，现有工程基线检查继续通过。
- [ ] 给出短小的 Play Mode 人工验收步骤，并记录实际执行结果或明确等待用户验收。
- [ ] 更新任务索引、任务卡和项目总览，区分静态验证与实际移动手感验证。

## 验证记录

| 日期 | 环境 | 检查 | 结果 | 证据/备注 |
| --- | --- | --- | --- | --- |

## 已知问题与未验证边界

- 当前没有正式角色模型或动画，视觉表现使用胶囊体。
- 键鼠与手柄的最终输入方案、自由镜头和动作混合不在本任务中封口。
- 移动速度、转弯半径和镜头距离均为灰盒值。

## 交接

- 已完成：任务范围、架构边界和验收条件已建立。
- 已验证：Unity 基线和移动数学包可在 Unity 6000.3.24f1 中编译。
- 尚未验证：项目移动适配器、灰盒场景和 Play Mode 手感。
- 下一步：新 Codex 任务读取本卡与权威架构文档后实现并验证。
- 相关提交：待完成后填写。

# MOVE-001：接通最小第三人称移动闭环

| 字段 | 内容 |
| --- | --- |
| 状态 | Done |
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

- [x] Bootstrap 或独立灰盒场景中存在胶囊玩家、地面、碰撞障碍和可观察相机。
- [x] 键盘输入可驱动角色按相机水平轴移动；无输入时角色停止。
- [x] 角色连续转向由 `HeadingSolver` 输出驱动，不瞬间复制目标方向。
- [x] 位置和旋转只有 Motor 写入，实际碰撞阻挡已通过 Play Mode 验收。
- [x] 关键 `LocomotionIntent` 值可通过 Inspector 和 Gizmo 观察。
- [x] 场景或必需资产可通过项目 Editor 工具重复创建/验证。
- [x] Unity 程序集编译无错误，现有工程基线检查继续通过。
- [x] 给出短小的 Play Mode 人工验收步骤，并记录实际执行结果。
- [x] 更新任务索引、任务卡和项目总览，区分静态验证与实际移动手感验证。

## 实施结果

- `MovementInputSource` 隔离输入设备，当前 `KeyboardMovementInput` 提供 `WASD` 和方向键输入。
- `FixedFollowCameraReference` 只提供相机参考轴并以固定偏置跟随玩家；自由/锁定镜头不在本任务中。
- `ThirdPersonLocomotionBrain` 调用包内 `CameraRelativeMovement`、`HeadingSolver`、`LocomotionIntent` 和 `LocomotionProfile`，不复制数学实现。
- `CharacterControllerMotor` 是玩家根节点运行时位置和旋转的唯一写入者，并通过 `CharacterController.Move` 处理碰撞位移。
- `LocomotionGreyboxValidation` 可确定性重建配置资产和独立灰盒场景，保存后重新打开并验证接线、碰撞体与 Build Settings。
- `Player` Inspector 暴露输入、目标方向、求解方向、速度、朝向误差、偏航速度、转向混合和起步方向；Scene 视图用青色/黄色 Gizmo 区分目标与求解方向。

## 验证记录

| 日期 | 环境 | 检查 | 结果 | 证据/备注 |
| --- | --- | --- | --- | --- |
| 2026-09-19 | Unity 6000.3.24f1 Batchmode | 程序集编译、创建场景、保存后重开与结构验证 | 通过 | 退出码 0；日志输出 `[MY_Project Locomotion] PASS` |
| 2026-09-19 | Unity 6000.3.24f1 Batchmode | 第二次执行相同场景工具 | 通过 | 退出码 0；证明资产和场景可重复重建、重开与验证 |
| 2026-09-19 | Unity 6000.3.24f1 Batchmode | 既有 `ProjectBaselineValidation` | 通过 | 退出码 0；日志输出 `[MY_Project Baseline] PASS` |
| 2026-09-19 | PowerShell / Git | 玩家根节点写入所有权与包 API 使用扫描、`git diff --check` | 通过 | 运行时代码中只有 Motor 写玩家旋转并调用 `CharacterController.Move`；Brain 直接使用移动包四个稳定 API；无空白错误 |
| 2026-09-19 | Unity 6000.3.24f1 Play Mode | 键盘移动、停止与转向、前墙和侧墙碰撞阻挡 | 通过 | 用户完成现场验收并确认“移动和阻挡没有问题” |

## Play Mode 人工验收

1. 在 Unity 运行 `Tools > MY Project > Create or Validate Locomotion Greybox`，打开生成的 `LocomotionGreybox` 场景并进入 Play Mode。
2. 选中 `Player`，依次短按和长按 `WASD`（或方向键）；确认方向以相机水平轴为基准、松键立即停止，Inspector 中目标方向、求解方向、偏航速度与转向意图随操作变化。
3. 从静止状态按 `A` 或 `D`，确认黄色求解方向逐步追向青色目标方向而非瞬间跳转；连续切换方向时角色保持平滑转向。
4. 重新开始场景后持续按 `W` 撞前方墙，再持续按 `D` 撞侧墙；确认胶囊被阻挡且没有穿墙或被 Transform 直写绕过。

## 已知问题与未验证边界

- 当前没有正式角色模型或动画，视觉表现使用胶囊体。
- 键鼠与手柄的最终输入方案、自由镜头和动作混合不在本任务中封口。
- 移动速度、转弯半径和镜头距离均为灰盒值。
- 自动验证覆盖编译、场景重建/重开、接线、所有权和碰撞体存在性；真实键盘移动和碰撞行为已在 Play Mode 验收。最终多设备输入和正式手感调优仍属于后续范围。

## 交接

- 已完成：项目输入/相机/Brain/Motor 适配器、灰盒配置、可重复场景生成验证和调试可观察性。
- 已验证：Unity 编译、灰盒场景创建/重开、接线和碰撞体结构、唯一 Motor 写入边界、既有工程基线，以及真人 Play Mode 键盘移动、停止、转向和碰撞阻挡。
- 尚未验证：本任务范围内无；手柄、自由/锁定镜头、正式动画和最终手感属于后续任务。
- 下一步：按 M1 依赖安排 Timeline 技能验证或首个战斗灰盒任务。
- 相关提交：MOVE-001 实现提交（见 Git 历史）。

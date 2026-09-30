# Animator-first 角色动画与战斗动作架构

| 字段 | 内容 |
| --- | --- |
| 决策日期 | 2026-09-30 |
| Unity 基线 | 6000.3.24f1 |
| 状态 | 架构方向已确认，等待原型与运行时验证 |
| 优先级 | 动画效果 > 编辑可见性 > 玩法可控性 > 实现成本 |

## 1. 决策

角色动画采用以下职责分配：

```text
Input / AI
  -> Combat Rule HSM（权限、优先级、资源、打断）
  -> ActionDefinition（动作与表现/玩法轨道）
      -> Animator Controller（姿势、状态图、过渡和混合）
      -> Action Window Evaluator（命中、反击、取消和无敌窗口）
      -> Presentation Tracks（VFX、SFX、镜头、IK和表情）
  -> Character Motor（唯一位置与旋转写入者）
```

- Animator Controller 是角色动画状态、过渡和混合的主要可视化入口。
- Combat Rule HSM 只决定动作是否合法以及何时被更高优先级状态打断，不复制完整动画图。
- `ActionDefinition` 是单个攻击、技能、闪避、受击或特殊动作的编辑资产。
- Timeline 不再作为普通战斗动作和玩家主动画 FSM 的默认编辑器，只保留给奥义、多角色同步、过场和复杂镜头序列。
- 现有 `com.afauxzhub.timeline-abilities` 保留，不删除；在特殊序列进入实际范围前不继续扩展为通用战斗动作框架。

## 2. 为什么不继续扩展 Timeline 主方案

Timeline 适合长序列和多轨编排，但用于每个普通攻击和技能时会引入大量 Director、绑定、轨道和编译资产。动画状态之间的过渡关系也无法在同一角色图中直观看到。

Animator Controller 更适合当前优先级：

- 状态、子状态机和过渡在同一图中可见。
- Blend Tree 可以直接预览移动方向、速度与转向混合。
- Animation Layer、Avatar Mask 和 Additive 动画适合拆分全身、上半身、受击修正、瞄准和表情。
- Animator Override Controller 可以复用结构并替换不同角色的动作，但过渡退出时间必须使用 normalized time。
- StateMachineBehaviour 只作为状态进入/退出、表现通知和调试桥接，不承载资源、伤害或取消规则。

官方参考：

- <https://docs.unity3d.com/6000.0/Documentation/Manual/Animator.html>
- <https://docs.unity3d.com/6000.0/Documentation/Manual/class-BlendTree.html>
- <https://docs.unity3d.com/6000.0/Documentation/Manual/AnimationLayers.html>
- <https://docs.unity3d.com/6000.0/Documentation/Manual/AnimatorOverrideController.html>
- <https://docs.unity3d.com/6000.0/Documentation/Manual/StateMachineBehaviours.html>

## 3. 状态结构

### 3.1 玩法 HSM

玩法层使用层级状态，不把所有动作铺平成一张巨大 FSM：

```text
Free
  -> Grounded / Airborne
Action
  -> Attack（Startup / Active / Recovery）
  -> Charge / Dodge / Guard / Counter / Skill / Ultimate
Reaction
  -> LightHit / HeavyHit / Launch / Knockdown / GetUp / WallHit / Death
Suspended
```

顶层战斗模式继续遵守 `integration-contracts.md`：

```text
OutOfCombat
NormalCombat
EnhancedCounterCombat
CombatSuspended
```

玩法层必须表达 `ATK-05` 至 `ATK-07`、`COUNTER-01` 至 `COUNTER-02`、`SKILL-05` 至 `SKILL-06`、`HIT-01` 至 `HIT-03`，但不得自行封口 `HIT-05` 等 `[OPEN]` 项。

### 3.2 Animator 图

Base Layer 建议按视觉行为组织：

```text
Locomotion
  -> Idle / Idle Variation / Start / Move / Pivot / Turn / Stop
Airborne
Combat Actions
Reactions
Death
```

附加层根据实际资产逐步加入：

- Upper Body Override。
- Additive breathing、recoil、hit accent。
- Aim / Look / weapon IK。
- Face。

只允许死亡、强制受击等少数硬中断使用全局过渡，避免 `Any State` 形成不可追踪的过渡网。

## 4. ActionDefinition 与专用编辑器

每个动作资产至少包含：

- 稳定动作 ID、用途和对应规则 ID。
- AnimationClip、Blend In/Out、播放速度或时间映射。
- Root Motion 策略、位移请求和可选目标对齐。
- 前摇、有效攻击阶段、后摇。
- `CounterWindow`、`CancelToEvade`、`CancelToGuard`、`CancelToSkill`、无敌与移动窗口。
- Hitbox、伤害/失衡请求及命中反馈事件。
- VFX、SFX、镜头、顿帧、时间缩放、IK和表情轨道。
- 被打断分支及仍属 `[TUNING]` 的字段。

专用编辑器应提供：

```text
Animation       [========================]
Hitbox                  [=====]
CounterWindow          [===]
CancelToEvade                 [===========]
CancelToGuard                 [===========]
CancelToSkill                         [====]
Invulnerability       [======]
RootMotion       [curve------------------]
IK / Warp             [--------]
VFX / SFX / Camera        *   *    *
```

- Scene View 或独立预览角色逐帧拖动。
- 表现帧与玩法判定帧可独立移动，遵守集成契约 2.2。
- Play Mode 显示当前 Animator 状态、下一状态、normalized time、活动窗口和 Root Motion 所有者。
- Animation Event 仅用于脚步、尘土、声音等非权威表现通知；命中、取消、反击和资源结算使用强类型轨道数据。

## 5. 3C 与 Root Motion 边界

- `Character Motor` 是最终位置与旋转的唯一写入者。
- Animator 的 `deltaPosition` / `deltaRotation` 转为 Root Motion 请求，再由 Motor 做碰撞和实际应用。
- 输入、相机、Heading Solver、动作和目标对齐只能提交意图，不能与 Motor 同时写 Transform。
- 起步、持续移动、停止和折返是移动阶段；左右弧线和转身动作属于表现选择，不膨胀为平行主状态。

## 6. 官方与开源方案边界

### 6.1 采用或评估

- Unity Animator Controller：主动画图。
- Unity Animation Rigging 1.4：评估武器手 IK、脚底贴地、Look/Aim 和局部姿势修正。
- UnityHFSM：MIT，可作为玩法 HSM 的候选实现；它不替代可视化动画图。<https://github.com/Inspiaaa/UnityHFSM>
- JLPM22 MotionMatching：MIT、标记支持 Unity 6+，仅作为主城/探索 Locomotion 的独立实验，不负责战斗招式窗口。<https://github.com/JLPM22/MotionMatching>

### 6.2 暂不作为生产依赖

- Unity Behavior：适合 Boss、NPC和任务决策图，不作为玩家动画播放器。
- Kinema Motion Matching：功能方向与 Unity 6000.3 匹配，但当前成熟度和采用证据不足，只允许隔离验证。<https://github.com/Nekuzaky/kinema-motion-matching>
- Animancer：现有 GitHub 仓库只公开文档，不是开源源码；直接代码播放不解决当前最重要的图形可见性问题。
- Unity Animation DOTS 示例：官方仓库仍明确标记为高度实验性，不作为当前生产底座。

## 7. 验证顺序

1. 用占位动作建立 Animator 图：Idle、Start、Move、Pivot、Stop、L1、Dodge、Hit。
2. 验证动画师可以在不修改代码的情况下调整过渡、Blend Tree 和替换 Clip。
3. 实现最小 `ActionDefinition` 编辑器：Animation、Hitbox、Counter、三类 Cancel 和 VFX/SFX。
4. 验证 L1 前摇/有效帧/后摇与闪避、防御、技能取消优先级。
5. 验证受击可硬中断普通动作，技能不能取消受击僵直。
6. 验证 Root Motion 只经 Motor 应用，程序移动与动画位移不重复。
7. 使用真实动画检查脚滑、转身、混合、镜头和特效效果。
8. 动画库数量和质量足够后，再独立比较 Blend Tree 与 Motion Matching 的主城移动效果。

## 8. 当前验证边界

- 已完成：参考工程和候选方案的静态调查、职责划分、状态结构和验证标准记录。
- 尚未完成：Unity 包安装、Animator 图、Action Editor、真实动画、Animation Rigging、Motion Matching 与游戏运行验收。
- 本文不代表任何候选方案已经通过 Unity 6000.3.24f1 运行验证。

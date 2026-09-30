# ANIM-002：验证 Animator-first 动画状态机与战斗动作编辑器

| 字段 | 内容 |
| --- | --- |
| 状态 | Backlog |
| 类型 | 工具开发 |
| 里程碑 | M1：玩家战斗最小灰盒 |
| 负责人 | 当前主任务 Agent |
| 创建日期 | 2026-09-30 |
| 最近更新 | 2026-09-30 |

## 目标

在 Unity 6000.3.24f1 中完成一个可由动画/设计侧直接观察和调整的最小原型，证明 Animator Controller、专用 `ActionDefinition` 编辑器与轻量玩法 HSM 能共同覆盖移动、普通攻击、闪避和受击，而不依赖 Timeline 作为玩家主动画状态机。

## 范围

- 本次包含：
  - Idle、Start、Move、Pivot、Stop、L1、Dodge、Hit 的 Animator 图。
  - 最小 `ActionDefinition` 及 Animation、Hitbox、Counter、Cancel、VFX/SFX 轨道。
  - 当前状态、normalized time、活动窗口与 Root Motion 所有者的运行时调试显示。
  - Animation Rigging 的最小可行性检查。
- 本次不包含：
  - 完整 L1-L4、H1-H3、全部技能、奥义、Boss 或正式美术资源。
  - Motion Matching 的生产接入。
  - 删除现有 `com.afauxzhub.timeline-abilities`。

## 权威依据

- 相关文档：
  - `docs/architecture/animation-state-machine-architecture.md`
  - `docs/design/combat/player-combat-spec.md`
  - `docs/design/combat/integration-contracts.md`
  - `docs/architecture/locomotion-framework.md`
- 规则 ID：
  - `ATK-05` 至 `ATK-07`
  - `COUNTER-01` 至 `COUNTER-02`
  - `SKILL-05` 至 `SKILL-06`
  - `HIT-01` 至 `HIT-03`
  - `PROTO-01` 至 `PROTO-03`

## 依赖

- Unity 6000.3.24f1 工程能够稳定编译运行。
- 至少一组可用于验证的 Idle、Move、L1、Dodge 和 Hit 动画；可先使用占位动作验证编辑器结构，真实表现验收依赖 `ANIM-001`。
- `PROTO-001` 开始前确认第一轮灰盒动作数据需求。

## 验收条件

- [ ] Animator 图可见并能在 Play Mode 显示当前/下一状态和过渡。
- [ ] 新增或替换原型动作不要求修改玩法状态代码。
- [ ] 表现时序与 Hitbox、Counter、Cancel 等玩法时序可以独立调整。
- [ ] L1 的闪避/防御取消不晚于技能取消，且技能不能取消受击僵直。
- [ ] Root Motion 只经 Character Motor 应用，没有重复位移或旋转写入。
- [ ] Animation Rigging 的收益和代价有真实角色检查记录。
- [ ] Unity 编译、EditMode 检查和代表性 Play Mode 场景通过。
- [ ] 使用真实动画完成过渡、脚滑、转身、受击和技能特效的人工验收。
- [ ] 任务索引和交接记录已更新。

## 实施与决策记录

- 2026-09-30：确认动画效果和编辑可见性高于复用现有 Timeline 技能框架的便利性。
- Timeline 降级为奥义、多角色同步、过场和复杂镜头序列的候选工具。
- Motion Matching 只作为主城/探索 Locomotion 的后续独立实验，不能替代精确战斗动作窗口。

## 验证记录

| 日期 | 环境 | 检查 | 结果 | 证据/备注 |
| --- | --- | --- | --- | --- |
| 2026-09-30 | 静态文档 | 架构与战斗规则映射 | 通过 | 未修改 `[CONFIRMED]` 规则，未封口 `[OPEN]` 项 |

## 已知问题与未验证边界

- 尚未在 Unity 中建立 Animator Controller 或专用编辑器。
- 尚未安装和验证 Animation Rigging、UnityHFSM 或任何 Motion Matching 候选。
- 真实动画质量、脚滑、Root Motion、目标对齐、特效和镜头编辑体验均待用户电脑验证。

## 交接

- 已完成：架构方向、责任边界、候选方案和验收条件落库。
- 已验证：文档与现有战斗规则契约不存在已知冲突。
- 尚未验证：全部 Unity、动画和运行时行为。
- 下一步：在隔离分支或工作树中建立最小 Animator + ActionDefinition 原型。
- 相关提交：见包含本任务卡的架构决策提交。

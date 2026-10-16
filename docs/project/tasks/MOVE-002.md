# MOVE-002：无连线动作配置、衔接预览与 Play 最小闭环

| 字段 | 内容 |
| --- | --- |
| 状态 | Awaiting Runtime Validation |
| 类型 | 工具开发 |
| 里程碑 | M1：玩家战斗最小灰盒 / 移动动画优先支线 |
| 负责人 | 当前主任务 Agent |
| 创建日期 | 2026-10-15 |
| 最近更新 | 2026-10-15 |

## 目标

在独立测试场景用 Idle↔Run 证明新的制作方式：替换动画、拖动融合时长/曲线即可预览和运行，不打开或重生成 Animator Controller。

## 范围

- 包含：实现角色动作槽、共享衔接模板/角色覆盖的最小数据模型；Playables 播放适配器；直接混合和可选桥接 Clip；当前配方/Clip/权重调试；Play 会话覆盖与显式保存/丢弃。
- 保留旧配置和场景。先验 Idle/Run/Start 切片；2026-10-15 用户授权后继续接入 MOVE-003 至 MOVE-008 共用播放机制，不扩张成全功能图编辑器。
- 不包含：完整移动动作组、动态 IK、正式战斗资源/伤害系统、旧图重新布局及新增第三方库。

## 权威依据

- `docs/architecture/animation-state-machine-architecture.md` 第 0 节。
- `docs/architecture/locomotion-framework.md`、`docs/architecture/company-reference-reuse-review.md`。
- `docs/design/combat/player-combat-spec.md`、`docs/design/combat/integration-contracts.md`；涉及动作打断时遵守 ATK-05..07、SKILL-05..06、HIT-01..03、COUNTER-01..02，不封口未确认规则。

## 依赖

MOVE-001 已完成；ANIM-002 现有 Idle/Run、预览与规则测试作为回归基线。确认实际骨架输出和 Animator/Playables 共存边界后实施，不让两个播放器同时写同一骨架。

## 验收条件

- [ ] 在隔离配置副本替换 Idle/Run 后直接生效；新增/删除同类变体有引用提示和 Undo，不要求修改状态代码、画边或生成 Controller。
- [ ] 衔接编辑器可调进入/退出点、重叠时长、权重曲线、目标起始相位；显示真实命中模板/覆盖及冲突，不让用户填写全连接矩阵。
- [ ] 隔离预览与 Play 使用同一播放/配方核心；逐帧、循环比较、当前/下一 Clip 权重与时钟可见。
- [ ] Play 中调参先写会话覆盖，显式保存差异或丢弃；退出 Play 不意外丢失已选择保存的配置，也不自动改源 Clip/场景。
- [x] 中途反向请求和同 Clip 重入不重置淡出源时钟，不反复重启同一过渡；无控制器新路径只由一个动画输出求值。
- [x] 最小战斗适配回归保持 L1 重播、受击打断与返回移动、表现/玩法双时钟和取消权限；不靠修改 ActionDefinition 玩法窗口消除差异。
- [ ] Unity 6000.3 编译、Editor/Player 程序集隔离及逻辑测试通过；真实 Idle↔Run（含中途改输入）完成 Play 和编辑器人工验收，记录差异。
- [ ] 更新本卡证据、缺项和交接，并同步唯一任务索引；机制通过不代替真实表现通过。

## 必要验证

静态检查数据序列化/引用稳定性、规则匹配/冲突、双时钟和过渡中断测试；Unity 实编译及隔离场景 Play；在编辑器实际操作换 Clip、拖曲线、Undo、保存/丢弃并重开配置。测试临时改变恢复，不修改原场景。

## 实施与决策记录

- 2026-10-15 实施授权：用户允许操作个人 Unity 并在最小闭环后自主推进缺资源情况下可完成的代码/环境。先完成本卡机制与隔离场景验证，再依次扩展 MOVE-003 至 MOVE-008；缺资源不伪造表现验收，MOVE-010 继续 Deferred。保留旧场景/配置，不操作外部工程或 Max。

- 2026-10-15 前一轮：建立任务，仅规划。后续本轮已在个人 Unity 实施，Max 未操作。
- 已新增 MotionLibrary / MotionRecipeTemplates、ClipBlendPlayer、MotionLibraryPlayer、MotionWorkbench、隔离预览与场景生成/验证入口。具体数据/播放合同与明确未完成项统一写在架构第 0.5 节。
- 已创建本地忽略的 AceMotionLibrary / AceNoWiresLab；修复新场景 Prefab override 引用未持久化，以及预览 Graph 跨 Play 切换未及时释放的问题。
- 不覆盖旧场景/配置；参考资产、报告和截图留在本地忽略目录，不提交公司资源或路径。

## 验证记录

| 日期 | 环境 | 检查 | 结果 | 证据/备注 |
| --- | --- | --- | --- | --- |
| 2026-10-15 | 文档/源码核对 | 范围、依赖和验收清单 | 已登记，功能未验 | 当前能力基线见 ANIM-002 和任务索引；不沿用旧机制测试作为本卡通过证据 |
| 2026-10-15 | Unity 6000.3.24f1 | 新 Editor 核心断言 | 123 通过 | 真正 PlayableGraph 姿势/权重、同 Clip 独立时钟、100 次快速中断、配方冲突、裁切/速度/相位和非法数据 |
| 2026-10-15 | Unity 6000.3.24f1 | Play 回放 | 通过机制回归；详见本地报告 | 双套阶段、真实离地、L1 重播、受击/取消门控、返回移动、源动作库不变；不等于全链美术验收 |
| 2026-10-15 | 原生界面 + MCP 数据核对 | 逐帧、融合拖柄、Undo | 通过 | 逐帧 0→0.033333s；草稿融合 0.18→0.475362s，源仍 0.18；Ctrl+Z 还原且草稿 clean |
| 2026-10-15 | Editor API / 真实资产重导入 | 显式保存与重载 | 通过 | 0.29s 保存后重导入存在，再恢复 0.18s；验证无错误。该项为 API 驱动，不冒充点击保存按钮的完整人工流程 |
| 2026-10-15 | 原生按钮 + Play / 退出 Play | 应用草稿、换 Clip 和丢弃 | 通过代表性路径 | 实际点击“应用到 Play”：工作副本 0.31s、源仍 0.18s；API 替换草稿 Idle 为 IdleVariation 后实际播放该 Clip，Controller 仍为空；退出 Play 后草稿保留，丢弃后恢复源引用 |
| 2026-10-15 | Unity 编译 / 源程序集清单 | Editor/Player 隔离 | 通过 | Workbench 在 Assembly-CSharp-Editor，Player 在 Assembly-CSharp；CompilationPipeline 的 Player sourceFiles 中无 Assets/Editor/Animation 文件。未做独立 Player 构建 |

## 已知问题与未验证边界

旧 CharacterAnimationProfile 仍引用 Controller，工作台不更新旧图。新场景 Controller=null，只有新播放器输出。真实 Root Motion 未验，强制程序 Motor；动态 IK 关闭。权重曲线/桥接/各 Clip 入出点的真实美术对照、完整增删资源操作仍待用户试用；短预览不是整个 locomotion/Motor 的复制。首版使用淡出姿势快照，最终动画连续性待实际资源调优。

## 交接

- 已完成：无连线配置/播放器/隔离预览/草稿保存与覆盖核心、独立场景和可重复回放入口；没有删除旧路径。
- 2026-10-16：MOVE-011 已补候选审核、资源矩阵/定位/导出、图形入出点裁剪、模式配方选择和内置帮助；工作台六页绘制、独立配置保存/重载/Undo 已回归。使用说明见 `docs/tools/motion-workbench-guide.md`；原用户草稿保留。
- 已验证：123 项 Editor 断言、旧战斗/纯逻辑回归、代表性真实 UI、保存重导入与 Play；帧率结果汇总见任务索引。
- 下一步：在工作台试调 Idle→Start→Run 的完整衔接，对照真实姿势；尚未验收的美术/操作项保留未勾选。代码可继续进入 MOVE-003，不等待缺 Clip 才推进。
- 相关提交：本轮未提交或推送。

# 角色动画配置与战斗动作架构

| 字段 | 内容 |
| --- | --- |
| 决策日期 | 初版 2026-09-30；制作方式修订 2026-10-15 |
| Unity 基线 | 6000.3.24f1 |
| 状态 | 无连线播放器、动作工作台和独立场景已落地；移动/跳跃基础机制已接入，完整资源与表现仍待逐项验收。旧 Animator 原型保留 |
| 优先级 | 动画效果 > 编辑可见性 > 玩法可控性 > 实现成本 |

## 0. 当前决策：动作配置优先，不维护 Animator 连线

### 0.1 变更与范围

2026-10-15 用户明确拒绝以 Animator 节点连线配置状态动画：调融合、修改衔接、增删 Clip、换角色都应通过更简单的制作入口完成。本节取代第 1–3、6–7 节中关于 Animator 作为主要制作入口的旧决定；不是在旧图上继续分组或隐藏连线。第 4–5、10 节的战斗权限、双时钟、位移所有权及资产保护约束继续有效。

- 日常入口是“角色动作槽 + 衔接配方 + 同源预览/运行观察”，不用 Animator 图，也不用为每对状态手工配置一条边。
- 底层实施选择 Unity Playables 的 Clip/Mixer 播放适配器，按数据创建和维护必要的混合节点；Animator 组件可以保留作骨架输出，但新移动链不依赖 Animator Controller 图。它不是 Timeline/PlayableDirector 技能方案的回归。
- Unity 官方 API 支持不创建 Animator Controller 直接播放 Clip、动态建立混合并控制权重；本项目仍需自行制作友好的编辑器，官方 API 本身不提供这套制作界面。依据：[Unity 6.3 Playables](https://docs.unity3d.com/6000.3/Documentation/Manual/Playables.html)。
- 复用现有移动意图/朝向数学、Motor、战斗规则层、ActionDefinition、轨道编辑与预览经验；替换 Animator 专属的播放和配置耦合，不重写玩法规范，不引入 Motion Matching。
- 新独立场景走 `MotionLibraryPlayer` → `ClipBlendPlayer`，Animator Controller 为空；旧场景继续原路径。下文工作流是完整目标，实际已交付/未交付边界见 0.5，不以槽位存在代替效果验收。

### 0.2 配置模型与美术工作流

| 配置 | 保存内容 | 换角色时的操作 |
| --- | --- | --- |
| 角色绑定 | 模型、Avatar/显式骨架绑定、模型朝向与比例、可选 IK 绑定 | 换模型，验证实际骨架路径；不猜骨骼名，不默认兼容 |
| 双套动作库 | 放松/战斗准备两套语义槽；方向、步态、变体、Clip、播放速度、入口相位及资源状态 | 拖入或批量匹配 Clip，审核匹配结果和缺项 |
| 共享衔接模板 | 起步、停步、换挡、转向、空中/落地等动作族的默认配方 | 复用模板，只覆盖角色确有差异的项 |
| 角色调参 | 速度/转向参数及配方覆盖 | 修改可见覆盖项；能恢复继承值并预览差异 |

槽和配方使用稳定 ID；文件改名不成为状态切换条件。增删同类动作、替换 Clip、调整融合、改变允许范围内的衔接不要求改代码。新增“攀爬”等全新行为仍需增加行为逻辑和验收，不能承诺所有行为都纯配表。

编辑器以三个工作区为目标：

1. **动作库**：先选姿态，再选步态/方向/动作族。支持批量填充、变体增删、引用检查；缺失、占位回退、真实资源分别标记。删掉在用 Clip 先列出影响，允许 Undo，不删除源文件。
2. **衔接配方**：选择“上一动作 → 可选桥接动作 → 下一动作”，在短时间条上拖入点、出点、重叠区，编辑混合时长/曲线、目标起始相位、脚步相位标记、速度映射和可中断区间。支持直接混合或独立衔接 Clip，逐帧播放与循环比较。比如 Idle → Start → Run、Run → Accelerate → Sprint、Run → Stop → Idle；不要求手绘节点边。
3. **运行观察**：显示实际生效配方、来源/目标 Clip 及权重、相位、期望/实际速度、转向角、姿态/锁定模式、资源回退与中断原因。Play 调参先进入会话覆盖，显式“应用”用于测试，显式“保存差异”才写配置；退出 Play 可选择丢弃，不隐式保存资产或场景。

规则按“动作族默认 → 姿态/步态/方向覆盖 → 特定衔接覆盖”解析，只编辑例外，不制作 N×N 全连接表。匹配优先级可见；相同优先级冲突必须报错；预览显示实际命中的规则。中途松键、反向、再起步或切换步态须从当前混合姿态继续，不反复重启同一过渡；旧/新 Clip 时钟独立，同一动作重入也不能把淡出源归零。

预览与 Play 使用同一配方求值/播放核心，区别只在隔离预览驱动与真实输入/Motor。移动的阶段/中断策略不能代替 Combat Rule HSM 的取消许可；动画时间调整不能悄悄改变 Hitbox、Counter、Cancel 窗口。移动切战斗、战斗回移动必须通过播放适配器回归验证。

### 0.3 完整移动目标与资源覆盖

两套姿态各自覆盖 Idle、Walk、Run、Sprint；自由移动和锁定目标模式正交。完整目标包括各方向靶向移动与方向切换、多方向起步、左右支撑脚停步、原地/移动转向、90 度转向、弧线与急弧、180 度折返、加速冲刺、减速，以及待机和移动中的跳跃与落地。不能默认把其中一套姿态或某个方向降级为不支持。

- 资源矩阵按“姿态 × 模式 × 步态 × 方向/动作族”列实际需要的槽及衔接变体。先登记缺项与制作要求；用混合共享、专用桥接或经审核的复用覆盖，不要求机械制作所有笛卡尔积，但每个可达组合都须有明确配置和验收结果。
- Start/Stop/转身等片段记录入口/出口姿态、左右支撑相位、适用速度/角度和位移策略；循环动画记录步长/节奏。这些数据可提前制作，**不等于提前实现动态锁脚**。
- 占位和回退仅用于机制验证；完整表现通过必须有适用的真实动画，不能把跑步降速当 Walk、待机滑动当靶向移动、原地旋转当转身动画。缺资源不妨碍先搭机制，但会阻止对应表现项标记完成。
- 跳跃链包含起跳、上升/空中、下落、落地到 Idle 或继续移动，支持从待机/走/跑/冲刺发起及两套姿态。允许动作资产按内容合并阶段，但代码必须有垂直动力学与落地判定；已有 Fall/Land 槽不算已实现跳跃。
- 跳跃输入独立配置，当前 Space 是闪避，不能直接覆盖。水平惯性、空中转向、起跳高度/重力和落地响应为 `[TUNING]`；本轮不新增二段跳、攀爬、空中攻击、跳跃无敌或受击脱离权限。攻击/受击中能否跳跃不在动画工具中暗自决定，仍由玩法许可控制。
- 所有根位移/旋转（含跳跃）经 Motor 处理碰撞。缺少可信 Root Motion 时显示程序位移；Root Motion 支路另需真实数据验收，不能让 IK 掩盖步长/速度不匹配。

### 0.4 实施次序和旧原型去向

唯一实施清单见 [`tasks.md` 的移动动画清单](../project/tasks.md#移动动画实施清单)。先做 MOVE-002 的 Idle↔Run 无连线最小闭环，再逐项扩展；MOVE-010 的动态锁脚、滑步、混合接触权重和动态地形修正在所有移动功能连通后最后实施。

ANIM-002 旧连线原型冻结并保留回归证据，不标 Done、不删除现有测试资产、不再安排图连线整理。新路径使用独立测试场景/配置副本；现存动作编辑器继续可用。已有静态 IK 可保留开关和回归，不在前序任务扩展动态锁脚，也不把其数值到达目标当成动态表现通过。正式个人资产发布仍独立接受 ANIM-001 验收。

### 0.5 首轮落地边界与使用入口（2026-10-15）

本节保留首轮快照；后续制作闭环见 0.6，2026-10-19 Root Motion 见 0.7，当前操作方式见 [工作台指南](../tools/motion-workbench-guide.md)，不再将下面的“尚未完成”直接视为最新代码清单。

- **配置入口**：`Tools > MY Project > Animation > Motion Workbench (No Wires)`。动作库/衔接配方/移动参数/运行覆盖四页；稳定 ID 槽位、Clip 替换和清空、禁用变体、绑定覆盖检查、共享模板与角色覆盖。共享模板只读，先复制为角色覆盖再修改；同排名冲突退回默认融合并报警。
- **衔接预览**：隔离模型、30fps 逐帧/播放/拖时间、拖黄色把手修改融合时长、CurveField 编辑权重曲线、可选桥接、入出点及相位。自动匹配模式显示真实规则来源；“试播所选覆盖”明确忽略匹配条件。预览与运行共用 Clip/Mixer 核心和规则解析；预览是双 Clip/桥接试播，不模拟完整输入、速度混合和地形。
- **保存边界**：工作台和 Play 都使用副本；`应用到 Play` 不写源资产；`保存差异` 显式写动作库/移动参数（可 Undo），检查源资产并发变化；`丢弃草稿` 重新载入源配置。只改引用，不重写 Clip/FBX。Play 副本同时克隆共享模板，运行不会反写模板。
- **播放机制**：手动求值单个 PlayableGraph，禁用 Clip AnimationEvent、内置 FootIK 和 Root Motion；战斗使用独立 ActionDefinition 时钟/权限。转场把当前混合姿势作为淡出快照；同 Clip 重播拥有独立目标时钟。快照淡出不是惯性化或持续采样源动画，仍需真实资源打磨；没有宣称达到最终融合质量。
- **移动机制**：双套循环的速度权重、方向起步、左右停步、加减速槽及回退、跑步缓/急弧和冲刺左右弧、90°/折返阶段、八向角度混合、Motor 单次起跳/上升/顶点/下落/落地已接入。循环按裁切范围和速度计算共享相位周期，避免非整数播放速度在 wrap 处复位。起停支撑脚当前仍按半周期估计，尚无美术脚步标记。
- **跳跃输入**：默认 `C`，Space 仍是闪避；高度、空中控制、起跳时长等可调。拒绝二段跳、动作/受击中跳跃及普通空中攻击；权威受击结果仍可打断。没有新设空中战斗/受击脱离许可。
- **缺资源策略**：无 Walk/冲刺/弧线时回退 Run；缺方向起步回退正向 Start；其余缺项回退 Idle，并显示“请求槽 → 实际槽”。这可能是站姿滑移或站姿跳跃，绝不是动画效果通过。当前参考库 128 个条目（含可选步态覆盖），仅 17 项已赋；8 个战斗动作继续由原 Profile 引用。
- **尚未完成**：资源审核矩阵产品化/批量审核、入出点图形拖柄、脚步相位标记、专门原地转身调度、靶向模式专用衔接覆盖、完整方向/步态/跳跃资源、第二角色无代码切换验收、真实 Root Motion。靶向已有通用 Start/Stop/加减速阶段与停止前方向保持；不等于专用美术链。新版测试场景 IK 整体关闭；动态锁脚/滑步仍只属于最后的 MOVE-010。

本地参考入口为 `Assets/LocalAnimationLab/ace-animation-lab-reference/AceNoWiresLab.unity` 与 `AceMotionLibrary.asset`，均在忽略目录，不加入 Build Settings。原场景、旧 Profile、公司工程和 Max 不属于本轮修改范围。

复验：`Validate No-Wires Core (no scene save)`；在干净独立场景使用 `Run No-Wires Play Sweep > 30/60/120 fps`。自动脚本进入 Play、回放输入、检查状态/权重/跳跃/打断、退出并恢复全局帧率设置；报告位于 `Client/Library/NoWiresValidation/play-*.json`，只是机制证据，不是美术或性能验收。

### 0.6 代码优先制作闭环目标（2026-10-16）

用户暂不补素材或调效果，优先完成程序位移模式的制作闭环（MOVE-011）。完成标准是新角色独立接入、资源候选审核、已有移动语义填槽、按模式/步态/方向选择、支撑相位元数据、实际命中配方和机制测试均可用；不以合成 Clip 或回退姿势宣称正式动画效果完成。

- 槽位允许 Any / Free / Targeting 模式覆盖，旧条目默认 Any；配方可按前后模式区分，保留旧库兼容。原地转身使用独立语义槽，不拿移动折返自动充当原地动作。
- 接触曲线使用源 Clip 的归一化时间（裁切/相位映射后采样），只用于动作选择与诊断，不执行锁脚。参考速度、适用范围和审核信息独立于生成 Clip 保存。
- 新角色向导只创建新资产/场景，缺 Clip 可先生成完整槽表。批量匹配只提候选，审核确认才改草稿；名称不证明骨架兼容。
- 保留“草稿 → Play 副本 → 显式保存”的边界。代码完成与真实资源/美术验收分开记录，动态锁脚仍属于最后 MOVE-010。真实 Root Motion 和正式战斗灰盒不混入本轮完成口径。

2026-10-16 已实现上述制作入口：工作台增加批量候选与帮助页、源动画入出点双柄条、模式配方条件、资源审核/过期状态、JSON/TXT 缺项导出；新角色向导独立创建库/移动参数/模板/灰盒适配与场景。详见 [制作与交接指南](../tools/motion-workbench-guide.md)。

运行契约补充：

- `MotionCatalog` 包含双套 136 选择槽，其中 86 基础、50 可选；旧库仅通过显式“补齐新版本动作槽”迁移，不自动重写。Any 的明确共享不算回退，不要求一个槽对应一个独立文件。
- 同一启用选择键（姿态/模式/槽/步态/方向）唯一；具体模式优先于共享项。速度/绝对角度范围用于过滤，一次性阶段使用进入时选择值，循环使用当前值。新增语义仍需实现代码，非任意可视化行为编程。
- 支撑脚由当前 Playable 混合姿势的源时间、权重与脚接触曲线计算；已知权重不足或双脚难区分时明确使用估计，不暗示无滑步。参考速度匹配只在动作显式启用后生效。
- 原地转身与移动转向分离；输入可按阶段中断比例取消，靶向改变或目标停用取消旧锁存；最后角度只在正常结束时提交，打断不瞬移补足原目标角度。
- 新角色向导不关闭/保存原场景，不覆盖目录，不改 Build Settings；模型仅复制渲染层，不实例化原模型脚本。参考资产的递归依赖不允许写入正式目录。
- 审核指纹跟踪模型/Clip 及其依赖；扫描、预览、Play 互不自动批准审核。换模型不在 Play 中自动更换网格，需要新建/调整角色场景。

机制与运行证据集中记录在 MOVE-011；最终视觉验收仍属于 MOVE-002 至 MOVE-009。

### 0.7 无连线 Root Motion 契约（MOVE-013，2026-10-19）

- 姿势与位移分离：手动定位 Clip 的姿势图不自动移动 Transform。Editor 在隔离模型上顺序求值 Unity 原生根运动，120Hz 提取模型专属的累计位置/旋转，保存在动作配置中，不改源 Clip、FBX 或 Max 发布协议。
- 提取需要明确的导入 Root/Motion 数据。缺曲线时拒绝，不猜骨骼路径、不把髋关节抖动当根运动。根轨迹保存模型/Clip 引用和依赖指纹；源文件或模型改变后须重新提取。正式发布仍归 ANIM-001。
- 动作槽默认为程序位移；启用 Root Motion 后可独立选择根转向、调整距离缩放。移动槽的 Y 保持重力/弹道；ActionDefinition 可显式启用垂直根位移，仍由 Movement、RootMotionScale、ApplyRootRotation 决定位移策略，轨迹配置不授予战斗权限。
- 根采样使用与姿势相同的裁剪、相位、播放速度及动作时间映射；循环保留双精度未取模时间，只组合本帧跨过的圈数，避免长时间全局累计位置相减的精度损失。跨圈按完整刚体变换组合，Motor 对直立胶囊仅应用 Y 轴转角。切目标/跳转相位建立独立基线，动画图重建或重新启用不重放已经过去的动作位移。
- 过渡仍采用当前姿势快照淡出：淡出快照的根速度为零，目标根增量按同一混合权重淡入。程序位移只占非根运动权重，不额外叠加完整程序速度。此策略不是惯性化；通过融合调速可能缩短过渡段的实际位移，需作者调校。
- Combat 的结束/打断时机不因动画更改。正常结束消费最后尚未采样的根增量；受击/取消不消费剩余轨迹。暂停不推进根时钟，不积攒恢复补偿。缺根轨迹明确报错并保持该权重的位移，不伪造程序位移成功。
- Motor 唯一拥有实际位置/朝向；根请求每帧经 CharacterController 碰撞，阻挡位移丢弃而不欠账。默认 Y 由重力/跳跃负责；动作显式选垂直根位移时，不再叠加同权重重力，退出时继承碰撞后的垂直速度。地面移动离边与主动跳跃继续使用弹道策略，不因为 Root Motion 开启而新增空中动作许可。
- 数据缓存是角色专属，换 Avatar/比例必须重新提取和验收。验证分三层：合成轨迹数学与原生提取、实际 Play 碰撞/生命周期、真实角色观感；前两者不能代替第三者和 Max 发布。

## 1. 历史决策：Animator-first（制作入口已被第 0 节取代）

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
- 2026-10-13 实施范围：收武器/持武器两套配置与锁定目标正交；不采用 Motion Matching。脚部先提供不依赖 Humanoid 的 Generic 两骨 IK，Animation Rigging 保留为后续武器手/瞄准等扩展候选，不自动安装。

## 2. 历史选型理由（非当前制作入口）

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

## 3. 职责结构与旧图记录

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

### 3.2 历史 Animator 图（仅保留作旧原型说明）

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
- Play Mode 显示当前/下一播放动作、混合权重、normalized time、活动窗口和 Root Motion 所有者；旧后端展示 Animator 路径，新后端展示配方和 Clip。
- Animation Event 仅用于脚步、尘土、声音等非权威表现通知；命中、取消、反击和资源结算使用强类型轨道数据。

## 5. 3C 与 Root Motion 边界

- `Character Motor` 是最终位置与旋转的唯一写入者。
- 旧 Animator 路线使用实时 `deltaPosition` / `deltaRotation`；新无连线路线使用第 0.7 节提取并按姿势时钟采样的根增量。两者均转为请求，再由 Motor 做碰撞和实际应用。
- 输入、相机、Heading Solver、动作和目标对齐只能提交意图，不能与 Motor 同时写 Transform。
- 起步、持续移动、停止和折返是移动阶段；左右弧线和转身动作属于表现选择，不膨胀为平行主状态。

## 6. 历史官方与开源调查（2026-09-30，非当前依赖清单）

以下保留当时的选型依据，不作为当前产品能力或价格的最新核验。当前播放器方向以第 0 节为准；暂无新增第三方包依赖。

### 6.1 采用或评估

- Unity Animator Controller：主动画图。
- Unity Animation Rigging 1.4：评估武器手 IK、脚底贴地、Look/Aim 和局部姿势修正。
- UnityHFSM：MIT，可作为玩法 HSM 的候选实现；它不替代可视化动画图。<https://github.com/Inspiaaa/UnityHFSM>
- JLPM22 MotionMatching：此前调查的历史候选；2026-10-13 按用户要求不进入本轮实现或验证。<https://github.com/JLPM22/MotionMatching>

### 6.2 暂不作为生产依赖

- Unity Behavior：适合 Boss、NPC和任务决策图，不作为玩家动画播放器。
- Kinema Motion Matching：功能方向与 Unity 6000.3 匹配，但当前成熟度和采用证据不足，只允许隔离验证。<https://github.com/Nekuzaky/kinema-motion-matching>
- Animancer：现有 GitHub 仓库只公开文档，不是开源源码；直接代码播放不解决当前最重要的图形可见性问题。
- Unity Animation DOTS 示例：官方仓库仍明确标记为高度实验性，不作为当前生产底座。

## 7. 历史原型验证顺序（已由 MOVE-002 至 MOVE-010 接替）

1. 用占位动作建立 Animator 图：Idle、Start、Move、Pivot、Stop、L1、Dodge、Hit。
2. 验证动画师可以在不修改代码的情况下调整过渡、Blend Tree 和替换 Clip。
3. 实现最小 `ActionDefinition` 编辑器：Animation、Hitbox、Counter、三类 Cancel 和 VFX/SFX。
4. 验证 L1 前摇/有效帧/后摇与闪避、防御、技能取消优先级。
5. 验证受击可硬中断普通动作，技能不能取消受击僵直。
6. 验证 Root Motion 只经 Motor 应用，程序移动与动画位移不重复。
7. 使用真实动画检查脚滑、转身、混合、镜头和特效效果。
8. 补齐定向移动、转身、持握切换及脚步接触数据后，继续迭代 Blend Tree 与显式动作过渡；本轮不引入 Motion Matching。

## 8. 旧原型验证边界

- 已完成源码：角色配置工作台、普通 Animator Controller 生成器、动作轨道编辑器、隔离模型/粒子预览、规则窗口时钟、双配置移动驱动、Generic 脚部 IK、运行调试及测试场景生成入口。
- 离线编译将 Locomotion 包、Player 源码和 Editor 源码分开，使用本机可读取的 Unity 2022.3 参考程序集进行兼容性检查；不是 Unity 6000.3.24f1 的实际导入/编译。
- 2026-10-14 已获明确许可，在 Unity 6000.3.24f1 导入隔离参考并实际生成 Profile、Controller 和独立测试场景，未修改原场景/Build Settings，未操作 Max。参考与派生资产、验证脚本及报告均在忽略的 `Client/Assets/LocalAnimationLab/`。
- 已通过 Unity 编译、12 项 Editor 断言、57 项纯逻辑断言，以及三档帧率目标下的双套移动和代表性动作规则测试；这不等于缺资源状态或全部动画质量通过。实测结果与后续缺口以 `docs/project/tasks/ANIM-002.md` 为准。
- 尚未完成：全部模型/武器节点兼容性、Root Motion 提取、移动脚滑、坡面/台阶边缘 IK、粒子/声音/镜头及完整界面交互/人工表现验收。
- 当前是动画制作/验证原型，不是完整战斗游戏：命中裁决、资源与强化反击模式、冷却、技能联动、浮空动力学和目标 Motion Warping 仍由后续正式适配负责。空中/受击状态槽位不代表浮空物理已经实现。

## 9. 现存旧原型源码与编辑入口

本节描述当前实际代码，不是第 0 节新工作流已实现的证据。原入口保留兼容，不再要求用户整理 Animator 图。

| 层 | 实现位置 | 职责 |
| --- | --- | --- |
| 移动数学 | `packages/com.afauxzhub.character-locomotion/Runtime` | 朝向、速度曲线、阶段与转身锁存；不引用项目/公司类型 |
| 角色运行 | `Client/Assets/Scripts/Animation` | Animator 参数、规则时钟、Motor 请求、表现事件与 Generic IK |
| 编辑工具 | `Client/Assets/Editor/Animation` | 工作台、动作时间轴、绑定映射、Controller/场景生成器；不进入 Player |
| 离线检查 | `tools/validation/validate-animation-lab.ps1` | 不启动 Unity 的分程序集编译与纯逻辑测试 |
| 本地参考准备 | `tools/validation/prepare-local-animation-reference.ps1` | 参数化读取外部 Assets，复制动画与渲染依赖到忽略的临时目录；不改源文件、不自动导入 |

Unity 菜单位于 `Tools > MY Project > Animation`：

1. `Character Workbench`：新建 Profile，分别配置 `Sheathed` / `Drawn`，选择模型、移动参数、脚步接触曲线及明确骨骼路径。两种持握状态都可以锁定目标。
2. `Combat Action Editor`：选择动作，逐帧拖动/播放，拖拽/缩放 Hitbox、Counter、Cancel 等窗口；编辑 VFX/SFX/Camera/Marker cue、命中体、动画时间曲线和 IK 权重。支持 Undo。Play Mode 下锁定资产编辑，避免误把调试参数写入资产。
3. `Explicit Clip Binding Map`：显示源路径和目标路径，唯一同名叶节点仅作建议。改路径或剔除 LOD 缺失辅助节点需要逐项确认，只输出新 Clip；拒绝未审核项、不存在的目标和曲线冲突。这不是 rest-pose/骨轴数学重定向。
4. `Import Prepared LOCAL Reference Pack`：手动导入预处理包到忽略的 `Assets/LocalAnimationLab`。派生 Profile、映射、Controller、材质和场景也必须留在该目录，不得提交到仓库。
5. `Run Editor Logic Checks (no scene save)`：验证动作数据约束、表现/玩法时序独立、两骨 IK 数学和预览副本不包含脚本/Collider；使用临时内存对象，不保存场景。2026-10-14 已实机执行，12 项通过。

工作台的 `Actions / Graph` 页生成**新的**标准 Animator Controller，并可直接打开原生 Animator 编辑。现有手工编辑图绝不覆盖。生成图按两种持握状态分别组织 Idle、Start、Move、Accelerate、Decelerate、Stop、左右 Pivot、左右 Turn90、Strafe、Fall、Land；动作按独立 ID 放在 `Actions` 子状态机。默认动作槽含 L1–L4、H1–H3、Charge、Dodge、Guard、Counter、Skill、Ultimate、持握切换及主要受击/死亡类型。

Locomotion 使用显式局部转换，不用全局 Any State 自动打断动作；为了支持同时切换姿态、目标和接地状态，初版生成器保留完整的阶段转换组合，选中节点可查看命名过渡。这正是本次反馈的编辑负担，不再继续裁剪旧图作为解决方案。动作进入由规则接受后 CrossFade，动作退出由图中的可编辑 Blend Out 转换处理。改 Clip、动作 ID、生成参数后需要生成新图或手动同步已有图；不是隐式热重建。旧路径的状态完整路径必须与 `ActionDefinition.animatorState` 一致。

移动过渡使用 `Destination` 中断源，禁止自过渡。实机曾发现 `SourceThenDestination` 配合无序中断会重新选择仍满足条件的当前边，令混合时间反复归零；不应将这组设置重新引入生成器。修复只影响新生成图，不覆盖旧图。

`Live Debug` 可以查看可读的当前/下一 Animator 路径、混合权重、动作秒数、开放窗口和 Root Motion 所有者。该界面不自动进入 Play Mode。

该面板同时显示每条腿的 IK 权重、锁脚状态、脚踝到目标的误差及骨盆偏移。满权重且误差大于 2cm 会告警；权重为 0 时不把历史目标误差当成当前求解误差。`Sole Offset` 表示地面到脚踝轴心的距离，不是鞋底厚度，必须按实际骨架校准。

`pelvisPath` 是相对模型根的显式双腿共同父节点路径，留空时关闭骨盆补偿；不能根据骨骼名猜默认绑定。可配置 `maxPelvisDrop` 和 `pelvisResponse`，依据有效支撑脚的目标高度平滑下沉视觉骨架，再求解双腿。每帧 Animator 求值前撤销上帧补偿，禁用组件时恢复，避免累积写入源姿态；不移动 CharacterController/Motor，也不写源 Clip。补偿只处理有界的竖直下沉，不代表已经处理脚滑、骨盆碰撞、极端台阶或摆动脚轨迹。验收必须区分落地/过渡瞬态与稳定接地，不能只看最后一个样本或权重达到 1。

Locomotion 页默认只显示当前槽的 Clip、接触曲线和预览；需要批量配表时展开 `Show all slot assignments / missing clips`。全部槽位和缺项仍保留，避免完整列表把日常预览推到页面底部。

每个生成动作内含 A/B 两个播放状态，独立的 `ActionTimeA/B` 交替使用：新动作开始时不重置正在淡出的旧姿势，即使连续播放同一动作也不共用一个被归零的时间参数。两份状态使用同一 Clip，艺术修改过渡时应保持两路配置一致；手工图可以配置自己的双路径与时间参数。

## 10. 动作与移动调参约定

- Gameplay window 的单位是秒，区间为 `[start, end)`；同一时刻先关闭窗口、再开启窗口、最后触发 cue。大帧步也逐个分发边界，打断会清理活动窗口及本动作生成的表现物。
- `animationTime` 的 X/Y 都是 0–1：动作时间比例映射到 Clip normalized time；修改它不移动玩法窗口。`duration`、阶段边界与全部窗口应单独审查，非法取消时序会被运行层拒绝。
- `hold` 适合防御/蓄力停留，`onRelease` 配置释放动作。规则转换的 `Ended/Changed` 通知中禁止同步重入发起新转换；应延后发出请求。
- `ICombatActionGate` 由正式项目实现资源、冷却、模式与技能链验证。缺少适配时 Guard/Skill/Ultimate 拒绝执行。测试场景的 `AnimationLabPermissionGate.allowUnpaidPreview` 默认关闭，手动打开只表示绕过付费模拟，不证明任何资源规则已验证。
- 反击无独立按键。反击结果需要外部裁决、当前主动攻击以及开放 Counter 窗口；受击期间不会接受过期反击或技能取消。受击闪避仅识别明确 `EvadeEscape` 数据，模板不为尚未确认的 `HIT-05` 自动添加窗口。
- `CharacterControllerMotor` 仍是角色根位置/旋转唯一写入者。Animator 位移由 Relay 收集，Motor 统一碰撞应用；当前垂直位移由重力负责。未提取出 Root Motion 时明确显示程序移动回退，不伪称动画根运动已生效。
- Start/Stop/Pivot/Turn90/Land 的姿势采样跟随配置阶段时间；连续移动按速度与转向混合。脚步接触曲线是独立制作数据：0 为摆动，接近 1 时允许落脚锁定；默认为 0，不根据动画名猜测接触时机。Idle 可做基础地形对齐，移动时仅接触段施加 IK，避免把摆动脚压到地面。
- 动作预览只复制 Transform、渲染组件、Avatar 及受限粒子组件，不复制游戏脚本/碰撞器、不修改当前 Scene。复杂脚本特效、SubEmitter、声音与镜头需要 Play Mode；预览中的命中体只是编辑可视化，不执行伤害结算。

## 11. 历史资源盘点与旧原型测试说明

下面包含最初参考包的调查；新参考角色已直接通过绑定匹配，不沿用旧角色层级重建结论。当前可见效果、缺项和新实施顺序统一见 [`tasks.md`](../project/tasks.md)；本节不再作为下一轮执行清单。

基于本轮本地参考资源的**文件名/曲线路径静态盘点**，不是视觉验收：

| 项目 | 收武器参考 | 持武器参考 | 当前处理 |
| --- | --- | --- | --- |
| Idle / Start / Run | 有候选 | 有候选 | 绑定覆盖审核后再赋槽 |
| 左右 Stop | 有候选 | 仅明确看到一侧 | 两槽保留，缺项标记 |
| 弧线 Run / Sprint | 有候选 | 缺明确专用候选 | 保留槽；回退 Run 只能验证机制 |
| 180 折返 | 有单个候选，左右适用性未验 | 缺明确候选 | 左右状态保留，不默认镜像 Generic 骨架 |
| 90 度转身、Walk、专用加减速 | 缺明确候选 | 缺明确候选 | 保留状态/槽；暂用占位姿势或速度 Blend Tree |
| 靶向前后左右与斜向循环 | 缺明确候选 | 缺明确完整组 | 八方向槽齐全；缺项回退 Idle，不作为质量结果 |
| 拔武器 / 收武器、Guard/Charge hold | 缺明确完整候选 | 缺明确完整候选 | 动作槽保留；测试场景 F2 仅作即时切组调试 |
| 脚步接触、骨轴、Root Motion | 待制作/核验 | 待制作/核验 | 不自动猜测；由绑定与实测确认 |

LOD 模型缺少部分动画辅助节点，两套动画还存在父级路径差异；一次前缀替换不能保证完整通用。需要先审核主变形骨骼，再决定哪些辅助通道可以仅从副本剔除，最后检查同一模型上的武器、四肢与身体姿态。

拿到用户许可后的顺序：

1. 确认活动工程是本仓库 `Client`，版本 6000.3.24f1，保留已有未保存场景；先看导入和编译错误。
2. 导入本地参考包并检查材质/网格/Avatar；先审核一个 Idle 和一个 Run，不批量默认接受骨骼映射。
3. 为两种配置赋槽、配置腿链和接触曲线，再生成新 Controller。通过 Editor 检查入口后生成新的测试场景。
4. 测试场景是 **Additive** 创建，运行前卸载其他玩法场景，避免重复相机/AudioListener/物理；不改 Build Settings。斜坡与 0.15m 台阶用于 IK 检查。
5. 控制：WASD、Shift 跑速切换、Ctrl 步行、Tab 锁定、鼠标右键转相机；V 请求持握切换，F2 仅测试时强制切组；J/K 连段、Space 闪避、G 防御、L 技能、H 模拟受击、P 暂停规则/动画/角色移动及本动作粒子声音。
6. 按 30/60/120 fps 检查起停、加减速、弧线、90/180 转身、靶向横移后退、两种持握、坡面脚步、混合中受击、同动作重播的 A/B 淡出姿势、取消窗口、动作打断清理与根运动唯一写入；记录未补资源导致的表现缺口。
7. 仅在验收条件全部满足后关闭 `ANIM-002`。本阶段不需要占用 Max。

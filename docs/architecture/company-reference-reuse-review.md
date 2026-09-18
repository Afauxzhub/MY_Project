# 公司工程 3C 与 Timeline 技能方案复用评审

| 字段 | 内容 |
| --- | --- |
| 评审日期 | 2026-09-18 |
| 公司工程范围 | 主城角色移动、自由视角相机、技能 Timeline 编辑与运行链 |
| 个人仓库落地 | `com.afauxzhub.character-locomotion`、`com.afauxzhub.timeline-abilities` |
| 迁移原则 | 只迁移通用算法与架构思想，不迁移项目资产、业务类型、目录约定或第三方框架依赖 |

## 1. 主城移动现状

当前调用链是：

```text
Input System / Gamepad
  -> MainCityPlayer.ReadInput
  -> 相机 forward/right 转换世界目标方向
  -> 折返手势检测 + 输入来源分析
  -> 程序朝向求解与动态半径
  -> 弧线动作权重
  -> CityPlayer FSM / Animancer
  -> Root Motion 或程序方向驱动 AgentMove
  -> FreeLookCamera 自动跟随抑制
```

实现已经处理了不少真实问题：连续输入跨 180 度的转向符号、自动跟随与玩家转相机的反馈环、急转弯动作迟滞、折返过摇杆中心的确认窗、起跑/跑步/冲刺的脚步相位与 Root Motion 所有权。

但不适合整体搬用，原因是：

1. `MainCityPlayer` 同时负责输入、相机、网络同步、手势、朝向、动作参数和位移，职责过密。
2. 大量静态调参和调试项用于修补同一条耦合链，配置者很难知道参数属于轨迹、视觉还是状态切换。
3. FSM 直接依赖动画名和当前动画进度，新增多方向起步、小转向衔接或镜头模式时容易继续增加分支。
4. 程序轨迹、Root Motion 和动画 Mixer 共享控制权，必须靠很多条件决定本帧谁拥有位移与旋转。

## 2. 移动侧可复用内容

已经抽到个人包的部分：

- 相机相对输入到世界方向的纯函数。
- `速度 / 转弯半径 -> 角速度` 的曲率约束。
- 朝向误差追赶、角速度加减速与最大转速限制。
- 小转向动作进入/退出迟滞。
- 八方向起步意图分类。
- “数学求解只输出意图，不直接播放动作、不控制镜头”的职责边界。

没有迁移的部分：

- 主城网络上报、导航、对话、NPC或场景逻辑。
- SRDebugger 的大量静态调参入口。
- Animancer Mixer、动画资源名和公司角色资产。
- 公司 Input Action、Cinemachine 相机类、NavMeshAgent 和 Root Motion 接线。
- 当前折返 FSM 的具体状态与过渡补丁。

## 3. 个人项目移动架构建议

```text
输入适配器
  -> Camera-relative Intent
  -> Locomotion Brain（移动阶段与控制权）
      -> Heading Solver（纯数学）
      -> Motor（碰撞与实际位移）
      -> Animation Presenter（动作选择与混合）
      -> Camera Rig（跟随、自由转镜头、锁定模式）
```

后续增加功能时：

- 镜头控制只提供相机基向量、手动横转量和模式，不反向调用角色动画。
- 多方向起步读取 `StartDirection`，不在移动求解器里写动画名。
- 小转向衔接读取 `TurnIntent`、`YawRate`、`TurnBlend`，由 Presenter 决定播放独立过渡动作还是循环混合。
- Motor 是位移唯一所有者。Root Motion 先转换为位移请求，再交给 Motor 处理碰撞；不要让 Transform、Animator 和 CharacterController 同时写位置。
- 起步、持续移动、停止和折返属于移动阶段；左右弧线只是持续移动阶段的表现意图，不应膨胀成一组平行主状态。

## 4. 公司 Timeline 技能链现状

当前核心链路是：

```text
EditorSkillData 引用多个 TimelineAsset
  -> GameActionTrack / GameActionClip<T> 编辑运行数据
  -> 导出器把 Clip 起止时间和 RuntimeData 转为 TimelineClipConfig
  -> MemoryPack 写出纯运行时配置
  -> TimelineSystem 按时间调用 IGameAction Start / Update / Stop
```

最有价值的设计是“Timeline 只是编辑器，运行时执行的是编译后指令”。它避免让战斗逻辑依赖 `PlayableDirector`，也让事件型 Clip 与区间型 Clip 共享统一调度。

不适合搬用的部分：

- 角色/技能表、ECS、定点数、MemoryPack 和 PVE/PVP 业务范围。
- Odin 条件树、技能预览场景和 3000 多行专用编辑器窗口。
- 数量庞大的公司 GameAction、投射物、Buff、镜头和特效业务类型。
- 运行时配置中直接持有公司战斗上下文与 Entity 的接口。

## 5. 个人项目 Timeline 技能架构

个人包采用相同的关键思想，但缩成四层：

```text
AbilityAsset
  -> Timeline 上的语义 Clip
  -> AbilityPlanCompiler
  -> AbilityRuntimePlan
  -> AbilitySequencePlayer + 项目 IAbilityInstructionSink
```

Timeline 负责编排“什么时候发生什么”，战斗控制器负责“现在是否允许释放”：

- 黄色/灰色支付遵守 `SKILL-02`、`SKILL-03`。
- 连段内技能取消点晚于闪避和防御，遵守 `ATK-07`、`SKILL-05`。
- 技能不能解除受击僵直，遵守 `SKILL-06`、`HIT-02`。
- 动画与反击、命中、取消等玩法窗口分成独立 Clip，遵守集成契约的“表现帧与玩法判定帧可分离”。
- 技能联动状态不写进 Timeline 通用包，由战斗系统在成功命中或机制完成事件后处理，遵守 `SKILL-LINK-01` 至 `SKILL-LINK-05`。

## 6. 当前验证边界

- 已完成：源码调用链核对、去公司化设计、个人包文件静态检查。
- 尚未完成：个人 Unity 工程导入、程序集编译、Timeline 菜单与子资源生成、实际角色移动、动作混合、镜头联动和灰盒手感。
- 公司主城弧线跑文档自身也标记为仅完成 Unity 编译，快速键盘/摇杆/相机组合仍需实机验证，因此不能把现有效果当成已通过的个人项目基准。

# 第三人称移动框架边界

## 目标

第一阶段只建立可扩展的移动底座，不直接完成最终 3C。它需要支持后续加入：自由镜头、锁定镜头、多方向起步、小角度转向衔接、急转、停止和战斗移动覆盖。

## 控制权

每帧只允许一个 Motor 写角色的最终位置与旋转。输入、镜头、动作和 Root Motion 只能提交意图：

```text
InputSource -> DesiredDirection
CameraRig -> ReferenceAxes / CameraIntent
HeadingSolver -> SolvedDirection / YawRate
AnimationPresenter -> VisualPose / RootMotionRequest
Motor -> Collision-resolved Position and Rotation
```

## 稳定接口

- `CameraRelativeMovement`：把二维输入投影为水平世界方向。
- `HeadingSolver`：维护连续朝向并输出 `LocomotionIntent`。
- `LocomotionIntent.StartDirection`：八方向起步选择依据。
- `LocomotionIntent.Turn/YawRate/TurnBlend`：小转向或弧线循环的表现依据。
- `LocomotionProfile`：只保存移动意图与轨迹层参数；具体动作资产由 Presenter 配置。

## 初期底座顺序（历史记录）

1. 用胶囊体和占位动作接入 Motor，验证直跑、转向、停止。
2. 加入第三人称 CameraRig，分别测试玩家手动转镜头和自动跟随。
3. 接四方向或八方向起步动作，先验证输入方向选择，再处理脚步与 Root Motion。
4. 加小转向衔接动作，保持 Solver 不知道动作名。
5. 最后再实现急转/折返与跑步、冲刺之间的相位同步。

不要在第一版重新引入几十个暴露参数。每加入一个参数，都要明确它属于轨迹、动作表现、输入手势还是镜头，并给出独立验证场景。

## 当前移动动画范围（2026-10-15）

完整双姿态移动和跳跃采用无 Animator 连线的动作槽/衔接配方入口；具体职责、资产覆盖和播放适配见 [`animation-state-machine-architecture.md`](animation-state-machine-architecture.md) 第 0 节。当前实施顺序只维护在 [`tasks.md`](../project/tasks.md) 的 MOVE-002 至 MOVE-010，不继续按上面的早期底座顺序排期。

跳跃的垂直速度、重力、接地/顶碰和最终位移归 Motor；表现层只选择起跳/空中/落地动画。动态锁脚及滑步修正排在所有移动链连通之后最后实施，不使用 IK 补丁代替速度、步长和过渡相位的基础校准。

## 地形与连续输入约定（MOVE-012）

- Motor 在上一帧接地且未起跳时，允许一次有限距离的下探校正：下胶囊扫掠、排除自身/Trigger/忽略碰撞对象、只接受坡度限制内的表面，默认最大 0.35m。已经离开真实落边或正在上升时不吸回地面；查询饱和时不猜地面。这是根位置碰撞处理，不是脚 IK 或动态锁脚。
- 旧基础移动和动画移动统一经同一条 Motor 位移路径，避免两套重力/贴地行为。Velocity 取碰撞后的实际位移；顶碰清除上升速度。
- 离开平台时继承该帧碰撞后的水平速度，不沿用历史跳跃的速度。离地后的攻击权限在 Motor 完成帧立即关闭，避免输入先于 Driver.Update 时出现一帧漏洞；不添加空中攻击/二段跳许可。
- Lab 输入先采集为 LabInputFrame，再统一处理命令；回放通过同一适配器提交，不能直接写阶段。暂停命令先于同帧其他操作执行。物理键鼠/手柄采样仍是独立设备验收边界。
- 相机只发布朝向基向量；ApplyLook 统一限制俯仰/距离并把 yaw 归一到 ±180°。角色数学和动画选择不回写相机 yaw。
- 高频中断时最多保留 16 个淡出动画节点，超限只移除权重最小的旧节点，保留全部当前目标及独立时钟，并重新归一化。该防护不代表任意资源下的视觉过渡已调好。
- FrameCompleted 在角色 LateUpdate 完成后发布，即使战斗暂停也发布。机制验收以此采样，不能依赖会被暂停的动画求值事件推进测试。

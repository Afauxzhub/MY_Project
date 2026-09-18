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

## 后续实现顺序

1. 用胶囊体和占位动作接入 Motor，验证直跑、转向、停止。
2. 加入第三人称 CameraRig，分别测试玩家手动转镜头和自动跟随。
3. 接四方向或八方向起步动作，先验证输入方向选择，再处理脚步与 Root Motion。
4. 加小转向衔接动作，保持 Solver 不知道动作名。
5. 最后再实现急转/折返与跑步、冲刺之间的相位同步。

不要在第一版重新引入几十个暴露参数。每加入一个参数，都要明确它属于轨迹、动作表现、输入手势还是镜头，并给出独立验证场景。

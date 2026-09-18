# Afauxzhub Timeline Abilities

这个包把 Unity Timeline 当作“技能指令编辑界面”，而不是运行时状态机。

工作流：

1. 创建 `AbilityAsset` 和对应 `TimelineAsset`。
2. 在 `AbilityCommandTrack` 上放动画、判定窗口或语义事件 Clip。
3. 选中 `AbilityAsset`，执行 `Assets/Afauxzhub/Compile Timeline Ability`。
4. 编译结果写入 Ability 子资源 `AbilityRuntimePlan`。
5. 战斗控制器完成施法许可与资源支付后，再用 `AbilitySequencePlayer` 执行计划。

重要边界：

- Timeline 不判断黄色/灰色资源、不决定是否允许从受击僵直释放，也不自行修改技能联动状态。
- 动画时间与玩法窗口是独立 Clip；调整动画不应被迫改判定，反之亦然。
- `eventId`/`windowId` 是稳定语义契约；具体伤害、失衡、资源和目标选择交给运行时 Sink。
- 当前只提供最小骨架。命中盒、位移、镜头、特效和音频应通过新的语义 Clip 与项目适配器扩展，避免把业务系统引用塞进包内。

当前仅完成源码静态检查；需要在个人 Unity 工程中验证 Timeline 菜单、资产编译、重导入、取消和运行时事件顺序。

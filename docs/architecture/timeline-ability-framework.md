# Timeline 技能框架边界

## 原则

Timeline 是技能编排工具，不是玩家战斗状态机，也不是资源系统。

`AbilityPlanCompiler` 把编辑 Timeline 转为 `AbilityRuntimePlan`；运行时的 `AbilitySequencePlayer` 只按时间派发指令。项目通过 `IAbilityInstructionSink` 把语义指令接到动画、命中盒、位移、镜头、特效和战斗事件。

## 施法顺序

```text
输入请求
  -> CombatActionController 检查当前动作与取消优先级
  -> ResourceSystem 检查并支付黄色/灰色
  -> AbilitySequencePlayer.Play(compiledPlan)
  -> Sink 接收 Enter / Update / Exit
  -> 命中或机制成功事件反馈给资源、失衡和联动系统
```

对应规则：`SKILL-02`、`SKILL-03`、`SKILL-05`、`SKILL-06`、`ATK-07`、`HIT-02`。

## Clip 分类

- Animation：动画片段和播放参数，只负责表现请求。
- Window：攻击、反击、闪避/防御/技能取消、位移、无敌等有起止时间的玩法窗口。
- Event：伤害结算请求、特效、音效、镜头或自定义语义的瞬时事件。

事件 ID 和窗口 ID 必须稳定。运行时代码匹配语义 ID，不匹配 Timeline 轨道名或显示名。

## 明确禁止

- 不在 Timeline Clip 内直接判断或修改黄色、蓝色、灰色资源。
- 不用 Timeline 绕过受击僵直和取消优先级。
- 不把敌人引用、场景对象或当前战斗动态状态序列化进编译结果。
- 不让动画 Clip 的长度自动成为无法单独调整的判定窗口。
- 不把公司工程的 SkillData、ECS Entity、MemoryPack 或 GameAction 类型复制进个人包。

## 第一版扩展范围

按 `PROTO-01`，先只扩展一个基础伤害技能需要的语义：动画、攻击窗口、命中事件、取消窗口和后摇结束。资源事件、联动状态、复杂位移和镜头轨道等到基础战斗循环能运行后再加。

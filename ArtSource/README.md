# 美术制作源文件

Max、模型、绑定、贴图分层文件等放在此目录；Unity 工程是同级的 `Client/`。

先读 [资产制作与发布规范](../docs/production/asset-workflow.md) 和 [首个角色登记表](../docs/production/characters/Player.md)。

角色原画、四视图及生成记录放在 `Characters/<角色代号>/Design/`。主角当前版本入口为 [Player/Design](Characters/Player/Design/README.md)；后续新角色使用相同结构。原画版本子目录可以保留，正式模型与动画仍遵循稳定命名规则。

动画源文件示例：`Characters/Player/Animations/Locomotion/Player_Unarmed_Run.max`。

此例的正式 FBX 发布到 Unity 的 `Assets/Art/Animations/Player/Locomotion`。动作集不单独拆目录，其他武器的移动动画也可放在这里。制作端生成的临时 `FBX/`、`Autoback/`、`Backups/` 和 `Previews/` 不提交；不要把唯一源文件放在这些目录。

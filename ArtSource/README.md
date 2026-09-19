# 美术制作源文件

Max、模型、绑定、贴图分层文件等放在此目录；Unity 工程是同级的 `Client/`。

先读 [资产制作与发布规范](../docs/production/asset-workflow.md) 和 [首个角色登记表](../docs/production/characters/Player.md)。

动画源文件示例：`Characters/Player/Animations/Locomotion/Role_Player_LocomotionUnarmedRunForward.max`。

正式 FBX 发布到 Unity 的 `Assets/Art/Animations/Role/Role_Player`。制作端生成的临时 `FBX/`、`Autoback/`、`Backups/` 和 `Previews/` 不提交；不要把唯一源文件放在这些目录。

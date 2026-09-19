# MY_Project Unity Client

这是 `MY_Project` 的 Unity 工程根目录。

## 打开工程

- Unity 版本：6000.3.24f1（Unity 6.3 LTS）。
- 在 Unity Hub 中添加并打开本目录：`MY_Project/Client`。
- 换电脑时以 `ProjectSettings/ProjectVersion.txt` 为准确版本依据，不要让 Hub 自动升级工程。

Unity Editor 安装目录属于本机工具配置，不放入仓库。当前电脑使用：

`E:/GameDev/UnityEditors/6000.3.24f1/Editor/Unity.exe`

## 本地包

`Packages/manifest.json` 通过相对路径引用仓库根目录 `packages/` 下的三个包：

- `com.afauxzhub.animation-pipeline`
- `com.afauxzhub.character-locomotion`
- `com.afauxzhub.timeline-abilities`

不要把这些依赖改成本机绝对路径。

## 基线验证

打开菜单：

`Tools > MY Project > Create or Validate Baseline`

验证会确认三个本地包已经注册，创建或重新打开 `Assets/Scenes/Bootstrap.unity`，并确保该场景已加入 Build Settings。

编辑器缓存与本机设置目录（如 `Library/`、`Temp/`、`Logs/` 和 `UserSettings/`）由根目录 `.gitignore` 排除，不应提交。

## 移动灰盒

打开菜单：

`Tools > MY Project > Create or Validate Locomotion Greybox`

工具会确定性重建 `Assets/Scenes/LocomotionGreybox.unity`、创建灰盒移动配置，并验证玩家、相机、地面、障碍和适配器接线。Play Mode 中使用 `WASD` 或方向键移动；选中 `Player` 可在 Inspector 观察输入、目标方向、求解方向、偏航速度和转向意图，并在 Scene 视图看到青色目标方向与黄色求解方向 Gizmo。

该场景只验证胶囊体程序移动。速度、转向和镜头偏移均为灰盒值，不代表最终手感。

## 个人资产制作

目录、命名、LFS 和发布规范见 [`../docs/production/asset-workflow.md`](../docs/production/asset-workflow.md)；角色骨架信息见 [`../docs/production/characters/Player.md`](../docs/production/characters/Player.md)。

运行 `Tools > MY Project > Validate Asset Workflow` 可检查目录和共享配置，不会修改当前场景。已按用户确认将 Root / Motion 节点设为 `Root` 并启用自动提取 `.anim`；曲线优化和 FBX 动画压缩暂时关闭，保留首条动画的数据检查基线。这只完成导入配置，真实根运动和重复发布引用仍待首条 FBX 验收。设置入口为 `Tools > Animation Pipeline > Settings`。

本机 Max 发布工具的 Unity 路径需指向这个工程的 `Client/Assets`。共享配置使用相对路径，个人 `rm_config.json` 不提交。

新动画使用 `Player_Unarmed_Run` 等短名称，后续按实际武器动作集扩展。个人短命名的 `.anim` 镜像 FBX 子目录，旧格式保持原分组。运行 `Tools > MY Project > Validate Animation Naming` 可验证双端共享样例及导出路径；真实 FBX 与根运动仍另行验收。

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

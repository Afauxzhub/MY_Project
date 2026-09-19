# 个人项目资产制作与发布规范

状态：用户于 2026-09-20 采纳；本文件是目录、命名和资产管理的权威规范。

## 1. 单一来源与目录

| 内容 | 目录 | 谁修改 / 版本管理 |
| --- | --- | --- |
| 模型、绑定、动画、贴图的制作源文件 | `ArtSource/Characters/<角色代号>/Model`、`Rig`、`Animations`、`Textures` | 制作端；大型二进制 Git LFS |
| 场景、UI、声音制作源文件 | `ArtSource/Environments`、`UI`、`Audio` | 制作端；大型二进制 Git LFS |
| 发布的角色模型、材质、运行贴图 | `Client/Assets/Art/Characters/<角色代号>/Models`、`Materials`、`Textures` | 发布文件 + Unity 材质；保留 `.meta` |
| 发布的动画 FBX | `Client/Assets/Art/Animations/<分类目录>/<分类>_<角色代号>` | Max 发布；Git LFS + `.meta` |
| 提取的动画 | `Client/Assets/Generated/AnimationClips/<分类>_<角色代号>` | Unity 导出工具；`.anim` + `.meta` 提交 |
| 手工 Animator、Mask、Unity 原生动画 | `Client/Assets/Animations` | Unity 手工维护，禁止放到生成目录 |
| 动作定义、脚步接触元数据、移动/战斗配置 | `Client/Assets/GameData` | 项目数据，独立于生成动画 |
| 项目脚本 / 编辑器工具 | `Client/Assets/Scripts` / `Editor` | 普通 Git |
| Prefab / 场景 / 第三方内容 | `Client/Assets/Prefabs` / `Scenes` / `ThirdParty` | 保留依赖、`.meta` 和第三方许可 |
| 可复用包 / Max 工具源码 | 根目录 `packages/` / `tools/` | 不混入个人角色资产 |
| 构建结果 / 自动备份 / 临时导出 | `Builds/`、制作端备份、`ArtSource/**/FBX/` | 不提交；备份另行保存 |

Unity 只打开 `Client/`。日常制作使用主工程的 `ArtSource/` 和 `Client/`，两者应来自同一份检出；工具里的本机绝对路径指向实际使用的工程，不指向临时任务工作树。源文件不放进 `Client/Assets`，避免依赖 Max 的自动导入。

目录按需要增补。既有 `Assets/Locomotion` 灰盒配置继续有效，本次不移动已引用资产；新的动作数据放在 `GameData/Locomotion`。

## 2. 命名与 Max 兼容协议

正式动作资产使用 ASCII 字母与数字，以 `_` 分字段：

```text
<分类>_<角色代号>_<动作ID>
Role_Player_LocomotionUnarmedRunForward
Role_Player_LocomotionUnarmedStopPlantL
Role_Player_LocomotionUnarmedPivot180TurnRPlantL
Role_Player_LocomotionArmedIdle
```

- `Role` 是现有发布工具的分类；其他分类沿用工具已有白名单。
- `Player` 是首个角色的稳定技术代号，用户已确认；不随显示名称改变。
- 第三段合并用途、持物姿态与动作，例如 `LocomotionUnarmedRunForward`，内部不加下划线，避免被旧解析器误认为制作阶段。
- `Unarmed` 表示空手 / 武器收纳状态；`Armed` 表示手持武器状态。首轮只做 `Unarmed`，后续两套移动与待机分别命名。武器收纳 / 取出是切换动作，不与空手待机混为一项；具体武器分类后续再补。
- `TurnL/TurnR` 表示向左/右转，`PlantL/PlantR` 表示进入动作时左/右支撑脚，左右以角色自身为准。
- 正式输出保持同名；工作版本由 Git 保存，不在发布名称追加日期、`Final`、`V003`。
- 前期一个动作一个 Max 文件、一个 FBX 一个 Clip；模型 FBX 与动画 FBX 分开。
- FBX 文件基名在动画来源目录内必须唯一，不能依靠子目录区分同名动作。

实际示例（均从仓库根目录算起）：

```text
ArtSource/Characters/Player/Animations/Locomotion/Role_Player_LocomotionUnarmedRunForward.max
Client/Assets/Art/Animations/Role/Role_Player/Role_Player_LocomotionUnarmedRunForward.fbx
Client/Assets/Generated/AnimationClips/Role_Player/Role_Player_LocomotionUnarmedRunForward.anim
```

这是核对现有 Max `validate_indoor_name`、`get_unity_indoor_path` 与 Unity `BuildOutputFolder` 后选定的实际协议，替代讨论阶段的 `Player_Locomotion_RunForward` 示例。Unity 按文件名前两段分组，不镜像 FBX 子目录。多 Clip 会追加 Clip 名；要启用这种用法先明确映射及重命名规则。

## 3. 资产权威来源

- 姿态、根轨迹：Max；FBX 是发布接口，`.anim` 是其派生结果。
- 导入参数：共享 `Client/ProjectSettings/AfauxzhubAnimationPipelineSettings.asset` 和 FBX `.meta`。
- 状态选择、衔接区间、脚步标记、允许的时间/轨迹修正：独立项目动作数据。若改为制作端导出接触曲线，须指定其为权威来源，不再同时手工维护同一字段。
- 不在生成 `.anim` 内保存唯一一份手工事件或曲线修改，下一次发布会覆盖。
- 骨架拓扑、骨骼路径、比例和参考姿势见角色登记表；不能未经资产迁移直接更名。

## 4. 本项目共享导入配置

| 项目 | 当前配置 |
| --- | --- |
| FBX 来源 | `Assets/Art/Animations` |
| `.anim` 输出 | `Assets/Generated/AnimationClips` |
| 分组 | 文件名前两段 |
| 动画类型 | 沿用现有工具的 Generic |
| 曲线优化 | 关闭，先保留数据检查基线 |
| Unity 动画压缩 | Off，先检查原始轨迹 |
| 自动导出 | 开启，导入来源目录内的 FBX 后自动提取 `.anim` |
| Root / Motion 节点 | 均为 `Root`，用户确认，大小写固定 |

入口：`Tools > Animation Pipeline > Settings`。上述配置随仓库保存，不必每次重新设置。首次只发布一条实际动作，检查根位移、旋转、时长和脚步，再批量发布。节点名称已确认不等于已核对 FBX 导出层级；不要仅因自动提取成功就认定 Root Motion 正确。

`Tools > MY Project > Validate Asset Workflow` 检查目录、共享配置、命名和输出碰撞，不改场景、不重建已有动画。还没有 FBX 时，检查可以通过，但日志会明确提示真实骨架 / 动画仍需单独验收。

## 5. Max 工作机设置

可复用源码仍在 `tools/max-animation-tools`，安装版只是运行副本。真实 `rm_config.json` 是机器配置，不提交。

- `unity_root` 选择正在工作的 `Client/Assets`，不是仓库根、也不是仅 `Client`。
- 自动复制 FBX 可开启；NAS 自动备份保持关闭，使用自己的版本控制和独立备份。
- 分类目录使用现有 `Role → Role` 等映射，以保持本文输出路径成立。
- Max 2020 / Biped / 独立 `Root` 已确认；Root/Bip/导出骨架选择仍需结合登记表和实际文件在 Max 内核对。工具对部分 Biped/蒙皮结构有专门处理，不能只凭名称承诺实际层级直接兼容。
- 本机路径不写入通用包、提交的示例或角色登记表。换电脑只需要设置机器位置，不重定命名和目录协议。

共享 Unity 配置已随工程准备，安装版 Max 的个人配置不由此自动改写。首次工作机只需选定本机工程路径并核对导出节点，真实发布按 ANIM-001 验证；之后无需重复建立目录或规范。

## 6. Git 与备份

- `.gitattributes` 定义 Max、FBX、PSD、贴图、音视频等二进制的 LFS 规则，大小写扩展名均覆盖。
- 每台电脑执行 `git lfs install --local`，拉取资产执行 `git lfs pull`；仓库配置跟随检出，本机 LFS 过滤器/钩子需初始化。
- `.meta`、文本 `.anim`、Prefab、场景、Controller、Mask 和配置使用普通 Git。特别大的 `.anim` 再讨论精确路径的 LFS 规则，不把所有 `.asset` 一并二进制化。
- 发布 FBX、生成 `.anim` 及各自 `.meta` 在同次提交里保持一致；更改制作源文件时一起记录，或在提交说明明确尚未发布。
- 在 Unity 内移动/重命名资产，保留 `.meta`。不要通过删除重建来“刷新”动画。
- `Generated` 表示写入者是工具，不表示该目录可以整体忽略；当前 `.anim` 和 `.meta` 必须提交，避免重新生成 GUID 后引用断裂。
- 自动备份、临时 `FBX` 目录、预览、日志、`Library/Temp` 与构建结果忽略。Git/LFS 历史也不替代独立备份；切换电脑前完成正式提交与同步。
- 第三方资产按许可管理；只提交自己的或明确有权使用的内容。

## 7. 打包与后续验收

当前通过场景、Prefab、动作配置引用资产；不建立 `Bundle`/`Dependencies` 的自定义打包体系。需要分包或内容更新时再建立 Addressables/AssetBundle 配置，磁盘目录不等于进包规则。

首条真实动画验收：Max 打开源文件 → 发布 FBX → Unity 提取 `.anim` → 验证根位移/旋转和姿态 → 修改源文件再发布 → 确认 `.anim` GUID、Prefab/Controller 引用不变。包含从 LFS 拉取后重新打开工程的检查。此次工程设置验证不代替这条链路。

## 变更记录

| 日期 | 内容 |
| --- | --- |
| 2026-09-20 | 采纳源文件/发布 FBX/生成动画分层；核对两端命名协议；建立共享配置和 LFS；确认 Player、Max 2020、Biped、Root、首轮 Unarmed / 后续 Armed，真实导出层级待首条 FBX 核对 |

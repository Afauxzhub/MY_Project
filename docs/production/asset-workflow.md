# 个人项目资产制作与发布规范

状态：用户于 2026-09-20 采纳；本文件是目录、命名和资产管理的权威规范。

## 1. 单一来源与目录

| 内容 | 目录 | 谁修改 / 版本管理 |
| --- | --- | --- |
| 模型、绑定、动画、贴图的制作源文件 | `ArtSource/Characters/<角色代号>/Model`、`Rig`、`Animations`、`Textures` | 制作端；大型二进制 Git LFS |
| 场景、UI、声音制作源文件 | `ArtSource/Environments`、`UI`、`Audio` | 制作端；大型二进制 Git LFS |
| 发布的角色模型、材质、运行贴图 | `Client/Assets/Art/Characters/<角色代号>/Models`、`Materials`、`Textures` | 发布文件 + Unity 材质；保留 `.meta` |
| 发布的动画 FBX | `Client/Assets/Art/Animations/<角色代号>/<用途分类>` | Max 发布；Git LFS + `.meta` |
| 提取的动画 | `Client/Assets/Generated/AnimationClips/<角色代号>/<用途分类>` | Unity 镜像 FBX 子目录；`.anim` + `.meta` 提交 |
| 手工 Animator、Mask、Unity 原生动画 | `Client/Assets/Animations` | Unity 手工维护，禁止放到生成目录 |
| 动作定义、脚步接触元数据、移动/战斗配置 | `Client/Assets/GameData` | 项目数据，独立于生成动画 |
| 项目脚本 / 编辑器工具 | `Client/Assets/Scripts` / `Editor` | 普通 Git |
| Prefab / 场景 / 第三方内容 | `Client/Assets/Prefabs` / `Scenes` / `ThirdParty` | 保留依赖、`.meta` 和第三方许可 |
| 可复用包 / Max 工具源码 | 根目录 `packages/` / `tools/` | 不混入个人角色资产 |
| 构建结果 / 自动备份 / 临时导出 | `Builds/`、制作端备份、`ArtSource/**/FBX/` | 不提交；备份另行保存 |

Unity 只打开 `Client/`。日常制作使用主工程的 `ArtSource/` 和 `Client/`，两者应来自同一份检出；工具里的本机绝对路径指向实际使用的工程，不指向临时任务工作树。源文件不放进 `Client/Assets`，避免依赖 Max 的自动导入。

目录按需要增补。既有 `Assets/Locomotion` 灰盒配置继续有效，本次不移动已引用资产；新的动作数据放在 `GameData/Locomotion`。

## 2. 个人短命名与旧格式兼容

正式动作资产使用 ASCII 字母与数字，以 `_` 分字段：

```text
<角色代号>_<动作集>_<动作>
Player_Unarmed_Run
Player_Unarmed_Idle
Player_Sword_Idle
Wolf_Run
```

- 不再强制 `Role` 前缀；主角、怪物和 NPC 使用稳定角色 / 类型代号，不使用场景实例编号。
- `Player` 是首个角色的稳定技术代号，用户已确认；不随显示名称改变。
- 动作集与动作是独立字段；没有多套动作的角色可以省略动作集，形成 `Wolf_Run`。只允许 2 或 3 段，每段以大写 ASCII 字母开头，只含字母数字。
- 首轮动作集为 `Unarmed`，后续按实际武器动作体系命名，不采用笼统 `Armed`；`Sword` / `Spear` 仅为示例，不代表武器设计已确认。多把武器可引用同一动作集；装备实例、动作集与持握状态分开。
- 收纳后姿态相同可以共用 `Unarmed`；收纳 / 取出是独立切换动作，不与空手待机混为一项。动作集不等于战斗状态。
- `Locomotion` 等用途留在目录中，不进入动作字段。目录用于整理，状态选择由配置显式引用动画，不能仅靠文件夹推断状态机。不同动作集的待机可以放在同一目录。
- `TurnL/TurnR` 表示向左/右转，`PlantL/PlantR` 表示进入动作时左/右支撑脚，左右以角色自身为准。
- 正式输出保持同名；个人模式的制作阶段 / 工作版本由 Git 保存，不在名称或目录追加 `Final`、`V003`、初版 / 终版。可用 `Idle02` 标记真正不同的动作变体，而不是制作版本。
- 前期一个动作一个 Max 文件、一个 FBX 一个 Clip；模型 FBX 与动画 FBX 分开。
- FBX 文件基名在动画来源目录内必须唯一，不能依靠子目录区分同名动作。

实际示例（均从仓库根目录算起）：

```text
ArtSource/Characters/Player/Animations/Locomotion/Player_Unarmed_Run.max
Client/Assets/Art/Animations/Player/Locomotion/Player_Unarmed_Run.fbx
Client/Assets/Generated/AnimationClips/Player/Locomotion/Player_Unarmed_Run.anim
```

用途分类为 `Locomotion`、`Attacks`、`Reactions`、`Interactions`、`Common`。Max 从源文件路径中的 `Animations/<用途分类>` 读取分类，名称中的动作集不参与目录分组；路径未包含这些明确分类时进入 `Common`，不通过 Run/Idle 等词猜测。Unity 对短命名镜像 FBX 相对来源根的子目录，Max 定位到同一路径。

新建面板默认“个人短命名”，动作集可留空，绑定可从个人 `Rig` 目录发现或手动选择任意 `.max`。个人模式首版采用一源文件、一动画 FBX、一 Clip；开启分段或相机导出时会在导出前明确阻止，避免产生未定义名称。分段动作暂时分别制作 `RunStart`、`RunStop` 等源文件，不静默改名。

兼容边界：旧 `Role_Player_Run(_Start)` 等分类格式和局外 / 过场格式保持原路径及解析；旧格式仍按文件名前两段输出，不批量迁移或重命名现有素材。`Role/Monster/Elite/Boss/Npc/Scene` 和已有过场前缀为保留前缀，不作为新角色代号。新格式不做旧公盘阶段确认和自动备份，旧设置不被改写。

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
| 分组 | 个人短命名镜像 FBX 子目录；旧格式保留文件名前两段分组 |
| 动画类型 | 沿用现有工具的 Generic |
| 曲线优化 | 关闭，先保留数据检查基线 |
| Unity 动画压缩 | Off，先检查原始轨迹 |
| 自动导出 | 开启，导入来源目录内的 FBX 后自动提取 `.anim` |
| Root / Motion 节点 | 均为 `Root`，用户确认，大小写固定 |

入口：`Tools > Animation Pipeline > Settings`。上述配置随仓库保存，不必每次重新设置。首次只发布一条实际动作，检查根位移、旋转、时长和脚步，再批量发布。节点名称已确认不等于已核对 FBX 导出层级；不要仅因自动提取成功就认定 Root Motion 正确。

`Tools > MY Project > Validate Asset Workflow` 检查目录、共享配置、命名和输出碰撞，不改场景、不重建已有动画。还没有 FBX 时，检查可以通过，但日志会明确提示真实骨架 / 动画仍需单独验收。

`Tools > MY Project > Validate Animation Naming` 使用与 Max 共用的 `tests/fixtures/animation-naming.json`，验证新名称、非法名称、不同动作集同目录、真实导出器路径及旧格式回退；不创建正式动画。

## 5. Max 工作机设置

可复用源码仍在 `tools/max-animation-tools`，安装版只是运行副本。真实 `rm_config.json` 是机器配置，不提交。

- `unity_root` 选择正在工作的 `Client/Assets`，不是仓库根、也不是仅 `Client`。
- 自动复制 FBX 可开启；NAS 自动备份保持关闭，使用自己的版本控制和独立备份。
- 分类映射 `Role → Role` 等只影响旧格式。个人短命名按角色与用途分类发布，Unity 需启用“个人短命名镜像 FBX 子目录”。
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
| 2026-09-20 | 用户修订：取消新资产的 Role / Locomotion 长命名，动作集独立、后续按武器类型扩展，不采用泛化 Armed；双端短命名适配由 ASSET-002 实施 |

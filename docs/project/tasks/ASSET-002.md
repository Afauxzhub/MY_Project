# ASSET-002：个人动画短命名与双端发布适配

| 字段 | 内容 |
| --- | --- |
| 状态 | Awaiting Runtime Validation |
| 类型 | 工具开发 / 本机部署 |
| 里程碑 | M1 |
| 负责人 | 当前主任务 Agent |
| 创建日期 | 2026-09-20 |
| 最近更新 | 2026-09-20 |

## 目标与范围

将用户确认的 `Player_Unarmed_Run` / 按武器类型区分动作集的短命名用于 Max 新建、校验、发布及 Unity 提取，并部署到用户已安装的 Max 脚本目录。

- 新格式为角色、可选动作集、动作；不要求 Role、Locomotion 或制作阶段进入正式资产名。
- 区分文件整理与运行时状态，不生成战斗状态机、不制作动画、不迁移用户现有素材。
- 保持 Max 2020 / Python 2.7 / PySide2 兼容；保留旧格式及局外发布的兼容边界。
- 仓库源码先改，再备份并同步安装副本；不覆盖个人配置，不把本机路径提交进通用工具。

## 权威依据与依赖

- `docs/production/asset-workflow.md`、`docs/production/characters/Player.md`（本任务同步用户新决定）。
- `docs/tools/animation-tools-porting.md`；两端源码 `tools/max-animation-tools` 和 `packages/com.afauxzhub.animation-pipeline`。
- ASSET-001；用户已明确授权工具适配与本机安装目录更新。

## 验收条件

- [x] Max 新建、重命名、发布采用同一短命名解析；Unarmed / 不同武器动作集不会混淆；旧格式与局外流程回归检查通过。
- [x] Max 发布 / 定位与 Unity `.anim` 输出映射一致；同名冲突、非法名称被检查。
- [x] Unity 编译与项目验证通过；跨端命名 / 路径测试通过，检查 Python 2.7 兼容。
- [x] 本机 Max 安装目录已核实、改动已备份并同步，部署文件与源码哈希一致；个人配置保留。
- [x] 规范、角色登记、任务索引与总览更新，主工程同步且用户场景 / 素材保持原样。
- [ ] 真实 Max 新建与导出、Unity 首条 FBX 根运动及再次发布引用验收通过；未执行时标记 Awaiting Runtime Validation。

## 验证与交接

- 实施前已核对工作树干净；主工程有用户场景修改与未跟踪素材，不纳入本任务。
- 静态测试和安装目录同步不替代 Max 内实际导出与动画表现验收。
- 已完成：短命名解析、个人新建面板、重命名提示、发布路由、定位路径、Unity 目录镜像、规范与共用测试样例。
- 已验证：Python 纯函数与新建 / 发布阶段 / 发布历史回归；Unity 6000.3.24f1 编译与实际导出器路径检查；Max 2020 Python 2.7.15 / PySide2 新建与重命名面板测试。
- 测试证据：`Client/Logs/asset-002-naming.log`、`.validation-temp/asset-002-max-smoke.result`（均为本机忽略文件）。第一次 Max 测试入口因编码声明失败，改为 ASCII 入口后进程退出码 0；工具模块未发生该编码问题。
- 安装目录已经核实；安装器 SourceRoot 指向日常主工程，AutoSyncOnOpen 开启。因此必须先同步主工程源码，再同步安装副本，防止启动时回退。
- 已部署：9 个文件同步到 `%LOCALAPPDATA%/Autodesk/3dsMax/2020 - 64bit/CHS/scripts/AnimationTools`，与主工程源码 SHA256 一致；1 份既有配置保持不变。原先没有 `RootMotionTool/config/rm_config.json`，已仅在本机初始化个人 Unity Assets 路径及自动复制 / 关闭 NAS，未提交该配置。
- 安装备份：同级 `AnimationToolsBackups/ASSET-002-504c3ae98dcd48209d53d8d5f02a5b50`，保留被替换前的文件，没有删除用户数据。
- 安装副本验证：直接用安装目录的 `validation/validate_personal_naming_max.py` 在 Max 2020 批处理运行；共用命名样例、目录推导、动作集切换、旧模式切换、非法名称、重命名按钮和局内 / 过场识别均通过，进程退出码 0。报告 `.validation-temp/asset-002-installed-max.result`，Listener 日志 `.validation-temp/asset-002-installed-max.log`。这不是实际骨架导出验收。
- 主工程保护：既有 `LocomotionGreybox.unity` 的 SHA256 前后相同，`ArtSource/Character/` 中用户素材未移动 / 提交。
- 下一步：关闭并重新打开 Max 工具窗口；用个人绑定创建 `Player_Unarmed_Run.max`，完成首条 Root Motion 动画后执行真实 FBX 发布及再次发布引用验收。运行菜单 `Tools > MY Project > Validate Animation Naming` 可重跑 Unity 检查。
- 相关提交：实现工作树 `3753ab0`，主工程 `b3b3792`；部署记录随后单独提交，未推送远端。
- 运行边界：个人短命名首版仅单动作 FBX，分段 / 相机导出在导出前明确阻止；旧格式流程保持。真实动画制作和根运动验收仍待首条资产。

# ASSET-001：建立个人资产目录与可恢复的动画发布配置

| 字段 | 内容 |
| --- | --- |
| 状态 | Done |
| 类型 | 工程基础 / 工具配置 |
| 里程碑 | M1：玩家战斗最小灰盒 |
| 负责人 | 当前主任务 Agent |
| 创建日期 | 2026-09-20 |
| 最近更新 | 2026-09-20 |

## 目标

将用户采纳的 Max → FBX → Unity `.anim` 资产管理方案落入版本库，使目录、命名、Git LFS 和 Unity 导入策略能够随工程恢复。

## 范围

- 建立个人美术源文件与 Unity 资产目录、命名和单一权威来源规范。
- 调整原工具迁移阶段的资产提交限制，允许个人项目资产进入指定目录。
- 配置 Git LFS、临时文件忽略、共享 Unity 动画导入设置和可重复检查入口。
- 记录已确认的 Player / Max 2020 / Biped / Root / 首轮 Unarmed，预留 Armed；其余骨架事实由首条 FBX 核对，不批量迁移旧资产。
- 本任务不制作动画、不替代真实 Max 发布验收；实际发布链保留在 ANIM-001。

## 权威依据

- `AGENTS.md`
- `docs/tools/animation-tools-porting.md`
- `docs/production/asset-workflow.md`（本任务建立的资产流程权威文档）
- `packages/com.afauxzhub.animation-pipeline/Editor/`
- `tools/max-animation-tools/RootMotionTool/pipeline/rm_naming.py`、`rm_file_io.py`

## 依赖

- [x] UNITY-001 工程与包导入基线完成。
- [x] 用户采纳同仓资产管理方案，授权建立目录、配置并记录规范。
- [x] Git LFS 已安装；本机 Unity 为 6000.3.24f1。
- 骨架、首个动画与真实 Max 操作不属于本任务完成前置条件。

## 验收条件

- [x] 源文件、FBX、生成动画、手工配置、代码、缓存各有明确目录与写入职责。
- [x] 个人资产可按修订规则提交，临时文件和工具个人设置被忽略。
- [x] 大型二进制文件匹配 LFS，`.meta` 和 Unity 文本资产继续由普通 Git 追踪。
- [x] 共享导入配置随仓库存储并由 Unity 正确读取，目录检查工具不重建用户场景。
- [x] 命名示例通过现有 Max 命名校验，Max 和 Unity 的输出分组一致。
- [x] Unity 编译、配置检查、Git 差异检查通过；记录未执行的真实资产验证。
- [x] 总览、索引、交接记录同步；本任务提交并同步主工程，保留已有场景改动。

## 验证记录

| 日期 | 环境 | 检查 | 结果 | 证据/备注 |
| --- | --- | --- | --- | --- |
| 2026-09-20 | Unity 6000.3.24f1 / 当前工作树 | 编译并执行 `AssetWorkflowValidation.Validate` | PASS | `Client/Logs/asset-001-validation.log`；0 个真实 FBX；配置读取为 Root / 自动提取开启 / 压缩与曲线优化关闭 |
| 2026-09-20 | Unity 6000.3.24f1 / 重新打开 | 再次执行只读目录与配置检查 | PASS | `Client/Logs/asset-001-reopen.log`；进程退出码 0；没有重建或修改移动场景 |
| 2026-09-20 | 本机 Python / Max 工具源码 | 6 个 Unarmed/Armed 名称、清理规则、FBX 路由及 `.anim` 分组 | PASS | 调用实际 `rm_naming` / `rm_file_io` 纯函数；不等于 Max 2020 运行验收 |
| 2026-09-20 | Git LFS 3.7.1 | 本机初始化、大小写扩展名、文本资产与忽略规则 | PASS | `git lfs install --local`、`git check-attr`、`git check-ignore`；尚无真实 LFS 资产拉取测试 |
| 2026-09-20 | Git | `git diff --check`、场景变更检查 | PASS | 工作树现有场景无变更；主工程已有场景修改继续保留 |
| 2026-09-20 | 主工程 | 同步实现提交并复核用户文件 | PASS | 主工程提交 `2b0f56c`；已有移动场景 SHA256 前后一致；用户新放入的 `ArtSource/Character/` 保持原样，未移动或纳入本次提交 |

## 交接

- 已完成：目录与规范、角色登记、Git LFS、共享 Unity 导入配置、只读检查菜单；保留包对其他工程的默认设置。
- 尚未验证：Max 安装版的本机路径 / 导出节点、真实骨架与首条 FBX 根运动、重复发布保留引用、LFS 跨机拉取。这些由 ANIM-001 承接；本次无角色或动画素材，未声称完成制作链验收。
- 下一步：制作 `Role_Player_LocomotionUnarmedRunForward.max` 测试动画，首次发布核对 `Root` 的真实导出路径、比例、轨迹及脚部接触。
- 目录提醒：正式规范为 `ArtSource/Characters/`（复数）。主工程中新出现的 `ArtSource/Character/` 内容未核对来源 / 许可和用途，不自动迁移或提交。
- 相关提交：实现工作树 `b3ee4be`；已同步主工程 `2b0f56c`。任务完成记录随后单独提交；未推送远端。

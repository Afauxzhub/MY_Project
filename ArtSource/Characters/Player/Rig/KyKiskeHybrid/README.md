# Ky Kiske · Biped 混合绑定试版

入口：`Player_BipedRig.max`，使用 **3ds Max 2020**。这是供试动画和修改变形的第一版，用户的动画手感验收与 Unity 发布验收仍待完成。原始 `1.max` 保持不变。

远端交付边界（2026-10-16）：本次上传本目录的制作脚本与说明；第三方原模型、贴图及其派生 MAX/BIP/FIG 尚无仓库分发授权确认，保留本地，不随此批推送。上文入口描述本机已有成果，并不表示从 Git 克隆后已包含模型文件；取得合法素材后再按绑定任务记录补齐。

## 开始制作动画

1. 打开 `Player_BipedRig.max`，为具体动作另存一份 `.max`。
2. 通过 **Scripting → Run Script** 运行同目录的 `RigTools.ms`，打开控制面板。绑定关系已保存在场景里；不打开面板也能控制骨架。
3. 身体、头部、双手和手指用 `Bip001` 系列节点制作动画。独立的黄色 `Root` 控制整套角色的位移与朝向。
4. 面板的 `Extra controls` 可显示 Face、Hair、Cloth 或 Correctives 控制组；附加控制使用普通关键帧。原变形骨位于隐藏且冻结的 `Deform` 层。
5. `Select face settings` 选择 `CTRL_FaceSettings`，在修改面板调整左右眨眼、视线和张口参数，开启 Auto Key 可记录参数动画。

`Key selected extras to rest here` 会在当前帧给所选附加控制器写入参考姿势，不会清除已有动画。面部参数需单独归零。

## 本版结构

- 角色参考高度 1.8 米；Max 系统单位为米，显示单位为厘米。
- 原 609 根变形骨保留原层级，去掉名称的 `G_` 前缀。网格的 44,326 个顶点及原 Skin 影响骨、权重、DQ 权重按顶点还原，没有自动重新分配权重。
- `Bip001 Head` 驱动正确的 `Head_Attach`。原 `head_root` 的偏移继续保留，不把它当作头部控制点。
- 披风、头发、衣领、腰带与脸部保留可编辑 FK 控制；前臂、肩、肘、膝、踝、颈有基础自动跟随。此版没有布料动力学，也没有完整表情预设库。
- `Root → body_root → pelvis → …` 是变形/导出层级；Biped 是动画控制层。原骨盆与 Bip 骨盆的参考位置存在有意保留的偏移。
- `Player_Reference.bip` 只保存 Biped 参考动作，`Player_Reference.fig` 保存 Biped 体型。**完整动作请保存 `.max`**，单独 `.bip` 不包含 Root、面部、头发、衣服等附加控制动画。

## 此版动画 FBX 导出

本目录的 `ExportAnimation.ms` 提供一个独立导出函数。现有动画发布工具尚未适配这套骨架的识别规则，因此首版先用这个入口验证。

在 Max 中运行 `ExportAnimation.ms` 后，在 Listener 调用：

```maxscript
KYExportAnimation "D:/your-output/Player_Unarmed_Test.fbx" 0 60
```

输出目录需已存在。该函数逐帧烘焙 `Root` 与 609 根原变形骨，排除 Biped、控制器和网格，供动画测试。它使用 Y-up、米单位，并对烘焙骨架与源骨架的矩阵误差做检查。回读 Max 时需要启用单位转换，目标单位设为米；不要沿用本机不明的导入倍率。首次导入 Unity 时仍需核对单位、朝向、层级、根运动和动画播放。

本版不自动从 Bip COM 提取 Root Motion；需要根位移时直接给 `Root` 制作动画。模型和蒙皮 FBX 发布、旧工具的一键发布、Unity Generic Avatar 兼容性属于后续集成范围。

## 重建与验证

`BuildRig.ms` 与 `AddControls.ms` 是本资产专用的构建脚本。只在独立 Max 会话加载原始 `1.max` 后运行 `BuildRig.ms`；它拒绝覆盖已存在的 `Player_BipedRig.max`。请先保留已有成果再重建。

构建及测试中间文件位于仓库的 `.validation-temp/ky-rig-build/`，不进入资产交付。正式验证结论与未完成项见 [RIG-002](../../../../../docs/project/tasks/RIG-002.md)。贴图继续引用原 Ky Kiske 素材目录，移动资产时请同时保留原贴图。

# 动画工具迁移与维护说明

## 存放位置

- Max：`tools/max-animation-tools`
- Unity：`packages/com.afauxzhub.animation-pipeline`

两端必须作为一条发布链共同维护：Max 负责生成和复制 FBX、写入定位请求；Unity 负责导入设置、提取 `.anim`、曲线处理和 Project 定位。

## 可提交内容

- Python、MaxScript、C# 源码。
- 安装脚本、示例配置、README、验证脚本。
- 与工具本身直接相关的 SVG/QSS 等轻量 UI 资源。

## 禁止提交内容

- 公司内网地址、公司工程绝对路径、账号、令牌和个人身份信息。
- 真实的 `rm_config.json`、`afm_config.json`、`afm_user_config.json`、动作库用户配置。
- `.max`、FBX、Prefab、贴图、角色配置等项目资产。
- `.pyc`、日志、错误报告、临时目录、备份和生成结果。

## 修改流程

1. 先确认修改属于 Max、Unity 或跨端契约。
2. 跨端契约必须同时检查写入方和读取方，尤其是请求文件位置、JSON 字段、Unity Assets 路径和武器状态映射。
3. 修改源代码后同步修改本仓库中的个人版本，不从安装目录反向覆盖仓库。
4. 运行静态验证和敏感信息扫描。
5. 在真实 Max/Unity 中完成相关功能验收后，再记录为运行时已验证。

## 当前通用契约

定位请求文件：

`%LOCALAPPDATA%/Afauxzhub/AnimationPipeline/unity_bridge_request.json`

JSON 字段：

```json
{
  "asset_path": "Assets/.../Example.anim",
  "absolute_path": "D:/MyUnityProject/Assets/.../Example.anim"
}
```

Unity 端只接受 `Assets` 或 `Assets/` 开头的 `asset_path`。

## 上游同步提醒

公司工程后续若继续修改同类工具，不应直接整目录覆盖个人版本。先比较差异，再只移植通用逻辑，并重新执行敏感信息扫描。个人版已经移除了固定共享盘、战斗数据序列化、公司资源路由和第三方业务框架依赖。

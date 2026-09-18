# Animation Library

`Animation Library` 是 `Max_AI_Tools` 里的 3ds Max 动画库插件。

## 安装说明

安装和发布说明请看根目录 `README.md`。

推荐安装方式：

1. 把根目录 `install_plugin.ms` 拖进 3ds Max。
2. 让安装脚本自动复制到 Max 默认用户脚本目录。
3. 通过 `Max AI Tools > Anim Library` 启动。

## 模块作用

这个目录包含插件主体代码，包括：

- 主窗口与 UI
- 动画资源浏览
- 动画保存与应用逻辑
- Pose / Mirror 相关操作
- 配置与样式资源

## 开发备注

- 启动入口由根目录 `launch_plugin.py` 负责。
- `launch_plugin.py` 现在按自身路径定位插件根目录，不依赖固定机器路径。
- 后续更新时，只需要替换安装目录内的对应文件，不需要改启动方式。

## 目录结构

```text
AnimationLibrary/
├── __init__.py
├── main.py
├── config/
├── resources/
├── ui/
└── utils/
```

## 内部使用说明

这是内部工具目录，面向开发和维护使用。

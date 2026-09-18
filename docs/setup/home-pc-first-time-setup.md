# 家庭电脑首次接管项目

这份文档用于在一台新的 Windows 个人电脑上接管 `MY_Project`。目标是尽量把 Git、GitHub、仓库克隆和项目检查交给 Codex 完成，同时避免覆盖已有文件或安装错误的 Unity 版本。

## 你必须亲自完成的三件事

1. 在家庭电脑上安装并打开 ChatGPT 桌面应用，登录当前使用的 OpenAI 账号。
2. 新建一个临时 Codex 任务，把下方“首次安装提示词”完整发送给它，并批准必要的软件安装操作。
3. 当 GitHub 在浏览器中要求登录或授权时，亲自完成登录、验证码和授权确认。不要把密码、验证码或访问令牌发给 Agent。

其余操作交给 Agent 完成。

## 第一步：发送给临时 Agent 的首次安装提示词

复制下面整段内容，原样发送给家庭电脑上的新 Codex 任务：

```text
请帮我在这台 Windows 个人电脑上完成 MY_Project 的首次开发环境接管。除了 GitHub 登录、验证码、授权确认，以及在 Codex 界面中选择项目文件夹之外，其余步骤请直接执行，不要只给我教程。

项目资料：
- GitHub 仓库：https://github.com/Afauxzhub/MY_Project.git
- GitHub 用户名：Afauxzhub
- Git 提交邮箱：296432846+Afauxzhub@users.noreply.github.com
- 默认本地目录：$env:USERPROFILE\GameDev\MY_Project
- 默认分支：main
- 这台电脑只用于个人项目，可以设置全局 Git 提交身份。

执行要求：
1. 使用 Windows 原生环境和 PowerShell，不要把项目放进 WSL、OneDrive、桌面或临时目录。
2. 先只读检查 winget、Git、GitHub CLI 和 Git LFS 是否已经安装，并报告检查结果。
3. 缺少 Git 时，使用 winget 安装官方 Git for Windows；缺少 GitHub CLI 或 Git LFS 时，也先通过 winget 查询准确的软件包 ID，再安装。任何安装操作需要审批时直接申请审批。
4. 安装完成后重新检查命令是否可用；必要时说明是否需要重启 Codex，但不要假装命令已经生效。
5. 设置个人电脑的全局 Git 身份：
   git config --global user.name "Afauxzhub"
   git config --global user.email "296432846+Afauxzhub@users.noreply.github.com"
   git config --global init.defaultBranch main
6. 初始化 Git LFS。如果命令可用，执行 git lfs install。
7. 使用 GitHub CLI 的浏览器登录方式登录 github.com。停在需要我亲自完成浏览器登录、验证码或授权确认的位置，明确告诉我该做什么；不要要求我把密码、验证码或访问令牌发给你。
8. 确认 GitHub 登录用户是 Afauxzhub 后，把仓库克隆到 $env:USERPROFILE\GameDev\MY_Project。执行命令前先把它解析成绝对路径并显示出来，不要创建名称中包含“$env:USERPROFILE”的字面目录。
9. 如果目标目录已经存在，不要删除、覆盖或重新克隆。先检查它是否是正确仓库以及是否有未提交内容；能够安全继续时执行拉取，否则停止并说明冲突。
10. 克隆后执行 Git LFS 拉取（如果 Git LFS 可用），然后验证：
    - 当前分支是 main；
    - main 跟踪 origin/main；
    - origin 指向 Afauxzhub/MY_Project；
    - 本地 HEAD 与 origin/main 一致；
    - 工作区干净；
    - Git 作者是 Afauxzhub 和指定 noreply 邮箱；
    - 仓库中存在 AGENTS.md；
    - 仓库中存在 .agents/skills/combat-design/SKILL.md；
    - 仓库中存在 docs/design/combat/player-combat-spec.md、integration-contracts.md 和 maintenance-rules.md。
11. 检查仓库是否已经包含 Unity 的 ProjectSettings/ProjectVersion.txt：
    - 如果存在，只报告文件中声明的 Unity 版本和家庭电脑是否已经安装匹配版本；不要擅自升级项目。
    - 如果不存在，说明当前仓库还没有确定 Unity 工程版本，不要猜测版本、不要创建 Unity 项目，也不要安装任意 Unity Editor。
12. 不要修改、提交或推送项目文件。本次任务只完成工具安装、账号配置、仓库克隆和只读验收。
13. 最后给出一份简短验收结果，明确列出：安装完成的工具、仓库绝对路径、GitHub 登录用户、Git 身份、当前提交、工作区状态、Unity 环境状态，以及下一步需要我在 Codex 界面中完成的唯一操作。
```

## 第二步：把克隆目录添加为 Codex 本地项目

首次安装 Agent 完成后：

1. 在 ChatGPT 桌面应用中选择“添加新项目”，或按 `Ctrl+O`。
2. 选择首次安装 Agent 最后报告的仓库绝对路径，通常类似：

   ```text
   C:\Users\你的Windows用户名\GameDev\MY_Project
   ```

3. 确保它是项目的主文件夹。
4. 在该项目中创建一个新任务。

这一步必须在 Codex 界面中由你完成。临时任务不能替你把自己切换到另一个本地项目。

## 第三步：发送给项目 Agent 的接管提示词

进入新建的 `MY_Project` 本地项目任务后，复制下面整段内容并发送：

```text
这是我从另一台电脑接管的 MY_Project。请先进行只读接管检查，不要修改设计或代码：

1. 确认当前工作目录是 MY_Project 的仓库根目录。
2. 检查当前分支、origin、HEAD、工作区状态和 Git 提交身份。
3. 完整读取仓库根目录的 AGENTS.md，并确认项目级 combat-design Skill 已被发现。
4. 按 AGENTS.md 的要求读取当前任务所需的权威设计文档；不要用旧聊天记忆覆盖仓库中的 [CONFIRMED] 规则。
5. 概括当前项目已经具备的内容、尚未开始的制作内容，以及建议的下一项最小工作。
6. 如果仓库、Skill 或设计文档缺失，停止并告诉我，不要自行重建或猜测。

完成检查后等待我的下一条制作要求。
```

## 以后两台电脑之间的固定规则

每次开始工作时，让 Agent 先执行：

```text
检查工作区；如果干净，拉取 origin/main，并确认本地与远端一致后再开始工作。
```

每次结束工作时，明确要求 Agent：

```text
检查本次改动，进行必要验证，提交到 main 并推送到 origin；最后确认工作区干净且本地与远端一致。
```

不要在公司电脑和家庭电脑上同时修改同一批文件。换电脑前先提交并推送，到另一台电脑后先拉取。

## 当前限制

- 当前仓库只有设计规范和项目 Skill，还没有 Unity 工程，因此首次接管时不应猜测 Unity 版本。
- Git 仓库会同步 `AGENTS.md`、项目 Skill 和设计文档，但不会同步 Fork 登录状态、GitHub 登录缓存、个人级 Codex 配置或尚未提交的本地文件。
- 当前聊天记录可以作为参考，但长期有效的规则必须以仓库中的 `AGENTS.md` 和权威设计文档为准。

## 官方依据

- [OpenAI Docs：Windows 桌面应用](https://developers.openai.com/zh-Hans/docs/app/windows)
- [OpenAI Docs：项目和聊天](https://developers.openai.com/zh-Hans/docs/projects)
- [OpenAI Docs：构建技能](https://developers.openai.com/zh-Hans/docs/build-skills)

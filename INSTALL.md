# 安装 chess-diagram-to-fen

这个仓库只包含一个 Agent Skill：`chess-diagram-to-fen`。安装 = **把整个技能目录复制到 agent 会扫描的 skills 根目录**，再装好 Python 依赖。没有构建步骤，没有常驻服务；技能运行时不发网络请求。

本文有两类读者：

- **用户手动安装**：从 [§1 快速安装](#1-快速安装) 开始。
- **让另一个 agent 自己装**：把 [§5 给 agent 的安装协议](#5-给-agent-的安装协议) 整段发给它；仓库根的 `AGENTS.md` 也指向这一节。

装完不生效，直接看 [§7 故障排查](#7-故障排查)。

## 0. 先确认要复制什么

源目录：

```text
<repo>/.dsh/skills/chess-diagram-to-fen/
├── SKILL.md
├── requirements.txt
├── references/
│   ├── recognition.md
│   └── verification.md
└── scripts/
    ├── boardtool.py
    └── selftest.py
```

必须**整个目录一起复制**：

- 只复制 `SKILL.md`：丢掉识别参考、校验规则和脚本，技能只能手工执行，且很多步骤没有工具兜底。
- 只复制 `scripts/`：agent 根本发现不了技能，因为没有 `SKILL.md` 入口。
- 把仓库根目录整个放进 skills 根：多了一层，agent 扫描不到。

许可证文件 `LICENSE-MIT` 和 `LICENSE-CC0` 在仓库根，不在技能目录内。建议安装时把两个文件一并复制进技能目录；至少单独分发这个技能目录时必须这样做。

安装后的目标形态必须是：

```text
<skills-root>/chess-diagram-to-fen/SKILL.md
```

不是：

```text
<skills-root>/boardtofen/.dsh/skills/chess-diagram-to-fen/SKILL.md   # 多了一层
<skills-root>/SKILL.md                                              # 丢了技能目录
<skills-root>/chess-diagram-to-fen/SKILL.md/SKILL.md                 # SKILL.md 被当成目录
```

## 1. 快速安装

### 1.1 选目标目录

| 装给谁 | 作用域 | 目标目录 |
|---|---|---|
| DeepSeek Harness（本项目） | 仅当前项目 | `<repo>/.dsh/skills/` |
| DeepSeek Harness | 当前用户所有项目 | `~/.dsh/skills/` |
| 多个 agent 共用 | 当前用户 | `~/.agents/skills/` |
| Claude Code | 当前用户 | `~/.claude/skills/` |
| Claude Code | 仅当前项目 | `<repo>/.claude/skills/` |
| Codex | 当前用户 | `$CODEX_HOME/skills/`（默认 `~/.codex/skills/`） |
| Codex | 仅当前项目 | `<repo>/.codex/skills/` |
| Cursor | 当前用户 | `~/.cursor/skills/` 或 `~/.agents/skills/` |
| Cursor | 仅当前项目 | `<repo>/.cursor/skills/` 或 `<repo>/.agents/skills/` |
| 其他支持 Agent Skills 的客户端 | 看客户端文档 | 其 skills 根下的 `chess-diagram-to-fen/` |

几个容易踩的点：

- `<repo>` 是**项目根**。DeepSeek Harness 取最近的包含 `.git` 的上级目录；没有 `.git` 时取会话启动目录。如果本目录只是更大 git 仓库的子目录，项目根是那个仓库根，不是本目录；把技能放在项目根的 `.dsh/skills`，或改用用户级安装。
- `~/.agents/skills/` 是目前最通用的用户级位置：DeepSeek Harness、Cursor 会读，Codex 的部分版本也读（见 §3.3）。想“装一次，多个 agent 用”，优先选它。
- 不确定时装用户级；只在一个仓库用就装项目级。
- 同一技能装了多份时，各客户端按自己的优先级取一份；排查问题时先确认 agent 实际读的是哪一份。

### 1.2 复制目录（Windows PowerShell）

```powershell
$repo = "K:\boardtofen"                     # 改成你的仓库路径
$src  = Join-Path $repo ".dsh\skills\chess-diagram-to-fen"
$dst  = Join-Path $HOME ".agents\skills"    # 换成上表的目标
$target = Join-Path $dst "chess-diagram-to-fen"

New-Item -ItemType Directory -Force -Path $dst | Out-Null
Write-Host "target: $target"
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
Copy-Item -Recurse -Force $src $target
Copy-Item -Path (Join-Path $repo "LICENSE-MIT"), (Join-Path $repo "LICENSE-CC0") -Destination $target
Get-ChildItem $target
```

`Remove-Item` 只删除目标技能目录；第一次安装时它不存在，不会执行。升级时它会删除旧版本，所以确认 `$target` 就是你要替换的技能目录。

macOS / Linux：

```bash
repo="/path/to/boardtofen"
src="$repo/.dsh/skills/chess-diagram-to-fen"
dst="$HOME/.agents/skills"
mkdir -p "$dst"
echo "target: $dst/chess-diagram-to-fen"
rm -rf "$dst/chess-diagram-to-fen"
cp -R "$src" "$dst/"
cp "$repo/LICENSE-MIT" "$repo/LICENSE-CC0" "$dst/chess-diagram-to-fen/"
ls "$dst/chess-diagram-to-fen"
```

如果源是压缩包，先解压，再对解压出来的 `chess-diagram-to-fen/` 执行同样的复制。不要直接把 `.zip` 放进 skills 根。

### 1.3 安装 Python 依赖

```bash
python -m pip install -r "<skill-dir>/requirements.txt"
# 可选：更严格的合法性交叉检查
python -m pip install python-chess
```

`<skill-dir>` 就是上一步的 `$target`（Windows）或 `$dst/chess-diagram-to-fen`（macOS/Linux）。

Windows 如果 `python` 指向 Microsoft Store 的占位程序，改用 `py -3`：

```powershell
py -3 -m pip install -r "$target\requirements.txt"
```

要求 Python 3.10+、Pillow、NumPy。没有 `python-chess` 也能完成识图；`check` 只是少了最后一道交叉验证。

macOS / Linux 如果没有 `python` 命令，把上面的 `python` 换成 `python3`；两个命令指向不同版本时，用 `python3 -m pip` 保证装进同一个解释器。

### 1.4 验证

```bash
cd "<skill-dir>"
python scripts/selftest.py
```

看到 `PASS` 即安装完成。它会在**当前目录**建一个临时目录，渲染起始局面，跑 `prepare → check → annotate`，然后自动删除。不会碰真实棋图，也不会联网。

当前目录不可写时，指定一个可写目录：

```bash
python scripts/selftest.py --workdir "$HOME/tmp"
```

只想看机器可读结果：

```bash
python scripts/selftest.py --json
```

## 2. 安装后怎么用

- **DeepSeek Harness**：新会话直接附棋图并说“把这张图转成 FEN”，或输入 `/chess-diagram-to-fen`。
- **Claude Code**：输入 `/chess-diagram-to-fen`，或直接描述任务让模型按 description 自动调用。
- **Codex / Cursor**：直接说“用 chess-diagram-to-fen 把这个棋盘图转成 FEN”；支持斜杠的界面也可以 `/chess-diagram-to-fen`。
- **首次使用**：给一张清晰、带印刷坐标、完整包含 8×8 棋盘的图。边缘被裁掉一格，技能会拒绝猜测，要求换图。

## 3. 各客户端说明

### 3.1 DeepSeek Harness

扫描根按优先级从高到低：

| 优先级 | 根 | 说明 |
|---|---|---|
| 100 | `<project>/.dsh/skills` | 项目级，DSH 专用 |
| 200 | `<project>/.agents/skills` | 项目级，跨客户端 |
| 300 | 配置的 `customSkillDirs` | 自定义 |
| 400 | `$DSH_HOME/skills`（默认 `~/.dsh/skills`） | 用户级，DSH 专用 |
| 500 | `~/.agents/skills` | 用户级，跨客户端 |

- **只扫描一层**：`<root>/<name>/SKILL.md` 或 `<root>/<name>.md`。嵌套的 `**/SKILL.md` 不会被发现。
- 如果本目录只是某个 git 仓库的子目录，DSH 的项目根是那个仓库根，不是本目录；把技能放在仓库根的 `.dsh/skills`，或改用用户级安装。
- `name` 必须是 kebab-case（小写字母、数字、连字符）。本技能是 `chess-diagram-to-fen`。
- `SKILL.md` 必须有 YAML frontmatter，至少包含 `name` 和 `description`。
- 前端有文件监听：复制进去后通常无需重启；当前会话的目录没刷新，就开一个新会话。
- 斜杠调用发送的是字面量 `/chess-diagram-to-fen`，宿主在发送时注入技能正文；不支持斜杠的界面直接说技能名也可以。
- `$DSH_HOME` 被改过时，用户级路径随之改变；用 `echo $env:DSH_HOME` 确认。

### 3.2 Claude Code

- 个人：`~/.claude/skills/chess-diagram-to-fen/SKILL.md`
- 项目：`<repo>/.claude/skills/chess-diagram-to-fen/SKILL.md`
- 调用：`/chess-diagram-to-fen`，或让模型按 description 自动触发。
- Claude Code 支持把技能目录做成插件、从 claude.ai 同步等；本技能不需要这些，普通目录即可。
- 同名技能的作用域优先级与 DSH 不同（Claude Code 是 enterprise > personal > project）；排查“为什么加载的是旧版本”时先看这一点。

### 3.3 Codex

- 用户：`$CODEX_HOME/skills/`（未设置时 `~/.codex/skills/`）
- 项目：`<repo>/.codex/skills/`；项目通常需要被 trust 后才会加载项目级配置。
- 部分版本也读取 `~/.agents/skills/`；装完用 Codex 自己的技能列表确认。
- Codex 的技能目录随版本演进，安装前以当前版本文档为准；本技能的格式遵循 Agent Skills 标准，目录结构不需要改。

### 3.4 Cursor

- 项目：`<repo>/.cursor/skills/` 或 `<repo>/.agents/skills/`
- 用户：`~/.cursor/skills/` 或 `~/.agents/skills/`
- Cursor 也兼容 `.claude/skills/`、`.codex/skills/` 及其用户级目录；如果你同时用 Claude Code 和 Cursor，装在 `~/.claude/skills/` 也能被 Cursor 读到。
- 在 Agent 聊天里输入 `/` 可以搜索技能名；选中后只对当前消息生效。

### 3.5 其他 agent

- **支持 Agent Skills 标准的客户端**：按它的文档找到 skills 根，放成 `<root>/chess-diagram-to-fen/`。不同客户端的根目录不统一，不要假设 `~/.agents` 一定被读。
- **只支持 `AGENTS.md` / `CLAUDE.md` 的客户端**：加一行指针，例如：

  ```markdown
  - 棋图转 FEN：读取 `.dsh/skills/chess-diagram-to-fen/SKILL.md`，按其中的七步协议执行。
  ```

  这不会提供自动发现，但能让 agent 找到完整流程。注意：指针里的路径必须从 agent 的工作目录可达；跨项目使用时写绝对路径或先复制技能。
- **完全没有文件访问的对话产品**：把 `SKILL.md` 正文粘贴进对话，并上传棋图。脚本无法运行时，按 SKILL.md 的手工流程做双读和审计；工具能省时间，但流程本身不依赖工具。

## 4. 文件校验

复制后至少确认这些文件存在：

```text
<skill-dir>/SKILL.md
<skill-dir>/requirements.txt
<skill-dir>/references/recognition.md
<skill-dir>/references/verification.md
<skill-dir>/scripts/boardtool.py
<skill-dir>/scripts/selftest.py
```

许可证文件在仓库根：`LICENSE-MIT`、`LICENSE-CC0`。单独分发技能目录时，把它们一起放进 `<skill-dir>/`。

检查入口文件的开头：

```powershell
Get-Content "<skill-dir>\SKILL.md" -TotalCount 6
```

应看到：

```yaml
---
name: chess-diagram-to-fen
description: Read a printed or on-screen 2D chess diagram and return a verified FEN. ...
compatibility: "Python 3.10+ with Pillow and NumPy; python-chess optional."
license: "MIT (software) / CC0-1.0 (documentation)"
---
```

macOS / Linux 用 `head -6 "<skill-dir>/SKILL.md"`。

如果 `SKILL.md` 开头不是 `---`，或缺少 `name` / `description`，客户端会静默跳过这个技能，列表里不会出现。

## 5. 给 agent 的安装协议

> English summary: copy the whole `chess-diagram-to-fen/` directory into the client's skills root (`<root>/chess-diagram-to-fen/SKILL.md`), keep `references/` and `scripts/`, install `requirements.txt` if needed, run `python scripts/selftest.py` until it prints `PASS`, then confirm the client lists the skill. Ask before replacing an existing install.

你是被要求安装这个 skill 的 agent。按以下顺序执行，不要跳步，也不要在验证失败时宣称安装成功。

1. **定位源目录 S。** 优先用用户给出的仓库路径下的 `.dsh/skills/chess-diagram-to-fen`；如果是压缩包，先解压到临时目录再找同名目录。确认 `S/SKILL.md` 存在。
2. **确定目标根 R。** 用户指定了就用用户的。没有指定时按场景选择，并告诉用户你选了哪个：
   - 当前项目使用 DeepSeek Harness：`<project>/.dsh/skills`
   - 当前用户、跨项目、多 agent 共用：`~/.agents/skills`
   - Claude Code：`~/.claude/skills`
   - Codex：`$CODEX_HOME/skills`（默认 `~/.codex/skills`）
   - Cursor：`~/.cursor/skills`
3. **检查目标是否已存在。** 如果 `R/chess-diagram-to-fen` 已存在，不要直接覆盖。先比较版本或询问用户是否升级；需要保留时先备份到临时目录。不要删除 `R` 下其他技能。
4. **复制整个目录。** 目标必须是 `R/chess-diagram-to-fen/`，且其下直接有 `SKILL.md`。不要把仓库根复制进去，不要把内容摊平，不要漏掉 `references/` 或 `scripts/`。把仓库根的 `LICENSE-MIT`、`LICENSE-CC0` 也复制到目标目录（单独分发时需要）。
5. **校验文件。** 检查 `R/chess-diagram-to-fen/SKILL.md` 首行是 `---`，frontmatter 有 `name: chess-diagram-to-fen` 和 `description:`，并且第 4 节列出的文件都存在。
6. **检查依赖。** 先运行 `python -c "import PIL, numpy"` 和 `python --version`。缺依赖时，安装前告诉用户会修改哪个 Python 环境；优先 `python -m pip install -r "R/chess-diagram-to-fen/requirements.txt"`。不要静默使用 `sudo`、不要静默改系统 Python、不要跳过用户确认。
7. **运行自检。** 在技能目录执行 `python scripts/selftest.py`，要求退出码为 0 且输出 `PASS`。失败时报告完整错误和已经尝试的修复，不要继续宣称成功。
8. **确认客户端发现。** DeepSeek Harness 开新会话看技能列表或输入 `/chess-diagram-to-fen`；Claude Code 输入 `/chess-diagram-to-fen`；Codex / Cursor 用其技能列表确认。看不到时按第 7 节排查。
9. **报告。** 给出：源路径、目标路径、Python 版本、Pillow/NumPy/python-chess 版本、自检结果、调用方式、任何失败项。不要只说“装好了”。
10. **清理。** 删除临时解压目录和备份；不要删除用户的 `work/` 目录、棋图或原始仓库。

安装完成的判定条件（全部满足才算完成）：

- `R/chess-diagram-to-fen/SKILL.md` 存在且 frontmatter 正确；
- 第 4 节列出的文件全部存在；
- `python scripts/selftest.py` 退出码 0，输出 `PASS`；
- 目标客户端能看到或调用 `chess-diagram-to-fen`；
- 若单独分发，目标目录内有 `LICENSE-MIT` 和 `LICENSE-CC0`。

可以直接把下面这段发给另一个 agent：

```text
请安装这个 Agent Skill：<repo>/.dsh/skills/chess-diagram-to-fen
目标：<用户级 ~/.agents/skills / DSH 项目级 / Claude Code / Codex / Cursor>
按 INSTALL.md 第 5 节“给 agent 的安装协议”执行；最后运行 scripts/selftest.py，
报告目标路径、依赖版本、自检结果和调用方式。
```

## 6. 升级、卸载、回滚

### 升级

用新版本目录整体替换旧目录，不要只覆盖 `SKILL.md`：

```powershell
$target = Join-Path $HOME ".agents\skills\chess-diagram-to-fen"
$bak = "$target.bak-$(Get-Date -Format yyyyMMddHHmmss)"
if (Test-Path $target) { Move-Item $target $bak }
Copy-Item -Recurse -Force "<新版本>\chess-diagram-to-fen" $target
python "$target\scripts\selftest.py"
```

确认新版可用后删除 `.bak-*`。`work/` 是运行时产物，放在技能目录外，不要跟着技能一起替换。

### 卸载

删除目标技能目录即可：

```powershell
Remove-Item -Recurse -Force (Join-Path $HOME ".agents\skills\chess-diagram-to-fen")
```

Python 依赖（Pillow、NumPy、python-chess）可能被其他项目共用，不要为了卸载技能而直接卸载它们。

### 回滚

保留上一版的 `.bak-*`，删除新版目录，把备份改回原名，再跑一次 `selftest.py`。

## 7. 故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 技能列表里没有 | 放错层级；`SKILL.md` 缺 frontmatter；`name` 不是 kebab-case；客户端没刷新 | 确认路径是 `<root>/chess-diagram-to-fen/SKILL.md`；检查开头 6 行；重开会话 |
| DSH 找不到项目级技能 | 会话启动目录不是项目根；仓库没有 `.git` 且从子目录启动 | 在仓库根启动；或改装到 `~/.dsh/skills` |
| 装了两份，加载的不是新版 | 同名技能多份，客户端按自己的优先级取一份 | 删除旧副本；用客户端的技能列表确认实际路径 |
| `python` 版本低于 3.10 | 系统里有多个 Python | `py -3.12`、`python3.12`，或建 venv |
| `ModuleNotFoundError: PIL` / `numpy` | pip 装到了另一个解释器 | 用 `python -m pip install ...`；`python -c "import sys; print(sys.executable)"` 对照 |
| `externally-managed-environment` | 系统 Python 受 PEP 668 保护 | 建 venv：`python -m venv .venv`，再 `.venv\Scripts\python -m pip install ...`（macOS/Linux 用 `.venv/bin/python`） |
| `selftest` 报 Permission denied | 当前目录不可写，或沙箱限制 | `python scripts/selftest.py --workdir <可写目录>`；DSH 下选工作区内的目录 |
| `prepare` 找不到 8×8 网格 | 不是安装问题：图被裁、倾斜、非标准棋盘 | 用 `grid` + `--bbox`；裁剪出完整棋盘；先矫正透视 |
| 识别结果明显错位 | 棋盘方向反了（黑方在下） | `prepare --flip`，或先确认印刷坐标 |
| 字体缺失、渲染像字母 | 系统没有 Segoe UI Symbol / DejaVu | 审计标注仍可读；Linux 装 `fonts-dejavu-core`，或忽略渲染样式 |
| agent 能加载但不用 | 用户没明确点名；description 没有被匹配 | 明确说“使用 chess-diagram-to-fen”；检查技能列表里 description 是否完整 |
| Windows 路径含空格/中文 | 命令没加引号 | 所有路径加双引号；PowerShell 变量用 `Join-Path` |
| OneDrive / 同步盘文件锁 | 同步进程占用文件 | 暂停同步，或把技能装到本地非同步目录 |

DSH 在 workspace-write 沙箱下只允许写工作区；如果技能装在用户目录、而会话工作区在别处，`selftest.py` 默认往 cwd 写临时目录，通常没问题；cwd 不可写时用 `--workdir` 指到工作区内。

## 8. 安全与隐私

- `scripts/boardtool.py` 只读你给的图片，只写你指定的输出路径和 `work/`；没有网络请求。
- `scripts/selftest.py` 只在自己的临时目录里生成图片，结束即删除；没有网络请求。
- 唯一需要联网的步骤是 `pip install`。安装前确认包名和来源；企业环境走内部镜像。
- 棋图可能包含未公开的题目、比赛局面或个人信息；`work/` 里的裁剪图、审计图在任务结束后按需删除。
- 从不受信任来源拿到技能包时，先读 `scripts/boardtool.py` 和 `scripts/selftest.py`，再运行。技能脚本拥有与你相同的文件权限。

## 9. 参考

- [Agent Skills 规范](https://agentskills.io/specification)：`SKILL.md`、`references/`、`scripts/` 的通用格式
- [Claude Code Skills 文档](https://code.claude.com/docs/en/skills)：个人/项目技能目录与调用方式
- [Codex Skills 文档](https://developers.openai.com/codex/skills)：用户级与项目级技能目录
- [Cursor Skills 文档](https://cursor.com/docs/skills)：技能目录、斜杠调用与兼容路径
- [PGN 标准](https://www.saremba.de/chessgml/standards/pgn/pgn-complete.htm)：FEN 与 PGN 的正式定义
- [`SKILL.md`](.dsh/skills/chess-diagram-to-fen/SKILL.md)：技能本身的七步协议
- [`README.md`](README.md)：项目介绍、FEN 入门、FEN 与 PGN 的区别

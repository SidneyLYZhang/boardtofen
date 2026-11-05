# boardtofen

**把二维国际象棋局面图，变成一串可验证的 FEN。**

`boardtofen` 是一个可移植的 Agent Skill（技能名 `chess-diagram-to-fen`）。它把“看图写 FEN”从一次容易出错的目测，变成一条有中间产物的流水线：**双读、逐格仲裁、合法性检查、审计图**。识别由模型完成，几何切分、差异比对、FEN 组装和终检由脚本兜底。

- 适用于书籍、试卷、网页截图里的平面棋盘。
- 不适用于 3D 棋盘、严重透视/模糊、或被裁掉边缘的图。
- 只产出**局面** FEN，不推断棋谱历史。

> 第一次接触 FEN 和 PGN？先记住一句话：**FEN 是局面，PGN 是对局**。下文有完整对比。

## 快速开始

### 1. 安装

本仓库已经把技能放在 `.dsh/skills/chess-diagram-to-fen/`。在仓库根目录启动 DeepSeek Harness 即可直接使用。

装到其他位置（用户级、Claude Code、Codex、Cursor、多 agent 共用），见 **[INSTALL.md](INSTALL.md)**。最短的 Windows 用户级安装：

```powershell
$repo = "K:\boardtofen"                     # 改成你的仓库路径
$src = Join-Path $repo ".dsh\skills\chess-diagram-to-fen"
$dst = Join-Path $HOME ".agents\skills"
$target = Join-Path $dst "chess-diagram-to-fen"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
Copy-Item -Recurse -Force $src $target
Copy-Item -Path (Join-Path $repo "LICENSE-MIT"), (Join-Path $repo "LICENSE-CC0") -Destination $target
python -m pip install -r "$target\requirements.txt"
python "$target\scripts\selftest.py"
```

`selftest.py` 输出 `PASS` 即安装完成。它不需要真实棋图，会渲染起始局面并跑通 `prepare → check → annotate`。

### 2. 使用

在新会话里附上棋图，然后说：

> 把这张棋图转成 FEN。

也可以直接输入 `/chess-diagram-to-fen`。技能会按固定流程读取，并在最后给出 FEN 和一张“每个字段从哪来”的说明表。

如果你已经有一个 FEN、想核对它是否对得上图片，就把图和 FEN 一起给出；技能会用同一套审计图逐格比对，指出不一致的格子，而不是只回答“合法/不合法”。

### 3. 输出长什么样

```text
r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w - - 0 1
```

| 字段 | 值 | 来源 |
|---|---|---|
| 行棋方 | `w` | 图注 “White to move” |
| 易位权 | `-` | 图上未标注 |
| 吃过路兵 | `-` | 图上未标注 |
| 半回合 / 回合 | `0 1` | 图上未标注 |
| 方向 | 白方在下 | 印刷坐标；无坐标时按约定 |

这是一张“图能给出多少，就写多少”的 FEN。它的棋子位置来自图片；其余五个字段来自图注或默认假设，不会被假装成历史事实。

## 它如何工作

| 步骤 | 做什么 | 产物 |
|---|---|---|
| 1. 定位棋盘 | 检测 8×8 网格，校正倾斜，切出四象限和上下半区 | `overlay.png`、`contact.png`、`q1`–`q4`、`half_top/bottom.png` |
| 2. 第一读 | 按象限逐格读取，写 8×8 字符账本 | `read1.txt` |
| 3. 第二读 | **不看第一读**，按上下半区再读一遍 | `read2.txt` |
| 4. 仲裁 | 逐格比对差异，放大争议格，记录判据 | `disputes.png`、`notes.md`、`final.txt` |
| 5. 编码 | 从账本组装 FEN，做结构 + 合法性检查 | FEN、`ARBITER` 结果 |
| 6. 审计 | 把 FEN 的每个符号盖回原图，逐格核对 | `audit.png` |
| 7. 报告 | 给出 FEN 和来源说明表（provenance）；不确定的格子明确列出 | 最终答复 |

关键点：**合法性不等于正确性**。一个把皇后从 e3 读成 f3 的 FEN 完全可以合法。第 6 步的审计图才是“FEN 是否真的对应该图”的最终检查。

完整协议见 [`SKILL.md`](.dsh/skills/chess-diagram-to-fen/SKILL.md)；识别细节和校验规则分别在 [`references/recognition.md`](.dsh/skills/chess-diagram-to-fen/references/recognition.md) 和 [`references/verification.md`](.dsh/skills/chess-diagram-to-fen/references/verification.md)。

## FEN 是什么

FEN 全称 **Forsyth–Edwards Notation**，通常直接叫 **FEN 标记**或 **FEN 字符串**。它不是棋谱，而是**某一瞬间的完整局面**：一行文本，六个用空格分隔的字段。

```text
r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4
```

从左到右依次是：棋子位置、行棋方、易位权、吃过路兵目标格、半回合钟、回合数。下面逐项拆开。

### 六个字段

| # | 字段 | 示例 | 含义 |
|---|---|---|---|
| 1 | 棋子位置 | `r1bqkb1r/.../RNBQK2R` | 8 段，从第 8 横线写到第 1 横线；大写白、小写黑；数字表示连续空格 |
| 2 | 行棋方 | `w` | `w` = 白方走，`b` = 黑方走 |
| 3 | 易位权 | `KQkq` | 白王翼 `K`、白后翼 `Q`、黑王翼 `k`、黑后翼 `q`；没有权利写 `-` |
| 4 | 吃过路兵目标格 | `-` | 上一步是兵走两格时，记录兵越过的格子，如 `e3`；否则 `-` |
| 5 | 半回合钟 | `4` | 距离上一次吃子或兵移动的半步数，用于 50 回合规则 |
| 6 | 回合数 | `4` | 从 1 开始，黑方走完一步后加 1 |

### 棋子位置怎么读

规则只有四条，但第一条最常被写反：

1. **从第 8 横线往第 1 横线写**，也就是从图的上方读到下方。写反会把整盘棋上下镜像。
2. 八段用 `/` 分隔。每一段从左到右是 a→h 列。
3. 大写是白棋 `K Q R B N P`，小写是黑棋 `k q r b n p`。
4. 连续空格用数字 1–8 压缩；每一段展开后必须正好 8 格。

几个小例子：

| 片段 | 含义 |
|---|---|
| `8` | 整条横线为空 |
| `4P3` | a–d 空，e 列一个白兵，f–h 空 |
| `3Q4` | a–c 空，d 列一个白后，e–h 空 |
| `PPPP1PPP` | a–d 白兵，e 空，f–h 白兵 |

把上面的完整示例拆开，第 8 横线 `r1bqkb1r` 就是：a8 黑车、b8 空、c8 黑象、d8 黑后、e8 黑王、f8 黑象、g8 空、h8 黑车。`2n2n2` 表示第 6 横线 c6、f6 各有一个黑马。

### 图上得不到的字段

一张局面图能可靠给出的是**棋子位置**，也许还有图注里的行棋方。其余字段依赖历史，图上通常看不到：

| 字段 | 图上能看到吗 | 技能默认值 |
|---|---|---|
| 行棋方 | 只有图注、`W`/`B` 标记或“White to move”能说明 | `w`，并标记为 assumed |
| 易位权 | 不能。看到王车在原位，不等于还有易位权 | `-` |
| 吃过路兵 | 只有明确标出“上一步兵走两格”时才能确定 | `-` |
| 半回合 / 回合 | 不能 | `0 1` |
| 方向 | 印刷坐标是证据；没有坐标时按“白方在下”约定 | 记录为假设 |

这正是本技能反复强调的：**不要因为王车在初始格就写 `KQkq`**。一张图只能证明棋子在哪，不能证明它们是否移动过。宁可写 `-`，也不要编造历史。

## FEN 与 PGN 的区别

一句话：**FEN 是局面，PGN 是对局。**

### PGN 是什么

PGN 全称 **Portable Game Notation**。它记录的是一整盘棋：标签对（赛事、棋手、结果等）+ 着法序列（通常用 SAN，即 Standard Algebraic Notation，标准代数记谱），还可以带注释和变例；不少工具还会用注释记录每步耗时。

```pgn
[Event "Miniature"]
[Site "?"]
[Date "????.??.??"]
[Round "1"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0
```

- 标签对是元数据：谁下的、在哪、什么时候、结果如何。
- 着法序列是历史：从初始局面开始，一步一步走到终局。
- 非标准起始局面用 `[SetUp "1"]` 加 `[FEN "..."]` 指定。
- 一个 `.pgn` 文件可以包含多盘棋。

### 对比表

| 维度 | FEN | PGN |
|---|---|---|
| 记录对象 | 某一瞬间的完整局面 | 一整盘棋的过程 |
| 时间性 | 快照，无先后 | 录像，着法有序 |
| 长度 | 一行，通常几十个字符 | 通常数百到数千字符；短局更短，多局更长 |
| 核心内容 | 棋子位置 + 行棋方 + 易位权 + 吃过路兵 + 半回合钟 + 回合数 | 标签对 + SAN 着法 + 注释/变例 + 结果 |
| 对局元数据 | 没有棋手、赛事、结果 | 有 |
| 能否还原另一种表示 | 不能唯一还原对局；同一局面可由不同着法顺序到达 | 可以逐步回放，导出任意一步的 FEN |
| 历史相关字段 | 易位权、吃过路兵、半回合钟、回合数都依赖历史 | 由着法序列自然产生 |
| 重复局面 / 三次重复 | 无法判断，因为没有历史 | 可以回放判断 |
| 典型用途 | 引擎接口、排局/残局、局面检索、图片识别 | 棋谱存档、复盘、教学、赛事记录 |
| 合法性 | 语法不保证合法；需要校验器 | 合法着法序列通常隐含合法性，但文件仍可能损坏 |
| 文件形态 | 单行字符串，常嵌入 JSON/CSV/数据库 | `.pgn` 文本，可多局 |

### 为什么 FEN 不能反推 PGN

同一个局面可以由很多不同的着法顺序到达。FEN 只记录“现在是什么样”，不记录“怎么走到这里”。因此：

- 从 FEN 出发，无法知道上一步是什么、完整的吃子与兵移动历史、是否三次重复。
- 从 FEN 出发，无法知道棋手、赛事、结果。
- 从 PGN 出发，可以回放并导出每一步的 FEN；反向则不成立。

### 用同一盘棋看差别

假设棋谱走到 `1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6`，白方走第 4 步。PGN 知道完整历史，所以能得到：

```text
r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4
```

而如果只给你这张**局面图**，图上没有写易位权、吃过路兵、半回合钟，也没有写这是第几回合。技能按“图上没有就不编”的原则，会给出：

```text
r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w - - 0 1
```

两个 FEN 的棋子位置完全相同，差别全在历史字段。第一个是“从棋谱回放出来的真相”，第二个是“这张图能证明的事实”。如果图注明确写了易位权或上一步，技能会把对应字段填上，并在报告里注明来源。

### 它们如何配合

- **PGN → FEN**：回放棋谱，在任意半步暂停，导出当前局面。适合做局面检索、引擎分析、题目抽取。
- **FEN → PGN**：不能还原唯一对局；要得到有意义的 PGN，必须补上着法历史。若只需要把该局面存成 PGN 的起始局面，可以用 `[SetUp "1"]` + `[FEN "..."]`。
- **PGN 内嵌 FEN**：棋谱库和研究资料常用这种形式保存非标准起始局面；回放时先按 `[FEN]` 摆好，再走着法。
- **本技能的定位**：从图片产出 FEN，不产出 PGN。若图来自一本有棋谱的书，正确做法是先找到棋谱记录，再用 PGN 回放；只有图片时，FEN 是诚实的产出。

## 安装（详细）

### 本仓库内使用（DeepSeek Harness，项目级）

技能已在 `.dsh/skills/chess-diagram-to-fen/`。在仓库根目录启动 DSH 即可。DSH 以最近的包含 `.git` 的目录为项目根；如果本目录本身是仓库根，项目根就是它；如果本目录只是更大 git 仓库的子目录，项目根是那个仓库根——此时把技能装到仓库根，或改用用户级安装。不要在子目录里启动后再期待它找到仓库根。

### 装到用户级或多 agent 共用

```powershell
$repo = "K:\boardtofen"                     # 改成你的仓库路径
$src = Join-Path $repo ".dsh\skills\chess-diagram-to-fen"
$dst = Join-Path $HOME ".agents\skills"
$target = Join-Path $dst "chess-diagram-to-fen"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
Copy-Item -Recurse -Force $src $target
Copy-Item -Path (Join-Path $repo "LICENSE-MIT"), (Join-Path $repo "LICENSE-CC0") -Destination $target
```

`~/.agents/skills/` 是通用的用户级位置：DeepSeek Harness、Cursor 会读，Codex 的部分版本也读；适合“装一次，多处用”。Claude Code 用 `~/.claude/skills/`；DSH 用户级用 `~/.dsh/skills/`。完整目标表、macOS/Linux 命令和各客户端注意事项见 **[INSTALL.md](INSTALL.md)**。

### 依赖

- Python 3.10+
- Pillow、NumPy
- `python-chess` 可选；`check` 有它时会多一道交叉验证

```bash
python -m pip install -r .dsh/skills/chess-diagram-to-fen/requirements.txt
python -m pip install python-chess        # 可选
```

### 自检

```bash
python .dsh/skills/chess-diagram-to-fen/scripts/selftest.py
```

看到 `PASS` 即安装完成。它会在当前目录建临时目录，渲染起始局面，跑通 `prepare → check → annotate`，然后自动删除。当前目录不可写时用 `--workdir` 指定可写目录。

## 目录结构

```text
boardtofen/
├── README.md
├── INSTALL.md
├── AGENTS.md                     # 给 coding agent 的仓库指针
├── LICENSE-MIT                   # 软件与脚本
├── LICENSE-CC0                   # 文档与技能文本
├── .gitignore                    # work/、临时目录、pycache
└── .dsh/skills/chess-diagram-to-fen/
    ├── SKILL.md                    # 技能入口：七步协议
    ├── requirements.txt            # Pillow + NumPy
    ├── references/
    │   ├── recognition.md          # 棋子轮廓、字母记谱、印刷伪影
    │   └── verification.md         # 六字段、合法性、审计规则
    └── scripts/
        ├── boardtool.py            # 切图、比对、FEN 组装、检查、审计
        └── selftest.py             # 安装自检
```

复制到其他客户端时，保持 `chess-diagram-to-fen/` 整个目录的层级，不要把里面的文件摊平到 skills 根目录。

仓库根的 `AGENTS.md` 是给 coding agent 的快速指针（先读 INSTALL §5）；人看 README 和 INSTALL 即可。

## 设计原则

- **两次独立读取**：象限扫描和半区扫描用不同的切法、不同的顺序；同一张裁剪图读两遍不算独立。
- **差异必须仲裁**：每个不一致的格子都要放大、看轮廓、记录判据；不靠“哪个更像”掷硬币。
- **元数据默认值显式化**：图上没写的字段用默认值，并在报告里列为假设。
- **合法不等于正确**：`check` 只证明 FEN 合法；`annotate` 的逐格审计才证明它对应图片。
- **不恢复被裁掉的信息**：边缘缺一格、缺一个子，就要求换一张完整图，而不是猜。
- **不伪造历史**：不因为王车在原位就写 `KQkq`，不因为“看起来能吃过路兵”就写目标格。
- **原图只读**：所有中间产物写到 `work/`，不改动输入图片。

## 限制

- 只支持平面 2D 棋盘；照片透视严重时先裁剪、矫正，再跑 `prepare`。
- 极低分辨率、棋子被箭头/高亮大面积遮挡时，识别会退化；技能会明确报告不确定的格子，而不是给一个虚假的置信度。
- 图上有多个棋盘时，需要先裁出目标棋盘；每个棋盘单独转写。
- 不处理 Chess960 的易位权记法（标准 FEN 的 `KQkq` 之外的文件字母形式）。
- 不判断三次重复；50 回合规则只能提供当前半回合钟，不能还原完整对局历史。
- 3D 棋子、动画截图、严重压缩伪影不在保证范围内。

## 常见问题

**技能没有出现在列表里？**
先看 [INSTALL.md 的故障排查](INSTALL.md#7-故障排查)。最常见的原因是放错层级（`<root>/chess-diagram-to-fen/SKILL.md` 才是对的）、DSH 会话不在项目根，或客户端需要重开会话。

**`prepare` 说找不到 8×8 网格？**
这不是安装问题。用 `grid` 生成带像素坐标的图，读出棋盘外框的 `x0,y0,x1,y1`，再跑 `prepare --bbox`。框的是棋盘外网格线，不是纸张边缘。

**图是黑方视角？**
加 `--flip`。印刷坐标跟着棋子走，翻转后接触图会归一化为白方在下。

**一页有好几张图？**
先裁出目标棋盘，再逐张处理。不要把整页扔给识别。

**FEN 合法，但和图片不一样？**
跑 `annotate`，把 FEN 的符号盖回原图逐格看。合法只说明局面没违反规则，不说明读对了。

**能直接读 PGN 吗？**
这个技能的目标是“图 → 局面 FEN”。PGN 是另一类输入；如果你有棋谱，直接用棋谱回放更可靠。

## 许可证

本仓库按内容类型使用两个许可证：

| 内容 | 许可证 | 文件 |
|---|---|---|
| 软件与脚本（`scripts/` 下的 Python 代码、`requirements.txt` 等） | MIT | [LICENSE-MIT](LICENSE-MIT) |
| 文档、技能说明、参考文本及其他非代码内容（`README.md`、`INSTALL.md`、`AGENTS.md`、`SKILL.md`、`references/`） | CC0 1.0 Universal | [LICENSE-CC0](LICENSE-CC0) |

- MIT 允许商用、修改、再分发，要求保留版权与许可声明。
- CC0 在适用法律允许的最大范围内放弃版权及相关权利，不要求署名。
- MIT 的版权行目前写作 `Copyright (c) 2026 boardtofen contributors`；以个人或组织名义发布时，替换成实际版权人即可。

## 参考

- [Agent Skills 规范](https://agentskills.io/specification)：`SKILL.md`、`references/`、`scripts/` 的通用格式
- [PGN 标准](https://www.saremba.de/chessgml/standards/pgn/pgn-complete.htm)：FEN 与 PGN 的正式定义
- [python-chess](https://python-chess.readthedocs.io/)：合法性校验与棋谱解析
- [`SKILL.md`](.dsh/skills/chess-diagram-to-fen/SKILL.md)：本技能的完整七步协议
- [`INSTALL.md`](INSTALL.md)：各客户端安装、依赖、自检、故障排查

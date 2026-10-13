# Vine (藤蔓) - 面向高智商 AI Agent 的轻量敏捷工程化底座

> **告别繁文缛节，释放前沿模型真正潜能。**  
> 融合 **Trellis** 的生命周期管理与自动 Hook 注入、**Ponytail** 的极简高级工程师哲学、与 **grill-with-docs** 的苏格拉底式启发提问与活文档沉淀。

---

## 为什么需要 Vine？

现如今，前沿大模型（如 Gemini 2.5/3、Claude 3.5/3.7、GPT-4.5/o1/o3）的代码与逻辑推理能力大幅提升。早期 AI 编码框架（如 Trellis）中将模型视为“弱智流水线工人”的机械化强约束——如**强制每轮只能问一个问题**、**强制切分多层 PRD/Design/Implement 琐碎文件**、**强制双阶段子代理分发**等——反而成了束缚模型智能的沉重枷锁，带来了严重的 Token 消耗、流程卡顿与心智负担。

**Vine** 的核心理念是：**给模型以思考自由，给工程以坚实防护**。

### 三大开源精粹融合矩阵

| 开源项目 | 汲取的精华 | 彻底舍弃的繁缛/痛点 | 在 Vine 中的新实现 |
| :--- | :--- | :--- | :--- |
| **mindfold-ai/Trellis** | 1. 任务全生命周期管理<br>2. 自动 Hook 动态上下文注入<br>3. 跨会话 Spec 与记忆沉淀 | 1. 繁琐冗长的 4 阶段审批流水线<br>2. 强制只能单问单答的流程手铐<br>3. 强制多子代理（Implement/Check）派发<br>4. 数万行多语言混杂的沉重运行时 | **零依赖纯 Python 3 内核**，任务看板轻量透明；毫秒级极速 Hook 矩阵；任务完成时自动经验萃取。 |
| **DietrichGebert/ponytail** | 1. 极简解题阶梯（The Ladder）<br>2. 绝不写没被要求的封装与抽象<br>3. 核心逻辑配小测，安全边界严防死守<br>4. 故意技术债标注：`shortcut:` | 无独立任务管理系统，仅依赖会话 diff | **植入 Agent 核心直觉**，在任何编码动作中优先复用代码库与标准库，回复末尾透明交代遗漏与风险。 |
| **mattpocock/skills (grill-with-docs)** | 1. 决策树前沿（Frontier）成组提问<br>2. 提问附带推荐选项（支持单字 `yes` 确认）<br>3. 自主探查代码库事实，不问已知代码<br>4. 实时沉淀 `glossary.md` 词汇表与 ADR 决策 | 单次会话容易丢失，且部分实现因依赖多 Skill 易发生加载失效 | **原生 Socratic Frontier Brainstorming**，规划期模型主动探查事实，成组推进决策并实时写入活文档。 |

---

## 快速上手

### 1. 安装

Vine 基于纯 Python 3 标准库构建，跨 Windows/macOS/Linux 均零外部依赖：

```bash
# 进入你的项目目录
cd your-project

# 安装并全局/本地可用
pip install -e /path/to/Assistant
# 或者直接通过 python -m vine 调用
```

### 2. 在项目中初始化（支持类似 Trellis 的按需指定平台）

```bash
# 默认初始化（自动检测或安装标准平台）
vine init -u your-name

# 或仅按需初始化你实际使用的平台：
vine init --cursor --opencode --codex -u your-name
vine init --claude --pi -u your-name

# 或一次性初始化所有平台：
vine init --all -u your-name

# 在已有项目中随时按需追加平台：
vine add codex
vine add pi
```
支持的平台包括：
- `--claude`: 生成 `.claude/settings.json`（SessionStart 与 UserPromptSubmit Hook）
- `--cursor`: 生成 `.cursor/rules/vine.mdc`
- `--pi`: 生成 `.pi/extensions/vine.js`
- `--codex`: 生成 `.codex/hooks.json`
- `--opencode`: 生成 `.opencode/hooks.json`
- `--gemini`: 生成通用 `AGENTS.md`
- 核心底座：总是生成 `.vine/`（任务、规约与原生轻量 Hook）

### 3. 在 Pi Coding Agent (pi) 中使用

Vine 原生提供针对 Pi Agent (`@mariozechner/pi-coding-agent`) 的扩展支持：

```bash
# 方式 1：通过 Pi 包管理器直接安装
pi install npm:vine-harness
# 或从 GitHub 安装
pi install git:github.com/your-username/vine-harness

# 方式 2：在任意已执行 vine init 的项目中直接启动 pi
pi
```
在 Pi 终端交互中即可获得：
- 启动自动检测活跃任务并注入上下文；
- 专属快捷斜杠指令：`/vine [status|new|done|review]`、`/grill`、`/vine-review`。

---

## 核心工作流与命令

```
  [1. 启发式规划]                  [2. 极简实现]                 [3. 知识沉淀]
   vine task new                   Ponytail 阶梯                vine task done
         │                               │                             │
         ▼                               ▼                             ▼
Socratic Frontier 提问 ───────► 编写最小有效代码 ───────► 自动萃取经验至
自主探查事实，更新词汇与ADR        高危逻辑配微测试，标 shortcut:       .vine/spec/conventions.md
```

### 任务生命周期管理 (`vine task`)

```bash
# 创建任务并进入 planning 状态（自动设为当前激活任务）
vine task new "实现速率限制器" --desc "基于令牌桶算法的高吞吐 API 速率控制"

# 查看当前活跃任务详情与 Spec 摘要
vine task status

# 列出所有任务与看板
vine task list

# 切换激活任务
vine task start 2026-10-13-rate-limiter

# 标记完成：自动触发经验萃取，提取 shortcut 标注和复盘要点到规范库
vine task done

# 归档已完成任务
vine task archive 2026-10-13-rate-limiter
```

### 活文档与规约管理 (`vine spec`)

```bash
# 浏览当前沉淀的规约、架构或词汇表
vine spec show [conventions|architecture|glossary]

# 在头脑风暴中澄清关键术语，实时写入领域词汇表
vine spec term "TokenBucket" "令牌桶算法，平滑限制瞬时并发" --context "API Gateway"

# 记录重大技术权衡与架构决策 (ADR)
vine spec adr "使用内存存储代替Redis" \
  --context "当前为单实例部署，Redis引入额外网络延迟" \
  --decision "采用Python内置线程安全字典" \
  --consequences "极大降低延迟与运维复杂度，未来多实例扩展时需重构"
```

### 极简工程师自检清单 (`vine review`)

```bash
vine review
```
输出 Ponytail Senior Dev 评审标准：检查越界影响、删除臆测性包装、核验安全边界与遗漏测试。

---

## 自动 Hook 注入机制

Vine 包含毫秒级原生 Hook 脚本（位于 `.vine/hooks/`）：
1. **`session_start.py`**: 会话启动时瞬间唤醒（执行时间 < 30ms），向 AI 注入当前活跃任务的最新 Spec、工程底线与架构关键约定。
2. **`prompt_submit.py`**: 每一轮提问时注入极简的单行状态锚点（例如 `[Vine | Active Task: 实现速率限制器 (active)]`），确保模型始终聚焦目标，无需漫长死板的阶段强制卡点。

---

## 目录结构一览

```
your-repo/
├── .vine/
│   ├── config.json              # 项目与当前会话配置
│   ├── tasks/                   # 任务看板 (每个任务包含独立的 spec.md 与 notes.md)
│   ├── archive/                 # 已归档的历史任务
│   ├── spec/                    # 活文档仓库
│   │   ├── architecture.md      # 系统边界与架构基线
│   │   ├── conventions.md       # 代码规约与沉淀出的经验
│   │   ├── glossary.md          # 领域词汇表
│   │   └── adr/                 # 架构决策记录 (ADR)
│   ├── workspace/               # 跨会话个人日志 (journal.md)
│   └── hooks/                   # 平台注入脚本 (session_start.py, prompt_submit.py)
├── AGENTS.md                    # 针对各类 Coding Agent 的通用行为准则
└── ...
```

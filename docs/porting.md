# 跨宿主移植架构（Claude / Codex）—— 维护者指南

本 skill 需在两种宿主运行：**Claude Code**（`SKILL.md` + Skill 工具 + 原生 subagent + `document-skills:docx` 插件）与 **Codex**（`AGENTS.md` + 无原生 subagent + `python-docx` 直连）。

采用**单内核 + 薄适配层**，避免两份副本漂移。

## 1. 什么是内核（core），什么是适配层

| 类别 | 文件 | 两端是否一致 | 归属 |
|---|---|---|---|
| 领域规则 | `references/rules/*.md` | 逐字一致 | **core** |
| 案例知识 | `references/cases/*.md` | 逐字一致 | **core** |
| 校验脚本 | `scripts/*.py` | 逐字一致（跨平台已验证） | **core** |
| 模板资产 | `assets/docx/*` | 逐字一致 | **core** |
| subagent 契约 | `agents/*.md` | 逐字一致（宿主差异写在契约内的"跨宿主说明"） | **core** |
| 通用文档 | `rules.md`、`docs/install.md`、`docs/porting.md` | 逐字一致 | **core** |
| **Claude 入口** | `SKILL.md` | Claude 独有 | **claude 适配** |
| **Codex 入口** | `AGENTS.md` | Codex 独有 | **codex 适配** |

**铁律：任何领域规则、脚本、模板改动只落 core，绝不落适配层。** 适配层只写"这个宿主怎么编排 core"，不含任何规则内容。

## 2. Git 分支结构（core + 两适配分支）

```
core          内核开发主线: references/ scripts/ assets/ agents/ rules.md docs/
              （不含 SKILL.md / AGENTS.md 任一入口的宿主专属编排差异）
 ├── claude   = core + SKILL.md（Claude 宿主入口）
 └── codex    = core + AGENTS.md（Codex 宿主入口）
```

> 现状过渡：`subagent` 分支即当前 core 开发线。两个适配分支从它派生。

### 改一条规则的正确流程

1. 在 **core** 分支改 `references/`（或 `scripts/`、`agents/`），跑 `python3 tests/test_scripts_smoke.py`。
2. 把 core merge 进 `claude` 与 `codex` 两个适配分支。
3. 因为适配分支只在 core 之上**新增**了各自入口文件、未改 core 内容，merge **无冲突**。
4. 两个宿主版本同步完成，零漂移。

### 反模式（不要做）

- ❌ 在 `claude` 或 `codex` 分支直接改规则——会造成两端分叉。规则改动一律回 core。
- ❌ 把规则内容抄进 `SKILL.md` / `AGENTS.md`——入口文件只写编排，规则永远指向 `references/`。
- ❌ 两个平台各存一份完整副本（裸 fork）——90% 内容冗余，同步即冲突。

## 3. 两端编排差异对照（唯一出处 = 各自入口文件）

| 能力 | Claude（`SKILL.md`） | Codex（`AGENTS.md`） |
|---|---|---|
| 环境自检 | `check_env.py --json`（检测 docx 插件） | `check_env.py --host codex --json`（跳过插件） |
| 事实提纲 | 独立 Agent `disclosure-analyst` | 主 agent 按契约自查 |
| 规则外审 | 独立 Agent `rule-auditor`（物理隔离） | 主 agent 按契约自查（无独立性，标注 + 依赖脚本闸门） |
| DOCX 执行 | `document-skills:docx` 插件 | `python-docx` / XML 直接编辑 |

## 4. 能力差异的诚实边界

Codex 无原生独立 subagent，`rule-auditor` 退化为主 agent 自查，**语义层防确认偏差弱于 Claude**。这是宿主能力差异、非规则差异。弥补：

- 机械项（`check_hard_rules`）+ 结构项（`check_cross_block`）两端脚本判定**逐字节一致**，是不依赖宿主的硬防线——实战中字数踩线、结构不同构等问题主要由脚本拦截。
- Codex 端语义自查须逐条附原文证据、不得无证据 PASS，并在完工报告标注"无独立外审"。

## 5. 校验清单（每次同步后）

- [ ] `python3 tests/test_scripts_smoke.py` 全绿（core 分支）。
- [ ] `python3 scripts/check_env.py --host claude --json` 与 `--host codex --json` 均能产出合法 JSON。
- [ ] `SKILL.md` / `AGENTS.md` 中无规则正文，只有编排（grep 关键规则编号如 `L1-1` 不应出现在入口文件的规则定义位置，只能出现在"指向 references"的引用里）。
- [ ] 两适配分支相对 core 的 diff 只含各自入口文件。

# 跨宿主移植架构（Claude / Codex）—— 维护者指南

本 skill 需在两种宿主运行：**Claude Code**（`SKILL.md` + Skill 工具 + 原生 subagent + `document-skills:docx` 插件）与 **Codex**（`SKILL.md` + `agents/openai.yaml` + 无原生 subagent + `python-docx` 直连）。

**两个宿主都以 `SKILL.md` 为 skill 入口**（Codex skill 打包规范与 Claude 一致：顶层 `SKILL.md` 带 `name`/`description` frontmatter；Codex 另需 `agents/openai.yaml` 界面清单）。区别不在文件名，而在**同名 `SKILL.md` 的内容范式**与所在**分支**。

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
| **入口 `SKILL.md`** | Claude 范式（claude 分支）/ Codex 范式（codex 分支） | 同名不同内容，各分支专属 | **适配层** |
| **Codex 界面清单** | `agents/openai.yaml` | 仅 codex 分支 | **codex 适配** |

**铁律：任何领域规则、脚本、模板改动只落 core，绝不落适配层（`SKILL.md` / `openai.yaml`）。** 适配层只写"这个宿主怎么编排 core"，不含任何规则内容。

## 2. Git 分支结构（claude 权威 + codex 适配）

```
claude        权威分支 = core 开发主线（references/ scripts/ assets/ agents/*.md rules.md docs/）
              + SKILL.md(Claude 范式)
 └── codex    = merge claude + SKILL.md(Codex 范式) + agents/openai.yaml
```

> `SKILL.md` 在两个分支同名但内容不同，故它是**适配层**、不跨分支共享。claude→codex 的 merge 若碰到 `SKILL.md`，以 codex 自身版本为准（`git checkout --ours SKILL.md`）；core 改动不碰 `SKILL.md`，正常 merge 无冲突。

> 历史沿革：早期存在独立的 `subagent` 分支作为 core 开发线，2026-07 起退役删除——其内容与 claude 分支完全重复。现在 **core 改动直接在 claude 分支做**（与"Claude 版权威 → Codex 适配同步"的协作约定一致）。

### 改一条规则的正确流程

1. 在 **claude** 分支改 `references/`（或 `scripts/`、`agents/`），跑 `python3 tests/test_scripts_smoke.py`。
2. 把 claude merge 进 `codex`；若 `SKILL.md` 冲突，执行 `git checkout --ours SKILL.md` 保留 Codex 范式。
3. 检查 codex 分支的 `SKILL.md` 编排是否需要随 core 变化同步调整（如新增/退役 subagent 契约时更新编排差异表）。
4. 两个宿主版本同步完成，零漂移。

### 反模式（不要做）

- ❌ 在 `codex` 分支直接改规则——core 改动单向流：只在 claude 分支做，codex 只接收 merge。
- ❌ 把规则内容抄进 `SKILL.md`（任一范式）——入口文件只写编排，规则永远指向 `references/`。
- ❌ 两个平台各存一份完整副本（裸 fork）——90% 内容冗余，同步即冲突。

## 3. 两端编排差异对照（唯一出处 = 各自入口文件）

| 能力 | Claude（claude 分支 `SKILL.md`） | Codex（codex 分支 `SKILL.md`） |
|---|---|---|
| 环境自检 | `check_env.py --json`（检测 docx 插件） | `check_env.py --host codex --json`（跳过插件） |
| 事实提纲 | 主 agent 深读交底书时亲自产出 `docs/facts.md`（`disclosure-analyst` 已废弃，契约备查 `docs/archive/disclosure-analyst.deprecated.md`） | 同左 |
| 规则外审 | **`Workflow` 工具编排多路并行独立 agent**（每路一个 `agent()`）：权要稿 = `claims-auditor` + `global-auditor`；全文稿 = `content-auditor` + `impl-auditor` + `global-auditor`（物理隔离，每路只带本路规则包；Workflow 不可用时整级降级为分轮自查） | 主 agent 按同一组契约**分轮自查**（每轮只带一路规则包，获得同等注意力集中收益；无独立性，标注 + 依赖脚本闸门） |
| DOCX 执行 | `document-skills:docx` 插件 | `python-docx` / XML 直接编辑 |

## 4. 能力差异的诚实边界

Codex 无原生独立 subagent，多路审查（multi-auditor）退化为主 agent 分轮自查，**语义层防确认偏差弱于 Claude**。这是宿主能力差异、非规则差异。弥补：

- 机械项（`check_hard_rules`）+ 结构项（`check_cross_block`）两端脚本判定**逐字节一致**，是不依赖宿主的硬防线——实战中字数踩线、结构不同构等问题主要由脚本拦截。
- Codex 端语义自查须逐条附原文证据、不得无证据 PASS，并在完工报告标注"无独立外审"。

## 5. 校验清单（每次同步后）

- [ ] `python3 tests/test_scripts_smoke.py` 全绿（core 分支）。
- [ ] `python3 scripts/check_env.py --host claude --json` 与 `--host codex --json` 均能产出合法 JSON。
- [ ] `SKILL.md`（两范式）中无规则正文，只有编排（grep 关键规则编号如 `L1-1` 不应出现在入口文件的规则定义位置，只能出现在"指向 references"的引用里）。
- [ ] 两适配分支相对 core 的 diff 只含各自入口文件。

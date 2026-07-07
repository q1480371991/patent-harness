# patent skill — Codex / AGENTS.md 适配层

本文件是 `patent` skill 在 **Codex（AGENTS.md 宿主）** 下的编排入口。

**架构约定（单内核 + 薄适配层）**：领域规则、校验脚本、模板、产物结构与 Claude 端**共享同一份内核**，不复制、不分叉：

- `references/rules/*.md`、`references/cases/*.md` —— 规则与案例，**唯一权威**，两端逐字一致。
- `scripts/*.py` —— 校验脚本，纯 Python 跨平台，两端跑出的判定结果逐字节一致。
- `assets/docx/专利撰写模板.docx` —— 模板资产。
- `agents/*.md` —— subagent 的 Input/Output/失败契约（在本宿主下由主 agent 按契约自查执行，见下）。

本文件**只**描述 Codex 相对 Claude（`SKILL.md`）的编排差异。任何领域规则改动只改 `references/`，两端自动同步；**不要**把规则内容抄进本文件。

---

## 0. 接入前环境自检（首次接入必做）

```bash
python3 scripts/check_env.py --host codex --json
```

- `python-docx`（pip/必需）缺失 → `python3 scripts/check_env.py --host codex --fix` 自动安装。
- `python ≥ 3.9`（系统级/必需）→ 按 `install_hint` 引导用户装。
- `pandoc`（可选）→ 缺失不阻断。
- `--host codex` 下**不检测 `document-skills:docx` 插件**（Codex 无此插件），DOCX 能力由 `python-docx` 直接提供，已被 python-docx 必需项覆盖。

`missing_required=0` 即可开工。

## 1. 规则读取与闸门（与 Claude 完全一致）

- 按 `rules.md` 阶段读取表读 `references/rules/global.md` + 当前阶段规则，渐进式披露，不越读无关阶段。
- 写入 DOCX 前的两道机械化闸门与 Claude 端逐字一致：
  ```bash
  python3 scripts/check_hard_rules.py --md <稿件> --stage <claims-draft|full-draft> --json
  python3 scripts/check_cross_block.py --md <稿件> --stage <阶段> [--claims-md <权要稿>]
  ```
  任一 FAIL 定点回修再重跑，不跳过。

## 2. 编排差异（本文件的核心）

| 能力 | Claude（SKILL.md） | Codex 适配（本文件） |
|---|---|---|
| 入口触发 | `SKILL.md` frontmatter + Skill 工具自动发现 | 本 `AGENTS.md` + 用户显式请求撰写专利 |
| 事实提纲 `disclosure-analyst` | 独立 Agent（独立上下文） | 主 agent **按 `agents/disclosure-analyst.md` 契约自行提取**（无独立上下文）；输出仍须满足该契约的 6 段结构、创新点只摘批注、优审关键词照抽 |
| 规则外审 `rule-auditor` | 独立 Agent（物理隔离，消除主 agent 自评确认偏差） | 主 agent **按 `agents/rule-auditor.md` 契约自查**——**失去独立性**：完工报告必须标注"本宿主无独立外审，auditor 为主 agent 自查"；**硬防线以脚本闸门为准**（`check_hard_rules` + `check_cross_block` 两端等价，不依赖独立性）。语义项自查仍按 auditor 的"语义项必审清单"逐条给证据 |
| DOCX 执行层 | 官方 `document-skills:docx` 插件 | **直接用 `python-docx` / 直接编辑解包后的 `word/document.xml`**（留痕返修本就是 XML 层最小侵入注入）；读交底书用 `scripts/disclosure_docx_to_md.py`；骨架保护规则同 `docx-template.md` G8-0/G8-1，不清空 body、保留 sectPr/header/headerReference |
| 工具名 | Read / Bash / Edit / Write | Codex 的 shell / 文件读写 / apply_patch（语义对应，不改行为） |

## 3. 不变量（两端必须逐字一致，改一处即两端同步）

- 领域规则判定、脚本 PASS/FAIL 口径、模板骨架、案件目录约定（案件根目录放交付 DOCX，工作文件放 `docs/`）。
- 产物结构：`docs/facts.md`、`docs/权要稿.md`、`docs/全文稿.md`、`docs/审查报告-*.md`。
- 返修署名不设默认值，每次由用户提供（见 `SKILL.md`「默认立场」，规则同源）。
- 创新点以交底书批注圈定为准，不自行另判（`global.md` G2-1）。

## 4. 诚实边界

Codex 端因无原生独立 subagent，`rule-auditor` 退化为主 agent 自查，**语义层防确认偏差能力弱于 Claude 端**。这是宿主能力差异，不是规则差异——弥补方式是把尽可能多的质量约束压进 `scripts/` 客观闸门（机械项 + 结构项两端等价），语义项自查须逐条附原文证据、不得无证据给 PASS。

# 专利撰写规则索引

本文件是 patent skill 的当前唯一规则索引。具体规则按阶段渐进式读取，旧版完整规则仅保留在 `docs/archive/` 作为历史备查，正常工作流不得读取或执行。

## 默认读取

每次调用 patent skill 时，先读取：

- `references/rules/global.md`

再根据当前任务阶段读取下列阶段规则。不要默认读取无关阶段规则，避免把其他稿次的约束带入当前上下文。

## 阶段读取表

下表三列分别为：**必读核心**（该阶段每次都加载）、**触发式按需**（命中触发条件才加载，省 token）、**禁止默认读取**。触发式块的具体触发条件见各规则文件内的触发索引（如 `revision.md` A4-0）和 `references/cases/INDEX.md`。

| 阶段 | 必读核心 | 触发式按需（命中才读） | 禁止默认读取 |
|---|---|---|---|
| 权要一稿 | `global.md`、`claims.md`、`scoring.md`、`docx-template.md` | — | `full-draft.md`、`figures.md`、`revision.md` |
| 权要二稿/三稿 | `global.md`、`claims.md`、`scoring.md`、`revision.md`（G9+通用返修+A4-1核心）、`docx-template.md` | `revision.md` A4-0 触发块（删除类/算法类/序号类）；`cases/INDEX.md`（挂回复批注、清痕等） | 未被批注涉及的全文块规则 |
| 全文一稿 | `global.md`、`full-draft.md`、`scoring.md`、`figures.md`、`docx-template.md` | — | `claims.md`（权要已冻结，仅用户明确要求改权要时读）、`revision.md`，除非存在批注或权要联动 |
| 全文二稿/三稿 | `global.md`、`full-draft.md`、`scoring.md`、`revision.md`（G9+通用返修+A4-1核心）、`figures.md`、`docx-template.md` | `revision.md` A4-0 触发块；`cases/INDEX.md` | `claims.md`，除非批注涉及权要联动 |
| Word 批注返修 | `global.md`、`revision.md`（G9+通用返修+A4-1核心）、`docx-template.md`，并按批注内容读 `claims.md`/`full-draft.md`/`figures.md` | `revision.md` A4-0 触发块（按批注命中）；`cases/INDEX.md`（按操作命中） | 未被批注涉及且无必要联动的内容块规则 |

> **docx-template.md 分层读取**：md 撰写阶段只读 G8-0 / G8-0b 及 md 层可判定条目；G8-1 XML 骨架与注入细节延后到进入 DOCX 执行层（SKILL.md step 8-12）时再读，避免前置占用撰写上下文。
| DOCX 格式修复 / 模板写入 / XML 验证 | `global.md`、`docx-template.md`，并读当前稿次对应规则 | `cases/INDEX.md`（批注挂载、清痕、schema 顺序等执行陷阱） | 与格式无关且未涉当前稿次的规则 |
| 附图设计 | `global.md`、`figures.md`，如需全文一致性再读 `claims.md` 和 `full-draft.md` | — | `revision.md`，除非存在批注返修 |

**加载顺序**：先读必读核心 → 判断当前批注/操作命中哪些触发条件 → 只加载命中的触发式块或 cases 详情。不得为省事一次性全量加载，也不得跳过命中的触发块导致漏规则。

## 交底书阅读时机

交底书阅读时机（仅一稿阶段深读、返修默认不读及其例外）的唯一权威出处是 `references/rules/global.md` G2，本索引不重复其内容。

## 规则文件职责

- `references/rules/global.md` — 全部阶段默认读取的全局硬规则：文件命名、交底书理解、技术链条闭合、术语与“所述”、禁用措辞、公式/模型/阈值、Markdown 优先和跨阶段自检。
- `references/rules/claims.md` — 权要阶段规则：权利要求书、技术领域、背景技术、权要格式标准与权要阶段自检。
- `references/rules/full-draft.md` — 全文稿规则：说明书摘要、摘要附图、发明内容、附图说明、具体实施方式和全文公开充分自检。
- `references/rules/revision.md` — 统一返修规则：通用返修原则、权要返修、全文返修、老板批注、DOCX 留痕返修和学习闭环。
- `references/rules/docx-template.md` — DOCX 模板和执行层规则：`docx` skill 边界、模板资产、分节↔页眉↔正文内容对照表（G8-0）、章节标题与正文格式（G8-0b）、`sectPr`、`header*.xml`、`headerReference`、案例性术语清理和 XML 骨架验收。
- `references/rules/figures.md` — 附图设计规则：L9 图 1/子流程图/系统图/摘要附图与 Visio 手画提示；L10 给生图模型的「结构示意图提示词」生成规则（用户要 AI 出图提示词、需体现创新点的实物/场景图时读 L10）。
- `references/rules/scoring.md` — md 审查评分卡：权要稿/全文稿写入 DOCX 前的"完整性一票否决 + 质量百分制"质量闸门；只规定评分机制，逐项引用 G/L 规则编号，不复述规则内容。

## 冲突处理

- 用户明确指示 > 老板批注 > 当前阶段硬规则 > 全局硬规则 > 当前阶段质量优化规则。
- **单一出处原则**：每条规则只有一个权威出处文件，其他文件只允许一句话指针（点名规则编号或文件名，不复述内容）。学习闭环沉淀新规则时，先确定唯一归属文件再写入；发现同一内容出现在两处时，保留权威出处、把另一处改为指针。

## 沉淀分诊纪律（防规则膨胀）

每次返修/撰写收尾沉淀新经验时，先按下表分诊到正确层级，避免必读层无限变重：

| 经验类型 | 判据 | 去向 | 形态 |
|---|---|---|---|
| **主动义务型** | 每次撰写/返修都需主动遵守，不读到就会违反（如链条闭合、术语一致、权要改算法后说明书同步、去序号词全文联动） | `references/rules/` 必读核心 | 精简条目，一句话讲“做什么” |
| **触发式义务** | 只在批注/任务命中特定条件时才需遵守（如删除类、算法类、序号类） | `references/rules/` 对应触发块，并登记到该文件触发索引 | 条目，标注触发条件 |
| **避坑型/执行细节** | 只在做某个具体 DOCX/XML 操作时才需要，平时用不上（如 comment.py 孤立部件、清痕清单、schema 子元素顺序） | `references/cases/` 对应文件，并登记到 `cases/INDEX.md` | 可含 Why/How 详情 |
| **完整案例** | 整篇定稿经验，供对照学习 | `references/cases/` 独立文件，登记到 `cases/INDEX.md` 完整案例节 | 案例全文，本案技术对象名不外迁 |

分诊纪律附加约束：

- **必读核心文件设软上限**：单个 `references/rules/*.md` 超过约 250 行时，触发审查——把其中“触发式义务”切成带触发索引的子块、把“避坑型”下移到 `references/cases/`，必读核心只留高频主动义务。
- **沉淀前先查重**：新经验若与现有规则“精神相同、只是换了案例”，不新增条目，只在 `cases/` 加案例指针或在原条目后补一句限定。
- **L1 写“做什么”、L2 写“怎么做+为什么”**：必读规则层保持条目式，Why/How、XML 片段、操作步骤进 `cases/`。
- **完整性优先于省 token**：主动义务型一律留必读层，不得为减重下移；省 token 只能靠“避坑型下移 + 触发式按需加载”，不能靠少读主动义务。
- 批注与交底书、可实施性或强制规则冲突时，先询问用户，不要静默违反任何一方。
- 具体案例只放 `references/cases/`，不要内联进本规则索引或通用规则正文。
- `docs/archive/` 只作历史备查，正常工作流不得读取或执行其中旧规则、旧脚本。

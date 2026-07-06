# patent skill subagent 拆分方案 — 修正稿

本稿基于原方案 `patent-skill-subagent-拆分方案.md`，结合现有 `patent` skill 实际结构（`SKILL.md` 18KB / `rules.md` 阶段读取表 / `references/rules/*` 单一出处 / `references/cases/*` 案例层 / `docx` 执行层已分离）做增删。凡是原方案已经写对且落地无风险的部分，本稿只保留结论、不再重复论证；重点写"哪里要改"和"改成什么"。

---

## 1. 对原方案的整体判断

### 1.1 判断准确、无需改动的部分

- **不把 skill 整体外包，`patent` 继续做主控**：符合现有 `SKILL.md` 中 `patent` 与 `docx` 的职责分工，也符合"跨块规则不能下放到 subagent"的事实。
- **按职责拆而非按章节拆**：原方案 §6.1 已经明确否定"每章节一个 agent"，这个判断正确，本稿沿用。
- **写作与审查必须分离**：这是原方案最有价值的一条。现有 `scoring.md` 虽然定义了评分卡，但主 agent 自评自检，天然存在放水风险，独立审计是唯一稳定解。
- **主控只维护共享真相**：符合现有 `rules.md` 的阶段读取表和"渐进式披露"设计，方向正确。
- **给每个 subagent 限定只读规则范围**（原方案 §9.2）：与现有渐进式披露机制天然吻合，直接沿用。

### 1.2 需要修正的部分

以下四条是本稿的主要修正点，详见后文各节：

1. **不拆 `claims-writer` 和 `full-draft-writer`**（写作留在主 agent）。
2. **不拆 `docx-verifier`**（业务验收本就是 `patent` 职责，`docx` skill 已负责通用 DOCX 验证）。
3. **MVP 从 3 个 subagent 收窄到 2 个**：先只做 `rule-auditor` 和 `disclosure-analyst`，`revision-mapper` 放第二阶段。
4. **共享中间产物需要落地为明确的 prompt 契约**，否则"共享真相"会退化成"多副本各自演化"。
5. **`disclosure-analyst` 只能做预提纲，不替代主 agent 深读交底书**。

---

## 2. 修正点 1：不拆写作类 subagent

### 2.1 原方案位置

原方案 §4.3 `claims-writer` 与 §4.4 `full-draft-writer`。

### 2.2 修正理由

Claude Code 的 subagent 是独立 context，主 agent 只能拿到 subagent 的最终返回文本，中间 tool use、规则读取过程、边写边查的思考轨迹全部不可见。而专利写作是"密集引用规则 + 密集回查交底书 + 边写边核对权要一致性"的联动过程：

- **写作阶段的细粒度联动会丢失**：例如"具体实施方式写到 S3 时回头查权要 1 步骤是否漏落"这种联动，在 subagent 内部完成后主 agent 无法看到过程，只能拿到成品，出问题时定位困难。
- **token 总量不减反增**：subagent 需要主 agent 把 `global.md + claims.md + facts.md + 已冻结权要 + 交底书相关段落` 作为 prompt 传过去。原本主 agent 一次会话中共享的上下文，拆成 subagent 后每次调用都要重传，反而更贵。
- **`full-draft.md`「全文稿分块撰写法」本就要求分块写、逐块自检**：这已经是"主 agent 内部的分块流水线"，等价于原方案想要的"分工"，不需要再拆 subagent。

### 2.3 修正结论

**写作留在主 `patent` agent**。等 §5 的 MVP 稳定、并且真正观察到"审计/事实抽取已稳定但写作仍不稳"的证据后，再考虑二次拆分。

---

## 3. 修正点 2：不拆 `docx-verifier`

### 3.1 原方案位置

原方案 §4.7 `docx-verifier`。

### 3.2 修正理由

现有 `SKILL.md` 已经明确两级验收分工：

- `docx` skill 做**通用 DOCX 验证**（unpack/pack 完整性、schema 校验、`validate` 命令）。
- `patent` 主 agent 按 `docx-template.md` G8-0 / G8-0b / G8-1 做**业务验收**（分节落位、页眉可见性、模板残留、红蓝字清理、权要 1 字数、分号断行）。

再拆一个 `docx-verifier` subagent 会造成三层验收：docx 通用验证 → docx-verifier 中间层 → patent 业务验收。中间层没有独立价值，只是把主 agent 已经在做的事复制一份、增加协调成本。

### 3.3 修正结论

**保留现有两级验收结构不变**。`docx-template.md` 的业务验收由主 `patent` 完成，`docx` skill 只做通用 DOCX 验证。

---

## 4. 修正点 3：MVP 收窄到 2 个 subagent

### 4.1 原方案位置

原方案 §7「最小可落地版本」定义 MVP 为 3 个 subagent：`disclosure-analyst` / `rule-auditor` / `revision-mapper`。

### 4.2 修正理由

MVP 的目的是**用最小改动验证 subagent 协作机制本身是否可靠**（prompt 契约、共享文件、返回格式的稳定性），而不是一次性覆盖所有能拆的职责。

三个 subagent 里：

- `rule-auditor`：**边界最清、收益最大**。输入固定（当前 md 草稿 + 当前阶段 + `scoring.md`），输出固定（评分卡 JSON/结构化报告），失败易归因。
- `disclosure-analyst`：**边界较清但语义复杂**。输入是交底书原文，输出是术语表/技术问题/主流程等结构化事实。语义解读容易漂移，需要真实案子验证提取质量。
- `revision-mapper`：**语义最重、上下文最杂**。批注理解需要同时看批注原文、原稿上下文、可能涉及的多个规则文件（`revision.md` + `claims.md`/`full-draft.md`/`figures.md`）、可能需要回查交底书。这本身就是主 agent 判断力最集中的地方，不适合作为 MVP 首批。

### 4.3 修正结论

**MVP 分两步走**：

- **第一步（先落 `rule-auditor`）**：只在 md 草稿写完、进入 DOCX 前调用。跑 1-2 个真实案子，验证审查稳定性、返回格式一致性、和主 agent 的回修联动是否顺畅。
- **第二步（再落 `disclosure-analyst`）**：只在权要一稿、全文一稿两个"深读交底书"节点调用（符合 `global.md` G2），返修阶段默认不调。产出 `docs/facts.md` 供主 agent 使用。

**第二阶段再考虑 `revision-mapper`**。前两个稳定后，再评估是否值得拆批注映射。

**写作类 subagent 不进入路线图**，除非 MVP 之后仍能观察到写作层的具体不稳定证据。

---

## 5. 修正点 4：共享中间产物需要明确 prompt 契约

### 5.1 原方案位置

原方案 §8 列了 `facts.md` / `revision-plan.md` / `audit-report.md` 三个共享文件，但没定义"谁写谁读、什么时刻写读、传路径还是传内容"。

### 5.2 修正理由

subagent 是独立 context，主 agent 和 subagent 之间只能通过 prompt 传递信息。共享文件如果落地方式模糊，会出现两种失败模式：

- **只传路径给 subagent 自读**：subagent 需要重新读规则、重新解析文件结构，等于把主 agent 的"共享真相"重新自证一遍，成本翻倍且容易漂移。
- **主 agent 每次都把整个文件拼进 prompt**：token 成本高，且主 agent 需要判断"这次调用要拼哪些文件"，判断错就等于 subagent 缺规则。

### 5.3 修正结论：定义显式 prompt 契约

每个 subagent 定义三段固定契约：**Input Contract / Output Contract / Failure Contract**。主 agent 按契约拼 prompt，subagent 按契约返回，出错时按 Failure Contract 判定。

#### 5.3.1 `rule-auditor` 契约（第一步 MVP）

**Input Contract**（主 agent 调用时必传）：

- `stage`：当前阶段字符串。MVP 阶段仅接受 `claims-draft` 和 `full-draft`；返修阶段（`claims-revision` / `full-revision`）不在 MVP 范围，其调用时机与输入拼装留到 §8.3 第二阶段再补契约。
- `md_path`：待审 md 草稿的绝对路径。
- `scoring_rules_content`：`references/rules/scoring.md` 全文（直接拼入 prompt，不传路径）。
- `stage_rules_content`：当前阶段对应规则文件全文，主 agent 按 `rules.md` 阶段读取表决定拼哪些。各阶段完整拼装如下（不含已单独拼入的 `scoring.md`、`external_rule_refs_content` 与 `docx_visible_rules_content`）：
  - 权要一稿：`global.md + claims.md`
  - 全文一稿：`global.md + full-draft.md + figures.md`
  - （MVP 阶段返修节点不纳入，见 `stage` 字段说明）
- `docx_visible_rules_content`：从 `docx-template.md` 中**摘录** md 阶段可判定的条目，不整入全文。可摘录范围仅限：G8-0b 章节标题格式、发明名称格式；G8-1 中红蓝字占位是否清理、案例性术语是否清理、权要 1 字数、分号断行是否规范。**明确排除**：G8-0 分节落位、G8-1 中 `sectPr` / `header*.xml` / `headerReference` 骨架保护——这些必须解包 XML 才能验证，不在 auditor 的 md 阶段审查范围内，由 `docx` skill 通用验证 + 主 agent 业务验收覆盖。
- `external_rule_refs_content`：当前阶段评分卡显式依赖、但不在主规则正文中的外部规则全文。最典型的是 `claims-format-standard.md`；如果当前阶段命中了 `revision.md` 触发块或某个 `cases` 执行陷阱也必须一并传入，不能只传主规则文件。
- `triggered_rule_notes`：由主 agent 先判断本次任务命中了哪些触发式规则，简短列成清单传入 auditor，避免 auditor 在独立 context 里重新猜测是否该读某块。

**Output Contract**（subagent 必须返回的结构化文本）：

```
# 审查报告

## 完整性一票否决
- PASS / FAIL
- 若 FAIL，列出缺失的块或漏项（引用规则编号）

## 1 级硬规则
- 通过率：N/M
- 失败项：
  - [规则编号] 位置：md 第 X 行 / 章节 Y
    证据：原文引用
    应改为：具体修改建议

## 2 级质量分
- 通过率：N/M（阈值 ≥90%）
- 失败项：同上格式

## 最短回修清单
- 按优先级排序，每项含：位置、当前问题、目标状态
```

**Failure Contract**：

- 若 subagent 返回不含"完整性一票否决"段落或"最短回修清单"段落，主 agent 视为审计失败，重试 1 次；仍失败则回退到主 agent 自评并在完工报告中标注"auditor 未生效"。
- subagent 只输出报告，不修改 md、不改 DOCX。
- **工具白名单**（严格）：
  - 允许：`Read`（仅限主 agent 通过 Input Contract 传入路径的 md 草稿）、`Bash`（仅限确定性只读统计命令：`wc`、`grep`、`awk`、`sed -n`、`head`、`tail`、`diff`）。
  - 禁止：`Write`、`Edit`、`NotebookEdit`；任何 DOCX 相关工具或脚本；任何联网工具（`WebFetch`/`WebSearch`/MCP 网络工具）；任何 `Read` Input Contract 之外的规则文件（规则内容只能从 prompt 里获得，不允许自行去 `references/rules/` 或 `references/cases/` 读取）；任何写文件、修改环境或调用外部 skill 的操作。
- 如果 auditor 没拿到 `claims-format-standard.md` 或命中的触发式规则内容，应明确报告"输入规则不完整，审计结果不可信"，而不是假装完成全量审计。

#### 5.3.2 `disclosure-analyst` 契约（第二步 MVP）

**Input Contract**：

- `disclosure_md_path`：`docs/交底书.md` 绝对路径。
- `global_rules_content`：`global.md` 全文。
- `stage`：`claims-draft` 或 `full-draft`（决定提取深度）。

**Output Contract**：返回结构化事实提纲，由主 agent 审核通过后再写入 `docs/facts.md`。结构固定为：

```
# 案件事实包

## 技术问题
- 核心痛点 1
- 核心痛点 2

## 术语表
| 术语 | 定义 | 首次出现位置 |

## 主流程
- S1 …
- S2 …

## 创新候选点
- 候选点 1（仅描述交底书中可见的技术贡献，不判断保护策略）
- 候选点 2

## 数据来源 / 用途
| 数据 | 来源 | 用途 | 在交底书中是否核心 |

## 潜在风险
- 逻辑不闭合处
- 需要回查确认处
```

**Failure Contract**：

- subagent 只提取事实、不起草专利正文、不决定权要数量和保护策略。
- 若交底书某段无法解析或存在矛盾，写入"潜在风险"节而非静默省略。
- 主 agent 在调用 `disclosure-analyst` 后，仍需自行判断 facts.md 是否足以支撑写作；不足时不进入写作，而是回问用户。
- `disclosure-analyst` 不能替代主 agent 对 `docs/交底书.md` 的深读义务。主 agent 仍必须亲自过一遍高亮、批注和关键技术链，尤其要覆盖 `global.md` G2 要求的 `==高亮==` 与 `> 💡 [批注 ...]` 行。
- subagent 不直接写案件共享文件。`docs/facts.md` 由主 agent 根据 subagent 返回结果审核后落盘，避免把“共享真相”的第一次定稿权下放给 subagent。

### 5.4 共享文件的读写时序

| 时刻 | 动作 | 主体 |
|---|---|---|
| 权要一稿 / 全文一稿开始 | 调用 `disclosure-analyst`，拿到结构化事实提纲 | 主 agent |
| 事实提纲返回后 | 主 agent 审核提纲并写入 `docs/facts.md` | 主 agent |
| `facts.md` 生成后 | 主 agent 继续亲自深读 `docs/交底书.md`，核对高亮、批注、技术链和潜在风险 | 主 agent |
| 主 agent 写 `权要稿.md` / `全文稿.md` | 读取 `docs/facts.md` 作为事实基准，同时以原 `交底书.md` 为最终事实来源 | 主 agent |
| md 草稿写完、进入 DOCX 前 | 调用 `rule-auditor`，拿到审查报告 | 主 agent |
| 审查不通过 | 按最短回修清单改 md，重新调用 `rule-auditor` | 主 agent |
| 审查通过 | 进入 DOCX 执行层 | 主 agent + `docx` skill |
| 返修阶段（MVP 阶段） | 不调用 subagent，主 agent 沿用现有流程 | 主 agent |

---

## 6. 修正点 5：`disclosure-analyst` 只做预提纲，不替代深读

### 6.1 修正理由

现有 `global.md` G2 的约束不是“案件里有一个东西把交底书总结过”，而是“起草前主写作者必须充分理解交底书，并亲自处理高亮、批注、技术链和风险点”。  
如果把 `disclosure-analyst` 的输出当成主写作者的主要输入，容易产生一种危险错觉：主 agent 只要读 `facts.md` 就算完成了 G2。这个替代关系不成立。

`disclosure-analyst` 的正确定位应是：

- 帮主 agent 快速整理结构化事实
- 暴露潜在风险和模糊点
- 降低反复翻交底书的次数

但它不能替代：

- 主 agent 对 `==高亮==` 的逐条判断
- 主 agent 对 `> 💡 [批注 ...]` 的逐条判断
- 主 agent 对“技术问题—技术方案—技术效果”链条是否闭合的最终把关

### 6.2 修正结论

**`disclosure-analyst` 是预提纲器，不是交底书代理阅读器。**  
调用顺序必须是：

1. 由 `disclosure-analyst` 产出结构化事实提纲，主 agent 审核后写入 `docs/facts.md`（首次落盘权在主 agent，不下放给 subagent）
2. 再由主 agent 带着 `facts.md` 深读 `交底书.md`
3. 主 agent 确认 G2 硬门槛满足后，才进入写作

---

## 7. 修正后的最终架构

保留主 `patent` agent + 新增 2 个 subagent（分两步落地）。

```
patent（主控 skill）
├── disclosure-analyst（subagent，第二步落地）
│   └── 输入：交底书.md + global.md
│       输出：结构化事实提纲（经主 agent 审核后写入 docs/facts.md）
│       调用时机：权要一稿、全文一稿的深读前辅助节点
│
├── rule-auditor（subagent，第一步落地）
│   └── 输入：md 草稿 + scoring.md + 当前阶段规则
│       输出：审查报告（含完整性/1级/2级/最短回修清单）
│       调用时机：md 草稿写完、进入 DOCX 前
│
└── docx skill（现有官方 skill，不改）
    └── 通用 DOCX 执行与验证
```

被删除的 subagent（相对原方案）：

- `claims-writer`：写作留在主 agent。
- `full-draft-writer`：写作留在主 agent。
- `docx-verifier`：现有两级验收结构已足够。
- `revision-mapper`：延后到第二阶段再评估。

---

## 8. 落地路线图

### 8.1 第一步：`rule-auditor`（优先级最高）

1. 在 `~/.claude/agents/` 或 patent skill 内新增 `rule-auditor.md`，写清 Input/Output/Failure Contract。
2. 修改 `SKILL.md` 「权要一稿」第 7 步、「全文一稿」第 7 步：保持主 agent 现有块内自检与阶段越界检查不变，在其后新增"调用 `rule-auditor` subagent 做独立复核"。
3. 用 1-2 个真实案子跑一遍，验证：
   - 审查报告是否稳定输出固定结构
   - 主 agent 按最短回修清单回修后再次调用是否收敛
   - token 成本是否可接受
4. 稳定后再进第二步。

### 8.2 第二步：`disclosure-analyst`

1. 新增 `disclosure-analyst.md`，写清契约。
2. 修改 `SKILL.md` 「权要一稿」第 2-3 步、「全文一稿」相关步骤：把流程改为"先调用 `disclosure-analyst` 获取结构化事实提纲，由主 agent 审核后写入 `docs/facts.md`，再由主 agent 亲自深读 `交底书.md` 并核对高亮、批注和技术链，最后判断是否需要回问用户"。
3. 验证 facts.md 是否能真正减少主 agent 写作时的交底书重读次数，同时不削弱 G2 的主写作者理解义务。

### 8.3 第二阶段（MVP 稳定后再评估）

- `revision-mapper`：如果返修阶段仍观察到"批注理解不稳"的具体证据，再评估拆分。
- 写作类 subagent：暂不进入路线图。

---

## 9. 需要 GPT 复审的重点

请复审时重点关注以下几点：

1. **`rule-auditor` 的 Output Contract 是否足够严格**：现在的结构化报告能否真的替代主 agent 自评？是否需要要求 subagent 返回 JSON 而非 Markdown？
2. **`disclosure-analyst` 的定位是否足够克制**：作为预提纲器而非代理阅读器，这样的收益是否仍然足够大？
3. **共享 prompt 契约的 token 估算**：把 `scoring.md` + 阶段规则全文拼进每次 auditor 调用，是否比主 agent 自评更贵？成本 / 稳定性的 trade-off 是否值得？

   规则文件实际体积（`wc -c` 实测，按中文粗估 tokens ≈ bytes / 2）：

   | 文件 | 字节 | 估算 tokens |
   |---|---:|---:|
   | `scoring.md` | 6,120 | ~3,000 |
   | `global.md` | 19,398 | ~9,700 |
   | `claims.md` | 12,572 | ~6,300 |
   | `full-draft.md` | 15,974 | ~8,000 |
   | `figures.md` | 14,341 | ~7,200 |
   | `docx-template.md` 全文 | 11,353 | ~5,700 |
   | `docx-template.md` md 阶段可判定摘录 | ~4,000 | ~2,000 |
   | `revision.md` | 14,554 | ~7,300 |
   | `claims-format-standard.md` | 1,608 | ~800 |

   注：按 §5.3.1 契约，`docx-template.md` 只摘录 md 阶段可判定条目（G8-0b 章节标题格式、G8-1 红蓝字占位与案例性术语清理、权要 1 字数、分号断行），不整入 auditor prompt。以下按 ~2,000 tokens 摘录版本估算。

   单次 auditor 调用 Input Contract 拼装成本：

   - **权要一稿**：`scoring + global + claims + claims-format-standard + docx-template 摘录` ≈ **21,800 tokens 规则** + md 草稿约 3,000-5,000 tokens ≈ **~26,000 tokens / 次**。
   - **全文一稿**：`scoring + global + full-draft + figures + docx-template 摘录` ≈ **29,900 tokens 规则** + 全文稿 5,000-10,000 tokens ≈ **~37,000 tokens / 次**。
   - 若回修 1 次需再调 1 次，总计 52,000-74,000 tokens。

   对比主 agent 自评：写作阶段主 agent 已加载 `global + claims/full-draft + docx-template` 到自身 context，`scoring.md` 写完才首次加载。仅看**边际 token**，主 agent 自评只多约 3,000 tokens（scoring.md），auditor 则要重新拼一份 22,000-30,000 tokens 规则包，单次贵约 7-10 倍。

   但 token 不是本 trade-off 的核心维度。核心是 **auditor 换来的三样东西是否值这个溢价**：

   - **独立 context**：主 agent 已经带着"我刚写完的稿"进入自评，天然对自己产出有确认偏差；auditor 从零 context 读稿更接近"外审"。
   - **强制输出契约**：主 agent 自评的输出结构容易随会话状态漂移，auditor 有固定 Failure Contract 兜底。
   - **无自评放水**：现有 skill 长期存在"自评说 PASS、实际写入 DOCX 后仍有硬规则违反"的历史证据，这是拆 auditor 的直接动机。

   请 GPT 复审时判断：
   - auditor 的三项收益能否落地为可验证的稳定性提升（如硬规则违反率下降）？
   - 是否存在更省的替代路径，例如"主 agent 自评但强制返回固定 JSON + 二次自我质询"能否达到同等效果、避免每次多花 20,000+ tokens？
4. **是否漏掉了其他更适合作为 MVP 的 subagent 候选**：例如"权要格式硬规则检查"（分号断行、字数、编号连续性）这种纯规则匹配任务，是否值得并入 `rule-auditor` 的只读检查能力，而不是单独再拆一个 agent？
5. **返修阶段完全不用 subagent 是否合理**：原方案把 `revision-mapper` 放 MVP，本稿延后。请评估是否过度保守。

---

## 10. 与原方案的一句话对比

**原方案**：一个主控 + 6 个 subagent（事实/权要写作/全文写作/返修映射/规则审计/DOCX 验收）。

**修正稿**：一个主控 + 2 个 subagent（事实 + 规则审计），写作与 DOCX 验收留在主控，返修映射延后。

修正稿的核心判断：**先用最少的拆分验证 subagent 协作机制本身是否可靠，再决定是否继续拆**。

---
name: patent
description: Use when 用户要求基于交底书 DOCX 撰写、修订或继续中国专利申请，包括权要一稿/二稿/三稿、全文一稿/二稿/三稿、Word 批注修订、老板反馈、专利模板填写、或固定 Patent 文件夹工作流。
---

# 专利撰写工作流

本 skill 用于用户在 `/Users/example/Desktop/Patent/` 下的专利撰写工作流。

跨设备迁移到 Windows 时，参考 `docs/windows-setup.md`。

## 资源目录约定

- `assets/docx/` 只放可被执行层直接复制或套用的 DOCX 资产，例如固定专利撰写模板。默认模板为 `assets/docx/专利撰写模板.docx`。
- `references/cases/` 放案例标准、定稿经验和可迁移写作范例。案例文件用于理解“写到什么粒度”和“如何解释技术链条”，不得作为模板直接套用，不得把其中的技术对象、参数值、附图名迁移到新案件。
- `references/rules/` 放阶段化规则文件。每次任务只读取 `rules.md` 索引、`references/rules/global.md` 和当前阶段对应规则，按阶段读取规则以实现渐进式披露，避免把无关阶段规则带入上下文。
- `rules.md` 只放可跨案件复用的规则索引、阶段读取表和冲突处理原则；具体案件经验需要沉淀时，先抽象成宏观规则，原案例细节只放在 `references/cases/` 并在规则中用一句话指向。
- `docs/archive/` 只放历史备查文件，正常工作流不得读取或执行其中的旧规则、旧脚本。

## 必读

在撰写或修订前，必须先阅读 `rules.md` 和 `references/rules/global.md`。然后根据 `rules.md` 的阶段读取表，仅读取当前任务对应的阶段规则文件。不要默认读取无关阶段规则；例如权要一稿不默认读取 `references/rules/full-draft.md`、`references/rules/figures.md`，除非用户明确要求全文、摘要、附图或具体实施方式。

## DOCX 执行层硬门槛

当本工作流涉及任何 `.docx` 文件的读取、编辑、批注、修订痕迹、页眉页脚、XML 解包/打包、模板写入、Word 导出、公式写入或 DOCX 验证时，必须先显式调用官方 `document-skills:docx`（即 docx）skill。

未调用 `docx` skill 前，不得直接读取、编辑、生成、修订或打包 DOCX 文件。如果当前会话无法调用 `docx` skill，例如插件未安装、skill 未出现在可用列表、当前会话尚未刷新插件，则必须停止并提示用户重启 Claude Code 或重新加载插件；不得退回到未加载 `docx` 的手写 DOCX 操作。

**留痕返修例外**：`Word 批注修订（留痕返修）` 场景需保留老板修订原样，因 `docx` 的 unpack/pack 会 `simplify` 规整他人已有修订，故写入改用最小侵入直接注入 `word/document.xml`（详见该章节）；此例外仅限写入方式，仍须先加载 `docx` skill、用其 `validate` 校验并由 `patent` 终验收，不得跳过。

职责分工：

- `patent` 负责专利业务判断、交底书理解、权要/说明书撰写、老板批注解释、章节取舍、模板约束和最终验收；
- `docx` 负责 Word/DOCX 执行层，包括读取 DOCX、解包 XML、编辑 `word/document.xml`、`word/comments.xml`、`word/header*.xml`、`word/footer*.xml`、处理批注和修订痕迹、打包 DOCX、通用 DOCX 验证；
- `docx` 不参与判断专利文本是否合格，不决定权要结构、技术特征、前序基础、章节取舍或老板批注意图；
- `patent` 的 `rules.md` 和本 skill 中的模板保护规则优先于 `docx` 的通用文档生成建议；
- 对既有专利模板 DOCX，不得使用 `docx-js` 从零重建交付稿，除非用户明确要求放弃既有模板；
- 对既有专利模板 DOCX，优先采用 `docx` skill 的 unpack → edit XML → pack 流程；
- DOCX 写入完成后，仍必须由 `patent` 按本 skill 的规则验证 `sectPr`、`header*.xml`、`headerReference`、可见页眉、正文禁显章节、批注清除、权要格式和模板残留。

公式处理：权利要求中不写公式；说明书公式一律以 **LaTeX 源码**独立成段、按普通可编辑文本写入 DOCX（供用户复制后用 Word"插入公式 → LaTeX"转换）。细则唯一出处：`references/rules/global.md` G6。

## 默认立场

- 默认中文撰写，除必要的英文缩写、模型名、公式符号、技术术语外。
- 没有交底书 DOCX 时不要凭空起稿。
- 不要机械照抄交底书；提取技术问题、技术方案、技术效果。
- 若交底书逻辑不连贯、无法支持一个干净的权要集，停下来询问用户，不要凭空发明。
- 用户没明确要求时，不另外输出独立的撰写检查报告。
- 用户明确要求只读分析、规则检查、经验总结或修改建议时，不生成 DOCX，不改动案件文件。
- 批注/修订的作者名默认 `Juventude`（覆盖 docx skill 默认的 "Claude"）；用户另行指定时用指定名。
- 需要 pandoc 时用 `conda run -n base pandoc` 调用（默认 shell PATH 不含 pandoc；base 环境实测为 pandoc 3.9.0.2）。

## 阶段判断

整个工作流分两大阶段——**权要稿**与**全文稿**，每个阶段各含"一稿撰写 + 返修稿"。交底书阅读时机的唯一出处是 `references/rules/global.md` G2：仅权要一稿、全文一稿深读交底书，返修阶段默认不读。

根据用户表述和案件文件夹里的现有文件判断当前阶段：

| 用户意图 | 阶段 | 输出版本 |
|---|---|---|
| 第一次撰写权要，权要一稿 | claims draft | `案件号-权要1稿-作者-发明题目全称.docx` |
| 老板对权要稿给批注 | claims revision | 下一稿 `权要2稿` 或 `权要3稿` |
| 权要已定，写全文 | full draft | `案件号-全文1稿-作者-发明题目全称.docx` |
| 老板对全文稿给批注 | full revision | 下一稿 `全文2稿` 或 `全文3稿` |

如果缺以下任一元数据，应主动询问用户：案件号、作者名、发明题目、案件文件夹、当前阶段。不要在缺信息时凭猜测填。

## 案件文件夹约定

用户在 `/Users/example/Desktop/Patent/` 下新建与发明题目对应的案件文件夹。目录布局的唯一出处是 `references/rules/global.md` G1：根目录只放对外交付 DOCX 和老板批注稿，工作文件（`交底书.docx`、`交底书.md`、`权要稿.md`、`全文稿.md`）统一放 `docs/` 子目录，旧案散落文件先迁入 `docs/` 再继续。

自动识别明显文件。如果有多个可能候选，请用户选择。

## 权要一稿

`权要一稿`：

1. 先按 `rules.md` 阶段读取表读取 `references/rules/claims.md` 和 `references/rules/docx-template.md`。确认案件文件夹下已有 `docs/` 子目录（无则创建），并把交底书 DOCX 放入 `docs/`。进入 DOCX 执行层时，必须先调用官方 `document-skills:docx`（即 docx）skill；用其读取交底书 DOCX 的正文、批注和高亮，再把交底书 DOCX 转为带批注的 Markdown，保存为 `docs/交底书.md`。可继续使用 `scripts/disclosure_docx_to_md.py --input <案件文件夹>/docs/交底书.docx --output <案件文件夹>/docs/交底书.md`，但执行前必须已加载 `docx` skill。
2. **调用 `disclosure-analyst` subagent 生成事实提纲**：按 `agents/disclosure-analyst.md` 的 Input Contract 拼装 prompt（`disclosure_md_path` + `global.md` 全文 + `stage=claims-draft`），拿到结构化事实提纲。主 agent 审核提纲一致性和完整性后，写入 `docs/facts.md`。**subagent 不直接写文件**；若提纲缺"潜在风险"段落或结构破坏，视为失败并重试 1 次，仍失败则跳过 subagent、主 agent 亲自完成事实抽取。
3. **主 agent 亲自深读 `交底书.md`**（`disclosure-analyst` 是预提纲器，不替代 G2 深读义务）：带着 `docs/facts.md` 逐条核对 `==高亮==` 内容和 `> 💡 [批注 ...]` 行，确认技术问题—技术方案—技术效果链条闭合，提取核心技术问题、创新逻辑、关键步骤、特征命名、数据来源、数据用途、预期效果。若 `facts.md` 的"潜在风险"段落有需要回问用户的项，先解决再进入撰写。
4. 先用 Markdown 把专利稿件写在 `docs/权要稿.md`。
5. **权要一稿仅撰写并展示三部分，按此顺序排列**：权利要求书 → 技术领域 → 背景技术。其他章节（说明书摘要、摘要附图、发明内容、附图说明、具体实施方式、说明书附图）一律留到全文一稿撰写，权要一稿阶段不要写入 `权要稿.md`，也不要在 DOCX 正文或页眉中显示。
6. 在 `权要稿.md` 中写完整的权要集、技术领域、背景技术。权要数量、保护主题组合（方法权/计算机设备式系统权/存储介质权）、权要 1 字数、分号断行、从权粒度和依附关系的唯一出处是 `references/rules/claims.md` 及其指向的 `references/cases/claims-format-standard.md`。
7. 写入 DOCX 之前，对 `权要稿.md` 按 `claims.md` 各块自检清单自检，并确认未误写权要一稿以外的章节（摘要等属全文一稿，见 `full-draft.md` L4）。**随后调用 `rule-auditor` subagent 做独立复核**：按 `agents/rule-auditor.md` 的 Input Contract 拼装 prompt（`stage=claims-draft` + `md_path` + `scoring.md` 全文 + `stage_rules_content=global.md + claims.md + docx-template.md 的 md 可判定条目摘录` + `external_rule_refs_content=claims-format-standard.md` + `triggered_rule_notes`），拿到审查报告。**通过判定**：完整性 PASS + 1 级 100% + 2 级 ≥90%；未达通过标准不得进入 DOCX，按最短回修清单改 `权要稿.md` 后重评。若 auditor 两次失败（无固定结构或报告"输入规则不完整"），回退到主 agent 自评并在完工报告中标注"auditor 未生效"。
8. 进入 DOCX 执行层，确认已显式调用官方 `document-skills:docx`（即 docx）skill；若尚未调用，必须先调用 `docx` skill 后再继续。
9. 由 `docx` 执行层把内置模板 `assets/docx/专利撰写模板.docx` 拷贝到案件文件夹（用户明确指定其他模板时除外），重命名为 `案件号-权要1稿-作者-发明题目全称.docx`。
10. 由 `docx` 执行层采用 unpack → edit XML → pack 流程填充当前稿次可见章节，就地替换、只控制最终可见文本和当前稿次页眉显示。模板骨架保护（sectPr/header/headerReference 全保留、不清空 body 重建）与各分节应填内容的唯一出处是 `references/rules/docx-template.md` G8-0、G8-0b、G8-1。
11. 权要一稿的可见范围按 G8-0 对照表"权要稿"列与 G8-1 可见性规则执行：只显示"权利要求书""说明书"页眉，正文只显示权利要求书、发明名称、技术领域、背景技术；后续阶段槽位保留不删。
12. 完成后由 `docx` 执行层做通用 DOCX 验证，再由 `patent` 按 `docx-template.md` G8-0（分节3、分节4 内容落位）、G8-0b（发明名称与章节标题格式）、G8-1（骨架、可见性、红蓝字与案例性术语清理、权要1字数、分号断行）逐项验收。
13. 仅报告：输出 DOCX 路径、`docs/交底书.md` 路径、`docs/权要稿.md` 路径，以及任何需要用户关注的问题。不出独立的撰写检查报告。

## Word 批注修订（留痕返修）

`权要二稿/三稿` 或 `全文二稿/三稿`。**默认产物 = 留痕稿**：以 `Juventude` 名义的 track changes 修订痕迹，**保留老板原有的批注与修订不动**，供老板审阅"改了什么"，**默认不清除批注**；仅当用户明确要求定稿/归档的干净稿时，才另行由 `docx` 清除批注。

**返修四步工作流：**

1. **读返修意见**：先按 `rules.md` 阶段读取表读取 `references/rules/revision.md` 和 `references/rules/docx-template.md`，并根据批注涉及内容读取 `references/rules/claims.md`、`references/rules/full-draft.md` 或 `references/rules/figures.md`；再调用官方 `document-skills:docx`（即 docx）skill，由其提取批注稿 `word/comments.xml` 的批注 + `word/document.xml` 的 tracked changes，逐条列出老板要求。
2. **交底书按需查阅**：交底书阅读按 `global.md` G2 唯一出处执行——返修默认不读，仅批注要求新增稿件中尚不存在的技术内容时按需查 `docs/交底书.md` 对应段落。
3. **AI 返修（署 Juventude、留痕）**：`patent` 先逐条把批注翻译成具体修改方案，再按下方"留痕注入法"以 `Juventude` 名义注入 track changes。
4. **回填学习**：按下方"学习闭环"沉淀规律。

**留痕注入法（本场景对 unpack/pack 的例外）：**

- 仍先加载 `docx` skill，注入后用其 `validate` 校验、由 `patent` 终验收。
- **写入不走 `docx` 的 unpack→pack**：实测其 `simplify` 会规整老板已有修订（本案插入标记 61→23），破坏"保留老板痕迹原样"。
- **先归位再落笔**：插入/删除前先确认锚点属于哪个内容块（权要N / 技术领域 / 背景 / 发明内容 / 具体实施方式等）与哪一段，内容只补在其归属块内的正确位置；严禁跨块错位、严禁调换权要编号/段落/章节的既有顺序；已审块默认冻结，只改老板批注点名处；涉及多处或锚点不确定时，先把"改第几条/哪块哪句"报用户确认再落笔。
- 改用**最小侵入直接注入**：读原始 `word/document.xml`，锚定要改的 run 做单点字符串替换为 `<w:ins>/<w:del w:author="Juventude" w:date="...">`；用 zip 逐条复制、仅替换 `document.xml`，其余字节及老板全部 `w:ins/w:del/批注` 原样保留。
- `w:ins` 内 run 复制原 run 的 `<w:rPr>`（保字体字号）；`w:date` 用真实当前时间（`date +%Y-%m-%dT%H:%M:%SZ`，本所查看器直接显示字符串时分，格式与老板修订一致）；`w:id` 取现有最大值以上的未占用值；整段删除时在 `<w:pPr><w:rPr>` 加 `<w:del/>`。
- **校验项**：作者集合含 `Juventude`、老板批注条数不减、老板 `delText` 字数不变、`Juventude` 修订数符合预期、`docx validate` 无新增错误（原文件自带的 schema 小瑕疵不计）。
- 不覆盖老板批注过的原文件；留痕稿存为新文件名。

**学习闭环（每次返修收尾）：** 把本次批注体现的、可迁移的写作规律按主题补入对应阶段规则文件，例如返修纪律进 `references/rules/revision.md`，权要表达进 `references/rules/claims.md`，全文公开充分进 `references/rules/full-draft.md`，模板/XML 问题进 `references/rules/docx-template.md`，附图规则进 `references/rules/figures.md`；`rules.md` 仅在新增阶段索引或冲突原则时更新。具体案例只进入 `references/cases/`，并先给用户看 diff 再并入；本案技术对象名、参数值、附图名不进通用规则。

批注与硬性规则、交底书或可实施性冲突时的处理，唯一出处是 `rules.md` 冲突处理与 `references/rules/revision.md` G9。

## 全文一稿

`全文一稿`：

1. 先按 `rules.md` 阶段读取表读取 `references/rules/full-draft.md`、`references/rules/figures.md` 和 `references/rules/docx-template.md`；**全文阶段不读 `references/rules/claims.md`**（权要已冻结，全文只补说明书，术语一致与权要对应已由 `global.md G4`、`full-draft.md L6` 覆盖；仅当返修批注涉及权要联动时才按需读 `claims.md`）。从最新已审权要 DOCX 开始，不从空白模板起稿；若候选不唯一，必须先请用户确认使用哪一份权要 DOCX。并从该 DOCX 提取权利要求书全文作为全文稿唯一权要基准；若 `docs/全文稿.md` 已存在且其权要内容或撰写时间早于最新已审权要，必须先按 `full-draft.md` L8-0 对照新权要重构受影响章节，禁止直接复用旧稿注入。
2. 除非用户要求改动，保留已审权要不变。
3. **在开始补写说明书前，调用 `disclosure-analyst` subagent 获取或复用 `docs/facts.md`**：若 `docs/facts.md` 已在权要一稿阶段生成且交底书未变更，可直接复用；否则按 `agents/disclosure-analyst.md` 的 Input Contract 传入（`disclosure_md_path=docs/交底书.md` + `global.md` 全文 + `stage=full-draft`），拿到结构化事实提纲，由主 agent 审核后写入 `docs/facts.md`。主 agent **仍必须亲自深读 `docs/交底书.md`** 并核对高亮、批注、技术链和潜在风险，`facts.md` 不替代 `global.md` G2 的主写作者深读义务。
4. 在 `docs/全文稿.md` 中补全权要一稿未写的章节，必须按 `references/rules/full-draft.md`「全文稿分块撰写法」（唯一出处）逐块写、逐块过自检清单，不得一次性生成全文长文；具体实施方式框架按 `full-draft.md` L8-0 Sxx 框架同构规则执行。
5. 在说明书中解释每一条权要步骤。
6. 加入有益效果的技术原因。
7. 在 `docs/全文稿.md` 末尾追加 `## 附图设计（供手画 Visio 用）` 一节，按 `rules.md` 中的附图设计规则执行（规则 A 主流程基于权要 1、规则 B 子流程基于展开的主步骤、规则 C 系统结构基于系统权要）。用户根据这一节在 Visio 中手画实际附图，本 skill 不输出图片文件。
8. 写入 DOCX 之前，对 `docs/全文稿.md` 做跨块总检：各块自检已在分块撰写时逐块完成，此处只查跨块项——权要保留、全文术语一致性、模板案例性术语、禁用措辞、公式、模型/阈值细节、可实施性，并核对附图设计节的附图清单和节点数与权要 1、子步骤编号、系统权要相吻合。先由主 agent 沿用现有跨块自检流程做一遍初检；随后**调用 `rule-auditor` subagent 做独立复核**（按 `agents/rule-auditor.md` 的 Input Contract 传入 `stage=full-draft` + `md_path=docs/全文稿.md` + `scoring.md` 全文 + `global.md + full-draft.md + figures.md` 全文 + `docx-template.md` 中 md 可判定条目 + 命中的触发式规则）；未达通过标准不得进入 DOCX，按 auditor 返回的最短回修清单改 `全文稿.md` 后重新调用 auditor。auditor 未生效时（重试 1 次仍不返回契约结构），回退到主 agent 自评并在完工报告中标注"auditor 未生效"。
9. 进入 DOCX 执行层，确认已显式调用官方 `document-skills:docx`（即 docx）skill；若尚未调用，必须先调用 `docx` skill 后再继续。
10. 由 `document-skills:docx` 执行层把最新已审权要 DOCX 前向拷贝为 `案件号-全文1稿-作者-发明题目全称.docx`。
11. 由 `docx` 执行层采用 unpack → edit XML → pack，在权要一稿留空的槽位**就地填入**内容。骨架保护与分节落位的唯一出处是 `docx-template.md` G8-0/G8-0b/G8-1；分块注入（一次一块、注一块验一块）按 `full-draft.md`「全文稿分块撰写法」DOCX 注入层执行。
12. 报告完工前，先由 `docx` 执行层做通用 DOCX 验证，再由 `patent` 按 `docx-template.md` G8-0（逐分节内容落位）、G8-0b（发明名称与五个章节标题格式）、G8-1（骨架与可见性）逐项验收。

## DOCX 处理注意事项

所有 DOCX 工作均由官方 `document-skills:docx`（即 docx）skill 作为执行层。`patent` 只给出专利业务决策、模板约束和验收标准，不绕过 `docx` 直接处理 DOCX。

使用安全文件操作：

- 编辑前先拷贝
- 保留原审过的文件
- 权要一稿和全文一稿，写 DOCX 前确认对应的 `docs/权要稿.md` 或 `docs/全文稿.md` 存在
- 写完后验证输出文件存在
- 模板骨架保护（不清空 body 重建、保留 sectPr/header/headerReference、就地替换）的唯一出处是 `references/rules/docx-template.md` G8-1
- 清除批注时，验证 `word/comments.xml` 已不存在或确认没有遗留批注

辅助脚本：

- `scripts/disclosure_docx_to_md.py --input <案件文件夹>/docs/交底书.docx --output <案件文件夹>/docs/交底书.md`

历史脚本：

- `docs/archive/inject_md_to_template.deprecated.py` 是旧版清空 body 重建脚本，仅作历史备查，不得用于权要一稿/全文一稿模板写入。若需要自动写入模板，应先实现就地替换版脚本，确保不清空 body、不删除 `sectPr`、`header*.xml` 和 `headerReference`。

补充 Python 片段的使用边界（仅辅助检查、不替代 `docx` 执行层）唯一出处是 `references/rules/docx-template.md`「DOCX 执行层边界」。

## 完工报告

最终报告简短即可：

- 输出文件路径
- 完成阶段
- 修订模式下的交付类型：留痕稿/干净稿；若为干净稿，说明是否已清除批注；若为留痕稿，说明老板批注与修订已保留
- 是否有未解决的需要用户澄清的事项

默认不输出冗长的撰写检查报告。

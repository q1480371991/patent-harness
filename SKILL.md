---
name: patent
description: Use when 用户要求基于交底书 DOCX 撰写、修订或继续中国专利申请，包括权要一稿/二稿/三稿、全文一稿/二稿/三稿、Word 批注修订、老板反馈、专利模板填写、或固定 Patent 文件夹工作流。
---

# 专利撰写工作流

本 skill 用于用户在专利案件目录（macOS 默认 `~/Desktop/Patent/<撰写者>/`、Windows 默认 `C:\Users\<用户名>\Desktop\Patent\<撰写者>\`）下的专利撰写工作流。

跨设备迁移与首次接入的完整步骤参考 `docs/install.md`（含 Windows/macOS 目录、路径适配、依赖自检）。

## 接入前环境自检（首次接入必做）

本 skill 首次被接入一台新机器（Windows/macOS/Linux），或用户要求"检查/配置环境""能不能直接用"时，**在开始任何专利撰写工作前先跑一次环境自检**：

```bash
python3 scripts/check_env.py --json
```

按返回的 JSON 分类处理缺失项（力度已定：pip 库自动补，系统级/插件只引导）：

- **`category=pip` 且 `ok=false`（如 python-docx）**：AI 直接执行 `python3 scripts/check_env.py --fix` 自动 `pip install` 补齐，无需逐次征询。
- **`category=system` 且 `ok=false`**：`python`（运行时）用报告里的 `install_hint` 引导用户安装，不擅自静默改环境；`pandoc` 为**推荐项**（`scripts/omml_formulas.py` 用它把说明书公式转为原生 OMML 可编辑公式；缺失时公式回退纯 LaTeX 文本写入，不阻断工作），缺失时按提示引导安装。
- **`category=plugin`（document-skills:docx）**：脚本检测不到,由 AI 在会话中确认能否调用 `document-skills:docx` skill；不能调用则按报告提示让用户重启 Claude Code 或重新加载插件。

`missing_required=0` 即必需项就绪，可进入撰写；仍缺必需项时先补齐再开工。Windows 上 `python3` 不通时改用 `py`。

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

公式处理：权利要求中不写公式；说明书公式在 `全文稿.md` 中以 **LaTeX 源码**独立成段；写入 DOCX 时经 `scripts/omml_formulas.py` 转为原生 OMML 公式段（WPS/Word 均可编辑的二维公式），收尾跑其 `fix-settings` 与 `check`；pandoc 缺失时回退纯 LaTeX 文本写入并在完工报告注明。细则唯一出处：`references/rules/global.md` G6、`references/rules/docx-template.md` G8-3。

## 默认立场

- 默认中文撰写，除必要的英文缩写、模型名、公式符号、技术术语外。
- 没有交底书 DOCX 时不要凭空起稿。
- 不要机械照抄交底书；提取技术问题、技术方案、技术效果。
- 若交底书逻辑不连贯、无法支持一个干净的权要集，停下来询问用户，不要凭空发明。
- 用户没明确要求时，不另外输出独立的撰写检查报告。
- 用户明确要求只读分析、规则检查、经验总结或修改建议时，不生成 DOCX，不改动案件文件。
- 批注/修订的作者名**不设默认值**：每次返修任务开始时由用户提供署名；用户未提供时必须主动询问，不得擅自使用 `Juventude`、`Claude` 或任何其他名字。本文档下文出现的 `<用户指定署名>` 均指本条获取的名字。
- **新稿元数据缺则留空、不追问、不停顿**（仅适用权要一稿/全文一稿/直写全文稿等新稿；返修署名见上一条必须获取）：案件号、作者（撰写者）、正式发明题名全称这三项交付文件名/校验所需元数据，开工时若用户未提供，**不得停下来追问、不得等用户 Enter 确认**——先按"留空规则"（见全文一稿 step 9）写入 Word 完成交付，把所有缺项统一汇总到完工报告「待补清单」，由用户收稿后补齐或改名。作者位缺则文件名写 `待补`；发明题名缺则从权 1 保护主题提取作文件名占位（但 `check_hard_rules.py --invention-name` 的正式题名不得用提取值冒充，传空并报 suspect 记入待补）。这是为了让"交底书 → md → 三路审核 → Word"一条龙自动跑完，不被缺元数据打断。
- 需要 pandoc 时，先探测可用路径再调用：`scripts/omml_formulas.py` 已内置探测（PATH → `~/.local/bin` → `~/miniconda3/bin` → `/opt/homebrew/bin` → `/usr/local/bin`）；手工调用时优先直接 `pandoc`，不在 PATH 时 macOS 可尝试 `conda run -n base pandoc`（本机 base 环境实测为 pandoc 3.9.0.2），或按 `scripts/check_env.py` 报告的 `install_hint` 安装。pandoc 缺失时公式按 G6-1 回退纯 LaTeX 文本，不阻断主流程。

## 阶段判断

整个工作流分两大阶段——**权要稿**与**全文稿**，每个阶段各含"一稿撰写 + 返修稿"。交底书阅读时机的唯一出处是 `references/rules/global.md` G2：仅权要一稿、全文一稿深读交底书，返修阶段默认不读。

根据用户表述和案件文件夹里的现有文件判断当前阶段：

| 用户意图 | 阶段 | 输出版本 |
|---|---|---|
| 第一次撰写权要，权要一稿 | claims draft | `案件号-权要1稿-作者-发明题目全称.docx` |
| 老板对权要稿给批注 | claims revision | 下一稿 `权要2稿` 或 `权要3稿` |
| 权要已定，写全文 | full draft | `案件号-全文1稿-作者-发明题目全称.docx` |
| 有经验撰写者，一轮写完权要+全文 | direct full draft | `案件号-全文1稿-作者-发明题目全称.docx`（**不单独出 `权要1稿.docx`**，权要三章并入本稿；由用户指令"直接写完全文稿"触发，详见「直写全文稿」段） |
| 老板对全文稿给批注 | full revision | 下一稿 `全文2稿` 或 `全文3稿` |

如果缺以下任一元数据，应主动询问用户：案件号、发明题目、案件文件夹、当前阶段。撰写者从案件路径的一级目录自动识别（白名单与经验档案映射唯一出处 `global.md` G1）；路径不在白名单目录下或无法唯一判断时再询问用户，不要凭猜测填。

## 案件文件夹约定

用户在 `~/Desktop/Patent/夏晓贝/` 或 `~/Desktop/Patent/王培元/` 下新建与发明题目对应的案件文件夹。目录布局与交付命名的唯一出处是 `references/rules/global.md` G1：一级目录名即撰写者；案件根目录只放对外交付 DOCX 和老板批注稿，工作文件（`交底书.docx`、`交底书.md`、`权要稿.md`、`全文稿.md`）统一放 `docs/` 子目录，旧案散落文件先迁入 `docs/` 再继续。

自动识别明显文件。如果有多个可能候选，请用户选择。

## 审查闸门通用规则（两阶段共用）

权要一稿 step 7 与全文一稿 step 8 的闸门都按本节执行，各 step 只写差异（脚本参数、auditor 路名、传入字段）：

- **调用机制（Workflow 编排，替代逐路 Agent 调用）**：多路语义复核统一通过 **`Workflow` 工具**一次编排执行，不再用 Agent 工具逐路派发 subagent。编排方式：脚本内用 `parallel()` 并行发起各路 `agent()` 调用，每路一个 `agent()`；每路的 prompt 固定为——先 Read 本路契约文件（`agents/<路名>.md` 绝对路径）并严格按契约执行，随后给出输入契约全部字段（`stage`、`md_path`、两脚本 JSON 全文内嵌、各 `*_rules_path`/`scoring_excerpt_path` 绝对路径、`triggered_rule_notes`，重审轮加 `reaudit_context`）；**规则一律传文件路径，不把规则内容抄进 prompt**（脚本 JSON 除外，其为运行产物必须内嵌）；每案件首次编排前主 agent 先跑一次 `python3 scripts/verify_rule_anchors.py`（校验各契约 `sed -n` 锚点与规则文件标题匹配，非 0 退出=锚点失效，先修复再编排，防止 auditor 定向提取静默取空；规则文件的节标题行由此冻结，改标题必须同步改契约锚点）；每路 `agent()` 的返回值即该路完整审查报告全文，由主 agent 在 workflow 结束后取回合并。workflow 的 `meta.name` 用 `patent-audit-<stage>`，一路一个 `phase`/`label`（用路名），不在 workflow 内做通过判定或落盘——判定与合并是主 agent 职责。
- **通过判定**（合并口径唯一出处 `scoring.md` 计分方法）：global-auditor 完整性 PASS + 各路 1 级均 100% + 合并 2 级分（Σ各路通过 ÷ Σ各路适用）≥90%。
- **合并落盘**：主 agent 合并各路报告落盘一份 `docs/审查报告-<稿次>.md`（合并结论在前、各路原始报告附后；同位置同规则去重，跨路冲突按 `rules.md` 冲突处理原则裁决）。未达标不得进入 DOCX。
- **回修重审**：按合并后的最短回修清单改 md 后重审——**本阶段全部机械脚本必重跑**（权要稿：check_hard_rules + check_cross_block；全文稿：check_hard_rules + check_cross_block + verify_claims_alignment）；上轮有 FAIL 的路（专审路与 global-auditor 均适用）**以增量复核模式重调**（重审轮重新调用一次 Workflow，仅编排上轮 FAIL 的路）：额外传 `reaudit_context`（上轮该路报告的失败项 + 主 agent 列出的本轮改动块清单），各路契约中标注"完整性级"或"恒全文复核"的项仍全量复核，其余上轮 PASS 且不涉改动块的项沿用上轮结论并标注"沿用"；上轮全 PASS 的专审路不重调。
- **降级兜底**：任一路两次失败（无契约结构或报告"输入不完整"）时，仅该路降级为主 agent 按其契约自查并在完工报告标注"<路名> 未生效"，其余路照常生效，但脚本闸门必须通过。若 `Workflow` 工具本身不可用或整次运行连续两次失败（脚本报错、全部路无返回），**首先回退到 Agent 工具逐路并行派发**（每路一个 subagent，prompt 与输入字段同调用机制条，保留物理隔离与并行独立性），在完工报告标注"Workflow 未生效，已 Agent 派发"；Agent 工具亦不可用时，才整级降级为主 agent 按各路契约**分轮自查**（每轮只带一路规则包），标注"已分轮自查"。任何降级级别下脚本闸门都必须通过；降级不得静默——完工报告校验清单首行必须写明本次审查的实际执行方式（Workflow 编排 / Agent 派发 / 分轮自查）。

## 权要一稿

`权要一稿`：

1. 先按 `rules.md` 阶段读取表读取 `references/rules/claims.md` 和 `references/rules/docx-template.md`（此阶段只读其 G8-0/G8-0b 及 md 层可判定条目；G8-1 XML 骨架细节留到 DOCX 执行层 step 8-12 再读）。确认案件文件夹下已有 `docs/` 子目录（无则创建），并把交底书 DOCX 放入 `docs/`。先调用官方 `document-skills:docx`（即 docx）skill 满足执行层门槛（**不用其向上下文回读交底书正文**），随后直接执行 `scripts/disclosure_docx_to_md.py --input <案件文件夹>/docs/交底书.docx --output <案件文件夹>/docs/交底书.md` 完成确定性转换；仅当脚本转换失败或批注锚点异常时，才用 `docx` skill 读原 DOCX 定点排查。交底书全文只在 step 2 深读 `交底书.md` 时进入上下文一次。
2. **主 agent 亲自深读 `交底书.md` 并产出事实提纲**（G2 深读义务）：逐条核对 `> 💡 [批注 ...]` 行，确认技术问题—技术方案—技术效果链条闭合，提取核心技术问题、关键步骤、特征命名、数据来源、数据用途、预期效果，并在深读的同时把结构化事实提纲写入 `docs/facts.md`，固定结构为：技术问题、术语表、主流程、批注圈定的创新点、优先审查要求（批注）、数据来源/用途、潜在风险。**创新点以批注圈定为准，不自行另判**（G2-1）：批注 `> 💡 [批注 ...]` 已直接写出权利要求书创新点，按其圈定的步骤/特征展开创新特征，批注未点名的步骤按支撑环节处理；批注锚点丢失（只剩批注文字、不知选中哪段）时不猜测指向，回查 DOCX 选区或记入潜在风险。优先审查案件的关键词表缺失时记入潜在风险，向用户索取。
3. 若 `facts.md` 的"潜在风险"段落有需要回问用户的项，或批注圈定的创新点在交底书中找不到支撑，先解决再进入撰写。
4. 先用 Markdown 把专利稿件写在 `docs/权要稿.md`。
5. **权要一稿仅撰写并展示三部分，按此顺序排列**：权利要求书 → 技术领域 → 背景技术。其他章节（说明书摘要、摘要附图、发明内容、附图说明、具体实施方式、说明书附图）一律留到全文一稿撰写，权要一稿阶段不要写入 `权要稿.md`，也不要在 DOCX 正文或页眉中显示。
6. 在 `权要稿.md` 中写完整的权要集、技术领域、背景技术。权要数量、保护主题组合（方法权/计算机设备式系统权/存储介质权）、权要 1 字数、分号断行、从权粒度和依附关系的唯一出处是 `references/rules/claims.md` 及其指向的 `references/cases/claims-format-standard.md`。
7. 写入 DOCX 之前，主 agent 只自查**脚本与 auditor 均不覆盖的项**：未误写权要一稿以外的章节（摘要等属全文一稿，见 `full-draft.md` L4）。机械项交阶段 A 脚本终判、语义项交阶段 B auditor 专审，主 agent 不预演 `claims.md` 自检清单。**随后按两阶段闸门流程审查**：
   - **阶段 A：机械化硬规则脚本前置**：由主 agent 依次执行两个脚本——先 `python3 scripts/check_hard_rules.py --md <权要稿.md 绝对路径> --stage claims-draft --json`（第一类硬规则），再 `python3 scripts/check_cross_block.py --md <权要稿.md 绝对路径> --stage claims-draft`（第二类：结构抽取 + 依附合法校验）。**任一 FAIL 直接回修**，不进入阶段 B；结构抽取失败（`extraction_ok=false`）说明写法不合 A/B 标准，按 `extraction_errors` 规范化写法后重跑。主 agent 按报告的 `location` 和 `evidence` 定点修改 `权要稿.md` 后重跑脚本，直到全部 PASS。两个脚本的 JSON 分别作为 `mechanical_check_result` 和 `structure_check_result` 传给下一阶段。
   - **阶段 B：调用 `Workflow` 工具编排两路 auditor 并行语义复核**（多路审查，每路一个 `agent()`、只带本路规则包，编排细节见「审查闸门通用规则」调用机制条；**规则一律传文件路径，不把规则内容抄进 prompt**——auditor 按契约以 `sed -n` 标题区间定向提取所需节（不整篇 Read），主 agent 只传路径与两脚本 JSON；`scoring.md` 的按路摘录已实体化为 `references/rules/scoring-<路名>.md` 静态文件，合并计分方法留在主 agent）：
     - `claims-auditor`（契约 `agents/claims-auditor.md`）：传 `stage=claims-draft` + `md_path` + `mechanical_check_result` + `structure_check_result` + `scoring_excerpt_path=references/rules/scoring-claims.md` + `claims_rules_path=references/rules/claims.md`（只执行 L1 节）+ `claims_format_standard_path=references/cases/claims-format-standard.md` + `triggered_rule_notes`。
     - `global-auditor`（契约 `agents/global-auditor.md`）：传 `stage=claims-draft` + `md_path` + 两脚本 JSON + `scoring_excerpt_path=references/rules/scoring-global.md` + `global_rules_path=references/rules/global.md`（只执行 G3-G6）+ `short_block_rules_path=references/rules/claims.md`（只执行 L2+L3 节）+ `docx_template_rules_path=references/rules/docx-template.md`（只执行 md 层可判定条目）+ `triggered_rule_notes`。
     **通过判定、合并落盘（`docs/审查报告-权要N稿.md`）、回修重审与降级兜底一律按「审查闸门通用规则」节执行。**
8. **闸门通过 → 直接写入 DOCX**（不等待用户确认/Enter）：确认已显式调用官方 `document-skills:docx`（即 docx）skill（首次进入执行层调用一次即可）。
9. 由 `docx` 执行层把内置模板 `assets/docx/专利撰写模板.docx` 拷贝到案件文件夹（用户明确指定其他模板时除外），重命名遵循 G1 + 「默认立场」新稿留空规则（作者/案件号缺则写 `待补`，发明题名缺则从权 1 保护主题提取占位），不追问、不停顿。
10. 由 `docx` 执行层采用 unpack → edit XML → pack 流程填充当前稿次可见章节，就地替换、只控制最终可见文本和当前稿次页眉显示。模板骨架保护（sectPr/header/headerReference 全保留、不清空 body 重建）与各分节应填内容的唯一出处是 `references/rules/docx-template.md` G8-0、G8-0b、G8-1。
11. 权要一稿的可见范围按 G8-0 对照表"权要稿"列与 G8-1 可见性规则执行（章节清单唯一出处为 G8-0 表，本步不复列）；后续阶段槽位保留不删。
12. 完成后由 `docx` 执行层做通用 DOCX 验证，再由 `patent` 按 `docx-template.md` G8-0（分节3、分节4 内容落位）、G8-0b（发明名称与章节标题格式）、G8-1（骨架、可见性、案例性术语清理、权要1字数、分号断行）逐项验收。验收通过后，把 `docs/权要稿.md` 复制为 `docs/history/权要1稿.md`（快照留档，命名见 G1）。
13. 仅报告：输出 DOCX 路径、`docs/交底书.md` 路径、`docs/权要稿.md` 路径、按"完工报告"的**校验清单**格式逐规则打 ✅/❌/➖，以及任何需要用户关注的问题。不出独立的撰写检查报告。

## Word 批注修订（留痕返修）

`权要二稿/三稿` 或 `全文二稿/三稿`。**默认产物 = 留痕稿**：以 `<用户指定署名>` 名义的 track changes 修订痕迹，**保留老板原有的批注与修订不动**，供老板审阅"改了什么"，**默认不清除批注**；仅当用户明确要求定稿/归档的干净稿时，才另行由 `docx` 清除批注。开工前若用户尚未提供署名，先按"默认立场"该条询问，取得署名后再注入。

**返修工作流：**

1. **读返修意见**：先按 `rules.md` 阶段读取表读取 `references/rules/revision.md` 和 `references/rules/docx-template.md`，并根据批注涉及内容读取 `references/rules/claims.md`、`references/rules/full-draft.md` 或 `references/rules/figures.md`；再调用官方 `document-skills:docx`（即 docx）skill，由其提取批注稿 `word/comments.xml` 的批注 + `word/document.xml` 的 tracked changes，逐条列出老板要求。
2. **交底书按需查阅**：交底书阅读按 `global.md` G2 唯一出处执行——返修默认不读，仅批注要求新增稿件中尚不存在的技术内容时按需查 `docs/交底书.md` 对应段落。
3. **AI 返修方案 + 落 md 基准**：`patent` 先逐条把批注翻译成具体修改方案；对每一处补写/改写/扩写，把改后的块文本同步写入对应 md 基准（`docs/权要稿.md` / `docs/全文稿.md`），使**审查基准 = 将注入 DOCX 的确切内容**。严禁只改 DOCX 不回写 md（审查与交付脱节，是本 skill 已复盘的返修事故根因）。
4. **返修定向审查闸门**（重灾区块补写/改写时必过；执行细则同「审查闸门通用规则」，只按本轮改动块定向收窄）：本轮对 L1/L6/L8 做了补写/改写/扩写（非纯格式、纯编号迁移）时，注入 DOCX 前必须先过闸——先跑**本阶段全部机械脚本**（返修入口先跑 `timestamp_guard.py --case` 与 `fingerprint_claims.py --check` 两道守卫；权要案件跑 check_hard_rules + check_cross_block，全文案件再加 `verify_claims_alignment.py`——反向特征差集与步骤集差集正是镜像失同步的机械探测器），再**以增量复核模式**（`reaudit_context` = 本轮批注清单 + 改动块清单）调用改动块对应的 auditor 路（改 L1 调 claims-auditor、改 L6 调 content-auditor、改 L8 调 impl-auditor；术语或短块联动一律加 global-auditor），按「审查闸门通用规则」合并落盘 `docs/审查报告-<稿次>.md`，未过闸不得注入。纯留痕格式修订、纯编号迁移可豁免本闸的语义审查；**纯删除不豁免语义审查**——删除会牵动镜像块、引用关系与依赖链，至少以增量复核模式调 global-auditor 核查联动完整性；所有返修均须跑本阶段全部脚本闸门。
5. **留痕注入**：审查通过后，按下方“留痕注入法”以 `<用户指定署名>` 名义把已过闸的文本注入 track changes。注入时执行 `revision.md`「DOCX 留痕返修」的**改写即替换**（新句入、旧句删，禁止新旧并存）；注入完成后执行**注入后通读**与**反向保全 diff**（细则唯一出处 `revision.md`）。
6. **逐条销项回验**：回到 step 3 的批注-方案清单逐条核销——每条批注给出 DOCX 落点、改前→改后摘要（纯动作类给执行证据）、状态（已执行/部分执行/未执行+原因）；任何一条无落点证据即不得交付，纯动作类批注同权重核销，上轮标记“已完成”的项以本轮 DOCX 实际文本为准复检。细则唯一出处 `revision.md` G9-1「逐条销项回验」。
7. **md 基准同步校验 + 定稿快照**：注入与逐条销项回验通过后、进入完工报告前，按 `revision.md` G9-1「返修收尾 md 基准同步校验 + 定稿快照」执行——先逐个本轮改动块断言 `docs/全文稿.md`（涉权要联动并含 `docs/权要稿.md`）该块文本与本稿 DOCX 接受修订后干净正文一致（复用 step 5 的注入后通读/接受修订模拟同一遍，不一致回写 md 至一致），再把该基准复制为 `docs/history/全文N稿.md` / `docs/history/权要N稿.md`（命名见 `global.md` G1）；未通过不得交付。
8. **回填学习**：按下方“学习闭环”沉淀规律。

**留痕注入法（本场景对 unpack/pack 的例外）：**

- 仍先加载 `docx` skill，注入后用其 `validate` 校验、由 `patent` 终验收。
- **写入不走 `docx` 的 unpack→pack**：实测其 `simplify` 会规整老板已有修订（本案插入标记 61→23），破坏"保留老板痕迹原样"。
- **先归位再落笔**：插入/删除前先确认锚点属于哪个内容块（权要N / 技术领域 / 背景 / 发明内容 / 具体实施方式等）与哪一段，内容只补在其归属块内的正确位置；严禁跨块错位、严禁调换权要编号/段落/章节的既有顺序；已审块默认冻结，只改老板批注点名处；涉及多处或锚点不确定时，先把"改第几条/哪块哪句"报用户确认再落笔。
- 改用**最小侵入直接注入**：读原始 `word/document.xml`，锚定要改的 run 做单点字符串替换为 `<w:ins>/<w:del w:author="<用户指定署名>" w:date="...">`；用 zip 逐条复制、仅替换 `document.xml`，其余字节及老板全部 `w:ins/w:del/批注` 原样保留。
- `w:ins` 内 run 复制原 run 的 `<w:rPr>`（保字体字号）；`w:date` 用真实当前时间（`date +%Y-%m-%dT%H:%M:%SZ`，本所查看器直接显示字符串时分，格式与老板修订一致）；`w:id` 取现有最大值以上的未占用值；整段删除时在 `<w:pPr><w:rPr>` 加 `<w:del/>`。
- **校验项**：作者集合含 `<用户指定署名>`、老板批注条数不减、老板 `delText` 字数不变、`<用户指定署名>` 修订数符合预期、`docx validate` 无新增错误（原文件自带的 schema 小瑕疵不计）。
- 不覆盖老板批注过的原文件；留痕稿存为新文件名。
- **权要联动回写**：若本次返修改动了权利要求书内容（无论留痕或干净稿），注入并校验完成后，把最新权要全文同步回写 `docs/权要稿.md`，保证后续全文阶段的 md 基准不陈旧。

**学习闭环（每次返修收尾）：** **先过升格三闸**（判据唯一出处 `references/rules/revision.md` 学习闭环）——「审批意见准入标准（三进四不进）」判进不进规则层 → 「升格前去重检索」判是否已被现有条覆盖 → 「规则节清单容量上限」判该节还能不能新增编号；三闸结论按「准入决策留痕」回标 experience 条目的升格状态字段，**不得为凑完整度强行升格**。过闸后，把可迁移的写作规律按主题补入对应阶段规则文件，例如返修纪律进 `references/rules/revision.md`，权要表达进 `references/rules/claims.md`，全文公开充分进 `references/rules/full-draft.md`，模板/XML 问题进 `references/rules/docx-template.md`，附图规则进 `references/rules/figures.md`；`rules.md` 仅在新增阶段索引或冲突原则时更新。具体案例只进入 `references/cases/`，并先给用户看 diff 再并入；本案技术对象名、参数值、附图名不进通用规则。

批注与硬性规则、交底书或可实施性冲突时的处理，唯一出处是 `rules.md` 冲突处理与 `references/rules/revision.md` G9。

## 全文一稿

`全文一稿`：

1. 先按 `rules.md` 阶段读取表读取 `references/rules/full-draft.md`、`references/rules/figures.md` 和 `references/rules/docx-template.md`；**全文阶段不读 `references/rules/claims.md`**（权要已冻结，全文只补说明书，术语一致与权要对应已由 `global.md G4`、`full-draft.md L6` 覆盖；仅当返修批注涉及权要联动时才按需读 `claims.md`）。从最新已审权要 DOCX 开始，不从空白模板起稿；若候选不唯一，必须先请用户确认使用哪一份权要 DOCX。并从该 DOCX 提取权利要求书全文作为全文稿唯一权要基准（**DOCX 为权威源**）：提取后与 `docs/权要稿.md` 的权利要求书比对，不一致时以 DOCX 为准**回写更新 `docs/权要稿.md`**，使后续闸门与三路 auditor 使用的 `claims_md_path` 基准与 DOCX 保证一致；一致则直接使用。若 `docs/全文稿.md` 已存在且其权要内容或撰写时间早于最新已审权要，必须先按 `full-draft.md` L8-0 对照新权要重构受影响章节，禁止直接复用旧稿注入。
2. 除非用户要求改动，保留已审权要不变。
3. **在开始补写说明书前，获取或复用 `docs/facts.md`**：若 `docs/facts.md` 已在权要一稿阶段生成且交底书未变更，直接复用；否则由主 agent 在下述深读时亲自生成（结构同权要一稿 step 2 的事实提纲）。主 agent **必须亲自深读 `docs/交底书.md`**（G2 深读义务）并核对批注、技术链和潜在风险，`facts.md` 只是深读的落盘产物，不替代深读本身。
4. 在 `docs/全文稿.md` 中补全权要一稿未写的章节，必须按 `references/rules/full-draft.md`「全文稿分块撰写法」（唯一出处）逐块写、逐块过自检清单，不得一次性生成全文长文；具体实施方式框架按 `full-draft.md` L8-0 Sxx 框架同构规则执行。
5. 在说明书中解释每一条权要步骤。
6. 加入有益效果的技术原因。
7. 生成图 1（摘要附图 = 方法主流程图）：运行 `python3 scripts/render_patent_figure.py --claims-md <案件文件夹>/docs/权要稿.md --output <案件文件夹>/docs/figures/figure-1.png`。节点 = 权要 1 分句逐字、编号 S11..S1N 右侧引出线，均由脚本从权要稿构造保证；规则唯一出处 `references/rules/figures.md` L9。脚本报错（无方法独权提取不到分句）时按 L9/L5 请用户自备 PNG；权要在后续任何轮次被改动时必须重跑本步并重新注入。本 skill 不再输出"附图设计（供手画 Visio 用）"节，附图不手画。
8. 写入 DOCX 之前，主 agent 只自查**任何闸门都不覆盖的项**：`docs/figures/figure-1.png` 已按最新权要生成（渲染脚本零 ERROR 退出；附图内容一致性由脚本构造保证，不在多路审查范围）。其余跨块项（权要保留、术语一致、案例性术语、禁用措辞、公式、模型/阈值细节、可实施性）一律交脚本与三路 auditor 终判，主 agent 不做全量初检；**先跑基准时序前置守卫**：`python3 scripts/timestamp_guard.py --case <案件文件夹>`（全文稿早于审核稿即 exit=3，先查权要是否变更）与 `python3 scripts/fingerprint_claims.py --check --fulltext <案件文件夹>/docs/全文稿.md --claims <案件文件夹>/docs/权要稿.md`（权要基准 sha1 变更即 exit=3 硬停，按 L8-0 先 diff→同步→重构，重构后 `--gen` 更新指纹）——两守卫 FAIL 时不得进入下述脚本闸门与注入；**随后直接依次跑机械化脚本**：先 `python3 scripts/check_hard_rules.py --md <案件文件夹>/docs/全文稿.md --stage full-draft --claims-md <案件文件夹>/docs/权要稿.md --invention-name "<正式题名全称>" --json`（第一类硬规则；`--claims-md` 用于量词检查的权要原文复述豁免，见 G6-1 适用边界；**`--invention-name` 必传**——传本案正式发明题名全称（含"及系统／及装置"等后缀，取自案件已确认元数据，如 `"一种基于边缘计算的喷胶机自适应控制方法及系统"`），用于 G8-0b A 类槽位题名逐字校验；不传时该项校验静默不执行并回一条 `S-W35-name-input-missing` 配置缺失 suspect，题名错漏将无人拦截），再 `python3 scripts/check_cross_block.py --md <案件文件夹>/docs/全文稿.md --stage full-draft --claims-md <案件文件夹>/docs/权要稿.md`（第二类：结构抽取 + L8-0 步骤数同构 + 主步骤编号连续 + 依附合法 + 禁止合并展开；`--claims-md` 传入权要基准，因全文稿.md 不含冻结的权利要求书），再 `python3 scripts/verify_claims_alignment.py --md <案件文件夹>/docs/全文稿.md --claims-md <案件文件夹>/docs/权要稿.md --stage full-draft`（反向特征差集 + 撞名 + 步骤集差集；`hard` 违规=完整性 FAIL 定点回修，`suspect` 项以 `alignment_check_result` 字段——该脚本完整 JSON——传各路 auditor 逐条复核处置）。任一脚本不通过时按输出定点回修再重跑，不得跳过；结构抽取失败（`extraction_ok=false`）说明 Sx 步骤或权要写法不合 A/B 标准（L8-1 主步骤展开范式），按 `extraction_errors` 规范化后重跑。两个脚本都通过后**调用 `Workflow` 工具编排三路 auditor 并行独立复核**（多路审查，每路一个 `agent()`、只带本路规则包，编排细节见「审查闸门通用规则」调用机制条；**规则一律传文件路径，不把规则内容抄进 prompt**——auditor 按契约以 `sed -n` 标题区间定向提取所需节（不整篇 Read）；`scoring.md` 的按路摘录已实体化为 `references/rules/scoring-<路名>.md` 静态文件，合并计分方法留在主 agent；权要冻结基准 `claims_md_path=docs/权要稿.md` 传给三路）：
   - `content-auditor`（契约 `agents/content-auditor.md`）：传 `stage=full-draft` + `md_path=docs/全文稿.md` + `claims_md_path` + `mechanical_check_result` + `structure_check_result` + `alignment_check_result` + `scoring_excerpt_path=references/rules/scoring-content.md` + `content_rules_path=references/rules/full-draft.md`（只执行 L6 节与 L8-0 反向断言条）+ `triggered_rule_notes`。
   - `impl-auditor`（契约 `agents/impl-auditor.md`）：传同上公共项（含 `alignment_check_result`）+ `scoring_excerpt_path=references/rules/scoring-impl.md` + `impl_rules_path=references/rules/full-draft.md`（只执行 L8 节；Sxx 展开范式唯一出处即 L8-1）+ `global_rules_path=references/rules/global.md`（只执行 G6-1 节：公式/统计/判断清单与模型测度）。
   - `global-auditor`（契约 `agents/global-auditor.md`）：传 `stage=full-draft` + `md_path` + `claims_md_path` + 两脚本 JSON + `alignment_check_result` + `fingerprint_check_result`（`fingerprint_claims.py --check` 结果，用于权要冻结完整性项判据）+ `scoring_excerpt_path=references/rules/scoring-global.md` + `global_rules_path=references/rules/global.md`（只执行 G3-G6）+ `short_block_rules_path=references/rules/full-draft.md`（只执行 L4+L5+L7 节）+ `docx_template_rules_path=references/rules/docx-template.md`（只执行 md 层可判定条目）+ `triggered_rule_notes`。
   **通过判定、合并落盘（`docs/审查报告-全文N稿.md`）、回修重审与降级兜底一律按「审查闸门通用规则」节执行。闸门通过后直接进入 step 9 写入 Word，不因缺元数据而停下询问（缺项按下方 step 9 留空规则处理，统一汇总到完工报告的待补清单）。**
9. **闸门通过 → 直接写入 DOCX**（不等待用户确认/Enter）：确认已显式调用官方 `document-skills:docx`（即 docx）skill（首次进入执行层时调用一次即可，后续 step 复用）。**交付文件名命名规则**：`<案件号>-全文N稿-<作者>-<发明题目全称>.docx`（唯一出处 G1）。**缺元数据时的留空规则**（本 step 不追问、不停顿）：①**作者**未提供时，文件名作者位写 `待补`（如 `待补-全文1稿-待补-…docx`，案件号也缺则前缀整段省略或同样写 `待补`），完工后由用户自行改名；②**发明题名**未提供时，从权 1 保护主题自动提取作为文件名题名位（如"一种基于边缘计算的喷胶机自适应控制方法及系统"），但 `check_hard_rules.py --invention-name` 的正式题名**不得用自动提取值冒充**（G8-0b 信源纪律：正式题名须案件元数据确认；提取值仅用于文件名占位），此时该脚本传空、题名校验报 `S-W35-name-input-missing` suspect、记入待补清单。**所有留空/占位项一律记入完工报告「待补清单」**，由用户在收稿后补齐（含：案件号、正式发明题名全称、作者署名）。
10. 由 `document-skills:docx` 执行层把最新已审权要 DOCX 前向拷贝为 `案件号-全文N稿-作者-发明题目全称.docx`（命名唯一出处 G1）。
11. 由 `docx` 执行层采用 unpack → edit XML → pack：先用模板 `assets/docx/专利撰写模板.docx` 拷贝为 `案件号-全文N稿-作者-发明题目全称.docx`（若 step 10 已前向拷贝则复用），再跑 `python3 scripts/inject_fulltext_docx.py <unpack目录> --md <案件文件夹>/docs/全文稿.md`（默认一次性注入摘要+发明内容+附图说明+具体实施方式四章，可选 `--block` 分块调试），把全文稿就地注入分节1（摘要）与分节4（L6–L8）。骨架保护与分节落位唯一出处是 `docx-template.md` G8-0/G8-0b/G8-1；权要三章（权利要求书/技术领域/背景技术）由 step 10 前向拷贝保留，不在本脚本范围。正文注入完成后、最终 pack 前，运行 `python3 scripts/insert_figures_docx.py <unpack目录> --png <案件文件夹>/docs/figures/figure-1.png` 把图 1 注入分节 2（摘要附图）与分节 5（说明书附图，含"图1"图题），再 pack。pack 后跑 `python3 scripts/verify_docx_injection.py <案件文件夹>/案件号-全文N稿-作者-发明题目全称.docx --md <案件文件夹>/docs/全文稿.md` + `python3 scripts/omml_formulas.py check <docx>`（必要时 `fix-settings`）+ `python3 scripts/verify_docx_skeleton.py <docx> --stage 全文` 三件套收尾验收。
12. 报告完工前，先由 `docx` 执行层做通用 DOCX 验证，再由 `patent` 按 `docx-template.md` G8-0（逐分节内容落位）、G8-0b（发明名称与五个章节标题格式）、G8-1（骨架与可见性）逐项验收；验收通过后，把 `docs/全文稿.md` 复制为 `docs/history/全文1稿.md`（快照留档，命名见 G1）；完工报告按“完工报告”的**校验清单**格式逐规则打 ✅/❌/➖。

## 直写全文稿（有经验撰写者）

`直写全文稿`：用户指令"直接写完全文稿"（或同义表述，如"一次性写完权要和全文""直接全写完"）触发，资格不预判、不靠白名单，纯由用户口头指令区分。经验丰富的撰写者在 md 层一轮写完权要稿+全文稿，**先过权要闸门、再过全文闸门（两闸门串行在 md 层完成），最后只写一次 Word**——只出 `案件号-全文1稿-作者-发明题目全称.docx`，**不单独出 `权要1稿.docx`**（权要三章直接并入本稿）。若用户中途想先让老板审权要，改用传统「权要一稿」流程分阶段出稿。两闸门不冗余（权要闸门管 L1/L2/L3 三章本身合规，全文闸门管 L4–L8 说明书章节 + 与权要镜像对齐），串行执行是正确顺序。

1. 先按 `rules.md` 阶段读取表「直写全文稿」行读取 `global.md`、`claims.md`（**全量，不冻结**）、`full-draft.md`、`figures.md`、`docx-template.md`、`scoring.md`。确认案件文件夹下已有 `docs/` 子目录（无则创建），把交底书 DOCX 放入 `docs/`。先调用官方 `document-skills:docx`（即 docx）skill 满足执行层门槛（**不用其向上下文回读交底书正文**），随后直接执行 `scripts/disclosure_docx_to_md.py --input <案件文件夹>/docs/交底书.docx --output <案件文件夹>/docs/交底书.md` 完成确定性转换。`claims.md` 不冻结，是本阶段必读核心。
2. **主 agent 亲自深读 `docs/交底书.md` 并产出 `docs/facts.md`**（G2 深读义务，结构同权要一稿 step 2）：逐条核对批注、技术问题—技术方案—技术效果链条闭合，提取核心技术问题、关键步骤、特征命名、数据来源/用途、预期效果、批注圈定创新点（G2-1，创新点以批注圈定为准）、潜在风险。
3. **md 层先写权要稿**（`docs/权要稿.md`）：按 `claims.md` 规则写权利要求书 → 技术领域 → 背景技术三部分（同权要一稿 step 5/6）。此时不写任何说明书章节、不动 Word。
4. **跑权要闸门（claims-draft，此时无任何 Word 产物）**：先 `python3 scripts/check_hard_rules.py --md <案件文件夹>/docs/权要稿.md --stage claims-draft --json`，再 `python3 scripts/check_cross_block.py --md <案件文件夹>/docs/权要稿.md --stage claims-draft`。任一 FAIL 按 `location`/`evidence` 定点回修 `权要稿.md` 重跑，直到全 PASS。PASS 后按「审查闸门通用规则」用 `Workflow` 工具编排 claims-auditor + global-auditor 两路并行语义复核（`stage=claims-draft`，规则一律传文件路径，编排细节同权要一稿 step 7 阶段 B）。通过判定、合并落盘（`docs/审查报告-权要1稿.md`）、回修重审同「审查闸门通用规则」。
5. **权要闸门 PASS 后，立即跑 `python3 scripts/fingerprint_claims.py --gen --fulltext <案件文件夹>/docs/全文稿.md --claims <案件文件夹>/docs/权要稿.md`**，把权要稿当前分句序列的 sha1 写入 `docs/全文稿.md` 头部 front-matter（为后续 `--check` 准备；此时 `全文稿.md` 可仅为含 front-matter 的空壳）。**写全文期间权要稿不得再改**——一旦改动必须回本步重新 `--gen`，否则后续 `--check` 硬停（exit 3）。
6. **md 层续写全文稿**（`docs/全文稿.md`）：按 `full-draft.md`「全文稿分块撰写法」（唯一出处）逐块撰写 L4 说明书摘要 → L5 摘要附图 → L6 发明内容 → L7 附图说明 → L8 具体实施方式（L8 按 L8-0 Sxx 框架同构、逐条主步骤分批写），逐块过自检清单、自检通过才写下一块；以已通过自检的权要三章为术语与链条基准。L9 附图见 step 7。
7. 生成图 1（摘要附图 = 方法主流程图）：`python3 scripts/render_patent_figure.py --claims-md <案件文件夹>/docs/权要稿.md --output <案件文件夹>/docs/figures/figure-1.png`（规则唯一出处 `figures.md` L9，同全文一稿 step 7）。
8. **跑全文闸门（full-draft，此时仍无任何 Word 产物）**：**先跑基准时序前置守卫**——`python3 scripts/timestamp_guard.py --case <案件文件夹>`（直写模式无 `审核*.docx` 时 exit 0，安全不触发）与 `python3 scripts/fingerprint_claims.py --check --fulltext <案件文件夹>/docs/全文稿.md --claims <案件文件夹>/docs/权要稿.md`（验权要稿自 step 5 `--gen` 后未改动，sha1 不一致即 exit 3 硬停，回 step 5 处理）；两守卫 FAIL 不得进入下述脚本闸门；**随后直接依次跑机械化脚本**：`check_hard_rules.py --md <案件文件夹>/docs/全文稿.md --stage full-draft --claims-md <案件文件夹>/docs/权要稿.md --invention-name "<正式题名全称>" --json`（`--invention-name` 必传，口径同全文一稿 step 8） → `check_cross_block.py --md <案件文件夹>/docs/全文稿.md --stage full-draft --claims-md <案件文件夹>/docs/权要稿.md` → `verify_claims_alignment.py --md <案件文件夹>/docs/全文稿.md --claims-md <案件文件夹>/docs/权要稿.md --stage full-draft`（`--claims-md` 传入同会话刚写完的权要稿，守卫不检查"已审批/冻结"标记，只看磁盘内容）。任一 FAIL 定点回修 `全文稿.md` 重跑；结构抽取失败按 `extraction_errors` 规范化写法后重跑。三脚本全 PASS 后按「审查闸门通用规则」用 `Workflow` 工具编排 content-auditor + impl-auditor + global-auditor 三路并行语义复核（`stage=full-draft`，`claims_md_path=docs/权要稿.md` 传给三路，编排细节同全文一稿 step 8）。通过判定、合并落盘（`docs/审查报告-全文1稿.md`）、回修重审同「审查闸门通用规则」。
9. **两闸门均 PASS → 一次性写入 Word**（不等待用户确认/Enter）：进入 DOCX 执行层，确认已显式调用官方 `document-skills:docx` skill（首次进入执行层调用一次即可）。由 `docx` 执行层把内置模板 `assets/docx/专利撰写模板.docx`（用户明确指定其他模板时除外）拷贝到案件文件夹，重命名遵循 G1 + 「默认立场」新稿留空规则：作者缺则作者位写 `待补`，发明题名缺则从权 1 保护主题提取作文件名占位，案件号缺则前缀省略或 `待补`；采用 unpack → edit XML → pack：按 `docx-template.md` G8-0/G8-0b/G8-1 骨架与分节落位，**权要三章（权利要求书/技术领域/背景技术）由 docx 执行层手填**，全文章节（L4 摘要 + L6 发明内容 + L7 附图说明 + L8 具体实施方式）由 `python3 scripts/inject_fulltext_docx.py <unpack目录> --md <案件文件夹>/docs/全文稿.md` 一次性注入（就地下笔、不清空 body、不删 sectPr，段落成段与块/行内公式编译由脚本保证；可选 `--block` 分块调试）。正文注入完成后、最终 pack 前，运行 `python3 scripts/insert_figures_docx.py <unpack目录> --png <案件文件夹>/docs/figures/figure-1.png` 注入图 1 至分节 2/5，再 pack。pack 后跑 `python3 scripts/verify_docx_injection.py <案件文件夹>/<交付文件名>.docx --md <案件文件夹>/docs/全文稿.md` + `python3 scripts/omml_formulas.py check <docx>`（必要时 `fix-settings`）+ `python3 scripts/verify_docx_skeleton.py <docx> --stage 全文` 三件套收尾验收。
10. 报告完工前，先由 `docx` 执行层做通用 DOCX 验证，再由 `patent` 按 `docx-template.md` G8-0（逐分节内容落位）、G8-0b（发明名称与五个章节标题格式）、G8-1（骨架与可见性）逐项验收；验收通过后，把 `docs/全文稿.md` 复制为 `docs/history/全文1稿.md`、`docs/权要稿.md` 复制为 `docs/history/权要1稿.md`（权要虽未单独出 Word，仍留 md 快照，命名见 G1）；完工报告按“完工报告”的**校验清单**格式逐规则打 ✅/❌/➖，**并注明本稿为直写模式、未出独立 `权要1稿.docx`**；**所有留空/占位项（案件号、正式发明题名、作者署名等）汇总进完工报告「待补清单」**，由用户收稿后补齐或改名。

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
- `scripts/render_patent_figure.py --claims-md <权要稿.md> --output <案件文件夹>/docs/figures/figure-1.png`：从权要 1 分号分句自动生成图 1（摘要附图 = 方法主流程图）PNG；节点文字逐字一致由构造保证，规则见 `figures.md` L9。
- `scripts/insert_figures_docx.py <unpack目录> --png <figure-1.png>`：把图 1 注入分节 2（摘要附图）与分节 5（说明书附图 + "图1"图题），自动注册 media/relationship/Content-Type；两处已有图片时为替换语义。
- `scripts/inject_fulltext_docx.py <unpack目录> --md <全文稿.md> [--block 章节]`：全文稿 md → 模板 DOCX 就地注入摘要+发明内容+附图说明+具体实施方式四章（L4+L6+L7+L8），默认一次性注完，可选 `--block` 分块调试。就地下笔不清空 body、不删 sectPr/header/headerReference；按 md 单换行切段（子步骤各自成段，根治挤段），块公式与行内 `$...$` 编译为原生 OMML（G8-3）；pandoc 缺失回退纯文本（G6-1）。摘要替换分节1占位段，L6–L8 追加到分节4末 sectPr 前并删模板 `......` 占位套话段；权要三章仍由 docx 执行层手填、不在本脚本范围。
- `scripts/verify_docx_injection.py <file.docx> --md <全文稿.md> [--fallback]`：注入后机械校验（zipfile 直读磁盘 docx）——块/行内 oMath 数对账 md、sectPr=5、无 `$`/裸 LaTeX 残留、章节标题加粗顶格、套话锚点齐全、图1 drawing≥2。任一不符 exit=1。`--fallback` 用于 pandoc 缺失回退模式（放宽公式数断言为仅查无 `$` 残留）。
- `scripts/check_hard_rules.py --md <md 草稿> --stage claims-draft|full-draft [--claims-md <权要稿.md>] [--invention-name "<正式题名全称>"] --json`：第一类硬规则机械检查（字数、断行、编号、禁用措辞等；full-draft 传 `--claims-md` 以豁免权要原文复述中的量词；**full-draft 必传 `--invention-name`**——本案正式发明题名全称含"及系统／及装置"后缀，供 G8-0b A 类槽位逐字校验，不传则该项静默不执行、只回一条配置缺失 suspect），闸门用法见权要一稿 step 7 / 全文一稿 step 8。
- `scripts/extract_structure.py --md <md 草稿> --stage claims-draft|full-draft`：按 A/B 标准写法抽取结构 JSON（权要分句、Sx 主步骤、子步骤、附图清单、依附关系），写法不规范时报错停。
- `scripts/check_cross_block.py --md <md 草稿> --stage claims-draft|full-draft [--claims-md <权要稿.md>]`：第二类跨块校验（内部自动跑结构抽取）——L8-0 步骤数同构、主步骤编号连续、依附合法、禁止合并展开，输出作为 `structure_check_result` 传给各路 auditor（多路审查契约见 `agents/*-auditor.md`）。full-draft 阶段必须用 `--claims-md` 传入权要基准（全文稿.md 不含冻结的权利要求书）。
- `scripts/verify_claims_alignment.py --md <全文稿.md> --claims-md <权要稿.md> --stage full-draft`：反向特征差集（L8-0，框架句实体名词 − 权要，suspect）+ 权要内撞名（`claims.md` L1-1，suspect）+ 步骤集差集（L8-1，权要分句产物名在三节缺失=hard FAIL）。`hard` 与 auditor 冲突以脚本为准；`suspect` 回传各路 auditor 复核。exit=hard 违规数。
- `scripts/fingerprint_claims.py --gen|--check --fulltext <全文稿.md> --claims <权要稿.md>`：权要基准指纹（ADR-0005）。`--gen` 按当前权要写入全文稿.md 头 front-matter（基准权要/sha1/提取时间/分句数）；`--check` 重算权要 sha1 与之比对，不一致 exit=3 硬停，提示走 L8-0 diff→同步流程。
- `scripts/timestamp_guard.py --case <案件文件夹>`：版本时序守卫（ADR-0005）。全文稿.md 早于任一 `审核*.docx` → exit=3，要求先跑 fingerprint --check 确认权要是否变更，防"用旧说明书交付新权要"。
- `scripts/verify_rule_anchors.py [--json]`：契约 sed 锚点守卫——校验四份 auditor 契约中 `sed -n` 定向提取的起止锚点在规则文件标题中可命中、无歧义且区间非空（每案件首次编排 auditor 前跑一次；改规则文件节标题或契约锚点后必跑）。exit=失败锚点数。
- `scripts/verify_scoring_excerpts.py [--json]`：scoring 摘录一致性守卫——校验四份 `scoring-*.md` 与 `scoring.md` 的规则编号分派一致（单路标注行编号必进对应摘录、摘录不得私增编号、前置纪律句逐字在场）。改 `scoring.md` 或任一摘录后必跑。exit=失败检查数。

历史脚本：

- `docs/archive/inject_md_to_template.deprecated.py` 是旧版清空 body 重建脚本，仅作历史备查，不得用于权要一稿/全文一稿模板写入。就地替换版通用注入已由 `scripts/inject_fulltext_docx.py` 实现（保留 `sectPr`/`header*.xml`/`headerReference`，按章节落位、不清空 body）。

补充 Python 片段的使用边界（仅辅助检查、不替代 `docx` 执行层）唯一出处是 `references/rules/docx-template.md`「DOCX 执行层边界」。

## 完工报告

最终报告简短即可：

- 输出文件路径
- 完成阶段
- **校验清单**（权要一稿/全文一稿交付时必附）：**直接从合并落盘的 `docs/审查报告-*.md` 与验收结论转录，逐规则编号打勾，不重新校验**。用 emoji 标记：✅ 通过、❌ 失败（注明原因）、➖ 不适用（注明理由）。按块分组列出，格式如下：

  ```
  校验清单：

  【审查执行】
  ✅ 审查执行方式：Workflow 编排 / Agent 派发 / 分轮自查（写实际方式；降级须注明原因）

  【脚本闸门】
  ✅ check_hard_rules.py 硬规则脚本 PASS
  ✅ check_cross_block.py 结构/跨块校验 PASS
  ✅ verify_claims_alignment.py 对齐校验 PASS（全文稿；hard=0，suspect 已由 auditor 逐条处置）
  ✅ timestamp_guard.py / fingerprint_claims.py --check 守卫 PASS（全文稿/返修）

  【权利要求书 L1】（权要稿）/【发明内容 L6】【具体实施方式 L8】（全文稿）
  ✅ L1-1 权 1 ≤400 字
  ✅ L1-1 从权依附多元化
  ✅ L6-1 发明内容逐条权要覆盖
  ➖ L6-2 系统从权效果对应（本案无系统从权）
  …（本块每条 1 级 / 2 级规则逐条列出）

  【全局与短块 G3-G6 / L2-L5 / L7】
  ✅ G4 全文术语一致
  …

  【DOCX 验收】
  ✅ docx 通用验证无错误
  ✅ verify_docx_injection.py 注入机械项 PASS（块/行内 oMath 数、$ 残留、章节标题加粗顶格、套话锚点、图1 drawing）
  ✅ omml_formulas.py check 公式健康 PASS（无空壳/无 m:d/无编号残留/无幽灵字体，必要时已 fix-settings）
  ✅ verify_docx_skeleton.py 骨架机械项 PASS（sectPr=5 / header=13 / headerReference 完整 / 可见页眉符合稿次）
  ✅ 模板骨架（sectPr / header / headerReference 完整）
  ✅ 页眉与正文可见性符合当前稿次（G8-0 / G8-1）
  ✅ md 基准已快照到 docs/history/（权要1稿.md / 全文1稿.md）

  【待补清单】（新稿交付必附；无留空项时写「无」）
  ➖ 案件号：（未提供时文件名写了 `待补`，用户改名时补全）
  ➖ 正式发明题名全称：（未提供时用权1保护主题占位；补全后可重跑 check_hard_rules --invention-name 核验）
  ➖ 作者署名：（未提供时文件名写了 `待补`，用户改名时补全）
  ```

  多轮回修的案子以**最终通过轮**的结论为准；auditor 增量复核中"沿用上轮"的项照常打 ✅ 并可标注"(沿用)"。返修交付时清单换为返修校验项（署名正确、老板批注条数不减、老板 delText 字数不变、修订数符合预期、docx validate 无新增错误、**返修清单销项表 N/N 全核销**、**镜像块同步检查**（摘要/发明内容对应段/S 复述句/附图说明/"综上所述"段）、**注入后通读与反向保全 diff 已执行**、**md 基准已同步并快照**（`全文稿.md`/`权要稿.md` 与交付稿接受修订后干净正文一致，且 `docs/history/全文N稿.md`（权要案 `权要N稿.md`）已生成））。
- 修订模式下的交付类型：留痕稿/干净稿；若为干净稿，说明是否已清除批注；若为留痕稿，说明老板批注与修订已保留
- 是否有未解决的需要用户澄清的事项
- **待补清单**（新稿交付必附）：开工时缺失的元数据/可补项，按本稿实际留空情况逐项列出，供用户收稿后补齐或改名。典型项：
  - 案件号（文件名前缀，缺则写了 `待补`，用户改名时补全）
  - 正式发明题名全称（`check_hard_rules.py --invention-name` 缺则该题名槽位校验未执行/报 suspect；正式题名须案件元数据确认，未确认前用权 1 保护主题占位，用户确认后可补跑该脚本核验）
  - 作者署名（文件名作者位，缺则写了 `待补`，用户改名时补全；返修留痕稿的 track changes 作者名另行获取，不在此清单）

默认不输出冗长的撰写检查报告；校验清单逐规则只列"emoji + 规则编号 + 一句话"结论行，不展开证据（证据已在 `docs/审查报告-*.md` 落盘）。

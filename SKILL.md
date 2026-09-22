---
name: patent
description: Use when 用户要求基于交底书 DOCX 撰写、修订或继续中国专利申请，包括权要一稿/二稿/三稿、全文一稿/二稿/三稿、Word 批注修订、老板反馈、专利模板填写、或固定 Patent 文件夹工作流。
---

# 专利撰写工作流

本 skill 用于用户在专利案件目录下的专利撰写工作流。**本 fork（`claude-lxl`）的默认工作目录是 `<桌面>/专利/正式派单/<案件文件夹>/`**（撰写者 lxl，单撰写者维护、路径下不再嵌撰写者名）；目录白名单的唯一出处是 `references/rules/global.md` G1。

跨设备迁移与首次接入的完整步骤参考 `docs/install.md`（含 Windows/macOS 目录、路径适配、依赖自检）。

## 接入前环境自检（首次接入必做）

本 skill 首次被接入一台新机器（Windows/macOS/Linux），或用户要求"检查/配置环境""能不能直接用"时，**在开始任何专利撰写工作前先跑一次环境自检**：

```bash
python scripts/check_env.py --json
```

按返回的 JSON 分类处理缺失项（力度已定：pip 库自动补，系统级/插件只引导）：

- **`category=pip` 且 `ok=false`（如 python-docx）**：AI 直接执行 `python scripts/check_env.py --fix` 自动 `pip install` 补齐，无需逐次征询。
- **`category=system` 且 `ok=false`**：`python`（运行时）用报告里的 `install_hint` 引导用户安装，不擅自静默改环境；`pandoc` 为**推荐项**（`scripts/omml_formulas.py` 用它把说明书公式转为原生 OMML 可编辑公式；缺失时公式回退纯 LaTeX 文本写入，不阻断工作），缺失时按提示引导安装。
- **`category=plugin`（document-skills:docx）**：脚本检测不到,由 AI 在会话中确认能否调用 `document-skills:docx` skill；不能调用则按报告提示让用户重启 Claude Code 或重新加载插件。

`missing_required=0` 即必需项就绪，可进入撰写；仍缺必需项时先补齐再开工。**命令名一律 `python`，不用 `python3`**：Windows 上 `python3` 常是 Microsoft Store 空壳（调用无任何输出、exit 49），照它跑闸门脚本会拿到空输出而不报错、被误读为「无违规」（2026-09-11 本机实测）；`python` 不通时改用 `py`。本 skill 自 2026-09 起在 **Windows + Word** 环境维护（原作者 macOS + WPS），规则里提到 WPS 的渲染陷阱（G8-3 公式降级、打开占用回写）在 Word 下同样按规则执行，不因平台跳过。

## 资源目录约定

- `assets/docx/` 放 DOCX 资产，**两份性质不同、勿混用**：
  - `专利撰写模板.docx` —— **唯一可用作写入骨架的模板**（含 5 个 `sectPr`、13 个 header）。权要一稿 / 直写全文稿从它拷贝出交付稿。其正文预置的 3 段占位套话在注入时会被 `inject_fulltext_docx.py` 按文本特征删掉，收尾三段以 `docx-template.md` G8-2 嵌入的批注 21 定版原文为准（模板文件内的旧措辞不进交付稿）。
  - `参考-申请文件样例-王工2026-09.docx` —— **王工 2026-09 顺手发的参考件，非写入骨架源**（其为旧版措辞：第二段「需说明」「装置实施例」+多一句附图连接关系，与王工 H2608165 批注 21 定版不一致）。仅作格式参考；套话措辞冲突时以 G8-2 规则为准。模板类资产可能持续更新，王工后续再发模板时先与其批注定版口径比对、再决定是否替换骨架源。
- `references/cases/` 放案例标准、定稿经验和可迁移写作范例。**粒度、句式、解释深度的判据已抽象进 `references/rules/`，撰写/返修时按规则文件执行、不回读本目录**（读取纪律唯一出处 `rules.md`「案例文件读取纪律」）；目录下只有被规则点名的执行层文件（`claims-format-standard.md`、`docx-execution.md`、`INDEX.md`）可按触发条件读取。案例文件不得作为模板直接套用，不得把其中的技术对象、参数值、附图名迁移到新案件。
- `references/rules/` 放阶段化规则文件。每次任务只读取 `rules.md` 索引、`references/rules/global.md` 和当前阶段对应规则，按阶段读取规则以实现渐进式披露，避免把无关阶段规则带入上下文。
- `rules.md` 只放可跨案件复用的规则索引、阶段读取表、冲突处理原则与 **skill 维护纪律**（沉淀分诊、学习闭环、容量治理）；具体案件经验需要沉淀时，先抽象成宏观规则，原案例细节只放在 `references/cases/` 并在规则中用一句话指向。
- `agents/` 放各路审计员契约。**两类不同源，勿混**：①`{claims,content,impl,global}-auditor.md` 是**一致性检查路**——读 `references/rules/`（我们的标准），有 1 级 FAIL 否决权；②`reviewer-sim-{claims,spec}.md` 是**审稿人视角复核路（第五路）**——以审核人自用审查提示词为唯一 mandate，**禁止读本 skill 规则库**，无否决权、只出疑点清单。第五路的存在理由是不共享我们的规则库假设，详见「审查闸门通用规则」第五路条。
- `docs/archive/` 只放历史备查文件，正常工作流不得读取或执行其中的旧规则、旧脚本。

## 必读

在撰写或修订前，必须先阅读 `rules.md` 和 `references/rules/global.md`。然后根据 `rules.md` 的阶段读取表，仅读取当前任务对应的阶段规则文件。不要默认读取无关阶段规则；例如权要一稿不默认读取 `references/rules/implementation.md`、`references/rules/figures.md`，除非用户明确要求全文、摘要、附图或具体实施方式。

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

元数据缺失分两类处置，**不得混同**：①**开工必需项**——`案件文件夹`、`当前阶段`缺失时必须主动询问用户（没有它们无法定位工作对象、无法选择工作流）；②**交付文件名/校验项**——`案件号`、`发明题目`（正式发明题名全称）、`作者署名`缺失时**一律不追问、不停顿**，按上文「默认立场」新稿留空规则先写完交付，缺项汇总进完工报告「待补清单」（该口径唯一出处即「默认立场」条）。撰写者从案件路径的一级目录自动识别（白名单唯一出处 `global.md` G1）；路径不在白名单目录下或无法唯一判断时才询问用户，不要凭猜测填。

## 案件文件夹约定

用户在白名单目录（本 fork 默认 `<桌面>/专利/正式派单/`）下新建与发明题目对应的案件文件夹。目录布局与交付命名的唯一出处是 `references/rules/global.md` G1：撰写者由案件路径归属的白名单目录自动识别；案件根目录只放对外交付 DOCX 和老板批注稿，工作文件（`交底书.docx`、`交底书.md`、`权要稿.md`、`全文稿.md`）统一放 `docs/` 子目录，旧案散落文件先迁入 `docs/` 再继续。

自动识别明显文件。如果有多个可能候选，请用户选择。

## 审查闸门通用规则（两阶段共用）

**★ 审计结论必须先回原文核实（1级动作；2026-09-11 吸收王工《撰写AI自查流程指引》「AI 说的不一定对」）**：任何一路 auditor、脚本或第五路报出的问题，**处置前先回 `docs/*.md` 或 DOCX 原文定位**——①核对问题是否真实存在（AI 会报不存在的缺陷）；②指控「未说明／未记载」的，先全文搜索确认真的没写；③拿不准的，要求该路给出**原文具体位置**，给不出则不予采纳。核实后分两路收口：真问题→回修；假阳性→在审查报告标注「经核原文不成立」，并**同步修闸门或补豁免项**（同一形态第二次报错视为闸门缺陷，不是稿子的问题）。

权要一稿 step 7 与全文一稿 step 8 的闸门都按本节执行，各 step 只写差异（脚本参数、auditor 路名、传入字段）。**本节多路语义复核的强制范围仅限首次生成稿**——全文一稿三路（content/impl/global-auditor）、权要一稿两路（claims/global-auditor）为强制；返修阶段（全文二稿/三稿、权要二稿/三稿）的 auditor 语义复核**不强制**，机械脚本闸门照常强制，auditor 是否调用按 `SKILL.md` 返修工作流 step 4 询问用户：

- **调用机制（Workflow 编排，替代逐路 Agent 调用）**：多路语义复核统一通过 **`Workflow` 工具**一次编排执行，不再用 Agent 工具逐路派发 subagent。编排方式：脚本内用 `parallel()` 并行发起各路 `agent()` 调用，每路一个 `agent()`；每路的 prompt 固定为——先 Read 本路契约文件（`agents/<路名>.md` 绝对路径）并严格按契约执行，随后给出输入契约全部字段（`stage`、`md_path`、两脚本 JSON 全文内嵌、各 `*_rules_path`/`scoring_excerpt_path` 绝对路径、`triggered_rule_notes`，重审轮加 `reaudit_context`）；**规则一律传文件路径，不把规则内容抄进 prompt**（脚本 JSON 除外，其为运行产物必须内嵌）；每案件首次编排前主 agent 先跑一次 `python scripts/verify_rule_anchors.py`（校验各契约 `sed -n` 锚点与规则文件标题匹配，非 0 退出=锚点失效，先修复再编排，防止 auditor 定向提取静默取空；规则文件的节标题行由此冻结，改标题必须同步改契约锚点）；每路 `agent()` 的返回值即该路完整审查报告全文，由主 agent 在 workflow 结束后取回合并。workflow 的 `meta.name` 用 `patent-audit-<stage>`，一路一个 `phase`/`label`（用路名），不在 workflow 内做通过判定或落盘——判定与合并是主 agent 职责。 **⚠️ 编排脚本必须以 LF 换行写入磁盘**（Python 用 `io.open(path, "w", encoding="utf-8", newline="")`）——CRLF 会被 `Workflow` 的校验判为「control characters that would be hidden in the approval dialog」而拒收（H2609100 全文2稿实测，与 H2609029 同一坑）。另：prompt 文本内**不得出现反引号**（会提前闭合 JS 模板字面量），代码片段一律用「」或纯文本；内嵌 JSON 的 `\`、`${`、`` ` `` 三个序列须转义。
- **通过判定**（合并口径唯一出处 `scoring.md` 计分方法）：global-auditor 完整性 PASS + 各路 1 级均 100% + 合并 2 级分（Σ各路通过 ÷ Σ各路适用）≥90%。
- **合并落盘**：主 agent 合并各路报告落盘一份 `docs/审查报告-<稿次>.md`（合并结论在前、各路原始报告附后；同位置同规则去重，跨路冲突按 `rules.md` 冲突处理原则裁决）。未达标不得进入 DOCX。
- **回修重审**：按合并后的最短回修清单改 md 后重审——**本阶段全部机械脚本必重跑**（权要稿：check_hard_rules + check_cross_block；全文稿：check_hard_rules + check_cross_block + verify_claims_alignment）；上轮有 FAIL 的路（专审路与 global-auditor 均适用）**以增量复核模式重调**（重审轮重新调用一次 Workflow，仅编排上轮 FAIL 的路）：额外传 `reaudit_context`（上轮该路报告的失败项 + 主 agent 列出的本轮改动块清单），各路契约中标注"完整性级"或"恒全文复核"的项仍全量复核，其余上轮 PASS 且不涉改动块的项沿用上轮结论并标注"沿用"；上轮全 PASS 的专审路不重调。
  - **★ 改动块自查证据（1级动作；本条为该项唯一出处，2026-09-19 加）**：交给下一轮 auditor 的 `reaudit_context`，其**改动块清单每处必须附自查证据**——缺证据的改动**视为未改完，不得送审**：
    - **①代入／复算**：凡改动涉及**数值、阈值、示例值、公式、维度**者，把改后的值**代回原式重算一遍**，写出算式与结果（例：「320/120/60 代入米塞斯式得 235.8 ≠ 原写 285.6 → 改为 600/280/280，重算得 320 ✓」）。
    - **②下游回查**：凡改动某个量的**输出**，必须搜出**全部消费该量的位置**并逐一核对是否同步（例：「微观劣化状态矩阵 2 列 → 3 列」须回查权 9 的「分量」计数、标准化段、投影矩阵维度三处）。
      - **★ 回查范围必须机械化穷举，不得靠记忆（2026-09-22 加，H2609100 全文复盘）**：用 `python scripts/grep_impact.py <本轮改动的关键词…> --in <全文稿.md> <权要稿.md>` **列出该词在全稿的全部出现处**，逐处标注「已同步／不需同步／漏改」，**把这张清单贴进 `reaudit_context`**——缺清单即视为下游回查未做。原话教训：该案权 5 引导句补「所述」时，回查核了权要 3 处 + 说明书 2 处，**漏了说明书里「在一种实施方式中，〔引导句〕，包括：」这一族衔接句**，王工审核v2 批注 3 亲手指出；工具一跑，那处（全文稿第 127 行）就在 11 处命中里。
      - **说明书三层同步一个都不能少**：改权要后，说明书侧须同步 **①集中罗列段 ②展开段入口句 ③「在一种实施方式中，〔从权引导句〕，包括：」衔接句**。第三层最易漏，现已由 `check_cross_block.py` 的 **X8** 机械兜住（该检项 2026-09-22 修好：原先有「全文子串兜底」会被集中罗列段永远满足，等于没查）。
    - **立此条的依据（H2609100 实测，2026-09-19）**：全文闸门第二～四轮合计 9 项 FAIL，其中 **4 项是主 agent 上一轮回修自己引入的**——补体积膨胀项时写成材料常数致「判断分支对全部节点恒真」、补公式示例值未代入验算（K·u 与 F_T+F_P 相差 147 倍）、某量维度改了未回查下游消费点（状态矩阵 2 列却仍按 3 个分量算）。**绕回去重跑 auditor 的 token 与时间大半耗在这里**，且第五轮还要再确认一次。
    - ⚠️ **这不是新规则**：`global.md` G6-1 的 **W53①代入验算／②量级一致／③跨步骤数据流一致**与 `implementation.md` L8-1 的「**落笔前数值三问**」（均为 1 级）本就要求同一件事，本案属典型 **A 类「规则已有但没执行」**。故此处不加义务，只把它**定为回修动作的收口条件**——「改动即验算、验算须留证」。
- **★ 第五路·审稿人视角复核（`reviewer-sim`，无否决权，在四路/三路 auditor 全部 PASS 之后跑）**：契约 `agents/reviewer-sim-claims.md`（权要闸门）与 `agents/reviewer-sim-spec.md`（全文闸门）。它与既有 auditor 的分工是**判据来源不同**——既有各路读本 skill 的 `references/rules/`（我们的标准）做**一致性检查**；本路以**审核人自用审查提示词**为唯一 mandate 做**领域知识检查**（数值合不合常理、算式本身对不对、合不合行业习惯、符不符合领域常规理论）。**一个内部完全自洽的方案可以整体不合常理**，这是本路存在的理由。
  - **必须不读本 skill 规则库**：不传任何 `*_rules_path`，且契约禁止其 Read `references/rules/`、`agents/`、`references/cases/` —— 一旦读了就又成了"用我们的标准审我们的稿"，正是五案连续"自审全 PASS 然后挨批注"的成因。
  - **调用时点**：**机械脚本 + 各路 auditor 全部 PASS 之后**，作为进入 DOCX 前的最后一道。未过基本合规就送本路，会被格式问题淹没、看不到方案层疑点。传 `gate_result` 字段说明前置闸门已通过（该字段缺失时本路拒绝执行）。⚠️ **顺序纪律**：第五路若在 auditor 之前跑、且主 agent 据其疑点重写了 `权要稿.md`，**重写后必须增量重跑两路 auditor（reaudit_context）+ 两个机械脚本**，不得直接进 DOCX——auditor 的引用句逐字一致（X7）与 A22 条件包裹等规则层项在重写版上可能新触发 FAIL，第五路框架不含这些规则、会漏检。本路本身只给出"疑点清单"，凡采纳修改均视为"改动块"，回修重审口径同「审查闸门通用规则·回修重审」条。
  - **无否决权**：输出「疑点清单 + 依据」，**不给 PASS/FAIL、不给评分、不阻断 DOCX 注入**。判据（行业习惯、常理）本身是概率性的，给否决权会造成无法自辩的死锁。主 agent 逐条判断是否改稿；**未采纳的疑点写入完工报告「提请老板确认清单」**。
  - **落盘**：单独落 `docs/审稿人视角复核-<稿次>.md`，**不混进 `docs/审查报告-<稿次>.md`** ——后者是过闸凭证（须清零），前者是疑点备忘（不必清零），混在一起会让人误以为疑点也要清零才能交付。
  - **可联网**：本路白名单含 `scripts/patent_search.py`（patenthub.cn 专利库，**优先**，用法唯一出处＝脚本自身 `--help`/docstring——「行业习惯」对照以同类真实专利为判据）、`mcp__tavily-hikari__tavily_search`（行业现状/常规理论/数值量级）与 `WebSearch`（末位兜底）。⚠️ **禁止把交底书、权要、说明书原文贴进查询**，查询词只能是抽象后的公开技术术语（第三方端点会缓存与索引）；`docs/facts.md` 里 step 2.5 已有的检索结果优先复用。
  - **返修阶段：由主 agent 按批注实际性质决定是否调用**（不按批注条数）。判据——①纯措辞/格式/编号迁移类小修 → 不调用；②批注触及方案层或技术实质 → 调用；③**本轮返修的改动质量本身不可信**（如返修产出明显未遵守 skill、把既有内容改坏）→ **必须调用**，此时它审的是"改烂了没"而非"改动量大小"。**定稿轮不强制**（定稿即不再改，审核人该轮的改动留全案复盘）。
  - **交叉印证暂不启用**：审核人原话「最好开两个 ai 交叉印证」，实现方式是同一契约跑两次由主 agent 比对差异；**当前先跑一遍**，实测发现漏检再启用第二遍，且第二遍应**换模型**跑（重点在异质性、不在数量；同模型两遍输出高度相似）。
- **降级兜底**：任一路两次失败（无契约结构或报告"输入不完整"）时，仅该路降级为主 agent 按其契约自查并在完工报告标注"<路名> 未生效"，其余路照常生效，但脚本闸门必须通过。整次编排的降级链为**按次计数、自动切换**：第 1 次尝试 `Workflow` 工具编排（一次编完全部 auditor），失败（工具不可用/脚本报错/全部路无返回）即切第 2 次尝试 **Agent 工具逐路并行派发**（每路一个 subagent，prompt 与输入字段同调用机制条，保留物理隔离与并行独立性）；第 2 次失败再切回 `Workflow` 第 3 次重试；**Workflow 与 Agent 派发共享一个计数器，累计 3 次失败即自动切换为主 agent 串行审查**——主 agent 按各路契约逐路串行自查（每轮只带一路规则包、一轮一审不并行），完工报告标注"主 agent 串行审查（累计 3 次编排失败自动切换）"。切换后本审查流程内锁死串行，不再回退 Workflow/Agent；回修重审轮是新流程，重新从 `Workflow` 编排开始尝试。任何降级级别下脚本闸门都必须通过；降级不得静默——完工报告校验清单首行必须写明本次审查的实际执行方式（Workflow 编排 / Agent 派发 / 主 agent 串行审查）。

## 权要一稿

`权要一稿`：

1. 先按 `rules.md` 阶段读取表读取 `references/rules/claims-requirements.md`、`references/rules/docx-template.md` 与 `references/rules/scoring.md`（后者主 agent 合并计分口径所需，可按需只取「计分方法」节）（此阶段只读其 G8-0/G8-0b 及 md 层可判定条目；G8-1 XML 骨架细节留到 DOCX 执行层 step 8-12 再读）。确认案件文件夹下已有 `docs/` 子目录（无则创建），并把交底书 DOCX 放入 `docs/`。先调用官方 `document-skills:docx`（即 docx）skill 满足执行层门槛（**不用其向上下文回读交底书正文**），随后直接执行 `scripts/disclosure_docx_to_md.py --input <案件文件夹>/docs/交底书.docx --output <案件文件夹>/docs/交底书.md` 完成确定性转换；仅当脚本转换失败或批注锚点异常时，才用 `docx` skill 读原 DOCX 定点排查。交底书全文只在 step 2 深读 `交底书.md` 时进入上下文一次。
2. **主 agent 亲自深读 `交底书.md` 并产出事实提纲**（G2 深读义务）：逐条核对 `> 💡 [批注 ...]` 行，确认技术问题—技术方案—技术效果链条闭合，提取核心技术问题、关键步骤、特征命名、数据来源、数据用途、预期效果，并在深读的同时把结构化事实提纲写入 `docs/facts.md`，固定结构为：技术问题、术语表、主流程、批注圈定的创新点、优先审查要求（批注）、数据来源/用途、潜在风险。**创新点以批注圈定为准，不自行另判**（G2-1）：批注 `> 💡 [批注 ...]` 已直接写出权利要求书创新点，按其圈定的步骤/特征展开创新特征，批注未点名的步骤按支撑环节处理；批注锚点丢失（只剩批注文字、不知选中哪段）时不猜测指向，回查 DOCX 选区或记入潜在风险。优先审查案件的关键词表缺失时记入潜在风险，向用户索取。
   - **★ `facts.md` 第 0 节＝案件名称真源**（规则唯一出处 `global.md` G1）：**审核人给的案件名称**与**交底书文件名**并列两栏作交叉校验，不一致时以审核人给的为准并注明来源与日期。⚠️ 不得靠 `ls *交底书*` 截名称——名称可在撰写中途被改而文件名/文件夹名不同步。
2.5. **★★ 方案层前置体检（三项，动笔前主 agent 自做，产物写入 `docs/facts.md`）**：这一步是"一稿定稿"的关键——H2608040 权要审核 17 条批注里 6 条属方案层（现有技术写窄／技术问题维度选错／声称效果物理不可实现），**这 6 条就是该案必须返修一轮的全部原因**，而它们无一能靠格式规则拦住。三项都是**自己动笔前做的功课，不是拿去问审核人的**：
   - **① 现有技术水位**：检索本领域**近期专利 + 行业现状**，写出"现有技术已到什么水平"（规则 `claims-field-background.md` L3-1「现有技术要写足到行业当前水平」）；**再自查本方案的手段是否已在其中**（反噬自查——若在，该手段不能再作区别技术特征，须重新核区别技术特征还剩什么）。
   - **② 技术问题选维度**：列候选维度表，逐个问"成熟技术在这个指标上做到什么水平、本方案能否超过"；不能超过就换一个成熟技术不覆盖的维度（规则同上 L3-1，判定细则见 `agents/claims-auditor.md` 第 19 项）。
   - **③ 效果可实现性**：从**交底书自有参数**抽两端物理量，算尺度比与每帧跨度；**每帧跨越 > 2 倍即判盲插**（判定细则见 `agents/claims-auditor.md` 第 17 项）。H2608040 实测所需四个参数全在交底书里、一次算术即可，不需要审核人另给数据。
   - **★ ④ 行业真实创新方向与行业习惯（审核人自用审查提示词其一，本项须联网）**：①本案锁定的技术问题与权 1 技术路线，是否是本领域**当前真在投入的方向**（而非业内已绕开、或从未被视为问题的方向）；②逐个技术环节问「本领域惯常怎么做这一步、本案有无偏离」——**偏离分两类**：创新性偏离（有意为之、正是创造性所在，不是问题但审查员可能要求解释）与**非创新性偏离**（该步骤并非创新点却用了非常规做法 → 是问题，通常意味着对领域惯例不熟或交底书本身有问题）。典型形态：用分类器输出连续量、用不可逆映射反解原空间坐标、用极值统计表征渐变现象、过程结束后才生效的调整指令。
     - **为什么必须前置**：这两条判断错了，写完才发现就是白工；而第五路 `reviewer-sim-claims` 在**交付前**以同样判据复核一次（分工：本步是**写之前定方向**，第五路是**写完后验收**）。本步的检索结果写入 `facts.md`，第五路**优先复用、不重复检索**。
     - **★ 检索真实性铁律（1级；王工《专利撰写AI自查流程指引》前置定义，2026-09-11 吸收）**：①**禁止编造专利数据**——专利号/标题/申请人等事实字段只能来自 `patent_search.py` 或 Tavily 的**真实返回**，查不全写「未检索到」，不得凭模型记忆补全；②**检索为空必须降级、不许跳过**——换多组同义词重试后仍为空，按「诚实知识模式」如实写明「本次未检索到同类专利」，**禁止靠编数据凑结论**；③**来源分离**——专利数据与行业/网页数据的结论要分开标注，不得混源。
     - **★ 检索工具优先级（2026-09-02 起，王工 H2608165 指示「主要还是检索行业趋势比较重要」）**：**第一优先 `scripts/patent_search.py`**（patenthub.cn 专利库直连，用法与判据唯一出处＝脚本自身 `--help`/docstring）——同类**真实专利**是「操作手段是否符合行业习惯」最可靠的判据（远胜模型训练记忆与泛网页归纳；H2608165 七处偏离行业习惯即缺此对照）；主用法 `multi` 多候选词检索 → 挑 3-5 条最相关查 `claims` 对照主流操作手段。**第二优先 Tavily**，用于专利库覆盖不到的行业现状/市场规模/常规理论。⚠️ **两路同守一条纪律**：查询词只能是**抽象后的公开技术术语**，**禁止把交底书原文贴进查询**（第三方端点会缓存与索引）；`patent_search.py` 需环境变量 `PATENT_HUB_TOKEN`（缺失或 207/211 额度错误时降级用 Tavily，并在完工报告注明）。
   - **只有一种情况才停下来问用户**：③ 算出不可实现之后的**选型**（补实拍层级／改技术效果／降为示意）——涉及是否改动交底书方案，超出撰写权限。① ② 的结论自己拿主张。
   - **产物形态**：三项结论各成一节写入 `docs/facts.md`，与"批注圈定的创新点"并列作为起稿基准；②须留候选维度表（列出每个被弃用维度及其原因），③须留两端物理量与算式。**结论若为"无此问题"，须附据以判定的参数值**，不得只写"已核查无异常"。
3. 若 `facts.md` 的"潜在风险"段落有需要回问用户的项，或批注圈定的创新点在交底书中找不到支撑，先解决再进入撰写。
4. 先用 Markdown 把专利稿件写在 `docs/权要稿.md`。
4.5. **★ 落笔计划三张表（排权 1 分句之前做，产物 `docs/_claims_plan.md`，非交付件）**：X2608107 实测方案层体检全部通过、**问题全部落在"同一个正确判断怎么落成正确的分句"这一层**，而这一层可以做成机械清单：
   - **表一·上位程度分档**（规则 `claims-requirements.md` L1-1「上位程度分档」）：交底书每一步 → 基础档／支撑档／创新档 + 判档理由。判档标尺：解决背景技术收口问题、最重要的相关步骤＝创新档；为创新步骤提供必要输入＝支撑档；其余＝基础档。**贴档发生在排分句之前**，三档决定权 1 怎么写、从权写多深。
   - **表二·分句 → 从权引导句动作数反推**（规则同上「从权引导句只覆盖 1 个动作」）：排完每个分句**立刻**反推"它将来的从权引导句会有几个动作"，>1 就**在权 1 侧先拆**。⚠️ 本表是**事前预防**，`agents/claims-auditor.md` 第 14 项是事后检查，两者都要——事后才发现时，改法只能是回权 1 重排（改从权侧会违反引用句逐字一致）。
   - **表三·预设对象清单**（规则同上「权要内预设对象总量 ≤4–5」）：`grep -oE '预设[一-鿿]{2,10}' docs/权要稿.md` 去重成表，逐行填四列——技术必需？／能否改实测？／能否不点名？／与他项撞名？**distinct >5 即回改，不进 step 7**。
   - ⚠️ **本表与 `check_hard_rules.py` 规则 43 的分工**：规则 43 数**总量**（机械终判），本表证明**每一个都过了四问**（脚本判不了"这个对象是否技术必需"）。**表与落笔态不一致时以落笔态为准，并回改表**——X2608107/H2608165 均出现过计划表列 5 个、落笔实测 4 个而表未回改的情况。
5. **权要一稿仅撰写并展示三部分，按此顺序排列**：权利要求书 → 技术领域 → 背景技术。其他章节（说明书摘要、摘要附图、发明内容、附图说明、具体实施方式、说明书附图）一律留到全文一稿撰写，权要一稿阶段不要写入 `权要稿.md`，也不要在 DOCX 正文或页眉中显示。
6. 在 `权要稿.md` 中写完整的权要集、技术领域、背景技术。权要数量与配比（方法权写满权 9 + 计算机设备式系统权权 10，**不写存储介质权**，王工 2026-09-11）、权要 1 字数、分号断行、从权粒度和依附关系的唯一出处是 `references/rules/claims-requirements.md` 及其指向的 `references/cases/claims-format-standard.md`。
7. 写入 DOCX 之前，主 agent 只自查**脚本与 auditor 均不覆盖的项**：未误写权要一稿以外的章节（摘要等属全文一稿，见 `abstract-figures.md` L4）；**并断言 step 2.5 三项体检结论与 step 4.5 三张表已在 `docs/facts.md` / `docs/_claims_plan.md` 落盘且与落笔态一致**（表三的 distinct 数须等于 `check_hard_rules.py` 规则 43 的实测数——不一致说明表未回改，先改表再过闸）。机械项交阶段 A 脚本终判、语义项交阶段 B auditor 专审，主 agent 不预演 `claims-requirements.md` 自检清单。**随后按两阶段闸门流程审查**：
   - **阶段 A：机械化硬规则脚本前置**：由主 agent 依次执行两个脚本——先 `python scripts/check_hard_rules.py --md <权要稿.md 绝对路径> --stage claims-draft --json`（第一类硬规则），再 `python scripts/check_cross_block.py --md <权要稿.md 绝对路径> --stage claims-draft`（第二类：结构抽取 + 依附合法校验）。**任一 FAIL 直接回修**，不进入阶段 B；结构抽取失败（`extraction_ok=false`）说明写法不合 A/B 标准，按 `extraction_errors` 规范化写法后重跑。主 agent 按报告的 `location` 和 `evidence` 定点修改 `权要稿.md` 后重跑脚本，直到全部 PASS。两个脚本的 JSON 分别作为 `mechanical_check_result` 和 `structure_check_result` 传给下一阶段。
   - **阶段 B：调用 `Workflow` 工具编排两路 auditor 并行语义复核**（多路审查，每路一个 `agent()`、只带本路规则包，编排细节见「审查闸门通用规则」调用机制条；**规则一律传文件路径，不把规则内容抄进 prompt**——auditor 按契约以 `sed -n` 标题区间定向提取所需节（不整篇 Read），主 agent 只传路径与两脚本 JSON；`scoring.md` 的按路摘录已实体化为 `references/rules/scoring-<路名>.md` 静态文件，合并计分方法留在主 agent）：
     - `claims-auditor`（契约 `agents/claims-auditor.md`）：传 `stage=claims-draft` + `md_path` + `mechanical_check_result` + `structure_check_result` + `scoring_excerpt_path=references/rules/scoring-claims.md` + `claims_rules_path=references/rules/claims-requirements.md`（只执行 L1 节）+ `claims_format_standard_path=references/cases/claims-format-standard.md` + `triggered_rule_notes`。
     - `global-auditor`（契约 `agents/global-auditor.md`）：传 `stage=claims-draft` + `md_path` + 两脚本 JSON + `scoring_excerpt_path=references/rules/scoring-global.md` + `global_rules_path=references/rules/global.md`（只执行 G3-G6）+ `short_block_rules_path=references/rules/claims-field-background.md`（只执行 L2+L3 节）+ `docx_template_rules_path=references/rules/docx-template.md`（只执行 md 层可判定条目）+ `triggered_rule_notes`。
     **通过判定、合并落盘（`docs/审查报告-权要N稿.md`）、回修重审与降级兜底一律按「审查闸门通用规则」节执行。**
   - **阶段 C：两路 auditor 全部 PASS 后，调 `reviewer-sim-claims` 做审稿人视角复核**（第五路，无否决权，细则见「审查闸门通用规则」第五路条）：传 `stage=claims-draft` + `md_path=docs/权要稿.md` + `facts_path=docs/facts.md` + `gate_result`（一句话写明"两路 auditor 与两个机械脚本已全部 PASS，第 N 轮"）+ `workflow_mode=separate`。**不传任何规则文件路径。** 疑点清单落 `docs/审稿人视角复核-权要N稿.md`；主 agent 逐条判断是否改稿，**未采纳的疑点写进完工报告「提请老板确认清单」**。本路不阻断——即便有疑点未改，仍可进入 step 8 写入 DOCX。
8. **闸门通过 → 直接写入 DOCX**（不等待用户确认/Enter）：确认已显式调用官方 `document-skills:docx`（即 docx）skill（首次进入执行层调用一次即可）。
9. 由 `docx` 执行层把内置模板 `assets/docx/专利撰写模板.docx` 拷贝到案件文件夹（用户明确指定其他模板时除外），重命名遵循 G1 + 「默认立场」新稿留空规则（作者/案件号缺则写 `待补`，发明题名缺则从权 1 保护主题提取占位），不追问、不停顿。
10. 由 `docx` 执行层采用 unpack → edit XML → pack，**权要三章由脚本注入、不手填**：`python scripts/inject_fulltext_docx.py <unpack目录> --claims-md <案件文件夹>/docs/权要稿.md --invention-name "<facts.md 第 0 节的案件名称原样>"`（权要 1..N 注分节3；发明名称 → 技术领域 → 背景技术注分节4 开头，并清掉分节4 内模板预置的 `......` 占位套话段；三种段 XML 内置王工定稿标准段，就地替换、不清空 body、不删 sectPr/header；分节1/2/5 不动）。`--invention-name` 传王工给定名称**原样**（含不含「一种」照给定值），未确认时传 `待补` 并记待补清单，不得从权 1 保护主题推导。模板骨架保护与各分节应填内容的唯一出处是 `references/rules/docx-template.md` G8-0、G8-0b、G8-1。
11. 权要一稿的可见范围按 G8-0 对照表"权要稿"列与 G8-1 可见性规则执行（章节清单唯一出处为 G8-0 表，本步不复列）；后续阶段槽位保留不删。
12. 完成后由 `docx` 执行层做通用 DOCX 验证，再跑 `python scripts/verify_docx_skeleton.py <docx> --stage 权要 --invention-name "<facts.md 第 0 节的案件名称原样>"`（骨架 + G8-0 分节落位 + G8-0b 发明名称六属性与标题段格式 + 权要段行距 + 发明名称=给定名称，任一 FAIL 回修重跑），再由 `patent` 按 `docx-template.md` G8-1（案例性术语清理、权要1字数、分号断行）核对脚本未覆盖项。验收通过后，把 `docs/权要稿.md` 复制为 `docs/history/权要1稿.md`（快照留档，命名见 G1）。
13. 仅报告：输出 DOCX 路径、`docs/交底书.md` 路径、`docs/权要稿.md` 路径、按"完工报告"的**校验清单**格式逐规则打 ✅/❌/➖，以及任何需要用户关注的问题。不出独立的撰写检查报告。

## Word 批注修订（留痕返修）

`权要二稿/三稿` 或 `全文二稿/三稿`。**默认产物 = 留痕稿**：以 `<用户指定署名>` 名义的 track changes 修订痕迹，**保留老板原有的批注与修订不动**，默认不清除批注；仅当用户明确要求定稿/归档干净稿时才另行清除。开工前若用户尚未提供署名，先按「默认立场」询问。

**完整返修工作流（审核稿到手 XML 实测三件事、返修意见读取、留痕注入、权要联动回写、校验项、学习闭环）的唯一出处 = `references/rules/revision-docx.md`**，进入返修阶段必读该文件，本节不复述判据。若返修改动了权利要求书内容，注入并校验完成后把最新权要同步回写 `docs/权要稿.md`，保证后续全文阶段的 md 基准不陈旧。

**学习闭环（★ **该阶段定稿后**才做，不是每轮返修收尾；跨阶段义务、不随本节外置）**：先过升格三闸（判据唯一出处 `rules.md`「学习闭环（复盘、升格与留痕）」节）——三进四不进 → 升格前去重检索 → 规则节清单容量上限；三闸结论回标**该案复盘文档**（`references/cases/lxl/<案号>-…复盘与下案提效清单.md`）的升格状态，**不得为凑完整度强行升格**。**唯一例外＝重申类批注**：该条含一项**当轮生效的返修义务**（对本稿全文扫描同类问题一并改齐），在返修轮即须执行，不等定稿。过闸后把可迁移的写作规律按主题补入**对应阶段规则文件**（返修纪律进 `revision.md`、权要表达进 `claims-requirements.md`、全文公开充分进 `implementation.md`、模板/XML 进 `docx-template.md`、附图进 `figures.md`），`rules.md` 仅在新增阶段索引或冲突原则时更新；具体案例只进 `references/cases/`，先给用户看 diff 再并入，本案技术对象名/参数值/附图名不进通用规则。

批注与硬性规则、交底书或可实施性冲突时的处理，唯一出处是 `rules.md` 冲突处理与 `references/rules/revision.md` G9。

## 全文一稿

`全文一稿`：

1. 先按 `rules.md` 阶段读取表读取 `references/rules/implementation.md`、`references/rules/figures.md`、`references/rules/docx-template.md` 与 `references/rules/scoring.md`（后者主 agent 合并计分口径所需）；**全文阶段不整篇读 `references/rules/claims-requirements.md`**（权要已冻结，全文只补说明书，术语一致与权要对应已由 `global.md G4`、`invention-content.md L6` 覆盖），仅两种情形按需**定向提取**：①本步的冻结块只读体检；②返修批注涉及权要联动。从最新已审权要 DOCX 开始，不从空白模板起稿；若候选不唯一，必须先请用户确认使用哪一份权要 DOCX。并从该 DOCX 提取权利要求书全文作为全文稿唯一权要基准（**DOCX 为权威源**）：提取后与 `docs/权要稿.md` 的权利要求书比对，不一致时以 DOCX 为准**回写更新 `docs/权要稿.md`**，使后续闸门与三路 auditor 使用的 `claims_md_path` 基准与 DOCX 保证一致；一致则直接使用。若 `docs/全文稿.md` 已存在且其权要内容或撰写时间早于最新已审权要，必须先按 `implementation.md` L8-0 对照新权要重构受影响章节，禁止直接复用旧稿注入。
   - **冻结块只读体检（1级，开工前置，规则唯一出处 `implementation.md`「阶段映射与权要冻结」节）**：本工作流（权要已单独定稿冻结）必做。对上一句刚确定的权要基准与稿内技术领域、背景技术做一遍只读扫描，规则用 `sed -n '/^### L1-1 /,/^### L1-2 /p' claims-requirements.md`、`sed -n '/^### L2-1 /,/^### L2-2 /p' claims-field-background.md`、`sed -n '/^### L3-1 /,/^### L3-2 /p' claims-field-background.md` 三段定向提取（**只取 1 级块**，不读 2 级与自检清单；提取为空即按输入不完整处理，不得静默跳过）。发现违反项**不擅改冻结块**，逐项记入完工报告「提请老板确认清单」（含所在权要条/块、违反的规则编号、原文摘录）。**直写全文稿工作流不执行本项**（权要与全文同轮产出、自始不冻结，判据见该节适用边界）。
2. 除非用户要求改动，保留已审权要不变。
3. **在开始补写说明书前，获取或复用 `docs/facts.md`**：若 `docs/facts.md` 已在权要一稿阶段生成且交底书未变更，直接复用；否则由主 agent 在下述深读时亲自生成（结构同权要一稿 step 2 的事实提纲）。主 agent **必须亲自深读 `docs/交底书.md`**（G2 深读义务）并核对批注、技术链和潜在风险，`facts.md` 只是深读的落盘产物，不替代深读本身。
4. 在 `docs/全文稿.md` 中补全权要一稿未写的章节，必须按 `references/rules/implementation.md`「全文稿分块撰写法」（唯一出处）逐块写、逐块过自检清单，不得一次性生成全文长文；具体实施方式框架按 `implementation.md` L8-0 Sxx 框架同构规则执行。
   - **★ 动笔前先跑模板句渲染（1级动作）**：`python scripts/boilerplate.py render --method-name "<方法名>" --system-name "<系统名>"`——参数=本案方法/系统保护主题（取自 `facts.md` 第 0 节案件名称真源，方法名=给定名称去「及系统/及装置」后缀、系统名同词干+「系统/装置」；无系统权不传 `--system-name`）。渲染出的 11 句模板句**整句粘贴、只填自由槽位**（`{串述}`/`{手段}`/`{效果}`），不凭记忆手写；口径与细节见 `docx-scripts.md`。
   - **★ 每块写完立刻过「审核人四问」**（清单唯一出处 `references/rules/implementation.md` L8-1「审核人四问」条，**本 step 只留指针、不复述**）：①这个运算**对什么做**；②**这个数哪来的**（且不得用待判断结果反推阈值）；③**另一半分支呢**（含"为零/不存在/冷启动"的边界情形）；④**同名同义吗**。**答案不能在稿中定位的，该块不算写完。** 四问与「逐槽点数」分工：四问抓"该写的没想到"（链条断裂、分支缺失、术语双义），逐槽点数（`check_preset_params.py` 预设量点数闸门 + `global.md` G6-1 公式/统计/判断/模型各清单）抓"想到了但写得不全"——**反向质询解决不了槽位漏填型问题**，两者都要过。
5. 在说明书中解释每一条权要步骤。
6. 加入有益效果的技术原因。
7. 生成图 1（摘要附图 = 方法主流程图）：运行 `python scripts/render_patent_figure.py --claims-md <案件文件夹>/docs/权要稿.md --output <案件文件夹>/docs/figures/figure-1.png`。节点 = 权要 1 分句逐字、编号 S11..S1N 右侧引出线，均由脚本从权要稿构造保证；规则唯一出处 `references/rules/figures.md` L9。脚本报错（无方法独权提取不到分句）时按 L9/L5 请用户自备 PNG；权要在后续任何轮次被改动时必须重跑本步并重新注入。本 skill 不再输出"附图设计（供手画 Visio 用）"节，附图不手画。
8. **写入 DOCX 之前过闸**（按 8a→8b→8c 顺序，任一步 FAIL 不得进入下一步）：

   **8a. 主 agent 自查——只查任何闸门都不覆盖的项**
   - `docs/figures/figure-1.png` 已按最新权要生成（渲染脚本零 ERROR 退出；附图内容一致性由脚本构造保证，不在多路审查范围）。
   - 其余跨块项（权要保留、术语一致、案例性术语、禁用措辞、公式、模型/阈值细节、可实施性）**一律交脚本与三路 auditor 终判，主 agent 不做全量初检**。

   **8b. 基准时序前置守卫（两个，FAIL 时不得进入 8c 与注入）**
   - `python scripts/timestamp_guard.py --case <案件文件夹>` —— 全文稿早于审核稿即 exit=3，先查权要是否变更。
   - `python scripts/fingerprint_claims.py --check --fulltext <案件文件夹>/docs/全文稿.md --claims <案件文件夹>/docs/权要稿.md` —— 权要基准 sha1 变更即 exit=3 硬停，按 L8-0 先 diff→同步→重构，重构后 `--gen` 更新指纹。

   **8c. 机械化脚本闸门（三个，依次跑）**
   - ① `python scripts/check_hard_rules.py --md <案件文件夹>/docs/全文稿.md --stage full-draft --claims-md <案件文件夹>/docs/权要稿.md --invention-name "<正式题名全称>" --draft-round 1 --json` —— 第一类硬规则。**三个参数都必传**：
     - `--claims-md`：量词检查的权要原文复述豁免（G6-1 适用边界），**并作为 L8-1 稿次字数区间的合并统计输入**——交付 DOCX 含权要三章，缺此参数则字数项记为未执行。
     - `--invention-name`：本案正式发明题名全称（含"及系统／及装置"后缀，取自案件已确认元数据，如 `"一种基于边缘计算的喷胶机自适应控制方法及系统"`），用于 G8-0b A 类槽位题名逐字校验。不传则该项静默不执行、只回 `S-W35-name-input-missing` suspect，题名错漏无人拦截。
     - `--draft-round`：本流程恒为 `1`，校验 L8-1 稿次字数区间（1稿 15000–17000，Word「字数」口径、`全文稿.md`＋`权要稿.md` 合并计）。不传则回 `S-L8-1-draft-round-missing` suspect、字数无人拦截。
   - ② `python scripts/check_cross_block.py --md <案件文件夹>/docs/全文稿.md --stage full-draft --claims-md <案件文件夹>/docs/权要稿.md` —— 第二类跨块：结构抽取 + L8-0 步骤数同构 + 主步骤编号连续 + 依附合法 + 禁止合并展开。`--claims-md` 传入权要基准（全文稿.md 不含冻结的权利要求书）。
   - ③ `python scripts/verify_claims_alignment.py --md <案件文件夹>/docs/全文稿.md --claims-md <案件文件夹>/docs/权要稿.md --stage full-draft` —— 反向特征差集 + 撞名 + 步骤集差集。`hard` 违规＝完整性 FAIL 定点回修；`suspect` 项以 `alignment_check_result` 字段（该脚本完整 JSON）传各路 auditor 逐条复核处置。
   - **失败处置**：任一脚本不通过时按输出定点回修再重跑，不得跳过。结构抽取失败（`extraction_ok=false`）说明 Sx 步骤或权要写法不合标准写法（L8-1 主步骤展开范式，A 范式唯一），按 `extraction_errors` 规范化后重跑。

   **8d. 三个脚本全部通过后，调用 `Workflow` 工具编排三路 auditor 并行独立复核**（多路审查，每路一个 `agent()`、只带本路规则包，编排细节见「审查闸门通用规则」调用机制条）：
   - **规则一律传文件路径，不把规则内容抄进 prompt** —— auditor 按契约以 `sed -n` 标题区间定向提取所需节（不整篇 Read）。
   - `scoring.md` 的按路判据在 `references/rules/scoring-<路名>.md`（定位见 `scoring.md`「分层定位」节），合并计分方法留在主 agent。
   - 权要冻结基准 `claims_md_path=docs/权要稿.md` 传给三路。
   - `content-auditor`（契约 `agents/content-auditor.md`）：传 `stage=full-draft` + `md_path=docs/全文稿.md` + `claims_md_path` + `mechanical_check_result` + `structure_check_result` + `alignment_check_result` + `scoring_excerpt_path=references/rules/scoring-content.md` + `content_rules_path=references/rules/invention-content.md`（只执行 L6 节与 L8-0 反向断言条）+ `triggered_rule_notes`。
   - `impl-auditor`（契约 `agents/impl-auditor.md`）：传同上公共项（含 `alignment_check_result`）+ `scoring_excerpt_path=references/rules/scoring-impl.md` + `impl_rules_path=references/rules/implementation.md`（只执行 L8 节；Sxx 展开范式唯一出处即 L8-1）+ `global_rules_path=references/rules/global.md`（只执行 G6-1 节：公式/统计/判断清单与模型测度）。
   - `global-auditor`（契约 `agents/global-auditor.md`）：传 `stage=full-draft` + `md_path` + `claims_md_path` + 两脚本 JSON + `alignment_check_result` + `fingerprint_check_result`（`fingerprint_claims.py --check` 结果，用于权要冻结完整性项判据）+ `scoring_excerpt_path=references/rules/scoring-global.md` + `global_rules_path=references/rules/global.md`（只执行 G3-G6）+ `short_block_rules_path=references/rules/abstract-figures.md`（只执行 L4+L5+L7 节）+ `docx_template_rules_path=references/rules/docx-template.md`（只执行 md 层可判定条目）+ `triggered_rule_notes`。
   **通过判定、合并落盘（`docs/审查报告-全文N稿.md`）、回修重审与降级兜底一律按「审查闸门通用规则」节执行。**
   - **三路 auditor 全部 PASS 后，调 `reviewer-sim-spec` 做审稿人视角复核**（第五路，无否决权，细则见「审查闸门通用规则」第五路条）：传 `stage=full-draft` + `md_path=docs/全文稿.md` + `claims_md_path=docs/权要稿.md` + `facts_path=docs/facts.md` + `gate_result`（写明"三路 auditor 与全部机械脚本已 PASS，第 N 轮"）+ `workflow_mode=separate`。**不传任何规则文件路径。** 疑点清单落 `docs/审稿人视角复核-全文N稿.md`；未采纳的疑点写进完工报告「提请老板确认清单」。本路不阻断。
   **闸门通过后直接进入 step 9 写入 Word，不因缺元数据而停下询问（缺项按下方 step 9 留空规则处理，统一汇总到完工报告的待补清单）。**
9. **闸门通过 → 直接写入 DOCX**（不等待用户确认/Enter）：确认已显式调用官方 `document-skills:docx`（即 docx）skill（首次进入执行层时调用一次即可，后续 step 复用）。**交付文件名命名规则**：`<案件号>-全文N稿-<作者>-<发明题目全称>.docx`（唯一出处 G1）。**缺元数据时的留空规则**（本 step 不追问、不停顿）：①**作者**未提供时，文件名作者位写 `待补`（如 `待补-全文1稿-待补-…docx`，案件号也缺则前缀整段省略或同样写 `待补`），完工后由用户自行改名；②**发明题名**未提供时，从权 1 保护主题自动提取作为文件名题名位（如"一种基于边缘计算的喷胶机自适应控制方法及系统"），但 `check_hard_rules.py --invention-name` 的正式题名**不得用自动提取值冒充**（G8-0b 信源纪律：正式题名须案件元数据确认；提取值仅用于文件名占位），此时该脚本传空、题名校验报 `S-W35-name-input-missing` suspect、记入待补清单。**所有留空/占位项一律记入完工报告「待补清单」**，由用户在收稿后补齐（含：案件号、正式发明题名全称、作者署名）。
10. 由 `document-skills:docx` 执行层把最新已审权要 DOCX 前向拷贝为 `案件号-全文N稿-作者-发明题目全称.docx`（命名唯一出处 G1）。
11. 由 `docx` 执行层采用 unpack → edit XML → pack：**直接在 step 10 前向拷贝出的 `案件号-全文N稿-作者-发明题目全称.docx` 上就地操作**——**不得改用空白模板另存**（模板内没有本案权利要求书/技术领域/背景技术，权要三章正是靠 step 10 的前向拷贝带过来的；用模板会交出一份权要三章为模板占位内容的废稿）。随后跑 `python scripts/inject_fulltext_docx.py <unpack目录> --md <案件文件夹>/docs/全文稿.md`（默认一次性注入摘要+发明内容+附图说明+具体实施方式四章，可选 `--block` 分块调试），把全文稿就地注入分节1（摘要）与分节4（L6–L8）。骨架保护与分节落位唯一出处是 `docx-template.md` G8-0/G8-0b/G8-1；权要三章（权利要求书/技术领域/背景技术）由 step 10 前向拷贝保留，不在本脚本范围。正文注入完成后、最终 pack 前，运行 `python scripts/insert_figures_docx.py <unpack目录> --png <案件文件夹>/docs/figures/figure-1.png` 把图 1 注入分节 2（摘要附图）与分节 5（说明书附图，含"图1"图题），再 pack。pack 后跑 `python scripts/verify_docx_injection.py <案件文件夹>/案件号-全文N稿-作者-发明题目全称.docx --md <案件文件夹>/docs/全文稿.md` + `python scripts/omml_formulas.py check <docx>`（必要时 `fix-settings`）+ `python scripts/verify_docx_skeleton.py <docx> --stage 全文 --invention-name "<正式题名，同 check_hard_rules --invention-name>"` 三件套收尾验收。
12. 报告完工前，**机械闸门统一走总跑**：`python scripts/run_gates.py <案件文件夹> --invention-name “<王工给定名称>”`——它按**固定清单**一次跑完全部机械闸门（权要+全文 hard_rules、跨块、对齐、指纹自锁、预设量、时序、页数、骨架、注入），输出一张表（闸门/结论/退出码/计数/备注），跑不了的**显式标「未执行」并给原因、以退出码 2 逼补**，不静默跳过。**该表即完工报告校验清单的底稿，逐行抄入**；清单只此一处，**不得凭记忆手挑脚本**（H2609100 全文1稿就是这样漏掉 `check_preset_params` 与 `check_page_count` 的：审查报告的闸门表只有 5 个脚本，既没跑、也没人发现少了）。表内 FAIL 项逐条按脚本 docstring 的校准要点给「已改（写改后原文）」或「判为误报（贴原文与位置）」。随后由 `docx` 执行层做通用 DOCX 验证；**页数报 STALE 时须用 Word/WPS 打开另存后重跑，不得据当前值判达标**；再由 `patent` 核对 G8-1 脚本未覆盖项；验收通过后，把 `docs/全文稿.md` 复制为 `docs/history/全文1稿.md`（快照留档，命名见 G1）；完工报告按”完工报告”的**校验清单**格式逐规则打 ✅/❌/➖。

## 直写全文稿（有经验撰写者）

`直写全文稿`：用户指令"直接写完全文稿"（或同义表述，如"一次性写完权要和全文""直接全写完"）触发，资格不预判、不靠白名单，纯由用户口头指令区分。经验丰富的撰写者在 md 层一轮写完权要稿+全文稿，**先过权要闸门、再过全文闸门（两闸门串行在 md 层完成），最后只写一次 Word**——只出 `案件号-全文1稿-作者-发明题目全称.docx`，**不单独出 `权要1稿.docx`**（权要三章直接并入本稿）。若用户中途想先让老板审权要，改用传统「权要一稿」流程分阶段出稿。两闸门不冗余（权要闸门管 L1/L2/L3 三章本身合规，全文闸门管 L4–L8 说明书章节 + 与权要镜像对齐），串行执行是正确顺序。

1. 先按 `rules.md` 阶段读取表「直写全文稿」行读取 `global.md`、`claims-requirements.md`、`claims-field-background.md`（**全量，不冻结**）、`abstract-figures.md`、`invention-content.md`、`implementation.md`、`figures.md`、`docx-template.md`、`scoring.md`。确认案件文件夹下已有 `docs/` 子目录（无则创建），把交底书 DOCX 放入 `docs/`。先调用官方 `document-skills:docx`（即 docx）skill 满足执行层门槛（**不用其向上下文回读交底书正文**），随后直接执行 `scripts/disclosure_docx_to_md.py --input <案件文件夹>/docs/交底书.docx --output <案件文件夹>/docs/交底书.md` 完成确定性转换。权要规则不冻结，是本阶段必读核心。
2. **主 agent 亲自深读 `docs/交底书.md` 并产出 `docs/facts.md`**（G2 深读义务，结构同权要一稿 step 2）：逐条核对批注、技术问题—技术方案—技术效果链条闭合，提取核心技术问题、关键步骤、特征命名、数据来源/用途、预期效果、批注圈定创新点（G2-1，创新点以批注圈定为准）、潜在风险。
2.5. **★★ 方案层前置体检（三项）＋ 2.6 `facts.md` 第 0 节案件名称真源**：与权要一稿 step 2.5 **完全同流程**（三项体检产物、只有一种情况才停下来问用户、结论须附判定参数），本节不复述。
3. **md 层先写权要稿**（`docs/权要稿.md`）：按 `claims-requirements.md`、`claims-field-background.md` 规则写权利要求书 → 技术领域 → 背景技术三部分（同权要一稿 step 5/6）。此时不写任何说明书章节、不动 Word。
3.5. **★ 落笔计划三张表**（产物 `docs/_claims_plan.md`）：与权要一稿 step 4.5 **完全同流程**（表一上位程度分档在排分句前做、表二分句→引导句动作数反推、表三预设对象清单 distinct >5 即回改），本节不复述。
4. **跑权要闸门（claims-draft，此时无任何 Word 产物）**：先断言 step 2.5 体检结论与 step 3.5 三张表已落盘且与落笔态一致（表三 distinct 数须等于规则 43 实测数），再 `python scripts/check_hard_rules.py --md <案件文件夹>/docs/权要稿.md --stage claims-draft --json`，再 `python scripts/check_cross_block.py --md <案件文件夹>/docs/权要稿.md --stage claims-draft`。任一 FAIL 按 `location`/`evidence` 定点回修 `权要稿.md` 重跑，直到全 PASS。PASS 后按「审查闸门通用规则」用 `Workflow` 工具编排 claims-auditor + global-auditor 两路并行语义复核（`stage=claims-draft`，规则一律传文件路径，编排细节同权要一稿 step 7 阶段 B）。通过判定、合并落盘（`docs/审查报告-权要1稿.md`）、回修重审同「审查闸门通用规则」。**两路 PASS 后调 `reviewer-sim-claims`**（第五路，无否决权）：传 `stage=claims-draft` + `md_path` + `facts_path` + `gate_result` + **`workflow_mode=direct`** —— ⚠️ **直写模式下权要不经审核人过目即进入说明书撰写，本路是权要侧唯一的外部检查，且挡在大量下游工作之前，价值明显高于分离式**。疑点清单落 `docs/审稿人视角复核-权要1稿.md`；未采纳的疑点进完工报告「提请老板确认清单」。本路不阻断，可继续 step 5。
5. **权要闸门 PASS 后，立即跑 `python scripts/fingerprint_claims.py --gen --fulltext <案件文件夹>/docs/全文稿.md --claims <案件文件夹>/docs/权要稿.md`**，把权要稿当前分句序列的 sha1 写入 `docs/全文稿.md` 头部 front-matter（为后续 `--check` 准备；此时 `全文稿.md` 可仅为含 front-matter 的空壳）。**写全文期间权要稿不得再改**——一旦改动必须回本步重新 `--gen`，否则后续 `--check` 硬停（exit 3）。
6. **md 层续写全文稿**（`docs/全文稿.md`）：按 `implementation.md`「全文稿分块撰写法」（唯一出处）逐块撰写 L4 说明书摘要 → L5 摘要附图 → L6 发明内容 → L7 附图说明 → L8 具体实施方式（L8 按 L8-0 Sxx 框架同构、逐条主步骤分批写），逐块过自检清单、自检通过才写下一块；以已通过自检的权要三章为术语与链条基准。L9 附图见 step 7。
   - **★ 动笔前先跑模板句渲染（1级动作）**：`python scripts/boilerplate.py render --method-name "<方法名>" --system-name "<系统名>"`——参数=本案方法/系统保护主题（取自 `facts.md` 第 0 节案件名称真源，方法名=给定名称去「及系统/及装置」后缀、系统名同词干+「系统/装置」；无系统权不传 `--system-name`）。渲染出的 11 句模板句**整句粘贴、只填自由槽位**（`{串述}`/`{手段}`/`{效果}`），不凭记忆手写；口径与细节见 `docx-scripts.md`。
   - **★ 每块写完立刻过「审核人四问」**：与全文一稿 step 4 同流程（清单唯一出处 `references/rules/implementation.md` L8-1「审核人四问」条），本节不复述。
7. 生成图 1（摘要附图 = 方法主流程图）：`python scripts/render_patent_figure.py --claims-md <案件文件夹>/docs/权要稿.md --output <案件文件夹>/docs/figures/figure-1.png`（规则唯一出处 `figures.md` L9，同全文一稿 step 7）。
8. **跑全文闸门（full-draft，此时仍无任何 Word 产物）**，按 8a→8b→8c 顺序：

   **8a. 基准时序前置守卫（FAIL 不得进入 8b）**
   - `python scripts/timestamp_guard.py --case <案件文件夹>` —— 直写模式无 `审核*.docx` 时 exit 0，安全不触发。
   - `python scripts/fingerprint_claims.py --check --fulltext <案件文件夹>/docs/全文稿.md --claims <案件文件夹>/docs/权要稿.md` —— 验权要稿自 step 5 `--gen` 后未改动，sha1 不一致即 exit 3 硬停，回 step 5 处理。

   **8b. 机械化脚本闸门（依次跑）**
   - ① `check_hard_rules.py --md <案件文件夹>/docs/全文稿.md --stage full-draft --claims-md <案件文件夹>/docs/权要稿.md --invention-name "<正式题名全称>" --draft-round 1 --json` —— `--invention-name` 与 `--draft-round` 均必传，口径同全文一稿 step 8c①；直写模式恒为 1 稿。
   - ② `check_cross_block.py --md <案件文件夹>/docs/全文稿.md --stage full-draft --claims-md <案件文件夹>/docs/权要稿.md`
   - ③ `verify_claims_alignment.py --md <案件文件夹>/docs/全文稿.md --claims-md <案件文件夹>/docs/权要稿.md --stage full-draft` —— `--claims-md` 传入同会话刚写完的权要稿；守卫不检查"已审批/冻结"标记，只看磁盘内容。
   - **失败处置**：任一 FAIL 定点回修 `全文稿.md` 重跑；结构抽取失败按 `extraction_errors` 规范化写法后重跑。

   **8c. 三脚本全 PASS 后的语义复核**
   - 按「审查闸门通用规则」用 `Workflow` 工具编排 content-auditor + impl-auditor + global-auditor 三路并行（`stage=full-draft`，`claims_md_path=docs/权要稿.md` 传给三路，编排细节同全文一稿 step 8d）。通过判定、合并落盘（`docs/审查报告-全文1稿.md`）、回修重审同「审查闸门通用规则」。
   - **三路 PASS 后调 `reviewer-sim-spec`**（第五路，无否决权）：传 `stage=full-draft` + `md_path` + `claims_md_path` + `facts_path` + `gate_result` + `workflow_mode=direct`。疑点清单落 `docs/审稿人视角复核-全文1稿.md`；未采纳的疑点进完工报告「提请老板确认清单」。本路不阻断。
9. **两闸门均 PASS → 一次性写入 Word**（不等待用户确认/Enter）：进入 DOCX 执行层，确认已显式调用官方 `document-skills:docx` skill（首次进入执行层调用一次即可）。由 `docx` 执行层把内置模板 `assets/docx/专利撰写模板.docx`（用户明确指定其他模板时除外）拷贝到案件文件夹，重命名遵循 G1 + 「默认立场」新稿留空规则：作者缺则作者位写 `待补`，发明题名缺则从权 1 保护主题提取作文件名占位，案件号缺则前缀省略或 `待补`；采用 unpack → edit XML → pack：**权要三章 + 全文四章一条命令注完**——`python scripts/inject_fulltext_docx.py <unpack目录> --md <案件文件夹>/docs/全文稿.md --claims-md <案件文件夹>/docs/权要稿.md --invention-name "<facts.md 第 0 节的案件名称原样>"`（权要 1..N 注分节3、发明名称+技术领域+背景技术注分节4 开头、L4 摘要 + L6 发明内容 + L7 附图说明 + L8 具体实施方式注分节1/4；就地下笔、不清空 body、不删 sectPr；三种权要段 XML 内置王工定稿标准段，段落成段与块/行内公式编译由脚本保证；可选 `--block` 分块调试；骨架与分节落位唯一出处 `docx-template.md` G8-0/G8-0b/G8-1）。**权要三章不得手填**（H2609029 审核v1 王工「格式乱套，发明名称不一致，副标题也没了」即手填所致）；`--invention-name` 传 `facts.md` 第 0 节的王工给定名称**原样**，含不含「一种」都照给定值、脚本不加不减；名称未确认时按「默认立场」留空规则传 `待补` 并记待补清单，**不得从权 1 保护主题推导后填进发明名称段**。正文注入完成后、最终 pack 前，运行 `python scripts/insert_figures_docx.py <unpack目录> --png <案件文件夹>/docs/figures/figure-1.png` 注入图 1 至分节 2/5，再 pack。pack 后跑 `python scripts/verify_docx_injection.py <案件文件夹>/<交付文件名>.docx --md <案件文件夹>/docs/全文稿.md` + `python scripts/omml_formulas.py check <docx>`（必要时 `fix-settings`）+ `python scripts/verify_docx_skeleton.py <docx> --stage 全文 --invention-name "<同上>"` 三件套收尾验收。
10. 报告完工前，先由 `docx` 执行层做通用 DOCX 验证，再由 `patent` 核对 step 9 三件套中 `verify_docx_skeleton.py --stage 全文 --invention-name <给定名称>` 的报告（G8-0 逐分节落位、G8-0b 发明名称六属性与五个章节标题格式、权要段行距、发明名称=给定名称均已机械化，任一 FAIL 回修重跑）与 G8-1 脚本未覆盖项；验收通过后，把 `docs/全文稿.md` 复制为 `docs/history/全文1稿.md`、`docs/权要稿.md` 复制为 `docs/history/权要1稿.md`（权要虽未单独出 Word，仍留 md 快照，命名见 G1）；完工报告按“完工报告”的**校验清单**格式逐规则打 ✅/❌/➖，**并注明本稿为直写模式、未出独立 `权要1稿.docx`**；**所有留空/占位项（案件号、正式发明题名、作者署名等）汇总进完工报告「待补清单」**，由用户收稿后补齐或改名。

## DOCX 处理注意事项

所有 DOCX 工作均由官方 `document-skills:docx`（即 docx）skill 作为执行层。`patent` 只给出专利业务决策、模板约束和验收标准，不绕过 `docx` 直接处理 DOCX。

**安全文件操作纪律、辅助脚本清单（参数与语义）、历史脚本禁用项的唯一出处 = `references/rules/docx-scripts.md`**。各闸门脚本在流程中的**调用时点与必传参数**见本文件各阶段 step，不在此重复。

## 完工报告

**★ 不允许定稿的情形（王工《撰写AI自查流程指引》第 9 步，2026-09-11 吸收）**：下列任一未清，一律压着不定稿——①说明书有未补的预设／模型说明（26.3）；②权要存在指示代词（其/该）或引用断裂；③公式参数缺定义或举例数值验算不等价；④附图与正文内容不一致。**可定稿 = 前述必改项全部清零 + 形式问题核实修改完毕。**

最终报告简短即可：

- 输出文件路径
- 完成阶段
- **校验清单**（权要一稿/全文一稿交付时必附）：**直接从合并落盘的 `docs/审查报告-*.md` 与验收结论转录，逐规则编号打勾，不重新校验**。用 emoji 标记：✅ 通过、❌ 失败（注明原因）、➖ 不适用（注明理由）。按块分组列出，格式如下：

  ```
  校验清单：

  【审查执行】
  ✅ 审查执行方式：Workflow 编排 / Agent 派发 / 主 agent 串行审查（写实际方式；降级须注明原因）
  ✅ 第五路 reviewer-sim 已跑（无否决权；疑点 N 条，已采纳 M 条、未采纳 N-M 条已列入提请老板确认清单）
     ➖ 或：本轮未调 reviewer-sim（写明理由：纯格式小修 / 定稿轮不强制）

  【脚本闸门】
  ✅ check_hard_rules.py 硬规则脚本 PASS
  ✅ check_cross_block.py 结构/跨块校验 PASS
  ✅ verify_claims_alignment.py 对齐校验 PASS（全文稿；hard=0，suspect 已由 auditor 逐条处置）
  ✅ A5 第三层联动：返修轮已传 `--prev-claims/--prev-md` 快照比对（无 suspect 或已逐条处置）；首稿轮由 content-auditor 语义核
  ✅ check_cross_block.py 的 X8（从权引导句在说明书逐字复现）PASS（全文稿；权要本轮有改动时重点看）
  ✅ 模板句逐字（boilerplate.py check；系统权整条由规则 51 在权要侧查；介质相关三句为禁写项，出现即 FAIL）PASS
  ✅ 规则 52 有益效果字数 / 规则 53 单步子动作密度 / 规则 54 采样率·频带 / 规则 55「其中」代指 的 suspect 已逐条处置（无则写「无」）
  ✅ 规则 56 权要「其/该」代指（hard）/ 规则 57 权 1「所述」引用基础（suspect）已核（无违规或无则写「无」）
  ✅ timestamp_guard.py / fingerprint_claims.py --check 守卫 PASS（全文稿/返修）

  【权利要求书 L1】（权要稿）/【发明内容 L6】【具体实施方式 L8】（全文稿）
  ✅ L1-1 权 1 ≤600 字
  ✅ L1-1 从权依附关系两轨平权（2 级质量项；轨 A 逐句对应型全拉平与轨 B 分支＋局部链条型均合格，多元化门槛仅轨 B 适用，见 `claims-requirements.md` L1-1）
  ✅ L6-1 发明内容逐条权要覆盖
  ➖ L6-2 系统从权效果对应（本案无系统从权）
  …（本块每条 1 级 / 2 级规则逐条列出）

  【全局与短块 G3-G6 / L2-L5 / L7】
  ✅ G4 全文术语一致
  …

  【DOCX 验收】
  ✅ run_gates.py 总跑表已贴入（全部门闸列全，含"未执行"项及原因，无静默缺项——**只写"已跑"不给表 = 未检查**）
  ✅ docx 通用验证无错误
  ✅ verify_docx_injection.py 注入机械项 PASS（块/行内 oMath 数、$ 残留、章节标题加粗顶格、模板句逐字、图1 留位与「图1」图题——现行流程成品图由用户 Visio 自绘后插入，传 `--user-figures`，drawing=0 属预期）
  ✅ verify_docx_skeleton.py 分节2/分节5 图位与图题（同上，`--user-figures` 下两项为 WARN「位置已留，待用户插入」）
  ✅ omml_formulas.py check 公式健康 PASS（无空壳/无 m:d/无编号残留/无幽灵字体，必要时已 fix-settings）
  ✅ verify_docx_skeleton.py PASS（sectPr=5 / header=13 / headerReference 完整 / 可见页眉符合稿次 / 分节落位 / 标题段格式 / 权要段行距 / 发明名称=给定名称；--invention-name 已传，无「未执行」WARN）
  ✅ check_preset_params.py 预设量八槽 PASS（exit=0；FAIL 项须逐条给"已改"或"判为误报+理由"）
  ✅ check_page_count.py 页数 PASS（N 页 ≤30；报 STALE 须注明"已用 Word 另存后重跑"，不得留 STALE 交付）
  ✅ 模板骨架（sectPr / header / headerReference 完整）
  ✅ 页眉与正文可见性符合当前稿次（G8-0 / G8-1）
  ✅ md 基准已快照到 docs/history/（权要1稿.md / 全文1稿.md）
  ✅ 审稿人视角复核疑点清单已落盘 docs/审稿人视角复核-<稿次>.md（与 docs/审查报告-<稿次>.md 分开存放）

  【提请老板确认清单】（返修稿与全文稿交付必附；无项时写「无」）
  ⚠️ 〔位置：块/权要条/段〕｜〔涉及规则编号〕｜〔冲突或违反内容摘录〕｜〔已采取的处置〕

  【待补清单】（新稿交付必附；无留空项时写「无」）
  ➖ 案件号：（未提供时文件名写了 `待补`，用户改名时补全）
  ➖ 正式发明题名全称：（未提供时用权1保护主题占位；补全后可重跑 check_hard_rules --invention-name 核验）
  ➖ 作者署名：（未提供时文件名写了 `待补`，用户改名时补全）
  ```

  多轮回修的案子以**最终通过轮**的结论为准；auditor 增量复核中"沿用上轮"的项照常打 ✅ 并可标注"(沿用)"。返修交付时清单换为返修校验项（署名正确、老板批注条数不减、老板 delText 字数不变、修订数符合预期、docx validate 无新增错误、**返修清单销项表 N/N 全核销**、**镜像块同步检查**（摘要/发明内容对应段/S 复述句/附图说明/"综上所述"段）、**注入后通读与反向保全 diff 已执行**、**md 基准已同步并快照**（`全文稿.md`/`权要稿.md` 与交付稿接受修订后干净正文一致，且 `docs/history/全文N稿.md`（权要案 `权要N稿.md`）已生成））。
- 修订模式下的交付类型：留痕稿/干净稿；若为干净稿，说明是否已清除批注；若为留痕稿，说明老板批注与修订已保留
- 是否有未解决的需要用户澄清的事项
- **提请老板确认清单**（返修稿与全文稿交付必附；无项写「无」）：把"已按批注/亲笔执行、但与规则或可实施性存在冲突"以及"发现了但按规矩不擅改"的项集中列出，使冲突可见而不是被静默吞掉（对外可见通道，判据唯一出处 `rules.md`「冲突处理」决策树）。**四类**来源必须都过一遍：①**批注与 1 级硬规则或可实施性冲突**——默认执行批注，同时列此清单；②**冻结块只读体检**发现的违反项（`implementation.md`「阶段映射与权要冻结」节）——不擅改冻结块，逐项列出；③**审核人亲笔重写的文本与硬规则字面冲突**（`revision.md` A4-1-核心）——一字不改保留，列出；④**第五路 `reviewer-sim` 提出但本轮未采纳的疑点**——本路无否决权，未采纳不阻断交付，但须逐条列出「疑点 + 依据 + 未采纳理由」，使判断可见而非被静默吞掉（疑点全文在 `docs/审稿人视角复核-<稿次>.md`，本清单只列未采纳项）。每项写全四段：位置（块/权要条/段）+ 涉及规则编号 + 冲突或违反内容摘录 + 已采取的处置（执行批注／保留亲笔／未改冻结块）。**任何一类有项而清单未列 = 未完成交付。**
- **待补清单**（新稿交付必附）：开工时缺失的元数据/可补项，按本稿实际留空情况逐项列出，供用户收稿后补齐或改名。典型项：
  - 案件号（文件名前缀，缺则写了 `待补`，用户改名时补全）
  - 正式发明题名全称（`check_hard_rules.py --invention-name` 缺则该题名槽位校验未执行/报 suspect；正式题名须案件元数据确认，未确认前用权 1 保护主题占位，用户确认后可补跑该脚本核验）
  - 作者署名（文件名作者位，缺则写了 `待补`，用户改名时补全；返修留痕稿的 track changes 作者名另行获取，不在此清单）

默认不输出冗长的撰写检查报告；校验清单逐规则只列"emoji + 规则编号 + 一句话"结论行，不展开证据（证据已在 `docs/审查报告-*.md` 落盘）。

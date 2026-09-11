# DOCX 处理注意事项与脚本清单

> 本文件是 `SKILL.md`「DOCX 处理注意事项」节的**外置**，内容一字未改，只是移出必读层。
> **触发式加载**：涉及 DOCX 读写/注入/校验，或需要查脚本用法时读取。各闸门在流程中的**调用时点**仍在 `SKILL.md` 各阶段 step 内（未下移），本文件只放脚本的参数与语义说明。

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

- `scripts/disclosure_docx_to_md.py --input <案件文件夹>/docs/交底书.docx --output <案件文件夹>/docs/交底书.md`（**损坏部件容错**：交底书含无扩展名/零字节的 docProps 部件时自动剥离其在 [Content_Types]/rels 的登记后重试，原文件只读——H2609029 交底书实测 python-docx 直接崩溃）
- `scripts/render_patent_figure.py --claims-md <权要稿.md> --output <案件文件夹>/docs/figures/figure-1.png`：从权要 1 分号分句自动生成图 1（摘要附图 = 方法主流程图）PNG；节点文字逐字一致由构造保证，规则见 `figures.md` L9。
- `scripts/insert_figures_docx.py <unpack目录> --png <figure-1.png>`：把图 1 注入分节 2（摘要附图）与分节 5（说明书附图 + "图1"图题），自动注册 media/relationship/Content-Type；两处已有图片时为替换语义。
- `scripts/rules_budget.py [--save|--check]`：**规则读取量预算表**——按 `rules.md` 阶段读取表统计各阶段要读的规则字符数，`--save` 存基线、`--check` 超基线 10% 提示（防规则无声膨胀；维护工具，非撰写流程脚本）。
- `scripts/boilerplate.py render --method-name <方法名> --system-name <系统名> [--no-medium]` / `boilerplate.py check --md <全文稿.md> --claims-md <权要稿.md>`：**模板句（套话）唯一副本**——13 句（发明内容第一/二/三方面、有益效果引入、附图说明图1、具体实施方式开篇段、集中罗列入口句、综上所述骨架、第二实施例、方法—系统对应、存储介质(可选，默认不写)、示意性说明、结束语）。`render` 把本案名称填进全部模板句供落笔整句粘贴；`check` 逐字校验（含名称槽位一致、收尾顺序），同一逻辑被 `check_hard_rules.py` 规则 47（md 层）与 `verify_docx_injection.py`（DOCX 层）调用。规则文件只放指针不摘引原文（W08 口径）。
- `scripts/docx_assets.py list|extract|restore <file.docx>`：交付 DOCX 里**用户手工资产**（Visio/EMF `<w:object>`、手贴图片）的查看/抠出/回注。用途：**重建类操作前先备份**——重建链路只含 md 基准 + 脚本占位 PNG，用户贴的图不在基准里，重建即丢（H2609029 连环重建 3 次、用户重贴 3 次）；正常返修一律走段级手术不重建。
- `scripts/inject_fulltext_docx.py <unpack目录> [--md <全文稿.md>] [--block 章节] [--claims-md <权要稿.md> --invention-name <名称>]`：全文稿 md → 模板 DOCX 就地注入摘要+发明内容+附图说明+具体实施方式四章（L4+L6+L7+L8），默认一次性注完，可选 `--block` 分块调试。就地下笔不清空 body、不删 sectPr/header/headerReference；按 md 单换行切段（子步骤各自成段，根治挤段），块公式与行内 `$...$` 编译为原生 OMML（G8-3）；pandoc 缺失回退纯文本（G6-1）。摘要替换分节1占位段，L6–L8 追加到分节4末 sectPr 前并删模板 `......` 占位套话段。**权要三章同样由本脚本注入、不手填**（2026-09-10 起，H2609029 审核v1 格式乱套的根治）：加 `--claims-md <权要稿.md> --invention-name "<王工给定名称原样>"`，权要 1..N 注分节3、发明名称+技术领域+背景技术注分节4 开头，三种段 XML 内置王工定稿标准段（正文段只有 1.5 倍行距 + eastAsia hint，标题段加粗顶格，发明名称段居中加粗三号顶格）；只传 `--claims-md` 不传 `--md` = 权要一稿模式（另清掉分节4 模板占位套话，分节1/2/5 不动）；分节3/4 已有同类内容时拒绝重复注入。分离式全文一稿的前向拷贝稿已带三章，**勿传 `--claims-md`**。
- `scripts/verify_docx_injection.py <file.docx> --md <全文稿.md> [--fallback]`：注入后机械校验（zipfile 直读磁盘 docx）——块/行内 oMath 数对账 md、sectPr=5、无 `$`/裸 LaTeX 残留、章节标题加粗顶格、**13 句模板句逐字**（`boilerplate.py`）、图1 drawing≥2。任一不符 exit=1。`--fallback` 用于 pandoc 缺失回退模式（放宽公式数断言为仅查无 `$` 残留）。
- `scripts/check_hard_rules.py --md <md 草稿> --stage claims-draft|full-draft [--claims-md <权要稿.md>] [--invention-name "<正式题名全称>"] [--draft-round 1|2|3|4] --json`：第一类硬规则机械检查（字数、断行、编号、禁用措辞等；full-draft 传 `--claims-md` 以豁免权要原文复述中的量词、并作为 L8-1 稿次字数区间的合并统计输入；**full-draft 必传 `--invention-name`**——本案正式发明题名全称含"及系统／及装置"后缀，供 G8-0b A 类槽位逐字校验，不传则该项静默不执行、只回一条配置缺失 suspect；**full-draft 必传 `--draft-round`**——本轮产出第几稿就传几，供 L8-1 稿次字数区间校验（1稿 15000–17000 双向区间、2/3/4稿 ≤20000，Word「字数」口径、`全文稿.md`＋`权要稿.md` 合并计），不传则该项记为未执行、回 `S-L8-1-draft-round-missing` suspect），闸门用法见权要一稿 step 7 / 全文一稿 step 8 / 返修 step 4。
- `scripts/extract_structure.py --md <md 草稿> --stage claims-draft|full-draft`：按标准写法（基准案 H2606029／H2605066；此处 A/B 指两份标杆案例，**与已废止的 L8「B 范式」无关**）抽取结构 JSON（权要分句、Sx 主步骤、子步骤、附图清单、依附关系），写法不规范时报错停。
- `scripts/check_cross_block.py --md <md 草稿> --stage claims-draft|full-draft [--claims-md <权要稿.md>]`：第二类跨块校验（内部自动跑结构抽取）——L8-0 步骤数同构、主步骤编号连续、依附合法、禁止合并展开，输出作为 `structure_check_result` 传给各路 auditor（多路审查契约见 `agents/*-auditor.md`）。full-draft 阶段必须用 `--claims-md` 传入权要基准（全文稿.md 不含冻结的权利要求书）。
- `scripts/verify_claims_alignment.py --md <全文稿.md> --claims-md <权要稿.md> --stage full-draft`：反向特征差集（L8-0，框架句实体名词 − 权要，suspect）+ 权要内撞名（`claims-requirements.md` L1-1，suspect）+ 步骤集差集（L8-1，权要分句产物名在三节缺失=hard FAIL）。`hard` 与 auditor 冲突以脚本为准；`suspect` 回传各路 auditor 复核。exit=hard 违规数。。（**A5 第三层联动**：加 `--prev-claims docs/history/权要N-1稿.md --prev-md docs/history/全文N-1稿.md` 时，权 1 有改动而摘要/「综上所述」串述段与上轮逐字一致即出 suspect；缺参跳过该项）
- `scripts/fingerprint_claims.py --gen|--check --fulltext <全文稿.md> --claims <权要稿.md>`：权要基准指纹（ADR-0005）。`--gen` 按当前权要写入全文稿.md 头 front-matter（基准权要/sha1/提取时间/分句数）；`--check` 重算权要 sha1 与之比对，不一致 exit=3 硬停，提示走 L8-0 diff→同步流程。
- `scripts/timestamp_guard.py --case <案件文件夹>`：版本时序守卫（ADR-0005）。全文稿.md 早于任一 `审核*.docx` → exit=3，要求先跑 fingerprint --check 确认权要是否变更，防"用旧说明书交付新权要"。
- `scripts/check_page_count.py <交付.docx> [--md <全文稿.md>] [--claims-md <权要稿.md>] [--max 30] [--json]`：**篇幅页数闸门**（`global.md`／`implementation.md` 篇幅硬线：说明书+附图 ≤30 页）。读 DOCX `docProps/app.xml` 的 `<Pages>`；>30 → exit=1。⚠️ **`<Pages>` 由 Word/WPS 最后一次保存时写入**，纯脚本注入而未经 Word 打开另存的 DOCX 该字段停留在模板旧值 → 本脚本对"可疑陈旧"的值报 **STALE（exit=2）而非 PASS**，要求用 Word/WPS 另存后重跑（传 `--md` 才启用陈旧检测：按 CJK 字数估算页数，实测值 <估算 60% 即 STALE）。⚠️ 同一 `app.xml` 的 `<Words>` 字段**不可用**（实测 21531 字的稿子写 4260），字数一律走 `check_hard_rules.py` 规则 41。
- `scripts/check_preset_params.py <全文稿.md> [--window 400] [--json]`：**说明书预设量八槽点数闸门**（`implementation.md` L8-1 阈值确定方式 + `experience/lxl.md` 第 2 节八槽模板的机械实现）。五槽判定：槽1 依据／槽2 操作／槽3 定义（条件）为 FAIL；槽4 取值**按类别分级**（模型超参与量化尺度类 FAIL、阈值/对照关系类 WARN）；槽5 可调整为 WARN。模型/网络类跳过（走模型九项）。`※` 标记 = 裸量词补充路径识别，其缺槽只计 WARN（该路径未经双向验证）。⚠️ **建表 ≠ 过闸门**：交付前必须真跑并把 exit code 与 FAIL 明细贴进完工报告；回归基准见 `tests/regression/regress_preset_params.py`。
- `scripts/verify_rule_anchors.py [--json]`：契约 sed 锚点守卫——校验四份 auditor 契约中 `sed -n` 定向提取的起止锚点在规则文件标题中可命中、无歧义且区间非空（每案件首次编排 auditor 前跑一次；改规则文件节标题或契约锚点后必跑）。exit=失败锚点数。
- `scripts/verify_scoring_excerpts.py [--json]`：scoring 摘录一致性守卫——校验四份 `scoring-*.md` 与 `scoring.md` 的规则编号分派一致（单路标注行编号必进对应摘录、摘录不得私增编号、前置纪律句逐字在场）。改 `scoring.md` 或任一摘录后必跑。exit=失败检查数。

历史脚本：

- `docs/archive/inject_md_to_template.deprecated.py` 是旧版清空 body 重建脚本，仅作历史备查，不得用于权要一稿/全文一稿模板写入。就地替换版通用注入已由 `scripts/inject_fulltext_docx.py` 实现（保留 `sectPr`/`header*.xml`/`headerReference`，按章节落位、不清空 body）。

补充 Python 片段的使用边界（仅辅助检查、不替代 `docx` 执行层）唯一出处是 `references/rules/docx-template.md`「DOCX 执行层边界」。

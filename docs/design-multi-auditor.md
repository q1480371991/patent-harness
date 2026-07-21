# 多路审查(multi-auditor)设计 — 按重灾区拆分 rule-auditor

> **沿革注记（2026-07）**：本文档为设计稿；运行口径以 `SKILL.md`「审查闸门通用规则」与 `agents/*-auditor.md` 契约为准。scoring 已改为静态摘录文件按路径传入、所有 FAIL 路重审均走增量复核。

日期:2026-07-08。本设计取代单一 `rule-auditor` 的审查架构,是 `docs/design-subagent-split.md` 的后续演进。

---

## 1. 动机

单 `rule-auditor` 一次要装下全部规则(全文一稿 ≈30k tokens 规则 + 全文稿本体,单次 ~37k tokens),长清单逐项判定时注意力被稀释——这是"自评说 PASS、写入 DOCX 后仍有硬规则违反"的一类根因。

`design-subagent-split.md` §1.1 否定过"每章节一个 agent",但那是针对**写作类** subagent(边写边回查权要的联动会丢失)。**审查是无状态只读任务、输入输出契约固定**,那些反对理由不适用;规则文件本身天然按内容块组织(L1/L6/L8/…),拆分边界现成。

## 2. 架构:4 个契约,按阶段路由 2-3 路

```
                    权要一稿(claims-draft)               全文一稿(full-draft)
脚本闸门(不变) ──▶ check_hard_rules + check_cross_block ──▶ 同左(加 --claims-md)
                            │                                      │
并行 subagent ──▶ ┌─ claims-auditor(L1 专审)            ┌─ content-auditor(L6 专审)
                  └─ global-auditor(全局+L2/L3)         ├─ impl-auditor(L8 专审)
                                                        └─ global-auditor(全局+L4/L5/L7)
                            │                                      │
主 agent 汇总仲裁 ──▶ 合并报告落盘 docs/审查报告-*.md ──▶ 通过才进 DOCX
```

**关键决策**:

- **claims-auditor 只在权要阶段跑,全文阶段不跑**——全文阶段权要已冻结(`full-draft.md` 权要冻结条),`全文稿.md` 不含权利要求书;全文阶段再审权要等于重复权要阶段已过的闸,还可能诱导改冻结权要。权要稿在全文阶段的角色是**只读基准**,传给 content / impl 两路做跨块比对。
- **审核重灾区各设专审**:权利要求书(L1)、发明内容(L6)、具体实施方式(L8);短块(L2/L3/L4/L5/L7)与全局项(G1-G7)、完整性一票否决集中到 global-auditor。
- **附图退出审查**:用户自行生图画图。`figures.md` 不进任何规则包;原 rule-auditor 语义必审清单中"权要 1 vs 图 1 节点""附图说明 vs 附图设计图数"两项删除;完整性清单中"附图设计节(L9)"降级为存在性检查;`scoring.md` 中"L7-1 与 L9 一致"降级为 L7 自身格式检查。
- **返修阶段(claims-revision / full-revision)按改动块定向调 auditor(2026-07 修订)**:早期决策为"返修不调 auditor,沿用现有边界不扩大",经 X2607008 全文三稿复盘证伪——返修改动量大、且会引入一稿审查未见过的新文本(如新写的 AI 自辩句、跨技术体系术语),裸奔无语义兜底,一次暴露 19 条批注。现改为:返修对重灾区块(L1/L6/L8)做补写/改写/扩写时,以增量复核模式(`reaudit_context`=本轮批注+改动块清单)定向调用改动块对应的 auditor 路,合并落盘 `docs/审查报告-<稿次>.md`,未过闸不注入;纯格式/纯删除/纯编号迁移仍只走两道脚本闸门。执行细则唯一出处 `SKILL.md` 返修工作流。

## 3. 跨块语义项归属

原 rule-auditor 语义必审清单的跨块项,分配给"被审部分"的专审路,权要稿作为公共只读基准传入:

| 跨块语义项 | 归属 |
|---|---|
| 发明内容语义覆盖每条权要(L6-1,完整性级) | content-auditor |
| 反向特征校验:说明书有而权要无的特征(L8-0,完整性级) | impl-auditor |
| Sxx 框架句与权 1 分句逐字比对(L8-0 文字层;数量/编号由脚本 X1/X2 判) | impl-auditor |
| 从权多元化依附(L1-1) | claims-auditor |
| 全文术语一致(G4,以权要术语为基准) | global-auditor |
| 权要 1 vs 附图 1、附图说明 vs 附图设计(figures.md) | 删除(附图不审) |

## 4. 契约共性(每个 `agents/*-auditor.md` 三段式)

- **输入**:`stage` + 稿件 `md_path`(传全文路径不切片——切片省的 token 不值切错的风险,契约限定"只审 X 章节") + 两脚本完整 JSON(契约限定只沿用本范围条目) + `scoring_excerpt_path`(本路静态摘录 `scoring-<路名>.md`,规则一律传路径不传内容) + 本路规则包 + `triggered_rule_notes`;full-draft 专审另传 `claims_md_path` 冻结基准。
- **输出**:统一结构——范围声明 → 完整性(仅 global)→ 1 级硬规则 N/M → 2 级质量分 N/M → 最短回修清单;每个 FAIL 带规则编号+位置+原文证据+应改为;无证据的 PASS 视为未检查。
- **失败契约**:重试 1 次,仍失败该路降级为主 agent 自查并在完工报告标注"<路名> 未生效";脚本闸门不受影响必须过。
- **白名单**:只读(`Read` 仅限传入路径,`Bash` 仅限 wc/grep/awk/sed -n/head/tail/diff),禁止写文件/DOCX/联网/越权读规则。

## 5. 汇总仲裁与回修收敛(主 agent,编排层)

- **通过判定**:global 完整性 PASS **且** 各路 1 级全部 100% **且** 合并 2 级分 = Σ各路通过 ÷ Σ各路适用 ≥ 90%(口径见 `scoring.md` 计分方法)。
- **合并落盘**:一份 `docs/审查报告-<稿次>.md`,合并结论在前、各路原始报告附后;同位置同规则去重,跨路冲突按 `rules.md` 冲突处理原则裁决。保持"无落盘报告 = 未过闸"。
- **回修后重审**:必重跑两脚本;重调**上轮有 FAIL 的专审路**;**FAIL 路(含 global-auditor 与专审路)以 `reaudit_context` 增量复核模式重调**(完整性级/恒复核项仍全量,其余沿用上轮);上轮全 PASS 的专审路不重调。

## 6. Token 成本(诚实账)

权要阶段 ~26k→~34k(+30%);全文阶段 ~37k→~62k(+68%)。换来:每路规则密度从 ~30k 降到 3-12k(注意力集中),并行 wall-clock 更短,每路输出契约更短更稳。

## 7. 宿主适配

- **Claude(claude 分支 SKILL.md)**:单消息并行调起本阶段全部 auditor(独立 Agent,物理隔离)。
- **Codex(codex 分支 SKILL.md)**:无原生 subagent,按同一组契约**分轮自查**——每轮只带一路规则包,获得同等注意力集中收益;仍无独立性,完工报告标注,硬防线以脚本闸门为准。

## 8. 分支纪律变更(随本设计一并生效)

`subagent` 分支退役删除(内容与 claude 分支完全重复)。core 开发直接在 **claude 分支**(权威)进行,codex 分支接收 merge(SKILL.md 冲突以 codex 版本为准)。详见 `docs/porting.md` §2。

## 9. 落地清单

- 新增 `agents/{global,claims,content,impl}-auditor.md`;`agents/rule-auditor.md` → `docs/archive/rule-auditor.deprecated.md`。
- `references/rules/scoring.md`:评分项归属标注、附图项降级、多路合并口径、多路合并落盘。
- `docs/porting.md`:分支结构、编排差异表、诚实边界更新。
- claude 分支 `SKILL.md`:权要一稿阶段 B → 2 路并行;全文一稿 → 3 路并行;汇总仲裁与降级措辞。
- codex 分支 `SKILL.md`:规则外审行 → 按 4 契约分轮自查。
- 验证:`tests/test_scripts_smoke.py` 全绿(脚本零改动);以 H2605066 定稿全文稿实测 3 路并行,按"定稿为最优"反推校准审查器(FAIL 项优先怀疑误报)。

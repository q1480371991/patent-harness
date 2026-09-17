# -*- coding: utf-8 -*-
"""独立复核·第 3 组：补规则条文出处、豁免出处、跨路归属、清单补登、称谓与检索铁律。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(rel, pairs=(), prefix_inserts=()):
    p = ROOT / rel
    t = p.read_text(encoding="utf-8")
    for old, new in pairs:
        n = t.count(old)
        assert n >= 1, (rel, old[:60], n)
        t = t.replace(old, new)
    for prefix, ins in prefix_inserts:
        idx = t.index(prefix)
        t = t[:idx] + ins + t[idx:]
    assert "�" not in t, rel
    p.write_text(t, encoding="utf-8", newline="")
    print("patched", rel)


# ---- ① claims-requirements L1-1：补规则 56/57 的条文（此前只有脚本、无规则文本） ----
patch("references/rules/claims-requirements.md", prefix_inserts=[("### L1-2 2级规则（质量优化）", (
 "- **★ 权要内不得用「其／该」代指（1级；王工《专利撰写AI自查流程指引》第 5 步「指示代词是硬红线」，2026-09-11 吸收）**："
 "执行步骤里出现「其、该」指代（「其特征在于」「其中」等惯用式除外）一律改为「所述＋术语」或重复术语全称。"
 "机械终判 `check_hard_rules.py` **规则 56**（hard；七案定稿实测零误报）。\n"
 "- **★ 权 1 的「所述X」须有引用基础（2级；同上出处）**：权 1 特征部分的每个「所述X」，X 须在前文以非「所述」形态"
 "出现过；确为首次引入的应去掉「所述」；前文出现过而此处漏「所述」的要补上。机械线索 `check_hard_rules.py` **规则 57**"
 "（suspect `S-L1-referent-basis`，owner=claims；限权 1、七案零误报——扩到全条权会因系统权写全名与套话固定搭配误报，故不做）。"
 "与 `global.md` G4-1「'所述'前序引用规则」同源，本条为**权要侧执行口径**。\n"
))])

# ---- ② global.md G4-1：补规则 55 的条文（脚本 owner=G4-1，此前真源查不到） ----
patch("references/rules/global.md", [
 ("- “所述”前序引用规则：特征第一次引入时不加“所述”；第二次及之后引用该特征必须加“所述”。检查每个被引用对象都存在、命名一致；“所述 XXX”必须在前文有引入基础。",
  "- “所述”前序引用规则：特征第一次引入时不加“所述”；第二次及之后引用该特征必须加“所述”。检查每个被引用对象都存在、命名一致；“所述 XXX”必须在前文有引入基础。"
  "**权要侧的执行口径见 `claims-requirements.md` L1-1「权 1 的『所述X』须有引用基础」条**（机械线索规则 57）。\n"
  "- **★ 不用「其中」代指对象（1级；王工《专利撰写AI自查流程指引》第 5 步，2026-09-11 吸收）**："
  "**段首引导词「其中，」合法**（`implementation.md` L8-1 引导词表）；但**句中「通过／将／对／在／由／从／把＋其中」代指"
  "已出现的对象**属回指不显式，须写「所述〔对象〕中」。机械线索 `check_hard_rules.py` **规则 55**（suspect `S-G4-qizhong`，owner=global）。"),
])

# ---- ③ 6 路契约：豁免项出处补 implementation.md 的可调性条 ----
for rel in ("agents/claims-auditor.md", "agents/global-auditor.md", "agents/content-auditor.md",
            "agents/impl-auditor.md", "agents/reviewer-sim-claims.md", "agents/reviewer-sim-spec.md"):
    patch(rel, [("唯一出处 `claims-requirements.md` L1-1「自查／审计的豁免项」条与 `global.md` G6-1 公式必要性条）",
                "唯一出处 `claims-requirements.md` L1-1「自查／审计的豁免项」条、`global.md` G6-1 公式必要性条"
                "与 `implementation.md` L8-1「阈值可调性说明是合格写法」条）")])

# ---- ④ 四层回收链的跨路归属说明 ----
patch("agents/global-auditor.md", [
 ("- **四层回收链完整性**（`claims-field-background.md` L3-1 四层回收链条）：核背景技术每个缺陷句是否被"
  "「问题总结 → 发明目的 → 有益效果（1）」逐层回收；断链的缺陷句须删或确认为纯背景性描述。",
  "- **四层回收链完整性**（`claims-field-background.md` L3-1 四层回收链条）：核背景技术每个缺陷句是否被"
  "「问题总结 → 发明目的 → 有益效果（1）」逐层回收；断链的缺陷句须删或确认为纯背景性描述。"
  "⚠️ **本项是「不在本路范围」的唯一例外**：L6 属 content-auditor，但本核项须读 L6 的**技术目的句与有益效果第（1）项**"
  "两处（只读这两句、不做 L6 块内深审）；核完把结论写进本路报告，与 content-auditor 的对应结论交叉即可。"),
])

patch("agents/content-auditor.md", [
 ("- **第三层联动语义核（权要→说明书三层清单的第三层，无历史快照时的唯一防线）**：",
  "- **四层回收链（L6 侧）**：核「发明目的句」与「有益效果第（1）项」是否分别回收了背景技术末尾的问题总结"
  "（完整链条的权威出处与机械处置口径见 `claims-field-background.md` L3-1；背景侧由 global-auditor 核，本路核 L6 侧）。\n"
  "- **第三层联动语义核（权要→说明书三层清单的第三层，无历史快照时的唯一防线）**："),
])

# ---- ⑤ SKILL 完工报告清单：补规则 52 / 55 ----
patch("SKILL.md", [
 ("  ✅ 规则 53 单步子动作密度 / 规则 54 采样率·频带 的 suspect 已逐条处置（无则写「无」）",
  "  ✅ 规则 52 有益效果字数 / 规则 53 单步子动作密度 / 规则 54 采样率·频带 / 规则 55「其中」代指 "
  "的 suspect 已逐条处置（无则写「无」）"),
])

# ---- ⑥ 第五路契约：称谓与检索铁律 ----
patch("agents/reviewer-sim-claims.md", [
 ("| 调用时点 | 机械脚本 PASS 后 | **四路 auditor 全部 PASS 之后** |",
  "| 调用时点 | 机械脚本 PASS 后 | **本闸门的各路 auditor 全部 PASS 之后** |"),
 ("| `gate_result` | 一句话说明「四路 auditor 与机械脚本已全部 PASS」+ 通过轮次。",
  "| `gate_result` | 一句话说明「本闸门各路 auditor 与机械脚本已全部 PASS」+ 通过轮次。"),
 ("- 前置闸门：四路 auditor 与机械脚本已全部 PASS（轮次：…）",
  "- 前置闸门：本闸门各路 auditor 与机械脚本已全部 PASS（轮次：…）"),
])

for rel in ("agents/reviewer-sim-claims.md", "agents/reviewer-sim-spec.md"):
    patch(rel, [("**禁止把交底书原文贴进查询**（第三方端点会缓存与索引）",
                 "**禁止把交底书原文贴进查询**（第三方端点会缓存与索引）。"
                 "**检索真实性铁律（1级；`SKILL.md` 检索条，2026-09-11）**：①禁止编造专利号与专利字段——"
                 "只引用真实检索返回，查不全写「未检索到」；②检索为空时换同义词重试，仍为空则如实写明"
                 "「本次未检索到同类专利」，**不得靠编数据凑结论**；③专利数据与行业/网页数据来源分离、分别标注。")])
print("第 3 组完成")

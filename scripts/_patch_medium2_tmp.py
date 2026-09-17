# -*- coding: utf-8 -*-
"""同步调用点 + 规则文本：王工 2026-09-11 新权要配比（方法 9 + 系统 10，不写介质权、无第三方面）。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(rel, pairs=(), regex_pairs=()):
    p = ROOT / rel
    t = p.read_text(encoding="utf-8")
    for old, new in pairs:
        assert t.count(old) == 1, (rel, old[:55], t.count(old))
        t = t.replace(old, new)
    for pat, new in regex_pairs:
        m = re.search(pat, t, re.S)
        assert m, (rel, pat[:50])
        t = t[:m.start()] + new + t[m.end():]
    assert "�" not in t, rel
    p.write_text(t, encoding="utf-8", newline="")
    print("patched", rel)


# ---- ① 调用点 ----
patch("scripts/check_hard_rules.py", [
 ("    has_system, has_medium = boilerplate.detect_subjects(claims_src)\n"
  "    for v in boilerplate.check_paragraphs(paras, has_system, has_medium, secs):",
  "    has_system, _has_medium = boilerplate.detect_subjects(claims_src)  # 介质权已禁写，仅用于兜底提示\n"
  "    for v in boilerplate.check_paragraphs(paras, has_system, secs):"),
])

patch("scripts/verify_docx_injection.py", [
 ("    has_system, has_medium = boilerplate.detect_subjects(\"\\n\".join(paras))\n"
  "    vio = boilerplate.check_paragraphs(paras, has_system, has_medium, secs)\n"
  "    results.append((f\"模板句逐字（系统权={has_system} 介质权={has_medium}）\", not vio,",
  "    has_system, _has_medium = boilerplate.detect_subjects(\"\\n\".join(paras))\n"
  "    vio = boilerplate.check_paragraphs(paras, has_system, secs)\n"
  "    results.append((f\"模板句逐字（系统权={has_system}）\", not vio,"),
])

# ---- ② claims-requirements.md ----
patch("references/rules/claims-requirements.md", [
 ("当方法权数量与系统/装置权、存储介质权相加不等于 10 条时，通过拆分/合并方法从权调整条数凑满 10 条"
  "（拆分时每条须有实质技术内容、不得灌水；不得通过删除计算机可读存储介质权减条）。",
  "当方法权数量与系统/装置权相加不等于 10 条时，通过拆分/合并方法从权调整条数凑满 10 条"
  "（拆分时每条须有实质技术内容、不得灌水）。**介质权自 2026-09-11 起不再撰写**（见下条），"
  "方法权不足时用方法从权补足、不得回头写介质权凑数。"),
 ("- 当题目同时包含方法和系统/装置时，通常采用“方法独权 + 方法从权 + 系统/装置独权及其从权”的结构；方法权通常写到权要 8，系统/装置权及存储介质权占末尾 2 条（权9 系统、权10 存储介质），合计 10 条。",
  "- **★ 权要配比：方法权写满权 9、系统/装置权为权 10，不写存储介质权（1级；王工 2026-09-11 定）**："
  "原话「把方法写满九条，最后一个写系统，介质权10不要写了」「写满九条是很轻松的；就不用介质来凑数了」。"
  "即「方法独权 + 方法从权（合计写到权 9）+ 系统/装置独权（权 10）」= **共 10 条**；方法权不够 9 条时"
  "用方法从权补足（不得靠介质权凑数、不得写介质权）。"),
 ("- 系统/装置独权默认采用计算机设备式写法，并单列一条计算机可读存储介质权（**两条整条都是模板句**：",
  "- 系统/装置独权默认采用计算机设备式写法（**整条是模板句**："),
 ("N = 系统权编号 − 1；句末「所述处理器执行所述计算机程序时」与「所述程序时」**两种写法均可**（用户 2026-09-11 确认）。"
  "H2609029 交付稿把「其特征在于」挪到「包括存储器」前、写成「如权利要求1至8中任一项」即偏离）：装置独权写“一种……装置，包括存储器、处理器及存储在所述存储器上并可在所述处理器上运行的计算机程序，其特征在于，所述处理器执行所述计算机程序时实现权利要求 1 至 N 任一项所述的方法。”；存储介质权写“一种计算机可读存储介质，其上存储有计算机程序，其特征在于，所述计算机程序被处理器执行时实现权利要求 1 至 N 任一项所述的方法。”。",
  "N = 系统权编号 − 1 = **9**（系统权固定在权 10）；句末「所述处理器执行所述计算机程序时」与「所述程序时」"
  "**两种写法均可**（用户 2026-09-11 确认）。**存储介质权不再撰写**（王工 2026-09-11；机械校验 "
  "`boilerplate.check_claims` 出现即 FAIL））：装置独权写“一种……装置，包括存储器、处理器及存储在所述存储器上并可在所述处理器上运行的计算机程序，其特征在于，所述处理器执行所述计算机程序时实现权利要求 1 至 9 任一项所述的方法。”。"),
 ("- **权要数量必须写满 10 条**；方法+系统/装置题目时方法权通常写到权要 8、系统/装置权及存储介质权占末尾 2 条（权9 系统、权10 存储介质为常见收尾），合计正好 10 条（“方法权到权7 + 权9 + 权10”只有 9 条，会漏 权8，勿照此配比）。",
  "- **权要数量必须写满 10 条**；方法+系统/装置题目时方法权写到权要 9、系统/装置权占权 10，合计正好 10 条；**不写存储介质权**（王工 2026-09-11）。"),
 ("- 系统/装置独权是否按默认计算机设备式撰写并单列计算机可读存储介质权；若用功能模块式，是否有个案",
  "- 系统/装置独权是否按默认计算机设备式撰写、且**未**撰写存储介质权（权 10 应为系统权）；若用功能模块式，是否有个案"),
])

# ---- ③ invention-content.md：第三方面撤掉 ----
patch("references/rules/invention-content.md", [
 ("- **第三方面存储介质段（1级；有计算机可读存储介质权时必写）**：模板句「第三方面，本发明提供一种计算机可读存储介质，其上存储有计算机程序，所述计算机程序被处理器执行时实现如上所述的方法。」（唯一副本 `boilerplate.py` 键 `aspect3`；「其上存储有」口径）。三个方面句首照模板原句（第一方面「提供了一种」、第二/三方面「提供一种」），**不得为“统一”而互改**。",
  "- **发明内容只写第一方面（方法）与第二方面（系统）两段；第三方面自 2026-09-11 起不再撰写（1级；王工口径「发明内容没有第三方面了」）**。两段句首照模板原句（第一方面「本发明提供**了**一种」、第二方面「本发明提供一种」），**不得为“统一”而互改**；出现「第三方面」段即 FAIL（`boilerplate.check_paragraphs` 禁写项）。"),
])

# ---- ④ implementation.md：收尾条 ④ 与实施例分层 ----
patch("references/rules/implementation.md", regex_pairs=[
 (r"→ ④存储介质段（键 `medium_spec`；\*\*可选段，默认不写\*\*.*?→ ⑤示意性说明段",
  "→ ④~~存储介质段~~（**自 2026-09-11 起不再撰写**——王工「不用介质来凑数了」；出现即 FAIL，"
  "`boilerplate.FORBIDDEN_MEDIUM_PARAS` 为禁写项）→ ⑤示意性说明段"),
])

# ---- ⑤ docx-template.md ----
patch("references/rules/docx-template.md", [
 ('  - 附带：**"另一实施例"专指同一方法的第二种执行方式**；系统、存储介质一律称"第二实施例""第三实施例"。',
  '  - 附带：**"另一实施例"专指同一方法的第二种执行方式**；系统一律称"第二实施例"（**存储介质相关段落自 2026-09-11 起不再撰写**，故不涉及"第三实施例"）。'),
 ("- 仅当符合保护策略和案件类型时，才包含计算机可读存储介质的权要或说明书段落。不要因为模板里有\"计算机可读存储介质\"就强行套到每个案件。",
  "- **计算机可读存储介质的权要与说明书段落自 2026-09-11 起一律不写**（王工口径「介质权10不要写了」「不用介质来凑数了」「发明内容没有第三方面了」）；出现即 FAIL。"),
])

# ---- ⑥ global.md / scoring ----
patch("references/rules/global.md", [
 ("- 起草前宜判断是否存在方法权、系统/装置权、存储介质权的保护空间。",
  "- 起草前宜判断是否存在方法权、系统/装置权的保护空间（存储介质权自 2026-09-11 起不写）。"),
])
for rel in ("references/rules/scoring.md", "references/rules/scoring-global.md"):
    patch(rel, [
     ("- 权要集结构完整：方法独权 + 方法从权 + 系统/装置独权（+ 存储介质权），编号连续无断号（L1-1）。",
      "- 权要集结构完整：方法独权 + 方法从权（合计写到权 9）+ 系统/装置独权（权 10），编号连续无断号（L1-1；存储介质权自 2026-09-11 起不写）。"),
    ])

print("callers + rules done")

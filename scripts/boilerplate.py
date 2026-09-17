#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""boilerplate.py — 模板句（套话）唯一真源：渲染填空 + 逐字校验。

★ 立项根因（H2609029 全文稿，2026-09-09/10 用户连抓 6 处）：「第一方面，为了解决上述技术问题…」
整句漏写、附图说明漏「第一实施例」、装置示意段被删、存储介质段/第二实施例段措辞自由改写、
结束语与王工批注 21 定版不一致——全部是「模板句交给 LLM 自由发挥」的结果。王工 H2608165
审核v2 批注 21 原话「不一致，后续都按模板来」。用户口径：**模板和套话是填空题，只替换案件
变量词，不能乱改、不能乱删、不能乱加；能固定下来的就用脚本固定，不以规则文本交给 LLM**。

本文件是全部模板句的**唯一副本**（规则文件只放指针，不再摘引原文——`implementation.md`
W08 条 2026-09-01 口径：省略号摘引会被照残句抄）。两个用法：

    # 1) 落笔前渲染：把本案名称填进全部模板句，撰写侧整句粘贴、不手写
    python scripts/boilerplate.py render --method-name "<方法名>" --system-name "<系统名>"

    # 1b) 只想看原文口径（不填案子）：
    python scripts/boilerplate.py show [--claims]

    # 2) 校验：md 层（check_hard_rules.py 规则 47 调用）与 DOCX 层（verify_docx_injection.py 调用）
    python scripts/boilerplate.py check --md docs/全文稿.md [--claims-md docs/权要稿.md]

定版来源（逐条）：
  - 第一方面：王工模板原句「第一方面，为了解决上述技术问题，本发明提供了一种AAA方法，包括：」
    （X2607134 定稿、H2609029 3稿同；H2608040/X2608107 定稿曾用短式「第一方面，本发明提供一种…」，
    按「后续都按模板来」统一为模板原句）
  - 第二方面 / 第三方面：`invention-content.md` L6-1 W05 定版（王工 2026-08-28「所述的方法」口径；
    H2608040/X2608107/H2608165 定稿逐字同）
  - 有益效果引入句：L6-1（五案定稿逐字同）
  - 附图说明图1句：四案定稿逐字同「图1为本发明第一实施例提供的〔方法名〕的流程示意图。」
  - 开篇段：母版原文 130 字（五案逐字同，「作出/做出」两种）
  - 集中罗列入口句：`implementation.md` L8-0 王工口径「如图1所示，本发明实施例提供的一种〔方法名〕，包括：」
  - 综上所述段：L8-1 收尾条①骨架（三个槽位自由）
  - 第二实施例段：L8-1 收尾条②，「所述计算机程序」按 H2608165 定稿与权 9/第二方面同源写法
  - 方法—系统对应段：L8-1 收尾条③（五案逐字同）
  - ★ **介质相关三句自 2026-09-11 起不再撰写**（王工口径：「方法权写满九条……就不用介质来凑数了」
    「发明内容没有第三方面了」）：权利要求书存储介质权 / 发明内容第三方面 / 说明书收尾存储介质段，
    原文移入 `FORBIDDEN_MEDIUM_PARAS` 作**禁写项**——出现即 FAIL（见 `check_paragraphs` / `check_claims`）
  - 示意性说明段 / 结束语：`docx-template.md` G8-2 嵌入的王工批注 21 定版原文
  - 权利要求书侧 系统权（权 10）：`claims-requirements.md` L1-1（X2608107/H2608165 定稿逐字同；
    `check_claims`，由 check_hard_rules.py 规则 51 在 claims-draft 阶段调用；`{N}` = 系统权编号 − 1 = 9）
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

# ---------------------------------------------------------------- 模板句定义

_SLOT_RE = {
    "方法名": r"(?P<方法名>[^，。；：]{2,60}?)",
    "系统名": r"(?P<系统名>[^，。；：]{2,60}?)",
    "S": r"(?P<S>系统|装置)",
}
# 自由槽位（内容由案件决定，只校验骨架）
_FREE_SLOT_RE = r".+?"


@dataclass(frozen=True)
class Template:
    key: str
    section: str          # 所在章节（md `## ` 标题 / DOCX 分节4 内章节）
    anchor: str           # 候选段定位串（段落起始或包含）
    text: str             # 模板原文，{方法名}{系统名}{S} 为命名槽位，{…} 为自由槽位
    need: str             # always | system | medium | optional
    label: str            # 报告用名
    anchor_mode: str = "prefix"   # prefix | contains
    variants: tuple[str, ...] = ()  # 允许的逐字变体（整句模板，含 {槽位}；与主正则在 check 内一并尝试）


_OPENING = (
    "下面将结合本发明实施例中的附图，对本发明实施例中的技术方案进行清楚、完整地描述，"
    "显然，所描述的实施例仅仅是本发明一部分实施例，而不是全部的实施例。"
    "基于本发明中的实施例，本领域普通技术人员在没有作出创造性劳动前提下"
    "所获得的所有其他实施例，都属于本发明保护的范围。"
)
_INDICATIVE = (
    "需要说明的是，以上所描述的{S}实施例仅仅是示意性的，其中所述作为分离部件说明的单元"
    "可以是或者也可以不是物理上分开的，作为单元显示的部件可以是或者也可以不是物理单元，"
    "即可以位于一个地方，或者也可以分布到多个网络单元上。可以根据实际需要选择其中的部分"
    "或者全部模块来实现本实施例方案的目的。本领域普通技术人员在不付出创造性劳动的情况下，"
    "即可理解并实施。"
)
_CLOSING = (
    "以上所述的具体实施例，对本发明的目的、技术方案和有益效果进行了进一步的详细说明，"
    "应当理解，以上所述仅为本发明的具体实施例而已，并不用于限定本发明的保护范围。"
    "特别指出，对于本领域技术人员来说，凡在本发明的精神和原则之内，所做的任何修改、"
    "等同替换、改进等，均应包含在本发明的保护范围之内。"
)

# 「所述（计算机）程序」两种写法均可（用户 2026-09-11 确认；五案定稿两种并存）：
# 第二方面段 / 第二实施例段 / 权利要求书系统权 三处按变体白名单放行。
_ALT_PROGRAM = "所述程序"


def _program_alt(text: str) -> tuple[str, ...]:
    """把「所述计算机程序」替换为「所述程序」的整句变体（无该串则返回空元组）。"""
    return (text.replace("所述计算机程序", _ALT_PROGRAM),) if "所述计算机程序" in text else ()

TEMPLATES: tuple[Template, ...] = (
    Template("aspect1", "发明内容", "第一方面",
             "第一方面，为了解决上述技术问题，本发明提供了一种{方法名}，包括：",
             "always", "发明内容·第一方面句"),
    Template("aspect2", "发明内容", "第二方面",
             "第二方面，本发明提供一种{系统名}，包括存储器、处理器及存储在所述存储器上并可在所述处理器上"
             "运行的计算机程序，所述处理器执行所述计算机程序时实现如上所述的方法。",
             "system", "发明内容·第二方面系统段", variants=_program_alt(
                 "第二方面，本发明提供一种{系统名}，包括存储器、处理器及存储在所述存储器上并可在所述处理器上"
                 "运行的计算机程序，所述处理器执行所述计算机程序时实现如上所述的方法。")),
    Template("benefit_intro", "发明内容", "相比于现有技术",
             "相比于现有技术，本发明具有如下有益效果：",
             "always", "发明内容·有益效果引入句"),
    Template("fig1", "附图说明", "图1为",
             "图1为本发明第一实施例提供的{方法名}的流程示意图。",
             "always", "附图说明·图1句"),
    Template("opening", "具体实施方式", "下面将结合", _OPENING, "always", "具体实施方式·开篇段",
             variants=(_OPENING.replace("作出创造性", "做出创造性"),)),
    Template("intro", "具体实施方式", "如图1所示",
             "如图1所示，本发明实施例提供的一种{方法名}，包括：",
             "always", "具体实施方式·集中罗列入口句"),
    Template("summary", "具体实施方式", "综上所述",
             "综上所述，本发明公开了一种{方法名}，{串述}。本发明通过{手段}，实现了{效果}。",
             "always", "具体实施方式·综上所述段"),
    Template("embod2", "具体实施方式", "本发明第二实施例",
             "本发明第二实施例提供了一种{系统名}，包括：存储器、处理器及存储在存储器上并可在处理器上"
             "运行的计算机程序，所述处理器执行所述计算机程序时实现如上述所述的方法。",
             "system", "具体实施方式·第二实施例系统段", variants=_program_alt(
                 "本发明第二实施例提供了一种{系统名}，包括：存储器、处理器及存储在存储器上并可在处理器上"
                 "运行的计算机程序，所述处理器执行所述计算机程序时实现如上述所述的方法。")),
    Template("correspond", "具体实施方式", "因而不再赘述",
             "需要说明的是，本发明实施例提供的一种{系统名}用于执行上述实施例的一种{方法名}的所有流程步骤，"
             "两者的工作原理和有益效果一一对应，因而不再赘述。",
             "system", "具体实施方式·方法—系统对应段", anchor_mode="contains"),
    Template("indicative", "具体实施方式", "仅仅是示意性", _INDICATIVE, "system",
             "具体实施方式·示意性说明段（批注 21 定版）", anchor_mode="contains"),
    Template("closing", "具体实施方式", "以上所述的具体实施例", _CLOSING, "always",
             "具体实施方式·结束语（批注 21 定版）",
             # 王工 2026-09-11 答复「都可以，删改一两个字的不影响，这里不是重点」——简版一并接受
             variants=(
                 "以上所述的具体实施例，对本发明的目的、技术方案和有益效果进行了进一步详细说明，"
                 "所应理解的是，以上所述仅为本发明的具体实施例，并不用于限定本发明的保护范围，"
                 "凡在本发明的精神和原则之内，所作的修改、等同替换、改进等，均应包含在本发明的保护范围之内。",
             )),
)
# 收尾固定顺序（L8-1 收尾条）：综上所述 → 第二实施例 → 方法—系统对应 → [存储介质] → 示意性说明 → 结束语
CLOSING_ORDER = ("summary", "embod2", "correspond", "indicative", "closing")

# ---- 禁写项：介质相关三句（王工 2026-09-11：方法写满九条 + 权10 系统，不再用介质凑数）----
FORBIDDEN_MEDIUM_PARAS: tuple[tuple[str, str], ...] = (
    ("发明内容·第三方面存储介质段（禁写）",
     "第三方面，本发明提供一种计算机可读存储介质，其上存储有计算机程序，"
     "所述计算机程序被处理器执行时实现如上所述的方法。"),
    ("具体实施方式·存储介质段（禁写）",
     "需要说明的是，本发明实施例还提供了一种计算机可读存储介质，其上存储有计算机程序，"
     "所述计算机程序被处理器执行时实现如上述所述的方法。"),
)
MEDIUM_CLAIM_PREFIX = "一种计算机可读存储介质"

# ---- 权利要求书侧模板句（claims-requirements.md L1-1；X2608107 / H2608165 定稿逐字同）----
# 编号头「N.」不入模板；{系统名} 含「系统/装置」后缀；{N} = 末条方法权编号（= 系统权编号 − 1）。
# 王工 2026-08-28 口径：句末「所述的方法」，不写全称、不写「的步骤」。
CLAIM_TEMPLATES: tuple[Template, ...] = (
    Template("claim_system", "权利要求书", "包括存储器、处理器",
             "一种{系统名}，包括存储器、处理器及存储在所述存储器上并可在所述处理器上运行的计算机程序，"
             "其特征在于，所述处理器执行所述计算机程序时实现权利要求1至{N}任一项所述的方法。",
             "system", "权利要求书·系统权（计算机设备式）", anchor_mode="contains",
             variants=_program_alt(
                 "一种{系统名}，包括存储器、处理器及存储在所述存储器上并可在所述处理器上运行的计算机程序，"
                 "其特征在于，所述处理器执行所述计算机程序时实现权利要求1至{N}任一项所述的方法。")),
)
_SLOT_RE["N"] = r"(?P<N>\d{1,2})"

_SLOT_TOKEN_RE = re.compile(r"\{([^{}]+)\}")


def template_regex(t: Template) -> re.Pattern:
    """模板原文 → 逐字正则（命名槽位按名称正则、自由槽位 .+?、其余逐字转义）。"""
    out, pos = [], 0
    for m in _SLOT_TOKEN_RE.finditer(t.text):
        out.append(re.escape(t.text[pos:m.start()]))
        name = m.group(1)
        out.append(_SLOT_RE.get(name, _FREE_SLOT_RE))
        pos = m.end()
    out.append(re.escape(t.text[pos:]))
    return re.compile("^" + "".join(out) + "$", re.S)


def render(method_name: str, system_name: str | None,
           indicative_subject: str = "系统") -> list[tuple[Template, str]]:
    """把本案名称填进全部适用模板句（介质三句已废弃、不渲染）。自由槽位保留 {…} 供撰写侧填。"""
    out = []
    for t in TEMPLATES:
        if t.need == "system" and not system_name:
            continue
        s = t.text.replace("{方法名}", method_name).replace("{S}", indicative_subject)
        if system_name:
            s = s.replace("{系统名}", system_name)
        out.append((t, s))
    return out


# ---------------------------------------------------------------- 校验

def _candidates(paragraphs: list[str], t: Template) -> list[int]:
    if t.anchor_mode == "prefix":
        return [i for i, p in enumerate(paragraphs) if p.startswith(t.anchor)]
    return [i for i, p in enumerate(paragraphs) if t.anchor in p]


def _first_diff(expected_literal: str, got: str) -> int:
    n = min(len(expected_literal), len(got))
    for i in range(n):
        if expected_literal[i] != got[i]:
            return i
    return n


def _mismatch_detail(t: Template, got: str) -> str:
    """定位第一个偏离点：拿模板首个槽位之前的字面前缀与实得比对，给出「第 N 字起」的窗口。"""
    lit = t.text.split("{")[0]
    i = _first_diff(lit, got)
    if i < len(lit):
        return (f"第 {i + 1} 字起偏离：期望「…{lit[max(0, i - 6):i + 12]}…」 "
                f"实得「…{got[max(0, i - 6):i + 12]}…」")
    return f"槽位之后有改写：实得「{got[:40]}…{got[-24:]}」 vs 模板「{t.text[:40]}…{t.text[-24:]}」"


def check_paragraphs(paragraphs: list[str], has_system: bool,
                     sections: dict[int, str] | None = None) -> list[dict]:
    """逐字校验。paragraphs = 接受修订态的段落文本列表（md 非空行 / DOCX 段）。

    sections: {段索引: 章节名}（可选；给了就把候选限制在该模板的章节内，避免跨章误命中）。
    返回 violation 列表：{key, label, section, kind(missing|mismatch|extra|order|name), message, evidence}
    """
    vio: list[dict] = []
    found: dict[str, int] = {}
    names: dict[str, list[tuple[str, str]]] = {"方法名": [], "系统名": []}

    def in_section(i: int, t: Template) -> bool:
        if not sections:
            return True
        return sections.get(i) == t.section

    # 禁写项：介质相关段出现即 FAIL（王工 2026-09-11 口径）
    for label, forbidden in FORBIDDEN_MEDIUM_PARAS:
        for i, para in enumerate(paragraphs):
            if forbidden in para:
                vio.append({"key": "forbidden_medium", "label": label, "section": "全文",
                            "kind": "forbidden",
                            "message": f"出现禁写段：{label}——王工 2026-09-11 定「方法权写满九条、权10 系统、"
                                       "不再写介质权；发明内容没有第三方面了」，该段一律不写",
                            "evidence": para[:80]})
                break

    for t in TEMPLATES:
        needed = (t.need == "always"
                  or (t.need == "system" and has_system))
        cands = [i for i in _candidates(paragraphs, t) if in_section(i, t)]
        if not cands:
            if needed:
                vio.append({"key": t.key, "label": t.label, "section": t.section, "kind": "missing",
                            "message": f"缺模板句：{t.label}——须逐字为『{t.text}』（只填槽位）",
                            "evidence": f"锚点『{t.anchor}』在{t.section}零命中"})
            continue
        if len(cands) > 1 and t.key not in ("fig1",):
            vio.append({"key": t.key, "label": t.label, "section": t.section, "kind": "extra",
                        "message": f"{t.label}出现 {len(cands)} 处，应恰 1 处",
                        "evidence": "；".join(paragraphs[i][:30] for i in cands)})
        i = cands[0]
        got = paragraphs[i].strip()
        rx = template_regex(t)
        m = rx.match(got)
        if not m:
            for alt in t.variants:           # 「所述程序 / 所述计算机程序」等整句变体
                m_alt = template_regex(replace(t, text=alt)).match(got)  # dataclasses.replace
                if m_alt:
                    m = m_alt
                    break
        if not m and got not in t.variants:
            if t.need == "system" and not needed:
                msg = f"{t.label}在本案无对应保护主题却出现，且措辞偏离定版『{t.text}』"
            else:
                msg = f"{t.label}偏离模板——须逐字为『{t.text}』（只填槽位、不改一字）"
            vio.append({"key": t.key, "label": t.label, "section": t.section, "kind": "mismatch",
                        "message": msg, "evidence": _mismatch_detail(t, got)})
            found[t.key] = i
            continue
        found[t.key] = i
        if m:
            for slot in ("方法名", "系统名"):
                if slot in m.groupdict() and m.group(slot):
                    names[slot].append((t.key, m.group(slot)))

    # 名称槽位一致性：各模板句里的方法名/系统名必须相同，且系统名=方法名词干+「系统」
    for slot, items in names.items():
        vals = {v for _, v in items}
        if len(vals) > 1:
            vio.append({"key": "names", "label": f"{slot}槽位一致", "section": "全文", "kind": "name",
                        "message": f"各模板句的{slot}不一致：{sorted(vals)}",
                        "evidence": "；".join(f"{k}=『{v}』" for k, v in items)})
    mn = {v for _, v in names["方法名"]}
    sn = {v for _, v in names["系统名"]}
    if len(mn) == 1 and len(sn) == 1:
        a, b = next(iter(mn)), next(iter(sn))
        stem_a = re.sub(r"方法$", "", a)
        stem_b = re.sub(r"(系统|装置)$", "", b)
        if stem_a != stem_b:
            vio.append({"key": "names", "label": "方法名/系统名同源", "section": "全文", "kind": "name",
                        "message": f"方法名『{a}』与系统名『{b}』词干不一致（应为同一题名 +方法/+系统）",
                        "evidence": f"词干『{stem_a}』 vs 『{stem_b}』"})

    # 收尾顺序
    seq = [(found[k], k) for k in CLOSING_ORDER if k in found]
    if [k for _, k in sorted(seq)] != [k for _, k in seq]:
        vio.append({"key": "order", "label": "收尾套话顺序", "section": "具体实施方式", "kind": "order",
                    "message": "收尾顺序错误：应 综上所述 → 第二实施例 → 方法—系统对应 → 示意性说明 → 结束语",
                    "evidence": " → ".join(k for _, k in sorted(seq))})
    return vio


def check_claims(claim_lines: list[str]) -> list[dict]:
    """权利要求书侧：系统权整条逐字（编号头剥离后比对；{N} 须 = 系统权编号 − 1 = 9）。

    claim_lines = 权利要求书章的非空行（编号头行含正文）。**存储介质权自 2026-09-11 起不再撰写**
    （王工口径），出现即 FAIL。
    """
    vio: list[dict] = []
    heads = [(i, int(m.group(1)), m.group(2).strip())
             for i, ln in enumerate(claim_lines)
             for m in [re.match(r"^\s*(\d+)\s*[\.．]\s*(.*)$", ln)] if m]
    if not heads:
        return vio
    sys_idx = [(num, body) for _, num, body in heads if "包括存储器、处理器" in body
               or re.match(r"^一种[^，。；]{2,40}(?:系统|装置)，", body)]
    for num, body in ((n, b) for _, n, b in heads if b.startswith(MEDIUM_CLAIM_PREFIX)):
        vio.append({"key": "forbidden_medium", "label": "权利要求书·存储介质权（禁写）",
                    "section": "权利要求书", "kind": "forbidden",
                    "message": f"权{num} 出现存储介质权——王工 2026-09-11 定「方法权写满九条、最后一个写系统、"
                               "介质权不要写了」，该条一律不写；方法权不足 9 条时用方法从权补足",
                    "evidence": body[:80]})
    expect_n = (sys_idx[0][0] - 1) if sys_idx else None
    for t, hits in ((CLAIM_TEMPLATES[0], sys_idx),):
        if not hits:
            continue
        num, body = hits[0]
        m = template_regex(t).match(body)
        if not m:
            for alt in t.variants:              # 「所述程序 / 所述计算机程序」两种写法均可
                m_alt = template_regex(replace(t, text=alt)).match(body)
                if m_alt:
                    m = m_alt
                    break
        if not m:
            vio.append({"key": t.key, "label": t.label, "section": "权利要求书", "kind": "mismatch",
                        "message": f"权{num} {t.label}偏离模板——须逐字为『{t.text}』（编号头外只填槽位；"
                                   f"「其特征在于」位置、「权利要求1至N任一项」写法均不得改）",
                        "evidence": _mismatch_detail(t, body)})
            continue
        n = int(m.group("N"))
        if expect_n is not None and n != expect_n:
            vio.append({"key": t.key, "label": t.label, "section": "权利要求书", "kind": "mismatch",
                        "message": f"权{num} 引用范围「权利要求1至{n}」应为「1至{expect_n}」（= 系统权编号 − 1，覆盖全部方法权）",
                        "evidence": body[-40:]})
    return vio


# ---------------------------------------------------------------- 输入适配

def md_paragraphs(md_path: Path) -> tuple[list[str], dict[int, str]]:
    """全文稿 md → (非空正文行列表, {行索引: 章节名})。front-matter 与标题行剔除。"""
    raw = md_path.read_text(encoding="utf-8")
    if raw.startswith("---"):
        end = raw.find("\n---\n", 4)
        if end != -1:
            raw = raw[end + len("\n---\n"):]
    paras, secs, cur = [], {}, None
    for line in raw.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            if s.startswith("## "):
                cur = s[3:].strip()
            continue
        secs[len(paras)] = cur
        paras.append(s)
    return paras, secs


def docx_paragraphs(document_xml: str) -> tuple[list[str], dict[int, str]]:
    """DOCX document.xml → (接受修订态段落文本列表, {段索引: 章节名})。章节名按分节4 标题段推断。"""
    paras, secs = [], {}
    cur = None
    for p in re.findall(r"<w:p(?:\s[^>]*)?/>|<w:p(?:\s[^>]*)?>.*?</w:p>", document_xml, re.S):  # 含自闭合 <w:p/>
        q = re.sub(r"<w:del\b.*?</w:del>", "", p, flags=re.S)
        t = "".join(re.findall(r"<w:t\b[^>]*>([^<]*)</w:t>", q)).strip()
        if not t:
            continue
        if t in ("技术领域", "背景技术", "发明内容", "附图说明", "具体实施方式"):
            cur = t
            continue
        secs[len(paras)] = cur
        paras.append(t)
    return paras, secs


def detect_subjects(claims_text: str) -> tuple[bool, bool]:
    """从权利要求文本判断是否有系统/装置权、存储介质权（后者仅用于报禁写，非应写项）。"""
    has_system = bool(re.search(r"一种[^，。；]{2,40}(?:系统|装置)，(?:包括|其特征在于)", claims_text))
    has_medium = "一种计算机可读存储介质" in claims_text
    return has_system, has_medium


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sh = sub.add_parser("show", help="打印全部模板句原文（槽位留空，供人查看口径；机器校对用 check）")
    sh.add_argument("--claims", action="store_true", help="连同权利要求书侧系统权一条一起打印")
    r = sub.add_parser("render", help="把本案名称填进全部模板句")
    r.add_argument("--method-name", required=True,
                   help="本案方法保护主题：权 1 名称去掉「一种」后的整串，"
                        "= 王工给定案件名称去掉「及系统/及装置」后缀（如「基于红外热成像的埋地供热管网泄漏定位方法」）")
    r.add_argument("--system-name", default=None,
                   help="本案系统/装置保护主题：与方法同词干、末尾「系统」或「装置」（无系统权则不传；check 会校验两名词干一致）")

    r.add_argument("--indicative-subject", default="系统", choices=["系统", "装置"])
    c = sub.add_parser("check", help="逐字校验全文稿 md")
    c.add_argument("--md", type=Path, required=True)
    c.add_argument("--claims-md", type=Path, default=None, help="权要稿.md（判断系统/介质权；缺省从全文稿找权利要求书章）")
    c.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "show":
        items = list(TEMPLATES) + (list(CLAIM_TEMPLATES) if args.claims else [])
        for tpl in items:
            print(f"[{tpl.section}] {tpl.label}  (need={tpl.need}, key={tpl.key})")
            print(tpl.text)
            print()
        print("（以上为全部模板句的唯一副本；撰写时用 `render` 填本案名称后整句粘贴，"
              "校验用 `check`，规则文件只放指针不摘引原文。介质相关三句自 2026-09-11 起禁写，不在本表）")
        return 0

    if args.cmd == "render":
        for t, s in render(args.method_name, args.system_name, args.indicative_subject):
            print(f"[{t.section}] {t.label}")
            print(s)
            print()
        return 0

    paras, secs = md_paragraphs(args.md)
    claims_text = ""
    if args.claims_md and args.claims_md.exists():
        claims_text = args.claims_md.read_text(encoding="utf-8")
    else:
        claims_text = args.md.read_text(encoding="utf-8")
    has_system, has_medium = detect_subjects(claims_text)
    vio = check_paragraphs(paras, has_system, secs)
    if args.claims_md and args.claims_md.exists():
        cl, _ = md_paragraphs(args.claims_md)
        vio += check_claims(cl)
    if args.json:
        import json
        print(json.dumps({"has_system": has_system, "has_medium": has_medium, "violations": vio},
                         ensure_ascii=False, indent=2))
    else:
        print(f"== 模板句逐字校验: {args.md}  (系统权={has_system} 介质权={has_medium}) ==")
        for v in vio:
            print(f"  [FAIL] {v['label']} — {v['message']}\n         {v['evidence']}")
        print("-" * 40)
        print("结果: 全部 PASS" if not vio else f"结果: {len(vio)} 项 FAIL")
    return 0 if not vio else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())

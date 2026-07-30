#!/usr/bin/env python3
"""
硬规则机械化检查脚本 (第一类).

用法:
    python3 scripts/check_hard_rules.py --md docs/权要稿.md --stage claims-draft
    python3 scripts/check_hard_rules.py --md docs/全文稿.md --stage full-draft

Exit code = 违反的硬规则数量; 0 = 全通过.

输出 JSON 到 stdout (方便各路 auditor / 主 agent 消费), 报告到 stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# -----------------------------------------------------------------------------
# 常量
# -----------------------------------------------------------------------------

# G5-1 禁用措辞黑名单
FORBIDDEN_WORDS = [
    "直接", "即时", "然后", "可以", "首先", "其次", "能够", "例如",
    "只有", "一定",
]
# 采用 xxx 工具 / 模块 (模式匹配)
FORBIDDEN_PATTERNS = [
    (r"采用[一-龥A-Za-z0-9]{1,20}工具", "G5-1 采用xxx工具"),
    (r"采用[一-龥A-Za-z0-9]{1,20}模块", "G5-1 采用xxx模块"),
]

# 案例性术语黑名单 (docx-template.md G8-2)
CASE_TERMS = [
    "特征1", "特征2", "特征3", "特征4",
    "智慧农业", "目标结果", "xx操作", "xx模型", "XX操作", "XX模型",
    "本方法能够实现",
]

# 权要一稿禁写章节 (SKILL.md 权要一稿 step 5)
CLAIMS_DRAFT_FORBIDDEN_SECTIONS = [
    "说明书摘要", "摘要附图", "发明内容", "附图说明",
    "具体实施方式", "说明书附图",
]

# 全文稿正文章节顺序 (full-draft.md L4-L8; 权利要求书/技术领域/背景技术冻结在权要稿.md, 不在全文稿)
FULL_DRAFT_REQUIRED_SECTIONS_ORDER = [
    "说明书摘要", "摘要附图", "发明内容", "附图说明", "具体实施方式",
]

# 说明书禁用数量词 (G6-1)
FULL_DRAFT_FORBIDDEN_QUANTIFIERS = ["若干个", "多个"]

# -----------------------------------------------------------------------------
# 数据结构
# -----------------------------------------------------------------------------


@dataclass
class Violation:
    rule_id: str
    location: str
    evidence: str
    message: str


@dataclass
class Report:
    stage: str
    md_path: str
    violations: list[Violation] = field(default_factory=list)

    def add(self, rule_id: str, location: str, evidence: str, message: str) -> None:
        self.violations.append(Violation(rule_id, location, evidence, message))

    def count(self) -> int:
        return len(self.violations)


# -----------------------------------------------------------------------------
# 通用工具
# -----------------------------------------------------------------------------


def count_chinese(text: str) -> int:
    """统计中文字符数 (不含标点/空白)."""
    return sum(1 for ch in text if "一" <= ch <= "鿿")


def count_chars_incl_punct(text: str) -> int:
    """统计全部非空白字符数 (含标点), 与 Word 字数统计/电子申请客户端口径一致."""
    return sum(1 for ch in text if not ch.isspace())


def load_md(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def split_sections(lines: list[str]) -> dict[str, tuple[int, int]]:
    """按 `##` heading 切分, 返回 {section_title: (start_line, end_line)} (含首行, 不含末行)."""
    sections: dict[str, tuple[int, int]] = {}
    current_title: str | None = None
    current_start = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_title is not None:
                sections[current_title] = (current_start, idx)
            current_title = stripped[3:].strip()
            current_start = idx + 1
    if current_title is not None:
        sections[current_title] = (current_start, len(lines))
    return sections


def get_section_lines(lines: list[str], sections: dict, key_substr: str) -> tuple[list[str], int]:
    """按标题子串找 section, 返回该段行列表与起始行号 (未找到则返回 [], -1)."""
    for title, (start, end) in sections.items():
        if key_substr in title:
            return lines[start:end], start
    return [], -1


def extract_claim_blocks(lines: list[str], sections: dict) -> dict[int, tuple[int, int]]:
    r"""
    从权利要求书 section 里抽出每条权要的行区间.
    权要开头段格式: `^\d+\.` (行首编号后接点号).
    返回 {claim_number: (start_line_absolute, end_line_absolute)}.
    """
    body, offset = get_section_lines(lines, sections, "权利要求书")
    if offset < 0:
        return {}
    heads: list[tuple[int, int]] = []
    for i, line in enumerate(body):
        m = re.match(r"^\s*(\d+)\s*\.", line)
        if m:
            heads.append((int(m.group(1)), offset + i))
    if not heads:
        return {}
    blocks: dict[int, tuple[int, int]] = {}
    for i, (num, start) in enumerate(heads):
        end = heads[i + 1][1] if i + 1 < len(heads) else offset + len(body)
        blocks[num] = (start, end)
    return blocks


# -----------------------------------------------------------------------------
# 检查项: Phase 1a
# -----------------------------------------------------------------------------


def check_claim1_length(lines: list[str], sections: dict, report: Report) -> None:
    """规则 1: 权要 1 中文字数 <= 400 (L1-1, claims-format-standard)."""
    blocks = extract_claim_blocks(lines, sections)
    if 1 not in blocks:
        report.add("L1-1", "权利要求书", "-", "未找到权要 1")
        return
    start, end = blocks[1]
    text = "\n".join(lines[start:end])
    n = count_chinese(text)
    if n > 400:
        report.add(
            "L1-1", f"权利要求书 第{start + 1}行起",
            f"权要 1 中文字数 = {n}",
            f"权要 1 中文字数超限 (>{400}, 实际 {n})",
        )


def check_claim1_step_count(lines: list[str], sections: dict, report: Report) -> None:
    """规则 1b: 权要 1 主步骤最多不超过 6 个 (L1-1 硬上限; 3-5 个为宜属建议口径不在此报).

    主步骤数 = 权要 1 块内非空行数 - 1 (扣除编号头行"1.一种...包括:");
    与 claims-format-standard 的"每个分号步骤独立成段"口径一致,
    步骤行内续写的"; 所述xx包括..."限定短句不另计步骤.
    """
    blocks = extract_claim_blocks(lines, sections)
    if 1 not in blocks:
        return  # 缺权要 1 已由 check_claim1_length 报
    start, end = blocks[1]
    body_lines = [ln for ln in lines[start:end] if ln.strip()]
    if len(body_lines) < 2:
        return  # 未按分段格式撰写, 由断行检查项报
    n_steps = len(body_lines) - 1
    if n_steps > 6:
        report.add(
            "L1-1", f"权利要求书 第{start + 1}行起",
            f"权要 1 主步骤数 = {n_steps}",
            f"权要 1 主步骤超过硬上限 6 个 (实际 {n_steps}), 应合并同一技术链上的连续动作或将细节下沉从属权要",
        )


def check_each_claim_one_period(lines: list[str], sections: dict, report: Report) -> None:
    """规则 2: 每条权要只用一个句号 (L1-1)."""
    blocks = extract_claim_blocks(lines, sections)
    for num, (start, end) in blocks.items():
        text = "\n".join(lines[start:end])
        cnt = text.count("。")
        if cnt != 1:
            report.add(
                "L1-1", f"权利要求书 第{start + 1}行起",
                f"权要 {num} 中句号 (。) 数量 = {cnt}",
                f"权要 {num} 应只用一个句号, 实际 {cnt} 个",
            )


def check_system_media_claim_no_debuzou(lines: list[str], sections: dict, report: Report) -> None:
    """规则 2b: 系统/装置独权、存储介质权末尾不写'的步骤'三字 (L1-1, claims.md 系统/介质权收尾口径).

    系统/介质权末尾一律以句号收口, 即'……所述的〔方法权发明名称全称〕。',
    不写'……所述的〔方法权发明名称全称〕的步骤。'。
    识别: 权要正文含'包括存储器、处理器'或'计算机可读存储介质'者属系统/介质权。
    """
    blocks = extract_claim_blocks(lines, sections)
    for num, (start, end) in blocks.items():
        text = "\n".join(lines[start:end])
        is_system_or_media = (
            "包括存储器、处理器" in text or "计算机可读存储介质" in text
        )
        if not is_system_or_media:
            continue
        if "的步骤" in text:
            report.add(
                "L1-1", f"权利要求书 第{start + 1}行起",
                f"权要 {num} (系统/介质权) 含 '的步骤'",
                f"系统/装置独权、存储介质权末尾不写'的步骤', 以句号直接收口 "
                f"('……所述的〔方法权发明名称全称〕。' 而非 '……的步骤。'); "
                f"请删除权 {num} 末尾 '的步骤' 三字",
            )



def check_semicolon_line_ending(lines: list[str], sections: dict, report: Report) -> None:
    """规则 3: 含分号的段落以分号结尾 (L1-1 / G8-1)."""
    blocks = extract_claim_blocks(lines, sections)
    for num, (start, end) in blocks.items():
        for i in range(start, end):
            line = lines[i].rstrip()
            if not line:
                continue
            if "；" in line and not line.endswith("；"):
                # 允许权要末段以句号结尾 (整条权要唯一句号)
                if line.endswith("。"):
                    continue
                report.add(
                    "L1-1 / G8-1", f"第{i + 1}行",
                    line.strip()[:80],
                    f"权要 {num} 内含分号的行未以分号结尾",
                )


def check_claim_numbering(lines: list[str], sections: dict, report: Report) -> None:
    """规则 4: 权要编号连续无断号 (scoring.md 第一闸)."""
    blocks = extract_claim_blocks(lines, sections)
    if not blocks:
        return
    nums = sorted(blocks.keys())
    for i, n in enumerate(nums, start=1):
        if n != i:
            report.add(
                "L1-1 编号连续", "权利要求书",
                f"实际编号 = {nums}",
                f"权要编号不连续: 期望 {i}, 实际 {n}",
            )
            return


def check_total_claim_count(lines: list[str], sections: dict, report: Report) -> None:
    """规则 6: 权要总数必须 = 10 (L1-1, claims.md '必须写满十条')."""
    blocks = extract_claim_blocks(lines, sections)
    n = len(blocks)
    if n != 10:
        report.add(
            "L1-1", "权利要求书",
            f"权要总数 = {n}",
            f"权要总数必须写满 10 条 (实际 {n}, {'少于' if n < 10 else '多于'} 10); "
            f"通过拆分/合并方法从权调整条数凑满 10 条, 不得多写也不得少写",
        )


def check_dependent_claim_no_yizhong(lines: list[str], sections: dict, report: Report) -> None:
    """规则 7: 从权开头不重复"一种" (L1-1)."""
    blocks = extract_claim_blocks(lines, sections)
    pattern = re.compile(r"根据权利要求\s*\d+\s*所述的一种")
    for num, (start, end) in blocks.items():
        for i in range(start, end):
            if pattern.search(lines[i]):
                report.add(
                    "L1-1", f"第{i + 1}行",
                    lines[i].strip()[:80],
                    f"权要 {num} 从属开头重复了'一种'",
                )
                break


def check_dependent_claim_reference(lines: list[str], sections: dict, report: Report) -> None:
    """规则 5: 从权依附合法 (被依附的权要必须存在且在前) (scoring.md 第一闸)."""
    blocks = extract_claim_blocks(lines, sections)
    if not blocks:
        return
    max_num = max(blocks.keys())
    pattern = re.compile(r"根据权利要求\s*(\d+)")
    for num, (start, end) in blocks.items():
        text = "\n".join(lines[start:end])
        deps = pattern.findall(text)
        for d in deps:
            d_int = int(d)
            if d_int not in blocks:
                report.add(
                    "L1-1", f"权要 {num}",
                    f"引用了权要 {d_int}",
                    f"权要 {num} 依附的权要 {d_int} 不存在",
                )
            elif d_int >= num:
                report.add(
                    "L1-1", f"权要 {num}",
                    f"引用了权要 {d_int}",
                    f"权要 {num} 依附了后位权要 {d_int} (应依附前位)",
                )


def check_no_formula_in_claims(lines: list[str], sections: dict, report: Report) -> None:
    """规则 8: 权利要求中不写公式 (L1-1 / G6-1)."""
    blocks = extract_claim_blocks(lines, sections)
    # 简单启发式: 出现 LaTeX / 独立等号数学式
    formula_re = re.compile(r"\\frac|\\sum|\\int|\\sqrt|\\[a-zA-Z]+\{|\$")
    for num, (start, end) in blocks.items():
        for i in range(start, end):
            if formula_re.search(lines[i]):
                report.add(
                    "L1-1 / G6-1", f"第{i + 1}行",
                    lines[i].strip()[:80],
                    f"权要 {num} 内出现疑似公式",
                )
                break


def check_forbidden_words(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 9: G5-1 禁用措辞黑名单."""
    scan_range = _get_scan_ranges(lines, sections, stage)
    for (label, start, end) in scan_range:
        for i in range(start, end):
            line = lines[i]
            for w in FORBIDDEN_WORDS:
                if w in line:
                    report.add(
                        "G5-1", f"{label} 第{i + 1}行",
                        line.strip()[:80],
                        f"出现禁用措辞: {w}",
                    )
        for i in range(start, end):
            line = lines[i]
            for pat, tag in FORBIDDEN_PATTERNS:
                if re.search(pat, line):
                    report.add(
                        tag, f"{label} 第{i + 1}行",
                        line.strip()[:80],
                        f"出现禁用模式: {tag}",
                    )


def check_case_terms(lines: list[str], sections: dict, report: Report) -> None:
    """规则 15: 案例性术语黑名单 (docx-template.md G8-2)."""
    for i, line in enumerate(lines):
        for term in CASE_TERMS:
            if term in line:
                report.add(
                    "G8-2", f"第{i + 1}行",
                    line.strip()[:80],
                    f"出现模板遗留案例性术语: {term}",
                )


def check_background_length_and_paragraphs(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 18/19: 背景技术字数 250-350 / 段落数 2-3 (L3-1)."""
    if stage not in {"claims-draft", "full-draft"}:
        return
    body, offset = get_section_lines(lines, sections, "背景技术")
    if offset < 0:
        return
    text = "\n".join(body).strip()
    if not text:
        return
    n = count_chinese(text)
    if not (250 <= n <= 350):
        report.add(
            "L3-1", "背景技术",
            f"中文字数 = {n}",
            f"背景技术字数应在 250-350 之间 (实际 {n})",
        )
    # 段落数: 以空行分段
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not (2 <= len(paragraphs) <= 3):
        report.add(
            "L3-1", "背景技术",
            f"段落数 = {len(paragraphs)}",
            f"背景技术应 2-3 段 (实际 {len(paragraphs)})",
        )


def check_tech_field_single_paragraph(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 20: 技术领域单段 (L2-1)."""
    if stage not in {"claims-draft", "full-draft"}:
        return
    body, offset = get_section_lines(lines, sections, "技术领域")
    if offset < 0:
        return
    text = "\n".join(body).strip()
    if not text:
        return
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) != 1:
        report.add(
            "L2-1", "技术领域",
            f"段落数 = {len(paragraphs)}",
            f"技术领域应单段 (实际 {len(paragraphs)})",
        )


# -----------------------------------------------------------------------------
# 检查项: Phase 1b
# -----------------------------------------------------------------------------


def check_section_order(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 13: 全文稿必备文本章节齐全且说明书内部顺序正确 (L4/L6/L7/L8).

    全文稿.md 结构 (inject_fulldraft.py 要求): 技术领域/背景技术/发明内容/附图说明/
    具体实施方式为 `## 说明书` 下的 `### ` 子标题, 说明书摘要为独立 `## ` 章节;
    故须同时扫描 `## ` 与 `### ` 两级标题(split_sections 只切 `## `, 不足以覆盖)。
    摘要附图(L5)为 DOCX 图形分节、无 md 文本标题(由 verify_docx_skeleton 核分节2/5),
    不作为 md 级必备文本章节。"""
    if stage != "full-draft":
        return
    required = [n for n in FULL_DRAFT_REQUIRED_SECTIONS_ORDER if n != "摘要附图"]
    pos: dict[str, int] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            title = stripped.lstrip("#").strip()
            for name in required:
                if name in title and name not in pos:
                    pos[name] = i
    for name in required:
        if name not in pos:
            report.add(
                "L1-L8 章节顺序", "全文稿",
                f"已检出 = {list(pos)}",
                f"缺少章节: {name}",
            )
    # 说明书正文内部顺序: 发明内容 → 附图说明 → 具体实施方式
    body_seq = [n for n in ("发明内容", "附图说明", "具体实施方式") if n in pos]
    for a, b in zip(body_seq, body_seq[1:]):
        if pos[a] > pos[b]:
            report.add(
                "L1-L8 章节顺序", "全文稿",
                f"{a}@{pos[a] + 1} > {b}@{pos[b] + 1}",
                f"章节顺序错误: {b} 应在 {a} 之后",
            )
            break


def check_claims_draft_forbidden_sections(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 14: 权要一稿禁写章节 (SKILL.md 权要一稿 step 5)."""
    if stage != "claims-draft":
        return
    for title in sections:
        for forbidden in CLAIMS_DRAFT_FORBIDDEN_SECTIONS:
            if forbidden in title:
                report.add(
                    "SKILL 权要一稿", "章节",
                    title,
                    f"权要一稿不得写入章节: {forbidden}",
                )


# -----------------------------------------------------------------------------
# 检查项: Phase 1c
# -----------------------------------------------------------------------------


def check_noun_colon_definition(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 10: 名词冒号定义句式 (G5-1). 旧稿带编号子步骤引导句 `步骤SxN：...` 仍排除 (新范式子步骤无编号、在"包括："后分号列举, 不触发本规则)."""
    scan = _get_scan_ranges(lines, sections, stage)
    # 匹配: 行首 (可能有缩进) 短名词 + 中文冒号 + 内容 (不是子列表说明)
    pattern = re.compile(r"^\s*[一-龥A-Za-z0-9]{2,10}：[一-龥]{2,}")
    sub_step_lead = re.compile(r"^\s*步骤S\d+[：:]")
    for (label, start, end) in scan:
        for i in range(start, end):
            line = lines[i]
            if sub_step_lead.match(line):
                continue
            if pattern.match(line):
                report.add(
                    "G5-1", f"{label} 第{i + 1}行",
                    line.strip()[:80],
                    "出现名词冒号定义句式",
                )


def check_latex_no_delimiter(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 16: 块公式独立成段不带定界符; 行内公式用成对 $…$ (G6-1).

    G6-1 区分两类: **块公式**独立成段、纯 LaTeX、不带 `$`; **行内公式**(参数解释段/
    正文中引用的符号如 `$s_1$`、`$\\Sigma_1^{-1}$`)以**成对** `$…$` 定界, 注入时转原生
    行内 `<m:oMath>` —— 成对行内 `$…$` 属规则要求, 合法放行。仅在下列情形报错:
    出现 `$$` 行间定界符(本工作流不使用), 或单行内未转义 `$` 落单未闭合。"""
    if stage != "full-draft":
        return
    for i, line in enumerate(lines):
        if "$$" in line:
            report.add(
                "G6-1", f"第{i + 1}行",
                line.strip()[:80],
                "不应使用 $$ 行间公式定界符(块公式独立成段、不带定界符)",
            )
            continue
        # 未转义单 $ 成对=行内公式(合法); 落单(奇数个)=定界符未闭合
        if len(re.findall(r"(?<![\\])\$", line)) % 2 == 1:
            report.add(
                "G6-1", f"第{i + 1}行",
                line.strip()[:80],
                "行内公式 $ 定界符未成对闭合",
            )


def check_impl_no_stale_expansion(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 17: 具体实施方式禁"进一步地"逐条复述旧范式 (L8-1 新范式).

    新范式下子步骤在"包括："后无编号分号集中列举、展开段用"具体而言/需要说明的是"
    引导; "进一步地，"是已废止的旧范式子步骤复述引导, 仅合法出现于发明内容 (L6 从权
    引导). 具体实施方式章内出现即旧范式残留, 逐处报.
    """
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "具体实施方式")
    if offset < 0:
        return
    for i, line in enumerate(body):
        s = line.strip()
        if s.startswith("进一步地，") or s.startswith("进一步地,"):
            report.add(
                "L8-1", f"具体实施方式 第{offset + i + 1}行",
                s[:60],
                "具体实施方式出现'进一步地'旧范式子步骤复述; 新范式应在'包括：'后无编号分号列举、展开段用'具体而言/需要说明的是'",
            )


def check_include_lead_not_inline(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 18: "包括："引导句后不得把子步骤挤在同一行 (L6-1 / L8-0 分号分段).

    规范写法: 引导句以"……，包括："结尾单独成段, 其后各子步骤分号断行、各自成段.
    "，包括："(带全角冒号) 后同行还有非空文本 = 子步骤逗号连缀挤入引导行 (未分号分段).
    系统权"……系统，包括存储器、处理器……"用"包括"无冒号、不匹配, 不误报. 仅扫发明内容
    与具体实施方式两章.
    """
    if stage != "full-draft":
        return
    for key in ("发明内容", "具体实施方式"):
        body, offset = get_section_lines(lines, sections, key)
        if offset < 0:
            continue
        for i, line in enumerate(body):
            s = line.strip()
            m = re.search(r"，包括：(.*)$", s)
            if m and m.group(1).strip():
                report.add(
                    "L6-1 / L8-0", f"{key} 第{offset + i + 1}行",
                    s[:80],
                    "'包括：'后子步骤挤在引导行 (逗号连缀), 应各子步骤分号断行、各自成段",
                )


# G6-1 Unicode 下标字符集 (冒充公式下标; 上标 ²³ 在单位 m² 合法故不纳入, 保零误报)
UNICODE_SUBSCRIPTS = set("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼ")


def check_unicode_subscript_abuse(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 19: 禁用 Unicode 下标字符冒充公式符号下标 (G6-1).

    如 s₁、Σ₁、xᵢ 里的 ₁/ᵢ——WPS 渲染成全角、上下标不叠放, 等同未编译公式=公开不充分.
    公式符号一律写 $…$ 行内 LaTeX (注入转原生 <m:oMath>). 仅查下标: 上标 ²³ 等在单位
    (m²) 合法, 不纳入以保零误报. 仅扫说明书正文 (full-draft).
    """
    if stage != "full-draft":
        return
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        for i in range(start, end):
            hit = sorted({ch for ch in lines[i] if ch in UNICODE_SUBSCRIPTS})
            if hit:
                report.add(
                    "G6-1", f"{label} 第{i + 1}行", lines[i].strip()[:60],
                    f"出现 Unicode 下标字符 {''.join(hit)} 冒充公式下标; 应写 $…$ 行内 LaTeX",
                )


def check_double_punctuation(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 20: 相同句读标点连续 (双标点, 注入后通读机械化).

    。。/；；/，，/：： 等相同全角标点连续 = 断句残缺或留痕注入残留. 中文省略号用 …(U+2026)
    不在此集、不冲突. 仅查相同标点连续 (不查 ？！ 等合法组合) 以保零误报. 仅扫说明书正文.
    """
    if stage != "full-draft":
        return
    pat = re.compile(r"([。；，：！？])\1")
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        for i in range(start, end):
            m = pat.search(lines[i])
            if m:
                report.add(
                    "G8", f"{label} 第{i + 1}行", lines[i].strip()[:60],
                    f"相同标点连续 '{m.group(0)}' (双标点/断句残缺)",
                )


def check_full_draft_forbidden_quantifiers(lines: list[str], sections: dict, report: Report, stage: str, claims_text: str = "") -> None:
    """规则 12: 全文稿 (说明书部分) 禁用'若干个'/'多个' (G6-1).

    豁免: 权要分句原文复述 (L8-0 同构优先) —— 若量词及其后续短语 (量词+6字窗口)
    同样出现在 --claims-md 传入的权要文本中, 视为权要原文复述, 不报violation.
    """
    if stage != "full-draft":
        return
    # 说明书范围 = 除权利要求书外的章节
    for title, (start, end) in sections.items():
        if "权利要求书" in title:
            continue
        for i in range(start, end):
            for w in FULL_DRAFT_FORBIDDEN_QUANTIFIERS:
                pos = lines[i].find(w)
                if pos < 0:
                    continue
                if claims_text:
                    phrase = lines[i][pos:pos + len(w) + 6]
                    if phrase and phrase in claims_text:
                        continue  # 权要原文复述, 同构优先豁免
                report.add(
                    "G6-1", f"{title} 第{i + 1}行",
                    lines[i].strip()[:80],
                    f"说明书内禁用数量词: {w}",
                )


def check_abstract_length(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 (L4-1): 说明书摘要 <= 300 字 (含标点口径)."""
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "说明书摘要")
    if offset < 0:
        return
    text = "\n".join(body).strip()
    if not text:
        return
    n = count_chars_incl_punct(text)
    if n > 300:
        report.add(
            "L4-1", "说明书摘要",
            f"含标点字数 = {n}",
            f"说明书摘要字数超限 (>300, 实际 {n}, 含标点口径)",
        )


def check_figure_numbering(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 (L7-1): 附图编号连续."""
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "附图说明")
    if offset < 0:
        return
    nums = []
    pattern = re.compile(r"^\s*图\s*(\d+)")
    for line in body:
        m = pattern.match(line)
        if m:
            nums.append(int(m.group(1)))
    if not nums:
        return
    for i, n in enumerate(nums, start=1):
        if n != i:
            report.add(
                "L7-1", "附图说明",
                f"图编号 = {nums}",
                f"附图编号不连续: 期望 图{i}, 实际 图{n}",
            )
            return


def check_closing_boilerplate(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 21: 具体实施方式收尾=实施例分层+固定套话 (L8-1).

    说明书按实施例分层: 第一实施例=方法, 第二实施例=系统 (计算机设备式), 其后可续
    计算机可读存储介质. 系统内容属第二实施例, 不得用"本发明实施例还提供了一种...系统"
    模糊表述写进方法(第一实施例)正文并展开存储器/处理器构成与部署细节. 收尾四锚点按序
    出现, 缺一或乱序即 FAIL. 锚点取模板固定骨架 (发明名称在填空处、不入锚点), 零误报.
    仅 full-draft.
    """
    if stage != "full-draft":
        return
    anchors = [
        ("综上所述总结段(第一实施例=方法收口)", re.compile(r"综上所述，本发明公开了一种")),
        ("第二实施例系统段", re.compile(r"第[一二三四五六七八九]实施例提供了一种")),
        ("方法-系统对应段(因而不再赘述)", re.compile(r"因而不再赘述")),
        ("结束语(并不用于限定本发明的保护范围)", re.compile(r"并不用于限定本发明的保护范围")),
    ]
    # 收尾总结段缺失 = 说明书未写收尾, 只报一次 (避免全缺时刷屏)
    if not any(anchors[0][1].search(ln) for ln in lines):
        report.add(
            "L8-1", "具体实施方式(收尾)",
            "未检出 综上所述，本发明公开了一种",
            "缺收尾总结段'综上所述，本发明公开了一种〔发明名称〕方法……'",
        )
        return
    pos: list[int] = []
    missing = False
    for name, pat in anchors:
        hit = next((i for i, ln in enumerate(lines) if pat.search(ln)), -1)
        pos.append(hit)
        if hit < 0:
            missing = True
            if name == "第二实施例系统段":
                report.add(
                    "L8-1", "具体实施方式(收尾)",
                    "未检出 第X实施例提供了一种",
                    "系统实施例未按'本发明第二实施例提供了一种〔发明名称〕系统，包括：存储器、处理器…'规整: "
                    "第一实施例=方法、第二实施例=系统; 勿用'本发明实施例还提供了一种系统'模糊表述, "
                    "勿把系统构成/部署展开写进方法(第一实施例)正文",
                )
            else:
                report.add(
                    "L8-1", "具体实施方式(收尾)",
                    f"缺锚点: {name}",
                    f"收尾固定套话缺失: {name}",
                )
    if missing:
        return
    order_names = [a[0] for a in anchors]
    for k in range(len(pos) - 1):
        if pos[k] > pos[k + 1]:
            report.add(
                "L8-1", "具体实施方式(收尾)",
                f"{order_names[k]}@{pos[k] + 1} 在 {order_names[k + 1]}@{pos[k + 1] + 1} 之后",
                "收尾套话顺序错误: 应 综上所述(方法)→第二实施例(系统)→因而不再赘述→结束语",
            )
            break


def check_benefit_enumeration(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 22: 有益效果分项禁"其一/其二"式序数词, 用"（1）（2）"(L6-1).

    发明内容有益效果分项一律全角括号数字"（1）（2）（3）", 禁"其一/其二/其三"或"其1".
    "其"+序数汉字+全角逗号 模式在规范说明书 (分项用 Sxx/分号/括号数字) 不应出现, 零误报.
    仅 full-draft.
    """
    if stage != "full-draft":
        return
    pat = re.compile(r"其[一二三四五六七八九十]，")
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        for i in range(start, end):
            if pat.search(lines[i]):
                report.add(
                    "L6-1", f"{label} 第{i + 1}行", lines[i].strip()[:60],
                    "有益效果/正文分项用了'其一/其二'式序数词; 应改全角括号数字'（1）（2）（3）'",
                )


def check_judgment_sentence_pattern(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 23: 说明书判断步骤句式合规 (G6-1 规定句式, 原 impl-auditor 语义项 9 的句式半边).

    G6-1 只允许两种双分支句式:
      句式一: 当判定满足xx时，则执行xx；当判定不满足xx时，则执行xx。
      句式二: 判断是否满足xx，若是，则执行xx；若否，则执行xx。
    单分支条件触发合并写成"若xx，则xx"(不含"判断是否"), 合法。机械红线 (按句号分句判):
      - 某分句以"判断/判定…是否"作步骤谓语开头(允许前置'则/再/并/先/随后/然后'),
        整句却未同时含"若是"与"若否" → 句式二残缺或未用规定句式。"用于判定是否…"
        "作为判断是否…的依据"等名词性描述非步骤谓语, 不报(实测三真实案件的误报边界);
      - 句内出现"当判定满足"却无"当判定不满足"(或反之) → 句式一只写半支;
      - 句内"若是，/若是则"与"若否，/若否则"落单 → 分支不成对("若是首次采集"式
        白话条件不匹配, 不报)。
    分支数与权要一致(G6-1 清单①②)需比对权要语义, 仍归 impl-auditor, 本规则不越权。
    仅 full-draft, 只扫具体实施方式章。
    """
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "具体实施方式")
    if offset < 0:
        return
    judge_step = re.compile(r"^(?:则|再|并|先|随后|然后)?判[断定][^，；：]{0,30}?是否")
    branch_yes = re.compile(r"若是[，,则]")
    branch_no = re.compile(r"若否[，,则]")
    for i, line in enumerate(body):
        loc = f"具体实施方式 第{offset + i + 1}行"
        for sent in re.split(r"。", line):
            if not sent.strip():
                continue
            ev = sent.strip()[:70]
            is_judge_step = any(judge_step.match(cl.strip()) for cl in re.split(r"[，；：]", sent))
            if is_judge_step and not (branch_yes.search(sent + "，") and branch_no.search(sent + "，")):
                report.add(
                    "G6-1", loc, ev,
                    "判断步骤含'判断…是否'但未按规定句式写全'若是，则…；若否，则…'两分支; "
                    "单分支逻辑应合并为'若xx，则执行xx'(G6-1 判断句式)",
                )
                continue
            if ("当判定满足" in sent) != ("当判定不满足" in sent):
                report.add(
                    "G6-1", loc, ev,
                    "判断句式一只写了半支; '当判定满足…时，则…'必须与'当判定不满足…时，则…'成对(G6-1)",
                )
                continue
            if bool(branch_yes.search(sent)) != bool(branch_no.search(sent)):
                report.add(
                    "G6-1", loc, ev,
                    "'若是'/'若否'分支落单; 双分支判断两支必须在同一句内成对写全(G6-1 判断句式)",
                )


def check_substep_numbering(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 24: 子步骤禁 SXX1/步骤Sxxx 式编号 (L8-2, 原 impl-auditor 语义项 14 的编号半边).

    主步骤编号为 S11..S16 (权 1 分句数硬上限 6, 两位数字); 具体实施方式出现
    S+三位及以上数字即子步骤编号残留 (子步骤一律在"包括："后无编号分号列举)。
    LaTeX 公式中的下标写作 S_{11} 带下划线, 不匹配。仅 full-draft。
    """
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "具体实施方式")
    if offset < 0:
        return
    pat = re.compile(r"S\d{3,}")
    for i, line in enumerate(body):
        m = pat.search(line)
        if m:
            report.add(
                "L8-2", f"具体实施方式 第{offset + i + 1}行", line.strip()[:60],
                f"子步骤编号残留 '{m.group(0)}'; 子步骤一律无编号, 在'包括：'后分号断行集中列举(L8-2)",
            )


def check_benefit_generic_phrases(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 25: 有益效果光杆泛词 (L6-2, 原 content-auditor 语义项 7 的泛词半边).

    只抓紧邻形态"提高/提升/增强/降低(了)(系统/整体)效率/准确性/精度/鲁棒性/可靠性/
    稳定性/成本"——动词与泛化名词间无具体宾语即光杆泛词; "提高了xx识别的准确性"
    带具体宾语, 不匹配 (实测三真实案件零命中边界)。只扫发明内容章, 仅 full-draft。
    """
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "发明内容")
    if offset < 0:
        return
    pat = re.compile(r"(?:提高|提升|增强|降低)(?:了)?(?:系统|整体)?(?:效率|准确性|精度|鲁棒性|可靠性|稳定性|成本)")
    for i, line in enumerate(body):
        for m in pat.finditer(line):
            report.add(
                "L6-2", f"发明内容 第{offset + i + 1}行", line.strip()[:60],
                f"有益效果光杆泛词 '{m.group(0)}'; 应与具体技术特征/对象逐项对应, 写明提升的是什么环节的什么指标(L6-2)",
            )


def check_problem_echo(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 26: 背景技术收口唯一 + 发明内容"以解决…"逐字呼应 (L3-1 / L6-1,
    原 content-auditor 语义项 2 的逐字呼应半边).

    背景技术须有且仅有一个"导致〔单一技术问题〕的(技术)?问题"收口 (L3-1 标准句式,
    技术问题唯一); full-draft 时发明内容"以解决…"句须逐字包含该收口原文 (实测三
    真实案件均为收口原文整段嵌入)。创新处与技术问题的语义对应仍归 content-auditor。
    """
    bg, _ = get_section_lines(lines, sections, "背景技术")
    if not bg:
        return
    collectors = list(dict.fromkeys(re.findall(r"导致[^。；，、]{2,60}的(?:技术)?问题", "".join(bg))))
    if not collectors:
        report.add(
            "L3-1", "背景技术", "".join(bg).strip()[:60],
            "背景技术缺标准收口句'……，导致〔单一技术问题〕的问题'(L3-1)",
        )
        return
    if len(collectors) > 1:
        report.add(
            "L3-1", "背景技术", " / ".join(c[:30] for c in collectors[:3]),
            f"背景技术出现 {len(collectors)} 个'导致…的问题'收口; 技术问题必须唯一(L3-1)",
        )
        return
    if stage != "full-draft":
        return
    fm, _ = get_section_lines(lines, sections, "发明内容")
    if not fm:
        return
    fm_text = "".join(fm)
    if "以解决" not in fm_text:
        report.add(
            "L6-1", "发明内容", fm_text.strip()[:60],
            "发明内容首段缺'以解决……问题'句(L6-1, 须与背景技术收口逐字呼应)",
        )
    elif collectors[0] not in fm_text:
        report.add(
            "L6-1", "发明内容", f"背景收口='{collectors[0][:40]}'",
            "发明内容'以解决…'句未逐字包含背景技术收口'导致…的问题'原文; 二者必须逐字呼应(L6-1/L3-1)",
        )


# -----------------------------------------------------------------------------
# 辅助: 决定扫描范围 (只扫说明书正文, 避开代码块/表格头)
# -----------------------------------------------------------------------------


def _get_scan_ranges(lines: list[str], sections: dict, stage: str) -> list[tuple[str, int, int]]:
    ranges: list[tuple[str, int, int]] = []
    for title, (start, end) in sections.items():
        # 跳过评分报告、审查报告等非正文; "附图设计"节为旧版手画流程遗留(现行附图由
        # render_patent_figure.py 从权要稿生成, figures.md L9), 旧案 md 中若存在仍跳过、不按交付正文扫描
        if any(x in title for x in ["评分报告", "审查报告", "元数据", "TODO", "附图设计", "供手画"]):
            continue
        ranges.append((title, start, end))
    return ranges


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------


def run_checks(md_path: Path, stage: str, claims_md: Path | None = None) -> Report:
    lines = load_md(md_path)
    sections = split_sections(lines)
    claims_text = claims_md.read_text(encoding="utf-8") if claims_md else ""
    report = Report(stage=stage, md_path=str(md_path))

    # 权要类检查仅在权利要求书章节存在时执行.
    # 分离式工作流的全文稿.md 不含权要 (冻结在权要稿.md, 已在 claims-draft 阶段过闸),
    # 此时跳过而非误报; 权要稿 (claims-draft) 必含该章节, 缺失照常报错.
    has_claims_section = any("权利要求书" in t for t in sections)
    if stage == "claims-draft" or has_claims_section:
        # Phase 1a: 字符/正则/字数类 (权要部分)
        check_claim1_length(lines, sections, report)
        check_claim1_step_count(lines, sections, report)
        check_each_claim_one_period(lines, sections, report)
        check_system_media_claim_no_debuzou(lines, sections, report)
        check_semicolon_line_ending(lines, sections, report)
        check_claim_numbering(lines, sections, report)
        check_total_claim_count(lines, sections, report)
        check_dependent_claim_no_yizhong(lines, sections, report)
        check_dependent_claim_reference(lines, sections, report)
        check_no_formula_in_claims(lines, sections, report)

    check_forbidden_words(lines, sections, report, stage)
    check_case_terms(lines, sections, report)
    check_background_length_and_paragraphs(lines, sections, report, stage)
    check_tech_field_single_paragraph(lines, sections, report, stage)

    # Phase 1b: 结构类
    check_section_order(lines, sections, report, stage)
    check_claims_draft_forbidden_sections(lines, sections, report, stage)

    # Phase 1c: 高误报风险
    check_noun_colon_definition(lines, sections, report, stage)
    check_latex_no_delimiter(lines, sections, report, stage)
    check_impl_no_stale_expansion(lines, sections, report, stage)
    check_include_lead_not_inline(lines, sections, report, stage)
    check_unicode_subscript_abuse(lines, sections, report, stage)
    check_double_punctuation(lines, sections, report, stage)
    check_full_draft_forbidden_quantifiers(lines, sections, report, stage, claims_text)
    check_abstract_length(lines, sections, report, stage)
    check_figure_numbering(lines, sections, report, stage)
    check_closing_boilerplate(lines, sections, report, stage)
    check_benefit_enumeration(lines, sections, report, stage)
    check_judgment_sentence_pattern(lines, sections, report, stage)
    check_substep_numbering(lines, sections, report, stage)
    check_benefit_generic_phrases(lines, sections, report, stage)
    check_problem_echo(lines, sections, report, stage)

    return report


def format_human_report(report: Report) -> str:
    if report.count() == 0:
        return f"[check_hard_rules] PASS  stage={report.stage}  file={report.md_path}\n"
    lines = [f"[check_hard_rules] FAIL  stage={report.stage}  violations={report.count()}"]
    for v in report.violations:
        lines.append(f"  - [{v.rule_id}] {v.location}")
        lines.append(f"      evidence: {v.evidence}")
        lines.append(f"      message : {v.message}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="第一类硬规则机械化检查.")
    parser.add_argument("--md", required=True, help="待审 md 草稿路径")
    parser.add_argument(
        "--stage", required=True,
        choices=["claims-draft", "full-draft"],
        help="当前阶段 (MVP 仅支持 claims-draft / full-draft)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="stdout 输出 JSON (给各路 auditor / 主 agent 消费)",
    )
    parser.add_argument(
        "--claims-md", default=None,
        help="权要基准 md (full-draft 阶段可选; 用于量词检查的权要原文复述豁免)",
    )
    args = parser.parse_args()

    md_path = Path(args.md)
    if not md_path.exists():
        print(f"[check_hard_rules] ERROR md not found: {md_path}", file=sys.stderr)
        return 2

    claims_path = Path(args.claims_md) if args.claims_md else None
    if claims_path and not claims_path.exists():
        print(f"[check_hard_rules] ERROR claims-md not found: {claims_path}", file=sys.stderr)
        return 2

    report = run_checks(md_path, args.stage, claims_path)

    if args.json:
        print(json.dumps({
            "stage": report.stage,
            "md_path": report.md_path,
            "violation_count": report.count(),
            "violations": [asdict(v) for v in report.violations],
        }, ensure_ascii=False, indent=2))
    else:
        print(format_human_report(report), file=sys.stderr)

    return report.count()


if __name__ == "__main__":
    sys.exit(main())

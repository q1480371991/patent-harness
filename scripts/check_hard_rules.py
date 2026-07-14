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
    """规则 6: 权要总数 <= 10 (L1-1)."""
    blocks = extract_claim_blocks(lines, sections)
    if len(blocks) > 10:
        report.add(
            "L1-1", "权利要求书",
            f"权要总数 = {len(blocks)}",
            f"权要总数超过 10 (实际 {len(blocks)})",
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
    """规则 18/19: 背景技术字数 270-350 / 段落数 2-3 (L3-1)."""
    if stage not in {"claims-draft", "full-draft"}:
        return
    body, offset = get_section_lines(lines, sections, "背景技术")
    if offset < 0:
        return
    text = "\n".join(body).strip()
    if not text:
        return
    n = count_chinese(text)
    if not (270 <= n <= 350):
        report.add(
            "L3-1", "背景技术",
            f"中文字数 = {n}",
            f"背景技术字数应在 270-350 之间 (实际 {n})",
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
    """规则 13: 章节标题存在且顺序正确 (L1-L8)."""
    if stage != "full-draft":
        return
    titles_in_order = []
    for title, (start, _) in sorted(sections.items(), key=lambda kv: kv[1][0]):
        for name in FULL_DRAFT_REQUIRED_SECTIONS_ORDER:
            if name in title:
                titles_in_order.append((name, start))
                break
    seen = [t for t, _ in titles_in_order]
    # 缺章节
    for name in FULL_DRAFT_REQUIRED_SECTIONS_ORDER:
        if name not in seen:
            report.add(
                "L1-L8 章节顺序", "全文稿",
                f"实际顺序 = {seen}",
                f"缺少章节: {name}",
            )
    # 顺序错
    idx_map = {name: i for i, name in enumerate(FULL_DRAFT_REQUIRED_SECTIONS_ORDER)}
    prev = -1
    for name in seen:
        cur = idx_map[name]
        if cur < prev:
            report.add(
                "L1-L8 章节顺序", "全文稿",
                f"实际顺序 = {seen}",
                f"章节顺序错误: {name} 出现在错误位置",
            )
            return
        prev = cur


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
    """规则 10: 名词冒号定义句式 (G5-1). L8-1 子步骤引导句 `步骤SxN：...` 是合法范式, 排除."""
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
    """规则 16: LaTeX 公式不带定界符 (G6-1)."""
    if stage != "full-draft":
        return
    for i, line in enumerate(lines):
        if re.search(r"\$\$|(?<![\\])\$", line):
            report.add(
                "G6-1", f"第{i + 1}行",
                line.strip()[:80],
                "LaTeX 公式不应带 $/$$ 定界符",
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


# -----------------------------------------------------------------------------
# 辅助: 决定扫描范围 (只扫说明书正文, 避开代码块/表格头)
# -----------------------------------------------------------------------------


def _get_scan_ranges(lines: list[str], sections: dict, stage: str) -> list[tuple[str, int, int]]:
    ranges: list[tuple[str, int, int]] = []
    for title, (start, end) in sections.items():
        # 跳过评分报告、审查报告等非正文
        if any(x in title for x in ["评分报告", "审查报告", "元数据", "TODO"]):
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
    check_full_draft_forbidden_quantifiers(lines, sections, report, stage, claims_text)
    check_abstract_length(lines, sections, report, stage)
    check_figure_numbering(lines, sections, report, stage)

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

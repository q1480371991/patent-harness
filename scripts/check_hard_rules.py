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
    # --- 以下仅 suspect 使用 (hard violation 留空), 唯一出处: 设计稿 §2.4 ---
    suspect_id: str = ""          # 稳定的探测器编号 (如 "S-W08-impl-opening")
    section: str = ""             # 规范化章节编号 (L1..L8); 未知章节不得产出 suspect
    owner: str = ""               # 唯一负责 auditor (global/impl/content/claims)
    missing_dimensions: list[str] = field(default_factory=list)  # 疑似缺失维度


@dataclass
class Report:
    stage: str
    md_path: str
    violations: list[Violation] = field(default_factory=list)
    suspects: list[Violation] = field(default_factory=list)

    def add(self, rule_id: str, location: str, evidence: str, message: str) -> None:
        self.violations.append(Violation(rule_id, location, evidence, message))

    def add_suspect(self, rule_id: str, location: str, evidence: str, message: str,
                    suspect_id: str = "", section: str = "", owner: str = "",
                    missing_dimensions: list[str] | None = None) -> None:
        """线索级: 不计 FAIL、不影响 exit code, 随 JSON 回传对应 auditor 逐条复核处置.

        新增结构化字段 (设计稿 §2.4 唯一路由): suspect_id/section/owner/
        missing_dimensions. owner 必须唯一确定; 未知章节或 owner 不唯一时调用方
        应改报结构抽取/路由错误 (report.add), 不得广播给多路 auditor (设计稿 §7).
        规则 27/28 为历史调用, 暂不带新字段 (其 owner 由契约固定为 impl).
        """
        self.suspects.append(Violation(
            rule_id, location, evidence, message,
            suspect_id=suspect_id, section=section, owner=owner,
            missing_dimensions=list(missing_dimensions or []),
        ))

    def suspect_manifest(self) -> dict[str, list[dict]]:
        """按 owner 分组的 suspect 路由清单 (设计稿 §5.5).

        主 agent 按此分发给各路 auditor; 每条 suspect 恰好出现在一个 owner 下.
        owner 为空的历史 suspect (规则 27/28) 归入 impl —— 与 impl-auditor 契约
        既有的"规则 27/28 必须逐条处置"条款一致.

        **本 manifest 是 suspect 的唯一出口** (顶层 `suspects` 已在 emit 层去除以
        省 token: 两者同源, 重复载荷实测占 JSON 26.6%)。故字段必须完整、不截断——
        `message` 是 auditor 的判定依据, `evidence` 是原文证据, 缺任一项都会让
        auditor 无从判断违规与豁免。
        """
        manifest: dict[str, list[dict]] = {"global": [], "impl": [], "content": [], "claims": []}
        for s in self.suspects:
            owner = s.owner or "impl"
            manifest.setdefault(owner, []).append({
                "suspect_id": s.suspect_id,
                "rule_id": s.rule_id,
                "section": s.section,
                "location": s.location,
                "evidence": s.evidence,
                "message": s.message,
                "missing_dimensions": s.missing_dimensions,
            })
        return manifest

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


def count_word_caliber(text: str) -> int:
    """Word「字数」口径: 汉字逐字各 1 + 连续英文单词各 1 + 连续数字串各 1 + 标点各 1.

    与 Word 状态栏「字数」(非「字符数」) 一致, 也是老板批注给字数区间时的口径。
    与 count_chars_incl_punct (字符数, 逐字符计) 的区别: 英文单词与数字串整体计 1,
    故 "PID" 计 1 而非 3。行内公式须在调用前剔除 —— DOCX 侧公式落在 OMML (m:t),
    不计入 Word 字数, md 侧的 `$..$` 若不剔除会虚高。
    """
    return (len(re.findall(r"[一-鿿]", text))
            + len(re.findall(r"[a-zA-Z]+", text))
            + len(re.findall(r"\d+", text))
            + len(re.findall(r"[^\w\s一-鿿]", text)))


def strip_for_word_count(text: str) -> str:
    """剔除不进 DOCX 正文字数的 md 构件: front-matter、md 标题行、行内/块公式.

    md 的 `## 章节名` 在 DOCX 里是章节标题段 (确实计入 Word 字数), 但各案标题集合
    固定 (五个章节共约 22 字), 剔除后总数系统性偏低约 20 字, 远小于区间余量; 保留
    则需区分 md 结构性标题与正文, 得不偿失。实测本案: 剔除后 md 合计 17554 字,
    DOCX 接受修订后实测 17486 字, 差 68 字 (0.4%)。
    """
    if text.startswith("---"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            text = text[end + 5:]
    text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    return re.sub(r"\$[^$]*\$", "", text)


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


# -----------------------------------------------------------------------------
# 章节规范化与 suspect 唯一路由 (设计稿 §2.4/§3.2; W46 按章节互斥路由的前置)
# -----------------------------------------------------------------------------

# 章节标题 → 规范化编号. suspect 的 section 字段与 owner 路由均以此为唯一映射表.
SECTION_NORM_MAP: dict[str, str] = {
    "权利要求书": "L1",
    "技术领域": "L2",
    "背景技术": "L3",
    "说明书摘要": "L4",
    "摘要附图": "L5",
    "发明内容": "L6",
    "附图说明": "L7",
    "具体实施方式": "L8",
}


def normalize_section(title: str) -> str | None:
    """章节标题 → 规范化编号 (L1..L8); 未知章节返回 None.

    未知章节意味着无法确定唯一 owner, 调用方必须改报结构抽取/路由错误
    (report.add), 不得把 suspect 广播给多路 auditor (设计稿 §7).
    "摘要附图" 必须先于 "说明书摘要" 之外的模糊匹配命中, 故按最长键优先匹配.
    """
    for key in sorted(SECTION_NORM_MAP, key=len, reverse=True):
        if key in title:
            return SECTION_NORM_MAP[key]
    return None


def suspect_owner_for_section(section_code: str | None) -> str | None:
    """规范化章节编号 → 唯一 auditor owner; 无法唯一确定时返回 None.

    W46 路由表 (设计稿 §3.2, 唯一按章节互斥路由的 suspect):
      L8 → impl; 其他说明书块 (L4/L5/L6/L7) → global.
    规则正文仍只有一个出处 (global.md G3-1), 执行路由由 section 决定;
    同一线索只由一路处置, 不重复计分 (scoring.md 路由例外条).
    """
    if section_code == "L8":
        return "impl"
    if section_code in ("L4", "L5", "L6", "L7"):
        return "global"
    return None


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

    例外: L8-1 收尾②号第二实施例系统套话的唯一出处原文即为**带冒号的单句**
    "本发明第二实施例提供了一种〔发明名称〕系统，包括：存储器、处理器及……的步骤。",
    与 L6-1 W05 发明内容侧(无冒号)写法不同源. 该固定套话不是子步骤展开段, 逗号连缀是
    骨架本身, 按骨架写反被本规则误判, 故精确豁免(须同时命中"实施例提供了一种"与
    "包括：存储器、处理器"), 不放宽对真正展开段的检查.
    """
    if stage != "full-draft":
        return
    for key in ("发明内容", "具体实施方式"):
        body, offset = get_section_lines(lines, sections, key)
        if offset < 0:
            continue
        for i, line in enumerate(body):
            s = line.strip()
            if "实施例提供了一种" in s and "包括：存储器、处理器" in s:
                continue  # L8-1 ②号固定套话骨架, 见 docstring 例外
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


def check_full_draft_length(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 (L8-1): 全文稿纯汉字字数下限 = 13000 (full-draft 阶段闸门).

    口径: 纯 CJK 汉字 (不含标点/数字/空白), 阈值留有余量 (经验上易写到 1.3 万,
    优质终稿 1.5–2 万)。低于下限 = hard FAIL, 阻断进 DOCX (字数不足在旧版是 2 级
    质量项、不阻断闸门, 是字数缩水的根因之一; 本条将其提为闸门前置)。

    统计范围: 全文稿全文 (权要三章冻结在权要稿.md, 不在此文件内, 故只统计算说明书
    各章节), 不剔 front-matter; front-matter 行数极少, 误差可忽略。
    """
    if stage != "full-draft":
        return
    text = "\n".join(lines)
    n = count_chinese(text)
    # 豁免: 非真实全文稿的短样例 (如单元测试 fixture、半成品草稿).
    # 真实全文稿必然含"具体实施方式"且远超 1000 字; 不足 1000 字的样例
    # 不适用本下限, 直接跳过, 避免误伤测试与中途草稿.
    if n < 1000:
        return
    if n < 13000:
        report.add(
            "L8-1", "全文稿",
            f"纯汉字字数 = {n}",
            f"全文稿纯汉字字数不足 (< 13000, 实际 {n}); 补足 S11–S15 解释段"
            "数据来源/工况/标定/示例细节至 ≥ 13000 字 (不引权外特征)",
        )


DRAFT_ROUND_BUDGET: dict[int, tuple[int, int]] = {
    1: (15000, 17000),          # 全文1稿: 双向区间, 留出返修补写余量
    2: (0, 20000),              # 全文2/3/4稿: 仅上限 (下限由纯汉字 13000 条守)
    3: (0, 20000),
    4: (0, 20000),
}


def check_full_draft_word_budget(md_path: Path, claims_md: Path | None, report: Report,
                                 stage: str, draft_round: int | None) -> None:
    """规则 (L8-1): 全文稿字数分稿次区间 —— 1稿 15000-17000, 2/3/4稿 <= 20000.

    口径 = Word「字数」(count_word_caliber), 统计范围 = 全文稿.md + 权要稿.md 合并。
    合并的理由: 交付 DOCX 同时含说明书与权利要求书三章 (技术领域/背景技术存放在
    权要稿.md), 老板在 Word 状态栏读到的是两者之和; 只按全文稿.md 判会系统性低估
    约 2600 字, 出现"md 达标而 DOCX 超标"。

    与既有纯汉字 13000 下限条 (check_full_draft_length) 分工: 那条守"写得够不够",
    只看说明书本体; 本条守"交付件是否落在老板给的区间", 按稿次给上限。

    draft_round 缺失时不判 (走 suspect), 与 --invention-name 同一处置口径: 该状态
    无法通过改稿消除, 计 violation 会致闸门死锁。
    """
    if stage != "full-draft":
        return
    body = strip_for_word_count(md_path.read_text(encoding="utf-8"))
    n_full = count_word_caliber(body)
    # 豁免: 非真实全文稿的短样例 (单元测试 fixture / 半成品草稿), 与下限条同口径.
    if n_full < 1000:
        return
    if draft_round is None:
        report.add_suspect(
            "L8-1", "全文稿", f"全文稿.md Word 口径字数 = {n_full}",
            "未传 --draft-round, 稿次字数区间校验未执行 (1稿 15000-17000 / "
            "2-4稿 <=20000); 该项记为未执行, 不得据此认为字数合规",
            suspect_id="S-L8-1-draft-round-missing", section="全文稿", owner="impl",
        )
        return
    if claims_md is None:
        report.add_suspect(
            "L8-1", "全文稿", f"全文稿.md Word 口径字数 = {n_full}",
            "未传 --claims-md, 无法合并权利要求书三章字数, 稿次字数区间校验未执行 "
            f"(仅说明书本体 {n_full} 字, 交付 DOCX 另含权要三章约 2600 字)",
            suspect_id="S-L8-1-claims-md-missing", section="全文稿", owner="impl",
        )
        return
    n_claims = count_word_caliber(strip_for_word_count(claims_md.read_text(encoding="utf-8")))
    total = n_full + n_claims
    lo, hi = DRAFT_ROUND_BUDGET.get(draft_round, (0, 20000))
    ev = f"Word 口径合计 = {total} (说明书 {n_full} + 权要三章 {n_claims})"
    if total > hi:
        report.add(
            "L8-1", f"全文{draft_round}稿", ev,
            f"交付字数超上限 (> {hi}, 实际 {total}); 按 L8-1 精简 S11-S15 解释段"
            "冗余展开/合并同源段落, 不得删可实施细节与权要步骤对应展开",
        )
    elif lo and total < lo:
        report.add(
            "L8-1", f"全文{draft_round}稿", ev,
            f"交付字数不足下限 (< {lo}, 实际 {total}); 补足 S11-S15 数据来源/工况/"
            "标定/示例细节 (不引权外特征)",
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
                "L8-1", f"具体实施方式 第{offset + i + 1}行", line.strip()[:60],
                f"子步骤编号残留 '{m.group(0)}'; 子步骤一律无编号, 在'包括：'后分号断行集中列举(L8-1, 1 级)",
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


# 规则 27 词表唯一出处: 同一技术实现路径上互斥的技术体系 (impl-auditor 语义项"技术
# 路径术语自洽"的机械探测词表; 新互斥体系一律在此登记, 契约只引用不复列).
MUTEX_TECH_SYSTEMS: list[tuple[str, list[str], str, list[str]]] = [
    ("数字调光/PWM 体系", ["数字调光", "PWM", "占空比", "数字信号链"],
     "模拟调流/线性体系", ["模拟调流", "电流镜像", "恒流线性", "模拟信号链"]),
]


def check_tech_system_mixing(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 27 (suspect 线索级): 互斥技术体系词共现探测 (L8-1 技术路径术语自洽).

    MUTEX_TECH_SYSTEMS 中一对互斥体系的词在具体实施方式内同时出现 → 出 suspect
    线索(附两侧命中词与行号), 由 impl-auditor 判定是否同一技术路径混用(合法的对比
    描述/背景引用可豁免)。时域/频域共现在信号处理案中常为合法变换关系, 不入词表。
    不计 FAIL、不影响 exit code。仅 full-draft。
    """
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "具体实施方式")
    if offset < 0:
        return
    text = "\n".join(body)
    for name_a, words_a, name_b, words_b in MUTEX_TECH_SYSTEMS:
        hit_a = [w for w in words_a if w in text]
        hit_b = [w for w in words_b if w in text]
        if hit_a and hit_b:
            loc_a = next(offset + i + 1 for i, l in enumerate(body) if any(w in l for w in hit_a))
            loc_b = next(offset + i + 1 for i, l in enumerate(body) if any(w in l for w in hit_b))
            report.add_suspect(
                "L8-1", f"具体实施方式 第{loc_a}行/第{loc_b}行",
                f"{name_a}:{hit_a} ↔ {name_b}:{hit_b}",
                "互斥技术体系词共现; impl-auditor 判定是否同一技术路径混用, 混用则给出应统一为的本领域公认技术",
            )


def check_model_detail_hints(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 28 (suspect 线索级): 模型四维度细节缺失探测 (L8-1 模型细节/G6-1 模型测度).

    具体实施方式出现"预设(的)xx模型"时, 按关键词探测四维度是否在章内有着落:
    训练数据(训练/样本/标注)、损失或目标(损失/目标函数)、使用方式(输入/输出)、
    终止条件(终止/收敛/迭代/轮次)。某维度零关键词命中 → 出 suspect 线索列出缺失
    维度, 由 impl-auditor 复核(关键词只探在场性, 不判"算够"; 不适用维度可豁免)。
    不计 FAIL、不影响 exit code。仅 full-draft。
    """
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "具体实施方式")
    if offset < 0:
        return
    text = "\n".join(body)
    models = list(dict.fromkeys(re.findall(r"预设的?([^，。；：\s]{1,14}模型)", text)))
    if not models:
        return
    dims = [
        ("训练数据", ["训练", "样本", "标注"]),
        ("损失/目标", ["损失", "目标函数"]),
        ("使用方式", ["输入", "输出"]),
        ("终止条件", ["终止", "收敛", "迭代", "轮次", "早停"]),
    ]
    missing = [name for name, kws in dims if not any(k in text for k in kws)]
    if missing:
        report.add_suspect(
            "L8-1", "具体实施方式",
            f"模型: {models[:3]}",
            f"模型细节四维度关键词缺失: {missing}; impl-auditor 复核是否公开不充分(不适用维度可豁免并注明理由)",
        )


# 规则 29 禁词表唯一出处: 说明书正文不得出现的权要专用体例措辞 (G5-1 说明书禁用
# 权要体例条; W18/W29/W30 三条批注合并为一项义务, 不写三个近义函数).
SPEC_FORBIDDEN_CLAIM_WORDINGS: list[tuple[str, str]] = [
    ("不在权利要求中",
     "删除该取舍元叙述, 直接写技术内容 (与 G5-1 AI 元叙述条同源, 本规则先命中不重复报)"),
    ("权利要求",
     "说明书不写'权利要求1至N所述的……'式引用; 系统/介质段改用说明书专用套话"
     "(唯一出处 full-draft.md L8-1 收尾条), 方法名用发明名称全称"),
    ("其特征在于",
     "说明书不写'其特征在于'(权要专用体例); 直接陈述特征内容"),
]


def check_spec_no_claims_wording(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 29: 说明书禁用权要体例措辞 (G5-1, W18/W29/W30 合并).

    说明书正文块不得出现权要专用体例: "权利要求"(含"权利要求1至8任一项"等引用
    形态)、"其特征在于"、"不在权利要求中……"式取舍元叙述.

    扫描边界: 只扫说明书正文章节 (发明内容/附图说明/具体实施方式/说明书摘要);
    权利要求书章节本身出现"其特征在于"是法定体例, 不适用; 评分报告/审查报告等
    非交付正文由 _get_scan_ranges 排除. 每行只报一次 (禁词表按特异性排序, 长词
    "不在权利要求中"先于"权利要求"命中), 避免同行多词重复计数. 仅 full-draft.
    """
    if stage != "full-draft":
        return
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        code = normalize_section(label)
        # 权要/技术领域/背景技术 (L1-L3) 冻结块不在本规则范围: L1 的"其特征在于"是法定体例
        if code in ("L1", "L2", "L3"):
            continue
        for i in range(start, end):
            for kw, advice in SPEC_FORBIDDEN_CLAIM_WORDINGS:
                if kw in lines[i]:
                    report.add(
                        "G5-1", f"{label} 第{i + 1}行", lines[i].strip()[:60],
                        f"说明书出现权要体例措辞'{kw}': {advice}",
                    )
                    break


def check_second_aspect_boilerplate(lines: list[str], sections: dict, report: Report,
                                    stage: str, claims_text: str = "") -> None:
    """规则 30: 第二方面系统复述段用固定套话 (L6-1, W05).

    发明内容存在系统/装置保护主题时, 第二方面系统复述段须直接套用固定计算机
    设备式段落、只替换案件变量:
      「第二方面，本发明提供一种〔系统名全称〕，包括存储器、处理器及存储在所述
      存储器上并可在所述处理器上运行的计算机程序，所述处理器执行所述计算机程序
      时实现如上所述的〔方法名全称〕。」

    检查: ①计算机设备式骨架(存储器/处理器/计算机程序); ②方法名用全称而非"第一方面
    所述方法"式简称(线索级, 交 content-auditor 语义复核).

    **不检查"的步骤"**: 说明书侧第二方面段固定套话本身带"的步骤"(与 L8-1 收尾套话②
    骨架一致); claims.md L1-1 的"不写'的步骤'"只约束权利要求书的系统/介质权收尾,
    由规则 2b 负责, 两侧口径不同源、勿交叉迁移.

    适用边界(避免对未采用该体例的稿件误判): 仅当发明内容**已出现"第二方面"
    锚点**时才校验其套话形态. 有系统权却整段缺失第二方面, 属"发明内容与权要
    一一对应"的完整性问题, 由 content-auditor 按 L6-1 判定, 不在本机械规则内
    —— 机械规则只在体例已采用时校验其正确性, 不强制体例选择. 仅 full-draft.
    """
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "发明内容")
    if offset < 0:
        return
    second_idx = next((i for i, ln in enumerate(body) if "第二方面" in ln), -1)
    if second_idx < 0:
        return  # 未采用"方面"体例, 本规则不适用

    line_no = offset + second_idx + 1
    # 第二方面段: 从锚点行起至下一个空行或段末 (套话通常单段)
    chunk_lines = []
    for ln in body[second_idx:]:
        if not ln.strip() and chunk_lines:
            break
        chunk_lines.append(ln)
    chunk = "".join(chunk_lines)

    # 判断本案是否有系统/装置保护主题 (claims_text 优先, 回退到本文权要块)
    claims_src = claims_text or "\n".join(
        ln
        for t in sections if "权利要求书" in t
        for ln in lines[sections[t][0]:sections[t][1]]
    )
    has_system = bool(re.search(r"一种[^，。；]{2,40}(系统|装置)[，。]", claims_src))

    # ①计算机设备式骨架
    if has_system and not re.search(r"包括存储器、处理器|包括：存储器、处理器", chunk):
        report.add(
            "L6-1", f"发明内容 第{line_no}行", chunk.strip()[:60],
            "第二方面系统段未用固定计算机设备式套话; 应为'包括存储器、处理器及存储在所述"
            "存储器上并可在所述处理器上运行的计算机程序，所述处理器执行所述计算机程序时实现…'",
        )
    # 注: 说明书侧的第二方面段固定套话**本身带"的步骤"**(与 L8-1 收尾套话②骨架一致),
    # 不校验该三字。claims.md L1-1 的"不写'的步骤'"只约束权利要求书的系统/介质权收尾
    # (由规则 2b check_system_media_claim_no_debuzou 负责), 两侧口径不同源、勿交叉迁移。
    # ②方法名简称 → 线索级, 交 content-auditor 语义复核
    if re.search(r"(第一方面所述方法|如上所述的方法(?!名))", chunk):
        report.add_suspect(
            "L6-1", f"发明内容 第{line_no}行", chunk.strip()[:60],
            "第二方面系统段疑似用'第一方面所述方法'式简称; 应写发明名称方法全称"
            "(如'一种基于反向视角验证的无人机融合定位方法'), content-auditor 复核确认或豁免",
            suspect_id="S-W05-aspect-name", section="L6", owner="content",
            missing_dimensions=["方法名全称"],
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


# 规则 31 槽位表唯一出处: docx-template.md G8-0b 的 **A 类槽位**(须写正式题名全称,
# 含"及系统/及装置"后缀; 这四处代表整件发明). B 类槽位(权要各条、第一/第二方面复述、
# 实施例引入句、图1附图说明、收尾"综上所述"段、第二实施例系统段、介质段)按保护主题
# 分别写方法名/系统名, 句式出处见 docx-template.md G8-2 与 full-draft.md L8-1 收尾条
# —— 在 B 类写入含"及系统"的全称反而产出"……方法及系统方法"式重复拼接, 故不入本表.
# 分节4首段发明名称属 DOCX 可见层, 由 verify_docx_injection.py 后验, 不在 md 层.
INVENTION_NAME_SLOTS: list[tuple[str, str]] = [
    (r"本发明的目的在于提供了?一种([^，。；]{4,60})", "发明内容 目的句"),
    (r"具体涉及一种([^，。；]{4,60})", "技术领域 句"),
    # (?<!综上所述，本发明) 排除收尾总结段 —— 该段属 B 类, 句式为"综上所述，本发明
    # 公开了一种〔权1保护主题〕"(方法名), 不填含"及系统"的正式全称.
    (r"(?<!综上所述，本发明)公开了一种([^，。；]{4,60})", "说明书摘要 句"),
]


def check_invention_name_slots(lines: list[str], sections: dict, report: Report,
                               stage: str, invention_name: str | None = None) -> None:
    """规则 31: 正式题名槽位逐字一致 (docx-template.md G8-0b, W35).

    正式发明题名在各复现槽位必须逐字一致, 含"及系统／及装置"等后缀.
    违规形态: 漏后缀、简称、变形、重复拼接.

    信源纪律(设计稿 §5.3): 题名由 --invention-name 显式传入, **不从权 1 主题
    (extract_structure.py SUBJECT_RE) 推导** —— 权 1 主题只含方法名, 推不出
    "及系统".

    **配置缺失 vs 稿件违规的通道分离(闸门死锁修复)**: 检出槽位但未传该参数时,
    走 **suspect 通道** 报"配置缺失", 不计 violation、不影响 exit code —— 因为
    该状态**无法通过改稿消除**, 计为 violation 会让"任一 FAIL 直接回修"的闸门
    纪律陷入死锁(稿子完全合规也过不了闸, 主 agent 要么空转改坏正确的题名句,
    要么跳过整个闸门失去机械前置保护). 稿件真违规(漏后缀/简称/变形/重复拼接)
    仍走 violation 通道硬拦。

    与规则 26 (check_problem_echo) 的边界: 规则 26 扫同一句的"以解决…"部分,
    本规则只判题名槽位部分, 两者不重复报同一问题. 仅 full-draft.
    """
    if stage != "full-draft":
        return
    # 只扫交付正文: _get_scan_ranges 排除评分报告/审查报告/元数据/TODO 等非正文节 ——
    # 审查报告在引述问题时常复述题名(如"摘要写'公开了一种xx方法'漏了'及系统'"),
    # 扫全文会把这类引述误判为槽位违规.
    hits: list[tuple[str, str, int]] = []  # (slot_label, found_name, line_no)
    for _label, start, end in _get_scan_ranges(lines, sections, stage):
        for i in range(start, end):
            for pat, slot_label in INVENTION_NAME_SLOTS:
                m = re.search(pat, lines[i])
                if m:
                    hits.append((slot_label, m.group(1).strip(), i + 1))
    if not hits:
        return  # 无题名槽位, 本规则不适用

    if not invention_name:
        # 配置缺失 ≠ 稿件违规: 走 suspect 通道, 不计 exit code, 不阻断闸门.
        report.add_suspect(
            "G8-0b", "全文稿(调用配置)",
            f"检出题名槽位 {len(hits)} 处: {hits[0][0]}第{hits[0][2]}行等",
            "**配置缺失, 非稿件违规**: 未传 --invention-name, 规则 31(G8-0b A 类槽位"
            "题名逐字一致)本轮未执行。请在调用命令补 --invention-name \"<正式题名全称>\""
            "(含'及系统/及装置'等后缀, 取自案件已确认元数据)后重跑; "
            "不得从权 1 保护主题推导后缀(设计稿 §5.3 信源纪律)。"
            "本条不可通过改稿消除, 故不计 FAIL —— 但该项校验缺失, 不得据此认为题名已合规",
            suspect_id="S-W35-name-input-missing", section="G8", owner="global",
            missing_dimensions=["--invention-name 参数"],
        )
        return

    name = invention_name.strip()
    name_body = name[2:] if name.startswith("一种") else name
    for slot_label, found, line_no in hits:
        if found == name_body:
            continue
        if name_body.startswith(found):
            detail = f"题名漏后缀'{name_body[len(found):]}': 应为'{name_body}', 实为'{found}'"
        elif found.startswith(name_body):
            detail = f"题名重复拼接: 应为'{name_body}', 实为'{found}'"
        else:
            detail = f"题名变形/简称: 应逐字写'{name_body}', 实为'{found}'"
        report.add(
            "G8-0b", f"{slot_label} 第{line_no}行", found[:60],
            f"{detail} (G8-0b 正式题名逐字一致, 含'及系统/及装置'后缀)",
        )


def _impl_body(lines: list[str], sections: dict) -> tuple[list[str], int]:
    """具体实施方式正文与其起始行号 (未找到返回 [], -1). 供 L8 类 suspect 复用."""
    return get_section_lines(lines, sections, "具体实施方式")


def check_impl_opening_tech_hints(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 32 (suspect): 实施方式开篇技术展开线索 (L8-1, W08).

    首个 Sxx 主步骤之前的开篇段只应写法律/结构套话与图导引句; 出现案件技术展开
    (设备构成与机制、参数示例值、公式) 即出线索, 由 impl-auditor 判定应否下沉到
    对应步骤解释段. 纯法律套话与图导引句不报. 仅 full-draft.
    """
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    first_sxx = next((i for i, ln in enumerate(body) if re.search(r"步骤S\d+|^S\d+，", ln.strip())), -1)
    if first_sxx <= 0:
        return  # 无 Sxx 或开篇为空
    # 技术展开特征: 具体数值+单位 / 器件构成句 / 公式号 / 示例值
    tech_pat = re.compile(
        r"\d+(\.\d+)?\s*(伏特|安培|瓦特|秒|毫秒|赫兹|摄氏度|%|米|毫米)"
        r"|包括[^，。；]{0,20}(电路|模块|单元|传感器)[^，。；]{0,20}(用于|连接)"
        r"|一个实施值|示例值|取值为"
    )
    for i in range(first_sxx):
        ln = body[i]
        if not ln.strip():
            continue
        if tech_pat.search(ln):
            report.add_suspect(
                "L8-1", f"具体实施方式 第{offset + i + 1}行", ln.strip()[:60],
                "实施方式开篇(首个 Sxx 之前)疑似出现案件技术展开; 开篇只写法律/结构套话与图导引句, "
                "技术细节应下沉到对应步骤解释段(W08). 纯套话可豁免",
                suspect_id="S-W08-impl-opening", section="L8", owner="impl",
                missing_dimensions=["技术展开位置"],
            )


# 规则 33 词表: 参与判断的定性状态词 (W11)
QUALITATIVE_STATE_WORDS = ["恒定", "下降", "上升", "平稳", "稳定", "异常", "退化", "波动"]


def check_qualitative_state_bounds(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 33 (suspect): 定性状态词双边界线索 (G6-1 定性状态词双边界, W11).

    定性状态词参与判断 (同句含"当…时/判定/确定…阶段/转为") 时, 须同时具备幅度
    边界 (数值+单位) 与时间/连续样本边界 ("连续N点/持续T秒"). 局部窗口 (命中行
    前后各 3 行) 内两类边界齐全即豁免, 不出线索. 仅背景描述不报. 仅 full-draft.
    """
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    judge_pat = re.compile(r"当[^，。；]{0,30}时|判定|确定[^，。；]{0,10}阶段|转为|视为")
    amp_pat = re.compile(r"\d+(\.\d+)?\s*(伏特|安培|瓦特|秒|毫秒|%|倍|个)|阈值|超过|小于|大于")
    dur_pat = re.compile(r"连续\s*\d+|持续\s*\d+|\d+\s*个?(采样点|采样周期|连续样本)|单点")
    # 状态词须作状态判定使用; 嵌在名词短语内 (如"采样异常记录"的"异常"、"波动指标"
    # 的"波动") 属对象命名的一部分, 不是参与判断的定性状态词, 剔除后再判以免误报.
    noun_ctx_pat = re.compile(r"异常记录|异常数据|异常样本|异常事件|波动指标|波动幅度|波动值|波动特征|退化状态标识|稳定变化限值")
    for i, ln in enumerate(body):
        if not any(w in ln for w in QUALITATIVE_STATE_WORDS):
            continue
        if not judge_pat.search(ln):
            continue  # 未参与判断, 不适用
        if not any(w in noun_ctx_pat.sub("", ln) for w in QUALITATIVE_STATE_WORDS):
            continue  # 状态词只是对象名的一部分, 非判断依据
        lo, hi = max(0, i - 3), min(len(body), i + 4)
        window = "\n".join(body[lo:hi])
        missing = []
        if not amp_pat.search(window):
            missing.append("幅度边界")
        if not dur_pat.search(window):
            missing.append("时间/连续样本边界")
        if missing:
            report.add_suspect(
                "G6-1", f"具体实施方式 第{offset + i + 1}行", ln.strip()[:60],
                f"定性状态词参与判断但局部窗口疑似缺{('与'.join(missing))}; "
                "须同时给幅度边界(数值+单位)与时间/连续样本边界(W11). 边界已在他处给出可豁免",
                suspect_id="S-W11-state-bounds", section="L8", owner="impl",
                missing_dimensions=missing,
            )


def check_calibration_sample_dims(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 34 (suspect): 标定样本四维度线索 (G6-1 标定样本四维度, W14).

    出现"标定/预先标定/历史数据确定"时, 须给全来源、纳排、数量、数量依据四项.
    局部窗口 (命中行前后各 5 行) 四项齐全即豁免. 仅 full-draft.
    """
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    trig_pat = re.compile(r"标定|由[^，。；]{0,20}历史[^，。；]{0,10}(数据|样本)[^，。；]{0,10}确定")
    dims = [
        ("样本来源", re.compile(r"同型号|同一型号|同功率|工况|历史切换|出厂|采集自")),
        ("纳排条件", re.compile(r"未记录|排除|剔除|经[^，。；]{0,10}检测|合格|完成[^，。；]{0,6}检测")),
        ("样本数量", re.compile(r"不少于\s*\d+|不低于\s*\d+|\d+\s*(次|组|个)(完整|历史|样本)?")),
        ("数量依据", re.compile(r"依据|理由|以保证|为使|满足[^，。；]{0,10}(置信|统计|稳定)|足以")),
    ]
    reported_lines = set()
    for i, ln in enumerate(body):
        if not trig_pat.search(ln):
            continue
        lo, hi = max(0, i - 5), min(len(body), i + 6)
        if any(x in reported_lines for x in range(lo, hi)):
            continue  # 同一窗口只报一次
        window = "\n".join(body[lo:hi])
        missing = [name for name, pat in dims if not pat.search(window)]
        if missing:
            reported_lines.add(i)
            report.add_suspect(
                "G6-1", f"具体实施方式 第{offset + i + 1}行", ln.strip()[:60],
                f"标定过程疑似缺维度: {missing}; 须给全样本来源、纳排条件、样本数量、数量依据"
                "四项方可复现(W14). 维度已在他处给出可豁免",
                suspect_id="S-W14-calibration", section="L8", owner="impl",
                missing_dimensions=missing,
            )


def check_vague_qualification_def(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 35 (suspect): 笼统资格定义线索 (L8-1 资格与状态定义须可测, W16).

    "健康/合格/有效/正常"等资格类对象的定义句以"满足…要求/符合…标准/性能良好"
    等笼统谓词收口, 且句内无量化指标 (数值+单位/阈值) 时出线索. 可测定义不报.
    仅 full-draft.
    """
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    def_pat = re.compile(r"(健康|合格|有效|正常|达标)[^，。；]{0,12}(是指|指的?是|定义为)")
    vague_pat = re.compile(r"满足[^，。；]{0,12}(要求|标准|规定)|符合[^，。；]{0,12}(标准|规范|要求)|性能良好|状态良好")
    quant_pat = re.compile(r"\d+(\.\d+)?\s*(伏特|安培|瓦特|秒|毫秒|%|兆欧|欧姆|摄氏度)|阈值|不低于\s*\d|不高于\s*\d|误差[^，。；]{0,8}\d")
    for i, ln in enumerate(body):
        if not def_pat.search(ln):
            continue
        # 定义句可能跨行, 取本行+后 2 行为判定窗口
        window = "\n".join(body[i:min(len(body), i + 3)])
        if vague_pat.search(window) and not quant_pat.search(window):
            report.add_suspect(
                "L8-1", f"具体实施方式 第{offset + i + 1}行", ln.strip()[:60],
                "资格/状态定义疑似以笼统谓词收口而无量化指标; 每项判定条件须可测量可复核"
                "(给检测项、量化指标、判定阈值或范围)(W16). 已有量化指标可豁免",
                suspect_id="S-W16-vague-def", section="L8", owner="impl",
                missing_dimensions=["可测量化指标"],
            )


def check_multisource_schema(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 36 (suspect): 多源拼接 schema 线索 (L8-1 多源特征拼接须公开 schema, W20).

    多源数据经"拼接/融合/串接/沿特征维度组合"形成数据集/矩阵/向量时, 须公开
    字段清单、列顺序、总维数三项. 局部窗口 (命中行前后各 4 行) 三项齐全即豁免.
    仅 full-draft.
    """
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    trig_pat = re.compile(r"(拼接|融合|串接|组合)[^。；]{0,20}(得到|形成)[^。；]{0,16}(数据集|矩阵|向量|序列)")
    dims = [
        ("字段清单", re.compile(
            r"(包括|按照|其中)[^。；]{0,80}(电流|电压|占空比|温度|功率|频率|转速|压力|电阻|流量)"
            r"[^。；]{0,60}(、|和|以及)[^。；]{0,60}"
            r"(电流|电压|占空比|温度|功率|频率|转速|压力|电阻|流量)")),
        ("列顺序", re.compile(r"在前|在后|依次|顺序[^，。；]{0,10}(排列|拼接|组合)|第[一二三四五六七八九十\d]+列")),
        ("总维数", re.compile(r"共\s*\d+\s*(维|列)|总维数|维数为\s*\d+|n\s*为\s*\d+|\d+\s*维")),
    ]
    for i, ln in enumerate(body):
        if not trig_pat.search(ln):
            continue
        lo, hi = max(0, i - 4), min(len(body), i + 5)
        window = "\n".join(body[lo:hi])
        missing = [name for name, pat in dims if not pat.search(window)]
        if missing:
            report.add_suspect(
                "L8-1", f"具体实施方式 第{offset + i + 1}行", ln.strip()[:60],
                f"多源拼接疑似缺 schema 维度: {missing}; 须公开各源具体字段、拼接列顺序与总维数"
                "(不得以'运行状态数据'等统称代替)(W20). 已在他处公开可豁免",
                suspect_id="S-W20-concat-schema", section="L8", owner="impl",
                missing_dimensions=missing,
            )


def check_trivial_arithmetic_formula(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 37 (suspect): 初等算术公式线索 (G6-1 显而易见初等算术, W26).

    极保守识别: 独立成段的公式行仅含两个已知量的一次减法或除法 (形如 A = B - C
    或 A = B / C), 无函数、求和、上下标叠加、矩阵、条件分段. 命中即出线索, 由
    impl-auditor 判断可否改用操作性文字表达. 任何复杂形态一律不报. 仅 full-draft.
    """
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    complex_pat = re.compile(r"\\(frac|sum|int|sqrt|exp|log|min|max|left|begin)|\^|_\{|\||≥|≤|\\geq|\\leq")
    simple_pat = re.compile(r"^\s*[A-Za-z一-龥]{1,12}\s*=\s*[A-Za-z一-龥]{1,12}\s*[-/]\s*[A-Za-z一-龥]{1,12}\s*$")
    for i, ln in enumerate(body):
        s = ln.strip()
        if not s or complex_pat.search(s):
            continue
        if simple_pat.match(s):
            report.add_suspect(
                "G6-1", f"具体实施方式 第{offset + i + 1}行", s[:60],
                "疑似显而易见的二元初等算术单独列为公式段; 此类运算优先用操作性文字表达"
                "('计算 A 与 B 的差值，得到 C')(W26). 确需公式的复杂关系可豁免",
                suspect_id="S-W26-trivial-formula", section="L8", owner="impl",
                missing_dimensions=["文字化表达"],
            )


def check_negative_only_action(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 38 (suspect): 纯否定动作线索 (G3-1 正向动作—输出闭合, W46).

    否定谓语 (不执行/不生成/不参与/不判断/不再等) 收束且句内无正向动作或输出时
    出线索. 合法否定分支 (作触发条件、作范围限定) 由 auditor 豁免.
    另含对比句模式 (W46 实判, 2026-08-02): "不新增/不引入/不另设/不使用…，而是…"
    否定前导即使后接正向动作也出线索, 不适用正向豁免.

    唯一按章节互斥路由的 suspect (设计稿 §3.2): section=L8 → impl; 其他说明书块
    (L4/L5/L6/L7) → global. 未知章节 → 报结构抽取/路由错误 (add), **不广播给多路
    auditor** (设计稿 §7). 仅 full-draft.
    """
    if stage != "full-draft":
        return
    neg_pat = re.compile(r"不(执行|生成|参与|判断|再|进行|输出|触发|计算|采集)")
    # 正向动作: 否定词之外另有实质动作产出.
    # (?<!不) 排除"不生成预警指令"中的"生成"—— 该动词本身正被否定, 不构成正向动作.
    pos_pat = re.compile(r"(?<!不)(得到|输出|生成|执行|计算|确定|记录|发出|写入|存储|标记)[^，。；]{1,}")
    # 对比句模式 (W46 实判, 2026-08-02): "不新增/不引入/不另设/不使用…，而是…" 否定前导+对比结构.
    # 王工口径更严: 即使"而是"后为正向动作, 句首否定前导也应删后直写动作 (X2607024: 划删
    # "本实施方式不新增独立的风险判断阈值，而是"并批"直接写操作"). 该模式不适用 pos_pat 豁免.
    contrast_pat = re.compile(r"不(新增|引入|另设|使用|设置|增加|采用|单独|重复)[^，。]{0,24}，而是")
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        code = normalize_section(label)
        if code in ("L1", "L2", "L3"):
            continue  # 权要/技术领域/背景技术不在说明书正文 W46 范围
        owner = suspect_owner_for_section(code)
        for i in range(start, end):
            ln = lines[i]
            if not (neg_pat.search(ln) or contrast_pat.search(ln)):
                continue
            contrast_hit = bool(contrast_pat.search(ln))
            if pos_pat.search(ln) and not contrast_hit:
                continue  # 同句已有正向动作且非对比句, 属合法否定分支
            if owner is None:
                report.add(
                    "G3-1", f"{label} 第{i + 1}行", ln.strip()[:60],
                    f"检出否定式表述, 但章节'{label}'无法规范化为已知编号, 无法确定唯一 auditor 路由; "
                    "请先修复章节结构后重跑(设计稿 §7); 本条不广播给多路 auditor",
                )
                continue
            msg = (
                "疑似'不X，而是Y'否定前导+对比结构; 即使'而是'后为正向动作, 否定前导"
                "也应删除后直写正向动作, 不适用正向豁免 (W46 实判, X2607024)"
                if contrast_hit else
                "疑似纯否定表述(否定谓语收束、未给正向动作或输出); 按 G3-1 改写为"
                "'对X做Y得到Z'(W46). 合法否定分支(触发条件/范围限定)可豁免, 须给上下文证据"
            )
            report.add_suspect(
                "G3-1", f"{label} 第{i + 1}行", ln.strip()[:60],
                msg,
                suspect_id="S-W46-negative-only", section=code, owner=owner,
                missing_dimensions=["正向动作或输出"],
            )


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------


def run_checks(md_path: Path, stage: str, claims_md: Path | None = None,
               invention_name: str | None = None,
               draft_round: int | None = None) -> Report:
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
    check_full_draft_length(lines, sections, report, stage)
    check_full_draft_word_budget(md_path, claims_md, report, stage, draft_round)
    check_figure_numbering(lines, sections, report, stage)
    check_closing_boilerplate(lines, sections, report, stage)
    check_benefit_enumeration(lines, sections, report, stage)
    check_judgment_sentence_pattern(lines, sections, report, stage)
    check_substep_numbering(lines, sections, report, stage)
    check_benefit_generic_phrases(lines, sections, report, stage)
    check_problem_echo(lines, sections, report, stage)
    check_spec_no_claims_wording(lines, sections, report, stage)
    check_second_aspect_boilerplate(lines, sections, report, stage, claims_text)
    check_invention_name_slots(lines, sections, report, stage, invention_name)
    # suspect 线索级 (不计 FAIL, 回传 auditor 复核)
    check_tech_system_mixing(lines, sections, report, stage)
    check_model_detail_hints(lines, sections, report, stage)
    # 新增 7 个探测器 (设计稿 §5.4; 均不计 FAIL、不影响 exit code)
    check_impl_opening_tech_hints(lines, sections, report, stage)      # W08
    check_qualitative_state_bounds(lines, sections, report, stage)     # W11
    check_calibration_sample_dims(lines, sections, report, stage)      # W14
    check_vague_qualification_def(lines, sections, report, stage)      # W16
    check_multisource_schema(lines, sections, report, stage)           # W20
    check_trivial_arithmetic_formula(lines, sections, report, stage)   # W26
    check_negative_only_action(lines, sections, report, stage)         # W46

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
    parser.add_argument(
        "--invention-name", default=None,
        help="本案正式发明题名全称(含'及系统/及装置'等后缀, 如'一种基于反向视角验证的无人机融合定位方法及系统')。"
             "full-draft 阶段用于 G8-0b 题名槽位逐字比对; 检出槽位却未传时"
             "走 suspect 通道报'配置缺失'(suspect_id=S-W35-name-input-missing), "
             "不计 violation、不阻断闸门(该状态无法通过改稿消除, 计入会致闸门死锁), "
             "该项校验记为未执行、不得据此认为题名合规; 不从权 1 推导(设计稿 §5.3)",
    )
    parser.add_argument(
        "--draft-round", type=int, default=None,
        choices=[1, 2, 3, 4],
        help="当前全文稿稿次 (1/2/3/4)；不传则稿次字数区间校验不执行。"
             "1稿 = 双向区间 15000-17000 (Word 口径)，2-4稿 = 仅上限 20000",
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

    report = run_checks(md_path, args.stage, claims_path, args.invention_name, args.draft_round)

    if args.json:
        # 注: 不输出顶层 `suspects` —— 它与 `suspect_manifest` 同源 (后者是按 owner
        # 分组的完整投影), 两份并列会让重复载荷占 JSON 26.6%; 而 SKILL.md:97 要求
        # 脚本 JSON 全文内嵌进**每一路** auditor prompt, 重复代价随并行路数放大。
        # suspect 的唯一出口是 suspect_manifest.<owner>; suspect_count 保留作总数校验。
        print(json.dumps({
            "stage": report.stage,
            "md_path": report.md_path,
            "violation_count": report.count(),
            "violations": [asdict(v) for v in report.violations],
            "suspect_count": len(report.suspects),
            "suspect_manifest": report.suspect_manifest(),
        }, ensure_ascii=False, indent=2))
    else:
        print(format_human_report(report), file=sys.stderr)

    return report.count()


if __name__ == "__main__":
    sys.exit(main())

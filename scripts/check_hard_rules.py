#!/usr/bin/env python3
"""
硬规则机械化检查脚本 (第一类).

用法:
    python scripts/check_hard_rules.py --md docs/权要稿.md --stage claims-draft
    python scripts/check_hard_rules.py --md docs/全文稿.md --stage full-draft

Exit code = 违反的硬规则数量; 0 = 全通过.

输出 JSON 到 stdout (方便各路 auditor / 主 agent 消费), 报告到 stderr.

★ 「规则 NN」编号体系 (必读, 防止跨系统串号):
  本脚本每条检查的编号只在本脚本内有效, 与规则文件的 G/L 章节号、W 号、A 号、X 号
  互不相干 (例: 本脚本的「规则 48」与「W48」无关; 「规则 41」是 W55 首现定义,
  不是全文字数条)。编号**按增设顺序递增、不复用**, 惯例是「有号者皆被规则或文档
  按号引用过」——未被引用的检查不设号 (全文字数两项即无号, 一律按口径指:
  「L8-1 字数条」)。**新增检查发号前先在本文件 grep 最大号、避开已用号。**
  唯一出处: `rules.md`「编号体系」节。
"""

from __future__ import annotations

import argparse
import json
import re
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
import boilerplate  # 模板句唯一副本 (规则 47)
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

# 权要稿禁写章节 (SKILL.md 权要一稿 step 5: 权要稿.md 只写权要三章;
# 直写全文稿在同轮产出 权要稿.md 时同守此界)
CLAIMS_DRAFT_FORBIDDEN_SECTIONS = [
    "说明书摘要", "摘要附图", "发明内容", "附图说明",
    "具体实施方式", "说明书附图",
]

# 全文稿正文章节顺序 (L4/L7 abstract-figures.md, L6 invention-content.md, L8 implementation.md;
# 权利要求书/技术领域/背景技术写在权要稿.md, 不在全文稿)
FULL_DRAFT_REQUIRED_SECTIONS_ORDER = [
    "说明书摘要", "摘要附图", "发明内容", "附图说明", "具体实施方式",
]

# 说明书禁用数量词 (G6-1)
FULL_DRAFT_FORBIDDEN_QUANTIFIERS = ["若干个", "多个"]

# 权要 1 主步骤硬上限 (L1-1; 规则 1b)。王工 2026-09-10 H2609029 口径「最多 6 步」。
CLAIM1_MAX_MAIN_STEPS = 6

# 权要 1 中文字数硬上限 (L1-1; 规则 1)。上限史: 400 → 2026-09-21 按王工 H2609100 口径
# 「权1最多不超过600」放宽为 600——该案王工要求两个创造性分句在权 1 内各写出子步骤
# (「创造性步骤 3-4 行左右」), 400 字放不下; 放宽的是**上限**, 仍以「说清楚」为先,
# 不为凑字数灌水。
CLAIM1_MAX_CHARS = 600

# 收尾装置/系统示意性说明段锚点 (docx-template.md G8-2 模板固定套话)
# 「需要说明的是，以上所描述的…实施例仅仅是示意性的，其中所述作为分离部件说明的
# 单元可以是或者也可以不是物理上分开的，…分布到多个网络单元上。…」
# 该段为模板法定套话 (王工 H2608165 定稿亲手保留版), 含「可以」「多个」等禁词字面——
# 禁词/数量词扫描对其整行豁免。H2609029 实测教训: 1稿曾为过闸门删段, 属闸门误报
# 引发的错误决策 (套话报警不删段, 修闸门不修稿)。锚点取段内独有短语
# 「实施例仅仅是示意性」, 正常正文不会命中。
BOILER_INDICATIVE_ANCHOR = "实施例仅仅是示意性"

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
    """规则 1: 权要 1 中文字数 <= 600 (L1-1, claims-format-standard)."""
    blocks = extract_claim_blocks(lines, sections)
    if 1 not in blocks:
        report.add("L1-1", "权利要求书", "-", "未找到权要 1")
        return
    start, end = blocks[1]
    text = "\n".join(lines[start:end])
    n = count_chinese(text)
    if n > CLAIM1_MAX_CHARS:
        report.add(
            "L1-1", f"权利要求书 第{start + 1}行起",
            f"权要 1 中文字数 = {n}",
            f"权要 1 中文字数超限 (>{CLAIM1_MAX_CHARS}, 实际 {n})",
        )


def check_claim1_step_count(lines: list[str], sections: dict, report: Report) -> None:
    """规则 1b: 权要 1 主步骤最多不超过 6 个 (L1-1 硬上限; 3-5 个为宜属建议口径不在此报).

    上限史: 初版 6 → 2026-08-15 收紧为 5 → 2026-09-10 按王工 H2609029 口径「最多 6 步」放回 6
    (该案权 1 末步一步串 7 个子动作被判臃肿, 王工指示拆成第 6 步; 上限不是越紧越好,
    过紧会把多个子动作挤进一步)。

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
    if n_steps > CLAIM1_MAX_MAIN_STEPS:
        report.add(
            "L1-1", f"权利要求书 第{start + 1}行起",
            f"权要 1 主步骤数 = {n_steps}",
            f"权要 1 主步骤超过硬上限 {CLAIM1_MAX_MAIN_STEPS} 个 (实际 {n_steps}), 应合并同一技术链上的连续动作或将细节下沉从属权要",
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
    """规则 2b: 系统/装置独权、存储介质权末尾不写'的步骤'三字 (L1-1).

    系统/介质权末尾一律以句号收口, 即'……任一项所述的方法。',
    不写'……任一项所述的方法的步骤。'。

    ★ 口径已扩展 (王工 2026-08-28 原话「'的步骤'三个字全文去掉」): 本规则仍只在
    权要侧精确报错 (指名是哪一条权要), full-draft 阶段的说明书正文由
    `check_spec_no_debuzou` (规则 46) 全文扫描 —— 两者分工不重叠。

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
                f"('……任一项所述的方法。' 而非 '……的方法的步骤。'); "
                f"请删除权 {num} 末尾 '的步骤' 三字 (王工 2026-08-28「'的步骤'三个字全文去掉」)",
            )


# 规则 46 豁免表唯一出处: 说明书正文中含"步骤"但**不属**违规形态的合法表述.
# 王工口径是删掉引用方法时的收尾三字"…所述的方法的步骤", 不是禁用"步骤"一词 ——
# L8-1 收尾套话③原文即"用于执行上述实施例的一种〔发明名称〕方法的**所有流程步骤**"
# (五案定稿全部保留), 以及"在…的步骤中"式叙述, 均合法.
_DEBUZOU_EXEMPT_RE = re.compile(r"所有流程步骤|流程步骤|的步骤中|的步骤，采用|的步骤时")


def check_spec_no_debuzou(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 46 (1级 hard): 说明书正文不写'的步骤' (L1-1 / 王工 2026-08-28 全文口径).

    王工原话「'的步骤'三个字**全文**去掉」+ H2608040 全文审核v1 批注「'的步骤'三个
    字，对应从模版中删除」并亲手删 3 处。

    ★ **本规则推翻了 skill 此前的"两侧不同源"表述**: `invention-content.md` L6-1 与
    本文件规则 30 原注释均写"说明书侧固定套话本身带'的步骤'、勿据权要侧口径删去"。
    **五案定稿接受修订态实测 (直读 word/document.xml 剔 w:del) 「的步骤」全部为 0**
    (X2607040/X2607043/X2607134/H2608040/X2608107), 该表述无实测支撑、已废止。

    合法豁免见 `_DEBUZOU_EXEMPT_RE`: 收尾套话③的"所有流程步骤"是骨架原文 (五案定稿
    全部保留), "在…的步骤中"式叙述亦非违规形态 —— 王工删的是**引用方法时的收尾三字**
    ("…所述的方法的步骤"), 不是禁用"步骤"一词。

    只扫说明书正文块 (权利要求书由规则 2b 精确报错; 交底书不在 md 交付物内). 仅 full-draft.
    """
    if stage != "full-draft":
        return
    for title, start, end in _get_scan_ranges(lines, sections, stage):
        if "权利要求书" in title:
            continue  # 权要侧归规则 2b
        for i in range(start, end):
            s = lines[i].strip()
            if "的步骤" not in s:
                continue
            probe = _DEBUZOU_EXEMPT_RE.sub("", s)
            if "的步骤" not in probe:
                continue  # 全部命中豁免形态
            report.add(
                "L1-1", f"{title} 第{i + 1}行", s[:70],
                "说明书正文出现'的步骤' —— 王工 2026-08-28「'的步骤'三个字全文去掉」; "
                "引用方法处写'实现如上述所述的方法。'(不带'的步骤'、不带发明名称全称)。"
                "合法例外仅收尾套话③的'所有流程步骤'与'在…的步骤中'式叙述",
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
    """规则 6: 权要总数必须 = 10 (L1-1, claims-requirements.md '必须写满十条')."""
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


def check_no_specific_values_in_claims(lines: list[str], sections: dict, report: Report) -> None:
    """规则 8b: 权要正文禁写具体技术数值 (L1-1, 王工口径 X2608024).

    限缩保护范围的具体数值——度量值+单位、标准编号、比例/百分比、数量/计数限定
    (含"最近N个"式窗口)——一律上位化为"预设xx"或下沉说明书实施例.
    权利要求编号与从属引用不属违规, 先剔除再检测.
    """
    blocks = extract_claim_blocks(lines, sections)
    # 合法剔除: 行首编号、从属引用 (权利要求1至9 / 权利要求1所述 / 根据权利要求1所述)
    legal_re = re.compile(
        r"^\s*\d+\s*\.|权利要求\s*\d+\s*至\s*\d+|权利要求\s*\d+\s*所述|根据权利要求\s*\d+\s*所述"
    )
    # 技术数值: 数字+单位/量词/百分号、"最近N个"式窗口、标准编号前缀
    value_re = re.compile(
        r"\d+(?:\.\d+)?\s*(?:dBm|mV|kV|mA|mW|kHz|MHz|GHz|Mbps|Gbps|Kbps|μs|ms|ns|dB|V|A|W|Hz|%|秒|分钟|小时|天|月|年|米|mm|cm|nm|km|次|帧|芯|路|个|bit|Byte|字节)"
        r"|最近\s*[0-9Nn]\s*个"
        r"|(?:IEEE|TIA|EIA|Cat|ISO|GB|ITU)\s*[/A-Za-z-]*\s*\d+(?:\.\d+)*"
    )
    for num, (start, end) in blocks.items():
        for i in range(start, end):
            line = legal_re.sub("", lines[i])
            if not line.strip():
                continue
            m = value_re.search(line)
            if m:
                report.add(
                    "L1-1", f"第{i + 1}行", lines[i].strip()[:80],
                    f"权要 {num} 内出现疑似具体技术数值 '{m.group(0)}' —— 权要禁写限缩保护范围的具体数值"
                    f"(王工口径 X2608024), 改为'预设xx'上位表达或下沉说明书实施例",
                )
                break


# 规则 43 量词表唯一出处: 权要内「预设对象」名称的收尾量词 (claims-requirements.md L1-1「预设对象总量 ≤5」).
#
# ⚠️ **前缀必须贪婪 `{0,8}`, 不能用惰性 `{0,8}?`** —— 这是本规则实测踩到的坑
# (五案回归实测, 2026-08-28): 惰性前缀会让**位置更靠前的短量词**优先命中, 把长名字
# 截短, 且"长量词排前面"救不了 (那只在同一起始位置有效)。实测三例:
#   `预设需求权重映射表` → 惰性截成 `预设需求权重`  (`权重` 抢在 `映射表` 之前)
#   `预设浓度映射模型`   → 惰性截成 `预设浓度`      (`浓度` 抢在 `模型` 之前)
#   `预设深度阈值区间`   → 惰性截成 `预设深度`      (`深度` 抢在 `阈值区间` 之前)
# 截短会让两个不同对象归并成一个 → **under-count, 是本闸门唯一危险的错误方向**
# (X2608107 惰性下只数出 13 个, 贪婪下 15 个, 定稿实测 16 个; 基准见
#  tests/regression/regress_preset_budget.py 的 EXPECT)。
# 贪婪从最长前缀开始回退, 先撞上最靠后的量词, 自然得到完整名字。
#
# ⚠️ 名字内部禁含 `所述` 与 `的` —— 二者都标志已跨到下一个语法成分:
#   `所述` 是回指词, 其后的量词属于别的对象。实测 `预设像素距离与预设纹理方向统计
#   所述基准灰度图像` 若不禁, 贪婪会切出 `预设纹理方向统计所述基准`(吞掉动词与回指)。
#   `的` 是所属关系, 其后是该对象的某个部分而非新对象。实测 `预设波动阈值的差值`
#   须归入 `预设波动阈值`、`预设深度阈值区间的下限` 须归入 `预设深度阈值区间` ——
#   不禁则 over-count(同一对象被数成两三个)。
_PRESET_NOUN_TAIL = (
    # ① 多字复合词 (同起点时长优先; 不放案件专有名, 只放跨案通用复合形态)
    "单幅采集分辨率|金字塔层数|基准碱浓度|阈值区间|对照关系|换算关系|映射关系"
    "|元素尺寸|网格尺寸|显示尺寸|采样周期|采样窗口|剪切速率|空间分辨率|分辨率"
    "|映射表|映射模型|案例库|波动基准|长短期记忆网络|卷积神经网络|神经网络"
    # ② 通用名词
    "|阈值|基准|权重|容差|区间|周期|窗口|时长|频率|速率|浓度|温度|压力|角度|半径"
    "|深度|高度|长度|面积|体积|密度|增量|步长|尺寸|数量|距离|轮数|层数|差值|系数"
    "|比例|宽度|间距|范围|顺序|下限|上限|地图|模型|网络|矩阵|向量|序列|集合|表格"
    "|关系|模式|策略|规则|标识|编码|格式|配置|参数|条件|标准|基线|门限|等级|档位"
    "|方向|方式|数据库|库|表|图谱|字典|清单|列表"
)
_PRESET_OBJ_RE = re.compile(
    r"预设(?:的)?((?:(?!所述|的)[一-鿿]){0,8}(?:" + _PRESET_NOUN_TAIL + r"))")
# 名字尾部误吞的动词 (惰性量词偶会把紧随动词并入, 同 check_preset_params.py)
_PRESET_TAIL_VERB_RE = re.compile(
    r"(映射|匹配|比对|统计|换算|求和|叠加|修正|判定|计算|采集|归一化)$")
_PRESET_BUDGET_MAX = 5


def check_claims_preset_budget(lines: list[str], sections: dict, report: Report) -> None:
    """规则 43 (1级 hard): 权要内「预设对象」distinct 总量 ≤5 (claims-requirements.md L1-1, 王工 2026-08-21).

    王工原话: 「预设的东西也不能用太多, 虽然没有明确规定数量, 但整个权要里面最好
    不超过 4-5 个吧, 不然显得整个方案像空中楼阁, 而且也会导致说明书要用大量篇幅
    来解释怎么预设」。四案定稿水位 0/4/6/6, X2608107 我的 1 稿 17 个被点名为
    「最大的问题」。

    **数 distinct 对象, 不数出现次数** —— 同一对象被多条权要引用只算 1 个。

    ★ 与「模型类另走模型展开清单、不计入本预算」这一主张的分歧 (本脚本有意不采纳, 已报用户): 该主张
    建议 `预设××模型／网络` 不计入本预算 (理由是它走模型四要素与四维度测度)。本规则**照计入** ——
    模型展开清单/阈值槽位管的是"每个对象要解释到什么程度"(槽位表选哪张), 本规则管的是"一共有
    几个对象"(总量), 两者不同维; 且王工原话是"预设的东西"不设例外, H2608165 我的
    1 稿也是把 `预设姿态分类模型` 计入后得 4 个。

    **覆盖率兜底**: 量词表必然不全, 未归类的 `预设` 出现处按其后 6 字上下文去重后
    计入"疑似对象", 仅当 归类数 ≤5 而 归类数+疑似数 >5 时才报 —— 宁可让人确认一次,
    不静默放行 (under-count 是本闸门唯一危险的错误方向)。
    """
    body, offset = get_section_lines(lines, sections, "权利要求书")
    if offset < 0:
        return
    claims_text = "\n".join(body)
    objs: dict[str, int] = {}
    spans: list[tuple[int, int]] = []
    for m in _PRESET_OBJ_RE.finditer(claims_text):
        name = "预设" + _PRESET_TAIL_VERB_RE.sub("", m.group(1))
        objs[name] = objs.get(name, 0) + 1
        spans.append((m.start(), m.end()))
    # 未被归类的 `预设` 出现处 (量词表未覆盖)
    unclassified: dict[str, int] = {}
    for m in re.finditer(r"预设", claims_text):
        if any(s <= m.start() < e for s, e in spans):
            continue
        ctx = claims_text[m.start():m.start() + 8].replace("\n", "")
        unclassified[ctx] = unclassified.get(ctx, 0) + 1
    n, u = len(objs), len(unclassified)
    listing = "、".join(f"{k}×{v}" for k, v in objs.items())
    if n > _PRESET_BUDGET_MAX:
        report.add(
            "L1-1", "权利要求书",
            f"distinct 预设对象 {n} 个: {listing}",
            f"权要内「预设」对象 distinct {n} 个, 超上限 {_PRESET_BUDGET_MAX} "
            "(claims-requirements.md L1-1, 王工 2026-08-21「整个权要里面最好不超过 4-5 个」)。"
            "四条消解通路: ①基础档步骤整条不写从权(写从权=引进预设对象); "
            "②基准/初值类改实测(`预设初始××基准`→`在××时刻采集的初始××基准`); "
            "③隐含参数不点名(采样周期/窗口/权重); ④同一映射的相邻两步合并。"
            "⚠️ 不得靠给两个异构映射共用一个名字减总量 —— 那是撞名(完整性级 FAIL)",
        )
    elif u and n + u > _PRESET_BUDGET_MAX:
        report.add(
            "L1-1", "权利要求书",
            f"已归类 {n} 个: {listing}; 未归类 {u} 处: " + "、".join(unclassified),
            f"权要内已归类预设对象 {n} 个未超线, 但另有 {u} 处 `预设` 未被量词表归类, "
            f"合计可能达 {n + u} 个 (>上限 {_PRESET_BUDGET_MAX})。请人工确认这几处是否为"
            "独立预设对象; 若是且总量超线按 2.4a 四条通路消解, 若属同一对象的不同表述"
            "或非对象性表达(如概括称谓), 请把其收尾量词补进本规则 _PRESET_NOUN_TAIL",
        )


# 规则 44 模式表唯一出处: 权要措辞七条中「机械可查」的四项 (claims-requirements.md L1-1「权要措辞紧凑七条」,
# X2607134 王工点名"权要的表述是最要学习的"; 该案 1 稿→定稿字级 diff 实测清零).
# 七条中 ⑤不为中间量命名 / ⑥所述只跨句回指 / ⑦篇幅守恒属判断题, 由 claims-auditor
# 语义判 (契约第 12 项), 不进本规则。
_CLAIM_WORDING_PATTERNS = (
    ("预设的", r"预设的",
     "「预设」后不加「的」 —— 写 `预设xx阈值`, 不写 `预设的xx阈值`"
     "(X2607134 定稿 `预设的xx` 17 处→0 处)"),
    ("大于或者等于", r"大于或者等于|小于或者等于",
     "删不承载技术含义的虚字 —— `大于或者等于`→`大于等于`(删「或者」)"),
    ("若…则", r"若[^，。；]{1,30}[，,]?则",
     "判断句用 `当…时，〔动作〕` 且不带「则」, 不用 `若…则`"
     "(G6-1 两种句式里王工选了「当…时」并删掉「则」)"),
    ("，并", r"，并(?![且非])",
     "删「，并」 —— 权要内并列连接词不承载技术含义, 拆句或改「，根据」"
     "(X2607134 定稿 2 处→0 处)"),
)


def check_claim_wording_seven(lines: list[str], sections: dict, report: Report) -> None:
    """规则 44 (1级 hard): 权要措辞七条的四项机械项 (claims-requirements.md L1-1 措辞紧凑七条, X2607134).

    ★ **只扫权利要求书章节内**, 不扫技术领域/背景技术 —— 措辞七条的证据来自
    X2607134 **权利要求书** 1 稿→定稿的字级 diff, 适用范围是权要本体。背景技术
    是叙述性文本, 其中的 `，并` 承接同一主语的连续动作, 删除后语义断裂
    (H2608165 权要 1 稿实测: 背景技术段 2「读取该标识对应的坐标，并以该坐标校正
    编码器的累计值」属合法叙述连接, 若全稿扫即误报)。

    L1-2 另有一条"短步骤不宜过碎, 宜用「，并」「，根据」等连接合并"—— 与本项
    方向相反但不冲突: 那条讲的是**分段过碎时的合并手段**, 本项讲的是**合并后
    的措辞选择**(优先「，根据」而非「，并」)。命中时按本项改写, 不是回退到不合并。
    """
    body, offset = get_section_lines(lines, sections, "权利要求书")
    if offset < 0:
        return
    for i, line in enumerate(body):
        s = line.strip()
        if not s:
            continue
        for label, pat, advice in _CLAIM_WORDING_PATTERNS:
            m = re.search(pat, s)
            if m:
                report.add(
                    "L1-1", f"权利要求书 第{offset + i + 1}行",
                    f"命中「{m.group(0)}」: {s[:60]}",
                    f"权要措辞七条(L1-1, X2607134 王工口径): {advice}",
                )


def check_forbidden_words(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 9: G5-1 禁用措辞黑名单."""
    scan_range = _get_scan_ranges(lines, sections, stage)
    for (label, start, end) in scan_range:
        for i in range(start, end):
            line = lines[i]
            if BOILER_INDICATIVE_ANCHOR in line:
                continue  # 收尾装置/系统示意性说明段 = 模板固定套话, 整行豁免(见常量注释)
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
    """规则 14: 权要稿禁写章节 (SKILL.md 权要一稿 step 5)."""
    if stage != "claims-draft":
        return
    for title in sections:
        for forbidden in CLAIMS_DRAFT_FORBIDDEN_SECTIONS:
            if forbidden in title:
                report.add(
                    "SKILL 权要一稿", "章节",
                    title,
                    f"权要稿.md 不得写入章节: {forbidden}",
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
    "本发明第二实施例提供了一种〔发明名称〕系统，包括：存储器、处理器及……实现如上述
    所述的方法。"(2026-08-28 起句末不带"的步骤", 见规则 46),
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


# G6-1 Unicode 上/下标字符集。
# ★ 2026-09-22 改（H2609100 全文复盘）：原实现**只收下标**，注释还明写着
#   「上标 ²³ 在单位 m² 合法故不纳入, 保零误报」——于是该案 10 处手打上标
#   （2.1×10⁸、6×10⁻¹⁷、1.0×10⁻⁴ …）**一次都没响**，五轮审查加第五路全过，
#   直到王工肉眼看到并亲自删改。**这不是漏收一个字符，是把整类上标排除在外**。
#   按「不打地鼠」口径改为**收全部上下标 + 单一白名单豁免**，不再逐个补形态：
#   合法的只有「长度单位后的 ²/³」（m²、km²、cm³…），那是中文出版物的通行写法；
#   除此之外的 Unicode 上下标一律视为「冒充公式」，改写成 $…$ 行内 LaTeX。
UNICODE_SUBSCRIPTS = set("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼ")
UNICODE_SUPERSCRIPTS = set("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
UNICODE_SUBSUP = UNICODE_SUBSCRIPTS | UNICODE_SUPERSCRIPTS
# 白名单：长度单位结尾（m / km / cm / dm / mm / μm / nm）
_LEN_UNIT_TAIL = re.compile(r"(?:[kcdμn]?m)$")


def check_unicode_subscript_abuse(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 19: 禁用 Unicode 上/下标字符冒充公式 (G6-1).

    如 s₁、Σ₁、xᵢ（下标）与 2.1×10⁸、6×10⁻¹⁷（上标）——WPS 渲染成全角、上下标不叠放，
    等同未编译公式＝公开不充分；且手打的上标与公式对象里的格式不一致，**转档可能识别不出来**
    （王工 H2609100 审核v2 批注 2 + 提醒 3 原话）。公式符号一律写 `$…$` 行内 LaTeX。
    **白名单**：长度单位后的 ²/³（m²、km²、cm³…）属中文出版物通行写法，不报。
    仅扫说明书正文 (full-draft)。
    """
    if stage != "full-draft":
        return
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        for i in range(start, end):
            line = lines[i]
            hits: list[str] = []
            for pos, ch in enumerate(line):
                if ch not in UNICODE_SUBSUP:
                    continue
                if ch in "²³" and _LEN_UNIT_TAIL.search(line[:pos]):
                    continue                      # 白名单：长度单位的平方/立方
                hits.append(ch)
            if hits:
                report.add(
                    "G6-1", f"{label} 第{i + 1}行", line.strip()[:60],
                    f"出现 Unicode 上/下标字符 {''.join(sorted(set(hits)))} 冒充公式；"
                    f"应写 $…$ 行内 LaTeX（手打的形式转档可能识别不出来）",
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
            if BOILER_INDICATIVE_ANCHOR in lines[i]:
                continue  # 收尾套话段豁免(同 check_forbidden_words)
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

    说明书按实施例分层: 第一实施例=方法, 第二实施例=系统 (计算机设备式);
    存储介质相关段落自 2026-09-11 起不再撰写(原「其后可续计算机可读存储介质」已废止).
    系统内容属第二实施例, 不得用"本发明实施例还提供了一种...系统"
    模糊表述写进方法(第一实施例)正文并展开存储器/处理器构成与部署细节. 收尾四锚点按序
    出现, 缺一或乱序即 FAIL. 锚点取模板固定骨架 (发明名称在填空处、不入锚点), 零误报.
    仅 full-draft.
    """
    if stage != "full-draft":
        return
    anchors = [
        ("综上所述总结段(第一实施例=方法收口)", re.compile(r"综上所述，本发明公开了一种")),
        # ★ 锚点须同时锁"第二实施例"与"系统": 原正则只写 第[一二三…]实施例提供了一种,
        # 宽到会命中方法侧入口句"本发明第一实施例提供了一种〔…〕方法"(H2608165 王工亲改
        # 集中罗列段入口句为该形态), 且 next() 取首个命中行 → 方法入口句被误当系统段,
        # 误报"系统段在总结段之前"顺序错误. 序数词仍放宽(容"第二/第三"), 但正文须落"系统".
        ("第二实施例系统段", re.compile(r"第[二三四五六七八九]实施例提供了一种[^。]{0,60}?系统")),
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


# ---------------------------------------------------------------- 规则 47: 模板句逐字断言
#
# 立项根因 (H2608165 全文审核v1, 王工三条批注 8/9/10「未按照模板套话来写」「不要改模板」
# 「不要删减模板」): 套话原文第一次经过撰写者之手就被改写/删减 (开篇段 130 字抄成 70 字)。
# 2026-09-10 升级 (H2609029 用户连抓 6 处模板问题: 第一方面整句漏、附图说明漏「第一实施例」、
# 装置示意段被删、第二实施例/存储介质段措辞自改、结束语偏离王工批注 21 定版): 首版只上三段
# 骨架、且为避免对旧定稿误报而放宽变体; 现按王工批注 21「不一致, 后续都按模板来」与用户
# 「模板是填空题, 变量词之外一字不动; 能固定的用脚本固定」口径, **全部模板句逐字断言**,
# 原文唯一副本与校验逻辑移入 `scripts/boilerplate.py` (同一份常量同时服务 md 层本规则、
# DOCX 层 verify_docx_injection.py、以及落笔前 `boilerplate.py render` 填空渲染)。
# 变体口径：模板句整体逐字，但两类按白名单放行 —— ①「所述程序 / 所述计算机程序」两版；②结束语批注 21 定版 + 简版；
# 其余旧定稿同义变体（第一方面短式、其它结束语写法）仍判 FAIL。
_BOILER_OPENING = boilerplate._OPENING          # 兼容旧引用
_BOILER_OPENING_VARIANT = _BOILER_OPENING.replace("作出创造性", "做出创造性")


def check_boilerplate_verbatim(lines: list[str], sections: dict, report: Report,
                               stage: str, claims_text: str = "") -> None:
    """规则 47 (1级 hard): 模板句逐字断言 (L6-1 / L7 / L8-1 / G8-2 批注 21; 唯一副本 boilerplate.py).

    覆盖 11 句: 第一方面 / 第二方面 / 有益效果引入 / 附图说明图1 / 开篇段 /
    集中罗列入口句 / 综上所述骨架 / 第二实施例 / 方法—系统对应 / 示意性说明 /
    结束语; 另查名称槽位一致与收尾顺序。介质相关三句为禁写项，出现即 FAIL。
    与规则 21 (四锚点按序) 并存: 规则 21 管结构, 本规则管内容逐字。仅 full-draft。
    """
    if stage != "full-draft":
        return
    text = "\n".join(lines)
    # 豁免: 非真实全文稿的短样例 (单元测试 fixture / 半成品草稿), 与 L8-1 字数条同口径。
    if count_chinese(text) < 1000:
        return
    paras, secs = [], {}
    cur = None
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            if s.startswith("## "):
                cur = s[3:].strip()
            continue
        secs[len(paras)] = cur
        paras.append(s)
    claims_src = claims_text or "\n".join(
        ln for tt in sections if "权利要求书" in tt for ln in lines[sections[tt][0]:sections[tt][1]]
    )
    has_system, _has_medium = boilerplate.detect_subjects(claims_src)  # 介质权已禁写，仅作兜底提示
    rule_of = {"发明内容": "L6-1", "附图说明": "L7", "具体实施方式": "L8-1", "全文": "L8-1"}
    for v in boilerplate.check_paragraphs(paras, has_system, secs):
        report.add(
            rule_of.get(v["section"], "L8-1"),
            f"{v['section']}(模板句·{v['label'].split('·', 1)[-1]})",
            v["evidence"][:160],
            v["message"] + " —— 落笔前用 `python scripts/boilerplate.py render --method-name … --system-name …` 渲染后整句粘贴",
        )


# ---------------------------------------------------------------- 规则 51: 权10 系统权模板句逐字 + 介质权禁写
#
# 立项 (2026-09-10 模板句机械化盘点): 系统权/存储介质权整条都是套话 (L1-1 给了原句), 但此前只有
# 规则 2b 查「的步骤」、规则 30 查发明内容第二方面骨架, 权要侧整条写法无人逐字核。
# H2609029 交付稿实测: 权 9 把「其特征在于」挪到「包括存储器」之前、句末写成「如权利要求1至8中
# 任一项」—— 两处均偏离 X2608107/H2608165 定稿逐字形态 (王工未点名, 但按「都按模板来」属应改)。
# 原文唯一副本 boilerplate.CLAIM_TEMPLATES; {N} 须 = 系统权编号 − 1 (覆盖全部方法权)。

def check_claim_boilerplate(lines: list[str], sections: dict, report: Report) -> None:
    """规则 51 (1级 hard): 系统权整条逐字 + 介质权禁写 (L1-1; 唯一副本 boilerplate.py)."""
    body, offset = get_section_lines(lines, sections, "权利要求书")
    if offset < 0:
        return
    claim_lines = [ln.strip() for ln in body if ln.strip()]
    for v in boilerplate.check_claims(claim_lines):
        loc = f"权利要求书(模板句·{v['label'].split('·', 1)[-1]})"
        if v.get("kind") == "suspect":
            # 形态/位置类线索只出 suspect（功能模块式属规则允许的备选形态、位置偏差由人定）
            sid = "S-L1-system-claim-form" if "形态" in v["label"] else "S-L1-system-claim-position"
            report.add_suspect("L1-1", loc, v["evidence"][:160], v["message"],
                               suspect_id=sid, section="L1", owner="claims",
                               missing_dimensions=["权要形态"])
        else:
            report.add("L1-1", loc, v["evidence"][:160],
                       v["message"] + " —— 系统权是填空题: 只填系统名与 N, 其余一字不改（介质权已禁写）")


# ---------------------------------------------------------------- 规则 52: 有益效果分项数与字数
#
# invention-content.md L6-1「有益效果字数与分项数 (1级)」: 恰好 3 项 / 400–450 字 (含标点)。
# 此前无机械校验。五案定稿实测 (2026-09-10): 项数 3/3/3/3 (X2607134 旧稿 4); 字数 415/429/430/496
# —— 字数区间在王工亲改后的 H2608165 定稿也破线 (496), 故**项数 hard、字数 suspect** (由
# content-auditor 判是否确属灌水/过短), 不做假红灯。

def check_benefit_count_and_length(lines: list[str], sections: dict, report: Report,
                                   stage: str) -> None:
    """规则 52: 有益效果恰 3 项 (hard) + 400–450 字 (suspect S-L6-benefit-length)。仅 full-draft。"""
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "发明内容")
    if offset < 0:
        return
    start = next((i for i, ln in enumerate(body) if ln.strip().startswith("相比于现有技术")), -1)
    if start < 0:
        return  # 引入句缺失由规则 47 报
    seg = [ln.strip() for ln in body[start:] if ln.strip()]
    items = [ln for ln in seg[1:] if _BENEFIT_ITEM_RE.match(ln)]
    if len(items) != 3:
        report.add(
            "L6-1", f"发明内容 第{offset + start + 1}行起",
            f"有益效果分项数 = {len(items)}",
            f"有益效果必须恰好 3 项 (（1）（2）（3）), 实际 {len(items)} 项 (L6-1 1级)",
        )
    n_chars = sum(len(ln) for ln in seg)
    if not 400 <= n_chars <= 450:
        report.add_suspect(
            "L6-1", f"发明内容 第{offset + start + 1}行起",
            f"有益效果部分 {n_chars} 字 (含引入句与标点)",
            f"有益效果字数 {n_chars} 不在 400–450 区间 (L6-1); 请判是否灌水/过短后回修或豁免 "
            "(H2608165 王工定稿 496 字, 区间非绝对红线)",
            suspect_id="S-L6-benefit-length", section="L6", owner="content",
            missing_dimensions=["字数区间"],
        )


# ---------------------------------------------------------------- 规则 53: 权 1 单步子动作密度
#
# 立项 (王工 2026-09-10 看 H2609029 Visio 图口头: 「最后一步太臃肿」, 指示自「当关联度大于阈值」
# 起另起第 6 步): claims-requirements.md L1-1 早有「创新档拆 2–3 个显式子步骤(有上限)」、X12「引导句只覆盖
# 1 个动作」, 但落笔时没人数——原 S15 一步串 7 个动作 127 字。机械闸门此前只查主步骤**数量**
# (规则 1b), 不查单步**密度**。
# 计数法 (七案定稿标定, 2026-09-11): 去掉「当…时」判定条件后按「，；」切分, 「得到/输出/作为」
# 起句的输出分句并入前一动作, 每个含动作动词的分句计 1, 「…的」定语里藏的动作 (「声学定位得到的」)
# 另计 1, 判定条件本身计 1。六案定稿 30 步实测密度 1–4, H2609029 1稿臃肿步 = 6, 3稿拆后末步 = 5
# (王工看图后仍要求再拆, 说明 5 也偏密)。阈值 ≥5 出 suspect (owner=claims, 交 claims-auditor 判
# 是否拆步), 不做 hard —— 拆步是方案层决策。
_ACTION_VERB_RE = re.compile(
    r"(获取|采集|提取|计算|确定|生成|构建|输出|导入|输入|进行|求解|识别|判定|划分|匹配|融合|反演"
    r"|滤除|校验|验证|修正|补偿|加权|拼接|映射|换算|截取|标定|记录|更新|选取|筛选|比对|统计|叠加"
    r"|回调|解算|定位|得到|作为|平滑|归一化|变换|分类|聚类|预测|估计|拟合|检测|分割|重构|转换"
    r"|编码|解码|排序|存储|发送|接收|调节|控制|触发|执行)"
)
_HIDDEN_ACTION_RE = re.compile(r"(得到|输出|提取|采集|计算|确定|生成|求解|识别|定位|拟合|预测|估计)的")
_OUTPUT_CLAUSE_RE = re.compile(r"^(得到|输出|作为|确定为)")
CLAIM1_STEP_ACTION_DENSITY_MAX = 4


def claim1_step_action_density(step: str) -> int:
    """单步子动作数 (计数法见上方注释)。"""
    s = step.strip().rstrip("；;。")
    n = len(re.findall(r"当[^，；]{2,60}?时", s))
    s2 = re.sub(r"当[^，；]{2,60}?时，?", "", s)
    clauses = [c.strip() for c in re.split(r"[，；]", s2) if c.strip()]
    merged: list[str] = []
    for c in clauses:
        if _OUTPUT_CLAUSE_RE.match(c) and merged:
            merged[-1] += "，" + c
        else:
            merged.append(c)
    for c in merged:
        hidden = len(_HIDDEN_ACTION_RE.findall(c))
        core = _HIDDEN_ACTION_RE.sub("", c)
        n += (1 if _ACTION_VERB_RE.search(core) else 0) + hidden
    return n


def check_claim1_step_action_density(lines: list[str], sections: dict, report: Report) -> None:
    """规则 53 (suspect S-L1-step-density): 权 1 单步子动作 ≥5 出线索, 建议拆步 (claims-requirements.md L1-1「上位程度分档/单动作步骤」)。"""
    blocks = extract_claim_blocks(lines, sections)
    if 1 not in blocks:
        return
    start, end = blocks[1]
    body_lines = [ln.strip() for ln in lines[start:end] if ln.strip()]
    for k, step in enumerate(body_lines[1:], start=1):
        n = claim1_step_action_density(step)
        if n > CLAIM1_STEP_ACTION_DENSITY_MAX:
            report.add_suspect(
                "L1-1", f"权利要求书 权 1 第 {k} 分句 (第{start + 1 + k}行)",
                f"子动作 {n} 个 / {len(step)} 字: {step[:60]}…",
                f"权 1 第 {k} 分句串了约 {n} 个子动作 (六案定稿单步 1–4; H2609029 被王工判「太臃肿」的末步为 6), "
                "建议自判定条件之后的第一动作起拆为新主步骤 (上限 6 步), 不得为守步数把多个动作塞进一步 (claims-requirements.md L1-1)",
                suspect_id="S-L1-step-density", section="L1", owner="claims",
                missing_dimensions=["拆步"],
            )


# ---------------------------------------------------------------- 规则 54: 采样率/频带数值三问
#
# 立项 (H2609029 交底书数值自相矛盾照抄进 1 稿, 第五路 reviewer-sim 才拦住): S104 特征频段
# 特征频段与能量积分区间 / 频率峰值 不在同一覆盖范围; 采样周期
# 采样周期对应的采样率连最高频率都采不到 (奈奎斯特)。规则 39 (W53) 只做示例值代回与量级一致, 不做频域三问。
# 本规则是「数值三问」的机械半边 (①奈奎斯特 ②数值落区间), ③阈值方向仍靠 G6-1 不等号核。
# 只报 suspect (owner=impl): 频率单位混写 (kHz/Hz)、多通道各自采样率等合法情形须由 auditor 判。
_FREQ_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kHz|KHz|Hz|MHz)")
_SAMPLE_RATE_RE = re.compile(r"采样(?:率|频率)[^。；]{0,12}?(\d+(?:\.\d+)?)\s*(kHz|KHz|Hz|MHz)")
_SAMPLE_PERIOD_RE = re.compile(r"采样(?:周期|间隔)[^。；]{0,12}?(\d+(?:\.\d+)?)\s*(ms|毫秒|μs|us|微秒|s|秒)")
_BAND_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:kHz|KHz|Hz|MHz)?\s*[~～\-–—至到]\s*(\d+(?:\.\d+)?)\s*(kHz|KHz|Hz|MHz)")


def _hz(v: str, unit: str) -> float:
    x = float(v)
    return x * {"kHz": 1e3, "KHz": 1e3, "Hz": 1.0, "MHz": 1e6}[unit]


def check_sampling_nyquist(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 54 (suspect S-G6-nyquist / S-G6-band-range): 采样率 vs 最高频率 (奈奎斯特) 与频带覆盖。仅 full-draft。"""
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    text = "\n".join(body)
    rates = [_hz(v, u) for v, u in _SAMPLE_RATE_RE.findall(text)]
    for v, u in _SAMPLE_PERIOD_RE.findall(text):
        sec = float(v) * {"ms": 1e-3, "毫秒": 1e-3, "μs": 1e-6, "us": 1e-6, "微秒": 1e-6, "s": 1.0, "秒": 1.0}[u]
        if sec > 0:
            rates.append(1.0 / sec)
    # 先剔除「采样率/采样周期」片段本身，否则采样率会被当成信号频率自吞（10kHz 采样 → 误判最高频率 10kHz）
    text_wo_fs = _SAMPLE_RATE_RE.sub("", _SAMPLE_PERIOD_RE.sub("", text))
    freqs = [(_hz(v, u), v + u) for v, u in _FREQ_RE.findall(text_wo_fs)]
    if rates and freqs:
        fs = min(rates)
        top = max(freqs, key=lambda x: x[0])
        if top[0] > fs / 2:
            report.add_suspect(
                "G6-1", "具体实施方式(采样率 vs 最高频率)",
                f"最低采样率 {fs:g}Hz, 文中最高频率 {top[1]}",
                f"奈奎斯特: 采样率 {fs:g}Hz 只能表示 ≤{fs / 2:g}Hz, 文中出现 {top[1]} (实测: 采样周期换算的采样率不足最高频率两倍)。"
                "若为不同通道/设备各自采样率, 请在文中写明; 否则改数值",
                suspect_id="S-G6-nyquist", section="L8", owner="impl",
                missing_dimensions=["采样率与频率自洽"],
            )
    bands = [(_hz(a, u), _hz(b, u)) for a, b, u in _BAND_RE.findall(text)]
    if len(bands) >= 2:
        lo = min(b[0] for b in bands)
        hi = max(b[1] for b in bands)
        disjoint = [b for b in bands if b[1] < lo or b[0] > hi]
        # 任一频带与其余频带完全不相交 → 线索
        for b in bands:
            others = [o for o in bands if o is not b]
            if others and all(b[1] < o[0] or b[0] > o[1] for o in others):
                report.add_suspect(
                    "G6-1", "具体实施方式(频带覆盖)",
                    f"频带 {b[0]:g}–{b[1]:g}Hz 与其余频带 {[(o[0], o[1]) for o in others][:3]} 完全不相交",
                    "同一信号链的特征频段/积分区间/峰值频率应互相覆盖 (实测: 特征频段与能量积分区间不相交, "
                    "积分区间处无数据)。若两频带属不同信号, 请在文中写明",
                    suspect_id="S-G6-band-range", section="L8", owner="impl",
                    missing_dimensions=["频带自洽"],
                )
                break


# ---------------------------------------------------------------- 规则 55: 「其中」代指不显式
#
# 立项 (H2609029 定稿轮): 王工把 3 处「通过其中的决策树集合」改为「通过所述预设随机森林模型中的
# 决策树集合」——正文里不写「其中」代指, 写「所述〔对象〕中」, 让回指对象显式化 (与 G4-1 的
# 「所述」回指链同一取向)。规则零误报口径: 只在「介词 + 其中」形态命中 (通过其中/将其中/对其中/
# 在其中的 X), 正常引述「其中，…」作引导词不算 (那是 implementation.md L8-1 的合法引导词)。
_PRONOUN_QIZHONG_RE = re.compile(r"(?:通过|将|对|在|由|从|把)其中")


def check_pronoun_qizhong(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 55 (suspect): 正文用「其中」代指对象 (G4-1 回指显式化; H2609029 定稿轮)."""
    if stage != "full-draft":
        return
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        for i in range(start, end):
            m = _PRONOUN_QIZHONG_RE.search(lines[i])
            if m:
                report.add_suspect(
                    "G4-1", f"{label} 第{i + 1}行", lines[i].strip()[:60],
                    "「其中」代指对象不显式; 应写「所述〔对象〕中」(王工 H2609029 定稿亲改 3 处)",
                    suspect_id="S-G4-qizhong", section="G4", owner="global",
                    missing_dimensions=["回指显式化"],
                )


# ---------------------------------------------------------------- 规则 58: 「其/该」纯代词代指
#
# 出处：`global.md` G4-1「不要使用"其""此""该"等**指代不明**的代词」。
#
# ★ 覆盖缺口（2026-09-19，H2609100 实测）：本条落地前，**说明书的「其/该/此」三方皆无覆盖**——
#   规则 56（「其/该」代指，hard）的扫描范围是 `get_section_lines(..., "权利要求书")`，
#   **只扫权利要求书章节**；规则 55 只抓「其中」一种形态（`(?:通过|将|对|在|由|从|把)其中`）。
#   该案背景技术在 `权要稿.md` 的「背景技术」章节内（不是「权利要求书」章节），
#   于是「该方式先采集…」（跨段回指段 1 的「寿命评估方式」）与全文稿 4 处「其与／其为」
#   **全部静默通过**，由用户通读全文才被发现——与规则 49 词表漏收「确定方式为：」同类。
#
# 判据取**窄带高精度**：只抓两类几乎必为纯代词的形态，**不抓**「该节点／该矩阵／该区域」
#   这类「该＋明确名词」的合法限定词用法——后者是中文专利说明书的标准高频写法，
#   本案全文稿 99 处「该/其」命中里 95 处属此类，若一并上报即为大面积误报。
#   ① `其` 后直接接介词/助动词（其与／其为／其被…）→ 后面没有名词，必是纯代词；
#   ② `该` 后接**通用抽象名词**（该方式／该方法／该过程…）→ 最易跨段回指、最易指代不明。
# 与规则 56 不重叠：本条跳过「权利要求书」章节（该章由规则 56 以 hard 终判）。
_QIDAI_BARE_RE = re.compile(r"(?<!特征)其(与|为|即|乃|被|使|让|由|从|把|将)")
_QIDAI_VAGUE_RE = re.compile(r"该(方式|方法|过程|方案|步骤|情况|措施|做法|手段|思路|策略|途径|装置)")


def check_bare_pronoun(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 58 (suspect): 「其/该」纯代词代指、指代不明 (G4-1；覆盖说明书各块)."""
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        if "权利要求书" in label:
            continue  # 该章由规则 56 以 hard 终判，不重复上报
        for i in range(start, end):
            ln = lines[i]
            if not ln.strip():
                continue
            for pat, dim in ((_QIDAI_BARE_RE, "「其」后不接名词，为纯代词代指，应写「所述〔对象〕」"),
                             (_QIDAI_VAGUE_RE, "「该+通用名词」易跨段回指，应写「所述〔对象〕」或点名对象")):
                if pat.search(ln):
                    report.add_suspect(
                        "G4-1", f"{label} 第{i + 1}行", ln.strip()[:60], dim,
                        suspect_id="S-G4-bare-pronoun", section="G4", owner="global",
                        missing_dimensions=["回指显式化"],
                    )
                    break


# ---------------------------------------------------------------- 规则 60: 中文正文的非常规符号（白名单法）
#
# 出处：`global.md` G5-1「**破折号与其他特殊符号全文不用**」（王工 H2608165 批注 5）。
#
# ★ 为什么用白名单而不是词表（2026-09-22，H2609100 全文复盘）：
#   规则 48 只机械化了**破折号**，「其他特殊符号」一直没有词表——于是该案曲率句里的
#   `「1加一阶导数平方」` 全程漏网，王工审核v2 批注 4 亲手指出「「」不是中文文稿的标准标点」。
#   **给规则 48 补一个「还有哪些符号」的词表就是打地鼠**：下次来个 `→`、`≈`、`§`
#   照样漏。改为**白名单法**——中文正文只允许一批常规字符，**白名单外的一切符号出线索**，
#   新符号不需要再补名单。
#
# 级别：**suspect 不是 FAIL**。理由同「闸门松紧原则」：白名单不可能穷尽（单位符号、
#   专业记号各有惯例），判 FAIL 会大面积误报并把闸门信誉耗尽。出线索交 auditor 逐条判。
#   上报时给出**该行全部越界字符的原文片段**，让判定有据。
# 范围：仅说明书正文（full-draft）。权利要求书的法定体例标点不受 G5-1 约束（该条扫描边界）。
_CN_PUNCT_OK = set("，。、；：？！（）《》“”‘’")   # 中文正文的标准标点（含引号）
_OTHER_OK = set(" \t%°×·.,/-+")          # 数值/单位/型号里合法
_MICRO = "μ"                              # 微米等单位的词头
_GREEK_OK = set("μΩ")                     # 工程单位里通行的两个希腊字母
_ALLOWED_EXTRA = _CN_PUNCT_OK | _OTHER_OK | _GREEK_OK | {_MICRO}


def check_unconventional_symbols(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 60 (suspect): 中文正文出现白名单外的非常规符号 (G5-1；仅说明书).

    ⚠️ 扫描前必须**剔除公式承载部分**：块公式行（行首 [A-Za-z\\] + 含 \\ + 无 $）整行跳过，
    行内 `$…$` 先剥掉再扫。否则 LaTeX 的 `\\ { } _ ^` 会被当成"非常规符号"，本案实测
    未剔除时一次报 17 处（应为 1 处）——**闸门误报洪水比漏报更快耗掉信誉**。
    """
    if stage != "full-draft":
        return
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        if "权利要求书" in label:
            continue                    # 法定体例标点不受 G5-1 约束
        for i in range(start, end):
            line = lines[i]
            s = line.strip()
            if s and s[0].isascii() and ("\\" in s) and "$" not in s:
                continue                # 块公式行（同 inject 的 _BLOCK_FORMULA_RE 口径）
            line = re.sub(r"\$[^$\n]*\$", "", line)     # 剥掉行内公式再扫
            bad = sorted({ch for ch in line
                          if not (ch.isalnum() or ch in _ALLOWED_EXTRA
                                  or ch in UNICODE_SUBSUP      # 上下标归规则 19，不重复报
                                  or "一" <= ch <= "鿿")})
            if bad:
                report.add_suspect(
                    "G5-1", f"{label} 第{i + 1}行", line.strip()[:60],
                    f"出现白名单外的符号 {''.join(bad)}；G5-1「破折号与其他特殊符号全文不用」，"
                    f"应改写为文字表述或用 $…$ 公式承载",
                    suspect_id="S-G5-1-symbol", section="G5", owner="global",
                    missing_dimensions=["非常规符号改述"],
                )


# ---------------------------------------------------------------- 规则 61: 数学表达的文字化写法（suspect）
#
# 出处：王工 H2609100 审核v2 提醒 3「**指数形式用公式框插入，手打的后面转档有可能会
#   识别不出来**」+ 批注 4（把曲率句改写掉）。
#
# 该案曲率句原文：「…的绝对值与「1加一阶导数平方」的3/2次方的比值」——「3/2次方」
#   是**手打的分数指数**，与 Unicode 上下标同源（都属"本该是公式却写成了文字"），
#   转档后可能识别不出来。审核v2 王工改成文字叙述后仍留着「3/2次方」，经用户确认
#   **这是漏改、不是认可**，故仍需机械兜住。
#
# 级别 **suspect**：词表虽属封闭集（中文里表示指数/根式的词就那么几个），但正文里
#   引用既有公式名（如"高斯求积"）或描述既有结论时可能合法出现，判 FAIL 风险高于收益；
#   出线索交 impl-auditor 逐条判。**只收指数与根式**——「除以/乘以」这类纯叙述词不收，
#   否则大范围误报（王工自己认可的文字叙述里就有"除以"）。
_MATH_WORD_RE = re.compile(r"次方|次幂|开方|开根|根号|平方根|立方根|分之[一二三四五六七八九十\d]+")


def check_math_wording(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 61 (suspect): 数学表达用文字手打（应写 $…$ 公式，转档可能识别不出来）."""
    if stage != "full-draft":
        return
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        if "权利要求书" in label:
            continue
        for i in range(start, end):
            line = re.sub(r"\$[^$\n]*\$", "", lines[i])   # 剥掉行内公式再判
            m = _MATH_WORD_RE.search(line)
            if m:
                report.add_suspect(
                    "G6-1", f"{label} 第{i + 1}行", line.strip()[:60],
                    f"出现文字化的数学表达「{m.group(0)}」——应写成 $…$ 公式"
                    f"（手打形式转档可能识别不出来；王工 H2609100 审核v2 提醒 3）",
                    suspect_id="S-G6-1-math-wording", section="G6", owner="impl",
                    missing_dimensions=["数学表达公式化"],
                )


# ---------------------------------------------------------------- 规则 59: 权要编号与正文之间的空白
#
# 出处：王工 H2609100 审核v1 批注 0「权要编号与正文之间不要留空格，每个都有」。
#
# ★ 覆盖缺口（2026-09-21，H2609100 实测）：格式标准 `claims-format-standard.md` 第 9 行
#   早就写对了——「权要编号开头单独成段，例如"**1.一种**……方法，其特征在于，包括："」，
#   落笔时却写成「1. 一种」，**违反已写明的标准**（A 类）。更关键的是**没有闸门**：
#   `extract_claim_blocks` 的抽取正则 `^\s*(\d+)\s*\.` 是**容错**的（允许编号周围空白），
#   带空格的编号照样被正确识别、后续所有检查照跑、五轮闸门没有一处能看见这个空格，
#   直到王工肉眼看到。规则写对而无闸门 = 静默通过，本条把它机械化。
# 判据（窄带）：编号行「数字 + 点号」之后若紧跟空白（半角空格/制表符/全角空格）即违规；
#   编号行前的行首缩进不管（另有段落格式闸门负责）。
_CLAIM_NUM_WS_RE = re.compile(r"^\s*\d+\s*[.．][ \t　]")


def check_claim_number_spacing(lines: list[str], sections: dict, report: Report) -> None:
    """规则 59 (hard): 权要编号与正文之间不留空白 (L1-1; 王工 H2609100 审核v1 批注 0)."""
    body, offset = get_section_lines(lines, sections, "权利要求书")
    if offset < 0:
        return
    for i, ln in enumerate(body):
        if _CLAIM_NUM_WS_RE.match(ln):
            report.add(
                "L1-1", f"权利要求书 第{offset + i + 1}行",
                ln.strip()[:40],
                "权要编号与正文之间不得留空白，应写「1.一种…」（claims-format-standard 第 9 行）",
            )


# ---------------------------------------------------------------- 规则 56/57: 权要代指与引用基础
#
# 出处：王工《专利撰写AI自查流程指引（撰写人版）》第 5 步「尺度提醒」——
#   ①「指示代词是硬红线：执行步骤里不允许出现'其、该'指代（'其特征在于'等惯用式除外），
#     一律改为'所述+术语'或重复术语全称」（规则 56，hard）
#   ②「每个'所述'要有引用基础（前文出现过）……前文出现过的特征，再次出现漏'所述'要补上」
#     （规则 57 取前者；后者属语义，交 claims-auditor）
# 标定（七案定稿权要块，2026-09-11）：规则 56 命中 0 处（唯一命中是介质权惯用句「其上存储有计算机程序」，
# 该权已禁写）；规则 57 限「权 1 特征部分」时七案 0 处，扩到全条权会因系统权写全名/套话固定搭配误报，故只做权 1。
_QIDAI_RE = re.compile(r"(?<!特)其(?!中|他|余)|(?<!如)(?<!应)该")
_QIDAI_EXEMPT = ("其特征在于", "其中", "其他", "其余", "其上存储有", "及其", "应该", "如该")

# 抽取「所述」后面的名词短语。★ 2026-09-22 改：原式 `[^，。；、：（）]{2,10}` 会**贪婪吞掉
# 后面 10 个字**，把紧跟的下一个「所述」一起吃掉——H2609100 权 9 里「获取所述蠕变孔洞密度
# 与所述孔洞平均直径」被抽成一个整体，**「所述孔洞平均直径」根本没被单独看到**，
# 于是那条真缺陷（王工审核v2 批注 0/1）漏报。改为「2–8 字且内部不得再出现『所述』」。
_REFERENT_RE = re.compile(r"(?<!所述)所述((?:(?!所述)[^，。；、：（）]){2,8})")
# 套话部件名：由权要模板句给出（系统权三件套），不参与引用基础判定
_REFERENT_EXEMPT_NOUNS = {"存储器", "处理器", "计算机程序", "程序", "方法", "系统", "装置", "存储器上"}


def check_claim_pronoun_qidai(lines: list[str], sections: dict, report: Report) -> None:
    """规则 56 (1级 hard): 权要内不得用「其/该」代指，一律写「所述〔术语〕」(王工自查指引第 5 步)。"""
    body, offset = get_section_lines(lines, sections, "权利要求书")
    if offset < 0:
        return
    for i, ln in enumerate(body):
        s = ln.strip()
        if not s:
            continue
        # 惯用式与固定搭配先挖掉再扫，避免误报
        probe = s
        for ex in _QIDAI_EXEMPT:
            probe = probe.replace(ex, "【】")
        m = _QIDAI_RE.search(probe)
        if m:
            report.add(
                "L1-1", f"权利要求书 第{offset + i + 1}行", s[:60],
                f"权要内出现「{m.group(0)}」式代指；执行步骤里不得用「其/该」指代"
                "（『其特征在于』等惯用式除外），一律改「所述〔术语〕」或重复术语全称"
                "（王工《撰写AI自查流程指引》第 5 步硬红线）",
            )


def check_claim1_referent_basis(lines: list[str], sections: dict, report: Report) -> None:
    """规则 57 (suspect): 每条权的「所述X」须有引用基础（更早位置以非「所述」形态出现过）。

    ★ 2026-09-22 扩面（H2609100 全文复盘）：原实现**只查权 1**，注释理由是「限权 1 时
      七案 0 处；扩到全条权会因系统权写全名与套话固定搭配误报，故不做」。但该案的问题
      恰恰出在**权 9**——按审核v1 批注 5 改写「获取」时把范围写窄了（只取蠕变孔洞密度），
      于是第 4 子步骤的「所述孔洞平均直径」在权要里**从没出现过**，失去先行词；
      王工审核v2 批注 0/1 亲手指出。**为躲误报把范围收在权 1，等于把整片从权让给人工。**
      改为「全条权 + 定点豁免」——豁免套话固定搭配与系统权独有写法，而不是整条不查。

    引用基础池 = 权 1 全文 + 本条权「其特征在于」之前的引导句 + 本条特征部分中该处之前。
    """
    blocks = extract_claim_blocks(lines, sections)
    if 1 not in blocks:
        return
    # 权 1 全文作为所有从权的共用基础池
    s1, e1 = blocks[1]
    c1_text = "\n".join(lines[s1:e1])
    c1_own = c1_text.split("其特征在于", 1)[1] if "其特征在于" in c1_text else c1_text
    for num, (start, end) in sorted(blocks.items()):
        body = "\n".join(lines[start:end])
        if "其特征在于" not in body:
            continue
        lead, own = body.split("其特征在于", 1)
        # 从权的 own 以引导句的句首「所述」开头（「…其特征在于，所述根据所述××…」），
        # 剥掉它，否则 _REFERENT_RE 会把它当成一个指代（H2609100 实测：捕获出
        # 「根据所述微观劣化特征」，正是引导句本身的内容）。
        own = re.sub(r"^[，,、\s]*所述", "", own)
        # 豁免：系统/装置独权的套话固定搭配（整条跳过）——本项只管方法权
        if "存储器、处理器及存储在" in body:
            continue
        # 豁免：套话部件名（复用「所述」但实体由模板给出）
        for m in _REFERENT_RE.finditer(own):
            noun = m.group(1)
            if noun in _REFERENT_EXEMPT_NOUNS:
                continue
            pool = (c1_own if num != 1 else "") + lead + own[:m.start()]
            found = False
            # probe 逐级缩短用于容错，但**下限不得低于 4 字**（2026-09-22 改）：
            # 原下限 2 字会把「孔洞平均直径」降成「孔洞」、再由同句的「蠕变孔洞密度」满足，
            # 于是 H2609100 权 9 的「所述孔洞平均直径」漏报（王工审核v2 批注 0/1 即此）。
            for L in (10, 8, 6, 5, 4):
                probe = noun[:L]
                if len(probe) < 2:
                    continue
                if re.search(r"(?<!所述)" + re.escape(probe), pool):
                    found = True
                    break
            if not found:
                report.add_suspect(
                    "L1-1", f"权利要求书 权 {num} 第{start + 1}行起", f"所述{noun}",
                    f"权 {num} 里的「所述{noun}」找不到首次出现（引用基础）——若确为首次引入应去掉「所述」，"
                    "若是漏写首次出现则补全（王工《撰写AI自查流程指引》第 5 步；"
                    "H2609100 权 9「所述孔洞平均直径」即此类，审核v2 批注 0/1）",
                    suspect_id="S-L1-referent-basis", section="L1", owner="claims",
                    missing_dimensions=["引用基础"],
                )


# ---------------------------------------------------------------- 规则 45: 有益效果分项句式
#
# 立项根因 (H2608165 全文审核v1, 王工批注 9 原话「套话模板，本发明通过xx，这样做怎么xx，
# 实现xx效果，不要改模板」): 既有规则只管"相比于现有技术 + 恰好 3 项 + 全角括号数字"
# (invention-content.md L6-1 / 规则 22), **三条各自的句式规则此前不存在** —— 撰写侧遂自拟
# 为「（1）补偿坐标序列既参与…，其技术原因在于…」, 把模板的"本发明通过"整个换掉。
#
# ★ 五案实测各条首句 (2026-09-01):
#   X2608107  （1）本发明通过对初始表面图像提取…    ✓
#   X2607043  （1）本发明从企业短信文本中提取…      ✓ (本发明+动词)
#   X2607040  （1）本发明根据当前气体体积计算…      ✓ (本发明+动词)
#   X2607134  （1）本发明将接缝区域掩码上采样为…    ✓ (本发明+动词)
#   H2608040  （1）通过从宏观图像提取绿化特征区域…  ✓ (通过+动词, 省"本发明")
#   H2608165  （1）补偿坐标序列既参与…              ✗ 唯一偏离形态
# 故判据取**宽口径**: 每条须以"本发明"或"通过"起句 (五案全部满足), 不强求逐字"本发明通过"
# —— 新模板第 47-49 段写的是"（1）本发明通过…", 但五案定稿有 4 种合法变体, 按母 skill
# 优先于新模板的口径 (用户 2026-09-01), 只拦"既不以本发明起句、也不以通过起句"的形态。
_BENEFIT_ITEM_RE = re.compile(r"^（[0-9１-９]）\s*(.*)$")
_BENEFIT_OK_HEAD = re.compile(r"^(?:本发明|通过|采用)")


def check_benefit_item_pattern(lines: list[str], sections: dict, report: Report,
                               stage: str) -> None:
    """规则 45 (1级 hard): 有益效果分项须按模板句式起句 (L6-1; 王工审核v1 批注 9).

    模板句式『（N）本发明通过〔技术方案〕对〔作用对象〕，〔推导过程〕，实现〔有益效果〕。』
    判据 (宽口径, 五案零误报): 每条以"本发明"/"通过"/"采用"起句。以技术特征名直接起句
    (如"（1）补偿坐标序列既参与…") 即违规 —— 那是把套话骨架换掉, 属改模板。
    仅 full-draft, 只扫发明内容章。
    """
    if stage != "full-draft":
        return
    body, offset = get_section_lines(lines, sections, "发明内容")
    if offset < 0:
        return
    for i, line in enumerate(body):
        m = _BENEFIT_ITEM_RE.match(line.strip())
        if not m:
            continue
        rest = m.group(1).strip()
        if not rest or _BENEFIT_OK_HEAD.match(rest):
            continue
        report.add(
            "L6-1", f"发明内容 第{offset + i + 1}行", line.strip()[:70],
            "有益效果分项未按模板句式起句; 须为『（N）本发明通过〔技术方案〕对〔作用对象〕，"
            "〔推导过程〕，实现〔有益效果〕。』—— 以『本发明』或『通过』起句, "
            "不得以技术特征名直接起句 (王工审核v1 批注『套话模板…不要改模板』)",
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
     "(唯一出处 implementation.md L8-1 收尾条), 引用方法处写'所述的方法'"
     "(王工 2026-08-28: 不写发明名称全称、不写'的步骤')"),
    ("其特征在于",
     "说明书不写'其特征在于'(权要专用体例); 直接陈述特征内容"),
]


def check_spec_no_claims_wording(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 29: 说明书禁用权要体例措辞 (G5-1, W18/W29/W30 合并).

    说明书正文块不得出现权要专用体例: "权利要求"(含"权利要求1至9任一项"等引用
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

    检查: **仅①计算机设备式骨架**(存储器/处理器/计算机程序).

    ②原"方法名须用全称"的简称探测 (`S-W05-aspect-name`) **已于 2026-08-28 停用** ——
    王工正式答复把"所述的方法"定为唯一正确写法, 该探测守的是被推翻的旧口径, 详见
    函数体内注释。

    **"的步骤"不在本规则**: 王工 2026-08-28「'的步骤'三个字全文去掉」, 说明书正文
    由规则 46 (`check_spec_no_debuzou`) 全文扫描、权要侧由规则 2b 精确报错。此前
    本处写"说明书侧套话本身带'的步骤'、两侧不同源"已被五案定稿实测推翻。

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
    # 注: "的步骤"三字**不在本规则**范围 —— 王工 2026-08-28「'的步骤'三个字全文去掉」,
    # 说明书正文由规则 46 (check_spec_no_debuzou) 全文扫描、权要侧由规则 2b 精确报错。
    # 此前本处注释写"说明书侧套话本身带'的步骤'、两侧不同源勿交叉迁移", 已被五案定稿
    # 实测推翻 (接受修订态「的步骤」全部为 0), 见规则 46 docstring。
    #
    # ②方法名写法 → **本探测已停用** (2026-08-28)
    # 原探测: `第一方面所述方法|如上所述的方法(?!名)` → 报"疑似用简称, 应写发明名称全称"。
    # 王工 2026-08-28 正式答复「系统项和介质项的句末, 还有说明书里的套话, 只写'如上述所述
    # 的方法'就行」—— **"所述的方法"从违规形态变成了唯一正确写法**, 本探测守的是旧口径,
    # 继续保留会把正确写法报成违规 (假红灯比漏检更难纠)。
    # 不做"翻转"(改为探测"写了全称")的理由: 全称在 A 类槽位 (摘要句/技术领域句/发明内容
    # 目的句, 规则 31) 仍是 1 级必需, 两条正则会互相误伤; 且"写没写全称"在新口径下已不再
    # 是问题 —— 新口径就是不写全称。
    # 若日后审核人再次要求全称, 恢复本段并同步 content-auditor.md 第 10 项与
    # scoring-content.md 的 S-W05 消费条款 (三处同改, 缺一即静默失效)。



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
# 分别写方法名/系统名, 句式出处见 docx-template.md G8-2 与 implementation.md L8-1 收尾条
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


# 规则 31b: A 类槽位**存在性**。规则 31 只判"写了的地方写对没有", 不判"该写的地方
# 有没有写" —— H2608165 实测: 发明内容首段整个漏掉「本发明的目的在于提供一种…以解决…」
# 槽位(`目的在于` 全稿零命中), 规则 31 因 hits 为空而 `return`, 判 PASS。
# 判据取"该槽位的引导串是否在场", 不比对题名(比对由规则 31 做), 两条互补不重复。
# ★ 五案实测 (2026-09-01) 决定了本表只能用**宽口径**引导串:
#   发明内容首段五案两种写法, 都合法 ——
#     「本发明**提供了**一种〔题名〕，以解决……」  X2607040 / X2607043 / X2608107 / H2608040
#     「本发明**的目的在于提供**一种〔题名〕，以解决……」  X2607134
#   ⚠️ 首版只认后者, 五案误报 4 例。新模板第 38 段写的也是「本发明提供了一种…以解决」,
#      即**前者才是模板原文**; 后者是 X2607134 的合法变体。
#   ⚠️⚠️ 更要紧的是: H2608165 上一轮据 global-auditor「缺目的在于槽位」的提示**补写了
#      「本发明的目的在于提供一种…」** —— 按本次实测, 原稿写「本发明提供一种…以解决…」
#      本就合规, 那次"补槽位"属**照错误判据改稿**。本表的宽口径同时纠正该判据。
#   技术领域: 五案「尤其涉及」与新模板/规则的「具体涉及」并存, 两者都收。
_A_SLOT_PRESENCE: list[tuple[str, str, str]] = [
    # (章节, 引导串正则, 缺失时的提示)
    ("发明内容", r"本发明(?:的目的在于)?提供了?一种[^\n]{0,80}?以(?:解决|实现)",
     "发明内容首段缺 A 类槽位『本发明提供了一种〔正式题名〕，以解决……的问题。』"
     "(或『本发明的目的在于提供一种…以解决…』, 两种句式均合法)"),
    ("技术领域", r"(?:具体涉及|尤其涉及)一种",
     "技术领域段缺 A 类槽位『本发明涉及〔领域〕技术领域，具体涉及一种〔正式题名〕。』"),
    ("说明书摘要", r"公开了一种",
     "说明书摘要缺 A 类槽位『……公开了一种〔正式题名〕，……』"),
]


def check_a_slot_presence(lines: list[str], sections: dict, report: Report,
                          stage: str) -> None:
    """规则 31b (1级 hard): A 类槽位存在性 (G8-0b; 2026-09-01 补).

    与规则 31 的分工: 规则 31 = 槽位**内容**逐字一致(写了的地方对不对);
    本规则 = 槽位**存在性**(该写的地方在不在)。两条并存, 各报各的。

    ⚠️ 技术领域/说明书摘要在分离式工作流下可能存放于 `权要稿.md`(不在 `全文稿.md`),
    故本规则只在该章节**存在于本文件**时才判其槽位 —— 章节整体缺失属分节落位问题,
    由 check_cross_block / verify_docx_skeleton 管, 不在此重复报。
    仅 full-draft。
    """
    if stage != "full-draft":
        return
    text_all = "\n".join(lines)
    if count_chinese(text_all) < 1000:
        return  # fixture / 草稿豁免, 与 L8-1 字数条同口径
    for sec, pat, msg in _A_SLOT_PRESENCE:
        body, offset = get_section_lines(lines, sections, sec)
        if offset < 0:
            continue  # 该章节不在本文件(分离式存放于权要稿.md), 不判
        if not re.search(pat, "\n".join(body)):
            report.add(
                "G8-0b", f"{sec}(A 类槽位缺失)", f"『{pat}』在该章节零命中",
                msg + " —— 该槽位代表整件发明, 属 A 类必写(G8-0b); "
                "规则 31 只校验已写槽位的题名逐字一致, 整段漏写由本规则拦",
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
    """规则 34 (suspect): 标定工况线索 (G6-1 W14, 2026-09-02 起按档位判).

    旧口径"标定四维度全写(来源/纳排/数量/数量依据)"已废止(H2608165 王工定稿实践:
    约十五个参数全套四维度是篇幅失控首要根因, 王工整类压成一句). 现行口径按
    implementation.md L8-1 落笔预算条三档判: 第一档(权要点名预设)须有标定工况一句
    (样本来源+样本数量); 数量依据/纳排条件属默认不写项, 审核人点名才补, 不再探测.
    本探测器只探"触发了标定叙述却连标定工况(来源或数量)都没有"的线索, 豁免判据
    由旧四项收敛为两项. 仅 full-draft.
    """
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    trig_pat = re.compile(r"标定|由[^，。；]{0,20}历史[^，。；]{0,10}(数据|样本)[^，。；]{0,10}确定")
    dims = [
        ("样本来源", re.compile(r"同型号|同一型号|同功率|工况|历史切换|出厂|采集自")),
        ("样本数量", re.compile(r"不少于\s*\d+|不低于\s*\d+|\d+\s*(次|组|个)(完整|历史|样本)?")),
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
                f"标定叙述疑似缺标定工况: {missing}; 第一档(权要点名预设)须给标定工况一句"
                "(样本来源+数量). 数量依据/纳排条件默认不写(W14 按档位判, 2026-09-02)",
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



def check_cross_step_numeric_selfconsistency(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 39 (suspect): 跨公式/跨步骤数值自洽线索 (G6-1, W53).

    ① 示例值代入验算: 对披露了具体示例值的除法/减法等简单关系, 尝试两两做粗略
    一致性判读 (如 b 与 q 已给示例、且 |q-b| 与 r 亦给示例时, 校验 |q-b|/b ≈ r).
    ② 量级一致性: 同一特征向量/数据集内不同来源分量的数值量级差悬殊 (如均值分量
    与方差分量相差 >=3 个数量级) 且附近无"标准化/归一化"说明时出线索.
    ③ 稀疏/全量口径冲突: 同一链上出现"仅含异常事件/仅记录偏差/稀疏"与
    "逐帧/全部帧/完整序列/每帧"类同现且无"完整序列作为共同切分对象"式澄清时出线索.
    仅 full-draft. 三子项均只报线索, 由 auditor 判是否 FAIL.
    """
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    # ③ 稀疏×全量口径冲突 (本项目实例: S11 稀疏刷新率序列 vs S13 逐帧统计)
    sparse_pat = re.compile(r"仅(将|记录|含|对|只).{0,14}(异常|稀疏|偏差|延迟|部分)|稀疏[^，。；]{0,8}序列|只记录异常")
    full_pat = re.compile(r"逐帧|全部帧|完整[^，。；]{0,8}(帧|序列|数据)|所有帧|每一帧|每帧")
    exempt_pat = re.compile(r"完整[^，。；]{0,16}(作为|作为时序|共同(切分|统计)?对象)|完整[^，。；]{0,16}共同对象|以[^，。；]{0,20}完整[^，。；]{0,10}作为")
    full_text_body = "\n".join(body)
    # 全文级豁免: 写稿者已明确"以完整帧序列作为时序切分与色彩统计的共同对象"则稀疏说明自洽
    global_exempt = bool(re.search(r"完整[^，。；]{0,16}作为[^，。；]{0,8}共同[^，。；]{0,6}(切分|统计)?对象|共同[^，。；]{0,6}(切分|统计)?对象", full_text_body))
    for i, ln in enumerate(body):
        if not sparse_pat.search(ln):
            continue
        lo, hi = max(0, i - 2), min(len(body), i + 3)
        window_lines = body[lo:hi]
        window = "\n".join(window_lines)
        if exempt_pat.search(window) or global_exempt:
            continue
        if full_pat.search(window):
            report.add_suspect(
                "G6-1", f"具体实施方式 第{offset + i + 1}行", ln.strip()[:60],
                "疑似稀疏(仅异常事件)切分对象与逐帧/完整序列消费对象发生冲突; 跨步骤数据流"
                "粒度/口径须自洽, 明确以完整帧序列作为时序切分与色彩统计的共同对象(W53③). "
                "已写明完整序列作为共同切分对象可豁免",
                suspect_id="S-W53-numeric", section="L8", owner="impl",
                missing_dimensions=["跨步骤数据流口径一致"],
            )
            break  # 同一链只报一次
    # ② 量级一致性: 均值分量与方差分量同现且量级差悬殊, 附近无标准化说明
    mean_pat = re.compile(r"均值(特征向量|分量|.*)|色彩均值")
    var_pat = re.compile(r"方差(特征向量|分量|.*)|色彩方差")
    norm_pat = re.compile(r"标准化|归一化|Z-score|零均值|单位方差")
    for i, ln in enumerate(body):
        if not (mean_pat.search(ln) and var_pat.search(ln)):
            continue
        lo, hi = max(0, i - 1), min(len(body), i + 4)
        window = "\n".join(body[lo:hi])
        if norm_pat.search(window):
            continue
        # 量级证据: 均值分量示例量级(计数级) vs 方差分量示例量级(计数平方级)
        if re.search(r"像素总数的平方|像素频次平方|平方量级|量级差(异|悬)", "\n".join(body[max(0,i-3):min(len(body),i+4)])):
            report.add_suspect(
                "G6-1", f"具体实施方式 第{offset + i + 1}行", ln.strip()[:60],
                "均值分量与方差分量数值量级差悬殊(计数级 vs 计数平方级)且未说明是否标准化/归一化; "
                "拼接后直接做后续分析会使方差分量主导判别, 须补标准化/归一化说明(W53②)",
                suspect_id="S-W53-numeric", section="L8", owner="impl",
                missing_dimensions=["量级一致性/标准化说明"],
            )
            break


def check_category_label_consistency(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 40 (suspect): 类别/标签前后一致线索 (G6-1, W54).

    同一处理链上训练标签、中间类别、输出类别须逐字一致. 检测"训练样本(标记|标注)为
    X 和 Y" 与 "位于超平面正向→上升趋势/负向→下降趋势" 类跨段类别名漂移.
    仅 full-draft."""
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    train_pat = re.compile(r"训练(样本|过程|阶段)[^，。；]{0,30}(标记|标注|分为|为)")
    out_pat = re.compile(r"正向(一侧|侧)|负向(一侧|侧)|上升趋势|下降趋势")
    for i, ln in enumerate(body):
        m = train_pat.search(ln)
        if not m:
            continue
        train_labels = ln[m.end():m.end() + 40]
        lo, hi = i, min(len(body), i + 6)
        window = "\n".join(body[lo:hi])
        if re.search(r"上升趋势|下降趋势", window) and not re.search(r"上升趋势样本|下降趋势样本", window):
            report.add_suspect(
                "G6-1", f"具体实施方式 第{offset + i + 1}行", ln.strip()[:60],
                f"训练标签 '{train_labels.strip()[:20]}' 与输出类别(上升/下降趋势)疑似类别名不一致; "
                "训练标签、中间类别、输出类别须同一套名称、逐字一致, 否则下游判定口径冲突(W54)",
                suspect_id="S-W54-label", section="L8", owner="impl",
                missing_dimensions=["类别/标签前后一致"],
            )
            break


def check_function_noun_first_definition(lines: list[str], sections: dict, report: Report, stage: str, claims_text: str = "") -> None:
    """规则 41 (suspect): 自造功能名词首现定义线索 (G6-1, W55).

    解释段承担判据/功能作用的非权要非交底书名词短语(如"频次分布特征向量""分类得分
    (绝对值)"), 若仅在判定句中作为判据出现、而全文无其定义/生成来源, 出线索.
    仅在同时出现"以…为标志/作为…判定/用…判定/取…作为阈值"等判据句式时触发, 避免误报.
    仅 full-draft."""
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    judge_pat = re.compile(r"以[^，。；]{2,14}(为标志|作为|判定|确定)|取[^，。；]{2,14}作为|作为[^，。；]{2,14}判定依据|用[^，。；]{2,14}判定")
    # 疑似自造的判据名词: 含"向量/特征/矩阵/值"且非"特征偏移量集合/量化记录数值/色彩均值/色彩方差"等白名单
    suspicious_noun = re.compile(r"(频次分布特征向量|分类得分|得分绝对值|偏移量变化幅度|波动特征向量|异常度|置信得分)")
    for i, ln in enumerate(body):
        if not judge_pat.search(ln):
            continue
        sm = suspicious_noun.search(ln)
        if not sm:
            continue
        noun = sm.group(1)
        # 全文是否已有该名词的生成/定义来源(在前文出现"得到/计算/构建…名词"或"名词, 即")
        full_text = "\n".join(body)
        defined = bool(re.search(r"(得到|计算|构建|提取|生成|确定)[^，。；]{0,20}" + re.escape(noun) + r"|" + re.escape(noun) + r"[^，。；]{0,8}(为|指|即|由)", full_text))
        if not defined:
            report.add_suspect(
                "G6-1", f"具体实施方式 第{offset + i + 1}行", ln.strip()[:60],
                f"判据名词 '{noun}' 在判定句中作为判据出现, 但全文未见其定义/生成来源; "
                "须补充首现定义或改写为已有术语(W55). 已在前文定义可豁免",
                suspect_id="S-W55-function-noun", section="L8", owner="impl",
                missing_dimensions=["首现定义"],
            )
            break

# 规则 42 判据 (implementation.md L8-1 解释段段落行数区间): 四号宋体 1.5 倍行距、
# 正文宽 ≈16.9cm 换行折算 ≈34 字/行. ★ 王工 H2609029 定稿轮给全区间「正常 5-10 行,
# 最多不超过 15 行; 解释同一部分内容的就不要拆分两个段落」(原话), 故上限由 7 行(240 字)
# 放宽为 15 行(≈510 字); 下限 5 行(≈170 字) 与「一句话一段/一行」属语义项, 交 impl-auditor
# (机械判会误伤王工定稿保留的短解释段, 实测 19 段 <3 行中多为合规项).
# 豁免段前缀: Sxx 框架句/展开段入口句 (按权 1/从权分句逐字, 行数跟随分句)、
# 收尾"综上所述"方法与三段法律套话、图导引句.
_IMPL_PARA_EXEMPT_PREFIX = (
    "综上所述", "以下所述", "以上所述", "本发明第二实施例", "第二方面",
    "图1为", "图1为本", "如图1", "下面将结合",
)
# 解释段段落长度硬上限 (≈34 字/行 × 15 行); 王工 2026-09-11 H2609029 定稿轮口径。
IMPL_PARA_MAX_CHARS = 510
_IMPL_PARA_ENTRY_RE = re.compile(r"^(在步骤S\d+中|在一个实施方式中|在一种实施方式中).*，包括：$")


def check_dash_and_special_symbols(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 48 (1级): 破折号与特殊符号 (G5-1 形式标点条, 王工 H2608165 批注 5).

    王工原话「全文不要使用破折号，以及其他特殊的符号」. 范围连接写「至」, 要解释
    直接跟在句子后面. 全角破折号 —/—— 在专利正文无合法用途, 命中即 FAIL.
    半角连字符-不查(公式LaTeX/英文连写字/日期合法), 顿号分句由 auditor 语义判
    (机械正则无法区分名词列举与子句连接, 保零误报).
    """
    if stage != "full-draft":
        return
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        for i in range(start, end):
            if "—" in lines[i]:
                report.add(
                    "G5-1", f"{label} 第{i + 1}行", lines[i].strip()[:80],
                    "出现破折号; 全文不用破折号与其他特殊符号, 范围连接写「至」,"
                    "解释直接跟在句子后面 (王工 H2608165 批注 5)",
                )


# 冒号引导的举例/过程句式: 「过程为：」「具体如下：」「步骤如下：」等 (G5-1 形式
# 标点条, 王工 H2608165 批注 9 原话「不要用'过程为：''具体如下：'等等带冒号的举例
# 表述，直接讲具体过程是什么就好了」). 匹配句中任意位置的引导短语+中文冒号收尾,
# 不限行首——批注 9 的实例即落在句中 (「其确定过程为：」).
COLON_LEAD_PAT = re.compile(
    r"(确定过程为|标定过程为|计算过程为|处理过程为|操作过程为|过程为|具体如下|步骤如下|如下式|表达如下"
    # ★ 2026-09-19 扩充（H2609100 实测）：原词表只收了「过程为／具体如下／步骤如下」一类，
    #   而同一形态的「其**确定方式为**：」「其**构建方式为**：」「**生成方式为**：」
    #   「按如下**方式**预先标定：」一个都抓不到——该案全文 11 处这类引导句在闸门上
    #   全部静默通过，是人工通读才发现的。同属王工 H2608165 批注 9 针对的
    #   「带冒号的举例/过程引导表述，直接讲具体过程是什么就好了」，故一并收入。
    #   边界：只收「引导短语＋冒号」，不收合法冒号（公式引导句末「…为：」是 G6-1 明文
    #   要求、「包括：」是范式/法定体例、模板句「具有如下有益效果：」），三者不在词表内。
    r"|确定方式为|构建方式为|生成方式为|标定方式为|计算方式为|处理方式为|操作方式为|如下方式|方式如下"
    #   「按如下方式预先标定：」这类引导短语与冒号之间还夹着动词，故再补一条**带间隔**的式
    #   （间隔限 10 字且不得跨越句读）。不收宽泛的「如下」——模板句「具有如下有益效果：」
    #   会误报，故只认「按如下方式」这一具体引导语。
    r"|按如下方式[^，。；：]{0,10})"
    r"[：:]")


def check_colon_lead_phrases(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 49 (1级): 冒号引导的举例/过程句式 (G5-1 形式标点条, 王工 H2608165 批注 9).

    「过程为：」「具体如下：」等带冒号的举例表述一律改为直接陈述 (「其标定通过
    在……」). ⚠️ 与规则 10 (名词冒号定义句式) 分工: 规则 10 查行首短名词+冒号,
    本条查句中引导短语+冒号, 两正则不重叠. 扫描范围含权要三章外的全部章节
    (形式标点条约束说明书摘要/发明内容/具体实施方式; 权要章节法定体例不适用,
    但权要内出现「过程为：」同样违规, 一并扫).
    """
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        for i in range(start, end):
            m = COLON_LEAD_PAT.search(lines[i])
            if m:
                report.add(
                    "G5-1", f"{label} 第{i + 1}行", lines[i].strip()[:80],
                    f"冒号引导的举例/过程句式「{m.group(0)}」; 改为直接陈述具体过程,"
                    "不带冒号引导 (王工 H2608165 批注 9)",
                )


def check_long_parenthetical(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 50 (suspect): 长括号插入语线索 (G5-1 形式标点条, 王工 H2608165 批注 20).

    王工原话「长句解释直接跟在后面，不要用括号」——括号插入语改为「，当……时，」
    「，即……，」接入主句. 判据: 括号内 ≥15 字的汉字内容属"长句解释"线索; 短括号
    (单位标注、简称、数值单位) 不报. 只报线索由 auditor 复核——机械判据分不出
    "可保留的公式符号说明"与"该改从句的长解释", 保零误报交人工.
    仅 full-draft.
    """
    if stage != "full-draft":
        return
    pat = re.compile(r"（([^（）]{15,})）")
    for label, start, end in _get_scan_ranges(lines, sections, stage):
        for i in range(start, end):
            m = pat.search(lines[i])
            if m:
                inner = m.group(1)
                # 括号内纯公式符号/单位说明特征 (LaTeX/单位/数字占比高) 不报:
                # 保留公式五项「(单位: 米)」「(无量纲)」式合法短标注, 长度阈值已滤掉大部分
                cjk = len(re.findall(r"[一-鿿]", inner))
                if cjk < 10:
                    continue
                report.add_suspect(
                    "G5-1", f"{label} 第{i + 1}行", lines[i].strip()[:60],
                    f"疑似长括号插入语 ({len(m.group(0))} 字): 长句解释改为「，当……时，」"
                    "或「，即……，」接入主句; 单位/符号短标注可豁免 (王工 H2608165 批注 20)",
                    suspect_id="S-G5-long-parenthetical", section="L8", owner="impl",
                )


def check_impl_para_lines(lines: list[str], sections: dict, report: Report, stage: str) -> None:
    """规则 42 (1级 hard): 解释段段落行数上限 (L8-1).

    具体实施方式章节内正文段 (v2 基线每行一段) 纯汉字 >510 字 (≈34字/行×15行)
    即直接 hard FAIL、阻断闸门 —— 段落行数属确定性可判规则, 豁免段 (Sxx 框架
    句/展开段入口句/收尾套话/图导引句) 已在探测器内预过滤, 无歧义, 不交 auditor
    复核. 说明书摘要受 L4 ≤300 字约束、不在本规则范围. 仅 full-draft.
    """
    if stage != "full-draft":
        return
    body, offset = _impl_body(lines, sections)
    if offset < 0:
        return
    for i, ln in enumerate(body):
        stripped = ln.strip()
        if not stripped:
            continue
        if re.search(r"^S\d+，", stripped) or _IMPL_PARA_ENTRY_RE.search(stripped):
            continue  # Sxx 框架句 / 展开段入口句 (按分句逐字, 行数跟随分句)
        if stripped.startswith(_IMPL_PARA_EXEMPT_PREFIX):
            continue
        cjk = len(re.findall(r"[一-鿿]", stripped))
        if cjk > IMPL_PARA_MAX_CHARS:
            report.add(
                "L8-1", f"具体实施方式 第{offset + i + 1}行", stripped[:60],
                f"解释段单段纯汉字 >{IMPL_PARA_MAX_CHARS} 字(≈34字/行×15行上界), 超 ≤15 行上限; "
                "按语义自然断点(对图像通路/对文本通路、随后/最后等动作或对象切换处)"
                "拆分为多个 ≤7 行独立段, 或精简冗余展开(L8-1 解释段段落行数上限)",
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
    # 注: 返修轮 (权要二稿/三稿、全文二稿/三稿) 改动了权要时必须另跑一次
    #     --stage claims-draft --md 权要稿.md, 否则本段 L1 机械规则全部跳过
    #     (SKILL.md 返修工作流 step 4 已定为无条件跑两套).
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
        check_no_specific_values_in_claims(lines, sections, report)
        check_claims_preset_budget(lines, sections, report)      # 规则 43 (claims-requirements L1-1)
        check_claim_wording_seven(lines, sections, report)        # 规则 44 (claims-requirements L1-1 措辞七条)
        check_claim_boilerplate(lines, sections, report)           # 规则 51 (权10 系统权逐字 + 介质权禁写, boilerplate.py)
        check_claim_pronoun_qidai(lines, sections, report)       # 规则 56 (权要「其/该」代指 hard)
        check_claim1_referent_basis(lines, sections, report)     # 规则 57 (权 1「所述」引用基础 suspect)
        check_claim1_step_action_density(lines, sections, report)  # 规则 53 (单步子动作密度 suspect)

    check_forbidden_words(lines, sections, report, stage)
    check_spec_no_debuzou(lines, sections, report, stage)      # 规则 46 (王工全文口径)
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
    check_boilerplate_verbatim(lines, sections, report, stage, claims_text)   # 规则 47 (模板句逐字, boilerplate.py)
    check_benefit_enumeration(lines, sections, report, stage)
    check_benefit_item_pattern(lines, sections, report, stage)
    check_benefit_count_and_length(lines, sections, report, stage)   # 规则 52 (恰 3 项 hard / 字数 suspect)
    check_judgment_sentence_pattern(lines, sections, report, stage)
    check_substep_numbering(lines, sections, report, stage)
    check_benefit_generic_phrases(lines, sections, report, stage)
    check_problem_echo(lines, sections, report, stage)
    check_spec_no_claims_wording(lines, sections, report, stage)
    check_second_aspect_boilerplate(lines, sections, report, stage, claims_text)
    check_invention_name_slots(lines, sections, report, stage, invention_name)
    check_a_slot_presence(lines, sections, report, stage)
    # 形式标点 (G5-1 形式标点条, 王工 H2608165 批注 5/9/20; 破折号与冒号引导为
    # 1级 hard, 长括号插入语为 suspect)
    check_dash_and_special_symbols(lines, sections, report, stage)   # 规则 48
    check_colon_lead_phrases(lines, sections, report, stage)          # 规则 49
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
    check_cross_step_numeric_selfconsistency(lines, sections, report, stage)  # W53
    check_sampling_nyquist(lines, sections, report, stage)                    # 规则 54 (数值三问机械半边)
    check_category_label_consistency(lines, sections, report, stage)             # W54
    check_function_noun_first_definition(lines, sections, report, stage, claims_text)  # W55
    check_long_parenthetical(lines, sections, report, stage)          # 规则 50 (suspect, 批注 20)
    check_pronoun_qizhong(lines, sections, report, stage)             # 规则 55 (「其中」代指, H2609029)
    check_bare_pronoun(lines, sections, report, stage)                # 规则 58 (「其/该」纯代词, H2609100)
    check_claim_number_spacing(lines, sections, report)               # 规则 59 (权要编号后空白, H2609100)
    check_unconventional_symbols(lines, sections, report, stage)      # 规则 60 (非常规符号白名单, H2609100)
    check_math_wording(lines, sections, report, stage)                # 规则 61 (数学表达文字化, H2609100)
    # 规则 42 (1级 hard): 解释段段落行数上限 (L8-1) —— 确定性可判, 不交 auditor
    check_impl_para_lines(lines, sections, report, stage)

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
    # Windows GBK 控制台: 报告含 ⚠/全角空格等 GBK 外字符, 裸跑会 UnicodeEncodeError
    # 且 stdout 半截/为空, --json 消费方解析失败 (H2609029 实测, 2026-09-10)。
    # 强制 UTF-8 输出, 与 PYTHONIOENCODING=utf-8 等效但不依赖调用方带环境变量。
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())

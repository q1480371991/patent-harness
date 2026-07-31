#!/usr/bin/env python3
"""全文稿 md → 专利模板 DOCX 就地注入（摘要 / 发明内容 / 附图说明 / 具体实施方式）。

承担全文稿章节（L4 摘要 + L6 发明内容 + L7 附图说明 + L8 具体实施方式）的 DOCX
就地下笔，根治两类手写即兴 bug：① 行内 `$...$` 公式漏编译成原生 OMML；② md 单换行
分隔的子步骤被挤进同一段。权要三章（权利要求书 / 技术领域 / 背景技术）仍由 docx
执行层手填（SKILL.md 权要一稿 step 10 不动）。

设计约束（规则出处 docx-template.md G8-0/G8-0b/G8-1、global.md G6-1、案例 C-DOCX-7/8）：
- 不用 paraId 定位（WPS 再保存重排 paraId），改用 5 个 `<w:sectPr>` 序数 + 段内文本
  特征定位（与 insert_figures_docx.py 同一已验证机制）。
- 不清空 body、不删 sectPr / header / headerReference：摘要就地替换分节1占位段；L6-L8
  在分节4末个 sectPr 段前追加，并清掉模板预置的 `......` 占位套话段。
- 块公式（L8 独立成段的 LaTeX，无 `$`）：复用 omml_formulas.gen_omml_paragraphs 取整段
  `<w:p>…<m:oMathPara>…</w:p>`，不加 w:jc、不加 pStyle（G8-3）。
- 行内公式（`$…$`）：每条唯一片段经 gen 生成后取内层 `<m:oMath>` 子元素，按 `$…$` 拆段
  与文本 run 平级混排（字符串天然不可变 = deepcopy）。
- pandoc 不可用：块公式回退纯 LaTeX 文本（Times New Roman）、行内回退去 `$` 纯文本，
  完工报告注明（G6-1）。
- 默认一次性注完（输入是已过 md 闸门的审定全文稿）；`--block 章节` 可只注单章节调试。

用法：
    python3 scripts/inject_fulltext_docx.py <unpack目录> --md docs/全文稿.md
    python3 scripts/inject_fulltext_docx.py <unpack目录> --md docs/全文稿.md --block 具体实施方式
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# 复用同仓 scripts 既有模块（sys.path[0] = scripts/）
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import omml_formulas  # noqa: E402
from insert_figures_docx import find_paragraph_span  # noqa: E402


# ---------------------------------------------------------------- 格式常量（G8-0b）

_SONG = (
    '<w:rPr><w:rFonts w:hint="eastAsia" w:ascii="宋体" w:hAnsi="宋体" '
    'w:eastAsia="宋体" w:cs="宋体"/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr>'
)
_SONG_BOLD = (
    '<w:rPr><w:rFonts w:hint="eastAsia" w:ascii="宋体" w:hAnsi="宋体" '
    'w:eastAsia="宋体" w:cs="宋体"/><w:b/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr>'
)
_HEADING_PPR = (
    '<w:pPr><w:spacing w:line="360" w:lineRule="auto"/>'
    '<w:ind w:left="0" w:leftChars="0" w:firstLine="0" w:firstLineChars="0"/>'
    + _SONG_BOLD + '</w:pPr>'
)
_BODY_PPR = (
    '<w:pPr><w:spacing w:line="360" w:lineRule="auto"/>'
    '<w:ind w:firstLine="560" w:firstLineChars="200"/>'
    + _SONG + '</w:pPr>'
)
_FALLBACK_MATH_RPR = (
    '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
    'w:cs="Times New Roman"/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr>'
)

# md 章节标题 → 分节落位（G8-0 对照表）。摘要附图章节正文不注入（图1由
# insert_figures_docx.py 单独注到分节2/5），仅作章节边界标记跳过。
SECTION_TITLES = ("说明书摘要", "摘要附图", "发明内容", "附图说明", "具体实施方式")
# 落位：说明书摘要 → 分节1（首个 sectPr 段前的占位段就地替换）；
# 发明内容/附图说明/具体实施方式 → 分节4（末个 sectPr 段前追加，并删模板 ...... 占位套话）。
_BLOCK_FORMULA_RE = re.compile(r"^[A-Za-z\\]")
_INLINE_RE = re.compile(r"\$([^$\n]+)\$")


# ---------------------------------------------------------------- md 解析

def parse_fulltext_md(md_path: Path) -> list[dict]:
    """全文稿 md → Block 列表。Block = {kind, text, latex?, section}。

    策略：每行各自成段（契合 v2 基线：md 单换行分隔的子步骤各自一个 <w:p>）。
    空行仅作可读分隔、不产出；front-matter 跳过；`## ` 切章节标题；块公式启发式 =
    行首 [A-Za-z\\] + 含 \\命令 + 无 $；其余为正文段。「摘要附图」章节正文跳过。
    """
    raw = md_path.read_text(encoding="utf-8")
    # 剥 YAML front-matter（--- ... ---）
    if raw.startswith("---"):
        end = raw.find("\n---\n", 4)
        if end != -1:
            raw = raw[end + len("\n---\n"):]

    blocks: list[dict] = []
    section = None
    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            section = title if title in SECTION_TITLES else section
            blocks.append({"kind": "heading", "text": title, "section": section})
            continue
        # 摘要附图章节正文（图1 占位）不注入，由 insert_figures_docx.py 注图
        if section == "摘要附图":
            continue
        if _BLOCK_FORMULA_RE.match(stripped) and "\\" in stripped and "$" not in stripped:
            blocks.append({"kind": "block_formula", "text": stripped, "latex": stripped,
                           "section": section})
        else:
            blocks.append({"kind": "paragraph", "text": stripped, "section": section})
    return blocks


def collect_latex(blocks: list[dict]) -> tuple[list[str], list[str]]:
    """返回 (块公式 latex 列表, 行内 $...$ 去重 latex 列表)。顺序稳定。"""
    block_list: list[str] = []
    inline_seen: set[str] = set()
    inline_list: list[str] = []
    for b in blocks:
        if b["kind"] == "block_formula":
            block_list.append(b["latex"])
        elif b["kind"] == "paragraph":
            for m in _INLINE_RE.finditer(b["text"]):
                latex = m.group(1)
                if latex not in inline_seen:
                    inline_seen.add(latex)
                    inline_list.append(latex)
    return block_list, inline_list


# ---------------------------------------------------------------- OMML 表

def build_omml_tables(block_list: list[str], inline_list: list[str],
                      pandoc: str | None) -> tuple[dict, dict, bool]:
    """返回 (block_para_xml: latex→整段<w:p>, inline_omath: latex→内层<m:oMath>, fallback)。

    pandoc 缺失时走 G6-1 回退：表为空、fallback=True，渲染层把公式当纯文本写。
    """
    fallback = pandoc is None
    block_xml: dict[str, str] = {}
    inline_xml: dict[str, str] = {}
    if fallback:
        return block_xml, inline_xml, True
    if block_list:
        items = [{"latex": lx, "number": None} for lx in block_list]
        for it, r in zip(items, omml_formulas.gen_omml_paragraphs(items, pandoc)):
            block_xml[it["latex"]] = r["xml"]  # 整段 <w:p>…<m:oMathPara>…</w:p>
    for lx in inline_list:
        items = [{"latex": lx, "number": None}]
        r = omml_formulas.gen_omml_paragraphs(items, pandoc)[0]
        m = re.search(r"<m:oMath>.*?</m:oMath>", r["xml"], re.S)
        if not m:
            raise RuntimeError(f"行内公式未取到内层 <m:oMath>：{lx}")
        inline_xml[lx] = m.group(0)
    return block_xml, inline_xml, False


# ---------------------------------------------------------------- 渲染

def _text_run(text: str, rpr: str = _SONG) -> str:
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def render_heading_xml(title: str) -> str:
    return f'<w:p>{_HEADING_PPR}{_text_run(title, _SONG_BOLD)}</w:p>'


def render_block_formula_xml(para_xml: str, latex: str, fallback: bool) -> str:
    """块公式段：pandoc 可用取整段 OMML（不加 jc/pStyle，G8-3）；否则回退纯 LaTeX 文本。"""
    if fallback:
        return f'<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/>' \
               f'<w:ind w:firstLine="0" w:firstLineChars="0"/>{_FALLBACK_MATH_RPR}</w:pPr>' \
               f'<w:r>{_FALLBACK_MATH_RPR}<w:t xml:space="preserve">{escape(latex)}</w:t></w:r></w:p>'
    return para_xml  # gen 已剥 pStyle；不加 w:jc


def render_paragraph_xml(text: str, inline_table: dict, fallback: bool) -> str:
    """正文段：按 $...$ 拆段，文本 run 与 <m:oMath> 平级混排。无公式时单文本 run。"""
    if not _INLINE_RE.search(text):
        return f'<w:p>{_BODY_PPR}{_text_run(text)}</w:p>'
    runs: list[str] = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            runs.append(_text_run(text[pos:m.start()]))
        latex = m.group(1)
        if fallback or latex not in inline_table:
            runs.append(_text_run(m.group(0)))  # 回退：保留 $...$ 原样纯文本
        else:
            runs.append(inline_table[latex])  # <m:oMath>…</m:oMath> 平级嵌入
        pos = m.end()
    if pos < len(text):
        runs.append(_text_run(text[pos:]))
    return f'<w:p>{_BODY_PPR}{"".join(runs)}</w:p>'


def render_blocks(blocks: list[dict], block_table: dict, inline_table: dict,
                  fallback: bool) -> list[str]:
    """Block 列表 → <w:p> 字符串列表（保持 md 顺序）。"""
    out: list[str] = []
    for b in blocks:
        if b["kind"] == "heading":
            out.append(render_heading_xml(b["text"]))
        elif b["kind"] == "block_formula":
            out.append(render_block_formula_xml(
                block_table.get(b["latex"], ""), b["latex"], fallback))
        else:
            out.append(render_paragraph_xml(b["text"], inline_table, fallback))
    return out


def split_by_section(blocks: list[dict]) -> dict[str, list[dict]]:
    """按章节分组 Block（标题段归该章节）。摘要附图章节正文已被 parse 跳过。"""
    by_sec: dict[str, list[dict]] = {}
    cur = None
    for b in blocks:
        if b["kind"] == "heading" and b["section"] in SECTION_TITLES:
            cur = b["section"]
            by_sec.setdefault(cur, []).append(b)
        elif cur is not None:
            by_sec[cur].append(b)
    return by_sec


# ---------------------------------------------------------------- 注入

_SECTPR_RE = re.compile(r"<w:sectPr[ >]")
_PLACEHOLDER_QMARK = "......"
# 模板预置占位套话特征（带 ...... 的系统用于执行 / 装置实施例 / 具体实施例段）
_PLACEHOLDER_PATTERNS = (
    "......系统用于执行",
    "以上所描述的装置实施例",
    "以上所述的具体实施例",
)


def _section_sectpr_positions(doc: str) -> list[int]:
    """5 个 <w:sectPr> 起始位置（升序）。"""
    return [m.start() for m in _SECTPR_RE.finditer(doc)]


def inject(unpacked_dir: Path, rendered_by_section: dict[str, list[str]],
           stats: dict) -> dict:
    """就地注入：摘要→分节1；发明内容/附图说明/具体实施方式→分节4末 sectPr 前。

    保留所有 sectPr / headerReference / header*.xml；不清空 body。
    """
    doc_path = unpacked_dir / "word" / "document.xml"
    doc = doc_path.read_text(encoding="utf-8")

    sect_positions = _section_sectpr_positions(doc)
    if len(sect_positions) != 5:
        raise SystemExit(
            f"ERROR\tsectPr 数量 {len(sect_positions)}（模板家族应为 5），停止注入"
        )

    abstract_paras = rendered_by_section.get("说明书摘要", [])
    body_paras = (
        rendered_by_section.get("发明内容", [])
        + rendered_by_section.get("附图说明", [])
        + rendered_by_section.get("具体实施方式", [])
    )

    # ---- 分节1（摘要正文）：替换首个 sectPr 段之前的非 sectPr 占位段 ----
    if abstract_paras:
        p1_start, p1_end = find_paragraph_span(doc, sect_positions[0])
        region = doc[:p1_start]
        # 删除该区域内现有 <w:p>…</w:p>（模板空占位段），保留首个 sectPr 段本身
        region_clean = re.sub(r"<w:p\b[^>]*>.*?</w:p>", "", region, flags=re.S)
        doc = region_clean + "".join(abstract_paras) + doc[p1_start:]
        stats["abstract_paragraphs"] = len(abstract_paras)

    # ---- 分节4（发明内容/附图说明/具体实施方式）：删占位套话 + 末 sectPr 前追加 ----
    if body_paras:
        sect_positions = _section_sectpr_positions(doc)
        p4_start, p4_end = find_paragraph_span(doc, sect_positions[3])
        region = doc[:p4_start]
        # 删模板预置的 ...... 占位套话段（按文本特征，保留真实背景技术段）
        def _drop_placeholder(m: re.Match) -> str:
            seg = m.group(0)
            txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", seg))
            if _PLACEHOLDER_QMARK in txt or any(p in txt for p in _PLACEHOLDER_PATTERNS):
                stats["placeholders_removed"] += 1
                return ""
            return seg
        region = re.sub(r"<w:p\b[^>]*>.*?</w:p>", _drop_placeholder, region, flags=re.S)
        doc = region + "".join(body_paras) + doc[p4_start:]
        stats["body_paragraphs"] = len(body_paras)

    doc_path.write_text(doc, encoding="utf-8")
    stats["sectpr_kept"] = len(_section_sectpr_positions(doc))
    return stats


# ---------------------------------------------------------------- 主流程

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("unpacked", type=Path, help="docx skill 的 unpack 目录")
    parser.add_argument("--md", type=Path, required=True, help="已过闸门的审定全文稿.md")
    parser.add_argument("--block", choices=list(SECTION_TITLES), default=None,
                        help="只注指定单章节（调试用）；缺省一次性注完 L4+L6+L7+L8")
    args = parser.parse_args(argv)

    if not args.md.exists():
        raise SystemExit(f"ERROR\t全文稿 md 不存在：{args.md}")
    if not (args.unpacked / "word" / "document.xml").exists():
        raise SystemExit(f"ERROR\tunpack 目录无效：{args.unpacked}")

    pandoc = omml_formulas.find_pandoc()

    blocks = parse_fulltext_md(args.md)
    by_sec = split_by_section(blocks)
    block_list, inline_list = collect_latex(blocks)
    block_table, inline_table, fallback = build_omml_tables(block_list, inline_list, pandoc)

    rendered: dict[str, list[str]] = {}
    targets = [args.block] if args.block else ["说明书摘要", "发明内容", "附图说明", "具体实施方式"]
    for sec in targets:
        if sec in by_sec:
            rendered[sec] = render_blocks(by_sec[sec], block_table, inline_table, fallback)

    stats = {
        "paragraphs": sum(len(v) for v in rendered.values()),
        "block_omml": sum(1 for b in blocks if b["kind"] == "block_formula") if not fallback else 0,
        "inline_omath": sum(len(_INLINE_RE.findall(b["text"]))
                            for b in blocks if b["kind"] == "paragraph") if not fallback else 0,
        "abstract_paragraphs": 0,
        "body_paragraphs": 0,
        "placeholders_removed": 0,
        "sectpr_kept": 0,
        "fallback": fallback,
    }
    inject(args.unpacked, rendered, stats)

    mode = "一次性注入" if not args.block else f"分块注入({args.block})"
    pandoc_note = "pandoc 缺失，公式回退纯文本（G6-1，完工报告须注明）" if fallback else "pandoc 编译原生 OMML"
    print(f"OK\t{mode} · {stats['paragraphs']} 段 · "
          f"块公式 {stats['block_omml']} · 行内公式 {stats['inline_omath']} · "
          f"删占位套话 {stats['placeholders_removed']} · sectPr={stats['sectpr_kept']}")
    print(f"   · {pandoc_note}")
    if fallback:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

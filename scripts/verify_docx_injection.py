#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""verify_docx_injection.py — 全文稿 DOCX 注入后机械校验。

inject_fulltext_docx.py 注入 + insert_figures_docx.py 注图 + pack 之后、交付前跑一次，
机械断言注入质量，替代 AI 手动数 oMath / grep `$` 残留 / 查套话锚点。zipfile 直读
**磁盘 docx**（G8-3：不以 unpack 目录计数代替磁盘真相）。

断言项（任一不符 exit=1，打印差异明细）：
  - 块 `m:oMathPara` 数 == md 块公式数
  - 行内 `m:oMath` 数（总 oMath − oMathPara）== md `$...$` 实例数
  - `<w:sectPr>` 数 == 5（不破坏骨架，G8-0/G8-1）
  - 无 `$` 残留、无裸 LaTeX 源码残留（`\frac`/`\sum`/`\gamma` 等出现在 `<w:t>` 内）
  - 无中西文间空格（汉字与西文数字/字母间不得留空白，W-SPACE）
  - 章节标题齐全（发明内容/附图说明/具体实施方式 各 ≥1 段含 `<w:b/>`，且顶格 firstLine=0）
  - 套话锚点齐全（综上所述 / 本发明第二实施例 / 并不用于限定）
  - 图1 已注入（分节2 摘要附图 + 分节5 说明书附图各 ≥1 个 `<w:drawing>`）

pandoc 缺失走 G6-1 回退时（inject 退出码 3），公式断言自动放宽为「无 `$` 残留」即可。

用法：
    python3 scripts/verify_docx_injection.py <file.docx> --md docs/全文稿.md
    python3 scripts/verify_docx_injection.py <file.docx> --md docs/全文稿.md --fallback
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from inject_fulltext_docx import (  # noqa: E402
    parse_fulltext_md, collect_latex, _INLINE_RE,
)


def _read_docx(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as z:
        return z.read("word/document.xml").decode("utf-8", errors="replace")


def _all_text(doc: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", doc))


def _expect_md_counts(md_path: Path) -> tuple[int, int]:
    blocks = parse_fulltext_md(md_path)
    block_list, inline_list = collect_latex(blocks)
    # md 中 $...$ 实例总数（含重复，即注入后行内 oMath 应有数）
    inline_instances = sum(len(_INLINE_RE.findall(b["text"]))
                           for b in blocks if b["kind"] == "paragraph")
    return len(block_list), inline_instances


def check(docx_path: Path, md_path: Path, fallback: bool) -> list[tuple[str, bool, str]]:
    """返回 [(项名, ok, 明细)]。"""
    doc = _read_docx(docx_path)
    all_t = _all_text(doc)
    results: list[tuple[str, bool, str]] = []

    expect_block, expect_inline = _expect_md_counts(md_path)
    omp = len(re.findall(r"<m:oMathPara\b", doc))
    om_total = len(re.findall(r"<m:oMath\b", doc))
    om_inline = om_total - omp

    # 1) 公式数对账（回退模式只查无 $ 残留）
    if fallback:
        results.append(("公式(回退模式)", "$" not in all_t,
                        f"$ 残留数={all_t.count('$')}（回退模式应=0）"))
    else:
        results.append((f"块公式 oMathPara={omp}", omp == expect_block,
                        f"期望 {expect_block}，实际 {omp}"))
        results.append((f"行内 oMath={om_inline}", om_inline == expect_inline,
                        f"期望 {expect_inline}，实际 {om_inline}"))

    # 2) 骨架 sectPr=5
    sect = len(re.findall(r"<w:sectPr[ >]", doc))
    results.append((f"sectPr={sect}", sect == 5, f"期望 5，实际 {sect}"))

    # 3) 无 $ 残留、无裸 LaTeX 源码残留（正稿里任何 \frac/\sum/\gamma 都该在 OMML 内）
    dollar = all_t.count("$")
    latex_cmds = re.findall(r"\\[a-zA-Z]{2,}", all_t)
    results.append((f"$残留={dollar}", dollar == 0, f"$ 数={dollar}"))
    results.append((f"裸LaTeX残留={len(latex_cmds)}", len(latex_cmds) == 0,
                    f"命中：{latex_cmds[:5]}" if latex_cmds else "无"))

    # 3b) 中西文间空格（W-SPACE）：汉字/中文标点 与 数字/西文字母 之间不得留空白。
    # 症状来源三处：① md 撰写时手敲空格；② pandoc 编译公式边界带出空格；
    # ③ 在 WPS/Word 内手工编辑后回存。均在此处一次性兜住（zipfile 直读磁盘真相）。
    _CJK = r"一-鿿　-〿＀-￯"
    sp_hits = (re.findall(rf"[{_CJK}] +[0-9A-Za-z$\\]", all_t)
               + re.findall(rf"[0-9A-Za-z%$\\] +[{_CJK}]", all_t))
    results.append((f"中西文间空格={len(sp_hits)}", len(sp_hits) == 0,
                    f"命中样例：{sp_hits[:5]}" if sp_hits else "无"))

    # 4) 章节标题齐全（含 <w:b/> + 顶格 firstLine=0）
    for title in ("发明内容", "附图说明", "具体实施方式"):
        # 找文本==title 的段
        paras = re.findall(r"<w:p\b[^>]*>.*?</w:p>", doc, re.S)
        hit = None
        for p in paras:
            ts = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
            if ts.strip() == title:
                hit = p
                break
        if hit is None:
            results.append((f"标题「{title}」", False, "未找到该标题段"))
        else:
            has_b = "<w:b/>" in hit or "<w:b " in hit
            top_left = 'w:firstLine="0"' in hit and 'w:firstLineChars="0"' in hit
            results.append((f"标题「{title}」加粗+顶格",
                            has_b and top_left,
                            f"加粗={has_b} 顶格={top_left}"))

    # 5) 套话锚点齐全
    for anchor in ("综上所述", "本发明第二实施例", "并不用于限定"):
        results.append((f"套话「{anchor}」", anchor in all_t,
                        "缺失" if anchor not in all_t else "在"))

    # 6) 图1 注入（分节2 + 分节5 各 ≥1 drawing）—— 仅在 insert_figures 跑过后查
    drawings = len(re.findall(r"<w:drawing>", doc))
    results.append((f"图1 drawing={drawings}", drawings >= 2,
                    f"期望 ≥2（摘要附图+说明书附图），实际 {drawings}"))

    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("docx", type=Path, help="待校验的 .docx（pack 后磁盘文件）")
    ap.add_argument("--md", type=Path, required=True, help="注入用的全文稿.md（对账期望数）")
    ap.add_argument("--fallback", action="store_true",
                    help="pandoc 缺失回退模式：放宽公式数断言为仅查无 $ 残留")
    args = ap.parse_args(argv)

    if not args.docx.exists():
        print(f"[ERROR] docx 不存在：{args.docx}")
        return 2
    if not args.md.exists():
        print(f"[ERROR] md 不存在：{args.md}")
        return 2

    results = check(args.docx, args.md, args.fallback)
    print(f"== 全文稿注入校验: {args.docx} ==")
    n_fail = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            n_fail += 1
        line = f"  [{mark:>4}] {name}"
        if detail and not ok:
            line += f"  — {detail}"
        print(line)
    print("-" * 40)
    if n_fail == 0:
        print("结果: 注入机械项全部 PASS")
        return 0
    print(f"结果: {n_fail} 项 FAIL，需修正")
    return 1


if __name__ == "__main__":
    sys.exit(main())

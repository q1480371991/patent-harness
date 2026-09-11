#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_para_indent.py — 把指定段落的「首行缩进」清零（修 Word 再保存物化出的 firstLine=643）。

★ 立项（H2609029 / H2608165 两案定稿实测）：模板 Normal 样式带 `firstLineChars=200`（缩进 2 字），
段落只写 `firstLine=0` 而漏写 `firstLineChars=0` 时，**Word/WPS 再保存会把继承值物化**成
`firstLine=643`（≈2 个三号字）——发明名称段是**居中**的，一旦带这 2 字缩进就整体右移 1.13cm。
新注入的稿两个属性都写全、不会出；**老稿（或经 Word 手工编辑过的稿）会残留**，本脚本一次清掉。

用法：
    # 只查看（不改文件）：列出指定段落当前的缩进属性
    python scripts/fix_para_indent.py list <file.docx> --para "发明名称文本或段落前缀"

    # 清零（**默认输出新文件**，不覆盖原稿——定稿/审核稿纪律；默认只处理名称段与五个章节标题段）
    python scripts/fix_para_indent.py fix <file.docx>                       # 输出 <名>-indent-fix.docx
    python scripts/fix_para_indent.py fix <file.docx> --out 修正后.docx
    python scripts/fix_para_indent.py fix <file.docx> --in-place            # 明确要求时才就地覆盖（覆盖前自动 .bak）

改完请重跑 `verify_docx_skeleton.py` 复核（该脚本的「首行缩进0」项须 PASS）。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

_PARA_RE = re.compile(r"<w:p(?:\s[^>]*)?/>|<w:p(?:\s[^>]*)?>.*?</w:p>", re.S)
_HEADINGS = ("技术领域", "背景技术", "发明内容", "附图说明", "具体实施方式")
_ZERO_IND = '<w:ind w:left="0" w:leftChars="0" w:firstLine="0" w:firstLineChars="0"/>'


def _text(p: str) -> str:
    return "".join(re.findall(r"<w:t\b[^>]*>([^<]*)</w:t>", p)).strip()


def _ind(p: str) -> str | None:
    ppr = re.search(r"<w:pPr>.*?</w:pPr>", p, re.S)
    if not ppr:
        return None
    m = re.search(r"<w:ind\b[^>]*/>", ppr.group(0))
    return m.group(0) if m else None


def _targets(doc: str, names: list[str]) -> list[tuple[int, str, str]]:
    """返回 [(段索引, 段落文本, 当前 ind)]。names 为空时自动取 名称段 + 五个标题段。"""
    paras = _PARA_RE.findall(doc)
    out = []
    for i, p in enumerate(paras):
        t = _text(p)
        if not t:
            continue
        hit = (t in names) if names else (t in _HEADINGS or (
            i + 1 < len(paras) and _text(paras[i + 1]) == "技术领域"))
        if hit:
            out.append((i, t, _ind(p) or "(无 ind)"))
    return out


def _fix(doc: str, names: list[str]) -> tuple[str, int]:
    paras = _PARA_RE.findall(doc)
    fixed = 0
    for i, p in enumerate(paras):
        t = _text(p)
        if not t:
            continue
        hit = (t in names) if names else (t in _HEADINGS or (
            i + 1 < len(paras) and _text(paras[i + 1]) == "技术领域"))
        if not hit:
            continue
        new = re.sub(r"<w:ind\b[^>]*/>", _ZERO_IND, p, count=1) if "<w:ind" in p else None
        # 无 ind 时：插到 pPr 内（跳过 pPr 内的 rPr 之前）
        if new is None:
            if "<w:pPr>" in p:
                new = p.replace("<w:pPr>", "<w:pPr>" + _ZERO_IND, 1)
            elif p.startswith("<w:p>"):
                new = p.replace("<w:p>", "<w:p><w:pPr>" + _ZERO_IND + "</w:pPr>", 1)
            else:
                continue
        if new != p:
            doc = doc.replace(p, new, 1)
            fixed += 1
    return doc, fixed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("list", "fix"):
        s = sub.add_parser(cmd)
        s.add_argument("docx", type=Path)
        s.add_argument("--para", action="append", default=[],
                       help="指定段落文本或前缀（可多次）；缺省=发明名称段 + 五个章节标题段")
        if cmd == "fix":
            s.add_argument("--out", type=Path, default=None, help="输出路径（默认 <原文件名>-indent-fix.docx）")
            s.add_argument("--in-place", action="store_true", help="就地覆盖原文件（覆盖前备份 .bak）")
    a = ap.parse_args(argv)

    with zipfile.ZipFile(a.docx) as z:
        doc = z.read("word/document.xml").decode("utf-8")

    if a.cmd == "list":
        for i, t, ind in _targets(doc, a.para):
            print(f"[{i:03d}] {t[:24]:<26} {ind}")
        return 0

    new_doc, fixed = _fix(doc, a.para)
    if not fixed:
        print("无需要修改的段落（已是缩进 0）")
        return 0
    out = a.out or (a.docx if a.in_place else a.docx.with_name(a.docx.stem + "-indent-fix.docx"))
    if a.in_place:
        bak = a.docx.with_suffix(a.docx.suffix + ".bak")
        shutil.copy2(a.docx, bak)
        print(f"已备份原稿 → {bak}")
    tmp = out.with_suffix(".tmp.docx")
    with zipfile.ZipFile(a.docx) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            zout.writestr(it, new_doc.encode("utf-8") if it.filename == "word/document.xml"
                          else zin.read(it.filename))
    Path(tmp).replace(out)
    print(f"已清零 {fixed} 段的缩进 → {out}")
    print("请重跑 verify_docx_skeleton.py 复核「首行缩进0」项")
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())

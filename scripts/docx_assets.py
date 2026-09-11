#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docx_assets.py — 交付 DOCX 里用户手工资产（Visio 图 / 手贴图片）的提取与回注。

★ 立项根因（H2609029 全文 2 稿，2026-09-10 用户「你为什么老是把我贴的 visio 图删了」）：
**重建类操作（从模板/基准稿重新生成交付稿）会丢掉基准里没有的东西**——用户贴在
`word/media/` 里的 Visio EMF/OLE 对象、手工调整过的图片，都不在 `docs/全文稿.md`
基准里，重建即丢。本案连环重建 3 次、用户重贴 3 次。

纪律（`revision-docx.md`「返修执行纪律」）：**返修一律段级手术，不重建**；万不得已要重建时，
先用本脚本把用户资产从**旧交付稿**里抠出来，重建后回注。

用法：
    # 看一眼旧稿里有哪些手工资产（只读）
    python scripts/docx_assets.py list <旧交付稿.docx>

    # 抠出到目录（media 原样 + 清单 json + 每个 drawing 段的 XML 片段）
    python scripts/docx_assets.py extract <旧交付稿.docx> --out docs/_assets-备份/

    # 回注：把备份里的 media 与 drawing 段落插回新稿（按分节序数定位 分节2/分节5）
    python scripts/docx_assets.py restore <新交付稿.docx> --from docs/_assets-备份/
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

_PARA_RE = re.compile(r"<w:p(?:\s[^>]*)?/>|<w:p(?:\s[^>]*)?>.*?</w:p>", re.S)
_MEDIA_RE = re.compile(r"word/media/[^\"']+")
# 用户手工资产的形态：Visio/EMF 对象（<w:object>）与任何 drawing/pict/v:imagedata
_ASSET_MARK = ("<w:object", "<w:pict", "<v:imagedata", "<w:drawing")


def _sections(doc: str) -> list[list[str]]:
    out, cur = [], []
    for p in _PARA_RE.findall(doc):
        cur.append(p)
        if "<w:sectPr" in p:
            out.append(cur)
            cur = []
    out.append(cur)
    return out


def list_assets(docx: Path) -> list[dict]:
    with zipfile.ZipFile(docx) as z:
        doc = z.read("word/document.xml").decode("utf-8", errors="replace")
        media = [n for n in z.namelist() if n.startswith("word/media/") and not n.endswith("/")]
    secs = _sections(doc)
    found = []
    for si, sec in enumerate(secs, 1):
        for pi, p in enumerate(sec):
            marks = [m for m in _ASSET_MARK if m in p]
            if not marks:
                continue
            txt = "".join(re.findall(r"<w:t\b[^>]*>([^<]*)</w:t>", p)).strip()
            embeds = re.findall(r'r:(?:embed|id)="([^"]+)"', p)
            found.append({"section": si, "para_index": pi, "marks": marks,
                          "text": txt[:60], "rels": embeds})
    return [{"file": str(docx), "media": media, "assets": found}]


def extract(docx: Path, out_dir: Path) -> dict:
    info = list_assets(docx)[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    media_dir = out_dir / "media"
    media_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(docx) as z:
        for name in info["media"]:
            (media_dir / Path(name).name).write_bytes(z.read(name))
        doc = z.read("word/document.xml").decode("utf-8", errors="replace")
        rels = ""
        try:
            rels = z.read("word/_rels/document.xml.rels").decode("utf-8", errors="replace")
        except KeyError:
            pass
    secs = _sections(doc)
    para_xml = {}
    for a in info["assets"]:
        p = secs[a["section"] - 1][a["para_index"]]
        para_xml[f"s{a['section']}_p{a['para_index']}"] = p
    (out_dir / "manifest.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "paragraphs.xml.json").write_text(json.dumps(para_xml, ensure_ascii=False, indent=2), encoding="utf-8")
    if rels:
        (out_dir / "document.xml.rels").write_text(rels, encoding="utf-8")
    print(f"OK\t抠出 media {len(info['media'])} 个 · 资产段 {len(info['assets'])} 个 → {out_dir}")
    for a in info["assets"]:
        print(f"   分节{a['section']} 第{a['para_index']}段 {'/'.join(a['marks'])} rels={a['rels']}")
    return info


def restore(new_docx: Path, backup: Path) -> int:
    """把备份的 media 文件与资产段回注到新稿（就地改写新稿的 zip）。"""
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    para_xml = json.loads((backup / "paragraphs.xml.json").read_text(encoding="utf-8"))
    if not para_xml:
        print("SKIP\t备份中没有资产段，无需回注")
        return 0
    tmp = new_docx.with_suffix(".restore.docx")
    added = 0
    with zipfile.ZipFile(new_docx) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        names = set(zin.namelist())
        doc = zin.read("word/document.xml").decode("utf-8")
        secs = _sections(doc)
        for key, px in para_xml.items():
            m = re.match(r"s(\d+)_p(\d+)$", key)
            si = int(m.group(1))
            if si > len(secs):
                continue
            # 若该分节已有同类资产段（drawing/object），先删掉再插，避免重复
            doc = doc.replace(px, "", 1)
            secs = _sections(doc)
            anchor = next((p for p in secs[si - 1] if "<w:sectPr" in p), None)
            if anchor is None:
                continue
            doc = doc.replace(anchor, px + anchor, 1)
            added += 1
        for it in zin.infolist():
            if it.filename == "word/document.xml":
                zout.writestr(it, doc.encode("utf-8"))
            elif it.filename in names and it.filename.startswith("word/media/"):
                # 媒体文件以备份为准
                b = backup / "media" / Path(it.filename).name
                zout.writestr(it, b.read_bytes() if b.exists() else zin.read(it.filename))
            else:
                zout.writestr(it, zin.read(it.filename))
        # 备份里多出来的 media 一并补进包
        for f in (backup / "media").glob("*") if (backup / "media").exists() else []:
            target = f"word/media/{f.name}"
            if target not in names:
                zout.writestr(target, f.read_bytes())
    shutil.move(str(tmp), str(new_docx))
    print(f"OK\t回注资产段 {added} 个（media 已按备份覆盖）→ {new_docx}")
    print("⚠️ 回注后必须重跑 verify_docx_injection.py + verify_docx_skeleton.py 确认未破坏骨架")
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("list"); p1.add_argument("docx", type=Path)
    p2 = sub.add_parser("extract"); p2.add_argument("docx", type=Path); p2.add_argument("--out", type=Path, required=True)
    p3 = sub.add_parser("restore"); p3.add_argument("docx", type=Path); p3.add_argument("--from", dest="src", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        info = list_assets(a.docx)[0]
        print(f"media: {info['media']}")
        for it in info["assets"]:
            print(f"  分节{it['section']} 第{it['para_index']}段 {'/'.join(it['marks'])} text={it['text']!r} rels={it['rels']}")
        return 0
    if a.cmd == "extract":
        extract(a.docx, a.out)
        return 0
    restore(a.docx, a.src)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())

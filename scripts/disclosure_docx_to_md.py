#!/usr/bin/env python3
"""Convert a disclosure DOCX to Markdown while preserving highlights and comments.

Highlighted runs are wrapped as ==text==. Word comments anchored to a
paragraph are emitted immediately after that paragraph as blockquotes.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def load_comments(docx_path: Path) -> dict[str, dict[str, str]]:
    try:
        with zipfile.ZipFile(str(docx_path)) as archive:
            if "word/comments.xml" not in archive.namelist():
                return {}
            xml = archive.read("word/comments.xml")
    except (KeyError, zipfile.BadZipFile):
        return {}

    comments: dict[str, dict[str, str]] = {}
    root = ET.fromstring(xml)
    for comment in root.findall(".//w:comment", NS):
        comment_id = comment.get(f"{{{W_NS}}}id")
        if comment_id is None:
            continue
        author = comment.get(f"{{{W_NS}}}author") or ""
        text = "".join(node.text or "" for node in comment.findall(".//w:t", NS)).strip()
        comments[comment_id] = {"author": author, "text": text}
    return comments


def paragraph_comment_ids(paragraph) -> list[str]:
    ids: list[str] = []
    for elem in paragraph._element.iter():
        if elem.tag in (qn("w:commentRangeStart"), qn("w:commentReference")):
            comment_id = elem.get(qn("w:id"))
            if comment_id is not None and comment_id not in ids:
                ids.append(comment_id)
    return ids


def paragraph_text_with_highlights(paragraph) -> str:
    parts: list[str] = []
    for run in paragraph.runs:
        if not run.text:
            continue
        if run.font.highlight_color is not None:
            parts.append(f"=={run.text}==")
        else:
            parts.append(run.text)
    return "".join(parts)


def markdown_line_for_paragraph(paragraph, text: str) -> str:
    style_name = paragraph.style.name if paragraph.style is not None else ""
    if style_name == "Heading 1":
        return f"# {text}" if text.strip() else ""
    if style_name.startswith("Heading"):
        digits = "".join(ch for ch in style_name if ch.isdigit())
        level = int(digits or "2")
        return f"{'#' * level} {text}" if text.strip() else ""
    return text


def open_tolerant(docx_path: Path):
    """打开交底书 DOCX；带损坏部件（如无扩展名的 docProps/thumbnail.）时先剥离再打开。

    H2609029 实测：交底书内有空内容、无扩展名的 `docProps/thumbnail.` 部件，python-docx
    直接 KeyError 崩溃（"no content type for partname '/docProps/thumbnail.'"）。
    容错策略——把读不出/命名异常的部件连其在 [Content_Types].xml 与 _rels/.rels 里的登记
    一并剥离，改副本重试；原文件不动，全程只读。
    """
    try:
        return Document(str(docx_path)), []
    except Exception as exc:  # noqa: BLE001 —— 部件损坏形态多样, 统一走剥离重试
        import tempfile
        import zipfile

        with zipfile.ZipFile(docx_path) as zin:
            items = [(i.filename, zin.read(i.filename)) for i in zin.infolist()]
        dropped: list[str] = []
        kept: list[tuple[str, bytes]] = []
        for name, data in items:
            tail = name.rsplit("/", 1)[-1]
            bad = (not tail) or ("." not in tail) or tail.endswith(".") or not data
            bad = bad and name.startswith("docProps")
            if bad:
                dropped.append(name)
                continue
            kept.append((name, data))

        def _strip(member: str, pattern: str) -> None:
            for idx, (name, data) in enumerate(kept):
                if name != member:
                    continue
                body = data.decode("utf-8", errors="replace")
                for d in dropped:
                    body = re.sub(pattern.format(target=re.escape(d)), "", body)
                kept[idx] = (name, body.encode("utf-8"))

        _strip("[Content_Types].xml", r'<Override[^>]*PartName="/{target}"[^>]*/>')
        _strip("_rels/.rels", r'<Relationship[^>]*Target="{target}"[^>]*/>')

        tmp = Path(tempfile.mkdtemp(prefix="disclosure_")) / docx_path.name
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, data in kept:
                zout.writestr(name, data)
        if dropped:
            print(f"WARN	交底书含损坏/异常部件 {len(dropped)} 个，已剥离后重试：{dropped[:5]}",
                  file=sys.stderr)
        try:
            return Document(str(tmp)), dropped
        except Exception as exc2:  # noqa: BLE001
            raise SystemExit(f"ERROR	交底书 DOCX 无法解析（剥离 {len(dropped)} 个部件后仍失败）："
                             f"{exc2}；原始错误：{exc}") from exc2


def convert(docx_path: Path, md_path: Path) -> dict[str, int]:
    doc, _dropped = open_tolerant(docx_path)
    comments = load_comments(docx_path)
    seen_comments: set[str] = set()
    highlights_count = 0
    output: list[str] = []

    for paragraph in doc.paragraphs:
        text = paragraph_text_with_highlights(paragraph)
        highlights_count += text.count("==") // 2
        output.append(markdown_line_for_paragraph(paragraph, text))

        for comment_id in paragraph_comment_ids(paragraph):
            if comment_id in seen_comments:
                continue
            seen_comments.add(comment_id)
            comment = comments.get(comment_id)
            if not comment:
                continue
            output.append(f"> 💡 [批注 #{comment_id} by {comment['author']}]: {comment['text']}")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(output), encoding="utf-8")
    return {
        "paragraphs": len(doc.paragraphs),
        "comments_total": len(comments),
        "comments_anchored": len(seen_comments),
        "highlights_marked": highlights_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert disclosure DOCX to annotated Markdown")
    parser.add_argument("--input", required=True, type=Path, help="source disclosure DOCX")
    parser.add_argument("--output", required=True, type=Path, help="output Markdown path")
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2

    stats = convert(args.input, args.output)
    print(
        f"wrote {args.output} "
        f"(paragraphs={stats['paragraphs']}, "
        f"comments={stats['comments_anchored']}/{stats['comments_total']}, "
        f"highlights={stats['highlights_marked']})"
    )
    return 0


if __name__ == "__main__":
    # Windows GBK 控制台: 输出含 GBK 外字符时裸跑 UnicodeEncodeError (H2609029 实测, 2026-09-10)。强制 UTF-8。
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())

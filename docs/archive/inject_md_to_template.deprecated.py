#!/usr/bin/env python3
"""Inject checked patent Markdown into a DOCX template copy.

The script preserves the template package structure and styles, clears body
paragraph/table content, then rebuilds document body from Markdown.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

NUMBERED_CLAIM_RE = re.compile(r"^\d+[.．]")


def parse_md(md_path: Path) -> list[dict[str, str | None]]:
    paragraphs: list[dict[str, str | None]] = []
    current_h1: str | None = None
    current_h2: str | None = None

    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            current_h1 = line[2:].strip()
            current_h2 = None
            paragraphs.append({"level": "h1", "h1": current_h1, "h2": None, "text": current_h1})
        elif line.startswith("## "):
            current_h2 = line[3:].strip()
            paragraphs.append({"level": "h2", "h1": current_h1, "h2": current_h2, "text": current_h2})
        else:
            paragraphs.append({"level": "p", "h1": current_h1, "h2": current_h2, "text": line})
    return paragraphs


def clear_body_content(doc: Document) -> int:
    body = doc.element.body
    removed = 0
    for child in list(body):
        if child.tag in (qn("w:p"), qn("w:tbl")):
            body.remove(child)
            removed += 1
    return removed


def decide_style(item: dict[str, str | None]) -> str:
    if item["level"] == "h1":
        return "Heading 1"
    if item["level"] == "h2":
        return "Normal"
    if item["h1"] == "权利要求书" and item["text"] and not NUMBERED_CLAIM_RE.match(item["text"]):
        return "List Paragraph"
    return "Normal"


def inject(template_path: Path, md_path: Path, output_path: Path) -> dict[str, object]:
    if not template_path.is_file():
        raise FileNotFoundError(f"template not found: {template_path}")
    if not md_path.is_file():
        raise FileNotFoundError(f"markdown not found: {md_path}")

    items = parse_md(md_path)
    if not items:
        raise ValueError("markdown parsed to no paragraphs")

    doc = Document(str(template_path))
    removed = clear_body_content(doc)
    available_styles = {style.name for style in doc.styles}

    style_counts: dict[str, int] = {}
    h1_count = 0
    for item in items:
        style_name = decide_style(item)
        if style_name not in available_styles:
            style_name = "Normal"
        doc.add_paragraph(str(item["text"]), style=style_name)
        style_counts[style_name] = style_counts.get(style_name, 0) + 1
        if item["level"] == "h1":
            h1_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return {
        "removed": removed,
        "paragraphs": len(items),
        "h1_count": h1_count,
        "style_counts": style_counts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inject checked patent Markdown into a DOCX template")
    parser.add_argument("--template", required=True, type=Path, help="template DOCX path")
    parser.add_argument("--md", required=True, type=Path, help="checked case_draft.md path")
    parser.add_argument("--output", required=True, type=Path, help="output DOCX path")
    args = parser.parse_args(argv)

    try:
        stats = inject(args.template, args.md, args.output)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"wrote {args.output}")
    print(f"  cleared template paragraphs/tables: {stats['removed']}")
    print(f"  injected paragraphs: {stats['paragraphs']} (h1 titles: {stats['h1_count']})")
    print(f"  style breakdown: {stats['style_counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

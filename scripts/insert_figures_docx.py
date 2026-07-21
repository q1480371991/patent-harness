#!/usr/bin/env python3
"""把图 1 PNG 注入专利模板 DOCX 的摘要附图（分节2）与说明书附图（分节5）。

在 docx skill 的 unpack 目录上操作（unpack → 本脚本 → pack），职责：
- 注册 media 文件、image relationship、png Content-Type；
- 分节2（摘要附图）：段内已有 drawing 则替换其图片与显示尺寸，否则居中插入图片；
- 分节5（说明书附图）：已有 drawing 则替换第一张（图 1）并确保其后有"图1"图题段，
  无 drawing 则在节末插入"图片段 + 图1 图题段"；分节5 的其他既有图（如图 2）不触碰；
- 显示尺寸按 PNG 宽高比与目标宽度计算，超出最大高度时等比缩小。

模板结构硬约束：必须恰好 5 个 sectPr（G8-0），否则报错退出、不做任何修改。

用法：
    python3 scripts/insert_figures_docx.py <unpack目录> --png docs/figures/figure-1.png \
        [--abstract-width-cm 16.0] [--spec-width-cm 12.3] [--max-height-cm 22.0]
"""

import argparse
import re
import shutil
from pathlib import Path

EMU_PER_CM = 360000

IMAGE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
)

RUN_FONT = (
    '<w:rPr><w:rFonts w:hint="eastAsia" w:ascii="宋体" w:hAnsi="宋体" '
    'w:eastAsia="宋体" w:cs="宋体"/><w:szCs w:val="28"/></w:rPr>'
)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise SystemExit(f"ERROR\t{path} 不是有效 PNG")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def display_emu(png: Path, width_cm: float, max_height_cm: float) -> tuple[int, int]:
    px_w, px_h = png_size(png)
    cx = round(width_cm * EMU_PER_CM)
    cy = round(cx * px_h / px_w)
    max_cy = round(max_height_cm * EMU_PER_CM)
    if cy > max_cy:
        cy = max_cy
        cx = round(cy * px_w / px_h)
    return cx, cy


def drawing_xml(rid: str, doc_pr_id: int, cx: int, cy: int, name: str) -> str:
    return (
        f'<w:r>{RUN_FONT}<w:drawing>'
        f'<wp:inline distT="0" distB="0" distL="114300" distR="114300">'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{doc_pr_id}" name="{name}" descr="{name}"/>'
        f'<wp:cNvGraphicFramePr>'
        f'<a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>'
        f'</wp:cNvGraphicFramePr>'
        f'<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f'<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{doc_pr_id}" name="{name}" descr="{name}"/>'
        f'<pic:cNvPicPr><a:picLocks noChangeAspect="1"/></pic:cNvPicPr></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
    )


def image_paragraph(rid: str, doc_pr_id: int, cx: int, cy: int, name: str) -> str:
    return (
        '<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/>'
        '<w:ind w:firstLine="0" w:firstLineChars="0"/><w:jc w:val="center"/>'
        f'{RUN_FONT}</w:pPr>{drawing_xml(rid, doc_pr_id, cx, cy, name)}</w:p>'
    )


def caption_paragraph(text: str) -> str:
    return (
        '<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/>'
        '<w:ind w:firstLine="0" w:firstLineChars="0"/><w:jc w:val="center"/>'
        f'{RUN_FONT}</w:pPr><w:r>{RUN_FONT}<w:t>{text}</w:t></w:r></w:p>'
    )


def find_paragraph_span(doc: str, inner_pos: int) -> tuple[int, int]:
    """返回包含 inner_pos 的 <w:p ...>...</w:p> 的 [start, end) 区间。"""
    start = max(doc.rfind("<w:p>", 0, inner_pos), doc.rfind("<w:p ", 0, inner_pos))
    end = doc.find("</w:p>", inner_pos)
    if start == -1 or end == -1:
        raise SystemExit("ERROR\t定位段落失败：XML 结构与模板家族不符")
    return start, end + len("</w:p>")


def register_media(unpacked: Path, png: Path) -> tuple[str, str]:
    """拷贝 PNG 进 media 并注册 relationship 与 Content-Type，返回 (rId, media名)。"""
    media_dir = unpacked / "word" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.name for p in media_dir.iterdir()}
    index = 1
    while f"image{index}.png" in existing:
        index += 1
    media_name = f"image{index}.png"
    shutil.copy2(png, media_dir / media_name)

    rels_path = unpacked / "word" / "_rels" / "document.xml.rels"
    rels = rels_path.read_text(encoding="utf-8")
    rid_numbers = [int(m) for m in re.findall(r'Id="rId(\d+)"', rels)]
    rid = f"rId{max(rid_numbers, default=0) + 1}"
    rels = rels.replace(
        "</Relationships>",
        f'<Relationship Id="{rid}" Type="{IMAGE_REL_TYPE}" '
        f'Target="media/{media_name}"/></Relationships>',
    )
    rels_path.write_text(rels, encoding="utf-8")

    ct_path = unpacked / "[Content_Types].xml"
    ct = ct_path.read_text(encoding="utf-8")
    if 'Extension="png"' not in ct:
        ct = ct.replace(
            "</Types>",
            '<Default Extension="png" ContentType="image/png"/></Types>',
        )
        ct_path.write_text(ct, encoding="utf-8")
    return rid, media_name


def resolve_media_target(unpacked: Path, rid: str) -> Path:
    rels = (unpacked / "word" / "_rels" / "document.xml.rels").read_text(encoding="utf-8")
    match = re.search(rf'Id="{rid}"[^>]*Target="([^"]+)"', rels)
    if not match:
        raise SystemExit(f"ERROR\t关系 {rid} 不存在于 document.xml.rels")
    return unpacked / "word" / Path(match.group(1))


def next_doc_pr_id(doc: str) -> int:
    ids = [int(m) for m in re.findall(r'<wp:docPr id="(\d+)"', doc)]
    ids += [int(m) for m in re.findall(r'<pic:cNvPr id="(\d+)"', doc)]
    return max(ids, default=0) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unpacked", type=Path, help="docx skill 的 unpack 目录")
    parser.add_argument("--png", type=Path, required=True, help="图 1 PNG 路径")
    parser.add_argument("--abstract-width-cm", type=float, default=16.0)
    parser.add_argument("--spec-width-cm", type=float, default=12.3)
    parser.add_argument("--max-height-cm", type=float, default=22.0)
    args = parser.parse_args()

    if not args.png.exists():
        raise SystemExit(f"ERROR\t图片不存在：{args.png}")
    doc_path = args.unpacked / "word" / "document.xml"
    doc = doc_path.read_text(encoding="utf-8")

    sect_positions = [m.start() for m in re.finditer(r"<w:sectPr>", doc)]
    if len(sect_positions) != 5:
        raise SystemExit(
            f"ERROR\tsectPr 数量为 {len(sect_positions)}（模板家族应为 5），停止注入"
        )

    actions = []
    abstract_cx, abstract_cy = display_emu(args.png, args.abstract_width_cm,
                                           args.max_height_cm)
    spec_cx, spec_cy = display_emu(args.png, args.spec_width_cm, args.max_height_cm)

    # ---- 分节5（先处理文末，避免位置偏移影响分节2） ----
    sect4_p_start, sect4_p_end = find_paragraph_span(doc, sect_positions[3])
    final_sect_start = doc.rfind("<w:sectPr>")
    line_start = doc.rfind("\n", 0, final_sect_start) + 1
    section5 = doc[sect4_p_end:line_start]

    drawing_iter = [m for m in re.finditer(r"<w:drawing>", section5)]
    if drawing_iter:
        span = find_paragraph_span(section5, drawing_iter[0].start())
        rel_start, rel_end = span[0] + sect4_p_end, span[1] + sect4_p_end
        block = doc[rel_start:rel_end]
        embed = re.search(r'r:embed="(rId\d+)"', block)
        if not embed:
            raise SystemExit("ERROR\t分节5 drawing 内找不到 r:embed")
        target = resolve_media_target(args.unpacked, embed.group(1))
        shutil.copy2(args.png, target)
        block = re.sub(r'<wp:extent cx="\d+" cy="\d+"/>',
                       f'<wp:extent cx="{spec_cx}" cy="{spec_cy}"/>', block, count=1)
        block = re.sub(r'<a:ext cx="\d+" cy="\d+"/>',
                       f'<a:ext cx="{spec_cx}" cy="{spec_cy}"/>', block, count=1)
        insertion = ""
        after = doc[rel_end:line_start]
        if not re.search(r"<w:t[^>]*>\s*图1\s*。?\s*</w:t>", after[:4000]):
            insertion = caption_paragraph("图1")
            actions.append("分节5：补插图题段「图1」")
        doc = doc[:rel_start] + block + insertion + doc[rel_end:]
        actions.append(
            f"分节5：替换既有图1（{target.name}），尺寸 {spec_cx}x{spec_cy} EMU"
        )
    else:
        rid, media_name = register_media(args.unpacked, args.png)
        doc_pr = next_doc_pr_id(doc)
        new_content = (
            image_paragraph(rid, doc_pr, spec_cx, spec_cy, "图1")
            + caption_paragraph("图1")
        )
        doc = doc[:line_start] + new_content + doc[line_start:]
        actions.append(
            f"分节5：插入图1（{media_name}, {rid}）+ 图题段，尺寸 {spec_cx}x{spec_cy} EMU"
        )

    # ---- 分节2（摘要附图） ----
    sect_positions = [m.start() for m in re.finditer(r"<w:sectPr>", doc)]
    p2_start, p2_end = find_paragraph_span(doc, sect_positions[1])
    paragraph = doc[p2_start:p2_end]
    if "<w:drawing>" in paragraph:
        embed = re.search(r'r:embed="(rId\d+)"', paragraph)
        if not embed:
            raise SystemExit("ERROR\t分节2 drawing 内找不到 r:embed")
        target = resolve_media_target(args.unpacked, embed.group(1))
        shutil.copy2(args.png, target)
        paragraph = re.sub(r'<wp:extent cx="\d+" cy="\d+"/>',
                           f'<wp:extent cx="{abstract_cx}" cy="{abstract_cy}"/>',
                           paragraph, count=1)
        paragraph = re.sub(r'<a:ext cx="\d+" cy="\d+"/>',
                           f'<a:ext cx="{abstract_cx}" cy="{abstract_cy}"/>',
                           paragraph, count=1)
        actions.append(
            f"分节2：替换既有摘要附图（{target.name}），尺寸 {abstract_cx}x{abstract_cy} EMU"
        )
    else:
        rid, media_name = register_media(args.unpacked, args.png)
        # 清掉占位文本 run（如"图1。"），保留 pPr
        cleaned, removed = re.subn(
            r"<w:r(?:\s[^>]*)?>(?:(?!</w:r>).)*?<w:t(?:(?!</w:r>).)*?</w:r>",
            "", paragraph, flags=re.S)
        if removed:
            actions.append(f"分节2：清除 {removed} 个占位文本 run")
        paragraph = cleaned
        # 确保居中
        p_pr_end = paragraph.find("</w:pPr>")
        if p_pr_end != -1 and "<w:jc" not in paragraph[:p_pr_end]:
            anchor = paragraph.find("<w:rPr>")
            if anchor == -1 or anchor > p_pr_end:
                anchor = paragraph.find("<w:sectPr>")
            if anchor == -1 or anchor > p_pr_end:
                anchor = p_pr_end
            paragraph = (paragraph[:anchor] + '<w:jc w:val="center"/>'
                         + paragraph[anchor:])
            actions.append("分节2：补 <w:jc center>")
        doc_pr = next_doc_pr_id(doc)
        run = drawing_xml(rid, doc_pr, abstract_cx, abstract_cy, "图1")
        paragraph = paragraph.replace("</w:p>", run + "</w:p>")
        actions.append(
            f"分节2：插入摘要附图（{media_name}, {rid}），尺寸 {abstract_cx}x{abstract_cy} EMU"
        )
    doc = doc[:p2_start] + paragraph + doc[p2_end:]

    doc_path.write_text(doc, encoding="utf-8")
    for action in actions:
        print(f"OK\t{action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

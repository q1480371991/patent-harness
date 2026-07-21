#!/usr/bin/env python3
"""生成专利图 1（摘要附图 = 方法主流程图）PNG。

唯一信源是权要稿：节点 = 权利要求 1 的分号分句**逐字**（去句末标点），
编号 S11..S1N 以水平引出线标注在方框右侧外部，纵向单线单向箭头。
逐字一致由构造保证（直接从权要稿提取，不接受手工节点输入）。

版式（经审核确认，勿随意改动）：等宽黑白矩形 520px、每行 26 字、
框间距 50px、画布边距 30px、宋体、300 DPI。

用法：
    python3 scripts/render_patent_figure.py --claims-md docs/权要稿.md \
        --output docs/figures/figure-1.png [--claim-number 1]

输出仅 PNG（任务宗旨：能成功插入 Word）。依赖 Pillow。
"""

import argparse
import re
import textwrap
from pathlib import Path

# ---- 版式常量 ----
BOX_WIDTH = 520      # 矩形等宽
GAP = 50             # 相邻矩形垂直间距（箭头长度）
MARGIN = 30          # 画布边距
LEADER = 28          # 右侧编号引出线长度
LABEL_GAP = 10       # 引出线与编号文字间距
LABEL_ZONE = 105     # 右侧编号区总宽度
WRAP = 26            # 框内文字每行字数
LINE_H = 24          # 行高
FONT_BODY = 18
SCALE = 2            # 2 倍采样，300 DPI

VAGUE_FINAL = re.compile(r"(技术结果|处理结果|最终结果)")


def strip_tail_punct(text: str) -> str:
    return re.sub(r"[；;。．.，,]+$", "", str(text).strip())


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", strip_tail_punct(text))


def extract_claim_clauses(claims_md: Path, claim_number: int) -> list[str]:
    """从权要稿.md 提取第 claim_number 条权要"其特征在于…："后的分号分句。"""
    text = claims_md.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^{claim_number}[\.．、](.*?)(?=^\d+[\.．、]|\Z)", re.M | re.S
    )
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"ERROR\t权要稿中找不到权利要求 {claim_number}")
    body = match.group(1)
    marker = re.search(r"其特征在于[^：:]*[：:]", body)
    tail = body[marker.end():] if marker else body
    clauses = [normalize(c) for c in tail.split("；")]
    clauses = [c for c in clauses if c]
    if len(clauses) < 2:
        raise SystemExit(
            f"ERROR\t权利要求 {claim_number} 仅提取到 {len(clauses)} 个分句，"
            "无法构成流程图；确认其为方法独立权要（无方法独权的案件由用户自备图片）"
        )
    return clauses


def wrap_label(label: str) -> list[str]:
    return textwrap.wrap(label, width=WRAP) or [""]


def layout(clauses: list[str]):
    """返回每个节点的 (x, y, w, h) 与画布尺寸。"""
    boxes = []
    y = MARGIN
    for clause in clauses:
        height = max(72, 34 + len(wrap_label(clause)) * LINE_H)
        boxes.append((MARGIN, y, BOX_WIDTH, height))
        y += height + GAP
    return boxes, MARGIN + BOX_WIDTH + LABEL_ZONE, y - GAP + MARGIN


def load_font(size: int):
    from PIL import ImageFont

    candidates = (
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def render_png(clauses: list[str], output: Path) -> None:
    from PIL import Image, ImageDraw

    boxes, width, height = layout(clauses)
    image = Image.new("RGB", (width * SCALE, height * SCALE), "white")
    draw = ImageDraw.Draw(image)
    font = load_font(FONT_BODY * SCALE)

    def pt(value: float) -> int:
        return int(round(value * SCALE))

    # 箭头：上一框底边中点 → 下一框顶边中点
    for (x1, y1, w1, h1), (x2, y2, _, _) in zip(boxes, boxes[1:]):
        sx, sy, tx, ty = x1 + w1 / 2, y1 + h1, x2 + BOX_WIDTH / 2, y2
        draw.line((pt(sx), pt(sy), pt(tx), pt(ty)), fill="black", width=2 * SCALE)
        draw.polygon(
            [(pt(tx), pt(ty)),
             (pt(tx - 7), pt(ty - 12)),
             (pt(tx + 7), pt(ty - 12))],
            fill="black",
        )

    for index, ((x, y, w, h), clause) in enumerate(zip(boxes, clauses), 1):
        draw.rectangle((pt(x), pt(y), pt(x + w), pt(y + h)), fill="white",
                       outline="black", width=2 * SCALE)
        lines = wrap_label(clause)
        line_h = LINE_H * SCALE
        text_y = pt(y + h / 2) - line_h * len(lines) / 2
        for line in lines:
            box = draw.textbbox((0, 0), line, font=font)
            draw.text((pt(x + w / 2) - (box[2] - box[0]) / 2, text_y),
                      line, fill="black", font=font)
            text_y += line_h
        # 右侧引出线 + 编号 S1<index>
        mid_y = y + h / 2
        draw.line((pt(x + w), pt(mid_y), pt(x + w + LEADER), pt(mid_y)),
                  fill="black", width=2 * SCALE)
        label = f"S1{index}"
        box = draw.textbbox((0, 0), label, font=font)
        draw.text(
            (pt(x + w + LEADER + LABEL_GAP),
             pt(mid_y) - (box[3] - box[1]) / 2 - box[1]),
            label, fill="black", font=font,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", dpi=(300, 300))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims-md", type=Path, required=True, help="权要稿.md 路径")
    parser.add_argument("--output", type=Path, required=True, help="输出 PNG 路径")
    parser.add_argument("--claim-number", type=int, default=1,
                        help="方法独立权要编号（默认 1）")
    args = parser.parse_args()

    clauses = extract_claim_clauses(args.claims_md, args.claim_number)
    if VAGUE_FINAL.search(clauses[-1]):
        print("WARN\t末分句含模糊结果词（技术结果/处理结果/最终结果）；"
              "图 1 终点节点建议为具体领域结果（权要已冻结，仅提示不阻断）")
    render_png(clauses, args.output)
    print(f"{args.output}")
    print(f"OK\t图1：{len(clauses)} 个节点（S11–S1{len(clauses)}），"
          f"节点文字=权要{args.claim_number}分句逐字")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

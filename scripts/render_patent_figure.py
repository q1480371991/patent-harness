#!/usr/bin/env python3
"""生成专利图 1（摘要附图 = 方法主流程图）PNG。

唯一信源是权要稿：节点 = 权利要求 1 的分号分句**逐字**（去句末标点），
编号 S11..S1N 以 45° 斜向上引出线标注在方框右上角外侧，纵向单线单向箭头。
逐字一致由构造保证（直接从权要稿提取，不接受手工节点输入）。

版式（经审核确认，勿随意改动）：等宽黑白矩形 520px、每行 26 字、
框间距 50px、画布边距 30px、宋体常规字重（不加粗）、300 DPI；
框内折行遵循行首禁则（行首不出现标点，标点上提至上一行行尾）。

用法：
    python scripts/render_patent_figure.py --claims-md docs/权要稿.md \
        --output docs/figures/figure-1.png [--claim-number 1]

输出仅 PNG（任务宗旨：能成功插入 Word）。依赖 Pillow。
"""

import argparse
import re
from pathlib import Path

# ---- 版式常量 ----
BOX_WIDTH = 520      # 矩形等宽
GAP = 50             # 相邻矩形垂直间距（箭头长度）
MARGIN = 30          # 画布边距
TOP_ALLOWANCE = 0    # 斜线从框右边中点起、不超出首框顶边，无需顶部预留
LEADER = 28          # 编号引出线水平/垂直位移（45° 斜向上）
LABEL_GAP = 10       # 引出线末端与编号文字间距
LABEL_ZONE = 105     # 右侧编号区总宽度
WRAP = 26            # 框内文字每行字数
LINE_H = 24          # 行高
FONT_BODY = 18
SCALE = 2            # 2 倍采样，300 DPI

VAGUE_FINAL = re.compile(r"(技术结果|处理结果|最终结果)")

# 行首禁则字符：折行后不得作为行首，出现时上提至上一行行尾
LINE_START_FORBIDDEN = set("，。、；：？！）】》〉」』％%,.;:!?)")


def strip_tail_punct(text: str) -> str:
    return re.sub(r"[；;。．.，,]+$", "", str(text).strip())


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", strip_tail_punct(text))


def merge_supplemental(clauses: list[str]) -> list[str]:
    """把"其中，…"列举补充句并入前一个动作分句（与 extract_structure 同口径）。

    权 1 中"……；其中，所述物理层参数包括……；"式补充句是前一步骤的补充说明，
    不占节点位；并入时去掉"其中，"前缀、逗号连接前句，使图 1 节点数 = 动作分句数。
    """
    merged: list[str] = []
    for c in clauses:
        if c.startswith("其中") and merged:
            supp = c[len("其中"):].lstrip("，, ")
            merged[-1] = f"{merged[-1]}，{supp}"
        else:
            merged.append(c)
    return merged


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
    clauses = merge_supplemental(clauses)
    if len(clauses) < 2:
        raise SystemExit(
            f"ERROR\t权利要求 {claim_number} 仅提取到 {len(clauses)} 个分句，"
            "无法构成流程图；确认其为方法独立权要（无方法独权的案件由用户自备图片）"
        )
    return clauses


# 折行优先断点：这些标点之后是自然断点
BREAK_AFTER = set("，、；：,;")
# 超宽片段（整段无标点）的次级断点：连接词之后。见 wrap_label 的 ②
CONNECTORS = set("与及和并")
# 次级断点（双字，断在**其后**）：常见动作词尾。中文无词边界，这是排版启发式——
# 漏收只会让某一行断点不够漂亮，**不影响正确性**（节点文字始终是分句逐字）。
BREAK_AFTER_WORDS = ("得到", "进行", "提取", "根据", "更新", "判定", "构建", "确定",
                     "生成", "计算", "识别", "重构", "分离", "累加", "折减", "插值")


def wrap_label(label: str) -> list[str]:
    """按每行 WRAP 字折行，**优先断在标点之后**。

    ★ 为什么不能硬数 WRAP 字就切（2026-09-21，H2609100 用户当场指出「你怎么乱换行」）：
      `label[index:index + WRAP]` 这种定长切法会把术语从中间劈开——该案实测切出
      「通过有／限元分析」（把整个案子的关键词「有限元分析」一分为二）、
      「材料属／性数据」「三维温／度梯度分布矩阵」「蠕变损／伤演化计算」「弹／塑变形张量」。
      中文没有词间空格，**唯一的天然断点就是标点**，所以折行必须先按句读切段、再贪心装行；
      单个片段本身超过 WRAP（罕见）时才退化为定长硬切。
    行首禁则（`LINE_START_FORBIDDEN`）作为兜底保留：片段起点本就是标点后一位，
    正常不触发；触发时把该字上提至上一行行尾。
    """
    lines: list[str] = []
    for paragraph in str(label).splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue
        # ① 按标点切成片段（标点留在片段末尾）
        segs, buf = [], ""
        for ch in paragraph:
            buf += ch
            if ch in BREAK_AFTER:
                segs.append(buf)
                buf = ""
        if buf:
            segs.append(buf)
        # ② 贪心装行
        cur = ""
        for seg in segs:
            while len(seg) > WRAP:          # 单片段超宽：退化为硬折，但先找连接词
                if cur:
                    lines.append(cur)
                    cur = ""
                # 在 [len-WRAP, WRAP] 内取**最右**的次级断点，保证折后两段都 ≤WRAP；
                # 找不到才定长硬切（如「…分布矩阵提／取目标应力集中区域」把动词劈开）。
                cut = 0
                for k in range(max(1, len(seg) - WRAP), WRAP + 1):
                    if seg[k - 1] in CONNECTORS or seg[max(0, k - 2):k] in BREAK_AFTER_WORDS:
                        cut = k
                lines.append(seg[:cut or WRAP])
                seg = seg[cut or WRAP:]
            if len(cur) + len(seg) <= WRAP:
                cur += seg
            else:
                if cur:
                    lines.append(cur)
                cur = seg
        if cur:
            lines.append(cur)
        # ③ 行首禁则兜底
        fixed: list[str] = []
        for ln in lines:
            while ln and ln[0] in LINE_START_FORBIDDEN and fixed:
                fixed[-1] += ln[0]
                ln = ln[1:]
            fixed.append(ln)
        lines = fixed
    return lines or [""]


def layout(clauses: list[str]):
    """返回每个节点的 (x, y, w, h) 与画布尺寸。"""
    boxes = []
    y = MARGIN + TOP_ALLOWANCE
    for clause in clauses:
        height = max(72, 34 + len(wrap_label(clause)) * LINE_H)
        boxes.append((MARGIN, y, BOX_WIDTH, height))
        y += height + GAP
    return boxes, MARGIN + BOX_WIDTH + LABEL_ZONE, y - GAP + MARGIN


def load_font(size: int):
    """加载中文宋体**常规字重**。

    TTC 字体集合内含多个字面（如 macOS Songti.ttc 的 index 0 是 Black 特粗体），
    直接取默认 index 会渲染成粗体；这里逐字面探测，优先选 style=Regular
    （简体家族优先），确保不加粗。
    """
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
        if not candidate.exists():
            continue
        if candidate.suffix.lower() != ".ttc":
            return ImageFont.truetype(str(candidate), size=size)
        best = None  # (score, font)：分数越小越优
        for face_index in range(16):
            try:
                font = ImageFont.truetype(str(candidate), size=size, index=face_index)
            except OSError:
                break
            family, style = font.getname()
            if style.lower() == "regular":
                score = 0 if ("sc" in family.lower() or "simsun" in family.lower()) else 1
            else:
                score = 2
            if best is None or score < best[0]:
                best = (score, font)
            if best[0] == 0:
                break
        if best is not None:
            return best[1]
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
        # 右侧编号 S1<index>：45° 斜向上引出线，起点为矩形右边中点
        start_x, start_y = x + w, y + h / 2
        end_x, end_y = x + w + LEADER, y + h / 2 - LEADER
        draw.line((pt(start_x), pt(start_y), pt(end_x), pt(end_y)),
                  fill="black", width=2 * SCALE)
        label = f"S1{index}"
        box = draw.textbbox((0, 0), label, font=font)
        draw.text(
            (pt(end_x + LABEL_GAP),
             pt(end_y) - (box[3] - box[1]) / 2 - box[1]),
            label, fill="black", font=font,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", dpi=(300, 300))


def render_label_md(clauses: list[str]) -> str:
    """生成「图1内容-供 Visio 手画」md。

    ★ 节点文字**不预折行**（2026-09-21 用户两次追问后定）：
      用户是整段复制进 Visio，Visio 按自己的框宽折行。md 里预先插硬换行，粘过去就连断行
      一起带进 Visio，等于替用户定了排版——用户原话「你乱换行干什么」。
      与 PNG 的关系：**同一 clauses**（节点文字逐字一致），但**不共用折行**——
      PNG 的框内折行由 `wrap_label` 负责，是成品图自己的事。
    """
    n = len(clauses)
    out: list[str] = [
        "# 图1 内容（供 Visio 手画用）",
        "",
        "> 本文件由 `render_patent_figure.py --label-md` 生成，与成品 PNG **同一数据源**（节点文字逐字一致）。",
        "> 节点文字＝权利要求 1 分句**逐字**（去句末标点），画图时请逐字照抄，不要改写、不要增减字。",
        f"> 节点数固定为 {n} 个（S11–S1{n}）。",
        "> **权 1 分句一旦改动，必须重跑本脚本同时重出 PNG 与本文件。**",
        "",
        "## 版式（脚本 PNG 已按此版式定稿，用户审核过，勿调）",
        "",
        f"- 纵向单列、自上而下：S11 在最上，S1{n} 在最下",
        f"- 每个节点为一个矩形框；编号 `S11`…`S1{n}` **以水平引出线标注在矩形右侧外部**，不写在矩形内",
        "- 矩形之间为**单线单向箭头**，方向自上而下",
        "- 黑白、宋体、300 DPI",
        "",
        f"## 节点文字（每框**一段连续文本，不预折行**）",
        "",
        "> 直接整段复制进 Visio，**由 Visio 按你的框宽自行折行**。",
        "> 本文档刻意不在文字里插硬换行——预折行会把断行带进 Visio，等于替你定了排版。",
        f"> 下节『版式』里的「每行 {WRAP} 字」只是脚本 PNG 的框内排法，供参考，**不必照抄**。",
        "",
    ]
    for i, clause in enumerate(clauses):
        text = strip_tail_punct(clause)
        han = sum(1 for c in text if "一" <= c <= "鿿")
        out.append(f"### S1{1 + i}（{han} 汉字）")
        out.append("")
        out.append("```")
        out.append(text)
        out.append("```")
        out.append("")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims-md", type=Path, required=True, help="权要稿.md 路径")
    parser.add_argument("--output", type=Path, required=True, help="输出 PNG 路径")
    parser.add_argument("--claim-number", type=int, default=1,
                        help="方法独立权要编号（默认 1）")
    parser.add_argument("--label-md", type=Path, default=None,
                        help="同时输出「图1内容-供 Visio 手画」md（与 PNG 同一 clauses + 同一 wrap_label，"
                             "杜绝手画稿与成品图折行不一致）")
    args = parser.parse_args()

    clauses = extract_claim_clauses(args.claims_md, args.claim_number)
    if VAGUE_FINAL.search(clauses[-1]):
        print("WARN\t末分句含模糊结果词（技术结果/处理结果/最终结果）；"
              "图 1 终点节点建议为具体领域结果（权要已冻结，仅提示不阻断）")
    render_png(clauses, args.output)
    print(f"{args.output}")
    print(f"OK\t图1：{len(clauses)} 个节点（S11–S1{len(clauses)}），"
          f"节点文字=权要{args.claim_number}分句逐字")
    if args.label_md:
        args.label_md.write_text(render_label_md(clauses), encoding="utf-8")
        print(f"{args.label_md}")
        print("OK\t图1 手画稿：节点文字与本脚本同源（**不预折行**，粘进 Visio 由用户框宽自行折行）")
    return 0


if __name__ == "__main__":
    # Windows GBK 控制台: 输出含全角字符, 裸跑 UnicodeEncodeError (H2609029 实测, 2026-09-10)。强制 UTF-8。
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main())

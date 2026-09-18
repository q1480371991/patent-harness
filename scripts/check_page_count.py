#!/usr/bin/env python3
"""
篇幅页数闸门 (篇幅硬线, 王工 2026-08-27「整个说明书+附图不超过30页, 这个是法条要求」).

与 `check_hard_rules.py` 的 L8-1 稿次字数区间条 (Word 口径、从 md 算) 互为交叉验证:
字数是**写稿时可控的先行指标**, 页数是**交付件的实际结果**。五案实测约 550-600 CJK
字 = 1 页, 即 2 万字 ≈ 33-36 页 —— 两条线基本等价, 但页数只能在 DOCX 上量。

判据: DOCX `docProps/app.xml` 的 `<Pages>` 字段 > 30 即 FAIL。
⚠️ 该值含权利要求书与摘要, 是**上界** —— 读到 32-33 页时说明书本体可能已达标, 但
王工看的就是整件页数, 不据此放宽。

★★ `<Pages>` 的可信性前提 (本脚本最大的坑, 静默放行比误报危险):
`Pages` 由 Word/WPS 在**最后一次保存时**写入, 纯脚本注入 (inject_fulltext_docx.py)
生成而未经 Word/WPS 打开另存的 DOCX, 该字段会**停留在模板的旧值**(通常 1-5 页)。
此时若直接判 PASS 就是假绿灯。故本脚本对"可疑陈旧"的 Pages 一律报 **STALE 而非 PASS**
(exit=2), 要求用 Word/WPS 打开另存后重跑。

判"陈旧"的启发式 (任一命中即 STALE):
  ① 无 app.xml, 或无 <Pages> 字段;
  ② Pages <= 8 且 md 侧字数 > 8000 (一份 8000 字以上的说明书不可能只有 8 页);
  ③ 传了 --md 且 Pages < 估算页数的 60% (估算 = CJK 字数 / 575).

五案实测校准 (Pages 字段与 tests/regression/regress_page_count.py 的 EXPECT 基准逐案吻合, 故本判据可靠):
  X2607043 定稿 28 / X2607040 定稿 33 / X2607134 定稿 34 / H2608040 定稿 31
  / X2608107 定稿 36 ← 全部与基准表一致; X2608107 我的 2 稿 46 (五案唯一破线)
⚠️ 同一份 app.xml 里的 `<Words>` 字段**不可用** —— 实测 X2608107 我的 2 稿实际
21531 字, Words 写的是 4260。字数一律走 check_hard_rules.py 的 L8-1 字数条从 md 算。

用法:
    python scripts/check_page_count.py <交付.docx>
    python scripts/check_page_count.py <交付.docx> --md docs/全文稿.md   # 开启陈旧检测
    python scripts/check_page_count.py <交付.docx> --max 30 --json

Exit code: 0 = PASS, 1 = 超页数 FAIL, 2 = Pages 不可信 (STALE) 或读取失败.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

PAGES_RE = re.compile(r"<Pages>(\d+)</Pages>")
CJK_PER_PAGE = 575          # 五案实测 550-600 CJK 字/页, 取中值
DEFAULT_MAX_PAGES = 30      # 篇幅硬线 (王工口径): 说明书+附图 ≤30 页


def read_pages(docx: Path) -> int | None:
    """读 docProps/app.xml 的 <Pages>; 缺 app.xml 或缺字段返回 None."""
    with zipfile.ZipFile(docx) as z:
        if "docProps/app.xml" not in z.namelist():
            return None
        xml = z.read("docProps/app.xml").decode("utf-8", errors="replace")
    m = PAGES_RE.search(xml)
    return int(m.group(1)) if m else None


def md_cjk_count(md: Path) -> int:
    text = md.read_text(encoding="utf-8")
    text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    text = re.sub(r"\$[^$]*\$", "", text)
    return len(re.findall(r"[一-鿿]", text))


def main() -> int:
    ap = argparse.ArgumentParser(description="交付 DOCX 页数闸门 (篇幅硬线: ≤30 页)")
    ap.add_argument("docx", help="交付 DOCX 路径")
    ap.add_argument("--md", help="对应 md 基准 (全文稿.md; 传入即开启 Pages 陈旧检测)")
    ap.add_argument("--claims-md", help="权要稿 md (分离式工作流, 与 --md 合并计字数)")
    ap.add_argument("--max", type=int, default=DEFAULT_MAX_PAGES, help="页数上限, 默认 30")
    ap.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    a = ap.parse_args()

    docx = Path(a.docx)
    if not docx.is_file():
        print(f"读取失败: 找不到 {docx}", file=sys.stderr)
        return 2

    try:
        pages = read_pages(docx)
    except (zipfile.BadZipFile, OSError) as e:
        print(f"读取失败: {e}", file=sys.stderr)
        return 2

    cjk = 0
    for p in (a.md, a.claims_md):
        if p and Path(p).is_file():
            cjk += md_cjk_count(Path(p))
    est = round(cjk / CJK_PER_PAGE) if cjk else None

    stale_reasons: list[str] = []
    if pages is None:
        stale_reasons.append("app.xml 缺失或无 <Pages> 字段")
    else:
        if cjk > 8000 and pages <= 8:
            stale_reasons.append(f"Pages={pages} 但 md 侧 {cjk} CJK 字 —— 不可能只有 {pages} 页")
        if est and pages < est * 0.6:
            stale_reasons.append(f"Pages={pages} 远低于按字数估算的 {est} 页 (<60%)")

    result = {
        "docx": str(docx),
        "pages": pages,
        "max_pages": a.max,
        "md_cjk": cjk or None,
        "estimated_pages": est,
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "ok": bool(pages is not None and not stale_reasons and pages <= a.max),
    }

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if stale_reasons:
            print(f"[check_page_count] STALE  {docx.name}", file=sys.stderr)
            for r in stale_reasons:
                print(f"  · {r}", file=sys.stderr)
            print("  → <Pages> 由 Word/WPS 最后一次保存时写入; 脚本注入生成的 DOCX 该字段"
                  "停留在模板旧值。请用 Word/WPS 打开该文件、另存后重跑本脚本。"
                  "**不得据当前值判达标**(根因: 自证清白式结论是最高风险信号)",
                  file=sys.stderr)
        elif result["ok"]:
            extra = f" (md {cjk} CJK 字, 估算 {est} 页)" if est else ""
            print(f"[check_page_count] PASS  {pages} 页 ≤ {a.max}{extra}  {docx.name}",
                  file=sys.stderr)
        else:
            print(f"[check_page_count] FAIL  {pages} 页 > 上限 {a.max}  {docx.name}",
                  file=sys.stderr)
            print("  → 篇幅硬线 (王工 2026-08-27「整个说明书+附图不超过30页, 这个是法条要求」)。",
                  file=sys.stderr)
            print("  → ⚠️ 先判根因是「讲得太细」还是「对象太多」: X2608107 实测按 X14 顺序"
                  "删满 2777 字后 46→36 页仍超线, 证明**删示例救不回来**。真正的杠杆是"
                  "预设对象总量 (2.4a 权要 ≤4-5 / 2.4b 返修增量)。", file=sys.stderr)
            print("  → 不得用「删可实施细节」凑线 (implementation.md L8-1 明文禁止, 反向踩 26.3)。",
                  file=sys.stderr)

    if stale_reasons or pages is None:
        return 2
    return 0 if pages <= a.max else 1


if __name__ == "__main__":
    # Windows GBK 控制台: 输出含 GBK 外字符时裸跑 UnicodeEncodeError (H2609029 实测, 2026-09-10)。强制 UTF-8。
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())

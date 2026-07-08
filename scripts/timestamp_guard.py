#!/usr/bin/env python3
"""
版本时序守卫 (ADR-0005 / 审2 复盘 5.3).

审2 事故根因: 用 6-19 的说明书交付 6-27 的权要——`docs/全文稿.md` 早于最新
权要审核稿存在, 却被静默沿用注入. 本守卫在全文一稿 / 返修入口处检查:

    docs/全文稿.md 的 mtime  <  任一 审核*.docx / 权要审核稿 的 mtime

命中即输出警告并 exit 3 (非硬错, 但要求主 agent 停下, 进入
"权要变更 diff → 说明书同步清单 → 逐项落实"流程, 不允许静默沿用旧稿).

判定按文件 mtime; 若同时有 fingerprint_claims.py 的指纹校验, 两者互补:
时序守卫抓"稿比审核稿旧"的可疑, 指纹抓"权要内容实际变了"的确证.

用法:
    # 传案件目录, 自动 glob 审核稿
    python3 scripts/timestamp_guard.py --case <案件文件夹>
    # 或显式指定
    python3 scripts/timestamp_guard.py --fulltext docs/全文稿.md \
        --review-glob '审核*.docx'

exit: 0 = 全文稿不早于任何审核稿 (放行); 2 = 用法错误;
      3 = 全文稿早于某审核稿 (可疑, 停下走 diff 流程).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


def _mtime(p: Path) -> float:
    return p.stat().st_mtime


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def find_fulltext(case: Path) -> Path | None:
    """案件目录下定位全文稿.md: 优先 docs/全文稿.md."""
    for cand in (case / "docs" / "全文稿.md", case / "全文稿.md"):
        if cand.exists():
            return cand
    return None


def collect_reviews(case: Path, patterns: list[str]) -> list[Path]:
    """收集案件目录 (含 docs/ 与根) 下匹配审核稿模式的 DOCX."""
    found: list[Path] = []
    for base in (case, case / "docs"):
        if not base.exists():
            continue
        for pat in patterns:
            found.extend(base.glob(pat))
    # 去重 (同一文件可能被多个 base/pat 命中), 排除临时锁文件 ~$
    uniq = {}
    for p in found:
        if p.name.startswith("~$"):
            continue
        uniq[p.resolve()] = p
    return list(uniq.values())


def run(fulltext: Path, reviews: list[Path]) -> int:
    if not reviews:
        print("[timestamp_guard] PASS 未发现审核稿 DOCX, 无时序风险 (放行)", file=sys.stderr)
        return 0
    ft_m = _mtime(fulltext)
    newer = [(p, _mtime(p)) for p in reviews if _mtime(p) > ft_m]
    if not newer:
        latest = max(_mtime(p) for p in reviews)
        print(f"[timestamp_guard] PASS 全文稿 ({_fmt(ft_m)}) 不早于任何审核稿 "
              f"(最新审核稿 {_fmt(latest)}) (放行)", file=sys.stderr)
        return 0
    newer.sort(key=lambda x: x[1], reverse=True)
    print(f"[timestamp_guard] FAIL 全文稿 {fulltext.name} ({_fmt(ft_m)}) "
          f"早于以下审核稿, 可能基于过期权要:", file=sys.stderr)
    for p, m in newer:
        print(f"    · {p.name}  ({_fmt(m)})", file=sys.stderr)
    print("  → 不得静默沿用. 按 full-draft.md L8-0 / revision.md 权要变更跨阶段联动: "
          "先跑 fingerprint_claims.py --check 确认权要是否实际变更, 变则做 "
          "新旧权要 diff → 说明书同步清单 → 逐项落实 (硬停)", file=sys.stderr)
    return 3


def main() -> int:
    ap = argparse.ArgumentParser(description="版本时序守卫 (ADR-0005).")
    ap.add_argument("--case", help="案件文件夹 (自动定位全文稿.md 与 审核*.docx)")
    ap.add_argument("--fulltext", help="全文稿.md 路径 (不传 --case 时必填)")
    ap.add_argument("--review-glob", action="append", default=None,
                    help="审核稿 glob 模式, 可多次; 默认 '审核*.docx'")
    args = ap.parse_args()

    patterns = args.review_glob or ["审核*.docx"]

    if args.case:
        case = Path(args.case)
        if not case.exists():
            print(f"[timestamp_guard] ERROR 案件目录不存在: {case}", file=sys.stderr)
            return 2
        fulltext = find_fulltext(case)
        if fulltext is None:
            print(f"[timestamp_guard] ERROR 案件目录下未找到 全文稿.md: {case}", file=sys.stderr)
            return 2
        reviews = collect_reviews(case, patterns)
    else:
        if not args.fulltext:
            print("[timestamp_guard] ERROR 需传 --case 或 --fulltext", file=sys.stderr)
            return 2
        fulltext = Path(args.fulltext)
        if not fulltext.exists():
            print(f"[timestamp_guard] ERROR 全文稿不存在: {fulltext}", file=sys.stderr)
            return 2
        reviews = collect_reviews(fulltext.parent.parent, patterns) or \
            collect_reviews(fulltext.parent, patterns)

    return run(fulltext, reviews)


if __name__ == "__main__":
    sys.exit(main())

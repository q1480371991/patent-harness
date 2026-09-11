#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rules_budget.py — 规则读取量预算表：按阶段统计「该阶段要读的规则文件」字符数。

用途（防无声膨胀）：skill 的规则文件逐案增补是常态，但**每个阶段实际要读多少字**没人量过。
本脚本按 `rules.md` 阶段读取表的口径把各阶段读取量加总，并与基线比对——超过基线 10% 时报
提示，触发一次「这段新规则该不该进必读层」的审查（同 `rules.md`「必读核心文件设软上限」的
思路，只是把口径从**单文件行数**换成**阶段字符数**）。

用法：
    python scripts/rules_budget.py                 # 打印当前各阶段读取量
    python scripts/rules_budget.py --save          # 存基线到 docs/_rules_budget.json
    python scripts/rules_budget.py --check         # 与基线比对，超 10% 提示（exit 1）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
BASELINE = SKILL / "docs" / "_rules_budget.json"

# 阶段 → 读取文件（口径同 rules.md 阶段读取表；新增规则文件时同步本表）
STAGES: dict[str, list[str]] = {
    "权要一稿/直写权要闸门": ["global.md", "claims-requirements.md", "claims-field-background.md",
                              "docx-template.md", "scoring.md"],
    "直写全文稿": ["global.md", "claims-requirements.md", "claims-field-background.md",
                   "abstract-figures.md", "invention-content.md", "implementation.md",
                   "figures.md", "docx-template.md", "scoring.md"],
    "全文一稿": ["global.md", "abstract-figures.md", "invention-content.md", "implementation.md",
                 "figures.md", "docx-template.md", "scoring.md"],
    "返修": ["global.md", "revision.md", "revision-docx.md", "docx-template.md"],
}
ALSO = ["SKILL.md"]        # 每次会话都进上下文的
THRESHOLD = 0.10


def counts() -> dict[str, int]:
    out = {}
    for stage, files in STAGES.items():
        out[stage] = sum(len((SKILL / "references" / "rules" / f).read_text(encoding="utf-8"))
                         for f in files if (SKILL / "references" / "rules" / f).exists())
    out["_SKILL.md"] = len((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--save", action="store_true", help="存为基线")
    ap.add_argument("--check", action="store_true", help="与基线比对（超 10% 提示）")
    args = ap.parse_args(argv)

    cur = counts()
    if args.save:
        BASELINE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK\t基线已存 {BASELINE}")
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    over = []
    for k, v in cur.items():
        b = base.get(k)
        delta = (v - b) if b else None
        pct = f"{delta / b * 100:+.1f}%" if b else "—"
        flag = ""
        if b and delta > b * THRESHOLD:
            flag = "  ← 超基线 10%，触发一次「这段新规则该不该进必读层」审查"
            over.append(k)
        print(f"{k:<24}{v:>8} 字符   基线 {b if b else '—':>8}  {pct}{flag}")
    if args.check and over:
        print(f"\n[WARN] {len(over)} 个阶段读取量超基线 10%：{over}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())

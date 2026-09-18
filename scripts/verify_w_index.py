#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_w_index.py —— W 编号索引守卫（`references/rules/W-INDEX.md` 与规则文件的一致性）。

为什么需要
----------
`W-INDEX.md` 长期自称「自动生成」，但**仓内从来没有生成脚本**，也没有任何守卫盯着它 —— 结果是它被改坏而无人知：
2026-09-19 两路复核实测，30 行里 **12 行「定义文件/章节」与规则条实际所在不符、5 行是不存在的编号**
（W01／W17／W22／W24／W52 —— 全仓无此编号规则条，来源是把 `rules.md` 里 `W01–W52` 这种**区间记法**
当成编号展开）。本脚本把「索引 ↔ 规则文件」的一致性变成能机械跑的检查。

判据（每行三项，任一不符即 FAIL）
--------------------------------
  ① **定义文件存在**：`references/rules/<定义文件>` 必须存在；
  ② **章节是实际标题**：该文件内必须有一行标题（`#` 开头）的正文以「章节」列的字串**开头**；
  ③ **编号在该文件内出现**：该 W 编号必须作为 `W##` 字样出现在 `references/rules/<定义文件>` 内
     （即该编号确实由该文件承载，而不是只在本索引里）。

用法
----
    python scripts/verify_w_index.py           # 报告到 stderr
    python scripts/verify_w_index.py --json    # stdout 输出 JSON

Exit code = 失败行数；0 = 全部一致。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = SKILL_ROOT / "references" / "rules"
INDEX = RULES_DIR / "W-INDEX.md"

# 表格数据行：| W05 | invention-content.md | L6-1 1级规则 | 主题… |
ROW_RE = re.compile(r"^\|\s*(W\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")


def check() -> list[dict]:
    failures: list[dict] = []
    text = INDEX.read_text(encoding="utf-8")
    rows = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = ROW_RE.match(line)
        if m:
            rows.append((lineno, m.group(1), m.group(2), m.group(3)))

    if not rows:
        failures.append({"line": 0, "w": "-", "reason": "W-INDEX.md 表体零数据行（解析失败或表被清空）"})
        return failures

    # 表尾声明的总数须与实际行数一致
    m = re.search(r"总计：\s*(\d+)\s*个 W 编号", text)
    if m and int(m.group(1)) != len(rows):
        failures.append({"line": 0, "w": "-",
                         "reason": f"表尾声明「{m.group(1)} 个」与实际数据行数 {len(rows)} 不一致"})

    for lineno, w, rel, section in rows:
        f = RULES_DIR / rel
        if not f.exists():
            failures.append({"line": lineno, "w": w, "reason": f"定义文件不存在：references/rules/{rel}"})
            continue
        body = f.read_text(encoding="utf-8")
        # ② 章节须是实际标题
        if not any(ln.lstrip("#").strip().startswith(section) for ln in body.splitlines() if ln.startswith("#")):
            failures.append({"line": lineno, "w": w,
                             "reason": f"文件 {rel} 内无以此开头的标题：{section}"})
        # ③ 编号须在该文件内实际出现
        if not re.search(rf"\b{w}\b", body):
            failures.append({"line": lineno, "w": w,
                             "reason": f"编号 {w} 未出现在 {rel} 中（索引指错文件，或该编号根本无定义条）"})
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    failures = check()
    if args.json:
        print(json.dumps({"checked_rows": True, "failures": len(failures),
                          "details": failures}, ensure_ascii=False, indent=2))
    else:
        text = INDEX.read_text(encoding="utf-8")
        n_rows = sum(1 for ln in text.splitlines() if ROW_RE.match(ln))
        for d in failures:
            print(f"[FAIL] W-INDEX.md:{d['line']}  {d['w']}  {d['reason']}", file=sys.stderr)
        print(f"共 {n_rows} 行, 失败 {len(failures)}", file=sys.stderr)
    return len(failures)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())

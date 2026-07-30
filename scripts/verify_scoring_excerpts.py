#!/usr/bin/env python3
"""
scoring 摘录一致性守卫 (仅标准库).

`scoring.md` 的评分项按路实体化为四份静态摘录 `scoring-{claims,content,impl,global}.md`,
同步纪律原先只靠文件头告示牌. 本脚本把可机械化的部分变成检查:

- A. 评分前置纪律句在 `scoring.md` 与四份摘录中逐字在场;
- B. `scoring.md`「评分项与权重」节内每条评分项行都带至少一个已知【路】标注;
- C. 单路标注行的规则编号必须全部出现在该路摘录中 (多路标注行: 编号出现在
     任一被标注路的摘录中即可) —— 抓"改了 scoring.md 忘了改摘录";
- D. 摘录中出现的规则编号必须在 `scoring.md` 全文出现 —— 抓"摘录私自加项";
- E. `scoring-global.md` 含第一闸完整性清单锚点.

摘录是按路改写而非逐字复制, 语义级一致仍归人判; 本脚本只兜编号集合与
纪律句的漂移.

用法:
    python3 scripts/verify_scoring_excerpts.py           # 报告到 stderr
    python3 scripts/verify_scoring_excerpts.py --json    # stdout 输出 JSON

Exit code = 失败检查数; 0 = 全部一致.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent / "references" / "rules"
ROUTES = ("claims", "content", "impl", "global")
DISCIPLINE_SENTENCE = "无证据的 PASS 一律视为未检查"
RULE_ID_RE = re.compile(r"[GL][0-9](?:-[0-9])?")
TAG_RE = re.compile(r"【(claims|content|impl|global)】")


def rule_ids(text: str) -> set[str]:
    return set(RULE_ID_RE.findall(text))


def scoring_item_lines(scoring_text: str) -> list[str]:
    """「评分项与权重」→「计分方法」之间的评分项 bullet 行."""
    lines = scoring_text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("### 评分项与权重"))
        end = next(i for i, l in enumerate(lines) if l.startswith("### 计分方法"))
    except StopIteration:
        return []
    return [l for l in lines[start:end] if l.lstrip().startswith("- ")]


def run() -> list[dict]:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    scoring_text = (RULES_DIR / "scoring.md").read_text(encoding="utf-8")
    excerpts = {r: (RULES_DIR / f"scoring-{r}.md").read_text(encoding="utf-8") for r in ROUTES}

    # A. 前置纪律句逐字在场
    for name, text in [("scoring.md", scoring_text)] + [(f"scoring-{r}.md", excerpts[r]) for r in ROUTES]:
        add(f"A.前置纪律@{name}", DISCIPLINE_SENTENCE in text,
            "在场" if DISCIPLINE_SENTENCE in text else f"缺纪律句「{DISCIPLINE_SENTENCE}」")

    # B + C. 评分项行标注完备 + 编号进摘录
    items = scoring_item_lines(scoring_text)
    add("B.评分项区间可定位", bool(items), f"评分项 bullet 行 {len(items)} 条" if items else "定位不到评分项区间(节标题被改?)")
    for line in items:
        tags = TAG_RE.findall(line)
        preview = line.strip()[:42]
        if not tags:
            add("B.行有路标注", False, f"无【路】标注: {preview}…")
            continue
        ids = rule_ids(line)
        if not ids:
            continue
        pool = "".join(excerpts[t] for t in tags)
        missing = sorted(i for i in ids if i not in rule_ids(pool))
        add(f"C.编号进摘录[{'+'.join(tags)}]", not missing,
            f"{preview}… 全部命中" if not missing else f"{preview}… 缺 {missing} 于 {['scoring-%s.md' % t for t in tags]}")

    # D. 摘录不得私自加项
    scoring_ids = rule_ids(scoring_text)
    for r in ROUTES:
        extra = sorted(i for i in rule_ids(excerpts[r]) if i not in scoring_ids)
        add(f"D.摘录无私增@scoring-{r}.md", not extra,
            "无 scoring.md 之外的编号" if not extra else f"出现 scoring.md 没有的编号: {extra}")

    # E. global 摘录含第一闸完整性清单
    ok_e = "完整性" in excerpts["global"] and "一票否决" in excerpts["global"]
    add("E.global摘录含完整性清单", ok_e, "在场" if ok_e else "缺第一闸完整性清单")

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 scoring.md 与四份按路摘录的编号/纪律一致性.")
    parser.add_argument("--json", action="store_true", help="stdout 输出 JSON 报告 (给 AI 消费)")
    args = parser.parse_args()

    checks = run()
    failures = sum(1 for c in checks if not c["ok"])

    if args.json:
        print(json.dumps({"failures": failures, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        for c in checks:
            print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}", file=sys.stderr)
        print(f"共 {len(checks)} 项检查, 失败 {failures}", file=sys.stderr)
    return failures


if __name__ == "__main__":
    sys.exit(main())

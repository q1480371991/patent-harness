#!/usr/bin/env python3
"""
契约 sed 锚点校验 (auditor 定向提取守卫, 仅标准库).

四份 auditor 契约 (agents/*-auditor.md) 的规则读取已从"整篇 Read"改为
`sed -n '/^起始标题/,/^结束标题/p'` 按节定向提取. 本脚本机械校验每条
提取命令的两个锚点在规则文件 (references/rules/*.md) 中真实可命中,
防止规则文件标题行被改写后 auditor 静默取空:

- 起始锚点必须在恰好一个规则文件中命中, 且该文件内恰好一行
  (跨文件多命中 = 节编号冲突, 文件内多命中 = 区间歧义, 均 FAIL);
- 结束锚点必须在起始行之后命中;
- 提取区间必须非空 (起止之间至少一行正文).

用法 (每案件首次编排 auditor 前跑一次; 改规则文件标题或契约锚点后必跑):
    python3 scripts/verify_rule_anchors.py           # 报告到 stderr
    python3 scripts/verify_rule_anchors.py --json    # stdout 输出 JSON

Exit code = 失败锚点数; 0 = 全部命中.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = SKILL_ROOT / "agents"
RULES_DIR = SKILL_ROOT / "references" / "rules"

# 契约中 sed 提取命令的固定书写形态: sed -n '/START/,/END/p' [<var>]
SED_RANGE_RE = re.compile(r"sed -n '/([^']+?)/,/([^']+?)/p'(?:` |\s+<(\w+)>)?")


def load_rule_files() -> dict[str, list[str]]:
    files: dict[str, list[str]] = {}
    for path in sorted(RULES_DIR.glob("*.md")):
        files[path.name] = path.read_text(encoding="utf-8").splitlines()
    return files


def match_lines(pattern: str, lines: list[str]) -> list[int]:
    """返回 0-based 命中行号列表; 契约锚点为 ^ 起始的简单正则, BRE 与 Python re 兼容."""
    rx = re.compile(pattern)
    return [i for i, line in enumerate(lines) if rx.search(line)]


def check_anchor(contract: str, start: str, end: str, var: str | None,
                 rule_files: dict[str, list[str]]) -> dict:
    result = {
        "contract": contract,
        "var": var or "",
        "start": start,
        "end": end,
        "ok": False,
        "resolved_file": "",
        "detail": "",
    }
    try:
        candidates = {name: match_lines(start, lines) for name, lines in rule_files.items()}
    except re.error as exc:
        result["detail"] = f"锚点不是合法正则: {exc}"
        return result

    hits = {name: idx for name, idx in candidates.items() if idx}
    if not hits:
        result["detail"] = "起始锚点在所有规则文件中零命中 (标题行被改写?)"
        return result
    if len(hits) > 1:
        result["detail"] = f"起始锚点跨文件多命中 (节编号冲突): {sorted(hits)}"
        return result

    name, start_lines = next(iter(hits.items()))
    result["resolved_file"] = name
    if len(start_lines) > 1:
        result["detail"] = f"起始锚点在 {name} 内命中 {len(start_lines)} 行, 区间歧义"
        return result

    start_idx = start_lines[0]
    lines = rule_files[name]
    try:
        end_hits = [i for i in match_lines(end, lines) if i > start_idx]
    except re.error as exc:
        result["detail"] = f"结束锚点不是合法正则: {exc}"
        return result
    if not end_hits:
        result["detail"] = f"结束锚点在 {name} 第 {start_idx + 1} 行之后零命中"
        return result

    end_idx = end_hits[0]
    body = [l for l in lines[start_idx + 1:end_idx] if l.strip()]
    if not body:
        result["detail"] = f"{name} 第 {start_idx + 1}-{end_idx + 1} 行提取区间为空"
        return result

    result["ok"] = True
    result["detail"] = f"{name} 第 {start_idx + 1}-{end_idx + 1} 行, 正文 {len(body)} 行"
    return result


def run() -> tuple[list[dict], int]:
    rule_files = load_rule_files()
    checks: list[dict] = []
    contracts = sorted(AGENTS_DIR.glob("*.md"))
    for contract_path in contracts:
        text = contract_path.read_text(encoding="utf-8")
        for m in SED_RANGE_RE.finditer(text):
            checks.append(check_anchor(contract_path.name, m.group(1), m.group(2),
                                       m.group(3), rule_files))
    failures = sum(1 for c in checks if not c["ok"])
    if not checks:
        # 契约里一条 sed 提取都解析不到, 本身就是异常 (书写形态漂移).
        checks.append({
            "contract": "(agents/*.md)", "var": "", "start": "", "end": "",
            "ok": False, "resolved_file": "",
            "detail": "未在任何契约中解析到 sed -n 提取命令, 检查契约书写形态",
        })
        failures = 1
    return checks, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 auditor 契约 sed 锚点与规则文件标题匹配.")
    parser.add_argument("--json", action="store_true", help="stdout 输出 JSON 报告 (给 AI 消费)")
    args = parser.parse_args()

    checks, failures = run()

    if args.json:
        print(json.dumps({"failures": failures, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        for c in checks:
            mark = "PASS" if c["ok"] else "FAIL"
            var = f" <{c['var']}>" if c["var"] else ""
            print(f"[{mark}] {c['contract']}{var} /{c['start']}/ → {c['detail']}", file=sys.stderr)
        print(f"共 {len(checks)} 条提取命令, 失败 {failures}", file=sys.stderr)

    return failures


if __name__ == "__main__":
    sys.exit(main())

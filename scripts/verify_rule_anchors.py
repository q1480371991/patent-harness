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

# 契约中 sed 提取命令的书写形态: sed -n '/START/,/END/p' [<var>] 或 sed -n "/START/,/END/p"
# 引号类型用反向引用配对 (\1), 单双引号均识别 —— 早期版本把单引号写死在正则里,
# 契约改用双引号书写时该条锚点会整条从校验面上消失、零告警 (静默漏检).
SED_RANGE_RE = re.compile(
    r"""sed -n (['"])/(.+?)/,/(.+?)/p\1(?:` |\s+<(\w+)>)?"""
)

# 锚点提取的正文行数基线 (contract, start_anchor) -> 期望行数.
# 作用: sed 的 `/start/,/end/` 是"首次命中即闭区间", 若区间**内部**出现与结束锚点
# 同名的标题行, 提取会提前闭合并大幅塌缩 (实测 full-draft.md L8 区间从 90 行塌到
# 4 行、L8-1/L8-2/L8-3 全丢), 而旧逻辑只判 `if not body` (空才 FAIL), 非空即 PASS,
# 导致规则静默消失。基线比对把"塌缩"变成可检出的红灯。
# 维护: 规则文件正常增删条文后跑 `--update-baseline` 重写本文件的基线块。
ANCHOR_BASELINE: dict[tuple[str, str], int] = {
    ("claims-auditor.md", r"^## L1\. "): 80,
    ("content-auditor.md", r"^## L6\. "): 28,
    ("content-auditor.md", r"^### L8-0 "): 8,
    ("global-auditor.md", r"^## G3\. "): 95,
    ("global-auditor.md", r"^## 0\. "): 8,
    ("global-auditor.md", r"^## L2\. "): 44,
    ("global-auditor.md", r"^## L4\. "): 29,
    ("global-auditor.md", r"^## L7\. "): 13,
    ("global-auditor.md", r"^## G8-0\. "): 28,
    ("global-auditor.md", r"^### G8-2 "): 11,
    ("impl-auditor.md", r"^## L8\. "): 77,
    ("impl-auditor.md", r"^### G6-1 "): 32,
}

# 基线容差: 正文行数跌破基线的这个比例即 FAIL (规则条文正常增删不会腰斩).
BASELINE_SHRINK_TOLERANCE = 0.5

# 期望的 sed 提取命令总条数. 作用: 从契约里误删一条锚点时, 旧逻辑会从 12 条静默
# 降到 11 条仍报 0 失败 —— 且与"书写形态漂移导致解析不到"输出同形、无法区分.
EXPECTED_ANCHOR_COUNT = 12


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

    result["body_lines"] = len(body)
    # 区间塌缩检出: 只判"非空"不足以发现提前闭合 —— 区间内出现同名结束锚点时,
    # sed 会在首个命中处闭合, 正文可能从 90 行塌到 1 行, 而规则主体已全部丢失。
    baseline = ANCHOR_BASELINE.get((contract, start))
    if baseline is not None:
        result["baseline"] = baseline
        floor = int(baseline * BASELINE_SHRINK_TOLERANCE)
        if len(body) < floor:
            result["detail"] = (
                f"{name} 第 {start_idx + 1}-{end_idx + 1} 行, 正文 {len(body)} 行 —— "
                f"**区间塌缩**: 基线 {baseline} 行, 跌破下限 {floor} 行。"
                f"最常见成因是区间内部出现与结束锚点 /{end}/ 同名的标题行, "
                f"使 sed 提前闭合、该节规则主体丢失 (auditor 会静默少读规则)。"
                f"若确为规则文件正常瘦身, 跑 --update-baseline 重写基线"
            )
            return result

    result["ok"] = True
    detail = f"{name} 第 {start_idx + 1}-{end_idx + 1} 行, 正文 {len(body)} 行"
    if baseline is None:
        detail += "  (无基线登记: 新增锚点请跑 --update-baseline)"
    result["detail"] = detail
    return result


def run() -> tuple[list[dict], int]:
    rule_files = load_rule_files()
    checks: list[dict] = []
    contracts = sorted(AGENTS_DIR.glob("*.md"))
    for contract_path in contracts:
        text = contract_path.read_text(encoding="utf-8")
        for m in SED_RANGE_RE.finditer(text):
            # group(1)=引号(反向引用配对用), 2=起始锚点, 3=结束锚点, 4=变量名
            checks.append(check_anchor(contract_path.name, m.group(2), m.group(3),
                                       m.group(4), rule_files))
    failures = sum(1 for c in checks if not c["ok"])
    if not checks:
        # 契约里一条 sed 提取都解析不到, 本身就是异常 (书写形态漂移).
        checks.append({
            "contract": "(agents/*.md)", "var": "", "start": "", "end": "",
            "ok": False, "resolved_file": "",
            "detail": "未在任何契约中解析到 sed -n 提取命令, 检查契约书写形态",
        })
        failures = 1
    elif len(checks) != EXPECTED_ANCHOR_COUNT:
        # 条数校验: 误删一条锚点会从 12 条静默降到 11 条仍报 0 失败, 且与"书写形态
        # 漂移导致解析不到"在报告层同形。显式断言条数, 让两种故障都亮红灯。
        checks.append({
            "contract": "(锚点条数校验)", "var": "", "start": "", "end": "",
            "ok": False, "resolved_file": "",
            "detail": f"解析到 {len(checks)} 条 sed 提取命令, 期望 {EXPECTED_ANCHOR_COUNT} 条。"
                      f"成因二选一: ①契约里误删/新增了锚点 → 同步改 EXPECTED_ANCHOR_COUNT "
                      f"与 ANCHOR_BASELINE; ②某条锚点书写形态漂移致解析不到 "
                      f"(如引号被改成中文引号、sed 拆行) → 修回标准形态",
        })
        failures += 1
    return checks, failures


def update_baseline() -> int:
    """按当前实际提取行数重写本文件的 ANCHOR_BASELINE 与 EXPECTED_ANCHOR_COUNT.

    仅在**确认规则文件的增删是有意为之**时使用 (如正常瘦身/扩写规则条文后)。
    若锚点当前处于塌缩状态, 用它会把错误状态固化为基线 —— 故先跑一次校验,
    有失败项时拒绝更新并提示先修。
    """
    checks, failures = run()
    collapsed = [c for c in checks if not c["ok"] and "区间塌缩" in c.get("detail", "")]
    if collapsed:
        print("[update-baseline] 拒绝更新: 检出区间塌缩, 先修锚点再重写基线", file=sys.stderr)
        for c in collapsed:
            print(f"  {c['contract']} /{c['start']}/ → {c['detail'][:90]}", file=sys.stderr)
        return 1

    entries = [(c["contract"], c["start"], c["body_lines"])
               for c in checks if c.get("body_lines") is not None]
    if not entries:
        print("[update-baseline] 未解析到任何锚点, 放弃", file=sys.stderr)
        return 1

    src = Path(__file__).read_text(encoding="utf-8")
    block = "ANCHOR_BASELINE: dict[tuple[str, str], int] = {\n"
    for contract, start, n in entries:
        block += f'    ({contract!r}, r{start!r}): {n},\n'
    block += "}"
    new_src = re.sub(
        r"ANCHOR_BASELINE: dict\[tuple\[str, str\], int\] = \{.*?\n\}",
        block.replace("\\", "\\\\"), src, count=1, flags=re.S,
    )
    new_src = re.sub(r"EXPECTED_ANCHOR_COUNT = \d+",
                     f"EXPECTED_ANCHOR_COUNT = {len(entries)}", new_src, count=1)
    Path(__file__).write_text(new_src, encoding="utf-8")
    print(f"[update-baseline] 已重写 {len(entries)} 条基线, EXPECTED_ANCHOR_COUNT={len(entries)}",
          file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 auditor 契约 sed 锚点与规则文件标题匹配.")
    parser.add_argument("--json", action="store_true", help="stdout 输出 JSON 报告 (给 AI 消费)")
    parser.add_argument("--update-baseline", action="store_true",
                        help="按当前实际行数重写 ANCHOR_BASELINE (仅在规则增删是有意为之时用; "
                             "检出塌缩时拒绝更新)")
    args = parser.parse_args()

    if args.update_baseline:
        return update_baseline()

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

#!/usr/bin/env python3
"""
跨块结构校验脚本 (第二类硬规则).

消费 `scripts/extract_structure.py` 的结构 JSON, 做机械化数量比对:

- X1 (L8-0, 仅 full-draft): 权要 1 分号分句数 == 具体实施方式主步骤数.
- X2 (L8-0, 仅 full-draft): 主步骤编号为 S11..S1N 连续 (与权 1 分句一一对应).
- X3 (L1-1, 两阶段): 从权依附合法 —— 被依附权要存在且在前位 (基于结构邻接表,
  与 check_hard_rules.py 规则 5 互为双保险, 数据源不同).

其余第二类项 (权要 1 步骤数/附图 1 节点数、发明内容对每条权要、附图说明数 vs
附图设计节图数、反向特征校验、从权多元化依附) 为语义项, 归 `rule-auditor`
subagent 判定, 本脚本不越权.

用法 (主 agent 常规入口, 内部自动跑抽取):
    python3 scripts/check_cross_block.py --md docs/权要稿.md --stage claims-draft
    python3 scripts/check_cross_block.py --md docs/全文稿.md --stage full-draft

也可直接消费已有抽取 JSON:
    python3 scripts/check_cross_block.py --structure structure.json

输出 JSON 到 stdout (作为 `structure_check_result` 传给 rule-auditor),
报告到 stderr. Exit code = 抽取错误数 + 违规数; 0 = 全通过.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_structure import extract_structure  # noqa: E402


# -----------------------------------------------------------------------------
# 校验项
# -----------------------------------------------------------------------------


def _claim1(structure: dict) -> dict | None:
    claims = structure.get("claims") or {}
    for it in claims.get("items", []):
        if it["num"] == 1:
            return it
    return None


def check_x1_step_count(structure: dict, violations: list[dict]) -> None:
    """X1: 权要 1 分句数 == 主步骤数 (L8-0 Sxx 框架同构)."""
    claim1 = _claim1(structure)
    main = structure.get("main_steps")
    if claim1 is None or claim1.get("step_count") is None or main is None:
        return  # 抽取层已报错, 不重复
    n_claim = claim1["step_count"]
    n_main = main["count"]
    if n_claim != n_main:
        violations.append({
            "rule_id": "L8-0",
            "check": "X1",
            "location": "具体实施方式 vs 权利要求书",
            "evidence": f"权要 1 分句数 = {n_claim}, 主步骤数 = {n_main} ({', '.join(main['ids'])})",
            "message": f"主步骤数应等于权要 1 分句数 (期望 {n_claim}, 实际 {n_main}), "
                       "不得增删/合并/拆分步骤",
        })


def check_x2_step_numbering(structure: dict, violations: list[dict]) -> None:
    """X2: 主步骤编号 S11..S1N 连续 (L8-0)."""
    main = structure.get("main_steps")
    if main is None or main["count"] == 0:
        return
    nums = sorted(int(sid[1:]) for sid in main["ids"])
    expected = list(range(11, 11 + len(nums)))
    if nums != expected:
        violations.append({
            "rule_id": "L8-0",
            "check": "X2",
            "location": "具体实施方式",
            "evidence": f"实际主步骤编号 = {['S%d' % n for n in nums]}",
            "message": f"主步骤编号应为 S11..S{10 + len(nums)} 连续 "
                       f"(期望 {['S%d' % n for n in expected]})",
        })


def check_x3_dependency(structure: dict, violations: list[dict]) -> None:
    """X3: 依附/引用合法 —— 单点依附与范围引用的目标权要均须存在且在前位."""
    claims = structure.get("claims") or {}
    items = claims.get("items", [])
    nums = {it["num"] for it in items}
    for it in items:
        for dep in it.get("depends_on", []):
            if dep not in nums:
                violations.append({
                    "rule_id": "L1-1",
                    "check": "X3",
                    "location": f"权要 {it['num']} (md 第{it['start_line']}行起)",
                    "evidence": f"依附了权要 {dep}",
                    "message": f"权要 {it['num']} 依附的权要 {dep} 不存在",
                })
            elif dep >= it["num"]:
                violations.append({
                    "rule_id": "L1-1",
                    "check": "X3",
                    "location": f"权要 {it['num']} (md 第{it['start_line']}行起)",
                    "evidence": f"依附了权要 {dep}",
                    "message": f"权要 {it['num']} 依附了后位权要 {dep} (应依附前位)",
                })
        for lo, hi in it.get("range_refs", []):
            bad = None
            if lo > hi:
                bad = f"范围下界 {lo} 大于上界 {hi}"
            elif hi >= it["num"]:
                bad = f"范围上界 {hi} 不在本权要 {it['num']} 之前"
            elif not all(n in nums for n in range(lo, hi + 1)):
                missing = [n for n in range(lo, hi + 1) if n not in nums]
                bad = f"范围内权要 {missing} 不存在"
            if bad:
                violations.append({
                    "rule_id": "L1-1",
                    "check": "X3",
                    "location": f"权要 {it['num']} (md 第{it['start_line']}行起)",
                    "evidence": f"引用了权利要求 {lo} 至 {hi} 任一项",
                    "message": f"权要 {it['num']} 范围引用不合法: {bad}",
                })


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------


def run_checks(structure: dict) -> dict:
    violations: list[dict] = []
    if structure["stage"] == "full-draft":
        check_x1_step_count(structure, violations)
        check_x2_step_numbering(structure, violations)
    check_x3_dependency(structure, violations)

    return {
        "stage": structure["stage"],
        "md_path": structure["md_path"],
        "extraction_ok": structure["extraction_ok"],
        "extraction_errors": structure["extraction_errors"],
        "violation_count": len(violations),
        "violations": violations,
        "structure": structure,
    }


def format_human_report(result: dict) -> str:
    n_err = len(result["extraction_errors"])
    n_vio = result["violation_count"]
    if n_err == 0 and n_vio == 0:
        return (f"[check_cross_block] PASS  stage={result['stage']}  "
                f"file={result['md_path']}\n")
    out = [f"[check_cross_block] FAIL  stage={result['stage']}  "
           f"extraction_errors={n_err}  violations={n_vio}"]
    for e in result["extraction_errors"]:
        out.append(f"  - [STRUCT-EXTRACT] {e}")
    for v in result["violations"]:
        out.append(f"  - [{v['rule_id']}/{v['check']}] {v['location']}")
        out.append(f"      evidence: {v['evidence']}")
        out.append(f"      message : {v['message']}")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="第二类硬规则跨块校验.")
    parser.add_argument("--md", help="待审 md 草稿路径 (内部自动跑结构抽取)")
    parser.add_argument(
        "--stage", choices=["claims-draft", "full-draft"],
        help="当前阶段 (与 --md 搭配必填)",
    )
    parser.add_argument("--structure", help="已有 extract_structure JSON 文件路径")
    args = parser.parse_args()

    if args.structure:
        s_path = Path(args.structure)
        if not s_path.exists():
            print(f"[check_cross_block] ERROR structure json not found: {s_path}",
                  file=sys.stderr)
            return 2
        structure = json.loads(s_path.read_text(encoding="utf-8"))
    elif args.md and args.stage:
        md_path = Path(args.md)
        if not md_path.exists():
            print(f"[check_cross_block] ERROR md not found: {md_path}", file=sys.stderr)
            return 2
        structure = extract_structure(md_path, args.stage)
    else:
        parser.error("需要 --md + --stage, 或 --structure")
        return 2

    result = run_checks(structure)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(format_human_report(result), file=sys.stderr)

    return len(result["extraction_errors"]) + result["violation_count"]


if __name__ == "__main__":
    sys.exit(main())

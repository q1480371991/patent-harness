#!/usr/bin/env python3
"""
跨块结构校验脚本 (第二类硬规则).

消费 `scripts/extract_structure.py` 的结构 JSON, 做机械化数量比对:

- X1 (L8-0, 仅 full-draft): 权要 1 分号分句数 == 具体实施方式主步骤覆盖数.
- X2 (L8-0, 仅 full-draft): 主步骤编号为 S11..S1N 连续 (与权 1 分句一一对应).
- X3 (L1-1, 两阶段): 从权依附/范围引用合法 —— 目标权要存在且在前位.
- X4 (L8-0, 仅 full-draft): 主步骤不得用 `在步骤Sx至步骤Sy中` 合并展开.

其余第二类项 (权要 1 步骤数/附图 1 节点数、发明内容对每条权要、附图说明数 vs
反向特征校验、从权多元化依附) 为语义项, 归各路 auditor (multi-auditor)
subagent 判定, 本脚本不越权.

用法 (主 agent 常规入口, 内部自动跑抽取):
    python3 scripts/check_cross_block.py --md docs/权要稿.md --stage claims-draft
    python3 scripts/check_cross_block.py --md docs/全文稿.md --stage full-draft --claims-md docs/权要稿.md

分离式工作流的全文稿.md 不含权利要求书 (冻结在权要稿.md), full-draft 必须
用 --claims-md 传入权要基准; 一体式 md (自含权要章节) 可省略.

也可直接消费已有抽取 JSON:
    python3 scripts/check_cross_block.py --structure structure.json

输出 JSON 到 stdout (作为 `structure_check_result` 传给各路 auditor),
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


def _covered_step_nums(main: dict) -> set[int]:
    """单步引导句 + 合并引导句展开后的全部已覆盖主步骤编号."""
    nums = {int(sid[1:]) for sid in main["ids"]}
    for m in main.get("merged", []):
        nums.update(range(m["from_num"], m["to_num"] + 1))
    return nums


def check_x1_step_count(structure: dict, violations: list[dict]) -> None:
    """X1: 权要 1 分句数 == 主步骤覆盖数 (L8-0 Sxx 框架同构)."""
    claim1 = _claim1(structure)
    main = structure.get("main_steps")
    if claim1 is None or claim1.get("step_count") is None or main is None:
        return  # 抽取层已报错, 不重复
    n_claim = claim1["step_count"]
    covered = _covered_step_nums(main)
    n_main = len(covered)
    if n_claim != n_main:
        merged_note = ""
        if main.get("merged"):
            spans = ", ".join(f"S{m['from_num']}至S{m['to_num']}" for m in main["merged"])
            merged_note = f"; 含合并展开 {spans}"
        violations.append({
            "rule_id": "L8-0",
            "check": "X1",
            "location": "具体实施方式 vs 权利要求书",
            "evidence": f"权要 1 分句数 = {n_claim}, 主步骤覆盖数 = {n_main} "
                        f"({', '.join('S%d' % n for n in sorted(covered))}{merged_note})",
            "message": f"主步骤覆盖数应等于权要 1 分句数 (期望 {n_claim}, 实际 {n_main}), "
                       "不得增删/合并/拆分步骤",
        })


def check_x2_step_numbering(structure: dict, violations: list[dict]) -> None:
    """X2: 主步骤编号 S11..S1N 连续 (L8-0), 合并引导句展开后一并计入."""
    main = structure.get("main_steps")
    if main is None:
        return
    nums = sorted(_covered_step_nums(main))
    if not nums:
        return
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


def check_x4_no_merged_steps(structure: dict, violations: list[dict]) -> None:
    """X4: 主步骤不得合并展开 (L8-0: 不得增删/合并/拆分步骤)."""
    main = structure.get("main_steps")
    if main is None:
        return
    for m in main.get("merged", []):
        violations.append({
            "rule_id": "L8-0",
            "check": "X4",
            "location": f"具体实施方式 (md 第{m['line']}行)",
            "evidence": m["text"],
            "message": f"步骤S{m['from_num']}至S{m['to_num']}用了合并展开引导句; "
                       "L8-0 要求每个主步骤单独按 L8-1 范式展开 "
                       "(`在步骤SxN中，〔复述权1对应分句〕，包括：...`), 不得合并",
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


def check_x5_fmnr_dep_expansion(structure: dict, violations: list[dict]) -> None:
    """X5: 发明内容"进一步地"从权展开段数/分句数 == 权要方法从权 (L6-1 分号同构).

    发明内容应对每条方法从权 (权2..权N, dependent 且非系统权) 各有一段
    "进一步地……包括："分号分段展开; 段数不符 = 漏写/合并从权; 逐段分句数 !=
    对应从权 step_count = 未分号分段或漏/多子步骤. (补 verify_claims_alignment 盲区:
    其步骤集差集只核权1/从权在三节'有无对应展开'的粗粒度, 不核发明内容对从权的分号
    分段与子步骤数一致.)
    """
    fmnr = structure.get("fmnr_deps")
    claims = structure.get("claims") or {}
    if not fmnr:
        return  # 发明内容无"进一步地"从权展开段: 不核段数(交 verify_claims_alignment 步骤集差集兜底), 避免对极简/不展开从权风格误伤
    method_deps = [it for it in claims.get("items", [])
                   if it["num"] >= 2 and it.get("dependent")
                   and it.get("subject") is None and it.get("step_count")]
    if not method_deps:
        return
    if len(fmnr) != len(method_deps):
        violations.append({
            "rule_id": "L6-1",
            "check": "X5",
            "location": "发明内容 vs 权利要求书",
            "evidence": f"发明内容'进一步地'从权段数 = {len(fmnr)}, 方法从权数 = {len(method_deps)}",
            "message": f"发明内容应对每条方法从权 (权2..权{method_deps[-1]['num']}) 各有一段分号分段展开; "
                       f"段数不符 (期望 {len(method_deps)}, 实际 {len(fmnr)}), 疑漏写或合并从权展开",
        })
    for i in range(min(len(fmnr), len(method_deps))):
        cc = fmnr[i]["clause_count"]
        sc = method_deps[i]["step_count"]
        if cc != sc:
            note = "; 且子步骤挤在引导行(逗号连缀未分段)" if fmnr[i].get("inline_after") else ""
            violations.append({
                "rule_id": "L6-1",
                "check": "X5",
                "location": f"发明内容 (md 第{fmnr[i]['line']}行)",
                "evidence": f"该段分句数 = {cc}, 对应权 {method_deps[i]['num']} 子步骤数 = {sc}{note}",
                "message": f"发明内容第 {i + 1} 段从权展开分句数应等于对应从权分句数 "
                           f"(期望 {sc}, 实际 {cc}); 未分号分段或漏/多子步骤",
            })


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------


def run_checks(structure: dict) -> dict:
    violations: list[dict] = []
    if structure["stage"] == "full-draft":
        check_x1_step_count(structure, violations)
        check_x2_step_numbering(structure, violations)
        check_x4_no_merged_steps(structure, violations)
        check_x5_fmnr_dep_expansion(structure, violations)
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
    parser.add_argument(
        "--claims-md",
        help="权要基准 md 路径 (分离式工作流: 全文稿不含权要时传 docs/权要稿.md)",
    )
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
        claims_md_path = Path(args.claims_md) if args.claims_md else None
        if claims_md_path is not None and not claims_md_path.exists():
            print(f"[check_cross_block] ERROR claims md not found: {claims_md_path}",
                  file=sys.stderr)
            return 2
        structure = extract_structure(md_path, args.stage, claims_md_path)
    else:
        parser.error("需要 --md + --stage, 或 --structure")
        return 2

    result = run_checks(structure)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(format_human_report(result), file=sys.stderr)

    return len(result["extraction_errors"]) + result["violation_count"]


if __name__ == "__main__":
    sys.exit(main())

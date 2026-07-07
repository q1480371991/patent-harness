#!/usr/bin/env python3
"""
结构抽取器 (第二类硬规则前置).

按 A/B 标准写法 (H2606029 / H2605066) 从 md 草稿抽取结构化 JSON, 供
`scripts/check_cross_block.py` 与各路 auditor subagent 消费:

- 权要块: 编号 / 独权从权 / 保护主题 / 从权依附邻接表 / 分号分句
- 具体实施方式主步骤: 行首 `在步骤S<nn>中，` (L8-1 主步骤展开范式)
- 具体实施方式子步骤: 行首 `步骤S<nnn>：`
- 附图说明: 行首 `图N为...` / `图N是...`
- 附图设计节是否存在 (只报存在性; 附图内容深审不在 md 闸门范围)

写法不合 A/B 标准时**报错停** (不做宽容猜测): C 类全角空格章节标题、
非 `在步骤SxN中` 的主步骤写法等一律视为结构不规范, 要求主 agent 先按
A/B 写法规范化 md 再重跑.

用法:
    python3 scripts/extract_structure.py --md docs/权要稿.md --stage claims-draft
    python3 scripts/extract_structure.py --md docs/全文稿.md --stage full-draft

输出 JSON 到 stdout. extraction_errors 非空时 exit 2, 否则 exit 0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_hard_rules import (  # noqa: E402
    extract_claim_blocks,
    get_section_lines,
    load_md,
    split_sections,
)

# -----------------------------------------------------------------------------
# A/B 标准写法正则 (唯一出处: subagent 分支结构标记侦查清单, 2026-07)
# -----------------------------------------------------------------------------

# 主步骤: `在步骤S11中，...` (中文/半角逗号)
MAIN_STEP_RE = re.compile(r"^\s*在步骤S(\d+)中[，,]")
# 合并主步骤: `在步骤S17至步骤S19中，...` (L8-0 禁止合并展开, 抽出来供校验定位)
MERGED_STEP_RE = re.compile(r"^\s*在步骤S(\d+)至步骤S(\d+)中[，,]")
# 子步骤: `步骤S151：...` (中文/半角冒号)
SUB_STEP_RE = re.compile(r"^\s*步骤S(\d+)[：:]")
# 附图说明: `图1为...` / `图1是...`
FIGURE_RE = re.compile(r"^\s*图\s*(\d+)[为是]")
# 从权引用: `根据权利要求N所述`
DEP_REF_RE = re.compile(r"根据权利要求\s*(\d+)\s*所述")
# 范围引用 (计算机设备式系统权/存储介质权): `权利要求M至N(中)任(意)一项所述`
RANGE_REF_RE = re.compile(r"权利要求\s*(\d+)\s*至\s*(\d+)\s*(?:中)?任意?一项所述")
# 保护主题: `一种...方法/系统/装置/(存储)介质`
SUBJECT_RE = re.compile(r"(一种[^，。；]{2,40}?(?:方法|系统|装置|存储介质|介质))")


# -----------------------------------------------------------------------------
# 权要抽取
# -----------------------------------------------------------------------------


def _split_claim_steps(text: str) -> list[str] | None:
    """
    从单条权要正文抽分号分句 (步骤).

    A/B 标准: `N.一种...，其特征在于，(所述...)包括：分句1；分句2；...；分句M。`
    锚点优先级: "其特征在于"之后的第一个"包括：" > "其特征在于，"直接后文.
    抽不出锚点返回 None (由调用方决定是否算结构错误).
    """
    anchor = text.find("其特征在于")
    if anchor < 0:
        return None
    rest = text[anchor + len("其特征在于"):]
    m = re.search(r"包括[：:]", rest)
    if m:
        body = rest[m.end():]
    else:
        body = rest.lstrip("，, ")
    body = body.strip()
    if not body:
        return None
    steps = [s.strip().rstrip("。").strip() for s in body.split("；")]
    steps = [s for s in steps if s]
    return steps or None


def extract_claims(lines: list[str], sections: dict, errors: list[str]) -> dict | None:
    """抽取权利要求书结构. 关键结构缺失时写入 errors 并返回已抽到的部分."""
    blocks = extract_claim_blocks(lines, sections)
    if not blocks:
        errors.append(
            "权利要求书结构抽取失败: 未找到 `## 权利要求书` 章节或 `N.` 编号权要段"
        )
        return None

    items = []
    for num in sorted(blocks):
        start, end = blocks[num]
        text = "\n".join(lines[start:end]).strip()
        flat = text.replace("\n", "")
        deps = sorted({int(d) for d in DEP_REF_RE.findall(flat)})
        range_refs = [[int(a), int(b)] for a, b in RANGE_REF_RE.findall(flat)]
        subj_m = SUBJECT_RE.search(flat)
        steps = _split_claim_steps(flat)
        items.append({
            "num": num,
            "start_line": start + 1,
            # dependent 仅指单点依附从权; 范围引用型 (系统权/介质权) 是名义独权
            "dependent": bool(deps),
            "depends_on": deps,
            "range_refs": range_refs,
            "subject": subj_m.group(1) if subj_m else None,
            "step_count": len(steps) if steps else None,
            "steps": steps,
        })

    claim1 = next((it for it in items if it["num"] == 1), None)
    if claim1 is None:
        errors.append("权利要求书结构抽取失败: 未找到权要 1")
    elif claim1["steps"] is None:
        errors.append(
            "权要 1 分句抽取失败: 未找到 `其特征在于(，...包括：)` 锚点, "
            "写法不合 A/B 标准"
        )

    return {"total": len(items), "items": items}


# -----------------------------------------------------------------------------
# 具体实施方式 / 附图说明抽取 (full-draft)
# -----------------------------------------------------------------------------


def _scan_pattern(body: list[str], offset: int, pattern: re.Pattern) -> list[dict]:
    found = []
    for i, line in enumerate(body):
        m = pattern.match(line)
        if m:
            found.append({
                "id": f"S{m.group(1)}",
                "num": int(m.group(1)),
                "line": offset + i + 1,
                "text": line.strip()[:120],
            })
    return found


def extract_steps(lines: list[str], sections: dict, errors: list[str]) -> tuple[dict | None, dict | None]:
    """抽取具体实施方式的主步骤 / 子步骤."""
    body, offset = get_section_lines(lines, sections, "具体实施方式")
    if offset < 0:
        errors.append("未找到 `## 具体实施方式` 章节")
        return None, None

    main_items = _scan_pattern(body, offset, MAIN_STEP_RE)
    sub_items = _scan_pattern(body, offset, SUB_STEP_RE)

    merged_items = []
    for i, line in enumerate(body):
        m = MERGED_STEP_RE.match(line)
        if m:
            merged_items.append({
                "from_num": int(m.group(1)),
                "to_num": int(m.group(2)),
                "line": offset + i + 1,
                "text": line.strip()[:120],
            })

    main_ids = sorted({it["num"] for it in main_items})
    sub_ids = sorted({it["num"] for it in sub_items})

    if not main_items and not merged_items:
        errors.append(
            "主步骤抽取失败: 具体实施方式内无 `在步骤SxN中，` 行, "
            "写法不合 A/B 标准 (L8-1 主步骤展开范式)"
        )

    main = {
        "count": len(main_ids),
        "ids": [f"S{n}" for n in main_ids],
        "occurrences": main_items,
        "merged": merged_items,
    }
    sub = {
        "count": len(sub_ids),
        "ids": [f"S{n}" for n in sub_ids],
        "occurrences": sub_items,
    }
    return main, sub


def extract_figures(lines: list[str], sections: dict, errors: list[str]) -> dict | None:
    """抽取附图说明的图 N 清单."""
    body, offset = get_section_lines(lines, sections, "附图说明")
    if offset < 0:
        errors.append("未找到 `## 附图说明` 章节")
        return None
    items = []
    for i, line in enumerate(body):
        m = FIGURE_RE.match(line)
        if m:
            items.append({
                "num": int(m.group(1)),
                "line": offset + i + 1,
                "text": line.strip()[:120],
            })
    if not items:
        errors.append(
            "附图说明抽取失败: 无 `图N为/图N是` 行, 写法不合 A/B 标准"
        )
        return None
    return {"count": len(items), "nums": [it["num"] for it in items], "items": items}


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------


def extract_structure(md_path: Path, stage: str, claims_md_path: Path | None = None) -> dict:
    lines = load_md(md_path)
    sections = split_sections(lines)
    errors: list[str] = []

    # 权要来源: 主 md 自含权利要求书章节时用主 md;
    # 分离式工作流 (全文稿.md 不含权要, 冻结在权要稿.md) 用 --claims-md 传入权要稿.
    claims_source = "self"
    claims_lines, claims_sections = lines, sections
    if not any("权利要求书" in t for t in sections):
        if claims_md_path is not None:
            claims_lines = load_md(claims_md_path)
            claims_sections = split_sections(claims_lines)
            claims_source = "claims_md"
        elif stage == "full-draft":
            errors.append(
                "主 md 不含 `## 权利要求书` 章节 (分离式工作流权要冻结在权要稿.md): "
                "请用 --claims-md <案件文件夹>/docs/权要稿.md 传入权要基准"
            )
            claims_source = None

    claims = None
    if claims_source is not None:
        claims = extract_claims(claims_lines, claims_sections, errors)

    main_steps = sub_steps = figures = None
    figure_design_present = False
    if stage == "full-draft":
        main_steps, sub_steps = extract_steps(lines, sections, errors)
        figures = extract_figures(lines, sections, errors)
        _, fd_offset = get_section_lines(lines, sections, "附图设计")
        figure_design_present = fd_offset >= 0

    return {
        "stage": stage,
        "md_path": str(md_path),
        "claims_md_path": str(claims_md_path) if claims_md_path else None,
        "claims_source": claims_source,
        "extraction_ok": not errors,
        "extraction_errors": errors,
        "claims": claims,
        "main_steps": main_steps,
        "sub_steps": sub_steps,
        "figures": figures,
        "figure_design_present": figure_design_present,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="第二类硬规则结构抽取器 (A/B 标准写法).")
    parser.add_argument("--md", required=True, help="待抽取 md 草稿路径")
    parser.add_argument(
        "--stage", required=True,
        choices=["claims-draft", "full-draft"],
        help="当前阶段 (claims-draft 仅抽权要, full-draft 全量)",
    )
    parser.add_argument(
        "--claims-md",
        help="权要基准 md 路径 (分离式工作流: 全文稿不含权要时传 docs/权要稿.md)",
    )
    args = parser.parse_args()

    md_path = Path(args.md)
    if not md_path.exists():
        print(f"[extract_structure] ERROR md not found: {md_path}", file=sys.stderr)
        return 2
    claims_md_path = Path(args.claims_md) if args.claims_md else None
    if claims_md_path is not None and not claims_md_path.exists():
        print(f"[extract_structure] ERROR claims md not found: {claims_md_path}", file=sys.stderr)
        return 2

    result = extract_structure(md_path, args.stage, claims_md_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result["extraction_ok"]:
        print(
            "[extract_structure] FAIL 结构不规范, 请按 A/B 标准写法 "
            "(H2606029 / H2605066) 规范化 md 后重跑:",
            file=sys.stderr,
        )
        for e in result["extraction_errors"]:
            print(f"  - {e}", file=sys.stderr)
        return 2
    print(f"[extract_structure] PASS stage={args.stage} file={md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

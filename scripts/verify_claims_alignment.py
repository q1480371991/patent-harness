#!/usr/bin/env python3
"""
权要-说明书对齐校验 (反向特征差集 / 撞名 / 步骤集差集).

审2 复盘 5.1 的机械执行层. 消费 `extract_structure.py` 的权要分句 + 直接读
md 三节文本 (具体实施方式 + 发明内容 + 有益效果), 做三项断言:

- A1 反向特征差集 (L8-0 反向断言, 唯一出处 full-draft.md L8-0):
  说明书三节出现、而权利要求书不存在的实体名词 (带"所述/预设"特征指代形态
  的专名). 语义边界靠正则近似, 判为 **suspect** (供 auditor 复核).
- A2 权要内撞名 (claims.md L1-1): 同一实体名词在权要内被多处赋值为不同来源
  (既"提取...得到 X"又"将...作为 X"). 语义, 判为 **suspect**.
- A3 步骤集差集 (full-draft.md L8-1): 权要每条分句的末端产物名是否在三节被
  复述. 产物名字符串在三节完全缺失 = **hard** (机械可确定, FAIL).

分档纪律:
- hard: 机械可确定, 与 auditor 冲突时以本脚本为准 (scoring 双通道).
- suspect: 正则近似的语义线索, 不直接 FAIL, 回传 auditor 复核确认.

用法:
    python3 scripts/verify_claims_alignment.py --md docs/全文稿.md \
        --claims-md docs/权要稿.md --stage full-draft

输出 JSON 到 stdout, 人读报告到 stderr.
exit code = hard 违规数 (0 = 无 hard 违规; suspect 不计入 exit code).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_hard_rules import get_section_lines, load_md, split_sections  # noqa: E402
from extract_structure import extract_structure  # noqa: E402

# -----------------------------------------------------------------------------
# 实体名词 / 产物名抽取 (正则近似; 实体名词定义见 full-draft.md L8-0)
# -----------------------------------------------------------------------------

# 规范化时剥离的前缀 (第一/第二.. 序号词、所述、预设、该、一个)
_PREFIX_RE = re.compile(
    r"^(?:所述|预设的|预设|该|各|每个|一个|一种|多个|上述|前述"
    r"|第[一二三四五六七八九十]+)+"
)

# "所述X" 里 X 若以下列动词/介词开头, 说明 X 不是名词而是动词短语, 丢弃
_VERB_HEAD_RE = re.compile(
    r"^(?:根据|基于|对|将|按|在|把|通过|利用|使|从|向|以|经|对于|由|为)"
)

# 特征指代形态实体名词: 所述X / 预设(的)X (收紧: 遇虚词/动词边界即停, 核心名词 ≤8 字)
_STOP = r"的|大于|小于|高于|低于|等于|为|时|按|进行|包括|和|与|及|或|不|中|个|条|项"
_ENTITY_REF_RE = re.compile(r"(?:所述|预设的?)([一-龥]{2,8}?)(?=" + _STOP + r"|[，。；、）：]|$)")

# 产物名: 生成性动词 + 名词 (末端产物, 用于步骤集差集与撞名)
_PRODUCT_RE = re.compile(
    r"(?:得到|生成|确定|获得|输出|形成|构建|计算得到|提取出)"
    r"([一-龥]{2,8}?)(?=" + _STOP + r"|[，。；、）：]|$)"
)

# 撞名信号: X 被"提取/计算类"生成 vs 被"作为"赋值
_ASSIGN_AS_RE = re.compile(r"作为([一-龥]{2,14})")


def normalize_entity(s: str) -> str:
    """剥离序号/所述/预设前缀, 得到核心名词, 用于跨句比较."""
    prev = None
    cur = s.strip()
    while cur != prev:
        prev = cur
        cur = _PREFIX_RE.sub("", cur)
    return cur


def extract_entities(text: str) -> set[str]:
    """抽取一段文本里的实体名词核心集 (规范化后)."""
    out: set[str] = set()
    for m in _ENTITY_REF_RE.finditer(text):
        raw = m.group(1)
        if _VERB_HEAD_RE.match(raw):
            continue
        norm = normalize_entity(raw)
        if len(norm) >= 2:
            out.add(norm)
    for m in _PRODUCT_RE.finditer(text):
        norm = normalize_entity(m.group(1))
        if len(norm) >= 2:
            out.add(norm)
    return out


def extract_products_ordered(text: str) -> list[str]:
    """按出现顺序抽末端产物名 (规范化), 用于步骤集差集."""
    out: list[str] = []
    for m in _PRODUCT_RE.finditer(text):
        norm = normalize_entity(m.group(1))
        if len(norm) >= 2:
            out.append(norm)
    return out


# -----------------------------------------------------------------------------
# 三节文本获取
# -----------------------------------------------------------------------------


def get_section_text(md_path: Path, key: str) -> tuple[str, bool]:
    """取单节文本, 返回 (文本, 是否命中)."""
    lines = load_md(md_path)
    sections = split_sections(lines)
    body, offset = get_section_lines(lines, sections, key)
    return ("\n".join(body), offset >= 0)


def get_frame_text(md_path: Path, struct: dict) -> tuple[str, dict]:
    """
    反向特征校验(A1)只作用于**框架句**, 不碰解释段:
    - 具体实施方式: 只取主步骤句 `在步骤SxN中，...` (struct.main_steps),
      不取后续解释段 (实施细节名词合法出现在解释段, 不算越界).
    - 发明内容(含有益效果): 整节取 (发明内容本是权要概括, 出现权要外特征即越界,
      审3 批注 25/26/27 正是在有益效果抓到权要没有的"异常信号").
    """
    hits = {}
    parts = []
    main = struct.get("main_steps") or {}
    for occ in (main.get("occurrences") or []):
        parts.append(occ.get("text", ""))
    hits["具体实施方式主步骤句"] = bool(main.get("occurrences"))
    inv_text, inv_hit = get_section_text(md_path, "发明内容")
    hits["发明内容"] = inv_hit
    if inv_hit:
        parts.append(inv_text)
    return "\n".join(parts), hits


def get_full_three_sections(md_path: Path) -> str:
    """步骤集差集(A3)用三节**全文**: 权要产物在解释段被复述也算数."""
    parts = []
    for key in ("具体实施方式", "发明内容"):
        body, hit = get_section_text(md_path, key)
        if hit:
            parts.append(body)
    return "\n".join(parts)


def claim_entities_and_steps(claims: dict) -> tuple[set[str], list[dict]]:
    """从权要结构抽实体名词集 + 每条分句的产物名 (步骤集基准)."""
    entities: set[str] = set()
    steps: list[dict] = []
    for it in claims.get("items", []):
        for sent in (it.get("steps") or []):
            entities |= extract_entities(sent)
            prods = extract_products_ordered(sent)
            steps.append({
                "claim_num": it["num"],
                "sentence": sent[:80],
                "products": prods,
            })
    return entities, steps


# -----------------------------------------------------------------------------
# 三项断言
# -----------------------------------------------------------------------------


def check_reverse_features(claim_ents: set[str], frame_text: str) -> list[dict]:
    """A1 反向特征差集 (suspect): 框架句实体名词 − 权要实体名词 (核心名词 ≤8 字)."""
    spec_ents = {e for e in extract_entities(frame_text) if 2 <= len(e) <= 8}
    diff = sorted(spec_ents - claim_ents)
    suspects = []
    for e in diff:
        m = re.search(r".{0,20}" + re.escape(e) + r".{0,20}", frame_text)
        suspects.append({
            "assert": "A1-反向特征差集",
            "confidence": "suspect",
            "entity": e,
            "evidence": (m.group(0).replace("\n", " ") if m else ""),
            "note": "框架句出现而权要实体名词集无; 若为功能性换述/白名单项请豁免",
        })
    return suspects


def check_name_collision(claims: dict) -> list[dict]:
    """A2 权要内撞名 (suspect): 同一产物名既被生成又被'作为'赋值, 或多来源."""
    flat = ""
    for it in claims.get("items", []):
        for sent in (it.get("steps") or []):
            flat += sent + "；"
    # 产物名 → 生成动词证据集
    gen_map: dict[str, list[str]] = {}
    for m in _PRODUCT_RE.finditer(flat):
        name = normalize_entity(m.group(1))
        ctx = flat[max(0, m.start() - 18):m.end()].replace("\n", " ")
        gen_map.setdefault(name, []).append(ctx)
    as_map: dict[str, list[str]] = {}
    for m in _ASSIGN_AS_RE.finditer(flat):
        name = normalize_entity(m.group(1))
        ctx = flat[max(0, m.start() - 18):m.end() + 4].replace("\n", " ")
        as_map.setdefault(name, []).append(ctx)

    suspects = []
    names = {n for n in (set(gen_map) | set(as_map)) if len(n) >= 2}
    for name in sorted(names):
        gen_ev = gen_map.get(name, [])
        as_ev = as_map.get(name, [])
        # 撞名信号: 既被生成(提取/计算类)又被"作为"赋值 → 疑似两义
        both = bool(gen_ev) and bool(as_ev)
        # 或同一名产物出现在 >=2 条不同分句的不同生成语境
        multi_gen = len(set(gen_ev)) >= 2
        if both or multi_gen:
            suspects.append({
                "assert": "A2-权要内撞名",
                "confidence": "suspect",
                "entity": name,
                "evidence": (gen_ev + as_ev)[:4],
                "note": "同名可能指两义 (既生成又赋值/多来源); auditor 判是否需改名拆名",
            })
    return suspects


def check_step_set_diff(claim_steps: list[dict], spec_text: str) -> list[dict]:
    """A3 步骤集差集 (hard): 权要分句末端产物名在三节完全缺失 = FAIL."""
    violations = []
    for st in claim_steps:
        prods = st["products"]
        if not prods:
            continue
        # 只要该分句任一产物名在三节出现, 视为该步骤被复述; 全缺失才判 FAIL
        found = any(p and (p in spec_text) for p in prods)
        if not found:
            violations.append({
                "assert": "A3-步骤集差集",
                "confidence": "hard",
                "claim_num": st["claim_num"],
                "sentence": st["sentence"],
                "missing_products": prods,
                "note": "该权要分句的产物名在三节均未出现 = 步骤缺失 (完整性 FAIL)",
            })
    return violations


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------


def run(md_path: Path, claims_md_path: Path | None, stage: str) -> dict:
    struct = extract_structure(md_path, stage, claims_md_path)
    result = {
        "md_path": str(md_path),
        "claims_md_path": str(claims_md_path) if claims_md_path else None,
        "stage": stage,
        "ok": False,
        "errors": list(struct.get("extraction_errors") or []),
        "hard_violations": [],
        "suspects": [],
        "section_hits": {},
    }
    claims = struct.get("claims")
    if claims is None:
        result["errors"].append("权要结构抽取失败, 无法比对 (先修复 md 权要写法)")
        return result

    spec_text = get_full_three_sections(md_path)
    frame_text, hits = get_frame_text(md_path, struct)
    result["section_hits"] = hits
    if not spec_text.strip():
        result["errors"].append("未取到具体实施方式/发明内容三节文本")
        return result

    claim_ents, claim_steps = claim_entities_and_steps(claims)

    hard = check_step_set_diff(claim_steps, spec_text)
    suspects = (
        check_reverse_features(claim_ents, frame_text)
        + check_name_collision(claims)
    )
    result["hard_violations"] = hard
    result["suspects"] = suspects
    result["ok"] = not result["errors"]
    return result


def format_report(r: dict) -> str:
    out = []
    tag = "PASS" if (r["ok"] and not r["hard_violations"]) else "FAIL"
    out.append(
        f"[verify_claims_alignment] {tag}  stage={r['stage']}  "
        f"hard={len(r['hard_violations'])}  suspect={len(r['suspects'])}"
    )
    for e in r["errors"]:
        out.append(f"  ERROR  {e}")
    for v in r["hard_violations"]:
        out.append(
            f"  HARD   [{v['assert']}] 权{v['claim_num']} 缺失产物={v['missing_products']} "
            f"« {v['sentence']} »"
        )
    for s in r["suspects"]:
        ent = s.get("entity", "")
        out.append(f"  SUSP   [{s['assert']}] {ent}  {s.get('note','')}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="权要-说明书对齐校验 (反向特征/撞名/步骤集).")
    ap.add_argument("--md", required=True, help="全文稿 md 路径")
    ap.add_argument("--claims-md", help="权要基准 md (分离式工作流全文稿不含权要时必传)")
    ap.add_argument("--stage", default="full-draft", choices=["full-draft"])
    args = ap.parse_args()

    md_path = Path(args.md)
    if not md_path.exists():
        print(f"[verify_claims_alignment] ERROR md not found: {md_path}", file=sys.stderr)
        return 2
    claims_md_path = Path(args.claims_md) if args.claims_md else None
    if claims_md_path is not None and not claims_md_path.exists():
        print(f"[verify_claims_alignment] ERROR claims md not found: {claims_md_path}", file=sys.stderr)
        return 2

    r = run(md_path, claims_md_path, args.stage)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print(format_report(r), file=sys.stderr, end="")

    if r["errors"]:
        return 2
    return len(r["hard_violations"])


if __name__ == "__main__":
    sys.exit(main())

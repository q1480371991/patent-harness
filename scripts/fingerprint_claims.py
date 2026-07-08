#!/usr/bin/env python3
"""
权要基准指纹 (ADR-0005 / 审2 复盘 5.2).

给 `docs/全文稿.md` 头部维护一段 YAML front-matter 基准指纹, 锚定其所依据的
权要基准 (最新已审权要 md; DOCX 经 disclosure_docx_to_md 转写后的权要稿.md):

    ---
    基准权要: 权要稿.md
    sha1: <权要分句序列的 sha1>
    提取时间: 2026-07-08T14:30:00
    分句数: <权 1 分句数 N>
    ---

sha1 覆盖"全部权要的全部分号分句规范化序列"——权要一旦发生分句增删或文字改动,
sha1 即变. `--check` 在撰写/注入前重算当前权要基准 sha1 与 front-matter 比对,
不一致即**硬停** (exit 3), 提示按 full-draft.md L8-0 先做 diff→同步→重构.

用法:
    # 生成/更新指纹 (按当前权要基准写入全文稿.md 头)
    python3 scripts/fingerprint_claims.py --gen \
        --fulltext docs/全文稿.md --claims docs/权要稿.md

    # 校验 (撰写/注入前置闸门)
    python3 scripts/fingerprint_claims.py --check \
        --fulltext docs/全文稿.md --claims docs/权要稿.md

exit: 0 = 一致/已写入; 2 = 用法或抽取错误; 3 = 指纹不一致 (硬停).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_structure import extract_structure  # noqa: E402

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def compute_fingerprint(claims_md: Path) -> tuple[str, int, int]:
    """返回 (sha1, 全部权要分句总数, 权1分句数). 抽取失败抛 ValueError."""
    struct = extract_structure(claims_md, "claims-draft")
    if struct.get("extraction_errors"):
        raise ValueError("; ".join(struct["extraction_errors"]))
    claims = struct.get("claims") or {}
    all_sents: list[str] = []
    n_claim1 = 0
    for it in claims.get("items", []):
        sents = it.get("steps") or []
        if it["num"] == 1:
            n_claim1 = len(sents)
        for s in sents:
            all_sents.append(re.sub(r"\s+", "", s))
    if not all_sents:
        raise ValueError("未抽到任何权要分句, 无法计算指纹")
    payload = "\n".join(all_sents).encode("utf-8")
    return hashlib.sha1(payload).hexdigest(), len(all_sents), n_claim1


def parse_front_matter(text: str) -> dict:
    m = _FM_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def write_front_matter(fulltext: Path, fm: dict) -> None:
    text = fulltext.read_text(encoding="utf-8")
    block = "---\n" + "".join(f"{k}: {v}\n" for k, v in fm.items()) + "---\n"
    m = _FM_RE.match(text)
    if m:
        text = block + text[m.end():]
    else:
        text = block + text
    fulltext.write_text(text, encoding="utf-8")


def do_gen(fulltext: Path, claims_md: Path) -> int:
    sha1, n_all, n_c1 = compute_fingerprint(claims_md)
    fm = {
        "基准权要": claims_md.name,
        "sha1": sha1,
        "提取时间": datetime.now().isoformat(timespec="seconds"),
        "分句数": str(n_c1),
        "权要分句总数": str(n_all),
    }
    write_front_matter(fulltext, fm)
    print(f"[fingerprint] GEN 已写入 {fulltext.name} 头部: sha1={sha1[:12]}… "
          f"权1分句={n_c1} 总分句={n_all}", file=sys.stderr)
    return 0


def do_check(fulltext: Path, claims_md: Path) -> int:
    recorded = parse_front_matter(fulltext.read_text(encoding="utf-8"))
    if not recorded.get("sha1"):
        print("[fingerprint] CHECK FAIL 全文稿.md 头部无基准指纹 front-matter; "
              "先运行 --gen 建立基准, 或该稿未经指纹守卫产生 (硬停)", file=sys.stderr)
        return 3
    cur_sha1, n_all, n_c1 = compute_fingerprint(claims_md)
    if cur_sha1 != recorded["sha1"]:
        print("[fingerprint] CHECK FAIL 权要基准已变更 (sha1 不一致):", file=sys.stderr)
        print(f"  记录: {recorded.get('sha1','')[:12]}… (基准权要={recorded.get('基准权要')}, "
              f"权1分句={recorded.get('分句数')})", file=sys.stderr)
        print(f"  当前: {cur_sha1[:12]}… (权1分句={n_c1})", file=sys.stderr)
        print("  → 按 full-draft.md L8-0: 先做 新旧权要 diff → 说明书同步清单 → "
              "逐项落实, 重构受影响章节并 --gen 更新指纹后再继续 (硬停)", file=sys.stderr)
        return 3
    print(f"[fingerprint] CHECK PASS 权要基准未变 sha1={cur_sha1[:12]}… "
          f"权1分句={n_c1}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="权要基准指纹生成/校验 (ADR-0005).")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--gen", action="store_true", help="按当前权要基准写入全文稿.md 头指纹")
    mode.add_argument("--check", action="store_true", help="校验全文稿.md 头指纹与当前权要基准是否一致")
    ap.add_argument("--fulltext", required=True, help="docs/全文稿.md 路径")
    ap.add_argument("--claims", required=True, help="权要基准 md 路径 (docs/权要稿.md)")
    args = ap.parse_args()

    fulltext, claims_md = Path(args.fulltext), Path(args.claims)
    for p in (fulltext, claims_md):
        if not p.exists():
            print(f"[fingerprint] ERROR 文件不存在: {p}", file=sys.stderr)
            return 2
    try:
        return do_gen(fulltext, claims_md) if args.gen else do_check(fulltext, claims_md)
    except ValueError as e:
        print(f"[fingerprint] ERROR 权要抽取失败: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

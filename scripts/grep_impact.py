#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grep_impact.py —— 改动下游回查：把「我记得查过哪几处」换成「全稿穷举、逐处销项」

用途
----
H2609100 全文复盘（2026-09-22）：本轮把权 5 引导句补了「所述」，回查时核了权要 3 处 +
说明书 2 处，**漏了说明书里「在一种实施方式中，〔引导句〕，包括：」这一族衔接句**，
王工审核v2 批注 3 亲手指出。同轮 F4（「所述初始弹性矩阵」漏查 S13 展开段正文）是同一形状。

根因不是不懂规则，是**回查范围靠记忆**——「我记得查过哪几处」。本脚本把它变成机械动作：
给定本轮改动的关键词，**穷举它在全稿的出现处**，输出一张待判清单，逐处标注
「已同步 / 不需同步 / 漏改」。**清单本身就是产物**——缺了就是没做，可独立复核。

「该查哪些词」仍由人给（改了什么只有人知道）；本脚本负责**保证不漏掉位置**。

用法
----
    python grep_impact.py 服役时间数据 所述孔洞平均直径 --in docs/全文稿.md
    python grep_impact.py 刚度退化矩阵 --in docs/全文稿.md docs/权要稿.md
    python grep_impact.py 服役时间数据 --in docs/全文稿.md --only-changed

输出：每个词一张表（文件 / 行号 / 上下文 40 字 / 待判栏留空），末尾给合计。
退出码：0 = 全部词都找到；1 = 有词在全稿 0 命中（**可能是已改完，也可能是词给错了**，
须当场确认——0 命中同样要销项）。
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def scan(word: str, files: list[Path]) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if word in line:
                hits.append((f.name, i, line.strip()[:60]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="改动下游回查：全稿穷举关键词出现处")
    ap.add_argument("words", nargs="+", help="本轮改动的关键词（可多个）")
    ap.add_argument("--in", dest="files", nargs="+", required=True,
                    help="待查稿件路径（可多个）")
    args = ap.parse_args()

    files = [Path(p) for p in args.files]
    missing = [f for f in files if not f.is_file()]
    if missing:
        print("ERROR\t文件不存在：" + "、".join(str(f) for f in missing), file=sys.stderr)
        return 2

    zero: list[str] = []
    total = 0
    for w in args.words:
        hits = scan(w, files)
        total += len(hits)
        print(f"=== 关键词「{w}」 命中 {len(hits)} 处 ===")
        if not hits:
            zero.append(w)
            print("  （全稿 0 命中——确认是已改完，还是关键词给错了）")
        for name, ln, ctx in hits:
            print(f"  [ ] {name}:{ln}  {ctx}")
        print()
    print("-" * 60)
    print(f"合计 {len(args.words)} 个关键词、{total} 处——**逐处标注「已同步／不需同步／漏改」后，"
          f"把这张清单贴进 reaudit_context**（缺清单即视为下游回查未做）")
    if zero:
        print(f"⚠️ 0 命中的词：{'、'.join(zero)}（须当场确认，不得跳过）")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

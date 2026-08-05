#!/usr/bin/env python3
"""
留痕/批注时间戳序列生成器 (去 AI 痕迹).

**问题**: 一次注入的全部 `w:ins`/`w:del`/回复批注若共用同一个 `date +...`
取值, Word/WPS 审阅窗格里所有痕迹显示同一分同一秒, 一眼即知机器批量生成.

**做法**: 生成一条**单调递增、间隔随机**的时间戳序列——首条为基准时间,
其后每条在前一条上累加 1-4 分钟随机值 + 0-59 秒抖动 (秒位抖动同样必要:
全部落在同一秒数本身也是痕迹).

**时区口径**: 沿用 `date +%Y-%m-%dT%H:%M:%SZ` 的既有约定——取**本地时间**
字面量并缀 `Z`. 本所查看器直接显示字符串的时分, 用 UTC 会让北京时间的
批注显示成凌晨, 反而更可疑. 故此处刻意不做时区换算.

用法:
    # 取当前时间为基准, 生成 10 条
    python3 scripts/gen_comment_timestamps.py --count 10

    # 指定基准时间 (接首轮之后的第二轮注入时可续上一轮末尾时间)
    python3 scripts/gen_comment_timestamps.py --count 5 --base 2026-08-06T10:30:00Z

    # 收窄间隔为 2-3 分钟
    python3 scripts/gen_comment_timestamps.py --count 5 --min-gap 2 --max-gap 3

    # JSON 输出 (便于注入脚本直接读)
    python3 scripts/gen_comment_timestamps.py --count 3 --json

输出: 默认每行一个 `w:date` 可直接使用的时间戳字符串.

exit: 0 = 成功; 2 = 用法错误.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta

FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_base(text: str) -> datetime:
    """解析基准时间字符串; 容忍缀 Z 与不缀 Z 两种写法, 一律当本地时间字面量."""
    return datetime.strptime(text.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")


def generate(count: int, base: datetime, min_gap: int, max_gap: int,
             rng: random.Random) -> list[str]:
    """
    生成单调递增、间隔随机的时间戳序列.

    count   条数; base 首条时间; min_gap/max_gap 相邻间隔的分钟数区间 (含端点);
    rng     随机源 (传入以便 --seed 复现).
    """
    out: list[str] = []
    cur = base
    for i in range(count):
        out.append(cur.strftime(FMT))
        if i < count - 1:
            cur += timedelta(minutes=rng.randint(min_gap, max_gap),
                             seconds=rng.randint(0, 59))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="生成留痕/批注用的递增随机间隔时间戳序列 (去 AI 痕迹).")
    ap.add_argument("--count", type=int, required=True,
                    help="要生成的时间戳条数 (= 本轮 w:ins/w:del/回复批注总条数)")
    ap.add_argument("--base",
                    help=f"基准时间 (格式 {FMT}, 本地时间字面量); 默认取当前时间")
    ap.add_argument("--min-gap", type=int, default=1,
                    help="相邻时间戳最小间隔分钟数 (默认 1)")
    ap.add_argument("--max-gap", type=int, default=4,
                    help="相邻时间戳最大间隔分钟数 (默认 4)")
    ap.add_argument("--seed", type=int,
                    help="随机种子; 仅用于测试复现, 实际注入不要传")
    ap.add_argument("--json", action="store_true",
                    help="以 JSON 数组输出, 便于注入脚本读取")
    args = ap.parse_args()

    if args.count < 1:
        print("[gen_comment_timestamps] ERROR --count 必须 >= 1", file=sys.stderr)
        return 2
    if args.min_gap < 0 or args.max_gap < args.min_gap:
        print(f"[gen_comment_timestamps] ERROR 间隔区间非法: "
              f"min-gap={args.min_gap} max-gap={args.max_gap}", file=sys.stderr)
        return 2

    if args.base:
        try:
            base = parse_base(args.base)
        except ValueError:
            print(f"[gen_comment_timestamps] ERROR --base 格式应为 {FMT}, "
                  f"实收: {args.base}", file=sys.stderr)
            return 2
    else:
        base = datetime.now()

    rng = random.Random(args.seed)
    stamps = generate(args.count, base, args.min_gap, args.max_gap, rng)

    if args.json:
        print(json.dumps(stamps, ensure_ascii=False, indent=2))
    else:
        for s in stamps:
            print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())

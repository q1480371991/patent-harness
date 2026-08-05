#!/usr/bin/env python3
"""
gen_comment_timestamps.py 单元测试.

覆盖去 AI 痕迹的核心不变量: 同一序列内时间戳互不重复、单调递增、
相邻间隔落在指定分钟区间内.
"""

import json
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "gen_comment_timestamps.py"

FMT = "%Y-%m-%dT%H:%M:%SZ"


def run_script(*args):
    """运行脚本并返回 CompletedProcess (不 check, 便于测错误分支)."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_lines(stdout):
    """把逐行输出解析为 datetime 列表."""
    return [datetime.strptime(ln, FMT) for ln in stdout.strip().split("\n") if ln]


class TestGenCommentTimestamps(unittest.TestCase):
    """测试批注时间戳序列生成器."""

    def test_basic_count(self):
        """生成指定条数, 且每条为合法 w:date 格式."""
        ret = run_script("--count", "3")
        self.assertEqual(ret.returncode, 0)
        lines = [ln for ln in ret.stdout.strip().split("\n") if ln]
        self.assertEqual(len(lines), 3)
        for ln in lines:
            self.assertRegex(ln, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_all_timestamps_distinct(self):
        """核心不变量: 同一序列内时间戳互不重复 (同值即 AI 痕迹)."""
        ret = run_script("--count", "12")
        self.assertEqual(ret.returncode, 0)
        lines = [ln for ln in ret.stdout.strip().split("\n") if ln]
        self.assertEqual(len(set(lines)), len(lines), "时间戳出现重复值")

    def test_monotonic_increasing(self):
        """序列单调递增."""
        ret = run_script("--count", "8")
        stamps = parse_lines(ret.stdout)
        self.assertEqual(len(stamps), 8)
        for i in range(1, len(stamps)):
            self.assertGreater(stamps[i], stamps[i - 1], f"第 {i} 条未递增")

    def test_default_gap_within_1_to_4_minutes(self):
        """默认间隔落在 1 分钟 ~ 4 分 59 秒 (含秒位抖动)."""
        ret = run_script("--count", "20")
        stamps = parse_lines(ret.stdout)
        for i in range(1, len(stamps)):
            delta = (stamps[i] - stamps[i - 1]).total_seconds()
            self.assertGreaterEqual(delta, 60, "间隔小于 1 分钟")
            self.assertLessEqual(delta, 4 * 60 + 59, "间隔大于 4 分 59 秒")

    def test_custom_gap_range(self):
        """--min-gap/--max-gap 收窄间隔区间."""
        ret = run_script("--count", "10", "--min-gap", "2", "--max-gap", "3")
        stamps = parse_lines(ret.stdout)
        for i in range(1, len(stamps)):
            delta = (stamps[i] - stamps[i - 1]).total_seconds()
            self.assertGreaterEqual(delta, 2 * 60)
            self.assertLessEqual(delta, 3 * 60 + 59)

    def test_base_time_is_first_stamp(self):
        """--base 指定的基准时间即首条时间戳."""
        ret = run_script("--count", "3", "--base", "2026-08-06T10:30:00Z")
        self.assertEqual(ret.stdout.strip().split("\n")[0], "2026-08-06T10:30:00Z")

    def test_base_accepts_no_trailing_z(self):
        """--base 容忍不缀 Z 的写法."""
        ret = run_script("--count", "1", "--base", "2026-08-06T10:30:00")
        self.assertEqual(ret.returncode, 0)
        self.assertEqual(ret.stdout.strip(), "2026-08-06T10:30:00Z")

    def test_reproducible_with_seed(self):
        """同 seed + 同 base 生成同一序列 (供测试复现)."""
        args = ("--count", "6", "--base", "2026-08-06T10:00:00Z", "--seed", "123")
        self.assertEqual(run_script(*args).stdout, run_script(*args).stdout)

    def test_different_seeds_differ(self):
        """不同 seed 生成不同序列."""
        base = ("--count", "6", "--base", "2026-08-06T10:00:00Z")
        out1 = run_script(*base, "--seed", "1").stdout
        out2 = run_script(*base, "--seed", "2").stdout
        self.assertNotEqual(out1, out2)

    def test_json_output(self):
        """--json 输出合法 JSON 数组."""
        ret = run_script("--count", "4", "--json")
        arr = json.loads(ret.stdout)
        self.assertIsInstance(arr, list)
        self.assertEqual(len(arr), 4)
        self.assertEqual(len(set(arr)), 4)

    def test_single_timestamp(self):
        """count=1 边界: 只回基准时间, 不做累加."""
        ret = run_script("--count", "1", "--base", "2026-01-01T00:00:00Z")
        self.assertEqual(ret.stdout.strip(), "2026-01-01T00:00:00Z")

    def test_invalid_count_zero(self):
        """count=0 报错 exit 2."""
        ret = run_script("--count", "0")
        self.assertEqual(ret.returncode, 2)
        self.assertIn("必须 >= 1", ret.stderr)

    def test_invalid_base_format(self):
        """非法 --base 格式报错 exit 2."""
        ret = run_script("--count", "1", "--base", "not-a-date")
        self.assertEqual(ret.returncode, 2)
        self.assertIn("格式应为", ret.stderr)

    def test_invalid_gap_range(self):
        """min-gap > max-gap 报错 exit 2."""
        ret = run_script("--count", "2", "--min-gap", "5", "--max-gap", "3")
        self.assertEqual(ret.returncode, 2)
        self.assertIn("间隔区间非法", ret.stderr)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patent_search.py —— patenthub.cn API 直连客户端（行业趋势对照用）

背景
----
王工 H2608165 审核v1 口径：「背景技术、技术问题、操作手段的选取符合行业趋势」三点
很重要，行业趋势判断的可靠依据是**同类真实专利**（而非模型训练记忆/泛网页）。
王工提供的 patent-analysis skill 的 .so 壳是 Linux/Py3.13 编译，Windows 跑不了；
本脚本直连官方 API（文档 https://www.patenthub.cn/api/interface.html），等价替代。

为什么不用官方 MCP：MCP 工具 schema 常驻上下文，写专利阶段上下文金贵；
本脚本按需调用、输出紧凑（默认只出 专利号|标题|申请人|申请日|IPC），零常驻开销。

认证
----
token 从环境变量 PATENT_HUB_TOKEN 读；未设置时可用 --token 传（勿把 key 写进
案件文档/交付件）。免费测试版额度：搜索 30 次/天、claims 20 次/天，一案用量
约 3-5 次搜索 + 5-10 次 claims，够用。

用法
----
  # 检索（默认紧凑表格输出）
  python patent_search.py search "穿梭车 高精度定位" --limit 10
  python patent_search.py search "documentYear:[2020 TO 2026] AND 穿梭车 定位" --sort !applicationDate
  # 多候选词轮询（行业趋势对照主用法：同义词/上位词/下位词各检一轮，合并去重）
  python patent_search.py multi "四向穿梭车 定位" "穿梭车 融合定位" "RGV 位置校准"

  # 查权利要求（判断「操作手段是否符合行业习惯」的核心材料）
  python patent_search.py claims CN122540533A

  # 输出原始 JSON（调试/需要全字段时）
  python patent_search.py search "穿梭车" --json

退出码：0 正常；1 API 报错（错误码/网络）；2 用法错误
"""

import argparse
import json
import os
import sys
import urllib.parse

try:
    import requests
except ImportError:
    print('缺 requests：pip install requests', file=sys.stderr)
    sys.exit(2)

BASE = 'https://www.patenthub.cn/api'
V = '1'


def _get(path: str, params: dict) -> dict:
    """GET 并统一处理 patenthub 错误码。"""
    r = requests.get(BASE + path, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get('success', False):
        code = data.get('code')
        hints = {
            206: '没有找到对应数据',
            207: '调用量用尽', 211: '总量用尽',
            208: '权限不足', 215: '限流，30 秒后重试',
        }
        print(f'API 错误 code={code}: {hints.get(code, "未知")} path={path}', file=sys.stderr)
        sys.exit(1)
    return data


def _token(arg_token):
    tok = arg_token or os.environ.get('PATENT_HUB_TOKEN', '')
    if not tok:
        print('未提供 token：设环境变量 PATENT_HUB_TOKEN 或用 --token', file=sys.stderr)
        sys.exit(2)
    return tok


def cmd_search(a):
    """搜索接口 /api/s。q 支持官方检索式（AND / 字段:值 / [年 TO 年]）。"""
    data = _get('/s', {
        't': _token(a.token), 'q': a.query, 'v': V,
        'ps': min(a.limit, 50), 'p': a.page,
        **({'s': a.sort} if a.sort else {}),
        **({'ds': a.ds} if a.ds else {}),
    })
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(f"共 {data.get('total')} 条（本页 {len(data.get('patents', []))} 条）")
    for p in data.get('patents', []):
        # 紧凑单行：专利号 | 标题 | 申请人 | 申请日 | IPC | 法律状态
        print('{} | {} | {} | {} | {} | {}'.format(
            p.get('documentNumber', ''),
            (p.get('title', '') or '')[:38],
            (p.get('applicant', '') or '')[:16],
            p.get('applicationDate', ''),
            p.get('mainIpc', ''),
            (p.get('legalStatus', '') or '')[:6],
        ))
    print('提示：看某条的权利要求 → python patent_search.py claims <专利号>')


def cmd_multi(a):
    """多候选词轮询合并去重（行业趋势对照主用法）。"""
    tok = _token(a.token)
    seen, rows = {}, []
    for q in a.queries:
        try:
            data = _get('/s', {'t': tok, 'q': q, 'v': V, 'ps': min(a.limit, 50)})
        except SystemExit:
            continue  # 单轮失败不中断整体
        for p in data.get('patents', []):
            num = p.get('documentNumber', '')
            if num and num not in seen:
                seen[num] = True
                rows.append(p)
    print(f"{len(a.queries)} 轮检索，去重后 {len(rows)} 条（按检索轮次顺序）")
    for p in rows[:a.limit]:
        print('{} | {} | {} | {} | {}'.format(
            p.get('documentNumber', ''),
            (p.get('title', '') or '')[:38],
            (p.get('applicant', '') or '')[:16],
            p.get('applicationDate', ''),
            p.get('mainIpc', ''),
        ))


def cmd_claims(a):
    """权利要求接口 /api/patent/claims（注意参数是 id 不是 q）。"""
    data = _get('/patent/claims', {'t': _token(a.token), 'id': a.patent_id, 'v': V})
    p = data.get('patent', {}) or {}
    claims = (p.get('claims', '') or '').replace('<br/>', '\n')
    if a.json:
        print(json.dumps(p, ensure_ascii=False, indent=2))
        return
    print(f"{p.get('documentNumber', a.patent_id)} 权利要求（{len(claims)} 字）：")
    print(claims)


def main():
    ap = argparse.ArgumentParser(description='patenthub.cn 直连客户端')
    ap.add_argument('--token', default='', help='缺省读环境变量 PATENT_HUB_TOKEN')
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('search', help='检索（支持官方检索式）')
    s.add_argument('query')
    s.add_argument('--limit', type=int, default=10)
    s.add_argument('--page', type=int, default=1)
    s.add_argument('--sort', default='', help='relation/!applicationDate/!documentDate/rank')
    s.add_argument('--ds', default='', help='cn（默认）/all')
    s.add_argument('--json', action='store_true')
    s.set_defaults(func=cmd_search)

    m = sub.add_parser('multi', help='多候选词轮询合并去重')
    m.add_argument('queries', nargs='+')
    m.add_argument('--limit', type=int, default=20)
    m.set_defaults(func=cmd_multi)

    c = sub.add_parser('claims', help='查权利要求')
    c.add_argument('patent_id')
    c.add_argument('--json', action='store_true')
    c.set_defaults(func=cmd_claims)

    a = ap.parse_args()
    a.func(a)


if __name__ == '__main__':
    # Windows GBK 控制台: 输出含 GBK 外字符时裸跑 UnicodeEncodeError (H2609029 实测, 2026-09-10)。强制 UTF-8。
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main() or 0)

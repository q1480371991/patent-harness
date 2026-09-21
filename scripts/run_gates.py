#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_gates.py —— 机械闸门总跑（一次跑完，出一张表）

用途
----
H2609100 全文1稿的出稿方式暴露的缺口：机械闸门清单只写在 `SKILL.md` 收尾 step 12
的一段话里，靠人记着挨个跑。那份审查报告的闸门表里只有 5 个脚本，
`check_preset_params` / `check_page_count` **不在**——既没跑、也没人发现少了，
因为**没有一份「应该跑哪些」的对照物**。产物因此不可独立复核（根因四补一维）。

本脚本把清单变成可执行的对照物：
    一条命令跑完 -> 输出一张表（闸门 / 退出码 / FAIL 数 / 备注）-> 汇总

三条纪律
--------
1. **跑不了的显式标「未执行」并给原因，不静默跳过**——1 稿就是静默少的。
2. **未执行项计入非零退出**（退出码 2），逼着人去补，而不是让表格看起来全绿。
3. 退出码：0 = 全部执行且全过；1 = 有闸门 FAIL；2 = 无 FAIL 但有未执行。
   有 FAIL 时同时打印「逐条处置」要求（改后原文 / 判为误报＋依据句原文与位置）。

用法
----
    python run_gates.py <案件目录>
    python run_gates.py <案件目录> --invention-name "<王工给定名称>"
    python run_gates.py <案件目录> --docx <交付.docx>
    python run_gates.py <案件目录> --phase claims     # 只跑权要阶段闸门
    python run_gates.py <案件目录> --json

案件目录约定：`<案件目录>/docs/权要稿.md`、`<案件目录>/docs/全文稿.md`；
交付 DOCX 默认在案件目录下按 `<案件号>-全文*稿-*.docx` 自动发现（排除审核稿）。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent


# ----------------------------------------------------------------- 闸门定义

class Gate:
    """一个闸门 = 一条命令 + 一份结论提取规则。

    count_re / note_re 只做「把脚本输出里已经写好的结论搬进表里」，
    不重新判定——判定权始终在脚本自己。
    """

    def __init__(self, key, name, phase, argv, needs=(), count_re=None,
                 note_re=None, count_mode="num"):
        self.key = key
        self.name = name
        self.phase = phase          # claims | full
        self.argv = argv            # 回调：ctx -> list[str]（不含解释器与脚本路径）
        self.needs = needs          # 需要的输入键；缺任一即「未执行」
        self.count_re = count_re
        self.note_re = note_re
        # count_mode 决定怎么读 count_re 的捕获组：
        #   "num"=直接取数字  "preset"=取分子  "obj_array"=数对象个数  "str_array"=数字符串条数
        self.count_mode = count_mode


def _mk_gates():
    return [
        Gate(
            key="hard_claims", name="check_hard_rules (权要)", phase="claims",
            argv=lambda c: ["--md", c["claims"], "--stage", "claims-draft"]
            + (["--invention-name", c["invention_name"]] if c.get("invention_name") else []),
            needs=("claims",),
            count_re=re.compile(r"violations=(\d+)"),
            note_re=re.compile(r"\[check_hard_rules\] (PASS|FAIL)"),
        ),
        Gate(
            key="hard_full", name="check_hard_rules (全文)", phase="full",
            argv=lambda c: ["--md", c["fulltext"], "--stage", "full-draft",
                            "--claims-md", c["claims"]]
            + (["--invention-name", c["invention_name"]] if c.get("invention_name") else []),
            needs=("claims", "fulltext"),
            count_re=re.compile(r"violations=(\d+)"),
            note_re=re.compile(r"\[check_hard_rules\] (PASS|FAIL)"),
        ),
        Gate(
            key="cross", name="check_cross_block (全文跨块)", phase="full",
            argv=lambda c: ["--md", c["fulltext"], "--stage", "full-draft",
                            "--claims-md", c["claims"]],
            needs=("claims", "fulltext"),
            count_re=re.compile(r'"violation_count":\s*(\d+)'),
            note_re=re.compile(r"\[check_cross_block\] (PASS|FAIL)"),
        ),
        Gate(
            key="align", name="verify_claims_alignment (权要-说明书对齐)", phase="full",
            argv=lambda c: ["--md", c["fulltext"], "--claims-md", c["claims"],
                            "--stage", "full-draft"],
            needs=("claims", "fulltext"),
            count_re=re.compile(r'"hard_violations":\s*\[(.*?)\]', re.S),
            note_re=re.compile(r'"ok":\s*(true|false)'),
            count_mode="obj_array",
        ),
        Gate(
            key="fingerprint", name="fingerprint_claims --check (权要自锁)", phase="full",
            argv=lambda c: ["--check", "--fulltext", c["fulltext"],
                            "--claims", c["claims"]],
            needs=("claims", "fulltext"),
            count_re=None,
            note_re=re.compile(r"\[fingerprint\] (PASS|CHECK|GEN|MISMATCH[^\n]*)"),
        ),
        Gate(
            key="preset", name="check_preset_params (预设量八槽)", phase="full",
            argv=lambda c: [c["fulltext"]],
            needs=("fulltext",),
            count_re=re.compile(r"FAIL：(\d+)/(\d+)"),
            note_re=re.compile(r"^(PASS：|FAIL：)([^\n]*)", re.M),
        ),
        Gate(
            key="timestamp", name="timestamp_guard (版本时序)", phase="full",
            argv=lambda c: ["--case", c["case"]],
            needs=("case",),
            count_re=None,
            note_re=re.compile(r"\[timestamp[^\]]*\]\s*([^\n]*)", re.I),
        ),
        Gate(
            key="pages", name="check_page_count (≤30 页)", phase="full",
            argv=lambda c: [c["docx"], "--md", c["fulltext"],
                            "--claims-md", c["claims"]],
            needs=("docx", "fulltext", "claims"),
            count_re=re.compile(r"(\d+)\s*页"),
            note_re=re.compile(r"\[check_page_count\]\s*([^\n]*)"),
        ),
        Gate(
            key="skeleton", name="verify_docx_skeleton (骨架/落位/格式)", phase="full",
            argv=lambda c: [c["docx"], "--stage", "全文"]
            + (["--invention-name", c["invention_name"]] if c.get("invention_name") else []),
            needs=("docx",),
            count_re=None,
            note_re=re.compile(r"^结果[:：]\s*([^\n]*)", re.M),
        ),
        Gate(
            key="injection", name="verify_docx_injection (注入机械项)", phase="full",
            argv=lambda c: [c["docx"], "--md", c["fulltext"]],
            needs=("docx", "fulltext"),
            count_re=None,
            note_re=re.compile(r"^结果[:：]\s*([^\n]*)", re.M),
        ),
        Gate(
            key="omml", name="omml_formulas check (公式健康)", phase="full",
            argv=lambda c: ["check", c["docx"]],
            needs=("docx",),
            count_re=re.compile(r'"errors":\s*\[(.*?)\]', re.S),
            note_re=re.compile(r'"warnings":\s*\[(.*?)\]', re.S),
            count_mode="str_array",
        ),
    ]


# ----------------------------------------------------------------- 执行

def _run(script, argv):
    cmd = [sys.executable, str(HERE / script)] + argv
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _extract(gate, out, code):
    """从脚本输出里搬出结论；搬不到就据实写『—』，不猜。"""
    count = "—"
    if gate.count_re:
        m = gate.count_re.search(out)
        if m:
            body_txt = m.group(1).strip()
            if gate.count_mode == "preset":
                count = m.group(1)                       # 缺槽个数
            elif gate.count_mode == "obj_array":         # 对象数组（hard_violations）
                count = 0 if not body_txt else len(re.findall(r"\{", body_txt))
            elif gate.count_mode == "str_array":         # 字符串数组（errors）
                count = 0 if not body_txt else len(re.findall(r'"[^"]+"', body_txt))
            else:                                        # num
                count = m.group(1)
    if code == 0 and count in ("—", "0"):
        count = "0"
    note = "—"
    if gate.note_re:
        m = gate.note_re.search(out)
        if m:
            if gate.key == "omml":                       # warnings 是字符串数组，用条数
                body_txt = m.group(1).strip()
                n = 0 if not body_txt else len(re.findall(r'"[^"]+"', body_txt))
                note = "warnings %d" % n
            else:
                note = " ".join(m.groups()) if len(m.groups()) > 1 else m.group(1)
    else:
        tail = [x.strip() for x in out.strip().split("\n") if x.strip()]
        if tail:
            note = tail[-1]
    note = re.sub(r"\s+", " ", note).strip()
    return count, (note[:56] + "…" if len(note) > 57 else note)


def _pad(s, width):
    """按**显示宽度**补齐（中文等宽字符按 2 计），保证中文表格不歪。"""
    w = sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)
    return s + " " * max(0, width - w)


def _discover_docx(case: Path):
    """案件目录下按 `<案件号>-全文*稿-*.docx` 找交付件；排除审核稿。"""
    cands = [p for p in case.glob("*-全文*稿-*.docx")
             if not p.name.startswith("审核")]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def main():
    ap = argparse.ArgumentParser(description="机械闸门总跑（一次跑完，出一张表）")
    ap.add_argument("case", help="案件文件夹")
    ap.add_argument("--invention-name", default=None,
                    help="王工给定发明名称全称（传给需校验题名的闸门）")
    ap.add_argument("--docx", default=None, help="交付 DOCX（默认自动发现）")
    ap.add_argument("--phase", choices=["auto", "claims", "full"], default="auto")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    case = Path(a.case).resolve()
    docs = case / "docs"
    ctx = {
        "case": str(case),
        "claims": str(docs / "权要稿.md") if (docs / "权要稿.md").is_file() else None,
        "fulltext": str(docs / "全文稿.md") if (docs / "全文稿.md").is_file() else None,
        "invention_name": a.invention_name,
        "docx": None,
    }
    if a.docx:
        ctx["docx"] = str(Path(a.docx).resolve())
    else:
        d = _discover_docx(case)
        ctx["docx"] = str(d) if d else None

    phase = a.phase
    if phase == "auto":
        phase = "full" if ctx["fulltext"] else "claims"

    rows = []
    for g in _mk_gates():
        if phase == "claims" and g.phase != "claims":
            continue          # 权要阶段：只跑权要闸门
        # phase == "full"：claims 与 full 的闸门全跑（权要是全文的前置，不能跳过）
        missing = [k for k in g.needs if not ctx.get(k)]
        if missing:
            reason = "缺输入：" + "、".join(missing)
            rows.append({"key": g.key, "name": g.name, "status": "未执行",
                         "exit": None, "count": "—", "note": reason})
            continue
        script = {
            "hard_claims": "check_hard_rules.py", "hard_full": "check_hard_rules.py",
            "cross": "check_cross_block.py", "align": "verify_claims_alignment.py",
            "fingerprint": "fingerprint_claims.py", "preset": "check_preset_params.py",
            "timestamp": "timestamp_guard.py", "pages": "check_page_count.py",
            "skeleton": "verify_docx_skeleton.py", "injection": "verify_docx_injection.py",
            "omml": "omml_formulas.py",
        }[g.key]
        code, out = _run(script, g.argv(ctx))
        count, note = _extract(g, out, code)
        rows.append({"key": g.key, "name": g.name,
                     "status": "PASS" if code == 0 else "FAIL",
                     "exit": code, "count": count, "note": note})

    failed = [r for r in rows if r["status"] == "FAIL"]
    skipped = [r for r in rows if r["status"] == "未执行"]
    n_pass = len([r for r in rows if r["status"] == "PASS"])

    if a.json:
        print(json.dumps({"case": str(case), "phase": phase, "rows": rows,
                          "pass": n_pass, "fail": len(failed),
                          "skipped": len(skipped)}, ensure_ascii=False, indent=2))
        return 1 if failed else (2 if skipped else 0)

    print("机械闸门总跑  case=%s  phase=%s" % (case.name, phase))
    print(_pad("闸门", 44) + _pad("结论", 8) + _pad("退出码", 8) + _pad("计数", 6) + "备注")
    print("-" * 110)
    for r in rows:
        print(_pad(r["name"], 44) + _pad(r["status"], 8) + _pad(
            "—" if r["exit"] is None else str(r["exit"]), 8) + _pad(
            str(r["count"]), 6) + r["note"])
    print("-" * 110)
    print("%d 个闸门 · %d 通过 · %d FAIL · %d 未执行"
          % (len(rows), n_pass, len(failed), len(skipped)))

    if failed:
        print()
        print("★ 逐条处置（必做，缺一视为未检查）：上面 FAIL 的每一路都要给结论——")
        print("  ①「已改」：写出改后原文；或")
        print("  ②「判为误报」：贴出稿中对应原文与位置，按该脚本 docstring 的校准要点记账放行。")
        print("  处置结论须逐条进完工报告校验清单——**不得只写『已跑』两个字**。")
    if skipped:
        print()
        print("★ 未执行项不是豁免：本表如实标出缺失的输入（如交付 DOCX 尚未生成）。")
        print("  交付前必须补跑，未执行项不得在完工报告里按 PASS 记。")
    return 1 if failed else (2 if skipped else 0)


if __name__ == "__main__":
    sys.exit(main())

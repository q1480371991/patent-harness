#!/usr/bin/env python3
"""
patent skill 接入前环境自检器 (跨平台: Windows / macOS / Linux).

设计约束: **只用 Python 标准库**——本脚本的职责就是检查依赖, 自己绝不能引入
第三方依赖, 否则"检查依赖的工具自己缺依赖"会死锁.

用途: 别人把 patent skill 装到自己机器上时, AI 读到 skill 后先跑一次本脚本,
按报告补齐缺失依赖, 做到开箱即用, 而不是运行到一半才报 ImportError / not found.

依赖分类 (决定 AI 的补齐力度):
- pip   : pip 可装的第三方库 (python-docx). AI 可用 --fix 直接安装, 不逗问.
- system: 系统级工具 (python3 本身版本 / pandoc). AI 不擅自静默改环境,
          只给出当前平台的安装命令引导用户.
- plugin: Claude Code 插件能力 (document-skills:docx). 文件系统检测不到,
          由 AI 在会话中自行确认能否调用, 本脚本仅提示.

用法:
    python3 scripts/check_env.py                    # 只检测, 人类可读报告到 stderr
    python3 scripts/check_env.py --json             # 追加 JSON 报告到 stdout (给 AI 消费)
    python3 scripts/check_env.py --fix              # 对 pip 类缺失项执行 pip install
    python3 scripts/check_env.py --host codex       # Codex 宿主: 跳过 document-skills:docx 插件检测

`--host`（单内核多宿主）:
- `claude`（默认）: 检测 document-skills:docx 插件（DOCX 执行层走该插件）。
- `codex`: 不检测该插件（Codex 无此插件, DOCX 由 python-docx 直接提供, 已被 pip 必需项覆盖）。

Exit code: 0 = 必需项全部就绪 (可选项缺失不影响); 非 0 = 缺必需项数量.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys

MIN_PYTHON = (3, 9)

OS_NAME = platform.system()  # 'Windows' / 'Darwin' / 'Linux'


def _install_hint(system_cmds: dict) -> str:
    """按当前平台取安装命令 (键: Windows/Darwin/Linux/other)."""
    return system_cmds.get(OS_NAME, system_cmds.get("other", "见依赖官网"))


def check_python_version() -> dict:
    ok = sys.version_info >= MIN_PYTHON
    cur = ".".join(map(str, sys.version_info[:3]))
    need = ".".join(map(str, MIN_PYTHON))
    return {
        "name": "python",
        "category": "system",
        "required": True,
        "ok": ok,
        "detail": f"当前 {cur}, 需 >= {need}",
        "auto_installable": False,
        "install_hint": _install_hint({
            "Darwin": "brew install python@3.12  (或 https://www.python.org/downloads/)",
            "Windows": "winget install Python.Python.3.12  (或 https://www.python.org/downloads/)",
            "Linux": "用发行版包管理器升级 python3 (如 apt install python3)",
            "other": "https://www.python.org/downloads/",
        }),
    }


def check_python_docx() -> dict:
    ok = importlib.util.find_spec("docx") is not None
    return {
        "name": "python-docx",
        "category": "pip",
        "required": True,
        "ok": ok,
        "detail": "import docx" + (" 成功" if ok else " 失败 (未安装)"),
        "auto_installable": True,
        "pip_name": "python-docx",
        "install_hint": f"{sys.executable} -m pip install python-docx",
    }


def check_pillow() -> dict:
    ok = importlib.util.find_spec("PIL") is not None
    return {
        "name": "Pillow",
        "category": "pip",
        "required": True,
        "ok": ok,
        "detail": "import PIL" + (" 成功" if ok else " 失败 (未安装)") + " (附图渲染 render_patent_figure.py 用)",
        "auto_installable": True,
        "pip_name": "pillow",
        "install_hint": f"{sys.executable} -m pip install pillow",
    }


def check_pandoc() -> dict:
    path = shutil.which("pandoc")
    if not path:
        # 与 scripts/omml_formulas.py 的探测清单保持一致
        home = Path.home()
        for cand in (
            home / ".local/bin/pandoc",
            home / "miniconda3/bin/pandoc",
            Path("/opt/homebrew/bin/pandoc"),
            Path("/usr/local/bin/pandoc"),
            Path("C:/Program Files/Pandoc/pandoc.exe"),
        ):
            if cand.exists():
                path = str(cand)
                break
    ok = path is not None
    return {
        "name": "pandoc",
        "category": "system",
        "required": False,  # 推荐: omml_formulas.py 用它把公式转原生 OMML; 缺失时公式回退纯 LaTeX 文本
        "ok": ok,
        "detail": (
            f"已找到 {path}"
            if ok
            else "未找到 (推荐安装: 公式原生 OMML 转换需要; 缺失时公式回退纯 LaTeX 文本写入)"
        ),
        "auto_installable": False,
        "install_hint": _install_hint({
            "Darwin": "brew install pandoc",
            "Windows": "winget install --id JohnMacFarlane.Pandoc  (或 choco install pandoc)",
            "Linux": "apt install pandoc  (或对应发行版包管理器)",
            "other": "https://pandoc.org/installing.html",
        }),
    }


def check_docx_plugin() -> dict:
    """
    document-skills:docx 是 Claude Code 插件能力, 文件系统检测不到.
    本项永远返回 ok=None (未知), 由 AI 在会话中自行确认能否调用该 skill.
    """
    return {
        "name": "document-skills:docx (Claude Code 插件)",
        "category": "plugin",
        "required": True,
        "ok": None,
        "detail": "本脚本无法检测插件; 由 AI 在会话中确认能否调用 document-skills:docx",
        "auto_installable": False,
        "install_hint": "在 Claude Code 中确认已安装 document-skills 插件; 若 AI 无法调用, 重启 Claude Code 或重新加载插件",
    }


def run_checks(host: str = "claude") -> list[dict]:
    checks = [
        check_python_version(),
        check_python_docx(),
        check_pillow(),
        check_pandoc(),
    ]
    # document-skills:docx 仅 Claude 宿主适用; Codex 用 python-docx 直连, 不检测插件.
    if host == "claude":
        checks.append(check_docx_plugin())
    return checks


def do_fix(results: list[dict]) -> list[dict]:
    """对 pip 类且缺失且可自动安装的项执行 pip install."""
    fixes = []
    for r in results:
        if r["category"] == "pip" and r["ok"] is False and r.get("auto_installable"):
            cmd = [sys.executable, "-m", "pip", "install", r["pip_name"]]
            print(f"[check_env] 自动安装 {r['name']}: {' '.join(cmd)}", file=sys.stderr)
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            ok = proc.returncode == 0
            fixes.append({"name": r["name"], "installed": ok, "log": proc.stdout[-500:]})
            if not ok:
                print(f"[check_env] 安装失败: {r['name']}\n{proc.stdout[-500:]}", file=sys.stderr)
    return fixes


def summarize(results: list[dict]) -> tuple[int, int]:
    """返回 (缺失的必需项数, 缺失的可选项数). ok=None 的插件项不计入缺失."""
    missing_required = sum(1 for r in results if r["required"] and r["ok"] is False)
    missing_optional = sum(1 for r in results if not r["required"] and r["ok"] is False)
    return missing_required, missing_optional


def format_report(results: list[dict], missing_required: int, missing_optional: int) -> str:
    lines = [f"[check_env] 平台={OS_NAME}  python={'.'.join(map(str, sys.version_info[:3]))}"]
    for r in results:
        icon = {True: "✓", False: "✗", None: "?"}[r["ok"]]
        tag = "必需" if r["required"] else "可选"
        lines.append(f"  {icon} [{tag}/{r['category']}] {r['name']} — {r['detail']}")
        if r["ok"] is False or r["ok"] is None:
            lines.append(f"      安装: {r['install_hint']}")
    if missing_required == 0:
        lines.append("[check_env] 必需项就绪" + (f"; {missing_optional} 个可选项缺失 (不阻断)" if missing_optional else ""))
    else:
        lines.append(f"[check_env] 缺 {missing_required} 个必需项, 请按上面安装提示补齐后重跑")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="patent skill 环境自检 (仅标准库).")
    parser.add_argument("--json", action="store_true", help="stdout 输出 JSON 报告 (给 AI 消费)")
    parser.add_argument("--fix", action="store_true", help="对 pip 类缺失项执行 pip install 后重检")
    parser.add_argument(
        "--host", choices=["claude", "codex"], default="claude",
        help="宿主: claude 检测 docx 插件; codex 跳过插件 (用 python-docx 直连)",
    )
    args = parser.parse_args()

    results = run_checks(args.host)
    fixes = []
    if args.fix:
        fixes = do_fix(results)
        if fixes:  # 装完重检, 反映最新状态
            results = run_checks(args.host)

    missing_required, missing_optional = summarize(results)

    if args.json:
        print(json.dumps({
            "platform": OS_NAME,
            "host": args.host,
            "python": ".".join(map(str, sys.version_info[:3])),
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "fixes": fixes,
            "checks": results,
        }, ensure_ascii=False, indent=2))
    else:
        print(format_report(results, missing_required, missing_optional), file=sys.stderr)

    return missing_required


if __name__ == "__main__":
    sys.exit(main())

"""批1 回归：check_page_count.py 五案实测（基准值即下方 EXPECT 表）。

定稿实测：X2607043 28页 / X2607040 33页 / X2607134 34页 / H2608040 31页 / X2608107 36页
我的稿破线：X2608107 我的2稿 46页（五案唯一异常值）、X2607134 我的2稿 49页
"""
import sys, os, glob, subprocess
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "..", "scripts", "check_page_count.py")
BASE = r"（本地案卷目录）"

EXPECT = {  # 五案定稿实测页数（本表即基准）
    "定稿-审核v3-梁旭林-全文三稿-X2607043": 28,
    "定稿-审核v2-梁旭林-全文二稿-X2607040": 33,
    "定稿-审核v2-X2607134-全文2稿": 34,
    "定稿-审核v2-H2608040-全文2稿": 31,
    "定稿-审核v2-X2608107-全文2稿": 36,
    "X2608107-全文2稿-梁旭林": 46,
    "X2607134-全文2稿-梁旭林": 49,
}

files = sorted(set(glob.glob(os.path.join(BASE, "**", "*.docx"), recursive=True)))
rows = []
for f in files:
    name = os.path.basename(f)
    if ".bak" in f or "交底书" in name or "权要" in name or "参考" in name or "案例" in name:
        continue
    key = next((k for k in EXPECT if name.startswith(k)), None)
    r = subprocess.run([sys.executable, SCRIPT, f], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    first = (r.stderr or "").splitlines()[0] if r.stderr else "(无输出)"
    verdict = "PASS" if r.returncode == 0 else ("FAIL" if r.returncode == 1 else "STALE")
    pages = ""
    for tok in first.split():
        if tok.isdigit():
            pages = tok
            break
    rows.append((key, verdict, pages, EXPECT.get(key), name[:58]))

print(f"{'判定':<6}{'实测页':<7}{'外置表':<7}文件")
print("-" * 88)
for key, verdict, pages, exp, name in rows:
    mark = ""
    if exp is not None:
        mark = " ✓一致" if str(exp) == pages else f" ✗差异(表记{exp})"
    print(f"{verdict:<6}{pages:<7}{str(exp or '-'):<7}{name}{mark}")

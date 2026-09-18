"""批1 回归：五案权要稿 预设对象 distinct 实测（基准值即下方 EXPECT）。"""
import sys, glob, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from check_hard_rules import _PRESET_OBJ_RE, _PRESET_TAIL_VERB_RE

BASE = r"（本地案卷目录）"
EXPECT = {"X2607040": 0, "X2607043": 4, "X2607134": 6, "H2608040": 6, "X2608107": 16}

for case in ["X2607040", "X2607043", "X2607134", "H2608040", "X2608107", "H2608165"]:
    hits = glob.glob(os.path.join(BASE, case + "*", "docs", "权要稿.md"))
    if not hits:
        print(f"=== {case}: 无 docs/权要稿.md")
        continue
    text = open(hits[0], encoding="utf-8").read()
    sec = text.split("## 技术领域")[0]
    objs = {}
    for m in _PRESET_OBJ_RE.finditer(sec):
        name = "预设" + _PRESET_TAIL_VERB_RE.sub("", m.group(1))
        objs[name] = objs.get(name, 0) + 1
    exp = EXPECT.get(case)
    tag = "" if exp is None else f"  (基准: {exp})"
    print(f"=== {case}  distinct={len(objs)}  原始「预设」出现={sec.count('预设')}{tag}")
    for k, v in sorted(objs.items()):
        print(f"      {k} x{v}")

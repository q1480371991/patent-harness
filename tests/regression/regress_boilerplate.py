"""回归：规则 47/48 法律套话逐字断言 + 有益效果句式（双向验证，改脚本前后必跑）。

五案实测基准（2026-09-01，直读 docs/全文稿.md）：
  开篇段：五案全 130 字逐字同（"作出/做出"两种）；H2608165 一稿 70 字 = 唯一违规
  有益效果各条首句：五案全以"本发明"或"通过"起句；H2608165 一稿以特征名起句 = 唯一违规

⚠️ 本脚本是"能让人推翻结论的材料"（外置根因四补一维）：
   规则 47/48 是**收紧**方向（新增 FAIL 可能性），故改动前后都要跑，
   五个已定稿件必须保持 0 违规 —— 任一案新报 FAIL 即为误报，须先校准再提交。
"""
import sys, os, subprocess, json
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "..", "scripts", "check_hard_rules.py")
BASE = os.environ.get("PATENT_CASES_DIR", "")
if not BASE:
    print("未设置 PATENT_CASES_DIR 环境变量，跳过——本回归装置需指向本地案卷目录")
    sys.exit(0)
NAME = "一种基于多传感器融合多向穿梭车高精度定位方法及系统"

CASES = [
    ("X2608107", r"X2608107一种废旧聚酯表面解聚的催化改性处理方法及系统", 0),
    ("X2607134", r"X2607134基于机器视觉的灌区渠道渗漏识别方法及系统", 0),
    ("X2607040", r"X2607040一种树脂填充饱和度仿真方法及系统", 0),
    ("X2607043", r"X2607043面向企业短信触达场景的多通道通信调度方法及系统", 0),
    ("H2608040", r"H2608040基于数字孪生的城市环卫绿化可视化监控方法及系统", 0),
    ("H2608165", r"H2608165一种基于多传感器融合多向穿梭车高精度定位方法及系统", None),
]
TARGET = ("L8-1", "L6-1", "G8-0b")
KEYS = ("开篇段", "方法-系统对应段", "第二实施例系统段", "有益效果分项未按模板句式",
        "A 类槽位")
fails = 0
for label, rel, expect in CASES:
    md = os.path.join(BASE, rel, "docs", "全文稿.md")
    claims = os.path.join(BASE, rel, "docs", "权要稿.md")
    if not os.path.isfile(md):
        print(f"=== {label}: 文件不存在，跳过")
        continue
    cmd = [sys.executable, SCRIPT, "--md", md, "--stage", "full-draft", "--json"]
    if os.path.isfile(claims):
        cmd += ["--claims-md", claims]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        d = json.loads(r.stdout)
    except Exception as e:
        print(f"=== {label}: JSON 解析失败 {e}")
        fails += 1
        continue
    hits = [v for v in d.get("violations", [])
            if any(k in (v.get("message", "") + v.get("location", "")) for k in KEYS)]
    got = len(hits)
    print(f"=== {label}  规则47/48 命中={got}")
    for h in hits:
        print(f"      · {h.get('location')} | {h.get('evidence', '')[:60]}")
    if expect is not None:
        ok = got == expect
        print(f"      基准 {expect} → {'✓ 一致' if ok else '✗ 偏离，属误报须校准'}")
        if not ok:
            fails += 1
print()
print("回归结论:", "PASS（五个定稿件零误报）" if fails == 0 else f"FAIL（{fails} 项偏离）")
sys.exit(1 if fails else 0)

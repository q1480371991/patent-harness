"""批1 回归：check_preset_params.py 双向验证（外置 8.1 基准，改脚本前后必跑）。

外置 8.1 双向验证记录（H2608040 实测，零漏报零误报）：
  我的全文2稿  → FAIL 3：预设工作距离 / 预设单幅采集分辨率 / 预设前景差值
                        —— 正是王工定稿轮亲手补的那几处
  王工定稿     → FAIL 1：预设颜色映射表 —— 正是复盘登记的遗留项

X2608107 校准要点 5（首锚点误报，改后应消除）：
  改前 我的2稿/王工定稿 均 FAIL 2（预设酸碱度波动基准 / 预设下降幅度阈值）
  改后 应 PASS —— 两条都是误报，真缺口 0

⚠️ 本脚本是"能让人推翻结论的材料"（外置根因四补一维）；改 check_preset_params.py
   前后都要跑，FAIL 集合变化必须逐条给出理由。
"""
import sys, os, subprocess, json
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "..", "scripts", "check_preset_params.py")
BASE = r"（本地案卷目录）"

CASES = [
    ("H2608040 我的2稿", r"H2608040基于数字孪生的城市环卫绿化可视化监控方法及系统\docs\全文稿.md",
     ["预设工作距离", "预设单幅采集分辨率", "预设前景差值"]),
    ("X2608107 我的2稿", r"X2608107一种废旧聚酯表面解聚的催化改性处理方法及系统\docs\全文稿.md",
     []),
    ("X2608107 王工定稿", r"X2608107一种废旧聚酯表面解聚的催化改性处理方法及系统\docs\_rev3\v2_accept_as.md",
     []),
    ("X2607134 我的2稿", r"X2607134基于机器视觉的灌区渠道渗漏识别方法及系统\docs\全文稿.md",
     None),   # 无基准记录，仅打印
]

for label, rel, expect in CASES:
    path = os.path.join(BASE, rel)
    if not os.path.isfile(path):
        print(f"=== {label}: 文件不存在，跳过")
        continue
    r = subprocess.run([sys.executable, SCRIPT, path, "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        d = json.loads(r.stdout)
    except Exception as e:
        print(f"=== {label}: JSON 解析失败 {e}")
        continue
    fails = [x["name"] for x in d["rows"] if not x["ok"]]
    supp = [x["name"] for x in d["rows"] if x.get("supplementary")]
    print(f"=== {label}  exit={r.returncode}  识别={d['checked']}  FAIL={len(fails)}")
    print(f"      FAIL: {fails}")
    print(f"      ※补充识别: {supp}")
    if expect is not None:
        ok = sorted(fails) == sorted(expect)
        print(f"      基准 {expect} → {'✓ 一致' if ok else '✗ 偏离，须逐条给理由'}")

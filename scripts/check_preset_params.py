#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_preset_params.py —— 说明书预设量点数闸门（外置经验 2.6 八槽的机械实现）

用途
----
H2608040 的最大执行缺口：说明书 17 个预设量里 6 个没给确定方式、1 个缺取值操作
含义，王工在全文审核v1 与定稿轮两次亲手补。根因不是不懂规则（外置经验 2.6 八槽、
`implementation.md` L8-1「阈值必须说明确定方式」都写清了），而是「逐槽点数」没有
产物，退化成凭印象边写边扫。

本脚本把它变成能 grep、能数数的机械动作：
    列清单 -> 逐个查槽 -> 任一必填槽为空即 FAIL

⚠️ **建表 ≠ 过闸门**（外置根因四补一维）：X2608107 建了五案最完整的预设量台账、
却全程没跑本脚本，两个产物都失效。交付前必须**真跑**并把 exit code 与 FAIL 明细
贴进销项表；跑出 FAIL 先按下方校准要点判是否误报，再决定改稿。

分工（实测 + 规则双重确认）
--------------------------
* 权利要求书：只标名，不给依据。
  `claims-requirements.md` L1-1「用『预设xx阈值』标明来源，其确定依据下沉到说明书」
  权要禁写具体技术数值 + **权要内预设对象 distinct ≤5**（外置 2.4a）均已由
  `check_hard_rules.py` 规则 8b / 规则 43 硬闸门覆盖，本脚本不重复。
* 说明书：给确定方式 + 示例取值 + 取值的操作含义。
  => 本脚本只扫说明书区，不扫权要区。

槽位（压到 5 个可机械判定的，对应外置经验 2.6 八槽）
--------------------------------------------------
  槽1 依据    〔预设量〕根据/通过〔依据对象〕确定/得到      <- 必填(FAIL)
  槽2 操作    取/选择/排序/统计/计算…作为〔预设量〕        <- 必填(FAIL)
  槽3 定义    统计量的定义句（用到四分位数/百分位时才必填）  <- 条件必填(FAIL)
  槽4 取值    示例性地，〔预设量〕取〔值〕                <- 条件必填，**按类别分级**（见下）
  槽5 可调    〔工况〕变化时，重新执行…                  <- 建议项(WARN，不阻断)

槽4 **按 X14 类别分级**（X2608107 校准要点 6，2026-08-27）
--------------------------------------------------------
对**王工定稿件**补跑得 FAIL 4，其中 `预设电导率波动基准`／`预设剂量调整对照关系`
两条恰恰是**王工自己按 X14 删掉示例取值造成的** —— 这不是遗留项，是脚本与审核人
口径打架。故槽4 按 X14 三层类别分级：

  · 模型超参 / 量化尺度类（核参数、惩罚系数、活化能、终止条件、子块尺寸、邻域
    尺寸、采样周期、标注分档）—— **仍为 FAIL**，不给值本领域技术人员无法实施，
    王工一处未删。
  · 阈值 / 对照关系的取值表、公式符号示例值 —— **降为 WARN**，确定方式已能复现
    取值，超线时王工会先删这一类。

★ 不要为了让脚本变绿去补王工会删的示例值。

槽5 的判据（校准要点 7，随 2.9 反转重定）
---------------------------------------
原注释写"槽5 定为 WARN 是因为可调整语义已由 2.9 末尾兜底句整体覆盖"——
**2026-08-27 王工把兜底句定性为「只要原本的阈值讲得清楚就可写可不写、一般都不用
写，属于冗余」，这个理由失效了。**

现行判据：**槽5 仍为 WARN，但理由改为「属质量项、非公开充分必需」**（H2608040
定稿实测：王工亲手补的 5 个预设量都没写"变化时重新执行"，不是硬要求）。
⚠️ 但写稿时应把槽5 **当默认动作写上** —— 兜底句既已定性为不写，每个参数自己的
解释段就是"可调整"语义的唯一落点。X2608107 定稿实测 3 个预设量缺槽5、兜底句又被
删，这三处的可调整语义在定稿里确实无处体现（该真空已报审核人，答复为：阈值讲清楚
即可，不必再单写"可调整"一层）。

模型/网络类（`预设xx网络`/`预设xx模型`）不走本脚本：它们按 A11 模型九项走，
已由 `check_hard_rules.py` 的四维度探测覆盖，本脚本自动跳过以免误报。
（⚠️ 与 `check_hard_rules.py` 规则 43 的边界：那条**数总量**时模型类照计入，
本脚本**查槽位**时模型类跳过 —— 两者不同维，不矛盾。）

用法
----
    python check_preset_params.py <全文稿.md>
    python check_preset_params.py <全文稿.md> --json
    python check_preset_params.py <全文稿.md> --window 500

退出码：0 = PASS，1 = FAIL（有必填槽为空），2 = 用法错误
"""

import argparse
import json
import re
import sys

# ---- 说明书区起点：从这些标题之后开始算，避开权利要求书区 ----
SPEC_START = re.compile(r'^\s*(技术领域|说明书)\s*$', re.M)
# 权利要求书区特征（用于兜底切分）
CLAIMS_LINE = re.compile(r'^\s*\d+\s*[.．]\s*(一种|根据权利要求)')

# ---- 预设量识别：预设 + 2~8 汉字，收尾于常见量词 ----
# 量词必须"长的排前面"：正则的 (?:A|B) 是最左优先，若 `元素` 排在 `元素尺寸` 之前，
# `预设结构元素尺寸` 会被截成 `预设结构元素` 而与定义句失配（H2608040 实测误报）。
# 同理 `分辨率` 要在 `率` 之前、`映射表` 要在 `表` 之前。
#
# ★★ 前缀 `{2,8}?`（惰性、至少 2 字）是**有意的**，改动前先读下面三条实测（2026-08-28）：
#
# ① **不能放宽到 `{0,8}?`** —— 会把长名字截短成裸量词，进而误报。实测 H2608040:
#      `预设数量阈值`（八槽写全）→ 截成 `预设数量`，槽1 正则要求名字后紧跟"根据"，
#      实际后面是"阈值根据"→ 判缺槽1 = **误报**
#      `预设轮数与最大训练轮数`（写全）→ 截成 `预设轮数`，后面是"与最大…" → **误报**
#    FAIL 从基准的 3 涨到 5，两条全是假的 —— 破坏了 8.1 的"零漏报零误报"基准。
# ② **不能改贪婪 `{0,8}`**（与 `check_hard_rules.py` 规则 43 的修法相反）—— 说明书
#    句子长、`与`/`取`/`、` 连接词多，贪婪会跨语法成分切出假名：实测切出
#    `预设工作距离与预设单幅采集分辨率`（跨"与"合并两个对象，反而**丢掉**这两个真
#    缺口）、`预设酸碱度波动基准取窗口`（吞掉动词"取"）。
#    ⚠️ 权要侧规则 43 用贪婪是安全的，因为权要句式规整、`预设××` 后通常紧跟动词；
#    **两侧正则策略不同源，勿互相搬**。
# ③ **不能用"名字内禁含 的/与/取/统计…"过滤** —— 那些字也出现在合法名字里：实测
#    `预设统计网格尺寸`（含"统计"）、`预设指数阈值`（含"指"）会被整条挡掉。
#
# 裸量词盲区（`预设采样周期`／`预设剪切速率`／`预设基准碱浓度` 这类 0 字前缀的名字）
# 由下方 `_BARE_PRESET_RE` 补充识别路径覆盖，不动本正则。
PRESET = re.compile(
    r'预设([一-鿿]{2,8}?'
    r'(?:元素尺寸|单幅采集分辨率|分辨率|映射表|金字塔层数|网格尺寸|显示尺寸'
    r'|阈值区间|对照关系|换算关系|映射关系|基准碱浓度|剪切速率|采样周期|波动基准'
    r'|阈值|尺寸|数量|距离|轮数|层数|窗口|差值|网络|模型|系数|比例|宽度|间距|范围|顺序|下限|上限))'
)

# ---- 裸量词补充识别（0 字前缀，仅用于主正则未覆盖的 `预设` 出现处）----
# 主正则前缀 ≥2 字，故 `预设采样周期`／`预设剪切速率`／`预设基准碱浓度`／`预设阈值`
# 这类量词自身即全名的对象一律漏检（X2608107 定稿实测漏 3 个）。本正则只在主正则
# **没有覆盖到**的 `预设` 位置上补跑，因此不会把长名字截短（长名字已被主正则吃掉）。
# 补充识别出的对象走同一套槽位判定，但结果标 `supplementary=True`：
#   —— 缺槽一律计 **WARN 而非 FAIL**。理由：本路径未经 8.1 双向验证（H2608040
#      零漏报零误报基准是在主正则下建立的），把未验证路径的结论升到 FAIL 会让闸门
#      在下一案以"假红灯"形式失去可信度，比漏检更难纠。**待累积 2 案实测无误报后
#      再考虑升为 FAIL**，届时须重跑 8.1 双向验证并回写基准。
_BARE_PRESET_RE = re.compile(
    r'预设(?:的)?((?:元素尺寸|单幅采集分辨率|分辨率|映射表|金字塔层数|网格尺寸|显示尺寸'
    r'|阈值区间|对照关系|换算关系|映射关系|基准碱浓度|剪切速率|采样周期|波动基准'
    r'|阈值|尺寸|数量|距离|轮数|层数|窗口|差值|网络|模型|系数|比例|宽度|间距|范围|顺序|下限|上限))')

# ---- 动名连写切分假阳（X2608107 实测）----
# 有益效果段「按预设深度换算关系映射为初始解聚深度」中，惰性量词把紧随的动词
# 一并吃进名字，切出并不存在的预设量（如「预设深度换算关系映射」），随后在其后
# 窗口内找不到定义句而误报缺槽1/槽2。此处按"名字尾部紧跟的动词"剥离，
# 不用右边界断言 (?![一-鿿])——那会连合法的「预设波动阈值的差值」一并挡掉，
# 反而把识别总数从 14 打到 3（实测）。
_TRAILING_VERB = re.compile(
    r'(映射|匹配|比对|统计|换算|求和|叠加|修正|判定|计算|采集|归一化)$')


# ---- 2.9 末尾参数兜底句：其中的"预设xx"是概括称谓、非具体预设对象，整段跳过 ----
# （X2608107 实测：兜底句"上述各预设阈值、预设采样周期、预设权重系数…均为本发明的一种
#   具体实施方式"里的 `预设权重系数` 被当成独立预设对象，报 FAIL 缺槽1/槽2；它本就无需
#   单独给确定方式——真实对象是 `预设波动权重`，已在 S13 给全八槽。）
# ⚠️ 剔除逻辑本身保留（若真写了兜底句，其中的"预设xx"仍是概括称谓、不该当独立对象）；
#   2.9 已于 2026-08-27 反转为「一般不写」，故本正则多数稿件不会命中，属兜底防护。
FALLBACK_SENT = re.compile('[^' + chr(92) + 'n]*均为本发明的一种具体实施方式[^' + chr(92) + 'n]*')

# ---- 槽4 分级词表（X14 三层类别，校准要点 6）----
# 模型超参与量化尺度类：不给值则本领域技术人员无法实施 → 缺槽4 仍 FAIL
_SLOT4_HARD_KIND = re.compile(
    r'核参数|惩罚系数|活化能|终止条件|收敛条件|迭代次数|学习率|正则'
    r'|子块尺寸|邻域尺寸|窗口尺寸|网格尺寸|元素尺寸|采样周期|采样窗口|采样频率'
    r'|分辨率|标注分档|层数|轮数|步长|工作距离|显示尺寸')
# 阈值/对照关系取值表、公式符号示例值：确定方式已能复现取值，超线时王工先删这类
# → 缺槽4 降为 WARN（不为让脚本变绿去补王工会删的示例值）
_SLOT4_SOFT_KIND = re.compile(r'对照关系|换算关系|映射关系|映射表|阈值|基准|区间|权重')

# ---- 模型/网络类不按阈值槽位判（无"取某个数值"语义）----
# 它们走 A11 模型九项，由 check_hard_rules.py 的四维度探测覆盖，本脚本跳过。
MODEL_LIKE = re.compile(r'(?:网络|模型)$')

# ---- 定义句锚点 ----
# 关键：槽1 必须由「〔预设量〕紧跟 根据/通过/依据/按 …确定/得到」构成，
# 不能在窗口内自由匹配——否则会命中相邻段落里别的句子而误放行。
# H2608040 实测教训：`按预设工作距离与预设单幅采集分辨率拍摄` 是**使用处**不是定义处，
# 自由匹配会捞到 300 字外「按对应加权系数求和，得到」而误判为"有依据"。
def _slot1_re(name):
    return re.compile(
        re.escape(name) + r'(?:根据|通过|依据|按)[^。；]{2,160}?(?:确定|得到|给出)'
        # 「其确定依据是/为…」式写法（X2607134 实测：`所述预设判定阈值用于…，其确定依据为
        # 对已标注渗漏样本与正常样本的特征融合值分布分析…`）——动词在名字之后隔了一段，
        # 上一分支的 `name+根据/通过/依据/按` 紧邻式匹配不到。
        r'|' + re.escape(name) + r'[^。；]{0,60}?(?:确定依据是|确定依据为|确定方式为|的确定依据|确定方法为)')


# 定义处锚点：〔预设量〕后紧跟这些词，才算在"解释它"而非"使用它"
# ★ 校准要点 8（2026-08-28 新增）：**必须含 `按`**，与 `_slot1_re` 的动词表对齐。
#   原表缺 `按`，导致 `所述预设对比度方差阈值按实验统计方式确定，采集…不少于100幅…`
#   这类**定义句写得很全**的对象因找不到锚点而 `defined=False` → 槽1/槽2 直接判缺 =
#   误报（X2607134 实测 4 条）。两处动词表原本就不一致，属实现漏洞。
#   ⚠️ 加锚点是**放宽**方向（锚点越多、窗口越多、越容易 PASS），故加之前必须跑
#   `tests/regression/regress_preset_params.py` 确认 H2608040 基准 FAIL 3 不变 ——
#   已确认：五案中仅 X2607134 由 FAIL 11 降为 7，其余四案一字未变。
#   （注：`按实验统计方式确定` 这层归类标签按 X7 口径**不该写进说明书**，X2607134 那 6 处
#     正是王工定稿时 WPS 查找替换删掉的。本锚点认它只为兼容旧稿，不代表推荐该写法。）
DEFINE_ANCHOR = r'(?:根据|通过|依据|按|为|指|取)'

# ---- 槽位特征串（槽2-5 在定义块内匹配即可）----
SLOT2 = re.compile(r'(?:取|选择|排序|统计|计算|换算|测量|提取|使)')     # 操作动作
SLOT3 = re.compile(r'(?:四分位数|百分位|中位数)[^。]{0,40}?(?:为|指|是)')  # 统计量定义
SLOT4 = re.compile(r'(?:示例性地|本实施例中)[^。]{0,60}?取')            # 示例取值
SLOT5 = re.compile(r'(?:变化时|不同时|变更时)[^。]{0,80}?(?:重新|按)')   # 可调整
# 触发槽3必填：解释里用了分位类统计量
NEEDS_SLOT3 = re.compile(r'(?:四分位数|百分位|中位数)')
# 触发槽4必填：该预设量在文中出现过具体数值取值
HAS_VALUE = re.compile(r'取\s*[\d０-９]')


def split_spec(text):
    """切出说明书区正文。优先按'技术领域'切；否则按最后一条权利要求行之后切。"""
    m = SPEC_START.search(text)
    if m:
        return text[m.start():], m.start()
    last = None
    for mm in CLAIMS_LINE.finditer(text):
        last = mm
    if last:
        nl = text.find('\n', last.end())
        pos = nl if nl > 0 else last.end()
        return text[pos:], pos
    return text, 0


def audit(text, window=400):
    spec, _ = split_spec(text)
    # 2.9 兜底句整段剔除：其中的"预设xx"是概括称谓，不是需要单独给确定方式的对象
    spec = FALLBACK_SENT.sub('', spec)

    # 建清单：去重 + 记录首次出现位置
    order, first = [], {}
    covered = []            # 主正则已覆盖的字符区间, 供裸量词补充路径排除
    supplementary = set()   # 由补充路径识别出的对象名 (缺槽只计 WARN)
    for m in PRESET.finditer(spec):
        name = '预设' + m.group(1)
        # 动名连写切分假阳（X2608107 实测）："按预设深度换算关系映射为…"中惰性量词
        # 把动词"映射"并入名字，切出不存在的新对象；剥掉尾部动词恢复真实名字。
        if _TRAILING_VERB.search(name):
            name = _TRAILING_VERB.sub('', name)
        covered.append((m.start(), m.end()))
        if name not in first:
            first[name] = m.start()
            order.append(name)

    # 裸量词补充路径：只在主正则未覆盖的 `预设` 位置上补跑（不会截短长名字）
    for m in _BARE_PRESET_RE.finditer(spec):
        if any(s <= m.start() < e for s, e in covered):
            continue
        name = '预设' + m.group(1)
        if _TRAILING_VERB.search(name):
            name = _TRAILING_VERB.sub('', name)
        if name not in first:
            first[name] = m.start()
            order.append(name)
            supplementary.add(name)

    rows = []
    for name in order:
        # 模型/网络类跳过：走 A11 模型九项，不按阈值槽位判
        if MODEL_LIKE.search(name):
            rows.append({'name': name, 'pos': first[name], 'skipped': True,
                         'reason': '模型/网络类，按 A11 模型九项另查', 'missing': [],
                         'warn': [], 'ok': True})
            continue

        # 定义块起点：必须是"解释它"的位置（〔预设量〕紧跟 根据/通过/依据/为/指/取），
        # 不是"使用它"的位置（如 `按预设工作距离…拍摄`）。找不到定义处 = 槽1 直接缺。
        #
        # ★★ 校准要点 5（X2608107 实测，改脚本前先读）：**必须遍历全部锚点、任一命中
        # 即通过**，不能取首个。原实现 `for mm in ...: block_start = mm.start(); break`
        # 取首个锚点，本案 `预设酸碱度波动基准`／`预设下降幅度阈值` 各有两个锚点：首个
        # 落在**横向对比段**（2.6 W25「同链多阈值横向解释」要求写的并列句——"预设酸碱度
        # 波动基准**取**窗口内极差…；预设漂移阈值**取**…"，`取` 命中 DEFINE_ANCHOR），
        # 真正的定义句在 400 字窗口之外（pos 相差 376 与 10658），于是报"缺槽1+槽4"。
        # 两条都是误报，真缺口 0。
        # ⚠️ 这个误报形态会随 W25 执行到位而变多 —— 横向解释写得越全，并列句越多，
        # 首锚点越容易落错。
        anchors = [mm.start() for mm in re.finditer(re.escape(name) + DEFINE_ANCHOR, spec)]
        defined = bool(anchors)
        if not anchors:
            anchors = [first[name]]

        # 逐锚点各开一窗分别判槽，任一窗满足即该槽 PASS（取各窗的逐槽并集）
        has1 = has2 = has3 = has4 = has5 = False
        need3 = need4 = False
        for bs in anchors:
            blk = spec[bs:bs + window]
            if defined:
                has1 = has1 or bool(_slot1_re(name).search(blk))
                has2 = has2 or bool(SLOT2.search(blk))
                need3 = need3 or bool(NEEDS_SLOT3.search(blk))
                need4 = need4 or bool(HAS_VALUE.search(blk))
            has3 = has3 or bool(SLOT3.search(blk))
            has4 = has4 or bool(SLOT4.search(blk))
            has5 = has5 or bool(SLOT5.search(blk))
        block_start = anchors[0]

        missing, warn = [], []
        if not has1:
            missing.append('槽1依据')
        if not has2:
            missing.append('槽2操作')
        if need3 and not has3:
            missing.append('槽3定义')
        if need4 and not has4:
            # 校准要点 6：槽4 按 X14 三层类别分级，不一律 FAIL
            if _SLOT4_HARD_KIND.search(name):
                missing.append('槽4取值表述')          # 模型超参/量化尺度类 → FAIL
            elif _SLOT4_SOFT_KIND.search(name):
                warn.append('槽4取值表述(阈值/对照关系类,X14 可删)')   # → WARN
            else:
                warn.append('槽4取值表述(类别未归,按 X14 人工判)')     # → WARN，待归类
        if not has5:
            warn.append('槽5可调整')      # 建议项，不阻断（校准要点 7）

        # 补充路径识别出的对象: 缺槽一律降为 WARN (该路径未经 8.1 双向验证, 见
        # _BARE_PRESET_RE 注释)。累积 2 案实测无误报后再考虑升 FAIL。
        is_supp = name in supplementary
        if is_supp and missing:
            warn = [f'{x}(裸量词补充识别,未经双向验证)' for x in missing] + warn
            missing = []

        rows.append({
            'name': name,
            'pos': block_start,
            'anchors': len(anchors),
            'supplementary': is_supp,
            'skipped': False,
            'slot1_依据': has1,
            'slot2_操作': has2,
            'slot3_定义': has3 if need3 else None,
            'slot4_取值': has4 if need4 else None,
            'slot5_可调': has5,
            'missing': missing,
            'warn': warn,
            'ok': not missing,
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description='说明书预设量点数闸门')
    ap.add_argument('md', help='全文稿 md 路径')
    ap.add_argument('--window', type=int, default=400, help='解释块扫描窗口汉字数，默认400')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    a = ap.parse_args()

    try:
        text = open(a.md, encoding='utf-8').read()
    except OSError as e:
        print('读取失败: %s' % e, file=sys.stderr)
        return 2

    rows = audit(text, a.window)
    checked = [r for r in rows if not r.get('skipped')]
    skipped = [r for r in rows if r.get('skipped')]
    bad = [r for r in checked if not r['ok']]
    warned = [r for r in checked if r.get('warn')]

    if a.json:
        print(json.dumps({
            'total': len(rows), 'checked': len(checked),
            'skipped': len(skipped), 'fail': len(bad), 'warn': len(warned),
            'ok': not bad, 'rows': rows,
        }, ensure_ascii=False, indent=2))
        return 1 if bad else 0

    def mk(v):
        return '—' if v is None else ('有' if v else '★无')

    print('预设量点数（说明书区：核查 %d 个，跳过模型类 %d 个；其中 %d 个由裸量词补充路径识别，标 ※）'
          % (len(checked), len(skipped), sum(1 for r in checked if r.get('supplementary'))))
    print('%-22s %-6s %-6s %-6s %-6s %-6s %s' %
          ('预设量', '依据', '操作', '定义', '取值', '可调', '缺(FAIL)'))
    print('-' * 78)
    for r in checked:
        print('%-22s %-6s %-6s %-6s %-6s %-6s %s' % (
            r['name'] + ('※' if r.get('supplementary') else ''),
            mk(r['slot1_依据']), mk(r['slot2_操作']),
            mk(r['slot3_定义']), mk(r['slot4_取值']), mk(r['slot5_可调']),
            '、'.join(r['missing']) if r['missing'] else ''))
    for r in skipped:
        print('%-22s %s' % (r['name'], '（跳过：' + r['reason'] + '）'))
    print('-' * 78)

    if warned:
        print('WARN（建议项，不阻断）：%d 个有提示项——' % len(warned))
        for r in warned:
            print('  · %s：%s' % (r['name'] + ('※' if r.get('supplementary') else ''),
                                 '、'.join(r['warn'])))
        print('  ※ = 裸量词补充路径识别，其缺槽只计 WARN（该路径未经 8.1 双向验证）；'
              '请人工确认后再决定是否改稿')
    if bad:
        print('FAIL：%d/%d 个预设量有必填槽为空，不得交付' % (len(bad), len(checked)))
        for r in bad:
            print('  - %s 缺 %s' % (r['name'], '、'.join(r['missing'])))
        return 1
    print('PASS：%d 个预设量必填槽齐全' % len(checked))
    return 0


if __name__ == '__main__':
    sys.exit(main())

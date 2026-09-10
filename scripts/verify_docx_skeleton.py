#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_docx_skeleton.py — 专利模板 DOCX 骨架 + 分节落位 + 标题/权要段格式一次性机械校验。

用途：权要稿 / 全文稿写入完成后，收尾一次性核对模板骨架与 G8-0/G8-0b 格式机械项，
替代人工逐分节核对。H2609029 审核v1（王工「格式乱套，发明名称不一致，副标题也没了」）
暴露的四个盲区自 2026-09-10 起全部机械化——此前脚本只查骨架与发明名称段六属性，
对照表 G8-0 明文「交付前必须逐分节核对本表」却一直是人工动作：
  ① 分节落位（G8-0）：分节1 摘要 / 分节2 摘要附图 / 分节3 权要 1..N / 分节4 发明名称→
     技术领域→背景技术(→发明内容→附图说明→具体实施方式) / 分节5 说明书附图+图1；
     说明书内容塞进分节3、分节4 首段不是发明名称，均 FAIL；
  ② 章节标题段：存在、顺序、加粗、顶格（G8-0b）；权要稿不得出现全文阶段标题；
  ③ 权要段行距：分节3 每个正文段 1.5 倍行距（w:line=360 auto，王工定稿标准段）；
  ④ 发明名称 = 给定名称：传 --invention-name 时分节4 首段须与之逐字一致
     （G1-1「一种」跟给定名称走；缺参报「未执行」WARN，不得视为合规）。
发明名称段六属性（G8-0b：宋体/三号/加粗/居中/首行缩进0/1.5倍行距）默认用内置常量
比对（六属性本就是固定值）；`--reference-docx` 可选，传了就改从基准稿同位置提取期望值。
（此前默认基准稿是原作者 macOS 绝对路径，本机永不可读、该项长期「未执行」，H2608165 #17。）

用法：
    python scripts/verify_docx_skeleton.py <file.docx> --stage 全文 --invention-name "<给定名称>"
    python scripts/verify_docx_skeleton.py <file.docx> --stage 权要 --invention-name "<给定名称>"
    python scripts/verify_docx_skeleton.py <file.docx> --expect-sectpr 5 --expect-headers 13
    python scripts/verify_docx_skeleton.py <file.docx> --reference-docx <基准稿.docx>   # 六属性改从基准稿取

退出码：全部 PASS=0；有 FAIL=1；文件/参数错误=2。
"""
import argparse
import re
import sys
import zipfile

# G8-0b 发明名称段六属性内置期望值（W04）；--reference-docx 传入时改从基准稿提取
TITLE_EXPECTED = {
    "font_east": "宋体",
    "sz": "32",
    "bold": True,
    "jc": "center",
    "line": "360",
}
# 王工定稿标准段行距（H2608165 权要1稿/定稿：pPr 只有 <w:spacing w:line="360" w:lineRule="auto"/>）
BODY_LINE = "360"

# G8-0 分节4 章节标题（顺序固定）；权要稿只允许前两个
SPEC_HEADINGS_ALL = ("技术领域", "背景技术", "发明内容", "附图说明", "具体实施方式")
SPEC_HEADINGS_CLAIMS = SPEC_HEADINGS_ALL[:2]

_PARA_RE = re.compile(r"<w:p(?:\s[^>]*)?/>|<w:p(?:\s[^>]*)?>.*?</w:p>", re.S)  # 含自闭合 <w:p/>（留痕删段常留空壳）


def _read(zf, name):
    try:
        return zf.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return None


def _para_text(p: str) -> str:
    """段落接受修订态文本（w:t，不含 w:delText）。"""
    return "".join(re.findall(r"<w:t\b[^>]*>([^<]*)</w:t>", p)).strip()


def _has_graphic(p: str) -> bool:
    return any(k in p for k in ("<w:drawing", "<w:object", "<w:pict", "<v:imagedata"))


def _is_blank(p: str) -> bool:
    return not _para_text(p) and not _has_graphic(p)


def _split_sections(doc: str) -> list[list[str]]:
    """按 sectPr 段切成 5 个分节的段落列表（分节5 = 第 4 个 sectPr 段之后的全部段落）。"""
    paras = _PARA_RE.findall(doc)
    out, cur = [], []
    for p in paras:
        cur.append(p)
        if "<w:sectPr" in p:
            out.append(cur)
            cur = []
    out.append(cur)  # 分节5（其 sectPr 为 body 末尾裸 sectPr，不在段内）
    return out


def _style_first_line(styles_xml: str, style_id: str | None) -> tuple[str | None, str | None]:
    """段落样式链（缺 pStyle 则取默认段落样式）上最近的 (firstLine, firstLineChars)；无则 (None, None)。"""
    if not styles_xml:
        return None, None
    if style_id is None:
        m = re.search(r'<w:style w:type="paragraph" w:default="1"[^>]*w:styleId="([^"]+)"', styles_xml)
        if not m:
            return None, None
        style_id = m.group(1)
    fl = fc = None
    seen = set()
    while style_id and style_id not in seen:
        seen.add(style_id)
        m = re.search(r'<w:style w:type="paragraph"[^>]*w:styleId="%s"[^>]*>(.*?)</w:style>'
                      % re.escape(style_id), styles_xml, re.S)
        if not m:
            break
        body = m.group(1)
        ind = re.search(r"<w:ind\b([^>]*)/>", body)
        if ind:
            a = re.search(r'w:firstLine="([^"]*)"', ind.group(1))
            b = re.search(r'w:firstLineChars="([^"]*)"', ind.group(1))
            if fl is None and a:
                fl = a.group(1)
            if fc is None and b:
                fc = b.group(1)
            if fl is not None and fc is not None:
                break
        base = re.search(r'<w:basedOn w:val="([^"]+)"', body)
        style_id = base.group(1) if base else None
    return fl, fc


def _ind_first_line_zero(p: str, styles_xml: str = "") -> bool:
    """段落首行缩进有效值为 0。

    OOXML 的 ind 属性逐个继承，且 firstLineChars 优先于 firstLine：模板 Normal 样式带
    firstLineChars=200，段内只写 firstLine=0 不写 firstLineChars=0 时**仍缩进两字**
    （H2608165 审核v1 王工批注 5「模板这里是顶格」实测 firstLine=562；WPS 再保存会把
    继承值物化为 firstLine=643）。故：样式链带非零 firstLineChars 时，段内必须显式
    firstLineChars=0；缺 ind 一律不合格。
    """
    ppr = re.search(r"<w:pPr>.*?</w:pPr>", p, re.S)
    ppr_s = ppr.group(0) if ppr else ""
    ps = re.search(r'<w:pStyle w:val="([^"]+)"', ppr_s)
    style_fl, style_fc = _style_first_line(styles_xml, ps.group(1) if ps else None)
    ind = re.search(r"<w:ind\b([^>]*)/>", ppr_s)
    attrs = ind.group(1) if ind else ""
    fl = re.search(r'w:firstLine="([^"]*)"', attrs)
    fc = re.search(r'w:firstLineChars="([^"]*)"', attrs)
    # 有效值 = 段内直接值，缺则继承样式链；firstLineChars 非零即压过 firstLine
    eff_fc = fc.group(1) if fc else style_fc
    eff_fl = fl.group(1) if fl else style_fl
    zero = lambda v: v is None or v in ("0", "0.0")
    if not zero(eff_fc):
        return False
    return zero(eff_fl)


def _text_runs_bold(p: str) -> bool:
    """段内每个带文本的 run 都加粗（<w:b/> 或 w:val=true/1；w:val=0/false 视为不加粗）。"""
    runs = re.findall(r"<w:r\b[^>]*>.*?</w:r>", p, re.S)
    text_runs = [r for r in runs if re.search(r"<w:t\b", r)]
    if not text_runs:
        return False
    for r in text_runs:
        rpr = re.search(r"<w:rPr>.*?</w:rPr>", r, re.S)
        rpr_s = rpr.group(0) if rpr else ""
        if re.search(r'<w:b w:val="(0|false)"', rpr_s):
            return False
        if not re.search(r"<w:b(/>| w:val=\"(1|true|on)\")", rpr_s):
            return False
    return True


def _looks_like_spec_para(txt: str, invention_name) -> bool:
    """分节3 内疑似说明书段：章节标题原文 / 发明名称（含带「一种」变体）/ 技术领域首句 / 背景技术收口句。

    H2609029 1稿实测：三章被塞进权利要求书分节，且发明名称多了「一种」、标题段整个漏写，
    只按标题原文与给定名称逐字匹配抓不到——补句式特征。
    """
    if not txt:
        return False
    if txt in SPEC_HEADINGS_ALL:
        return True
    if invention_name and invention_name.strip():
        want = invention_name.strip()
        if txt in (want, "一种" + want) or "一种" + txt == want:
            return True
    if txt.startswith("本发明涉及"):
        return True
    if txt.startswith("因此，现有技术存在"):
        return True
    return False


def _line_spacing_ok(p: str) -> bool:
    ppr = re.search(r"<w:pPr>.*?</w:pPr>", p, re.S)
    if not ppr:
        return False
    sp = re.search(r"<w:spacing\b[^>]*/>", ppr.group(0))
    if not sp:
        return False
    return (f'w:line="{BODY_LINE}"' in sp.group(0)) and ('w:lineRule="auto"' in sp.group(0))


def check(docx_path, stage, expect_sectpr, expect_headers,
          reference_docx=None, invention_name=None):
    results = []  # (level, name, ok, detail)  level: FAIL/WARN/INFO

    try:
        zf = zipfile.ZipFile(docx_path)
    except (zipfile.BadZipFile, FileNotFoundError) as e:
        print(f"[ERROR] 无法打开 DOCX: {e}")
        return 2

    names = zf.namelist()
    doc = _read(zf, "word/document.xml")
    if doc is None:
        print("[ERROR] 缺少 word/document.xml")
        return 2

    # 1) sectPr 数量
    sectpr = len(re.findall(r"<w:sectPr[ >]", doc))
    results.append(("FAIL", f"sectPr 数量={sectpr}（期望 {expect_sectpr}）",
                    sectpr == expect_sectpr, ""))

    # 2) header 文件数
    headers = [n for n in names if re.match(r"word/header\d+\.xml$", n)]
    results.append(("FAIL", f"header*.xml 数量={len(headers)}（期望 {expect_headers}）",
                    len(headers) == expect_headers, ""))

    # 3) headerReference 全部保留（至少与 header 文件数相称；不少于 sectPr 应引用数）
    href = len(re.findall(r"<w:headerReference[ >]", doc))
    results.append(("FAIL", f"headerReference 数量={href}（应>0且保留）",
                    href > 0, ""))

    # 4) 残留修订痕迹（干净稿应为 0；留痕稿会有，标 INFO）
    del_n = len(re.findall(r"<w:del[ />]", doc))
    ins_n = len(re.findall(r"<w:ins[ >]", doc))
    pprc = len(re.findall(r"<w:pPrChange[ >]", doc))
    rprc = len(re.findall(r"<w:rPrChange[ >]", doc))
    deltext = len(re.findall(r"<w:delText[ >]", doc))
    trace_total = del_n + ins_n + pprc + rprc
    results.append(("INFO",
                    f"修订痕迹: del={del_n} ins={ins_n} pPrChange={pprc} rPrChange={rprc} delText={deltext}",
                    True,
                    "（干净稿应全为0；留痕稿正常含 del/ins）"))

    # 5) 可见页眉文本（按阶段）— 只取真正的标题文本，排除页码域/字段代码
    def visible_text(xml):
        # 去掉字段域内容（PAGE 等）与 instrText、域字符
        xml = re.sub(r"<w:instrText[^>]*>.*?</w:instrText>", "", xml, flags=re.S)
        xml = re.sub(r"<w:fldChar[^>]*/?>", "", xml)
        # 非贪婪逐个取 <w:t>…</w:t>，禁止跨越下一个 < 标签
        parts = re.findall(r"<w:t\b[^>]*>([^<]*)</w:t>", xml)
        t = "".join(parts).strip()
        # 去掉纯数字页码
        if re.fullmatch(r"\d+", t):
            return ""
        return t

    header_texts = []
    for h in sorted(headers):
        ht = _read(zf, h) or ""
        txt = visible_text(ht)
        if txt:
            header_texts.append(txt)
    seen = set()
    header_texts = [x for x in header_texts if not (x in seen or seen.add(x))]
    joined = " | ".join(header_texts)

    if stage == "权要":
        # 权要稿可见页眉应仅含"权利要求书""说明书"；不应出现后续阶段页眉
        forbidden = ["说明书摘要", "摘要附图", "说明书附图"]
        bad = [w for w in forbidden if w in joined]
        results.append(("WARN",
                        f"权要稿可见页眉={joined or '(空)'}",
                        len(bad) == 0,
                        f"出现不应可见的页眉: {bad}" if bad else ""))
    else:
        results.append(("INFO", f"可见页眉={joined or '(空)'}", True, ""))

    # 6) [Content_Types] 与 rels 中 comments 注册一致性（有 comments.xml 才查）
    if "word/comments.xml" in names:
        ct = _read(zf, "[Content_Types].xml") or ""
        rels = _read(zf, "word/_rels/document.xml.rels") or ""
        ct_ok = "/word/comments.xml" in ct
        rel_ok = "comments.xml" in rels
        results.append(("FAIL",
                        f"comments.xml 注册: ContentTypes={'有' if ct_ok else '缺'} rels={'有' if rel_ok else '缺'}",
                        ct_ok and rel_ok,
                        "存在 comments.xml 但未在 [Content_Types]/rels 注册（孤立部件，Word 可能报错）"
                        if not (ct_ok and rel_ok) else ""))
        # 孤立部件检测：commentsIds/commentsExtensible 存在但未注册
        for part in ["commentsIds.xml", "commentsExtensible.xml"]:
            if f"word/{part}" in names:
                reg = (f"/word/{part}" in ct) and (part in rels)
                results.append(("WARN",
                                f"{part} 注册={'有' if reg else '缺'}",
                                reg,
                                f"{part} 为孤立部件（comment.py 常见副作用）" if not reg else ""))

    # 7) 发明名称段六属性格式 (G8-0b; W04 机械化, 期望值=内置常量或 --reference-docx 基准稿)
    styles = _read(zf, "word/styles.xml") or ""
    check_title_format(doc, styles, reference_docx, invention_name, results)

    # 8)-11) 分节落位 / 章节标题段 / 权要段行距 / 发明名称=给定名称（G8-0、G8-0b、G1-1）
    if sectpr == 5:
        check_section_layout(doc, stage, invention_name, trace_total, results, styles)
    else:
        results.append(("WARN", "分节落位·校验未执行", False,
                        f"sectPr 数量 {sectpr} ≠ 5，无法按分节切分"))

    zf.close()

    # 输出
    print(f"== DOCX 骨架校验: {docx_path}  (stage={stage}) ==")
    n_fail = 0
    for level, name, ok, detail in results:
        # 「未执行」项以 (WARN, ok=False) 登记 → 打印 WARN、不计 FAIL；绝不能标 PASS（H2608165 #17 假绿灯）
        if level == "INFO":
            mark = "·"
        elif ok:
            mark = "PASS"
        else:
            mark = "FAIL" if level == "FAIL" else "WARN"
        if not ok and level == "FAIL":
            n_fail += 1
        line = f"  [{mark:>4}] {name}"
        if detail:
            line += f"  — {detail}"
        print(line)

    print("-" * 40)
    if n_fail == 0:
        print("结果: 机械项全部 PASS（标 WARN 的「未执行」项不得视为合规，须补参重跑或人工核对）")
        return 0
    print(f"结果: {n_fail} 项 FAIL，需修正")
    return 1


def check_section_layout(doc: str, stage: str, invention_name, trace_total: int, results,
                         styles_xml: str = "") -> None:
    """G8-0 分节落位 + G8-0b 标题段格式 + 权要段行距 + 发明名称=给定名称。"""
    secs = _split_sections(doc)
    if len(secs) != 5:
        results.append(("WARN", "分节落位·校验未执行", False, f"切分得到 {len(secs)} 个分节"))
        return
    s1, s2, s3, s4, s5 = secs
    full = stage != "权要"

    def _body(sec):
        # sectPr 段若自带正文/图（X2608107 定稿摘要正文就写在分节1 的 sectPr 段内）同样计入
        return [p for p in sec if not _is_blank(p)]

    # ---- 分节1 摘要 ----
    t1 = [p for p in _body(s1) if _para_text(p)]
    if full:
        results.append(("FAIL", f"分节1·摘要正文段={len(t1)}", len(t1) >= 1,
                        "全文稿分节1 应有摘要正文" if not t1 else ""))
    else:
        results.append(("FAIL", f"分节1·权要稿应留空（正文段={len(t1)}）", len(t1) == 0,
                        f"权要稿分节1 出现正文「{_para_text(t1[0])[:20]}」" if t1 else ""))

    # ---- 分节2 摘要附图 ----
    g2 = any(_has_graphic(p) for p in s2)
    t2 = [p for p in _body(s2) if _para_text(p)]
    if full:
        results.append(("FAIL", "分节2·摘要附图有图", g2, "全文稿分节2 应嵌入图 1" if not g2 else ""))
    else:
        results.append(("FAIL", "分节2·权要稿应留空", not g2 and not t2,
                        "权要稿分节2 出现图/文" if (g2 or t2) else ""))

    # ---- 分节3 权利要求书 ----
    b3 = _body(s3)
    first3 = _para_text(b3[0]) if b3 else ""
    first_ok = bool(re.match(r"^1\s*[\.．、]", first3))
    results.append(("FAIL", "分节3·首段为权利要求 1", first_ok,
                    f"首段实得「{first3[:30]}」" if not first_ok else ""))
    leaked = [_para_text(p) for p in b3 if _looks_like_spec_para(_para_text(p), invention_name)]
    results.append(("FAIL", "分节3·无说明书内容混入", not leaked,
                    f"分节3 出现说明书段（发明名称/技术领域/背景技术塞进了权利要求书分节）: "
                    f"{[s[:20] for s in leaked]}" if leaked else ""))
    bad_line = [i for i, p in enumerate(b3) if _para_text(p) and not _line_spacing_ok(p)]
    lvl = "WARN" if trace_total else "FAIL"  # 留痕稿含审核人手写段，降为 WARN
    results.append((lvl, f"分节3·权要段 1.5 倍行距（{len(b3) - len(bad_line)}/{len(b3)} 段）",
                    not bad_line,
                    (f"{len(bad_line)} 段缺 w:line=360 auto，首个第 {bad_line[0] + 1} 段"
                     f"「{_para_text(b3[bad_line[0]])[:20]}」" if bad_line else "")))

    # ---- 分节4 说明书 ----
    b4 = _body(s4)
    texts4 = [_para_text(p) for p in b4]
    first4 = texts4[0] if texts4 else ""
    # 发明名称 = 给定名称（G1-1）
    if invention_name and invention_name.strip():
        want = invention_name.strip()
        ok = first4 == want
        hint = ""
        if not ok and first4 == "一种" + want:
            hint = "（自行加了「一种」——G1-1 名称跟给定值走，王工给的不带就不带）"
        elif not ok and "一种" + first4 == want:
            hint = "（漏了给定名称自带的「一种」）"
        results.append(("FAIL", "分节4·首段发明名称=给定名称", ok,
                        "" if ok else f"期望「{want}」 实得「{first4[:40]}」{hint}"))
    else:
        results.append(("WARN", "分节4·发明名称=给定名称·校验未执行", False,
                        "缺 --invention-name（不得视为合规；G1-1 名称须与王工给定值逐字一致）"))
    # 章节标题段：存在 / 顺序 / 加粗 / 顶格
    required = SPEC_HEADINGS_ALL if full else SPEC_HEADINGS_CLAIMS
    idx = {h: [i for i, t in enumerate(texts4) if t == h] for h in SPEC_HEADINGS_ALL}
    missing = [h for h in required if not idx[h]]
    results.append(("FAIL", f"分节4·章节标题段齐全（{'/'.join(required)}）", not missing,
                    f"缺标题段: {missing}" if missing else ""))
    dup = [h for h in required if len(idx[h]) > 1]
    if dup:
        results.append(("FAIL", "分节4·章节标题段唯一", False, f"标题段重复: {dup}"))
    present = [(idx[h][0], h) for h in required if idx[h]]
    ordered = [h for _, h in sorted(present)] == [h for _, h in present]
    results.append(("FAIL", "分节4·章节标题顺序", ordered,
                    f"实得顺序 {[h for _, h in sorted(present)]}" if not ordered else ""))
    if idx["技术领域"]:
        i_field = idx["技术领域"][0]
        results.append(("FAIL", "分节4·发明名称段在技术领域标题之前且为首段", i_field == 1,
                        f"技术领域标题前有 {i_field} 段（应恰为发明名称 1 段）" if i_field != 1 else ""))
    for h in required:
        if not idx[h]:
            continue
        p = b4[idx[h][0]]
        bold, top = _text_runs_bold(p), _ind_first_line_zero(p, styles_xml)
        results.append(("FAIL", f"分节4·标题「{h}」加粗+顶格", bold and top,
                        "" if (bold and top) else
                        ("缺加粗 " if not bold else "") + ("缺顶格(须 ind firstLine=0 且 firstLineChars=0)" if not top else "")))
    if not full:
        extra = [h for h in SPEC_HEADINGS_ALL[2:] if idx[h]]
        results.append(("FAIL", "分节4·权要稿无全文阶段标题段", not extra,
                        f"出现 {extra}" if extra else ""))

    # ---- 空段（王工 X2608107 全文审核v1 点名「内容段之间有莫名其妙的换行」）----
    # 分节1/3/4 为纯文本分节, 干净稿不应残留无文本无图的空段 (模板自带空占位段由注入脚本清理);
    # 分节2/5 承载图片、模板结构自带空段, 不计。留痕稿的整段删除会留下空壳段, 降 WARN。
    # 权要稿分节1 按设计留空 (模板自带 2 个空占位段, 全文阶段才被摘要替换), 不计。
    scope = (("分节1", s1), ("分节3", s3), ("分节4", s4)) if full else (("分节3", s3), ("分节4", s4))
    blanks = {label: sum(1 for p in sec if "<w:sectPr" not in p and _is_blank(p)) for label, sec in scope}
    n_blank = sum(blanks.values())
    scope_lbl = "/".join(l[2:] for l, _ in scope)
    results.append(("WARN" if trace_total else "FAIL", f"分节{scope_lbl}·无空段（{n_blank} 个）", n_blank == 0,
                    f"空段分布 {blanks}（无文本无图的 <w:p>；干净稿应为 0）" if n_blank else ""))

    # ---- 分节5 说明书附图 ----
    g5 = any(_has_graphic(p) for p in s5)
    cap5 = any(re.fullmatch(r"图\s*1\s*[。．.]?", _para_text(p)) for p in s5)
    t5 = [p for p in _body(s5) if _para_text(p)]
    if full:
        results.append(("FAIL", "分节5·说明书附图有图+「图1」图题", g5 and cap5,
                        ("无图 " if not g5 else "") + ("缺「图1」图题段" if not cap5 else "")))
    else:
        results.append(("FAIL", "分节5·权要稿应留空", not g5 and not t5,
                        "权要稿分节5 出现图/文" if (g5 or t5) else ""))


def _parse_rpr_attrs(rpr_xml: str) -> dict:
    """从 run 属性 XML 提取格式属性: font_ascii/font_east/sz/bold."""
    out = {}
    rf = re.search(r"<w:rFonts[^>]*/>", rpr_xml)
    if rf:
        m = re.search(r'w:ascii="([^"]+)"', rf.group(0))
        if m:
            out["font_ascii"] = m.group(1)
        m = re.search(r'w:eastAsia="([^"]+)"', rf.group(0))
        if m:
            out["font_east"] = m.group(1)
    m = re.search(r'<w:sz w:val="(\d+)"', rpr_xml)
    if m:
        out["sz"] = m.group(1)
    if re.search(r"<w:b/>", rpr_xml):
        out["bold"] = True
    elif re.search(r'<w:b w:val="(0|false)"', rpr_xml):
        out["bold"] = False
    return out


def _parse_style_chain(styles_xml: str, style_id: str, depth: int = 0) -> dict:
    """沿 basedOn 链收集命名样式格式属性（链顶优先；供 pStyle 二级解析用）."""
    if depth > 5:
        return {}
    out = {}
    m = re.search(
        r'<w:style w:type="paragraph" w:styleId="%s">(.*?)</w:style>' % re.escape(style_id),
        styles_xml, re.S)
    if not m:
        return out
    body = m.group(1)
    base = re.search(r'<w:basedOn w:val="([^"]+)"', body)
    if base:
        out.update(_parse_style_chain(styles_xml, base.group(1), depth + 1))
    rpr = re.search(r"<w:rPr>(.*?)</w:rPr>", body, re.S)
    if rpr:
        out.update(_parse_rpr_attrs(rpr.group(1)))
    ppr = re.search(r"<w:pPr>.*?</w:pPr>", body, re.S)
    if ppr:
        ppr_s = ppr.group(0)
        m = re.search(r'<w:jc w:val="([^"]+)"', ppr_s)
        if m:
            out["jc"] = m.group(1)
        m = re.search(r'<w:spacing w:line="(\d+)" w:lineRule="([^"]+)"', ppr_s)
        if m:
            out["line"], out["lineRule"] = m.group(1), m.group(2)
    return out


def _parse_doc_defaults(styles_xml: str) -> dict:
    """解析 styles.xml docDefaults 的 rPrDefault（三级解析兜底层）."""
    out = {}
    dd = re.search(r"<w:docDefaults>(.*?)</w:docDefaults>", styles_xml, re.S)
    if dd:
        rprd = re.search(r"<w:rPrDefault>(.*?)</w:rPrDefault>", dd.group(1), re.S)
        if rprd:
            rpr = re.search(r"<w:rPr>(.*?)</w:rPr>", rprd.group(1), re.S)
            if rpr:
                out.update(_parse_rpr_attrs(rpr.group(1)))
    return out


def _parse_para_format(para_xml: str, styles_xml: str) -> dict:
    """三级解析段落有效格式: 段内直接格式(pPr rPr + 首 run rPr) → pStyle 样式链 → docDefaults.

    只取直接格式会漏样式继承与"格式全写在段落标记 rPr"的写法（X2607024 发明名称段
    即 run 无 rPr、格式全在 pPr 内嵌 rPr），故按三层合并、直接格式覆盖样式/默认。
    返回: font_ascii/font_east/sz/bold/jc/firstLine/firstLineChars/line/lineRule.
    """
    ppr = re.search(r"<w:pPr>.*?</w:pPr>", para_xml, re.S)
    ppr_s = ppr.group(0) if ppr else ""
    direct = {}
    m = re.search(r'<w:jc w:val="([^"]+)"', ppr_s)
    if m:
        direct["jc"] = m.group(1)
    m = re.search(r'<w:spacing w:line="(\d+)" w:lineRule="([^"]+)"', ppr_s)
    if m:
        direct["line"], direct["lineRule"] = m.group(1), m.group(2)
    m = re.search(r"<w:ind ([^/]*)/>", ppr_s)
    if m:
        ind_body = m.group(1)
        fm = re.search(r'w:firstLine="([^"]*)"', ind_body)
        direct["firstLine"] = fm.group(1) if fm else None
        fm = re.search(r'w:firstLineChars="([^"]*)"', ind_body)
        direct["firstLineChars"] = fm.group(1) if fm else None
    # 段内 run 属性: pPr 内嵌 rPr（段落标记格式）+ 正文 run 的 rPr（后者覆盖前者）
    for rpr_xml in re.findall(r"<w:rPr>(.*?)</w:rPr>", para_xml, re.S):
        direct.update(_parse_rpr_attrs(rpr_xml))
    style_fmt = {}
    m = re.search(r'<w:pStyle w:val="([^"]+)"', ppr_s)
    if m:
        style_fmt = _parse_style_chain(styles_xml, m.group(1))
    defaults = _parse_doc_defaults(styles_xml)
    merged = {}
    for layer in (defaults, style_fmt, direct):
        for k, v in layer.items():
            if v is not None:
                merged[k] = v
    return merged


def _locate_title_para(paras: list[str], invention_name: str | None) -> int | None:
    """定位发明名称段: 优先按 --invention-name 逐字匹配; 缺参/未命中取"技术领域"标题前一段."""
    if invention_name:
        name = invention_name.strip()
        for i, p in enumerate(paras):
            if _para_text(p) == name:
                return i
    for i, p in enumerate(paras):
        if _para_text(p) == "技术领域":
            return i - 1
    return None


def _extract_title_format(doc_xml: str, styles_xml: str, invention_name: str | None) -> dict | None:
    paras = _PARA_RE.findall(doc_xml)
    idx = _locate_title_para(paras, invention_name)
    if idx is None:
        return None
    return _parse_para_format(paras[idx], styles_xml)


def check_title_format(doc_xml, styles_xml, reference_docx, invention_name, results) -> None:
    """W04: 发明名称段六属性格式机械校验（G8-0b）.

    六属性：宋体 / 三号(sz 32) / 加粗 / 居中 / 首行缩进0 / 1.5倍行距。
    期望值默认 = 内置常量 TITLE_EXPECTED（六属性是固定值，不依赖任何机器上的基准稿）；
    传 --reference-docx 时改从基准稿同位置现场提取（基准不可读/定位不到 → 报「未执行」
    WARN、不计 FAIL，但不得视为合规）。本稿定位不到发明名称段 → 同样报「未执行」。
    """
    if reference_docx:
        try:
            zf = zipfile.ZipFile(reference_docx)
            ref_doc = _read(zf, "word/document.xml") or ""
            ref_styles = _read(zf, "word/styles.xml") or ""
            zf.close()
        except (zipfile.BadZipFile, FileNotFoundError):
            results.append(("WARN", "发明名称段·格式校验未执行", False,
                            f"期望值基准稿不可读: {reference_docx}"))
            return
        ref_fmt = _extract_title_format(ref_doc, ref_styles, invention_name)
        if ref_fmt is None:
            results.append(("WARN", "发明名称段·格式校验未执行", False,
                            "基准稿中未定位到发明名称段（技术领域标题前一段）"))
            return
        source = "基准稿"
    else:
        ref_fmt = dict(TITLE_EXPECTED)
        source = "内置常量"
    target_fmt = _extract_title_format(doc_xml, styles_xml, invention_name)
    if target_fmt is None:
        results.append(("WARN", "发明名称段·格式校验未执行", False,
                        "本稿未定位到发明名称段（技术领域标题前一段）"))
        return
    checks = [
        ("字体(宋体)", "font_east", ref_fmt.get("font_east")),
        ("字号(三号)", "sz", ref_fmt.get("sz")),
        ("加粗", "bold", ref_fmt.get("bold")),
        ("居中", "jc", ref_fmt.get("jc")),
        ("1.5倍行距", "line", ref_fmt.get("line")),
    ]
    for label, key, ref_val in checks:
        got = target_fmt.get(key)
        ok = got == ref_val
        results.append(("FAIL", f"发明名称段·{label}", ok,
                        f"期望={ref_val!r}({source}) 实得={got!r}" if not ok else ""))

    paras = _PARA_RE.findall(doc_xml)
    idx = _locate_title_para(paras, invention_name)
    ok = idx is not None and _ind_first_line_zero(paras[idx], styles_xml)
    results.append(("FAIL", "发明名称段·首行缩进0", ok,
                    "期望=ind firstLine=0 且 firstLineChars=0（模板 Normal 的 firstLineChars=200 会压过单写的 firstLine=0）"
                    f" 实得=firstLineChars={target_fmt.get('firstLineChars')!r} "
                    f"firstLine={target_fmt.get('firstLine')!r}" if not ok else ""))


if __name__ == "__main__":
    # Windows GBK 控制台: 输出含 GBK 外字符时裸跑 UnicodeEncodeError (H2609029 实测, 2026-09-10)。强制 UTF-8。
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="专利模板 DOCX 骨架/分节落位/标题与权要段格式一次性校验")
    ap.add_argument("docx", help="待校验的 .docx 文件")
    ap.add_argument("--stage", choices=["权要", "全文"], default="全文",
                    help="稿次：权要稿分节1/2/5 须留空、分节4 只允许技术领域/背景技术标题")
    ap.add_argument("--expect-sectpr", type=int, default=5, help="期望 sectPr 数（默认5）")
    ap.add_argument("--expect-headers", type=int, default=13, help="期望 header*.xml 数（默认13）")
    ap.add_argument("--reference-docx", default=None,
                    help="发明名称段六属性期望值改从该基准稿提取（缺省用内置常量，见 TITLE_EXPECTED）")
    ap.add_argument("--invention-name", default=None,
                    help="王工给定的案件名称原样：定位发明名称段并校验分节4 首段与之逐字一致；缺省该项报 WARN 未执行")
    args = ap.parse_args()
    sys.exit(check(args.docx, args.stage, args.expect_sectpr, args.expect_headers,
                   args.reference_docx, args.invention_name))

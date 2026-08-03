#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_docx_skeleton.py — 专利模板 DOCX 骨架机械项一次性校验。

用途：全文一稿/权要稿写入完成后，收尾一次性核对模板骨架机械项，
替代分块注入时反复手动数 sectPr / header / 残留痕迹。
只覆盖"机械可判定"的项；标题加粗/顶格/字号、正文内容落位等需语义判断的，
仍由 patent 收尾人工核对（见 docx-template.md G8-0、G8-0b）。

用法：
    python scripts/verify_docx_skeleton.py <file.docx>
    python scripts/verify_docx_skeleton.py <file.docx> --stage 权要   # 权要稿可见页眉规则
    python scripts/verify_docx_skeleton.py <file.docx> --stage 全文   # 全文稿（默认）
    python scripts/verify_docx_skeleton.py <file.docx> --expect-sectpr 5 --expect-headers 13

退出码：全部 PASS=0；有 FAIL=1；文件/参数错误=2。
"""
import argparse
import re
import sys
import zipfile

# W04 发明名称段格式校验的期望值来源: G8-0b 基准稿 (docx-template.md G8-0b「基准 = H2606029 全文1稿」).
# 从基准稿发明名称段现场提取六属性作为期望, 不硬编码格式值; 其他基准用 --reference-docx 显式覆盖.
DEFAULT_REFERENCE_DOCX = (
    "/Users/example/Desktop/Patent/夏晓贝/Done/H2606029一种基于线性传感器的智能锁芯控制方法及系统/"
    "H2606029-全文1稿-夏晓贝-一种基于线性传感器的智能锁芯控制方法及系统.docx"
)


def _read(zf, name):
    try:
        return zf.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return None


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
        # 权要稿正文禁显章节
        forbid_body = ["发明内容", "附图说明", "具体实施方式"]
        body_txt = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", doc))
        bad_body = [w for w in forbid_body if w in body_txt]
        results.append(("WARN",
                        "权要稿正文禁显章节检查",
                        len(bad_body) == 0,
                        f"正文出现禁显章节标题: {bad_body}" if bad_body else "无禁显章节"))
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

    # 7) 发明名称段六属性格式 (G8-0b; W04 机械化, 期望值来源=基准稿发明名称段)
    styles = _read(zf, "word/styles.xml") or ""
    check_title_format(doc, styles, reference_docx or DEFAULT_REFERENCE_DOCX,
                       invention_name, results)

    zf.close()

    # 输出
    print(f"== DOCX 骨架校验: {docx_path}  (stage={stage}) ==")
    n_fail = 0
    for level, name, ok, detail in results:
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
        print("结果: 机械项全部 PASS（标题格式/正文落位仍需 patent 人工核对一次）")
        return 0
    print(f"结果: {n_fail} 项 FAIL，需修正")
    return 1


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
            txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip()
            if txt == name:
                return i
    for i, p in enumerate(paras):
        txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip()
        if txt == "技术领域":
            return i - 1
    return None


def _extract_title_format(doc_xml: str, styles_xml: str, invention_name: str | None) -> dict | None:
    paras = re.findall(r"<w:p[ >].*?</w:p>", doc_xml, re.S)
    idx = _locate_title_para(paras, invention_name)
    if idx is None:
        return None
    return _parse_para_format(paras[idx], styles_xml)


def check_title_format(doc_xml, styles_xml, reference_docx, invention_name, results) -> None:
    """W04: 发明名称段六属性格式机械校验（G8-0b；期望值来源=参考基准稿发明名称段）.

    六属性（G8-0b）：宋体 / 三号(sz 32) / 加粗 / 居中 / 首行缩进0 / 1.5倍行距。
    期望值不硬编码——从 reference_docx 同一位置现场提取；reference 缺失/不可读/
    定位不到发明名称段 → 报"未执行"（WARN、不计 FAIL，但不得视为合规，口径同
    check_hard_rules 规则 31 缺 --invention-name）。
    """
    try:
        zf = zipfile.ZipFile(reference_docx)
        ref_doc = _read(zf, "word/document.xml") or ""
        ref_styles = _read(zf, "word/styles.xml") or ""
        zf.close()
    except (zipfile.BadZipFile, FileNotFoundError):
        results.append(("WARN", "发明名称段·格式校验未执行", True,
                        f"期望值基准稿不可读: {reference_docx}"))
        return
    ref_fmt = _extract_title_format(ref_doc, ref_styles, invention_name)
    if ref_fmt is None:
        results.append(("WARN", "发明名称段·格式校验未执行", True,
                        "基准稿中未定位到发明名称段（技术领域标题前一段）"))
        return
    target_fmt = _extract_title_format(doc_xml, styles_xml, invention_name)
    if target_fmt is None:
        results.append(("WARN", "发明名称段·格式校验未执行", True,
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
                        f"期望={ref_val!r} 实得={got!r}" if not ok else ""))

    def _no_first_line(fmt):
        fc, fl = fmt.get("firstLineChars"), fmt.get("firstLine")
        okc = fc is None or str(fc) in ("0", "0.0")
        okl = fl is None or str(fl) in ("0", "0.0")
        return okc and okl

    ok = _no_first_line(target_fmt)
    results.append(("FAIL", "发明名称段·首行缩进0", ok,
                    f"期望=无首行缩进 实得=firstLineChars={target_fmt.get('firstLineChars')!r} "
                    f"firstLine={target_fmt.get('firstLine')!r}" if not ok else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="专利模板 DOCX 骨架机械项一次性校验")
    ap.add_argument("docx", help="待校验的 .docx 文件")
    ap.add_argument("--stage", choices=["权要", "全文"], default="全文",
                    help="稿次：权要稿额外查可见页眉与正文禁显章节")
    ap.add_argument("--expect-sectpr", type=int, default=5, help="期望 sectPr 数（默认5）")
    ap.add_argument("--expect-headers", type=int, default=13, help="期望 header*.xml 数（默认13）")
    ap.add_argument("--reference-docx", default=None,
                    help="发明名称段六属性期望值来源基准稿（默认 G8-0b 基准 H2606029 全文1稿）")
    ap.add_argument("--invention-name", default=None,
                    help="发明名称全称，用于定位发明名称段；缺省时取技术领域标题前一段")
    args = ap.parse_args()
    sys.exit(check(args.docx, args.stage, args.expect_sectpr, args.expect_headers,
                   args.reference_docx, args.invention_name))

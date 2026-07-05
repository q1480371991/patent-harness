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


def _read(zf, name):
    try:
        return zf.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return None


def check(docx_path, stage, expect_sectpr, expect_headers):
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="专利模板 DOCX 骨架机械项一次性校验")
    ap.add_argument("docx", help="待校验的 .docx 文件")
    ap.add_argument("--stage", choices=["权要", "全文"], default="全文",
                    help="稿次：权要稿额外查可见页眉与正文禁显章节")
    ap.add_argument("--expect-sectpr", type=int, default=5, help="期望 sectPr 数（默认5）")
    ap.add_argument("--expect-headers", type=int, default=13, help="期望 header*.xml 数（默认13）")
    args = ap.parse_args()
    sys.exit(check(args.docx, args.stage, args.expect_sectpr, args.expect_headers))

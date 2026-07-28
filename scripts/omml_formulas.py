#!/usr/bin/env python3
"""公式原生 OMML 工具：LaTeX → WPS/Word 可编辑二维公式（块级 m:oMathPara）。

三个子命令（规则出处 global.md G6-1、docx-template.md G8-3、案例 C-DOCX-8）：

  gen           把 LaTeX 公式经 pandoc 转成可整段注入 document.xml 的
                `<w:p>…<m:oMathPara>…</w:p>` XML 段（已剥 pStyle、编号内嵌、
                `\\left/\\right` 归一为普通括号防 WPS `<m:d>` 留白）。
  fix-settings  把 DOCX 的 word/settings.xml 中 mathPr 重建为只含 m:mathFont
                （按平台选字体：macOS=STIX Two Math / Windows=Cambria Math /
                Linux=DejaVu Math TeX Gyre），清除 dispDef/defJc 等 WPS 降级源。
  check         公式健康体检：oMathPara 计数、空结构壳、`<m:d>` 告警、mathPr
                状态、样式链幽灵字体扫描（样式引用系统安全清单外字体时告警）。

设计约束：只用标准库 zipfile/re 直改 XML，不经 python-docx 重序列化，
保证模板包结构 byte 级无损（G8-1 骨架保护）。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- pandoc 探测

PANDOC_CANDIDATES = (
    Path.home() / ".local/bin/pandoc",
    Path.home() / "miniconda3/bin/pandoc",
    Path("/opt/homebrew/bin/pandoc"),
    Path("/usr/local/bin/pandoc"),
    Path("C:/Program Files/Pandoc/pandoc.exe"),
)


def find_pandoc() -> str | None:
    found = shutil.which("pandoc")
    if found:
        return found
    for cand in PANDOC_CANDIDATES:
        if cand.exists():
            return str(cand)
    return None


# ---------------------------------------------------------------- gen

# \left( … \right) 会生成可伸缩定界符对象 <m:d>，深嵌套时 WPS 渲染留白
# （实测案例见 docx-execution.md C-DOCX-8）。默认归一为普通括号字符。
_LEFT_RIGHT_DOT = re.compile(r"\\(?:left|right)\s*\.")
_LEFT_RIGHT = re.compile(r"\\(?:left|right)\s*")


def normalize_latex(latex: str) -> str:
    latex = _LEFT_RIGHT_DOT.sub("", latex)  # \left. / \right. 连点一起删
    latex = _LEFT_RIGHT.sub("", latex)      # 其余保留定界符字符本身
    return latex


_EQ_PARA = re.compile(r"<w:p\b[^>]*>.*?</w:p>", re.S)
_PSTYLE = re.compile(r"<w:pStyle\b[^>]*/>")


def gen_omml_paragraphs(items: list[dict], pandoc: str, keep_left_right: bool = False) -> list[dict]:
    """items: [{"latex": str, "number": int|None}, ...] → 附加 "xml" 字段返回。

    编号经 \\qquad\\text{(N)} 内嵌进 oMathPara（不得做成公式后的独立 run，
    否则 WPS 把整段降级成线性文本）。
    """
    md_parts = []
    for it in items:
        latex = it["latex"] if keep_left_right else normalize_latex(it["latex"])
        num = it.get("number")
        tail = f"\\qquad\\text{{({num})}}" if num is not None else ""
        md_parts.append(f"$${latex}{tail}$$\n")
    with tempfile.TemporaryDirectory() as tmp:
        md_path = Path(tmp) / "eq.md"
        docx_path = Path(tmp) / "eq.docx"
        md_path.write_text("\n".join(md_parts), encoding="utf-8")
        subprocess.run(
            [pandoc, "-f", "markdown", "-t", "docx", "-o", str(docx_path), str(md_path)],
            check=True,
        )
        import zipfile

        with zipfile.ZipFile(docx_path) as z:
            doc = z.read("word/document.xml").decode("utf-8")
    paras = [p for p in _EQ_PARA.findall(doc) if "m:oMathPara" in p]
    if len(paras) != len(items):
        raise RuntimeError(
            f"pandoc 生成公式段 {len(paras)} 与输入 {len(items)} 不一致，检查 LaTeX 语法"
        )
    out = []
    for it, p in zip(items, paras):
        # 剥 pStyle：不依赖目标文档样式表；居中由 oMathParaPr 自带，
        # 不得再给段落加 w:jc（会与 oMathParaPr 冲突导致 WPS 降级）。
        xml = _PSTYLE.sub("", p)
        out.append({**it, "xml": xml, "m_d_count": xml.count("<m:d>")})
    return out


# ---------------------------------------------------------------- fix-settings

PLATFORM_MATH_FONT = {
    "darwin": "STIX Two Math",       # 系统自带 /System/Library/Fonts/Supplemental/STIXTwoMath.otf
    "win32": "Cambria Math",         # 随 Office 分发，Windows 上最通用
}
DEFAULT_LINUX_MATH_FONT = "DejaVu Math TeX Gyre"


def pick_math_font() -> str:
    return PLATFORM_MATH_FONT.get(sys.platform, DEFAULT_LINUX_MATH_FONT)


_MATHPR = re.compile(r"<m:mathPr>.*?</m:mathPr>|<m:mathPr\s*/>", re.S)


def fix_settings(docx_path: Path, font: str) -> str:
    """重建 mathPr 为只含 mathFont。python-docx/WPS 模板默认 mathPr 携带的
    defJc/dispDef/intLim/naryLim 会让 WPS 把公式降级成线性文本。"""
    import zipfile

    with zipfile.ZipFile(docx_path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
    settings = data["word/settings.xml"].decode("utf-8")
    simplified = f'<m:mathPr><m:mathFont m:val="{font}"/></m:mathPr>'
    m = _MATHPR.search(settings)
    if m:
        # 先替换首个，再只对其后的余文清重复块（不能全局清，否则把刚替换的也删掉）
        head = settings[: m.start()] + simplified
        tail = _MATHPR.sub("", settings[m.end():])
        settings = head + tail
    else:
        # 无 mathPr：补上（需保证 m 命名空间已声明）
        root_m = re.search(r"<w:settings\b[^>]*>", settings)
        if root_m and "xmlns:m=" not in root_m.group(0):
            new_root = root_m.group(0).replace(
                ">",
                ' xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">',
                1,
            )
            settings = settings.replace(root_m.group(0), new_root, 1)
        settings = settings.replace("</w:settings>", simplified + "</w:settings>", 1)
    data["word/settings.xml"] = settings.encode("utf-8")
    tmp = docx_path.with_suffix(".tmp_omml.docx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, data[n])
    shutil.move(str(tmp), str(docx_path))
    return font


# ---------------------------------------------------------------- check

# 样式链字体安全清单：Word/WPS 常见系统字体。样式引用清单外字体时给告警——
# 公式正体 run 沿段落样式链解析西文字体，字体不存在时 WPS 数学环境不回退、
# 直接空白（实测元凶 Dutch801 Rm BT，见 C-DOCX-8）。
SAFE_FONTS = {
    "Times New Roman", "宋体", "SimSun", "新宋体", "NSimSun", "黑体", "SimHei",
    "仿宋", "FangSong", "楷体", "KaiTi", "微软雅黑", "Microsoft YaHei", "等线",
    "DengXian", "Calibri", "Cambria", "Cambria Math", "STIX Two Math",
    "DejaVu Math TeX Gyre", "Arial", "Courier New", "Symbol", "Wingdings",
    "Segoe UI", "Helvetica", "PingFang SC", "Songti SC", "STSong", "华文宋体",
    "PMingLiU", "MingLiU", "新細明體", "MS Mincho", "ＭＳ 明朝",
}
# 只扫 <w:rFonts> 元素内的字体属性（不能全文扫属性名：<w:lang w:eastAsia="zh-CN"/>
# 的语言代码会被误报成字体）
_RFONTS_TAG = re.compile(r"<w:rFonts\b[^>]*>")
_RFONT_ATTR = re.compile(r'w:(?:ascii|hAnsi|eastAsia|cs)="([^"]+)"')


def _referenced_fonts(xml: str) -> set:
    fonts = set()
    for tag in _RFONTS_TAG.findall(xml):
        fonts.update(_RFONT_ATTR.findall(tag))
    return fonts
_EMPTY_SHELL = re.compile(r"<m:(?:e|sub|sup|num|den)\s*/>")


def check_docx(docx_path: Path) -> dict:
    import zipfile

    with zipfile.ZipFile(docx_path) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        settings = z.read("word/settings.xml").decode("utf-8")
        try:
            styles = z.read("word/styles.xml").decode("utf-8")
        except KeyError:
            styles = ""

    mathpr_m = _MATHPR.search(settings)
    mathpr_xml = mathpr_m.group(0) if mathpr_m else ""
    inner = re.sub(r"^<m:mathPr>|</m:mathPr>$", "", mathpr_xml)
    mathpr_simplified = bool(mathpr_xml) and re.fullmatch(
        r'<m:mathFont m:val="[^"]+"\s*/>', inner.strip()
    ) is not None
    font_m = re.search(r'<m:mathFont m:val="([^"]+)"', mathpr_xml)

    referenced = _referenced_fonts(styles) | _referenced_fonts(doc)
    unknown_fonts = sorted(f for f in referenced if f not in SAFE_FONTS)

    result = {
        "file": str(docx_path),
        "omathpara_count": len(re.findall(r"<m:oMathPara\b", doc)),
        "omath_count": len(re.findall(r"<m:oMath\b", doc)) - len(re.findall(r"<m:oMathPara\b", doc)),
        "empty_shell_count": len(_EMPTY_SHELL.findall(doc)),
        "m_d_count": doc.count("<m:d>"),
        "mathpr_simplified": mathpr_simplified,
        "math_font": font_m.group(1) if font_m else None,
        "unknown_fonts": unknown_fonts,
        "formula_numbering_count": 0,
        "errors": [],
        "warnings": [],
    }
    if result["empty_shell_count"]:
        result["errors"].append(
            f"发现 {result['empty_shell_count']} 个空结构壳（<m:e/> 等），公式已损坏"
        )
    if result["m_d_count"]:
        result["warnings"].append(
            f"发现 {result['m_d_count']} 个可伸缩定界符 <m:d>（\\left\\right 产物），"
            "深嵌套时 WPS 渲染留白，建议归一为普通括号后重注（C-DOCX-8）"
        )
    if not result["mathpr_simplified"] and result["omathpara_count"]:
        result["warnings"].append(
            "mathPr 未简化（含 defJc/dispDef 等），WPS 可能把公式降级成线性文本；"
            "跑 fix-settings 修复"
        )
    if unknown_fonts:
        result["warnings"].append(
            "样式链引用了安全清单外字体: " + ", ".join(unknown_fonts)
            + "；若系统缺失该字体，WPS 公式正体部分会空白（幽灵字体，C-DOCX-8），须人工确认"
        )
    # 公式编号残留检测（专利说明书公式不加编号；G8-3 禁止 --number 内嵌或独立文本 run 编号）
    # 命中形态：① <m:t>...  (N)</m:t>（gen --number 经 pandoc 产出的全角空格+括号编号）
    #          ② <m:t>(N)</m:t> 紧跟在 oMath/oMathPara 末尾的独立编号文本 run
    #          ③ <m:t>...  </m:t> 末尾全角空格残留（编号被手动删除后留下的痕迹，提示公式段被改过）
    numbering_hits = re.findall(r"<m:t[^>]*>[^<]*  \(\d+\)[^<]*</m:t>", doc)
    numbering_hits += re.findall(r"<m:t[^>]*>\s*\(\d+\)\s*</m:t>", doc)
    result["formula_numbering_count"] = len(numbering_hits)
    if numbering_hits:
        result["errors"].append(
            f"发现 {len(numbering_hits)} 处公式编号残留（如 (1)(2)(3)），"
            "违反 G8-3「不得给公式段添加编号」与专利公式惯例；"
            "多为 omml_formulas.py gen 误传 --number 所致，去除 --number 重新生成并重注"
        )
    # 全角空格残留（编号被删但空格未清，告警级）
    u2001_tail = re.findall(r"<m:t[^>]*>[^<]*  [^<]*</m:t>", doc)
    u2001_tail = [t for t in u2001_tail if "  (" not in t]  # 排除已在编号errors计入的
    if u2001_tail:
        result["warnings"].append(
            f"发现 {len(u2001_tail)} 处公式末尾全角空格残留（U+2001），"
            "多为公式编号被手动删除后未清理干净；建议清理公式段末尾空白"
        )
    return result


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("gen", help="LaTeX → OMML 公式段 XML")
    p_gen.add_argument("--latex", action="append", default=[], help="LaTeX 源码，可重复传入多条")
    p_gen.add_argument("--number", action="append", type=int, default=[], help="与 --latex 顺序对应的公式编号（可省略）")
    p_gen.add_argument("--json", type=Path, help='批量输入: [{"latex": "...", "number": 1}, ...]')
    p_gen.add_argument("--out-dir", type=Path, help="每条公式写为 eq-<序号>.xml；缺省打印 JSON 到 stdout")
    p_gen.add_argument("--keep-left-right", action="store_true", help="保留 \\left\\right（默认归一为普通括号）")

    p_fix = sub.add_parser("fix-settings", help="mathPr 重建为仅 mathFont")
    p_fix.add_argument("docx", type=Path)
    p_fix.add_argument("--font", help="覆盖默认平台字体")

    p_chk = sub.add_parser("check", help="公式健康体检（JSON 报告）")
    p_chk.add_argument("docx", type=Path)

    args = parser.parse_args(argv)

    if args.cmd == "gen":
        pandoc = find_pandoc()
        if not pandoc:
            print(
                json.dumps({"error": "pandoc 不可用；按 check_env.py 提示安装后重试，"
                                     "或按 G6-1 回退为纯 LaTeX 文本写入并在完工报告注明"},
                           ensure_ascii=False)
            )
            return 3
        if args.json:
            items = json.loads(args.json.read_text(encoding="utf-8"))
        else:
            items = [
                {"latex": lx, "number": args.number[i] if i < len(args.number) else None}
                for i, lx in enumerate(args.latex)
            ]
        if not items:
            parser.error("gen 需要 --latex 或 --json 输入")
        results = gen_omml_paragraphs(items, pandoc, keep_left_right=args.keep_left_right)
        if args.out_dir:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            for i, r in enumerate(results, 1):
                name = f"eq-{r['number']}.xml" if r.get("number") is not None else f"eq-{i}.xml"
                (args.out_dir / name).write_text(r["xml"], encoding="utf-8")
            print(f"已写出 {len(results)} 条公式段到 {args.out_dir}")
        else:
            print(json.dumps(results, ensure_ascii=False, indent=1))
        residual = sum(r["m_d_count"] for r in results)
        if residual:
            print(f"警告: 仍含 {residual} 个 <m:d> 定界符对象，WPS 深嵌套可能留白", file=sys.stderr)
        return 0

    if args.cmd == "fix-settings":
        font = args.font or pick_math_font()
        fix_settings(args.docx, font)
        print(f"mathPr 已重建为仅 mathFont: {font}")
        return 0

    if args.cmd == "check":
        result = check_docx(args.docx)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 1 if result["errors"] else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

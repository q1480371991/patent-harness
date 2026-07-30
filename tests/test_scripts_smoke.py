from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

from docx import Document
from docx.enum.text import WD_COLOR_INDEX


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"


def run_script(script_name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), *map(str, args)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def run_script_allow_fail(script_name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), *map(str, args)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


GOOD_FULL_DRAFT_MD = """## 权利要求书

1.一种测试对象控制方法，其特征在于，包括：获取输入数据；根据输入数据确定中间结果；根据中间结果生成控制信号。

2.根据权利要求1所述的测试对象控制方法，其特征在于，所述获取输入数据，包括：读取传感器数据；对传感器数据滤波。

3.一种测试对象控制系统，包括存储器、处理器，其特征在于，所述处理器执行程序时实现权利要求1至2任一项所述的方法的步骤。

## 技术领域

本发明涉及测试领域。

## 背景技术

现有技术存在问题。

## 发明内容

本发明提供一种测试对象控制方法。

## 附图说明

图1为本发明实施例提供的测试对象控制方法流程示意图；

图2为本发明实施例提供的测试对象控制系统结构示意图。

## 具体实施方式

在步骤S11中，获取输入数据，包括：读取传感器数据；对传感器数据滤波。

在步骤S12中，根据输入数据确定中间结果。

在步骤S13中，根据中间结果生成控制信号。
"""


def add_minimal_comment(docx_path: Path, comment_text: str):
    tmp_path = docx_path.with_suffix(".tmp.docx")
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    ET.register_namespace("w", ns["w"])

    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
        root = ET.fromstring(zin.read("word/document.xml"))
        paragraph = root.find(".//w:p", ns)
        run = paragraph.find("w:r", ns)
        paragraph.insert(0, ET.Element(f"{{{ns['w']}}}commentRangeStart", {f"{{{ns['w']}}}id": "0"}))
        paragraph.insert(list(paragraph).index(run) + 1, ET.Element(f"{{{ns['w']}}}commentRangeEnd", {f"{{{ns['w']}}}id": "0"}))
        comment_ref_run = ET.Element(f"{{{ns['w']}}}r")
        comment_ref = ET.SubElement(comment_ref_run, f"{{{ns['w']}}}commentReference")
        comment_ref.set(f"{{{ns['w']}}}id", "0")
        paragraph.append(comment_ref_run)

        comments = ET.Element(f"{{{ns['w']}}}comments")
        comment = ET.SubElement(
            comments,
            f"{{{ns['w']}}}comment",
            {f"{{{ns['w']}}}id": "0", f"{{{ns['w']}}}author": "tester"},
        )
        p = ET.SubElement(comment, f"{{{ns['w']}}}p")
        r = ET.SubElement(p, f"{{{ns['w']}}}r")
        t = ET.SubElement(r, f"{{{ns['w']}}}t")
        t.text = comment_text

        for item in zin.infolist():
            if item.filename == "word/document.xml":
                zout.writestr(item, ET.tostring(root, encoding="utf-8", xml_declaration=True))
            else:
                zout.writestr(item, zin.read(item.filename))
        zout.writestr("word/comments.xml", ET.tostring(comments, encoding="utf-8", xml_declaration=True))

    shutil.move(tmp_path, docx_path)


def _find_pandoc():
    found = shutil.which("pandoc")
    if found:
        return found
    for cand in (
        Path.home() / ".local/bin/pandoc",
        Path.home() / "miniconda3/bin/pandoc",
        Path("/opt/homebrew/bin/pandoc"),
        Path("/usr/local/bin/pandoc"),
    ):
        if cand.exists():
            return str(cand)
    return None


PANDOC_AVAILABLE = _find_pandoc() is not None


class PatentScriptSmokeTests(unittest.TestCase):
    @unittest.skipUnless(PANDOC_AVAILABLE, "pandoc 不可用, 跳过公式 OMML 生成测试")
    def test_omml_formulas_gen_produces_block_omml(self):
        import json

        result = run_script(
            "omml_formulas.py", "gen",
            "--latex", r"Z_k=\mathrm{LN}(Z_{k-1}+\mathrm{ReLU}(x))",
            "--number", "12",
        )
        data = json.loads(result.stdout)
        self.assertEqual(len(data), 1)
        xml = data[0]["xml"]
        # 块级 oMathPara + 编号内嵌, WPS 才能渲染为可编辑二维公式 (G8-3)
        self.assertIn("m:oMathPara", xml)
        self.assertIn("(12)", xml)
        # pStyle 已剥离 (不依赖目标文档样式表); 无段落级居中 (由 oMathParaPr 承担)
        self.assertNotIn("pStyle", xml)
        self.assertNotIn('w:jc w:val="center"', xml)
        self.assertEqual(data[0]["m_d_count"], 0)

    @unittest.skipUnless(PANDOC_AVAILABLE, "pandoc 不可用, 跳过公式 OMML 生成测试")
    def test_omml_formulas_gen_normalizes_left_right(self):
        import json

        # \left( \right) 生成 <m:d> 可伸缩定界符, WPS 深嵌套渲染留白 (C-DOCX-8);
        # gen 默认归一为普通括号
        result = run_script(
            "omml_formulas.py", "gen",
            "--latex", r"y=\left(\frac{a}{b}\right)+\left|c\right|",
        )
        data = json.loads(result.stdout)
        self.assertEqual(data[0]["m_d_count"], 0)
        self.assertNotIn("<m:d>", data[0]["xml"])

    def test_omml_formulas_fix_settings_and_check(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "math.docx"
            doc = Document()
            doc.add_paragraph("正文")
            doc.save(docx_path)

            # python-docx 默认模板 mathPr 带 Cambria Math + defJc/dispDef 等降级源
            run_script("omml_formulas.py", "fix-settings", str(docx_path), "--font", "STIX Two Math")
            result = run_script("omml_formulas.py", "check", str(docx_path))
            data = json.loads(result.stdout)
            self.assertTrue(data["mathpr_simplified"])
            self.assertEqual(data["math_font"], "STIX Two Math")
            self.assertEqual(data["empty_shell_count"], 0)
            self.assertEqual(data["errors"], [])

    def test_native_formula_workflow_is_wired(self):
        global_text = (SKILL_DIR / "references" / "rules" / "global.md").read_text(encoding="utf-8")
        docx_text = (SKILL_DIR / "references" / "rules" / "docx-template.md").read_text(encoding="utf-8")
        case_text = (SKILL_DIR / "references" / "cases" / "docx-execution.md").read_text(encoding="utf-8")

        # G6-1 落盘策略: md 层仍写 LaTeX 源码, DOCX 层转原生 OMML
        self.assertIn("omml_formulas.py", global_text)
        self.assertIn("原生可编辑二维公式", global_text)
        # 执行层细则 G8-3 与案例 C-DOCX-8 存在且互相指向
        self.assertIn("G8-3", docx_text)
        self.assertIn("omml_formulas.py", docx_text)
        self.assertIn("C-DOCX-8", docx_text)
        self.assertIn("C-DOCX-8", case_text)
        self.assertIn("幽灵字体", case_text)
        self.assertTrue((SCRIPTS_DIR / "omml_formulas.py").exists())
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("omml_formulas.py", skill_text)

    def test_bundled_template_has_no_ghost_font(self):
        # 模板样式链引用系统不存在的字体 (如 Dutch801 Rm BT) 会让 WPS 公式
        # 正体部分空白 (C-DOCX-8 实测根因), 模板资产必须保持无幽灵字体
        template = SKILL_DIR / "assets" / "docx" / "专利撰写模板.docx"
        with zipfile.ZipFile(template) as z:
            styles = z.read("word/styles.xml").decode("utf-8")
        self.assertNotIn("Dutch801", styles)
        self.assertIn("Times New Roman", styles)

    def test_disclosure_docx_to_md_preserves_highlights_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docx_path = tmp_path / "disclosure.docx"
            md_path = tmp_path / "disclosure_annotated.md"

            doc = Document()
            para = doc.add_paragraph()
            para.add_run("普通内容 ")
            highlighted = para.add_run("关键创新步骤")
            highlighted.font.highlight_color = WD_COLOR_INDEX.YELLOW
            doc.save(docx_path)
            add_minimal_comment(docx_path, "该步骤必须进入权利要求1")

            result = run_script("disclosure_docx_to_md.py", "--input", docx_path, "--output", md_path)

            text = md_path.read_text(encoding="utf-8")
            self.assertIn("==关键创新步骤==", text)
            self.assertIn("批注 #0", text)
            self.assertIn("该步骤必须进入权利要求1", text)
            self.assertIn("highlights=1", result.stdout)
            self.assertIn("comments=1/1", result.stdout)

    def test_skill_frontmatter_and_bundled_template_paths_are_stable(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("name: patent", skill_text)
        self.assertIn("description: Use when", skill_text)
        self.assertTrue((SKILL_DIR / "assets" / "docx" / "专利撰写模板.docx").exists())
        self.assertIn("assets/docx/专利撰写模板.docx", skill_text)
        self.assertNotIn("assets/专利撰写模板.docx", skill_text)

    def test_claims_format_guidance_is_bundled_not_external_path(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        claims_text = (SKILL_DIR / "references" / "rules" / "claims.md").read_text(encoding="utf-8")
        reference_path = SKILL_DIR / "references" / "cases" / "claims-format-standard.md"

        self.assertTrue(reference_path.exists())
        self.assertIn("references/cases/claims-format-standard.md", skill_text)
        self.assertIn("references/cases/claims-format-standard.md", claims_text)
        self.assertNotIn("/Users/example/Desktop/Patent/第3-4课的案例资料", skill_text)
        self.assertNotIn("/Users/example/Desktop/Patent/第3-4课的案例资料", claims_text)

    def test_rules_have_no_self_referential_or_docx_boundary_residue(self):
        rules_text = (SKILL_DIR / "rules.md").read_text(encoding="utf-8")
        docx_text = (SKILL_DIR / "references" / "rules" / "docx-template.md").read_text(encoding="utf-8")

        self.assertNotIn("本文件是 `rules.md` 的分级重组与扩展版", rules_text)
        self.assertIn("当前唯一规则索引", rules_text)
        self.assertNotIn("可用 zipfile + xml.etree 直接读写", docx_text)
        self.assertIn("已显式加载官方 `docx` skill", docx_text)
        self.assertIn("不得替代 `docx` skill 的执行层", docx_text)
    def test_progressive_rules_files_exist_and_are_referenced(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        rules_text = (SKILL_DIR / "rules.md").read_text(encoding="utf-8")
        rule_files = [
            "global.md",
            "claims.md",
            "full-draft.md",
            "revision.md",
            "docx-template.md",
            "figures.md",
        ]

        for filename in rule_files:
            relative_path = f"references/rules/{filename}"
            self.assertTrue((SKILL_DIR / relative_path).exists(), relative_path)
            self.assertIn(relative_path, rules_text)

        self.assertIn("按阶段读取规则", skill_text)
        self.assertIn("references/rules/global.md", skill_text)

    def test_rules_index_is_lightweight(self):
        rules_text = (SKILL_DIR / "rules.md").read_text(encoding="utf-8")

        self.assertLess(len(rules_text.splitlines()), 180)
        self.assertIn("当前唯一规则索引", rules_text)
        self.assertNotIn("# 第一部分：全局规则", rules_text)
        self.assertNotIn("# 第二部分：局部规则", rules_text)
        self.assertNotIn("# 第三部分：最终交付前总自检", rules_text)

    def test_skill_uses_progressive_rule_loading(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertNotIn("必须阅读本目录下的 `rules.md`。它是本工作流的强制写作规范。", skill_text)
        self.assertIn("references/rules/global.md", skill_text)
        self.assertIn("references/rules/claims.md", skill_text)
        self.assertIn("references/rules/full-draft.md", skill_text)
        self.assertIn("references/rules/revision.md", skill_text)
        self.assertIn("references/rules/docx-template.md", skill_text)
        self.assertIn("references/rules/figures.md", skill_text)

    def test_split_rules_preserve_critical_constraints(self):
        global_text = (SKILL_DIR / "references" / "rules" / "global.md").read_text(encoding="utf-8")
        claims_text = (SKILL_DIR / "references" / "rules" / "claims.md").read_text(encoding="utf-8")
        full_text = (SKILL_DIR / "references" / "rules" / "full-draft.md").read_text(encoding="utf-8")
        revision_text = (SKILL_DIR / "references" / "rules" / "revision.md").read_text(encoding="utf-8")
        docx_text = (SKILL_DIR / "references" / "rules" / "docx-template.md").read_text(encoding="utf-8")
        figures_text = (SKILL_DIR / "references" / "rules" / "figures.md").read_text(encoding="utf-8")

        self.assertIn("技术链条闭合", global_text)
        self.assertIn("禁用或风险措辞", global_text)
        self.assertIn("公式、模型、阈值", global_text)

        self.assertIn("权利要求书规则", claims_text)
        self.assertIn("技术领域规则", claims_text)
        self.assertIn("背景技术规则", claims_text)
        self.assertIn("references/cases/claims-format-standard.md", claims_text)
        self.assertNotIn("说明书摘要规则", claims_text)
        self.assertNotIn("具体实施方式规则", claims_text)

        self.assertIn("说明书摘要规则", full_text)
        self.assertIn("发明内容规则", full_text)
        self.assertIn("具体实施方式规则", full_text)

        self.assertIn("权要返修", revision_text)
        self.assertIn("全文返修", revision_text)
        self.assertIn("留痕返修", revision_text)
        # 署名不再默认 Juventude，改为每次由用户提供
        self.assertIn("作者名不设默认值", revision_text)
        self.assertNotIn("默认作者名为 `Juventude`", revision_text)

        self.assertIn("sectPr", docx_text)
        self.assertIn("header*.xml", docx_text)
        self.assertIn("headerReference", docx_text)
        self.assertIn("不得替代 `docx` skill 的执行层", docx_text)

        self.assertIn("附图自动生成规则", figures_text)
        self.assertIn("图 1", figures_text)
        self.assertIn("Visio", figures_text)
    def test_audit_reinforcements_are_preserved(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        rules_text = (SKILL_DIR / "rules.md").read_text(encoding="utf-8")
        global_text = (SKILL_DIR / "references" / "rules" / "global.md").read_text(encoding="utf-8")
        claims_text = (SKILL_DIR / "references" / "rules" / "claims.md").read_text(encoding="utf-8")
        full_text = (SKILL_DIR / "references" / "rules" / "full-draft.md").read_text(encoding="utf-8")
        revision_text = (SKILL_DIR / "references" / "rules" / "revision.md").read_text(encoding="utf-8")
        docx_text = (SKILL_DIR / "references" / "rules" / "docx-template.md").read_text(encoding="utf-8")
        figures_text = (SKILL_DIR / "references" / "rules" / "figures.md").read_text(encoding="utf-8")

        self.assertIn("单一出处原则", rules_text)
        self.assertIn("唯一权威出处是 `references/rules/global.md` G2", rules_text)
        self.assertIn("所有阶段默认强制读取", global_text)
        self.assertNotIn("当前唯一强制规则文件", global_text)
        self.assertEqual(global_text.count("## 0. 规则分级总表"), 1)

        self.assertIn("输入对象 → 关键处理机制 → 中间结果 → 参与最终结果", global_text)
        self.assertIn("训练阶段的历史输入", global_text)
        self.assertIn("使用阶段的当前输入", global_text)
        self.assertIn("交底书 DOCX 转出的带批注 Markdown 统一命名", global_text)

        self.assertIn("背景技术默认写成 2–3 个自然段", claims_text)
        self.assertIn("第一段", claims_text)
        self.assertIn("第二段", claims_text)
        self.assertIn("第三段", claims_text)
        self.assertIn("两个相对独立且均有技术贡献", claims_text)
        self.assertIn("功能模块式系统/装置权", claims_text)
        self.assertIn("不得展开技术效果、实施步骤或背景缺陷", claims_text)

        self.assertIn("只控制最终可见文本", skill_text)
        self.assertIn("不删除、不重建非当前阶段分节锚点", docx_text)
        self.assertIn("非当前阶段模板槽位", docx_text)
        self.assertIn("后续阶段内容不得因权要一稿被全局清空", docx_text)
        self.assertIn("权要一稿/二稿/三稿最终 DOCX 可见页眉仅为", docx_text)
        self.assertIn("仍保留包内全部 `word/header*.xml`", docx_text)
        self.assertIn("案例性术语清理", skill_text)
        self.assertIn("后续阶段槽位保留不删", skill_text)

        self.assertIn("全文终稿目标约 1.5–2 万字", full_text)
        self.assertIn("render_patent_figure.py", figures_text)
        self.assertIn("insert_figures_docx.py", figures_text)
        self.assertIn("子流程图默认不画", figures_text)

        self.assertIn("同类问题", revision_text)
        self.assertIn("原稿、返修稿和 `comments.xml`", revision_text)
        self.assertIn("对应阶段规则文件", skill_text)

    def test_second_reaudit_alignment_fixes_are_preserved(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        global_text = (SKILL_DIR / "references" / "rules" / "global.md").read_text(encoding="utf-8")
        claims_text = (SKILL_DIR / "references" / "rules" / "claims.md").read_text(encoding="utf-8")
        full_text = (SKILL_DIR / "references" / "rules" / "full-draft.md").read_text(encoding="utf-8")
        revision_text = (SKILL_DIR / "references" / "rules" / "revision.md").read_text(encoding="utf-8")
        docx_text = (SKILL_DIR / "references" / "rules" / "docx-template.md").read_text(encoding="utf-8")
        figures_text = (SKILL_DIR / "references" / "rules" / "figures.md").read_text(encoding="utf-8")

        self.assertNotIn("由用户自行编译后粘贴到 DOCX", global_text)
        self.assertIn("一律写成 **LaTeX 源码**", global_text)
        self.assertIn("LaTeX 源码", skill_text)
        self.assertIn("权利要求中不写公式", global_text)
        self.assertIn("解释每个参数", global_text)

        self.assertIn("构造保证", figures_text)
        self.assertIn("替换语义", figures_text)
        self.assertIn("重新生成", figures_text)
        self.assertIn("用户自备", figures_text)

        for row in [
            "| 全局 1级规则 | 所有块、所有阶段 |",
            "| 全局 2级规则 | 所有块、所有阶段 |",
            "| 局部 1级规则 | 某一块 |",
            "| 局部 2级规则 | 某一块 |",
        ]:
            self.assertEqual(global_text.count(row), 1, row)

        self.assertNotIn("方法 ≤7 条", claims_text)
        self.assertIn("方法权通常写到权要 7 左右", claims_text)
        self.assertIn("可扩展方法权数量或压缩系统", claims_text)
        self.assertIn("系统/装置独权默认采用计算机设备式写法", claims_text)
        self.assertIn("计算机可读存储介质权", claims_text)
        self.assertNotIn("系统/装置独权及其从权的结构", skill_text)

        self.assertIn("构建模型", global_text)
        self.assertIn("生成策略", global_text)
        self.assertIn("补偿信号", global_text)
        self.assertIn("进行评估", global_text)
        self.assertIn("输入参数 → 控制参数 → 初步控制信号", global_text)

        self.assertIn("交付类型：留痕稿/干净稿", skill_text)
        self.assertIn("默认不清除批注", revision_text)
        self.assertIn("最新已审权要 DOCX", skill_text)
        self.assertIn("候选不唯一", skill_text)
        self.assertIn("document-skills:docx", skill_text)
        self.assertIn("docx` skill", docx_text)

        self.assertIn("未来槽位锚点仍可定位", docx_text)
        self.assertIn("保留 XML 锚点", docx_text)
        self.assertIn("不得删除整节", docx_text)
        self.assertIn("不得全局清空 body", docx_text)

        self.assertIn("无方法独立权要", full_text)
        self.assertIn("主要保护主题", full_text)
        self.assertIn("附图说明一致", full_text)
        self.assertIn("句末标点", figures_text)
        self.assertIn("分号分句", figures_text)

    def test_dedup_and_segmented_write_rules_are_preserved(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        rules_text = (SKILL_DIR / "rules.md").read_text(encoding="utf-8")
        global_text = (SKILL_DIR / "references" / "rules" / "global.md").read_text(encoding="utf-8")
        full_text = (SKILL_DIR / "references" / "rules" / "full-draft.md").read_text(encoding="utf-8")
        docx_text = (SKILL_DIR / "references" / "rules" / "docx-template.md").read_text(encoding="utf-8")
        figures_text = (SKILL_DIR / "references" / "rules" / "figures.md").read_text(encoding="utf-8")

        # 单一出处原则与指针化
        self.assertIn("单一出处原则", rules_text)
        self.assertIn("仅适用于**权要一稿**和**全文一稿**", global_text)

        # 全文稿分块撰写法：Markdown 层 + DOCX 注入层
        self.assertIn("全文稿分块撰写法", full_text)
        self.assertIn("不得一次性生成全文长文", global_text)
        self.assertIn("一次只注入一个内容块", full_text)
        self.assertIn("有效 checkpoint", full_text)
        self.assertIn("要求用户手动复制粘贴进 Word", full_text)
        self.assertIn("全文稿分块撰写法", skill_text)

        # G8-0 分节对照表与 G8-0b 标题格式
        self.assertIn("分节↔页眉↔正文内容对照表", docx_text)
        self.assertIn("G8-0b", docx_text)
        self.assertIn("顶格", docx_text)
        self.assertIn("<w:b/>", docx_text)
        self.assertIn("五个章节标题", docx_text)

        # 摘要附图唯一出处对齐 full-draft L5
        self.assertIn("full-draft.md` L5", figures_text)
        self.assertNotIn("摘要附图默认 = 图 1", figures_text)

        # 公式 LaTeX 源码交付
        self.assertIn("不带 `$`/`$$` 定界符", global_text)

        # 案件 docs/ 目录与 skill 自身 docs/ 消歧
        self.assertIn("docs/` 子目录", global_text)
        self.assertIn("技能文档目录", global_text)


    def test_extract_structure_and_cross_block_pass_on_conforming_draft(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "全文稿.md"
            md_path.write_text(GOOD_FULL_DRAFT_MD, encoding="utf-8")

            result = run_script("extract_structure.py", "--md", md_path, "--stage", "full-draft")
            data = json.loads(result.stdout)
            self.assertTrue(data["extraction_ok"])
            claim1 = next(i for i in data["claims"]["items"] if i["num"] == 1)
            self.assertEqual(claim1["step_count"], 3)
            self.assertEqual(data["main_steps"]["ids"], ["S11", "S12", "S13"])
            self.assertEqual(data["figures"]["nums"], [1, 2])
            claim3 = next(i for i in data["claims"]["items"] if i["num"] == 3)
            self.assertEqual(claim3["range_refs"], [[1, 2]])

            result = run_script("check_cross_block.py", "--md", md_path, "--stage", "full-draft")
            data = json.loads(result.stdout)
            self.assertEqual(data["violation_count"], 0)

    def test_check_cross_block_catches_step_mismatch_and_bad_dependency(self):
        import json

        bad_md = GOOD_FULL_DRAFT_MD.replace(
            "在步骤S13中，根据中间结果生成控制信号。\n", ""
        ).replace("根据权利要求1所述", "根据权利要求9所述")
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "全文稿.md"
            md_path.write_text(bad_md, encoding="utf-8")

            result = run_script_allow_fail(
                "check_cross_block.py", "--md", md_path, "--stage", "full-draft"
            )
            self.assertNotEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            checks = {v["check"] for v in data["violations"]}
            self.assertIn("X1", checks)  # 权 1 分句 3 vs 主步骤 2
            self.assertIn("X3", checks)  # 依附了不存在的权要 9

    def test_check_cross_block_x7_dep_quote_verbatim(self):
        import json

        good_md = """## 权利要求书

1.一种测试控制方法，其特征在于，包括：获取输入数据；根据输入数据确定中间结果；根据中间结果生成控制信号。

2.根据权利要求1所述的测试控制方法，其特征在于，所述根据输入数据确定中间结果，包括：对输入数据滤波；确定中间结果。

## 技术领域

本发明涉及测试领域。

## 背景技术

现有技术存在问题。
"""

        def run_case(md_text):
            with tempfile.TemporaryDirectory() as tmp:
                md_path = Path(tmp) / "权要稿.md"
                md_path.write_text(md_text, encoding="utf-8")
                result = run_script_allow_fail(
                    "check_cross_block.py", "--md", md_path, "--stage", "claims-draft"
                )
                data = json.loads(result.stdout)
                return [v for v in data["violations"] if v["check"] == "X7"]

        # 规范引用 (仅去连接词/加"所述") 通过
        self.assertEqual(run_case(good_md), [])
        # 改动词 (根据→对): 引用句不再是权 1 原文连续子串, X7 FAIL
        bad_verb = good_md.replace(
            "所述根据输入数据确定中间结果，包括", "所述对输入数据确定中间结果，包括"
        )
        self.assertEqual(len(run_case(bad_verb)), 1)
        # 引用句内附加原句没有的限定, X7 FAIL
        bad_extra = good_md.replace(
            "所述根据输入数据确定中间结果，包括",
            "所述根据输入数据确定中间结果，其中所述中间结果为预设模型输出，包括",
        )
        self.assertEqual(len(run_case(bad_extra)), 1)

    def test_extract_structure_fails_hard_on_nonstandard_writing(self):
        import json

        bad_md = "## 权利要求书\n\n1.一种测试方法，包括：步骤甲；步骤乙。\n"
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "权要稿.md"
            md_path.write_text(bad_md, encoding="utf-8")

            result = run_script_allow_fail(
                "extract_structure.py", "--md", md_path, "--stage", "claims-draft"
            )
            self.assertEqual(result.returncode, 2)
            data = json.loads(result.stdout)
            self.assertFalse(data["extraction_ok"])
            self.assertTrue(any("其特征在于" in e for e in data["extraction_errors"]))

    def test_split_workflow_full_draft_uses_claims_md(self):
        import json

        # 真实工作流: 全文稿.md 不含权利要求书 (冻结在权要稿.md)
        idx = GOOD_FULL_DRAFT_MD.index("## 技术领域")
        claims_part = GOOD_FULL_DRAFT_MD[:idx]
        full_part = GOOD_FULL_DRAFT_MD[idx:]
        with tempfile.TemporaryDirectory() as tmp:
            claims_path = Path(tmp) / "权要稿.md"
            full_path = Path(tmp) / "全文稿.md"
            claims_path.write_text(claims_part, encoding="utf-8")
            full_path.write_text(full_part, encoding="utf-8")

            # 不传 --claims-md: 报结构错误并提示传入
            result = run_script_allow_fail(
                "check_cross_block.py", "--md", full_path, "--stage", "full-draft"
            )
            self.assertNotEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertTrue(any("--claims-md" in e for e in data["extraction_errors"]))

            # 传 --claims-md: 全部通过
            result = run_script(
                "check_cross_block.py", "--md", full_path, "--stage", "full-draft",
                "--claims-md", claims_path,
            )
            data = json.loads(result.stdout)
            self.assertEqual(data["violation_count"], 0)
            self.assertEqual(data["structure"]["claims_source"], "claims_md")

            # 分离式全文稿跑第一类脚本: 不误报权要缺失/章节缺失
            result = run_script_allow_fail(
                "check_hard_rules.py", "--md", full_path, "--stage", "full-draft", "--json"
            )
            hard = json.loads(result.stdout)
            msgs = " ".join(v["message"] for v in hard["violations"])
            self.assertNotIn("未找到权要 1", msgs)
            self.assertNotIn("缺少章节: 权利要求书", msgs)

    def test_check_cross_block_flags_merged_step_lead(self):
        import json

        merged_md = GOOD_FULL_DRAFT_MD.replace(
            "在步骤S12中，根据输入数据确定中间结果。\n\n在步骤S13中，根据中间结果生成控制信号。\n",
            "在步骤S12至步骤S13中，根据输入数据确定中间结果，再根据中间结果生成控制信号。\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "全文稿.md"
            md_path.write_text(merged_md, encoding="utf-8")

            result = run_script_allow_fail(
                "check_cross_block.py", "--md", md_path, "--stage", "full-draft"
            )
            self.assertNotEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            checks = {v["check"] for v in data["violations"]}
            self.assertIn("X4", checks)   # 合并展开被点名
            self.assertNotIn("X1", checks)  # 覆盖数 3 == 分句数 3, 不误报数量

    def test_skill_wires_cross_block_check_into_gates(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("scripts/check_cross_block.py", skill_text)
        self.assertIn("structure_check_result", skill_text)
        # 多路审查: SKILL.md 编排四个 auditor 契约
        for name in ("claims-auditor", "content-auditor", "impl-auditor", "global-auditor"):
            self.assertIn(name, skill_text)
        # 各契约消费 structure_check_result 且引用脚本
        for fname in ("claims-auditor.md", "content-auditor.md", "impl-auditor.md", "global-auditor.md"):
            text = (SKILL_DIR / "agents" / fname).read_text(encoding="utf-8")
            self.assertIn("structure_check_result", text)
            self.assertIn("check_hard_rules", text)
        # 专审契约有必审语义项清单
        for fname in ("claims-auditor.md", "content-auditor.md", "impl-auditor.md"):
            text = (SKILL_DIR / "agents" / fname).read_text(encoding="utf-8")
            self.assertIn("必审语义项", text)

    def test_signature_not_defaulted_to_juventude(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        revision_text = (SKILL_DIR / "references" / "rules" / "revision.md").read_text(encoding="utf-8")

        # 署名不设默认值，每次由用户提供
        self.assertIn("不设默认值", skill_text)
        self.assertIn("<用户指定署名>", skill_text)
        # 正文流程不再把 Juventude 作为默认署名硬写
        self.assertNotIn("默认 `Juventude`", skill_text)
        self.assertNotIn("署 Juventude", skill_text)
        self.assertNotIn("默认作者名为 `Juventude`", revision_text)

    def test_innovation_points_driven_by_disclosure_annotations(self):
        global_text = (SKILL_DIR / "references" / "rules" / "global.md").read_text(encoding="utf-8")
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        # 创新点以批注圈定为准，不自行判断
        self.assertIn("创新点以交底书批注为准", global_text)
        self.assertIn("不自行另判", skill_text)
        # disclosure-analyst 已废弃：事实提纲由主 agent 深读时亲自产出，批注驱动条款落在 SKILL.md 主流程
        self.assertFalse((SKILL_DIR / "agents" / "disclosure-analyst.md").exists())
        self.assertIn("批注圈定的创新点", skill_text)
        self.assertIn("优先审查要求（批注）", skill_text)

    def test_highlight_is_not_a_workflow_rule(self):
        global_text = (SKILL_DIR / "references" / "rules" / "global.md").read_text(encoding="utf-8")

        self.assertNotIn("高亮", global_text)
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("高亮", skill_text)

    def test_delivery_filename_uses_writer_directory(self):
        global_text = (SKILL_DIR / "references" / "rules" / "global.md").read_text(encoding="utf-8")

        self.assertIn("`夏晓贝/` 和 `王培元/`", global_text)
        # 现行 G1-1: 对外交付用全称命名, 禁止简写与状态后缀
        self.assertIn("`案件号-稿次-作者-发明题目全称.docx`", global_text)
        self.assertIn("不得使用 `<撰写者>-<稿次>.docx` 简写", global_text)
        self.assertIn("不得加 `-留痕` 等状态后缀", global_text)
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("案件号-权要1稿-作者-发明题目全称.docx", skill_text)

    def test_a_paradigm_anchor_matches_extractor(self):
        """L8-0 展开段入口句锚点与 extract_structure.py 的主步骤正则互相匹配(防规则句面与脚本漂移)。"""
        full_draft_text = (SKILL_DIR / "references" / "rules" / "full-draft.md").read_text(encoding="utf-8")
        self.assertIn("在步骤Sxx中，〔复述权1第xx分句原文〕，包括：", full_draft_text)
        extractor_src = (SKILL_DIR / "scripts" / "extract_structure.py").read_text(encoding="utf-8")
        self.assertIn("在步骤S", extractor_src)

    def test_slimming_regression_guards(self):
        """三项瘦身 + 增量复核的回归保护：防止改动回退成整篇传规则/全量重审。"""
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        scoring_text = (SKILL_DIR / "references" / "rules" / "scoring.md").read_text(encoding="utf-8")

        # 1) scoring 摘录已实体化为静态文件并按路径传入，不整篇传卡
        self.assertIn("不整篇传入任何 auditor", scoring_text)
        for route in ("claims", "content", "impl", "global"):
            self.assertTrue(
                (SKILL_DIR / "references" / "rules" / f"scoring-{route}.md").exists(),
                f"scoring-{route}.md 静态摘录缺失",
            )
        self.assertIn("scoring_excerpt_path", skill_text)
        self.assertNotIn("scoring_rules_content", skill_text)
        self.assertNotIn("scoring_excerpt_content", skill_text)

        # 2) 规则一律传路径：四路契约用 *_path 字段且白名单放行契约点名路径
        for name in ("claims-auditor", "content-auditor", "impl-auditor", "global-auditor"):
            contract = (SKILL_DIR / "agents" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("scoring_excerpt_path", contract, name)
            self.assertNotIn("_content` |", contract, f"{name} 仍有内容内联字段")
            # 3) 增量复核：四路契约均支持 reaudit_context
            self.assertIn("reaudit_context", contract, name)
        self.assertIn("增量复核模式", skill_text)
        self.assertNotIn("恒重调", skill_text)

        # 4) facts.md 由主 agent 深读时亲自产出
        self.assertIn("docs/facts.md", skill_text)

        # 5) 闸门命令带 --md；权要基准回写条款存在
        self.assertNotIn("check_hard_rules.py <", skill_text)
        self.assertIn("回写更新 `docs/权要稿.md`", skill_text)
        self.assertIn("权要联动回写", skill_text)


    def test_check_env_runs_stdlib_only_and_reports_deps(self):
        import json

        # 自检器必须只用标准库 (否则"检查依赖的工具自己缺依赖"会死锁):
        # 用空 site (-S) + 清空 PYTHONPATH 剥离第三方包路径来近似"纯净解释器".
        import os

        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-S", str(SCRIPTS_DIR / "check_env.py"), "--json"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, check=False,
        )
        # 脚本本身不能因为 import 第三方失败而崩溃: returncode 只应是
        # 0 (必需项齐) 或 缺失必需项数; -S 剥离 site 会让 pip 类必需项不可见.
        # 不锁具体数值 (必需项清单会演进, 如新增 Pillow), 断言 rc == 报告的缺失数.
        data = json.loads(proc.stdout)  # 崩溃则这里抛 JSONDecodeError / stdout 为空
        missing_required = sum(
            1 for c in data["checks"] if c["required"] and c["ok"] is False
        )
        self.assertEqual(
            proc.returncode, missing_required,
            msg=f"check_env 异常崩溃或退出码失真: {proc.stderr[-300:]}",
        )
        names = {c["name"] for c in data["checks"]}
        self.assertIn("python-docx", names)
        self.assertIn("pandoc", names)
        # 分类正确: python-docx 属可自动装的 pip 类, pandoc 属可选
        docx_check = next(c for c in data["checks"] if c["name"] == "python-docx")
        self.assertEqual(docx_check["category"], "pip")
        self.assertTrue(docx_check["auto_installable"])
        pandoc_check = next(c for c in data["checks"] if c["name"] == "pandoc")
        self.assertFalse(pandoc_check["required"])  # pandoc 为可选

    def test_skill_wires_env_check_into_onboarding(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("接入前环境自检", skill_text)
        self.assertIn("scripts/check_env.py", skill_text)
        self.assertTrue((SKILL_DIR / "docs" / "install.md").exists())

    def test_check_env_includes_docx_plugin_check(self):
        import json

        # 单宿主 (claude): docx 插件检测项恒在, python-docx 同为必需 pip 项
        r = run_script_allow_fail("check_env.py", "--json")
        d = json.loads(r.stdout)
        names = {c["name"] for c in d["checks"]}
        self.assertTrue(any("document-skills:docx" in n for n in names))
        self.assertTrue(any(c["name"] == "python-docx" for c in d["checks"]))

    def test_single_host_no_codex_residue(self):
        # 2026-07-30 起 codex 分支删除, 仅维护 claude 单宿主; 跨宿主适配层不得回流
        self.assertFalse((SKILL_DIR / "docs" / "porting.md").exists())
        self.assertFalse((SKILL_DIR / "agents" / "openai.yaml").exists())
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("Codex", skill_text)
        for fname in ("global-auditor.md", "claims-auditor.md", "content-auditor.md", "impl-auditor.md"):
            auditor_text = (SKILL_DIR / "agents" / fname).read_text(encoding="utf-8")
            self.assertNotIn("跨宿主", auditor_text)
            self.assertNotIn("Codex", auditor_text)


class FigureScriptsSmokeTest(unittest.TestCase):
    """render_patent_figure.py + insert_figures_docx.py 冒烟：权要稿 → PNG → 注入 XML."""

    CLAIMS_MD = (
        "# 测试权要稿\n\n## 权利要求书\n\n"
        "1.一种测试数据处理方法，其特征在于，包括：\n\n"
        "采集测试输入数据，得到输入序列；\n\n"
        "对所述输入序列进行特征提取，得到特征向量；\n\n"
        "根据所述特征向量生成测试处理指令。\n\n"
        "2.根据权利要求1所述的测试数据处理方法，其特征在于，包括：省略。\n"
    )

    MINIMAL_SECT = (
        "    <w:p>\n      <w:pPr>\n        <w:sectPr>\n"
        '          <w:pgSz w:w="11906" w:h="16838"/>\n'
        "        </w:sectPr>\n      </w:pPr>\n    </w:p>\n"
    )

    MINIMAL_DOC = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">\n'
        "  <w:body>\n"
        + MINIMAL_SECT * 4
        + "    <w:sectPr>\n"
        '      <w:pgSz w:w="11906" w:h="16838"/>\n'
        "    </w:sectPr>\n"
        "  </w:body>\n"
        "</w:document>\n"
    )

    MINIMAL_RELS = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>\n'
    )

    MINIMAL_CT = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/></Types>\n'
    )

    def test_render_then_insert_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            claims = tmp / "权要稿.md"
            claims.write_text(self.CLAIMS_MD, encoding="utf-8")
            png = tmp / "figure-1.png"
            result = run_script(
                "render_patent_figure.py", "--claims-md", claims, "--output", png
            )
            self.assertTrue(png.exists())
            self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertIn("S11", result.stdout)

            unpacked = tmp / "unpacked"
            (unpacked / "word" / "_rels").mkdir(parents=True)
            (unpacked / "word" / "document.xml").write_text(
                self.MINIMAL_DOC, encoding="utf-8"
            )
            (unpacked / "word" / "_rels" / "document.xml.rels").write_text(
                self.MINIMAL_RELS, encoding="utf-8"
            )
            (unpacked / "[Content_Types].xml").write_text(
                self.MINIMAL_CT, encoding="utf-8"
            )
            run_script("insert_figures_docx.py", unpacked, "--png", png)

            doc = (unpacked / "word" / "document.xml").read_text(encoding="utf-8")
            self.assertEqual(doc.count("<w:drawing>"), 2)  # 分节2 + 分节5
            self.assertIn(">图1</w:t>", doc)  # 分节5 图题
            rels = (unpacked / "word" / "_rels" / "document.xml.rels").read_text(
                encoding="utf-8"
            )
            self.assertIn("media/image1.png", rels)
            self.assertTrue((unpacked / "word" / "media" / "image1.png").exists())
            ct = (unpacked / "[Content_Types].xml").read_text(encoding="utf-8")
            self.assertIn('Extension="png"', ct)

    def test_render_rejects_single_clause_claim(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            claims = tmp / "权要稿.md"
            claims.write_text(
                "## 权利要求书\n\n1.一种测试系统，其特征在于，包括：处理器。\n",
                encoding="utf-8",
            )
            result = run_script_allow_fail(
                "render_patent_figure.py",
                "--claims-md", claims, "--output", tmp / "figure-1.png",
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()

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

# 单内核 + 薄适配层: core 测试在两个适配分支都要能跑.
# 两个宿主分支的入口文件都叫 SKILL.md, 但内容不同——Claude 范式 vs Codex 范式.
# 校验 Claude 范式专属内容的断言, 只在"当前 SKILL.md 是 Claude 范式"时跑,
# 否则跳过(不是失败). 判据用 Codex 范式没有、Claude 范式必有的锚点串.
_skill_md = SKILL_DIR / "SKILL.md"
_skill_text = _skill_md.read_text(encoding="utf-8") if _skill_md.exists() else ""
# core(subagent) 分支与 claude 分支的 SKILL.md 是 Claude 范式(含"接入前环境自检"段);
# codex 分支的 SKILL.md 是 Codex 适配层(含"Codex 适配层"标题, 无该段).
CLAUDE_SKILL = "接入前环境自检" in _skill_text and "Codex 适配层" not in _skill_text
CODEX_SKILL = "Codex 适配层" in _skill_text
AGENTS_MD_PRESENT = (SKILL_DIR / "AGENTS.md").exists()


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


class PatentScriptSmokeTests(unittest.TestCase):
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

    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
    def test_skill_frontmatter_and_bundled_template_paths_are_stable(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("name: patent", skill_text)
        self.assertIn("description: Use when", skill_text)
        self.assertTrue((SKILL_DIR / "assets" / "docx" / "专利撰写模板.docx").exists())
        self.assertIn("assets/docx/专利撰写模板.docx", skill_text)
        self.assertNotIn("assets/专利撰写模板.docx", skill_text)

    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
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
    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
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

    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
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

        self.assertIn("说明书附图设计规则", figures_text)
        self.assertIn("图 1", figures_text)
        self.assertIn("Visio", figures_text)
    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
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
        self.assertIn("存在方法独立权要时必备", figures_text)
        self.assertIn("存在功能模块式系统/装置独权或系统侧独立结构创新时必备", figures_text)
        self.assertIn("从对应子步骤句末结果性表达中提取产物名", figures_text)

        self.assertIn("同类问题", revision_text)
        self.assertIn("原稿、返修稿和 `comments.xml`", revision_text)
        self.assertIn("对应阶段规则文件", skill_text)

    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
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

        self.assertIn("计算机设备式系统/装置权", figures_text)
        self.assertIn("功能模块式系统/装置独权", figures_text)
        self.assertIn("不机械生成业务模块式系统图", figures_text)
        self.assertIn("计算机设备结构示意图", figures_text)

        for row in [
            "| 全局 1级规则 | 所有块、所有阶段 |",
            "| 全局 2级规则 | 所有块、所有阶段 |",
            "| 局部 1级规则 | 某一块 |",
            "| 局部 2级规则 | 某一块 |",
        ]:
            self.assertEqual(global_text.count(row), 1, row)

        self.assertNotIn("方法 ≤7 条", claims_text)
        self.assertIn("方法权通常写到权要 7 左右", claims_text)
        self.assertIn("可扩展方法权数量或压缩系统/装置从权数量", claims_text)
        self.assertIn("计算机设备式系统/装置独权", claims_text)
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
        self.assertIn("附图设计一致", full_text)
        self.assertIn("句末标点", figures_text)
        self.assertIn("分号/句号", figures_text)

    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
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

    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
    def test_skill_wires_cross_block_check_into_gates(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        auditor_text = (SKILL_DIR / "agents" / "rule-auditor.md").read_text(encoding="utf-8")

        self.assertIn("scripts/check_cross_block.py", skill_text)
        self.assertIn("structure_check_result", skill_text)
        self.assertIn("structure_check_result", auditor_text)
        self.assertIn("check_cross_block.py", auditor_text)
        self.assertIn("语义项必审清单", auditor_text)

    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
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

    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
    def test_innovation_points_driven_by_disclosure_annotations(self):
        global_text = (SKILL_DIR / "references" / "rules" / "global.md").read_text(encoding="utf-8")
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        analyst_text = (SKILL_DIR / "agents" / "disclosure-analyst.md").read_text(encoding="utf-8")

        # 创新点以批注圈定为准，不自行判断
        self.assertIn("创新点以交底书批注为准", global_text)
        self.assertIn("不自行另判", skill_text)
        self.assertIn("批注圈定的创新点", analyst_text)
        self.assertIn("优先审查要求（批注）", analyst_text)


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
        # 0 (必需项齐) 或 缺失必需项数; -S 剥离 site 会让 python-docx 不可见,
        # 故这里只断言"未异常崩溃"(<2 且能产出合法 JSON), 不锁具体值.
        self.assertLess(proc.returncode, 2, msg=f"check_env 异常崩溃: {proc.stderr[-300:]}")
        data = json.loads(proc.stdout)  # 崩溃则这里抛 JSONDecodeError
        names = {c["name"] for c in data["checks"]}
        self.assertIn("python-docx", names)
        self.assertIn("pandoc", names)
        # 分类正确: python-docx 属可自动装的 pip 类, pandoc 属可选
        docx_check = next(c for c in data["checks"] if c["name"] == "python-docx")
        self.assertEqual(docx_check["category"], "pip")
        self.assertTrue(docx_check["auto_installable"])
        pandoc_check = next(c for c in data["checks"] if c["name"] == "pandoc")
        self.assertFalse(pandoc_check["required"])  # pandoc 为可选

    @unittest.skipUnless(CLAUDE_SKILL, "当前 SKILL.md 非 Claude 范式(codex 分支), 跳过 Claude 专属断言")
    def test_skill_wires_env_check_into_onboarding(self):
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("接入前环境自检", skill_text)
        self.assertIn("scripts/check_env.py", skill_text)
        self.assertTrue((SKILL_DIR / "docs" / "install.md").exists())

    def test_check_env_host_codex_skips_docx_plugin(self):
        import json

        # Claude 宿主: 含 docx 插件检测项
        r_claude = run_script_allow_fail("check_env.py", "--host", "claude", "--json")
        d_claude = json.loads(r_claude.stdout)
        names_claude = {c["name"] for c in d_claude["checks"]}
        self.assertTrue(any("document-skills:docx" in n for n in names_claude))

        # Codex 宿主: 跳过 docx 插件 (由 python-docx 直连)
        r_codex = run_script_allow_fail("check_env.py", "--host", "codex", "--json")
        d_codex = json.loads(r_codex.stdout)
        names_codex = {c["name"] for c in d_codex["checks"]}
        self.assertFalse(any("document-skills:docx" in n for n in names_codex))
        self.assertEqual(d_codex["host"], "codex")
        # python-docx 两端都在 (Codex 的 DOCX 能力由它提供)
        self.assertTrue(any(c["name"] == "python-docx" for c in d_codex["checks"]))

    def test_dual_host_adapter_layer_present(self):
        # 单内核 + 薄适配层: porting 指南属 core 恒在; 入口文件都叫 SKILL.md
        # 但内容分 Claude 范式 / Codex 范式. 当前分支必属其一.
        self.assertTrue((SKILL_DIR / "docs" / "porting.md").exists())
        self.assertTrue(
            CLAUDE_SKILL or CODEX_SKILL,
            msg="SKILL.md 必须是 Claude 范式或 Codex 范式之一",
        )
        # Codex 范式 SKILL.md: 校验其指向共享内核并声明 rule-auditor 降级自查
        if CODEX_SKILL:
            self.assertIn("references/", _skill_text)
            self.assertIn("scripts/", _skill_text)
            self.assertIn("自查", _skill_text)
            self.assertIn("--host codex", _skill_text)
            self.assertTrue((SKILL_DIR / "agents" / "openai.yaml").exists())
        # rule-auditor 契约含跨宿主说明 (属 core, 两分支恒在)
        auditor_text = (SKILL_DIR / "agents" / "rule-auditor.md").read_text(encoding="utf-8")
        self.assertIn("跨宿主说明", auditor_text)


if __name__ == "__main__":
    unittest.main()

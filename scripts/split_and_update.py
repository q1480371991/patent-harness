#!/usr/bin/env python3
"""
规则文件拆分脚本（完整引用更新版）
"""

import re
from pathlib import Path
from typing import List, Tuple

SKILL_ROOT = Path(__file__).parent.parent
RULES_DIR = SKILL_ROOT / "references" / "rules"

# 完整的引用路径替换映射
REFERENCE_MAPPING = {
    # claims.md 拆分
    "claims.md` L1": "claims-requirements.md` L1",
    "claims.md` L2": "claims-field-background.md` L2",
    "claims.md` L3": "claims-field-background.md` L3",
    "`claims.md` L1/L2/L3": "`claims-requirements.md` L1、`claims-field-background.md` L2/L3",
    
    # full-draft.md 拆分
    "full-draft.md` L4": "abstract-figures.md` L4",
    "full-draft.md` L5": "abstract-figures.md` L5",
    "full-draft.md` L6": "invention-content.md` L6",
    "full-draft.md` L7": "abstract-figures.md` L7",
    "full-draft.md` L8": "implementation.md` L8",
    
    # 新增：修复 figures.md 的引用
    "references/rules/abstract-figures.md` L5": "abstract-figures.md` L5",
    "`references/rules/abstract-figures.md` L5": "`abstract-figures.md` L5",
}


def extract_section(lines: List[str], start_marker: str, end_marker: str = None) -> List[str]:
    """从行列表中提取指定章节"""
    start_idx = None
    end_idx = len(lines)

    for i, line in enumerate(lines):
        if line.strip() == start_marker:
            start_idx = i
            break

    if start_idx is None:
        raise ValueError(f"找不到起始标记: {start_marker}")

    if end_marker:
        for i in range(start_idx + 1, len(lines)):
            if lines[i].strip() == end_marker:
                end_idx = i
                break

    return lines[start_idx:end_idx]


def split_claims_md():
    """拆分 claims.md"""
    print("\n=== 拆分 claims.md ===")
    source_file = RULES_DIR / "claims.md"
    lines = source_file.read_text(encoding="utf-8").splitlines(keepends=True)

    l1_lines = extract_section(lines, "## L1. 权利要求书规则", "## L2. 技术领域规则")
    claims_req_content = (
        "# 权利要求书规则\n\n"
        "本文件用于权利要求书的撰写与审查。\n\n"
        + "".join(l1_lines)
    )
    (RULES_DIR / "claims-requirements.md").write_text(claims_req_content, encoding="utf-8")
    print(f"  ✓ claims-requirements.md: {len(l1_lines)} 行")

    l2_lines = extract_section(lines, "## L2. 技术领域规则", None)
    claims_field_content = (
        "# 技术领域与背景技术规则\n\n"
        "本文件用于技术领域和背景技术的撰写。\n\n"
        + "".join(l2_lines)
    )
    (RULES_DIR / "claims-field-background.md").write_text(claims_field_content, encoding="utf-8")
    print(f"  ✓ claims-field-background.md: {len(l2_lines)} 行")

    return [
        ("claims-requirements.md", len(l1_lines)),
        ("claims-field-background.md", len(l2_lines)),
    ]


def split_full_draft_md():
    """拆分 full-draft.md"""
    print("\n=== 拆分 full-draft.md ===")
    source_file = RULES_DIR / "full-draft.md"
    lines = source_file.read_text(encoding="utf-8").splitlines(keepends=True)

    l4_lines = extract_section(lines, "## L4. 说明书摘要规则", "## L5. 摘要附图规则")
    l5_lines = extract_section(lines, "## L5. 摘要附图规则", "## L6. 发明内容规则")
    l7_lines = extract_section(lines, "## L7. 附图说明规则", "## L8. 具体实施方式规则")
    
    abstract_content = (
        "# 摘要与附图规则\n\n"
        "本文件用于说明书摘要、摘要附图和附图说明的撰写。\n\n"
        + "".join(l4_lines)
        + "\n---\n\n"
        + "".join(l5_lines)
        + "\n---\n\n"
        + "".join(l7_lines)
    )
    (RULES_DIR / "abstract-figures.md").write_text(abstract_content, encoding="utf-8")
    abstract_line_count = len(l4_lines) + len(l5_lines) + len(l7_lines)
    print(f"  ✓ abstract-figures.md: {abstract_line_count} 行")

    l6_lines = extract_section(lines, "## L6. 发明内容规则", "## L7. 附图说明规则")
    invention_content = (
        "# 发明内容规则\n\n"
        "本文件用于发明内容（含有益效果）的撰写。\n\n"
        + "".join(l6_lines)
    )
    (RULES_DIR / "invention-content.md").write_text(invention_content, encoding="utf-8")
    print(f"  ✓ invention-content.md: {len(l6_lines)} 行")

    l8_lines = extract_section(lines, "## L8. 具体实施方式规则", None)
    impl_content = (
        "# 具体实施方式规则\n\n"
        "本文件用于具体实施方式的撰写。\n\n"
        + "".join(l8_lines)
    )
    (RULES_DIR / "implementation.md").write_text(impl_content, encoding="utf-8")
    print(f"  ✓ implementation.md: {len(l8_lines)} 行")

    return [
        ("abstract-figures.md", abstract_line_count),
        ("invention-content.md", len(l6_lines)),
        ("implementation.md", len(l8_lines)),
    ]


def update_references():
    """更新所有文件中的引用路径"""
    print("\n=== 更新引用路径 ===")

    files_to_update = [
        "global.md",
        "revision.md",
        "docx-template.md",
        "figures.md",
        "claims-requirements.md",
        "claims-field-background.md",
        "abstract-figures.md",
        "invention-content.md",
        "implementation.md",
    ]

    total_replacements = 0

    for filename in files_to_update:
        filepath = RULES_DIR / filename
        if not filepath.exists():
            continue

        content = filepath.read_text(encoding="utf-8")
        original_content = content

        for old_ref, new_ref in REFERENCE_MAPPING.items():
            if old_ref in content:
                content = content.replace(old_ref, new_ref)

        if content != original_content:
            filepath.write_text(content, encoding="utf-8")
            replacements = []
            for old_ref in REFERENCE_MAPPING:
                if old_ref in original_content:
                    replacements.append(old_ref)
            total_replacements += len(replacements)
            print(f"  ✓ {filename}: {len(replacements)} 处引用更新")

    print(f"\n  总计: {total_replacements} 处引用更新")
    return total_replacements


def generate_w_index():
    """生成 W 编号索引"""
    print("\n=== 生成 W 编号索引 ===")

    w_pattern = re.compile(r'\bW\d+\b')
    index_entries = {}

    for md_file in RULES_DIR.glob("*.md"):
        if md_file.name.startswith("_") or md_file.name == "W-INDEX.md":
            continue

        content = md_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            if "W" not in line:
                continue
                
            matches = w_pattern.findall(line)
            for w_code in matches:
                if w_code in index_entries:
                    continue
                
                section = "未知"
                for i in range(line_num - 1, -1, -1):
                    if lines[i].startswith("### L") or lines[i].startswith("### G"):
                        section = lines[i].strip("#").strip()
                        break
                    elif lines[i].startswith("## L") or lines[i].startswith("## G"):
                        section = lines[i].strip("#").strip()
                        break

                topic = line.strip()
                topic = re.sub(r'^[\-\*\s]+', '', topic)
                if len(topic) > 80:
                    topic = topic[:77] + "..."

                index_entries[w_code] = (md_file.name, section, topic)

    index_content = """# W 编号索引

本文件自动生成，记录所有 W 编号的定义位置。

| W编号 | 定义文件 | 章节 | 主题 |
|-------|----------|------|------|
"""

    for w_code in sorted(index_entries.keys(), key=lambda x: int(x[1:])):
        filename, section, topic = index_entries[w_code]
        index_content += f"| {w_code} | {filename} | {section} | {topic} |\n"

    index_content += f"\n总计：{len(index_entries)} 个 W 编号\n"

    index_file = RULES_DIR / "W-INDEX.md"
    index_file.write_text(index_content, encoding="utf-8")

    print(f"  ✓ W-INDEX.md: {len(index_entries)} 个 W 编号")
    return len(index_entries)


def main():
    """主函数"""
    print("=" * 80)
    print("规则文件拆分脚本")
    print("=" * 80)

    claims_stats = split_claims_md()
    full_draft_stats = split_full_draft_md()
    all_stats = claims_stats + full_draft_stats

    ref_count = update_references()
    w_count = generate_w_index()

    print("\n" + "=" * 80)
    print("✅ 拆分完成！")
    print("=" * 80)
    print(f"\n新建文件: {len(all_stats)} 个")
    for filename, lines in all_stats:
        print(f"  - {filename}: {lines} 行")
    print(f"\n更新引用: {ref_count} 处")
    print(f"W 编号索引: {w_count} 个")
    
    print("\n下一步人工检查:")
    print("  1. 查看 W 索引: head -30 references/rules/W-INDEX.md")
    print("  2. 检查新文件: ls -lh references/rules/*.md | grep -E '(claims-|abstract-|invention-|implementation)'")
    print("  3. Git 状态: git status")
    
    return 0


if __name__ == "__main__":
    exit(main())

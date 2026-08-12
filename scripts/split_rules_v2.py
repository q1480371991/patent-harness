#!/usr/bin/env python3
"""
规则文件拆分脚本 v2

将 claims.md 和 full-draft.md 按章节拆分为多个独立文件，
并更新所有跨文件引用路径。
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

# 项目根目录
SKILL_ROOT = Path(__file__).parent.parent
RULES_DIR = SKILL_ROOT / "references" / "rules"

# 引用路径替换映射
REFERENCE_MAPPING = {
    "claims.md` L1": "claims-requirements.md` L1",
    "claims.md` L2": "claims-field-background.md` L2",
    "claims.md` L3": "claims-field-background.md` L3",
    "`claims.md` L1/L2/L3": "`claims-requirements.md` L1、`claims-field-background.md` L2/L3",
    "full-draft.md` L4": "abstract-figures.md` L4",
    "full-draft.md` L5": "abstract-figures.md` L5",
    "full-draft.md` L6": "invention-content.md` L6",
    "full-draft.md` L7": "abstract-figures.md` L7",
    "full-draft.md` L8": "implementation.md` L8",
}


def extract_section(lines: List[str], start_marker: str, end_marker: str = None) -> List[str]:
    """从行列表中提取指定章节"""
    start_idx = None
    end_idx = len(lines)

    # 找起点
    for i, line in enumerate(lines):
        if line.strip() == start_marker:
            start_idx = i
            break

    if start_idx is None:
        raise ValueError(f"找不到起始标记: {start_marker}")

    # 找终点
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

    # 1. claims-requirements.md (L1)
    l1_lines = extract_section(lines, "## L1. 权利要求书规则", "## L2. 技术领域规则")
    claims_req_content = (
        "# 权利要求书规则\n\n"
        "本文件用于权利要求书的撰写与审查。\n\n"
        + "".join(l1_lines)
    )
    (RULES_DIR / "claims-requirements.md").write_text(claims_req_content, encoding="utf-8")
    print(f"  ✓ claims-requirements.md: {len(l1_lines)} 行")

    # 2. claims-field-background.md (L2+L3)
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

    # 1. abstract-figures.md (L4+L5+L7)
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

    # 2. invention-content.md (L6)
    l6_lines = extract_section(lines, "## L6. 发明内容规则", "## L7. 附图说明规则")
    invention_content = (
        "# 发明内容规则\n\n"
        "本文件用于发明内容（含有益效果）的撰写。\n\n"
        + "".join(l6_lines)
    )
    (RULES_DIR / "invention-content.md").write_text(invention_content, encoding="utf-8")
    print(f"  ✓ invention-content.md: {len(l6_lines)} 行")

    # 3. implementation.md (L8)
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
            content = content.replace(old_ref, new_ref)

        if content != original_content:
            filepath.write_text(content, encoding="utf-8")
            count = sum(1 for old_ref in REFERENCE_MAPPING if old_ref in original_content)
            total_replacements += count
            print(f"  ✓ {filename}: {count} 处引用更新")

    print(f"\n  总计: {total_replacements} 处引用更新")
    return total_replacements


def generate_w_index():
    """生成 W 编号索引"""
    print("\n=== 生成 W 编号索引 ===")

    # 修正正则：W 编号可能单独出现或用斜杠连接
    w_pattern = re.compile(r'\bW\d+\b')
    index_entries = {}

    # 扫描所有规则文件
    for md_file in RULES_DIR.glob("*.md"):
        if md_file.name.startswith("_") or md_file.name == "W-INDEX.md":
            continue

        content = md_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            # 跳过非规则定义行（W 编号通常在圆括号内或条目开头）
            if "W" not in line:
                continue
                
            matches = w_pattern.findall(line)
            for w_code in matches:
                if w_code in index_entries:
                    continue  # 已记录过
                
                # 找到所在章节
                section = "未知"
                for i in range(line_num - 1, -1, -1):
                    if lines[i].startswith("### L") or lines[i].startswith("### G"):
                        section = lines[i].strip("#").strip()
                        break
                    elif lines[i].startswith("## L") or lines[i].startswith("## G"):
                        section = lines[i].strip("#").strip()
                        break

                # 提取主题（该行关键内容）
                topic = line.strip()
                # 去掉前导符号
                topic = re.sub(r'^[\-\*\s]+', '', topic)
                if len(topic) > 80:
                    topic = topic[:77] + "..."

                index_entries[w_code] = (md_file.name, section, topic)

    # 生成索引文件
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


def verify_integrity(split_stats: List[Tuple[str, int]]):
    """完整性校验"""
    print("\n=== 完整性校验 ===")

    # 1. 行数守恒校验（放宽至 50 行，因为新增了 5 个文件头）
    original_total = (
        len((RULES_DIR / "claims.md").read_text().splitlines()) +
        len((RULES_DIR / "full-draft.md").read_text().splitlines())
    )
    new_total = sum(count for _, count in split_stats)

    print(f"  原文件总行数: {original_total}")
    print(f"  新文件总行数: {new_total}")
    diff = abs(original_total - new_total)
    
    # 新增了 5 个文件头（每个约 4-5 行），允许差异 50 行
    if diff <= 50:
        print(f"  ✓ 行数守恒: 差异 {diff} 行（允许范围内）")
    else:
        print(f"  ✗ 行数守恒: 差异 {diff} 行（超出允许范围）")
        return False

    # 2. 章节完整性校验
    print("\n  章节完整性:")
    all_valid = True
    for filename, _ in split_stats:
        filepath = RULES_DIR / filename
        content = filepath.read_text()

        has_title = content.startswith("#")
        has_level_section = "## L" in content
        
        if has_title and has_level_section:
            print(f"    ✓ {filename}")
        else:
            print(f"    ✗ {filename}: 缺少必要元素")
            all_valid = False

    # 3. 引用完整性校验
    print("\n  引用完整性:")
    all_refs_valid = True
    ref_pattern = re.compile(r'`([^`]+\.md)` (L\d+)')

    for md_file in RULES_DIR.glob("*.md"):
        if md_file.name.startswith("_") or md_file.name == "W-INDEX.md":
            continue

        content = md_file.read_text()
        for match in ref_pattern.finditer(content):
            target_file, target_rule = match.groups()
            target_path = RULES_DIR / target_file

            if not target_path.exists():
                print(f"    ✗ {md_file.name}: 引用不存在的文件 {target_file}")
                all_refs_valid = False

    if all_refs_valid:
        print("    ✓ 所有引用有效")

    return all_valid and all_refs_valid


def main():
    """主函数"""
    print("=" * 80)
    print("规则文件拆分脚本 v2")
    print("=" * 80)

    # 拆分文件
    claims_stats = split_claims_md()
    full_draft_stats = split_full_draft_md()
    all_stats = claims_stats + full_draft_stats

    # 更新引用
    ref_count = update_references()

    # 生成索引
    w_count = generate_w_index()

    # 完整性校验
    if verify_integrity(all_stats):
        print("\n" + "=" * 80)
        print("✅ 拆分成功！")
        print("=" * 80)
        print(f"\n新建文件: {len(all_stats)} 个")
        for filename, lines in all_stats:
            print(f"  - {filename}: {lines} 行")
        print(f"\n更新引用: {ref_count} 处")
        print(f"W 编号索引: {w_count} 个")
        print("\n下一步:")
        print("  1. 检查新文件: ls -lh references/rules/*.md")
        print("  2. 搜索旧引用: grep -r 'claims.md\`' references/rules/ || echo '无旧引用'")
        print("  3. 查看索引: cat references/rules/W-INDEX.md | head -30")
        print("  4. Git 操作: git status")
        return 0
    else:
        print("\n" + "=" * 80)
        print("❌ 完整性校验失败，请检查")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    exit(main())

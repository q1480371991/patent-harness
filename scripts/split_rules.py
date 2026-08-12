#!/usr/bin/env python3
"""
规则文件拆分脚本

将 claims.md 和 full-draft.md 按章节拆分为多个独立文件，
并更新所有跨文件引用路径。
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

# 项目根目录
SKILL_ROOT = Path(__file__).parent.parent
RULES_DIR = SKILL_ROOT / "references" / "rules"

# 拆分映射配置
SPLIT_CONFIG = {
    "claims.md": [
        {
            "output": "claims-requirements.md",
            "title": "# 权利要求书规则\n\n本文件用于权利要求书的撰写与审查。\n\n",
            "start_marker": "## L1. 权利要求书规则",
            "end_marker": "## L2. 技术领域规则",
        },
        {
            "output": "claims-field-background.md",
            "title": "# 技术领域与背景技术规则\n\n本文件用于技术领域和背景技术的撰写。\n\n",
            "start_marker": "## L2. 技术领域规则",
            "end_marker": None,  # 到文件末尾
        },
    ],
    "full-draft.md": [
        {
            "output": "abstract-figures.md",
            "title": "# 摘要与附图规则\n\n本文件用于说明书摘要、摘要附图和附图说明的撰写。\n\n",
            "sections": ["L4", "L5", "L7"],  # 需要合并多个章节
        },
        {
            "output": "invention-content.md",
            "title": "# 发明内容规则\n\n本文件用于发明内容（含有益效果）的撰写。\n\n",
            "start_marker": "## L6. 发明内容规则",
            "end_marker": "## L7. 附图说明规则",
        },
        {
            "output": "implementation.md",
            "title": "# 具体实施方式规则\n\n本文件用于具体实施方式的撰写。\n\n",
            "start_marker": "## L8. 具体实施方式规则",
            "end_marker": None,  # 到文件末尾
        },
    ],
}

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

    stats = []

    for config in SPLIT_CONFIG["claims.md"]:
        output_file = RULES_DIR / config["output"]
        section_lines = extract_section(lines, config["start_marker"], config.get("end_marker"))

        # 写入新文件
        content = config["title"] + "".join(section_lines)
        output_file.write_text(content, encoding="utf-8")

        line_count = len(section_lines)
        stats.append((config["output"], line_count))
        print(f"  ✓ {config['output']}: {line_count} 行")

    return stats


def split_full_draft_md():
    """拆分 full-draft.md（包含合并多个章节的情况）"""
    print("\n=== 拆分 full-draft.md ===")
    source_file = RULES_DIR / "full-draft.md"
    lines = source_file.read_text(encoding="utf-8").splitlines(keepends=True)

    stats = []

    for config in SPLIT_CONFIG["full-draft.md"]:
        output_file = RULES_DIR / config["output"]

        if "sections" in config:
            # 合并多个章节（abstract-figures.md）
            all_sections = []
            for section_id in config["sections"]:
                start_marker = f"## {section_id}."
                # 找下一个章节标记
                next_section_idx = None
                for i, line in enumerate(lines):
                    if line.startswith(start_marker):
                        # 找下一个 ## 开头的行
                        for j in range(i + 1, len(lines)):
                            if lines[j].startswith("## L") and not lines[j].startswith(start_marker):
                                next_section_idx = j
                                break
                        section_lines = lines[i:next_section_idx] if next_section_idx else lines[i:]
                        all_sections.extend(section_lines)
                        if section_id != config["sections"][-1]:
                            all_sections.append("\n---\n\n")  # 章节分隔
                        break

            content = config["title"] + "".join(all_sections)
            line_count = len(all_sections)
        else:
            # 单个章节
            section_lines = extract_section(lines, config["start_marker"], config.get("end_marker"))
            content = config["title"] + "".join(section_lines)
            line_count = len(section_lines)

        output_file.write_text(content, encoding="utf-8")
        stats.append((config["output"], line_count))
        print(f"  ✓ {config['output']}: {line_count} 行")

    return stats


def update_references():
    """更新所有文件中的引用路径"""
    print("\n=== 更新引用路径 ===")

    # 需要更新的文件（包括新建的文件）
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

        # 执行替换
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

    w_pattern = re.compile(r'\*\*(W\d+)\b')
    index_entries = []

    # 扫描所有规则文件
    for md_file in RULES_DIR.glob("*.md"):
        if md_file.name.startswith("_") or md_file.name == "W-INDEX.md":
            continue

        content = md_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            matches = w_pattern.findall(line)
            for w_code in matches:
                # 找到所在章节
                section = "未知"
                for i in range(line_num - 1, -1, -1):
                    if lines[i].startswith("### L") or lines[i].startswith("### G"):
                        section = lines[i].strip("# ")
                        break

                # 提取主题（从该行或下一行）
                topic = line.strip()
                if len(topic) > 60:
                    topic = topic[:57] + "..."

                index_entries.append((w_code, md_file.name, section, topic))

    # 去重并排序
    unique_entries = {}
    for w_code, filename, section, topic in index_entries:
        if w_code not in unique_entries:
            unique_entries[w_code] = (filename, section, topic)

    # 生成索引文件
    index_content = """# W 编号索引

本文件自动生成，记录所有 W 编号的定义位置。

| W编号 | 定义文件 | 章节 | 主题 |
|-------|----------|------|------|
"""

    for w_code in sorted(unique_entries.keys(), key=lambda x: int(x[1:])):
        filename, section, topic = unique_entries[w_code]
        index_content += f"| {w_code} | {filename} | {section} | {topic} |\n"

    index_content += f"\n总计：{len(unique_entries)} 个 W 编号\n"

    index_file = RULES_DIR / "W-INDEX.md"
    index_file.write_text(index_content, encoding="utf-8")

    print(f"  ✓ W-INDEX.md: {len(unique_entries)} 个 W 编号")
    return len(unique_entries)


def verify_integrity(split_stats: List[Tuple[str, int]]):
    """完整性校验"""
    print("\n=== 完整性校验 ===")

    # 1. 行数守恒校验
    original_total = (
        len((RULES_DIR / "claims.md").read_text().splitlines()) +
        len((RULES_DIR / "full-draft.md").read_text().splitlines())
    )
    new_total = sum(count for _, count in split_stats)

    print(f"  原文件总行数: {original_total}")
    print(f"  新文件总行数: {new_total}")
    diff = abs(original_total - new_total)
    if diff <= 15:  # 允许误差（文件头、分隔线）
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

        # 检查必须包含的元素
        has_title = content.startswith("#")
        has_level_1 = "### L" in content or "### G" in content
        has_checklist = "自检清单" in content or "checklist" in content.lower()

        if has_title and has_level_1:
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
    print("规则文件拆分脚本")
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
        print(f"更新引用: {ref_count} 处")
        print(f"W 编号索引: {w_count} 个")
        print("\n下一步:")
        print("  1. 检查新文件: ls references/rules/")
        print("  2. 搜索旧引用: grep -r 'claims.md`' references/rules/")
        print("  3. 查看索引: cat references/rules/W-INDEX.md")
        print("  4. Git 操作: git status && git diff")
        return 0
    else:
        print("\n" + "=" * 80)
        print("❌ 完整性校验失败，请检查")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    exit(main())

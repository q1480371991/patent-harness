#!/usr/bin/env python3
"""
更新所有规则文件中的引用路径
"""

import re
from pathlib import Path

SKILL_ROOT = Path(__file__).parent.parent
RULES_DIR = SKILL_ROOT / "references" / "rules"

# 完整的引用替换映射（包含各种可能的引用格式）
REPLACEMENTS = [
    # claims.md L1 引用
    (r'`claims\.md` L1(?![0-9])', r'`claims-requirements.md` L1'),
    (r'`claims\.md` L1/L2/L3', r'`claims-requirements.md` L1、`claims-field-background.md` L2/L3'),
    (r'claims\.md` L1(?![0-9])', r'claims-requirements.md` L1'),
    
    # claims.md L2 引用
    (r'`claims\.md` L2', r'`claims-field-background.md` L2'),
    (r'claims\.md` L2', r'claims-field-background.md` L2'),
    
    # claims.md L3 引用
    (r'`claims\.md` L3', r'`claims-field-background.md` L3'),
    (r'claims\.md` L3', r'claims-field-background.md` L3'),
    
    # full-draft.md L4 引用
    (r'`full-draft\.md` L4', r'`abstract-figures.md` L4'),
    (r'full-draft\.md` L4', r'abstract-figures.md` L4'),
    
    # full-draft.md L5 引用
    (r'`full-draft\.md` L5', r'`abstract-figures.md` L5'),
    (r'full-draft\.md` L5', r'abstract-figures.md` L5'),
    (r'`references/rules/abstract-figures\.md` L5', r'`abstract-figures.md` L5'),
    
    # full-draft.md L6 引用
    (r'`full-draft\.md` L6', r'`invention-content.md` L6'),
    (r'full-draft\.md` L6', r'invention-content.md` L6'),
    
    # full-draft.md L7 引用
    (r'`full-draft\.md` L7', r'`abstract-figures.md` L7'),
    (r'full-draft\.md` L7', r'abstract-figures.md` L7'),
    
    # full-draft.md L8 引用
    (r'`full-draft\.md` L8', r'`implementation.md` L8'),
    (r'full-draft\.md` L8', r'implementation.md` L8'),
    
    # 其他格式的引用
    (r'按现行 `claims\.md` L1/L2/L3', r'按现行 `claims-requirements.md` L1、`claims-field-background.md` L2/L3'),
    (r'按批注所在内容块读取 `claims\.md`、`full-draft\.md`', 
     r'按批注所在内容块读取 `claims-requirements.md`、`claims-field-background.md`、`abstract-figures.md`、`invention-content.md`、`implementation.md`'),
    (r'参见 `references/rules/full-draft\.md`', r'参见 `references/rules/abstract-figures.md`、`references/rules/invention-content.md`、`references/rules/implementation.md`'),
]


def update_file_references(filepath: Path) -> int:
    """更新单个文件中的所有引用"""
    content = filepath.read_text(encoding="utf-8")
    original_content = content
    
    replacements_made = 0
    for pattern, replacement in REPLACEMENTS:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            replacements_made += 1
            content = new_content
    
    if content != original_content:
        filepath.write_text(content, encoding="utf-8")
        return replacements_made
    
    return 0


def main():
    """主函数"""
    print("=" * 80)
    print("更新所有规则文件中的引用路径")
    print("=" * 80)
    
    total_files = 0
    total_replacements = 0
    
    # 更新所有规则文件
    for md_file in sorted(RULES_DIR.glob("*.md")):
        if md_file.name.startswith("_") or md_file.name == "W-INDEX.md":
            continue
        
        count = update_file_references(md_file)
        if count > 0:
            total_files += 1
            total_replacements += count
            print(f"  ✓ {md_file.name}: {count} 类引用更新")
    
    print(f"\n总计: {total_files} 个文件, {total_replacements} 类引用更新")
    
    # 验证是否还有旧引用
    print("\n验证残留引用...")
    remaining = []
    for md_file in RULES_DIR.glob("*.md"):
        if md_file.name == "W-INDEX.md":
            continue
        content = md_file.read_text()
        if 'claims.md`' in content or 'full-draft.md`' in content:
            count = content.count('claims.md`') + content.count('full-draft.md`')
            remaining.append((md_file.name, count))
    
    if remaining:
        print(f"  ⚠ 还有 {len(remaining)} 个文件包含旧引用:")
        for filename, count in remaining:
            print(f"    - {filename}: {count} 处")
        print("\n  建议人工检查这些引用是否需要更新")
    else:
        print("  ✓ 无残留旧引用")
    
    return 0


if __name__ == "__main__":
    exit(main())

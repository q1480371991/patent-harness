# 经验库索引（按需加载）

本索引列出所有可按需读取的经验案例。**按症状/任务命中条目时，才加载对应文件**，平时不读。

每条格式：**[症状/任务]** → `文件:锚点` (一句话说明)

---

## DOCX 执行层避坑

- **要挂 Juventude 回复批注** → `docx-execution.md:C-DOCX-1` (手工挂载法：只动 comments/commentsExtended/document 三文件，避免 comment.py 产生孤立部件)
- **交付干净稿、需清除既有 tracked changes** → `docx-execution.md:C-DOCX-2` (清痕清单：接受/拒绝 del/ins/pPrChange/rPrChange，保留段落与 sectPr)
- **留痕注入段落标记报 schema 错** → `docx-execution.md:C-DOCX-3` (pPr/rPr 内 ins 必须排第一个子元素)

## 完整案例（非触发式，供研读）

- **配电设备火灾全文稿经验总结** → `H2605066-配电设备火灾识别主动灭火控制全文稿经验总结.md` (完整案例：权要编号迁移、附图同步、方法-系统对应)
- **权要格式标准示例** → `claims-format-standard.md` (独立权+从权标准格式、引用方式)

---

**新增经验的沉淀位置判断**：
- 主动义务型（每次撰写/返修都要遵守）→ 进 `references/rules/`（必读核心或触发块）
- 避坑型（只在做特定操作时需要）→ 进本索引对应文件（按需加载）
- 完整案例（供对照学习）→ 进 `cases/` 独立文件，索引列入"完整案例"节

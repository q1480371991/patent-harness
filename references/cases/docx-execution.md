# DOCX 执行层避坑案例库

本文件收录 DOCX 执行层（XML/批注/修订痕迹）的具体操作陷阱与最小侵入步骤。**属避坑型经验，非必读**：仅在执行对应操作时，由 `revision.md` / `docx-template.md` 的指针引导按需读取，不进必读规则层。

收录原则：只放“做某个具体 DOCX 操作时才需要、平时读了用不上”的执行细节；跨案件主动义务规则仍进 `references/rules/`，不进本文件。

---

## C-DOCX-1 给老板批注挂 Juventude 回复批注（手工挂载法）

**触发**：返修时要逐条回复老板批注、挂 AI 署名的 reply。

**为什么不用 `comment.py`**：`docx` skill 的 `comment.py` 会无条件新建 `commentsIds.xml`、`commentsExtensible.xml` 部件并注册关系。若原文件只含 `comments.xml`+`commentsExtended.xml`（很多 WPS/Word 导出的批注稿就是这样），新建的部件不会被正确注册到 `[Content_Types].xml` 与 `document.xml.rels`，产生未注册孤立部件，Word 打开可能报错。

**最小侵入挂载步骤**（只动三个文件，不新建部件、不新增关系）：

1. `word/comments.xml`：在 `</w:comments>` 前追加回复评论块，作者署名 `Juventude`，每条给唯一 `w:id`（取现有最大 id 之上）和唯一 8 位十六进制 `w14:paraId`；评论段格式（`pStyle`、`rPr`）复制原有评论块以保持一致。
2. `word/commentsExtended.xml`：在 `</w15:commentsEx>` 前为每条回复追加
   `<w15:commentEx w15:paraId="<回复paraId>" w15:paraIdParent="<父批注paraId>" w15:done="0"/>`，
   其中父批注 paraId 取自 `comments.xml` 中父评论 `<w:p w14:paraId="...">`（这是回复嵌套显示的关键）。
3. `word/document.xml`：在父批注的 `commentReference` run 之后插入回复的
   `<w:r><w:commentReference w:id="<回复id>"/></w:r>`。点锚点批注（只有 `commentReference`、无 `commentRangeStart/End`）也按此处理。

**校验**：作者集合含 `Juventude`；老板原批注条数与 `delText` 字数不减；`commentReference` 总数 = 原批注数 + 回复数；`docx` skill `validate` 无新增错误。

**注意**：老板原批注、原修订痕迹一律原样保留，不动。

---

## C-DOCX-2 干净稿交付：清除既有遗留修订痕迹

**触发**：用户要求交付干净稿（非留痕稿），而文件中残留有上一轮的 tracked changes。

**要清除的痕迹**：`<w:del>`/`<w:ins>`、`<w:delText>`、`<w:pPrChange>`/`<w:rPrChange>`，以及段落标记删除 `<w:pPr><w:rPr><w:del/></w:rPr></w:pPr>`。

**做法**：接受或拒绝既有痕迹使其落为最终文本——
- `<w:ins>` 接受：保留其内 run，去掉 `<w:ins>` 包裹。
- `<w:del>` 接受：整块删除（含 `delText`）。
- `<w:pPrChange>`/`<w:rPrChange>`：删除该变更记录块，保留当前属性。
- 段落标记 `<w:del/>`（在 `pPr/rPr` 内）：删除该标记，保留段落。

**底线**：只清痕迹，**保留段落结构、`sectPr`、`headerReference`、header 文件不动**；不得借清痕之名删段或合并分节。

**校验**：清除后文本检索确认无 `<w:del`、`<w:ins`、`pPrChange`、`rPrChange`、`delText` 残留；`sectPr` 数与 header 文件数不变。

**备注**：本机若无 LibreOffice，`docx` skill 的 `accept_changes.py` 不可用，需按上述规则手工在 XML 中处理。

---

## C-DOCX-3 留痕注入段落标记的子元素顺序

**触发**：留痕返修注入新段落且需把段末段落标记 `¶` 也标记为插入态。

**陷阱与规避**：`<w:pPr>/<w:rPr>` 内的 `<w:ins .../>` 必须作为第一个子元素，置于 `<w:rFonts>`、`<w:sz>` 等格式元素之前；否则严格 schema 报“ins 不被允许，期望 rPrChange”。该条与 `docx-template.md` G8-1 同源，详见该处。

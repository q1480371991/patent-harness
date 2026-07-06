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

---

## C-DOCX-4 整段留痕删除时遗漏段内 OMML 公式对象

**触发**：对含行内/独立公式的段落做整段留痕删除（del_para）。

**陷阱**：OMML 公式是 `<m:oMath>`/`<m:oMathPara>` 元素，**不是 `<w:r>`**——按 run 遍历段内内容转 delText 的删除逻辑会漏掉它。结果：接受修订后段落文本消失、段落合并，裸公式对象残留并挤进下一段开头（实测案例：被删参数解释段中的一个行内公式接受修订后孤零零出现在下一步骤引导行行首，被审核人质疑“这个公式出现的也很奇怪”）。

**规避**：del_para 逻辑必须同时处理三类内容——`<w:t>` 文本 run（转 delText 包 del）、`<w:drawing>`/`<w:object>` 图片 run（整 run 包 `<w:del>`）、`<m:oMath>`/`<m:oMathPara>` 数学对象（整块包 `<w:del>`，schema 合法）。删除后用“接受修订模拟”全文检索裸公式残留。

---

## C-DOCX-5 向 ins/del 混杂段插入内容时落点进入 del 块

**触发**：向“用户新写文本（w:ins）与被删旧文本（w:del）共存于同一 w:p”的段落插入新内容（常见于用户在 Word/WPS 中改写过的段落）。

**陷阱**：以“段内最后一个 `</w:r>`”或“段尾”定位插入点，落点可能在段内 `<w:del>` 块内部——插入的内容在接受修订时会随删除块一起消失（实测案例：一个公式被插入被删旧文的 del 块内，接受修订模拟才发现会丢失）。

**规避**：插入前判断落点的祖先链是否处于未闭合的 `<w:del>` 内（注意自闭合标记误判，见 C-DOCX-6）；插入公式/解释段时按“引导句→公式→参数解释”的语义链选择锚点，不得只锚“某段之后”；插入后必做接受修订模拟并断言段序（引导句与公式不被隔断、内容不落在删除态）。

---

## C-DOCX-6 自闭合修订标记误判与 rPr 内 ins/del 顺序

**触发**：脚本判断“某 run 是否处于他人 w:ins/w:del 内”，或向已有段落标记修订的 rPr 再加标记。

**陷阱一（误判）**：段落标记的 `<w:ins .../>`、`<w:del .../>` 是**自闭合**标签，无对应闭标签；用 `rfind('<w:ins ') > rfind('</w:ins>')` 判断包含关系会把自闭合标记当成未闭合的开标签，产生“目标在他人 ins 内”的误报。规避：只统计**非自闭合**开标签（正则 `<w:ins\b[^>]*[^/]>`）与闭标签的数量差。

**陷阱二（顺序）**：段落标记 rPr 内已有他人 `<w:ins/>` 时再加自己的 `<w:del/>`，CT_ParaRPr 要求 `ins` 在 `del` 之前；把 del 插在最前会触发 schema 错误。规避：rPr 内已有 ins 的，del 排在 ins 之后。

---

## C-DOCX-7 Word/WPS 再保存后的状态漂移与 pandoc OMML 假象

**触发**：用户与 AI 交替编辑同一 DOCX；或用 pandoc 判断公式好坏。

**陷阱一（状态漂移）**：Word/WPS 保存会重排全部修订 id 和批注 id、重拆 run、重新序列化 XML（去 xml:space 等）——上一轮的解包结果、批注 id 对照表、文本锚点全部失效。规避：每轮注入前重新解包当前文件、重验全部锚点；批注改用“批注人＋批注开头文字”指认而非 id；先 diff 出用户已完成的修改，从注入清单剔除，避免重复注入或覆盖用户成果。

**陷阱二（OMML 假象）**：pandoc 对 WPS 生成的 OMML 解析不全，`--track-changes` 输出中完好的公式也会显示成 `\frac{}{}{}_{}` 空槽——**不能以 pandoc 输出判断公式好坏**。规避：直接查 XML，以块内是否存在空结构元素（`<m:e/>`、`<m:sub/>`、`<m:sup/>`、`<m:num/>`、`<m:den/>`；`<m:deg/>` 配 degHide 除外）为壳判据。

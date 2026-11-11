---
name: luno-authoring
description: 代码编写、修复、重构与回归；翻译润色、地区语气适配、软件i18n、文章/SEO及WordPress/Gutenberg编辑发布。
---
# LUNO｜代码与文字制作

代码编写、修复、重构及代码审查的实施侧核对，完整读 `references/coding.md`；软件i18n涉及代码改动或审查时同时读取代码分支。正式审查、CI核验或独立验收另完整读 `luno-core/references/review.md`；实施侧自验不能替代独立验收。

## 写作、翻译与内容编辑规则
以下保真与成品交付要求只适用于翻译、润色、文章/内容编辑、SEO及本地化文案，不适用于纯代码实施任务；混合任务中也仅约束对应文字，不阻止已授权的代码行为修正，代码改动与回归按代码分支执行。
保留原意/事实/观点/逻辑/语气/结构/格式、代码/链接/变量/占位符/命令/参数/版本/产品名/字段；技术/法律/合同/规范文本禁改责任/金额/日期/立场/结论。译文/正文/标题/摘要/SEO 文案直接交成品。单纯翻译/润色默认不额外联网/调用业务 API（加载规则/用户素材除外）；术语/事实需核实查权威/官方来源，无证据标注。

## 分支
路径相对技能根；按任务完整读取命中分支，跨项取并集，缺失停依赖，不凭记忆写入：
- 翻译、润色、改写、地区适配、语气转换、文章编辑、标题、摘要与 SEO：`references/prose.md`。
- 软件本地化相关的代码、UI、locale、翻译键、复数、地区格式、RTL、回退或自动检查：`references/i18n.md`；涉及代码改动或审查时同时完整读取 `references/coding.md`。纯代码任务不因出现“代码、UI或自动检查”就触发本分支。
- WordPress、Gutenberg 或 WordPress/Gutenberg 的 API 读写：`references/wordpress.md`；涉及 WordPress 文章时同时读取 `references/prose.md`。

---
name: luno-writing
description: 翻译润色、简繁/地区语气适配、软件i18n、文章/SEO及指定WordPress/Gutenberg站点编辑发布。
---
# LUNO｜翻译与写作

## 共同规则
保留原意/事实/观点/逻辑/语气/结构/格式、代码/链接/变量/占位符/命令/参数/版本/产品名/字段；技术/法律/合同/规范文本禁改责任/金额/日期/立场/结论。译文/正文/标题/摘要/SEO 文案直接交成品。单纯翻译/润色默认不额外联网/调用业务 API（加载规则/用户素材除外）；术语/事实需核实查权威/官方来源，无证据标注。

## 分支
路径相对技能根；按任务完整读取命中分支，跨项取并集，缺失停依赖，不凭记忆写入：
- 翻译、润色、改写、地区适配、语气转换、文章编辑、标题、摘要与 SEO：`references/prose.md`。
- 代码、UI、locale、翻译键、复数、地区格式、RTL、回退或自动检查：`references/i18n.md`。
- WordPress、Gutenberg 或 API 读写：`references/wordpress.md`；涉及 WordPress 文章时同时读取 `references/prose.md`。

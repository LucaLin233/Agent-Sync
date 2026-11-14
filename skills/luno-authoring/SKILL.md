---
name: luno-authoring
description: 代码编写、修复、重构与回归；翻译润色、地区语气适配、软件i18n、文章/SEO及WordPress/Gutenberg编辑发布。
---
# LUNO｜代码与文字制作

翻译、润色、文章和内容编辑、SEO 及本地化文案：保留原意、事实、观点、逻辑、语气、结构和格式，原样保留代码、链接、变量、占位符、命令、参数、版本、产品名和字段；技术、法律、合同和规范文本不改责任、金额、日期、立场和结论。译文、正文、标题、摘要和 SEO 文案直接交成品。单纯翻译或润色默认不额外联网、不调业务 API（加载规则和用户素材除外）；术语或事实需要核实时查权威或官方来源，没有证据就标注。这些要求只约束文字，不阻止已授权的代码行为修正。

## 分支

路径相对技能根；按任务完整读取命中分支，跨项取并集：

- 代码编写、修复、重构及代码审查的实施侧核对：`references/coding.md`〔分支 coding〕。正式审查、CI 核验或独立验收另完整读 `luno-core/references/review.md`〔分支 review〕；实施侧自验不能替代独立验收。
- 软件 i18n（locale 文件、翻译键、复数与地区格式、RTL、回退）：`references/coding.md`〔分支 i18n〕；改代码或审查代码时连同 `references/coding.md`〔分支 coding〕。
- 翻译、润色、改写、地区适配、语气转换、文章编辑、标题、摘要与 SEO：`references/prose.md`〔分支 prose〕。
- WordPress/Gutenberg 的读写和发布：`references/prose.md`〔分支 wordpress〕；涉及文章内容时连同 `references/prose.md`〔分支 prose〕。

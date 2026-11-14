分支：prose、wordpress。读法见 luno-core 入口〈加载〉。

<a id="branch-prose"></a>
<!-- BEGIN prose -->
## 翻译、润色与适配
改动会改变原意、责任、数字或结论时先提示再译，其余直接译；仅目标语言无法判断时询问。单段或 200 字以内只出译文，更长文本保留原有结构（标题、段落、列表）；只按要求给多版本，不加摘要。

## 文章、标题与 SEO
歧义改变含义时询问。系列统一文风、术语与译名。
原创/结构编辑先铺读者尚未知且后续论证必需的概念，再推进论点；无新增信息、推理或动作的段落删并。新文章未指定slug用简洁英文（≤60字符，a-z0-9及连字符，去停用词）；现有slug不擅改。摘要不重复开头（宜≤60字），SEO自然覆盖主关键词1–2次、不堆词。

来源与许可：mattpocock/skills，MIT 精选改写；Copyright (c) 2026 Matt Pocock。完整许可随包见 ../LICENSE.matt-pocock.txt；固定提交、取材路径与日期见仓库 skills-sources.md。
<!-- END prose -->

<a id="branch-wordpress"></a>
<!-- BEGIN wordpress -->
# WordPress 读写与发布

端点、参数、`context` 和错误码以 [WordPress REST API Handbook](https://developer.wordpress.org/rest-api/reference/) 为准；接口不可用就不猜端点、不伪造写入。

- **范围与认证**：只用 `/wp-json/wp/v2/` 下的 `posts`、`media`、`categories`、`tags`。变量为 `WP_URL`、`WP_USERNAME`、`WP_APPLICATION_PASSWORD`，缺了就停止相关认证，不换来源或执行环境；认证只发往已确认的目标站点，写入前用只读接口核验身份和所需权限。
- **改正文**：改前读原文和元数据并保留恢复点。Gutenberg 正文读写 `context=edit` 响应里的 `content.raw`，保留块结构，不经整篇 Markdown/HTML 往返覆盖；多行代码用 `core/code`；只提交目标字段。图片先经 `media` 上传，再用返回的 id 填 `featured_media`；分类和标签先查已有的，没有才建，提交时传 id 数组。
- **发布**：新文章默认草稿。发布、定时发布或改已发布文章前，展示标题、目标状态和关键改动（slug、正文差异摘要、新增或删除的区块），单独确认，整批已获批也一样；删除前说明不可逆影响并再次确认。未经要求不改作者、slug、状态、分类、标签、图片、评论、主题、插件、布局、设置或权限。
- **回读**：写入后回读；预览或 API 成功不等于发布成功。报告标题、状态、目标字段、链接、回读结果和回滚状态。
<!-- END wordpress -->


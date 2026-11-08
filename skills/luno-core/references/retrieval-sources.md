# 来源登记与追新基线

基线：首次公开快照，以 Git 历史为准；核查日：2026-11-01（旧私有 LucaLin233/Agent@ff4ce212… 仅作历史溯源）。本文件随 luno-core 分发，承载来源与追新记录；完整 MIT 通知见本包 `../LICENSE.retrieval-sources.txt`。S1–S5 为正文来源编号；仓库实名只用于溯源，不表示当前调用机制。 Exa/Keenable 的接口细节、制稿取舍与验证记录保留供历史溯源，不作为当前调用契约，不证明 MCP 可用或行为一致。

## 精选改写的官方技能文件（5 个）

末改日期均由固定提交内逐路径 commits API 补证，取 committer 日期，非目录/HEAD/release 日期；固定原文与 LICENSE 当日公开可取。S1–S5 均对应本批 retrieval.md，逐文件复查基线为各固定提交＋本文件末节的成品哈希；原文 SHA-256 随各项登记。

### S1
原文 SHA-256：`150606d9b144863ea8b780fa06bc0f491a29b783f5869451901af50e4f553a7a`。
- 上游：`exa-labs/agent-skills` @ `aa6d5e6f7315b215c20bf15930367d61f86cc268`；文件 `skills/build-with-exa/references/search.md`（末次提交 2026-10-02T02:21:12Z）；许可 MIT，Copyright (c) 2026 Exa Labs, Inc.（完整通知见下节）。
- 精选改写：字段层级、无内容默认、内容模式与缓存/历史条件；未写：不搬参数大表、全产品路由、固定条数与强制用户批准过滤。

### S2
原文 SHA-256：`08bfdf43c5a2b3652223985aa4738a36714336fac633374aa950c5daa64db5f4`。
- 上游：`exa-labs/agent-skills` @ `aa6d5e6f7315b215c20bf15930367d61f86cc268`；文件 `skills/build-with-exa/references/contents.md`（末次提交 2026-10-14T07:37:13Z）；许可 MIT，Copyright (c) 2026 Exa Labs, Inc.。
- 精选改写：顶层提取/新鲜度、只选一种模式、逐 URL statuses；未写：不搬 SDK、重复的默认模式；两份参考的默认冲突改为按事实所需选择。

### S3
原文 SHA-256：`8dd37283380f7335d03017385f5d8eb9aa43be06c580d32e02f5681b8cb4c363`。
- 上游：`keenableai/keenable-hermes-plugin` @ `99ddccbd5ba37f3dc3f7b8c8bf24bed01ddf5ac7`；文件 `skills/keenable-search/SKILL.md`（末次提交 2026-10-25T06:38:10Z）；许可 MIT，Copyright (c) 2026 Keenable。
- 精选改写：精确引文/冲突才深读、prompt 定向、时间语义、401/429 分流；未写：不搬匿名降级、摘要足够即定论、固定数量、客户端传输与参数表。

### S4
原文 SHA-256：`3169a23e86ed0c167814dff0b8f850a092e5dde9eb7af7bf93dea5ec6d5dbc9e`。
- 上游：`keenableai/keenable-hermes-plugin` @ `99ddccbd5ba37f3dc3f7b8c8bf24bed01ddf5ac7`；文件 `skills/keenable-research/SKILL.md`（末次提交 2026-10-25T06:38:10Z）；许可 MIT，Copyright (c) 2026 Keenable。
- 精选改写：已答/冲突/未答状态、只补缺口、边际收益停止、限流不循环；未写：不搬固定 3–6 题、只跟进一次、固定轮数或并发要求。

### S5
原文 SHA-256：`0aacd119c70b57144e7358c5829061a0d25a734ea29afb668392861250c9e42f`。
- 上游：`exa-labs/exa-mcp-server` @ `55cc85c7305117aea538ea0b9dc7d19523be0c6a`；文件 `skills/search/SKILL.md`（末次提交 2026-04-22T04:27:41Z）；许可 MIT，Copyright (c) 2025 Exa Labs。
- 精选改写：Gotchas：相似候选不等于满足条件或验证；未写：不搬厂商独占/禁换源、强制子代理与模型、按 numResults 冒充审过来源数。

### 追新参数模板（S1–S5 共用，替换原五条逐条 curl）
- 逐文件最新提交：`curl -fsS 'https://api.github.com/repos/<owner/repo>/commits?path=<path>&per_page=1'`
- 最新 release：`curl -fsS 'https://api.github.com/repos/<owner/repo>/releases/latest'`
- `<owner/repo>` 与 `<path>` 取对应 S 条登记；同仓多文件（S1/S2、S3/S4）只换 `path`，跨仓（S5）换仓库与 `path`。404、无 latest tag 的降级与 `git diff <固定commit> <新commit> -- <path>` 核对流程仍按下方原文执行，不因模板合并放宽。

release/latest 返回 404 时，仅记无 latest release，再查同仓库 `/releases?per_page=1`，不得把无 tag 当作无更新。追新先查默认分支 `/commits/HEAD`，再查逐文件 commits；取得新提交后在该上游的独立克隆执行 `git diff <本表固定commit> <新commit> -- <本表文件路径>`，核正文与 LICENSE，不自动覆盖本地取舍。固定日期重查形态为同一 commits 查询加 `&sha=<本表固定commit>`；禁止用目录最后更新日期代替文件日期。

## 官方接口事实补充与限制

以下网页均于 2026-11-01 HTTP 200 可取；无可确认的源仓库/commit/文件末改日期，版权行未提供，表达再分发许可未裁定，仅改写接口事实、不转载正文、不套用技能 MIT。追新重取原 URL、比对快照；取回日不冒充发布日期。

- https://docs.keenable.ai/api-reference/search.md ：日期 before 含整日；query_time 日期为 UTC 零点并限当时索引，非历史原文。
- https://docs.keenable.ai/api-reference/fetch.md 与 https://api.keenable.ai/openapi.json （0.1.24）：search POST、fetch GET 查询参数；live 默认 false，prompt 是定向合成，不代事实验证；published_at 类型冲突未写死。
- https://docs.keenable.ai/authentication.md 与 https://exa.ai/docs/admin/error-codes ：认证、额度/权限、401/429 分流与 Retry-After。
- OnlyBoxes 来源、官方 URL、快照、实测与历史限制集中登记于 `skills/luno-ops/references/onlyboxes-baseline.md`；本文件不重复接口契约、现场证据或 OnlyBoxes 成品哈希。设备侧门禁只证 Exa/Keenable 鉴权与出网，不证 LobeHub 子进程继承、结果质量或真实任务表现；不据此删除/部署。

## 精选边界

- Exa common-mistakes.md、prompting-and-patterns.md 与已选 search/contents 重复，不另吸收；同义客户端技能、SDK/Agent/监控/SELECT/求职及安装器不纳入。历史内容只辨语义，未启用新产品；两份 Exa 参考默认模式冲突改为按事实选择，不强定默认。
- 拒绝禁换源、强制子代理/模型、固定题数/条数/轮数、401 匿名降级、摘要直接定论、厂商独占路由。
- retrieval.md 第一段合并同义表述，显式保留先读工具定义、按支持参数调用、不可发现报受限、不猜参数，保留默认先搜、官方优先、两轮转检索、交叉核对、原文证据/未核实与限长边界；defuddle/jina 全段及 OpenMinis 来源段逐字不变，旧许可冲突仍未裁定。OnlyBoxes 接口、证据与成品哈希本批集中登记于 `skills/luno-ops/references/onlyboxes-baseline.md`，不在本文件重复。

## 历史制稿成品哈希（2026-11-01记录；不作当前部署判等）

- `luno-core/references/retrieval.md`：SHA-256 `4d5061133bce8061bc8e00e26dbb90e1adb7a0aef42e86e895fe1354074d7766`。

## MIT 通知指针

以下版权行依次适用于 S1/S2、S5、S3/S4，以及本包 retrieval.md 的 OpenMinis 精选改写；完整 MIT 正文随本包 `../LICENSE.retrieval-sources.txt` 分发，不得只留来源链接。OpenMinis 固定提交为 164395f193a56e3507ca98415383c7c16780da00；2026-10-25 本地维护者决定按 MIT 处理，上游根 LICENSE 与 README 标 Apache-2.0 的不一致仍保留；此内部决定不构成法律适用结论，不授权扩大分发。附件 sha256：`4053fcd4931d9730ca91f63deabb58e69c8c7a2aee6b058cfc2d32371712ce01`。

完整 MIT 正文已随本包 `../LICENSE.retrieval-sources.txt` 分发；上段保留适用版权行、提交、日期与本地许可决定。

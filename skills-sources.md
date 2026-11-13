# 技能来源登记

登记固定版本、取材路径与边界、许可和恢复线索；活身份以 `tools/sync-targets.json` 为准。哈希仅为所注日期的历史取证，不作当前部署判等，不自动跟版。公开快照未导入旧私有 `LucaLin233/Agent` 历史。

## 约定

- 运行正文保留最短必要作者/许可、改写性质及来源指针，完整来源细节集中本文件；正文中的运行限制和加载触发不因来源下沉而删除。Apache-2.0 改写内容另保留修改声明，现有文件为：`skills/luno-core/references/agent-document-writing.md`〔分支 skill-authoring〕、`skills/luno-core/scripts/quick_validate.py`、`skills/luno-core/references/code-review.md`。
- 许可全文随技能包分发，文件名为 `skills/<技能>/LICENSE.*.txt`；本文件不是许可原文。对外分发含第三方改写内容的产物时，必须随附对应的版权行和许可全文。
- 「精选改写」指按本端需要用中文改写选定的判据，不是原文翻译，也不整段照抄。
- 「核对」指所注日期的本地或在线取证。标「在线可取性未复核」的条目此后没有再访问上游；整理本文件时也没有重新访问任何上游。
- 新增或退役吸收件、改动取材范围时，按 `skills/luno-core/references/sync.md`〔分支 sync-workflow〕〈变更纪律〉中的来源与许可规则同步更新本文件，缺少登记不算完成。
- 各节按现役技能归组，相对路径按该技能根解析；旧技能名仅作取材时的历史坐标，迁移历史见文末 git 指针。

## 总览

| 技能 | 性质 | 随包许可文件 |
|---|---|---|
| luno-core（并入原 luno-review、luno-sync） | 自编＋精选改写 | `LICENSE.matt-pocock.txt`、`LICENSE.retrieval-sources.txt`、`LICENSE.openminis.txt`、`LICENSE.apache-2.0.txt`、`LICENSE.code-review.txt`、`LICENSE.obra-superpowers.txt` |
| luno-ops | 自编＋精选改写 | `LICENSE.openclaw.txt` |
| luno-platform（记忆分支） | 自编＋精选改写，各端自持 | `LICENSE.matt-pocock.txt` |
| luno-authoring（并入原 luno-coding、luno-writing） | 自编＋精选改写 | `LICENSE.davila7.txt`、`LICENSE.matt-pocock.txt`、`LICENSE.obra-superpowers.txt` |
| luno-platform（并入原 luno-cchp、luno-lobehub、luno-minis） | 本端约定＋精选改写（含 CCHP 历史余段） | `LICENSE.openminis.txt`、`LICENSE.upstream.txt` |
| luno-platform（CCHP 上游资源） | 官方技能原样 vendored，另补随包许可 | `references/cchp-upstream/LICENSE.upstream.txt` |
| luno-surge | 自编运行资料＋历史来源证据＋精选改写 | `LICENSE.openminis.txt`、`LICENSE.openminis-ios-dev.txt` |

已移除和已退役的来源见文末〈已移除与退役的来源〉。

## 共用上游

### mattpocock/skills

许可为 MIT，版权行 `Copyright (c) 2026 Matt Pocock`；用到它的技能各自随包附 `LICENSE.matt-pocock.txt`。涉及三个固定提交：

- `5beb35b040e3de97e54fa9e386d7e42d15c295c2`：2026-10-19 的提交，2026-10-25 本地核对，在线可取性未复核。用于 luno-authoring（原 luno-coding）、luno-core（原 luno-review）、luno-memory。
- `6fd947921b935b7e1e69293a200400f0fdd5c15f`：依据 2026-10-07 的记录。用于 luno-core（原 luno-sync）。
- `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`：2026-11-05（luno-core、luno-review、luno-writing）和 2026-11-06（luno-coding）核对时上游可取。

### obra/superpowers

固定提交 `22f0b463e7a5e579904dd6211a520321035526f7`，MIT，版权行 `Copyright (c) 2025 Jesse Vincent`，随包附件为 `LICENSE.obra-superpowers.txt`。2026-11-05（luno-review）和 2026-11-06（luno-coding）核对时上游可取。

### OpenMinis/MinisSkills

固定提交 `164395f193a56e3507ca98415383c7c16780da00`，2026-10-25 本地核对；所有取自它的条目，在线可取性和本机行为都未复核。用于 luno-platform（原 luno-minis）、luno-surge、luno-core（含原 luno-review）。

**许可事实**：该提交的根 `LICENSE`（1,066 B，sha256 `2858f336d8173207aa079c4711085a28d22615d464b6a387363f7824116d00f0`，版权行 `Copyright (c) 2026 OpenMinis`）和 `ios-dev/LICENSE`（1,770 B，sha256 `06dfb33ed30ecda0338b8318d8243f36c501281a5d44398a7e3425ce149bd4f3`，版权行 `Copyright (c) 2026 OpenMinis contributors`）都记载 MIT，而 `README.md` 标的是 Apache-2.0。这是上游文件自身的不一致，作为事实保留。

**裁定（2026-10-25，已决）**：本地维护者按 MIT 处理，不随 README 改标。分发改写须附 MIT 版权和全文；内部决定不是法律结论、不扩大分发权。附件仅供通知及溯源，不授权发布；公开副本仍由负责人核原裁定对象与范围。

**随包附件**（根 LICENSE 与 ios-dev/LICENSE 的哈希见上述许可事实；Surge 两份原件取自该固定提交的公开 raw URL）：

- `skills/luno-surge/LICENSE.openminis.txt`：根 `LICENSE` 原字节。
- `skills/luno-surge/LICENSE.openminis-ios-dev.txt`：`ios-dev/LICENSE` 原字节，保留目录范围、第三方排除和致谢。
- `skills/luno-core/LICENSE.openminis.txt`（原 luno-review 附件）：根 `LICENSE` 原字节。
- `skills/luno-platform/LICENSE.openminis.txt`（原 luno-minis 附件）：完整 MIT 正文，附件 sha256 `78a0f6fa39ad99be9494b462b98081023fc3fd21616a9eaa20924ef9332d2005`。
- `skills/luno-core/LICENSE.retrieval-sources.txt`：合并的 MIT 通知，其中含 OpenMinis 版权行，见〈luno-core〉。

## luno-core

**mattpocock/skills（2026-11 固定提交，见〈共用上游〉）**（2026-11-05 核对，上游可取）：

- `skills/engineering/triage/SKILL.md`、`skills/engineering/triage/AGENT-BRIEF.md`、`skills/engineering/triage/OUT-OF-SCOPE.md` → `SKILL.md`：只吸收按行为概念查找既有实现和拒绝理由的判据。
- `skills/productivity/handoff/SKILL.md` → `references/handoff.md`：只吸收交接时引用既有 spec、issue、diff 并保留必要恢复信息的判据。

**OpenMinis/MinisSkills（共用固定提交，见〈共用上游〉）**（服务可用性也未复核）：`web-content-extractor/SKILL.md` → `references/retrieval.md`〈公开代理回退〉。内容是既有抓取方式都失败后依次回退到 Defuddle、Jina，保留上游两者的相对顺序，并限于 URL 和内容都获准公开披露的页面。许可依据根 `LICENSE`（MIT），见〈OpenMinis/MinisSkills〉。

**S1–S5** → `references/retrieval.md`：核查日 2026-11-01，当日固定原文与 LICENSE 公开可取；基线见首次公开快照，旧私有 `LucaLin233/Agent@ff4ce212…` 仅作溯源。编号和仓库名不是调用契约，历史验证不证明当前 MCP 可用或行为一致。末改日期由固定提交的逐路径 commits API 取 committer 日期，非目录、HEAD 或 release 日期。

- **S1** `exa-labs/agent-skills@aa6d5e6f7315b215c20bf15930367d61f86cc268`，`skills/build-with-exa/references/search.md`（末次提交 2026-10-02T02:21:12Z），原文 sha256 `150606d9b144863ea8b780fa06bc0f491a29b783f5869451901af50e4f553a7a`。采用字段层级、无内容时的默认、内容模式以及缓存和历史条件；没有搬参数大表、全产品路由、固定条数和强制用户批准过滤。
- **S2** 同一仓库与提交，`skills/build-with-exa/references/contents.md`（末次提交 2026-10-14T07:37:13Z），原文 sha256 `08bfdf43c5a2b3652223985aa4738a36714336fac633374aa950c5daa64db5f4`。采用顶层提取与新鲜度、只选一种模式、逐 URL 的 statuses；没有搬 SDK 和重复的默认模式。S1 与 S2 两份参考的默认模式互相冲突，改为按事实所需选择，不强定默认。
- **S3** `keenableai/keenable-hermes-plugin@99ddccbd5ba37f3dc3f7b8c8bf24bed01ddf5ac7`，`skills/keenable-search/SKILL.md`（末次提交 2026-10-25T06:38:10Z），原文 sha256 `8dd37283380f7335d03017385f5d8eb9aa43be06c580d32e02f5681b8cb4c363`。采用只在需要精确引文或存在冲突时深读、prompt 定向、时间语义、401 与 429 分流；没有搬匿名降级、摘要足够即定论、固定数量、客户端传输和参数表。
- **S4** 同一仓库与提交，`skills/keenable-research/SKILL.md`（末次提交 2026-10-25T06:38:10Z），原文 sha256 `3169a23e86ed0c167814dff0b8f850a092e5dde9eb7af7bf93dea5ec6d5dbc9e`。采用已答、冲突、未答三种状态，只补缺口，边际收益低时停止，限流时不循环；没有搬固定 3–6 题、只跟进一次、固定轮数或并发要求。
- **S5** `exa-labs/exa-mcp-server@55cc85c7305117aea538ea0b9dc7d19523be0c6a`，`skills/search/SKILL.md`（末次提交 2026-04-22T04:27:41Z），原文 sha256 `0aacd119c70b57144e7358c5829061a0d25a734ea29afb668392861250c9e42f`。采用其 Gotchas 中「相似候选不等于满足条件或已经验证」；没有搬厂商独占与禁止换源、强制子代理和模型、以 numResults 冒充审过的来源数。

S1–S5 的许可都是 MIT，版权行分别为：S1 与 S2 `Copyright (c) 2026 Exa Labs, Inc.`，S5 `Copyright (c) 2025 Exa Labs`，S3 与 S4 `Copyright (c) 2026 Keenable`。这些版权行连同 OpenMinis 的版权行合并在 `skills/luno-core/LICENSE.retrieval-sources.txt`（sha256 `4053fcd4931d9730ca91f63deabb58e69c8c7a2aee6b058cfc2d32371712ce01`）里随包分发，不能只留来源链接。

**未采纳**：与 search/contents 重复的 Exa `common-mistakes.md`、`prompting-and-patterns.md`，同义客户端技能、SDK、Agent、监控、SELECT、求职、安装器；拒绝禁止换源、强制子代理/模型、固定题/条/轮数、401 匿名降级、摘要即定论、厂商独占路由。历史辨析不启用新产品。

**官方接口文档**：以下 URL 于 2026-11-01 返回 200；源仓库、提交、末改日期和版权行不可确认，再分发表达许可未决，故只改写接口事实、不转载或套用 MIT。追新重取原 URL 比快照，取回日不冒充发布日期。

- `https://docs.keenable.ai/api-reference/search.md`：日期参数 before 包含当天整日；query_time 的日期按 UTC 零点计，并受当时索引限制，不是历史原文。
- `https://docs.keenable.ai/api-reference/fetch.md` 与 `https://api.keenable.ai/openapi.json`（0.1.24）：search 用 POST，fetch 用 GET 查询参数；live 默认为 false；prompt 是定向合成，不能代替事实验证；published_at 的类型存在冲突，没有写死。
- `https://docs.keenable.ai/authentication.md` 与 `https://exa.ai/docs/admin/error-codes`：认证、额度与权限、401 和 429 的分流以及 Retry-After。
- OnlyBoxes 的官方文档和实测结论在 `skills/luno-ops/references/execution-environment.md`〔分支 onlyboxes-baseline〕，这里不重复。

**历史成品**：2026-11-01 `luno-core/references/retrieval.md` sha256 `4d5061133bce8061bc8e00e26dbb90e1adb7a0aef42e86e895fe1354074d7766`；当时 S1–S5 复查用各固定提交加此哈希，不用于现部署判等。

### 技能编写与书写

**openai/skills@`49f948faa9258a0c61caceaf225e179651397431`**（提交时间 2026-06-24T02:36:12Z；2026-11-05 经公开 API 确认可取）：取自 `skills/.system/skill-creator/`，许可 Apache-2.0，许可原字节随包为 `LICENSE.apache-2.0.txt`。

- 精选改写进 `references/agent-document-writing.md`〔分支 skill-authoring〕，只留技能专属的增量；通用书写启发式在 `references/agent-document-writing.md`〔分支 agent-document-writing〕。
- 校验器 `scripts/quick_validate.py` 源自上游的 `quick_validate.py`，已在本地修改。
- 两个文件各保留一行 Apache-2.0 修改声明。已去掉 Codex 专用件，初始化器已退役。
- 已知缺口：历史上端侧退役的未闭合记录没有补证，不能视为已完成。

**mattpocock/skills（writing-for-agents 固定提交，见〈共用上游〉）**（直接取自上游 GitHub，不经市场）：`skills/productivity/writing-for-agents/SKILL.md`（该文件 sha256 `551adca942227b44192edba88acd4e8db911f0121ce58ad16944ccf6a896a74a`）→ `references/agent-document-writing.md`〔分支 agent-document-writing〕，是中文适配改写，没有作为独立技能入库。上游事实取自 2026-10-07 的核对记录，补登记时没有重新取上游。

- 未采纳 `SKILL-MECHANICS.md` 的调用机制（`disable-model-invocation`、按调用拆分、router skill）。
- 未采纳 leading words：中文锚词没有本端证据，不推广「一词代替多句」。
- 未把 negation 当作普遍定律，不据此改写现行的禁令式表述。
- 「按序列拆分」只作启发式，不授予派发权限，派发仍按各入口和子代理的规则。

### 审查取材

**anthropics/knowledge-work-plugins@`d3ee81913e5e179273313345847a2a4f42449bd2`**（2026-09-11）：`engineering/skills/code-review/SKILL.md` → `references/code-review.md`。精选改写了上游的四维清单和输出要素；架构维、依赖纪律、结构整改和诚实与分歧是自撰或扩写的；GitHub 长版没有整体采用。许可 Apache-2.0，原字节随包为 `LICENSE.code-review.txt`（11607 B，sha256 `a6946284993aeec75c7d75906064b66210c46051e562077efb30eb6dcfe72e26`）。在线可取性未复核。

- 2026-10-16 许可补证：从旧私有 `LucaLin233/Agent` 的 `ee75bb6` 取回原 `code-review` 市场发布物，1302 B，sha256 `3612de8f2c897f98ad20a46f5e0c9f8c6f160873b1e7f44def0bb2ff96ee3451`。实际吸收的四维清单原文 649 B，sha256 `adac810be9904bfb1e479b5bfc547b475ce4f6abab0e7ab3a3952090182bd6b5`，与[固定上游提交的同一段](https://github.com/anthropics/knowledge-work-plugins/blob/d3ee81913e5e179273313345847a2a4f42449bd2/engineering/skills/code-review/SKILL.md)逐字节相等。该提交的[完整 LICENSE](https://github.com/anthropics/knowledge-work-plugins/blob/d3ee81913e5e179273313345847a2a4f42449bd2/LICENSE) 为 Apache-2.0；目标提交根目录的 NOTICE 实读为 404。
- 这次补证只覆盖当前采用片段的可追溯许可；原市场整包的许可仍未决，不声称已核。

**anthropics/claude-plugins-official@`fa4eb54397ee2faccb6940512a19c017cb1337f3`**（2026-11-05 核对，上游可取）：`plugins/code-review/commands/code-review.md`、`plugins/pr-review-toolkit/agents/silent-failure-hunter.md`、`plugins/pr-review-toolkit/agents/pr-test-analyzer.md` → `references/code-review.md`。只吸收按适用目录核对规范、具体指出宽泛 catch 或 fallback 隐藏的错误、说明测试建议能抓住哪类回归这三条判据。许可 Apache-2.0（插件 LICENSE；根目录和目标路径的 NOTICE 实读均为 404），随包为 `LICENSE.apache-2.0.txt`。

**mattpocock/skills（2026-10 固定提交，见〈共用上游〉）**：

- `skills/productivity/grilling/SKILL.md` → `references/review.md`〔分支 review〕〈输出〉：只吸收提问按依赖分层。
- `skills/engineering/tdd/SKILL.md` → `references/code-review.md`〈四、审查过程要点〉：只吸收期望值须有独立来源的判据。
- 未采纳 design tree 全量穷举、自动派子代理和强制 TDD。

**mattpocock/skills（2026-11 固定提交，见〈共用上游〉）**（均进 `references/code-review.md`）：

- `skills/engineering/code-review/SKILL.md`：只作代码双轴本次比照的来源，不冒充旧的固定版本，不替代五维检查、授权或独立审查。
- `skills/engineering/codebase-design/{SKILL.md,DEEPENING.md,DESIGN-IT-TWICE.md}`：只吸收删除抽象后核对复杂度去向和调用方负担的判据。
- `skills/engineering/improve-codebase-architecture/{SKILL.md,HTML-REPORT.md}`：只吸收架构健康评估先按用户痛点和近期高频变更圈定热点的判据。
- `skills/engineering/domain-modeling/{SKILL.md,DOMAIN-MODELING-FORMAT.md,DOMAIN-MODELING-FORMAT-EXAMPLES.md}`：已登记为取材路径，具体取材边界没有单独记录。

**obra/superpowers（共用固定提交，见〈共用上游〉）**：`skills/requesting-code-review/SKILL.md`、`skills/receiving-code-review/SKILL.md`、`skills/verification-before-completion/SKILL.md` → `references/code-review.md`。只吸收采纳反馈前先核对当前调用方、平台和既有设计理由，以及没有消费者就不扩项的判据。

**OpenMinis/MinisSkills（共用固定提交，见〈共用上游〉）**：`evidence-chain-builder/SKILL.md` → `references/review.md`〔分支 review〕〈审查〉中事实核证按命题逐项进行的一段；不采用其打分脚本和二分标签门禁。许可依据根 `LICENSE`（MIT），附件为 `LICENSE.openminis.txt`。

## luno-ops

**openclaw/openclaw@`e4129b6375e3179be5d9ed0a56a35f2871f4e73b`**（2026-09-12）：`skills/github/SKILL.md` → `references/github.md`。精选改写时压入了凭据和远端对象的流程条款，没有搬运上游的命令示例；上游的 GitHub 版和市场版之间另有较大差异。2026-10-11 实测上游可访问。许可为 MIT：该提交根 `LICENSE` 的头三行含 `Copyright (c) 2026 OpenClaw Foundation`；2026-11-06 按该提交逐字节取回，1170 B，sha256 `73571b25…1c29d`，全文随包为 `LICENSE.openclaw.txt`。原完整快照只在 Git 历史中。

**自有表述的资源**：

- `references/service-runtime.md`〔分支 service-runtime〕 的服务排障节于 2026-11-06 依据官方文档（systemd 的 systemctl 与 journalctl、PM2、Docker Compose CLI、nginx 的运行控制与配置测试）独立重写；授权、确认和秘密投影条款是本技能的自有规则。它取代了已移除的 linux-service-triage 来源。
- `references/cfst.md` 的固定用法和脚本由用户 2026-10-30 指定，脚本行为据 2026-10-31 静态核对，没有实际执行测速。
- `references/execution-environment.md`〔分支 onlyboxes-baseline〕 自带 OnlyBoxes 官方文档链接、访问日期和实测证据层。

## luno-platform

### Minis

全部来自 **OpenMinis/MinisSkills（共用固定提交，见〈共用上游〉）**，精选改写进 `references/minis.md`〔分支 minis-runtime-device〕〈本机特性〉，许可见〈OpenMinis/MinisSkills〉，完整 MIT 正文随包为 `LICENSE.openminis.txt`。

- `ios-dev/SKILL.md` → iSH 文件与进程异常一段。许可依据 `ios-dev/LICENSE`（MIT）。正文所列复制样本之外的上游所述行为，本机未复核。
- `codex-on-ish/SKILL.md` → Codex/iSH TLS 排障一段。许可按 2026-10-25 的 MIT 裁定。
- `apple-reminders/SKILL.md` 第 94–103 行 → 原生 `apple-*` 条款之后关于原生查询完整性的一段。许可依据根 `LICENSE`（MIT，`Copyright (c) 2026 OpenMinis`）。

### CCHP 本端层

`references/cchp.md` 只保留本端认证/输出边界、组织写入约定、恢复及链路核验、带版本的实例经验；官方已覆盖的 CLI 说明、业务示例、输出、错误和分页不再维护中文副本。原 `cchp-source.md`、`cchp-workflow-org.md`、`cchp-workflow-providers.md`、`cchp-coverage-rules.md` 退役，历史取材证据可从 β 前 main 提交 `217ff083cf536cf9f946ffc9a233bc748dffc44b` 恢复。本端层保留历史精选改写的 MIT 版权通知及 `LICENSE.upstream.txt`，不因精简删除必要许可。本端层必需加载官方 cchp，不覆盖官方正文，官方凭据回退不适用于本端。

## cchp

- **官方来源**：https://github.com/CCH-HQ/cchp-cli ，固定采用提交 `d9da5760a8d2f6ce689c01b98b6c96540513045d`；2026-11-12 匿名 clone 核对默认分支 main HEAD 仍为该提交，未发生基线推进。
- **取材范围**：上游 `skills/cchp/` 的全部 6 个文件，原字节落到本仓库 `skills/luno-platform/references/cchp-upstream/`，仅将入口文件名 SKILL.md 改为 ENTRY.md；不翻译、不合并、不改正文/frontmatter。额外把上游根 `LICENSE` 原字节加入 `skills/luno-platform/references/cchp-upstream/LICENSE.upstream.txt`，不复制 CLI 二进制、spec、docs、构建/安装脚本或其他目录。
- **许可**：MIT，`Copyright (c) 2026 the cchp contributors`；完整版权与 MIT 条款随包分发，根 LICENSE 不替代它。
- **两端来源**：Minis 按审定仓库版本逐文件更新 `/var/minis/skills/luno-platform/`，并核 App 登记及新会话元数据；LobeHub 用 `https://github.com/LucaLin233/Agent-Sync/tree/main/skills/luno-platform` 安装，正文按 body_contract 核验，安装裁掉的尾 LF 须补回。独立 cchp 的退役已按当时规则备份真实前态并按授权逐端回读（历史记录，不是现行备份义务）；运行端 ID 和状态只在实际安装回读后更新，不在制稿阶段虚填。
- **追新**：只从官方 GitHub 默认分支核 HEAD、逐文件末次提交、正文及 LICENSE diff；经授权采纳与审查后更新 vendored 字节和本登记，不自动跟版。安装 main URL 不能锁 SHA，部署前后核分支 HEAD 与已审提交，并逐文件回读，分支推进或内容不符就停止相关对象。
- **原始文件 SHA-256**（2026-11-12，固定提交）：
  - `skills/luno-platform/references/cchp-upstream/LICENSE.upstream.txt`：`481c79a8e1493001832cfb2e417e2a698f7f0b0d3b3351a10fa0750e53046cb2`
  - `skills/luno-platform/references/cchp-upstream/ENTRY.md`：`b5be23e8377bb71a275245c025047fbf9ab4e3435793e8641f3005d67a7149b6`
  - `skills/luno-platform/references/cchp-upstream/references/auth.md`：`0db41d2c9142d8b63e30a0933d257233634e4bd5c0ddcf94356fdfea514af053`
  - `skills/luno-platform/references/cchp-upstream/references/errors.md`：`8cca46803de493de7ac75f24be098d7a5e236900a786474529627da68c9a60dc`
  - `skills/luno-platform/references/cchp-upstream/references/output-contract.md`：`10bf216fa42ff8ed87aa137898039c72328af10b20279e5f90ea1d0fb0c8d296`
  - `skills/luno-platform/references/cchp-upstream/references/pagination.md`：`a49814cd2246eeb69c8f85df2e4b3c37b2a39b7ca833d08892bdc80687760229`
  - `skills/luno-platform/references/cchp-upstream/references/workflows.md`：`30a15014d3dfdd53f40bc8380f2c101d2cddb53ef0ae925c9d3b86a2cf942e4c`

## luno-authoring

### 写作与本地化

**davila7/claude-code-templates@`c93d4ee1e1a2ffabbc5084ccf4715d10683f4b82`**（2026-09-11）：`cli-tool/components/skills/development/i18n-localization/` → `references/coding.md`〔分支 i18n〕，要点精选并入，原脚本已退役。退役前的市场版与上游逐字节一致（2026-10-11 实测复核），2026-10-11 实测上游可访问。许可为 MIT：该提交根 `LICENSE` 的头三行含 `Copyright (c) 2025 Daniel (San) Ávila`；2026-11-06 按该提交逐字节取回，1075 B，sha256 `15cc073f…a705`，全文随包为 `LICENSE.davila7.txt`。

**mattpocock/skills（2026-11 固定提交，见〈共用上游〉）**（2026-11-05 核对，上游可取）：`skills/in-progress/writing-shape/SKILL.md` → `references/prose.md`〔分支 prose〕。只吸收原创和结构编辑时先铺陈受众未知而论证需要的概念、删去或合并没有新增作用的段落这两条判据。

**自有表述**：`references/prose.md`〔分支 wordpress〕 的接口要点于 2026-11-06 依据 [WordPress REST API Handbook](https://developer.wordpress.org/rest-api/reference/) 独立重写；授权、确认和回读条款是本技能的自有规则。它取代了已移除的 wordpress-api-gutenberg 来源。

### 代码实施

**mattpocock/skills（2026-11 固定提交，见〈共用上游〉）**（2026-11-06 核对）：`skills/engineering/tdd/SKILL.md`、`skills/engineering/implement/SKILL.md`。只吸收〈动手前〉的「沿用领域词表与 ADR 的词汇」「按纵切片而非横向分层推进」，〈改动〉的「不为未出现的用法做投机扩展」，以及 implement 的「收尾时再跑一次完整检查」。

**obra/superpowers（共用固定提交，见〈共用上游〉）**（2026-11-06 核对）：`skills/verification-before-completion/SKILL.md`。依据是该文件的「Core principle: Evidence before claims, always」，以及〈Common Failures〉中测试通过需要测试命令输出、之前的运行或「should pass」都不算数的判据。只对应〈交付〉中「附结果证据……不以『应该没问题』或文件已存在代替」这一句；〈改动〉的三条 diff 核对判据是自有流程，不取自上游。

**mattpocock/skills（2026-10 固定提交，见〈共用上游〉）**：`skills/engineering/diagnosing-bugs/SKILL.md`、`skills/engineering/to-tickets/SKILL.md`。改写进〈修正与重构〉（复现入口必须对应同一症状、实跑记录、随机故障的命中率、正确的接缝）和〈动手前〉（按行为切片，机械性宽重构的 expand–contract 例外）。

**自有部分**：〈动手前〉的可判定验收及「定位约定 → 定验收 → 行为切片」自定；2026-11-06 重写时的最小改动、沿用风格、孤儿清理、不可能情形须证据、宽重构例外均非上述两上游。上游为英文，按句自查未发现同形句，不作更强断言。

原吸收来源已移除，见〈已移除与退役的来源〉。

## luno-memory

**mattpocock/skills（2026-10 固定提交，见〈共用上游〉）**：`skills/engineering/retro/SKILL.md` → `references/maintenance.md`〔分支 maintenance〕 的固化落点条款，即机械可判定的编码规范违规，先核对既有检查是否实际接通。不采用「没有护栏即缺陷」，也不无条件新建检查器或门禁。

## luno-surge

运行资料的自编/官方事实摘要边界、非译本与无原文摘录声明、`agents/openai.yaml` 自写、有限短摘录的逐项及累计核对义务，统一见 `skills/luno-surge/references/SOURCE.md`〈来源与许可范围〉；不得以根 MIT 或 OpenMinis 通知扩大 Surge 材料分发权。

**官方来源例外**：Surge Mac 应用包，非 GitHub 技能仓库。取源、包身份、逐文件哈希及许可按 `skills/luno-surge/references/SOURCE.md`，机器证据见 `skills/luno-surge/references/upstream-manifest.json`；普通使用不补原件，原件和 logo 不进公开 Git 或运行包。哈希不授予分发权；例外仅对该对象有效（`luno-core/references/sync.md`〈真源与落点〉）。

**OpenMinis/MinisSkills（共用固定提交，见〈共用上游〉）**：精选改写的同机回环内容，不是 Surge.app 的官方更新，与官方来源哈希无关；在线可取性和当前设备行为都未复核。

- `ios-dev/SKILL.md`、`ios-dev/references/loopback.md`、`coredevice-toolkit/references/SURGE_LOOPBACK.md` → `references/command-reference.md`〔分支 diagnostics〕〈CoreDevice/RSD 同机回环（第三方报告，非本机验收）〉。许可依据根 `LICENSE` 和 `ios-dev/LICENSE`（均为 MIT）。
- 许可附件为 `LICENSE.openminis.txt` 和 `LICENSE.openminis-ios-dev.txt`，README 与 LICENSE 的不一致及其裁定见〈OpenMinis/MinisSkills〉。`references/SOURCE.md`〈第三方精选改写〉只保留指向本文件的简短说明。

输出脱敏的历史保证边界和使用方契约见 `skills/luno-surge/references/SOURCE.md`〈luno-surge 输出脱敏的保证边界〉。

## 已移除与退役的来源

- **luno-coding 原吸收上游**（2026-11-06 公开快照时移除）：原上游没有 LICENSE 文件和版权行（2026-10-20 实查全树及 30 次提交历史），许可材料不完整，不具备公开分发条件，因此不随仓库分发其原件，来源注释和登记一并移除。〈动手前〉〈改动〉两节改按可公开取用的 MIT 上游重写，见〈luno-authoring〉。原快照（2518 B）只作旧私有 `LucaLin233/Agent` 的历史溯源，不是本仓库的来源。重写时按句人工对照了该原文，重写后的两节没有与之同形的句子；这是逐句比对，不是工具全量判等，不作「零相似」这样更强的断言。
- **linux-service-triage**（luno-ops，2026-11-06 公开快照时移除）：旧三文件已从 `02f82fb^` 找回，其中 `SKILL.md` 为 3209 B，sha256 `6029658dba3841a9503d18af2c80f448dd45795ae6b90f1aa7b23f96e7daece2`；没有 license 字段或许可证附件。元信息给出的完整提交为 `8d4113eba2202d4cbbbc66ff6c429d846fdcd800`，但原上游两个同名 skills 仓库（clawdbot 与 openclaw 名下）对该提交都返回 404。许可缺口保留，不得虚构。服务排障节已按官方文档独立重写（见〈luno-ops〉）；没有持有上游原文，所以没有做逐句比对；本仓库不再含该上游文件。
- **wordpress-api-gutenberg**（luno-writing，2026-11-06 公开快照时移除）：原上游仓库和提交已 404，许可状态从未记录，缺口保留。接口要点已独立重写为自有表述（见〈luno-authoring〉），来源注释和「吸收件」标注已移除。没有持有上游原文，无法逐句对照，因此不就是否含原句作断言，只声明不再以该上游为来源。原 10 个文件只作旧私有 `LucaLin233/Agent` 的历史溯源。
- **nexttrace**（2026-11-01 退役，仅仓库侧）：`nxtrace/NTrace-core@7ff73b2c51f9f37a9bc1d6139b7053948f0250db`（2026-09-13），原有八个文件，另加同一提交根 LICENSE 的包装附件；七个 references 加 LICENSE。来源以及与固定 licensed ZIP 的逐文件判等历史见 2026-09-21 的归档；不自动更新。

## 追新核对

通用核对方法见 `skills/luno-core/references/retrieval.md`〈来源维护（仅溯源、追新或再分发核对）〉及 `skills/luno-core/references/sync.md`〈真源与落点〉；CCHP 另按上述对象专属要求，Surge 按包内 SOURCE 的官方来源例外。

合并及共读资源迁移历史见提交 [`484de55052413ef2004d5e588d5a0540bcf88826`](https://github.com/LucaLin233/Agent-Sync/commit/484de55052413ef2004d5e588d5a0540bcf88826) 及后续 git 历史；现役路径以本文件和 `tools/sync-targets.json` 为准。

## 本次两项独立入口合并

固定主基线 86b6f088835c8a25f2c4843bc032f4bca301f76b。独立 cchp、luno-memory 退役，能力进入 luno-platform；不卸载 CLI，不迁移各端记忆数据。CCHP 原上游 skills/cchp 六文件及根 MIT 按原字节承接到 skills/luno-platform/references/cchp-upstream/（SKILL.md 仅改文件名为 ENTRY.md）；原 frontmatter、相对引用、固定上游和上列内容哈希保持不变。上文旧独立安装路径及链接是迁移前历史，不是新部署入口；新安装只用 skills/luno-platform 子目录，旧身份见本次 PR 的真实前态记录。

memory-common.md 承接跨端共同义务；minis-memory.md 承接 Minis 文件入口、容量/注入与下次写入复核；LobeHub 平台记忆仍保留在既有 lobehub-knowledge.md 的 lobehub-memory 分支，知识库剩余内容在 knowledge 分支逐字保留，仅补分支定界和必要引用。共同义务未移入 Minis 或 LobeHub 专属分支。原 luno-memory 的 Matt Pocock MIT 全文移到平台根并继续随包分发。更新 CCHP 时人工核 GitHub 默认分支 HEAD、逐文件末次提交、原始字节 diff 与 LICENSE，不自动覆盖本端限制；不再从独立 cchp 安装入口直接更新。

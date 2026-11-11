# 技能来源登记

本文件登记第三方来源的固定版本、所取文件、取材边界、许可和恢复线索。对象的活身份只以 `tools/sync-targets.json` 为准。本仓库不自动跟随上游，也不缓存上游的当前哈希；文中的哈希都是所注日期取证时的记录，不用于当前部署判等。部署沿革等旧历史在旧私有仓库 `LucaLin233/Agent` 的 Git 历史里，公开快照仓库没有这段历史。

## 约定

- 运行正文保留最短必要作者/许可、改写性质及来源指针，完整来源细节集中本文件；正文中的运行限制和加载触发不因来源下沉而删除。Apache-2.0 改写内容另保留修改声明，现有文件为：`skills/luno-sync/references/skill-authoring.md`、`skills/luno-sync/scripts/quick_validate.py`、`skills/luno-review/references/code-review.md`。
- 许可全文随技能包分发，文件名为 `skills/<技能>/LICENSE.*.txt`；本文件不是许可原文。对外分发含第三方改写内容的产物时，必须随附对应的版权行和许可全文。
- 「精选改写」指按本端需要用中文改写选定的判据，不是原文翻译，也不整段照抄。
- 「核对」指所注日期的本地或在线取证。标「在线可取性未复核」的条目此后没有再访问上游；整理本文件时也没有重新访问任何上游。
- 新增或退役吸收件、改动取材范围时，按 `skills/luno-sync/references/sync-workflow.md`〈变更纪律〉中的来源与许可规则同步更新本文件，缺少登记不算完成。

## 总览

| 技能 | 性质 | 第三方上游 | 随包许可文件 |
|---|---|---|---|
| luno-core | 自编＋精选改写 | mattpocock/skills、OpenMinis/MinisSkills、Exa 与 Keenable 的技能文件（S1–S5） | `LICENSE.matt-pocock.txt`、`LICENSE.retrieval-sources.txt` |
| luno-sync | 自编＋精选改写 | openai/skills（Apache-2.0）、mattpocock/skills | `LICENSE.skill-authoring.txt`、`LICENSE.matt-pocock.txt` |
| luno-ops | 自编＋精选改写 | openclaw/openclaw | `LICENSE.openclaw.txt` |
| luno-lobehub | 自编 | 无 | 无 |
| luno-minis | 自编＋精选改写 | OpenMinis/MinisSkills | `LICENSE.openminis.txt` |
| luno-review | 自编＋精选改写 | anthropics/knowledge-work-plugins、anthropics/claude-plugins-official（均为 Apache-2.0）、mattpocock/skills、obra/superpowers、OpenMinis/MinisSkills | `LICENSE.code-review.txt`、`LICENSE.anthropic-plugins.txt`、`LICENSE.matt-pocock.txt`、`LICENSE.obra-superpowers.txt`、`LICENSE.openminis.txt` |
| luno-writing | 自编＋精选改写 | davila7/claude-code-templates、mattpocock/skills | `LICENSE.davila7.txt`、`LICENSE.matt-pocock.txt` |
| luno-memory | 自编＋精选改写 | mattpocock/skills | `LICENSE.matt-pocock.txt` |
| luno-coding | 自编＋精选改写 | mattpocock/skills、obra/superpowers | `LICENSE.matt-pocock.txt`、`LICENSE.obra-superpowers.txt` |
| luno-cchp | 第三方改编（含精选改写） | CCH-HQ/cchp-cli | `LICENSE.upstream.txt` |
| luno-surge | 自编运行资料＋历史来源证据＋精选改写 | Surge Mac 应用包（官方来源例外）、OpenMinis/MinisSkills | `LICENSE.openminis.txt`、`LICENSE.openminis-ios-dev.txt` |

已移除和已退役的来源见文末〈已移除与退役的来源〉。

## 共用上游

### mattpocock/skills

许可为 MIT，版权行 `Copyright (c) 2026 Matt Pocock`；用到它的技能各自随包附 `LICENSE.matt-pocock.txt`。涉及三个固定提交：

- `5beb35b040e3de97e54fa9e386d7e42d15c295c2`：2026-10-19 的提交，2026-10-25 本地核对，在线可取性未复核。用于 luno-coding、luno-review、luno-memory。
- `6fd947921b935b7e1e69293a200400f0fdd5c15f`：依据 2026-10-07 的记录。用于 luno-sync。
- `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`：2026-11-05（luno-core、luno-review、luno-writing）和 2026-11-06（luno-coding）核对时上游可取。

### obra/superpowers

固定提交 `22f0b463e7a5e579904dd6211a520321035526f7`，MIT，版权行 `Copyright (c) 2025 Jesse Vincent`，随包附件为 `LICENSE.obra-superpowers.txt`。2026-11-05（luno-review）和 2026-11-06（luno-coding）核对时上游可取。

### OpenMinis/MinisSkills

固定提交 `164395f193a56e3507ca98415383c7c16780da00`，2026-10-25 本地核对；所有取自它的条目，在线可取性和本机行为都未复核。用于 luno-minis、luno-surge、luno-review、luno-core。

**许可事实**：该提交的根 `LICENSE`（1,066 B，sha256 `2858f336d8173207aa079c4711085a28d22615d464b6a387363f7824116d00f0`，版权行 `Copyright (c) 2026 OpenMinis`）和 `ios-dev/LICENSE`（1,770 B，sha256 `06dfb33ed30ecda0338b8318d8243f36c501281a5d44398a7e3425ce149bd4f3`，版权行 `Copyright (c) 2026 OpenMinis contributors`）都记载 MIT，而 `README.md` 标的是 Apache-2.0。这是上游文件自身的不一致，作为事实保留。

**裁定（2026-10-25，已决）**：本地维护者决定按 MIT 处理，不依据 README 改标。对外分发含这些改写内容的产物时，须随附 MIT 版权行和许可全文。这个内部决定不是法律适用结论，也不授权扩大分发。随包附件只用于许可通知和溯源，不产生新的发布授权；公开副本仍需负责人另行核对原裁定的对象与范围。

**随包附件**：

- `skills/luno-surge/LICENSE.openminis.txt`：根 `LICENSE` 原文，取自该固定提交的公开 raw URL，sha256 `2858f336d8173207aa079c4711085a28d22615d464b6a387363f7824116d00f0`。
- `skills/luno-surge/LICENSE.openminis-ios-dev.txt`：`ios-dev/LICENSE` 原文，取自同一提交的公开 raw URL，sha256 `06dfb33ed30ecda0338b8318d8243f36c501281a5d44398a7e3425ce149bd4f3`；原文中的目录范围、第三方排除和致谢一并保留。
- `skills/luno-review/LICENSE.openminis.txt`：完整 MIT 正文，sha256 `2858f336d8173207aa079c4711085a28d22615d464b6a387363f7824116d00f0`。
- `skills/luno-minis/LICENSE.openminis.txt`：完整 MIT 正文，附件 sha256 `78a0f6fa39ad99be9494b462b98081023fc3fd21616a9eaa20924ef9332d2005`。
- `skills/luno-core/LICENSE.retrieval-sources.txt`：合并的 MIT 通知，其中含 OpenMinis 版权行，见〈luno-core〉。

## luno-core

**mattpocock/skills@`4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`**（2026-11-05 核对，上游可取）：

- `skills/engineering/triage/SKILL.md`、`skills/engineering/triage/AGENT-BRIEF.md`、`skills/engineering/triage/OUT-OF-SCOPE.md` → `SKILL.md`：只吸收按行为概念查找既有实现和拒绝理由的判据。
- `skills/productivity/handoff/SKILL.md` → `references/handoff.md`：只吸收交接时引用既有 spec、issue、diff 并保留必要恢复信息的判据。

**OpenMinis/MinisSkills@`164395f193a56e3507ca98415383c7c16780da00`**（服务可用性也未复核）：`web-content-extractor/SKILL.md` → `references/retrieval.md`〈公开代理回退〉。内容是既有抓取方式都失败后依次回退到 Defuddle、Jina，保留上游两者的相对顺序，并限于 URL 和内容都获准公开披露的页面。许可依据根 `LICENSE`（MIT），见〈OpenMinis/MinisSkills〉。

**S1–S5**（精选改写进 `references/retrieval.md`）：基线是首次公开快照，以 Git 历史为准；核查日 2026-11-01，旧私有 `LucaLin233/Agent@ff4ce212…` 只作历史溯源。S1–S5 只是来源编号，仓库实名用于溯源，不代表当前的调用机制。2026-11-01 的可取性和接口验证是历史记录，不是当前调用契约，也不证明当前 MCP 可用或行为一致。各文件的末改日期由固定提交内的逐路径 commits API 补证，取 committer 日期，不是目录、HEAD 或 release 的日期；当日固定原文和 LICENSE 都公开可取。

- **S1** `exa-labs/agent-skills@aa6d5e6f7315b215c20bf15930367d61f86cc268`，`skills/build-with-exa/references/search.md`（末次提交 2026-10-02T02:21:12Z），原文 sha256 `150606d9b144863ea8b780fa06bc0f491a29b783f5869451901af50e4f553a7a`。采用字段层级、无内容时的默认、内容模式以及缓存和历史条件；没有搬参数大表、全产品路由、固定条数和强制用户批准过滤。
- **S2** 同一仓库与提交，`skills/build-with-exa/references/contents.md`（末次提交 2026-10-14T07:37:13Z），原文 sha256 `08bfdf43c5a2b3652223985aa4738a36714336fac633374aa950c5daa64db5f4`。采用顶层提取与新鲜度、只选一种模式、逐 URL 的 statuses；没有搬 SDK 和重复的默认模式。S1 与 S2 两份参考的默认模式互相冲突，改为按事实所需选择，不强定默认。
- **S3** `keenableai/keenable-hermes-plugin@99ddccbd5ba37f3dc3f7b8c8bf24bed01ddf5ac7`，`skills/keenable-search/SKILL.md`（末次提交 2026-10-25T06:38:10Z），原文 sha256 `8dd37283380f7335d03017385f5d8eb9aa43be06c580d32e02f5681b8cb4c363`。采用只在需要精确引文或存在冲突时深读、prompt 定向、时间语义、401 与 429 分流；没有搬匿名降级、摘要足够即定论、固定数量、客户端传输和参数表。
- **S4** 同一仓库与提交，`skills/keenable-research/SKILL.md`（末次提交 2026-10-25T06:38:10Z），原文 sha256 `3169a23e86ed0c167814dff0b8f850a092e5dde9eb7af7bf93dea5ec6d5dbc9e`。采用已答、冲突、未答三种状态，只补缺口，边际收益低时停止，限流时不循环；没有搬固定 3–6 题、只跟进一次、固定轮数或并发要求。
- **S5** `exa-labs/exa-mcp-server@55cc85c7305117aea538ea0b9dc7d19523be0c6a`，`skills/search/SKILL.md`（末次提交 2026-04-22T04:27:41Z），原文 sha256 `0aacd119c70b57144e7358c5829061a0d25a734ea29afb668392861250c9e42f`。采用其 Gotchas 中「相似候选不等于满足条件或已经验证」；没有搬厂商独占与禁止换源、强制子代理和模型、以 numResults 冒充审过的来源数。

S1–S5 的许可都是 MIT，版权行分别为：S1 与 S2 `Copyright (c) 2026 Exa Labs, Inc.`，S5 `Copyright (c) 2025 Exa Labs`，S3 与 S4 `Copyright (c) 2026 Keenable`。这些版权行连同 OpenMinis 的版权行合并在 `skills/luno-core/LICENSE.retrieval-sources.txt`（sha256 `4053fcd4931d9730ca91f63deabb58e69c8c7a2aee6b058cfc2d32371712ce01`）里随包分发，不能只留来源链接。

**精选边界**：Exa 的 `common-mistakes.md`、`prompting-and-patterns.md` 与已选的 search、contents 重复，没有另行吸收；同义的客户端技能、SDK、Agent、监控、SELECT、求职和安装器都不纳入。整体拒绝的内容有：禁止换源、强制子代理或模型、固定题数、条数或轮数、401 匿名降级、摘要直接定论、厂商独占路由。历史内容只用于辨析语义，没有因此启用新产品。

**官方接口文档**：以下页面 2026-11-01 都返回 HTTP 200。它们没有可确认的源仓库、提交或文件末改日期，也没有提供版权行，表达的再分发许可没有裁定，因此只改写接口事实，不转载正文，也不套用技能的 MIT。追新时重取原 URL 并比对快照；取回日期不能当作发布日期。

- `https://docs.keenable.ai/api-reference/search.md`：日期参数 before 包含当天整日；query_time 的日期按 UTC 零点计，并受当时索引限制，不是历史原文。
- `https://docs.keenable.ai/api-reference/fetch.md` 与 `https://api.keenable.ai/openapi.json`（0.1.24）：search 用 POST，fetch 用 GET 查询参数；live 默认为 false；prompt 是定向合成，不能代替事实验证；published_at 的类型存在冲突，没有写死。
- `https://docs.keenable.ai/authentication.md` 与 `https://exa.ai/docs/admin/error-codes`：认证、额度与权限、401 和 429 的分流以及 Retry-After。
- OnlyBoxes 的官方文档和实测结论在 `skills/luno-ops/references/onlyboxes-baseline.md`，这里不重复。

**历史成品哈希**：2026-11-01 制稿的 `luno-core/references/retrieval.md` 的 SHA-256 为 `4d5061133bce8061bc8e00e26dbb90e1adb7a0aef42e86e895fe1354074d7766`。当时 S1–S5 的逐文件复查基线是各固定提交加这个成品哈希；它不用于当前部署判等。

## luno-sync

**openai/skills@`49f948faa9258a0c61caceaf225e179651397431`**（提交时间 2026-06-24T02:36:12Z；2026-11-05 经公开 API 确认可取）：取自 `skills/.system/skill-creator/`，许可 Apache-2.0，许可原字节随包为 `LICENSE.skill-authoring.txt`。

- 精选改写进 `references/skill-authoring.md`，只留技能专属的增量；通用书写启发式在 `references/agent-document-writing.md`。
- 校验器 `scripts/quick_validate.py` 源自上游的 `quick_validate.py`，已在本地修改。
- 两个文件各保留一行 Apache-2.0 修改声明。已去掉 Codex 专用件，初始化器已退役。
- 已知缺口：历史上端侧退役的未闭合记录没有补证，不能视为已完成。

**mattpocock/skills@`6fd947921b935b7e1e69293a200400f0fdd5c15f`**（直接取自上游 GitHub，不经市场）：`skills/productivity/writing-for-agents/SKILL.md`（该文件 sha256 `551adca942227b44192edba88acd4e8db911f0121ce58ad16944ccf6a896a74a`）→ `references/agent-document-writing.md`，是中文适配改写，没有作为独立技能入库。上游事实取自 2026-10-07 的核对记录，补登记时没有重新取上游。

- 未采纳 `SKILL-MECHANICS.md` 的调用机制（`disable-model-invocation`、按调用拆分、router skill）。
- 未采纳 leading words：中文锚词没有本端证据，不推广「一词代替多句」。
- 未把 negation 当作普遍定律，不据此改写现行的禁令式表述。
- 「按序列拆分」只作启发式，不授予派发权限，派发仍按各入口和子代理的规则。

## luno-ops

**openclaw/openclaw@`e4129b6375e3179be5d9ed0a56a35f2871f4e73b`**（2026-09-12）：`skills/github/SKILL.md` → `references/github.md`。精选改写时压入了凭据和远端对象的流程条款，没有搬运上游的命令示例；上游的 GitHub 版和市场版之间另有较大差异。2026-10-11 实测上游可访问。许可为 MIT：该提交根 `LICENSE` 的头三行含 `Copyright (c) 2026 OpenClaw Foundation`；2026-11-06 按该提交逐字节取回，1170 B，sha256 `73571b25…1c29d`，全文随包为 `LICENSE.openclaw.txt`。原完整快照只在 Git 历史中。

**自有表述的资源**：

- `references/service-runtime.md` 的服务排障节于 2026-11-06 依据官方文档（systemd 的 systemctl 与 journalctl、PM2、Docker Compose CLI、nginx 的运行控制与配置测试）独立重写；授权、确认和秘密投影条款是本技能的自有规则。它取代了已移除的 linux-service-triage 来源。
- `references/cfst.md` 的固定用法和脚本由用户 2026-10-30 指定，脚本行为据 2026-10-31 静态核对，没有实际执行测速。
- `references/onlyboxes-baseline.md` 自带 OnlyBoxes 官方文档链接、访问日期和实测证据层。

## luno-minis

全部来自 **OpenMinis/MinisSkills@`164395f193a56e3507ca98415383c7c16780da00`**，精选改写进 `references/runtime.md`〈本机特性〉，许可见〈OpenMinis/MinisSkills〉，完整 MIT 正文随包为 `LICENSE.openminis.txt`。

- `ios-dev/SKILL.md` → iSH 文件与进程异常一段。许可依据 `ios-dev/LICENSE`（MIT）。正文所列复制样本之外的上游所述行为，本机未复核。
- `codex-on-ish/SKILL.md` → Codex/iSH TLS 排障一段。许可按 2026-10-25 的 MIT 裁定。
- `apple-reminders/SKILL.md` 第 94–103 行 → 原生 `apple-*` 条款之后关于原生查询完整性的一段。许可依据根 `LICENSE`（MIT，`Copyright (c) 2026 OpenMinis`）。

## luno-review

**anthropics/knowledge-work-plugins@`d3ee81913e5e179273313345847a2a4f42449bd2`**（2026-09-11）：`engineering/skills/code-review/SKILL.md` → `references/code-review.md`。精选改写了上游的四维清单和输出要素；架构维、依赖纪律、结构整改和诚实与分歧是自撰或扩写的；GitHub 长版没有整体采用。许可 Apache-2.0，原字节随包为 `LICENSE.code-review.txt`（11607 B，sha256 `a6946284993aeec75c7d75906064b66210c46051e562077efb30eb6dcfe72e26`）。在线可取性未复核。

- 2026-10-16 许可补证：从旧私有 `LucaLin233/Agent` 的 `ee75bb6` 取回原 `code-review` 市场发布物，1302 B，sha256 `3612de8f2c897f98ad20a46f5e0c9f8c6f160873b1e7f44def0bb2ff96ee3451`。实际吸收的四维清单原文 649 B，sha256 `adac810be9904bfb1e479b5bfc547b475ce4f6abab0e7ab3a3952090182bd6b5`，与[固定上游提交的同一段](https://github.com/anthropics/knowledge-work-plugins/blob/d3ee81913e5e179273313345847a2a4f42449bd2/engineering/skills/code-review/SKILL.md)逐字节相等。该提交的[完整 LICENSE](https://github.com/anthropics/knowledge-work-plugins/blob/d3ee81913e5e179273313345847a2a4f42449bd2/LICENSE) 为 Apache-2.0；目标提交根目录的 NOTICE 实读为 404。
- 这次补证只覆盖当前采用片段的可追溯许可；原市场整包的许可仍未决，不声称已核。

**anthropics/claude-plugins-official@`fa4eb54397ee2faccb6940512a19c017cb1337f3`**（2026-11-05 核对，上游可取）：`plugins/code-review/commands/code-review.md`、`plugins/pr-review-toolkit/agents/silent-failure-hunter.md`、`plugins/pr-review-toolkit/agents/pr-test-analyzer.md` → `references/code-review.md`。只吸收按适用目录核对规范、具体指出宽泛 catch 或 fallback 隐藏的错误、说明测试建议能抓住哪类回归这三条判据。许可 Apache-2.0（插件 LICENSE；根目录和目标路径的 NOTICE 实读均为 404），随包为 `LICENSE.anthropic-plugins.txt`。

**mattpocock/skills@`5beb35b040e3de97e54fa9e386d7e42d15c295c2`**：

- `skills/productivity/grilling/SKILL.md` → `SKILL.md`〈输出〉：只吸收提问按依赖分层。
- `skills/engineering/tdd/SKILL.md` → `references/code-review.md`〈四、审查过程要点〉：只吸收期望值须有独立来源的判据。
- 未采纳 design tree 全量穷举、自动派子代理和强制 TDD。

**mattpocock/skills@`4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`**（均进 `references/code-review.md`）：

- `skills/engineering/code-review/SKILL.md`：只作代码双轴本次比照的来源，不冒充旧的固定版本，不替代五维检查、授权或独立审查。
- `skills/engineering/codebase-design/{SKILL.md,DEEPENING.md,DESIGN-IT-TWICE.md}`：只吸收删除抽象后核对复杂度去向和调用方负担的判据。
- `skills/engineering/improve-codebase-architecture/{SKILL.md,HTML-REPORT.md}`：只吸收架构健康评估先按用户痛点和近期高频变更圈定热点的判据。
- `skills/engineering/domain-modeling/{SKILL.md,DOMAIN-MODELING-FORMAT.md,DOMAIN-MODELING-FORMAT-EXAMPLES.md}`：已登记为取材路径，具体取材边界没有单独记录。

**obra/superpowers@`22f0b463e7a5e579904dd6211a520321035526f7`**：`skills/requesting-code-review/SKILL.md`、`skills/receiving-code-review/SKILL.md`、`skills/verification-before-completion/SKILL.md` → `references/code-review.md`。只吸收采纳反馈前先核对当前调用方、平台和既有设计理由，以及没有消费者就不扩项的判据。

**OpenMinis/MinisSkills@`164395f193a56e3507ca98415383c7c16780da00`**：`evidence-chain-builder/SKILL.md` → `SKILL.md`〈审查〉中事实核证按命题逐项进行的一段；不采用其打分脚本和二分标签门禁。许可依据根 `LICENSE`（MIT），附件为 `LICENSE.openminis.txt`。

## luno-writing

**davila7/claude-code-templates@`c93d4ee1e1a2ffabbc5084ccf4715d10683f4b82`**（2026-09-11）：`cli-tool/components/skills/development/i18n-localization/` → `references/i18n.md`，要点精选并入，原脚本已退役。退役前的市场版与上游逐字节一致（2026-10-11 实测复核），2026-10-11 实测上游可访问。许可为 MIT：该提交根 `LICENSE` 的头三行含 `Copyright (c) 2025 Daniel (San) Ávila`；2026-11-06 按该提交逐字节取回，1075 B，sha256 `15cc073f…a705`，全文随包为 `LICENSE.davila7.txt`。

**mattpocock/skills@`4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`**（2026-11-05 核对，上游可取）：`skills/in-progress/writing-shape/SKILL.md` → `references/prose.md`。只吸收原创和结构编辑时先铺陈受众未知而论证需要的概念、删去或合并没有新增作用的段落这两条判据。

**自有表述**：`references/wordpress.md` 的接口要点于 2026-11-06 依据 [WordPress REST API Handbook](https://developer.wordpress.org/rest-api/reference/) 独立重写；授权、确认和回读条款是本技能的自有规则。它取代了已移除的 wordpress-api-gutenberg 来源。

## luno-memory

**mattpocock/skills@`5beb35b040e3de97e54fa9e386d7e42d15c295c2`**：`skills/engineering/retro/SKILL.md` → `references/maintenance.md` 的固化落点条款，即机械可判定的编码规范违规，先核对既有检查是否实际接通。不采用「没有护栏即缺陷」，也不无条件新建检查器或门禁。

## luno-coding

**mattpocock/skills@`4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`**（2026-11-06 核对）：`skills/engineering/tdd/SKILL.md`、`skills/engineering/implement/SKILL.md`。只吸收〈动手前〉的「沿用领域词表与 ADR 的词汇」「按纵切片而非横向分层推进」，〈改动〉的「不为未出现的用法做投机扩展」，以及 implement 的「收尾时再跑一次完整检查」。

**obra/superpowers@`22f0b463e7a5e579904dd6211a520321035526f7`**（2026-11-06 核对）：`skills/verification-before-completion/SKILL.md`。依据是该文件的「Core principle: Evidence before claims, always」，以及〈Common Failures〉中测试通过需要测试命令输出、之前的运行或「should pass」都不算数的判据。只对应〈交付〉中「附结果证据……不以『应该没问题』或文件已存在代替」这一句；〈改动〉的三条 diff 核对判据是自有流程，不取自上游。

**mattpocock/skills@`5beb35b040e3de97e54fa9e386d7e42d15c295c2`**：`skills/engineering/diagnosing-bugs/SKILL.md`、`skills/engineering/to-tickets/SKILL.md`。改写进〈修正与重构〉（复现入口必须对应同一症状、实跑记录、随机故障的命中率、正确的接缝）和〈动手前〉（按行为切片，机械性宽重构的 expand–contract 例外）。

**自有部分**：〈动手前〉的「验收落成可判定的结果」及其三步组织（定位约定 → 定可判定验收 → 按行为切片推进）是自定判据。2026-11-06 重写〈动手前〉〈改动〉时，上述两个上游未覆盖的条款（只改要改的、沿用风格、孤儿清理、「不可能情形」须有证据、宽重构例外）为自有表述。上游原文为英文，改写后按句自查，没有发现与之同形的句子。

原吸收来源已移除，见〈已移除与退役的来源〉。

## luno-cchp

上游是 GitHub `CCH-HQ/cchp-cli`，包含 `cchp` CLI 和内置的 Agent Skill。

- **取材基线**：`d9da5760a8d2f6ce689c01b98b6c96540513045d`（2026-10-25，CLI v0.1.3，spec v1.0.12）。只有采纳更新且包内正文随之改动时才更新基线；只核对而未采纳时不改基线。
- **许可**：MIT，`Copyright (c) 2026 the cchp contributors`，原文随包为 `skills/luno-cchp/LICENSE.upstream.txt`。上游 MIT 原文和版权行随包分发，中文改写也可以按 MIT 再分发。
- **取材文件**（上游路径）：`skills/cchp/SKILL.md`、`skills/cchp/references/auth.md`、`skills/cchp/references/errors.md`、`skills/cchp/references/output-contract.md`、`skills/cchp/references/pagination.md`、`skills/cchp/references/workflows.md`、`docs/agent-guide.md`、`docs/output-contract.md`、`docs/safety-model.md`、`LICENSE`。
- 契约另以 CLI 内置的 spec、schema、命令元数据、指南和实例只读结果核对，动作前仍要核对当次的版本和契约。本机的非生效副本只用于对照锁定的基线，不代替最新上游，也不覆盖正文。

| 本地文件 | 主要上游来源 | 处理 |
|---|---|---|
| `SKILL.md` | `skills/cchp/SKILL.md`、`docs/agent-guide.md` | 保留「发现 → schema → 调用」、门禁和停止条件；补本端位置、版本、认证和授权边界 |
| `references/interfaces.md` | auth、errors、output-contract、pagination 及 docs 中的契约与安全文档 | 合并认证、直连、错误、分页、流式与下载、重试契约；删去面向人的入门叙述；列表形状、操作字段和分页只在命中操作时按当前内置 spec 核对，不缓存旧表 |
| `references/workflows.md` | `skills/cchp/references/workflows.md` | 保留业务骨架，补范围、变更前后和恢复等通用约束；实例数字不落值，以当次实测为准 |
| `references/coverage-rules.md` | `skills/cchp/references/workflows.md` | 迁入本地 request-overrides 的完整分支，保留精选改写和实例验证边界 |

未纳入入门流程、Restish 隔离和本地凭据存储；安装只保留获准安装器的版本、目录、校验和入口验收，不纳入 Homebrew 或源码构建。上游的凭据回退不适用于本端（见 `luno-cchp/SKILL.md`〈认证边界〉）；`--allow-write`、`--confirm` 和上游新增的命令都不扩大授权。

**追新**：不自动跟版。核对时以取材基线为旧 ref，锁定默认分支 HEAD 和技能目录的末次提交，比较期间不改基线。全部取材文件（含目录外的 docs 和 LICENSE）逐个比较哈希，变化项逐文件 diff；404 不等于未变，旧 ref 缺失是新增，新 ref 缺失是删除或可能改名，要结合 compare 的 added、removed、renamed 核对；取不齐就报缺证。文件未变也要对照 CHANGELOG、最新 release 和 CLI 与 spec 的实际契约。门禁、退出码、输出、分页、错误、认证、安全与脱敏、参数与 schema、默认值、重试与超时、流式与下载中任一项变化都算契约变化；CLI 实现、安装方式或面向人界面的变化不能用来排除契约变化。判定无需跟版，必须同时有取材文件 diff 为空和 CHANGELOG、release 未见上述语义改动的正面证据。需要跟版时，先列出上表四个本地文件的受影响小节、旧到新的差异和实例兼容性，再按 `luno-sync/references/sync-workflow.md` 和当次授权处理；核对本身不授权实施或部署，包变化后重算部署哈希并以部署回读为准。上游只新增命令而本端没有授权场景时，不补步骤。

## luno-surge

自编范围：`SKILL.md`、`references/command-reference.md` 及 `references/plugin-authoring.md` 承载本端工作流、接口事实与安全差异，不是完整官方文件的译本；本次未加入官方叙述原文摘录。以后确需短摘录，须记录来源、版本、位置、长度、用途及改编范围，核累计取用和可披露的许可证据，不假定统一额度。Surge 材料不因根 MIT 或 OpenMinis 通知而获无界分发权。

**官方来源例外**：官方上游是 Surge for macOS 应用包，不是 GitHub 技能仓库。取源方式、包身份校验、逐文件哈希和许可边界写在 `skills/luno-surge/references/SOURCE.md`，机器记录是 `skills/luno-surge/references/upstream-manifest.json`。运行资料由本项目独立组织，不再要求补入官方原件，官方原件和 logo 不进入公开仓库或运行包；来源哈希只保留历史证据，不作为分发许可；这个例外只对该对象有效（见 `luno-sync/SKILL.md`〈真源与落点〉）。

**OpenMinis/MinisSkills@`164395f193a56e3507ca98415383c7c16780da00`**：精选改写的同机回环内容，不是 Surge.app 的官方更新，与官方来源哈希无关；在线可取性和当前设备行为都未复核。

- `ios-dev/SKILL.md`、`ios-dev/references/loopback.md`、`coredevice-toolkit/references/SURGE_LOOPBACK.md` → `references/diagnostics.md`〈CoreDevice/RSD 同机回环（第三方报告，非本机验收）〉。许可依据根 `LICENSE` 和 `ios-dev/LICENSE`（均为 MIT）。
- 许可附件为 `LICENSE.openminis.txt` 和 `LICENSE.openminis-ios-dev.txt`，README 与 LICENSE 的不一致及其裁定见〈OpenMinis/MinisSkills〉。`references/SOURCE.md`〈第三方精选改写〉只保留指向本文件的简短说明。

## 已移除与退役的来源

- **luno-coding 原吸收上游**（2026-11-06 公开快照时移除）：原上游没有 LICENSE 文件和版权行（2026-10-20 实查全树及 30 次提交历史），许可材料不完整，不具备公开分发条件，因此不随仓库分发其原件，来源注释和登记一并移除。〈动手前〉〈改动〉两节改按可公开取用的 MIT 上游重写，见〈luno-coding〉。原快照（2518 B）只作旧私有 `LucaLin233/Agent` 的历史溯源，不是本仓库的来源。重写时按句人工对照了该原文，重写后的两节没有与之同形的句子；这是逐句比对，不是工具全量判等，不作「零相似」这样更强的断言。
- **linux-service-triage**（luno-ops，2026-11-06 公开快照时移除）：旧三文件已从 `02f82fb^` 找回，其中 `SKILL.md` 为 3209 B，sha256 `6029658dba3841a9503d18af2c80f448dd45795ae6b90f1aa7b23f96e7daece2`；没有 license 字段或许可证附件。元信息给出的完整提交为 `8d4113eba2202d4cbbbc66ff6c429d846fdcd800`，但原上游两个同名 skills 仓库（clawdbot 与 openclaw 名下）对该提交都返回 404。许可缺口保留，不得虚构。服务排障节已按官方文档独立重写（见〈luno-ops〉）；没有持有上游原文，所以没有做逐句比对；本仓库不再含该上游文件。
- **wordpress-api-gutenberg**（luno-writing，2026-11-06 公开快照时移除）：原上游仓库和提交已 404，许可状态从未记录，缺口保留。接口要点已独立重写为自有表述（见〈luno-writing〉），来源注释和「吸收件」标注已移除。没有持有上游原文，无法逐句对照，因此不就是否含原句作断言，只声明不再以该上游为来源。原 10 个文件只作旧私有 `LucaLin233/Agent` 的历史溯源。
- **nexttrace**（2026-11-01 退役，仅仓库侧）：`nxtrace/NTrace-core@7ff73b2c51f9f37a9bc1d6139b7053948f0250db`（2026-09-13），原有八个文件，另加同一提交根 LICENSE 的包装附件；七个 references 加 LICENSE。来源以及与固定 licensed ZIP 的逐文件判等历史见 2026-09-21 的归档；不自动更新。

## 追新核对

通用判据见 `luno-sync/SKILL.md`〈真源与落点〉：只比对上游 GitHub 仓库的默认分支 HEAD、目标文件的末次提交和内容哈希，并与本地逐字 diff。补充以下做法：

- 先查默认分支的 `/commits/HEAD`，再按路径查逐文件 commits；按固定提交复查日期时，在同一查询上加 `&sha=<固定提交>`。文件日期取 committer 日期，不用目录的最后更新日期代替。
- `releases/latest` 返回 404 只说明没有 latest release，要再查同仓库的 `/releases?per_page=1`，不能把没有 tag 当作没有更新。
- 取得新提交后，在该上游的独立克隆里执行 `git diff <固定提交> <新提交> -- <文件路径>`，核对正文和 LICENSE，不自动覆盖本地取舍。
- 没有仓库的文档页，重取原 URL 并比对快照；取回日期不能当作发布日期。

## luno-surge 输出脱敏的保证边界

本节不是来源记录，暂时没有更合适的位置，所以单列于此。它是历史判据，不是对自由 Shell 的强制保证。边界于 2026-09-16 确立，实现与覆盖范围于 2026-10-11 变更。

**2026-09-16 的覆盖范围**：

- 带键名的认证字段（`authorization`、`proxy-authorization`、`auth`、`authz`，键可带引号）分三种情形处理。① 引号值按引号配对，双引号和单引号各有自己的字符类与转义，键与值之间允许换行缩进，因此覆盖多行 JSON 和双引号内含单引号的情况。② 带方案词（`Bearer`、`Basic`、`Digest`、`Negotiate`、`NTLM`、`aws4-hmac-sha256`）时抹除该字段整行。③ 其余裸值以逗号、分号或换行为界，不以 `}`、`]` 为界，否则 `Authorization: SYNTH}SECRET` 会在闭合符处截断，泄漏尾部；值以抹除标记开头时，只保留标记和其后的结构闭合符，其余残余丢弃。
- 敏感键（`password`、`passwd`、`pwd`、`psk`、`private_key`、`token`、`api_key`、`x_key`、`secret`、`credential`）的引号值、裸值和平面数组值，以及已知 token 前缀（`sk`、`ghp`、`github_pat`、`xox*`）。
- `user` 和 `username` 也在抹除范围内。2026-09-16 的判定是：字段名不能证明其值永远不敏感，移除它们属于收窄保护，必须由用户明确确认后才能放宽，确认前维持默认抹除。

**2026-09-16 的不覆盖范围**，不得据此宣称完整脱敏：

- 没有键名的裸方案词，例如 `x Bearer <值> end`。这是刻意为之，避免误抹普通英文 `basic configuration failed`。
- 嵌套在数组或对象里的敏感键，例如 `{"token":[["x"]]}`。2026-10-11 起，JSON 文档（任意布局）中的这类情况已被覆盖；非 JSON 文本形态仍不覆盖。
- Unicode 转义的键名，例如 `{"to\u006ben":"x"}`。
- 整体编码或 Base64 载荷。

因此脱敏输出不等于可以对外发布的安全日志。作为诊断输出前仍需人工检查，对外分享前还要另行核对。

**2026-10-11 的变更**（2026-10-11 记录时尚未部署或平台验收）：

- 实现收敛为共享模块 `scripts/_privacy.py`，由 `surge_cli.py`、`surge_ios.py`、`test_policy_descriptor.py` 共用。`surge_cli.py` 此前完全没有脱敏，成功 JSON、错误、`profile diff` 和 `--check` 的返回都原样输出；此次在全部输出边界接入了脱敏。
- 新增覆盖：前缀驼峰键（如 `proxyPassword`）、复数键（如 `tokens`）、认证键（`Authorization`、`proxy-authorization`、`auth`、`authz` 及其前缀驼峰变体）的结构化整值替换、Profile 代理行（如 `PROXY-A = https, host, 443, user, <PASS>`，含中文或 Unicode 节点名）、内层转义的 JSON 串，以及 JSON 文档（任意布局）中嵌套容器的整值替换。紧凑布局走结构化重排，其他布局按 JSON 字符串 token 就地脱敏并保留原布局。
- 仍不覆盖：没有键名的裸方案词、Unicode 转义键名、整体编码或 Base64 载荷，以及 JSON 嵌在普通文本中时的嵌套容器。
- 有据例外：`surge_cli.py` 的 `--help` 和 `help <cmd>` 走不脱敏的路径。它们输出编译期的帮助字面量，含变量名 `SURGE_API_KEY`，脱敏会把变量名改写成 `<redacted>`；其中不含运行时数据。
- Profile 代理行的凭据字段位置表按协议常识和包内示例实现，没有与官方手册核对（离线取不到）；类型表只列位置明确的协议，以免误抹策略组行。

**输出契约**（2026-09-16 确立，使用方必须遵守）：

1. 裸认证行的整段都视为敏感值。冒号或等号之后的整段内容都是该字段的值，不是「凭据加诊断字段」，所以 `Authorization: <值> status=502` 里的 `status=502` 会一并丢弃。空格不是诊断字段的分隔符，写成 `key=value` 也没有例外（`Authorization: <值> status:502` 同样整段丢弃）。诊断字段只能改为独立的结构化字段或独立的行（如另起一行 `status=502`），不得与认证值同行混排。
2. 值只限同一行。换行即该字段结束，下一行是独立内容。因此冒号后直接换行的续行凭据 `Authorization:\n<裸凭据>` 不在覆盖范围内，生产者不得输出这种裸续行凭据；而 `Authorization:\nstatus=502` 这样下一行是普通内容的，按独立内容原样保留。
3. 逗号和分号只是第 ③ 种情形（其余裸值）的终止符，其后的内容视为独立字段而保留，所以契约禁止在这一情形里用 `,` 或 `;` 在值中承载凭据（`Authorization: <标记>,SECRET` 不在覆盖范围内）。第 ② 种带方案词的字段整行抹除，不适用本条：`Authorization: Bearer <值>,status=502` 里的 `status=502` 同样会被抹掉，同行的诊断信息须移到独立行或独立的结构化字段。
4. 多行结构化值与「同一行」规则不冲突。规则 2 约束的是裸值；`{"auth":\n"值"}` 这种键与值之间换行缩进的引号值属于第 ① 种情形，正常脱敏。
5. 生产者不满足上述任一条时，必须先解析和规范化认证字段再调用脱敏，或者拒绝输出有歧义的段落。


## 优化后合并候选的路径迁移

上文旧技能名和本地路径是取材时的历史坐标，固定提交、日期、作者、许可和缺口全部保留；不是活动加载入口。本次候选将review/sync迁入core，CCHP/Minis/LobeHub迁入platform，Coding/Writing迁入用户已定名authoring。完整旧身份和真实资源以本版本migration.json及provenance.json为准，不以中间稿新增文件冒充原资源。现役书写启发式未增加合并豁免；本次选择来自用户明确要求，仍需独立预审。

|固定基线真实路径|候选路径|
|---|---|
|`skills/luno-cchp/LICENSE.upstream.txt`|`skills/luno-platform/LICENSE.upstream.txt`|
|`skills/luno-cchp/SKILL.md`|`skills/luno-platform/SKILL.md`、`skills/luno-platform/references/cchp.md`|
|`skills/luno-cchp/SOURCE.md`|`skills/luno-platform/references/cchp-source.md`|
|`skills/luno-cchp/references/coverage-rules.md`|`skills/luno-platform/references/cchp-coverage-rules.md`|
|`skills/luno-cchp/references/interfaces.md`|`skills/luno-platform/references/cchp-interfaces.md`|
|`skills/luno-cchp/references/workflows.md`|`skills/luno-platform/references/cchp-workflows.md`、`skills/luno-platform/references/cchp-workflow-writes.md`、`skills/luno-platform/references/cchp-workflow-usage.md`、`skills/luno-platform/references/cchp-workflow-requests.md`、`skills/luno-platform/references/cchp-workflow-providers.md`、`skills/luno-platform/references/cchp-workflow-tokens.md`、`skills/luno-platform/references/cchp-workflow-import.md`|
|`skills/luno-coding/LICENSE.matt-pocock.txt`|`skills/luno-authoring/LICENSE.matt-pocock.txt`|
|`skills/luno-coding/LICENSE.obra-superpowers.txt`|`skills/luno-authoring/LICENSE.obra-superpowers.txt`|
|`skills/luno-coding/SKILL.md`|`skills/luno-authoring/references/coding.md`|
|`skills/luno-core/SKILL.md`|`skills/luno-core/SKILL.md`、`skills/luno-core/references/execution.md`、`skills/luno-core/references/safety.md`|
|`skills/luno-lobehub/SKILL.md`|`skills/luno-platform/SKILL.md`、`skills/luno-platform/references/lobehub.md`|
|`skills/luno-lobehub/references/access.md`|`skills/luno-platform/references/lobehub-access.md`|
|`skills/luno-lobehub/references/agents.md`|`skills/luno-platform/references/lobehub-agents.md`|
|`skills/luno-lobehub/references/instance.md`|`skills/luno-platform/references/lobehub-instance.md`|
|`skills/luno-lobehub/references/knowledge.md`|`skills/luno-platform/references/lobehub-knowledge.md`|
|`skills/luno-lobehub/references/skills.md`|`skills/luno-platform/references/lobehub-skills.md`|
|`skills/luno-memory/references/maintenance.md`|`skills/luno-memory/references/maintenance.md`、`skills/luno-memory/references/correction.md`|
|`skills/luno-minis/LICENSE.openminis.txt`|`skills/luno-platform/LICENSE.openminis.txt`|
|`skills/luno-minis/SKILL.md`|`skills/luno-platform/SKILL.md`、`skills/luno-platform/references/minis.md`|
|`skills/luno-minis/references/configuration.md`|`skills/luno-platform/references/minis-configuration.md`|
|`skills/luno-minis/references/memory.md`|`skills/luno-platform/references/minis-memory.md`|
|`skills/luno-minis/references/runtime.md`|`skills/luno-platform/references/minis-runtime.md`、`skills/luno-platform/references/minis-runtime-context.md`、`skills/luno-platform/references/minis-runtime-device.md`|
|`skills/luno-minis/references/session-groups.md`|`skills/luno-platform/references/minis-session-groups.md`|
|`skills/luno-review/LICENSE.anthropic-plugins.txt`|`skills/luno-core/LICENSE.anthropic-plugins.txt`|
|`skills/luno-review/LICENSE.code-review.txt`|`skills/luno-core/LICENSE.code-review.txt`|
|`skills/luno-review/LICENSE.matt-pocock.txt`|`skills/luno-core/LICENSE.matt-pocock.txt`|
|`skills/luno-review/LICENSE.obra-superpowers.txt`|`skills/luno-core/LICENSE.obra-superpowers.txt`|
|`skills/luno-review/LICENSE.openminis.txt`|`skills/luno-core/LICENSE.openminis.txt`|
|`skills/luno-review/SKILL.md`|`skills/luno-core/references/review.md`|
|`skills/luno-review/references/code-review.md`|`skills/luno-core/references/code-review.md`|
|`skills/luno-surge/references/http-api.md`|`skills/luno-surge/references/http-api.md`、`skills/luno-surge/references/http-sections.md`|
|`skills/luno-sync/LICENSE.matt-pocock.txt`|`skills/luno-core/LICENSE.matt-pocock.txt`|
|`skills/luno-sync/LICENSE.skill-authoring.txt`|`skills/luno-core/LICENSE.skill-authoring.txt`|
|`skills/luno-sync/SKILL.md`|`skills/luno-core/references/sync.md`|
|`skills/luno-sync/references/agent-document-writing.md`|`skills/luno-core/references/agent-document-writing.md`|
|`skills/luno-sync/references/skill-authoring.md`|`skills/luno-core/references/skill-authoring.md`|
|`skills/luno-sync/references/sync-workflow.md`|`skills/luno-core/references/sync-workflow.md`|
|`skills/luno-sync/references/test-authoring.md`|`skills/luno-core/references/test-authoring.md`|
|`skills/luno-sync/scripts/quick_validate.py`|`skills/luno-core/scripts/quick_validate.py`|
|`skills/luno-writing/LICENSE.davila7.txt`|`skills/luno-authoring/LICENSE.davila7.txt`|
|`skills/luno-writing/LICENSE.matt-pocock.txt`|`skills/luno-authoring/LICENSE.matt-pocock.txt`|
|`skills/luno-writing/SKILL.md`|`skills/luno-authoring/SKILL.md`|
|`skills/luno-writing/references/i18n.md`|`skills/luno-authoring/references/i18n.md`|
|`skills/luno-writing/references/prose.md`|`skills/luno-authoring/references/prose.md`|
|`skills/luno-writing/references/wordpress.md`|`skills/luno-authoring/references/wordpress.md`|

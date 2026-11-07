# 技能来源登记

只记来源、固定版本、许可与恢复线索；活身份唯一见 `tools/sync-targets.json`。不自动跟上游，不缓存当前哈希。历史部署沿革见旧私有 `LucaLin233/Agent` 的 Git 历史（公开快照仓库无该历史）。

## 自编与混合来源

自编：core、sync、ops、lobehub、minis、review、writing、memory。luno-cchp 为精选改写，详细来源见包内 `SOURCE.md`；luno-surge 为自编与官方快照混合，详细来源及官方 Mac 应用包例外见 `skills/luno-surge/references/SOURCE.md`。

### 吸收件登记（批次 `minisskills-absorb-20261025`，2026-10-25）

> 本节只记**来源事实**：上游仓库@完整提交、所取文件、核对日期、改写性质、许可文件状态与块内来源行位置。`README.md` 与 `LICENSE` 的许可标注冲突本批**未裁定**，本节不给分发结论。

| 技能 | 吸收件来源与状态 |
|---|---|
| luno-minis | **第三方精选改写（吸收件）**：上游 `OpenMinis/MinisSkills`@`164395f193a56e3507ca98415383c7c16780da00`（2026-10-25 本地核对；在线可取性未复核），取 `ios-dev/SKILL.md`、`codex-on-ish/SKILL.md`、`apple-reminders/SKILL.md`（:94–103）；**精选改写**后落 `skills/luno-minis/references/runtime.md` 三处——〈本机特性〉末尾两段（iSH 文件／进程异常、Codex/iSH TLS）与原生 `apple-*` 条款之后一段（原生查询完整性），每段正文后各带一行 `来源：`，写明仓库@提交、文件路径、2026-10-25 本地核对、许可状态与「在线可取性及本机行为未复核」。许可状态：根 `LICENSE` 与 `ios-dev/LICENSE` 记载 MIT，`README.md` 标 Apache-2.0，**冲突未裁定**，不据此宣告分发许可；完整 MIT 见 `skills/luno-minis/LICENSE.openminis.txt`。 |
| luno-surge | **第三方精选改写（吸收件；与自编正文、官方快照并存）**：上游 `OpenMinis/MinisSkills`@`164395f193a56e3507ca98415383c7c16780da00`（2026-10-25 本地核对；在线可取性及当前设备行为未复核），取 `ios-dev/SKILL.md`、`ios-dev/references/loopback.md`、`coredevice-toolkit/references/SURGE_LOOPBACK.md`；**精选改写**后落三处——`references/platform-compatibility.md` 新增 `## CoreDevice/RSD 同机回环（第三方报告，非本机验收）`、`references/diagnostics.md` 新增同名 `###` 诊断场景、`references/SOURCE.md` 新增独立二级节 `## 第三方精选补充（2026-10-25）`（**不并入〈模块推送〉，不替换官方快照或哈希**）。三段各带 `来源：` 行，写明仓库@提交、所取文件、2026-10-25 本地核对与「未复核」。许可状态：根 `LICENSE` 与 `ios-dev/LICENSE` 记载 MIT，`README.md` 标 Apache-2.0，冲突未裁定，不据此宣告分发许可。 |
| luno-review | **第三方精选改写（吸收件）**：上游 `OpenMinis/MinisSkills`@`164395f193a56e3507ca98415383c7c16780da00`（2026-10-25 本地核对；在线可取性未复核），取 `evidence-chain-builder/SKILL.md`；**精选改写**后落 `skills/luno-review/SKILL.md`〈审查〉末条之后、`## 边界` 之前一段（事实核证按命题逐项；**不采用**其打分脚本与二分标签门禁），正文后带 `来源：` 行，写明仓库@提交、文件路径、2026-10-25 本地核对、许可状态与「在线可取性未复核」。许可状态：根 `LICENSE` 记载 MIT，`README.md` 标 Apache-2.0，冲突未裁定，不据此宣告分发许可。 |
| luno-core | **第三方精选改写（吸收件）**：上游 `OpenMinis/MinisSkills`@`164395f193a56e3507ca98415383c7c16780da00`（2026-10-25 本地核对；在线可取性及服务可用性未复核），取 `web-content-extractor/SKILL.md`；**精选改写**后落 `skills/luno-core/references/retrieval.md` 末尾一段（既有抓取仍失败时的 Defuddle → Jina 回退，保留上游两者相对顺序，限 URL 与内容获准公开披露），正文后带 `来源：` 行，写明仓库@提交、文件路径、2026-10-25 本地核对、许可状态与「未复核」。许可状态：根 `LICENSE` 记载 MIT，`README.md` 标 Apache-2.0，冲突未裁定，不据此宣告分发许可。 |

**许可裁定（2026-10-25，已决；关闭原 `待条件`）**：上引「冲突未裁定」「本节不给分发结论」为 2026-10-25 当批记录，本段取代之——**决定按 MIT 处理**。依据：该提交的 `LICENSE`（1,066 B，sha256 `2858f336d8173207aa079c4711085a28d22615d464b6a387363f7824116d00f0`）与 `ios-dev/LICENSE`（1,770 B，sha256 `06dfb33ed30ecda0338b8318d8243f36c501281a5d44398a7e3425ce149bd4f3`）实际均记载 MIT（版权行分别为 `Copyright (c) 2026 OpenMinis`、`Copyright (c) 2026 OpenMinis contributors`），`README.md` 标 Apache-2.0 属上游文件自身不一致，**不据 README 改标**。**对外分发含上述正文的产物时，须随附 MIT 版权行（`Copyright (c) 2026 OpenMinis`）与 MIT 许可全文。**

### 吸收件登记（批次 `pocock-absorb-20261025`，2026-10-25）

> 本节只记**来源事实**：上游仓库@完整提交、所取文件、核对日期、改写性质、许可与块内来源行位置。同批五条判据经 LENS 预审（`CBD96A91`）修订后实施。

| 技能 | 吸收件来源与状态 |
|---|---|
| luno-coding | **第三方精选改写（吸收件）**：上游 `mattpocock/skills`@`5beb35b040e3de97e54fa9e386d7e42d15c295c2`（2026-10-19 提交，2026-10-25 本地核对；在线可取性未复核），取 `engineering/diagnosing-bugs/SKILL.md`、`engineering/to-tickets/SKILL.md`；**精选改写**后落 `skills/luno-coding/SKILL.md`〈修正与重构〉（复现入口须对应同一症状、实跑记录、随机故障命中率、正确接缝）与〈动手前〉（行为切片、机械性宽重构的 expand–contract 例外），顶部来源注释随之追加。许可：MIT（`Copyright (c) 2026 Matt Pocock`）；对外分发含该正文须随附 MIT 版权行与许可全文。 |
| luno-review | **第三方精选改写（吸收件）**：上游同上，取 `productivity/grilling/SKILL.md`（`skills/luno-review/SKILL.md`〈输出〉提问依赖分层）与 `engineering/tdd/SKILL.md`（`skills/luno-review/references/code-review.md`〈四、审查过程要点〉期望值独立来源）；两处各带 `来源：` 行。不采用 design tree 全量穷举、自动派子代理、强制 TDD。 |
| luno-memory | **第三方精选改写（吸收件）**：上游同上，取 `engineering/retro/SKILL.md`；**精选改写**后落 `skills/luno-memory/references/maintenance.md`〈写入格式与精简〉固化落点条（机械可判定的编码规范违规先核既有检查是否实际接通），文件顶部新增来源注释。不采用「无护栏即缺陷」或无条件新建检查器、门禁。 |

## 其他来源与许可

| luno-cchp | **第三方改编（含精选改写）**：上游 `CCH-HQ/cchp-cli`；实际取材基线、取材文件与逐文件处理以包内 `skills/luno-cchp/SOURCE.md` 为准，本概览不重复缓存活提交。MIT，`Copyright (c) 2026 the cchp contributors`；许可原文随包 `skills/luno-cchp/LICENSE.upstream.txt`。 |
| luno-coding（上游来源已移除；2026-11-06 公开快照） | 原吸收来源的上游**没有 LICENSE 文件与版权行**（2026-10-20 全树及 30 次提交历史实查），许可材料不完整，不具备公开分发条件，故不随仓库分发其原件，来源注释与登记一并移除。〈动手前〉〈改动〉两节改按可公开取用的 MIT 上游重写：`mattpocock/skills@4ae2317ddb22b046e26455e4f9c9b3aaaf62212d` 的 `skills/engineering/tdd/SKILL.md`、`skills/engineering/implement/SKILL.md`，`obra/superpowers@22f0b463e7a5e579904dd6211a520321035526f7` 的 `skills/verification-before-completion/SKILL.md`，均为精选改写（obra 只对应〈交付〉的「附结果证据…」一句）；本批自定的只有〈动手前〉的「验收落成可判定的结果」与三步组织；上游未覆盖的条款（只改要改的、沿用风格、孤儿清理、「不可能情形」须有证据、宽重构例外）为自有表述。许可原文随包 `skills/luno-coding/LICENSE.matt-pocock.txt`、`skills/luno-coding/LICENSE.obra-superpowers.txt`；逐条「原约束→新来源」映射见当批改稿报告。原快照（2518 B）只作旧私有 `LucaLin233/Agent` 的历史溯源，不作为本仓库来源；本批以该原文按句人工自查，重写后的两节未见与之同形的句子，此为逐句比对、非工具全量判等，不作「零相似」的更强断言。 |
| github（已吸收） | openclaw/openclaw@e4129b6375e3179be5d9ed0a56a35f2871f4e73b（2026-09-12），skills/github/SKILL.md；精选改写至 `skills/luno-ops/references/github.md`；许可 **MIT**（该提交根 `LICENSE`，3 行头为 `Copyright (c) 2026 OpenClaw Foundation`；2026-11-06 按该提交逐字节取回，1170 B／sha256 `73571b25…1c29d`，全文随包 `skills/luno-ops/LICENSE.openclaw.txt`）。原完整快照仅在 Git 历史。 |
| i18n-localization（已吸收） | davila7/claude-code-templates@c93d4ee1e1a2ffabbc5084ccf4715d10683f4b82（2026-09-11），cli-tool/components/skills/development/i18n-localization/；精选至 `skills/luno-writing/references/i18n.md`；原脚本退役；许可 **MIT**（该提交根 `LICENSE`，3 行头为 `Copyright (c) 2025 Daniel (San) Ávila`；2026-11-06 按该提交逐字节取回，1075 B／sha256 `15cc073f…a705`，全文随包 `skills/luno-writing/LICENSE.davila7.txt`）。 |
| nexttrace（已退役；仅仓库侧，2026-11-01） | nxtrace/NTrace-core@`7ff73b2c51f9f37a9bc1d6139b7053948f0250db`（2026-09-13），原八文件＋同提交根 LICENSE 包装附件；七 references＋LICENSE。来源与固定 licensed ZIP 的逐文件判等历史见归档 2026-09-21；不自动更新。 |
| wordpress-api-gutenberg（来源已移除；2026-11-06 公开快照） | 原吸收来源的上游仓库与提交已 404、许可状态从未记录（缺口保留）。首条接口要点已依据 WordPress REST API Handbook 独立重写为自有表述（链接见 `skills/luno-writing/references/wordpress.md` 顶部注释），来源注释与「吸收件」标注移除；**未持有上游原文、无法逐句对照**，故不就「是否含原句」作断言，只声明本批不以该上游为来源。原 10 文件只作旧私有 `LucaLin233/Agent` 的历史溯源。 |
| skill-authoring（已吸收） | openai/skills@49f948faa9258a0c61caceaf225e179651397431（2026-06-24），skills/.system/skill-creator/；Apache-2.0，精选至 `skills/luno-sync/references/skill-authoring.md`，校验器与许可原字节迁入该技能。已去 Codex 专用件；初始化器退役。历史端侧退役未闭合记录未补证，不据本轮压缩假称完成。 |
| writing-for-agents | 上游 GitHub 直取（非市场） | `mattpocock/skills` → `skills/productivity/writing-for-agents/` | `6fd947921b935b7e1e69293a200400f0fdd5c15f` | — | **MIT**（`Copyright (c) 2026 Matt Pocock`）；上游 `SKILL.md` sha256 `551adca942227b44192edba88acd4e8db911f0121ce58ad16944ccf6a896a74a`。**精选吸收（吸收件）**：正文落 `skills/luno-sync/references/agent-document-writing.md`，为**中文适配改写、非原文翻译**，不整段照抄；未作为独立技能入库，`skills/upstream/` 无对应目录。上游事实取自 2026-10-07 记录（本行按证据补登记，本批未重取上游），适配排除项见该资源〈来源与许可〉。 |

**2026-10-16 许可补证**：从旧私有 `LucaLin233/Agent` 的 `ee75bb6` 取回原 `code-review` 市场发布物，1302B／sha256=`3612de8f2c897f98ad20a46f5e0c9f8c6f160873b1e7f44def0bb2ff96ee3451`。实际吸收的四维清单原文649B／sha256=`adac810be9904bfb1e479b5bfc547b475ce4f6abab0e7ab3a3952090182bd6b5`，与 [固定上游提交同段](https://github.com/anthropics/knowledge-work-plugins/blob/d3ee81913e5e179273313345847a2a4f42449bd2/engineering/skills/code-review/SKILL.md)逐字节相等；该提交[完整LICENSE](https://github.com/anthropics/knowledge-work-plugins/blob/d3ee81913e5e179273313345847a2a4f42449bd2/LICENSE)为Apache-2.0，原字节随 `luno-review/LICENSE.code-review.txt` 分发（11607B／sha256=`a6946284993aeec75c7d75906064b66210c46051e562077efb30eb6dcfe72e26`），目标提交根NOTICE实读404。此处补齐当前采用片段的可追溯许可，不声称原市场整包授权已核。`linux-service-triage` 旧三文件已从 `02f82fb^` 找回，SKILL.md 3209B／sha256=`6029658dba3841a9503d18af2c80f448dd45795ae6b90f1aa7b23f96e7daece2`；无license字段或许可证附件，元信息给出的完整提交为 `8d4113eba2202d4cbbbc66ff6c429d846fdcd800`，原上游两个同名 skills 仓库（clawdbot 与 openclaw 名下）对该提交均 404，许可缺口仍保留，禁止虚构；**2026-11-06 公开快照**：服务排障节已依据官方文档（systemd／journalctl、PM2、Docker Compose、nginx）独立重写为自有表述，来源注释与登记移除；上游原件 404、许可缺口保留，未持有原文故不作逐句比对，本仓库不再含该上游文件。

### 本批增量来源与许可附件登记（2026-11-05）

| 对象 | 上游增量、路径、许可与包内附件 |
|---|---|
| luno-coding | `mattpocock/skills@5beb35b040e3de97e54fa9e386d7e42d15c295c2`；`skills/engineering/diagnosing-bugs/SKILL.md`、`skills/engineering/to-tickets/SKILL.md`；2026-10-25；MIT，精选改写；`skills/luno-coding/LICENSE.matt-pocock.txt`。 |
| luno-memory | 同上游完整提交；`skills/engineering/retro/SKILL.md`；2026-10-25；MIT，精选改写；`skills/luno-memory/LICENSE.matt-pocock.txt`。 |
| luno-sync | `mattpocock/skills@6fd947921b935b7e1e69293a200400f0fdd5c15f`；`skills/productivity/writing-for-agents/SKILL.md`；2026-10-07；MIT，精选改写；`skills/luno-sync/LICENSE.matt-pocock.txt`。 |
| luno-core | `mattpocock/skills@4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`；`skills/engineering/triage/SKILL.md`、`AGENT-BRIEF.md`、`OUT-OF-SCOPE.md`、`skills/productivity/handoff/SKILL.md`；2026-11-05；MIT，精选改写；`skills/luno-core/LICENSE.matt-pocock.txt`。OpenMinis 来源保留完整提交与 `skills/luno-core/LICENSE.retrieval-sources.txt`。 |
| luno-writing | `mattpocock/skills@4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`；`skills/in-progress/writing-shape/SKILL.md`；2026-11-05；MIT，精选改写；`skills/luno-writing/LICENSE.matt-pocock.txt`。 |
| luno-review | `mattpocock/skills@4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`；`skills/engineering/code-review/SKILL.md`、`codebase-design/{SKILL.md,DEEPENING.md,DESIGN-IT-TWICE.md}`、`domain-modeling/{SKILL.md,DOMAIN-MODELING-FORMAT.md,DOMAIN-MODELING-FORMAT-EXAMPLES.md}`、`improve-codebase-architecture/{SKILL.md,HTML-REPORT.md}`；2026-11-05；MIT，精选改写；另有 `obra/superpowers@22f0b463e7a5e579904dd6211a520321035526f7` 三路径（MIT）与 `anthropics/claude-plugins-official@fa4eb54397ee2faccb6940512a19c017cb1337f3` 三路径（Apache-2.0）；附件为 `skills/luno-review/LICENSE.matt-pocock.txt`、`LICENSE.obra-superpowers.txt`、`LICENSE.anthropic-plugins.txt`、`LICENSE.openminis.txt`。 |
| luno-surge | 官方上游是 Surge Mac 应用包，非 GitHub 技能仓库；来源与 manifest 为本包 `skills/luno-surge/references/SOURCE.md`、`skills/luno-surge/references/upstream-manifest.json`；OpenMinis 固定提交 `164395f193a56e3507ca98415383c7c16780da00` 的精选改写，MIT 原件附件为 `skills/luno-surge/LICENSE.openminis.txt`（sha256 `2858f336d8173207aa079c4711085a28d22615d464b6a387363f7824116d00f0`）与 `skills/luno-surge/LICENSE.openminis-ios-dev.txt`（sha256 `06dfb33ed30ecda0338b8318d8243f36c501281a5d44398a7e3425ce149bd4f3`）；README Apache-2.0／LICENSE MIT 冲突保留，不外推许可或发布授权。 |
| luno-review | OpenMinis 固定提交 `164395f193a56e3507ca98415383c7c16780da00`；MIT 通知附件 `skills/luno-review/LICENSE.openminis.txt`。 |

## 脱敏边界（历史判据，非自由 Shell 强制保证）

**surge 输出脱敏的保证边界**（2026-09-16，四轮 LENS 复审后确立；实现与覆盖范围**已于 2026-10-11 变更**，见本段末「2026-10-11 变更」）：
- 覆盖：带键名的认证字段（`authorization`/`proxy-authorization`/`auth`/`authz`，键可带引号）分三态——① 引号值按引号配对（双/单引号**各自**的字符类与转义，键与值之间允许换行缩进，覆盖多行 JSON 与「双引号内含单引号」）；② 带方案词（`Bearer`/`Basic`/`Digest`/`Negotiate`/`NTLM`/`aws4-hmac-sha256`）取该字段整行；③ 其余裸值以**逗号/分号/换行**为界（**不以** `}`、`]` 为界——否则 `Authorization: SYNTH}SECRET` 会在闭合符处截断而泄漏尾部；值以抹除标记开头时只保留标记及其后的结构闭合符，其余残余丢弃）;另有敏感键（`password`/`passwd`/`pwd`/`psk`/`private_key`/`token`/`api_key`/`x_key`/`secret`/`credential`）的引号/裸值/平面数组值、已知 token 前缀（`sk`/`ghp`/`github_pat`/`xox*`）。**含 `user`/`username`**（2026-09-16 复审判定：字段名不能证明其值永远非敏感，移除属收窄保护，须用户明确确认后才可放宽；未确认前维持默认抹除）。
- **不覆盖（保证边界，不得据此宣称完整脱敏）**：无键名的裸方案词（如 `x Bearer <值> end`，不识别——刻意为之，避免误抹普通英文 `basic configuration failed`）；嵌套数组/对象内的敏感键（`{"token":[["x"]]}`）**【2026-10-11 已替代：JSON 文档（任意布局）下按结构整值替换已覆盖，见本段末变更块；非 JSON 文本形态仍不覆盖】**；Unicode 转义键名（`{"to\u006ben":"x"}`）；整体编码或 Base64 载荷。
- 因此该脱敏输出**不等于可对外发布的安全日志**：作为诊断输出前仍需人工检查；对外分享前另行核对。
- **2026-10-11 变更（本批候选实现，尚未部署/平台验收）**：
  - 实现收敛为共享模块 `scripts/_privacy.py`，由 `surge_cli.py`／`surge_ios.py`／`test_policy_descriptor.py` 三脚本共用；**`surge_cli.py` 此前无任何脱敏**（成功 JSON、错误、`profile diff`、`--check` 返回均原样输出），本批已在全部输出边界接入。
  - **新增覆盖**：前缀驼峰键（`proxyPassword`）、复数键（`tokens`）、**认证键的结构化整值替换**（`Authorization`／`proxy-authorization`／`auth`／`authz` 及其前缀驼峰变体）、**Profile 代理行**（`PROXY-A = https, host, 443, user, <PASS>`，含中文／Unicode 节点名）、内层转义 JSON 串、以及 **JSON 文档（任意布局）**下的嵌套容器整值替换——紧凑布局走结构化重排，其余布局按 JSON 字符串 token 就地脱敏并**保留原布局**。
  - **仍不覆盖**：无键名的裸方案词、Unicode 转义键名、整体编码或 Base64 载荷、以及 **JSON 嵌在普通文本中**的非 JSON 文本形态下的嵌套容器。
  - **有据例外**：`surge_cli.py` 的 `--help`／`help <cmd>` 走不脱敏路径——那是编译期帮助字面量（含变量名 `SURGE_API_KEY` 字样），走脱敏会把变量名改写成 `<redacted>`；不含运行时数据。
  - Profile 代理行的**凭据字段位置表**按协议常识与包内示例实现，**未与官方手册核对**（离线取不到）；类型表只列位置明确的协议，避免误抹策略组行。
- **输出契约（2026-09-16 复审确立，使用方须遵守）**：
  1. **裸认证行整段视为敏感值**：冒号/等号之后的整段内容都是该字段的值，不是「凭据＋诊断字段」。因此 `Authorization: <值> status=502` 里的 `status=502` 会被一并丢弃——**空格不是诊断字段分隔符**，也不存在「写成 `key=value` 就能保留」的例外（`Authorization: <值> status:502` 同样整段丢弃）。诊断字段只能改为**独立的结构化字段或独立行**（如另起一行 `status=502`），不得与认证值同行混排。
  2. **值仅限同一行**：换行即该字段结束，下一行视为独立内容。因此 `Authorization:\n<裸凭据>`（冒号后直接换行的续行凭据）**不在覆盖内**，生产者不得输出裸续行凭据；`Authorization:\nstatus=502` 这类下一行普通内容则按独立内容原样保留。
  3. **逗号/分号是「其余裸值」的终止符**（仅限三态中的第 ③ 类）：该分支的尾随内容视为独立字段而保留，故契约**禁止**在这一分支用 `,`/`;` 在值里承载凭据（`Authorization: <标记>,SECRET` 不在覆盖内）。**带方案词的字段（第 ② 类）取整行抹除**，不适用本条——`Authorization: Bearer <值>,status=502` 里的 `status=502` 同样会被抹掉，同行诊断须移到独立行或独立结构化字段。生产者无法保证时应先解析／规范化认证字段，或拒绝输出该歧义段。
  4. **多行结构化值与上述「同一行」不冲突**：规则 2 约束的是**裸值**；`{"auth":\n"值"}` 这种键与值之间换行缩进的引号值属规则 ① 的覆盖范围，正常脱敏。
  5. 生产者不满足上述任一条时，须先解析／规范化认证字段再调用脱敏，或拒绝输出歧义段。

## 执行正文来源详情下沉

2026-11-08：以下保留core/review/coding的完整来源说明，供分批压缩运行正文时引用；仅来源元信息整理，不改变取材或许可结论。对应正文实际下沉后，本节为详情位置；必要署名/许可与指针留在正文。既有历史位置描述不作为现役加载要求；不声称本轮重新访问上游。

<!-- 来源：mattpocock/skills@4ae2317ddb22b046e26455e4f9c9b3aaaf62212d；路径：skills/engineering/triage/SKILL.md、skills/engineering/triage/AGENT-BRIEF.md、skills/engineering/triage/OUT-OF-SCOPE.md；2026-11-05 核对；MIT，Copyright (c) 2026 Matt Pocock；精选改写，仅吸收按行为概念查既有实现与拒绝理由的判据；上游可取；完整许可见 `luno-core/LICENSE.matt-pocock.txt`；登记见 skills-sources.md。 -->

来源：OpenMinis/MinisSkills@164395f193a56e3507ca98415383c7c16780da00，evidence-chain-builder/SKILL.md；2026-10-25 本地核对；本地维护者已决定按 MIT 处理；上游根 LICENSE 与 README 的许可标注不一致仍保留；精选改写，不采用打分脚本或二分标签门禁；在线可取性未复核。 适用版权行与本地维护决定仍在本包 `references/code-review.md`〈MIT 通知与本地维护决定〉，完整 MIT 正文见 `luno-review/LICENSE.openminis.txt`；溯源或再分发核对前完整读取；代码审查与 CI 的既定必读触发不变。

来源：mattpocock/skills@5beb35b040e3de97e54fa9e386d7e42d15c295c2，路径 `skills/productivity/grilling/SKILL.md`；2026-10-25 本地核对；MIT，Copyright (c) 2026 Matt Pocock；精选改写，仅吸收提问依赖分层，不采用 design tree 全量穷举或自动派子代理；完整许可见 `luno-review/LICENSE.matt-pocock.txt`；上游在线可取性未复核。来源登记见 skills-sources.md。

<!-- 来源：mattpocock/skills@4ae2317ddb22b046e26455e4f9c9b3aaaf62212d；路径：skills/engineering/tdd/SKILL.md、skills/engineering/implement/SKILL.md；2026-11-06 核对；MIT，Copyright (c) 2026 Matt Pocock；精选改写，仅吸收〈动手前〉的「沿用领域词表与 ADR 的词汇」「按纵切片而非横向分层推进」与〈改动〉的「不为未出现的用法做投机扩展」、implement 的「收尾时再跑一次完整检查」判据；本批自定判据只有〈动手前〉的「验收落成可判定的结果」与其三步组织（定位约定→定可判定验收→按行为切片推进）；上游原文为英文，改写后按句自查未见与之同形；上游可取；完整许可见 `luno-coding/LICENSE.matt-pocock.txt`；登记见 skills-sources.md。 -->

<!-- 来源：obra/superpowers@22f0b463e7a5e579904dd6211a520321035526f7；路径：skills/verification-before-completion/SKILL.md；2026-11-06 核对（该文件「Core principle: Evidence before claims, always」与〈Common Failures〉「Tests pass 需 test command output，Previous run／"should pass" 不算」）；MIT，Copyright (c) 2025 Jesse Vincent；精选改写，仅吸收〈交付〉的「附结果证据…不以「应该没问题」或文件已存在代替」一句，对应上游「evidence before claims」「Previous run／『should pass』不足以证明」判据；〈改动〉三条 diff 核对判据为自有流程，不取自上游；上游原文为英文，改写后按句自查未见与之同形；上游可取；完整许可见 `luno-coding/LICENSE.obra-superpowers.txt`；登记见 skills-sources.md。 -->

<!-- 来源：mattpocock/skills@5beb35b040e3de97e54fa9e386d7e42d15c295c2；路径：skills/engineering/diagnosing-bugs/SKILL.md、skills/engineering/to-tickets/SKILL.md；2026-10-25 本地核对；MIT，Copyright (c) 2026 Matt Pocock；精选改写；完整许可见 `luno-coding/LICENSE.matt-pocock.txt`；上游在线可取性未复核。来源登记见 skills-sources.md。 -->

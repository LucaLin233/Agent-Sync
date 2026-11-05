# Agent-Sync

本公开仓库为 LUNO 的提示词、技能、子代理提供**版本化存档备份和多端同步**。仓库文件是可恢复资产；合并不等于部署成功，`present` 只表示登记的受管落点，不表示已部署或回读通过。Minis 与 LobeHub 是运行端，仓库是管理落点；记忆各端自持，不在此同步。

## 目录与入口

- `AGENTS.md`：仓库工作入口；先加载当前生效的规则，不以候选覆盖它们。
- `prompt/LUNO.md`：提示词正文；`prompt/SOUL-frontmatter.yaml`：Minis 文件元信息。两者不可把文件误当 `soul.body` 生效字段。
- `skills/`：技能正文、包内资源、脚本、上游快照与许可；`skills-sources.md` 登记来源、固定版本、许可和必要恢复线索。
- `subagents/`：LENS、FORGE 的两端同文，以及 Minis 专用通用执行兜底；第三份不是 FORGE 副本，LobeHub 无该对象。
- `tools/sync-targets.json`：受管对象、资源与各端身份/落点登记。
- `tools/`：必要部署、正文判等、资源回读与打包工具；`tests/`：部署、Surge、脱敏、打包和规则守卫反例等六个测试入口和最小调度。它们各自的触发与授权以现役流程及相关规则为准，仓库目录不构成执行授权。
- [`PENDING.md`](PENDING.md)：当前活动未完成状态；`changelog/`：按日变更记录，一条记录一个文件、文件名 `YYYY-MM-DD.md`（当天已有则追加）。旧历史见旧私有 `LucaLin233/Agent` 的 Git 历史（本仓库为无历史快照，不含该历史）。

Minis 内置技能（如 `skill-creator`）不是同步对象；模型分组参数、记忆、设备与环境配置不在本仓库备份范围。第三方材料与来源、许可例外见 `skills-sources.md`；`luno-surge` 是自编与官方快照混合来源，详见 `skills/luno-surge/references/SOURCE.md`。

## 许可

根 `LICENSE` 为 MIT（`Copyright (c) 2026 LucaLin233`），**只覆盖本仓库自有内容**。第三方吸收件、上游快照与随包附件按各自上游许可分发、版权归各上游作者：`skills/<技能>/LICENSE.*.txt` 是对应上游许可全文，来源仓库@固定提交、所取路径与许可状态登记在 `skills-sources.md`；`luno-surge` 的官方分发特例见其包内 `references/SOURCE.md`。再分发前按该登记逐项核对，根许可不替代第三方授权。

## 授权、同步与恢复

操作规则对象或仓库前，完整读取**当前生效**的 `luno-sync/SKILL.md` 和 `luno-sync/references/sync-workflow.md`，再按入口加载命中资源；权限和审批以用户当次授权及现役规则为准。正文改动须独立预审与实施差分独立验收；每会话使用独立副本/分支、原生 PR，收口者串行合并并同步本批对象。必要测试与按需 MCP 核验按现役流程执行；对象身份唯一真源为 `tools/sync-targets.json`，部署写前回读目标，不再自动三副本互校或全量同名发现；不得把工具存在视为许可。

恢复先确认所需对象、版本与目标实际生效状态：从经核实的仓库版本或备份取对应文件，覆写前保存目标的真实前态及将变更的资源和元数据，核可读和权限；遵循对应端受支持入口写入，再逐端回读。正文及资源按现役字节契约比较，变化的 name/description 等字段另核；`soul.body` 与带 frontmatter 的磁盘文件分别核对；LENS/FORGE 和 Minis 兜底分别按其登记字段恢复。文件存在、HTTP 成功或 PR 已合并均不能代替回读。失败只停相关对象，保留前态与恢复入口，未回读即未完成。

**未变分支 rc=2 的操作性恢复路径（2026-10-12，复审 S1）**：该分支**不自动修复、也没有 `--force`**。若确认差异**仅为恰少一个尾 LF**：由主助理先核对**目标实例、登记 ID、候选 ZIP 与修复授权**，再从该候选 ZIP 的 `SKILL.md` 按 `body_contract` 提取**完整正文**，用受支持的 `lh skill edit <id> -c <正文>` **原样**提交，随后重新核验全部字段与资源；**不得**用会吞尾换行的 shell 命令替换（如 `$(...)` 命令替换、`echo` 等）来传递正文。其他漂移（描述／正文其它差异／资源路径集或 bytes／同 key 身份）**先诊断**，不盲重投、不改包规避只读分支。

Checks 仅当次授权临时使用 `GH_TOKEN_CLASSIC`；不改变默认 `$GH_TOKEN`，不将经典令牌用于普通仓库操作，不自动回退。仅获授权的Checks调用临时覆盖进程变量，秘密不回显、不写文件；0条仅表示无检查记录，不等于CI通过。GitHub Actions、Commit Status与Check Runs不互相冒充。

## 秘密与公开边界

**本仓库为公开快照、不含旧私有仓库历史**（旧历史曾包含连接配置，故按无历史重建）。不得提交 token、私钥、密码、`.env`、数据库/Redis 导出或备份归档，也不得提交一般连接配置与主机清单。非秘密受管对象身份/字段路径及专用巡检目标常量仅限既有窄例外，不含凭据，也不新增连接授权。发现秘密泄漏只报位置与类型、按授权处置和轮换，不复制秘密。

第三方素材、混合来源和许可缺口不因进入本仓库而取得公开或再分发权；拟扩大分发须先核来源许可与用户授权。不得把仓库或共享档案当凭据来源。

## 保留测试与资源

`sh tests/run-tests.sh full` 登记六个测试入口；`group deploy,surge,privacy,gate,pack` 或 `case <文件名>` 定向运行；`select-paths` 从 stdin 接收 NUL 分隔路径、输出 selector JSON，`select` 读取该 JSON 并去重运行。纯正文或无专项命中只运行 smoke（结构守卫），不把它当成六个专项已通过。规则正文保留结构守卫及两阶段独立审查；不再受逐字锚点约束，防弱化依赖两阶段独立审查，改加载边／资源边须同批更新 `tools/rule-claims.tsv`。`tools/sync-all.sh` 只运行结构守卫与包内校验，不访问生效端。
结构守卫 `tools/check-rules.py` 的退出码固定为 **0＝无问题／1＝结构错误（阻断）／2＝仅提示（不阻断）／3＝检查不完整（阻断）**。两处消费口径**不同且均为现状**：`tools/sync-all.sh` 按 0／2 放行（rc=2 的提示**保留输出但非阻断**）；`tests/run-tests.sh` 把**任何非零**（含 rc=2 的提示）记为 FAIL，即当前测试门禁要求**零提示**——这是更严的门禁，不是与 sync-all 的矛盾，也不因本说明放宽。`tests/test-check-rules.sh` 以 0／1／2／3 四态回归固定该语义。

按未暂存变更选路：`git diff --name-only -z --diff-filter=d | sh tests/run-tests.sh select-paths`。删除的文件不参与选路；现存未登记的测试路径仍须拒绝。

`skills/luno-sync/references/test-authoring.md` 保留测试准入与成本纪律；技能结构校验直接调用 `skills/luno-sync/scripts/quick_validate.py`。

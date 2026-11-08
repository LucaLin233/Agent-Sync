# 来源与许可

## 上游与取材基线

- 仓库：GitHub `CCH-HQ/cchp-cli`，包含 `cchp` CLI 与内置 Agent Skill。
- 本包实际取材提交：`d9da5760a8d2f6ce689c01b98b6c96540513045d`（2026-10-25，CLI v0.1.3／spec v1.0.12）。仅在采纳更新且包内正文随之改动后更新基线；只核对未采纳，不改取材基线。
- MIT，`Copyright (c) 2026 the cchp contributors`；许可原文随包保留于 `luno-cchp/LICENSE.upstream.txt`，本文件不是许可证原文。
- 取材文件（上游仓库路径）：
  - skills/cchp/SKILL.md
  - skills/cchp/references/auth.md
  - skills/cchp/references/errors.md
  - skills/cchp/references/output-contract.md
  - skills/cchp/references/pagination.md
  - skills/cchp/references/workflows.md
  - docs/agent-guide.md
  - docs/output-contract.md
  - docs/safety-model.md
  - LICENSE

另以 CLI 内置 spec、schema、命令元数据、指南及实例只读结果核对契约；动作前仍核当次版本与契约。本机非生效副本只用于对照锁定基线，不代替最新上游或覆盖正文。

## 上游更新核对

通用取源与同步依 `luno-sync/SKILL.md`〈真源与落点〉及 `luno-sync/references/sync-workflow.md`；只用获准来源与认证，缺证或限流标待核实，不换凭据。

1. 锁定默认分支 HEAD 与技能目录末次提交；以〈上游与取材基线〉完整提交为旧 ref，比较期间不改基线。
2. 对全部取材文件逐个比较两 ref 的哈希，变化项逐文件 diff。末次提交或目录未变不能代替文件比较（含目录外 docs、LICENSE）；404 不等于未变：旧 ref 缺失为新增，新 ref 缺失为删除或可能改名，结合 compare 的 added／removed／renamed 与原路径核对。取不齐即报缺证，不判无需更新。
3. 对照 CHANGELOG、最新 release 与 CLI/spec 实际契约；文件未变也须核契约。失败、权限或证据不足记「待核实」及缺项。

### 契约面判据

门禁、退出码、输出、分页、错误、认证、安全／脱敏、参数与 schema、默认值、重试／超时、流式／下载任一变化均属契约变化。CLI 实现、安装方式或面向人界面变化不能排除契约变化。判无变化须同时有取材文件 diff 为空、CHANGELOG／release 未见上述语义改动的正面证据；不足不得写「不需跟版」。

### 处理规则

不自动跟版；先列 `luno-cchp/SKILL.md`、`references/interfaces.md`、`references/workflows.md`、`references/coverage-rules.md` 的受影响小节、旧→新差异及实例兼容性，再按 `luno-sync/references/sync-workflow.md` 与当次授权处理。核对不授权实施／部署；未采纳只记录核对状态，不改基线。包变化后重算部署哈希，以部署回读值为准。上游仅新增命令且本端无授权场景时不补步骤；需要时依既有流程处理。

## 精选改写映射

中文精选改写，非逐字搬运：

| 本地文件 | 主要上游来源 | 处理 |
|---|---|---|
| `luno-cchp/SKILL.md` | skills/cchp/SKILL.md、docs/agent-guide.md | 保留发现→schema→调用、门禁和停止条件；补本端位置、版本、认证及授权边界 |
| `references/interfaces.md` | auth、errors、output-contract、pagination 及 docs 的契约／安全文档 | 合并认证、直连、错误、分页、流式／下载与重试契约 |
| `references/workflows.md` | skills/cchp/references/workflows.md | 保留业务骨架，补范围、变更前后与恢复等通用约束 |
| `references/coverage-rules.md` | skills/cchp/references/workflows.md | 迁移本地 request-overrides 完整分支，保留精选改写与实例验证边界 |

未纳入入门流程、Restish 隔离及本地凭据存储；安装只留获准安装器的版本、目录、校验与入口验收，不纳入 Homebrew／源码构建。上游凭据回退不适用于本端，依 `luno-cchp/SKILL.md`〈认证边界〉；`--allow-write`／`--confirm` 及上游新增命令均不扩大授权。上游 MIT 原文与版权行随包分发，中文改写亦可按 MIT 再分发。

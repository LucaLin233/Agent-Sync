# 来源维护

本文件仅保留跟版判据；仓库 skills-sources.md〈luno-cchp〉集中记录上游、固定提交、日期、取材文件、映射与排除项。核对前读取该登记，取不到就停止依赖它的判断。普通控制面操作不因此加载档案。

中文精选改写自CCH-HQ/cchp-cli；MIT，Copyright (c) 2026 the cchp contributors。完整许可随包见 LICENSE.upstream.txt；上游凭据回退不适用于本端，仍按入口认证边界执行。

## 上游更新核对

通用取源与同步依 `luno-sync/SKILL.md`〈真源与落点〉及 `luno-sync/references/sync-workflow.md`；只用获准来源与认证，缺证或限流标待核实，不换凭据。

1. 锁定默认分支 HEAD 与技能目录末次提交；以仓库 skills-sources.md〈luno-cchp〉登记的完整取材提交为旧 ref，比较期间不改基线。
2. 对全部取材文件逐个比较两 ref 的哈希，变化项逐文件 diff。末次提交或目录未变不能代替文件比较（含目录外 docs、LICENSE）；404 不等于未变：旧 ref 缺失为新增，新 ref 缺失为删除或可能改名，结合 compare 的 added／removed／renamed 与原路径核对。取不齐即报缺证，不判无需更新。
3. 对照 CHANGELOG、最新 release 与 CLI/spec 实际契约；文件未变也须核契约。失败、权限或证据不足记「待核实」及缺项。

### 契约面判据

门禁、退出码、输出、分页、错误、认证、安全／脱敏、参数与 schema、默认值、重试／超时、流式／下载任一变化均属契约变化。CLI 实现、安装方式或面向人界面变化不能排除契约变化。判无变化须同时有取材文件 diff 为空、CHANGELOG／release 未见上述语义改动的正面证据；不足不得写「不需跟版」。

### 处理规则

不自动跟版；先列 `luno-cchp/SKILL.md`、`references/interfaces.md`、`references/workflows.md`、`references/coverage-rules.md` 的受影响小节、旧→新差异及实例兼容性，再按 `luno-sync/references/sync-workflow.md` 与当次授权处理。核对不授权实施／部署；未采纳只记录核对状态，不改基线。包变化后重算部署哈希，以部署回读值为准。上游仅新增命令且本端无授权场景时不补步骤；需要时依既有流程处理。


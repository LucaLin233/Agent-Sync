# CCHP 导入

先完整读 `references/cchp-workflows.md`，按其触发与共同前置使用本资源。涉及写入的解释、方案、审查或执行，还须完整读 `references/cchp-workflow-writes.md`；实际调用或展示结果先完整读 `references/cchp-interfaces.md`。

## CC Hub 导入

- 只在用户本次明确要求迁移或导入、持有平台管理员 token（含 `config:write`）、源站和目标站都已确认、冲突处置策略已由用户选定时执行。
- 流程：预览 → 复核计数和 warning → 追加（`--mode append`，保留现状）或覆盖（`--mode overwrite`，要用预览给出的确认短语）→ 报告 job 状态和 `report`。
- **`--preview-only` 也要求 `--allow-write`，并且会在服务端创建导入 job**（后续步骤引用它的 jobId）；它不是只读，也不是没有副作用，不能当作「先看看」的安全试探。
- 覆盖模式会替换已有数据，先按 `luno-ops` 做改前备份和可回滚点；失败时错误会指明 job，`retryable` 决定能否用 `cchp import retry <jobId>` 续跑。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。

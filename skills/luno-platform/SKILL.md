---
name: luno-platform
description: 当前运行端（Minis、宿主端 Codex 及 paseo）的派发、文件编辑、临时目录、截断与执行环境等端机制；跨任务记忆读写、更正、事故复发与规则固化（共同规则、Minis 端自持）；CCHP 控制面与官方 CLI；Minis/iSH 配置运行时。
---
# LUNO｜平台配置、运行时与本端记忆

以下各项仅适用于标明的产品，不跨用能力、入口、实例或凭据。

## 运行端

中立规则按「当前端〈槽位〉」引用的本端机制包括派发通道、通用兜底、文件编辑、截断与压缩、临时目录、执行环境、秘密注入、技能根、工作副本、远端工作目录、连接清单、Surge 控制目标。按当前端完整读取对应资源：

- Minis 端（App 内置 iSH，存在 `/var/minis`）读 `references/runtime-minis.md`。
- Codex 端（宿主为 Codex CLI）读 `references/runtime-codex.md` 和 `references/runtime-host.md`。
- Claude Code 端（宿主为 Claude Code）读 `references/runtime-claude.md` 和 `references/runtime-host.md`。
- Codex 端通过 Paseo 派发、追问、处理子代理审批或核验角色前，完整读取 `references/runtime-paseo.md`〔分支 paseo-dispatch〕。
- Paseo 的查询、管理、配置或恢复前，完整读取 `references/runtime-paseo.md`〔分支 paseo-operations〕。
- 接续 Paseo 主会话前，完整读取 `references/runtime-paseo.md`〔分支 paseo-resume〕。涉及子代理操作时同时读取〔分支 paseo-dispatch〕。

无法确定当前端，或当前端没有登记资源时，只停依赖这些槽位的步骤并报告。当前端资源未列出某槽位时分两类处理。

- **规则类**（派发通道、通用兜底、文件编辑、截断与压缩、临时目录、执行环境）表示本端没有补充规则，按引用处的中立规则执行。
- **取值类**（秘密注入、技能根、工作副本、远端工作目录、连接清单、Surge 控制目标）表示本端没有该取值，依赖它的操作停止并报告缺口，不猜路径，也不借用其他端的取值。

引用处另写了缺省做法的（如连接清单缺失时向用户索取、通用兜底缺失时报告不可用），按引用处执行。端资源只给本端机制和取值，不新增或削弱引用处的义务，也不授予权限。

## 管理产品

- Minis 配置或运行时任务，完整读 `references/minis.md`〔分支 minis〕。
- CCHP 功能、公开文档、CLI 用法或控制面任务，完整读 `references/cchp.md`。仅查公开资料不走管理面。

跨产品取并集。

## Minis执行能力

**正文可读不等于本端有能力**：本技能的正文可以在各端只读加载，但其中的 **Minis 专属操作只在 Minis 端可用**；共同记忆仍按各自的能力和授权执行。其他端不能声称可以调用 `minis-config`、读写 `/var/minis/*`、使用 `apple-*`/`minis-*` 或刷新 App 技能元数据；遇到这类操作只在咨询层面处理，本端确有可用通道且获准时才转交。

## 处理记忆

- 实际涉及记忆读写、检索、更正、整理，或确需保存经验、实施经验固化（包括非平台任务），先完整读取 `references/memory-common.md`〔分支 memory-common〕，再按原触发读取共同维护、纠正及本端资源。
- Minis 与 Paseo 的 LUNO 主会话按端写入此类经验：Minis 按 `references/minis-memory.md`〔分支 minis-memory〕，Paseo 按 `references/runtime-host.md`〈记忆入口〉。

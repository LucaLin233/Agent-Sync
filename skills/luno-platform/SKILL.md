---
name: luno-platform
description: 跨任务记忆读写、更正、事故复发与规则固化（共同规则、Minis/LobeHub 各端自持）；CCHP 控制面与官方 CLI；Minis/iSH 配置运行时；已部署 LobeHub 2.x CE 的 Agent/模型、权限渠道、Skill/MCP、知识库及实例运维。
---
# LUNO｜平台配置、运行时与本端记忆

CCHP控制面完整读 `references/cchp.md`；Minis配置/运行时完整读 `references/minis.md`〔分支 minis〕；已部署LobeHub 2.x CE完整读 `references/lobehub.md`〔分支 lobehub〕。跨产品取并集。实际涉及记忆读写、检索、更正、整理，或确需保存经验、实施经验固化（包括非平台任务）先完整读取 `references/memory-common.md`〔分支 memory-common〕，再按原触发读取共同维护/纠正及本端资源。LobeHub 新话题的 GLOBAL 首次读取，完整读取 `references/lobehub.md`〔分支 lobehub〕 和 `references/lobehub-knowledge.md`〔分支 knowledge〕，按其中的私人副本规则处理；这不是原生记忆导入。以下各项仅适用于标明的产品，不跨用能力、入口、实例或凭据。

## Minis执行能力

**正文可读不等于本端有能力**：本技能的正文可以在各端只读加载，但其中的 **Minis 专属操作只在 Minis 端可用**；共同记忆与 LobeHub 分支仍按各自的能力和授权执行。其他端不能声称可以调用 `minis-config`、读写 `/var/minis/*`、使用 `apple-*`/`minis-*` 或刷新 App 技能元数据；遇到这类操作只在咨询层面处理，本端确有可用通道且获准时才转交。Minis 端遇到 LobeHub 操作，按 `luno-platform/references/lobehub.md`〔分支 lobehub〕 和既有授权的连接处理。

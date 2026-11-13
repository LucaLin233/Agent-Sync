---
name: luno-platform
description: 跨任务记忆读写、更正、事故复发与规则固化（共同规则、Minis/LobeHub 各端自持）；CCHP 控制面与官方 CLI；Minis/iSH 配置运行时；已部署 LobeHub 2.x CE 的 Agent/模型、权限渠道、Skill/MCP、知识库及实例运维。
---
# LUNO｜平台配置、运行时与本端记忆

CCHP控制面完整读 `references/cchp.md`；Minis配置/运行时完整读 `references/minis.md`〔分支 minis〕；已部署LobeHub 2.x CE完整读 `references/lobehub.md`〔分支 lobehub〕。跨产品取并集。记忆读写、检索、更正、事故或复发、固化候选和疑似规则缺口（包括非平台任务）先完整读取 `references/memory-common.md`〔分支 memory-common〕，再按原触发读取共同维护/纠正及本端资源。以下各项仅适用于标明的产品，不跨用能力、入口、实例或凭据。

## 实例与端点

管理面用 `CCHP_GATEWAY_URL` + `CCHP_TOKEN`，模型数据面用 `CCHP_BASE_URL` + LLM token，**两个面不得混用**。CLI 的 server 必须指向管理面（本端变量映射与认证限制见 `references/cchp.md`〈安全与认证〉）。缺哪个入口或凭据，就停止依赖它的请求、命令和结论，并报告变量名；不回退旧地址、不猜子域、不换实例或环境。

## Minis执行能力

**正文可读不等于本端有能力**：本技能的正文可以在各端只读加载，但其中的 **Minis 专属操作只在 Minis 端可用**；共同记忆与 LobeHub 分支仍按各自的能力和授权执行。其他端不能声称可以调用 `minis-config`、读写 `/var/minis/*`、使用 `apple-*`/`minis-*` 或刷新 App 技能元数据；遇到这类操作只在咨询层面处理，本端确有可用通道且获准时才转交。Minis 端遇到 LobeHub 操作，按 `luno-platform/references/lobehub.md`〔分支 lobehub〕 和既有授权的连接处理。

## LobeHub入口

- **入口**：公网入口取环境变量 `LOBEHUB_SERVER`，实例坐标见 `references/lobehub-instance.md`；宿主机和入口地址按当次的连接参数和实际注入值确定。**`LOBEHUB_SERVER` 未设置或为空时，停止依赖这个入口的 CLI 命令、平台读写和发布**，报告变量名和本端的设置入口；不回退旧域名、不猜子域、不读已保存的登录态补地址、不换实例，也不因此自动 `lh login`。离线核对正文和资源可以继续。

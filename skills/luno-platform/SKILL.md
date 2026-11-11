---
name: luno-platform
description: CCHP控制面（用量、请求、provider/key、覆写规则、LLM token、成员配额与导入）；Minis/iSH配置与运行时（技能元数据、子代理模型、SOUL、变量挂载、上下文、会话调度、记忆注入）；已部署LobeHub 2.x CE（Agent/模型、权限渠道、Skill/MCP、知识库记忆、实例运维）。
---
# LUNO｜平台配置与运行时

CCHP控制面完整读 `references/cchp.md`〔分支 cchp〕；Minis配置/运行时完整读 `references/minis.md`〔分支 minis〕；已部署LobeHub 2.x CE完整读 `references/lobehub.md`〔分支 lobehub〕。跨产品取并集。以下各项仅适用于标明的产品，不跨用能力、入口、实例或凭据。

## 实例与端点

管理面用 `CCHP_GATEWAY_URL` + `CCHP_TOKEN`，模型数据面用 `CCHP_BASE_URL` + LLM token，两者都必须是本次获准、已注入的变量，**两个面不得混用**。CLI 的 server 必须指向管理面（变量用法和反例见 `references/cchp.md`〔分支 cchp-interfaces〕〈实例端点与凭据〉）。缺哪个入口或凭据，就停止依赖它的请求、命令和结论，并报告变量名；不回退旧地址、不猜子域、不换实例或环境。离线分析和另一个入口的已授权操作可以继续。

## Minis执行能力

**正文可读不等于本端有能力**：本技能的正文可以在各端只读加载，但其中的操作**只在 Minis 端可用**。其他端不能声称可以调用 `minis-config`、读写 `/var/minis/*`、使用 `apple-*`/`minis-*` 或刷新 App 技能元数据；遇到这类操作只在咨询层面处理，本端确有可用通道且获准时才转交。Minis 端遇到 LobeHub 操作，按 `luno-platform/references/lobehub.md`〔分支 lobehub〕 和既有授权的连接处理。

## LobeHub入口

- **入口**：公网入口取环境变量 `LOBEHUB_SERVER`，实例坐标见 `references/lobehub-instance.md`；宿主机和入口地址按当次的连接参数和实际注入值确定。**`LOBEHUB_SERVER` 未设置或为空时，停止依赖这个入口的 CLI 命令、平台读写和发布**，报告变量名和本端的设置入口；不回退旧域名、不猜子域、不读已保存的登录态补地址、不换实例，也不因此自动 `lh login`。离线核对正文和资源可以继续。

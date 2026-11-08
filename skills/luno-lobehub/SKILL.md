---
name: luno-lobehub
description: 已部署LobeHub 2.x CE的Agent/模型、权限渠道、Skill/MCP、知识库记忆及实例运维；非Cloud/LobeChat。
---

# LUNO｜LobeHub 平台运维

## 范围

已部署的 LobeHub 2.x CE（Server DB + Better Auth）实例：平台侧的 Agent、模型、Skill 与连接器、渠道、权限、知识库与记忆、鉴权；实例侧的 Docker Compose 服务栈、升级、备份和运行环境。不处理 Cloud 和 LobeChat；默认不安装、不重建。

## 资源与触发

路径相对技能根，按总控的加载规则读取：

- Agent 与模型配置、调用模型的归属，或启用任何技能类工具：`references/agents.md`。
- Skill、连接器和 Custom MCP，技能的创建、安装、资源更新和启用排障：`references/skills.md`。
- 知识库、文档、文件分块、embedding、检索和平台记忆：`references/knowledge.md`。
- 实例部署、基线、升级恢复、密钥与鉴权、数据库扩展、S3、Redis、检索后端、卷与暴露面、执行位置与负载、异步任务和实例故障：`references/instance.md`。
- 使用或评估 CLI/HTTP、批量与自动化、设备端凭据环境：`references/access.md`。只读加载规则本身不触发。

## 依据

- **官方文档**就是上游仓库的 `docs/**`（`usage/**` 是平台功能和权限，`self-hosting/**` 是部署和实例配置），按实例版本 tag 取原文：`raw.githubusercontent.com/lobehub/lobehub/<当次已核的实例版本tag>/docs/<路径>`（或 lobehub.com/docs）。平台机制、变量含义和开关表查文档；本技能只记本实例的坐标、实测和文档里没写的坑。CLI 的语法、参数和退出码以本机 `lh <cmd> --help`、`lh man <cmd>` 为准，不复制帮助。
- 公开的 API 参考没有覆盖 `/trpc/lambda/<router>.<procedure>`，用法见 `references/access.md`；网关地址、令牌和 JWKS 的分工见对应版本文档 `self-hosting/platform/docker-compose.mdx`〈Agent Gateway〉。

## 方法

- 区分执行设备、目标实例和请求链路；核对版本、镜像 digest、Compose、环境变量、日志、端点和实际结果。
- 聊天和 embedding 分别验证。OIDC userinfo 成功不代表业务 API 的认证、映射或授权成功；登录失败先分清是 IdP 没回 email（`error=email_not_found`）还是授权问题。
- 界面和接口常把密钥显示成掩码，不要把掩码当真实值。前端异常时保持账号、数据和网络不变，只改视口复现。多版本实例要隔离有状态的数据，共享服务要评估争用。

## 平台层

- **入口**：公网入口取环境变量 `LOBEHUB_SERVER`，实例坐标见 `references/instance.md`；宿主机和入口地址按当次的连接参数和实际注入值确定。**`LOBEHUB_SERVER` 未设置或为空时，停止依赖这个入口的 CLI 命令、平台读写和发布**，报告变量名和本端的设置入口；不回退旧域名、不猜子域、不读已保存的登录态补地址、不换实例，也不因此自动 `lh login`。离线核对正文和资源可以继续。
- **读技能**：`lh skill view <id> --json content,name,description` 按字段只读回读；资源和细则见 `references/skills.md`。
- **权限与渠道**：角色有 Owner、Member、Viewer（Viewer 不能聊天）；Skill 和连接器只有创建者或 Owner 能编辑；渠道的全局 Allowed Users 优先于 DM/Group 策略。
- **功能缺失**：用户说某功能「没反应」，先看角色和 `FEATURE_FLAGS`（不支持 `all`），再怀疑实例层。

## 授权与底线

- 删除知识库、改密钥、开放端口等生产变更的确认按 `luno-core`〈授权与安全〉。
- 异步任务只精确取消，并保留审计。官方 CLI（`lh`）是受支持的自动化面；改库只走官方脚本，不用未公开的接口绕过限制。

## 输出

另列出基线、证据和链路判断；没做行为实测的写「仅配置验证」。

---
name: luno-lobehub
description: 已部署 LobeHub 2.x CE：Agent/模型、权限/渠道/开关、Skill/连接器/Custom MCP、知识库/记忆及实例部署/排障；非 Cloud/LobeChat。
---

# LUNO｜LobeHub 平台运维

## 范围
已部署的 LobeHub 2.x CE（Server DB + Better Auth）实例：平台侧 Agent、模型、Skill 与连接器、渠道、权限、知识库与记忆、鉴权；实例侧 Docker Compose 服务栈、升级、备份与运行环境。不处理 Cloud 与 LobeChat；不默认安装或重建。

**加载边界**：加载与缺失处置依 `luno-core/SKILL.md`〈路由〉；子代理按派发摘要，不足时可只读取得当前任务及必要依赖的 Skill/资源，仍不可得交负责人补齐。

## 资源与触发
下列路径均相对本技能根目录（SKILL.md 所在目录），按任务读取对应原文；跨项取并集，未读不得执行，不可读即暂停对应分支并报告，不凭记忆写入。
- Skill、连接器与 Custom MCP，及技能创建/安装/资源更新/启用排障：`references/skills.md`
- 知识库、文档、文件分块、embedding、检索与平台记忆：`references/knowledge.md`
- 实例部署、基线、升级恢复、密钥与鉴权、数据库扩展、S3、Redis、检索后端、卷与暴露面、执行位置与负载、异步任务及实例故障：`references/instance.md`

- 使用或评估 CLI/HTTP、批量与自动化、设备端凭据环境时，必须在操作/建议/结论前完整读取 `references/access.md`；中途涉及先补读。仅只读加载规则本身不触发本资源，仍守既定安全与授权边界。

## 依据
- 官方文档即仓库 `docs/**`（`usage/**` 平台功能与权限、`self-hosting/**` 部署与实例配置），按实例版本 tag 取原文 `raw.githubusercontent.com/lobehub/lobehub/<当次已核实例版本tag>/docs/<路径>`（或 lobehub.com/docs）；平台机制、变量含义与开关表按文档查，正文只留本实例坐标、实测与文档不认的坑；CLI 语法/参数/退出码以本机 `lh <cmd> --help`、`lh man <cmd>` 为准，不复制帮助。
- 公开 API 参考文档未覆盖（`/trpc/lambda/<router>.<procedure>` 用法见 `luno-lobehub/references/access.md`）；网关地址、令牌与 JWKS 分工见对应实例版本文档 `self-hosting/platform/docker-compose.mdx`〈Agent Gateway〉。

## 方法
- 区分执行设备、目标实例与请求链路；核对版本、镜像 digest、Compose、环境变量、日志、端点与实际结果。
- 聊天与 embedding 分别验证；OIDC userinfo 成功不代表业务 API 的认证、映射或授权成功；登录失败先分 IdP 未回 email（`error=email_not_found`）与授权问题。
- 界面与接口对密钥常以掩码呈现，别把掩码当真实值；前端异常保持账号、数据、网络不变，只改视口复现。多版本实例隔离有状态数据，共享服务评估争用。
- 批量与自动化先读 `references/access.md` 的入口选择判据。

（文档、文件上传、分块、embedding、检索、`pg_search`、批量 HTTP 已验证接口与最终一致性见 `references/knowledge.md`，异步任务失败的实例条件见 `references/instance.md`。）

## 平台层
- **本部署**：公网入口取环境变量 `LOBEHUB_SERVER`；实例坐标、记录时点及现场复核见 `references/instance.md`。宿主机与入口地址按当次连接参数与实际注入值确定。**`LOBEHUB_SERVER` 未设置或为空时，停止依赖该入口的 CLI 命令、平台读写与发布动作**，报告变量名与本端设置入口；不回退旧域名、不猜子域、不读已保存登录态补齐地址、不换实例，也不据此自动 `lh login`；离线核对正文与资源可继续。
- **Agent 与模型**：改 Agent 前用 `lh agent view <id> --json <fields>` 按当前 CLI 已验证语法投影非秘密字段并存实例备份位；不能安全限定嵌套子字段或备份失败即停，不全量后脱敏。部分更新保留未改字段；改后以相同的非秘密字段（含嵌套子字段）回读模型、提供商、工具/Skill、提示词与开场。`--config-file` 对象 deep-merge、数组整体替换，未提供的标量与对象保留。历史实测（2026-10-07，v2.2.19 单实例两次采样）：嵌套 `callAgent` 使用被调 agent 的 model/provider，不沿用调用方 topic pin；不外推其他版本，使用前按当前部署版本核对。需要调用方模型时，先验证顶层运行或调整被调配置的适用性，未核实则标「待验证」，不得据历史值改配置。模型与供应商只改用户指定层级（内置/市场/用户自定义/Custom MCP）；重试前回读查重，同对象最多 3 次，仍失败即停并报告。
- **角色名不构成工具白名单**：启用技能类内置工具前，须按当次授权与当前版本核角色 manifest 和 device 实际能力（含写/执行 API）；未经当次核实不得启用，可独立配置的只读模式亦然。按任务、当次授权与隔离条件启用必要工具，不因审查角色名禁用写/执行。现场清单、manifest 与 device 形态须按当次授权取证，不凭历史值推断；部署变更后重验。
- **读技能的可用路径**：`lh skill view <id> --json content,name,description` 按字段只读回读；技能资源与细则见 `references/skills.md`。
- **权限与渠道**：角色 Owner/Member/Viewer（Viewer 不能 chat）；Skill 与连接器编辑限创建者或 Owner；渠道全局 Allowed Users 优先于 DM/Group 策略。
- **功能与开关**：功能缺失或用户「没反应」先看角色与 `FEATURE_FLAGS`（不支持 `all`），再怀疑实例层。

## 授权与底线
- 删知识库、改密钥、放开端口等生产变更的确认依 `luno-core/SKILL.md`〈授权与安全〉。
- 异步任务只精确取消并保留审计。官方 CLI（`lh`）是受支持的自动化面；改库只走官方脚本，不用未公开接口绕过限制。

## 输出
输出依 `luno-core/SKILL.md`〈执行闭环〉；另列基线、证据及链路判断；未做行为实测写「仅配置验证」。

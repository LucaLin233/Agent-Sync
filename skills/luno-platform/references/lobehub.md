# 共读资源（按原分支合并）

指针中的“分支”以 branch 锚点及 BEGIN/END 注释定界。沿用各分支原有触发和共同前置：完整读取命中的分支；原规则指定分节时，读取指定完整分节及共同前置，不加载未命中分支。同一文件的命中并集优先一次取齐，返回受限时分块补齐，不以截断内容作已加载。

分支内的“本文件”“本文”“本资源”均只指该分支，不把其他分支的接口事实、版本、能力或权限并入；“本技能”仍指原技能。主体、条件、例外、停止、恢复和许可边界保持原文，不因合并授予额外权限。跨技能先读目标技能入口及产品/业务入口；候选不改变现役规则。

分支：lobehub、lobehub-access、lobehub-agents、lobehub-skills。

<a id="branch-lobehub"></a>
<!-- BEGIN lobehub -->
# LUNO｜LobeHub 平台运维

## 范围

已部署的 LobeHub 2.x CE（Server DB + Better Auth）实例：平台侧的 Agent、模型、Skill 与连接器、渠道、权限、知识库与记忆、鉴权；实例侧的 Docker Compose 服务栈、升级、备份和运行环境。不处理 Cloud 和 LobeChat；默认不安装、不重建。

## 资源与触发

路径相对技能根，按总控的加载规则读取：

- Agent 与模型配置、调用模型的归属，或启用任何技能类工具：`references/lobehub.md`〔分支 lobehub-agents〕。
- Skill、连接器和 Custom MCP，技能的创建、安装、资源更新和启用排障：`references/lobehub.md`〔分支 lobehub-skills〕。
- 知识库、文档、文件分块、embedding、检索和平台记忆：`references/lobehub-knowledge.md`。
- 实例部署、基线、升级恢复、密钥与鉴权、数据库扩展、S3、Redis、检索后端、卷与暴露面、执行位置与负载、异步任务和实例故障：`references/lobehub-instance.md`。
- 使用或评估 CLI/HTTP、批量与自动化、设备端凭据环境：`references/lobehub.md`〔分支 lobehub-access〕。只读加载规则本身不触发。

## 依据

- **CLI 先查执行设备帮助**：使用 `lh` 前，在实际执行设备上确认 CLI 版本并读取目标子命令的 `--help`，需要更完整说明时再读 `lh man <命令路径>`。帮助已有的语法、参数、退出码和解释不抄进技能；帮助不足时，再查匹配 CLI 版本和目标实例版本的官方原文。服务端功能、变量和开关查上游仓库对应实例版本 tag 的 `docs/**`（或 lobehub.com/docs）；CLI 源码须匹配 CLI 版本，不以服务端 tag 代替。本技能只保留帮助缺失的本地规则、实例坐标和有版本边界的经验。
- 公开的 API 参考没有覆盖 `/trpc/lambda/<router>.<procedure>`，用法见 `references/lobehub.md`〔分支 lobehub-access〕；网关地址、令牌和 JWKS 的分工见对应版本文档 `self-hosting/platform/docker-compose.mdx`〈Agent Gateway〉。

## 方法

- 区分执行设备、目标实例和请求链路；核对版本、镜像 digest、Compose、环境变量、日志、端点和实际结果。
- 聊天和 embedding 分别验证。OIDC userinfo 成功不代表业务 API 的认证、映射或授权成功；登录失败先分清是 IdP 没回 email（`error=email_not_found`）还是授权问题。
- 界面和接口常把密钥显示成掩码，不要把掩码当真实值。前端异常时保持账号、数据和网络不变，只改视口复现。多版本实例要隔离有状态的数据，共享服务要评估争用。

## 平台层

- **读技能**：按字段只读回读技能正文和元数据，本地非秘密投影示例为 `lh skill view <id> --json content,name,description`；这三个字段是此读取的白名单，不授权读取其他字段。资源和细则见 `references/lobehub.md`〔分支 lobehub-skills〕。
- **权限与渠道**：按当前版本、部署形态和对象作用域核对权限，不把通用 Workspace 角色表直接套到 CE，也不凭角色名推定 Skill 或连接器的编辑权；渠道的全局 Allowed Users 优先于 DM/Group 策略。
- **功能缺失**：用户说某功能「没反应」，先看角色和 `FEATURE_FLAGS`（不支持 `all`），再怀疑实例层。

## 授权与底线

- 删除知识库、改密钥、开放端口等生产变更的确认按 `luno-core/references/execution.md`〔分支 safety〕〈授权与安全〉。
- 异步任务只精确取消，并保留审计。官方 CLI（`lh`）是受支持的自动化面；改库只走官方脚本，不用未公开的接口绕过限制。

## 输出

另列出基线、证据和链路判断；没做行为实测的写「仅配置验证」。
<!-- END lobehub -->

<a id="branch-lobehub-access"></a>
<!-- BEGIN lobehub-access -->
# CLI/HTTP 调用与设备端凭据

## CLI

- 官方 CLI `@lobehub/cli`（`lh`）是自动化入口；调用前核对实际执行设备、CLI 与目标实例的版本和服务端支持，不以命令存在证明服务端可用。实例入口与缺失处置见本技能入口的〈LobeHub入口〉；不得用登录态补入口或自动登录、换实例。
- **版本证据**：npm 的 `latest` 不等于已装的版本；观测到的版本不等于最低支持版本，单个版本的端到端验证不能确定最低支持边界。
- **诊断**：选用诊断模式前核对副作用与输出字段，深度检查和修复须有对应授权；离线诊断不等于没有写入或敏感输出。
- **运行结果**：脚本按当前帮助的退出状态分支，并保留外层等待期限；不能用状态成功冒充完整取回结果。传输、续接、降级和退出路径未行为实测。
- **会话与权限**：调用会触发运行的命令前核对目标和运行授权，成员权限变更另核授权。多路复用的跟随不能直接外推到 CE 链路，要核对服务端协议和网关能力。
- **定位与检索**：JSON 里的 `url` 和已存地址对象的 `appUrl` 仍按字段白名单取。检索限定当次获准的对象和时间窗，旧实例缺过滤接口也不放宽。消息检索的截断警告在 stderr 里，JSON 成功不代表结果完整，截断时在授权内收窄范围复查；这项历史记录未复测当前行为。

## 认证与设备端凭据

- CLI 支持的认证来源不扩大本端秘密授权；不得用保存态、其他变量或交互登录替代本次明确授权且已注入的指定变量。
- 设备端的 `/root/.zshenv`（所有 shell）和 `/root/connect-device.sh`（`lobehub-connect` 的启动脚本）都从 `/root/env/*.env` 加载变量（默认单个文件 `secrets.env`，按主题注释）；新会话才生效，轮换时只改这个文件，然后 `systemctl restart lobehub-connect`。缺 key 时只核对指定变量是否已注入，缺失就交回维护者，不读文件，不通过交互绕过。实例的 `/root/lobehub/.env` 供 Compose 解析，是另一套，不要混放。

## 批量与自动化走 HTTP

有等价的已验证接口时，批量和自动化走 HTTP，不用 CLI 循环（既有样本里 CLI 串行调用开销大；性能按当前版本和链路核对，不把历史耗时当常量）。没有等价接口的，仍按官方支持的 CLI 用法，先查原文再试。写法：

- `POST https://<实例>/trpc/lambda/<router>.<procedure>`
- 请求头：`X-API-Key: $LOBEHUB_CLI_API_KEY`、`Content-Type: application/json`；User-Agent 按当前链路选用可识别值。历史观测为缺 UA 触发 Cloudflare `error code: 1010`，未复测当前链路，不固定 curl 版本。
- 请求体 `{"json":{…}}`，响应 `{"result":{"data":{"json":…}}}`
<!-- END lobehub-access -->

<a id="branch-lobehub-agents"></a>
<!-- BEGIN lobehub-agents -->
# Agent、模型与工具启用

字段的安全投影、指定实例和授权不因本资源放宽；CLI 用法另见 `references/lobehub.md`〔分支 lobehub-access〕。

- **改 Agent 前**：按当前 CLI 已核实的字段投影方式只读取非秘密字段，存到实例的备份位置；不能安全限定嵌套子字段，或备份失败，就停，不全量读取再脱敏。
- **部分更新**保留未改的字段。改完用相同的非秘密字段（含嵌套子字段）回读模型、提供商、工具和 Skill、提示词和开场白。`--config-file` 对对象做 deep-merge、对数组整体替换，未提供的标量和对象保持不变。
- **嵌套调用的模型**（历史实测，2026-10-07，v2.2.19 单实例两次采样）：嵌套的 `callAgent` 使用被调 agent 自己的 model/provider，不沿用调用方 topic 固定的模型。不外推到其他版本，使用前按当前部署版本核对。需要调用方的模型时，先验证顶层运行或调整被调配置是否适用；没核实就标「待验证」，不按历史结果改配置。
- **改动范围**：模型和供应商只改用户指定的层级（内置、市场、用户自定义、Custom MCP）。重试前先回读查重，同一对象最多试 3 次，仍失败就停下报告。
- **角色名不是工具白名单**：启用技能类的内置工具之前，按当次授权和当前版本核对角色 manifest 和 device 的实际能力（含写入和执行 API）；没有当次核实就不启用，可单独配置的只读模式也一样。按任务、授权和隔离条件启用必要的工具，不因为是审查角色就禁用写入和执行。现场清单、manifest 和 device 形态按当次授权取证，不凭历史值推断，部署变更后重验。配置成功不等于行为实测。
<!-- END lobehub-agents -->

<a id="branch-lobehub-skills"></a>
<!-- BEGIN lobehub-skills -->
# Skill 与连接器

- **分清对象**：区分内置工具、市场和用户自定义的技能，以及 Custom MCP。共享范围和 Agent 的启用方式按对象类型和当前版本核对，不把连接器的启用方式套到技能上。只改用户指定的层级和启用方式，平台没有的模式不模拟。连接器和 STDIO MCP 的密钥用环境变量传入，不写进内容。
- **禁读列**（2026-09-17 诊断记录）：`user_connectors.credentials` 是禁读列。对它做 `::jsonb` 强制转换时，Postgres 的错误详情会回显原值前缀；任何涉及这一列的表达式都不能进入诊断输出，包括类型探测。
- **来源边界**：GitHub 来源可以指向技能子目录（v2.3.2 源码，未行为实测），不限定在仓库根目录；服务端不读 GitHub token，所以私有仓库、本地路径和私有 IP 都不能作为来源。
- **更新**：`install` 既能新建也能更新，不需要先删除。核对当前的入口、identifier 和来源，分清「同一 identifier 的包更新」和「正文资源化」，不要断言 identifier 一律由 URL 生成；更新后回读 ID。只有无法原位更新、并且用户明确授权迁移时，才备份后删除重建；旧 ID 不保证能恢复，要同步更新登记。核对来源用 `lh skill view <id> --json id,identifier,source,zipFileHash` 等已确认不含秘密的字段，禁止全量读取 manifest（会泄漏签名 URL）。
- **三个字段分开更新**：平台把技能的 `content`（正文）、`description`、`name` 当独立字段存。仅编辑正文不会同步描述（本实例发生过，只比正文的巡检没发现）。每次改完分别回读三个字段判等：本地正文按规则仓库 `tools/body_contract.py` 的契约提取，与平台 `content` 的 UTF-8 字节严格相等，不 strip，不归一 CRLF 或末尾换行；没有该仓库工具的端也要遵循同一契约。资源按完整相对路径逐个回读并比较原始字节；CLI 0.0.79 的 `read-resource` 对非空二进制输出 base64，空内容输出 JSON，不能直接把 stdout 当作文件字节，须核对资源编码并还原后判等（对应版本源码，未行为实测）。资源目录、ZIP 哈希和正文判等都不能代替资源判等。
- **末尾换行的坑**：本实例实测 `install` 会裁掉正文的末尾换行，要按契约提取正文后用 `lh skill edit -c` 原样补齐。**给 CLI 传带末尾换行的正文时，禁止用 `$(cat …)` 或 `"$(…)"`**：命令替换会剥掉末尾换行。改用 `--config-file` 传 JSON（如 `lh agent edit --config-file` 的 `{"systemRole": 全文}`）或由脚本直接写入。
- **读技能的途径**：按字段只读回读正文、名称和描述，资源另行逐个读取；也可以由派发方给出规则摘要，或在设备侧按路径只读读取。需要的是规则而不是安装能力时，不必启用任何技能类工具（2026-09-16 实测：平台侧助手在其设备上执行 `lh skill view` 和 `lh skill resources` 可用、退出码 0；`read-resource` 未实测）。
- **登记、启用、加载和行为分别验证**：不能因为 `lh agent view` 的 `plugins` 里没有某个技能就断言它没启用；网页端列出了自定义技能也不能证明已加载或行为生效。按当前版本核对技能的暴露机制、目标 Agent 的可用性和实际的加载或调用证据，证据不足标「未验证」。重建后回读新 ID，并核对相关引用和目标 Agent 的可用性，不预设一定要重新绑定或一定不用。
- **私有资源包投递**（2026-09-20/21 本实例实测）：私有 R2 桶生成约 600 秒有效的预签名 ZIP GET URL，供 `lh skill install` 一次性下载；桶本身不公开，不用私有仓库直链。更新沿用同一个 R2 key（本实例已复现会保留 ID，但仍要回读 ID），并用已确认版本的候选独立核对打包源、完整资源字节和 ZIP/`zipFileHash`；预期换包但包哈希没变时先查原因，不盲目重投。预签名 URL 含临时凭据，不进入回复、日志、归档或文件，只经已核实的安全通道在授权的源和目标之间传递；没有这样的通道就暂停投递并交负责人，不改塞进 argv 或工具 JSON 规避，也不改用公开对象。生产写入授权和同名核对不豁免。
<!-- END lobehub-skills -->


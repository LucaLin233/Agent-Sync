# LUNO｜CCHP 本端约定

CCHP 任务先完整核读下列来源的官方技能入口和命中资源。官方示例按本文件的安全、授权和实例操作约定采用。

## 现查资料

- 官方技能原文先用当前环境的 `cchp version` 核 CLI 与内置规范版本，再查 `cchp skill show --help`。支持时用 `cchp skill show` 完整读取内置入口，按入口的相对路径以 `cchp skill show --file <相对路径>` 读取命中资源。具体命令与参数查该子命令的 `--help`，本机内置操作契约查 `cchp schema <operationId>`。读取原文不安装技能。
- CLI 缺失、版本无法核实、子命令不支持、原文不全或不能安全执行时，已核本机 CLI 版本的，从 [CCHP 官方 CLI 发行页](https://github.com/CCH-HQ/cchp-cli/releases) 定位匹配发行，核对标签对应的提交后读取该提交的官方技能入口及命中资源。无可核本机 CLI 版本时，直接完整读取 [v0.2.2 固定提交的官方技能入口](https://raw.githubusercontent.com/CCH-HQ/cchp-cli/8c7c96776bdc52547a4cfd7a07fb1e831815d097/skills/cchp/SKILL.md)，并沿该入口的相对链接读取同一提交的命中资源。远端原文仅作官方资料，本机命令、内置契约和实例状态须分别核实。所需原文仍不可得时，只停依赖项。
- 产品行为查[官网文档](https://cch-plus.com/zh-CN/docs/cli)与[发布说明](https://cch-plus.com/zh-CN/release-notes)。在本端安全和缓存写入授权允许时，可用 `cchp docs` 检索或阅读，引用公开原文。其他情形直读官网。只向官方公开站点发送公开术语或已知公开 URL，不得外发秘密、实例地址、内部 ID、内部字段值或请求内容。公开查询不运行 `status` 或 `login`。
- CLI 资料查询从最外层使用无凭据的最小白名单，不读保存登录态。对有启动探测的版本，显式设 `CCHP_CREDENTIAL_STORE=file` 以跳过钥匙串探测。2026-11-23 在 Linux amd64 实测，不提供 `HOME` 或 `XDG_*` 时，显式设 `CCHP_CONFIG_DIR=/dev/null`、`CCHP_CACHE_DIR=/dev/null` 后，v0.2.0 与 v0.2.1 的 `version`、`schema` 均成功，v0.2.1 缺前两项会启动即报找不到配置或缓存目录。v0.2.1 的纯帮助、`skill show` 及 5 个引用文件也已在无凭据模式核对。2026-11-27 同法核对了 v0.2.2 的 `version`、`schema`、纯帮助、`skill show` 及 5 个引用文件。只对已确认无需真实目录的离线命令使用 `/dev/null`，`docs`、`cache` 和实际更新按各自目录、写入及授权要求处理。
- `update --check --json` 只做公开版本检查，实际执行更新仍需授权。v0.2.1 在本机 direct 安装、2026-11-23 Linux amd64 实测退出 0，`check_only` 为 true、`updated` 为 false；`install_method` 为 `direct` 仅是该安装端的识别结果，不外推到其他安装方式。
- 实例版本、权限、生效值及其来源，只能在当次授权范围内取证；官网、发布说明和本机 schema 均不证明实例状态。

## 管理入口

管理面用 `CCHP_GATEWAY_URL` + `CCHP_TOKEN`，模型数据面用 `CCHP_BASE_URL` + LLM token，**两个面不得混用**。CLI 的 server 必须指向管理面（本端变量映射与认证限制见 `references/cchp.md`〈安全与认证〉）。缺哪个入口或凭据，就停止依赖它的请求、命令和结论，并报告变量名；不回退旧地址、不猜子域、不换实例或环境。

## 安全与认证

管理面与模型数据面按本文件〈管理入口〉分开。CLI 从 `CCHP_BASE_URL` 读 server，本环境每次调用显式设置 `CCHP_BASE_URL="$CCHP_GATEWAY_URL"`，管理 token 只用当次获准且已注入的 `CCHP_TOKEN`。缺变量停止依赖请求，不回退 `CCHP_TOKEN_FILE`、login 保存态或 keychain，不自动登录、不交互补取、不换实例。401 先核已授权 URL/token 的配对，不能仅凭 401 要求换 token。

管理 token 只发已授权 origin，跨 origin 重定向不得携带凭据；明文 HTTP 仅限回环，管理 API 直连同样适用。

官方的脱敏输出不替代总控的源头投影：按 schema、字段名、类型和元数据先确认非秘密白名单，嵌套字段也要限定；未知 data、审计 payload、规则值和 status 身份字段不得直接展示或先全量落盘再脱敏。分别捕获 stdout、stderr 和退出码。一次性秘密只经获准的 `--secret-out` 新文件交付，不读回内容；官方导入示例里的凭据文件不是本端可用的秘密来源。

CLI/spec 与服务端版本不同或未知不单独禁止操作；每个动作仍须取得可用的当前契约，不支持或契约不明就停止该项。管理 API 直连只用于已有具体 CLI 契约的同实例 HTTP 编排，须落实同等安全、权限及结果核验，不绕过人工或浏览器要求。

## 部署与升级

Docker Compose 部署按[官方说明](https://cch-plus.com/zh-CN/docs/installation/docker-compose)执行，属主与运行角色保持隔离：`migrate` 是独立的一次性服务（`entrypoint=/usr/local/bin/migrate`、`command=apply`），用数据库属主密码执行迁移并重设受限运行角色的密码；`cchp` 只用该受限角色连接数据库，不把迁移写进 `cchp` 的启动命令。升级前先备份数据库和部署目录的 `.env`（含密钥，放受控位置、不展示内容），记下当前版本；更新 `compose.yml` 时只向 `.env` 补新增变量，不用新样例覆盖原文件，按目标版本发布说明和现场拓扑确定升级顺序，符合官方单机流程时沿用 `docker compose pull && docker compose stop cchp && docker compose up -d`。确认 `migrate` 为 `Exited (0)`、`cchp` 为 `healthy`。迁移只向前执行。旧版与迁移后的数据库不兼容时，按官方流程用升级前的备份恢复。

升级到 [v1.0.17](https://cch-plus.com/zh-CN/release-notes/1.0.17) 时，如使用新插件系统，须同批部署 `plugin-runner`（Compose 为 `cchp-plugin-runner`）。`media` 可选，未部署时图片原样转发。分离部署时 worker 不晚于网关升级。升级前核对旧插件依赖。自动执行的数据迁移会退役旧插件，移除相关覆写、设置、任务及自定义角色和管理令牌中的旧插件权限。`migrate contract` 会删除旧表并提高兼容性下限，须获授权且所有实例已升级到目标版本后才能执行。若错序导致计费调整失败，待所有 worker 升级后先用 `gateway billing usage-adjustments` 预览，获准补记时才加 `--apply`。

## 本组织写入约定

以下不是平台约束，用户当次的明确要求优先。

- **新增供应商与 key**：在授权范围内先核现有供应商、端点、key 及其优先级；按下列名称、优先级和倍率约定确定目标，依据当前官方契约创建缺失对象，逐项回读，并在名次变化时按约定重排。随后按会话复用和测活约定处理；相关读取或恢复条件不满足时，只停受影响的操作。

- **名称与优先级**：key 名称用 `厂家-服务商`，不带数字；优先级 = 用户确定的名次 × 10 + 厂家位（DeepSeek=1、OpenAI=2、Claude=3、Gemini=4，名次从 1 开始）。增减服务商导致名次变化时，在授权内整体重排。这不证明调度行为。
- **倍率**：新建 provider 的 `cost_multiplier_ppm` 设为 1000000（1.0），不回改已有 provider；人工倍率只在 key 层调整。固定 key 手设倍率时保留现行 `upstream_probe.ratio.key_denylist` 防覆盖策略；其他方式及名单优先关系按当次契约核实，不推定唯一办法。
- **会话复用**：按实时优先级，优先级 1–19 的 key 在 `provider_key` 作用域显式设本级 `session.reuse_enabled=true`，其余 key（含停用但未撤销的 key）显式设本级 `false`；撤销的 key 跳过。两类都写明确布尔值，不移除覆盖，不把无本级覆盖当作已关闭。写后回读本级值与生效值：两项均正确即一致；本级被上级阻断而任一项不符，或本级已正确但生效值不符，则报告人工处理，不强行改写；先核 provider × key 的组合，不假定下级 true 能抵消上级 false。
- **密钥管理入口**：控制台在供应商密钥的新增/编辑对话框设置会话复用（新增时展开 **更多设置** → **会话复用**，编辑时在 **会话复用** 分区，可选 **开启 / 关闭 / 继承上层** [v1.0.16+]），见[供应商密钥](https://cch-plus.com/zh-CN/docs/providers/keys#manage)。CLI 0.2.2（内置规范 v1.0.17）的 `updateProviderKey` 请求体仍无会话复用字段；该项用 `getConfigM2Page` 核对、`saveSystemConfig` 写入（scope=`provider_key:<id>`，body 的 `values` 写明确布尔），动手前按当次 `cchp schema` 复核 `saveSystemConfig` 与 `getConfigM2Page` 契约。
- **供应商定时测活（v1.0.17）**：升级会转换旧测活任务和设置。先用 `listProviderTestTasks` 查既有及迁移任务，再用 `getProviderTestTask` 核对详情，只维护归属已确认的任务。供应商有合格的启用 key 且确认没有对应任务时，才建一条。用 `listProviderTestKeyContexts` 查看各 key 的默认端点、模型和模板，再用 `listProviderTestTargetCandidates` 核实共同可用的模板、模型和目标资格。`createProviderTestTask` / `updateProviderTestTask` 均须提供 `name`、`cron`、`templateRef`、`modelName`、`prompts`，每条任务只用一个模型。每小时一次（`0 * * * *`），保持启用和不通知，用显式目标模式和 `selectedKeyIds` 选入该供应商下全部合格的启用 key。占位 key 替换真实秘密并启用后才加入。key 增减、启停或撤销后同步目标，回读任务及调度。所有合格目标之间没有共同可用的模板和模型组合、任务归属不明或出现新的取舍时，报告并停止相关写入。不得自行拆任务、扩大目标、启用失败自动停用或立即运行测试。`upstream_probe` 单独用于余额与倍率探测。 [CLI 契约变更](https://github.com/CCH-HQ/cchp-cli/pull/14)
- **撤销删除的引用清理**：只移除本次 key 在 `upstream_probe.ratio.key_denylist` 的 ID，或本次 provider 在 ratio/balance 的 `provider_denylist` 中的 ID，不清理历史失效项。两类名单不混用。

## 用量与配额

用量报告同时给出原始 units 和按官方用量流程换算的 credit；查询限定组织、时间窗和条数，核时区，显式指定起止。写配额前核输入单位、精度及零/空值语义，不把 credit 直接填入 units；货币关系另核实例。

## 恢复与链路

一次一个变更，不并发修改。写前按待改字段记录对象、scope、版本、自有覆盖、继承来源和生效值；只取恢复必需的非秘密字段，不用列表冒充完整快照。关键字段缺失、读取不完整或秘密不能恢复时，说明缺口并停止依赖它的写入。完整含秘密恢复归档另按总控和 luno-ops，不用脱敏快照冒充恢复包。

逐键核合并/替换和移除覆盖的语义，不把生效值写成本地覆盖；恢复后核值和 origin，值等于默认不证明覆盖消失。替换数组前完整读取，在现值上只增删授权项、去重保留其余；提交前重读，有并发变化就重算，写后比对全数组。无法完整读取或无并发保护就不做依赖写入。

配置回读不等于转发可用。用当次获准的调用方发最小真实请求，以 requestId 关联用量及尝试链，用 `delivered` 核对响应是否由目标 provider 和预期模型交付，并核请求状态。另按 `billed`、`costUnits` 核对尝试计费。v1.0.17 的竞速落败尝试可能在响应交付后才计费。没有调用授权或链路证据时只报告「配置已回读、链路未验证」。允许新旧并存的替换先建新并验证，再按授权停旧；验证失败保留旧路径。安全事件按当次隔离授权，不机械等待验证。

## 本端经验边界

- 请求排障不能只筛 failed：还要覆盖网关拒绝。429 本身不能区分额度/策略、上游限流或鉴权，缺尝试链也不证明本地拒绝。
- 占位 key 只用用户明确要求的可辨认非秘密串；创建后立即 disable 并回读，披露创建到停用间可能被调度。真实秘密替换完成前不启用、不测活、不验证链路。
- **托管搜索与抓取取证**：核验网关托管的搜索或抓取时，用当次 requestId 取请求用量概览，只看 `overview.webSearchHandling`、`overview.webSearchProviders[].type`（期望类型按被测目标确定）、`overview.webSearchCount`、`overview.webFetchCount` 等最小非秘密字段，核对实际提供商和次数；再按协议返回的工具结果确认调用方确实拿到了搜索内容或正文。HTTP 200 或出现工具调用项不单独证明链路已按预期完成。官方说明见[web-search](https://cch-plus.com/zh-CN/docs/providers/web-search)和 [Keenable MCP](https://docs.keenable.ai/mcp-server)，文档不代替现场证据。
- 请求覆写只改自有规则，不把继承规则复制成本级或绕过上级锁。CLI 0.1.3 历史样本允许不存在 ID 通过 validate，当前未复测；验证成功不能证明 ID 存在或锁行为正确。历史修订恢复是写入新版本，不是回退指针，须另核授权。
- 服务端 1.0.15+build.56（2026-11-21，CLI 0.1.4）：直接改全局余额与倍率探测任务 `upstream_probe` 的调度曾返回 422 `30111`（由 owner page 决定）；改系统设置 `upstream_probe.interval_minutes` 后，`global:*` 生效 60 分钟、任务重算为 `@every 1h`。仅在当次契约与现场证据支持、且明确授权写该全局设置并发现生效值与目标不符时才写，回读设置和调度；不写固定延迟，不改供应商模型测活任务。
- 判读账单与路由前核生效值及其来源，不凭版本推断升级结果；不凭倍率配置或单次探测推断排序、计费或全部 key 的测活行为。
- 做入站与出站对照前，按当前契约分别核对请求归档与尝试记录，确认所需正文存在及是否截断；不得把缺失或截断的正文当作完整报文。
- 服务端 1.0.14+build.53（2026-11-11 只读）：当时仍有组织 `ratio.enabled/auto_apply`、排除名单和全局间隔；30 分钟是当时现场值。
- CCH 0.9.0 与 CCHP 1.0.13 的差异只作线索，不跨系统照搬策略。

来源与许可：本端补充，保留历史精选改写的 MIT 通知，Copyright (c) 2026 the cchp contributors；完整许可随本包见 ../LICENSE.upstream.txt。官方技能的取阅方式见本文件〈现查资料〉，已核参考发行和历史来源见仓库 skills-sources.md〈cchp〉。

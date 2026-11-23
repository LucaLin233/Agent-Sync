# LUNO｜CCHP 本端约定

CCHP 任务先完整读取 `references/cchp-upstream/ENTRY.md`；其相对引用随包，缺件只停依赖项，不用旧副本替代。官方示例不得覆盖本端边界。

## 现查资料

- 产品行为查[官网文档](https://cch-plus.com/zh-CN/docs/cli)与[发布说明](https://cch-plus.com/zh-CN/release-notes)。可用时按官方入口用 `cchp docs` 检索或阅读，引用公开原文。只向官方公开站点发送公开术语或已知公开 URL；不得外发秘密、实例地址、内部 ID、内部字段值或请求内容。公开查询不运行 `status` 或 `login`。
- 本机命令与参数查具体子命令的 `--help`；用 `cchp version` 核 CLI 与内置规范版本，用 `cchp schema` 核具体操作契约。以上 CLI 查询用无凭据最小白名单，不读保存的登录态；对有启动探测的版本，显式设 `CCHP_CREDENTIAL_STORE=file` 只为跳过钥匙串探测，不得读取凭据文件。CLI 缺失、不支持或不符合上述边界及写入授权时，直读官网和对应版本的公开上游，不用登录态补查，也不把上游资料当成本机契约。
- 2026-11-23 在 Linux amd64 实测：不提供 `HOME`/`XDG_*` 时，上述离线查询在最小白名单中显式设 `CCHP_CONFIG_DIR=/dev/null`、`CCHP_CACHE_DIR=/dev/null` 和 `CCHP_CREDENTIAL_STORE=file`，v0.2.0 与 v0.2.1 的 `version`、`schema` 均成功；v0.2.1 缺前两项会启动即报找不到配置或缓存目录。`/dev/null` 只用于已确认无需真实目录的离线命令，不用于 `docs`、`cache` 或实际更新。
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

Docker Compose 部署按[官方说明](https://cch-plus.com/zh-CN/docs/installation/docker-compose)执行，属主与运行角色保持隔离：`migrate` 是独立的一次性服务（`entrypoint=/usr/local/bin/migrate`、`command=apply`），用数据库属主密码执行迁移并重设受限运行角色的密码；`cchp` 只用该受限角色连接数据库，不把迁移写进 `cchp` 的启动命令。升级前先备份数据库和部署目录的 `.env`（含密钥，放受控位置、不展示内容），记下当前版本；更新 `compose.yml` 时只向 `.env` 补新增变量，不用新样例覆盖原文件，随后 `docker compose pull && docker compose stop cchp && docker compose up -d`，确认 `migrate` 为 `Exited (0)`、`cchp` 为 `healthy`。迁移只向前执行，不能回退。

## 本组织写入约定

以下不是平台约束，用户当次的明确要求优先。

- **新增供应商与 key**：在授权范围内先核现有供应商、端点、key 及其优先级；按下列名称、优先级和倍率约定确定目标，依据当前官方契约创建缺失对象，逐项回读，并在名次变化时按约定重排。随后按会话复用和测活约定处理；相关读取或恢复条件不满足时，只停受影响的操作。

- **名称与优先级**：key 名称用 `厂家-服务商`，不带数字；优先级 = 用户确定的名次 × 10 + 厂家位（DeepSeek=1、OpenAI=2、Claude=3、Gemini=4，名次从 1 开始）。增减服务商导致名次变化时，在授权内整体重排。这不证明调度行为。
- **倍率**：新建 provider 的 `cost_multiplier_ppm` 设为 1000000（1.0），不回改已有 provider；人工倍率只在 key 层调整。固定 key 手设倍率时保留现行 `upstream_probe.ratio.key_denylist` 防覆盖策略；其他方式及名单优先关系按当次契约核实，不推定唯一办法。
- **会话复用**：按实时优先级，优先级 1–19 的 key 在 `provider_key` 作用域显式设本级 `session.reuse_enabled=true`，其余 key（含停用但未撤销的 key）显式设本级 `false`；撤销的 key 跳过。两类都写明确布尔值，不移除覆盖，不把无本级覆盖当作已关闭。写后回读本级值与生效值：本级已正确但生效值被上级作用域或锁改变时报人工处理，不强行改写；先核 provider × key 的组合，不假定下级 true 能抵消上级 false。
- **密钥管理入口**：控制台在供应商密钥的新增/编辑对话框设置会话复用（新增时展开 **更多设置** → **会话复用**，编辑时在 **会话复用** 分区，可选 **开启 / 关闭 / 继承上层** [v1.0.16+]），见[供应商密钥](https://cch-plus.com/zh-CN/docs/providers/keys#manage)。CLI 0.2.1（内置规范 v1.0.16）的 `updateProviderKey` 请求体没有会话复用字段；该项用 `saveSystemConfig` 的配置 scope 接口核对和写入（scope=`provider_key:<id>`，body 的 `values` 写明确布尔），动手前按当次 `cchp schema` 复核 `saveSystemConfig` 与 `getConfigM2Page` 契约。
- **测活**：provider 有启用 key 后先查既有任务，没有才建一条，已有就维护。每小时一次（`0 * * * *`）、enabled、不通知；只含其下已启用且符合接口状态的 key。模型取 `getProviderKeyLivenessContexts` 派生默认值，不自行指定模型或 endpoint；契约或派生结果不给模型就停止该项。占位 key 替换真实秘密并启用后才加入；key 增减、启停或撤销后同步 targets，回读任务及调度。
- **撤销删除的引用清理**：只移除本次 key 在 `upstream_probe.ratio.key_denylist` 的 ID，或本次 provider 在 ratio/balance 的 `provider_denylist` 中的 ID，不清理历史失效项。两类名单不混用。

## 用量与配额

用量报告同时给出原始 units 和按官方用量流程换算的 credit；查询限定组织、时间窗和条数，核时区，显式指定起止。写配额前核输入单位、精度及零/空值语义，不把 credit 直接填入 units；货币关系另核实例。

## 恢复与链路

一次一个变更，不并发修改。写前按待改字段记录对象、scope、版本、自有覆盖、继承来源和生效值；只取恢复必需的非秘密字段，不用列表冒充完整快照。关键字段缺失、读取不完整或秘密不能恢复时，说明缺口并停止依赖它的写入。完整含秘密恢复归档另按总控和 luno-ops，不用脱敏快照冒充恢复包。

逐键核合并/替换和移除覆盖的语义，不把生效值写成本地覆盖；恢复后核值和 origin，值等于默认不证明覆盖消失。替换数组前完整读取，在现值上只增删授权项、去重保留其余；提交前重读，有并发变化就重算，写后比对全数组。无法完整读取或无并发保护就不做依赖写入。

配置回读不等于转发可用。用当次获准的调用方发最小真实请求，以 requestId 关联用量及尝试链，核目标 provider、最终模型、状态和计费，排除失败后被其他 provider 接管。没有调用授权或链路证据时只报告「配置已回读、链路未验证」。允许新旧并存的替换先建新并验证，再按授权停旧；验证失败保留旧路径。安全事件按当次隔离授权，不机械等待验证。

## 本端经验边界

- 请求排障不能只筛 failed：还要覆盖网关拒绝。429 本身不能区分额度/策略、上游限流或鉴权，缺尝试链也不证明本地拒绝。
- 占位 key 只用用户明确要求的可辨认非秘密串；创建后立即 disable 并回读，披露创建到停用间可能被调度。真实秘密替换完成前不启用、不测活、不验证链路。
- 会话复用的本级值与生效值分开记录：本级 `false` 只表示本作用域设置，不等于生效关闭；`blocked` 或 `blocked_by_scope_key` 表示本级被上级阻断，不能当作已对齐。
- 请求覆写只改自有规则，不把继承规则复制成本级或绕过上级锁。CLI 0.1.3 历史样本允许不存在 ID 通过 validate，当前未复测；验证成功不能证明 ID 存在或锁行为正确。历史修订恢复是写入新版本，不是回退指针，须另核授权。
- 服务端 1.0.15+build.56（2026-11-21，CLI 0.1.4）：直接改全局余额与倍率探测任务 `upstream_probe` 的调度曾返回 422 `30111`（由 owner page 决定）；改系统设置 `upstream_probe.interval_minutes` 后，`global:*` 生效 60 分钟、任务重算为 `@every 1h`。仅在当次契约与现场证据支持、且明确授权写该全局设置并发现生效值与目标不符时才写，回读设置和调度；不写固定延迟，不改供应商模型测活任务。
- 判读账单与路由前核生效值及其来源，不凭版本推断升级结果；不凭倍率配置或单次探测推断排序、计费或全部 key 的测活行为。
- 做入站与出站对照前，按当前契约分别核对请求归档与尝试记录，确认所需正文存在及是否截断；不得把缺失或截断的正文当作完整报文。
- 服务端 1.0.14+build.53（2026-11-11 只读）：当时仍有组织 `ratio.enabled/auto_apply`、排除名单和全局间隔；30 分钟是当时现场值。
- CCH 0.9.0 与 CCHP 1.0.13 的差异只作线索，不跨系统照搬策略。

来源与许可：本端补充，保留历史精选改写的 MIT 通知，Copyright (c) 2026 the cchp contributors；完整许可随本包见 ../LICENSE.upstream.txt。官方技能的来源与固定版本见仓库 skills-sources.md〈cchp〉，本端不修改官方正文。

# 共读资源（按原分支合并）

指针中的“分支”以 branch 锚点及 BEGIN/END 注释定界。沿用各分支原有触发和共同前置：完整读取命中的分支；原规则指定分节时，读取指定完整分节及共同前置，不加载未命中分支。同一文件的命中并集优先一次取齐，返回受限时分块补齐，不以截断内容作已加载。

分支内的“本文件”“本文”“本资源”均只指该分支，不把其他分支的接口事实、版本、能力或权限并入；“本技能”仍指原技能。主体、条件、例外、停止、恢复和许可边界保持原文，不因合并授予额外权限。跨技能先读目标技能入口及产品/业务入口；候选不改变现役规则。

分支：cchp、cchp-interfaces、cchp-workflow-writes。

<a id="branch-cchp"></a>
<!-- BEGIN cchp -->
# LUNO｜CCHP 控制面

## 范围

CCHP（Claude Code Hub Plus）控制面：用量与耗材、请求日志、provider 与 provider key、LLM token、成员与配额、CC Hub 导入，以及少量设置读取。有两个入口：`cchp` CLI（用管理 token；spec 内置在 CLI 里，可以离线查操作）是默认入口；Management API（HTTP 直连）只在 CLI 可用、并已从 CLI 取得操作契约时用于编排，不是缺 CLI 时的替代。网关转发、模型质量和通用运维不属于本技能。

**相邻领域**：宿主机、容器、反代、DNS、TLS、防火墙和 CCHP 镜像升级归 `luno-ops`；Minis 技能登记归 `luno-platform/references/minis.md`〔分支 minis〕；LobeHub 的模型和渠道归 `luno-platform/references/lobehub.md`〔分支 lobehub〕。混合任务取并集，不用控制面技能代替运维。

## 资源与触发

路径相对技能根。完整读取命中的资源及其指定的共同前置；跨业务取并集，不摘段或用摘要代替：

- 任何实际CLI或API调用，以及认证、结果、错误、分页、重试、流式和下载的解释：`references/cchp.md`〔分支 cchp-interfaces〕。
- 业务操作、解释、建议或结论，以及任何写入、恢复、覆盖或转发变更：按〈业务分支〉完整读取命中的业务资源。涉及写入的解释、方案、审查或执行还必须读写入共同规则，组织约定、改前快照、配置继承与恢复仍适用于所有写入。纯接口认证或分页咨询不触发业务资源。
- 请求/响应覆盖规则（request-overrides，旧称“请求过滤器”）的读取、解释、建议、结论、草稿验证和任何写操作：`references/cchp-coverage-rules.md`；实际调用或涉及接口契约时另读 `references/cchp.md`〔分支 cchp-interfaces〕，写入或跨业务比较另按〈业务分支〉完整读取写入共同规则和命中的业务资源。
- 实际需要备份（如导入覆盖）或命中宿主机、容器、反代、DNS、TLS等运维时，按需加载 `luno-ops` 并读取命中的完整资源；需要备份的变更须完成改前备份与改后回读。普通对象操作仍须核授权、留改前快照、改后回读并具备恢复办法，不因免读ops而免除这些义务。
- 来源、许可、改写边界或上游更新核对：完整读取 `luno-platform/references/cchp-source.md` 的维护规则及其仓库登记；普通调用不加载来源档案。

## 业务分支

不执行未请求的业务，不为示例访问实例或用生产凭据测试。先用 `cchp commands --search` 找 operationId，再查 `cchp commands show <operationId> --json` 和 `cchp schema <operationId> --json` 的当前契约；实例数字以当次实测为准。执行或展示结果前，完整读 `references/cchp.md`〔分支 cchp-interfaces〕，逐操作确认非秘密字段白名单；前提不满足就停止相关调用并报告缺口。

- **写入共同前置**：涉及写入、恢复、覆盖或转发变更的解释、建议、方案、审查或执行，先完整读 `references/cchp.md`〔分支 cchp-workflow-writes〕。本组织约定、改前快照、配置继承与恢复适用于所有写入；纯只读用量或请求定位不加载写入规则。
- 用量、耗材、计费、成员或配额，失败请求定位或审计追溯，LLM token 创建、轮换或撤销，CC Hub 迁移、导入或预览：`references/cchp-workflow-org.md`。导入另读写入共同规则；预览会在服务端创建 job，不是只读。
- provider/endpoint/key 的状态、启停、撤销、删除、创建、更新、倍率、探测、model_redirects 或跨系统配置比较：`references/cchp-workflow-providers.md`。
- 配置继承与恢复的解释，转发相关变更的验收或切换：`references/cchp.md`〔分支 cchp-workflow-writes〕。配置回读不等于链路验证，本技能不因此获得网关调用权。

## 执行位置与版本门槛

1. **先定位置**：CLI 可以按授权装在多台主机上（含 Minis 本机），不预设固定主机；先确认本次的执行主机、用户和项目，定位和安装都只在这个环境里做。不凭文档或历史结论推断当前实例的状态。
2. **再找 CLI**：先 `command -v cchp`；没命中不等于没安装（非交互 shell 的 PATH 常不全），再查该用户的 `$HOME/.local/bin/cchp`、`/usr/local/bin/cchp`、`/opt/homebrew/bin/cchp` 和已知的自定义位置。仍找不到就报告「当前执行环境未定位到可用 CLI」，不断言没装。找到后用选定的入口执行 `version --json`，记录实际路径、CLI 和 spec 版本，后续一直用这个入口。
3. **安装或升级**只在获准的主机目录里做，不动服务端和编排：核对 `CCH-HQ/cchp-cli` 安装器的来源和内容，用 `CCHP_VERSION`/`CCHP_INSTALL_DIR` 明确版本和目录（默认 `$HOME/.local/bin`），用 `checksums.txt` 校验，覆盖旧二进制前备份。默认用显式路径；只有系统入口获准、目标没有冲突、目录在实际 PATH 里时，才建 `/usr/local/bin/cchp` 软链。改完按真实的调用方式（含非交互 SSH）核对入口和 `version --json`。失败就停止依赖的部分，按备份和授权恢复。
4. **再定身份和实例**：用选定的 CLI 执行 `status --json`，核对 server、token 前缀、身份和连通性，和本次授权不符就停。服务端版本（控制台或 `cchp admin about`）和 CLI、spec 版本一起记录；服务端版本未知，或动作依赖未核实的契约时，只做只读。
5. **门槛**：没找到可用的 CLI、版本不符或 spec 与实例不匹配时，停止控制面操作并报告缺口，不用 Management API 直连代替；已获授权的定位、安装或升级可以按本节处理，完成后重新核验前提。

## 认证边界

- 只用技能入口〈实例与端点〉里本次授权且已注入的变量；缺失就停下报告变量名，不换来源，不交互补取。
- **不回退**到 `CCHP_TOKEN_FILE`、`cchp login` 的保存态、系统 keychain，或其他服务器、其他组织的 token（上游 CLI 默认会尝试这些来源，所以要明确拒绝）。
- token 不进命令行参数、会话、日志、提交或报告。一次性密钥（新建的 token、生成码）只经 `--secret-out` 写入本次授权的受控路径，回报路径和字段名，不回显值。
- 管理 token 只能调用其权限范围内的操作，有效权限是人员角色和 token 授权范围的交集。`excluded` 类操作（改密、通行密钥、二步验证、轮换 token、登录和安装流程）只能由用户在控制台完成。

## 核心循环

`cchp commands --search "<词>" --json` → `cchp schema <operationId> --json` → `cchp api <operationId> [--flag value] --json`。

- 操作的旗标、风险门禁、示例和分页描述符，按当前 CLI 执行 `cchp commands show <operationId> --json`；通用的输出、错误和任务规则按需查 `cchp guide agents|errors|tasks`。不缓存普通命令示例或旧分页表；当前 CLI 和 spec 没给出的字段、旗标或续页方式不能猜。
- 参数是 kebab-case 旗标（`providerId` → `--provider-id`），数组重复书写；路径参数可以按位置给；JSON 请求体用 `--body-file <file>` 或 `-`，先过本地 schema 校验再原样发送。
- 先 `--dry-run` 看将要发出的 method、URL 和请求体（已脱敏），再决定是否加写入门禁。
- `orgId` 默认取 token 所属的组织，不指定其他组织。
- 分组命令和 `cchp api` 同源；operationId 仍是记录和交接用的标识，但**以所选 CLI 内置的 spec 为准**：升级后重新发现操作并核对 schema，不假定旧 operationId 仍然存在。
- 一次只执行一个变更；不并发批量修改，不在同一个窗口里混用不同的操作。

## 门禁不是授权

`--allow-write`、`--confirm <operationId>`、`--secret-out` 是 cchp 的工具门禁，只说明「这条命令可以发出」，**不等于用户授权**，也不扩大授权范围；加之前必须有本次用户请求或既有授权里的明确范围。

## 停止条件

遇到以下情况立即停下，不绕路、不换入口重试。按 `references/cchp.md`〔分支 cchp-interfaces〕〈结果契约〉的安全输出要求，报告已确认不含秘密的 `error.kind`、`error.message` 和 `request_id`；含秘密或安全性不明时只报位置、类型和缺口。

- `permission_denied`（退出码 4）或 `unauthorized`（3）：权限或 token 边界问题；有 `required_permission` 就照实报告。
- `browser_session_required` 或 `human_verification_required`（8）：只能由用户在控制台完成，说明原因，不找替代路径。
- `unknown_outcome`（12）：结果未知，停止变更，先只读取证再决定。
- `policy`（13）：门禁拒绝；核对是否真的属于本次授权，不为了通过而叠加旗标。
- 不满足〈执行位置与版本门槛〉里的 CLI 可用性或版本、契约前提。
- 需要超出本次授权的写入、不可逆动作、新环境或新凭据。

## 输出

结论先行：操作和目标实例、实际命令或 operationId、关键字段（用量、状态、`request_id`）、没执行的项和不确定之处。有变更时补上改前状态、改后回读结果和回滚方式；影响转发时另报链路验证结果或没验证的原因（判据见 `references/cchp.md`〔分支 cchp-workflow-writes〕〈转发相关变更的验收与切换〉）。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。
<!-- END cchp -->

<a id="branch-cchp-interfaces"></a>
<!-- BEGIN cchp-interfaces -->
# 接口与契约（CCHP 控制面）

本文件的判据以 CLI 0.1.3 / spec v1.0.12 为基线。列表形状、操作字段和分页一律在命中操作时以当前内置 spec（`cchp schema`、`cchp commands show`）为准，这里不缓存。

## 两个入口

- **`cchp` CLI**（默认）：查询和小范围变更，离线查操作和 schema，带门禁和脱敏。前提：已安装、server 指向管理面、配了已授权的 `CCHP_TOKEN`、`cchp status --json` 可读。
- **Management API 直连**：只在 CLI 可用、并已从 CLI 取得该操作契约、需要 HTTP 编排（批量读、接入现有 HTTP 客户端）时使用；同一实例、同一管理 token、同一组织。CLI 不可用、版本不符或 spec 与实例不匹配时按 `luno-platform/references/cchp.md`〔分支 cchp〕〈执行位置与版本门槛〉停止，直连不是替代入口。
  - 路径和方法从 `cchp api <operationId> --dry-run --json` 的 `method`/`url` 取，请求体形状以 `cchp schema <operationId> --json` 为准，不凭记忆或第三方文档拼路径。
  - CLI 的门禁、脱敏、重试和分页在直连时**都不生效**：写操作要自己做同等的前置（改前取证、改后回读，重试和接续按〈超时与重试〉），错误响应不能原样打印含凭据的请求头。
  - 端点前缀、版本化路径和直连分页参数**须当次实测确认**，确认前只做只读。

## 认证

- 管理 token 形如 `cch_auth_live_<prefix>_<secret>`；`cch_llm_live_…` 这类 LLM token 会被拒绝。
- 一个 token 属于「一个人 + 一个组织」，有效权限是人员角色和 token 授权范围的交集。现状用 `getMyPermissionSummary` 查；被拒时 `denied_reasons` 为 `token_scope` 表示限制来自 token 本身。
- token 只发往签约服务器的 origin（scheme、host、port 全部匹配）；重定向到别处就丢弃，不把 `X-CCH-Organization` 带到其他组织。明文 `http://` 只对回环地址成立。
- 需要浏览器会话的操作在 `cchp commands --all --json` 里标为 `excluded`，没有程序化的替代。

## 实例端点与凭据（部署记录 2026-10-25/26，HTTP 探测 2026-10-26）

两个地址都从环境注入（https）：`CCHP_GATEWAY_URL` 是面板和管理 API（`/api/*`），`CCHP_TOKEN` 作为管理面的 `Authorization: Bearer`；`CCHP_BASE_URL` 是数据面 `{CCHP_BASE_URL}/v1/*`，LLM token 作为数据面的 `Authorization: Bearer`（或 `x-api-key`）。

- **CLI 的 server 必须指向管理面。**既有用法是逐命令覆盖：`CCHP_BASE_URL="$CCHP_GATEWAY_URL" cchp status --json`。这说明 CLI 是从 `CCHP_BASE_URL` 读 server，而本环境的 `CCHP_BASE_URL` 是数据面地址，所以**不覆盖就可能打到数据面**（表现为下面的 401 code 10003）。CLI 实际读哪个变量**待验证**：在实例上用 `cchp status --json` 看 server 字段确认，确认前每条命令都显式覆盖。
- 反例（2026-10-26）：数据面域名对带管理 token 的已测管理路径返回 401 `data plane requires LLM token`（code 10003），不能据此断定管理 token 失效或未测的路由存在。数据面 `GET /v1/models` 无凭据返回 401 `missing API key`；模型推理未验证。
- 面板域的根 `/` 和 `/v1/models` 曾返回 200 HTML（SPA 回退），不能当作数据面可用。

## 结果契约

带 `--json`、`CCHP_AGENT=1` 或 stdout 不是终端时进入 agent 模式：stdout 恰好一个 JSON 结果对象（流式先逐行输出事件，最后一行是终态），诊断和失败提示走 stderr，失败时退出码非 0，没有提示符、分页器和颜色。结果对象按操作带 `schema_version`、`ok`、`operation`、`status`、`request_id`、`data`、`error`、`warnings` 等字段，列表、变更、密钥、下载、流式和 dry-run 分别可能带 `pagination`、`outcome`、`idempotency_key`、`secret`、`file`、`stream`、`dry_run`；缺字段不能推断成功或完整。发现类命令（`commands`、`schema`、`version`、`guide`、`status`）同形，内容在 `data`；`cchp skill show` 默认输出原始 Markdown，加 `--json` 才是结果对象。

**安全输出**（含错误、流式和下载诊断）：`data` 是服务端原值，不等于可以展示。执行前按具体操作的契约确认非秘密字段白名单，嵌套对象限定子字段，未知字段不输出；按`luno-core/references/execution.md`〔分支 safety〕〈秘密面〉做源头投影，按字段名、类型和元数据判敏，不靠取样或事后处理。CLI 或客户端的安全捕获和内存投影只用于满足上述前提的响应：分别处理 stdout、stderr 和退出码，只把投影结果送进工具结果、会话或诊断文件，不先全量落盘再脱敏。不满足前提就停止这次读取或调用并报告缺口，不猜 `--fields` 之类的旗标。必要且已确认不含秘密的警告、授权或恢复限制和错误原文要完整保留。一次性密钥只走 `--secret-out`，且不授权读取那个文件。

## 错误与退出码

失败时 `error` 含 `kind`、`message`、`hint`、`code`、`detail`、`required_permission`、`challenge_action`、`fields`、`retryable`、`problem`（服务端 problem+json，已脱敏）。完整的码表以 `cchp guide errors` 为准，决定处置的几个：

- **3 `unauthorized`**（401）：可能是 URL 和 token 类型不匹配（见上节的数据面反例），或 token 过期、撤销、写错。停止并报告，核对已授权的 URL/token 配对；不能只凭 401 就要求换 token。
- **9 `rate_limited`**：CLI/Management API 的 429；确认是可重试的管理面限流后按 `hint` 等待，只有只读可以重试。它不能用来归因网关的业务请求，业务拒绝按 `references/cchp-workflow-org.md`〈失败请求定位〉核查。
- **11 `not_sent`**：请求没离开本机，修因后按〈超时与重试〉接续。
- **12 `unknown_outcome`**：可能已到达服务端，停止变更，先查状态。
- 其余：4 权限不足报 `required_permission`；6 冲突（409/412）先重读现状；7 输入校验失败按 `fields` 修；8 只能由用户在控制台完成；10 服务端 5xx，读可以稍后重试，变更先查状态；13 安全策略拒绝，核授权，不叠加旗标；14 没有凭据，报告缺口，按认证边界处理；1、2、5 分别是未预期失败、用法错误、对象不存在，按 `hint` 处理。

## 分页

默认只取一页。以当前 `cchp commands show <operationId> --json` 的 pagination 描述符确定 items 和 next 的路径、cursor 或 page 以及续页旗标，schema 或契约升级后重核。cursor 不透明，只在同一筛选条件下原样传回，不构造也不跨查询复用。

`partial`/`preparing` 为真时要重取，或按当次契约消解。没有描述符、没有 next 或没有续页旗标，都不证明结果完整；按筛选条件、返回数量和上限以及契约核对目标集合，不能确认完整就不做依赖它的写入。只读查询可以用支持的 `--page-limit`/`--max-items` 串行翻页，命中上限或 truncated 时报告是部分结果；限流时按 hint 有限等待，不并行抓页或重试。`--timeout` 默认 60 秒，覆盖多页的整次运行；到期的 warning 和续页信息不等于完整结果，要报告数量并说明覆盖范围。

## 流式与下载

- **流式**：先逐行输出 NDJSON 事件（`type`、`operation`、`seq`、`event`、`id`、`data`），最后一个终态结果对象。agent 模式默认 20 个事件后停，`--max-events` 改上限，`--timeout` 可以提前结束；终态的 `stream` 说明已投递的事件数和结束原因（`max_events`/`deadline`/`server_closed`）。
- **下载**：需要 `--output <新文件>`（`-` 表示 stdout），cchp 拒绝覆盖已有文件，`download-bundle` 也一样。响应体按字节原样落盘，结果里 `file` 的 `bytes`、`sha256` 描述的就是落盘的文件，回读用 sha256 判等。请求归档标明某部分非空、却下载到空内容时，会以 `server_error`（退出码 10）失败，不报成功。

## 超时与重试

`--timeout` 默认 60 秒。读请求在网络失败和 5xx 后会自动重试两次；**CLI 对变更不自动重试**。超时发生在请求发出前是 `not_sent`，发出后没收到应答是 `unknown_outcome`。人工接续前先查真实现状，确认原因和授权；只有操作支持、并且已经返回或发送过 `idempotency_key` 时，才复用这个键。没有幂等头的操作按其业务专节处理；request-overrides 的写入没有幂等头，见 `references/cchp-coverage-rules.md`。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。
<!-- END cchp-interfaces -->

<a id="branch-cchp-workflow-writes"></a>
<!-- BEGIN cchp-workflow-writes -->
# CCHP 写入共同规则

先完整读 `references/cchp.md`〔分支 cchp〕，按其〈业务分支〉的触发与共同前置使用本资源；实际调用或展示结果先完整读 `references/cchp.md`〔分支 cchp-interfaces〕。

## 本组织约定

以下是用户为本组织定的约定，不是 CCHP 平台的约束；用户当次的明确要求优先。所有写入都适用。

- **key 名称与优先级**：名称用 `厂家-服务商`，不带数字；优先级 = 用户确定的名次 × 10 + 厂家位（DeepSeek=1、OpenAI=2、Claude=3，名次从 1 开始）。增减服务商导致名次变化时，在授权内按新名次整体重排。这条只约束名称和优先级字段，不据此推断调度行为。
- **新建 provider 的倍率**：`cost_multiplier_ppm` 设为 1000000（1.0）；人工的倍率调整只在 key 层做，不回改已有的 provider。这只定新建的初值，不改变自动探测和自动写入策略；要固定某个 key 的手设倍率，按 `references/cchp-workflow-providers.md`〈key 的创建、更新与倍率〉的排除名单规则。
- **会话复用**：只有名次第 1 的 key 开会话复用；其他 key 没有本地覆盖、继承组织设置，并核实为关闭。
- **测活任务**：provider 下有已启用的 key 后，先查这个 provider 的测活任务，没有才建一条，已有就维护，不另建第二条。任务每小时一次（cron `0 * * * *`）、enabled、不通知；目标只含它下面已启用、且满足接口状态要求的 key（实测 disabled/revoked 会被拒），模型用平台为该 key 派生的测活默认模型（`getProviderKeyLivenessContexts`），不自行指定模型或 endpoint；当次 schema 或派生结果给不出模型时，停止这一项并报告。占位 key 换成真实密钥并启用后才加入。key 增减、启停或撤销时同步更新目标，改完回读任务、targets 和调度。
- **撤销或删除后的清理**：只清理本次对象的引用：key ID 从 `upstream_probe.ratio.key_denylist` 移除，provider ID 从 `upstream_probe.ratio.provider_denylist` 和 `upstream_probe.balance.provider_denylist` 移除；按〈配置继承与恢复〉的数组规则写入并回读全数组，不顺带清理历史上失效的引用。

## 配置变更前的快照

按待改的字段建立非秘密的恢复清单：provider 取列表或详情；key 已知 ID 时用 `getProviderKeysByIds --key-ids <keyId>`，未知时才用 `listProviderKeyPage` 定位再按 ID 重读；endpoint 和限额查对应的操作；系统配置只查相关 scope 下 `getSystemConfig` 的自有覆盖、继承和生效值，不扫无关的 scope，也不用 provider 列表冒充全量快照。记录对象、scope、版本、时间、是否有覆盖，以及已取的页和 key ID；`has_more` 没取完或 `partial`/`preparing` 没消解时只算部分，不能确认完整就不做依赖它的写入。

只投影已确认不含秘密、恢复必需的字段；关键字段缺失或秘密无法恢复时，说明缺口并停止依赖它的写入。含秘密的完整备份另走总控和 `luno-ops` 的受控归档，不用脱敏快照冒充可恢复的备份。回滚时按输入 schema 重建请求体；原来没有覆盖的，按契约移除，不把生效值写成本地覆盖。

## 配置继承与恢复

- 逐个键核对 scope、继承来源、合并还是替换的语义和生效值。`saveSystemConfig`、`removeKeys`、`getSystemConfig` 的 values/origins/overriddenKeys 和 `getConfigM2Page` 的参数、字段、reason，只认当次契约，不从同名或相邻的键外推，也不把读到的全集写回去。变更后回读自有覆盖、生效值和 origin；键消失或值等于默认，不证明覆盖已移除，恢复默认要核对最终值和来源。
- 只改 key 时，先核对是否支持 key 级覆盖和关闭的语义；改 provider 级之前，先核影响面和授权。会话复用先读默认值和现状，再核 provider × key 的组合，不假定下级的 true 能抵消上级的 false；需要改变未授权的 provider 前提时，停止这一项。
- **数组**先核是合并还是替换。替换时要完整读取目标数组，在现值上只增删授权的项，去重并保留其余；提交前重读现值，有变化就重新计算；改后比对整个数组。无法确认完整读取或没有并发保护时，不做依赖它的写入（包括组织级的 `upstream_probe.balance.provider_denylist`）。探测超时或地址为空只触发诊断，不授权停止探测或修改组织配置。

## 转发相关变更的验收与切换

- 配置回读只证明存储和生效视图，不证明转发可用。用本次授权的调用方发出最小的真实请求，以 requestId 关联 `listUsageLogs` 和尝试链，核对目标 provider、最终模型、状态和计费字段；HTTP 200 或非零成本都不能单独证明命中了新目标，要排除失败后被其他 provider 接管的情况。没有调用授权或链路证据时，只报告「配置已回读、链路未验证」，不扩展成由本技能执行网关调用。
- 替换上游且允许新旧并存时，先建新的并按上面的判据验证，再在授权内停用旧的；验证失败就保留旧路径，不为了验证停掉其他 provider。需要立即隔离旧路径的安全事件，按当次的处置授权执行，不机械坚持先验证。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。
<!-- END cchp-workflow-writes -->


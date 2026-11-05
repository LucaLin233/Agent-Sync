# 接口与契约（CCHP 控制面）

上游依据：CCH-HQ/cchp-cli@d9da5760a8d2f6ce689c01b98b6c96540513045d（2026-10-25，MIT，CLI 0.1.3／spec v1.0.12）的 `docs/agent-guide.md`、`docs/output-contract.md`、`docs/safety-model.md` 与 `skills/cchp/references/{auth,errors,output-contract,pagination}.md`；本文件为中文精选改写，删除上游面向人的入门叙述，只留本端要用的判据；列表形状、操作字段与分页只在命中操作时以当前内置 spec（`cchp schema`／`cchp commands show` 的 schema 与 `pagination` 描述符）核对，不在此缓存旧表。来源与分层见技能根 `luno-cchp/SOURCE.md`。

## 两条分支

| 分支 | 适用 | 前提 |
|---|---|---|
| `cchp` CLI | 默认分支。查询与小范围变更、需要离线查操作与 schema、需要门禁与脱敏 | 已安装 cchp；CLI 的 server 取 `CCHP_GATEWAY_URL`（管理 API 域），配已授权的 `CCHP_TOKEN`；`cchp status --json` 可读 |
| Management API 直连 | CLI 可用且已从 CLI 取得该操作契约，需要 HTTP 编排（批量读、接入现有 HTTP 客户端） | 同一实例、同一管理 token、同一组织；已从 CLI 取得该操作的 method 与 URL |

CLI 不可用、版本不符或 spec 与实例不匹配时，按 `luno-cchp/SKILL.md`〈执行位置与版本门槛〉停止并报缺口；直连不是缺 CLI 时的替代入口。

直连约束：
- 路径与方法从 `cchp api <operationId> --dry-run --json` 的 `method`／`url` 取，不凭记忆或第三方文档拼路径；请求体形状以 `cchp schema <operationId> --json` 为准。
- CLI 的门禁、脱敏、重试与分页在这一分支都**不生效**：写操作须自行加同等前置（改前取证、改后回读；自动重试与人工接续遵守本文件〈超时与重试〉），错误响应不得原样打印含凭据的头。
- 端点前缀、版本化路径与直连分页参数**需当次实测确认**；未确认前只做只读。

## 认证

- 管理 token 形如 `cch_auth_live_<prefix>_<secret>`；`cch_llm_live_…` 一类 LLM token 会被拒绝。
- 一个 token 属于「一个人＋一个组织」；有效权限是人员角色与 token 授权范围的交集。`getMyPermissionSummary` 看现状；被拒时 `denied_reasons` 为 `token_scope` 表示限制来自 token 本身。
- token 只随请求发往签约服务器的 origin（scheme＋host＋port 全匹配）；重定向到别处即丢弃，不携带 `X-CCH-Organization` 到其他组织。
- 明文 `http://` 只对回环地址成立。
- 取凭据只有本技能入口允许的那一种来源；`CCHP_TOKEN_FILE` 与保存态登录不在授权回退序列内。
- 需要浏览器会话的操作由 `cchp commands --all --json` 标为 `excluded`，无程序化替代。

## 实例端点与凭据（部署记录 2026-10-25/26；HTTP 探测 2026-10-26）

变量与缺失处置见 `luno-cchp/SKILL.md`〈实例与端点〉：两地址从环境注入（https），`CCHP_GATEWAY_URL` 用于面板与管理 API（`/api/*`），`CCHP_TOKEN` 用作管理面 `Authorization: Bearer`；`CCHP_BASE_URL` 用于 `{CCHP_BASE_URL}/v1/*`，LLM token 用作数据面 `Authorization: Bearer`（或 `x-api-key`）。CLI 的 server 须指向管理面，可逐命令覆盖 `CCHP_BASE_URL="$CCHP_GATEWAY_URL" cchp status --json`，勿把数据面地址当管理 server。

- 最小反例：2026-10-26 数据面域对带管理 token 的已测管理路径返回 401 `data plane requires LLM token`（code 10003）；不能据此断定管理 token 失效或未测路由存在。数据面 `GET /v1/models` 无凭据返回 401 `missing API key`；模型推理本轮未验证。
- 面板根 `/` 与 `/v1/models` 在面板域曾返回 200 HTML（SPA 回退），不能当数据面可用。

## 结果契约

`--json`、`CCHP_AGENT=1` 或 stdout 非终端即进入 agent 模式：stdout 恰好一个 JSON 结果对象（流式先逐行事件、末行终态），诊断与失败提示走 stderr，失败退出码非 0，无提示符、分页器与颜色。通用输出规则按需反向核实 `cchp guide agents|errors|tasks`；操作参数、响应与分页以 `cchp commands show <operationId> --json`、`cchp schema <operationId> --json` 的当前离线契约为准，不在此缓存字段大表或普通示例。

结果对象按操作返回 `schema_version`、`ok`、`operation`、`status`、`request_id`、`data`、`error`、`warnings` 等适用字段；列表、变更、密钥、下载、流式与 dry-run 分别可能带 `pagination`、`outcome`、`idempotency_key`、`secret`、`file`、`stream`、`dry_run`。缺失字段不作成功或完整性推断。

发现类命令（`commands`、`schema`、`version`、`guide`、`status`）同形，内容在 `data`。`cchp skill show` 默认输出原始 Markdown，`--json` 才回到结果对象。

**安全输出前置（含错误、流式与下载诊断）**：`data` 为服务端原值，不等于已获准展示。执行前按具体操作契约确认非秘密字段白名单，嵌套对象限定子字段；未知字段不输出。按 `luno-core/SKILL.md`〈授权与安全〉的秘密面规则，先做源头非秘密字段投影，按字段名、类型与元数据判敏，不以取样、整值捕获或内存后处理替代；全量／整对象读取仅限已确认不含秘密且在既有授权内，并先说明必要性。既有 CLI／客户端的安全捕获与内存投影只处理满足上述前提的响应，分别处理 stdout、stderr 与退出码，只把安全投影送入工具结果、会话或诊断文件，不先全量落盘后脱敏；不满足源头读取前提即停该读取／调用并报缺口，不猜 `--fields` 等旗标。必要且已确认非秘密的警告、授权／恢复限制与错误原文完整保留；含秘密或安全性不明时仅报位置、类型和缺口。一次性密钥仍只走入口已授权的 `--secret-out` 例外，不授权读取该秘密文件。

## 列表与完整性

列表默认一页。某操作的分页样式、续页旗标、limit 参数、next 字段与条目路径，先查 `cchp commands show <operationId> --json` 的 `pagination` 描述符；升级后重核，不从历史操作名或相邻响应推断。结果中的 `pagination` 依操作给出 `pages`、`items`、`has_more`、`truncated` 及 cursor/page 续页信息。

`partial` 或 `preparing` 为真时，该页不足以充当完整视图；先重取或按当次契约消解。无 `pagination` 描述符、无续页旗标或没有 next 字段，均不证明响应完整；按筛选、数量上限与返回契约核对目标集合，不能确认完整性时停止依赖写入。多页抓取遵循当前命令的 `--page-limit`／`--max-items` 与不透明 cursor，保持筛选条件不变，串行翻页；命中上限或 `truncated` 为真时报告部分结果。限流按 `hint` 有界等待，不并行重试。

## 错误与退出码


失败时 `error` 含 `kind`、`message`、`hint`、`code`、`detail`、`required_permission`、`challenge_action`、`fields`、`retryable`、`problem`（服务端 problem+json，已脱敏）。

| 退出码 | `kind` | 含义与处置 |
|---|---|---|
| 1 | `internal`／`http_error` | 未预期失败或异常状态码；取证后报 |
| 2 | `usage` | 命令或旗标不对、缺输入、cchp 不执行该操作；按 `hint` 修命令 |
| 3 | `unauthorized` | 认证未通过（401）：可能是 URL／token 类型不匹配，或 token 过期、撤销、写错。停止并报告，核对已授权的 URL／token 配对；不能仅凭 401 要求更换 token |
| 4 | `permission_denied` | 权限不足（403）：报 `required_permission` |
| 5 | `not_found` | 404：核 id |
| 6 | `conflict` | 409／412：现状不允许；重读现状再判断 |
| 7 | `invalid_input`／`validation` | 本地 schema 校验失败或服务端拒绝（400／422）；按 `fields` 修 |
| 8 | `browser_session_required`／`human_verification_required` | 428：只能由用户在控制台完成 |
| 9 | `rate_limited` | CLI／Management API 的 429 分类；确认可重试的管理面限流后按 `hint` 等待，仅只读可重试；不据此归因网关业务请求，业务拒绝按 `references/workflows.md`〈失败请求定位〉核查。 |
| 10 | `server_error` | 5xx：读可稍后重试；变更先查状态 |
| 11 | `not_sent` | 请求未离开本机：修因后按〈超时与重试〉接续 |
| 12 | `unknown_outcome` | 可能已到达服务端：停止变更并先查状态；接续按〈超时与重试〉 |
| 13 | `policy` | cchp 安全策略拒绝：核授权，不为过关叠旗标 |
| 14 | `not_signed_in` | 无凭据：报缺口，按入口的认证边界处理 |

## 请求／响应覆盖规则（request-overrides）

涉及 request-overrides 的操作、解释、建议或结论前，须完整读取 `references/coverage-rules.md`〈请求／响应覆盖规则：读取、草稿验证、变更与回读〉；本节不复述，也不为已随 CLI 0.1.3 移除的旧接口保留作用域断言。

## 分页

每个操作的续页参数与 next／items 路径只认 `cchp commands show <operationId> --json` 的 `pagination` 描述符；本文件不维护逐操作分页表。游标不透明，只能在同一筛选条件下传回；不构造或跨查询复用。无续页不代表完整，不能确认完整性时停止依赖写入。

只读查询按当前操作支持的 `--page-limit`／`--max-items` 串联翻页，不并行抓页；`rate_limited` 按 `hint` 等待。`--timeout`（默认 60 秒）约束整次运行含多页；到点返回的部分结果带 warning 与续页信息，部分结果不等于完整结果，报数必须说明。

## 流式与下载例外

- 流式：先逐行 NDJSON 事件（`type`、`operation`、`seq`、`event`、`id`、`data`），最后再给一个终态结果对象。agent 模式默认 20 个事件后停，`--max-events` 改上限，`--timeout` 可提前结束；终态对象的 `stream` 说明已投递事件数与结束原因（`max_events`／`deadline`／`server_closed`）。
- 下载：需要 `--output <新文件>`（`-` 走 stdout）；cchp 拒绝覆盖已有文件，`download-bundle` 同属下载、同样要 `--output`。响应体按字节原样落盘，不论 Content-Type（含 `text/event-stream` 与 NDJSON 响应帧），结果 `file` 的 `bytes`、`sha256` 描述的就是落盘文件，回读以 sha256 判等。请求归档标注该 part 非空、却下载到空内容时，以 `server_error`（退出码 10）失败，不报成功。
- `cchp skill show` 是契约例外：默认打原始 Markdown，加 `--json` 才回到结果对象。

## 超时与重试

`--timeout` 默认 60 秒。读在 2 次网络失败与 5xx 后重试两次；CLI 对变更**不自动重试**。超时发生在请求发出前为 `not_sent`，发出后应答未回为 `unknown_outcome`。人工接续前先查真实现态、确认原因和授权；仅操作支持且已返回／已发送 `idempotency_key` 时复用该键。未提供幂等头的操作按其业务专节处理，不套用该键；request-overrides 的例外见 `references/coverage-rules.md`〈请求／响应覆盖规则：读取、草稿验证、变更与回读〉。

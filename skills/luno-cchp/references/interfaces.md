# 接口与契约（CCHP 控制面）

本文件的判据以 CLI 0.1.3 / spec v1.0.12 为基线。列表形状、操作字段和分页一律在命中操作时以当前内置 spec（`cchp schema`、`cchp commands show`）为准，这里不缓存。

## 两个入口

- **`cchp` CLI**（默认）：查询和小范围变更，离线查操作和 schema，带门禁和脱敏。前提：已安装、server 指向管理面、配了已授权的 `CCHP_TOKEN`、`cchp status --json` 可读。
- **Management API 直连**：只在 CLI 可用、并已从 CLI 取得该操作契约、需要 HTTP 编排（批量读、接入现有 HTTP 客户端）时使用；同一实例、同一管理 token、同一组织。CLI 不可用、版本不符或 spec 与实例不匹配时按 `luno-cchp/SKILL.md`〈执行位置与版本门槛〉停止，直连不是替代入口。
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

**安全输出**（含错误、流式和下载诊断）：`data` 是服务端原值，不等于可以展示。执行前按具体操作的契约确认非秘密字段白名单，嵌套对象限定子字段，未知字段不输出；按总控〈秘密面〉做源头投影，按字段名、类型和元数据判敏，不靠取样或事后处理。CLI 或客户端的安全捕获和内存投影只用于满足上述前提的响应：分别处理 stdout、stderr 和退出码，只把投影结果送进工具结果、会话或诊断文件，不先全量落盘再脱敏。不满足前提就停止这次读取或调用并报告缺口，不猜 `--fields` 之类的旗标。必要且已确认不含秘密的警告、授权或恢复限制和错误原文要完整保留。一次性密钥只走 `--secret-out`，且不授权读取那个文件。

## 错误与退出码

失败时 `error` 含 `kind`、`message`、`hint`、`code`、`detail`、`required_permission`、`challenge_action`、`fields`、`retryable`、`problem`（服务端 problem+json，已脱敏）。完整的码表以 `cchp guide errors` 为准，决定处置的几个：

- **3 `unauthorized`**（401）：可能是 URL 和 token 类型不匹配（见上节的数据面反例），或 token 过期、撤销、写错。停止并报告，核对已授权的 URL/token 配对；不能只凭 401 就要求换 token。
- **9 `rate_limited`**：CLI/Management API 的 429；确认是可重试的管理面限流后按 `hint` 等待，只有只读可以重试。它不能用来归因网关的业务请求，业务拒绝按 `references/workflows.md`〈失败请求定位〉核查。
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

`--timeout` 默认 60 秒。读请求在网络失败和 5xx 后会自动重试两次；**CLI 对变更不自动重试**。超时发生在请求发出前是 `not_sent`，发出后没收到应答是 `unknown_outcome`。人工接续前先查真实现状，确认原因和授权；只有操作支持、并且已经返回或发送过 `idempotency_key` 时，才复用这个键。没有幂等头的操作按其业务专节处理；request-overrides 的写入没有幂等头，见 `references/coverage-rules.md`。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；取材基线、排除项与跟版条件见包内 luno-cchp/SOURCE.md。

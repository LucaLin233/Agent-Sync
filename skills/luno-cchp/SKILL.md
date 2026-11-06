---
name: luno-cchp
description: CCHP（Claude Code Hub Plus）控制面操作：通过 cchp CLI 或 Management API 查询用量与请求、管理 provider/key、LLM token、成员配额及导入；不承接通用 Linux/Compose 运维或 Minis 技能登记。
---
# LUNO｜CCHP 控制面

## 范围
CCHP（Claude Code Hub Plus）控制面：用量与耗材、请求日志、provider 与 provider key、LLM token、成员与配额、CC Hub 导入、少量设置读取。两条入口分支：`cchp` CLI（管理 token；spec 内置于 CLI，可离线查操作）与 Management API（HTTP 直连，只在 CLI 可用且已取得操作契约时用于编排）。网关转发、模型质量、通用 Linux/Compose/网络运维不属本技能；CLI 本体的定位、安装与升级按〈执行位置与版本门槛〉处理。

## 何时用／何时不用
用：查某实例用量与成本、定位失败请求、看或改 provider／key 状态、处理 LLM token 与配额、导入 CC Hub 数据、核对控制面与账目口径。
不用：宿主机部署、容器、反向代理、DNS/TLS、防火墙排障（→ `luno-ops`）；Minis 端技能登记与安装（→ `luno-minis`）；LobeHub 实例自身的模型与渠道配置（→ `luno-lobehub`）；CCHP 自身镜像／Compose 升级（→ `luno-ops`）。

## 实例与端点
管理面 `CCHP_GATEWAY_URL`＋`CCHP_TOKEN`、模型数据面 `CCHP_BASE_URL`＋LLM token 须为当次获准且已注入，两面不得混用；变量用途与错误反例见 `references/interfaces.md`〈实例端点与凭据〉。缺哪个入口或凭据即停其依赖的请求、命令与结论并报变量名；不回退旧地址、不猜子域、不换实例或其他环境。离线分析与另一入口的已授权操作可继续；身份和版本依〈执行位置与版本门槛〉核实。

## 资源与触发
路径相对本技能根目录。命中项须在动作前读完整资源；跨项取并集，中途新增先补读；资源缺失或版本不适用即停依赖并报缺口；加载不授权。
- 认证解析、结果契约、错误与退出码、分页、流式与下载例外，以及直连 Management API 的前置条件：必须读取 `references/interfaces.md`。
- 用量与耗材、失败请求定位、provider/key 的启停、撤销、创建与更新、endpoint 创建、配置快照、转发相关变更验收与切换、优先级与测活、配置继承与会话复用、倍率与探测、审计追溯、LLM token、导入：按命中业务标题读取 `references/workflows.md` 对应完整节；普通只读用量／请求查询不必加载整份业务全集。写入、恢复、覆盖或转发变更必须连读〈配置变更前的快照〉、〈配置继承与恢复〉及目标业务节；转发变更再读〈转发相关变更的验收与切换〉，导入再读〈CC Hub 导入〉，LLM token 再读〈LLM token〉，配额写入另读〈用量与耗材〉；新建 provider，或启停、撤销、删除 key 时，另连读〈key 的创建、更新与倍率〉；删除 provider 或 key 时，另连读〈provider 与 key 的启停、撤销〉。纯接口认证／分页咨询不触发业务节；直连 Management API 不得绕过。资源缺失或版本不适用即停止其依赖的操作、解释、建议及结论并报缺口。
- 涉及请求／响应覆盖规则（request-overrides；旧称“请求过滤器”，旧 operationId 已随 CLI 0.1.3 移除）的读取、解释、建议、草稿验证、创建、修改、恢复或其他操作／结论前，必须完整读取 `references/coverage-rules.md`；实际调用，或涉及认证、结果、错误、分页、重试契约的解释／结论前，另须完整读取 `references/interfaces.md`。创建、修改、恢复或其他写操作前，仍须按上一条完整读取 `references/workflows.md` 的共用变更与恢复节；实际涉及其他业务或跨业务机制比较时亦须读取相应业务节。仅纯文字解释且未命中上述接口、调用、写入或跨业务事项时，不自动加载这两份资源；与其他命中资源取并集，加载不授权。
- 动作前只读核对当次实例；错误码与计费口径以当次契约和实测为准，不凭历史记录推断。
- 来源、许可、改写边界与上游更新核对方法：技能根 `luno-cchp/SOURCE.md`（非加载资源，供溯源与再分发核对；判断是否跟版时按其〈上游更新核对〉执行）。
- 生产写入或不可逆动作前：必须完整加载 `luno-ops`，按其〈资源与触发〉读取远端落位／备份资源并执行改前备份与改后回读；授权核对、秘密面与跨会话交接按 `luno-core`〈授权与安全〉〈执行闭环〉。

## 执行位置与版本门槛
- 先定位置：CLI 可按授权安装在多台主机（含 Minis 本机），不预设固定主机；先确认当次执行主机、用户与项目，定位和安装均只在该环境进行。不得据文档或历史结论推断当前实例状态。
- 再找 CLI：先 `command -v cchp`；未命中不等于未安装，补核该用户的 `$HOME/.local/bin/cchp`、`/usr/local/bin/cchp`、`/opt/homebrew/bin/cchp` 等常见路径及已知自定义安装位置。候选不是穷尽清单；仍未找到时报「当前执行环境未定位到可用 CLI」，不据此断言未安装。找到后以选定入口执行 `version --json`，记录实际路径、CLI 与 spec 版本；后续使用同一入口。
- 安装／升级仅限当次授权的主机与目录，不改服务端或容器编排。核上游 `CCH-HQ/cchp-cli` 的 `install.sh` 来源及内容，以 `CCHP_VERSION`、`CCHP_INSTALL_DIR` 指定目标版本与获准目录（默认 `$HOME/.local/bin`），核 `checksums.txt` 通过；改前备份将覆盖的旧二进制。默认用明确路径；系统级入口已获授权、目标无冲突且目录在实际 PATH 时才建 `/usr/local/bin/cchp` 软链。改后按实际执行方式（含非交互 SSH）复验入口与 `version --json`；约定裸命令时另核 `command -v cchp` 命中预期路径。失败即停并报告，按备份与既有授权恢复。
- 再定身份与实例：遵守〈认证边界〉，用选定 CLI 执行 `status --json`，核对 server、token 前缀、身份与连通性；与当次授权不符即停。服务端版本（控制台或 `getSystemAbout`，CLI 为 `cchp admin about`）与 CLI／spec 版本一并记录；服务端版本未知，或动作语义依赖未核实的契约时，只做只读，不做依赖该契约的写。
- 版本门槛：未定位到可用 CLI、版本不符或 spec 与实例不匹配时，停止控制面操作并报缺口，不以 Management API 直连替代；已获授权的 CLI 定位、安装或升级可按本节处理，完成后重新核验前提。

## 认证边界
- 只用〈实例与端点〉的当次授权且已注入变量；缺失即停并报变量名，不换来源、不交互绕过。
- **不**回退 `CCHP_TOKEN_FILE`、`cchp login` 的保存态、系统 keychain、其他服务器或其他组织的 token；不读凭据文件、不枚举环境变量、不把 token 写进任何文件。
- token 不进命令行参数、会话、日志、提交或报告；一次性密钥（新建 token、生成码）只经 `--secret-out` 写入当次授权的受控路径，回报路径与字段名，不回显值。
- 管理 token 只能调用其权限范围内的操作；有效权限＝人员角色与 token 授权范围的交集。`excluded` 类操作（改密、通行密钥、二步验证、轮换 token、登录与安装流程）只能由用户在控制台完成。

## 核心循环
`cchp commands --search "<词>" --json` → `cchp schema <operationId> --json` → `cchp api <operationId> [--flag value] --json`。
- 操作旗标、风险门禁、示例与 pagination 描述符按当前 CLI 执行 `cchp commands show <operationId> --json`；agent、错误与任务的通用输出规则按需查 `cchp guide agents|errors|tasks`。不缓存普通命令示例或旧分页表；当前 CLI／spec 未给出的字段、旗标或续页方式不可猜。
- 参数是 kebab-case 旗标（`providerId` → `--provider-id`），数组重复书写；路径参数可就位；JSON 体走 `--body-file <file>` 或 `-`，先过本地 schema 校验再原样发送。
- 先 `--dry-run` 看将发出的 method、URL 与体（已脱敏），再决定是否加写门禁。
- `orgId` 默认取 token 所属组织；不指定其他组织。
- 分组命令与 `cchp api` 同源；operationId 仍是记录与交接的标识，但**以所选 CLI 内置 spec 为准**：升级后重新发现操作并核对 schema，不假定旧 operationId 继续存在。
- 一次只跑一个变更；不并发批量改，不在同一窗口混用不同操作。

## 门禁不是授权
- `--allow-write`、`--confirm <operationId>`、`--secret-out` 是 cchp 的工具门禁，只说明「这条命令可以发」，**不等于用户授权**，也不扩大当次授权范围；加之前须有当次用户请求或既有授权里的明确范围。
- 读的查询范围与导出上限、生产低负载、凭据与实例边界、写前取证与改后回读：按 `luno-core`〈授权与安全〉〈执行闭环〉；CCHP 的备份落位与回读执行按 `luno-ops`（加载要求见本文件〈资源与触发〉）。
- CLI 自动重试与人工接续前提依 `references/interfaces.md`〈超时与重试〉；request-overrides 无幂等头操作依 `references/coverage-rules.md`；其他无幂等头操作依其业务专节。

## 停止条件
遇到以下情形立即停，不绕路、不换入口试；按 `references/interfaces.md`〈结果契约〉的安全输出前置，报告已确认非秘密的 `error.kind`、`error.message` 与 `request_id` 必要原文，保留必要的非秘密警告及授权／恢复限制；含秘密或安全性未明时只报位置、类型和缺口，不回显未知内容：
- `permission_denied`（退出码 4）／`unauthorized`（3）：权限或 token 边界问题；有 `required_permission` 就照实报。
- `browser_session_required`／`human_verification_required`（8）：只能由用户在控制台完成，说明原因，不找替代路径。
- `unknown_outcome`（12）：结果未知，停止变更动作，先只读取证再决定。
- `policy`（13）：门禁拒绝；核对是否真属当次授权，不得为提高通过率而叠加旗标。
- 未满足〈执行位置与版本门槛〉中的 CLI 可用性或版本／契约前提；停止范围及恢复条件按该节执行。
- 需要超出当次授权的写入、不可逆动作、新环境或新凭据。

## 输出
给结论先行的中文答复：操作与目标实例、实际命令或 operationId、关键字段（用量、状态、`request_id`）、未执行项与不确定处；有变更时补改前状态、改后回读结果与回滚方式；影响转发时另报链路验证结果或未验证原因（判据见 `references/workflows.md`〈转发相关变更的验收与切换〉）。

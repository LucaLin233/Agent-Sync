# 共读资源（按原分支合并）

指针中的“分支”以 branch 锚点及 BEGIN/END 注释定界。沿用各分支原有触发和共同前置：完整读取命中的分支；原规则指定分节时，读取指定完整分节及共同前置，不加载未命中分支。同一文件的命中并集优先一次取齐，返回受限时分块补齐，不以截断内容作已加载。

分支内的“本文件”“本文”“本资源”均只指该分支，不把其他分支的接口事实、版本、能力或权限并入；“本技能”仍指原技能。主体、条件、例外、停止、恢复和许可边界保持原文，不因合并授予额外权限。跨技能先读目标技能入口及产品/业务入口；候选不改变现役规则。

分支：cchp、cchp-interfaces、cchp-workflow-writes。

<a id="branch-cchp"></a>
<!-- BEGIN cchp -->
# LUNO｜CCHP 控制面

## 范围与资源

用 `cchp` 管理用量、请求、provider/key、LLM token、成员配额、设置和 CC Hub 导入；CLI 离线发现操作，默认由它调用管理面。模型调用、宿主机与网络运维不在本资源范围。涉及运维或实际备份时按需加载 `luno-ops`；Minis 登记与 LobeHub 配置分别按 `luno-platform/references/minis.md`〔分支 minis〕和 `luno-platform/references/lobehub.md`〔分支 lobehub〕处理。

完整读取命中的资源；跨业务取并集：

- 实际 CLI/API 调用，或认证、结果、错误、分页、重试、流式、下载的解释：`references/cchp.md`〔分支 cchp-interfaces〕。
- 业务操作、解释、建议或结论按下列业务分支加载；涉及写入、恢复、覆盖或转发变更，另读 `references/cchp.md`〔分支 cchp-workflow-writes〕，组织约定与恢复规则仍适用。
## 业务分支

- 用量、成员配额、请求审计、LLM token、导入：`references/cchp-workflow-org.md`。导入预览创建 job，不是只读。
- provider/endpoint/key、倍率、测活或跨系统配置比较：`references/cchp-workflow-providers.md`。
- 覆写规则的读取、解释、建议、草稿验证或变更：`references/cchp-coverage-rules.md`；写入与跨业务比较另加载对应共同前置。
- 来源、许可或上游更新：`luno-platform/references/cchp-source.md`，普通调用不读来源档案。

## 入口、认证与版本

先确认获准的执行主机和用户，`command -v cchp` 定位；未命中再查该用户已知安装位置，不能据此断言未安装。记录选定入口的 `version --json`，后续固定使用；缺 CLI 就报告，安装升级须另有授权，核官方安装器、版本、目录、校验和、覆盖前备份及改后入口。

## 认证边界

管理面与模型数据面按技能入口〈实例与端点〉分开。CLI 从 `CCHP_BASE_URL` 读 server；本环境每次调用显式设置 `CCHP_BASE_URL="$CCHP_GATEWAY_URL"`，管理 token 使用 `CCHP_TOKEN`。缺变量停止依赖请求，不换来源或实例。
不回退到 `CCHP_TOKEN_FILE`、login 保存态或 keychain；不交互补取凭据。token 不进参数或输出，一次性秘密只经获准的 `--secret-out` 新文件交付，不读回内容。有效权限是人员角色和 token scope 的交集；excluded 的浏览器/人工操作交用户完成。

实例调用前核授权、server 和身份；`status --json` 等结果也须先满足安全投影。能取得时记录服务端版本；**CLI/spec 与服务端版本不同或服务端版本未知，不单独禁止操作**。每个动作仍须取得可用的操作契约，核方法、参数、权限及实际响应；契约无法确定、不支持或发生相关错误时停止该项。样本成功不证明全部操作兼容。

## 发现、schema、调用

`cchp commands --search "<词>" --json` → `cchp commands show <operationId> --json` → `cchp schema <operationId> --json` → `cchp api <operationId> … --json`。

参数、字段、风险门禁、分页和示例查所选 CLI，不缓存静态表或猜旧操作仍存在。请求体按输入 schema 构造，以 `--body-file` 或 stdin 交付；orgId 默认 token 所属组织。先 dry-run 核请求，再执行已授权变更；一次一个变更，不并发修改。

门禁不是授权：allow-write、confirm、secret-out 不能扩大用户请求。认证或权限拒绝、browser_session_required、human_verification_required、policy、unknown_outcome 或越权时停止相关操作，不换入口绕过。未知结果先只读取证；错误处置和安全输出按接口分支。

结论写明操作/目标实例、关键非秘密字段、request_id、覆盖及未核项；变更补改前状态、改后回读和恢复办法，转发变更按写入分支报告链路证据或未验证原因。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；取材见仓库 skills-sources.md，维护见包内来源资源。

<!-- END cchp -->

<a id="branch-cchp-interfaces"></a>
<!-- BEGIN cchp-interfaces -->
# 接口与契约（CCHP 控制面）

## 实例端点与凭据

默认 CLI。Management API 直连仅用于 CLI 可用且已取得具体操作契约的 HTTP 编排；同一管理面、token 和组织，按 `luno-platform/references/cchp.md`〔分支 cchp〕核准入，不因版本号差异单独拒绝。方法/URL 从 dry-run、请求体从 schema 取得；直连没有 CLI 的门禁、脱敏、重试或分页保障，须自行落实同等约束，不打印凭据头。

管理 token 不可用于模型数据面，LLM token 不可用于管理面。token 只发签约 origin，跨 origin 重定向不携带凭据；明文 HTTP 仅限回环。401 可能是 URL/token 类型配错，不能仅据 401 要求换 token；核已授权配对，不猜地址或换凭据。

执行前按操作 schema、字段名、类型和元数据确认非秘密白名单；嵌套投影，不展示未知 data、审计 payload 或任意规则值。按 `luno-core/references/execution.md`〔分支 safety〕做源头投影，分别捕获 stdout/stderr/退出码，仅输出白名单，禁止先全量落盘再脱敏。前提不足停止该读取。一次性秘密走 secret-out，不授权读文件。

## 官方结果与错误契约

输出字段和完整退出码按当前 `cchp skill show --file references/output-contract.md`、`cchp guide errors`；认证细节查内置 auth，但不得采用本端禁止的凭据回退。agent 模式 stdout 为一个结果对象，流式为事件行加终态；诊断走 stderr，失败退出码非零。缺字段不等于成功或完整，data 不因 CLI 输出就自动可展示；skill show 默认是原始 Markdown。

unauthorized/permission_denied 报安全的错误类型及缺权限；人工/浏览器操作只交用户；conflict 重读现状；policy 核授权，不叠加旗标绕过。not_sent 修因后接续，unknown_outcome 停止变更先查现状。读请求的网络/5xx 自动重试按 CLI 契约，变更不自动重试；仅在操作支持且已有 idempotency_key 时复用。管理面 429 按 hint 有限等待且仅重试读取，业务 429 另按 `references/cchp-workflow-org.md` 定因。必要且确认非秘密的错误、警告及恢复限制完整报告。

## 分页、流式与下载

默认一页；续页旗标、items/next 路径查 commands show 的 pagination，不缓存操作表。cursor 仅在原筛选条件下原样回传。partial/preparing、truncated、到期或未取完必须披露；没有描述符或 next 不能单独证明完整，无法确认完整就不做依赖它的写入。支持的 page-limit/max-items 串行取页，限流有限等待，不并行抓页；timeout 覆盖整次多页运行。

流式事件上限和结束原因查内置 output-contract；事件 data 同样先投影。下载必须授权新落点，不覆盖已有文件；按 file.bytes/sha256 核实际文件，不能用下载成功替代内容验证。空归档部分的错误、超时及续页警告按实际结果报告。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md。

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


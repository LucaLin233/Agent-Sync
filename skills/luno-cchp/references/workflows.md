# 业务动作与变更

命中某个业务时，先用 `cchp commands --search` 找 operationId，再查 `cchp commands show <operationId> --json` 和 `cchp schema <operationId> --json` 的当前契约；实例数字以当次实测为准，这里不落值。执行或展示结果前，按 `references/interfaces.md`〈结果契约〉逐个操作确认非秘密字段白名单；前提不满足就停止相关调用并报告缺口。不为示例访问实例，不用生产凭据做测试。

入口命中本资源时整份读取；整读只改变加载范围，不授权执行未请求的业务。所有写入仍须遵守组织约定、改前快照、配置继承与恢复及目标业务的判据。来源维护按包内 `luno-cchp/SOURCE.md`，完整档案见仓库 skills-sources.md。

## 本组织约定

以下是用户为本组织定的约定，不是 CCHP 平台的约束；用户当次的明确要求优先。所有写入都适用。

- **key 名称与优先级**：名称用 `厂家-服务商`，不带数字；优先级 = 用户确定的名次 × 10 + 厂家位（DeepSeek=1、OpenAI=2、Claude=3，名次从 1 开始）。增减服务商导致名次变化时，在授权内按新名次整体重排。这条只约束名称和优先级字段，不据此推断调度行为。
- **新建 provider 的倍率**：`cost_multiplier_ppm` 设为 1000000（1.0）；人工的倍率调整只在 key 层做，不回改已有的 provider。这只定新建的初值，不改变自动探测和自动写入策略；要固定某个 key 的手设倍率，按〈key 的创建、更新与倍率〉的排除名单规则。
- **会话复用**：只有名次第 1 的 key 开会话复用；其他 key 没有本地覆盖、继承组织设置，并核实为关闭。
- **测活任务**：provider 下有已启用的 key 后，先查这个 provider 的测活任务，没有才建一条，已有就维护，不另建第二条。任务每小时一次（cron `0 * * * *`）、enabled、不通知；目标只含它下面已启用、且满足接口状态要求的 key（实测 disabled/revoked 会被拒），模型用平台为该 key 派生的测活默认模型（`getProviderKeyLivenessContexts`），不自行指定模型或 endpoint；当次 schema 或派生结果给不出模型时，停止这一项并报告。占位 key 换成真实密钥并启用后才加入。key 增减、启停或撤销时同步更新目标，改完回读任务、targets 和调度。
- **撤销或删除后的清理**：只清理本次对象的引用：key ID 从 `upstream_probe.ratio.key_denylist` 移除，provider ID 从 `upstream_probe.ratio.provider_denylist` 和 `upstream_probe.balance.provider_denylist` 移除；按〈配置继承与恢复〉的数组规则写入并回读全数组，不顺带清理历史上失效的引用。

## 用量与耗材

- 以 `Units` 结尾的成本字段是信用分单位：10,000,000,000 units = 1 credit。报数时同时给原始 units 和换算后的 credit，都标单位，免得小数精度被四舍五入抹掉。
- 写配额前逐个字段核对输入单位、换算系数、精度和零值、空值的语义；输入是 units 时，先把授权额度换算成原始 units，不直接填 credit 或货币金额。回读同时列原始值和换算额度；credit 和货币的对应关系另核实例契约。
- 时间窗按服务端时区解释之前先核实例约定；跨天边界用显式的 `start`/`end`，报告里不写「今天」这类相对词。
- 用户账单按当次的实例文档或 openapi 核对计费字段、单位和口径，不自行推算；上游成本倍率不是用户的计费倍率（见〈key 的创建、更新与倍率〉）。
- 用量查询是只读，但范围仍要限定（组织、时间窗、条数），不整表导出。

## 失败请求定位

先筛时间窗，再看单个请求。列表过滤按当次 schema 覆盖失败和网关拒绝两类，不只查 failed。定位到 requestId 后，核对网关状态、拒绝原因和尝试链，区分本地配额或策略拒绝、上游限流、鉴权、超时和上游 5xx。429 不能单独证明是上游限流：本地配额要有拒绝主体和额度原因的证据，上游限流要有对应的尝试证据；尝试链缺失也不能单独证明是本地拒绝。结论带 requestId、时间、模型和 provider、类别和依据。

## provider 与 key 的启停、撤销

- `disableProviderKey` 可逆，用 `enableProviderKey` 复原；**`revokeProviderKey` 不可逆**，需要 `--allow-write --confirm revokeProviderKey`，只在用户明确要求时执行，执行前说明无法恢复。停用可以回滚，删除和撤销不能，报告里写清做的是哪一种。
- provider 级和 key 级是两种粒度：CCHP 没有 provider 级的 purge，物理删除要先处理 key（按当次实测核对）。
- 改前读一次目标对象的当前状态并记下关键字段，改后回读同一字段确认；两次读之间不夹其他变更。
- 列表续页按 `references/interfaces.md`〈分页〉，`--limit` 是每页条数；`data.partial` 或 `data.preparing` 为真时先重取，不根据这一页判断 key 状态或统计条数。
- 对已撤销的 key 不再尝试启停；状态冲突时先核当前状态和当次契约，不自动改走其他状态。
- 撤销或删除后按〈本组织约定〉清理排除名单。

## 配置变更前的快照

按待改的字段建立非秘密的恢复清单：provider 取列表或详情；key 已知 ID 时用 `getProviderKeysByIds --key-ids <keyId>`，未知时才用 `listProviderKeyPage` 定位再按 ID 重读；endpoint 和限额查对应的操作；系统配置只查相关 scope 下 `getSystemConfig` 的自有覆盖、继承和生效值，不扫无关的 scope，也不用 provider 列表冒充全量快照。记录对象、scope、版本、时间、是否有覆盖，以及已取的页和 key ID；`has_more` 没取完或 `partial`/`preparing` 没消解时只算部分，不能确认完整就不做依赖它的写入。

只投影已确认不含秘密、恢复必需的字段；关键字段缺失或秘密无法恢复时，说明缺口并停止依赖它的写入。含秘密的完整备份另走总控和 `luno-ops` 的受控归档，不用脱敏快照冒充可恢复的备份。回滚时按输入 schema 重建请求体；原来没有覆盖的，按契约移除，不把生效值写成本地覆盖。

## 配置继承与恢复

- 逐个键核对 scope、继承来源、合并还是替换的语义和生效值。`saveSystemConfig`、`removeKeys`、`getSystemConfig` 的 values/origins/overriddenKeys 和 `getConfigM2Page` 的参数、字段、reason，只认当次契约，不从同名或相邻的键外推，也不把读到的全集写回去。变更后回读自有覆盖、生效值和 origin；键消失或值等于默认，不证明覆盖已移除，恢复默认要核对最终值和来源。
- 只改 key 时，先核对是否支持 key 级覆盖和关闭的语义；改 provider 级之前，先核影响面和授权。会话复用先读默认值和现状，再核 provider × key 的组合，不假定下级的 true 能抵消上级的 false；需要改变未授权的 provider 前提时，停止这一项。
- **数组**先核是合并还是替换。替换时要完整读取目标数组，在现值上只增删授权的项，去重并保留其余；提交前重读现值，有变化就重新计算；改后比对整个数组。无法确认完整读取或没有并发保护时，不做依赖它的写入（包括组织级的 `upstream_probe.balance.provider_denylist`）。探测超时或地址为空只触发诊断，不授权停止探测或修改组织配置。

## provider 与 endpoint 的创建

- 创建 endpoint 前，核对端点类型、operations 和路径组装规则，分清 provider 根地址、版本前缀和操作路径；`base_url` 只填契约要求的那一层，不照搬完整的请求 URL。
- catalog 和自定义 endpoint 分别核对可写字段和目录约束；`path_overrides` 只在当次契约明确允许时提交，不从读取视图推断可写。422 先核类型和目录是否匹配，不靠追加路径绕过。
- 创建 provider 后，核对实际生成的 endpoint 和限额策略再决定是否补建；创建回执不代表只新增了请求体里的对象。发现重叠先核归属和引用，清理要另核授权和可恢复性，不自动删除。

## key 的创建、更新与倍率

- **请求体**：创建和更新都按输入 schema 重建请求体，不直接回写读取视图；嵌套数组也只取可写字段，`model_whitelist`、`model_redirects` 里的派生字段要逐项去掉。更新前核对是部分更新还是替换：部分更新只提交授权的字段；替换要确认能在授权和秘密边界内保留其余字段，否则停止；改后回读，确认没有扩大变更范围。
- **密钥来源只有两种**：本次授权且已注入的真实密钥，或用户本次明确要求的占位密钥；都没有就不创建。占位密钥用可辨认的非秘密串（如 `placeholder-<provider>-<YYYYMMDD>`），不取自也不仿写任何真实密钥；创建后立即 `disableProviderKey` 并回读确认已停用，报告标「占位、未启用」，并说明创建到停用之间可能被调度的风险。真实密钥由用户在控制台替换，或按授权注入后用 `rotateProviderKey` 替换；替换完成之前（控制台路径以用户告知为准，`rotateProviderKey` 以回执和回读为准），不启用、不测活、不做链路验证。
- **回读**：创建或更新后回读倍率、探测开关、白名单、优先级和状态；请求体不等于存储值，不一致时先核来源和审计，不直接归因于自动探测。
- `model_redirects` 在 CLI 0.1.3 的 create/update 输入里是数组字段（最多 500 条）；它和 request-overrides 的 `model_redirect` 预置是不是同一机制**未核实**，不推定等价，不用一个代替另一个。
- **倍率与探测**：`cost_multiplier_ppm`、`upstream_ratio_auto_detect` 和结果字段按 schema 和实例证据确认；关闭探测后分别验证开关和实际倍率，开关关了不等于倍率已恢复。组织级的 `upstream_probe.ratio.auto_apply` 对应面板的「自动写入成本倍率」，key 级的 `upstream_ratio_auto_detect` 对应「成本倍率自动探测」；倍率探测的排除名单是 `upstream_probe.ratio.key_denylist` 和 `upstream_probe.ratio.provider_denylist`，不要和余额探测的 `upstream_probe.balance.*` 混用。`upstream_probe` 定时任务每 30 分钟一轮，实际是否探测和写入要结合开关和排除名单核对。
- 上游成本倍率只影响「价格优先」的路由排序，不计入用户账单。要固定某个 key 的手设倍率，必须把它加入 `upstream_probe.ratio.key_denylist`，否则仍可能被自动覆盖；写名单按〈配置继承与恢复〉的数组规则。
- **CCH 与 CCHP 的差异**（用户实测 CCH 0.9.0 / CCHP 1.0.13，不外推其他版本）：CCH 只有手设的成本倍率，没有上游倍率的自动探测和自动写入；它的 `cost_multiplier` 字段不代表支持自动探测。跨系统同步配置时，不把 CCHP 的探测开关和自动写入策略当作 CCH 的可同步项。

## 审计追溯

`listOrgAudit` 用来追溯配置来源：参数、路径和分页按当次 schema 和返回确认，返回空不能单独证明参数不受支持；`occurredAt` 是 UTC。只输出已确认不含秘密的字段，未知的 `payload`/`value.preview` 不展示；审计不能代替当前状态的回读。

## 成员与配额

配额调整是写操作：先读现状（成员、当前配额和用量），按最小增量修改，改后回读；`conflict`（409/412）要重读现状再决定，不机械重试。成员和配额的人事决策归用户，这里只执行已确认的数值和对象。

## LLM token

只在用户本次明确要求新建 LLM token、并指定了可写的受控路径时执行，否则只讨论方案。一次性密钥只出现在 `--secret-out` 文件里（mode 600，拒绝覆盖已有文件），stdout 只有占位；回报文件路径和字段名，不回显值，也不把文件内容读进会话。令牌只在创建时可以取得，之后只能轮换或撤销；轮换不可逆，按用户的明确指令执行。

## CC Hub 导入

- 只在用户本次明确要求迁移或导入、持有平台管理员 token（含 `config:write`）、源站和目标站都已确认、冲突处置策略已由用户选定时执行。
- 流程：预览 → 复核计数和 warning → 追加（`--mode append`，保留现状）或覆盖（`--mode overwrite`，要用预览给出的确认短语）→ 报告 job 状态和 `report`。
- **`--preview-only` 也要求 `--allow-write`，并且会在服务端创建导入 job**（后续步骤引用它的 jobId）；它不是只读，也不是没有副作用，不能当作「先看看」的安全试探。
- 覆盖模式会替换已有数据，先按 `luno-ops` 做改前备份和可回滚点；失败时错误会指明 job，`retryable` 决定能否用 `cchp import retry <jobId>` 续跑。

## 转发相关变更的验收与切换

- 配置回读只证明存储和生效视图，不证明转发可用。用本次授权的调用方发出最小的真实请求，以 requestId 关联 `listUsageLogs` 和尝试链，核对目标 provider、最终模型、状态和计费字段；HTTP 200 或非零成本都不能单独证明命中了新目标，要排除失败后被其他 provider 接管的情况。没有调用授权或链路证据时，只报告「配置已回读、链路未验证」，不扩展成由本技能执行网关调用。
- 替换上游且允许新旧并存时，先建新的并按上面的判据验证，再在授权内停用旧的；验证失败就保留旧路径，不为了验证停掉其他 provider。需要立即隔离旧路径的安全事件，按当次的处置授权执行，不机械坚持先验证。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-cchp/SOURCE.md。

# 业务动作与变更限制

上游依据同 `interfaces.md`；业务口径中的实例数字不在此文件落值，以当次实测为准。本文件按现有业务标题披露判据，不缓存普通命令示例；命中分支时先用 `cchp commands --search` 找 operationId，再查 `cchp commands show <operationId> --json` 与 `cchp schema <operationId> --json` 的当前契约。agent、错误与任务通用规则按需查 `cchp guide agents|errors|tasks`。

执行或展示结果前，必须完整读取 `references/interfaces.md`〈结果契约〉的安全输出前置，逐操作确认非秘密字段白名单与异常出口。源头读取或安全捕获／投影前提不满足即停相关调用并报缺口；不为示例访问实例，不用生产凭据测试。

## 用量与耗材

- 成本字段以 `Units` 结尾的信用分单位：10,000,000,000 units = 1 credit。报数时给原始 units 与换算后的 credit，二者都标单位，避免小数点后精度被四舍五入抹掉。
- 写配额前逐字段核对输入单位、换算系数、精度及零值／空值语义；输入为 units 时先把授权额度换算为原始 units，不把 credit 或货币金额直接填入。回读同时列原始值与换算额度；credit 与货币的对应关系另核实例契约。
- 时间窗按服务端时区解释前先核实例约定；跨天边界用显式 `start`／`end`，不用「今天」这类相对词写入报告。
- 用户账单按当次实例文档或 openapi 核对计费字段、单位与计算口径，不自行推算；不要把上游成本倍率当作用户计费倍率，其作用见〈key 的创建、更新与倍率〉。
- 用量查询本身就是只读，但范围仍要限定（组织、时间窗、条数），不整表导出。

## 失败请求定位

顺序是「先筛窗口再进单请求」：列表过滤按当次 schema 覆盖失败与网关拒绝，不只查 failed；定位 requestId 后核网关状态、拒绝原因与尝试链，区分本地配额／策略拒绝、上游限流、鉴权、超时与上游 5xx。429 不单独证明上游限流；本地配额须有拒绝主体与额度原因证据，上游限流须有对应尝试证据；链缺失不独立证明本地拒绝。结论带 requestId、时间、模型／provider、类别与依据；字段及错误码以当次契约为准。

## provider 与 key 的启停、撤销

- `disableProviderKey` 可逆，用 `enableProviderKey` 复原；**`revokeProviderKey` 不可逆**，须 `--allow-write --confirm revokeProviderKey`，只在用户明确要求时执行，且执行前说明不可恢复。
- provider 级与 key 级是两种粒度：CCHP 没有 provider 级 purge，物理删除要先处理 key（接口行为，按当次实测核对）。
- 改前取证：目标对象当前状态（列表项或单条详情）先读一次并记下关键字段；改后回读同一字段确认。两次读之间不夹其他变更。
- 停用与删除不是同一动作：停用可回滚，删除/撤销不可回滚；报告里必须写清做的是哪一种。
- 续页依 `references/interfaces.md`〈分页〉，`--limit` 为每页条数；`data.partial` 或 `data.preparing` 为真先重取，不据此页判断 key 状态或统计条数。
- 对已撤销 key 不继续尝试启停；遇状态冲突先核当前状态与当次契约，不自动改走其他状态。
- 本组织用户约定：撤销或删除 provider 或 key 后，只清理本次对象的引用：key ID 从 `upstream_probe.ratio.key_denylist` 移除，provider ID 从 `upstream_probe.ratio.provider_denylist`、`upstream_probe.balance.provider_denylist` 移除；在授权范围内按〈配置继承与恢复〉的数组规则写入并回读全数组，不顺带清理历史失效引用；用户当次明确要求优先。

## 配置变更前的快照

按待改字段建立非秘密恢复清单：provider取列表/详情；key已知ID用 `getProviderKeysByIds --key-ids <keyId>`，未知才用 `listProviderKeyPage` 定位再按ID重读；endpoint/限额查对应操作，系统配置按相关scope查 `getSystemConfig` 的自有覆盖、继承与effective，不扫无关scope，不用provider列表冒充全快照。记录对象、scope、版本、时间、覆盖存在性及已取页/key ID；has_more未完或partial/preparing未消解只报部分，不能确认完整性即停依赖写入。

仅投影已确认非秘密、恢复必需字段；关键字段缺失或秘密无法恢复即说明缺口并停依赖写入。含秘密的完整备份另走core/ops受控归档，不用脱敏快照冒充可恢复备份。回滚体按输入schema重建；原无覆盖按契约移除，不把effective写成本地覆盖。

## 配置继承与恢复

逐键核scope、继承来源、合并/替换语义及生效值；`saveSystemConfig`、`removeKeys`、`getSystemConfig`的values/origins/overriddenKeys和 `getConfigM2Page` 的参数/字段/reason只认当次契约，不从同名/相邻键外推、不回写读取全集。变更后回读自有覆盖、effective、origin；键消失或值等于默认不证明覆盖已移除，恢复默认须核最终值与来源。

仅改key先核支持key级覆盖及关闭语义；provider级修改先核影响与授权。会话复用先读默认/现状，再核provider×key组合，不假定下级true抵消上级false；需要改变未授权provider前提即停该项。组织约定保留：仅名次1的key开会话复用，其他key无本地覆盖、继承组织且核为关；名次见〈key 的创建、更新与倍率〉，用户当次明确要求优先。

数组先核合并/替换；替换须完整读目标数组，在现值仅增删授权项、去重并保留其余。提交前重读现值，变化即重算；改后比对全数组。无法确认完整读取或并发保护即停依赖写入，包括组织级 `upstream_probe.balance.provider_denylist`；探测超时或地址为空只触发诊断，不授予停探测/改组织配置。其他ratio/balance denylist及撤销后只清本次对象的约定按对应业务节保留。

## provider 与 endpoint 的创建

- 创建 endpoint 前核对端点类型、operations 与路径组装规则，区分 provider 根地址、版本前缀和操作路径；`base_url` 只填契约要求的层级，不直接照搬完整请求 URL。
- catalog 与自定义 endpoint 分别核对可写字段及目录约束；`path_overrides` 仅在当次契约明确允许时提交，不从读取视图推定可写。422 先核类型与目录匹配，不靠追加路径绕过。
- 创建 provider 后核对实际生成的 endpoint 与限额策略，再决定是否补建；创建回执不代表仅新增了请求体中的对象。发现重叠先核归属与引用，清理须另核授权与可恢复性，不自动删除。

## key 的创建、更新与倍率

- 用户约定（非 CCHP 平台约束）：仅约束本组织内 key 的名称与优先级字段，用户当次对这两项的明确要求优先，不据此推断调度行为。名称用 `厂家-服务商`、不带数字，优先级＝用户确定的名次×10＋厂家位（DeepSeek=1、OpenAI=2、Claude=3，名次从 1 起）。增减服务商导致名次变化时，在授权范围内按新名次整体重排优先级。
- 本组织用户约定：新建 provider 的 `cost_multiplier_ppm` 设为 1000000（1.0），人工倍率调整只在 key 层进行，不回改已有 provider；本条只定新建初值，不改变自动探测与自动写入策略，要固定 key 的手设倍率仍按本节排除名单规则；用户当次明确要求优先。
- 创建与更新按输入 schema 重建请求体，不直接回写读取视图；嵌套数组同样只取可写字段，`model_whitelist`／`model_redirects` 中的派生字段也须逐项筛除；密钥来源只有两种：当次授权且已注入的真实密钥，或用户当次明确要求的占位密钥；两者都没有即停止创建。占位分支：值用可辨认的非秘密串（如 `placeholder-<provider>-<YYYYMMDD>`），不取自、不仿写任何真实密钥；创建后立即 `disableProviderKey` 并回读为停用，报告标「占位、未启用」，并说明创建到停用之间可能被调度的风险；真实密钥由用户在控制台替换，或按授权注入后用 `rotateProviderKey` 替换；替换完成（控制台路径以用户告知为准，`rotateProviderKey` 路径以回执与回读为准）前，不对该 key 启用、测活或做链路验证。创建或更新后回读倍率、探测开关、白名单、优先级与状态：请求体不是存储值，不一致时先核来源与审计，不直接归因于自动探测。
- `model_redirects` 在 0.1.3 的 create／update 输入 schema 里仍是数组字段（至多 500 条）；它与 request overrides 的 `model_redirect` 预置是否同一机制**未核实**，不推定等价、不用一方代替另一方。
- 倍率与探测字段（`cost_multiplier_ppm`、`upstream_ratio_auto_detect` 及结果字段）按 schema 与实例证据确认；关闭探测后分别验证开关与实际倍率，不把开关等同于倍率已恢复。
- **CCH／CCHP 能力差异**（据用户本次实测：CCH 0.9.0／CCHP 1.0.13；不外推其他版本）：CCH 只有手设成本倍率，没有「上游倍率自动探测／自动写入」能力；其 `cost_multiplier` 字段不代表支持自动探测。跨系统同步配置时，不把 CCHP 的探测开关与自动写入策略视为 CCH 的可同步项。
- CCHP 的组织级单键 `upstream_probe.ratio.auto_apply` 对应面板「自动写入成本倍率」，key 级 `upstream_ratio_auto_detect` 对应「成本倍率自动探测」；倍率探测排除名单为 `upstream_probe.ratio.key_denylist` 与 `upstream_probe.ratio.provider_denylist`，不要与余额探测的 `upstream_probe.balance.*` 混用。`upstream_probe` 定时任务每 30 分钟一轮；实际是否探测、写入须结合开关与排除名单核对。
- 上述上游成本倍率只影响「价格优先」路由排序，不计入用户账单。要固定某个 key 的手设倍率，须将其加入 `upstream_probe.ratio.key_denylist`，否则仍可能被自动覆盖；写名单仍遵守〈配置继承与恢复〉的数组变更规则。
- 更新前核对部分更新还是替换：部分更新只提交授权字段；替换须确认能在授权与秘密边界内保留其余字段，否则停止。改后回读，确认未扩大变更范围。
- 本组织用户约定：provider 下有已启用的 key 后，先查该 provider 的测活任务，缺失才建一条，已有则维护，不另建第二条。任务每小时一次（cron `0 * * * *`）、enabled、不通知；目标只含其下已启用且满足接口状态要求的 key，模型用平台为该 key 派生的测活默认模型（`getProviderKeyLivenessContexts`），不自行指定模型或 endpoint；当次 schema 或派生结果给不出模型时停该项并报。占位 key 按本节停用，换成真实密钥并启用后才加入。key 增减、启停或撤销时同步目标，改后回读任务、targets 与调度；用户当次明确要求优先。
- 测活目标须为接口允许的状态（本次实测 disabled／revoked 被拒）；不符合即停，不自动启用或换目标；改后回读 targets 与调度。

## 审计追溯

- `listOrgAudit` 用于追溯配置来源：参数、路径与分页按当次 schema 与返回确认，返回空不能单独证明参数不受支持；`occurredAt` 为 UTC。
- 只输出已确认非秘密字段，未知 `payload`／`value.preview` 不展示；审计不代替当前状态回读。CLI 分页依 `interfaces.md`〈分页〉。

## 成员与配额

- 配额调整属写操作：先读现状（成员、当前配额、用量），再按最小增量改，改后回读。
- `conflict`（409／412）表示请求与当前状态冲突：重读现状后再决定，不机械重试。
- 成员与配额的人事决策归用户；本技能只执行已确认的数值与对象。

## LLM token（仅满足下述启用条件时执行）

- 分支启用条件：用户当次明确要求新建 LLM token，并指定可写的受控路径。未满足即只讨论方案，不执行。
- 一次性密钥只出现在 `--secret-out` 文件（mode 600，拒绝覆盖已有文件），stdout 只有占位；回报文件路径与字段名，不回显值，不把文件内容读进会话。
- 令牌只在创建时可取；后续只能轮换或撤销。轮换属不可逆动作，按用户明确指令执行。

## CC Hub 导入（仅满足下述启用条件时执行）

- 分支启用条件：用户当次明确要求迁移/导入，且持平台管理员 token（含 `config:write`）；源站与目标站都已确认，冲突处置策略已由用户选定。
- 流程：预览 → 复核计数与 warning → 追加（`--mode append`，保留现状）或覆盖（`--mode overwrite`，须预览给出的确认短语）→ 报告 job 状态与 `report`。
- **`--preview-only` 仍要求 `--allow-write`，且会在服务端创建导入 job**（后续步骤引用其 jobId）；它不等于只读、也不等于无副作用，不得当作「先看看」的安全试探。
- 覆盖模式替换既有数据，先按 `luno-ops` 做改前备份与可回滚点；失败时错误会指明 job，`retryable` 决定 `cchp import retry <jobId>` 能否续跑。

## 转发相关变更的验收与切换

- 配置回读只证明存储／生效视图，不证明转发可用。用当次授权调用方产生的最小真实请求，以 requestId 关联 `listUsageLogs` 与尝试链，核目标 provider、最终模型、状态及计费字段；HTTP 200 或非零成本均不能单独证明命中新目标，须排除失败后由其他 provider 接管。无调用授权或链路证据时，只报配置已回读、链路未验证，不扩展为本技能执行网关调用。
- 替换上游且允许新旧并存时，先建新并按上述判据验证，再在授权内停旧；验证失败保留旧路径，不为验证停掉其他 provider。旧路径须立即隔离的安全事件按当次处置授权执行，不机械坚持先验证。

## 变更限制（CCHP 增量）

人工串行与 dry-run 依 `luno-cchp/SKILL.md`〈核心循环〉；CLI 自动重试与人工接续依 `references/interfaces.md`〈超时与重试〉，无幂等头操作按其业务专节；request-overrides 另依 `references/coverage-rules.md`。只读翻页、限流等待及不并行抓页／重试依 `references/interfaces.md`〈分页〉。查询、凭据、低负载及回读依 `luno-core/SKILL.md`〈授权与安全〉〈执行闭环〉，备份与回滚落位依 `luno-ops/SKILL.md`。

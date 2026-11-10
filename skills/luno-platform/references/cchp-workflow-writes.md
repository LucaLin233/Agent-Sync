# CCHP 写入共同规则

先完整读 `references/cchp-workflows.md`，按其触发与共同前置使用本资源；实际调用或展示结果先完整读 `references/cchp-interfaces.md`。

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

# CCHP 请求与审计定位

先完整读 `references/cchp-workflows.md`，按其触发与共同前置使用本资源。涉及写入的解释、方案、审查或执行，还须完整读 `references/cchp-workflow-writes.md`；实际调用或展示结果先完整读 `references/cchp-interfaces.md`。

## 失败请求定位

先筛时间窗，再看单个请求。列表过滤按当次 schema 覆盖失败和网关拒绝两类，不只查 failed。定位到 requestId 后，核对网关状态、拒绝原因和尝试链，区分本地配额或策略拒绝、上游限流、鉴权、超时和上游 5xx。429 不能单独证明是上游限流：本地配额要有拒绝主体和额度原因的证据，上游限流要有对应的尝试证据；尝试链缺失也不能单独证明是本地拒绝。结论带 requestId、时间、模型和 provider、类别和依据。

## 审计追溯

`listOrgAudit` 用来追溯配置来源：参数、路径和分页按当次 schema 和返回确认，返回空不能单独证明参数不受支持；`occurredAt` 是 UTC。只输出已确认不含秘密的字段，未知的 `payload`/`value.preview` 不展示；审计不能代替当前状态的回读。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。

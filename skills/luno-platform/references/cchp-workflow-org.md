# CCHP 用量、成员与配额、请求与审计、LLM token 与导入

先完整读 `references/cchp.md`，按其〈业务分支〉的触发与共同前置使用本资源。涉及写入的解释、方案、审查或执行，还须完整读 `references/cchp-workflow-writes.md`；实际调用或展示结果先完整读 `references/cchp-interfaces.md`。

## 用量与耗材

- 以 `Units` 结尾的成本字段是信用分单位：10,000,000,000 units = 1 credit。报数时同时给原始 units 和换算后的 credit，都标单位，免得小数精度被四舍五入抹掉。
- 写配额前逐个字段核对输入单位、换算系数、精度和零值、空值的语义；输入是 units 时，先把授权额度换算成原始 units，不直接填 credit 或货币金额。回读同时列原始值和换算额度；credit 和货币的对应关系另核实例契约。
- 时间窗按服务端时区解释之前先核实例约定；跨天边界用显式的 `start`/`end`，报告里不写「今天」这类相对词。
- 用户账单按当次的实例文档或 openapi 核对计费字段、单位和口径，不自行推算；上游成本倍率不是用户的计费倍率（见 `references/cchp-workflow-providers.md`〈key 的创建、更新与倍率〉）。
- 用量查询是只读，但范围仍要限定（组织、时间窗、条数），不整表导出。

## 成员与配额

配额调整是写操作：先读现状（成员、当前配额和用量），按最小增量修改，改后回读；`conflict`（409/412）要重读现状再决定，不机械重试。成员和配额的人事决策归用户，这里只执行已确认的数值和对象。

## 失败请求定位

先筛时间窗，再看单个请求。列表过滤按当次 schema 覆盖失败和网关拒绝两类，不只查 failed。定位到 requestId 后，核对网关状态、拒绝原因和尝试链，区分本地配额或策略拒绝、上游限流、鉴权、超时和上游 5xx。429 不能单独证明是上游限流：本地配额要有拒绝主体和额度原因的证据，上游限流要有对应的尝试证据；尝试链缺失也不能单独证明是本地拒绝。结论带 requestId、时间、模型和 provider、类别和依据。

## 审计追溯

`listOrgAudit` 用来追溯配置来源：参数、路径和分页按当次 schema 和返回确认，返回空不能单独证明参数不受支持；`occurredAt` 是 UTC。只输出已确认不含秘密的字段，未知的 `payload`/`value.preview` 不展示；审计不能代替当前状态的回读。

## LLM token

只在用户本次明确要求新建 LLM token、并指定了可写的受控路径时执行，否则只讨论方案。一次性密钥只出现在 `--secret-out` 文件里（mode 600，拒绝覆盖已有文件），stdout 只有占位；回报文件路径和字段名，不回显值，也不把文件内容读进会话。令牌只在创建时可以取得，之后只能轮换或撤销；轮换不可逆，按用户的明确指令执行。

## CC Hub 导入

- 只在用户本次明确要求迁移或导入、持有平台管理员 token（含 `config:write`）、源站和目标站都已确认、冲突处置策略已由用户选定时执行。
- 流程：预览 → 复核计数和 warning → 追加（`--mode append`，保留现状）或覆盖（`--mode overwrite`，要用预览给出的确认短语）→ 报告 job 状态和 `report`。
- **`--preview-only` 也要求 `--allow-write`，并且会在服务端创建导入 job**（后续步骤引用它的 jobId）；它不是只读，也不是没有副作用，不能当作「先看看」的安全试探。
- 覆盖模式会替换已有数据，先按 `luno-ops` 做改前备份和可回滚点；失败时错误会指明 job，`retryable` 决定能否用 `cchp import retry <jobId>` 续跑。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。

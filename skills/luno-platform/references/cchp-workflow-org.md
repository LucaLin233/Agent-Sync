# CCHP 用量、成员与配额、请求与审计、LLM token 与导入

先完整读 `references/cchp.md`〔分支 cchp〕；实际调用或展示结果读接口分支，涉及写入的解释、建议、方案、审查或执行另读写入共同分支。

## 用量与成员配额

官方 Units 成本换算为 10,000,000,000 units = 1 credit，同时报告原值和换算值。写配额前核输入单位、精度、零/空值语义，不能把 credit 直接填入 units；货币关系另核实例。限定组织、时间窗和条数，核时区，用显式 start/end。账单口径按当次契约，不把上游成本倍率当账单倍率，相关比较另读 `references/cchp-workflow-providers.md`。

成员和额度决策归用户；只执行已确认对象与数值，改前读现有配额及用量、最小变更、改后回读；冲突重读，不机械重试。

## 请求与审计

先时间窗再单请求，按当次 schema 覆盖失败和网关拒绝，不只筛 failed。以 requestId 核网关状态、拒绝原因和尝试链；429 不足以判断上游限流，缺尝试链也不证明本地拒绝。区分额度/策略、鉴权、上游限流、超时和 5xx，结论带时间、模型、provider、类别及证据。

审计追溯用 listOrgAudit，参数与分页查 schema；空结果不证明参数无效，审计不代替当前回读。未知 payload/value.preview 不展示，时间字段按当前契约解释。

## LLM token 与导入

新建 LLM token 必须有本次明确要求和受控可写新路径；secret-out 交付后只报路径及字段名，不读回。轮换不可逆，轮换或撤销只按用户明确指令执行，说明一次性秘密与恢复限制。

CC Hub 导入仅在本次明确要求、源目标和冲突策略已确认、具平台管理员及 config:write 权限时执行。命令按当前内置 workflows/schema：预览→复核计数与 warning→append 或 overwrite→报告 job/report。preview-only 也创建 job 并需 allow-write，不是只读；overwrite 需确认短语和改前备份，按 luno-ops 的授权流程处理。失败按 job 与 retryable 决定接续，不盲目重投。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；取材见仓库 skills-sources.md，跟版见包内 cchp-source.md。

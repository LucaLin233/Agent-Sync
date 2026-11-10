# CCHP 用量、成员与配额

先完整读 `references/cchp-workflows.md`，按其触发与共同前置使用本资源。涉及写入的解释、方案、审查或执行，还须完整读 `references/cchp-workflow-writes.md`；实际调用或展示结果先完整读 `references/cchp-interfaces.md`。

## 用量与耗材

- 以 `Units` 结尾的成本字段是信用分单位：10,000,000,000 units = 1 credit。报数时同时给原始 units 和换算后的 credit，都标单位，免得小数精度被四舍五入抹掉。
- 写配额前逐个字段核对输入单位、换算系数、精度和零值、空值的语义；输入是 units 时，先把授权额度换算成原始 units，不直接填 credit 或货币金额。回读同时列原始值和换算额度；credit 和货币的对应关系另核实例契约。
- 时间窗按服务端时区解释之前先核实例约定；跨天边界用显式的 `start`/`end`，报告里不写「今天」这类相对词。
- 用户账单按当次的实例文档或 openapi 核对计费字段、单位和口径，不自行推算；上游成本倍率不是用户的计费倍率（见 `references/cchp-workflow-providers.md`〈key 的创建、更新与倍率〉）。
- 用量查询是只读，但范围仍要限定（组织、时间窗、条数），不整表导出。

## 成员与配额

配额调整是写操作：先读现状（成员、当前配额和用量），按最小增量修改，改后回读；`conflict`（409/412）要重读现状再决定，不机械重试。成员和配额的人事决策归用户，这里只执行已确认的数值和对象。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。

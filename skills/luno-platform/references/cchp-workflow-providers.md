# CCHP provider、endpoint 与 key

先完整读 `references/cchp.md`〔分支 cchp〕，按其〈业务分支〉的触发与共同前置使用本资源。涉及写入的解释、方案、审查或执行，还须完整读 `references/cchp.md`〔分支 cchp-workflow-writes〕；实际调用或展示结果先完整读 `references/cchp.md`〔分支 cchp-interfaces〕。

## provider 与 key 的启停、撤销

- `disableProviderKey` 可逆，用 `enableProviderKey` 复原；**`revokeProviderKey` 不可逆**，需要 `--allow-write --confirm revokeProviderKey`，只在用户明确要求时执行，执行前说明无法恢复。停用可以回滚，删除和撤销不能，报告里写清做的是哪一种。
- provider 级和 key 级是两种粒度：CCHP 没有 provider 级的 purge，物理删除要先处理 key（按当次实测核对）。
- 改前读一次目标对象的当前状态并记下关键字段，改后回读同一字段确认；两次读之间不夹其他变更。
- 列表续页按 `references/cchp.md`〔分支 cchp-interfaces〕〈分页〉，`--limit` 是每页条数；`data.partial` 或 `data.preparing` 为真时先重取，不根据这一页判断 key 状态或统计条数。
- 对已撤销的 key 不再尝试启停；状态冲突时先核当前状态和当次契约，不自动改走其他状态。
- 撤销或删除后按 `references/cchp.md`〔分支 cchp-workflow-writes〕〈本组织约定〉清理排除名单。

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
- 上游成本倍率只影响「价格优先」的路由排序，不计入用户账单。要固定某个 key 的手设倍率，必须把它加入 `upstream_probe.ratio.key_denylist`，否则仍可能被自动覆盖；写名单按 `references/cchp.md`〔分支 cchp-workflow-writes〕〈配置继承与恢复〉的数组规则。
- **CCH 与 CCHP 的差异**（用户实测 CCH 0.9.0 / CCHP 1.0.13，不外推其他版本）：CCH 只有手设的成本倍率，没有上游倍率的自动探测和自动写入；它的 `cost_multiplier` 字段不代表支持自动探测。跨系统同步配置时，不把 CCHP 的探测开关和自动写入策略当作 CCH 的可同步项。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。

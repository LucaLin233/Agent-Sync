# 请求与响应覆盖规则

读取、解释、草稿验证和变更先按 `references/cchp.md`〔分支 cchp〕的资源与共同前置加载；实际调用读接口分支，写入或跨业务比较另读写入共同规则。

## 作用域、目录与读取

scope 是类型与 ID 组成的键，下级实体可带父级；合法形式查当前 listConfigScopes/getRequestOverrideCatalog，不复制固定类型表。省略组织时限 token 所属组织，不指向其他组织。inbound、attempt、response 分阶段版本；target/field 的 slots、ops、when 字段、预置及 limits 都查当前 catalog，不猜 scope、插件或阶段支持。

规则输入按当前 schema 构造，不缓存字段全集。读取 getRequestOverrideRuleSets 的 ruleSet（本级自有）、effective（生效集）、permissions；只写自有规则，不把继承规则复制成本级。上级锁定按 blockedBy 报告，不改写本级绕过锁；规则 ID、origin、patchOrigin 须在现状中核到。

## 草稿验证

validateRequestOverrides 在内置契约中为 read，不落库、不发模型请求；是否获准调用仍按任务范围。取样 request/response/draft 按 schema，以逐规则结果、action 前后和 final 核变换；通过不证明上游接受取值。失败按当前字段错误修因，不用生产测试补猜。

## 变更、锁与恢复

patchRequestOverrideRule 只改一条 enabled/lock；saveRequestOverrideRuleSet 是整个 phase 替换，遗漏即删除。请求体、风险及门禁查 commands show/schema；写前重读 scope、phase、version 和目标，保留未授权范围内修改，先 dry-run。两项在当前 CLI/spec 没有幂等头，失败先读现状，不凭幂等键重投。写后回读本级版本/规则、生效视图与权限。

lock_all、单规则锁和 patches 按当前 schema、目标 ID 和来源处理。历史 CLI 0.1.3 样本曾允许不存在 ID 通过 validate，当前未复测；不能把 validate 成功当作 ID 存在或锁行为已验证。

历史修订用 listRequestOverrideRevisions/getRequestOverrideRevision，完整性按接口分支，不拿部分列表做恢复依据。restoreRequestOverrideRevision 把历史内容写成新的当前版本，只影响目标 phase，不是回退指针；属于 destructive 写，单独授权，不自动当作撤销步骤。

## 相邻入口

LLM token 的 get/save/validateMyKeyRequestOverrides 不是 provider key 入口，阶段按当前契约；applyRequestOverridePreset 是写入，不用于只读查询。涉及 model_redirects 与预置比较或 key 更新，读 `references/cchp-workflow-providers.md`，未核实前不互相替代。

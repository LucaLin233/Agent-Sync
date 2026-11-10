# 业务动作与变更

先完整读本入口，再完整读命中的业务资源；跨业务比较取并集。不执行未请求的业务，不为示例访问实例或用生产凭据测试。先用 `cchp commands --search` 找 operationId，再查 `cchp commands show <operationId> --json` 和 `cchp schema <operationId> --json` 的当前契约；实例数字以当次实测为准。执行或展示结果前，完整读 `references/cchp-interfaces.md`，逐操作确认非秘密字段白名单；前提不满足就停止相关调用并报告缺口。

## 写入共同前置

涉及写入、恢复、覆盖或转发变更的解释、建议、方案、审查或执行，先完整读 `references/cchp-workflow-writes.md`。本组织约定、改前快照、配置继承与恢复适用于所有写入；纯只读用量或请求定位不加载写入规则。

## 业务分支

- 用量、耗材、计费、成员或配额：`references/cchp-workflow-usage.md`。
- 失败请求定位或审计追溯：`references/cchp-workflow-requests.md`。
- provider/endpoint/key 的状态、启停、撤销、删除、创建、更新、倍率、探测、model_redirects 或跨系统配置比较：`references/cchp-workflow-providers.md`。
- LLM token 创建、轮换或撤销：`references/cchp-workflow-tokens.md`。
- CC Hub 迁移、导入或预览：`references/cchp-workflow-import.md` 和写入共同规则；预览会在服务端创建 job，不是只读。
- 配置继承与恢复的解释，转发相关变更的验收或切换：`references/cchp-workflow-writes.md`。配置回读不等于链路验证，本技能不因此获得网关调用权。

上述各分支命中即完整读取；写入均另满足共同前置。来源维护按包内 luno-platform/references/cchp-source.md，完整档案见仓库 skills-sources.md。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-platform/references/cchp-source.md。

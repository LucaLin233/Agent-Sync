# CCHP provider、endpoint 与 key

先完整读 `references/cchp.md`〔分支 cchp〕；实际调用或展示结果读接口分支，涉及写入的解释、建议、方案、审查或执行另读写入共同分支，组织五项约定不变。

## 状态与创建

disableProviderKey 可由 enableProviderKey 恢复；revokeProviderKey 不可逆，仅明确要求时执行并说明后果。门禁按 commands show；已撤销对象先核当前状态，不自动换操作。改前/改后读同一对象；列表 partial/preparing 未消解，不据单页定状态或数量。撤销删除后按写入共同分支清理本次对象引用。

provider 与 key 是不同粒度；旧 CLI/spec 只提供 key purge，不据此断言当前服务端没有 provider 删除能力。物理删除需当次契约与授权，不用破坏性调用验证约束。

endpoint 先核类型、catalog、自定义字段及路径组装，不把完整请求 URL 当 base_url。只提交 schema 允许的 path_overrides；422 先核契约，不靠追加路径绕过。创建后核实际 endpoint/限额和已有对象关系；历史的附带生成现象不是所有版本保证，清理另核授权。

## key 的创建、更新与倍率

按 create/update 输入 schema 重建请求体，嵌套数组只取可写字段，不能整包回写读取视图。核部分更新还是替换；替换若无法保留其余字段或秘密即停止。改后核倍率、探测开关、白名单、优先级和状态，不凭请求体或单次差异归因自动探测。

密钥只来自本次授权且注入的真实变量，或用户本次明确要求的可辨认非秘密占位串。占位 key 创建后立即 disable 并回读，报告占位未启用及创建到停用间可能被调度的风险。真实密钥由用户在控制台替换，或按授权注入后 rotateProviderKey；控制台以用户告知、CLI 以回执及回读确认，完成前不启用、不测活、不验证链路。

model_redirects 的形状和上限查当前 schema，不与 request-overrides 的 model_redirect 预置推定等价。

## 倍率、探测与必要场景

手设倍率前核 cost_multiplier_ppm、探测/自动应用开关及相关 scope 的 allowlist/denylist；关闭探测不证明倍率恢复。upstream_probe.ratio 与 balance 名单不能混用，数组按写入共同分支规则处理。固定某 key 倍率时保留现行 key_denylist 防覆盖策略；是否存在其他方式、名单优先关系及开关映射须当次核契约，不能据旧记录断言唯一办法。

2026-11-11 对服务端 1.0.14+build.53 的只读核查确认组织 ratio.enabled/auto_apply、排除名单和全局间隔配置仍存在；30 分钟是当时有效值，不是永久常量。该核查没有证明倍率对排序/账单的因果关系、每个 key 的探测行为或全部配置组合。涉及这些结论时定向核证，不沿用未复核断言。

跨系统比较时，既有 CCH 0.9.0/CCHP 1.0.13 差异只作历史线索，不把 CCH 的 cost_multiplier 字段当自动探测能力，也不把 CCHP 探测策略直接同步过去。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 ../LICENSE.upstream.txt；取材见仓库 skills-sources.md，跟版见包内 cchp-source.md。

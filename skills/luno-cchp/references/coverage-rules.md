## 请求／响应覆盖规则：读取、草稿验证、变更与回读

作用域键是 `<scope_type>:<id>`。合法类型由 `listConfigScopes` 给出（global、organization、team、model、provider_group、provider、provider_key、provider_key_whitelist_rule、provider_endpoint、user、user_key）；带下级实体的键把父级写在 `@` 之后，如 `provider_key:*@provider:<id>`、`user_key:*@user:<id>`。0.1.3 实测的拒收形态：裸 `global` → `config: invalid scope_key`，未知类型 → `config: invalid scope_type`，`organization:` 缺 id → `config: scope_id required for organization`；`global:*` 与 `model:*` 可读。键里不含组织的按 token 所属组织解析；只有平台管理员可用 `--organization-id` 指向别处，本端不指定。示例不是合法集全集；以当次 `getRequestOverrideCatalog --scope` 与报错为准，被拒按 `validation`（422，code 31500）修因，不猜键、不换凭据、不改走直连。

phase为inbound、attempt、response，独立版本。target能否使用取决于phase；错配可被服务端以target_unavailable_in_phase拒绝。实施前读目标scope当前catalog，逐项核targets[].slots/ops及fields[].slots；不缓存某次观测的target矩阵，不从缺项推断不支持，亦不猜plugin等未验证能力。

同一次 catalog 还给出 `fields[]`（可作 `when.field`，含 `slots`）、`operators[]`、`variables[]`、`presets[]` 与 `limits`（`maxRulesPerPhase`／`maxActions`／`maxValueBytes`）；枚举与取值类型以当次 catalog 为准，字段名写错会逐条报 `unknown_field`，不凭猜。

规则形状（`Rule`／`Condition`／`Action`，全量枚举见 `cchp schema` 的 `$defs`）：`Rule` 必填 `name`、`enabled`、`actions`，可选 `id`、`lock`、`when`、`description`、`preset`、`managedBy`；`when` 用 `field`＋`op`＋`value` 或 `all`／`any`／`not` 组合；`actions[]` 每项必填 `target`，`op` 与配套字段按 target 取——header 类用 `name`／`namePattern`（不给 `path`），JSON／path 类用 `path`；`value` 是任意 JSON 值，不要求写成 JSON 字面量字符串。

读取：`cchp api getRequestOverrideRuleSets --scope <scope> --json` 返回 `data.scope`、`data.phases.{inbound,attempt,response}`、`data.permissions`；每个 phase 给 `ruleSet`（本 scope 自有：`phase`、`version`、`lock_all`、`rules`、`patches`）、`effective`（合成后的生效集）与 `presetModified`；`version` 为 0 表示从未保存。

区分自有与生效：`effective[]` 每条是 `EffectiveRule`（全量字段见 schema；`status` 为 `active`｜`blocked_by_ancestor_lock`）。写只写自有：`own=false` 的规则不在本 scope 的 `ruleSet.rules` 里，整表回写会把继承规则复制成本级规则；被上级锁定的条目按 `blockedBy` 报出，不改写本级去「解锁」。

草稿验证：`validateRequestOverrides` 顶层 schema 仅必填 `scope`；本节做取样变换验证时提供 `request`（提供时 `path` 必填、body 为字符串），并按需提供 `response`、`phases`、`draft{phase:{rules,patches}}`。它不发真实请求、不落库；返回 `rules[]`（逐条 `result` 与 `actions[]` 的 `before`／`after`／`outcome`／`note`）与 `final` 快照（字段见 schema）。422 时 `error.detail` 逐条给 `rule #i` 的 `pointer` 与 `code`（实测见过 `unknown_field`、`invalid_parameter`、`target_unavailable_in_phase`、`invalid_patch`）。验证通过只说明变换结果与取样请求吻合，不证明上游接受该取值。

两种写不可互换：
- `patchRequestOverrideRule`（PATCH，`risk=write`）：只改一条规则的 `enabled` 或 `lock`，body `{version, enabled?|lock?}` 只给要改的那个，需 `--allow-write`、不需 confirm。
- `saveRequestOverrideRuleSet`（PUT，`risk=destructive`）：整 phase 替换，body 必填 `version`、`lock_all`、`rules`、`patches`，需 `--allow-write --confirm saveRequestOverrideRuleSet`；未带上的规则等于删除。

写前：重读该 phase 的 `version` 与目标规则现状，确认 scope／phase／版本三者；保留未授权的他人修改，不用旧快照整表覆盖；先 `--dry-run` 看 method、URL 与体。这两个操作在 spec 里都没有 `Idempotency-Key`（spec 中另有 48 个操作带该头），失败不得靠幂等键重试，只能先查现状再决定。

写后回读：`ruleSet`（`version` 递增、规则集符合预期）、`effective`（生效集与 `origin`／`patchOrigin`）、`permissions`。版本或状态不符按实际 `error.kind` 处理；本操作版本冲突的确切响应未验证，不按 HTTP 码猜。

`lock_all`、`lock` 与 `patches`：`lock_all` 与每条 `Rule.lock` 是锁定声明；被上级锁定的条目在 `effective` 里是 `status=blocked_by_ancestor_lock` 并带 `blockedBy`。`patches` 是 `{id, set:{enabled}}` 列表（`PatchSet` 只有 `enabled`），`effective[].patchOrigin` 非空表示启用态由 patch 决定；校验不查 id 是否存在（实测格式合法但不存在的 id 通过 validate），写前须在 `effective`／`ruleSet` 核到该 id 及 `origin`。两者在实例上的行为未逐项实测，以当次 schema 与回读为准。

版本与恢复：版本是每个 phase 的快照号。`listRequestOverrideRevisions --phase <phase> --scope <scope>` 给 `{version, createdAt, actor, reason, ruleCount}`（无 `pagination` 描述符；完整性按 `references/interfaces.md`〈分页〉判定）；`getRequestOverrideRevision --version <n>` 另给 `document` 与 `lock_all`。`restoreRequestOverrideRevision` 把历史版本内容写成**新的当前版本**（上游 “as a new version”），不退指针、不回滚其他 phase 或该 scope 的其他配置；属 destructive 写，须单独授权，不随常规变更触发，也不当「撤销刚才的改动」的自动步骤。

两个相邻入口别混：
- LLM token 自己的覆写走 `getMyKeyRequestOverrides`／`saveMyKeyRequestOverrides`／`validateMyKeyRequestOverrides`，路径是 `/api/account/api-keys/{keyId}/request-overrides`，只有 inbound 与 response；这里的 keyId 是 **LLM token**，不是 provider key，不能当 provider key 的覆写入口。
- `applyRequestOverridePreset` 把预置规则写进某 phase（`risk=write`，需 `--allow-write`），不在只读路径上使用；实际涉及 provider key 输入 `model_redirects` 与 `model_redirect` 预置的比较、替代或 key 创建／更新时，须完整读取 `references/workflows.md`〈key 的创建、更新与倍率〉；两者关系未核实，不推定等价。仅解释覆盖规则且未涉及该比较或业务时不触发该资源。


# 请求与响应覆盖规则

覆盖规则（request-overrides）的读取、草稿验证、变更和回读。字段全集以当次 `cchp schema` 和 catalog 为准，这里只写判据和已实测的坑（CLI 0.1.3）。

## 作用域与 phase

- **作用域键**是 `<scope_type>:<id>`。合法类型由 `listConfigScopes` 给出（global、organization、team、model、provider_group、provider、provider_key、provider_key_whitelist_rule、provider_endpoint、user、user_key）；带下级实体的键把父级写在 `@` 后面，如 `provider_key:*@provider:<id>`、`user_key:*@user:<id>`。
- 0.1.3 实测的拒收形态：裸 `global` → `config: invalid scope_key`；未知类型 → `config: invalid scope_type`；`organization:` 缺 id → `config: scope_id required for organization`。`global:*` 和 `model:*` 可读。
- 键里不含组织时按 token 所属的组织解析；只有平台管理员能用 `--organization-id` 指向别的组织，本端不指定。上面的例子不是合法集的全部：以当次 `getRequestOverrideCatalog --scope` 和报错为准，被拒按 `validation`（422，code 31500）修正原因，不猜键、不换凭据、不改走直连。
- **phase** 有 inbound、attempt、response 三个，各自独立计版本。target 能不能用取决于 phase，错配会被拒（`target_unavailable_in_phase`）。实施前读目标 scope 当前的 catalog，逐项核对 `targets[].slots`/`ops` 和 `fields[].slots`；不缓存某次观测到的 target 矩阵，不从缺项推断不支持，也不猜 plugin 之类没验证过的能力。
- 同一次 catalog 还给出 `fields[]`（可用作 `when.field`）、`operators[]`、`variables[]`、`presets[]` 和 `limits`（`maxRulesPerPhase`/`maxActions`/`maxValueBytes`）。字段名写错会逐条报 `unknown_field`。

## 规则形状

`Rule` 必填 `name`、`enabled`、`actions`，可选 `id`、`lock`、`when`、`description`、`preset`、`managedBy`。`when` 用 `field` + `op` + `value`，或用 `all`/`any`/`not` 组合。`actions[]` 每项必填 `target`，`op` 和配套字段按 target 取：header 类用 `name`/`namePattern`（不给 `path`），JSON/path 类用 `path`；`value` 是任意 JSON 值，不需要写成 JSON 字面量字符串。

## 读取：自有与生效

`cchp api getRequestOverrideRuleSets --scope <scope> --json` 返回 `data.scope`、`data.phases.{inbound,attempt,response}` 和 `data.permissions`。每个 phase 有 `ruleSet`（本 scope 自有：`phase`、`version`、`lock_all`、`rules`、`patches`）、`effective`（合成后的生效集）和 `presetModified`；`version` 为 0 表示从未保存。

`effective[]` 的每条带 `status`（`active` 或 `blocked_by_ancestor_lock`）。**只写自有规则**：`own=false` 的规则不在本 scope 的 `ruleSet.rules` 里，整表回写会把继承来的规则复制成本级规则。被上级锁定的条目按 `blockedBy` 报出，不改写本级去「解锁」。

## 草稿验证

`validateRequestOverrides` 只要求 `scope`；做取样变换验证时要给 `request`（`path` 必填，body 是字符串），按需给 `response`、`phases`、`draft{phase:{rules,patches}}`。它不发真实请求、不落库，返回逐条规则的 `result` 和每个 action 的 `before`/`after`/`outcome`/`note`，以及 `final` 快照。422 时 `error.detail` 逐条给出 `rule #i` 的 `pointer` 和 `code`（实测见过 `unknown_field`、`invalid_parameter`、`target_unavailable_in_phase`、`invalid_patch`）。验证通过只说明变换结果和取样请求吻合，不证明上游接受这个取值。

## 两种写操作

两者不能互换：

- `patchRequestOverrideRule`（PATCH，`risk=write`）只改一条规则的 `enabled` 或 `lock`，body `{version, enabled?|lock?}` 只给要改的那一项；需要 `--allow-write`，不需要 confirm。
- `saveRequestOverrideRuleSet`（PUT，`risk=destructive`）**整个 phase 替换**，body 必填 `version`、`lock_all`、`rules`、`patches`，需要 `--allow-write --confirm saveRequestOverrideRuleSet`；没带上的规则等于删除。

写之前重读这个 phase 的 `version` 和目标规则现状，确认 scope、phase、版本三者一致；保留未授权范围内别人的修改，不用旧快照整表覆盖；先 `--dry-run` 看 method、URL 和请求体。这两个操作都没有 `Idempotency-Key`，失败后不能靠幂等键重试，只能先查现状再决定。

写之后回读 `ruleSet`（`version` 递增、规则集符合预期）、`effective`（生效集和 `origin`/`patchOrigin`）和 `permissions`。版本或状态不符时按实际的 `error.kind` 处理；版本冲突的确切响应没验证过，不按 HTTP 码猜。

## 锁与 patches

`lock_all` 和每条 `Rule.lock` 是锁定声明；被上级锁定的条目在 `effective` 里是 `blocked_by_ancestor_lock` 并带 `blockedBy`。`patches` 是 `{id, set:{enabled}}` 列表，`effective[].patchOrigin` 非空表示启用状态由 patch 决定。校验不检查 id 是否存在（实测格式合法但不存在的 id 也能通过 validate），所以写之前要在 `effective` 或 `ruleSet` 里核到这个 id 和它的 `origin`。锁和 patches 在实例上的行为没有逐项实测，以当次 schema 和回读为准。

## 版本与恢复

版本是每个 phase 的快照号。`listRequestOverrideRevisions --phase <phase> --scope <scope>` 给出 `{version, createdAt, actor, reason, ruleCount}`（没有 `pagination` 描述符，完整性按 `references/interfaces.md`〈分页〉判定）；`getRequestOverrideRevision --version <n>` 另给 `document` 和 `lock_all`。

`restoreRequestOverrideRevision` 把历史版本的内容写成**新的当前版本**，不是退回指针，也不回滚其他 phase 或这个 scope 的其他配置。它是 destructive 写，要单独授权，不随常规变更触发，也不当作「撤销刚才的改动」的自动步骤。

## 相邻入口

- LLM token 自己的覆写走 `getMyKeyRequestOverrides`/`saveMyKeyRequestOverrides`/`validateMyKeyRequestOverrides`，路径是 `/api/account/api-keys/{keyId}/request-overrides`，只有 inbound 和 response。这里的 keyId 是 **LLM token**，不是 provider key，不能当 provider key 的覆写入口。
- `applyRequestOverridePreset` 把预置规则写进某个 phase（`risk=write`，需要 `--allow-write`），不在只读路径上用。provider key 的 `model_redirects` 输入和 `model_redirect` 预置的关系没核实，不推定等价；涉及两者比较、替代或 key 的创建和更新时，按 `references/workflows.md`〈key 的创建、更新与倍率〉处理。

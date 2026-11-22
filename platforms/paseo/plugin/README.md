# Shared role providers 插件

两个 Paseo provider（`cchp`、`gdr`）承载 LUNO、LENS、FORGE 六个 Profile。角色来自 Profile 的
`options.paseo_role` 与 `options.paseo_upstream`：`agent.create.before` 校验后把绑定写入 agent
元数据并移除这两个路由键，`agent.open.before` 再从绑定推导 `CODEX_HOME`、角色原文和预期上游，
以启动 env 交给服务端。Codex 适配器在首个 turn 之前核对同一活线程的
`codexRoleVerification`（`role`、`upstream`、`resolvedModel`、`roleMatches`、`overrideExists`、
`upstreamMatches`），缺证或错配不发模型请求。

## 文件

- `index.server.ts`：create/open 两个钩子；LUNO 交互会话另附加一段宿主侧编排说明。
- `server/roles.ts`：角色表、绑定校验、上游匹配和选项清理；部署只需改这一处路径。
- `paseo-plugin.json`：插件清单，要求 Paseo >= 0.17.1。

`server/roles.ts` 的路径是公开占位值，部署时替换为实际安装根。`lens-codex`、`forge-codex`、
`lens-gdr`、`forge-gdr` 是角色家目录名，不是 provider ID；两个 LUNO 角色共用主 Codex home。
四个 LENS/FORGE 家目录的 `config.toml` 需要 `[agents] enabled=false` 与
`[features] multi_agent_v2=false`，LUNO 家目录不加这两项。

插件目录通过 Paseo 官方插件设置接入（`pluginsEnabled` + 目录来源）；本仓库不提供自动安装、
迁移或切换脚本。启用、回读和回退边界见仓库 README〈Paseo 共享角色体系〉。

## 行为边界

- 新派发由编排每次 `list_profiles` 按 `options.paseo_role`、`options.paseo_upstream` 选同上游唯一
  Profile，再把 `provider/model`、`modeId`、`thinkingOptionId` 和 `options` 传给 `create_agent`，
  正式任务只用一次 `initialPrompt`。
- 桌面前台直建只在无编排调用、前台且所选共享 provider 的 `providerOptions` 同时缺少
  `paseo_role` 和 `paseo_upstream` 时，由服务端按该 provider 的上游绑定 LUNO；显式选择 Profile
  以 Profile 的角色为准；只给一个字段或值错配仍拒绝。创建请求不携带 Profile ID，服务端无法区分
  未选 Profile 与所选 Profile 两字段均缺失，详见[根 README](../../../README.md#插件与派发)。
- 草稿 Speed 只用 provider 固定启动信息查询能力，不启动线程、不投消息。

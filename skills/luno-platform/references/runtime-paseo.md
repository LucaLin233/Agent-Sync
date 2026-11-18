# paseo 叠加适配

当前端为 Claude Code 或 Codex，且会话可用 paseo 编排工具（如 `create_agent`）或存在指定变量 `PASEO_AGENT_ID` 时，另读本资源。它只补跨会话、跨 provider 的派发；其余槽位仍按 `references/runtime-claude-code.md` 或 `references/runtime-codex.md` 与 `references/runtime-host.md`。义务、授权和停止条件以引用处为准，本资源不新增或放宽权限。

## 派发通道

- **角色 provider**：`lens-claude`、`forge-claude`、`lens-codex`、`forge-codex`。每个 provider 有独立家目录 `~/.luno/homes/<provider>/`（Claude Code 用 `CLAUDE_CONFIG_DIR`，Codex 用 `CODEX_HOME`），常驻提示词就是 `subagents/` 中对应角色的原文（安装器软链），不含 LUNO 常驻提示词和 GLOBAL。配置样例见仓库 `platforms/paseo/config.example.json`。各家目录由用户分别登录；安装器不读取、不复制凭据或登录态，也不预置权限配置，沙箱和审批按 paseo 中该 provider 的模式与 provider 默认设置。
- **派单**：`create_agent`，`provider` 取 `<角色 provider>/<模型>`，`initialPrompt` 为派单，`notifyOnFinish` 为真；实施类先用 `create_workspace` 以 worktree 隔离从基线分出任务分支。参数名以工具当前 schema 为准。编排工具未注入时，用 CLI：`paseo run --provider <角色 provider> --no-wait`，等待用 `paseo wait <id> --timeout <秒>`。
- **时限**：paseo 不设平台上限，负责人为每次派发设定时限。超时先用 `get_agent_status` 核真实状态，未确认终止就不重派同一写任务；取消用 `cancel_agent`。
- **追问或续派**：`send_agent_prompt`，`activeTurnBehavior` 取 `steer`。
- **身份核验**：`get_agent_status` 或 `list_agents` 返回的 provider id 即实际角色，模型取同一返回的模型字段，记入回包和 PR。首次使用某个角色 provider 时，另核对其加载来源确为该家目录中的角色文件（Codex 为线程启动返回的 `instructionSources`）；核清前按「通道身份未验证」处理。
- **审批**：子会话的权限请求经 `list_pending_permissions`、`respond_to_permission` 或手机端处理，仍按原授权判断，不因请求来自 paseo 而放宽。

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

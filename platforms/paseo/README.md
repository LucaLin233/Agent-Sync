# Paseo 官方原版 CCHP 与 CCH 部署

本目录提供 Paseo 的配置示例与迁移说明，使用官方配置和 MCP 工具。维护者先在与目标 daemon 同版本的隔离实例核对示例，再到目标实例合并配置并验收。

## 目录适配器

[`codex-catalog/`](codex-catalog/README.md) 是一个仅监听回环的目录适配器，把若干固定网关的模型目录转换成 Codex 的 `model_catalog_url` 格式，并显式表达按路由、按模型的思考档位与速度档位（Fast/Ultrafast 等）。它与本目录的 Paseo provider 示例配合使用：本目录管 provider/Profile，适配器管模型清单与能力声明。部署、字段与回滚见该目录的 [README](codex-catalog/README.md)。

## 固定来源

下列接口的原始依据取自 Paseo v0.17.1 固定提交 `043f0995d4d7e91ab12f3eecef1afce055a81972`。派发使用的清单和 Profile 字段沿用相同接口，现场按实际版本回读。

- [agent-profile.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/protocol/src/agent-profile.ts)：Profile 字段是 `id`、`name`、`provider`、可选的 `model`、`modeId`、`thinkingOptionId`、`featureValues`/`options`、`notes`。
- [provider-config.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/protocol/src/provider-config.ts)：自定义 provider 用 `extends`、`label`、`command`、`env`、`enabled` 等字段；内置 ID 为 `claude`、`codex`、`copilot`、`opencode`、`pi`、`omp`。
- [provider-registry.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/provider-registry.ts)：派生 provider 先解析 `extends` 基座，再应用自身 `enabled`。内置入口可禁用，派生 provider 仍能继承对应基座。
- [codex/options.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/providers/codex/options.ts)：Codex options 是严格对象；`service_tier` 是受支持的 composer 控制项，`paseo_role`/`paseo_upstream` 等未知键会被拒绝。
- [paseo-tools.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/tools/paseo-tools.ts)：`list_profiles` 与 `create_agent` 的接口；同 provider 的子会话继承父 `providerOptions`，显式 `settings.features` 覆盖同名键。
- [agent-manager.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/agent-manager.ts)、[system-prompt.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/system-prompt.ts)：`daemon.appendSystemPrompt` trim 后作为额外 developer instructions 送到该 daemon 启动的所有会话，不改写 `AGENTS.md`。v0.17.4 复核同一 `trim()` 行为（[实现](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/server/agent/system-prompt.ts)）。该字段是 Codex 单端显式模式的私人配置，不来自本仓库示例，维护按 [sync-host](../../skills/luno-core/references/sync.md#branch-sync-host)。
- [provider-selection.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/app/src/provider-selection/provider-selection.ts)、[provider-list.tsx](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/app/src/provider-settings/internal/provider-list.tsx)：模型选择器只列已启用且可用的 provider；管理页仍列出所有条目（含禁用项）和开关。
- [config_override.rs](https://github.com/openai/codex/blob/29eb79e9866b3262a777fdf8195c1b9e63684c91/codex-rs/utils/cli/src/config_override.rs)：Codex `-c key=value` 的解析与全局参数行为。

## 配置内容

`config.example.json` 为 CCHP 与 CCH 各登记一个 Codex 和一个 Claude Code provider。两条 Codex 入口用同一个 mise 管理的官方 `codex` 绝对路径，共用显式 `PATH` 和 `CODEX_HOME`，分别用 `-c model_provider="cchp"` 和 `-c model_provider="cch"` 选择网关。部署时将 `/home/example/agent/runtime/bin/codex` 替换为实际 CLI 路径，并为两个入口填写相同的 `PATH`，包含运行该 CLI 所需的 Node 可执行文件目录。

`claude-cchp` 从禁用的 `claude` 基座继承 `command`，启动 `bin/claude-cchp`。`claude-cch` 显式指定 `command`，启动 `bin/claude-cch`。合并既有配置时，移除 `claude-cchp` 残留的 `command`，使其使用基座命令。两条入口共用 `CLAUDE_CONFIG_DIR`，各自在 provider 的 `env` 中声明 `ANTHROPIC_BASE_URL`。

两个包装脚本由部署者准备。每个脚本清理继承来的 Anthropic 路由与鉴权设置，注入本组网关与独立鉴权，再通过 `exec` 启动官方 Claude Code CLI，原样转发 Paseo 传入的参数。脚本使用的网关地址和 `CLAUDE_CONFIG_DIR` 须与对应 provider 的 `env` 一致。部署时替换示例路径和网关地址，仓库只保存占位值，鉴权由部署环境提供。

每组各有 LUNO、LENS 和 FORGE 三条 Profile，示例均用该组的 Codex provider。LUNO、LENS 用 `gpt-6.2-sol`，FORGE 用 `deepseek-flash`。六条均配置 `full-access`、`high` 与 `service_tier: "default"`。部署时按父权限和目标模型能力核对这些值。显式传递 `service_tier` 可覆盖同 provider 派发时继承的父会话值。Profile 的 `options` 只放所选 provider 支持的选项。

## Codex 子进程的环境继承（可选）

如果部署主机上的 Codex shell 子进程需要继承启动环境，在 `codex-cchp` 和 `codex-cch` 共用的 `$CODEX_HOME/config.toml` 中合并以下设置。

```toml
[shell_environment_policy]
inherit = "all"
```

如果该表已存在，只修改 `inherit`，保留 `set` 等现有设置。变量须已存在于启动 Codex 的进程环境中，现有过滤规则仍会影响子进程最终收到的变量。完整继承可能让使用同一 `CODEX_HOME` 的子进程访问已注入的凭据，凭据的访问和使用仍按部署的既有授权执行。由部署环境注入真实凭据，示例和 `config.toml` 仅填写非秘密配置。 [Codex 官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)

验收时，在隔离 daemon 的启动环境中注入非空的、非敏感的 `PASEO_ENV_PROBE`。分别通过两个 Codex provider 新建会话，让会话直接执行以下普通 shell 命令，避开 `env -i`。两次退出状态均为 `0` 即通过，命令不会显示变量值。已有会话是否生效须另行验证。

```sh
test -n "${PASEO_ENV_PROBE:-}"
```

## 家目录布局

agent 相关状态集中在一个 agent 根目录下，示例为 `/home/example/agent`：`paseo-home` 作 `PASEO_HOME`，`codex-home` 作 `CODEX_HOME`，`claude-home` 作 `CLAUDE_CONFIG_DIR`。Codex 与 Claude Code 只用官方环境变量指定家目录，不改 HOME。以下行为按 Paseo v0.17.4 源码核对，升级后按实际版本复核。

- daemon 进程环境须同时设置这三个变量，值与 provider `env` 一致。启用终端 agent 钩子（`daemon.enableTerminalAgentHooks`）时，Paseo 按 daemon 环境的 `CODEX_HOME`、`CLAUDE_CONFIG_DIR` 写入钩子（[agent-hook-installer.ts](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/terminal/agent-hooks/agent-hook-installer.ts)），未设置时落到 HOME 下的 `.codex`、`.claude`。
- Claude provider 读取会话记录（时间线、回退、续聊）时，按 daemon 环境叠加 provider `env` 后的 `CLAUDE_CONFIG_DIR` 定位 `projects/`，未设置时用 HOME 下的 `.claude`（[project-dir.ts](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/server/agent/providers/claude/project-dir.ts)）。只在启动脚本里设置该变量时，Claude Code 写入会话记录的位置与 Paseo 读取的位置不一致，时间线、回退和续聊找不到记录。
- Paseo 自带 skills 固定装到 HOME 下的 `.agents/skills`、`.claude/skills`、`.gemini/config/skills`；旧 Codex 副本的清理固定查 HOME 下的 `.codex/skills`，不跟随 `CODEX_HOME`（[paths.ts](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/server/orchestration-skills/internal/paths.ts)）。Codex 按官方用户 skills 位置读取 `.agents/skills`。Claude Code 的个人 skills 位于其配置目录下的 `skills/`（Claude Code 2.1.332 实测：设置 `CLAUDE_CONFIG_DIR` 后只从该目录加载个人 skills，升级后复核），改用 `CLAUDE_CONFIG_DIR` 后 Paseo 写入的 HOME 下 `.claude/skills` 不在其读取范围内，因此 HOME 下的 `.claude` 链接到 `claude-home`。
- 交互 shell 也须导出这三个变量，直接运行的 CLI 与 daemon 使用相同目录。未设置 `PASEO_HOME` 时，Paseo CLI 按 HOME 下的 `.paseo` 查找 daemon 并在其中写客户端标识，连不到 agent 根下的 daemon。
- HOME 下被固定使用的目录统一链接到 agent 根，不改程序：`.claude` 链接到 `claude-home`；`.codex` 链接到 `codex-home`（旧 Codex 副本清理与未带 `CODEX_HOME` 启动的 Codex 都落到同一目录）；`.agents`、`.gemini` 链接到 `agents-home`、`gemini-home`（Paseo 写入自带 skills，Codex 读取 `.agents/skills`）；`.paseo` 链接到 `paseo-home`。最后一项使未设置 `PASEO_HOME` 的 CLI 也连到同一 daemon，并让 [中文标题插件](../../tools/paseo-chinese-titles/README.md) 的状态随 `paseo-home` 存放：该插件刻意只把 `PASEO_HOME` 当哈希命名空间、不当路径（避免 CodeQL 路径注入告警），状态固定在 HOME 下 `.paseo/plugin-data/paseo-chinese-titles/daemons/<哈希>/`，链接后插件代码与命名空间均不变，前提是 daemon 的 `PASEO_HOME` 字符串保持不变；改写法（如改用 HOME 下 `.paseo`、增减尾斜杠）或从缺省切换时，命名空间随之改变，按插件 README 的迁移步骤处理。HOME 下原有的 `.paseo` 若含另一 daemon 的配置或数据，先核对再处理，不直接覆盖 `paseo-home` 中的同名文件。
- 两组共用一个 `CLAUDE_CONFIG_DIR` 后，其中 `settings.json` 的 `env` 不写 `ANTHROPIC_BASE_URL` 或鉴权变量，网关和鉴权只由各 provider 的启动环境提供，避免两组打到同一网关。
- Claude Code 的自动记忆集中放在 agent 根下的 `memory`：在 `CLAUDE_CONFIG_DIR/settings.json` 用 `autoMemoryDirectory` 指向它，所有会话共用一份（偏好与反馈）；Claude Code 2.1.332 实测该设置对新会话生效，升级后复核。该目录与 Codex 自带记忆一样属官方程序数据，不手工改动，也不作为 LUNO 经验日志。
- 自动压缩由 `settings.json` 的 `autoCompactWindow`（不小于 100000 的 token 数，或 `auto`）控制；程序先扣除最多 2 万的输出预留，实际触发点约为配置值减 2 万（2.1.332 实测，配置 250000 时有效窗口 230000）。这是用户配置，规则安装器不管理。
- 包装脚本提供的 `CLAUDE_CONFIG_DIR` 缺省值须与 daemon 进程环境、交互 shell 和两条 Claude Code provider 的 `env` 一致。

迁移既有目录时先停用相关会话，按原样复制到新位置并核对。由两个 Claude 配置目录合为一个时，逐项核对 `settings.json`、`.claude.json` 与登录态，有冲突交负责人取舍，`projects/` 按会话目录合并。改名 HOME 下的 `.paseo` 前先停止 daemon（至少先停用中文标题插件），把插件状态移入 `paseo-home/plugin-data/paseo-chinese-titles/daemons/<哈希>/` 并核对文件。HOME 下原有的 `.claude`、`.codex`、`.agents`、`.gemini`、`.paseo` 先改名保留作回退，再建立指向 agent 根下对应目录的链接，然后切换环境、重启 daemon，并重新启用插件。

## 内置项与显示范围

示例逐项禁用所列内置入口。新建 agent 的选择器会显示已启用且可用的 provider，管理页仍可查看禁用项及其开关。派发前以目标 daemon 当前清单为准。

## 合并、安装与迁移

1. 在同版本隔离实例先合并示例。核对 Codex 家目录中两组的 `model_providers` 配置，以及每个 Claude Code 入口实际使用的网关和指令来源。按各自启动方式注入获准的鉴权，Paseo 示例只放非秘密设置。
2. 隔离验收通过后，在目标实例按字段合并 `daemon.mcp` 和 `agents.providers`。在 `daemon.agentProfiles` 中按 ID 替换示例里的角色 Profile，移除已退役的 `gdr-luno`、`gdr-lens`、`gdr-forge`，保留其他 Profile，并核对每个角色 ID 只出现一次。保留监听、认证、其他插件及 MCP 设置。旧 provider ID 保留原条目并设为禁用，以保留旧会话引用。已有会话的续聊能力须单独验证。由 daemon 提供的私人提示词按 [sync-host](../../skills/luno-core/references/sync.md#branch-sync-host) 维护。来自热修版的迁移仍须核对旧插件和实际程序入口，再按既有迁移与回退范围处理。
3. 合并后执行 `paseo reload`，按回执处理需要重启的路径，再回读四个 provider 的可用状态和六条 Profile。从获准的新会话验收实际 provider、模型和权限模式。Claude Code 被选作角色 provider 时，另验首行角色识别与受管原文加载。

## 角色协议（软角色）

显式使用 `paseo-append-system-prompt` 且登记启用 `paseoRoleStartup` 时，安装器生成 Codex 角色启动段。采用其他入口时，先核验实际加载的等效角色指令，再启用首行角色派发。首条任务正文的第一行恰为 `角色：LUNO`、`角色：LENS` 或 `角色：FORGE` 时采用对应角色，任务正文紧随其后；没有角色行时按 LUNO。桌上或 MCP 直接选择角色 Profile 后，首条消息仍要写这一行，漏写按 LUNO。接口与首行投递按 [Paseo 派发通道](../../skills/luno-platform/references/runtime-paseo.md#branch-paseo-dispatch)，生成入口的渲染与回读见 [sync-host](../../skills/luno-core/references/sync.md#branch-sync-host)。

LENS/FORGE 开始前必须完整读取部署的 `subagents/LENS.md` 或 `subagents/FORGE.md` 原文；该启动段由已核检出路径渲染，示例不再保留占位路径。角色只选择提示词，不授予新的文件、网络、凭据、审批或派发权限；受派后不得再委派；任何角色声明都不改变现行规则规定的准入。

同一 Codex provider 的角色共用其 `CODEX_HOME`、登录态和文件系统。Claude Code 角色的指令来源按其实际启动入口核实。

## 派发契约

配置使用 `<运行时>-<网关>` 和 `<网关>-<角色小写>` 登记。例如 `claude-cchp` 父会话可按 `cchp-lens` 派到同组的 `codex-cchp`。新增网关时先配置实际 provider 和角色 Profile，再核实时清单。派发步骤及停止条件以 [Paseo 派发通道](../../skills/luno-platform/references/runtime-paseo.md#branch-paseo-dispatch) 为准。

## 隔离与前态

仓库不提供现成隔离前缀。隔离验收需另建同版本 npm 前缀，并配独立 `PASEO_HOME`、回环端口和临时 HOME，不能原地改写现役前缀。隔离 daemon 及其 provider `env` 的 `CODEX_HOME`、`CLAUDE_CONFIG_DIR` 指向临时目录，不继承交互 shell 的取值。旧会话可能保存运行时注入的提示词，回退设置不会清除历史。

从热修版切换失败时，在同一维护窗口恢复原配置、插件与原程序入口，按原托管方式重启并回读健康状态及 Profile。只改过配置时，恢复原配置后按 `paseo reload` 的结果处理。

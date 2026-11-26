# Paseo 官方原版 CCHP 与 CCH 部署

本目录提供 Paseo 0.17.4 的配置示例与迁移说明。示例使用官方配置和 MCP 工具。维护者在目标实例合并配置并验收。

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

`config.example.json` 为 CCHP 与 CCH 各登记一个 Codex 和一个 Claude Code provider。Codex 入口用 `-c model_provider="<网关>"` 选择上游，两组共用同一 `CODEX_HOME`。Claude Code 入口用各自的 Anthropic 兼容 `ANTHROPIC_BASE_URL` 选择上游，两组共用同一 `CLAUDE_CONFIG_DIR`。部署时替换 agent 根目录和网关地址占位值，按各自的实际启动环境配置鉴权。

每组各有 LUNO、LENS 和 FORGE 三条 Profile，示例均用该组的 Codex provider。LUNO、LENS 用 `gpt-6.2-sol`，FORGE 用 `deepseek-flash`。六条均配置 `full-access`、`high` 与 `service_tier: "default"`。部署时按父权限和目标模型能力核对这些值。显式传递 `service_tier` 可覆盖同 provider 派发时继承的父会话值。Profile 的 `options` 只放所选 provider 支持的选项。

## 家目录布局

agent 相关状态集中在一个 agent 根目录下，示例为 `/home/example/agent`：`paseo-home` 作 `PASEO_HOME`，`codex-home` 作 `CODEX_HOME`，`claude-home` 作 `CLAUDE_CONFIG_DIR`。Codex 与 Claude Code 只用官方环境变量指定家目录，不改 HOME。以下行为按 Paseo v0.17.4 源码核对，升级后按实际版本复核。

- daemon 进程环境同时设置这三个变量，值与 provider `env` 一致。Paseo 按 daemon 环境的 `CODEX_HOME`、`CLAUDE_CONFIG_DIR` 写入终端 agent 钩子（[agent-hook-installer.ts](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/terminal/agent-hooks/agent-hook-installer.ts)），缺省落到 HOME 下的 `.codex`、`.claude`。
- Claude provider 读取会话记录（时间线、回退、续聊）时按 provider `env` 的 `CLAUDE_CONFIG_DIR` 定位 `projects/`（[project-dir.ts](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/server/agent/providers/claude/project-dir.ts)）。只在启动脚本里设置该变量时，Claude Code 与 Paseo 会读写不同目录。
- Paseo 自带 skills 固定装到 HOME 下的 `.agents/skills`、`.claude/skills`、`.gemini/config/skills`，并只从 `.codex/skills` 清理旧副本（[paths.ts](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/server/orchestration-skills/internal/paths.ts)）。Codex 按官方用户 skills 位置读取 `.agents/skills`。Claude Code 改用 `CLAUDE_CONFIG_DIR` 后不再读 HOME 下的 `.claude/skills`，因此 HOME 下的 `.claude` 链接到 `claude-home`，使 Paseo 写入与 Claude Code 读取同一目录。
- 交互 shell 同样导出这三个变量，直接运行的 CLI 与 daemon 使用相同目录；未设置 `PASEO_HOME` 时，Paseo CLI 会在 HOME 下的 `.paseo` 写客户端标识。

迁移既有目录时先停用相关会话，按原样复制到新位置并核对，旧目录改名保留作回退，再切换环境并重启 daemon。

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

仓库不提供现成隔离前缀。隔离验收需另建同版本 npm 前缀，并配独立 `PASEO_HOME`、回环端口和临时 HOME，不能原地改写现役前缀。旧会话可能保存运行时注入的提示词，回退设置不会清除历史。

从热修版切换失败时，在同一维护窗口恢复原配置、插件与原程序入口，按原托管方式重启并回读健康状态及 Profile。只改过配置时，恢复原配置后按 `paseo reload` 的结果处理。

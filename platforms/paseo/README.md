# Paseo 官方原版双上游部署

本目录是 Paseo 0.17.1 官方原版的唯一 Paseo 配置示例与安装/迁移说明。它只用官方配置和官方 MCP 工具，不引入补丁、插件、脚本、探针或 wrapper。仓库不修改运行配置、服务、会话或登录态；实际合并和切换由有权限的维护者在目标实例完成。

## 固定来源

服务端口径按 Paseo v0.17.1 固定提交 `043f0995d4d7e91ab12f3eecef1afce055a81972` 核对，源码路径均取该提交：

- [agent-profile.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/protocol/src/agent-profile.ts)：Profile 字段是 `id`、`name`、`provider`、可选的 `model`、`modeId`、`thinkingOptionId`、`featureValues`/`options`、`notes`。
- [provider-config.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/protocol/src/provider-config.ts)：自定义 provider 用 `extends`、`label`、`command`、`env`、`enabled` 等字段；内置 ID 为 `claude`、`codex`、`copilot`、`opencode`、`pi`、`omp`。
- [provider-registry.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/provider-registry.ts)：派生 provider 先解析 `extends` 基座，再应用自身 `enabled`；禁用内置 `codex` 不妨碍 `cchp`/`gdr` 继承它。
- [codex/options.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/providers/codex/options.ts)：Codex options 是严格对象；`service_tier` 是受支持的 composer 控制项，`paseo_role`/`paseo_upstream` 等未知键会被拒绝。
- [paseo-tools.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/tools/paseo-tools.ts)：`list_profiles` 与 `create_agent` 的接口；同 provider 的子会话继承父 `providerOptions`，显式 `settings.features` 覆盖同名键。
- [agent-manager.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/agent-manager.ts)、[system-prompt.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/system-prompt.ts)：`daemon.appendSystemPrompt` trim 后作为额外 developer instructions 送到该 daemon 启动的所有会话，不改写 `AGENTS.md` 或私人 GLOBAL 副本。
- [provider-selection.ts](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/app/src/provider-selection/provider-selection.ts)、[provider-list.tsx](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/app/src/provider-settings/internal/provider-list.tsx)：模型选择器只列已启用且可用的 provider；管理页仍列出所有条目（含禁用项）和开关。
- [config_override.rs](https://github.com/openai/codex/blob/29eb79e9866b3262a777fdf8195c1b9e63684c91/codex-rs/utils/cli/src/config_override.rs)：Codex `-c key=value` 的解析与全局参数行为。

官方原版没有补丁版的宿主侧硬绑定；参数选路由 Profile 和 `create_agent` 约束，角色选择由首条消息和 `daemon.appendSystemPrompt` 软提示。错绑概率无法量化。

## 配置内容

`config.example.json` 只启用 `cchp`（CCHP）和 `gdr`（GDR）两个自定义 provider。二者都 `extends: "codex"`，用官方 Codex 命令参数 `-c model_provider="<上游>"` 固定各自上游，共用占位主家目录 `/home/example/codex-home`；同一上游的 LUNO/LENS/FORGE 共用该家目录。

六个 Profile：

| Profile ID | 显示名 | provider | model | modeId | thinkingOptionId | options |
| --- | --- | --- | --- | --- | --- | --- |
| `cchp-luno` | LUNO · CCHP | `cchp` | `gpt-6.2-sol` | `full-access` | `high` | `{"service_tier":"default"}` |
| `cchp-lens` | LENS · CCHP | `cchp` | `gpt-6.2-sol` | `full-access` | `high` | `{"service_tier":"default"}` |
| `cchp-forge` | FORGE · CCHP | `cchp` | `deepseek-flash` | `full-access` | `high` | `{"service_tier":"default"}` |
| `gdr-luno` | LUNO · GDR | `gdr` | `gpt-6.2-sol` | `full-access` | `high` | `{"service_tier":"ultrafast"}` |
| `gdr-lens` | LENS · GDR | `gdr` | `gpt-6.2-sol` | `full-access` | `high` | `{"service_tier":"ultrafast"}` |
| `gdr-forge` | FORGE · GDR | `gdr` | `gpt-6.2-sol` | `full-access` | `high` | `{"service_tier":"ultrafast"}` |

Profile 的 `options` 只放 Codex provider options；旧的 `paseo_role`、`paseo_upstream` 已移除。CCHP FORGE 显式写 `service_tier: "default"`：同 provider 派发会继承父 `providerOptions`，显式 `settings.features` 才能覆盖父会话的 Fast/Ultrafast，保持本 Profile 的 Normal 默认。

**Ultrafast 依据**：该档位由 Codex 模型目录声明，不是 Paseo 固定常量。官方原版模拟实测已证 `model_catalog_json` 可以添加该档位，GDR 的 3 条请求均发出 `ultrafast`；宿主目前两个上游各自已有 `model_catalog_url`，这是通用机制，现场具体 URL/路径不写入仓库。如果实际模型目录未声明 Ultrafast，`service_tier: "ultrafast"` 可能被降为 `default`，须按实际 catalog 和能力回读，不能只看配置。

## 内置项与显示范围

示例把 `claude`、`codex`、`copilot`、`opencode`、`pi`、`omp` 都设为 `enabled: false`。固定版本中 `omp` 默认禁用，其余五个默认启用；六个 ID 都是合法禁用项。这不是 allowlist，只是逐 provider 的 `enabled` 布尔值。

效果：新建 agent 的 provider picker 只显示已启用且可用的 `cchp`、`gdr`；管理页仍显示被禁用的内置项及其开关。`codex` 被禁用后仍是 `cchp`/`gdr` 的继承基座。

## 合并、安装与迁移

1. **独立实例**：用同一 Paseo 版本建立独立实例；不改现役前缀。宿主已有 `@getpaseo/cli`/`@getpaseo/server@0.17.1` 可用时，按既有 npm 安装路径核对版本即可。
2. **Codex 上游**：主家目录的 Codex `config.toml` 必须能解析 `model_providers.cchp` 和 `model_providers.gdr`，并已有各自的登录/鉴权安排；Paseo 配置只放非秘密 `CODEX_HOME` 和命令参数。
3. **合并配置**：按示例替换原有六个角色 Profile，并移除两项 provider 启动环境中的 `PASEO_CODEX_ROLE_*`。合并获准的 `daemon.mcp` 两项和 `agents.providers` 条目，保留监听、认证、其他插件及 MCP 设置。将示例 `daemon.appendSystemPrompt` 追加到现有值末尾。移除旧共享角色插件登记；如 systemd 覆盖仍指向热修前缀，切换到已核验的官方程序入口。
4. **重载**：合并后执行 `paseo reload`；若报告需要重启的路径，按报告重启。已有线程不自动改写历史指令，新会话才按新配置启动。
5. **Paseo 工具**：固定版本 `config.js` 的 `mcpInjectIntoAgents` 缺省为 false；示例明确加入 `daemon.mcp: {"enabled": true, "injectIntoAgents": true}`，供官方 `list_profiles`/`create_agent` 编排。只设这两项，不改其他 MCP 设置，运行时仍照既有审批。
6. **验收**：确认 provider picker、六个 Profile、`appendSystemPrompt` 生效范围，以及新建 agent 的 `provider`/`model` 回读。旧的 LENS/FORGE 记录绑定旧家目录，不能直接在共用主家目录续用；旧 LUNO 切换前也应在隔离实例验收。

## 角色协议（软角色）

`daemon.appendSystemPrompt` 规定：首条消息可用 `角色：LUNO`、`角色：LENS`、`角色：FORGE`；未写则按 LUNO。若使用角色行，角色行单独占第一行，不加前缀或其他文字，任务正文紧随其后并在同一条消息投递。桌面上直接选择角色 Profile 后也要写这一行；漏写按 LUNO。LUNO 负责协调、验收和交付。

LENS/FORGE 开始前必须完整读取部署的 `subagents/LENS.md` 或 `subagents/FORGE.md` 原文；示例路径必须替换为实际受管检出。角色只选择提示词，不授予新的文件、网络、凭据、审批或派发权限；受派后不得再委派；任何角色声明都不改变现行规则规定的准入。

同一上游的三个角色共用同一 `CODEX_HOME`、登录态、文件系统和权限边界。这不是独立身份、权限隔离或操作系统隔离；模型是否遵循角色提示与 provider/model/options 是否传错是两类问题。

## 派发契约

1. 从父活会话运行元数据取得实际 provider（不是标签或角色自述）。
2. 用官方 `list_profiles` 按父 provider 和精确 `profile.id` 选唯一 Profile；`provider` 必须精确等于父 provider。
3. 无唯一匹配、字段缺失、provider 不等或配置不可读时停止，不跨上游、不换模型、不按名称或 `notes` 猜选。
4. 用 `create_agent` 送出 `<provider>/<model>`、`settings.modeId`、`settings.thinkingOptionId`、`settings.features`（即 Profile `options`）和一次 `initialPrompt`；首行写角色行，任务正文紧随其后。正式任务不另发启动探针。
5. 创建后用 `get_agent_status` 回读实际 `provider` 和 `model`；标签、显示名和角色自述不能作为正式身份证据。

参数串线可靠精确 Profile ID、父 provider 相等检查、显式字段和回读缩小；模型是否按角色行执行只能靠角色原文和实际观察，不能给概率或冒充硬保证。正式独立身份没有可核证据时不采纳。

## 隔离与前态

仓库不提供现成隔离前缀。隔离验收需另建同版本 npm 前缀，并配独立 `PASEO_HOME`、回环端口和临时 HOME，不能原地改写现役前缀。旧会话可能保存运行时注入的提示词，回退设置不会清除历史。

从热修版切换失败时，在同一维护窗口恢复原配置、插件与原程序入口，按原托管方式重启并回读健康状态及 Profile。只改过配置时，恢复原配置后按 `paseo reload` 的结果处理。

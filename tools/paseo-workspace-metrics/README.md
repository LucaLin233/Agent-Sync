# 工作区用量

适用 Paseo 0.17.1。在插件已启用的 daemon 主机上安装源码，安装无需构建。GitHub 子目录安装要到改动合并进 `main` 后才可用。

本目录源码：

```sh
paseo plugin install "$PWD"
```

已合并的仓库版本：

```sh
paseo plugin install github:LucaLin233/Agent-Sync:tools/paseo-workspace-metrics --ref main
```

在工作区输入框输入 `/metrics`（无参数），或从命令中心搜索「打开工作区用量」。已有对话的输入框工具条会显示「缓存 98.2%」按钮：按当前工作区可见会话的最新有效缓存快照汇总，缺有效数据时显示「缓存 —」；点击仍打开该对话所属 workspace 的同一面板；按钮随当前 host 的会话目录增删，归档、后台或没有 workspace 的会话不注册，重连后按新快照重建并限制同一会话只保留一个。`/metrics` 在 Paseo 0.17.1 不与内建客户端命令（`exit`、`quit`、`q`、`clear`、`new`）冲突。

面板只查询当前 host、当前 workspace 在客户端目录中可见的会话，不含已归档会话和后台助手。打开详情可查看模型、状态、用量字段和实时观测。用量在进入面板、会话列表变化或手动刷新时读取。输入框按钮与面板共用同一套计算和一位小数格式，但按钮跟随会话目录订阅实时更新，面板读取打开或刷新时的快照，两者采样时点可能不同。

| 指标 | 口径 |
| --- | --- |
| 工作区累计缓存率 | Paseo 0.17.1 的公开接口缺少可统一分母的历史累计数据，显示「—」。Codex 只传出请求级 `tokenUsage.last`。Claude Code、Pi 和 OpenCode 适配器没有在可比较的用量字段中提供完整的缓存写入计数。 |
| 最近样本缓存率 | 每个可确认使用 Codex 的会话取当前 `lastUsage` 一次。汇总缓存读取后除以汇总输入，Codex 输入已包含缓存读取。缺字段或分母无效时排除该样本，明确上报零缓存命中会纳入计算。覆盖分母是当前面板可见会话数。 |
| 输入框缓存按钮 | 与「最近样本缓存率」同一范围、计算和格式：当前 workspace 每个可见 Codex 会话各取最新一笔有效输入，汇总后显示为「缓存 98.2%」；没有有效样本或读取不到时显示「缓存 —」。目录订阅快照与面板刷新快照的时点可能不同。 |
| Paseo 首段观测 | 打开会话详情后，仅用同一轮的 daemon 时间戳，取 `turn_started` 到首个 `assistant_message` 事件。首个事件可能是工具操作后的文本或一条合成消息。服务商 TTFT 和纯生成 TPS 未上报。 |
| Paseo 整轮耗时与整轮输出速率 | 耗时从轮开始到终态。内置 Claude Code 成功轮次另用该轮主循环输出 token 除以整轮耗时，包含工具与等待。计数缺失、轮次不完整或断线时段留空。 |

详情中的「上报」计数沿用 provider 的口径。插件只投影用量、会话元数据和实时事件的类型、轮次 ID 与时间戳，不读取消息文本，也没有服务端入口、外部请求或持久化采集。会话目录订阅只取公开 ID、`workspaceId`、归档与后台标志、`lastUsage` 用量数值，以及 `persistence.metadata.provider` 这一个非秘密 Codex 标记；provider ID 和该标记只用于即时判定计算口径，读取后只保留按会话算出的样本，用于注册按钮和汇总缓存率，不保留完整快照。插件停止或重载时统一撤销。

会话行保留原始 provider ID。别名会话的 `persistence.metadata.provider` 明确为 `codex` 时，以 Codex 口径计算最近样本缓存率。插件在持久会话元数据中只读取这个标志，随后保留计算后的样本计数。缺少该标志的别名会话仍可查看用量和 Paseo 事件耗时。[Paseo v0.17.1 provider 包装层](https://github.com/getpaseo/paseo/blob/v0.17.1/packages/server/src/server/agent/provider-registry.ts#L326)

## 候选自验

在 Node.js 22.18 及以上运行。

```sh
npm install --ignore-scripts
npm run typecheck
npm test
```

接口来源见 [Paseo 插件参考](https://paseo.sh/docs/plugins/reference.md)、[SDK 事件](https://paseo.sh/docs/sdk/events.md)、[v0.17.1 公共用量与事件结构](https://github.com/getpaseo/paseo/blob/v0.17.1/packages/protocol/src/messages.ts)、[Codex 适配器](https://github.com/getpaseo/paseo/blob/v0.17.1/packages/server/src/server/agent/providers/codex-app-server-agent.ts)、[Codex 输入计数定义](https://github.com/openai/codex/blob/cf3ff1530d821ec2d26452da4971d8e3e7d18d25/codex-rs/protocol/src/protocol.rs)及 [Claude Agent SDK 的流式用量口径](https://platform.claude.com/docs/en/agent-sdk/cost-tracking#track-costs-in-streaming-input-mode)。

# 工作区用量

适用 Paseo 0.17.1。在插件已启用的 daemon 主机上安装源码，安装无需构建。

本目录源码：

```sh
paseo plugin install "$PWD"
```

已合并的仓库版本：

```sh
paseo plugin install github:LucaLin233/Agent-Sync:tools/paseo-workspace-metrics --ref main
```

在工作区输入框输入 `/metrics`（无参数），或从命令中心搜索「打开工作区用量」。已有对话的输入框工具条会显示「缓存 98.2%」按钮：优先显示当前工作区 Codex 累计缓存率；尚未取到累计结果时显示「缓存 …」，累计接口不可用时显示「累计 —」，有结果但没有有效样本时显示「缓存 —」。点击仍打开该对话所属 workspace 的同一面板；按钮随当前 host 的会话目录增删，归档、后台或没有 workspace 的会话不注册，重连后按新快照重建并限制同一会话只保留一个。`/metrics` 在 Paseo 0.17.1 不与内建客户端命令（`exit`、`quit`、`q`、`clear`、`new`）冲突。

面板同时显示累计缓存率、累计覆盖、累计缓存读取/总输入，以及现有的最近样本缓存率和最近覆盖，便于对照。累计由 daemon 侧 RPC 读取 Codex rollouts；最近样本仍由 Paseo 的 `lastUsage` 读取。输入框按钮与面板共用累计口径和一位小数格式，但按钮由会话目录订阅触发更新，面板在打开或刷新时读取，两者采样时点可能不同。

| 指标 | 口径 |
| --- | --- |
| 累计缓存率 | 服务端按当前 workspace 的可见 Codex 会话校验 `workspaceId`、归档状态、provider 或 `persistence.metadata.provider = "codex"` 标记，以及 UUID 形式的 `nativeHandle`。每个唯一 native 会话只取最新一笔有效 `payload.info.total_token_usage`，汇总 `cached_input_tokens / input_tokens`。closed 会话计入；归档、后台、跨 workspace 或无法确认的会话排除。缺失、无效或不完整快照不计为 0。 |
| 累计覆盖 | `covered / eligible`：有有效累计快照的唯一 native 会话数 / 当前 workspace 可确认的 Codex 唯一 native 会话数。另有缺失和排除会话数用于说明失败原因。 |
| 最近样本缓存率 | 每个可确认使用 Codex 的会话取当前 `lastUsage` 一次。汇总缓存读取后除以汇总输入，Codex 输入已包含缓存读取。缺字段或分母无效时排除该样本，明确上报零缓存命中会纳入计算。覆盖分母是当前面板可见会话数。 |
| 输入框缓存按钮 | 有累计结果时与「累计缓存率」同口径、同格式；加载中「缓存 …」，接口不可用「累计 —」，无有效样本「缓存 —」。不会把缺失当 0，也不混用最近样本口径。 |
| Paseo 首段观测 | 打开会话详情后，仅用同一轮的 daemon 时间戳，取 `turn_started` 到首个 `assistant_message` 事件。首个事件可能是工具操作后的文本或一条合成消息。服务商 TTFT 和纯生成 TPS 未上报。 |
| Paseo 整轮耗时与整轮输出速率 | 耗时从轮开始到终态。内置 Claude Code 成功轮次另用该轮主循环输出 token 除以整轮耗时，包含工具与等待。计数缺失、轮次不完整或断线时段留空。 |

## 累计数据来源与边界

Codex 数据根依次尝试：daemon 进程的 `CODEX_HOME`、插件 host 设置 `codexHome`，最后才是 `~/.codex`。实际 Codex home 和 workspace 允许列表由 Paseo 的 host 设置提供，不写入发布源码。只会进入数据根下固定的 `sessions/` 和 `archived_sessions/`，不跟随软链，不允许解析结果逃出数据根。

服务端只服务 host 设置 `workspaceIds` 允许的 workspace；未配置或列表为空时累计功能关闭，前端也不发累计查询。服务端只接受 workspace ID 和会话 ID，不接受客户端路径；每个会话都用 Paseo 的 exact agent ref 刷新后校验，拒绝跨 workspace、归档、非 Codex 或 `nativeHandle` 不是 UUID 的成员。rollout 文件名必须与该 UUID 精确匹配。每个 UUID 的日期目录或归档精确匹配结果最多缓存 30 秒；文件按 `dev/ino/size/mtime/ctime` 校验身份并只从上次偏移继续读取，不建立全局会话索引。单文件上限 256 MiB，单目录条目上限 5,000。

JSONL 每行先看前 240 字节是否同时含 `event_msg` 与 `token_count` 标记，命中后才 `JSON.parse` 并复核 `type` 和 `payload.type`。只读取 `payload.info.total_token_usage.input_tokens` 与 `cached_input_tokens`，要求非负安全整数且缓存不超过输入；同一会话较新的累计快照覆盖旧值，不累加。RPC 只返回计数、覆盖和错误说明，不返回会话路径、native 会话 ID 或消息内容。

详情中的「上报」计数沿用 provider 的口径。客户端会话目录订阅只取公开 ID、`workspaceId`、归档与后台标志、`lastUsage` 用量数值，以及 `persistence.metadata.provider` 这一个非秘密 Codex 标记；读取后只保留按会话算出的样本，不保留完整快照。累计接口在 daemon 侧读取授权的 Codex rollout 计数，不读取或传出正文。插件停止或重载时撤销按钮、定时器和面板注册。

会话行保留原始 provider ID。别名会话的 `persistence.metadata.provider` 明确为 `codex` 时，以 Codex 口径计算缓存率。插件在持久会话元数据中只读取这个标志。缺少该标志的别名会话仍可查看最近用量和 Paseo 事件耗时。[Paseo v0.17.1 provider 包装层](https://github.com/getpaseo/paseo/blob/v0.17.1/packages/server/src/server/agent/provider-registry.ts#L326)

## 候选自验

在 Node.js 22.18 及以上运行。

```sh
npm install --ignore-scripts
npm run typecheck
npm test
```

接口来源见 [Paseo 插件参考](https://paseo.sh/docs/plugins/reference.md)、[SDK 事件](https://paseo.sh/docs/sdk/events.md)、[v0.17.1 公共用量与事件结构](https://github.com/getpaseo/paseo/blob/v0.17.1/packages/protocol/src/messages.ts)、[Codex 适配器](https://github.com/getpaseo/paseo/blob/v0.17.1/packages/server/src/server/agent/providers/codex-app-server-agent.ts)、[Codex 输入计数定义](https://github.com/openai/codex/blob/cf3ff1530d821ec2d26452da4971d8e3e7d18d25/codex-rs/protocol/src/protocol.rs)及 [Claude Agent SDK 的流式用量口径](https://platform.claude.com/docs/en/agent-sdk/cost-tracking#track-costs-in-streaming-input-mode)。

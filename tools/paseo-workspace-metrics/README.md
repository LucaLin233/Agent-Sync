# 工作区用量

适用 Paseo 0.16.0 及以上。在插件已启用的 daemon 主机上安装源码，安装无需构建。

首次安装，本地开发路径：

```sh
PLUGIN_ID=${PLUGIN_ID:?先按本次部署选定运行 ID}
paseo plugin install "$PWD" --id "$PLUGIN_ID"
```

首次安装，正式部署（只从已合并并通过验证的提交）：

```sh
PLUGIN_ID=${PLUGIN_ID:?先按本次部署选定运行 ID}
REF=${REF:?填已核对的已合并提交}
paseo plugin install github:LucaLin233/Agent-Sync:tools/paseo-workspace-metrics --id "$PLUGIN_ID" --ref "$REF"
```

已有 Git 安装：先用可信本地进程通过目标的结构化入口，在输出前只投影运行 ID、允许的来源字段、已安装修订和运行状态，核对原仓库和子目录；一致后更新到已核 ref，不要重走安装：

```sh
PLUGIN_ID=${PLUGIN_ID:?先确认现有安装的运行 ID}
REF=${REF:?填已核对的已合并提交}
paseo plugin update "$PLUGIN_ID" --ref "$REF"
```

已有本地开发安装：源码更新后用运行 ID 重载：

```sh
PLUGIN_ID=${PLUGIN_ID:?先确认现有安装的运行 ID}
paseo plugin reload "$PLUGIN_ID"
```

所有安装、更新或重载写入前，确认目标 daemon、运行 ID 和本次写授权；已有 Git 安装的 `update --ref` 会直接按该 ref 更新，不重走 install。

运行 ID 未知时用 `paseo --quiet plugin ls` 取 ID-only 输出；目标不支持该全局选项时说明缺口，不回退到完整记录。已知 ID 只核目标项：由可信本地进程调用目标的结构化入口，在工具输出前只投影运行 ID、允许的来源字段、已安装修订和运行状态，不输出目录或错误文本；失败只报失败，不转储 stderr，也不为补齐而读取完整记录。现有安装继续沿用读到的运行 ID，新部署按本次部署选定。安装来源不匹配时，先在授权范围内确定迁移方案，不直接按同一 ID 覆盖。

安装、更新或重载后按同一投影方式回读：由可信本地进程在工具输出前只投影运行 ID、允许的来源字段、已安装修订和运行状态；Git 安装或更新核对已安装修订等于选定提交，reload 核回执，设置另用目标适用的设置入口只取必要字段。没有可安全投影的入口时说明缺口，不以完整记录代替。该回读不联系远端，一致也不证明远端已有更新。

安装后在「设置 → 插件 → 工作区用量」的齿轮打开设置：默认只显示最近样本，累计统计关闭；打开「累计统计」后默认按本机全部 workspace 各自汇总，可在「高级设置」里改为只查询指定 workspace ID，并可选填 Codex home（留空自动发现）。保存使用 host 设置的 revision，其他客户端和已打开的面板、输入框按钮会随设置订阅刷新并清除旧累计缓存，不需要重载插件。

在工作区输入框输入 `/metrics`（无参数），或从命令中心搜索「打开工作区用量」。已有对话的输入框工具条会显示缓存按钮：累计开启时优先显示当前工作区 Codex 累计缓存率（「缓存 98.2%」），累计关闭或不可用时显示最近样本（「最近 98.2%」）；加载中为「缓存 …」，无有效样本为「缓存 —」或「最近 —」。点击仍打开该对话所属 workspace 的同一面板；按钮随当前 host 的会话目录增删，归档、后台或没有 workspace 的会话不注册，重连后按新快照重建并限制同一会话只保留一个。`/metrics` 在 Paseo 0.17.1 不与内建客户端命令（`exit`、`quit`、`q`、`clear`、`new`）冲突。

面板同时显示累计缓存率、累计覆盖、累计缓存读取/总输入，以及现有的最近样本缓存率和最近覆盖，便于对照。累计由 daemon 侧 RPC 读取 Codex rollouts；最近样本仍由 Paseo 的 `lastUsage` 读取。输入框按钮与面板共用累计口径和一位小数格式，但按钮由会话目录订阅触发更新，面板在打开或刷新时读取，两者采样时点可能不同。

| 指标 | 口径 |
| --- | --- |
| 累计缓存率 | 服务端按当前 workspace 的可见 Codex 会话校验 `workspaceId`、归档状态、provider 或 `persistence.metadata.provider = "codex"` 标记，以及 UUID 形式的 `nativeHandle`。每个唯一 native 会话只取最新一笔有效 `payload.info.total_token_usage`，汇总 `cached_input_tokens / input_tokens`。closed 会话计入；归档、后台、跨 workspace 或无法确认的会话排除。缺失、无效或不完整快照不计为 0。 |
| 累计覆盖 | `covered / eligible`：有有效累计快照的唯一 native 会话数 / 当前 workspace 可确认的 Codex 唯一 native 会话数。另有缺失和排除会话数用于说明失败原因。 |
| 最近样本缓存率 | 每个可确认使用 Codex 的会话取当前 `lastUsage` 一次。汇总缓存读取后除以汇总输入，Codex 输入已包含缓存读取。缺字段或分母无效时排除该样本，明确上报零缓存命中会纳入计算。覆盖分母是当前面板可见会话数。 |
| 输入框缓存按钮 | 累计开启且可用时与「累计缓存率」同口径、同格式；累计关闭或不可用时显示「最近」样本口径。加载中「缓存 …」，无有效样本「缓存 —」或「最近 —」。不会把缺失当 0，也不会把两种口径混成一个数。 |
| Paseo 首个可见文本 | 打开会话详情后，仅用同一轮的 daemon 时间戳，取 `turn_started` 到首个含非空白助手文本的 `assistant_message` 事件；空或纯空白消息、工具和推理事件不算。它可能出现在工具操作之后，也不是服务商 TTFT。 |
| Paseo 整轮耗时与本轮输出速率 | 耗时从轮开始到终态。内置 Claude Code 成功轮次另用该轮主循环输出 token 除以整轮耗时，包含工具与等待。计数缺失、轮次不完整或断线时段留空。 |
| 最近 Codex 完成轮 | 仅累计统计开启且能确认 Codex（含 CCHP/GDR 等别名标记）时显示。只用该会话同一 rollout 内同一 native `turn_id` 的 `task_started`/`task_complete` 边界，以及两边界之间最后一笔累计 `total_token_usage.output_tokens` 相对 `task_started` 时累计值的差；耗时同样取这两个原生边界。它与上方 Paseo 实时观测独立展示，不按客户端时间窗切分。起点基线只取上一完成轮可信的最终累计输出值；该轮缺少最终计数、边界中断或中途被新的开始取代时，下一轮基线作废。轮内每个计数都要时间前进、不低于起点基线且不倒退；任一回退或时间倒退都使该轮速率留空。`task_complete` 带非空 `error`、`turn_aborted`、`thread_rolled_back` 时不出该轮数据并清空基线。完成轮有原生边界时，耗时可独立显示；`time_to_first_token_ms` 可独立显示；两者都不依赖输出计数。 |
| Codex 首个模型 Token | 同一完成轮 `task_complete.time_to_first_token_ms` 有非负整数时显示，即使该轮缺少有效输出基线也照常显示。它是 Codex 自报的模型首 token 时间，与 Paseo 首个可见文本口径不同，也不冒充服务商 TTFT。 |

## 累计数据来源与边界

Codex 数据根：填写插件 host 设置 `codexHome` 时作为显式覆盖优先使用，必须解析到 daemon 用户家目录内；不存在、不是绝对路径或越界时返回明确错误，不会静默回退到其他根。留空时先用 daemon 进程的 `CODEX_HOME`（作为管理员配置的外部根，规范化并解析软链后必须仍位于其配置根所在目录内），最后才是 `~/.codex`。workspace 允许列表由 Paseo 的 host 设置提供，不写入发布源码。只会进入数据根下固定的 `sessions/` 和 `archived_sessions/`，不跟随软链，不允许解析结果逃出数据根。

累计统计默认关闭，关闭时服务端不访问任何 cumulative 数据，即使设置里还留有旧 allowlist。显式打开后默认覆盖本机全部 workspace；高级设置可写入 `allWorkspaces: false` 和 `workspaceIds` 限制名单，空名单会报错而不会放开。旧版只含 `allWorkspaces: true` 或非空 `workspaceIds` 的设置继续按原含义启用；新设置用可选 `cumulativeEnabled` 统一表达开关。服务端仍逐一校验每个会话的 workspace、归档、后台、Codex 标记与 UUID，范围读取失败时前端不会声称该 workspace 不在白名单。两个 RPC 都用同一份设置快照确定范围，关闭、名单外或会话校验不通过时不会解析或探测任何数据目录；通过后才解析同一快照配置的根，并在 `agent.refresh()` 之后、读文件前和返回前核对设置 revision。配置已变就丢弃结果，不会在旧授权下读新目录。聚合缓存键包含设置 revision 与解析后的可用根，换根不会复用旧结果。手动刷新绕过短聚合缓存与路径负缓存；每次观测到轮次后最多三次、每次 1.2 秒由查询自身重读，覆盖终态先于落盘的情况，卸载或观测变化时撤销。服务端只接受 workspace ID 和会话 ID，不接受客户端路径；每个会话都用 Paseo 的 exact agent ref 刷新后校验，拒绝跨 workspace、归档、后台、非 Codex 或 `nativeHandle` 不是 UUID 的成员。rollout 文件名必须与该 UUID 精确匹配。每个 UUID 的日期目录或归档精确匹配结果最多缓存 30 秒；文件按 `dev/ino/size/mtime/ctime` 校验身份并只从上次偏移继续读取，不建立全局会话索引。单文件上限 256 MiB，单目录条目上限 5,000。

JSONL 每行先看前 240 字节是否含 `event_msg` 标记，再看是否含 `token_count` 或轮次事件，命中后才解析并复核 `type` 和 `payload.type`。累计只读取 `payload.info.total_token_usage` 的 `input_tokens`、`cached_input_tokens` 与 `output_tokens`，要求非负安全整数且缓存不超过输入；同一会话较新的累计快照覆盖旧值，不累加。轮次边界只投影 `turn_id`、`error` 是否存在、`time_to_first_token_ms` 和行时间戳；读取使用结构级白名单扫描，先按顶层真实事件 `type` 识别对象，再跳过所有非白名单字符串和嵌套正文，`task_complete` 的助手正文与嵌套错误内容不反序列化、不保留，也不会进入客户端状态。坏缓存快照保留上一笔有效输入/缓存样本，不影响轮次判断；有首 token 但边界耗时为 0 时仍显示首 token。时间戳或输出计数缺失只影响轮次级指标，累计输入/缓存仍按原口径解析，读取层分别返回缓存样本和完成轮。RPC 只返回计数、覆盖和错误说明，不返回会话路径、native 会话 ID、turn ID 或消息内容。

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

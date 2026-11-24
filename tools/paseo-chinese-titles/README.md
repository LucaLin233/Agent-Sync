# Paseo 中文标题（Agent-Sync 工具）

本目录是 [Agent-Sync](https://github.com/LucaLin233/Agent-Sync) 的 Paseo 插件工具，源码与主插件目录一致，仅此子目录纳入仓库。

## 从 Agent-Sync 安装

```sh
REF=${REF:?填已核对的已合并提交}
paseo --home "$PASEO_HOME" plugin install \
  github:LucaLin233/Agent-Sync:tools/paseo-chinese-titles \
  --id paseo-chinese-titles --ref "$REF"
```

合并前请使用本分支的本地目录安装；不要把未合并的候选路径冒充 `main` 已发布内容。开发依赖固定 `@getpaseo/* 0.17.3` 是类型检查目标；manifest 下限保持 `>=0.16.0`。新行为按 0.17.3 类型检查与单测验证，未在 0.16.0 黑盒复验。

## 存储位置与旧状态迁移

插件状态不再把 `PASEO_HOME` 当文件系统路径，而是：

- 固定 base：`$HOME/.paseo/plugin-data/paseo-chinese-titles/daemons/`；
- 每个 daemon 一个 32 位十六进制 SHA-256 namespace（输入是 `PASEO_HOME`），因此不同 daemon 状态隔离；
- `helper/` 与 `bootstrap/` 也位于该 namespace 下。

旧版曾使用 `$PASEO_HOME/plugin-data/paseo-chinese-titles/state.json`。升级时由部署者一次性迁移，插件代码不读取旧任意路径：

```sh
NS=$(printf '%s' "$PASEO_HOME" | sha256sum | cut -c1-32)
OLD="$PASEO_HOME/plugin-data/paseo-chinese-titles/state.json"
NEW="$HOME/.paseo/plugin-data/paseo-chinese-titles/daemons/$NS/state.json"
mkdir -p "$(dirname "$NEW")"
# 在插件已 disable/停止写入的窗口内，单写入者串行复制
cp "$OLD" "$NEW.tmp" && chmod 600 "$NEW.tmp" && mv "$NEW.tmp" "$NEW"
```

保留旧文件作为回滚副本；不要在新旧版本同时运行时复制，避免重复命名。迁移后安装/更新从已合并提交构建的插件，再按实际需要启用。

## 设置屏

Provider、Model、Thinking 档位使用官方原生 `SettingsSelect`。目录来自 daemon 当前 provider catalog：只列状态为 ready 的 Codex 内置或 `extends: "codex"` 别名，显示 provider 的 label、保存真实 ID；选择 provider 后只列该 provider 的可选模型，选择模型后只列其 thinking options。保留「自动选择 provider / 模型默认 / 默认思考档」，切换上层时清空失效的模型和思考档。目录不可用或已保存值过期时显示不可用状态，不做手输。

## 兼容版本

- 目标与类型检查：Paseo **0.17.3**（`@getpaseo/* 0.17.3`）。
- manifest 下限：`>=0.16.0`。官方 v0.16.0 源码已有 `workspace.create.before`（`packages/plugin/src/server/lifecycle.ts:136,199`）、`addWorkspacePanel`（`packages/plugin/src/client/contracts.ts:236`），且 `session.ts:7350,7373-7405` 已让 metadata/firstAgentContext 经过该 hook，`workspace-auto-name.ts:179-191` 的覆盖条件与 0.17.3 相同；未发现真实 0.16.0 API 不兼容，故保留原下限。新行为在 0.17.3 类型检查与单测中验证；时间线断点语义另按本机 0.17.4 的 `agent-timeline-store.js` 实际实现核对（`staleCursor`/`gap` 会重置为尾页），并用 0.17.4 daemon 自带编译器对候选做了打包检查。0.16.0 黑盒结果属于加入手动面板与种子钩子之前的构建，本版本未复验。

---

## 主插件说明

面向 **Paseo 0.17.3** 的本地插件。它只写显示覆盖：

- 新登记项目：生成一次简体中文侧栏名称；
- 新工作区：收到首个真实任务时生成一次中文标题；
- 新普通会话（可选）：收到首个真实任务时生成一次中文标题。

不写目录、仓库或 Git 分支。项目标题写入 Paseo 的 `customName`，工作区/会话标题写入 `title`；桌面和手机连接同一个 daemon 时看到同一份持久结果。

## 安装

在目标 daemon 所在主机执行，`--home` 必须是同一个 `PASEO_HOME`：

```sh
PLUGIN_ID=paseo-chinese-titles
paseo --home "$PASEO_HOME" plugin install /absolute/path/to/paseo-chinese-titles --id "$PLUGIN_ID"
paseo --home "$PASEO_HOME" plugin ls --json
```

安装后插件应显示 `status: "running"`。插件没有构建步骤；`package.json` 的 `devDependencies` 只用于源码类型检查。分发包可只含本仓库的源码文件，不依赖本地 `node_modules`。

修改源码后：

```sh
paseo --home "$PASEO_HOME" plugin reload "$PLUGIN_ID"
```

卸载：

```sh
paseo --home "$PASEO_HOME" plugin remove "$PLUGIN_ID"
```

## 设置

设置入口：Paseo 设置 → 插件 → Paseo 中文标题。也可直接编辑 host 设置文件：

`$PASEO_HOME/plugin-settings/paseo-chinese-titles/chinese-titles.json`

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `autoNameProjects` | `true` | 新项目生成一次中文名称 |
| `autoNameWorkspaces` | `true` | 新工作区首个真实任务生成中文标题 |
| `autoNameSessions` | `false` | 新普通会话首个真实任务生成中文标题；默认关闭，保留 Better Paseo 管会话标题 |
| `provider` | 空 | 留空自动选择 daemon 已就绪的 Codex provider 或其别名（`extends: "codex"`）；只允许 Codex 系列，不会选 Pi |
| `model` | 空 | 留空使用所选 provider 默认模型 |
| `thinkingOptionId` | 空 | 留空使用模型默认思考档 |
| `projectMaxChars` | `20` | 项目名称上限 |
| `titleMaxChars` | `28` | 工作区/会话标题上限 |
| `paseoBin` | `paseo` | 官方 CLI 可执行文件；daemon 的 PATH 找不到时填绝对路径 |

插件不读取 provider 密钥、Codex 登录态或 daemon 凭据文件。模型调用复用 daemon 已配置的 provider 入口；项目/会话更名调用官方可信 CLI，CLI 自己连接同一 daemon。

## Better Paseo 共存

Better Paseo 1.6.4 的 **「自动优化新任务标题」**（设置里的 `afterFirstReply`）默认关闭。使用本插件的会话命名时：

1. 先在 Better Paseo 设置中关闭 **Tasks →「自动优化新任务标题」**，即 `title-generation.json` 的 `values.afterFirstReply: false`；此时 Better Paseo 不再在首条消息开始时自动优化 agent 标题；
2. 确认 Better Paseo 的 `title-generation.json` 仍是 `afterFirstReply: false` 后，再把本插件的 `autoNameSessions` 打开；
3. Better Paseo 的手动「从对话生成标题」仍可继续使用；它只在用户主动操作时运行。Better Paseo 的 agent 自动标题还有一个边界：只有在 `workspace.name === previousTitle` 时才顺带改写工作区标题；本插件不修改 Better Paseo 配置，也不依赖这个条件。

本插件的辅助会话同时带 `paseo-chinese-titles.helper=1` 和 `better-paseo.purpose=title-generation` 标签，Better Paseo 会跳过它；本插件也跳过带该标签、`background` 或 `paseo.parent-agent-id` 的会话。

## 行为与边界

- **项目**：SDK 没有项目更名方法，插件用官方 CLI `project rename` 写入 `customName`。写入前重新读取 `projectCustomName`；已有手动值直接跳过。无 app 连接时，插件用官方 CLI 定时 `project ls` 只发现新 `projectId`，再在插件专属中性目录下创建一个 **background directory workspace**（`workspace create --isolation local --path .../bootstrap --project <id> --title 中文标题引导 --background`）。这个 workspace 的 `workspace.create.after` 提供同 daemon 的 `context.paseo`，插件随后走正常 SDK 项目流程并归档它。每进程最多一次成功引导；只归档精确路径、`background`、同 project 且本进程发起的引导 workspace。
- **工作区**：通过 hook 自带的 `context.paseo` 生成。`workspace.create.before` 先写入一个中文兜底种子标题（仅当请求没有 `title`；New Workspace 原始请求就是这样传 `firstAgentContext`），工作区收到首个真实任务后再用模型或兜底替换；种子值记录在 workspace metadata，只有标题仍等于该值时才允许自动替换。写后重新读取并核对 `title`。**没有跨进程 CAS**：如果手动改名恰好落在最终 `refresh` 与写入之间，仍可能被覆盖；同一进程内自动与手动共用 workspace claim，最终写前看到已变化才跳过。
- **会话**（`autoNameSessions`，默认关闭）：等首轮实质回答完成后再命名，素材是**首问与该完成轮末的实质回答**（同一轮可能有多段助手正文，按顺序全部取用），不再只截取首句。时间线出现新的用户问题即视为首轮结束；只有可见助手回答达到至少 4 个非空白字符才算实质回答，失败、取消、仅工具调用或空回答都不消耗命名机会。工具密集的首轮若正向扫描先到页数/条目上限，会再对最新一轮做一次有界尾页读取取回回答，不会拿别的轮次作答。模型无可用标题时**保留临时标题**并记录具体可核失败原因（`model_failed`、`invalid_title`、`timeout`、`provider_unavailable`），下一次**不同**的完成轮次最多补试一次；同一轮重复事件、进程重启、并发 hook 都不会重复消耗（尝试次数与 `lastTurnId` 在调用模型前先落盘）。两次用尽或成功后停止；provider 暂时不可用也保留这一次补试机会，写入失败或回读不一致同样只消耗当前机会。整个命名步骤（扫描 + 模型 + 一次 CLI 改名 + 回读）受 20 秒内部预算约束，短于 daemon 30 秒 hook 超时；写前回读会核对会话仍存在、仍在原工作区且未归档，剩余预算不足以完成改名和回读时记 `timeout` 并完全不调用 CLI。历史 `done + model_failed`（或 `provider_unavailable`）的错标只有在「标题正是插件所写且用户未手动改名」时保留一轮修复机会，且这次修复同样只接受已完成轮，失败或取消轮留下的半截正文不会消耗它，修复后置 `repairUsed`；`done` 且无失败码的记录当作真实标题，不修。写入前回读，首句截断、以「的/与/和」等虚词收尾的断句或任何确定性兜底都不会被标成功（自动命名把它当作不可用结果，按既有补试规则保留临时标题）；已有明确标题、手动改名和 `legacy`/后台/子会话/辅助会话不受影响。
- **首任务判断**：正向读取首条真实用户消息时，一旦遇到 0.17.4 的 `reset`/`staleCursor`/`gap` 尾页即放弃本次判断，避免把会话中段误当成首任务。不看创建顺序。workspace claim 内读取所有非后台、非子会话的首条真实用户消息，按 timeline entry 时间戳选最早者，同一毫秒用 agent ID 固定 tie break；由该获胜会话决定工作区标题。最早创建但一直没收到任务的空会话不会阻塞后创建会话先收到任务；两个会话都已有任务时也不会都返回 false。并发多 agent 由进程内 workspace claim 保证工作区只命名一次。
- **模型输出校验**：去掉 JSON/引号/Markdown/标签后只取一行；至少两个汉字，且每个拉丁词必须是产品/协议/大写缩写/含数字或文件名的标识符。普通英文、单汉字、全英文、仅首字母大写的普通词、带末尾句号或普通连字符伪装的英文都视为无效（例如 `修复 login bug`、`修复 LOGIN BUG.`、`修复 login-bug`）。中英混合首句会先规范化，不会因为句中出现一个汉字就直接通过。
- **中文兜底**：先识别常见任务动词和名词，保留有意义的专名/技术标识，再用自然中文组合（如 `修复登录问题`、`优化 Codex 会话`、`新增 OAuth 回调`）；识别不出时用简短通用中文（如 `处理任务`、`处理工作区`），不拼接整段普通英文。
- **保留已有和手动名称**：首次启用时用官方 CLI 列表建立基线，已有对象不改。自动路径只处理当前 `title` 为空、仍等于 Paseo provisional 首 prompt 文本、或仍等于本插件创建时写入的种子标题；显式标题、手动改名和其他英文标题都不当成自动标题。手动按钮不受此限制，但写前回读，生成期间被手动改名则跳过。
- **辅助会话**：中性目录、`background`、固定标题、只读 sandbox、`approval_policy: "never"`、禁用 web search、无预批准工具。辅助会话不进入本插件或 Better Paseo 的自动命名。
- **Paseo 内置 workspace-auto-name**：0.17.3 daemon 会在创建带首 prompt 的 workspace 时异步生成原生摘要，只在当前标题为空或仍等于首 prompt 文本时写入；它还可能重命名 branch-off 的占位分支，且没有受支持的关闭开关。本插件在 `workspace.create.before` 写入一个不同于首 prompt 的中文种子标题，因此原生摘要不会覆盖它；插件随后用它自己的模型/兜底替换。插件只写 `title`，不写 branch。若严格禁止分支变化，创建 worktree 时显式给 `--new-branch`，并接受内置分支重命名仍可能发生。安装前已存在的旧工作区没有种子；隐式创建工作区（例如打开普通目录时由 Paseo 内部 upsert，而不经过 `workspace.create.before`）也不会经过种子钩子。这两类工作区若已有英文标题，使用下面的手动按钮修复；按钮也可处理原生自动命名已跳过或已写英文的现场。
- **侧栏显示**：Paseo 的侧栏可按「标题」或「分支」显示。切到「分支」时看到的是 Git 分支名，不是本插件写入的标题；切到「标题」才能看到同一 daemon 持久的中文标题。

### 手动重新生成

工作区面板「中文标题」里先选会话、再选更新范围，最后点生成按钮。

- **先选会话，再生成**。面板列出这个工作区的普通会话（排除后台、子会话、内部会话和本插件自己的命名辅助会话）。只有一个可选会话时自动选中；有多个时默认不选，必须明确点选。插件不会按「最近运行」或工作区里第一个会话擅自替你选；未选中的会话既不参与摘要也不被改名。
- **三种更新范围**：「工作区和所选会话」（面板默认）、「仅工作区」、「仅所选会话」。一次请求只生成一个标题，同时写入选定目标，两处使用同一个标题和同一个字数上限（长会话会先在内部分段提炼，再合成这一个标题）。「仅会话」不读写工作区标题，也不改工作区的自动命名状态。「仅工作区」不改所选会话标题。
- **旧请求兼容**：请求未携带 `scope` 时按原行为只更新工作区；面板会显式发送 `both`。
- 生成时**从头按时间连续分页**读取用户与助手可见文本，不再两端采样：翻到尾部、页数上限（40 页 × 100 条）、可见条目上限（3000）或文本上限（30000 字）即停。推理、工具调用、通知、待办、压缩记录、插件行和附件都不进入摘要；可识别的凭据（私钥、GitHub/OpenAI 类令牌、`*_TOKEN=` 赋值、`password=` 等）会先移除。**这段文本会发送到设置里指定的标题模型**；界面与本节都提示这一点。
- **重置与断层**：0.17.4 的 timeline store 在游标过期或序列断层时会把该页改成尾页并带 `reset`/`staleCursor`/`gap`，这种页的 `hasNewer: false` 不代表读完了，也不能和它前面的页拼成连续对话。插件遇到这种页即停止并标「部分覆盖」，只保留中断前已连续读到的内容，不误报全量；如果首页就是这种重置尾页，则只用这一页并同样标部分覆盖。命名用的首问读取和会话命名素材遇到断点直接放弃本次判断，避免把会话中段当成开头。
- **短会话单次生成，长会话分段提炼**：整段能放进一次模型输入（约 1.5 万字）时直接生成标题；更长则按连续轮次切成最多 2 段，**每段依次提炼用户目标、关键结论和实际操作**，再用各段摘要合成最终标题。分段与合成在同一个辅助会话里顺序完成，不额外新建工作区。任何一段失败都不返回标题，避免用子集冒充全会话；`segments.used` 如实记录实际完成的分段数。
- **覆盖语义**：成功结果带 `coverage` 仅在**部分覆盖**时出现，`reason` 取 `page_cap`、`entry_cap`、`char_cap`、`deadline`、`cursor_missing`、`read_error`、`segment_cap`、`reset`、`gap` 之一，`turns` 是实际读取轮数；面板会显示对应中文原因和「标题只概括了已读取的 N 轮，可重试」，不假装完整。
- **概括口径**：提示词要求按整段对话找贯穿多轮的目标和实际工作；最后单独收尾的议题不会仅因靠后就自动变标题，但对话里有证据的真实主题变化会保留。提示词不写死任何具体领域词。
- **读失败与空会话分开**：首个 timeline 页读取失败（含传输异常）返回 `conversation_unavailable`，不会误报成 `empty_conversation`；首页成功而后续页失败时用已读到的连续内容继续并标 `partial`，不额外重试。
- **只接受真实模型结果**。手动路径不会用确定性兜底冒充成功：模型不可用、超时、没有可概括内容，或答案不是合格简体中文标题时，保留原标题并给出可重试的具体原因（`provider_unavailable`、`model_failed`、`invalid_title`、`rewrite_failed`、`empty_conversation` 等）。标题超过字数上限时，不再按字符硬截成半句，而是在同一个辅助模型会话里追加**最多一次**语义缩写：优先收短前置修饰，保留可识别的中心技术对象，不写切掉主宾语的句子；缩写后仍超限、仍不合格或已无预算时保留原标题，分别返回 `rewrite_failed` 或 `timeout`，不写任何目标。只有具备明确断句证据的形态才在未超限时也判为不完整：句末的结构助词「的」（已排除「目的」「标的」等成词）或拉丁标识符后单独悬空的助词；句末的「地/得/和/与」等常见词尾是正常收尾（如「迁移到本地」「趋于饱和」「应纳税所得」），不会触发改写。合格的短标题不会触发这次追加调用。自动命名的硬截断规则保持上一现役版不变。
- 每次点击只触发一次生成请求；进行中按钮禁用，服务端对同一工作区或同一会话的自动/手动生成返回 `busy`；成功、失败或跳过之后都可再次点击。重复点击属于正常用法，旧英文工作区和自动命名已跳过的工作区都能反复改。
- 工作区标题用 `setTitle` 写入；会话标题复用官方 CLI `agent update --name`；两者都不改目录、仓库或分支。
- 生成前记录各目标原标题，写入前逐一回读：生成期间工作区或所选会话被手动改名、归档或移出工作区，则本次不写任何目标并返回 `skipped`。工作区写入后再紧随 CLI 之前回读一次会话，若两处写之间会话被手动改名，工作区已写入，返回 `partial` 且不覆盖会话。
- 两个写入没有跨对象事务。任一处失败或超时时按实际回读结果分别报告 `workspaceUpdated` / `sessionUpdated`，状态为 `partial` 并给出可重试的原因；不会回滚已成功的写入，也不会覆盖人手改动。完成后逐目标回读确认写入值。
- Paseo 0.17.3/0.17.4 的常规插件 RPC 传输超时为 30 秒，而 `PluginHandlerContext` 没有 abort signal；插件使用 22 秒内部截止，扫描只花其中约 5 秒，并在分页之间、模型调用之间和最终写前反复检查；超时返回 `timeout`，迟到的模型或辅助会话完成不会在 RPC 返回后写入。分段提炼时每段预算按剩余时间均分，剩余不够就以 `timeout` 结束，不用残缺分段冒充完成。

**同步时限与分段**：分段提炼仍走同一个同步 RPC，在 22 秒预算内完成，每段只分到剩余预算的一部分；时间不够就以 `timeout` 结束，不写任何标题。常规会话的 30 000 字读取能放进两段；若轮次极多、每轮很短，「用户：」「助手：」标签也可能把已读内容推过两段上限，此时按 `segment_cap` 如实标部分覆盖，不冒充全会话。若需要更长会话的完整覆盖，或让多段提炼不受同步时限约束，需要另做受控异步 RPC/UI，本版本未做。

工作区自动首任务路径不变：仍是 `workspace.create.before` 种子加首个真实任务的模型/兜底标题，不读会话历史，也不受本面板选择影响。


## 验收与限制

**本次候选（会话自动命名与全量连续摘要）的自动化验证是离线合成的**：`npm run typecheck`、`npm test`，以及用 Paseo 0.17.4 自带插件编译器对候选目录做的真实打包检查（入口解析、manifest、server/client bundle 均成功；该检查在内存中完成，不安装、不加载）。测试全程使用合成输入与独占临时目录，无真实模型调用、未读取任何真实会话正文。候选内容在运行 Paseo 0.17.4 的宿主 daemon 上以 `plugin reload` 加载成功（`enabled`、`status: "running"`、`Plugin ready`，无报错行）。现场回读另已覆盖两类真实路径：一条历史失败记录被自动修复（状态为 `done`、`attempts=2`、`repairUsed=true`、无失败码，Paseo 回读的标题确实换成了摘要），以及一次手动重生成成功（标题保留了 WebSocket 主题，不再被截断）。全新会话的首轮自动命名（`agent.turn.after` 首轮触发与 `agent update --name` 实写）、20 秒 hook 与 22 秒 RPC 的实际预算上界，仍尚未单独现场实测。

下面这一组 0.17.3 隔离 daemon 黑盒结果来自**更早的构建**，不是本次候选的运行结果，只保留作为基础安装/命名背景，不能当作本版本的逐字输出或行为证据。那次 E2E 只覆盖安装/running、`workspace-sessions` RPC 接线与无会话时的可识别状态，不包含真实模型、真实会话摘要、会话改名或 30 秒传输。

- （旧构建）最终 `npm pack` 目录无 `node_modules`，官方 `plugin install` 后 `plugin ls` 为 `status: "running"`。
- （旧构建）普通目录英文首任务 `Fix login bug` → 工作区与 agent 均为 `修复 login bug`；本版本的同一输入应得到 `修复登录问题`，但未在真实 daemon 重跑。
- （旧构建）Git worktree 使用显式 `--new-branch keep-branch`，运行任务后分支仍为 `keep-branch`，工作区/agent 为 `实现 auth flow`。
- （旧构建）手动 workspace `手工工作区`、显式 agent `人工标题` 均保留。
- （旧构建）同一 workspace 并发/先后两条不同会话：工作区只命名一次，后续会话只命名自己；双并发两个不同 workspace 时各自标题正确。
- （旧构建）`plugin reload` 后名称保持；精确路径的引导 workspace 已归档，普通同标题 workspace 未被归档。
- （旧构建）Better Paseo **1.6.4**（本地可核副本 `version=1.6.4`、`build=202611211751`）与插件同装运行；其 `title-generation.json` 的 `afterFirstReply=false` 时，旧构建的新工作区/会话由本插件得到 `优化 cache metrics`，自动优化未接管。本版本按新规则应为 `优化缓存指标`，未在真实 daemon 复验。

### 本次验证

- `npm run typecheck`：通过。
- `npm test`：130 项通过。在上一候选的项目/工作区/双目标手动摘要覆盖之外，本候选新增：会话自动命名的场景 B（首次模型失败保留临时标题、下一不同完成轮补试、成功即停）、同一轮重复事件/重启/并发不重复消耗、失败与仅工具调用轮不消耗、provider 暂时不可用仍保留补试、两次失败后耗尽、手动改名胜出不被覆盖、`done+model_failed`/`provider_unavailable` legacy 只修复一次且用户改过就不修、已有明确标题与 `legacy` 不碰；`agent.turn.after` 的 `completed/failed/canceled` 经由真实 `contribute()` 注册的 hook 走通，已命名会话后续轮零读取零模型；时间线读取的 reset/gap/staleCursor 首屏与中途断点都标部分覆盖且不把跳段尾页拼进正文、首页读失败区分于空会话、连续分页覆盖时间顺序、超长会话分段上限如实标 `segment_cap`、工具密集首问仍取到本轮实质回答、同轮多段助手正文全部纳入、尾页不借别的轮次；摘要覆盖信息经 RPC 透传到界面，手动范围与刷新守卫保持；手动摘要另覆盖真实断句复现（`诊断 422 后关闭 CCHP 与 GDR 的` 不再被正式入口接受）、完整短标题单次调用（含「迁移到本地」「趋于饱和」「应纳税所得」这类正常词尾）、超长标题单次语义缩写保留中心对象、缩写仍不合格或预算耗尽时零写入与明确失败码。
- （上一候选，非本版本）0.17.3 隔离 daemon E2E（0.17.3 CLI、独占 `/tmp`、合成 HOME、`unix://` socket、`codex` provider 禁用）：`plugin install` 后 `plugin ls` 为 `running`，插件日志无报错；新建普通工作区后调用 `chinese-titles.workspace-sessions` 返回 `{"sessions":[]}`；不传 `agentId` 的重生成返回 `{"status":"needs_selection","reason":"no_session"}`，传不属于该工作区的 `agentId` 返回 `{"status":"skipped","reason":"session_not_selectable"}`，工作区标题保持不变；对不存在的工作区调用会话列表返回空数组。临时 daemon 与临时根已退出并清理。
- （上一候选，非本版本）隔离 daemon 冒烟（0.17.3 CLI 与 daemon、独占 `/tmp`、合成 HOME、`unix://` socket、`codex` provider 禁用、daemon 只监听该 socket）：`plugin install` 后 `plugin ls` 为 `running`、插件日志无报错；对一个真实存在、无会话的工作区，`chinese-titles.workspace-sessions` 返回 `{"sessions":[]}`；重生成分别传 `scope: "both"`、`"workspace"`、`"session"` 和不传 `scope`，四种请求都返回 `{"status":"needs_selection","reason":"no_session","workspaceUpdated":false,"sessionUpdated":false}`，工作区标题未变；`scope: "all"` 被 RPC 输入校验拒绝，缺 `workspaceId` 同样被拒绝；传不属于该工作区的 `agentId` 返回 `{"status":"skipped","reason":"session_not_selectable"}`；不存在的 `workspaceId` 重生成返回 `not_found`，会话列表返回空数组。该实例的 `codex` provider 已禁用，创建普通会话会报 `Provider 'codex' is disabled`，因此 CLI 会话改名的写前回读与真实写入未在此次冒烟中执行。临时 daemon 已停止，合成 HOME 与 `/tmp` 临时目录已删除。
- 未覆盖：真实 daemon 上的 `agent.turn.after` 回调、CLI `agent update --name` 实写与回读、20 秒 hook / 22 秒 RPC 的真实时限、真实时间线的 reset/gap 触发、真实模型的分段提炼与合成、客户端覆盖提示的实际渲染（宽屏/紧凑、深浅主题）、桌面/手机 UI、Better Paseo 手动“从对话生成标题”。

### 最小 smoke 复跑

```sh
# 1. 只使用独占合成 HOME/PASEO_HOME/CODEX_HOME，不读取真实登录态
D=$(mktemp -d); mkdir -p "$D/home" "$D/codex" "$D/proj"
cat > "$D/home/config.json" <<'JSON'
{"daemon":{"listen":"127.0.0.1:18888"},"agents":{"providers":{"codex":{"enabled":false}}},"pluginsEnabled":true}
JSON
env -i HOME="$D/home" PASEO_HOME="$D/home" CODEX_HOME="$D/codex"   PASEO_NODE_ENV=development PATH="$PATH" TMPDIR=/tmp   paseo daemon run --home "$D/home" &
# 2. 安装 npm pack 解包后的目录
env -i HOME="$D/home" PASEO_HOME="$D/home" CODEX_HOME="$D/codex" PATH="$PATH"   paseo --home "$D/home" plugin install /path/to/packed-plugin --id paseo-chinese-titles --json
# 3. 预期：plugin ls 为 running；新项目出现汉字；英文任务后工作区/agent 为中文兜底；
#    显式 new-branch 的 worktree 分支不变；手动改名后 reload 仍保持。
```

> 侧栏切到「标题」才能看到本插件写入的持久标题；「分支」显示的是 Git 分支。

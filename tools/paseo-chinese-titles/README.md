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
- manifest 下限：`>=0.16.0`。官方 v0.16.0 源码已有 `workspace.create.before`（`packages/plugin/src/server/lifecycle.ts:136,199`）、`addWorkspacePanel`（`packages/plugin/src/client/contracts.ts:236`），且 `session.ts:7350,7373-7405` 已让 metadata/firstAgentContext 经过该 hook，`workspace-auto-name.ts:179-191` 的覆盖条件与 0.17.3 相同；未发现真实 0.16.0 API 不兼容，故保留原下限。新行为仅在 0.17.3 类型检查与单测中验证，0.16.0 黑盒结果属于加入手动面板与种子钩子之前的构建，本版本未复验。

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
- **工作区/会话**：通过 hook 自带的 `context.paseo` 生成。只会话命名只调用一次；同一首任务同时命名工作区和会话且该会话是获胜会话时，只生成一次并复用；竞争中的非获胜会话在工作区结果之外单独生成一次自己的会话标题。自动路径在 `workspace.create.before` 先写入一个中文兜底种子标题（仅当请求没有 `title`；New Workspace 原始请求就是这样传 `firstAgentContext`），首个真实任务到达后再用模型或兜底替换；种子值记录在 workspace metadata，只有标题仍等于该值时才允许自动替换。写后重新读取并核对 `title`。**没有跨进程 CAS**：如果手动改名恰好落在最终 `refresh` 与写入之间，仍可能被覆盖；同一进程内自动与手动共用 workspace claim，最终写前看到已变化才跳过。
- **首任务判断**：不看创建顺序。workspace claim 内读取所有非后台、非子会话的首条真实用户消息，按 timeline entry 时间戳选最早者，同一毫秒用 agent ID 固定 tie break；由该获胜会话决定工作区标题。最早创建但一直没收到任务的空会话不会阻塞后创建会话先收到任务；两个会话都已有任务时也不会都返回 false。并发多 agent 由进程内 workspace claim 保证工作区只命名一次。
- **模型输出校验**：去掉 JSON/引号/Markdown/标签后只取一行；至少两个汉字，且每个拉丁词必须是产品/协议/大写缩写/含数字或文件名的标识符。普通英文、单汉字、全英文、仅首字母大写的普通词、带末尾句号或普通连字符伪装的英文都视为无效（例如 `修复 login bug`、`修复 LOGIN BUG.`、`修复 login-bug`）。中英混合首句会先规范化，不会因为句中出现一个汉字就直接通过。
- **中文兜底**：先识别常见任务动词和名词，保留有意义的专名/技术标识，再用自然中文组合（如 `修复登录问题`、`优化 Codex 会话`、`新增 OAuth 回调`）；识别不出时用简短通用中文（如 `处理任务`、`处理工作区`），不拼接整段普通英文。
- **保留已有和手动名称**：首次启用时用官方 CLI 列表建立基线，已有对象不改。自动路径只处理当前 `title` 为空、仍等于 Paseo provisional 首 prompt 文本、或仍等于本插件创建时写入的种子标题；显式标题、手动改名和其他英文标题都不当成自动标题。手动按钮不受此限制，但写前回读，生成期间被手动改名则跳过。
- **辅助会话**：中性目录、`background`、固定标题、只读 sandbox、`approval_policy: "never"`、禁用 web search、无预批准工具。辅助会话不进入本插件或 Better Paseo 的自动命名。
- **Paseo 内置 workspace-auto-name**：0.17.3 daemon 会在创建带首 prompt 的 workspace 时异步生成原生摘要，只在当前标题为空或仍等于首 prompt 文本时写入；它还可能重命名 branch-off 的占位分支，且没有受支持的关闭开关。本插件在 `workspace.create.before` 写入一个不同于首 prompt 的中文种子标题，因此原生摘要不会覆盖它；插件随后用它自己的模型/兜底替换。插件只写 `title`，不写 branch。若严格禁止分支变化，创建 worktree 时显式给 `--new-branch`，并接受内置分支重命名仍可能发生。安装前已存在的旧工作区没有种子；隐式创建工作区（例如打开普通目录时由 Paseo 内部 upsert，而不经过 `workspace.create.before`）也不会经过种子钩子。这两类工作区若已有英文标题，使用下面的手动按钮修复；按钮也可处理原生自动命名已跳过或已写英文的现场。
- **侧栏显示**：Paseo 的侧栏可按「标题」或「分支」显示。切到「分支」时看到的是 Git 分支名，不是本插件写入的标题；切到「标题」才能看到同一 daemon 持久的中文标题。

### 手动重新生成

工作区面板「中文标题」里先选会话、再选更新范围，最后点生成按钮。

- **先选会话，再生成**。面板列出这个工作区的普通会话（排除后台、子会话、内部会话和本插件自己的命名辅助会话）。只有一个可选会话时自动选中；有多个时默认不选，必须明确点选。插件不会按「最近运行」或工作区里第一个会话擅自替你选；未选中的会话既不参与摘要也不被改名。
- **三种更新范围**：「工作区和所选会话」（面板默认）、「仅工作区」、「仅所选会话」。一次请求只调用一次标题模型，生成的中文摘要同时写入选定目标，两处使用同一个标题和同一个字数上限。「仅会话」不读写工作区标题，也不改工作区的自动命名状态。「仅工作区」不改所选会话标题。
- **旧请求兼容**：请求未携带 `scope` 时按原行为只更新工作区；面板会显式发送 `both`。
- 生成时从所选会话的两端有界读取用户与助手可见文本，交错分页，尽量覆盖开头、中段和结尾，再按字数预算均匀取样。每侧有页数上限，并在每页前检查已有的 RPC 截止、到页数或两侧相遇即停；单次 timeline 请求没有取消参数，所以这是「页间截止」，不是绝对扫描时限。工具密集时可跨多页寻找可见对话；页数仍有上限，极端情况下仍可能遇不到。推理、工具调用、通知、待办、压缩记录、插件行和附件都不进入摘要；可识别的凭据（私钥、GitHub/OpenAI 类令牌、`*_TOKEN=` 赋值、`password=` 等）会先移除。**这段摘录会发送到设置里指定的标题模型**；界面与本节都提示这一点。
- **摘录取舍**：预算紧时每段取样优先保留用户自己的问题，助手的长回复只吃剩余额度；选段先按全场均匀取样，再在剩余预算内补中段空隙，避免最后一段重复收尾挤掉贯穿多轮的主线。摘录是有界采样，不是全量读取；极长会话仍可能有页间未覆盖的区段。
- **概括口径**：提示词要求按整个摘录找贯穿多轮的目标和实际工作；最后单独收尾的议题不会仅因靠后就自动变标题，但摘录里有证据的真实主题变化会保留。提示词不写死任何具体领域词。
- **读失败与空会话分开**：首个 timeline 页读取失败（含传输异常）返回 `conversation_unavailable`，不会误报成 `empty_conversation`；首页成功而后续页失败时用已读到的有界内容继续，不额外重试。
- **只接受真实模型结果**。手动路径不会用确定性兜底冒充成功：模型不可用、超时、没有可概括内容，或答案不是合格简体中文标题时，保留原标题并给出可重试的具体原因（`provider_unavailable`、`model_failed`、`invalid_title`、`empty_conversation` 等）。超过字数上限时按汉字/单词边界裁剪，不截断英文术语。
- 每次点击只触发一次生成；进行中按钮禁用，服务端对同一工作区或同一会话的自动/手动生成返回 `busy`；成功、失败或跳过之后都可再次点击。重复点击属于正常用法，旧英文工作区和自动命名已跳过的工作区都能反复改。
- 工作区标题用 `setTitle` 写入；会话标题复用官方 CLI `agent update --name`；两者都不改目录、仓库或分支。
- 生成前记录各目标原标题，写入前逐一回读：生成期间工作区或所选会话被手动改名、归档或移出工作区，则本次不写任何目标并返回 `skipped`。工作区写入后再紧随 CLI 之前回读一次会话，若两处写之间会话被手动改名，工作区已写入，返回 `partial` 且不覆盖会话。
- 两个写入没有跨对象事务。任一处失败或超时时按实际回读结果分别报告 `workspaceUpdated` / `sessionUpdated`，状态为 `partial` 并给出可重试的原因；不会回滚已成功的写入，也不会覆盖人手改动。完成后逐目标回读确认写入值。
- Paseo 0.17.3 的常规插件 RPC 传输超时为 30 秒，而 `PluginHandlerContext` 没有 abort signal；插件使用 22 秒内部截止，并在最终写前再次检查。超时返回 `timeout`，迟到的模型或辅助会话完成不会在 RPC 返回后写入。

自动首任务路径不变：仍是 `workspace.create.before` 种子加首个真实任务的模型/兜底标题，不读会话历史，也不受本面板选择影响。


## 验收与限制

**本次候选（三种更新范围与双目标写入）跑了离线验证和一次隔离 daemon 冒烟**：`npm run typecheck`、`npm test`，以及 0.17.3 真实 daemon 安装本候选后的 RPC 接线检查（见下方“本次验证”）。全程使用合成 HOME 与独占 `/tmp`，`codex` provider 禁用，无真实模型、无生产写入、未推送。真实会话摘要、SDK `setTitle` 与 CLI `agent update --name` 的实际写入路径仍未经黑盒验证，因为该实例禁用了 provider，无法创建普通会话。

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
- `npm test`：63 项通过。在原有覆盖（自然中文兜底、专名/标识符保留、普通英文/单汉字/全英文拒绝、中英混合首句规范化、`autoNameWorkspaces=false` 仍可手动生成、生成期间手动改名保护、并发 `busy` 与完成后重试、超时后不迟到写入、最终 refresh 后的截止与归档检查、创建种子与 metadata 标记、显式 title 保留、后台工作区跳过）之外，新增：单会话自动选中与多会话必须显式选择、跨工作区/辅助/子会话/隐藏会话选择被拒绝且不读取他人文本、长会话同时保留真实首任务与最近轮次（含 150 轮、隐藏推理混入的合成时间线）、隐藏事件/工具行/注入块不进摘录、`GH_TOKEN=`、`CCHP_TOKEN=`、密码 JSON、Bearer 等明确凭据被移除、模型失败/无效/超时/空历史不写标题、自动首任务兜底路径不受手动改动影响；三种范围各自的目标写入与未写入断言、双目标仅一次模型调用且两处标题逐字一致、多会话未选者零写入、生成期间工作区或会话手动改名/归档/移出时整体不写、工作区写后会话被改（或 CLI 失败）返回 `partial` 且不覆盖、缺省 `scope` 仍只改工作区、会话模式不占用工作区 claim、工作区写入真实失败时即便会话随后被改也不降级为 `skipped`。
- （上一候选，非本版本）0.17.3 隔离 daemon E2E（0.17.3 CLI、独占 `/tmp`、合成 HOME、`unix://` socket、`codex` provider 禁用）：`plugin install` 后 `plugin ls` 为 `running`，插件日志无报错；新建普通工作区后调用 `chinese-titles.workspace-sessions` 返回 `{"sessions":[]}`；不传 `agentId` 的重生成返回 `{"status":"needs_selection","reason":"no_session"}`，传不属于该工作区的 `agentId` 返回 `{"status":"skipped","reason":"session_not_selectable"}`，工作区标题保持不变；对不存在的工作区调用会话列表返回空数组。临时 daemon 与临时根已退出并清理。
- 本次隔离 daemon 冒烟（0.17.3 CLI 与 daemon、独占 `/tmp`、合成 HOME、`unix://` socket、`codex` provider 禁用、daemon 只监听该 socket）：`plugin install` 本候选后 `plugin ls` 为 `running`、插件日志无报错；对一个真实存在、无会话的工作区，`chinese-titles.workspace-sessions` 返回 `{"sessions":[]}`；重生成分别传 `scope: "both"`、`"workspace"`、`"session"` 和不传 `scope`，四种请求都返回 `{"status":"needs_selection","reason":"no_session","workspaceUpdated":false,"sessionUpdated":false}`，工作区标题未变；`scope: "all"` 被 RPC 输入校验拒绝，缺 `workspaceId` 同样被拒绝；传不属于该工作区的 `agentId` 返回 `{"status":"skipped","reason":"session_not_selectable"}`；不存在的 `workspaceId` 重生成返回 `not_found`，会话列表返回空数组。该实例的 `codex` provider 已禁用，创建普通会话会报 `Provider 'codex' is disabled`，因此 CLI 会话改名的写前回读与真实写入未在此次冒烟中执行。临时 daemon 已停止，合成 HOME 与 `/tmp` 临时目录已删除。
- 未覆盖：客户端面板的更新范围控件、三种范围的界面文案与实际渲染（宽屏/紧凑、深浅主题）、CLI 会话改名与 SDK `setTitle` 在真实 daemon 上的写入、重生成 RPC 的 30 秒真实传输、真实 Codex 鉴权下的会话摘要模型结果、桌面/手机 UI、Better Paseo 手动“从对话生成标题”。

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

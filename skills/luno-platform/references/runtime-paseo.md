# paseo 叠加适配

分支为 paseo-operations、paseo-dispatch、paseo-resume。触发见 `luno-platform`〈运行端〉。paseo-dispatch 与 paseo-resume 两分支共读本节，paseo-operations 不适用本节。其余槽位 Codex 端按 `references/runtime-codex.md`，Claude Code 端按 `references/runtime-claude.md`，均与 `references/runtime-host.md` 合用。义务、授权和停止条件以引用处为准。

## 共同前置

**审批。**以 Paseo 可核验的父子关系确认派单来源。需要审批或授权来源无法核实时，经对应 daemon 的官方入口或手机端处理原请求。Paseo v0.17.1 的 `list_pending_permissions` 和 `respond_to_permission` 作用于调用方 daemon，无 `serverId`。按已定位的目标 agent 核对请求，无法在对应 daemon 核实或处理时暂停依赖步骤。转述的批准和外发动作通过自动审批均不代替该会话的权限审批。

<a id="branch-paseo-operations"></a>
<!-- BEGIN paseo-operations -->
## Paseo 操作

产品用法和故障说明查官方 `paseo-help` 和当前文档。host、项目、工作区、agent、脚本和调度等通用操作查官方 `paseo`，命令及工具参数按目标端实际定义或 CLI 帮助核对。插件的开发、安装、管理和排障查官方 `paseo-plugin`。本分支规定本端的目标选择、授权、证据读取和回读；涉及本端角色派发时，另按本技能入口加载对应分支。

Paseo 的查询、管理、配置或恢复，先按目标 daemon 和预期结果选官方入口：优先能覆盖所需作用范围的结构化工具，其次用 CLI。选择前先核实目标 daemon 或宿主、版本、对象、所需能力以及认证和权限边界，再选择覆盖该作用范围的入口。遇到 403 时，在当前授权内依据可核的非秘密回执判断拒绝层，证据不足时标为未定位。入口缺失、语义不明或存在版本兼容差异时，查官方文档索引和当前工具定义，在目标环境读实际 CLI、子命令的 `--help`，按需核对相关配置；仍有疑问再比对同一版本的官方实现。只有在已核实同一语义，或没有可比接口但已核对候选入口能实现预期效果，且当前授权覆盖该入口时，才改走可用的 CLI 或另一种官方入口；不默认切换到另一 daemon，不绕过权限策略补齐操作，并从目标同一 daemon 回读实际对象和效果。CLI 与 daemon 的版本、权限和宿主选择按现场读取。

- **会话与工作区范围。**项目、workspace ID 和 cwd 分属不同层级；会话还分活动、归档和后台，默认列表通常看不到后两类，按 ID 或显式包含参数才能投影出来。历史只在授权内按最小必要读取；活动摘要这类混合文本不是源头投影，不能当作权威清单，应改用能按需限定字段和范围的入口，找不到就停在安全可得的证据并说明覆盖缺口。回读时交代实际覆盖了哪些清单和对象，从历史消息读取内容不因此获得新的操作授权。
- **生命周期与作用范围。**停止、关闭、归档和硬删除是不同层级的动作：停止通常只中止当前运行，关闭会结束会话运行时，归档把对象移出默认活动列表但保留可查记录，硬删除移除目标对象，历史和关联资源的保留范围以目标版本实现为准；具体语义和作用范围以目标版本的文档、帮助和实际状态为准，不按动作名称推测。归档会话或工作区可能连带子会话、终端或 Paseo 管理的 worktree；执行前按对象和作用域确认会牵连什么。归档后按原 ID 核归档记录；硬删除后在同一 daemon、同一权限范围内按原 ID 复核对象已移除。归档和硬删除都要按目标语义核本次操作涉及的历史和关联资源，不能只看活跃列表。只停止或关闭而按原 ID 仍能查到对象的，判断为实际停止、关闭或归档状态。
- **事实优先与生效判定。**以目标现场的可核证据为准，个例限于实测版本和入口。回执不明时从同一 daemon 按原对象回读，核对实际托管与运行状态（已落盘、已热加载、待重启或仍在途）。探测只核入口可用，目标会话实际使用按调用记录核验。证据分层与超时处置按 `luno-core/references/execution.md`〔分支 execution〕〈执行闭环〉。
- **观测台关项证据。**判断观测台（Agent Observatory）报告里的问题能否关闭时，按报告的 jobId 和报告内 finding id 定位（即 `observatory.insights.report`、`observatory.insights.feedback` 的输入字段）；界面没显示 ID 时，记下能唯一定位该报告与发现的 agent、生成时间和标题，不为此多设关项门禁。关项说明要给足以达到原问题关闭条件的可核证据和实际结果，证据可以是原始时间线、仓库、现场回读或实测；只写「已处理」或指向另一份总结不足以关项。改进建议按该建议记录单独验收。原始发现按各自的报告、发现和原关闭条件单独核对。改进建议完成、其他报告的状态和仓库合并，都不能代替原始发现的实际验收。遇同类复发，仍按对应原关闭条件和现场证据判断。证据沿用本分支的分层，配置回读不冒充实际执行，未测阶段写未验证。改进建议和原始发现的反馈都只在既有授权内写入，分别写进该建议自身的反馈入口和报告自带的 finding 反馈，并逐项回读。不另建账本、流程产物或普通状态关口。

- **观测台插件 RPC。**当现有官方入口无法完成观测台清单查询、反馈或回读时，可在当次授权覆盖的本地环境使用已安装的官方 `@getpaseo/client`。从现场确认的 Paseo CLI 实际入口解析其 SDK 依赖，核对 daemon、SDK 与 Agent Observatory 的版本及插件接口。以下接口于 2026-11-25 核对，适用于 Paseo 和 SDK v0.17.4、Agent Observatory v2.20.0，版本变化时重核。由获准的可信进程用 `@getpaseo/client/node` 的 `createHostClient` 创建指向已核目标的客户端，调用 `client.connect()` 后确认 `client.getLastServerInfoMessage()?.serverId` 与目标一致，再用 `client.invokePluginRpc("agent-observatory", method, input)`。凭据只用当次明确授权且已注入的指定变量，禁止从配置或保存态取用。遇到 `Password required` 且缺少获准凭据时，暂停依赖调用并报告。
  - 清点观测台当前未解决项时，在同一 daemon 用 `observatory.insights.list({})` 查询未按 agent 筛选的当前清单。逐份可查报告按发现和对应反馈计数，无反馈或 `open` 计为未解决，`resolved` 和 `false_positive` 计为已关闭。改进建议按自身反馈另计。汇报查询时间、实际覆盖范围和已知保留限制。引用历史报告时，标明其统计窗口。用户追踪修复进度时，按同一 daemon、同一查询范围和状态口径，与可比快照按 `jobId` 与 `findingId` 对账；可比范围内增加的新报告照常计入。区分快照差异与已知动作，不凭首尾两点声称中间过程的逐次变化。基线足够时分别给出关闭、重开、新出现和当前开放数；证据不足时只报已确认的变动与当前覆盖，不另设账本或扩大取数。
  - 按 agent 定位报告时调用 `observatory.insights.list`，传 `{ agentId }`，从 `jobs[].id` 取报告 `jobId`。用 `observatory.insights.report` 传 `{ jobId }`，在 `job.report.findings` 定位 `findingId`。按既有关闭条件和实际证据确定状态，已有写入授权时，用 `observatory.insights.feedback` 传 `{ jobId, findingId, status }`，状态取值为 `open`、`resolved`、`false_positive`。在同一 daemon 用原 `jobId` 重查报告，逐项核对 `job.findingFeedback[findingId].status`。
  - 用 `observatory.insights.suggestions` 传建议自身的 `{ jobId }`，在 `job.report.actions` 定位 `actionId`。获准写入时，用 `observatory.insights.action-feedback` 传 `{ jobId, actionId, status }`，状态取值为 `open`、`adopted`、`done`、`dismissed`。在同一 daemon 用原建议 `jobId` 重查建议，逐项核对 `job.feedback[actionId].status`。
  - 已合并仓库的 `tools/paseo-observatory.py` 是本节的固定窄入口：`report list|show` 读（清单只投影 `findings`、`resolvedFindings`、`reportAvailable`；`resolvedFindings` 只计 `resolved`，清单不推断开放数，完整清点按 `show` 的实际条目分别统计 `resolved` 与 `false_positive`；`show` 直接按 `jobId` 调 `report`）、`finding|suggestion dry-run` 零写预演、`close` 按显式条目与目标状态写一次并按原 ID 回读、`verify` 只回读；无反馈按 `open` 计，回读 `job.id` 必须等于请求 `jobId`。finding 与建议状态枚举分开，只连显式回环 IP（`127.0.0.1` 或 `[::1]`，不接受 `localhost`）且核对 `serverId`，并同时核 CLI 与 SDK 版本；凭据仅按名传 `PASEO_PASSWORD`，认证失败按 `DaemonAuthenticationError` 的 `name` 与 `reason` 识别。它不替代以上授权、条目判定和逐项回读义务，也不证明实际条目已验收。
  - 两个反馈接口只接收任务 ID、条目 ID 和状态。在可信进程内只投影所需的非秘密字段。关项证据、实际结果及逐项回读覆盖情况沿用本分支的口径向用户报告。写入回执不明时先回读原条目，再按总控规则处理。

入口与语义参考：[文档索引](https://paseo.sh/llms.txt) · [MCP](https://paseo.sh/docs/mcp) · [CLI](https://paseo.sh/docs/cli.md)。
<!-- END paseo-operations -->

<a id="branch-paseo-dispatch"></a>
<!-- BEGIN paseo-dispatch -->
## 派发通道

官方 `paseo` 技能中按 `notes` 选 Profile、复制 `featureValues` 和无匹配时发现 provider 的步骤适用于通用派发。Paseo 受管角色按下文匹配实时配置。

- Paseo 主会话、独立 Codex CLI 和 Claude Code 的所有委派（含通用兜底）按用户偏好默认使用已核验的 Paseo agent 通道。派发条件、角色归属和独立资格按 `luno-core/references/review.md`〔分支 delegation〕。只有用户明确指定才使用 Codex 原生 LENS/FORGE，按 `references/runtime-codex.md`〈派发通道〉核验。使用 Paseo 前按运行元数据核实会话归属、目标 daemon 和所需父子关系。归属不明或无已核通道时，只停依赖该派发的步骤并报告缺口。
- **角色入口。**在目标 daemon 上把派发用的 provider 登记为 `<运行时>-<网关>`，把角色 Profile 登记为 `<网关>-<角色小写>`。运行时前缀为 `codex` 或 `claude`；网关标识由小写 ASCII 字母或数字组成，可用单个连字符连接多段。维护者配置时须核对 provider 实际使用该网关和相应运行时，ID 是派发用的登记约定。旧会话继续保留原 provider 记录，已禁用或不符合登记约定的旧 ID 不参与新派发。角色是提示词层软角色，不构成独立身份或权限隔离。LENS/FORGE 开始前须完整读取部署的对应 `subagents/` 原文，项目指令及权限仍按实际加载核验。Claude 角色须先核实其启动入口能识别首条任务的角色行，并加载对应受管原文；不得从 Codex 的启动规则推定 Claude 已加载。
- **GLOBAL、角色启动与鉴权。**Codex 单端显式选择 `--codex-global-source paseo-append-system-prompt` 时，私人 GLOBAL 存放在已核 daemon 的 `daemon.appendSystemPrompt`，该提示词另附加到同一 daemon 启动的所有 agent，包括 LUNO、LENS、FORGE 及其他；原文同步由用户在 Minis 发起。授权、字节核对、切换、回读及全部接收端的新会话验收按 `luno-core/references/sync.md`〔分支 sync-host〕，不做 provider 级过滤。该模式的 Codex 生成入口按登记渲染角色启动段与共享提示词，首条任务的角色选择在 LUNO 职责段之前生效；安装器只处理受管生成文件，不读写该字段，独立 CLI 不直接获得它。需登录的鉴权由用户分别完成，`env_key` 沿用当次授权注入。安装器不读取、复制凭据或登录态，也不预置权限配置。
- **选取角色 Profile。**每次新派发前，从父会话同一活线程的运行元数据取得实际 provider。在目标 daemon 的 `list_providers` 核对该 ID 已启用且可用，按〈角色入口〉去掉运行时前缀及其后的连字符，得到完整网关标识。从同一 daemon 的 `list_profiles` 按 `<网关>-<角色小写>` 精确选出唯一 `profile.id`。子会话使用该 Profile 指定的 provider；按同一口径核对该 ID 已启用、可用且网关标识与父会话完全相同，并符合目标运行时的启动与权限要求。缺读取入口、ID 不合约定、匹配不唯一、必要字段缺失或网关不一致时，停止该次派发并报告缺口。不得换网关、换模型，或按显示名或 `notes` 兜底。
- **Profile 参数与权限。**将选中的 `provider` 和 `model` 拼成官方入口的 `provider/model` 选择：MCP 放在 `create_agent` 顶层 `provider`，SDK 放在 `config.provider`。将同一 Profile 的 `modeId`、`thinkingOptionId` 和完整 `options` 原样传入对应字段：MCP 为 `settings.modeId`、`settings.thinkingOptionId`、`settings.features`，SDK 为 `config.modeId`、`config.thinkingOptionId`、`config.options`。正式任务不论走哪个入口都只投递一次：MCP 用一次 `initialPrompt`，SDK 用一次 `prompt`，两者首行都写精确角色行，任务正文紧随其后同条投递。显式模式须为目标当前官方模式目录中的受支持值。省略可选项时，按目标官方解析或同 provider 的继承核实实际生效值。派发前比较父会话与目标实际生效的权限。跨运行时按模式、沙箱、审批和 provider 选项逐项核对，避免同名模式产生不同权限。子会话不得扩大父权限或绕过审批。无法核实实际权限或需要新授权时暂停相应派发，不猜模式或自动改为 unattended。
- **普通任务 MCP 派单。**负责人按当前任务选择工作区，优先检查父会话已核实的 `workspaceId`。讨论、只读及无需在 Paseo 工作区形成或修改仓库候选的任务，可以在当前工作区另建子会话，前提是能在授权范围内访问所需对象和版本并完成任务。当前工作区不适用时，可选目标 daemon 上其他已核且获准的工作区。`workspaceId` 指定会话所在的工作区，`projectId` 指定工作区归属的项目，实际读写路径和权限按任务授权核定，不能从父会话的 `cwd` 或项目归属推定。

  同一任务已有合适的隔离 worktree 时，包括父工作区就是该 worktree 的情况，核对候选归属、分支、基线、当前差分和写入交接后可以沿用，保持单一写入者。续派原 agent 或另建 agent 接续，按〈追问或续派〉和〈断流或不透明回包〉处理。只有需要独立仓库候选且没有合适的任务副本时，才从已核来源和确定基线调用 `create_workspace`，显式传入所属 `projectId`，以 `isolation: "worktree"` 创建任务分支和工作区。

  仅在需要定位目标仓库的工作区或新建仓库候选时核对项目归属。采用用户指定且已核实的项目，或与检出路径及 Git 归属证据唯一匹配的已登记项目。标题、目录名和 remote 同名只作线索。活跃工作区无匹配时，按〈Paseo 操作〉查询同一 daemon 的项目清单，覆盖没有活跃工作区的项目。归属仍有歧义或清单覆盖不足时，只暂停依赖该归属的步骤。仅在确需登记、项目清单确认无匹配且已有授权覆盖时创建项目，并回读登记路径与 `projectId`。不得为承载会话新造空仓库，或用无关仓库代替目标仓库。远端仓库候选按目标端规则隔离并核对基线，部署既定版本到获准的现役路径时核对现场前态并回读。混合任务逐项满足对应的隔离、授权和验证要求。

  新工作区建成后，在同一 daemon 按返回的 `workspaceId` 回读实际 `projectId`、`cwd` 和隔离类型，并核对候选的 Git 分支和基线。调用 `create_agent` 时显式传已核的 `workspaceId`，`notifyOnFinish` 取 `true`。创建后在同一 daemon 按 agent ID 用 `get_agent_status` 核对实际 `workspaceId`、`provider`、`model`，并核对 `snapshot.currentModeId` 与按本分支规则确定的预期模式一致（Paseo v0.17.4 的 snapshot 含该字段）；官方明确无模式的 provider 以该字段为空为预期。字段缺失、结果不符或创建状态不明时，先核实原对象及副作用，再决定如何接续。正式独立身份、权限、沙箱、审批和恢复仍按本分支对应条款核验。
- **SDK 角色入口。**普通任务仍用 MCP。正式审查或放行需要可核的角色来源，而常规入口无法证明启动参数、角色指令或任务绑定时，可在目标官方版本支持相应能力的前提下改用已实测的官方 SDK：Profile 仍按〈选取角色 Profile〉取得；由获准的宿主可信进程按〈SDK 取证边界〉回读目标 daemon 与工作区，并以工作区 ID 定位对象，不以 cwd 反推工作区。用当次获准注入的连接凭据创建匹配目标版本的 SDK client，在已核工作区调用 `client.workspaces.ref(workspaceId).agents.create`，传真实 parent 地址（agent ID、`{serverId, agentId}` 或句柄）、Profile 的 `provider/model`、`modeId`、`thinkingOptionId`、`options`，并以一次 `prompt` 投递与 MCP 相同的角色首行和完整任务。`config.systemPrompt` 取实际受管检出中该角色 `subagents/` 的完整原文；它不替代角色启动前完整加载受管源和 `luno-core` 的义务。权限、工作区、审批和 GLOBAL 附加规则不变。SDK 不是各版本通用的开关，先按目标官方版本核对这些能力。超时按现有规则先查原会话；SDK 可等待完成，或按〈SDK 取证边界〉从同一 daemon 投影必要字段后回读，不二次投递。
- **SDK 角色验收。**由获准的宿主可信进程按〈SDK 取证边界〉投影父子、`provider`/`model`、`workspaceId`、运行/轮次和待审批标记。Codex 按对应原生线程核对官方指令回执；Claude 只在取得等效的运行证据，能把有效角色指令和实际任务绑定到同一线程时，才可正式采纳。完整有效角色与附加文本、实际任务及回执的比对只在该进程内进行并只回结论。官方指令回执要核对线程 ID 与摘要对应有效完整指令，包含现有的附加部分，不能只对角色文件单独取哈希就当作已下发；回执字段、快照算法和内部路径属版本实现，不作稳定 API。MCP 未暴露该回执不构成省略本项核验的理由。启动参数、任务或证据无法绑定，或只有标签、自述时，不正式采纳。采纳按总控，换一个操作者不产生独立资格；只记录现场取值和布尔结论，不回显角色正文、其他线程历史或秘密。能力与回执参考目标版本的 [SDK API](https://paseo.sh/docs/sdk/reference.md) 与 [v0.17.2 回执实现](https://github.com/getpaseo/paseo/blob/v0.17.2/packages/server/src/server/agent/providers/codex/instruction-snapshot.ts)；版本只作可更新的取证引用。
- **SDK 取证边界。**对 SDK 会话，状态或活动读取（包括 `get_agent_status` 与 `get_agent_activity`）只有在获准的宿主可信进程能在工具输出前只投影父子 ID、模型、工作区、运行/轮次和待审批标记等必要非秘密字段时才适用；回包含角色正文、其他线程或其他原文时，不得直接调用后再脱敏，改用该进程内的官方 SDK 或获准的精确原记录投影。完整有效角色与附加文本、任务和回执的比对只回结论；已核 v0.17.2 的 wire 投影会去掉回执和附加字段但保留 `systemPrompt`，内部字段属版本实现，不作稳定 API。没有可安全取证入口时报告具体缺口，暂停依赖的采纳和恢复，不盲建新会话，也不取消原授权。
- **活线程验收。**官方原版 0.17.1 不提供 `codexRoleVerification`，不得把它列为必需证据或伪造替代；MCP 缺少该字段也不等于整个通道不可用。普通角色派发按父会话网关组、精确 Profile、显式参数和实际 `provider`/`model` 回读验收，并核对目标运行时的角色指令来源；正式独立审查或放行需要独立身份证据时，可按〈SDK 角色验收〉取得可核的角色来源，也可采用其他等效且已核的运行证据，证明不足时只报「通道身份未验证」并停止正式采纳。启动参数、上游、模型或指令来源变化时重核。私人角色正文和绝对路径留在宿主侧。
- **前台直建与草稿 Speed。**桌面前台直接选择角色 Profile 只展开 provider/model/mode/thinking/options；创建请求不携带 Profile ID 或角色身份，首条消息仍要写角色行，漏写按 LUNO。草稿中的 Speed 查询用该 provider 已登记的固定启动信息取得所选模型的能力，不建线程、不发送消息。Ultrafast 档位以实际 Codex 模型目录声明为准，没有声明时可能回落到 `default`。
- **非 Codex。**沿用各自已核实的官方运行入口、Profile 选择、启动核验和投递流程，核对实际 provider、上游、模型及角色指令来源，并保留上述权限、审批和工作区隔离要求。Profile 的旧 `featureValues` 与 `options` 合并，同键以 `options` 为准。Profile 未设模型时从目标官方模型目录解析默认值。跨 provider 未设模式时，从目标 daemon 的已就绪 provider 条目核实默认模式属于受支持模式并显式传入，只有官方明确无模式时才省略。无法核实所需模型、模式或身份时暂停相关派发。编排工具不可用时，须核实等价官方 CLI 能读取目标 daemon 生效的同一 Profile，完整传递所需字段，且满足工作区隔离、启动核验及同一会话投递要求，才可采用。调用发出后失败或状态未知时，先按下述恢复规则核实原执行。
- **daemon 范围。**Paseo v0.17.1 的 `list_profiles`、`cancel_agent` 和 provider 查询作用于调用方 daemon，无 `serverId`；v0.17.4 的 `list_profiles` 和 `list_providers` 仍是同一作用范围。跨宿主须使用目标 daemon 上已核实的官方入口。支持 `serverId` 的状态查询和投递工具按已核服务器及 agent ID 使用。没有目标入口时只停依赖操作并报告通道缺口，不以本机结果代替目标或据此判断产品能力。
- **时限与等待。**启动按 MCP 或 SDK 对应条款核验，跟进按 `luno-core/references/review.md`〔分支 delegation〕〈负责人：调用与采纳〉。MCP 默认依已开启的 `notifyOnFinish`。v0.17.4 的完成、错误及待审批通知排队，等父轮结束再投递。正常快任务写明在途即可结束父轮。触发检查时在已核服务器按原 `agentId` 用 `get_agent_status`，状态不足才在授权内用 `get_agent_activity` 读取最少的近期条目，SDK 按〈SDK 取证边界〉。待审批按〈共同前置〉，纠偏按〈追问或续派〉，获准取消当前运行用 `cancel_agent`。 [v0.17.4 通知实现](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/server/agent/finish-subscriptions/index.ts#L169-L205)

  父轮将结束且届时若仍无通知就需要检查时，已有创建授权且工具支持才用 `create_heartbeat` 唤醒当前父会话。核实目标版忙轮语义，可能打断运行时须已有相应授权。用 `cron` 对准检查时间，设 `maxRuns: 1` 和覆盖该次触发的短期 `expiresIn`，核对回执的目标、ID、`maxRuns`、`expiresAt` 和 `nextRunAt`。回执确认后结束等待中的父轮。提示只带当前任务和已核子会话地址，只在任务仍需跟进且缺终态时检查。终态先到且已获准删除时按 ID 用 `delete_heartbeat` 收尾，其余由上限约束。v0.17.4 遇忙可能失败，若另一轮在忙状态检查后抢先开始，还可能介入该轮。能力或授权不足、创建状态不明或唤醒失败时，按原预算在当前父轮做一次有界等待后检查，或由后续消息等自然唤醒再查，明确没有已确认的后台复查。创建回执不明先核原对象，不补建。 [MCP](https://paseo.sh/docs/mcp#schedules-and-heartbeats) · [Schedules](https://paseo.sh/docs/schedules) · [v0.17.4 heartbeat 执行](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/server/schedule/service.ts#L991-L1020) · [v0.17.4 运行启动](https://github.com/getpaseo/paseo/blob/v0.17.4/packages/server/src/server/agent/agent-prompt.ts#L95-L110)

- **断流或不透明回包。**遇到 `stream disconnected before completion`、`Required opaque-content summary was unavailable` 或等价回包，先唯一定位原服务器和 agent。按〈时限与等待〉核状态、active turn 和审批标记，并从获准的工作副本、Git、PR 或已改目标核清实际执行和交付。原会话无法定位、所需活动为空或交付不明时，停止依赖的接续和重派。待审批按〈共同前置〉。已完成的只核验或回传。原授权仍适用、待审批已解除且所需新审批已办妥后，按〈追问或续派〉向原会话排队投递已核实、仍获准且未排队或在途的剩余步骤。只有确认原会话无法恢复、执行和交付已核清且无在途任务，才按原派发规则核角色、模型、上游和授权后新建会话，仅承接已核实且仍获准的剩余步骤。正式独立审查的恢复与重试按 `luno-core/references/review.md`〔分支 review〕。
- **追问或续派。**向已核验的原 agent 使用 agent-scoped `send_agent_prompt`，跨宿主传入已核的 `serverId`。先核目标入口对 `activeTurnBehavior` 的实际定义。普通追问和续派省略该字段，按默认语义排队。v0.17.1 的 agent 默认值名为 `steer`，普通消息实际等当前轮结束，协议不接受显式 `queue`。v0.17.2 和 v0.17.3 的 agent 默认值是 `queue`。CLI 或无 agent 调用方的入口须单独核对。只有确需实时纠偏、已核实入口支持实时 `steer`，且当次授权允许在无法 steer 时打断当前轮，才显式传 `steer`。收到回执后核对 `messageId` 和 `guidance`。`queued` 只记为已受理排队，实际投递和任务完成分别按原会话的通知或回读核实。回执不明时先查原会话和投递状态，状态未核清前不得重发。 [v0.17.1 工具注册](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/tools/paseo-tools.ts#L1969-L2062) · [v0.17.1 协议](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/protocol/src/messages.ts#L1348) · [v0.17.1 投递](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/agent-messages/delivery.ts#L373-L400) · [v0.17.2 投递](https://github.com/getpaseo/paseo/blob/b2ca56ee73cb039d65ef23bc3b4bf17f7a650fa0/packages/server/src/server/agent/agent-messages/delivery.ts#L581-L602) · [v0.17.3 工具定义](https://github.com/getpaseo/paseo/blob/dd7c0499a8c311fae7b3244722a64d73cc178e4a/packages/server/src/server/agent/tools/paseo-tools.ts#L1297-L1324) · [v0.17.3 CLI](https://github.com/getpaseo/paseo/blob/dd7c0499a8c311fae7b3244722a64d73cc178e4a/packages/cli/src/commands/agent/send.ts#L42-L56)

Profile 字段和工具范围按 Paseo v0.17.1 固定提交 `043f0995d4d7e91ab12f3eecef1afce055a81972` 核对。共享角色选择、首行角色和 provider/model 回读为宿主适配；[Profile 类型](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/protocol/src/agent-profile.ts) · [工具注册](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/tools/paseo-tools.ts)
<!-- END paseo-dispatch -->

<a id="branch-paseo-resume"></a>
<!-- BEGIN paseo-resume -->
## 主会话接续

主会话断流、必要的不透明摘要缺失或回包不完整，按 `luno-core/references/handoff.md`〈恢复时〉接续。跨会话时在授权内按交接的 agent ID 或 Paseo 工作区会话列表唯一定位原会话及 daemon，只回读获准范围内必要的用户指令、交接、审批原证和交付记录。

用 `get_agent_status` 核对原会话及相关 agent 的运行和 active turn，证据不足才按授权读取最小活动。SDK 子会话按〈SDK 取证边界〉。审批按〈共同前置〉沿原请求处理。按授权查任务工作副本、Git、PR 或已改目标，核实执行、交付和剩余步骤。无法唯一定位、缺原文、授权不清、执行或交付不明、有在途或待审批时，暂停依赖步骤并报告缺口。只接续已核实且仍获准的剩余工作。已完成写入只核验，部分写入按原恢复规则处理。

<!-- END paseo-resume -->

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

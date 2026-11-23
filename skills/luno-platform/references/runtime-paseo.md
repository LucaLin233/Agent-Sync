# paseo 叠加适配

分支为 paseo-operations、paseo-dispatch、paseo-resume。触发见 `luno-platform`〈运行端〉。paseo-dispatch 与 paseo-resume 两分支共读本节，paseo-operations 不适用本节。其余槽位仍按 `references/runtime-codex.md` 与 `references/runtime-host.md`。义务、授权和停止条件以引用处为准。

## 共同前置

**审批。**以 Paseo 可核验的父子关系确认派单来源。需要审批或授权来源无法核实时，经对应 daemon 的官方入口或手机端处理原请求。Paseo v0.17.1 的 `list_pending_permissions` 和 `respond_to_permission` 作用于调用方 daemon，无 `serverId`。按已定位的目标 agent 核对请求，无法在对应 daemon 核实或处理时暂停依赖步骤。转述的批准和外发动作通过自动审批均不代替该会话的权限审批。

<a id="branch-paseo-operations"></a>
<!-- BEGIN paseo-operations -->
## Paseo 操作

Paseo 的查询、管理、配置或恢复，先按目标 daemon 和预期结果选官方入口：优先能覆盖所需作用范围的结构化工具，其次用 CLI。入口缺失、语义不明或存在版本兼容差异时，查官方文档索引和当前工具定义，在目标环境读实际 CLI、子命令的 `--help`，按需核对相关配置；仍有疑问再比对同一版本的官方实现。只有在已核实同一语义，或没有可比接口但已核对候选入口能实现预期效果，且当前授权覆盖该入口时，才改走可用的 CLI 或另一种官方入口；不默认切换到另一 daemon，不绕过权限策略补齐操作，并从目标同一 daemon 回读实际对象和效果。CLI 与 daemon 的版本、权限和宿主选择按现场读取。

- **会话与工作区范围。**项目、workspace ID 和 cwd 分属不同层级；会话还分活动、归档和后台，默认列表通常看不到后两类，按 ID 或显式包含参数才能投影出来。历史只在授权内按最小必要读取；活动摘要这类混合文本不是源头投影，不能当作权威清单，应改用能按需限定字段和范围的入口，找不到就停在安全可得的证据并说明覆盖缺口。回读时交代实际覆盖了哪些清单和对象，从历史消息读取内容不因此获得新的操作授权。
- **生命周期与作用范围。**停止、关闭、归档和硬删除是不同层级的动作：停止通常只中止当前运行，关闭会结束会话运行时，归档把对象移出默认活动列表但保留可查记录，硬删除移除目标对象，历史和关联资源的保留范围以目标版本实现为准；具体语义和作用范围以目标版本的文档、帮助和实际状态为准，不按动作名称推测。归档会话或工作区可能连带子会话、终端或 Paseo 管理的 worktree；执行前按对象和作用域确认会牵连什么。归档后按原 ID 核归档记录；硬删除后在同一 daemon、同一权限范围内按原 ID 复核对象已移除。归档和硬删除都要按目标语义核本次操作涉及的历史和关联资源，不能只看活跃列表。只停止或关闭而按原 ID 仍能查到对象的，判断为实际停止、关闭或归档状态。
- **事实优先与生效判定。**文档、帮助输出和实际状态不一致时，以现场已核证据为准，并按证据描述行为，不把个例命令当作通用能力。配置或异步操作要区分受理回执、明确的生效结果和等待超时。返回信息未能确定实际结果时，回读目标状态，按目标当前的托管方式和实际运行状态判断是已落盘、已热加载、待重启还是任务仍在途，重试与继续等待按 `luno-core` 的规则处理。

入口与语义参考：[文档索引](https://paseo.sh/llms.txt) · [MCP](https://paseo.sh/docs/mcp) · [CLI](https://paseo.sh/docs/cli.md)。
<!-- END paseo-operations -->

<a id="branch-paseo-dispatch"></a>
<!-- BEGIN paseo-dispatch -->
## 派发通道

- Paseo 主会话和独立 Codex CLI 的所有委派（含通用兜底）按用户偏好默认使用已核验的 Paseo agent 通道。派发条件、角色归属和独立资格按 `luno-core/references/review.md`〔分支 delegation〕。只有用户明确指定才使用 Codex 原生 LENS/FORGE，按 `references/runtime-codex.md`〈派发通道〉核验。使用 Paseo 前按运行元数据核实会话归属、目标 daemon 和所需父子关系。归属不明或无已核通道时，只停依赖该派发的步骤并报告缺口。受派方不得再委派。
- **角色入口。**共享 Codex 使用内部 ID 为 `cchp`、`gdr` 的两个 provider，显示名分别为 CCHP、GDR。每个 provider 各有 LUNO、LENS、FORGE 三个 Profile，六个 Profile ID 固定为 `cchp-luno`、`cchp-lens`、`cchp-forge`、`gdr-luno`、`gdr-lens`、`gdr-forge`。官方原版只使用主 `CODEX_HOME`，同一上游三个角色共用家目录、登录态、文件系统和权限边界；角色是提示词层软角色，不是独立身份或权限隔离。LENS/FORGE 开始前须完整读取部署的对应 `subagents/` 原文，项目指令及权限仍按实际加载核验。
- **GLOBAL 与鉴权。**启用 daemon 范围 GLOBAL（`daemon.appendSystemPrompt`）时，该提示词另附加到同一 daemon 启动的所有 agent，包括 LUNO、LENS、FORGE 及其他。授权、切换、回读及全部接收端的新会话验收按 `luno-core/references/sync.md`〔分支 sync-host〕，不做 provider 级过滤。安装器不读写该字段，独立 CLI 不直接获得它。需登录的鉴权由用户分别完成，`env_key` 沿用当次授权注入。安装器不读取、复制凭据或登录态，也不预置权限配置。
- **选取共享 Codex Profile。**每次新派发前，从父会话同一活线程的运行元数据取得实际 provider。用目标 daemon 的 `list_profiles` 读取当前配置，按父 provider 和所需角色的精确 `profile.id` 选出唯一 Profile，再核它的 `provider` 精确等于父 provider。缺读取入口、无唯一匹配、字段缺失或 provider 不等时，报告缺口并停止依赖该次派发的步骤；不跨上游、不换模型、不按名称或 `notes` 兜底。
- **Profile 参数与权限。**将选中的 `provider` 和 `model` 拼成官方入口的 `provider/model` 选择：MCP 放在 `create_agent` 顶层 `provider`，SDK 放在 `config.provider`。将同一 Profile 的 `modeId`、`thinkingOptionId` 和完整 `options` 原样传入对应字段：MCP 为 `settings.modeId`、`settings.thinkingOptionId`、`settings.features`，SDK 为 `config.modeId`、`config.thinkingOptionId`、`config.options`。正式任务不论走哪个入口都只投递一次：MCP 用一次 `initialPrompt`，SDK 用一次 `prompt`，两者首行都写精确角色行，任务正文紧随其后同条投递。显式模式须为目标当前官方模式目录中的受支持值。省略可选项时，按目标官方解析或同 provider 的继承核实实际生效值。所选模式、沙箱、审批及 provider 选项不得扩大父权限或绕过审批。无法核实实际权限或需要新授权时暂停相应派发，不猜模式或自动改为 unattended。
- **普通任务 MCP 派单。**负责人按当前任务选择工作区，优先检查父会话已核实的 `workspaceId`。讨论、只读及无需在 Paseo 工作区形成或修改仓库候选的任务，可以在当前工作区另建子会话，前提是能在授权范围内访问所需对象和版本并完成任务。当前工作区不适用时，可选目标 daemon 上其他已核且获准的工作区。`workspaceId` 指定会话所在的工作区，`projectId` 指定工作区归属的项目，实际读写路径和权限按任务授权核定，不能从父会话的 `cwd` 或项目归属推定。

  同一任务已有合适的隔离 worktree 时，包括父工作区就是该 worktree 的情况，核对候选归属、分支、基线、当前差分和写入交接后可以沿用，保持单一写入者。续派原 agent 或另建 agent 接续，按〈追问或续派〉和〈断流或不透明回包〉处理。只有需要独立仓库候选且没有合适的任务副本时，才从已核来源和确定基线调用 `create_workspace`，显式传入所属 `projectId`，以 `isolation: "worktree"` 创建任务分支和工作区。

  仅在需要定位目标仓库的工作区或新建仓库候选时核对项目归属。采用用户指定且已核实的项目，或与检出路径及 Git 归属证据唯一匹配的已登记项目。标题、目录名和 remote 同名只作线索。活跃工作区无匹配时，按〈Paseo 操作〉查询同一 daemon 的项目清单，覆盖没有活跃工作区的项目。归属仍有歧义或清单覆盖不足时，只暂停依赖该归属的步骤。仅在确需登记、项目清单确认无匹配且已有授权覆盖时创建项目，并回读登记路径与 `projectId`。不得为承载会话新造空仓库，或用无关仓库代替目标仓库。远端仓库候选按目标端规则隔离并核对基线，部署既定版本到获准的现役路径时核对现场前态并回读。混合任务逐项满足对应的隔离、授权和验证要求。

  新工作区建成后，在同一 daemon 按返回的 `workspaceId` 回读实际 `projectId`、`cwd` 和隔离类型，并核对候选的 Git 分支和基线。调用 `create_agent` 时显式传已核的 `workspaceId`，`notifyOnFinish` 取 `true`。创建后在同一 daemon 按 agent ID 用 `get_agent_status` 核对实际 `workspaceId`、`provider` 和 `model`。字段缺失、结果不符或创建状态不明时，先核实原对象及副作用，再决定如何接续。正式独立身份、权限、沙箱、审批和恢复仍按本分支对应条款核验。
- **SDK 角色入口。**普通任务仍用 MCP。正式审查或放行需要可核的角色来源，而常规入口无法证明启动参数、角色指令或任务绑定时，可在目标官方版本支持相应能力的前提下改用已实测的官方 SDK：Profile 仍按〈选取共享 Codex Profile〉取得；由获准的宿主可信进程按〈SDK 取证边界〉回读目标 daemon 与工作区，并以工作区 ID 定位对象，不以 cwd 反推工作区。用当次获准注入的连接凭据创建匹配目标版本的 SDK client，在已核工作区调用 `client.workspaces.ref(workspaceId).agents.create`，传真实 parent 地址（agent ID、`{serverId, agentId}` 或句柄）、Profile 的 `provider/model`、`modeId`、`thinkingOptionId`、`options`，并以一次 `prompt` 投递与 MCP 相同的角色首行和完整任务。`config.systemPrompt` 取实际受管检出中该角色 `subagents/` 的完整原文；它不替代角色启动前完整加载受管源和 `luno-core` 的义务。权限、工作区、审批和 GLOBAL 附加规则不变。SDK 不是各版本通用的开关，先按目标官方版本核对这些能力。超时按现有规则先查原会话；SDK 可等待完成，或按〈SDK 取证边界〉从同一 daemon 投影必要字段后回读，不二次投递。
- **SDK 角色验收。**由获准的宿主可信进程按〈SDK 取证边界〉投影父子、`provider`/`model`、`workspaceId`、运行/轮次和待审批标记，并关联对应的 Codex 原生线程；完整有效角色与附加文本、实际任务及回执的比对只在该进程内进行并只回结论。官方指令回执要核对线程 ID 与摘要对应有效完整指令，包含现有的附加部分，不能只对角色文件单独取哈希就当作已下发；回执字段、快照算法和内部路径属版本实现，不作稳定 API。MCP 未暴露该回执不构成省略本项核验的理由。启动参数、任务或证据无法绑定，或只有标签、自述时，不正式采纳。采纳按总控，换一个操作者不产生独立资格；只记录现场取值和布尔结论，不回显角色正文、其他线程历史或秘密。能力与回执参考目标版本的 [SDK API](https://paseo.sh/docs/sdk/reference.md) 与 [v0.17.2 回执实现](https://github.com/getpaseo/paseo/blob/v0.17.2/packages/server/src/server/agent/providers/codex/instruction-snapshot.ts)；版本只作可更新的取证引用。
- **SDK 取证边界。**对 SDK 会话，超时或断流后的通用状态读取（包括 `get_agent_status` 与 `get_agent_activity`）只有在获准的宿主可信进程能在工具输出前只投影父子 ID、模型、工作区、运行/轮次和待审批标记等必要非秘密字段时才适用；回包含角色正文、其他线程或其他原文时，不得直接调用后再脱敏，改用该进程内的官方 SDK 或获准的精确原记录投影。完整有效角色与附加文本、任务和回执的比对只回结论；已核 v0.17.2 的 wire 投影会去掉回执和附加字段但保留 `systemPrompt`，内部字段属版本实现，不作稳定 API。没有可安全取证入口时报告具体缺口，暂停依赖的采纳和恢复，不盲建新会话，也不取消原授权。
- **活线程验收。**官方原版 0.17.1 不提供 `codexRoleVerification`，不得把它列为必需证据或伪造替代；MCP 缺少该字段也不等于整个通道不可用。普通角色派发按父 provider、精确 Profile、显式参数和实际 `provider`/`model` 回读验收；正式独立审查或放行需要独立身份证据时，可按〈SDK 角色验收〉取得可核的角色来源，也可采用其他等效且已核的运行证据，证明不足时只报「通道身份未验证」并停止正式采纳。启动参数、上游、模型或指令来源变化时重核。私人角色正文和绝对路径留在宿主侧。
- **前台直建与草稿 Speed。**桌面前台直接选择角色 Profile 只展开 provider/model/mode/thinking/options；创建请求不携带 Profile ID 或角色身份，首条消息仍要写角色行，漏写按 LUNO。草稿中的 Speed 查询用该 provider 已登记的固定启动信息取得所选模型的能力，不建线程、不发送消息。Ultrafast 档位以实际 Codex 模型目录声明为准，没有声明时可能回落到 `default`。
- **非 Codex。**沿用各自已核实的官方运行入口、Profile 选择、启动核验和投递流程，核对实际 provider、上游、模型及角色指令来源，并保留上述权限、审批和工作区隔离要求。Profile 的旧 `featureValues` 与 `options` 合并，同键以 `options` 为准。Profile 未设模型时从目标官方模型目录解析默认值。跨 provider 未设模式时，从目标 daemon 的已就绪 provider 条目核实默认模式属于受支持模式并显式传入，只有官方明确无模式时才省略。无法核实所需模型、模式或身份时暂停相关派发。编排工具不可用时，须核实等价官方 CLI 能读取目标 daemon 生效的同一 Profile，完整传递所需字段，且满足工作区隔离、启动核验及同一会话投递要求，才可采用。调用发出后失败或状态未知时，先按下述恢复规则核实原执行。
- **daemon 范围。**Paseo v0.17.1 的 `list_profiles`、`cancel_agent` 和 provider 查询作用于调用方 daemon，无 `serverId`。跨宿主须使用目标 daemon 上已核实的官方入口。支持 `serverId` 的状态查询和投递工具按已核服务器及 agent ID 使用。没有目标入口时只停依赖操作并报告通道缺口，不以本机结果代替目标或据此判断产品能力。
- **时限。**负责人为每次派发设定时限。超时先用 `get_agent_status` 核真实状态，未确认终止就不重派同一写任务。取消用 `cancel_agent`。
- **断流或不透明回包。**派发返回 `stream disconnected before completion`、`Required opaque-content summary was unavailable` 或等价的不完整回包时，完成状态视为未知。先唯一定位原 agent 及其服务器，再用 `get_agent_status` 与 `get_agent_activity` 核对运行状态、active turn 和待处理审批，并从任务工作副本、Git 或 PR、已改目标核清实际执行和交付。创建结果无法定位、活动摘要为空或交付仍不明时，均不得据此自动重建会话或重派任务。审批待处理时只按〈共同前置〉跟进原请求。已完成的任务只核验或回传。向原 agent 续派或另建角色会话接续前，均须确认原授权仍适用、无待处理审批，并办妥确需的新审批。只有确认原 agent 空闲、执行与交付已核清、确有剩余步骤且能避免投递竞态，才向原 agent 发 `steer`。投递期间若出现新轮次，`steer` 无法加入时可能退化为 `interrupt`，发送前的空闲快照无法保证投递时仍空闲。确认原会话无法恢复、执行与交付已核清且无在途任务后，方可按现有派单规则新建角色会话，只承接已核实且仍获授权的剩余步骤，并重新核验角色、模型、上游和授权。正式独立审查的恢复与重试按 `luno-core/references/review.md`〔分支 review〕执行。
- **追问或续派。**向已核验的原 agent 使用 `send_agent_prompt`，`activeTurnBehavior` 取 `steer`。

Profile 字段和工具范围按 Paseo v0.17.1 固定提交 `043f0995d4d7e91ab12f3eecef1afce055a81972` 核对。共享角色选择、首行角色和 provider/model 回读为宿主适配；官方原版不提供 `codexRoleVerification`。 [Profile 类型](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/protocol/src/agent-profile.ts) · [工具注册](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/tools/paseo-tools.ts)
<!-- END paseo-dispatch -->

<a id="branch-paseo-resume"></a>
<!-- BEGIN paseo-resume -->
## 主会话接续

主会话自身遇到断流、必要的不透明摘要缺失或回包不完整时，按 `luno-core/references/handoff.md`〈恢复时〉核对任务版本、原授权、实际执行状态和验收缺口。

新主会话在获准接续时，通过交接给出的 agent ID 或获准查看的 Paseo 工作区会话列表，按当前任务与工作区唯一定位原主会话及其服务器。按 `luno-core/references/handoff.md`〈恢复时〉，只在获准的消息范围内回读必要的用户指令、交接、审批原证和交付记录，核对任务版本及原授权是否仍适用。用 `get_agent_status` 和 `get_agent_activity` 核对原主会话及本任务相关 agent 的运行状态和 active turn，按〈共同前置〉核对待处理请求。用已授权的任务工作副本、Git、PR 或已改目标核实实际执行、已有交付和剩余步骤。只继续已核实且仍获授权的剩余工作。对已完成的写入，核验符合要求即可。遇部分写入，核清实际状态后只处理仍获授权的缺口，必要时按原恢复规则处置。已有交付按需回传。

原会话无法唯一定位、必要原文缺失、相关 agent 在途或状态未知、实际执行或交付不明、原授权不清或审批待处理时，只停依赖步骤并报告缺口。待审批沿原请求处理，确需的新审批经实际审批入口办妥后再执行相关步骤。例如，原主会话收到 HTTP 503，确认无 active turn、无待审批且本任务无相关在途操作后，新主会话可根据当前工作区及原会话必要记录完成仍获授权的未答事项。

<!-- END paseo-resume -->

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

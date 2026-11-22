# paseo 叠加适配

分支为 paseo-dispatch、paseo-resume。触发见 `luno-platform`〈运行端〉。两分支共读本节。其余槽位仍按 `references/runtime-codex.md` 与 `references/runtime-host.md`。义务、授权和停止条件以引用处为准。

## 共同前置

**审批。**以 Paseo 可核验的父子关系确认派单来源。需要审批或授权来源无法核实时，经对应 daemon 的官方入口或手机端处理原请求。Paseo v0.17.1 的 `list_pending_permissions` 和 `respond_to_permission` 作用于调用方 daemon，无 `serverId`。按已定位的目标 agent 核对请求，无法在对应 daemon 核实或处理时暂停依赖步骤。转述的批准和外发动作通过自动审批均不代替该会话的权限审批。

<a id="branch-paseo-dispatch"></a>
<!-- BEGIN paseo-dispatch -->
## 派发通道

- Paseo 主会话和独立 Codex CLI 的所有委派（含通用兜底）按用户偏好默认使用已核验的 Paseo agent 通道。派发条件、角色归属和独立资格按 `luno-core/references/review.md`〔分支 delegation〕。只有用户明确指定才使用 Codex 原生 LENS/FORGE，按 `references/runtime-codex.md`〈派发通道〉核验。使用 Paseo 前按运行元数据核实会话归属、目标 daemon 和所需父子关系。归属不明或无已核通道时，只停依赖该派发的步骤并报告缺口。受派方不得再委派。
- **角色入口。**共享 Codex 使用内部 ID 为 `cchp`、`gdr` 的两个 provider，显示名分别为 CCHP、GDR。每个 provider 各有 LUNO、LENS、FORGE 三个 Profile。宿主按上游和角色选择实际启动入口、`CODEX_HOME` 和登记的角色原文。LENS、FORGE 的四个角色家目录各自独立并与主会话分开，沿用 `tools/sync-targets.json` 的登记，目录名独立于 provider ID。这四个家目录的 `AGENTS.md` 仅含相应 `subagents/` 角色原文，生效的 Codex 配置均须为 `agents.enabled=false` 和 `features.multi_agent_v2=false`。家目录分离不构成操作系统或数据访问隔离，项目指令及权限仍须按实际加载核验。
- **GLOBAL 与鉴权。**启用 daemon 范围 GLOBAL（`daemon.appendSystemPrompt`）时，该提示词另附加到同一 daemon 启动的所有 agent，包括 LUNO、LENS、FORGE 及其他。授权、切换、回读及全部接收端的新会话验收按 `luno-core/references/sync.md`〔分支 sync-host〕，不做 provider 级过滤。安装器不读写该字段，独立 CLI 不直接获得它。需登录的鉴权由用户分别完成，`env_key` 沿用当次授权注入。安装器不读取、复制凭据或登录态，也不预置权限配置。
- **选取共享 Codex Profile。**每次新派发前，从已核实的父会话同一活线程的角色验收记录取得当前 `upstream`，按本节的活线程核验要求回读并确认父 provider 与该上游一致。用目标 daemon 的 `list_profiles` 读取当前配置，按 `options.paseo_role` 和 `options.paseo_upstream` 选出同上游、所需角色的唯一 Profile，再核它的 `provider` 精确等于父已核 provider。每次重读路由及启动参数。缺父活线程证据、缺读取入口、无唯一匹配、字段缺失或错配时，报告缺口并停止依赖该次派发的步骤，不跨上游或换模型兜底。
- **Profile 参数与权限。**将选中的 `provider` 和 `model` 拼成 Paseo v0.17.1 `create_agent` 顶层的 `provider` 参数 `<provider>/<model>`。共享 Codex 将同一 Profile 的 `modeId`、`thinkingOptionId` 和完整 `options` 分别原样传入 `settings.modeId`、`settings.thinkingOptionId` 和 `settings.features`。显式模式须为目标当前官方模式目录中的受支持值。省略可选项时，按目标官方解析或同 provider 的继承核实实际生效值。所选模式、沙箱、审批及 provider 选项不得扩大父权限或绕过审批。无法核实实际权限或需要新授权时暂停相应派发，不猜模式或自动改为 unattended。
- **共享 Codex 派单。**实施类先用 `create_workspace` 以 worktree 隔离，从确定基线分出任务分支，创建时传对应 `workspaceId`。用 `create_agent` 创建角色，`notifyOnFinish` 取 `true`。正式任务仅用一次 `initialPrompt` 投递。宿主在首个模型请求前硬拒绝缺失或错配的绑定，并从实际线程启动或恢复响应核验线程 ID、生效的 `modelProvider`、解析后的模型和 `instructionSources`。预期家目录的 `AGENTS.md` 须实际加载并与登记原文字节一致，且无该家目录的 `AGENTS.override.md` 遮蔽。进入 `turn/start` 前还须确认核验仍对应当前连接、线程和模型。
- **活线程验收。**创建后用同一 daemon、同一 agent ID 的 `get_agent_status` 回读该活线程的 `snapshot.runtimeInfo.extra.codexRoleVerification`。核对 `role` 和 `upstream` 与预期一致，`resolvedModel` 与实际提交的目标模型一致，且 `roleMatches=true`、`overrideExists=false`、`upstreamMatches=true`。配置模型、列表、角色自述和历史快照均不能代替活线程证据。启动参数、上游、模型、home 或指令来源变化时重核。缺证或不符时报告「通道身份未验证」，停止依赖步骤，按下述规则查原 agent 的实际状态。私人角色正文和绝对路径留在宿主侧。
- **前台直建与草稿 Speed。**桌面前台直建请求在无编排调用者、非后台且共享 provider 的 `providerOptions` 同时缺少 `paseo_role` 和 `paseo_upstream` 时，由宿主按所选 provider 的上游绑定 LUNO。创建请求不携带 Profile ID，宿主无法区分未选 Profile 与所选 Profile 两字段均缺失，配置验收须逐一确认共享 Profile 声明有效角色和与 provider 一致的上游，并确认两个字段随创建请求传入。仅缺一个字段、值错配或编排缺绑定的请求须由宿主拒绝。草稿中的 Speed 查询用该 provider 已登记的固定启动信息取得所选模型的能力，不建线程、不发送消息。创建或恢复真实线程仍执行角色门禁。
- **非 Codex。**沿用各自已核实的官方运行入口、Profile 选择、启动核验和投递流程，核对实际 provider、上游、模型及角色指令来源，并保留上述权限、审批和工作区隔离要求。Profile 的旧 `featureValues` 与 `options` 合并，同键以 `options` 为准。Profile 未设模型时从目标官方模型目录解析默认值。跨 provider 未设模式时，从目标 daemon 的已就绪 provider 条目核实默认模式属于受支持模式并显式传入，只有官方明确无模式时才省略。无法核实所需模型、模式或身份时暂停相关派发。编排工具不可用时，须核实等价官方 CLI 能读取目标 daemon 生效的同一 Profile，完整传递所需字段，且满足工作区隔离、启动核验及同一会话投递要求，才可采用。调用发出后失败或状态未知时，先按下述恢复规则核实原执行。
- **daemon 范围。**Paseo v0.17.1 的 `list_profiles`、`cancel_agent` 和 provider 查询作用于调用方 daemon，无 `serverId`。跨宿主须使用目标 daemon 上已核实的官方入口。支持 `serverId` 的状态查询和投递工具按已核服务器及 agent ID 使用。没有目标入口时只停依赖操作并报告通道缺口，不以本机结果代替目标或据此判断产品能力。
- **时限。**负责人为每次派发设定时限。超时先用 `get_agent_status` 核真实状态，未确认终止就不重派同一写任务。取消用 `cancel_agent`。
- **断流或不透明回包。**派发返回 `stream disconnected before completion`、`Required opaque-content summary was unavailable` 或等价的不完整回包时，完成状态视为未知。先唯一定位原 agent 及其服务器，再用 `get_agent_status` 与 `get_agent_activity` 核对运行状态、active turn 和待处理审批，并从任务工作副本、Git 或 PR、已改目标核清实际执行和交付。创建结果无法定位、活动摘要为空或交付仍不明时，均不得据此自动重建会话或重派任务。审批待处理时只按〈共同前置〉跟进原请求。已完成的任务只核验或回传。向原 agent 续派或另建角色会话接续前，均须确认原授权仍适用、无待处理审批，并办妥确需的新审批。只有确认原 agent 空闲、执行与交付已核清、确有剩余步骤且能避免投递竞态，才向原 agent 发 `steer`。投递期间若出现新轮次，`steer` 无法加入时可能退化为 `interrupt`，发送前的空闲快照无法保证投递时仍空闲。确认原会话无法恢复、执行与交付已核清且无在途任务后，方可按现有派单规则新建角色会话，只承接已核实且仍获授权的剩余步骤，并重新核验角色、模型、上游和授权。正式独立审查的恢复与重试按 `luno-core/references/review.md`〔分支 review〕执行。
- **追问或续派。**向已核验的原 agent 使用 `send_agent_prompt`，`activeTurnBehavior` 取 `steer`。

Profile 字段和工具范围按 Paseo v0.17.1 固定提交 `043f0995d4d7e91ab12f3eecef1afce055a81972` 核对。共享角色选择、线程门禁及草稿启动为宿主适配。 [Profile 类型](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/protocol/src/agent-profile.ts) · [工具注册](https://github.com/getpaseo/paseo/blob/043f0995d4d7e91ab12f3eecef1afce055a81972/packages/server/src/server/agent/tools/paseo-tools.ts)
<!-- END paseo-dispatch -->

<a id="branch-paseo-resume"></a>
<!-- BEGIN paseo-resume -->
## 主会话接续

主会话自身遇到断流、必要的不透明摘要缺失或回包不完整时，按 `luno-core/references/handoff.md`〈恢复时〉核对任务版本、原授权、实际执行状态和验收缺口。

新主会话在获准接续时，通过交接给出的 agent ID 或获准查看的 Paseo 工作区会话列表，按当前任务与工作区唯一定位原主会话及其服务器。按 `luno-core/references/handoff.md`〈恢复时〉，只在获准的消息范围内回读必要的用户指令、交接、审批原证和交付记录，核对任务版本及原授权是否仍适用。用 `get_agent_status` 和 `get_agent_activity` 核对原主会话及本任务相关 agent 的运行状态和 active turn，按〈共同前置〉核对待处理请求。用已授权的任务工作副本、Git、PR 或已改目标核实实际执行、已有交付和剩余步骤。只继续已核实且仍获授权的剩余工作。对已完成的写入，核验符合要求即可。遇部分写入，核清实际状态后只处理仍获授权的缺口，必要时按原恢复规则处置。已有交付按需回传。

原会话无法唯一定位、必要原文缺失、相关 agent 在途或状态未知、实际执行或交付不明、原授权不清或审批待处理时，只停依赖步骤并报告缺口。待审批沿原请求处理，确需的新审批经实际审批入口办妥后再执行相关步骤。例如，原主会话收到 HTTP 503，确认无 active turn、无待审批且本任务无相关在途操作后，新主会话可根据当前工作区及原会话必要记录完成仍获授权的未答事项。

<!-- END paseo-resume -->

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

# paseo 叠加适配

分支：paseo-dispatch、paseo-resume。触发见 `luno-platform`〈运行端〉。两分支共读本节；其余槽位仍按 `references/runtime-codex.md` 与 `references/runtime-host.md`。义务、授权和停止条件以引用处为准。

## 共同前置

**审批**：以 Paseo 可核验的父子关系确认派单来源。需要审批或授权来源无法核实时，经对应 daemon 的官方入口或手机端处理原请求。Paseo 0.16.2 的 `list_pending_permissions`、`respond_to_permission` 只作用于调用方 daemon，没有 `serverId`；按已定位的目标 agent 核对请求，无法在对应 daemon 核实或处理时，暂停依赖步骤。转述的批准和外发动作通过自动审批均不代替该会话的权限审批。

<a id="branch-paseo-dispatch"></a>
<!-- BEGIN paseo-dispatch -->
## 派发通道

- Paseo 主会话和独立 Codex CLI 的所有委派（含通用兜底）按用户偏好默认使用已核验的 **Paseo agent 通道**。是否需要派发、角色归属和独立资格按 `luno-core/references/review.md`〔分支 delegation〕。只有用户明确指定才使用 Codex 原生 LENS/FORGE，按 `references/runtime-codex.md`〈派发通道〉核验。使用 Paseo 前按运行元数据核实会话归属、目标 daemon 和派发所需的父子关系。归属不明或无已核通道时，只停依赖该派发的步骤并报告缺口。被派发的子代理不得继续委派。
- **角色 provider**：以当前官方 provider 配置解析出的实际启动程序、家目录及指令来源确认角色，不维护 provider ID、显示名或上游名称白名单。角色家目录独立于主会话（Codex 用 `CODEX_HOME`），其常驻提示词须为已登记的 `subagents/` 对应角色原文，不含 LUNO 常驻提示词和 GLOBAL；登记路径不要求与 provider ID 同名。配置样例见仓库 `platforms/paseo/config.example.json`，其中 ID、标签和初值是可编辑配置，不是派发规则。需登录的鉴权方式由用户分别登录；环境变量 `env_key` 方式沿用当次授权注入，不复制凭据；安装器不读取、不复制凭据或登录态，也不预置权限配置，沙箱和审批按 paseo 中该 provider 的模式与 provider 默认设置。
- **选择当前 Profile**：每次新派发用官方 `list_profiles` 读取当前值，不缓存路由或参数。Codex 的 `notes` 用 JSON 字符串 `{"role":"LUNO","upstream":"<不透明上游标识>"}` 声明，`role` 只取 `LUNO`、`LENS` 或 `FORGE`，`upstream` 由配置声明。以主会话运行元数据中的 provider ID 唯一定位主 Profile；官方明确返回选用的 Profile ID 时按该 ID 核对。只选同 `upstream`、所需 `role` 的唯一当前 Profile，不按名称、标签、前缀或列表顺序选。Profile 的 `provider` 须精确等于已核目标 provider ID；声明须与实际启动参数、`CODEX_HOME`、生效 `model_provider` 及角色指令来源相符，启动覆盖值优先于共享 home 默认值。provider ID 变动时更新相应引用；声明、引用、上游、启动来源或改变启动值的选项变化后重核。声明和参数不授予权限。缺读取通道、无匹配、多义、身份冲突或关联无法核实时停止该次派发并报告，不跨上游或换模型兜底。
- **传入 Profile 参数**：Paseo 0.16.2 的 `create_agent` 无 profile 参数。将 `provider` 和 `model` 拼成 `<provider>/<model>`；将 `thinkingOptionId`、`modeId`、`options` 分别传入 `settings.thinkingOptionId`、`settings.modeId`、`settings.features`。未设 `model` 时按官方模型目录解析默认模型，解析不出则停该项。仍接受 `featureValues` 的版本，按 `{...featureValues, ...options}` 合并成 `features`，同键以 `options` 为准。未设置的思考强度及选项沿用 provider 默认，不合成空值或空对象；显式空对象按原语义传递。模式见下一条，参数名和层级以安装版 schema 为准。
- **模式解析**：Profile 显式设置 `modeId` 时，先用目标 `inspect_provider.modes[].id` 等官方支持模式字段验证，再原样传入 `settings.modeId`，不改值。Profile 未设置时，同 provider ID 沿用官方继承；跨 provider ID（即使同为 `extends codex`）须查询目标当前模式：官方明确返回空模式列表才省略，列表未知不算无模式；有模式则从官方客户端 `providers.snapshot({cwd})` 返回的 `entries` 中，精确匹配目标 `provider` 且 `enabled=true`、`status="ready"` 的条目，读取 `defaultModeId`，验证其属于该条目的 `modes[].id` 后显式传入 `settings.modeId`。paseo 0.16.2 的 `inspect_provider` 只返回 `modes`，不返回默认模式；不能从列表首项、母会话模式或静态 manifest 猜默认。官方读取面不可用、默认值为空或不受支持时，停止该次派发，说明需用户明确选择受支持模式，不自动修改 Profile 或自建 fallback。官方默认不构成权限授权；所选模式（含显式值）的实际沙箱、审批及 provider 选项不得扩大父权限或绕过审批，无法核清或需要新授权时停止相关派发并交回，不自动改为 unattended。
- **派单**：实施类先用 `create_workspace` 以 worktree 隔离从基线分出任务分支。用 `create_agent` 创建角色，`notifyOnFinish` 为真。需要用 `initialPrompt` 建立待核验的会话时，只给不含私有材料、不要求读写的启动探针。取得下述启动证据后，向已核验的同一会话派单。参数名以工具当前 schema 为准。
- 编排工具的相应入口不可用时，可以采用**等价的官方 CLI**，前提是能证明 CLI 读取的是目标 daemon 生效的同一 Profile，且派发入口能完整传递本次所需字段并满足上述工作区隔离、启动核验和同一会话投递要求。通过官方接口取值，不直接解析配置文件。Paseo 0.16.2（2026-11-21 核对固定源码 `2ee30f4164af42ba209236ab3a31bf9532592fc3`）的 `daemon config get` 调用 `readPersistedConfig`，其输出单独不足以证明 daemon 生效值。同版 `agent run` 调用 `createAgent` 时不传 `settings.features` 对应的值，凡需传该字段（包括显式 `{}` 或旧字段合并后应传的值），该命令均不适用。该字段按缺省应省略且其余等价条件满足时，可用 `agent run` 的 `--provider`、`--thinking`、`--mode` 传相应的已核值，需显式传入的模式不得省略，初始 prompt 只给启动探针，按同一 agent ID 和派发时限核实完成状态。调用发出后失败或状态未知时，先核实际状态并按下述恢复规则处理，避免换通道重复派发。
- **daemon 范围**：Paseo 0.16.2 的 `list_profiles`、`cancel_agent` 和 provider 查询作用于调用方 daemon，没有 `serverId`。跨宿主时须用目标 daemon 上已核实的官方入口；查询和投递支持 `serverId` 的工具按同一服务器及 agent ID 使用。目标无已核入口时只停依赖操作，报告通道缺口，不以本机结果代替目标或据此判定产品不支持。
- **时限**：paseo 不设平台上限，负责人为每次派发设定时限。超时先用 `get_agent_status` 核真实状态，未确认终止就不重派同一写任务；取消用 `cancel_agent`。
- **断流或不透明回包**：派发返回 `stream disconnected before completion`、`Required opaque-content summary was unavailable` 或等价的不完整回包时，完成状态视为未知。先唯一定位原 agent 及其服务器，再用 `get_agent_status` 与 `get_agent_activity` 核对运行状态、active turn 和待处理审批，并从任务工作副本、Git 或 PR、已改目标核清实际执行和交付。创建结果无法定位、活动摘要为空或交付仍不明时，均不得据此自动重建会话或重派任务。审批待处理时只按〈共同前置〉跟进原请求。已完成的任务只核验或回传。向原 agent 续派或另建角色会话接续前，均须确认原授权仍适用、无待处理审批，并办妥确需的新审批。只有确认原 agent 空闲、执行与交付已核清、确有剩余步骤且能避免投递竞态，才向原 agent 发 `steer`。投递期间若出现新轮次，`steer` 无法加入时可能退化为 `interrupt`，发送前的空闲快照无法保证投递时仍空闲。确认原会话无法恢复、执行与交付已核清且无在途任务后，方可按现有派单规则新建角色会话，只承接已核实且仍获授权的剩余步骤，并重新核验角色、模型、上游和授权。正式独立审查的恢复与重试按 `luno-core/references/review.md`〔分支 review〕执行。
- **追问或续派**：`send_agent_prompt`，`activeTurnBehavior` 取 `steer`。
- **身份核验**：`get_agent_status` 或 `list_agents` 的 provider ID 须绑定到已核实的实际角色和上游。非 Codex 角色沿用各自已核实的运行入口，核对实际 provider、模型和角色指令来源。Codex 由宿主侧从实际线程启动或恢复响应读取 `instructionSources` 和生效的 `modelProvider`，核对角色家目录入口、登记角色原文及 `AGENTS.override.md` 遮蔽。使用带角色核验能力的 Paseo 时，从 `get_agent_status` 的 `snapshot.runtimeInfo.extra.codexRoleVerification` 核对 `roleMatches=true`、`overrideExists=false`、`upstreamMatches=true`，将 `resolvedModel` 和 Profile 的模型或本次解析出的默认模型比对。状态表里的配置模型、角色自述和启动探针答复不能代替这些证据。按实际线程记证据，启动参数、上游、模型、home 或指令来源变动时重核；证据缺失或不一致时报告「通道身份未验证」，停止正式派发。私人正文与绝对路径留在宿主侧。家目录分离不构成操作系统或数据访问隔离，项目指令及权限仍须按实际加载核验。

Profile 与派发接口按 Paseo 0.16.2 的公开类型及工具注册代码核对，说明见 https://paseo.sh/docs/agent-profiles。同上游选择是本地约定。
<!-- END paseo-dispatch -->

<a id="branch-paseo-resume"></a>
<!-- BEGIN paseo-resume -->
## 主会话接续

主会话自身遇到断流、必要的不透明摘要缺失或回包不完整时，按 `luno-core/references/handoff.md`〈恢复时〉核对任务版本、原授权、实际执行状态和验收缺口。

新主会话在获准接续时，通过交接给出的 agent ID 或获准查看的 Paseo 工作区会话列表，按当前任务与工作区唯一定位原主会话及其服务器。按 `luno-core/references/handoff.md`〈恢复时〉，只在获准的消息范围内回读必要的用户指令、交接、审批原证和交付记录，核对任务版本及原授权是否仍适用。用 `get_agent_status` 和 `get_agent_activity` 核对原主会话及本任务相关 agent 的运行状态和 active turn，按〈共同前置〉核对待处理请求。用已授权的任务工作副本、Git、PR 或已改目标核实实际执行、已有交付和剩余步骤。只继续已核实且仍获授权的剩余工作。对已完成的写入，核验符合要求即可。遇部分写入，核清实际状态后只处理仍获授权的缺口，必要时按原恢复规则处置。已有交付按需回传。

原会话无法唯一定位、必要原文缺失、相关 agent 在途或状态未知、实际执行或交付不明、原授权不清或审批待处理时，只停依赖步骤并报告缺口。待审批沿原请求处理，确需的新审批经实际审批入口办妥后再执行相关步骤。例如，原主会话收到 HTTP 503，确认无 active turn、无待审批且本任务无相关在途操作后，新主会话可根据当前工作区及原会话必要记录完成仍获授权的未答事项。

<!-- END paseo-resume -->

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

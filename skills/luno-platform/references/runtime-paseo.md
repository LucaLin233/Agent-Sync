# paseo 叠加适配

当前端为 Claude Code 或 Codex，且会话可用 paseo 编排工具（如 `create_agent`）或存在指定变量 `PASEO_AGENT_ID` 时，另读本资源。它只补跨会话、跨 provider 的派发；其余槽位仍按 `references/runtime-claude-code.md` 或 `references/runtime-codex.md` 与 `references/runtime-host.md`。义务、授权和停止条件以引用处为准，本资源不新增或放宽权限。

## 派发通道

- **角色 provider**：以当前官方 provider 配置解析出的实际启动程序、家目录及指令来源确认角色，不维护 provider ID、显示名或上游名称白名单。角色家目录独立于主会话（Claude Code 用 `CLAUDE_CONFIG_DIR`，Codex 用 `CODEX_HOME`），其常驻提示词须为已登记的 `subagents/` 对应角色原文，不含 LUNO 常驻提示词和 GLOBAL；登记路径不要求与 provider ID 同名。配置样例见仓库 `platforms/paseo/config.example.json`，其中 ID、标签和初值是可编辑配置，不是派发规则。需登录的鉴权方式由用户分别登录；环境变量 `env_key` 方式沿用当次授权注入，不复制凭据；安装器不读取、不复制凭据或登录态，也不预置权限配置，沙箱和审批按 paseo 中该 provider 的模式与 provider 默认设置。
- **同上游选择**：Codex 入口使用当前 Profile 的 `notes` 保存一份路由声明，格式为 JSON 字符串 `{"role":"LUNO","upstream":"<不透明上游标识>"}`；`role` 只取 `LUNO`、`LENS` 或 `FORGE`，`upstream` 由当前配置声明，不维护上游名单。声明只用于选择候选，不是身份或权限证明；采用前须核其与实际 provider 的启动参数、`CODEX_HOME`、有效 `model_provider` 连接声明及角色指令来源一致，共享 home 的默认值不代替启动覆盖值。每次派发先以主会话运行元数据中的实际 provider ID 找到当前唯一匹配的主 Profile，再读取其声明；只选择 `upstream` 相同、`role` 为所需角色的当前唯一 Profile。官方运行面明确给出选用的 Profile ID 时按该 ID 核对，不按显示名、前缀或列表顺序挑选。声明、引用或实际启动来源变化后须重核；缺失、多义、声明与真实身份冲突或无法核实关联时停止该次派发并报告，不跨上游或换模型 fallback。Claude Code 等其他 provider 沿用已核角色通道，不套用 Codex 上游声明语义。
- **按当前 Profile 派发**：模型、思考强度、mode 与 provider 选项由主会话在**每次新派发时**从当前 Profile 读取，不在指令、脚本或记忆里缓存或写死。paseo 0.16.2 已核：编排工具 `list_profiles` 返回已配置的 Profile（`id`、`name`、`provider`、`model`、`modeId`、`thinkingOptionId`、`options`、`notes`），而 `create_agent` **没有** profile 参数：取该 Profile 的 `provider` 与 `model` 组成 `provider` 的 `<provider>/<model>`，把 `thinkingOptionId`、`modeId`、`options` 分别放进 `settings.thinkingOptionId`、`settings.modeId`、`settings.features`。Profile 未设置 `model` 时，按官方 provider 模型目录解析当前默认模型再拼，解析不出就停该项，不用空值或 `undefined` 拼路径。字段名与层级以工具当前 schema 为准，不按旧样例写死；安装版仍接受旧字段 `featureValues` 时，按 `{...featureValues, ...options}` 按键合并（同名项以 `options` 覆盖，旧字段独有键保留），不漏旧字段；后续版本以当时 schema 为准。
- **Profile 与角色身份绑定**：Profile 的 `provider` 必须精确等于上述核实的目标 provider ID；Profile 名称、`notes`、标签及其前缀均不证明角色或上游身份。改名不改变身份，换模型不改变角色；更换 provider ID 时须同步更新引用并重新核验。模型、`thinkingOptionId`、`modeId` 和 `options` 可由用户在 UI 改成任意受支持值，但不改变本资源的授权、审批与权限边界。选项若改变实际启动配置或上游，须据其生效值重核，不能仅凭 Profile 的 provider 字段放行。
- **读取通道与停止条件**：当前 Profile 的读取通道可以是官方编排工具（`list_profiles`），也可以是已确认等价的官方 CLI 读取同一当前 Profile；两者择可用者，取值来自同一配置，不另存副本。当两条 Profile 读取通道都不可用、没有匹配该角色的 Profile、Profile 的 provider 与角色身份不符，或前述默认模型解析不出时，停止该次派发并报告缺口，不静默改用原生 roles、通用子代理或写死模型。`model`、`modeId`、`options`、`thinkingOptionId` 未设置属于官方允许的可选缺省，按 provider 默认继续，不当作缺失阻塞；未设置时不合成空值或空对象，用户显式给出的值（含显式空对象）按其语义原样传递。
- **派单**：`create_agent`，`initialPrompt` 为派单，`notifyOnFinish` 为真；实施类先用 `create_workspace` 以 worktree 隔离从基线分出任务分支。参数名以工具当前 schema 为准。
- **CLI 兜底同一口径**：编排工具未注入时用 CLI，但同样先经官方配置读取接口取当前 Profile（不解析 Paseo 配置文件），再按 `provider`、`model`、`thinking`、`mode` 与 provider 选项传参（如 `paseo agent run --provider <provider>/<model> --thinking <id> --mode <id>`，等待用 `paseo wait <id> --timeout <秒>`），不得绕开 Profile 传固定模型；派发调用已发出但失败或状态未知时，先用状态接口核真实状态，不盲目换另一读取通道重派。
- **安装版没有任何受支持的 Profile 读取/派发路径时**：报告版本或配置缺口，不声称已按 Profile 派发，也不以临时改动顶替；单个编排工具未注入只说明该通道不可用，不等于产品不支持 Profile。
- **作用范围**：以上只作用于 Paseo 主会话。普通 Claude Code 与 Codex CLI 的原生角色注册和模型不变；被派发的子代理仍不得继续委派。
- **时限**：paseo 不设平台上限，负责人为每次派发设定时限。超时先用 `get_agent_status` 核真实状态，未确认终止就不重派同一写任务；取消用 `cancel_agent`。
- **追问或续派**：`send_agent_prompt`，`activeTurnBehavior` 取 `steer`。
- **身份核验**：`get_agent_status` 或 `list_agents` 返回的 provider ID 是实际通道标识，须与已核实的角色来源绑定后才构成角色证据，不把 ID 本身当角色。模型取同一返回的模型字段，记入回包和 PR；按 Profile 派发时，Profile 明确设置了 `model` 则返回模型须等于该值，未设置则对照本次按官方 provider 模型目录解析出的默认模型，不一致按「通道身份未验证」处理。首次使用某个角色 provider，以及其启动参数、home 或指令来源改变后，另核对其加载来源确为该家目录中的角色文件（Codex 为线程启动返回的 `instructionSources`），并核没有 LUNO/GLOBAL 注入或 `AGENTS.override.md` 遮蔽；核清前按「通道身份未验证」处理。家目录分离不构成操作系统或数据访问隔离，项目指令及权限仍须按实际加载核验。
- **审批**：子会话的权限请求经 `list_pending_permissions`、`respond_to_permission` 或手机端处理，仍按原授权判断，不因请求来自 paseo 而放宽。

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。Profile 与派发契约按 paseo 0.16.2 安装包内公开类型和工具注册代码核对（`list_profiles`、`create_agent` 的 `settings`、daemon 配置的 `agentProfiles`）；说明性文档见 https://paseo.sh/docs/agent-profiles，网页更新不作为实装依据。同上游选择是本地约定，不声称 Paseo 内建按角色或上游自动路由。

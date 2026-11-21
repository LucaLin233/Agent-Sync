# Codex 端运行适配

本资源是 `luno-platform` 入口〈运行端〉在 Codex 端的槽位取值，与 `references/runtime-host.md` 合用；Paseo 派发与接续按 `luno-platform`〈运行端〉读对应分支。义务、授权和停止条件以引用处为准，本资源只给本端的机制和取值，不新增或放宽权限。

本端全局常驻提示词位于实际 `$CODEX_HOME/AGENTS.md`（未设置 CODEX_HOME 时默认 `~/.codex/AGENTS.md`），默认由安装器把 `prompt/LUNO.md` 原文、一个 LF 和本端 GLOBAL 私人副本原文拼接生成；GLOBAL 副本更新后须重新生成。显式 opt-in `--ends codex --codex-global-source paseo-append-system-prompt` 时，`AGENTS.md` 只等于 `prompt/LUNO.md` 原文，GLOBAL 由 Paseo daemon 的私人配置 `daemon.appendSystemPrompt` 提供；安装器不读写该配置，设置与生成文件须在同一受控窗口切换并回读。该来源是 daemon 范围，覆盖同一 daemon 启动的所有 agent（LUNO、LENS、FORGE 及其他），不做 provider 级过滤；授权、切换、回读及全部接收端的新会话验收按 `luno-core/references/sync.md`〔分支 sync-host〕。角色 home 的 `AGENTS.md` 仍仅角色正文，运行时另收这段提示词；原生 CLI 不经该 daemon，不直接获得它。`AGENTS.override.md` 优先于同目录的 `AGENTS.md`，存在时停止受管安装，不覆盖它。项目级指令另按 Codex 官方发现规则加载；文件一致不证明未被遮蔽、完整注入或实际行为一致。

## 原生安装与技能发现

Codex CLI 0.170.0 的用户技能根包括实际 HOME 下的 `.agents/skills`，另保留已弃用的 `$CODEX_HOME/skills` 兼容根；设置 CODEX_HOME 不会把前者一起搬走。当前版本源码支持用户技能目录软链。原生安装须先选定并核实实际加载入口，不能只按安装器输出推定；其他版本或配置变化须重核。

安装器默认处理 `codex` 和 `paseo` 两端。只选 Codex 时用 `--ends codex`；`--home` 指定受管安装根，不能冒充 Codex 的 HOME。显式指定 `--codex-home` 时，仅在 Codex 单端模式下，把登记的 Codex 全局指令和用户技能入口重定位到该目录的 `AGENTS.md`、`skills/<技能名>`，采用上述 0.170.0 兼容根；该目录须位于安装根内。此模式不改 HOME、不建根外链接、不安装或迁移 paseo、角色家目录、会话、登录态、秘密、审批或沙箱配置。兼容根已弃用，不承诺未来版本；需要改 HOME 或采用其他根时另定明确方案，不自动改公共入口。

官方依据（2026-11-19 核对）：[全局指令发现](https://learn.chatgpt.com/docs/agent-configuration/agents-md)；[0.170.0 技能根源码](https://github.com/openai/codex/blob/29eb79e9866b3262a777fdf8195c1b9e63684c91/codex-rs/ext/skills/src/host_roots.rs)；[同版软链策略](https://github.com/openai/codex/blob/29eb79e9866b3262a777fdf8195c1b9e63684c91/codex-rs/ext/skills/src/loader/host.rs)。

## 原生运行与观察

日常交互优先使用官方 Codex CLI；脚本化非交互任务可用 `codex exec`。`codex app-server` 面向自定义富客户端集成，不是日常运行或原生角色验收的必经层。原生子代理可在 CLI 中用 `/subagents` 观察和切换线程；实际身份及成功判定仍按下文与总控核验。

在非交互流程或无法呈现新审批的运行中，需要新审批的动作会失败并向父流程返回错误；这不等于角色不可用或权限已获批准。

官方依据（2026-11-19 核对）：[CLI](https://learn.chatgpt.com/docs/codex/cli)；[原生子代理](https://learn.chatgpt.com/docs/agent-configuration/subagents?surface=cli)；[App Server](https://learn.chatgpt.com/docs/app-server)。

## 派发通道

- 本端所有委派（含通用兜底）默认按 `references/runtime-paseo.md`〔分支 paseo-dispatch〕使用已核验的 Paseo 通道。独立 Codex CLI 使用 Paseo CLI 前须有明确获准的目标。无已核验通道时，只停依赖派发的步骤并报告。只有用户明确指定才使用 Codex 原生 LENS/FORGE。
- Codex CLI 0.170.0 支持通过 `[agents.<角色名>]` 的 `config_file` 注册原生角色，并由角色文件中的 `developer_instructions` 指定 LENS 或 FORGE。只有在当次授权内完成配置、必要审查及实际角色和模型元数据核验后，才能把它作为相应角色通道采用；原文资源存在、角色说明、昵称和自述都不算注册或运行成功。未注册、不可用或身份不可核时，仍按 `luno-core/references/review.md`〔分支 delegation〕〈任务归属〉停止依赖任务并报告；已获准且可用的 paseo 角色通道保留原用途，不自动迁移。
- 原生子代理保留父会话的 AGENTS 指令及其权限上下文；角色 developer instructions 可以覆盖角色身份指令，但不删除、隐藏父提示词或私人内容，也不构成操作系统、凭据或数据隔离。子代理继承父当前 provider、审批、沙箱及 MCP 配置，角色配置不得扩大父权限或绕过审批。角色可按明确授权分别指定模型和思考强度；不得将配置值冒充实际运行模型，其他版本须重新核证。
- 平台不设单次或累计时限，负责人为每次派发设定时限。
- 会话内通用子代理的身份核验：以线程元数据 `agentRole`、线程 ID 和父线程为运行元数据，模型以线程启动返回的解析结果为准；昵称和自述都不算。

## 提示词资源与 MCP

主 LUNO 提示词可先按上述规则生成、离线回读；LENS、FORGE 原文随已合并受管检出的 `subagents/` 保留为可读资源，不因此启用角色或取得派发资格。没有可核的角色通道时，需要相应角色的任务仍按总控停止并报告，不用自述、会话内改名或通用子代理冒充。不得把已有提示词文件报告成角色调用成功。

含 GLOBAL 的生成物用于所选 Codex 主会话的常驻入口。Paseo 角色家目录与 Codex 原生角色文件沿用各自登记的角色指令，不拼入 GLOBAL。原生子代理从父会话继承的指令按〈派发通道〉核对。

实际加载只在获准的真实 Codex 主会话新建场景中核验。原生 CLI 按实际运行用户和 `CODEX_HOME` 核入口，Paseo 按主会话实际 provider 的启动入口和家目录核入口。结合该新会话的实际 Codex 版本与工作目录，按上述官方指令发现规则核对用户级和适用的项目级指令链、`AGENTS.override.md`、指令优先级与截断。用该会话的启动或实际加载证据确认已离线回读的生成内容完整纳入有效指令。影响预期内容的遮蔽或截断据实报告。只看到文件判等或来源路径，或因其他原因无法确认有效加载范围时，报「实际加载未验证」。结论限于该新会话，旧线程是否重读单凭文件更新无法判定。只报核验状态，不展示私人正文。

MCP 的非秘密配置可在当次授权内按目标支持的现有接口预置；服务各自的凭据须另按指定变量授权与注入，不存在由模型凭据统一替代的约定。模型凭据、MCP 凭据与管理、SSH、GitHub 凭据用途分开，不能互换或自行补取。缺 MCP 凭据只停止对应连接或调用，不阻塞不依赖它的提示词安装与离线回读；配置存在不证明连通或可用。本资源不固定服务清单，不自动复制秘密或现有保存态。

## 通用兜底

其余任务默认自办。只有用户明确授权使用 Codex 内置的默认子代理时才可调用，并按〈派发通道〉核对主体。它继承父会话的权限，不另设只读边界。

## 文件编辑

宿主 MEMORY 新增按 `references/runtime-host.md`〈记忆入口〉走末尾追加。其他文件编辑用 `apply_patch`，补丁上下文须唯一匹配，写后按 core 回读全部目标。

## 截断与压缩

- 上下文接近上限时 Codex 自动压缩；压缩后按 `luno-core/references/handoff.md`〈恢复时〉重读必要规则原文，不以摘要代替。
- 批次间收口时，提示用户可以在批次之间执行 `/compact`；是否压缩由用户决定，不自动执行，不改自动压缩设置。

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

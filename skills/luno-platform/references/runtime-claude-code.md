# Claude Code 端运行适配

本资源是 `luno-platform` 入口〈运行端〉在 Claude Code 端的槽位取值，与 `references/runtime-host.md` 合用；会话由 paseo 启动时另叠加 `references/runtime-paseo.md`。义务、授权和停止条件以引用处为准，本资源只给本端的机制和取值，不新增或放宽权限。

本端载体由安装器生成：常驻提示词 `~/.claude/CLAUDE.md` 只含导入 `prompt/LUNO.md` 与 `~/.luno/memory/GLOBAL.md` 的两行；LENS、FORGE 为 `~/.claude/agents/lens.md`、`forge.md`，frontmatter 预加载 `luno-core` 并不注入常驻提示词，正文与 `subagents/` 原文逐字节相同。

## 派发通道

- 会话内派发用 Agent 工具，`subagent_type` 取 `lens` 或 `forge`。受派方启动即注入完整 `luno-core`，不带常驻 LUNO 提示词与 GLOBAL。
- 平台不设单次或累计时限。负责人为每次派发设定时限，用前台调用等待结果；后台派发只在明确不依赖其结果时使用，不当作已等待。
- 身份核验：以工具返回的子代理类型和 agentId 为运行元数据，模型组以会话可见的模型设置为准；只有角色自述或缺这两项时，按「通道身份未验证」处理。
- 派给另一 provider（如 Codex）时按 `references/runtime-paseo.md`。

## 通用兜底

其余任务在 LENS、FORGE 不可用时，可以明确改用内置 general-purpose 子代理并核对主体。

## 文件编辑

- Edit 先完整 Read 目标文件，再按唯一的精确旧串替换；旧串不唯一就扩大上下文，不用全部替换规避逐处核对。Write 覆盖整个文件，只用于新建或已确认的整份替换。
- Read 单次返回有行数和长度上限，被截断时按偏移分块补齐，截断部分不算已读。

## 截断与压缩

- 上下文接近上限时 Claude Code 自动压缩；压缩后已调用的技能只保留开头部分，按 `luno-core/references/handoff.md`〈恢复时〉重读必要规则原文，不以摘要代替。
- 批次间收口时，提示用户可以在批次之间执行 `/compact`；是否压缩由用户决定，不自动执行，不改自动压缩设置。

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

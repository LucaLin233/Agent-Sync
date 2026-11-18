# Codex 端运行适配

本资源是 `luno-platform` 入口〈运行端〉在 Codex 端的槽位取值，与 `references/runtime-host.md` 合用；会话由 paseo 启动时另叠加 `references/runtime-paseo.md`。义务、授权和停止条件以引用处为准，本资源只给本端的机制和取值，不新增或放宽权限。

本端常驻提示词 `~/.codex/AGENTS.md` 由安装器生成，是 `prompt/LUNO.md` 原文与 `~/.luno/memory/GLOBAL.md` 原文的拼接；GLOBAL 副本更新后须重新生成。

## 派发通道

- 本端不安装 LENS、FORGE 的会话内自定义 agent：Codex 子代理继承父会话的常驻 `AGENTS.md`（即 LUNO）和沙箱、审批设置，做不到角色隔离。需要 LENS 或 FORGE 时按 `references/runtime-paseo.md` 经 paseo 角色 provider 派发；不在 paseo 中运行时，按 `luno-core/references/review.md`〔分支 delegation〕〈任务归属〉报告角色不可用。
- 平台不设单次或累计时限，负责人为每次派发设定时限。
- 会话内通用子代理的身份核验：以线程元数据 `agentRole`、线程 ID 和父线程为运行元数据，模型以线程启动返回的解析结果为准；昵称和自述都不算。

## 通用兜底

其余任务可以明确改用 Codex 内置的默认子代理并核对主体；它继承父会话的权限，不另设只读边界。

## 文件编辑

用 `apply_patch` 修改文件，补丁上下文须唯一匹配；写后按 core 回读全部目标。

## 截断与压缩

- 上下文接近上限时 Codex 自动压缩；压缩后按 `luno-core/references/handoff.md`〈恢复时〉重读必要规则原文，不以摘要代替。
- 批次间收口时，提示用户可以在批次之间执行 `/compact`；是否压缩由用户决定，不自动执行，不改自动压缩设置。

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

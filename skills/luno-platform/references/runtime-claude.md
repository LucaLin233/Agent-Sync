# Claude Code 端运行适配

本资源是 `luno-platform` 入口〈运行端〉在 Claude Code 宿主端的槽位取值，与 `references/runtime-host.md` 合用；Paseo 的派发、操作与接续按〈运行端〉读 `references/runtime-paseo.md` 对应分支。同一槽位两处都写时以本资源为准。义务、授权和停止条件以引用处为准，本资源只给本端的机制和取值，不新增或放宽权限。

## 常驻提示词与技能

本端常驻提示词位于实际 `$CLAUDE_CONFIG_DIR/CLAUDE.md`（未设置时默认 `~/.claude/CLAUDE.md`）。它由安装器以 `--ends claude --claude-home <CLAUDE_CONFIG_DIR>` 登记渲染：renderer `claude-main` 把角色启动段与 `prompt/LUNO.md` 生成到安装根的受管生成目录，再在该处建公开软链。首条任务的角色选择在 LUNO 职责段之前生效。GLOBAL 不进入生成文件，由 Paseo daemon 的私人配置 `daemon.appendSystemPrompt` 提供，只覆盖该 daemon 启动的会话；原生 Claude Code 不经该 daemon，不直接获得它。项目级 `CLAUDE.md` 与企业级指令另按 Claude Code 官方发现规则加载；文件一致不证明未被遮蔽或实际加载。

用户技能根是 `$CLAUDE_CONFIG_DIR/skills/<技能名>`，安装器把它们软链到受管检出 `skills/<技能名>/`。Claude Code 2.1.332 在设置 `CLAUDE_CONFIG_DIR` 后只从该目录加载个人技能，不再读取 HOME 下的 `.claude/skills`；版本变化须重核。`claude` 端是可选端，默认安装不处理，只有显式选择并给出安装根内的配置目录才启用；`--ends` 须只含 `claude`，不与 Codex 端同次执行。

Paseo daemon、其启动的会话与手工运行的包装脚本必须使用同一个 `CLAUDE_CONFIG_DIR`，否则会话转录的位置与 daemon 查找的位置不一致。切换配置目录前先停止相关会话。

## 记忆边界

Claude Code 的自动记忆（`autoMemoryDirectory` 所指目录）只保存用户偏好与反馈，不作为 LUNO 记忆：不往里写 LUNO 经验，也不据此采用经验。LUNO 共用经验日志的位置、授权与写法见 `references/runtime-host.md`〈记忆入口〉。自动压缩等 Claude Code 自身设置属于用户配置，不由规则安装器管理或改写。

## 派发通道

本端的委派按 `references/runtime-paseo.md`〔分支 paseo-dispatch〕使用已核验的 Paseo 通道；独立 Claude Code 使用 Paseo CLI 前须有明确获准的目标，无已核验通道时只停依赖派发的步骤并报告。Claude 角色须先核实其启动入口能识别首条任务的角色行并加载对应受管原文，取得等效运行证据前不正式采纳，不从 Codex 的启动规则推定。

## 截断与压缩

上下文接近上限时 Claude Code 自动压缩；压缩后按 `luno-core/references/handoff.md`〈恢复时〉重读必要规则原文，不以摘要代替。批次间收口时可提示用户执行 `/compact`；是否压缩由用户决定，不自动执行，不改自动压缩设置。

## 文件编辑

宿主经验日志的新增按 `references/runtime-host.md`〈记忆入口〉执行：既有文件末尾追加，首次按日文件排他创建。其他文件按本端编辑工具修改，改前先读取，写后回读全部目标。

来源与许可：自编本端适配；取值依据 Claude Code 2.1.332 的实测行为（2026-11-26），不转载上游正文。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

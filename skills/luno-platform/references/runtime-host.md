# 宿主端运行适配（Claude Code、Codex 共用）

本资源是 `luno-platform` 入口〈运行端〉在宿主端的共用槽位取值。宿主端指用 `tools/link-install.py` 安装了本仓库提示词与技能的 Debian 主机，Claude Code 与 Codex 都在其上运行，可由 paseo 托管。只在当前端为 Claude Code 或 Codex 时读取，并与 `references/runtime-claude-code.md` 或 `references/runtime-codex.md` 合用，同一槽位两处都写时以后者为准。义务、授权和停止条件以引用处为准，本资源只给本端的机制和取值，不新增或放宽权限。

## 临时目录

含秘密的临时文件用 `mktemp -d` 在 `/tmp` 下创建独占目录（700），文件 600，用完即删，并满足 `luno-core/references/execution.md`〔分支 writing-safety〕中「`/tmp` 默认范围」一条的创建、清理和核验条件；不放进受管检出、paseo worktree 或其他会被提交、同步的目录。

## 执行环境

- 本端执行环境是宿主 Debian 的原生 Linux；Claude Code 与 Codex 各自的沙箱和审批设置按其运行端资源。来源可信、入口及依赖已静态核对的测试可以把宿主当作原生执行环境。
- Docker、systemd 可用于测试隔离，前提和限制按 `luno-ops` 入口〈安全与测试〉。宿主同时运行生产服务时，重测试和 Docker 测试不落在宿主上，另选隔离环境。
- 并行执行在宿主上的收益没有验证过，不作推荐手段。

## 秘密注入

秘密由宿主环境或 paseo provider 的 `env` 注入运行会话。缺失时报告变量名，请用户在宿主上设置（例如写入启动 paseo daemon 的服务环境），不提供在聊天里粘贴的入口。paseo 的 `config.json` 是明文，只放非秘密值。

## 技能根

Claude Code 为 `~/.claude/skills/<技能名>/`（paseo 的 Claude Code 角色家目录为 `~/.luno/homes/<角色 provider>/skills/<技能名>/`），Codex 为 `~/.agents/skills/<技能名>/`；都是指向受管检出 `skills/<技能名>/` 的软链。

## 工作副本

- 受管检出是 `~/.luno/agent-sync`：只由收口者在干净状态下快进到已合并的 main，供软链和安装器使用，不在其中编辑。
- 候选在 paseo 为任务创建的 worktree 或独立 clone 中编辑：一个任务一个分支、一个写入者，不写受管检出或共享集成副本。

## 远端工作目录

**宿主端登录的其他主机**：过程产物（脚本草稿和被测副本、夹具、日志、克隆副本、样本、临时快照）统一放在 `/root/workdir/host/<项目>/`，根目录不存在就 `install -d -m 700 /root/workdir/host`。**项目目录按任务对象命名，同一对象始终复用，不在 `/root` 顶层散落文件。**目录 700、文件 600；保留结论性产物。

## 连接清单

SSH 主机清单和连接约定在 `~/.luno/memory/GLOBAL.md`（Minis `GLOBAL.md` 的单向只读副本）。

## 记忆入口

- `~/.luno/memory/GLOBAL.md`：Minis `/var/minis/memory/GLOBAL.md` 的整份单向只读副本，经安装器生成的常驻提示词在每个主会话注入；AI 不修改。复制与冲突处理按 `luno-core/references/sync.md`〔分支 sync-host〕。
- `~/.luno/memory/MEMORY.md`：宿主端自持的经验日志，Claude Code 与 Codex 共读共写；写法、容量和整理按 `references/memory-common.md`〔分支 maintenance〕，纯检索按〔分支 memory-common〕。
- Claude Code 的 auto memory 和 Codex 的 memories 不作为 LUNO 记忆：不往里写，也不据此采用经验。

## Surge 控制目标

本端没有默认控制目标，也不设置 `SURGE_ALLOW_REMOTE`。Surge 任务在本端只做配置、规则和模块的离线工作；需要操作实例时交回 Minis 端，或由用户为当次任务显式指定可达目标并单独授权。

来源与许可：自编本端适配。完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

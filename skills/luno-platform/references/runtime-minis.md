# Minis 端运行适配

本资源是 `luno-platform` 入口〈运行端〉在 Minis 端（App 内置 iSH/Alpine）的槽位取值。中立规则按〈槽位名〉引用这里；义务、授权和停止条件以引用处为准，本资源只给本端的机制、取值和必读资源，不新增或放宽权限。

## 派发通道

- Minis `subagent_task` 的参数、等待、进度、轮询和回包语义按当前工具定义；本端显式设置 max_minutes，task 只交必需信息，context 只放必要原文，不重复整份派单。
- Minis 单个子代理累计最多 60 分钟，单次 max_minutes 不超过 60。
- 任务下一步或最终交付依赖子代理结果、当前 schema 支持 `wait` 且场景适用时，显式设置 `wait=true`，并以工具返回的实际终态和结果推进后续步骤。上游 OpenMinis 公开源码（固定提交 `1a71df0f381cefde80bf912b723de6f9831bc177`，`src/ios/Agent/Jobs/HelperRunner.swift`）中 `wait` 缺省为 `false`：调用立即返回，结果稍后作为新消息投递父会话。走异步回包时，父会话告知正在等待哪项交付，期间继续可独立推进的工作，收到本端回调后再验收，不把重复查询当等待。
- 排队或已转后台（例如用户新消息使等待模式转为后台）的回执只表示已受理，仍需等本端回调取得结果；回执不代替回包，也不作为重复派单的理由。只看到进度、收到回执、失败、超时或没有回包时，不推进依赖该结果的下一步，按既有 `max_minutes` 上限和超时恢复义务核实实际终态与交付后再接续。
- 装机版本未确认，以上只是上游固定提交的源码行为；实际参数与回包以当前工具 schema 和真实回传为准，不套用 Paseo 的队列机制。

## 通用兜底

其余任务在 Minis 角色不可用时，可以明确改用内置通用执行兜底并核对主体。

## 文件编辑

使用 Minis 文件编辑工具前加载 `references/minis.md`〔分支 minis〕及其完整运行时共同规则。Minis/iSH 上的掩码误改或路径异常，操作或下结论前另读 `references/minis.md`〔分支 minis〕 及其运行时资源。

## 截断与压缩

- Minis 工具结果自动卸载按 `references/minis.md`〔分支 minis-runtime-context〕。
- 批次间收口时提示用户查看输入框用量，在约30%（约300K）时手动压缩；该数值只是用户操作参考，不是助手可估算的余量或平台硬限。容量事件包括收到 App 实际容量提示；不改 App 自动压缩设置，自动压缩只作平台兜底。

## 临时目录

含秘密的临时文件在 Minis/iSH 上一律使用 `/tmp`，用 `mktemp -d` 创建独占目录（700），文件 600，用完即删，并满足 `luno-core/references/execution.md`〔分支 writing-safety〕中「`/tmp` 默认范围」一条的创建、清理和核验条件。

## 执行环境

- 本端执行环境是 Minis iSH/Alpine。来源可信、入口及依赖已静态核对的测试可以把 Minis/iSH 当作原生执行环境。并行执行在 iSH 上的收益没有验证过，不作推荐手段。
- 下列资源属于 `luno-ops`，读取前先完整读该技能入口：
  - Minis 端的执行环境选址、脚本运行或测试、派发选址：`luno-ops/references/execution-environment.md`〔分支 execution-environment〕；纯咨询，或已确定在本机做的静态只读检查不必读。
  - 已选定 OnlyBoxes 之后的调用、会话、依赖和回传：`luno-ops/references/execution-environment.md`〔分支 onlyboxes〕。
  - Minis 本机的 CFST（CloudflareSpeedTest）测速：`luno-ops/references/cfst.md`。

## 秘密注入

环境变量在 Minis「设置 → 环境变量」中设置。需要给出设置入口时，用 `minis://settings/environments?create_key=<变量名>&create_value=` 形式的链接（如 Surge 的 [设置入口](minis://settings/environments?create_key=SURGE_API_KEY&create_value=)）。

## 技能根

技能安装在 `/var/minis/skills/<技能名>/`；例如 `luno-surge` 的脚本在 `/var/minis/skills/luno-surge/scripts/`。

## 工作副本

规则仓库 `LucaLin233/Agent-Sync` 的 Minis 工作副本是 `/var/minis/shared/agent-sync`。

## 远端工作目录

- **Minis 端登录的所有主机**：过程产物（脚本草稿和被测副本、夹具、日志、克隆副本、样本、临时快照）统一放在 `/root/workdir/minis/<项目>/`，根目录不存在就 `install -d -m 700 /root/workdir/minis`。**项目目录按任务对象命名，同一对象始终复用，不在 `/root` 顶层散落文件。**目录 700、文件 600；保留结论性产物。

## 连接清单

SSH 主机清单和连接约定在 Minis 端的 `GLOBAL.md`。

## Surge 控制目标

默认连同机的 Controller 和 HTTP API（脚本默认 `127.0.0.1`）。

来源与许可：自编本端适配。自 `luno-core` 迁入的句子沿用原文件的 MIT 精选改写性质（Copyright (c) 2026 Matt Pocock；Copyright (c) 2026 OpenMinis），完整许可随包见 ../LICENSE.matt-pocock.txt、../LICENSE.openminis.txt；取材登记见仓库 skills-sources.md。

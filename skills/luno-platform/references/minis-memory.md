分支：minis-memory、minis-memory-correction、minis-memory-injection。读法见 luno-core 入口〈加载〉。

<a id="branch-minis-memory"></a>
<!-- BEGIN minis-memory -->
# Minis 记忆读写

本资源仅适用于 Minis；共同规则先完整读取 `references/memory-common.md`〔分支 memory-common〕 及其命中的 maintenance/correction 分支。

## Minis 记忆读写入口

- **用户的既定选择**：用户已明确选定并授权 Minis 两路记忆读写。关闭记忆开关的本意是取消自动注入、保留原有读写。后续会话沿用此约定，不重新选择或逐次确认；仅适用于 Minis，仍受当次授权和下列停止条件约束。
- **先确认开关**：首次记忆操作时确认一次本会话的实际开关，以平台明确状态或用户确认的本会话设置为准；不把 `memory.enabled` 的新会话默认值或工具缺失当成当前状态。开关切换或状态与工具不一致时重判，状态不明先停依赖的操作。
- **开**：日志检索和写入用 `memory_get`/`memory_write`；GLOBAL 仍按既有授权用文件维护，自动注入保持平台原状。
- **关**：仅当用户意图是取消自动注入、保留正常读写时，用 `rg` 和文件工具按需检索、读写 `/var/minis/memory/GLOBAL.md` 及同目录的 `YYYY-MM-DD.md`；不扩到 SOUL、其他文件或其他端。实际停用记忆、撤销授权、平台禁止、权限不足或工具异常都不触发此回退，做不到就停止并报告缺口。
- **两路共同要求**：沿用 `references/memory-common.md` 命中分支的触发、关键词与格式、保密、查重、预算、回读和更正规则，继续主动写入，不改成点名才写或逐次确认；GLOBAL 只在仍有效的明示维护范围内维护。文件检索按主题或日期定位，回读命中条目和必要条件，不全量加载记忆，并如实说明检索范围和未查重部分。写前重读目标（不存在则核实后在授权内新建）；日志新条目带时间戳置顶，原内容保留，不用旧缓存覆盖。遇并发变化或冲突就停写重核，不保证跨会话原子性。写后回读，核对内容、字节数和行数；失败先核实际状态，不盲目重试。

## 检索观测

「多个词须同时命中、排序含时间权重、首条不保证最新或仍有效」是 Minis 上的既有观测（版本未记录），不推广到其他端，也不保证现版本仍然如此。

## 关键词位置

Minis 日志的独立关键词行放在正文前；格式、选词与预算按共同规则。

## 写入前容量

**另核整日容量**：在「按日文件 + 按行截断注入」的端（Minis），先测当天日志的总行数和总字节，判断新增后是否越过截断线（截取规则、来源和核实要求见 `references/minis-memory.md`〔分支 minis-memory-injection〕，须按平台、版本和开关核实）。预测要计入写入工具的包装行，包装规则未知就报告预测缺口，不能用写后回读冒充写前预测；接近或越线时按需读注入规则并报告受影响范围。不用压短单条、填空行或删事实来达标。

来源与许可：mattpocock/skills，MIT 精选改写；Copyright (c) 2026 Matt Pocock；完整许可见 ../LICENSE.matt-pocock.txt，来源登记见仓库 skills-sources.md。
<!-- END minis-memory -->

<a id="branch-minis-memory-correction"></a>
<!-- BEGIN minis-memory-correction -->
# Minis 记忆整理更正后的下一次写入复核

先完整读取 `references/memory-common.md`〔分支 maintenance〕、`references/memory-common.md`〔分支 correction〕 和 `references/minis-memory.md`〔分支 minis-memory〕。

- **当次复核**：Minis 当日日志更正后另核整日目标条目数和内容，确认已删断言没有回流。
- **下次写入时复核**：Minis 日志经授权直接整理或更正后，下一次获授权的写入完成时，回读此前受影响的日志文件，按文件日期、节标题和可识别短语核对目标条目数和最终内容，确认已删或改写的旧版本没有重现；异常按 `references/memory-common.md`〔分支 correction〕〈改的范围〉处理。还没发生这次写入时只注明未验证，不为验证额外写入。
<!-- END minis-memory-correction -->

<a id="branch-minis-memory-injection"></a>
<!-- BEGIN minis-memory-injection -->
# Minis 记忆：条目校验与日志注入

本资源的工具和命令只在 Minis 端可用。涉及日志注入、截断或容量的操作、建议或判断前，先完整读取 `references/minis.md`〔分支 minis〕、`references/minis.md`〔分支 minis-runtime〕 和 `references/minis.md`〔分支 minis-runtime-context〕，保留原 Minis 运行时共同前置。

## 条目校验工具

- **格式体检** `/var/minis/shared/memory-tools/verify-memory-format.py`（只读）：按条目检查条目数、关键词行、时间戳、词数和字节预算，退出码 1 表示有硬失败。写入或整理记忆后跑一次，用来查漏；`--strict-terms` 是回补专用的严格档（要求关键词在正文原样出现，比规则更严），不要用它评判既有条目。它是事后查漏工具，不是写入的强制入口，不能据此说格式已被强制。
- **压缩门禁** `/var/minis/shared/memory-tools/entry-guard.py`（只读）：压缩某条记忆前后，用 `--old <压缩前副本> --new <当前文件>` 逐条比对可检索的标识有没有丢（哈希、提交号、job id、`skl_*`、路径、文件名、容量、常量名），并检查条目数和关键词行。硬失败（非 0）就不能说压缩无损。子代理的自述不代替父级核对：父级核对对象哈希、命令、退出码和原始结果，证据不足或对象变了才重跑。

## 日志自动注入（2026-09-19 本机实测，App 版本未记录）

- **规则**：记忆开启时，按文件日期取当天和前两天的日志，每份截取前 199 个物理行（不按 mtime、字符或 token 截取）。第 200 行起不注入，跨越截断线的条目可能不完整。注入的字符量约为各文件所取行数乘以平均每行字符数之和，token 数还取决于文本和 tokenizer。
- **目标**：每日日志 ≤199 物理行是完整注入的目标；每日约 25,000 B 是文本规模的观察目标。两者分别核算，都不是写入工具的硬限，也不是跨端规则（行数含标题、时间戳和空行）。单条 2 KiB 的软预算见 `references/memory-common.md`〔分支 maintenance〕。
- **接近或超标时**：检查重复、完整条目和截断边界；不为了达标删事实、补空行、机械折行、拆散条件或擅自整理历史。无法兼顾时保留必要的事实，报告超标和可能的截断，不声称完整注入。授权内折短长行可以减少字符，但可能把原文推到截断线之外，不保证关键结论和条件完整；折行宽度按当次的目标和边界决定，不自动批量重排历史。
- **重核**：App 更新、开关变化或观察结果改变时，要重新核实，并在记忆开启的新会话里验证注入，不能用当前会话或文件回读代替。
<!-- END minis-memory-injection -->

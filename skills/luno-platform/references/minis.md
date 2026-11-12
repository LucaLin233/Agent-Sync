分支：minis、minis-configuration、minis-runtime、minis-runtime-context、minis-runtime-device、minis-memory。读法见 luno-core 入口〈加载〉。

<a id="branch-minis"></a>
<!-- BEGIN minis -->
# LUNO｜Minis 客户端与运行时

## 范围

Minis App 及其内置的 iSH 环境（Alpine/aarch64）：技能、子代理、模型与分组、SOUL、环境变量与挂载、`/var/minis/` 目录与备份，以及上下文卸载与压缩、会话结果截断、本机展示和调度等运行时行为。LobeHub 实例见 `luno-platform/references/lobehub.md`〔分支 lobehub〕。

## 手册优先

Minis 自身的目录、挂载、CLI、`minis-config` 字段、报错、deeplink 和 iSH 限制，先查 `/var/minis/docs/` 并读命中的页面（只读，随 App 更新，版本见 `VERSION`）：`rg -il '<关键词>' /var/minis/docs`，报错用 `rg -F '<原文片段>' /var/minis/docs/errors`，命令参数以 `<cmd> --help` 为准。手册只说明平台机制，不覆盖总控、本技能的触发和安全授权规则；与本机观测不符时注明版本和证据，在授权内核验或标「待验证」。手册没覆盖的 LUNO 约定和本机观测仍以本技能为准。

## 本机能力

系统和架构、运行时版本以及网络限制，以当次的本机证据和手册 `faq/ish-limits.md` 为准，不拿历史版本当当前能力；不假设 iSH 里有 Docker、systemd 或可用的入站监听。环境变量的语义查 `config/envvars.md`，只引用当次授权的变量，不凭列表顺序推断能力。

## 资源与触发

路径相对技能根，按总控的加载规则读取；下列操作只在 Minis 端可用。

- 客户端配置的读写（`minis-config`、子代理与模型、SOUL 与提示词、环境变量与挂载、技能新建与元数据刷新）：完整读取 `references/minis.md`〔分支 minis-configuration〕。
- **使用 Minis 文件编辑工具前**，以及上下文卸载与压缩、会话结果截断、跨会话目录与挂载、隐私掩码、独立 Shell 进程、后台调度、工具连接异常：`references/minis.md`〔分支 minis-runtime〕。命中以下情形时另完整读对应分支：
  - 上下文卸载、压缩、offloads、会话结果截断、会话原文回读，以及记忆注入、截断或容量相关判断前；跨会话目录、挂载、用户文件定位或跨话题交接前：`references/minis.md`〔分支 minis-runtime-context〕。其中需要记忆规则时继续按该资源加载，不凭旧阈值推断。
  - 本机能力、独立 Shell 进程、原生命令、分页覆盖、后台服务与调度、Bonjour、debug、文件或进程异常、Codex/iSH TLS 的操作、建议或判断前：`references/minis.md`〔分支 minis-runtime-device〕。`references/minis.md`〔分支 minis-runtime〕 的编辑与隐私掩码规则和工具异常规则仍适用；不因分支化省略安全、授权或写后回读。
- 记忆写入或整理后的条目格式体检、压缩前后的标识保全校验，记忆日志的自动注入、截断与容量评估：`references/minis.md`〔分支 minis-memory〕。
- 归档会话、判断会话归属，或用 `minis-sessions-cli update --group` 改派之前：`references/minis.md`〔分支 minis-configuration〕〈会话归组〉。

## 输出

另给出改动入口（App 页面或 `minis-config` 路径）；登记表与文件不一致、或掩码导致的疑似异常，要说明是展示层的问题还是实际状态。
<!-- END minis -->

<a id="branch-minis-configuration"></a>
<!-- BEGIN minis-configuration -->
# Minis 客户端配置

本资源的操作只在Minis端可用。配置任务整份读取。

## 配置接口

- **先读帮助**：字段、路径、支持面、确认与回滚按当前 `minis-config --help`、`list-topics` 和 `topic-help <相关主题>`（含 FIELD I/O、AUDIT）；同一会话、版本和主题已读的不重读，未知或版本变化时补读。筛选和分页不能代替非秘密字段投影。
- **App 补位**：新增子代理、技能元数据及其刷新走 App；技能正文改文件不刷新登记（见〈技能登记〉）。
- **`set-batch` 的未明示边界**：`value_json` 是 JSON **文本**，须多一层编码。既有本机观测中，任一项失败会报 `partial_write_failed`，且**同批已成功的项也可能没落盘**；失败后先逐项回读，只重写缺失项。
- **环境变量**在 App 设置页维护；按变量名引用，缺失就说明并给出创建入口，不换来源。凭据类只读存在性和长度，取值不经过对话。

## 子代理与模型

- roster 的 `builtin.general` 对应 `subagents.general.instructions`；字段与各条目上限按 `minis-config topic-help subagents`，不在条目间外推。
- 子代理的工具和上下文能力按当前手册和实际运行面核对，不外推到两端；派发按 `luno-core/references/review.md`〔分支 delegation〕，身份和采纳按 `luno-core/references/review.md`〔分支 review〕。
- **生效窗口**由分组的 `contextLimitTokens` 决定，**分组优先于模型条目**的 `contextWindowOverride`/`contextWindowTokens`；关掉「Limit Context Window」会回落到条目值，再打开后**要回读当前分组的生效值**，不用历史观测代替。
- 模型不可用时，按分组的解析结果和报错判断，分清「配置已保存」「分组已绑定」「调用实际成功」三件事。

## SOUL 与提示词

- `soul.body` 是生效值；与文件视图 `SOUL.md` 不一致时，先判定当前生效的版本，不自行挑一份覆盖其他。
- **正文值**：`soul.body` 必须按 `minis-config --help`〈FIELD I/O〉编码成 JSON **字符串**，不能把裸文本交给 `--file`。长度预算查 `topic-help soul`；字节提取口径按 `body_contract.body_bytes`。
- 改写 `SOUL.md` 要保留 frontmatter，正文按 `body_contract.body_bytes` 提取，重组时不额外追加换行。文件正文、`soul.body` 和仓库正文按 UTF-8 字节判等，不 strip，不归一换行。

## 记忆与生效真源

- `memory_write` 写入 `/var/minis/memory/YYYY-MM-DD.md`。需要每轮注入的偏好和约定可以放 `GLOBAL.md`：它默认只读、由用户维护，AI 只按用户的明示修改，只承载本端约定，不作跨端真源。记忆的边界、更正和诚实边界见 `luno-memory`；注入窗口和容量见本技能的记忆资源。
- **跨端规则的生效真源在 Minis**：技能正文 `/var/minis/skills/<name>/SKILL.md`，常驻提示词 `soul.body`（文件视图 `SOUL.md`）。候选只在隔离的仓库副本里编辑，写生效端之前必须按 `luno-core/references/sync.md`〔分支 sync〕 的同步流程执行。

## 技能登记

- **正文和元数据分开存**：正文在 `/var/minis/skills/<name>/SKILL.md`，改文件即时生效；但技能页和系统提示里的**元数据（描述、排序）存在 App 的登记表里**，改文件不会刷新，重启也不会重扫。
- **新建技能**：建目录和 `SKILL.md`，frontmatter 含 `name`、`description`，App 会自动登记，到技能页核对描述和排序。技能清单在**会话开始时注入**，当前会话看不到新登记，要在**新会话里复核元数据**（清单可能被截断，不保证完整）。名称和路径已确认的正文，当前会话就可以按 `/var/minis/skills/<name>/SKILL.md` 只读加载；能读到正文不等于登记已刷新。
- **刷新元数据**：备份内容（含附属文件；先列文件清单，凭据类文件只记位置不打开，无法安全完整备份就暂停）并核对哈希 → 在技能页删除该技能（会连同磁盘目录一起删）→ 用备份重建 → 核对新登记和内容一致。**只删磁盘目录没用**：登记记录还在，放回去会沿用旧的元数据。

## 会话归组

只适用于本用户的 Minis。App 的分组没有描述字段，自动归组只看组名；下面的判据供助手归档和必要时改派（`minis-sessions-cli update --group`），不是 App 的归组依据。

- **CCHP**：CCH/CCHP 网关的升级迁移、Bug 排障、供应商与模型、覆写规则、配额、打包。
- **Minis 与技能**：Minis 平台的技能增改与来源登记、MCP、子代理、会话、提示词与 SOUL。
- **Surge 与模块开发**：Surge 配置、模块、脚本、面板；aiapi 也归这组，不单拆。
- **服务器运维**：主机层的内存和 swap、磁盘清理、备份打包、Redis 等常驻服务、权限。
- **容器与部署**：Docker/Compose、镜像与多架构、Nginx、服务上线与迁移。
- **仓库与工具链**：仓库 CI、测试、脚本实测、Node.js 和 onlyboxes 等运行环境。
- **网络与隧道**：Cloudflare Tunnel/cloudflared、测速、链路诊断。
- **LobeHub**：LobeHub 2.x 实例的部署、Agent 与模型、连接器、知识库。
- **创作与素材**：文案、故事、音译、图标、矢量图等非技术产出。
<!-- END minis-configuration -->

<a id="branch-minis-runtime"></a>
<!-- BEGIN minis-runtime -->
# Minis 运行时

本资源的操作只在 Minis 端可用。

## 编辑与隐私掩码

- **`file_edit`**：同一个文件的多次调用必须串行，不能并行；改完按总控回读。目标互不影响时可以连续应用后统一回读，出现失配就立即停下核对；报错原文见手册 `errors/tool-errors.md`。
- **Privacy Mode 占位符**（2026-11-04，Minis 1.16 (21)，合成样本，`envvars.privacyMode=true`）：手册 `config/envvars.md` 只写了按变量值掩码（≥5 字符，`MINIS_SHORTCUT_OPT_*` 除外），但本机实测还会按形态替换，而且没有提示：邮箱 → `[邮箱]`，IP 地址（含回环）→ `[IP地址]`，`sk-` 前缀加随机串 → `[密钥]`，≥32 字符的字母数字随机串和部分长连字符名 → `[高熵密钥]`；31 字符随机串、40 位 hex 和普通路径未替换。这只是已测样本，完整的匹配边界未知，可能随版本变化，误掩和漏掩可能同时存在。
- **占位符出现在哪里**：不只 `shell_execute` 的输出，`file_read`、记忆检索与注入、子代理回包里都可能出现；磁盘上和 shell 里是原值。2026-11-05 本机有两例：变量引用落盘成了四个字符的字面量，派单里的引用变成了占位符（是平台替换还是模型沿着掩码上下文生成的，没有区分）。
- **不得把占位符当原值写回**文件、命令、提交署名或派单。需要原值时，按已授权的非秘密参数和指定变量重构；对已授权且确认不含秘密的原文，可以用 `rg -c -F` 核对字面、`od -c` 核对字节，不猜着填。非秘密文本可以用脚本拼接（如 `chr(36)`）或让负责人预制，写后核对长度和字节。秘密不用这些方法，只核存在性和长度。
- **掩码不是防泄漏**：不能假定其他秘密也会被掩码，展示上的掩码不能作为没泄漏的证据；安全核验要检查原始出口里的合成标记。出现占位符或参数失配时，用已授权的非秘密证据区分是展示问题还是实际执行；区分不了就标「待验证」并停止依赖，不以换成脚本来证明绕过了掩码。命令不要压制 stderr。

- **工具异常**：工具结果出现固定替换或错配就停止依赖，用可靠的独立通道回读对象来判断写入；状态不明不重试，不采信被污染的输出。`minis-model-use run` 按当前的 `--help`、版本和请求链路核验，报错不单独定因。`minis-mcp-cli` 改了配置或环境变量后要先 `shutdown` 再 `ping`，否则守护进程沿用旧配置，表现为 401（原版本和日期未记录，Minis 1.16 (21) 未核）；OAuth 类 MCP 回 App 的 MCP Integrations → Authorize 授权，配完 `ping` 通过才算好。

来源与许可：OpenMinis/MinisSkills，MIT 精选改写；Copyright (c) 2026 OpenMinis；2026-10-25 本地决定按 MIT 处理，README 的 Apache-2.0 标注冲突保留，不作法律适用结论或扩大分发授权。完整许可随包见 ../LICENSE.openminis.txt；固定提交、取材路径与日期见仓库 skills-sources.md。
<!-- END minis-runtime -->

<a id="branch-minis-runtime-context"></a>
<!-- BEGIN minis-runtime-context -->
# Minis 上下文、目录与挂载

先完整读 `references/minis.md`〔分支 minis-runtime〕，本资源只在 Minis 端操作；遵守其中的编辑、隐私掩码和工具异常共同规则。

## 上下文行为

- 上下文卸载、压缩和占位符以当前手册 `concepts/minis-url-scheme.md`〈Offloads〉和本次的实际提示为准；不沿用旧的 32K/64K/128K 阈值、压缩轮数或 token 估算倍率。当前行为未知就标「待验证」，不凭字符数估算余量；开启诊断日志仍需配置修改授权。
- **工具结果自动卸载**是执行者无法关闭的平台行为（机制见上述手册）：派单和执行时用字段投影、截断或计数控制单次输出，避免触发。发生后只报告工具给出的确切路径，未经另行授权不读不删；不算受派方主动越权，不需逐次记入事故。获准回读时不猜文件名；编码或二进制拒读不代表不存在，只对确认不含秘密的文本，在确认编码后用管道转成 UTF-8 读取。秘密输出禁令不因自动卸载而豁免。
- 回读会话的参数和字段上限见手册 `cli/minis-sessions-cli.md`（含 `--full`、`--tools`；`messages --tools --full` 读取已存储的 shell 输入，不保证恢复完整元数据）。`messages --id` 必须用完整 UUID：2026-10-25 本机用 8 位前缀时返回成功但消息为空，不能据此判断没有消息。长结果要当轮按授权归档，没有授权就报告缺口；检索或回读父会话和其他会话须当次授权，默认不提供父会话转录。
- 规则文本本身不会报告余量，所以只在事件和阶段边界触发交接，不做「快满了」的预警。
- 涉及记忆日志的自动注入、截断或容量，或据此评估日志的压缩、折行和整理时，先读 `references/minis.md`〔分支 minis-memory〕。

## 目录与挂载

目录分工、会话隔离和挂载读写按手册 `concepts/directories.md`、`faq/shared-vs-workspace.md`、`concepts/mounts.md`。跨会话、跨话题的交接写进 `shared/`（按项目分目录，不放临时文件，备份附校验清单）；`mounts/` 写入被拒就如实报错，不改写到别处；找用户文件先看 `mounts/`，不全盘扫描。

来源与许可：OpenMinis/MinisSkills，MIT 精选改写；Copyright (c) 2026 OpenMinis；2026-10-25 本地决定按 MIT 处理，README 的 Apache-2.0 标注冲突保留，不作法律适用结论或扩大分发授权。完整许可随包见 ../LICENSE.openminis.txt；固定提交、取材路径与日期见仓库 skills-sources.md。
<!-- END minis-runtime-context -->

<a id="branch-minis-runtime-device"></a>
<!-- BEGIN minis-runtime-device -->
# Minis 本机能力与异常

先完整读 `references/minis.md`〔分支 minis-runtime〕，本资源只在 Minis 端操作；遵守其中的编辑、隐私掩码和工具异常共同规则。

## 本机特性

- 系统和架构、Python/Node 版本、磁盘余量按当次目标现查；限制按 `luno-platform/references/minis.md`〔分支 minis〕〈本机能力〉和当前手册，不拿旧版本代替。
- BusyBox 的 `cut -c` 按字节切分，会截断中文，验证中文输出时不要用。
- 原生 `apple-*` 以本机 `/usr/local/bin` 下的二进制和 `--help` 为准（手册 `cli/_gotchas.md`），不按旧文档的表格调用。原生查询出现截断、分页或总量大于返回量时，结果只代表已读取的范围；排序没有保证时，不能当作最早、最新或优先级最高的子集，也不能据此说「全部」「没有」或「已清空」。优先在既有数据授权内缩小范围或补齐必要的分页；补不齐就说明覆盖范围，不为求全量而扩大个人数据的访问。
- **后台与调度**：独立 Shell 进程、后台服务、定时任务、后台开关和 `minis-bonjour`，按手册 `faq/ish-limits.md`、`cli/minis-scheduled.md`、`config/topics/background.md`、`cli/minis-bonjour.md` 和各命令的 `--help`。补充：定时任务只在 App 运行期间执行，「已注册」不等于「会执行」，必须送达的场景改用 Apple Shortcuts，创建后核对 `delivery` 去向；后台开关不保证 App 被杀后继续执行；Bonjour 的发现、连接或发布仍须覆盖相应网络对象的授权，不顺带扫描周边设备。
- **`minis-debug`**：Release 版只有 `logs`（手册 `cli/_gotchas.md`）；`write`/`exec` 涉及写入和执行，不因排障自动获准。日志（以及 Debug 版的视图和 trace）可能含会话内容或秘密，只按非秘密字段投影，不能安全投影就停，不全量导出。
- **iSH 文件和进程异常**：上游 ios-dev 报告过 `shutil.copy2` 失败、`cp` 偶尔报 `file replaced`、`pgrep -x` 漏检。2026-10-25 本机实测：从 `/var/minis/{skills,memory,mounts}` 复制已测文件到 workspace 或 shared 会报 `replaced while being copied`，workspace 内部和 workspace → shared 成功（现版本未复测，不外推）。只需要内容时，在授权内用 `cat` 重定向或 `tar` 管道并核对内容，不要反复重试 `cp`；需要保留元数据时不能直接用 `copyfile` 代替 `copy2`，另核权限。判断进程是否退出要交叉核对 `ps` 的完整命令，不凭一次 `pgrep` 未命中下结论。
- **Codex/iSH TLS**：上游 codex-on-ish 报告，官方 musl 二进制 ≥v0.143 首次 TLS 握手出现 `installed rustls crypto provider must support ECDSA_NISTP521_SHA512`（v0.130/ring 只接受 ECDSA P-256），远端异步连接另报 `connect errno 65`/`error sending request`，而 curl 和 loopback 正常（2026-10-25 记录，现版本未核）。先核对当前版本和原始错误，不自动降级、关闭校验、安装 MITM 或伪装版本。

来源与许可：OpenMinis/MinisSkills，MIT 精选改写；Copyright (c) 2026 OpenMinis；2026-10-25 本地决定按 MIT 处理，README 的 Apache-2.0 标注冲突保留，不作法律适用结论或扩大分发授权。完整许可随包见 ../LICENSE.openminis.txt；固定提交、取材路径与日期见仓库 skills-sources.md。
<!-- END minis-runtime-device -->

<a id="branch-minis-memory"></a>
<!-- BEGIN minis-memory -->
# Minis 记忆：条目校验与日志注入

本资源的工具和命令只在 Minis 端可用。

## 条目校验工具

- **格式体检** `/var/minis/shared/memory-tools/verify-memory-format.py`（只读）：按条目检查条目数、关键词行、时间戳、词数和字节预算，退出码 1 表示有硬失败。写入或整理记忆后跑一次，用来查漏；`--strict-terms` 是回补专用的严格档（要求关键词在正文原样出现，比规则更严），不要用它评判既有条目。它是事后查漏工具，不是写入的强制入口，不能据此说格式已被强制。
- **压缩门禁** `/var/minis/shared/memory-tools/entry-guard.py`（只读）：压缩某条记忆前后，用 `--old <压缩前副本> --new <当前文件>` 逐条比对可检索的标识有没有丢（哈希、提交号、job id、`skl_*`、路径、文件名、容量、常量名），并检查条目数和关键词行。硬失败（非 0）就不能说压缩无损。子代理的自述不代替父级核对：父级核对对象哈希、命令、退出码和原始结果，证据不足或对象变了才重跑。

## 日志自动注入（2026-09-19 本机实测，App 版本未记录）

- **规则**：记忆开启时，按文件日期取当天和前两天的日志，每份截取前 199 个物理行（不按 mtime、字符或 token 截取）。第 200 行起不注入，跨越截断线的条目可能不完整。注入的字符量约为各文件所取行数乘以平均每行字符数之和，token 数还取决于文本和 tokenizer。
- **目标**：每日日志 ≤199 物理行是完整注入的目标；每日约 25,000 B 是文本规模的观察目标。两者分别核算，都不是写入工具的硬限，也不是跨端规则（行数含标题、时间戳和空行）。单条 2 KiB 的软预算见 `luno-memory`。
- **接近或超标时**：检查重复、完整条目和截断边界；不为了达标删事实、补空行、机械折行、拆散条件或擅自整理历史。无法兼顾时保留必要的事实，报告超标和可能的截断，不声称完整注入。授权内折短长行可以减少字符，但可能把原文推到截断线之外，不保证关键结论和条件完整；折行宽度按当次的目标和边界决定，不自动批量重排历史。
- **重核**：App 更新、开关变化或观察结果改变时，要重新核实，并在记忆开启的新会话里验证注入，不能用当前会话或文件回读代替。
<!-- END minis-memory -->


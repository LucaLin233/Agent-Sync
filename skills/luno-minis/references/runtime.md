# Minis 运行时

本资源的操作只在 Minis 端可用。

## 编辑与隐私掩码

- **`file_edit`**：同一个文件的多次调用必须串行，不能并行；改完按总控回读。目标互不影响时可以连续应用后统一回读，出现失配就立即停下核对；报错原文见手册 `errors/tool-errors.md`。
- **Privacy Mode 占位符**（2026-11-04，Minis 1.16 (21)，合成样本，`envvars.privacyMode=true`）：手册 `config/envvars.md` 只写了按变量值掩码（≥5 字符，`MINIS_SHORTCUT_OPT_*` 除外），但本机实测还会按形态替换，而且没有提示：邮箱 → `[邮箱]`，IP 地址（含回环）→ `[IP地址]`，`sk-` 前缀加随机串 → `[密钥]`，≥32 字符的字母数字随机串和部分长连字符名 → `[高熵密钥]`；31 字符随机串、40 位 hex 和普通路径未替换。这只是已测样本，完整的匹配边界未知，可能随版本变化，误掩和漏掩可能同时存在。
- **占位符出现在哪里**：不只 `shell_execute` 的输出，`file_read`、记忆检索与注入、子代理回包里都可能出现；磁盘上和 shell 里是原值。2026-11-05 本机有两例：变量引用落盘成了四个字符的字面量，派单里的引用变成了占位符（是平台替换还是模型沿着掩码上下文生成的，没有区分）。
- **不得把占位符当原值写回**文件、命令、提交署名或派单。需要原值时，按已授权的非秘密参数和指定变量重构；对已授权且确认不含秘密的原文，可以用 `rg -c -F` 核对字面、`od -c` 核对字节，不猜着填。非秘密文本可以用脚本拼接（如 `chr(36)`）或让负责人预制，写后核对长度和字节。秘密不用这些方法，只核存在性和长度。
- **掩码不是防泄漏**：不能假定其他秘密也会被掩码，展示上的掩码不能作为没泄漏的证据；安全核验要检查原始出口里的合成标记。出现占位符或参数失配时，用已授权的非秘密证据区分是展示问题还是实际执行；区分不了就标「待验证」并停止依赖，不以换成脚本来证明绕过了掩码。命令不要压制 stderr。

## 上下文行为

- 上下文卸载、压缩和占位符以当前手册 `concepts/minis-url-scheme.md`〈Offloads〉和本次的实际提示为准；不沿用旧的 32K/64K/128K 阈值、压缩轮数或 token 估算倍率。当前行为未知就标「待验证」，不凭字符数估算余量；开启诊断日志仍需配置修改授权。
- offloads 只读工具给出的确切路径，不猜文件名。因编码或二进制拒读不代表文件不存在；只对获准且确认不含秘密的文本，在确认编码后用管道转成 UTF-8 读取。
- 回读会话的参数和字段上限见手册 `cli/minis-sessions-cli.md`（含 `--full`、`--tools`；`messages --tools --full` 读取已存储的 shell 输入，不保证恢复完整元数据）。`messages --id` 必须用完整 UUID：2026-10-25 本机用 8 位前缀时返回成功但消息为空，不能据此判断没有消息。长结果要当轮按授权归档，没有授权就报告缺口；检索或回读父会话和其他会话须当次授权，默认不提供父会话转录。
- 规则文本本身不会报告余量，所以只在事件和阶段边界触发交接，不做「快满了」的预警。
- 涉及记忆日志的自动注入、截断或容量，或据此评估日志的压缩、折行和整理时，先读 `references/memory.md`。

## 目录与挂载

目录分工、会话隔离和挂载读写按手册 `concepts/directories.md`、`faq/shared-vs-workspace.md`、`concepts/mounts.md`。跨会话、跨话题的交接写进 `shared/`（按项目分目录，不放临时文件，备份附校验清单）；`mounts/` 写入被拒就如实报错，不改写到别处；找用户文件先看 `mounts/`，不全盘扫描。

## 本机特性

- 系统和架构、Python/Node 版本、磁盘余量按当次目标现查；限制按 `luno-minis/SKILL.md`〈本机能力〉和当前手册，不拿旧版本代替。
- BusyBox 的 `cut -c` 按字节切分，会截断中文，验证中文输出时不要用。
- 原生 `apple-*` 以本机 `/usr/local/bin` 下的二进制和 `--help` 为准（手册 `cli/_gotchas.md`），不按旧文档的表格调用。原生查询出现截断、分页或总量大于返回量时，结果只代表已读取的范围；排序没有保证时，不能当作最早、最新或优先级最高的子集，也不能据此说「全部」「没有」或「已清空」。优先在既有数据授权内缩小范围或补齐必要的分页；补不齐就说明覆盖范围，不为求全量而扩大个人数据的访问。
- **后台与调度**：独立 Shell 进程、后台服务、定时任务、后台开关和 `minis-bonjour`，按手册 `faq/ish-limits.md`、`cli/minis-scheduled.md`、`config/topics/background.md`、`cli/minis-bonjour.md` 和各命令的 `--help`。补充：定时任务只在 App 运行期间执行，「已注册」不等于「会执行」，必须送达的场景改用 Apple Shortcuts，创建后核对 `delivery` 去向；后台开关不保证 App 被杀后继续执行；Bonjour 的发现、连接或发布仍须覆盖相应网络对象的授权，不顺带扫描周边设备。
- **工具异常**：工具结果出现固定替换或错配就停止依赖，用可靠的独立通道回读对象来判断写入；状态不明不重试，不采信被污染的输出。`minis-model-use run` 按当前的 `--help`、版本和请求链路核验，报错不单独定因。`minis-mcp-cli` 改了配置或环境变量后要先 `shutdown` 再 `ping`，否则守护进程沿用旧配置，表现为 401（原版本和日期未记录，Minis 1.16 (21) 未核）；OAuth 类 MCP 回 App 的 MCP Integrations → Authorize 授权，配完 `ping` 通过才算好。
- **`minis-debug`**：Release 版只有 `logs`（手册 `cli/_gotchas.md`）；`write`/`exec` 涉及写入和执行，不因排障自动获准。日志（以及 Debug 版的视图和 trace）可能含会话内容或秘密，只按非秘密字段投影，不能安全投影就停，不全量导出。
- **iSH 文件和进程异常**：上游 ios-dev 报告过 `shutil.copy2` 失败、`cp` 偶尔报 `file replaced`、`pgrep -x` 漏检。2026-10-25 本机实测：从 `/var/minis/{skills,memory,mounts}` 复制已测文件到 workspace 或 shared 会报 `replaced while being copied`，workspace 内部和 workspace → shared 成功（现版本未复测，不外推）。只需要内容时，在授权内用 `cat` 重定向或 `tar` 管道并核对内容，不要反复重试 `cp`；需要保留元数据时不能直接用 `copyfile` 代替 `copy2`，另核权限。判断进程是否退出要交叉核对 `ps` 的完整命令，不凭一次 `pgrep` 未命中下结论。
- **Codex/iSH TLS**：上游 codex-on-ish 报告，官方 musl 二进制 ≥v0.143 首次 TLS 握手出现 `installed rustls crypto provider must support ECDSA_NISTP521_SHA512`（v0.130/ring 只接受 ECDSA P-256），远端异步连接另报 `connect errno 65`/`error sending request`，而 curl 和 loopback 正常（2026-10-25 记录，现版本未核）。先核对当前版本和原始错误，不自动降级、关闭校验、安装 MITM 或伪装版本。

来源与许可：OpenMinis/MinisSkills，MIT 精选改写；Copyright (c) 2026 OpenMinis；2026-10-25 本地决定按 MIT 处理，README 的 Apache-2.0 标注冲突保留，不作法律适用结论或扩大分发授权。完整许可随包见 ../LICENSE.openminis.txt；固定提交、取材路径与日期见仓库 skills-sources.md。

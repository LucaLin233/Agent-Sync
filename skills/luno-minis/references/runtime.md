# LUNO｜Minis 运行时排障

先取得本包入口必需规则；其中操作只在 Minis 端可用。

## 上下文行为
- 上下文卸载、压缩与占位符以当前手册 `concepts/minis-url-scheme.md`〈Offloads〉及本次实际提示为准；不保留旧32K/64K/128K阈值、压缩轮数和token估算倍率作能力依据。未知当前行为标待验证，不据字符估算判断余量；开启诊断日志仍需配置修改授权。
- offloads只读工具实际给出的确切路径，不猜名。编码/二进制拒读不证明不存在；仅对获准且确认非秘密文本，在确认编码后用管道转UTF-8读取。
- 回读会话的参数与字段上限见手册 `cli/minis-sessions-cli.md`（含 `--full`、`--tools`；`messages --tools --full` 读取已存储的 shell 输入，不保证恢复完整元数据）。`messages --id` 须用完整 UUID：2026-10-25 本机八位前缀返回成功但消息为空，不能据此判无消息。长结果须当轮按授权归档，无授权报缺口；检索/回读父会话或其他会话须当次授权，父会话转录默认不给。
- 规则文本本身不报余量，故只做事件触发与阶段边界触发，不做「快满预警」。
- Minis 记忆日志自动注入/截断/容量，或据此评估日志压缩/折行/整理，须在操作/建议/结论前完整读取 `references/memory.md`（相对本技能根目录）；其它任务不必读，中途涉及先补读。跨域取必需规则并集；必需资源缺失/不完整/不可读/版本冲突即停依赖、报告，不凭记忆替代；加载不新增授权。

## 会话归组

**适用范围：仅本用户的 Minis**。App 的分组没有描述字段，自动归组只读组名；以下判据供助手归档与必要时改派（`minis-sessions-cli update --group`），不是 App 的归组依据。

- **CCHP**：CCH/CCHP 网关——升级迁移、Bug 排障、供应商与模型、覆写规则、配额、打包。
- **Minis 与技能**：Minis 平台——技能增改及来源登记、MCP、子代理、会话、提示词与 SOUL。
- **Surge 与模块开发**：Surge 配置、模块、脚本、面板；**aiapi 属此组，不单拆**。
- **服务器运维**：主机层——内存/swap、磁盘清理、备份打包、Redis 等常驻服务、权限。
- **容器与部署**：Docker/Compose、镜像与多架构、Nginx、服务上线与迁移。
- **仓库与工具链**：仓库 CI、测试、脚本实测、Node.js/onlyboxes 等运行环境。
- **网络与隧道**：Cloudflare Tunnel/cloudflared、测速、链路诊断。
- **LobeHub**：LobeHub 2.x 实例——部署、Agent 与模型、连接器、知识库。
- **创作与素材**：文案、故事、音译、图标、矢量图等非技术产出。

## 目录与持久化（跨会话目录与挂载）
- 目录分工、会话隔离与挂载读写依手册 `concepts/directories.md`、`faq/shared-vs-workspace.md`、`concepts/mounts.md`。跨会话与跨话题交接写入 `shared/`（按项目分目录、不放临时文件，备份附校验清单）；`mounts/` 写入被拒如实报错，不改写别处；找用户文件先看 `mounts/`，不全盘扫描。

## 本机特性
- 系统/架构、Python/Node版本及磁盘余量按当次目标现查；限制依 `luno-minis/SKILL.md`〈本机能力〉与当前手册，不拿旧版本替代。
- Minis `file_edit`：同一文件的多个调用须串行（不得并行）；改完按 `luno-core/SKILL.md`〈执行闭环〉回读；目标互不影响时可连续应用后统一回读，出现失配立即停止核对；报错原文见手册 `errors/tool-errors.md`。
- **Privacy Mode**：手册 `config/envvars.md`〈Privacy Mode〉只写按变量值掩码（≥5 字符，`MINIS_SHORTCUT_OPT_*` 除外）并附提示，与本机实测不符；以下为实测。2026-11-04 Minis 1.16 (21) 本机以合成样本实测（`envvars.privacyMode=true`），另有按形态替换且未见该提示：邮箱→`[邮箱]`，IP 地址（含回环）→`[IP地址]`，`sk-` 前缀加随机串→`[密钥]`，≥32 字符的字母数字随机串及部分长连字符名→`[高熵密钥]`；31 字符随机串、40 位 hex 与普通路径未替换。以上仅为已测样本，未确定完整匹配边界；规则可能随版本变化，误掩与漏掩可并存。替换不限 `shell_execute` 输出，`file_read`、记忆检索与注入、子代理回包同样可见占位符；磁盘与 shell 内为原值；2026-11-05 本机两例：变量引用落盘成四字符字面量、派单引用成占位符；平台替换或模型沿掩码上下文生成，未区分。非秘密文本可用脚本拼接（如 chr(36)）或负责人预制，写后核长度和字节；此仅为写入手法。占位符不得当原值写回文件、命令、提交署名或派单：需原值时按已授权非秘密参数与指定变量重构，或仅对已授权且已确认非秘密的原文用 `rg -c -F` 核字面、`od -c` 核字节（署名以现行规则为准），不猜填；禁用于秘密（只核存在性与长度）。不得假定其他秘密会被掩码，展示掩码不作防泄漏证据，安全核验检查原始出口的合成标记。出现占位符或参数失配时，用已授权非秘密证据区分展示与实际执行；不能区分即标待验证并停依赖，不以换成脚本证明绕过。命令勿压制 stderr。
- BusyBox `cut -c` 按字节切分，会截断中文，验证中文输出不要用。
- 原生 `apple-*` 以本机 `/usr/local/bin` 二进制与 `--help` 为准（手册 `cli/_gotchas.md`），不按旧文档表格调用。
- 原生命令查询出现截断、分页或总量大于返回量时，结果仅代表已读取范围；排序未保证时不得视为最早、最新或优先级最高的子集，不能据此宣称“全部”“没有”或“已清空”。优先在既有数据授权内缩小范围或补齐必要分页；不能补齐则明确覆盖范围，不为求全量而扩大个人数据访问。
来源：OpenMinis/MinisSkills@164395f193a56e3507ca98415383c7c16780da00，apple-reminders/SKILL.md:94–103；2026-10-25 本地核对；MIT（Copyright (c) 2026 OpenMinis），精选改写；完整许可见 `../LICENSE.openminis.txt`；上游根 LICENSE 与 README 的许可标注不一致仍保留，在线可取性未复核。
- 独立 Shell 进程与后台服务、定时任务、后台开关、`minis-bonjour`：依手册 `faq/ish-limits.md`、`cli/minis-scheduled.md`、`config/topics/background.md`、`cli/minis-bonjour.md` 与各命令 `--help`。LUNO 补充：定时任务只在 App 运行期间执行，「已注册」不等于「会执行」，必达场景指向 Apple Shortcuts，创建后核 `delivery` 去向；后台开关不是 App 被杀后继续执行的保证；Bonjour 的发现、连接或发布仍须覆盖相应网络对象的授权，不顺带扫描周边设备。
- 工具结果固定替换或错配即停依赖，由可靠独立通道回读对象判断写入；状态不明不重试、不采信污染输出。`minis-model-use run` 按当前 `--help`、版本与请求链路核验，报错不单独定因；`minis-mcp-cli` 改配置或环境变量后须 `shutdown` 再 `ping`，否则守护进程沿用旧配置（表现为 401；原版本/日期未记，Minis 1.16 (21) 未核）；OAuth 类 MCP 授权回 App 的 MCP Integrations → Authorize，配完须 `ping` 通过。
- `minis-debug`：Release 版只有 `logs`（手册 `cli/_gotchas.md`）；`write/exec` 涉写入/执行，不因排障自动获准；日志（及 Debug 版视图、trace）可能含会话或秘密，只按非秘密字段投影，不能安全投影即停，不全量导出。
- iSH 文件/进程异常：上游 ios-dev 报 `shutil.copy2` 失败、`cp` 偶报 `file replaced`、`pgrep -x` 漏检。2026-10-25 本机实测 `/var/minis/{skills,memory,mounts}` 的已测文件复制到 workspace/shared 报 `replaced while being copied`，workspace 内及 workspace→shared 成功；不外推（2026-10-25 记录，现版未复测）。只需内容时可在授权内用 `cat` 重定向或 `tar` 管道并核内容，勿反复重试 `cp`；其余上游行为本机未复核。需保留元数据时不可直接以 `copyfile` 代 `copy2`，另核权限；进程交叉核对 `ps` 完整命令，不凭一次 pgrep 未命中认定退出。
来源：OpenMinis/MinisSkills@164395f193a56e3507ca98415383c7c16780da00，ios-dev/SKILL.md；2026-10-25 本地核对；MIT（ios-dev/LICENSE）；精选改写；上游在线可取性未复核；上述复制样本外的上游所述行为本机未复核。
- Codex/iSH TLS 排障：上游 codex-on-ish 报告官方 musl 二进制 ≥v0.143 首次 TLS 握手出现 `installed rustls crypto provider must support ECDSA_NISTP521_SHA512`（v0.130/ring 仅接受 ECDSA P-256），远端异步连接另报 `connect errno 65`／`error sending request` 而 curl 与 loopback 可用（2026-10-25 记录，现版未核）；先核当前版本与原始错误，不自动降级、关闭校验、安装 MITM 或伪装版本。
来源：OpenMinis/MinisSkills@164395f193a56e3507ca98415383c7c16780da00，codex-on-ish/SKILL.md；2026-10-25 本地核对；本地维护者已决定按 MIT 处理；上游根 LICENSE 与 README 的许可标注不一致仍保留；精选改写；在线可取性与本机行为未复核。


## MIT 通知与本地维护决定

OpenMinis/MinisSkills@164395f193a56e3507ca98415383c7c16780da00；2026-10-25 本地维护者决定按 MIT 处理。上游根 LICENSE 与 README 标 Apache-2.0 的不一致仍保留；本地决定不是法律适用结论，不授权扩大分发；在线可取性未复核。适用于本文件 apple-reminders、ios-dev 与 codex-on-ish 三处已标注的精选改写；既有历史证据范围与其他许可不变。

完整 MIT 正文随本包 `../LICENSE.openminis.txt` 分发（原文附件 sha256：`78a0f6fa39ad99be9494b462b98081023fc3fd21616a9eaa20924ef9332d2005`）。

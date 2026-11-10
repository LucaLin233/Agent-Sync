# Minis 本机能力与异常

先完整读 `references/minis-runtime.md`，本资源只在 Minis 端操作；遵守其中的编辑、隐私掩码和工具异常共同规则。

## 本机特性

- 系统和架构、Python/Node 版本、磁盘余量按当次目标现查；限制按 `luno-platform/references/minis.md`〈本机能力〉和当前手册，不拿旧版本代替。
- BusyBox 的 `cut -c` 按字节切分，会截断中文，验证中文输出时不要用。
- 原生 `apple-*` 以本机 `/usr/local/bin` 下的二进制和 `--help` 为准（手册 `cli/_gotchas.md`），不按旧文档的表格调用。原生查询出现截断、分页或总量大于返回量时，结果只代表已读取的范围；排序没有保证时，不能当作最早、最新或优先级最高的子集，也不能据此说「全部」「没有」或「已清空」。优先在既有数据授权内缩小范围或补齐必要的分页；补不齐就说明覆盖范围，不为求全量而扩大个人数据的访问。
- **后台与调度**：独立 Shell 进程、后台服务、定时任务、后台开关和 `minis-bonjour`，按手册 `faq/ish-limits.md`、`cli/minis-scheduled.md`、`config/topics/background.md`、`cli/minis-bonjour.md` 和各命令的 `--help`。补充：定时任务只在 App 运行期间执行，「已注册」不等于「会执行」，必须送达的场景改用 Apple Shortcuts，创建后核对 `delivery` 去向；后台开关不保证 App 被杀后继续执行；Bonjour 的发现、连接或发布仍须覆盖相应网络对象的授权，不顺带扫描周边设备。
- **`minis-debug`**：Release 版只有 `logs`（手册 `cli/_gotchas.md`）；`write`/`exec` 涉及写入和执行，不因排障自动获准。日志（以及 Debug 版的视图和 trace）可能含会话内容或秘密，只按非秘密字段投影，不能安全投影就停，不全量导出。
- **iSH 文件和进程异常**：上游 ios-dev 报告过 `shutil.copy2` 失败、`cp` 偶尔报 `file replaced`、`pgrep -x` 漏检。2026-10-25 本机实测：从 `/var/minis/{skills,memory,mounts}` 复制已测文件到 workspace 或 shared 会报 `replaced while being copied`，workspace 内部和 workspace → shared 成功（现版本未复测，不外推）。只需要内容时，在授权内用 `cat` 重定向或 `tar` 管道并核对内容，不要反复重试 `cp`；需要保留元数据时不能直接用 `copyfile` 代替 `copy2`，另核权限。判断进程是否退出要交叉核对 `ps` 的完整命令，不凭一次 `pgrep` 未命中下结论。
- **Codex/iSH TLS**：上游 codex-on-ish 报告，官方 musl 二进制 ≥v0.143 首次 TLS 握手出现 `installed rustls crypto provider must support ECDSA_NISTP521_SHA512`（v0.130/ring 只接受 ECDSA P-256），远端异步连接另报 `connect errno 65`/`error sending request`，而 curl 和 loopback 正常（2026-10-25 记录，现版本未核）。先核对当前版本和原始错误，不自动降级、关闭校验、安装 MITM 或伪装版本。

来源与许可：OpenMinis/MinisSkills，MIT 精选改写；Copyright (c) 2026 OpenMinis；2026-10-25 本地决定按 MIT 处理，README 的 Apache-2.0 标注冲突保留，不作法律适用结论或扩大分发授权。完整许可随包见 ../LICENSE.openminis.txt；固定提交、取材路径与日期见仓库 skills-sources.md。

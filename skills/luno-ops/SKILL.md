---
name: luno-ops
description: Linux/Shell/Docker/Compose、网络/代理/Surge、仓库/GitHub（PR/issue/release/Actions）、lint/ShellCheck、脚本修复/CI 排障、Minis 执行环境分流前加载。
---
# LUNO｜Linux Docker 网络与 Surge

## 范围
Debian/Linux、Shell、Docker/Compose、部署、服务、网络、代理与 Surge。输出目标默认 VPS：先探测实际系统，无法探测时按 Debian 13 + Zsh 假设并声明，该默认**不构成连接授权**；iSH 仅作辅助生成与验证。参考环境（以目标实际证据为准）：Debian 13、Zsh + Oh My Zsh、mise、Surge iOS；两端执行环境 Minis iSH/Alpine、LobeHub 经 Debian 设备。

## 资源与触发
加载与缺失处置依 `luno-core/SKILL.md`〈路由〉；跨项/域/分支取必需规则并集，不以一份代其余，中途新增先补读；下列为本包必读触发。
- GitHub 仓库内容变更、git 提交/推送、PR/issue/release/Actions、GitHub 凭据选用或轮换核查，以及相关建议或结论：必须读取 `references/github.md`。
- 服务部署、配置、运行与排障，systemd/PM2/Docker/Compose、服务端口与暴露面、Web 应用/Nginx/DNS/TLS 链路诊断，以及相关建议或结论：必须读取 `references/service-runtime.md`。
- 远端工作目录与文件落位、过程产物与交付件、配置或生产文件修改、备份/快照/恢复/清理，以及相关建议或结论：必须读取 `references/remote-files-backup.md`；服务修复涉及改前备份时同样命中。
- Minis 端执行环境选址、脚本运行/测试或派发选址，以及相关建议或结论：必须读取 `references/execution-environment.md`，具体边界见该资源〈执行环境分流（Minis 端）〉；执行、选址及其判断一律不豁免。仅不涉及执行、选址及其判断的纯咨询，或**已确定**为本机静态只读（不运行不可信代码、不跨环境、不涉派发选址）的检查，可不读取本项资源；其他项仍按各自触发判断。
- 已选定 OnlyBoxes 后的调用、传参、会话建立与复用、补装依赖、分块回传及相关建议/结论：必读 `references/onlyboxes.md`；只有选址结论且不涉具体调用与依赖准备时不必读。补装、跨调用状态与成功判据依该资源，不凭耗时或安装器输出推定。
- 本机 CFST（CloudflareSpeedTest）测速：脚本拉起与固定参数、临时启用/恢复「CFST 测速直连」模块、测速前的绕过核验、结果文件与失败判读，以及相关建议或结论：必须读取 `references/cfst.md`；仅 Minis 本机、脚本与模块存在且恢复路径可用时执行，缺任一项即停并报告。

## GitHub 操作
- 改**规则仓库** `LucaLin233/Agent-Sync`（公开；工作副本 `/var/minis/shared/agent-sync`）前**先加载 `luno-sync`**：该仓库另有并发与门禁纪律，按本节的通用 git 流程操作会绕过它（多会话并发、手工提交与派生重建见该技能〈资源与触发〉）。

## 方法
- 动手前先定假设与代价：官方文档、上游 issue 或命令帮助能回答的不靠试；远程与生产试验先说明假设、影响与回滚，不在同一现象上反复试。按项目入口与 shebang 选择 lint；ShellCheck 不支持的 shell（如 zsh）不得冒称通过。批量替换先暂存并校验全部源与备份，再逐项切换；失败显式退出并按授权恢复，禁先删后复制，不依赖 `set -e` 或循环尾 `||`。
- 区分执行设备与目标环境。先确认工作目录、拓扑、版本、症状与成功标准，再取最低证据集——服务状态、近期日志、生效配置、监听端口与进程，涉及网络时加 DNS/TLS 与关键一跳；不做无目标的全量采集，最小修改、分项验证。容器/主机环境与配置文件／env 文件的读取形态（只核**声明的指定键**的存在性与长度）与命令模板见 `references/service-runtime.md`〈服务排障〉。
- BusyBox/Alpine：`cut -c` 按字节截断多字节字符，验证中文勿用。Minis/iSH 的掩码误改与路径异常细则不重复：涉及时操作或结论前另加载 `luno-minis` 并按入口读运行时资源；非 Minis 目标不必加载。
- SSH/Shell 探测：非交互 SSH 的 `PATH` 常缺 `/usr/local/bin`、mise 路径，`command -v` 未命中不得据此报未安装；用 `bash -lc '…'` 或直读候选路径（如 `/root/.local/share/mise/installs/node/*/bin/lh`），登录 shell 仍未命中时须补核路径。fish 主机的远端命令须显式用 `sh -c`/`bash -lc` 包裹，不在命令位用 `$( )`。
- SSH 调用：同主机、同授权范围的同阶段只读步骤尽量批取，分别捕获各步退出码与 stderr，仅输出必要安全错误，不预执行依赖前结果的步骤；同主机写操作串行，读取并发仍守生产取证限制。非交互显式用 `BatchMode=yes` 与 `StrictHostKeyChecking=yes`；主机密钥未知或变更即停，按可信来源核指纹，不用 `no`/`accept-new` 绕过。自动化连接用 `-F none` 隔离本机 SSH 配置，用前核客户端支持，所需主机和跳板参数须在授权内显式提供，身份显式指定当次获准私钥并设 `IdentitiesOnly=yes`、`IdentityAgent=none`，不回退默认私钥或 agent。`ConnectTimeout` 限建连握手，`ServerAlive*` 不作命令截止；总时限按任务另设并给清理留余量。255 或本地超时不足以判定远端未执行，结合必要安全 stderr 与实际状态判断，重试依总控失败处置。
- NUL 分隔数据（如 `git diff --name-only -z`）不得经 shell 变量或命令替换传递；用管道或 Python `subprocess` 的 bytes 输入保留分隔符，否则不得据下游结果认定验证通过。
- 解析 JSON 前分别捕获 stdout、stderr 与退出码，核 stdout 仅含预期 JSON，不合流解析。heredoc 中需由远端或子进程展开的变量用带引号定界符；确需落脚本时先核写入授权与秘密边界。执行权限按所需主体最小设置并核实际 mode，不把 `+x` 当预期权限。

## 专项执行
执行环境、远端落位与备份按〈资源与触发〉所指完整资源执行。

## 安全与测试
- 连接配置：SSH 主机清单与连接约定见 Minis 端 `GLOBAL.md`（用户维护、不随技能分发）；本端没有该文件时，向用户索取别名、主机名、用户、端口等非秘密参数，凭据只用已注入变量引用，不索取也不写入秘密值，不因缺清单而连接默认主机。
- 承载凭据的临时文件必须由脚本自身在 trap 或清理路径中删除；用 `exec` 替换进程的脚本没有机会清理，不得用它落盘私钥。
- 系统级安装、权限扩大与生产副作用按 `luno-core/SKILL.md`〈授权与安全〉判定；仅生成未生效的配置无需确认。
- 本机测试按执行环境原生隔离；Docker/systemd 只在原生支持的 Linux 目标上执行。测试隔离硬边界：不带生产凭据、不挂生产数据或 Docker socket、不用特权或宿主命名空间；systemd 限额不等于权限隔离。真实网络、内核、磁盘、服务变更与重测试用独立测试 VM。

## 输出
输出依 `luno-core/SKILL.md`〈执行闭环〉；咨询与排障给判断、依据与命令（附预期结果）。

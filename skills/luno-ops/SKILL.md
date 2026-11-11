---
name: luno-ops
description: Linux/Shell/Docker/Compose、部署与网络代理、GitHub/CI/lint排障、脚本修复及Minis执行环境选址。
---
# LUNO｜Linux、Docker 与网络

## 范围

Debian/Linux、Shell、Docker/Compose、部署、服务、网络和代理（Surge 的配置与控制另见 `luno-surge`）。输出目标默认是 VPS：先探测实际系统，探测不到时按 Debian 13 + Zsh 假设并声明；这个默认**不构成连接授权**。iSH 只用于辅助生成和验证。参考环境以目标的实际证据为准：Debian 13、Zsh + Oh My Zsh、mise、Surge iOS；两端的执行环境分别是 Minis iSH/Alpine 和经 Debian 设备的 LobeHub。

## 资源与触发

路径相对技能根，按总控的加载规则读取；跨项取并集，中途新增的先补读。

- GitHub 仓库内容变更、git 提交或推送、PR/issue/release/Actions、GitHub 凭据的选用或轮换核查：`references/github.md`。
- 服务的部署、配置、运行和排障，systemd/PM2/Docker/Compose，服务端口和暴露面，Web 应用、Nginx、DNS、TLS 链路诊断：`references/service-runtime.md`〔分支 service-runtime〕。
- 远端工作目录和文件落位，过程产物和交付件，修改配置或生产文件，备份、快照、恢复和清理（包括服务修复需要改前备份时）：`references/service-runtime.md`〔分支 remote-files-backup〕。
- Minis 端的执行环境选址、脚本运行或测试、派发选址：`references/execution-environment.md`〔分支 execution-environment〕。只有不涉及执行和选址判断的纯咨询，或已确定是本机静态只读的检查（不运行不可信代码、不跨环境、不涉及派发选址）可以不读。
- 已选定 OnlyBoxes 之后的调用、传参、会话建立和复用、补装依赖、分块回传：`references/execution-environment.md`〔分支 onlyboxes〕。只有选址结论、不涉及具体调用和依赖准备时不必读。
- Minis 本机的 CFST（CloudflareSpeedTest）测速：`references/cfst.md`。只在 Minis 本机、脚本和模块都存在且恢复路径可用时执行，缺一项就停下报告。
- SSH 连接、非交互命令定位：`references/service-runtime.md`〔分支 ssh〕；不猜 PATH、主机指纹或凭据来源。

## GitHub 操作

改**规则仓库** `LucaLin233/Agent-Sync`（公开；工作副本 `/var/minis/shared/agent-sync`）之前，先加载 `luno-core/references/sync.md`〔分支 sync〕：该仓库有自己的并发和门禁纪律，按通用 git 流程操作会绕过它。

## 方法

- **先定假设和代价**：官方文档、上游 issue 或命令帮助能回答的，不靠试。远程和生产上的试验先说明假设、影响和回滚，不在同一现象上反复试。
- **先取最低证据集**：区分执行设备和目标环境；先确认工作目录、拓扑、版本、症状和成功标准，再取服务状态、近期日志、生效配置、监听端口和进程，涉及网络时加 DNS/TLS 和关键的一跳。不做无目标的全量采集；最小修改，分项验证。读取容器、主机环境和配置文件时只核声明的指定键，命令模板见 `references/service-runtime.md`〔分支 service-runtime〕。
- **lint**：按项目入口和 shebang 选择 lint；ShellCheck 不支持的 shell（如 zsh）不能声称通过。
- **批量替换**：先暂存并校验全部源和备份，再逐项切换；失败要显式退出并按授权恢复。禁止先删后复制，不依赖 `set -e` 或循环末尾的 `||` 兜底。
- **数据传递**：NUL 分隔的数据（如 `git diff --name-only -z`）不能经过 shell 变量或命令替换，用管道或 Python `subprocess` 的 bytes 输入保留分隔符，否则不能据下游结果判定验证通过。解析 JSON 前分别捕获 stdout、stderr 和退出码，确认 stdout 只有预期的 JSON，不混在一起解析。heredoc 里要由远端或子进程展开的变量，用带引号的定界符。执行权限按需要的主体最小设置并核对实际 mode，不把 `+x` 当作预期权限。
- **BusyBox/Alpine**：`cut -c` 按字节截断多字节字符，验证中文时不要用。涉及 Minis/iSH 的掩码误改和路径异常时，操作或下结论前另加载 `luno-platform/references/minis.md`〔分支 minis〕 并读它的运行时资源；非 Minis 目标不必加载。

## 安全与测试

- **连接配置**：SSH 主机清单和连接约定在 Minis 端的 `GLOBAL.md`（用户维护，不随技能分发）。本端没有这个文件时，向用户索取别名、主机名、用户、端口等非秘密参数；凭据只用已注入变量引用，不索取也不写入秘密值，不因为缺清单就去连默认主机。
- **凭据临时文件**必须由脚本自己在 trap 或清理路径里删除；用 `exec` 替换进程的脚本没机会清理，不能用它落盘私钥。
- **确认**：系统级安装、权限扩大和生产副作用按 `luno-core/references/execution.md`〔分支 safety〕〈授权与安全〉判定；只生成未生效的配置不需确认。
- **测试隔离**：本机测试按执行环境原生隔离；Docker/systemd 只在原生支持的 Linux 目标上用。测试的硬边界：不带生产凭据，不挂生产数据或 Docker socket，不用特权或宿主命名空间；systemd 限额不等于权限隔离。真实的网络、内核、磁盘、服务变更和重测试放在独立的测试 VM 里。

## 输出

咨询和排障给出判断、依据和命令（附预期结果）；其余按总控。

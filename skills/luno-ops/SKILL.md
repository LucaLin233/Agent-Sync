---
name: luno-ops
description: Linux/Shell/Docker/Compose、部署与网络代理、GitHub/CI/lint排障、脚本修复及Minis执行环境选址。
---
# LUNO｜Linux、Docker 与网络

## 范围

Debian/Linux、Shell、Docker/Compose、部署、服务、网络和代理（Surge 的配置与控制另见 `luno-surge`）。服务器运维交付的目标默认是 VPS：先探测实际系统，探测不到时按 Debian 13 + Zsh 假设并声明；这个默认**不构成连接授权**，也不覆盖已经明确的本机任务或执行环境。为服务器交付在 iSH 辅助生成和验证，不代替目标环境验收；需要本机能力的任务、可信测试及执行环境选择，仍按〈资源与触发〉及命中资源，不因上述默认改派或换环境。参考环境以目标的实际证据为准：Debian 13、Zsh + Oh My Zsh、mise、Surge iOS；两端的执行环境分别是 Minis iSH/Alpine 和经 Debian 设备的 LobeHub。

## 资源与触发

路径相对技能根，按总控的加载规则读取；跨项取并集，中途新增的先补读。

- GitHub 仓库内容变更、git 提交或推送、PR/issue/release/Actions、GitHub 凭据的选用或轮换核查：`references/github.md`。改规则仓库 `LucaLin233/Agent-Sync`（公开；Minis 工作副本 `/var/minis/shared/agent-sync`）之前，另读 `luno-core/references/sync.md`〔分支 sync〕：它有自己的并发和门禁纪律，通用 git 流程会绕过它。
- 服务的部署、配置、运行和排障（systemd/PM2/Docker/Compose、端口与暴露面、Nginx、DNS、TLS）：`references/service-runtime.md`〔分支 service-runtime〕。
- 远端工作目录和文件落位、交付件、改配置或生产文件、备份、快照、恢复和清理：`references/service-runtime.md`〔分支 remote-files-backup〕。
- SSH 连接和非交互命令定位：`references/service-runtime.md`〔分支 ssh〕。
- Minis 端的执行环境选址、脚本运行或测试、派发选址：`references/execution-environment.md`〔分支 execution-environment〕；纯咨询，或已确定在本机做的静态只读检查不必读。
- 已选定 OnlyBoxes 之后的调用、会话、依赖和回传：`references/execution-environment.md`〔分支 onlyboxes〕。
- Minis 本机的 CFST（CloudflareSpeedTest）测速：`references/cfst.md`。

## 方法

- **取证有界**：区分执行设备和目标环境，先确认工作目录、拓扑、版本、症状和成功标准，再按需取证，不做无目标的全量采集；最小修改，分项验证。读容器、主机环境和配置文件时只核声明的指定键，命令模板见 `references/service-runtime.md`〔分支 service-runtime〕。
- **lint**：按项目入口和 shebang 选 lint；ShellCheck 不支持 zsh，zsh 脚本不能声称已通过 ShellCheck。
- **批量替换**：先暂存并校验全部源和备份，再逐项切换，失败显式退出并按授权恢复。禁止先删后复制，不依赖 `set -e` 或循环末尾的 `||` 兜底。
- **验证数据不失真**：NUL 分隔的数据（如 `git diff --name-only -z`）不经过 shell 变量或命令替换，改用管道或 Python `subprocess` 的 bytes 输入；解析 JSON 前分开捕获 stdout、stderr 和退出码，确认 stdout 只有预期的 JSON。做不到就不能据下游结果判定验证通过。
- **BusyBox/Alpine**：`cut -c` 按字节截断多字节字符，验证中文时不要用。Minis/iSH 上的掩码误改或路径异常，操作或下结论前另读 `luno-platform/references/minis.md`〔分支 minis〕 及其运行时资源。

## 安全与测试

- **连接配置**：SSH 主机清单和连接约定在 Minis 端的 `GLOBAL.md`（用户维护，不随技能分发）。本端没有时向用户索取别名、主机名、用户、端口等非秘密参数，不因缺清单就去连默认主机；凭据只用已注入的变量引用。
- **凭据临时文件**必须由脚本自己在 trap 或清理路径里删除；用 `exec` 替换进程的脚本没机会清理，不能用它落盘私钥。
- **确认**：只生成未生效的配置不需确认。
- **测试隔离**：Docker/systemd 只在原生支持的 Linux 目标上用。测试不带生产凭据，不挂生产数据或 Docker socket，不用特权或宿主命名空间；systemd 限额不等于权限隔离。真实的网络、内核、磁盘、服务变更和重测试放在独立的测试 VM 里。

## 输出

咨询和排障给出判断、依据和命令（附预期结果）；其余按总控。

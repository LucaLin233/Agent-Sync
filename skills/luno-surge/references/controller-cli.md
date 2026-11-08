# Minis Surge CLI

`surge-cli --remote` 的传输和命令行面的 Python 重实现，面向 iOS 上的 iSH/Minis。

## 传输协议

External Controller 是以 CRLF 分隔的命令和结果流：

1. 客户端发送密码 + CRLF；
2. 服务端回 welcome JSON + CRLF；
3. 客户端发送一行文本命令 + CRLF：动词裸写，后面的每个参数用双引号包裹，如 `rule "match" "example.com"`；
4. 服务端回一个结果 JSON 对象，或一串 JSON 事件对象。

含 CR/LF 的参数在本地就拒绝；普通引号和反斜杠在引号字段里原样发送，和官方客户端一致。编码对齐的版本依据见 `platform-compatibility.md`。

客户端不做 HTTP API 转换。多数命令参数由 Controller 自己解析，所以普通命令的行为随所连的 Surge 版本；客户端只复现官方 CLI 已知的本地转换：`summary`、`profile diff`、`rule temp`、`watch speed`、`script evaluate <file>`（含 mock-type 名到数字 ID 的转换）。macOS 上的在线 `plugin` 操作是普通 Controller 命令；官方 CLI 的离线 `plugin validate`/`pack` 依赖本地 macOS 工具，在 iSH 里**有意不可用**。`--raw` 返回经客户端脱敏的 Controller JSON（紧凑序列化），不保证和服务端原文逐字节一致。

## 安装与凭据

`/usr/local/bin/surge-cli` 是指向 `scripts/surge_cli.py` 的符号链接；默认 Controller 是 `127.0.0.1:6170`，可以用 `SURGE_CLI_REMOTE` 或 `--remote` 覆盖。

凭据按这个优先级取：先 `--password-stdin`，再 `SURGE_API_KEY`（Minis 推荐，存在「设置 → 环境变量」）。客户端非交互：不建也不读密码文件，不在 TTY 提示输入。`SURGE_API_KEY` 缺失时给出 Minis 环境变量的设置入口，不要让用户把密码发到聊天里。调用安全、危险操作再确认和数据最小化按入口 §3。

## 远程管理

依据官方指南 [Surge Remote Management](https://kb.nssurge.com/surge-knowledge-base/guidelines/remote-management)（2026-09-26 读；加 `.md` 取 Markdown 源）。它描述的是官方控制器，不代表每个特性本实现都有。

- **Ponte 与远端 loopback**：有用户授权的 Ponte 通路时，`--remote <name>.sgponte:6170` 可以到达远端 Mac 的 loopback，它的 External Controller 可以继续只绑 `127.0.0.1`，不必为此放宽监听。Surge UI 原生的 Ponte 免密发现和这个 CLI 的 host/port/password 连接是两回事，凭据处理不变。
- **iOS 可达性**：Surge iOS 不能当 Ponte 服务端；蜂窝网络下远程 External Controller 连接会被拒，Wi-Fi 下要开启 Allow Access From Wi-Fi。这些是入站限制，不能证明同机 Minis 的 loopback 可用，要看实际路径。
- **USB**：官方 Mac Dashboard 能管理 USB 连接的 iPhone/iPad（包括走蜂窝时），本 CLI 不实现；不要从通用能力表推断支持 USB。
- **认证封禁**：30 秒内 10 次密码错误会临时封禁来源 IP 或本地进程。先停止反复认证，判断「服务死了」之前先考虑是否被封禁。`security ban` 的查看和清除语法见命令参考；清除封禁不是自动的测试恢复步骤。
- **Ponte 与 HTTP API**：官方对比表把 HTTP API 和 Web Dashboard 标为不支持 Ponte。这说的是原生远程管理集成，不否定「经已有的 `.sgponte` 隧道访问 HTTP 端口」；以实际端点为准。
- **官方与 Minis CLI 的差异**：Mac CLI 不带命令时进交互模式，Minis 打印帮助。指南里的 Mac 专属能力（Gateway 设备、插件、无人值守升级）不是命令规范，也不授权升级或重启。远程功能缺失可能是版本不匹配或 Mac 专属，不一定是传输故障；官方建议两端版本对齐（必要时都用 beta），先诊断，不自动升级。

## 兼容性

多数命令透明转发。status、version、mode、features、策略组、rule match/explain、DNS lookup/trace、modules、GeoIP、performance 和 macOS VMNET 等常用命令有可读的格式化输出，其余打印美化的 JSON；脚本和需要精确 Controller 数据时用 `--raw`。VMNET、`restart-engine` 的平台和协议门槛按 `references/platform-compatibility.md`；`reload` 和完整重启不等价，不能因为回执成功就忽略对连接、缓存和临时规则的影响。

`--check <path>`（`-c <path>`）使用 Surge 官方 beta HTTPS 校验服务（`https://services.nssurge.com/v1/config/validate`），因为 iSH 没有 macOS 的本地解析器。它只读显式指定的 UTF-8 文件，以 JSON 的 `profile` 字段 POST 上去，按官方 CLI 的格式打印 `OK` 或 `Failed: ...`，退出码 0 或 1。**这是上传**：绝不隐式替换或上传活动 profile；profile 可能含服务器地址、订阅 URL、用户名、密码、PSK 等秘密，先告知用户，必要时脱敏。

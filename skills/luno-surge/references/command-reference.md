# Surge 命令参考：Minis 覆盖层

查命令语法或 key-path 时，先完整读本覆盖层，再完整读目标命令需要的 `luno-surge/references/upstream-command-reference.md` 相关部分：适用的全局语义（§1 CLI Usage 和 Response envelope，以及判断命令是否存在所需的 §2 目录）和对应的命令节（§3/§4 及其中明确的交叉引用）。未知的命令、节或定位不到的交叉引用不要猜，停止依赖它的部分；动作之前还要按入口的触发读对应的专题资源。

原件是部署时按 manifest 哈希从官方包取件装入的官方快照，公开仓库不含；没装入就停止依赖，不猜内容。它**不是本端的执行许可**，版本或平台条件未知或不满足时不执行。冲突时的优先级：安全与授权底线 → 入口和对应专题 → 本覆盖层 → 官方原文。协议、平台和历史验证只以 `platform-compatibility.md` 为准，官方原文里的协议号和版本描述只作历史说明。

## 不适用于 Minis 的官方说法

- **超时**：官方 §1 的「无进展 60 秒」不适用于本客户端。现行实现里，建立连接超时 **8 秒**；认证、普通命令和有限事件流的 socket 读超时 **30 秒**（不是整项任务的总时限）。有限流指 `test-policy-bandwidth`、`benchmark encryption`、`test-ponte`。`watch <event...>`、`log watch`、`diagnostics` 进入连续流读取后不设 socket 读超时（包含首帧等待），要按诊断资源由外部限时停止；它们的认证阶段仍是 30 秒。`--check` 的网络请求超时 30 秒。这些只是陈述现行实现，不据此修改客户端阈值，也不把官方的 60 秒当本端保障。
- **输出和凭据**：官方 §1 关于 rendered 默认、`--raw`、密码文件、其他环境变量、TTY 提示、无命令时进交互和 Mac 可执行位置的说明，不是 Minis 的实现。本端优先用 `--raw`，它的 JSON 已由客户端脱敏、不是服务端原文；客户端非交互。凭据优先级、非交互和传输按 `references/controller-cli.md`，授权和不回退的边界按入口 §3。
- **`--check`** 在本端是远程上传，不是本地解析，调用前完整读 `references/controller-cli.md` 的上传和告知规则。
- **`lsp [--stdio]`** 是官方离线编辑器的语言服务器，Minis 不实现，不得向 Controller 转发，不当一次性校验用，也不和 remote 或认证参数一起用；官方 VS Code 扩展需要 Surge Mac 6.10.0+，不是 iOS 能力。
- **修改前的收集**：官方 §5 建议修改前收集 `environment`、`dump policy`、`dump profile`，本端不作默认。先按入口预检，只在任务必要时最小读取，不得默认全量收集 `dump policy` 或 `dump profile`；后者只取需要的字段、脱敏引用、不写进支持包。多帧、真实流量和临时规则清理先读 `references/diagnostics.md`。
- **官方示例**：插件的 `insecure: true`、`token=…` 等不作本端默认，敏感参数和平台限制按 `references/platform-compatibility.md`。其他官方示例也要先核对授权、平台和专题边界，不能直接当执行指令。

## Surge 6 的分节与捕获过滤

官方新快照包含 `profile section list`/`get`/`set` 和 `capture-filter`，版本和协议门槛见 `references/platform-compatibility.md`。官方 `get` 可能含密码；官方的 `--raw` 和本端脱敏的 `--raw` 不是同一个接口。

本端还没实现 `profile section set` 的本地文件和 stdin 转换，因此**禁止通过本端调用 `set`（含 `--raw`）**。现有的桥会在建立 Controller 连接、读文件和取密之前用固定错误拦下这个命令，但这只是程序护栏，不等于适配了这个命令，官方的文件和 stdin 语义仍不可用；也不要靠猜 Controller 编码去实现它。`list`/`get` 不因为写入风险而整体禁用，但仍受「读之前已有明确的非秘密来源」和当次授权的限制，不能拿脱敏输出回写。要永久修改内容，执行前完整读 `references/http-api.md` 的安全入口规则。

## 必要语法索引

调用形式：`surge-cli [--remote host:port] [--password-stdin] [--raw] <command> [args...]`。入口 `/usr/local/bin/surge-cli` 是自建的 Python 桥，不是官方二进制；默认端点和远端选择见 `references/controller-cli.md`。短选项：`--remote`/`-r`、`--check`/`-c`、`--help`/`-h`。不带命令时打印帮助；命令关键字由所连的 Controller 解析。

- 命令全集和响应格式看官方 §2/§1.2；具体参数和响应字段看 §3；批量 `set` 和环境 key-path 看 §4；§5 只在不和本覆盖层及本地规则冲突时参考。
- `set` 里的 `<nil>`/`(null)` 表示 null。shell 里含 `<nil>` 的赋值要整体加引号，避免被当成重定向，例如 `surge-cli set 'AutoPolicyGroupOverride.Streaming=<nil>'`。
- 临时规则的语法、名称和清理以官方 §3.9、实际返回和 `references/diagnostics.md` 为准；不得猜索引，也不能用清空全部代替只清理本次新增的项。
- `proxy-runtime-status` 可以传策略名或 line-hash；`dump policy` 给策略名、不打印 line-hash，line-hash 要从 `policy-group list` 或 `dump policy-group-sub-policies` 取，判读见 `references/diagnostics.md`。

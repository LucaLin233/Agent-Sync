# Surge 命令参考｜Minis 覆盖层

查询命令语法或 key-path 时，先完整读本覆盖层，再完整读目标命令所需的 `luno-surge/references/upstream-command-reference.md` 节：适用全局语义（§1 CLI Usage／Response envelope，及命令存在性所需的 §2 目录）和对应命令节（§3／§4 及其中明确交叉引用）。未知命令、未知节或未能定位的交叉引用不可猜，停依赖。动作前还须按 `luno-surge/SKILL.md` 触发完整读取对应专题。原件是部署时从官方包按 manifest 哈希取件装入本端的官方快照（公开仓库不含该文件，未装入即停依赖、不猜内容），**不是本端执行许可**；未知或不满足版本／平台条件不得执行。冲突时：安全与授权底线 → `luno-surge/SKILL.md` 及对应专题 → 本覆盖层 → 官方原文。协议、平台及历史验证唯一执行判据为 `platform-compatibility.md`；本文件不另设门槛，官方原文的协议号／版本描述仅作历史说明。

## 不适用于 Minis 的官方建议

官方 §1 的“无进展 60 秒”不适用于本客户端：现行建立连接超时 **8 秒**，认证、普通命令与有限事件流 socket 读超时 **30 秒**（不是整项任务总时限）。有限流为 `test-policy-bandwidth`、`benchmark encryption`、`test-ponte`；`watch <event...>`、`log watch`、`diagnostics` 进入连续流读取后不设 socket 读超时，包含首帧等待，仍须按诊断资源外部限时停止；认证阶段仍为 30 秒。`--check` 网络请求超时 **30 秒**。这些取值只陈述现行实现，不修改客户端阈值，不把官方 60 秒当本端保障。

- 官方 §1 对 rendered 默认、`--raw`、密码文件／其他环境变量／TTY 提示、无命令时交互及 Mac 可执行位置的说明不作为 Minis 实现：本端优先 `--raw`，其 JSON 已由客户端脱敏、不是服务端原文；客户端非交互。凭据优先级、非交互与传输须按 `references/controller-cli.md`，授权及不回退边界按 `luno-surge/SKILL.md` §3。
- 官方 §1 的 `--check` 本端是远程上传，不是本地解析；调用前完整读 `references/controller-cli.md` 的上传与告知规则。`lsp [--stdio]` 为官方离线编辑器语言服务器，Minis 不实现，不得向 Controller 转发，不作一次性校验，也不与 remote／认证参数同用；官方 VS Code 扩展需 Surge Mac 6.10.0+，不是 iOS 能力。
- 官方 §5 修改前收集 `environment`、`dump policy`、`dump profile` 的建议不作默认：先按入口预检，仅在任务必要时最小读取；不得默认全量收集 `dump policy`／`dump profile`。后者只取所需字段、脱敏引用、不写支持包；多帧、真实流量与临时规则清理先读 `references/diagnostics.md`。
- 官方插件 `insecure: true`、`token=…` 等不作本端默认；敏感参数及平台限制依 `references/platform-compatibility.md`。其他官方示例亦须先核授权、平台与专题边界，不能直接当执行指令。

## Surge 6 分节与捕获过滤

官方新快照包含profile section list／get／set和capture-filter；版本／协议唯一判据见 `references/platform-compatibility.md`。官方get可含密码，官方--raw与本端脱敏--raw不是同一接口。本端尚未实现profile section set的本地文件／stdin转换，因此禁止通过本端调用set（含--raw）；现有桥已在建立 Controller 连接、读取文件与取密之前以固定错误拦截该命令（T8 已通过），但该程序护栏不构成对该命令的适配，官方文件/stdin 语义仍不可用。list/get不因该写风险整体禁用，但仍受读前非秘密来源与当次授权限制，不可拿脱敏输出回写。永久内容编辑执行前完整读 `references/http-api.md` 的安全入口规则；本批不通过猜Controller编码实现set。

## 必要语法索引

调用：`surge-cli [--remote host:port] [--password-stdin] [--raw] <command> [args...]`；入口 `/usr/local/bin/surge-cli` 是自建 Python 桥，非官方二进制。默认端点／远端选择见 `references/controller-cli.md`；`--remote`／`-r`，`--check`／`-c`，`--help`／`-h`。无命令打印帮助；关键字由所连 Controller 处理。

- 命令全集／响应：官方 §2／§1.2；具体参数／响应字段：§3；批量 `set` 与环境 key-path：§4；§5 只在不与覆盖层及本地规则冲突时参考。
- `set` 的 `<nil>`／`(null)` 表示 null；shell 中含 `<nil>` 的赋值须整体引用，如 `surge-cli set 'AutoPolicyGroupOverride.Streaming=<nil>'`，避免重定向。
- 临时规则语法、名称与清理以官方 §3.9、实际返回及 `references/diagnostics.md` 为准；不得猜索引或用清空全部代替清理本次新增项。
- `proxy-runtime-status` 可用策略名或 line-hash；`dump policy` 给策略名、不打印 line-hash，后者从 `policy-group list`／`dump policy-group-sub-policies` 取；判读见 `references/diagnostics.md`。

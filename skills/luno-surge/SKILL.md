---
name: luno-surge
description: 创建、审查、解释、修复和诊断 Surge 配置与运行状态；用户给配置、模块、日志、报错、截图，或要求通过 CLI/External Controller 实查、控制 Surge 时使用。
---

# Surge（iOS-first）

默认 iOS；仅明确提 Mac、给 Mac-only 证据或需跨平台时进 macOS/shared。iOS 不套 Mac 文件系统或 Gateway/System Proxy/Enhanced Mode；shared profile 用 `#!IOS-ONLY`、`#!MACOS-ONLY`、`#!TVOS-ONLY` 隔离。

## 1. 路由

先读用户材料，保留顺序、注释、策略名与资源 URL。配置走 §4，运行状态走 §5；关联时只读检查→最小修改→立即复验。版本／平台／语义敏感时读 `references/official-sources.md` 查官方资料；不套其他客户端语法、不猜字段／能力。

执行前完整读 `references/platform-compatibility.md`：平台／协议／历史验证的**唯一执行判据**；未知或不满足不得执行，本文件和官方原文不设协议门槛。异常先 `surge-cli --raw version`；Unknown/Unsupported command 再查 `help <command>`，勿把 Mac-only 当 iOS 能力。

## 2. 引擎状态预检

依赖 Surge 联网／代理／DNS／脚本／API 前查当前实例 `surge-cli --raw status`／`--raw environment`；EOF／超时后重查。切策略／模块／功能前核目标存在；纯文档不连接。

Controller/API 响应≠引擎正常；核 Suspend 与 VPN/引擎，不假设暂停字段同名；不足则标未确认、请用户看界面。EOF／超时≠暂停或节点／凭据／目标故障；不擅自恢复、重启、换模式／实例。获准后重读状态再试，仍失败再查路由、DNS、节点与目标；不默认全量 `dump policy`、日志或 Profile。

## 3. 安全与平台边界

- 不编造节点、策略名、证书、凭据、订阅 URL 或 Controller 返回。
- Controller 密码／HTTP API Key 仅取 `SURGE_API_KEY`／`--password-stdin`，不入 argv、文件、日志或回复。非交互，不读凭据文件、不从 TTY 补取；缺失给[设置入口](minis://settings/environments?create_key=SURGE_API_KEY&create_value=)，不让用户在聊天发密码。
- `dump profile`、请求正文、日志可含节点／订阅 URL／隐私：仅必要时最小读取、脱敏引用、不进支持包。启用 MITM、Rewrite、脚本、抓包或远程控制前说明影响；hostname 不默认 `*`。
- `stop`、`restart-engine`、切换/更新 profile、批量终止连接、改变模式或策略前**再次单独确认，即使整批已获批**（严于 `luno-core`）；`stop` 须用户明确要求。`reload`≠`restart-engine`：后者完整重启、关连接、清缓存与临时规则，须单独授权。
- 临时规则立即生效、优先于 Profile，停引擎后失效；`rule temp flush` 清空全部，**禁作本次默认清理**；只删本次新增项，不猜索引。清理及多帧处理前完整读 `references/diagnostics.md`。
- `http probe` 发真实 HEAD；DNS／节点／带宽／加密 benchmark 有真实流量／负载，均按需。`watch`／`diagnostics`／benchmark 为 JSON Lines，限流读至 `hasMore=false`；长期订阅外部限时停止，首帧≠终态。
- `--check` 联网上传官方服务，非本地解析；禁自动上传活动 Profile，先告知、必要时验证脱敏副本。
- `policy-descriptor` 可含密码/PSK，不同于认证：只经 stdin／`--descriptor-file -` 输入，不落盘、不写配置、不读凭据文件；`SURGE_API_KEY` 仅认证。

## 4. 配置

核 section／行语法、选项、最低版本／平台、策略／组成员／hostname 引用（MITM/Rewrite/Script）、远程资源格式、规则顺序／`FINAL`、DNS 循环／绕过、模块 `%APPEND%`／`%INSERT%`、脚本 `$done()` 路径及无关数据收集。

最小改动、保持路由意图；交完整文件或精确定位 patch。模块单目的、可逆，说明覆盖／插入／追加与前提；参数 `<面板名>_` 前缀，`#!arguments` 逗号分隔、默认值无逗号（多值用 `|`）、占位符 `{{{name}}}`。无 Controller：导入/应用→查 parser warning→复现→请求查看器核 matched rule／policy；交验证／回滚。

分节编辑前完整读 `references/http-api.md` 的“安全分节写入”，按 `references/platform-compatibility.md` 核平台、版本与协议。官方 CLI／HTTP／内置 MCP 的分节能力不等于本端桥已实现文件／stdin转换；只处理合成或读前已有明确非秘密来源且获准的完整单节，不先读未知节再脱敏。整节替换会校验并reload，按§3再次单独确认；先合成验证不授权活动配置变更。

## 5. CLI

`/usr/local/bin/surge-cli` 是 `scripts/surge_cli.py` 自建 Python 3 桥，**非官方 Mac 二进制**。默认同机 Controller；`SURGE_CLI_REMOTE`／`--remote` 仅显式指定，未经用户指定不连外部主机。传输／凭据／`--check` 前完整读 `references/controller-cli.md`。

优先 `--raw`＝**客户端脱敏 JSON，非服务端原文**（覆盖包内“原始”说法）。查命令语法／key-path：先完整读 `references/command-reference.md` 覆盖层；再按目标命令读取 `references/upstream-command-reference.md` 的适用全局语义（§1 CLI Usage／Response envelope，及命令存在性所需的 §2 目录）和对应命令节（§3／§4 及其中明确交叉引用）。未知命令、未知节或未能定位的交叉引用不可猜，停依赖；官方原件不随公开仓库分发：部署时从官方包按 manifest 哈希取件装入本端 `references/upstream-command-reference.md`，未装入或哈希不符即停依赖、不猜内容（取件方法见 `references/SOURCE.md`〈取件与部署〉）；原件不授权。路由／DNS／临时规则／性能／Tailscale/WireGuard 前完整读 `references/diagnostics.md`；调试路由优先临时规则、不改 Profile，变更前后读最窄相关状态。macOS 插件配置先读 parameters schema 与 `references/plugin-authoring.md`。

## 6. 回退

Controller 不可用或需 `/v1/*`／Prometheus：先完整读 `references/http-api.md`（含远程明文风险），再用 `scripts/surge_ios.py`。核端点、认证／`X-Key`；默认同机，`SURGE_HTTP_API_BASE` 指活动实例或可信局域网均须用户指定；危险操作按 §3 再确认。未入 Profile 节点用 `scripts/test_policy_descriptor.py`，不改配置，凭据按 §3。

## 7. 交付

安装／验收时读 `references/SOURCE.md` 的〈安装与验收〉；取源、追新或官方导入时读〈官方上游定位与更新核对〉、`references/upstream-manifest.json` 及〈导入与失败恢复〉；打包／投递时读〈打包与投递〉；模块推送时读〈模块推送〉。这些分支仍须遵守〈通用门禁〉；暂存落点授权、内容／模式漂移即停、失败恢复与公开发布另授权不得省略。同步人工合并，禁整体覆盖入口／短覆盖层。只用 `scripts/package_release.py` 打包，禁含凭据、profile、抓包、请求正文、数据库、运行输出。`references/upstream-SKILL.md` 同样只在部署取件后存在，仅上游对照／官方导入审查时读，未装入即停；官方来源、包身份／版本与哈希追新信息以 `references/SOURCE.md` 与 `references/upstream-manifest.json` 的登记为准。

交结论、修改/操作、验证、回滚/注意；区分实操／建议、规则推演／端到端成功、版本快照／当前实测。

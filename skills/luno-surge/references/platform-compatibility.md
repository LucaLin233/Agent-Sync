# 平台与协议差异

协议门槛、平台限制和历史验证结论只以本文件为准。其他文件（入口、`controller-cli.md`、命令参考和插件指南等）里的协议号或版本说法与本文件冲突时，按本文件执行；来源快照中的描述不自动成为当前设备能力。

下面是有日期的版本快照，不代表当前运行的版本。能力异常时先跑 `surge-cli --raw version`，核对 Surge、Core、平台和 Controller Protocol；不要把 App 发行版本和 Controller 内部版本混为一谈。

## 命令门槛

| 能力 | 最低 Controller Protocol | 平台 | 说明 |
|---|---|---|---|
| `rule`、`dns`、`http probe`、`security ban` | 20 | 共享 | |
| `geoip`、性能/规则使用/虚拟 IP 的 dump、`benchmark rule-matching` | 22 | 共享 | |
| `vmnet status`/`arp`/`ndp`/`ra` | 23 | 仅 macOS | 排查 Enhanced/Gateway Mode 的接口、ARP/NDP 邻居和 IPv6 RA 接管；iOS 返回 `Unsupported command` 属正常 |
| `plugin list`/`info`/`parameters`/`load-unpacked`/`configure`/`enable`/`disable`/`select`/`uninstall` | 24 | 仅 macOS | iOS 返回 `Unknown command`；`plugin install` 尚未开放 |
| `restart-engine` | 24 | 共享 | 影响和再确认按入口 §3 |
| logbook 的大小截断语义 | 27 | 共享 | 本行至 capture-filter 行的协议数字沿用官方 Mac 6.11.0 命令参考（12680）的来源记录 |
| `dump dns-lookup-times`、`traffic-stat-hourly`、`summary.network` | 28 | 共享 | |
| `policy-usage`、`traffic-stat-hourly.policy`、`network-changed` 事件 | 29 | 共享 | |
| `summary.network` 的 ipv4/ipv6 | 30 | 共享 | |
| `profile section list`/`get`/`set` | 31 | 共享 | 本端桥不实现 `set`，见下文 |
| `summary.network` 的 encrypted-dns | 33 | 共享 | |
| `traffic.testBytes` | 35 | 共享 | |
| `capture-filter` | 36 | 共享 | 改捕获过滤会影响记录范围，按既有授权和数据最小化执行 |
| `capture-session list`/`dump`/`data` | 未核实，见下文 | iOS / macOS | 读取已存盘的 HTTP 抓包会话，取代 `retrieve-data` |
| `dump traffic-stat-breakdown` | 未核实，见下文 | iOS / macOS | 按两个维度汇总流量 |
| `dump traffic-stat-records` | 未核实，见下文 | iOS / macOS | 读取指定期间的流量及请求计数记录 |

上述已列数字只是有来源版本的能力条件，不代表本端设备已验收。官方 CLI 手册为 capture-session、dump traffic-stat-breakdown 和 dump traffic-stat-records 标注 iOS 6.0.0+ / Mac 6.11.0+，但这三项的最低 Controller Protocol 数字尚未核实，不以未核实的数字判定支持或拒绝，也不从发行版本反推协议号。执行前仍须按入口核对当前实例的平台、发行版本和 build，并取得当前实例支持目标命令的证据；必要条件未知或不满足时停止该项，不能只凭命令列在手册或历史 Protocol 25 推断可用。依据：https://manual.nssurge.com/tools/cli.html（2026-11-11 读取）。

`plugin validate`/`pack` 是官方 macOS CLI 的本地离线工具，不是 Controller 命令，Minis/iSH 客户端不实现。配置插件前先用 `parameters` 读 schema，API Key 等敏感参数不能出现在回复、日志或公开包里；开发契约见 `references/plugin-authoring.md`；未覆盖的当前格式按官方资料核实，缺依据就停止该项。引用上游插件示例时，不把 `insecure: true` 或命令行里的 `token=…` 当本端默认：保持证书校验，密钥只用已授权注入的变量经已核实的安全入口传递，无法避免进入参数或日志时暂停相关配置。

## Surge 6：分节编辑与内置 MCP

- HTTP 分节编辑和内置 MCP 的最低版本是 iOS 6.0.0 / Mac 6.11.0，仍要核对所选实例实际的平台、营销版本和 build。2026-11-03 时 iOS 6 的发布页是 TestFlight，不是 App Store 稳定版。
- iOS 6 的 MCP 另需订阅已解锁或有效试用的权益；装了这个版本或有 TestFlight 资格，都不能证明有这项权益。
- 命令参考和插件指南取材的官方版本和原文哈希，以当前的 `upstream-manifest.json` 为来源证据；拿到安装包或有来源记录，不表示官方原件随包分发，也不表示新能力已经设备实测。
- Minis 自建桥不实现 `profile section set` 的本地文件和 stdin 转换，但保留 `list`/`get` 的只读路径，不因为 `set` 的风险一律禁用。官方 `get` 可能返回含密码的真实正文，本端 `--raw` 仍是客户端脱敏的 JSON，两者都不会自动成为获准的回写原稿。读取和安全写入按 `references/http-api.md` 执行；这些新能力没有设备实测，历史的只读和重启验收不扩大到它们。

## 历史验证

| Controller build | 日期 | 平台与版本 | 覆盖范围 |
|---|---|---|---|
| 3822 | — | — | 首次验证 `reload` 和 `restart-engine` 的差异（关闭连接、清除缓存和临时规则） |
| 3830 | 2026-09-02 | 正式版 Surge iOS 5.22.0（Controller 内部版本 5.102.0），Protocol 25 | 认证、CRLF 文本命令、JSON Lines 响应和 `restart-engine` 的逐项结论 |
| 3842 | 2026-09-15 | 同上 5.22.0 / Protocol 25 | 复测认证和只读命令；`restart-engine` 未复测 |
| 3852 | 2026-09-27 | Controller 内部版本 5.102.0 | `scripts/acceptance.sh --controller` 和 `--network` 两档只读验收全部通过（握手与能力、`status`、`summary`、`dump performance`、`rule match`、`rule temp list`、`feature list`、`module list`、`watch speed` 首帧、Prometheus metrics、官方校验服务上传合成的无秘密 profile、`dns lookup`），全程没改 Surge 设置；变更类操作（`restart-engine`、切换 profile）未复测，仍按 3830/3822 |

Protocol 25 仍兼容旧的 JSON `argv` 请求，但本客户端已对齐正式版 Surge Mac 6.9.0 build 12250 的文本编码。

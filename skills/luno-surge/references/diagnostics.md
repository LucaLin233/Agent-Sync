# Surge 按需诊断

只在实际排查对应功能时读取，并先按入口 §2 做完引擎状态预检。命令语法、key-path 和响应字段以 [command-reference.md](command-reference.md) 为准，协议门槛和平台限制以 [platform-compatibility.md](platform-compatibility.md) 为准。这里只写 Surge 特有的行为，不用其他代理软件的语法代替。

## 流量与多帧输出

- `http probe <url> [policy]` 会发真实的 HEAD 请求；DNS、节点、带宽和加密 benchmark 同样会产生真实流量或负载。只在任务需要时执行，执行前确认目标和影响。
- `diagnostics`、各种 `watch`、带宽和加密 benchmark 持续输出 JSON Lines：按 `hasMore=false` 或结束载荷判断完成，不能拿首帧当最终结果；长期订阅要限时停止。

## 路由与 DNS

```sh
surge-cli --raw rule match example.com
surge-cli --raw rule explain https://example.com
surge-cli --raw dns trace example.com
surge-cli --raw geoip 1.1.1.1
```

`rule match` 快速看命中的规则和最终策略；`rule explain` 给出完整的策略组决策路径，回答「为什么这样走」时优先用它。

需要改变路由才能验证、并且用户授权时，优先用临时规则，不改 Profile；临时规则立即生效，优先于 Profile 规则。先列出已有的规则，记下本次新增的项：

```sh
surge-cli rule temp list
# 确认 Proxy 存在且获准测试后再添加：
surge-cli rule temp add "DOMAIN-SUFFIX,example.com,Proxy"
surge-cli rule temp list
```

`rule temp flush` 会清空全部临时规则，禁止当作本次测试的常规清理。只移除本次新增的规则；具体的标识和 remove 参数先核对 [命令参考](command-reference.md) 和实际返回，不能猜索引，也不能清掉用户已有的规则。

## 性能与隧道

```sh
surge-cli --raw dump performance
surge-cli --raw dump rule-usage
surge-cli --raw benchmark rule-matching
surge-cli --raw benchmark encryption 25
```

`dump policy`、`dump performance`、`dump rule-usage` 和各种 benchmark 都按需读取，不作为每次任务的前置或基线。`benchmark encryption` 测的是 Surge 所在设备的本地加密性能，不是网络带宽。

排查 Tailscale/WireGuard 时，用 `proxy-runtime-status` 传策略名读取运行时状态，名称含空格要加引号。`line-hash` 仍然可用，但 `dump policy` 已经不打印它，要从 `policy-group list` 或 `dump policy-group-sub-policies` 的方括号里取：

```sh
surge-cli --raw proxy-runtime-status "<策略名>"
surge-cli --raw proxy-runtime-status POLICY::…
```

优先检查握手、底层策略、Tailscale 会话、Exit Node、DERP 和 peer path，不要先做宽泛的日志搜索。

`test-policy-udp` 需要真实的 Internet 出网：对 P2P 的 Tailscale/WireGuard 策略（`Test Capability: rtt-only`）会返回 not-applicable，这类策略改用 `test-policy` 取 RTT。这个错误**不是**隧道故障的证据。

## CoreDevice/RSD 同机回环

只在这个场景下评估 `[IP Rewrite]` 的目标地址 `reflect`，以及该地址 `/32` 的 `tun-included-routes`；先核对目标地址、现有路由、模块和配对前提，版本和平台条件按 `references/platform-compatibility.md`。

- 不自动改路由，不整段覆盖已有路由，也不照搬上游「无副作用」的保证。
- TCP connect 成功不等于协议成功：任意端口都能瞬间连上却没有数据，可能是假通。要分别确认 TCP、Pair-Verify、RSD 会话和获准的只读业务返回。
- 上游要求导入模块后重启 VPN。不为验证而自动导入、启停模块或重启 VPN；需要的动作先列出影响和回滚，按入口和既有授权执行。前提没满足就不能说验证通过。
- 配对凭据或设备访问缺授权时停止这一步，不读凭据文件取密。

来源与许可：OpenMinis/MinisSkills，MIT 精选改写；Copyright (c) 2026 OpenMinis；Copyright (c) 2026 OpenMinis contributors；本地许可决定与边界见本包 references/SOURCE.md〈第三方精选改写〉。完整许可随包见 ../LICENSE.openminis.txt、../LICENSE.openminis-ios-dev.txt；固定提交、取材路径与日期见仓库 skills-sources.md。

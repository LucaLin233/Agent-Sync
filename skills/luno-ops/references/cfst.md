# CFST 测速（Minis 本机）

固定用法和脚本由用户 2026-10-30 指定；下面的脚本行为是 2026-10-31 静态核对的结果，没有实际执行过测速。

## 前提

- 只在 **Minis 本机（iSH）** 执行：测速流量要走 iOS 直连，需要临时让指定网段绕过 Surge VIF，其他端不适用。
- 三项同时成立才执行，**缺任何一项就停下报告**，不自行改脚本、模块或网段：脚本 `/var/minis/shared/cfst/cfst-run.sh` 可读可执行；同目录有 `cfst`（arm64）和 `ip.txt`；模块「CFST 测速直连」（同目录 `CFST.sgmodule`）在 `surge-cli module list` 里可见。
- `surge-cli`、`curl` 在 PATH 里，`SURGE_API_KEY` 已注入（缺了脚本直接退出）；凭据只引用变量，不打印、不进命令行、不写文件。
- **每次执行都要另核授权**：测速占用带宽或蜂窝流量，并临时启停 Surge 模块（TUN 重配），可能让 VPN 或隧道重连、短暂断网；模块自述的「测完关闭并重连 VPN」不是自动恢复的保证。按 `luno-core/references/execution.md`〔分支 safety〕〈授权与安全〉当次确认，不把重新测速当作默认的验收手段。
- 调用前核对实际的二进制版本、参数和模块网段覆盖；替换二进制后重核。

## 运行

```sh
/var/minis/shared/cfst/cfst-run.sh              # 输出 result-MMDD-HHMM.csv
/var/minis/shared/cfst/cfst-run.sh my.csv       # 位置参数指定输出文件名
CFST_OUT=my.csv /var/minis/shared/cfst/cfst-run.sh
```

固定参数（用户指定，不要改）：

```sh
./cfst -httping -cfcolo LAX,SJC -url https://dl.yuumi.moe/iso/debian-amd64.iso \
  -n 200 -dn 3 -dt 15 -tl 400 -sl 20 -p 3 -o "$OUT"
```

`-httping` 是 HTTPing 口径，`-tl 400` 是这个口径下的延迟上限：2026-10-30 本机观察到 HTTPing 比 TCPing 高约 100–150 ms，`-tl 300` 会把结果清零（本机经验，不推广）。

## 脚本行为

1. 读取模块原状态（`[x]`/`[ ]`）；读不到或模块不存在就退出，此时还没建临时目录。
2. 原状态关闭才临时启用并等 3 秒；原本开着的全程不动，结束时也不关。
3. **绕过核验**：从 `ip.txt` 每个 IPv4 网段的基址取 +2、+3，分批用 `curl -sk -w '%{time_connect}' https://<ip>/` 测 443 的 TCP 握手时间（不是 TLS 完成时间）。有一个候选 **≥ 20 ms** 就判定已直连；全部 < 20 ms 且成功 **≥ 2** 个，判定仍被 VIF 接管并中止；其余（成功 0 或 1 个且没有高值）判定无结论并中止，提示文字是「候选地址均未建连成功（成功 N 个）」，成功 1 个也走这里。20 ms 是受机房、路由和首包放行影响的固定启发值。
4. 用固定参数运行 cfst，用轮询代替阻塞的 `wait`（ash 会推迟 trap，阻塞时 INT/TERM 无法及时恢复）。
5. `EXIT`/`INT`/`TERM`/`HUP` 都走恢复：终止 cfst（TERM → 5 秒 → KILL），按原状态关闭模块，打印恢复后的状态；`mktemp -d` 建的核验目录在结束时清理。

## 判读与恢复

- 结果默认是脚本同目录的 `result-MMDD-HHMM.csv`，脚本最后打印前 3 行；延迟、丢包和下载速度以 cfst 输出为准，HTTPing 延迟不是 TCP 建连延迟。单次结果只代表当次的网络和出口，不据此下长期结论。
- **被 `SIGKILL` 时 trap 不会执行**，模块可能还开着；原状态读不到时脚本虽在启用前退出，也不能假定没动过。两种情况都人工核对 `surge-cli module list`，按原状态处置（原来关闭就关掉，原状态不明先核实，不猜），不因为「跑完了」就假定已恢复。中断后残留的临时目录按实际路径核查。

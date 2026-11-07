# SSH连接与非交互探测

先加载luno-core与luno-ops；凭据、落点、临时文件及授权规则不由本资源放宽。连接或判断远端命令定位前完整读取。

- SSH/Shell 探测：非交互 SSH 的 `PATH` 常缺 `/usr/local/bin`、mise 路径，`command -v` 未命中不得据此报未安装；用 `bash -lc '…'` 或直读候选路径（如 `/root/.local/share/mise/installs/node/*/bin/lh`），登录 shell 仍未命中时须补核路径。fish 主机的远端命令须显式用 `sh -c`/`bash -lc` 包裹，不在命令位用 `$( )`。
- SSH 调用：同主机、同授权范围的同阶段只读步骤尽量批取，分别捕获各步退出码与 stderr，仅输出必要安全错误，不预执行依赖前结果的步骤；同主机写操作串行，读取并发仍守生产取证限制。非交互显式用 `BatchMode=yes` 与 `StrictHostKeyChecking=yes`；主机密钥未知或变更即停，按可信来源核指纹，不用 `no`/`accept-new` 绕过。自动化连接用 `-F none` 隔离本机 SSH 配置，用前核客户端支持，所需主机和跳板参数须在授权内显式提供，身份显式指定当次获准私钥并设 `IdentitiesOnly=yes`、`IdentityAgent=none`，不回退默认私钥或 agent。`ConnectTimeout` 限建连握手，`ServerAlive*` 不作命令截止；总时限按任务另设并给清理留余量。255 或本地超时不足以判定远端未执行，结合必要安全 stderr 与实际状态判断，重试依总控失败处置。

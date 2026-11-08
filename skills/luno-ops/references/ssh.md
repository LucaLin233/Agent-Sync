# SSH 连接与非交互探测

凭据、落点、临时文件和授权规则不因本资源放宽。

- **命令定位**：非交互 SSH 的 `PATH` 常缺 `/usr/local/bin` 和 mise 路径，所以 `command -v` 没命中不能说明没安装。用 `bash -lc '…'` 或直接读候选路径（如 `/root/.local/share/mise/installs/node/*/bin/lh`）；登录 shell 仍没命中时还要补核路径。fish 主机上的远端命令要显式用 `sh -c` 或 `bash -lc` 包裹，不在命令位置用 `$( )`。
- **批量与串行**：同一主机、同一授权范围、同一阶段的只读步骤尽量合并执行，分别捕获各步的退出码和 stderr，只输出必要的安全错误；依赖前一步结果的步骤不提前执行。同一主机的写操作串行；读取并发仍受生产取证限制。
- **连接参数**：非交互连接显式设置 `BatchMode=yes` 和 `StrictHostKeyChecking=yes`；主机密钥未知或变更就停下，按可信来源核对指纹，不用 `no` 或 `accept-new` 绕过。自动化连接用 `-F none` 隔离本机的 SSH 配置（用前确认客户端支持），所需的主机和跳板参数在授权内显式给出；身份显式指定本次获准的私钥，并设 `IdentitiesOnly=yes`、`IdentityAgent=none`，不回退到默认私钥或 agent。
- **超时与结果**：`ConnectTimeout` 只限制建连握手，`ServerAlive*` 不能当命令截止时间；总时限按任务另设，并给清理留余量。退出码 255 或本地超时不足以判定远端没执行，要结合必要的安全 stderr 和实际状态判断；重试按总控的失败处置。

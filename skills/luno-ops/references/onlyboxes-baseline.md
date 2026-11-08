## OnlyBoxes 版本能力与成本观测

先取得本包入口必需规则。

**定位**：本资源集中记录 OnlyBoxes 的来源、版本、镜像能力、成本与宿主风险证据，不授予沙箱资格；选址按 `references/execution-environment.md`，调用规则由同技能的 OnlyBoxes 落地资源承接。每个数字和能力都带证据日期、版本与证据层；平台或镜像变化须整体重核，有限测量不得外推。

## 官方来源与快照

- **仅文档（访问日期 2026-11-05；UTC 2026-11-04）**：OnlyBoxes 官方 [MCP Tools Reference](https://onlybox.es/en/docs/mcp-tools/) 说明 MCP Streamable HTTP、`tools/list`／`tools/call`、`echo`、`pythonExec`、`terminalExec`、`computerUse`、`readImage` 与 `exportFile` 的公开参数和返回形态；本轮 GET HTML 快照 SHA-256 为 `e1d091aaa8787d55286903995fbb0111dc37e7b810ddbce7ff1ec27082e6a9ee`。页面文档不证明当前实例版本、账号能力或工具实际可调用。
- **仅文档（访问日期 2026-11-05；UTC 2026-11-04）**：OnlyBoxes 官方 [Console API Reference](https://onlybox.es/en/docs/console-api/) 说明 `/api/v1`、执行令牌、`/api/v1/tasks*` 与统一错误形态；本轮 GET HTML 快照 SHA-256 为 `ad150f54131bca88cbec0713be01163bc295d0973cc5fca4c250abcd9677a984`。2026-11-01 旧登记的该页快照为 `6c0ec431b49ffd7998196bd766923d9e489b7dbf8d3e23d8f5c07a2d9d96da2b`，只作历史快照，不替代本轮页面。
- **未验证**：本轮未取得官方仓库提交、实例运行时版本、worker 配置、账户级能力或完整 REST/MCP 兼容性；页面文档、工具列表和服务器 note 均不构成访问控制结论。

## 2026-11-05 Minis 按需 MCP 有限实测

- **2026-11-05 Minis 实测（合成样本）**（Minis 1.16 (21)；LUNO 记录，其后未重测）：已配置的 OnlyBoxes MCP（`/mcp` 端点） 使用 `ONLYBOXES_API_KEY` 引用认证，ping 成功；工具定义共 5 个，合计 8,977 B：`terminalExec` 2,664 B、`pythonExec` 2,152 B、`computerUse` 1,931 B、`readImage` 1,138 B、`echo` 1,092 B。
- **2026-11-05 Minis 实测（合成样本）**（同上证据层）：`terminalExec` 的 exit 0 与 exit 3 样本均返回正确 `exit_code`，并带 `stderr`、`stdout_truncated` 与 `stderr_truncated`；执行环境报告为 x86_64。非零退出码是工具结果，不能只看协议层成功。
- **2026-11-05 Minis 实测（合成样本）**（同上证据层）：同一 `session_id` 下文件与 cwd 跨调用保留，`export` 不保留；该样本不外推到新会话、其他实例、租约、超时、截断或并发。
- **2026-11-05 Minis 实测（合成样本）**（同上证据层）：`pythonExec` 抛异常时返回 `exit_code=1` 与 `output`，`stderr` 含 traceback；MCP Python 结果没有 REST Task `status`。
- **2026-11-05 Minis 实测（合成样本）**（同上证据层）：`readImage` 返回 `content type=image/png` 的 base64；解码后 75 B，SHA-256 前缀 `57cda64cead0869c` 与沙箱端一致，本机视觉读取通过；仅拿到元数据不算读图成功。
- **未验证**：系统提示只列服务器名和 note，工具定义按需取得；新会话未复核。截断阈值、超时、lease 到期、`computerUse`／`CU:<worker_id>`、并发和本日 REST Task 均未测。

## 能力与成本重新取证

不保留旧镜像包清单、安装耗时、速度倍率、输出上限样本与历史制稿成品哈希。它们不证明当前能力或资源上界；需要时在当次已授权环境核版本、依赖、vCPU/内存/pids/磁盘/输出上限及目标完整回传。未取得当前上界不得准入，不以试跑整个任务替代成本判断。下列未解除的宿主风险仍保留，删除历史性能缓存不代表风险解除。

## 历史宿主风险与未决选择

- **历史记录（2026-10-18；来源为退役前 MCP 登记及对应取证）**：以下不是本轮现场结论；MCP 登记退役不等于宿主风险解除，当前实例版本、权限与网络仍未整体复验。
- **历史结论（2026-10-18，未整体解除）**：在无 worker-sys 的前提下，原 `computerUse` 裸宿主执行路径当前不可达；历史登记描述的风险路径是 worker 属 `executor_kind=sys` 时在宿主以 `/bin/sh -lc` 直接执行、无容器隔离，等同宿主 root shell。该前提只说明本账号当前没有可用 worker-sys，不证明服务端能力不存在。一旦新增 worker-sys 或执行路由改变，该路径即可恢复可达，工具仍可能列在工具表中。
- **历史风险（2026-09-17／2026-10-18）**：worker 仍持有 `/var/run/docker.sock`（派生沙箱容器所必需）；该 socket 的权限上限等同完整 Docker API，存在通过 `docker run -v /:/host` 等方式到达宿主 root 的逃逸链。非 root 运行只降低部分直接操作权限；2026-09-17 曾实测不能写自身二进制、不能 `chown root`，但未降低 Docker API 可达的权限上限。worker 的 `network_mode: host` 是与 socket 独立的另一暴露面，可直连宿主 `127.0.0.1` 的服务；两项均未按加固方案实施，用户于 2026-09-17 决定另行研判。
- **历史隔离取证（2026-09-17；镜像 `onlyboxes-sandbox:0.11.0`）**：宿主侧曾见 `NetworkMode=bridge`、`HostConfig.Binds` 为空、`CapAdd=[]`、`Privileged=false`、`CapEff=00000000a80425fb`（Docker 默认能力集、无 `CAP_SYS_ADMIN`）；在已测试地址和端口中仅见宿主 bridge 网关的 nginx:80 与 webhook:9000 可达，不能据此断言其他地址可达；loopback 绑定的 console 8089、gRPC 50051、lobe-postgres 3211 曾不可达。
- **历史隔离取证（2026-10-18；console／worker／镜像均标为 0.14.1）**：容器内曾见 UID 0、Docker 默认 capability 集、Seccomp 模式 2、无 `/var/run/docker.sock`、无宿主挂载、PID1 无 init、pids 128、**1 vCPU／2 GiB**；磁盘无配额，写满宿主根分区；容器内仍是 root + 默认能力集，**不是安全隔离区**。这些只描述该版本容器内的可达面，不能外推当前实例。
- **历史实施与取证（2026-09-17）**：worker 曾配置 `user: "65534:65534"`、`group_add: ["990"]`、`HOME=/tmp`；回读为非 root，主进程 groups 为 990、65534，echo、pythonExec、terminalExec、readImage 与派生沙箱样本通过。该取证依赖宿主 docker 组 gid 990、socket 路径和权限、daemon 授权、版本 0.14.1、无 worker-sys 以及 `HOME=/tmp` 等前提，任一变化即须重核；本次 UID 与能力集不是长期保证。
- **仅文档／历史建议（日期未单独核现值）**：若加固，应使用会校验请求体的 Docker 代理；只按方法和路径做 ACL 不能阻挡 `POST /containers/create` 请求体中的逃逸参数，放行 create 等于放行该逃逸面。

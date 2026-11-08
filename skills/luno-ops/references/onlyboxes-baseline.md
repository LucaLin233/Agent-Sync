# OnlyBoxes 版本能力与宿主风险

本资源记录选址时需要的 OnlyBoxes 结论，不授予沙箱资格；选址按 `references/execution-environment.md`，调用按同技能的 `references/onlyboxes.md`。每条结论都带证据日期、版本和证据层；平台或镜像变化后整体重核，有限的测量不外推。原始取证记录（文档页快照哈希、工具定义字节数、容器能力集等）见规则仓库中本文件的 git 历史，不随技能分发。

## 官方文档

官方 [MCP Tools Reference](https://onlybox.es/en/docs/mcp-tools/) 说明 MCP Streamable HTTP、`tools/list`/`tools/call` 和 `echo`、`pythonExec`、`terminalExec`、`computerUse`、`readImage`、`exportFile` 的公开参数与返回形态；[Console API Reference](https://onlybox.es/en/docs/console-api/) 说明 `/api/v1`、执行令牌、`/api/v1/tasks*` 和统一的错误形态（均为 2026-11-05 访问）。文档不证明当前实例版本、账号能力或工具实际可调用；官方仓库提交、实例运行时版本、worker 配置和完整的 REST/MCP 兼容性都没有取得。

## 有限实测（2026-11-05，Minis 1.16 (21)，合成样本）

- 已配置的 OnlyBoxes MCP（`/mcp` 端点）用 `ONLYBOXES_API_KEY` 引用认证，ping 成功，共 5 个工具；执行环境报告为 x86_64。
- `terminalExec` 对 exit 0 和 exit 3 都返回正确的 `exit_code`，并带 `stderr`、`stdout_truncated`、`stderr_truncated`：非零退出码是工具结果，不能只看协议层成功。同一 `session_id` 下文件和 cwd 跨调用保留，`export` 不保留。
- `pythonExec` 抛异常时返回 `exit_code=1` 和 `output`，`stderr` 带 traceback；MCP 的 Python 结果没有 REST Task 的 `status`。
- `readImage` 返回 `image/png` 的 base64，解码后与沙箱端哈希一致，本机视觉读取通过；只拿到元数据不算读图成功。
- 未验证：新会话、截断阈值、超时、lease 到期、`computerUse`/`CU:<worker_id>`、并发和 REST Task。

## 能力与成本重新取证

不保留旧的镜像包清单、安装耗时、速度倍率、输出上限样本：它们不能证明当前的能力或资源上界。需要时，在当次已授权的环境里核对版本、依赖、vCPU、内存、pids、磁盘、输出上限和目标的完整回传。没取得当前上界就不准入，也不用试跑整个任务来代替成本判断。删除历史性能数据不代表下面的宿主风险已经解除。

## 宿主风险（未解除）

以下是历史结论，不是本轮的现场结论，当前实例的版本、权限和网络都没有整体复验；MCP 登记退役也不等于风险解除。

- **沙箱不是隔离边界**（2026-10-18，console/worker/镜像标为 0.14.1）：容器内是 UID 0 加 Docker 默认能力集，pids 128、1 vCPU/2 GiB，磁盘没有配额（可以写满宿主根分区）。
- **worker 持有 `/var/run/docker.sock`**（2026-09-17 与 2026-10-18）：派生沙箱容器需要它，但它的权限上限等同完整的 Docker API，存在通过 `docker run -v /:/host` 之类到达宿主 root 的逃逸链；worker 以非 root 运行只降低部分直接操作的权限，不降低 Docker API 的上限。worker 的 `network_mode: host` 是另一个独立的暴露面，可以直连宿主 `127.0.0.1` 上的服务。这两项都没按加固方案实施，用户 2026-09-17 决定另行研判。
- **worker-sys 路径等于宿主 root shell**（2026-10-18）：worker 属 `executor_kind=sys` 时在宿主上以 `/bin/sh -lc` 直接执行、没有容器隔离。本账号当前没有 worker-sys，所以 `computerUse` 的这条路径暂时不可达，但这不证明服务端没有这个能力；一旦新增 worker-sys 或执行路由改变，这条路径就会恢复可达，而工具仍可能列在工具表里。
- **加固建议**（仅文档）：若要加固，应该用会校验请求体的 Docker 代理；只按方法和路径做 ACL 挡不住 `POST /containers/create` 请求体里的逃逸参数，放行 create 就等于放行这个逃逸面。

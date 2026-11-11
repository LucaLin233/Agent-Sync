# 共读资源（按原分支合并）

指针中的“分支”以 branch 锚点及 BEGIN/END 注释定界。沿用各分支原有触发和共同前置：完整读取命中的分支；原规则指定分节时，读取指定完整分节及共同前置，不加载未命中分支。同一文件的命中并集优先一次取齐，返回受限时分块补齐，不以截断内容作已加载。

分支内的“本文件”“本文”“本资源”均只指该分支，不把其他分支的接口事实、版本、能力或权限并入；“本技能”仍指原技能。主体、条件、例外、停止、恢复和许可边界保持原文，不因合并授予额外权限。跨技能先读目标技能入口及产品/业务入口；候选不改变现役规则。

分支：execution-environment、onlyboxes、onlyboxes-baseline。

<a id="branch-execution-environment"></a>
<!-- BEGIN execution-environment -->
# 执行环境分流（Minis 端）

本端有两个 Linux 执行面：本机 **iSH**（Alpine/aarch64，与 `/var/minis/*`、`apple-*`、`minis-*` 在同一侧）和远端的 **OnlyBoxes 沙箱**（远程调用）。下面是**选址判据**，按顺序过滤，前一步不过就停；它只提供选址依据，不授予任何端使用沙箱的权限。

引用 OnlyBoxes 的版本、镜像能力或测量成本做选址建议或结论之前，先读 `references/execution-environment.md`〔分支 onlyboxes-baseline〕。资源拿不到、版本未核或证据只有历史样本时，暂停依赖这些证据的判断，不把历史能力、限额或成本当作现值；有限的测量不外推。

1. **准入与禁止（硬约束）**：沙箱只承接**准入通过**的任务：来源和版本可追溯，入口和依赖的执行行为已核对，没有未经审查的动态下载和执行；**助手或模型生成的代码同样要核对，核不了就不准入**。沙箱不是安全隔离区，不承接不可信代码和来源不明的脚本或二进制。不承载秘密、生产凭据和生产数据；**默认不访问宿主和私网服务**，公网只限任务必需的目标，禁止扫描、洪泛和代理转发。本机侧的评估只限只读静态检查，运行不可信代码要先有独立的隔离环境。
2. **环境资格与默认归属**：区分执行时必须直接访问的本机能力和最终交付的位置。下面「默认沙箱」类的任务，通过第 1、3、4 步就派沙箱，不因为本机也能做或更熟悉而改判；结果最终存本机，不排除在授权内先在沙箱计算再回传。硬约束淘汰的是候选环境，不是任务本身。
   - **默认沙箱**：纯计算，统计和数据处理，媒体转码，文档转换，x86_64 wheel 和需要 glibc 行为的任务，gcc/g++/make 编译和小型构建，批量文本、正则、日志解析，JSON/CSV/SQLite/zip 转换。具体镜像能力按基线的当前证据核对。
   - **混合（本机取数、编排、落盘 + 远端计算）**：本机源文件的批处理，可以断点续跑的长任务（分段派发、逐段回传），公共 HTTP 抓取和解析。
   - **保持本机（不得默认外派）**：需要读写 `/var/minis/*` 或需要 `apple-*`、`minis-*`、记忆、已有浏览器会话的子任务；规则仓库的测试（不把 `TMPDIR` 指向 Minis 共享目录）；秘密、生产凭据或生产数据；不可信代码；宿主和私网探测；目标服务器的真实状态和服务操作（走既有的 SSH 授权通道）。
   - **不迁移**：毫秒级的小操作；超过已核上界或资源上界不明的任务；无法完整校验回传的大产物；要求 Alpine/musl、aarch64 或与生产目标完全同构的验收。

   `computerUse` 和 `CU:<worker_id>` 路径一律按禁用处理；工具列出来不等于可以调用，也不能据此断言服务端不可用。
3. **资源资格**：任务要能给出运行时长，以及磁盘、日志、解压、缓存和并发的上界，并且逐项不超过派发前在当次已授权环境核实、适用于当前版本和镜像的 vCPU、内存、pids、磁盘和回传界限（`references/execution-environment.md`〔分支 onlyboxes-baseline〕 不保存现值，取证方式见其〈能力与成本重新取证〉）。给不出上界、没取得当次界限，或会并发压满宿主的，不派沙箱。版本或镜像变化后，资源上界整体重核；不通过压测或试跑整个任务取得准入。
4. **交付完整性**：结果必须完整回传，并通过目标校验（按工具使用长度、序号、总长、哈希、解码或其他适用的校验）；截断、缺块、目标不完整或校验失败都不算交付。工具或协议报错、执行状态不明、lease 到期，都按结果未知处理：不盲目重试，不跨协议重跑。
5. **成本择优**：前四步都通过后才比较成本。基线里的耗时、固定开销和能力数字都要按日期和版本解读，历史样本不能外推成跨时段的常量。耗时未知就标未知，不为了定路由先跑一遍完整任务；只有批量化这类有依据的复用才计入比较。
6. **未知或失败**：不擅自换环境。OnlyBoxes 不可用、工具能力未核或结果未知时，报告证据，停止依赖这个结果，并按能力降级或暂停；**不静默改由 iSH 承接重计算。**
<!-- END execution-environment -->

<a id="branch-onlyboxes"></a>
<!-- BEGIN onlyboxes -->
# OnlyBoxes 沙箱调用（Minis 端）

本资源讲已经选定沙箱之后的 MCP 调用、会话、依赖和回传；选址和资源上界按 `references/execution-environment.md`〔分支 execution-environment〕，版本、实测和宿主风险按 `references/execution-environment.md`〔分支 onlyboxes-baseline〕。短任务用当前已配置的 OnlyBoxes MCP；REST Task 只用于长任务的追踪和恢复。

## 工具发现与成功判据

- **先发现再调用**：通过宿主提供的工具发现入口（通常是 MCP `tools/list` 或等价的按需发现）取得实际的工具定义，按返回的工具名、参数和约束调用；不猜工具名、参数、认证或未列出的端点。服务器名、note 或工具被隐藏只是发现结果，不是访问控制；`?tools=` 过滤是否受支持尚未核实，不能据此收窄权限或绕过准入。
- **成功判据**：MCP 协议错误、工具结果的 `isError: true` 和正常输出分开记录；出现前两者时，不能把其他字段当成功。执行类工具还要核对定义里的 `exit_code`、`stderr` 和 stdout/stderr 截断标志（如果返回），并核对目标的完整性。只有 `exit_code=0`、协议和工具结果都没有错误、目标通过完整性校验，才算执行成功；非零 `exit_code` 是执行失败的结果，仍要保留并回传 `stderr`。
- **认证**只用已配置连接承接的授权变量引用（如 `ONLYBOXES_API_KEY`），不回显、不转存，也不把秘密传给代码、测试或生产数据路径。准入、宿主和私网、资源和停止规则按执行环境资源。

## 会话、Python 和读图

- `terminalExec` 按实际工具定义建立或复用 `session_id`；命令用绝对路径，不把跨调用的 `cd`、`export` 或别名当作已保存的状态（实测 `export` 不跨调用保留，见基线）。
- `pythonExec` 读取工具返回的 `output`、`stderr` 和 `exit_code`。MCP 的 Python 结果没有 REST Task 的 `status`，不能伪造状态，也不能改用 Task 轮询来判定 MCP 调用。官方文档说它支持用 PEP 723 脚本元数据声明第三方依赖，本资源未提供依赖安装、缓存、版本或执行效果的验证证据，不能据此把 PEP 723 当作已承诺的能力。
- `readImage` 只有取得完整的 image 内容才算读图成功：先解码 base64，核对 MIME、字节长度或哈希、图像能解码和目标完整，再做本机的视觉读取；只拿到 `file_path`、`mime_type`、`size_bytes` 等元数据不算成功。
- `computerUse` 和 `CU:<worker_id>` 路径按禁用处理；这表示不依赖它，不表示服务端不可用。工具列表里有没有它，都不构成访问控制结论。

## REST Task（长任务）

- 只有需要长任务追踪或恢复、并且本次授权明确允许 REST 时才用；短调用不因为 MCP 结果不方便就跨协议重跑。官方文档给出 `/api/v1/tasks` 和执行令牌认证，实例版本和当前行为仍按当次证据核对。
- 提交形状按实际文档和工具定义核准，例如：

  ```json
  {"capability":"pythonExec","input":{"code":"print(6 * 7)"},"mode":"async","timeout_ms":60000,"request_id":"task-python-unique-id"}
  ```

- 历史实测（2026-11-01，实例版本未知）：`mode=async` 返回 `task_id` 和同源的 `status_url`，用相同认证在同一来源查询；要设置客户端超时和总轮询预算，有限次取得终态。提交时遇到 HTTP 502/504 或状态查询失败，有 ID 就先在预算内查询；没有 ID、查不到终态或状态不明，都按结果未知处理，不盲目重试。
- 成功要同时满足 `status=succeeded` 和 `exit_code=0`，并核对 `result.output`、`result.stderr` 和目标完整性。本资源未定义取消流程；关闭或 404 不能证明容器已删除或回收。每个新 Task 用唯一的 `request_id`；文档里的幂等不作为重试的保证。

## 依赖与产物回传

- 准备依赖前，核对来源、版本、行为和安装边界；未经审查的动态下载、来源不明的代码、秘密和生产数据不准入。工具定义或实例没有验证过依赖安装的，停止依赖这项能力；不凭耗时或安装器输出推定成功，要保留 `exit_code` 和 `stderr`，并用同一个解释器核对导入结果。
- 文本和二进制按实际的 MCP 或 REST 契约回传；需要分块时，记录序号、总长和整件 SHA-256，逐块和整件都校验后再落盘。拿不到可验证的完整目标就不交付；截断、协议错误、`isError`、非零退出码或状态未知都按失败或未知报告，并停止依赖。
<!-- END onlyboxes -->

<a id="branch-onlyboxes-baseline"></a>
<!-- BEGIN onlyboxes-baseline -->
# OnlyBoxes 版本能力与宿主风险

本资源记录选址时需要的 OnlyBoxes 结论，不授予沙箱资格；选址按 `references/execution-environment.md`〔分支 execution-environment〕，调用按同技能的 `references/execution-environment.md`〔分支 onlyboxes〕。每条结论都带证据日期、版本和证据层；平台或镜像变化后整体重核，有限的测量不外推。原始取证记录（文档页快照哈希、工具定义字节数、容器能力集等）见规则仓库中本文件的 git 历史，不随技能分发。

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
<!-- END onlyboxes-baseline -->


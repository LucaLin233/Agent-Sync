## OnlyBoxes 沙箱落地操作（Minis 端）

先取得本包入口必需规则。

本资源讲已选定沙箱后的按需 MCP 调用、会话、依赖与回传；选址与资源上界按 `references/execution-environment.md`，版本、镜像能力、历史成本与宿主风险按 `references/onlyboxes-baseline.md`。短任务以当前已配置的 OnlyBoxes MCP 为主；REST Task 只保留长任务追踪与恢复的短契约。

### MCP 调用面与工具发现

1. 先通过当前宿主提供的 OnlyBoxes MCP 工具发现入口取得实际工具定义（通常是 MCP `tools/list` 或其等价按需发现），再按返回的工具名、参数和约束调用；不猜工具名、参数、认证或未列出的端点。服务器名、note 或工具隐藏只说明发现结果，不是访问控制；`?tools=` 过滤是否支持本轮未核，不能据此收窄权限或绕过准入。
2. MCP 协议错误、工具结果的 `isError: true` 与正常工具输出分开记录。出现协议错误或 `isError: true` 时不得把其他字段当成功；执行类工具仍须核其定义中的 `exit_code`、`stderr` 以及 stdout／stderr 截断标志（若返回），并核目标完整性。只有 `exit_code=0`、协议与工具结果无错误且目标通过完整性校验，才算执行成功；非零 `exit_code` 是执行失败结果，仍须保留并回传 `stderr`。
3. 认证只使用已配置连接承接的授权变量引用（如 `ONLYBOXES_API_KEY`），不回显、转存或把秘密传给代码、测试或生产数据路径。准入、宿主／私网、资源和停止规则沿用执行环境资源。

### MCP 工具、会话与读图

- `terminalExec` 的调用按实际工具定义建立或复用 `session_id`；命令使用绝对路径，不把跨调用的 `cd`、`export` 或别名当作已保存状态。**2026-11-05 Minis 实测（合成样本）**（Minis 1.16 (21)）同一 `session_id` 下文件与 cwd 跨调用保留，`export` 不保留；该样本不外推到新会话、其他实例或未测的租约、超时、并发和截断边界。
- `pythonExec` 的结果读取工具返回的 `output`、`stderr` 与 `exit_code`；**2026-11-05 Minis 实测（合成样本）**（Minis 1.16 (21)）异常样本返回 `exit_code=1`、`output`，并在 `stderr` 带 traceback。MCP 的 Python 结果没有 REST Task 的 `status`，不得伪造状态或改用 Task 轮询判定 MCP 调用。
- **仅文档（官方 MCP 文档，访问日期 2026-11-05；UTC 2026-11-04）**描述 `pythonExec` 支持以 PEP 723 脚本元数据声明第三方依赖；本轮只取得定义，未验证依赖安装、缓存、版本或执行效果，不能把 PEP 723 当作已承诺能力。
- `readImage` 只有在取得完整 image 内容后才算读图成功：先解码 base64，核 MIME、字节长度／哈希、图像解码和目标完整性，再进行本机视觉读取；仅拿到 `file_path`、`mime_type`、`size_bytes` 等元数据不算成功。**2026-11-05 Minis 实测（合成样本）**（Minis 1.16 (21)）收到 `image/png` base64，解码 75 B，SHA-256 前缀与沙箱端一致，本机视觉读取通过；该样本不外推图片大小上限或其他入口。
- `computerUse` 与 `CU:<worker_id>` 路径按禁用处理；这表示本单不依赖该路径，不等于服务端不可用。工具列表中的存在或缺失均不构成访问控制结论。

### REST Task 长任务契约

- 只有需要长任务追踪或恢复，且本次授权明确允许 REST 时才使用 REST Task；短调用不因 MCP 结果不便而跨协议重跑。**仅文档（官方 REST 文档，访问日期 2026-11-05；UTC 2026-11-04）**给出 `/api/v1/tasks` 及执行令牌认证；实例版本和当前 REST 行为仍按本轮证据核对。
- 提交 Python Task 可采用按实际文档与工具定义核准的形状，例如：
```json
{"capability":"pythonExec","input":{"code":"print(6 * 7)"},"mode":"async","timeout_ms":60000,"request_id":"task-python-unique-id"}
```
  **历史实测（2026-11-01；实例版本未知，本单仅交短契约）**：`mode=async` 取得 `task_id` 与同源 `status_url` 后，使用相同认证在同一源查询；设置客户端超时和总轮询预算，有界取得终态。**历史实测（同上证据层）**提交 HTTP 502／504 或状态查询失败时，有 ID 先在预算内查询；无 ID、查不到终态或任务状态不明均按结果未知处理，不盲重试。
- **历史实测（2026-11-01；实例版本未知）**：REST 结果须同时核任务 `status`、`result.output`、`result.stderr`、`result.exit_code` 与目标完整性；只有 `status=succeeded` 且 `exit_code=0` 才算成功。**2026-11-05 Minis 实测（合成样本）**（Minis 1.16 (21)）MCP `pythonExec` 没有 Task `status`，不得套用这一字段。**本单方案**当前未新增取消流程。关闭/404不证明容器删除或回收；每个新Task取唯一`request_id`，文档幂等不作重试保证。

### 依赖与产物回传

依赖准备前核来源、版本、行为和安装边界；未审动态下载、来源不明代码、秘密与生产数据不准入。若 MCP 工具定义或实例未验证依赖安装，停止依赖该能力；不得用耗时或安装器输出推定成功，须保留 `exit_code`／`stderr` 并用同一解释器核导入结果。

文本和二进制按实际 MCP／REST 契约回传；需要分块时记录序号、总长与整件 SHA-256，逐块和整件校验后再落盘。未取得可验证的完整目标不得交付；截断、协议错误、`isError`、非零退出码或状态未知均按失败／未知报告，并停止依赖。

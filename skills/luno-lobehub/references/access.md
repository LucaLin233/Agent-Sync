# CLI/HTTP 调用与设备端凭据

先取得本包入口必需规则。

- **版本证据**：npm `latest` 不等于已装版本；观测版本不等于最低支持版本，单版本端到端验证不能确定最低支持边界。

- **跨会话与跟随**：`topic send`／`message reply` 会唤醒目标会话并触发运行（仅文档，未实测），调用前核目标与运行授权；`workspace member update` 按权限变更处理。多路复用跟随不能直接外推 CE 链路，须核服务端协议与网关能力。

- 官方 CLI `@lobehub/cli`（`lh`）可用 `LOBEHUB_SERVER` 或 `lh login --server` 指向自建实例。仓库 `.agents/skills/cli/` 是开发指南且命令表不全；命令与参数以本机 `--help`／`lh man <cmd>` 和版本为准，命令存在不代表服务端支持；调用前解析真实路径。变量未设置或为空时按 `luno-lobehub/SKILL.md`〈平台层〉停依赖，不自动登录、复用登录态或换实例。
- **诊断边界**：分层与 `--offline`／`--deep`／`--fix` 见 `lh doctor --help`（后两者须授权）；`core`／`connect` 实测输出 ok/warnings/failing 计数，`--deep`／`--fix` 未验证；offline 不等于无写入或无敏感输出。
- `lh agent run` 的 WebSocket 与事件日志续接（含 `--json`）、不可用时降级 `lh agent status`（0.0.72 记录，未在现版核实），不能以状态成功冒充完整取回。退出码、`--timeout`（只停等待、服务端继续）、`--no-headless`（需审批的调用挂起等人，CLI 以退出码 2 返回）见 `lh agent run --help`；脚本按退出码分支并保留外层 `timeout`。（实测：本机 `agent run --help`，仅帮助；传输、降级与退出路径未行为实测。）
- **定位与检索**：JSON 里的 `url`／已存地址对象的 `appUrl` 仍按字段白名单取。`lh read <url>` 只解析 LobeHub 分享链接、非通用网页抓取（见 `lh read --help`）。检索用 `lh recall`／`lh message search` 的 `--since`／`--until` 窗口（见各自 `--help`），不扩大授权；旧实例缺过滤接口也不放宽。`lh message search --json` 的截断警告在 stderr，JSON 成功不代表完整，截断时在授权范围内收窄复查。通知不到达可按授权只读查 `lh notification settings`；`enable`／`disable`／`update` 属写操作，区别于 `lh notify`，语义见各自 `--help`。
- `lh` 两条认证通道不可互换：`~/.lobehub/` 存 `lh login` 设备码登录态与运行状态；API key 只认 `LOBEHUB_CLI_API_KEY`，不读配置文件，有 key 时优先于 OIDC token（目录存在≠key 可用）。设备端 `/root/.zshenv`（所有 shell）与 `/root/connect-device.sh`（`lobehub-connect` 启动脚本）同源加载 `/root/env/*.env`（默认单文件 `secrets.env`，按主题注释）；新会话生效，轮换只改该文件后 `systemctl restart lobehub-connect`。缺 key 只核指定变量是否注入，缺失交回维护，不读文件、不交互绕过。实例 `/root/lobehub/.env` 供 Compose 解析，是另一套，不混放。

- **批量与自动化在存在等价已验证接口时走 HTTP，不走 CLI 循环**：无等价接口的自动化仍按官方支持的 CLI 用法，先查原文再试错。既有样本中 CLI 串行调用开销较大，批量优先已验证的 HTTP 接口；性能须按当前版本与链路核对，不把历史耗时当常量。写法：`POST https://<实例>/trpc/lambda/<router>.<procedure>`，头 `X-API-Key: $LOBEHUB_CLI_API_KEY`、`Content-Type: application/json` 与 **`User-Agent: curl/8.7.1`**（历史观测：缺 UA 会被 Cloudflare 拦，body 仅回 `error code: 1010`；UA 是可随链路调整的请求参数，被拦时按当时链路改用其他可识别 UA），体 `{"json":{…}}`，响应 `{"result":{"data":{"json":…}}}`。

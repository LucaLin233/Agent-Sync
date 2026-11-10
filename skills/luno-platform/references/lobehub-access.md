# CLI/HTTP 调用与设备端凭据

## CLI

- 官方 CLI `@lobehub/cli`（`lh`）可以用 `LOBEHUB_SERVER` 或 `lh login --server` 指向自建实例。上游仓库的 `.agents/skills/cli/` 是开发指南，命令表不全；命令和参数以本机的 `--help`、`lh man <cmd>` 和版本为准，命令存在不代表服务端支持，调用前先解析真实路径。变量未设置或为空时按 `luno-platform/references/lobehub.md`〈平台层〉停止依赖它的部分，不自动登录、不复用登录态、不换实例。
- **版本证据**：npm 的 `latest` 不等于已装的版本；观测到的版本不等于最低支持版本，单个版本的端到端验证不能确定最低支持边界。
- **诊断**：分层和 `--offline`/`--deep`/`--fix` 见 `lh doctor --help`（后两个须授权）。`core`/`connect` 实测输出 ok/warnings/failing 计数，`--deep`/`--fix` 未验证；offline 不等于没有写入或敏感输出。
- **`lh agent run`**：WebSocket 和事件日志的续接（含 `--json`），不可用时降级为 `lh agent status`（CLI 0.0.72 记录，现版本未核）；不能用状态成功冒充完整取回结果。退出码、`--timeout`（只停止等待，服务端继续运行）、`--no-headless`（需要审批的调用会挂起等人，CLI 以退出码 2 返回）见 `lh agent run --help`；脚本按退出码分支，并保留外层的 `timeout`。（只核过本机 `--help`，传输、降级和退出路径未行为实测。）
- **会唤醒会话的命令**：`topic send`、`message reply` 会唤醒目标会话并触发运行（仅文档，未实测），调用前核对目标和运行授权；`workspace member update` 按权限变更处理。多路复用的跟随不能直接外推到 CE 链路，要核对服务端协议和网关能力。
- **定位与检索**：JSON 里的 `url` 和已存地址对象的 `appUrl` 仍按字段白名单取。`lh read <url>` 只解析 LobeHub 分享链接，不是通用的网页抓取。检索用 `lh recall`、`lh message search` 的 `--since`/`--until` 窗口，不扩大授权；旧实例缺过滤接口也不放宽。`lh message search --json` 的截断警告在 stderr 里，JSON 成功不代表结果完整，截断时在授权内收窄范围复查。通知收不到时，可以按授权只读查看 `lh notification settings`；`enable`/`disable`/`update` 是写操作，和 `lh notify` 不同。

## 认证与设备端凭据

- `lh` 有两条认证通道，不能互换：`~/.lobehub/` 存 `lh login` 的设备码登录态和运行状态；API key 只认环境变量 `LOBEHUB_CLI_API_KEY`，不读配置文件，有 key 时优先于 OIDC token（目录存在不代表 key 可用）。
- 设备端的 `/root/.zshenv`（所有 shell）和 `/root/connect-device.sh`（`lobehub-connect` 的启动脚本）都从 `/root/env/*.env` 加载变量（默认单个文件 `secrets.env`，按主题注释）；新会话才生效，轮换时只改这个文件，然后 `systemctl restart lobehub-connect`。缺 key 时只核对指定变量是否已注入，缺失就交回维护者，不读文件，不通过交互绕过。实例的 `/root/lobehub/.env` 供 Compose 解析，是另一套，不要混放。

## 批量与自动化走 HTTP

有等价的已验证接口时，批量和自动化走 HTTP，不用 CLI 循环（既有样本里 CLI 串行调用开销大；性能按当前版本和链路核对，不把历史耗时当常量）。没有等价接口的，仍按官方支持的 CLI 用法，先查原文再试。写法：

- `POST https://<实例>/trpc/lambda/<router>.<procedure>`
- 请求头：`X-API-Key: $LOBEHUB_CLI_API_KEY`、`Content-Type: application/json`，以及 **`User-Agent: curl/8.7.1`**（历史观测：缺 UA 会被 Cloudflare 拦截，响应体只有 `error code: 1010`；UA 是可以随链路调整的请求参数，被拦时换用其他可识别的 UA）
- 请求体 `{"json":{…}}`，响应 `{"result":{"data":{"json":…}}}`

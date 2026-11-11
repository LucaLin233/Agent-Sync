# Surge iOS HTTP API

官方手册：<https://manual.nssurge.com/tools/http-api.html>。需要 Surge iOS 4.4.0+；每个请求带 `X-Key`；GET 用查询参数，POST 用 JSON 体；除注明外响应是 JSON。

## 引擎状态预检

依赖 Surge 联网的任务（包括这条回退路径）先按入口 §2 预检。HTTP 特有的判读：API 能响应，不等于引擎在正常处理流量；Suspend 时内层 `$httpClient` 探针可能返回 EOF 或超时，遇到意外的 EOF 或超时要重新预检，不沿用之前的状态。

## 端点发现

普通的 Features、Outbound/策略、请求、Profile/DNS/模块、脚本和事件端点，本包不复制目录表。实际调用前按当前平台和版本的官方手册取得 method、完整 path、输入和结果契约，并确认脚本支持这个形态；未知就停，不猜路由。不把 macOS 专属端点套到 iOS 上。

## 连接与授权共同前置

HTTP API 仍须先满足入口的实例、认证、平台与版本门槛；默认同机，活动实例或其他目标须由用户指定且已授权。远程明文 HTTP 会暴露 API key；描述符探测还会暴露节点密码或 PSK，只能在获准的可信局域网使用，其他情况用 HTTPS。分节写入更严格：除精确 loopback IP 外必须是已获授权的可信 HTTPS，不能因这里的普通回退条件而放宽。危险操作仍按入口再次单独确认，不自动启用监听、MCP、MITM 或关闭校验。

## 安全分节写入

分节读取、编辑、恢复或相关方案与判断前，完整读 `references/http-sections.md`，并按其中要求读 `references/platform-compatibility.md`；缺失就停止依赖部分。

## 用 `policy-descriptor` 测未配置的节点

`POST /v1/policies/test` 只接受已配置的策略名。想不动 Profile 测新节点，可以执行一个 cron 脚本，让它的 `$httpClient` 请求带一条完整的 Surge 策略行作为 `policy-descriptor`（**优先于** `policy`）。它会发真实请求，不修改 Profile 不等于没有副作用。用自带的助手：

```sh
python3 /var/minis/skills/luno-surge/scripts/test_policy_descriptor.py \
  --descriptor-file - --url http://checkip.amazonaws.com
```

- **描述符含密码或 PSK**：默认经 stdin 送一行（`--descriptor-file -`），不落盘、不进 shell history、不写进 Profile。它只引用任务已授权、执行环境已注入的指定变量，缺失就停；不接受聊天里粘贴的秘密，不读凭据文件。`--descriptor-file <path>` 是脚本能力，不是获准的来源。
- 助手只从 `SURGE_API_KEY` 读 key，调用 `/v1/scripting/evaluate`，报告探针的状态、响应体、延迟和错误，**不打印描述符**。
- **目标实例**：要指向用户当次授权连接的 Mac 或 iOS 实例时，用单条命令的环境赋值 `SURGE_HTTP_API_BASE=http://<trusted-host>:6171`，不持久化，不静默换主机。HTTP 回退和描述符探测共用同一套校验：只接受 HTTP(S)，拒绝 URL 里的 userinfo；解析出的主机名不在 `127.0.0.1`、`localhost`、`::1` 这个精确名单里时，还要在同一条命令里设置 `SURGE_ALLOW_REMOTE=1`。这个开关只在获得目标连接的当次授权后单条命令设置，不持久化；环境里已有的 base 或开关不等于授权。
- 明文 HTTP 的风险按上文〈连接与授权共同前置〉。解释探针失败前先按〈引擎状态预检〉预检：Suspend 是通用的网络诊断考虑，不是 `policy-descriptor` 特有的限制。

## Metrics（iOS 5.22.0+）

`GET /v1/metrics` 输出 Prometheus 文本，**不是 JSON**，同样需要 `X-Key`。用助手可以避免在 curl 命令里暴露 key：

```sh
python3 /var/minis/skills/luno-surge/scripts/surge_ios.py metrics
```

正式版 iOS 5.22.0 build 3830 上（2026-09-02）验证过它暴露 build 信息、uptime、内存、活动请求、DNS 缓存、封禁计量，以及按接口和策略的流量计数器（不代表当前版本）。官方手册确认路由是 `/v1/metrics`，裸 `/metrics` 不是 API 路由。流量计数器在引擎重启时归零，PromQL 的 `rate()`/`increase()` 能处理重置。Prometheus 通常加不了 `X-Key` 头，实际抓取可以用 `x-key` 查询参数，这个 key 不得进入聊天、日志或共享配置。

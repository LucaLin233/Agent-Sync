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

描述符探测或相关解释前，完整读 `references/http-descriptor.md`；它会发真实请求，不修改 Profile 不等于没有副作用。

## Metrics（iOS 5.22.0+）

Prometheus、metrics 的解释或采集前，完整读 `references/http-metrics.md`；不把历史验证当当前能力。

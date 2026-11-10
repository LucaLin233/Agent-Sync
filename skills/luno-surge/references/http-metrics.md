# Surge Metrics

先完整读 `references/http-api.md`，满足共同前置；本资源不扩大实例连接、凭据、写入、真实流量或发布授权。

## Metrics（iOS 5.22.0+）

`GET /v1/metrics` 输出 Prometheus 文本，**不是 JSON**，同样需要 `X-Key`。用助手可以避免在 curl 命令里暴露 key：

```sh
python3 /var/minis/skills/luno-surge/scripts/surge_ios.py metrics
```

正式版 iOS 5.22.0 build 3830 上（2026-09-02）验证过它暴露 build 信息、uptime、内存、活动请求、DNS 缓存、封禁计量，以及按接口和策略的流量计数器（不代表当前版本）。官方手册确认路由是 `/v1/metrics`，裸 `/metrics` 不是 API 路由。流量计数器在引擎重启时归零，PromQL 的 `rate()`/`increase()` 能处理重置。Prometheus 通常加不了 `X-Key` 头，实际抓取可以用 `x-key` 查询参数，这个 key 不得进入聊天、日志或共享配置。

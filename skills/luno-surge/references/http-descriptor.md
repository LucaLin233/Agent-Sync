# Surge 未配置节点探测

先完整读 `references/http-api.md`，满足共同前置；本资源不扩大实例连接、凭据、写入、真实流量或发布授权。

## 用 `policy-descriptor` 测未配置的节点

`POST /v1/policies/test` 只接受已配置的策略名。想不动 Profile 测新节点，可以执行一个 cron 脚本，让它的 `$httpClient` 请求带一条完整的 Surge 策略行作为 `policy-descriptor`（**优先于** `policy`）。用自带的助手：

```sh
python3 /var/minis/skills/luno-surge/scripts/test_policy_descriptor.py \
  --descriptor-file - --url http://checkip.amazonaws.com
```

- **描述符含密码或 PSK**：默认经 stdin 送一行（`--descriptor-file -`），不落盘、不进 shell history、不写进 Profile。它只引用任务已授权、执行环境已注入的指定变量，缺失就停；不接受聊天里粘贴的秘密，不读凭据文件。`--descriptor-file <path>` 是脚本能力，不是获准的来源。
- 助手只从 `SURGE_API_KEY` 读 key，调用 `/v1/scripting/evaluate`，报告探针的状态、响应体、延迟和错误，**不打印描述符**。
- **目标实例**：要指向用户当次授权连接的 Mac 或 iOS 实例时，用单条命令的环境赋值 `SURGE_HTTP_API_BASE=http://<trusted-host>:6171`，不持久化，不静默换主机。HTTP 回退和描述符探测共用同一套校验：只接受 HTTP(S)，拒绝 URL 里的 userinfo；解析出的主机名不在 `127.0.0.1`、`localhost`、`::1` 这个精确名单里时，还要在同一条命令里设置 `SURGE_ALLOW_REMOTE=1`。这个开关只在获得目标连接的当次授权后单条命令设置，不持久化；环境里已有的 base 或开关不等于授权。
- 明文 HTTP 会把 API key 和描述符暴露在网络上，远程只用于可信局域网，否则改用 HTTPS。解释探针失败前先按 `references/http-api.md`〈引擎状态预检〉预检：Suspend 是通用的网络诊断考虑，不是 `policy-descriptor` 特有的限制。


分支：http-api、http-sections。读法见 luno-core 入口〈加载〉。

<a id="branch-http-api"></a>
<!-- BEGIN http-api -->
# Surge HTTP API 回退

端点、method、参数和返回以官方 [HTTP API](https://manual.nssurge.com/tools/http-api.md) 为准（iOS 4.4.0+，每个请求带 `X-Key`）；本包不复制端点目录。调用前按当前平台和版本取得完整契约，并确认 `scripts/surge_ios.py` 支持这个形态；未知就停，不猜路由，不把 Mac 专属端点用到 iOS 上。

## 引擎状态预检

依赖 Surge 联网的任务（包括这条回退路径）先按入口 §2 预检。API 能响应不等于引擎在正常处理流量：Suspend 时内层 `$httpClient` 探针可能返回 EOF 或超时；遇到意外的 EOF 或超时要重新预检，不沿用之前的状态。

## 连接与授权

HTTP API 仍须满足入口的实例、认证、平台和版本门槛：默认同机，活动实例或其他目标须由用户指定并授权。远程明文 HTTP 会暴露 API key，描述符探测还会暴露节点密码或 PSK，只能在获准的可信局域网使用，其他情况用 HTTPS。分节写入更严，见 `references/http-api.md`〔分支 http-sections〕。危险操作按入口再次单独确认，不自动启用监听、MCP、MITM，也不关闭证书校验。

## 安全分节写入

分节读取、编辑、恢复，以及相关方案和判断之前，完整读 `references/http-api.md`〔分支 http-sections〕，并按其中要求读 `references/command-reference.md`〔分支 platform-compatibility〕；缺失就停止依赖它的部分。

## 用 `policy-descriptor` 测未配置的节点

`POST /v1/policies/test` 只接受已配置的策略名。想不动 Profile 测新节点，可以执行一个 cron 脚本，让它的 `$httpClient` 请求带一条完整的 Surge 策略行作为 `policy-descriptor`（**优先于** `policy`）。它会发真实请求，不修改 Profile 不等于没有副作用。用自带的助手：

```sh
python3 /var/minis/skills/luno-surge/scripts/test_policy_descriptor.py \
  --descriptor-file - --url http://checkip.amazonaws.com
```

- **描述符含密码或 PSK**：经 stdin 送一行（`--descriptor-file -`），不落盘、不进 shell history、不写进 Profile。它只引用任务已授权、执行环境已注入的指定变量，缺失就停；不接受聊天里粘贴的秘密，不读凭据文件。`--descriptor-file <path>` 是脚本能力，不是获准的来源。
- 助手只从 `SURGE_API_KEY` 读 key，调用 `/v1/scripting/evaluate`，报告探针的状态、响应体、延迟和错误，**不打印描述符**。
- **目标实例**：指向用户当次授权连接的实例时，用单条命令的环境赋值 `SURGE_HTTP_API_BASE=http://<trusted-host>:6171`，不持久化，不静默换主机。只接受 HTTP(S)，拒绝 URL 里的 userinfo；主机不在 `127.0.0.1`、`localhost`、`::1` 这个精确名单里时，还要在同一条命令里设置 `SURGE_ALLOW_REMOTE=1`。这个开关只在获得目标连接的当次授权后设置；环境里已有的 base 或开关不等于授权。
- 解释探针失败之前先按〈引擎状态预检〉预检：Suspend 是通用的网络诊断考虑，不是 `policy-descriptor` 特有的限制。

## Metrics（iOS 5.22.0+）

`GET /v1/metrics` 输出 Prometheus 文本，不是 JSON，同样需要 `X-Key`；指标清单和抓取配置见官方 HTTP API 页。用助手可以避免在 curl 命令里暴露 key：

```sh
python3 /var/minis/skills/luno-surge/scripts/surge_ios.py metrics
```

2026-09-02 在正式版 iOS 5.22.0 build 3830 上实测过这个端点（不代表当前版本）。流量计数器在引擎重启时归零。Prometheus 用 `x-key` 查询参数抓取时，这个 key 不得进入聊天、日志或共享配置。
<!-- END http-api -->

<a id="branch-http-sections"></a>
<!-- BEGIN http-sections -->
# Surge 安全分节写入

先完整读 `references/http-api.md`〔分支 http-api〕，满足共同前置；本资源不扩大实例连接、凭据、写入、真实流量或发布授权。

接口契约见官方 [HTTP API](https://manual.nssurge.com/tools/http-api.md)〈Profile Sections〉和 [CLI](https://manual.nssurge.com/tools/cli.md)〈Editing Profile Sections〉（2026-11-12 读）：GET 取不带 header 的 content 和 revision，POST 提交 name、content、revision；服务端先校验完整 profile，再写承载文件并 reload；托管、企业、URL 来源、多文件拼接和自身行混 include 的节只读。两个入口的条件按各自契约判断，不推定完全相同。版本、协议和权益条件见 `references/command-reference.md`〔分支 platform-compatibility〕。

## 本端限制

- 官方允许创建节，本端入口只替换已有的节，不开放创建、删除和清空。
- 写入必带 revision；revision 变了就停，不丢弃 revision，也不自动刷新后重发。
- 不依赖 sections 列表或 POST 成功体里未确定的 schema；写完用 GET 读同一节核对 content 和 revision，HTTP 200 不算验收。

## 调用前由调用方负责的条件

脚本证明不了这些，调用前要核实并保持：

- 实例和当前 profile 的绑定、版本、目标节、读写授权，以及独占的编辑窗口。revision 不是跨设备的锁，其他编辑端和云同步写回也要纳入独占条件；保持不了就不调用。
- 只读取读之前就有明确非秘密来源、并且获准的完整单节原文；含秘密或来源未知就停，不先导出再脱敏。`--raw`、`profile diff`、`sensitive=0` 的输出都不能当回写原稿。不读凭据文件、整份 profile 和未知的节；`SURGE_API_KEY` 只用于认证。

## 本端入口

`python3 -B scripts/surge_ios.py --confirm-dangerous section replace --input -`，stdin 是一份 UTF-8 JSON，字段只有 name、revision、original、content、backup_dir。用户数据不放 argv 或普通日志；原文按 UTF-8 保留换行、空行和注释，不 trim、不脱敏。流程：GET 核对原稿和 revision → 把实际的原单节内容和 revision 写入当次授权的受控备份 → POST → GET 核验。

- **备份目录**：本用户所有、权限恰好 0700 的真实目录；路径不经符号链接，不含 `//`、`.`、`..`。脚本在联网前逐级打开并持有该目录，备份文件以 0600 新建、fsync 后读回核对；任一步失败都不发 POST。这只是单节的受控恢复备份，另有文件级恢复需求时再安排目标侧的文件备份。
- **连接**：认证用已授权的 `SURGE_API_KEY` 作 `X-Key`。入口不跟随重定向、不用代理环境变量；只有精确的 loopback IP 可以用 HTTP，其他目标要有当次的远端授权和可信的 HTTPS，并校验证书和主机名。信任 Surge MITM CA 的条件必须事先具备，不自动开监听、开 MCP、装 CA 或关闭校验。
- **输出**：只有固定的状态和错误类别；正文、revision、HTTP 错误体和未知字段都不进输出。

## 错误与恢复

POST 超时、EOF 或写后核验失败时，按「可能已经写入」处理，不盲目重投，也不自动回滚。固定 token 和退出码：读取解码 `E_READ_DECODE`/4，写后核验 `E_VERIFY_FAILED`/5，写请求 `E_REJECTED`/4 或 `E_WRITE_UNKNOWN`/5（含传输层协议异常，不重试）；argv 形状不合格或 stdin 不合规只回 `E_INPUT`/2，不回显 argv；普通的 `request POST` 命中分节路由时，在解析 JSON、取密和联网之前就被拒绝。

恢复：先核对是同一个实例和 profile、当前的单节不含秘密；当前内容仍等于本次写入的内容、且没有后续编辑时，用当前的 revision 和当前原稿经同一入口写回备份的原文，再 GET 验证。有新改动或绑定不明就停，不能强制覆盖。恢复同样需要授权和再次确认；备份撤销不了 reload 的副作用和云同步。

## 云同步

官方 CLI 手册写明：iOS 改动后立即上传 iCloud Drive，Dropbox 在主 App 下次打开时上传；Surge 的 iCloud Drive 文件夹超过 200 个文件和文件夹时后台同步不可用，主 App 关闭期间不能用分节编辑修改存放在那里的 profile。这不证明 HTTP API 在所有 App 状态下都按同样条件拒绝。遇到 `E_REJECTED` 不重试、不换入口绕过；入口不输出错误体，需要时请用户在 App 里查看报错、App 状态和该目录的文件数。文件回滚撤销不了已经发生的云同步。

## 内置 MCP

`POST /v1/mcp` 默认关闭，用 `http-api-mcp=true` 启用，和 HTTP API 共用 key；工具清单见官方 HTTP API 页。启用 MCP 须另获授权，不自动执行；工具注解不代替授权，iOS 6 的 MCP 另需核对订阅权益。官方 CLI `profile section set <name> <file|-> [revision]` 的本地文件和 stdin 转换不能照搬到 Controller 桥上。
<!-- END http-sections -->

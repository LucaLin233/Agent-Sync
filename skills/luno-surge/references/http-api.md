分支：http-api、http-sections。读法见 luno-core 入口〈加载〉。

<a id="branch-http-api"></a>
<!-- BEGIN http-api -->
# Surge iOS HTTP API

官方手册：<https://manual.nssurge.com/tools/http-api.html>。需要 Surge iOS 4.4.0+；每个请求带 `X-Key`；GET 用查询参数，POST 用 JSON 体；除注明外响应是 JSON。

## 引擎状态预检

依赖 Surge 联网的任务（包括这条回退路径）先按入口 §2 预检。HTTP 特有的判读：API 能响应，不等于引擎在正常处理流量；Suspend 时内层 `$httpClient` 探针可能返回 EOF 或超时，遇到意外的 EOF 或超时要重新预检，不沿用之前的状态。

## 端点发现

普通的 Features、Outbound/策略、请求、Profile/DNS/模块、脚本和事件端点，本包不复制目录表。实际调用前按当前平台和版本的官方手册取得 method、完整 path、输入和结果契约，并确认脚本支持这个形态；未知就停，不猜路由。不把 macOS 专属端点套到 iOS 上。

## 连接与授权共同前置

HTTP API 仍须先满足入口的实例、认证、平台与版本门槛；默认同机，活动实例或其他目标须由用户指定且已授权。远程明文 HTTP 会暴露 API key；描述符探测还会暴露节点密码或 PSK，只能在获准的可信局域网使用，其他情况用 HTTPS。分节写入更严格：除精确 loopback IP 外必须是已获授权的可信 HTTPS，不能因这里的普通回退条件而放宽。危险操作仍按入口再次单独确认，不自动启用监听、MCP、MITM 或关闭校验。

## 安全分节写入

分节读取、编辑、恢复或相关方案与判断前，完整读 `references/http-api.md`〔分支 http-sections〕，并按其中要求读 `references/command-reference.md`〔分支 platform-compatibility〕；缺失就停止依赖部分。

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
<!-- END http-api -->

<a id="branch-http-sections"></a>
<!-- BEGIN http-sections -->
# Surge 安全分节写入

先完整读 `references/http-api.md`〔分支 http-api〕，满足共同前置；本资源不扩大实例连接、凭据、写入、真实流量或发布授权。

## 安全分节写入

依据 <https://manual.nssurge.com/tools/http-api.html> 的 Profile Sections/MCP 和 <https://manual.nssurge.com/tools/cli.html> 的 Editing Profile Sections（2026-11-11 读取）；两个入口的条件分别按其契约判断，不推定完全相同。版本、协议和权益条件见 `references/command-reference.md`〔分支 platform-compatibility〕。

**官方接口**：GET `/v1/profiles/section?name=…` 返回不带 header 的 content 和 revision；POST `/v1/profiles/section` 提交 JSON 的 name、content、revision。服务端先校验完整的 profile，再写承载文件并 reload；托管或企业的、来自 URL 或托管来源的、多文件拼接的，以及自身行与 include 混合的 section，服务端会拒绝编辑。官方允许创建，但本端的最小安全入口不开放创建、删除和清空。本端写入必带 revision，不丢弃，也不自动更新后重发。不依赖 sections 列表或 POST 成功体里未确定的 schema；写完用 GET 读同一节核对 content 和 revision，不以 HTTP 200 作验收。

**调用前由调用方负责的条件**（脚本证明不了）：

- 实例和当前 profile 的绑定、版本、现有的 section、读写授权，以及独占的编辑窗口，都由调用方在调用前核实并保持。revision 不是跨设备的锁，其他编辑端和云同步写回也要纳入独占条件；保持不了就不调用。
- 只对读之前就有明确非秘密来源、并且获准的完整单节读原文；含秘密或来源未知就停，不先导出再脱敏。`--raw`、`profile diff`、`sensitive=0` 的输出都不能当回写原稿。不读凭据文件、整份 profile 和未知的节；`SURGE_API_KEY` 只用于认证。

**本端入口**：`python3 -B scripts/surge_ios.py --confirm-dangerous section replace --input -`，stdin 是一份 UTF-8 JSON，字段只有 name、revision、original、content、backup_dir。用户数据不放 argv 或普通日志；原文按 UTF-8 保留换行、空行和注释，不 trim、不脱敏。流程是：GET 核对原稿和 revision → 把实际的原单节内容和 revision 写入当次授权的受控备份 → POST → GET 核验。

**备份要求**（任一项失败都不发 POST）：

- 联网之前，从根目录逐级用 `O_DIRECTORY|O_NOFOLLOW` 打开备份目录并持有末级目录的 fd，不再按完整路径重新解析；拒绝符号链接和 `//`、`.`、`..` 这类歧义的路径分量。目录必须属于本用户，权限恰好是 0700（0500 这类只读目录也拒绝）。
- 备份文件 0600，用 O_EXCL 创建，fsync 之后读回核对；O_EXCL 或 fsync 失败时，只清除本次创建、且 dev/ino 仍然匹配的文件，已有的同名文件不动。
- 这是单节的受控恢复备份，不是完整文件的逐字备份；另有文件级恢复需求时才额外安排目标侧的文件备份。

**连接与输出**：认证用已授权的 `SURGE_API_KEY` 作 `X-Key`。入口不跟随重定向、不用代理环境变量；只有精确的 loopback IP 可以用 HTTP，其他目标要有当次的远端授权和可信的 HTTPS，并校验证书和主机名。信任 Surge MITM CA 的条件必须事先具备，不自动开监听、开 MCP、装 CA 或关闭校验。输出只有固定的状态和错误类别，正文、revision、HTTP 错误体和未知字段都不进输出。

**错误处理**：revision 变了就停。POST 超时、EOF 或写后核验失败时，按「可能已经写入」处理，不盲目重投，也不自动回滚。各阶段的固定 token 和退出码：读取解码 `E_READ_DECODE`/4，写后核验 `E_VERIFY_FAILED`/5，写请求 `E_REJECTED`/4 或 `E_WRITE_UNKNOWN`/5（含传输层协议异常，不重试）。argv 形状不合格或 stdin 不合规都只回固定的 `E_INPUT`/2，不回显 argv；普通的 `request POST` 命中分节路由时，在解析 JSON、取密和联网之前就拒绝。

**恢复**：先核对是同一个实例和 profile、当前的单节不含秘密；当前内容仍等于本次写入的目标内容、且没有后续编辑时，用当前的 revision 和当前原稿经同一入口写回备份的原文，再 GET 验证。有新改动或绑定不明就停，不能强制覆盖。恢复同样需要授权和再次确认；备份撤销不了 reload 的副作用和云同步。

**回归范围**：测试用本机合成数据和本机随机端口的夹具（真实子进程入口，含可信 CA 正向和 hostname 错配两组 TLS 用例），不等于设备实测；修改活动配置仍要有当次授权。

**同步注意**：官方 CLI 手册在 profile section 编辑说明中指出，Surge iOS 会立即把变更文件上传 iCloud Drive，Dropbox 在主 App 下次打开时上传；Surge 的 iCloud Drive 文件夹超过 200 个文件和文件夹时后台同步不可用，主 App 关闭期间，不能用该 CLI 分节编辑方式修改存放在该目录的 profile。这不证明 HTTP API 在所有 App 状态下都采用相同的拒绝条件，也不泛化到其他目录的 profile。本端 HTTP 入口的实际限制仍须按对应接口和实例证据核实；遇到 `E_REJECTED` 不重试、不换入口绕过，入口不输出错误体，需要时请用户在 App 中查看报错、App 状态和该目录的文件数。文件回滚不能撤销已经发生的云同步。

**内置 MCP**：默认关闭，端点是 POST `/v1/mcp`，用 `http-api-mcp=true` 启用；stateless Streamable HTTP，和 HTTP API 共用 key，可以用 `X-Key` 或新版的 Bearer。`get_profile_section`/`replace_profile_section` 通过回传 revision 编辑；工具注解不代替授权，iOS 6 的 MCP 另需核对订阅权益。新建或启用 MCP 须另获授权，不自动执行。官方 CLI `profile section set <name> <file|-> [revision]` 的本地文件和 stdin 转换不能照搬到 Controller 桥上。

<!-- END http-sections -->


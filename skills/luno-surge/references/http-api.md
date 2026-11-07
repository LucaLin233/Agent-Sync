# Surge iOS HTTP API 参考

官方手册：<https://manual.nssurge.com/tools/http-api.html>。需 Surge iOS 4.4.0+；每请求带 `X-Key`；GET 用查询参数、POST 用 JSON 体；响应除注明外为 JSON。

## 引擎状态预检

依赖 Surge 联网的任务（含本回退）先按 [../SKILL.md](../SKILL.md) §2 预检。HTTP 特有判读：API 能响应不等于引擎在正常处理流量；Suspend 时内层 `$httpClient` 探针可能返回 `EOF`/超时，意外 EOF/超时后重新预检，不沿用历史状态。

## 安全分节写入

规范：<https://manual.nssurge.com/tools/http-api.md> 的Profile Sections／MCP及<https://manual.nssurge.com/tools/cli.md> 的Editing Profile Sections，2026-11-03核读；版本／协议及权益条件见 `references/platform-compatibility.md`。

GET `/v1/profiles/section?name=…`返回无header的content及revision；POST `/v1/profiles/section`使用JSON name、content、revision。服务端先校验完整profile，再写承载文件并reload；托管／企业、URL／托管来源、多文件拼接或自身行与include混合的section由服务端拒绝编辑。官方允许创建，最小安全入口不开放创建、删除、清空；revision在本端必带，不丢弃或自动更新重发。不依赖sections列表或POST成功体未确定的schema；写后GET同节核content/revision，不以HTTP200作验收。

实例／当前profile绑定、版本、现有section与读写授权、独占编辑窗口由调用方在调用前核实并维持，不由脚本证明。revision不是跨设备锁；调用方须将其他编辑端和云同步写回纳入独占条件，不能维持即不调用。仅对读前已有明确非秘密来源、获准的完整单节读取原文；含密或未知即停，不先导出再脱敏。`--raw`、profile diff、sensitive=0均不可作回写原稿。凭据文件、整profile及未知节不读；SURGE_API_KEY只用于认证。

安全入口采用stdin JSON传name、original、revision、content、backup_dir，用户数据不得放argv或普通日志；原文按UTF-8保留换行、空行、注释，不trim或脱敏。写前GET核原稿/revision，将实际原单节内容与revision写入当次授权的受控备份，再POST，最后GET核验。备份目录在联网前从根目录逐级` O_DIRECTORY|O_NOFOLLOW `打开并持有末级目录fd（不按完整路径重解析，拒绝符号链接与`//`、`.`、`..`等歧义分量），要求本用户所有且权限恰为0700（0500等只读目录同样拒绝）；文件0600、O_EXCL创建、fsync后读回核对，O_EXCL／fsync失败只清除本次创建且dev/ino仍匹配的文件，既有同名文件不动；以上失败均零POST。此为单节受控恢复备份，不是完整文件级逐字备份；只有另有文件级恢复需求时才额外安排目标侧文件备份。

认证用已授权SURGE_API_KEY的X-Key；新入口不跟随重定向、不用代理环境，仅精确loopback IP可用HTTP，其他目标须当次远端授权及可信HTTPS并校验证书／主机名。TLS信任Surge MITM CA须事先具备，不自动启监听、MCP、装CA或关闭校验。输出仅固定状态／错误类别，正文、revision、HTTP错误体和未知字段不进入输出。revision变化即停；POST超时／EOF／写后核验失败按可能已写入处理，不盲重投或自动回滚。

恢复先核同一实例/profile及当前无密单节；当前仍等于本次目标内容且无后续编辑时，用当前revision和当前原稿经同一入口恢复备份原文，再GET验证。存在新改动或绑定不明即停，不能强制覆盖。恢复同样需授权和再次确认；备份不撤销reload副作用或云同步。

iOS改动立即上传iCloud，Dropbox在下次打开App时同步。Surge的iCloud Drive文件夹超过200个文件和文件夹时，后台同步不可用，仅该目录的profiles在App关闭期间受相应修改限制；不泛化为所有profile／前台编辑上限。

内置MCP为默认关闭的POST `/v1/mcp`，启用项http-api-mcp=true；stateless Streamable HTTP，共用API key，可用X-Key或新版Bearer。get_profile_section／replace_profile_section回传revision编辑；工具注解不替代授权，iOS6 MCP另核订阅已解锁／有效试用权益。本批不新建MCP服务或自动启用。官方CLI `profile section set <name> <file|-> [revision]` 的本地文件／stdin转换不能照搬到Controller桥。

本端入口：`python3 -B scripts/surge_ios.py --confirm-dangerous section replace --input -`；stdin为一份UTF-8 JSON，字段仅name、revision、original、content、backup_dir。写后阶段错误按阶段固定token：读`E_READ_DECODE`／4、写后核验`E_VERIFY_FAILED`／5、写请求`E_REJECTED`／4或`E_WRITE_UNKNOWN`／5（含传输级协议异常，不重试）。本入口的argv形状不合格与stdin不合规都只回固定`E_INPUT`／2且不回显argv，普通`request POST`命中分节路由在JSON解析、取密与联网之前即拒绝。回归为本机合成数据＋本机随机端口夹具（真实子进程入口，含可信CA正向与hostname错配两组TLS用例），不等于设备实测；活动配置变更仍须另有本批授权。

## 端点发现

普通Features、Outbound/策略、请求、Profile/DNS/模块、脚本及事件端点不再在本包复制目录表。实际调用前按当前平台/版本的官方HTTP手册取得method、完整path、输入及结果契约；确认脚本支持该形态，未知即停、不猜路由。不把macOS-only端点套iOS；授权、秘密源头投影、危险操作再次确认及本节安全分节写入例外不变。`/v1/metrics`和policy-descriptor的本地特有说明仍见下节。

## 用 `policy-descriptor` 测未配置节点

`POST /v1/policies/test` 只接受已配置策略名。要不动 Profile 探新节点，可执行一个 cron 脚本，其 `$httpClient` 请求带一条完整 Surge 策略行作 `policy-descriptor`（**优先于** `policy`）。

用自带助手；描述符含密码/PSK，默认形式经 stdin 送一行（`--descriptor-file -`），不落盘、不进 shell history、不写入 Profile：

```sh
python3 /var/minis/skills/luno-surge/scripts/test_policy_descriptor.py \
  --descriptor-file - --url http://checkip.amazonaws.com
```

描述符仅引用任务已授权且执行环境已注入的指定变量，经 stdin 送入；缺失即停，不接受聊天粘贴作秘密来源，不读凭据文件、不落盘。`--descriptor-file <path>` 是脚本能力，不是助手获准的来源。

助手只从 `SURGE_API_KEY` 读 key，调 `/v1/scripting/evaluate`，报告探针状态、响应体、延迟与错误且**不打印描述符**。指向用户当次授权连接的活动 Mac/iOS 实例，用单命令环境赋值 `SURGE_HTTP_API_BASE=http://<trusted-host>:6171`，不持久化、不静默换主机。HTTP 回退与描述符探测共用校验：仅接受 HTTP(S)，拒绝 URL userinfo；解析后的 `hostname` 不在精确名单 `127.0.0.1`、`localhost`、`::1` 中时，还须在该命令设置 `SURGE_ALLOW_REMOTE=1`。该开关须获目标连接的当次授权后单命令设置，不持久化；环境中已有 base 或开关值不等于授权。明文 HTTP 会把 API key 与描述符暴露到网络，远程使用限可信局域网或改 HTTPS。解释探针失败前先套用上节预检——Suspend 是通用网络诊断考量，非 `policy-descriptor` 专属限制。

## Metrics（iOS 5.22.0+）

`GET /v1/metrics` 是 Prometheus 文本输出，**不是 JSON**，仍需 `X-Key`；用助手避免在 curl 命令里打印 key：

```sh
python3 /var/minis/skills/luno-surge/scripts/surge_ios.py metrics
```

历史观察：正式版 iOS 5.22.0 build 3830 曾验证暴露 build 信息、uptime、内存、活动请求/DNS 缓存/封禁计量与按接口/策略流量计数器（2026-09-02 记录，非当前版本声明）。官方手册确认 HTTP Controller 路由是 `/v1/metrics`，裸 `/metrics` 不是 API 路由；流量计数器在引擎重启时归零，PromQL `rate()`／`increase()` 可处理重置；Prometheus 通常无法加 `X-Key`，实际抓取可用 `x-key` 查询参数传递——该 key 不得进入聊天、日志或共享配置。

本参考曾于 2026-09-02 对照官方手册与 iOS 5.22.0 build 3830 刷新（历史记录）；增改端点前先查官方 URL。

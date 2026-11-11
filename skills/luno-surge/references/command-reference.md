# 共读资源（按原分支合并）

指针中的“分支”以 branch 锚点及 BEGIN/END 注释定界。沿用各分支原有触发和共同前置：完整读取命中的分支；原规则指定分节时，读取指定完整分节及共同前置，不加载未命中分支。同一文件的命中并集优先一次取齐，返回受限时分块补齐，不以截断内容作已加载。

分支内的“本文件”“本文”“本资源”均只指该分支，不把其他分支的接口事实、版本、能力或权限并入；“本技能”仍指原技能。主体、条件、例外、停止、恢复和许可边界保持原文，不因合并授予额外权限。跨技能先读目标技能入口及产品/业务入口；候选不改变现役规则。

分支：command-reference、controller-cli、platform-compatibility、diagnostics。

<a id="branch-command-reference"></a>
<!-- BEGIN command-reference -->
# Surge 命令知识与操作参考（非官方摘要）

这是依据 Surge Mac 6.11.0 官方命令参考（12680，按 12710 补核），并结合官方公开手册整理的中文接口事实摘要，按本端任务重新组织；不是官方技能或译本，没有原文摘录。取证版本见 `references/upstream-manifest.json`；不是当前设备验收。下列命令即使列出也不等于 Python 桥实现了所有本地转换。协议和平台以 `references/command-reference.md`〔分支 platform-compatibility〕 为执行门槛；连接、认证和编码先完整读 `references/command-reference.md`〔分支 controller-cli〕；安全与再次确认以入口为准。没有证据的参数、输出字段或新版本变化必须停止相关步骤，不用猜测补全。

## 调用与证据

基本调用、全局参数和常用子命令的参数说明，先在本端读 `surge-cli --help` 和 `surge-cli help <command>`，不在本参考复刻。帮助证据的版本和范围见 `references/SOURCE.md`〈本地帮助证据〉。安全读取示例：`env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/nonexistent PYTHONDONTWRITEBYTECODE=1 surge-cli help rule`，不附 --check、远端或认证参数。目标无精确帮助时可能回退到父级或主帮助，且仍正常返回（rc=0）；必须检查输出是否实际覆盖目标用法，不能把父帮助当成目标子命令的完整说明，也不以退出码证明覆盖。

本地帮助足够的用法入口：status、summary、version、mode、global-policy、policy-group、rule、rule temp、profile、module、feature、dns、geoip、http、test、diagnostics、flush、log、logbook、benchmark、vmnet、kill、stop、environment、set、set-log-level。dump/watch/script 只给部分用法，下面只补其缺失知识。plugin、capture-filter 帮助在已核桥上回落主帮助，capture-session 在桥里没有帮助条目，都没有该族的实际契约。

本端 default 同机不授予远程连接权；IPv6 地址使用方括号加端口，参数含 CR/LF 会在本地拒绝。凭据只用入口允许的变量或 stdin，不采纳官方客户端的密码文件、其他凭据变量和交互提示。

**本桥的纯帮助调用仅保证：无命令、以 `help` 为首个命令词，或 `-h`/`--help` 出现在首个命令词之前时，走本地帮助而不连接 Controller；不要混入 `--check`、远端或认证参数。命令词之后的 `-h`/`--help` 不保证本地截获，可能进入认证及 Controller 路径，禁止用这种位置做无连接帮助取证，例如不得为此执行 `version --help` 或 `rule match -h`。本地帮助不能证明远端支持该命令。** 不要换 `--raw` 绕过。需官方帮助时，在用户明确指定且获准的 Mac 上先确认是官方应用包内 `/Applications/Surge.app/Contents/Applications/surge-cli`、核应用身份/版本，再读该二进制的帮助；帮助是否需要远程认证由该工具实际契约决定，不自动连接或换实例。没有获准 Mac 时用 `references/official-sources.md` 路由的官方正文；取不到就停缺证部分。查帮助不豁免身份、平台、网络和秘密门禁。

结果通常是含 `result`、`error` 与任务载荷的 JSON 对象；`hasMore=true` 表示后续还有块。本端优先 `--raw`，但该 JSON 已经客户端脱敏，既不是服务端原始字节，也不保证可以公开。变更需回读同一对象；脱敏的 profile、diff 或单节正文不能回写。

连接超时 8 秒；认证、普通命令及有限流的 socket 读超时 30 秒，均不是任务总时限。有限流包括带宽、加密 benchmark 和 test-ponte；watch、log watch、diagnostics 在认证后无 socket 读超时，首帧也须外部限时。流完成应核 `hasMore=false` 或该命令明确终态，不以首帧当完成。

## 先观察，再决定变更

以下读取也须先限定已确认非秘密的字段和实际需要的量；本表不授权全量导出。

|任务|离线调用知识与结果判读|
|---|---|
|识别实例|通过 help version/status 取字段概览；`profile-path` 为本地文件路径，非文件来源可无路径；`environment` 是环境字典，不默认全量展示。Controller 响应不能证明引擎/VPN 正在处理流量。|
|被动网络概览|summary 的用法/被动查询性质已在 help；桥把它转为 `dump summary`。Network Indicators 不是新测量。`canPingRouter`、`canTestDNS`、`canTestEncryptDNS` 只表示后续测试资格。`network` 中 type/ssid/interface/ipv4-address/ipv4-router、后增 ipv4/ipv6 与 encrypted-dns 的协议门槛见平台表。|
|读取模式与组|语法分别查 help mode/global-policy/policy-group。组结果中的 line-hash 可用于单代理诊断，不从 dump policy 猜 line-hash。|
|配置与模块|语法查 help profile；本桥 diff 会取原始与有效配置并在本地比较，可能含秘密。profile 的 list/check 仅 Mac；check 不合格是命令错误。模块/特性语法查 help module/feature。|
|外部资源|`external-resource list` 含 ready，远程资源可含 updatedAt。|
|单代理/隧道|`show-policy <policy-name>` 查看策略详情；`proxy-runtime-status <policy-name|line-hash>` 观察流量/速率、UDP relay、测试能力、近期连接错误。WireGuard 还看有效底层策略、活动 TCP/UDP 数与 peer 握手；Tailscale 看会话错误、本地地址、Exit Node、DERP、peer path 和 MagicDNS 等实际提供的信息。先此项，后定向日志。|
|设备/网关|仅 Mac：`device list|show <identifier|mac>` 和 VMNET 各表；语法查 help vmnet，字段按〈调用与证据〉取官方 Mac 资料。status 在 VMNET 未运行时仍返回 running=false，其他表会报错。|
|数据通道|抓包正文用〈抓包会话〉的 `capture-session`；旧的 `retrieve-data <record-id> <request|response> [replica-dir]` 走原始数据通道，本桥不渲染，已被前者取代。`get-resource device-icon <id...>` 返回 Base64 图标；两者不是普通状态查询，正文/资源须单独授权和限制，不进入支持包。`provider-message <base64-data>` 发 Packet Tunnel Provider 消息，不支持 Mac，不能当只读探测。|

## 路由、DNS 和主动测量

路由/DNS/临时规则/性能/Tailscale/WireGuard 工作先完整读 `references/command-reference.md`〔分支 diagnostics〕。

rule 的基本形式查 help rule；匹配只评价当前规则，不创建业务连接；match 看命中规则与最终策略，explain 另给组解析链、决策理由、smart 选择、底层代理链及评价说明。裸 hostname 默认 TCP/443，HTTP(S) URL 提供 URL、Host、SNI、协议与端口。可覆盖 hostname、dest-port（别名 port）、process-path、user-agent、url、sni、http-host、source-address、source-port、is-local（别名 local）、client-mac、listen-port、protocol、device-name；空值用于清除可选字段，不按返回内容猜新键。

DNS 参数查 help dns；经过 Surge DNS 流程会产生查询流量；lookup 看 A/AAAA、回答服务器、接口/路径、耗时与缓存到期，trace 增加解析轨迹。指定接口不存在会失败。GeoIP 用法查 help geoip；它本地查询国家/ASN/组织及两个数据库日期，无记录字段可为 null。

|测量目标|语法、负载与限制|
|---|---|
|当前网络|环境测试类型和调用查 help test；test-network 返回 time。它们不属于 dump，也不是 test-policy 的子命令。|
|策略 RTT/组|调用查 help test；当前历史 Controller 支持 test-policy 多个策略参数，不把单参数帮助当上限。test-group 立即重测组，test-all-policies 重测所有策略，影响范围更大，不能默认替代单策略测试。|
|UDP/STUN|UDP 调用查 help test，支持多个策略参数且需 Internet 出网；P2P Tailscale/WireGuard 的 rtt-only 返回 not-applicable 不证明隧道坏，改用 RTT。external-ip/nat-type 的策略测试为 STUN 探测。|
|真实 HTTP|用法查 help http；probe 发 HEAD，未给策略则按规则选路；结果看状态、时序、路由及 headers，非无副作用模拟。|
|带宽/Ponte|语法查 help test；带宽和 Ponte 测试是流，必须限时并核终态。|
|本地计算负载|基本调用查 help benchmark；encryption 测 Surge 所在设备而非 CLI 主机的加密吞吐/正确性，不是网络带宽；默认 100 MiB，整数 1–1024，块 type=start/line/complete，中断后当前 primitive 完成才取消。rule-matching 对随机 hostname 做最坏全扫描，返回单个 average-ns，不是流。|

## 运行数据、日志与事件

`dump <type> [extra]` 的历史类型全集按用途列在下表；某类型不提供更细字段契约时只能承认其目录存在，不能自造 payload。多数原始运行数据具有隐私面，先定字段、数量和时间窗。

|用途|type 及已核说明|
|---|---|
|请求/地址|active、recent、request、dns；dns-lookup-times 为最近 24 次实际发往服务器的查询耗时（ms，旧到新，协议≥28）；virtual-ip-db 是全库，优先 `virtual-ip <ip|domain-substring>`：IPv4 精确匹配、域名不区分大小写子串匹配。|
|策略/配置|policy、auto-test-group-result、policy-group-sub-policies、smart-group-info、rule、map-remote、map-local、temp-rule、profile、event；`dump profile original|effective` 分别看原始与有效配置，可能含秘密，不默认读取。|
|流量/使用度|traffic（testBytes 是策略测试产生的字节，协议≥35）；traffic-stat 可加 prefix；traffic-stat-host；traffic-stat-hourly 是本地今日逐小时 total/DIRECT（协议≥28），其中 policy 映射是今日有流量的策略分小时数据（协议≥29）；policy-usage 按 line-hash 给近期使用分数，最后使用十分钟后衰减为零（协议≥29）；`traffic-stat-breakdown <主> <次>` 按 host、policy、interface、process、device 中两个不同维度交叉汇总今日、本月和上月，process/device 区分本机进程路径与其他设备 MAC；`traffic-stat-records <today|this-month|last-month>` 给该期按 host、policy、interface 合并的记录，只有它带 requestCount；这两项的版本及当前实例支持条件见平台表，不使用未核实的 Controller Protocol 数字作门槛。|
|概览/性能|summary；performance 含 memory-bytes、运行时长、活动请求/DNS cache/virtual IP/临时规则/封禁数量；rule-usage 是两次 App 收集间的命中计数，App 会定期取走（历史 iOS 每六小时），dump 本身不清空，不应误称自启动累计。|

日志基本调用查 help log；省略为 file/100，单给数量沿用 file，范围 1–10000，旧到新。memory 保留近期各级，file 受运行日志级别限制。log 的 watch 只订阅新日志，不重放旧内容，可能一直无事件；外部限时。保留日志的字段为 source、requested-line-count、line-count、log，事件字段为 level、module、log。语法查 help set-log-level；它改运行级别，不写 Profile，level 允许值未在本历史资料穷举，需当前证据；不能猜。用法查 help logbook；它返回 records 与 truncated，新到旧；协议≥27 的响应大小上限历史约 iOS 3 MB/Mac 15 MB，会跳过放不下的记录，truncated=true 不是所有记录已取到。`script-log <log-name> <session-id>` 定位单次脚本记录。

**抓包会话**（版本及当前实例支持条件见平台表）：`dump recent` 只留近期记录；HTTP capture 把会话内每个请求连同头和正文存盘，`capture-session` 读取这些会话（iOS 经 Controller 同样可读）。流程：需要时先 `capture-filter set on-disk …` 收窄范围 → 同一条 `set` 先写 `ReplicaSessionParameters.*` 限额、最后写 `Replica=1` 开始（默认 180 秒、100 个请求、50 MB，0 为不限）→ `feature set capture off` 或到达限额结束 → 读取。开始前告知用户并按入口 §3 确认：开关抓包会断开全部现有连接；抓包期间 MITM override 名单内的主机（默认除 Apple、iCloud 等少数外几乎全部）即使 MITM 关闭也会被解密，需要设备信任 profile 里的 CA，`ReplicaSessionParameters.mitmOverride=0` 把解密限回 `[MITM]` 主机名；会话中途改 `ReplicaSessionParameters.*` 会结束当前会话（endReason=replaced）并另起一个，所以限额要先设；限额存在环境里，用户没要求保留就事后恢复原值。

读取：`capture-session list [include-size]` 新到旧，active 表示正在写入，include-size 会读遍文件，非必要不加；`dump <会话> [offset=N] [limit=N] [filter=TEXT]` 按存盘顺序返回记录及其 key，limit 默认 100、上限 500，filter 对 URL、主机、地址、策略、规则、进程、设备、状态和方法做不区分大小写的子串匹配，翻页到 offset+returned 达到 total（有 filter 时为 matched）；`data <会话> <key> <request|response> [offset=N] [length=N]` 每次最多 1 MiB（默认 512 KiB），`--raw` 下正文为 base64，truncated=true 时按已取字节推进 offset 续读。会话用 name、请求用 key 定位，不用请求 id（引擎重启后会重复），两者含空格要加引号。正文按传输原样存，有 Content-Encoding 时先解码；取正文报错表示没存下正文（没有发送或 HTTPS 未解密）。会话内容和正文按入口 §3 的隐私数据处理。

订阅的已知基本形式查 help watch，但该帮助未列全事件；支持多个 event 参数；无参数表示取消订阅，本桥 `watch speed` 转 real-time-speed。离线事件名全集按用途为：速度/策略 real-time-speed、auto-test-group、policy-benchmark；流量 request、request-update、traffic、dns；状态 summary、environment、reload、shutdown、network-changed；设备 device-name-map、device-info；诊断 diagnostics、dns-flush、log。network-changed 在新网络稳定后发送，无 payload，协议≥29；log 推荐走 log watch。未在原资料定义的事件字段不在此臆造。诊断用法查 help diagnostics；它启动诊断流，配合 `stop-diagnostics` 停止；长期流按外部限时及真实终态处理。

## 变更路径与隐含副作用

下列是语法知识，不是授权。模式/策略、profile 切换或更新、批量连接终止、stop/restart 等保持入口的再次单独确认；其他操作按实际影响核授权。

|目标|语法与变化契约|
|---|---|
|模式/策略|语法分别查 help mode/global-policy/policy-group；auto 清自动组 override。任务型命令优先于内部 set；返回变化后的状态，仍要同对象回读。|
|特性|共享名及基本用法查 help feature；Mac 才有 system-proxy/enhanced-mode，后两者等待实际切换，未完成报错。启 MITM/Rewrite/脚本/抓包先说明隐私影响；开关抓包会断开全部现有连接，按入口 §3 再确认。|
|捕获范围|协议≥36：`capture-filter list`、`get <in-memory|on-disk>`、`set <scope> <option=value>...`；in-memory 管未开 HTTP capture 时的近期记录，on-disk 管 capture 会话。选项顺序应用，任一无效则不修改。http-only/hide-crash-reporter/hide-apple/hide-udp 为 on/off，crash reporter 默认隐藏；type=off/with-keywords/without-keywords/pattern；keywords=a,b,... 替换（空清除），add-keyword/remove-keyword 单项增删，enable-keyword/disable-keyword 保留但切换。含逗号单项用 add-keyword。pattern 的 *、? 与前缀 - 排除主机语义需保留。list 返回 active 和 filters，get/set 返回 scope、active 布尔与 filter；filter 字段为 httpOnly、hideCrashReporterRequests、hideAppleRequests、hideUDP、type、keywords、disabledKeywords。隐藏项、http-only 和关键词过滤共同决定记录范围，不改变网络是否通。|
|模块/资源|语法查 help module；改变模块状态会安排 profile reload；`external-resource update <key|all>` 会更新资源，all 不作为默认；Mac 的 `managed-profile update` 强制检查活动托管配置，等待下载/校验/替换，变化才安排 reload，返回 updated/unchanged。|
|配置/重载|profile 的基本语法查 help profile；底层 `switch-profile <profile-name>` 同为切配置；Mac 的 `update-profile <base64-rule-section>` 为旧 Rule 更新入口，已由分节入口替代，不能借它绕本桥分节禁令。`reload` 优先差量应用；它与 `restart-engine`、`stop` 的影响和再确认按入口 §3。|
|临时规则|语法查 help rule temp；其 list/add/remove/set-policy/flush 在桥内分别转 dump temp-rule/add-temp-rule/del-temp-rule/update-temp-rule/flush-temp-rule；直接底层命令参数相同。生效范围和清理限制按入口 §3；先列已有项，按实际规则标识删除。|
|连接与封禁|语法查 help kill；它断连接，批量断开按入口 §3。用法查 help flush；它清 DNS 数据，其他 type 未核。`security ban list|clear` 查看/清除未授权访问封禁；clear 不作默认测试恢复。|
|Mac 设备/升级|`set-dhcp-device`、`remove-device-record`、`reconnect-device`、`unattended-upgrade` 仅 Mac，参数按官方 Mac 资料；它们改设备记录、断开客户端或升级，不套到 iOS，也不因在目录出现而获准。|

分节读取/编辑/恢复先完整读 `references/http-api.md`〔分支 http-api〕 和 `references/http-api.md`〔分支 http-sections〕。协议≥31 的 `profile section list` 按 Profile 顺序列节的来源相对文件、editable/reason、行数和 revision；get <name> 取无节标题的正文及 file/editable/exists/revision，可能含密码。官方 set <name> <file|-> [revision] 是整节替换/缺节则主文件末尾创建、整 Profile 验证后写回并 reload，revision 冲突拒绝；但**本桥没有文件/stdin 转换，连接、读文件、取密前即拒绝 set，包括 --raw，禁止绕过**。托管/企业、URL/托管 include、多文件汇成或混自身行与 include 的节只读；正文不能另含 header，include 文件中不能再插 include。iOS 写入会触发 iCloud、Dropbox 另有主 App 时机和文件数限制，细节只以安全分节分支为准，不能靠文件回滚撤销已发同步。

## 脚本、Mac 插件与本地能力

基础语法查 help script；run 可执行已启用或已禁用的配置 cron，返回输出与结果/异常，并非只读。桥的 `script evaluate <file> [mock-type] [timeout] [engine] [argument]` 读取显式 JS 文件，转 Base64 并转换 mock 名：http-request/http-response/cron/event/rule/dns/generic；engine=auto/jsc/webview。Controller 接口本身为 evaluate <base64-js> 等后续位置参数；不能把 Controller 编码与本地文件入口混用。先审脚本/读取授权，评估可有真实网络或修改行为，mock 不保证隔离。

Mac 插件在线命令的子命令和门槛见平台表，输出字段按官方 Mac 资料；list/info 的 values 可能含秘密，先限制读取。configure、load-unpacked、uninstall 的影响和开发流程先读 `references/plugin-authoring.md`。

`plugin validate`、`plugin pack` 和 `lsp` 是官方 Mac 本地能力（pack 产物见插件指南，lsp 是编辑器长驻服务），本桥不实现，不能发 Controller。`--check` 的上传风险按入口 §3。

## 环境 key-path：类型、合并与回读

基本语法查 help set；可一次多项，缺等号报 Illegal parameter；值经 CLI 作为字符串传输，bool/int 靠运行时转换，不表示任意 JSON 会解析。`<nil>`/`(null)` 为 null，含 `<nil>` 的整项须 shell 引用，避免重定向。普通键走 key-path 赋值；ProxyGroupSelection. 和 AutoPolicyGroupOverride. 特殊处理为映射合并，不是整个字典替换。复杂数组/字典不直接塞 shell 字面量；只有核实具体 JSON/SDK 入口、类型及授权后才用，不虚构本桥的 JSON 支持。先确认相关现值，只改必要叶子，不默认导出环境全文。

|key 或字典|离线类型与语义|
|---|---|
|ProxyGroupSelection|dict<string,string>；`ProxyGroupSelection.<group>=<policy>` 指定 select 组选择。|
|AutoPolicyGroupOverride|dict<string,string或null>；`AutoPolicyGroupOverride.<group>=<policy>` 强制自动组，引用的 `<nil>` 清 override。组名含点或其他歧义的编码没有本历史契约，不猜。|
|ProxyMode|int；0=Direct、1=Global Proxy、2=Rule；优先 mode。|
|AllProxyModePolicyNameKey|string；全局代理策略名，优先 global-policy。全局模式下非法值可能自动退到有效策略或 DIRECT，不能以发送值当生效值。|
|MitMEnabled、RewriteEnabled、ScriptingEnabled、Replica|bool，分别为 MITM、Rewrite、脚本、HTTP capture 开关；MITM 条件不满足时会自动纠正回 0。|
|PacketCaptureEnabled|bool；历史仅 iOS/tvOS 有效；不是打开 capture 的同义词。|
|SGEnvironmentCellularModeEnabledKey|bool，蜂窝模式；优先 feature。|
|SGEnvironmentCellularModeProcessPathsKey|array<string>，蜂窝模式允许进程路径；复杂结构不拼接未经核实的 shell 值。|

捕获会话字典 `ReplicaSessionParameters`：sizeLimit:int 默认 52428800 字节，requestCountLimit:int 默认 100，timeLimit:int 默认 180 秒，mitmOverride:bool 默认 1，mitmOverrideHostnames:array<string> 为内建名单，mitmOverrideHostnamesDisabled:array<string> 默认空。扩大捕获和 MITM 范围先说明影响；数组的当前内容与安全入口要另核。iOS 6.0.0 / Mac 6.11.0 之前，App 没保存过一次捕获设置时，这类嵌套 key-path（如 `ReplicaSessionParameters.timeLimit`）会被静默丢弃，set 返回成功也要回读；会话中途修改的后果见〈抓包会话〉。

内存/磁盘过滤字典 `InMemoryCaptureFilter`、`OnDiskCaptureFilter`：httpOnly、hideCrashReporterRequest、hideAppleRequest、hideUDP 为 bool（crash reporter 默认 1）；filterType:int 的 0/1/2/3 分别为无/白名单/黑名单/pattern；keywordFilter、disabledKeywordFilter 是 array<string>。注意内部 key 的 Request 单数与 capture-filter 结果字段 Requests 复数不同，不能互相代换。协议≥36 优先任务型 capture-filter set，而非原始复杂 key-path。

`PacketCaptureParameters`：sizeLimit:int 默认 1048576 字节，packetCountLimit:int 默认 100，timeLimit:int 默认 180 秒，packetType:int 的 0/1/6/17 为 Unknown/ICMP/TCP/UDP。成功 set 会发送环境变更通知，但通知、成功回执和真实状态是三件事；必须最小回读，并核自动纠正/回退。

## 覆盖与停止边界

本参考与已核本地帮助共同覆盖官方 12710 §2 的命令名（含高级入口）、§3.2 的 dump 类型、§3.8 事件及 §4 的 key-path/复杂结构事实；结构按观察、负载、变更与类型重新组织，不移植官方叙述或示例集。详细审计映射随制稿方案保存，不进入运行时增加加载负担。§3.17 的官方 rendered 解析器名单不适用于本桥；本桥格式化支持以代码和 controller-cli 为准，其他结果可能仅美化 JSON。

离线知识覆盖不等于执行等价：原目录未给出的数据通道 payload、事件字段、日志级别枚举、provider-message 消息格式和复杂值的可用安全写入口仍属明确缺口；缺证时停止这些参数/字段或执行结论，不撤销已核目录知识，也不擅自接受功能退化。新协议、平台或插件变化逐项核官方资料。未知内容不因未列出被判为不支持；不能把最新官方行为直接归给本桥。

来源与许可：依据官方命令参考整理的接口事实摘要，项目非官方。来源核对和许可限制见 `references/SOURCE.md`；没有把客服短摘录许可扩张为整件、整篇译文、拆分转载或 logo 分发权。未实测的能力不报告通过。
<!-- END command-reference -->

<a id="branch-controller-cli"></a>
<!-- BEGIN controller-cli -->
# Minis Surge CLI

`surge-cli --remote` 的传输和命令行面的 Python 重实现，面向 iOS 上的 iSH/Minis。

## 传输协议

External Controller 是以 CRLF 分隔的命令和结果流：

1. 客户端发送密码 + CRLF；
2. 服务端回 welcome JSON + CRLF；
3. 客户端发送一行文本命令 + CRLF：动词裸写，后面的每个参数用双引号包裹，如 `rule "match" "example.com"`；
4. 服务端回一个结果 JSON 对象，或一串 JSON 事件对象。

含 CR/LF 的参数在本地就拒绝；普通引号和反斜杠在引号字段里原样发送，和官方客户端一致。编码对齐的版本依据见 `references/command-reference.md`〔分支 platform-compatibility〕。

客户端不做 HTTP API 转换。多数命令参数由 Controller 自己解析，所以普通命令的行为随所连的 Surge 版本；客户端只复现官方 CLI 已知的本地转换：`summary`、`profile diff`、`rule temp`、`watch speed`、`script evaluate <file>`（含 mock-type 名到数字 ID 的转换）。macOS 上的在线 `plugin` 操作是普通 Controller 命令；官方 CLI 的离线 `plugin validate`/`pack` 依赖本地 macOS 工具，在 iSH 里**有意不可用**。`--raw` 返回经客户端脱敏的 Controller JSON（紧凑序列化），不保证和服务端原文逐字节一致。

## 安装与凭据

`/usr/local/bin/surge-cli` 是指向 `scripts/surge_cli.py` 的符号链接；默认 Controller 是 `127.0.0.1:6170`，可以用 `SURGE_CLI_REMOTE` 或 `--remote` 覆盖。

凭据按这个优先级取：先 `--password-stdin`，再 `SURGE_API_KEY`（Minis 推荐，存在「设置 → 环境变量」）。客户端非交互：不建也不读密码文件，不在 TTY 提示输入。`SURGE_API_KEY` 缺失时给出 Minis 环境变量的设置入口，不要让用户把密码发到聊天里。调用安全、危险操作再确认和数据最小化按入口 §3。

## 远程管理

依据官方指南 [Surge Remote Management](https://kb.nssurge.com/surge-knowledge-base/guidelines/remote-management)（2026-09-26 读；加 `.md` 取 Markdown 源）。它描述的是官方控制器，不代表每个特性本实现都有。

- **Ponte 与远端 loopback**：有用户授权的 Ponte 通路时，`--remote <name>.sgponte:6170` 可以到达远端 Mac 的 loopback，它的 External Controller 可以继续只绑 `127.0.0.1`，不必为此放宽监听。Surge UI 原生的 Ponte 免密发现和这个 CLI 的 host/port/password 连接是两回事，凭据处理不变。
- **iOS 可达性**：Surge iOS 不能当 Ponte 服务端；蜂窝网络下远程 External Controller 连接会被拒，Wi-Fi 下要开启 Allow Access From Wi-Fi。这些是入站限制，不能证明同机 Minis 的 loopback 可用，要看实际路径。
- **USB**：官方 Mac Dashboard 能管理 USB 连接的 iPhone/iPad（包括走蜂窝时），本 CLI 不实现；不要从通用能力表推断支持 USB。
- **认证封禁**：30 秒内 10 次密码错误会临时封禁来源 IP 或本地进程。先停止反复认证，判断「服务死了」之前先考虑是否被封禁。`security ban` 的查看和清除语法见命令参考；清除封禁不是自动的测试恢复步骤。
- **Ponte 与 HTTP API**：官方对比表把 HTTP API 和 Web Dashboard 标为不支持 Ponte。这说的是原生远程管理集成，不否定「经已有的 `.sgponte` 隧道访问 HTTP 端口」；以实际端点为准。
- **官方与 Minis CLI 的差异**：Mac CLI 不带命令时进交互模式，Minis 打印帮助。指南里的 Mac 专属能力（Gateway 设备、插件、无人值守升级）不是命令规范，也不授权升级或重启。远程功能缺失可能是版本不匹配或 Mac 专属，不一定是传输故障；官方建议两端版本对齐（必要时都用 beta），先诊断，不自动升级。

## 兼容性

多数命令透明转发。status、version、mode、features、策略组、rule match/explain、DNS lookup/trace、modules、GeoIP、performance 和 macOS VMNET 等常用命令有可读的格式化输出，其余打印美化的 JSON；脚本和需要精确 Controller 数据时用 `--raw`。VMNET、`restart-engine` 的平台和协议门槛按 `references/command-reference.md`〔分支 platform-compatibility〕；`reload`、`restart-engine` 的影响和再确认按入口 §3。

`--check <path>`（`-c <path>`）使用 Surge 官方 beta HTTPS 校验服务（`https://services.nssurge.com/v1/config/validate`），因为 iSH 没有 macOS 的本地解析器。它只读显式指定的 UTF-8 文件，以 JSON 的 `profile` 字段 POST 上去，按官方 CLI 的格式打印 `OK` 或 `Failed: ...`，退出码 0 或 1。**这是上传**，限制按入口 §3。
<!-- END controller-cli -->

<a id="branch-platform-compatibility"></a>
<!-- BEGIN platform-compatibility -->
# 平台与协议差异

协议门槛、平台限制和历史验证结论只以本文件为准。其他文件（入口、`references/command-reference.md`〔分支 controller-cli〕、命令参考和插件指南等）里的协议号或版本说法与本文件冲突时，按本文件执行；来源快照中的描述不自动成为当前设备能力。

下面是有日期的版本快照，不代表当前运行的版本。能力异常时先跑 `surge-cli --raw version`，核对 Surge、Core、平台和 Controller Protocol；不要把 App 发行版本和 Controller 内部版本混为一谈。

## 命令门槛

| 能力 | 最低 Controller Protocol | 平台 | 说明 |
|---|---|---|---|
| `rule`、`dns`、`http probe`、`security ban` | 20 | 共享 | |
| `geoip`、性能/规则使用/虚拟 IP 的 dump、`benchmark rule-matching` | 22 | 共享 | |
| `vmnet status`/`arp`/`ndp`/`ra` | 23 | 仅 macOS | 排查 Enhanced/Gateway Mode 的接口、ARP/NDP 邻居和 IPv6 RA 接管；iOS 返回 `Unsupported command` 属正常 |
| `plugin list`/`info`/`parameters`/`load-unpacked`/`configure`/`enable`/`disable`/`select`/`uninstall` | 24 | 仅 macOS | iOS 返回 `Unknown command`；`plugin install` 尚未开放 |
| `restart-engine` | 24 | 共享 | 影响和再确认按入口 §3 |
| logbook 的大小截断语义 | 27 | 共享 | 本行至 capture-filter 行的协议数字沿用官方 Mac 6.11.0 命令参考（12680）的来源记录 |
| `dump dns-lookup-times`、`traffic-stat-hourly`、`summary.network` | 28 | 共享 | |
| `policy-usage`、`traffic-stat-hourly.policy`、`network-changed` 事件 | 29 | 共享 | |
| `summary.network` 的 ipv4/ipv6 | 30 | 共享 | |
| `profile section list`/`get`/`set` | 31 | 共享 | 本端桥不实现 `set`，见下文 |
| `summary.network` 的 encrypted-dns | 33 | 共享 | |
| `traffic.testBytes` | 35 | 共享 | |
| `capture-filter` | 36 | 共享 | 改捕获过滤会影响记录范围，按既有授权和数据最小化执行 |
| `capture-session list`/`dump`/`data` | 未核实，见下文 | iOS / macOS | 读取已存盘的 HTTP 抓包会话，取代 `retrieve-data` |
| `dump traffic-stat-breakdown` | 未核实，见下文 | iOS / macOS | 按两个维度汇总流量 |
| `dump traffic-stat-records` | 未核实，见下文 | iOS / macOS | 读取指定期间的流量及请求计数记录 |

上述已列数字只是有来源版本的能力条件，不代表本端设备已验收。官方 CLI 手册为 capture-session、dump traffic-stat-breakdown 和 dump traffic-stat-records 标注 iOS 6.0.0+ / Mac 6.11.0+，但这三项的最低 Controller Protocol 数字尚未核实，不以未核实的数字判定支持或拒绝，也不从发行版本反推协议号。执行前仍须按入口核对当前实例的平台、发行版本和 build，并取得当前实例支持目标命令的证据；必要条件未知或不满足时停止该项，不能只凭命令列在手册或历史 Protocol 25 推断可用。依据：https://manual.nssurge.com/tools/cli.html（2026-11-11 读取）。

`plugin validate`/`pack` 是官方 macOS CLI 的本地离线工具，不是 Controller 命令，Minis/iSH 客户端不实现。配置插件前先用 `parameters` 读 schema，API Key 等敏感参数不能出现在回复、日志或公开包里；开发契约见 `references/plugin-authoring.md`；未覆盖的当前格式按官方资料核实，缺依据就停止该项。引用上游插件示例时，不把 `insecure: true` 或命令行里的 `token=…` 当本端默认：保持证书校验，密钥只用已授权注入的变量经已核实的安全入口传递，无法避免进入参数或日志时暂停相关配置。

## Surge 6：分节编辑与内置 MCP

- HTTP 分节编辑和内置 MCP 的最低版本是 iOS 6.0.0 / Mac 6.11.0，仍要核对所选实例实际的平台、营销版本和 build。2026-11-03 时 iOS 6 的发布页是 TestFlight，不是 App Store 稳定版。
- iOS 6 的 MCP 另需订阅已解锁或有效试用的权益；装了这个版本或有 TestFlight 资格，都不能证明有这项权益。
- 命令参考和插件指南取材的官方版本和原文哈希，以当前的 `upstream-manifest.json` 为来源证据；拿到安装包或有来源记录，不表示官方原件随包分发，也不表示新能力已经设备实测。
- Minis 自建桥不实现 `profile section set` 的本地文件和 stdin 转换，但保留 `list`/`get` 的只读路径，不因为 `set` 的风险一律禁用。官方 `get` 可能返回含密码的真实正文，本端 `--raw` 仍是客户端脱敏的 JSON，两者都不会自动成为获准的回写原稿。读取和安全写入按 `references/http-api.md`〔分支 http-api〕 执行；这些新能力没有设备实测，历史的只读和重启验收不扩大到它们。

## 历史验证

| Controller build | 日期 | 平台与版本 | 覆盖范围 |
|---|---|---|---|
| 3822 | — | — | 首次验证 `reload` 和 `restart-engine` 的差异（关闭连接、清除缓存和临时规则） |
| 3830 | 2026-09-02 | 正式版 Surge iOS 5.22.0（Controller 内部版本 5.102.0），Protocol 25 | 认证、CRLF 文本命令、JSON Lines 响应和 `restart-engine` 的逐项结论 |
| 3842 | 2026-09-15 | 同上 5.22.0 / Protocol 25 | 复测认证和只读命令；`restart-engine` 未复测 |
| 3852 | 2026-09-27 | Controller 内部版本 5.102.0 | `scripts/acceptance.sh --controller` 和 `--network` 两档只读验收全部通过（握手与能力、`status`、`summary`、`dump performance`、`rule match`、`rule temp list`、`feature list`、`module list`、`watch speed` 首帧、Prometheus metrics、官方校验服务上传合成的无秘密 profile、`dns lookup`），全程没改 Surge 设置；变更类操作（`restart-engine`、切换 profile）未复测，仍按 3830/3822 |

Protocol 25 仍兼容旧的 JSON `argv` 请求，但本客户端已对齐正式版 Surge Mac 6.9.0 build 12250 的文本编码。
<!-- END platform-compatibility -->

<a id="branch-diagnostics"></a>
<!-- BEGIN diagnostics -->
# Surge 按需诊断

只在实际排查对应功能时读取，并先按入口 §2 做完引擎状态预检。命令语法、key-path 和响应字段以 [command-reference.md](command-reference.md#branch-command-reference) 为准，协议门槛和平台限制以 [platform-compatibility.md](command-reference.md#branch-platform-compatibility) 为准。这里只写 Surge 特有的行为，不用其他代理软件的语法代替。

## 流量与多帧输出

- `http probe <url> [policy]` 会发真实的 HEAD 请求；DNS、节点、带宽和加密 benchmark 同样会产生真实流量或负载。只在任务需要时执行，执行前确认目标和影响。
- `diagnostics`、各种 `watch`、带宽和加密 benchmark 持续输出 JSON Lines：按 `hasMore=false` 或结束载荷判断完成，不能拿首帧当最终结果；长期订阅要限时停止。

## 路由与 DNS

```sh
surge-cli --raw rule match example.com
surge-cli --raw rule explain https://example.com
surge-cli --raw dns trace example.com
surge-cli --raw geoip 1.1.1.1
```

`rule match` 快速看命中的规则和最终策略；`rule explain` 给出完整的策略组决策路径，回答「为什么这样走」时优先用它。

需要改变路由才能验证、并且用户授权时，优先用临时规则，不改 Profile。先列出已有的规则，记下本次新增的项：

```sh
surge-cli rule temp list
# 确认 Proxy 存在且获准测试后再添加：
surge-cli rule temp add "DOMAIN-SUFFIX,example.com,Proxy"
surge-cli rule temp list
```

清理按入口 §3，只移除本次新增的规则；具体的标识和 remove 参数先核对 [命令参考](command-reference.md#branch-command-reference) 和实际返回。

## 性能与隧道

```sh
surge-cli --raw dump performance
surge-cli --raw dump rule-usage
surge-cli --raw benchmark rule-matching
surge-cli --raw benchmark encryption 25
```

`dump policy`、`dump performance`、`dump rule-usage` 和各种 benchmark 都按需读取，不作为每次任务的前置或基线。`benchmark encryption` 测的是 Surge 所在设备的本地加密性能，不是网络带宽。

排查 Tailscale/WireGuard 时，用 `proxy-runtime-status` 传策略名读取运行时状态，名称含空格要加引号。`line-hash` 仍然可用，但 `dump policy` 已经不打印它，要从 `policy-group list` 或 `dump policy-group-sub-policies` 的方括号里取：

```sh
surge-cli --raw proxy-runtime-status "<策略名>"
surge-cli --raw proxy-runtime-status POLICY::…
```

优先检查握手、底层策略、Tailscale 会话、Exit Node、DERP 和 peer path，不要先做宽泛的日志搜索。

`test-policy-udp` 需要真实的 Internet 出网：对 P2P 的 Tailscale/WireGuard 策略（`Test Capability: rtt-only`）会返回 not-applicable，这类策略改用 `test-policy` 取 RTT。这个错误**不是**隧道故障的证据。

## CoreDevice/RSD 同机回环（第三方报告，非本机验收）

上游 OpenMinis ios-dev（2026-10-25 本地核对）报告：Surge iOS 5.23.0 可用，5.22.1 会静默丢弃 `[IP Rewrite]`，并以 ≥5.23.0 作为门槛（这里是 App 发行版本，不是 Controller 内部版本）。上游列出的验证环境是 iOS 27.0.1/27.1 和 Surge 5.23.0；流程要求 Wi-Fi、已开启开发者模式和有效的 RemotePairing 配对材料，同机只运行一个相应的 NetworkExtension VPN；49152 是该上游握手实现固定的端口。当前版本、拓扑和前提没核对时不据此执行，也不外推到其他系统、实现或全部服务端口。这是第三方报告的 App 版本条件，不是 `references/command-reference.md`〔分支 platform-compatibility〕 门槛表里的 Controller 协议门槛。

只在这个场景下评估 `[IP Rewrite]` 的目标地址 `reflect`，以及该地址 `/32` 的 `tun-included-routes`；先核对目标地址、现有路由、模块、配对前提和上述版本条件。

- 不自动改路由，不整段覆盖已有路由，也不照搬上游「无副作用」的保证。
- TCP connect 成功不等于协议成功：任意端口都能瞬间连上却没有数据，可能是假通。要分别确认 TCP、Pair-Verify、RSD 会话和获准的只读业务返回。
- 上游要求导入模块后重启 VPN。不为验证而自动导入、启停模块或重启 VPN；需要的动作先列出影响和回滚，按入口和既有授权执行。前提没满足就不能说验证通过。
- 配对凭据或设备访问缺授权时停止这一步，不读凭据文件取密。

来源与许可：OpenMinis/MinisSkills，MIT 精选改写；Copyright (c) 2026 OpenMinis；Copyright (c) 2026 OpenMinis contributors；本地许可决定与边界见本包 references/SOURCE.md〈第三方精选改写〉。完整许可随包见 ../LICENSE.openminis.txt、../LICENSE.openminis-ios-dev.txt；固定提交、取材路径与日期见仓库 skills-sources.md。
<!-- END diagnostics -->


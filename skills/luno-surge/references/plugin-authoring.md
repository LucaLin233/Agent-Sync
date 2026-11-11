# Surge macOS 插件开发（自编）

本指南为非官方、自编接口事实说明，不含官方插件指南全文或逐段译文。仅在用户明确要求 macOS 插件工作时使用；iOS 不支持此插件分支。先完整读 `references/platform-compatibility.md`；在线命令的传输、凭据和秘密边界另读 `references/controller-cli.md`。新版本或未列出的字段须核官方资料，不把本指南当未来版本保证。

## 范围和交付物

当前取证基线中的插件类型是 `ap-controller`：为 Mac 的局域网设备面板提供无线接入信息，必要时触发重连。它不是普通 Profile 脚本，也不是 iOS 模块。在线插件管理最低 Controller Protocol 24；离线 validate/pack 依赖官方 Mac CLI，本端 Python 桥不实现。

开发目录包含 `manifest.json`、单入口 `main.js` 及项目自有的 `icon.png`。icon 必须为 256×256 PNG，不使用 Surge logo。多文件代码在获准的开发环境构建成单个 main.js；运行时没有模块加载、DOM、fetch 或文件访问，不假定其他资源可从脚本读取。

manifest 的核心身份是 `manifest_version=1`、永久 reverse-DNS `id`、`name`、版本文本 `version`（x、x.y 或 x.y.z，每段 0–999）和 `type=ap-controller`。更换 id 表示另一个插件；id 至少有一个点，只用字母、数字和连字符组成各段。可声明 description、author、homepage、min_core_version、min_api_version、supports_validation、event_timeout 和 parameters。名称、描述及参数标签等可本地化；历史官方例子以 JSON string 提供 version，本指南不推荐 JSON number。官方文字给出版本形态而未在此证明校验器对 JSON number 的拒绝行为，若要断言其严格类型，须另核官方 schema/validate；未核则停止该类型结论。min_core_version 形态为 x.y.z，min_api_version 当前默认 1；未知字段历史会忽略，不代替当前 schema 核验。

parameters 每项有唯一 key 和 type，可声明 label、description、required、default、placeholder；数字使用 min/max，enum 使用 values/allow_custom，字符串可加 pattern。类型包括 string、int、double、bool、enum、url、hostname。url 仅接受 HTTP(S)，hostname 接受域名或 IP（含 IPv6），两者在 JS 中均为字符串；default 也须符合 schema，required 默认 false。参数由 Surge 校验后放在 `$plugin.params`；参数以明文存储，UI 可见，因此不能把此机制描述为秘密保管库。测试和日志不得回显凭据。

## 事件和状态

在 main.js 顶层同步用 `$plugin.on(event, handler)` 注册；handler 可以异步，返回对象完成事件，抛异常表示失败。空闲实例可能重建，不能依赖跨事件内存状态。`$plugin.id`、`$plugin.version`、`$plugin.apiVersion`、`$plugin.params` 和 `$environment` 提供运行上下文，后者含 system、core-version、surge-version、surge-build、language。超出事件时限的执行会被终止；异常的 error.message 会向用户呈现，不能夹带秘密。

- `apc.fetchClients` 返回含 clients 数组的对象；每个客户必须有 macAddress（接受常见格式），其余字段可选，可提供 accessPointName、ssid、connectionType、radioTechnology、canReconnect。Surge 按 MAC 合并到设备记录。只对确有能力重连的设备报告 canReconnect；可返回控制器已知的所有客户，由 Surge 匹配，有线客户设为 false。
- `apc.reconnect` 接收含 client 的参数，由插件完成获准的设备重连；这是实际网络变更，不当作只读测试。
- 声明 supports_validation 后实现 `system.validate`；连通性或认证验证返回 ok 与必要错误。错误信息先做秘密面检查，不把服务端原文或参数直接拼入。

持久状态使用 `$persistentStore.read(key)` 和 `write(value,key)`；value 为字符串，写 null 删除键。read 缺键返回 null，write 返回成功与否的布尔值。存储按插件隔离，重启和更新后保留，卸载会删除。console.log 会进入 Surge 日志并带插件标识；可使用 setTimeout/clearTimeout，仍受事件时限。

## 外部请求和限制

通过 `$httpClient` 的 get/post/put/delete/head/options/patch 发请求；回调接收错误字符串或 null、含 status/headers 的响应、字符串响应体（binary-body-mode 时为 Uint8Array）。body 可为字符串或对象，对象按 JSON 发送。请求可带 URL、headers、body、timeout、auto-redirect 和 binary-body-mode；timeout 默认 30 秒、auto-redirect 默认 true、binary-body-mode 默认 false。不要默认关闭证书或主机名校验；官方示例中的 insecure 选项不构成本项目默认。没有选策略的 policy 参数，不假设 Cookie 会跨请求保存。

本指南基于 Mac 6.11.0 包内资料（12680，12710 未变）记录：manifest ≤64 KB，main.js ≤2 MB，ZIP ≤10 MB，解包 ≤30 MB 且 ≤200 文件；事件 1–60 秒、默认 15 秒；HTTP 请求/响应体各 ≤8 MB，最多 20 个并发请求；持久存储共 4 MB，键 ≤128 字符并限字母数字及 `._-`；参数 key ≤64 字符。这些是有版本的事实，不代表本端实测，也不外推到未来版本。

## 开发、验证和分发

先核 schema 与版本，再在获准 Mac 上加载开发目录。开发循环是 load-unpacked 后读 parameters，安全配置参数，验证 plugin list 和设备面板，改代码后重新 load-unpacked。schema 收紧、移除字段或新增必填项可能清掉原配置，更新前说明影响并留恢复信息。配置会触发插件自己的验证代码，仍可能访问外部网络。

敏感参数不得以 `token=…` 之类 argv 方式配置。只有已核实的安全入口能够避免秘密进入 argv、日志和输出时才配置；入口不明确就暂停秘密相关步骤，不能因为官方示例这样写而放宽。

在官方 Mac 环境用 plugin validate 检查目录；用 plugin pack 构建时会产生版本 ZIP 和带 asset URL/sha256 的分发 manifest。产物命名为 <id>-<version>.zip 和 <id>-<version>.manifest.json。构建、上传、发布是三种授权，不自动联动。版本资产 URL 不覆盖旧内容，分发 manifest 使用稳定 HTTPS URL；ZIP 不内嵌 manifest 的格式须与当前官方工具核对。历史基线的 plugin install 尚未开放，使用 load-unpacked 不代表远端安装已可用；新版本需重新取证。

验收分别记录离线格式检查、真实插件参数验证、面板数据及获准的重连结果，不能以构包成功替代设备行为。回滚前核插件身份、参数变化和持久数据；卸载会丢持久存储，须另获删除授权。

来源：Surge 官方应用包的历史接口事实，版本与哈希见 `references/upstream-manifest.json`；取源与许可边界见 `references/SOURCE.md`。本指南独立组织，未加入官方叙述原文摘录。

# Surge 官方资料

按平台和版本取证，只取当前问题需要的页面，优先用 Markdown 端点（`….md` 或 `/llms.txt`）。用户提供了 `llms.txt` 就先读它：它是路由文件，不是文档正文。

## 取证顺序

不知道该查哪一份时，先读官方统一入口 [nssurge.com/llms.txt](https://nssurge.com/llms.txt)，按它分流到下面各项。它只是路由，不含正文，也不必每次先读；根入口改版或失效时直接用下面的子入口，不猜新 URL。

1. **平台发布说明**：iOS 稳定版的变化读 [Surge iOS Release Notes](https://kb.nssurge.com/surge-knowledge-base/zh/release-notes/surge-ios.md)；只在 beta 出现的问题读 [iOS TestFlight 说明](https://kb.nssurge.com/surge-knowledge-base/zh/faq/ios-testflight.md)。
2. **规范语法和行为**以 [Surge Manual](https://manual.nssurge.com/llms.txt) 为准。
3. **Mac 版本**：用户明确问 Mac 时才读 [Mac release/beta appcast](https://nssurge.com/mac/latest/appcast-signed-beta.xml)。它不是 iOS 能力的权威，只在 macOS 分支用，或另有官方来源证明共享内核的变化也适用于 iOS 时用。
4. **用户工作流和排障**读 [Surge Knowledge Base](https://kb.nssurge.com/llms.txt)。
5. **官方 CLI 的变更**另见 [Surge CLI 更新概览](https://nssurge.com/blog/surge-cli-updates/) 和 [Beta 公告频道](https://t.me/SurgeTestFlight)。

同一个 iOS 版本上发布说明和手册冲突时，以发布说明为准并说明差异；只有 Mac 发布说明记录的能力，没有 iOS 或共享内核的证据就不能断言 iOS 支持。版本敏感或容易误读的结论要记下来源 URL；页面失效时从手册首页或侧栏目录重新定位，不猜 URL，也不用搜索引擎摘要代替官方正文。

## 配置手册

从 Manual 入口按本次涉及的 section 或功能定位原文，本包不缓存逐页目录或旧版的变化清单。版本敏感的字段、include 和分节、模块行为，临用时核对对应平台的发布说明和规范正文；在目录里找到不等于读过原文，取不到就标「未核实」，停止依赖它的部分。

## 本地校验

- 装有 Mac 时可以用官方本地解析器：`/Applications/Surge.app/Contents/Applications/surge-cli --check /path/to/profile.conf`。
- Minis/iSH 没有本地解析器：`surge-cli --check <path>` 会把显式指定的文件上传到官方 beta HTTPS 校验服务；上传和脱敏要求见入口 §3 和 [controller-cli.md](command-reference.md#branch-controller-cli)。
- 校验副本不能把真实的密码、PSK、订阅 URL、API Key 或其他凭据复制到不受控的位置，优先用占位值验证结构。

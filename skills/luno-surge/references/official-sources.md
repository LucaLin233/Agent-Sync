# Surge 官方资料

产品事实以官方资料为准，本包只记去哪里查。只取当前问题需要的页面，优先用 Markdown 端点（页面 URL 后缀换成 `.md`，或各站的 `/llms.txt`）。用户给了 `llms.txt` 就先读它：它是路由文件，不是正文。

| 要查的 | 去处 |
|---|---|
| 不确定该查哪一份 | 官方统一入口 <https://nssurge.com/llms.txt>，只做路由 |
| 配置语法和规范行为 | 手册 <https://manual.nssurge.com/llms.txt>，按 section 或功能定位页面 |
| Mac 与 iOS 的差异 | <https://manual.nssurge.com/getting-started/platform-differences.md> |
| 模块（`%APPEND%`、`#!arguments`、占位符） | <https://manual.nssurge.com/profile/module.md> |
| CLI 命令族和起始版本 | <https://manual.nssurge.com/tools/cli.md> |
| HTTP API、Metrics、分节、MCP | <https://manual.nssurge.com/tools/http-api.md> |
| HTTP 抓包自动化 | <https://manual.nssurge.com/tools/http-capture.md> |
| 远程管理、Ponte、USB | <https://kb.nssurge.com/surge-knowledge-base/guidelines/remote-management.md> |
| 工作流和排障 | 知识库 <https://kb.nssurge.com/llms.txt> |
| iOS beta | <https://kb.nssurge.com/surge-knowledge-base/zh/faq/ios-testflight.md> |
| Mac 版本变化 | Mac beta appcast <https://nssurge.com/mac/latest/appcast-signed-beta.xml> |
| 官方 CLI 新命令概览 | <https://nssurge.com/blog/surge-cli-updates/> |

## 判读

- 来源冲突时按官方入口的优先级：发布记录高于手册，手册高于知识库。
- 知识库的 [iOS 更新日志](https://kb.nssurge.com/surge-knowledge-base/zh/release-notes/surge-ios.md) 截至 2026-11-12 只更新到 5.14.6，较新的 iOS 能力看手册里的版本标注（如「iOS 6.0.0+」）。
- Mac appcast 不是 iOS 能力的证据：只在 macOS 问题上用，或另有官方来源证明共享内核的变化也适用于 iOS。
- 在目录里找到不等于读过原文。版本敏感或容易误读的结论记下来源 URL；取不到就标「未核实」，停止依赖它的部分。页面失效时从手册目录重新定位，不猜 URL，不用搜索引擎摘要代替正文。

## 本地校验

- 用户指定的 Mac 上可以用官方本地解析器：`/Applications/Surge.app/Contents/Applications/surge-cli --check /path/to/profile.conf`。
- Minis/iSH 没有本地解析器：`surge-cli --check <path>` 会把文件上传到官方校验服务，限制见入口 §3 和 [controller-cli](command-reference.md#branch-controller-cli)。
- 校验副本只放占位值，不把真实的密码、PSK、订阅 URL、API Key 或其他凭据复制到不受控的位置。

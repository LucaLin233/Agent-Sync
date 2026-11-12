# GitHub 操作

- **凭证**：默认用 `$GH_TOKEN`（细粒度、按仓库收窄）。只有它覆盖不到时（写第三方公开仓库、调用经典令牌独占的端点），才按次显式注入 `$GH_TOKEN_CLASSIC`（账号级、无法收窄），**不得自动回退**。撤销或轮换前，先核查所有引用（Minis 变量、设备侧 env、平台和 CI secrets），确认没有消费者后再执行。
- **分工**：仓库内容变更走本地 `git`；`gh` 按当前 `--help` 操作远端对象、认证辅助和状态回读，但「只操作远端对象」不是绝对边界。合并、关闭、删除、分支保护和触发流水线，须用户明确要求。
- **私有 Git 管道窄例外**：只有同时满足以下条件时，才按下述单次 `GH_TOKEN` → `gh auth git-credential` 管道向获准的 GitHub 远端提供凭据：用户已授权，本次 `GH_TOKEN` 获准且非空，HTTPS origin 限定为获准的 `github.com` 仓库，`gh` 可信。这个管道不读取既有的 credential helper。命令里先清空 helper 和目标仓库生效的 `extraHeader`，关闭交互和 askpass，再设置 `gh auth git-credential` 作为 helper；同一条命令里把 `GH_CONFIG_DIR` 指向自建的空临时目录，并立即清理。空目录隔离不了系统 keyring：无法确认 keyring 或已保存的登录态不会被读取时就停止，禁止回退到配置或 keyring。禁止 `gh auth login`、`gh auth setup-git`、修改全局配置和调试输出；令牌不得进入 argv。缺变量、隔离目录、目标范围，或任何一项条件无法核实时，都停止。
- **结果确认**：私有 Git 的结果以 `gh api` 回读为准；推送成功不等于远端可见（raw CDN 曾观察到 2–7 分钟缓存，这是历史记录，不是当前时效的保证）。
- **CI 状态**：按当前 `gh pr checks`、`gh run view`、`gh run watch` 的 `--help` 只取最小字段和失败日志；watch 外层要设时限，pending 的退出码 8 不算失败也不算通过。读取日志仍按秘密投影；读状态不授权 rerun、合并或部署。查询结果为 0 条只表示没有检查记录，不等于 CI 通过；GitHub Actions、Commit Status 和 Check Runs 不能互相冒充。

来源与许可：openclaw/openclaw，MIT 精选改写；Copyright (c) 2026 OpenClaw Foundation。完整许可随包见 ../LICENSE.openclaw.txt；固定提交、取材路径与日期见仓库 skills-sources.md。

<!-- 来源：openclaw/openclaw@e4129b6375e3179be5d9ed0a56a35f2871f4e73b（2026-09-12）；许可：该提交根 `LICENSE` 为 MIT（2026-11-06 按该提交逐字节取回，全文见 `luno-ops/LICENSE.openclaw.txt`）；精选改写（压入凭据与远端对象流程条款，上游命令示例未搬运；上游 GitHub 版与市场版另有较大差异）；上游可取（2026-10-11 实测可访问）；登记见 skills-sources.md -->
先取得本包入口必需规则。

## GitHub 操作
- 凭证默认 `$GH_TOKEN`（细粒度、按仓库收窄）；仅当它不覆盖时（写第三方公开仓库、调用经典独占端点）按次显式注入 `$GH_TOKEN_CLASSIC`（账号级、不可收窄），**不得自动回退**。撤销或轮换前先核查引用（Minis 变量、设备侧 env、平台与 CI secrets），确认无消费者再执行。
- 仓库内容变更走本地 `git`；`gh` 按当前 `--help` 操作远端对象、认证辅助与状态回读，不把“只操作远端对象”当作绝对边界。合并、关闭、删除、分支保护与触发流水线须用户明确要求。
- **GitHub 私有 Git 管道窄例外**：仅在用户已授权且当次 `GH_TOKEN` 获准且非空、HTTPS origin 限定为获准的 `github.com` 仓库、`gh` 可信时，按下述单次 `GH_TOKEN`→`gh auth git-credential` 管道向获准 GitHub 远端提供凭据；这不读取既有 credential helper。命令先清空 helper 及目标仓库生效的 `extraHeader`，关闭交互／askpass，再设 `gh auth git-credential` helper；单命令将 `GH_CONFIG_DIR` 指向自建空临时目录并即时清理；该空目录不隔离系统 keyring，无法确认 keyring／保存态不会被读取即停止，禁止回退配置/keyring；禁 `gh auth login`、`gh auth setup-git`、全局配置与调试输出；令牌不得进入 argv。缺变量、隔离目录、目标范围或任一上述条件无法核实时停止。
- 私有Git结果以 `gh api` 回读为准（raw CDN缓存2–7分钟为历史记录，非当前时效保证）；推送成功不等于远端可见。
- CI 状态按当前 `gh pr checks`、`gh run view`、`gh run watch` 的 `--help` 取最小字段与失败日志；watch 外层设有界时限，pending 的退出码 8 不当作失败或通过，读取日志仍按秘密投影，状态读取不授权 rerun、合并或部署。

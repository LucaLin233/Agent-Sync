---
name: luno-surge
description: Surge配置、模块、规则、脚本与日志诊断；CLI/External Controller状态检查和控制。默认iOS。
---

# Surge（iOS 优先）

本项目非 Surge 官方技能。Surge 名称及官方资料归 Surge Networks；本技能采用自编工作流和接口事实说明，来源、有限摘录及第三方许可边界见 `references/SOURCE.md`。

默认按 iOS 处理；只有用户明确提到 Mac、给出 Mac 专属证据或需要跨平台时，才进入 macOS 或共享配置。iOS 上不套用 Mac 的文件系统和 Gateway、System Proxy、Enhanced Mode；共享 profile 用 `#!IOS-ONLY`、`#!MACOS-ONLY`、`#!TVOS-ONLY` 隔离平台差异。

## 1. 路由

先读用户给的材料，保留原有的顺序、注释、策略名和资源 URL。配置问题按 §4，运行状态按 §5；两者相关时按「只读检查 → 最小修改 → 立即复验」推进。结论对版本、平台或语义敏感时，按 `references/official-sources.md` 查官方资料；不套用其他客户端的语法，不猜字段和能力。

实际执行 Surge 命令（CLI、HTTP API 或脚本）之前，完整读 `references/platform-compatibility.md`：协议门槛、平台限制和历史验证只以它为准，未知或不满足的不执行；本文件和官方原文里出现的协议号都不作门槛。遇到异常先跑 `surge-cli --raw version`；报 Unknown 或 Unsupported command 时再查 `help <command>`，不要把 Mac 专属能力当成 iOS 能力。

## 2. 引擎状态预检

任务依赖 Surge 的联网、代理、DNS、脚本或 API 时，先查当前实例的 `surge-cli --raw status` 和 `--raw environment`，遇到 EOF 或超时后重查；切换策略、模块或功能之前，先确认目标存在。纯文档工作不连接实例。

Controller 或 API 能响应，不等于引擎在正常处理流量：要核对 Suspend 和 VPN/引擎状态，不假定暂停字段的名字；证据不够就标「未确认」，请用户看界面。EOF 或超时也不能证明是暂停、节点、凭据或目标的故障；不要自行恢复、重启、换模式或换实例。获准后重读状态再试，仍失败再依次查路由、DNS、节点和目标；不默认全量读取 `dump policy`、日志或 Profile。

## 3. 安全与平台边界

- 不编造节点、策略名、证书、凭据、订阅 URL 或 Controller 的返回。
- **凭据**：Controller 密码或 HTTP API Key 只从 `SURGE_API_KEY` 或 `--password-stdin` 取，不进 argv、文件、日志或回复。客户端非交互，不读凭据文件，不在 TTY 补问；缺失时给出[设置入口](minis://settings/environments?create_key=SURGE_API_KEY&create_value=)，不要让用户在聊天里发密码。
- **隐私数据**：`dump profile`、请求正文和日志可能含节点、订阅 URL 和隐私，只在必要时最小读取、脱敏引用，不放进支持包。启用 MITM、Rewrite、脚本、抓包或远程控制之前，先说明影响；hostname 不默认写 `*`。
- **高影响操作再确认**：`stop`、`restart-engine`、切换或更新 profile、批量终止连接（开关 HTTP capture 也算：`feature set capture` 和 `set Replica=…` 都会断开全部现有连接）、改变模式或策略之前，**即使整批已获批准，也要再单独确认一次**（比 `luno-core` 更严）；`stop` 只在用户明确要求时执行。`reload` 通常差量应用，但必要时会自动转完整重启，不能保证保留连接、缓存和临时规则。直接或间接触发 reload 前，应核对本次变更与实例版本；无法排除完整重启时，即使整批已获批准，也必须就这些影响再次单独确认，未获准即不执行。`restart-engine` 总是完整重启，亦须再次单独确认；不能仅凭命令名或历史成功判为无损。
- **临时规则**立即生效、优先于 Profile，引擎停止后失效。`rule temp flush` 会清空全部临时规则，**禁止当作本次的默认清理**；只删本次新增的项，不猜索引。清理和处理多帧输出之前，完整读 `references/diagnostics.md`。
- **真实流量**：`http probe` 会发真实的 HEAD 请求，DNS、节点、带宽和加密 benchmark 也会产生真实流量或负载，都按需执行。`watch`、`diagnostics` 和 benchmark 输出 JSON Lines，要限流读到 `hasMore=false`；长期订阅由外部限时停止，首帧不是终态。
- **`--check` 会上传**：它把文件发到官方服务校验，不是本地解析；禁止自动上传活动 Profile，先告知用户，必要时只校验脱敏副本。
- **`policy-descriptor`** 可能含密码或 PSK，和认证凭据是两回事：只经 stdin（`--descriptor-file -`）输入，不落盘、不写进配置、不读凭据文件；`SURGE_API_KEY` 只用于认证。

## 4. 配置

逐项核对：section 和行语法、选项、最低版本和平台、策略和策略组成员、hostname 引用（MITM、Rewrite、Script）、远程资源格式、规则顺序和 `FINAL`、DNS 循环和绕过、模块的 `%APPEND%`/`%INSERT%`、脚本的 `$done()` 路径，以及有没有无关的数据收集。

改动要最小并保持原有的路由意图，交付完整文件或精确定位的 patch。模块保持单一目的、可逆，说明它是覆盖、插入还是追加，以及前提条件；参数名带 `<面板名>_` 前缀，`#!arguments` 用逗号分隔、默认值里不能有逗号（多值用 `|`），占位符写 `{{{name}}}`。没有 Controller 时的验证流程：导入或应用 → 查 parser warning → 复现 → 在请求查看器核对命中的规则和策略；交付时附验证和回滚方法。

分节编辑之前，完整读 `references/http-api.md` 的〈安全分节写入〉，并按 `references/platform-compatibility.md` 核对平台、版本和协议；官方支持分节编辑不代表本端已经实现。整节替换会触发校验和 reload，要按 §3 再单独确认；先合成验证不等于授权修改活动配置。

## 5. CLI

`/usr/local/bin/surge-cli` 是 `scripts/surge_cli.py` 这个自建的 Python 3 桥，**不是官方 Mac 二进制**。默认连同机的 Controller；`SURGE_CLI_REMOTE` 或 `--remote` 只在显式指定时使用，用户没指定就不连外部主机。涉及传输、凭据或 `--check` 时，先完整读 `references/controller-cli.md`。

优先用 `--raw`，它输出的是**客户端脱敏后的 JSON，不是服务端原文**（包内其他地方说的「原始」都按这个理解）。

查命令选择、语法或 key-path 时，先完整读自编的 `references/command-reference.md`，再按任务读取其中触发的专业资源。本文和自编参考未覆盖的参数、字段或版本语义，须通过已核实的当前帮助或官方资料确认；无法取得依据就停止该项，不猜命令，也不要求安装官方 Skill 原件。取得帮助仍须遵守平台、实例连接及当次授权。

涉及路由、DNS、临时规则、性能或 Tailscale/WireGuard 之前，完整读 `references/diagnostics.md`。调试路由优先用临时规则，不改 Profile；变更前后只读最窄的相关状态。写 macOS 插件配置前，先读 parameters schema 和 `references/plugin-authoring.md`。

## 6. HTTP API 回退

Controller 不可用，或需要 `/v1/*` 端点、Prometheus 指标时，先完整读 `references/http-api.md`（含远程明文的风险），再用 `scripts/surge_ios.py`。核对端点和认证（`X-Key`）；默认连同机，`SURGE_HTTP_API_BASE` 指向活动实例或可信局域网时，都要用户指定。危险操作按 §3 再确认。测试还没写进 Profile 的节点用 `scripts/test_policy_descriptor.py`，它不改配置，凭据按 §3 处理。

## 7. 交付

安装和验收、取源和追新、打包和投递、模块推送之前，完整读 `references/SOURCE.md` 的共同前置和对应分支。仓库提供自编的运行资料和桥接脚本，不要求补入官方 Skill 原件；官方应用包只作为维护取证来源，不作为普通使用或部署的必需附件。自编正文须人工维护，不整体覆盖成本地或远程官方原件。打包只用现有的专用打包器；包中不得有完整官方文件、官方 logo、凭据、profile、抓包、请求正文、数据库或运行输出。SOURCE 中的授权、漂移即停、失败恢复和发布边界均须保留。

交付时给出结论、实际做了的修改或操作、验证结果和回滚注意事项；分清建议和实操、规则推演和端到端成功、版本快照和当前实测。

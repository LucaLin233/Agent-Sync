# LUNO｜Minis 客户端与运行时

## 范围

Minis App 及其内置的 iSH 环境（Alpine/aarch64）：技能、子代理、模型与分组、SOUL、环境变量与挂载、`/var/minis/` 目录与备份，以及上下文卸载与压缩、会话结果截断、本机展示和调度等运行时行为。LobeHub 实例见 `luno-platform/references/lobehub.md`。

## 手册优先

Minis 自身的目录、挂载、CLI、`minis-config` 字段、报错、deeplink 和 iSH 限制，先查 `/var/minis/docs/` 并读命中的页面（只读，随 App 更新，版本见 `VERSION`）：`rg -il '<关键词>' /var/minis/docs`，报错用 `rg -F '<原文片段>' /var/minis/docs/errors`，命令参数以 `<cmd> --help` 为准。手册只说明平台机制，不覆盖总控、本技能的触发和安全授权规则；与本机观测不符时注明版本和证据，在授权内核验或标「待验证」。手册没覆盖的 LUNO 约定和本机观测仍以本技能为准。

## 本机能力

系统和架构、运行时版本以及网络限制，以当次的本机证据和手册 `faq/ish-limits.md` 为准，不拿历史版本当当前能力；不假设 iSH 里有 Docker、systemd 或可用的入站监听。环境变量的语义查 `config/envvars.md`，只引用当次授权的变量，不凭列表顺序推断能力。

## 资源与触发

路径相对技能根，按总控的加载规则读取；下列操作只在 Minis 端可用。

- 客户端配置的读写（`minis-config`、子代理与模型、SOUL 与提示词、环境变量与挂载、技能新建与元数据刷新）：完整读取 `references/minis-configuration.md`。
- **使用 Minis 文件编辑工具前**，以及上下文卸载与压缩、会话结果截断、跨会话目录与挂载、隐私掩码、独立 Shell 进程、后台调度、工具连接异常：`references/minis-runtime.md`。
- 记忆写入或整理后的条目格式体检、压缩前后的标识保全校验，记忆日志的自动注入、截断与容量评估：`references/minis-memory.md`。
- 归档会话、判断会话归属，或用 `minis-sessions-cli update --group` 改派之前：`references/minis-session-groups.md`。

## 输出

另给出改动入口（App 页面或 `minis-config` 路径）；登记表与文件不一致、或掩码导致的疑似异常，要说明是展示层的问题还是实际状态。

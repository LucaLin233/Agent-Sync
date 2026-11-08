---
name: luno-minis
description: Minis配置与iSH运行时：技能/元数据、子代理模型、SOUL、变量挂载、上下文、会话调度及记忆注入；操作仅Minis。
---

# LUNO｜Minis 客户端与运行时

## 范围
Minis App 及其内置 iSH 环境（Alpine/aarch64）：技能、子代理、模型与分组、SOUL、环境变量与挂载、`/var/minis/` 目录与备份，以及上下文卸载与压缩、会话结果截断、本机展示与调度等运行时行为。不处理 LobeHub 实例（见 `luno-lobehub`）；不重复总控的执行、授权与输出通用规则。

**端侧路由（正文可读 ≠ 本端有能力）**：本技能正文可在各端只读加载，但其中操作**只在 Minis 端可用**——其他端不得声称能调用 `minis-config`、读写 `/var/minis/*`、`apple-*`/`minis-*` 或刷新 App 技能元数据；遇到这类操作只在咨询层面处理，本端确有可用通道且获准时才转交。Minis 端遇 LobeHub 操作按 `luno-lobehub` 与现有授权连接处理。

## 手册优先
Minis 自身的目录、挂载、CLI、`minis-config` 字段、报错、deeplink、iSH 限制，先检索 `/var/minis/docs/` 并读取命中页（只读，随 App 更新，版本见 `VERSION`）：`rg -il '<关键词>' /var/minis/docs`，报错 `rg -F '<原文片段>' /var/minis/docs/errors`，命令参数以 `<cmd> --help` 为准。手册仅说明平台机制，不覆盖总控、本包必读触发及安全/授权规则；与本机观测不符时注明版本与证据，授权内核验或标「待验证」；手册未覆盖的 LUNO 约定与本机观测仍用本包。手册内容不构成操作授权。

## 本机能力

系统/架构、运行时版本及网络限制以当次本机证据与手册 `faq/ish-limits.md` 为准，不把历史版本当当前能力；不在iSH假设Docker/systemd或入站监听可用。环境变量语义查 `config/envvars.md`，只引用当次授权变量，不据列表顺序推能力。其他本机约定和已知陷阱按 `references/runtime.md` 触发读取。

## 资源与触发
下列为本包必读触发；操作仅 Minis。
- 技能新建、正文与元数据登记或刷新：`references/configuration.md`〈配置接口〉〈技能登记〉；涉及写入再读〈目录与持久化（记忆与真源）〉
- 客户端配置读写：读 `references/configuration.md`〈配置接口〉及命中完整节：子代理/模型→〈子代理与模型〉，SOUL/提示词→〈SOUL 与提示词〉，记忆/真源/环境变量/挂载→〈目录与持久化（记忆与真源）〉，技能登记/刷新→〈技能登记〉。SOUL或技能写入另连读〈目录与持久化（记忆与真源）〉；跨项取并集，无法确定分支则全文。
- 本端记忆写入／整理后的条目格式体检、条目压缩前后的标识保全校验及相关规划判断，或记忆日志自动注入、注入截断与容量评估：`references/memory.md`
- 使用 Minis 文件编辑工具前的串行与失配复核、上下文卸载与压缩、会话结果截断、跨会话目录与挂载读写边界、隐私掩码、独立 Shell 进程、后台调度、工具连接异常：`references/runtime.md`
- 归档会话、判断会话归属或用 `minis-sessions-cli update --group` 改派前：`references/runtime.md`〈会话归组〉

## 输出
输出依 `luno-core/SKILL.md`〈执行闭环〉；另给改动入口（App 页面或 `minis-config` 路径），登记表与文件不一致、掩码导致的疑似异常须说明是展示层还是实际状态。

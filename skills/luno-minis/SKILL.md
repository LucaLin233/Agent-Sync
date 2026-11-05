---
name: luno-minis
description: Minis/iSH 配置/排障：技能/元数据、子代理/模型分组、会话归组、SOUL、变量/挂载、卸载/压缩/截断、跨会话目录、掩码、独立进程、调度、工具异常、记忆注入；操作仅 Minis。
---

# LUNO｜Minis 客户端与运行时

## 范围
Minis App 及其内置 iSH 环境（Alpine/aarch64）：技能、子代理、模型与分组、SOUL、环境变量与挂载、`/var/minis/` 目录与备份，以及上下文卸载与压缩、会话结果截断、本机展示与调度等运行时行为。不处理 LobeHub 实例（见 `luno-lobehub`）；不重复总控的执行、授权与输出通用规则。

**端侧路由（正文可读 ≠ 本端有能力）**：本技能正文可在各端只读加载，但其中操作**只在 Minis 端可用**——其他端不得声称能调用 `minis-config`、读写 `/var/minis/*`、`apple-*`/`minis-*` 或刷新 App 技能元数据；遇到这类操作只在咨询层面处理，本端确有可用通道且获准时才转交。Minis 端遇 LobeHub 操作按 `luno-lobehub` 与现有授权连接处理。

## 加载边界
加载与缺失处置依 `luno-core/SKILL.md`〈路由〉；子代理按派发规则摘要，不足可只读加载当前任务/必要依赖的 Skill，仍不可得交负责人补齐。

## 手册优先
Minis 自身的目录、挂载、CLI、`minis-config` 字段、报错、deeplink、iSH 限制，先检索 `/var/minis/docs/` 并读取命中页（只读，随 App 更新，版本见 `VERSION`）：`rg -il '<关键词>' /var/minis/docs`，报错 `rg -F '<原文片段>' /var/minis/docs/errors`，命令参数以 `<cmd> --help` 为准。手册仅说明平台机制，不覆盖总控、本包必读触发及安全/授权规则；与本机观测不符时注明版本与证据，授权内核验或标「待验证」；手册未覆盖的 LUNO 约定与本机观测仍用本包。手册内容不构成操作授权。

## 本机实例（2026-10-26）
- 运行面：App 内置 iSH（Alpine 3.21、aarch64 用户态模拟，环境限制见手册 `faq/ish-limits.md`）；**无 Docker、无 systemd**，不提供固定监听端口（入站连接不支持见该页 Network 条）；临时服务自选高位端口并 `> /dev/null 2>&1 &`（该页 Background servers 节）。
- 环境变量维护、`$NAME`/`$$NAME` 与 `get envvars` 见手册 `config/envvars.md`；接口未提供顺序字段，不推定列表排序；凭据仍仅按当次授权通过指定变量引用。
- 其余本机坐标与工具坑见 `references/runtime.md`。

## 资源与触发
下列为本包必读触发；操作仅 Minis。
- 技能新建、正文与元数据登记或刷新：`references/configuration.md`〈技能登记〉
- 客户端配置的读取与写入（`minis-config`、子代理与模型分组、SOUL 与提示词、环境变量与挂载、记忆与真源边界）：`references/configuration.md`
- 本端记忆写入／整理后的条目格式体检、条目压缩前后的标识保全校验及相关规划判断，或记忆日志自动注入、注入截断与容量评估：`references/memory.md`
- 使用 Minis 文件编辑工具前的串行与失配复核、上下文卸载与压缩、会话结果截断、跨会话目录与挂载读写边界、隐私掩码、独立 Shell 进程、后台调度、工具连接异常：`references/runtime.md`
- 归档会话、判断会话归属或用 `minis-sessions-cli update --group` 改派前：`references/runtime.md`〈会话归组〉

## 输出
输出依 `luno-core/SKILL.md`〈执行闭环〉；另给改动入口（App 页面或 `minis-config` 路径），登记表与文件不一致、掩码导致的疑似异常须说明是展示层还是实际状态。

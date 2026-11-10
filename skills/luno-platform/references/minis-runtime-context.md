# Minis 上下文、目录与挂载

先完整读 `references/minis-runtime.md`，本资源只在 Minis 端操作；遵守其中的编辑、隐私掩码和工具异常共同规则。

## 上下文行为

- 上下文卸载、压缩和占位符以当前手册 `concepts/minis-url-scheme.md`〈Offloads〉和本次的实际提示为准；不沿用旧的 32K/64K/128K 阈值、压缩轮数或 token 估算倍率。当前行为未知就标「待验证」，不凭字符数估算余量；开启诊断日志仍需配置修改授权。
- offloads 只读工具给出的确切路径，不猜文件名。因编码或二进制拒读不代表文件不存在；只对获准且确认不含秘密的文本，在确认编码后用管道转成 UTF-8 读取。
- 回读会话的参数和字段上限见手册 `cli/minis-sessions-cli.md`（含 `--full`、`--tools`；`messages --tools --full` 读取已存储的 shell 输入，不保证恢复完整元数据）。`messages --id` 必须用完整 UUID：2026-10-25 本机用 8 位前缀时返回成功但消息为空，不能据此判断没有消息。长结果要当轮按授权归档，没有授权就报告缺口；检索或回读父会话和其他会话须当次授权，默认不提供父会话转录。
- 规则文本本身不会报告余量，所以只在事件和阶段边界触发交接，不做「快满了」的预警。
- 涉及记忆日志的自动注入、截断或容量，或据此评估日志的压缩、折行和整理时，先读 `references/minis-memory.md`。

## 目录与挂载

目录分工、会话隔离和挂载读写按手册 `concepts/directories.md`、`faq/shared-vs-workspace.md`、`concepts/mounts.md`。跨会话、跨话题的交接写进 `shared/`（按项目分目录，不放临时文件，备份附校验清单）；`mounts/` 写入被拒就如实报错，不改写到别处；找用户文件先看 `mounts/`，不全盘扫描。

来源与许可：OpenMinis/MinisSkills，MIT 精选改写；Copyright (c) 2026 OpenMinis；2026-10-25 本地决定按 MIT 处理，README 的 Apache-2.0 标注冲突保留，不作法律适用结论或扩大分发授权。完整许可随包见 ../LICENSE.openminis.txt；固定提交、取材路径与日期见仓库 skills-sources.md。

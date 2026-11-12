# Agent-Sync

LUNO 提示词、技能与子代理的版本化资产。Minis/LobeHub 是运行端，仓库是管理落点；合并不等于部署，`present` 不等于已回读。记忆各端自持。

## 入口与许可

- `AGENTS.md`：仓库工作入口；`prompt/`、`skills/`、`subagents/`：受管资产。
- `tools/sync-targets.json`：对象身份、资源与落点的唯一登记；`PENDING.md`：活动未决项。
- 根 `LICENSE`（MIT，Copyright (c) 2026 LucaLin233）仅覆盖自有内容；第三方版权、固定版本、取材边界见 `skills-sources.md`，完整许可随技能包分发，不以根许可替代。Surge 官方原件和 logo 不分发，其边界见 `skills/luno-surge/references/SOURCE.md`。
- 内置技能不是同步对象；模型分组、记忆、设备与环境配置不在备份范围。

## 授权、同步与恢复

操作前完整读取当前生效的 `luno-core/references/sync.md`〔分支 sync、sync-workflow〕及命中资源；候选不覆盖现役授权。分级、独立审查、串行合并部署、真实前态备份、失败恢复与逐端字节回读均按该流程；工具存在不授予执行权。

**部署工具「未变分支」rc=2 的恢复**：这个分支不自动修复，也没有 `--force`。如果确认差异**只是恰好少了一个尾部 LF**：先由主助理核对目标实例、登记 ID、候选 ZIP 和修复授权，再从候选 ZIP 的 `SKILL.md` 按 `body_contract` 提取完整正文，用受支持的 `lh skill edit <id> -c <正文>` 原样提交，然后重新核验全部字段和资源。不要用会吞掉尾部换行的 shell 写法（`$(...)` 命令替换、`echo` 等）传递正文。其他漂移（描述、正文的其他差异、资源路径集或字节、同 key 的身份）先诊断，不盲目重投，也不改包来绕过只读分支。

## 秘密与公开边界

不得提交 token、私钥、密码、`.env`、数据库或 Redis 导出、备份归档、一般连接配置和主机清单。非秘密受管身份、字段路径和专用巡检常量仅限现役窄例外，不新增连接权；秘密泄漏只报位置和类型，按授权处置与轮换，不复制秘密。仓库和共享档案不是凭据来源；第三方或混合素材的公开与再分发须另核许可及授权。

## 测试与历史

用法、选路及白名单环境见 `tests/run-tests.sh` 头部与实现；准入和成本见 `skills/luno-core/references/test-authoring.md`。结构守卫退出码见 `tools/check-rules.py` 头部；测试将任何非零记为失败，`sync-all.sh` 只阻断 rc=1/3。结构通过不代替行为审查。

批次结果只记当批 PR，历史以 git 为准；公开快照未导入旧私有 `LucaLin233/Agent` 历史。合并及共读资源迁移见提交 `484de55052413ef2004d5e588d5a0540bcf88826` 及后续历史，加载读法以 `luno-core` 为准。

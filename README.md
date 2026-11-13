# Agent-Sync

LUNO 提示词、技能与子代理的版本化资产。Minis/LobeHub 是运行端，仓库是管理落点；合并不等于部署，`present` 不等于已回读。记忆各端自持。

## 入口与许可

- `AGENTS.md`：仓库工作入口；`prompt/`、`skills/`、`subagents/`：受管资产。
- `tools/sync-targets.json`：对象身份、资源与落点的唯一登记；`PENDING.md`：活动未决项。
- 根 `LICENSE`（MIT，Copyright (c) 2026 LucaLin233）仅覆盖自有内容；第三方版权、固定版本、取材边界见 `skills-sources.md`，完整许可随技能包分发，不以根许可替代。Surge 官方原件和 logo 不分发，其边界见 `skills/luno-surge/references/SOURCE.md`。
- 内置技能不是同步对象；模型分组、记忆、设备与环境配置不在备份范围。

## 授权、同步与恢复

操作前完整读取当前生效的 `luno-core/references/sync.md`〔分支 sync、sync-workflow〕及命中资源；候选不覆盖现役授权。分级、独立审查、串行合并部署、仓库历史前态核对与恢复、失败恢复与逐端字节回读均按该流程；工具存在不授予执行权。

LobeHub 技能按同步流程使用 `lh skill install` 从已合并的 GitHub `tree/main/skills/<name>` 按需重装；main 可变，不支持用 SHA 固定，安装前后核提交。平时原位重装，有资源退役才按仓库历史明确版本可恢复后删除重装；删除后 ID 会变，须补回安装丢失的正文末尾 LF，并逐字段、逐资源回读。旧 R2 包暂留作恢复材料，不再使用仓库自研部署链；恢复不能承诺保住旧 ID。

官方 CCHP 技能原样 vendored 在 `skills/luno-platform/references/cchp-upstream/`（入口文件为 ENTRY.md）（含 MIT 全文），两端从同一审定仓库版本安装；`luno-platform/references/cchp.md` 仅保留本端边界、组织约定和实例经验。来源与采用版本见 `skills-sources.md`。新增技能的运行端登记在首次安装回读后补齐，候选不表示已经安装。

## 秘密与公开边界

不得提交 token、私钥、密码、`.env`、数据库或 Redis 导出、备份归档、一般连接配置和主机清单。非秘密受管身份、字段路径和专用巡检常量仅限现役窄例外，不新增连接权；秘密泄漏只报位置和类型，按授权处置与轮换，不复制秘密。仓库和共享档案不是凭据来源；第三方或混合素材的公开与再分发须另核许可及授权。

## 测试与历史

用法、选路及白名单环境见 `tests/run-tests.sh` 头部与实现；准入和成本见 `skills/luno-core/references/test-authoring.md`。结构守卫退出码见 `tools/check-rules.py` 头部；测试将任何非零记为失败，`sync-all.sh` 只阻断 rc=1/3。结构通过不代替行为审查。

批次结果只记当批 PR，历史以 git 为准；公开快照未导入旧私有 `LucaLin233/Agent` 历史。合并及共读资源迁移见提交 `484de55052413ef2004d5e588d5a0540bcf88826` 及后续历史，加载读法以 `luno-core` 为准。

记忆规则并入 luno-platform：memory-common、minis-memory 分别负责跨端共同义务及 Minis 专属机制；LobeHub 平台记忆仍在既有 references/lobehub-knowledge.md 的 lobehub-memory 分支，知识库任务只读 knowledge 分支；各端记忆数据自持，不作跨端同步。独立 cchp、luno-memory 的退役须按登记、仓库历史前态恢复口径和逐端回读完成，不以仓库目录移除冒充已部署。

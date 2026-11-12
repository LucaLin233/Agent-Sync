# Agent-Sync

本公开仓库保存 LUNO 提示词、技能与子代理的版本化资产，并管理 Minis/LobeHub 同步。Minis、LobeHub 是运行端，仓库是管理落点；合并不等于部署成功，present 不等于已部署或回读通过。记忆各端自持，不同步。

## 目录

- `AGENTS.md`：在仓库里工作的入口。先加载当前生效的规则，不拿候选覆盖它们。
- `prompt/LUNO.md`：提示词正文；`prompt/SOUL-frontmatter.yaml`：Minis 文件的元信息。两者都不是 `soul.body` 这个生效字段本身。
- `skills/`：技能正文、包内资源、脚本、上游快照和许可；`skills-sources.md` 登记来源、固定版本、许可和必要的恢复线索。
- `subagents/`：LENS、FORGE 的两端同文，以及 Minis 专用的通用执行兜底。第三份不是 FORGE 的副本，LobeHub 没有这个对象。
- `tools/sync-targets.json`：受管对象、资源和各端的身份与落点登记，是对象身份的唯一真源。
- `tools/`：部署、正文判等、资源回读、打包、结构守卫和署名检查工具；`tests/`：这些工具和规则守卫的回归测试及调度器。工具的触发和授权以现役流程为准，放在仓库里不构成执行授权。
- [`PENDING.md`](PENDING.md)：当前未完成的事项。`changelog/` 只保留既有的历史记录；新的批次结果只写在当批的 PR 里。更早的历史在旧私有仓库 `LucaLin233/Agent` 的 Git 历史里（本仓库未导入旧私库历史，公开快照建立后的提交历史正常保留）。

Minis 内置技能（如 `skill-creator`）不是同步对象；模型分组参数、记忆、设备和环境配置不在备份范围内。

## 许可

根 `LICENSE` 是 MIT（`Copyright (c) 2026 LucaLin233`），**只覆盖本仓库自有的内容**。第三方吸收件、上游快照和随包附件按各自的上游许可分发、版权归各上游作者：`skills/<技能>/LICENSE.*.txt` 是对应上游许可的全文，来源仓库和固定提交、所取路径和许可状态登记在 `skills-sources.md`；`luno-surge` 的运行资料由自编工作流和依据官方资料整理的接口事实摘要组成（不是译本，无原文摘录），官方原件和 logo 不随 Git 或运行包分发；历史来源、有限摘录和第三方许可边界见其包内的 `references/SOURCE.md`。再分发前按登记逐项核对，根许可不能代替第三方授权。

## 授权与同步

操作规则对象或仓库之前，完整读取**当前生效**的 `luno-core/references/sync.md`〔分支 sync〕 和 `luno-core/references/sync.md`〔分支 sync-workflow〕，再按入口加载命中的资源；权限和审批以用户当次的授权和现役规则为准。正文改动按 sync-workflow 的风险分级审查和验收；每个会话用独立 clone 和唯一任务分支，通过原生 PR，由收口者串行合并并同步变化的对象。部署写入前先回读目标，不做自动的三副本互校或全量同名发现。

Checks 只在当次授权时临时使用 `GH_TOKEN_CLASSIC`：不改变默认的 `$GH_TOKEN`，不把经典令牌用于普通仓库操作，不自动回退；临时覆盖只限进程变量，秘密不回显、不写文件。查询结果为 0 条只表示没有检查记录，不等于 CI 通过；GitHub Actions、Commit Status 和 Check Runs 不能互相冒充。

## 恢复

恢复前先确认需要的对象、版本和目标端实际的生效状态：从经过核实的仓库版本或备份取对应文件，覆写前保存目标真实的前态和将要变更的资源与元数据，确认可读和权限；用对应端受支持的入口写入，再逐端回读。正文和资源按现役的字节契约比较，name、description 等变化的字段另外核对；`soul.body` 和带 frontmatter 的磁盘文件分别核对；LENS/FORGE 和 Minis 兜底各按它们的登记字段恢复。文件存在、HTTP 成功或 PR 已合并都不能代替回读；失败时只停相关对象，保留前态和恢复入口，没有回读就不算完成。

**部署工具「未变分支」rc=2 的恢复**：这个分支不自动修复，也没有 `--force`。如果确认差异**只是恰好少了一个尾部 LF**：先由主助理核对目标实例、登记 ID、候选 ZIP 和修复授权，再从候选 ZIP 的 `SKILL.md` 按 `body_contract` 提取完整正文，用受支持的 `lh skill edit <id> -c <正文>` 原样提交，然后重新核验全部字段和资源。不要用会吞掉尾部换行的 shell 写法（`$(...)` 命令替换、`echo` 等）传递正文。其他漂移（描述、正文的其他差异、资源路径集或字节、同 key 的身份）先诊断，不盲目重投，也不改包来绕过只读分支。

## 秘密与公开边界

本仓库从公开快照建立，未导入曾含连接配置的旧私库历史；并非不保留此后的公开提交历史。不得提交 token、私钥、密码、`.env`、数据库或 Redis 的导出、备份归档，也不提交一般的连接配置和主机清单。非秘密的受管对象身份、字段路径和专用巡检目标常量只限既有的窄例外，不含凭据，也不新增连接授权。发现秘密泄漏时只报位置和类型，按授权处置和轮换，不复制秘密。

第三方素材、混合来源和许可缺口不因为进了本仓库就取得公开或再分发的权利；要扩大分发，先核对来源许可和用户授权。不得把仓库或共享档案当作凭据来源。

## 测试

```sh
sh tests/run-tests.sh            # smoke：只跑结构守卫
sh tests/run-tests.sh full       # 结构守卫 + gate、privacy、pack、surge、deploy
sh tests/run-tests.sh group surge,deploy
sh tests/run-tests.sh case test-redact.py
sh tests/run-tests.sh list       # 列出入口、分组和是否进 full
git diff --name-only -z --diff-filter=d | sh tests/run-tests.sh select-paths | sh tests/run-tests.sh select
```

- `select-paths` 从 stdin 读 NUL 分隔的变更路径，输出 selector JSON；`select` 读这个 JSON，合并去重后运行。路径到套件的映射在 `tests/test_paths.py`，`run-tests.sh` 头部的说明块必须和 `render-paths` 的输出一致。删除的文件不参与选路，现存但未登记的测试路径会被拒绝。
- `surge` 组分两个入口：`test-surge-package.py` 只核包态（登记资源、自编资料、真包打包与离线验收），Surge 文档、资源或登记改动只跑它；改 `skills/luno-surge/scripts/` 时另跑脚本行为 `test-surge-scripts.py`。
- 署名检查的测试（`identity` 组）不进 `full`，改动署名检查器、它的测试或〈Git 提交署名〉规则时由选路触发；没有 gpg 的机器上，涉及真实签名的用例会跳过。
- 只改正文、没有命中专项时只跑 smoke，不能把它当作各专项都已通过。结构通过不证明行为没有弱化；改加载边或资源边要在同一批更新 `tools/rule-claims.tsv`。
- 测试在白名单环境里运行：独占的 HOME 和 TMPDIR，调用方的其他环境变量不进入，stdin 固定为 `/dev/null`。

结构守卫 `tools/check-rules.py` 的退出码固定为 **0 = 无问题，1 = 结构错误（阻断），2 = 仅提示，3 = 检查不完整（阻断）**。`tools/sync-all.sh` 按 0 和 2 放行（rc=2 的提示保留输出但不阻断）；`tests/run-tests.sh` 把任何非零（含 rc=2）都记为 FAIL，也就是测试门禁要求零提示。两者口径不同是有意的，`tests/test-check-rules.sh` 回归固定这四种状态。`tools/sync-all.sh` 只跑结构守卫和包内校验，不访问生效端。

测试的准入和成本纪律见 `skills/luno-core/references/test-authoring.md`；技能结构校验直接调用 `skills/luno-core/scripts/quick_validate.py`。

共读资源按指针指定的完整原分支读取，原触发和共同前置不变；读法写在 `luno-core` 入口〈加载〉，`tools/check-rules.py` 核对每个分支指针都能找到锚点和 BEGIN/END 定界。路径迁移见 skills-sources.md 的共读资源迁移表；六个技能身份和许可附件保持不变。路径迁移见 skills-sources.md 的共读资源迁移表；六个技能身份和许可附件保持不变。

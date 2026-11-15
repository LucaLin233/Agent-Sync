# Agent-Sync

LUNO 提示词、技能与子代理的版本化资产。Minis/LobeHub 是运行端，仓库是管理落点；合并不等于部署，`present` 不等于已回读。记忆各端自持。

## 入口与许可

- `AGENTS.md`：仓库工作入口；`prompt/`、`skills/`、`subagents/`：受管资产。
- `tools/sync-targets.json`：对象身份、资源与落点的唯一登记；`PENDING.md`：活动未决项。
- 根 `LICENSE`（MIT，Copyright (c) 2026 LucaLin233）仅覆盖自有内容；第三方版权、固定版本、取材边界见 `skills-sources.md`，完整许可随技能包分发，不以根许可替代。Surge 官方原件和 logo 不分发，其边界见 `skills/luno-surge/references/SOURCE.md`。
- 内置技能不是同步对象；模型分组、记忆、设备与环境配置不在备份范围。

## 授权、同步与恢复

操作前完整读取当前生效的 `luno-core/references/sync.md`〔分支 sync、sync-workflow〕及命中资源；候选不覆盖现役授权。分级、独立审查、串行合并部署、前态核对、LobeHub 按需重装与恢复、逐端字节回读均按该流程；工具存在不授予执行权。

官方 CCHP 技能原样放在 `skills/luno-platform/references/cchp-upstream/`（入口 ENTRY.md，含 MIT 全文），本端约定只写在 `luno-platform/references/cchp.md`；来源与采用版本见 `skills-sources.md`。

## 秘密与公开边界

不得提交 token、私钥、密码、`.env`、数据库或 Redis 导出、备份归档、一般连接配置和主机清单。非秘密受管身份、字段路径和专用巡检常量仅限现役窄例外，不新增连接权；秘密泄漏只报位置和类型，按授权处置与轮换，不复制秘密。仓库和共享档案不是凭据来源；第三方或混合素材的公开与再分发须另核许可及授权。

## 固定认证读取

Minis/iSH 已审工作副本中运行（仅标准库）：

```sh
python3 -B tools/auth-call.py pr-meta --repo OWNER/REPO --number 51
python3 -B tools/auth-call.py skill-resource --id SKILL_ID --path references/example.md
```

调用方必须先核确定版本可信和当次授权，再由可信父进程以显式白名单环境调用（不复制整份环境，shell=False）：PR 动作仅提供 GH_TOKEN，资源动作仅提供 LOBEHUB_SERVER、LOBEHUB_CLI_API_KEY 及必要运行常量。不要在 env 命令参数赋密，不读保存态，不将凭据给待审代码或测试。工具只按名读取，不替调用方隔离环境；普通 Shell 可绕过，env-i 不是权限隔离。

成功 stdout 为一行 JSON：ok/action 加 pullRequest/repo 或 resource；帮助 rc=0，所有可控失败 rc=2、stdout 空、stderr 固定 JSON 错误码。无文件写入或自动重试；调用时用 -B。固定 HTTPS、禁代理继承/重定向、验证 TLS；响应上限 2000000B、网络 I/O 超时20秒，调用方另设总体期限。反射检查仅针对本次动作密钥，拒绝而不脱敏改写。

pr-meta 仅九字段，不含 CI 或签名验收；skill-resource 仅六字段，按 encoding 解码并核 size/SHA256，返回值不去尾换行。自洽不证明完整资源集或与 Git 一致，消费者仍须与已合并版本原字节比较。无 PR/merge、安装、删除、SSH、绑定或任意 HTTP/exec 能力，不自动部署到 LobeHub。

专项：sh tests/run-tests.sh case test-auth-call.py，默认不进 full。新增同族测试是因为既有 body/privacy 套件不覆盖固定认证动作；设计预算见 test-authoring，耗时以实跑为准。

## 测试与历史

用法、选路及白名单环境见 `tests/run-tests.sh` 头部与实现；准入和成本见 `skills/luno-core/references/test-authoring.md`。结构守卫退出码见 `tools/check-rules.py` 头部；测试将任何非零记为失败，`sync-all.sh` 只阻断 rc=1/3。结构通过不代替行为审查。

批次结果只记当批 PR，历史以 git 为准；公开快照未导入旧私有 `LucaLin233/Agent` 历史。技能合并与资源迁移见提交 `484de55052413ef2004d5e588d5a0540bcf88826`（六技能）和 #43（记忆并入 luno-platform、CCHP 官方件入包）。

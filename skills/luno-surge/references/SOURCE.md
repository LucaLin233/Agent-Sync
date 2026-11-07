# 上游来源、同步与打包

安装、验收、取源、追新、导入、打包或模块推送前，只读本文件命中的分支；不因一个分支加载整份来源登记。

## 分支索引

- 安装／验收：读〈安装与验收〉及脚本自身 `--help`；运行时传输、参数转换、凭据优先级与远程差异另读 `references/controller-cli.md`。
- 取源／追新／官方导入：读〈官方上游定位与更新核对〉、`references/upstream-manifest.json`、〈导入与失败恢复〉；命令原文导入还要读部署取件装入的 `references/upstream-command-reference.md` 与活动覆盖层。
- 插件开发／导入：读部署取件装入的 `references/plugin-authoring.md` 对应章节（公开仓库不含该文件）；平台门槛以 `references/platform-compatibility.md` 为准。
- 打包／投递：读〈打包与投递〉；模块推送：读〈模块推送〉。第三方精选改写与许可附件只在相关再分发分支读取〈第三方精选补充〉。
- 所有分支共享〈通用门禁〉；本登记自身 `references/SOURCE.md` 只作来源分支索引；HTTP 安全分节写入另读 `references/http-api.md`，诊断与临时规则清理另读 `references/diagnostics.md`。本文件不替代 `luno-core` 授权、秘密、隔离、写后回读与停止规则。

## 通用门禁

- 候选从已核 origin 的独占 `$CANDIDATE` 克隆调用；候选不等于生效值。安装、同步、部署、公开发布和模块推送分别核授权；本登记不授予写入或发布。
- 官方命令原件 `references/upstream-command-reference.md`、官方技能原件 `references/upstream-SKILL.md`、官方插件指南 `references/plugin-authoring.md` **不随公开仓库分发**：部署时从官方包按 manifest 的 `raw_sha256` 取件装入本端技能对应路径（方法见〈取件与部署〉），未装入或哈希不符即停依赖、不换来源；`agents/openai.yaml` 是本地有意改写、随包分发的自有文件，不从官方包取件，也不与官方原件互称。活动 `references/command-reference.md`、本 `SKILL.md` 与脚本是本端覆盖层，人工合并，禁止整体覆盖成 macOS 版。凭据、profile、抓包、请求正文和其他秘密不得进入技能目录。
- 版本、包身份、当前导入／运行验证状态和五个官方文件的逐文件哈希，以 `references/upstream-manifest.json` 为唯一机器记录；正文不复制本批进度或另存第二份当前哈希表。取得包、审阅、批准准入、prepare/apply、部署和逐端回读是不同状态。

## 安装与验收

- `scripts/install.sh` 只把本包 `scripts/surge_cli.py` 链到目标（默认 `/usr/local/bin/surge-cli`，可由 `SURGE_CLI_LINK` 指定），随后必须运行 `scripts/acceptance.sh --installed`；安装点缺失、断链、目标不等或不可执行均非零退出。安装点是包外状态；技能目录改名或迁移后重新验收。
- `scripts/acceptance.sh --offline` 只查包内语法与相对链接，不能证明 PATH 安装点；`--controller`／`--network` 还会连接实例或官方服务，分别需要对应的网络、写删临时目录和上传授权。临时目录必须按 `luno-core` 的单命令创建、退出清理并按实际路径核验；不能满足就不运行联机档。脚本 trap 不保证 SIGKILL 后清理。
- `--controller` 仅在用户指定并授权的实例上读；`--network` 上传合成无秘密 Profile 并发 DNS 请求。任何已注入变量只核存在性，不输出值；凭据只按 `luno-surge/SKILL.md` 与 `references/controller-cli.md` 处理。

## 官方上游定位与更新核对

本对象的官方上游是 Surge for macOS 应用包，非 GitHub 技能仓库。官方 Agent Skill 随 Mac 应用包分发，手册 `manual.nssurge.com/tools/cli.html` 指向 `/Applications/Surge.app/Contents/Resources/Skills/surge/`；不以同名第三方仓库冒充官方来源。

- 官方发现渠道：优先官方 beta appcast `https://nssurge.com/mac/latest/appcast-signed-beta.xml`（`https://nssurge.com/llms.txt` 可作路由），发行包直链形如 `https://dl.nssurge.com/mac/v6/Surge-<版本>-<build>-<hash>.zip`。来源身份检查包内 `Surge.app/Contents/Info.plist`：`CFBundleIdentifier=com.nssurge.surge-mac`、短版本、build；存在 `_CodeSignature` 条目不等于验签通过。
- 固定来源证据：2026-11-03 取源样本的直链为 `https://dl.nssurge.com/mac/v6/Surge-6.11.0-12680-482248c03e2f359522830a18ee52b1f2.zip`，包 sha256 为 `37e72b8e31917c2f9a4f0f350147c8d59abd3c4b9eefd59d585521c99cffba85`；这是来源身份证据，不代替 manifest 的当前状态记录。当前版本报告、取源时间与五文件 `raw_sha256` 只看 `references/upstream-manifest.json`。
- 从包内解出五个官方路径：`SKILL.md`、`references/command-reference.md`、`references/plugin-authoring.md`、`agents/openai.yaml`、`assets/logo.png`。五文件 hash 只与 manifest 的 `raw_sha256` 对照；只有官方命令参考原文哈希进入适配器 `REVIEWED_SHA256` 才可导入。`agents/openai.yaml` 是本地有意改写，logo 不回写；官方原件与本地适配成品不可互称。
- 上游更新核对按每个文件逐个 hash/diff：同时检查默认分支／官方包版本、命令参考准入集合与发布说明；取不齐、身份不符、未知 hash 或协议／平台语义未核实即标缺证并停。无变化也要以文件比较和当前契约正面核实，不用目录名、版本标签或单个末次提交代替。
- 取源时先读官方发布说明及 Mac/iOS 差异；直链优先，SSH 仅限当次指定且获准的 Mac 目标，保持 host-key 检查。不得从生效目录 apply。

### 取件与部署

官方 3 份参考原件不随公开仓库分发，部署任一末端时按此取件；下载（约 48 MB）与写入属该部署授权范围内的操作，没有部署授权就不下载；临时文件放该单元独占临时目录、用完删除：

1. 从官方直链取包（约 48 MB）：`https://dl.nssurge.com/mac/v6/Surge-<版本>-<build>-<hash>.zip`，直链形如 `https://dl.nssurge.com/mac/v6/Surge-6.11.0-12680-482248c03e2f359522830a18ee52b1f2.zip`；核包 sha256 与〈官方上游定位与更新核对〉固定的包 sha256 一致（`raw_sha256` 只记逐文件哈希，没有包哈希字段）。
2. 解出 `Surge.app/Contents/Resources/Skills/surge/` 下的五个官方路径：`SKILL.md`、`references/command-reference.md`、`references/plugin-authoring.md`、`agents/openai.yaml`、`assets/logo.png`。
3. 其中 3 份参考原件逐个核 `raw_sha256` 与 manifest 记录一致：`SKILL.md`→`references/upstream-SKILL.md`、`references/command-reference.md`→`references/upstream-command-reference.md`、`references/plugin-authoring.md`→`references/plugin-authoring.md`；`agents/openai.yaml` 与 `assets/logo.png` 只作来源核对，不回写本包。
4. 各端各自装入本端技能对应路径：Minis 写 `/var/minis/skills/luno-surge/` 下的 `references/upstream-SKILL.md`、`references/upstream-command-reference.md`、`references/plugin-authoring.md`；LobeHub 按现有部署流程写入对应资源。只装这 3 份参考原件；`agents/openai.yaml`、覆盖层 `references/command-reference.md`、`SKILL.md`、`SOURCE.md` 与脚本随包分发、走人工合并。
5. 顺序固定：先拿到**已合并**的版本（PR 合并后按该提交取，不从候选或未合并分支取），在**该次部署独占的 clone** 里按上面步骤补件，逐件核 `raw_sha256`，再用 `tools/deploy_skill.py` 构包／部署，最后回读全部资源。原件只存在于该部署 clone、本端技能目录与平台侧，**不进入公开 Git**（不提交、不建分支、不进 patch）；该 clone 用完即弃。
6. 直链失效、版本不符、包 sha256 或任一 `raw_sha256` 不符即停，不换来源、不改用同名第三方仓库；`scripts/update_upstream.py --source <解出的 skills/surge 目录>` 可直接衔接目录导入与哈希门禁。`tools/deploy_skill.py` **只在本次部署目标就是 `luno-surge` 时**先核这 3 份原件在位且哈希等于 manifest，缺件或取件声明缺失／损坏即拒绝构包（门禁与登记逐项判等，不得绕过）；部署 `luno-core` 等其它对象不因本仓库缺这三件而被拦下。

## 导入与失败恢复

- `scripts/sync_upstream.sh prepare`（也可 `prepare --source DIRECTORY --version LABEL` 或获准 Mac 的 `prepare --host`）只在固定事务根 `/var/minis/shared/surge-updates/` 暂存 raw, staged, review.diff, transaction；无参数等同 prepare。该事务根不属于本单唯一制稿根；若落点授权、目录边界或清理闭环与当前任务冲突，停止并交负责人核资产目录授权。

### `--source` 门禁（不是来源或真实性认证）

门禁只核五个官方路径存在与命令参考哈希，不证明来源或真实性；其他四文件须人工核来源及内容，目录名和版本标签不证明身份。准入集合以 `luno-surge/scripts/adapt_upstream_reference.py` 的 `REVIEWED_SHA256`／`ADAPTED_SHA256` 为准，另核当前文件 sha256。只允许已审阅官方原文作导入源；拒绝未知哈希与已适配成品，不用本技能目录、候选树、覆盖层或适配本作 `--source`，适配成品不得作为 manifest `raw_sha256` 或官方原件。适配器 CLI 只读输出 `raw sha256=<hash>` 或 `adapted sha256=<hash>`，未知哈希非零退出；不再生成、归一或写文件。保留 `adapt_text(text)` 符号仅为显式拒绝旧生成调用，不返回可写回的长本；短覆盖层不得加入任一原文准入集合。

- 新参考哈希被拒先查事务状态：本地 `--source` 在建事务前拒绝，远程可能留 raw 与拒绝记录，不假定 raw 或 diff 留存。审阅 CLI 选项／语义、更新适配器及已审阅哈希并测试后再 prepare；未审阅文字不得批准哈希。
- 审阅原文、diff、manifest 与适配器哈希后，才可在候选内 `apply <TRANSACTION>`。apply 白名单只有 `references/upstream-SKILL.md`、`references/plugin-authoring.md`、`references/upstream-command-reference.md` 与 `references/upstream-manifest.json`（前三份原件只在部署取件后存在于本端，公开仓库不含）；活动覆盖层、`SKILL.md`、`SOURCE.md`、agents 和图标必须人工合并。事务含活动 `references/command-reference.md` 时 fail-closed，不补字段续跑，重新 prepare。
- 建立 `backup/` 前同时核活动内容哈希和模式与 prepare 记录；任一漂移即停且不写、不建 backup，重新 prepare。apply 不是全文件系统原子事务；`state=applying` 中断时先按 `backup/`、transaction 记录的内容和原模式逐文件恢复，再重试；禁止并发更新。
- 导入后只跑离线验收；Controller／网络档按命中授权执行。未设备实测的能力不得写成通过；更新不自动包含打包、重启、临时规则清理或公开发布。

## 打包与投递

- 只用 `scripts/package_release.py` 打包，ZIP 根不带顶层目录；过滤敏感目录／后缀，拒绝符号链接与非常规条目，命中私钥块或 token 前缀即中止。不得包含凭据、profile、抓包、请求正文、数据库或运行输出。
- `tools/deploy_skill.py` 对 `skills/luno-surge` 固定使用本专用打包器；通用工具和专用工具的收集、秘密检查、ZIP 布局不得分叉。候选哈希门禁、源端复核、平台资源逐字节回读与失败分级按工具和 `luno-sync` 执行，不修改脚本实现。
- 本批正文、覆盖层、来源登记或许可附件变化会改变 ZIP 内容及其摘要，可能触发 `deploy_skill.py` 的候选摘要门禁、平台 `zipFileHash` 判等和资源清单断言；`tests/test-surge-scripts.py` 仍须核官方原件 manifest、`REVIEWED_SHA256`／`ADAPTED_SHA256` 与专用打包器约束。审批后重新计算待发布 Git blob、ZIP 和平台资源摘要，并按登记更新；不得为保旧摘要改回正文或修改脚本断言。
- 平台投递使用获准的私有 R2／`lh skill install` 流程，更新后回读实际 identifier、内容、元数据和资源。预签名 URL及临时凭据不得写入回复、日志或文件。

## 模块推送

- 只推自有仓库 `LucaLin233/Proxy` 的 Surge 模块源；推送前读 `luno-ops/references/github.md`，凭据不进命令行，结果以 `gh api` 回读为准，CDN 延迟不算成功。推送与发布仍分别需要授权。
- Git推送仅依 `luno-core/SKILL.md`〈授权与安全〉窄例外，条件不满足即停。

## 第三方精选补充

来源为 `OpenMinis/MinisSkills@164395f193a56e3507ca98415383c7c16780da00` 的 `coredevice-toolkit/references/SURGE_LOOPBACK.md`、`ios-dev/references/loopback.md` 与 `ios-dev/SKILL.md`；2026-10-25 本地核对，精选改写，非 Surge.app 官方更新，在线可取性及当前设备行为未复核。冲突记录：上游根 `LICENSE` 与 `ios-dev/LICENSE` 记载 MIT，README 标 Apache-2.0；按已决裁定随附 MIT 原文，不据 README 改标，也不宣称设备或许可范围因此扩大。

完整原许可不再随本登记正文重复，随包保留为：
- `luno-surge/LICENSE.openminis.txt`：根 LICENSE 原文，来源为该固定提交的公开 raw URL，sha256 `2858f336d8173207aa079c4711085a28d22615d464b6a387363f7824116d00f0`，版权行 `Copyright (c) 2026 OpenMinis`。
- `luno-surge/LICENSE.openminis-ios-dev.txt`：`ios-dev/LICENSE` 原文，来源为同一固定提交的公开 raw URL，sha256 `06dfb33ed30ecda0338b8318d8243f36c501281a5d44398a7e3425ce149bd4f3`，版权行 `Copyright (c) 2026 OpenMinis contributors`；其目录范围、第三方排除与致谢随原文保留。

上述附件仅随包通知与溯源，不产生新的发布授权；公开副本仍需负责人另核原裁定的对象与范围。
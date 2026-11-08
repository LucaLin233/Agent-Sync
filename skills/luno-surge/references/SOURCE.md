# 上游来源、同步与打包

安装、验收、取源、追新、导入、打包或模块推送之前，只读本文件里命中的分支。

## 分支索引

- **安装和验收**：读〈安装与验收〉和脚本自己的 `--help`；运行时的传输、参数转换、凭据优先级和远程差异另读 `references/controller-cli.md`。
- **取源、追新和官方导入**：读〈官方上游与更新核对〉、`references/upstream-manifest.json` 和〈导入与失败恢复〉；导入命令参考原文时，还要读部署取件装入的 `references/upstream-command-reference.md` 和活动覆盖层。
- **插件开发和导入**：读部署取件装入的 `references/plugin-authoring.md` 对应章节（公开仓库不含）；平台门槛以 `references/platform-compatibility.md` 为准。
- **打包和投递**读〈打包与投递〉；**模块推送**读〈模块推送〉。
- 所有分支都适用〈通用门禁〉。HTTP 安全分节写入另读 `references/http-api.md`，诊断和临时规则清理另读 `references/diagnostics.md`。本文件不替代 `luno-core` 的授权、秘密、隔离、写后回读和停止规则。

## 通用门禁

- 候选从已核实 origin 的独占 `$CANDIDATE` 克隆里调用；候选不等于生效值。安装、同步、部署、公开发布和模块推送分别核对授权，本文件不授予写入或发布。
- **官方原件不随公开仓库分发**：命令参考 `references/upstream-command-reference.md`、技能原件 `references/upstream-SKILL.md`、插件指南 `references/plugin-authoring.md`，部署时按 manifest 的 `raw_sha256` 从官方包取件装入本端技能的对应路径（见〈取件与部署〉）；没装入或哈希不符就停止依赖，不换来源。`agents/openai.yaml` 是本地有意改写、随包分发的自有文件，不从官方包取件，也不和官方原件互相冒充。
- 活动的 `references/command-reference.md`、`SKILL.md` 和脚本是本端覆盖层，人工合并，禁止整体覆盖成 macOS 版。凭据、profile、抓包、请求正文和其他秘密不得进入技能目录。
- 版本、包身份、当前的导入和运行验证状态、官方文件的逐文件哈希，只以 `references/upstream-manifest.json` 为机器记录，正文不另存第二份哈希表。拿到包、审阅、批准准入、prepare/apply、部署和逐端回读是不同的状态，不能互相代替。

## 安装与验收

- `scripts/install.sh` 只把本包的 `scripts/surge_cli.py` 链接到目标（默认 `/usr/local/bin/surge-cli`，可用 `SURGE_CLI_LINK` 指定），之后必须运行 `scripts/acceptance.sh --installed`；安装点缺失、断链、指向不符或不可执行都以非零退出。安装点是包外状态，技能目录改名或迁移后要重新验收。
- `scripts/acceptance.sh --offline` 只查包内语法和相对链接，不能证明 PATH 上的安装点。`--controller` 会连接实例，`--network` 会上传合成的无秘密 Profile 并发 DNS 请求，分别需要对应的网络、临时目录读写和上传授权；`--controller` 只读用户指定并授权的实例。临时目录按 `luno-core` 用单条命令创建、退出时清理并按实际路径核验，做不到就不跑联机档；脚本的 trap 在 SIGKILL 后不保证清理。
- 已注入的变量只核对是否存在，不输出值；凭据按入口和 `references/controller-cli.md` 处理。

## 官方上游与更新核对

官方上游是 Surge for macOS 的应用包，不是 GitHub 技能仓库。官方 Agent Skill 随 Mac 应用包分发，手册 `manual.nssurge.com/tools/cli.html` 指向 `/Applications/Surge.app/Contents/Resources/Skills/surge/`；不要拿同名的第三方仓库冒充官方来源。

- **发现渠道**：优先用官方 beta appcast `https://nssurge.com/mac/latest/appcast-signed-beta.xml`（`https://nssurge.com/llms.txt` 可作路由）。官方直链形如 `https://dl.nssurge.com/mac/v6/Surge-<版本>-<build>-<hash>.zip`。来源身份看包内 `Surge.app/Contents/Info.plist`：`CFBundleIdentifier=com.nssurge.surge-mac`、短版本和 build；有 `_CodeSignature` 条目不等于验签通过。
- **固定的来源证据**：2026-11-03 取源的直链是 `https://dl.nssurge.com/mac/v6/Surge-6.11.0-12680-482248c03e2f359522830a18ee52b1f2.zip`，包 sha256 为 `37e72b8e31917c2f9a4f0f350147c8d59abd3c4b9eefd59d585521c99cffba85`。这是来源身份证据，不代替 manifest 的当前状态。
- **五个官方路径**：`SKILL.md`、`references/command-reference.md`、`references/plugin-authoring.md`、`agents/openai.yaml`、`assets/logo.png`。它们的哈希只和 manifest 的 `raw_sha256` 对照；只有命令参考原文的哈希进了适配器的 `REVIEWED_SHA256` 才可以导入。`agents/openai.yaml` 是本地改写，logo 不回写；官方原件和本地适配成品不能互相冒充。
- **更新核对**：逐个文件比较哈希和 diff，同时检查官方包版本、命令参考准入集合和发布说明；取不齐、身份不符、哈希未知或协议和平台语义没核实时，标「缺证」并停止。没有变化也要用文件比较和当前契约正面确认，不拿目录名、版本标签或单个末次提交代替。
- 取源前先读官方发布说明和 Mac/iOS 的差异。优先用直链；SSH 只限当次指定且获准的 Mac 目标，保持 host-key 检查。不得从生效目录 apply。

### 取件与部署

3 份官方参考原件不随公开仓库分发，部署任何一端时按下面的步骤取件。下载（约 48 MB）和写入属于这次部署授权范围内的操作，没有部署授权就不下载；临时文件放在这次部署独占的临时目录，用完删除。

1. 从官方直链下载安装包，核对包 sha256 与〈官方上游与更新核对〉里固定的包 sha256 一致（manifest 的 `raw_sha256` 只记逐文件哈希，没有包哈希字段）。
2. 解出 `Surge.app/Contents/Resources/Skills/surge/` 下的五个官方路径。
3. 3 份参考原件逐个核对 `raw_sha256` 与 manifest 一致，并按这个映射装入：`SKILL.md` → `references/upstream-SKILL.md`，`references/command-reference.md` → `references/upstream-command-reference.md`，`references/plugin-authoring.md` → `references/plugin-authoring.md`。`agents/openai.yaml` 和 `assets/logo.png` 只用于来源核对，不回写本包。
4. 各端分别装入本端技能的对应路径：Minis 写 `/var/minis/skills/luno-surge/` 下的这 3 个文件，LobeHub 按现有部署流程写入对应资源。`agents/openai.yaml`、覆盖层、`SKILL.md`、`SOURCE.md` 和脚本随包分发，走人工合并。
5. 顺序固定：先取**已合并**的版本（PR 合并后按该提交取，不从候选或未合并的分支取），在**这次部署独占的 clone** 里按上面的步骤补件、逐件核对哈希，再用 `tools/deploy_skill.py` 构包和部署，最后回读全部资源。原件只存在于这个部署 clone、本端技能目录和平台侧，**不进入公开 Git**（不提交、不建分支、不进 patch）；clone 用完即弃。
6. 直链失效、版本不符、包 sha256 或任一 `raw_sha256` 不符时停止，不换来源，也不改用同名的第三方仓库。`scripts/update_upstream.py --source <解出的 skills/surge 目录>` 可以直接衔接目录导入和哈希门禁。`tools/deploy_skill.py` 只在部署目标是 `luno-surge` 时检查这 3 份原件在位且哈希等于 manifest，缺件或登记损坏就拒绝构包；部署其他对象不受影响。

## 导入与失败恢复

- `scripts/sync_upstream.sh prepare`（也可以 `prepare --source DIRECTORY --version LABEL`，或对获准的 Mac 用 `prepare --host`；不带参数等同 prepare）只在固定的事务根 `/var/minis/shared/surge-updates/` 暂存 raw、staged、review.diff 和 transaction。落点授权、目录边界或清理闭环和当前任务冲突时，停止并交负责人核对。
- **`--source` 门禁不是来源或真实性认证**：它只检查五个官方路径存在、命令参考哈希在准入集合里，不证明来源和真实性；其余四个文件要人工核对来源和内容，目录名和版本标签不证明身份。准入集合以 `scripts/adapt_upstream_reference.py` 的 `REVIEWED_SHA256`/`ADAPTED_SHA256` 为准。只允许已审阅的官方原文作导入源：拒绝未知哈希和已适配的成品；不用本技能目录、候选树、覆盖层或适配本作 `--source`；适配成品不能写成 manifest 的 `raw_sha256` 或冒充官方原件。适配器 CLI 只读，输出 `raw sha256=<hash>` 或 `adapted sha256=<hash>`，未知哈希以非零退出，不生成、不归一、不写文件；覆盖层不得加入任何原文准入集合。
- **新的参考哈希被拒**时先查事务状态：本地 `--source` 在建事务之前就拒绝，远程可能留下 raw 和拒绝记录，不假定 raw 或 diff 一定留存。先审阅 CLI 的选项和语义、更新适配器和已审阅哈希并测试，再重新 prepare；没审阅的文字不得批准哈希。
- **apply**：审阅原文、diff、manifest 和适配器哈希之后，才可以在候选里 `apply <TRANSACTION>`。apply 的白名单只有 `references/upstream-SKILL.md`、`references/plugin-authoring.md`、`references/upstream-command-reference.md` 和 `references/upstream-manifest.json`（前三份只在部署取件后存在于本端）；活动覆盖层、`SKILL.md`、`SOURCE.md`、agents 和图标必须人工合并。事务里出现活动的 `references/command-reference.md` 时直接失败，不补字段续跑，重新 prepare。
- 建立 `backup/` 之前，同时核对活动内容的哈希和文件模式与 prepare 时的记录，任一项漂移就停，不写、不建 backup，重新 prepare。apply 不是文件系统级的原子事务：`state=applying` 时中断，先按 `backup/`、transaction 记录的内容和原模式逐个文件恢复，再重试；禁止并发更新。
- 导入后只跑离线验收，Controller 和网络档按各自的授权执行。没在设备上实测的能力不能写成通过；更新不自动包含打包、重启、临时规则清理或公开发布。

## 打包与投递

- 只用 `scripts/package_release.py` 打包，ZIP 根不带顶层目录；它过滤敏感的目录和后缀，拒绝符号链接和非常规条目，发现私钥块或 token 前缀就中止。包里不能有凭据、profile、抓包、请求正文、数据库或运行输出。
- `tools/deploy_skill.py` 对 `skills/luno-surge` 固定使用这个专用打包器，通用工具和专用工具的收集、秘密检查和 ZIP 布局不能分叉。候选哈希门禁、源端复核、平台资源逐字节回读和失败分级按工具和 `luno-sync` 执行。
- 正文、覆盖层、来源登记或许可附件的任何变化都会改变 ZIP 内容和摘要，从而触发候选摘要门禁、平台 `zipFileHash` 判等和资源清单断言。审批后重新计算待发布的 Git blob、ZIP 和平台资源摘要并按登记更新；不得为了保住旧摘要改回正文或修改脚本断言。
- 平台投递使用获准的私有 R2 / `lh skill install` 流程，更新后回读实际的 identifier、内容、元数据和资源。预签名 URL 和临时凭据不得写进回复、日志或文件。

## 模块推送

只推自有仓库 `LucaLin233/Proxy` 的 Surge 模块源。推送前读 `luno-ops/references/github.md`，凭据不进命令行，结果以 `gh api` 回读为准，CDN 延迟不算成功；推送和发布分别需要授权，Git 推送只按 `luno-core/SKILL.md`〈授权与安全〉的窄例外执行，条件不满足就停。

## 第三方精选改写

`platform-compatibility.md` 和 `diagnostics.md` 里的 CoreDevice/RSD 同机回环内容，精选改写自 `OpenMinis/MinisSkills@164395f193a56e3507ca98415383c7c16780da00`（2026-10-25 本地核对），不是 Surge.app 的官方更新，在线可取性和当前设备行为没复核。上游许可按 MIT 处理，许可原文随包保留为 `LICENSE.openminis.txt`（根 LICENSE）和 `LICENSE.openminis-ios-dev.txt`（`ios-dev/LICENSE`）；README 标 Apache-2.0 的不一致及其裁定见仓库的 `skills-sources.md`。这些附件只用于许可通知和溯源，不产生新的发布授权。

上述 OpenMinis 材料：Copyright (c) 2026 OpenMinis；Copyright (c) 2026 OpenMinis contributors；2026-10-25 本地决定按 MIT 处理，根 LICENSE 与 README 标 Apache-2.0 的不一致仍保留。本地决定不是法律适用结论，不授权扩大分发；在线可取性及当前设备行为未复核。

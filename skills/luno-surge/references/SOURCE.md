# 来源、维护与交付

本项目非 Surge 官方技能。运行资料由自编工作流和依据官方资料整理的接口事实摘要组成，不分发官方 Skill 完整文件、整篇译文或官方 logo。Surge 名称与官方材料归 Surge Networks；根 MIT 不替代第三方授权。命令、平台和安全门禁分别以入口及对应专业资源为准，本文件不授予连接、写入、删除或发布权限。取源、构包或部署前完整读取 `luno-core/references/execution.md`〔分支 safety〕、`luno-core/references/sync.md`〔分支 sync〕 及其命中的完整分支，写入和临时产物另外满足总控的写入安全规则。

## 共同前置

普通使用和安装不需要补入官方 Skill 原件。本仓库体系的必需运行资料须随包可读，未覆盖的时效性事实按 `references/official-sources.md` 核官方资料；缺依据只停该项。候选不等于生效值，维护不得整体覆盖自编入口、参考资料或脚本。

获准实施时，只在已核实 origin 的独占候选 clone 中修改，并保持串行写入；候选不等于生效值，不从生效目录执行维护。操作候选、安装、取源和投递分别核授权。凭据、profile、抓包、请求正文、数据库和运行输出不得进入技能目录或发布包；不得以私有 ZIP、运行时补件、托管服务或分拆文件绕过完整官方文件不再分发的边界。任何端已有的官方原件如何保留、替换或删除，均另做受控迁移，不由此文件自动授权。

## 来源与许可范围

命令参考（command-reference.md）和插件指南（plugin-authoring.md）是依据官方命令参考和插件指南整理的中文接口事实摘要：按本端任务重新组织，不是译本，没有原文摘录，但事实内容来自官方原文，不称独立创作；其余运行资料是自编的。命令名、协议字段和数值属于接口说明，不据此宣称整套表达无版权限制。`agents/openai.yaml` 是本项目自写的界面元数据，不沿用官方同名文件。

维护时如确需有限短摘录，逐项登记官方来源、版本/日期、位置、长度、用途及改编范围；同时检查整套文件和历次累计取用，不能只看每段短。没有获确认的统一字数或百分比额度，不自行编造安全阈值。注明 Surge 和本项目非官方，不附官方 logo；新版本的取材仍要核版本差异。

私下许可材料由用户持有，本包不公开私信、通信身份或邮件全文。任何对外许可声明须在发布前由负责人核对实际证据及可披露范围；有争议的片段不进入发布包。既有许可附件只覆盖对应 OpenMinis 改写，不覆盖 Surge 材料。

## 安装和验收

`scripts/install.sh` 先把本包 `scripts/` 下的 `*.py`、`*.sh` 设为 755，再建立 `scripts/surge_cli.py` 到安装点的链接；安装是包外写入，须有目标授权。随后使用 `scripts/acceptance.sh --installed` 核链接实际指向；仅包内检查不证明 PATH 安装正确。

`--offline` 核语法和相对链接，不证明运行行为；`--controller` 会连接指定实例；`--network` 还会上传合成无秘密 Profile 并产生 DNS 请求。联机档有临时目录和输出写入，须分别满足工作根、清理、实例、网络和上传授权，未满足不运行。临时目录须按总控在单条命令内独占创建、退出清理并逐路径核验；脚本 trap 不保证 SIGKILL 后清理，未核实残留不得声称已清理。缺失变量只报告，不输出值、不换来源。当前设备未验证的能力如实标未实测。

## 官方来源和追新

官方 Agent Skill 随 Surge Mac 应用包分发，不以同名第三方 GitHub 仓库代替。官方手册 `https://manual.nssurge.com/tools/cli.html` 说明应用包 Skills 目录；Mac 官方 beta appcast `https://nssurge.com/mac/latest/appcast-signed-beta.xml` 可发现版本，它不是 iOS 能力证据。

当前来源基线是 Surge Mac 6.12.0（12810）：2026-11-14 从本机已安装的应用包只读核过 Info.plist 的 bundle id、版本、build 及五份来源文件；没有下载包哈希。历史 12710 与 12680 的来源见 `references/upstream-manifest.json`；12680 于 2026-11-03 取自官方直链 `https://dl.nssurge.com/mac/v6/Surge-6.11.0-12680-482248c03e2f359522830a18ee52b1f2.zip`，包 sha256 `37e72b8e31917c2f9a4f0f350147c8d59abd3c4b9eefd59d585521c99cffba85`。manifest 按 build 只追加、不删旧条目，末项为当前来源基线；raw_sha256 只记官方原件。来源证据、包身份和运行验收不得互相冒充，普通使用不补原件。

取源须另获下载及独占证据根写权；无授权就不下载。核 Info.plist 的 bundle id `com.nssurge.surge-mac`、版本和 build，再核文件哈希、差分及发布说明；存在签名目录不等于验签成功。官方包只在获准的私人维护证据范围查阅，原件和 logo 不进入候选发布目录、公开 Git、patch 或托管包。Mac 原生直接从用户自己的已安装应用包使用官方 Skill，与本项目的再分发方案分开。

追新时，用 `shasum -a 256` 只读计算应用包 Skills/surge 下 SKILL.md、references/command-reference.md、references/plugin-authoring.md、agents/openai.yaml、assets/logo.png，与 manifest 末项比较；它只算摘要，不认证来源。有变化先人工核官方差异并更新受影响的本端事实与流程，再追加新 build；不凭哈希批准准入。来源不齐、身份不符、内容漂移或平台语义未核实时停止相关项。追新不自动安装、部署、重启或清空临时规则。旧 prepare/apply 导入流程已移除，运行包不再携带只用于维护取证的 update_upstream.py。

## 打包、投递及恢复

独立发布包只用仓库级 `tools/package_release.py`（不随技能分发），从仓库根运行 `python3 -B tools/package_release.py <包外输出路径>`；ZIP 根不带顶层目录，LobeHub 仍从 GitHub 子目录安装。打包器拒绝符号链接和非常规条目，扫描已知秘密模式，并按 manifest 全部 build 的哈希并集拒绝已知官方整文件；每个文件只读一次，同一份字节扫描后归档。它不检查源端漂移或审批摘要，也不证明没有其他秘密或已完成许可审查。

部署只用已合并且已独立审查通过的版本；目标身份、实际生效前态、候选核对、写后逐字节回读及恢复均按 `luno-core/references/sync.md`〔分支 sync-workflow〕。现场与历史不符、存在独有资源或未入库差异、并发漂移、部分失败或结果未知时停止相关对象，列出已同步和未同步范围，不盲目重投或自动删除。受管规则的恢复来源不替代非规则配置、业务数据或完整恢复备份；安装成功、HTTP 200 和 CI 通过不证明一致。

**端上旧资源**：新包不含已退役的 `http-metrics.md`、`http-descriptor.md`、`adapt_upstream_reference.py`、`sync_upstream.sh`、`update_upstream.py`、`package_release.py`（打包器已迁仓库 tools），安装也不保证删除端上的旧文件。LobeHub 端 2026-11-11 已按此前的包删除重建，不再有官方原件，当时仍带着前 4 个退役资源；Minis 端未核实，除这些外还可能留有旧流程装入 references/ 的官方原件 `upstream-SKILL.md`、`upstream-command-reference.md`。下一次部署前，先只读列出两端现有资源（Minis 列技能目录，LobeHub 用 `lh skill resources`），与候选资源清单比对并逐项列出多出的文件。删除仍是单独获批的一步：先按上述同步分支核对目标身份、现存路径集及原始字节与仓库历史明确旧版本的对应，核恢复能力和平台限制；未入库差异或独有资源未裁定前停止相关删除。非规则对象和旧事务原有的适用备份、恢复义务不因本说明豁免。再只删明确退役的路径，不递归扫父目录，不随部署顺带执行。LobeHub 原位更新不删除旧资源（2026-11-11 实测），而部署要求平台资源集合与候选完全相等，带着旧资源直接部署会在安装后的回读失败（此时已进入写路径）；所以先按授权处理旧资源（例如删除重建），再部署。历史 prepare/apply 事务不自动迁移或清理；若曾在 state=applying 中断，停止新维护，先在独立授权下核旧事务的 backup、记录内容及原 mode，逐项恢复受影响的旧目标。追新不得续跑旧事务，也不能把旧原件回写到自编候选或据此批准重新分发。

## 第三方精选改写

CoreDevice/RSD 同机回环内容精选改写自 `OpenMinis/MinisSkills@164395f193a56e3507ca98415383c7c16780da00`，2026-10-25 本地核对；不是 Surge 官方更新，在线可取性和当前设备行为未复核。版权为 Copyright (c) 2026 OpenMinis、Copyright (c) 2026 OpenMinis contributors。依既有本地决定按 MIT 处理，根 LICENSE 与 README 标 Apache-2.0 的冲突仍保留；完整通知随包保留 `LICENSE.openminis.txt`、`LICENSE.openminis-ios-dev.txt`，详细范围见仓库 skills-sources.md。本地决定不作法律适用结论，也不扩大分发权。

## luno-surge 输出脱敏的保证边界

本节不是来源记录，暂时没有更合适的位置，所以单列于此。它是历史判据，不是对自由 Shell 的强制保证。边界于 2026-09-16 确立，实现与覆盖范围于 2026-10-11 变更。现行运行义务及其加载触发已迁至 `references/command-reference.md`〔分支 output-safety〕；本节保留历史取证，不替代运行分支。

**2026-09-16 的覆盖范围**：

- 带键名的认证字段（`authorization`、`proxy-authorization`、`auth`、`authz`，键可带引号）分三种情形处理。① 引号值按引号配对，双引号和单引号各有自己的字符类与转义，键与值之间允许换行缩进，因此覆盖多行 JSON 和双引号内含单引号的情况。② 带方案词（`Bearer`、`Basic`、`Digest`、`Negotiate`、`NTLM`、`aws4-hmac-sha256`）时抹除该字段整行。③ 其余裸值以逗号、分号或换行为界，不以 `}`、`]` 为界，否则 `Authorization: SYNTH}SECRET` 会在闭合符处截断，泄漏尾部；值以抹除标记开头时，只保留标记和其后的结构闭合符，其余残余丢弃。
- 敏感键（`password`、`passwd`、`pwd`、`psk`、`private_key`、`token`、`api_key`、`x_key`、`secret`、`credential`）的引号值、裸值和平面数组值，以及已知 token 前缀（`sk`、`ghp`、`github_pat`、`xox*`）。
- `user` 和 `username` 也在抹除范围内。2026-09-16 的判定是：字段名不能证明其值永远不敏感，移除它们属于收窄保护，必须由用户明确确认后才能放宽，确认前维持默认抹除。

**2026-09-16 的不覆盖范围**，不得据此宣称完整脱敏：

- 没有键名的裸方案词，例如 `x Bearer <值> end`。这是刻意为之，避免误抹普通英文 `basic configuration failed`。
- 嵌套在数组或对象里的敏感键，例如 `{"token":[["x"]]}`。2026-10-11 起，JSON 文档（任意布局）中的这类情况已被覆盖；非 JSON 文本形态仍不覆盖。
- Unicode 转义的键名，例如 `{"to\u006ben":"x"}`。
- 整体编码或 Base64 载荷。

因此脱敏输出不等于可以对外发布的安全日志。作为诊断输出前仍需人工检查，对外分享前还要另行核对。

**2026-10-11 的变更**（2026-10-11 记录时尚未部署或平台验收）：

- 实现收敛为共享模块 `scripts/_privacy.py`，由 `surge_cli.py`、`surge_ios.py`、`test_policy_descriptor.py` 共用。`surge_cli.py` 此前完全没有脱敏，成功 JSON、错误、`profile diff` 和 `--check` 的返回都原样输出；此次在全部输出边界接入了脱敏。
- 新增覆盖：前缀驼峰键（如 `proxyPassword`）、复数键（如 `tokens`）、认证键（`Authorization`、`proxy-authorization`、`auth`、`authz` 及其前缀驼峰变体）的结构化整值替换、Profile 代理行（如 `PROXY-A = https, host, 443, user, <PASS>`，含中文或 Unicode 节点名）、内层转义的 JSON 串，以及 JSON 文档（任意布局）中嵌套容器的整值替换。紧凑布局走结构化重排，其他布局按 JSON 字符串 token 就地脱敏并保留原布局。
- 仍不覆盖：没有键名的裸方案词、Unicode 转义键名、整体编码或 Base64 载荷，以及 JSON 嵌在普通文本中时的嵌套容器。
- 有据例外：`surge_cli.py` 的 `--help` 和 `help <cmd>` 走不脱敏的路径。它们输出编译期的帮助字面量，含变量名 `SURGE_API_KEY`，脱敏会把变量名改写成 `<redacted>`；其中不含运行时数据。
- Profile 代理行的凭据字段位置表按协议常识和包内示例实现，没有与官方手册核对（离线取不到）；类型表只列位置明确的协议，以免误抹策略组行。

现行输出安全契约已迁至 `references/command-reference.md`〔分支 output-safety〕，原五项义务逐字保留；使用三个桥接助手或判读、整理、分享其输出前，由技能入口明确触发完整加载。本节保留历史取证，不替代运行分支。


## 本地帮助证据

历史帮助证据：2026-11-10 核过 Minis 当时安装的桥（`4e58a2411a6af6ef271a1f68fcb749cfd0a9daee5f29e8a520fe2e3e1fb20732`），在清空凭据环境并禁止写入/网络的审计下，--help、help 和当时全部静态 HELP 键均可本地读取；plugin、capture-filter 当时回落主帮助。后续仓库版 `0ff3ef70080190856e435f57957afa14a995dbed6ffffbe91ddf99729b9bdd72` 只补过 reload 的自动完整重启说明。新增或修改帮助后须重新核目标输出覆盖及无连接路径，并记录受测脚本哈希；历史结果不覆盖新增帮助，不证明远端支持。部署后按已审脚本字节回读。只保留帮助未覆盖的领域事实、安全风险、平台约束及复杂语义，不复制可靠帮助已有的参数说明。

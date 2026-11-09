---
name: luno-cchp
description: CCHP控制面：用量、请求、provider/key、覆写规则、LLM token、成员配额与导入；非通用运维。
---
# LUNO｜CCHP 控制面

## 范围

CCHP（Claude Code Hub Plus）控制面：用量与耗材、请求日志、provider 与 provider key、LLM token、成员与配额、CC Hub 导入，以及少量设置读取。有两个入口：`cchp` CLI（用管理 token；spec 内置在 CLI 里，可以离线查操作）是默认入口；Management API（HTTP 直连）只在 CLI 可用、并已从 CLI 取得操作契约时用于编排，不是缺 CLI 时的替代。网关转发、模型质量和通用运维不属于本技能。

**相邻领域**：宿主机、容器、反代、DNS、TLS、防火墙和 CCHP 镜像升级归 `luno-ops`；Minis 技能登记归 `luno-minis`；LobeHub 的模型和渠道归 `luno-lobehub`。混合任务取并集，不用控制面技能代替运维。

## 实例与端点

管理面用 `CCHP_GATEWAY_URL` + `CCHP_TOKEN`，模型数据面用 `CCHP_BASE_URL` + LLM token，两者都必须是本次获准、已注入的变量，**两个面不得混用**。CLI 的 server 必须指向管理面（变量用法和反例见 `references/interfaces.md`〈实例端点与凭据〉）。缺哪个入口或凭据，就停止依赖它的请求、命令和结论，并报告变量名；不回退旧地址、不猜子域、不换实例或环境。离线分析和另一个入口的已授权操作可以继续。

## 资源与触发

路径相对技能根，命中即整份读取，不再按小节裁剪：

- 任何实际CLI或API调用，以及认证、结果、错误、分页、重试、流式和下载的解释：`references/interfaces.md`。
- 业务操作、解释、建议或结论，以及任何写入、恢复、覆盖或转发变更：完整读取 `references/workflows.md`；其中组织约定、改前快照、配置继承与恢复适用于所有写入。纯接口认证或分页咨询不触发业务资源。
- 请求/响应覆盖规则（request-overrides，旧称“请求过滤器”）的读取、解释、建议、结论、草稿验证和任何写操作：`references/coverage-rules.md`；实际调用或涉及接口契约时另读 `references/interfaces.md`，写入或跨业务比较另完整读 `references/workflows.md`。
- 实际需要备份（如导入覆盖）或命中宿主机、容器、反代、DNS、TLS等运维时，按需加载 `luno-ops` 并读取命中的完整资源；需要备份的变更须完成改前备份与改后回读。普通对象操作仍须核授权、留改前快照、改后回读并具备恢复办法，不因免读ops而免除这些义务。
- 来源、许可、改写边界或上游更新核对：完整读取 `luno-cchp/SOURCE.md` 的维护规则及其仓库登记；普通调用不加载来源档案。

## 执行位置与版本门槛

1. **先定位置**：CLI 可以按授权装在多台主机上（含 Minis 本机），不预设固定主机；先确认本次的执行主机、用户和项目，定位和安装都只在这个环境里做。不凭文档或历史结论推断当前实例的状态。
2. **再找 CLI**：先 `command -v cchp`；没命中不等于没安装（非交互 shell 的 PATH 常不全），再查该用户的 `$HOME/.local/bin/cchp`、`/usr/local/bin/cchp`、`/opt/homebrew/bin/cchp` 和已知的自定义位置。仍找不到就报告「当前执行环境未定位到可用 CLI」，不断言没装。找到后用选定的入口执行 `version --json`，记录实际路径、CLI 和 spec 版本，后续一直用这个入口。
3. **安装或升级**只在获准的主机目录里做，不动服务端和编排：核对 `CCH-HQ/cchp-cli` 安装器的来源和内容，用 `CCHP_VERSION`/`CCHP_INSTALL_DIR` 明确版本和目录（默认 `$HOME/.local/bin`），用 `checksums.txt` 校验，覆盖旧二进制前备份。默认用显式路径；只有系统入口获准、目标没有冲突、目录在实际 PATH 里时，才建 `/usr/local/bin/cchp` 软链。改完按真实的调用方式（含非交互 SSH）核对入口和 `version --json`。失败就停止依赖的部分，按备份和授权恢复。
4. **再定身份和实例**：用选定的 CLI 执行 `status --json`，核对 server、token 前缀、身份和连通性，和本次授权不符就停。服务端版本（控制台或 `cchp admin about`）和 CLI、spec 版本一起记录；服务端版本未知，或动作依赖未核实的契约时，只做只读。
5. **门槛**：没找到可用的 CLI、版本不符或 spec 与实例不匹配时，停止控制面操作并报告缺口，不用 Management API 直连代替；已获授权的定位、安装或升级可以按本节处理，完成后重新核验前提。

## 认证边界

- 只用〈实例与端点〉里本次授权且已注入的变量；缺失就停下报告变量名，不换来源，不交互补取。
- **不回退**到 `CCHP_TOKEN_FILE`、`cchp login` 的保存态、系统 keychain，或其他服务器、其他组织的 token（上游 CLI 默认会尝试这些来源，所以要明确拒绝）。
- token 不进命令行参数、会话、日志、提交或报告。一次性密钥（新建的 token、生成码）只经 `--secret-out` 写入本次授权的受控路径，回报路径和字段名，不回显值。
- 管理 token 只能调用其权限范围内的操作，有效权限是人员角色和 token 授权范围的交集。`excluded` 类操作（改密、通行密钥、二步验证、轮换 token、登录和安装流程）只能由用户在控制台完成。

## 核心循环

`cchp commands --search "<词>" --json` → `cchp schema <operationId> --json` → `cchp api <operationId> [--flag value] --json`。

- 操作的旗标、风险门禁、示例和分页描述符，按当前 CLI 执行 `cchp commands show <operationId> --json`；通用的输出、错误和任务规则按需查 `cchp guide agents|errors|tasks`。不缓存普通命令示例或旧分页表；当前 CLI 和 spec 没给出的字段、旗标或续页方式不能猜。
- 参数是 kebab-case 旗标（`providerId` → `--provider-id`），数组重复书写；路径参数可以按位置给；JSON 请求体用 `--body-file <file>` 或 `-`，先过本地 schema 校验再原样发送。
- 先 `--dry-run` 看将要发出的 method、URL 和请求体（已脱敏），再决定是否加写入门禁。
- `orgId` 默认取 token 所属的组织，不指定其他组织。
- 分组命令和 `cchp api` 同源；operationId 仍是记录和交接用的标识，但**以所选 CLI 内置的 spec 为准**：升级后重新发现操作并核对 schema，不假定旧 operationId 仍然存在。
- 一次只执行一个变更；不并发批量修改，不在同一个窗口里混用不同的操作。

## 门禁不是授权

`--allow-write`、`--confirm <operationId>`、`--secret-out` 是 cchp 的工具门禁，只说明「这条命令可以发出」，**不等于用户授权**，也不扩大授权范围；加之前必须有本次用户请求或既有授权里的明确范围。

## 停止条件

遇到以下情况立即停下，不绕路、不换入口重试。按 `references/interfaces.md`〈结果契约〉的安全输出要求，报告已确认不含秘密的 `error.kind`、`error.message` 和 `request_id`；含秘密或安全性不明时只报位置、类型和缺口。

- `permission_denied`（退出码 4）或 `unauthorized`（3）：权限或 token 边界问题；有 `required_permission` 就照实报告。
- `browser_session_required` 或 `human_verification_required`（8）：只能由用户在控制台完成，说明原因，不找替代路径。
- `unknown_outcome`（12）：结果未知，停止变更，先只读取证再决定。
- `policy`（13）：门禁拒绝；核对是否真的属于本次授权，不为了通过而叠加旗标。
- 不满足〈执行位置与版本门槛〉里的 CLI 可用性或版本、契约前提。
- 需要超出本次授权的写入、不可逆动作、新环境或新凭据。

## 输出

结论先行：操作和目标实例、实际命令或 operationId、关键字段（用量、状态、`request_id`）、没执行的项和不确定之处。有变更时补上改前状态、改后回读结果和回滚方式；影响转发时另报链路验证结果或没验证的原因（判据见 `references/workflows.md`〈转发相关变更的验收与切换〉）。

来源与许可：CCH-HQ/cchp-cli 的 MIT 精选改写；Copyright (c) 2026 the cchp contributors；完整许可见 LICENSE.upstream.txt；详细取材见仓库 skills-sources.md；跟版按包内 luno-cchp/SOURCE.md。

# Agent-Sync

LUNO 提示词、技能与子代理的版本化资产。Minis 与已授权宿主 CLI 是运行端，仓库是管理落点；合并不等于部署，`present` 不等于已回读。记忆各端自持。

## 入口与许可

- `AGENTS.md`：仓库工作入口；`prompt/`、`skills/`、`subagents/`：受管资产。
- `tools/sync-targets.json`：对象身份、资源与落点的唯一登记；`PENDING.md`：活动未决项。
- 根 `LICENSE`（MIT，Copyright (c) 2026 LucaLin233）仅覆盖自有内容；第三方版权、固定版本、取材边界见 `skills-sources.md`，完整许可随技能包分发，不以根许可替代。Surge 官方原件和 logo 不分发，其边界见 `skills/luno-surge/references/SOURCE.md`。
- 内置技能不是同步对象；模型分组、记忆、设备与环境配置不在备份范围。

## 授权、同步与恢复

操作前完整读取当前生效的 `luno-core/references/sync.md`〔分支 sync、sync-workflow〕及命中资源；候选不覆盖现役授权。分级、独立审查、串行合并部署、前态核对、逐端字节回读均按该流程；工具存在不授予执行权。

官方 CCHP 技能原样放在 `skills/luno-platform/references/cchp-upstream/`（入口 ENTRY.md，含 MIT 全文），本端约定只写在 `luno-platform/references/cchp.md`；来源与采用版本见 `skills-sources.md`。

## 秘密与公开边界

不得提交 token、私钥、密码、`.env`、数据库或 Redis 导出、备份归档、一般连接配置和主机清单。非秘密受管身份、字段路径和专用巡检常量仅限现役窄例外，不新增连接权；秘密泄漏只报位置和类型，按授权处置与轮换，不复制秘密。仓库和共享档案不是凭据来源；第三方或混合素材的公开与再分发须另核许可及授权。

## 固定认证读取

Minis/iSH 已审工作副本中运行（仅标准库）：

```sh
python3 -B tools/auth-call.py pr-meta --repo OWNER/REPO --number 51
```

调用方必须先核确定版本可信和当次授权，再由可信父进程以显式白名单环境调用（不复制整份环境，shell=False），只提供 GH_TOKEN 及必要运行常量。不要在 env 命令参数赋密，不读保存态，不将凭据给待审代码或测试。工具只按名读取，不替调用方隔离环境；普通 Shell 可绕过，env-i 不是权限隔离。

成功 stdout 为一行 JSON：ok/action 加 pullRequest/repo；帮助 rc=0，所有可控失败 rc=2、stdout 空、stderr 固定 JSON 错误码。无文件写入或自动重试；调用时用 -B。固定 HTTPS、禁代理继承/重定向、验证 TLS；响应上限 2000000B、网络 I/O 超时20秒，调用方另设总体期限。反射检查仅针对本次动作密钥，拒绝而不脱敏改写。

pr-meta 仅九字段，不含 CI 或签名验收。自洽不证明与 Git 一致，消费者仍须与已合并版本核对。无 PR/merge、安装、删除、SSH、绑定或任意 URL/query 能力。

专项：sh tests/run-tests.sh case test-auth-call.py，默认不进 full。新增同族测试是因为既有 body/privacy 套件不覆盖固定认证动作；设计预算见 test-authoring，耗时以实跑为准。

## Minis 本端只读验收

`tools/minis-verify.py` 将所选 Minis受管对象与指定提交比较；只读，不采集配置、不联网、不修复或 chmod。

```sh
python3 -I -B tools/minis-verify.py --repo REPO \
  --git-version FULL_SHA --object OBJECT_ID [--object OBJECT_ID …] \
  [--root /] [--projection projection.json]
```

`FULL_SHA` 必须是40位小写十六进制的 commit本身；不接受 tag/tree或隐式解引用。`--object` 必须非空、不重复，并且每项都在同提交登记中满足 `ends.minis.present=true`。登记、期望文件、资源及 Git模式均取该提交，不取工作树。

`--root` 默认 `/`。目标登记路径 `/var/minis/...` 映射为 `<root>/var/minis/...`；测试根也必须保留这一布局。根必须是绝对路径，不接受 `.`、`..`、空组件或软链；不提供逐对象改路径功能。非 `/` 根仅表示重定位文件视图，不能据此声称真实 Minis已验收。身份检查失败时不得换根重跑以绕过失败。

#### 检查范围与字节口径

| 登记对象 | 文件检查 | 生效字段检查 |
| --- | --- | --- |
| 技能，`minis.kind=file` | `minis.path`全文及登记资源原字节；枚举该技能包集合 | 不检查 App登记元数据、启用或加载 |
| SOUL，`minis.kind=field`且有 `alsoFile` | `alsoFile` 经 `body_bytes` 提取的正文；不比较其 App frontmatter | 登记指定字段与 Git源文件正文严格比较 |
| 子代理，`minis.kind=field` | 无登记文件则不另找文件 | 只比较登记指定 instructions字段 |

技能资源从登记 `source` 所在仓库目录转为包内相对路径；不得逃出该目录、重复或指向别的对象。技能主文件亦计入包集合。二进制、空文件、CRLF及末尾换行保持，不将资源套入 UTF-8正文契约。

SOUL文件 frontmatter不在本入口覆盖内，不从 `prompt/SOUL-frontmatter.yaml` 猜造现场完整文件；配置中的 SOUL名称、图标等也不读取。SOUL文件正文、`soul.body`及 Git正文分别比较，不能因其中两项相等而豁免第三项。

字段默认严格比较。仅对登记所覆盖的子代理 instructions，沿用既有“允许去掉恰好一个尾 LF”的有限例外；不得 `rstrip`或归一换行。仓库当前三份子代理本来不带尾 LF，不能再删字节。SOUL不应用该例外。

Git `100644/100755` 在本入口只映射为**属主执行位关闭／开启**；同时要求目标为普通文件。其他 POSIX权限位、所有者、ACL等没有在 Git中表达，不报“全部权限一致”，也不自动 chmod。SOUL文件使用其登记源文件的 Git执行位口径；纯配置字段没有 filemode检查。其他 Git文件类型为不支持的期望输入，rc2。

#### 有界文件读取

只进入所选对象的登记路径和技能包；不列举其他技能或打开未选对象正文。

从 `/` 的目录 fd开始，逐组件以已锚定父 `dir_fd`、`O_DIRECTORY|O_NOFOLLOW` 打开根及祖先目录；组件不得含斜线或为 `.`、`..`。身份只用仍存活 fd的 `fstat(dev, ino, S_IFMT)` 全 tuple：从同一父 fd真正重新 open同名组件，比较原持有 fd与新 fd的完整 tuple，保留父子 fd关系和祖先 fd至操作后收尾。不得用 dup、重复 fstat同一 fd或缓存目录项代替名字重开；路径 stat可作元数据用途，但不得与 fstat混合判身份，不归一 dev、不只比 inode。

普通文件以 nofollow、非阻塞方式打开，先 fstat确认普通文件再读；预后核身份、模式、size、mtime_ns、ctime_ns，并在读后从原父 fd安全重开同名文件，以两个仍存活 fd的完整 tuple复核，再逐祖先同父重开收尾。常规 open后 fstat不能保证连瞬时特殊设备打开都没有副作用；O_NONBLOCK不作这种保证，不引入未经验证的 O_PATH或 /proc依赖，任何非普通文件均不得读取正文。读取至多为比较所需字节：普通全文文件可用已知期望长度加1检测超长；SOUL文件和投影输入各设2,000,000 B读取上限，超限报不可验证，不截断后判通过。

技能包通过已锚定目录 fd枚举，比较普通文件及隐含父目录集合，文件字节和属主执行位分别报告。缺失的登记文件报 `file_missing`，相同路径上的类型不符报 `file_type`。多余普通文件只取元数据，不打开内容；多余目录可继续作目录元数据枚举，不读其中文件正文；不跟随任何软链。单包枚举上限为10,000个条目、64层、累计路径字节1,000,000 B；超限 rc3。多余空目录同样报告额外路径，不以 Git未记录空目录为由忽略。

末级软链或错误类型不打开：保留已确认的类型／集合差异；涉及软链阻断的内容检查同时记不可验证。祖先软链、身份不一致、权限不足、读取／枚举期间变化均 rc3，不能降级跟随或忽略 dev。缺失且已被稳定目录观察确认的登记文件为差异，不伪装成执行异常。

同父安全重开所得 fd与原持有 fd的完整身份 tuple无法一致时，固定报 `identity_unverifiable`；不支持该原语时停止相关检查。路径 stat与 fstat的 dev差异根因未定位；本原语不混用两接口判身份，也不从 inode单值或正常观察推断映射。实施者须以同环境低成本验证实际 open/fstat接缝及替换拒绝；未测子树不能外推。前后复核不证明原子快照、绝无并发或不存在 ABA式短暂换绑。

#### 生效字段安全投影

选中任何 `kind=field` 对象时，需由当次可信调用方按授权从源头只取得所选字段，保存为下面的投影文件。工具不调用 `minis-config`，不读整配置、环境、保存态或凭据来源。

只选文件对象时可省略 `--projection`；此时提供该参数属于不必要输入，rc2且不打开文件。选中字段对象而未提供投影时仍可检查独立文件，但字段检查 rc3。

所有层级只接受下表键；键均必需。任意层重复键、未知键、非有限数值、错误类型为 rc2；缺键为 rc3。缺键不能阻断其他已给字段的独立类型检查。字符串必须可严格编码为 UTF-8。

| 层级 | 必需键及类型 |
| --- | --- |
| 根 | `schemaVersion`：整数1；`observation`：对象；`objects`：对象数组 |
| `observation` | `id`、`instanceRef`、`sourceVersion`、`sourceBasis`：非空字符串；`startedAt`、`finishedAt`：时间字符串 |
| `objects[]` | `object`、`observationId`、`instanceRef`、`field`：非空字符串；`value`：字符串或 null |

时间须为有效 UTC秒格式 `YYYY-MM-DDTHH:MM:SSZ`，无小数，结束不早于开始。数组可为空：缺少所选字段对象为 rc3；含未选对象、文件型对象或重复对象为 rc2。每条记录的观察与实例标签分别等于顶层标签，`field` 必须逐字等于该提交登记字段；不匹配为关联错误 rc2。此检查不证明标签真实。

`value`缺键为缺证；显式 null与任何字符串不同；空串是可比较值。不得用 null或空串补缺失。不得先整取配置再筛选成此文件；输入结构完整、`sourceBasis`有值都不证明源头投影安全。

下面仅展示结构，值是虚构观察，不表示真实现场或 PASS。对象与字段必须从所选提交登记取得：

```json
{
  "schemaVersion": 1,
  "observation": {
    "id": "obs-example",
    "instanceRef": "minis-example",
    "sourceVersion": "app-example",
    "startedAt": "2026-11-15T19:00:00Z",
    "finishedAt": "2026-11-15T19:00:01Z",
    "sourceBasis": "reference-to-authorized-field-projection"
  },
  "objects": [
    {
      "object": "prompt/LUNO.md",
      "observationId": "obs-example",
      "instanceRef": "minis-example",
      "field": "soul.body",
      "value": "示例正文\n"
    },
    {
      "object": "subagents/minis-general-fallback.md",
      "observationId": "obs-example",
      "instanceRef": "minis-example",
      "field": "subagents.general.instructions",
      "value": ""
    }
  ]
}
```

真实实例、源端版本、采集时点、源头投影及记录真实性由当次可信调用方在外部核准；工具只验证可观察结构、关联与字节。观察标签不是配置内容版本，也不是无并发证明。投影仅限当次输入，不新增长期配置、签名或批准回执。

#### 输出、退出码与限制

stdout固定输出一份 JSON，stderr不输出原异常：

- 根键：`gitVersion`（提交字符串；参数未接受时 null）、`rootView`（`live/relocated`）、`status`（`match/different/error/incomplete`）、`checks`、`issues`、`notCovered`。
- `checks`为对象数组，每项固定键 `object/item/status`；status为 `match/different/not_checked`。item只使用 `file:<登记仓库路径>`、`exec:<登记仓库路径>`、`field:<登记字段>`、`package-set`。
- `issues`为对象数组，每项固定键 `class/code/object/path`。class为 `difference/error/missing_evidence`；object为已核登记ID或 null；path只允许已校验的包内相对路径或 null。不输出内容、元数据值、任意异常、非法路径或未经确认的输入对象名。
- `notCovered`为字符串数组，明确列出适用的 App登记／启用／实际加载、SOUL frontmatter、其他 POSIX权限、来源真实性及原子快照未覆盖项；不能凭文件相等报 App整体通过。

固定分类：

| 类别 | 固定码 |
| --- | --- |
| rc1差异 | `file_missing/file_type/file_bytes/file_exec/file_contract/package_set/field_value` |
| rc2输入或执行错误 | `bad_args/bad_json/bad_shape/unknown_key/duplicate_key/duplicate_item/unselected_object/field_binding/git_error/unsupported_git_mode/expected_contract_error/internal_error` |
| rc3缺证或不可验证 | `missing_projection/missing_field/missing_object/identity_unverifiable/unsafe_path/not_readable/changed_during_read/enumeration_limit/unsupported_runtime` |

混合结果按 **2 > 3 > 1 > 0** 汇总，status分别为 `error/incomplete/different/match`；已确认差异、独立错误和缺证同时保留，不能用一个坏节点清空其他可核发现。已变化文件不能保留未经确认的 match；其他独立稳定检查仍保留。

rc0只表示所选范围、所给可信投影及本次可验证文件视图下匹配，不证明投影真实、无并发或实际加载。某技能不需要字段投影，不代表 App登记已验收。

写前选明确历史旧提交，写后选合并提交并重新观察。不得拿旧投影冒充写后结果；字节等价的不同提交、伪造且一致的标签不能据此识别。失败不自动重试、采集、修复或改权限。

## 宿主端安装（npm 安装、systemd 托管的 Paseo 与 Codex）

宿主端是 npm 安装并由 systemd 托管的 Paseo；Codex 作为 provider 进程在运行用户下启动。仓库不提供容器构建路径，也不假定部署目录、用户名或镜像布局。规则与流程按 `skills/luno-core/references/sync.md`〔分支 sync-host〕，各端机制见 `skills/luno-platform/references/runtime-host.md`、`runtime-codex.md`、`runtime-paseo.md`。下文 `<home>` 是核实后的受管安装根（安装器的 `--home`，不必然等于 Paseo data home 或 systemd 的工作目录），`<checkout>` 是受管检出，`<prefix>` 是隔离安装前缀；它们都是占位符，实际值按当次现场读取，不写进仓库。已核基线是活动 systemd 单元经 Node/mise 启动，`@getpaseo/cli` 与 `@getpaseo/server` 同为 0.17.1；具体用户、安装前缀、HOME 与 Paseo data home 以现场读取为准。除只读取证外，命令都以实际运行用户执行；需要提权或切换系统单元的动作另按授权进行。

1. **核实实际入口**：只读核对活动 systemd 单元的实际用户、`ExecStart`、环境和工作目录，确认进程实际加载的 `@getpaseo/cli` 与 `@getpaseo/server` 来自同一安装前缀且版本一致，记录可恢复的旧程序入口、配置和登录态位置。不要只凭 `which`、全局 npm 清单或包目录推定实际加载。
2. **隔离前缀验证补丁包**：在独立构建目录取固定上游提交 `043f0995d4d7e91ab12f3eecef1afce055a81972`，用 `git apply --check` 后应用 [0.17.1 共享角色补丁](platforms/paseo/codex-role-verification-v0.17.1.patch)，按 Paseo 发布流程构建；把构建产物装进与现役前缀分离的 npm `<prefix>`（同版本 `@getpaseo/cli`、`@getpaseo/server`），用该前缀的版本回读和隔离启动验证补丁包，不原地改写现役前缀，也不在这步切换 systemd 单元。
3. **受管检出**：以运行用户 `git clone https://github.com/LucaLin233/Agent-Sync.git <checkout>`；之后只快进到已合并的 main（升级失败时的回退见第 10 步），不在其中编辑。
4. **GLOBAL 副本或 daemon 范围来源**：默认内嵌模式把 Minis `GLOBAL.md` 整份复制到 `<home>/.luno/memory/GLOBAL.md`（属主为运行用户，权限 600）；缺这个文件时安装器在预检阶段报错，不做任何写入。以后 GLOBAL 更新时，复制后再运行一次 `--apply` 与 `--check`，重新生成 Codex 常驻文件。已选 daemon 模式时改用单端选项（见下文〈Codex GLOBAL 来源〉），不再要求私人副本。宿主经验日志的创建、检索和共享见 [宿主端记忆入口](skills/luno-platform/references/runtime-host.md#记忆入口)。
5. **安装与核对**：以运行用户运行 `python3 -B <checkout>/tools/link-install.py --checkout <checkout> --home <home>`。默认只列计划，确认后加 `--apply` 写入，用 `--check` 回读。安装器按 `tools/sync-targets.json` 的 `codex`、`paseo` 端登记，建立以下内容：技能软链；`~/.luno/generated/` 下的生成文件及其公开软链（`~/.codex/AGENTS.md`）；登记的角色家目录（包括 `~/.luno/homes/{lens,forge}-codex/`、`{lens,forge}-gdr/` 及配置示例的角色落点）。如果第 4 步选择 daemon 范围 GLOBAL，角色家目录仍需单独安装：分别以 `--ends codex --codex-global-source paseo-append-system-prompt` 和 `--ends paseo` 各做一次 plan、`--apply`、`--check`；前者只生成 Codex 主入口，后者建立角色家目录与技能链接。它不读取、不复制凭据和登录态，不改写已有的 settings 或 config；遇到非受管文件占位、经非受管软链的路径、没有对应公开软链的生成文件、角色家目录属主或权限（700）不符，或本次安装计划中的受管 `AGENTS.md` 旁存在 `AGENTS.override.md` 时，停止并报告，不覆盖这些文件。生成文件先在同一目录以本次运行独占的随机名排他创建暂存文件，再改名或链接成正式文件，所以中断时正式文件保持原样；暂存残留的归属无法证明，安装器不清理也不判断，只在报告 `residue` 里按前缀列出（含旧版固定名 `.<文件名>.link-install.tmp`），由用户核对后自行删除。`--apply` 成功时报告的 `created` 只列本次实际执行过的项及其 `state`（`create` 新建、`update` 覆盖），计划里没有执行的项不列入，已一致的重跑为空。
6. **登录**：主会话以运行用户执行 `codex login`。使用登录态的角色家目录各登录一次；使用 `env_key` 的角色沿用当次获准注入，不要求另行登录。例如 `env CODEX_HOME="<home>/.luno/homes/forge-codex" codex login`。登录态留在该用户的持久目录中。
7. **paseo 配置**：从 `platforms/paseo/config.example.json` 选择本次获准的 `daemon.mcp`、provider 与 Profile 条目，保全其他现值后合并进经核实的 `PASEO_HOME`/生效配置路径（按 systemd 单元环境和实际启动参数核对，不推定为运行用户 HOME 下的 `.paseo/config.json`）。示例中的 `/home/example` 只是可见占位根，实际替换为核实后的安装路径；`PASEO_CODEX_ROLE_SOURCE` 也要按实际 `<checkout>` 单独替换，不能只改 HOME 根。不要把示例整表覆盖现有配置。监听地址、systemd 环境和登录态保持现值，不在示例里改。合并后按安装版支持的入口运行 `paseo reload`。Relay 是可选入口，部署不依赖它；需要手机经 Relay 连接时再运行 `paseo daemon pair --relay`。仓库根的 `paseo.json` 提供 worktree 初始化检查，以及 `smoke`、`select` 两个测试脚本。开始前确保 Paseo 进程的 `PATH` 能找到装有 PyYAML 的 Python 3.11+。各命令用 `env -i` 保留 `PATH`，测试还传入解析后的临时目录路径，在 macOS 上可处理系统的 `/tmp` 软链。
8. **隔离前缀角色验收**：在隔离前缀启动的 daemon 上，`--check` 一致后确认技能可以列出；逐一核对 CCHP、GDR 两套 LUNO/LENS/FORGE 六个 Profile，按 [Paseo 运行端规则](skills/luno-platform/references/runtime-paseo.md#派发通道) 回读实际 provider、启动解析模型、权限模式及同一活线程的 `codexRoleVerification`（`role`、`upstream`、`resolvedModel` 与三项标志）。六个 Profile 各发一次初始正式消息，证明校验在首个模型请求之前完成；异常绑定只允许零模型请求。草稿 Speed 只查能力。此步不动现役 systemd。
9. **可恢复切换与新现役回读**：隔离前缀验收通过且规则安装 `--check` 一致后，在同一维护窗口暂停新会话，把 systemd 单元的实际程序入口切到已验证的补丁包；`daemon-reload` 与重启由获准的系统服务操作者执行，不假定能以单元运行用户直接操作 systemd。重启后对新的现役 daemon 回读实际加载的包版本、配置、工作目录及全部已授权接收端，再运行最小新会话验收；daemon 配置与生成文件须在同一受控维护窗口切换并回读。失败立即恢复记录的旧入口并重新回读。安装器不切换包、systemd 单元或登录态。
10. **升级与回退**：下文 `LI` 代表第 5 步的安装器命令，`CO` 代表以运行用户执行的 `git -C <checkout>`。安装器不 fetch、不切换 Git、包或 systemd 单元，旧版与新版都要已在本地。
   - 预检：`CO fetch origin`，记下当前 HEAD 为旧版、`origin/main` 为新版，运行 `LI --preflight <新版>`。只有检出干净、现有安装一致、新版登记无冲突时才返回就绪；输出列出旧版、新版与将退役的入口。
   - 升级：`CO merge --ff-only <新版>`，再运行 `LI --apply --previous <旧版>` 与 `LI --check`。只退役旧版独有的公开软链和受管生成文件，目录、设置和登录态不动。`--apply` 中断时，可用同样的参数重跑完成升级；中断留下的暂存残留不参与判断，也不被清掉，按 `residue` 报告交你核对。
   - 首版只支持同布局：升级与回退要求两版的 `tools/link-install.py` 逐字节相同、并由登记推导出相同的公开入口目标。旧版登记先通过核验、进入这套兼容比较后，安装器一变（可能改变渲染路径）就在 `--preflight` 和 `--apply --previous` 写入前停止并报告 `installer_changed`，该停止码不与登记核验阶段的结果混用；同一公开入口目标不同报 `layout_changed`；旧版没有宿主端登记时报 `previous_without_host_installation`，已有宿主端登记但找不到旧版 `tools/link-install.py` 时报 `previous_installer_missing`。首版不承诺跨布局回退，也不迁移布局；维护窗口从 Git 切换前一直开到 `--check` 结束，期间暂停新会话。
   - 跨安装器只读准入：旧版 `--preflight` 报 `installer_changed`，但两版受管树相同（例如只改了 `tools/link-install.py` 的 override 检查）时，可从目标提交取出安装器原字节，在干净旧版检出上只读核对。入口自行从当前 HEAD 和目标提交的 Git 对象取两个安装器 blob，并绑定运行中的目标工具字节，不需手抄 blob。`CHECKOUT`、`INSTALL_HOME` 按实际根设置，`NEW` 取已核完整目标 SHA。在目标环境中按实际使用的每套参数各调用 `run_check` 一次，沿用现有 `--ends`、`--codex-home` 和 `--codex-global-source` 选择。下例为默认同时管理两端的安装。全部 rc0 才进入快进：

     ```sh
     CHECKOUT="$HOME/.luno/agent-sync"
     INSTALL_HOME="$HOME"
     NEW="已核完整目标 SHA"
     OLD=$(git -C "$CHECKOUT" rev-parse HEAD)
     git -C "$CHECKOUT" merge-base --is-ancestor "$OLD" "$NEW" || exit 1
     TMP=$(mktemp -d) || exit 1
     trap 'rm -f -- "$TMP/link-install.py"; rmdir -- "$TMP" 2>/dev/null || true' EXIT HUP INT TERM
     git -C "$CHECKOUT" show "$NEW:tools/link-install.py" > "$TMP/link-install.py" || exit 1
     run_check() {
       python3 -B "$TMP/link-install.py" --checkout "$CHECKOUT" --home "$INSTALL_HOME" \
         --check-installer-upgrade "$NEW" "$@"
     }
     run_check || exit 1
     ```

     入口要求旧版 HEAD 干净、旧版为新版祖先、运行中的目标工具字节等于 `$NEW` 的安装器；旧安装器执行自己的 `--check`，目标安装器按目标提交的登记和受管源核对同一实际根。同一旧版 HEAD 下每套参数的实际选择都必须通过；两版完整公开投影必须相同且目标每项 `match`，`prompt/`、`skills/`、`subagents/`、`tools/sync-targets.json`、`platforms/paseo/` 均未变，否则阻断。布局或受管源变更新增/退役项仍须该 PR 提供迁移与回退步骤，不能借此绕过。全部通过后在同一维护窗口只快进一次：`git -C "$CHECKOUT" merge --ff-only "$NEW"`；随后对每套参数逐一用新版 `--check`，任一失败立即 `git -C "$CHECKOUT" reset --keep "$OLD"` 并对所有选择重新检查。两版安装器相异时不得运行 `--apply`。普通 `--preflight` / `--apply --previous` 遇 `installer_changed` 仍按前条阻断，原升级、回退和首装撤回流程不变。更改安装器的 PR 合入前须在目标实际宿主上用旧版做上述只读预检，结果或迁移/回退步骤随 PR 记录；沿用现有流程，不为此新增 CI job。
   - 运行端退役（本仓库已移除 Claude Code 端及其安装器入口）：从含 Claude Code 登记的旧版跨到退役版，旧版 `--preflight <新版>` 会因新版登记缺 `claude-code` 键而按 `registry_end_missing` 停止，不进入安装器 blob 比较；新版 `--apply --previous <旧版>` 在正常前态会因安装器 blob 改变而按 `installer_changed` 在写入前停止。预检未就绪，不切换检出，不借普通 `--apply` 绕过，不套用首装撤回。若已切换或已有现场写入，先暂停新会话并核实际检出、已写项和可证前态，另按授权确定恢复或迁移方案。新装及安装器 blob 相同、共有公开软链目标不变的后续升级和回退，仍沿用原流程。遗留 Claude Code 入口不会由新版安装器渲染或删除，现场清理另行授权。
- 回退（升级失败或中断）：`CO reset --keep <旧版>`，再运行 `LI --apply --previous <新版>` 与 `LI --check`，清理新版独有的受管入口并恢复旧版的生成文件。这条只用于已核两版都有宿主端登记（旧版 `tools/sync-targets.json` 里已有 `codex`、`paseo` 端条目）、安装器 blob 相同且共有公开软链目标一致的同布局恢复；不满足这些前提时按上文相应条停在报告并先核实际检出与前态，不把首装撤回用于既有安装。
   - 首次安装的撤回：旧基线里还没有宿主端登记、也没有 `tools/link-install.py` 时，`--previous <旧版>` 表达不出任何退役项，安装器不会删除新版装上的文件，此时直接回退会留下新装与旧基线混合的状态。安全默认是保留新版安装器与已装入口，不撤回；确需撤回时，只按本次 `--apply` 报告 `created` 里 `state=create` 的项逐项核对归属：源链接按登记推导出的精确 target 核，生成文件按仍指向它的公开软链核（生成文件须同 UID、0600 且仍被对应公开软链指向，软链须指向本次生成文件）后删除这些项（先全部核完再删，生成文件在指向它的公开软链仍在时删除；源链接与生成文件分开核），`~/.luno/generated/`、`~/.luno/homes/*`、`~/.luno/memory/GLOBAL.md`、settings 与登录态一律保留；项数或归属对不上就停下交你处理，不删目录、不整目录删除；报告缺失、`created` 为空（例如刚成功的重跑）或无法区分是否本次新增时，只停不删，不拿计划项或前态已有的受管项充当本次新增。

### Codex GLOBAL 来源（可选）

默认的 `codex-main` 仍生成 `prompt/LUNO.md` 原文、一个 LF 和私人 GLOBAL 副本；其他端不变。只选 Codex 单端时，可显式加 `--codex-global-source paseo-append-system-prompt`：`AGENTS.md` 恰为 `prompt/LUNO.md` 原文，GLOBAL 改由 Paseo daemon 的 `daemon.appendSystemPrompt` 提供（Paseo 设置 → Host → Orchestration → System Prompt）。该选项只接受 `--ends codex`；默认同时选择 `codex`、`paseo` 时，不接受此 GLOBAL 来源选项。安装器不读写这份私人配置；设置与生成文件须在同一受控维护窗口切换，先暂停新会话，切换或回滚后回读再恢复会话。

该来源是 daemon 范围，不是单个 provider 的选项：Paseo 0.17.1（固定上游提交 `043f0995d4d7e91ab12f3eecef1afce055a81972`）的 agent-manager 会把 `daemon.appendSystemPrompt` trim 后附加到该 manager 启动的所有会话配置，Codex 作为 developerInstructions 接收。因此同一 daemon 启动的 LUNO、LENS、FORGE 及其他 agent 都在适用范围内，写前授权须覆盖该 daemon 的全部接收端；不要另加 provider 级过滤或自研注入。角色 home 的 `AGENTS.md` 仍仅角色正文，运行时另收这段提示词；选 daemon 来源时角色 home 仍按 `--ends paseo` 单独安装。回读时配置值按原始字节核对，实际交付按 trim 后口径理解；文件和配置匹配不等于实际加载，原生 CLI 不经该 daemon，不直接获得这段提示词。

首次接入时，安装器 blob 已变，旧的 `--preflight`/`--apply --previous` 跨 blob 尚未支持。现场已经改成 LUNO-only 且仍有旧 GLOBAL 副本时，用旧、新可信安装器对同一安装根和除来源选项外相同的入口参数只读 `--check`：旧安装器只把 `AGENTS.md` 列为 update，新安装器带 `--ends codex --codex-global-source paseo-append-system-prompt` 应全部 match；目标登记与 `prompt/LUNO.md` 均未变时，快进检出后只跑带选项的 `--check`，不运行 `--apply`。仍内嵌的现场沿用原版升级路径，但仅在该路径满足同布局前提（两版安装器 blob 相同、共有公开软链目标不变）时可用；从含 Claude Code 登记的旧版跨到退役版不满足该前提，按上文〈升级与回退〉的运行端退役条处理，不用作本次跨退役迁移。已迁移入口后续换版沿用同 blob 的 `--preflight`/`--apply --previous`（带同一来源选项），只重生成受管文件，不改安装器。

回滚时显式运行 `--ends codex --apply --codex-global-source agents-md` 与 `--check`，要求私人 GLOBAL 副本仍在；同一窗口恢复 daemon 设置，再核对旧组合。

## 独立原生 Codex（0.170.0）

此模式不迁移 paseo、会话或登录态，沿用原有秘密、审批和角色分工。主提示词源仍是 `prompt/LUNO.md`，LENS/FORGE 原文仍在受管检出 `subagents/`；保留原文不等于独立 Codex 已具备角色派发。MCP 非秘密配置可另按目标支持的现有接口预置；服务凭据独立授权，缺失不阻塞无依赖的提示词安装。本安装器不配置 MCP、不注入任何凭据，也不请求模型。

`--home` 是已存在的受管安装根，不改变进程 HOME。`--ends` 只选择登记端；省略时处理 `codex` 和 `paseo` 两端。`--codex-home` 仅允许与 `--ends codex` 合用，且须是安装根内的绝对目录：把登记 Codex 的全局入口映射到该目录的 `AGENTS.md`，把技能入口映射到该目录的 `skills/<名称>`；生成物和 GLOBAL 仍在安装根的 `.luno/` 布局中。登记对象、源文件与默认模板不变，不新增同步对象或私有实例登记。

实际 HOME 下的 `.agents/skills` 不随 CODEX_HOME 改变。此模式明确采用 0.170.0 仍支持、但已弃用的 `$CODEX_HOME/skills` 兼容根，避免改 HOME 或建立根外链接；版本变化必须重核，不承诺未来继续支持。对应官方源码与指令优先级见 `skills/luno-platform/references/runtime-codex.md`。要采用其他根或改 HOME，另定方案，不由安装器自动迁移。

先按 `skills/luno-core/references/sync.md`〔分支 sync-host〕准备已授权私人 GLOBAL 副本，再运行下列命令；路径变量均为本次明确核实的非秘密值，不是自动探测入口：

```sh
python3 -B tools/link-install.py --checkout "$CHECKOUT" --home "$INSTALL_ROOT" \
  --ends codex --codex-home "$CODEX_HOME"
```

计划无冲突后，在已有授权内同参数加 `--apply`，再加 `--check` 回读。该模式不检查、创建、删除或修复未选端的用户入口；登记结构仍整体校验。原有未受管占位、父目录软链、GLOBAL 缺失及实际 CODEX_HOME 下的 override 均在写前阻断。不会扫描实际 HOME、项目或其他技能根以排除全部同名对象；调用方须按明确范围核实际加载，不把离线匹配报告为模型行为实测。

GLOBAL 更新需重新 apply/check；没有私人复制授权或完整前态时停依赖部分。新参数与旧安装器 blob 不同，所以既有宿主端安装跨到此安装器版本时，原有 `--preflight` / `--apply --previous` 会按 `installer_changed` 停止；不绕过该门禁，也不借原生首装迁移既有安装。首装撤回和同布局恢复沿用上节规则，必须保留本次 create 报告；更换安装根或 CODEX_HOME 不是已支持的原位升级。

原生两角色（`subagents/LENS.md`、`subagents/FORGE.md`）的 Codex 落点是 `$CODEX_HOME/roles/{lens,forge}.toml`，由登记里的 `generated/codex-role` renderer 生成：`model`、`model_reasoning_effort`、`developer_instructions` 三键各一行，前者取该端登记的模型参数，后者是指令真源原文按 TOML basic string 转义的 UTF-8 字节（不 strip、不归一换行）。这两个文件**只在 `--ends codex --codex-home` 的显式布局启用**，默认两端布局不生成原生角色文件。注册（主 `config.toml` 的 `[agents.LENS]` / `[agents.FORGE]`，字段 `description`、`config_file`）和角色文件都是**只读前提**：plan/check 只核对，`--apply` 对相等文件仅 no-op，缺文件、缺注册、字段/类型/指向不符或正文漂移一律停止，不创建、不代修，没有首次接管记录也不把等字节的普通文件当成已接管。接管是零安装动作的检出升级：维护窗口内核 HEAD=旧版且干净，用旧版安装器自己的 `--check` 取投影，再用新版 `--check-native-role-adoption <新版> --adoption-blobs <旧blob>,<新blob>` 对同一实际根只读核对：绑定当前 HEAD=旧版、旧版为新版祖先、两版安装器 blob 与运行中的本工具字节哈希一致，并在独占临时目录执行旧版自己的 `--check`，把它的完整动作投影与新计划逐项比对（只准两个角色文件与已有目录的 match 增量，旧项缺失或改指即停）；不写文件、不 fetch、不切版本。角色 renderer 按 TOML basic string 转义生成三键，不另做生成物复核；注册只按已核现有布局逐行定位两个受管表，标准库 `tomllib` 只解码 `description`、`config_file` 的单行 basic string 值，不整份解码主 `config.toml`，因此需 **Python 3.11+**，随后只 ff-only 到新版并跑新版 `--check`。已经接管的同布局更新沿用 check→`--preflight`→ff→`--apply --previous`→check，只有现场旧文件全字节等于上一登记版本的渲染结果时才改写角色文件；失败按已记录版本回读角色文件、注册与共同入口，不反向跨 blob apply，也不删除文件。准入失败或中断时保留原检出与未写文件，不删除角色文件、不改注册；恢复只按已记录的旧/新两态各自原字节进行，第三态交负责人。

## Paseo 共享角色体系

`platforms/paseo/config.example.json` 只保留两个共享 Codex provider：`cchp`（CCHP）与 `gdr`（GDR），
各承载 LUNO、LENS、FORGE 一个 Profile，共六个。Profile 用 `options.paseo_role` 与
`options.paseo_upstream` 声明角色和上游，不再使用 `notes` 路由。示例中的模型、思考强度、模式和
`service_tier` 是可编辑初值，不表示所有上游已验证支持；实例只合并获准条目，不能整表覆盖现有配置。

- CCHP 的 LUNO、LENS 默认 Normal（`service_tier: "default"`），可在客户端选择 Fast/Ultrafast；
  CCHP FORGE 使用 `deepseek-flash`，不写 `service_tier`，在 Normal/Flex 中选择；GDR 三个 Profile
  默认 Ultrafast。
- 两个 provider 的 `env` 固定主 Codex home、LUNO 角色原文和各自上游，并设置
  `PASEO_CODEX_ROLE_SHARED=1`、`PASEO_CODEX_ROLE_REQUIRED=1`。缺少插件启动绑定时会话失败，
  不会退回未核验的默认角色。
- 角色家目录仍是登记里的 `lens-codex`、`forge-codex`、`lens-gdr`、`forge-gdr`；这些是目录名，
  不是 provider ID。LUNO 使用主 Codex home。四个 LENS/FORGE 家目录的 `config.toml` 需要：

  ```toml
  [agents]
  enabled = false

  [features]
  multi_agent_v2 = false
  ```

  LUNO 家目录不加这两项。安装器只建立角色 home 和技能链接，不改写 `config.toml`。

### 插件与派发

`platforms/paseo/plugin` 是共享角色插件：`agent.create.before` 从 Profile 的
`options.paseo_role`、`options.paseo_upstream` 校验并持久化绑定，`agent.open.before` 从绑定推导
`CODEX_HOME`、角色原文和预期上游。安装时复制该目录到实例的插件目录，用 Paseo 官方插件设置启用
（`pluginsEnabled` 与目录来源）；插件路径是公开占位值，实际值按现场替换。本仓库不提供自动安装、
迁移或切换脚本。

编排每次派发用官方 `list_profiles` 读取当前 Profile，按主会话已核上游选同 `provider`、
同角色、同上游的唯一 Profile，把 `provider/model`、`modeId`、`thinkingOptionId` 和
`options`（`settings.features`）传给 `create_agent`，正式任务只用一次 `initialPrompt`，不另发
启动探针。宿主在首个模型请求前核对同一活线程的 `codexRoleVerification`：`role`、`upstream`、
`resolvedModel` 与 `roleMatches=true`、`overrideExists=false`、`upstreamMatches=true` 全部匹配；
缺证、错配或异常时零模型请求。状态表里的配置模型和角色自述不能代替这份证据。

桌面前台直接新建只有在未选 Profile 且两个路由字段都不存在时，由服务端默认当前上游 LUNO；
显式选择 Profile 以 Profile 的角色为准；只给一个字段、两者错配或编排缺失仍拒绝。客户端路径由
服务端默认补全，编排路径仍须显式选择 Profile，两条路径分别验收。

协议边界：创建请求不携带 Profile ID；客户端把 Profile 展开成 draft 设置，服务端无法区分「未选
Profile」与「所选 Profile 两个路由字段均缺失」。因此配置验收须逐一确认六个共享 Profile 都声明
有效角色和与 provider 一致的上游，并确认两个字段随创建请求进入 `providerOptions`；不把服务端
默认当成对坏 Profile 的拒绝。

草稿 Speed 只使用 provider 已登记的固定启动信息查询能力，不启动线程、不投消息；回读六个 Profile
的真实速度选项后，真实会话仍走上面的角色门禁。

### 构建、切换与回退边界

补丁基线是固定上游提交 `043f0995d4d7e91ab12f3eecef1afce055a81972`（v0.17.1），修改服务端
`session.ts`、`agent-manager.ts`、`agent-projections.ts`、`agent-sdk-types.ts`、
`provider-registry.ts` 与 `agent/providers/codex-app-server-agent.ts`，包含共享角色校验、
桌面前台默认、草稿 Speed 和调用方 env/metadata 隔离。来源、固定提交和许可核验登记见
[skills-sources.md](skills-sources.md#paseo-服务端补丁)。

先核基线、应用补丁并按官方入口构建：

```sh
set -eu
SRC="/absolute/path/to/paseo-0.17.1-src"
PATCH="/absolute/path/to/agent-sync/platforms/paseo/codex-role-verification-v0.17.1.patch"
test "$(git -C "$SRC" rev-parse HEAD)" = 043f0995d4d7e91ab12f3eecef1afce055a81972
git -C "$SRC" apply --check "$PATCH"
git -C "$SRC" apply "$PATCH"
(cd "$SRC" && set -eu && npm ci && npm run build:server)
```

在与现役前缀分离的 npm 前缀装入同版本包，回读版本后再覆盖构建产物：

```sh
set -eu
SRC="/absolute/path/to/paseo-0.17.1-src"
PREFIX="/absolute/path/to/isolated-prefix"
npm install --prefix "$PREFIX" --no-audit --no-fund @getpaseo/cli@0.17.1 @getpaseo/server@0.17.1
node -e "const [p]=process.argv.slice(1); for (const n of ['@getpaseo/cli','@getpaseo/server']) console.log(n, require(p+'/node_modules/'+n+'/package.json').version)" "$PREFIX"
cp -a "$SRC/packages/server/dist/." "$PREFIX/node_modules/@getpaseo/server/dist/"
cp -a "$SRC/packages/cli/dist/." "$PREFIX/node_modules/@getpaseo/cli/dist/"
"$PREFIX/node_modules/.bin/paseo" --version
```

完整 monorepo 构建超出本端资源时，可用官方 TypeScript（本批为 5.9.3）按
`packages/server/tsconfig.server.json` 的 `target: ES2020` 和 ESM 输出，配合 `esModuleInterop`、
`isolatedModules` 对补丁触及的 TS 文件逐文件 `transpileModule`（单文件转译用 `module: ESNext`，
`NodeNext` 在无包上下文的转译中会输出 CJS），按 `dist/server/server/...` 路径覆盖同一 0.17.1 npm
前缀的 dist。该缩小路径只证明触及文件进入运行集；它不替代
`npm run build:server`、`typecheck:server` 或真实角色验收。覆盖后须在隔离 `PASEO_HOME`、回环端口
和临时 HOME 下用该前缀运行端到端 fixture，并回读 `@getpaseo/cli`、`@getpaseo/server` 的 `0.17.1`
版本和构建产物里的共享角色标记。

现役宿主是 npm 安装并由 systemd 托管：确认旧前缀、旧 `config.json` 和四个角色 home 的
`config.toml` 都可恢复后，再切换 systemd 单元的程序入口并重启一次。`paseo reload` 只重读配置，
不能加载本补丁的代码，不能当作代码切换。切换前暂停新会话；切换后回读新进程实际加载的包版本、
配置和六个 Profile 的角色证据。

回退与会话边界：早期宿主迁移把获准的旧 LUNO 记录的 `provider`、`runtimeProvider` 和
`persistenceProvider` 映射到 `cchp`/`gdr`，保留原 agent ID 和 `sessionId`，并只对这笔无绑定的
记录用 `PASEO_ROLE_LEGACY_AGENT_IDS` 精确配对。未完成该迁移时直接切入口会让旧 `luno-*` provider
的 ID 失效。回退时把单元指回旧前缀、恢复旧 `config.json`、移除插件，并同时恢复受影响的旧记录到
迁移前态；四个旧 worker 家目录按记录的原字节恢复 `config.toml`。切换后新建的共享角色记录在旧前缀
接管前必须隔离或归档，避免旧 ID 把新绑定会话当 LUNO 打开。持久化会话可能保存运行时注入的提示词，
回退设置不会清除历史。公开文档不提供迁移脚本、名单或现场路径。

## 测试与历史

用法、选路及白名单环境见 `tests/run-tests.sh` 头部与实现；准入和成本见 `skills/luno-core/references/test-authoring.md`。结构守卫退出码见 `tools/check-rules.py` 头部；测试将任何非零记为失败，`sync-all.sh` 只阻断 rc=1/3。结构通过不代替行为审查。

仓库根的 `paseo.json` `select` 以 `git merge-base origin/main HEAD` 为基线，对当前 Git 工作树的 tracked diff（`--no-renames --no-ext-diff --no-textconv -z`）选路，因此未提交的已跟踪修改也会命中；新增文件必须先 `git add` 才会进入该 diff，CI 仍按已提交的 B→M 差分选路。

CI（`.github/workflows/tests.yml`）只用一个 job 和一个 `selected` 步骤，选路表与测试都取受测 checkout：`pull_request` 以事件 base 为 B、merge 提交为 M，显式检出 M 后核 HEAD=M 且 M 的双亲恰为 [B, head]，取 `git diff B M` 并测试 M（base 自己前进不算 PR 变化，冲突 PR 无合并结果）；`push` 取 before→after。事件值经 env 传入并校验事件名与 40 位 hex，diff 以 NUL bytes 经 `select-paths` 内存串接，缺对象、全零或上游失败都阻断，不静默 fetch、不以空树或 full 兜底。运行器、选路表或该 workflow 变更命中所有把 runner 当消费者的组，与 full 取并集后为登记表展开的全部入口各跑一次；普通未映射正文仍只跑 smoke。

运行器一轮输出即原证：轮首打印 HEAD、tree、git 版本和 trackedState，每入口 BEGIN 记 name/group，stdout/stderr 原 bytes 合并流式输出（不截断、不加前缀、不重打），END 记原始 exitCode、unittest 摘要的 tests/skip（非 unittest 或摘要缺失分别记 N/A、unavailable）和单调耗时。聚合退出码：全成功 0、测试失败 1、选路/环境/基础设施或清理失败 2，原始子进程退出码始终保留；INT/TERM 清理后 130/143。WORK 由 `mktemp` 在 TMPDIR 排他创建并在本轮 nofollow 核验后删除，不落持久日志、不建证据平台；调用方获准后自行保存本轮 stdout/stderr 与进程退出码。

批次结果只记当批 PR，历史以 git 为准；公开快照未导入旧私有 `LucaLin233/Agent` 历史。技能合并与资源迁移见提交 `484de55052413ef2004d5e588d5a0540bcf88826`（六技能）和 #43（记忆并入 luno-platform、CCHP 官方件入包）。

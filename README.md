# Agent-Sync

LUNO 提示词、技能与子代理的版本化资产。Minis/LobeHub 与已授权宿主 CLI 是运行端，仓库是管理落点；合并不等于部署，`present` 不等于已回读。记忆各端自持。

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

## 技能专项离线验收

`tools/lh-verify.py` 把一次 LobeHub 技能专项观察记录与**同一提交**的仓库原字节对账；只读、无网络、无写入。

```sh
python3 -I -B tools/lh-verify.py --repo REPO --git-version <40位小写hex> \
    --object luno-ops [--object …] --evidence evidence.json
```

- **输入**：固定严格 JSON，下表所列键均必需且只接受这些键；任意层重复键、多余键、错类型、非有限数值 rc=2，缺必需字段 rc=3。`projection` 的四个可空字段区分缺键、`null`、空串，禁止互相代填；stdout/stderr 必须保存原字符串，不接受解析后的对象。

| 层级 | 必需键及类型 |
| --- | --- |
| 根 | `schemaVersion`：整数 `1`；`observation`：对象；`objects`：对象数组 |
| `observation` | `id`、`instanceRef`、`sourceVersion`、`sourceBasis`：非空字符串；`startedAt`、`finishedAt`：UTC时间字符串 |
| `objects[]` | `object`、`observationId`、`instanceRef`：非空字符串；`projection`：对象；`resourcePaths`：路径字符串数组；`calls`：调用对象数组 |
| `projection` | `id`：非空字符串；`name`、`description`、`identifier`、`content`：字符串或 `null` |
| `calls[]` | `observationId`、`instanceRef`：非空字符串；`request`：对象；`exitCode`：整数 `0` 或 `2`；`stdout`、`stderr`：字符串，允许空串 |
| `request` | `id`、`path`：非空字符串 |

UTC时间须为有效的 `YYYY-MM-DDTHH:MM:SSZ`（秒精度、无小数），结束不早于开始。对象及调用的 `observationId`、`instanceRef` 须分别等于顶层 `observation.id`、`observation.instanceRef`。命令的 `--object` 范围须非空；证据 `objects` 可为空，缺所选对象为 rc=3，含未选对象为 rc=2；对象和资源路径不得重复，同一对象的调用以 `(request.id,request.path)` 为唯一键。路径字符串非空；`resourcePaths` 可空，但必须是现场完整相对路径集合；`calls` 为登记集合与该集合交集内每个 `(id,path)` 各一条，多余资源只列路径、不提交正文。`sourceBasis` 仅是外部依据的定位引用，字段齐全不证明来源真实或无并发。

下面是完整结构示例，所有业务标签和内容均为虚构；实际必须按指定提交登记和当次可信观察填充，不表示真实现场或 PASS。

```json
{
  "schemaVersion": 1,
  "observation": {
    "id": "o",
    "instanceRef": "i",
    "sourceVersion": "v",
    "startedAt": "2026-11-15T08:00:00Z",
    "finishedAt": "2026-11-15T08:00:01Z",
    "sourceBasis": "basis-ref"
  },
  "objects": [
    {
      "object": "example-skill",
      "observationId": "o",
      "instanceRef": "i",
      "projection": {
        "id": "skill-example",
        "name": "example-skill",
        "description": "示例描述",
        "identifier": "example-identifier",
        "content": "示例正文\n"
      },
      "resourcePaths": [
        "references/example.md"
      ],
      "calls": [
        {
          "observationId": "o",
          "instanceRef": "i",
          "request": {
            "id": "skill-example",
            "path": "references/example.md"
          },
          "exitCode": 0,
          "stdout": "{\"ok\": true, \"action\": \"skill-resource\", \"resource\": {\"content\": \"abc\", \"encoding\": \"utf8\", \"fileHash\": \"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad\", \"fileType\": \"text/plain\", \"path\": \"references/example.md\", \"size\": 3}}\n",
          "stderr": ""
        }
      ]
    }
  ]
}
```

成功调用如上：`exitCode=0`、stderr为空，stdout是原成功 JSON字符串并保留末尾 LF。失败调用保持相同关联字段，改为 `exitCode=2`、`stdout=""`，stderr保存固定错误 JSON原字符串，例如 `"{\"ok\": false, \"error\": \"transport_error\"}\n"`；未知错误码不透传。响应仍须满足六字段的类型、编码和自洽性，详见“固定认证读取”。缺交集调用为缺证；完整集合中缺登记资源是差异，不能补造成功记录。
- **对象**：只取该提交 `tools/sync-targets.json` 里 `type=skill` 且 `ends.lobehub.present=true` 的项；`projection.id` 比登记的 LobeHub ID，不等即身份差异并停止该对象内容比较；`request.id` 必须等登记 ID，`response.path` 必须等 `request.path`，不靠 path 猜 ID。
- **判据**：完整 `resourcePaths` 与登记集合先比（登记有、现场无 → 差异；现场多 → 只报告，不接受其正文记录、不扩读）；`name`/`description` 用同提交 `SKILL.md` 的 `fm_get`，`content` 用 `body_contract.body_bytes`（不 strip、不补尾换行、CRLF 不归一）；资源按**原字节**比较；每条记录核结构、编码、`size`、`fileHash`（失败记录只认固定码，未知文本不透传）。`identifier` 仅覆盖已确证五技能：同版 `name`=对象 ID 且 `installSource` 恰为 `https://github.com/LucaLin233/Agent-Sync/tree/main/skills/<ID>` 时期望 `lucalin233-agent-sync-<ID>`，否则记缺证。
- **Git**：`shell=False`、白名单环境，禁 global/system 配置、optional locks、fsmonitor、replace objects、lazy fetch；只认完整本地仓，缺对象即停，不 fetch 修复。
- **输出**：stdout 一份 JSON（`gitVersion`/`status`/`objects`/`missingEvidence`/`errors`），不输出正文或元数据值。退出码 0 匹配 / 1 确证差异 / 2 参数、格式、执行或已记录读取错误 / 3 缺证，并存按 2>3>1>0。
- **边界**：工具只证结构与字节一致。真实实例、源端版本、采集侧投影、资源集合完整性、记录真实性和无并发须由当次可信调用方在外部核准；`sourceBasis` 只是依据定位引用，不打开也不当批准或真实性证明；标签一致的伪造记录仍可能 rc=0。写前写明旧提交与新观察，写后对合并提交另做一次观察，否则只能看出可观察路径/bytes 差异。

专项：`sh tests/run-tests.sh case test-lh-verify.py`，不进 full；跑集另含依赖变更命中的 verify 消费者选路。

### Minis 本端只读验收

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

技能包通过已锚定目录 fd枚举，比较主文件／资源及隐含父目录集合。多余普通文件只取元数据，不打开内容；多余目录可继续作目录元数据枚举，不读其中文件正文；不跟随任何软链。单包枚举上限为10,000个条目、64层、累计路径字节1,000,000 B；超限 rc3。多余空目录同样报告额外路径，不以 Git未记录空目录为由忽略。

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

## LobeHub 窄采集与窄部署（首版）

两个薄工具，`python3 -I -B`；`lh-collect` 仅标准库，`lh-deploy` 另需 PyYAML（正文契约 `tools/body_contract.py` 的依赖，缺依赖按执行错误 rc2 停止）。它们只覆盖已登记对象的采集与部署，不是通用同步、通用 SSH/SQL/HTTP 入口。

```sh
python3 -I -B tools/lh-collect.py --repo REPO --object ID [--object …] --git-version FULL_SHA \
    --out-dir NEW_DIR --instance-ref LABEL --source-basis REF --source-version TEXT \
    [--total-timeout 180] < target.json
python3 -I -B tools/lh-deploy.py --repo REPO --object ID [--object …] --base FULL_SHA \
    --merged FULL_SHA --out-dir NEW_DIR --instance-ref LABEL --source-basis REF \
    --source-version TEXT [--total-timeout 180] < target.json
```

- **来源版本**：两工具必填`--source-version TEXT`，提供调用方本批已核的实际应用来源版本；真实性与sourceBasis同由调用方负责。工具只转录，不自动发现或证明版本。不得以PG版本、待比较Git提交或固定历史版本代替；来源未核时不得启动现场执行。`lh-deploy` 把该值原样传给每次 pre/post 采集，`lh-collect` 原样写入 `observation.sourceVersion`，不被 `--git-version`/`--base`/`--merged` 覆盖。
- **准入**：`--object` 取该提交 `tools/sync-targets.json` 的顶层 `id`；只接 `ends.lobehub.present=true`。技能须 `type=skill` 且 `ends.lobehub.kind=skill`，Agent 须 `type=prompt|subagent`、`kind=agent`、`field=systemRole`。`--git-version`/`--base`/`--merged` 只接受 40 位小写 hex 的本地 commit，不 fetch、不隐式解析 HEAD/tag/tree。`--out-dir` 必须不存在，排他建 700 目录、600 文件。`target.json` 只在内存使用（根键 `ssh`/`postgres`，固定子键，端口为 1..65535 整数），不落盘、不回显，不接收 query/command/凭据。
- **采集**：只读事务内用固定列取技能的 `id/name/description/identifier/content` 与资源**实际完整键**，文本经 base64 还原严格 UTF-8（不 strip、不归一 CRLF 或尾 LF）；资源正文只按「登记 ∩ 实际」逐路径走 `tools/auth-call.py skill-resource`，原 `stdout`/`stderr`/`exitCode` 原样写入 `skill-evidence.json`（`schemaVersion=1` 全键），另一份 `projection-source.json` 只存安全投影。额外资源只报告、不读正文。
- **Agent**：`lh-collect` 对 `kind=agent` 的登记对象按 ID 取固定投影——`agents` 表的 `id/user_id/workspace_id/system_role`，谓词 `id = :'obj_id' AND is_deleted IS NOT TRUE`（软删除列可空，不用 `=false`），`system_role` 经 base64 严格还原 UTF-8 且保留 `null` 与空串差别，写入 `agent-evidence.json`（`schemaVersion=1/observation/objects`，对象固定 `object/observationId/instanceRef/id/field/value`，`field` 仅 `systemRole`）。不读取默认配置、知识关联或任何凭据列，不新增 scope/绑定参数。`lh-deploy` 对 Agent 先做完整 pre 采集并严格核唯一对象、ID、`field` 与观察关联，再按 `body_contract.body_bytes` 比较 UTF-8 bytes；不等即 `pre_difference` 零写。相等后只调用官方 `lh agent edit <id> --config-file <600 新文件>`（JSON 仅含 `systemRole`，正文按 argv 原样传），写后对 `merged` 重新采集并按 bytes 复核，相等才 `completed`；Agent 差异不自动纠正，也不进 `lh-verify` 比较器。**运行前提（人工，不由工具证明）**：同实例/账户 scope/所选 ID 归属，以及当前实例该 Agent 的有效 `systemRole` 与存储 `system_role` 等价，须由负责人本批核实并记录；本仓库只提供离线链，不声称当前实例已验证。
- **部署**：无凭据阶段先核两版登记的身份、`type`、`kind`、LobeHub ID、`source`、`installSource` 相同、资源只增不减、旧 blob 完整可读，并匿名核安装分支 HEAD 等于 `--merged`；随后新建 pre 观察（`lh-collect` + `lh-verify`）对 `base` 验收，**任意非 0 零写**；通过后紧邻执行官方 `lh skill install <installSource>`；写后再核分支 HEAD，仍以新建 post 观察对 `merged` 验收。首错后其余对象 `not_run`，不自动重投、不回滚，只有 post 通过才 `completed`。
- **退出码**：采集 0 完整 / 2 参数、格式、执行、不安全出口或读取错误 / 3 缺证或未核准前提。部署 0 全部 post 通过 / 1 确证差异 / 2 执行、格式、写失败、超时或清理失败 / 3 缺证或首版不支持，并存按 2>3>1>0。stdout 各一份摘要 JSON（`schemaVersion=1/status/objects/errors/artifacts/cleanupResiduals/notCovered`），stderr 只固定码。
- **截止与清理**：每对象硬截止 `D=开始+T`，采集、验收、写入只用 `W=D-2`（2 秒固定留给清理，不挪用）；`T<=2` 仍是合法输入，但在读凭据值、建钥根或起子进程前返回 `timeout`/rc2。`lh-deploy` 调 `lh-collect` 时另传两个**工具内部私有参数**，不是用户绑定接口（帮助不列出，调用方不得依赖）：`--_parent-deadline D`（子对象硬截止取 `min(自身开始+T, D)`）与 `--_cleanup-fd N`（只继承本次清理通知管道写端，子进程里 ssh/postgres 的 stdin 不变）。子进程只在根已创建且核定身份后、写钥之前发一条 `{"event":"key_root","root":"…"}`，清理完成后发一条 `{"event":"cleanup","residuals":[…]}`。父进程执行超过 W 先发 SIGTERM 等子清理到 D，仍不退才强杀本次独占进程组；强杀或缺 `cleanup` 确认不声称已清理。子进程对 SIGTERM/SIGINT 只记取消标志并终止已登记的活动 ssh/auth-call，在安全检查点以内部 `Cancelled` 结束并映射 `timeout`/rc2，不被普通异常处理吞掉；每对象先进入 `try/finally` 再建根、写钥，并在同一路径关闭钥根后才处理下一对象。
- **新增摘要字段**：两工具摘要只新增默认空数组 `cleanupResiduals`，元素固定 `{"path": "/tmp 下本次随机根或其 id", "status": "remaining|unverified"}`：`remaining` 表示确定仍在用，`unverified` 表示身份、删除或清理未核，已确认删除的不列入。只含本次登记的非秘密临时路径，不含材料或连接坐标；父强杀且缺 `cleanup` 确认时按先前的根记录列根与 id 为 `unverified`，不扫描 `/tmp`、不猜名、不代删。`cleanup_failed` 且 `cleanupResiduals` 为空表示根登记前就异常终止（该窗口尚未写钥），清理未核且未取得根路径。

- **未覆盖（首版明确不做）**：资源退役、删除重装、ID 变化、自动登记、新装未登记对象、任意 SQL/命令/HTTP、通用 SSH 框架、GH 合并、跨端聚合、持久发布状态机、自动回滚、行为评测；post 阶段唯一的纠正例外是：verify 原 JSON 的差异恰为 `content`、无错误/缺证/资源差异，且现场 `content` 的 bytes 恰等于期望正文去掉一个尾 LF 时，按 argv 原样传全文补一次 `lh skill edit`，随后全量重采并复验；其余差异只报 `post_difference`，不报成功。首版没有平台 CAS，不保证不存在外部并发。
- **运行时前提**：SSH 只做代码内固定只读查询（`-F none`、`BatchMode=yes`、`StrictHostKeyChecking=yes`、`IdentitiesOnly=yes`、`IdentityAgent=none`、明确 `known_hosts` 与总截止时间），私钥只在获准的秘密落盘授权下用独占 `/tmp` 700 根/600 文件承载并在退场重核身份后清理；本次未使用任何秘密，也未连现场。结构化验收不证明现场安全或行为一致。

专项测试（不进常跑）：`sh tests/run-tests.sh case test-lh-collect.py`、`sh tests/run-tests.sh case test-lh-deploy.py`；选路见 `tests/run-tests.sh` 头部。

## 宿主端安装（Docker Compose 运行的 paseo 与 Codex）

宿主端是 Debian 主机上用 Docker Compose 运行的 paseo 容器；Codex 在容器内以非 root 用户 `paseo`（uid/gid 1000）运行，`~` 即容器内的 `/home/paseo`（持久卷）。规则与流程按 `skills/luno-core/references/sync.md`〔分支 sync-host〕，各端机制见 `skills/luno-platform/references/runtime-host.md`、`runtime-codex.md`、`runtime-paseo.md`。下文的 `dc` 代表在部署目录执行的 `docker compose`，容器内命令都用 `dc exec --user paseo paseo …`。

1. **构建与启动**：主机先装好 Docker Engine 与 Compose 插件。在仓库外建部署目录：`platforms/paseo/compose.example.yaml` 复制为其中的 `compose.yaml`，`platforms/paseo/Dockerfile` 复制到其中的 `build/` 子目录（构建上下文只有 `build/`，env、登录态和工作区都不进入构建）；同目录建立只由你维护的 `paseo.env`（权限 600），写入 `PASEO_PASSWORD`。确认 `./paseo-home`、`./workspace` 归属 uid/gid 1000 后，运行 `dc up -d --build`。`./paseo-home` 会保存各端登录态和凭据，部署目录不要放进任何 Git 仓库，也不要同步或分享。端口只绑定 `127.0.0.1:6767`，主机外的访问入口自选（Relay 只是可选项，见第 6 步）。不要挂载 Docker socket，不用 host 网络，也不开特权模式。
2. **受管检出**：`dc exec --user paseo paseo git clone https://github.com/LucaLin233/Agent-Sync.git /home/paseo/.luno/agent-sync`。之后只快进到已合并的 main（升级失败时的回退见第 8 步），不在其中编辑。
3. **GLOBAL 副本**：把 Minis `GLOBAL.md` 整份复制到主机上的 `./paseo-home/.luno/memory/GLOBAL.md`（即容器内 `~/.luno/memory/GLOBAL.md`，属主 1000，权限 600）。缺这个文件时安装器在预检阶段报错，不做任何写入。以后 GLOBAL 更新时，复制后再运行一次 `--apply` 与 `--check`，重新生成 Codex 常驻文件。宿主经验日志的创建、检索和共享见 [宿主端记忆入口](skills/luno-platform/references/runtime-host.md#记忆入口)。
4. **安装与核对**：`dc exec --user paseo paseo python3 -B /home/paseo/.luno/agent-sync/tools/link-install.py --checkout /home/paseo/.luno/agent-sync`。默认只列计划，确认后加 `--apply` 写入，用 `--check` 回读。安装器按 `tools/sync-targets.json` 的 `codex`、`paseo` 端登记，建立以下内容：技能软链；`~/.luno/generated/` 下的生成文件及其公开软链（`~/.codex/AGENTS.md`）；登记的角色家目录（包括既有 `~/.luno/homes/{lens,forge}-codex/`、`{lens,forge}-gdr/` 及配置示例的角色落点）。它不读取、不复制凭据和登录态，不改写已有的 settings 或 config；遇到非受管文件占位、经非受管软链的路径、没有对应公开软链的生成文件、角色家目录属主或权限（700）不符，或主会话与 `lens-codex`、`forge-codex` 家目录中有遮蔽常驻提示词的 `AGENTS.override.md` 时，停止并报告，不覆盖这些文件。生成文件先在同一目录以本次运行独占的随机名排他创建暂存文件，再改名或链接成正式文件，所以中断时正式文件保持原样；暂存残留的归属无法证明，安装器不清理也不判断，只在报告 `residue` 里按前缀列出（含旧版固定名 `.<文件名>.link-install.tmp`），由用户核对后自行删除。`--apply` 成功时报告的 `created` 只列本次实际执行过的项及其 `state`（`create` 新建、`update` 覆盖），计划里没有执行的项不列入，已一致的重跑为空。
5. **登录**：主会话执行 `dc exec -it --user paseo paseo codex login`。使用登录态的角色家目录各登录一次；使用 `env_key` 的角色沿用当次获准注入，不要求另行登录。例如 `dc exec -it --user paseo -e CODEX_HOME=/home/paseo/.luno/homes/forge-codex paseo codex login`。登录态保存在持久卷中。
6. **paseo 配置**：从 `platforms/paseo/config.example.json` 选择本次获准的 `daemon.mcp`、provider 与 Profile 条目，保全其他现值后合并进 `./paseo-home/.paseo/config.json`。监听地址由镜像环境变量决定，不在这里改。合并后运行 `dc exec --user paseo paseo paseo reload`。Relay 是可选入口，部署不依赖它；需要手机经 Relay 连接时再运行 `dc exec -it --user paseo paseo paseo daemon pair --relay`。仓库根的 `paseo.json` 提供 worktree 初始化检查，以及 `smoke`、`select` 两个测试脚本，三者都从最外层以最小环境（`env -i`，只给 `PATH` 与 `TMPDIR`）启动。
7. **验收**：`--check` 一致后，新开会话确认技能可以列出。默认 Compose 的 Codex 角色由 Paseo 派发。逐一核对获准启用的 CCHP、GDR LENS/FORGE 入口，按 [Paseo 运行端规则](skills/luno-platform/references/runtime-paseo.md#派发通道) 回读实际 provider、启动解析模型、权限模式及角色证据，再派无私人材料的验收任务。GDR 新角色家目录按下文逐项核查 `AGENTS.override.md`，并核角色 provider 的 `env` 实际覆盖镜像里的家目录变量。
8. **升级与回退**：下文 `LI` 代表第 4 步的安装器命令，`CO` 代表 `dc exec --user paseo paseo git -C /home/paseo/.luno/agent-sync`。安装器不 fetch、不切换 Git，旧版与新版都要已在本地。
   - 预检：`CO fetch origin`，记下当前 HEAD 为旧版、`origin/main` 为新版，运行 `LI --preflight <新版>`。只有检出干净、现有安装一致、新版登记无冲突时才返回就绪；输出列出旧版、新版与将退役的入口。
   - 升级：`CO merge --ff-only <新版>`，再运行 `LI --apply --previous <旧版>` 与 `LI --check`。只退役旧版独有的公开软链和受管生成文件，目录、设置和登录态不动。`--apply` 中断时，可用同样的参数重跑完成升级；中断留下的暂存残留不参与判断，也不被清掉，按 `residue` 报告交你核对。
   - 首版只支持同布局：升级与回退要求两版的 `tools/link-install.py` 逐字节相同、并由登记推导出相同的公开入口目标。安装器一变（可能改变渲染路径）就在 `--preflight` 和 `--apply --previous` 写入前停止并报告 `installer_changed`；同一公开入口目标不同报 `layout_changed`；旧基线没有宿主端登记或没有安装器时报 `previous_without_host_installation`。首版不承诺跨布局回退，也不迁移布局；维护窗口从 Git 切换前一直开到 `--check` 结束，期间暂停新会话。
   - 运行端退役（本仓库已移除 Claude Code 端及其安装器入口）：旧部署里的 `~/.claude/`（`CLAUDE.md`、`agents/*.md`、`skills/*`）、`~/.luno/generated/claude-code/` 与 `~/.luno/homes/{lens,forge}-claude/` 已不在登记中，新版安装器不再渲染、也不会删除它们；安装器 blob 随之改变，`--preflight` 与 `--apply --previous` 会在写入前按 `installer_changed` 停止。清理这些遗留入口属于现场操作，须另行授权后按精确路径逐项核对归属再删，不能借用安装器。
- 回退（升级失败或中断）：`CO reset --keep <旧版>`，再运行 `LI --apply --previous <新版>` 与 `LI --check`，清理新版独有的受管入口并恢复旧版的生成文件。这条适用于两个宿主版本都已登记宿主端（旧版 `tools/sync-targets.json` 里已有 `codex`、`paseo` 端条目）的情形；旧代码看不到新版渲染布局时按上一条停在报告，改按下面首装撤回处置。
   - 首次安装的撤回：旧基线里还没有宿主端登记、也没有 `tools/link-install.py` 时，`--previous <旧版>` 表达不出任何退役项，安装器不会删除新版装上的文件，此时直接回退会留下新装与旧基线混合的状态。安全默认是保留新版安装器与已装入口，不撤回；确需撤回时，只按本次 `--apply` 报告 `created` 里 `state=create` 的项逐项核对归属：源链接按登记推导出的精确 target 核，生成文件按仍指向它的公开软链核（生成文件须同 UID、0600 且仍被对应公开软链指向，软链须指向本次生成文件）后删除这些项（先全部核完再删，生成文件在指向它的公开软链仍在时删除；源链接与生成文件分开核），`~/.luno/generated/`、`~/.luno/homes/*`、`~/.luno/memory/GLOBAL.md`、settings 与登录态一律保留；项数或归属对不上就停下交你处理，不删目录、不整目录删除；报告缺失、`created` 为空（例如刚成功的重跑）或无法区分是否本次新增时，只停不删，不拿计划项或前态已有的受管项充当本次新增。

### Codex GLOBAL 来源（可选）

默认的 `codex-main` 仍生成 `prompt/LUNO.md` 原文、一个 LF 和私人 GLOBAL 副本；其他端不变。只选 Codex 单端时，可显式加 `--codex-global-source paseo-append-system-prompt`：`AGENTS.md` 恰为 `prompt/LUNO.md` 原文，GLOBAL 改由 Paseo daemon 的 `daemon.appendSystemPrompt` 提供（Paseo 设置 → Host → Orchestration → System Prompt）。该选项只接受 `--ends codex`，默认三端会在写前阻断。安装器不读写这份私人配置；设置与生成文件须在同一受控维护窗口切换，先暂停新会话，切换或回滚后回读再恢复会话。

首次接入时，安装器 blob 已变，旧的 `--preflight`/`--apply --previous` 跨 blob 尚未支持。现场已经改成 LUNO-only 且仍有旧 GLOBAL 副本时，用旧、新可信安装器对同一安装根和除来源选项外相同的入口参数只读 `--check`：旧安装器只把 `AGENTS.md` 列为 update，新安装器带 `--ends codex --codex-global-source paseo-append-system-prompt` 应全部 match；目标登记与 `prompt/LUNO.md` 均未变时，快进检出后只跑带选项的 `--check`，不运行 `--apply`。仍内嵌的现场保持原版升级路径。已迁移入口后续换版沿用同 blob 的 `--preflight`/`--apply --previous`（带同一来源选项），只重生成受管文件，不改安装器。

回滚时显式运行 `--ends codex --apply --codex-global-source agents-md` 与 `--check`，要求私人 GLOBAL 副本仍在；同一窗口恢复 daemon 设置，再核对旧组合。

## 独立原生 Codex（0.170.0）

此模式不迁移 paseo、会话或登录态，沿用原有秘密、审批和角色分工。主提示词源仍是 `prompt/LUNO.md`，LENS/FORGE 原文仍在受管检出 `subagents/`；保留原文不等于独立 Codex 已具备角色派发。MCP 非秘密配置可另按目标支持的现有接口预置；服务凭据独立授权，缺失不阻塞无依赖的提示词安装。本安装器不配置 MCP、不注入任何凭据，也不请求模型。

`--home` 是已存在的受管安装根，不改变进程 HOME。`--ends` 只选择登记端；省略时维持 Compose 的三端布局。`--codex-home` 仅允许与 `--ends codex` 合用，且须是安装根内的绝对目录：把登记 Codex 的全局入口映射到该目录的 `AGENTS.md`，把技能入口映射到该目录的 `skills/<名称>`；生成物和 GLOBAL 仍在安装根的 `.luno/` 布局中。登记对象、源文件与默认模板不变，不新增同步对象或私有实例登记。

实际 HOME 下的 `.agents/skills` 不随 CODEX_HOME 改变。此模式明确采用 0.170.0 仍支持、但已弃用的 `$CODEX_HOME/skills` 兼容根，避免改 HOME 或建立根外链接；版本变化必须重核，不承诺未来继续支持。对应官方源码与指令优先级见 `skills/luno-platform/references/runtime-codex.md`。要采用其他根或改 HOME，另定方案，不由安装器自动迁移。

先按 `skills/luno-core/references/sync.md`〔分支 sync-host〕准备已授权私人 GLOBAL 副本，再运行下列命令；路径变量均为本次明确核实的非秘密值，不是自动探测入口：

```sh
python3 -B tools/link-install.py --checkout "$CHECKOUT" --home "$INSTALL_ROOT" \
  --ends codex --codex-home "$CODEX_HOME"
```

计划无冲突后，在已有授权内同参数加 `--apply`，再加 `--check` 回读。该模式不检查、创建、删除或修复未选端的用户入口；登记结构仍整体校验。原有未受管占位、父目录软链、GLOBAL 缺失及实际 CODEX_HOME 下的 override 均在写前阻断。不会扫描实际 HOME、项目或其他技能根以排除全部同名对象；调用方须按明确范围核实际加载，不把离线匹配报告为模型行为实测。

GLOBAL 更新需重新 apply/check；没有私人复制授权或完整前态时停依赖部分。新参数与旧安装器 blob 不同，所以既有 Compose 安装跨到此安装器版本时，原有 `--preflight` / `--apply --previous` 会按 `installer_changed` 停止；不绕过该门禁，也不借原生首装迁移 Compose。首装撤回和同布局恢复沿用上节规则，必须保留本次 create 报告；更换安装根或 CODEX_HOME 不是已支持的原位升级。

原生两角色（`subagents/LENS.md`、`subagents/FORGE.md`）的 Codex 落点是 `$CODEX_HOME/roles/{lens,forge}.toml`，由登记里的 `generated/codex-role` renderer 生成：`model`、`model_reasoning_effort`、`developer_instructions` 三键各一行，前者取该端登记的模型参数，后者是指令真源原文按 TOML basic string 转义的 UTF-8 字节（不 strip、不归一换行）。这两个文件**只在 `--ends codex --codex-home` 的显式布局启用**，默认 Compose 三端不产生它们。注册（主 `config.toml` 的 `[agents.LENS]` / `[agents.FORGE]`，字段 `description`、`config_file`）和角色文件都是**只读前提**：plan/check 只核对，`--apply` 对相等文件仅 no-op，缺文件、缺注册、字段/类型/指向不符或正文漂移一律停止，不创建、不代修，没有首次接管记录也不把等字节的普通文件当成已接管。接管是零安装动作的检出升级：维护窗口内核 HEAD=旧版且干净，用旧版安装器自己的 `--check` 取投影，再用新版 `--check-native-role-adoption <新版> --adoption-blobs <旧blob>,<新blob>` 对同一实际根只读核对：绑定当前 HEAD=旧版、旧版为新版祖先、两版安装器 blob 与运行中的本工具字节哈希一致，并在独占临时目录执行旧版自己的 `--check`，把它的完整动作投影与新计划逐项比对（只准两个角色文件与已有目录的 match 增量，旧项缺失或改指即停）；不写文件、不 fetch、不切版本。角色 renderer 按 TOML basic string 转义生成三键，不另做生成物复核；注册只按已核现有布局逐行定位两个受管表，标准库 `tomllib` 只解码 `description`、`config_file` 的单行 basic string 值，不整份解码主 `config.toml`，因此需 **Python 3.11+**，随后只 ff-only 到新版并跑新版 `--check`。已经接管的同布局更新沿用 check→`--preflight`→ff→`--apply --previous`→check，只有现场旧文件全字节等于上一登记版本的渲染结果时才改写角色文件；失败按已记录版本回读角色文件、注册与共同入口，不反向跨 blob apply，也不删除文件。准入失败或中断时保留原检出与未写文件，不删除角色文件、不改注册；恢复只按已记录的旧/新两态各自原字节进行，第三态交负责人。

## Paseo 多上游 Codex 入口

`platforms/paseo/config.example.json` 保留内置 Codex 原通道，另给出两个上游各三个自定义 Codex 入口。实例只采用获准条目，不能将示例整表覆盖现有配置。六个自定义标签按助手命名；LUNO · CCHP 使用独立 `luno-cchp`（`extends: codex`），原 `luno-cchp` Profile 只将 provider 引用改到该新入口。内置 `codex` 不承载 LUNO 标签或 Profile 身份，示例仅撤其 label 覆盖，保留 command/env；生产恢复原名称也不得删除或重置原启动、鉴权及其他配置。旧 `lens-codex`、`forge-codex` 与 `lens`、`forge` Profile 引用保留。`luno-cchp` 在示例中列所有 custom 条目之首；界面也应排在全部自定义入口最前、LENS · CCHP 之前，但须按安装版支持的官方排序机制实施并回读，不能把 JSON 键顺序当成 UI 排序证明。示例中模型与思考值是用户可编辑初值，不表示该上游已验证支持。

两个 LUNO 入口共用原有主 home，以启动参数选择各自 `model_provider`，不复制私人 GLOBAL。四个 Codex worker 使用互相独立的角色 home，`AGENTS.md` 只链接对应 `subagents/` 原文；新 home 的角色与技能链接以 `tools/sync-targets.json` 为准。每个 home 的普通 Codex 配置只声明其需要的模型上游及已授权非秘密配置，秘密仍由当次授权变量注入；示例不包含这些实例配置，不是单文件即装即用包。新增角色不修改终端 Codex 的原生角色注册、模型或思考值。

派发按 `skills/luno-platform/references/runtime-paseo.md`：当前官方 Profile 的 `notes` 是角色与上游关联声明的唯一真源，仅用 `role`、`upstream` 两个字段；它不证明实际身份，仍须核实际启动参数、home、上游配置及指令来源。不另存路由表，不新增派发脚本或 provider schema 字段。显示名随意更改不影响匹配；模型、thinking、mode、options 改动在下一次派发重新读取。新增上游时配置入口/Profile 声明和经核实的角色 home，新增受管链接须更新登记；规则不增补上游或 provider 名单。缺失或多义关联停止，不跨上游兜底。

安装器不管理 Paseo providers/Profile 或 Codex 的上游配置。当前 `link-install.py` 的目录与链接生成支持追加登记路径；它对 Paseo 的 `AGENTS.override.md` 检查只覆盖原有两条 Codex home，新 home 须按精确落点另查。

角色启动核验需要包含 [Paseo v0.16.2 角色核验补丁](platforms/paseo/codex-role-verification-v0.16.2.patch) 的 daemon。在 Paseo 源码副本核对基线为 `2ee30f4164af42ba209236ab3a31bf9532592fc3`，依次用 `git apply --check <补丁路径>`、`git apply <补丁路径>` 应用，按 Paseo 的发布流程构建并隔离验收。Compose 部署时通过既有 `PASEO_BASE_IMAGE` 构建参数选择已验收的镜像。npm 安装并由 systemd 托管时，先核实单元实际加载的 server 包，以独立安装前缀验证同版补丁包，确认原有启动入口和配置可以恢复，再切换单元使用的程序并核对新进程实际加载的包。

该补丁修改了 Paseo 服务端源码和测试，上游版权及 Apache 2.0 全文随补丁分发。 [Paseo 上游许可](platforms/paseo/LICENSE.upstream.txt)

对选用的 Codex worker，在 provider 的 `env` 同时配置 `PASEO_CODEX_ROLE_SOURCE`（受管检出里登记的角色原文绝对路径）和 `PASEO_CODEX_ROLE_MODEL_PROVIDER`（预期生效的 Codex 上游标识），然后按运行端规则核验状态。角色会话空闲后才可切换模型，Paseo 会重连并核对新模型。临时会话切换模型时需新建会话。未返回角色证据时停止正式派发。使用新契约前，完成独立审查及授权部署。

Paseo 0.16.2 的动态 provider 子路径不宜假定为受支持接口；已见 `Unknown configuration path`，而 `set agents.providers` 会替换整表。把声明存入 Profile `notes` 的方案不扩展 provider schema；落地前须核安装版接受该 JSON 字符串，并通过已核支持的官方 Profile 读写入口补充和回读。安全与授权沿用总控，不因配置示例而扩大。

## 测试与历史

用法、选路及白名单环境见 `tests/run-tests.sh` 头部与实现；准入和成本见 `skills/luno-core/references/test-authoring.md`。结构守卫退出码见 `tools/check-rules.py` 头部；测试将任何非零记为失败，`sync-all.sh` 只阻断 rc=1/3。结构通过不代替行为审查。

CI（`.github/workflows/tests.yml`）只用一个 job 和一个 `selected` 步骤，选路表与测试都取受测 checkout：`pull_request` 以事件 base 为 B、merge 提交为 M，显式检出 M 后核 HEAD=M 且 M 的双亲恰为 [B, head]，取 `git diff B M` 并测试 M（base 自己前进不算 PR 变化，冲突 PR 无合并结果）；`push` 取 before→after。事件值经 env 传入并校验事件名与 40 位 hex，diff 以 NUL bytes 经 `select-paths` 内存串接，缺对象、全零或上游失败都阻断，不静默 fetch、不以空树或 full 兜底。运行器、选路表或该 workflow 变更命中所有把 runner 当消费者的组，与 full 取并集后为登记表展开的全部入口各跑一次；普通未映射正文仍只跑 smoke。

运行器一轮输出即原证：轮首打印 HEAD、tree、git 版本和 trackedState，每入口 BEGIN 记 name/group，stdout/stderr 原 bytes 合并流式输出（不截断、不加前缀、不重打），END 记原始 exitCode、unittest 摘要的 tests/skip（非 unittest 或摘要缺失分别记 N/A、unavailable）和单调耗时。聚合退出码：全成功 0、测试失败 1、选路/环境/基础设施或清理失败 2，原始子进程退出码始终保留；INT/TERM 清理后 130/143。WORK 由 `mktemp` 在 TMPDIR 排他创建并在本轮 nofollow 核验后删除，不落持久日志、不建证据平台；调用方获准后自行保存本轮 stdout/stderr 与进程退出码。

批次结果只记当批 PR，历史以 git 为准；公开快照未导入旧私有 `LucaLin233/Agent` 历史。技能合并与资源迁移见提交 `484de55052413ef2004d5e588d5a0540bcf88826`（六技能）和 #43（记忆并入 luno-platform、CCHP 官方件入包）。

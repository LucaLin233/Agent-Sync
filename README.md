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

## 测试与历史

用法、选路及白名单环境见 `tests/run-tests.sh` 头部与实现；准入和成本见 `skills/luno-core/references/test-authoring.md`。结构守卫退出码见 `tools/check-rules.py` 头部；测试将任何非零记为失败，`sync-all.sh` 只阻断 rc=1/3。结构通过不代替行为审查。

批次结果只记当批 PR，历史以 git 为准；公开快照未导入旧私有 `LucaLin233/Agent` 历史。技能合并与资源迁移见提交 `484de55052413ef2004d5e588d5a0540bcf88826`（六技能）和 #43（记忆并入 luno-platform、CCHP 官方件入包）。

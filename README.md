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

## 测试与历史

用法、选路及白名单环境见 `tests/run-tests.sh` 头部与实现；准入和成本见 `skills/luno-core/references/test-authoring.md`。结构守卫退出码见 `tools/check-rules.py` 头部；测试将任何非零记为失败，`sync-all.sh` 只阻断 rc=1/3。结构通过不代替行为审查。

批次结果只记当批 PR，历史以 git 为准；公开快照未导入旧私有 `LucaLin233/Agent` 历史。技能合并与资源迁移见提交 `484de55052413ef2004d5e588d5a0540bcf88826`（六技能）和 #43（记忆并入 luno-platform、CCHP 官方件入包）。

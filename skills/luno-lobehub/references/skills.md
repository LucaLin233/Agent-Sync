# LUNO｜LobeHub Skill 与连接器

先取得本包入口必需规则。

## Skill 与连接器
- **Skill 与连接器**：区分内置工具、市场/用户自定义技能与 Custom MCP；共享范围及 Agent 启用方式按对象类型和当前版本核对，不把连接器的启用方式套用于技能。只改用户指定的层级与启用方式，平台没有的模式不模拟。连接器与 STDIO MCP 的密钥用环境变量传入，不写进内容。
- **历史诊断陷阱（2026-09-17）**：`user_connectors.credentials` 为禁读列；历史记录显示，对其做 `::jsonb` 强制转换时，Postgres 错误详情会回显原值前缀。任何涉及该列的表达式都不得进入诊断输出，连类型探测也不例外。
- **新建与更新**：无资源的新技能用 `lh skill create`（参数见 `--help`），无需公网位置。`lh skill install` 的来源类型（GitHub URL/简写、ZIP URL、市场标识符）与 `--branch` 见 `--help`，使用前核当前版本；GitHub 下载整仓 ZIP，技能须在根目录，服务端不读 GitHub token，私有仓库、本地路径、私有 IP 不作可用来源；市场标识符不是 URL。install 既可新建也可更新，不以删除为前置；核当前入口、identifier 与来源，区分同 identifier 包更新与正文资源化，不断言 identifier 一律由 URL 生成；更新后回读 ID。仅无法原位更新且用户明确授权迁移时备份后删重建；旧 ID 不保证恢复，须同步登记。用 `lh skill view <id> --json id,identifier,source,zipFileHash` 等已确认非秘密字段核来源，禁全量读 manifest 致签名 URL 泄漏。
- **更新时平台把技能拆成独立字段**：`content`（正文）与 `description`、`name` 各自独立，`lh skill edit` 不带 `--description` 只改正文——描述会静默停留在旧文案（本实例曾发生，巡检只比正文未发现）；每次改完须用 `lh skill view <id> --json content,name,description` 分别回读判等：本地正文按规则仓库 `tools/body_contract.py` 提取（去掉有效 frontmatter（含结束分隔行自身行终止符），再去掉其后紧随的至多一个行终止符（若存在）；不泛化删除所有前导空行；无有效 frontmatter 则保留全文；入口校验及边界以实际契约为准），与平台 `content` 的 UTF-8 字节严格相等，不用 strip/rstrip，不规范化 CRLF 或尾 LF；其他端不假定具备该仓库工具，须遵循同一契约。现有巡检将恰少一个尾 LF 列为平台形态差异并**计入 rc=1**（2026-10-02 起；本实例实测 install 会裁尾 LF，须以 `body_bytes` 提取正文再 `lh skill edit -c` 原样补齐，不作通过例外），并非字节相等，当前修改对象须消除此差异。资源按完整相对文件路径逐项 `read-resource` 比原始 bytes；`resources` 顶层目录、ZIP 哈希及正文判等均不代替资源判等。**给 CLI 传带尾换行的正文时禁用 `$(cat …)`／`"$(…)"`**：命令替换会剥掉尾部换行，回读缺一个 LF 会被误判成平台形态差异。改用 `--config-file` 传 JSON（`lh agent edit --config-file`，`{"systemRole": 全文}`）或由脚本直写。
- **读技能的可用路径**：`lh skill view <id> --json content,name,description` 按字段只读回读（字段语法以 `--help` 为准；技能资源另用 `lh skill resources`）；或由派发方给规则摘要、按执行目标在设备侧按路径只读读取。需要的是规则而不是安装能力时，不必启用任何技能类工具（2026-09-16 实测：平台侧助手在其设备环境执行 `lh skill view` 与 `lh skill resources` 两条命令可用、退出码 0；`read-resource` 未实测）。
- **登记、启用、加载与行为分别验证**：不得仅因 `lh agent view` 的 `plugins` 缺少技能条目就断言未启用；网页端自定义技能在列也不足以证明已加载或行为生效。按当前版本核对技能暴露机制、目标 Agent 的可用性及实际加载/调用证据；证据不足标“未验证”。重建后回读新 ID，并核对相关引用与目标 Agent 可用性，不预设必须重新绑定或无需关联。

**既有私有资源包投递**（2026-09-20/21 本实例实测）：私有 R2 桶生成约 600 秒有效的预签名 ZIP GET URL，供 `lh skill install` 一次性下载；桶本身不公开，不使用私有仓库直链。更新沿用同一 R2 key；本实例已复现保留 ID，仍须回读 ID，并以已确认版本的本批候选独立核对打包源、完整资源 bytes 与 ZIP/`zipFileHash`；本批预期换包而包哈希未变时，先查原因，不盲重投。预签名 URL 含临时凭据，不进入回复、日志、归档或文件；仅由已核安全通道在授权源与目标间传递，无该通道即暂停投递并交负责人，不改塞 argv 或 tool JSON 规避，也不改用公开对象；生产写入授权与同名核对不豁免。

## 与入口及其它资源的关系
- 知识库、文档、分块、embedding、检索与平台记忆见 `references/knowledge.md`；实例部署、升级恢复、鉴权、服务栈与异步任务条件见 `references/instance.md`。跨项取并集，不以本资源替代其它资源。

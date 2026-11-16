分支：knowledge、lobehub-memory。读法见 luno-core 入口〈加载〉。

<a id="branch-knowledge"></a>
<!-- BEGIN knowledge -->
# 知识库与平台记忆

## 知识库

- **删除前**盘点知识库的内容和关联，并确认；核对 embedding 的供应商和模型。
- **挂载**用 `lh agent add-kb`。`lh agent edit --config-file` 会静默忽略 `knowledgeBases`（agent.updatedAt 变了，但 `agents_knowledge_bases` 没变）。核对挂载要查关系表，或用 `lh agent view <agentId> --json <已确认的非秘密字段白名单>` 回读（先核对当前 CLI 的字段语法，不能安全限定子字段就停，禁止全量读取再脱敏），不能只看 CLI 打了勾。`lh agent list --json` 不返回这个字段（请求得到 `{}`），不能用来判断；2026-10-01 实测 CLI 0.0.55（现版本未核）：`lh agent view <id> --json knowledgeBases` 可用，并与关系表一致。
- **入库的两条路**：`custom/document`（`lh doc create`、`doc batch-create`）不分块，走 BM25 全文检索（`documents_bm25_idx`）；上传文件才会分块和向量化。知识库检索并行走文件向量和文档 BM25，一路失败会自动降级并附注。
- **上传不会自动分块**（2026-10-01 实测 CLI 0.0.55，现版本未核）：`lh kb upload`、`lh file upload`、`lh doc parse` 都不触发分块（CLI 里没有 `chunk.*` 调用，Web 端才有 `createParseFileTask`；当时本实例 `files.chunk_task_id` 全部为 NULL）。需要向量召回时，补调 `POST /trpc/lambda/chunk.createParseFileTask`，请求头 `X-API-Key`，请求体 `{"json":{"id":"<fileId>"}}`（同族还有 `chunk.createEmbeddingChunksTask`；需要 `knowledge_base:update` 权限）。HTTP 写法见 `references/lobehub.md`〔分支 lobehub-access〕。
- `lh file view` 的 `chunkCount`/`chunkingStatus`/`embeddingStatus` 为 `null` 时不单独判定失败；`chunkCount>0` 只表示有分块，不是检索验收（本资源未提供对应版本的检索验收正例）。
- `unboxing minimum_should_match_ argument failed` 的已知原因之一是 SQL 定义和 .so 不匹配，不能只凭这条报错定因；`pg_search` 版本核对和扩展更新见 `references/lobehub-instance.md`。

## GLOBAL 私人副本与首次读取

- **载体与定位**：Minis `/var/minis/memory/GLOBAL.md` 是唯一真源，整份单向同步，不分区、不反向回写或双向合并。优先用经核实的私人助理空间文件；只有确认该能力不可用时，才以为此新建的专用私有知识库兜底，保存题为 `GLOBAL.md` 的完整文档，不得使用或改动三个既有知识库及其文档和关联。新建载体仍须取得当次授权，不因本规则自动创建。空间根没有 GLOBAL 文件不证明空间能力不可用；CLI 管理入口存在也不证明对话可调用。只在用户授权的关联范围按标题或文件名定位，确认唯一文件或文档身份后按真实路径或文档 ID 完整读取；同名冲突或范围不明即停该项，不全局枚举或猜定位。真实路径、ID、归属和权限证据只留在部署私人侧，不进入公开仓库或稿件。
- **首次读取**：LobeHub 每个新话题首次回复前读取指定 GLOBAL；同话题已经完整读取且能确认未变时不重复。发现更新、版本不明或读取有缺口时重核并补读，不自建状态机或账本。读取使用当前实例已核实可用的完整文档入口；知识库检索仅可定位，不以 RAG 片段、摘要、单个窗口或工具自述代替全文。遇分页或截断，按工具给出的续读位置补齐并确认完整；不得把未读部分算已加载，也不凭复制文件、挂载或管理面回读宣称模型实际可读。
- **不可用时**：载体不存在、文档冲突、无权限、工具缺失或无法完整读取时，明确说明 GLOBAL 尚未加载，仅暂停依赖其中资料的操作；无需其资料的答复和已独立确认事项可以继续，不猜偏好或环境事实，不把所有对话阻塞。不得为读取自动启用写工具、扩大权限或改用原生记忆导入。
- **写前与恢复**：同步前核对目标的真实身份、私人权限、授权关联范围、实际挂载/启用及完整正文前态；目标有独有修改、并发变化或无法核对前态即停，交用户核对，不覆盖、不双向合并。写后核完整正文与源文件的 UTF-8 字节，不 strip 或归一换行；私人内容和实际定位不进入公开仓库、候选仓库、稿件示例、日志或提交。GLOBAL 不得含秘密；端专属事实标范围、日期和例外，偏好不构成已部署事实或操作授权。恢复须先核现状及并发，只用授权私人侧明确前态；未获删除授权不删库或文档，不把私人正文存进公开 Git 恢复历史。不假定自动注入或已完成部署。

## 已验证的 HTTP 接口

`document.getDocumentById`、`document.updateDocument {id,content}`、`document.createDocument {title,content,knowledgeBaseId,fileType}`、`document.deleteDocument {id}`（没有 `document.removeDocument`）、`document.queryDocuments`、`chunk.createParseFileTask`、`chunk.createEmbeddingChunksTask`、`chunk.semanticSearch`、`knowledgeBase.getKnowledgeBases`。

- `document.queryDocuments` 的输入支持 `current` 和 `pageSize`（上限 100），但不支持 `knowledgeBaseId` 过滤（v2.3.2 路由源码，未行为实测）；不能把全局分页结果当作指定知识库的完整枚举，须使用匹配版本的知识库范围读取入口。
- **写后读有最终一致性延迟**：写完立刻复读可能还是旧内容，判等要留时间窗口。

<!-- END knowledge -->

<a id="branch-lobehub-memory"></a>
<!-- BEGIN lobehub-memory -->
## 平台记忆

- 记忆由内置工具 `lobe-user-memory`（五类 add*Memory 和 searchUserMemory）以及平台的话题提取写入实例库 `user_memories` 和关联表。v2.3.1 的迁移 0193/0195 加入了结构化记忆表与生命周期、实体和 dossier 关联列，五层分类不等于完整的 schema；查库前先核对当前元数据，不沿用固定的列清单。话题提取的记录按 `metadata.source`、`metadata.sourceId`、`metadata.messageIds` 追溯来源，读取时仍要限定已确认的嵌套子字段（v2.3.1 迁移源码记录，2026-11-03，现版本未核，迁移和展示未实测）。
- `memory_category` 是自由的主题文本；`captured_at` 是对话时间，写入时间看 `created_at`。记忆入口和可用层级按执行设备各子命令的帮助分别核对，不能把单一创建入口的层级限制外推到其他子命令。
- 原生平台记忆只来自本平台的对话提取或 agent 基于当前对话主动写入；不导入外部记忆副本，知识库文档不参与原生记忆生成。用户指定的整份 GLOBAL 单向私人副本是另行管理的上下文，不写入原生记忆库；按 `references/lobehub-knowledge.md`〔分支 knowledge〕 的 GLOBAL 规则处理，其他记忆仍各端自持，共同边界见 `references/memory-common.md`〔分支 memory-common〕。
- **记忆工具是否可用，不看 agent 的 `plugins` 数组**：`lobe-user-memory` 属于默认工具集和 chat 模式白名单，实际开关是 `agent.chatConfig?.memory?.enabled ?? (userSettings.memory?.enabled !== false)`，`lh agent view` 不显示这个字段（历史源码记录，原版本和日期未记录，2.3.1 未核）。
<!-- END lobehub-memory -->

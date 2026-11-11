# 知识库与平台记忆

## 知识库

- **删除前**盘点知识库的内容和关联，并确认；核对 embedding 的供应商和模型。
- **挂载**用 `lh agent add-kb`。`lh agent edit --config-file` 会静默忽略 `knowledgeBases`（agent.updatedAt 变了，但 `agents_knowledge_bases` 没变）。核对挂载要查关系表，或用 `lh agent view <agentId> --json <已确认的非秘密字段白名单>` 回读（先核对当前 CLI 的字段语法，不能安全限定子字段就停，禁止全量读取再脱敏），不能只看 CLI 打了勾。`lh agent list --json` 不返回这个字段（请求得到 `{}`），不能用来判断；2026-10-01 实测 CLI 0.0.55（现版本未核）：`lh agent view <id> --json knowledgeBases` 可用，并与关系表一致。
- **入库的两条路**：`custom/document`（`lh doc create`、`doc batch-create`）不分块，走 BM25 全文检索（`documents_bm25_idx`）；上传文件才会分块和向量化。知识库检索并行走文件向量和文档 BM25，一路失败会自动降级并附注。
- **上传不会自动分块**（2026-10-01 实测 CLI 0.0.55，现版本未核）：`lh kb upload`、`lh file upload`、`lh doc parse` 都不触发分块（CLI 里没有 `chunk.*` 调用，Web 端才有 `createParseFileTask`；当时本实例 `files.chunk_task_id` 全部为 NULL）。需要向量召回时，补调 `POST /trpc/lambda/chunk.createParseFileTask`，请求头 `X-API-Key`，请求体 `{"json":{"id":"<fileId>"}}`（同族还有 `chunk.createEmbeddingChunksTask`；需要 `knowledge_base:update` 权限）。HTTP 写法见 `references/lobehub.md`〔分支 lobehub-access〕。
- `lh file view` 的 `chunkCount`/`chunkingStatus`/`embeddingStatus` 为 `null` 时不单独判定失败；`chunkCount>0` 只表示有分块，不是检索验收（本资源未提供对应版本的检索验收正例）。
- `unboxing minimum_should_match_ argument failed` 的已知原因之一是 SQL 定义和 .so 不匹配，不能只凭这条报错定因；`pg_search` 版本核对和扩展更新见 `references/lobehub-instance.md`。

## 已验证的 HTTP 接口

`document.getDocumentById`、`document.updateDocument {id,content}`、`document.createDocument {title,content,knowledgeBaseId,fileType}`、`document.deleteDocument {id}`（没有 `document.removeDocument`）、`document.queryDocuments`、`chunk.createParseFileTask`、`chunk.createEmbeddingChunksTask`、`chunk.semanticSearch`、`knowledgeBase.getKnowledgeBases`。

- `document.queryDocuments` **会忽略 `knowledgeBaseId` 参数**，只返回全局最近的 100 条，且没有分页，所以不能用来枚举知识库；枚举要先用 `lh kb view` 引导一次。
- **写后读有最终一致性延迟**：写完立刻复读可能还是旧内容，判等要留时间窗口。

## 平台记忆

- 记忆由内置工具 `lobe-user-memory`（五类 add*Memory 和 searchUserMemory）以及平台的话题提取写入实例库 `user_memories` 和关联表。v2.3.1 的迁移 0193/0195 加入了结构化记忆表与生命周期、实体和 dossier 关联列，五层分类不等于完整的 schema；查库前先核对当前元数据，不沿用固定的列清单。话题提取的记录按 `metadata.source`、`metadata.sourceId`、`metadata.messageIds` 追溯来源，读取时仍要限定已确认的嵌套子字段（v2.3.1 迁移源码记录，2026-11-03，现版本未核，迁移和展示未实测）。
- `memory_category` 是自由的主题文本；`captured_at` 是对话时间，写入时间看 `created_at`。子命令以及 `create` 只支持 identity 层，见 `lh memory --help`（2026-11-03 本机 CLI 0.0.73 只核过帮助）；其余层通过工具或提取写入。
- 平台记忆只来自本平台的对话提取或 agent 基于当前对话主动写入；不导入外部记忆副本，知识库文档不参与生成。各端记忆分工见 `luno-memory`。
- **记忆工具是否可用，不看 agent 的 `plugins` 数组**：`lobe-user-memory` 属于默认工具集和 chat 模式白名单，实际开关是 `agent.chatConfig?.memory?.enabled ?? (userSettings.memory?.enabled !== false)`，`lh agent view` 不显示这个字段（历史源码记录，原版本和日期未记录，2.3.1 未核）。

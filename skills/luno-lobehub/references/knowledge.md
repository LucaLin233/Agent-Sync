# LUNO｜LobeHub 知识库与记忆

先取得本包入口必需规则。

## 知识库与记忆
- **知识库与记忆**：删 KB 前盘点内容与关联并确认；核 embedding 供应商与模型。挂载 KB 用 `lh agent add-kb`（参数见 `--help`）；`lh agent edit --config-file` 静默忽略 `knowledgeBases`（agent.updatedAt 变、`agents_knowledge_bases` 不变）。须查关系表或以 `lh agent view <agentId> --json <已确认非秘密字段白名单>` 回读，先核当前 CLI `--help`/只读源码的字段语法，不能安全限定子字段即停，禁全量后脱敏；不只看 CLI ✓。`lh agent list --json` 不返回此字段，请求得 `{}`，不能用于判断；2026-10-01 实测 CLI 0.0.55（现版未核）：上游 `queryAgents` select 无此列，`lh agent view <id> --json knowledgeBases` 可用且与关系表一致。
- **入库两条路**：`custom/document`（`lh doc create` / `doc batch-create`）不分块，走 BM25 全文（`documents_bm25_idx`）；上传文件才分块＋向量。KB 检索并行走文件向量与文档 BM25，单路失败自动降级并附注。`lh kb upload` / `lh file upload` / `lh doc parse` 均不触发分块（2026-10-01 实测 CLI 0.0.55，现版未核：全包无 `chunk.*` 调用，Web 有 `createParseFileTask`；本实例 `files.chunk_task_id` 536/536 为 NULL）；需向量召回时补 `POST /trpc/lambda/chunk.createParseFileTask`，头 `X-API-Key`、体 `{"json":{"id":"<fileId>"}}`（同族 `chunk.createEmbeddingChunksTask`；权限 `knowledge_base:update`）。
- `lh file view`：`chunkCount`/`chunkingStatus`/`embeddingStatus` 为 `null` 不单独判失败；`chunkCount>0` 仅示有分块，非检索验收；本批无正例。
- 记忆由内置工具 `lobe-user-memory`（五类 add*Memory、searchUserMemory）与平台话题提取写入实例库 `user_memories` 及关联表。v2.3.1 的 0193/0195 包含结构化记忆表与生命周期、实体及 dossier 关联列，五层分类不等于完整 schema，查库先核当前元数据，不沿用固定列清单；话题提取记录按 `metadata.source`、`metadata.sourceId`、`metadata.messageIds` 追溯来源，读取仍须限定已确认的嵌套子字段。（v2.3.1 迁移源码记录，2026-11-03，现版未核；未实测迁移/展示。）`memory_category` 是自由主题文本；`captured_at` 为对话时间，写入时间看 `created_at`。子命令与 `create` 仅支持 identity 见 `lh memory --help`，其余层用工具或提取。（实测：本机 0.0.73 `memory --help` 与 `memory create --help`，2026-11-03，仅帮助，未调用服务端。）平台记忆仅由本平台对话提取或 agent 基于当前对话主动写入；不导入外部记忆副本，KB 文档不参与生成；记忆分工依 `luno-memory/SKILL.md`。
- **记忆工具是否可用不看 agent 的 `plugins` 数组**：`lobe-user-memory` 属默认工具集与 chat 模式白名单，实际开关是 `agent.chatConfig?.memory?.enabled ?? (userSettings.memory?.enabled !== false)`，`lh agent view` 不显示该字段（历史源码记录，原版本/日期未记，LobeHub 2.3.1 未核）。
- SQL 定义与 .so 不匹配是 `unboxing minimum_should_match_ argument failed` 的既有原因之一，不据报错单独定因。

## 批量 HTTP 已验证接口与写后读一致性
（下列为知识库已验证接口与写后读一致性；CLI/HTTP 调用或相关建议、结论前仍须完整读取 `references/access.md`。）
- 已验证：`document.getDocumentById`、`document.updateDocument {id,content}`、`document.createDocument {title,content,knowledgeBaseId,fileType}`、`document.deleteDocument {id}`（`document.removeDocument` 不存在）、`document.queryDocuments`（**`knowledgeBaseId` 参数被忽略**，只回溯全局最近 100 条且无分页 → 不能枚举 KB，枚举须用 `lh kb view` 引导一次）、`chunk.createParseFileTask` / `chunk.createEmbeddingChunksTask` / `chunk.semanticSearch`、`knowledgeBase.getKnowledgeBases`。**写后读有最终一致延迟**：写完立刻复读可能仍是旧内容，判等要留时间窗口。

## 与入口及其它资源的关系
- 涉及 `pg_search` 版本核对、扩展更新、数据库或实例侧改动及相关建议／结论前，须完整读取本包 `references/instance.md`。

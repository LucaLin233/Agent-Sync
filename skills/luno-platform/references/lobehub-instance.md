# 实例运维

## 坐标与基线

- **本部署坐标**（应用和数据库 2026-10-04、网关 2026-09-22 的记录，现版本未核）：Compose 在 `/root/lobehub/compose.yaml`（同目录 `.env`）；`lobe` 用 host 网络监听 `:3210`，`lobe-postgres`（ParadeDB PG17）`:3211`，`lobe-gateway` `:8787/:8788`。公网入口 `LOBEHUB_SERVER` 的取值和缺失处置见本技能入口的〈LobeHub入口〉；宿主按当次的连接参数确定，正文不缓存地址。
- **宿主初查**：`docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'`、`curl -fsS http://localhost:3210/`；host 网络的监听看 `ss -lntp`，不要只看 `Ports` 或凭上游默认端口（3000）推断。
- **基线核对**：应用和网关分别核对实际的镜像版本或 digest、Compose 标签和各自的自动更新策略；不拿应用版本推网关版本，也不把浮动标签当实际版本。检查项：PostgreSQL（推荐 17+ 和 `pg_search`）、Redis、S3、`INTERNAL_APP_URL`、`AUTH_SECRET`、`JWKS_KEY`；通信和网关相关的项（如 `INTERNAL_APP_URL`）按文档 `self-hosting/platform/docker-compose.mdx`〈Necessary Configuration〉核对。应用版本以容器内的 `/app/package.json` 为准，OCI 标签可能和代码不符。现场取值按当次授权取证，不凭历史值推断，部署变更后重验。
- **设备连接器**：装了新版不等于连接器已换版，要分别核对 installed 和 running，任务结束后按实际的管理器重启；重启会断开设备连接和远程终端。不拿本机 CLI 版本推远端运行版本；服务管理范围按执行设备当前帮助核对。

## 升级、迁移与恢复

- **升级**：用 `docker compose` 管理。镜像启动时自动执行 schema 迁移，日志出现 `database migration pass` 才算生效；迁移机制和排障见文档 `self-hosting/platform/docker-compose.mdx`〈Database Migration Issues〉，失败了不能用清库绕过。升级前备份数据库（`pg_dump`）、对象存储和 Redis；完整恢复备份按 `luno-core/references/execution.md`〔分支 safety〕〈秘密面〉③，`KEY_VAULTS_SECRET` 必须和加密数据配对。官方的重置手段（`down` 后删除挂载数据）会清空数据库，属于需要确认的操作。
- **迁移核对**：升级前按实际要执行的迁移核对表规模、锁和停写窗口、索引、唯一键冲突和 schema 新增；补丁版本也可能有迁移，没有回填不等于没有锁。已知的 2.3.x 风险线索（2026-11-03/07 源码记录，生产开销未实测）：0196 普通建索引可能阻塞写入，0197 唯一键改为 (message_id, member_id)，0199 新增 topic_analyses。只有命中这些迁移时，才核对 0195 的列是否已存在，并按授权安排事务外的并发索引（CONCURRENTLY 不能放在迁移事务里）。重复键不得自动删除业务数据；版本不符就重读对应的迁移，不拿旧编号代表现状。
- **网关模式**：升级前核对 compose 里的网关服务和 `.env` 里的网关 URL 与令牌。漏配的现象、`AGENT_GATEWAY_PROTOCOL` 的取值（默认 `1`）和 `/v2/ws` 前提见文档 `self-hosting/environment-variables/basic.mdx` 和 `self-hosting/platform/docker-compose.mdx`〈Agent Gateway〉，不要和 `agent_gateway_mux_mobile` 混淆；改成 2 之前要确认网关实际支持 `/v2/ws`，不能只因为应用升级了就切换。网关状态在内存里，重启会中断正在跑的任务（未复现）；升级后分别回验设备连接、agent 执行位置和跟随，反代要允许 WebSocket 升级并放宽读超时。
- **Bot**：v2.3.0 起 Proactive Bot 默认开启，并移除了 `bot_wake` 灰度键（现版本未核）。升级时核对频道的自动参与范围和用量，不拿旧开关推断已关闭；关闭入口是频道设置 Wake policy → Proactive participation，改动仍须当次授权。

## 密钥、鉴权与查库

- **`KEY_VAULTS_SECRET`** 必须和已有的加密数据配对，不能直接替换。确需轮换或迁移时，先核实当前版本支持的恢复或重加密方案，做好配对备份并取得明确授权；没确认可恢复之前不改。变量含义见文档 `self-hosting/environment-variables/`（改 `AUTH_COOKIE_PREFIX` 会作废会话，`JWKS_KEY` 用于 OIDC 和内部 JWT）。
- **S3/R2 报 Unauthorized**：服务端 S3 请求的 AWS SDK 401，优先查目标桶的凭据和权限；list、view、doctor 正常不排除存储故障；不借用没核过目标桶授权的其他端凭据。
- **网关鉴权**：网关模式需要 `ENABLE_AGENT_GATEWAY` 和 `AGENT_GATEWAY_URL` 同时配置，令牌和 JWKS 不一致就会握手失败。升级后出现 JWKS 配对告警时，先核对当前版本的匹配判据（含公钥参数和 kid 的处理）；启动告警不单独证明密钥配错或网关拒签，健康检查通过也不证明鉴权通过。没有真实的网关鉴权请求时，标「网关拒签未实测」，不能只凭告警更换密钥。
- **查库、导表、导配置**按 `luno-core/references/execution.md`〔分支 safety〕〈秘密面〉的源头投影，排除 `providers.key`、`KEY_VAULTS_SECRET` 和 JWKS 私钥。先取列名与类型元数据（`SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = '<schema>' AND table_name = '<表>' ORDER BY ordinal_position`），据此写出**人已确认的列白名单**再取数（`SELECT <列1>, <列2> FROM <表> WHERE <条件> LIMIT <n>`）。禁止 `SELECT *`、`row_to_json` 等整行转 JSON 再减列，以及整体 dump（`pg_dump` 只用于完整恢复备份，按〈秘密面〉③ 放受控位置）。凭据列的诊断陷阱见 `references/lobehub.md`〔分支 lobehub-skills〕。

## 检索、暴露面与负载

- **全文检索**：`FTS_SEARCH_PROVIDER` 显式选择后端，不会静默回退；切回 `pg_search` 前须满足对应版本所需的扩展和 BM25 索引前提。Elasticsearch 的端口不能发布，进度卷禁止删除；迁移、回填和清理按对应版本文档 `self-hosting/advanced/full-text-search.mdx` 及既有备份和生产变更授权执行（v2.3.2 文档，未实测切换）。
- **`pg_search` 扩展**：镜像更新后，先核对已安装的扩展版本和镜像提供的版本；确认要更新时，按当前版本的升级说明、备份和生产变更授权执行 `ALTER EXTENSION pg_search UPDATE`，再验证检索。验收是检索回验，不以 SQL 返回成功代替；是否另有周期性对齐、最近结果如何、是否仍需手工更新，按当前部署现查。
- **暴露面与卷**：公网只开 HTTPS，不暴露数据库、Redis 和对象存储的管理端口；默认不删卷，例外只限官方排障步骤，并且已备份、已确认。
- **执行位置**：执行面**默认是云沙箱**；配好设备网关后可以在会话里选设备，选定后工具在该设备上运行。实例操作经设备连接器在目标主机执行，云沙箱只用于一次性的数据处理，不承载实例凭据，也不代替设备执行实例操作。新增设备浏览器能力要重核授权，不能按只读浏览器对待；自建实例不能因为发现失败就回退到别处的网关。
- **负载**：生产只做低负载取证；重测试（压测、批量重建索引、全量扫日志等）放到已授权的独立测试 VM，资源和权限都隔离，并限定 CPU、内存和并发，不和生产争用，做不到就停。生产业务必需的索引维护另按生产变更判断，不以测试的名义绕过。OOM 之后暂停新增的重负载，先查来源，不清 Redis、不淘汰数据、不盲目重启。

## 异步任务失败

异步任务（如生图）请求成功却没有产物时，先查两项：

- `INTERNAL_APP_URL`（Compose 必需，指向容器自身）；
- `S3_ENDPOINT`：预签名 URL 的主机名取自它，浏览器和 CLI 会直连，所以必须是可解析的主机名或地址，容器内部名无效；服务端内部访问可以另设 `S3_INTERNAL_ENDPOINT`（语义见 `self-hosting/environment-variables/s3.mdx`）。`S3_SET_ACL=0` 时普通文件的 URL 也是预签名的（这是条件说明，不是部署现值）。

图片是否要求 LLM 直连，按实际请求链路核对，不凭浏览器或 CLI 的访问方式推断；会话图片失败而头像正常只是线索，要结合任务日志、请求链路和端点可达性定因。Redis 缺失会导致会话不共享、渠道 Pairing 不可用。现场取值按当次授权取证，部署变更后重验。

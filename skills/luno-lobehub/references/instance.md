# LUNO｜LobeHub 实例运维

先取得本包入口必需规则。

## 实例层
- **本部署坐标**（应用/数据库 2026-10-04、网关 2026-09-22 记录，现版未核）：Compose `/root/lobehub/compose.yaml`（同目录 `.env`）；`lobe` host 网络 `:3210`、`lobe-postgres`（ParadeDB PG17）`:3211`、`lobe-gateway` `:8787/:8788`。公网入口 `LOBEHUB_SERVER` 的取值及缺失处置依 `luno-lobehub/SKILL.md`〈平台层〉；宿主按当次连接参数确定，正文不缓存地址。宿主初步检查：`docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'`、`curl -fsS http://localhost:3210/`；host 网络监听看 `ss -lntp`，不只凭 `Ports` 或上游默认（3000）推断。
- **基线核对**：应用与网关分别核实际镜像版本/digest、Compose 标签及各自自动更新策略；不以应用版本推网关版本或以浮动标签当实际版本。本实例检查项：PostgreSQL（推荐 17+ 与 `pg_search`）、Redis、S3、`INTERNAL_APP_URL`、`AUTH_SECRET`、`JWKS_KEY`；其中通信/网关相关项（如 `INTERNAL_APP_URL`）按文档 `self-hosting/platform/docker-compose.mdx`〈Necessary Configuration〉核。应用版本以容器内 `/app/package.json` 为准，OCI 标签可能与代码不符；现场取值按当前授权取证，不凭历史值推断，部署变更后重验。安装新版不等于连接器换版：核 installed 与 running，待任务结束后按实际管理器重启；`lh connect service` 启停/重启仅管用户级服务，`status` 可查用户级和系统级；重启会断设备连接与远程终端，不以本机 `lh --version` 推远端版本（0.0.72，2026-10-30 依连接器状态源码与 `lh connect service --help`）。
- **升级与恢复**：用 `docker compose` 管理；镜像启动自动执行 schema 迁移，确认日志出现 `database migration pass` 才算起效，迁移机制与排障见文档 `self-hosting/platform/docker-compose.mdx`〈Database Migration Issues〉，失败不得以清库绕过。升级前备份数据库（`pg_dump`）、对象存储与 Redis；完整恢复备份依 `luno-core/SKILL.md`〈授权与安全〉的〈秘密面〉③，`KEY_VAULTS_SECRET` 须与加密数据配对。官方重置手段（`down` 后删挂载数据）会清空数据库，属需确认操作。
- **2.3.x 迁移核对**：升级前按待执行迁移评估表规模与停写窗口；v2.3.1 的 0196 注释指出普通建索引会在构建期间阻塞写入，大表应先核 0195 列是否已存在，再按授权安排事务外并发建索引，不能把 CONCURRENTLY 塞入迁移事务；小库可由迁移建索引。0197 将投递唯一键改为 `(message_id, member_id)`，迁移前核重复键；若冲突不得自动删业务记录。v2.3.1 另含 0199 `topic_analyses`，不把补丁版本视为无 schema 变化；无数据回填不等于无锁等待或停写风险。（v2.3.1 迁移源码与发布说明记录，2026-11-03；v2.3.2 迁移 SQL 核对，2026-11-07；生产迁移开销未实测；重复键失败为 SQL 语义推论，未实测。）
- **网关模式升级**：升级前核 compose 网关服务及 `.env` 网关 URL/令牌；漏配现象与 `AGENT_GATEWAY_PROTOCOL` 取值、默认 `1`、`/v2/ws` 前提见文档 `self-hosting/environment-variables/basic.mdx` 与 `self-hosting/platform/docker-compose.mdx`〈Agent Gateway〉，勿与 `agent_gateway_mux_mobile` 混同；改成 2 前须核网关实际支持 `/v2/ws`，不能仅凭应用升级切换。网关状态在内存、重启会中断在跑任务（未复现）；升级后分别回验设备连接、agent 执行位置与跟随，反代须允许 WebSocket 升级并放宽读超时。
- **Bot 升级行为**：v2.3.0 起 Proactive Bot 默认开启、移除 `bot_wake` 灰度键（现版未核）；升级时核频道自动参与范围与用量，不拿旧开关推断关闭。关闭入口是频道设置 Wake policy → Proactive participation，变更仍须当次授权。
- **密钥与鉴权**：`KEY_VAULTS_SECRET` 须与既有加密数据配对，不得直接替换；确需轮换或迁移时，先核实当前版本支持的恢复/重加密方案，完成配对备份并取得明确授权，未确认可恢复前不改；变量含义见文档 `self-hosting/environment-variables/`（`AUTH_COOKIE_PREFIX` 变更作废会话，`JWKS_KEY` 用于 OIDC 与内部 JWT）；S3/R2 报 Unauthorized 时，服务端 S3 请求的 AWS SDK 401 优先查目标桶凭据与权限；list/view/doctor 正常不排除存储故障，不借用未核目标桶授权的别端凭据；网关模式需 `ENABLE_AGENT_GATEWAY` 与 `AGENT_GATEWAY_URL` 同配，令牌与 JWKS 不一致即握手失败。升级后出现 JWKS 配对告警，先核当前版本的匹配判据（含公钥参数与 kid 的处理）；启动告警不单独证明密钥配错或网关拒签，健康检查通过也不证明鉴权通过，无真实网关鉴权请求时标「网关拒签未实测」，不得仅据告警更换密钥。**查库/导表/导配置按 `luno-core/SKILL.md`〈授权与安全〉的〈秘密面〉源头投影**；排除 `providers.key`、`KEY_VAULTS_SECRET`、JWKS 私钥。先取列名与类型元数据（`SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = '<schema>' AND table_name = '<表>' ORDER BY ordinal_position`），据此写出**人已确认的列白名单**再取数（`SELECT <列1>, <列2> FROM <表> WHERE <条件> LIMIT <n>`）；禁 `SELECT *`、`row_to_json`／`row2json` 整行转 JSON 后减列及整体 dump（`pg_dump` 仅作完整恢复备份，按 core〈秘密面〉③ 落受控位置）。
- **检索**：`FTS_SEARCH_PROVIDER` 显式切换、不静默回退；换成 Elasticsearch 后不能直接回 `pg_search`，其端口不得发布，进度卷禁删（取值、回填、切回与清理见文档 `self-hosting/advanced/full-text-search.mdx`）。
- **pg_search 版本与扩展更新**：使用 ParadeDB `pg_search` 的实例，镜像更新后先核对已安装扩展版本与镜像提供版本；确认需更新时，按当前版本升级说明、备份与生产变更授权执行 `ALTER EXTENSION pg_search UPDATE`，再验证检索——验收是检索回验，不以 SQL 返回成功替代。是否另设周期性对齐、最近结果及是否仍需手工更新须按当前部署现查，不以历史配置推断。
- **暴露面与卷**：公网只开 HTTPS，不暴露数据库、Redis、对象存储管理端口；默认不删卷，例外仅限官方排障步骤且已备份并确认。
- **执行位置与秘密**：执行面**默认云沙箱**，配好设备网关后可在会话中选择设备，选定后工具在该设备上运行；实例操作经设备连接器在目标主机执行，云沙箱只用于一次性数据处理，不承载实例凭据、不替代设备执行实例操作。`connect` 可用设备上的 `agent-browser` 提供 browser 工具，默认从 PATH 自动发现，也可用 `--agent-browser` 指定；新增该能力须重核授权，不按只读浏览器对待。网关解析依次为显式 `--gateway`、当前服务器保存地址、服务端公布地址；自建实例不得因发现失败回退别处网关（0.0.72 依 `connect --help` 与差分）。
- **负载**：生产仅低负载取证；重测试（压测、批量索引重建、全量日志扫描等）转已授权的独立测试 VM，资源与权限均隔离，并限定 CPU/内存上限与并发，不与生产争用；无法做到即停。生产业务必需的索引维护另按生产变更判定，不以测试名义绕过。OOM 后暂停新增重负载，先查来源，不清 Redis、不淘汰数据、不盲目重启。

## 异步任务失败的实例条件
- **异步任务**（如生图）请求成功却无产物：先查 `INTERNAL_APP_URL`（Compose 必需，指容器自身）与 `S3_ENDPOINT`（预签名 URL 的主机名取自它；浏览器/CLI 直连，须用可解析主机名或地址，容器内部名无效；服务端内部访问可另设 `S3_INTERNAL_ENDPOINT`，语义见 `self-hosting/environment-variables/s3.mdx:40–44`）。`S3_SET_ACL=0` 时普通文件 URL 也是预签名：这是条件句非部署现值；现场取值按当前授权取证，不凭历史值推断；部署变更后重验。图片是否要求 LLM 直连须核实际请求链路，不凭浏览器/CLI 访问方式推断；部署变更后重验。会话图片失败而头像正常仅为线索，须结合任务日志、请求链路与端点可达性定因。Redis 缺失可致会话不共享、渠道 Pairing 不可用。

## 与入口及其它资源的关系
- 跨层排障先按入口〈方法〉〈平台层〉核对平台侧现象、权限与开关，再用本资源核对实例条件；涉及 Skill、连接器、知识库与记忆时按入口〈资源与触发〉读取对应资源，不以入口正文替代资源正文。

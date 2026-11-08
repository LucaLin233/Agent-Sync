# LUNO｜Minis 客户端配置

先取得本包入口必需规则；其中操作只在 Minis 端可用。配置任务必读〈配置接口〉，其余按入口指定完整节及交叉依赖；SOUL/技能写入必须连读〈目录与持久化（记忆与真源）〉，分支不明则全文。

## 配置接口
- `minis-config` 的字段形态与路径写法、写入确认、审计回滚及数组 `--filter`/分页语义，以当前 `--help`、`list-topics`、`topic-help <topic>`（含 AUDIT、FIELD I/O）为准；同会话、版本、主题已完整取得则不重读，未知或版本变化时补读。必要时才整体列举；筛选／分页只缩小记录集，不替代字段投影。回读依 `luno-core/SKILL.md`〈执行闭环〉。
- 技能与子代理**只在平台实际支持的字段与动作上** App 页面与 CLI 等效，按用户便利选择；改完以回读为准。支持面以 `minis-config list-topics`／`topic-help` 为准；例外只有 App 可做：新增子代理、技能元数据（描述／排序）及其刷新；技能正文仍可直接改文件，但改文件不刷新元数据（见本文〈技能登记〉）。
- `set-batch` 的 `value_json` 必须是 JSON **文本**（多一层编码）；批量中任一项失败会整批 `partial_write_failed`，**同批已成功项也可能未落盘**——失败后先逐项回读确认差异，只重写缺失项。
- 环境变量经 App 设置页维护；引用按变量名，缺失即说明并给创建入口，不换来源。凭据类只读存在性与长度，取值不经对话。

## 子代理与模型
- 子代理条目在 App UI 配置。内置通用子代理位于 `subagents.general.instructions`（roster 显示为 `builtin.general`）。instructions 字符上限见 `minis-config topic-help subagents`（LENS/FORGE 同该值），其他条目不外推。
- 子代理的工具/上下文能力按当前手册和实际运行面核，不外推两端；派发依 `luno-core/references/delegation.md`，身份采纳依review。尤其retry/resume后核任务、实际角色与模型组；`minis-sessions-cli status`只作可见字段证据，缺必要元数据标通道身份未验证，不以角色自述补齐。
- 分组 `contextLimitTokens` 决定生效窗口，**分组优先于模型条目**的 `contextWindowOverride`/`contextWindowTokens`；关掉「Limit Context Window」回落到条目值，再打开后**须回读当前分组的生效值**，不以历史观测代替。
- 模型不可用时按分组解析结果与报错判断，区分「配置已保存」「分组已绑定」「调用实际成功」。

## SOUL 与提示词
- `soul.body` 是生效值；与文件视图 `SOUL.md` 不一致时先判定当前生效版本，不自行挑一份覆盖其余。
- 写入：按 `minis-config --help`〈FIELD I/O〉用 `set soul.body --file`，文件内容必须是 **JSON 字符串**（`json.dumps(body, ensure_ascii=False)`），不是裸文本。`soul.body` 长度上限见 `minis-config topic-help soul`；改写常驻正文须核该预算，字节口径仍按 `body_contract.body_bytes`。
- 改写 `SOUL.md` 须保留 frontmatter，正文按 `body_contract.body_bytes` 提取；重组不额外追加 LF。文件正文、`soul.body` 与仓库正文按 UTF-8 bytes 判等，禁 strip/换行归一。

## 目录与持久化（记忆与真源）
- **记忆**：`memory_write` 写入 `/var/minis/memory/YYYY-MM-DD.md`；需每轮注入的偏好/约定可放入 `GLOBAL.md`——默认只读、由用户维护，AI 仅按用户明示修改，只承载本端约定、不作跨端真源。本端记忆边界依 `luno-memory/SKILL.md`；**跨端规则的生效真源在 Minis，候选只在隔离仓库编辑；写生效端前必须按 `luno-sync` 的〈轻量同步顺序〉执行**——技能正文 `/var/minis/skills/<name>/SKILL.md`、常驻提示词 `soul.body`（文件视图 `SOUL.md`）。记忆有误即更正或删除（判据、授权与诚实边界见 `luno-memory/SKILL.md`）；自动注入窗口与容量诊断按需读取入口〈资源与触发〉中列出的记忆注入资源，本文不复述。

## 技能登记

- **正文与元数据分离**：正文在 `/var/minis/skills/<name>/SKILL.md`，改文件即时生效；但技能页与系统提示注入的**元数据（描述、排序）存于 App 登记表**，改文件不刷新、重启也不重扫。
- **新建技能**：建目录/`SKILL.md`，frontmatter 含 `name`/`description`；App 自动按其登记，技能页核描述/排序。清单**会话开始时注入**，当前会话不见新登记；**新会话复核元数据**（清单可能截断，不保证完整）。已确认名称/路径的正文**当前即可按 `/var/minis/skills/<name>/SKILL.md` 只读加载**；能读正文≠登记已刷新。
- **刷新元数据**：备份内容（含附属文件；先列文件清单，凭据类文件只记位置不打开，无法安全完整备份则暂停删除重建）并核对哈希 → 技能页删除该技能（会连磁盘目录一起删）→ 用副本重建 → 核对新登记与内容一致。**只删磁盘目录无效**：登记记录仍在，放回去会复用旧元数据。
- `minis-config` 无 skills 字段，技能元数据只能走 App。

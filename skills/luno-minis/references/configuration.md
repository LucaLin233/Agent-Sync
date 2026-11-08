# Minis 客户端配置

本资源的操作只在Minis端可用。配置任务整份读取，不再按节裁剪；SOUL或技能写入仍须遵守〈记忆与生效真源〉，不得以整读代替实际生效字段回读。

## 配置接口

- **以 CLI 自述为准**：`minis-config` 的字段形态和路径写法、写入确认、审计回滚以及数组的 `--filter` 和分页语义，以当前的 `--help`、`list-topics`、`topic-help <topic>`（含 AUDIT、FIELD I/O）为准；同一会话、版本和主题已经完整读过的不重读，未知或版本变化时补读。必要时才整体列举；筛选和分页只缩小记录集，不能代替字段投影。
- **App 与 CLI 的分工**：技能和子代理只在平台实际支持的字段和动作上，App 页面与 CLI 等效，按用户方便选择，改完以回读为准；支持面以 `list-topics`/`topic-help` 为准。只有 App 能做的：新增子代理，技能元数据（描述、排序）及其刷新。技能正文可以直接改文件，但改文件不刷新元数据（见〈技能登记〉）。`minis-config` 没有 skills 字段。
- **`set-batch`**：`value_json` 必须是 JSON **文本**（多一层编码）。批量中任何一项失败，整批都会报 `partial_write_failed`，而且**同批已成功的项也可能没落盘**；失败后先逐项回读确认差异，只重写缺失的项。
- **环境变量**在 App 设置页维护；按变量名引用，缺失就说明并给出创建入口，不换来源。凭据类只读存在性和长度，取值不经过对话。

## 子代理与模型

- 子代理条目在 App UI 配置。内置的通用子代理在 `subagents.general.instructions`（roster 显示为 `builtin.general`）。instructions 的字符上限见 `minis-config topic-help subagents`（原核对记录中 LENS/FORGE 同值，原日期和版本未记录；当前值需重核），其他条目不外推。
- 子代理的工具和上下文能力按当前手册和实际运行面核对，不外推到两端；派发按 `luno-core/references/delegation.md`，身份和采纳按 `luno-review`。retry 或 resume 之后尤其要核对任务、实际角色和模型组；`minis-sessions-cli status` 只能作为可见字段的证据，缺必要元数据就标「通道身份未验证」，不用角色自述补齐。
- **生效窗口**由分组的 `contextLimitTokens` 决定，**分组优先于模型条目**的 `contextWindowOverride`/`contextWindowTokens`；关掉「Limit Context Window」会回落到条目值，再打开后**要回读当前分组的生效值**，不用历史观测代替。
- 模型不可用时，按分组的解析结果和报错判断，分清「配置已保存」「分组已绑定」「调用实际成功」三件事。

## SOUL 与提示词

- `soul.body` 是生效值；与文件视图 `SOUL.md` 不一致时，先判定当前生效的版本，不自行挑一份覆盖其他。
- **写入**：按 `minis-config --help`〈FIELD I/O〉用 `set soul.body --file`，文件内容必须是 **JSON 字符串**（`json.dumps(body, ensure_ascii=False)`），不是裸文本。长度上限见 `minis-config topic-help soul`，改写常驻正文要核对这个预算；字节口径按 `body_contract.body_bytes`。
- 改写 `SOUL.md` 要保留 frontmatter，正文按 `body_contract.body_bytes` 提取，重组时不额外追加换行。文件正文、`soul.body` 和仓库正文按 UTF-8 字节判等，不 strip，不归一换行。

## 记忆与生效真源

- `memory_write` 写入 `/var/minis/memory/YYYY-MM-DD.md`。需要每轮注入的偏好和约定可以放 `GLOBAL.md`：它默认只读、由用户维护，AI 只按用户的明示修改，只承载本端约定，不作跨端真源。记忆的边界、更正和诚实边界见 `luno-memory`；注入窗口和容量见本技能的记忆资源。
- **跨端规则的生效真源在 Minis**：技能正文 `/var/minis/skills/<name>/SKILL.md`，常驻提示词 `soul.body`（文件视图 `SOUL.md`）。候选只在隔离的仓库副本里编辑，写生效端之前必须按 `luno-sync` 的同步流程执行。

## 技能登记

- **正文和元数据分开存**：正文在 `/var/minis/skills/<name>/SKILL.md`，改文件即时生效；但技能页和系统提示里的**元数据（描述、排序）存在 App 的登记表里**，改文件不会刷新，重启也不会重扫。
- **新建技能**：建目录和 `SKILL.md`，frontmatter 含 `name`、`description`，App 会自动登记，到技能页核对描述和排序。技能清单在**会话开始时注入**，当前会话看不到新登记，要在**新会话里复核元数据**（清单可能被截断，不保证完整）。名称和路径已确认的正文，当前会话就可以按 `/var/minis/skills/<name>/SKILL.md` 只读加载；能读到正文不等于登记已刷新。
- **刷新元数据**：备份内容（含附属文件；先列文件清单，凭据类文件只记位置不打开，无法安全完整备份就暂停）并核对哈希 → 在技能页删除该技能（会连同磁盘目录一起删）→ 用备份重建 → 核对新登记和内容一致。**只删磁盘目录没用**：登记记录还在，放回去会沿用旧的元数据。

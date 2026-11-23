# Paseo 中文标题（Agent-Sync 工具）

本目录是 [Agent-Sync](https://github.com/LucaLin233/Agent-Sync) 的 Paseo 插件工具，源码与主插件目录一致，仅此子目录纳入仓库。

## 从 Agent-Sync 安装

```sh
REF=${REF:?填已核对的已合并提交}
paseo --home "$PASEO_HOME" plugin install \
  github:LucaLin233/Agent-Sync:tools/paseo-chinese-titles \
  --id paseo-chinese-titles --ref "$REF"
```

合并前请使用本分支的本地目录安装；不要把未合并的候选路径冒充 `main` 已发布内容。开发依赖固定 `@getpaseo/* 0.17.3` 是类型检查目标，不限制插件安装版本。

## 存储位置与旧状态迁移

插件状态不再把 `PASEO_HOME` 当文件系统路径，而是：

- 固定 base：`$HOME/.paseo/plugin-data/paseo-chinese-titles/daemons/`；
- 每个 daemon 一个 32 位十六进制 SHA-256 namespace（输入是 `PASEO_HOME`），因此不同 daemon 状态隔离；
- `helper/` 与 `bootstrap/` 也位于该 namespace 下。

旧版曾使用 `$PASEO_HOME/plugin-data/paseo-chinese-titles/state.json`。升级时由部署者一次性迁移，插件代码不读取旧任意路径：

```sh
NS=$(printf '%s' "$PASEO_HOME" | sha256sum | cut -c1-32)
OLD="$PASEO_HOME/plugin-data/paseo-chinese-titles/state.json"
NEW="$HOME/.paseo/plugin-data/paseo-chinese-titles/daemons/$NS/state.json"
mkdir -p "$(dirname "$NEW")"
# 在插件已 disable/停止写入的窗口内，单写入者串行复制
cp "$OLD" "$NEW.tmp" && chmod 600 "$NEW.tmp" && mv "$NEW.tmp" "$NEW"
```

保留旧文件作为回滚副本；不要在新旧版本同时运行时复制，避免重复命名。迁移后安装/更新从已合并提交构建的插件，再按实际需要启用。

## 兼容版本

- 目标与完整黑盒实测：Paseo **0.17.3**。
- manifest 下限：`>=0.16.0`。已静态核对 0.16.0 的 `@getpaseo/plugin` hooks（`workspace.create.after`、`agent.create.after`、`agent.turn.before/after`）、`PluginHandlerContext.paseo`、settings 注册与 client `useSettings`/`addSettingsScreen`；并核对 0.16.0 `@getpaseo/client` 的工作区 `create/setTitle/refresh/archive`、后台 workspace/agent 参数、agent `run/refresh/archive` 与 provider 入口。CLI `--home`、`workspace create --background`、`project rename`、`agent update --name` 为该下限的安装/更名依赖。
- 实际以 0.16.0 CLI/daemon 干净安装：`plugin ls` 为 `running`；普通目录项目得到 `项目 proj`，英文首任务工作区得到 `修复 0.16 login bug`。0.16.0 的会话 agent 自动标题未实测通过：该 smoke 中 `plugin install` 重建了 plugin-settings，测试设置未在安装后重新写入，`autoNameSessions` 为默认 `false`，所以只覆盖项目与普通目录工作区；未证实接口不兼容。0.17.3 会话自动标题已实测。

---

## 主插件说明

面向 **Paseo 0.17.3** 的本地插件。它只写显示覆盖：

- 新登记项目：生成一次简体中文侧栏名称；
- 新工作区：收到首个真实任务时生成一次中文标题；
- 新普通会话（可选）：收到首个真实任务时生成一次中文标题。

不写目录、仓库或 Git 分支。项目标题写入 Paseo 的 `customName`，工作区/会话标题写入 `title`；桌面和手机连接同一个 daemon 时看到同一份持久结果。

## 安装

在目标 daemon 所在主机执行，`--home` 必须是同一个 `PASEO_HOME`：

```sh
PLUGIN_ID=paseo-chinese-titles
paseo --home "$PASEO_HOME" plugin install /absolute/path/to/paseo-chinese-titles --id "$PLUGIN_ID"
paseo --home "$PASEO_HOME" plugin ls --json
```

安装后插件应显示 `status: "running"`。插件没有构建步骤；`package.json` 的 `devDependencies` 只用于源码类型检查。分发包可只含本仓库的源码文件，不依赖本地 `node_modules`。

修改源码后：

```sh
paseo --home "$PASEO_HOME" plugin reload "$PLUGIN_ID"
```

卸载：

```sh
paseo --home "$PASEO_HOME" plugin remove "$PLUGIN_ID"
```

## 设置

设置入口：Paseo 设置 → 插件 → Paseo 中文标题。也可直接编辑 host 设置文件：

`$PASEO_HOME/plugin-settings/paseo-chinese-titles/chinese-titles.json`

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `autoNameProjects` | `true` | 新项目生成一次中文名称 |
| `autoNameWorkspaces` | `true` | 新工作区首个真实任务生成中文标题 |
| `autoNameSessions` | `false` | 新普通会话首个真实任务生成中文标题；默认关闭，保留 Better Paseo 管会话标题 |
| `provider` | 空 | 留空自动选择 daemon 已就绪的 Codex provider 或其别名（`extends: "codex"`）；只允许 Codex 系列，不会选 Pi |
| `model` | 空 | 留空使用所选 provider 默认模型 |
| `thinkingOptionId` | 空 | 留空使用模型默认思考档 |
| `projectMaxChars` | `20` | 项目名称上限 |
| `titleMaxChars` | `28` | 工作区/会话标题上限 |
| `paseoBin` | `paseo` | 官方 CLI 可执行文件；daemon 的 PATH 找不到时填绝对路径 |

插件不读取 provider 密钥、Codex 登录态或 daemon 凭据文件。模型调用复用 daemon 已配置的 provider 入口；项目/会话更名调用官方可信 CLI，CLI 自己连接同一 daemon。

## Better Paseo 共存

Better Paseo 1.6.4 的 **「自动优化新任务标题」**（设置里的 `afterFirstReply`）默认关闭。使用本插件的会话命名时：

1. 先在 Better Paseo 设置中关闭 **Tasks →「自动优化新任务标题」**，即 `title-generation.json` 的 `values.afterFirstReply: false`；此时 Better Paseo 不再在首条消息开始时自动优化 agent 标题；
2. 确认 Better Paseo 的 `title-generation.json` 仍是 `afterFirstReply: false` 后，再把本插件的 `autoNameSessions` 打开；
3. Better Paseo 的手动「从对话生成标题」仍可继续使用；它只在用户主动操作时运行。Better Paseo 的 agent 自动标题还有一个边界：只有在 `workspace.name === previousTitle` 时才顺带改写工作区标题；本插件不修改 Better Paseo 配置，也不依赖这个条件。

本插件的辅助会话同时带 `paseo-chinese-titles.helper=1` 和 `better-paseo.purpose=title-generation` 标签，Better Paseo 会跳过它；本插件也跳过带该标签、`background` 或 `paseo.parent-agent-id` 的会话。

## 行为与边界

- **项目**：SDK 没有项目更名方法，插件用官方 CLI `project rename` 写入 `customName`。写入前重新读取 `projectCustomName`；已有手动值直接跳过。无 app 连接时，插件用官方 CLI 定时 `project ls` 只发现新 `projectId`，再在插件专属中性目录下创建一个 **background directory workspace**（`workspace create --isolation local --path .../bootstrap --project <id> --title 中文标题引导 --background`）。这个 workspace 的 `workspace.create.after` 提供同 daemon 的 `context.paseo`，插件随后走正常 SDK 项目流程并归档它。每进程最多一次成功引导；只归档精确路径、`background`、同 project 且本进程发起的引导 workspace。
- **工作区/会话**：通过 hook 自带的 `context.paseo` 生成。只会话命名只调用一次；同一首任务同时命名工作区和会话且该会话是获胜会话时，只生成一次并复用；竞争中的非获胜会话在工作区结果之外单独生成一次自己的会话标题。每个对象只写最终中文名一次，写后重新读取原始 `title` 覆盖值。**没有 CAS**：如果手动改名恰好落在最终 `refresh` 与写入之间，仍可能被本插件覆盖；插件只写一次，不重试、不写 placeholder，写入前看到已变化才跳过。
- **首任务判断**：不看创建顺序。workspace claim 内读取所有非后台、非子会话的首条真实用户消息，按 timeline entry 时间戳选最早者，同一毫秒用 agent ID 固定 tie break；由该获胜会话决定工作区标题。最早创建但一直没收到任务的空会话不会阻塞后创建会话先收到任务；两个会话都已有任务时也不会都返回 false。并发多 agent 由进程内 workspace claim 保证工作区只命名一次。
- **模型输出校验**：去掉 JSON/引号/Markdown/标签后只取一行；必须包含汉字，否则视为无效。英文、空、只有产品名、控制字符都走中文兜底。兜底会保留 ASCII 产品/模块名，并保证截断后最终仍含汉字（例如 `修复 login bug`、`处理 Paseo`）。
- **保留已有和手动名称**：首次启用时用官方 CLI 列表建立基线，已有对象不改。工作区/会话只有当前 `title` 为空或仍等于 Paseo 的 provisional 首 prompt 文本时才处理；显式标题或手动改名会跳过。
- **辅助会话**：中性目录、`background`、固定标题、只读 sandbox、`approval_policy: "never"`、禁用 web search、无预批准工具。辅助会话不进入本插件或 Better Paseo 的自动命名。
- **Paseo 内置 workspace-auto-name**：0.17.3 daemon 也会在创建带首 prompt 的 workspace 时写 provisional title，并可能重命名 branch-off 的占位分支；没有受支持的关闭开关。本插件只写 `title`，不写 branch。若严格禁止分支变化，创建 worktree 时显式给 `--new-branch`，并接受内置标题生成仍可能与插件竞争；两者都遵守“手动标题优先”的重新读取规则，但无 CAS。
- **侧栏显示**：Paseo 的侧栏可按「标题」或「分支」显示。切到「分支」时看到的是 Git 分支名，不是本插件写入的标题；切到「标题」才能看到同一 daemon 持久的中文标题。

## 验收与限制

已在本机 0.17.3 隔离 daemon 实测：

- 最终 `npm pack` 目录无 `node_modules`，官方 `plugin install` 后 `plugin ls` 为 `status: "running"`。
- 普通目录英文首任务 `Fix login bug` → 工作区与 agent 均为 `修复 login bug`；项目无 app 连接时经 CLI 引导后为 `项目 dirproj`。
- Git worktree 使用显式 `--new-branch keep-branch`，运行任务后分支仍为 `keep-branch`，工作区/agent 为 `实现 auth flow`。
- 手动 workspace `手工工作区`、显式 agent `人工标题` 均保留。
- 同一 workspace 并发/先后两条不同会话：工作区只命名一次，后续会话只命名自己；双并发两个不同 workspace 时各自标题正确。
- `plugin reload` 后名称保持；精确路径的引导 workspace 已归档，普通同标题 workspace 未被归档。
- Better Paseo **1.6.4**（本地可核副本 `version=1.6.4`、`build=202611211751`）与插件同装运行；其 `title-generation.json` 的 `afterFirstReply=false` 时，新工作区/会话由本插件得到 `优化 cache metrics`，自动优化未接管。

未覆盖：A 空会话/B 首任务 E2E 受官方 CLI `paseo run ""` 的 `MISSING_PROMPT` 限制，仅保留 `pickFirstTask` 单元测试；真实 Codex 鉴权下的模型成功回复、桌面/手机 UI、Better Paseo 手动“从对话生成标题”未实测。无 Codex 凭据时走中文兜底，不影响最终含汉字。

### 最小 smoke 复跑

```sh
# 1. 只使用独占合成 HOME/PASEO_HOME/CODEX_HOME，不读取真实登录态
D=$(mktemp -d); mkdir -p "$D/home" "$D/codex" "$D/proj"
cat > "$D/home/config.json" <<'JSON'
{"daemon":{"listen":"127.0.0.1:18888"},"agents":{"providers":{"codex":{"enabled":false}}},"pluginsEnabled":true}
JSON
env -i HOME="$D/home" PASEO_HOME="$D/home" CODEX_HOME="$D/codex"   PASEO_NODE_ENV=development PATH="$PATH" TMPDIR=/tmp   paseo daemon run --home "$D/home" &
# 2. 安装 npm pack 解包后的目录
env -i HOME="$D/home" PASEO_HOME="$D/home" CODEX_HOME="$D/codex" PATH="$PATH"   paseo --home "$D/home" plugin install /path/to/packed-plugin --id paseo-chinese-titles --json
# 3. 预期：plugin ls 为 running；新项目出现汉字；英文任务后工作区/agent 为中文兜底；
#    显式 new-branch 的 worktree 分支不变；手动改名后 reload 仍保持。
```

> 侧栏切到「标题」才能看到本插件写入的持久标题；「分支」显示的是 Git 分支。

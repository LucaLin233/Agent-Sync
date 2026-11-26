# Codex 动态模型目录适配器

一个仅监听本机回环的 Node 服务，把若干**固定**网关目录转换成本机 Codex 可读的动态模型目录。它只负责「目录发现」，不代理推理请求。

适用范围：本机运维自行配置上游与档位，Codex 通过 `model_catalog_url` 读取本服务。它不是通用网关，也不支持远程或多租户暴露。

## 为什么需要它

Codex 允许 provider 用 `model_catalog_url` 拉取模型清单，但要求条目符合它自己的模型 schema。各网关返回的形状、可用档位和模型 ID 并不一致：

- 某个网关的目录只列出对话模型，向量模型出现在另一个接口；
- 同一模型在不同网关可用的速度档位不同，不能互相继承；
- 某些模型的思考档位由模型自身决定，必须按模型声明。

本服务把这三件事显式配置化，每条路由独立，互不影响。

## 安全边界

- 只监听回环：`listen.host` 必须是 `127.0.0.1` 或 `::1`，其他值启动即拒绝；不支持远程监听。
- 只接受 `GET` 和精确匹配的已配置路径；其余请求在发出任何出站请求前就返回 401/404/405。
- 必须有调用方 `Bearer`；该令牌只转发给**该路由**配置的上游。令牌不记录、不落盘、不回显。
- 不使用调用方提供的任何目的地址、查询值或额外头。客户端带来的查询参数（如 `client_version`）不会转发。
- 所有上游调用都 `redirect: 'error'`（拒绝跟随重定向），并有单项超时；响应体有长度上限。
- 配置里的 URL 不得内嵌用户名或密码（`userinfo`），也不得带 `#fragment`；凭据只有调用方 `Bearer` 一个来源。
- 需要同一个 `Bearer` 的补充目录必须与主目录**同源**；匿名元数据允许跨源，因为它不带凭据。

## 配置字段

配置文件的路径由启动参数给出，因此有明确的输入边界：必须是**绝对路径**；解析软链后必须位于默认目录 `/etc/codex-catalog/`，或位于**服务的工作目录**之内（工作目录由启动器决定，不来自请求或参数；工作目录为 `/` 时它不额外放宽任何路径，默认目录照旧可用）；必须是常规文件、不超过 256 KiB，且读取时对最后一段使用 `O_NOFOLLOW`，防止检查后把文件换成软链。越界、相对路径、目录或超限都在启动时以退出码 2 拒绝。

完整样例见 [`catalog.example.json`](catalog.example.json)。样例里的 `baseCatalog` 路径只作示意，启动前要换成目标机器上真实存在的官方 `models.json`，或删掉该字段。未知字段一律在启动时拒绝（退出码 2），不会悄悄忽略，以免拼写错误看起来「生效」。

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `listen.host` | 否 | 回环地址，默认 `127.0.0.1`；非回环会被拒绝 |
| `listen.port` | 否 | 默认 `18923`；`0` 表示由系统分配（仅测试用） |
| `baseCatalog` | 否 | 上游 Codex `models.json` 的路径，作为官方模板来源 |
| `limits.*` | 否 | 各超时与长度上限，见下表 |
| `routes.<path>` | 是 | 路由键就是客户端请求路径，必须精确匹配且以 `/` 开头 |
| `routes.<path>.gatewayLabel` | 是 | 出现在未知模型的描述里，例如 `Listed by the <label> gateway.` |
| `routes.<path>.upstream` | 是 | 主目录固定 URL；`https`，或指向回环的 `http` |
| `routes.<path>.inheritBaseTiers` | 否 | 默认 `false`：不从 `baseCatalog` 继承 `service_tiers` 等速度字段 |
| `routes.<path>.metadata.url` | 否 | 匿名公共元数据 URL，只补充数值，不增删模型 |
| `routes.<path>.metadata.timeoutMs` | 否 | 覆盖 `limits.metadataTimeoutMs` |
| `routes.<path>.supplement.url` | 否 | 补充目录**完整** URL（含固定 query）；须与 `upstream` 同源 |
| `routes.<path>.supplement.allowIds` | 是 | 允许从补充目录追加的精确 ID 白名单，非空 |
| `routes.<path>.supplement.modelDescriptions` | 否 | 为补充模型给出明确描述 |
| `routes.<path>.supplement.timeoutMs` | 否 | 覆盖 `limits.supplementTimeoutMs` |
| `routes.<path>.models.<id>.*` | 否 | 按模型覆盖，见〈模型元数据与档位〉 |

`limits` 默认值：`upstreamTimeoutMs` 4000、`metadataTimeoutMs` 1200、`supplementTimeoutMs` 2500、`totalBudgetMs` 4500、`maxBodyBytes` 524288、`maxMetadataBytes` 131072、`maxModels` 200。

Codex 用 5 秒预算刷新目录，所以主请求超时取 4 秒，`totalBudgetMs` 封顶 4.5 秒。补充与元数据请求与主请求**并行**发出，不累加延迟；超出预算即放弃该跳，主列表照常返回。

固定 query 必须写在 `supplement.url` 里，例如 `https://gateway.example.invalid/v1/models?api_type=openai`。服务不会自己拼接 `?`；单独写 `supplement.query` 会启动失败，以免出现「URL 已带 query 再拼一次」的歧义。

## 模型元数据与档位

每条路由可对单个模型覆盖以下字段：

| 字段 | 说明 |
| --- | --- |
| `description` | 模型描述 |
| `reasoningLevels` | `supported_reasoning_levels`，数组，每项 `{effort, description}` |
| `defaultReasoningLevel` | `default_reasoning_level` |
| `serviceTiers` | `service_tiers`，数组，每项 `{id, name, description}` |
| `additionalSpeedTiers` | `additional_speed_tiers`，字符串数组 |
| `defaultServiceTier` | `default_service_tier` |

`service_tiers` 每个字段在 Codex 侧都是字符串类型（`id`/`name`/`description`）；`description` 在配置里可省略，省略时归一为 `""`。从 `baseCatalog` 模板继承来的档位也做同样归一，因此响应里不会出现 `null`、缺失或非字符串的 `description`。

速度档位是**按路由、按模型**声明的，不做跨网关继承：

- 有上游证据时显式写 `serviceTiers`（例：`priority`「Fast」、`ultrafast`「Ultrafast」）；
- 没有证据就什么都不写，该路由不会因此继承别的路由的档位；
- `inheritBaseTiers` 只在希望沿用 `baseCatalog` 中同一模型的速度字段时设为 `true`。

同一型号在多个网关上都有 Fast/Ultrafast 时，**每个路由各写一份**，不要靠 `inheritBaseTiers` 或模块间共享常量互通——那正是把某网关的能力误当成另一网关能力的地方。样例的 `/alpha` 与 `/beta` 两条路由都给 `gpt-6.2-sol`、`gpt-6.2-astra` 各写一份 Fast/Ultrafast，但 `/beta` 的 `inheritBaseTiers` 为 `false`，演示了这种隔离。档位声明只证明配置表达，不证明网关真的接受该档位；真实可用性须单独实测。

思考档位同理。样例给两条路由的 `deepseek-flash` 都写了只支持 `none/low/high/max` 且默认 `none`：

```json
"models": {
  "deepseek-flash": {
    "reasoningLevels": [
      { "effort": "none", "description": "No extra reasoning; fastest responses" },
      { "effort": "low", "description": "Fast responses with lighter reasoning" },
      { "effort": "high", "description": "Greater reasoning depth for complex problems" },
      { "effort": "max", "description": "Maximum reasoning depth for the hardest problems" }
    ],
    "defaultReasoningLevel": "none"
  }
}
```

`gpt-6.2-sol` 与 `gpt-6.2-astra` 的六档推理（`low/medium/high/xhigh/max/ultra`，默认 `low`）不写在样例里，而是从 `baseCatalog` 模板继承。这只在 `baseCatalog` 确实指向含这两个型号的官方 `models.json` 时成立：模板缺失时它们会退化成无推理档的最小条目，认不出既有能力。样例的 `baseCatalog` 路径只是占位，部署时须换成真实文件。

若提供 `baseCatalog`，未覆盖的字段沿用上游模板里的官方能力（例如 `context_window`、`input_modalities`）。未知模型只输出最小的结构必填项，不推断上下文窗口或提示词正文。

## 补充目录

某网关的补充分录可能需要与主目录相同的 `Bearer`。为此服务要求补充 URL 与主 URL 同源，且只接受 `allowIds` 里的精确 ID：

```json
"supplement": {
  "url": "https://gateway.example.invalid/v1/models?api_type=openai",
  "allowIds": ["text-embedding-3-small"],
  "modelDescriptions": {
    "text-embedding-3-small": "Text embedding model listed by the gateway; returns embeddings, not chat completions."
  }
}
```

上游返回的其他 ID 一律丢弃，已在主列表中的不重复追加。补充请求的 500、解析失败、重定向、超时都只让补充项缺席，主列表与状态码不受影响；主请求自身的错误语义（401/403 透传，其余 502）保持不变。

匿名 `metadata` 与补充目录不同：它不带凭据，可跨源，只用于给主列表已有 ID 补充厂商数值。

## 服务启动

```sh
node /opt/codex-catalog/catalog-server.mjs --config /etc/codex-catalog/catalog.json
```

也可用环境变量指定配置：`CATALOG_CONFIG=/etc/codex-catalog/catalog.json node catalog-server.mjs`。监听地址与端口来自配置，不读取命令行参数。

配置不必放在默认目录：把配置目录设为服务的**工作目录**即可，不新增环境变量。

```sh
cd /srv/codex-catalog && node /opt/codex-catalog/catalog-server.mjs --config /srv/codex-catalog/catalog.json
```

这两条边界只约束**配置文件自身**的读取位置，不影响 `baseCatalog`、上游 URL 或任何出站请求，也不放宽监听与路由。工作目录由启动器决定，不从请求或 `--config` 参数推导；`--config` 与 `CATALOG_CONFIG` 两个入口都仍然可用，且都必须写绝对路径。默认部署（配置放 `/etc/codex-catalog/`）在任意工作目录下都可用。

systemd 单元示例（本机专用，`ProtectSystem` 等按目标环境核对）：

```ini
[Unit]
Description=Codex model catalog bridge (loopback)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=codex-catalog
Group=codex-catalog
ExecStart=/usr/bin/node /opt/codex-catalog/catalog-server.mjs --config /etc/codex-catalog/catalog.json
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
```

服务本身不需要任何凭据变量：它转发调用方的 `Bearer`。凭据只注入到启动 Codex 的进程，按各部署既有方式提供。

## 接入 Codex

在 Codex 的 provider 配置里指向本服务某条路由：

```toml
[model_providers.example]
name = "Example"
base_url = "https://gateway.example.invalid/v1"
env_key = "EXAMPLE_GATEWAY_KEY"
wire_api = "responses"
requires_openai_auth = false
model_catalog_url = "http://127.0.0.1:18923/alpha/v1/models"
```

`env_key` 写的是**变量名**，不是密钥值。宿主按获准方式把该变量注入 Codex 进程；本服务只把该进程送来的 `Bearer` 转给对应上游。

每条路由对应一个 provider。想让不同 provider 使用不同网关/档位，就在配置里各写一条路由、各配一个 `model_catalog_url`。

## 快速自检

先确认服务在监听，再带令牌取目录（令牌从已注入的变量读取，不要写进命令或日志）：

```sh
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18923/alpha/v1/models
```

未带凭据应返回 401。带凭据时可用同样的 URL 查看返回的 `models[].slug`、`service_tiers` 与 `supported_reasoning_levels`，核对是否符合配置。

## 运维与回滚

- 改配置后重启服务（`systemctl restart`）；配置非法会直接以退出码 2 失败，不会带着错误配置运行。
- 回滚：恢复上一版配置文件并重启。建议把配置放在版本化目录，并保留上一版文件。
- 本服务只读目录、不写业务数据；回滚不涉及数据迁移。

## 测试

离线回归只用 Node 标准库，全部使用合成输入与回环夹具，不需要网络或生产环境：

```sh
node --test platforms/paseo/codex-catalog/test/*.test.mjs
```

覆盖：路由与鉴权隔离（未通过鉴权的请求零出站调用）、不转发客户端查询、配置里固定的 query 原样送达且不被二次拼接、补充目录的同源/白名单/失败降级与 `maxModels` 上限、主请求错误语义、按路由区分的思考档位与速度档位、继承模板档位的字符串归一与畸形档位剔除、匿名元数据不带凭据、URL 内嵌凭据/`#fragment`/未知字段/跨源补充被拒、非回环监听被拒、日志不含令牌或上游 URL。这些是配置与协议层的行为测试，不证明任何真实网关的能力。

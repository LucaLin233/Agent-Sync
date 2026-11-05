#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立版本化的技能部署入口（P2a 第 25 项）：**默认只打包**，`--deploy` 才允许上传／安装。

用法：
  python3 -B tools/deploy_skill.py --repo <审定仓库> --src <显式技能目录> --name <技能名> \\
      --key <既有 R2 对象 key> --out-dir <已授权资产目录> --expect-id <登记平台 ID> [--deploy]
      [--expect-zip-sha256 <完整 64 位小写十六进制>]

接口与边界：
  · `--src` **必填且显式**（相对 `--repo` 或绝对，须落在 `--repo` 内）；**不用环境变量、不按
    名称猜源目录**：登记源若位于 `skills/upstream/` 下，不得按技能名改写成 `skills/<name>`。
  · `--repo` 下 `tools/sync-targets.json` 是唯一登记真源：对象名／源路径／平台 ID 必须与参数
    **完全一致**；`--expect-id` 直接用于回读，**不按名称取列表第一项**。辅助模块
    （`pack-skill-zip.py`／`body_contract.py`）也只从 `--repo/tools/` 加载，**无回退**。
  · 默认只把包写到 `--out-dir`（原子写出、固定 0644、失败不覆盖已有产物）。**只有 `--deploy`**
    才允许读平台、下载部署前回滚包、上传、install、回读判等；`tools/sync-all.sh` **不调用本入口**。
  · `--deploy` 的**防误触断言**：环境变量 `LUNO_DEPLOY_AUTHORIZED=1` **不是授权来源**——
    须由主助理**先核既有部署授权**再传 `--deploy`；断言不过即拒绝，且在**任何写操作之前**
    （含候选包写出）返回，不产生任何写操作。
  · **候选哈希门禁（可选，写前零写路径）**：`--expect-zip-sha256 <完整 64 位小写十六进制>`
    给出时，本次**内存构包**的 `sha256` 必须与其**逐位相等**，否则固定分类失败（rc=2）——此时
    平台／存储尚未被访问，**零 R2 读取／零上传／零 install／零 edit**，候选包也**不写出**到
    `--out-dir`（失败不留半成品）。值须为完整 64 位小写十六进制（缩写、大写、`sha256:` 前缀等
    一律按格式无效拒绝，且**不回显**该值）；不给该参数＝不启用该门禁，行为与旧调用完全一致。
    该断言在**只打包模式同样生效**（位置：打包与包有效性之后、写产物与 `--deploy` 分支之前），
    用于核对「已核实的通用包」与本次实构包是否为同一对象；它**不替代**平台 `zipFileHash` 核对、
    来源身份核对、上传前源端复核与未变对象只读分支。
  · **专用打包器复用（本批）**：登记源路径命中 `DEDICATED_PACKERS`（当前仅
    `skills/luno-surge` → `skills/luno-surge/scripts/package_release.py`）时，收集／构包改用该
    技能自带的专用器（过滤名单、符号链接与非普通条目守卫、秘密检测、ZIP 布局都由它持有），
    通用器与专用器共用 `collect(root)`／`build(entries)` 两个内存接口，故源端复核的两个检查点
    用的也是**同一个**专用器。专用器路径固定、按 `--repo` 加载，**模块缺失即固定分类失败，
    不回退通用器**；其异常（含以 `SystemExit` 报错）一律转本地 rc=2，只报异常类名，不回显
    消息或命中值。该技能的 `--deploy` **必须**显式给出 `--expect-zip-sha256`，且缺摘要时在
    **加载专用器之前**就 rc=2（零产物／零远端）；`run_deploy` 另做一次防御性复核。
    纯打包（无 `--deploy`）不强制该参数；其他技能行为完全不变。
  · 本批（未实施第 24 项）沿用的**源准入**规则：源文件模式必须是 0644，含 0755 等非常规权限
    文件即**明确拒绝**并指向 P2b，**不**悄悄压平权限。**源准入模式（对源文件的检查）与产物
    文件模式（`--out-dir` 内 0644）及 ZIP 成员模式是三个不同概念**：通用器把成员统一写
    `0o644<<16`；专用器按既有 `os.access(X_OK)` 语义写 `S_IFREG|{644,755}`。ZIP **成员在内存
    构建**（不影响源文件）；**仅全部校验通过后**才写出候选或进入部署，源准入不通过即无产物。
    故本批不改变任何模式策略、也不 chmod。
  · 资源完整清单由本文件内置函数核对审定仓库离线包与同一登记快照
    （无子进程依赖）；错误仅输出固定类别与可信化的对象／路径，不回显未经校验的登记自由文本。
  · 平台只读**带源端字段白名单**：`skill view` 只取
    `id,identifier,name,description,content,zipFileHash,resources`（**不取** `source`／
    `manifest`，避免把签名 URL 带进内存）；资源集取**同一次 view 返回的顶层 `resources`**
    （`Record<VirtualPath,{size,fileHash}>`，与官方 `agentSkill.ts` 定义一致），
    **不再单独启动 `skill resources`**（树形态 CLI 与之一并取消）。
  · 存储与凭据**全部**取自环境变量（`CF_ACCOUNT_ID`／`R2_ACCESS_KEY_ID`／`R2_SECRET_ACCESS_KEY`
    ／`R2_BUCKET`），**不设默认值**：**桶名与 key 均须显式给出，工具不持默认值**；缺一即拒绝
    并按**变量名**报缺，从不展示值。SDK 层存在**有界传输重试**（客户端 `max_attempts`），本入口
    不重复无界重试，也不声称底层请求只尝试一次。
  · 秘密面：预签名 URL、认证值、SDK／CLI 原始失败 stdout／stderr **不进**日志／报告／产物；
    失败只报**固定阶段**＋异常**类名**（不回述原始报文），URL 只在内存中传递、不落盘。
  · **SDK 静音边界**：`boto3` 导入、客户端创建、`download`／`upload`／`presigned_get` 每一次
    调用都在同一边界内执行——SDK 自身的 stdout／stderr 与 logging **一律丢弃**，只向外给固定
    阶段、状态与所需结果。
  · 上传前**证明所写 bucket／key 是该对象既有来源**：平台条目 `identifier` 须为 URL 型
    `url.<CF_ACCOUNT_ID>.r2.cloudflarestorage.com.<bucket>.<key>`；按**首个点号**切出 bucket／key
    并与本次 `R2_BUCKET`／`--key` 完全比对，形态不可解析（如 `create` 型 `user.…`）或任一项不符
    即 **fail-closed 拒绝部署**——**不用「ZIP 相同」推定 key 相同**；来源里的签名查询参数不输出。
  · 部署前能力不成立（平台部署前 `zipFileHash` 不是完整 64 位十六进制，或同 key 现存对象与
    该哈希不符）即**停止部署**；回滚包按**实读** sha256 复核，不用部署后包充当回滚包。
  · **同域前置＝硬门槛（零上传）**：部署开始前先用 `tools/resource_http.py`（经 `load_module`
    加载，**无回退**）的 `connection_context()` 冻结一次 `(origin, key)`，并按**同一**
    `(origin, key)` 冻结受控 CLI runner（见下）。任一不成立——origin 与受批准实例不符／缺指定
    key／key 含非法字符／显式 `LOBEHUB_WORKSPACE_ID`／`lh` 无法解析为绝对 argv——即**固定分类
    失败**（rc=2），在**任何平台或存储访问之前**停止：零 HTTP、零 R2 读取／上传、零 install、
    零 edit。**不退回登录态、不改用其它实例、不退回逐资源 CLI `read-resource`**。
  · **受控 CLI runner**：`lh` 在**原环境**用 `shutil.which` ＋ realpath 解析一次并冻结为**绝对
    argv**，此后所有 CLI 调用（`view`）都用该
    argv，**不经 PATH 的 shim 解析**；CLI 子进程 env **只含** `PATH`／`HOME`／`XDG_CONFIG_HOME`
    ／`XDG_DATA_HOME`／`XDG_CACHE_HOME`／`NODE_COMPILE_CACHE`／`LOBEHUB_SERVER`（＝冻结
    origin）／`LOBEHUB_CLI_API_KEY`（＝冻结 key），**不继承** `LOBEHUB_WORKSPACE_ID`、JWT、代理
    等；每次运行新建**空 HOME/XDG**（`tempfile.mkdtemp`，子目录 `cfg`／`data`／`cache`），**不读任何
    登录态文件**，收尾（含异常路径）删除该目录；`PATH` 取受批准的**最小**目录集并排除任何名为
    `shims` 的目录。CLI 与 HTTP 由构造处于**同一** `(origin, key)`：同域由构造保证。
  · **CLI 启动开销**：CLI 子进程另得一个**运行期私有**的 Node 官方模块编译缓存目录
    （`NODE_COMPILE_CACHE`，见 `COMPILE_CACHE_DIR`），只为让同一次运行内的多次 `lh` 调用复用
    V8 代码缓存、不重复编译官方 bundle；该目录 0700、位于 runner 的临时根内、随收尾一并删除，
    且**只可能装官方模块代码**（不接收正文、凭据或平台数据）。该变量属**纯优化、可省略**：缓存
    目录建不出来（权限／配额／平台限制）即**省略该变量**照常跑 CLI（`CliRunner.OPTIONAL_ENV_KEYS`），
    Node 不支持它（<22.1）时也会忽略——两种情况都**不改变任何 CLI 的 rc／stdout、不吞业务错误、
    不阻断部署**；HOME／XDG 仍 fail-closed。
  · 资源**路径集与逐项元数据**取自**同一次** `skill view` 的顶层 `resources`（官方
    `SkillResourceMeta`＝`Record<VirtualPath,{size,fileHash}>`）：每个值的嵌套字段**只接受**这两个
    已知键，未知键／缺键／非法路径／size 或 fileHash 类型不符即**固定分类失败**；空值（`null`／
    `{}`）按已核平台约定严格允许为空集，其它形态失败。**`resources` 键本身必须存在**（缺键＝失败，
    不得由 `get` 投影抹成空集／`None`）；路径合法性**复用已加载的** `tools/resource_http.py`
    `valid_path`（生产零新依赖，不再维护第二份校验器）。失败文案**只报固定分类、已知字段名、类型名
    或数量**——外部路径、未知字段名与字段值一律**不回显**（对象键不保证非秘密，控制字符还可能注入
    日志）。该字段与 bytes 判等**同时**生效（**不以 size／hash 判等代替逐字节比较**）；原独立启动的
    `skill resources`（树形态）随之取消——每包少一次 CLI 启动。
  · 资源 bytes 回读经**同一** HTTP 客户端：用 `ResourceClient(deadline, context)` ＋
    `collect(..., workers=4)` 有界逐资源取回**原始 bytes**；`planned` 项的 `(path, size, sha256)`
    **一律取自不可变候选 ZIP 内该资源的 bytes**，取回后仍与该包内 bytes **逐项严格比较**（不因
    客户端已校验过 size／hash 就放行）。HTTP 侧 401／403、429、重定向、截断、预算耗尽或完整性
    失败一律**失败**（不改判为元数据通过、不盲重试）。并发固定 4，仍逐资源校验，首错停发并关闭连接。
  · **官方写入走 HTTP（install／edit）**：安装与正文补写**不再启动 CLI**，改用官方 tRPC mutation
    （`agentSkills.importFromUrl`／`agentSkills.update`，见 `write_skill_http`），与资源回读共用同一已冻结 `(origin, key)`；
    请求体／URL 只在内存；响应体**有界读**（≤64 KB，只解析 tRPC 信封：出现 `error` 即失败、200 但非
    `result` 形态同样失败，日志只带 `status` 与错误 `code`，**不回显** message／body／URL／header），
    且须 `status == 200` 与 MIME `application/json`（可带参数），随即关闭连接；**install 不重试**，
    `edit` 仅在传输异常与 5xx（含 502／503／504）时最多重试 2 次（间隔 250／500 ms），4xx 与错误信封
    不重试；**不 fallback 到 CLI 重复写**。因此 **HTTP 200 绝不等于“安装／补写成功”**：成功一律以随后的
    **完整白名单回读**为准（与官方 CLI 的差别见 `write_skill_http` 文档串，属**非等价**）。正常部署
    （首次回读即通过）的 CLI 启动数仍为 `view` ×2；修补路径先做一次**写前基线复核**（每次 `update`
    尝试各一次 `view`：**先**判 id／zipFileHash，任一不一致即**零写入**停止，再判第三个值即停止），
    再按 0／0.5／1／2／4 s 轮询（总 ≤10 s，**含单次读取**：每轮读带上剩余预算、返回后再复查是否已
    超预算；每轮都先判 id／zipFileHash，任一轮差异即停止），每轮一次 `view`，相等即停。**所有**回读
    路径（部署前 `view`／安装后 `view`／写前复核／轮询每轮）都带剩余预算（≤10 s），不留 `timeout=None`。
  · **源端复核（部署窗口）**：候选 ZIP 一经打包即本次部署的**唯一**对象。**上传前**（与「进入未变
    对象只读分支」同一位置，两个分支都经过）与**安装后、全部资源回读之后、成功返回前**各按**同一判定函数**复核一次
    源文件集与逐文件 bytes：不一致时**不重新打包替换候选**；上传前命中 ⇒ 未进入写路径的固定分类
    失败（rc=2，零 R2 读取、零上传、零 install、零 edit），安装后命中 ⇒ 写路径后的固定分类失败
    （rc=1，文案说明「部署已写入完成，但源目录在部署窗口内发生变化，须人工确认是否重投」）。
  · **未变对象只读分支**：部署前 `skill view` 的 `zipFileHash` 等于候选 ZIP sha256 时，仍完成
    id／来源身份（`source_identity`）／name／description／正文／资源路径集与逐项
    size／fileHash／全部资源 bytes 核验（路径集与元数据取自**该次** `view` 的 `resources`），
    全部一致才输出固定文案「**核验一致，未执行部署写入**」并 rc=0；**零 R2 上传、零 install、
    零 edit**（SDK 初始化推迟到确需存储写入的分支）。任一差异一律 fail-closed 并停止（**不得报
    跳过成功**）；正文「恰少一个尾 LF」形态在该分支下也**不**用 edit 修补，须停止并回报——此时
    **未进入写路径 ⇒ rc=2**。
  · **分阶段 wall 计时**（打包／平台回读／源端复核／回滚包／上传／下载校验／安装／回读判等／
    资源回读／投后复核＋总）：
    只记阶段名、序号、耗时、rc 与资源数量；**不记**完整 argv、预签名 URL 或 SDK／CLI 原始报文。

退出码：
  0  成功（打包模式＝包已写出且本地校验全通过；部署模式＝平台判等全部完成；未变对象只读分支＝
     全部核验一致、未执行部署写入）
  1  **写路径已开始后**失败（上传／下载校验／官方 HTTP 写入（install／edit）／回读判等／正文修补／投后源端复核，含资源
     HTTP 回读失败与写路径内的 CLI 启动异常）——不得盲重试，先回读真实状态，再按 `--out-dir`
     内的部署前回滚包恢复
  2  参数或输入不可用，**未进入写路径**（缺 `--src`、登记不符、包无效、非常规权限、out-dir
     不可用或位于源内、资源清单未通过、`--expect-zip-sha256` 格式无效或与内存构包不一致、
     缺 SDK／凭据、防误触断言未过、**同域前置未通过／`lh` 启动器无法解析冻结**、上传前源端复核不一致、平台／存储读取失败、未变对象只读分支核验未
     通过，以及写路径开始前的 CLI 启动异常）

标准库 only；导入与 `--help` 不联网、不读凭据、不写产物；SDK 仅在部署分支延迟加载。
"""
import contextlib
import hashlib
import http.client
import importlib.util
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from urllib.parse import urlsplit

AUTH_ENV = "LUNO_DEPLOY_AUTHORIZED"
AUTH_VALUE = "1"

# 固定阶段名（失败只报这些，不回述原始报文）
STAGE_LOCAL = "本地校验"
STAGE_PACK = "打包"
STAGE_INVENTORY = "资源完整清单"
STAGE_AUTH = "授权"
STAGE_SDK = "SDK"
STAGE_PLATFORM = "平台回读"
STAGE_ROLLBACK = "回滚包"
STAGE_UPLOAD = "上传"
STAGE_DOWNLOAD = "下载校验"
STAGE_INSTALL = "安装"
STAGE_READBACK = "回读判等"
#: 资源 bytes 回读阶段（同域 HTTP 路径；同域不可证明即停止本次部署，不再退回 CLI）
STAGE_RESOURCE = "资源回读"
#: 未变对象只读分支的核验阶段——**不在** `WRITE_STAGES`：未进入写路径即 rc=2
STAGE_READONLY = "只读核验"
#: 正文尾 LF 修补（单独计时，便于单独报账）；它只在**上传之后**可达，故属写路径阶段（rc=1）
STAGE_EDIT = "正文修补"
#: 源端复核（部署窗口，F5）：**上传前**复核 ⇒ 未进入写路径（rc=2）
STAGE_SNAPSHOT = "源端复核"
#: 源端复核（部署窗口，F5）：**安装后**复核 ⇒ 写路径已开始（rc=1）
STAGE_SNAPSHOT_AFTER = "投后复核"
# 对生产（平台／对象存储）**已开始写**的阶段 → rc=1；其余 → rc=2
#   `STAGE_EDIT`／`STAGE_SNAPSHOT_AFTER` 只在**上传之后**可达，故同属写路径；`STAGE_SNAPSHOT`
#   落在上传之前（未进入写路径）⇒ rc=2。
WRITE_STAGES = (STAGE_UPLOAD, STAGE_DOWNLOAD, STAGE_INSTALL, STAGE_READBACK, STAGE_EDIT,
                STAGE_SNAPSHOT_AFTER)

#: CLI 启动器名：在**原环境**解析一次，此后只用解析出的绝对 argv（不经 PATH 的 shim 解析）
CLI_NAME = "lh"
#: 受控 CLI 子进程的**最小** PATH 目录集（受批准的系统目录；任何名为 `shims` 的目录一律排除）
CLI_PATH_DIRS = ("/usr/local/bin", "/usr/bin", "/bin")

#: Node 官方模块编译缓存目录名（`NODE_COMPILE_CACHE`，Node ≥22.1；更早版本忽略该变量）。
#: 建在 runner 的**运行期私有**临时根内、模式 0700：只承载官方 bundle 的 V8 代码缓存，供同一次
#: 运行内的多次 `lh` 调用复用，收尾随临时根一并删除。**不跨运行持久化**，不接收正文／凭据／平台
#: 数据。这是一项**纯优化**：目录建不出来（权限／配额／平台限制）即**省略该变量**照常跑 CLI，
#: 不改变 CLI 的 rc／stdout，也不因此阻断部署——失败绝不吞业务错误（HOME／XDG 仍 fail-closed）。
COMPILE_CACHE_DIR = "compilecache"
COMPILE_CACHE_MODE = 0o700

#: 官方 tRPC 写入 procedure（**只此两个**：安装与正文补写；不泛化成通用 router 调用）。
#: 形态由官方固定源（lobehub/lobehub@6c7a6fb033e443bc27bf34cbd5509ab3db7f22f3，2026-10-07）与真实 CLI 0.0.62 bundle 回环探针当场证实。
WRITE_PROCEDURES = {"install": "/trpc/lambda/agentSkills.importFromUrl",
                    "edit": "/trpc/lambda/agentSkills.update"}
#: 写入请求的**有界** socket 超时（秒）；不跟随 redirect、不读代理；重试口径见 `WRITE_RETRY_DELAYS`
WRITE_TIMEOUT = 30.0
#: 写入请求 User-Agent（与既有只读传输／历史通过 CF 的形态一致）
WRITE_UA = "curl/8.7.1"
#: 写入响应体的**有界**读取上限（字节）：只用于解析 tRPC 信封；超界即失败且**不继续读**
WRITE_BODY_LIMIT = 64 * 1024
#: 响应体分片读取粒度（字节）：单次 `read1` 请求量不超过它，故上限判定不会整包读入
WRITE_READ_CHUNK = 8192
#: 错误信封 `code` 的**已知枚举白名单**（tRPC `TRPC_ERROR_CODE_KEY` 的可外显子集）。
#: 只有**精确命中**的名字才进日志；整数码、`data.code`、拼装 token 一律 `unknown`——「字符集合规」
#: 不能证明语义，合成串（如带外部内容的 marker）照样会原样落日志（复审 F1）。
ENVELOPE_CODES = ("BAD_REQUEST", "UNAUTHORIZED", "FORBIDDEN", "NOT_FOUND",
                  "METHOD_NOT_SUPPORTED", "TIMEOUT", "CONFLICT", "PRECONDITION_FAILED",
                  "PAYLOAD_TOO_LARGE", "TOO_MANY_REQUESTS", "CLIENT_CLOSED_REQUEST",
                  "INTERNAL_SERVER_ERROR", "NOT_IMPLEMENTED", "BAD_GATEWAY",
                  "SERVICE_UNAVAILABLE", "GATEWAY_TIMEOUT")
#: `edit`（`agentSkills.update`：同 id 同 content 幂等）的**有界**重试间隔（秒）：最多重试 2 次。
#: 只对**瞬时失败**（传输异常、5xx 含 502／503／504）生效；4xx 与错误信封不重试。`install` 不重试。
WRITE_RETRY_DELAYS = (0.25, 0.5)
#: 补写后的平台收敛轮询等待点（秒，首个 0 即立即读一次）：相等即停，总预算 ≤ `REPAIR_POLL_BUDGET`
REPAIR_POLL_DELAYS = (0.0, 0.5, 1.0, 2.0, 4.0)
#: 轮询总预算（秒，含等待）：超出预算的等待点跳过；仍不收敛即失败（write 路径内 ⇒ rc=1）
REPAIR_POLL_BUDGET = 10.0
#: **非轮询**回读的单次预算上限（秒）：部署前 view／安装后 view／写前复核都以此为「剩余预算」，
#: 既下传子进程 `timeout`，也在读取返回后复查总耗时（复审 F2 第二轮：不留 `timeout=None` 的读）。
READBACK_BUDGET = 10.0

#: 资源回读传输：从审定仓库加载的既有 HTTP 客户端模块名（**无回退**）
RESOURCE_MODULE = "resource_http.py"
#: 并发固定 4（同一 collect 首错停发，最多 3 个已在途请求收束）；预算仍为协作式上限
HTTP_WORKERS = 4
RESOURCE_HTTP_BUDGET = 300.0

SKILL_FILE = "SKILL.md"
ROLLBACK_SUFFIX = ".predeploy.zip"
CANDIDATE_SUFFIX = ".zip"
#: 部署分支必需的存储环境变量（全部必填、无默认值；缺一即拒绝，只报变量名）
STORAGE_ENV = ("CF_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
PLATFORM_ID_RE = re.compile(r"^skl_[A-Za-z0-9]+$")
# R2 对象 key：单段、首字符字母数字、只含 A-Za-z0-9._- —— 不接受 URL／查询串／路径分隔符
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PACK_MODE = 0o644
#: 专用打包器：键为**已登记的源路径**，值为同一审定仓库内的固定相对路径。命中即用专用器
#: （不过滤名单／秘密检测／ZIP 布局都由它自己持有），**无回退**——模块缺失即固定分类失败，
#: 不退回通用打包器，也不按技能名猜路径。
DEDICATED_PACKERS = {"skills/luno-surge": "skills/luno-surge/scripts/package_release.py"}

USAGE = ("用法：python3 -B tools/deploy_skill.py --repo <审定仓库> --src <显式技能目录> "
         "--name <技能名> --key <既有 R2 对象 key> --out-dir <已授权资产目录> "
         "--expect-id <登记平台 ID> [--deploy] [--expect-zip-sha256 <64位小写十六进制>]\n"
         "  缺 --src 直接 rc=2；不用环境变量、不按名称猜源目录。\n"
         "  --expect-zip-sha256 为**可选**候选哈希门禁：给了就要求本次内存构包的 sha256 与其逐位\n"
         "  相等，否则在**任何远端写入之前** rc=2（打包模式同断言，只是不会有远端写入）。\n"
         "  默认只打包（不上传／不安装）；--deploy 才进入写路径，且 `%s=1` 只是**防误触断言**"
         "（不是授权来源：须由主助理先核既有部署授权）。\n"
         "  退出码：0 成功／1 写路径已开始后失败／2 参数或输入不可用。"
         % AUTH_ENV)


class Fail(Exception):
    """固定阶段失败。`stage` 取上面的固定阶段名，`detail` 为**不含秘密**的说明。"""

    def __init__(self, stage, detail):
        Exception.__init__(self, detail)
        self.stage = stage
        self.detail = detail

    @property
    def rc(self):
        return 1 if self.stage in WRITE_STAGES else 2


# ── 单点缝（测试可替换；生产实现只读环境变量与子进程）─────────────────────────

def env_get(name, default=None):
    """环境变量单点读取：只按名取，**从不展示值**。"""
    return os.environ.get(name, default)


def import_module(name):
    """单点导入缝：SDK 只在部署分支经此延迟加载（缺依赖报告，不自动安装）。"""
    return __import__(name, fromlist=["*"])


def controlled_path():
    """受控 CLI 子进程的**最小** PATH：受批准目录中真实存在者，排除任何名为 `shims` 的目录。"""
    return os.pathsep.join(d for d in CLI_PATH_DIRS
                           if os.path.isdir(d) and os.path.basename(d) != "shims")


def resolve_cli_argv():
    """在**原环境**把 `lh` 解析为**绝对 argv**并冻结一次（`shutil.which` ＋ realpath）。

    只解析、不执行、不读任何登录态文件；解析不到或形态不能证明（非绝对／不可执行／仍是 `mise`
    之类的 shim）即**固定分类失败**（`STAGE_PLATFORM` ⇒ rc=2）——此刻尚未有任何平台或存储访问。
    返回的 argv 此后直传子进程（列表直传、不经 shell 拼接），**不经 PATH 的 shim 解析**。
    """
    path = env_get("PATH")
    entry = shutil.which(CLI_NAME, path=path) if path else None
    if not entry:
        raise Fail(STAGE_PLATFORM, "无法解析 lh 启动器（原环境 PATH 内找不到）：同域前置未通过；"
                                   "停止本次部署，未执行平台或存储写入")
    real = os.path.realpath(entry)
    parts = [p for p in real.split(os.sep) if p]
    if not real.startswith(os.sep) or "shims" in parts or os.path.basename(real) == "mise":
        raise Fail(STAGE_PLATFORM, "lh 启动器形态不能证明（shim／非绝对）：同域前置未通过；"
                                   "停止本次部署，未执行平台或存储写入")
    if not os.path.isfile(real) or not os.access(real, os.X_OK):
        raise Fail(STAGE_PLATFORM, "lh 启动器不是可执行的常规文件：同域前置未通过；"
                                   "停止本次部署，未执行平台或存储写入")
    return [real]


class CliRunner(object):
    """冻结的受控 CLI runner：**绝对 argv** ＋ **空 HOME/XDG** ＋ 只含白名单变量的 env。

    每次运行新建空 HOME/XDG（`tempfile.mkdtemp`，子目录 `cfg`／`data`／`cache`）；env **只含**
    `PATH`／`HOME`／`XDG_*`／`LOBEHUB_SERVER`／`LOBEHUB_CLI_API_KEY`，**不继承**
    `LOBEHUB_WORKSPACE_ID`、JWT、代理等，也**不读任何登录态文件**；收尾删除临时目录，
    **构造中途失败也回收**已建目录（此刻 runner 尚未赋值给 `RUNNER`，外层 finally 看不到它）。
    """

    #: CLI 子进程 env 的**全部**键（顺序即构造顺序；新增键须同步本表与测试）。
    #: `NODE_COMPILE_CACHE` 属**可省略**项：缓存目录建不出来时该项不注入，其余键仍恒在。
    ENV_KEYS = ("PATH", "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                "NODE_COMPILE_CACHE", "LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY")
    OPTIONAL_ENV_KEYS = ("NODE_COMPILE_CACHE",)

    def __init__(self, argv, origin, key):
        self.argv = list(argv)
        root = tempfile.mkdtemp(prefix="deploy-lh-")
        self.root = root                      # 保留赋值：构造**中途**失败时清理也要有据可依
        self.cleaned = False
        # 构造中途失败（HOME／XDG 建目录、env 构造）必须回收已建临时目录：此刻 runner 尚未
        # 赋值给 `RUNNER`，外层 finally 的 `release_cli_runner()` 看不到它。清理后**原样抛出**，
        # 阶段归类与文案仍由 `freeze_cli_runner` 的 `OSError` 分支固定（不回显原始异常）。
        try:
            home = os.path.join(root, "home")
            os.mkdir(home)
            self.home = home
            for sub in ("cfg", "data", "cache"):
                os.mkdir(os.path.join(home, sub))
            # 编译缓存目录：0700、位于本次运行的临时根内（与 HOME/XDG 同源同寿命）。**纯优化**：
            # 建不出来（权限／配额／平台限制）就**省略该变量**照常跑 CLI——绝不因优化措施阻断部署，
            # 也不改变 CLI 的 rc／stdout（Node 自身也只把它当可选缓存）。HOME/XDG 仍 fail-closed。
            self.compile_cache = None
            try:
                candidate = os.path.join(root, COMPILE_CACHE_DIR)
                os.mkdir(candidate, COMPILE_CACHE_MODE)
                self.compile_cache = candidate
            except OSError:
                self.compile_cache = None
            self.env = {"PATH": controlled_path(), "HOME": home,
                        "XDG_CONFIG_HOME": os.path.join(home, "cfg"),
                        "XDG_DATA_HOME": os.path.join(home, "data"),
                        "XDG_CACHE_HOME": os.path.join(home, "cache"),
                        "LOBEHUB_SERVER": origin, "LOBEHUB_CLI_API_KEY": key}
            if self.compile_cache is not None:
                self.env["NODE_COMPILE_CACHE"] = self.compile_cache
        except BaseException:
            shutil.rmtree(root, ignore_errors=True)
            raise

    def close(self):
        """收尾：删除本次运行的临时根（HOME／XDG／编译缓存）并**回读确认**已消失。

        `cleaned` 只作事实记录，失败时由 `release_cli_runner()` 如实记一行；**不改变**退出码，
        也不让清理问题掩盖本次部署的真实结局。
        """
        shutil.rmtree(self.root, ignore_errors=True)
        self.cleaned = not os.path.lexists(self.root)

    def call(self, args, timeout=None):
        """调用一次 CLI：argv 直传（路径含空格仍是单个元素），env 用构造时的白名单副本。

        `timeout`（秒）＝调用方给的**剩余预算**：直接交给 `subprocess.run`，超时由子进程层中止并
        抛 `subprocess.TimeoutExpired`——读取本身受预算约束，而不是「读完再等」（复审 F2）。
        """
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                  "env": dict(self.env)}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return subprocess.run(self.argv + list(args), **kwargs)


#: 本次运行的受控 CLI runner（**未冻结**时任何 CLI 调用都必须失败）
RUNNER = None


def freeze_cli_runner(origin, key):
    """冻结受控 CLI runner：解析绝对 argv ＋ 建空 HOME/XDG ＋ 只含白名单变量的 env。"""
    global RUNNER
    argv = resolve_cli_argv()
    try:
        RUNNER = CliRunner(argv, origin, key)
    except OSError as exc:
        raise Fail(STAGE_PLATFORM, "无法建立受控 CLI 环境（%s）：同域前置未通过；"
                                   "停止本次部署，未执行平台或存储写入"
                    % exc.__class__.__name__)
    return RUNNER


def release_cli_runner():
    """收尾（含异常路径）：删除本次运行的临时 HOME/XDG／编译缓存目录，并回读确认。

    未删除成功只**如实记一行**（固定文案，不回显路径），不改变退出码、不掩盖业务结局。
    """
    global RUNNER
    if RUNNER is not None:
        root = RUNNER.root
        RUNNER.close()
        if not RUNNER.cleaned:
            log("警告：临时目录未删除（回读仍在）：%s" % os.path.basename(root))
        RUNNER = None


def run_lh(args, stage=STAGE_PLATFORM, timeout=None):
    """调用**冻结**的 CLI runner，只回传 (rc, stdout bytes, stderr bytes)。原始输出不进日志。

    未冻结即拒绝（不隐式解析、不走 PATH）。启动异常（`OSError`）按**调用方给的阶段**归类：
    写路径内 ⇒ rc=1，写路径前 ⇒ rc=2——不一律归「平台回读」，避免上传后误报「未进入写路径」。
    `timeout` 是**剩余预算**（秒）：非 `None` 时下传 `subprocess.run`，超时即固定分类失败（与
    `OSError` 分开归类，不把「超预算」误报成「无法调用」）。
    """
    if RUNNER is None:
        raise Fail(stage, "CLI runner 未冻结：拒绝调用 lh（不隐式解析、不走 PATH）")
    try:
        proc = RUNNER.call(args, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Fail(stage, "单次读取超过剩余预算（%.1f s）：已中止 lh 子进程，不判成功"
                    % (timeout or 0.0))
    except OSError as exc:
        raise Fail(stage, "无法调用 lh（%s）" % exc.__class__.__name__)
    return proc.returncode, proc.stdout, proc.stderr


def load_module(path, modname):
    """按路径加载审定仓库内的辅助模块（**无回退**：缺即拒绝）。"""
    if not os.path.isfile(path):
        raise Fail(STAGE_LOCAL, "审定仓库内缺辅助模块：%s" % path)
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise Fail(STAGE_LOCAL, "无法加载辅助模块：%s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise Fail(STAGE_LOCAL, "读取源文件失败（%s）：%s" % (exc.__class__.__name__, path))


def write_atomic(path, blob, stage):
    """原子写出：先写同目录临时文件 → chmod 0644 → os.replace；失败清理临时文件、
    **不覆盖**已有产物。"""
    out_dir = os.path.dirname(path)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=out_dir, prefix=".deploy-", delete=False) as tmp:
            tmp_name = tmp.name
            tmp.write(blob)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_name, PACK_MODE)
        os.replace(tmp_name, path)
        tmp_name = None
    except OSError as exc:
        raise Fail(stage, "写出产物失败（%s）：%s" % (exc.__class__.__name__, path))
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError as exc:
                # 删除失败原先被静默吞掉，残留物对调用方不可见（F5）。告警只用**固定类别＋自建
                #   文件 basename**：完整 out-dir 路径可能暴露调用方目录结构，故不外露；basename
                #   由本函数 `prefix=".deploy-"` 生成；文件内容、URL、token 一律不入日志。
                #   `sys.stderr` 本身失败（关闭／坏管道）**不得替代原异常**：这里的写失败一律
                #   吞掉，保证 finally 期间传播的仍是 write_atomic 的 Fail（失败分类不变）。
                try:
                    sys.stderr.write("[deploy] 警告：临时文件残留（%s）：%s\n"
                                     % (exc.__class__.__name__, os.path.basename(tmp_name)))
                except Exception:
                    pass


def log(line):
    sys.stdout.write("[deploy] %s\n" % line)


# ── 分阶段 wall 计时（只记阶段名／序号／耗时／rc／资源数量）──────────────────────

class PhaseTimer(object):
    """分阶段 wall 计时。**只**记阶段名、序号、耗时、rc 与资源数量。

    不记完整 argv、预签名 URL、SDK／CLI 原始报文——本入口的秘密面边界不受计时影响。
    失败时该阶段照样落一行（rc 取 `Fail.rc`，意外异常记 1），总计时由 `run()` 统一输出。
    """

    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._start = self._clock()
        self.rows = []

    @contextlib.contextmanager
    def phase(self, stage, count=None):
        entry = {"seq": len(self.rows) + 1, "stage": stage, "count": count, "rc": 0,
                 "seconds": 0.0}
        self.rows.append(entry)               # 入口即登记：嵌套阶段的序号与输出顺序一致
        started = self._clock()
        try:
            yield entry
        except Fail as exc:
            entry["rc"] = exc.rc
            raise
        except BaseException:
            entry["rc"] = 1
            raise
        finally:
            entry["seconds"] = round(self._clock() - started, 3)

    def report(self, rc):
        for row in self.rows:
            log("计时：%d｜%s｜%.3fs｜rc=%d｜资源=%s"
                % (row["seq"], row["stage"], row["seconds"], row["rc"],
                   "-" if row["count"] is None else row["count"]))
        log("计时：总｜%.3fs｜rc=%d｜阶段数=%d"
            % (round(self._clock() - self._start, 3), rc, len(self.rows)))


# ── SDK 静音边界（SDK 自身的 stdout／stderr／logging 一律丢弃）────────────────

@contextlib.contextmanager
def sdk_silence():
    """SDK 静音边界：SDK 自身的 stdout／stderr／logging **一律丢弃**。

    只包 `import_module("boto3")`、客户端创建与每次 SDK 调用；本入口对外只给**固定阶段**、
    状态与所需结果，不让 SDK 直接打印或 logging 进入工具输出。
    """
    saved_out, saved_err = sys.stdout, sys.stderr
    saved_disable = logging.root.manager.disable
    for stream in (saved_out, saved_err):      # 先冲出本入口已缓冲的输出，再堵
        try:
            stream.flush()
        except Exception:
            pass
    sink = open(os.devnull, "w")
    saved_fds = []
    sys.stdout = sink
    sys.stderr = sink
    logging.disable(logging.CRITICAL + 10)
    try:
        try:                                   # 再堵 fd 级写入（堵不上则只靠流级）
            for fd in (1, 2):
                dup = os.dup(fd)
                try:
                    os.dup2(sink.fileno(), fd)
                except OSError:
                    os.close(dup)
                    break
                saved_fds.append((fd, dup))
        except OSError:
            pass
        yield
    finally:
        for fd, dup in reversed(saved_fds):
            try:
                os.dup2(dup, fd)
            except OSError:
                pass
            try:
                os.close(dup)
            except OSError:
                pass
        logging.disable(saved_disable)
        sys.stdout, sys.stderr = saved_out, saved_err
        sink.close()


# ── 存储（预签名 URL 只在内存中传递）─────────────────────────────────────────

class Storage(object):
    """对象存储读写。SDK 异常只上报**类名**，不回述原始报文（可能含签名 URL）。"""

    def __init__(self, client, bucket):
        self._client = client
        self._bucket = bucket

    def download(self, key):
        try:
            with sdk_silence():
                body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
                return body.read()
        except Exception as exc:
            raise Fail(STAGE_ROLLBACK, "读取同 key 现存对象失败（%s）" % exc.__class__.__name__)

    def upload(self, key, blob):
        try:
            with sdk_silence():
                self._client.put_object(Bucket=self._bucket, Key=key, Body=blob,
                                        ContentType="application/zip")
        except Exception as exc:
            raise Fail(STAGE_UPLOAD, "上传失败（%s）" % exc.__class__.__name__)

    def presigned_get(self, key):
        try:
            with sdk_silence():
                return self._client.generate_presigned_url(
                    "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=600)
        except Exception as exc:
            raise Fail(STAGE_UPLOAD, "生成预签名 URL 失败（%s）" % exc.__class__.__name__)

    def fetch(self, url):
        try:
            with urllib.request.urlopen(url, timeout=120) as fh:
                return fh.read()
        except Exception as exc:
            raise Fail(STAGE_DOWNLOAD, "预签名下载失败（%s）" % exc.__class__.__name__)


def open_storage():
    """部署分支专用：延迟加载 SDK；缺依赖／缺凭据**报告**，不自动安装、不猜来源。"""
    try:
        with sdk_silence():
            boto3 = import_module("boto3")
            botocore_config = import_module("botocore.config")
    except ImportError as exc:
        raise Fail(STAGE_SDK, "缺少 SDK（boto3／botocore，%s）；不自动安装" % exc.__class__.__name__)
    missing = [name for name in STORAGE_ENV if not env_get(name)]
    if missing:
        raise Fail(STAGE_SDK, "缺少存储凭据环境变量（按名报缺，不展示值）：%s"
                    % "／".join(missing))
    try:
        with sdk_silence():
            client = boto3.client(
                "s3",
                endpoint_url="https://%s.r2.cloudflarestorage.com" % env_get("CF_ACCOUNT_ID"),
                aws_access_key_id=env_get("R2_ACCESS_KEY_ID"),
                aws_secret_access_key=env_get("R2_SECRET_ACCESS_KEY"),
                region_name="auto",
                config=botocore_config.Config(signature_version="s3v4",
                                              retries={"max_attempts": 3, "mode": "standard"}))
    except Exception as exc:
        raise Fail(STAGE_SDK, "初始化存储客户端失败（%s）" % exc.__class__.__name__)
    return Storage(client, env_get("R2_BUCKET"))


# ── 平台只读（只取已确认字段；按登记 ID 直接回读）─────────────────────────────

# 源端字段白名单（**不含** `source`：避免把签名 URL 带进内存／日志）；顺序即投影顺序
PLATFORM_FIELDS = ("id", "identifier", "name", "description", "content", "zipFileHash",
                   "resources")
#: 资源元数据的**唯一**已知嵌套字段集（官方 `SkillResourceMeta`：`{fileHash, size}`）。
#: 该集合之外的任何键——例如带签名 URL 的字段——一律 fail-closed，不进判等面。
RESOURCE_META_KEYS = ("fileHash", "size")
R2_HOST = "r2.cloudflarestorage.com"


def _iter_dicts(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            for item in _iter_dicts(value):
                yield item
    elif isinstance(node, list):
        for value in node:
            for item in _iter_dicts(value):
                yield item


def platform_entry(expect_id, stage, timeout=None):
    """按 `--expect-id` 直接回读单个对象，**只取白名单字段**（不读全量 manifest）。

    `skill view` 带**源端字段白名单**参数：只请求 `PLATFORM_FIELDS`（不含 `source`／
    `manifest`），避免把签名 URL 之类的非必要内容带进内存。`resources` 亦在白名单内：资源路径集与
    逐项 `(size, fileHash)` 由**同一次** view 一并取回，不再单独启动 `skill resources`。
    CLI 调用经冻结 runner，失败阶段用调用方的 `stage`。`timeout`（秒）＝**剩余预算**，非 `None`
    时下传到底层子进程（复审 F2：预算必须约束读取本身，不能只约束等待点）。**所有**调用点都必须
    携带预算：非轮询路径一律经 `bounded_entry`（缺省 `READBACK_BUDGET`＝10 s），轮询路径传剩余
    预算——不留 `timeout=None` 的回读（复审 F2 第二轮：四处回读曾有三处为 `None`）。
    """
    rc, out, _err = run_lh(["skill", "view", expect_id, "--json", ",".join(PLATFORM_FIELDS)],
                           stage, timeout=timeout)
    if rc != 0:
        raise Fail(stage, "平台回读失败：lh skill view rc=%d" % rc)
    try:
        doc = json.loads(out.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise Fail(stage, "平台回读结果不是合法 JSON（%s）" % exc.__class__.__name__)
    for node in _iter_dicts(doc):
        if node.get("id") == expect_id:
            # F1/F2：**键缺失**必须在投影前拦下——`get` 会把缺键抹成 `None`，被下游当成「空集」放行。
            if "resources" not in node:
                raise Fail(stage, "平台回读缺 resources 字段")
            return dict((key, node.get(key)) for key in PLATFORM_FIELDS)
    raise Fail(stage, "平台回读未命中登记 ID：%s" % expect_id)


def bounded_entry(expect_id, stage, budget=None):
    """**非轮询**回读的唯一入口：剩余预算下传子进程，返回后再复查总耗时（复审 F2 第二轮）。

    `budget` 缺省取 `READBACK_BUDGET`（10 s）。两条**同时**成立才判读取成功：子进程在预算内返回
    （`platform_entry` 的 `timeout`），且实测总耗时不超过预算（子进程计时不准、`timeout` 未生效或
    收尾拖长时同样失败）。任一越界即 `Fail`，不进入判等、不判成功——「只约束等待、放过单读 12 s」
    正是上一轮未闭环的形态。
    """
    cap = READBACK_BUDGET if budget is None else budget
    start = time.monotonic()
    entry = platform_entry(expect_id, stage, timeout=cap)
    elapsed = time.monotonic() - start
    if elapsed > cap:
        raise Fail(stage, "平台回读超过剩余预算（上限 %s s，实测 %.2f s）：不判成功"
                    % (cap, elapsed))
    return entry


def platform_resource_map(entry, stage, valid_path):
    """`view` 顶层 `resources` → `{path: (size, fileHash)}`；**形态不符即 fail-closed**。

    平台形态（官方 `agentSkill.ts` 的 `SkillResourceMeta`＝`Record<VirtualPath,
    SkillResourceMeta>`，与实测 `skill view <id> --json id,resources` 的返回一致）：每个值只应含
    `size`／`fileHash` 两个**已知**嵌套字段。四个口径：
      · `resources` **键必须存在**（缺键＝失败；不得与显式 `null`／`{}` 混同为空集）；
      · 空值（`null`）与空映射（`{}`）＝**无资源**：按已核平台约定严格允许为空集；
      · 每个值的键集**必须恰为** `RESOURCE_META_KEYS`：多一个键（例如带签名 URL 的字段）即失败，
        不把未知字段带进判等面；少一个键同样失败；
      · 路径须是合法虚拟路径（判据复用调用方传入的**已加载** `resource_http.valid_path`）、`size`
        须为非负整数、`fileHash` 须为 64 位十六进制。

    **失败文案不回显外部输入**：只报固定分类、已知字段名（`RESOURCE_META_KEYS` 派生）、类型名或
    数量；外部路径与未知字段名／值一概不输出（键不保证非秘密，控制字符还能注入日志）。资源集与
    bytes 判等同批生效，故本函数取代了原独立启动的 `skill resources`（树形态）CLI。
    """
    if "resources" not in entry:
        raise Fail(stage, "平台回读缺 resources 字段")
    raw = entry["resources"]
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise Fail(stage, "平台 resources 不是 Record 形态（%s）：无法核资源集"
                    % type(raw).__name__)
    out = {}
    for rel, meta in raw.items():
        if not valid_path(rel):
            raise Fail(stage, "平台 resources 含非法路径")
        if not isinstance(meta, dict):
            raise Fail(stage, "平台 resources 项不是对象（%s）" % type(meta).__name__)
        unknown = [key for key in meta if key not in RESOURCE_META_KEYS]
        if unknown:
            raise Fail(stage, "平台 resources 项含未知字段（%d 项）" % len(unknown))
        missing = [key for key in RESOURCE_META_KEYS if key not in meta]
        if missing:
            raise Fail(stage, "平台 resources 项缺字段（%s）" % "／".join(missing))
        size = meta["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise Fail(stage, "平台 resources 项 size 不是非负整数（%s）" % type(size).__name__)
        digest = meta["fileHash"]
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest.lower()):
            raise Fail(stage, "平台 resources 项 fileHash 不是 64 位十六进制（%s）"
                        % type(digest).__name__)
        out[rel] = (size, digest.lower())
    return out


# ── 资源 bytes 回读（同域 HTTP；不可证明即停止本次部署，无 CLI 回退）────────────

def freeze_resource_context(resource_mod):
    """同域前置：冻结一次 `(origin, key)`；**不通过即返回 None（调用方停止本次部署）**。

    `resource_http.connection_context()` 只接受受批准 origin ＋指定环境变量 API key ＋个人作用域；
    任一不满足（含显式 workspace、key 含非法字符）即判**无法证明同域**：本入口**不**退化为登录态、
    **不**改用其它实例，**也****不再**退回逐资源 CLI `read-resource`（该退化路径按复审 F1／F2
    取消）——调用方在**任何平台或存储访问之前**按固定分类失败停止（零 HTTP／零 R2／零 install／
    零 edit）。冻结结果只在内存中传递，**key 不落日志**。
    """
    try:
        context = resource_mod.connection_context()
    except resource_mod.ResourceError as exc:
        log("资源回读：同域不可证明（%s）；停止本次部署（无 CLI 回退，零平台／存储写入；"
            "须 %s 等于已核准实例、指定凭据有效且不设 workspace 变量）"
            % (exc, resource_mod.ORIGIN_ENV))
        return None
    except Exception as exc:
        log("资源回读：同域不可证明（%s）；停止本次部署（无 CLI 回退，零平台／存储写入）"
            % exc.__class__.__name__)
        return None
    log("资源回读：HTTP 同域已冻结（受批准 origin＋指定 key＋个人作用域；workers=%d）；"
        "预算 %ss（协作式，非硬截止）" % (HTTP_WORKERS, RESOURCE_HTTP_BUDGET))
    return context


def read_resources_http(resource_mod, context, expect_id, planned, stage):
    """经既有 HTTP 客户端逐资源取回原始 bytes。**workers 固定 4**；失败即 fail-closed。"""
    deadline = time.monotonic() + RESOURCE_HTTP_BUDGET
    try:
        client = resource_mod.ResourceClient(deadline, context)
        return resource_mod.collect(client, expect_id, planned, HTTP_WORKERS)
    except resource_mod.ResourceError as exc:
        raise Fail(stage, "资源 HTTP 回读失败：%s" % exc)
    except Exception as exc:
        raise Fail(stage, "资源 HTTP 回读异常（%s）" % exc.__class__.__name__)


# ── 官方 HTTP 写入（install／edit；复用已冻结的 `(origin, key)`）───────────────

def https_connection(host, timeout):
    """写入用 HTTPS 连接**单点缝**（测试可替换）。

    生产实现只建标准库连接：**不读代理设置、不跟随 redirect、不重试**。
    """
    return http.client.HTTPSConnection(host, timeout=timeout)


class _WriteTransient(Exception):
    """写入的**瞬时**失败（传输异常／5xx）：仅 `edit` 在有界次数内重试，不直接对外暴露。

    `detail` 只含固定分类文案与状态码／异常类名；信封 message、响应体、URL、header 一律不进。
    """

    def __init__(self, detail):
        Exception.__init__(self, detail)
        self.detail = detail


def _envelope_code(error):
    """从 tRPC 错误信封取**可安全回显**的 `code`：**只认 `ENVELOPE_CODES` 白名单**，其余 `unknown`。

    取 `error.json.code`（缺失时退回 `error.code`），且只接受**精确命中**已知枚举名的字符串：整数
    tRPC 码、`data.code`、拼装 token 一律 `unknown`——字符集合规不等于平台语义，合成串同样可能携带
    外部内容（复审 F1：字符集白名单会把构造出来的 code 原样落日志）。
    只取 `code`：`message`／`data`／`stack` 可能含平台原始报文甚至签名 URL，一律不取、不入日志。
    """
    node = error
    if isinstance(node, dict) and isinstance(node.get("json"), dict):
        node = node["json"]
    code = node.get("code") if isinstance(node, dict) else None
    if isinstance(code, str) and code in ENVELOPE_CODES:
        return code
    return "unknown"


def read_write_envelope(response, status, stage):
    """**有界**读写入响应体并判 tRPC 信封：出现 `error` 即失败、200 但非 `result` 形态同样失败。

    上限 `WRITE_BODY_LIMIT`（64 KB）：超界即失败且**不再继续读**；分片粒度 `WRITE_READ_CHUNK`，故不会
    把整包读进内存。响应体内容**一律不进日志**：错误只报 `status` 与提取出的 `code`，不回显
    message／body／URL／header。
    """
    chunks = []
    total = 0
    while total <= WRITE_BODY_LIMIT:
        chunk = response.read1(min(WRITE_READ_CHUNK, WRITE_BODY_LIMIT + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > WRITE_BODY_LIMIT:
            raise Fail(stage, "官方写入响应体超过 %d B 上限：不继续读、不回显（status=%d）"
                        % (WRITE_BODY_LIMIT, status))
        chunks.append(chunk)
    try:
        doc = json.loads(b"".join(chunks).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise Fail(stage, "官方写入响应体不是合法 JSON 信封（%s，status=%d）：不回显响应体"
                    % (exc.__class__.__name__, status))
    if not isinstance(doc, dict):
        raise Fail(stage, "官方写入响应信封不是对象（status=%d）：不回显响应体" % status)
    if "error" in doc:
        raise Fail(stage, "官方写入返回错误信封（status=%d code=%s）："
                          "不回显 message／body／URL／header"
                    % (status, _envelope_code(doc.get("error"))))
    if not isinstance(doc.get("result"), dict):
        raise Fail(stage, "官方写入响应不是 result 形态（status=%d）：不回显响应体" % status)


def write_once(context, kind, payload, stage):
    """**一次**写入尝试：发请求 → 核状态／MIME → 有界读信封；瞬时失败抛 `_WriteTransient`。

    非 200 一律**不读体**（5xx 归瞬时失败、3xx／4xx 固定分类失败）；200 但 MIME 非 json（反代中介页）
    同样不读体、不重试。
    """
    path = WRITE_PROCEDURES.get(kind)
    if path is None:
        raise Fail(stage, "未知写入 procedure：%s" % kind)
    origin, key = context
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname:
        raise Fail(stage, "写入目标不可证明（同域前置未成立）：停止本次部署")
    body = json.dumps({"json": payload}, ensure_ascii=False).encode("utf-8")
    headers = {"X-API-Key": key, "User-Agent": WRITE_UA, "Accept": "application/json",
               "Content-Type": "application/json", "Connection": "close",
               "Content-Length": str(len(body))}
    conn = None
    try:
        conn = https_connection(parsed.hostname, WRITE_TIMEOUT)
        conn.request("POST", path, body=body, headers=headers)
        response = conn.getresponse()
        status = response.status
        ctype = response.getheader("Content-Type") or ""
        if status != 200:
            if 500 <= status <= 599:
                raise _WriteTransient("官方写入未返回 200（status=%d）（5xx 瞬时失败）" % status)
            raise Fail(stage, "官方写入未返回 200（status=%d）：不回显响应体，不重试" % status)
        if ctype.split(';', 1)[0].strip().lower() != "application/json":
            raise Fail(stage, "官方写入返回 200 但 Content-Type 非 json（中介页形态）：不重试")
        read_write_envelope(response, status, stage)
    except (Fail, _WriteTransient):
        raise
    except (OSError, http.client.HTTPException) as exc:
        raise _WriteTransient("官方写入请求异常（%s）（传输瞬时失败）" % exc.__class__.__name__)
    except ValueError as exc:
        raise Fail(stage, "官方写入请求参数异常（%s）：不重试、不改用 CLI 重复写"
                    % exc.__class__.__name__)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def write_skill_http(context, kind, payload, stage, guard=None):
    """官方 mutation：`install`→`agentSkills.importFromUrl`／`edit`→`agentSkills.update`。

    请求形态与官方固定源（`agentSkills.ts`）及真实 CLI bundle 回环抓到的形态一致：
    `POST /trpc/lambda/<procedure>`，体 `{"json": payload}`（纯 string 负载无 SuperJSON meta），
    头 `X-API-Key`（冻结的 key）＋`Content-Type: application/json`＋`User-Agent: curl/8.7.1`＋
    `Connection: close`。响应面：`status == 200` 且 MIME 为 `application/json`（可带参数），随后
    **有界**读响应体（≤64 KB）并判 tRPC 信封——出现 `error` 即失败、200 但非 `result` 形态同样失败，
    日志只带 `status` 与错误 `code`。URL／请求体／header／异常正文／信封 message 一概不进日志。

    因此两件事必须显式区分：
      * HTTP 200 ＋ `result` 信封**只表请求已被接受**，绝不报“安装／补写成功”——成功一律由**随后的
        完整白名单回读**（id／zipFileHash／name／description／content／全资源 bytes）判定；
      * 与官方 CLI 仍**非等价**：CLI 还做校验、ID 解析与本地状态处理，本函数只判信封形态；「200 ＋
        错误信封」现已在此拦下，反代「200 中介页」按 Content-Type 拦下，剩余差异只能靠回读兜住。

    失败固定分类（`Fail(stage, ...)`，不回显异常正文／URL／argv／header）：未知 procedure、同域不可
    证明、非 200（含 3xx／4xx／5xx，**不跟随 redirect**）、200 但 Content-Type 非 json、响应体超界／
    非法 JSON／非对象／错误信封／非 `result` 形态、请求参数异常。

    重试口径：**install 不重试**（重复安装有副作用）；`edit` 幂等（同 id 同 content），仅在**瞬时
    失败**——传输异常（`OSError`／`HTTPException`）与 5xx（含 502／503／504）——时最多重试
    `len(WRITE_RETRY_DELAYS)`＝2 次（间隔 250／500 ms）；4xx 与错误信封**不重试**。**不 fallback 到
    CLI 重复写**。

    并发口径（复审 F4）：`guard` 非 `None` 时**每次尝试（含重试）发请求之前**先调用它；`guard` 发现
    并发变更即抛 `Fail`（中止整个修补，不发本次 `update`）。平台没有可证的 CAS，故「写前重读基线」
    是本入口能给出的唯一防线；`install` 无基线，传 `None`。
    """
    attempts = len(WRITE_RETRY_DELAYS) + 1 if kind == "edit" else 1
    for attempt in range(attempts):
        if guard is not None:
            guard()
        try:
            write_once(context, kind, payload, stage)
            return
        except _WriteTransient as exc:
            if attempt + 1 >= attempts:
                raise Fail(stage, "%s；已尝试 %d 次仍失败：不重试、不改用 CLI 重复写"
                                  "（仅 edit 对瞬时失败重试；install 与 4xx／错误信封不重试）"
                            % (exc.detail, attempt + 1))
            log("官方写入（%s）：%s；第 %d 次重试（间隔 %ss）"
                % (kind, exc.detail, attempt + 1, WRITE_RETRY_DELAYS[attempt]))
            time.sleep(WRITE_RETRY_DELAYS[attempt])


def zip_member_bytes(blob, stage):
    """候选 ZIP 的不可变成员 bytes：计划项与预期值一律取自这里，源目录此后漂移不影响判等。"""
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            return dict((name, archive.read(name)) for name in archive.namelist())
    except (zipfile.BadZipFile, OSError) as exc:
        raise Fail(stage, "候选 ZIP 不可读（%s）" % exc.__class__.__name__)


def verify_resource_bytes(expect_id, entry, exp_res, zip_bytes, resource_mod, context, stage):
    """资源路径集 ＋ 逐项 size／fileHash ＋ 全部资源**原始 bytes** 判等；返回核验过的资源数。

    路径集与逐项元数据取自**同一次** `skill view` 返回的顶层 `resources`（`entry`：未变只读分支
    用 `before`、写路径用安装后重取的 `after`）——`skill resources` CLI **不再启动**。预期
    size／sha256 另从**不可变候选 ZIP 内该资源的 bytes** 现算并逐项比对（**不以 size／hash 判等
    代替逐字节比较**）；bytes 一律经同域 HTTP 取回，与该包内 bytes 严格比较——**无 CLI 回退**
    （同域前置不成立时调用方早已停止）。形态校验（未知嵌套字段／非法路径／类型不符）在路径集
    判等**之前**执行，失败时**不发起任何资源 HTTP**；路径合法性复用调用方已加载的
    `resource_http.valid_path`，**路径集差异只报数量**（外部路径不回显）。
    """
    got_res = platform_resource_map(entry, stage, resource_mod.valid_path)
    if sorted(got_res) != exp_res:
        raise Fail(stage, "资源路径集不等（平台 %d 项／候选 %d 项）"
                    % (len(got_res), len(exp_res)))
    if not exp_res:
        return 0
    planned = []
    for rel in exp_res:
        data = zip_bytes.get(rel)
        if data is None:
            raise Fail(stage, "候选 ZIP 内缺资源：%s" % rel)
        size, digest = len(data), hashlib.sha256(data).hexdigest()
        p_size, p_digest = got_res[rel]
        flags = []
        if p_size != size:
            flags.append("size 不等（平台 %d／候选 %d）" % (p_size, size))
        if p_digest != digest:
            flags.append("fileHash 不等")
        if flags:
            raise Fail(stage, "资源元数据与候选不等：%s（%s）" % (rel, "；".join(flags)))
        planned.append((rel, size, digest))
    if context is None:
        # 防御性：同域未冻结时**不得**改用登录态或逐资源 CLI；一律 fail-closed
        raise Fail(stage, "同一 (origin, key) 未冻结：拒绝回读资源（无 CLI 回退）")
    actual = read_resources_http(resource_mod, context, expect_id, planned, stage)
    if sorted(actual) != exp_res:
        raise Fail(stage, "资源 HTTP 回读项集与候选不等（%d 项／候选 %d 项）"
                    % (len(actual), len(exp_res)))
    for rel in exp_res:
        if actual[rel] != zip_bytes[rel]:
            raise Fail(stage, "资源字节不等：%s" % rel)
    return len(exp_res)


def source_identity(entry, account_id, bucket, key, stage):
    """上传前**证明**所写 bucket／key 是该对象既有来源（fail-closed）。

    只接受 URL 型 `identifier`：`url.<CF_ACCOUNT_ID>.r2.cloudflarestorage.com.<bucket>.<key>`；
    主机须为 `r2.cloudflarestorage.com`，其后缀按**首个点号**切成 `<bucket>` 与 `<key>`（key 可含
    点号，bucket 段不含），二者须与本次 `R2_BUCKET`／`--key` **完全相等**。解析不出该形态
    （如 `create` 型 `user.…`）即拒绝部署——**不用「ZIP 相同」推定 key 相同**。诊断只出固定
    字段，**不回显 identifier 或签名查询参数**。
    """
    ident = entry.get("identifier")
    if not isinstance(ident, str) or not ident.startswith("url."):
        raise Fail(stage, "平台条目 identifier 非 URL 型（如 create 型 user.…）："
                          "无法证明所写 bucket／key 是该对象既有来源，拒绝部署")
    prefix = "url.%s." % account_id
    if not ident.startswith(prefix):
        raise Fail(stage, "平台条目 identifier 前缀不是 url.<CF_ACCOUNT_ID>：拒绝部署"
                          "（所写 bucket／key 无法证明是该对象既有来源）")
    rest = ident[len(prefix):]
    host_prefix = R2_HOST + "."
    if not rest.startswith(host_prefix):
        raise Fail(stage, "平台条目 identifier 主机不是 %s：无法证明既有来源，拒绝部署" % R2_HOST)
    src_bucket, sep, src_key = rest[len(host_prefix):].partition(".")
    if not sep or src_bucket != bucket or src_key != key:
        raise Fail(stage, "平台条目 identifier 的 bucket／key 与本次上传不一致：拒绝部署"
                          "（不用「ZIP 相同」推定 key 相同）")
    return src_bucket, src_key


UNSAFE_NAME = "<非法对象名>"

def _safe_name(name):
    """不复建审计名称副本；任意登记名仅以固定占位符进入内部诊断。"""
    return UNSAFE_NAME

INVENTORY_ROOT = "skills"                 # 受管技能源固定位于仓库 `skills/` 下
INVENTORY_SKIP_NAMES = ("__pycache__",)   # 沿用既有 T3 口径
INVENTORY_SKIP_SUFFIX = ".pyc"
INVENTORY_INCOMPLETE = "检查不完整"        # 本地读取／遍历无法完成 ⇒ 内置核对分类 rc=2（部署输入失败仍按既有阶段返回2）
#: 部署取件后才进本端的官方参考原件：对象登记 `officialPackageResources.paths` 的每一项都必须
#: 落在该对象技能根内、且能映射到 `skills/luno-surge/references/upstream-manifest.json` 的
#: `raw_sha256`（3 份参考原件；映射与 `luno-surge/references/SOURCE.md`〈取件与部署〉第 3 步同源，
#: 也与 `tools/check-rules.py` 的 OFFICIAL_ORIGINALS 一致）。`agents/openai.yaml` 是本地有意
#: 改写的自有文件，走普通 `resources` 登记，不在取件名单内。
OFFICIAL_SOURCE_ROOT = "skills/luno-surge"
OFFICIAL_MANIFEST = "skills/luno-surge/references/upstream-manifest.json"
OFFICIAL_ORIGINALS = {
    "skills/luno-surge/references/upstream-SKILL.md": "SKILL.md",
    "skills/luno-surge/references/upstream-command-reference.md": "references/command-reference.md",
    "skills/luno-surge/references/plugin-authoring.md": "references/plugin-authoring.md",
}
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/+-]{1,255}$")
UNSAFE_PATH = "<非法路径>"


def _safe_path(rel):
    """包内路径进入诊断前的可信化：形态不合格（含控制字符／非 ASCII／超长）即固定占位符。"""
    return rel if isinstance(rel, str) and SAFE_PATH_RE.match(rel) else UNSAFE_PATH


def _inventory_source_root(source):
    """登记源 → 技能根（仓库相对）；不是已规整的 skills 下 SKILL.md 源即返回 None。"""
    if not isinstance(source, str) or not source:
        return None
    if os.path.isabs(source) or "\\" in source or os.path.normpath(source) != source:
        return None
    parts = source.split("/")
    if len(parts) < 3 or parts[0] != INVENTORY_ROOT or parts[-1] != "SKILL.md":
        return None
    if any(seg in ("", ".", "..") for seg in parts):
        return None
    return "/".join(parts[:-1])


def _inventory_resource_error(root_rel, rel):
    """登记资源路径的形态判据；返回固定文案说明或 None（合格）。"""
    if not isinstance(rel, str) or not rel:
        return "非字符串或空"
    if os.path.isabs(rel) or "\\" in rel:
        return "绝对路径或含反斜杠"
    if os.path.normpath(rel) != rel:
        return "未规整（含 .／..／重复分隔符）"
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in rel):
        return "含控制字符"
    if not rel.startswith(root_rel + "/"):
        return "逃逸技能根"
    if rel == root_rel + "/SKILL.md":
        return "不得把 SKILL.md 自身登记成附属资源"
    return None


def _inventory_live_files(root, root_rel, problems):
    """递归收集技能根下的全部**普通**包文件（仓库相对路径集合）。

    排除该技能自身 `SKILL.md`、`__pycache__` 与 `.pyc`（沿用既有 T3 口径）。
    符号链接、非常规文件与遍历错误一律**报检查失败**（不静默跳过），追加进 `problems`。
    """
    base = os.path.join(root, root_rel)
    found = set()
    if not os.path.isdir(base):
        problems.append((INVENTORY_INCOMPLETE, root_rel, "技能根不可达，检查不完整"))
        return found

    def _onerror(exc):
        problems.append((INVENTORY_INCOMPLETE, root_rel,
                         "遍历失败（%s），检查不完整" % type(exc).__name__))

    for dirpath, dirnames, filenames in os.walk(base, topdown=True, onerror=_onerror,
                                                followlinks=False):
        for name in list(dirnames):
            path = os.path.join(dirpath, name)
            if name in INVENTORY_SKIP_NAMES:
                dirnames.remove(name)
                continue
            if os.path.islink(path):
                problems.append((INVENTORY_INCOMPLETE, root_rel,
                                 "包内含符号链接目录，不跟随（检查不完整）"))
                dirnames.remove(name)
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if os.path.islink(path):
                problems.append((INVENTORY_INCOMPLETE, root_rel,
                                 "包内含符号链接文件，不静默跳过（检查不完整）"))
                continue
            if not os.path.isfile(path):
                problems.append((INVENTORY_INCOMPLETE, root_rel,
                                 "包内含非常规文件，检查不完整"))
                continue
            if rel == root_rel + "/SKILL.md" or name.endswith(INVENTORY_SKIP_SUFFIX):
                continue
            found.add(rel)
    return found


def official_declaration(registry, root_rel, problems):
    """登记 `officialPackageResources` → 该对象的官方取件路径集合（同时做形态与映射校验）。

    只对 `skills/luno-surge` 有效；路径必须是包内路径、必须能映射到 manifest 的 3 份参考原件
    `raw_sha256`、不得重复、不得缺项。形态不合一律进「登记异常」（rc=1），不静默放过。
    """
    declared = set()
    if root_rel != OFFICIAL_SOURCE_ROOT:
        if registry.get("officialPackageResources"):
            problems.append(("登记异常", INVENTORY_ROOT,
                             "E0 官方取件登记只允许 luno-surge 对象"))
        return declared
    block = registry.get("officialPackageResources")
    if block is None:
        return declared
    if not isinstance(block, dict) or not isinstance(block.get("paths"), list):
        problems.append(("登记异常", INVENTORY_ROOT, "E0 官方取件登记形态非法"))
        return declared
    for rel in block["paths"]:
        if not isinstance(rel, str) or rel not in OFFICIAL_ORIGINALS:
            problems.append(("登记异常", INVENTORY_ROOT, "E0 官方取件路径不可映射到参考原件"))
            continue
        if rel in declared:
            problems.append(("登记异常", INVENTORY_ROOT, "E0 官方取件路径重复"))
            continue
        declared.add(rel)
    if set(OFFICIAL_ORIGINALS) - declared:
        problems.append(("登记异常", INVENTORY_ROOT, "E0 官方取件登记缺项"))
    return declared


def official_originals_problem(registry, root, target_rel):
    """`--src` 部署目标是 `luno-surge` 时的取件门禁：声明完整＋3 份参考原件在位且哈希等于 manifest。

    只对**本次部署目标**生效（`target_rel` 即该次的 `--src` 技能根）：部署别的对象不因本仓库缺
    这三件而被拦下——门禁以前遍历整份登记，导致 `luno-core` 等构包也被 Surge 缺件判 rc=2。
    部署目标为 `luno-surge` 时，声明缺失／损坏一律拒绝，不绕过（不自动下载、不换来源、不跳过）：
    先按 `luno-surge/references/SOURCE.md`〈取件与部署〉取件、核哈希，再重跑本工具。返回固定文案或 None。
    """
    if not isinstance(registry, dict) or target_rel != OFFICIAL_SOURCE_ROOT:
        return None
    obj = next((o for o in registry.get("objects") or []
                if isinstance(o, dict)
                and _inventory_source_root(o.get("source")) == OFFICIAL_SOURCE_ROOT), None)
    block = obj.get("officialPackageResources") if isinstance(obj, dict) else None
    paths = block.get("paths") if isinstance(block, dict) else None
    if not isinstance(paths, list) or not all(isinstance(rel, str) for rel in paths) \
            or sorted(paths) != sorted(OFFICIAL_ORIGINALS):
        return ("部署目标 luno-surge 要求 officialPackageResources 完整声明这 3 份参考原件"
                "（声明缺失／损坏即拒绝，不绕过）：先按 SOURCE.md〈取件与部署〉取件后再构包")
    try:
        with open(os.path.join(root, OFFICIAL_MANIFEST), encoding="utf-8") as handle:
            raw = json.load(handle).get("raw_sha256")
    except (OSError, ValueError, TypeError, AttributeError):
        return "官方原件 manifest 不可读，无法核对取件哈希"
    if not isinstance(raw, dict):
        return "官方原件 manifest 缺 raw_sha256，无法核对取件哈希"
    for rel, key in sorted(OFFICIAL_ORIGINALS.items()):
        expect = raw.get(key)
        if not isinstance(expect, str) or not SHA256_RE.match(expect):
            return "官方原件 manifest 的 %s 哈希形态非法" % key
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            return ("官方参考原件缺失（%s）：先按 SOURCE.md〈取件与部署〉取件并核对哈希"
                    "后再构包" % _safe_path(rel))
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
        except OSError:
            return "官方参考原件不可读（%s）：检查不完整" % _safe_path(rel)
        if digest.hexdigest() != expect:
            return "官方参考原件哈希不符 manifest（%s）：不换来源、不改用第三方仓库" % _safe_path(rel)
    return None


def compare_resource_inventory(registry, root):
    """仓库包文件 ↔ 登记资源清单的**双向**核对（P2a 第 22 项）。

    只读仓库：不读资源内容、不访问 Minis／平台、不取凭据、不生成文件。诊断只用可信对象名、
    固定判据码与**可信化后的**路径／计数，不回显未经校验的路径或登记自由文本。返回既有问题
    元组列表：集合不一致／非法结构 ⇒「登记异常」／「未登记巡检」（rc=1）；读取／遍历无法
    完成 ⇒「检查不完整」（rc=2）。**合法空清单可以通过**（技能确无附属文件）；只有
    「活资源非空而登记为空」才是空清单反例。
    """
    if not isinstance(registry, dict):
        return [("登记异常", "registry", "E0 登记表顶层不是 JSON 对象")]
    objects = registry.get("objects")
    if not isinstance(objects, list):
        return [("登记异常", "objects", "E0 objects 非数组（类型=%s）" % type(objects).__name__)]
    problems = []
    entries = []
    for idx, obj in enumerate(objects):
        if not isinstance(obj, dict):
            problems.append(("登记异常", "objects[%d]" % idx, "E0 objects[] 非对象"))
            continue
        if obj.get("type") != "skill":
            continue
        name = _safe_name(obj.get("id"))
        root_rel = _inventory_source_root(obj.get("source"))
        if root_rel is None:
            problems.append(("登记异常", name,
                             "E0 技能源须为已规整的 skills/.../SKILL.md（值不输出）"))
            continue
        if "resources" not in obj:
            problems.append(("登记异常", name, "E0 技能对象缺 resources 字段（不得吞掉）"))
            continue
        res = obj.get("resources")
        if not isinstance(res, list):
            problems.append(("登记异常", name,
                             "E0 resources 非数组（类型=%s）" % type(res).__name__))
            continue
        entries.append((name, obj.get("source"), root_rel, res))
    if not entries:
        problems.append(("登记异常", "objects", "E0 技能对象为零（不得视为无差异）"))
        return problems

    # ⑥ 仓库技能源集合：整条技能登记被删后不得因此不再检查。
    repo_skills = set()
    base = os.path.join(root, INVENTORY_ROOT)
    if not os.path.isdir(base):
        problems.append((INVENTORY_INCOMPLETE, INVENTORY_ROOT, "仓库技能根不可达，检查不完整"))
        return problems

    def _onerror(exc):
        problems.append((INVENTORY_INCOMPLETE, INVENTORY_ROOT,
                         "遍历失败（%s），检查不完整" % type(exc).__name__))

    for dirpath, dirnames, filenames in os.walk(base, topdown=True, onerror=_onerror,
                                                followlinks=False):
        for name in list(dirnames):
            path = os.path.join(dirpath, name)
            if name in INVENTORY_SKIP_NAMES:
                dirnames.remove(name)
                continue
            if os.path.islink(path):
                problems.append((INVENTORY_INCOMPLETE, INVENTORY_ROOT,
                                 "技能根内含符号链接目录，不跟随（检查不完整）"))
                dirnames.remove(name)
        if "SKILL.md" in filenames:
            path = os.path.join(dirpath, "SKILL.md")
            repo_skills.add(os.path.relpath(path, root).replace(os.sep, "/"))

    for name, source, root_rel, res in entries:
        live = _inventory_live_files(root, root_rel, problems)
        obj = next((o for o in objects if isinstance(o, dict) and o.get("source") == source), {})
        official = official_declaration(obj, root_rel, problems)
        declared = set()
        for rel in res:
            err = _inventory_resource_error(root_rel, rel)
            if err:
                problems.append(("登记异常", name, "登记资源路径非法：%s" % err))
                continue
            if rel in declared:
                problems.append(("登记异常", name, "登记资源重复：%s" % _safe_path(rel)))
                continue
            if rel in official:
                problems.append(("登记异常", name,
                                 "官方取件原件不得同时登记为普通资源：%s" % _safe_path(rel)))
                continue
            declared.add(rel)
        for rel in sorted(declared - live):
            if os.path.isfile(os.path.join(root, rel)):
                problems.append(("未登记巡检", name,
                                 "登记资源不在技能包文件集内（逃逸或非普通文件）：%s"
                                 % _safe_path(rel)))
            else:
                problems.append(("未登记巡检", name,
                                 "登记资源在包内不存在（幽灵／缺失资源）：%s" % _safe_path(rel)))
        # 官方取件原件在给件后确实在包内，但它按 `officialPackageResources` 单独登记，
        # 不重复进 `resources`；未给件时本集合为空，行为与原判据一致。
        for rel in sorted(live - declared - official):
            problems.append(("未登记巡检", name,
                             "包内有、登记无（漏登记）：%s" % _safe_path(rel)))

    name_by_source = {source: name for name, source, _r, _res in entries}
    declared_sources = set(name_by_source)
    for source in sorted(declared_sources - repo_skills):
        problems.append(("未登记巡检", name_by_source[source], "登记技能源在仓库不存在"))
    extra = sorted(repo_skills - declared_sources)
    if extra:
        problems.append(("未登记巡检", UNSAFE_NAME,
                         "仓库存在 %d 个未登记的技能源（源不输出）" % len(extra)))
    return problems


def check_inventory(objects, repo, target_rel):
    """同一登记快照的离线双向清单核对；失败在候选写出／上传之前结束。

    `target_rel` 是本次 `--src` 的技能根：只有它就是 `luno-surge` 时，取件门禁（声明＋3 件哈希）
    才强制——清单核对本身仍针对整份登记，部署其它对象不受 Surge 缺件影响。
    """
    problems = compare_resource_inventory({"objects": objects}, repo)
    if problems:
        rc = 2 if any(p[0] == INVENTORY_INCOMPLETE for p in problems) else 1
        kinds = sorted({p[0] for p in problems})
        raise Fail(STAGE_INVENTORY, "资源完整清单未通过：内置离线核对 rc=%d；%s（%d 项）" %
                   (rc, "／".join(kinds), len(problems)))
    # 官方参考原件取件门禁：只在部署目标为 luno-surge 时强制；缺件／声明缺失即在此停下
    # （不自动下载、不跳过门禁），先按 SOURCE.md〈取件与部署〉取件后重跑。
    problem = official_originals_problem({"objects": objects}, repo, target_rel)
    if problem:
        raise Fail(STAGE_INVENTORY, "官方取件门禁未通过：%s" % problem)



# ── 包有效性（空包在这里拒绝；这是进入上传前唯一的包有效性拒绝点）──────────────

class PackageProblems(list):
    """包问题列表及本次 CRC 校验取得的不可变成员内容。"""

    def __init__(self):
        super().__init__()
        self.zip_bytes = None


def package_problems(entries, name, blob, body_contract):
    """逐项体检：空包／缺根 SKILL.md／SKILL.md 无效或名称不符／非常规权限／ZIP 与源不等。

    **空包在首条返回**：本函数是空包进入上传前唯一的拦截点（调用方据此**一处**拒绝）。
    """
    if not entries:
        return ["空包（源内无文件；本入口不打包空 ZIP）"]
    paths = dict(entries)
    problems = PackageProblems()
    if SKILL_FILE not in paths:
        problems.append("缺根 %s" % SKILL_FILE)
    for rel, path in entries:
        mode = os.stat(path).st_mode & 0o7777
        if mode != PACK_MODE:
            problems.append("非常规权限 %04o：%s（通用权限支持属 P2b，本批不压平权限）"
                            % (mode, rel))
    if SKILL_FILE in paths:
        raw = read_bytes(paths[SKILL_FILE])
        try:
            fm_name = body_contract.fm_get(raw, "name")
        except body_contract.ContractError as exc:
            problems.append("%s frontmatter 不合契约（%s）" % (SKILL_FILE, exc.code))
        else:
            if fm_name is body_contract.MISSING:
                problems.append("%s 缺 frontmatter name" % SKILL_FILE)
            elif not isinstance(fm_name, str) or fm_name != name:
                problems.append("%s frontmatter name 与 --name 不等" % SKILL_FILE)
        try:
            if not body_contract.body_bytes(raw).strip():
                problems.append("%s 正文为空" % SKILL_FILE)
        except body_contract.ContractError as exc:
            problems.append("%s 正文不合契约（%s）" % (SKILL_FILE, exc.code))
    # 逐个 ZipInfo 读取会验证每个成员的 CRC（等价于 testzip），同时保存内容供后续复用。
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            contents = {info.filename: archive.read(info) for info in infos}
    except zipfile.BadZipFile:
        problems.append("打包结果不是合法 ZIP")
        return problems
    problems.zip_bytes = contents
    if sorted(names) != sorted(paths):
        problems.append("ZIP 文件集与源不等（zip %d 项／源 %d 项）" % (len(names), len(paths)))
    else:
        for rel, path in entries:
            if contents[rel] != read_bytes(path):
                problems.append("ZIP 内容与源不等：%s" % rel)
    if SKILL_FILE not in names:
        problems.append("ZIP 内缺根 %s" % SKILL_FILE)
    return problems


def first_difference(left, right):
    """两个已排序列表的首个差异（只输出路径，不输出内容）。"""
    only_left = [item for item in left if item not in right]
    only_right = [item for item in right if item not in left]
    if only_left:
        return only_left[0]
    if only_right:
        return only_right[0]
    return "(顺序不同)"


def source_drift(pack, src_abs, entries, blob):
    """源端复核（F5）：重新收集＋重新打包，与**候选快照**逐文件比对；返回固定问题列表（空＝未变）。

    同一判定函数用于**两个**检查点：**上传前**（未进入写路径 ⇒ rc=2）与**安装后、成功返回前**
    （写路径已开始 ⇒ rc=1）。不一致时**不重新打包替换候选**——本次部署对象始终是已核定的候选
    ZIP；本函数**只判定**，不写任何东西（无产物、无平台／存储访问）。
    """
    try:
        now = pack.collect(src_abs)
        now_blob = pack.build(now)
    except Exception as exc:                    # 收集／打包异常一律按「源端不可复核」fail-closed
        return ["源端重新收集失败（%s）" % exc.__class__.__name__]
    if now_blob == blob:
        return []
    problems = []
    cand_names = sorted(rel for rel, _path in entries)
    now_names = sorted(rel for rel, _path in now)
    if now_names != cand_names:
        problems.append("源文件集已变化（现 %d 项／候选 %d 项；首个差异 %s）"
                        % (len(now_names), len(cand_names),
                           first_difference(now_names, cand_names)))
    try:
        cand_bytes = zip_member_bytes(blob, STAGE_LOCAL)
    except Fail:
        cand_bytes = {}
    for rel, path in now:
        if rel not in cand_bytes:
            continue
        try:
            data = read_bytes(path)
        except Fail:
            problems.append("源端文件不可读：%s" % rel)
            continue
        if data != cand_bytes[rel]:
            problems.append("源端内容已变化：%s" % rel)
    if not problems:
        problems.append("源端 ZIP 逐字节不等（差异未落在候选成员上）")
    return problems


# ── 参数与登记 ──────────────────────────────────────────────────────────────

REQUIRED_ARGS = ("--repo", "--src", "--name", "--key", "--out-dir", "--expect-id")
#: 可选参数：值形态在**解析期**校验（不合格即参数无效 rc=2，先于任何读写）
OPTIONAL_ARGS = ("--expect-zip-sha256",)


def parse_args(argv):
    """返回 (cfg, bad)；bad 非 None 表示参数无效。`--help` 直接打印用法并退出 0。"""
    got = {}
    deploy = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            sys.stdout.write(USAGE + "\n")
            raise SystemExit(0)
        if arg == "--deploy":
            deploy = True
            i += 1
            continue
        if arg in OPTIONAL_ARGS:
            if arg in got:
                # 仅**本门禁参数**拒绝重复：同一参数给两次时无法判定哪一个是「已核实的包」，
                # 故 fail-closed；其他旧参数保留既有「后者覆盖」语义（不在本批改动范围）。
                return None, "参数 %s 不允许重复给出" % arg
            if i + 1 >= len(argv):
                return None, "参数 %s 缺值" % arg
            value = argv[i + 1]
            # `fullmatch` 而非 `match`：`^…$` 的 `$` 会容许**单 LF 结尾**（`"<64 hex>\n"` 曾因此
            # 通过格式校验并被回显进日志——LENS F1）。只接受完整 64 位小写十六进制；不合格时
            # **不回显**该值（外部自由文本，可能含换行／控制字符，会注入日志）。
            if not SHA256_RE.fullmatch(value):
                return None, "参数 %s 须为完整 64 位小写十六进制 SHA-256" % arg
            got[arg] = value
            i += 2
            continue
        if arg in REQUIRED_ARGS:
            if i + 1 >= len(argv):
                return None, "参数 %s 缺值" % arg
            got[arg] = argv[i + 1]
            i += 2
            continue
        return None, "未知参数 %s" % arg
    if "--src" not in got:
        return None, "缺少必填参数 --src（本入口不用环境变量、不按名称猜源目录）"
    missing = [arg for arg in REQUIRED_ARGS if arg not in got]
    if missing:
        return None, "缺少必填参数：%s" % "／".join(missing)
    got["deploy"] = deploy
    return got, None


def load_registry(repo):
    path = os.path.join(repo, "tools", "sync-targets.json")
    if not os.path.isfile(path):
        raise Fail(STAGE_LOCAL, "--repo 内缺登记真源：%s" % path)
    try:
        with open(path, "rb") as fh:
            doc = json.loads(fh.read().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise Fail(STAGE_LOCAL, "登记不可读或不是合法 JSON（%s）" % exc.__class__.__name__)
    objects = doc.get("objects") if isinstance(doc, dict) else None
    if not isinstance(objects, list):
        raise Fail(STAGE_LOCAL, "登记缺 objects 数组：%s" % path)
    return objects


def registry_entry(objects, name):
    hits = [obj for obj in objects
            if isinstance(obj, dict) and obj.get("id") == name and obj.get("type") == "skill"]
    if len(hits) != 1:
        raise Fail(STAGE_LOCAL, "登记中 type=skill 且 id=%s 的对象不是恰好 1 个（命中 %d 个）"
                    % (name, len(hits)))
    return hits[0]


def resolve_target(cfg, objects=None, with_registry=False):
    """核 `--repo`／登记对象名／源路径／平台 ID 与参数完全一致，返回规范化后的落点。"""
    repo = os.path.abspath(cfg["--repo"])
    name = cfg["--name"]
    key = cfg["--key"]
    expect_id = cfg["--expect-id"]
    src_arg = cfg["--src"]
    if not NAME_RE.match(name):
        raise Fail(STAGE_LOCAL, "--name 须为小写 slug（a-z0-9-）：%s" % name)
    if not PLATFORM_ID_RE.match(expect_id):
        raise Fail(STAGE_LOCAL, "--expect-id 须为登记平台 ID 形态 skl_<字母数字>：%s" % expect_id)
    if not KEY_RE.match(key):
        raise Fail(STAGE_LOCAL, "--key 须为单段对象 key（首字符字母数字、只含 A-Za-z0-9._-、"
                                "≤128）；不接受 URL／查询串／路径分隔符")
    if not os.path.isdir(repo):
        raise Fail(STAGE_LOCAL, "--repo 不是目录：%s" % repo)
    if objects is None:
        objects = load_registry(repo)
    entry = registry_entry(objects, name)
    reg_source = entry.get("source")
    if not isinstance(reg_source, str) or os.path.basename(reg_source) != SKILL_FILE:
        raise Fail(STAGE_LOCAL, "登记对象的 source 不是 <目录>/%s：%s" % (SKILL_FILE, name))
    reg_dir = os.path.dirname(reg_source)
    src_abs = os.path.normpath(src_arg if os.path.isabs(src_arg)
                               else os.path.join(repo, src_arg))
    src_rel = os.path.relpath(src_abs, repo).replace(os.sep, "/")
    if src_rel != reg_dir:
        raise Fail(STAGE_LOCAL, "--src 与登记源路径不一致（不按名称猜源目录）：登记 %s ≠ 参数 %s"
                    % (reg_dir, src_rel))
    ends = entry.get("ends")
    lobe = ends.get("lobehub") if isinstance(ends, dict) else None
    if not isinstance(lobe, dict) or lobe.get("present") is not True \
            or not isinstance(lobe.get("id"), str):
        raise Fail(STAGE_LOCAL, "登记对象 %s 缺 lobehub 落点／平台 ID" % name)
    if lobe.get("id") != expect_id:
        raise Fail(STAGE_LOCAL, "--expect-id 与登记平台 ID 不一致：登记 %s ≠ 参数 %s"
                    % (lobe.get("id"), expect_id))
    if os.path.islink(src_abs) or not os.path.isdir(src_abs):
        raise Fail(STAGE_LOCAL, "--src 不是普通目录（不存在／非目录／符号链接）：%s" % src_rel)
    result = (repo, src_rel, src_abs, key, expect_id)
    return result + (objects,) if with_registry else result


def dedicated_packer_rel(src_rel):
    """该源路径是否有专用打包器；无则 None（→ 沿用通用 `tools/pack-skill-zip.py`）。"""
    return DEDICATED_PACKERS.get(src_rel.replace(os.sep, "/"))


def require_dedicated_digest(src_rel, deploy, expect_digest):
    """专用打包器的写路径先决条件：`--deploy` 必须显式给出已审核候选的完整摘要。

    位置在**加载专用器之前**：缺摘要时不导入模块、不收集源、不写产物、不访问平台／存储。
    只打包（无 `--deploy`）不强制，行为与旧调用一致。
    """
    if deploy and dedicated_packer_rel(src_rel) and expect_digest is None:
        raise Fail(STAGE_LOCAL, "该技能（%s）走专用打包器，`--deploy` 必须显式给出"
                                " --expect-zip-sha256（已审核候选的完整 64 位小写十六进制）；"
                                "未加载专用打包器、未产出候选包、未访问平台或存储"
                    % src_rel)


def dedicated_packer_path(repo, src_rel, rel):
    """专用器的**导入前**路径与类型检查：通过才返回可加载路径，任一不符即固定分类失败。

    检查的是「登记源内固定 `scripts/` 目录 + 该目录下的普通非链接模块文件 + 解析后仍在登记源
    内」三件事，**不**引入模块固定 pin、全链 dirfd 身份机制或额外预检包；也不改变通用器。
    前提仍是：该克隆可信、已审、单写入者、无敌意并发。
    """
    scripts_rel = os.path.dirname(rel)
    scripts_abs = os.path.join(repo, scripts_rel)
    path = os.path.join(repo, rel)
    if scripts_rel != src_rel.rstrip("/") + "/scripts":
        raise Fail(STAGE_LOCAL, "专用打包器不在登记源的固定 scripts 目录内；拒绝加载（%s）"
                    % rel)
    if os.path.islink(scripts_abs):
        raise Fail(STAGE_LOCAL, "专用打包器的 scripts 目录是符号链接；拒绝加载（%s）"
                    % scripts_rel)
    if not os.path.isdir(scripts_abs):
        raise Fail(STAGE_LOCAL, "专用打包器的 scripts 目录缺失或不是目录：%s" % scripts_rel)
    if os.path.islink(path):
        raise Fail(STAGE_LOCAL, "专用打包器模块本身是符号链接；拒绝加载（%s）" % rel)
    if not os.path.isfile(path):
        raise Fail(STAGE_LOCAL, "专用打包器模块缺失或不是普通文件：%s" % rel)
    real_src = os.path.realpath(os.path.join(repo, src_rel))
    if not os.path.realpath(path).startswith(real_src.rstrip(os.sep) + os.sep):
        raise Fail(STAGE_LOCAL, "专用打包器解析后不在登记源内；拒绝加载（%s）" % rel)
    return path


def load_dedicated_module(path):
    """导入专用器：既有 Fail 原样保留；导入期异常一律转本地固定分类，只报类名。"""
    try:
        return load_module(path, "dedicated_package_release")
    except Fail:
        raise                               # 缺模块等既有固定分类失败（文本不含秘密）保持原样
    except SystemExit as exc:
        raise Fail(STAGE_LOCAL, "专用打包器导入失败（%s）；未产出包、未访问平台或存储"
                    % exc.__class__.__name__)
    except Exception as exc:                # SyntaxError／RuntimeError 等：只给类名，不回显文本
        raise Fail(STAGE_LOCAL, "专用打包器导入失败（%s）；未产出包、未访问平台或存储"
                    % exc.__class__.__name__)


def load_packer(repo, src_rel):
    """返回 (打包器模块, 是否专用器)。专用器先做导入前检查再导入，**不回退**通用器。"""
    rel = dedicated_packer_rel(src_rel)
    if rel is None:
        return load_module(os.path.join(repo, "tools", "pack-skill-zip.py"), "pack_skill_zip"), False
    return load_dedicated_module(dedicated_packer_path(repo, src_rel, rel)), True


def pack_collect(pack, src_abs, dedicated):
    """收集源条目。专用器的失败（含以 `SystemExit` 报错的形态）一律转本地固定分类失败，
    **不回显其文本**（可能含自由文本），也不让 `SystemExit` 直接结束进程。"""
    if not dedicated:
        try:                        # 通用器沿用既有转译：OSError → 源收集失败（rc=2，不打 traceback）
            return pack.collect(src_abs)
        except OSError as exc:
            raise Fail(STAGE_PACK, "源收集失败（符号链接／非常规条目／遍历错误）：%s" % exc)
    try:
        return pack.collect(src_abs)
    except SystemExit as exc:
        raise Fail(STAGE_PACK, "专用打包器拒绝该源（%s）；未产出任何包"
                    % exc.__class__.__name__)
    except OSError as exc:
        raise Fail(STAGE_PACK, "源收集失败（符号链接／非常规条目／遍历错误）：%s"
                    % exc.__class__.__name__)
    except Exception as exc:                # 固定类别：只给异常类名，不回显消息
        raise Fail(STAGE_PACK, "专用打包器收集失败（%s）；未产出任何包"
                    % exc.__class__.__name__)


def pack_build(pack, entries, dedicated):
    """按条目构包。专用器的秘密命中／构建失败转本地固定分类失败（rc=2），只给类名。"""
    if not dedicated:
        return pack.build(entries)
    try:
        return pack.build(entries)
    except SystemExit as exc:
        raise Fail(STAGE_LOCAL, "专用打包器构建失败（%s）；未产出候选包"
                    % exc.__class__.__name__)
    except Exception as exc:
        raise Fail(STAGE_LOCAL, "专用打包器拒绝该源（%s）；未产出候选包、未上传"
                    % exc.__class__.__name__)


def resolve_out_dir(out_dir, src_abs):
    out_abs = os.path.abspath(out_dir)
    if not os.path.isdir(out_abs):
        raise Fail(STAGE_LOCAL, "--out-dir 不是已存在目录（本入口不创建目录）：%s" % out_abs)
    src_real = os.path.realpath(src_abs)
    out_real = os.path.realpath(out_abs)
    if out_real == src_real or out_real.startswith(src_real.rstrip(os.sep) + os.sep):
        raise Fail(STAGE_LOCAL, "--out-dir 位于 --src 之内（产物会被下次打包吸入）：%s" % out_abs)
    return out_abs


# ── 部署（只有 --deploy 才进入）─────────────────────────────────────────────

def require_deploy_authorization():
    """**防误触断言**（不是授权来源）：须由主助理先核既有部署授权，再传 `--deploy`。

    环境变量只是防误触标记；缺即拒绝，且调用点在**任何写操作之前**（含候选包写出）。
    """
    if env_get(AUTH_ENV) != AUTH_VALUE:
        raise Fail(STAGE_AUTH, "防误触断言未通过：--deploy 须由主助理先核既有部署授权"
                               "（%s=%s 只是防误触标记，不构成授权来源）；"
                               "缺即拒绝，不产生任何写操作" % (AUTH_ENV, AUTH_VALUE))


def identity_problems(after, expect_id, digest):
    """回读**不可修补**的字段判等：id 与 zipFileHash（任一不符即立即失败，不走 update 修补）。"""
    problems = []
    if after.get("id") != expect_id:
        problems.append("回读 id 改变：%s ≠ --expect-id" % after.get("id"))
    after_hash = after.get("zipFileHash")
    if not isinstance(after_hash, str) or after_hash.lower() != digest:
        problems.append("回读 zipFileHash 与候选 ZIP sha256 不一致")
    return problems


def field_problems(after, name, want_desc):
    """回读**可经 manifest 修正**的字段判等：name 与 description。

    平台把 `content`／`description`／`name` 当三个独立字段（`lh skill edit` 不带 `--description`
    时描述会静默留旧文案），故二者不符属可修补差异：合并进同一次 `agentSkills.update` 的 `manifest`
    （`{name, description}`）后重核。
    """
    problems = []
    if after.get("name") != name:
        problems.append("回读 name 与 --name 不一致")
    if (after.get("description") or "") != want_desc:
        problems.append("回读 description 与源 frontmatter 不等")
    return problems


def readback_problems(after, expect_id, name, digest, want_desc):
    """回读**完整白名单对象**的字段判等：id／zipFileHash／name／description。

    返回固定问题列表（空列表＝全部相等；顺序固定为 id→zipFileHash→name→description）。`content`
    因「可能裁尾 LF」另走受支持的 edit 修补，但修补后仍须**重新取得完整对象**并重跑本函数，不得只重读
    `content`。分解口径：`identity_problems`（不可修补）＋`field_problems`（可经 manifest 修正），
    本函数供**未变对象只读分支**整体判等使用。
    """
    return (identity_problems(after, expect_id, digest)
            + field_problems(after, name, want_desc))


def patch_baseline(entry):
    """安装后**首次**完整回读的**修补基线**（复审 F4）：只记可修补的三个值，不留平台原文。

    `content` 存 bytes（与候选正文同一口径），`description` 缺省按空串归一（与 `field_problems`
    一致）。基线只用于「写前比对」，不写盘、不进日志。
    """
    return {"name": entry.get("name"),
            "description": entry.get("description") or "",
            "content": (entry.get("content") or "").encode("utf-8")}


def patch_guard(baseline, expect_id, digest, name, want_desc, want, stage):
    """`update`（**含每次重试**）前的并发复核闭包：完整性异常或**第三个值**即停止，不用写覆盖。

    写前那次回读**先**判 `identity_problems`（`id`／`zipFileHash`）：任一不一致——例如候选源或
    对象在安装与修补之间被替换——立即 `Fail` 且**零写入**，不得先发 `update` 再由回读发现异常
    （那时已经不是零写；复审 N1）。随后判第三个值＝既不是修补基线值、也不是候选期望值
    （`name`／`description`／`content` 三面各判）。平台没有可证的 CAS，故每次写前重读并比对基线；
    一旦发现并发变更（人或其他流程改了同一对象），必须停下来交人工，而不是把别人刚写的内容静默
    覆盖（复审 F4：实测静默覆盖且 rc=0）。该读经 `bounded_entry`，**同样携带剩余预算**（复审 F2）。
    失败文案只报**字段名**，不回显任何字段值。
    """
    def check():
        entry = bounded_entry(expect_id, stage)
        blocking = identity_problems(entry, expect_id, digest)
        if blocking:
            raise Fail(stage, "写前复核发现完整性异常（零写入停止，不发 update）：%s"
                        % "；".join(blocking))
        current = patch_baseline(entry)
        changed = [field for field, wanted in (("name", name),
                                              ("description", want_desc),
                                              ("content", want))
                   if current[field] != baseline[field] and current[field] != wanted]
        if changed:
            raise Fail(stage, "写前复核发现并发变更（字段：%s）：既非修补基线、也非候选期望值；"
                              "停止本次修补，不用 update 覆盖" % "／".join(changed))
    return check


def poll_repaired_entry(expect_id, name, digest, want_desc, want, stage):
    """补写后按 `REPAIR_POLL_DELAYS`（0／0.5／1／2／4 s）轮询平台收敛，相等即停。

    每轮取**完整白名单对象**并重跑判等（不用「稍后再读一次」代替判等，也不只重读 `content`）。
    总预算 `REPAIR_POLL_BUDGET`（10 s，**含读取本身**；超预算的等待点跳过）：
      · 每次读取都带**剩余预算**（`subprocess.run` 的 `timeout`），单次读超预算即中止子进程并失败；
        只约束等待、放过单次读 12 s 仍判成功，等于没有预算（复审 F2）；
      · 读取返回后**再复查**总耗时：已超预算即失败（子进程计时不准或收尾拖长时同样不判成功）。
    每轮都**先**判 id／zipFileHash：任一轮出现差异即立即失败（文案指出完整性异常、不继续等），
    不用「下一轮又对了」掩盖完整性异常（复审 F3）。
    超时仍不等即 `Fail`：detail 只带轮询次数、末次正文字节数与固定问题文案（不回显平台原文）。
    返回收敛后的完整对象，供随后的资源集／bytes 核验复用（不再多一次 `view`）。
    """
    start = time.monotonic()
    entry = None
    problems = []
    got = b""
    polls = 0

    def remaining():
        return REPAIR_POLL_BUDGET - (time.monotonic() - start)

    for delay in REPAIR_POLL_DELAYS:
        if delay:
            if delay > remaining():
                break
            time.sleep(delay)
        budget = remaining()
        if budget <= 0:
            raise Fail(stage, "补写后回读已无剩余预算（上限 %s s，第 %d 轮前停止）：不判成功"
                        % (REPAIR_POLL_BUDGET, polls + 1))
        polls += 1
        entry = platform_entry(expect_id, stage, timeout=budget)
        if remaining() < 0:
            raise Fail(stage, "补写后第 %d 轮读取超过剩余预算（上限 %s s）：不判成功"
                        % (polls, REPAIR_POLL_BUDGET))
        blocking = identity_problems(entry, expect_id, digest)
        if blocking:
            raise Fail(stage, "补写后回读出现完整性异常（第 %d 轮即停止，不继续等待）：%s"
                        % (polls, "；".join(blocking)))
        problems = field_problems(entry, name, want_desc)
        got = (entry.get("content") or "").encode("utf-8")
        if not problems and got == want:
            return entry
    detail = "补写后轮询 %d 次仍未收敛（末次正文 %d／%d B）" % (polls, len(got), len(want))
    if problems:
        detail += "：%s" % "；".join(problems)
    raise Fail(stage, detail)


def verify_unchanged(before, expect_id, name, digest, want_desc, want, exp_res, zip_bytes,
                     resource_mod, context, timer):
    """未变对象只读分支：**只跳写入、不跳核验**（零 R2 上传／零 install／零 edit）。

    候选 ZIP sha256 等于现场 `zipFileHash` 时进入；仍按登记 `--expect-id` 核 id、来源身份、
    name、description、正文与全部资源 bytes。任一差异一律 fail-closed 并停止——**不报跳过成功**，
    也**不**用 edit 修补正文（含「恰少一个尾 LF」形态）。该分支未进入写路径，故失败为 rc=2。
    """
    with timer.phase(STAGE_READBACK):
        problems = readback_problems(before, expect_id, name, digest, want_desc)
        if problems:
            raise Fail(STAGE_READONLY, "未变对象核验未通过（未执行部署写入）：%s"
                        % "；".join(problems))
        got = (before.get("content") or "").encode("utf-8")
        if got != want:
            raise Fail(STAGE_READONLY, "未变对象核验未通过（未执行部署写入）：正文与候选 ZIP "
                                       "bytes 不等（%d／%d B）；本分支不用 edit 修补，停止"
                        % (len(got), len(want)))
    with timer.phase(STAGE_RESOURCE, len(exp_res)):
        count = verify_resource_bytes(expect_id, before, exp_res, zip_bytes, resource_mod,
                                      context, STAGE_READONLY)
    log("核验一致，未执行部署写入")
    log("未变对象只读分支：id／来源身份／name／description／正文／资源 %d 项 bytes 全部相等；"
        "零 R2 上传／零 install／零 edit" % count)


def run_deploy(cfg, entries, blob, digest, out_abs, pack, src_abs, body_contract, timer, zip_bytes):
    repo = os.path.abspath(cfg["--repo"])
    name = cfg["--name"]
    key = cfg["--key"]
    expect_id = cfg["--expect-id"]
    require_deploy_authorization()      # 防御性复核；主检查在 `run()`，位于任何写操作之前

    # 防御性复核（专用打包器）：进入写路径前**再**核一次摘要门禁——即使 `_run` 的调用顺序
    # 被后续改动打乱，也不会在没有「已审核候选逐位相符」的情况下上传／安装。此处任何写操作
    # 都还未发生（回滚包、上传、install、edit 均在其后）。
    dedicate_rel = os.path.relpath(src_abs, repo).replace(os.sep, "/")
    if dedicated_packer_rel(dedicate_rel) and cfg.get("--expect-zip-sha256") != digest:
        raise Fail(STAGE_LOCAL, "防御性复核：该技能（%s）要求 --expect-zip-sha256 与本次构包 "
                                "sha256 逐位相等；已停止，未上传／未安装／未编辑" % dedicate_rel)

    # 同域前置＝**硬门槛**：资源回读传输与 CLI runner 在**任何平台／存储访问之前**定妥，且共用
    # 同一 `(origin, key)`。任一不成立（缺指定 key／key 含非法字符／origin 不符／显式 workspace／
    # lh 无法解析为绝对 argv）即固定分类失败停止——零 HTTP、零 R2 读取／上传、零 install、
    # 零 edit。**不退回登录态、不改用其它实例、不退回逐资源 CLI read-resource**。
    resource_mod = load_module(os.path.join(repo, "tools", RESOURCE_MODULE),
                               os.path.splitext(RESOURCE_MODULE)[0])
    context = freeze_resource_context(resource_mod)
    if context is None:
        raise Fail(STAGE_PLATFORM, "同域前置未通过；停止本次部署，未执行平台或存储写入")
    runner = freeze_cli_runner(context[0], context[1])
    log("CLI runner：已冻结（绝对 argv＋空 HOME/XDG＋受控 env：%s；编译缓存%s）；与 HTTP 共用同一 "
        "(origin, key)" % ("／".join(CliRunner.ENV_KEYS),
                           "已启用" if runner.compile_cache is not None
                           else "不可用（已省略，不影响 CLI 结果）"))

    # 候选 ZIP 是**不可变事实来源**：正文／描述与逐资源 size／sha256 一律取自包内 bytes
    try:
        want_desc = body_contract.fm_get(zip_bytes[SKILL_FILE], "description")
        want = body_contract.body_bytes(zip_bytes[SKILL_FILE])
    except body_contract.ContractError as exc:
        raise Fail(STAGE_PLATFORM, "%s 不合契约（%s）" % (SKILL_FILE, exc.code))
    want_desc = "" if want_desc is body_contract.MISSING or want_desc is None else want_desc
    exp_res = sorted(rel for rel, _path in entries if rel != SKILL_FILE)

    with timer.phase(STAGE_PLATFORM):
        # 复审 F2 第二轮：该读同样带剩余预算（`bounded_entry`：子进程 timeout＋返回后复查总耗时），
        # 不再留 `timeout=None`。阶段仍为「平台回读」⇒ 写路径前失败仍归 rc=2（rc 分类不动）。
        before = bounded_entry(expect_id, STAGE_PLATFORM)
        if before.get("id") != expect_id:
            raise Fail(STAGE_PLATFORM, "平台回读 id 与 --expect-id 不符")
        if before.get("name") != name:
            raise Fail(STAGE_PLATFORM, "平台回读 name 与 --name 不符")
        # 上传前证明所写 bucket／key 就是该对象既有来源（fail-closed；不用 ZIP 相同推定）
        source_identity(before, env_get("CF_ACCOUNT_ID"), env_get("R2_BUCKET"), key,
                        STAGE_PLATFORM)
        pre_hash = before.get("zipFileHash")
        if not isinstance(pre_hash, str) or not SHA256_RE.match(pre_hash.lower()):
            raise Fail(STAGE_ROLLBACK, "平台部署前 zipFileHash 不是完整 64 位十六进制；"
                                       "回滚能力不成立，停止部署")
        pre_hash = pre_hash.lower()
    log("平台回读（部署前）：id=%s zipFileHash=%s" % (expect_id, pre_hash))

    # 源端复核①（F5，**上传前**／进入只读分支前）：打包后源目录是否变化——不一致即停止
    # （未进入写路径 ⇒ rc=2），**不重新打包替换候选**（本次部署对象始终是已核定的候选 ZIP）。
    # 该检查落在打开存储／回滚包／上传之前，且**两个分支都经过**（未变只读分支不写平台／存储，
    # 命中时同属 rc=2）：命中时零 R2 读取、零上传、零 install、零 edit。
    with timer.phase(STAGE_SNAPSHOT):
        drift = source_drift(pack, src_abs, entries, blob)
        if drift:
            raise Fail(STAGE_SNAPSHOT, "打包后源端已变化（未进入写路径；未上传）：%s"
                        % "；".join(drift))
    log("源端复核（上传前）：源文件集与逐文件 bytes 与候选快照一致")

    if pre_hash == digest:
        # 未变对象只读分支（只跳写入、不跳核验）；零存储访问 ⇒ SDK 初始化被推迟到这里之后
        verify_unchanged(before, expect_id, name, digest, want_desc, want, exp_res,
                         zip_bytes, resource_mod, context, timer)
        return

    with timer.phase(STAGE_ROLLBACK):
        storage = open_storage()
        rollback = storage.download(key)
        if hashlib.sha256(rollback).hexdigest() != pre_hash:
            raise Fail(STAGE_ROLLBACK, "同 key 现存对象与平台部署前 zipFileHash 不一致；"
                                       "回滚能力不成立，停止部署")
        rollback_path = os.path.join(out_abs, name + ROLLBACK_SUFFIX)
        write_atomic(rollback_path, rollback, STAGE_ROLLBACK)
        if hashlib.sha256(read_bytes(rollback_path)).hexdigest() != pre_hash:
            raise Fail(STAGE_ROLLBACK, "回滚包实读 sha256 与平台部署前哈希不一致")
    log("回滚包：%s（实读 sha256 与平台部署前 zipFileHash 逐位相等）" % rollback_path)

    with timer.phase(STAGE_UPLOAD):
        storage.upload(key, blob)
    log("上传：key=%s bytes=%d sha256=%s" % (key, len(blob), digest))

    with timer.phase(STAGE_DOWNLOAD):
        url = storage.presigned_get(key)
        if storage.fetch(url) != blob:
            raise Fail(STAGE_DOWNLOAD, "预签名 GET 所得 bytes 与候选 ZIP 不一致")
    log("下载校验：预签名 GET 与候选 ZIP 逐字节相等（URL 只在内存中，未落日志）")

    with timer.phase(STAGE_INSTALL):
        write_skill_http(context, "install", {"url": url}, STAGE_INSTALL)
    log("安装：官方 importFromUrl HTTP 已返回 status=200 且信封为 result 形态"
        "（请求已返回，待完整回读判等）")

    with timer.phase(STAGE_READBACK):
        # 复审 F2 第二轮：安装后这次完整回读同样带剩余预算（子进程 timeout＋返回后复查总耗时）。
        after = bounded_entry(expect_id, STAGE_READBACK)
        # id 改变／zipFileHash 不符属**不可修补**差异：不写入、立即失败（与可经 manifest 修正的
        # name／description 明确分开，后者不再直接失败）。
        blocking = identity_problems(after, expect_id, digest)
        if blocking:
            raise Fail(STAGE_READBACK, "；".join(blocking))
        fields = field_problems(after, name, want_desc)
        got = (after.get("content") or "").encode("utf-8")
        # 只有**恰少一个尾 LF** 才是可修补的平台形态；任意其它差异一律停止，不自动改写。
        if got != want and not (want.endswith(b"\n") and got == want[:-1]):
            raise Fail(STAGE_READBACK, "正文不等且非恰少一个尾 LF；停止，不自动改写")
        if got != want or fields:
            # 正文补 LF 与 name／description 不符**合并成一次** `agentSkills.update`：平台把
            # content／description／name 当独立字段（edit 不带 manifest 时描述会静默留旧文案），
            # 故 `content` 只在需要时给，`manifest` 只在字段不符时给。该调用幂等（同 id 同 content），
            # 由 `write_skill_http` 只对瞬时失败做有界重试。
            # 并发防护（复审 F4）：安装后的**这次**完整回读即修补基线；每次 update（含重试）之前
            # 重读并比对基线，出现第三个值（非基线、非候选期望）即停止，不用写覆盖别人的改动。
            baseline = patch_baseline(after)
            guard = patch_guard(baseline, expect_id, digest, name, want_desc, want, STAGE_EDIT)
            payload = {"id": expect_id}
            if got != want:
                payload["content"] = want.decode("utf-8")
            if fields:
                payload["manifest"] = {"name": name, "description": want_desc}
            # 计时口径：**保留嵌套**——父阶段「回读判等」**包含**本阶段「正文修补」的耗时，
            #   各阶段耗时**不得相加**；失败检查在计时块**内**，故本阶段的 rc 如实反映成败。
            with timer.phase(STAGE_EDIT):
                write_skill_http(context, "edit", payload, STAGE_EDIT, guard=guard)
            log("正文修补／元数据修正：官方 update HTTP 已返回 status=200 且信封为 result 形态"
                "（请求已返回，待轮询完整回读判等）")
            # 补写后**按 0／0.5／1／2／4 s 轮询**取完整白名单对象重核（id／zipFileHash／
            # name／description 与正文逐字节），相等即停；超时仍不等才失败（带轮询次数与末次字节数）。
            after = poll_repaired_entry(expect_id, name, digest, want_desc, want, STAGE_READBACK)
    with timer.phase(STAGE_RESOURCE, len(exp_res)):
        verify_resource_bytes(expect_id, after, exp_res, zip_bytes, resource_mod, context,
                              STAGE_READBACK)
    # 源端复核②（F5，**全部资源回读之后、成功返回前**）：同一判定函数再核一次；命中即写路径后的
    # 固定分类失败（rc=1）——部署已写入完成，但源目录在部署窗口内发生变化，须人工确认是否重投。
    # 位置在平台 view／edit／全资源回读**之后**：这些步骤都在部署窗口内，若检查早于它们，窗口
    # 内的源变化仍会报成功。仍只保留两次检查、**不重新打包替换候选**、不替换已核定的候选 ZIP。
    with timer.phase(STAGE_SNAPSHOT_AFTER):
        drift = source_drift(pack, src_abs, entries, blob)
        if drift:
            raise Fail(STAGE_SNAPSHOT_AFTER,
                        "部署已写入完成，但源目录在部署窗口内发生变化，须人工确认是否重投"
                        "（未重新打包替换候选）：%s" % "；".join(drift))
    log("源端复核（安装后）：源文件集与逐文件 bytes 仍与候选快照一致")
    log("回读判等：id／zipFileHash／name／description／正文／全资源 %d 项 全部相等"
        % len(exp_res))


# ── 主流程 ──────────────────────────────────────────────────────────────────

def run(cfg):
    """分阶段计时外壳：无论成败都输出各阶段耗时与总耗时（**不含** argv／URL／原始报文）。"""
    timer = PhaseTimer()
    try:
        _run(cfg, timer)
    except Fail as exc:
        timer.report(exc.rc)
        raise
    timer.report(0)


def _run(cfg, timer):
    repo, src_rel, src_abs, key, expect_id, objects = resolve_target(cfg, with_registry=True)
    out_abs = resolve_out_dir(cfg["--out-dir"], src_abs)
    name = cfg["--name"]
    deploy = bool(cfg["deploy"])
    if deploy:
        # 授权断言（防误触）在**任何写操作之前**：缺断言时 `--out-dir` 不被触碰、无产物写出。
        require_deploy_authorization()
        log("防误触断言：%s=%s（须由主助理先核既有部署授权；不是授权来源）"
            % (AUTH_ENV, AUTH_VALUE))

    # 专用打包器的**写路径先决条件**在加载之前：缺完整摘要即 rc=2，此时零模块加载、
    # 零源收集、零产物、零平台／存储访问。只打包模式不强制（与旧调用一致）。
    expect_digest = cfg.get("--expect-zip-sha256")
    require_dedicated_digest(src_rel, deploy, expect_digest)
    pack, dedicated = load_packer(repo, src_rel)
    body_contract = load_module(os.path.join(repo, "tools", "body_contract.py"), "body_contract")

    with timer.phase(STAGE_PACK):
        entries = pack_collect(pack, src_abs, dedicated)
        blob = pack_build(pack, entries, dedicated)
        digest = hashlib.sha256(blob).hexdigest()

        # 保留纵深守卫的独立性：若上游校验被绕过，仍可自行解析并拒绝缺根文件。
        problems = None
        # 空包／包有效性：**唯一**拒绝点（空包在此拒绝，未通过即不上传）
        problems = package_problems(entries, name, blob, body_contract)
        if problems:
            raise Fail(STAGE_LOCAL, "包有效性未通过（不上传）：%s" % "／".join(problems))

        # 候选哈希门禁（可选）：给了完整预期 SHA-256 就要求**本次内存构包**与其逐位相等。
        # 位置在包有效性之后、写产物与 `--deploy` 分支之前：不一致时**任何远端写入都未开始**
        # （零 R2 读取／零上传／零 install／零 edit），也不留下候选包半成品；不给参数＝旧行为。
        # 只打包模式同样断言（本批口径：该参数是**包身份**约束，不是仅写路径约束）。
        if expect_digest is not None and expect_digest != digest:
            raise Fail(STAGE_LOCAL, "候选 ZIP sha256 与 --expect-zip-sha256 不一致（未上传／未安装）："
                                    "预期 %s｜实构 %s｜源 %s"
                        % (expect_digest, digest, src_rel))

        # 纵深守卫先校验候选 ZIP，清单核对仍在写出／上传前执行。
        zip_bytes = problems.zip_bytes if problems is not None else zip_member_bytes(blob, STAGE_LOCAL)
        if SKILL_FILE not in zip_bytes:
            raise Fail(STAGE_LOCAL, "候选 ZIP 内缺根 %s" % SKILL_FILE)

        # 清单核对＋取件门禁：门禁只在本目标就是 luno-surge 时生效（别处缺件不拦本次构包）。
        check_inventory(objects, repo, src_rel)

        candidate_path = os.path.join(out_abs, name + CANDIDATE_SUFFIX)
        write_atomic(candidate_path, blob, STAGE_PACK)

    log("模式：%s" % ("打包＋部署（--deploy）" if deploy else "仅打包（未上传／未安装）"))
    log("校验：repo=%s name=%s src=%s key=%s expect-id=%s" % (repo, name, src_rel, key, expect_id))
    log("权限：%d 项全部 0644（本批口径；0755 等属 P2b）" % len(entries))
    log("打包：files=%d bytes=%d sha256=%s" % (len(entries), len(blob), digest))
    log("资源完整清单：内置离线核对 rc=0（通过）")
    log("产物：%s（0644，原子写出，失败不覆盖已有产物）" % candidate_path)
    if deploy:
        try:
            run_deploy(cfg, entries, blob, digest, out_abs, pack, src_abs, body_contract, timer, zip_bytes)
        finally:
            release_cli_runner()        # 收尾（**含异常路径**）删除临时 HOME/XDG 目录
    else:
        log("写路径：未进入（加 --deploy 才允许上传／安装）")


def main(argv):
    try:
        cfg, bad = parse_args(argv)
        if bad is not None:
            raise Fail(STAGE_LOCAL, "参数无效：%s" % bad)
        run(cfg)
    except Fail as exc:
        sys.stderr.write("[deploy] 阶段失败：%s｜%s\n" % (exc.stage, exc.detail))
        return exc.rc
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

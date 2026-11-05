#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test-deploy-skill.py —— tools/deploy_skill.py 的离线回归（P2a 第 25 项）。

判据（每项都断言**可复核的退出码／字节事实**，不做源码计数对账）：
  1 接口与前置：缺 `--src` 直接 rc=2（**设了 DEPLOY_SRC 也不回退**、不猜源目录、不产生产物）；
    未知参数 rc=2；`--src` 与登记源路径不一致（`skills/guessed-skill` vs `skills/upstream/guessed-skill`）
    rc=2；`--repo` 缺登记、`--out-dir` 不存在或位于源内 rc=2；`--help` rc=0 且不导入 SDK。
  2 本地校验：有效源打包 rc=0、stdout 的 sha256 与产物实读 sha256 相等、产物 0644；
    空目录／空 SKILL.md／名字不符／符号链接／遍历失败／非常规权限（0755）／资源清单未通过
    一律 rc≠0 且**零上传**；0755 源的权限**未被压平**。
  3 资源完整清单：由部署工具内置函数核对审定仓库的包与登记（**真实实现**，
    不依赖外部审计入口）；清单失败即拒绝且零上传，合法空资源清单须与实际包一致。
  4 写路径门禁：无 `--deploy` 时**零上传零安装**（`lh` 桩零调用、SDK 零导入）；`--deploy`
    缺授权／缺 SDK 时 rc=2 且零上传；SDK 只在部署分支延迟加载（毒化 boto3 不影响打包模式）。
  5 部署判等（进程内假件）：正控 rc=0 且恰一次上传；官方 HTTP 写入非 200／下载不同／ID 改变／
    ZIP 哈希不同／正文不同（补齐失败）／资源路径集不同／任一资源字节不同 → 非零；
    正文被裁尾 LF 时经 `edit` 补齐后实读相等 → rc=0。
  6 回滚包：平台部署前 `zipFileHash` 非完整 64 位十六进制、或同 key 现存对象与其不符 → rc=2、
    **零上传**（回滚能力不成立即停止部署）。
  7 秘密面：合成标记放进 SDK／CLI 原始失败输出、预签名 URL、凭据环境变量后，标记**不得**出现在
    最终 stdout／stderr，也不得落在产物目录内的任何文件。
  8 空包反例＋变异：有效源绿 → **仅**把显式源换成空目录 → 红且零上传 → 恢复有效源 → 绿；
    删除空包拒绝条件（包有效性统一拒绝语句）后**不再报该分类**：实际是**错误分类变化**＋第二道
    守卫（候选 ZIP 根 `SKILL.md`）接手，仍 fail-closed、**零上传**（不是「会产生上传」），也不是
    缺 SDK／凭据的偶然失败。
  9 LENS 首审 F1：`skill view` 的 argv 精确断言（带字段白名单、含 `resources`、**不含**
    `source`／`manifest`）；本批起资源集经**同一次** view 取回，`skill resources` CLI **归零**
    （夹具已**不应答**该 verb ⇒ 一旦回归即 fail-closed）；SDK 静音边界——合成标记经 SDK
    stdout／stderr／logging 也**不得**外流，
    并以「撤掉静音边界」的变异体作反控（标记必须出现，证明断言非空转）。
 10 LENS 首审 F2：只有「恰少一个尾 LF」才允许走受支持的 `edit` 修补；同长度改字／多尾 LF／
    截断等一律**零 edit** 停止；`edit` 后必须**重取完整白名单对象**重核——hash／description／
    name 在 edit 后变化必须非零。
 11 LENS 首审 F3：上传前按 URL 型 `identifier` 解析出既有 bucket／key 并与本次 `R2_BUCKET`／
    `--key` 完全比对——**另一 key 下存在同字节 ZIP 也必须零上传**；非 URL 型（`user.…`）／
    桶名／账号／主机不符／带签名查询参数一律拒绝，且签名参数不外流。
 12 LENS 首审 F6：缺防误触断言时 `--out-dir` 文件集合与已有产物 bytes **均不变**（断言在任何
    写操作之前，含候选包）；无 `--deploy` 的打包正控仍成功。

 13 O5 资源回读走 HTTP：注入离线 HTTP 假件（`HttpStub`，不联网）后同域前置冻结通过 ⇒ 每个候选
    资源恰一次 HTTP 读取、逐资源 `read-resource` CLI **归零**、上传仍恰一次；空文件／二进制／
    CRLF／无尾 LF 形态一并覆盖。**同域前置＝硬门槛**（F2）：缺指定 key／key 含非法字符／origin
    不符／显式 workspace ⇒ 固定分类失败（rc=2）**停止本次部署**，零 HTTP／零 R2 读取／零上传／
    零 install／零 edit、无成功文案。CLI 逐资源回退分支已按 F2 删除（不再有用例固定该行为）。
 14 HTTP 侧固定分类失败：401／403、429、重定向、截断、坏编码、预算耗尽分别落到
    `authentication`／`rate-limit`／`http-status`／`truncated`／`encoding`／`budget` 固定分类且
    rc=1（写路径已开始）；「声明的 size／hash 正确而实际 bytes 不同」「与回放 bytes 自洽但异于
    候选」一律失败；缺／多资源、非法路径、未知嵌套字段、缺字段与 size／fileHash 不符一律在**发起
    任何资源 HTTP 之前**拒绝（形如带 URL 的未知字段既不进判等面、**也不外流**）。另以注入
    传输模块的变异（回放错字节 → 必红；回放正确字节 → 必绿）证明本入口自己的逐项 bytes 比较
    不是死代码。
 15 O3 未变对象只读分支：现场 `zipFileHash` 等于候选 ZIP sha256 时仍完成 id／来源身份／name／
    description／正文／资源路径集（取自**该次** view 的 `resources`）与全部资源 bytes 核验，输出固定
    文案「核验一致，未执行部署写入」
    且 rc=0，**零 R2 上传、零 R2 读取、零 install、零 edit**；正文（含「恰少一个尾 LF」形态）／
    描述／资源 bytes／资源路径集任一漂移或同名不同 ID 一律 fail-closed（rc=2，未进入写路径），
    **不得报跳过成功**。
 16 分阶段计时：部署流程输出「计时：序号｜阶段｜耗时｜rc｜资源=…」＋总计时，阶段覆盖打包／平台
    回读／源端复核／回滚包／上传／下载校验／安装／回读判等／资源回读／投后复核；计时行**不含** URL
    与完整 argv，SDK 合成标记也不得借计时外流；同域不成立时在平台／存储访问前停止，不进入资源
    回读阶段。
 17 判据 4 的口径更新（SDK 初始化推迟到确需存储写入的分支）：平台只读发生在 SDK 之前——缺 SDK
    时 `lh` 调用只有一次 `skill view`，rc=2 且零上传／零 install／零 edit；打包模式仍不加载资源
    传输模块、不查平台。

 18 复审 F1／F2（受控 CLI runner，**子进程级**真跑；桩 `lh` 记录调用面，不替换 `run_lh`）：
    `lh` 在**原环境**解析为绝对 argv（`shutil.which`＋realpath），CLI 子进程 env **只含**
    `PATH`／`HOME`／`XDG_CONFIG_HOME`／`XDG_DATA_HOME`／`XDG_CACHE_HOME`／
    `NODE_COMPILE_CACHE`／`LOBEHUB_SERVER`／`LOBEHUB_CLI_API_KEY`，`PATH` 为受批准最小目录集
    且不含 `shims`；**不继承** workspace／JWT／代理／PYTHONPATH；HOME/XDG 为**新建空目录**
    （列表恰 `cfg`／`cache`／`data`，不读 HOME 下持久化配置），收尾（含异常路径）删除；未设
    `LOBEHUB_SERVER` 时按受批准默认值**显式**注入；冻结后环境变化不改变已冻结的 argv／env；
    解析不到 `lh` 或同域不成立 ⇒ rc=2、**零 CLI 调用**、零 SDK（⇒ 零 R2）／零回滚包。
 18b 本批（CLI 启动开销）：`NODE_COMPILE_CACHE`＝**运行期私有**目录——位于本次运行临时根内、
    0700、首次调用时为空（未复用上一轮），与 HOME/XDG 同根同寿命；收尾随临时根删除并回读确认；
    非空转＝删掉该 env 注入行的变异体让同一组断言变红。该变量只影响 Node 自身编译缓存：不支持它的
    Node 忽略之，写不进缓存也不改变 CLI 的 rc／stdout（缓存失败不吞业务错误）。
 18c 本批（纯优化不得阻断）：缓存目录**建不出来**即**省略** `NODE_COMPILE_CACHE` 照常跑 CLI——
    进程内注入 `os.mkdir` 故障与真入口子进程（`sitecustomize` 注入）各一例证明：部署仍推进到
    stdout 可见的同一阶段（rc=2／一次 `skill view`）、CLI env 缺该项而其余白名单键不变、临时根
    照常回收、零 SDK（⇒ 零 R2）／零回滚包；HOME／XDG 的同类故障仍 fail-closed（上面的用例）。
 19 复审 F3（CLI 启动异常分档，进程内**真 `run_lh`** ＋ 桩 `subprocess.run`）：平台前置启动失败
    rc=2（零上传）；**安装后 view** 启动失败 rc=1（资源集随该次 view 回读）。
    原「资源清单（`skill resources`）启动失败」两例随该 CLI 取消**同批退休**，判据迁至 24。
退休说明：判据 20 随 `PhaseTimingSemantics` 退休，无迁移对象：假时钟计时口径属诊断契约，非写入安全。
 21 复审 F5（部署窗口源端复核）：打包后改源文件 ⇒ **上传前**命中固定分类失败（rc=2，零 R2 读取／
    零上传／零 install／零 edit、不写回滚包）；安装窗口内改源 ⇒ **投后**固定分类失败（rc=1，文案
    含「部署已写入完成，但源目录在部署窗口内发生变化，须人工确认是否重投」）；未变只读分支同样先过
    该门槛；源未变则两处均通过（正控）。复审 N2 订正：投后检查点位于**全资源回读之后、最终成功
    日志之前**，故「安装后第一次 view／edit／最后一个资源回读」三处窗口内改源同样 rc=1（三类负控）。

 25 本批（写入面迁移）：install／edit 改经官方 HTTP mutation（`agentSkills.importFromUrl`／
    `agentSkills.update`）——请求面逐项冻结、非 200／200 非 json／传输异常一律固定分类失败、
    200 只表请求已返回（成功以完整白名单 view 回读为准）、未变分支零 HTTP 写、正常路径（首读即
    通过）CLI 总调用数为 `view` ×2；同批**退休**「install 启动失败 rc=1」「edit 启动失败 rc=1
    且归到正文修补」两例（判据迁至 `HttpWritePath`，CLI 写入调用点已不存在，无空转留守）。
    （响应体读取与重试口径由 26 更新：原「不读响应体／一律不重试」已不再成立。）

 26 本批（写路径健壮性，2026-10-25 部署事故修复）：`WriteEnvelopeAndRepair` 固定四项改动的可判
    判据——① 响应体**有界读**（≤64 KB、分片 ≤8 KiB）后判 tRPC 信封：200 ＋ `error` ⇒ 失败（日志只
    带 status 与 code，message／data／body 不回显；install 与 edit 均不重试）、200 但非 `result` 形态
    ⇒ 失败；超界响应体读到上限＋1 即停，并以「上限放大到 1 MiB 后同一体被接受」作变异反控。
    ② `edit` 遇瞬时 5xx（503／502）⇒ 重试到成功（同一幂等载荷、`edit_payloads` 仅 1 次生效）；
    `install` 遇 5xx 仍恰一次请求。③ `edit` 遇 4xx ⇒ 不重试、一次即失败（无重试日志）。④ 补写后
    平台先读旧后读新 ⇒ 轮询到收敛即停（view 计数＝部署前 1＋安装后 1＋写前复核 1＋轮询 2，
    不读满等待表）。
    ⑤ 正文尾 LF 与 description 不符**合并成一次** update（载荷同时含 `content` 与
    `manifest{name,description}`）；字段单独不符时载荷**不带** `content`。⑥ `200 但不生效`（
    `ignore_edit`）⇒ 轮询用尽后 rc=1，detail 含轮询次数与末次字节数。重试／轮询时间表与 64 KB 上限
    另由常量判据固定。旧「`reads == 0` 不读响应体」判据随本批**退休**（由有界读判据取代）。

 23 复审 N1（runner 构造清理）：`CliRunner` 构造**中途**失败（HOME 创建／各 XDG 子目录创建／env
    构造）必须回收已建临时目录，且外层固定分类（`STAGE_PLATFORM`⇒rc=2）、文案不含原始异常；真入口
    子进程下同样零 CLI 调用／零 SDK（⇒ 零 R2）且 TMPDIR 内无 `deploy-lh-*` 残留。
 22 复审 S2（未变分支）：任一漂移同时断言零 R2 `get`／零上传／零 install／零 edit **且**不出现成功
    文案；HTTP runner 下的 bytes 漂移与路径集漂移各有反控（路径集不等时不发起任何资源 HTTP）。

 24 本批（资源集并入 view）：平台 `resources` 顶层字段（`Record<path,{size,fileHash}>`）的**形态门**
    ——`resources` **键必须存在**（缺键＝固定分类失败；由真实 `platform_entry` 归一化层拦下，**不得**
    被 `get` 投影抹成空集／`None`，与显式 `null`／`{}` 区分）、每个值的键集须恰为
    `{size,fileHash}`（未知嵌套字段／缺字段一律固定分类失败）、路径须为合法虚拟路径（复用**已加载**的
    `resource_http.valid_path`）、`size` 须为非负整数、`fileHash` 须为 64 位十六进制（`fullmatch`，
    尾随 LF 不放行）；空映射与 `null` 严格允许为**空集**——空候选亦须过同一门，非 Record 形态失败。
    上述任一失败都在**发起任何资源 HTTP 之前**停止，rc 随写路径进度（写路径内 rc=1、未变只读分支
    rc=2）；size／fileHash 与候选 ZIP 内 bytes 现算值逐项判等，**不以元数据判等代替逐字节 HTTP
    回读**；两分支都不得启动 `skill resources`。
 24b 修复 R1 的 F1／F2 边界（**用现有夹具＋`subTest`＋一张单元小表**，不新开 Harness 架构）：
    ——**F1（日志不回显外部键／路径／未知字段）**：失败文案只报固定分类、已知字段名（`RESOURCE_META_KEYS`
    派生）、类型名或数量；**路径集差异只报数量**（不再回显首个差异路径），非法路径／未知嵌套字段名／
    外部路径一律不输出（控制字符也无法注入日志）。反证把合成标记分别放进**合法但多出的路径**、
    **非法 URL 路径**、**未知字段名**，三者均断言非零 rc、stdout／stderr **零标记**、零资源 HTTP。
    ——**F2（缺字段）**：初始 view 缺 `resources` ⇒ rc=2 且零 R2 `get`／上传／install／edit、零资源
    HTTP；安装后 view 缺字段 ⇒ rc=1（写路径已开始）、零资源 HTTP；未变只读分支缺字段 ⇒ rc=2 零写且
    **不得**出现「核验一致，未执行部署写入」；**空候选**（源内无资源）在两分支上同样拒缺字段。
    ——单元小表直接调 `platform_resource_map(entry, stage, valid_path)`（消费**真实**校验器）：缺键／
    未知嵌套字段／缺嵌套字段／项非对象／非法路径／控制字符路径／非 Record／负 size／bool／非 int／
    非 str fileHash／尾随 LF 各一类，另含合法映射与 `{}`／`null` 正控。
    ——**F4**：随 `skill resources` CLI 退休后失去唯一调用点的 `CliStartupFailures.readonly_harness`
    同批**删除**（孤儿夹具，无断言被删）；写路径内等价调用点保留在「安装后 view 启动失败 rc=1」。

 25 第二轮差分复审（N1／F2）负控：写前那次回读同样判 id／zipFileHash——安装后基线读之后注入
    hash 变化 ⇒ rc=1、**零 edit**（不得先发 update 再由轮询发现异常）；**全部**回读路径都带剩余
    预算（≤10 s）：安装后回读 12 s ⇒ rc=1、写前复核 12 s ⇒ rc=1 且零 edit、部署前 `view` 12 s
    ⇒ rc=2（写路径前，rc 分类不变、零上传零写入）；另以修补路径正控固定「每次回读的预算都非
    `None` 且 0＜b≤10 s」。

成本例外（>10 s 用例，按 `skills/luno-sync/references/test-authoring.md` 的报账口径报账）：
  本入口保留 subprocess／进程内两层与 inventory 子进程边界回归（F1 用真解析及
  `CliProcessStub` 下的 `subprocess.run`，不替换 `run_lh`），因此有重量必要性。历史 Minis/iSH
  `case test-deploy-skill.py` 实测 44–47 s，发布者已接受当时增量；2026-11-01 本机 select 中该入口
  实测 34 s。当前该入口在 `full` 中（`tests/run-tests.sh` 第 5 列为 1）。若成为日常门禁瓶颈，
  降级为按命中路径定向运行须由当批发布者裁定；等待表置零，不引入真实等待。

 27 本批（上传前候选哈希门禁，`CandidateDigestGate`）：`--expect-zip-sha256` 给出时要求**本次
    内存构包**的 sha256 与其逐位相等——匹配照旧部署（上传／install／回读判等与旧调用逐项等同，
    并断言日志 `sha256=` 即该哈希）；不一致 rc=2 且**零 R2 读取／零上传／零 install／零 edit**、
    不写候选包与回滚包；格式不合格（63 位／64 位、大写、`sha256:` 前缀、65 位、非十六进制、
    前导空格）与缺值 rc=2 且不回显该值；**旧调用（不给该参数）行为不变**；只打包模式同样生效
    （不一致即不写出产物、零平台调用）；部署窗口内改源后实构哈希变化 ⇒ 在**写路径前**被该门禁
    拦下（而非投后复核）。

全部离线：不联网、不调真 `lh`／`minis-config`、不读真凭据、不写仓库内文件；夹具随用例清理。
"""
import ast
import base64
import contextlib
from functools import lru_cache
import hashlib
import http.client
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "deploy_skill.py"

#: 合成秘密标记：只出现在夹具的「原始失败输出／预签名 URL／凭据值」里，绝不允许外流
SECRET_MARKER = "SYNTHETIC-SECRET-9f3c1a7d"

SKILL_BODY = "---\nname: %s\ndescription: 夹具技能描述\n---\n\n# %s\n\n夹具正文。\n"
RESOURCE_REL = "references/fixture.md"
RESOURCE_BYTES = "夹具资源正文\n".encode("utf-8")
#: 子进程形态下的写入假路由参数（值非秘密：只是状态码／响应头；实现侧只按名取用）
HTTP_WRITES_ENV = "LUNO_DEPLOY_HTTP_WRITES"

#: F1／F2 的**冻结合成 key**：同一 `(origin, key)` 同时供 CLI runner 与 HTTP —— 即「同域」的构造
FROZEN_KEY = "synthetic-offline"


POISON_BOTO3 = '''"""夹具：毒化 boto3 —— 导入即记录标记并抛 ImportError（模拟缺依赖；不联网）。"""
import os

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "boto3-imported.marker"), "a") as fh:
    fh.write("imported\\n")
raise ImportError("boto3 不可用（离线夹具）")
'''

LH_STUB = '''#!/bin/sh
# 夹具桩：只记录调用（证明「零上传／零安装」），不访问网络、不读凭据
printf '%%s\\n' "$*" >> "%s"
exit 0
'''


def sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def write_file(path, text, mode=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        os.chmod(str(path), mode)


@lru_cache(maxsize=16)
def compile_source(source, filename):
    """只缓存完整源码＋路径的不可变 code；不缓存执行状态。"""
    return compile(ast.parse(source, filename=filename), filename, "exec")


def load_source_namespace(source):
    """复用编译结果，每次仍 exec 到全新命名空间。"""
    code = compile_source(source, str(TOOL))
    ns = {"__name__": "deploy_skill_under_test", "__file__": str(TOOL)}
    exec(code, ns)                       # noqa: S102 —— 受控加载，非不可信输入
    return ns


def load_tool_namespace():
    return load_source_namespace(TOOL.read_text(encoding="utf-8"))


def load_body_contract():
    """仓库真实正文契约实现（期望值当场算出，不硬编码任何来路不明的常量）。"""
    path = ROOT / "tools" / "body_contract.py"
    ns = {"__name__": "body_contract_fixture", "__file__": str(path)}
    exec(compile_source(path.read_text(encoding="utf-8"), str(path)), ns)
    return ns


def run_main(ns, argv):
    """进程内跑 main()，捕获 stdout／stderr。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = ns["main"](list(argv))
    return rc, out.getvalue(), err.getvalue()


class FakeS3Client(object):
    """假 SDK 客户端：记录 put／get；预签名 URL 带合成秘密标记；异常报文也带标记。

    `noisy=True` 时每次调用都向 stdout／stderr 打印并 `logging` 合成标记——用于验证
    「SDK 静音边界」确实把 SDK 自身的 stdout／stderr／logging 全部丢弃。
    """

    def __init__(self, pre_blob, fail=(), noisy=False):
        self.pre_blob = pre_blob
        self.fail = set(fail)
        self.noisy = noisy
        self.puts = []
        self.gets = []

    def _noise(self):
        if not self.noisy:
            return
        sys.stdout.write("%s（SDK stdout）\n" % SECRET_MARKER)
        sys.stderr.write("%s（SDK stderr）\n" % SECRET_MARKER)
        logging.getLogger("fixture.sdk").error("SDK logging %s", SECRET_MARKER)

    def get_object(self, Bucket=None, Key=None):
        self._noise()
        self.gets.append(Key)
        if "get" in self.fail:
            raise RuntimeError("get_object 原始报文 %s" % SECRET_MARKER)
        # 同 key 原位更新：键上的现存对象＝最近一次上传的字节，否则＝部署前对象
        blob = self.puts[-1][1] if self.puts else self.pre_blob
        return {"Body": io.BytesIO(blob)}

    def put_object(self, Bucket=None, Key=None, Body=None, ContentType=None):
        self._noise()
        if "put" in self.fail:
            raise RuntimeError("put_object 原始报文 %s" % SECRET_MARKER)
        self.puts.append((Key, Body))

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self._noise()
        if "url" in self.fail:
            raise RuntimeError("generate_presigned_url 原始报文 %s" % SECRET_MARKER)
        return "https://r2.example.invalid/%s?X-Amz-Signature=%s" % (Params["Key"], SECRET_MARKER)


class FakeResponse(object):
    def __init__(self, blob):
        self._blob = blob

    def read(self):
        return self._blob

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeUrlOpen(object):
    """假 urllib：返回「服务端回读」的字节（默认＝最近一次上传的字节）。"""

    def __init__(self, client, served=None, error=None):
        self.client = client
        self.served = served
        self.error = error
        self.urls = []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        if self.served is not None:
            return FakeResponse(self.served)
        return FakeResponse(self.client.puts[-1][1] if self.client.puts else b"")


class FakeUrlLib(object):
    def __init__(self, urlopen):
        self.request = type("Request", (), {"urlopen": staticmethod(urlopen)})()


#: 资源元数据旋钮的「未指定」哨兵：给出该值时按候选 bytes 现算（**不是** `None`）
AUTO_META = object()
#: `view` 字段「**缺失**」哨兵（F2）：给出该值时该键**不出现在**回读对象里——区别于显式 `null`
MISSING = object()


class FakePlatform(object):
    """假 lh：按命令回放可控 JSON／bytes；记录调用；stderr 可携带合成秘密标记。

    `skill resources` **不再应答**（该 CLI 已随资源集并入 `view` 而取消）：任何一次回归调用都会
    落到末尾的 `(2, b"", b"")` 默认分支，使被测入口 fail-closed 并由用例当场看见。
    """

    def __init__(self, client, name, expect_id, content, resources, resource_bytes,
                 pre_hash, install_status=200, edit_status=200, view_rc=0,
                 post_id=None, post_hash=None, post_content=None, post_resources=None,
                 pre_resources=None, resources_raw=AUTO_META, post_resources_raw=AUTO_META,
                 post_description=None, post_name=None,
                 identifier=None, account="fixture-account", bucket="fixture-bucket",
                 post_hash_after_edit=None, post_description_after_edit=None,
                 post_name_after_edit=None,
                 pre_description=None, pre_content=None, entry_id=None, on_call=None,
                 on_write=None, ignore_edit=False, stale_views=0, stale_content=None,
                 view_cost=0.0, advance=None):
        self.client = client
        self.name = name
        self.expect_id = expect_id
        self.content = content
        self.resources = list(resources)
        self.resource_bytes = dict(resource_bytes)
        self.pre_hash = pre_hash
        self.install_status = install_status
        self.edit_status = edit_status
        self.view_rc = view_rc
        self.pre_resources = pre_resources
        #: `view` 顶层 `resources` 的形态旋钮：`AUTO_META`＝按候选 bytes 现算（正控）；
        #: 显式给出即**原样**回放（含 `null`／空映射／非法路径／未知嵌套字段等负控形态）。
        self.resources_raw = resources_raw
        self.post_resources_raw = post_resources_raw
        self.post_id = post_id
        self.post_hash = post_hash
        self.post_content = post_content
        self.post_resources = post_resources
        self.post_description = post_description
        self.post_name = post_name
        # identifier 按**已实测的 URL 型形态**生成：url.<account>.r2.cloudflarestorage.com.<bucket>.<key>
        self.identifier = identifier if identifier is not None else (
            "url.%s.r2.cloudflarestorage.com.%s.%s.zip" % (account, bucket, name))
        self.post_hash_after_edit = post_hash_after_edit
        self.post_description_after_edit = post_description_after_edit
        self.post_name_after_edit = post_name_after_edit
        self.calls = []
        self.installed = False
        #: 官方 HTTP 写入记录（受控假路由 `WriteStub` 交给本对象的**同一** dict 引用）
        self.writes = []
        #: 意外退回 CLI 写入时的现场（夹具级不变量要求恒为空）
        self.cli_writes = []
        self.install_payloads = []
        self.edit_payloads = []
        #: `False` ＝ 写入返回 200 但**不生效**（用于「200 由完整回读拒绝」负控）
        self.apply_writes = True
        # 未变对象只读分支的现场字段（默认沿用既有「部署前描述／正文」形态）
        self.pre_description = pre_description
        self.pre_content = pre_content
        self.entry_id = entry_id
        #: 调用钩子（F5）：每次 CLI 调用**前**触发，供用例在「打包后／上传前／安装后」改源目录
        self.on_call = on_call
        #: 写入钩子（同 F5）：每次官方 HTTP 写入**登记后**触发（写窗口内改源用）
        self.on_write = on_write
        #: `True` ＝ update 返回 200 但**不生效**（补写后轮询超时的负控）
        self.ignore_edit = ignore_edit
        #: 安装后**先读陈旧**的次数：`stale_views>0` 时安装后的 view 依次回放 `stale_content`
        #: （模拟平台读后写延迟；用于「首读旧、次读新」的轮询收敛用例）
        self.stale_views = stale_views
        self.stale_content = stale_content
        #: 单次 `view` 的**假耗时**（秒）：非 0 时经 `advance` 推进假时钟，用于断言
        #: 「读取本身」也受剩余预算约束（复审 F2；不真睡、不改测试时长）。
        self.view_cost = view_cost
        self.advance = advance
        #: `view` **返回之后**的钩子：供 F4 用例模拟「基线已读到、第三方随即改动」的竞争窗口
        #: （`on_call` 在**读取之前**触发，会让第三值混进基线，不能用于该判据）
        self.on_view_served = None

    # ── 状态 ──
    def _installed_hash(self):
        return sha256_bytes(self.client.puts[-1][1]) if self.client.puts else self.pre_hash

    def _entry(self):
        if not self.installed:
            entry = {"id": self.entry_id or self.expect_id, "identifier": self.identifier,
                     "source": "fixture", "zipFileHash": self.pre_hash, "name": self.name,
                     "description": self.pre_description
                     if self.pre_description is not None else "部署前描述",
                     "content": self.pre_content
                     if self.pre_content is not None else "部署前正文\n",
                     "resources": self._resources_field()}
        else:
            entry = {"id": self.post_id or self.expect_id, "identifier": self.identifier,
                     "source": "fixture",
                     "zipFileHash": self.post_hash if self.post_hash is not None
                     else self._installed_hash(),
                     "name": self.post_name or self.name,
                     "description": self.post_description
                     if self.post_description is not None else "夹具技能描述",
                     "content": self.post_content if self.post_content is not None
                     else self.content,
                     "resources": self._resources_field()}
        if entry["resources"] is MISSING:
            del entry["resources"]      # F2：`resources` **键缺失**（≠ 显式 `null`／`{}`）
        if self.installed and self.stale_views > 0 and self.stale_content is not None:
            # 读后写延迟形态：前若干次安装后 view 仍回放陈旧正文（逐次递减，直到收敛）
            self.stale_views -= 1
            entry["content"] = self.stale_content
        return entry

    def _paths(self):
        return self.post_resources if self.post_resources is not None else self.resources

    def _bytes(self):
        return self.resource_bytes

    def _meta_paths(self):
        """该状态（部署前／安装后）下平台声明的资源路径集。"""
        if self.installed:
            return self._paths()
        return self.pre_resources if self.pre_resources is not None else list(self.resources)

    def _auto_meta(self):
        """按候选 bytes 现算 `Record<path,{size,fileHash}>`（正控形态）；池外路径按空 bytes 计。"""
        pool = self._bytes()
        out = {}
        for rel in self._meta_paths():
            blob = pool.get(rel, b"")
            out[rel] = {"size": len(blob), "fileHash": sha256_bytes(blob)}
        return out

    def _resources_field(self):
        """`view` 返回的顶层 `resources`：未显式注入时按候选 bytes 现算（等价于现场元数据）。"""
        raw = self.post_resources_raw if self.installed else self.resources_raw
        return self._auto_meta() if raw is AUTO_META else raw

    # ── 调用面 ──
    def __call__(self, args):
        self.calls.append(list(args))
        if self.on_call is not None:
            self.on_call(list(args))
        if len(args) < 2 or args[0] != "skill":
            return (2, b"", b"")
        verb = args[1]
        if verb == "view":
            if self.advance is not None and self.view_cost:
                # 读取**在途**消耗假时钟：模拟「单次读 12 s」，用于预算约束的负控。
                self.advance(self.view_cost)
            if self.view_rc != 0:
                return (self.view_rc, b"",
                        ("view 原始 stderr %s" % SECRET_MARKER).encode("utf-8"))
            entry = self._entry()
            if self.on_view_served is not None:
                # 「读取已返回、下一位写者尚未动手」的窗口：F4 用例在此注入第三值
                self.on_view_served(list(args))
            return (0, json.dumps({"data": entry}).encode("utf-8"), b"")
        if verb == "read-resource":
            rel = args[3] if len(args) > 3 else ""
            blob = self._bytes().get(rel)
            if blob is None:
                return (1, b"", b"")
            return (0, blob, b"")
        if verb in ("install", "edit"):
            # 本批起：写业务**只**经官方 HTTP（`write_skill_http`）。夹具在此登记并要求恒为空，
            # 且固定回 rc=1 —— 一旦有人把写入退回 CLI，用例立刻以 rc／零 HTTP 写入两条断言变红。
            self.cli_writes.append(list(args))
            return (1, b"", b"cli-write-must-not-happen (HTTP write only)")
        return (2, b"", b"")

    # ── 断言面 ──
    def uploads(self):
        return len(self.client.puts)

    def installed_calls(self):
        """**官方 HTTP** 安装请求（不再有 CLI 形态；语义与原「安装发生了几次」一致）。"""
        return [w for w in self.writes if w["kind"] == "install"]

    def edits(self):
        """**官方 HTTP** 正文补写请求（不再有 CLI 形态）。"""
        return [w for w in self.writes if w["kind"] == "edit"]

    @property
    def install_urls(self):
        """安装请求体里携带的 URL（预签名 URL 仍只在内存中传递）。"""
        return [json.loads(w["body"].decode("utf-8"))["json"]["url"]
                for w in self.installed_calls()]

    # ── 官方 HTTP 写入面（受控假路由 `WriteStub` 把请求交给这里）──
    def write_status(self, kind):
        return self.install_status if kind == "install" else self.edit_status

    def note_write(self, record):
        """登记一次写入请求（**同一** dict 引用：形态面与业务面共用一个真源）。"""
        self.writes.append(record)
        if self.on_write is not None:
            self.on_write(record)

    def apply_write(self, record):
        """把**成功**（200）的写入作用到平台状态；`apply_writes=False` 时不生效（负控）。

        载荷形态即官方 tRPC mutation 的 `{"json": …}`：install 取 `url`；edit 取 `id`／可选
        `content`／可选 `manifest{name,description}`（平台把三者当独立字段，故两条路径分别生效）。
        `ignore_edit=True` 模拟「200 但不生效」（补写后轮询超时的负控）。
        """
        if not self.apply_writes:
            return
        payload = json.loads(record["body"].decode("utf-8"))["json"]
        if record["kind"] == "install":
            self.installed = True
            self.install_payloads.append(payload)
            return
        self.edit_payloads.append(payload)
        if self.ignore_edit:
            return
        if "content" in payload:
            value = payload["content"]
            self.content = value
            self.post_content = value
        manifest = payload.get("manifest")
        if isinstance(manifest, dict):
            if "name" in manifest:
                self.post_name = manifest["name"]
            if "description" in manifest:
                self.post_description = manifest["description"]
        # 模拟「edit 之后对象其它字段变化」：验证修补后须**重取完整对象**重核
        if self.post_hash_after_edit is not None:
            self.post_hash = self.post_hash_after_edit
        if self.post_description_after_edit is not None:
            self.post_description = self.post_description_after_edit
        if self.post_name_after_edit is not None:
            self.post_name = self.post_name_after_edit


class DeployFixture(object):
    """隔离夹具：自足的「审定仓库」＋真实清单／桩 lh＋毒化 SDK＋受控授权环境。"""

    def __init__(self, root, name="fixture-skill", expect_id="skl_Fixture00001",
                 src_rel=None, create_source=True):
        self.root = Path(root)
        self.name = name
        self.expect_id = expect_id
        self.src_rel = src_rel or ("skills/%s" % name)
        self.repo = self.root / "repo"
        self.assets = self.root / "assets"
        self.bin = self.root / "bin"
        self.poison = self.root / "poison"
        for path in (self.repo / "tools", self.assets, self.bin, self.poison):
            path.mkdir(parents=True, exist_ok=True)
        # 审定仓库内的辅助模块用仓库**真实实现**（不是近似物）
        shutil.copyfile(ROOT / "tools/pack-skill-zip.py", self.repo / "tools/pack-skill-zip.py")
        shutil.copyfile(ROOT / "tools/body_contract.py", self.repo / "tools/body_contract.py")
        shutil.copyfile(ROOT / "tools/resource_http.py", self.repo / "tools/resource_http.py")
        install_synthetic_pin(self.repo / "tools/resource_http.py")
        write_file(self.bin / "lh", LH_STUB % (self.bin / "lh-calls.log"), mode=0o755)
        write_file(self.poison / "boto3.py", POISON_BOTO3)
        self.write_registry()
        (self.repo / self.src_rel).mkdir(parents=True, exist_ok=True)
        if create_source:
            self.write_skill()

    # ── 夹具面 ──
    def write_registry(self, source=None, platform_id=None):
        doc = {"schemaVersion": 1, "objects": [{
            "id": self.name, "type": "skill",
            "source": source if source is not None else "%s/SKILL.md" % self.src_rel,
            "resources": ["%s/%s" % (self.src_rel, RESOURCE_REL)],
            "ends": {"repo": {"present": True},
                     "lobehub": {"present": True, "kind": "skill",
                                 "id": platform_id or self.expect_id,
                                 "fields": "content,name,description"}}}]}
        write_file(self.repo / "tools/sync-targets.json", json.dumps(doc, ensure_ascii=False))

    def register_resources(self, resources):
        path = self.repo / "tools/sync-targets.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["objects"][0]["resources"] = [self.src_rel + "/" + p for p in resources]
        write_file(path, json.dumps(doc, ensure_ascii=False))

    def write_skill(self, name=None, body=None, resources=(RESOURCE_REL,)):
        name = name or self.name
        skill_dir = self.repo / self.src_rel
        write_file(skill_dir / "SKILL.md",
                   body if body is not None else SKILL_BODY % (name, name))
        for item in resources:
            write_file(skill_dir / item, RESOURCE_BYTES.decode("utf-8"))
        return skill_dir

    def write_resource(self, rel, blob):
        """按**原始 bytes** 写入一个资源（空文件／二进制／CRLF／无尾 LF 等形态用）。"""
        path = self.repo / self.src_rel / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        registry = json.loads((self.repo / "tools/sync-targets.json").read_text(encoding="utf-8"))
        listed = registry["objects"][0]["resources"]
        if self.src_rel + "/" + rel not in listed:
            self.register_resources([p[len(self.src_rel) + 1:] for p in listed] + [rel])
        return path

    def write_env_lh_stub(self, name=None, expect_id=None):
        """把桩 `lh` 换成**记录调用面**的 Python 桩（复审 F1／F2）；返回记录文件路径。"""
        log = self.root / "lh-env.log"
        write_file(self.bin / "lh",
                   LH_ENV_STUB % (sys.executable, str(log), name or self.name,
                                  expect_id or self.expect_id),
                   mode=0o755)
        return log

    def env_lh_records(self, log):
        """读回桩 `lh` 的记录（夹具自产，非不可信输入）。"""
        path = Path(log)
        if not path.exists():
            return []
        return [json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines() if line]

    def write_persisted_config(self):
        """在调用方 HOME 下放一份「别处身份」的持久化配置（复核 F1 的持久化 workspace 干扰项）。"""
        write_file(self.root / ".config/lobehub/cli.json",
                   json.dumps({"server": "https://untrusted.invalid",
                               "workspaceId": "ws-persisted"}, ensure_ascii=False))
        return self.root / ".config"

    def clear_skill(self):
        """把已登记的源目录清空（用于空包反例；登记与参数都不变）。"""
        skill_dir = self.repo / self.src_rel
        for path in sorted(skill_dir.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink()
            else:
                path.rmdir()
        self.references_dir_removed = True

    @property
    def skill_md(self):
        return self.repo / self.src_rel / "SKILL.md"

    def body_text(self):
        raw = self.skill_md.read_bytes()
        return load_body_contract()["body_bytes"](raw).decode("utf-8")

    def resource_map(self):
        root = self.repo / self.src_rel
        return dict((str(path.relative_to(root)), path.read_bytes())
                    for path in sorted(root.rglob("*"))
                    if path.is_file() and path.name != "SKILL.md")

    def args(self, src=None, out=None, deploy=False, **over):
        args = ["--repo", str(self.repo),
                "--src", self.src_rel if src is None else src,
                "--name", over.pop("name", self.name),
                "--key", over.pop("key", "%s.zip" % self.name),
                "--out-dir", str(self.assets if out is None else out),
                "--expect-id", over.pop("expect_id", self.expect_id)]
        for flag, value in over.items():
            args += ["--" + flag.replace("_", "-"), value]
        if deploy:
            args.append("--deploy")
        return args

    @property
    def cli_path(self):
        """进程内 harness 的受控 PATH：桩 `lh` 目录在前，其余用 `os.defpath`（不依赖宿主 PATH）。"""
        return os.pathsep.join([str(self.bin)] + [p for p in os.defpath.split(os.pathsep) if p])

    def env(self, extra=None, poison=True, lh_stub=True):
        env = {"HOME": str(self.root), "TMPDIR": str(self.root),
               "PATH": ("%s:" % self.bin if lh_stub else "") + "/usr/bin:/bin",
               "PYTHONPATH": str(self.poison) if poison else ""}
        env.update(extra or {})
        return env

    def run_tool(self, args, extra_env=None, poison=True, lh_stub=True, cwd=None,
                 http_writes=None):
        extra = dict(extra_env or {})
        if http_writes is not None:
            extra[HTTP_WRITES_ENV] = json.dumps({"json": http_writes})
        return subprocess.run([sys.executable, "-B", str(TOOL)] + list(args),
                              cwd=str(cwd or self.repo), env=self.env(extra, poison, lh_stub),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)

    # ── 断言面 ──
    def lh_calls(self):
        log = self.bin / "lh-calls.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def sdk_imported(self):
        return (self.poison / "boto3-imported.marker").exists()

    def candidate(self):
        return self.assets / ("%s.zip" % self.name)

    def rollback(self):
        return self.assets / ("%s.predeploy.zip" % self.name)

    def artifacts(self):
        return sorted(path.name for path in self.assets.iterdir())

    def out_dir_files(self):
        return dict((path.name, path.read_bytes()) for path in self.assets.iterdir())


def text_of(completed):
    """子进程输出解码（夹具自产，非不可信输入）。"""
    return (completed.stdout.decode("utf-8", "replace"),
            completed.stderr.decode("utf-8", "replace"))


# ── 离线 HTTP 假件（资源回读走 resource_http 的既有传输；不联网、不读真凭据）────────

class _StubResponse(object):
    """假 HTTP 响应：只实现既有传输会用的四个面（status／getheader／read1／close）。"""

    def __init__(self, stub, body):
        self.stub = stub
        self.body = body
        self.status = stub.status
        self.closed = False
        self._stream = io.BytesIO(body)

    def getheader(self, name):
        if self.stub.headers is not None:
            return self.stub.headers.get(name)
        if name == "Content-Length":
            return str(len(self.body))
        return None

    def read1(self, size):
        return self._stream.read(size)

    def close(self):
        self.closed = True


class _StubConnection(object):
    """假 HTTPS 连接：记录请求路径并按路径回放一封 readResource 信封。"""

    def __init__(self, stub):
        self.stub = stub
        self.sock = None
        self.timeout = None
        self.path = None

    def request(self, method, target, headers):
        from urllib.parse import unquote
        self.stub.methods.append(method)
        self.path = json.loads(unquote(target.split("?input=", 1)[1]))["json"]["path"]
        self.stub.requests.append(self.path)
        if self.stub.on_request is not None:
            self.stub.on_request(self.path)

    def getresponse(self):
        return _StubResponse(self.stub, self.stub.envelope(self.path))

    def close(self):
        self.stub.connections_closed += 1


# ── 官方 HTTP 写入假路由（本批：install／edit 改走官方 tRPC mutation）─────────────

class WriteLedger(object):
    """一次运行的连接账本：受批准 origin 的**写入**走 `stub`，**只读**走 `fallback`。"""

    def __init__(self, stub, fallback):
        self.stub = stub
        self.fallback = fallback
        self.host = stub.host


#: 实现写请求的**唯一**出口（`https_connection`）在测试中改由此变量指向的账本
#: （模块级、非全局 patch）：只有「写出请求」这一件事被替换，业务分支与错误分类仍走真实实现。
WRITE_PROBE = {"ledger": None}

#: 只读传输的 `https_connection`（同一模块内被写入 helper 复用）
REAL_HTTPS_CONNECTION = None


def _install_write_probe(ns):
    """安装探针：只把 `https_connection` 换成「按 host 派发到受控假路由」的实现。"""
    global REAL_HTTPS_CONNECTION
    REAL_HTTPS_CONNECTION = ns["https_connection"]

    def routed(host, timeout):
        ledger = WRITE_PROBE["ledger"]
        if ledger is not None and host == ledger.host:
            return ledger.stub.connect(host, timeout)
        if ledger is not None and ledger.fallback is not None:
            return ledger.fallback.connect(host, timeout)
        raise AssertionError("意外的 HTTP 连接目标：离线夹具只允许受批准 origin")

    ns["https_connection"] = routed


class _WriteResponse(object):
    """写入响应的最小面：状态行／响应头／**有界**正文；记录每次读体的字节数。

    `read1` 按 `size` 返回 `body` 的下一段（超出即空），故「有界读（≤64 KB、分片）」
    与「偷偷整包读／不读」都能由 `stub.reads`／`stub.bytes_read`／`stub.requested` 当场判定。
    """

    def __init__(self, stub, status, content_type, body=b""):
        self.stub = stub
        self.status = status
        self.content_type = content_type
        self.body = _json_bytes(body)
        self.closed = False
        self._stream = io.BytesIO(self.body)

    def getheader(self, name):
        lowered = (name or "").lower()
        if lowered == "content-type":
            return self.content_type
        if lowered == "content-length":
            return str(len(self.body))
        return None

    def read1(self, size):
        self.stub.reads += 1
        self.stub.requested.append(size)
        chunk = self._stream.read(size)
        self.stub.bytes_read += len(chunk)
        return chunk

    def close(self):
        self.closed = True


def _json_bytes(body):
    """响应体归一：dict／list 按 UTF-8 JSON 序列化，bytes 原样，`None`／空串为空体。"""
    if body is None:
        return b""
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


#: 写入**成功**信封（tRPC v10：`{"result":{"data":{"json":…}}}`；mutation 的 json 可为空对象）
OK_ENVELOPE = {"result": {"data": {"json": {}}}}


class _WriteConnection(object):
    """假 HTTPS 连接：只记录请求（method／target／headers／body）并回放路由决定的状态。"""

    def __init__(self, stub):
        self.stub = stub
        self.sock = None
        self.timeout = None
        self.method = None
        self.target = None
        self.headers = None
        self.body = None

    def request(self, method, target, body=None, headers=None):
        self.method = method
        self.target = target
        self.headers = dict(headers or {})
        self.body = body or b""
        self.stub.protocol.append({"event": "request", "method": method,
                                   "target": target.split("?", 1)[0]})

    def getresponse(self):
        kind = write_kind(self.target or "")
        record = {"kind": kind, "method": self.method,
                  "target": (self.target or "").split("?", 1)[0],
                  "headers": dict(self.headers or {}), "body": self.body}
        self.stub.requests.append(record)
        self.stub.platform.note_write(record)
        route = dict(self.stub.route(kind))
        if route.get("exception") is not None:
            raise route["exception"]
        status = route["status"]
        if status == 200 and kind is not None and "json" in route["content_type"].lower():
            # 与真实 mutation 一致：只有「200 ＋ json 信封」才可能生效；中介页（200 HTML）不生效
            self.stub.platform.apply_write(record)
        return _WriteResponse(self.stub, status, route["content_type"], route.get("body"))

    def close(self):
        self.stub.protocol.append({"event": "close"})


def write_kind(target):
    """按官方 procedure 路径判 kind（只认本批冻结的两个写入 procedure）。"""
    path = (target or "").split("?", 1)[0]
    if path.endswith("agentSkills.importFromUrl"):
        return "install"
    if path.endswith("agentSkills.update"):
        return "edit"
    return None


class WriteStub(object):
    """受控「官方 HTTP 写入」假路由：与业务面（`FakePlatform`）共用**同一**记录对象。

    `routes` 按 kind 覆盖状态码／响应头／传输异常／响应体（缺省取 `FakePlatform.write_status`，即
    `install_status`／`edit_status`，默认 200；缺省响应体为 `OK_ENVELOPE`）。**值可为 list**：按尝试
    次序逐项回放、末项在后续尝试上重复——用于「5xx→5xx→200」这类有界重试用例。未声明的 procedure
    回 404，用于「不泛化到其它 router 工具」的负控。
    """

    def __init__(self, platform, routes=None):
        self.platform = platform
        self.routes = dict(routes or {})
        self.requests = []          # 业务面：注入内容（**不落盘、不出对话**）
        self.protocol = []          # 协议面：method／关闭事件顺序
        self.connects = []          # 每次 connect 的 (host, timeout)
        self.reads = 0              # 读响应体的次数
        self.bytes_read = 0         # 读响应体的总字节数（有界判据）
        self.requested = []         # 每次 `read1` 请求的字节数（分片粒度判据）
        self.attempts = {}          # kind → 已用尝试次数（list 形态按序回放）

    @property
    def host(self):
        return urlsplit(HttpStub.ORIGIN).hostname

    def connect(self, host, timeout=None):
        self.connects.append((host, timeout))
        return _WriteConnection(self)

    def route(self, kind):
        if kind is None:
            return {"status": 404, "content_type": "text/html", "exception": None,
                    "body": OK_ENVELOPE}
        spec = self._step(kind, self.routes.get(kind))
        if spec is not None:
            return {"status": spec.get("status", 200),
                    "content_type": spec.get("content_type", "application/json"),
                    "exception": spec.get("exception"),
                    "body": spec.get("body", OK_ENVELOPE)}
        return {"status": self.platform.write_status(kind),
                "content_type": "application/json", "exception": None, "body": OK_ENVELOPE}

    def _step(self, kind, spec):
        """按尝试次序取本条路由：list ⇒ 取第 n 项（末项重复），否则原样返回。"""
        if not isinstance(spec, list):
            return spec
        index = min(self.attempts.get(kind, 0), len(spec) - 1)
        self.attempts[kind] = self.attempts.get(kind, 0) + 1
        return spec[index]

    def connections_closed(self):
        return len([e for e in self.protocol if e["event"] == "close"])


# ── 合成受批准 origin（夹具面）───────────────────────────────────────────────
# 真实 origin 的私有域名不进仓库（实现里只留 sha256）：夹具用 `.invalid` 合成值，并把**夹具仓库
# 副本**的 pin 换成它的摘要——只替换 pin、不复制 HTTP 实现，生产 pin 与校验逻辑原样。
SYNTH_ORIGIN = "https://deploy.invalid"
SYNTH_ORIGIN_SHA256 = hashlib.sha256(SYNTH_ORIGIN.encode("utf-8")).hexdigest()
SYNTH_WRITE_HOST = "write.invalid"
_ORIGIN_PIN_RE = re.compile(r"^APPROVED_ORIGIN_SHA256 = '[0-9a-f]{64}'$", re.M)


def install_synthetic_pin(path):
    """只把副本里的 origin pin 换成合成摘要（供同域前置在夹具内成立）。"""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    new_text, count = _ORIGIN_PIN_RE.subn(
        "APPROVED_ORIGIN_SHA256 = '%s'" % SYNTH_ORIGIN_SHA256, text)
    if count != 1:
        raise AssertionError("夹具副本须恰有一处 origin pin：%d" % count)
    path.write_text(new_text, encoding="utf-8")


class HttpStub(object):
    """离线 HTTP 假件：按请求路径回放 readResource 信封（不联网、不读凭据）。

    `serve` 覆盖回放的 bytes、`meta` 覆盖信封声明的 `(size, fileHash)`、`encoding` 覆盖编码形态、
    `override` 覆盖整封响应体——用于「声明的 size／hash 看着正确但实际 bytes 不同」等负控。
    """

    ORIGIN = SYNTH_ORIGIN

    def __init__(self, resources, status=200, headers=None, serve=None, meta=None,
                 encoding=None, override=None, on_request=None):
        self.resources = dict(resources)
        self.status = status
        self.headers = headers
        self.serve = dict(serve or {})
        self.meta = dict(meta or {})
        self.encoding = dict(encoding or {})
        self.override = dict(override or {})
        #: 请求钩子（N2 ③）：每个资源请求**登记后**触发，供用例在「最后一个资源回读时」改源目录
        self.on_request = on_request
        self.requests = []
        self.methods = []
        self.connections_closed = 0

    def connect(self, host, timeout=None):
        return _StubConnection(self)

    def envelope(self, path):
        if path in self.override:
            return self.override[path]
        data = self.serve.get(path, self.resources.get(path, b""))
        encoding = self.encoding.get(path, "utf8")
        size, digest = self.meta.get(path, (len(data), sha256_bytes(data)))
        content = (data.decode("utf-8") if encoding == "utf8"
                   else base64.b64encode(data).decode("ascii"))
        payload = {"path": path, "size": size, "fileHash": digest, "fileType": "text/plain",
                   "encoding": encoding, "content": content}
        return json.dumps({"result": {"data": {"json": payload}}},
                          ensure_ascii=True).encode("utf-8")


def pack_candidate(fixture):
    """先跑一次默认打包模式，取出**确定性候选 ZIP bytes**（供未变分支的现场哈希使用）。"""
    cp = fixture.run_tool(fixture.args())
    out, err = text_of(cp)
    if cp.returncode != 0:
        raise AssertionError("夹具前置打包失败：%s" % (out + err))
    return fixture.candidate().read_bytes()


class Harness(object):
    """进程内假件：替换 SDK 客户端、`lh`、`urllib`、环境变量（不联网、不读真凭据）。"""

    DEFAULT_ENV = {"LUNO_DEPLOY_AUTHORIZED": "1", "CF_ACCOUNT_ID": "fixture-account",
                   "R2_ACCESS_KEY_ID": "fixture-key-id", "R2_BUCKET": "fixture-bucket",
                   "R2_SECRET_ACCESS_KEY": "fixture-secret-%s" % SECRET_MARKER}
    #: 冻结同一 `(origin, key)` 的受控环境（F1／F2：同域是**硬门槛**，不再是可降级前提）
    FROZEN_ENV = {"LOBEHUB_SERVER": HttpStub.ORIGIN, "LOBEHUB_CLI_API_KEY": FROZEN_KEY}

    def __init__(self, fixture, source=None, env="default", patch_storage=True, patch_lh=True,
                 pre_blob=None, served=None, urlopen_error=None, sdk_fail=False,
                 platform_kwargs=None, fail_client=(), content=None, resources=None,
                 noisy=False, http=None, http_env=None, transport=None, http_writes=None):
        self.fixture = fixture
        self.source = source if source is not None else TOOL.read_text(encoding="utf-8")
        self.ns = load_source_namespace(self.source)
        self.env = dict(self.DEFAULT_ENV) if env == "default" else dict(env)
        # 受控 CLI runner 的解析读 `PATH`：夹具给一个**离线、确定**的 PATH（桩 `lh` 目录在前），
        # 使进程内用例不依赖宿主 PATH 上是否装着真的 `lh`。
        self.env.setdefault("PATH", fixture.cli_path)
        self.http_writes = dict(http_writes or {})
        #: 受控 env 的**真源**（进程内用例的 `env_get` 一律读它，不读宿主环境）
        self._base_env_get = lambda name, default=None: self.env.get(name, default)

        def env_get(name, default=None):
            # 受控 env 单点缝透传**夹具自产**的写入假路由参数（非秘密、不联网）
            if name == HTTP_WRITES_ENV:
                return (json.dumps({"json": self.http_writes})
                        if self.http_writes else None)
            return self._base_env_get(name, default)

        self.ns["env_get"] = env_get
        self.pre_blob = pre_blob if pre_blob is not None else b"deployment-before-blob"
        self.client = FakeS3Client(self.pre_blob, fail=fail_client, noisy=noisy)
        self.urlopen = FakeUrlOpen(self.client, served=served, error=urlopen_error)
        self.ns["urllib"] = FakeUrlLib(self.urlopen)
        # 候选包的期望内容／资源：可在源仍有效时先取好，供「源已被清空」的反例复用
        self.content = content if content is not None else fixture.body_text()
        self.resource_map = resources if resources is not None else fixture.resource_map()
        kwargs = {"pre_hash": sha256_bytes(self.pre_blob)}
        kwargs.update(platform_kwargs or {})
        self.platform = FakePlatform(self.client, fixture.name, fixture.expect_id,
                                     self.content, sorted(self.resource_map),
                                     self.resource_map, **kwargs)
        # 写入假路由：与业务面共用同一 `FakePlatform`（真实 tRPC 载荷形态只在 apply_write 里解析）
        self.write_stub = WriteStub(self.platform, routes=self.http_writes)
        _install_write_probe(self.ns)
        if patch_lh:
            # `run_lh(args, stage=…, timeout=…)`：假 CLI 收到 args（阶段归类由**真实** run_lh 承担）；
            # `timeout`＝调用方带的**剩余预算**，如实记账供「读取受预算约束」的用例断言（复审 F2）。
            self.read_budgets = []

            def fake_run(args, stage=None, timeout=None):
                self.read_budgets.append(timeout)
                return self.platform(args)

            self.ns["run_lh"] = fake_run
        if sdk_fail:
            def boom(name):
                raise ImportError("毒化夹具：%s 不可用" % name)
            self.ns["import_module"] = boom
        if patch_storage:
            self.ns["open_storage"] = lambda: self.ns["Storage"](self.client, "fixture-bucket")
        # 同域前置默认**成立**（受批准 origin ＋合成 key，与真实 `resource_http` 的批准值一致）；
        # 用例显式给 `http_env={}` 等即构造「同域不可证明」——按 F2 必须**停止本次部署**（零上传）。
        self.http = http
        self.http_env = dict(self.FROZEN_ENV if http_env is None else http_env)
        # 部署分支的资源 bytes 回读**恒经 HTTP**（CLI 回退按 F2 取消）：未显式注入 HTTP 假件时，
        # 默认注入**离线传输假件**（回放夹具资源集）——不联网、也不需要真实同域。
        if transport is None and http is None:
            transport = StubTransport(fixture.resource_map())
        self.transport = transport
        self.loaded = []
        real_load = self.ns["load_module"]

        def record_load(path, modname):
            self.loaded.append(modname)
            if self.transport is not None and modname == "resource_http":
                # 形态门消费**真实**校验器：把已加载模块的 `valid_path` 挂到桩传输上（不抄一份）
                self.transport.valid_path = real_load(path, modname).valid_path
                return self.transport
            return real_load(path, modname)

        self.ns["load_module"] = record_load

    def run(self, argv):
        env = dict(self.http_env)
        try:
            env[HTTP_WRITES_ENV] = json.dumps({"json": self.http_writes})
        except TypeError:
            # 进程内用例的写入假路由参数直接取自夹具（可含异常对象），不经 env 序列化
            pass
        WRITE_PROBE["ledger"] = WriteLedger(self.write_stub, self.http)
        try:
            with mock.patch.dict(os.environ, env, clear=True):
                if self.http is None:
                    return run_main(self.ns, argv)
                # 只读资源传输仍经**注入的** HTTP 假件（真实 `resource_http` 被装载时用它）；
                # 写入请求已在 `https_connection` 单点缝上改派给受控写入假路由。
                with mock.patch.object(http.client, "HTTPSConnection", self.http.connect):
                    return run_main(self.ns, argv)
        finally:
            WRITE_PROBE["ledger"] = None


class FixtureCase(unittest.TestCase):
    """每个用例一个唯一临时目录，随用例清理。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="test-deploy-")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def fixture(self, **kwargs):
        return DeployFixture(Path(tempfile.mkdtemp(prefix="fixture-", dir=self.work)), **kwargs)

    def fast(self, name, **kwargs):
        """夹具＋进程内 harness；重试／轮询等待表置零（行为判据不依赖真实等待）。"""
        fixture = self.fixture(name=name)
        harness = Harness(fixture, **kwargs)
        harness.ns["WRITE_RETRY_DELAYS"] = (0.0, 0.0)
        harness.ns["REPAIR_POLL_DELAYS"] = (0.0,) * 5
        return fixture, harness


class CliInterface(FixtureCase):
    """判据 1：参数与前置拒绝（rc=2、零上传、不产生产物）。"""

    def test_missing_src_is_rc2_without_env_fallback(self):
        fixture = self.fixture()
        args = fixture.args()
        args.remove("--src")
        args.remove(fixture.src_rel)
        cp = fixture.run_tool(args, extra_env={"DEPLOY_SRC": str(fixture.repo / fixture.src_rel)})
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("[deploy] 阶段失败：本地校验", err)
        self.assertIn("缺少必填参数 --src", err)
        self.assertIn("不按名称猜源目录", err)
        self.assertEqual(fixture.artifacts(), [])
        self.assertEqual(fixture.lh_calls(), [])
        self.assertFalse(fixture.sdk_imported(), "打包模式不得导入 SDK")

    def test_unknown_argument_is_rc2(self):
        fixture = self.fixture()
        cp = fixture.run_tool(fixture.args() + ["--frobnicate"])
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("未知参数 --frobnicate", err)
        self.assertEqual(fixture.artifacts(), [])

    def test_help_is_rc0_without_side_effects(self):
        fixture = self.fixture()
        cp = fixture.run_tool(["--help"])
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 0, out + err)
        self.assertIn("--src", out)
        self.assertIn("默认只打包", out)
        self.assertEqual(fixture.artifacts(), [])
        self.assertEqual(fixture.lh_calls(), [])
        self.assertFalse(fixture.sdk_imported(), "--help 不得加载 SDK")

    def test_guessed_source_path_is_rejected(self):
        """登记源在 `skills/upstream/<name>`；参数写 `skills/<name>` 必须拒绝，不得推断。"""
        fixture = self.fixture(name="guessed-skill", src_rel="skills/upstream/guessed-skill")
        cp = fixture.run_tool(fixture.args(src="skills/guessed-skill"))
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("与登记源路径不一致", err)
        self.assertIn("skills/upstream/guessed-skill", err)
        self.assertEqual(fixture.artifacts(), [])
        self.assertEqual(fixture.lh_calls(), [])

    def test_repo_without_registry_is_rejected(self):
        fixture = self.fixture()
        (fixture.repo / "tools/sync-targets.json").unlink()
        cp = fixture.run_tool(fixture.args())
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("缺登记真源", err)
        self.assertEqual(fixture.artifacts(), [])

    def test_out_dir_missing_and_inside_source_are_rejected(self):
        fixture = self.fixture()
        missing = self.work / "nope"
        cp = fixture.run_tool(fixture.args(out=str(missing)))
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("--out-dir 不是已存在目录", err)
        inside = fixture.repo / fixture.src_rel / "assets"
        inside.mkdir(parents=True)
        cp = fixture.run_tool(fixture.args(out=str(inside)))
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("--out-dir 位于 --src 之内", err)
        self.assertEqual(fixture.artifacts(), [])


class LocalValidation(FixtureCase):
    """判据 2／3：包有效性与资源清单门禁（rc≠0、零上传、不产生产物）。"""

    def assert_rejected(self, fixture, needle, args=None, rc=2):
        cp = fixture.run_tool(args if args is not None else fixture.args())
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, rc, out + err)
        self.assertIn(needle, err)
        self.assertEqual(fixture.artifacts(), [], "失败不得产出包")
        self.assertEqual(fixture.lh_calls(), [], "失败不得触碰 lh（零上传／零安装）")
        return out, err

    def test_valid_source_packs_with_expected_digest_and_mode(self):
        fixture = self.fixture()
        cp = fixture.run_tool(fixture.args())
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 0, out + err)
        self.assertIn("写路径：未进入", out)
        self.assertIn("资源完整清单：内置离线核对 rc=0（通过）", out)
        self.assertIn("权限：2 项全部 0644", out)
        digest = None
        for line in out.splitlines():
            if line.startswith("[deploy] 打包："):
                digest = line.rsplit("sha256=", 1)[1].strip()
        self.assertIsNotNone(digest, out)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        blob = fixture.candidate().read_bytes()
        self.assertEqual(sha256_bytes(blob), digest, "stdout 的 sha256 必须等于产物实读")
        self.assertEqual(os.stat(str(fixture.candidate())).st_mode & 0o7777, 0o644)
        self.assertEqual(fixture.lh_calls(), [], "无 --deploy 时零上传零安装")
        self.assertFalse(fixture.sdk_imported(), "无 --deploy 时不得导入 SDK")

    def test_empty_directory_is_rejected(self):
        fixture = self.fixture(name="empty-skill", create_source=False)
        self.assert_rejected(fixture, "包有效性未通过（不上传）：空包（源内无文件")

    def test_empty_skill_md_is_rejected(self):
        fixture = self.fixture(name="blank-skill", create_source=False)
        fixture.write_skill(body="")
        self.assert_rejected(fixture, "正文为空")

    def test_frontmatter_name_mismatch_is_rejected(self):
        fixture = self.fixture(name="mismatch-skill", create_source=False)
        fixture.write_skill(body=SKILL_BODY % ("other-name", "other-name"))
        self.assert_rejected(fixture, "frontmatter name 与 --name 不等")

    def test_symlink_in_source_is_rejected(self):
        fixture = self.fixture(name="link-skill")
        os.symlink(str(fixture.skill_md), str(fixture.repo / fixture.src_rel / "linked.md"))
        self.assert_rejected(fixture, "源收集失败")

    def test_walk_error_is_rejected(self):
        """进程内把 pack 的 collect() 换成抛 OSError 的实现：必须 rc=2 且不产生产物。"""
        fixture = self.fixture(name="walk-skill")
        ns = load_tool_namespace()
        real_load = ns["load_module"]

        class FakePack(object):
            @staticmethod
            def collect(root):
                raise OSError("夹具遍历错误")

            @staticmethod
            def build(entries):
                return b""

        def fake_load(path, modname):
            return FakePack if modname == "pack_skill_zip" else real_load(path, modname)

        ns["load_module"] = fake_load
        rc, out, err = run_main(ns, fixture.args())
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：打包", err)
        self.assertIn("源收集失败", err)
        self.assertEqual(fixture.artifacts(), [])

    def test_nonstandard_permissions_are_rejected_and_not_flattened(self):
        fixture = self.fixture(name="perm-skill")
        script = fixture.repo / fixture.src_rel / "scripts" / "run.sh"
        write_file(script, "#!/bin/sh\nexit 0\n", mode=0o755)
        out, err = self.assert_rejected(fixture, "非常规权限 0755")
        self.assertIn("P2b", err)
        self.assertIn("scripts/run.sh", err)
        self.assertEqual(os.stat(str(script)).st_mode & 0o7777, 0o755,
                         "本批不得悄悄压平源权限")

    def test_inventory_failure_is_rejected(self):
        fixture = self.fixture(name="inventory-skill")
        fixture.register_resources([RESOURCE_REL, "references/ghost.md"])
        self.assert_rejected(fixture, "资源完整清单未通过：内置离线核对 rc=1")

    def test_missing_resource_is_rejected_by_inline_inventory(self):
        """缺资源由真实内置清单拒绝；恢复实际文件才可通过，不再用 rc 桩伪造完整。"""
        fixture = self.fixture(name="missing-resource-skill")
        (fixture.repo / fixture.src_rel / RESOURCE_REL).unlink()
        self.assert_rejected(fixture, "资源完整清单未通过")
        fixture.write_resource(RESOURCE_REL, RESOURCE_BYTES)
        cp = fixture.run_tool(fixture.args())
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 0, out + err)
        self.assertIn("资源完整清单：内置离线核对 rc=0（通过）", out)


#: 变异用的源码片段（删除即「空包拒绝条件」失效；先断言片段确实存在，再替换）
EMPTY_PACKAGE_GUARD = (
    '        problems = package_problems(entries, name, blob, body_contract)\n'
    '        if problems:\n'
    '            raise Fail(STAGE_LOCAL, "包有效性未通过（不上传）：%s" % "／".join(problems))\n')
EMPTY_PACKAGE_CLAUSE = (
    '    if not entries:\n'
    '        return ["空包（源内无文件；本入口不打包空 ZIP）"]\n')

#: SDK 静音边界的变异锚点：删掉即「SDK stdout／stderr／logging 静音」失效（用于反控）
SILENCE_ANCHOR = (
    '    sys.stdout = sink\n'
    '    sys.stderr = sink\n'
    '    logging.disable(logging.CRITICAL + 10)\n')
SILENCE_MUTATION = '    pass  # 变异：撤掉 SDK stdout／stderr／logging 静音\n'


class SdkAndAuthorization(FixtureCase):
    """判据 4：SDK 延迟加载、授权与凭据缺口的失败面（rc=2、零上传）。"""

    def test_deploy_branch_defers_sdk_until_storage_write(self):
        """SDK 初始化推迟到**确需存储写入**的分支：平台只读先发生；缺 SDK 仍 rc=2 且零写入。"""
        fixture = self.fixture(name="sdk-skill")
        harness = Harness(fixture, sdk_fail=True, patch_storage=False)
        imported = []
        boom = harness.ns["import_module"]

        def record(name):
            imported.append(name)
            return boom(name)

        harness.ns["import_module"] = record
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertEqual(imported, ["boto3"], "只有部署分支才延迟加载 SDK")
        self.assertIn("阶段失败：SDK", err)
        self.assertIn("缺少 SDK（boto3／botocore，ImportError）", err)
        self.assertIn("不自动安装", err)
        # 「推迟」的正面证据：SDK 之前只发生了平台**只读**（零存储访问）
        self.assertEqual([call[:2] for call in harness.platform.calls], [["skill", "view"]],
                         "SDK 初始化之前只应有平台只读")
        self.assertEqual(harness.platform.uploads(), 0, "缺 SDK 时零上传")
        self.assertEqual(harness.platform.installed_calls(), [], "缺 SDK 时零 install")
        self.assertEqual(harness.platform.edits(), [], "缺 SDK 时零 edit")
        self.assertTrue(fixture.candidate().exists(), "包是本地产物，在进入写路径前已写出")

    def test_deploy_without_authorization_touches_nothing(self):
        fixture = self.fixture(name="auth-skill")
        existing = fixture.assets / "existing-artifact.zip"
        existing.write_bytes(b"PREVIOUS-ARTIFACT-BYTES")
        before = fixture.out_dir_files()
        cp = fixture.run_tool(fixture.args(deploy=True))
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("阶段失败：授权", err)
        self.assertIn("LUNO_DEPLOY_AUTHORIZED=1", err)
        self.assertIn("防误触断言", err)
        self.assertEqual(fixture.lh_calls(), [])
        self.assertFalse(fixture.sdk_imported(), "缺授权时连 SDK 都不加载")
        # F6：断言在任何写操作之前 ⇒ --out-dir 文件集合与已有产物 bytes 均不变
        self.assertEqual(fixture.out_dir_files(), before)
        self.assertEqual(existing.read_bytes(), b"PREVIOUS-ARTIFACT-BYTES")
        self.assertFalse(fixture.candidate().exists(), "缺断言时不得写出候选包")

    def test_missing_sdk_in_deploy_branch(self):
        fixture = self.fixture(name="sdk-inproc-skill")
        harness = Harness(fixture, sdk_fail=True, patch_storage=False)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：SDK", err)
        self.assertIn("缺少 SDK", err)
        self.assertEqual(harness.platform.uploads(), 0)
        self.assertEqual(harness.platform.installed_calls(), [])
        self.assertEqual(harness.platform.edits(), [])

    def test_missing_credentials_report_names_only(self):
        fixture = self.fixture(name="cred-skill")
        harness = Harness(fixture, env={"LUNO_DEPLOY_AUTHORIZED": "1",
                                        "CF_ACCOUNT_ID": "fixture-account",
                                        "R2_BUCKET": "fixture-bucket",
                                        "R2_SECRET_ACCESS_KEY": SECRET_MARKER},
                          patch_storage=False)
        fake_boto3 = type("FakeBoto3", (), {"client": staticmethod(lambda *a, **k: None)})()
        fake_config = type("FakeConfig", (), {"Config": staticmethod(lambda *a, **k: None)})()
        harness.ns["import_module"] = lambda name: (fake_boto3 if name == "boto3" else fake_config)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：SDK", err)
        self.assertIn("缺少存储凭据环境变量", err)
        self.assertIn("R2_ACCESS_KEY_ID", err)
        self.assertNotIn("CF_ACCOUNT_ID", err, "只报**缺**的变量名")
        self.assertNotIn("R2_BUCKET", err, "只报**缺**的变量名")
        self.assertNotIn(SECRET_MARKER, out + err, "缺凭据只报变量名，不展示值")

    def test_missing_authorization_in_process(self):
        fixture = self.fixture(name="auth-inproc-skill")
        harness = Harness(fixture, env={})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：授权", err)
        self.assertEqual(harness.platform.calls, [])
        self.assertEqual(harness.platform.uploads(), 0)


class SecretFace(FixtureCase):
    """判据 7：合成秘密标记不得出现在最终输出或产物里。"""

    def test_marker_never_reaches_output_or_artifacts(self):
        fixture = self.fixture(name="secret-skill")
        cases = (
            ("happy", {}, 0),
            ("install_http_error", {"platform_kwargs": {"install_status": 401}}, 1),
            ("download_error", {"urlopen_error": RuntimeError("原始报文 %s" % SECRET_MARKER)}, 1),
            ("get_error", {"fail_client": ("get",)}, 2),
            ("put_error", {"fail_client": ("put",)}, 1),
            ("url_error", {"fail_client": ("url",)}, 1),
            ("view_error", {"platform_kwargs": {"view_rc": 1}}, 2),
        )
        for label, kwargs, expect_rc in cases:
            with self.subTest(case=label):
                harness = Harness(fixture, **kwargs)
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, expect_rc, "%s: %s" % (label, out + err))
                self.assertNotIn(SECRET_MARKER, out + err, label)
                for name, blob in fixture.out_dir_files().items():
                    self.assertNotIn(SECRET_MARKER.encode(), blob, "%s：产物 %s" % (label, name))

    def test_presigned_url_flows_but_is_never_logged(self):
        fixture = self.fixture(name="url-skill")
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertTrue(harness.urlopen.urls, "必须经预签名 GET 回读")
        url = harness.urlopen.urls[0]
        self.assertIn(SECRET_MARKER, url, "夹具的预签名 URL 确实带合成标记（断言非空转）")
        self.assertEqual(harness.platform.install_urls[0], url, "install 用的就是该 URL")
        self.assertNotIn(SECRET_MARKER, out + err)
        self.assertNotIn(url, out + err, "预签名 URL 不得进日志／报告")


class DeployFlow(FixtureCase):
    """判据 5／6：部署判等与回滚能力（进程内假件，不联网）。"""

    def harness(self, name="deploy-skill", **kwargs):
        fixture = self.fixture(name=name)
        return fixture, Harness(fixture, **kwargs)

    def test_happy_path_uploads_once_and_verifies_everything(self):
        fixture, harness = self.harness(name="happy-skill")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(harness.platform.uploads(), 1, "恰一次上传")
        self.assertEqual(len(harness.platform.installed_calls()), 1, "恰一次 install")
        self.assertEqual(harness.platform.edits(), [], "正文本来就相等，不需要 edit")
        for needle in ("防误触断言：LUNO_DEPLOY_AUTHORIZED=1", "平台回读（部署前）：id=",
                       "回滚包：", "上传：key=", "下载校验：",
                       "安装：官方 importFromUrl HTTP 已返回 status=200 且信封为 result 形态"
                       "（请求已返回，待完整回读判等）",
                       "回读判等："):
            self.assertIn(needle, out)
        self.assertEqual(harness.client.puts[0][0], "%s.zip" % fixture.name,
                         "上传 key 须等于 --key（= 登记既有来源 key）")
        rollback = fixture.rollback().read_bytes()
        self.assertEqual(sha256_bytes(rollback), sha256_bytes(harness.pre_blob))
        self.assertEqual(os.stat(str(fixture.rollback())).st_mode & 0o7777, 0o644)
        self.assertNotEqual(sha256_bytes(rollback), sha256_bytes(fixture.candidate().read_bytes()),
                            "回滚包不是候选包（不得拿部署后包充当回滚包）")

    def test_install_http_error_is_rc1(self):
        fixture, harness = self.harness(name="install-fail-skill",
                                        platform_kwargs={"install_status": 500})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：安装", err)
        self.assertIn("官方写入未返回 200（status=500）", err)
        self.assertEqual(harness.platform.uploads(), 1)
        self.assertFalse(harness.platform.installed, "非 200 不得被当成安装生效")

    def test_download_mismatch_is_rc1(self):
        fixture, harness = self.harness(name="download-fail-skill", served=b"tampered")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：下载校验", err)
        self.assertIn("与候选 ZIP 不一致", err)

    def test_platform_id_change_is_rc1(self):
        fixture, harness = self.harness(name="id-change-skill",
                                        platform_kwargs={"post_id": "skl_OtherFixture01"})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)

    def test_zip_hash_change_is_rc1(self):
        fixture, harness = self.harness(name="hash-change-skill",
                                        platform_kwargs={"post_hash": "0" * 64})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("zipFileHash", err)

    def test_name_and_description_change_is_repaired_by_manifest(self):
        """name／description 不符不再直接失败：合并进**一次** `agentSkills.update` 的 manifest 修正。

        平台把 `content`／`description`／`name` 当独立字段（edit 不带 description 时描述静默留旧
        文案），故字段差异走受支持的修正路径 `{id, manifest:{name, description}}`，修正后重读复核。
        正文本来就相等 ⇒ 载荷**不得**带 `content`（只在需要时给）。
        """
        for label, kwargs in (("name", {"post_name": "other-name"}),
                              ("description", {"post_description": "别的描述"})):
            with self.subTest(field=label):
                fixture, harness = self.harness(name="field-change-%s-skill" % label,
                                                platform_kwargs=kwargs)
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 0, out + err)
                edits = harness.platform.edits()
                self.assertEqual(len(edits), 1, "字段修正恰一次 update（不逐字段重投）")
                payload = json.loads(edits[0]["body"].decode("utf-8"))["json"]
                self.assertEqual(payload, {"id": fixture.expect_id,
                                           "manifest": {"name": fixture.name,
                                                        "description": "夹具技能描述"}},
                                 "正文相等时不得带 content；manifest 两项一次给齐")
                self.assertEqual(harness.platform.post_name, fixture.name)
                self.assertEqual(harness.platform.post_description, "夹具技能描述")

    def test_field_repair_taking_no_effect_is_rc1(self):
        """修正路径不是「发一次就算成功」：重读仍不符即失败（rc=1、阶段「回读判等」）。"""
        fixture, harness = self.harness(
            name="field-repair-stuck-skill",
            platform_kwargs={"post_name": "other-name", "post_name_after_edit": "other-name"})
        harness.ns["REPAIR_POLL_DELAYS"] = (0.0,) * 5      # 行为判据不依赖真实等待
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("轮询 5 次仍未收敛", err)
        self.assertIn("回读 name 与 --name 不一致", err)

    def test_tail_lf_trimmed_is_fixed_by_supported_edit(self):
        fixture, harness = self.harness(name="tail-lf-skill")
        harness.platform.post_content = fixture.body_text().rstrip("\n")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(harness.platform.edits()), 1, "裁尾 LF 只能靠 edit 补齐")
        self.assertEqual(harness.platform.content, fixture.body_text())

    def test_tail_lf_trimmed_and_edit_fails_is_rc1(self):
        fixture, harness = self.harness(name="tail-lf-fail-skill",
                                        platform_kwargs={"edit_status": 500})
        harness.ns["WRITE_RETRY_DELAYS"] = (0.0, 0.0)      # 5xx 重试次数才是判据，不依赖等待
        harness.platform.post_content = fixture.body_text().rstrip("\n")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        # F4：失败检查在 `with timer.phase(STAGE_EDIT)` **内** ⇒ 失败阶段如实归到「正文修补」
        self.assertIn("阶段失败：正文修补", err)
        self.assertIn("官方写入未返回 200（status=500）", err)
        self.assertIn("已尝试 3 次仍失败", err, "edit 遇 5xx 须重试到上限（1 次＋2 次重试）")
        self.assertEqual(len(harness.platform.edits()), 3, "同一幂等 update 最多 3 次尝试")
        table, _total = PhaseTiming.rows(self, out)
        self.assertIn("正文修补", table, out)
        self.assertEqual(table["正文修补"][3], "rc=1", "修补阶段须如实显示失败 rc")

    def test_resource_path_set_difference_is_rc1(self):
        fixture, harness = self.harness(name="resource-set-skill")
        harness.platform.post_resources = sorted(fixture.resource_map()) + ["references/extra.md"]
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("资源路径集不等（平台 2 项／候选 1 项）", err)
        self.assertNotIn("references/extra.md", err, "外部路径不回显（F1）")

    def test_resource_bytes_difference_is_rc1(self):
        """资源 bytes 漂移仍在**本入口的逐项比较点**上被判失败（bytes 经同域 HTTP 回读）。

        CLI 逐资源 `read-resource` 回退按 F2 取消，故此形态用注入传输层构造（离线、不联网）。
        """
        fixture = self.fixture(name="resource-bytes-skill")
        honest = fixture.resource_map()
        tampered = dict(honest)
        tampered[RESOURCE_REL] = honest[RESOURCE_REL][:-1] + b"!"
        self.assertNotEqual(tampered[RESOURCE_REL], honest[RESOURCE_REL], "注入须确实改变 bytes")
        harness = Harness(fixture, transport=StubTransport(tampered))
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("资源字节不等：%s" % RESOURCE_REL, err)

    def test_platform_view_failure_is_rc2_before_write(self):
        fixture, harness = self.harness(name="view-fail-skill",
                                        platform_kwargs={"view_rc": 1})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：平台回读", err)
        self.assertEqual(harness.platform.uploads(), 0)

    def test_post_install_view_failure_is_rc1(self):
        """安装后那次 view（现同时承载资源集回读）失败 ⇒ 写路径内 rc=1。

        原「资源清单（`skill resources`）失败」判据随该 CLI 退休后迁移到本用例。
        """
        fixture, harness = self.harness(name="postview-fail-skill")

        def fail_after_install(args):
            if args[:2] == ["skill", "view"] and harness.platform.installed:
                harness.platform.view_rc = 1

        harness.platform.on_call = fail_after_install
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("平台回读失败：lh skill view rc=1", err)
        self.assertEqual(harness.platform.uploads(), 1, "写路径已开始 ⇒ 不得报「未进入写路径」")
        views = [c for c in harness.platform.calls if c[:2] == ["skill", "view"]]
        self.assertEqual(len(views), 2, "失败点是安装后那次 view（正控：部署前 view 已通过）")

    def test_predeploy_hash_not_64_hex_stops_deploy(self):
        fixture, harness = self.harness(name="prehash-skill",
                                        platform_kwargs={"pre_hash": "deadbeef"})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：回滚包", err)
        self.assertIn("完整 64 位十六进制", err)
        self.assertEqual(harness.platform.uploads(), 0, "回滚能力不成立即零上传")
        self.assertFalse(fixture.rollback().exists())

    def test_predeploy_object_mismatch_stops_deploy(self):
        fixture, harness = self.harness(name="preblob-skill",
                                        platform_kwargs={"pre_hash": "a" * 64})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：回滚包", err)
        self.assertIn("回滚能力不成立，停止部署", err)
        self.assertEqual(harness.platform.uploads(), 0)
        self.assertFalse(fixture.rollback().exists())


class EmptyPackageCounterexample(FixtureCase):
    """判据 8：空包反例链＋变异验证。"""

    def test_chain_and_mutation(self):
        fixture = self.fixture(name="empty-package-skill")
        harness = Harness(fixture)
        args = fixture.args(deploy=True)

        # ① 有效源基线绿（部署模式，假件齐备）
        rc, out, err = harness.run(args)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(harness.platform.uploads(), 1)
        baseline_files = fixture.out_dir_files()

        # ② 仅把显式源换成空目录 → 红且零上传
        fixture.clear_skill()
        uploads_before = harness.platform.uploads()
        calls_before = len(harness.platform.calls)
        rc, out, err = harness.run(args)
        self.assertEqual(rc, 2, out + err)
        self.assertIn("包有效性未通过（不上传）：空包（源内无文件", err)
        self.assertEqual(harness.platform.uploads(), uploads_before, "空包必须零上传")
        self.assertEqual(len(harness.platform.calls), calls_before,
                         "空包不得进入任何平台读取／安装")
        self.assertEqual(fixture.out_dir_files(), baseline_files, "失败不得覆盖已有有效产物")

        # ③ 恢复有效源 → 绿
        fixture.write_skill()
        rc, out, err = harness.run(args)
        self.assertEqual(rc, 0, out + err)

        # ④ 变异：删除空包拒绝条件（包有效性统一拒绝语句）→ 「空包」分类必须消失；
        #    纵深守卫（候选 ZIP 根 SKILL.md）接手后仍 fail-closed、零上传。
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn(EMPTY_PACKAGE_GUARD, source, "变异前须存在待删片段")
        mutated = source.replace(EMPTY_PACKAGE_GUARD, "")
        self.assertNotEqual(mutated, source, "变异须确实改变字节（否则本用例空转）")
        self.assertIn(EMPTY_PACKAGE_CLAUSE, source, "变异前须存在待删片段")
        narrow = source.replace(EMPTY_PACKAGE_CLAUSE, "")
        self.assertNotEqual(narrow, source)
        # 假件在源仍有效时构造（期望内容／资源已捕获），随后才清空源目录
        mutant = Harness(fixture, source=mutated, content=harness.content,
                         resources=harness.resource_map)
        narrow_harness = Harness(fixture, source=narrow, content=harness.content,
                                 resources=harness.resource_map)
        fixture.clear_skill()
        try:
            rc_m, out_m, err_m = mutant.run(args)
        except Exception as exc:                      # 变异体可能在上传之后崩溃
            rc_m, out_m, err_m = 1, "", "%s: %s" % (exc.__class__.__name__, exc)
        self.assertNotIn("空包", out_m + err_m,
                         "删除空包拒绝条件后不得再报该分类（证明该判据非空转）")
        self.assertEqual(rc_m, 2, out_m + err_m)
        self.assertIn("候选 ZIP 内缺根 SKILL.md", err_m, "第二道守卫须接手并 fail-closed")
        self.assertEqual(mutant.platform.uploads(), 0, "纵深守卫仍须零上传")
        self.assertNotIn("缺少 SDK", out_m + err_m, "不得因缺 SDK 碰巧失败")
        self.assertNotIn("缺少存储凭据", out_m + err_m, "不得因缺凭据碰巧失败")

        # ⑤ 收窄变异（纵深证据）：只删 helper 的空包子句 → 仍 fail-closed、零上传
        rc_n, out_n, err_n = narrow_harness.run(args)
        self.assertEqual(rc_n, 2, out_n + err_n)
        self.assertIn("缺根 SKILL.md", err_n)
        self.assertEqual(narrow_harness.platform.uploads(), 0)


class SdkSilenceBoundary(FixtureCase):
    """F1：SDK 静音边界——SDK 自身的 stdout／stderr／logging 一律丢弃（正控＋反控）。"""

    def test_sdk_noise_never_reaches_output(self):
        fixture = self.fixture(name="noisy-sdk-skill")
        harness = Harness(fixture, noisy=True)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(harness.platform.uploads(), 1, "正控须真的走到上传（断言非空转）")
        self.assertNotIn(SECRET_MARKER, out + err,
                         "SDK stdout／stderr／logging 不得进入工具输出")

    def test_mutation_without_boundary_leaks_the_marker(self):
        fixture = self.fixture(name="noisy-mutant-skill")
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn(SILENCE_ANCHOR, source, "变异前须存在待删片段")
        mutant = source.replace(SILENCE_ANCHOR, SILENCE_MUTATION)
        self.assertNotEqual(mutant, source, "变异须确实改变字节（否则本用例空转）")
        harness = Harness(fixture, source=mutant, noisy=True)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertIn(SECRET_MARKER, out + err,
                      "撤掉静音边界后 SDK 标记必须出现（证明上面的断言不是空转）")


class PlatformFieldWhitelist(FixtureCase):
    """F1 ＋ 本批：`skill view` 必须带字段白名单（含 `resources`、**不含** `source`／`manifest`），
    且资源集经**同一次** view 回读 ⇒ `skill resources` CLI **归零**（夹具已不应答该 verb）。"""

    def test_argv_carries_field_whitelists_without_source(self):
        ns = load_tool_namespace()
        self.assertEqual(ns["PLATFORM_FIELDS"],
                         ("id", "identifier", "name", "description", "content", "zipFileHash",
                          "resources"))
        self.assertNotIn("TREE_FIELDS", ns, "树形态投影已随该 CLI 取消，字段常量一并退休")
        self.assertNotIn("source", ns["PLATFORM_FIELDS"])
        self.assertNotIn("manifest", ns["PLATFORM_FIELDS"], "manifest 含签名 URL，不进白名单")
        fixture = self.fixture(name="fields-skill")
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        views = [c for c in harness.platform.calls if c[:2] == ["skill", "view"]]
        self.assertEqual(len(views), 2, "部署前＋回读各一次 view")
        self.assertEqual(views[0], ["skill", "view", fixture.expect_id, "--json",
                                    "id,identifier,name,description,content,zipFileHash,"
                                    "resources"])
        for call in views:
            self.assertEqual(call[-2], "--json", "字段白名单须作为 --json 的值")
            fields = call[-1].split(",")
            self.assertIn("resources", fields, "资源集随该次 view 回读")
            self.assertNotIn("source", fields,
                             "源端白名单不得含 source 字段（签名 URL 不进内存）")
            self.assertNotIn("source", call, "命令行不得出现裸 source 参数")
        self.assertEqual([c[:2] for c in harness.platform.calls],
                         [["skill", "view"], ["skill", "view"]],
                         "整条写路径的 CLI 面：view ×2（install 已改官方 HTTP 写入）")
        self.assertEqual([w["kind"] for w in harness.write_stub.requests], ["install"],
                         "写入恰一次、只经官方 HTTP")


class SourceIdentity(FixtureCase):
    """F3：ZIP 哈希匹配不能证明所写 bucket／key 是该对象既有来源。"""

    def test_same_bytes_under_another_key_is_refused(self):
        fixture = self.fixture(name="other-key-skill")
        cp = fixture.run_tool(fixture.args())          # 打包模式：取出确定性候选包字节
        self.assertEqual(cp.returncode, 0, text_of(cp)[1])
        candidate = fixture.candidate().read_bytes()
        other = "url.fixture-account.r2.cloudflarestorage.com.fixture-bucket.other-key.zip"
        harness = Harness(fixture, pre_blob=candidate, platform_kwargs={"identifier": other})
        self.assertEqual(sha256_bytes(harness.pre_blob), sha256_bytes(candidate),
                         "夹具前置：另一 key 下的 ZIP 与候选包**同字节**")
        self.assertEqual(harness.platform.pre_hash, sha256_bytes(candidate),
                         "夹具前置：部署前 zipFileHash 等于候选包（仅 ZIP 判据会放行）")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：平台回读", err)
        self.assertIn("bucket／key", err)
        self.assertEqual(harness.platform.uploads(), 0, "同字节 ZIP 也不得推定同 key")

    def test_non_url_identifier_is_refused(self):
        fixture = self.fixture(name="user-ident-skill")
        harness = Harness(fixture, platform_kwargs={"identifier": "user.fixture"})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("非 URL 型", err)
        self.assertEqual(harness.platform.uploads(), 0)

    def test_bucket_account_host_and_signed_query_mismatch_are_refused(self):
        name = "ident-mismatch-skill"
        key = "%s.zip" % name
        cases = (
            ("bucket", "url.fixture-account.r2.cloudflarestorage.com.other-bucket." + key,
             "bucket／key"),
            ("account", "url.other-account.r2.cloudflarestorage.com.fixture-bucket." + key,
             "前缀不是"),
            ("host", "url.fixture-account.s3.amazonaws.com.fixture-bucket." + key, "主机不是"),
            ("signed-query", "url.fixture-account.r2.cloudflarestorage.com.fixture-bucket."
                             + key + "?X-Amz-Signature=" + SECRET_MARKER, "bucket／key"),
        )
        for label, ident, needle in cases:
            with self.subTest(case=label):
                fixture = self.fixture(name=name)
                harness = Harness(fixture, platform_kwargs={"identifier": ident})
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 2, "%s: %s" % (label, out + err))
                self.assertIn("阶段失败：平台回读", err)
                self.assertIn(needle, err)
                self.assertEqual(harness.platform.uploads(), 0)
                self.assertNotIn(SECRET_MARKER, out + err, "签名查询参数不得外流")
                self.assertNotIn("X-Amz-Signature", out + err)


class ContentRepairBoundary(FixtureCase):
    """F2：只有「恰少一个尾 LF」可修补；修补后须重取**完整对象**重核。"""

    def test_non_tail_lf_difference_is_refused_with_zero_edit(self):
        fixture = self.fixture(name="non-lf-skill")
        body = fixture.body_text()
        cases = (
            ("同长度改单字", body.replace("夹具正文。", "夹具正文！")),
            ("多一个尾 LF", body + "\n"),
            ("少两个尾部字节", body[:-2]),
        )
        for label, mutated in cases:
            with self.subTest(case=label):
                self.assertNotEqual(mutated, body, "变异须确实改变字节")
                harness = Harness(fixture)
                harness.platform.post_content = mutated
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, "%s: %s" % (label, out + err))
                self.assertIn("非恰少一个尾 LF；停止，不自动改写", err)
                self.assertEqual(harness.platform.edits(), [], "任意正文差异都不得自动改写")
                self.assertEqual(harness.platform.uploads(), 1, "上传已发生（写路径已开始 ⇒ rc=1）")

    def test_tail_lf_positive_control_still_passes(self):
        fixture = self.fixture(name="lf-ok-skill")
        harness = Harness(fixture)
        harness.platform.post_content = fixture.body_text().rstrip("\n")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(harness.platform.edits()), 1, "恰少一个尾 LF 仍走支持的 edit")

    def test_field_change_after_edit_is_rejected(self):
        """补写后**轮询**仍不收敛即失败：hash 走**每轮**完整性判定（立即停），字段走轮询重核。"""
        for label, kwargs, needle, terminal in (
                ("hash", {"post_hash_after_edit": "0" * 64}, "zipFileHash", "完整性异常"),
                ("description", {"post_description_after_edit": "别的描述"}, "description",
                 "轮询 5 次仍未收敛"),
                ("name", {"post_name_after_edit": "other-name"}, "name",
                 "轮询 5 次仍未收敛")):
            with self.subTest(field=label):
                fixture = self.fixture(name="post-edit-%s-skill" % label)
                harness = Harness(fixture, platform_kwargs=kwargs)
                harness.ns["REPAIR_POLL_DELAYS"] = (0.0,) * 5   # 行为判据不依赖真实等待
                harness.platform.post_content = fixture.body_text().rstrip("\n")
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, "%s: %s" % (label, out + err))
                self.assertEqual(len(harness.platform.edits()), 1, "先按支持的 edit 修补")
                self.assertIn(terminal, err)
                self.assertIn(needle, err)


class AuthorizationOrder(FixtureCase):
    """F6：缺防误触断言时不产生任何写操作（含候选包）；无 `--deploy` 正控仍成功。"""

    def test_missing_assertion_writes_nothing_in_process(self):
        fixture = self.fixture(name="auth-order-skill")
        existing = fixture.assets / "existing-artifact.zip"
        existing.write_bytes(b"PREVIOUS-ARTIFACT-BYTES")
        before = fixture.out_dir_files()
        harness = Harness(fixture, env={})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：授权", err)
        self.assertIn("防误触断言", err)
        self.assertIn("不构成授权来源", err)
        self.assertEqual(fixture.out_dir_files(), before, "--out-dir 不得有任何变化")
        self.assertEqual(existing.read_bytes(), b"PREVIOUS-ARTIFACT-BYTES")
        self.assertFalse(fixture.candidate().exists(), "缺断言时不得写出候选包")
        self.assertEqual(harness.platform.calls, [], "零平台调用")
        self.assertEqual(harness.platform.uploads(), 0)

    def test_pack_only_positive_control_still_succeeds(self):
        fixture = self.fixture(name="pack-only-skill")
        cp = fixture.run_tool(fixture.args())
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 0, out + err)
        self.assertTrue(fixture.candidate().exists())
        self.assertEqual(fixture.lh_calls(), [])
        self.assertFalse(fixture.sdk_imported())


# ── O5：资源回读走既有 HTTP 客户端，保留逐项原始 bytes 判等 ────────────────────

class StubTransport(object):
    """假传输模块（接口与 `tools/resource_http.py` 同）：按 path 回放指定 bytes。

    用于证明**本入口自己的**逐项 bytes 比较不是死代码——客户端校验不到「结构自洽但异于候选」
    的返回（真客户端的完整性校验会先拦下），故这里注入传输层，直接打本入口的比较点。

    `valid_path` 由 `Harness` 装载时挂上**真实** `tools/resource_http.py` 的同名函数（形态门与
    HTTP 客户端消费同一校验器，不在夹具里抄第二份）。
    """

    class ResourceError(ValueError):
        pass

    valid_path = None

    def __init__(self, blobs):
        self.blobs = dict(blobs)
        self.reads = []

    def connection_context(self):
        return (HttpStub.ORIGIN, "synthetic-offline")

    def ResourceClient(self, deadline, context):
        return self

    def collect(self, client, sid, planned, workers):
        self.reads = [item[0] for item in planned]
        return dict((path, self.blobs[path]) for path, _size, _digest in planned)


class HttpResourceReadback(FixtureCase):
    """判据 13／14：HTTP 资源回读、同域前置硬门槛、HTTP 侧固定分类失败。"""

    EXTRA_RESOURCES = ("references/empty.md", "references/binary.bin",
                       "references/crlf.txt", "references/no-lf.txt")

    def rich_fixture(self, name):
        """含空文件／二进制／CRLF／无尾 LF 的候选资源集（bytes 判等的最小形态覆盖）。"""
        fixture = self.fixture(name=name)
        fixture.write_resource("references/empty.md", b"")
        fixture.write_resource("references/binary.bin", b"\x89PNG\r\n\x1a\n\x00\xff\xfe")
        fixture.write_resource("references/crlf.txt", b"a\r\nb\r\n")
        fixture.write_resource("references/no-lf.txt", b"no trailing LF")
        return fixture

    def stub(self, fixture, **kwargs):
        encoding = {"references/binary.bin": "base64"}
        encoding.update(kwargs.pop("encoding", {}))
        return HttpStub(fixture.resource_map(), encoding=encoding, **kwargs)

    def test_http_readback_reads_every_resource_over_http(self):
        fixture = self.rich_fixture("http-bytes-skill")
        expected = sorted(fixture.resource_map())
        stub = self.stub(fixture)
        harness = Harness(fixture, http=stub)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertIn("资源回读：HTTP 同域已冻结", out)
        self.assertEqual(sorted(stub.requests), expected, "每个候选资源恰一次 HTTP 读取")
        self.assertEqual(set(stub.methods), {"GET"})
        reads = [call for call in harness.platform.calls if call[:2] == ["skill", "read-resource"]]
        self.assertEqual(reads, [], "逐资源 CLI read-resource 归零（该退化路径按 F2 取消）")
        self.assertEqual(harness.platform.uploads(), 1)

    def test_same_origin_unprovable_stops_before_any_write(self):
        """F2：同域不可证明 ⇒ 固定分类失败并**停止本次部署**（零 HTTP／零上传／零 install／零 edit）。"""
        cases = (
            ("缺指定 key", {}),
            ("key 含非法字符", {"LOBEHUB_CLI_API_KEY": "bad\r\nkey"}),
            ("origin 不符", {"LOBEHUB_SERVER": "https://untrusted.invalid",
                             "LOBEHUB_CLI_API_KEY": FROZEN_KEY}),
            ("显式 workspace", {"LOBEHUB_SERVER": HttpStub.ORIGIN,
                                "LOBEHUB_CLI_API_KEY": FROZEN_KEY,
                                "LOBEHUB_WORKSPACE_ID": "ws-fixture"}),
        )
        for label, env in cases:
            with self.subTest(case=label):
                fixture = self.fixture(name="freeze-fail-skill")
                stub = self.stub(fixture)
                harness = Harness(fixture, http=stub, http_env=env)
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 2, "%s: %s" % (label, out + err))
                self.assertIn("阶段失败：平台回读", err)
                self.assertIn("同域前置未通过；停止本次部署，未执行平台或存储写入", err)
                self.assertIn("同域不可证明", out)
                self.assertNotIn("核验一致，未执行部署写入", out, "不得报成功")
                self.assertEqual(stub.requests, [], "同域不可证明时零 HTTP")
                self.assertEqual(harness.platform.calls, [], "零平台 CLI 调用")
                self.assertEqual(harness.platform.uploads(), 0, "零上传")
                self.assertEqual(harness.client.gets, [], "零 R2 读取")
                self.assertEqual(harness.platform.installed_calls(), [], "零 install")
                self.assertEqual(harness.platform.edits(), [], "零 edit")
                self.assertFalse(fixture.rollback().exists(), "不得写回滚包")
                self.assertNotIn("LOBEHUB_CLI_API_KEY", out, "凭据变量名不外流")
                self.assertNotIn(FROZEN_KEY, out + err, "key 值不外流")

    def test_http_failures_are_fixed_classifications(self):
        cases = (
            ("401", {"status": 401}, "authentication"),
            ("403", {"status": 403}, "authentication"),
            ("429", {"status": 429}, "rate-limit"),
            ("重定向 302", {"status": 302}, "http-status"),
            ("500", {"status": 500}, "http-status"),
            ("截断", {"headers": {"Content-Length": "999999"}}, "truncated"),
            ("坏编码", {"encoding": {RESOURCE_REL: "gzip"}}, "encoding"),
            ("预算耗尽", {"budget": -1.0}, "budget"),
        )
        for label, kwargs, kind in cases:
            with self.subTest(case=label):
                fixture = self.fixture(name="http-fail-skill")
                kwargs = dict(kwargs)
                budget = kwargs.pop("budget", None)
                stub = self.stub(fixture, **kwargs)
                harness = Harness(fixture, http=stub)
                if budget is not None:
                    harness.ns["RESOURCE_HTTP_BUDGET"] = budget
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, "%s: %s" % (label, out + err))
                self.assertIn("阶段失败：回读判等", err)
                self.assertIn("资源 HTTP 回读失败：%s" % kind, err)
                self.assertEqual(harness.platform.uploads(), 1, "写路径已开始 ⇒ rc=1")

    def test_size_hash_met_but_actual_bytes_differ_is_refused(self):
        """元数据（size／fileHash）与候选一致而实际回放 bytes 不同 ⇒ 必须失败。"""
        cases = (
            ("声明取自候选（实际 bytes 不同）", "integrity"),
            ("声明与回放 bytes 自洽但异于候选", "structure"),
        )
        for label, kind in cases:
            with self.subTest(case=label):
                fixture = self.fixture(name="http-lie-skill")
                rel = RESOURCE_REL
                real = fixture.resource_map()[rel]
                tampered = real[:-1] + b"!"          # 同长度、单字节不同、仍是合法 UTF-8
                self.assertNotEqual(tampered, real)
                self.assertEqual(len(tampered), len(real))
                meta = ((len(real), sha256_bytes(real)) if kind == "integrity"
                        else (len(tampered), sha256_bytes(tampered)))
                stub = self.stub(fixture, serve={rel: tampered}, meta={rel: meta})
                harness = Harness(fixture, http=stub)
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, "%s: %s" % (label, out + err))
                self.assertIn("资源 HTTP 回读失败：%s" % kind, err)
                self.assertEqual(harness.platform.uploads(), 1)

    def test_deploy_side_bytes_comparison_is_not_dead_code(self):
        """注入传输层返回「异于候选」的 bytes ⇒ 本入口的逐项比较必须拒绝（负控非空转）。"""
        fixture = self.fixture(name="transport-tamper-skill")
        honest = fixture.resource_map()
        good = Harness(fixture, transport=StubTransport(honest))
        rc, out, err = good.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(good.ns["HTTP_WORKERS"], 4, "并发固定 4；原有逐项 bytes 负控仍须拒绝")
        tampered = dict(honest)
        tampered[RESOURCE_REL] = honest[RESOURCE_REL][:-1] + b"!"
        self.assertNotEqual(tampered[RESOURCE_REL], honest[RESOURCE_REL], "注入须确实改变 bytes")
        bad = Harness(fixture, transport=StubTransport(tampered))
        rc, out, err = bad.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("资源字节不等：%s" % RESOURCE_REL, err)

    def test_resource_path_set_drift_is_refused_without_http(self):
        cases = (
            ("多一个资源", ["references/extra.md"], [], "资源路径集不等"),
            ("少一个资源", [], [RESOURCE_REL], "资源路径集不等"),
            ("非法路径", ["references/../escape.md"], [], "平台 resources 含非法路径"),
        )
        for label, extra, drop, needle in cases:
            with self.subTest(case=label):
                fixture = self.fixture(name="set-drift-skill")
                served = sorted([p for p in fixture.resource_map() if p not in drop] + extra)
                stub = self.stub(fixture)
                harness = Harness(fixture, http=stub,
                                  platform_kwargs={"post_resources": served})
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, "%s: %s" % (label, out + err))
                self.assertIn(needle, err)
                self.assertEqual(len(harness.platform.installed_calls()), 1, "写路径已开始")
                self.assertEqual(stub.requests, [], "路径集／形态不符时不得发起任何资源 HTTP")

    def test_pack_mode_queries_nothing(self):
        """默认（不带 `--deploy`）打包模式不得查询平台，也不得加载资源传输模块。"""
        fixture = self.fixture(name="pack-only-platform-skill")
        stub = HttpStub(fixture.resource_map())
        harness = Harness(fixture, http=stub)
        rc, out, err = harness.run(fixture.args())
        self.assertEqual(rc, 0, out + err)
        self.assertIn("写路径：未进入", out)
        self.assertEqual(harness.platform.calls, [], "打包模式不得查询平台")
        self.assertEqual(harness.platform.uploads(), 0)
        self.assertNotIn("resource_http", harness.loaded, "打包模式不得加载资源传输模块")
        self.assertEqual(stub.requests, [])


# ── 本批：资源集并入 `skill view` 顶层 `resources` 后的形态门 ──────────────────

class ResourceMetadataGate(FixtureCase):
    """判据 24：`resources` 顶层字段（`Record<path,{size,fileHash}>`）的形态门与逐项元数据判等。

    正控：按候选 bytes 现算的合法映射、空映射与 `null` 空集放行；负控：未知嵌套字段（含 URL
    形态）、缺字段、非法路径、size／fileHash 不符、非 Record 形态一律 fail-closed，且**都在发起
    资源 HTTP 之前**；未知字段的**值**不得进入输出（可能是签名 URL）。资源 bytes 仍经 HTTP 逐项
    回读——元数据判等**不**代替逐字节比较。
    """

    def stub(self, fixture, **kwargs):
        return HttpStub(fixture.resource_map(), **kwargs)

    def meta_of(self, fixture, rel=RESOURCE_REL):
        """按候选 ZIP 内该资源 bytes 现算的合法元数据（不从平台侧抄任何常量）。"""
        blob = fixture.resource_map()[rel]
        return {"size": len(blob), "fileHash": sha256_bytes(blob)}

    def test_unknown_nested_field_is_refused_without_http(self):
        """未知嵌套字段（形如带签名 URL 的字段）⇒ 固定分类失败，且**值**不进输出。"""
        fixture = self.fixture(name="meta-unknown-skill")
        raw = {RESOURCE_REL: dict(self.meta_of(fixture),
                                  url="https://r2.invalid/x?X-Amz-Signature=%s" % SECRET_MARKER)}
        stub = self.stub(fixture)
        harness = Harness(fixture, http=stub, platform_kwargs={"post_resources_raw": raw})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("平台 resources 项含未知字段（1 项）", err)
        self.assertNotIn("项含未知字段：", err, "未知字段名不得回显")
        self.assertEqual(harness.platform.uploads(), 1, "写路径已开始 ⇒ rc=1")
        self.assertEqual(stub.requests, [], "形态门失败 ⇒ 零资源 HTTP")
        self.assertNotIn(SECRET_MARKER, out + err, "未知字段的值不得外流")
        self.assertNotIn("r2.invalid", out + err, "未知字段的值不得外流")

    def test_missing_nested_field_is_refused(self):
        fixture = self.fixture(name="meta-missing-skill")
        blob = fixture.resource_map()[RESOURCE_REL]
        raw = {RESOURCE_REL: {"size": len(blob)}}
        stub = self.stub(fixture)
        harness = Harness(fixture, http=stub, platform_kwargs={"post_resources_raw": raw})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("平台 resources 项缺字段（fileHash）", err)
        self.assertEqual(stub.requests, [], "形态门失败 ⇒ 零资源 HTTP")

    def test_size_and_file_hash_mismatch_are_refused_per_item(self):
        """size／fileHash 与候选 bytes 现算值不等 ⇒ 逐项判等拒绝（元数据不代替 bytes 回读）。"""
        fixture = self.fixture(name="meta-mismatch-skill")
        blob = fixture.resource_map()[RESOURCE_REL]
        cases = (
            ("size", dict(self.meta_of(fixture), size=len(blob) + 1),
             "资源元数据与候选不等：%s（size 不等（平台 %d／候选 %d））"
             % (RESOURCE_REL, len(blob) + 1, len(blob))),
            ("fileHash", dict(self.meta_of(fixture), fileHash="0" * 64),
             "资源元数据与候选不等：%s（fileHash 不等）" % RESOURCE_REL),
        )
        for label, meta, needle in cases:
            with self.subTest(case=label):
                stub = self.stub(fixture)
                harness = Harness(fixture, http=stub,
                                  platform_kwargs={"post_resources_raw": {RESOURCE_REL: meta}})
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, "%s: %s" % (label, out + err))
                self.assertIn(needle, err)
                self.assertEqual(stub.requests, [], "元数据不符须在资源 HTTP 之前停止")

    def test_empty_resources_allows_empty_candidate_and_refuses_nonempty(self):
        # ① 无资源技能（源内无资源）＋ `{}`／`null` ⇒ 严格允许为空集、rc=0、零资源 HTTP
        for label, raw in (("空映射", {}), ("null", None)):
            with self.subTest(case=label):
                fixture = self.fixture(name="meta-empty-skill")
                (fixture.repo / fixture.src_rel / RESOURCE_REL).unlink()
                fixture.register_resources([])
                stub = HttpStub({})
                harness = Harness(fixture, http=stub,
                                  platform_kwargs={"post_resources_raw": raw})
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 0, "%s: %s" % (label, out + err))
                self.assertEqual(stub.requests, [], "空资源集不得发起任何资源 HTTP")
        # ② 有资源候选 ＋ 空集 ⇒ 路径集不等（平台 0 项／候选 1 项），且不发资源 HTTP
        fixture = self.fixture(name="meta-empty-platform-skill")
        stub = self.stub(fixture)
        harness = Harness(fixture, http=stub, platform_kwargs={"post_resources_raw": {}})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("资源路径集不等（平台 0 项／候选 1 项", err)
        self.assertEqual(stub.requests, [], "路径集不等须在资源 HTTP 之前停止")

    def test_non_record_shape_is_refused(self):
        for label, raw, needle in (("列表", [RESOURCE_REL], "不是 Record 形态（list）"),
                                   ("字符串", RESOURCE_REL, "不是 Record 形态（str）")):
            with self.subTest(case=label):
                fixture = self.fixture(name="meta-shape-skill")
                stub = self.stub(fixture)
                harness = Harness(fixture, http=stub,
                                  platform_kwargs={"post_resources_raw": raw})
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, "%s: %s" % (label, out + err))
                self.assertIn(needle, err)
                self.assertEqual(stub.requests, [], "形态门失败 ⇒ 零资源 HTTP")

    def test_readonly_branch_metadata_gate_is_rc2_with_zero_writes(self):
        """未变只读分支取**部署前**那次 view 的 `resources`；形态失败 ⇒ rc=2 且零写入。"""
        fixture = self.fixture(name="meta-readonly-skill")
        candidate = pack_candidate(fixture)
        raw = {RESOURCE_REL: dict(self.meta_of(fixture), url="https://r2.invalid/x")}
        stub = self.stub(fixture)
        harness = Harness(fixture, http=stub, pre_blob=candidate,
                          platform_kwargs={"pre_hash": sha256_bytes(candidate),
                                           "pre_content": fixture.body_text(),
                                           "pre_description": "夹具技能描述",
                                           "resources_raw": raw})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：只读核验", err)
        self.assertIn("平台 resources 项含未知字段（1 项）", err)
        self.assertNotIn("项含未知字段：", err, "未知字段名不得回显")
        self.assertNotIn("核验一致，未执行部署写入", out, "不得报跳过成功")
        self.assertEqual(harness.platform.uploads(), 0, "零 R2 上传")
        self.assertEqual(harness.client.gets, [], "零 R2 读取")
        self.assertEqual(harness.platform.installed_calls(), [], "零 install")
        self.assertEqual(harness.platform.edits(), [], "零 edit")
        self.assertEqual(stub.requests, [], "只读分支形态门失败：零资源 HTTP")

    def test_external_keys_and_paths_never_reach_output(self):
        """F1 反证：合成标记放进**合法但多出的路径**／**非法 URL 路径**／**未知字段名**。

        三种位置都必须：非零 rc、**零输出**（stdout／stderr 均无标记）、零资源 HTTP。对象键不保证
        非秘密，只禁回显字段**值**不构成秘密边界。
        """
        marker = SECRET_MARKER
        fixture = self.fixture(name="meta-marker-skill")
        cases = (
            ("合法但多出的路径",
             {"post_resources": sorted(fixture.resource_map())
              + ["references/%s.md" % marker]},
             "资源路径集不等（平台 2 项／候选 1 项）"),
            ("非法 URL 路径",
             {"post_resources_raw": {"https://r2.invalid/x-%s" % marker: self.meta_of(fixture)}},
             "平台 resources 含非法路径"),
            ("未知字段名",
             {"post_resources_raw": {RESOURCE_REL: dict(self.meta_of(fixture), **{marker: "v"})}},
             "平台 resources 项含未知字段（1 项）"),
        )
        for label, kwargs, needle in cases:
            with self.subTest(case=label):
                stub = self.stub(fixture)
                harness = Harness(fixture, http=stub, platform_kwargs=kwargs)
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertNotEqual(rc, 0, "%s: %s" % (label, out + err))
                self.assertIn(needle, err)
                self.assertNotIn(marker, out + err, "%s：外部键／字段名不得外流" % label)
                self.assertEqual(stub.requests, [], "%s：须在资源 HTTP 之前停止" % label)

    def test_missing_resources_field_is_refused_at_real_view_entry(self):
        """F2：`resources` **键缺失**（≠ 显式 `null`）由真实 `platform_entry` 归一化层拒绝。

        初始 view 缺字段 ⇒ rc=2、零写；安装后 view 缺字段 ⇒ rc=1（写路径已开始）、零资源 HTTP。
        """
        fixture = self.fixture(name="meta-missing-pre-skill")
        stub = self.stub(fixture)
        harness = Harness(fixture, http=stub, platform_kwargs={"resources_raw": MISSING})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：平台回读", err)
        self.assertIn("平台回读缺 resources 字段", err)
        self.assertEqual(harness.platform.uploads(), 0, "零 R2 上传")
        self.assertEqual(harness.platform.installed_calls(), [], "零 install")
        self.assertEqual(harness.platform.edits(), [], "零 edit")
        self.assertEqual(harness.client.gets, [], "零 R2 读取")
        self.assertEqual(stub.requests, [], "零资源 HTTP")
        fixture = self.fixture(name="meta-missing-post-skill")
        stub = self.stub(fixture)
        harness = Harness(fixture, http=stub, platform_kwargs={"post_resources_raw": MISSING})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("平台回读缺 resources 字段", err)
        self.assertEqual(harness.platform.uploads(), 1, "写路径已开始 ⇒ rc=1")
        self.assertEqual(stub.requests, [], "缺字段须在资源 HTTP 之前停止")

    def test_missing_resources_field_in_readonly_and_empty_candidate(self):
        """F2 补：未变只读分支缺字段 ⇒ rc=2 零写且**不得**报「核验一致」；**空候选**同样拒缺字段。"""
        fixture = self.fixture(name="meta-missing-readonly-skill")
        candidate = pack_candidate(fixture)
        stub = self.stub(fixture)
        harness = Harness(fixture, http=stub, pre_blob=candidate,
                          platform_kwargs={"pre_hash": sha256_bytes(candidate),
                                           "pre_content": fixture.body_text(),
                                           "pre_description": "夹具技能描述",
                                           "resources_raw": MISSING})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("平台回读缺 resources 字段", err)
        self.assertNotIn("核验一致，未执行部署写入", out, "缺字段不得被当成空集放行")
        self.assertEqual(harness.platform.uploads(), 0, "零 R2 上传")
        self.assertEqual(harness.client.gets, [], "零 R2 读取")
        self.assertEqual(harness.platform.installed_calls(), [], "零 install")
        self.assertEqual(harness.platform.edits(), [], "零 edit")
        self.assertEqual(stub.requests, [], "零资源 HTTP")
        cases = (("空候选＋初始 view 缺字段", {"resources_raw": MISSING}, 2),
                 ("空候选＋安装后 view 缺字段", {"post_resources_raw": MISSING}, 1))
        for label, kwargs, want in cases:
            with self.subTest(case=label):
                empty = self.fixture(name="meta-missing-empty-skill")
                (empty.repo / empty.src_rel / RESOURCE_REL).unlink()
                empty.register_resources([])
                stub = HttpStub({})
                harness = Harness(empty, http=stub, platform_kwargs=kwargs)
                rc, out, err = harness.run(empty.args(deploy=True))
                self.assertEqual(rc, want, "%s: %s" % (label, out + err))
                self.assertIn("平台回读缺 resources 字段", err)
                self.assertEqual(stub.requests, [], "零资源 HTTP")

    def test_resource_map_boundary_table(self):
        """F1／F2 单元级小表：直接调 `platform_resource_map(entry, stage, valid_path)`。

        消费模块**真实**校验器（与生产同一份）；负控逐类断言固定分类，正控放行合法映射／空映射／
        `null`。含 `fullmatch` 边界（64 hex 尾随 LF 必须拒绝，`match`＋`$` 会放行）。
        """
        ns = load_tool_namespace()
        mod = load_source_namespace(
            (ROOT / "tools" / "resource_http.py").read_text(encoding="utf-8"))
        valid_path = mod["valid_path"]
        good = {"size": len(RESOURCE_BYTES), "fileHash": sha256_bytes(RESOURCE_BYTES)}
        cases = (
            ("缺 resources 键", {}, "平台回读缺 resources 字段"),
            ("未知嵌套字段", {"resources": {RESOURCE_REL: dict(good, url="u")}},
             "平台 resources 项含未知字段（1 项）"),
            ("缺嵌套字段", {"resources": {RESOURCE_REL: {"size": 1}}},
             "平台 resources 项缺字段（fileHash）"),
            ("项非对象", {"resources": {RESOURCE_REL: [RESOURCE_REL]}},
             "平台 resources 项不是对象（list）"),
            ("非法路径", {"resources": {"https://r2.invalid/x": good}},
             "平台 resources 含非法路径"),
            ("控制字符路径", {"resources": {"references/a\x01b.md": good}},
             "平台 resources 含非法路径"),
            ("非 Record 形态", {"resources": [RESOURCE_REL]},
             "平台 resources 不是 Record 形态（list）"),
            ("负 size", {"resources": {RESOURCE_REL: dict(good, size=-1)}},
             "平台 resources 项 size 不是非负整数（int）"),
            ("bool size", {"resources": {RESOURCE_REL: dict(good, size=True)}},
             "平台 resources 项 size 不是非负整数（bool）"),
            ("非 int size", {"resources": {RESOURCE_REL: dict(good, size="1")}},
             "平台 resources 项 size 不是非负整数（str）"),
            ("非 str fileHash", {"resources": {RESOURCE_REL: dict(good, fileHash=1)}},
             "平台 resources 项 fileHash 不是 64 位十六进制（int）"),
            ("fileHash 尾随 LF",
             {"resources": {RESOURCE_REL: dict(good, fileHash="a" * 64 + "\n")}},
             "平台 resources 项 fileHash 不是 64 位十六进制（str）"),
        )
        for label, entry, needle in cases:
            with self.subTest(case=label):
                with self.assertRaises(ns["Fail"]) as ctx:
                    ns["platform_resource_map"](entry, "单元表", valid_path)
                self.assertIn(needle, str(ctx.exception))
        self.assertEqual(ns["platform_resource_map"]({"resources": {RESOURCE_REL: good}},
                                                     "单元表", valid_path),
                         {RESOURCE_REL: (len(RESOURCE_BYTES), sha256_bytes(RESOURCE_BYTES))})
        for label, raw in (("空映射", {}), ("null", None)):
            with self.subTest(case=label):
                self.assertEqual(ns["platform_resource_map"]({"resources": raw}, "单元表",
                                                             valid_path), {})

    def test_resources_cli_is_never_launched_and_bytes_still_read_over_http(self):
        """两分支都不得启动 `skill resources`；资源 bytes 仍逐项经 HTTP 回读。"""
        fixture = self.fixture(name="meta-nocli-skill")
        stub = self.stub(fixture)
        write = Harness(fixture, http=stub)
        rc, out, err = write.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual([c[:2] for c in write.platform.calls],
                         [["skill", "view"], ["skill", "view"]],
                         "写路径 CLI 面：view ×2（install 已改官方 HTTP 写入）")
        self.assertEqual(stub.requests, sorted(fixture.resource_map()),
                         "每个候选资源恰一次 HTTP 读取（不以元数据判等代替逐字节比较）")
        other = self.fixture(name="meta-nocli-readonly-skill")
        candidate = pack_candidate(other)
        r_stub = self.stub(other)
        readonly = Harness(other, http=r_stub, pre_blob=candidate,
                           platform_kwargs={"pre_hash": sha256_bytes(candidate),
                                            "pre_content": other.body_text(),
                                            "pre_description": "夹具技能描述"})
        rc, out, err = readonly.run(other.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertIn("核验一致，未执行部署写入", out)
        self.assertEqual([c[:2] for c in readonly.platform.calls], [["skill", "view"]],
                         "只读分支的 CLI 面只有一次 view")
        self.assertEqual([c for c in readonly.platform.calls if c[1] == "resources"], [],
                         "只读分支同样不得启动 skill resources")
        self.assertEqual(r_stub.requests, sorted(other.resource_map()))


# ── O3：未变对象只读分支（只跳写入、不跳核验）──────────────────────────────────

class UnchangedObjectReadback(FixtureCase):
    """判据 15：现场 ZIP 哈希等于候选时仍完成全部核验，且零上传／零 install／零 edit。"""

    def unchanged_harness(self, fixture, **kwargs):
        """对齐现场 `zipFileHash` 与候选 ZIP sha256，使流程进入只读分支。"""
        candidate = pack_candidate(fixture)
        platform_kwargs = {"pre_hash": sha256_bytes(candidate),
                           "pre_content": fixture.body_text(),
                           "pre_description": "夹具技能描述"}
        platform_kwargs.update(kwargs.pop("platform_kwargs", {}))
        return Harness(fixture, pre_blob=candidate, platform_kwargs=platform_kwargs, **kwargs)

    def test_unchanged_object_verifies_everything_and_writes_nothing(self):
        fixture = self.fixture(name="unchanged-skill")
        expected = sorted(fixture.resource_map())
        stub = HttpStub(fixture.resource_map(), encoding={"references/binary.bin": "base64"})
        harness = self.unchanged_harness(fixture, http=stub)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertIn("核验一致，未执行部署写入", out)
        self.assertEqual(harness.platform.uploads(), 0, "零 R2 上传")
        self.assertEqual(harness.client.gets, [], "零 R2 读取（不下载回滚包）")
        self.assertEqual(harness.platform.installed_calls(), [], "零 install")
        self.assertEqual(harness.platform.edits(), [], "零 edit")
        self.assertNotIn("上传：key=", out)
        self.assertNotIn("安装：", out)
        self.assertEqual(stub.requests, expected, "资源 bytes 仍逐项核验（HTTP）")
        views = [c for c in harness.platform.calls if c[:2] == ["skill", "view"]]
        self.assertEqual(len(views), 1, "只读分支只回读一次平台对象")

    def assert_readonly_refusal(self, harness, rc, out, err, needle):
        """S2：未变分支失败必须**同时**零 R2 get／零上传／零 install／零 edit，且无成功文案。"""
        self.assertEqual(rc, 2, out + err)
        self.assertIn(needle, err)
        self.assertNotIn("核验一致，未执行部署写入", out, "不得报跳过成功")
        self.assertNotIn("上传：key=", out)
        self.assertNotIn("安装：", out)
        self.assertEqual(harness.platform.uploads(), 0, "零 R2 上传")
        self.assertEqual(harness.client.gets, [], "零 R2 读取（不下载回滚包）")
        self.assertEqual(harness.platform.installed_calls(), [], "零 install")
        self.assertEqual(harness.platform.edits(), [], "零 edit（只读分支不得用 edit 修补）")

    def test_unchanged_branch_drift_is_refused_without_edit(self):
        cases = (
            ("正文恰少一个尾 LF", "trim", "正文与候选 ZIP bytes 不等"),
            ("描述漂移", {"pre_description": "别的描述"}, "description"),
            ("同名不同 ID", {"entry_id": "skl_OtherFixture01"}, "未命中登记 ID"),
        )
        for label, over, needle in cases:
            with self.subTest(case=label):
                fixture = self.fixture(name="unchanged-drift-skill")
                platform_kwargs = ({"pre_content": fixture.body_text().rstrip("\n")}
                                   if over == "trim" else dict(over))
                stub = HttpStub(fixture.resource_map())
                harness = self.unchanged_harness(fixture, http=stub,
                                                 platform_kwargs=platform_kwargs)
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assert_readonly_refusal(harness, rc, out, err, needle)
                self.assertEqual(stub.requests, [], "核验在只读字段上失败，不应发起资源 HTTP")

    def test_unchanged_branch_resource_drift_is_refused(self):
        # ① bytes 漂移（HTTP runner 下的反控）：声明 size／hash 与候选一致、回放 bytes 不同
        fixture = self.fixture(name="unchanged-bytes-skill")
        rel = RESOURCE_REL
        real = fixture.resource_map()[rel]
        stub = HttpStub(fixture.resource_map(), serve={rel: real[:-1] + b"!"},
                        meta={rel: (len(real), sha256_bytes(real))})
        harness = self.unchanged_harness(fixture, http=stub)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assert_readonly_refusal(harness, rc, out, err, "阶段失败：只读核验")
        self.assertIn("资源 HTTP 回读失败：integrity", err)
        # ② 路径集漂移（HTTP runner 下的反控）：本分支只回读**部署前**那一次 view ⇒ 资源集取
        #    `before.resources`，故漂移注入在 `pre_resources` 上；路径集在发起任何资源 HTTP 前拒绝。
        fixture = self.fixture(name="unchanged-set-skill")
        extra = sorted(fixture.resource_map()) + ["references/extra.md"]
        stub = HttpStub(fixture.resource_map())
        harness = self.unchanged_harness(fixture, http=stub,
                                         platform_kwargs={"pre_resources": extra})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assert_readonly_refusal(harness, rc, out, err, "资源路径集不等")
        self.assertEqual(stub.requests, [], "路径集不等时不发起资源 HTTP")


class PhaseTiming(FixtureCase):
    """判据 16：分阶段 wall 计时只记阶段名／序号／耗时／rc／资源数量（不含 argv／URL）。"""

    PHASES = ("打包", "平台回读", "源端复核", "回滚包", "上传", "下载校验", "安装",
              "回读判等", "资源回读", "投后复核")

    def rows(self, out):
        table, total = {}, None
        for line in out.splitlines():
            if "计时：" not in line:
                continue
            parts = line.split("计时：", 1)[1].split("｜")
            self.assertGreaterEqual(len(parts), 4, line)
            if parts[0] == "总":
                total = parts
            else:
                table[parts[1]] = parts
        return table, total

    def test_timing_lines_carry_no_argv_or_url(self):
        fixture = self.fixture(name="timing-skill")
        stub = HttpStub(fixture.resource_map())
        harness = Harness(fixture, noisy=True, http=stub)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        table, total = self.rows(out)
        self.assertIsNotNone(total, out)
        for phase in self.PHASES:
            self.assertIn(phase, table, out)
            self.assertRegex(table[phase][2], r"^\d+\.\d{3}s$")
            self.assertRegex(table[phase][3], r"^rc=\d$")
            self.assertTrue(table[phase][4].startswith("资源="), table[phase])
        self.assertEqual(table["资源回读"][4], "资源=%d" % len(fixture.resource_map()))
        self.assertEqual([int(table[p][0]) for p in self.PHASES if p in table],
                         sorted(int(table[p][0]) for p in table), "序号须递增")
        self.assertNotIn(SECRET_MARKER, out + err, "计时不得外泄 SDK 标记")
        for line in out.splitlines():
            if "计时：" in line:
                self.assertNotIn("https", line, "计时行不得含 URL")
                self.assertNotIn("--repo", line, "计时行不得含完整 argv")
        # 同域不可证明的路径同样有「平台回读」阶段（口径一致），且**不进入写路径**（零上传）
        aborted = Harness(fixture, http=stub, http_env={})
        rc2, out2, err2 = aborted.run(fixture.args(deploy=True))
        self.assertEqual(rc2, 2, out2 + err2)
        self.assertIn("同域前置未通过", err2)
        self.assertEqual(aborted.platform.uploads(), 0)


# ── 复审 F1／F2／F3／F5：受控 CLI runner、启动异常分档、源端复核的假件 ─────────────

def approved_origin():
    """夹具的受批准 origin：**合成值**（真实 origin 在实现里只留 sha256；副本 pin 见
    `install_synthetic_pin`，不复制 HTTP 实现、不改生产 pin）。"""
    return SYNTH_ORIGIN


LH_ENV_STUB = '''#!%s
# 夹具桩（复审 F1／F2）：只记录调用面（argv／env 键与白名单值／HOME 列表／编译缓存形态），
# 并按 `skill view` 回放受控 JSON；不联网、不读凭据、不写仓库内文件。**不记** API key 的值。
import json, os, sys

LOG = %r
NAME = %r
EXPECT_ID = %r


def _cache_stat():
    """编译缓存目录的**形态**记录（存在性／模式／条目数／首层条目名），不记录任何内容 bytes。"""
    path = os.environ.get("NODE_COMPILE_CACHE")
    if not path:
        return {"set": False}
    row = {"set": True, "exists": os.path.isdir(path),
           "mode": ("%%o" %% (os.stat(path).st_mode & 0o777)) if os.path.isdir(path) else None}
    row["entries"] = sorted(os.listdir(path)) if os.path.isdir(path) else None
    return row


record = {"argv": sys.argv[1:], "argv0": sys.argv[0], "env_keys": sorted(os.environ),
          "values": dict((key, os.environ.get(key)) for key in (
              "PATH", "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
              "NODE_COMPILE_CACHE", "LOBEHUB_SERVER")),
          "compile_cache": _cache_stat(),
          "home_list": sorted(os.listdir(os.environ.get("HOME", "/")))}
with open(LOG, "a") as fh:
    fh.write(json.dumps(record, ensure_ascii=False) + "\\n")

args = sys.argv[1:]
if len(args) > 1 and args[0] == "skill" and args[1] == "view":
    entry = {"id": EXPECT_ID,
             "identifier": "url.fixture-account.r2.cloudflarestorage.com.fixture-bucket.%%s.zip"
                           %% NAME,
             "name": NAME, "description": "夹具技能描述", "content": "部署前正文\\n",
             "zipFileHash": "0" * 64,
             # 官方形态下 `resources` 恒在（本批起为**必需**字段）：空映射＝无资源
             "resources": {}}
    sys.stdout.write(json.dumps({"data": entry}, ensure_ascii=False))
sys.exit(0)
'''


class CompletedProc(object):
    """`subprocess.run` 的最小返回面（returncode／stdout／stderr）。"""

    def __init__(self, argv, rc, out, err):
        self.args = list(argv)
        self.returncode = rc
        self.stdout = out
        self.stderr = err


class CliProcessStub(object):
    """子进程桩（复审 F1／F3）：把假 CLI 的回答包成子进程结果，并按 verb 抛 `OSError`。

    只拦**冻结 runner 的 CLI 调用**（argv[0] 为解析出的绝对 `lh`）；`内置清单
    --inventory-only` 子进程仍走真实实现——被测入口的**两条**子进程路径因此都保留，且
    **不替换** `run_lh` 本身（复核 F1 所指的掩盖点）。
    """

    PIPE = subprocess.PIPE
    DEVNULL = subprocess.DEVNULL
    #: `run_lh` 的预算分支按名取该异常类（桩模块须与真实 `subprocess` 同面）
    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self, entry, platform, fail_verbs=(), fail_occurrence=None):
        self.entry = str(entry)
        self.platform = platform
        self.fail_verbs = tuple(fail_verbs)
        #: verb → {第几次出现（1 起算）}：只让**指定那一次**启动失败，其余照常（用于区分
        #: 「部署前 view」与「安装后 view」）
        self.fail_occurrence = dict(fail_occurrence or {})
        self.seen = {}
        self.calls = []

    def run(self, argv, **kwargs):
        argv = list(argv)
        if argv and argv[0] == self.entry:
            verb = argv[2] if len(argv) > 2 else ""
            self.calls.append((argv, dict(kwargs.get("env") or {})))
            self.seen[verb] = self.seen.get(verb, 0) + 1
            nth = self.fail_occurrence.get(verb)
            if verb in self.fail_verbs or (nth is not None and self.seen[verb] in nth):
                raise OSError("桩：模拟 lh 启动失败")
            rc, out, err = self.platform(argv[1:])
            return CompletedProc(argv, rc, out, err)
        return subprocess.run(argv, **kwargs)

    def envs(self):
        return [env for _argv, env in self.calls]

    def verbs(self):
        return [argv[2] if len(argv) > 2 else "" for argv, _env in self.calls]


class FakeTime(object):
    """假 `time` 模块（复审 F2）：`monotonic` 手动推进、`sleep` 只推进**不真睡**。

    用于断言「单次读 12 s」这类形态：读取本身消耗假时钟，而测试总时长不变。
    """

    def __init__(self, start=2000.0):
        self.now = start

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def tick(self, seconds):
        self.now += seconds


class FrozenCliRunner(FixtureCase):
    """复审 F1／F2：受控 CLI runner 的**子进程级**证据（真解析、真 runner、桩 `lh` 记录调用面）。

    用例**不替换** `run_lh`：跑的是真实入口子进程，桩只回答 `skill view` 并把 argv／env／HOME
    如实记下来。冻结通过后流程按既有顺序推进到 SDK 边界（夹具毒化 boto3 ⇒ rc=2）。
    """

    ENV_KEYS = ("PATH", "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                "NODE_COMPILE_CACHE", "LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY")
    APPROVED_DIRS = ("/usr/local/bin", "/usr/bin", "/bin")

    def run_deploy_subprocess(self, fixture, extra_env, lh_stub=True):
        """真跑一次 `--deploy`；返回 (CompletedProcess, 桩记录)。"""
        log = fixture.write_env_lh_stub()
        env = {"LUNO_DEPLOY_AUTHORIZED": "1", "CF_ACCOUNT_ID": "fixture-account",
               "R2_BUCKET": "fixture-bucket", "R2_ACCESS_KEY_ID": "fixture-key-id",
               "R2_SECRET_ACCESS_KEY": SECRET_MARKER,
               "HTTP_PROXY": "http://decoy.invalid:3128"}
        env.update(extra_env)
        cp = fixture.run_tool(fixture.args(deploy=True), extra_env=env, lh_stub=lh_stub)
        return cp, fixture.env_lh_records(log)

    def interpreter_noise(self, fixture):
        """控制组：用**最小 env** 直接跑同一个桩，取解释器包装器自带变量（与本入口无关）。

        本机 iSH 的 `python3` 是包装器脚本，会自带若干变量（如 `PYTHONMALLOC`）；这些不是
        本入口注入的，故以控制组扣除后再断言「env 只含白名单变量」——断言因此不是空转。
        """
        log = fixture.root / "lh-probe.log"
        write_file(fixture.bin / "lh-probe",
                   LH_ENV_STUB % (sys.executable, str(log), fixture.name, fixture.expect_id),
                   mode=0o755)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(fixture.root)}
        subprocess.run([str(fixture.bin / "lh-probe"), "probe"], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        recs = fixture.env_lh_records(log)
        self.assertTrue(recs, "控制组须真的跑起来（否则下面的扣除会掩盖真实继承）")
        return set(recs[0]["env_keys"]) - set(env)

    def test_cli_child_env_is_frozen_and_home_is_empty(self):
        fixture = self.fixture(name="frozen-env-skill")
        fixture.write_persisted_config()          # HOME 下的「别处身份」干扰项
        noise = self.interpreter_noise(fixture)
        cp, records = self.run_deploy_subprocess(
            fixture, {"LOBEHUB_SERVER": approved_origin(), "LOBEHUB_CLI_API_KEY": FROZEN_KEY})
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("阶段失败：SDK", err, "冻结通过后按既有顺序推进到 SDK 边界")
        self.assertEqual(len(records), 1, "冻结通过时恰一次 CLI 调用（skill view）")
        rec = records[0]
        self.assertEqual(rec["argv0"], str(fixture.bin / "lh"), "argv[0] 是解析出的**绝对**路径")
        self.assertEqual(sorted(set(rec["env_keys"]) - noise), sorted(self.ENV_KEYS),
                         "CLI 子进程 env 只含白名单变量（差值＝解释器包装器自带变量）")
        for key in ("LOBEHUB_WORKSPACE_ID", "HTTP_PROXY", "PYTHONPATH",
                    "LUNO_DEPLOY_AUTHORIZED", "R2_SECRET_ACCESS_KEY", "CF_ACCOUNT_ID"):
            self.assertNotIn(key, rec["env_keys"], "不得继承 %s" % key)
        self.assertEqual(rec["values"]["LOBEHUB_SERVER"], approved_origin())
        self.assertNotEqual(rec["values"]["HOME"], str(fixture.root), "不得用调用方 HOME")
        self.assertEqual(sorted(rec["home_list"]), sorted(["cfg", "cache", "data"]),
                         "空 HOME/XDG：不读持久化配置（恰好三个空目录）")
        for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            self.assertTrue(rec["values"][key].startswith(rec["values"]["HOME"] + os.sep), key)
        dirs = [p for p in rec["values"]["PATH"].split(os.pathsep) if p]
        self.assertNotIn("shims", dirs, "PATH 须排除 shim 目录")
        self.assertTrue(set(dirs) <= set(self.APPROVED_DIRS), rec["values"]["PATH"])
        self.assertFalse(os.path.exists(rec["values"]["HOME"]),
                         "收尾（含异常路径）须删除临时 HOME/XDG")

    def test_unset_server_stops_before_cli_sdk_and_writes(self):
        """缺 `LOBEHUB_SERVER`（无内置默认）：固定分类停止——零 CLI／零 SDK／零写入，错误写出变量名。"""
        fixture = self.fixture(name="default-server-skill")
        cp, records = self.run_deploy_subprocess(fixture, {"LOBEHUB_CLI_API_KEY": FROZEN_KEY})
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertEqual(records, [], "缺 server 时不得调用 CLI")
        self.assertIn("LOBEHUB_SERVER", out + err, "日志/错误须写出变量名（值不写）")
        self.assertNotIn(approved_origin(), out + err, "错误不得含任何值")
        self.assertFalse(fixture.sdk_imported(), "零 SDK ⇒ 零 R2 读取／上传")
        self.assertFalse(fixture.rollback().exists(), "零写入")

    def test_unresolvable_launcher_stops_before_platform(self):
        fixture = self.fixture(name="no-lh-skill")
        empty = fixture.root / "empty-path"
        empty.mkdir()
        cp, records = self.run_deploy_subprocess(
            fixture, {"LOBEHUB_SERVER": approved_origin(), "LOBEHUB_CLI_API_KEY": FROZEN_KEY,
                      "PATH": str(empty)}, lh_stub=False)
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("无法解析 lh 启动器", err)
        self.assertEqual(records, [])
        self.assertFalse(fixture.sdk_imported(), "零 SDK ⇒ 零 R2 读取／上传")
        self.assertFalse(fixture.rollback().exists())

    def test_unprovable_same_origin_never_touches_platform_or_storage(self):
        cases = (
            ("缺指定 key", {}),
            ("key 含非法字符", {"LOBEHUB_SERVER": approved_origin(),
                                "LOBEHUB_CLI_API_KEY": "bad key\n"}),
            ("origin 不符", {"LOBEHUB_SERVER": "https://untrusted.invalid",
                             "LOBEHUB_CLI_API_KEY": FROZEN_KEY}),
            ("显式 workspace", {"LOBEHUB_SERVER": approved_origin(),
                                "LOBEHUB_CLI_API_KEY": FROZEN_KEY,
                                "LOBEHUB_WORKSPACE_ID": "ws-fixture"}),
        )
        for label, env in cases:
            with self.subTest(case=label):
                fixture = self.fixture(name="stop-skill")
                cp, records = self.run_deploy_subprocess(fixture, env)
                out, err = text_of(cp)
                self.assertEqual(cp.returncode, 2, "%s: %s" % (label, out + err))
                self.assertIn("阶段失败：平台回读", err)
                self.assertIn("同域前置未通过；停止本次部署，未执行平台或存储写入", err)
                self.assertEqual(records, [], "零 CLI 调用（未执行 lh）")
                self.assertFalse(fixture.sdk_imported(), "零 SDK ⇒ 零 R2 读取／上传")
                self.assertFalse(fixture.rollback().exists(), "不得写回滚包")
                self.assertEqual(fixture.artifacts(), ["stop-skill.zip"],
                                 "只允许本地候选包；无回滚包／无其它产物")
                self.assertNotIn(FROZEN_KEY, out + err, "key 值不外流")

    def test_frozen_runner_ignores_later_environment_changes(self):
        """冻结后环境变化（含 PATH／server／key）不得改变已冻结的 argv／env。"""
        fixture = self.fixture(name="frozen-later-skill")
        mutated = []

        def mutate(_args):
            if mutated:
                return
            mutated.append(True)
            os.environ["LOBEHUB_CLI_API_KEY"] = "changed-later"
            os.environ["LOBEHUB_SERVER"] = "https://changed.invalid"
            os.environ["PATH"] = "/nonexistent"

        harness = Harness(fixture, patch_lh=False, platform_kwargs={"on_call": mutate})
        stub = CliProcessStub(str(fixture.bin / "lh"), harness.platform)
        harness.ns["subprocess"] = stub
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(stub.calls), 2,
                         "本批起写路径的 CLI 面只有 view ×2（install／edit 改官方 HTTP 写入）；"
                         "写入真的发生 ⇒ 断言非空转")
        self.assertTrue(mutated, "变异钩子须已触发")
        first = stub.envs()[0]
        self.assertEqual(first["LOBEHUB_SERVER"], HttpStub.ORIGIN)
        self.assertEqual(first["LOBEHUB_CLI_API_KEY"], FROZEN_KEY)
        for env in stub.envs():
            self.assertEqual(env, first, "冻结后每次调用都用同一 env")
        for argv, _env in stub.calls:
            self.assertEqual(argv[0], str(fixture.bin / "lh"), "argv[0] 恒为冻结的绝对路径")
        self.assertFalse(os.path.exists(first["HOME"]), "收尾删除临时 HOME/XDG")


class RunnerCompileCache(FixtureCase):
    """本批（CLI 启动开销）：CLI 子进程得到**运行期私有**的 `NODE_COMPILE_CACHE` 目录。

    判据：值与 HOME 同属本次运行的临时根、目录名固定、模式 0700、**首次调用时为空**（不复用上
    一轮的缓存）、收尾随临时根删除且不与 HOME/XDG 混放。变异（删掉注入该变量的 env 行）必须让
    同一组判据变红 ⇒ 断言非空转。该变量只影响 Node 自身的模块编译缓存：不改变 CLI 的 rc／
    stdout，缓存写不进也不吞业务错误（Node 侧失败语义的离线实测见本批 `artifacts/`）。
    """

    CACHE_DIRNAME = "compilecache"
    ENV_LINE = '            if self.compile_cache is not None:\n' \
               '                self.env["NODE_COMPILE_CACHE"] = self.compile_cache\n'
    #: 缓存目录**建不出来**的注入点：进程内 `os.mkdir` 桩与真子进程 `sitecustomize` 桩都用叶子名匹配
    FAULT_LEAF = "compilecache"

    def cache_problems(self, env, stat):
        """正控与变异体共用的判据：返回问题列表（空＝通过）。"""
        path = env.get("NODE_COMPILE_CACHE")
        home = env.get("HOME") or ""
        if not path:
            return ["未注入 NODE_COMPILE_CACHE"]
        problems = []
        if os.path.basename(path) != self.CACHE_DIRNAME:
            problems.append("缓存目录名不符")
        if os.path.dirname(path) != os.path.dirname(home):
            problems.append("缓存目录不在本次运行的临时根内")
        if not stat.get("exists"):
            problems.append("缓存目录不存在")
        if stat.get("mode") != "700":
            problems.append("缓存目录模式不是 0700（%s）" % stat.get("mode"))
        if stat.get("entries") != []:
            problems.append("首次调用时缓存目录非空（可能复用了上一轮）")
        return problems

    def deploy_once(self, fixture, extra_env):
        """真跑一次 `--deploy`（桩 `lh` 记录调用面）；返回 (CompletedProcess, 记录)。"""
        log = fixture.write_env_lh_stub()
        env = {"LUNO_DEPLOY_AUTHORIZED": "1", "CF_ACCOUNT_ID": "fixture-account",
               "R2_BUCKET": "fixture-bucket", "R2_ACCESS_KEY_ID": "fixture-key-id",
               "R2_SECRET_ACCESS_KEY": SECRET_MARKER,
               "HTTP_PROXY": "http://decoy.invalid:3128"}
        env.update(extra_env)
        cp = fixture.run_tool(fixture.args(deploy=True), extra_env=env)
        return cp, fixture.env_lh_records(log)

    def test_compile_cache_is_private_to_this_run(self):
        fixture = self.fixture(name="compile-cache-skill")
        cp, records = self.deploy_once(fixture, {"LOBEHUB_SERVER": approved_origin(),
                                                 "LOBEHUB_CLI_API_KEY": FROZEN_KEY})
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertEqual(len(records), 1, "冻结通过时恰一次 CLI 调用（skill view）")
        rec = records[0]
        problems = self.cache_problems(rec["values"], rec.get("compile_cache") or {})
        self.assertEqual(problems, [], "；".join(problems))
        self.assertNotIn(self.CACHE_DIRNAME, rec["home_list"],
                         "缓存目录不与 HOME/XDG 混放（HOME 仍恰三个空目录）")
        self.assertFalse(os.path.exists(os.path.dirname(rec["values"]["HOME"])),
                         "收尾须删除含编译缓存的临时根")

    def test_removing_the_injection_line_turns_the_checks_red(self):
        """负控：删掉注入行后同一判据必须失败，且判据不因此改口（仍余 0 个业务副作用）。"""
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn(self.ENV_LINE, source, "变异前须存在待删片段")
        mutant = source.replace(self.ENV_LINE, "")
        self.assertNotEqual(mutant, source, "变异须确实改变字节（否则本用例空转）")
        ns = load_source_namespace(mutant)
        runner = ns["CliRunner"](["/bin/true"], approved_origin(), FROZEN_KEY)
        try:
            problems = self.cache_problems(dict(runner.env), {})
        finally:
            runner.close()
        self.assertEqual(problems, ["未注入 NODE_COMPILE_CACHE"],
                         "删掉注入行后判据必须变红：%s" % problems)


    def test_compile_cache_mkdir_failure_degrades_to_no_cache(self):
        """纯优化降级（进程内）：缓存目录建不出来 ⇒ 只省略该变量，CLI env／部署能力不变。"""
        scratch = self.work / "cache-fault"
        scratch.mkdir()
        ns = load_tool_namespace()
        real_mkdtemp, real_mkdir = tempfile.mkdtemp, os.mkdir
        roots = []

        def mkdtemp(prefix="tmp", dir=None):
            root = real_mkdtemp(prefix=prefix, dir=str(scratch))
            roots.append(root)
            return root

        def mkdir(path, *args, **kwargs):
            if os.path.basename(str(path)) == self.FAULT_LEAF:
                raise OSError("injected cache fault")
            return real_mkdir(path, *args, **kwargs)

        with mock.patch.object(tempfile, "mkdtemp", mkdtemp), \
                mock.patch.object(os, "mkdir", mkdir):
            runner = ns["CliRunner"](["/nonexistent/lh"], approved_origin(), FROZEN_KEY)
        try:
            self.assertEqual(len(roots), 1, "注入须在今次构造里命中（否则用例空转）")
            self.assertIsNone(runner.compile_cache, "建不出来须降级为无缓存")
            self.assertNotIn("NODE_COMPILE_CACHE", runner.env, "降级须真的省略该变量")
            for key in ns["CliRunner"].ENV_KEYS:
                if key not in ns["CliRunner"].OPTIONAL_ENV_KEYS:
                    self.assertIn(key, runner.env, "其余白名单键不得缺失：%s" % key)
            self.assertTrue(os.path.isdir(runner.home), "HOME 仍应建成功")
            self.assertEqual(sorted(os.listdir(runner.home)), ["cache", "cfg", "data"])
        finally:
            runner.close()
        self.assertFalse(os.path.lexists(roots[0]), "降级路径收尾同样须删除临时根")
        self.assertTrue(runner.cleaned)

    def test_process_level_compile_cache_failure_keeps_deploy_flow(self):
        """真入口子进程：缓存目录故障下部署仍按原路径推进（不吞业务错误、不改结论）。"""
        fixture = self.fixture(name="cache-fault-skill")
        log = fixture.root / "created-roots.log"
        write_file(fixture.poison / "sitecustomize.py", RUNNER_FAULT_SITECUSTOMIZE)
        cp, records = self.deploy_once(fixture, {
            "LOBEHUB_SERVER": approved_origin(), "LOBEHUB_CLI_API_KEY": FROZEN_KEY,
            "FIXTURE_CREATED_LOG": str(log), "FIXTURE_FAULT_STAGE": self.FAULT_LEAF})
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 2, out + err)
        self.assertIn("阶段失败：SDK", err, "优化降级不得改变流程推进到的同一阶段")
        self.assertNotIn("injected cache fault", err, "不得回显原始异常")
        self.assertIn("编译缓存不可用（已省略，不影响 CLI 结果）", out)
        self.assertEqual(len(records), 1, "冻结通过时仍恰一次 CLI 调用（skill view）")
        rec = records[0]
        self.assertFalse((rec.get("compile_cache") or {}).get("set"),
                         "故障注入下缓存变量须被省略")
        self.assertNotIn("NODE_COMPILE_CACHE", rec["env_keys"])
        for key in ("PATH", "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                    "LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY"):
            self.assertIn(key, rec["env_keys"], "其余白名单键不得缺失：%s" % key)
        roots = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(len(roots), 1, "注入须真的命中（否则用例空转）")
        self.assertFalse(os.path.exists(roots[0]), "临时根仍须回收")
        self.assertFalse(fixture.rollback().exists(), "零 R2 读取／上传 ⇒ 无回滚包")
        self.assertEqual(fixture.artifacts(), ["cache-fault-skill.zip"], "只允许本地候选包")


#: N1 进程级注入：只在夹具的**毒化 PYTHONPATH 目录**里放一份 `sitecustomize.py`（不改被测入口）。
#:   · 记录 `tempfile.mkdtemp` 返回的临时根（供「无残留」断言）；
#:   · 仅当**父目录含 `deploy-lh-`**（＝本入口的受控 CLI 临时根）且叶子名等于注入阶段时让
#:     `os.mkdir` 抛 `OSError` —— `mkdtemp` 自身的 `mkdir` 与其它路径都不受影响。
RUNNER_FAULT_SITECUSTOMIZE = '''# -*- coding: utf-8 -*-
import os
import tempfile

LOG = os.environ["FIXTURE_CREATED_LOG"]
STAGE = os.environ["FIXTURE_FAULT_STAGE"]
_mkdtemp, _mkdir = tempfile.mkdtemp, os.mkdir


def mkdtemp(*args, **kwargs):
    root = _mkdtemp(*args, **kwargs)
    with open(LOG, "a") as fh:
        fh.write(root + "\\n")
    return root


def mkdir(path, *args, **kwargs):
    text = str(path)
    if "deploy-lh-" in os.path.dirname(text) and os.path.basename(text) == STAGE:
        raise OSError("injected construction fault")
    return _mkdir(path, *args, **kwargs)


tempfile.mkdtemp = mkdtemp
os.mkdir = mkdir
'''


class RunnerConstructionCleanup(FixtureCase):
    """N1：`CliRunner` **构造中途**失败必须回收已建临时目录。

    此刻 runner 尚未赋值给 `RUNNER`，外层 `release_cli_runner()` 看不到它——故清理只能由
    `CliRunner.__init__` 自己兜底。注入点：HOME 创建／各 XDG 子目录创建（进程内，真类真清理）与
    真实入口子进程的同一构造（真子进程、真文件系统）。
    """

    FAULT_TARGETS = ("home", "cfg", "data", "cache")

    def observed_construction(self, scratch, target=None, env_fault=False, freeze=False):
        """在受控 scratch 里真跑一次构造；返回 (异常, 临时根记录, rmtree 记录, subprocess.run 桩)。

        `target`：注入失败的叶子名（`None` 且 `env_fault=True` 时改在 env 构造阶段注入）。
        """
        ns = load_tool_namespace()
        records = []
        real_mkdtemp, real_mkdir = tempfile.mkdtemp, os.mkdir

        def mkdtemp(prefix="tmp", dir=None):
            root = real_mkdtemp(prefix=prefix, dir=str(scratch))
            records.append(root)
            return root

        def mkdir(path, *args, **kwargs):
            if os.path.basename(str(path)) == target:
                raise OSError("injected fs fault: %s" % target)
            return real_mkdir(path, *args, **kwargs)

        def boom():
            raise OSError("injected fs fault: env")

        ns["RUNNER"] = None                    # 真实初值：构造失败后必须仍是 None
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(tempfile, "mkdtemp", mkdtemp))
            stack.enter_context(mock.patch.object(os, "mkdir", mkdir))
            rmtree = stack.enter_context(mock.patch.object(shutil, "rmtree", wraps=shutil.rmtree))
            run_mock = stack.enter_context(mock.patch.object(subprocess, "run"))
            stack.enter_context(mock.patch.dict(ns, {"controlled_path": boom} if env_fault else {}))
            if freeze:
                stack.enter_context(mock.patch.dict(ns, {"env_get": self.fake_env_get}))
            try:
                if freeze:
                    ns["freeze_cli_runner"]("ht-approved-origin", "frozen-key-value")
                else:
                    ns["CliRunner"](["/nonexistent/lh"], "ht-approved-origin", "frozen-key-value")
            except BaseException as exc:                      # noqa: BLE001 —— 观察面就是它
                return exc, records, rmtree, run_mock, ns
            raise AssertionError("注入的构造失败须真的抛出（否则用例空转）")

    def assert_cleaned_without_touching_platform(self, scratch, exc, records, rmtree, run_mock):
        """共同断言：真抛出、临时根被回收、无残留、未跑任何子进程（⇒ 零 CLI／零平台／零存储）。"""
        self.assertIsInstance(exc, OSError, "构造失败原样抛出（分类在外层做）")
        self.assertIn("injected", str(exc), "须是夹具注入的故障，不是别的错误")
        self.assertEqual(len(records), 1, "恰建一个临时根")
        self.assertIn(records[0], [str(call.args[0]) for call in rmtree.call_args_list],
                      "清理须被调用（`shutil.rmtree(root, …)`）")
        self.assertFalse(os.path.exists(records[0]), "临时根须被删除")
        self.assertEqual(sorted(os.listdir(str(scratch))), [], "TMPDIR 内不得残留任何目录")
        run_mock.assert_not_called()

    def test_in_process_construction_failure_cleans_temp_root(self):
        for target in self.FAULT_TARGETS:
            with self.subTest(case="XDG／HOME 子目录：%s" % target):
                scratch = self.work / ("scratch-%s" % target)
                scratch.mkdir()
                exc, records, rmtree, run_mock, _ns = self.observed_construction(
                    scratch, target=target)
                self.assert_cleaned_without_touching_platform(scratch, exc, records, rmtree,
                                                              run_mock)

    def test_in_process_env_construction_failure_cleans_temp_root(self):
        scratch = self.work / "scratch-env"
        scratch.mkdir()
        exc, records, rmtree, run_mock, _ns = self.observed_construction(
            scratch, env_fault=True)
        self.assert_cleaned_without_touching_platform(scratch, exc, records, rmtree, run_mock)

    def fake_env_get(self, name, default=None):
        """冻结路径只用到 `PATH`：给一个含桩 `lh` 的最小目录，其余回落到原语义。"""
        if name == "PATH":
            return str(self.lh_bin)
        return default

    def test_freeze_failure_keeps_fixed_classification_and_no_raw_exception(self):
        """外层 `freeze_cli_runner` 的固定分类与文案不变：rc=2 且**不回显**原始异常。"""
        self.lh_bin = self.work / "lh-bin"
        self.lh_bin.mkdir()
        write_file(self.lh_bin / "lh", "#!/bin/sh\nexit 0\n", mode=0o755)
        scratch = self.work / "scratch-freeze"
        scratch.mkdir()
        exc, records, rmtree, run_mock, ns = self.observed_construction(
            scratch, target="home", freeze=True)
        self.assertIsInstance(exc, ns["Fail"], "外层按固定分类包装（不是裸 OSError）")
        self.assertEqual(exc.stage, ns["STAGE_PLATFORM"])
        self.assertEqual(exc.rc, 2)
        self.assertIn("无法建立受控 CLI 环境（OSError）", exc.detail)
        self.assertIn("同域前置未通过；停止本次部署，未执行平台或存储写入", exc.detail)
        self.assertNotIn("injected fs fault", exc.detail, "不得回显原始异常")
        self.assertIsNone(ns["RUNNER"], "构造失败不得留下半成品 runner")
        self.assertEqual(len(records), 1)
        self.assertFalse(os.path.exists(records[0]), "固定分类失败同样须回收临时根")
        run_mock.assert_not_called()

    def test_process_level_construction_failure_leaves_no_temp_root(self):
        """真入口子进程：构造中途失败 ⇒ rc=2、无残留，零 CLI 调用、零 SDK（⇒ 零 R2）。"""
        for label, stage in (("HOME 创建", "home"), ("XDG cache 创建", "cache")):
            with self.subTest(case=label):
                fixture = self.fixture(name="runner-fault-skill")
                log = fixture.root / ("created-roots-%s.log" % stage)
                write_file(fixture.poison / "sitecustomize.py", RUNNER_FAULT_SITECUSTOMIZE)
                env = {"LUNO_DEPLOY_AUTHORIZED": "1", "CF_ACCOUNT_ID": "fixture-account",
                       "R2_BUCKET": "fixture-bucket", "R2_ACCESS_KEY_ID": "fixture-key-id",
                       "R2_SECRET_ACCESS_KEY": SECRET_MARKER,
                       "LOBEHUB_SERVER": approved_origin(),
                       "LOBEHUB_CLI_API_KEY": FROZEN_KEY,
                       "FIXTURE_CREATED_LOG": str(log), "FIXTURE_FAULT_STAGE": stage}
                cp = fixture.run_tool(fixture.args(deploy=True), extra_env=env)
                out, err = text_of(cp)
                self.assertEqual(cp.returncode, 2, out + err)
                self.assertIn("阶段失败：平台回读", err)
                self.assertIn("无法建立受控 CLI 环境（OSError）", err)
                self.assertIn("同域前置未通过；停止本次部署，未执行平台或存储写入", err)
                self.assertNotIn("injected construction fault", err, "不得回显原始异常")
                self.assertNotIn("Traceback", err)
                roots = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
                self.assertEqual(len(roots), 1, "注入须真的在构造中途命中（否则用例空转）")
                self.assertFalse(os.path.exists(roots[0]), "构造失败须回收临时根：%s" % roots[0])
                self.assertEqual([p.name for p in fixture.root.glob("deploy-lh-*")], [],
                                 "TMPDIR 内不得残留 deploy-lh-* 目录")
                self.assertEqual(fixture.lh_calls(), [], "零 CLI 调用 ⇒ 零平台访问")
                self.assertFalse(fixture.sdk_imported(), "零 SDK ⇒ 零 R2 读取／上传")
                self.assertFalse(fixture.rollback().exists(), "不得写回滚包")
                self.assertEqual(fixture.artifacts(), ["runner-fault-skill.zip"],
                                 "只允许本地候选包；无回滚包／无其它产物")


class HttpWritePath(FixtureCase):
    """本批（写入面迁移）：install／edit 走**官方 HTTP tRPC mutation**，CLI 不再承载写业务。

    判据（逐项独立可失败）：
      a 请求面：`POST /trpc/lambda/agentSkills.<importFromUrl|update>`，体 `{"json": payload}`
        （纯 string 无 SuperJSON meta），头 `X-API-Key`（冻结 key）／`Content-Type: application/json`
        ／`User-Agent: curl/8.7.1`／`Connection: close`，host 为受批准 origin；
      b 响应体**有界读**（≤64 KB、分片 ≤8 KiB）后解析 tRPC 信封，连接随即关闭；出现 `error`
        即失败、200 但非 `result` 形态同样失败，日志只带 `status` 与错误 `code`；
      c 非 200（401／403／429／500／302）／200 但 `Content-Type` 非 json（反代中介页）／传输异常
        ⇒ 固定分类失败、回显不含响应体／URL／header 与合成秘密标记；非 200 与中介页**不读体**；
        `install` 任何失败都**恰一次请求**（不重试）；
      d **HTTP 200 不代表成功**：写入返回 200 但未生效时，成功与否仍由随后的**完整白名单 view
        回读**判定（判失败）；
      e 未变对象只读分支**零 HTTP 写**；
      f CLI 面恰为 view ×2（写入不再启动 CLI）；
      g 只认两个冻结 procedure：未声明 kind 直接固定分类失败且**零请求**（不泛化成通用 router 工具）。

    负控：响应体上限失效（把 `WRITE_BODY_LIMIT` 放大）后同一超界响应体会被接受 ⇒ 该判据变红
    （见 `test_oversized_envelope_is_refused_and_cap_is_not_vacuous`）。
    """

    PROC = {"install": "agentSkills.importFromUrl", "edit": "agentSkills.update"}

    def check_request(self, harness, kind, payload):
        """请求面逐项断言（method／路径／体／头；不回显任何值时只比较，不落盘）。"""
        record = harness.write_stub.requests[-1]
        self.assertEqual(record["kind"], kind)
        self.assertEqual(record["method"], "POST")
        self.assertEqual(record["target"], "/trpc/lambda/%s" % self.PROC[kind])
        self.assertEqual(json.loads(record["body"].decode("utf-8")), {"json": payload})
        headers = record["headers"]
        self.assertEqual(headers.get("X-API-Key"), FROZEN_KEY)
        self.assertEqual(headers.get("Content-Type"), "application/json")
        self.assertEqual(headers.get("User-Agent"), "curl/8.7.1")
        self.assertEqual(headers.get("Connection"), "close")
        self.assertEqual(str(headers.get("Content-Length")), str(len(record["body"])))
        host, timeout = harness.write_stub.connects[-1]
        self.assertEqual(host, urlsplit(HttpStub.ORIGIN).hostname, "写入打受批准 origin")
        self.assertTrue(0 < timeout <= 60, "socket 超时须有界（实测 %r）" % (timeout,))
        return record

    def test_install_request_matches_frozen_official_shape(self):
        fixture = self.fixture(name="http-install-skill")
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(harness.write_stub.requests), 1, "写得恰一次（不重试）")
        url = harness.urlopen.urls[0]
        self.check_request(harness, "install", {"url": url})
        self.assertTrue(0 < harness.write_stub.bytes_read <= 64 * 1024,
                        "响应体须**有界**读（只到信封）：实测 %d B" % harness.write_stub.bytes_read)
        self.assertLessEqual(max(harness.write_stub.requested), 8192,
                             "分片读取，单次请求量不超 8 KiB")
        self.assertEqual(harness.write_stub.connections_closed(), 1, "连接须关闭")
        self.assertEqual([c[:2] for c in harness.platform.calls],
                         [["skill", "view"], ["skill", "view"]],
                         "CLI 面恰为 view ×2（写入不启动 CLI）")
        self.assertIn("请求已返回，待完整回读判等", out, "只承诺请求已返回，不报安装成功")
        self.assertNotIn(url, out + err, "预签名 URL 不得进日志")

    def test_edit_request_carries_frozen_id_and_body(self):
        fixture = self.fixture(name="http-edit-skill")
        harness = Harness(fixture)
        want = fixture.body_text()
        harness.platform.post_content = want.rstrip("\n")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual([w["kind"] for w in harness.write_stub.requests], ["install", "edit"])
        self.check_request(harness, "edit", {"id": fixture.expect_id, "content": want})
        self.assertTrue(0 < harness.write_stub.bytes_read <= 64 * 1024, "两次写入体均有界读")
        self.assertEqual(harness.write_stub.connections_closed(), 2, "两次写入各自关闭连接")
        self.assertEqual(harness.platform.content, want, "补写后完整回读判等通过")

    def test_default_write_connector_is_stdlib_https(self):
        """写入出口的真实单点＝标准库 `http.client.HTTPSConnection`（只建对象，不连接）。"""
        ns = load_tool_namespace()
        conn = ns["https_connection"](SYNTH_WRITE_HOST, 1.0)
        self.assertIsInstance(conn, http.client.HTTPSConnection)
        self.assertEqual(conn.host, SYNTH_WRITE_HOST)
        conn.close()

    def test_non_200_is_fixed_failure_without_retry_or_body_echo(self):
        for status in (401, 403, 429, 500, 302):
            with self.subTest(status=status):
                fixture = self.fixture(name="http-status-skill")
                harness = Harness(fixture, http_writes={"install": {"status": status}})
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, out + err)
                self.assertIn("阶段失败：安装", err)
                self.assertIn("官方写入未返回 200（status=%d）" % status, err)
                self.assertIn("不重试", err)
                self.assertEqual(len(harness.write_stub.requests), 1, "不得重试")
                self.assertEqual(harness.write_stub.connects, [(urlsplit(HttpStub.ORIGIN).hostname,
                                                                30.0)], "同一有界超时、只连一次")
                self.assertEqual(harness.write_stub.reads, 0, "失败路径同样不读响应体")
                self.assertEqual(harness.write_stub.connections_closed(), 1)
                self.assertNotIn(SECRET_MARKER, out + err)
                self.assertNotIn("X-API-Key", out + err, "header 名与外泄现场不得回显")
                table, _total = PhaseTiming.rows(self, out)
                self.assertEqual(table["安装"][3], "rc=1", "安装阶段如实显示失败 rc")

    def test_200_html_intermediary_page_is_refused(self):
        fixture = self.fixture(name="http-html-skill")
        harness = Harness(fixture, http_writes={"install": {"status": 200,
                                                           "content_type": "text/html; charset=utf-8"}})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：安装", err)
        self.assertIn("Content-Type 非 json", err)
        self.assertFalse(harness.platform.installed, "中介页不得被当成安装生效")
        self.assertEqual(harness.write_stub.reads, 0)

    def test_json_substring_in_non_json_mime_is_refused(self):
        for ctype in ("text/html; note=json", "application/jsonp"):
            with self.subTest(content_type=ctype):
                fixture = self.fixture(name="http-mime-skill")
                harness = Harness(fixture, http_writes={"install": {"status": 200,
                                                                   "content_type": ctype}})
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, out + err)
                self.assertIn("Content-Type 非 json", err)
                self.assertEqual(harness.write_stub.reads, 0)
                self.assertEqual(len(harness.write_stub.requests), 1)

    def test_transport_exception_is_fixed_failure_without_retry(self):
        import socket as socket_mod
        for exc in (ConnectionResetError("raw upstream text %s" % SECRET_MARKER),
                    socket_mod.timeout("raw timeout text %s" % SECRET_MARKER),
                    http.client.RemoteDisconnected("raw disconnect %s" % SECRET_MARKER)):
            with self.subTest(exception=type(exc).__name__):
                fixture = self.fixture(name="http-transport-skill")
                harness = Harness(fixture, http_writes={"install": {"exception": exc}})
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, out + err)
                self.assertIn("阶段失败：安装", err)
                self.assertIn("官方写入请求异常（%s）" % type(exc).__name__, err)
                self.assertIn("不重试、不改用 CLI 重复写", err)
                self.assertNotIn(SECRET_MARKER, out + err, "不得回显原始异常正文")
                self.assertEqual(len(harness.write_stub.requests), 1, "不得重试")
                self.assertEqual(harness.write_stub.connections_closed(), 1, "异常路径也须关闭连接")

    def test_200_without_effect_is_rejected_by_the_full_readback(self):
        """`d`：HTTP 200 只表请求已返回——写入未生效时由**完整白名单回读**判失败。"""
        fixture = self.fixture(name="http-noop-skill")
        harness = Harness(fixture)
        harness.platform.apply_writes = False       # 200 但平台状态不变（未生效）
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("请求已返回，待完整回读判等", out, "200 只报请求已返回")
        self.assertNotIn("回读判等：id／zipFileHash／name／description／正文／全资源", out,
                         "不得输出最终成功文案")
        self.assertNotIn("核验一致，未执行部署写入", out)

    def test_edit_http_error_marks_repair_phase_and_does_not_persist(self):
        fixture = self.fixture(name="http-edit-fail-skill")
        harness = Harness(fixture, http_writes={"edit": {"status": 500}})
        harness.ns["WRITE_RETRY_DELAYS"] = (0.0, 0.0)      # 只判次数，不依赖等待
        want = fixture.body_text()
        harness.platform.post_content = want.rstrip("\n")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：正文修补", err)
        self.assertIn("官方写入未返回 200（status=500）", err)
        self.assertEqual([w["kind"] for w in harness.write_stub.requests],
                         ["install", "edit", "edit", "edit"],
                         "install 成功；edit 遇 5xx 重试到上限（1 次＋2 次重试）")
        self.assertEqual(harness.write_stub.bytes_read, len(_json_bytes(OK_ENVELOPE)),
                         "非 200 不读体（只消费了 install 的成功信封）")
        self.assertEqual(harness.platform.post_content, want.rstrip("\n"),
                         "写后未生效，平台正文仍是裁尾形态")
        self.assertEqual(harness.platform.uploads(), 1)
        table, _total = PhaseTiming.rows(self, out)
        self.assertEqual(table["正文修补"][3], "rc=1", "修补阶段如实显示失败 rc")

    def test_unchanged_object_never_writes_over_http(self):
        fixture = self.fixture(name="http-readonly-skill")
        candidate = pack_candidate(fixture)
        # 对齐现场字段使流程进入**只读分支**（与 `UnchangedObjectReadback.unchanged_harness` 同口径）
        harness = Harness(fixture, pre_blob=candidate,
                          platform_kwargs={"pre_hash": sha256_bytes(candidate),
                                           "pre_content": fixture.body_text(),
                                           "pre_description": "夹具技能描述"})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertIn("核验一致，未执行部署写入", out)
        self.assertEqual(harness.write_stub.requests, [], "只读分支零 HTTP 写")
        self.assertEqual(harness.write_stub.reads, 0)
        self.assertEqual(harness.platform.uploads(), 0)
        self.assertEqual([c[:2] for c in harness.platform.calls], [["skill", "view"]])

    def test_helper_refuses_unknown_procedure_without_any_request(self):
        """`g`：只认两个冻结 procedure，不泛化成通用 router 工具。"""
        ns = load_tool_namespace()
        fixture = self.fixture(name="http-unknown-skill")
        harness = Harness(fixture)
        ns["https_connection"] = harness.write_stub.connect      # 写入出口换受控假路由
        with self.assertRaises(ns["Fail"]) as caught:
            ns["write_skill_http"]((HttpStub.ORIGIN, FROZEN_KEY), "list", {"id": "skl_Probe"},
                                   ns["STAGE_INSTALL"])
        self.assertEqual(caught.exception.stage, ns["STAGE_INSTALL"])
        self.assertEqual(caught.exception.rc, 1, "安装阶段属写路径 ⇒ rc=1")
        self.assertIn("未知写入 procedure", caught.exception.detail)
        self.assertEqual(harness.write_stub.requests, [], "未声明的 procedure 不得发出请求")
        self.assertEqual(sorted(ns["WRITE_PROCEDURES"]), ["edit", "install"])

    def test_oversized_envelope_is_refused_and_cap_is_not_vacuous(self):
        """上限判据（含变异反控）：64 KB 之外的响应体不读、直接失败。

        变异体把 `WRITE_BODY_LIMIT` 放大到 1 MiB 后，**同一**响应体被读入并接受 ⇒ 若上限被去掉或
        失效，本用例第一条断言必红（判据非空转）。
        """
        big = dict(OK_ENVELOPE)
        big["pad"] = "x" * (70 * 1024)
        fixture = self.fixture(name="oversize-envelope-skill")
        harness = Harness(fixture, http_writes={"install": [{"status": 200, "body": big}]})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：安装", err)
        self.assertIn("响应体超过 65536 B 上限", err)
        self.assertEqual(harness.write_stub.bytes_read, 64 * 1024 + 1, "读到上限＋1 即停")
        self.assertNotIn("x" * 64, out + err, "响应体片段不得回显")
        mutated = TOOL.read_text(encoding="utf-8").replace(
            "WRITE_BODY_LIMIT = 64 * 1024", "WRITE_BODY_LIMIT = 1024 * 1024")
        self.assertNotEqual(mutated, TOOL.read_text(encoding="utf-8"), "变异须命中常量")
        fixture2 = self.fixture(name="oversize-envelope-mutant-skill")
        harness2 = Harness(fixture2, source=mutated,
                           http_writes={"install": [{"status": 200, "body": big}]})
        rc2, out2, err2 = harness2.run(fixture2.args(deploy=True))
        self.assertEqual(rc2, 0, "上限放大后同一响应体被接受（反控）: " + out2 + err2)


class WriteEnvelopeAndRepair(FixtureCase):
    """本批（写路径健壮性）：信封判定／`edit` 有界重试／补写后轮询／manifest 字段修正。

    判据（逐项独立可失败，断言**实际阶段与 rc**）：
      ① 200 ＋ `error` 信封 ⇒ 失败（日志只带 `status` 与错误 `code`；message／body 不回显），
         install 与 edit 均**不重试**；200 但非 `result` 形态同样失败；
      ② `edit` 遇瞬时 5xx（503／502）⇒ 重试后成功（同一幂等 `agentSkills.update`；install 不重试）；
      ③ `edit` 遇 4xx ⇒ **不重试**、一次即失败；
      ④ 补写后平台**先读旧、后读新** ⇒ 轮询到收敛即停（不读满等待表）；
      ⑤ name／description 与正文尾 LF **合并成一次** update（`content` 只在需要时给）；
      ⑥ 补写不生效（200 但平台不变）⇒ 轮询用尽后失败，detail 带轮询次数与末次字节数。
    另由常量判据固定重试／轮询时间表与 64 KB 上限。
    """

    def test_frozen_retry_and_poll_schedule(self):
        ns = load_tool_namespace()
        self.assertEqual(ns["WRITE_RETRY_DELAYS"], (0.25, 0.5), "edit 最多 2 次重试（250／500 ms）")
        self.assertEqual(ns["REPAIR_POLL_DELAYS"], (0.0, 0.5, 1.0, 2.0, 4.0))
        self.assertEqual(ns["REPAIR_POLL_BUDGET"], 10.0)
        self.assertLessEqual(sum(ns["REPAIR_POLL_DELAYS"]), ns["REPAIR_POLL_BUDGET"],
                             "等待表总和不得超预算")
        self.assertEqual(ns["WRITE_BODY_LIMIT"], 64 * 1024, "响应体上限 64 KB")
        self.assertEqual(ns["WRITE_READ_CHUNK"], 8192)

    def test_error_envelope_is_failure_without_retry(self):
        leak = "平台内部报文%s" % SECRET_MARKER
        cases = (
            # 已知枚举名：精确命中才外显（F1 白名单）
            ("BAD_REQUEST", {"error": {"json": {"message": leak, "code": "BAD_REQUEST",
                                               "data": {"stack": leak}}}}),
            # 整数 tRPC 码不再外显（F1：已知码枚举，其余一律 unknown）
            ("unknown", {"error": {"json": {"message": leak, "code": -32001,
                                           "data": {"code": "INTERNAL_SERVER_ERROR"}}}}),
            ("unknown", {"error": {"json": {"message": leak, "data": {"code": "FORBIDDEN"}}}}),
        )
        for kind, stage in (("install", "安装"), ("edit", "正文修补")):
            for code, envelope in cases:
                with self.subTest(kind=kind, code=code):
                    fixture, harness = self.fast(
                        "envelope-%s-%s-skill" % (kind, code.lower().replace("_", "-")),
                        http_writes={kind: [{"status": 200, "body": envelope}]})
                    if kind == "edit":
                        harness.platform.post_content = fixture.body_text().rstrip("\n")
                    rc, out, err = harness.run(fixture.args(deploy=True))
                    self.assertEqual(rc, 1, out + err)
                    self.assertIn("阶段失败：%s" % stage, err)
                    self.assertIn("官方写入返回错误信封（status=200 code=%s）" % code, err)
                    self.assertNotIn(leak, out + err, "信封 message 不得回显")
                    self.assertNotIn("INTERNAL_SERVER_ERROR", out + err, "信封 data 不得回显")
                    self.assertEqual([w["kind"] for w in harness.write_stub.requests
                                      if w["kind"] == kind], [kind], "错误信封不重试")
                    self.assertLessEqual(harness.write_stub.bytes_read, 64 * 1024)

    def test_200_without_result_shape_is_refused(self):
        cases = (({"result": "done"}, "不是 result 形态"),
                 ({"json": {"id": "skl_X"}}, "不是 result 形态"),
                 ({"result": None}, "不是 result 形态"),
                 ([], "信封不是对象"))
        for body, needle in cases:
            with self.subTest(body=type(body).__name__):
                fixture, harness = self.fast("shape-skill", http_writes={
                    "install": [{"status": 200, "body": body}]})
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, out + err)
                self.assertIn("阶段失败：安装", err)
                self.assertIn(needle, err)
                self.assertEqual(len(harness.write_stub.requests), 1, "不重试")

    def test_edit_retries_transient_5xx_then_succeeds(self):
        fixture, harness = self.fast("retry-edit-skill", http_writes={
            "edit": [{"status": 503}, {"status": 502}, {"status": 200}]})
        want = fixture.body_text()
        harness.platform.post_content = want.rstrip("\n")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual([w["kind"] for w in harness.write_stub.requests],
                         ["install", "edit", "edit", "edit"], "503／502 后第 3 次成功")
        self.assertEqual(harness.platform.edit_payloads,
                         [{"id": fixture.expect_id, "content": want}],
                         "只有 200 那次生效，且载荷幂等同一份")
        self.assertEqual(out.count("次重试"), 2, "两次瞬时失败各记一条重试日志")
        self.assertEqual(harness.platform.content, want, "补写后轮询判等通过")

    def test_edit_4xx_is_not_retried(self):
        for status in (400, 403, 409, 422):
            with self.subTest(status=status):
                fixture, harness = self.fast("no-retry-%d-skill" % status, http_writes={
                    "edit": [{"status": status}]})
                harness.platform.post_content = fixture.body_text().rstrip("\n")
                rc, out, err = harness.run(fixture.args(deploy=True))
                self.assertEqual(rc, 1, out + err)
                self.assertIn("阶段失败：正文修补", err)
                self.assertIn("官方写入未返回 200（status=%d）" % status, err)
                self.assertEqual([w["kind"] for w in harness.write_stub.requests],
                                 ["install", "edit"], "4xx 不重试")
                self.assertNotIn("次重试", err, "非瞬时失败不进入重试路径")

    def test_install_5xx_is_not_retried(self):
        fixture, harness = self.fast("install-no-retry-skill", http_writes={
            "install": [{"status": 503}]})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：安装", err)
        self.assertIn("install 与 4xx／错误信封不重试", err)
        self.assertEqual([w["kind"] for w in harness.write_stub.requests], ["install"],
                         "install 保持不重试")

    def test_poll_stops_when_platform_catches_up(self):
        fixture, harness = self.fast("poll-catchup-skill")
        trimmed = fixture.body_text().rstrip("\n")
        harness.platform.post_content = trimmed
        harness.platform.stale_views = 3          # 安装后首读＋写前复核＋第 1 轮轮询仍读旧
        harness.platform.stale_content = trimmed
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(harness.platform.edits()), 1)
        views = [c for c in harness.platform.calls if c[:2] == ["skill", "view"]]
        self.assertEqual(len(views), 5,
                         "部署前 1 次＋安装后 1 次＋写前复核 1 次＋轮询 2 次"
                         "（第 2 轮收敛即停，不读满等待表）")
        self.assertEqual(harness.platform.content, fixture.body_text())

    def test_tail_lf_and_field_mismatch_share_one_update(self):
        fixture, harness = self.fast("merged-repair-skill",
                                     platform_kwargs={"post_description": "别的描述"})
        want = fixture.body_text()
        harness.platform.post_content = want.rstrip("\n")
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        edits = harness.platform.edits()
        self.assertEqual(len(edits), 1, "正文与字段合并成一次 update")
        self.assertEqual(json.loads(edits[0]["body"].decode("utf-8"))["json"],
                         {"id": fixture.expect_id, "content": want,
                          "manifest": {"name": fixture.name, "description": "夹具技能描述"}})
        self.assertEqual(harness.platform.content, want)
        self.assertEqual(harness.platform.post_description, "夹具技能描述",
                         "manifest 修正后描述取源 frontmatter 文案")

    def test_poll_timeout_reports_counts_and_last_bytes(self):
        fixture, harness = self.fast("poll-timeout-skill",
                                     platform_kwargs={"ignore_edit": True})
        trimmed = fixture.body_text().rstrip("\n")
        harness.platform.post_content = trimmed
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("补写后轮询 5 次仍未收敛", err)
        self.assertIn("末次正文 %d／%d B" % (len(trimmed.encode("utf-8")),
                                             len(fixture.body_text().encode("utf-8"))), err)
        self.assertEqual(harness.platform.uploads(), 1, "写路径已开始 ⇒ rc=1")


class ReviewFixGuards(FixtureCase):
    """2026-10-25 复审发现 F1–F4 的**负控**（每例在修复前源码上必红、修后必绿）。

    判据：
      · F1 白名单之外的 `code`（整数码、`data.code`、形态合规的合成 token）只记 `unknown`，原样串
        不得进 stdout／stderr；
      · F2 单次读取 12 s（> 10 s 预算）⇒ rc=1、文案含「超过剩余预算」，且轮询读取带 ≤10 s 的正预算；
      · F3 轮询**首轮** hash 错、次轮又对 ⇒ 仍 rc=1、文案含「完整性异常」，且不读第 2 轮；
      · F4 基线后写前出现**第三个** description／name／content 值 ⇒ rc=1、文案含「并发变更」、
        不发 `update`（含重试前复核：首次 5xx 后不再发第 2 次）。
    """

    def test_envelope_code_whitelist_is_frozen(self):
        """F1：判定只认已知枚举名；整数码／小写合成串／非对象一律 unknown。"""
        ns = load_tool_namespace()
        for name in ("BAD_REQUEST", "UNAUTHORIZED", "FORBIDDEN", "NOT_FOUND",
                     "METHOD_NOT_SUPPORTED", "TIMEOUT", "CONFLICT", "PRECONDITION_FAILED",
                     "PAYLOAD_TOO_LARGE", "TOO_MANY_REQUESTS", "CLIENT_CLOSED_REQUEST",
                     "INTERNAL_SERVER_ERROR", "NOT_IMPLEMENTED", "BAD_GATEWAY",
                     "SERVICE_UNAVAILABLE", "GATEWAY_TIMEOUT"):
            self.assertIn(name, ns["ENVELOPE_CODES"])
        self.assertEqual(ns["_envelope_code"]({"json": {"code": "FORBIDDEN"}}), "FORBIDDEN")
        self.assertEqual(ns["_envelope_code"]({"code": "CONFLICT"}), "CONFLICT")
        self.assertEqual(ns["_envelope_code"]({"code": "forbidden"}), "unknown")
        self.assertEqual(ns["_envelope_code"]({"code": 403}), "unknown")
        self.assertEqual(ns["_envelope_code"]({"json": {"data": {"code": "FORBIDDEN"}}}),
                         "unknown")
        self.assertEqual(ns["_envelope_code"]("FORBIDDEN"), "unknown")
        self.assertEqual(ns["_envelope_code"](None), "unknown")

    def test_synthetic_envelope_code_is_only_unknown(self):
        """F1 负控：形态合规但不在白名单的 code 不得原样落日志。"""
        forged = "LEAK_" + SECRET_MARKER          # 字符集合规（旧实现会原样回显）
        fixture, harness = self.fast("forged-code-skill", http_writes={
            "install": [{"status": 200,
                         "body": {"error": {"json": {"code": forged, "message": forged}}}}]})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("官方写入返回错误信封（status=200 code=unknown）", err)
        self.assertNotIn(forged, out + err, "白名单之外的 code 不得回显")
        self.assertNotIn(SECRET_MARKER, out + err)
        self.assertEqual([w["kind"] for w in harness.write_stub.requests], ["install"],
                         "错误信封不重试")

    def test_single_read_over_budget_fails(self):
        """F2 负控：单次读取 12 s（> 10 s 预算）不得判成功；轮询读取须带剩余预算。"""
        fixture, harness = self.fast("slow-read-skill")
        clock = FakeTime()
        harness.ns["time"] = clock
        harness.platform.post_content = fixture.body_text().rstrip("\n")
        harness.platform.advance = clock.tick
        # 写入（edit）之后平台读取变慢：单次 12 s，超出 10 s 轮询总预算
        harness.platform.on_write = lambda record: setattr(harness.platform, "view_cost", 12.0)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("超过剩余预算", err)
        budgets = [b for b in harness.read_budgets if b is not None]
        self.assertTrue(budgets, "轮询读取必须携带剩余预算（不能只约束等待点）")
        self.assertTrue(all(0 < b <= 10.0 for b in budgets), budgets)

    def test_identity_anomaly_in_first_poll_round_stops(self):
        """F3 负控：轮询首轮 hash 错、次轮又对 ⇒ 仍必须 Fail（不继续等）。"""
        fixture, harness = self.fast("poll-identity-skill")
        harness.platform.post_content = fixture.body_text().rstrip("\n")
        state = {"edited": False, "reads": 0}

        def on_write(record):
            if record["kind"] == "edit":
                state["edited"] = True

        def on_call(args):
            if state["edited"] and args[:2] == ["skill", "view"]:
                state["reads"] += 1
                if state["reads"] == 1:
                    harness.platform.post_hash = "0" * 64     # 首轮：完整性异常
                elif state["reads"] == 2:
                    harness.platform.post_hash = None         # 次轮：又恢复正确

        harness.platform.on_write = on_write
        harness.platform.on_call = on_call
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("完整性异常", err)
        self.assertIn("zipFileHash", err)
        self.assertEqual(state["reads"], 1, "首轮差异即停，不读第 2 轮")

    def test_third_description_value_stops_before_write(self):
        """F4 负控：基线后、写前把 description 改成第三值 ⇒ rc=1 且不发 update。"""
        fixture, harness = self.fast("concurrent-desc-skill",
                                     platform_kwargs={"post_description": "别的描述"})
        state = {"views": 0, "changed": False}

        def after_view(args):
            if args[:2] == ["skill", "view"] and harness.platform.installed:
                state["views"] += 1
                if state["views"] == 1 and not state["changed"]:
                    # 安装后首读＝修补基线；它**返回之后**第三方改了描述（写前复核应看见第三值）
                    harness.platform.post_description = "第三方改的描述"
                    state["changed"] = True

        harness.platform.on_view_served = after_view
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：正文修补", err)
        self.assertIn("并发变更", err)
        self.assertIn("description", err)
        self.assertEqual(harness.platform.edits(), [], "并发变更即停，不得发 update 覆盖")
        self.assertEqual(harness.platform.post_description, "第三方改的描述",
                         "第三值必须保持原样")

    def test_third_value_before_retry_stops(self):
        """F4（重试面）：首次 update 瞬时失败后、重试前出现第三值 ⇒ 不再发第 2 次 update。"""
        fixture, harness = self.fast("concurrent-retry-skill",
                                     platform_kwargs={"post_description": "别的描述"},
                                     http_writes={"edit": [{"status": 503}, {"status": 200}]})
        state = {"edited": False}

        def on_write(record):
            if record["kind"] == "edit" and not state["edited"]:
                # 首次 update 已被平台登记（本次 503 不生效）：重试**之前**第三方改了描述
                state["edited"] = True
                harness.platform.post_description = "第三方改的描述"

        harness.platform.on_write = on_write
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("并发变更", err)
        self.assertEqual([w["kind"] for w in harness.write_stub.requests], ["install", "edit"],
                         "重试前复核发现并发变更 ⇒ 不再发第 2 次 update")


class ReviewRound2Guards(FixtureCase):
    """2026-10-25 **第二轮**差分复审 N1／F2 的负控（每例在 `d803743` 源码上必红、修后必绿）。

    判据：
      · N1 写前注入 hash 变化 ⇒ rc=1、`edit` 调用 **0**：完整性判定必须在写前那次回读里，不得先发
        `update` 再由轮询发现异常（那时已经不是零写）；
      · F2 非轮询单读 12 s（> 10 s 预算）⇒ rc=1 且不判成功；写前复核单读超预算同样零 edit；
      · F2 部署前 `view` 单读超预算 ⇒ rc=2（写路径前，rc 分类不动）且零上传、零写入；
      · F2 修补路径**全部**回读（部署前／安装后／写前复核／轮询）都带 0＜b≤10 s 的预算，无 `None`。
    """

    def test_hash_change_before_patch_guard_is_zero_write(self):
        """N1 负控：基线读之后、写前复核之前注入 hash 变化 ⇒ rc=1 且零 edit。"""
        fixture, harness = self.fast("guard-hash-skill")
        harness.platform.post_content = fixture.body_text().rstrip("\n")   # 需要走修补路径
        state = {"views": 0}

        def after_view(args):
            if args[:2] == ["skill", "view"] and harness.platform.installed:
                state["views"] += 1
                if state["views"] == 1:
                    # 安装后首读＝修补基线；它**返回之后**注入 hash 变化（写前复核应看见完整性异常）
                    harness.platform.post_hash = "0" * 64

        harness.platform.on_view_served = after_view
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：正文修补", err)
        self.assertIn("写前复核发现完整性异常", err)
        self.assertIn("zipFileHash", err)
        self.assertEqual(harness.platform.edits(), [], "完整性异常 ⇒ 零写：不得先发 update 再报错")
        self.assertEqual(harness.platform.post_hash, "0" * 64, "异常现场不得被改写")

    def test_install_readback_over_budget_fails(self):
        """F2 负控：非轮询的单次安装后回读 12 s（> 10 s）不得判成功。"""
        fixture, harness = self.fast("slow-install-read-skill")
        clock = FakeTime()
        harness.ns["time"] = clock
        harness.platform.advance = clock.tick
        harness.platform.on_write = lambda record: setattr(harness.platform, "view_cost", 12.0)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)          # 写路径内
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("超过剩余预算", err)
        self.assertNotIn("回读判等：id／zipFileHash", out, "超预算不得输出判等成功文案")
        self.assertTrue(all(b is not None and 0 < b <= 10.0 for b in harness.read_budgets),
                        harness.read_budgets)

    def test_guard_read_over_budget_blocks_write(self):
        """F2 负控：写前复核单读 12 s（> 10 s）⇒ rc=1 且零 edit、不判成功。"""
        fixture, harness = self.fast("slow-guard-read-skill")
        clock = FakeTime()
        harness.ns["time"] = clock
        harness.platform.advance = clock.tick
        harness.platform.post_content = fixture.body_text().rstrip("\n")
        state = {"views": 0}

        def after_view(args):
            if args[:2] == ["skill", "view"] and harness.platform.installed:
                state["views"] += 1
                if state["views"] == 1:
                    harness.platform.view_cost = 12.0   # 下一次读＝写前复核，超预算

        harness.platform.on_view_served = after_view
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：正文修补", err)
        self.assertIn("超过剩余预算", err)
        self.assertEqual(harness.platform.edits(), [], "读超预算 ⇒ 零写")

    def test_pre_deploy_read_over_budget_fails_before_write(self):
        """F2：部署前 `view` 单读 12 s ⇒ rc=2（写路径前，rc 分类不动）、零上传、零写入。"""
        clock = FakeTime()
        fixture = self.fixture(name="slow-pre-read-skill")
        harness = Harness(fixture, platform_kwargs={"view_cost": 12.0, "advance": clock.tick})
        harness.ns["time"] = clock
        harness.ns["WRITE_RETRY_DELAYS"] = (0.0, 0.0)
        harness.ns["REPAIR_POLL_DELAYS"] = (0.0,) * 5
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：平台回读", err)
        self.assertIn("超过剩余预算", err)
        self.assertEqual(harness.platform.uploads(), 0)
        self.assertEqual(harness.platform.writes, [])

    def test_every_readback_carries_budget(self):
        """F2 正控：修补路径每次回读的预算都非 `None` 且 0＜b≤10 s（覆盖四处回读）。"""
        fixture, harness = self.fast("budgeted-reads-skill")
        harness.platform.post_content = fixture.body_text().rstrip("\n")   # 走修补＋轮询
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertGreaterEqual(len(harness.read_budgets), 4, harness.read_budgets)
        self.assertTrue(all(b is not None and 0 < b <= 10.0 for b in harness.read_budgets),
                        harness.read_budgets)


class CliStartupFailures(FixtureCase):
    """复审 F3：CLI 启动异常（`OSError`）按**调用阶段**归类——写路径前 rc=2、写路径内 rc=1。

    本批起 install／edit 不再是 CLI 调用点，故那两例同批退休（判据迁至 `HttpWritePath`），
    此处保留写路径前的 view 与写路径内的**安装后 view** 两个调用点。
    """

    def harness(self, name, fail_verbs, fail_occurrence=None, **kwargs):
        fixture = self.fixture(name=name)
        harness = Harness(fixture, patch_lh=False, **kwargs)
        stub = CliProcessStub(str(fixture.bin / "lh"), harness.platform, fail_verbs,
                              fail_occurrence)
        harness.ns["subprocess"] = stub
        return fixture, harness, stub

    def test_platform_startup_failure_is_rc2_before_write(self):
        fixture, harness, stub = self.harness("startup-view-skill", ("view",))
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：平台回读", err)
        self.assertIn("无法调用 lh（OSError）", err)
        self.assertEqual(harness.platform.uploads(), 0, "写路径前 ⇒ 零上传")
        self.assertEqual(harness.client.gets, [])
        self.assertEqual(harness.platform.installed_calls(), [])
        self.assertEqual(harness.platform.edits(), [])
        self.assertEqual(stub.verbs(), ["view"], "只在平台前置一次调用上失败")

    # 本批退休：「install 启动失败 rc=1」「edit 启动失败 rc=1 且归到正文修补」两例。删除对象＝
    # 写业务的 CLI 启动面（install／edit 已改官方 HTTP 写入，不再有该调用点）。判据迁移：写路径内
    # 写入失败的 rc=1 与阶段归类由 `HttpWritePath` 承接（非 200／中介页／传输异常、修补阶段 rc=1）；
    # 「写路径内 CLI 启动异常 rc=1」仍由下面的「安装后 view 启动失败」一例固定，无空转用例留守。

    def test_post_install_view_startup_failure_is_rc1(self):
        """**安装后**那次 view 启动失败 ⇒ rc=1（该次 view 现同时承载资源集回读）。

        原「上传后资源清单启动失败 rc=1」与「只读期资源清单启动失败 rc=2」两例随 `skill
        resources` CLI 退休：只读分支只回读一次 view（无安装后调用点），其形态门判据迁至
        `ResourceMetadataGate`；此处保留写路径内的等价调用点。
        """
        fixture, harness, stub = self.harness("startup-postview-skill", (),
                                              fail_occurrence={"view": {2}})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：回读判等", err)
        self.assertIn("无法调用 lh（OSError）", err)
        self.assertEqual(harness.platform.uploads(), 1, "上传已发生 ⇒ 不得报「未进入写路径」")
        self.assertEqual(stub.verbs(), ["view", "view"],
                         "失败点是安装后那次 view（正控：部署前 view 启动正常；写入不启动 CLI）")


class SourceSnapshotWindow(FixtureCase):
    """复审 F5：部署窗口内源端变化的两个检查点（上传前 rc=2／投后 rc=1），不重打包候选。"""

    def drift_on(self, fixture, verb, rel=RESOURCE_REL, nth=1):
        """在指定 CLI 调用的第 `nth` 次（**调用之前**）改源文件（模拟「部署窗口内源目录被改动」）。

        `nth` 用于把「同域调用面里第几次出现」说清：写路径中 `view` 的**第 2 次**即安装后的平台
        回读，`install` 的**第 1 次**即安装本身。
        """
        state = {"seen": 0, "done": False}

        def hook(args):
            if state["done"] or args[:2] != ["skill", verb]:
                return
            state["seen"] += 1
            if state["seen"] < nth:
                return
            state["done"] = True
            fixture.write_resource(rel, b"changed-in-window\n")
        return hook

    def drift_on_write(self, fixture, kind, rel=RESOURCE_REL, nth=1):
        """同 `drift_on`，但触发点是**官方 HTTP 写入**（install／edit 已不走 CLI）。"""
        state = {"seen": 0, "done": False}

        def hook(record):
            if state["done"] or record["kind"] != kind:
                return
            state["seen"] += 1
            if state["seen"] < nth:
                return
            state["done"] = True
            fixture.write_resource(rel, b"changed-in-window\n")
        return hook

    def assert_window_stop(self, harness, fixture, rc, out, err):
        """N2 三类改源点的**共同口径**：rc=1、含人工确认文案、无最终成功文案、候选未被替换。"""
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：投后复核", err)
        self.assertIn("部署已写入完成，但源目录在部署窗口内发生变化，须人工确认是否重投", err)
        self.assertIn("源端内容已变化：%s" % RESOURCE_REL, err)
        self.assertNotIn("源端复核（安装后）：源文件集与逐文件 bytes 仍与候选快照一致", out,
                         "命中时不得输出投后「一致」成功文案")
        self.assertNotIn("回读判等：id／zipFileHash／name／description／正文／全资源", out,
                         "不得输出最终成功文案")
        self.assertEqual(harness.platform.uploads(), 1, "上传已发生 ⇒ rc=1")
        self.assertEqual(len(harness.platform.installed_calls()), 1, "安装已发生")
        self.assertNotIn(b"changed-in-window", fixture.candidate().read_bytes(),
                         "候选 ZIP 不得被重新打包替换（部署对象始终是已核定的候选）")

    def test_source_change_before_upload_stops_with_rc2(self):
        fixture = self.fixture(name="source-window-skill")
        harness = Harness(fixture, platform_kwargs={"on_call": self.drift_on(fixture, "view")})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：源端复核", err)
        self.assertIn("打包后源端已变化（未进入写路径；未上传）", err)
        self.assertIn("源端内容已变化：%s" % RESOURCE_REL, err)
        self.assertEqual(harness.platform.uploads(), 0, "零上传")
        self.assertEqual(harness.client.gets, [], "零 R2 读取")
        self.assertEqual(harness.platform.installed_calls(), [], "零 install")
        self.assertEqual(harness.platform.edits(), [], "零 edit")
        self.assertFalse(fixture.rollback().exists(), "不得写回滚包")
        table, _total = PhaseTiming.rows(self, out)
        self.assertEqual(table["源端复核"][3], "rc=2", "上传前复核阶段如实显示失败 rc")
        self.assertNotIn("源端复核（上传前）：源文件集与逐文件 bytes 与候选快照一致", out,
                         "命中时不得输出「一致」成功文案")

    def test_source_change_in_install_window_is_rc1_with_warning(self):
        fixture = self.fixture(name="source-window-after-skill")
        harness = Harness(fixture, platform_kwargs={"on_write": self.drift_on_write(fixture,
                                                                                  "install")})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：投后复核", err)
        self.assertIn("部署已写入完成，但源目录在部署窗口内发生变化，须人工确认是否重投", err)
        self.assertIn("源端内容已变化：%s" % RESOURCE_REL, err)
        self.assertEqual(harness.platform.uploads(), 1, "上传已发生 ⇒ rc=1")
        self.assertEqual(len(harness.platform.installed_calls()), 1, "安装已发生")
        table, _total = PhaseTiming.rows(self, out)
        self.assertEqual(table["投后复核"][3], "rc=1")

    def test_source_change_at_first_post_install_view_is_rc1(self):
        """N2 ①：安装后**第一次** `view`（平台回读）时改源——检查点未覆盖回读窗口就会误报成功。"""
        fixture = self.fixture(name="source-window-postview-skill")
        harness = Harness(fixture, platform_kwargs={"on_call": self.drift_on(fixture, "view", nth=2)})
        rc, out, err = harness.run(fixture.args(deploy=True))
        views = [c for c in harness.platform.calls if c[:2] == ["skill", "view"]]
        self.assertEqual(len(views), 2, "改源发生在投后那一次 view（第 2 次，非上传前那次）")
        self.assert_window_stop(harness, fixture, rc, out, err)
        table, _total = PhaseTiming.rows(self, out)
        self.assertEqual(table["投后复核"][3], "rc=1")
        self.assertEqual(table["资源回读"][3], "rc=0", "资源回读在检查点之前已按序完成")

    def test_source_change_during_edit_is_rc1(self):
        """N2 ②：平台正文**恰少一个尾 LF** ⇒ 真进 edit 分支；edit 调用前改源。"""
        fixture = self.fixture(name="source-window-edit-skill")
        harness = Harness(fixture,
                          platform_kwargs={"post_content": fixture.body_text().rstrip("\n"),
                                           "on_write": self.drift_on_write(fixture, "edit")})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(len(harness.platform.edits()), 1,
                         "夹具须真的进入 edit 分支（恰少一个尾 LF），否则本用例空转")
        self.assert_window_stop(harness, fixture, rc, out, err)
        table, _total = PhaseTiming.rows(self, out)
        self.assertEqual(table["正文修补"][3], "rc=0", "edit 本身成功，失败来自回读之后的源端复核")
        self.assertEqual(table["投后复核"][3], "rc=1")

    def test_source_change_at_last_resource_readback_is_rc1(self):
        """N2 ③：资源回读窗口最后一次请求到达时改源，检查点须覆盖并 fail-closed；
        请求次序不确定（workers=4），断言不依赖请求顺序。
        """
        fixture = self.fixture(name="source-window-resource-skill")
        fixture.write_resource("references/z-last.md", b"last-resource\n")
        expected = sorted(fixture.resource_map())
        state = {"done": False}

        def on_request(path):
            # 请求已登记；按到达次数而非资源路径定位窗口末次请求。
            if state["done"] or len(stub.requests) != len(expected):
                return
            state["done"] = True
            fixture.write_resource(RESOURCE_REL, b"changed-in-window\n")

        stub = HttpStub(fixture.resource_map(), on_request=on_request)
        harness = Harness(fixture, http=stub)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertTrue(state["done"], "须在最后一个资源回读时改源（否则用例空转）")
        self.assertEqual(sorted(stub.requests), expected, "每个候选资源恰一次 HTTP 读取")
        self.assert_window_stop(harness, fixture, rc, out, err)

    def test_readonly_branch_also_passes_the_snapshot_gate(self):
        fixture = self.fixture(name="source-window-readonly-skill")
        candidate = pack_candidate(fixture)
        harness = Harness(fixture, pre_blob=candidate,
                          platform_kwargs={"pre_hash": sha256_bytes(candidate),
                                           "pre_content": fixture.body_text(),
                                           "pre_description": "夹具技能描述",
                                           "on_call": self.drift_on(fixture, "view")})
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：源端复核", err)
        self.assertNotIn("核验一致，未执行部署写入", out)
        self.assertEqual(harness.platform.uploads(), 0)
        self.assertEqual(harness.client.gets, [], "零 R2 读取")

    def test_stable_source_passes_both_check_sites(self):
        fixture = self.fixture(name="source-stable-skill")
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertIn("源端复核（上传前）：源文件集与逐文件 bytes 与候选快照一致", out)
        self.assertIn("源端复核（安装后）：源文件集与逐文件 bytes 仍与候选快照一致", out)
        self.assertEqual(harness.platform.uploads(), 1)
        # N2 位置证据（负控对照）：投后检查的**成功日志**必须晚于回读判等／资源回读，即检查点
        # 确实落在部署窗口的**尾部**（若留在原处，这条序号关系会反过来）。
        table, _total = PhaseTiming.rows(self, out)
        self.assertGreater(int(table["投后复核"][0]), int(table["资源回读"][0]),
                           "N2：投后复核的计时序号须在资源回读之后（检查点落在窗口尾部）")
        self.assertLess(out.index("源端复核（安装后）"),
                        out.index("回读判等：id／zipFileHash／name／description／正文／全资源"),
                        "投后复核紧接全资源回读，最终成功日志仍是最后一条")


class BodyContractCrlf(FixtureCase):
    """正文契约的 LF／CRLF 口径与失败类别（F3）。§2.2 允许 CRLF 起止行，正文 bytes 不归一。

    修前失败点：`fm_get`／`fm_fields` 走 `parse_fm_mapping`，按 `\\n` 切行后行尾残留 `\\r`，
    结束行 `---\\r` 与字段行都被判成「无法识别」，抛 `UNSUPPORTED_YAML`；同一模块的
    `body_bytes` 却接受 CRLF 并原样返回 `\\r\\n`（自相矛盾）。本类固定两处口径：
    正文逐字节不归一；frontmatter 字段按行解析可取值。
    期望值一律**字面独立**给出（不从 `body_text()`／被测实现反算），失败类别按 `ContractError.code`
    精确断言，不用子串包含代替。
    """

    def setUp(self):
        super(BodyContractCrlf, self).setUp()
        self.bc = load_body_contract()

    def assert_code(self, code, fn, *args):
        with self.assertRaises(self.bc["ContractError"]) as ctx:
            fn(*args)
        self.assertEqual(code, ctx.exception.code)

    # ── 正控：CRLF 与混合行终止符 ──────────────────────────────────────────
    def test_crlf_frontmatter_fields_and_body_bytes(self):
        raw = b"---\r\nname: demo\r\ndescription: d\r\n---\r\nbody line\r\n"
        self.assertEqual("demo", self.bc["fm_get"](raw, "name"))
        self.assertEqual("d", self.bc["fm_get"](raw, "description"))
        # 正文契约：原样 bytes（CRLF 保留，不做任何尾换行／行终止符归一）
        self.assertEqual(b"body line\r\n", self.bc["body_bytes"](raw))
        # 同一逻辑正文的 LF 变体：正文按原 bytes 返回，不做行终止符归一
        self.assertEqual(b"body line\n", self.bc["body_bytes"](raw.replace(b"\r\n", b"\n")))

    def test_mixed_line_terminators_are_allowed(self):
        """§2.2：结束行行终止符不要求与起始行同族。"""
        raw = b"---\nname: demo\n---\r\nbody\r\n"
        self.assertEqual("demo", self.bc["fm_get"](raw, "name"))
        self.assertEqual(b"body\r\n", self.bc["body_bytes"](raw))
        raw2 = b"---\r\nname: demo\r\n---\nbody\n"
        self.assertEqual("demo", self.bc["fm_get"](raw2, "name"))
        self.assertEqual(b"body\n", self.bc["body_bytes"](raw2))

    def test_crlf_block_scalar_value_is_line_based(self):
        raw = b"---\r\ndescription: |\r\n  a\r\n  b\r\n---\r\nbody\r\n"
        self.assertEqual("a\nb\n", self.bc["fm_get"](raw, "description"))
        self.assertEqual(b"body\r\n", self.bc["body_bytes"](raw))

    def test_escaped_quoted_scalar_values(self):
        """转义按契约既有语义：双引号内 `\\t` 是制表符；单引号内是字面反斜杠＋t。"""
        self.assertEqual("a\tb", self.bc["fm_get"](b'---\nname: "a\\tb"\n---\nx\n', "name"))
        self.assertEqual("a\\tb", self.bc["fm_get"](b"---\nname: 'a\\tb'\n---\nx\n", "name"))

    # ── 负控：精确失败类别 ────────────────────────────────────────────────
    def test_duplicate_keys_rejected_including_crlf(self):
        self.assert_code("DUPLICATE_KEY", self.bc["fm_fields"], b"---\nname: a\nname: b\n---\nx\n")
        self.assert_code("DUPLICATE_KEY", self.bc["fm_fields"],
                         b"---\r\nname: a\r\nname: b\r\n---\r\nx\r\n")

    def test_invalid_utf8_is_rejected_in_body_and_frontmatter(self):
        self.assert_code("INVALID_UTF8", self.bc["body_bytes"], b"---\nname: a\n---\nbody \xff\n")
        self.assert_code("INVALID_UTF8", self.bc["fm_fields"], b"---\nname: \xff\n---\nx\n")

    def test_bom_is_forbidden_before_frontmatter_detection(self):
        raw = b"\xef\xbb\xbf---\nname: a\n---\nx\n"
        self.assert_code("BOM_FORBIDDEN", self.bc["body_bytes"], raw)
        self.assert_code("BOM_FORBIDDEN", self.bc["fm_fields"], raw)

    def test_unterminated_frontmatter_is_whole_body(self):
        """§2.2：扫到 EOF 无结束行 → 无 frontmatter，正文＝整个文件（原样 bytes）。"""
        raw = b"---\nname: a\nbody"
        self.assertEqual(b"---\nname: a\nbody", self.bc["body_bytes"](raw))
        self.assertIs(self.bc["MISSING"], self.bc["fm_get"](raw, "name"))
        raw_crlf = b"---\r\nname: a\r\nbody\r\n"
        self.assertEqual(b"---\r\nname: a\r\nbody\r\n", self.bc["body_bytes"](raw_crlf))
        self.assertIs(self.bc["MISSING"], self.bc["fm_get"](raw_crlf, "name"))

    # ── 真实打包入口：原始 bytes 夹具走过的不是 text 模式 ─────────────────
    def test_crlf_skill_md_through_real_pack_entry(self):
        """`write_bytes` 直接落 CRLF 的 SKILL.md，经**真实打包入口** rc=0；description 与正文
        取值与主路径一致（正文逐字节＝字面期望）。这是 CRLF 修复真正要守的链路。"""
        fixture = self.fixture(name="crlf-skill")
        raw = ("---\r\nname: crlf-skill\r\ndescription: CRLF 描述\r\n---\r\n"
               "# 正文\r\n\r\n首行\r\n").encode("utf-8")
        fixture.skill_md.write_bytes(raw)
        cp = fixture.run_tool(fixture.args())
        out, err = text_of(cp)
        self.assertEqual(cp.returncode, 0, out + err)
        # 断言面改为**生成的 ZIP 实际产物**（此前只对输入 raw 断言：打包若归一化 CRLF 则本用例
        #   依旧全绿，等于没守住这条链路——F3 验收缺口）。成员名取包内根 `SKILL.md`。
        with zipfile.ZipFile(str(fixture.candidate())) as archive:
            self.assertIn("SKILL.md", archive.namelist(), "候选 ZIP 根须含 SKILL.md")
            packed = archive.read("SKILL.md")
        self.assertEqual(raw, packed)
        self.assertEqual("# 正文\r\n\r\n首行\r\n".encode("utf-8"), self.bc["body_bytes"](packed))
        self.assertEqual("CRLF 描述", self.bc["fm_get"](packed, "description"))


class WriteAtomicResidualWarning(unittest.TestCase):
    """F5：`write_atomic` 接缝上的残留告警——固定类别＋自建 basename，绝不外露 out-dir 路径；
    `stderr` 自身失败不得替代原异常；旧产物保留、失败分类不变。"""

    def setUp(self):
        self.ns = load_tool_namespace()
        self.dir = Path(tempfile.mkdtemp(prefix="wa-"))
        self.addCleanup(shutil.rmtree, str(self.dir), True)
        self.target = self.dir / "artifact.zip"

    @staticmethod
    def boom(*args, **kwargs):
        raise OSError(13, "denied")

    def _patched(self, err):
        return (mock.patch.object(self.ns["os"], "replace", side_effect=self.boom),
                mock.patch.object(self.ns["os"], "unlink", side_effect=self.boom),
                contextlib.redirect_stderr(err))

    def test_replace_and_unlink_fail_keep_classification_and_hide_path(self):
        self.target.write_bytes(b"PREVIOUS-ARTIFACT-BYTES")
        err = io.StringIO()
        p1, p2, p3 = self._patched(err)
        with p1, p2, p3:
            with self.assertRaises(self.ns["Fail"]) as ctx:
                self.ns["write_atomic"](str(self.target), b"NEW-BYTES", "local")
        fail = ctx.exception
        self.assertEqual(("local", 2), (fail.stage, fail.rc), "本地阶段失败仍是 rc=2")
        self.assertIn("写出产物失败", fail.detail)
        self.assertIn("PermissionError", fail.detail, "异常类名进固定分类说明")
        self.assertNotIn("denied", fail.detail, "原异常消息不进固定分类说明")
        text = err.getvalue()
        self.assertIn("临时文件残留", text, "固定类别")
        self.assertNotIn(str(self.dir), text, "out-dir 完整路径不得出现在告警里")
        self.assertRegex(text, r"\.deploy-[^\s/]+\.?[^\s/]*", "只给自建 basename")
        self.assertEqual(b"PREVIOUS-ARTIFACT-BYTES", self.target.read_bytes(), "旧产物保留")
        # 残留文件只在自建目录内，且本用例自清理（setUp 的 rmtree）
        residual = sorted(x.name for x in self.dir.iterdir())
        self.assertEqual(["artifact.zip"], [n for n in residual if n == "artifact.zip"])
        self.assertTrue(any(n.startswith(".deploy-") for n in residual), "残留应是被删失败的临时文件")

    def test_stderr_failure_does_not_replace_original_fail(self):
        self.target.write_bytes(b"PREVIOUS-ARTIFACT-BYTES")

        class BrokenStderr(object):
            def write(self, _):
                raise OSError(9, "bad descriptor")

            def flush(self):
                raise OSError(9, "bad descriptor")

        p1, p2, _ = self._patched(io.StringIO())
        with p1, p2, mock.patch.object(sys, "stderr", BrokenStderr()):
            with self.assertRaises(self.ns["Fail"]) as ctx:
                self.ns["write_atomic"](str(self.target), b"NEW-BYTES", "local")
        self.assertEqual(("local", 2), (ctx.exception.stage, ctx.exception.rc),
                         "stderr 失败不得替换原 Fail 的分类")
        self.assertIn("写出产物失败", ctx.exception.detail)
        self.assertEqual(b"PREVIOUS-ARTIFACT-BYTES", self.target.read_bytes())


class CandidateDigestGate(FixtureCase):
    """判据 23（本批）：`--expect-zip-sha256` 候选哈希门禁。

    匹配 ⇒ 原部署流程一字不改（上传／install／回读判等照旧）；任何不一致或格式不合格 ⇒
    在**任何远端写入之前** rc=2（零 R2 读取／零上传／零 install／零 edit），且不留候选包；
    缺该参数 ⇒ 旧调用行为不变；只打包模式同样生效（按本批确认的口径）。
    """

    def pack_digest(self, fixture, sub="predigest"):
        """把候选包到**另一个**已存在目录取 sha256，保持 `assets/` 为空以便断言「零产物」。"""
        out = fixture.root / sub
        out.mkdir(parents=True, exist_ok=True)
        cp = fixture.run_tool(fixture.args(out=out))
        out_text, err_text = text_of(cp)
        self.assertEqual(cp.returncode, 0, out_text + err_text)
        return sha256_bytes((out / ("%s.zip" % fixture.name)).read_bytes())

    def assert_zero_remote_writes(self, harness):
        self.assertEqual(harness.platform.uploads(), 0, "零 R2 上传")
        self.assertEqual(harness.client.gets, [], "零 R2 读取")
        self.assertEqual(harness.platform.installed_calls(), [], "零 install")
        self.assertEqual(harness.platform.edits(), [], "零 edit")

    def test_matching_digest_keeps_normal_deploy_flow(self):
        fixture = self.fixture(name="digest-ok-skill")
        digest = self.pack_digest(fixture)
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(deploy=True, expect_zip_sha256=digest))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(harness.platform.uploads(), 1, "匹配时仍照旧上传一次")
        self.assertEqual(len(harness.platform.installed_calls()), 1, "匹配时仍照旧 install 一次")
        self.assertEqual(harness.platform.edits(), [], "正文本来就相等，不需要 edit")
        self.assertIn("打包：files=", out)
        self.assertIn("sha256=%s" % digest, out, "日志 sha256 即本次内存构包哈希")
        self.assertEqual(sha256_bytes(fixture.candidate().read_bytes()), digest,
                         "产物就是被门禁核过的那个包")

    def test_legacy_call_without_parameter_is_unchanged(self):
        fixture = self.fixture(name="digest-legacy-skill")
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(deploy=True))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(harness.platform.uploads(), 1, "不给新参数＝旧调用行为不变")
        self.assertEqual(len(harness.platform.installed_calls()), 1)
        self.assertNotIn("--expect-zip-sha256", out)

    def test_wrong_digest_is_rc2_with_zero_remote_writes(self):
        fixture = self.fixture(name="digest-bad-skill")
        digest = self.pack_digest(fixture)
        wrong = sha256_bytes(b"another-general-package")
        self.assertNotEqual(wrong, digest)
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(deploy=True, expect_zip_sha256=wrong))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：本地校验", err)
        self.assertIn("候选 ZIP sha256 与 --expect-zip-sha256 不一致（未上传／未安装）", err)
        self.assertIn("预期 %s" % wrong, err)
        self.assertIn("实构 %s" % digest, err, "报出的实构哈希须等于真实打包哈希")
        self.assert_zero_remote_writes(harness)
        self.assertEqual(fixture.artifacts(), [], "不一致时不留候选包半成品")
        self.assertFalse(fixture.rollback().exists(), "不得下载／写出回滚包")
        self.assertNotIn("模式：打包＋部署", out, "未进入写路径就不输出部署模式行")

    def test_source_change_after_digest_review_is_rc2_before_write_path(self):
        fixture = self.fixture(name="digest-drift-skill")
        digest = self.pack_digest(fixture)
        fixture.write_resource(RESOURCE_REL, b"changed-after-review\n")
        changed = self.pack_digest(fixture, sub="predigest2")
        self.assertNotEqual(changed, digest, "源变化后实构包必须不同（否则用例空转）")
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(deploy=True, expect_zip_sha256=digest))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：本地校验", err, "在写路径前的候选门禁命中，而非投后复核")
        self.assertIn("实构 %s" % changed, err)
        self.assert_zero_remote_writes(harness)
        self.assertEqual(fixture.artifacts(), [], "不一致时不留候选包")
        self.assertNotIn("阶段失败：源端复核", err)

    def test_invalid_digest_forms_are_rejected_as_parameters(self):
        fixture = self.fixture(name="digest-form-skill")
        good = "0" * 64
        bad_values = [(good[:63], "63 位"), (("a" * 64).upper(), "大写"),
                      ("sha256:" + good, "带前缀"), (good + "0", "65 位"),
                      ("z" * 64, "非十六进制"), (" " + good, "前导空格")]
        for value, label in bad_values:
            harness = Harness(fixture)
            rc, out, err = harness.run(fixture.args(deploy=True, expect_zip_sha256=value))
            self.assertEqual(rc, 2, "%s：%s" % (label, out + err))
            self.assertIn("阶段失败：本地校验", "%s：%s" % (label, err))
            self.assertIn("参数 --expect-zip-sha256 须为完整 64 位小写十六进制 SHA-256",
                          "%s：%s" % (label, err))
            self.assertNotIn(value, err, "格式不合格的值不得回显")
            self.assert_zero_remote_writes(harness)
            self.assertEqual(fixture.artifacts(), [], "%s：参数无效不产物" % label)

    def test_missing_value_for_gate_is_rc2(self):
        fixture = self.fixture(name="digest-noval-skill")
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(deploy=True) + ["--expect-zip-sha256"])
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：本地校验", err)
        self.assertIn("参数 --expect-zip-sha256 缺值", err)
        self.assert_zero_remote_writes(harness)
        self.assertEqual(fixture.artifacts(), [])

    def test_pack_only_mode_also_enforces_the_gate(self):
        fixture = self.fixture(name="digest-pack-skill")
        digest = self.pack_digest(fixture)
        wrong = sha256_bytes(b"wrong-pack-only")
        harness = Harness(fixture)
        rc, out, err = harness.run(fixture.args(expect_zip_sha256=wrong))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("候选 ZIP sha256 与 --expect-zip-sha256 不一致（未上传／未安装）", err)
        self.assertEqual(fixture.artifacts(), [], "只打包模式不一致也不写产物")
        self.assertEqual(harness.platform.calls, [], "零平台调用")
        rc, out, err = Harness(fixture).run(fixture.args(expect_zip_sha256=digest))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(sha256_bytes(fixture.candidate().read_bytes()), digest)
        self.assertIn("写路径：未进入", out)

    def test_trailing_newline_and_control_char_forms_are_rejected(self):
        """F1：`re.match` 的 `$` 容许「64 位合法 + 单 LF」——必须按**参数格式错误**拒绝且不回显。"""
        fixture = self.fixture(name="digest-eol-skill")
        good = "0" * 64
        cases = [(good + "\n", "单 LF"), (good + "\r\n", "CRLF"), ("", "空值"),
                 ("0" * 32 + "\x00" + "0" * 31, "内嵌 NUL"),
                 ("0" * 32 + "\x1b" + "0" * 31, "内嵌 ESC"),
                 ("0" * 32 + "\t" + "0" * 31, "内嵌 TAB"),
                 (good + " ", "尾随空格")]
        for value, label in cases:
            harness = Harness(fixture)
            rc, out, err = harness.run(fixture.args(deploy=True, expect_zip_sha256=value))
            joined = out + err
            self.assertEqual(rc, 2, "%s：%s" % (label, joined))
            self.assertIn("阶段失败：本地校验", joined, label)
            self.assertIn("参数 --expect-zip-sha256 须为完整 64 位小写十六进制 SHA-256",
                          joined, "%s：须是**参数格式**错误" % label)
            self.assertNotIn("未知参数", joined, "%s：不是「未知参数」分类" % label)
            self.assertNotIn("不一致", joined, "%s：未进入哈希比对分类" % label)
            if value:
                self.assertNotIn(value, out, "%s：stdout 不得回显输入" % label)
                self.assertNotIn(value, err, "%s：stderr 不得回显输入" % label)
            self.assertEqual(err.count("\n"), 1, "%s：只输出一行固定失败文案（控制字符不得注入）"
                             % label)
            self.assertEqual(harness.platform.calls, [], "%s：零平台调用" % label)
            self.assertEqual(harness.client.puts, [], "%s：零上传" % label)
            self.assertEqual(harness.client.gets, [], "%s：零 R2 读取" % label)
            self.assertEqual(fixture.artifacts(), [], "%s：零产物" % label)

    def test_duplicate_gate_parameter_is_rejected(self):
        """F2：仅**本门禁参数**重复即拒绝（同值／不同值／两种顺序），不回显、零远端、零产物。"""
        fixture = self.fixture(name="digest-dup-skill")
        first, second = "0" * 64, "a" * 64
        cases = [((first, first), "同值重复"), ((first, second), "不同值重复"),
                 ((second, first), "不同值重复·反序")]
        for pair, label in cases:
            harness = Harness(fixture)
            argv = (fixture.args(deploy=True)
                    + ["--expect-zip-sha256", pair[0], "--expect-zip-sha256", pair[1]])
            rc, out, err = harness.run(argv)
            joined = out + err
            self.assertEqual(rc, 2, "%s：%s" % (label, joined))
            self.assertIn("阶段失败：本地校验", joined, label)
            self.assertIn("参数 --expect-zip-sha256 不允许重复给出", joined, label)
            self.assertNotIn(pair[0], err, "%s：不得回显第一个值" % label)
            self.assertNotIn(pair[1], err, "%s：不得回显第二个值" % label)
            self.assert_zero_remote_writes(harness)
            self.assertEqual(fixture.artifacts(), [], "%s：零产物" % label)

    def test_other_parameter_duplicate_semantics_are_unchanged(self):
        """F2 边界：**其他**旧参数保留既有「后者覆盖」语义（本批只收紧新门禁参数）。"""
        fixture = self.fixture(name="digest-other-dup-skill")
        key = "%s.zip" % fixture.name
        harness = Harness(fixture)
        argv = fixture.args() + ["--key", key, "--name", fixture.name]
        rc, out, err = harness.run(argv)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("写路径：未进入", out)

    def test_matching_gate_still_stops_on_source_drift_before_write(self):
        """组合：携带**匹配**哈希参数时，构包后源变化仍由原 source_drift 在写前拦下（rc=2、零上传）。"""
        fixture = self.fixture(name="digest-window-skill")
        digest = self.pack_digest(fixture)
        state = {"done": False}

        def hook(args):
            if state["done"]:
                return
            state["done"] = True
            fixture.write_resource(RESOURCE_REL, b"changed-in-window\n")

        harness = Harness(fixture, platform_kwargs={"on_call": hook})
        rc, out, err = harness.run(fixture.args(deploy=True, expect_zip_sha256=digest))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：源端复核", err)
        self.assertIn("打包后源端已变化（未进入写路径；未上传）", err)
        self.assertNotIn("阶段失败：本地校验", err, "门禁本身已通过（匹配），拦住它的是源端复核")
        self.assert_zero_remote_writes(harness)
        self.assertFalse(fixture.rollback().exists(), "不得下载／写出回滚包")
        self.assertNotIn("回读判等：id／zipFileHash", out, "不得输出最终成功文案")


class DedicatedSurgePacker(FixtureCase):
    """专用打包器复用（luno-surge）：按登记源路径从同一审定仓库加载 `package_release.py`。

    判据（每项都断言退出码／字节事实）：① 纯打包走专用器（ZIP 时间戳／属性即专用布局，
    且产物 sha256 等于专用器内存构包）；② 专用器缺失**不回退**通用器（rc=2、零产物）；
    ③ `--deploy` 缺摘要时在**加载专用器之前** rc=2（模块缺失也不改分类，零 CLI／零 SDK）；
    ④ 摘要不符 rc=2、零产物、零远端；⑤ 秘密命中只报类别（`SecretError`）且不外流命中值、
    零产物；⑥ 源端复核（上传前）用的是同一个专用器：部署窗口内改源即拦下、零上传。
    其余技能路径由既有用例守住（`CandidateDigestGate` 的旧行为用例未改）。
    """

    PACKER_REL = "skills/luno-surge/scripts/package_release.py"

    def surge(self, with_packer=True):
        fixture = self.fixture(name="luno-surge", src_rel="skills/luno-surge")
        packer = fixture.repo / self.PACKER_REL
        if with_packer:
            packer.parent.mkdir(parents=True, exist_ok=True)
            packer.write_bytes((ROOT / self.PACKER_REL).read_bytes())
        # 登记真源里把源目录内的全部非 SKILL.md 文件登记为资源（含专用器自身），
        # 否则内置资源清单核对会先于本组判据失败（夹具问题，不是被测行为）。
        root = fixture.repo / "skills/luno-surge"
        # 取件门禁（目标就是 luno-surge）：声明 3 份参考原件并在位、哈希等于 manifest，再登记普通资源。
        official = {"references/upstream-SKILL.md": "SKILL.md",
                    "references/upstream-command-reference.md": "references/command-reference.md",
                    "references/plugin-authoring.md": "references/plugin-authoring.md"}
        blobs = {rel: ("fixture:%s\n" % key).encode() for rel, key in official.items()}
        for rel, blob in blobs.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        write_file(root / "references/upstream-manifest.json", json.dumps(
            {"raw_sha256": {key: sha256_bytes(blobs[rel]) for rel, key in official.items()}}))
        doc = json.loads((fixture.repo / "tools/sync-targets.json").read_text(encoding="utf-8"))
        doc["objects"][0]["officialPackageResources"] = {
            "paths": [fixture.src_rel + "/" + rel for rel in sorted(official)]}
        write_file(fixture.repo / "tools/sync-targets.json", json.dumps(doc, ensure_ascii=False))
        fixture.register_resources(sorted(
            str(path.relative_to(root)) for path in root.rglob("*")
            if path.is_file() and path.name != "SKILL.md" and str(path.relative_to(root)) not in official))
        return fixture

    def dedicated_digest(self, fixture):
        """期望值来源：**同一份**专用器在内存中收集＋构包的 sha256（部署入口复用的就是它）。"""
        import importlib.util
        path = str(fixture.repo / self.PACKER_REL)
        spec = importlib.util.spec_from_file_location("fixture_package_release", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        entries = module.collect(fixture.repo / "skills/luno-surge")
        return sha256_bytes(module.build(entries))

    def test_pure_pack_reuses_dedicated_packer_layout(self):
        fixture = self.surge()   # 登记（含取件声明，官方原件不进普通资源）已在夹具内完成
        root = fixture.repo / "skills/luno-surge"
        expected = sorted(str(path.relative_to(root)) for path in root.rglob("*")
                          if path.is_file())
        cp = fixture.run_tool(fixture.args())
        out, err = text_of(cp)
        self.assertEqual(0, cp.returncode, out + err)
        with zipfile.ZipFile(fixture.candidate()) as archive:
            self.assertEqual(expected, archive.namelist())
            info = archive.infolist()[0]
            # 通用器用 (1980,1,1,0,0,0)；专用器固定 (2026,1,1,0,0,0) ⇒ 该断言即「用了专用器」
            self.assertEqual((2026, 1, 1, 0, 0, 0), info.date_time)
            mode_bits = info.external_attr >> 16
            # 专用器写 S_IFREG 位（通用器只有 0o644<<16，无文件类型位）⇒ 该断言即「用了专用器」；
            # 权限位沿用既有 os.access(X_OK) 语义（root 误判是已登记遗留，本批不改）。
            self.assertEqual(0o100000, mode_bits & 0o170000)
            self.assertIn(mode_bits & 0o7777, (0o644, 0o755))
        self.assertEqual(self.dedicated_digest(fixture),
                         sha256_bytes(fixture.candidate().read_bytes()),
                         "候选产物就是专用器内存构包的那份 bytes")
        self.assertIn("打包：files=%d" % len(expected), out)

    def test_missing_dedicated_packer_does_not_fall_back(self):
        fixture = self.surge(with_packer=False)
        # scripts 目录存在但模块缺失：断言「缺模块」这条既有 Fail（目录缺失另有其固定分类）
        (fixture.repo / "skills/luno-surge/scripts").mkdir(parents=True, exist_ok=True)
        cp = fixture.run_tool(fixture.args())
        out, err = text_of(cp)
        self.assertEqual(2, cp.returncode, out + err)
        self.assertIn("专用打包器模块缺失或不是普通文件", err)
        self.assertIn(self.PACKER_REL, err)
        self.assertEqual([], fixture.artifacts(), "失败不留候选包")

    def test_deploy_without_digest_is_rc2_before_loading_packer(self):
        fixture = self.surge(with_packer=False)     # 模块缺失：顺序若错会落到「缺辅助模块」
        cp = fixture.run_tool(fixture.args(deploy=True),
                              extra_env={"LUNO_DEPLOY_AUTHORIZED": "1"})
        out, err = text_of(cp)
        self.assertEqual(2, cp.returncode, out + err)
        self.assertIn("必须显式给出", err)
        self.assertIn("--expect-zip-sha256", err)
        self.assertIn("未加载专用打包器", err)
        self.assertNotIn("缺辅助模块", err, "先决条件必须先于专用器加载")
        self.assertEqual([], fixture.artifacts(), "零产物")
        self.assertEqual([], fixture.lh_calls(), "零平台访问")
        self.assertFalse(fixture.sdk_imported(), "零 SDK ⇒ 零 R2")

    def test_deploy_mismatched_digest_writes_nothing(self):
        fixture = self.surge()
        cp = fixture.run_tool(fixture.args(deploy=True, expect_zip_sha256="0" * 64),
                              extra_env={"LUNO_DEPLOY_AUTHORIZED": "1"})
        out, err = text_of(cp)
        self.assertEqual(2, cp.returncode, out + err)
        self.assertIn("候选 ZIP sha256 与 --expect-zip-sha256 不一致", err)
        self.assertEqual([], fixture.artifacts(), "零产物")
        self.assertEqual([], fixture.lh_calls(), "零远端")
        self.assertFalse(fixture.sdk_imported())

    # ── A1-V：导入前拒绝的可观察证据（真实加载器读取探针＋固定绝对 marker 路径）──
    POISON_MARKER = "POISON_MARKER_9f3a"

    def poison_source(self, marker_path):
        """毒化模块源码：一旦被导入即写**固定绝对路径**的已执行标记，并抛带合成标记的异常。"""
        return ("open(%r, 'w').write('x')\n" % str(marker_path)
                + "raise RuntimeError(%r)\n" % self.POISON_MARKER)

    def read_probe(self):
        """装在**被测真实加载器**的数据读取缝 `SourceFileLoader.get_data` 上的可观察探针。

        不替换 `load_module`、也不 mock 不存在的读取点：`get_data` 正是 `exec_module` 读取模块
        源码时调用的方法。故「未读取即 0 次」与「读取即 ≥1 次（由正控证明）」都可观察。
        """
        import importlib.machinery
        real = importlib.machinery.SourceFileLoader.get_data
        reads = []

        def probe(self, path):
            reads.append(os.path.abspath(path))
            return real(self, path)

        importlib.machinery.SourceFileLoader.get_data = probe

        def restore():
            importlib.machinery.SourceFileLoader.get_data = real
        return reads, restore

    def run_inproc(self, fixture, args):
        harness = Harness(fixture)
        rc, out, err = harness.run(args)
        return harness, rc, out, err

    def assert_zero_side_effects(self, fixture, harness):
        self.assertEqual([], fixture.artifacts(), "零产物")
        self.assertEqual(0, harness.platform.uploads(), "零远端上传")
        self.assertEqual([], harness.platform.installed_calls(), "零 install")
        self.assertEqual([], harness.platform.edits(), "零 edit")
        self.assertEqual([], harness.client.gets, "零 R2 读取")

    def test_module_symlink_is_rejected_before_reading_target(self):
        fixture = self.surge(with_packer=False)
        marker_path = Path(os.path.abspath(str(fixture.root / "poison-executed.marker")))
        target = fixture.root / "poison_packer.py"
        write_file(target, self.poison_source(marker_path))
        packer = fixture.repo / self.PACKER_REL
        packer.parent.mkdir(parents=True, exist_ok=True)
        packer.symlink_to(target)
        blocked = {os.path.abspath(str(packer)), os.path.abspath(str(target))}
        reads, restore = self.read_probe()
        try:
            harness, rc, out, err = self.run_inproc(fixture, fixture.args())
        finally:
            restore()
        self.assertEqual(2, rc, out + err)
        self.assertIn("阶段失败：本地校验", err)
        self.assertIn("模块本身是符号链接", err)
        self.assertEqual([], [p for p in reads if p in blocked],
                         "拒绝必须**先于导入**：链接与其目标读取次数均为 0")
        self.assertFalse(marker_path.exists(), "固定绝对 marker 不存在 ⇒ 目标未被执行")
        self.assertNotIn(self.POISON_MARKER, out + err, "异常文本不得外流")
        self.assert_zero_side_effects(fixture, harness)

    def test_scripts_dir_symlink_is_rejected_before_reading_target(self):
        fixture = self.surge(with_packer=False)
        marker_path = Path(os.path.abspath(str(fixture.root / "poison-executed.marker")))
        elsewhere = fixture.root / "elsewhere/scripts"
        elsewhere.mkdir(parents=True)
        (elsewhere / "package_release.py").write_text(self.poison_source(marker_path),
                                                      encoding="utf-8")
        scripts = fixture.repo / "skills/luno-surge/scripts"
        scripts.parent.mkdir(parents=True, exist_ok=True)
        scripts.symlink_to(elsewhere)
        blocked = {os.path.abspath(str(elsewhere / "package_release.py")),
                   os.path.abspath(str(scripts / "package_release.py"))}
        reads, restore = self.read_probe()
        try:
            harness, rc, out, err = self.run_inproc(fixture, fixture.args())
        finally:
            restore()
        self.assertEqual(2, rc, out + err)
        self.assertIn("scripts 目录是符号链接", err)
        self.assertEqual([], [p for p in reads if p in blocked],
                         "拒绝先于导入：目标模块与经链接的路径读取次数均为 0")
        self.assertFalse(marker_path.exists(), "固定绝对 marker 不存在 ⇒ 目标未被执行")
        self.assertNotIn(self.POISON_MARKER, out + err)
        self.assert_zero_side_effects(fixture, harness)

    def test_read_probe_observes_legit_module_load(self):
        """正控：同一探针在**合法普通模块**加载时必然可见 ⇒ 上面的 0 次断言非恒真。"""
        fixture = self.surge()
        packer_path = os.path.abspath(str(fixture.repo / self.PACKER_REL))
        self.assertFalse(os.path.islink(fixture.repo / self.PACKER_REL))
        reads, restore = self.read_probe()
        try:
            harness, rc, out, err = self.run_inproc(fixture, fixture.args())
        finally:
            restore()
        self.assertEqual(0, rc, out + err)
        self.assertIn(packer_path, reads, "正控：探针必须观察到真实加载器对该模块的读取")

    def test_import_failure_is_rc2_class_only(self):
        for body, expect in (("raise RuntimeError('POISON_MARKER_9f3a')\n", "RuntimeError"),
                             ("def (\n", "SyntaxError"),
                             ("raise SystemExit('POISON_MARKER_9f3a')\n", "SystemExit")):
            fixture = self.surge()
            (fixture.repo / self.PACKER_REL).write_text(body, encoding="utf-8")
            cp = fixture.run_tool(fixture.args())
            out, err = text_of(cp)
            self.assertEqual(2, cp.returncode, out + err)
            self.assertIn("专用打包器导入失败（%s）" % expect, err)
            self.assertNotIn("POISON_MARKER_9f3a", out + err, "异常文本不得外流")
            self.assertEqual([], fixture.artifacts(), "零产物")
            self.assertEqual([], fixture.lh_calls(), "零远端")
            self.assertFalse(fixture.sdk_imported())

    def test_secret_hit_is_rc2_category_only(self):
        fixture = self.surge()
        marker = "ghp_" + "A" * 24        # 合成形态，不是任何真实凭据
        write_file(fixture.repo / "skills/luno-surge/references/leak.md", marker + "\n")
        cp = fixture.run_tool(fixture.args())
        out, err = text_of(cp)
        self.assertEqual(2, cp.returncode, out + err)
        self.assertIn("SecretError", err)
        self.assertNotIn(marker, out + err, "命中值不得外流")
        self.assertNotIn("leak.md", err, "只给固定类别，不回显专用器消息")
        self.assertEqual([], fixture.artifacts())

    def test_source_drift_uses_same_dedicated_packer(self):
        fixture = self.surge()
        digest = self.dedicated_digest(fixture)
        state = {"done": False}

        def hook(args):
            if state["done"]:
                return
            state["done"] = True
            fixture.write_resource(RESOURCE_REL, b"changed-in-window\n")

        harness = Harness(fixture, platform_kwargs={"on_call": hook})
        rc, out, err = harness.run(fixture.args(deploy=True, expect_zip_sha256=digest))
        self.assertEqual(2, rc, out + err)
        self.assertIn("阶段失败：源端复核", err)
        self.assertIn("打包后源端已变化（未进入写路径；未上传）", err)
        self.assertEqual(0, harness.platform.uploads(), "零上传")
        self.assertEqual([], harness.client.gets, "零 R2 读取")
        self.assertFalse(fixture.rollback().exists(), "不得下载／写出回滚包")

    def test_path_selection_routes_dedicated_packer_to_deploy(self):
        cp = subprocess.run([sys.executable, "-B", str(ROOT / "tests" / "test_paths.py"),
                             "select-paths"],
                            input=b"skills/luno-surge/scripts/package_release.py\x00",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(0, cp.returncode, cp.stderr.decode("utf-8", "replace"))
        selected = json.loads(cp.stdout.decode("utf-8"))
        self.assertIn(["case", "test-deploy-skill.py"], selected,
                      "专用器被部署入口消费 ⇒ 变更必须选到 deploy 消费者")
        self.assertIn(["case", "test-surge-scripts.py"], selected)
        self.assertNotIn(["full"], selected, "单文件变更不升级为 full")


class OfficialPackageFetchGate(unittest.TestCase):
    """S3：取件门禁只对部署目标 luno-surge 强制（SOURCE.md〈取件与部署〉）；合成字节，不联网。"""

    ORIGINALS = {
        "skills/luno-surge/references/upstream-SKILL.md": "SKILL.md",
        "skills/luno-surge/references/upstream-command-reference.md": "references/command-reference.md",
        "skills/luno-surge/references/plugin-authoring.md": "references/plugin-authoring.md",
    }
    SOURCE_MD = "skills/luno-surge/references/SOURCE.md"
    MANIFEST = "skills/luno-surge/references/upstream-manifest.json"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="test-official-gate-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.ns = load_source_namespace(TOOL.read_text(encoding="utf-8"))
        self.blobs = {rel: ("synthetic:%s\n" % key).encode("utf-8")
                      for rel, key in self.ORIGINALS.items()}
        write_file(self.root / self.MANIFEST, json.dumps({"raw_sha256": {
            key: sha256_bytes(self.blobs[rel]) for rel, key in self.ORIGINALS.items()}}))
        write_file(self.root / "skills/luno-surge/SKILL.md", "---\nname: luno-surge\n---\n")
        write_file(self.root / self.SOURCE_MD, "来源\n")
        write_file(self.root / "skills/luno-core/SKILL.md", "---\nname: luno-core\n---\n")
        self.surge = {"id": "luno-surge", "type": "skill",
                      "source": "skills/luno-surge/SKILL.md",
                      "resources": [self.SOURCE_MD, self.MANIFEST],
                      "officialPackageResources": {"paths": sorted(self.ORIGINALS)}}
        self.core = {"id": "luno-core", "type": "skill",
                     "source": "skills/luno-core/SKILL.md", "resources": []}

    def fetch(self):  # 〈取件与部署〉第 3 步的合成等价物：按 manifest 字节落盘
        for rel, blob in self.blobs.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(blob)

    def check(self, target, objects=None):
        """走真实调用点 `check_inventory(登记, 根, 本次 --src)`；rc=0 表示放行。"""
        try:
            self.ns["check_inventory"](objects or [self.surge, self.core],
                                       str(self.root), target)
        except self.ns["Fail"] as exc:
            return exc.rc, exc.detail
        return 0, ""

    def test_other_target_ignores_missing_originals(self):
        """正控：部署 luno-core 不因 Surge 缺件失败（r1 实测被连带判 rc=2）。"""
        self.assertEqual((0, ""), self.check("skills/luno-core"))

    def test_surge_target_requires_fetched_originals(self):
        """缺件拒绝→取件后放行；取件后在包内也不判漏登记。"""
        rc, detail = self.check("skills/luno-surge")
        self.assertEqual(2, rc)
        self.assertIn("官方参考原件缺失", detail)
        self.assertIn("取件与部署", detail)
        self.fetch()
        self.assertEqual((0, ""), self.check("skills/luno-surge"))
        self.assertEqual([], self.ns["compare_resource_inventory"](
            {"objects": [self.surge, self.core]}, str(self.root)))

    def test_surge_target_rejects_broken_declaration(self):
        """负控：删掉／写坏声明后 Surge 被拒（rc=2／rc=1），同登记的 luno-core 不受影响。"""
        no_decl = {k: v for k, v in self.surge.items() if k != "officialPackageResources"}
        rc, detail = self.check("skills/luno-surge", [no_decl, self.core])
        self.assertEqual(2, rc)
        self.assertIn("完整声明", detail)
        self.assertEqual(0, self.check("skills/luno-core", [no_decl, self.core])[0])
        self.fetch()
        part = dict(self.surge, officialPackageResources={"paths": sorted(self.ORIGINALS)[:2]})
        rc, detail = self.check("skills/luno-surge", [part, self.core])
        self.assertEqual(2, rc, "声明缺项同样拒绝")
        self.assertIn("登记异常", detail)

    def test_tampered_original_rejected(self):
        self.fetch()
        (self.root / "skills/luno-surge/references/plugin-authoring.md").write_bytes(b"tampered\n")
        rc, detail = self.check("skills/luno-surge")
        self.assertEqual(2, rc)
        self.assertIn("哈希不符", detail)

    def test_declaration_misuse_is_registry_error(self):
        """双登记／不可映射路径／别处豁免 → 登记异常 rc=1（G2 负控同方向）。"""
        block = {"paths": ["skills/luno-core/references/delegation.md"]}
        dup = [self.SOURCE_MD, self.MANIFEST,
               "skills/luno-surge/references/upstream-SKILL.md"]
        for label, target, objects in (
            ("双登记", "skills/luno-surge", [dict(self.surge, resources=dup), self.core]),
            ("不可映射", "skills/luno-surge", [dict(self.surge, officialPackageResources={
                "paths": sorted(self.ORIGINALS) + [
                    "skills/luno-surge/references/command-reference.md"]}), self.core]),
            ("别处豁免", "skills/luno-core",
             [self.surge, dict(self.core, officialPackageResources=block)]),
        ):
            rc, detail = self.check(target, objects)
            self.assertEqual(2, rc, label)
            self.assertIn("登记异常", detail, label)


if __name__ == "__main__":
    unittest.main()

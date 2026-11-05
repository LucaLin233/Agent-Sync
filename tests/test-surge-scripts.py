#!/usr/bin/env python3
"""surge 脚本离线回归（修复批 A：3xx 不外泄认证头、成功输出统一脱敏；修复批 B：共用脱敏模块与 CLI 输出边界）。

覆盖三项已授权修复面，全部**离线**：只连 `127.0.0.1` 上的本地夹具，用哑值
`SURGE_API_KEY=test` 与 `SURGE_HTTP_API_BASE=http://127.0.0.1:<port>`，经**真实子进程入口**
执行 `skills/luno-surge/scripts/*.py`；不联网、不用真凭据、不写仓库内文件。

修复批 A 判据（每条都写明它在修复前会红在哪一步）：
1. 负控 A：夹具回 302 且 `Location` 指向第二个本地端口 ⇒ 命令失败，且第二个端口**收不到带
   `X-Key` 的请求**（夹具记录收到的头）。修复前默认 `urlopen` 会跟随 3xx 并把 `X-Key`
   原样转发到新目标，本用例即在此断言上红。
2. 负控 A2：`test_policy_descriptor.py` 同一泄漏面（修复前同样跟随后把 `X-Key` 送出去，
   且 stdout 走「正常结果」分支、无 `http_error`）。
3. 负控 B：夹具回 200 ＋ 含 `password`/`x-key` 的 JSON ⇒ stdout/stderr 不得出现原值。
   修复前 `show()` 直出未脱敏。
4. 正控：夹具回普通 200 JSON ⇒ 正常输出、退出码 0（脱敏不得破坏普通响应）。

修复批 B 判据（`_privacy.py` 共用模块＋`surge_cli.py` 全输出边界；缺口①–⑤各一例）：
5. 递归脱敏：`{"a": {"credential": …}}`、数组内对象、复数键/驼峰键的**整个值**被替换，
   非敏感字段原样保留。
6. 缺口①：Profile 代理行 `NAME = https, host, 443, user, <PASS>` 整行凭据位置被抹；
   负控 `Group = select, A, B`／`FINAL,DIRECT` 不受影响。
7. 缺口②：前缀驼峰键 `proxyPassword`；缺口③：复数键 `tokens`；缺口④：数组内裸字符串值
   `["A","B"]`；缺口⑤：已转义/内层 JSON 串 `{\"token\":\"X\"}`（且外层仍是合法 JSON）。
8. `surge_cli.py` 的 raw／render／错误／`profile diff` 四条输出路径都脱敏（修复前
   `surge_cli.py` 完全没有脱敏，四条路径任一条都会红）。
9. `--check` 校验服务的成功与失败输出都脱敏（模块内直接调用＋替换 `urlopen`，仍不联网）。
10. 出网门禁统一：`test_policy_descriptor.py --api-base` 与 HTTP 回退同口径拒绝非本机目标
    与含 userinfo 的 URL；凭据只来自 `SURGE_API_KEY`／`--password-stdin`。

上游同步批（2026-11-01 覆盖层迁移）判据，见 `UpstreamAdapterTest`：
11. 覆盖层保留脱敏、最小 dump、nil 引号、LSP 与超时和完整双读等约束；不拼接官方正文。
12. 原件只读分类 raw，历史成品只读分类 adapted；覆盖层与未知哈希拒绝，所有入口不写。
    旧生成 API 一律拒绝；真实原件入口重复执行不改变字节或 mode。
13. 原件缺失、混合或重复关键内容时哈希准入拒绝；变异原件在 prepare 暂存前拒绝。
14. 保留的官方原文副本（`references/upstream-command-reference.md`）哈希必须仍在该适配器的
    `REVIEWED_SHA256` 内：provenance 与门禁同源。

重量自证（2026-10-12 R1 补；口径按 `skills/luno-sync/references/test-authoring.md`〈降耗〉〈准入〉）：
15. **跑集与降级路径**：本文件在 `run-tests.sh` 表中登记为 `test-surge-scripts.py|surge|…|0|1`——第 4 列
    是 `smoke`＝0（**不进 `smoke`**），第 5 列是常跑＝1（**进 `full`**），两列不可混读；按命中跑
    `sh tests/run-tests.sh group surge`（或 `case test-surge-scripts.py`）；
    再收窄到本批单例用 `python3 -B -m unittest -v test-surge-scripts.FailClosedRedactionTest.test_r1_…`。
    **不得只跑新增例替代整入口**：真实子进程／离线 HTTP 夹具那几组（3xx 不外泄认证头、raw／render／
    错误／`profile diff` 四条输出路径、`--check` 服务、出网门禁）与新增负控共用同一个 `_privacy.py`，
    只跑新增例就漏掉既有面的回归。
16. **体积与例数**：53,979 B（2026-10-12 收紧批之前）→63,217 B→73,862 B（R1 批）→82,186 B（R2／R4
    批，R4 未回改本条）→**93,323 B**（`16e2323` 快照）→**93,365 B**（`78b7930` 快照）；**本头不缓存当前字节数**——当前体积与增量由发布者按**待发布的 Git blob** 实算并记入当批条目（本条自身改动会改变文件大小，缓存值必然自相矛盾）；
    例数 63→70（R1）→**74**（R4，实读 `Ran 74 tests`）→**78**（本轮 R3，新增 4 条，见 18）。
    超 20 KB 属既有大文件的历史形态，本条按〈准入〉报增量、由发布者裁定。
17. **耗时（本机 iSH 实测，2026-10-12）**：整入口 `cd tests && python3 -B -m unittest -v
    test-surge-scripts` 当天实测 17.4 s／19.1 s／27.7 s／56.0 s（同命令同日可差 3 倍以上，iSH 负载波动）；
    `FailClosedRedactionTest` 单独 0.04 s。**必须保留真实子进程＋离线 HTTP 夹具**：那些面只有走真实入口
    才覆盖进程边界、退出码与「第二个端口收不到凭据」类断言，换成函数级调用等价于删判据；**新增 5 条
    负控必须保留**：每条对应一个曾在基线与候选**同时残留标记**的漏面，删掉即回到「声称闭合而实际未闭合」。
18. **R3 批（2026-10-12，独立复审判 N1／N2）**：N1＝3b 尾段兜底的容器豁免被 R2 改成**无条件**成立，
    「容器开头」被当成「尾段无秘密」的充分条件（`token=["x]", <标记>`／`token={"x": "}", <标记>` 的
    括号计数被引号内字符骗过、`token=[ "a" ], <标记>` 是已闭合容器＋携密引号尾段 ⇒ 尾段残留且不幂等）；
    N2＝`_CONTAINER_OPEN` 的 `rest` 接受任意裸值，物理行里同行前置键的匹配整行吃进（非重叠扫描前移），
    跨物理行容器的整份 fail-closed 不触发、续行原样输出。守它们的用例＝
    `R3ContainerExemptionAndScanPositionTest` 4 条（27 格「前置键×容器×引号变体×跨物理行」组合矩阵＋
    6 格 N1 形态逐字节期望值＋合法 JSON 逐字节形状的反向判据＋N1／N2 同文档组合）。撤防变异实测：
    ①豁免无条件（＝R2 旧形）⇒ 红 `test_n1_container_exemption_is_gated_to_json_documents`；
    ②豁免恒假 ⇒ 红 `test_n1_gate_keeps_legal_json_byte_shapes`；③`redact_text()` 去掉「按 JSON 文档
    门控」⇒ 红同上；④`_CONTAINER_OPEN` 的 `rest` 改回旧形 ⇒ 红
    `test_n2_same_line_key_does_not_swallow_cross_line_scan` 与 `test_n1_and_n2_faces_in_one_document`。
    本批实测（本机 iSH）：`case test-surge-scripts.py` 17 s；整入口 `python3 -B -m unittest`
    18.7 s（verbose 46.3 s）；`test-redact.py` 20 例 2.1 s（当时测量，不作为 B 档跑集或耗时承诺）。
19. **安装态档（2026-10-30）**：`acceptance.sh` 新增 `--installed`（离线档＋PATH 安装点核验，
    用例见 `InstalledTierTest`）。缺陷面＝`--offline` 不校验安装点：技能目录 `surge`→`luno-surge`
    改名后 `/usr/local/bin/surge-cli` 悬空、目标脚本又是 644，离线档仍 PASS。用例把整份技能包
    复制到临时目录，经**真实脚本入口**跑，用 `SURGE_CLI_BIN`／`SURGE_CLI_LINK` 注入隔离落点，
    逐类断言失败类别（缺失／断链／目标错／不可执行）与「离线档不读安装点、不执行 CLI、不写
    包目录」；`install.sh` 核验不通过即非零退出且不打印 `Installed:`，且核验按 **PATH 里的
    `surge-cli` 名字**解析（F1：装到 PATH 之外、或 PATH 前方有同名旧副本，都不算成功）。
    本组 11 例实测：整组 5.1–6.3 s（9 例时同机同口径 5.2 s），新增 2 例 1.1 s。
    撤防实测：删安装点核验整块 ⇒ 4 条负控红；删可执行位／realpath／存在性判据 ⇒ 对应用例各红；
    `install.sh` 去掉核验调用 ⇒ 「不打印成功语」负控红。
20. **公开发布快照两态（2026-11-06，待他批 N1 落地）**：`SurgeReleaseSnapshotTest` 原按公开态
    单态断言三份官方原件不在技能目录与 ZIP 中，按 manifest 部署取件后重跑必红。现改为两态：
    公开态（三件全不在）保持原断言；取件态（三件全在且逐件 sha256 等于 manifest
    `raw_sha256`：`SKILL.md`→`references/upstream-SKILL.md`、`references/command-reference.md`
    →`references/upstream-command-reference.md`、`references/plugin-authoring.md`→同名落点）
    断言三份原件**进包**且归档字节等于盘上字节——依据 `package_release.py` 的 `collect()`：
    排除表只含目录名／后缀／名单（`__pycache__`、`.pem`、`secrets.env` 等），不含这三条路径，
    故 `build()` 会把它们一并归档。部分在位或在位但哈希不符 ⇒ `self.fail()` 显式失败，不 skip。
    例数不变（一例换一例，仍 78）。
"""
import contextlib
import errno
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import socketserver
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/luno-surge/scripts'
SURGE_IOS = SCRIPTS / 'surge_ios.py'
POLICY_DESCRIPTOR = SCRIPTS / 'test_policy_descriptor.py'
SURGE_CLI = SCRIPTS / 'surge_cli.py'

# 哑值，不是任何真实凭据。
API_KEY = 'test'


def load_module(name, path):
    """按文件路径加载脚本模块（不执行 `main()`）。"""
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRIVACY = load_module('surge_privacy_under_test', SCRIPTS / '_privacy.py')

# 上游同步批（2026-10-11，官方 Surge Mac 6.10.0 导入）：适配器与官方原文副本（用例见
# UpstreamAdapterTest）。
ADAPTER = load_module('surge_adapter_under_test', SCRIPTS / 'adapt_upstream_reference.py')
COMMAND_REFERENCE = ROOT / 'skills/luno-surge/references/command-reference.md'
UPSTREAM_COMMAND_REFERENCE = ROOT / 'skills/luno-surge/references/upstream-command-reference.md'

# 官方原件不随公开仓库分发（2026-11-06 公开快照）：需要真实官方原文字节的用例在本仓库缺该文件时
# skip，并在部署取件（`references/SOURCE.md`〈取件与部署〉）后重跑；仓库侧「不含原件」这一状态
# 另由 `OfficialFilesAbsentTest` 正面核，不用 skip 掩盖。
OFFICIAL_PRESENT = UPSTREAM_COMMAND_REFERENCE.is_file()
requires_official = unittest.skipUnless(
    OFFICIAL_PRESENT, '公开仓库不含官方原件；按 SOURCE.md〈取件与部署〉装入后重跑')

# 官方原文形状的最小夹具：§1 前言待替换、封装标题待归一、§5 的 dump-profile 句待改写、
# `<nil>` 待加引号。**刻意复刻官方的折行方式**——只按单行字面匹配的实现会在 §5 句上静默放过。
RAW_FIXTURE = '''# Surge CLI / Controller Command Reference (for AI Agents)

## 1. CLI Usage

### 1.1 Basic format

```bash
surge-cli [--remote host:port] [--password-stdin] [--raw] <command> [args...]
```

- `--help` / `-h`: print help.

### 1.2 Response envelope

Responses are JSON objects.

## 5. Practical Recommendations for AI Agents

1. Use the default rendered output.
2. Start network troubleshooting with `status` and `dump summary`; before
   mutating settings, also collect relevant context with `environment`,
   `dump policy`, and `dump profile`.
3. For streaming commands, handle incremental chunks.

```bash
surge-cli set AutoPolicyGroupOverride.Streaming=<nil>
```
'''

# 夹具里上游 §5 句的原始形态（跨行），供「旧产物缺改写」的构造复用。
RAW_FIXTURE_SENTENCE = ('before\n'
                        '   mutating settings, also collect relevant context with `environment`,\n'
                        '   `dump policy`, and `dump profile`.')


def x_key_of(request):
    """按大小写不敏感取该请求携带的 X-Key 值（urllib 会把它规范成 `X-key`）；未带则 None。"""
    return {k.lower(): v for k, v in request['headers'].items()}.get('x-key')


class LocalFixture:
    """`127.0.0.1` 本地 HTTP 夹具：记录收到的请求（方法/路径/头），按 responder 应答。"""

    def __init__(self, responder):
        self.requests = []
        self._responder = responder
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_GET(self):
                fixture._handle(self)

            def do_POST(self):
                fixture._handle(self)

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={'poll_interval': 0.05}, daemon=True)
        self._thread.start()

    def _handle(self, handler):
        length = int(handler.headers.get('Content-Length') or 0)
        if length:
            handler.rfile.read(length)
        self.requests.append({'method': handler.command, 'path': handler.path,
                              'headers': {k: v for k, v in handler.headers.items()}})
        status, headers, body = self._responder()
        handler.send_response(status)
        for name, value in headers.items():
            handler.send_header(name, value)
        handler.send_header('Content-Length', str(len(body)))
        handler.end_headers()
        if body:
            handler.wfile.write(body)

    @property
    def base(self):
        return 'http://127.0.0.1:%d' % self._server.server_address[1]

    def close(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class LocalController:
    """`127.0.0.1` 本地 Controller 协议夹具（离线）：

    收密码行 → 回欢迎帧 → 收命令行 → 回一帧 JSON 响应。用于让 `surge_cli.py` 走**真实子进程**
    路径收到可控的服务端载荷，从而检验其输出边界。记录收到的密码与命令行（用于断言凭据来源）。
    """

    def __init__(self, response):
        self.passwords = []
        self.commands = []
        self.payload = response
        fixture = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                password = self.rfile.readline()
                fixture.passwords.append(password.rstrip(b'\r\n').decode('utf-8', 'replace'))
                self.wfile.write(json.dumps({'result': 'Welcome to Surge CLI'}).encode() + b'\r\n')
                line = self.rfile.readline()
                fixture.commands.append(line.rstrip(b'\r\n').decode('utf-8', 'replace'))
                self.wfile.write(json.dumps(fixture.payload).encode() + b'\r\n')

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._server = Server(('127.0.0.1', 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={'poll_interval': 0.05}, daemon=True)
        self._thread.start()

    @property
    def remote(self):
        return '127.0.0.1:%d' % self._server.server_address[1]

    def close(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def offline_env(base=None, api_key=API_KEY):
    """哑凭据＋本地 base，并剥掉代理环境变量以保证离线。"""
    env = dict(os.environ)
    for name in ('http_proxy', 'https_proxy', 'all_proxy',
                 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        env.pop(name, None)
    env.pop('SURGE_ALLOW_REMOTE', None)
    env.pop('SURGE_ALLOW_SENSITIVE', None)
    env['SURGE_API_KEY'] = api_key
    if base is None:
        env.pop('SURGE_HTTP_API_BASE', None)
    else:
        env['SURGE_HTTP_API_BASE'] = base
    return env


def run_script(script, args, base=None, stdin=None, timeout=60):
    """经真实子进程入口执行脚本。"""
    return subprocess.run([sys.executable, str(script), *args], env=offline_env(base),
                          input=stdin, capture_output=True, text=True, timeout=timeout)


def run_cli(args, remote=None, stdin=None, api_key=API_KEY, timeout=60):
    """经真实子进程入口执行 `surge_cli.py`（离线、哑凭据）。"""
    env = offline_env()
    env['SURGE_API_KEY'] = api_key
    if remote is not None:
        args = [*args, '--remote', remote]
    return subprocess.run([sys.executable, str(SURGE_CLI), *args], env=env, input=stdin,
                          capture_output=True, text=True, timeout=timeout)


class RedirectTest(unittest.TestCase):
    """负控 A／A2：3xx 不得被跟随，认证头不得被转发到重定向目标（跨源泄漏）。"""

    def _pair(self):
        """第一个端口回 302 指向第二个端口；两个夹具都记录收到的头。"""
        target = LocalFixture(lambda: (200, {'Content-Type': 'application/json'},
                                       b'{"result": {"status": 200}}'))
        self.addCleanup(target.close)
        sink = LocalFixture(lambda: (302, {'Location': target.base + '/v1/leaked'}, b'moved'))
        self.addCleanup(sink.close)
        return sink, target

    def _assert_redirect_blocked(self, sink, target):
        # 前置事实：请求确实带着 X-Key 打到了第一个端口（否则本负控是空转的永真）
        self.assertEqual([API_KEY], [x_key_of(q) for q in sink.requests])
        # 判据：重定向目标端口未收到带 X-Key 的请求
        self.assertEqual([], [q for q in target.requests if x_key_of(q) is not None])
        self.assertEqual([], target.requests)

    def test_surge_ios_does_not_follow_redirect(self):
        sink, target = self._pair()
        r = run_script(SURGE_IOS, ['outbound'], base=sink.base)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('HTTP 302', r.stderr)
        self._assert_redirect_blocked(sink, target)

    def test_policy_descriptor_does_not_follow_redirect(self):
        sink, target = self._pair()
        r = run_script(POLICY_DESCRIPTOR, ['--api-base', sink.base, '--descriptor-file', '-'],
                       stdin='PROBE-9c4e = http, 127.0.0.1, 1080\n')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('"http_error": 302', r.stdout)
        self._assert_redirect_blocked(sink, target)


class RedactionTest(unittest.TestCase):
    """负控 B／正控：成功路径与 fail() 同口径脱敏，普通响应不受影响。"""

    SECRETS = ('SYNTH-PASSWORD-9c4e', 'SYNTH-XKEY-9c4e')

    def test_success_body_secrets_are_redacted(self):
        body = json.dumps({'password': self.SECRETS[0], 'x-key': self.SECRETS[1],
                           'policy': 'Proxy'}).encode()
        fixture = LocalFixture(lambda: (200, {'Content-Type': 'application/json'}, body))
        self.addCleanup(fixture.close)

        r = run_script(SURGE_IOS, ['policies'], base=fixture.base)

        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for secret in self.SECRETS:
            self.assertNotIn(secret, r.stdout, r.stdout)
            self.assertNotIn(secret, r.stderr, r.stderr)
        self.assertIn('<redacted>', r.stdout)
        self.assertIn('Proxy', r.stdout)  # 非敏感字段仍原样可读

    def test_plain_success_output_is_unchanged(self):
        fixture = LocalFixture(lambda: (200, {'Content-Type': 'application/json'},
                                        b'{"outbound": "proxy", "enabled": true}'))
        self.addCleanup(fixture.close)

        r = run_script(SURGE_IOS, ['outbound'], base=fixture.base)

        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('"outbound": "proxy"', r.stdout)
        self.assertIn('"enabled": true', r.stdout)


class RecursiveRedactionTest(unittest.TestCase):
    """递归脱敏与五类缺口（⑤ 的合法 JSON 约束也在此面内）。"""

    def test_nested_and_array_values_are_whole_replaced(self):
        raw = {'policy': 'Proxy', 'a': {'credential': {'inner': 'SYNTH-N1'}},
               'list': [{'proxyPassword': 'SYNTH-N2'}, 'keep'],
               'tokens': ['SYNTH-N3', 'SYNTH-N4']}
        text = PRIVACY.dumps_redacted(raw, indent=2)
        for leaked in ('SYNTH-N1', 'SYNTH-N2', 'SYNTH-N3', 'SYNTH-N4'):
            self.assertNotIn(leaked, text, text)
        # 整值替换：命中键的值不是原地部分替换
        self.assertEqual(PRIVACY.redact_obj(raw)['a']['credential'], '<redacted>')
        self.assertEqual(PRIVACY.redact_obj(raw)['tokens'], '<redacted>')
        self.assertIn('"policy"', text)       # 非敏感字段保留
        self.assertIn('"keep"', text)

    def test_proxy_line_credentials_are_redacted(self):
        """缺口①：`NAME = <type>, host, port, user, <PASS>` 整行不抹。"""
        profile = ('[Proxy]\n'
                   'PROXY-A = https, 127.0.0.1, 443, synthuser, SYNTH-PASS-A\n'
                   'N2 = snell, 127.0.0.1, 8388, SYNTH-PSK-B, version=4\n'
                   'GroupA = select, A, B\n'
                   'FINAL,DIRECT\n')
        text = PRIVACY.redact_text(profile)
        self.assertNotIn('SYNTH-PASS-A', text, text)
        self.assertNotIn('synthuser', text, text)
        self.assertNotIn('SYNTH-PSK-B', text, text)
        self.assertIn('version=4', text)            # 非凭据尾随参数保留
        self.assertIn('GroupA = select, A, B', text)  # 策略组行不受影响
        self.assertIn('FINAL,DIRECT', text)

    def test_proxy_slot_credentials_are_not_shape_exempted(self):
        """负控（2026-10-12 定向审查 F1／F2）：凭据位**不按字段外形放行**。

        位置式口径下 `sni=…`／`version=…`／`a=b`／base64 形态的值都可能**就是口令本身**；
        `headers=`／`ws-headers=` 又是可携密容器（Cookie）。本模块对这些一律整值抹除——不设
        「已知非凭据参数」白名单（该白名单曾使 `headers=Cookie:…` 由抹除变成保留）。
        """
        base = 'P = https, example.com, 443, synthuser, '
        for value in ('SYNTHdGVzdA==', 'a=b', 'sni=SYNTH-PASS-1', 'version=SYNTH-PASS-2',
                      '"SNI=SYNTH-PASS-3"'):
            text = PRIVACY.redact_text(base + value)
            self.assertNotIn('synthuser', text, text)
            self.assertNotIn('SYNTH-PASS', text, text)
            self.assertNotIn(value, text, text)      # F7：值本身必须消失，不得只查无关子串
        for line in ('P = https, example.com, 443, headers=Cookie:session=SYNTH-COOKIE-1',
                     'P = vmess, example.com, 443, ws-headers=Cookie:session=SYNTH-COOKIE-2, '
                     'username=SYNTH-UUID-1'):
            text = PRIVACY.redact_text(line)
            self.assertNotIn('SYNTH-COOKIE', text, text)
            self.assertNotIn('SYNTH-UUID', text, text)

    def test_extra_named_credentials_are_redacted(self):
        """2026-10-12 官方手册核验：`uuid`／`auth-key` 与未列类型的命名凭据不漏抹。"""
        for line, leaked in (
                ('P = ss, 1.2.3.4, 8388, encrypt-method=aes-256-gcm, password=SYNTH-SS-1',
                 ('SYNTH-SS-1',)),
                ('P = tuic-v5, 1.2.3.4, 443, uuid=SYNTH-UUID-1, password=SYNTH-T5-1',
                 ('SYNTH-UUID-1', 'SYNTH-T5-1')),
                ('P = h2-connect, 1.2.3.4, 443, username=synthuser2, password=SYNTH-H2-1',
                 ('synthuser2', 'SYNTH-H2-1')),
                ('P = masque, 1.2.3.4, 443, username=synthuser3, password=SYNTH-MQ-1',
                 ('synthuser3', 'SYNTH-MQ-1')),
                ('[Tailscale ts1]\nauth-key = SYNTH-AUTH-1\nhostname = surge',
                 ('SYNTH-AUTH-1',)),
                ('[WireGuard wg1]\nprivate-key = SYNTH-WG-1\nself-ip = 10.0.0.2',
                 ('SYNTH-WG-1',))):
            text = PRIVACY.redact_text(line)
            for item in leaked:
                self.assertNotIn(item, text, text)

    def test_quoted_credential_with_comma_does_not_leak_tail(self):
        """F6（既有）：官方「Quote a value if it contains commas」——引号口令不得被 `split(",")`
        拆开而泄漏尾段；同时须保留 host/port 可读。"""
        for line in ('P = https, h, 443, synthuser, "SYNTH-PASS-1,TAIL-A"',
                     'P = https, h, 443, synthuser, "SYNTH-PASS-2\nTAIL-B"',
                     r'P = https, h, 443, synthuser, "SYNTH-PASS-3\nTAIL-C"',
                     'P = https, h, 443, synthuser, password="SYNTH-PASS-4,TAIL-D',
                     "P = https, h, 443, synthuser, 'SYNTH-PASS-5,TAIL-E'"):
            text = PRIVACY.redact_text(line)
            for leaked in ('SYNTH-PASS', 'TAIL-', 'synthuser'):
                self.assertNotIn(leaked, text, text)
            self.assertIn('https, h, 443,', text, text)

    def test_literal_newline_boundary_named_credentials(self):
        """F8：字面 `\\n` 之后的命名凭据须被抹除，且不得把后续 `hostname` 吞进秘密值。

        三类值形态各命中一条防线——裸值 `_KEY_BARE`、带引号值 `_KEY_QUOTED`、容器值
        `_KEY_CONTAINER`；三者键起点都在本轮加了字面 `\\n` 边界，故须各有一例（否则撤掉
        后两条改动仍绿、用例无判别力）。
        """
        for line, leaked in (
                (r'[Tailscale ts1]\nauth-key=SYNTH-AUTH-1\nhostname = h', ('SYNTH-AUTH-1',)),
                (r'[Tailscale ts1]\npassword=SYNTH-PASS-1\nhostname = h', ('SYNTH-PASS-1',)),
                (r'[Tailscale ts1]\npassword="SYNTH-PASS-2,SYNTH-TAIL-2"\nhostname = h',
                 ('SYNTH-PASS-2', 'SYNTH-TAIL-2')),
                (r'[Tailscale ts1]\npassword:["SYNTH-PASS-3","SYNTH-TAIL-3"]\nhostname = h',
                 ('SYNTH-PASS-3', 'SYNTH-TAIL-3'))):
            text = PRIVACY.redact_text(line)
            for item in leaked:
                self.assertNotIn(item, text, text)
            self.assertIn(r'\nhostname = h', text, text)
            # 两层 JSON 包装：逐层解析回来核验，且内层后缀完整保留
            out = PRIVACY.redact_boundary(json.dumps({'data': line}))
            for item in leaked:
                self.assertNotIn(item, out, out)
            out = PRIVACY.redact_boundary(json.dumps({'data': out}))
            for item in leaked:
                self.assertNotIn(item, out, out)
            inner = json.loads(json.loads(out)['data'])['data']
            self.assertEqual(inner, text, inner)

    def test_camel_prefix_and_plural_keys_are_redacted(self):
        """缺口②／③：`proxyPassword` 与 `tokens` 均不命中。"""
        text = PRIVACY.redact_text('{"proxyPassword": "SYNTH-C1", "tokens": ["SYNTH-C2"]}')
        self.assertNotIn('SYNTH-C1', text, text)
        self.assertNotIn('SYNTH-C2', text, text)

    def test_array_of_bare_strings_is_redacted(self):
        """缺口④：数组内裸字符串值不抹。"""
        text = PRIVACY.redact_text('{"tokens": ["SYNTH-D1", "SYNTH-D2"]}')
        self.assertNotIn('SYNTH-D1', text, text)
        self.assertNotIn('SYNTH-D2', text, text)

    def test_escaped_inner_json_is_redacted_and_stays_valid_json(self):
        """缺口⑤：已转义／内层 JSON 串不抹，且外层输出仍是合法 JSON。"""
        payload = json.dumps({'detail': json.dumps({'token': 'SYNTH-E1',
                                                    'tokens': ['SYNTH-E2'], 'policy': 'Proxy'})})
        text = PRIVACY.redact_text(payload)
        self.assertNotIn('SYNTH-E1', text, text)
        self.assertNotIn('SYNTH-E2', text, text)
        decoded = json.loads(text)
        inner = json.loads(decoded['detail'])       # 内层串本身也须仍是合法 JSON
        self.assertEqual(inner['token'], '<redacted>')
        self.assertEqual(inner['tokens'], ['<redacted>'])   # 容器整值替换，形态保留
        self.assertEqual(inner['policy'], 'Proxy')
        self.assertIn('Proxy', text)

    def test_output_boundary_entry_handles_documents_and_text(self):
        """输出边界入口：整段 JSON 文档走结构化路径（嵌套容器整值），其余走文本路径。"""
        nested = PRIVACY.redact_boundary('{"token":[["SYNTH-G1"]]}')
        self.assertNotIn('SYNTH-G1', nested, nested)
        self.assertEqual(PRIVACY.redact_obj({'token': [['SYNTH-G1']]})['token'], '<redacted>')

        pretty = PRIVACY.redact_boundary('{\n  "password": "SYNTH-G2",\n  "policy": "Proxy"\n}')
        self.assertNotIn('SYNTH-G2', pretty, pretty)
        self.assertIn('"policy": "Proxy"', pretty)

        # 非 JSON 文本与不可逐字节重排的 JSON 都保持文本路径，不改变输出形状
        for text in ('PROXY = https, h, 443, u, SYNTH-G3\n',
                     'Error: password=SYNTH-G4 failed',
                     '{ "password":"SYNTH-G5" }'):
            out = PRIVACY.redact_boundary(text)
            self.assertNotIn('SYNTH-G', out, out)
            self.assertEqual(PRIVACY.redact_boundary(out), out, out)

    def test_idempotent_and_negative_controls(self):
        samples = ['{"outbound": "proxy", "enabled": true}',
                   '{"user-agent": "Surge/5.0"}',
                   'basic configuration failed',
                   'policy-path = https://example.com/sub?token=SYNTH-F1']
        for sample in samples:
            once = PRIVACY.redact_text(sample)
            self.assertEqual(PRIVACY.redact_text(once), once, sample)
        self.assertNotIn('SYNTH-F1', PRIVACY.redact_text(samples[-1]))
        self.assertEqual(PRIVACY.redact_text(samples[1]), samples[1])
        self.assertEqual(PRIVACY.redact_text(samples[2]), samples[2])


class SurgeCliOutputTest(unittest.TestCase):
    """缺口补齐：`surge_cli.py` 的全部输出边界（修复前完全没有脱敏）。"""

    PROFILE = 'PROXY-A = https, 127.0.0.1, 443, synthuser, SYNTH-CLI-PASS\nFINAL,DIRECT\n'

    def _cli(self, payload, args):
        controller = LocalController(payload)
        self.addCleanup(controller.close)
        return run_cli(args, remote=controller.remote), controller

    def test_raw_output_is_redacted(self):
        payload = {'result': {'password': 'SYNTH-CLI-1', 'tokens': ['SYNTH-CLI-2'],
                              'policy': 'Proxy'}}
        r, controller = self._cli(payload, ['--raw', 'policy-group', 'list'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('SYNTH-CLI-1', r.stdout, r.stdout)
        self.assertNotIn('SYNTH-CLI-2', r.stdout, r.stdout)
        self.assertIn('Proxy', r.stdout)
        self.assertEqual([API_KEY], controller.passwords)  # 凭据只来自 SURGE_API_KEY

    def test_rendered_output_is_redacted(self):
        payload = {'result': {'sections': [{'section': 'Summary', 'lines': [
            {'title': 'Password', 'content': 'SYNTH-CLI-3'}]}]}}
        r, _ = self._cli(payload, ['summary'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('SYNTH-CLI-3', r.stdout, r.stdout)

    def test_error_output_is_redacted(self):
        payload = {'error': 'authentication failed: password=SYNTH-CLI-4', 'code': 1}
        r, _ = self._cli(payload, ['policy-group', 'list'])
        self.assertEqual(r.returncode, 1)
        self.assertNotIn('SYNTH-CLI-4', r.stderr, r.stderr)
        self.assertIn('<redacted>', r.stderr)

    def test_profile_diff_output_is_redacted(self):
        payload = {'originalProfile': 'PROXY-A = https, 127.0.0.1, 443, u, SYNTH-CLI-5\n',
                   'profile': self.PROFILE}
        r, _ = self._cli(payload, ['profile', 'diff'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('SYNTH-CLI-5', r.stdout, r.stdout)
        self.assertNotIn('SYNTH-CLI-PASS', r.stdout, r.stdout)
        self.assertIn('PROXY-A', r.stdout)  # diff 结构与非敏感内容保留

    def test_multiline_quoted_credential_in_summary_and_diff(self):
        """F6＋N1／N2（真实入口）：跨行引号口令经 `summary` 与 `profile diff` 不得泄漏尾段；
        diff 的 hunk 计数须与正文一致，host/port 保留。"""
        payload = {'sections': [{'section': 'Warnings', 'lines': [
            {'title': 'Proxy',
             'content': 'P = https, host1, 443, synthuser, "SYNTH-CLI-7,\nSYNTH-CLI-TAIL2"'}]}]}
        r, _ = self._cli(payload, ['summary'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for leaked in ('SYNTH-CLI-7', 'SYNTH-CLI-TAIL2', 'synthuser'):
            self.assertNotIn(leaked, r.stdout, r.stdout)
        self.assertIn('host1, 443', r.stdout)          # host/port 仍可读

        payload = {'originalProfile': ('PROXY-A = https, 127.0.0.1, 443, u, "SYNTH-CLI-6,\n'
                                       'SYNTH-CLI-TAIL"\nDOMAIN-SUFFIX,example.com,DIRECT\n'),
                   'profile': self.PROFILE + 'DOMAIN-SUFFIX,example.org,DIRECT\n'}
        r, _ = self._cli(payload, ['profile', 'diff'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for leaked in ('SYNTH-CLI-6', 'SYNTH-CLI-TAIL'):
            self.assertNotIn(leaked, r.stdout, r.stdout)
        self.assertIn('example.org', r.stdout)         # 非敏感差异仍可见

        lines = r.stdout.splitlines()
        headers = [l for l in lines if l.startswith('@@')]
        self.assertEqual(len(headers), 1, r.stdout)    # 整份先脱敏 ⇒ 单一自洽 hunk
        body = [l for l in lines if l[:1] in ' +-'
                and not l.startswith(('+++', '---'))]
        ctx = sum(1 for l in body if l.startswith(' '))
        rem = sum(1 for l in body if l.startswith('-'))
        add = sum(1 for l in body if l.startswith('+'))
        declared = [int(p.split(',')[-1]) for p in headers[0].split()[1:3]]
        self.assertEqual(declared, [ctx + rem, ctx + add], r.stdout)

    def test_plain_render_output_is_unchanged(self):
        payload = {'result': 'proxy'}
        r, _ = self._cli(payload, ['mode'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), 'proxy')


class ValidationServiceTest(unittest.TestCase):
    """`--check` 校验服务的输出同样脱敏（模块内调用＋替换 `urlopen`，不联网）。"""

    def _run(self, result, raw):
        module = load_module('surge_cli_under_test', SURGE_CLI)

        class Response(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request)
            return Response(json.dumps(result).encode())

        profile = SCRIPTS.parent / 'SKILL.md'       # 只作 UTF-8 上传源，内容不进判据（原用该技能 README，2026-10-11 瘦身删除后改用仍存在的 SKILL.md）
        module.urllib.request.urlopen = fake_urlopen
        captured = io.StringIO()
        captured_err = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured_err):
            with self.assertRaises(SystemExit) as exit_info:
                module.validate_profile(str(profile), raw)
        return exit_info.exception.code, captured.getvalue(), captured_err.getvalue(), calls

    def test_check_failure_message_is_redacted(self):
        code, stdout, stderr, _ = self._run(
            {'valid': False, 'error': {'message': 'profile rejected: password=SYNTH-CHK-1'}},
            False)
        self.assertEqual(code, 1)
        self.assertNotIn('SYNTH-CHK-1', stderr, stderr)
        self.assertIn('Failed:', stderr)

    def test_check_raw_output_is_redacted(self):
        code, stdout, _, _ = self._run(
            {'valid': True, 'warnings': [{'tokens': ['SYNTH-CHK-2'], 'line': 7}]}, True)
        self.assertEqual(code, 0)
        self.assertNotIn('SYNTH-CHK-2', stdout, stdout)
        self.assertEqual(json.loads(stdout)['valid'], True)


class ApiBaseGateTest(unittest.TestCase):
    """出网门禁统一：`--api-base` 与 HTTP 回退同口径，凭据只来自环境/ stdin。"""

    OFF_LOOPBACK = sorted({entry[4][0] for entry in
                           socketserver.socket.getaddrinfo('localhost', 6171, type=1)})

    def test_remote_api_base_is_rejected(self):
        r = run_script(POLICY_DESCRIPTOR,
                       ['--api-base', 'http://192.0.2.10:6171', '--descriptor-file', '-'],
                       stdin='PROBE-9c4e = http, 127.0.0.1, 1080\n')
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('SURGE_ALLOW_REMOTE', r.stderr, r.stderr)

    def test_userinfo_api_base_is_rejected(self):
        r = run_script(POLICY_DESCRIPTOR,
                       ['--api-base', 'http://user:SYNTH-GATE-1@127.0.0.1:6171',
                        '--descriptor-file', '-'],
                       stdin='PROBE-9c4e = http, 127.0.0.1, 1080\n')
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('SYNTH-GATE-1', r.stdout + r.stderr)   # 凭据不得回显
        self.assertIn('must not embed URL credentials', r.stderr, r.stderr)

    def test_non_http_api_base_is_rejected(self):
        r = run_script(POLICY_DESCRIPTOR,
                       ['--api-base', 'ftp://127.0.0.1:6171', '--descriptor-file', '-'],
                       stdin='PROBE-9c4e = http, 127.0.0.1, 1080\n')
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('must use http or https', r.stderr, r.stderr)

    def test_localhost_api_base_still_passes_gate(self):
        """正控：本机 base 不被门禁挡下（夹具可达即证明已越过门禁）。"""
        fixture = LocalFixture(lambda: (200, {'Content-Type': 'application/json'},
                                       b'{"result": {"status": 200}}'))
        self.addCleanup(fixture.close)
        r = run_script(POLICY_DESCRIPTOR,
                       ['--api-base', fixture.base, '--descriptor-file', '-'],
                       stdin='PROBE-9c4e = http, 127.0.0.1, 1080\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # 门禁已越过：请求确实带 X-Key 打到了本机夹具（否则是空转的永真）
        self.assertEqual([API_KEY], [x_key_of(q) for q in fixture.requests])
        self.assertIn('"node": "PROBE-9c4e"', r.stdout)

    def test_remote_gate_allows_explicit_opt_in(self):
        """显式 `SURGE_ALLOW_REMOTE=1` 是唯一放行远端的方式。

        **离线**：直接调共享门禁判据，不发起任何网络请求（原实现真向 `192.0.2.10` 发包，
        「预期不可达」不等于离线，2026-10-11 定向复审指出）。
        """
        os.environ.pop('SURGE_ALLOW_REMOTE', None)
        try:
            self.assertIsNotNone(PRIVACY.api_base_problem('http://192.0.2.10:6171'))
            os.environ['SURGE_ALLOW_REMOTE'] = '1'
            self.assertIsNone(PRIVACY.api_base_problem('http://192.0.2.10:6171'))
        finally:
            os.environ.pop('SURGE_ALLOW_REMOTE', None)


class CliContractTest(unittest.TestCase):
    """CLI 公开表面不变：帮助文本逐字节保留，且不因脱敏接线被改写。"""

    EXPECTED = ('Available parameters:', '  --raw - Output raw JSON instead of human-readable format',
                '  Remote password: SURGE_API_KEY 或 --password-stdin（不读凭据文件，也不交互补取）',
                '  --check/-c <path> - Validate a profile with the official Surge beta service')

    def test_help_text_is_unchanged(self):
        for args in (['--help'], []):
            r = run_cli(args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for line in self.EXPECTED:
                self.assertIn(line, r.stdout, r.stdout)
            self.assertNotIn('<redacted>', r.stdout)   # 帮助里没有凭据，不该被启发式改写

    def test_per_command_help_is_unchanged(self):
        r = run_cli(['help', 'dump'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('dump <type> [arguments]', r.stdout)
        self.assertNotIn('<redacted>', r.stdout)

    def test_symlinked_entry_point_resolves_shared_module(self):
        """install.sh 以符号链接落 `/usr/local/bin/surge-cli`，共享模块须按 realpath 解析。"""
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'surge-cli'
            link.symlink_to(SURGE_CLI)
            env = offline_env()
            # 用 runpy 显式执行链接（此时 `sys.path[0]` 不是脚本所在目录），
            # 只有按 realpath 解析才能找到同级 `_privacy.py`。
            # 只传 `--help`：该分支不建连接，避免碰到宿主 127.0.0.1:6170 上的实例。
            r = subprocess.run([sys.executable, '-c',
                                "import runpy, sys; sys.argv = [sys.argv[1], '--help'];"
                                " runpy.run_path(sys.argv[0], run_name='__main__')",
                                str(link)], env=env, cwd=tmp, capture_output=True, text=True,
                               timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Surge CLI (Minis Controller Edition)', r.stdout)
        self.assertNotIn('ModuleNotFoundError', r.stderr)


class FixRoundTest(unittest.TestCase):
    """定向复审必修项回归：Unicode 节点名、输出包装崩溃、入参错误脱敏、嵌套容器口径。

    每条都写明修复前的失败点，避免空转断言。
    """

    def test_unicode_proxy_name_credentials_are_redacted(self):
        """缺口①补：名称含中文/Unicode 时整行凭据位仍须抹除。

        修复前名称字符类只允许 ASCII，`香港节点 = …` 整行不匹配 ⇒ 密码原样输出。
        """
        out = PRIVACY.redact_text('香港节点 = https, node.example.com, 443, user, SYNTH-UNI-1')
        self.assertNotIn('SYNTH-UNI-1', out, out)
        self.assertIn('香港节点 = https, node.example.com, 443,', out)

    def test_unicode_proxy_name_in_diff_and_serialized_profile(self):
        """覆盖 `profile diff` 行首标记与序列化 Profile 两种形态。

        diff 夹具用**无 ASCII 尾缀**的名称（`东京节点`）——旧 ASCII 正则能匹配 `东京 02` 的
        尾部 `02`，那种夹具杀不死旧实现，没有区分力（2026-10-11 复审判 N2）。
        """
        for prefix in ('+', '-'):
            out = PRIVACY.redact_text(
                '%s东京节点 = socks5, 1.2.3.4, 1080, user, SYNTH-UNI-2' % prefix)
            self.assertNotIn('SYNTH-UNI-2', out, out)
            self.assertTrue(out.startswith(prefix), out)     # 行首标记保留
        serialized = PRIVACY.redact_boundary(
            '{"profile": "香港节点 = https, node.example.com, 443, user, SYNTH-UNI-3"}')
        self.assertNotIn('SYNTH-UNI-3', serialized, serialized)
        self.assertTrue(json.loads(serialized)['profile'].startswith('香港节点 = https'))

    def test_dumps_redacted_keeps_valid_json(self):
        """回归 N1：结构化输出不得因代理行规则改写 JSON 包装字符而变成非法 JSON。"""
        for value in ({'profile': '香港节点 = https, h, 443, u, SYNTH-JSON-1'},
                      {'detail': 'NODE-A = https, h, 443, u, SYNTH-JSON-2'},
                      {'nested': {'profile': '香港节点 = socks5, 1.2.3.4, 1080, u, SYNTH-JSON-3'}}):
            out = PRIVACY.dumps_redacted(value)
            json.loads(out)                                  # 非法 JSON 在此抛错
            self.assertNotIn('SYNTH-JSON-', out, out)
            self.assertIn('<redacted>', out)

    def test_top_level_json_string_keeps_valid_json(self):
        """回归 N5：顶层 JSON 字符串（`json.dumps("…")`）须走结构化边界。

        修复前 `redact_boundary()` 只认 `{`/`[` 开头，字符串文档落进文本路径 ⇒ 闭合引号被当
        末字段吃掉，输出成非法 JSON。
        """
        payload = json.dumps('NODE = snell, h, 443, SYNTH-TOP-1')
        for label, out in (('boundary', PRIVACY.redact_boundary(payload)),
                           ('redact', PRIVACY.redact(payload))):
            self.assertEqual(json.loads(out), 'NODE = snell, h, 443, <redacted>', label)
        outer = PRIVACY.redact_boundary(json.dumps({'detail': payload, 'keep': 'OK'},
                                                   ensure_ascii=False, separators=(',', ':')))
        parsed = json.loads(outer)
        self.assertEqual(parsed['keep'], 'OK')                     # 非敏感字段保留
        self.assertEqual(json.loads(parsed['detail']), 'NODE = snell, h, 443, <redacted>')

    def test_raw_scalar_string_output_is_valid_json(self):
        """真实 CLI 路径：Controller 回**标量字符串**时 `--raw` 输出仍须可解析。"""
        fixture = LocalController('NODE = snell, h, 443, SYNTH-TOP-2')
        self.addCleanup(fixture.close)
        r = run_cli(['--raw', 'status'], remote=fixture.remote)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        json.loads(r.stdout)                                       # 非法 JSON 在此抛错
        self.assertNotIn('SYNTH-TOP-2', r.stdout, r.stdout)

    def test_auth_keys_are_redacted_structurally(self):
        """回归 N3：认证键须由结构化路径整值替换，不能只靠序列化后的文本兜住。

        修复前 `_SENSITIVE_KEY` 不含认证键，撤掉序列化后文本处理时这些值直接泄漏。
        """
        value = {'Authorization': 'Bearer SYNTH-AUTH-1', 'proxyAuth': 'SYNTH-AUTH-2',
                 'authz': 'SYNTH-AUTH-3', 'nested': [{'auth': 'SYNTH-AUTH-4'}]}
        for label, out in (('dumps_redacted', PRIVACY.dumps_redacted(value)),
                           ('redact', PRIVACY.redact(value))):
            self.assertNotIn('SYNTH-AUTH-', out, '%s: %s' % (label, out))
            self.assertIn('<redacted>', out)
            json.loads(out)

    def test_json_layouts_keep_valid_json_and_unrelated_fields(self):
        """三种 JSON 布局 × 单字段／嵌套／数组／后随字段：不泄漏、JSON 合法、非敏感字段保留。"""
        profile = '香港节点 = https, h, 443, u, SYNTH-LAY-1'
        shapes = ({'profile': profile},
                  {'nested': {'profile': profile}},
                  {'profiles': [profile]},
                  {'profile': profile, 'keep': 'OK'})
        dumps = (lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':')),
                 lambda o: json.dumps(o, ensure_ascii=False),
                 lambda o: json.dumps(o, ensure_ascii=False, indent=2))
        for shape in shapes:
            for dump in dumps:
                out = PRIVACY.redact_boundary(dump(shape))
                self.assertNotIn('SYNTH-LAY-1', out, out)
                parsed = json.loads(out)                  # 任何布局都必须仍是合法 JSON
                if 'keep' in shape:                        # 按**夹具**决定验收，不按输出
                    self.assertIn('keep', parsed, out)     # 实现若删掉该键即变红
                    self.assertEqual(parsed['keep'], 'OK')

    def test_unicode_name_does_not_widen_to_policy_groups(self):
        """负控：Unicode 化名称不得把策略组行一并抹掉（夹具用 Unicode 组名，才有区分力）。"""
        self.assertEqual(PRIVACY.redact_text('香港组 = select, A, B'), '香港组 = select, A, B')
        self.assertEqual(PRIVACY.redact_text('Proxy = select, A, B'), 'Proxy = select, A, B')
        self.assertEqual(PRIVACY.redact_text('FINAL,DIRECT'), 'FINAL,DIRECT')

    def test_summary_sections_do_not_crash_and_keep_blank_lines(self):
        """`render_summary` 末尾用 `out()` 输出空行。

        修复前 `out(text, end=...)` 无默认值 ⇒ `TypeError: out() missing 1 required
        positional argument`；原测试把数据包在 `result` 层，走 JSON 回退分支，故未发现。
        """
        module = load_module('surge_cli_summary_fix_round', SURGE_CLI)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            module.render_summary({'sections': [{'section': 'DNS', 'lines': [
                {'title': 'server', 'content': '1.1.1.1\npassword=SYNTH-SUM-1'}]}]})
        text = buf.getvalue()
        self.assertIn('DNS:', text)
        self.assertIn('\n\n', text)             # 小节后的空行确实由 out() 写出
        self.assertNotIn('SYNTH-SUM-1', text)

    def test_vmnet_ra_does_not_crash_and_keeps_blank_lines(self):
        """`render_vmnet(..., 'ra')` 每个小节后同样用 `out()`。"""
        module = load_module('surge_cli_vmnet_fix_round', SURGE_CLI)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            module.render_vmnet(['vmnet', 'ra'], {'clients': [
                {'ip': '10.0.0.2', 'mac': 'aa:bb', 'password': 'SYNTH-RA-1'}]})
        text = buf.getvalue()
        self.assertIn('RA takeover clients (1):', text)
        self.assertIn('\n\n', text)
        self.assertNotIn('SYNTH-RA-1', text)

    def test_argparse_errors_are_redacted(self):
        """入参解析错误同样不得回显取值。

        修复前两入口用原生 `argparse`，`argparse` 把取值拼进错误消息 ⇒ stderr 含原值。
        """
        r = run_script(SURGE_IOS, ['--raw', 'password=SYNTH-ARG-1'])
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('SYNTH-ARG-1', r.stdout + r.stderr, r.stderr)
        d = run_script(POLICY_DESCRIPTOR, ['--bogus', 'password=SYNTH-ARG-2'])
        self.assertNotEqual(d.returncode, 0, d.stdout + d.stderr)
        self.assertNotIn('SYNTH-ARG-2', d.stdout + d.stderr, d.stderr)
        # 子解析器的取值/整数错误同口径（子解析器由 add_subparsers 按父解析器类型创建）
        for script, args in ((SURGE_IOS, ['kill', 'password=SYNTH-ARG-3']),
                             (SURGE_IOS, ['outbound', 'password=SYNTH-ARG-5']),
                             (POLICY_DESCRIPTOR, ['--timeout', 'password=SYNTH-ARG-4'])):
            r = run_script(script, args)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn('SYNTH-ARG-', r.stdout + r.stderr, r.stderr)

    def test_nested_container_coverage_in_json_layouts(self):
        """嵌套容器在**任一种 JSON 布局**下都按结构整值替换（紧凑走结构化、非紧凑走 token 扫描）。

        2026-10-11 第三轮复审判 N1 后覆盖扩大：原先只有满足「紧凑 JSON 可原样重排」判据才保证，
        现在非紧凑布局同样覆盖。**未覆盖的只剩「非 JSON 文本形态」**（JSON 嵌在普通句子里的那种）。
        """
        for label, text in (('紧凑', '{"token":[["SYNTH-NEST-1"]]}'),
                            ('缩进', '{"token": [\n  ["SYNTH-NEST-2"]\n]}')):
            out = PRIVACY.redact_boundary(text)
            self.assertNotIn('SYNTH-NEST', out, '%s：%s' % (label, out))
            json.loads(out)                                  # 仍须是合法 JSON
        # 边界（2026-10-12 收紧）：非 JSON 文本里的嵌套容器现由 `_KEY_CONTAINER_TAIL` 兜底——
        # 敏感键后是嵌套／未闭合容器时**整段隐藏**；代价是该逻辑行容器之后的文本一并消失。
        plain = '响应正文：{"token":[["SYNTH-NEST-3"]]} 结束'
        out = PRIVACY.redact_boundary(plain)
        self.assertNotIn('SYNTH-NEST-3', out, out)
        self.assertIn('响应正文：', out, out)


class UpstreamAdapterTest(unittest.TestCase):
    """覆盖层安全承重及官方原件只读分类；拒绝旧生成接口。"""

    ERROR = ('Unreviewed reference: neither reviewed official raw text nor a known '
             'historical adapted product; nothing was written.')
    DISABLED = ('Reference generation is disabled: command-reference.md is a manually '
                'maintained overlay; use classify() or the read-only CLI.')

    @contextlib.contextmanager
    def _record_writes(self):
        calls = []
        original = Path.write_bytes
        def spy(path, data):
            calls.append(str(path))
            return original(path, data)
        Path.write_bytes = spy
        try:
            yield calls
        finally:
            Path.write_bytes = original

    def test_overlay_preserves_every_local_override(self):
        out = COMMAND_REFERENCE.read_text(encoding='utf-8')
        for text in ('客户端脱敏、不是服务端原文', '不得默认全量收集',
                     "surge-cli set 'AutoPolicyGroupOverride.Streaming=<nil>'",
                     'Minis 不实现，不得向 Controller 转发', '60 秒', '8 秒',
                     '30 秒', '包含首帧等待', '外部限时停止', '先完整读本覆盖层，再完整读'):
            self.assertIn(text, out)
        self.assertNotIn('surge-cli set AutoPolicyGroupOverride.Streaming=<nil>', out)
        self.assertEqual(1, out.count("surge-cli set 'AutoPolicyGroupOverride.Streaming=<nil>'"))
        self.assertNotIn('also collect relevant context with', out)
        self.assertNotIn('### 1.4 Response envelope', out)

    def test_historical_classifier_never_writes(self):
        from unittest.mock import patch
        self.assertTrue(ADAPTER.ADAPTED_SHA256)
        for digest in ADAPTER.ADAPTED_SHA256:
            self.assertEqual('adapted', ADAPTER.classify(digest))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'historical'
            path.write_bytes(b'synthetic historical CLI fixture')
            before, mode = path.read_bytes(), path.stat().st_mode
            digest = hashlib.sha256(before).hexdigest()
            with patch.object(ADAPTER, 'classify', return_value='adapted'), \
                 self._record_writes() as calls, contextlib.redirect_stdout(io.StringIO()) as out:
                ADAPTER.main([str(path)])
            self.assertEqual('adapted sha256=' + digest + '\n', out.getvalue())
            self.assertEqual([], calls)
            self.assertEqual((before, mode), (path.read_bytes(), path.stat().st_mode))

    def test_shipped_overlay_is_never_official_or_historical(self):
        data = COMMAND_REFERENCE.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        self.assertNotIn(digest, ADAPTER.REVIEWED_SHA256)
        self.assertNotIn(digest, ADAPTER.ADAPTED_SHA256)
        self.assertEqual('unknown', ADAPTER.classify(digest))
        with self.assertRaises(SystemExit) as ex:
            ADAPTER.adapt_text(data.decode())
        self.assertEqual(self.DISABLED, str(ex.exception))

    def test_entry_refuses_overlay_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'overlay'
            path.write_bytes(COMMAND_REFERENCE.read_bytes())
            before, mode = path.read_bytes(), path.stat().st_mode
            with self._record_writes() as calls, contextlib.redirect_stdout(io.StringIO()) as out:
                with self.assertRaises(SystemExit) as ex:
                    ADAPTER.main([str(path)])
            self.assertEqual(self.ERROR, str(ex.exception))
            self.assertEqual('', out.getvalue())
            self.assertEqual([], calls)
            self.assertEqual((before, mode), (path.read_bytes(), path.stat().st_mode))
            r = subprocess.run([sys.executable, str(SCRIPTS / 'adapt_upstream_reference.py'), str(path)],
                               env=offline_env(), capture_output=True, text=True)
            self.assertEqual((1, '', self.ERROR + '\n'), (r.returncode, r.stdout, r.stderr))
            self.assertEqual((before, mode), (path.read_bytes(), path.stat().st_mode))

    def test_generation_api_rejects_historical_product(self):
        # 原始已登记 hash 可证明历史身份，不凭伪造夹具声称命中真实历史原文。
        self.assertTrue(ADAPTER.ADAPTED_SHA256)
        for digest in ADAPTER.ADAPTED_SHA256:
            self.assertEqual('adapted', ADAPTER.classify(digest))
        for text in (RAW_FIXTURE, COMMAND_REFERENCE.read_text(encoding='utf-8'), ''):
            with self.assertRaises(SystemExit) as ex:
                ADAPTER.adapt_text(text)
            self.assertEqual(self.DISABLED, str(ex.exception))

    @requires_official
    def test_read_only_classification_survives_two_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'raw'
            path.write_bytes(UPSTREAM_COMMAND_REFERENCE.read_bytes())
            before, mode = path.read_bytes(), path.stat().st_mode
            digest = hashlib.sha256(before).hexdigest()
            self.assertEqual('raw', ADAPTER.classify(digest))
            for _ in range(2):
                with self._record_writes() as calls, contextlib.redirect_stdout(io.StringIO()) as out:
                    ADAPTER.main([str(path)])
                self.assertEqual([], calls)
                self.assertEqual('raw sha256=' + digest + '\n', out.getvalue())
                r = subprocess.run([sys.executable, str(SCRIPTS / 'adapt_upstream_reference.py'), str(path)],
                                   env=offline_env(), capture_output=True, text=True)
                self.assertEqual((0, 'raw sha256=' + digest + '\n', ''),
                                 (r.returncode, r.stdout, r.stderr))
                self.assertEqual((before, mode), (path.read_bytes(), path.stat().st_mode))

    @requires_official
    def test_unknown_input_never_writes(self):
        reviewed, adapted = set(ADAPTER.REVIEWED_SHA256), set(ADAPTER.ADAPTED_SHA256)
        with tempfile.TemporaryDirectory() as tmp:
            for source in (UPSTREAM_COMMAND_REFERENCE.read_bytes(), COMMAND_REFERENCE.read_bytes()):
                path = Path(tmp) / 'mutated'
                path.write_bytes(source + b'!')
                before, mode = path.read_bytes(), path.stat().st_mode
                self.assertEqual('unknown', ADAPTER.classify(hashlib.sha256(before).hexdigest()))
                with self._record_writes() as calls, self.assertRaises(SystemExit) as ex:
                    ADAPTER.main([str(path)])
                self.assertEqual(self.ERROR, str(ex.exception))
                self.assertEqual([], calls)
                self.assertEqual((before, mode), (path.read_bytes(), path.stat().st_mode))
        self.assertEqual(reviewed, ADAPTER.REVIEWED_SHA256)
        self.assertEqual(adapted, ADAPTER.ADAPTED_SHA256)

    @requires_official
    def test_changed_raw_text_is_not_admitted(self):
        raw = UPSTREAM_COMMAND_REFERENCE.read_text(encoding='utf-8')
        for old, new in (('surge-cli set AutoPolicyGroupOverride.Streaming=<nil>', 'surge-cli set X=<nil>'),
                         ('also collect relevant context with', 'collect nothing with'),
                         ('### 1.2 Response envelope', '### 9.9 Nope')):
            self.assertIn(old, raw)
            changed = raw.replace(old, new)
            self.assertNotIn(hashlib.sha256(changed.encode()).hexdigest(), ADAPTER.REVIEWED_SHA256)
            self.assertEqual('unknown', ADAPTER.classify(hashlib.sha256(changed.encode()).hexdigest()))

    @requires_official
    def test_mixed_or_duplicated_source_is_rejected(self):
        raw = UPSTREAM_COMMAND_REFERENCE.read_text(encoding='utf-8')
        nil = 'surge-cli set AutoPolicyGroupOverride.Streaming=<nil>'
        self.assertIn(nil, raw)
        for changed in (raw + '\n' + nil, raw + '\n' + COMMAND_REFERENCE.read_text(encoding='utf-8'),
                        raw + '\n' + RAW_FIXTURE_SENTENCE):
            self.assertEqual('unknown', ADAPTER.classify(hashlib.sha256(changed.encode()).hexdigest()))

    @requires_official
    def test_retained_official_copy_matches_the_reviewed_set(self):
        digest = hashlib.sha256(UPSTREAM_COMMAND_REFERENCE.read_bytes()).hexdigest()
        self.assertIn(digest, ADAPTER.REVIEWED_SHA256)
        self.assertTrue(ADAPTER.REVIEWED_SHA256)
        for reviewed in ADAPTER.REVIEWED_SHA256:
            self.assertEqual('raw', ADAPTER.classify(reviewed))
        self.assertTrue(ADAPTER.ADAPTED_SHA256.isdisjoint(ADAPTER.REVIEWED_SHA256))
        manifest = json.loads((ROOT / 'skills/luno-surge/references/upstream-manifest.json').read_text())
        self.assertEqual(digest, manifest['raw_sha256']['references/command-reference.md'])


DRIVER = r'''
import importlib.util, json, pathlib, runpy, subprocess, sys
script, mode = sys.argv[1], sys.argv[2]
cfg = json.loads(sys.argv[3])
LOG = cfg['log']
REAL_PATH = pathlib.Path
real_mkdir = pathlib.Path.mkdir
writable = mode in ('source', 'host')

def note(entry):
    with open(LOG, 'a', encoding='utf-8') as fh:
        fh.write(entry + '\n')

def guarded_mkdir(self, *args, **kwargs):
    note('mkdir:' + str(self))
    if not writable:
        raise SystemExit(90)
    return real_mkdir(self, *args, **kwargs)

def blocked(name):
    def stub(argv, *args, **kwargs):
        note(name + ':' + ' '.join(map(str, argv if isinstance(argv, (list, tuple)) else [argv])))
        raise SystemExit(91)
    return stub

pathlib.Path.mkdir = guarded_mkdir
subprocess.call = blocked('call')
subprocess.Popen = blocked('Popen')
subprocess.check_output = blocked('check_output')
subprocess.run = blocked('run')
if mode == 'host':
    def stub_check_output(argv, *args, **kwargs):
        note('check_output:' + ' '.join(map(str, argv)))
        REAL_PATH(argv[-1]).write_bytes(cfg['payload'].encode())
        return b''
    subprocess.check_output = stub_check_output
    subprocess.run = blocked('run')
if mode == 'source':
    subprocess.run = blocked('run')  # 适配器生成子进程已退休，调用即失败
    real_spec = importlib.util.spec_from_file_location
    def spec_from_file_location(name, path, *args, **kwargs):
        if str(path).endswith('/adapt_upstream_reference.py'):
            path = cfg['stub_adapter']
        return real_spec(name, path, *args, **kwargs)
    importlib.util.spec_from_file_location = spec_from_file_location
    payload = cfg['payload'].encode()
    subprocess.check_output = blocked('check_output')

def redirected(*args, **kwargs):
    resolved = REAL_PATH(*args, **kwargs)
    return REAL_PATH(cfg['tx_root']) if str(resolved) == cfg['tx_real'] else resolved

pathlib.Path = redirected
sys.argv = [script] + cfg['argv']
runpy.run_path(script, run_name='__main__')
'''

GATE = ('Explicit --host required when --source is not given: pass the Mac target the user '
        'designated for this run. No default host is built into this skill, and nothing was '
        'created or downloaded.')


class UpstreamPrepareHostGateTest(unittest.TestCase):

    UPDATE = ROOT / 'skills/luno-surge/scripts/update_upstream.py'

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='upstream-gate-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = self.tmp / 'calls.log'
        self.tx = self.tmp / 'tx'
        self.tx.mkdir()
        self.stub_adapter = self._stub_adapter()
        self.payload = '# synthetic official raw command reference\n'

    def _stub_adapter(self, reviewed=(), kind='raw'):
        stub = self.tmp / 'adapter_stub.py'
        stub.write_text('REVIEWED_SHA256 = set(%r)\n'
                        'ADAPTED_SHA256 = set()\n'
                        'def classify(digest):\n'
                        '    return %r if %r != "raw" or digest in REVIEWED_SHA256 else "unknown"\n'
                        % (tuple(reviewed), kind, kind), encoding='utf-8')
        return stub

    def _source_dir(self):
        src = self.tmp / 'official-snapshot'
        for rel in ('SKILL.md', 'references/command-reference.md',
                    'references/plugin-authoring.md', 'agents/openai.yaml',
                    'assets/logo.png'):
            target = src / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.payload.encode() if rel.endswith('.md') else b'x')
        return src

    def _run(self, mode, argv):
        cfg = {'log': str(self.log), 'argv': argv, 'payload': self.payload,
               'stub_adapter': str(self.stub_adapter), 'tx_root': str(self.tx),
               'tx_real': '/var/minis/shared/surge-updates'}
        return subprocess.run([sys.executable, '-B', '-c', DRIVER, str(self.UPDATE), mode,
                               json.dumps(cfg)], env=offline_env(),
                              capture_output=True, text=True, timeout=60)

    def _calls(self):
        return self.log.read_text(encoding='utf-8').splitlines() if self.log.exists() else []

    def test_missing_host_fails_before_any_side_effect(self):
        r = self._run('gate', ['prepare'])
        self.assertEqual(1, r.returncode, r.stderr)
        self.assertEqual('', r.stdout)
        self.assertEqual(GATE + '\n', r.stderr)
        self.assertEqual([], self._calls())

    def test_source_without_host_still_prepares(self):
        src = self._source_dir()
        digest = hashlib.sha256((src / 'references/command-reference.md').read_bytes()).hexdigest()
        self.stub_adapter = self._stub_adapter([digest])
        r = self._run('source', ['prepare', '--source', str(src), '--version', '0.0.0-test'])
        self.assertEqual(0, r.returncode, r.stderr)
        first = r.stdout.splitlines()[0]
        folder = first[len('Review directory: '):]
        self.assertTrue(folder.startswith(str(self.tx)), first)
        self.assertTrue((Path(folder) / 'transaction.json').is_file(), r.stdout)
        self.assertTrue((Path(folder) / 'review.diff').is_file(), r.stdout)
        calls = self._calls()
        self.assertEqual([], [c for c in calls if c.startswith('check_output')])
        self.assertEqual([], [c for c in calls if c.startswith(('run:scp', 'run:ssh'))])
        self.assertEqual([], [c for c in calls if c.startswith('mkdir:')
                              and not c[len('mkdir:'):].startswith(str(self.tx))])
        self.assertEqual([], [c for c in calls if c.startswith('run:')])
        folder = Path(folder)
        tx = json.loads((folder / 'transaction.json').read_text())
        self.assertEqual({'references/upstream-SKILL.md', 'references/plugin-authoring.md',
                          'references/upstream-command-reference.md', 'references/upstream-manifest.json'},
                         set(tx['files']))
        self.assertNotIn('references/command-reference.md', tx['files'])
        self.assertEqual((src / 'references/command-reference.md').read_bytes(),
                         (folder / 'raw/references/command-reference.md').read_bytes())
        self.assertEqual((src / 'references/command-reference.md').read_bytes(),
                         (folder / 'staged/references/upstream-command-reference.md').read_bytes())
        manifest = json.loads((folder / 'staged/references/upstream-manifest.json').read_text())
        expected = {str(p.relative_to(src)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in src.rglob('*') if p.is_file()}
        self.assertEqual(5, len(expected))
        self.assertEqual(expected, manifest['raw_sha256'])

    def test_explicit_host_uses_only_the_transport_stub(self):
        host = 'mac-target.invalid'
        r = self._run('host', ['prepare', '--host', host, '--version', '0.0.0-test'])
        calls = self._calls()
        scp = [c for c in calls if c.startswith('check_output:scp ')]
        self.assertEqual(5, len(scp), calls)
        self.assertEqual([], [c for c in calls if c.startswith('check_output:ssh ')])
        for call in scp:
            self.assertEqual(host, call.split()[4].split(':')[0], call)
        digest = hashlib.sha256(self.payload.encode()).hexdigest()
        self.assertEqual(1, r.returncode)
        self.assertEqual('Refusing transaction import: unreviewed command reference sha256='
                         + digest + '\n'
                         '(neither REVIEWED_SHA256 official raw text nor a known ADAPTED_SHA256 '
                         'product). Review the raw\ndiff, update the adapter baseline, then '
                         'prepare again. Nothing was staged.\n', r.stderr)


    @requires_official
    def test_source_gate_rejects_adapted_unknown_and_invalid(self):
        src = self._source_dir()
        path = src / 'references/command-reference.md'
        active = COMMAND_REFERENCE.read_bytes(), COMMAND_REFERENCE.stat().st_mode
        raw = UPSTREAM_COMMAND_REFERENCE.read_bytes()
        cases = [('adapted', b'historical fixture'), ('unknown', raw + b'!'),
                 ('reviewed', b'invalid classification fixture')]
        for kind, data in cases:
            with self.subTest(kind=kind):
                path.write_bytes(data)
                digest = hashlib.sha256(data).hexdigest()
                if kind == 'unknown':
                    self.stub_adapter = SCRIPTS / 'adapt_upstream_reference.py'
                    expected = ('Refusing transaction import: unreviewed command reference sha256=' + digest + '\n'
                                '(neither REVIEWED_SHA256 official raw text nor a known ADAPTED_SHA256 product). Review the raw\n'
                                'diff, update the adapter baseline, then prepare again. Nothing was staged.\n')
                elif kind == 'adapted':
                    self.stub_adapter = self._stub_adapter([], kind='adapted')
                    expected = ('Refusing transaction import: ' + str(path) + ' sha256=' + digest + ' is an already-adapted product\n'
                                '(listed in ADAPTED_SHA256), NOT official raw text. Do not feed an adapted command\n'
                                'reference (e.g. 5331f03b..., 334747c7..., 515303de..., d3163362...) to the transaction as\n'
                                '--source, do not\n'
                                'stage it as references/upstream-command-reference.md, and do not record it as raw_sha256 in\n'
                                'upstream-manifest.json. The adapter only classifies historical products; it never rewrites them.\n')
                else:
                    self.stub_adapter = self._stub_adapter([], kind='reviewed')
                    expected = ('Refusing transaction import: unreviewed command reference sha256=' + digest + '\n'
                                '(neither REVIEWED_SHA256 official raw text nor a known ADAPTED_SHA256 product). Review the raw\n'
                                'diff, update the adapter baseline, then prepare again. Nothing was staged.\n')
                r = self._run('source', ['prepare', '--source', str(src), '--version', '0.0.0-test'])
                self.assertEqual((1, '', expected), (r.returncode, r.stdout, r.stderr))
                self.assertEqual([], list(self.tx.iterdir()))
                self.assertEqual(active, (COMMAND_REFERENCE.read_bytes(), COMMAND_REFERENCE.stat().st_mode))

    @requires_official
    def test_changed_and_mixed_raw_rejected_before_staging(self):
        src = self._source_dir()
        path = src / 'references/command-reference.md'
        raw = UPSTREAM_COMMAND_REFERENCE.read_text(encoding='utf-8')
        nil = 'surge-cli set AutoPolicyGroupOverride.Streaming=<nil>'
        variants = []
        for old, new in ((nil, 'surge-cli set X=<nil>'),
                         ('also collect relevant context with', 'collect nothing with'),
                         ('### 1.2 Response envelope', '### 9.9 Nope')):
            self.assertIn(old, raw)
            variants.append(raw.replace(old, new))
        variants.extend((raw + '\n' + nil, raw + '\n' + COMMAND_REFERENCE.read_text(encoding='utf-8'),
                         raw + '\n' + RAW_FIXTURE_SENTENCE))
        self.stub_adapter = SCRIPTS / 'adapt_upstream_reference.py'
        active = COMMAND_REFERENCE.read_bytes(), COMMAND_REFERENCE.stat().st_mode
        for text in variants:
            path.write_text(text, encoding='utf-8')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertNotIn(digest, ADAPTER.REVIEWED_SHA256)
            r = self._run('source', ['prepare', '--source', str(src), '--version', '0.0.0-test'])
            expected = ('Refusing transaction import: unreviewed command reference sha256=' + digest + '\n'
                        '(neither REVIEWED_SHA256 official raw text nor a known ADAPTED_SHA256 product). Review the raw\n'
                        'diff, update the adapter baseline, then prepare again. Nothing was staged.\n')
            self.assertEqual((1, '', expected), (r.returncode, r.stdout, r.stderr))
            self.assertEqual([], list(self.tx.iterdir()))
            self.assertEqual(active, (COMMAND_REFERENCE.read_bytes(), COMMAND_REFERENCE.stat().st_mode))


class UpstreamApplyOverlayTest(unittest.TestCase):
    """真实 apply 入口仅操作隔离夹具，防覆盖、漂移与回滚。"""
    GUARD = ('Refusing apply: references/command-reference.md is a manually maintained overlay; '
             'prepare again. Nothing was written and no backup/ was created.')
    FILES = ('references/upstream-SKILL.md', 'references/plugin-authoring.md',
             'references/upstream-command-reference.md', 'references/upstream-manifest.json')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='surge-apply-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'skill'
        self.folder = Path(self.temp.name) / 'transaction'
        (self.root / 'scripts').mkdir(parents=True)
        self.folder.mkdir()
        for name in ('update_upstream.py', 'adapt_upstream_reference.py'):
            (self.root / 'scripts' / name).write_bytes((SCRIPTS / name).read_bytes())
        self.overlay = self.root / 'references/command-reference.md'
        self.overlay.parent.mkdir()
        self.overlay.write_bytes(COMMAND_REFERENCE.read_bytes())
        self.overlay.chmod(0o640)
        self._make_transaction()

    def _make_transaction(self, absent=None):
        files = {}
        for i, name in enumerate(self.FILES):
            active, staged = self.root / name, self.folder / 'staged' / name
            active.parent.mkdir(parents=True, exist_ok=True)
            staged.parent.mkdir(parents=True, exist_ok=True)
            if name != absent:
                active.write_bytes(('before-' + name).encode())
                active.chmod(0o600 if i % 2 else 0o640)
            staged.write_bytes(('after-' + name).encode())
            files[name] = {'before': self._digest(active) if active.exists() else None,
                           'after': self._digest(staged),
                           'mode': active.stat().st_mode & 0o777 if active.exists() else None}
        self.tx = {'files': files, 'adapter': self._digest(self.root / 'scripts/adapt_upstream_reference.py'), 'manual': ['agents/openai.yaml']}
        self._save()

    @staticmethod
    def _digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _save(self):
        (self.folder / 'transaction.json').write_text(json.dumps(self.tx), encoding='utf-8')

    def _snapshot(self):
        return {name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode & 0o777)
                if (self.root / name).exists() else None for name in self.FILES + ('references/command-reference.md',)}

    def _run(self, fail_at=None):
        script = self.root / 'scripts/update_upstream.py'
        if fail_at is None:
            argv = [sys.executable, '-B', str(script), 'apply', str(self.folder)]
        else:
            driver = '''import pathlib,runpy,sys
root, count, script, folder = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
old = pathlib.Path.replace
seen = 0
def fail_once(self, target):
 global seen
 if str(target).startswith(root + "/references/"):
  seen += 1
  if seen == count: raise OSError("controlled failure")
 return old(self, target)
pathlib.Path.replace = fail_once
sys.argv = [script, "apply", folder]
runpy.run_path(script, run_name="__main__")
'''
            argv = [sys.executable, '-B', '-c', driver, str(self.root), str(fail_at), str(script), str(self.folder)]
        return subprocess.run(argv, env=offline_env(), capture_output=True, text=True, timeout=60)

    def test_apply_refuses_manual_overlay_before_backup(self):
        before = self._snapshot()
        self.tx['files']['references/command-reference.md'] = {'before': None, 'after': None, 'mode': None}
        self._save()
        tx_before = (self.folder / 'transaction.json').read_bytes()
        r = self._run()
        self.assertEqual((1, '', self.GUARD + '\n'), (r.returncode, r.stdout, r.stderr))
        self.assertFalse((self.folder / 'backup').exists())
        self.assertEqual(tx_before, (self.folder / 'transaction.json').read_bytes())
        self.assertEqual(before, self._snapshot())

    def test_old_transaction_cannot_overwrite_overlay(self):
        before = self._snapshot()
        self.tx['files']['references/command-reference.md'] = {'before': 'old', 'after': 'old'}
        self.tx['adapter'] = 'old-adapter-hash'
        self._save()
        tx_before = (self.folder / 'transaction.json').read_bytes()
        r = self._run()
        self.assertEqual((1, '', self.GUARD + '\n'), (r.returncode, r.stdout, r.stderr))
        self.assertEqual(tx_before, (self.folder / 'transaction.json').read_bytes())
        self.assertFalse((self.folder / 'backup').exists())
        self.assertEqual(before, self._snapshot())

    def test_raw_import_preserves_overlay_and_snapshot_bytes(self):
        before = self._snapshot()
        r = self._run()
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(before['references/command-reference.md'], self._snapshot()['references/command-reference.md'])
        for name in self.FILES:
            self.assertEqual((self.folder / 'staged' / name).read_bytes(), (self.root / name).read_bytes())
            self.assertEqual(before[name][1], (self.root / name).stat().st_mode & 0o777)
            self.assertEqual(before[name][0], (self.folder / 'backup' / name).read_bytes())
            self.assertEqual(before[name][1], (self.folder / 'backup' / name).stat().st_mode & 0o777)
        self.assertEqual('applied', (self.folder / 'state').read_text())

    def test_drift_and_invalid_list_fail_before_backup(self):
        for kind in ('active', 'staged', 'mode', 'adapter', 'list'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix='surge-drift-') as unused:
                name = self.FILES[0]
                if kind == 'active': (self.root / name).write_bytes(b'changed')
                if kind == 'staged': (self.folder / 'staged' / name).write_bytes(b'changed')
                if kind == 'mode': (self.root / name).chmod(0o777)
                if kind == 'adapter': self.tx['adapter'] = 'different'
                if kind == 'list': self.tx['files']['other'] = {}
                self._save()
                before = self._snapshot()
                r = self._run()
                if kind in ('active', 'staged'): expected = 'Changed since prepare: ' + name
                elif kind == 'adapter': expected = 'Adapter changed; prepare again'
                elif kind == 'list': expected = 'Invalid transaction file list'
                else: expected = ('Mode changed since prepare: ' + name + ' (recorded 0o640, now 0o777). '
                                  'Re-run prepare before applying:\nnothing was written, the active tree is unchanged and no backup/ was created.')
                self.assertEqual((1, '', expected + '\n'), (r.returncode, r.stdout, r.stderr))
                self.assertFalse((self.folder / 'backup').exists())
                self.assertEqual(before, self._snapshot())
                self.tearDown()
                self.temp.cleanup()
                self.setUp()

    def test_controlled_failures_restore_all_touched_modes_and_absent(self):
        for at in range(1, len(self.FILES) + 1):
            with self.subTest(at=at):
                absent = self.FILES[0]
                (self.root / absent).unlink()
                self._make_transaction(absent=absent)
                before = self._snapshot()
                r = self._run(at)
                self.assertEqual(1, r.returncode)
                self.assertIn('OSError: controlled failure', r.stderr)
                self.assertEqual('rolled-back', (self.folder / 'state').read_text())
                self.assertEqual(before, self._snapshot())
                self.temp.cleanup()
                self.setUp()


class SurgeReleaseSnapshotTest(unittest.TestCase):
    """公开发布快照的**两态**判据：公开态（三份官方原件全不在）与取件态（三件都在且哈希合规）。

    `package_release.py` 的 `collect()` 只按目录名／后缀／名单排除（`__pycache__`、`.pem`、
    `secrets.env` 等），**没有**把 `references/upstream-*`／`references/plugin-authoring.md`
    列入排除表，故取件后三份原件会随技能目录整份进包；公开态它们不存在，包里自然也没有。
    因此本用例按实际行为分态断言，不为迎合某一态改脚本。

    「部分在位」或「在位但哈希不符」不属任何一种合法态（未按 manifest 取件／夹具损坏），
    一律显式失败并报出具体文件与类别，不用 `skipTest` 静默跳过。
    """

    # 仓库内落点 → `references/upstream-manifest.json` 的 `raw_sha256` 键（官方取件时的原路径）。
    ORIGINALS = {
        'references/upstream-SKILL.md': 'SKILL.md',
        'references/upstream-command-reference.md': 'references/command-reference.md',
        'references/plugin-authoring.md': 'references/plugin-authoring.md',
    }

    def test_release_zip_snapshot_in_both_states(self):
        import zipfile
        skill = ROOT / 'skills/luno-surge'
        # 两态共有：覆盖层、manifest 与自有的 agents/openai.yaml（本地有意改写，从 df54a93
        # 按原字节恢复）都必须逐字节进包。
        names = ('references/command-reference.md', 'references/upstream-manifest.json',
                 'agents/openai.yaml')
        manifest = json.loads((skill / 'references/upstream-manifest.json').read_text())
        self.assertEqual(5, len(manifest['raw_sha256']))
        missing = sorted(rel for rel in self.ORIGINALS if not (skill / rel).exists())
        fetched = not missing
        if missing and len(missing) != len(self.ORIGINALS):
            self.fail('官方原件部分在位：缺少 ' + ', '.join(missing) +
                      '（公开态要求三件全不在，取件态要求三件全在且哈希合规）')
        if fetched:
            for rel, key in sorted(self.ORIGINALS.items()):
                actual = hashlib.sha256((skill / rel).read_bytes()).hexdigest()
                self.assertEqual(manifest['raw_sha256'][key], actual,
                                 f'{rel} 的 sha256 与 manifest raw_sha256[{key}] 不符')
        with tempfile.TemporaryDirectory(prefix='surge-zip-') as tmp:
            out = Path(tmp) / 'release.zip'
            r = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'package_release.py'), str(out)],
                               env=offline_env(), capture_output=True, text=True, timeout=60)
            self.assertEqual(0, r.returncode, r.stderr)
            with zipfile.ZipFile(out) as archive:
                for name in names:
                    self.assertEqual((skill / name).read_bytes(), archive.read(name))
                for rel in sorted(self.ORIGINALS):
                    if fetched:
                        # 取件态：见类注释——排除表不含这三条路径，故它们进包且字节等于盘上字节。
                        self.assertEqual((skill / rel).read_bytes(), archive.read(rel))
                    else:
                        # 公开态：原件不在技能目录，ZIP 里也不得出现这三条路径。
                        self.assertNotIn(rel, archive.namelist())
                self.assertFalse(any(name.endswith(('.pyc', '.log', '.pem')) for name in archive.namelist()))
            r = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'package_release.py'),
                                str(skill / 'not-allowed.zip')], env=offline_env(),
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(1, r.returncode)
            self.assertEqual('Output ZIP must be outside the Skill directory\n', r.stderr)
            self.assertFalse((skill / 'not-allowed.zip').exists())
            isolated = Path(tmp) / 'isolated'
            (isolated / 'scripts').mkdir(parents=True)
            script = isolated / 'scripts/package_release.py'
            script.write_bytes((SCRIPTS / 'package_release.py').read_bytes())
            (isolated / 'bad-link').symlink_to('scripts/package_release.py')
            rejected = Path(tmp) / 'symlink.zip'
            r = subprocess.run([sys.executable, '-B', str(script), str(rejected)],
                               env=offline_env(), capture_output=True, text=True, timeout=60)
            self.assertEqual((1, '', 'Symlinks are not allowed in release packages: bad-link\n'),
                             (r.returncode, r.stdout, r.stderr))
            self.assertFalse(rejected.exists())




class DedicatedPackerInterfaceTest(unittest.TestCase):
    """专用打包器的内存接口（`collect(root)`／`build(entries)`）：部署入口复用的就是这两个函数。

    判据：① 过滤名单与排序由 collect 持有、build 按同一布局归档，排除项（含 .pem／.log／
    `secrets.env`／`__pycache__`／`.ssh`）不进包；② **一次读取**——以可控钩子让指定文件第一次
    `read_bytes` 返回安全 bytes 后立刻改盘为合成敏感内容，断言该文件恰读一次且归档的是**第一次**
    已检 bytes；并用隔离副本内的确切变异（扫描用第一次、归档再读一次）证明该断言会变红；
    ③ 先拒符号链接、再拒非常规条目，遍历错误上抛（均抛 ReleaseError 家族，不产出包）；
    ④ CLI 输出三行与 ZIP 元数据（时间戳／属性）不变，产物 sha256 与内存构包一致；原子替换失败
    时原产物不变、临时文件清理。
    """

    def isolated(self, tmp):
        """把专用器复制进隔离技能目录：`SOURCE` 由脚本自身位置推导，故夹具自足。"""
        skill = Path(tmp) / 'skill'
        (skill / 'scripts').mkdir(parents=True)
        script = skill / 'scripts/package_release.py'
        script.write_bytes((SCRIPTS / 'package_release.py').read_bytes())
        (skill / 'SKILL.md').write_text('---\nname: surge\n---\n\n夹具正文\n')
        (skill / 'references').mkdir()
        (skill / 'references/one.md').write_text('one\n')
        (skill / 'references/two.md').write_text('two\n')
        return skill, script, load_module('surge_release_under_test', script)

    def read_once_hook(self, target, marker):
        """把 `Path.read_bytes` 换成可控钩子：指定文件**第一次**返回磁盘上的安全 bytes，
        并立即把该文件改写成合成敏感内容；之后照常读盘。返回 (调用计数, 还原函数)。"""
        real = Path.read_bytes
        state = {"n": 0}

        def hook(self, *args, **kwargs):
            if str(self) == str(target):
                state["n"] += 1
                if state["n"] == 1:
                    data = real(self)
                    Path(self).write_text(marker + "\n", encoding="utf-8")
                    return data
            return real(self)

        def restore():
            Path.read_bytes = real

        Path.read_bytes = hook
        return state, restore

    def test_build_archives_the_first_checked_bytes_and_reads_each_file_once(self):
        with tempfile.TemporaryDirectory(prefix='surge-readonce-') as tmp:
            skill, _script, module = self.isolated(tmp)
            entries = module.collect(skill)
            target = skill / 'references/two.md'
            safe = target.read_bytes()
            marker = 'ghp_' + 'C' * 24          # 合成形态，不是任何真实凭据
            state, restore = self.read_once_hook(target, marker)
            try:
                blob = module.build(entries)
            finally:
                restore()
            self.assertEqual(1, state['n'], '该文件在本次构包中**恰读一次**')
            import zipfile
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                self.assertEqual(safe, archive.read('references/two.md'),
                                 '归档的是第一次已检 bytes，不是改盘后的敏感内容')
                self.assertNotIn(marker.encode(),
                                 b''.join(archive.read(name) for name in archive.namelist()))

    def test_mutation_second_read_turns_the_new_assertion_red(self):
        """确切变异（只在隔离候选副本内）：把 build 的读取改成两次、用第二次读的结果归档。

        该变异让新增用例的两条断言（恰读一次／归档第一次 bytes）都不成立 ⇒ 用例必红；
        受管工作树内的实现不改动（副本单独复制到临时目录后替换源码文本）。
        """
        with tempfile.TemporaryDirectory(prefix='surge-mutant-') as tmp:
            skill, script, _module = self.isolated(tmp)
            original = script.read_text(encoding='utf-8')
            # 变异：扫描仍用第一次读取的 data，而**归档**再读一次盘 —— 即「检查与归档不同源」
            needle = "            archive.writestr(info,data)\n"
            self.assertEqual(1, original.count(needle), '变异点必须唯一可定位')
            mutant_src = original.replace(
                needle, "            archive.writestr(info,Path(path).read_bytes())\n")
            self.assertNotEqual(original, mutant_src)
            script.write_text(mutant_src, encoding='utf-8')
            mutant = load_module('surge_release_mutant', script)
            entries = mutant.collect(skill)
            target = skill / 'references/two.md'
            marker = 'ghp_' + 'C' * 24
            state, restore = self.read_once_hook(target, marker)
            try:
                blob = mutant.build(entries)
            finally:
                restore()
            self.assertEqual(2, state['n'], '变异后该文件被读两次 ⇒「恰读一次」断言必红')
            import zipfile
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                self.assertEqual((marker + "\n").encode(), archive.read('references/two.md'),
                                 '变异体归档未检的第二次 bytes ⇒「归档第一次 bytes」断言必红')

    def test_excluded_paths_are_filtered_from_archive(self):
        with tempfile.TemporaryDirectory(prefix='surge-filter-') as tmp:
            skill, _script, module = self.isolated(tmp)
            for rel in ('secrets.env', 'credentials', 'logs/run.log', 'certs/key.pem',
                        '__pycache__', 'notes.log', '.ssh/known_hosts'):
                path = skill / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('excluded\n', encoding='utf-8')
            entries = module.collect(skill)
            names = [rel for rel, _p in entries]
            self.assertIn('SKILL.md', names, '夹具非空转：保留项仍在')
            self.assertIn('references/one.md', names)
            for excluded in ('secrets.env', 'credentials', 'logs/run.log', 'certs/key.pem',
                             'notes.log', '.ssh/known_hosts'):
                self.assertNotIn(excluded, names, '排除名单必须命中：%s' % excluded)
            self.assertFalse(any(name.startswith('__pycache__') for name in names))

    CLI_SENTINEL = b'SENTINEL-OLD-ARTIFACT-BYTES\n'

    def run_cli_with_replace_fault(self, script, out, tmp):
        """仅在 `os.replace(tmp, out)` 这一处注入 PermissionError（sitecustomize 子进程级）。

        注入点用**绝对路径相等**定点命中，并写「已命中」标记，避免「注入没生效也算通过」。
        """
        hook = Path(tmp) / 'hook'
        hook.mkdir()
        fired = Path(os.path.abspath(str(Path(tmp) / 'replace-fired.marker')))
        (hook / 'sitecustomize.py').write_text(
            "import os\n"
            "real = os.replace\n"
            "def replace(src, dst, *a, **k):\n"
            "    if os.path.abspath(dst) == %r:\n" % str(out)
            + "        open(%r, 'w').write('x')\n" % str(fired)
            + "        raise PermissionError('synthetic-replace-denied')\n"
            "    return real(src, dst, *a, **k)\n"
            "os.replace = replace\n", encoding='utf-8')
        env = offline_env()
        env['PYTHONPATH'] = str(hook)
        return subprocess.run([sys.executable, '-B', str(script), str(out)],
                              env=env, capture_output=True, text=True, timeout=60), fired

    def test_cli_replace_failure_keeps_old_artifact_and_cleans_tmp(self):
        with tempfile.TemporaryDirectory(prefix='surge-atomic-') as tmp:
            _skill, script, _module = self.isolated(tmp)
            out = Path(os.path.abspath(str(Path(tmp) / 'release.zip')))
            out.write_bytes(self.CLI_SENTINEL)          # 正常旧产物（普通文件、非目录）
            r, fired = self.run_cli_with_replace_fault(script, out, tmp)
            self.assertTrue(fired.exists(), '故障注入必须确已命中毒化点（非空转）')
            self.assertNotEqual(0, r.returncode, '替换失败必须非零退出')
            self.assertIn('PermissionError', r.stderr, '错误类别沿用既有未捕获 OSError，未新增 catch')
            self.assertEqual(self.CLI_SENTINEL, out.read_bytes(), '原产物逐字节不变')
            self.assertFalse(out.with_suffix(out.suffix + '.tmp').exists(), '临时文件已清理')

    def test_cli_replace_success_overwrites_old_artifact(self):
        """同场景无故障正控：预置哨兵被真实替换、临时文件不残留 ⇒ 上面那条的覆盖非空转。"""
        with tempfile.TemporaryDirectory(prefix='surge-atomic-ok-') as tmp:
            _skill, script, _module = self.isolated(tmp)
            out = Path(os.path.abspath(str(Path(tmp) / 'release.zip')))
            out.write_bytes(self.CLI_SENTINEL)
            r = subprocess.run([sys.executable, '-B', str(script), str(out)],
                               env=offline_env(), capture_output=True, text=True, timeout=60)
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertNotEqual(self.CLI_SENTINEL, out.read_bytes(), '旧产物必须被替换')
            import zipfile
            with zipfile.ZipFile(out) as archive:
                self.assertIsNone(archive.testzip())
            self.assertFalse(out.with_suffix(out.suffix + '.tmp').exists())


    def test_symlink_nonregular_and_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='surge-guard-') as tmp:
            skill, _script, module = self.isolated(tmp)
            (skill / 'bad-link').symlink_to('references/one.md')
            with self.assertRaises(module.ReleaseError) as caught:
                module.collect(skill)
            self.assertEqual('Symlinks are not allowed in release packages: bad-link',
                             str(caught.exception))
            (skill / 'bad-link').unlink()
            os.mkfifo(str(skill / 'bad-fifo'))
            with self.assertRaises(module.ReleaseError) as caught:
                module.collect(skill)
            self.assertEqual('Non-regular entries are not allowed in release packages: bad-fifo',
                             str(caught.exception))
            (skill / 'bad-fifo').unlink()
            with self.assertRaises(module.ReleaseError) as caught:
                module.collect(Path(tmp) / 'missing')
            self.assertIn('Traversal error', str(caught.exception))


    def test_cli_output_and_zip_metadata_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='surge-cli-') as tmp:
            skill, script, _module = self.isolated(tmp)
            out = Path(tmp) / 'release.zip'
            r = subprocess.run([sys.executable, '-B', str(script), str(out)],
                               env=offline_env(), capture_output=True, text=True, timeout=60)
            self.assertEqual(0, r.returncode, r.stderr)
            lines = r.stdout.splitlines()
            self.assertEqual(3, len(lines), r.stdout)
            self.assertEqual(str(out), lines[0])
            self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(), lines[1])
            expected = sorted(str(path.relative_to(skill)) for path in skill.rglob('*')
                              if path.is_file())
            self.assertEqual('files=%d bytes=%d' % (len(expected), out.stat().st_size), lines[2])
            import zipfile
            with zipfile.ZipFile(out) as archive:
                self.assertEqual(expected, archive.namelist())
                for info in archive.infolist():
                    self.assertEqual((2026, 1, 1, 0, 0, 0), info.date_time)
                    self.assertIn(info.external_attr >> 16 & 0o7777, (0o644, 0o755))


class FailClosedRedactionTest(unittest.TestCase):
    """2026-10-12 FORGE 收紧批：九类**已知可复现漏面**逐类负控（fail-closed）。

    每类先以合成标记复现（改前基线保留标记，证据见当批条目），再由本类守住：标记不得出现在
    `redact_boundary()` 输出里。断言前先确认标记**确实在输入中**（夹具非空转）。用例只走模块
    公开边界入口，不联网、不读仓库外文件、不用真实凭据；每条断言都能在「撤掉对应规则」时变红
    （撤防变异见当批条目）。
    """

    def _erased(self, sample, markers, keep=()):
        for marker in markers:
            self.assertIn(marker, sample, '夹具非空转：标记须在输入里')
        out = PRIVACY.redact_boundary(sample)
        for marker in markers:
            self.assertNotIn(marker, out, out)
        for item in keep:
            self.assertIn(item, out, out)
        self.assertEqual(PRIVACY.redact_boundary(out), out, out)   # 幂等
        return out

    def test_keystore_section_values_are_hidden(self):
        """① Keystore 段 `base64=` 私钥：段内**值**整段隐藏（段头与键名保留），段外 `base64=` 同口径。"""
        self._erased('[Keystore]\nMyKey = base64=SYNTHFC-KS-1BLOB\n',
                     ('SYNTHFC-KS-1BLOB',), keep=('[Keystore]', 'MyKey'))
        self._erased('[Keystore]\nMY-KEY = SYNTHFC-KS-2BLOB\n',
                     ('SYNTHFC-KS-2BLOB',), keep=('MY-KEY',))
        self._erased('[Keystore]\nkey-material: base64:SYNTHFC-KS-3BLOB\n',
                     ('SYNTHFC-KS-3BLOB',), keep=('key-material',))

    def test_unlisted_protocol_positional_credentials_are_hidden(self):
        """② 未列协议（`anytls` 一类）的裸位置凭据：端口之后整段隐藏，协议名与 host/port 保留。"""
        for protocol in ('anytls', 'h2-connect', 'masque'):
            self._erased('P = %s, h.example, 443, u, SYNTHFC-AT-1\n' % protocol,
                         ('SYNTHFC-AT-1',), keep=('%s, h.example, 443' % protocol,))
        self._erased('+P = anytls, h.example, 443, SYNTHFC-AT-2\n',
                     ('SYNTHFC-AT-2',), keep=('h.example',))
        # 负控：端口位不是完整数字字段的行不触发形状兜底（策略组／多值行保持原样）
        for line in ('GroupA = select, A, B\n',
                     'dns-server = system, ns1.example, ns2.example\n'):
            self.assertEqual(line, PRIVACY.redact_boundary(line))

    def test_non_proxy_quoted_tail_is_hidden(self):
        """③ 非代理行的转义引号口令尾段：未闭合引号值／裸值后跟引号字段一律整段隐藏。"""
        for sample in ('password="SYNTHFC-QT-1A,SYNTHFC-QT-1B\n',
                       'password=SYNTHFC-QT-2A,"SYNTHFC-QT-2B,SYNTHFC-QT-2C"\n',
                       'note: a, password="SYNTHFC-QT-3A,SYNTHFC-QT-3B"\n'):
            self._erased(sample, ('SYNTHFC-QT-',), keep=('password',))
        # 正控：闭合引号值之后的同行参数不因尾段兜底被吃掉
        self._erased('password="SYNTHFC-QT-4A,SYNTHFC-QT-4B" other=1\n',
                     ('SYNTHFC-QT-4A',), keep=('other=1',))

    def test_whitespace_nested_containers_are_hidden(self):
        """④ 带空白的非 JSON 嵌套容器：嵌套／未闭合容器整段隐藏；单层容器仍按原形整值替换。"""
        for sample in ('token: [ [ "SYNTHFC-WS-1A" ] ]\n',
                       'password: ["SYNTHFC-WS-2A", ["SYNTHFC-WS-2B"]]\n',
                       'token = [[ "SYNTHFC-WS-3A" ]]\n',
                       'token: [[ SYNTHFC-WS-5A ]]\n'):
            self._erased(sample, ('SYNTHFC-WS-',))
        self.assertEqual(PRIVACY.redact_boundary('"tokens": ["SYNTHFC-WS-4A"]'),
                         '"tokens": ["<redacted>"]')

    def test_auth_value_literal_newline_boundary(self):
        """⑤ `auth` 值的字面 `\\n` 边界：转义记录边界之后的 auth 键同样抹除。

        代价（fail-closed）：`auth` 裸值规则**不**在字面 `\\n` 处截断，故该逻辑行后续内容一并隐藏
        ——不得据此把后续内容当已核实内容引用。
        """
        self._erased(r'[Tailscale t]\nauth=SYNTHFC-NL-1A\nhostname = h', ('SYNTHFC-NL-1A',))
        self._erased(r'[S]\nauth="SYNTHFC-NL-2A,SYNTHFC-NL-2B"\nhost = h', ('SYNTHFC-NL-2',))
        self._erased(r'[S]\nauth=Bearer SYNTHFC-NL-3A\nhost = h', ('SYNTHFC-NL-3A',))
        out = PRIVACY.redact_boundary('auth=SYNTHFC-NL-4A\n')
        self.assertNotIn('SYNTHFC-NL-4A', out, out)
        self.assertIn('auth=', out, out)

    def test_cookie_fields_are_hidden(self):
        """⑥ Cookie 字段（**非代理行**上下文）：`Cookie:`／`Set-Cookie:`／`cookie=` 值整段隐藏。"""
        for sample in ('Cookie: session=SYNTHFC-CK-1A\n',
                       'set-cookie: session=SYNTHFC-CK-2A; Path=/\n',
                       'headers = Cookie: a=SYNTHFC-CK-3A, b=SYNTHFC-CK-3B\n',
                       json.dumps({'note': 'Cookie: a=SYNTHFC-CK-4A'}),
                       json.dumps({'cookie': 'a=SYNTHFC-CK-5A'})):
            self._erased(sample, ('SYNTHFC-CK-',))
        self._erased('Cookie: a=SYNTHFC-CK-6A; Path=/\n', ('SYNTHFC-CK-6A',), keep=('Cookie',))

    def test_url_userinfo_is_hidden(self):
        """⑦ URL userinfo（`scheme://user:pass@host`）：整个 userinfo 隐藏，scheme 与 host 保留。"""
        for sample in ('url = https://synthuser:SYNTHFC-UI-1A@h.example/p\n',
                       json.dumps({'url': 'https://u:SYNTHFC-UI-2A@h.example'}),
                       'url = socks5://u:SYNTHFC-UI-3A@h.example:1080\n',
                       'url = https://SYNTHFC-UI-4A@h.example\n'):
            self._erased(sample, ('SYNTHFC-UI-',), keep=('h.example',))
        # 负控：无 userinfo 的普通 URL 与邮件形态不受影响（不得据此宣称任意 URL 均脱敏）
        for sample in ('url = https://h.example/sub?page=2\n', 'contact = ops@h.example\n'):
            self.assertEqual(sample, PRIVACY.redact_boundary(sample))

    def test_presigned_url_parameters_are_hidden(self):
        """⑧ 预签名 URL 参数（`X-Amz-Signature` 一类）与云 key id：值隐藏。"""
        for sample in ('url = https://b.example/o?X-Amz-Signature=SYNTHFC-SG-1A&X-Amz-Expires=300\n',
                       'https://b.example/o?X-Goog-Signature=SYNTHFC-SG-2A\n',
                       'https://b.example/o?signature=SYNTHFC-SG-3A&x=1\n',
                       'Signature=SYNTHFC-SG-4A\n',
                       'https://b.example/o?AWSAccessKeyId=SYNTHFC-SG-5A&Signature=SYNTHFC-SG-5B\n'):
            self._erased(sample, ('SYNTHFC-SG-',))

    def test_credential_shaped_values_under_unknown_keys_are_hidden(self):
        """⑨ 未知键下**形态明显为凭据**的值：JWT／PEM 块／长不透明串／厂商前缀，按形状抹除。"""
        for sample in ('opaque = eyJhbGciOiJIUzI1NiJ9.SYNTHFC-UN-1A.SYNTHFC-UN-1B\n',
                       'note = -----BEGIN PRIVATE KEY-----\nSYNTHFC-UN-2A\n-----END PRIVATE KEY-----\n',
                       'opaque = A1b2C3d4SYNTHFC-UN-3AE5f6G7h8I9j0K1l2M3n4O5p6\n',
                       'opaque = AIzaSYNTHFC-UN-4ASYMMETRICMARKER0123456\n'):
            self._erased(sample, ('SYNTHFC-UN-',))
        # 负控（正控面）：短普通值**不得**被形状规则误抹——本模块不是「未知键一律整段抹」
        for sample in ('opaque = SYNTHFC-UN-5A\n', 'note = ok\n', 'title = build 42\n'):
            self.assertEqual(sample, PRIVACY.redact_boundary(sample))

    def test_normal_diagnostics_stay_readable(self):
        """正控：普通诊断输出（正常 profile、摘要、diff 片段）不因本批规则改变。

        期望值＝**改前基线逐字节相同**（对照记录见当批条目）；此处按原样断言，不用「包含某子串」
        代替整体判据。
        """
        profile = ('[General]\nloglevel = notify\n'
                   '[Proxy]\n'
                   'PROXY-A = https, h.example, 443, user-a, SYNTHFC-PC-1\n'
                   'GroupA = select, A, B\nFINAL,DIRECT\n'
                   '[Rule]\nDOMAIN-SUFFIX,example.org,DIRECT\n')
        out = PRIVACY.redact_boundary(profile)
        self.assertIn('PROXY-A = https, h.example, 443', out, out)
        self.assertIn('GroupA = select, A, B', out, out)
        self.assertIn('DOMAIN-SUFFIX,example.org,DIRECT', out, out)
        self.assertIn('loglevel = notify', out, out)
        self.assertNotIn('SYNTHFC-PC-1', out, out)
        for sample in ('{"outbound": "proxy", "enabled": true}',
                       '{"user-agent": "Surge/5.0"}',
                       'basic configuration failed',
                       'local-port = 6171'):
            self.assertEqual(sample, PRIVACY.redact_boundary(sample))
        pretty = '{\n  "policy": "Proxy",\n  "outbound": "proxy"\n}'
        self.assertEqual(pretty, PRIVACY.redact_boundary(pretty))

    # ===== 2026-10-12 R1 批：五类**变体**漏面（独立复审判未闭合；上一轮报「已闭合」不成立）=====
    # 复现口径：复审对象 b376ff2，发布方独立复现——基线与候选都残留标记。每类先断言标记**确在
    # 输入中**（`_erased()` 的首个 `assertIn`），再断言不在输出中；每条都能在撤掉对应保护时变红。

    def test_r1_unlisted_compound_protocol_names_are_hidden(self):
        """① 未列协议的**复合名**（`tuic-v5`／`socks5-udp`）：排除判据只认「完整已列协议字段」。

        复现（改前）：`T1 = tuic-v5, h.example, 443, u, <标记>` 原样输出标记——负向断言按
        `\\b` 排除了已列协议**前缀**，`tuic-v5`／`socks5-udp` 连前缀一起被排除、整行落空。
        撤防变异：`_UNLISTED_TYPE` 改回 `…)\\b)` ⇒ 本用例红。
        """
        for protocol in ('tuic-v5', 'socks5-udp'):
            self._erased('T1 = %s, h.example, 443, u, SYNTHFC-R1-UP-1\n' % protocol,
                         ('SYNTHFC-R1-UP-1',), keep=('%s, h.example, 443' % protocol,))
        self.assertEqual('T2 = https-tls, h.example, 443, <redacted>\n',
                         PRIVACY.redact_boundary('T2 = https-tls, h.example, 443, u, SYNTHFC-R1-UP-2\n'))

    def test_r1_listed_protocol_slots_and_policy_lines_are_unaffected(self):
        """①的正控：已列表协议（含复合名 `socks5-tls`）仍走位置表；策略组／多值行不触发形状兜底。"""
        self.assertEqual('T3 = socks5-tls, h.example, 1080, <redacted>, <redacted>\n',
                         PRIVACY.redact_boundary('T3 = socks5-tls, h.example, 1080, u, SYNTHFC-R1-UP-3\n'))
        for line in ('GroupA = select, A, B\n', 'FINAL,DIRECT\n',
                     'dns-server = system, ns1.example, ns2.example\n'):
            self.assertEqual(line, PRIVACY.redact_boundary(line))

    def test_r1_input_supplied_marker_does_not_short_circuit(self):
        """② 输入自携 `<redacted>`：只有「整段即规范标记容器」才豁免尾段兜底。

        复现（改前）：`password="<redacted>,<标记>` 的首段正是 `<redacted>`，短路令整段原样输出。
        撤防变异：恢复「首段含标记即返回原文」的短路 ⇒ 本用例红。
        """
        for sample in ('password="<redacted>,SYNTHFC-R1-RM-1A\n',
                       "password='<redacted>,SYNTHFC-R1-RM-2A\n"):
            self._erased(sample, ('SYNTHFC-R1-RM-',), keep=('password',))
            self.assertEqual('password=<redacted>\n', PRIVACY.redact_boundary(sample))
        # 正控：规范形（含容器形态）仍幂等，不被尾段兜底二次改写
        for canonical in ('password=<redacted>\n', 'token=<redacted>\n',
                          '"tokens": ["<redacted>"]'):
            self.assertEqual(canonical, PRIVACY.redact_boundary(canonical), canonical)

    def test_r1_two_sensitive_keys_on_one_line_are_hidden(self):
        """③ 同一行两个敏感键：容器尾段规则不得吃掉前置值、妨碍扫描同行后续键。

        复现（改前）：`token1 = { <标记A> }, token2: [[ <标记B> ]]` 两个标记都原样输出——尾段
        规则把整行吃进匹配并原样返回，`re.sub` 扫描位置随即跳过同行后续敏感键。
        撤防变异：`_KEY_CONTAINER_TAIL` 的 `rest` 改回 `(?:(?!\\\\n)[^\\n])*` ⇒ 红；`_KEY` 去掉
        `[0-9]{0,3}` 后缀也红（夹具键名带序号后缀，两处保护缺一即漏）。
        """
        self._erased('token1 = { SYNTHFC-R1-TK-1A }, token2: [[ SYNTHFC-R1-TK-1B ]]\n',
                     ('SYNTHFC-R1-TK-1A', 'SYNTHFC-R1-TK-1B'))
        self.assertEqual('token1=<redacted>\n',
                         PRIVACY.redact_boundary(
                             'token1 = { SYNTHFC-R1-TK-1A }, token2: [[ SYNTHFC-R1-TK-1B ]]\n'))
        self.assertEqual('psk2=<redacted>\n',
                         PRIVACY.redact_boundary(
                             'psk2 = SYNTHFC-R1-TK-2A, token2: [[ SYNTHFC-R1-TK-2B ]]\n'))
        self._erased('token1 = { SYNTHFC-R1-TK-3A }, psk2 = { SYNTHFC-R1-TK-3B }\n',
                     ('SYNTHFC-R1-TK-3A', 'SYNTHFC-R1-TK-3B'))
        # 正控：同一行的**普通**键不被连坐
        self.assertEqual('a = 1, b = 2\n', PRIVACY.redact_boundary('a = 1, b = 2\n'))

    def test_r1_cross_physical_line_container_is_fail_closed(self):
        """④ 跨物理行的非 JSON 嵌套容器：整份 fail-closed（代价登记：普通字段一并变单一标记）。

        复现（改前）：`token = [ [\\n<标记>\\n] ]` 只隐藏首行，续行原样输出。
        撤防变异：去掉 `redact_text()` 前置的 `_has_unclosed_container()` 判据 ⇒ 红。
        """
        sample = 'a = 1\ntoken = [ [\nSYNTHFC-R1-XL-1A\n] ]\nb = 2\n'
        out = self._erased(sample, ('SYNTHFC-R1-XL-1A',))
        self.assertEqual(PRIVACY.REDACTED, out)      # 代价：整份不再可读（含 a/b 两个普通字段）
        # 负控：**同行闭合**的嵌套容器不进整份 fail-closed（结构保留，标记仍被抹）
        closed = PRIVACY.redact_boundary('token = [ [ "SYNTHFC-R1-XL-2A" ] ]\n')
        self.assertNotIn('SYNTHFC-R1-XL-2A', closed, closed)
        self.assertNotEqual(PRIVACY.REDACTED, closed, closed)

    def test_r1_quoted_variants_of_the_unclosed_faces(self):
        """⑤ ③④ 的引号变体：同行双键带引号值、跨行带引号／未闭合引号的嵌套容器。

        复现（改前）：`token1 = { "<标记A>" }, token2: [[ "<标记B>" ]]`、`token = [ [\\n"<标记>"\\n] ]`
        均残留标记。撤防变异：同 ③／④ 两处（引号形态不另走保护）。
        """
        self._erased('token1 = { "SYNTHFC-R1-QV-1A" }, token2: [[ "SYNTHFC-R1-QV-1B" ]]\n',
                     ('SYNTHFC-R1-QV-1A', 'SYNTHFC-R1-QV-1B'))
        self._erased("token1 = { 'SYNTHFC-R1-QV-2A' }, psk2 = [ 'SYNTHFC-R1-QV-2B' ]\n",
                     ('SYNTHFC-R1-QV-2A', 'SYNTHFC-R1-QV-2B'))
        for sample in ('token = [ [\n"SYNTHFC-R1-QV-3A"\n] ]\n',
                       'token = "[ [\nSYNTHFC-R1-QV-4A\n] ]\n'):
            self.assertEqual(PRIVACY.REDACTED, self._erased(sample, ('SYNTHFC-R1-QV-',)))
        # 正控：闭合引号值仍按引号形态替换，不被引号变体判据连坐
        self.assertEqual('password=<redacted>\n',
                         PRIVACY.redact_boundary('password = "SYNTHFC-R1-QV-5A"\n'))

    def test_r1_positive_controls_normal_output_is_unchanged(self):
        """正控：单行普通容器／合法 JSON／已列协议行／同行多键／幂等——本轮不得改变其输出。

        期望值＝**本轮改前基线逐字节相同**（31 条正常语料对照 0 差异，见当批条目）；此处按原样
        断言，不用「包含某子串」代替整体判据。
        """
        self.assertEqual('token=<redacted>\n',
                         PRIVACY.redact_boundary(
                             'token = [SYNTHFC-R1-PC-2A, SYNTHFC-R1-PC-2B]\n'))
        self.assertEqual('tokens=<redacted>\n',
                         PRIVACY.redact_boundary(
                             'tokens = ["SYNTHFC-R1-PC-3A", "SYNTHFC-R1-PC-3B"]\n'))
        self.assertEqual('{"token": "<redacted>", "note": "keep"}',
                         PRIVACY.redact_boundary('{"token": "SYNTHFC-R1-PC-4A", "note": "keep"}'))
        self.assertEqual('{\n  "token": "<redacted>",\n  "n": 1\n}',
                         PRIVACY.redact_boundary('{\n  "token": "SYNTHFC-R1-PC-5A",\n  "n": 1\n}'))
        self.assertEqual('PROXY-A = https, h.example, 443, <redacted>, <redacted>\n',
                         PRIVACY.redact_boundary(
                             'PROXY-A = https, h.example, 443, user-a, SYNTHFC-R1-PC-6A\n'))
        self.assertEqual('token=<redacted>, user=<redacted>\n',
                         PRIVACY.redact_boundary(
                             'token = SYNTHFC-R1-PC-7A, user = SYNTHFC-R1-PC-7B\n'))
        self.assertEqual('GroupA = select, A, B\nFINAL,DIRECT\n',
                         PRIVACY.redact_boundary('GroupA = select, A, B\nFINAL,DIRECT\n'))
        self.assertEqual('a = 1, b = 2\n', PRIVACY.redact_boundary('a = 1, b = 2\n'))
        for sample in ('token = [SYNTHFC-R1-PC-8A, SYNTHFC-R1-PC-8B]\n',
                       'a = 1\ntoken = SYNTHFC-R1-PC-9A\nb = 2\n',
                       '{"token": "SYNTHFC-R1-PC-10A", "n": [1, 2]}',
                       '"tokens": ["SYNTHFC-R1-PC-11A"]'):
            out = PRIVACY.redact_boundary(sample)
            self.assertNotIn('SYNTHFC-R1-PC-', out, out)
            self.assertEqual(out, PRIVACY.redact_boundary(out), out)     # 幂等


class R2JsonContractAndSegmentKeyTest(unittest.TestCase):
    """2026-10-12 R2 FORGE 修复批：合法 JSON 契约回归（上一轮 R1 引入）＋分隔段键名缺口。

    两组判据，都在 `_privacy.py` 内闭合（每条都能在撤掉对应改动时变红，见各条 docstring）：
      Fix A：合法 JSON（数组／嵌套／多键／紧凑＋缩进）经**文本路径**后仍可 `json.loads`，且容器
        形态保持（2) 规则的规范形 `["<redacted>"]` 不得被 3b 尾段兜底吃掉）；
      Fix B：`_`／`-` 分隔的敏感词段键名（真实事故形态 `POSTGRES_PASSWORD`）与值一并抹除，
        非敏感键名不连坐。

    判别力说明（重要）：`redact_text()` 的**合法 JSON 契约兜底**会在流水线产出非法 JSON 时改走
    结构化路由（形状变为整值字符串）。故 Fix A 的形状判据必须用**逐字节期望值**——只断言「可
    解析」会失去判别力（兜底会把流水线缺陷修好）；兜底自身另有一例（跨行展开／嵌套容器值）。
    """

    MARK = 'SYNTH-R2-'

    def _parse(self, out):
        """按 JSON 解析输出；失败即断言失败（不回显待判文本，避免把待判内容带进失败消息）。"""
        try:
            return json.loads(out)
        except ValueError as exc:
            self.fail('合法 JSON 契约被破坏：%s' % type(exc).__name__)

    def test_legal_json_survives_text_path(self):
        """Fix A：文本路径不得破坏合法 JSON（逐字节期望值 ＋ `json.loads` 双判据）。

        复现（改前，发布方实测）：`redact_text('{"tokens": ["A", "B"]}')` →
        `{"tokens": <redacted>`（丢闭合符、占位符未加引号，不可解析）——3b 的尾段兜底把 2)
        刚产出的规范形连同同行后续的 JSON 结构一起吃掉。
        撤防变异：`_key_quote_tail()` 去掉 `_CONTAINER_LEAD` 豁免 ⇒ 本用例红（形状转成兜底的
        整值字符串，`assertEqual` 与 `assertNotIn` 均失败）。
        """
        cases = (
            ('数组容器·紧凑', '{"tokens": ["SYNTH-R2-JS-1A", "SYNTH-R2-JS-1B"]}',
             '{"tokens": ["<redacted>"]}'),
            ('容器值·对象', '{"tokens": {"a": "SYNTH-R2-JS-2A"}}',
             '{"tokens": ["<redacted>"]}'),
            ('嵌套对象', '{"a": {"tokens": ["SYNTH-R2-JS-3A"]}}',
             '{"a": {"tokens": ["<redacted>"]}}'),
            ('多键·同行', '{"tokens": ["SYNTH-R2-JS-4A"], "x": "keep"}',
             '{"tokens": ["<redacted>"], "x": "keep"}'),
            ('多键·两个敏感键', '{"tokens": ["SYNTH-R2-JS-5A"], "password": "SYNTH-R2-JS-5B"}',
             '{"tokens": ["<redacted>"], "password": "<redacted>"}'),
            ('缩进布局·同行闭合', '{\n  "tokens": ["SYNTH-R2-JS-6A"],\n  "policy": "Proxy"\n}',
             '{\n  "tokens": ["<redacted>"],\n  "policy": "Proxy"\n}'),
            ('顶层数组', '[{"token": "SYNTH-R2-JS-7A"}, {"password": "SYNTH-R2-JS-7B"}]',
             '[{"token": "<redacted>"}, {"password": "<redacted>"}]'),
        )
        for label, fixture, expected in cases:
            with self.subTest(label=label):
                self.assertIn(self.MARK, fixture, '夹具非空转：标记须在输入里')
                out = PRIVACY.redact_text(fixture)
                self.assertNotIn(self.MARK, out, out)
                self.assertEqual(expected, out, out)              # 形状＝本模块既有契约
                self.assertEqual(json.loads(expected), self._parse(out))
                self.assertEqual(out, PRIVACY.redact_text(out), out)          # 同入口幂等
                # 注：不在此断言 `redact_boundary(out)`——整段合法 JSON 走**结构化**分支，命中键
                # 的值按结构整值替换为字符串（`"<redacted>"`），与本路径的容器规范形
                # `["<redacted>"]` 形状不同；两者都不残留标记且都可解析，形状差异是既有契约。

    def test_legal_json_document_stays_parseable_through_text_path(self):
        """Fix A：**可解析的 JSON 文档**经文本路径一律保持可解析（跨行展开／嵌套容器值）。

        这两类形状由流水线的「合法 JSON 契约兜底」改走结构化路由产出（命中键整值替换为字符串），
        故此处只断言「可解析 ＋ 标记不残留 ＋ 幂等」；形状判据在上一条。
        撤防变异：去掉 `redact_text()` 里的 `_json_document()` 兜底分支 ⇒ 本用例红
        （输出分别为 `<redacted>` 与 `{"token": ["<redacted>"]`，均不可解析）。
        """
        for fixture in ('{\n  "tokens": [\n    "SYNTH-R2-JD-1A"\n  ]\n}',
                        '{"token": [["SYNTH-R2-JD-2A"]]}',
                        '{"tokens": [["SYNTH-R2-JD-3A"]], "n": 1}'):
            with self.subTest(fixture=fixture.replace('\n', '\\n')):
                self.assertIn(self.MARK, fixture, '夹具非空转：标记须在输入里')
                out = PRIVACY.redact_text(fixture)
                self.assertNotIn(self.MARK, out, out)
                self.assertIsInstance(self._parse(out), (dict, list))
                self.assertEqual(out, PRIVACY.redact_text(out), out)

    def test_segment_separated_sensitive_key_names_are_redacted(self):
        """Fix B：`_`／`-` 分隔的敏感词段键名与值**一并**抹除（真实事故形态）。

        复现（改前，发布方实测）：`POSTGRES_PASSWORD`／`DB_PASSWORD`／`MY_TOKEN`／`SECRET_KEY`／
        `ADMIN_TOKEN`／`AWS_SECRET_ACCESS_KEY`／`REDIS_PASSWORD` 后的值原样残留，而裸
        `PASSWORD`／`API_KEY` 会被抹——2026-10-11 事故正是 `env | grep -i postgres` 把
        `POSTGRES_PASSWORD` 带进会话，共用入口的主要用途就是 env／配置输出。
        撤防变异：`_KEY` 改回「不含 `_SEG_PRE`／`_SEG_POST` 的旧词集」形态 ⇒ 红（三条形状全漏）。
        """
        for key in ('POSTGRES_PASSWORD', 'DB_PASSWORD', 'MY_TOKEN', 'SECRET_KEY', 'ADMIN_TOKEN',
                    'AWS_SECRET_ACCESS_KEY', 'REDIS_PASSWORD', 'github_token',
                    'MYSQL_ROOT_PASSWORD', 'aws_secret_access_key'):
            with self.subTest(key=key):
                for shape, transform in ((key + '=SYNTH-R2-SK-1A\n', PRIVACY.redact_boundary),
                                         ('{"%s": "SYNTH-R2-SK-1B"}' % key, PRIVACY.redact_boundary),
                                         (key + ': SYNTH-R2-SK-1C\n', PRIVACY.redact_text)):
                    self.assertIn(self.MARK, shape, '夹具非空转：标记须在输入里')
                    self.assertNotIn(self.MARK, transform(shape), shape)
                self.assertEqual(PRIVACY.redact_obj({key: 'SYNTH-R2-SK-1D'})[key], '<redacted>')
                self.assertNotIn(self.MARK, PRIVACY.dumps_redacted({key: 'SYNTH-R2-SK-1E'}))

    def test_non_sensitive_key_names_are_untouched(self):
        """Fix B 正控：非敏感键名不得连坐（`key` 不作裸子串命中；身份词不参与分隔段）。

        `USER_AGENT`／`user-agent` 归此列：`user`／`username` 属**身份**而非凭据，既有正控
        （`{"user-agent": "Surge/5.0"}`）要求其输出不变，故身份词只按**整键**命中（代价登记：
        `DB_USER`／`USER_NAME` 一类不抹）。`PUBLIC_KEY` 归此列：公钥按定义可公开（`.pub`、
        证书、上传到平台的公钥都不是秘密），模块另有 `_PEM_BLOCK` 会抹 **PUBLIC KEY 块**（另一
        件事，已登记）；单行 `PUBLIC_KEY=<40+ 串>` 属「长不透明串前视排除 `=`」的已知残余，
        不在本批。
        """
        for key in ('PATH', 'HOSTNAME', 'PORT', 'A_B_C', 'MONKEY', 'PUBLIC_KEY', 'USER_AGENT',
                    'NODE_ENV', 'LOG_LEVEL', 'HOST', 'POLICY'):
            for shape, transform in ((key + '=SYNTH-R2-NK-1A\n', PRIVACY.redact_boundary),
                                     ('{"%s": "SYNTH-R2-NK-1A"}' % key, PRIVACY.redact_boundary),
                                     (key + ': SYNTH-R2-NK-1A\n', PRIVACY.redact_text)):
                with self.subTest(key=key, shape=shape):
                    self.assertEqual(shape, transform(shape), shape)


class R3ContainerExemptionAndScanPositionTest(unittest.TestCase):
    """2026-10-12 R3 FORGE 修复批：两处确定性缺陷（独立复审判 N1／N2，发布方实测复现）。

    N1（严重）：3b 尾段兜底的**容器豁免**在 R2 变成无条件成立，于是「容器开头」本身被当成
      「尾段无秘密」的充分条件。非 JSON 文本里 2)／2b) 的括号计数会被引号内字符骗过
      （`token=["x]", <标记>` 的 `]`、`token={"x": "}", <标记>` 的 `}` 都落在引号里），或用
      `_KEY_BARE` 剪掉已闭合容器后只剩携密引号尾段（`token=[ "a" ], <标记>`）⇒ 尾段原样输出
      且 `f(f(x)) != f(x)`。修法：豁免只在**整份输入已确认为合法 JSON 文档**
      （`_json_document(source) is not None`）时开启，其余输入落回 fail-closed。
    N2（严重）：`_CONTAINER_OPEN` 的 `rest` 接受任意裸值，物理行里「前置键 ＋ 同行后续敏感容器
      键」的形态被**前置键**的匹配整行吃进（非重叠扫描随之前移），`token` 键不再单独成匹配
      ⇒ 跨物理行容器的整份 fail-closed 不触发、续行原样输出。修法：`rest` 只从容器开头起匹配。

    每条断言三件事：标记**确在输入里**（夹具非空转）、首遍输出不含标记、同入口幂等
    （`f(f(x)) == f(x)`）。形状类判据用**逐字节期望值**——只断言「可解析」会失去判别力（合法
    JSON 契约兜底会替流水线把形状修好）。撤防变异见各条 docstring。
    """

    MARK = 'SYNTH-R3-'

    def _clean(self, sample, markers):
        """公开入口 `redact_boundary()` 上：标记在输入里、不在输出里、同入口幂等。"""
        for marker in markers:
            self.assertIn(marker, sample, '夹具非空转：标记须在输入里')
        out = PRIVACY.redact_boundary(sample)
        for marker in markers:
            self.assertNotIn(marker, out, out)
        self.assertEqual(out, PRIVACY.redact_boundary(out), out)      # 同入口幂等
        return out

    def _parse(self, out):
        """按 JSON 解析输出；失败即断言失败（不回显待判文本）。"""
        try:
            return json.loads(out)
        except ValueError as exc:
            self.fail('合法 JSON 契约被破坏：%s' % type(exc).__name__)

    def test_n1_container_exemption_is_gated_to_json_documents(self):
        """N1 复现：容器豁免无条件时三条形态都残留尾段且不幂等；改后一律 fail-closed。

        复现（改前基线，`redact_boundary()` 实测）：`token=["x]", "<标记>"` →
        `token=<redacted>, "<标记>"` 且 `f(f(x)) != f(x)`；`token={"x": "}", "<标记>"`、
        `token=[ "a" ], "<标记>"` 同形（前两条是括号计数被引号内字符骗过，第三条是已闭合容器
        ＋携密引号尾段）。判据＝三条都落回逐字节的 `token=<redacted>`（同族形态另附三格）。
        撤防变异：`_key_quote_tail()` 的 `if allow_container and _CONTAINER_LEAD…` 改回
        `if _CONTAINER_LEAD…`（＝R2 的无条件豁免）⇒ 本用例六格全红。
        """
        tail = PRIVACY.REDACTED
        cases = (
            ('括号计数被引号内 `]` 骗过', 'token=["x]", "%sN1-1A"' % self.MARK, 'token=' + tail),
            ('括号计数被引号内 `}` 骗过', 'token={"x": "}", "%sN1-2A"' % self.MARK, 'token=' + tail),
            ('已闭合容器＋携密引号尾段', 'token=[ "a" ], "%sN1-3A"' % self.MARK, 'token=' + tail),
            ('键带引号（内层／顶层串形态）', '"token":["x"], "%sN1-4A"' % self.MARK,
             '"token":' + tail),
            ('尾段是另一敏感键的引号值', 'token=["x"], psk="%sN1-5A"' % self.MARK, 'token=' + tail),
            ('尾段是同行诊断字段', 'a = 1\ntoken=["x"] = "%sN1-6A"' % self.MARK,
             'a = 1\ntoken=' + tail),
        )
        for label, sample, expected in cases:
            with self.subTest(label=label):
                out = self._clean(sample, (self.MARK,))
                self.assertEqual(expected, out, out)

    def test_n2_same_line_key_does_not_swallow_cross_line_scan(self):
        """N2 复现：同行前置键吃走扫描位置 ⇒ 跨物理行容器 fail-closed 不触发（**组合**形态）。

        组合矩阵（27 格）＝前置（无／`psk=A, `／`a = 1, psk = A, `）× 容器（`[ [`／`{ {`／`[ {`）
        × 引号变体（裸／`"`／`'`），每格都**跨物理行**（首行只开容器、续行才是内容）。矩阵里同时
        含「有前置键」与「无前置键」两格：对照组改前改后都正确，只证孤立样本不足以守住本缺陷
        ——改前基线在「前置键 ＋ 裸 `[ [`／`{ {`」4 格残留续行标记（发布方实测复现）。
        判据＝整份 fail-closed（`out == PRIVACY.REDACTED`，代价已登记）＋标记不残留＋幂等。
        撤防变异：`_CONTAINER_OPEN` 的 `rest` 改回 `(?:(?!\\\\n)[^\\n])*` ⇒ 本用例红（那 4 格）。
        """
        prefixes = ('', 'psk=A, ', 'a = 1, psk = A, ')
        containers = (('[ [', '] ]'), ('{ {', '} }'), ('[ {', '] }'))
        for prefix in prefixes:
            for opener, closer in containers:
                for quote in ('', '"', "'"):
                    with self.subTest(prefix=prefix, opener=opener, quote=quote):
                        sample = ('%stoken = %s%s\n%sN2-1A\n%s%s\n'
                                  % (prefix, quote, opener, self.MARK, closer, quote))
                        out = self._clean(sample, (self.MARK,))
                        self.assertEqual(PRIVACY.REDACTED, out, out)
        # 正控：同行闭合的单层容器（含同行前置键）不得被跨行判据连坐成整份单一标记
        control = self._clean('psk=A, token = [%sN2-2A, %sN2-2B]\n' % (self.MARK, self.MARK),
                              (self.MARK,))
        self.assertNotEqual(PRIVACY.REDACTED, control, control)

    def test_n1_gate_keeps_legal_json_byte_shapes(self):
        """N1 修法的**反向**判据：豁免仍对合法 JSON 文档生效 ⇒ 既有字节形状与可解析性不变。

        判据逐字节取自既有契约（R2 批）：容器值的规范形 `["<redacted>"]` 不得因本轮收窄而退化成
        整值字符串；同时断言 `json.loads` 可解析、标记不残留、`redact_text()` 幂等。
        撤防变异：把豁免改成**从不**开启（`allow_container=False` 常量）⇒ 形状转成契约兜底的整值
        字符串，`assertEqual` 与 `assertNotIn` 均红。
        """
        cases = (
            ('数组容器·紧凑', '{"tokens": ["%sJS-1A", "%sJS-1B"]}' % (self.MARK, self.MARK),
             '{"tokens": ["%s"]}' % PRIVACY.REDACTED),
            ('多键·同行', '{"tokens": ["%sJS-2A"], "x": "keep"}' % self.MARK,
             '{"tokens": ["%s"], "x": "keep"}' % PRIVACY.REDACTED),
            ('缩进布局·同行闭合', '{\n  "tokens": ["%sJS-3A"],\n  "policy": "Proxy"\n}' % self.MARK,
             '{\n  "tokens": ["%s"],\n  "policy": "Proxy"\n}' % PRIVACY.REDACTED),
            ('嵌套对象', '{"a": {"tokens": ["%sJS-4A"]}}' % self.MARK,
             '{"a": {"tokens": ["%s"]}}' % PRIVACY.REDACTED),
        )
        for label, fixture, expected in cases:
            with self.subTest(label=label):
                self.assertIn(self.MARK, fixture, '夹具非空转：标记须在输入里')
                out = PRIVACY.redact_text(fixture)
                self.assertNotIn(self.MARK, out, out)
                self.assertEqual(expected, out, out)
                self.assertEqual(json.loads(expected), self._parse(out))
                self.assertEqual(out, PRIVACY.redact_text(out), out)          # 同入口幂等
                # 公开入口同样不得残留标记、同样可解析、同样幂等（形状由结构化路由决定，另计）
                boundary = PRIVACY.redact_boundary(fixture)
                self.assertNotIn(self.MARK, boundary, boundary)
                self._parse(boundary)
                self.assertEqual(boundary, PRIVACY.redact_boundary(boundary), boundary)

    def test_n1_and_n2_faces_in_one_document(self):
        """N1／N2 同文档组合：两处修复在同一份文本里同时成立（标记不残留＋幂等＋规范形稳定）。

        组合内容＝跨行容器（N2 面）＋同行携密引号尾段（N1 面）＋普通诊断行；判据＝标记不残留、
        同入口幂等；规范形（`<redacted>` 与规范标记容器）二次过入口不变。
        """
        sample = ('psk=A, token = [ [\n%sX-1A\n] ]\n'
                  'token=["x"], "%sX-1B"\n'
                  'loglevel = notify\n' % (self.MARK, self.MARK))
        out = self._clean(sample, (self.MARK,))
        self.assertEqual(PRIVACY.REDACTED, out, out)            # N2 面：跨行容器整份 fail-closed
        # 规范形（既有契约）二次过入口不变；容器规范形 `token=["<redacted>"]` 属**既有**的
        # 「二次收敛」形态（改前改后同形，非本轮引入），故不列入本组不动点断言。
        for canonical in (PRIVACY.REDACTED, 'token=' + PRIVACY.REDACTED,
                          'password=' + PRIVACY.REDACTED + '\n',
                          '"tokens": ["%s"]' % PRIVACY.REDACTED):
            self.assertEqual(canonical, PRIVACY.redact_boundary(canonical), canonical)


class InstalledTierTest(unittest.TestCase):
    """安装态验收档（`--installed`）与 `install.sh` 的安装点核验（2026-10-30）。

    缺陷面：`--offline` 只编译包内 `*.py` 与 md 相对链接，**不校验 PATH 安装点**——
    2026-10-30 技能目录从 `surge` 改名为 `luno-surge` 后 `/usr/local/bin/surge-cli`
    悬空，离线档照样 PASS。本组把整份技能包复制到临时目录（夹具隔离；也避免改仓库
    文件模式——索引里 `scripts/*.py` 是 644，安装时才由 `install.sh` chmod 755），用
    `SURGE_CLI_BIN` 指向临时链接，逐类断言**精确的失败类别**；`install.sh` 只在
    `SURGE_CLI_LINK` 的临时落点上跑，绝不写 `/usr/local/bin`。每个用例自有临时目录，
    不继承宿主 `SURGE_*`，PATH 去掉 `/usr/local/bin`，因此与宿主是否已安装无关。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.pkg = self.tmp / 'pkg'
        shutil.copytree(str(SCRIPTS.parent), str(self.pkg))
        self.scripts = self.pkg / 'scripts'
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _env(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith('SURGE_')}
        env['PATH'] = os.pathsep.join(
            [str(self.bin), os.path.dirname(sys.executable), '/bin', '/usr/bin'])
        env.update(extra)
        return env

    def _run(self, script, *args, **kwargs):
        return subprocess.run(
            ['sh', str(self.scripts / script)] + list(args), cwd=str(self.tmp),
            env=self._env(**kwargs), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=120)

    def _link(self, target):
        path = self.bin / 'surge-cli'
        if path.is_symlink() or path.exists():
            path.unlink()
        path.symlink_to(str(target))
        return path

    @staticmethod
    def _tree_state(root):
        """包目录快照：相对路径 → (字节数, sha256, 权限位)，用于断言「没写入」。"""
        state = {}
        for path in sorted(root.rglob('*')):
            if path.is_file():
                state[str(path.relative_to(root))] = (
                    path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest(),
                    path.stat().st_mode & 0o777)
        return state

    def test_installed_tier_passes_when_link_resolves_into_this_package(self):
        cli = self.scripts / 'surge_cli.py'
        cli.chmod(0o755)
        self._link(cli)
        done = self._run('acceptance.sh', '--installed')
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn('PASS  Offline syntax and local links\n', done.stdout)   # 先跑离线检查
        self.assertIn('PASS  Installed surge-cli resolves to this package\n', done.stdout)

    def test_installed_tier_fails_when_path_entry_is_absent(self):
        done = self._run('acceptance.sh', '--installed')
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn('installed-check: not found on PATH: surge-cli\n', done.stderr)

    def test_installed_tier_fails_when_link_is_dangling(self):
        self._link(self.tmp / 'gone' / 'surge_cli.py')
        done = self._run('acceptance.sh', '--installed')
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn('installed-check: missing target (broken link): surge-cli\n', done.stderr)

    def test_installed_tier_fails_when_target_is_another_copy(self):
        other = self.tmp / 'other' / 'surge_cli.py'
        other.parent.mkdir()
        shutil.copy2(str(self.scripts / 'surge_cli.py'), str(other))
        other.chmod(0o755)
        self._link(other)
        done = self._run('acceptance.sh', '--installed')
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn('installed-check: points elsewhere: surge-cli -> %s (expected %s)\n'
                      % (other, self.scripts / 'surge_cli.py'), done.stderr)

    def test_installed_tier_fails_when_target_is_not_executable(self):
        cli = self.scripts / 'surge_cli.py'
        cli.chmod(0o644)
        self._link(cli)
        done = self._run('acceptance.sh', '--installed')
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn('installed-check: not executable: surge-cli\n', done.stderr)

    def test_offline_tier_passes_while_the_install_point_is_broken(self):
        self._link(self.tmp / 'gone' / 'surge_cli.py')
        done = self._run('acceptance.sh')                     # 默认档＝--offline
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertNotIn('installed-check', done.stderr)

    def test_offline_tier_is_side_effect_free(self):
        """离线档不读安装点、不执行 PATH 中的 CLI、不写包目录（＝不发任何网络请求）。"""
        marker = self.tmp / 'cli-was-run'
        trap = self.tmp / 'surge-cli-trap'
        trap.write_text('#!/bin/sh\ntouch %s\nexit 9\n' % marker)
        trap.chmod(0o755)
        before = self._tree_state(self.pkg)
        done = self._run('acceptance.sh', '--offline', SURGE_CLI_BIN=str(trap))
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertFalse(marker.exists(), '离线档执行了 PATH 中的 surge-cli')
        self.assertEqual(before, self._tree_state(self.pkg), '离线档写入了包目录')

    def test_install_script_links_and_verifies_an_isolated_target(self):
        target = self.bin / 'surge-cli'                       # 落在夹具 PATH 里，才是真装好
        done = self._run('install.sh', SURGE_CLI_LINK=str(target))
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(str(self.scripts / 'surge_cli.py'), os.path.realpath(str(target)))
        self.assertIn('Installed: %s -> %s\n' % (target, self.scripts / 'surge_cli.py'),
                      done.stdout)

    def test_install_script_fails_when_target_is_not_on_path(self):
        """装到 PATH 之外的落点：链接建了，但之后的 `surge-cli` 找不到它（F1）。"""
        target = self.tmp / 'opt' / 'surge-cli'
        target.parent.mkdir()
        done = self._run('install.sh', SURGE_CLI_LINK=str(target))
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertEqual(str(self.scripts / 'surge_cli.py'), os.path.realpath(str(target)),
                         '核验失败前链接本身已建立')
        self.assertNotIn('Installed: ', done.stdout)
        self.assertIn('installed-check: not found on PATH: surge-cli\n', done.stderr)

    def test_install_script_fails_when_earlier_path_entry_points_elsewhere(self):
        """PATH 更前方有可执行的同名文件指向别的副本：本次装的那条没被用到（F1）。"""
        other = self.tmp / 'other' / 'surge_cli.py'
        other.parent.mkdir()
        shutil.copy2(str(self.scripts / 'surge_cli.py'), str(other))
        other.chmod(0o755)
        self._link(other)                                     # `self.bin` 在夹具 PATH 最前
        target = self.tmp / 'opt' / 'surge-cli'
        target.parent.mkdir()
        done = self._run('install.sh', SURGE_CLI_LINK=str(target))
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertNotIn('Installed: ', done.stdout)
        self.assertIn('installed-check: points elsewhere: surge-cli -> %s (expected %s)\n'
                      % (other, self.scripts / 'surge_cli.py'), done.stderr)

    def test_install_script_does_not_report_success_when_link_misses_package(self):
        target = self.tmp / 'opt-dir'                         # 已存在目录：ln 建到目录里
        target.mkdir()
        done = self._run('install.sh', SURGE_CLI_LINK=str(target))
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertNotIn('Installed: ', done.stdout)
        self.assertIn('Install failed: %s does not resolve' % target, done.stderr)


# ── Surge 6 安全分节写入（HTTP 单节 replace）─────────────────────────────────
# 全部经真实子进程入口 `surge_ios.py --confirm-dangerous section replace --input -`：
# stdin 解析 → 实际 urllib → 解码 → 原稿/revision 核对 → 真实备份 I/O → POST → 写后 GET。
# 夹具只替代服务端，不替换生产解码器、传输与编排。哑 key、合成无密正文、本机随机端口。

SEC_KEY = 'synthetic-key-not-a-credential'
SEC_REVISION = 'r-9f3c1a7d5e2b48c6a0f1d3e5b7c9a2f4'
SEC_ORIGINAL = ('# synthetic original\nDOMAIN-SUFFIX,old.invalid,REJECT\nFINAL,DIRECT\n')
SEC_CONTENT = ('# 中文注释、空行与 CRLF\r\n'
               'DOMAIN-SUFFIX,example.invalid,REJECT\n'
               '\n'
               'URL-REGEX,"^https://example\\.invalid/a,b",REJECT\n'
               'FINAL,DIRECT\n')


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


def section_payload(**overrides):
    payload = {'name': 'Rule', 'revision': SEC_REVISION, 'original': SEC_ORIGINAL,
               'content': SEC_CONTENT}
    payload.update(overrides)
    return payload


class SectionServer:
    """`/v1/profiles/section` 合成服务端：记录方法/路径/正文/头，可切 POST 拒绝、断连与并发改写。"""

    def __init__(self, content=SEC_ORIGINAL, revision=SEC_REVISION, post_status=200,
                 post_body=b'{"changed":true,"file":"unexpected-key"}', drop_after_post=False,
                 drop_on_get_after_post=False, post_rewrites=None,
                 truncate_post_response=False, verify_payload=None,
                 garbage_status_line=False, bump_after_get=None, illegal_chunk=None):
        self.content = content
        self.revision = revision
        self.calls = []
        self.post_status = post_status
        self.post_body = post_body
        self.drop_after_post = drop_after_post
        self.drop_on_get_after_post = drop_on_get_after_post
        self.post_rewrites = post_rewrites
        self.truncate_post_response = truncate_post_response
        self.verify_payload = verify_payload
        self.garbage_status_line = garbage_status_line
        # `bump_after_get=n`：第 n 次 GET 应答之后再前进 revision（并发写者），
        #   于是客户端手里那份只有服务端才判得了的新旧对比才是真实的。
        self.bump_after_get = bump_after_get
        # `illegal_chunk='read'|'verify'`：该阶段返回 200 但 chunked 分块长度非法（真实传输层异常）。
        self.illegal_chunk = illegal_chunk
        self.get_count = 0
        self.sent = []              # 真实发出的响应：(status, payload)，供「发送路径命中」断言
        self.stale_rejections = []  # 真实比较判出的旧 revision 拒绝：{'sent':…, 'current':…}
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_GET(self):
                self._dispatch()

            def do_POST(self):
                self._dispatch()

            def log_message(self, *args):
                pass

            def _dispatch(self):
                length = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(length) if length else b''
                server.calls.append({'method': self.command, 'path': self.path,
                                     'body': body,
                                     'headers': {k.lower(): v for k, v in self.headers.items()}})
                posted = any(c['method'] == 'POST' for c in server.calls)
                if self.command == 'POST':
                    status, payload = server._apply_post(body)
                    if server.drop_after_post:
                        # 先落地再断连：客户端只应看到「写可能已发生、无法核验」，
                        # 恢复的起点是该服务端当前的 GET。
                        self.close_connection = True
                        self.connection.close()
                        return
                    if server.garbage_status_line:
                        # 非 HTTP 状态行：客户端读到 BadStatusLine（HTTPException），
                        # 修复前不被 except 覆盖而冒 traceback。
                        self.wfile.write(b'NOT-HTTP\r\n\r\n')
                        self.close_connection = True
                        self.connection.close()
                        return
                    if server.truncate_post_response:
                        # 声明长度大于实际发送：读响应体时抛 IncompleteRead（HTTPException）。
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Content-Length', str(len(payload) + 64))
                        self.end_headers()
                        self.wfile.write(payload[:4])
                        self.close_connection = True
                        self.connection.close()
                        return
                    if server.illegal_chunk == 'post':
                        self._illegal_chunk(status, payload)
                        return
                else:
                    server.get_count += 1
                    if posted and server.drop_on_get_after_post:
                        self.close_connection = True
                        self.connection.close()
                        return
                    if posted and server.verify_payload is not None:
                        payload = server.verify_payload
                    else:
                        payload = _json_bytes({'content': server.content,
                                               'revision': server.revision,
                                               'undocumented': 'unknown-field-value'})
                    phase = 'verify' if posted else 'read'
                    if server.illegal_chunk == phase:
                        self._illegal_chunk(200, payload)
                        return
                    status = 200
                self._reply(status, payload)
                if (self.command == 'GET' and server.bump_after_get is not None
                        and server.get_count == server.bump_after_get):
                    # 并发写者在本客户端读完之后前进 revision：旧值只有服务端比较才拦得住。
                    server.revision = server.revision + '-concurrent'

            def _reply(self, status, payload):
                server.sent.append((status, payload))
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _illegal_chunk(self, status, payload):
                """真实非法分块：200 + `Transfer-Encoding: chunked`，块长度行不是十六进制。"""
                server.sent.append((status, payload))
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                self.wfile.write(b'ZZZZ-not-hex\r\n' + payload + b'\r\n0\r\n\r\n')
                self.close_connection = True
                self.connection.close()

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={'poll_interval': 0.05}, daemon=True)
        self._thread.start()

    @property
    def base(self):
        return 'http://127.0.0.1:%d' % self._server.server_address[1]

    def _apply_post(self, body):
        """真实服务端语义：比较客户端的 revision 与**当前** revision，旧值一律 409 且不落地。

        （不再用固定 409 常量冒充：只有「客户端带的 revision ≠ 本服务端当前值」才拒绝；
        带对的 revision 就落地并把 revision 推进，见 T1 正控。）
        """
        try:
            posted = json.loads(body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            posted = None
        if not isinstance(posted, dict):
            return 400, self.post_body
        if self.post_status != 200:
            return self.post_status, self.post_body
        if posted.get('revision') != self.revision:
            self.stale_rejections.append({'sent': posted.get('revision'),
                                          'current': self.revision})
            return 409, b'{"error":"revision changed"}'
        self.content = posted['content']
        # 真实服务端写入后 revision 前进：恢复必须取「当前 GET」，不能沿用旧值。
        self.revision = self.revision + '-next'
        if self.post_rewrites is not None:
            self.content = self.post_rewrites(self.content)
        return 200, self.post_body

    def posts(self):
        return [c for c in self.calls if c['method'] == 'POST']

    def current(self):
        """直接取该服务端当前的 content/revision（恢复起点，不经被测客户端）。"""
        with urllib.request.urlopen(self.base + '/v1/profiles/section?name=Rule',
                                    timeout=30) as response:
            doc = json.loads(response.read().decode('utf-8'))
        return doc['content'], doc['revision']

    def close(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class SectionWriteTest(unittest.TestCase):
    """Surge 6 安全分节写入 T1–T8（合成数据；不连真实实例、不写活动配置）。"""

    def setUp(self):
        self._servers = []
        self._dirs = []

    def tearDown(self):
        for server in self._servers:
            server.close()
        for path in self._dirs:
            shutil.rmtree(path, ignore_errors=True)

    def server(self, **kwargs):
        server = SectionServer(**kwargs)
        self._servers.append(server)
        return server

    def backup_dir(self, mode=0o700):
        path = tempfile.mkdtemp(prefix='surge6-impl-section-')
        self._dirs.append(path)
        os.chmod(path, mode)
        return path

    def run_section(self, payload, base, confirm=True, extra=(), key=SEC_KEY, env_extra=None):
        args = [sys.executable, str(SURGE_IOS)]
        if confirm:
            args.append('--confirm-dangerous')
        args += ['section', 'replace', '--input', '-', *extra]
        env = offline_env(base)
        env['SURGE_API_KEY'] = key
        for name, value in (env_extra or {}).items():
            env[name] = value
        if isinstance(payload, dict):
            payload = _json_bytes(payload)
        return subprocess.run(args, env=env, input=payload, capture_output=True, timeout=90)

    def run_argv(self, argv, base):
        """按给定 argv 经真实子进程入口执行（用于入口形状反例）。"""
        env = offline_env(base)
        env['SURGE_API_KEY'] = SEC_KEY
        return subprocess.run([sys.executable, str(SURGE_IOS), *argv], env=env,
                              input=b'', capture_output=True, timeout=90)

    def backup_record(self, backup_dir):
        """读真实备份盘上唯一那份记录（合成备份，非夹具内存值）。"""
        files = os.listdir(backup_dir)
        self.assertEqual(1, len(files), files)
        return json.loads(Path(backup_dir, files[0]).read_text(encoding='utf-8'))

    def recover_from_backup(self, server, backup_dir):
        """恢复驱动：先真实 GET 当前正文，与**备份里的 original** 比对；相等则不调用 replace。

        返回 (是否调用过 replace, 当前 content, 当前 revision)。相等分支零 POST，
        且这是驱动的判据，不依赖普通 replace 的 `changed:false` no-op 分支。
        当前既非 original 也非 intended_content（第三方改过该节）时同样零 POST，
        不强制覆盖，交负责人处理冲突（与设计 §恢复路径一致）。
        """
        record = self.backup_record(backup_dir)
        current, revision = server.current()
        if current == record['original']:
            return False, current, revision
        if current != record['intended_content']:
            return False, current, revision
        posts_before = len(server.posts())
        done = self.run_section({'name': 'Rule', 'revision': revision,
                                 'original': current, 'content': record['original'],
                                 'backup_dir': self.backup_dir()}, server.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(posts_before + 1, len(server.posts()))
        after, _ = server.current()
        self.assertEqual(record['original'], after)
        return True, after, revision

    def assert_clean_output(self, done, sentinels):
        blob = done.stdout + done.stderr
        for sentinel in sentinels:
            self.assertNotIn(sentinel.encode('utf-8'), blob)

    # T9（F8）BASE 解析失败：畸形方括号 host／非法端口 ⇒ 固定 E_BASE，退出 2、stdout 空、不回显。
    def test_t9_malformed_base_is_fixed_e_base_without_leak(self):
        sentinel = 'SYNTHETIC-BASE-SENTINEL-DO-NOT-ECHO'
        cases = ('http://[%s' % sentinel, 'http://[%s]:6171' % sentinel,
                 'http://[::1]:99999', 'https://[::1]:99999')
        for base in cases:
            with self.subTest(base=base):
                backup = self.backup_dir()
                payload = {'name': 'p', 'original': 'a:b\n', 'content': 'a:c\n',
                           'revision': 'r1', 'backup_dir': backup}
                done = self.run_section(payload, base)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertEqual(done.stderr, b'E_BASE\n')
                self.assertEqual(done.stdout, b'')
                self.assertNotIn(b'Traceback', done.stderr)          # 修复前 rc=1＋traceback 在此红
                self.assert_clean_output(done, [sentinel])
                self.assertEqual(os.listdir(backup), [])             # 零备份
        # 正控：同一入口下合法 loopback BASE 仍过 origin 门禁，不被本轮捕获吞成 E_BASE
        backup = self.backup_dir()
        ok = self.run_section({'name': 'p', 'original': 'a:b\n', 'content': 'a:c\n',
                              'revision': 'r1', 'backup_dir': backup},
                             'http://127.0.0.1:1')
        self.assertNotEqual(ok.stderr, b'E_BASE\n')
        self.assertEqual(ok.returncode, 4)

    # T1 正常纵切
    def test_t1_vertical_slice_carries_exact_bytes_and_backup(self):
        server = self.server()
        backups = self.backup_dir()
        done = self.run_section(section_payload(backup_dir=backups), server.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({'ok': True, 'changed': True, 'verified': True},
                         json.loads(done.stdout.decode('utf-8')))

        gets = [c for c in server.calls if c['method'] == 'GET']
        posts = server.posts()
        self.assertEqual(3, len(server.calls), [c['method'] for c in server.calls])
        self.assertEqual(2, len(gets))
        self.assertEqual(1, len(posts))
        for call in gets:
            self.assertEqual('/v1/profiles/section?name=Rule', call['path'])
        # POST 恰为 name/content/原 revision 三字段，逐字节一致；不跟随 POST 成功体的未知形状。
        body = json.loads(posts[0]['body'].decode('utf-8'))
        self.assertEqual(['content', 'name', 'revision'], sorted(body))
        self.assertEqual('Rule', body['name'])
        self.assertEqual(SEC_REVISION, body['revision'])
        self.assertEqual(SEC_CONTENT, body['content'])
        self.assertEqual(SEC_KEY, posts[0]['headers']['x-key'])
        self.assertEqual(SEC_CONTENT, server.content)

        files = os.listdir(backups)
        self.assertEqual(1, len(files))
        record = json.loads(Path(backups, files[0]).read_text(encoding='utf-8'))
        self.assertEqual(1, record['format'])
        self.assertEqual(SEC_ORIGINAL, record['original'])
        self.assertEqual(SEC_REVISION, record['revision'])
        self.assertEqual(SEC_CONTENT, record['intended_content'])
        self.assertEqual(0o600, stat.S_IMODE(os.stat(Path(backups, files[0])).st_mode))
        self.assertEqual(0o700, stat.S_IMODE(os.stat(backups).st_mode))
        self.assert_clean_output(done, ['Rule', SEC_REVISION, 'example.invalid', SEC_KEY,
                                        'unknown-field-value', backups])

    # T2 输入负例：固定错误、零网络、零备份
    def test_t2_input_rejections_are_pre_network(self):
        server = self.server()
        backups = self.backup_dir()
        base_payload = section_payload(backup_dir=backups)
        broken_utf8 = json.dumps(base_payload, ensure_ascii=False).encode('utf-8').replace(
            b'Rule', b'Ru\xffle')
        cases = {
            'duplicate key': b'{"name":"Rule","revision":"r","original":"A\\n","content":"B\\n"' \
                             b',"backup_dir":"/tmp","name":"Rule"}',
            'extra key': _json_bytes({**base_payload, 'extra': 'x'}),
            'missing key': _json_bytes({k: v for k, v in base_payload.items() if k != 'original'}),
            'bad utf8': broken_utf8,
            'lone surrogate': b'{"name":"Rule","revision":"r","original":"A\\n","content"' \
                              b':"B\\ud800\\n","backup_dir":"/tmp/forge-surge6-x"}',
            'nul byte': _json_bytes({**base_payload, 'content': 'A\x00B\n'}),
            'two docs': _json_bytes(base_payload) + _json_bytes(base_payload),
            'empty content': _json_bytes({**base_payload, 'content': ''}),
            'section header': _json_bytes({**base_payload, 'content': '[Rule]\nX\n'}),
            # F6：name 不是 header 行，两种分隔符写法都要拒绝
            'bracketed name': _json_bytes({**base_payload, 'name': '[Rule]'}),
            'shebang name': _json_bytes({**base_payload, 'name': '#!include x'}),
            'include line': _json_bytes({**base_payload, 'content': '#!include x.dconf\n'}),
            'oversize': _json_bytes({**base_payload, 'content': 'A' * (256 * 1024 + 1)}),
            'not json': b'not json at all',
        }
        for label, payload in cases.items():
            with self.subTest(label):
                server.calls.clear()
                done = self.run_section(payload, server.base)
                self.assertEqual(2, done.returncode, (label, done.stderr))
                self.assertIn(b'E_INPUT', done.stderr)
                self.assertEqual([], server.calls, label)
                self.assertEqual([], os.listdir(backups), label)

        # 正控：Unicode 节名仍按 UTF-8 正常编码并原样写入 POST。
        server.calls.clear()
        unicode_name = '\u89c4\u5219'
        done = self.run_section(section_payload(backup_dir=backups, name=unicode_name), server.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(unicode_name,
                         json.loads(server.posts()[0]['body'].decode('utf-8'))['name'])
        os.unlink(Path(backups, os.listdir(backups)[0]))

        for label, kwargs in {
            'missing confirm': {'confirm': False},
            'extra argv': {'extra': ('payload',)},
        }.items():
            with self.subTest(label):
                server.calls.clear()
                done = self.run_section(section_payload(backup_dir=backups), server.base, **kwargs)
                self.assertEqual(2, done.returncode, (label, done.stderr))
                self.assertEqual([], server.calls, label)
                self.assertEqual([], os.listdir(backups), label)

    # T3 原稿/revision 与写前变化
    def test_t3_revision_and_original_mismatch_stop_before_post(self):
        backups = self.backup_dir()
        for label, kwargs, token in (
            ('revision moved', {'revision': 'r-other'}, b'E_REVISION_CHANGED'),
            ('original moved', {'content': SEC_ORIGINAL + 'EXTRA,DOMAIN,x\n'}, b'E_ORIGINAL_CHANGED'),
        ):
            with self.subTest(label):
                server = self.server(**kwargs)
                done = self.run_section(section_payload(backup_dir=backups), server.base)
                self.assertEqual(3, done.returncode, done.stderr)
                self.assertIn(token, done.stderr)
                self.assertEqual([], server.posts())
                self.assertEqual([], os.listdir(backups))

        server = self.server()
        server.revision = ''
        done = self.run_section(section_payload(backup_dir=backups), server.base)
        self.assertEqual(4, done.returncode, done.stderr)
        self.assertIn(b'E_READ_DECODE', done.stderr)
        self.assertEqual([], server.posts())

    def test_t3_server_rejects_write_without_resend(self):
        backups = self.backup_dir()
        server = self.server(post_status=400)
        done = self.run_section(section_payload(backup_dir=backups), server.base)
        self.assertEqual(4, done.returncode, done.stderr)
        self.assertIn(b'E_REJECTED 400', done.stderr)
        self.assertEqual(1, len(server.posts()))
        self.assert_clean_output(done, ['synthetic rejection'])

    def test_t3_server_side_revision_compare_rejects_stale_write(self):
        """GET 之后 revision 前进：由服务端真实比较并拒绝，客户端不重投。

        变异可达性：把生产入口 `section_http("POST"…)` 的 revision 换成任何非当前值，
        T1 正常纵切会被同一服务端真比较拒绝（409 ⇒ 4），故本用例不可能靠固定 409 冒充通过。
        """
        backups = self.backup_dir()
        stale = self.server(bump_after_get=1)        # 第 1 次 GET 应答后并发写者推进 revision
        done = self.run_section(section_payload(backup_dir=backups), stale.base)
        self.assertEqual(4, done.returncode, done.stderr)
        self.assertIn(b'E_REJECTED 409', done.stderr)
        self.assertEqual(b'', done.stdout)
        self.assertEqual(1, len(stale.posts()))                    # 不重投
        self.assertEqual([{'sent': SEC_REVISION,
                           'current': SEC_REVISION + '-concurrent'}],
                         stale.stale_rejections)                    # 比的是客户端真发来的值
        self.assertEqual(SEC_ORIGINAL, stale.content)              # 未接受写入
        self.assertEqual(SEC_REVISION + '-concurrent', stale.revision)
        self.assert_clean_output(done, [SEC_CONTENT, SEC_REVISION])

        # 正控：同一夹具、同一入口，revision 未被推进 ⇒ 同一比较放行并落地。
        ok = self.server()
        done = self.run_section(section_payload(backup_dir=backups), ok.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], ok.stale_rejections)
        self.assertEqual(SEC_CONTENT, ok.content)

    # T4 受控备份：目录在联网前用 dirfd 逐级打开，写入不再按完整路径重解析
    def test_t4_backup_dir_is_rejected_before_any_request(self):
        cases = {}
        cases['world readable dir'] = self.backup_dir(mode=0o755)
        # 精确 0700：仅所有者可写的 0500 也只读、不能建文件，必须同口径拒绝（不依赖 uid==0 跳过）。
        cases['read only dir'] = self.backup_dir(mode=0o500)
        symlinked = self.backup_dir()
        link = os.path.join(tempfile.mkdtemp(prefix='surge6-impl-link-'), 'link')
        self._dirs.append(os.path.dirname(link))
        os.symlink(symlinked, link)
        cases['symlinked component'] = link
        cases['missing dir'] = '/nonexistent/forge-surge6-implementation'
        cases['ambiguous component'] = os.path.dirname(symlinked) + '//' + os.path.basename(symlinked)
        holder = tempfile.mkdtemp(prefix='surge6-impl-file-')
        self._dirs.append(holder)
        not_a_dir = os.path.join(holder, 'plain-file')
        Path(not_a_dir).write_text('x', encoding='utf-8')
        cases['not a directory'] = not_a_dir
        for label, path in cases.items():
            with self.subTest(label):
                server = self.server()
                done = self.run_section(section_payload(backup_dir=path), server.base)
                self.assertEqual(2, done.returncode, (label, done.stderr))
                self.assertIn(b'E_BACKUP_DIR', done.stderr)
                self.assertEqual([], server.calls, label)     # 网络前拒绝：一个请求都不发
                self.assertEqual([], os.listdir(symlinked), label)

    def test_t4_backup_writes_stay_on_the_opened_directory(self):
        """EEXIST／fsync 失败只清本次创建的文件；祖先替换后写入仍落在已打开的目录。"""
        module = load_module('surge_ios_section_backup', SURGE_IOS)
        real_secrets = module.secrets
        write = tempfile.mkdtemp(prefix='surge6-impl-own-')
        self._dirs.append(write)
        os.chmod(write, 0o700)
        edit = {'name': 'Rule', 'revision': SEC_REVISION, 'original': SEC_ORIGINAL,
                'content': SEC_CONTENT, 'backup_dir': write}
        existing = Path(write, 'section-fixed.json')
        existing.write_text('pre-existing', encoding='utf-8')
        try:
            # O_EXCL 失败（同名既有文件）：不得 unlink 既有文件。
            module.secrets = types.SimpleNamespace(token_hex=lambda _n: 'fixed')
            fd = module._open_backup_dir(write)
            try:
                with self.assertRaises(module.SectionStop) as caught:
                    module.save_section_backup(edit, fd)
            finally:
                os.close(fd)
            self.assertEqual('E_BACKUP_WRITE', str(caught.exception))
            self.assertEqual('pre-existing', existing.read_text(encoding='utf-8'))

            # fsync 失败：清理只针对本次创建的文件，既有文件保持原样。
            module.secrets = types.SimpleNamespace(token_hex=lambda _n: 'fixed2')
            real_fsync = os.fsync

            def refuse(_fd):
                raise OSError(errno.EIO, 'synthetic fsync failure')

            os.fsync = refuse
            fd = module._open_backup_dir(write)
            try:
                with self.assertRaises(module.SectionStop):
                    module.save_section_backup(edit, fd)
            finally:
                os.close(fd)
                os.fsync = real_fsync
        finally:
            module.secrets = real_secrets
        self.assertEqual(['section-fixed.json'], sorted(os.listdir(write)))

        # 祖先替换：先持有目录 fd，再把上级换成指向诱饵目录的链接；写入仍落在原目录。
        top = tempfile.mkdtemp(prefix='surge6-impl-race-')
        self._dirs.append(top)
        real_dir, decoy = Path(top, 'real'), Path(top, 'decoy')
        real_dir.mkdir()
        decoy.mkdir()
        os.chmod(real_dir, 0o700)
        os.chmod(decoy, 0o700)
        fd = module._open_backup_dir(str(real_dir))
        try:
            os.rename(str(real_dir), str(Path(top, 'moved-real')))
            os.symlink(str(decoy), str(real_dir))
            edit['backup_dir'] = str(real_dir)
            made = module.save_section_backup(edit, fd)
        finally:
            os.close(fd)
        self.assertEqual([], sorted(p.name for p in decoy.iterdir()))
        self.assertEqual(1, len(list(Path(top, 'moved-real').iterdir())))
        self.assertTrue(made.startswith(str(real_dir)))

    # T5 泄露：裸数据哨兵必须真实到达，输出只留固定 token
    def test_t5_no_secret_or_body_in_output(self):
        sentinels = ['SENTINEL-BODY-1', 'SENTINEL-REV-2', 'SENTINEL-KEY-3',
                     'SENTINEL-ERR-4', 'SENTINEL-UNKNOWN-5', 'SENTINEL-GUARD-6']
        backups = self.backup_dir()
        # 500 必须真实到达（POST 一次），且响应体是**含用户数据合成哨兵**的原文：
        #   先证夹具确实把它发出去了（sent 记录），再证输出不回显。
        leaky = self.server(post_status=500)
        leaky.post_body = (_json_bytes({'error': 'SENTINEL-ERR-4', 'echo': SEC_CONTENT,
                                        'key': SEC_KEY}))
        done = self.run_section(section_payload(backup_dir=backups), leaky.base)
        self.assertEqual(1, len(leaky.posts()))
        self.assertEqual((500, leaky.post_body), leaky.sent[-1])   # 发送路径真实命中
        self.assertIn(b'SENTINEL-ERR-4', leaky.sent[-1][1])        # 裸哨兵真的在线路上
        self.assertEqual(5, done.returncode, done.stderr)
        self.assertIn(b'E_WRITE_UNKNOWN 500', done.stderr)
        self.assertEqual(b'', done.stdout)
        self.assert_clean_output(done, sentinels + [SEC_CONTENT, SEC_KEY])

        rejected = self.server(post_status=400)
        done = self.run_section(section_payload(backup_dir=backups), rejected.base)
        self.assertEqual(4, done.returncode, done.stderr)
        self.assertEqual(1, len(rejected.posts()))
        self.assertIn(b'E_REJECTED 400', done.stderr)
        self.assert_clean_output(done, sentinels)

        # 写后 GET 回来的是**另一组**裸哨兵：退出码 5、正文不外泄。
        for body in (b'{"content":"SENTINEL-BODY-1","revision":"SENTINEL-REV-2"}'
                     b' SENTINEL-GUARD-6',
                     _json_bytes({'content': 'SENTINEL-BODY-1'}),
                     b'{"content":1,"revision":"SENTINEL-REV-2"}'):
            with self.subTest(body):
                server = self.server(verify_payload=body)
                done = self.run_section(section_payload(backup_dir=backups), server.base)
                self.assertEqual(5, done.returncode, done.stderr)
                self.assertIn(b'E_VERIFY_FAILED', done.stderr)
                self.assertEqual(b'', done.stdout)
                self.assertEqual(1, len(server.posts()))
                self.assertNotIn(b'Traceback', done.stderr)
                self.assert_clean_output(done, sentinels)

        unknown_body = self.server(post_body=b'{"changed":true,"SENTINEL-UNKNOWN-5":"x"}')
        done = self.run_section(section_payload(backup_dir=backups), unknown_body.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(b'{"changed":true,"ok":true,"verified":true}\n', done.stdout)
        self.assert_clean_output(done, sentinels)

    # T6 TLS／远端门禁
    def test_t6_remote_plaintext_and_tls_verification(self):
        backups = self.backup_dir()
        server = self.server()
        remote_base = server.base.replace('127.0.0.1', '203.0.113.7')
        done = self.run_section(section_payload(backup_dir=backups), remote_base)
        self.assertEqual(2, done.returncode, done.stderr)
        self.assertIn(b'E_TLS_REQUIRED', done.stderr)
        self.assertEqual([], server.calls)

        done = self.run_section(section_payload(backup_dir=backups), remote_base,
                                env_extra={'SURGE_ALLOW_REMOTE': '1'})
        self.assertEqual(2, done.returncode, done.stderr)
        self.assertIn(b'E_TLS_REQUIRED', done.stderr)
        self.assertEqual([], server.calls)

    def test_t6_tls_untrusted_certificate_is_not_bypassed(self):
        cert_dir = tempfile.mkdtemp(prefix='surge6-impl-tls-')
        self._dirs.append(cert_dir)
        if not shutil.which('openssl'):
            self.skipTest('openssl unavailable: TLS fixture not covered')
        cert, key = os.path.join(cert_dir, 'cert.pem'), os.path.join(cert_dir, 'key.pem')
        made = subprocess.run(
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
             '-subj', '/CN=localhost', '-keyout', key, '-out', cert],
            capture_output=True, timeout=120)
        if made.returncode != 0:
            self.skipTest('openssl could not build the test certificate')
        backups = self.backup_dir()
        server = self.server()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server._server.socket = context.wrap_socket(server._server.socket, server_side=True)
        base = server.base.replace('http://', 'https://')
        done = self.run_section(section_payload(backup_dir=backups), base)
        self.assertEqual(4, done.returncode, done.stderr)
        self.assertIn(b'E_READ_FAILED', done.stderr)
        self.assertEqual([], server.posts())
        self.assertEqual([], os.listdir(backups))
        self.assert_clean_output(done, [SEC_CONTENT, SEC_REVISION, SEC_KEY])

    def test_t6_tls_trusted_ca_and_hostname_mismatch(self):
        """可信 CA 正向必须成功；hostname 错配必须失败——两者都不以关闭 TLS 校验实现。"""
        if not shutil.which('openssl'):
            self.skipTest('openssl unavailable: TLS fixture not covered')
        cert_dir = tempfile.mkdtemp(prefix='surge6-impl-ca-')
        self._dirs.append(cert_dir)
        ca, ca_key = str(Path(cert_dir, 'ca.pem')), str(Path(cert_dir, 'ca.key'))
        cert, key = str(Path(cert_dir, 'cert.pem')), str(Path(cert_dir, 'key.pem'))
        csr, ext = str(Path(cert_dir, 'req.csr')), str(Path(cert_dir, 'ext.cnf'))
        Path(ext).write_text('subjectAltName=DNS:localhost\n', encoding='utf-8')
        steps = (
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
             '-subj', '/CN=lens-synthetic-ca', '-keyout', ca_key, '-out', ca],
            ['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=localhost',
             '-keyout', key, '-out', csr],
            ['openssl', 'x509', '-req', '-in', csr, '-days', '1', '-CA', ca, '-CAkey', ca_key,
             '-CAcreateserial', '-extfile', ext, '-out', cert],
        )
        for argv in steps:
            made = subprocess.run(argv, capture_output=True, timeout=180)
            if made.returncode != 0:
                self.skipTest('openssl could not build the test certificate chain')
        backups = self.backup_dir()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)

        trusted = self.server()
        trusted._server.socket = context.wrap_socket(trusted._server.socket, server_side=True)
        done = self.run_section(
            section_payload(backup_dir=backups),
            'https://localhost:%d' % trusted._server.server_address[1],
            # localhost 不是 loopback 字面量：https 非本机字面量按既有门禁需显式放行
            env_extra={'SSL_CERT_FILE': ca, 'SURGE_ALLOW_REMOTE': '1'})
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(1, len(trusted.posts()))
        self.assertEqual(SEC_CONTENT, trusted.content)

        mismatch = self.server()
        mismatch_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        mismatch_context.load_cert_chain(cert, key)
        mismatch._server.socket = mismatch_context.wrap_socket(
            mismatch._server.socket, server_side=True)
        done = self.run_section(
            section_payload(backup_dir=backups),
            'https://127.0.0.1:%d' % mismatch._server.server_address[1],
            env_extra={'SSL_CERT_FILE': ca})
        self.assertEqual(4, done.returncode, done.stderr)
        self.assertIn(b'E_READ_FAILED', done.stderr)
        self.assertEqual([], mismatch.calls)
        self.assert_clean_output(done, [SEC_KEY, SEC_CONTENT])

    # T7 写入未知与恢复：POST 落地后才断连，恢复取该服务端当前 GET
    def test_t7_unknown_after_post_and_recovery_path(self):
        backups = self.backup_dir()
        dropped = self.server(drop_after_post=True)
        done = self.run_section(section_payload(backup_dir=backups), dropped.base)
        self.assertEqual(5, done.returncode, done.stderr)
        self.assertIn(b'E_WRITE_UNKNOWN', done.stderr)
        self.assertEqual(1, len(dropped.posts()))
        self.assertNotIn(b'"ok":true', done.stdout)
        # 断连发生在写入落地之后：服务端已是新正文、revision 已前进。
        landed_content, landed_revision = dropped.current()
        self.assertEqual(SEC_CONTENT, landed_content)
        self.assertNotEqual(SEC_REVISION, landed_revision)

        # 同一服务端继续服务（不是另起一台）：恢复 stdin 由「备份 original + 该服务端当前
        # GET revision」生成，落地写一次即回到原稿。
        dropped.drop_after_post = False
        record = self.backup_record(backups)
        self.assertEqual(SEC_ORIGINAL, record['original'])
        self.assertEqual(SEC_REVISION, record['revision'])
        current, revision = dropped.current()
        self.assertEqual(SEC_CONTENT, current)              # 断连前的写真的落地了
        self.assertEqual(SEC_REVISION + '-next', revision)  # 且 revision 已前进
        restore_dir = self.backup_dir()
        restore = {'name': 'Rule', 'revision': revision, 'original': current,
                   'content': record['original'], 'backup_dir': restore_dir}
        posts_before = len(dropped.posts())
        done = self.run_section(restore, dropped.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(b'{"changed":true,"ok":true,"verified":true}\n', done.stdout)
        self.assertEqual(posts_before + 1, len(dropped.posts()))
        self.assertEqual(SEC_ORIGINAL, dropped.current()[0])

        # 第三方后续编辑（当前正文 != 恢复起点）：恢复必须停止，一个 POST 都不发。
        edited = SEC_CONTENT + 'NEW,RULE,REJECT\n'
        third = self.server(content=edited, revision=revision)
        done = self.run_section({**restore, 'backup_dir': self.backup_dir()}, third.base)
        self.assertEqual(3, done.returncode, done.stderr)
        self.assertIn(b'E_ORIGINAL_CHANGED', done.stderr)
        self.assertEqual([], third.posts())
        self.assertEqual(edited, third.current()[0])

    def test_t7_recovery_driver_skips_replace_when_backup_original_is_current(self):
        """④ 恢复驱动先核「当前 == 备份 original」：相等就不调用 replace，恢复阶段零 POST。"""
        backups = self.backup_dir()
        landed = self.server()
        done = self.run_section(section_payload(backup_dir=backups), landed.base)
        self.assertEqual(0, done.returncode, done.stderr)
        record = self.backup_record(backups)
        self.assertEqual(SEC_ORIGINAL, record['original'])

        # 先真实恢复一次（另用一份备份目录），使当前正文等于备份 original。
        done = self.run_section({'name': 'Rule', 'revision': landed.revision,
                                 'original': SEC_CONTENT, 'content': record['original'],
                                 'backup_dir': self.backup_dir()}, landed.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(record['original'], landed.current()[0])

        posts_before = len(landed.posts())
        calls_before = len(landed.calls)
        called, current, _ = self.recover_from_backup(landed, backups)
        self.assertFalse(called)                                    # 未调用 replace
        self.assertEqual(record['original'], current)
        self.assertEqual(posts_before, len(landed.posts()))         # 恢复阶段零 POST
        self.assertEqual(calls_before + 1, len(landed.calls))       # 只有驱动自己的那次 GET
        self.assertEqual('GET', landed.calls[-1]['method'])

    # F7-a 写后核验的真实触发：POST 落地后该节被改写（服务端 post_rewrites），
    #   写后 GET 的 content 与 intended_content 不同 ⇒ 固定 E_VERIFY_FAILED/5、stdout 空、
    #   恰一次 POST（不重投）、服务端保留被改写后的正文。失败来自内容比较，不是缺字段。
    def test_t7_post_write_rewrite_is_verify_failure(self):
        backups = self.backup_dir()
        server = self.server(post_rewrites=lambda body: body + '# third-party rewrite\n')
        done = self.run_section(section_payload(backup_dir=backups), server.base)
        self.assertEqual(5, done.returncode, done.stderr)
        self.assertEqual(b'E_VERIFY_FAILED\n', done.stderr)
        self.assertEqual(b'', done.stdout)
        self.assertEqual(1, len(server.posts()))
        self.assertEqual(['GET', 'POST', 'GET'], [c['method'] for c in server.calls])
        self.assertEqual(SEC_CONTENT + '# third-party rewrite\n', server.content)
        self.assertNotEqual(SEC_CONTENT, server.content)
        self.assertNotEqual(SEC_REVISION, server.revision)

    # F7-b 恢复驱动：同服务器落地写后当前正文又被第三方改过（既非 original 也非
    #   intended_content）⇒ 驱动不恢复、零 POST、第三方内容保留，只多一次 GET。
    def test_t7_recover_driver_stops_on_third_party_edit(self):
        backups = self.backup_dir()
        landed = self.server()
        done = self.run_section(section_payload(backup_dir=backups), landed.base)
        self.assertEqual(0, done.returncode, done.stderr)
        record = self.backup_record(backups)
        self.assertEqual(SEC_ORIGINAL, record['original'])
        self.assertEqual(SEC_CONTENT, record['intended_content'])
        # 同一服务器：真实写入已落地，第三方随后改写该节并推进 revision。
        edited = SEC_CONTENT + 'THIRD,PARTY,REJECT\n'
        landed.content = edited
        landed.revision = landed.revision + '-third'
        posts_before = len(landed.posts())
        calls_before = len(landed.calls)
        called, current, revision = self.recover_from_backup(landed, backups)
        self.assertFalse(called)                                     # 未调用 replace
        self.assertEqual(edited, current)
        self.assertEqual(posts_before, len(landed.posts()))          # 恢复阶段零 POST
        self.assertEqual(['GET'], [c['method'] for c in landed.calls[calls_before:]])
        self.assertEqual(landed.revision, revision)                  # 未因恢复而推进
        self.assertEqual(edited, landed.current()[0])                # 第三方内容保留

    # T9 入口形状与通用 POST 的固定 token（F3）
    # ⑤ 真实触发：写后 GET 断连／备份目录下降中途祖先换链／真实非法分块
    def test_t10_write_landed_but_verify_read_disconnects(self):
        """POST 落地后**写后 GET** 被断连：结果未知（5），不重投，判据以服务端状态核。"""
        backups = self.backup_dir()
        server = self.server(drop_on_get_after_post=True)
        done = self.run_section(section_payload(backup_dir=backups), server.base)
        self.assertEqual(5, done.returncode, done.stderr)
        self.assertIn(b'E_VERIFY_FAILED', done.stderr)
        self.assertNotIn(b'Traceback', done.stderr)
        self.assertEqual(b'', done.stdout)
        self.assertEqual(1, len(server.posts()))              # 不重投
        self.assertEqual(SEC_CONTENT, server.content)         # 写确实已落地
        self.assertEqual(['GET', 'POST', 'GET'],
                         [c['method'] for c in server.calls])  # 断连的写后 GET 只发一次
        self.assert_clean_output(done, [SEC_CONTENT, SEC_REVISION, SEC_KEY])

    def test_t10_illegal_chunked_body_is_stage_classified(self):
        """真实非法分块（chunked 长度行非十六进制）：读阶段 4／写后核验阶段 5，均无 traceback。"""
        backups = self.backup_dir()
        read = self.server(illegal_chunk='read')
        done = self.run_section(section_payload(backup_dir=backups), read.base)
        self.assertEqual(4, done.returncode, done.stderr)
        self.assertIn(b'E_READ_FAILED', done.stderr)
        self.assertEqual([], read.posts())
        self.assertNotIn(b'Traceback', done.stderr)
        self.assertEqual([], os.listdir(backups))
        self.assert_clean_output(done, [SEC_CONTENT, SEC_REVISION, SEC_KEY])

        verify = self.server(illegal_chunk='verify')
        done = self.run_section(section_payload(backup_dir=backups), verify.base)
        self.assertEqual(5, done.returncode, done.stderr)
        self.assertIn(b'E_VERIFY_FAILED', done.stderr)
        self.assertEqual(1, len(verify.posts()))
        self.assertNotIn(b'Traceback', done.stderr)
        self.assertEqual(b'', done.stdout)
        self.assert_clean_output(done, [SEC_CONTENT, SEC_REVISION, SEC_KEY,
                                        'ZZZZ-not-hex'])

    def test_t4_backup_dir_refuses_ancestor_swapped_mid_descent(self):
        """下降**途中**（还没走到该层）祖先被换成符号链接：拒绝且诱饵目录零写入。

        与「先持末级 fd 再换链」不同，这里换链发生在 `_open_backup_dir` 的下降过程内，
        故判据是「拒绝」而不是「仍写到原目录」。
        """
        module = load_module('surge_ios_section_backup_descent', SURGE_IOS)
        top = tempfile.mkdtemp(prefix='surge6-impl-descent-')
        self._dirs.append(top)
        real = Path(top, 'real')
        real.mkdir()
        decoy = Path(top, 'decoy')
        decoy.mkdir()
        target = real / 'backups'
        target.mkdir()
        (decoy / 'backups').mkdir()          # 诱饵里预置同名末级目录：非 fd 下降会落进去
        for path in (real, decoy, target, decoy / 'backups'):
            os.chmod(path, 0o700)
        real_open = os.open
        swapped = []

        def racing(path, flags, *args, **kwargs):
            if path == 'real' and kwargs.get('dir_fd') is not None and not swapped:
                os.rename(str(real), str(Path(top, 'moved-real')))
                os.symlink(str(decoy), str(real))
                swapped.append(True)
            return real_open(path, flags, *args, **kwargs)

        fd = None
        os.open = racing
        try:
            with self.assertRaises(module.SectionStop) as caught:
                fd = module._open_backup_dir(str(target))
        finally:
            os.open = real_open
            if fd is not None:
                os.close(fd)
        self.assertTrue(swapped, '下降途中未发生换链，用例未触发故障面')
        self.assertEqual('E_BACKUP_DIR', str(caught.exception))
        self.assertEqual([], sorted(p.name for p in (decoy / 'backups').iterdir()))
        self.assertEqual([], sorted(p.name for p in Path(top, 'moved-real',
                                                        'backups').iterdir()))

    def test_t9_entry_shape_and_generic_post_are_fixed_tokens(self):
        sentinel = 'SENTINEL-ARGV-7'
        server = self.server()
        backups = self.backup_dir()
        variants = {
            'unknown option': ['--confirm-dangerous', 'section', 'replace', '--input', '-',
                               '--' + sentinel],
            'missing value': ['--confirm-dangerous', 'section', 'replace', '--input'],
            'stray positional': ['--confirm-dangerous', 'section', 'replace', '--input', '-',
                                 sentinel],
            'path instead of stdin': ['section', 'replace', '--input', '/tmp/' + sentinel],
            'swapped order': ['section', 'replace', '-', '--input'],
            'bare section': ['section'],
        }
        for label, argv in variants.items():
            with self.subTest(label):
                server.calls.clear()
                done = self.run_argv(argv, server.base)
                self.assertEqual(2, done.returncode, (label, done.stderr))
                self.assertIn(b'E_INPUT', done.stderr)
                self.assertEqual(b'', done.stdout, label)
                self.assertNotIn(b'Traceback', done.stderr, label)
                self.assert_clean_output(done, [sentinel])
                self.assertEqual([], server.calls, label)
                self.assertEqual([], os.listdir(backups), label)

        # 通用 POST 的分节路由必须在 json 解析、取密与联网之前拒绝：非法 JSON 也只有固定 token。
        for body in ('{"name":"Rule"', '[1,2,', 'SENTINEL-ARGV-7'):
            with self.subTest(body):
                server.calls.clear()
                done = run_script(SURGE_IOS, ['request', 'POST', '/v1/profiles/section', body],
                                  server.base)
                self.assertEqual(2, done.returncode, done.stderr)
                self.assertIn('E_SECTION_WRITE_REQUIRES_SAFE_ENTRY', done.stderr)
                self.assertNotIn('Traceback', done.stderr)
                self.assertNotIn(sentinel, done.stderr)
                self.assertEqual([], server.calls)

    # T10 写阶段失败：阶段化 token 与传输级协议异常（F4）
    def test_t10_write_phase_failures_are_not_mistaken_for_reads(self):
        backups = self.backup_dir()
        for label, body in (
            ('verify not json', b'not-json-SENTINEL-GUARD-6'),
            ('verify missing revision', b'{"content":"x"}'),
            ('verify wrong type', b'{"content":1,"revision":"r"}'),
        ):
            with self.subTest(label):
                server = self.server(verify_payload=body)
                done = self.run_section(section_payload(backup_dir=backups), server.base)
                self.assertEqual(5, done.returncode, (label, done.stderr))
                self.assertIn(b'E_VERIFY_FAILED', done.stderr)
                self.assertEqual(1, len(server.posts()), label)
                self.assertNotIn(b'Traceback', done.stderr)

        # 传输级协议异常（非 HTTP 状态行）：写阶段一律「结果未知」5、不重试、无 traceback。
        garbage = self.server(garbage_status_line=True)
        done = self.run_section(section_payload(backup_dir=backups), garbage.base)
        self.assertEqual(5, done.returncode, done.stderr)
        self.assertIn(b'E_WRITE_UNKNOWN', done.stderr)
        self.assertEqual(1, len(garbage.posts()))
        self.assertNotIn(b'Traceback', done.stderr)

        # POST 响应体被截断（声明长度大于实际发送）：写已落地，结论以写后 GET 为准。
        truncated = self.server(truncate_post_response=True)
        done = self.run_section(section_payload(backup_dir=backups), truncated.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(1, len(truncated.posts()))
        self.assertEqual(SEC_CONTENT, truncated.current()[0])

    # T8 护栏与旧行为
    def test_t8_guardrails_block_bypass_and_keep_reads(self):
        sentinel = 'SENTINEL-GUARD-9'
        for path in ('/v1/profiles/section', '//v1//profiles//section',
                     '/v1/profiles/%73ection', '/v1/profiles/./section/',
                     '/V1/Profiles/Section', '/v1/x/../profiles/section'):
            with self.subTest(path):
                server = self.server()
                done = run_script(SURGE_IOS, ['request', 'POST', path, '{"name":"Rule"}'],
                                  server.base)
                self.assertEqual(2, done.returncode, done.stderr)
                self.assertIn('E_SECTION_WRITE_REQUIRES_SAFE_ENTRY', done.stderr)
                self.assertEqual([], server.calls)
                self.assertNotIn('Rule', done.stderr)

        read = self.server()
        done = run_script(SURGE_IOS, ['request', 'GET', '/v1/profiles/section?name=Rule'],
                          read.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(['/v1/profiles/section?name=Rule'], [c['path'] for c in read.calls])

        # CLI：set 在读文件/取密/连接前拒绝（Controller 收不到任何帧）；list/get 仍达服务端。
        for args in (['profile', 'section', 'set', 'Rule', sentinel],
                     ['--raw', 'Profile', 'SECTION', 'Set', 'Rule', sentinel],
                     ['profile', 'section', 'SET', 'Rule', '-']):
            with self.subTest(args):
                controller = LocalController({'result': 'ok'})
                self.addCleanup(controller.close)
                done = run_cli(args, remote=controller.remote, stdin=sentinel)
                self.assertEqual(2, done.returncode, done.stderr)
                self.assertIn('E_SECTION_SET_REQUIRES_LOCAL_ADAPTER', done.stderr)
                self.assertEqual([], controller.passwords)
                self.assertEqual([], controller.commands)
                self.assertNotIn(sentinel, done.stderr)

        for args in (['profile', 'section', 'list'], ['profile', 'section', 'get', 'Rule']):
            with self.subTest(args):
                controller = LocalController({'result': 'ok'})
                self.addCleanup(controller.close)
                done = run_cli(args, remote=controller.remote)
                self.assertEqual(0, done.returncode, done.stderr)
                self.assertEqual(1, len(controller.commands))
                self.assertTrue(controller.commands[0].lower().startswith('profile "section"'),
                                controller.commands[0])

    def test_t8_check_requires_a_readable_profile(self):
        """`--check` 合法但无 Controller 命令：读不到文件必须失败，不得打帮助退出 0。"""
        done = run_cli(['--check', '/nonexistent/lens-synthetic-profile.conf'])
        self.assertEqual(2, done.returncode, done.stderr)
        self.assertEqual('', done.stdout)
        self.assertIn('Cannot read profile file', done.stderr)


class OfficialFilesAbsentTest(unittest.TestCase):
    """公开快照不含官方参考原件（2026-11-06 r3）：仓库侧正面核登记、哈希与文档，不靠 skip 掩盖。

    3 份参考原件（`upstream-SKILL.md`、`upstream-command-reference.md`、`plugin-authoring.md`）
    只在部署取件后进本端；`agents/openai.yaml` 是本地有意改写的自有文件，随包分发、按普通资源
    登记（从 df54a93 按原字节恢复）。仓库必须仍保留 manifest 的**五文件** `raw_sha256`
    （64 位小写十六进制）、`officialPackageResources` 只对 `luno-surge` 有效且逐条映射到其中
    3 份参考文件的哈希，以及 SOURCE.md〈取件与部署〉的取件方法。

    跳过用例分档（`requires_official`）：**仓库内跳过**——公开快照不含原件，需要真实官方文字
    字节的用例在本仓库 skip；**部署取件后另跑**——按 SOURCE.md〈取件与部署〉装入 3 份原件后
    重跑 `group surge`，此时这些用例带真实原件执行、不再 skip。两份用例集合由装饰器决定，
    本文件不硬编码清单副本；分档本身由下面的 `test_skip_split_*` 断言。
    """

    REFERENCES = ('skills/luno-surge/references/upstream-SKILL.md',
                  'skills/luno-surge/references/upstream-command-reference.md',
                  'skills/luno-surge/references/plugin-authoring.md')
    #: 仓库路径 → manifest `raw_sha256` 的包内路径（与 SOURCE.md〈取件与部署〉第 3 步同源）
    MAPPING = {REFERENCES[0]: 'SKILL.md',
               REFERENCES[1]: 'references/command-reference.md',
               REFERENCES[2]: 'references/plugin-authoring.md'}
    HEX64 = re.compile(r'^[0-9a-f]{64}$')

    def registry(self):
        doc = json.loads((ROOT / 'tools/sync-targets.json').read_text(encoding='utf-8'))
        return doc, [o for o in doc['objects'] if o.get('id') == 'luno-surge'][0]

    def manifest(self):
        return json.loads((ROOT / 'skills/luno-surge/references/upstream-manifest.json')
                          .read_text(encoding='utf-8'))

    def test_originals_either_all_absent_or_all_fetched(self):
        """公开态＝3 件全缺；取件态＝3 件齐且哈希等于 manifest。只装一部分或哈希不符即报红。"""
        present = [rel for rel in self.REFERENCES if (ROOT / rel).is_file()]
        if not present:
            return
        self.assertEqual(sorted(present), sorted(self.REFERENCES), '取件须 3 件齐全，不得只装一部分')
        raw = self.manifest()['raw_sha256']
        for rel in self.REFERENCES:
            self.assertEqual(raw[self.MAPPING[rel]],
                             hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), rel)

    def test_self_owned_agent_yaml_is_present_and_not_official(self):
        rel = 'skills/luno-surge/agents/openai.yaml'
        self.assertTrue((ROOT / rel).is_file(), '自有 agents/openai.yaml 必须随包分发')
        digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        official = self.manifest()['raw_sha256']['agents/openai.yaml']
        self.assertNotEqual(digest, official, '本地改写文件不得与官方原件同哈希')
        _doc, obj = self.registry()
        self.assertIn(rel, obj['resources'], '自有文件按普通资源登记')
        self.assertNotIn(rel, obj['officialPackageResources']['paths'],
                         '自有文件不得出现在取件名单')

    def test_declared_as_official_package_resources(self):
        _doc, obj = self.registry()
        block = obj['officialPackageResources']
        self.assertIsInstance(block.get('note'), str)
        self.assertTrue(block['note'].strip(), '登记必须写明用途')
        self.assertEqual(sorted(self.REFERENCES), sorted(block['paths']))
        raw = self.manifest()['raw_sha256']
        for rel in block['paths']:
            self.assertIn(self.MAPPING[rel], raw, rel)
            self.assertNotIn(rel, obj['resources'], '取件原件不得同时当普通资源登记')
        # G2 负控方向：别处塞必需文件进取件名单必须报红（此处从登记侧正面核）
        doc, _surge = self.registry()
        for other in doc['objects']:
            if other.get('id') != 'luno-surge':
                self.assertNotIn('officialPackageResources', other, other.get('id'))

    def test_manifest_still_records_five_raw_hashes(self):
        raw = self.manifest()['raw_sha256']
        self.assertEqual(5, len(raw))
        for rel in ('SKILL.md', 'references/command-reference.md',
                    'references/plugin-authoring.md', 'agents/openai.yaml', 'assets/logo.png'):
            self.assertTrue(self.HEX64.match(raw[rel]), (rel, raw.get(rel)))

    def test_skip_split_follows_fetch_state(self):
        """仓库内跳过／取件后另跑：是否跳过只由「原件在位」决定，理由文案指向取件方法。"""
        flagged = []
        for obj in list(globals().values()):
            if not (isinstance(obj, type) and issubclass(obj, unittest.TestCase)):
                continue
            for attr in list(obj.__dict__.values()):
                why = getattr(attr, '__unittest_skip_why__', None)
                if isinstance(why, str) and '公开仓库不含官方原件' in why:
                    flagged.append((obj.__name__, attr.__name__, why))
        if OFFICIAL_PRESENT:
            self.assertEqual([], flagged, '取件后这些用例必须真跑，不能再 skip')
        else:
            self.assertTrue(flagged, '仓库内应当有依赖官方原件的用例被标记跳过')
            for _owner, _name, why in flagged:
                self.assertIn('取件与部署', why)

    def test_source_md_documents_how_to_fetch(self):
        text = (ROOT / 'skills/luno-surge/references/SOURCE.md').read_text(encoding='utf-8')
        self.assertIn('### 取件与部署', text)
        for needle in ('官方直链', 'Contents/Resources/Skills/surge/', 'raw_sha256',
                       '/var/minis/skills/luno-surge/', '不随公开仓库分发',
                       '没有部署授权就不下载', '固定的包 sha256',
                       'tools/deploy_skill.py'):
            self.assertIn(needle, text)
        # 只装 3 份参考原件；入口与来源登记都不再声称原件随包保留
        self.assertNotIn('只装这四份原件', text)
        for rel in ('skills/luno-surge/SKILL.md', 'skills/luno-surge/references/SOURCE.md',
                    'skills/luno-surge/references/command-reference.md'):
            body = (ROOT / rel).read_text(encoding='utf-8')
            self.assertNotIn('随包按原字节保留', body, rel)


if __name__ == '__main__':
    unittest.main()

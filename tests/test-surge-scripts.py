#!/usr/bin/env python3
"""luno-surge 脚本离线回归：只连 127.0.0.1 夹具、用哑凭据，按 `python3 脚本 参数` 的入口边界执行
scripts/*。多数用例在本进程内执行入口（见 run_entry），每个入口脚本至少保留一个真实子进程用例。

覆盖：输出脱敏（_privacy 语料＋各入口全部输出路径）、3xx 不外泄 X-Key、出网门禁、安全分节
写入（revision、POST 后不重投、备份目录、TLS、门禁先于副作用）、
专用打包器（按 manifest 全部 build 累积拒绝完整官方文件）、安装与验收档。真包与登记等包态判据在
test-surge-package.py。
"""
import contextlib
import errno
import hashlib
import importlib.util
import io
import json
import os
import runpy
import shutil
import signal
import socketserver
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import traceback
import types
import unittest
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/luno-surge'
SCRIPTS = SKILL / 'scripts'
SURGE_IOS = SCRIPTS / 'surge_ios.py'
POLICY_DESCRIPTOR = SCRIPTS / 'test_policy_descriptor.py'
SURGE_CLI = SCRIPTS / 'surge_cli.py'
PACKER = SCRIPTS / 'package_release.py'
API_KEY = 'test'                      # 哑值


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRIVACY = load_module('surge_privacy_under_test', SCRIPTS / '_privacy.py')
R = PRIVACY.REDACTED
B, T = PRIVACY.redact_boundary, PRIVACY.redact_text

def offline_env(base=None, api_key=API_KEY):
    """哑凭据＋本地 base；忽略调用方 Surge 参数和代理（含 macOS 系统代理）。"""
    env = {k: v for k, v in os.environ.items()
           if k.lower() not in ('http_proxy', 'https_proxy', 'all_proxy')
           and not k.startswith('SURGE_')}
    env['no_proxy'] = '*'
    env['SURGE_API_KEY'] = api_key
    if base is not None:
        env['SURGE_HTTP_API_BASE'] = base
    return env


def run_entry(script, args, env, stdin=b'', text=True, process=False):
    """等价于 `python3 script args`（给定环境与 stdin），返回 returncode／stdout／stderr。

    默认在本进程内执行（iSH 上每起一个解释器都很贵）：替换 argv、环境、标准流（含 .buffer）、
    sys.path[0] 与 SIGPIPE 处置，结束后清掉脚本目录的同级模块（下次重新导入，导入期读环境仍真实）；
    SystemExit 与未捕获异常按解释器口径折算退出码。process=True 起真实子进程。
    """
    data = stdin.encode('utf-8') if isinstance(stdin, str) else stdin
    if process:
        done = subprocess.run([sys.executable, str(script), *map(str, args)], env=env, input=data,
                              capture_output=True, timeout=90)
        code, out, err = done.returncode, done.stdout, done.stderr
    else:
        code, out, err = _run_in_process(str(script), [str(a) for a in args], env, data)
    if text:
        out, err = out.decode('utf-8'), err.decode('utf-8')
    return types.SimpleNamespace(returncode=code, stdout=out, stderr=err)


def _run_in_process(script, args, env, data):
    home = os.path.dirname(os.path.realpath(script))      # 解释器按解析后的脚本目录设 sys.path[0]
    out, err = io.BytesIO(), io.BytesIO()
    streams = (io.TextIOWrapper(io.BytesIO(data), encoding='utf-8'),
               io.TextIOWrapper(out, encoding='utf-8', write_through=True),
               io.TextIOWrapper(err, encoding='utf-8', errors='backslashreplace', write_through=True))
    saved = sys.argv, sys.path[:], sys.stdin, sys.stdout, sys.stderr, signal.getsignal(signal.SIGPIPE)
    before = set(sys.modules)
    sys.argv, sys.path[:0] = [script, *args], [home]
    sys.stdin, sys.stdout, sys.stderr = streams
    try:
        with mock.patch.dict(os.environ, env, clear=True):
            runpy.run_path(script, run_name='__main__')
        code = 0
    except SystemExit as stop:
        code = stop.code
        if code is None:
            code = 0
        elif not isinstance(code, int):
            print(code, file=sys.stderr)
            code = 1
    except Exception:
        traceback.print_exc()
        code = 1
    finally:
        sys.argv, sys.path[:], sys.stdin, sys.stdout, sys.stderr = saved[:5]
        signal.signal(signal.SIGPIPE, saved[5])
        for name in set(sys.modules) - before:
            path = getattr(sys.modules[name], '__file__', None)
            if path and os.path.dirname(os.path.realpath(path)) == home:
                del sys.modules[name]
    return code, out.getvalue(), err.getvalue()


def run_script(script, args, base=None, stdin=b'', process=False):
    return run_entry(script, args, offline_env(base), stdin, process=process)


def run_cli(args, remote=None, stdin=b'', process=False):
    if remote is not None:
        args = [*args, '--remote', remote]
    return run_entry(SURGE_CLI, args, offline_env(), stdin, process=process)


def serve(server):
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01},
                              daemon=True)
    thread.start()

    def close():
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return close


class LocalFixture:
    """本地 HTTP 夹具：记录请求（方法/路径/头），按 responder 应答。"""

    def __init__(self, responder):
        self.requests = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_GET(self):
                length = int(self.headers.get('Content-Length') or 0)
                if length:
                    self.rfile.read(length)
                fixture.requests.append({'method': self.command, 'path': self.path,
                                         'headers': {k.lower(): v for k, v in self.headers.items()}})
                status, headers, body = responder()
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_POST = do_GET

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.close = serve(self._server)

    @property
    def base(self):
        return 'http://127.0.0.1:%d' % self._server.server_address[1]

    def keys(self):
        return [q['headers'].get('x-key') for q in self.requests]


class LocalController:
    """本地 Controller 协议夹具：收密码行 → 欢迎帧 → 收命令行 → 一帧 JSON 响应。"""

    def __init__(self, response):
        self.passwords, self.commands = [], []
        fixture = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                fixture.passwords.append(self.rfile.readline().rstrip(b'\r\n').decode())
                self.wfile.write(b'{"result": "Welcome to Surge CLI"}\r\n')
                fixture.commands.append(self.rfile.readline().rstrip(b'\r\n').decode())
                self.wfile.write(json.dumps(response).encode() + b'\r\n')

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._server = Server(('127.0.0.1', 0), Handler)
        self.close = serve(self._server)

    @property
    def remote(self):
        return '127.0.0.1:%d' % self._server.server_address[1]


# ── _privacy 语料 ────────────────────────────────────────────────────────────
# (入口, 输入, 期望)：输入含 SYNTH 标记，输出不得残留（不分大小写）且同入口幂等；合法 JSON
# 输入的输出须仍可解析。期望为 str 时逐字节相等，为 tuple 时逐项须保留。
LITERAL_NL = (r'[Tailscale ts1]\nauth-key=SYNTH-AUTH-1\nhostname = h',
              r'[Tailscale ts1]\npassword=SYNTH-PASS-1\nhostname = h',
              r'[Tailscale ts1]\npassword="SYNTH-PASS-2,SYNTH-TAIL-2"\nhostname = h',
              r'[Tailscale ts1]\npassword:["SYNTH-PASS-3","SYNTH-TAIL-3"]\nhostname = h')
JSON_CONTAINERS = (     # 文本路径须保持容器规范形，且仍为合法 JSON
    ('{"tokens": ["SYNTH-R2-1A", "SYNTH-R2-1B"]}', '{"tokens": ["<redacted>"]}'),
    ('{"tokens": {"a": "SYNTH-R2-2A"}}', '{"tokens": ["<redacted>"]}'),
    ('{"a": {"tokens": ["SYNTH-R2-3A"]}}', '{"a": {"tokens": ["<redacted>"]}}'),
    ('{"tokens": ["SYNTH-R2-4A"], "x": "keep"}', '{"tokens": ["<redacted>"], "x": "keep"}'),
    ('{"tokens": ["SYNTH-R2-5A"], "password": "SYNTH-R2-5B"}',
     '{"tokens": ["<redacted>"], "password": "<redacted>"}'),
    ('{\n  "tokens": ["SYNTH-R2-6A"],\n  "policy": "Proxy"\n}',
     '{\n  "tokens": ["<redacted>"],\n  "policy": "Proxy"\n}'),
    ('[{"token": "SYNTH-R2-7A"}, {"password": "SYNTH-R2-7B"}]',
     '[{"token": "<redacted>"}, {"password": "<redacted>"}]'))
SCRUB = (
    # 代理行：位置凭据不按字段外形放行、命名凭据、引号含逗号、Unicode 名与 diff 行首
    (T, '[Proxy]\nPROXY-A = https, 127.0.0.1, 443, synthuser, SYNTH-PASS-A\n'
        'N2 = snell, 127.0.0.1, 8388, SYNTH-PSK-B, version=4\nGroupA = select, A, B\nFINAL,DIRECT\n',
     ('version=4', 'GroupA = select, A, B', 'FINAL,DIRECT')),
    *[(T, 'P = https, example.com, 443, synthuser, ' + value, ('P = https, example.com, 443,',))
      for value in ('SYNTHdGVzdA==', 'a=SYNTHb', 'sni=SYNTH-PASS-1', 'version=SYNTH-PASS-2',
                    '"SNI=SYNTH-PASS-3"')],
    (T, 'P = https, example.com, 443, headers=Cookie:session=SYNTH-COOKIE-1', ()),
    (T, 'P = vmess, example.com, 443, ws-headers=Cookie:session=SYNTH-COOKIE-2, '
        'username=SYNTH-UUID-1', ()),
    (T, 'P = ss, 1.2.3.4, 8388, encrypt-method=aes-256-gcm, password=SYNTH-SS-1', ()),
    (T, 'P = tuic-v5, 1.2.3.4, 443, uuid=SYNTH-UUID-1, password=SYNTH-T5-1', ()),
    (T, 'P = h2-connect, 1.2.3.4, 443, username=synthuser2, password=SYNTH-H2-1', ()),
    (T, 'P = masque, 1.2.3.4, 443, username=synthuser3, password=SYNTH-MQ-1', ()),
    (T, '[Tailscale ts1]\nauth-key = SYNTH-AUTH-1\nhostname = surge', ()),
    (T, '[WireGuard wg1]\nprivate-key = SYNTH-WG-1\nself-ip = 10.0.0.2', ()),
    *[(T, 'P = https, h, 443, synthuser, ' + value, ('https, h, 443,',))
      for value in ('"SYNTH-PASS-1,SYNTH-TAIL-A"', '"SYNTH-PASS-2\nSYNTH-TAIL-B"',
                    r'"SYNTH-PASS-3\nSYNTH-TAIL-C"', 'password="SYNTH-PASS-4,SYNTH-TAIL-D',
                    "'SYNTH-PASS-5,SYNTH-TAIL-E'")],
    *[(T, line, (r'\nhostname = h',)) for line in LITERAL_NL],
    (T, '香港节点 = https, node.example.com, 443, user, SYNTH-UNI-1',
     ('香港节点 = https, node.example.com, 443,',)),
    (T, '+东京节点 = socks5, 1.2.3.4, 1080, user, SYNTH-UNI-2', ('+东京节点 = socks5',)),
    (T, '-东京节点 = socks5, 1.2.3.4, 1080, user, SYNTH-UNI-2', ('-东京节点 = socks5',)),
    *[(B, 'P = %s, h.example, 443, u, SYNTH-AT-1\n' % p, ('%s, h.example, 443' % p,))
      for p in ('anytls', 'h2-connect', 'masque', 'tuic-v5', 'socks5-udp')],
    (B, '+P = anytls, h.example, 443, SYNTH-AT-2\n', ('h.example',)),
    (B, 'T2 = https-tls, h.example, 443, u, SYNTH-UP-2\n', 'T2 = https-tls, h.example, 443, <redacted>\n'),
    (B, 'T3 = socks5-tls, h.example, 1080, u, SYNTH-UP-3\n',
     'T3 = socks5-tls, h.example, 1080, <redacted>, <redacted>\n'),
    (B, 'PROXY-A = https, h.example, 443, user-a, SYNTH-PC-6A\n',
     'PROXY-A = https, h.example, 443, <redacted>, <redacted>\n'),
    (B, '[General]\nloglevel = notify\n[Proxy]\nPROXY-A = https, h.example, 443, user-a, SYNTH-PC-1\n'
        'GroupA = select, A, B\nFINAL,DIRECT\n[Rule]\nDOMAIN-SUFFIX,example.org,DIRECT\n',
     ('PROXY-A = https, h.example, 443', 'GroupA = select, A, B',
      'DOMAIN-SUFFIX,example.org,DIRECT', 'loglevel = notify')),
    # 键值：驼峰／复数／序号、引号尾段、输入自带标记、同行多键、容器
    (T, '{"proxyPassword": "SYNTH-C1", "tokens": ["SYNTH-C2"]}', ()),
    (T, 'policy-path = https://example.com/sub?token=SYNTH-F1', ()),
    (B, 'Error: password=SYNTH-G4 failed', ()),
    (B, '{ "password":"SYNTH-G5" }', ()),
    (B, '{\n  "password": "SYNTH-G2",\n  "policy": "Proxy"\n}', ('"policy": "Proxy"',)),
    (B, '{"token":[["SYNTH-G1"]]}', ()),
    (B, '{"token": [\n  ["SYNTH-NEST-2"]\n]}', ()),
    (B, '响应正文：{"token":[["SYNTH-NEST-3"]]} 结束', ('响应正文：',)),
    *[(B, s, ('password',)) for s in ('password="SYNTH-QT-1A,SYNTH-QT-1B\n',
                                      'password=SYNTH-QT-2A,"SYNTH-QT-2B,SYNTH-QT-2C"\n',
                                      'note: a, password="SYNTH-QT-3A,SYNTH-QT-3B"\n')],
    (B, 'password="SYNTH-QT-4A,SYNTH-QT-4B" other=1\n', ('other=1',)),
    (B, 'password="<redacted>,SYNTH-RM-1A\n', 'password=<redacted>\n'),
    (B, "password='<redacted>,SYNTH-RM-2A\n", 'password=<redacted>\n'),
    (B, 'password = "SYNTH-QV-5A"\n', 'password=<redacted>\n'),
    (B, 'token = SYNTH-PC-7A, user = SYNTH-PC-7B\n', 'token=<redacted>, user=<redacted>\n'),
    (B, 'a = 1\ntoken = SYNTH-PC-9A\nb = 2\n', ()),
    (B, 'token = [SYNTH-PC-2A, SYNTH-PC-2B]\n', 'token=<redacted>\n'),
    (B, 'tokens = ["SYNTH-PC-3A", "SYNTH-PC-3B"]\n', 'tokens=<redacted>\n'),
    (B, '"tokens": ["SYNTH-WS-4A"]', '"tokens": ["<redacted>"]'),
    *[(B, s, ()) for s in ('token: [ [ "SYNTH-WS-1A" ] ]\n',
                           'password: ["SYNTH-WS-2A", ["SYNTH-WS-2B"]]\n',
                           'token = [[ "SYNTH-WS-3A" ]]\n', 'token: [[ SYNTH-WS-5A ]]\n')],
    (B, 'token = [ [ "SYNTH-XL-2A" ] ]\n', ('token',)),       # 同行闭合：不整份抹
    (B, 'token1 = { SYNTH-TK-1A }, token2: [[ SYNTH-TK-1B ]]\n', 'token1=<redacted>\n'),
    (B, 'psk2 = SYNTH-TK-2A, token2: [[ SYNTH-TK-2B ]]\n', 'psk2=<redacted>\n'),
    (B, 'token1 = { SYNTH-TK-3A }, psk2 = { SYNTH-TK-3B }\n', ()),
    (B, 'token1 = { "SYNTH-QV-1A" }, token2: [[ "SYNTH-QV-1B" ]]\n', ()),
    (B, "token1 = { 'SYNTH-QV-2A' }, psk2 = [ 'SYNTH-QV-2B' ]\n", ()),
    # 容器豁免只对合法 JSON 文档成立：非 JSON 文本里的携密引号尾段一律抹到行尾
    (B, 'token=["x]", "SYNTH-N1-1A"', 'token=<redacted>'),
    (B, 'token={"x": "}", "SYNTH-N1-2A"', 'token=<redacted>'),
    (B, 'token=[ "a" ], "SYNTH-N1-3A"', 'token=<redacted>'),
    (B, '"token":["x"], "SYNTH-N1-4A"', '"token":<redacted>'),
    (B, 'token=["x"], psk="SYNTH-N1-5A"', 'token=<redacted>'),
    (B, 'a = 1\ntoken=["x"] = "SYNTH-N1-6A"', 'a = 1\ntoken=<redacted>'),
    # 跨物理行容器：整份 fail-closed
    (B, 'a = 1\ntoken = [ [\nSYNTH-XL-1A\n] ]\nb = 2\n', R),
    (B, 'token = [ [\n"SYNTH-QV-3A"\n] ]\n', R),
    (B, 'token = "[ [\nSYNTH-QV-4A\n] ]\n', R),
    (B, 'psk=A, token = [ [\nSYNTH-X-1A\n] ]\ntoken=["x"], "SYNTH-X-1B"\nloglevel = notify\n', R),
    # 认证、Cookie、Keystore
    (B, r'[Tailscale t]\nauth=SYNTH-NL-1A\nhostname = h', ()),
    (B, r'[S]\nauth="SYNTH-NL-2A,SYNTH-NL-2B"\nhost = h', ()),
    (B, r'[S]\nauth=Bearer SYNTH-NL-3A\nhost = h', ()),
    (B, 'auth=SYNTH-NL-4A\n', ('auth=',)),
    *[(B, s, ()) for s in ('Cookie: session=SYNTH-CK-1A\n',
                           'set-cookie: session=SYNTH-CK-2A; Path=/\n',
                           'headers = Cookie: a=SYNTH-CK-3A, b=SYNTH-CK-3B\n',
                           json.dumps({'note': 'Cookie: a=SYNTH-CK-4A'}),
                           json.dumps({'cookie': 'a=SYNTH-CK-5A'}))],
    (B, 'Cookie: a=SYNTH-CK-6A; Path=/\n', ('Cookie',)),
    (B, '[Keystore]\nMyKey = base64=SYNTH-KS-1BLOB\n', ('[Keystore]', 'MyKey')),
    (B, '[Keystore]\nMY-KEY = SYNTH-KS-2BLOB\n', ('MY-KEY',)),
    (B, '[Keystore]\nkey-material: base64:SYNTH-KS-3BLOB\n', ('key-material',)),
    # 与键名无关的形态：userinfo、预签名参数、JWT、PEM、长串、厂商前缀
    *[(B, s, ('h.example',)) for s in ('url = https://synthuser:SYNTH-UI-1A@h.example/p\n',
                                       json.dumps({'url': 'https://u:SYNTH-UI-2A@h.example'}),
                                       'url = socks5://u:SYNTH-UI-3A@h.example:1080\n',
                                       'url = https://SYNTH-UI-4A@h.example\n')],
    *[(B, s, ()) for s in (
        'url = https://b.example/o?X-Amz-Signature=SYNTH-SG-1A&X-Amz-Expires=300\n',
        'https://b.example/o?X-Goog-Signature=SYNTH-SG-2A\n',
        'https://b.example/o?signature=SYNTH-SG-3A&x=1\n', 'Signature=SYNTH-SG-4A\n',
        'https://b.example/o?AWSAccessKeyId=SYNTH-SG-5A&Signature=SYNTH-SG-5B\n',
        'opaque = eyJhbGciOiJIUzI1NiJ9.SYNTH-UN-1A.SYNTH-UN-1B\n',
        'note = -----BEGIN PRIVATE KEY-----\nSYNTH-UN-2A\n-----END PRIVATE KEY-----\n',
        'opaque = A1b2C3d4SYNTH-UN-3AE5f6G7h8I9j0K1l2M3n4O5p6\n',
        'opaque = AIzaSYNTH-UN-4ASYMMETRICMARKER0123456\n')],
    # 合法 JSON 文档：文本路径保形，边界入口结构化
    *[(T, fixture, expected) for fixture, expected in JSON_CONTAINERS],
    *[(B, fixture, ()) for fixture, _ in JSON_CONTAINERS],
    (B, '{"token": "SYNTH-PC-4A", "note": "keep"}', '{"token": "<redacted>", "note": "keep"}'),
    (B, '{\n  "token": "SYNTH-PC-5A",\n  "n": 1\n}', '{\n  "token": "<redacted>",\n  "n": 1\n}'),
    (B, '{"token": "SYNTH-PC-10A", "n": [1, 2]}', ()),
    *[(T, s, ()) for s in ('{\n  "tokens": [\n    "SYNTH-JD-1A"\n  ]\n}',
                           '{"token": [["SYNTH-JD-2A"]]}', '{"tokens": [["SYNTH-JD-3A"]], "n": 1}')],
)
UNCHANGED = (
    *[(fn, s) for fn in (T, B) for s in ('{"outbound": "proxy", "enabled": true}',
                                         '{"user-agent": "Surge/5.0"}', 'basic configuration failed')],
    (B, 'local-port = 6171'), (B, '{\n  "policy": "Proxy",\n  "outbound": "proxy"\n}'),
    (T, '香港组 = select, A, B'), (T, 'Proxy = select, A, B'), (T, 'FINAL,DIRECT'),
    (B, 'GroupA = select, A, B\nFINAL,DIRECT\n'), (B, 'dns-server = system, ns1.example, ns2.example\n'),
    (B, 'a = 1, b = 2\n'), (B, 'url = https://h.example/sub?page=2\n'),
    (B, 'contact = ops@h.example\n'), (B, 'opaque = SYNTH-UN-5A\n'), (B, 'note = ok\n'),
    (B, 'title = build 42\n'),
    # 规范输出形是不动点
    (B, 'password=<redacted>\n'), (B, 'token=<redacted>\n'), (B, '"tokens": ["<redacted>"]'),
    (B, R), (B, 'token=' + R),
)
SENSITIVE_KEYS = ('POSTGRES_PASSWORD', 'DB_PASSWORD', 'MY_TOKEN', 'SECRET_KEY', 'ADMIN_TOKEN',
                  'AWS_SECRET_ACCESS_KEY', 'REDIS_PASSWORD', 'github_token', 'MYSQL_ROOT_PASSWORD',
                  'aws_secret_access_key')
PLAIN_KEYS = ('PATH', 'HOSTNAME', 'PORT', 'A_B_C', 'MONKEY', 'PUBLIC_KEY', 'USER_AGENT',
              'NODE_ENV', 'LOG_LEVEL', 'HOST', 'POLICY')


def json_document(text):
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


class PrivacyTest(unittest.TestCase):

    def test_redaction_corpus(self):
        for fn, sample in UNCHANGED:               # 投影形态必须逐字节不变
            with self.subTest(fn=fn.__name__, sample=sample):
                self.assertEqual(sample, fn(sample))
        for fn, sample, expect in SCRUB:
            with self.subTest(fn=fn.__name__, sample=sample):
                self.assertIn('SYNTH', sample.upper())
                out = fn(sample)
                self.assertNotIn('SYNTH', out.upper(), out)
                if isinstance(expect, str):
                    self.assertEqual(expect, out)
                for item in () if isinstance(expect, str) else expect:
                    self.assertIn(item, out)
                self.assertEqual(out, fn(out))
                if json_document(sample):
                    self.assertTrue(json_document(out), out)

    def test_key_name_matrix(self):
        for key in SENSITIVE_KEYS + PLAIN_KEYS:
            for fn, sample in ((B, key + '=SYNTH-K\n'), (B, '{"%s": "SYNTH-K"}' % key),
                               (T, key + ': SYNTH-K\n')):
                with self.subTest(key=key, sample=sample):
                    if key in SENSITIVE_KEYS:
                        self.assertNotIn('SYNTH', fn(sample))
                    else:
                        self.assertEqual(sample, fn(sample))
            if key in SENSITIVE_KEYS:
                self.assertEqual(R, PRIVACY.redact_obj({key: 'SYNTH-K'})[key])

    def test_cross_line_container_matrix(self):
        """同行前置键不得挡住跨物理行容器的整份 fail-closed。"""
        for prefix in ('', 'psk=A, ', 'a = 1, psk = A, '):
            for opener, closer in (('[ [', '] ]'), ('{ {', '} }'), ('[ {', '] }')):
                for quote in ('', '"', "'"):
                    sample = '%stoken = %s%s\nSYNTH-N2\n%s%s\n' % (prefix, quote, opener, closer, quote)
                    with self.subTest(sample=sample):
                        self.assertEqual(R, B(sample))
        control = B('psk=A, token = [SYNTH-N2-2A, SYNTH-N2-2B]\n')
        self.assertNotIn('SYNTH', control)
        self.assertNotEqual(R, control)

    def test_structured_paths(self):
        raw = {'policy': 'Proxy', 'a': {'credential': {'inner': 'SYNTH-N1'}},
               'list': [{'proxyPassword': 'SYNTH-N2'}, 'keep'], 'tokens': ['SYNTH-N3']}
        obj = PRIVACY.redact_obj(raw)
        self.assertEqual((R, R, 'Proxy', 'keep'),
                         (obj['a']['credential'], obj['tokens'], obj['policy'], obj['list'][1]))
        for value in (raw, {'Authorization': 'Bearer SYNTH-A1', 'proxyAuth': 'SYNTH-A2',
                            'authz': 'SYNTH-A3', 'nested': [{'auth': 'SYNTH-A4'}]},
                      {'profile': '香港节点 = https, h, 443, u, SYNTH-J1'},
                      {'nested': {'profile': '香港节点 = socks5, 1.2.3.4, 1080, u, SYNTH-J3'}}):
            out = PRIVACY.dumps_redacted(value)
            self.assertNotIn('SYNTH', out)
            json.loads(out)
        profile = '香港节点 = https, h, 443, u, SYNTH-LAY-1'
        for shape in ({'profile': profile}, {'nested': {'profile': profile}},
                      {'profiles': [profile]}, {'profile': profile, 'keep': 'OK'}):
            for layout in ({'separators': (',', ':')}, {}, {'indent': 2}):
                out = B(json.dumps(shape, ensure_ascii=False, **layout))
                self.assertNotIn('SYNTH', out)
                self.assertEqual(shape.get('keep'), json.loads(out).get('keep'))
        top = json.dumps('NODE = snell, h, 443, SYNTH-TOP-1')
        self.assertEqual('NODE = snell, h, 443, <redacted>', json.loads(B(top)))
        outer = json.loads(B(json.dumps({'detail': top, 'keep': 'OK'}, separators=(',', ':'))))
        self.assertEqual(('OK', 'NODE = snell, h, 443, <redacted>'),
                         (outer['keep'], json.loads(outer['detail'])))
        serialized = B('{"profile": "香港节点 = https, node.example.com, 443, user, SYNTH-UNI-3"}')
        self.assertNotIn('SYNTH', serialized)
        self.assertTrue(json.loads(serialized)['profile'].startswith('香港节点 = https'))
        inner = json.dumps({'detail': json.dumps({'token': 'SYNTH-E1', 'tokens': ['SYNTH-E2'],
                                                  'policy': 'Proxy'})})
        self.assertEqual({'token': R, 'tokens': [R], 'policy': 'Proxy'},
                         json.loads(json.loads(T(inner))['detail']))
        for line in LITERAL_NL:                  # 两层 JSON 包装后解回来与文本路径一致
            out = B(json.dumps({'data': B(json.dumps({'data': line}))}))
            self.assertNotIn('SYNTH', out)
            self.assertEqual(T(line), json.loads(json.loads(out)['data'])['data'])


    def test_api_base_problem_requires_explicit_remote_opt_in(self):
        """普通 HTTP 与描述符共用的地址门禁；IPv6/远端正控不由分节专用门禁代替。"""
        with mock.patch.dict(os.environ, {'SURGE_ALLOW_REMOTE': ''}):
            self.assertIsNotNone(PRIVACY.api_base_problem('http://192.0.2.10:6171'))
            self.assertIsNone(PRIVACY.api_base_problem('http://[::1]:6171'))
        with mock.patch.dict(os.environ, {'SURGE_ALLOW_REMOTE': '1'}):
            self.assertIsNone(PRIVACY.api_base_problem('http://192.0.2.10:6171'))
            self.assertIsNotNone(PRIVACY.api_base_problem('http://u:p@192.0.2.10:6171'))


# ── HTTP 回退与描述符探测 ─────────────────────────────────────────────────────
PROBE = 'PROBE-9c4e = http, 127.0.0.1, 1080\n'


def json_reply(body):
    return lambda: (200, {'Content-Type': 'application/json'}, body)


class HttpEntryTest(unittest.TestCase):

    def fixture(self, responder):
        fixture = LocalFixture(responder)
        self.addCleanup(fixture.close)
        return fixture

    def test_redirect_is_not_followed(self):
        """3xx 不跟随：X-Key 不得被转发到重定向目标。"""
        for script, args, expect in (
                (SURGE_IOS, ['outbound'], 'HTTP 302'),
                (POLICY_DESCRIPTOR, ['--descriptor-file', '-'], '"http_error": 302')):
            with self.subTest(script=script.name):
                target = self.fixture(json_reply(b'{"result": {"status": 200}}'))
                sink = self.fixture(lambda: (302, {'Location': target.base + '/v1/leaked'}, b''))
                if script == POLICY_DESCRIPTOR:
                    args = ['--api-base', sink.base] + args
                r = run_script(script, args, base=sink.base, stdin=PROBE, process=True)  # 进程边界
                self.assertNotEqual(0, r.returncode)
                self.assertIn(expect, r.stdout + r.stderr)
                self.assertEqual([API_KEY], sink.keys())
                self.assertEqual([], target.requests)

    def test_success_output_is_redacted(self):
        secret = self.fixture(json_reply(json.dumps(
            {'password': 'SYNTH-PW', 'x-key': 'SYNTH-XKEY', 'policy': 'Proxy'}).encode()))
        r = run_script(SURGE_IOS, ['policies'], base=secret.base)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertNotIn('SYNTH', r.stdout + r.stderr)
        self.assertIn('<redacted>', r.stdout)
        self.assertIn('Proxy', r.stdout)
        plain = self.fixture(json_reply(b'{"outbound": "proxy", "enabled": true}'))
        r = run_script(SURGE_IOS, ['outbound'], base=plain.base)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn('"outbound": "proxy"', r.stdout)
        self.assertIn('"enabled": true', r.stdout)
        probe = self.fixture(json_reply(b'{"result": {"status": 200}}'))
        r = run_script(POLICY_DESCRIPTOR, ['--api-base', probe.base], stdin=PROBE)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual([API_KEY], probe.keys())
        self.assertIn('"node": "PROBE-9c4e"', r.stdout)

    def test_descriptor_api_base_gate(self):
        for base, message in (('http://192.0.2.10:6171', 'SURGE_ALLOW_REMOTE'),
                              ('http://user:SYNTH-GATE@127.0.0.1:6171', 'must not embed URL credentials'),
                              ('ftp://127.0.0.1:6171', 'must use http or https')):
            with self.subTest(base=base):
                with mock.patch.object(urllib.request.OpenerDirector, 'open') as request:
                    r = run_script(POLICY_DESCRIPTOR, ['--api-base', base], stdin=PROBE)
                request.assert_not_called()
                self.assertNotEqual(0, r.returncode)
                self.assertIn(message, r.stderr)
                self.assertNotIn('SYNTH', r.stdout + r.stderr)

    def test_argparse_errors_are_redacted(self):
        for script, args in ((SURGE_IOS, ['--raw', 'password=SYNTH-ARG-1']),
                             (SURGE_IOS, ['kill', 'password=SYNTH-ARG-3']),
                             (SURGE_IOS, ['outbound', 'password=SYNTH-ARG-5']),
                             (POLICY_DESCRIPTOR, ['--bogus', 'password=SYNTH-ARG-2']),
                             (POLICY_DESCRIPTOR, ['--timeout', 'password=SYNTH-ARG-4'])):
            with self.subTest(args=args):
                r = run_script(script, args)
                self.assertNotEqual(0, r.returncode)
                self.assertNotIn('SYNTH', r.stdout + r.stderr)


# ── surge_cli（Controller 客户端）───────────────────────────────────────────
class SurgeCliTest(unittest.TestCase):

    def cli(self, payload, args):
        controller = LocalController(payload)
        self.addCleanup(controller.close)
        return run_cli(args, remote=controller.remote), controller

    def test_every_output_path_is_redacted(self):
        cases = (   # (响应, argv, 退出码, 必须保留)
            ({'result': {'password': 'SYNTH-1', 'tokens': ['SYNTH-2'], 'policy': 'Proxy'}},
             ['--raw', 'policy-group', 'list'], 0, ('Proxy',)),
            ({'sections': [{'section': 'DNS', 'lines': [
                {'title': 'Password', 'content': '1.1.1.1\npassword=SYNTH-3'}]}]},
             ['summary'], 0, ('DNS:', '\n\n')),
            ({'error': 'authentication failed: password=SYNTH-4', 'code': 1},
             ['policy-group', 'list'], 1, ('<redacted>',)),
            ({'originalProfile': 'PROXY-A = https, 127.0.0.1, 443, u, SYNTH-5\n',
              'profile': 'PROXY-A = https, 127.0.0.1, 443, synthuser, SYNTH-6\nFINAL,DIRECT\n'},
             ['profile', 'diff'], 0, ('PROXY-A',)),
            ({'clients': [{'ip': '10.0.0.2', 'mac': 'aa:bb', 'password': 'SYNTH-7'}]},
             ['vmnet', 'ra'], 0, ('RA takeover clients (1):', '\n\n')),
            ('NODE = snell, h, 443, SYNTH-8', ['--raw', 'status'], 0, ()),
            ({'result': 'proxy'}, ['mode'], 0, 'proxy\n'),     # 普通输出逐字节不变
        )
        for payload, args, code, keep in cases:
            with self.subTest(args=args):
                r, controller = self.cli(payload, args)
                self.assertEqual(code, r.returncode, r.stderr)
                self.assertNotIn('SYNTH', r.stdout + r.stderr)
                if isinstance(keep, str):
                    self.assertEqual(keep, r.stdout)
                for item in () if isinstance(keep, str) else keep:
                    self.assertIn(item, r.stdout + r.stderr)
                self.assertEqual([API_KEY], controller.passwords)    # 凭据只来自 SURGE_API_KEY
                if args[0] == '--raw':
                    json.loads(r.stdout)

    def test_multiline_credential_in_summary_and_diff(self):
        """先整段脱敏再分行：跨行引号口令不泄漏尾段，diff hunk 计数与正文一致。"""
        r, _ = self.cli({'sections': [{'section': 'Warnings', 'lines': [
            {'title': 'Proxy', 'content': 'P = https, host1, 443, synthuser, "SYNTH-7,\nSYNTH-TAIL"'}]}]},
            ['summary'])
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertNotIn('SYNTH', r.stdout.upper())
        self.assertIn('host1, 443', r.stdout)
        r, _ = self.cli({'originalProfile': 'PROXY-A = https, 127.0.0.1, 443, u, "SYNTH-6,\n'
                                            'SYNTH-TAIL"\nDOMAIN-SUFFIX,example.com,DIRECT\n',
                         'profile': 'PROXY-A = https, 127.0.0.1, 443, synthuser, SYNTH-P\n'
                                    'FINAL,DIRECT\nDOMAIN-SUFFIX,example.org,DIRECT\n'},
                        ['profile', 'diff'])
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertNotIn('SYNTH', r.stdout.upper())
        self.assertIn('example.org', r.stdout)
        lines = r.stdout.splitlines()
        headers = [line for line in lines if line.startswith('@@')]
        self.assertEqual(1, len(headers), r.stdout)
        body = [line[:1] for line in lines if line[:1] in ' +-' and not line.startswith(('+++', '---'))]
        declared = [int(part.split(',')[-1]) for part in headers[0].split()[1:3]]
        self.assertEqual([body.count(' ') + body.count('-'), body.count(' ') + body.count('+')],
                         declared, r.stdout)

    def test_symlinked_entry_point_resolves_shared_module(self):
        """install.sh 以符号链接安装：共享模块须按 realpath 找到（sys.path[0] 不是脚本目录）。"""
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'surge-cli'
            link.symlink_to(SURGE_CLI)
            r = subprocess.run([sys.executable, '-c',
                                "import runpy, sys; sys.argv = [sys.argv[1], '--help'];"
                                " runpy.run_path(sys.argv[0], run_name='__main__')", str(link)],
                               env=offline_env(), cwd=tmp, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn('Surge CLI (Minis Controller Edition)', r.stdout)
        self.assertNotIn('<redacted>', r.stdout)        # help 是字面文本，不经脱敏

    def test_check_output_is_redacted(self):
        """--check：替换 urlopen（不联网），成功 raw 与失败消息都脱敏。"""
        for result, raw, code in (
                ({'valid': False, 'error': {'message': 'rejected: password=SYNTH-CHK-1'}}, False, 1),
                ({'valid': True, 'warnings': [{'tokens': ['SYNTH-CHK-2'], 'line': 7}]}, True, 0)):
            module = load_module('surge_cli_check', SURGE_CLI)
            body = json.dumps(result).encode()
            fake = mock.patch.object(module.urllib.request, 'urlopen',
                                     lambda request, timeout=None: contextlib.closing(io.BytesIO(body)))
            stdout, stderr = io.StringIO(), io.StringIO()
            with fake, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as done:
                    module.validate_profile(str(SKILL / 'SKILL.md'), raw)
            self.assertEqual(code, done.exception.code)
            self.assertNotIn('SYNTH', stdout.getvalue() + stderr.getvalue())
            if raw:
                self.assertTrue(json.loads(stdout.getvalue())['valid'])
            else:
                self.assertIn('Failed:', stderr.getvalue())

    def test_check_requires_a_readable_profile(self):
        r = run_cli(['--check', '/nonexistent/synthetic-profile.conf'], process=True)  # 进程边界
        self.assertEqual((2, ''), (r.returncode, r.stdout))
        self.assertIn('Cannot read profile file', r.stderr)

    def test_section_set_is_blocked_before_connecting(self):
        for args in (['profile', 'section', 'set', 'Rule', 'SYNTH-SET'],
                     ['--raw', 'Profile', 'SECTION', 'Set', 'Rule', 'SYNTH-SET'],
                     ['profile', 'section', 'SET', 'Rule', '-']):
            with self.subTest(args=args):
                controller = LocalController({'result': 'ok'})
                self.addCleanup(controller.close)
                r = run_cli(args, remote=controller.remote, stdin='SYNTH-SET')
                self.assertEqual(2, r.returncode, r.stderr)
                self.assertIn('E_SECTION_SET_REQUIRES_LOCAL_ADAPTER', r.stderr)
                self.assertEqual(([], []), (controller.passwords, controller.commands))
                self.assertNotIn('SYNTH', r.stderr)
        for args in (['profile', 'section', 'list'], ['profile', 'section', 'get', 'Rule']):
            with self.subTest(args=args):
                r, controller = self.cli({'result': 'ok'}, args)
                self.assertEqual(0, r.returncode, r.stderr)
                self.assertTrue(controller.commands[0].lower().startswith('profile "section"'))


# ── 专用打包器 ───────────────────────────────────────────────────────────────
class PackerTest(unittest.TestCase):
    KEYS = ('SKILL.md', 'references/command-reference.md', 'references/plugin-authoring.md',
            'agents/openai.yaml', 'assets/logo.png')

    def isolated(self, tmp):
        """复制打包器进隔离技能目录（SOURCE 由脚本位置推导）。"""
        skill = Path(tmp) / 'skill'
        (skill / 'references').mkdir(parents=True)
        (skill / 'scripts').mkdir()
        script = skill / 'scripts/package_release.py'
        shutil.copy2(str(PACKER), str(script))
        (skill / 'SKILL.md').write_text('---\nname: surge\n---\n\n夹具正文\n')
        (skill / 'references/one.md').write_text('one\n')
        (skill / 'references/two.md').write_text('two\n')
        self.write_manifest(skill)
        return skill, script, load_module('surge_release_under_test', script)

    def payloads(self, tag='raw'):
        # Independent synthetic provenance, not values exported by the packer.
        return {key: ('synthetic %s %s' % (tag, key)).encode() for key in self.KEYS}

    def write_manifest(self, skill, *tags):
        """builds 按 tags 顺序追加（末项为基线）；返回末项的合成原件。"""
        tags = tags or ('raw',)
        manifest = skill / 'references/upstream-manifest.json'
        manifest.write_text(json.dumps({'builds': [{'raw_sha256': {
            key: hashlib.sha256(value).hexdigest() for key, value in self.payloads(tag).items()}}
            for tag in tags]}))
        return manifest, self.payloads(tags[-1])

    def pack(self, script, out, process=False):
        return run_entry(script, [out], offline_env(), process=process)

    def test_collect_filters_and_refuses_unsafe_entries(self):
        with tempfile.TemporaryDirectory(prefix='surge-pack-') as tmp:
            skill, _script, module = self.isolated(tmp)
            excluded = ('secrets.env', 'credentials', 'logs/run.log', 'certs/key.pem', 'notes.log',
                        '.ssh/known_hosts', '__pycache__/x.pyc')
            for rel in excluded:
                (skill / rel).parent.mkdir(parents=True, exist_ok=True)
                (skill / rel).write_text('excluded\n')
            self.assertEqual(['SKILL.md', 'references/one.md', 'references/two.md',
                              'references/upstream-manifest.json', 'scripts/package_release.py'], [rel for rel, _ in module.collect(skill)])
            for make, message in (
                    (lambda p: p.symlink_to('references/one.md'), 'Symlinks are not allowed in release packages: bad'),
                    (lambda p: os.mkfifo(str(p)), 'Non-regular entries are not allowed in release packages: bad')):
                make(skill / 'bad')
                with self.assertRaises(module.ReleaseError) as caught:
                    module.collect(skill)
                self.assertEqual(message, str(caught.exception))
                (skill / 'bad').unlink()
            with self.assertRaises(module.ReleaseError) as caught:
                module.collect(Path(tmp) / 'missing')
            self.assertIn('Traversal error', str(caught.exception))
            (skill / 'references/leak.md').write_text('token ghp_' + 'C' * 24 + '\n')
            with self.assertRaises(module.SecretError) as caught:
                module.build(module.collect(skill))
            self.assertEqual('Potential secret found in references/leak.md', str(caught.exception))

    def test_build_archives_the_scanned_bytes(self):
        """每个文件只读一次：首读后改盘为合成秘密，归档的仍是已扫描的首读 bytes。"""
        with tempfile.TemporaryDirectory(prefix='surge-readonce-') as tmp:
            skill, _script, module = self.isolated(tmp)
            entries = module.collect(skill)
            target, real, reads = skill / 'references/two.md', Path.read_bytes, []

            def hook(path, *args, **kwargs):
                data = real(path)
                if str(path) == str(target):
                    reads.append(1)
                    target.write_text('ghp_' + 'C' * 24 + '\n')
                return data
            with mock.patch.object(Path, 'read_bytes', hook):
                blob = module.build(entries)
            self.assertEqual(1, len(reads))
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                self.assertEqual(b'two\n', archive.read('references/two.md'))

    def test_package_modes_follow_source_bits_not_root_access(self):
        """权限保真：以 root 能力模拟 os.access(X_OK) 恒真，模式仍须由源文件 stat 执行位决定。

        旧实现按 os.access 判定，在 iSH/root 上会把 0644 文档打成 0755（本用例转红）；
        新实现读 st_mode 执行位，doc 保持 0644、script 保持 0755。
        """
        with tempfile.TemporaryDirectory(prefix='surge-mode-') as tmp:
            skill, _script, module = self.isolated(tmp)
            os.chmod(str(skill / 'references/one.md'), 0o644)
            os.chmod(str(skill / 'references/two.md'), 0o755)
            entries = module.collect(skill)
            with mock.patch.object(os, 'access', lambda *a, **k: True):
                blob = module.build(entries)
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                modes = {i.filename: i.external_attr >> 16 & 0o7777 for i in archive.infolist()}
            self.assertEqual(0o644, modes['references/one.md'])
            self.assertEqual(0o755, modes['references/two.md'])

    def test_cli_output_metadata_and_atomic_replace(self):
        with tempfile.TemporaryDirectory(prefix='surge-cli-') as tmp:
            skill, script, _module = self.isolated(tmp)
            out = Path(tmp) / 'release.zip'
            out.write_bytes(b'OLD-ARTIFACT')
            def deny(self, target):
                raise PermissionError('synthetic-replace-denied')
            with mock.patch.object(Path, 'replace', deny):
                r = self.pack(script, out)
            self.assertNotEqual(0, r.returncode)
            self.assertIn('PermissionError', r.stderr)
            self.assertEqual(b'OLD-ARTIFACT', out.read_bytes())
            self.assertFalse(Path(str(out) + '.tmp').exists())
            r = self.pack(script, out, process=True)        # 进程边界
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertFalse(Path(str(out) + '.tmp').exists())
            expected = sorted(str(p.relative_to(skill)) for p in skill.rglob('*')
                              if p.is_file() and '__pycache__' not in p.parts)
            self.assertEqual([str(out), hashlib.sha256(out.read_bytes()).hexdigest(),
                              'files=%d bytes=%d' % (len(expected), out.stat().st_size)],
                             r.stdout.splitlines())
            with zipfile.ZipFile(out) as archive:
                self.assertEqual(expected, archive.namelist())
                for info in archive.infolist():
                    self.assertEqual((2026, 1, 1, 0, 0, 0), info.date_time)
                    self.assertIn(info.external_attr >> 16 & 0o7777, (0o644, 0o755))
            inside = skill / 'not-allowed.zip'
            r = self.pack(script, inside)
            self.assertEqual((1, 'Output ZIP must be outside the Skill directory\n'), (r.returncode, r.stderr))
            self.assertFalse(inside.exists())

    def test_whole_official_files_and_logo_are_rejected(self):
        for name in ('references/upstream-SKILL.md', 'references/upstream-command-reference.md', 'assets/logo.png'):
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix='surge-no-official-') as tmp:
                skill, script, module = self.isolated(tmp)
                target = skill / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'synthetic-whole-official-file')
                out = Path(tmp) / 'release.zip'
                out.write_bytes(b'EXISTING-ZIP-SENTINEL')
                out.chmod(0o640)
                before = (out.read_bytes(), out.stat().st_mode & 0o777)
                result = self.pack(script, out)
                self.assertEqual((1, '', 'Official resource is not distributable: ' + name + '\n'),
                                 (result.returncode, result.stdout, result.stderr))
                self.assertEqual(before, (out.read_bytes(), out.stat().st_mode & 0o777))
                self.assertFalse(Path(str(out) + '.tmp').exists())
                target.unlink()
                self.assertTrue(module.build(module.collect(skill)))

    def test_known_raw_content_is_denied_at_renamed_and_authored_paths(self):
        keys = ('SKILL.md', 'references/command-reference.md', 'references/plugin-authoring.md',
                'agents/openai.yaml', 'assets/logo.png')
        for key in keys:
            paths = ('references/renamed.md', 'references/plugin-authoring.md') if key == 'references/plugin-authoring.md' else ('references/renamed.md',)
            for name in paths:
                with self.subTest(key=key, name=name), tempfile.TemporaryDirectory(prefix='surge-known-raw-') as tmp:
                    skill, script, module = self.isolated(tmp)
                    _manifest, payloads = self.write_manifest(skill)
                    target = skill / name
                    target.write_bytes(payloads[key])
                    out = Path(tmp) / 'release.zip'
                    out.write_bytes(b'EXISTING-ZIP-SENTINEL')
                    out.chmod(0o640)
                    before = (out.read_bytes(), out.stat().st_mode & 0o777)
                    result = self.pack(script, out)
                    self.assertEqual((1, '', 'Known whole official file is not distributable: ' + name + '\n'),
                                     (result.returncode, result.stdout, result.stderr))
                    self.assertEqual(before, (out.read_bytes(), out.stat().st_mode & 0o777))
                    self.assertFalse(Path(str(out) + '.tmp').exists())
                    target.write_bytes(b'own distinct guide')
                    self.assertTrue(module.build(module.collect(skill)), 'Removing the injection must restore the positive control')

    def test_earlier_build_originals_stay_denied_after_baseline_moves(self):
        """累积名单：基线移到新 build 后，旧 build 的原件改名放入仍被拒；名单去掉旧 build 才放行。"""
        with tempfile.TemporaryDirectory(prefix='surge-cumulative-') as tmp:
            skill, _script, module = self.isolated(tmp)
            self.write_manifest(skill, 'old', 'new')
            (skill / 'references/renamed.md').write_bytes(self.payloads('old')['references/command-reference.md'])
            with self.assertRaises(module.ReleaseError) as caught:
                module.build(module.collect(skill))
            self.assertEqual('Known whole official file is not distributable: references/renamed.md',
                             str(caught.exception))
            self.write_manifest(skill, 'new')
            self.assertTrue(module.build(module.collect(skill)))

    def test_provenance_manifest_fails_closed_and_preserves_existing_zip(self):
        good = {k: hashlib.sha256(('synthetic raw ' + k).encode()).hexdigest() for k in self.KEYS}
        cases = [('absent-file', None), ('invalid-json', '{bad'), ('root-null', 'null'), ('root-list', '[]'),
                 ('missing-builds', '{}'), ('no-builds', '{"builds":[]}'),
                 ('builds-object', '{"builds":{"a":1}}'), ('build-null', '{"builds":[null]}'),
                 ('missing-table', '{"builds":[{}]}'), ('empty-table', '{"builds":[{"raw_sha256":{}}]}'),
                 ('table-string', '{"builds":[{"raw_sha256":"bad"}]}')]
        for key in self.KEYS:                     # 每个 build 都要校验，不只看基线
            for fault in ('missing', 'null', 'bad-char', 'short', 'uppercase'):
                raw = dict(good)
                if fault == 'missing':
                    del raw[key]
                else:
                    raw[key] = {'null': None, 'bad-char': 'z' * 64, 'short': 'a' * 63,
                                'uppercase': 'A' * 64}[fault]
                cases.append((key + ':' + fault, json.dumps({'builds': [{'raw_sha256': raw},
                                                                        {'raw_sha256': good}]})))
        for label, content in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory(prefix='surge-bad-manifest-') as tmp:
                skill, script, module = self.isolated(tmp)
                manifest = skill / 'references/upstream-manifest.json'
                if content is None:
                    manifest.unlink()
                else:
                    manifest.write_text(content)
                out = Path(tmp) / 'release.zip'
                out.write_bytes(b'EXISTING-ZIP-SENTINEL')
                out.chmod(0o640)
                before = (out.read_bytes(), out.stat().st_mode & 0o777)
                result = self.pack(script, out)
                self.assertEqual((1, '', 'Invalid provenance manifest\n'),
                                 (result.returncode, result.stdout, result.stderr))
                self.assertEqual(before, (out.read_bytes(), out.stat().st_mode & 0o777))
                self.assertFalse(Path(str(out) + '.tmp').exists())
                self.write_manifest(skill)
                self.assertTrue(module.build(module.collect(skill)), 'Removing the fault must pass')


# ── 安装与验收档 ─────────────────────────────────────────────────────────────
class InstallTest(unittest.TestCase):
    """scripts/ 复制到临时包目录（真包文档链接由包态测试核对），PATH 只含夹具 bin，
    SURGE_CLI_BIN／SURGE_CLI_LINK 指向隔离落点。"""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.pkg = self.tmp / 'pkg'
        shutil.copytree(str(SCRIPTS), str(self.pkg / 'scripts'))
        self.cli = self.pkg / 'scripts/surge_cli.py'
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        self.other = self.tmp / 'other/surge_cli.py'
        self.other.parent.mkdir()
        shutil.copy2(str(self.cli), str(self.other))
        self.other.chmod(0o755)

    def run_sh(self, script, *args, **env):
        base = {k: v for k, v in os.environ.items() if not k.startswith('SURGE_')}
        base['PATH'] = os.pathsep.join([str(self.bin), os.path.dirname(sys.executable), '/bin', '/usr/bin'])
        base.update(env)
        return subprocess.run(['sh', str(self.pkg / 'scripts' / script), *args], cwd=str(self.tmp),
                              env=base, capture_output=True, text=True, timeout=120)

    def link(self, target=None):
        path = self.bin / 'surge-cli'
        if path.is_symlink() or path.exists():
            path.unlink()
        if target is not None:
            path.symlink_to(str(target))

    def test_installed_tier_reports_each_failure_category(self):
        for target, mode, error in (
                (None, 0o755, 'not found on PATH: surge-cli'),
                (self.tmp / 'gone/surge_cli.py', 0o755, 'missing target (broken link): surge-cli'),
                (self.other, 0o755, 'points elsewhere: surge-cli -> %s (expected %s)' % (self.other, self.cli)),
                (self.cli, 0o644, 'not executable: surge-cli'),
                (self.cli, 0o755, None)):
            with self.subTest(error=error):
                self.cli.chmod(mode)
                self.link(target)
                r = self.run_sh('acceptance.sh', '--installed')
                self.assertIn('PASS  Offline syntax and local links\n', r.stdout)
                if error:
                    self.assertEqual(1, r.returncode)
                    self.assertIn('installed-check: %s\n' % error, r.stderr)
                else:
                    self.assertEqual(0, r.returncode, r.stderr)
                    self.assertIn('PASS  Installed surge-cli resolves to this package\n', r.stdout)

    def test_offline_tier_ignores_the_install_point(self):
        self.link(self.tmp / 'gone/surge_cli.py')
        marker, trap = self.tmp / 'cli-was-run', self.tmp / 'surge-cli-trap'
        trap.write_text('#!/bin/sh\ntouch %s\nexit 9\n' % marker)
        trap.chmod(0o755)

        def tree():
            return {str(p): (p.read_bytes(), p.stat().st_mode) for p in self.pkg.rglob('*') if p.is_file()}
        before = tree()
        for args, env in (((), {}), (('--offline',), {'SURGE_CLI_BIN': str(trap)})):
            r = self.run_sh('acceptance.sh', *args, **env)
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertNotIn('installed-check', r.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(before, tree())

    def test_install_reports_success_only_when_path_resolves_into_package(self):
        opt = self.tmp / 'opt'
        opt.mkdir()
        for target, shadow, error in (
                (opt / 'surge-cli', None, 'installed-check: not found on PATH: surge-cli'),
                (opt / 'surge-cli2', self.other, 'installed-check: points elsewhere: surge-cli -> %s' % self.other),
                (opt, None, 'Install failed: %s does not resolve' % opt)):
            with self.subTest(target=target.name):
                self.link(shadow)
                r = self.run_sh('install.sh', SURGE_CLI_LINK=str(target))
                self.assertEqual(1, r.returncode)
                self.assertNotIn('Installed: ', r.stdout)
                self.assertIn(error, r.stderr)
        self.link()
        target = self.bin / 'surge-cli'
        r = self.run_sh('install.sh', SURGE_CLI_LINK=str(target))
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(str(self.cli), os.path.realpath(str(target)))
        self.assertIn('Installed: %s -> %s\n' % (target, self.cli), r.stdout)


# ── 安全分节写入（surge_ios.py section replace）───────────────────────────────
# 真实子进程入口：stdin 解析 → urllib → 解码 → 原稿/revision 核对 → 备份 → POST → 写后 GET。
SEC_KEY = 'synthetic-key-not-a-credential'
SEC_REVISION = 'r-9f3c1a7d5e2b48c6a0f1d3e5b7c9a2f4'
SEC_ORIGINAL = '# synthetic original\nDOMAIN-SUFFIX,old.invalid,REJECT\nFINAL,DIRECT\n'
SEC_CONTENT = ('# 中文注释、空行与 CRLF\r\nDOMAIN-SUFFIX,example.invalid,REJECT\n\n'
               'URL-REGEX,"^https://example\\.invalid/a,b",REJECT\nFINAL,DIRECT\n')
SEC_PRIVATE = [SEC_CONTENT, SEC_REVISION, SEC_KEY]


def jbytes(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


def section_payload(**overrides):
    payload = {'name': 'Rule', 'revision': SEC_REVISION, 'original': SEC_ORIGINAL, 'content': SEC_CONTENT}
    payload.update(overrides)
    return payload


class SectionServer:
    """`/v1/profiles/section` 合成服务端：真实比较 revision（旧值 409 不落地，落地后 revision 前进）。

    故障开关：post_status、drop_after_post（先落地再断连）、drop_on_get_after_post、
    post_rewrites（落地后被改写）、truncate_post_response、verify_payload、garbage_status_line、
    bump_after_get=n（第 n 次 GET 后并发写者推进 revision）、illegal_chunk='read'|'verify'。
    """

    def __init__(self, content=SEC_ORIGINAL, revision=SEC_REVISION, post_status=200,
                 post_body=b'{"changed":true,"file":"unexpected-key"}', **faults):
        self.content, self.revision = content, revision
        self.post_status, self.post_body = post_status, post_body
        self.faults = faults
        self.calls, self.sent, self.stale_rejections = [], [], []
        self.get_count = 0
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def drop(self, data=b''):
                if data:
                    self.wfile.write(data)
                self.close_connection = True
                self.connection.close()

            def reply(self, status, payload, chunked=False):
                server.sent.append((status, payload))
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                if chunked:              # 非法分块：长度行不是十六进制
                    self.send_header('Transfer-Encoding', 'chunked')
                    self.end_headers()
                    return self.drop(b'ZZZZ-not-hex\r\n' + payload + b'\r\n0\r\n\r\n')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                server.record(self, body)
                status, payload = server.apply_post(body)
                if server.faults.get('drop_after_post'):
                    return self.drop()
                if server.faults.get('garbage_status_line'):
                    return self.drop(b'NOT-HTTP\r\n\r\n')
                if server.faults.get('truncate_post_response'):
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(payload) + 64))
                    self.end_headers()
                    return self.drop(payload[:4])
                self.reply(status, payload)

            def do_GET(self):
                server.record(self, b'')
                server.get_count += 1
                posted = any(c['method'] == 'POST' for c in server.calls)
                if posted and server.faults.get('drop_on_get_after_post'):
                    return self.drop()
                payload = server.faults.get('verify_payload') if posted else None
                if payload is None:
                    payload = jbytes({'content': server.content, 'revision': server.revision,
                                      'undocumented': 'unknown-field-value'})
                self.reply(200, payload, chunked=server.faults.get('illegal_chunk') == ('verify' if posted else 'read'))
                if server.get_count == server.faults.get('bump_after_get'):
                    server.revision += '-concurrent'

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.close = serve(self._server)

    def record(self, handler, body):
        self.calls.append({'method': handler.command, 'path': handler.path, 'body': body,
                           'headers': {k.lower(): v for k, v in handler.headers.items()}})

    def apply_post(self, body):
        try:
            posted = json.loads(body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            posted = None
        if not isinstance(posted, dict):
            return 400, self.post_body
        if self.post_status != 200:
            return self.post_status, self.post_body
        if posted.get('revision') != self.revision:
            self.stale_rejections.append({'sent': posted.get('revision'), 'current': self.revision})
            return 409, b'{"error":"revision changed"}'
        self.content = posted['content']
        self.revision += '-next'
        if self.faults.get('post_rewrites'):
            self.content = self.faults['post_rewrites'](self.content)
        return 200, self.post_body

    @property
    def base(self):
        return 'http://127.0.0.1:%d' % self._server.server_address[1]

    def posts(self):
        return [c for c in self.calls if c['method'] == 'POST']

    def methods(self):
        return [c['method'] for c in self.calls]

    def current(self):
        """直接取服务端当前状态（不经被测客户端）。"""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(self.base + '/v1/profiles/section?name=Rule', timeout=30) as response:
            doc = json.loads(response.read().decode('utf-8'))
        return doc['content'], doc['revision']


class SectionWriteTest(unittest.TestCase):

    def server(self, **kwargs):
        server = SectionServer(**kwargs)
        self.addCleanup(server.close)
        return server

    def backup_dir(self, mode=0o700):
        path = tempfile.mkdtemp(prefix='surge-section-')
        self.addCleanup(shutil.rmtree, path, True)
        os.chmod(path, mode)
        return path

    def run_section(self, payload, base, confirm=True, extra=(), env_extra=None, process=False):
        args = (['--confirm-dangerous'] if confirm else []) + ['section', 'replace', '--input', '-', *extra]
        env = offline_env(base, SEC_KEY)
        env.update(env_extra or {})
        return run_entry(SURGE_IOS, args, env, jbytes(payload) if isinstance(payload, dict) else payload,
                         text=False, process=process)

    def replace(self, server, backups, **overrides):
        return self.run_section(section_payload(backup_dir=backups, **overrides), server.base)

    def assert_stopped(self, done, code, token, private=()):
        """失败只给固定 token：退出码、空 stdout、无 traceback、不回显正文/key/revision。"""
        self.assertEqual(code, done.returncode, done.stderr)
        self.assertIn(token.encode(), done.stderr)
        self.assertEqual(b'', done.stdout)
        self.assertNotIn(b'Traceback', done.stderr)
        for item in private:
            self.assertNotIn(item.encode('utf-8'), done.stdout + done.stderr)

    def backup_record(self, backups):
        (name,) = os.listdir(backups)
        return json.loads(Path(backups, name).read_text(encoding='utf-8'))

    def test_t1_vertical_slice_carries_exact_bytes_and_backup(self):
        server, backups = self.server(), self.backup_dir()
        done = self.run_section(section_payload(backup_dir=backups), server.base, process=True)  # 进程边界
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(b'{"changed":true,"ok":true,"verified":true}\n', done.stdout)
        self.assertEqual(['GET', 'POST', 'GET'], server.methods())
        self.assertEqual(['/v1/profiles/section?name=Rule'] * 2,
                         [c['path'] for c in server.calls if c['method'] == 'GET'])
        post = server.posts()[0]
        self.assertEqual({'name': 'Rule', 'revision': SEC_REVISION, 'content': SEC_CONTENT},
                         json.loads(post['body'].decode('utf-8')))
        self.assertEqual(SEC_KEY, post['headers']['x-key'])
        self.assertEqual(SEC_CONTENT, server.content)
        (name,) = os.listdir(backups)
        record = self.backup_record(backups)
        self.assertEqual((1, SEC_ORIGINAL, SEC_REVISION, SEC_CONTENT),
                         (record['format'], record['original'], record['revision'], record['intended_content']))
        self.assertEqual(0o600, stat.S_IMODE(os.stat(Path(backups, name)).st_mode))
        for item in SEC_PRIVATE + ['Rule', 'example.invalid', 'unknown-field-value', backups]:
            self.assertNotIn(item.encode('utf-8'), done.stdout + done.stderr)

    def test_t2_input_rejections_are_pre_network(self):
        server, backups = self.server(), self.backup_dir()
        good = section_payload(backup_dir=backups)
        cases = {
            'duplicate key': b'{"name":"Rule","revision":"r","original":"A\\n","content":"B\\n",'
                             b'"backup_dir":"/tmp","name":"Rule"}',
            'extra key': jbytes(dict(good, extra='x')),
            'missing key': jbytes({k: v for k, v in good.items() if k != 'original'}),
            'bad utf8': jbytes(good).replace(b'Rule', b'Ru\xffle'),
            'lone surrogate': b'{"name":"Rule","revision":"r","original":"A\\n","content":"B\\ud800\\n",'
                              b'"backup_dir":"/tmp/x"}',
            'nul byte': jbytes(dict(good, content='A\x00B\n')),
            'two docs': jbytes(good) * 2,
            'empty content': jbytes(dict(good, content='')),
            'section header': jbytes(dict(good, content='[Rule]\nX\n')),
            'bracketed name': jbytes(dict(good, name='[Rule]')),
            'shebang name': jbytes(dict(good, name='#!include x')),
            'include line': jbytes(dict(good, content='#!include x.dconf\n')),
            'oversize': jbytes(dict(good, content='A' * (256 * 1024 + 1))),
            'not json': b'not json at all',
        }
        for label, payload in cases.items():
            with self.subTest(label):
                self.assert_stopped(self.run_section(payload, server.base), 2, 'E_INPUT')
        for label, kwargs in (('missing confirm', {'confirm': False}), ('extra argv', {'extra': ('x',)})):
            with self.subTest(label):
                done = self.run_section(good, server.base, **kwargs)
                self.assertEqual(2, done.returncode, done.stderr)
        self.assertEqual(([], []), (server.calls, os.listdir(backups)))
        done = self.replace(server, backups, name='规则')       # Unicode 节名正控
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual('规则', json.loads(server.posts()[0]['body'].decode('utf-8'))['name'])

    def test_t3_mismatch_stops_before_post(self):
        backups = self.backup_dir()
        for kwargs, code, token in (({'revision': 'r-other'}, 3, 'E_REVISION_CHANGED'),
                                    ({'content': SEC_ORIGINAL + 'EXTRA,DOMAIN,x\n'}, 3, 'E_ORIGINAL_CHANGED'),
                                    ({'revision': ''}, 4, 'E_READ_DECODE')):
            with self.subTest(token):
                server = self.server(**kwargs)
                self.assert_stopped(self.replace(server, backups), code, token)
                self.assertEqual([], server.posts())
        self.assertEqual([], os.listdir(backups))

    def test_t3_rejected_or_stale_write_is_not_resent(self):
        backups = self.backup_dir()
        rejected = self.server(post_status=400)
        self.assert_stopped(self.replace(rejected, backups), 4, 'E_REJECTED 400')
        self.assertEqual(1, len(rejected.posts()))
        stale = self.server(bump_after_get=1)    # 首次 GET 后并发写者推进 revision：只有服务端比较能拦
        self.assert_stopped(self.replace(stale, backups), 4, 'E_REJECTED 409', SEC_PRIVATE)
        self.assertEqual(1, len(stale.posts()))
        self.assertEqual([{'sent': SEC_REVISION, 'current': SEC_REVISION + '-concurrent'}],
                         stale.stale_rejections)
        self.assertEqual(SEC_ORIGINAL, stale.content)
        ok = self.server()
        self.assertEqual(0, self.replace(ok, backups).returncode)
        self.assertEqual(([], SEC_CONTENT), (ok.stale_rejections, ok.content))

    def test_t4_backup_dir_is_rejected_before_any_request(self):
        good = self.backup_dir()
        link = os.path.join(self.backup_dir(), 'link')
        os.symlink(good, link)
        plain = os.path.join(self.backup_dir(), 'plain-file')
        Path(plain).write_text('x')
        for label, path in (('world readable', self.backup_dir(0o755)), ('read only', self.backup_dir(0o500)),
                            ('symlinked component', link), ('missing', '/nonexistent/surge-section'),
                            ('ambiguous component', os.path.dirname(good) + '//' + os.path.basename(good)),
                            ('not a directory', plain)):
            with self.subTest(label):
                server = self.server()
                self.assert_stopped(self.replace(server, path), 2, 'E_BACKUP_DIR')
                self.assertEqual([], server.calls)
        self.assertEqual([], os.listdir(good))

    def test_t4_backup_writes_stay_on_the_opened_directory(self):
        """EEXIST／fsync 失败只清本次创建的文件；持有目录 fd 后祖先换链，写入仍落原目录。"""
        module = load_module('surge_ios_section_backup', SURGE_IOS)
        write = self.backup_dir()
        edit = section_payload(backup_dir=write)
        Path(write, 'section-fixed.json').write_text('pre-existing')

        def attempt(token):
            module.secrets = types.SimpleNamespace(token_hex=lambda _n: token)
            fd = module._open_backup_dir(write)
            try:
                with self.assertRaises(module.SectionStop) as caught:
                    module.save_section_backup(edit, fd)
            finally:
                os.close(fd)
            self.assertEqual('E_BACKUP_WRITE', str(caught.exception))
        attempt('fixed')

        def refuse(_fd):
            raise OSError(errno.EIO, 'synthetic fsync failure')
        with mock.patch.object(os, 'fsync', refuse):
            attempt('fixed2')
        self.assertEqual(['section-fixed.json'], os.listdir(write))
        self.assertEqual('pre-existing', Path(write, 'section-fixed.json').read_text())

        top = Path(self.backup_dir())
        real, decoy = top / 'real', top / 'decoy'
        for path in (real, decoy):
            path.mkdir(mode=0o700)
        fd = module._open_backup_dir(str(real))
        try:
            os.rename(str(real), str(top / 'moved-real'))
            os.symlink(str(decoy), str(real))
            module.secrets = types.SimpleNamespace(token_hex=lambda _n: 'race')
            module.save_section_backup(dict(edit, backup_dir=str(real)), fd)
        finally:
            os.close(fd)
        self.assertEqual(([], ['section-race.json']),
                         (os.listdir(str(decoy)), os.listdir(str(top / 'moved-real'))))

    def test_t4_backup_dir_refuses_ancestor_swapped_mid_descent(self):
        """下降途中祖先被换成软链：逐级 O_NOFOLLOW 使 _open_backup_dir 报 E_BACKUP_DIR，decoy 不被写入。"""
        module = load_module('surge_ios_section_descent', SURGE_IOS)
        top = Path(self.backup_dir())
        real, decoy = top / 'real', top / 'decoy'
        for path in (real, real / 'backups', decoy, decoy / 'backups'):
            path.mkdir(mode=0o700)
        real_open, swapped = os.open, []

        def racing(path, flags, *args, **kwargs):
            if path == 'real' and kwargs.get('dir_fd') is not None and not swapped:
                os.rename(str(real), str(top / 'moved-real'))
                os.symlink(str(decoy), str(real))
                swapped.append(True)
            return real_open(path, flags, *args, **kwargs)
        with mock.patch.object(os, 'open', racing), self.assertRaises(module.SectionStop) as caught:
            os.close(module._open_backup_dir(str(real / 'backups')))
        self.assertTrue(swapped)
        self.assertEqual('E_BACKUP_DIR', str(caught.exception))
        self.assertEqual([], os.listdir(str(decoy / 'backups')))

    def test_t5_no_secret_or_body_in_output(self):
        backups = self.backup_dir()
        sentinels = ['SENTINEL-BODY-1', 'SENTINEL-REV-2', 'SENTINEL-ERR-4', 'SENTINEL-UNKNOWN-5', 'SENTINEL-GUARD-6']
        leaky = self.server(post_status=500, post_body=jbytes({'error': 'SENTINEL-ERR-4', 'echo': SEC_CONTENT,
                                                               'key': SEC_KEY}))
        self.assert_stopped(self.replace(leaky, backups), 5, 'E_WRITE_UNKNOWN 500', sentinels + SEC_PRIVATE)
        self.assertEqual((500, leaky.post_body), leaky.sent[-1])       # 哨兵确实上了线路
        self.assertEqual(1, len(leaky.posts()))
        for body in (b'{"content":"SENTINEL-BODY-1","revision":"SENTINEL-REV-2"} SENTINEL-GUARD-6',
                     jbytes({'content': 'SENTINEL-BODY-1'}), b'{"content":1,"revision":"SENTINEL-REV-2"}'):
            with self.subTest(body):
                server = self.server(verify_payload=body)
                self.assert_stopped(self.replace(server, backups), 5, 'E_VERIFY_FAILED', sentinels)
                self.assertEqual(1, len(server.posts()))
        unknown = self.server(post_body=b'{"changed":true,"SENTINEL-UNKNOWN-5":"x"}')
        done = self.replace(unknown, backups)
        self.assertEqual(b'{"changed":true,"ok":true,"verified":true}\n', done.stdout)

    def test_t6_remote_plaintext_is_refused(self):
        server, backups = self.server(), self.backup_dir()
        remote = server.base.replace('127.0.0.1', '203.0.113.7')
        for env in ({}, {'SURGE_ALLOW_REMOTE': '1'}):
            with mock.patch.object(urllib.request.OpenerDirector, 'open') as request:
                done = self.run_section(section_payload(backup_dir=backups), remote, env_extra=env)
            request.assert_not_called()
            self.assert_stopped(done, 2, 'E_TLS_REQUIRED')
        self.assertEqual([], server.calls)

    def test_t6_tls_trusted_ca_and_hostname_mismatch(self):
        """TLS 校验不被关闭：未信任 CA 与 hostname 错配都失败，可信 CA 正向成功。"""
        if not shutil.which('openssl'):
            self.skipTest('openssl unavailable: TLS fixture not covered')
        certs = Path(self.backup_dir())
        ca, ca_key, cert, key, csr, ext = (str(certs / n) for n in
                                           ('ca.pem', 'ca.key', 'cert.pem', 'key.pem', 'req.csr', 'ext.cnf'))
        Path(ext).write_text('subjectAltName=DNS:localhost\n[req]\ndistinguished_name=dn\n[dn]\n'
                             '[ca]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign\n')
        for argv in (['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj',
                      '/CN=synthetic-ca', '-config', ext, '-extensions', 'ca', '-keyout', ca_key, '-out', ca],
                     ['req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=localhost', '-keyout', key,
                      '-out', csr],
                     ['x509', '-req', '-in', csr, '-days', '1', '-CA', ca, '-CAkey', ca_key,
                      '-CAcreateserial', '-extfile', ext, '-out', cert]):
            if subprocess.run(['openssl'] + argv, capture_output=True, timeout=180).returncode:
                self.skipTest('openssl could not build the test certificate chain')
        backups = self.backup_dir()

        def tls_server():
            server = self.server()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(cert, key)
            server._server.socket = context.wrap_socket(server._server.socket, server_side=True)
            return server, server._server.server_address[1]
        # localhost 不是 loopback 字面量：https 非字面量主机须显式放行。
        untrusted, port = tls_server()
        done = self.run_section(section_payload(backup_dir=backups), 'https://localhost:%d' % port,
                                env_extra={'SURGE_ALLOW_REMOTE': '1'})
        self.assert_stopped(done, 4, 'E_READ_FAILED', SEC_PRIVATE)
        self.assertEqual([], untrusted.calls)
        # LibreSSL 默认库加载不采用 SSL_CERT_FILE，仅该提供方显式加载合成 CA。
        # OpenSSL 保留环境变量信任路径；CERT_REQUIRED 和 hostname 校验始终真实执行。
        def load_fixture_ca(context, purpose=ssl.Purpose.SERVER_AUTH):
            context.load_verify_locations(cafile=ca)

        with contextlib.ExitStack() as trust:
            if ssl.OPENSSL_VERSION.startswith('LibreSSL '):
                trust.enter_context(mock.patch.object(ssl.SSLContext, 'load_default_certs', load_fixture_ca))
            mismatch, port = tls_server()
            done = self.run_section(section_payload(backup_dir=backups), 'https://127.0.0.1:%d' % port,
                                    env_extra={'SSL_CERT_FILE': ca})
            self.assert_stopped(done, 4, 'E_READ_FAILED', SEC_PRIVATE)
            self.assertEqual([], mismatch.calls)
            self.assertEqual([], os.listdir(backups))
            trusted, port = tls_server()
            done = self.run_section(section_payload(backup_dir=backups), 'https://localhost:%d' % port,
                                    env_extra={'SSL_CERT_FILE': ca, 'SURGE_ALLOW_REMOTE': '1'})
            self.assertEqual(0, done.returncode, done.stderr)
            self.assertEqual(SEC_CONTENT, trusted.content)

    def test_t7_unknown_after_post_and_recovery_path(self):
        """POST 落地后断连：E_WRITE_UNKNOWN 且不重投；按备份 original＋当前 revision 恢复；
        第三方后续编辑时恢复停在 E_ORIGINAL_CHANGED、零 POST。"""
        backups = self.backup_dir()
        dropped = self.server(drop_after_post=True)
        self.assert_stopped(self.replace(dropped, backups), 5, 'E_WRITE_UNKNOWN')
        self.assertEqual(1, len(dropped.posts()))
        record = self.backup_record(backups)
        self.assertEqual((SEC_ORIGINAL, SEC_REVISION), (record['original'], record['revision']))
        current, revision = dropped.current()
        self.assertEqual((SEC_CONTENT, SEC_REVISION + '-next'), (current, revision))
        dropped.faults.clear()
        restore = {'name': 'Rule', 'revision': revision, 'original': current,
                   'content': record['original'], 'backup_dir': self.backup_dir()}
        done = self.run_section(restore, dropped.base)
        self.assertEqual(b'{"changed":true,"ok":true,"verified":true}\n', done.stdout)
        self.assertEqual((2, SEC_ORIGINAL), (len(dropped.posts()), dropped.current()[0]))
        edited = SEC_CONTENT + 'NEW,RULE,REJECT\n'
        third = self.server(content=edited, revision=revision)
        self.assert_stopped(self.run_section(dict(restore, backup_dir=self.backup_dir()), third.base),
                            3, 'E_ORIGINAL_CHANGED')
        self.assertEqual(([], edited), (third.posts(), third.current()[0]))

    def test_t7_post_write_rewrite_is_verify_failure(self):
        server = self.server(post_rewrites=lambda body: body + '# third-party rewrite\n')
        done = self.replace(server, self.backup_dir())
        self.assert_stopped(done, 5, 'E_VERIFY_FAILED')
        self.assertEqual(b'E_VERIFY_FAILED\n', done.stderr)
        self.assertEqual(['GET', 'POST', 'GET'], server.methods())
        self.assertEqual(SEC_CONTENT + '# third-party rewrite\n', server.content)

    def test_t9_malformed_base_is_a_fixed_token_without_leak(self):
        """BASE 解析失败固定 token、零备份、不回显。旧版 urlparse 不校验方括号 host，
        该形态落到 E_TLS_REQUIRED，同样是联网前的固定拒绝。"""
        sentinel = 'SYNTHETIC-BASE-SENTINEL-DO-NOT-ECHO'
        payload = {'name': 'p', 'original': 'a:b\n', 'content': 'a:c\n', 'revision': 'r1'}
        for base in ('http://[%s' % sentinel, 'http://[%s]:6171' % sentinel,
                     'http://[::1]:99999', 'https://[::1]:99999'):
            with self.subTest(base=base):
                backups = self.backup_dir()
                done = self.run_section(dict(payload, backup_dir=backups), base)
                self.assert_stopped(done, 2, 'E_', [sentinel])
                self.assertRegex(done.stderr, rb'^E_(BASE|TLS_REQUIRED)\n$')
                self.assertEqual([], os.listdir(backups))
        done = self.run_section(dict(payload, backup_dir=self.backup_dir()), 'http://127.0.0.1:1')
        self.assert_stopped(done, 4, 'E_READ_FAILED')

    def test_t9_entry_shape_and_generic_post_are_fixed_tokens(self):
        sentinel = 'SENTINEL-ARGV-7'
        server = self.server()
        for argv in (['--confirm-dangerous', 'section', 'replace', '--input', '-', '--' + sentinel],
                     ['--confirm-dangerous', 'section', 'replace', '--input'],
                     ['--confirm-dangerous', 'section', 'replace', '--input', '-', sentinel],
                     ['section', 'replace', '--input', '/tmp/' + sentinel],
                     ['section', 'replace', '-', '--input'], ['section']):
            with self.subTest(argv=argv):
                done = run_entry(SURGE_IOS, argv, offline_env(server.base, SEC_KEY), text=False)
                self.assert_stopped(done, 2, 'E_INPUT', [sentinel])
        # 通用 POST 命中分节路由：先于 JSON 解析、取密与联网拒绝（含规范化绕过写法）
        for path, body in (('/v1/profiles/section', '{"name":"Rule"'), ('/v1/profiles/section', '[1,2,'),
                           ('/v1/profiles/section', sentinel), ('//v1//profiles//section', '{"name":"Rule"}'),
                           ('/v1/profiles/%73ection', '{}'), ('/v1/profiles/./section/', '{}'),
                           ('/V1/Profiles/Section', '{}'), ('/v1/x/../profiles/section', '{}')):
            with self.subTest(path=path, body=body):
                done = run_script(SURGE_IOS, ['request', 'POST', path, body], server.base)
                self.assertEqual((2, 'E_SECTION_WRITE_REQUIRES_SAFE_ENTRY\n'), (done.returncode, done.stderr))
        self.assertEqual([], server.calls)
        done = run_script(SURGE_IOS, ['request', 'GET', '/v1/profiles/section?name=Rule'], server.base)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(['/v1/profiles/section?name=Rule'], [c['path'] for c in server.calls])

    def test_t10_failures_after_post_are_stage_classified(self):
        """写已发出后的任何异常都是 5（结果未知／核验失败）且恰一次 POST；读阶段异常是 4、零 POST。"""
        backups = self.backup_dir()
        for faults, code, token, posts in (
                ({'illegal_chunk': 'read'}, 4, 'E_READ_FAILED', 0),
                ({'illegal_chunk': 'verify'}, 5, 'E_VERIFY_FAILED', 1),
                ({'drop_on_get_after_post': True}, 5, 'E_VERIFY_FAILED', 1),
                ({'verify_payload': b'not-json'}, 5, 'E_VERIFY_FAILED', 1),
                ({'verify_payload': b'{"content":"x"}'}, 5, 'E_VERIFY_FAILED', 1),
                ({'verify_payload': b'{"content":1,"revision":"r"}'}, 5, 'E_VERIFY_FAILED', 1),
                ({'garbage_status_line': True}, 5, 'E_WRITE_UNKNOWN', 1)):
            with self.subTest(faults=faults):
                server = self.server(**faults)
                self.assert_stopped(self.replace(server, backups), code, token, SEC_PRIVATE + ['ZZZZ-not-hex'])
                self.assertEqual(posts, len(server.posts()))
        truncated = self.server(truncate_post_response=True)    # 结论以写后 GET 为准
        self.assertEqual(0, self.replace(truncated, backups).returncode)
        self.assertEqual((1, SEC_CONTENT), (len(truncated.posts()), truncated.content))


if __name__ == '__main__':
    unittest.main()

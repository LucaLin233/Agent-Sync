"""Fixed authenticated reads: offline, synthetic only; opt-in case, not full."""
import base64, hashlib, importlib.util, io, json, pathlib
import ssl, socket, subprocess, sys, unittest
from unittest import mock
P = pathlib.Path(__file__).resolve().parents[1] / 'tools/auth-call.py'
spec = importlib.util.spec_from_file_location('auth_call', P)
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
TOKEN = 'SYNTHETIC-only-marker'
PR = dict(number=7, state='OPEN', merged=False, headRefOid='a' * 40, baseRefOid='b' * 40, isDraft=False, reviewDecision=None, mergeable='MERGEABLE', changedFiles=1)
ENV = {'GH_TOKEN': TOKEN, 'LOBEHUB_SERVER': 'https://hub.test', 'LOBEHUB_CLI_API_KEY': TOKEN}

def resource(b=b'abc', encoding='utf8'):
    return dict(content=b.decode() if encoding == 'utf8' else base64.b64encode(b).decode(), encoding=encoding, fileHash=hashlib.sha256(b).hexdigest(), fileType='text/plain', path='a.md', size=len(b))

class Response:
    status = 200

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def read(self, n):
        return self.raw[:n]

class Opener:

    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    def open(self, req, timeout):
        self.calls.append(req)
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw if isinstance(self.raw, Response) else Response(self.raw)

def wire(obj):
    return json.dumps(obj).encode()

def rd(obj):
    return wire({'result': {'data': {'json': obj}}})

class Tests(unittest.TestCase):

    def setUp(self):
        p = mock.patch.object(socket, 'socket', side_effect=AssertionError('no sockets'))
        p.start()
        self.addCleanup(p.stop)

    def call(self, obj=None, raw=None, token=TOKEN):
        op = Opener(raw if raw is not None else rd(resource() if obj is None else obj))
        g = dict(ENV, LOBEHUB_CLI_API_KEY=token).get
        return (A.skill_resource('skill', 'a.md', getter=g, opener=op), op)

    def reject(self, code, **kw):
        with self.assertRaises(A.ToolError) as c:
            self.call(**kw)
        self.assertEqual(str(c.exception), code)

    def test_resources(self):
        for b in (b'', b'abc', b'line\n'):
            for enc in ('utf8', 'base64'):
                obj = resource(b, enc)
                out, op = self.call(obj)
                self.assertEqual(out['resource'], obj)
                self.assertEqual(op.calls[0].get_method(), 'GET')
                self.assertNotIn(TOKEN, op.calls[0].full_url)

    def test_pr_query_and_credentials(self):
        op = Opener(wire({'data': {'repository': {'pullRequest': PR}}}))
        names = []

        def get(n):
            names.append(n)
            return ENV[n]
        out = A.pr_meta('owner/repo', 7, getter=get, opener=op)
        self.assertEqual(out['pullRequest'], PR)
        self.assertEqual(names, ['GH_TOKEN'])
        req = op.calls[0]
        self.assertEqual(req.full_url, A.GRAPHQL_URL)
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(json.loads(req.data)['variables'], dict(owner='owner', name='repo', number=7))

    def test_fields_and_integrity(self):
        for changes, code in [({'extra': 1}, 'bad_fields'), ({'size': True}, 'bad_fields'), ({'size': 4}, 'bad_integrity'), ({'fileHash': '0' * 64}, 'bad_integrity'), ({'path': 'other'}, 'bad_fields'), ({'encoding': 'raw'}, 'bad_fields'), ({'encoding': 'base64', 'content': '!'}, 'bad_fields')]:
            with self.subTest(changes=changes):
                self.reject(code, obj=dict(resource(), **changes))

    def test_reflection(self):
        for token in (TOKEN, 'quote"marker', 'back\\marker'):
            for enc in ('utf8', 'base64'):
                self.reject('reflected_credential', obj=resource(token.encode(), enc), token=token)
            self.reject('reflected_credential', obj=dict(resource(), fileType=token), token=token)
        with self.assertRaisesRegex(A.ToolError, '^reflected_credential$'):
            A.pr_meta('marker/repo', 7, getter=lambda n: 'marker', opener=Opener(wire({'data': {'repository': {'pullRequest': PR}}})))

    def test_shapes_and_bounds(self):
        for raw, code in [(b'{', 'bad_json'), (b'{"result":0,"result":1}', 'bad_json'), (wire({'result': {'data': {'json': resource()}, 'extra': 1}}), 'bad_shape'), (b' ' * (A.MAX_BODY + 1), 'response_too_large')]:
            with self.subTest(code=code):
                self.reject(code, raw=raw)
        raw = rd(resource())
        self.call(raw=raw + b' ' * (A.MAX_BODY - len(raw)))

    def test_targets_before_credentials(self):

        def no(n):
            raise AssertionError('credential read')
        for sid, path in (('../bad', 'a.md'), ('ok', '../a'), ('ok', 'a//b'), ('ok', 'a b')):
            with self.assertRaises(A.ToolError):
                A.skill_resource(sid, path, getter=no)
        for repo, num in (('bad', 7), ('o/r', True), ('o/r', 0)):
            with self.assertRaises(A.ToolError):
                A.pr_meta(repo, num, getter=no)

    def test_missing_and_bad_credentials(self):
        for token in ('a\r\nb', 'space key', 'badé'):
            self.reject('bad_credential:LOBEHUB_CLI_API_KEY', token=token)
        for server in ('http://h', 'https://u:p@h', 'https://h/api', 'https://h/?q=1'):
            with self.assertRaisesRegex(A.ToolError, '^bad_server$'):
                A.skill_resource('s', 'a.md', getter=dict(ENV, LOBEHUB_SERVER=server).get)
        with self.assertRaisesRegex(A.ToolError, '^missing_variable:GH_TOKEN$'):
            A.pr_meta('o/r', 7, getter=lambda n: None)

    def test_transport_and_unread_error_body(self):
        for exc in (TimeoutError(), RuntimeError(TOKEN)):
            self.reject('transport_error', raw=exc)

        class Bad(Response):
            status = 403

            def read(self, n):
                raise AssertionError('error body read')
        self.reject('http_status_403', raw=Bad(b''))
        for code in (301, 302, 303, 307, 308):
            err = A.urllib.error.HTTPError('https://x', code, TOKEN, None, io.BytesIO(TOKEN.encode()))
            self.reject('http_status_' + str(code), raw=err)

    def test_tls_and_no_redirect(self):
        with mock.patch.object(A.ssl, 'create_default_context', side_effect=AssertionError('keylog')):
            op = A.make_opener()
        ctx = next((h._context for h in op.handlers if isinstance(h, A.urllib.request.HTTPSHandler)))
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertIsNone(ctx.keylog_filename)
        self.assertIsNone(A._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil'))

    def test_pr_response_number(self):
        op = Opener(wire({'data': {'repository': {'pullRequest': dict(PR, number=8)}}}))
        with self.assertRaisesRegex(A.ToolError, '^bad_fields$'):
            A.pr_meta('o/r', 7, getter=ENV.get, opener=op)

    def test_real_cli(self):
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/nonexistent', 'PYTHONNOUSERSITE': '1'}
        for args, code, error in [(['--help'], 0, None), (['--unknown', TOKEN], 2, 'bad_args'), (['pr-meta', '--repo', 'o/r', '--number', '7'], 2, 'missing_variable:GH_TOKEN')]:
            r = subprocess.run([sys.executable, '-B', str(P)] + args, env=env, capture_output=True, timeout=5)
            self.assertEqual(r.returncode, code)
            self.assertNotIn(TOKEN.encode(), r.stdout + r.stderr)
            if error:
                self.assertEqual(r.stdout, b'')
                self.assertEqual(json.loads(r.stderr), dict(ok=False, error=error))
            else:
                self.assertEqual(r.stderr, b'')
                self.assertIn(b'pr-meta', r.stdout)
if __name__ == '__main__':
    unittest.main()

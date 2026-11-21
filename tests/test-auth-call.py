"""Fixed authenticated reads: offline, synthetic only; opt-in case, not full."""
import importlib.util, io, json, pathlib
import ssl, socket, subprocess, sys, unittest
from unittest import mock
P = pathlib.Path(__file__).resolve().parents[1] / 'tools/auth-call.py'
spec = importlib.util.spec_from_file_location('auth_call', P)
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
TOKEN = 'SYNTHETIC-only-marker'
PR = dict(number=7, state='OPEN', merged=False, headRefOid='a' * 40, baseRefOid='b' * 40, isDraft=False, reviewDecision=None, mergeable='MERGEABLE', changedFiles=1)
ENV = {'GH_TOKEN': TOKEN}

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

def payload(value=None):
    return wire({'data': {'repository': {'pullRequest': PR if value is None else value}}})

class Tests(unittest.TestCase):

    def setUp(self):
        p = mock.patch.object(socket, 'socket', side_effect=AssertionError('no sockets'))
        p.start()
        self.addCleanup(p.stop)

    def call(self, raw=None, token=TOKEN):
        op = Opener(raw if raw is not None else payload())
        g = dict(ENV, GH_TOKEN=token).get
        return (A.pr_meta('owner/repo', 7, getter=g, opener=op), op)

    def reject(self, code, **kw):
        with self.assertRaises(A.ToolError) as c:
            self.call(**kw)
        self.assertEqual(str(c.exception), code)

    def test_pr_query_and_credentials(self):
        op = Opener(payload())
        names = []

        def get(n):
            names.append(n)
            return ENV[n]
        out = A.pr_meta('owner/repo', 7, getter=get, opener=op)
        self.assertEqual(out, {'action': 'pr-meta', 'repo': 'owner/repo', 'pullRequest': PR})
        self.assertEqual(names, ['GH_TOKEN'])
        req = op.calls[0]
        self.assertEqual(req.get_header("Authorization"), "bearer " + TOKEN)
        self.assertEqual(req.full_url, A.GRAPHQL_URL)
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(json.loads(req.data)['variables'], dict(owner='owner', name='repo', number=7))
        self.assertEqual(set(json.loads(req.data)), {'query', 'variables'})

    def test_reflection(self):
        # 包装字段（repo）回显凭据
        with self.assertRaisesRegex(A.ToolError, '^reflected_credential$'):
            A.pr_meta('marker/repo', 7, getter=lambda n: 'marker', opener=Opener(payload()))
        # 嵌套字段（state）回显带引号或反斜杠的凭据
        for token in (TOKEN, 'quote"marker', 'back\\marker'):
            with self.assertRaisesRegex(A.ToolError, '^reflected_credential$'):
                A.pr_meta('owner/repo', 7, getter=lambda n, token=token: token,
                          opener=Opener(payload(dict(PR, state=token))))

    def test_fields(self):
        for changes in ({'extra': 1}, {'number': 8}, {'changedFiles': True}, {'merged': 'no'},
                        {'headRefOid': 'a' * 39}, {'state': 1}, {'reviewDecision': 1}):
            with self.subTest(changes=changes):
                self.reject('bad_fields', raw=payload(dict(PR, **changes)))

    def test_shapes_and_bounds(self):
        for raw, code in [(b'{', 'bad_json'), (b'{"data":0,"data":1}', 'bad_json'),
                          (wire({'data': {'repository': {'pullRequest': PR}}, 'extra': 1}), 'graphql_error'),
                          (wire({'data': {'repository': {}}, 'extra': 1}), 'graphql_error'),
                          (wire({'data': {'repository': {}}}), 'bad_shape'),
                          (b' ' * (A.MAX_BODY + 1), 'response_too_large')]:
            with self.subTest(code=code):
                self.reject(code, raw=raw)
        raw = payload()
        self.call(raw=raw + b' ' * (A.MAX_BODY - len(raw)))

    def test_bad_targets_before_credentials(self):

        def no(n):
            raise AssertionError('credential read')
        for repo, num in (('bad', 7), ('o/r', True), ('o/r', 0), ('a/b/c', 7)):
            with self.assertRaises(A.ToolError):
                A.pr_meta(repo, num, getter=no)

    def test_missing_and_bad_credentials(self):
        for token in ('a\r\nb', 'space key', 'bad\u00e9'):
            self.reject('bad_credential:GH_TOKEN', token=token)
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

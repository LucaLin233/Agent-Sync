"""LH 技能离线验收工具：离线、合成夹具、默认不进 full（opt-in verify）。"""
import base64
import contextlib
import io
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / 'tools'
TOOL = TOOLS / 'lh-verify.py'
spec = importlib.util.spec_from_file_location('auth_call', TOOLS / 'auth-call.py')
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
spec_verify = importlib.util.spec_from_file_location('lh_verify', TOOL)
V = importlib.util.module_from_spec(spec_verify)
spec_verify.loader.exec_module(V)
TOKEN = 'SYNTHETIC-only-marker'
OBS = 'OBS-1'
ALIAS = 'nonsecret-alias'

CORE_SKILL = '---\nname: luno-core\ndescription: 核心\n---\n# Body\nline\n'
EXTRA_SKILL = '---\r\nname: extra-skill\r\ndescription: 额外\r\n---\r\n\r\nbody\r\n'
FILES = {
    'skills/luno-core/SKILL.md': CORE_SKILL.encode(),
    'skills/luno-core/references/a.md': b'alpha\n',
    'skills/luno-core/references/crlf.md': b'crlf\r\nline\r\n',
    'skills/luno-core/references/empty.md': b'',
    'skills/luno-core/references/bin.dat': b'\xff\xfe\x00\x01\n',
    'skills/extra-skill/SKILL.md': EXTRA_SKILL.encode(),
    'skills/extra-skill/references/x.md': b'x\n',
}
REG = {'schemaVersion': 1, 'note': 'fixture', 'objects': [
    {'id': 'luno-core', 'type': 'skill', 'source': 'skills/luno-core/SKILL.md',
     'resources': ['skills/luno-core/references/a.md', 'skills/luno-core/references/crlf.md',
                   'skills/luno-core/references/empty.md', 'skills/luno-core/references/bin.dat'],
     'installSource': 'https://github.com/LucaLin233/Agent-Sync/tree/main/skills/luno-core',
     'ends': {'repo': {'present': True},
              'lobehub': {'present': True, 'kind': 'skill', 'id': 'skl_core'}}},
    {'id': 'extra-skill', 'type': 'skill', 'source': 'skills/extra-skill/SKILL.md',
     'resources': ['skills/extra-skill/references/x.md'],
     'installSource': 'https://example.test/elsewhere',
     'ends': {'repo': {'present': True},
              'lobehub': {'present': True, 'kind': 'skill', 'id': 'skl_extra'}}},
]}
IDS = {'luno-core': 'skl_core', 'extra-skill': 'skl_extra'}
CORE_PATHS = ['references/a.md', 'references/crlf.md', 'references/empty.md', 'references/bin.dat']
GITENV = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': os.devnull,
          'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
          'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@example.test',
          'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@example.test',
          'GIT_AUTHOR_DATE': '2026-11-15T00:00:00Z', 'GIT_COMMITTER_DATE': '2026-11-15T00:00:00Z',
          'LC_ALL': 'C'}


def git(repo, *args):
    out = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', repo] + list(args),
                         env=dict(GITENV), stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return out.stdout.decode().strip()


def snapshot(repo, label):
    for path, blob in list(FILES.items()) + [('tools/sync-targets.json',
                                              json.dumps(REG).encode())]:
        target = os.path.join(repo, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as handle:
            handle.write(blob)
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', label)
    return git(repo, 'rev-parse', 'HEAD')


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

    def open(self, req, timeout):
        return Response(self.raw)


def record(path, blob, encoding=None, ident='luno-core'):
    """经 auth-call 真实校验路径产出成功记录（生产消费接缝）。"""
    if encoding is None:
        try:
            blob.decode('utf-8')
            encoding = 'utf8'
        except UnicodeDecodeError:
            encoding = 'base64'
    obj = {'content': blob.decode('utf-8') if encoding == 'utf8'
           else base64.b64encode(blob).decode(),
           'encoding': encoding, 'fileHash': hashlib.sha256(blob).hexdigest(),
           'fileType': 'text/plain', 'path': path, 'size': len(blob)}
    out = A.skill_resource(IDS[ident], path, getter={'LOBEHUB_SERVER': 'https://hub.test',
                                                'LOBEHUB_CLI_API_KEY': TOKEN}.get,
                           opener=Opener(json.dumps({'result': {'data': {'json': obj}}}).encode()))
    return {'observationId': OBS, 'instanceRef': ALIAS,
            'request': {'id': IDS[ident], 'path': path}, 'exitCode': 0,
            'stdout': json.dumps({'ok': True, **out}) + '\n', 'stderr': ''}


def failure(path, code='transport_error', ident='luno-core'):
    return {'observationId': OBS, 'instanceRef': ALIAS,
            'request': {'id': IDS[ident], 'path': path}, 'exitCode': 2, 'stdout': '',
            'stderr': json.dumps({'ok': False, 'error': code}) + '\n'}


def evidence(objects):
    return {'schemaVersion': 1,
            'observation': {'id': OBS, 'instanceRef': ALIAS,
                            'sourceVersion': 'CE-2.3.2+collector-1',
                            'startedAt': '2026-11-15T08:00:00Z',
                            'finishedAt': '2026-11-15T08:00:01Z',
                            'sourceBasis': 'reviewed-source-projection-ref'},
            'objects': objects}


def core_entry(paths=None, calls=None, **over):
    proj = {'id': 'skl_core', 'name': 'luno-core', 'description': '核心',
            'identifier': 'lucalin233-agent-sync-luno-core', 'content': '# Body\nline\n'}
    proj.update(over)
    return {'object': 'luno-core', 'observationId': OBS, 'instanceRef': ALIAS,
            'projection': proj,
            'resourcePaths': CORE_PATHS if paths is None else paths,
            'calls': [record(p, FILES['skills/luno-core/' + p])
                      for p in (CORE_PATHS if paths is None else paths)
                      if 'skills/luno-core/' + p in FILES] if calls is None else calls}


def full_core():
    return core_entry()


class Fixture:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix='lh-verify-')
        self.repo = os.path.join(self.root, 'repo')
        self.home = os.path.join(self.root, 'home')
        os.makedirs(self.repo)
        os.makedirs(self.home)
        git(self.repo, 'init', '-q')
        self.c1 = snapshot(self.repo, 'base')
        FILES['skills/luno-core/references/a.md'] = b'alpha changed\n'
        FILES['skills/luno-core/SKILL.md'] = (CORE_SKILL + 'extra\n').encode()
        self.c2 = snapshot(self.repo, 'resource and body')
        FILES['skills/luno-core/SKILL.md'] = CORE_SKILL.encode()
        FILES['skills/luno-core/references/a.md'] = b'alpha\n'
        self.clean = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                      'HOME': self.home, 'TMPDIR': self.root,
                      'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}
        self.seq = 0

    def run(self, ev, version=None, objects=('luno-core',), cwd=None, args=None):
        self.seq += 1
        path = os.path.join(self.root, 'ev-%02d.json' % self.seq)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(ev if isinstance(ev, str) else json.dumps(ev))
        argv = [sys.executable, '-I', '-B', str(TOOL), '--repo', self.repo,
                '--git-version', version or self.c1]
        for name in objects:
            argv += ['--object', name]
        argv += ['--evidence', path] if args is None else args + ['--evidence', path]
        proc = subprocess.run(argv, capture_output=True, env=dict(self.clean),
                              cwd=cwd or self.root)
        text = proc.stdout.decode('utf-8')
        self.assert_single = (text.count('\n'), text.endswith('\n'))
        return proc.returncode, json.loads(text), text, proc

    def run_fast(self, ev, version=None, objects=('luno-core',), cwd=None, args=None):
        """进程内调用同一入口：只有进程边界与 -I 由 run() 的真实子进程守住。"""
        self.seq += 1
        path = os.path.join(self.root, 'ev-%02d.json' % self.seq)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(ev if isinstance(ev, str) else json.dumps(ev))
        argv = ['--repo', self.repo, '--git-version', version or self.c1]
        for name in objects:
            argv += ['--object', name]
        argv += ['--evidence', path] if args is None else args + ['--evidence', path]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = V.main(argv)
        text = out.getvalue()
        return rc, json.loads(text), text, err.getvalue()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


F = None


def setUpModule():
    global F
    F = Fixture()


def tearDownModule():
    F.tearDown()


class Verify(unittest.TestCase):

    def test_match(self):
        rc, doc, text, proc = F.run(evidence([full_core()]))
        self.assertEqual((rc, doc['status'], proc.stderr), (0, 'match', b''))
        self.assertEqual((text.count('\n'), text.endswith('\n')), (1, True))
        self.assertEqual(list(doc), ['gitVersion', 'status', 'objects', 'missingEvidence', 'errors'])
        obj = doc['objects'][0]
        self.assertEqual(list(obj), ['object', 'id', 'checked', 'differences',
                                    'missingEvidence', 'errors', 'resourcePaths'])
        self.assertEqual(doc['gitVersion'], F.c1)
        self.assertEqual(sorted(obj['checked']), sorted(
            ['id', 'name', 'description', 'identifier', 'content'] +
            ['resource:' + p for p in CORE_PATHS]))
        self.assertNotIn('alpha', text)

    def test_cli_isolation_and_order(self):
        ev = evidence([full_core()])
        rc, doc, _, _ = F.run(ev, objects=('luno-core',), cwd='/')
        self.assertEqual((rc, doc['status']), (0, 'match'))
        rc, doc, _, _ = F.run(ev, args=['--bogus'])
        self.assertEqual((rc, doc['errors']), (2, ['bad_args']))
        rc, doc, _, _ = F.run_fast(ev, args=['--bogus'])
        self.assertEqual((rc, doc['errors']), (2, ['bad_args']))
        rc, doc, _, _ = F.run_fast(ev, objects=('luno-core', 'luno-core'))
        self.assertEqual((rc, doc['errors']), (2, ['bad_args']))
        rc, doc, _, _ = F.run_fast(ev, version=F.c1.upper())
        self.assertEqual((rc, doc['errors']), (2, ['bad_args']))
        rc, doc, _, _ = F.run_fast(ev, objects=('luno-core', 'ghost'))
        self.assertEqual((rc, doc['errors']), (2, ['object_not_registered']))
        self.assertEqual(git(F.repo, 'status', '--porcelain'), '')

    def test_commit_differences(self):
        rc, doc, _, _ = F.run_fast(evidence([full_core()]), version=F.c2)
        self.assertEqual((rc, doc['status']), (1, 'different'))
        self.assertEqual(doc['objects'][0]['differences'],
                         ['content', 'resource:references/a.md'])
        self.assertEqual(F.run_fast(evidence([full_core()]), version='0' * 40)[0], 2)

    def test_missing_and_extra_sets(self):
        entry = core_entry(paths=CORE_PATHS[:2] + ['references/extra.md'])
        rc, doc, _, _ = F.run_fast(evidence([entry]))
        obj = doc['objects'][0]
        self.assertEqual((rc, doc['status']), (1, 'different'))
        self.assertEqual(obj['resourcePaths'], {'missing': ['references/bin.dat',
                                                            'references/empty.md'],
                                                 'extra': ['references/extra.md']})
        self.assertEqual(obj['missingEvidence'], [])
        dropped = core_entry(calls=[record(p, FILES['skills/luno-core/' + p])
                                    for p in CORE_PATHS[:2]])
        rc, doc, _, _ = F.run_fast(evidence([dropped]))
        self.assertEqual(rc, 3)
        self.assertEqual(doc['missingEvidence'], ['luno-core:resource:references/bin.dat',
                                                  'luno-core:resource:references/empty.md'])
        extra_call = record('references/extra.md', b'not accepted\n')
        rc, doc, _, _ = F.run_fast(evidence([core_entry(calls=[
            record(p, FILES['skills/luno-core/' + p]) for p in CORE_PATHS] + [extra_call])]))
        self.assertEqual((rc, doc['status']), (0, 'match'))
        rc, doc, _, _ = F.run_fast(evidence([]))
        self.assertEqual((rc, doc['missingEvidence']), (3, ['luno-core:objects[luno-core]']))

    def test_bytes_and_integrity(self):
        # CRLF 不归一：只把记录正文换成 LF 版，差异必须只落在该资源。
        entry = full_core()
        entry['calls'][1] = record('references/crlf.md', b'crlf\nline\n')
        rc, doc, _, _ = F.run_fast(evidence([entry]))
        self.assertEqual((rc, doc['status']), (1, 'different'))
        self.assertEqual(doc['objects'][0]['differences'], ['resource:references/crlf.md'])
        broken = record('references/a.md', b'alpha\n')
        broken['stdout'] = broken['stdout'].replace('alpha', 'alpho')
        entry = full_core()
        entry['calls'][0] = broken
        rc, doc, _, _ = F.run_fast(evidence([entry]))
        self.assertEqual((rc, doc['errors']), (2, ['bad_integrity']))
        bad = record('references/a.md', b'alpha\n')
        bad['stdout'] = bad['stdout'].replace('"utf8"', '"hex"')
        entry = full_core()
        entry['calls'][0] = bad
        rc, doc, _, _ = F.run_fast(evidence([entry]))
        self.assertEqual((rc, doc['errors']), (2, ['bad_fields']))

    def test_metadata_and_identifier(self):
        cases = [(dict(name=None), 1, ['name']), (dict(name='luno-core '), 1, ['name']),
                 (dict(description=''), 1, ['description']),
                 (dict(identifier='other'), 1, ['identifier']),
                 (dict(content='# Body\nline'), 1, ['content'])]
        for over, rc_want, field in cases:
            rc, doc, _, _ = F.run_fast(evidence([core_entry(**over)]))
            self.assertEqual((rc, doc['objects'][0]['differences']), (rc_want, field))
        extra = {'object': 'extra-skill', 'observationId': OBS, 'instanceRef': ALIAS,
                 'projection': {'id': 'skl_extra', 'name': 'extra-skill',
                                'description': '额外', 'identifier': None, 'content': 'body\r\n'},
                 'resourcePaths': ['references/x.md'],
                 'calls': [record('references/x.md', b'x\n', ident='extra-skill')]}
        rc, doc, _, _ = F.run_fast(evidence([extra]), objects=('extra-skill',))
        self.assertEqual((rc, doc['missingEvidence']), (3, ['extra-skill:identifier']))
        rc, doc, _, _ = F.run_fast(evidence([dict(extra, projection=dict(extra['projection'],
                                                                   id='skl_other'))]),
                              objects=('extra-skill',))
        self.assertEqual((rc, doc['objects'][0]['differences']), (1, ['id']))
        self.assertEqual(doc['objects'][0]['resourcePaths'], {'missing': [], 'extra': []})

    def test_records(self):
        ok = record('references/a.md', b'alpha\n')
        trimmed = dict(ok, stdout=ok['stdout'].rstrip('\n'))
        rc, doc, _, _ = F.run_fast(evidence([core_entry(calls=[trimmed])]))
        self.assertEqual((rc, doc['errors']), (2, ['bad_shape']))
        unknown = dict(ok, exitCode=2, stdout='',
                       stderr=json.dumps({'ok': False, 'error': 'some text'}) + '\n')
        rc, doc, _, _ = F.run_fast(evidence([core_entry(calls=[unknown])]))
        self.assertEqual((rc, doc['errors']), (2, ['bad_shape']))
        rc, doc, _, _ = F.run_fast(evidence([core_entry(calls=[failure('references/a.md')])]))
        self.assertEqual((rc, doc['errors']), (2, ['transport_error']))
        rc, doc, _, _ = F.run_fast(evidence([core_entry(calls=[failure('references/a.md', 'http_status_503')])]))
        self.assertEqual((rc, doc['errors']), (2, ['http_status_503']))

    def test_association(self):
        rc, doc, _, _ = F.run_fast(evidence([dict(full_core(), observationId='OTHER')]))
        self.assertEqual((rc, doc['errors']), (2, ['association_error']))
        call = record('references/a.md', b'alpha\n')
        call['instanceRef'] = 'other-alias'
        rc, doc, _, _ = F.run_fast(evidence([core_entry(calls=[call])]))
        self.assertEqual((rc, doc['errors']), (2, ['association_error']))
        moved = record('references/a.md', b'alpha\n')
        moved['request']['path'] = 'references/crlf.md'
        entry = full_core()
        entry['calls'][1] = moved
        rc, doc, _, _ = F.run_fast(evidence([entry]))
        self.assertEqual((rc, doc['errors']), (2, ['association_error']))


class Evidence(unittest.TestCase):

    def test_strict_json(self):
        text = json.dumps(evidence([full_core()]), ensure_ascii=False)
        dup = text.replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1')
        rc, doc, _, _ = F.run_fast(dup)
        self.assertEqual((rc, doc['errors']), (2, ['bad_evidence_json']))
        rc, doc, _, _ = F.run_fast(text.replace('"schemaVersion": 1', '"schemaVersion": NaN'))
        self.assertEqual((rc, doc['errors']), (2, ['bad_evidence_json']))
        rc, doc, _, _ = F.run_fast(text.replace('"schemaVersion": 1', '"schemaVersion": true'))
        self.assertEqual((rc, doc['errors']), (2, ['bad_evidence_shape']))
        rc, doc, _, _ = F.run_fast(json.loads(text) | {'extra': 1})
        self.assertEqual((rc, doc['errors']), (2, ['bad_evidence_shape']))

    def test_missing_and_ordering(self):
        doc = evidence([full_core()])
        del doc['observation']['finishedAt']
        rc, out, _, _ = F.run_fast(doc)
        self.assertEqual((rc, out['status'], out['missingEvidence']),
                         (3, 'incomplete', ['observation.finishedAt']))
        doc = evidence([full_core()])
        doc['observation']['finishedAt'] = '2026-11-15T07:00:00Z'
        rc, out, _, _ = F.run_fast(doc)
        self.assertEqual((rc, out['errors']), (2, ['bad_evidence_shape']))
        doc = evidence([full_core(), full_core()])
        rc, out, _, _ = F.run_fast(doc)
        self.assertEqual((rc, out['errors']), (2, ['duplicate_object']))
        doc = evidence([core_entry(paths=CORE_PATHS + ['references/a.md'])])
        rc, out, _, _ = F.run_fast(doc)
        self.assertEqual((rc, out['errors']), (2, ['duplicate_path']))
        doc = evidence([core_entry(calls=[record('references/a.md', b'alpha\n')] * 2)])
        rc, out, _, _ = F.run_fast(doc)
        self.assertEqual((rc, out['errors']), (2, ['duplicate_request']))
        doc = evidence([full_core(), dict(full_core(), object='extra-skill')])
        rc, out, _, _ = F.run_fast(doc)
        self.assertEqual((rc, out['errors']), (2, ['extra_object']))


if __name__ == '__main__':
    unittest.main()

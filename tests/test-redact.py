#!/usr/bin/env python3
"""读取形态的脱敏与模板契约（离线、确定性）。

* 输出侧：读取模板产出的投影（键名＋长度、列白名单结果、键名清单）经共用 `_privacy.redact_text`
  后形态不变；全量形态（env、SELECT *、整份配置）经同一入口后不残留标记。
* 读取侧：各技能模板里的读取命令示例，其实际字段面必须落在模板声明的字段面内；禁止原语
  （env／printenv／cat／SELECT * 等）只能出现在禁止语境里。

两类都只核离线夹具与模板文本，不证明自由 Shell 已被机械限制；读取侧关口仍由执行者按
`luno-core/references/safety.md`〈秘密面〉与各模板遵守。标记 `ZMARK` 为合成低熵串。
"""
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    'luno_shared_privacy', str(ROOT / 'skills/luno-surge/scripts/_privacy.py'))
PRIVACY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(PRIVACY)
redact = PRIVACY.redact_text

M = 'ZMARK'
LONG_BLOB = M * 9 + '0123456789abcdef'                 # 40+ 字符不透明串
JWT = 'eyJ' + M + 'abc.' + M + 'def.' + M + 'gh'
SK_KEY = 'sk-' + M + '0123456789abcdef'

OPS, HUB, MINIS = ROOT / 'skills/luno-ops', ROOT / 'skills/luno-platform', ROOT / 'skills/luno-platform'
TEMPLATE_FILES = {
    'platform-entry': HUB / 'SKILL.md',
    'ops-entry': OPS / 'SKILL.md',
    'ops-runtime': OPS / 'references/service-runtime.md',
    'hub-instance': HUB / 'references/lobehub-instance.md',
    'hub-entry': HUB / 'references/lobehub.md',
    'minis-config': MINIS / 'references/minis-configuration.md',
    'sync-workflow': ROOT / 'skills/luno-core/references/sync-workflow.md',
}
OPS_RUNTIME, HUB_INSTANCE, HUB_ENTRY = (TEMPLATE_FILES[k] for k in ('ops-runtime', 'hub-instance', 'hub-entry'))
# 模板必须真的给出这些声明范围形态（缺锚点 ⇒ 禁止原语检查会空转）
ANCHORS = {
    'ops-entry': ['references/service-runtime.md', '声明的指定键'],
    'ops-runtime': ['docker exec', 'sh -c', 'len=%s', 'awk -F=', 'length(substr($0,index($0,"=")+1))',
                    "jq '{port: .server.port", 'docker compose config --quiet', '没有这类接口就停止依赖'],
    'hub-instance': ['information_schema.columns', 'SELECT', '人已确认的列白名单', 'LIMIT'],
    'minis-config': ['筛选和分页只缩小记录集，不能代替字段投影', '字段形态和路径写法'],
}
FORBIDDEN = (
    ('env', re.compile(r'(?<![\w./-])env(?![\w-])')),
    ('printenv', re.compile(r'printenv')),
    ('Config.Env', re.compile(r'\.Config\.Env')),
    ('cat', re.compile(r'(?<![\w./-])cat(?![\w-])')),
    ('SELECT *', re.compile(r'(?i)select\s+\*')),
    ('row_to_json', re.compile(r'row_?to_?json')),
)
PROHIBITION = re.compile(r'禁|不得|不用|不取|不整|勿|拒绝|不')
CLAUSE_SPLIT = re.compile(r'[。；，]')
SENTENCE = re.compile(r'[。；\n]')
BACKTICK = re.compile(r'`([^`\n]+)`')


def read(path):
    assert path.is_file(), '模板不存在：%s' % path
    return path.read_text(encoding='utf-8')


class ProjectionRedactionTest(unittest.TestCase):

    def test_projection_outputs_survive_unchanged(self):
        for fixture in ('ZTMP len=10 state=set\nZNOTSET len=0 state=unset\nPATH len=18 state=set\n',
                        'API_KEY len=43 state=set\n',            # 敏感键名＋长度是投影元数据
                        'id | provider_id | enabled\n 1 | openai      | t\n',
                        'NODE_ENV\nPORT\nLOG_LEVEL\n', 'PATH=/usr/bin\n'):
            with self.subTest(fixture=fixture):
                self.assertEqual(fixture, redact(fixture))

    def test_full_dumps_leave_no_marker(self):
        cases = (
            ('\n'.join(['PATH=/usr/local/sbin', 'HOME=/root', 'API_KEY=%s-1' % M, 'TOKEN=%s-2' % M,
                        'SECRET=%s-3' % M, 'AUTH_KEY=%s-4' % M,
                        'DB_URL=postgres://svc:%s-5@db.invalid:5432/app' % M,
                        'UNKNOWN_ONE=' + JWT, 'UNKNOWN_TWO=' + SK_KEY, '']), ('PATH=/usr/local/sbin',)),
            (json.dumps([{'id': 1, 'email': 'a@example.invalid', 'password_hash': LONG_BLOB,
                          'provider': {'apiKey': M + '-6', 'token': M + '-7'}}]), ()),
            ('\n'.join(['ProxyHK = https, hk.example.invalid, 443, deployer, %s-8' % M,
                        'Group = select, DIRECT, ProxyHK', '[Keystore]', 'base64 = %s-9' % M, '']),
             ('Group = select, DIRECT, ProxyHK',)),
        )
        for fixture, keep in cases:
            with self.subTest(fixture=fixture[:40]):
                self.assertIn(M, fixture)
                out = redact(fixture)
                self.assertNotIn(M, out)
                for item in keep:
                    self.assertIn(item, out)


class TemplateScopeTest(unittest.TestCase):

    def test_declared_scope_anchors_present(self):
        for key, anchors in ANCHORS.items():
            body = read(TEMPLATE_FILES[key])
            for anchor in anchors:
                with self.subTest(file=key, anchor=anchor):
                    self.assertIn(anchor, body)

    def test_forbidden_primitives_only_in_prohibition_context(self):
        for key, path in TEMPLATE_FILES.items():
            body = read(path)
            for match in BACKTICK.finditer(body):
                for label, pattern in FORBIDDEN:
                    if pattern.search(match.group(1)):
                        with self.subTest(file=key, span=match.group(1), primitive=label):
                            self.assertRegex(CLAUSE_SPLIT.split(body[:match.start()])[-1], PROHIBITION)


# ── 读取侧：命令实际字段面 ⊆ 模板声明面（声明面从模板现读）──────────────────────
FULL, NARROW_ONLY, OPAQUE = '全量面', '只缩小记录集', '非字段读取形态'    # OPAQUE 不作断言
PLACEHOLDER = re.compile(r'^<[^>]+>$')
DECL_CUES = {
    'env': ('声明的指定键',),
    'config': ('声明的指定键', '声明的字段路径'),
    'db': ('人已确认的列白名单', '列名与类型元数据'),
    'platform': ('按字段',),
    'compose': ('配置持有方已有的投影接口',),
}
# 只有这些声明语可贡献具体字段名；其余只声明占位符（往白名单小句塞具体列名仍判越范围）
CONCRETE_CUES = dict(DECL_CUES, db=('列名与类型元数据',))
DECL_CUE_HOME = {'ops-runtime': ('env', 'config'), 'hub-instance': ('db',), 'hub-entry': ('platform',)}
CLS_PATTERNS = (
    ('compose', re.compile(r'^docker\s+compose\s+config\b')),
    ('env', re.compile(r'^docker\s+exec\b')),
    ('config', re.compile(r'^(?:awk\s+-F=|jq\b)')),
    ('db', re.compile(r'^select\s', re.I)),
    ('platform', re.compile(r'^(?:lh|minis-config)\s')),
)


class ReadScopeError(AssertionError):
    def __init__(self, category, detail=''):
        super().__init__('%s：%s' % (category, detail))
        self.category = category


def classify(span):
    return next((cls for cls, pattern in CLS_PATTERNS if pattern.match(span.strip())), None)


def parse_fields(cls, cmd):
    if cls == 'env':
        m = re.search(r'\bsh((?:\s+[A-Za-z_][A-Za-z0-9_]*)+)\s*$', cmd)
        return set(m.group(1).split()) if m else FULL
    if cls == 'config' and cmd.lstrip().startswith('jq'):
        m = re.search(r"'\{(.*?)\}'", cmd)
        return (set(re.findall(r'\.\s*[A-Za-z0-9_.]+', m.group(1))) or FULL) if m else FULL
    if cls == 'config':
        m = re.search(r'\$1\s*==\s*"([^"]+)"', cmd)
        if m:
            return {m.group(1)}
        return {'<键名>'} if re.search(r'print\s+\$1\b', cmd) else OPAQUE
    if cls == 'db':
        m = re.match(r'(?is)^select\s+(.*?)\s+from\b', cmd.strip())
        items = [t.strip() for t in m.group(1).split(',')] if m else ['*']
        return FULL if '*' in items else set(items)
    if cls == 'platform':
        m = re.search(r'--json(?:\s+([A-Za-z0-9_.,*<>/-]+))?', cmd)
        if m:
            return set(m.group(1).split(',')) if m.group(1) else FULL
        m = re.search(r'\bminis-config\s+get\s+(\S+)', cmd)
        if m:
            segs = [s for s in m.group(1).split('.') if s]
            return {segs[-1]} if len(segs) >= 3 else NARROW_ONLY     # 对象级＝只缩小记录集
        return OPAQUE
    return {'<解析性>'} if re.search(r'--(?:quiet|services|volumes|images)\b', cmd) else FULL


def snippets(body):
    """反引号片段与其所在小句（小句界＝。；换行）。"""
    return [(m.group(1), SENTENCE.split(body[:m.start()])[-1]) for m in BACKTICK.finditer(body)]


def declared_fields(cls, snips):
    """声明面：最近前置声明语属具体字段声明的同类命令所列字段（占位符不计）。"""
    out = set()
    for span, clause in snips:
        if classify(span) != cls:
            continue
        cue = max(DECL_CUES[cls], key=clause.rfind)
        if clause.rfind(cue) < 0 or cue not in CONCRETE_CUES[cls]:
            continue
        fields = parse_fields(cls, span)
        if isinstance(fields, set):
            out |= {t for t in fields if not PLACEHOLDER.match(t.strip())}
    return out


def check_read_scope(cls, cmd, declared):
    fields = parse_fields(cls, cmd)
    if fields is FULL:
        raise ReadScopeError('全量读取', cmd.strip()[:60])
    if fields is NARROW_ONLY:
        raise ReadScopeError('只缩小记录集，未做字段投影', cmd.strip()[:60])
    if fields is OPAQUE:
        return fields
    extra = {t for t in fields if not PLACEHOLDER.match(t.strip())} - set(declared)
    if extra:
        raise ReadScopeError('字段超出声明面', '、'.join(sorted(extra)))
    return fields


class ReadTemplateContractTest(unittest.TestCase):

    def test_declared_faces_exist(self):
        """防空转：声明语仍在，且每类声明面解析出字段。"""
        for key, classes in DECL_CUE_HOME.items():
            body = read(TEMPLATE_FILES[key])
            for cls in classes:
                with self.subTest(file=key, cls=cls):
                    for cue in DECL_CUES[cls]:
                        self.assertIn(cue, body)
                    self.assertTrue(declared_fields(cls, snippets(body)))

    def test_read_commands_within_declared_scope(self):
        for key, path in TEMPLATE_FILES.items():
            snips = snippets(read(path))
            for cls in sorted(DECL_CUES):
                declared = declared_fields(cls, snips)
                for span, clause in snips:
                    if classify(span) != cls:
                        continue
                    if parse_fields(cls, span) is FULL and PROHIBITION.search(clause):
                        continue                      # 禁止语境里的全量形态是反例
                    with self.subTest(file=key, span=span[:60]):
                        check_read_scope(cls, span, declared)


class ReadSideContractTest(unittest.TestCase):
    """四类来源：执行模板命令（离线夹具），输出字段与声明集合相等且标记消失；越范围按类别拒绝。"""

    def snippet(self, path, needle):
        for span, _ in snippets(read(path)):
            if needle in span:
                return span
        self.fail('模板中没有含 %r 的命令片段：%s' % (needle, path))

    def assert_rejected(self, cls, cmd, declared, category):
        with self.assertRaises(ReadScopeError) as caught:
            check_read_scope(cls, cmd, declared)
        self.assertEqual(category, caught.exception.category)

    def sh(self, cmd, *args, env=None):
        proc = subprocess.run(['sh', '-c', cmd, 'sh', *args], capture_output=True, text=True,
                              env=dict(env or {}, PATH='/usr/local/bin:/usr/bin:/bin'))
        self.assertEqual(0, proc.returncode, proc.stderr)
        return proc.stdout.strip()

    def tmpfile(self, text):
        handle = tempfile.NamedTemporaryFile('w', suffix='.conf', delete=False, encoding='utf-8')
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_env_read_scope(self):
        declared = declared_fields('env', snippets(read(OPS_RUNTIME)))
        cmd = self.snippet(OPS_RUNTIME, 'for k in "$@"')
        self.assertEqual(declared, parse_fields('env', cmd))
        out = self.sh(re.search(r"'([^']*)'", cmd).group(1), *sorted(declared),
                      env={'API_KEY': M + '-1', 'DB_PASSWORD': M + '-2'})
        self.assertEqual(declared, {line.split()[0] for line in out.splitlines()})
        self.assertNotIn(M, out)
        self.assert_rejected('env', "docker exec app sh -c '…' sh API_KEY DB_PASSWORD UNKNOWN_ONE",
                             declared, '字段超出声明面')

    def test_config_read_scope(self):
        length_cmd = self.snippet(OPS_RUNTIME, 'length(substr(')
        self.assertEqual({'KEY'}, parse_fields('config', length_cmd))
        path = self.tmpfile('KEY=aa=bbb\nOTHER=xx\n')          # 值含 `=` 时按第一个 `=` 后整段计长
        self.assertEqual('KEY 6', self.sh(length_cmd.replace('<文件>', path)))
        jq_cmd = self.snippet(OPS_RUNTIME, "jq '{port:")
        declared = parse_fields('config', jq_cmd)
        self.assertEqual({'.server.port', '.logging.level'}, declared)
        source = json.dumps({'server': {'port': 8080, 'admin_key': M + '-1'},
                             'logging': {'level': 'info', 'token': M + '-2'}, 'top': M + '-3'})
        out = self.sh(jq_cmd.replace('<文件>', self.tmpfile(source + '\n')))
        aliases = {part.split(':')[0].strip() for part in re.search(r"'\{([^}]*)\}'", jq_cmd).group(1).split(',')}
        self.assertEqual(aliases, set(json.loads(out)))
        self.assertNotIn(M, out)
        self.assert_rejected('config', "jq '.' <文件>", declared, '全量读取')
        self.assert_rejected('config', "jq '{port: .server.port, admin_key: .server.admin_key}' <文件>",
                             declared, '字段超出声明面')

    def test_db_read_scope(self):
        declared = declared_fields('db', snippets(read(HUB_INSTANCE)))
        self.assertTrue(declared)
        sql = self.snippet(HUB_INSTANCE, 'SELECT <列1>')
        for token, value in (('<列1>', 'id'), ('<列2>', 'name'), ('<表>', 'providers'),
                             ('<条件>', '1=1'), ('<n>', '10')):
            sql = sql.replace(token, value)
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.execute('CREATE TABLE providers (id INTEGER, name TEXT, api_key TEXT)')
        db.execute("INSERT INTO providers VALUES (1, 'kcne', ?)", (M + '-1',))
        cursor = db.execute(sql)
        self.assertEqual({'id', 'name'}, {d[0] for d in cursor.description})
        self.assertNotIn(M, str(cursor.fetchall()))
        self.assert_rejected('db', 'SELECT api_key FROM providers LIMIT 1', declared, '字段超出声明面')

    def test_platform_read_scope(self):
        declared = declared_fields('platform', snippets(read(HUB_ENTRY)))
        cmd = self.snippet(HUB_ENTRY, '--json content,name,description')
        self.assertEqual(declared, parse_fields('platform', cmd))
        record = {'id': 'skl_1', 'content': '…', 'name': 'n', 'description': 'd',
                  'raw': {'credentials': M + '-1'}, 'extra': M + '-2'}
        out = json.dumps({k: record[k] for k in parse_fields('platform', cmd)})
        self.assertEqual(declared, set(json.loads(out)))
        self.assertNotIn(M, out)
        self.assert_rejected('platform', 'lh skill view skl_1 --json content,name,description,raw',
                             declared, '字段超出声明面')
        self.assert_rejected('platform', 'minis-config get models --filter kcne', declared,
                             '只缩小记录集，未做字段投影')
        self.assert_rejected('platform', 'lh skill view skl_1 --json', declared, '全量读取')


if __name__ == '__main__':
    unittest.main()

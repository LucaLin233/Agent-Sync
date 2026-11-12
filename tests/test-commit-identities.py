#!/usr/bin/env python3
"""tools/check-commit-identities.py 的离线回归（identity 组定向运行，不入 full）。

真实 git 对象（按字节构造并直接写入对象库，可造畸形身份与伪造签名头）与 gpg
（测试内临时 ed25519 钥，非 web-flow）。真 web-flow 钥无法伪造，只在「验签结果」处打桩。
检查器多在进程内调用 main()，另留真实子进程用例守进程边界；同类矩阵串成一条链只跑一次。
无 gpg 时需要真实验签的用例跳过。所有检查器输出都断言不含夹具邮箱或任何 `@`。
身份多为合成值（example.invalid 保留域、`名@local` 本地地址），另含规则登记的两个外部身份；
不依赖本机 git 身份与网络。
"""
import contextlib
import hashlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools' / 'check-commit-identities.py'
LUNO = ('LUNO', 'luno@local')  # 现役形态：域名无点的本地地址
FORGE = ('FORGE', 'forge@local')
LENS = ('LENS', 'lens@local')
LIN = ('LIN student', '86354789+MiCat-S@users.noreply.github.com')
CLAUDE = ('Claude Opus 5.5', 'noreply@anthropic.com')
OTHER = ('someone', 'someone@example.invalid')
PLATFORM = ('GitHub', 'noreply@github.com')
SIGNER = 'Test Signer <test-signer@example.invalid>'
PLACEHOLDER = '[' + 'ADDR' + ']'
CURRENT_FPR = '968479A1AFF927E37D1A566BB5690EEEBB952194'
OLD_FPR = '5DE3E0509C47EA3CF04A42D34AEE18F83AFDEB23'  # 2024-01-16 过期的旧 web-flow 钥
FAKE_SIG = b'gpgsig -----BEGIN PGP SIGNATURE-----\n\n iQsynthfake\n -----END PGP SIGNATURE-----\n'
needs_gpg = unittest.skipIf(shutil.which('gpg') is None, '无 gpg')

_spec = importlib.util.spec_from_file_location('check_commit_identities', str(TOOL))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)


def rule_text(luno=LUNO[1], forge=FORGE[1], lens=LENS[1], lin=LIN):
    """与 delegation.md〈Git 提交署名〉段同形态的合成规则文件。"""
    return ('# 夹具规则\n\n## Git 提交署名\n\n'
            'Git提交按实际编写者设置 Author：LUNO 使用 `LUNO <%s>`，FORGE 使用 `FORGE <%s>`，LENS 使用 `LENS <%s>`。'
            '并登记 `%s <%s>`、`%s <%s>`。\n'
            '平台自动生成的合并提交保留平台身份。\n\n## 其他段\n\n不相关正文。\n'
            % ((luno, forge, lens) + lin + CLAUDE))


def ident(pair):
    return ('%s <%s>' % pair).encode('utf-8')


@contextlib.contextmanager
def in_dir(path):
    cwd = os.getcwd()
    os.chdir(str(path))
    try:
        yield
    finally:
        os.chdir(cwd)


def call_tool(argv, cwd, env=None):
    """进程内运行检查器 main(argv)：cwd、环境（env 给定时整份替换）与标准流同子进程口径。"""
    out, err = io.StringIO(), io.StringIO()
    with in_dir(cwd), mock.patch.dict(os.environ, env or {}, clear=env is not None), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = T.main(argv)
        except SystemExit as stop:
            code = stop.code
    return types.SimpleNamespace(returncode=code, stdout=out.getvalue(), stderr=err.getvalue())


# ── 测试内临时钥环（整轮共用）──
_HOMES, _CLEANUP, _TEMPLATE = {}, [], []
KEYGEN = {
    'valid': [('--quick-generate-key', SIGNER, 'ed25519', 'sign', '0')],
    # 主钥只作认证，由签名子钥签发
    'subkey': [('--quick-generate-key', SIGNER, 'ed25519', 'cert', '0'),
               ('--quick-add-key', None, 'ed25519', 'sign', '0')],
}


def gpg_env(home):
    return dict(os.environ, GNUPGHOME=str(home), LC_ALL='C')


def fingerprints(home):
    """→ (第一把主钥指纹, 第一把子钥指纹或 None)。"""
    proc = subprocess.run(('gpg', '--batch', '--with-colons', '--fingerprint'),
                          capture_output=True, env=gpg_env(home))
    if proc.returncode != 0:
        raise AssertionError('钥环不可读')
    found, last = {}, None
    for line in proc.stdout.decode('utf-8', 'replace').splitlines():
        field = line.split(':')
        if field[0] in ('pub', 'sub'):
            last = field[0]
        elif field[0] == 'fpr' and last and len(field) > 9:
            found.setdefault(last, field[9])
            last = None
    if 'pub' not in found:
        raise AssertionError('钥环内无主钥')
    return found['pub'], found.get('sub')


def gpg_home(kind):
    """→ (home, 主钥指纹, 子钥指纹或 None)。"""
    if kind not in _HOMES:
        home = tempfile.mkdtemp(prefix='ci-identity-gpg.')
        os.chmod(home, 0o700)
        _CLEANUP.append(home)
        for args in KEYGEN[kind]:
            args = tuple(fingerprints(home)[0] if a is None else a for a in args)
            proc = subprocess.run(('gpg', '--batch', '--passphrase', '') + args,
                                  capture_output=True, env=gpg_env(home))
            if proc.returncode != 0:
                raise unittest.SkipTest('测试钥生成失败')
        _HOMES[kind] = (home,) + fingerprints(home)
    return _HOMES[kind]


def gpg_sign(payload, home, faked=None):
    """对提交（不含 gpgsig 头）签名，返回 git 形态的 gpgsig 头块。"""
    argv = ['gpg', '--batch', '--yes', '--armor', '--detach-sign']
    if faked:
        argv += ['--faked-system-time', faked]
    proc = subprocess.run(argv, input=payload, capture_output=True, env=gpg_env(home))
    if proc.returncode != 0:
        raise AssertionError('夹具签名失败')
    armor = proc.stdout.rstrip(b'\n').split(b'\n')
    return b'gpgsig ' + armor[0] + b'\n' + b''.join(b' ' + line + b'\n' for line in armor[1:])


def tearDownModule():
    for home in _CLEANUP:
        with contextlib.suppress(OSError):
            subprocess.run(('gpgconf', '--kill', 'all'), capture_output=True, env=gpg_env(home))
        shutil.rmtree(home, True)
    for repo in _TEMPLATE:
        shutil.rmtree(str(repo.dir), True)


class Repo:
    """一次性仓库：空树＋手工构造的提交对象；无工作区、无身份配置。"""

    def __init__(self, template=None):
        self.dir = Path(tempfile.mkdtemp(prefix='ci-identity.'))
        self.rules = self.dir / 'rules.md'
        if template:  # 复制已初始化的模板，省掉每例 git init
            shutil.rmtree(str(self.dir))
            shutil.copytree(str(template.dir), str(self.dir))
            self.tree = template.tree
            return
        self.git('init', '-q', '-b', 'main', '--template=')
        self.tree = self.write(b'tree', b'')
        self.rules.write_text(rule_text(), encoding='utf-8')

    def write(self, kind, raw):
        """松散对象直接落库，等价 `git hash-object -w`，省一次 git 进程。"""
        data = b'%s %d\0' % (kind, len(raw)) + raw
        sha = hashlib.sha1(data).hexdigest()
        path = self.dir / '.git/objects' / sha[:2] / sha[2:]
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(zlib.compress(data))
        return sha

    def git(self, *args, input=b''):
        proc = subprocess.run(('git',) + args, cwd=str(self.dir), input=input, capture_output=True)
        if proc.returncode != 0:
            raise AssertionError('夹具 git %s 失败：%s' % (args, proc.stderr.decode('utf-8', 'replace')))
        return proc

    def commit(self, author, committer, message='subject\n', parents=(), gpgsig=False, sign=None):
        """gpgsig＝伪造签名头；sign＝True（valid 测试钥）或 (home, 假系统时间) 的真实签名。"""
        head = b'tree ' + self.tree.encode('ascii') + b'\n'
        head += b''.join(b'parent ' + p.encode('ascii') + b'\n' for p in parents)
        head += b'author ' + ident(author) + b' 1700000000 +0000\n'
        head += b'committer ' + ident(committer) + b' 1700000000 +0000\n'
        body = message.encode('utf-8')
        raw = head
        if gpgsig:
            raw += FAKE_SIG
        elif sign:
            home, faked = (gpg_home('valid')[0], None) if sign is True else sign
            raw += gpg_sign(head + b'\n' + body, home, faked)
        return self.write(b'commit', raw + b'\n' + body)

    def line(self, author=LUNO, committer=LUNO, **kw):
        """基线提交（表外身份，作 --base 不入范围）＋一个待检提交。"""
        base = self.commit(OTHER, OTHER)
        return base, self.commit(author, committer, parents=[base], **kw)

    def run(self, base, head, rules=True, allow_empty=False, extra=(), env=None, process=False):
        args = ['--base', str(base), '--head', str(head)]
        if rules:
            args += ['--rules', str(self.rules if rules is True else rules)]
        if allow_empty:
            args.append('--allow-empty')
        if not process:
            return call_tool(args + list(extra), self.dir, env)
        return subprocess.run([sys.executable, '-B', str(TOOL)] + args + list(extra), cwd=str(self.dir),
                              capture_output=True, text=True, encoding='utf-8', timeout=120, env=env)


class Base(unittest.TestCase):
    def setUp(self):
        if not _TEMPLATE:
            _TEMPLATE.append(Repo())
        self.repo = Repo(_TEMPLATE[0])
        self.addCleanup(shutil.rmtree, str(self.repo.dir), True)

    def verdict(self, proc, rc, *needles):
        out = proc.stdout + proc.stderr
        for secret in (LUNO[1], FORGE[1], LENS[1], LIN[1], CLAUDE[1], OTHER[1], PLATFORM[1],
                       PLACEHOLDER, '@'):
            self.assertNotIn(secret, out, '输出不得含邮箱、占位形态或 @')
        self.assertEqual(proc.returncode, rc, out)
        for needle in needles:
            self.assertIn(needle, out)

    def batch(self, cases):
        """[(标签, author, committer, message, rc, needles)] 串成一条链只跑一次检查器，每例只看
        自己那个提交的输出行：rc=0 不得报行，rc=1 须报行且含全部 needles。"""
        parent = base = self.repo.commit(OTHER, OTHER)
        shas = []
        for _label, author, committer, message, _rc, _needles in cases:
            parent = self.repo.commit(author, committer, message, [parent])
            shas.append(parent[:7])
        bad = any(case[4] for case in cases)
        proc = self.repo.run(base, parent)
        self.verdict(proc, 1 if bad else 0, *(() if bad else ('通过',)))
        for (label, _a, _c, _m, rc, needles), sha in zip(cases, shas):
            with self.subTest(label):
                lines = '\n'.join(x for x in proc.stdout.splitlines() if x.startswith(sha + ' '))
                self.assertEqual(bool(rc), bool(lines), lines)
                for needle in needles:
                    self.assertIn(needle, lines)

    def check(self, sha, allow_squash=False, verified=None):
        """直接调用 check_commit；verified 给定时打桩验签结果 → (['字段 类别'…], 豁免种类)。"""
        with contextlib.ExitStack() as stack:
            if verified is not None:
                stack.enter_context(mock.patch.object(T.WebFlow, 'verify', lambda _, s: verified))
            stack.enter_context(in_dir(self.repo.dir))
            problems, kind = T.check_commit(T.read_rules(self.repo.rules), sha, T.WebFlow(),
                                            allow_squash)
        return ['%s %s' % p for p in problems], kind

    def merge(self, committer=PLATFORM, message='Merge pull request\n', **kw):
        """双父合并；范围 first..merge 里另一个父提交身份合规，违规只可能来自合并提交本身。"""
        first, second = self.repo.line()
        return first, self.repo.commit(LUNO, committer, message, [first, second], **kw)


class PositiveTest(Base):
    def test_known_identities(self):
        # 含 LENS 制稿、FORGE 代提交与两个外部身份
        self.batch([('%s/%s' % (a[0], c[0]), a, c, 'subject\n', 0, ())
                    for a, c in ((LUNO, LUNO), (FORGE, FORGE), (FORGE, LUNO), (LENS, FORGE),
                                 (LIN, LIN), (CLAUDE, LENS))])

    def test_coauthor_allowed(self):
        self.batch([(pair[0], FORGE, FORGE, 'subject\n\nCo-authored-by: %s <%s>\n' % pair, 0, ())
                    for pair in (LUNO, LENS, LIN, CLAUDE)])

    def test_midbody_coauthor_not_parsed(self):
        # 同 git 口径：不在尾部 trailer 块里的同名行不参与解析
        base, head = self.repo.line(
            FORGE, FORGE, message='subject\n\nCo-authored-by: nobody <%s>\n\n尾段正文\n' % OTHER[1])
        self.verdict(self.repo.run(base, head), 0, '通过')


class PlatformTest(Base):
    """平台合并只凭「≥2 父＋平台提交者＋web-flow 验签通过」豁免。"""

    @needs_gpg
    def test_unverified_signature_not_exempt(self):
        for kw in ({}, {'gpgsig': True}, {'sign': True}):  # 无签名／伪造签名头／非 web-flow 钥真签名
            with self.subTest(**kw):
                first, merge = self.merge(**kw)
                self.verdict(self.repo.run(first, merge), 1, 'committer', '身份不在署名表内')

    def test_needs_platform_committer_and_two_parents(self):
        first, merge = self.merge(committer=OTHER, gpgsig=True)
        self.verdict(self.repo.run(first, merge), 1, 'committer')
        base, head = self.repo.line(LUNO, PLATFORM, gpgsig=True)  # 单父、未给 --allow-squash
        self.verdict(self.repo.run(base, head), 1, 'committer')

    def test_platform_still_checks_coauthor(self):
        _, merge = self.merge(gpgsig=True, message='Merge\n\nCo-authored-by: someone <%s>\n' % OTHER[1])
        problems, kind = self.check(merge, verified=True)
        self.assertEqual(kind, 'platform')
        self.assertIn('Co-authored-by#1 身份不在署名表内', problems)

    def test_gpg_unavailable_fails_closed(self):
        first, merge = self.merge(gpgsig=True)
        bare = Path(tempfile.mkdtemp(prefix='ci-identity-nogpg.'))  # PATH 里只有 git
        self.addCleanup(shutil.rmtree, str(bare), True)
        (bare / 'git').symlink_to(shutil.which('git'))
        self.verdict(self.repo.run(first, merge, env=dict(os.environ, PATH=str(bare))), 2, '缺少 gpg')


class SquashTest(Base):
    """--allow-squash（仅 push 事件）：单父＋平台提交者＋验签通过，且 Co-authored-by 非空合规。"""

    def inspect(self, message, parents=1, allow_squash=True):
        tail = [self.repo.commit(OTHER, OTHER) for _ in range(parents)]
        sha = self.repo.commit(LUNO, PLATFORM, message, tail, gpgsig=True)
        return self.check(sha, allow_squash, verified=True)

    def test_rules(self):
        co = 'Co-authored-by: %s <%s>\n'
        F, N, L, X = co % FORGE, co % LUNO, co % LENS, co % OTHER
        for label, message, kw, want in (
                ('合规尾行', F, {}, ('squash', [])),
                ('LENS 尾行', L, {}, ('squash', [])),
                ('同一身份重复只算一次', F + F, {}, ('squash', [])),
                ('尾行可与 Author 相同', F + N, {}, ('squash', [])),
                ('缺尾行', '正文\n', {}, ('squash', ['Co-authored-by squash 提交缺少 Co-authored-by'])),
                ('尾行身份不在表内', X, {}, ('squash', ['Co-authored-by#1 身份不在署名表内'])),
                ('未给 flag 按普通提交', F, {'allow_squash': False}, ('', ['committer 身份不在署名表内'])),
                ('双父是平台合并', F, {'parents': 2}, ('platform', [])),
                ('平台合并无需尾行', '正文\n', {'parents': 2}, ('platform', []))):
            with self.subTest(label):
                problems, kind = self.inspect('squash subject\n\n' + message, **kw)
                self.assertEqual((kind, problems), want)

    @needs_gpg
    def test_flag_does_not_bypass_signature(self):
        base, head = self.repo.line(LUNO, PLATFORM, gpgsig=True,
                                    message='squash\n\nCo-authored-by: FORGE <%s>\n' % FORGE[1])
        self.verdict(self.repo.run(base, head, extra=('--allow-squash',)), 1, 'committer')
        self.verdict(self.repo.run(base, head), 1, 'committer')


def validsig(fpr, primary=None, short=False):
    """git verify-commit --raw 形态的状态输出（gpg 对过期钥的好签名也报 VALIDSIG）。"""
    tail = b'' if short else b' ' + (primary or fpr).encode('ascii')
    return (b'[GNUPG:] NEWSIG\n[GNUPG:] VALIDSIG ' + fpr.encode('ascii')
            + b' 2026-11-05 1793868808 0 4 0 1 8 00' + tail + b'\n')


class WebflowGateTest(unittest.TestCase):
    """verify() 判据：只认退出码 0，且 VALIDSIG 末位主钥指纹须在固定集合内。"""

    def verify_with(self, rc, text):
        wf = T.WebFlow()
        wf.home = tempfile.mkdtemp(prefix='ci-identity-wf.')
        wf.ready = True
        self.addCleanup(shutil.rmtree, wf.home, True)
        real = T.git
        fake = lambda *a, **kw: (rc, b'', text) if a[0] == 'verify-commit' else real(*a, **kw)
        with mock.patch.object(T, 'git', fake):
            return wf.verify('0' * 40)

    def test_verdicts(self):
        for label, rc, text, want in (
                ('rc=0 正控', 0, validsig(CURRENT_FPR), True),
                ('rc=1 即使有 VALIDSIG', 1, validsig(CURRENT_FPR), False),
                ('rc=2 即使有 VALIDSIG', 2, validsig(CURRENT_FPR), False),
                ('末位主钥是旧钥', 0, validsig(CURRENT_FPR, OLD_FPR), False),
                ('缺末位主钥指纹', 0, validsig(CURRENT_FPR, short=True), False)):
            with self.subTest(label):
                self.assertIs(self.verify_with(rc, text), want)

    def test_primary_fingerprints_ignore_subkeys(self):
        colons = b'pub:-:255:22:K:\nfpr:::::::::AAA:\nsub:-:255:22:S:\nfpr:::::::::BBB:\npub:x\nfpr:::::::::CCC:\n'
        self.assertEqual(T.primary_fingerprints(colons), {'AAA', 'CCC'})


@needs_gpg
class RealSignatureTest(Base):
    """测试内临时钥的真实签名（指纹临时放进固定集合）。"""

    def inspect(self, home, fprs, faked=None):
        _, merge = self.merge(sign=(home, faked))
        wf = T.WebFlow()
        wf.home, wf.ready = home, True
        with mock.patch.object(T, 'WEBFLOW_FINGERPRINTS', frozenset(fprs)), in_dir(self.repo.dir):
            verified = wf.verify(merge)
            problems, kind = T.check_commit(T.read_rules(self.repo.rules), merge, wf)
        return merge, verified, [field for field, _ in problems], kind

    def test_valid_key_in_set_exempt(self):
        home, primary, _ = gpg_home('valid')
        _, verified, fields, kind = self.inspect(home, (CURRENT_FPR, primary))
        self.assertEqual((verified, kind, fields), (True, 'platform', []))

    def test_subkey_signature_judged_by_primary(self):
        home, primary, sub = gpg_home('subkey')
        self.assertNotEqual(sub, primary)
        _, verified, fields, kind = self.inspect(home, (primary,))
        self.assertEqual((verified, kind, fields), (True, 'platform', []))
        _, verified, fields, kind = self.inspect(home, (sub,))
        self.assertEqual((verified, kind), (False, ''))
        self.assertIn('committer', fields)


class NegativeIdentityTest(Base):
    def test_identity_mismatch(self):
        cases = [(('LUNO', OTHER[1]), LUNO, 'author'),
                 (('FORGE', LUNO[1]), LUNO, 'author'),
                 (('LENS', LUNO[1]), LUNO, 'author'),
                 (LUNO, ('LUNO', OTHER[1]), 'committer'),
                 ((LIN[0], LUNO[1]), LUNO, 'author'),
                 ((CLAUDE[0], 'claude@local'), LUNO, 'author')]
        # 大小写敏感：只改名字大小写，邮箱仍是正确地址
        cases += [((n, FORGE[1]), LUNO, 'author') for n in ('forge', 'Forge')]
        cases += [((n, LUNO[1]), FORGE, 'author') for n in ('luno', 'Luno')]
        cases += [((n, LENS[1]), FORGE, 'author') for n in ('lens', 'Lens', 'leNs')]
        self.batch([('%s/%s' % (a[0], c[0]), a, c, 'subject\n', 1, (field, '身份不在署名表内'))
                    for a, c, field in cases])

    def test_replace_ref_cannot_launder(self):
        base = self.repo.commit(OTHER, OTHER)
        good = self.repo.commit(LUNO, LUNO, parents=[base])
        bad = self.repo.commit(OTHER, OTHER, parents=[base])
        self.repo.git('replace', bad, good)
        self.verdict(self.repo.run(base, bad), 1, 'author', '身份不在署名表内')

    def test_grafts_cannot_hide_commit(self):
        base = self.repo.commit(OTHER, OTHER)
        bad = self.repo.commit(OTHER, OTHER, parents=[base])
        head = self.repo.commit(LUNO, LUNO, parents=[bad])
        info = self.repo.dir / '.git' / 'info'
        info.mkdir(exist_ok=True)
        (info / 'grafts').write_text('%s %s\n' % (head, base), encoding='utf-8')
        self.verdict(self.repo.run(base, head), 1, 'author', '身份不在署名表内')


class TrailerTest(Base):
    def test_trailers(self):
        L, X = '%s <%s>' % LUNO, '%s <%s>' % OTHER
        bad = ('Co-authored-by#1', '身份不在署名表内')
        self.batch([(label, FORGE, FORGE, 'subject\n\n' + trailers, rc, needles) for label, trailers, rc, needles in (
                ('畸形值', 'Co-authored-by: FORGE\n', 1, ('Co-authored-by#1', '格式非')),
                ('身份不在表内', 'Co-authored-by: LUNO <%s>\n' % OTHER[1], 1, bad),
                ('普通提交与 Author 相同', 'Co-authored-by: FORGE <%s>\n' % FORGE[1], 1, ('与 Author 相同',)),
                ('同一身份重复只算一次', 'Co-authored-by: %s\nCo-authored-by: %s\n' % (L, L), 0, ()),
                ('无空格分隔', 'Co-authored-by:%s\n' % L, 0, ()),
                ('无空格分隔·非法', 'Co-authored-by:%s\n' % X, 1, bad),
                ('Tab 分隔', 'Co-authored-by:\t%s\n' % L, 0, ()),
                ('Tab 分隔·非法', 'Co-authored-by:\t%s\n' % X, 1, bad),
                ('混合 trailer', 'Co-authored-by: %s\nSigned-off-by: %s\nAcked-by: %s\n' % (L, L, X), 0, ()),
                ('混合 trailer·非法', 'Signed-off-by: %s\nAcked-by: %s\nCo-authored-by: %s\n' % (L, X, X), 1, bad),
                ('续行并入值后判违规', 'Co-authored-by: %s\n 继续\n' % L, 1, ('Co-authored-by#1',)))])


class RulesTest(Base):
    def run_rules(self, text=None, path=True, process=False):
        if text is not None:
            self.repo.rules.write_text(text, encoding='utf-8')
        base, head = self.repo.line()
        return self.repo.run(base, head, rules=path, process=process)

    def test_unreadable_or_missing_section(self):
        self.verdict(self.run_rules(path=self.repo.dir / ('missing.' + OTHER[1])), 2, '规则文件不可读')
        (self.repo.dir / 'bad.md').write_bytes(b'## Git \xff\xfe 1\n')
        self.verdict(self.run_rules(path=self.repo.dir / 'bad.md'), 2, '规则文件不是 UTF-8')
        self.verdict(self.run_rules('# 夹具规则\n\n## 其他段\n\n无署名段。\n'), 2, '缺少')

    def test_identity_missing_or_duplicated(self):
        anchor = '平台自动生成的合并提交保留平台身份。'
        for pair in (LUNO, LENS, LIN):
            with self.subTest(dup=pair[0]):
                text = rule_text().replace(anchor, anchor + '\n\n`%s <%s>`' % pair, 1)
                self.verdict(self.run_rules(text), 2, '身份重复')
        text = rule_text().replace('，LENS 使用 `LENS <%s>`' % LENS[1], '', 1)
        self.assertNotEqual(text, rule_text())
        self.verdict(self.run_rules(text), 2, '缺少 LENS')
        # 只认完整声明：带前缀的名字不算登记名
        self.verdict(self.run_rules(rule_text(lin=('NotLIN student', LIN[1]))), 2, '缺少 LIN student')

    def test_two_identities_same_email(self):
        for a, b in ((LUNO, FORGE), (LUNO, LENS), (FORGE, LENS)):
            with self.subTest(a=a[0], b=b[0]):
                self.verdict(self.run_rules(rule_text(**{a[0].lower(): b[1]})), 2, '同一邮箱')

    def test_malformed_values_not_normalized(self):
        values = [{'luno': PLACEHOLDER}, {'forge': PLACEHOLDER}, {'luno': 'address'}]
        values += [{'luno': v % LUNO[1]} for v in (' %s', '%s ', ' %s ')]  # 两侧空白不 strip
        for kw in values:
            with self.subTest(**kw):
                self.verdict(self.run_rules(rule_text(**kw)), 2, '形态非法')

    def test_rule_change_takes_effect(self):  # 真实子进程：守住 0／1 退出码与 stdout 的进程边界
        self.verdict(self.run_rules(process=True), 0, '通过')
        self.verdict(self.run_rules(rule_text(luno=OTHER[1]), process=True), 1, 'author')


class EnvironmentTest(Base):
    def test_bad_rev_not_echoed(self):
        base, _ = self.repo.line()
        for b, h in (('deadbeef', base), (base, 'x' + OTHER[1])):
            with self.subTest(base=b, head=h):
                self.verdict(self.repo.run(b, h), 2, 'rev 无效或不是提交')

    def test_empty_range(self):
        base, _ = self.repo.line()
        self.verdict(self.repo.run(base, base), 2, '空范围')
        self.verdict(self.repo.run(base, base, allow_empty=True), 0, '空范围')

    def test_bad_arguments_not_echoed(self):  # 真实子进程：守住参数错误 rc=2 与 stderr 的进程边界
        for argv in (['--bogus', OTHER[1]], ['--base', 'HEAD']):
            with self.subTest(argv=argv):
                proc = subprocess.run([sys.executable, '-B', str(TOOL)] + argv, cwd=str(self.repo.dir),
                                      capture_output=True, text=True, encoding='utf-8', timeout=120)
                self.verdict(proc, 2, '参数无效')

    def test_shallow_clone(self):
        base, head = self.repo.line()
        self.repo.git('update-ref', 'refs/heads/main', head)
        dest = Path(tempfile.mkdtemp(prefix='ci-identity-shallow.')) / 'clone'
        self.addCleanup(shutil.rmtree, str(dest.parent), True)
        subprocess.run(('git', 'clone', '-q', '--depth', '1', 'file://' + str(self.repo.dir),
                        str(dest)), capture_output=True, check=True)
        proc = call_tool(['--base', base, '--head', head, '--rules', str(self.repo.rules)], dest)
        self.verdict(proc, 2, '浅克隆')


if __name__ == '__main__':
    unittest.main()

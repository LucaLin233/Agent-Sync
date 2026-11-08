#!/usr/bin/env python3
"""tools/check-commit-identities.py 的离线回归（identity 组定向运行，不入 full）。

真实 git 对象（hash-object 按字节构造，可造畸形身份与伪造签名头）、真实子进程与 gpg
（测试内临时 ed25519 钥，非 web-flow）。真 web-flow 钥无法伪造，只在「验签结果」处打桩。
无 gpg 时需要真实验签的用例跳过。所有子进程输出都断言不含夹具邮箱或任何 `@`。
身份均为合成值（example.invalid 保留域、`名@local` 本地地址），不依赖本机 git 身份与网络。
"""
import contextlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools' / 'check-commit-identities.py'
LUNO = ('LUNO', 'luno@local')  # 现役形态：域名无点的本地地址
FORGE = ('FORGE', 'forge@local')
LENS = ('LENS', 'lens@local')
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


def rule_text(luno=LUNO[1], forge=FORGE[1], lens=LENS[1]):
    """与 delegation.md〈Git 提交署名〉段同形态的合成规则文件。"""
    return ('# 夹具规则\n\n## Git 提交署名\n\n'
            'Git提交按实际编写者设置 Author：LUNO 使用 `LUNO <%s>`，FORGE 使用 `FORGE <%s>`，LENS 使用 `LENS <%s>`。\n'
            '平台自动生成的合并提交保留平台身份。\n\n## 其他段\n\n不相关正文。\n' % (luno, forge, lens))


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


# ── 测试内临时钥环（整轮共用）──
_HOMES, _CLEANUP, _TEMPLATE = {}, [], []
KEYGEN = {
    'valid': [('--quick-generate-key', SIGNER, 'ed25519', 'sign', '0')],
    # 假系统时间回到 2024-01-01 生成、1 天有效：现下已过期
    'expired': [('--faked-system-time', '20240101T000000', '--quick-generate-key', SIGNER,
                 'ed25519', 'sign', '1d')],
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
        if template:  # 复制已初始化的模板，省掉每例 git init／mktree
            shutil.rmtree(str(self.dir))
            shutil.copytree(str(template.dir), str(self.dir))
            self.tree = template.tree
            return
        self.git('init', '-q', '-b', 'main')
        self.tree = self.git('mktree').stdout.strip().decode('ascii')
        self.rules.write_text(rule_text(), encoding='utf-8')

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
        return self.git('hash-object', '-t', 'commit', '-w', '--stdin',
                        input=raw + b'\n' + body).stdout.strip().decode('ascii')

    def line(self, author=LUNO, committer=LUNO, **kw):
        """基线提交（表外身份，作 --base 不入范围）＋一个待检提交。"""
        base = self.commit(OTHER, OTHER)
        return base, self.commit(author, committer, parents=[base], **kw)

    def run(self, base, head, rules=True, allow_empty=False, extra=(), env=None):
        args = [sys.executable, '-B', str(TOOL), '--base', str(base), '--head', str(head)]
        if rules:
            args += ['--rules', str(self.rules if rules is True else rules)]
        if allow_empty:
            args.append('--allow-empty')
        return subprocess.run(args + list(extra), cwd=str(self.dir), capture_output=True,
                              text=True, encoding='utf-8', timeout=120, env=env)


class Base(unittest.TestCase):
    def setUp(self):
        if not _TEMPLATE:
            _TEMPLATE.append(Repo())
        self.repo = Repo(_TEMPLATE[0])
        self.addCleanup(shutil.rmtree, str(self.repo.dir), True)

    def verdict(self, proc, rc, *needles):
        out = proc.stdout + proc.stderr
        for secret in (LUNO[1], FORGE[1], LENS[1], OTHER[1], PLATFORM[1], PLACEHOLDER, '@'):
            self.assertNotIn(secret, out, '输出不得含邮箱、占位形态或 @')
        self.assertEqual(proc.returncode, rc, out)
        for needle in needles:
            self.assertIn(needle, out)

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
        # 含 LENS 制稿、FORGE 代提交
        for author, committer in ((LUNO, LUNO), (FORGE, FORGE), (FORGE, LUNO), (LENS, FORGE)):
            with self.subTest(author=author[0], committer=committer[0]):
                base, head = self.repo.line(author, committer)
                self.verdict(self.repo.run(base, head), 0, '通过')

    def test_coauthor_allowed(self):
        for pair in (LUNO, LENS):
            with self.subTest(pair=pair[0]):
                base, head = self.repo.line(
                    FORGE, FORGE, message='subject\n\nCo-authored-by: %s <%s>\n' % pair)
                self.verdict(self.repo.run(base, head), 0, '通过')

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

    def test_only_current_key_trusted(self):
        self.assertEqual(T.WEBFLOW_FINGERPRINTS, frozenset((CURRENT_FPR,)))

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

    def test_expired_key_rejected_even_if_trusted(self):
        home, primary, _ = gpg_home('expired')
        merge, verified, fields, kind = self.inspect(home, (CURRENT_FPR, primary), '20240101T010000')
        # 事实前提：gpg 对过期钥的好签名同时给出 VALIDSIG 与非零退出码
        proc = subprocess.run(('git', 'verify-commit', '--raw', merge), cwd=str(self.repo.dir),
                              capture_output=True, env=gpg_env(home))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(b'VALIDSIG', proc.stderr)
        self.assertEqual((verified, kind), (False, ''))
        self.assertIn('committer', fields)

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
                 (LUNO, ('LUNO', OTHER[1]), 'committer')]
        # 大小写敏感：只改名字大小写，邮箱仍是正确地址
        cases += [((n, FORGE[1]), LUNO, 'author') for n in ('forge', 'Forge')]
        cases += [((n, LUNO[1]), FORGE, 'author') for n in ('luno', 'Luno')]
        cases += [((n, LENS[1]), FORGE, 'author') for n in ('lens', 'Lens', 'leNs')]
        for author, committer, field in cases:
            with self.subTest(author=author[0], committer=committer[0]):
                base, head = self.repo.line(author, committer)
                self.verdict(self.repo.run(base, head), 1, field, '身份不在署名表内')

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
        for label, trailers, rc, needles in (
                ('畸形值', 'Co-authored-by: FORGE\n', 1, ('Co-authored-by#1', '格式非')),
                ('身份不在表内', 'Co-authored-by: LUNO <%s>\n' % OTHER[1], 1, bad),
                ('普通提交与 Author 相同', 'Co-authored-by: FORGE <%s>\n' % FORGE[1], 1, ('与 Author 相同',)),
                ('同一身份重复只算一次', 'Co-authored-by: %s\nCo-authored-by: %s\n' % (L, L), 0, ('通过',)),
                ('无空格分隔', 'Co-authored-by:%s\n' % L, 0, ('通过',)),
                ('无空格分隔·非法', 'Co-authored-by:%s\n' % X, 1, bad),
                ('Tab 分隔', 'Co-authored-by:\t%s\n' % L, 0, ('通过',)),
                ('Tab 分隔·非法', 'Co-authored-by:\t%s\n' % X, 1, bad),
                ('混合 trailer', 'Co-authored-by: %s\nSigned-off-by: %s\nAcked-by: %s\n' % (L, L, X), 0, ('通过',)),
                ('混合 trailer·非法', 'Signed-off-by: %s\nAcked-by: %s\nCo-authored-by: %s\n' % (L, X, X), 1, bad),
                ('续行并入值后判违规', 'Co-authored-by: %s\n 继续\n' % L, 1, ('Co-authored-by#1',))):
            with self.subTest(label):
                base, head = self.repo.line(FORGE, FORGE, message='subject\n\n' + trailers)
                self.verdict(self.repo.run(base, head), rc, *needles)


class RulesTest(Base):
    def run_rules(self, text=None, path=True):
        if text is not None:
            self.repo.rules.write_text(text, encoding='utf-8')
        base, head = self.repo.line()
        return self.repo.run(base, head, rules=path)

    def test_unreadable_or_missing_section(self):
        self.verdict(self.run_rules(path=self.repo.dir / ('missing.' + OTHER[1])), 2, '规则文件不可读')
        (self.repo.dir / 'bad.md').write_bytes(b'## Git \xff\xfe 1\n')
        self.verdict(self.run_rules(path=self.repo.dir / 'bad.md'), 2, '规则文件不是 UTF-8')
        self.verdict(self.run_rules('# 夹具规则\n\n## 其他段\n\n无署名段。\n'), 2, '缺少')

    def test_identity_missing_or_duplicated(self):
        anchor = '平台自动生成的合并提交保留平台身份。'
        for pair in (LUNO, FORGE, LENS):
            with self.subTest(dup=pair[0]):
                text = rule_text().replace(anchor, anchor + '\n\n%s <%s>' % pair, 1)
                self.verdict(self.run_rules(text), 2, '身份重复')
        text = rule_text().replace('，LENS 使用 `LENS <%s>`' % LENS[1], '', 1)
        self.assertNotEqual(text, rule_text())
        self.verdict(self.run_rules(text), 2, '缺少 LENS')

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

    def test_rule_change_takes_effect(self):
        self.verdict(self.run_rules(), 0, '通过')
        self.verdict(self.run_rules(rule_text(luno=OTHER[1])), 1, 'author')


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

    def test_bad_arguments_not_echoed(self):
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
        proc = subprocess.run([sys.executable, '-B', str(TOOL), '--base', base, '--head', head,
                               '--rules', str(self.repo.rules)], cwd=str(dest),
                              capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.verdict(proc, 2, '浅克隆')


if __name__ == '__main__':
    unittest.main()

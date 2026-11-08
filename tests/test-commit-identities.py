#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test-commit-identities.py —— tools/check-commit-identities.py 的离线回归。

成本例外（负责人 LUNO 2026-11-05 批准）：真实 Git 对象、进程、gpg 与浅克隆回归；iSH 实测约 18 秒／55 例（r3 为 51 例，r2 为 45 例，r1 为 31 例）。
保留真实边界，不降级为 mock；仅定向运行（identity 组）、不入 full。

单文件预算例外（发布者 LUNO 2026-11-05 批准）：超过 `test-authoring.md` 的 20,480 B；
UTF-8 原始字节数按 `wc -c < tests/test-commit-identities.py` 现读。环境：iSH／Alpine
3.21.0／aarch64；实测 `group identity` 55 例通过、17 s。理由：同族共用真实 Git／gpg
夹具，集中维护全部身份与签名边界。降级路径：仅 identity 定向运行、不入 full；若不接受体积
超额，另审保持完整断言与真实边界的同族拆分方案，不删例、不以 mock 替换真实边界、不缩跑。

单文件预算例外续登（2026-11-06，批准者为用户；本批 S1 并集去重用例）：本批在上一轮
42,537 B 基础上增加 1,736 B 至 44,273 B（`wc -c` 实测，UTF-8 原始字节；预算 20,480 B），
用例入口数 64（`rg -c '^\s+def test_'` 现读）。增量为 S1 的正负控三条（squash 去重、
squash 尾行等于 Author、平台合并无需作者行）与普通提交去重正控改写。降级路径同上：
仅 identity 定向运行、不入 full，不删例。环境与耗时同下条实测。

本批（r4，公开快照链 chain2，2026-11-06）体积与净差续登（批准者为用户；覆盖本批改动的四个
测试文件）：基线 `df54a93` → r4 实测（`wc -c`，UTF-8 原始字节；**本段自身字节已计入**本文件与
`tests/` 合计）：本文件 39,026 → 45,638 B（+6,612，S1 并集去重用例）；`test-surge-scripts.py`
192,180 → 199,974 B（+7,794，G5 两态断言与取件后另跑分档）；`test-deploy-skill.py` 263,769 →
270,231 B（+6,462，S3 正负控与取件声明夹具）；`test-check-rules.sh` 29,015 → 30,851 B
（+1,836，G2 豁免反例表驱动）；`tests/` 合计 624,784 → 647,488 B（**+22,704**）。本文件与
`test-surge-scripts.py` 均超 20,480 B 预算，按上条例外续用，不删例、不以 mock 或缩跑换速度；
**`test-surge-scripts.py` 在 `full` 常跑集**（`tests/run-tests.sh` 用例表第 5 列＝1），本文件
第 5 列＝0、**不在 `full`**，仅 identity 定向运行；体积例外不等于退出常跑。
该合计明显高于用户批准时告知的约 3.5 KB：本批按 LENS 最小减量方案只压了 gate 反例（−566 B）
与 surge 同源断言，其余增量是 S1／S3／G5 覆盖本身，减体积只能减覆盖——是否接受由用户裁定。
降级路径：只跑 `group identity`／`group surge` 定向回归，不删判据。

本批（LENS 署名，基线 `8813c1c`）体积与净差（本机实测 `wc -c`，UTF-8 原始字节）：本文件 45,638 → 48,910 B（+3,272）；用例入口 64 → 70（`rg -c '^\s+def test_'` 现读；新增 6 个方法、改 2 个既有方法体，旧 `test_lowercase_name` 未改）。发布者已按「同族增量 ≤5,120 B」原则允许本批必要同族增量，本批同族增量 3,272 B 在限内；不新增常跑项，本文件第 5 列仍为 0、仅 identity 定向运行。降级路径同上：只跑 `group identity` 定向回归，不删例、不以 mock 替换真实边界。

判据（每条都断言**可复核的退出码／输出事实**，不做源码计数对账）：
  1 正控：LUNO｜LUNO、FORGE｜FORGE、FORGE 作者＋LUNO 提交、LENS 作者＋FORGE 代提交、
    合法 `Co-authored-by`（LUNO／LENS 两种共同作者）、`--allow-empty` 空范围一律 rc=0。
  2 平台合并**只凭可信签名豁免**：假签名头、无签名、真签名但签发者不是 web-flow 钥、
    单父、committer 非 `GitHub` → 均 rc=1；真实 GitHub 平台合并提交（仓库内 `3ca8abd`
    原始对象，运行时可得才跑）→ rc=0 且报 `platform`；platform 分支仍核对 `Co-authored-by`。
    验签**只认退出码**：指纹在固定集合内、输出含 `VALIDSIG`，但 rc=1／rc=2 → 不豁免
    （rc=0 同输出为豁免正控）；测试内临时钥的**真实**签名（有效钥→豁免正控；过期钥
    → rc≠0 且按普通提交拒绝，即使其指纹临时放进集合）；旧钥指纹已不在固定集合内。
  3 身份负控：错误邮箱、`FORGE` 名配 LUNO 邮箱、`LENS` 名配 LUNO 邮箱、
    LENS 作者名大小写变体（`lens`／`Lens`／`leNs`，邮箱仍为 LENS 正确地址，单故障注入）、
    小写 `forge`／`Luno`（大小写敏感）、正确 Author＋错误 Committer → rc=1 且报对应字段。
  4 尾部署名负控：畸形（无 `<…>`）、身份不在表内 → rc=1；普通提交的尾行与 Author 相同 → rc=1；
    同一身份的重复尾行按并集去重 → rc=0。squash 提交另有 4b：尾行可与 Author 相同、重复按去重。
    无空格／Tab 分隔仍能解析（合法身份 rc=0、非法身份 rc=1）；续行与混合 trailer 下
    畸形值不回退为「无签名」而是判违规；正文中段（非尾部 trailer 块）的同一行不参与解析，
    与 git `interpret-trailers` 口径一致。
  5 规则单真源：规则文件缺失／缺〈Git 提交署名〉段／身份重复（规则登记的每个精确身份逐个）／规则登记的精确身份任意两者
    同邮箱（LUNO×FORGE、LUNO×LENS、FORGE×LENS）／任一登记身份缺失／方括号占位形态／
    邮箱两侧带空白 → rc=2；现役身份是不可路由的本地地址（域名无点）须被接受；
    且**不回退**（不读环境或 git config）；另证规则改动即时生效（无缓存、无上次身份沿用）。
  6 环境负控：无效 rev、空范围（未给 `--allow-empty`）→ rc=2；浅克隆 → rc=2。
    历史改写不可绕过：`git replace` 与 `info/grafts` 均不影响判定（仍 rc=1）。
  7 秘密面：全部用例的输出（stdout＋stderr）**不得**出现任何夹具邮箱、占位形态或 `@`；
    参数错误／路径错误／rev 错误三条路径亦不例外（argparse 已改为固定文案）。

夹具**绝大部分**为合成身份（`example.invalid` 保留域，与任何真实署名无关）。例外两项：真实
平台合并提交一例；以及 2 个**准确公开身份** `Claude Opus 5.5`、`LIN student`（名字与邮箱逐字节
取自原公开 commit meta，用于字节级精确匹配，**不得据此推断其实际模型或实际署名来源**）。
提交对象用 `hash-object -t commit -w` 按字节手工构造，故可覆盖畸形身份、伪造签名头；
真实签名用测试内临时生成的 ed25519 钥（非 web-flow）。不依赖本机 git 身份与网络。
"""
import importlib.util
from itertools import combinations
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools' / 'check-commit-identities.py'
LUNO = ('LUNO', 'luno@local')
FORGE = ('FORGE', 'forge@local')
LENS = ('LENS', 'lens@local')
OTHER = ('someone', 'someone@example.invalid')
PLATFORM = ('GitHub', 'noreply@github.com')
SIGNER = 'Test Signer <test-signer@example.invalid>'
PLACEHOLDER = '[' + 'ADDR' + ']'
# 真实 GitHub 平台合并提交（原始对象只读，不入库夹具文件：其 author 行含用户真实地址）。
# 本公开快照仓库为无历史快照，该对象不存在，HistoryTest 因此永久 skip；实证见旧私有 LucaLin233/Agent。
REAL_MERGE = '3ca8abd3033568e5394f62b9134081fda6b2f696'
# web-flow 主钥指纹：现用钥（唯一被信任）与 2024-01-16 已过期的旧钥（不信任）
CURRENT_FPR = '968479A1AFF927E37D1A566BB5690EEEBB952194'
OLD_FPR = '5DE3E0509C47EA3CF04A42D34AEE18F83AFDEB23'
_KEYRING = {}


def load_tool():
    """把检查器当模块载入（只为给密码学边界打桩，不替代子进程级回归）。"""
    spec = importlib.util.spec_from_file_location('check_commit_identities', str(TOOL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod



# 规则登记的外部身份夹具：**literal 期望**，不从生产 NAMES 反推。
EXTERNAL = (('LIN student', '86354789+MiCat-S@users.noreply.github.com'), ('Claude Opus 5.5', 'noreply@anthropic.com'))


def rule_text(luno=LUNO[1], forge=FORGE[1], lens=LENS[1], extra=None):
    """合成规则文件：与 delegation.md〈Git 提交署名〉段同形态；身份为**literal 期望**。"""
    if extra is None:
        extra = EXTERNAL
    decl = ''.join('，%s 使用 `%s <%s>`' % (n, n, v) for n, v in extra)
    return ('# 夹具规则\n\n## Git 提交署名\n\n'
            'Git提交按实际编写者设置 Author：LUNO 使用 `LUNO <%s>`，FORGE 使用 `FORGE <%s>`，'
            'LENS 使用 `LENS <%s>`%s。\n'
            '平台自动生成的合并提交保留平台身份。\n\n## 其他段\n\n不相关正文。\n'
            % (luno, forge, lens, decl))


def ident(pair):
    return ('%s <%s>' % pair).encode('utf-8')


def signing_home():
    """测试内临时 GNUPGHOME（ed25519 签名钥，无 passphrase）：整轮共用一个。"""
    if 'home' not in _KEYRING:
        home = Path(tempfile.mkdtemp(prefix='ci-identity-gpg.'))
        os.chmod(str(home), 0o700)
        env = dict(os.environ, GNUPGHOME=str(home), LC_ALL='C')
        proc = subprocess.run(('gpg', '--batch', '--passphrase', '', '--quick-generate-key',
                               SIGNER, 'ed25519', 'sign', '0'),
                              capture_output=True, env=env)
        if proc.returncode != 0:
            raise unittest.SkipTest('测试钥生成失败')
        _KEYRING['home'] = home
    return _KEYRING['home']


def tearDownModule():
    home = _KEYRING.pop('home', None)
    if home:
        subprocess.run(('gpgconf', '--kill', 'all'), capture_output=True,
                       env=dict(os.environ, GNUPGHOME=str(home)))
        shutil.rmtree(str(home), True)
    if _TEMPLATE:                      # 模板仓库同样不留残留
        shutil.rmtree(str(_TEMPLATE.pop().dir), True)
    exp = _EXPIRED.pop('home', None)
    if exp:
        subprocess.run(('gpgconf', '--kill', 'all'), capture_output=True,
                       env=dict(os.environ, GNUPGHOME=str(exp)))
        shutil.rmtree(str(exp), True)
    sub = _SUBKEY.pop('home', None)
    if sub:
        subprocess.run(('gpgconf', '--kill', 'all'), capture_output=True,
                       env=dict(os.environ, GNUPGHOME=str(sub)))
        shutil.rmtree(str(sub), True)


def gpg_sign(payload):
    """对提交正文（含 gpgsig 之外的完整头与消息）签名，返回 git 形态的 `gpgsig` 头块。"""
    env = dict(os.environ, GNUPGHOME=str(signing_home()), LC_ALL='C')
    proc = subprocess.run(('gpg', '--batch', '--yes', '--armor', '--detach-sign'),
                          input=payload, capture_output=True, env=env)
    if proc.returncode != 0:
        raise AssertionError('夹具签名失败')
    armor = proc.stdout.rstrip(b'\n').split(b'\n')
    return b'gpgsig ' + armor[0] + b'\n' + b''.join(b' ' + line + b'\n' for line in armor[1:])


def key_fpr(home):
    """取钥环里第一把主钥的指纹（ed25519 无子钥，取 pub 后的 fpr）。"""
    env = dict(os.environ, GNUPGHOME=str(home), LC_ALL='C')
    proc = subprocess.run(('gpg', '--batch', '--with-colons', '--fingerprint'),
                          capture_output=True, env=env)
    if proc.returncode != 0:
        raise AssertionError('钥环不可读')
    want = False
    for line in proc.stdout.decode('utf-8', 'replace').splitlines():
        field = line.split(':')
        if field[0] == 'pub':
            want = True
        elif field[0] == 'sub':
            want = False
        elif field[0] == 'fpr' and want and len(field) > 9:
            return field[9]
    raise AssertionError('钥环内无主钥')


def gpg_sign_at(payload, home, faked=None):
    """同 gpg_sign，但可指定钥环与（可选）假系统时间：过期钥只能在其有效期内签。"""
    argv = ['gpg', '--batch', '--yes', '--armor', '--detach-sign']
    if faked:
        argv += ['--faked-system-time', faked]
    env = dict(os.environ, GNUPGHOME=str(home), LC_ALL='C')
    proc = subprocess.run(argv, input=payload, capture_output=True, env=env)
    if proc.returncode != 0:
        raise AssertionError('夹具签名失败')
    armor = proc.stdout.rstrip(b'\n').split(b'\n')
    return b'gpgsig ' + armor[0] + b'\n' + b''.join(b' ' + line + b'\n' for line in armor[1:])


_EXPIRED = {}


def expired_home():
    """测试内临时 GNUPGHOME：假系统时间回到 2024-01-01 生成 1 天有效期的钥，现下已过期。"""
    if 'home' not in _EXPIRED:
        home = Path(tempfile.mkdtemp(prefix='ci-identity-gpg-exp.'))
        os.chmod(str(home), 0o700)
        env = dict(os.environ, GNUPGHOME=str(home), LC_ALL='C')
        proc = subprocess.run(('gpg', '--batch', '--passphrase', '', '--faked-system-time',
                               '20240101T000000', '--quick-generate-key', SIGNER, 'ed25519',
                               'sign', '1d'), capture_output=True, env=env)
        if proc.returncode != 0:
            shutil.rmtree(str(home), True)
            raise unittest.SkipTest('过期测试钥生成失败')
        _EXPIRED['home'] = home
        _EXPIRED['fpr'] = key_fpr(home)
    return _EXPIRED['home'], _EXPIRED['fpr']


_SUBKEY = {}


def subkey_fpr(home):
    """取钥环里第一把子钥的指纹（`sub` 后的 `fpr`）。"""
    env = dict(os.environ, GNUPGHOME=str(home), LC_ALL='C')
    proc = subprocess.run(('gpg', '--batch', '--with-colons', '--fingerprint'),
                          capture_output=True, env=env)
    if proc.returncode != 0:
        raise AssertionError('钥环不可读')
    want = False
    for line in proc.stdout.decode('utf-8', 'replace').splitlines():
        field = line.split(':')
        if field[0] == 'sub':
            want = True
        elif field[0] == 'fpr' and want and len(field) > 9:
            return field[9]
    raise AssertionError('钥环内无子钥')


def subkey_home():
    """测试内临时 GNUPGHOME：ed25519 主钥（cert-only）＋ 签名子钥，整轮共用一个。

    只在主钥与子钥指纹不同的前提下有意义（#12 的主钥／子钥区分）。
    """
    if 'home' not in _SUBKEY:
        home = Path(tempfile.mkdtemp(prefix='ci-identity-gpg-pri.'))
        os.chmod(str(home), 0o700)
        env = dict(os.environ, GNUPGHOME=str(home), LC_ALL='C')
        proc = subprocess.run(('gpg', '--batch', '--passphrase', '', '--quick-generate-key',
                               SIGNER, 'ed25519', 'cert', '0'), capture_output=True, env=env)
        if proc.returncode == 0:
            primary = key_fpr(home)
            proc = subprocess.run(('gpg', '--batch', '--passphrase', '', '--quick-add-key',
                                   primary, 'ed25519', 'sign', '0'),
                                  capture_output=True, env=env)
        if proc.returncode != 0:
            subprocess.run(('gpgconf', '--kill', 'all'), capture_output=True, env=env)
            shutil.rmtree(str(home), True)
            raise unittest.SkipTest('主钥／子钥测试钥生成失败')
        _SUBKEY.update(home=home, primary=primary, sub=subkey_fpr(home))
    return _SUBKEY['home'], _SUBKEY['sub'], _SUBKEY['primary']


class Repo:
    """一次性 git 仓库：空树 ＋ 手工构造的提交对象；无工作区、无身份配置、无网络。"""

    def __init__(self, text=None):
        self.dir = Path(tempfile.mkdtemp(prefix='ci-identity.'))
        self.git('init', '-q', '-b', 'main')
        self.tree = self.git('mktree').stdout.strip().decode('ascii')
        self.rules = self.dir / 'rules.md'
        self.rules.write_text(rule_text() if text is None else text, encoding='utf-8')

    @classmethod
    def copy_of(cls, other):
        """复制一份已初始化的空仓库：省掉每例 `git init`／`mktree` 的子进程开销。"""
        inst = object.__new__(cls)
        inst.dir = Path(tempfile.mkdtemp(prefix='ci-identity.'))
        shutil.rmtree(str(inst.dir))
        shutil.copytree(str(other.dir), str(inst.dir))
        inst.tree = other.tree
        inst.rules = inst.dir / 'rules.md'
        return inst

    def git(self, *args, input=b'', check=True):
        proc = subprocess.run(('git',) + args, cwd=str(self.dir), input=input,
                              capture_output=True)
        if check and proc.returncode != 0:
            raise AssertionError('夹具 git %s 失败：%s'
                                 % (args, proc.stderr.decode('utf-8', 'replace')))
        return proc

    def _head(self, author, committer, parents):
        raw = b'tree ' + self.tree.encode('ascii') + b'\n'
        for parent in parents:
            raw += b'parent ' + parent.encode('ascii') + b'\n'
        raw += b'author ' + ident(author) + b' 1700000000 +0000\n'
        raw += b'committer ' + ident(committer) + b' 1700000000 +0000\n'
        return raw

    def commit(self, author, committer, message='subject\n', parents=(), gpgsig=False,
               sign=False):
        head = self._head(author, committer, parents)
        body = message.encode('utf-8')
        raw = head
        if gpgsig:
            raw += (b'gpgsig -----BEGIN PGP SIGNATURE-----\n\n iQsynthfake\n'
                    b' -----END PGP SIGNATURE-----\n')
        elif sign:
            raw += gpg_sign(head + b'\n' + body)
        raw += b'\n' + body
        return self.git('hash-object', '-t', 'commit', '-w', '--stdin',
                        input=raw).stdout.strip().decode('ascii')

    def run(self, base, head, rules=True, allow_empty=False, extra=()):
        args = [sys.executable, '-B', str(TOOL), '--base', str(base), '--head', str(head)]
        if rules is True:
            args += ['--rules', str(self.rules)]
        elif rules:
            args += ['--rules', str(rules)]
        if allow_empty:
            args.append('--allow-empty')
        return subprocess.run(args + list(extra), cwd=str(self.dir), capture_output=True,
                              text=True, encoding='utf-8', timeout=120)

    def line(self, author=LUNO, committer=LUNO, **kw):
        """基线提交（非表内身份，作为 --base 不入范围）＋一个待检提交。"""
        base = self.commit(OTHER, OTHER)
        return base, self.commit(author, committer, parents=[base], **kw)


_TEMPLATE = []


class Base(unittest.TestCase):
    def setUp(self):
        if not _TEMPLATE:
            _TEMPLATE.append(Repo())
        self.repo = Repo.copy_of(_TEMPLATE[0])
        self.addCleanup(shutil.rmtree, str(self.repo.dir), True)

    def verdict(self, proc, rc, *needles):
        out = proc.stdout + proc.stderr
        for secret in (LUNO[1], FORGE[1], LENS[1], OTHER[1], PLATFORM[1], PLACEHOLDER):
            self.assertNotIn(secret, out, '输出不得含邮箱或占位形态')
        self.assertNotIn('@', out, '输出不得含任何 @ 串')
        self.assertEqual(proc.returncode, rc, out)
        for needle in needles:
            self.assertIn(needle, out)
        return out


class PositiveTest(Base):
    def test_forge_both(self):
        base, head = self.repo.line(FORGE, FORGE)
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_luno_both(self):
        base, head = self.repo.line()
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_forge_author_luno_committer(self):
        base, head = self.repo.line(FORGE, LUNO)
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_lens_author_forge_committer(self):
        # LENS 制稿、FORGE 代提交：作者保留实际编写者 LENS，Committer 记实际操作者
        base, head = self.repo.line(LENS, FORGE)
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_coauthor_allowed(self):
        for pair in (LUNO, LENS):
            with self.subTest(pair=pair[0]):
                base, head = self.repo.line(
                    FORGE, FORGE, message='subject\n\nCo-authored-by: %s <%s>\n' % pair)
                self.verdict(self.repo.run(base, head), 0, '通过')

    def test_midbody_coauthor_not_parsed(self):
        # 同 git 口径：尾部不是 trailer 块时，正文中段的同名行不参与解析
        base, head = self.repo.line(
            FORGE, FORGE, message='subject\n\nCo-authored-by: nobody <%s>\n\n尾段正文\n' % OTHER[1])
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_allow_empty(self):
        base, _ = self.repo.line()
        self.verdict(self.repo.run(base, base, allow_empty=True), 0, '空范围')


class PlatformTest(Base):
    """平台合并：只有「≥2 父 + 平台提交者 + web-flow 签名验证通过」才豁免，其余一律按普通提交。"""

    def merge(self, committer=PLATFORM, **kw):
        first, second = self.repo.line()
        return first, self.repo.commit(LUNO, committer, message='Merge pull request\n',
                                       parents=[first, second], **kw)

    def test_fake_signature_header_not_exempt(self):
        first, merge = self.merge(gpgsig=True)
        self.verdict(self.repo.run(first, merge), 1, 'committer', '身份不在署名表内')

    def test_real_signature_from_foreign_key_not_exempt(self):
        if shutil.which('gpg') is None:
            self.skipTest('无 gpg')
        first, merge = self.merge(sign=True)
        self.verdict(self.repo.run(first, merge), 1, 'committer', '身份不在署名表内')

    def test_two_parents_without_signature(self):
        first, merge = self.merge()
        self.verdict(self.repo.run(first, merge), 1, 'committer')

    def test_two_parents_signed_but_not_github(self):
        first, merge = self.merge(committer=OTHER, gpgsig=True)
        self.verdict(self.repo.run(first, merge), 1, 'committer')

    def test_single_parent_github_not_exempt(self):
        base, head = self.repo.line(LUNO, PLATFORM, gpgsig=True)
        self.verdict(self.repo.run(base, head), 1, 'committer')

    def test_platform_branch_still_checks_coauthor(self):
        # platform 分支只跳过 author／committer，Co-authored-by 仍须逐条核对。
        # 真 web-flow 钥无法伪造，故此处只把「签名验证通过」这一密码学边界打桩；
        # 真实签名验证由 HistoryTest 用仓库内真实平台合并提交覆盖。
        mod = load_tool()
        first = self.repo.commit(OTHER, OTHER)
        second = self.repo.commit(OTHER, OTHER, parents=[first])
        merge = self.repo.commit(LUNO, PLATFORM, parents=[first, second], gpgsig=True,
                                 message='Merge\n\nCo-authored-by: someone <%s>\n' % OTHER[1])
        rules = mod.read_rules(self.repo.rules)
        original = mod.WebFlow.verify
        mod.WebFlow.verify = lambda self, sha: True
        cwd = os.getcwd()
        try:
            os.chdir(str(self.repo.dir))
            problems, platform = mod.check_commit(rules, merge, mod.WebFlow())
        finally:
            os.chdir(cwd)
            mod.WebFlow.verify = original
        self.assertTrue(platform)
        self.assertIn('Co-authored-by#1 身份不在署名表内',
                      ['%s %s' % (f, c) for f, c in problems])

    def test_platform_with_gpg_unavailable_fails_closed(self):
        if shutil.which('gpg') is None:
            self.skipTest('本机无 gpg，无 gpg 的路径由上一例覆盖')
        first, merge = self.merge(sign=True)
        # PATH 只留一个 git 符号链接（无 gpg）：验证能力缺失 → rc=2（环境错误），
        # 不静默放过平台豁免，也不谎报违规
        bare = Path(tempfile.mkdtemp(prefix='ci-identity-nogpg.'))
        self.addCleanup(shutil.rmtree, str(bare), True)
        (bare / 'git').symlink_to(shutil.which('git'))
        env = dict(os.environ, PATH=str(bare))
        proc = subprocess.run([sys.executable, '-B', str(TOOL), '--base', first,
                               '--head', merge, '--rules', str(self.repo.rules)],
                              cwd=str(self.repo.dir), capture_output=True, text=True,
                              encoding='utf-8', timeout=120, env=env)
        self.verdict(proc, 2, '缺少 gpg')


def validsig_text(fpr, primary=None):
    """git verify-commit --raw 形态的输出：含 VALIDSIG（gpg 对「过期钥好签名」也这么报）。"""
    tail = (fpr if primary is None else primary).encode('ascii')
    return (b'[GNUPG:] NEWSIG\n[GNUPG:] VALIDSIG ' + fpr.encode('ascii')
            + b' 2026-11-05 1793868808 0 4 0 1 8 00 ' + tail + b'\n')


class SquashTest(Base):
    """squash 收口：只有「单父 + 平台提交者 + 验签通过 + Co-authored-by 非空且合规」才放行。

    `--allow-squash` 只给 push 事件；PR 事件不给，仍逐提交核对（见 PlatformTest 的单父负控）。
    「覆盖 PR 内全部作者」不在本工具范围（push 范围只有 squash 一个提交），故只断言可判部分。
    """

    def inspect(self, allow_squash=True, committer=PLATFORM, parents=1, message=None, **kw):
        """真 web-flow 钥无法伪造：只打桩「验签通过」这一密码学边界，其余全走真实对象。"""
        mod = load_tool()
        first = self.repo.commit(OTHER, OTHER)
        tail = [first]
        if parents > 1:
            tail.append(self.repo.commit(OTHER, OTHER))
        if message is None:
            message = 'squash subject\n\nCo-authored-by: FORGE <%s>\n' % FORGE[1]
        sha = self.repo.commit(LUNO, committer, parents=tail, gpgsig=True, message=message, **kw)
        rules = mod.read_rules(self.repo.rules)
        original = mod.WebFlow.verify
        mod.WebFlow.verify = lambda self, s: True
        cwd = os.getcwd()
        try:
            os.chdir(str(self.repo.dir))
            problems, kind = mod.check_commit(rules, sha, mod.WebFlow(), allow_squash)
        finally:
            os.chdir(cwd)
            mod.WebFlow.verify = original
        return ['%s %s' % (f, c) for f, c in problems], kind

    def test_squash_exempt_with_coauthor(self):
        problems, kind = self.inspect()
        self.assertEqual(kind, 'squash')
        self.assertEqual(problems, [])

    def test_squash_without_coauthor_rejected(self):
        problems, kind = self.inspect(message='squash subject\n\n正文\n')
        self.assertEqual(kind, 'squash')
        self.assertIn('Co-authored-by squash 提交缺少 Co-authored-by', problems)

    def test_squash_coauthor_must_be_known(self):
        problems, _ = self.inspect(
            message='squash\n\nCo-authored-by: nobody <%s>\n' % OTHER[1])
        self.assertIn('Co-authored-by#1 身份不在署名表内', problems)

    def test_squash_lens_coauthor_accepted(self):
        # PR 内 LENS 制稿的提交被 squash：收口者按原字节写一行 LENS 尾署即合规
        problems, kind = self.inspect(
            message='squash\n\nCo-authored-by: LENS <%s>\n' % LENS[1])
        self.assertEqual(kind, 'squash')
        self.assertEqual(problems, [])

    def test_squash_duplicate_coauthor_deduped(self):
        # 并集去重：PR 内多个提交同属 FORGE，收口者按原字节各写一行 → 同一身份重复只计一次
        problems, kind = self.inspect(
            message='squash\n\nCo-authored-by: FORGE <%s>\nCo-authored-by: FORGE <%s>\n'
                    % (FORGE[1], FORGE[1]))
        self.assertEqual(kind, 'squash')
        self.assertEqual(problems, [])

    def test_squash_coauthor_may_equal_author(self):
        # 仅 squash 允许尾行与 Author 相同：Author 即 PR 内最后一个提交的作者
        problems, kind = self.inspect(
            message='squash\n\nCo-authored-by: FORGE <%s>\nCo-authored-by: LUNO <%s>\n'
                    % (FORGE[1], LUNO[1]))
        self.assertEqual(kind, 'squash')
        self.assertEqual(problems, [])

    def test_platform_merge_needs_no_author_trailer(self):
        # 平台合并提交不额外要求作者行：无 Co-authored-by 也放行
        problems, kind = self.inspect(parents=2, message='Merge pull request #1\n\n正文\n')
        self.assertEqual(kind, 'platform')
        self.assertEqual(problems, [])

    def test_squash_flag_absent_still_rejected(self):
        # 不给 flag（PR 事件口径）：单父平台提交仍按普通提交判违规
        problems, kind = self.inspect(allow_squash=False)
        self.assertEqual(kind, '')
        self.assertIn('committer 身份不在署名表内', problems)

    def test_squash_two_parent_is_platform_not_squash(self):
        problems, kind = self.inspect(parents=2)
        self.assertEqual(kind, 'platform')
        self.assertEqual(problems, [])

    def test_squash_flag_needs_signature(self):
        # 端到端：假签名头下，带 --allow-squash 也不放行（flag 不是绕过签名的手段）
        base, head = self.repo.line(LUNO, PLATFORM, gpgsig=True,
                                    message='squash\n\nCo-authored-by: FORGE <%s>\n' % FORGE[1])
        self.verdict(self.repo.run(base, head, extra=('--allow-squash',)), 1, 'committer')
        self.verdict(self.repo.run(base, head), 1, 'committer')


class WebflowGateTest(unittest.TestCase):
    """LENS 第 2 轮第 10 项：退出码非零一律不豁免，输出里有 VALIDSIG 也不算数。"""

    def verify_with(self, rc, text, fingerprints=None):
        """只在密码学边界上打桩：伪造 verify-commit 的退出码与状态输出。"""
        mod = load_tool()
        original_git = mod.git
        original_fpr = mod.WEBFLOW_FINGERPRINTS
        wf = mod.WebFlow()
        wf.home = str(signing_home())      # 复用测试钥环，无需再导入 web-flow 文件
        wf.ready = True

        def fake(*args, **kw):
            if args and args[0] == 'verify-commit':
                return rc, b'', text
            return original_git(*args, **kw)

        mod.git = fake
        try:
            if fingerprints is not None:
                mod.WEBFLOW_FINGERPRINTS = frozenset(fingerprints)
            return wf.verify('0' * 40)
        finally:
            mod.git = original_git
            mod.WEBFLOW_FINGERPRINTS = original_fpr

    def test_validsig_text_with_rc1_not_exempt(self):
        # 指纹在集合内、输出含 VALIDSIG，但退出码 1：不得豁免
        self.assertFalse(self.verify_with(1, validsig_text(CURRENT_FPR)))

    def test_validsig_text_with_rc2_not_exempt(self):
        self.assertFalse(self.verify_with(2, validsig_text(CURRENT_FPR)))

    def test_validsig_text_with_rc0_exempt(self):
        # 正控：同一份输出，只有退出码 0 才豁免（证明前两例的 False 来自退出码，不是桩坏了）
        self.assertTrue(self.verify_with(0, validsig_text(CURRENT_FPR)))

    def test_old_primary_key_not_exempt(self):
        # #12：末位（主钥）是旧钥、签发者是现用钥 → 不豁免；旧口径只读 parts[2] 会误放
        self.assertFalse(self.verify_with(0, validsig_text(CURRENT_FPR, OLD_FPR)))

    def test_short_validsig_not_exempt(self):
        # 字段不足 12（无末位主钥指纹）：无从判定主钥 → 不豁免
        short = (b'[GNUPG:] NEWSIG\n[GNUPG:] VALIDSIG ' + CURRENT_FPR.encode('ascii')
                 + b' 2026-11-05 1793868808 0 4 0 1 8 00\n')
        self.assertFalse(self.verify_with(0, short))

    def test_only_current_key_trusted(self):
        mod = load_tool()
        self.assertEqual(mod.WEBFLOW_FINGERPRINTS, frozenset((CURRENT_FPR,)))
        self.assertNotIn(OLD_FPR, mod.WEBFLOW_FINGERPRINTS)
        self.assertIn('只信任', TOOL.read_text(encoding='utf-8'))


class ExpiredSignatureTest(Base):
    """真实过期钥签名：指纹临时放进固定集合，也必须验签失败、按普通提交拒绝。"""

    def signed_merge(self, home, faked):
        base = self.repo.commit(OTHER, OTHER)
        second = self.repo.commit(OTHER, OTHER, parents=[base])
        head = self.repo._head(LUNO, PLATFORM, [base, second])
        body = b'Merge pull request\n'
        raw = head + gpg_sign_at(head + b'\n' + body, home, faked) + b'\n' + body
        sha = self.repo.git('hash-object', '-t', 'commit', '-w', '--stdin', input=raw)
        return base, sha.stdout.strip().decode('ascii')

    def inspect(self, home, fpr, faked):
        mod = load_tool()
        _, merge = self.signed_merge(home, faked)
        wf = mod.WebFlow()
        wf.home = str(home)
        wf.ready = True
        rules = mod.read_rules(self.repo.rules)
        saved = mod.WEBFLOW_FINGERPRINTS
        cwd = os.getcwd()
        mod.WEBFLOW_FINGERPRINTS = frozenset((CURRENT_FPR, fpr))
        try:
            os.chdir(str(self.repo.dir))
            verdict = wf.verify(merge)
            problems, platform = mod.check_commit(rules, merge, wf)
        finally:
            os.chdir(cwd)
            mod.WEBFLOW_FINGERPRINTS = saved
        proc = subprocess.run(('git', 'verify-commit', '--raw', merge),
                              cwd=str(self.repo.dir), capture_output=True,
                              env=dict(os.environ, GNUPGHOME=str(home), LC_ALL='C'))
        return verdict, problems, platform, proc

    def test_expired_key_signature_rejected(self):
        if shutil.which('gpg') is None:
            self.skipTest('无 gpg')
        home, fpr = expired_home()
        verdict, problems, platform, proc = self.inspect(home, fpr, '20240101T010000')
        # 事实前提：gpg 对过期钥的好签名确实同时给出 VALIDSIG 与非零退出码
        self.assertNotEqual(proc.returncode, 0, '过期钥的验签退出码应非零')
        self.assertIn(b'VALIDSIG', proc.stderr)
        self.assertFalse(verdict, '指纹在集合内也不得豁免：退出码非零')
        self.assertFalse(platform)
        self.assertIn('committer', [field for field, _ in problems])

    def test_valid_key_in_set_still_exempt(self):
        # 正控：同一路径下未过期钥 ＋ 指纹临时入集合 → 豁免（证明上面失败来自退出码）
        if shutil.which('gpg') is None:
            self.skipTest('无 gpg')
        home = signing_home()
        verdict, _, platform, proc = self.inspect(home, key_fpr(home), None)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(verdict)
        self.assertTrue(platform)


class PrimaryKeyTest(Base):
    """#12：判据是 `VALIDSIG` 末位的主钥指纹——签名子钥入集合不得豁免，主钥入集合才豁免。"""

    def signed_merge(self):
        """用签名子钥真实签一个 `GitHub` 双父合并提交（主钥只作 cert，不签发）。"""
        home = subkey_home()[0]
        base = self.repo.commit(OTHER, OTHER)
        second = self.repo.commit(OTHER, OTHER, parents=[base])
        head = self.repo._head(LUNO, PLATFORM, [base, second])
        body = b'Merge pull request\n'
        raw = head + gpg_sign_at(head + b'\n' + body, home) + b'\n' + body
        sha = self.repo.git('hash-object', '-t', 'commit', '-w', '--stdin', input=raw)
        return sha.stdout.strip().decode('ascii')

    def inspect(self, fprs):
        mod = load_tool()
        merge = self.signed_merge()
        wf = mod.WebFlow()
        wf.home = str(subkey_home()[0])
        wf.ready = True
        rules = mod.read_rules(self.repo.rules)
        saved = mod.WEBFLOW_FINGERPRINTS
        cwd = os.getcwd()
        mod.WEBFLOW_FINGERPRINTS = frozenset(fprs)
        try:
            os.chdir(str(self.repo.dir))
            verdict = wf.verify(merge)
            problems, platform = mod.check_commit(rules, merge, wf)
        finally:
            os.chdir(cwd)
            mod.WEBFLOW_FINGERPRINTS = saved
        return verdict, problems, platform

    def test_primary_fingerprint_in_set_exempt(self):
        if shutil.which('gpg') is None:
            self.skipTest('无 gpg')
        _, sub, primary = subkey_home()
        self.assertNotEqual(sub, primary, '夹具须有独立的主钥与子钥指纹')
        verdict, problems, platform = self.inspect((primary,))
        self.assertTrue(verdict, '主钥在集合内：子钥签发应豁免')
        self.assertTrue(platform)
        self.assertEqual(problems, [])

    def test_subkey_fingerprint_in_set_not_exempt(self):
        if shutil.which('gpg') is None:
            self.skipTest('无 gpg')
        _, sub, primary = subkey_home()
        verdict, problems, platform = self.inspect((sub,))
        self.assertFalse(verdict, '只有签名子钥在集合内、主钥不在：不得豁免')
        self.assertFalse(platform)
        self.assertIn('committer', [field for field, _ in problems])


class HistoryTest(unittest.TestCase):
    """真实平台合并提交：原始对象只从仓库读，不另存夹具文件（其 author 行含用户真实地址）。"""

    def test_real_platform_merge_is_exempt(self):
        if shutil.which('gpg') is None:
            self.skipTest('无 gpg')
        probe = subprocess.run(('git', 'cat-file', '-e', REAL_MERGE + '^{commit}'),
                               cwd=str(ROOT), capture_output=True)
        if probe.returncode != 0:
            self.skipTest('仓库内无该对象（浅克隆或未含该历史），跳过')
        parent = subprocess.run(('git', 'rev-parse', REAL_MERGE + '^2'), cwd=str(ROOT),
                                capture_output=True, text=True, check=True).stdout.strip()
        proc = subprocess.run([sys.executable, '-B', str(TOOL), '--base', parent,
                               '--head', REAL_MERGE,
                               '--rules', str(ROOT / 'skills/luno-core/references/delegation.md')],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding='utf-8', timeout=120)
        out = proc.stdout + proc.stderr
        self.assertNotIn('@', out)
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('platform', out)


class NegativeIdentityTest(Base):
    def test_wrong_email(self):
        base, head = self.repo.line(('LUNO', OTHER[1]), LUNO)
        self.verdict(self.repo.run(base, head), 1, 'author', '身份不在署名表内')

    def test_forge_name_with_luno_mail(self):
        base, head = self.repo.line(('FORGE', LUNO[1]), LUNO)
        self.verdict(self.repo.run(base, head), 1, 'author', '身份不在署名表内')

    def test_lens_name_with_foreign_email(self):
        base, head = self.repo.line(('LENS', LUNO[1]), LUNO)
        self.verdict(self.repo.run(base, head), 1, 'author', '身份不在署名表内')

    def test_lowercase_name(self):
        for name in ('forge', 'Luno', 'luno', 'Forge'):
            with self.subTest(name=name):
                base, head = self.repo.line((name, FORGE[1]), LUNO)
                self.verdict(self.repo.run(base, head), 1, 'author')

    def test_lens_name_case_sensitive(self):
        # 单故障注入：仅改作者名大小写，邮箱仍是 LENS 的正确地址，其余条件同正控
        # （LENS 作者＋FORGE 代提交），故失败只能来自大小写敏感。
        for name in ('lens', 'Lens', 'leNs'):
            with self.subTest(name=name):
                base, head = self.repo.line((name, LENS[1]), FORGE)
                self.verdict(self.repo.run(base, head), 1, 'author', '身份不在署名表内')

    def test_bad_committer(self):
        base, head = self.repo.line(LUNO, ('LUNO', OTHER[1]))
        self.verdict(self.repo.run(base, head), 1, 'committer', '身份不在署名表内')

    def test_replace_ref_cannot_launder(self):
        # `git replace` 把一个合规提交顶包到违规提交上：检查器须无视替换对象，仍判违规
        base = self.repo.commit(OTHER, OTHER)
        good = self.repo.commit(LUNO, LUNO, parents=[base])
        bad = self.repo.commit(OTHER, OTHER, parents=[base])
        self.repo.git('replace', bad, good)
        self.verdict(self.repo.run(base, bad), 1, 'author', '身份不在署名表内')

    def test_grafts_cannot_hide_commit(self):
        # info/grafts 把 head 的父改成 base，可让违规的中间提交淡出 rev-list；须被屏蔽
        base = self.repo.commit(OTHER, OTHER)
        bad = self.repo.commit(OTHER, OTHER, parents=[base])
        head = self.repo.commit(LUNO, LUNO, parents=[bad])
        info = self.repo.dir / '.git' / 'info'
        info.mkdir(exist_ok=True)
        (info / 'grafts').write_text('%s %s\n' % (head, base), encoding='utf-8')
        self.verdict(self.repo.run(base, head), 1, 'author', '身份不在署名表内')


class TrailerTest(Base):
    def trailer(self, value, body=''):
        base, head = self.repo.line(FORGE, FORGE,
                                    message='subject\n\nCo-authored-by: %s\n%s' % (value, body))
        return self.repo.run(base, head)

    def test_malformed(self):
        self.verdict(self.trailer('FORGE'), 1, 'Co-authored-by#1', '格式非')

    def test_duplicate_deduped(self):
        # 并集去重正控：同一身份重复写两行只计一次，不判违规
        base, head = self.repo.line(FORGE, FORGE, message=(
            'subject\n\nCo-authored-by: LUNO <%s>\nCo-authored-by: LUNO <%s>\n'
            % (LUNO[1], LUNO[1])))
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_same_as_author(self):
        # 回归负控：普通提交的尾行与 Author 相同仍判违规（仅 squash 放行）
        self.verdict(self.trailer('FORGE <%s>' % FORGE[1]), 1, '与 Author 相同')

    def test_unknown_identity(self):
        self.verdict(self.trailer('LUNO <%s>' % OTHER[1]), 1, '身份不在署名表内')

    def test_no_space_separator_allowed(self):
        base, head = self.repo.line(FORGE, FORGE,
                                    message='subject\n\nCo-authored-by:LUNO <%s>\n' % LUNO[1])
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_no_space_separator_bad_identity(self):
        base, head = self.repo.line(FORGE, FORGE,
                                    message='subject\n\nCo-authored-by:someone <%s>\n' % OTHER[1])
        self.verdict(self.repo.run(base, head), 1, 'Co-authored-by#1', '身份不在署名表内')

    def test_tab_separator(self):
        base, head = self.repo.line(FORGE, FORGE,
                                    message='subject\n\nCo-authored-by:\tLUNO <%s>\n' % LUNO[1])
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_tab_separator_bad_identity(self):
        base, head = self.repo.line(FORGE, FORGE,
                                    message='subject\n\nCo-authored-by:\tsomeone <%s>\n' % OTHER[1])
        self.verdict(self.repo.run(base, head), 1, 'Co-authored-by#1', '身份不在署名表内')

    def test_mixed_trailers(self):
        basic = 'Signed-off-by: LUNO <%s>\nAcked-by: someone <%s>\n' % (LUNO[1], OTHER[1])
        base, head = self.repo.line(
            FORGE, FORGE, message='subject\n\nCo-authored-by: LUNO <%s>\n%s' % (LUNO[1], basic))
        self.verdict(self.repo.run(base, head), 0, '通过')
        base2, head2 = self.repo.line(
            FORGE, FORGE, message='subject\n\n%sCo-authored-by: someone <%s>\n'
            % (basic, OTHER[1]))
        self.verdict(self.repo.run(base2, head2), 1, 'Co-authored-by#1', '身份不在署名表内')

    def test_continuation_line(self):
        # 续行拼进值里 → 不再等于 `Name <email>`，须判违规而不是当作没有署名
        base, head = self.repo.line(
            FORGE, FORGE, message='subject\n\nCo-authored-by: LUNO <%s>\n 继续\n' % LUNO[1])
        self.verdict(self.repo.run(base, head), 1, 'Co-authored-by#1')


class RulesTest(Base):
    def test_missing_file(self):
        base, head = self.repo.line()
        self.verdict(self.repo.run(base, head, rules=self.repo.dir / 'nope.md'), 2, '规则文件不可读')

    def test_not_utf8(self):
        (self.repo.dir / 'bad.md').write_bytes(b'## Git \xff\xfe 1\n')
        base, head = self.repo.line()
        self.verdict(self.repo.run(base, head, rules=self.repo.dir / 'bad.md'), 2,
                     '规则文件不是 UTF-8')

    def test_missing_section(self):
        self.repo.rules.write_text('# 夹具规则\n\n## 其他段\n\n无署名段。\n', encoding='utf-8')
        base, head = self.repo.line()
        self.verdict(self.repo.run(base, head), 2, '缺少')

    def test_duplicate_identity(self):
        # 重复声明必须是**完整反引号声明**：reader 只认 `Name <email>`，不认裸行。
        tail = '，LENS 使用 `LENS <%s>`' % LENS[1]
        for pair in (LUNO, FORGE, LENS) + EXTERNAL:
            with self.subTest(pair=pair[0]):
                text = rule_text().replace(
                    tail, tail + '，%s 使用 `%s <%s>`' % (pair[0], pair[0], pair[1]), 1)
                self.assertNotEqual(text, rule_text())
                self.repo.rules.write_text(text, encoding='utf-8')
                base, head = self.repo.line()
                self.verdict(self.repo.run(base, head), 2, '身份重复')

    def test_empty_email_declaration(self):
        # 空邮箱是**坏声明**。reader 先判重复、后判邮箱形态，故位置决定**哪一个** rc=2：
        #   · 坏声明在本节**所有**合法声明之前 → 该名首次出现即空值 → 「形态非法」；
        #   · 坏声明在所有合法声明**之后**（下一 `##` 之前）→ 该名已登记 → 「身份重复」。
        # 两种位置都必须 rc=2，且断言顺序，防止只换期望字符串。
        head_anchor = '## Git 提交署名\n\n'
        tail_anchor = '平台自动生成的合并提交保留平台身份。'
        names = tuple(n for n, _ in (LUNO, FORGE, LENS) + EXTERNAL)
        for name in names:
            decl = '%s 使用 `%s <>`\n' % (name, name)
            for pos, anchor, want in (('before', head_anchor, '形态非法'),
                                      ('after', tail_anchor, '身份重复')):
                with self.subTest(name=name, pos=pos):
                    text = rule_text().replace(anchor, anchor + decl if pos == 'before'
                                               else anchor + '\n' + decl.rstrip('\n'), 1)
                    self.assertNotEqual(text, rule_text())
                    bad = text.index('`%s <>`' % name)
                    legit = [text.index('`%s <%s>`' % p) for p in (LUNO, FORGE, LENS) + EXTERNAL]
                    if pos == 'before':
                        self.assertLess(bad, min(legit))
                    else:
                        self.assertGreater(bad, max(legit))
                    self.repo.rules.write_text(text, encoding='utf-8')
                    base, head = self.repo.line()
                    self.verdict(self.repo.run(base, head), 2, want)

    def test_only_name_with_empty_email(self):
        # 把该名本身写成 `Name <>`：该名已登记但形态非法 → rc=2，不得读成别的放行。
        base_pairs = (LUNO, FORGE, LENS) + EXTERNAL
        for name, email in base_pairs:
            with self.subTest(name=name):
                text = rule_text().replace('`%s <%s>`' % (name, email), '`%s <>`' % name, 1)
                self.assertNotEqual(text, rule_text())
                self.repo.rules.write_text(text, encoding='utf-8')
                base, head = self.repo.line()
                self.verdict(self.repo.run(base, head), 2, '形态非法')

    def test_missing_lens_identity(self):
        text = rule_text().replace('，LENS 使用 `LENS <%s>`' % LENS[1], '', 1)
        self.assertNotEqual(text, rule_text())
        self.repo.rules.write_text(text, encoding='utf-8')
        base, head = self.repo.line()
        self.verdict(self.repo.run(base, head), 2, '缺少 LENS')

    def test_two_identities_same_email(self):
        for a, b in ((LUNO, FORGE), (LUNO, LENS), (FORGE, LENS)):
            with self.subTest(a=a[0], b=b[0]):
                self.repo.rules.write_text(rule_text(**{a[0].lower(): b[1]}), encoding='utf-8')
                base, head = self.repo.line()
                self.verdict(self.repo.run(base, head), 2, '同一邮箱')

    def test_placeholder_form(self):
        for text in (rule_text(luno=PLACEHOLDER), rule_text(forge=PLACEHOLDER),
                     rule_text(luno='address')):
            with self.subTest(text=text):
                self.repo.rules.write_text(text, encoding='utf-8')
                base, head = self.repo.line()
                self.verdict(self.repo.run(base, head), 2, '形态非法')

    def test_surrounding_whitespace_not_normalized(self):
        # 规则值不 strip：两侧空白不得被悄悄抹平后当成合法身份
        for luno in (' %s', '%s ', ' %s '):
            with self.subTest(luno=luno):
                self.repo.rules.write_text(rule_text(luno=luno % LUNO[1]), encoding='utf-8')
                base, head = self.repo.line()
                self.verdict(self.repo.run(base, head), 2, '形态非法')

    def test_local_address_form(self):
        self.repo.rules.write_text(rule_text(luno=LUNO[1], forge=FORGE[1]), encoding='utf-8')
        base, head = self.repo.line(FORGE, LUNO)
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_rule_change_is_single_source(self):
        base, head = self.repo.line()
        self.verdict(self.repo.run(base, head), 0, '通过')
        self.repo.rules.write_text(rule_text(luno=OTHER[1]), encoding='utf-8')
        self.verdict(self.repo.run(base, head), 1, 'author')


class EnvironmentTest(Base):
    def test_invalid_rev(self):
        base, _ = self.repo.line()
        self.verdict(self.repo.run('deadbeef', base), 2, 'rev 无效或不是提交')

    def test_empty_range_without_allow_empty(self):
        base, _ = self.repo.line()
        self.verdict(self.repo.run(base, base), 2, '空范围')

    def test_bad_argument_does_not_echo(self):
        proc = subprocess.run([sys.executable, '-B', str(TOOL), '--bogus', OTHER[1]],
                              cwd=str(self.repo.dir), capture_output=True, text=True,
                              encoding='utf-8', timeout=120)
        self.verdict(proc, 2, '参数无效')

    def test_bad_rules_path_does_not_echo(self):
        base, head = self.repo.line()
        proc = self.repo.run(base, head, rules=self.repo.dir / ('missing.' + OTHER[1]))
        self.verdict(proc, 2, '规则文件不可读')

    def test_bad_rev_does_not_echo(self):
        base, _ = self.repo.line()
        self.verdict(self.repo.run(base, 'x' + OTHER[1]), 2, 'rev 无效或不是提交')

    def test_missing_argument(self):
        proc = subprocess.run([sys.executable, '-B', str(TOOL), '--base', 'HEAD'],
                              cwd=str(self.repo.dir), capture_output=True, text=True,
                              encoding='utf-8', timeout=120)
        self.verdict(proc, 2, '参数无效')

    def test_shallow_clone(self):
        base, head = self.repo.line()
        self.repo.git('update-ref', 'refs/heads/main', head)
        shallow = Path(tempfile.mkdtemp(prefix='ci-identity-shallow.'))
        self.addCleanup(shutil.rmtree, str(shallow), True)
        dest = shallow / 'clone'
        subprocess.run(('git', 'clone', '-q', '--depth', '1', 'file://' + str(self.repo.dir),
                        str(dest)), capture_output=True, check=True)
        proc = subprocess.run([sys.executable, '-B', str(TOOL), '--base', base, '--head', head,
                               '--rules', str(self.repo.rules)], cwd=str(dest),
                              capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.verdict(proc, 2, '浅克隆')


if __name__ == '__main__':
    unittest.main()


class ExternalIdentityTest(Base):
    """规则登记的外部身份（测试内 literal fixture，独立于生产 NAMES，不从 NAMES 反推）。

    reader 契约顺序：整行标题 → 反引号完整声明 → 精确 name 入表 → 先判重复、再判邮箱形态。
    """

    def test_external_author_ok(self):
        for pair in EXTERNAL:
            with self.subTest(pair=pair[0]):
                base, head = self.repo.line(pair, pair)
                self.verdict(self.repo.run(base, head), 0, '通过')

    def test_external_committer_ok(self):
        for pair in EXTERNAL:
            with self.subTest(pair=pair[0]):
                base, head = self.repo.line(LUNO, pair)
                self.verdict(self.repo.run(base, head), 0, '通过')

    def test_lens_committer_with_external_author_ok(self):
        base, head = self.repo.line(EXTERNAL[1], LENS)
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_external_coauthor_ok(self):
        for pair in EXTERNAL:
            with self.subTest(coauthor=pair[0]):
                base, head = self.repo.line(
                    LUNO, LUNO, message='subject\n\nCo-authored-by: %s <%s>\n' % pair)
                self.verdict(self.repo.run(base, head), 0, '通过')

    def test_forge_not_author_coauthor_ok(self):
        base = self.repo.commit(OTHER, OTHER)
        msg = 'subject\n\nCo-authored-by: FORGE <%s>\n' % FORGE[1]
        head = self.repo.commit(EXTERNAL[0], EXTERNAL[0], message=msg, parents=[base])
        self.verdict(self.repo.run(base, head), 0, '通过')

    def test_external_wrong_email_rc1(self):
        for name, mail in EXTERNAL:
            for old_pair in (LUNO, FORGE, LENS):
                with self.subTest(new_name=name, old_email_owner=old_pair[0]):
                    bad = (name, old_pair[1])
                    self.assertNotEqual(bad, (name, mail))
                    base, head = self.repo.line(bad, LUNO)
                    out = self.verdict(self.repo.run(base, head), 1, 'author', '身份不在署名表内')
                    self.assertIn(head[:7] + ' author 身份不在署名表内', out.splitlines())

    def test_external_wrong_name_rc1(self):
        for name, mail in EXTERNAL:
            for old_pair in (LUNO, FORGE, LENS):
                with self.subTest(new_email_owner=name, old_name=old_pair[0]):
                    bad = (old_pair[0], mail)
                    self.assertNotEqual(bad, old_pair)
                    base, head = self.repo.line(bad, LUNO)
                    out = self.verdict(self.repo.run(base, head), 1, 'author', '身份不在署名表内')
                    self.assertIn(head[:7] + ' author 身份不在署名表内', out.splitlines())

    def test_generic_claude_rc1(self):
        base, head = self.repo.line(('Claude', EXTERNAL[1][1]), ('Claude', EXTERNAL[1][1]))
        self.verdict(self.repo.run(base, head), 1, 'author')

    def test_claude_local_alias_rc1(self):
        base, head = self.repo.line((EXTERNAL[1][0], 'claude@local'),
                                    (EXTERNAL[1][0], 'claude@local'))
        self.verdict(self.repo.run(base, head), 1, 'author')

    def test_external_case_variants_rc1(self):
        for name, mail in EXTERNAL:
            local, domain = mail.split('@', 1)
            names = (name.lower(), name.upper())
            if name == 'Claude Opus 5.5':
                names += ('Claude opus 5.5',)
            variants = tuple((n, mail) for n in names) + (
                (name, mail.upper()), (name, local + '@' + domain.upper()))
            for bad in variants:
                with self.subTest(identity=name, bad=bad):
                    self.assertNotEqual(ident(bad), ident((name, mail)))
                    base, head = self.repo.line(bad, LUNO)
                    out = self.verdict(self.repo.run(base, head), 1, 'author', '身份不在署名表内')
                    self.assertIn(head[:7] + ' author 身份不在署名表内', out.splitlines())

    def test_rule_missing_external_rc2(self):
        for idx, (name, _mail) in enumerate(EXTERNAL):
            with self.subTest(name=name):
                extra = tuple(p for i, p in enumerate(EXTERNAL) if i != idx)
                self.repo.rules.write_text(rule_text(extra=extra), encoding='utf-8')
                base, head = self.repo.line()
                self.verdict(self.repo.run(base, head), 2, '缺少')

    def test_rule_same_email_conflict_rc2(self):
        # 五名 literal 夹具的全部十对；不从生产 NAMES 或生产算法构造期望。
        for a, b in combinations((LUNO, FORGE, LENS) + EXTERNAL, 2):
            with self.subTest(a=a[0], b=b[0]):
                original = rule_text()
                needle = '`%s <%s>`' % b
                self.assertEqual(original.count(needle), 1)
                text = original.replace(needle, '`%s <%s>`' % (b[0], a[1]), 1)
                self.assertNotEqual(text, original)
                self.repo.rules.write_text(text, encoding='utf-8')
                base, head = self.repo.line()
                out = self.verdict(self.repo.run(base, head), 2, '同一邮箱')
                self.assertIn('错误：规则〈Git 提交署名〉段身份指向同一邮箱（5 个身份，不回退）',
                              out.splitlines())

    def test_rule_title_lookalike_rc2(self):
        for heading in ('## Git 提交署名示例', '##非Git提交署名'):
            with self.subTest(heading=heading):
                text = rule_text().replace('## Git 提交署名', heading, 1)
                self.assertNotEqual(text, rule_text())
                self.repo.rules.write_text(text, encoding='utf-8')
                base, head = self.repo.line()
                self.verdict(self.repo.run(base, head), 2, '缺少')

    def test_rule_external_name_whitespace_rc2(self):
        # 姓名不 strip；该精确声明缺失，不把所有未知声明一律判非法。
        name, mail = EXTERNAL[0]
        for bad in (' ' + name, name + ' ', ' ' + name + ' '):
            with self.subTest(bad=bad):
                self.assertNotEqual(bad.encode(), name.encode())
                extra = ((bad, mail), EXTERNAL[1])
                self.repo.rules.write_text(rule_text(extra=extra), encoding='utf-8')
                base, head = self.repo.line()
                out = self.verdict(self.repo.run(base, head), 2, '缺少')
                self.assertIn('错误：规则〈Git 提交署名〉段缺少 LIN student 身份（不回退）',
                              out.splitlines())

    def test_rule_notlin_prefix_rc2(self):
        for bad in ('NotLIN student', 'Fake LIN student'):
            with self.subTest(replacement=bad):
                extra = ((bad, EXTERNAL[0][1]), EXTERNAL[1])
                self.repo.rules.write_text(rule_text(extra=extra), encoding='utf-8')
                base, head = self.repo.line()
                out = self.verdict(self.repo.run(base, head), 2, '缺少')
                self.assertIn('错误：规则〈Git 提交署名〉段缺少 LIN student 身份（不回退）',
                              out.splitlines())

    def test_rule_unknown_extra_declaration_rc0(self):
        # 五名合法声明完整时，两种未知声明均忽略；不新增身份、不全拒未知名。
        tail = '平台自动生成的合并提交保留平台身份。'
        for bad in ('NotLIN student', 'Fake LIN student'):
            with self.subTest(extra=bad):
                text = rule_text().replace(tail, tail + '\n%s 使用 `%s <x@y>`' % (bad, bad), 1)
                self.assertNotEqual(text, rule_text())
                self.repo.rules.write_text(text, encoding='utf-8')
                base, head = self.repo.line()
                self.verdict(self.repo.run(base, head), 0, '通过')

    def test_rule_external_invalid_email_rc2(self):
        for name, mail in EXTERNAL:
            for invalid in (PLACEHOLDER, 'address', ''):
                with self.subTest(identity=name, invalid=invalid):
                    original = rule_text()
                    needle = '`%s <%s>`' % (name, mail)
                    self.assertEqual(original.count(needle), 1)
                    text = original.replace(needle, '`%s <%s>`' % (name, invalid), 1)
                    self.assertNotEqual(text, original)
                    self.repo.rules.write_text(text, encoding='utf-8')
                    base, head = self.repo.line()
                    out = self.verdict(self.repo.run(base, head), 2, '形态非法')
                    self.assertIn('错误：规则〈Git 提交署名〉段 %s 身份形态非法（占位、带空白或非邮箱）'
                                  % name, out.splitlines())

    def test_rule_title_trailing_whitespace_ok(self):
        for suffix in (' ', '\t', ' \t '):
            with self.subTest(suffix=suffix):
                text = rule_text().replace('## Git 提交署名\n', '## Git 提交署名' + suffix + '\n', 1)
                self.assertNotEqual(text, rule_text())
                self.repo.rules.write_text(text, encoding='utf-8')
                base, head = self.repo.line()
                self.verdict(self.repo.run(base, head), 0, '通过')

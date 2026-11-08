#!/usr/bin/env python3
"""提交署名机械检查：逐个读取 <base>..<head> 的原始 Git 对象，按字节核对身份。

- 身份只取 --rules 指定文件（默认 skills/luno-core/references/delegation.md）的〈Git 提交署名〉段。
  标题须整行精确匹配（允许行尾空白），只读反引号内完整的 Name <email> 声明；姓名由 NAMES
  固定，新增姓名须与规则同批更新，未知姓名不放行。姓名不 strip，带额外空白即不匹配；五名
  完整时忽略额外未知声明。缺段、缺身份、重复、同邮箱、非法邮箱（占位或空白）、不可读或
  非 UTF-8 均 rc=2；邮箱域名允许无点。不读环境、git config，不沿用上一提交的身份。
- git rev-list 范围内每个提交的 author／committer，须从 git cat-file commit 原始行解析，
  姓名及邮箱均与规则精确相等（大小写敏感）。
- 平台合并须同时满足父≥2、committer精确匹配平台身份常量、web-flow验签通过，才豁免
  author／committer；Co-authored-by仍逐条核对。验签仅用随仓库公钥和临时GNUPGHOME，
  不读用户钥环、不联网；git verify-commit须rc=0且签名主钥指纹在固定集合，不能仅凭VALIDSIG
  或签名子钥放行。公钥缺失/不可读、缺受信主钥或gpg不可用均rc=2；其他验签失败按普通提交检查。
- squash仅在--allow-squash下评估（push到main使用，PR事件不得带）：父恰为1、平台提交者、
  同上验签通过，并且尾部Co-authored-by非空且逐条合规。push范围只有squash提交，不能证明
  覆盖PR全部作者；该义务由PR事件逐提交检查和合并时人工自核共同保证。
- Co-authored-by交给git interpret-trailers --parse读取尾部块，格式须为Name <email>且身份在表内。
  编写身份按Author与合法尾行的并集去重；普通提交尾行不得等于Author，squash允许相同；
  同一身份重复尾行不判违规。正文中段不当尾行，畸形尾行不得回退为“无署名”。
- 非法rev、rev-list失败、浅克隆、对象缺失、空范围（未给--allow-empty）均rc=2。
  --no-replace-objects、GIT_NO_REPLACE_OBJECTS与GIT_GRAFT_FILE=/dev/null屏蔽replace和grafts。

输出只报短 SHA、字段与错误类别（可含既定登记姓名）；不得回显邮箱或任意输入值。退出码：0通过，1违规，2用法/环境/规则错误。
只做机械核对，不证明实际编写者或代提交授权；签名只确认GitHub平台自动合并，不评价普通提交签名。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_RULES = 'skills/luno-core/references/delegation.md'
SECTION_TITLE = 'Git 提交署名'
NAMES = (b'LUNO', b'FORGE', b'LENS', b'Claude Opus 5.5', b'LIN student')
# 身份行形态：`author NAME <EMAIL> 1700000000 +0800`
IDENT_LINE = re.compile(rb'^(.*?) <([^<>]*)> (\d+) ([+-]\d{4})$')
# 邮箱字符集限定得比 RFC 窄：任何方括号／尖括号／空白／中文占位形态一律判为非法。
# 域名**不要求含点**：现役身份是刻意不可路由的本地地址（`名@local` 形态），仍须是合法地址形态。
EMAIL = re.compile(
    rb"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    rb"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*$")
COAUTHOR_VALUE = re.compile(rb'^(.*?) <([^<>]+)>$')
RC_OK, RC_VIOLATION, RC_ENV = 0, 1, 2

# 平台自动合并的提交者：GitHub web-flow 的公开地址（全平台合并提交统一使用，与用户无关）。
PLATFORM_NAME = b'GitHub'
PLATFORM_EMAIL = b'noreply@github.com'
# 随仓库的 web-flow 公钥：来自 https://github.com/web-flow.gpg（GitHub 官方文档指向的下载点，
# 2026-11-05 取得）。检查器**只**导入此文件，不读用户 keyring、不联网取钥。
WEBFLOW_KEY_FILE = 'tools/github-web-flow.gpg'
# 解析顺序：先取**脚本所在仓库**（CI 中为 guard 目录内的同名布局），再取当前工作目录；
# 两处都没有 → rc=2。绝不回落到用户 keyring 或网络取钥。
WEBFLOW_KEY_PATHS = (Path(__file__).resolve().parents[1] / WEBFLOW_KEY_FILE,
                     Path(WEBFLOW_KEY_FILE))
# 只信任**现用**主钥的指纹：968479A1AFF927E37D1A566BB5690EEEBB952194（uid「GitHub」）。
# 上述公钥文件保持 GitHub 官方原文件逐字节不变（不裁剪），其中另有 2024-01-16 已过期的旧钥
# 5DE3E0509C47EA3CF04A42D34AEE18F83AFDEB23（uid「GitHub (web-flow commit signing)」）——
# 该钥签的提交验签退出码非零，已按普通提交处理，故不再列入本表。
# 核实方式：导入后 `gpg --list-keys --with-colons --fingerprint` 取值；并用真实平台合并提交
# 3ca8abd（本公开快照仓库不含该历史对象，见旧私有 LucaLin233/Agent）的 `git verify-commit --raw`
# 交叉核对得到 VALIDSIG 968479A1…（2026-11-05）。
# 导入后公钥文件的指纹集合若**不含**本表任一项 → rc=2（环境不完整，不做任何豁免）。
# GitHub 轮换签名钥后，用新钥签的合并提交一律验签失败、检查器对其 fail-closed（按普通提交判违规）；
# 须人工核实新钥后，同步更新 `tools/github-web-flow.gpg` 与本表。
WEBFLOW_FINGERPRINTS = frozenset((
    '968479A1AFF927E37D1A566BB5690EEEBB952194',
))
GIT = ('git', '--no-replace-objects')


class Env(Exception):
    """用法／环境／规则错误（rc=2）：检查不完整，不得当成通过。"""


class Parser(argparse.ArgumentParser):
    """参数错误只报固定文案：argparse 默认会回显 `--rules <用户输入>` 等原始值。"""

    def error(self, _):
        self.exit(RC_ENV, '错误：参数无效\n')


class Rules:
    """身份表：名 → 邮箱 bytes。绝不把邮箱放进任何对外消息。"""

    def __init__(self, pairs):
        self.pairs = pairs  # {b'LUNO': b'...', b'FORGE': b'...'}

    def match(self, name, email):
        for cand, want in self.pairs.items():
            if name == cand and email == want:
                return cand
        return None

    def known(self, name, email):
        return self.match(name, email) is not None


def read_rules(path):
    """只认**精确整行标题**与**反引号包裹的完整身份声明** `Name <email>`。

    节标题必须整行等于 `## <SECTION_TITLE>`（不做包含匹配，`## Git 提交署名示例`
    与 `##非Git提交署名` 都不算）；名字允许含空格，取反引号内**完整**名字与邮箱，
    绝不按后缀/包含匹配截取（`NotLIN student`、`Fake LIN student`、前后空白变体
    都不会被当成登记身份）。节标题允许**行尾空白**（`rstrip` 后整行相等即可），
    但身份字段不 strip：邮箱两侧多余空白即判形态非法；姓名带额外空白则不匹配登记名
    （该名缺精确声明 → 闭锁 rc=2；额外未知名在五名完整时忽略）。
    """
    try:
        raw = path.read_bytes()
    except OSError:
        raise Env('规则文件不可读')
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        raise Env('规则文件不是 UTF-8')
    lines = text.split('\n')
    heading = '## ' + SECTION_TITLE
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == heading:
            start = i
            break
    if start is None:
        raise Env('规则文件缺少〈%s〉段' % SECTION_TITLE)
    body = []
    for line in lines[start + 1:]:
        if line.lstrip().startswith('#'):
            break
        body.append(line)
    section = '\n'.join(body)
    pairs = {}
    for name, value in ((m.group(1).encode('utf-8'), m.group(2).encode('utf-8'))
                        for m in re.finditer(r'`([^`<>\n]+) <([^`<>\n]*)>`', section)):
        if name not in NAMES:
            continue
        if name in pairs:
            raise Env('规则〈%s〉段 %s 身份重复（%d 处，不回退）'
                      % (SECTION_TITLE, name.decode('utf-8'), 2))
        if not EMAIL.match(value):
            raise Env('规则〈%s〉段 %s 身份形态非法（占位、带空白或非邮箱）'
                      % (SECTION_TITLE, name.decode('utf-8')))
        pairs[name] = value
    for name in NAMES:
        if name not in pairs:
            raise Env('规则〈%s〉段缺少 %s 身份（不回退）'
                      % (SECTION_TITLE, name.decode('utf-8')))
    seen = {}
    for name, value in pairs.items():
        if value in seen:
            raise Env('规则〈%s〉段身份指向同一邮箱（%d 个身份，不回退）'
                      % (SECTION_TITLE, len(pairs)))
        seen[value] = name
    return Rules(pairs)


def git(*args, **kw):
    """始终屏蔽对象替换与嫁接（环境变量与命令行双保险），再跑 git。"""
    env = dict(os.environ)
    env['GIT_NO_REPLACE_OBJECTS'] = '1'
    env['GIT_GRAFT_FILE'] = os.devnull      # 令 .git/info/grafts 不参与
    env.update(kw.pop('env', {}))
    proc = subprocess.run(GIT + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=env, **kw)
    return proc.returncode, proc.stdout, proc.stderr


def run(argv, **kw):
    """跑任意外部命令（gpg 等），环境在 os.environ 之上叠加。"""
    env = dict(os.environ)
    env.update(kw.pop('env', {}))
    proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=env, **kw)
    return proc.returncode, proc.stdout, proc.stderr


def rev(rev):
    rc, out, _ = git('rev-parse', '--verify', '--quiet', rev + '^{commit}')
    if rc != 0 or not out.strip():
        raise Env('rev 无效或不是提交')      # 不回显输入值（可能被塞进地址等任意串）
    return out.strip().decode('ascii')


def header_pairs(raw):
    head = raw.split(b'\n\n', 1)[0]
    items = []
    for line in head.split(b'\n'):
        if line.startswith(b' ') and items:      # 多行头（gpgsig）续行
            items[-1][1] += b'\n' + line
            continue
        key, _, val = line.partition(b' ')
        items.append([key, val])
    return items


def ident_key(items, key):
    for k, val in items:
        if k == key:
            m = IDENT_LINE.match(val)
            if not m:
                return key.decode('ascii'), None, None
            return key.decode('ascii'), m.group(1), m.group(2)
    return key.decode('ascii'), None, None


def coauthors(message):
    """消息尾部 trailer 块里的 Co-authored-by 值（原序）：交给 git 自身解析，口径一致。"""
    rc, out, _ = git('-c', 'trailer.separators=:', 'interpret-trailers', '--parse',
                     input=message)
    if rc:
        raise Env('提交 trailer 解析失败')
    return [line.partition(b':')[2] for line in out.splitlines()
            if line.partition(b':')[0].lower() == b'co-authored-by']


class WebFlow:
    """临时 GNUPGHOME：只导入随仓库的 web-flow 公钥，验证平台合并签名，退出即弃。"""

    def __init__(self):
        self.home = None
        self.ready = False

    def _env(self):
        env = {'GNUPGHOME': self.home, 'LC_ALL': 'C'}
        return env

    def _prepare(self):
        if self.ready:
            return
        key_path = next((x for x in WEBFLOW_KEY_PATHS if x.is_file()), None)
        if key_path is None:
            raise Env('缺少随仓库的 web-flow 公钥文件')
        try:
            blob = key_path.read_bytes()
        except OSError:
            raise Env('缺少随仓库的 web-flow 公钥文件')
        if not blob:
            raise Env('缺少随仓库的 web-flow 公钥文件')
        if shutil.which('gpg') is None:
            # fail-closed：验证能力缺失时无法区分「平台合并」与「伪装的 GitHub 身份」，整批报环境错误
            raise Env('缺少 gpg：无法验证平台合并签名（检查不完整）')
        self.home = tempfile.mkdtemp(prefix='ci-webflow.')
        os.chmod(self.home, 0o700)
        rc, _, _ = run(('gpg', '--batch', '--quiet', '--import', str(key_path)),
                       env=self._env())
        if rc != 0:
            raise Env('web-flow 公钥导入失败')
        rc, out, _ = run(('gpg', '--batch', '--with-colons', '--fingerprint'),
                         env=self._env())
        if rc != 0:
            raise Env('web-flow 公钥读取失败')
        found = set()
        want_primary = False
        for line in out.decode('utf-8', 'replace').splitlines():
            field = line.split(':')
            if field[0] == 'pub':
                want_primary = True
            elif field[0] == 'sub':
                want_primary = False
            elif field[0] == 'fpr' and want_primary and len(field) > 9:
                found.add(field[9])
                want_primary = False
        # 只要求「本表 ⊆ 公钥文件」：官方原文件不裁剪，可能含已过期的历史钥，但都不被信任
        if not set(WEBFLOW_FINGERPRINTS) <= found:
            raise Env('web-flow 公钥指纹与代码固定值不一致')
        self.ready = True

    def verify(self, sha):
        """签名有效且主钥指纹在固定集合内 → True；其余（含验证失败）→ False。

        退出码非零**一律**不豁免：`git verify-commit --raw` 的退出码是唯一成功判据，
        不再以输出里是否出现 VALIDSIG 兜底（过期钥签的提交既报 VALIDSIG 又 rc=1）。
        指纹取 `VALIDSIG` 行末位的主钥指纹：子钥签发时 `parts[2]` 是签名子钥，不作判据。
        """
        self._prepare()
        rc, _, err = git('verify-commit', '--raw', sha, env=self._env())
        text = err
        if rc != 0:
            return False
        for bad in (b'BADSIG', b'ERRSIG', b'NO_PUBKEY', b'REVKEYSIG'):
            if bad in text:
                return False
        fprs = []
        for line in text.splitlines():
            if line.startswith(b'[GNUPG:] VALIDSIG '):
                parts = line.split()
                if len(parts) < 12:
                    return False
                fprs.append(parts[11].decode('ascii', 'replace').upper())
        return bool(fprs) and all(f in WEBFLOW_FINGERPRINTS for f in fprs)

    def close(self):
        if self.home:
            subprocess.run(('gpgconf', '--kill', 'all'), stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, env=dict(os.environ, **self._env()))
            shutil.rmtree(self.home, ignore_errors=True)
            self.home = None


def check_commit(rules, sha, webflow, allow_squash=False):
    """返回 (问题类别列表, 豁免种类 'platform'／'squash'／'')。类别里不含邮箱。"""
    rc, raw, _ = git('cat-file', 'commit', sha)
    if rc != 0:
        raise Env('提交对象缺失：%s' % sha[:7])
    items = header_pairs(raw)
    parents = [v for k, v in items if k == b'parent']
    problems = []
    _, cname, cemail = ident_key(items, b'committer')
    kind = ''
    platform_committer = cname == PLATFORM_NAME and cemail == PLATFORM_EMAIL
    if len(parents) >= 2 and platform_committer and webflow.verify(sha):
        kind = 'platform'                   # 仅凭可信签名豁免；否则按普通提交检查
    elif allow_squash and len(parents) == 1 and platform_committer and webflow.verify(sha):
        kind = 'squash'                     # 单父 + 平台提交者 + 可信签名：收口事件放行
    if not kind:
        author = {}
        for key in (b'author', b'committer'):
            field, name, email = ident_key(items, key)
            if name is None:
                problems.append((field, '身份行形态非法或缺失'))
                continue
            if not rules.known(name, email):
                problems.append((field, '身份不在署名表内'))
            if key == b'author':
                author = {'name': name, 'email': email}
    else:
        _, aname, aemail = ident_key(items, b'author')
        author = {'name': aname, 'email': aemail}
    _, _, message = raw.partition(b'\n\n')
    seen = []
    trailer = coauthors(message)
    if kind == 'squash' and not trailer:
        problems.append(('Co-authored-by', 'squash 提交缺少 Co-authored-by'))
    for index, value in enumerate(trailer, 1):
        label = 'Co-authored-by#%d' % index
        value = value.lstrip()              # git 解析后可能保留分隔符后的空白
        m = COAUTHOR_VALUE.match(value)
        if not m or not m.group(1).strip():
            problems.append((label, '格式非 Name <email>'))
            continue
        name, email = m.group(1), m.group(2)
        if not rules.known(name, email):
            problems.append((label, '身份不在署名表内'))
        # 编写身份 = Author ∪ 合法尾部署名，按身份去重：同一身份写多行只计一次，不判违规。
        # 「尾行与 Author 相同」只对普通提交判违规；squash 的 Author 是 PR 内最后一个提交的
        # 作者，收口者按原字节逐个提交各写一行时必然与 Author 重合，故放行。
        if kind != 'squash' and author.get('name') == name and author.get('email') == email:
            problems.append((label, '与 Author 相同'))
        if (name, email) in seen:
            continue
        seen.append((name, email))
    return problems, kind


def main(argv):
    ap = Parser(prog='check-commit-identities.py',
                description='按规则文件〈Git 提交署名〉段机械核对提交 author／committer／Co-authored-by。')
    ap.add_argument('--base', required=True, help='范围起点（不含），如已核基线提交')
    ap.add_argument('--head', required=True, help='范围终点（含），如 HEAD')
    ap.add_argument('--rules', default=DEFAULT_RULES, help='身份单真源规则文件（默认仓库内 %s）'
                    % DEFAULT_RULES)
    ap.add_argument('--allow-empty', action='store_true', help='范围无提交时不判失败')
    ap.add_argument('--allow-squash', action='store_true',
                    help='放行单父、Committer 为平台且验签通过的 squash 提交（仅 push 收口事件使用；'
                         'PR 事件不得给，仍逐提交核对）')
    args = ap.parse_args(argv)

    webflow = WebFlow()
    try:
        rules_path = Path(args.rules)
        if not rules_path.is_absolute() and not rules_path.exists():
            rc, out, _ = git('rev-parse', '--show-toplevel')
            if rc == 0 and out.strip():
                cand = Path(out.strip().decode('utf-8', 'surrogateescape')) / rules_path
                if cand.exists():
                    rules_path = cand
        rules = read_rules(rules_path)
        rc, out, _ = git('rev-parse', '--is-shallow-repository')
        if rc != 0:
            raise Env('不在 git 仓库内或 git 不可用')
        if out.strip() == b'true':
            raise Env('浅克隆：历史不完整，无法核对范围（请 fetch-depth: 0）')
        base, head = rev(args.base), rev(args.head)
        rc, out, err = git('rev-list', '--reverse', base + '..' + head)
        if rc != 0:
            raise Env('范围非法：%s..%s' % (base[:7], head[:7]))
        commits = [x.decode('ascii') for x in out.split()]
        if not commits:
            if args.allow_empty:
                print('空范围：%s..%s 无提交（--allow-empty 已给）' % (base[:7], head[:7]))
                return RC_OK
            raise Env('空范围：%s..%s 无提交（未给 --allow-empty）' % (base[:7], head[:7]))
        bad = 0
        platform = 0
        squash = 0
        for sha in commits:
            problems, kind = check_commit(rules, sha, webflow, args.allow_squash)
            if kind == 'platform':
                platform += 1
                print('%s platform 平台合并（签名经 web-flow 公钥验证通过），跳过身份校验'
                      % sha[:7])
            elif kind == 'squash':
                squash += 1
                print('%s squash 平台 squash 提交（单父、签名经 web-flow 公钥验证通过），'
                      '跳过身份校验并核对 Co-authored-by' % sha[:7])
            for field, category in problems:
                bad += 1
                print('%s %s %s' % (sha[:7], field, category))
    except Env as exc:
        print('错误：%s' % exc, file=sys.stderr)
        return RC_ENV
    except OSError as exc:      # git 不可用／路径不可访问等：检查不完整，按环境错误处理
        print('错误：检查未能完成（%s）' % exc.__class__.__name__, file=sys.stderr)
        return RC_ENV
    finally:
        webflow.close()
    if bad:
        print('检查 %d 个提交：%d 处违规（平台合并 %d 个、squash %d 个跳过身份校验）'
              % (len(commits), bad, platform, squash))
        return RC_VIOLATION
    print('检查 %d 个提交：通过（平台合并 %d 个、squash %d 个跳过身份校验）'
          % (len(commits), platform, squash))
    return RC_OK


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))

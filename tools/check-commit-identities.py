#!/usr/bin/env python3
"""提交署名机械检查：规则单真源 → 逐提交字节比对。

判据（全部为**可复核的字节事实**，不做启发式猜测）：
  1．身份单真源：从 `--rules` 指定的规则文件（默认 `skills/luno-core/references/delegation.md`）
     〈Git 提交署名〉段**磁盘 bytes** 取**规则登记的每个精确身份**（完整声明 `Name <email>`）各一处，构成精确身份对集合。姓名白名单由本文件 `NAMES` 固定：新增姓名须在规则与本文件
     两处同批；邮箱一律从规则的精确声明读取，不在此硬写（**不存在「动态开放身份」**，规则里
     多出未知名不会自动放行）。
     段缺失、身份缺失／重复、形态非法（无 `@`、含邮箱字符集外字符＝方括号等占位形态、两侧
     带空白）、读取失败 → 非零退出（**不回退**：不读环境变量、不读 git config、不沿用上一提交
     身份）。规则值**不做 strip 归一化**，但两类字段判法不同：邮箱两侧多余空白即判形态非法；
     姓名带额外空白则不匹配登记名（该名缺精确声明 → 闭锁 rc=2；额外未知名在五名完整时忽略，
     不因忽略而放宽）。
  2．逐提交：`git rev-list <base>..<head>` 的每个提交读 `git cat-file commit` **原始字节**，
     按提交对象的 author／committer 行解析「名 + 邮箱」bytes，须**精确等于**（大小写敏感）
     规则登记的某个精确身份。
  3．平台合并**只凭可信签名豁免**：须同时满足
     ① 父 ≥ 2；
     ② committer 行精确等于平台提交者 `GitHub <noreply@github.com>`（该地址是 GitHub 的公开
        平台地址，与用户个人的 GitHub noreply 转发地址无关）；
     ③ `git verify-commit` 在**临时 GNUPGHOME**（只导入随仓库的 `tools/github-web-flow.gpg`）
        下退出码为 0（非零一律不豁免，不看输出里有没有 `VALIDSIG`：已过期／已撤销钥签的
        提交既报 VALIDSIG 又 rc≠0），且签名主钥指纹属于本文件 `WEBFLOW_FINGERPRINTS`
        固定集合（只含现用钥）。
     满足才报 `platform`，跳过 author／committer 身份校验；`Co-authored-by` **仍逐条核对**。
     不满足即按普通提交检查（`GitHub` 不在署名表内，必然违规 → rc=1）。
     公钥文件缺失／无法读、其主钥指纹不含本文件固定值、gpg 不可用 → rc=2（环境不完整，
     fail-closed：宁可整批报错，也不把「验证不了」当成「不是平台合并」或「通过」）。
  3b．squash 提交（仅在 `--allow-squash` 时评估，供 push 到 main 的收口事件用；PR 事件一律不带该
     参数，仍逐提交核对）：须同时满足 ① 父**恰为 1**；② committer 行精确等于平台提交者；
     ③ 同上验签通过；④ 尾部 `Co-authored-by` **非空**且逐条合规（格式、身份在表内）。编写身份
     按 Author 与合法尾部署名的**并集去重**判定：同一身份写多行只计一次，且允许与 Author 相同
     （squash 的 Author 就是 PR 内最后一个提交的作者，收口者按原字节各写一行时必然重合）。
     满足才报 `squash` 并跳过 author／committer 身份校验。
     「覆盖 PR 内全部作者」**不在本工具可判范围**：push 事件的 `before..after` 只含 squash 这一
     个提交，PR 内原始提交不在该范围（也未取 `refs/pull/*`），故无法机械比对作者全集；边界
     由合并时的人工自核（规则〈Git 提交署名〉）与 PR 事件对原提交的逐个核对共同保证。
  4．`Co-authored-by:` 取自消息**尾部 trailer 块**（交由 `git interpret-trailers --parse` 解析，
     与 git 自身口径一致）：格式须为 `Name <email>`，身份须精确等于规则登记的某个精确身份。
     编写身份按 Author 与尾部署名的并集去重：普通提交的尾行**不得**与 Author 相同（判违规），
     squash 提交放行；同一身份的重复尾行按去重处理，不判违规。
  5．环境不可信即停：rev 非法、`rev-list` 失败、浅克隆、对象缺失、规则文件不可读／非 UTF-8、
     空范围（未给 `--allow-empty`）→ 非零退出，不把「未检到」当「通过」。
     另屏蔽对象替换与嫁接（`--no-replace-objects` + `GIT_NO_REPLACE_OBJECTS`，
     `GIT_GRAFT_FILE=/dev/null` 使 `info/grafts` 不参与），避免用 `git replace`／grafts 改写历史绕过。

输出**只报短 SHA、字段与错误类别**：任何情况下都不打印邮箱（也不打印名），即使输入含畸形值。
退出码：0 通过；1 存在违规；2 用法／环境／规则错误（检查不完整）。

边界：本工具只做**机械**核对，不证明「提交确实是实际编写者所写」——署名真实性与代提交是否
经授权仍需人工确认（见规则〈Git 提交署名〉末句）；签名只用于确认「这是 GitHub 平台的自动合并」，
不评价普通提交的签名状态。
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

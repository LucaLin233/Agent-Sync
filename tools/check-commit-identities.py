#!/usr/bin/env python3
"""提交署名机械检查：<base>..<head> 每个提交的 author／committer／Co-authored-by 须按字节
（大小写敏感）等于规则文件〈Git 提交署名〉段登记的身份之一。

- 身份只取自规则文件：整行标题 `## Git 提交署名` 下反引号内的完整声明 `Name <email>`，
  名字须逐字节等于 NAMES 之一（新增姓名须与规则同批改），其他声明忽略。段或登记名缺失、
  重复、同邮箱、邮箱形态非法（占位、两侧空白）→ rc=2，不回退到环境变量、git config 或上一提交。
- 平台合并（≥2 父）与 squash（恰 1 父，仅 --allow-squash，供 push 到 main 使用）只在 committer
  为 `GitHub <noreply@github.com>` 且 web-flow 签名验证通过时跳过 author／committer 校验；
  Co-authored-by 仍逐条核对，squash 还须至少一条。验签只用随仓库的公钥与临时 GNUPGHOME，
  以 `git verify-commit` 退出码为准；gpg 或公钥不可用 → rc=2（fail-closed）。
- Co-authored-by 取自尾部 trailer 块（git interpret-trailers 口径），格式须为 `Name <email>`；
  普通提交的尾行不得与 Author 相同，同一身份重复只算一次。squash 无法核对 PR 内全部作者
  （push 范围只有 squash 本身），由 PR 事件逐提交核对与合并时人工自核保证。
- 浅克隆、rev 非法、对象缺失、空范围（未给 --allow-empty）→ rc=2；屏蔽 git replace 与 grafts。

输出只含短 SHA、字段、类别与登记名，不含邮箱。退出码：0 通过，1 违规，2 用法／环境／规则错误。
只做机械核对，不证明署名真实或代提交已获授权。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 身份规则单真源；〈Git 提交署名〉段迁到别的文件时改这一行（并同步 tests/test_paths.py 的 identity 选路）。
DEFAULT_RULES = 'skills/luno-core/references/review.md'
SECTION_TITLE = 'Git 提交署名'
NAMES = (b'LUNO', b'FORGE', b'LENS', b'Claude Opus 5.5', b'LIN student')
IDENT_LINE = re.compile(rb'^(.*?) <([^<>]*)> (\d+) ([+-]\d{4})$')
# 比 RFC 窄，拒绝方括号、空白等占位形态；域名可以无点（现役身份是不可路由的 `名@local`）。
EMAIL = re.compile(
    rb"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    rb"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*$")
COAUTHOR_VALUE = re.compile(rb'^(.*?) <([^<>]+)>$')
RC_OK, RC_VIOLATION, RC_ENV = 0, 1, 2
PLATFORM = (b'GitHub', b'noreply@github.com')  # GitHub web-flow 的公开提交者，与个人地址无关
# GitHub 官方 https://github.com/web-flow.gpg 原文件（含已过期旧钥，不裁剪）；只导入它，不读用户 keyring、不联网。
WEBFLOW_KEY = Path(__file__).resolve().parents[1] / 'tools/github-web-flow.gpg'
# 只信任现用主钥。GitHub 轮换签名钥后，新钥签的合并提交会验签失败并按普通提交判违规；
# 须人工核实新钥后同步更新公钥文件与本表。
WEBFLOW_FINGERPRINTS = frozenset((
    '968479A1AFF927E37D1A566BB5690EEEBB952194',
))
GIT = ('git', '--no-replace-objects')


class Env(Exception):
    """用法／环境／规则错误（rc=2）：检查不完整，不得当作通过。"""


class Parser(argparse.ArgumentParser):
    def error(self, _):  # 默认会回显原始参数值
        self.exit(RC_ENV, '错误：参数无效\n')


def read_rules(path):
    """→ {名: 邮箱}（bytes）。名字与邮箱都不 strip：名字带空白即不是登记名，邮箱带空白即形态非法。"""
    try:
        text = path.read_bytes().decode('utf-8')
    except OSError:
        raise Env('规则文件不可读')
    except UnicodeError:
        raise Env('规则文件不是 UTF-8')
    lines = text.split('\n')
    start = next((i for i, line in enumerate(lines) if line.rstrip() == '## ' + SECTION_TITLE), None)
    if start is None:
        raise Env('规则文件缺少〈%s〉段' % SECTION_TITLE)
    body = []
    for line in lines[start + 1:]:
        if line.lstrip().startswith('#'):
            break
        body.append(line)
    rules = {}
    # 只取完整声明：`NotLIN student <…>` 不会被截成 `LIN student <…>`
    for m in re.finditer(r'`([^`<>\n]+) <([^`<>\n]*)>`', '\n'.join(body)):
        name, value = m.group(1).encode('utf-8'), m.group(2).encode('utf-8')
        if name not in NAMES:
            continue
        if name in rules:
            raise Env('规则〈%s〉段 %s 身份重复（不回退）' % (SECTION_TITLE, m.group(1)))
        if not EMAIL.match(value):
            raise Env('规则〈%s〉段 %s 身份形态非法（占位、带空白或非邮箱）' % (SECTION_TITLE, m.group(1)))
        rules[name] = value
    for name in NAMES:
        if name not in rules:
            raise Env('规则〈%s〉段缺少 %s 身份（不回退）' % (SECTION_TITLE, name.decode('utf-8')))
    if len(set(rules.values())) < len(rules):
        raise Env('规则〈%s〉段身份指向同一邮箱（%d 个身份，不回退）' % (SECTION_TITLE, len(rules)))
    return rules


def run(argv, env=None, **kw):
    proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=dict(os.environ, **(env or {})), **kw)
    return proc.returncode, proc.stdout, proc.stderr


def git(*args, env=None, **kw):
    """屏蔽对象替换与嫁接（命令行与环境变量双保险）后运行 git。"""
    base = {'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_GRAFT_FILE': os.devnull}
    return run(GIT + args, env=dict(base, **(env or {})), **kw)


def rev(name):
    rc, out, _ = git('rev-parse', '--verify', '--quiet', name + '^{commit}')
    if rc != 0 or not out.strip():
        raise Env('rev 无效或不是提交')  # 不回显输入值
    return out.strip().decode('ascii')


def headers(raw):
    """提交头 → [[键, 值]]；以空格开头的续行（gpgsig 等）并入上一条。"""
    items = []
    for line in raw.split(b'\n\n', 1)[0].split(b'\n'):
        if line.startswith(b' ') and items:
            items[-1][1] += b'\n' + line
        else:
            key, _, val = line.partition(b' ')
            items.append([key, val])
    return items


def ident(items, key):
    """第一条 `key` 头的 (名, 邮箱)；缺失或形态非法 → (None, None)。"""
    for k, val in items:
        if k == key:
            m = IDENT_LINE.match(val)
            return (m.group(1), m.group(2)) if m else (None, None)
    return None, None


def coauthors(message):
    rc, out, _ = git('-c', 'trailer.separators=:', 'interpret-trailers', '--parse', input=message)
    if rc:
        raise Env('提交 trailer 解析失败')
    return [line.partition(b':')[2] for line in out.splitlines()
            if line.partition(b':')[0].lower() == b'co-authored-by']


def primary_fingerprints(colons):
    """`gpg --with-colons --fingerprint` 输出里各主钥（pub 后第一条 fpr）的指纹。"""
    found, primary = set(), False
    for line in colons.decode('utf-8', 'replace').splitlines():
        field = line.split(':')
        if field[0] in ('pub', 'sub'):
            primary = field[0] == 'pub'
        elif field[0] == 'fpr' and primary and len(field) > 9:
            found.add(field[9])
            primary = False
    return found


class WebFlow:
    """临时 GNUPGHOME，只导入随仓库的 web-flow 公钥；首次需要验签时准备，退出即弃。"""

    def __init__(self):
        self.home = None
        self.ready = False

    def _env(self):
        return {'GNUPGHOME': self.home, 'LC_ALL': 'C'}

    def _prepare(self):
        if self.ready:
            return
        try:
            blob = WEBFLOW_KEY.read_bytes()
        except OSError:
            blob = b''
        if not blob:
            raise Env('缺少随仓库的 web-flow 公钥文件')
        if shutil.which('gpg') is None:
            raise Env('缺少 gpg：无法验证平台合并签名（检查不完整）')
        self.home = tempfile.mkdtemp(prefix='ci-webflow.')
        os.chmod(self.home, 0o700)
        if run(('gpg', '--batch', '--quiet', '--import', str(WEBFLOW_KEY)), env=self._env())[0]:
            raise Env('web-flow 公钥导入失败')
        rc, out, _ = run(('gpg', '--batch', '--with-colons', '--fingerprint'), env=self._env())
        if rc != 0:
            raise Env('web-flow 公钥读取失败')
        if not WEBFLOW_FINGERPRINTS <= primary_fingerprints(out):
            raise Env('web-flow 公钥指纹与代码固定值不一致')
        self.ready = True

    def verify(self, sha):
        """退出码 0、无坏签名标记、且每条 VALIDSIG 末位的主钥指纹都在固定集合内才算通过。

        只认退出码：过期钥的好签名会同时报 VALIDSIG 与非零退出码。parts[2] 可能是签名子钥，不作判据。
        """
        self._prepare()
        rc, _, err = git('verify-commit', '--raw', sha, env=self._env())
        if rc != 0 or any(bad in err for bad in (b'BADSIG', b'ERRSIG', b'NO_PUBKEY', b'REVKEYSIG')):
            return False
        fprs = []
        for line in err.splitlines():
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
    """→ ([(字段, 类别)], 豁免种类 'platform'／'squash'／'')。类别不含邮箱。"""
    rc, raw, _ = git('cat-file', 'commit', sha)
    if rc != 0:
        raise Env('提交对象缺失：%s' % sha[:7])
    items = headers(raw)
    parents = sum(1 for k, _ in items if k == b'parent')
    by_platform = ident(items, b'committer') == PLATFORM
    kind = ''
    if by_platform and parents >= 2 and webflow.verify(sha):
        kind = 'platform'
    elif by_platform and allow_squash and parents == 1 and webflow.verify(sha):
        kind = 'squash'
    problems = []
    if not kind:
        for key in (b'author', b'committer'):
            name, email = ident(items, key)
            if name is None:
                problems.append((key.decode(), '身份行形态非法或缺失'))
            elif rules.get(name) != email:
                problems.append((key.decode(), '身份不在署名表内'))
    author = ident(items, b'author')
    trailer = coauthors(raw.partition(b'\n\n')[2])
    if kind == 'squash' and not trailer:
        problems.append(('Co-authored-by', 'squash 提交缺少 Co-authored-by'))
    for index, value in enumerate(trailer, 1):
        label = 'Co-authored-by#%d' % index
        m = COAUTHOR_VALUE.match(value.lstrip())
        if not m or not m.group(1).strip():
            problems.append((label, '格式非 Name <email>'))
            continue
        if rules.get(m.group(1)) != m.group(2):
            problems.append((label, '身份不在署名表内'))
        # squash 的 Author 是 PR 内最后一个提交的作者，收口者逐个写尾行时必然与之重合
        if kind != 'squash' and (m.group(1), m.group(2)) == author:
            problems.append((label, '与 Author 相同'))
    return problems, kind


def rules_path(arg):
    """相对路径先按当前目录，再按所在仓库根目录解析。"""
    path = Path(arg)
    if not path.is_absolute() and not path.exists():
        rc, out, _ = git('rev-parse', '--show-toplevel')
        if rc == 0 and out.strip():
            cand = Path(out.strip().decode('utf-8', 'surrogateescape')) / path
            if cand.exists():
                return cand
    return path


def main(argv):
    ap = Parser(prog='check-commit-identities.py',
                description='按规则文件〈Git 提交署名〉段机械核对提交 author／committer／Co-authored-by。')
    ap.add_argument('--base', required=True, help='范围起点（不含）')
    ap.add_argument('--head', required=True, help='范围终点（含）')
    ap.add_argument('--rules', default=DEFAULT_RULES, help='身份规则文件（默认 %(default)s）')
    ap.add_argument('--allow-empty', action='store_true', help='范围无提交时不判失败')
    ap.add_argument('--allow-squash', action='store_true',
                    help='放行经验签的平台 squash 提交（仅 push 到 main 使用；PR 事件不得给）')
    args = ap.parse_args(argv)

    webflow = WebFlow()
    try:
        rules = read_rules(rules_path(args.rules))
        rc, out, _ = git('rev-parse', '--is-shallow-repository')
        if rc != 0:
            raise Env('不在 git 仓库内或 git 不可用')
        if out.strip() == b'true':
            raise Env('浅克隆：历史不完整，无法核对范围（请 fetch-depth: 0）')
        base, head = rev(args.base), rev(args.head)
        rc, out, _ = git('rev-list', '--reverse', base + '..' + head)
        if rc != 0:
            raise Env('范围非法：%s..%s' % (base[:7], head[:7]))
        commits = [x.decode('ascii') for x in out.split()]
        if not commits:
            if args.allow_empty:
                print('空范围：%s..%s 无提交（--allow-empty 已给）' % (base[:7], head[:7]))
                return RC_OK
            raise Env('空范围：%s..%s 无提交（未给 --allow-empty）' % (base[:7], head[:7]))
        bad = platform = squash = 0
        for sha in commits:
            problems, kind = check_commit(rules, sha, webflow, args.allow_squash)
            if kind == 'platform':
                platform += 1
                print('%s platform 平台合并（签名经 web-flow 公钥验证通过），跳过身份校验' % sha[:7])
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
    except OSError as exc:  # git 不可用、路径不可访问等
        print('错误：检查未能完成（%s）' % exc.__class__.__name__, file=sys.stderr)
        return RC_ENV
    finally:
        webflow.close()
    summary = '检查 %d 个提交：%s（平台合并 %d 个、squash %d 个跳过身份校验）'
    if bad:
        print(summary % (len(commits), '%d 处违规' % bad, platform, squash))
        return RC_VIOLATION
    print(summary % (len(commits), '通过', platform, squash))
    return RC_OK


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))

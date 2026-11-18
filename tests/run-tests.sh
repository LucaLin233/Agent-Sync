#!/bin/sh
# 用法：sh tests/run-tests.sh [smoke|full|list|group G[,G…]|case NAME|select [FILE]|select-paths|render-paths]
#   smoke＝只跑结构守卫 tools/check-rules.py（任何非零含 rc=2 提示都记 FAIL）；
#   full＝用例表第 4 列为 1 的全部入口（含 smoke）；group/case 定向运行；
#   select-paths：stdin 为 NUL 分隔的变更路径，stdout 为 selector JSON；
#   select：读取该 JSON（文件参数或 stdin），合并去重后运行。
# 一轮原证：每入口 BEGIN 记 name/group，原样流式合并 stdout+stderr（不截断、不加前缀、不重打尾行），
# END 记原始 exitCode、unittest 摘要的 tests/skip（非 unittest 记 N/A，缺摘要记 unavailable）与单调耗时；
# 轮首打印完整 HEAD、HEAD tree、git 版本和 trackedState（dirty/unknown 不冒充该提交字节）。
# 聚合退出码：全成功 0、测试失败 1、选路/环境/基础设施/清理失败 2；原始子进程退出码始终保留；
# INT/TERM 清理后以 130/143 退出（SIGKILL 无法保证清理，不能报完成）。
# 子进程环境不继承调用方：由本脚本内唯一构造点重建白名单（不复制 os.environ 再删）；
# 调用方须先用 env -i 起最小白名单，这里只用其已核的 PATH，TMPDIR 默认 /tmp。
# 变更路径→必跑套件（机器表 tests/test_paths.py；本块与 render-paths 输出须一致）：
# >>> PATHS_RULES
#   宿主安装器、目标登记与入口配置 → host
#   固定认证读取 → auth
#   结构守卫或边登记 → gate
#   正文契约及既有用例 → body
#   Surge 包内文件、登记或包态测试 → surge 包态
#   Surge 脚本或脚本测试 → surge 脚本
#   脱敏实现与读取模板 → privacy
#   署名机械检查器、其测试与署名规则 → identity
#   LH 技能离线验收工具或工具测试 → verify
#   固定认证读取变更 → verify 消费者
#   正文契约变更 → verify 消费者
#   对象登记变更 → verify 消费者
#   Minis 本端验收工具或工具测试 → minis-verify
#   正文契约变更 → Minis 验收消费者
#   对象登记变更 → Minis 验收消费者
#   LH 窄采集工具或工具测试 → 采集
#   固定认证读取变更 → 采集消费者
#   窄采集变更 → 部署消费者
#   对象登记变更 → 采集消费者
#   LH 窄部署工具或工具测试 → 部署
#   离线验收或正文契约变更 → 部署消费者
#   对象登记变更 → 部署消费者
#   运行器、选路表或 CI 测试 workflow → auth 消费者
#   运行器、选路表或 CI 测试 workflow → identity 消费者
#   运行器、选路表或 CI 测试 workflow → verify 消费者
#   运行器、选路表或 CI 测试 workflow → minis-verify 消费者
#   运行器、选路表或 CI 测试 workflow → lh-wiring 消费者
#   运行器、信号与选路回归 → runner
#   按需包内校验（结构守卫＋技能包校验）与运行器变更 → 包内校验
#   运行器、选路表或 CI 测试 workflow → runner 消费者
#   运行器与聚合入口 → full
# <<<
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd) || exit 1
cd "$ROOT" || exit 1

case ${1:-} in
    select-paths) exec python3 -I -B tests/test_paths.py select-paths ;;
    render-paths) exec python3 -I -B tests/test_paths.py render ;;
esac

# 名称|分组|命令|进 full
# unittest 以模块名加载：文件名带连字符，discover 找不到；整模块导入后再收集用例。
CASES='
test-auth-call.py|auth|cd tests && python3 -B -m unittest -v test-auth-call|0
check-rules.py|smoke|python3 -B tools/check-rules.py|1
test-check-rules.sh|gate|sh tests/test-check-rules.sh|1
test-runner.sh|runner|sh tests/test-runner.sh|1
sync-all.sh|package|sh tools/sync-all.sh|0
test-body-contract.py|body|cd tests && python3 -B -m unittest -v test-body-contract|1
test-redact.py|privacy|cd tests && python3 -B -m unittest -v test-redact|1
test-surge-package.py|surge|cd tests && python3 -B -m unittest -v test-surge-package|1
test-surge-scripts.py|surge|cd tests && python3 -B -m unittest -v test-surge-scripts|1
test-commit-identities.py|identity|cd tests && python3 -B -m unittest -v test-commit-identities|0
test-lh-verify.py|verify|cd tests && python3 -B -m unittest -v test-lh-verify|0
test-minis-verify.py|minis-verify|cd tests && python3 -B -m unittest -v test-minis-verify|0
test-lh-collect.py|lh-wiring|cd tests && python3 -B -m unittest -v test-lh-collect|0
test-lh-deploy.py|lh-wiring|cd tests && python3 -B -m unittest -v test-lh-deploy|0
test-link-install.py|host|cd tests && python3 -B -m unittest -v test-link-install|0
'

mode=${1:-smoke}
arg=${2:-}
usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; }

pick() {  # pick KIND [ARG]：把一个选择器展开为用例名，每行一个
    printf '%s\n' "$CASES" | while IFS='|' read -r n g c f; do
        [ -n "$n" ] || continue
        case $1 in
            smoke) [ "$g" = smoke ] ;;
            full)  [ "$f" = 1 ] ;;
            group) case ",${2:-}," in *",$g,"*) true ;; *) false ;; esac ;;
            case)  [ "$n" = "${2:-}" ] ;;
            *) false ;;
        esac && echo "$n"
    done
}

want=' '
add() {  # 选不到任何入口的选择器按用法错误处理，不当作“已跑”
    hit=$(pick "$@")
    [ -n "$hit" ] || { echo "选择器未选中任何入口：$*" >&2; exit 2; }
    for n in $hit; do
        case $want in *" $n "*) ;; *) want="$want$n " ;; esac
    done
}

case $mode in
    smoke|full) add "$mode" ;;
    group|case) [ -n "$arg" ] || { usage >&2; exit 2; }; add "$mode" "$arg" ;;
    select)
        sels=$( { if [ -n "$arg" ]; then cat -- "$arg"; else cat; fi; } | python3 -I -B -c '
import json, re, sys
try:
    doc = json.load(sys.stdin)
except ValueError:
    doc = None
arity = {"smoke": 1, "full": 1, "group": 2, "case": 2}
ok = isinstance(doc, list) and doc and all(
    isinstance(s, list) and s and s[0] in arity and len(s) == arity[s[0]]
    and all(isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_.,-]+", x) for x in s)
    for s in doc)
if not ok:
    sys.exit("select：selector JSON 不合法（须为 [[\"full\"|\"smoke\"] 或 [\"group\"|\"case\", 名称] …]）")
print("\n".join(" ".join(s) for s in doc))
') || exit 2
        while read -r k a; do add "$k" ${a:+"$a"}; done <<EOF
$sels
EOF
        ;;
    list)
        printf '%s\n' "$CASES" | while IFS='|' read -r n g c f; do
            [ -n "$n" ] && printf '%-28s %-9s %s\n' "$n" "$g" "$([ "$f" = 1 ] && echo full)"
        done
        exit 0 ;;
    -h|--help|help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac

command -v python3 >/dev/null 2>&1 || { echo "运行基础设施不可用：缺少 python3" >&2; exit 2; }
# 监督段：独占 WORK 的创建/信号/清理与逐例原证都在这一个内联标准库进程里，不落持久日志。
exec python3 -I -B - "$mode" "$arg" "$want" "$CASES" "$ROOT" <<'PYEOF'
import os, re, select, shutil, signal, stat, subprocess, sys, time, traceback

MODE, ARG, WANT, CASES, ROOT = sys.argv[1:6]
OUT = sys.stdout.buffer
STOP = []


def say(line):
    OUT.write((line + '\n').encode('utf-8'))
    OUT.flush()


def die(msg, code=2):
    say('运行基础设施错误：%s' % msg)
    raise SystemExit(code)


def on_signal(signum, _frame):
    STOP.append(signum)


for _s in (signal.SIGINT, signal.SIGTERM):
    signal.signal(_s, on_signal)

want = WANT.split()
rows = [line.split('|') for line in CASES.strip().splitlines() if line.strip()]
if not rows or any(len(r) != 4 for r in rows):
    die('用例表格式异常')
names = [r[0] for r in rows]
if len(set(names)) != len(names):
    die('用例表存在重名入口')
if not want or [n for n in want if n not in names]:
    die('选择器未选中已登记入口：%s' % ' '.join(n for n in want if n not in names))
selected = [r for r in rows if r[0] in set(want)]
if len(selected) != len(set(want)):
    die('选择器入口数不符')

PATH = os.environ.get('PATH') or '/usr/bin:/bin'
TMP = os.environ.get('TMPDIR') or '/tmp'
if not TMP.startswith('/') or any(c in ('', '.', '..') for c in TMP.split('/')[1:]):
    die('TMPDIR 必须是绝对规范路径：%r' % TMP)


def chain(path):
    """从 / 逐组件 O_DIRECTORY|O_NOFOLLOW 打开，返回持有 fd 链（末项为目标）。"""
    fds = [os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)]
    try:
        for comp in path.split('/')[1:]:
            fds.append(os.open(comp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                               dir_fd=fds[-1]))
    except OSError as exc:
        die('无法按 nofollow 打开 %r：%s' % (path, exc.strerror))
    return fds


def ident(fd):
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode):
        die('持有 fd 不是目录')
    return (st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode))


def recheck(path, held):
    """祖先同轴重开并比对 identity tuple；不一致立即停。"""
    now = chain(path)
    try:
        if [ident(f) for f in now] != [ident(f) for f in held]:
            die('路径身份在持有期间变化：%r' % path)
    finally:
        for fd in now:
            os.close(fd)


def reopen_current():
    """从已锚定父 fd 按当前 NAME 真重开（O_DIRECTORY|O_NOFOLLOW）；打不开返回 None。"""
    try:
        return os.open(NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=PFD)
    except OSError:
        return None


ANC = []
PFD = RF1 = RF2 = None
NAME = WORK = None
work_attempted = False
root_verified = False


def build_child_env():
    """唯一构造点：从零重建白名单，不复制调用方环境；不含事件值、令牌、代理或生产变量。"""
    return {
        'PATH': PATH,
        'HOME': os.path.join(WORK, 'home'),
        'TMPDIR': os.path.join(WORK, 'tmp'),
        'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
        'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1', 'TZ': 'UTC',
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_ATTR_NOSYSTEM': '1',
        'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_LAZY_FETCH': '1',
        'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '/bin/false',
        'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.fsmonitor',
        'GIT_CONFIG_VALUE_0': 'false',
    }


child_env = None


def git(*args):
    return subprocess.run(('git',) + args, cwd=ROOT, env=child_env, stdin=subprocess.DEVNULL,
                          capture_output=True)


def gitval(*args):
    r = git(*args)
    return r.stdout.decode('utf-8', 'replace').strip() if r.returncode == 0 else 'unavailable'


def emit_header():
    """轮首版本与状态：trackedState 先看退出码，Git 失败一律 unknown，不冒充该提交字节。"""
    say('==== 运行 mode=%s%s → %s' % (MODE, (' ' + ARG) if ARG else '', ' '.join(want)))
    say('==== HEAD %s' % gitval('rev-parse', 'HEAD'))
    say('==== tree %s' % gitval('rev-parse', 'HEAD^{tree}'))
    say('==== git %s' % gitval('--version').replace('git version ', ''))
    _st = git('status', '--porcelain', '--untracked-files=normal')
    if _st.returncode != 0:
        _state = 'unknown'
    elif _st.stdout.strip():
        _state = 'dirty'
    else:
        _state = 'clean'
    say('==== trackedState %s' % _state)
    say('==== WORK %s（本轮独占，收尾删除）' % WORK)

RAN_RE = re.compile(rb'^Ran (\d+) tests? in ', re.M)
SKIP_RE = re.compile(rb'skipped=(\d+)')


def counts(data, cmd):
    if '-m unittest' not in cmd:
        return 'N/A', 'N/A'
    m = RAN_RE.search(data)
    if not m:
        return 'unavailable', 'unavailable'
    sk = SKIP_RE.findall(data)
    return m.group(1).decode(), (sk[-1].decode() if sk else '0')


def drain(p, chunks, limit):
    """把剩余原 bytes 读完并转发，最多等 limit 秒；读到 EOF 返回 True，超时仍未 EOF 返回 False。"""
    fd = p.stdout.fileno()
    end = time.monotonic() + limit
    while time.monotonic() < end:
        r, _, _ = select.select([fd], [], [], 0.1)
        if not r:
            continue
        b = os.read(fd, 65536)
        if not b:
            return True
        chunks.append(b)
        OUT.write(b)
        OUT.flush()
    return False


def halt(p):
    """只处理本轮 start_new_session 的进程组：INT/TERM，5 秒未退则 KILL 并 wait。"""
    sig = STOP[0]
    try:
        os.killpg(os.getpgid(p.pid), sig)
    except OSError:
        pass
    end = time.monotonic() + 5
    while time.monotonic() < end and p.poll() is None:
        time.sleep(0.05)
    if p.poll() is None:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except OSError:
            pass
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        die('无法确认本轮执行已停，保留 WORK %s' % WORK, 2)


ACTIVE = []


def group_gone(pgid):
    """只用 signal 0 判断已登记组是否消失；无法确证返回 False。"""
    try:
        os.killpg(pgid, 0)
        return False
    except ProcessLookupError:
        return True
    except OSError:
        return False


def confirm_stopped(pgid, sig):
    """按登记组兑现停止：先 sig，再 KILL，各等 5 秒，最终以 signal 0 确证消失。"""
    if group_gone(pgid):
        return True
    for _s in (sig, signal.SIGKILL):
        try:
            os.killpg(pgid, _s)
        except OSError:
            pass
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if group_gone(pgid):
                return True
            time.sleep(0.05)
    return group_gone(pgid)


def retire_own(p):
    """入口已结束且 leader 已回收：组确证消失就不再保留登记，避免轮末拿历史 PID 盲发信号。"""
    if group_gone(p.pid):
        try:
            ACTIVE.remove(p)
        except ValueError:
            pass


def stop_own():
    """只终止本轮 Popen（start_new_session 的进程组）：INT/TERM，5 秒未退则 KILL 并 wait。

    无法确认已停就返回 False，调用方据此保留 WORK，不无条件删除。
    """
    ok = True
    sig = STOP[0] if STOP else signal.SIGTERM
    for p in ACTIVE:
        if p.poll() is not None:
            p.wait()
            continue
        try:
            os.killpg(os.getpgid(p.pid), sig)
        except OSError:
            pass
        end = time.monotonic() + 5
        while time.monotonic() < end and p.poll() is None:
            time.sleep(0.05)
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except OSError:
                pass
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ok = False
    # leader 退出不等于本轮进程组停止：对本次 start_new_session 的组按既有 5 秒→KILL 契约
    # 兑现停止，再只用 signal 0 确证消失；未确证消失就保留 WORK（不扫描、不按名扫杀、不宣称为已回收）。
    for p in ACTIVE:
        if not confirm_stopped(p.pid, STOP[0] if STOP else signal.SIGTERM):
            say('==== cleanup 停止：本轮进程组 %d 仍在或无法确证停止，保留 %s' % (p.pid, WORK))
            ok = False
    return ok


def run_entry(cmd):
    p = subprocess.Popen(['sh', '-c', cmd], cwd=ROOT, env=child_env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    ACTIVE.append(p)
    fd = p.stdout.fileno()
    chunks = []
    while True:
        if STOP:
            halt(p)
            drain(p, chunks, 5)
            break
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            b = os.read(fd, 65536)
            if not b:
                break
            chunks.append(b)
            OUT.write(b)
            OUT.flush()
        if p.poll() is not None:
            # 入口已退出但后代仍持 stdout：先按本轮登记组确证停止，再限时读到 EOF；任一失败保留 WORK。
            if not confirm_stopped(p.pid, signal.SIGTERM):
                die('无法确证本轮进程组已停，保留 WORK %s' % WORK, 2)
            if not drain(p, chunks, 5):
                die('后代仍持 stdout 未读到 EOF，保留 WORK %s' % WORK, 2)
            break
    rc = p.wait()
    retire_own(p)
    return rc, b''.join(chunks)


def inspect_tree(fd):
    """只在根内 nofollow 检查类型/属主；不读正文、不跟链接目标。"""
    bad = []

    def walk(cur, prefix):
        for ent in os.scandir(cur):
            st = os.stat(ent.name, dir_fd=cur, follow_symlinks=False)
            rel = prefix + ent.name
            if stat.S_ISLNK(st.st_mode):
                continue
            if st.st_uid != os.geteuid():
                bad.append('%s(uid=%d)' % (rel, st.st_uid))
            elif stat.S_ISDIR(st.st_mode):
                sub = os.open(ent.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=cur)
                try:
                    walk(sub, rel + '/')
                finally:
                    os.close(sub)
            elif not stat.S_ISREG(st.st_mode):
                bad.append('%s(type=%o)' % (rel, stat.S_IFMT(st.st_mode)))

    walk(fd, '')
    return bad


def cleanup():
    try:
        recheck(TMP, ANC)
        cur = reopen_current()
        if cur is None:
            say('==== cleanup 停止：进入清理时当前 %s 无法 nofollow 重开，替身未触碰，保留 %s' % (NAME, NAME))
            return False
        a, b = ident(RF1), ident(cur)
        if b != a:
            os.close(cur)
            say('==== cleanup 停止：进入清理时当前 %s 非仍持有原根（原根 dev/ino %d/%d，现路径 dev/ino %d/%d），'
                '替身未触碰，保留 %s' % (NAME, a[0], a[1], b[0], b[1], NAME))
            return False
        try:
            st = os.fstat(cur)
            if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o700:
                say('==== cleanup 停止：WORK 属主/模式变化，保留 %s' % WORK)
                return False
            bad = inspect_tree(cur)
            if bad:
                say('==== cleanup 停止：根内归属/类型不明（%s），保留 %s' % (' '.join(bad[:5]), WORK))
                return False
        finally:
            os.close(cur)
        if not getattr(shutil.rmtree, 'avoids_symlink_attacks', False) \
                or os.unlink not in os.supports_dir_fd or os.rmdir not in os.supports_dir_fd:
            say('==== cleanup 停止：标准库 rmtree 不支持 dir_fd/防符号链接，保留 %s' % WORK)
            return False
        cur2 = reopen_current()
        if cur2 is None:
            say('==== cleanup 停止：删除前当前 %s 无法 nofollow 重开，替身未触碰，保留 %s' % (NAME, NAME))
            return False
        a2, b2 = ident(RF1), ident(cur2)
        if b2 != a2:
            os.close(cur2)
            say('==== cleanup 停止：删除前当前 %s 非仍持有原根（原根 dev/ino %d/%d，现路径 dev/ino %d/%d），'
                '替身未触碰，保留 %s' % (NAME, a2[0], a2[1], b2[0], b2[1], NAME))
            return False
        os.close(cur2)
        shutil.rmtree(NAME, dir_fd=PFD)
    except OSError as exc:
        say('==== cleanup 失败：%s，已知残留 %s' % (exc, WORK))
        return False
    try:
        os.stat(NAME, dir_fd=PFD, follow_symlinks=False)
    except FileNotFoundError:
        say('==== cleanup 完成：%s 已不在原父目录' % NAME)
        return True
    say('==== cleanup 失败：%s 仍存在' % NAME)
    return False


npass = nfail = 0
done = []
cleaned = False
infra = None
interrupted = None
t_all = time.monotonic()
try:
    work_attempted = True
    ANC = chain(TMP)
    PFD = ANC[-1]
    recheck(TMP, ANC)
    proc = subprocess.run(['mktemp', '-d', 'run-tests-XXXXXX'],
                          env={'PATH': PATH, 'TMPDIR': TMP, 'LC_ALL': 'C.UTF-8'},
                          preexec_fn=lambda: os.fchdir(PFD), pass_fds=(PFD,),
                          stdin=subprocess.DEVNULL, capture_output=True)
    if proc.returncode != 0:
        die('mktemp 创建 WORK 失败：%r' % proc.stderr.decode('utf-8', 'replace').strip())
    lines = proc.stdout.decode('utf-8', 'replace').splitlines()
    if len(lines) != 1 or not re.fullmatch(r'run-tests-[A-Za-z0-9]{6,}', lines[0]):
        die('mktemp 返回名不合规：%r' % proc.stdout)
    NAME = lines[0]
    WORK = os.path.join(TMP, NAME)
    RF1 = os.open(NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=PFD)
    RF2 = os.open(NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=PFD)
    if ident(RF1) != ident(RF2):
        die('WORK 同名重开身份不一致')
    _st = os.fstat(RF1)
    if _st.st_uid != os.geteuid() or stat.S_IMODE(_st.st_mode) != 0o700:
        die('WORK 属主或模式异常（uid=%d mode=%o）' % (_st.st_uid, stat.S_IMODE(_st.st_mode)))
    recheck(TMP, ANC)
    root_verified = True
    for _d in ('home', 'tmp'):
        os.mkdir(_d, 0o700, dir_fd=RF1)
        _fd = os.open(_d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=RF1)
        os.close(_fd)
    child_env = build_child_env()
    emit_header()
    for name, grp, cmd, _full in selected:
        if STOP:
            interrupted = STOP[0]
            break
        say('==== BEGIN %s group %s' % (name, grp))
        t0 = time.monotonic()
        rc, data = run_entry(cmd)
        dt = time.monotonic() - t0
        tests, skip = counts(data, cmd)
        say('==== END %s exit %d tests %s skipped %s %.2fs' % (name, rc, tests, skip, dt))
        done.append((name, rc))
        if STOP:
            interrupted = STOP[0]
            break
        if rc == 0:
            npass += 1
        else:
            nfail += 1
except BaseException:
    infra = traceback.format_exc().rstrip()
    say('==== 基础设施异常（原文如下；已创建的 WORK 不因异常放宽身份核验）：')
    say(infra)
finally:
    if not stop_own():
        say('==== cleanup 停止：无法确认本轮执行已停，保留 %s' % WORK)
    elif root_verified and RF1 is not None:
        cleaned = cleanup()
    elif work_attempted:
        for _fd in (RF2, RF1):
            if _fd is not None:
                try:
                    os.close(_fd)
                except OSError:
                    pass
        say('==== cleanup 停止：WORK 创建已尝试但身份未核（已知 %s 与父目录 %s），不猜名、不删，残留未验证'
            % (WORK or 'WORK 名未取得', TMP))
        cleaned = False
    else:
        cleaned = True

unfinished = [r[0] for r in selected if r[0] not in {d[0] for d in done}]
if infra:
    code = 2
elif not cleaned:
    code = 2
elif interrupted:
    code = 130 if interrupted == signal.SIGINT else 143
elif unfinished:
    code = 2
elif nfail:
    code = 1
else:
    code = 0
say('---- %s：PASS %d / FAIL %d%s ｜ %.1fs ----' % (
    MODE, npass, nfail, (' ｜ 未完成 %s' % ' '.join(unfinished)) if unfinished else '',
    time.monotonic() - t_all))
raise SystemExit(code)
PYEOF

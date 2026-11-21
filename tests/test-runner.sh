#!/bin/sh
# tests/run-tests.sh 的运行器、信号与选路回归：真实 runner + 合成用例表 + 合成 Git 仓跑 CI 选路段。
# 从 test-check-rules.sh 按对象拆出（结构守卫与登记一致性留在 gate）：既有断言与真实进程边界随用例迁移，
# 未删判据；拆出后又按定向复审补了两处：C01「入口已退但后代持 stdout」用例改为登记精确 PID/PGID、
# 按本轮 WORK 判定，并恢复「外部 TERM→143＋清根」原场景。只由 tests/run-tests.sh、tests/test_paths.py、
# .github/workflows/tests.yml 与本文件自身的变更命中（见 tests/test_paths.py 的 runner 规则）。
# 成本事实（2026-11-17 本机 iSH/aarch64）：拆出后本入口仍是重入口，实测耗时见 PR；超单入口 10 s 设计预算，
# 因为合成 Git 仓里的真实 runner 与 workflow 选路段必须在真实子进程上跑。
# 体积：本文件 > 20 KB（原文拆出的用例 + 夹具），理由同上：每个信号/收尾断言都要真实进程与精确 PID 观察，
# 压缩只能删夹具或删判据。
# 降级条件：未来提速须单独提交等价性证明（退出码与 stdout 断言不变；每个入口至少保留一个真实子进程用例）。
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
python3 -B - "$ROOT" <<'PYEOF'
import importlib.util, json, os, re, shutil, signal, subprocess, sys, tempfile, textwrap, time
from pathlib import Path
ROOT=Path(sys.argv[1])
PASS=FAIL=0
TMP=Path(tempfile.mkdtemp(prefix='test-runner.'))

def check(label,ok,detail=''):
    global PASS,FAIL
    if ok:PASS+=1;print('PASS  '+label)
    else:FAIL+=1;print('FAIL  '+label+(('：'+detail) if detail else ''))

# 真源：manifest 由本仓 run-tests.sh 现读，不抄清单。
RUNNER=(ROOT/'tests/run-tests.sh').read_text(encoding='utf-8')
start=RUNNER.index("CASES='\n");end=RUNNER.index("\n'\n",start)+3
REAL_CASES=[l.split('|') for l in RUNNER[start+7:end-2].splitlines() if l]
names={c[0] for c in REAL_CASES};groups={c[1] for c in REAL_CASES}
spec2=importlib.util.spec_from_file_location('paths',ROOT/'tests/test_paths.py')
P=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(P)

FIX=TMP/'runner'
for d in ('tests','home','tmp','poison'):(FIX/d).mkdir(parents=True)
shutil.copyfile(ROOT/'tests/test_paths.py',FIX/'tests/test_paths.py')
(FIX/'poison/fnmatch.py').write_text('raise SystemExit("poison:fnmatch")\n')
(FIX/'poison/json.py').write_text('raise SystemExit("poison:json")\n')
# 探针：HOME/TMPDIR 须为 runner 本轮独占目录，调用方变量不得进入（空值也算进入）
(FIX/'tests/probe.sh').write_text('''leak=""
case ${HOME:-} in */run-tests-*/home) ;; *) leak="$leak HOME" ;; esac
case ${TMPDIR:-} in */run-tests-*/tmp) ;; *) leak="$leak TMPDIR" ;; esac
for v in PYTHONPATH SYNTH_SECRET SYNTH_EMPTY; do eval "[ \\"\\${$v+set}\\" = set ]" && leak="$leak $v"; done
[ -z "$leak" ] && echo probe:ok || { echo "probe:leak$leak"; exit 1; }
''')
ROWS=('lint|smoke|echo lint:ran|1','eat|g1|cat >/dev/null; echo eat:ran|1','probe|g1|sh tests/probe.sh|1',
      'bad|g2|echo bad:ran; exit 1|0','long|g1|sh tests/long.sh|1','unit|g1|cd tests && python3 -B -m unittest -v unitdemo|1',
      'unitbad|g2|cd tests && python3 -B -m unittest -v unitbad|0','slow|g3|sh -c "sleep 30"|0',
      'spawn|g4|python3 -B tests/spawn.py & exit 0|0','hold|g5|python3 -B tests/hold.py & exit 0|0')
(FIX/'tests/long.sh').write_text(''.join('echo %s%s\n'%(m,c*200) for m,c in (('LONGHEAD','A'),('LONGMID','M'),('LONGTAIL','T'))))
(FIX/'tests/unitdemo.py').write_text('''import unittest
class T(unittest.TestCase):
    def test_ok(self): pass
    @unittest.skip('synthetic')
    def test_skip(self): pass
''')
(FIX/'tests/unitbad.py').write_text('''import unittest
class T(unittest.TestCase):
    def test_boom(self): self.fail('synthetic-boom')
''')
# R2 夹具：leader（shell）收 TERM 即退，同组后代忽略 TERM 继续写 heartbeat；
# python 是该后代的真实直接父进程，延迟后 kill+wait 回收自己 fork 的子进程（不留孤儿/zombie 冒充 live）。
(FIX/'tests/spawn.py').write_text('''import json, os, signal, time
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN); signal.signal(signal.SIGINT, signal.SIG_IGN)
    os.close(1); os.close(2)
    with open('child.json', 'w') as f: json.dump({'pid': os.getpid(), 'pgid': os.getpgrp()}, f)
    while True:
        with open('heartbeat', 'a') as f: f.write('x')
        time.sleep(0.05)
ended = [False]
signal.signal(signal.SIGTERM, lambda *a: ended.__setitem__(0, True))
end = time.monotonic() + 5
while not ended[0] and time.monotonic() < end: time.sleep(0.01)
time.sleep(1)
os.kill(pid, signal.SIGKILL)
os.waitpid(pid, 0)
os._exit(0)
''')
# C01 夹具：leader 立即退出，孙进程持有 stdout 直到被信号停止（旧实现只有 select 空转 → 挂死）。
(FIX/'tests/hold.py').write_text('''import json, os, signal, time
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    with open('held.json', 'w') as f: json.dump({'pid': os.getpid(), 'pgid': os.getpgrp()}, f)
    os.write(1, b'HELD-LIVE\\n')
    time.sleep(60)                      # 远长于用例的判别期限：旧实现只能空转挂死
    os._exit(0)
stop = [False]
def term(*_a):
    stop[0] = True
signal.signal(signal.SIGTERM, term)
while not stop[0]: time.sleep(0.02)
os.kill(pid, signal.SIGKILL)
os.waitpid(pid, 0)                     # 只回收本夹具自己的登记后代
os._exit(0)
''')
FIXED=RUNNER[:start]+"CASES='\n"+''.join(r+'\n' for r in ROWS)+"'\n"+RUNNER[end:]
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
HOSTILE=dict(os.environ,HOME=str(FIX/'home'),TMPDIR=str(FIX/'tmp'),PYTHONPATH=str(FIX/'poison'),
             SYNTH_SECRET='synthetic-secret',SYNTH_EMPTY='')
def rt(*a,stdin=None,timeout=120):
    r=subprocess.run(['sh','tests/run-tests.sh',*a],cwd=str(FIX),env=HOSTILE,input=stdin,
                     capture_output=True,text=True,errors='replace',timeout=timeout)
    return r.returncode,r.stdout+r.stderr
def ran(out):return sorted(set(re.findall(r'(\w+):ran',out))|({'probe'} if 'probe:ok' in out else set()))
for label,args,stdin,rc,want in (
        ('case',('case','probe'),None,0,['probe']),
        ('smoke',('smoke',),None,0,['lint']),
        ('full',('full',),None,0,['eat','lint','probe']),
        ('select 合并去重',('select',),'[["smoke"],["group","g1"],["case","probe"]]',0,['eat','lint','probe']),
        ('多组：子进程读 stdin 不吞后续入口，失败传播为非零',('group','g1,g2'),None,1,['bad','eat','probe'])):
    code,out=rt(*args,stdin=stdin)
    check('runner %s：rc=%d 且只跑 %s'%(label,rc,want),code==rc and ran(out)==want and out.count('probe:ok')<=1,
          'rc=%d ran=%s\n%s'%(code,ran(out),out[-400:]))
check('runner 失败入口保留完整原文与原始退出码','bad:ran' in out and 'END bad exit 1' in out,out[-200:])
for label,args,stdin in (('未知组',('group','nope'),None),
                         ('选不到入口的 selector',('select',),'[["full"],["group","nope"]]'),
                         ('非法 selector JSON',('select',),'{"full":1}'),('空 selector',('select',),'[]'),
                         ('未知模式',('nope',),None)):
    code,out=rt(*args,stdin=stdin)
    check('runner 拒绝%s（rc=2，未跑任何入口）'%label,code==2 and not ran(out),'rc=%d\n%s'%(code,out[-300:]))
code,out=rt('select-paths',stdin='tests/run-tests.sh\0tools/check-rules.py\0')
check('select-paths：full 与定向组并存，且不受 PYTHONPATH 影响',code==0 and out.strip()=='[["full"], ["case", "test-link-install.py"], ["group", "auth"], ["group", "identity"], ["group", "minis-verify"], ["group", "cchp"], ["case", "sync-all.sh"], ["case", "test-runner.sh"], ["group", "gate"]]',out)
def expand(doc):
    got=set()
    for s in doc:
        k=s[0];a=s[1] if len(s)>1 else None
        if k=='case':got.add(a)
        elif k=='full':got|={c[0] for c in REAL_CASES if c[3]=='1'}
        elif k=='smoke':got|={c[0] for c in REAL_CASES if c[1]=='smoke'}
        else:got|={c[0] for c in REAL_CASES if c[1]==a}
    return got
for pth in ('tests/run-tests.sh','tests/test_paths.py','.github/workflows/tests.yml'):
    check('select：%s 展开全 %d 入口各一次'%(pth,len(names)),expand(P.select([pth]))==names,str(P.select([pth])))
check('select：普通未映射正文只 smoke',P.select(['README.md'])==[['smoke']])
check('select：已映射 .md 照表不作后缀豁免',all(x in P.select([p]) for p,x in (('skills/luno-core/references/sync.md',['case','test-redact.py']),('skills/luno-platform/references/minis.md',['case','test-redact.py']),('skills/luno-surge/SKILL.md',['case','test-surge-package.py']))))
check('select：退役的 lh 专项删除 diff 仍可选路且都落到 full',all(P.select([p])==[['full']] for p in ('tests/test-lh-collect.py','tests/test-lh-deploy.py','tests/test-lh-verify.py')),str([P.select([p]) for p in ('tests/test-lh-collect.py','tests/test-lh-deploy.py','tests/test-lh-verify.py')]))
try:P.select(['tests/nope.py']);ok=False
except ValueError:ok=True
check('select：未知 tests 路径拒绝',ok)
code,out=rt('select-paths',stdin='tests/test-pack-skill-zip.py\0tests/test_paths.py\0')
check('select-paths：重命名的旧新两路径都参与选路',code==0 and out.count('["full"]')==1 and '["group", "auth"]' in out,out)
check('select-paths：无命中只给 smoke',P.select([])==[['smoke']])
code,out=rt('select-paths',stdin='tests/unregistered.py\0')
check('select-paths：未登记测试路径拒绝',code==2,out)
code,out=rt('select',stdin='[["full"],["case","long"],["case","unit"],["case","unitbad"]]')
check('runner 长输出保留首中尾原文且只打一次',all(('LONG%s'%m)+c*200 in out for m,c in (('HEAD','A'),('MID','M'),('TAIL','T'))) and out.count('LONGHEAD')==1,out[-200:])
check('runner 失败 traceback 原文保留',"self.fail('synthetic-boom')" in out and 'AssertionError' in out)
check('runner 用例数/skip/原退出码/耗时取自摘要',all(re.search(x,out) for x in (r'END unit exit 0 tests 2 skipped 1 \d+\.\d\ds',r'END unitbad exit 1 tests 1 skipped 0 ',r'END long exit 0 tests N/A skipped N/A ')),out[-300:])
check('runner 失败不被后继 PASS 抹掉',code==1 and 'FAIL 1' in out)
# 负控：环境白名单构造点改为继承调用方环境后，探针必须报泄漏（不是只数文本）
assert FIXED.count('child_env = build_child_env()')==1
(FIX/'tests/run-tests.sh').write_text(FIXED.replace('child_env = build_child_env()','child_env = dict(os.environ)'),encoding='utf-8')
code,out=rt('case','probe')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
check('负控：改用继承环境后探针报泄漏',code==1 and all(v in out for v in ('PYTHONPATH','SYNTH_SECRET','SYNTH_EMPTY')),out[-300:])

# ── CI workflow 运行段：抽取标界内的真实代码，在合成 Git 仓里跑，不复制选路算法 ──
WF=(ROOT/'.github/workflows/tests.yml').read_text(encoding='utf-8');MK='          # >>> CI_SELECT\n'
CI=textwrap.dedent(WF[WF.index(MK)+len(MK):WF.index('          # <<<\n')])
# 实际跑 workflow 的最外层 env-i 白名单（含 Git 禁配置/replace），不只跑内层 Python。
SEL_AT=WF.index('      - name: selected\n')
RH=textwrap.dedent(WF[WF.index('        run: |\n',SEL_AT)+len('        run: |\n'):WF.index(MK)])
PRE=RH.replace(" <<'PY'\n","\n").rstrip('\n')
assert PRE.startswith('env -i ') and PRE.endswith('python3 -I -B -'),PRE
G=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_AUTHOR_NAME='f',GIT_AUTHOR_EMAIL='f@e',GIT_COMMITTER_NAME='f',GIT_COMMITTER_EMAIL='f@e')
R2=TMP/'ci';R2.mkdir()
def g(*a):
    r=subprocess.run(('git',)+a,cwd=str(R2),env=G,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    return r.stdout.strip()
def cm(m):
    g('add','-A');g('commit','-q','-m',m);return g('rev-parse','HEAD')
def ci(ev,pre=None,**kw):
    env={'PATH':os.environ['PATH'],'HOME':str(TMP/'h'),'TMPDIR':str(TMP/'t'),'EVENT_NAME':ev}
    env.update({k:str(v) for k,v in kw.items()})
    (R2/'selected.json').unlink(missing_ok=True)
    return subprocess.run(['sh','-c',PRE if pre is None else pre],input=CI,cwd=str(R2),env=env,
                          capture_output=True,text=True,timeout=120)
def plan(r):return [l[9:] for l in r.stdout.splitlines() if l.startswith('selector ')][-1]
(R2/'tests').mkdir();shutil.copyfile(ROOT/'tests/test_paths.py',R2/'tests/test_paths.py')
(R2/'tests/run-tests.sh').write_text('cat > selected.json\n')
g('init','-q','-b','main');(R2/'README.md').write_text('b\n');C1=cm('c1')
(R2/'tools').mkdir(exist_ok=True);(R2/'tools/check-rules.py').write_text('g\n');C2=cm('c2')
g('checkout','-q','-b','feat',C1);(R2/'skills/luno-core/references').mkdir(parents=True)
(R2/'skills/luno-core/references/review.md').write_text('f\n');C3=cm('c3')
g('checkout','-q','main');g('merge','-q','--no-ff','-m','m','feat');MM=g('rev-parse','HEAD')
r=ci('pull_request',BASE_SHA=C2,HEAD_SHA=C3,MERGE_SHA=MM)
check('CI：PR 测 B→M，base 前进不算 PR 变化',r.returncode==0 and plan(r)=='[["smoke"], ["group", "identity"]]' and 'identity' in (R2/'selected.json').read_text(),r.stdout[-300:]+r.stderr[-300:])
g('checkout','-q','-b','feat2',C1);(R2/'tools').mkdir(exist_ok=True);(R2/'tools/minis-verify.py').write_text('v\n');cm('d1')
(R2/'skills/luno-platform/references').mkdir(parents=True,exist_ok=True);(R2/'skills/luno-platform/references/minis.md').write_text('m\n');D2=cm('d2')
r=ci('push',BEFORE_SHA=C1,AFTER_SHA=D2)
check('CI：push 取 before→after，多提交都在',r.returncode==0 and all(x in plan(r) for x in ('test-minis-verify.py','test-redact.py')),r.stdout[-300:])
# R3 直接回归：本地 replace ref 不得改变选路（最外层 Git 禁配置生效）；去掉保护须真实反例
g('replace',C1,D2)
r=ci('push',BEFORE_SHA=C1,AFTER_SHA=D2)
check('CI：本地 replace ref 下仍按原始两棵树选路（禁 replace 生效）',
      r.returncode==0 and all(x in plan(r) for x in ('test-minis-verify.py','test-redact.py')),r.stdout[-300:]+r.stderr[-300:])
RED_PRE=PRE.replace('GIT_NO_REPLACE_OBJECTS=1 ','')
assert RED_PRE!=PRE and 'GIT_NO_REPLACE_OBJECTS' not in RED_PRE
r=ci('push',pre=RED_PRE,BEFORE_SHA=C1,AFTER_SHA=D2)
check('负控：去掉 GIT_NO_REPLACE_OBJECTS 后同一 replace ref 令 gate 退化为 smoke',
      r.returncode==0 and 'test-minis-verify.py' not in plan(r) and plan(r)=='[["smoke"]]',plan(r)+r.stderr[-200:])
g('replace','-d',C1)
for kw,label in ((dict(BASE_SHA=C2,HEAD_SHA=C3,MERGE_SHA='a'*40),'缺对象'),(dict(BEFORE_SHA='0'*40,AFTER_SHA=D2),'全零')):
    r=ci('push' if 'BEFORE_SHA' in kw else 'pull_request',**kw)
    check('CI：%s阻断且不得到成功 smoke'%label,r.returncode==2 and 'smoke' not in r.stdout and not (R2/'selected.json').exists(),r.stderr[-200:])

# ── 收尾：正常/失败/TERM 都只观察夹具自建的精确路径，不扫 /tmp ──
left=lambda:sorted(p.name for p in (FIX/'tmp').iterdir())
check('清理：正常与失败轮均删本轮 WORK 根',not left(),str(left()))
p=subprocess.Popen(['sh','tests/run-tests.sh','case','slow'],cwd=str(FIX),env=HOSTILE,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
time.sleep(3);p.terminate();o=p.communicate(timeout=120)[0].decode('utf-8','replace')
check('清理：TERM 停本轮进程组、删根并以 143 退出',p.returncode==143 and not left() and 'cleanup 完成' in o,'rc=%d %s'%(p.returncode,left()))
def work_of(out):
    """从本轮输出取本轮独占 WORK 的确切路径（不靠列举共享目录证明本轮保留）。"""
    m=re.search(r'==== WORK (\S+?)（',out)
    return m.group(1) if m else None
GATE=[]                                 # 每例各自的登记 (case,pid,pgid,work)：轮末逐例复核，不复用最后一个 info
def grp_gone(pgid):
    """只用 signal 0 观察登记组：ProcessLookupError 才算已无成员，其他 OSError 一律“未确证”。"""
    try:os.killpg(pgid,0);return False
    except ProcessLookupError:return True
    except OSError:return False
def stopped(pid,pgid,limit=8.0):
    """限时确证停止：精确 PID 已不在且登记组已无成员。只观察登记值，不扫进程表、不做僵尸推定。"""
    end=time.monotonic()+limit
    while True:
        if not alive(pid) and grp_gone(pgid):return True
        if time.monotonic()>=end:return False
        time.sleep(0.05)
def drop(case,m,info):
    """先按本夹具自己的登记确证停止，再删本轮输出绑定的 WORK；任一项未证就保留、报告残留并判失败。"""
    if info is None or m is None:
        check('清理（%s）：无登记信息或无 WORK 路径，保留不删'%case,False,'info=%s work=%s'%(info,m));return
    pid,pgid=info['pid'],info['pgid']
    GATE.append((case,pid,pgid,m))
    if not stopped(pid,pgid):
        check('清理（%s）：停止未确证，保留 WORK 与 TMP 不删'%case,False,
              '残留 %s（PID %d / PGID %d 未确证消失）'%(m,pid,pgid));return
    p=Path(m)
    if p.is_symlink() or p.parent!=FIX/'tmp' or not p.name.startswith('run-tests-'):
        check('清理（%s）：WORK 不是本夹具 tmp 的直接子目录或是软链，保留不删'%case,False,
              'work=%s parent=%s symlink=%s'%(m,p.parent,p.is_symlink()));return
    if not p.exists():
        check('清理（%s）：runner 已确证收尾，本夹具无 WORK 需删'%case,True);return
    try:shutil.rmtree(p)
    except OSError as exc:
        check('清理（%s）：删除失败'%case,False,'%s: %s'%(m,exc));return
    if p.exists() or p.is_symlink():
        check('清理（%s）：删除后仍存在'%case,False,m);return
    check('清理（%s）：确证停止后删除本轮 WORK'%case,True)
# R2 原场景（恢复）：leader 已退、同组后代仍在（spawn 后代忽略 TERM），外部 TERM 停本轮进程组。
# 契约为两条路线：确证停 → 143 + cleanup 完成 + 删本轮根 + 后代已停；无法确证 → 2 + 保留本轮根 + 披露。
for f in ('child.json','heartbeat'):
    if (FIX/f).exists():(FIX/f).unlink()
p=subprocess.Popen(['sh','tests/run-tests.sh','case','spawn'],cwd=str(FIX),env=HOSTILE,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
info=None
for _ in range(300):
    if (FIX/'child.json').exists():
        try:info=json.loads((FIX/'child.json').read_text());break
        except ValueError:pass
    time.sleep(0.02)
assert info,'夹具子进程未就绪'
def alive(pid):
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
assert alive(info['pid']),'夹具后代未就绪'
a=(FIX/'heartbeat').stat().st_size
assert a>0,'夹具后代未写 heartbeat'
p.terminate()
o=p.communicate(timeout=180)[0].decode('utf-8','replace');time.sleep(0.2)
grew=(FIX/'heartbeat').stat().st_size>a
live=alive(info['pid'])
w=work_of(o)
stop_ok=(p.returncode==143 and 'cleanup 完成' in o and w is not None and not os.path.exists(w) and not live)
fail_closed=(p.returncode==2 and '本轮进程组' in o and w is not None and os.path.exists(w))
drop('R2 原场景',w,info)
check('清理（R2 原场景）：外部 TERM 停本轮进程组（leader 已退、后代持流）→143+清本轮根；无法确证→2+保留/披露',
      stop_ok or fail_closed,
      'rc=%d live=%s grew=%s work=%s\n%s'%(p.returncode,live,grew,w,o[-500:]))
# R2 自然退出场景：同样输入但不注入外部信号；修复后由 run_entry 自身确证停止并正常收尾。
# 本机（iSH）孤儿僵尸无法被回收时按契约 2 + 保留 + 披露。iSH 聚合 rc2 的归因未证实，不放宽断言。
for f in ('child.json','heartbeat'):
    if (FIX/f).exists():(FIX/f).unlink()
p=subprocess.Popen(['sh','tests/run-tests.sh','case','spawn'],cwd=str(FIX),env=HOSTILE,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
info=None
for _ in range(300):
    if (FIX/'child.json').exists():
        try:info=json.loads((FIX/'child.json').read_text());break
        except ValueError:pass
    time.sleep(0.02)
assert info,'夹具子进程未就绪'
o=p.communicate(timeout=180)[0].decode('utf-8','replace');time.sleep(0.2)
live=alive(info['pid']);w=work_of(o)
self_ok=(p.returncode==0 and 'cleanup 完成' in o and w is not None and not os.path.exists(w) and not live)
early_closed=(p.returncode==2 and '本轮进程组' in o and w is not None and os.path.exists(w))
drop('R2 自然退出',w,info)
check('清理（自然退出）：leader 先退但同组后代仍在时按契约收尾（自身确证停→rc=0+清本轮根；否则2+保留/披露）',
      self_ok or early_closed,
      'rc=%d live=%s work=%s\n%s'%(p.returncode,live,w,o[-500:]))
# C01 定向回归：入口已退出、同组后代（寿命 60s）仍持 stdout。旧实现在 select 空转永久挂死；
# 修复后每轮读取后先按登记组 confirm_stopped，再限时 drain 到 EOF。判别期 40s < 后代寿命 60s。
for f in ('held.json',):
    if (FIX/f).exists():(FIX/f).unlink()
held_timeout=False
try:
    code,out=rt('case','hold',timeout=40)
except subprocess.TimeoutExpired as exc:
    raw=exc.stdout or b''
    out=raw.decode('utf-8','replace') if isinstance(raw,bytes) else (raw or '')
    code,held_timeout=None,True
held_info=None
if (FIX/'held.json').exists():
    try:held_info=json.loads((FIX/'held.json').read_text())
    except ValueError:held_info=None
if held_timeout:
    # 超时：先向登记组发 TERM，让负责 wait 的夹具父进程执行它既有的 kill+wait 回收自己的后代；
    # 再限时核验登记的 PID/PGID。不先 KILL 负责 wait 的父进程，也不推定回收已完成；核不出就按 R2-01 保留并失败。
    if held_info is not None:
        try:os.killpg(held_info['pgid'],signal.SIGTERM)
        except OSError:pass
    held_stopped=held_info is not None and stopped(held_info['pid'],held_info['pgid'])
else:
    held_stopped=True
work=work_of(out)
held_ok=(code==0 and 'HELD-LIVE' in out and 'cleanup 完成' in out and work is not None and not os.path.exists(work))
held_closed=(code==2 and 'HELD-LIVE' in out and '本轮进程组' in out and work is not None and os.path.exists(work))
drop('C01 持流后代',work,held_info)
check('runner：入口已退但后代持 stdout（后代 60s、判期 40s）不空转挂死（确证停→rc=0 删本轮根；无法确证→rc=2 保留并披露）',
      held_ok or held_closed,
      'timeout=%s grounded=%s rc=%r work=%s held=%s\n%s'%(held_timeout,held_stopped if held_timeout else None,code,work,held_info,out[-400:]))
check('C01 夹具登记：精确 PID/PGID 已记录，且该后代已不在',
      held_info is not None and not alive(held_info['pid']),'held=%s'%(held_info,))
# 精确 PID 消失由夹具的直接父进程 kill+wait 兑现：只等这一条精确 PID，不扫进程表
for _ in range(200):
    if not alive(info['pid']):break
    time.sleep(0.05)
check('夹具回收：同组后代按精确 PID 确证消失（直接父进程 wait）',not alive(info['pid']),'pid=%d'%info['pid'])
# >>> R2T-GATE 删任何根之前逐例核验每一例自己的精确 PID/组已停；未核一律非零并保留本轮 TMP
# 不再把「精确 PID 已回收＋组仍有成员」推定为僵尸放行：组是否已无成员核不出来就是「未知」，一律保留。
if len(GATE) != 3:  # 三例均须登记；缺 WORK/info 的 drop 不会追加 GATE
    raise SystemExit('夹具停止未确证（登记不完整 %d/3），保留本轮TMP：%s' % (len(GATE),TMP))
_GATE_BAD=[]
for _case,_pid,_pgid,_work in GATE:
    if alive(_pid):
        _GATE_BAD.append('%s：PID %d 仍在' % (_case,_pid))
    elif not grp_gone(_pgid):
        _GATE_BAD.append('%s：组 %d 仍有成员（停止未知，不做僵尸推定）' % (_case,_pgid))
    elif os.path.lexists(_work):
        _GATE_BAD.append('%s：WORK 仍残留 %s' % (_case,_work))
if _GATE_BAD:
    raise SystemExit('夹具停止未确证（%s），保留本轮TMP：%s' % ('；'.join(_GATE_BAD),TMP))
# <<< R2T-GATE
# 生命周期：已确证消失的本轮组不得保留到轮末（否则轮末会拿历史 PID 盲发信号）
ACTIVE_MUT=FIXED.replace('finally:\n    if not stop_own():',"finally:\n    say('ACTIVE-RESID=%d' % len(ACTIVE))\n    if not stop_own():",1)
assert ACTIVE_MUT!=FIXED
(FIX/'tests/run-tests.sh').write_text(ACTIVE_MUT,encoding='utf-8');code,out=rt('case','lint')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
check('生命周期：已确证消失的本轮组不保留到轮末（ACTIVE 退役）',code==0 and 'ACTIVE-RESID=0' in out,out[-300:])
# fail-closed 直接检查：无法确证停止时（普通退出也一样）必须 2 + 保留根 + 披露，不冒称完成
NOCONF=FIXED.replace('def confirm_stopped(pgid, sig):\n    """按登记组兑现停止','def confirm_stopped(pgid, sig):\n    return False\n    """按登记组兑现停止',1)
NOCONF=NOCONF.replace('def group_gone(pgid):\n    """只用 signal 0','def group_gone(pgid):\n    return False\n    """只用 signal 0',1)
assert NOCONF.count('def confirm_stopped(pgid, sig):\n    return False')==1
(FIX/'tests/run-tests.sh').write_text(NOCONF,encoding='utf-8');code,out=rt('case','lint')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
check('清理：无法确证停止时 rc=2、保留根并披露，不冒称完成',
      code==2 and left() and '本轮进程组' in out and 'cleanup 完成' not in out,
      'rc=%d left=%s\n%s'%(code,left(),out[-400:]))
for d in list((FIX/'tmp').iterdir()):
    shutil.rmtree(d) if not d.is_symlink() else d.unlink()
S=TMP/'sentinel';S.mkdir();(S/'keep').write_text('x')
MOD=FIXED.replace('        shutil.rmtree(NAME, dir_fd=PFD)','        os.rename(NAME, NAME+"-moved", src_dir_fd=PFD, dst_dir_fd=PFD)\n        os.symlink(%r, NAME, dir_fd=PFD)\n        shutil.rmtree(NAME, dir_fd=PFD)'%str(S))
assert MOD!=FIXED
(FIX/'tests/run-tests.sh').write_text(MOD,encoding='utf-8');code,out=rt('case','lint')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
check('清理：根被换成外部链接时非零、披露残留、不误删哨兵',code==2 and 'cleanup 失败' in out and (S/'keep').read_text()=='x',out[-300:])
# 清理：只比两个旧持有 fd 不够——按当前 NAME 从锚定父 fd 真重开核等。改名原根 + 普通目录替身（含哨兵）必须不被触碰。
SWAP=('        os.rename(NAME, NAME + \'-orig\', src_dir_fd=PFD, dst_dir_fd=PFD)\n'
      '        os.mkdir(NAME, 0o700, dir_fd=PFD)\n'
      '        _sx = os.open(NAME + \'/standin\', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=PFD)\n'
      '        os.close(_sx)\n'
      '        recheck(TMP, ANC)\n'
      '        cur = reopen_current()\n')
SWAP_AT='        recheck(TMP, ANC)\n        cur = reopen_current()'
assert FIXED.count(SWAP_AT)==1
def roots():
    ns=sorted(p.name for p in (FIX/'tmp').iterdir())
    return ns,[n for n in ns if not n.endswith('-orig')],[n for n in ns if n.endswith('-orig')]
def wipe_tmp():
    for d in list((FIX/'tmp').iterdir()):
        shutil.rmtree(d) if not d.is_symlink() else d.unlink()
wipe_tmp()
(FIX/'tests/run-tests.sh').write_text(FIXED.replace(SWAP_AT,SWAP),encoding='utf-8')
code,out=rt('case','lint')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
ns,now,orig=roots()
check('清理：原根改名+普通目录替身时 rc=2、披露原根/现路径、替身与哨兵未被触碰',
      code==2 and '替身未触碰' in out and '原根 dev/ino' in out and len(now)==1 and len(orig)==1
      and (FIX/'tmp'/now[0]/'standin').is_file(),'rc=%d %s'%(code,ns))
wipe_tmp()
# 有效负控：两处核等都禁用后同一注入才可达替身（证明上面的断言非空转）
MUT=FIXED.replace('if b != a:','if False:').replace('if b2 != a2:','if False:')
assert MUT.count('if False:')==2 and MUT!=FIXED
(FIX/'tests/run-tests.sh').write_text(MUT.replace(SWAP_AT,SWAP),encoding='utf-8')
code,out=rt('case','lint')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
ns,now,orig=roots()
check('负控：两处核等禁用后替身被删（正控断言可达、不空转）',
      code==0 and not now and len(orig)==1 and not (FIX/'tmp'/orig[0]/'standin').exists(),'rc=%d %s'%(code,ns))
wipe_tmp()
# 创建后直接可达的基础设施异常：rc=2、异常原文保留、WORK 按规则真实收尾
assert FIXED.count('        t0 = time.monotonic()')==1
(FIX/'tests/run-tests.sh').write_text(
    FIXED.replace('        t0 = time.monotonic()','        raise RuntimeError("synthetic-infra")',1),encoding='utf-8')
code,out=rt('case','lint')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
check('runner 创建后基础设施异常：rc=2、保留原文、WORK 安全收尾无残留',
      code==2 and '基础设施异常' in out and 'RuntimeError: synthetic-infra' in out and 'cleanup 完成' in out and not left(),
      'rc=%d %s\n%s'%(code,left(),out[-400:]))
# R1：创建块（含首个 home mkdir）也在 finally 覆盖内。位置与上面的循环 t0 用例不同，不是改名。
assert FIXED.count('        os.mkdir(_d, 0o700, dir_fd=RF1)')==1
(FIX/'tests/run-tests.sh').write_text(FIXED.replace(
    '        os.mkdir(_d, 0o700, dir_fd=RF1)','        raise OSError(28, "synthetic-ENOSPC-init")',1),encoding='utf-8')
code,out=rt('case','lint')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
check('runner 创建期首个 home mkdir 抛 OSError：rc=2、原文保留、按已核身份删精确根',
      code==2 and 'OSError: [Errno 28] synthetic-ENOSPC-init' in out and 'cleanup 完成' in out and not left(),
      'rc=%d left=%s\n%s'%(code,left(),out[-400:]))
# trackedState：先判退出码。git status 非 0 且 stdout 为空时必须 unknown，不能打印 clean
assert FIXED.count("    _st = git('status', '--porcelain', '--untracked-files=normal')")==1
(FIX/'tests/run-tests.sh').write_text(FIXED.replace(
    "    _st = git('status', '--porcelain', '--untracked-files=normal')",
    "    class _F:\n        returncode = 128\n        stdout = b''\n    _st = _F()",1),encoding='utf-8')
code,out=rt('case','lint')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
check('runner trackedState：git status 失败且空 stdout 记 unknown 而非 clean',
      code==0 and '==== trackedState unknown' in out and '==== trackedState clean' not in out and not left(),
      'rc=%d\n%s'%(code,out[-300:]))
for d in list((FIX/'tmp').iterdir()):
    shutil.rmtree(d) if not d.is_symlink() else d.unlink()
shutil.rmtree(TMP,ignore_errors=True)
print('---- runner／选路回归：PASS %d / FAIL %d ----'%(PASS,FAIL))
raise SystemExit(1 if FAIL else 0)
PYEOF

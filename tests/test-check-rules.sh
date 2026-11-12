#!/bin/sh
# 结构守卫 tools/check-rules.py 的反例回归（固定 rc 0/1/2/3 与错误类别），
# 以及 tests/run-tests.sh 的选路、失败传播、环境隔离与登记一致性回归（真实 runner + 合成用例表）。
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
python3 -B - "$ROOT" <<'PYEOF'
import contextlib, importlib.util, io, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from unittest import mock
ROOT=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('guard',ROOT/'tools/check-rules.py')
G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)
PASS=FAIL=0
TMP=Path(tempfile.mkdtemp(prefix='test-check-rules.'))
ENTRY='skills/luno-core/SKILL.md'
SYNC='skills/luno-core/references/sync.md'
CLAIMS='tools/rule-claims.tsv'

def check(label,ok,detail=''):
    global PASS,FAIL
    if ok:PASS+=1;print('PASS  '+label)
    else:FAIL+=1;print('FAIL  '+label+(('：'+detail) if detail else ''))

# 守卫输入只复制一次（skills/prompt/subagents 与两张登记表）；每例记录夹具改动过的路径，
# 跑完按仓库原件逐个还原或删除，下一例仍从原样副本开始（收尾逐字节核对副本）。
CASE=TMP/'case'
for top in ('skills','prompt','subagents'):shutil.copytree(ROOT/top,CASE/top,symlinks=True)
(CASE/'tools').mkdir()
for f in ('rule-claims.tsv','sync-targets.json'):shutil.copyfile(ROOT/'tools'/f,CASE/'tools'/f)
MUTATORS=('write_text','write_bytes','unlink','symlink_to','mkdir')

def case(label,want,category,setup=lambda p:None,n=1):
    touched={}
    def tracked(real):
        def method(path,*a,**k):
            touched.setdefault(path,os.path.lexists(path));return real(path,*a,**k)
        return method
    with contextlib.ExitStack() as stack:
        for name in MUTATORS:stack.enter_context(mock.patch.object(Path,name,tracked(getattr(Path,name))))
        setup(CASE)
    out=io.StringIO();guard=G.Guard(CASE)
    with contextlib.redirect_stdout(out):rc=guard.run()
    for path,existed in sorted(touched.items(),key=lambda x:-len(x[0].parts)):
        if path.is_dir() and not path.is_symlink():
            if not existed:shutil.rmtree(path)
            continue
        if os.path.lexists(path):path.unlink()
        if existed:shutil.copyfile(ROOT/path.relative_to(CASE),path)
    found=guard.hard+guard.incomplete+guard.soft if rc else ['无问题']
    check(label,rc==want and found.count(category)>=n,'rc=%d 期望 %d/%s×%d\n%s'%(rc,want,category,n,out.getvalue()))

def edit(p,rel,fn):
    f=p/rel;before=f.read_text(encoding='utf-8');after=fn(before)
    assert before!=after,'夹具变异空转：'+rel
    f.write_text(after,encoding='utf-8')
def append(p,rel,text):edit(p,rel,lambda s:s+text)
def claim(p,*fields):append(p,CLAIMS,'\t'.join(fields)+'\n')
def claim_rows(p):
    return [l for l in (p/CLAIMS).read_text(encoding='utf-8').splitlines() if l and not l.startswith('#')]
def registry(p,fn):
    f=p/'tools/sync-targets.json';d=json.loads(f.read_text(encoding='utf-8'));fn(d)
    f.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
def skill_obj(p,fn):registry(p,lambda d:fn(next(o for o in d['objects'] if o['type']=='skill')))
def scope_files(p):
    return [f for top in ('skills','prompt','subagents') for f in (p/top).rglob('*')
            if f.is_file() and f.suffix in ('.md','.py','.sh')]

# Fixture contracts: entry must retain actual frontmatter; sync is a resource.
assert (ROOT/ENTRY).read_text(encoding='utf-8').startswith('---\nname: luno-core\n')
assert not (ROOT/SYNC).read_text(encoding='utf-8').startswith('---\n')
assert (ROOT/'skills/luno-authoring/SKILL.md').is_file()
assert not any(m[2]=='luno-authoring' for m in G.LOAD_RE.finditer((ROOT/SYNC).read_text(encoding='utf-8')))

# ── 正控 ──
case('完整正控',0,'无问题')
case('frontmatter 内的加载语句不算加载边',0,'无问题',
     lambda p:edit(p,ENTRY,lambda s:s.replace('name: luno-core','name: luno-core\nmetadata: "必须加载 `luno-example-only`"',1)))

# ── 登记表 ──
case('缺登记表',3,'读取失败',lambda p:(p/CLAIMS).unlink())
case('空登记表',3,'条款登记为空',lambda p:(p/CLAIMS).write_text('# empty\n'))
case('登记字段数错误',3,'条款登记字段',lambda p:claim(p,SYNC,'luno-authoring','条件加载'))
case('未知形态',3,'加载形态',lambda p:claim(p,SYNC,'luno-authoring','未知','x'))
case('重复登记',1,'重复登记',lambda p:append(p,CLAIMS,claim_rows(p)[0]+'\n'))
case('登记来源不存在',3,'加载边来源缺失',lambda p:claim(p,'skills/luno-core/absent.md','references/a.md','资源条件','x'))

# ── 加载边 ──
LOAD='\n- 写入前先加载 `luno-memory`。\n'
case('加载语句未登记',3,'加载登记',lambda p:append(p,SYNC,LOAD))
case('登记该文件后通过',0,'无问题',lambda p:(append(p,SYNC,LOAD),claim(p,SYNC,'luno-memory','必需加载','x')))
case('加载形态错配',1,'加载形态',lambda p:(append(p,SYNC,LOAD),claim(p,SYNC,'luno-memory','条件加载','x')))
case('登记的加载边正文未出现',3,'加载边未出现',lambda p:claim(p,SYNC,'luno-authoring','条件加载','x'))
def no_loads(p):
    for f in scope_files(p):
        t=f.read_text(encoding='utf-8');u=G.LOAD_RE.sub('加载说明',t)
        if u!=t:f.write_text(u,encoding='utf-8')
case('加载语句核对为空',3,'0 条加载语句被核对',no_loads)

# ── 资源边 ──
def new_resource(p,register):
    (p/'skills/luno-core/references/new-structural.md').write_text('x\n')
    append(p,SYNC,'\n`references/new-structural.md`\n')
    if register:claim(p,SYNC,'references/new-structural.md','资源条件','x')
case('现存资源未登记',3,'资源加载边',lambda p:new_resource(p,False))
case('正文引用的资源不存在',1,'资源引用断链',lambda p:append(p,SYNC,'\n`references/absent.md`\n'))
case('登记的资源不存在',1,'资源引用断链',lambda p:claim(p,SYNC,'references/absent.md','资源条件','x'))
case('资源目标非路径',1,'资源加载边形态',lambda p:claim(p,SYNC,'这不是路径','资源条件','x'))
case('资源来源非技能包',1,'资源加载边来源',lambda p:claim(p,'prompt/LUNO.md','references/x.md','资源条件','x'))
def drift(p):
    (p/'skills/luno-core/references/foo.md').write_text('x\n')
    claim(p,SYNC,'references/foo.md','资源条件','x')
case('登记资源正文未引用＝仅提示（rc=2）',2,'条款真源漂移',drift)
def no_resources(p):
    for f in scope_files(p):
        t=f.read_text(encoding='utf-8');u=G.RESOURCE_RE.sub('',t)
        if u!=t:f.write_text(u,encoding='utf-8')
    (p/CLAIMS).write_text(''.join(l+'\n' for l in claim_rows(p) if not l.split('\t')[2].startswith('资源')))
case('资源路径核对为空',3,'0 条资源路径被核对',no_resources)
case('资源引用逃逸',1,'资源引用逃逸',lambda p:append(p,SYNC,'\n`references/../../outside.md`\n'))
def symlinked(p):
    (p/'skills/luno-core/references/linked.md').symlink_to(p/'tools/sync-targets.json')
    append(p,SYNC,'\n`references/linked.md`\n')
case('资源经 symlink',1,'资源引用逃逸',symlinked)

# Cross-package resources are now part of the same structural contract.
# These cases stay in the existing gate/full entry: cross edges are used by roles and prompt.
CROSS='luno-core/references/cross-structural.md'
def cross_resource(p,register=True,source='prompt/LUNO.md'):
    (p/('skills/'+CROSS)).write_text('fixture\n',encoding='utf-8')
    append(p,source,'\n先完整加载 `'+CROSS+'`。\n')
    if register:claim(p,source,CROSS,'资源条件','cross fixture')
case('跨包资源完整登记且不误判技能加载',0,'无问题',cross_resource)
case('跨包资源未登记',3,'资源加载边',lambda p:cross_resource(p,False))
case('跨包资源登记漂移仅提示',2,'条款真源漂移',
     lambda p:((p/('skills/'+CROSS)).write_text('fixture\n'),claim(p,'prompt/LUNO.md',CROSS,'资源条件','x')))
case('跨包资源断链',1,'资源引用断链',
     lambda p:append(p,'prompt/LUNO.md','\n`luno-core/references/no-cross-file.md`\n'))
case('跨包资源逃逸',1,'资源引用逃逸',
     lambda p:append(p,'prompt/LUNO.md','\n`luno-core/references/../../outside.md`\n'))
def cross_symlink(p):
    (p/('skills/'+CROSS)).symlink_to(p/'tools/sync-targets.json')
    append(p,'subagents/LENS.md','\n`'+CROSS+'`\n')
case('跨包资源经symlink',1,'资源引用逃逸',cross_symlink)

# ── 合并资源的分支指针 ──
case('分支指针指向不存在的分支',1,'分支指针失效',
     lambda p:edit(p,ENTRY,lambda s:s.replace('〔分支 execution〕','〔分支 absent〕',1)))
case('被指向的分支缺 END 定界',1,'分支指针失效',
     lambda p:edit(p,'skills/luno-core/references/execution.md',lambda s:s.replace('<!-- END safety -->','',1)))

# ── 身份登记 ──
case('身份登记不可读',3,'身份登记不可用',lambda p:(p/'tools/sync-targets.json').write_text('{bad'))
case('身份登记为空',3,'身份登记不可用',lambda p:(p/'tools/sync-targets.json').write_text('{"objects":[]}'))
case('身份与技能源不一致',1,'身份与技能源不一致',lambda p:skill_obj(p,lambda o:o.__setitem__('id','wrong-name')))
def shared_id(p):
    def fn(d):
        sk=[o for o in d['objects'] if o['type']=='skill'];sk[1]['ends']['lobehub']['id']=sk[0]['ends']['lobehub']['id']
    registry(p,fn)
case('同一平台 ID 多占',1,'平台身份多占',shared_id)
case('缺位仍带 ID',1,'缺位身份冲突',lambda p:skill_obj(p,lambda o:o['ends']['lobehub'].__setitem__('present',False)))
case('平台 ID 非法形态',1,'平台身份形态',lambda p:skill_obj(p,lambda o:o['ends']['lobehub'].__setitem__('id','bad')))
case('身份端缺 present',1,'身份端结构',lambda p:skill_obj(p,lambda o:o['ends']['minis'].pop('present')))
def minis_paths(p):
    def fn(d):
        sk=[o for o in d['objects'] if o['type']=='skill']
        sk[0]['ends']['minis']['path']='/var/minis/skills/wrong/SKILL.md';sk[1]['ends']['minis']['path']=[]
    registry(p,fn)
case('Minis 路径误配（错路径与非字符串各一）',1,'Minis 身份路径冲突',minis_paths,n=2)

# ── 义务块 ──
OB_SRC,OB_HEAD=G.OBLIGATIONS[0]
def ob_empty(s):
    lines=s.splitlines();i=lines.index(OB_HEAD)+1;j=i
    while j<len(lines) and not lines[j].startswith('#'):j+=1
    return '\n'.join(lines[:i]+lines[j:])+'\n'
case('义务块重复',1,'义务块缺失或重复',lambda p:append(p,OB_SRC,'\n'+OB_HEAD+'\nx\n'))
case('义务块为空',1,'义务块为空',lambda p:edit(p,OB_SRC,ob_empty))

# 新入口承载的产品边界同样必须有真实负控；从守卫声明现读，不钉正文措辞。
# 义务块缺失：逐个去掉平台入口的每个义务标题，每个都须单独报出。
ROOT_OBS=[(src,head) for src,head in G.OBLIGATIONS if src=='skills/luno-platform/SKILL.md']
assert ROOT_OBS, '平台入口义务负控不能空转'
def drop_root_obs(p):
    for src,head in ROOT_OBS:edit(p,src,lambda s,head=head:s.replace(head,head+'-removed',1))
case('义务块缺失（平台入口 %d 个义务逐个）'%len(ROOT_OBS),1,'义务块缺失或重复',drop_root_obs,n=len(ROOT_OBS))

# ── 自编资源：缺件不再豁免，旧取件登记一律拒绝 ──
def legacy_fetch(p):
    def mutate(doc):
        obj=next(o for o in doc['objects'] if o['id']=='luno-surge')
        obj['officialPackageResources']={'paths':[]}
    registry(p,mutate)
case('旧取件登记即使为空也拒绝',1,'官方取件登记已退休',legacy_fetch)
case('自编插件指南缺失不获豁免',1,'资源引用断链',
     lambda p:(p/'skills/luno-surge/references/plugin-authoring.md').unlink())
# Independent requirement oracle: never derive forbidden fixtures from the guard.
RETIRED=('skills/luno-surge/references/upstream-SKILL.md',
         'skills/luno-surge/references/upstream-command-reference.md',
         'skills/luno-surge/assets/logo.png')
def inject(p):
    for rel in RETIRED:
        target=p/rel;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(b'synthetic retired official resource')
case('退役官方资源进入运行树（%d 个逐个报出）'%len(RETIRED),1,'禁止分发完整官方资源',inject,n=len(RETIRED))

# ── frontmatter 剥离 ──
for text,want in (('---\n---\n正文\n---\n尾部','正文\n---\n尾部'),
                  ('---\nname: x\n---\n正文\n---\n尾部','正文\n---\n尾部'),
                  ('---\nname: x\n未结束','---\nname: x\n未结束')):
    check('strip_frontmatter %r'%text,G.strip_frontmatter(text)==want)

# ── run-tests.sh：真实 runner、合成用例表 ──
RUNNER=(ROOT/'tests/run-tests.sh').read_text(encoding='utf-8')
start=RUNNER.index("CASES='\n");end=RUNNER.index("\n'\n",start)+3
REAL_CASES=[l.split('|') for l in RUNNER[start+7:end-2].splitlines() if l]

# 登记一致性：tests/ 下每个测试入口都在用例表里，且每条选路规则都能选到入口
names={c[0] for c in REAL_CASES};groups={c[1] for c in REAL_CASES}
entries={f.name for f in (ROOT/'tests').iterdir() if re.match(r'test-.*\.(py|sh)$',f.name)}
check('tests/ 下测试入口全部登记',entries<=names,str(sorted(entries-names)))
check('用例表入口文件均存在',all((ROOT/'tests'/n).is_file() or n=='check-rules.py' for n in names))
spec2=importlib.util.spec_from_file_location('paths',ROOT/'tests/test_paths.py')
P=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(P)
bad=[s for _,s,_ in P.PATHS_RULES if not (s==('full',) or (s[0]=='group' and s[1] in groups) or (s[0]=='case' and s[1] in names))]
check('选路规则都指向已登记入口',not bad,str(bad))
r=subprocess.run(['sh',str(ROOT/'tests/run-tests.sh'),'render-paths'],capture_output=True,text=True)
block=RUNNER[RUNNER.index('# >>> PATHS_RULES\n')+18:RUNNER.index('# <<<\n')]
check('runner 头部选路块与 render-paths 一致',r.returncode==0 and r.stdout==block,r.stdout)

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
      'bad|g2|echo bad:ran; exit 1|0')
FIXED=RUNNER[:start]+"CASES='\n"+''.join(r+'\n' for r in ROWS)+"'\n"+RUNNER[end:]
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
HOSTILE=dict(os.environ,HOME=str(FIX/'home'),TMPDIR=str(FIX/'tmp'),PYTHONPATH=str(FIX/'poison'),
             SYNTH_SECRET='synthetic-secret',SYNTH_EMPTY='')
def rt(*a,stdin=None):
    r=subprocess.run(['sh','tests/run-tests.sh',*a],cwd=str(FIX),env=HOSTILE,input=stdin,
                     capture_output=True,text=True,errors='replace',timeout=120)
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
check('runner 失败入口附错误尾段','| bad:ran' in out)
for label,args,stdin in (('未知组',('group','nope'),None),
                         ('选不到入口的 selector',('select',),'[["full"],["group","nope"]]'),
                         ('非法 selector JSON',('select',),'{"full":1}'),('空 selector',('select',),'[]'),
                         ('未知模式',('nope',),None)):
    code,out=rt(*args,stdin=stdin)
    check('runner 拒绝%s（rc=2，未跑任何入口）'%label,code==2 and not ran(out),'rc=%d\n%s'%(code,out[-300:]))
code,out=rt('select-paths',stdin='tests/run-tests.sh\0tools/check-rules.py\0')
check('select-paths：full 与同批定向组并存，且不受 PYTHONPATH 影响',
      code==0 and out.strip()=='[["full"], ["group", "gate"]]',out)
check('select-paths：无命中只给 smoke',P.select([])==[['smoke']])
code,out=rt('select-paths',stdin='tests/unregistered.py\0')
check('select-paths：未登记测试路径拒绝',code==2,out)
# 负控：去掉 env -i 后探针必须报泄漏，证明隔离断言不是空转
assert FIXED.count('env -i ')==1
(FIX/'tests/run-tests.sh').write_text(FIXED.replace('env -i ','env '),encoding='utf-8')
code,out=rt('case','probe')
check('负控：撤掉 env -i 后探针报泄漏',code==1 and 'probe:leak PYTHONPATH SYNTH_SECRET SYNTH_EMPTY' in out,out[-300:])

def tree(b):
    fs=[f for t in ('skills','prompt','subagents') for f in (b/t).rglob('*')]+[b/'tools/rule-claims.tsv',b/'tools/sync-targets.json']
    return {f.relative_to(b):os.readlink(f) if f.is_symlink() else f.read_bytes() if f.is_file() else 0 for f in fs}
check('逐例还原后守卫副本与仓库逐字节一致',tree(CASE)==tree(ROOT))
shutil.rmtree(TMP,ignore_errors=True)
print('---- check-rules／runner 回归：PASS %d / FAIL %d ----'%(PASS,FAIL))
raise SystemExit(1 if FAIL else 0)
PYEOF

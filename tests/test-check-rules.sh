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

def check(label,ok,detail=''):
    global PASS,FAIL
    if ok:PASS+=1;print('PASS  '+label)
    else:FAIL+=1;print('FAIL  '+label+(('：'+detail) if detail else ''))

# 守卫输入只复制一次（skills/prompt/subagents 与资源登记表）；每例记录夹具改动过的路径，
# 跑完按仓库原件逐个还原或删除，下一例仍从原样副本开始（收尾逐字节核对副本）。
CASE=TMP/'case'
for top in ('skills','prompt','subagents'):shutil.copytree(ROOT/top,CASE/top,symlinks=True)
(CASE/'tools').mkdir()
for f in ('sync-targets.json',):shutil.copyfile(ROOT/'tools'/f,CASE/'tools'/f)
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
def registry(p,fn):
    f=p/'tools/sync-targets.json';d=json.loads(f.read_text(encoding='utf-8'));fn(d)
    f.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
def skill_obj(p,fn):registry(p,lambda d:fn(next(o for o in d['objects'] if o['type']=='skill')))
def register(p,skill,*rels):
    def fn(d):
        o=next(o for o in d['objects'] if o['id']==skill);o['resources']=sorted(set(o['resources'])|set(rels))
    registry(p,fn)
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

# ── 资源登记可读性 ──
case('资源登记不可用',3,'资源登记不可用',lambda p:(p/'tools/sync-targets.json').write_text('{bad'))

# ── 加载边（正文即真源，不再有独立登记表）──
LOAD='\n- 写入前条件加载 `luno-authoring`。\n'
case('新增条件加载边直接通过',0,'无问题',lambda p:append(p,SYNC,LOAD))
case('加载目标缺失',1,'加载目标缺失',lambda p:append(p,SYNC,'\n- 写入前另加载 `luno-absent`。\n'))
case('必需加载被降级为条件加载',1,'必需加载降级',
     lambda p:edit(p,'skills/luno-core/references/execution.md',
                   lambda s:s.replace('先完整加载 `luno-core`','条件加载 `luno-core`')))
def no_loads(p):
    for f in scope_files(p):
        t=f.read_text(encoding='utf-8');u=G.LOAD_RE.sub('加载说明',t)
        if u!=t:f.write_text(u,encoding='utf-8')
case('加载语句核对为空（同时报必需加载降级）',1,'0 条加载语句被核对',no_loads)

# 包内上游入口迁移后，仍须检测必需读取被弱化。
case('CCHP 上游入口必需读取降级',1,'必需加载降级',
     lambda p:edit(p,'skills/luno-platform/references/cchp.md',
                   lambda s:s.replace('先完整读取 `references/cchp-upstream/ENTRY.md`',
                                      '按需读取 `references/cchp-upstream/ENTRY.md`')))

# ── 资源边 ──
def new_resource(p,registered):
    (p/'skills/luno-core/references/new-structural.md').write_text('x\n')
    append(p,SYNC,'\n`references/new-structural.md`\n')
    if registered:register(p,'luno-core','skills/luno-core/references/new-structural.md')
case('正文引用的资源未登记',1,'资源未登记',lambda p:new_resource(p,False))
case('正文引用且登记后通过',0,'无问题',lambda p:new_resource(p,True))
case('包内新增文件未登记',1,'包内文件未登记',
     lambda p:(p/'skills/luno-core/references/stray.md').write_text('x\n'))
case('登记了不存在的包资源',1,'登记的包资源缺失',
     lambda p:register(p,'luno-core','skills/luno-core/references/ghost.md'))
case('包资源登记不能跨出所属包',1,'包资源不属于本包',
     lambda p:register(p,'luno-core','tools/sync-targets.json'))
case('包资源登记形态损坏不能跳过',1,'包资源登记结构',
     lambda p:skill_obj(p,lambda o:o.__setitem__('resources',None)))
def unregistered_skill(p):
    target=p/'skills/luno-new';target.mkdir()
    (target/'SKILL.md').write_text('---\nname: luno-new\n---\n正文\n')
case('新增技能入口必须登记',1,'技能源未登记',unregistered_skill)
case('正文引用的资源不存在',1,'资源引用断链',lambda p:append(p,SYNC,'\n`references/absent.md`\n'))
def no_resources(p):
    for f in scope_files(p):
        t=f.read_text(encoding='utf-8');u=G.RESOURCE_RE.sub('',t)
        if u!=t:f.write_text(u,encoding='utf-8')
case('资源路径核对为空',3,'0 条资源路径被核对',no_resources)
case('资源引用逃逸',1,'资源引用逃逸',lambda p:append(p,SYNC,'\n`references/../../outside.md`\n'))
def symlinked(p):
    (p/'skills/luno-core/references/linked.md').symlink_to(p/'tools/sync-targets.json')
    append(p,SYNC,'\n`references/linked.md`\n')
case('资源经 symlink',1,'资源引用逃逸',symlinked)

# Cross-package resources are now part of the same structural contract.
# These cases stay in the existing gate/full entry: cross edges are used by roles and prompt.
CROSS='luno-core/references/cross-structural.md'
def cross_resource(p,reg=True,source='prompt/LUNO.md'):
    (p/('skills/'+CROSS)).write_text('fixture\n',encoding='utf-8')
    append(p,source,'\n先完整加载 `'+CROSS+'`。\n')
    if reg:register(p,'luno-core','skills/'+CROSS)
case('跨包资源完整登记且不误判技能加载',0,'无问题',cross_resource)
case('跨包资源未登记',1,'资源未登记',lambda p:cross_resource(p,False))
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
      'bad|g2|echo bad:ran; exit 1|0','long|g1|sh tests/long.sh|1','unit|g1|cd tests && python3 -B -m unittest -v unitdemo|1',
      'unitbad|g2|cd tests && python3 -B -m unittest -v unitbad|0','slow|g3|sh -c "sleep 30"|0')
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
check('runner 失败入口保留完整原文与原始退出码','bad:ran' in out and 'END bad exit 1' in out,out[-200:])
for label,args,stdin in (('未知组',('group','nope'),None),
                         ('选不到入口的 selector',('select',),'[["full"],["group","nope"]]'),
                         ('非法 selector JSON',('select',),'{"full":1}'),('空 selector',('select',),'[]'),
                         ('未知模式',('nope',),None)):
    code,out=rt(*args,stdin=stdin)
    check('runner 拒绝%s（rc=2，未跑任何入口）'%label,code==2 and not ran(out),'rc=%d\n%s'%(code,out[-300:]))
code,out=rt('select-paths',stdin='tests/run-tests.sh\0tools/check-rules.py\0')
check('select-paths：full 与定向组并存，且不受 PYTHONPATH 影响',code==0 and out.strip()=='[["full"], ["group", "auth"], ["group", "identity"], ["group", "verify"], ["group", "minis-verify"], ["group", "lh-wiring"], ["group", "gate"]]',out)
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
    check('select：%s 展开全 12 入口各一次'%pth,expand(P.select([pth]))==names,str(P.select([pth])))
check('select：普通未映射正文只 smoke',P.select(['README.md'])==[['smoke']])
check('select：已映射 .md 照表不作后缀豁免',all(x in P.select([p]) for p,x in (('skills/luno-core/references/review.md',['case','test-redact.py']),('skills/luno-platform/references/minis.md',['case','test-minis-verify.py']),('skills/luno-surge/references/plugin-authoring.md',['case','test-surge-package.py']))) and P.select(['skills/luno-core/references/review.md'])!=P.select(['README.md']))
check('select：collect 双消费者',{['case','test-lh-collect.py'],['case','test-lh-deploy.py']}<=set(map(list,P.select(['tools/lh-collect.py']))))
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
G=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_AUTHOR_NAME='f',GIT_AUTHOR_EMAIL='f@e',GIT_COMMITTER_NAME='f',GIT_COMMITTER_EMAIL='f@e')
R2=TMP/'ci';R2.mkdir()
def g(*a):
    r=subprocess.run(('git',)+a,cwd=str(R2),env=G,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    return r.stdout.strip()
def cm(m):
    g('add','-A');g('commit','-q','-m',m);return g('rev-parse','HEAD')
def ci(ev,**kw):
    env=dict(G,PATH=os.environ['PATH'],HOME=str(TMP/'h'),TMPDIR=str(TMP/'t'),EVENT_NAME=ev);env.update(kw)
    (R2/'tests/selected.json').unlink(missing_ok=True)
    return subprocess.run([sys.executable,'-I','-B','-'],input=CI,cwd=str(R2),env=env,capture_output=True,text=True,timeout=120)
def plan(r):return [l[9:] for l in r.stdout.splitlines() if l.startswith('selector ')][-1]
(R2/'tests').mkdir();shutil.copyfile(ROOT/'tests/test_paths.py',R2/'tests/test_paths.py')
(R2/'tests/run-tests.sh').write_text('cat > tests/selected.json\n')
g('init','-q','-b','main');(R2/'README.md').write_text('b\n');C1=cm('c1')
(R2/'tools').mkdir();(R2/'tools/check-rules.py').write_text('g\n');C2=cm('c2')
g('checkout','-q','-b','feat',C1);(R2/'skills/luno-core/references').mkdir(parents=True)
(R2/'skills/luno-core/references/review.md').write_text('f\n');C3=cm('c3')
g('checkout','-q','main');g('merge','-q','--no-ff','-m','m','feat');MM=g('rev-parse','HEAD')
r=ci('pull_request',BASE_SHA=C2,HEAD_SHA=C3,MERGE_SHA=MM)
check('CI：PR 测 B→M，base 前进不算 PR 变化',r.returncode==0 and plan(r)=='[["smoke"], ["group", "identity"]]' and 'identity' in (R2/'tests/selected.json').read_text(),r.stdout[-300:]+r.stderr[-300:])
g('checkout','-q','-b','feat2',C1);(R2/'tools/lh-verify.py').write_text('v\n');cm('d1')
(R2/'skills/luno-platform/references').mkdir(parents=True);(R2/'skills/luno-platform/references/minis.md').write_text('m\n');D2=cm('d2')
r=ci('push',BEFORE_SHA=C1,AFTER_SHA=D2)
check('CI：push 取 before→after，多提交都在',r.returncode==0 and all(x in plan(r) for x in ('test-lh-verify.py','test-redact.py','test-minis-verify.py')),r.stdout[-300:])
for kw,label in ((dict(BASE_SHA=C2,HEAD_SHA=C3,MERGE_SHA='a'*40),'缺对象'),(dict(BEFORE_SHA='0'*40,AFTER_SHA=D2),'全零')):
    r=ci('push' if 'BEFORE_SHA' in kw else 'pull_request',**kw)
    check('CI：%s阻断且不得到成功 smoke'%label,r.returncode==2 and 'smoke' not in r.stdout and not (R2/'tests/selected.json').exists(),r.stderr[-200:])

# ── 收尾：正常/失败/TERM 都只观察夹具自建的精确路径，不扫 /tmp ──
left=lambda:sorted(p.name for p in (FIX/'tmp').iterdir())
check('清理：正常与失败轮均删本轮 WORK 根',not left(),str(left()))
p=subprocess.Popen(['sh','tests/run-tests.sh','case','slow'],cwd=str(FIX),env=HOSTILE,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
time.sleep(3);p.terminate();o=p.communicate(timeout=120)[0].decode('utf-8','replace')
check('清理：TERM 停本轮进程组、删根并以 143 退出',p.returncode==143 and not left() and 'cleanup 完成' in o,'rc=%d %s'%(p.returncode,left()))
S=TMP/'sentinel';S.mkdir();(S/'keep').write_text('x')
MOD=FIXED.replace('        shutil.rmtree(NAME, dir_fd=PFD)','        os.rename(NAME, NAME+"-moved", src_dir_fd=PFD, dst_dir_fd=PFD)\n        os.symlink(%r, NAME, dir_fd=PFD)\n        shutil.rmtree(NAME, dir_fd=PFD)'%str(S))
assert MOD!=FIXED
(FIX/'tests/run-tests.sh').write_text(MOD,encoding='utf-8');code,out=rt('case','lint')
(FIX/'tests/run-tests.sh').write_text(FIXED,encoding='utf-8')
check('清理：根被换成外部链接时非零、披露残留、不误删哨兵',code==2 and 'cleanup 失败' in out and (S/'keep').read_text()=='x',out[-300:])
for d in list((FIX/'tmp').iterdir()):
    shutil.rmtree(d) if not d.is_symlink() else d.unlink()

def tree(b):
    fs=[f for t in ('skills','prompt','subagents') for f in (b/t).rglob('*')]+[b/'tools/sync-targets.json']
    return {f.relative_to(b):os.readlink(f) if f.is_symlink() else f.read_bytes() if f.is_file() else 0 for f in fs}
check('逐例还原后守卫副本与仓库逐字节一致',tree(CASE)==tree(ROOT))
shutil.rmtree(TMP,ignore_errors=True)
print('---- check-rules／runner 回归：PASS %d / FAIL %d ----'%(PASS,FAIL))
raise SystemExit(1 if FAIL else 0)
PYEOF

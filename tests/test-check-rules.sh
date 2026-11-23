#!/bin/sh
# 结构守卫 tools/check-rules.py 的反例回归（固定 rc 0/1/2/3 与错误类别），以及测试登记的结构一致性：
# tests/ 下入口是否登记、选路规则是否指向已登记入口、runner 头部选路块是否等于 test_paths.py 的渲染结果。
# 运行器、信号、选路与 CI 选路段的真实进程回归已拆到 tests/test-runner.sh（独立入口，只由 runner、
# 选路表、CI workflow 与本文件自身的变更命中），断言与真实进程边界原样迁移，未删判据。
# 成本事实（2026-11-17 本机 iSH/aarch64）：拆出 runner 回归后本入口只跑守卫反例与登记结构，实测耗时见 PR。
# 降级条件：未来减少本入口运行频率或提速，须单独提交等价性证明（退出码与 stdout 断言不变），不得删判据换速度。
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

# ── 平台词只留在端适配与明确例外（Markdown 含 frontmatter，脚本不在此守卫范围）──
NEUTRAL='skills/luno-authoring/references/prose.md'
line=(ROOT/NEUTRAL).read_text(encoding='utf-8').count('\n')+2
case('中立正文的平台词报路径和行号',1,'平台词超出适配层：%s:%d: Minis'%(NEUTRAL,line),
     lambda p:append(p,NEUTRAL,'\nMinis\n'))
case('frontmatter 的平台词不能绕过',1,'平台词超出适配层：%s:2: LobeHub'%ENTRY,
     lambda p:edit(p,ENTRY,lambda s:s.replace('---\n','---\nmetadata: LobeHub\n',1)))
# 契约夹具独立列出受限词与例外，不从守卫的正则或白名单生成，避免同错同过。
WORDS=('Minis','iSH','LobeHub','OnlyBoxes','/var/minis','minis://','subagent_task','max_minutes')
for word in WORDS:
    g=G.Guard(CASE);g.platform_words(NEUTRAL,'说明\n'+word+'\n')
    check('平台词判据 '+word,g.hard==['平台词超出适配层：%s:2: %s'%(NEUTRAL,word)],str(g.hard))
ALLOWED=('skills/luno-platform/SKILL.md',
         'skills/luno-platform/references/runtime-minis.md',
         'skills/luno-core/references/sync.md',
         'skills/luno-ops/references/execution-environment.md',
         'skills/luno-ops/references/cfst.md',
         'skills/luno-surge/references/command-reference.md',
         'skills/luno-surge/references/SOURCE.md',
         'skills/luno-surge/references/official-sources.md')
for rel in ALLOWED+('prompt/LUNO.md','subagents/LENS.md','skills/luno-surge/scripts/install.sh'):
    g=G.Guard(CASE);g.platform_words(rel,' '.join(WORDS))
    check('平台词范围例外 '+rel,not g.hard,str(g.hard))
g=G.Guard(CASE);g.platform_words(NEUTRAL,'OpenMinis MinisTools iSHell LobeHubby OnlyBoxesAPI')
check('产品名边界不误伤较长英文词',not g.hard,str(g.hard))

# ── 资源登记可读性 ──
case('资源登记不可用',3,'资源登记不可用',lambda p:(p/'tools/sync-targets.json').write_text('{bad'))

# ── 加载边（正文即真源，不再有独立登记表）──
LOAD='\n- 写入前条件加载 `luno-authoring`。\n'
case('新增条件加载边直接通过',0,'无问题',lambda p:append(p,SYNC,LOAD))
case('加载目标缺失',1,'加载目标缺失',lambda p:append(p,SYNC,'\n- 写入前另加载 `luno-absent`。\n'))
case('必需加载被降级为条件加载',1,'必需加载降级',
     lambda p:edit(p,'skills/luno-core/references/execution.md',
                   lambda s:s.replace('先完整加载 `luno-core`','条件加载 `luno-core`')))
case('当前端入口的必需加载不能降级',1,'必需加载降级',
     lambda p:edit(p,ENTRY,lambda s:s.replace('必须完整加载 `luno-platform`',
                                             '条件加载 `luno-platform`',1)))
def no_loads(p):
    for f in scope_files(p):
        t=f.read_text(encoding='utf-8');u=G.LOAD_RE.sub('加载说明',t)
        if u!=t:f.write_text(u,encoding='utf-8')
case('加载语句核对为空（同时报必需加载降级）',1,'0 条加载语句被核对',no_loads)

# 运行端必读入口：任一端判定或合用指针被删掉都要失败。
for rel,fragment in G.REQUIRED_READS:
    case('运行端必读入口缺失 %s：%s'%(rel.rsplit('/',1)[1],fragment[:24]),1,'必需加载降级',
         lambda p,rel=rel,fragment=fragment:edit(p,rel,lambda s:s.replace(fragment,'',1)))
case('运行端资源改为可选读取',1,'必需加载降级',
     lambda p:edit(p,'skills/luno-platform/SKILL.md',
                   lambda s:s.replace('）读 `references/runtime-host.md`','）可选读 `references/runtime-host.md`',1)
                             .replace('和 `references/runtime-host.md`','，可选读 `references/runtime-host.md`',1)))

# ── 资源边 ──
case('角色归属下沉后的必需读取不能降级',1,'必需加载降级',
     lambda p:edit(p,ENTRY,lambda s:s.replace('先完整读取 `references/review.md`',
                                             '按需读取 `references/review.md`',1)))
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
def missing_with_id(p):
    def fn(o):
        o['ends']['minis']['present']=False
        o['ends']['minis']['id']='leftover'
    skill_obj(p,fn)
case('缺位仍带 ID',1,'缺位身份冲突',missing_with_id)
case('身份端缺 present',1,'身份端结构',lambda p:skill_obj(p,lambda o:o['ends']['minis'].pop('present')))
case('宿主端也须显式登记',1,'身份端结构',lambda p:skill_obj(p,lambda o:o['ends'].pop('codex')))
case('宿主端路径须为 HOME 相对路径',1,'宿主端路径形态',
     lambda p:skill_obj(p,lambda o:o['ends']['codex'].__setitem__('paths',['/tmp/skill'])))
case('宿主端种类须符合对象类型',1,'宿主端身份种类冲突',
     lambda p:skill_obj(p,lambda o:o['ends']['codex'].__setitem__('kind','field')))
case('生成常驻文件须使用对应 renderer',1,'宿主端身份种类冲突',
     lambda p:registry(p,lambda d:d['objects'][0]['ends']['codex'].__setitem__('renderer','claude-main')))
def shared_host_path(p):
    def fn(d):
        sk=[o for o in d['objects'] if o['type']=='skill']
        sk[1]['ends']['codex']['paths']=sk[0]['ends']['codex']['paths']
    registry(p,fn)
case('宿主端路径不能被不同对象占用',1,'宿主端身份多占',shared_host_path)
case('原生角色 renderer',1,'宿主端身份种类冲突',
     lambda p:registry(p,lambda d:[o for o in d['objects'] if o['id']=='subagents/LENS.md'][0]['ends']['codex'].__setitem__('renderer','claude-role')))
case('原生角色 model',1,'宿主端原生角色登记冲突',
     lambda p:registry(p,lambda d:[o for o in d['objects'] if o['id']=='subagents/LENS.md'][0]['ends']['codex'].__setitem__('model','other-model')))
case('原生角色 model_reasoning_effort',1,'宿主端原生角色登记冲突',
     lambda p:registry(p,lambda d:[o for o in d['objects'] if o['id']=='subagents/LENS.md'][0]['ends']['codex'].__setitem__('model_reasoning_effort','low')))
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

# 产品入口下沉后，原产品边界仍须逐个负控；从守卫声明现读，不钉正文措辞。
PRODUCT_PATHS={'skills/luno-platform/SKILL.md', 'skills/luno-platform/references/cchp.md'}
PRODUCT_OBS=[(src,head) for src,head in G.OBLIGATIONS if src in PRODUCT_PATHS and head!='## 范围']
assert PRODUCT_OBS, '产品入口义务负控不能空转'
def drop_product_obs(p):
    for src,head in PRODUCT_OBS:edit(p,src,lambda s,head=head:s.replace(head,head+'-removed',1))
case('义务块缺失（产品入口 %d 个义务逐个）'%len(PRODUCT_OBS),1,'义务块缺失或重复',drop_product_obs,n=len(PRODUCT_OBS))

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
def unreadable_with_retired(p):
    (p/'tools/sync-targets.json').write_text('{bad')
    inject(p)
case('登记不可解析仍检查退役官方资源',1,'禁止分发完整官方资源',unreadable_with_retired,n=len(RETIRED))

# ── frontmatter 剥离 ──
for text,want in (('---\n---\n正文\n---\n尾部','正文\n---\n尾部'),
                  ('---\nname: x\n---\n正文\n---\n尾部','正文\n---\n尾部'),
                  ('---\nname: x\n未结束','---\nname: x\n未结束')):
    check('strip_frontmatter %r'%text,G.strip_frontmatter(text)==want)


# ── 用例表与选路登记的结构一致性 ──
RUNNER=(ROOT/'tests/run-tests.sh').read_text(encoding='utf-8')
start=RUNNER.index("CASES='\n");end=RUNNER.index("\n'\n",start)+3
REAL_CASES=[l.split('|') for l in RUNNER[start+7:end-2].splitlines() if l]

# 登记一致性：tests/ 下每个测试入口都在用例表里，且每条选路规则都能选到入口
names={c[0] for c in REAL_CASES};groups={c[1] for c in REAL_CASES}
entries={f.name for f in (ROOT/'tests').iterdir() if re.match(r'test-.*\.(py|sh)$',f.name)}
check('tests/ 下测试入口全部登记',entries<=names,str(sorted(entries-names)))
check('用例表入口文件均存在',all((ROOT/'tests'/n).is_file() or (ROOT/'tools'/n).is_file() for n in names))
spec2=importlib.util.spec_from_file_location('paths',ROOT/'tests/test_paths.py')
P=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(P)
bad=[s for _,s,_ in P.PATHS_RULES if not (s==('full',) or (s[0]=='group' and s[1] in groups) or (s[0]=='case' and s[1] in names))]
check('选路规则都指向已登记入口',not bad,str(bad))
r=subprocess.run(['sh',str(ROOT/'tests/run-tests.sh'),'render-paths'],capture_output=True,text=True)
block=RUNNER[RUNNER.index('# >>> PATHS_RULES\n')+18:RUNNER.index('# <<<\n')]
check('runner 头部选路块与 render-paths 一致',r.returncode==0 and r.stdout==block,r.stdout)
def tree(b):
    fs=[f for t in ('skills','prompt','subagents') for f in (b/t).rglob('*')]+[b/'tools/sync-targets.json']
    return {f.relative_to(b):os.readlink(f) if f.is_symlink() else f.read_bytes() if f.is_file() else 0 for f in fs}
check('逐例还原后守卫副本与仓库逐字节一致',tree(CASE)==tree(ROOT))
shutil.rmtree(TMP,ignore_errors=True)
print('---- check-rules／登记结构回归：PASS %d / FAIL %d ----'%(PASS,FAIL))
raise SystemExit(1 if FAIL else 0)
PYEOF

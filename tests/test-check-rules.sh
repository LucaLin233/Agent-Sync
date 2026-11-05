#!/bin/sh
# B+ 四类结构反例；原命名/历史路径/逐字期望/片段副本检查随实现退休。
# 只测已保留行为；固定错误类别和非零失败传播，不放宽断言。
#
# 成本与准入（2026-11-02 补；口径按 `skills/luno-sync/references/test-authoring.md`〈准入〉〈降耗〉）：
#   ① 必要性（本文件为何必须这么重，不采用降级）：后半段（F2）把**真实** `tests/run-tests.sh`
#      复制进最小夹具根执行，逐项核对白名单环境隔离、控制变量（`SELFTEST_LIMIT`／
#      `SELFTEST_UNIT_FAIL`）、伪造复用日志、`case`／`group`／`select`／`select-paths`／
#      `render-paths`／`smoke`／`full` 的选路与「选中 N · 实跑 N」账本一致性，并以「同一夹具根、
#      唯一变异＝删掉 `env -i`」的负控证明断言非空转；前端另覆盖 rc=0／1／2／3 四态。这些判据的
#      被测对象就是运行器本身，只能在真实 runner 与子进程边界上验证——打桩、只跑单例或抽纯函数都会
#      丢掉「隔离是否真的成立、选路是否真的执行」这一被测行为，故不以降级换耗时。
#   ② 跑集归属（非「每批都跑」）：本文件属结构守卫入口，按 `tests/run-tests.sh` 头部〈变更路径→
#      必跑套件〉归 `gate`，`full` 的选路条件是「运行器与聚合入口」；故仅在变更路径选中 `full` 或
#      `gate` 时随既有选路执行，纯正文变更可只选 `smoke`。留在 `full` 内的理由：`env -i` 白名单与
#      入口选路是同步链共用入口，任一处回退即假绿（截断跑仍 PASS）、假红或调用方环境泄漏；本批 F2
#      修复只在本文件被证。发行者 2026-11-02 裁定理由成立。
#   ③ 实测（仅本机 iSH／Alpine 3.21.0／aarch64，2026-11-02 iSH 实测，不外推；调度器单入口口径）：
#      一轮 `full` 248 s 中**本文件入口** 124 s（非 `group gate` 整组）；另一轮 `full` 172 s 中同入口
#      90 s；最近一轮 `full` 101 s、同入口 37 s、同组 `tests/test-check-rules-driver.sh` 3 s。
#      **波动大**：同环境同入口 124／90／37 s，不可归因到单个 case 或组内分项，不以互相加减当定值；
#      另一次运行在 240 s 超时，该实验**未完成**，不作耗时证据；本轮只改注释、未重跑 `full`，耗时
#      取自上一轮 101 s（其后无运行逻辑改动）。
#   ④ 预算与例外：默认预算是调度器**单个入口** ≤ 10 s（非 `gate` 整组），本入口 37 s 超限；本文件
#      另超「单文件 ≤ 20 KiB」（按 `wc -c` 现读，不写定值以免自引用漂移）。两项由当批发布者在授权内按「**不削弱**上述保护」接受为
#      本批例外（理由见①；本批历史超额不是通用门限）。降级须**另批**先证明同等覆盖（等价判据、
#      变异仍可达）；**不得跳过、不得移出 `full`**，也不得删安全断言或用打桩替换真实 runner 边界。
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
python3 -B - "$ROOT" <<'PYEOF'
import contextlib, importlib.util, io, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(sys.argv[1]); spec=importlib.util.spec_from_file_location('guard',ROOT/'tools/check-rules.py')
G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)
PASS=FAIL=COUNT=0
LIMIT=os.environ.get('SELFTEST_LIMIT','0')
if not LIMIT.isdigit(): raise SystemExit(2)
LIMIT=int(LIMIT)

_fixture_tmp=tempfile.TemporaryDirectory(prefix='bplus-guard.')
_fixture=Path(_fixture_tmp.name)/'repo'
shutil.copytree(ROOT,_fixture,ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc'))
_snapshot={p.relative_to(_fixture):p.read_bytes() for p in _fixture.rglob('*') if p.is_file()}
def restore_fixture():
    for p in _fixture.rglob('*'):
        rel=p.relative_to(_fixture)
        if p.is_symlink() or (p.is_file() and rel not in _snapshot):p.unlink()
    for rel,data in _snapshot.items():
        p=_fixture/rel
        if not p.exists() or p.read_bytes()!=data:
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
def case(label, want, category, setup=lambda p: None):
    global PASS,FAIL,COUNT
    if LIMIT and COUNT>=LIMIT:return
    COUNT+=1
    try:
        setup(_fixture)
        out=io.StringIO();guard=G.Guard(_fixture)
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):rc=guard.run()
        categories=guard.hard+guard.incomplete+guard.soft if rc else ['无问题']
        if rc==want and category in categories:
            PASS+=1;print('PASS  '+label)
        else:
            FAIL+=1;print('FAIL  '+label+' rc='+str(rc)+' expected='+str(want)+' category='+category);print(out.getvalue())
    finally:restore_fixture()

def edit(p,rel,fn):
    f=p/rel;before=f.read_text();after=fn(before)
    assert before!=after,'夹具变异空转'
    f.write_text(after)
def registry(p,fn):
    edit(p,'tools/sync-targets.json',lambda s:json.dumps(fn(json.loads(s)),ensure_ascii=False))
def change_obj(p,fn):
    def apply(d):
        fn(next(x for x in d['objects'] if x['id']=='luno-sync'));return d
    registry(p,apply)
def edge_append(p,line):
    f=p/'tools/rule-claims.tsv';f.write_text(f.read_text()+line+'\n')
def missing_resource(p):
    edit(p,'skills/luno-sync/SKILL.md',lambda s:s+'\n`references/absent.md`\n')
def escape(p):
    edit(p,'skills/luno-sync/SKILL.md',lambda s:s+'\n`references/../../outside.md`\n')
def duplicate_id(p):
    def fn(d):
        sk=[x for x in d['objects'] if x['type']=='skill'];sk[1]['ends']['lobehub']['id']=sk[0]['ends']['lobehub']['id'];return d
    registry(p,fn)
def block_remove(p):
    src,heading=G.OBLIGATIONS[0]
    edit(p,src,lambda s:s.replace(heading,heading+'-removed',1))
def block_empty(p):
    src,heading=G.OBLIGATIONS[0]
    def fn(s):
        lines=s.splitlines();i=lines.index(heading)+1;j=i
        while j<len(lines) and not lines[j].startswith('#'):j+=1
        return '\n'.join(lines[:i]+lines[j:])+'\n'
    edit(p,src,fn)
def frontmatter_only(p):
    # Loading statements in frontmatter are not operative body edges.
    f=p/'skills/luno-sync/SKILL.md';s=f.read_text();f.write_text(s.replace('name: luno-sync','name: luno-sync\nmetadata: "必须加载 `luno-example-only`"',1))

case('完整正控',0,'无问题')
case('frontmatter 不纳入加载边',0,'无问题',frontmatter_only)
case('未知字段仅属正文非逐字约束',0,'无问题',lambda p:edit(p,'skills/luno-sync/SKILL.md',lambda s:s+'\n补充说明。\n'))
case('缺登记表不得绿',3,'读取失败',lambda p:(p/'tools/rule-claims.tsv').unlink())
case('空登记表不得绿',3,'条款登记为空',lambda p:(p/'tools/rule-claims.tsv').write_text('# empty\n'))
case('加载未登记',3,'加载登记',lambda p:edit(p,'skills/luno-sync/SKILL.md',lambda s:s+'\n必须加载 `luno-review`\n'))
case('加载形态错配',1,'加载形态',lambda p:(edit(p,'skills/luno-sync/SKILL.md',lambda s:s+'\n必须加载 `luno-review`\n'),edge_append(p,'skills/luno-sync/SKILL.md\tluno-review\t条件加载\tfixture')))
case('资源未登记且不存在',1,'资源引用断链',missing_resource)
case('资源引用逃逸',1,'资源引用逃逸',escape)
case('来源不存在',3,'加载边来源缺失',lambda p:edge_append(p,'skills/luno-sync/absent.md\treferences/absent.md\t资源条件\tfixture'))
case('未知形态',3,'加载形态',lambda p:edge_append(p,'skills/luno-sync/SKILL.md\tluno-review\t未知\tfixture'))
case('重复资源登记',1,'重复登记',lambda p:edge_append(p,next(x for x in (p/'tools/rule-claims.tsv').read_text().splitlines() if x and not x.startswith('#'))))
case('身份登记不可读',3,'身份登记不可用',lambda p:(p/'tools/sync-targets.json').write_text('{bad'))
case('空身份范围不得绿',3,'身份登记不可用',lambda p:(p/'tools/sync-targets.json').write_text('{"objects":[]}'))
case('身份与技能源不一致',1,'身份与技能源不一致',lambda p:change_obj(p,lambda o:o.__setitem__('id','wrong-name')))
case('同一平台 ID 多占',1,'平台身份多占',duplicate_id)
case('缺位仍带 ID',1,'缺位身份冲突',lambda p:change_obj(p,lambda o:o['ends']['lobehub'].__setitem__('present',False)))
case('ID 非法形态',1,'平台身份形态',lambda p:change_obj(p,lambda o:o['ends']['lobehub'].__setitem__('id','bad')))
case('义务块缺失',1,'义务块缺失或重复',block_remove)
case('义务块空内容',1,'义务块为空',block_empty)
def existing_unregistered(p):
    f=p/'skills/luno-sync/references/new-structural.md';f.write_text('fixture')
    edit(p,'skills/luno-sync/SKILL.md',lambda s:s+'\n`references/new-structural.md`\n')
def declared_absent(p):
    edge_append(p,'skills/luno-sync/SKILL.md\treferences/new-structural.md\t资源条件\tfixture')
def symlink_target(p):
    f=p/'skills/luno-sync/references/linked.md';f.symlink_to(p/'README.md')
    edit(p,'skills/luno-sync/SKILL.md',lambda s:s+'\n`references/linked.md`\n')
case('现存资源未登记不得绿',3,'资源加载边',existing_unregistered)
case('已登记资源正文无此边',1,'资源引用断链',declared_absent)
case('资源 symlink 不得沿用',1,'资源引用逃逸',symlink_target)
case('身份端缺 present',1,'身份端结构',lambda p:change_obj(p,lambda o:o['ends']['minis'].pop('present')))
case('Minis 身份路径误配',1,'Minis 身份路径冲突',lambda p:change_obj(p,lambda o:o['ends']['minis'].__setitem__('path','/var/minis/skills/wrong/SKILL.md')))
case('义务块重复不得绿',1,'义务块缺失或重复',lambda p:edit(p,G.OBLIGATIONS[0][0],lambda s:s+'\n'+G.OBLIGATIONS[0][1]+'\nfixture\n'))

# 下列 11 例沿用旧 T20 的原故障构造与退出码；仅夹具 schema／装载口径适配 B+。
SYNC='skills/luno-sync/SKILL.md'
CLAIMS_REL='tools/rule-claims.tsv'
class LegacyWork:
    def __init__(self,root):self.root=str(root);self.base=root
    def path(self,rel):return str(self.base/rel)
    def mkdirs(self,rel):(self.base/rel).mkdir(parents=True,exist_ok=True)
    def read(self,rel):return (self.base/rel).read_text()
    def write(self,rel,text):
        p=self.base/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    def append(self,rel,text):
        if rel==CLAIMS_REL:
            for line in text.splitlines():
                if line.strip():claims_append(self,line)
        else:self.write(rel,self.read(rel)+text)
def setign(w):pass  # 命名 lint 与豁免台账已退役；不改变被保留结构故障。
def claims_append(w,line):
    f=line.split('\t');f+=['']*(7-len(f))
    label,src,target,form=f[:4]
    if form in ('必需加载','条件加载'):
        target=re.search(r'luno-[a-z0-9-]+',target)[0]
    w.write(CLAIMS_REL,w.read(CLAIMS_REL)+'\t'.join((src,target,form,label))+'\n')
def claims_keep(w,predicate):
    kept=[]
    for line in w.read(CLAIMS_REL).splitlines():
        if not line or line.startswith('#'):kept.append(line);continue
        src,target,form,label=line.split('\t')
        if predicate('\t'.join((label,src,target,form,'','',''))):kept.append(line)
    w.write(CLAIMS_REL,'\n'.join(kept)+'\n')
def legacy_case(label,rc,category,setup):
    category={'未登记资源加载边':'资源加载边','引用断链':'资源引用断链','资源加载边':'资源加载边形态'}.get(category,category)
    case(label,rc,category,lambda p:setup(LegacyWork(p)))

def _claim(row):
    def setup(w):
        setign(w)
        claims_append(w, row)
    return setup

def _c29(w):
    setign(w)
    w.mkdirs("skills/luno-sync/references")
    w.write("skills/luno-sync/references/extra.md", "x\n")
    w.append(SYNC, "\n- 需要时读取 `references/extra.md`。\n")

def _c30b(w):
    setign(w)
    w.mkdirs("skills/luno-surge/references")
    w.write("skills/luno-surge/references/ghost-resource.md", "x\n")
    w.append("skills/luno-surge/SKILL.md", "\n- 需要时读取 `references/ghost-resource.md`。\n")

def _c30c(w):
    setign(w)
    w.append("skills/luno-surge/references/SOURCE.md", "\n见 `references/ghost-missing.md`。\n")

def _c32(w):
    setign(w)
    w.mkdirs("skills/luno-sync/references")
    w.write("skills/luno-sync/references/foo.md", "x\n")
    claims_append(w, "资源边漂移测试\tskills/luno-sync/SKILL.md\treferences/foo.md"
                     "\t资源条件\t\t\t")

def _c33(w):
    setign(w)
    for dp, _dns, fns in os.walk(w.path("skills")):
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, w.root)
            if "luno-" not in rel:
                continue
            try:
                with open(p, encoding="utf-8") as fh:
                    t = fh.read()
            except (OSError, UnicodeDecodeError):
                # UnicodeDecodeError：二进制附件（如 luno-surge/assets/logo.png）现在也落在
                # `luno-` 路径下，文本读取必须跳过——质检脚本不扫描它，夹具也不该因它中断。
                continue
            if "`references/" in t:
                # 与原实现一致：旧版是 sed 's/…/…/g' —— **逐行全局**替换。这里若用 sed_re
                # （只替换每行首个命中）会残留同一行的第二个 token，E 项计数不为 0，
                # 于是输出另一条 rc=3 诊断，本用例要验的「空范围守卫」就测不到了。
                w.write(rel, re.sub(r"`references/[A-Za-z0-9_./-]*`", "", t))
    claims_keep(w, lambda l: not l.startswith("资源加载边"))


def _c44(w):
    setign(w)
    claims_keep(w, lambda l: not l.startswith("资源加载边（ops·GitHub）\t"))

def _c45(w):
    setign(w)
    claims_keep(w, lambda l: not l.startswith("资源加载边（ops·服务运行）\t"))

def _c46(w):
    setign(w)
    claims_keep(w, lambda l: not l.startswith("资源加载边（ops·远端文件与备份）\t"))

def _c47(w):
    setign(w)
    claims_keep(w, lambda l: not l.startswith("资源加载边（ops 服务→备份）\t"))
legacy_case("未登记的资源加载边", 3, "未登记资源加载边", _c29)
legacy_case("资源边目标不存在", 1, "引用断链",
     _claim("资源边断链测试\tskills/luno-review/SKILL.md\treferences/nope.md"
            "\t资源条件\t\t\t"))
legacy_case("新纳入覆盖的技能未登记资源边", 3, "未登记资源加载边", _c30b)
legacy_case("新纳入覆盖的技能资源引用断链必报", 1, "资源引用断链", _c30c)
legacy_case("资源边锚点非路径", 1, "资源加载边",
     _claim("资源边形态测试\tskills/luno-review/SKILL.md\t这不是路径\t资源条件\t\t\t"))
legacy_case("资源边真源漂移", 2, "条款真源漂移", _c32)
legacy_case("资源边范围为空不得通过", 3, "0 条资源路径被核对", _c33)
legacy_case("ops GitHub 资源边漏登", 3, "未登记资源加载边", _c44)
legacy_case("ops 服务运行资源边漏登", 3, "未登记资源加载边", _c45)
legacy_case("ops 远端文件与备份资源边漏登", 3, "未登记资源加载边", _c46)
legacy_case("ops 兄弟资源边漏登", 3, "未登记资源加载边", _c47)
def unit(label, actual, expected):
    global PASS,FAIL,COUNT
    if LIMIT and COUNT>=LIMIT:return
    COUNT+=1
    if actual==expected:PASS+=1;print('PASS  '+label)
    else:FAIL+=1;print('FAIL  '+label)
unit('空 frontmatter 不吞正文',G.strip_frontmatter('---\n---\n正文\n---\n尾部'),'正文\n---\n尾部')
unit('正文分隔线不截断',G.strip_frontmatter('---\nname: x\n---\n正文\n---\n尾部'),'正文\n---\n尾部')
unit('无结束行整体为正文',G.strip_frontmatter('---\nname: x\n未结束'),'---\nname: x\n未结束')
case('Minis 路径字段坏类型不得 traceback',1,'Minis 身份路径冲突',lambda p:change_obj(p,lambda o:o['ends']['minis'].__setitem__('path',[])))
def zero_load_scope(p):
    for top in ('skills','prompt','subagents'):
        for f in (p/top).rglob('*'):
            if f.is_file() and f.suffix in ('.md','.py','.sh'):
                text=f.read_text();out=G.LOAD_RE.sub('加载说明',text)
                if out!=text:f.write_text(out)
case('同短语跨文件出现仍须登记',3,'加载登记',lambda p:edit(p,'skills/luno-sync/SKILL.md',lambda s:s+'\n- 写入前先加载 `luno-memory`。\n'))
case('显式登记该文件后通过',0,'无问题',lambda p:(edit(p,'skills/luno-sync/SKILL.md',lambda s:s+'\n- 写入前先加载 `luno-memory`。\n'),edge_append(p,'skills/luno-sync/SKILL.md\tluno-memory\t必需加载\t同步技能记忆加载')))
case('加载语句核对为空不得通过',3,'0 条加载语句被核对',zero_load_scope)
# F4 现状定界：rc=2 只由「提示」产生（条款真源漂移），sync-all 按 0|2 放行、run-tests 仍记 FAIL
#   （测试门禁要求零提示，见 README 测试节）。0／1／2／3 四态在本文件内各有断言。
def soft_drift(p):
    rows=[l.split('\t') for l in (p/'tools/rule-claims.tsv').read_text().splitlines()
          if l and not l.startswith('#')]
    src,target=[(r[0],r[1]) for r in rows if r[2].startswith('资源')][0]
    edit(p,src,lambda s:s.replace(target,'references/不存在-占位.md'))
case('仅提示（rc=2）不阻断 sync-all',2,'条款真源漂移',soft_drift)

# ── G2（r2 修订）：缺件豁免只对 luno-surge 的 3 份官方参考原件有效 ────────────────
# 判据：豁免对象必为 luno-surge、路径限该包内且须映射到 manifest 的 3 件 `raw_sha256`；坏登记停检。
# 负控取 r2 实测漏洞（把 core 的必需资源塞进别处豁免即可让缺口转绿）；表驱动复用同一变异器，
# 正控即上行「三份在册」那条。
def exempt(p,obj_id,mutate):
    def apply(d):
        o=next(x for x in d['objects'] if x['id']==obj_id)
        blk=o.get('officialPackageResources')
        if not isinstance(blk,dict):blk=o['officialPackageResources']={'note':'fixture','paths':[]}
        mutate(blk);return d
    registry(p,apply)
def manifest_hash_shape(p):
    edit(p,G.INVENTORY_MANIFEST,lambda s:s.replace('d01acba41ad9e90869a32f708b48b117b7e96a6c92b422636503837dc107beb1','z'*64))
case('官方原件豁免正控（三份在册）',0,'无问题')
for _l,_o,_why,_m in (
    ('必需文件塞进 surge 豁免须报红','luno-surge','官方原件豁免路径非法',
     lambda b:b['paths'].append('skills/luno-core/references/delegation.md')),
    ('必需文件塞进其他对象豁免须报红','luno-core','官方原件豁免对象非法',
     lambda b:b['paths'].append('skills/luno-core/references/delegation.md')),
    ('豁免登记缺项须报红','luno-surge','官方原件豁免登记缺项',
     lambda b:b['paths'].remove('skills/luno-surge/references/upstream-SKILL.md')),
    ('豁免登记形态坏须报红','luno-surge','官方原件登记形态',
     lambda b:b.update(paths='skills/luno-surge/references/plugin-authoring.md')),
):
    case(_l,1,_why,(lambda p,o=_o,m=_m:exempt(p,o,m)))
case('manifest 哈希形态坏须报红',1,'官方原件 manifest 哈希形态',manifest_hash_shape)

# ── 运行器环境隔离／控制变量／防伪日志／入口选路回归（F2）─────────────────────────
# 位置与来源：本批撤回自建的两项 runner 专用文件（`tests/env-probe.sh`、`tests/test-runner-env.sh`
#   及其 `runner` 分组登记与选路规则）——那两项**无条件** `group runner` 回调自身，构成确定性递归
#   调用环，且负控副本跑在错误根（缺 `tests/env-probe.sh` 而红），判据迁到这里。本夹具属既有
#   `gate` 分组且**进 `full`**，故改 `tests/run-tests.sh` 选 `full` 时会真实执行下列回归。
# 做法：把**真实** `tests/run-tests.sh` 复制进最小夹具仓库（保留原相对布局：`tests/run-tests.sh`
#   ＋ ROOT=夹具根），**只替换 CASES 表**为「`gate` 组只含探针＋一个不在 gate/full 的对照项」，
#   夹具内**不含任何测试编排项**，故不会递归回本文件；不新建分组、不新增长期 harness／测试文件。
#   探针只报 10 位结论位（HOME／TMPDIR／PATH／7 个敏感变量的键存在性），不输出任何变量值。
# 断言：目标**确实执行**（探针标记出现、账本「选中 N · 实跑 N」一致、对照项标记不出现）、
#   退出码、位串精确值、smoke 守卫不选它。负控与正控**同一夹具根同一入口**，唯一变异是删掉
#   白名单的 `-i`（撤销 `env -i` 隔离）：探针必须仍能启动，因合成变量被继承而红，撤销后回绿。
def rchk(label, cond, detail=''):
    global PASS,FAIL
    if cond:PASS+=1;print('PASS  '+label)
    else:FAIL+=1;print('FAIL  '+label+(('：'+detail) if detail else ''))

_PROBE=r'''#!/bin/sh
# 夹具探针：只报结论位，不输出变量值；10 位全 1 才退出 0（否则本入口在运行器里记 FAIL）。
set -u
bits=""
add() { if [ "$1" = 1 ]; then bits="${bits}1"; else bits="${bits}0"; fi; }
case ${HOME:-} in */run-tests.*/home) add 1 ;; *) add 0 ;; esac
case ${TMPDIR:-} in */run-tests.*/tmp) add 1 ;; *) add 0 ;; esac
if [ "${PATH:-}" = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" ]; then add 1; else add 0; fi
# 敏感变量按**键存在性**判断：`VAR=`（空值）也算已传入，不能用 -n 当成未传入。
for name in SELFTEST_LIMIT SELFTEST_UNIT_FAIL RT_CHECK_RULES_FULL_LOG RT_CHECK_RULES_FULL_RC \
            PYTHONPATH FORGE_SYNTH_SECRET FORGE_SYNTH_TOKEN; do
    eval "if [ \"\${$name+set}\" = set ]; then add 0; else add 1; fi"
done
echo "probe:iso=$bits"
[ "$bits" = 1111111111 ]
'''

if not LIMIT:   # 截断跑（SELFTEST_LIMIT）只验证失败传播成本，跳过本组分钟级以外的辅助专项
    _fix=Path(tempfile.mkdtemp(prefix='runner-env.'))
    try:
        for d in ('tests','tools','caller-home','caller-tmp','poison'):(_fix/d).mkdir()
        (_fix/'tests/probe.sh').write_text(_PROBE)
        (_fix/'tests/decoy.sh').write_text('#!/bin/sh\necho "decoy:ran"\n')
        (_fix/'tools/check-rules.py').write_text('print("夹具结构守卫：0 问题（stub）")\n')
        shutil.copyfile(ROOT/'tests/test_paths.py',_fix/'tests/test_paths.py')
        (_fix/'poison/fnmatch.py').write_text('import sys\nsys.stderr.write("poison:fnmatch\\n")\nraise SystemExit(3)\n')
        (_fix/'poison/json.py').write_text('import sys\nsys.stderr.write("poison:json\\n")\nraise SystemExit(3)\n')
        (_fix/'forged.log').write_text('PASS  伪造结果 伪造标记\n')
        _real=(ROOT/'tests/run-tests.sh').read_text(encoding='utf-8')
        _s=_real.index("CASES='\n"); _e=_real.index("\n'\n",_s)+3
        _rows=('probe.sh|gate|sh tests/probe.sh|0|1','decoy.sh|decoy|sh tests/decoy.sh|0|0')
        _rob=_real[:_s]+"CASES='\n"+''.join(r+'\n' for r in _rows)+"'\n"+_real[_e:]
        _blk="CASES='\n"+''.join(r+'\n' for r in _rows)+"'\n"
        assert _rob.count(_blk)==1 and 'probe.sh|gate' in _blk, '夹具 CASES 替换空转'
        _run=_fix/'tests/run-tests.sh'; _run.write_text(_rob)
        # 敌意调用方环境：控制变量／伪造复用日志／PYTHONPATH 影子标准库／合成秘密（其一为**空值**）
        _hostile={'PATH':'/nonexistent:'+os.environ.get('PATH','/usr/bin:/bin'),
                  'HOME':str(_fix/'caller-home'),'TMPDIR':str(_fix/'caller-tmp'),
                  'PYTHONPATH':str(_fix/'poison'),
                  'SELFTEST_LIMIT':'2','SELFTEST_UNIT_FAIL':'1',
                  'RT_CHECK_RULES_FULL_LOG':str(_fix/'forged.log'),'RT_CHECK_RULES_FULL_RC':'0',
                  'FORGE_SYNTH_SECRET':'合成-秘密-值','FORGE_SYNTH_TOKEN':''}
        def runrt(*a,stdin=None,env=None):
            base=dict(_hostile); base.update(env or {})
            return subprocess.run(['sh','tests/run-tests.sh',*a],cwd=str(_fix),env=base,
                                  input=stdin,capture_output=True,text=True,timeout=120)
        def iso(label,r,probe=True,ran=None):
            out=r.stdout+r.stderr
            rchk(label+'：退出码 0',r.returncode==0,'rc=%d'%r.returncode)
            if probe:
                rchk(label+'：探针确实执行','probe:iso=' in out,out[-300:])
                rchk(label+'：10 位隔离全部成立','probe:iso=1111111111' in out,out[-300:])
            else:
                rchk(label+'：探针未被选路（smoke 守卫）','probe:iso=' not in out,out[-300:])
                rchk(label+'：结构守卫入口执行','夹具结构守卫' in out,out[-300:])
            rchk(label+'：对照项未执行（选路非全跑）','decoy:ran' not in out,out[-300:])
            if ran:rchk(label+'：选中＝实跑（'+ran+'）',ran in out,out[-300:])
        iso('case 模式',runrt('case','probe.sh'),ran='选中 1 · 实跑 1')
        iso('group 模式',runrt('group','gate'),ran='选中 1 · 实跑 1')
        r=runrt('select',stdin='[["group","gate"]]')       # stdin 选集：兼容性一并覆盖
        iso('select（stdin）模式',r,ran='选中 1 · 实跑 1')
        rchk('select（stdin）模式：账本成员齐备','成员 1 · 实跑 1' in r.stdout,r.stdout[-400:])
        (_fix/'sel-full.json').write_text('[["full"]]')
        iso('select(full) 接缝',runrt('select',str(_fix/'sel-full.json')),ran='选中 2 · 实跑 2')
        iso('full 接缝（与 select 同一选路）',runrt('full'),ran='选中 2 · 实跑 2')
        iso('smoke 接缝',runrt('smoke'),probe=False,ran='选中 1 · 实跑 1')
        # 只读入口（select-paths／render-paths）也必须走白名单环境：影子 fnmatch 不得被导入。
        r=runrt('select-paths',stdin='tests/run-tests.sh\0tools/check-rules.py\0')
        # full 不再吞掉定向组：full＋同批命中的 gate 一并返回（否则改运行器即漏跑对应套件）
        rchk('select-paths：白名单环境＋输出不变',
             r.returncode==0 and r.stdout.strip()=='[["full"], ["group", "gate"]]','rc=%d out=%r'%(r.returncode,r.stdout))
        rchk('select-paths：影子 fnmatch 未生效','poison:fnmatch' not in r.stdout+r.stderr,r.stderr[-200:])
        r=runrt('render-paths')
        rchk('render-paths：白名单环境＋输出不变',
             r.returncode==0 and '→ full' in r.stdout,'rc=%d'%r.returncode)
        # F2 兼容性回归：只读出口**不得**依赖调用方临时目录可用。修前实跑复现：只读分支在
        #   `mktemp -d "${TMPDIR:-/tmp}/rt-ro.XXXXXXXX"` 建一次性沙箱，调用方 TMPDIR 不存在
        #   （如 TMPDIR=/nonexistent）或指向**不能当目录**的对象时 mktemp 失败 → `exit 1`，
        #   而同一调用在加入沙箱前是成功的只读选路。判据：两个只读出口 × 三种合成 TMPDIR
        #   （不存在／普通文件／与 HOME 同一不存在路径）都 rc=0，且 stdout 与 stderr 与
        #   基线（同一夹具根、默认合成环境）**文本一致**（`text=True`：子进程输出按解码文本比较，
        #   不做字节比较，故不声称逐字节）；合成秘密仍不出现（隔离未被削弱）。
        _tmp_absent=str(_fix/'caller-tmp-absent')
        _tmp_file=str(_fix/'caller-tmp-is-file'); Path(_tmp_file).write_bytes(b'x')
        _base={'select-paths':runrt('select-paths',stdin='tests/run-tests.sh\0tools/check-rules.py\0'),
               'render-paths':runrt('render-paths')}
        for _label,_over in (('TMPDIR 不存在',{'TMPDIR':_tmp_absent}),
                             ('TMPDIR 为普通文件（不可作目录）',{'TMPDIR':_tmp_file}),
                             ('HOME／TMPDIR 均不存在',{'HOME':_tmp_absent,'TMPDIR':_tmp_absent})):
            for _m,_stdin in (('select-paths','tests/run-tests.sh\0tools/check-rules.py\0'),
                              ('render-paths',None)):
                _b=_base[_m]
                _r=runrt(_m,stdin=_stdin,env=_over)
                _d='rc=%d／基线 %d；out=%r／%r'%(_r.returncode,_b.returncode,_r.stdout,_b.stdout)
                rchk(_label+'：'+_m+' 仍 rc=0',_r.returncode==0 and _b.returncode==0,_d)
                rchk(_label+'：'+_m+' 输出与基线文本一致',
                     _r.stdout==_b.stdout and _r.stderr==_b.stderr,_d)
                rchk(_label+'：'+_m+' 合成秘密未外流',
                     '合成-秘密-值' not in _r.stdout+_r.stderr,(_r.stdout+_r.stderr)[-200:])
        # 负控（非空转）：同一夹具根、同一入口，**唯一变异**＝删掉白名单的 `-i`。
        _bad=_rob.replace('env -i ','env ')
        _fn=_rob[_rob.index('rt_env() {'):]; _fn=_fn[:_fn.index('\n}')]
        _nfn=_bad[_bad.index('rt_env() {'):]; _nfn=_nfn[:_nfn.index('\n}')]
        rchk('负控变异可达（rt_env 内已无 -i 隔离）','env -i' in _fn and 'env -i' not in _nfn,_nfn)
        _run.write_text(_bad)
        out=''
        r=runrt('case','probe.sh'); out=r.stdout+r.stderr
        rchk('负控：探针确实启动（不是找不到脚本）','probe:iso=' in out,out[-300:])
        rchk('负控：因合成变量被继承而红，rc＝探针自身 1',r.returncode==1,'rc=%d'%r.returncode)
        rchk('负控：位串＝HOME/TMPDIR/PATH 成立、7 个敏感变量全部被继承（空值也计入）',
             'probe:iso=1110000000' in out,out[-300:])
        rchk('负控：运行器判该入口 FAIL 且非 127／未找到',
             bool(re.search(r'^probe\.sh\s+FAIL\b',out,re.M)) and 'not found' not in out,out[-400:])
        r=runrt('select-paths',stdin='tests/run-tests.sh\0')
        rchk('负控：只读入口不再隔离（影子 fnmatch 被导入 → rc=3）',
             r.returncode==3 and 'poison:fnmatch' in r.stdout+r.stderr,'rc=%d'%r.returncode)
        r=runrt('select',stdin='[["group","gate"]]')
        rchk('负控：selector 解析不再隔离（影子 json 被导入 → 拒绝选路 rc=2）',
             r.returncode==2 and 'poison:json' in r.stdout+r.stderr,'rc=%d'%r.returncode)
        # 正控回绿：撤销变异后同一入口恢复（证明负控红来自隔离缺失，而非夹具损坏）
        _run.write_text(_rob)
        iso('撤销变异后回绿：case 模式',runrt('case','probe.sh'),ran='选中 1 · 实跑 1')
        r=runrt('select-paths',stdin='tests/run-tests.sh\0')
        rchk('撤销变异后回绿：select-paths',
             r.returncode==0 and r.stdout.strip()=='[["full"]]','rc=%d'%r.returncode)
    finally:
        shutil.rmtree(_fix,ignore_errors=True)

if os.environ.get('SELFTEST_UNIT_FAIL')=='1':
    print('FAIL  驱动自检（故意失败，用于验证失败传播）');FAIL+=1
if LIMIT:print('SELFTEST_LIMIT='+str(LIMIT))
_fixture_tmp.cleanup()
print('---- R-1 反例回归：PASS %d / FAIL %d ----'%(PASS,FAIL))
raise SystemExit(1 if FAIL else 0)
PYEOF

#!/usr/bin/env python3
"""B+ 结构守卫：加载/资源边、单份身份、references 路径、义务块存在性。
不检查正文逐字片段、固定期望、命名或历史路径；rc=0 不等于规则无弱化。
只读当前树，不访问生效端。rc=1 确定错误，2 提示，3 检查不完整。
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / 'tools/rule-claims.tsv'
REGISTRY = ROOT / 'tools/sync-targets.json'
LOAD_RE = re.compile(r'(先加载|先完整加载|另加载|必须加载|必须完整加载|一律加载|按需加载|条件加载)\s*`?(luno-[a-z0-9-]+)`?')
REQUIRED_VERBS = {'先加载','先完整加载','必须加载','必须完整加载','一律加载'}
RESOURCE_RE = re.compile(r'`(references/[A-Za-z0-9_./-]+)`')
FORMS = {'必需加载','条件加载','资源必需','资源条件'}
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
# 只会由部署取件装入的官方参考原件：仓库路径 → manifest `raw_sha256` 的包内路径。
# 与 `luno-surge/references/SOURCE.md`〈取件与部署〉第 3 步的映射同源；agents/openai.yaml
# 是本地有意改写的自有文件，不在此列。
OFFICIAL_OBJECT = 'luno-surge'
OFFICIAL_ORIGINALS = {
    'skills/luno-surge/references/upstream-SKILL.md': 'SKILL.md',
    'skills/luno-surge/references/upstream-command-reference.md': 'references/command-reference.md',
    'skills/luno-surge/references/plugin-authoring.md': 'references/plugin-authoring.md',
}
OFFICIAL_REPO_PATHS = set(OFFICIAL_ORIGINALS)
INVENTORY_MANIFEST = 'skills/luno-surge/references/upstream-manifest.json'
# __OBLIGATIONS__
OBLIGATIONS = (('skills/luno-lobehub/SKILL.md', '## 范围'), ('skills/luno-review/SKILL.md', '## 审查'), ('skills/luno-ops/SKILL.md', '## 专项执行'), ('skills/luno-writing/SKILL.md', '## 分支'), ('skills/luno-minis/SKILL.md', '## 资源与触发'), ('skills/luno-minis/references/runtime.md', '## 上下文行为'), ('skills/luno-ops/SKILL.md', '## 资源与触发'), ('skills/luno-sync/SKILL.md', '## 资源与触发'), ('skills/luno-core/SKILL.md', '## 执行闭环'), ('skills/luno-core/SKILL.md', '## 路由'), ('skills/luno-core/SKILL.md', '## 子代理角色与派发'), ('skills/luno-memory/SKILL.md', '## 资源与触发'))

class Guard:
    def __init__(self, root):
        self.root = root.resolve()
        self.hard = []; self.incomplete = []; self.soft = []
        self._official = None
        self._official_ok = False
        self._declared = False
    def official(self):
        """部署取件后才进本端的官方参考原件 → 可豁免的仓库路径集合。

        豁免只对 `luno-surge` 对象有效，路径只能是该技能包内的路径，且每条必须能映射到
        `references/upstream-manifest.json` 的 `raw_sha256`（3 份参考原件：`SKILL.md`、
        `references/command-reference.md`、`references/plugin-authoring.md`）。登记形态不合
        （类型错、非 luno-surge 对象带该块、路径非包内、无法映射、缺项）一律判硬错误停止检查，
        不静默降级；仓库内允许缺文件，缺失不判断链，也不证明已装入。
        """
        if self._official is None:
            self._official = set()
            try:
                doc = json.loads((self.root / 'tools/sync-targets.json').read_text(encoding='utf-8'))
            except (OSError, ValueError, TypeError):
                doc = None
                # 登记表本身不可读已由 identities() 判「未核」；这里不重复升级为硬错误，
                # 只让缺件保持「未核」口径（rc=3），不冒充通过。
            try:
                manifest = json.loads((self.root / INVENTORY_MANIFEST).read_text(encoding='utf-8'))
                raw = manifest.get('raw_sha256') if isinstance(manifest, dict) else None
            except (OSError, ValueError, TypeError):
                raw = None
                self.problem('官方原件 manifest 不可读')
            if not isinstance(raw, dict) or set(OFFICIAL_ORIGINALS.values()) - set(raw):
                self.problem('官方原件 manifest 缺参考原件哈希')
                raw = raw if isinstance(raw, dict) else {}
            for key in OFFICIAL_ORIGINALS.values():
                if not HEX64.match(str(raw.get(key, ''))):
                    self.problem('官方原件 manifest 哈希形态')
            objects = doc.get('objects') if isinstance(doc, dict) else None
            if doc is not None and not isinstance(objects, list):
                self.problem('官方原件登记结构')
                objects = []
            objects = objects if isinstance(objects, list) else []
            declared = set()
            for o in objects:
                if not isinstance(o, dict) or 'officialPackageResources' not in o:
                    continue
                self._declared = True
                blk = o['officialPackageResources']
                if not isinstance(blk, dict) or not isinstance(blk.get('paths'), list):
                    self.problem('官方原件登记形态'); continue
                if o.get('id') != OFFICIAL_OBJECT and blk['paths']:
                    self.problem('官方原件豁免对象非法'); continue
                for q in blk['paths']:
                    if not isinstance(q, str) or q not in OFFICIAL_REPO_PATHS:
                        self.problem('官方原件豁免路径非法'); continue
                    if q in declared:
                        self.problem('官方原件豁免路径重复'); continue
                    declared.add(q)
            if self._declared and OFFICIAL_REPO_PATHS - declared:
                self.problem('官方原件豁免登记缺项')
            self._official = declared
            # 没有该声明时，缺文件只能判「未核」（rc=3），不冒充硬错误
            self._official_ok = self._declared and not self.hard
        return self._official
    def official_ok(self):
        """登记是否可读：不可读时不把「不在这份名单上」当硬错误，只报未核（rc=3 口径）。"""
        self.official()
        return self._official_ok
    def problem(self, kind, *, incomplete=False):
        (self.incomplete if incomplete else self.hard).append(kind)
    def read(self, rel):
        p = self.path(rel)
        if p is None: return None
        try: return p.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            self.problem('读取失败', incomplete=True); return None
    def path(self, rel):
        if not isinstance(rel,str) or not rel or '\\' in rel:
            self.problem('路径形态非法'); return None
        p = Path(rel)
        if p.is_absolute() or any(x in ('','.','..') for x in rel.split('/')):
            self.problem('资源引用逃逸'); return None
        q = self.root / p
        try:
            q.resolve().relative_to(self.root)
            # Any symlink in the source path invalidates the trusted local identity.
            cur = self.root
            for part in p.parts:
                cur = cur / part
                if cur.is_symlink():
                    self.problem('资源引用逃逸'); return None
        except (OSError,ValueError):
            self.problem('资源引用逃逸'); return None
        return q
    def sources(self):
        out = {}
        for top in ('skills','prompt','subagents'):
            base = self.root / top
            def err(exc): self.problem('遍历失败',incomplete=True)
            if not base.is_dir():
                self.problem('扫描范围缺失',incomplete=True); continue
            for dp, dirs, files in os.walk(base,followlinks=False,onerror=err):
                for d in list(dirs):
                    if (Path(dp)/d).is_symlink():
                        self.problem('资源引用逃逸'); dirs.remove(d)
                for fn in files:
                    if Path(fn).suffix not in ('.md','.py','.sh'): continue
                    rel=(Path(dp)/fn).relative_to(self.root).as_posix()
                    text=self.read(rel)
                    if text is not None: out[rel]=strip_frontmatter(text)
        if not out: self.problem('扫描范围为空',incomplete=True)
        return out
    def claims(self, bodies):
        raw=self.read('tools/rule-claims.tsv')
        if raw is None: return set()
        rows=set()
        for line in raw.splitlines():
            if not line.strip() or line.startswith('#'): continue
            f=line.split('\t')
            if len(f)!=4 or not all(x.strip() for x in f):
                self.problem('条款登记字段',incomplete=True); continue
            src,target,form,label=f
            if form not in FORMS:
                self.problem('加载形态',incomplete=True);continue
            key=(src,target,form)
            if key in rows: self.problem('重复登记');continue
            rows.add(key)
            if src not in bodies:
                self.problem('加载边来源缺失',incomplete=True);continue
            if form.startswith('资源'):
                if not target.startswith('references/'):
                    self.problem('资源加载边形态');continue
                if not own_skill(src):
                    self.problem('资源加载边来源');continue
                if target not in RESOURCE_RE.findall(bodies[src]):
                    self.soft.append('条款真源漂移')
                path=self.path(skill_root(src)+'/'+target)
                if path is not None and not path.is_file():
                    if not self.official_ok(): self.problem('资源引用断链未核', incomplete=True)
                    elif (skill_root(src)+'/'+target) not in self.official(): self.problem('资源引用断链')
            else:
                hits=[m for m in LOAD_RE.finditer(bodies[src]) if m[2]==target]
                if not hits: self.problem('加载边未出现', incomplete=True)
                if hits and not any((m[1] in REQUIRED_VERBS)==(form=='必需加载') for m in hits):
                    self.problem('加载形态')
                if not (self.root/'skills'/target/'SKILL.md').is_file():
                    self.problem('加载目标缺失')
        if not rows: self.problem('条款登记为空',incomplete=True)
        load_count = resource_count = 0
        for src,body in bodies.items():
            for m in LOAD_RE.finditer(body):
                load_count += 1
                form='必需加载' if m[1] in REQUIRED_VERBS else '条件加载'
                if (src,m[2],form) not in rows:
                    self.problem('加载登记',incomplete=True)
            if own_skill(src):
                for target in RESOURCE_RE.findall(body):
                    resource_count += 1
                    path=self.path(skill_root(src)+'/'+target)
                    if path is not None and not path.is_file():
                        if not self.official_ok(): self.problem('资源引用断链未核', incomplete=True)
                        elif (skill_root(src)+'/'+target) not in self.official(): self.problem('资源引用断链')
                    if not any((src,target,f) in rows for f in ('资源必需','资源条件')):
                        self.problem('资源加载边',incomplete=True)
        if not load_count: self.problem("0 条加载语句被核对", incomplete=True)
        if not resource_count: self.problem("0 条资源路径被核对", incomplete=True)
        return rows
    def identities(self):
        raw=self.read('tools/sync-targets.json')
        try: doc=json.loads(raw) if raw is not None else None
        except (ValueError,TypeError): doc=None
        if not isinstance(doc,dict) or not isinstance(doc.get('objects'),list) or not doc['objects']:
            self.problem('身份登记不可用',incomplete=True);return
        seen=set(); owners={}; sources=set()
        for o in doc['objects']:
            if not isinstance(o,dict): self.problem('身份登记结构');continue
            name=o.get('id');src=o.get('source');kind=o.get('type');ends=o.get('ends')
            if not isinstance(name,str) or not name or name in seen:
                self.problem('身份重复或缺失');continue
            seen.add(name)
            if kind not in ('skill','prompt','subagent') or not isinstance(ends,dict):
                self.problem('身份登记结构');continue
            text=self.read(src)
            if text is None: self.problem('身份源缺失');continue
            if src in sources: self.problem('身份源重复')
            sources.add(src)
            if kind=='skill':
                fm=text.split('---',2)
                m=re.search(r'^name:\s*[\'\"]?([a-z0-9-]+)[\'\"]?\s*$',fm[1],re.M) if len(fm)==3 and fm[0]=='' else None
                if m is None or m[1]!=name or Path(src).parent.name!=name:
                    self.problem('身份与技能源不一致')
            for end in ('repo','minis','lobehub'):
                v=ends.get(end)
                if not isinstance(v,dict) or not isinstance(v.get('present'),bool):
                    self.problem('身份端结构');continue
                if not v['present']:
                    if end=='repo':self.problem('仓库身份缺位')
                    if v.get('id') is not None: self.problem('缺位身份冲突')
                    continue
                if end=='repo' and v['present'] is not True:
                    self.problem('仓库身份缺位')
                if end=='minis':
                    if kind=='skill':
                        if v.get('kind')!='file' or v.get('path')!='/var/minis/skills/'+name+'/SKILL.md':
                            self.problem('Minis 身份路径冲突')
                    elif v.get('kind')!='field' or not isinstance(v.get('field'),str) or not v['field']:
                        self.problem('Minis 身份字段缺失')
                    if kind=='prompt' and (v.get('field')!='soul.body' or v.get('alsoFile')!='/var/minis/memory/SOUL.md'):
                        self.problem('prompt 生效字段或文件冲突')
                    if kind=='subagent' and (not isinstance(v.get('field'),str) or not re.fullmatch(r'subagents\.(?:general|[A-Fa-f0-9-]{36})\.instructions',v['field'])):
                        self.problem('子代理字段形态')
                    endpoint=v.get('path') if kind=='skill' else v.get('field')
                    if isinstance(endpoint,str) and endpoint:
                        key=(end,endpoint)
                        if key in owners and owners[key]!=name: self.problem('Minis 身份多占')
                        owners[key]=name
                if end=='lobehub':
                    if v.get('kind')!=('skill' if kind=='skill' else 'agent'):
                        self.problem('平台身份种类冲突')
                    if kind=='skill':
                        if not isinstance(v.get('fields'),str) or set(v['fields'].split(','))!={'content','name','description'}:
                            self.problem('技能字段形态')
                    elif v.get('field')!='systemRole':self.problem('Agent 字段形态')
                    sid=v.get('id');prefix='skl_' if kind=='skill' else 'agt_'
                    if not isinstance(sid,str) or not re.fullmatch(prefix+r'[A-Za-z0-9]+',sid):
                        self.problem('平台身份形态');continue
                    key=(end,sid)
                    if key in owners and owners[key]!=name: self.problem('平台身份多占')
                    owners[key]=name
        # One source of truth: no second table or hardcoded expected IDs.
    def obligations(self,bodies):
        for src,heading in OBLIGATIONS:
            body=bodies.get(src)
            if body is None:
                self.problem('义务块来源缺失',incomplete=True);continue
            lines=body.splitlines(); hits=[i for i,x in enumerate(lines) if x==heading]
            if len(hits)!=1:
                self.problem('义务块缺失或重复');continue
            i=hits[0]+1;j=i
            while j<len(lines) and not lines[j].startswith('#'): j+=1
            if not any(x.strip() for x in lines[i:j]): self.problem('义务块为空')
    def run(self):
        bodies=self.sources();self.claims(bodies);self.identities();self.obligations(bodies)
        for k in self.hard: print('[结构错误] '+k)
        for k in self.incomplete: print('[检查不完整] '+k)
        for k in self.soft: print('[提示] '+k)
        rc=1 if self.hard else 3 if self.incomplete else 2 if self.soft else 0
        print('[R1] '+('无问题（仅结构，不证明正文无弱化）' if rc==0 else '结构检查未通过'))
        return rc

def strip_frontmatter(text):
    lines=text.split('\n')
    if lines and lines[0].rstrip('\r')=='---':
        for i in range(1,len(lines)):
            if lines[i].rstrip('\r')=='---': return '\n'.join(lines[i+1:])
    return text

def own_skill(src): return bool(re.match(r'^skills/luno-[a-z0-9-]+/',src))
def skill_root(src): return '/'.join(src.split('/')[:2])
if __name__=='__main__': sys.exit(Guard(ROOT).run())

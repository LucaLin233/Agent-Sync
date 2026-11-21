#!/usr/bin/env python3
"""结构守卫：加载/资源边、身份、references 路径、分支指针、义务块及中立规则的平台词边界。
只读当前树，不访问生效端，不判定正文语义；rc=0 不证明规则无弱化。
退出码：0 无问题，1 结构错误，2 仅提示，3 检查不完整。
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOAD_RE = re.compile(r'(先加载|先完整加载|另加载|必须加载|必须完整加载|一律加载|按需加载|条件加载)\s*`?(luno-[a-z0-9-]+|cchp)(?![a-z0-9/-])`?')
REQUIRED_VERBS = {'先加载','先完整加载','必须加载','必须完整加载','一律加载'}
RESOURCE_RE = re.compile(r'`((?:luno-[a-z0-9-]+/)?references/[A-Za-z0-9_./-]+)`')
CROSS_RESOURCE_RE = re.compile(r'luno-[a-z0-9-]+/references/[A-Za-z0-9_./-]+\Z')
REGISTRY = 'tools/sync-targets.json'
HOST_ENDS = ('codex','paseo')
# 「必须加载」的入口义务：正文只写动词，被改成条件加载时无法自证，故保留原有必需加载行，并登记 CCHP 本端层对官方技能的必需加载。
NATIVE_ROLES = {'subagents/LENS.md': ('lens', 'gpt-6.2-sol', 'high'),
               'subagents/FORGE.md': ('forge', 'deepseek-flash', 'high')}
NATIVE_ROLE_KEYS = {'present', 'kind', 'paths', 'renderer', 'model', 'model_reasoning_effort'}

REQUIRED_LOADS = (('prompt/LUNO.md', 'luno-core'),
                  ('subagents/LENS.md', 'luno-core'),
                  ('subagents/FORGE.md', 'luno-core'),
                  ('subagents/minis-general-fallback.md', 'luno-core'),
                  ('prompt/LUNO.md', 'luno-platform'),
                  ('skills/luno-core/SKILL.md', 'luno-platform'),
                  ('skills/luno-core/SKILL.md', 'references/review.md'),
                  ('skills/luno-core/references/execution.md', 'luno-core'),
                  ('skills/luno-platform/references/cchp.md', 'references/cchp-upstream/ENTRY.md'))
# 运行端必读入口：〈运行端〉的端判定与各端资源之间的合用指针按原句片段核对，漏掉、改为可选或
# 改写判定时报必需加载降级；措辞有意改动时同步更新这里。
REQUIRED_READS = (
    ('skills/luno-platform/SKILL.md', '按当前端完整读取对应资源：'),
    ('skills/luno-platform/SKILL.md', 'Minis 端（App 内置 iSH，存在 `/var/minis`）读 `references/runtime-minis.md`'),
    ('skills/luno-platform/SKILL.md', 'Codex 端（宿主为 Codex CLI）读 `references/runtime-codex.md` 和 `references/runtime-host.md`'),
    ('skills/luno-platform/SKILL.md', '在 Codex 端且可用 paseo 编排工具或存在指定变量 `PASEO_AGENT_ID` 时，'
                                      '另读 `references/runtime-paseo.md`'),
    ('skills/luno-platform/references/runtime-codex.md',
     '与 `references/runtime-host.md` 合用；会话由 paseo 启动时另叠加 `references/runtime-paseo.md`'),
    ('skills/luno-platform/references/runtime-host.md',
     '并与 `references/runtime-codex.md` 合用'),
    ('skills/luno-platform/references/runtime-paseo.md',
     '其余槽位仍按 `references/runtime-codex.md` 与 `references/runtime-host.md`'))
# 合并资源的分支指针：`references/x.md`〔分支 y〕或 [文字](x.md#branch-y)；目标须有锚点及 BEGIN/END 定界。
BRANCH_PTR_RE = re.compile(r'`?((?:luno-[a-z0-9-]+/)?references/[A-Za-z0-9_./-]+\.md)`?〔分支 ([A-Za-z0-9_-]+)〕')
BRANCH_LINK_RE = re.compile(r'\]\(([A-Za-z0-9_.-]+\.md)#branch-([A-Za-z0-9_-]+)\)')
# Whole official files are not runtime resources; plugin-authoring.md is now self-authored.
RETIRED_RESOURCES = ('skills/luno-surge/references/upstream-SKILL.md',
                     'skills/luno-surge/references/upstream-command-reference.md',
                     'skills/luno-surge/assets/logo.png')
PLATFORM_WORD_RE = re.compile(r'(?<![A-Za-z])(?:Minis|iSH|LobeHub|OnlyBoxes)(?![A-Za-z])'
                              r'|/var/minis|minis://|subagent_task|max_minutes')
PLATFORM_WORD_ALLOWED = (
    'skills/luno-core/references/sync.md',
    'skills/luno-ops/references/execution-environment.md',
    'skills/luno-ops/references/cfst.md',
    'skills/luno-surge/references/command-reference.md',
    'skills/luno-surge/references/SOURCE.md',
    'skills/luno-surge/references/official-sources.md',
)
# __OBLIGATIONS__
OBLIGATIONS = (('skills/luno-platform/references/cchp.md', '## 管理入口'), ('skills/luno-platform/SKILL.md', '## Minis执行能力'), ('skills/luno-core/references/review.md', '## 审查'), ('skills/luno-authoring/SKILL.md', '## 分支'), ('skills/luno-platform/references/minis.md', '## 资源与触发'), ('skills/luno-platform/references/minis.md', '## 上下文行为'), ('skills/luno-ops/SKILL.md', '## 资源与触发'), ('skills/luno-core/references/sync.md', '## 资源与触发'), ('skills/luno-core/SKILL.md', '## 执行闭环'), ('skills/luno-core/references/execution.md', '## 执行闭环'), ('skills/luno-core/references/execution.md', '## 授权与安全'), ('skills/luno-core/SKILL.md', '## 路由'), ('skills/luno-core/SKILL.md', '## 子代理角色与派发'), ('skills/luno-core/references/review.md', '## 任务归属'), ('skills/luno-platform/references/memory-common.md', '## 资源与触发'))

class Guard:
    def __init__(self, root):
        self.root = root.resolve()
        self.hard = []; self.incomplete = []; self.soft = []

    def distribution(self):
        """No source-fetch exceptions remain; normal resources must be present."""
        try:
            doc = json.loads((self.root / 'tools/sync-targets.json').read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            return  # identities() reports an unreadable registry as incomplete.
        for obj in doc.get('objects', []) if isinstance(doc, dict) and isinstance(doc.get('objects'), list) else []:
            if isinstance(obj, dict) and 'officialPackageResources' in obj:
                self.problem('官方取件登记已退休')
        for rel in RETIRED_RESOURCES:
            path = self.path(rel)
            if path is not None and path.exists():
                self.problem('禁止分发完整官方资源')

    def problem(self, kind, *, incomplete=False):
        (self.incomplete if incomplete else self.hard).append(kind)

    def read(self, rel):
        p = self.path(rel)
        if p is None: return None
        try: return p.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            self.problem('读取失败', incomplete=True); return None

    def path(self, rel):
        """仓库内相对路径 → Path；绝对路径、`..`、反斜杠或途经 symlink 一律拒绝。"""
        if not isinstance(rel,str) or not rel or '\\' in rel:
            self.problem('路径形态非法'); return None
        p = Path(rel)
        if p.is_absolute() or any(x in ('','.','..') for x in rel.split('/')):
            self.problem('资源引用逃逸'); return None
        q = self.root / p
        try:
            q.resolve().relative_to(self.root)
            cur = self.root
            for part in p.parts:
                cur = cur / part
                if cur.is_symlink():
                    self.problem('资源引用逃逸'); return None
        except (OSError,ValueError):
            self.problem('资源引用逃逸'); return None
        return q

    def resource(self, src, target):
        """技能内必需资源均须在仓库内存在，不再豁免官方缺件。"""
        rel = 'skills/'+target if CROSS_RESOURCE_RE.fullmatch(target) else skill_root(src)+'/'+target
        path = self.path(rel)
        if path is not None and not path.is_file():
            self.problem('资源引用断链')

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
                    if text is not None:
                        self.platform_words(rel,text)
                        out[rel]=strip_frontmatter(text)
        if not out: self.problem('扫描范围为空',incomplete=True)
        return out

    def platform_words(self, rel, text):
        """只查技能 Markdown（含 frontmatter）；脚本中的平台协议和提示不属于规则正文。"""
        if (not rel.startswith('skills/') or not rel.endswith('.md')
                or rel.startswith('skills/luno-platform/') or rel in PLATFORM_WORD_ALLOWED):
            return
        for line, content in enumerate(text.splitlines(),1):
            for match in PLATFORM_WORD_RE.finditer(content):
                self.problem('平台词超出适配层：%s:%d: %s' % (rel,line,match[0]))

    def resources(self):
        """技能包资源清单的唯一真源：登记即部署与分发面，故从登记现读。"""
        raw=self.read(REGISTRY)
        try: doc=json.loads(raw) if raw is not None else None
        except (ValueError,TypeError): doc=None
        out={}
        if isinstance(doc,dict) and isinstance(doc.get('objects'),list):
            for o in doc['objects']:
                if not isinstance(o,dict) or o.get('type')!='skill': continue
                src=o.get('source');res=o.get('resources')
                if not isinstance(src,str) or not isinstance(res,list):
                    self.problem('包资源登记结构'); continue
                pkg=Path(src).parent
                if any(not isinstance(r,str) or not r.startswith(pkg.as_posix()+'/') for r in res):
                    self.problem('包资源不属于本包')
                out[pkg.name]={r for r in res if isinstance(r,str)}
        if not out: self.problem('资源登记不可用',incomplete=True); return None
        for entry in (self.root/'skills').glob('*/SKILL.md'):
            if entry.parent.name not in out: self.problem('技能源未登记')
        return out

    def edges(self, bodies, reg):
        """加载边、资源边与包内文件全部从正文和资源登记现读，不再有独立边登记表。"""
        load_count = resource_count = 0
        path_required_missing = 0
        for src,body in bodies.items():
            for m in LOAD_RE.finditer(body):
                load_count += 1
                if not (self.root/'skills'/m[2]/'SKILL.md').is_file():
                    self.problem('加载目标缺失')
            for target in RESOURCE_RE.findall(body):
                cross = bool(CROSS_RESOURCE_RE.fullmatch(target))
                if not own_skill(src) and not cross: continue
                resource_count += 1
                rel = 'skills/'+target if cross else skill_root(src)+'/'+target
                self.resource(src,target)
                if reg is not None and rel not in reg.get(rel.split('/')[1], ()):
                    self.problem('资源未登记')
            for target,skill in REQUIRED_LOADS:
                if target!=src: continue
                if '/' in skill:
                    # 路径形态的必需读取本身就依赖资源路径：一条资源路径都没核到时它必然缺失，
                    # 与「0 条资源路径被核对」同源，归入不完整而不是结构错误。
                    if not re.search(r'(?:先完整读取|必须完整读取)\s*`'+re.escape(skill)+r'`', body):
                        path_required_missing += 1
                elif not any(m[2]==skill and m[1] in REQUIRED_VERBS for m in LOAD_RE.finditer(body)):
                    self.problem('必需加载降级')
        # 必读片段都带资源路径，缺失与路径形态的必需读取同样计入，资源路径为空时归入不完整。
        path_required_missing += sum(fragment not in bodies.get(src,'') for src,fragment in REQUIRED_READS)
        if not load_count: self.problem("0 条加载语句被核对", incomplete=True)
        if not resource_count: self.problem("0 条资源路径被核对", incomplete=True)
        else:
            for _ in range(path_required_missing): self.problem('必需加载降级')
        for name,res in (reg or {}).items():
            pkg=self.root/'skills'/name
            for dp,dirs,files in os.walk(pkg,followlinks=False):
                for fn in files:
                    rel=(Path(dp)/fn).relative_to(self.root).as_posix()
                    if rel!='skills/'+name+'/SKILL.md' and rel not in res:
                        self.problem('包内文件未登记')
            for r in sorted(res):
                p=self.path(r)
                if p is not None and not p.is_file(): self.problem('登记的包资源缺失')

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
            for end in ('repo','minis')+HOST_ENDS:
                v=ends.get(end)
                if not isinstance(v,dict) or not isinstance(v.get('present'),bool):
                    self.problem('身份端结构');continue
                if not v['present']:
                    if end=='repo':self.problem('仓库身份缺位')
                    if v.get('id') is not None: self.problem('缺位身份冲突')
                    continue
                if end in HOST_ENDS:
                    self.host_identity(end,kind,name,v,owners)
                    continue
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
    def host_identity(self, end, kind, name, value, owners):
        """宿主端使用完整文件的软链或生成文件；不复用平台字段型身份。"""
        renderer = None
        if kind=='skill':
            want='link'
        elif kind=='prompt' and end=='codex':
            want='generated';renderer='codex-main'
        elif name in NATIVE_ROLES and end=='codex':
            # 原生 Codex 角色：两角色、此 renderer、精确路径与模型参数，其余键名一律冲突。
            role, model, effort = NATIVE_ROLES[name]
            want='generated';renderer='codex-role'
            if (set(value)!=NATIVE_ROLE_KEYS or value.get('paths')!=['~/.codex/roles/'+role+'.toml']
                    or value.get('model')!=model or value.get('model_reasoning_effort')!=effort):
                self.problem('宿主端原生角色登记冲突');return
        elif name in ('subagents/LENS.md','subagents/FORGE.md') and end=='paseo':
            want='link'
        else:
            self.problem('宿主端对象不支持');return
        if value.get('kind')!=want or (renderer is not None and value.get('renderer')!=renderer):
            self.problem('宿主端身份种类冲突')
        paths=value.get('paths')
        if (not isinstance(paths,list) or not paths or any(not isinstance(p,str)
                or not p.startswith('~/') or '\\' in p
                or any(c in ('','.','..') for c in p[2:].split('/')) for p in paths)):
            self.problem('宿主端路径形态');return
        for path in paths:
            key=('host',path)
            if key in owners and owners[key]!=name:self.problem('宿主端身份多占')
            owners[key]=name

    def branches(self,bodies):
        for src,body in bodies.items():
            targets=[('skills/'+f if CROSS_RESOURCE_RE.fullmatch(f) else skill_root(src)+'/'+f,b)
                     for f,b in BRANCH_PTR_RE.findall(body)]
            targets+=[(str(Path(src).parent/f),b) for f,b in BRANCH_LINK_RE.findall(body)]
            for rel,name in targets:
                text=bodies.get(rel,'')
                span='<!-- BEGIN %s -->'%name, '<!-- END %s -->'%name
                # 分支须有锚点，且 BEGIN/END 各出现一次并成对（BEGIN 在 END 之前）。
                if ('<a id="branch-%s"></a>'%name not in text or text.count(span[0])!=1
                        or text.count(span[1])!=1 or text.find(span[0])>text.find(span[1])):
                    self.problem('分支指针失效')

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
        self.distribution()
        bodies=self.sources();reg=self.resources();self.edges(bodies,reg)
        self.identities();self.branches(bodies);self.obligations(bodies)
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

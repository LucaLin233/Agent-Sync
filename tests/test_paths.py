#!/usr/bin/env python3
"""变更路径 → 必跑套件的唯一选路表（run-tests.sh select-paths / render-paths 的后端）。

select-paths：stdin 为 NUL 分隔路径，stdout 为 selector JSON，总含 smoke 或 full；
tests/ 下未登记的路径直接拒绝（rc=2），以免新测试永远选不到。
"""
import fnmatch
import json
import sys

PATHS_RULES = (
    (('tools/check-rules.py', 'tools/rule-claims.tsv', 'tools/sync-targets.json',
      'tests/test-check-rules.sh'),
     ('group', 'gate'), '结构守卫或边登记 → gate'),
    (('tools/deploy_skill.py', 'tools/body_contract.py', 'tools/resource_http.py',
      'tools/pack-skill-zip.py', 'tools/sync-targets.json', 'tests/test-deploy-skill.py',
      'skills/luno-surge/scripts/package_release.py'),
     ('case', 'test-deploy-skill.py'), '部署、正文契约、资源、打包与对象登记 → deploy'),
    (('skills/luno-surge/*', 'tests/test-surge-scripts.py'),
     ('case', 'test-surge-scripts.py'), 'Surge 包或测试 → surge'),
    (('skills/luno-surge/scripts/_privacy.py', 'skills/luno-ops/references/service-runtime.md',
      'skills/luno-platform/references/lobehub-instance.md', 'skills/luno-platform/references/lobehub.md', 'skills/luno-platform/SKILL.md',
      'skills/luno-platform/references/minis-configuration.md',
      'skills/luno-core/references/sync-workflow.md', 'tests/test-redact.py'),
     ('case', 'test-redact.py'), '脱敏实现与读取模板 → privacy'),
    (('tools/pack-skill-zip.py', 'tests/test-pack-skill-zip.py'),
     ('case', 'test-pack-skill-zip.py'), '打包器与专项测试 → pack'),
    (('tools/check-commit-identities.py', 'tools/github-web-flow.gpg',
      'tests/test-commit-identities.py', 'skills/luno-core/references/delegation.md',
      '.github/workflows/commit-identities.yml'),
     ('group', 'identity'), '署名机械检查器、其测试与署名规则 → identity'),
    (('tests/run-tests.sh', 'tests/test_paths.py', 'tools/sync-all.sh'),
     ('full',), '运行器与聚合入口 → full'),
)


def select(paths):
    selected = []
    for path in paths:
        hits = [sel for globs, sel, _ in PATHS_RULES
                if any(fnmatch.fnmatchcase(path, g) for g in globs)]
        if path.startswith('tests/') and not hits:
            raise ValueError(path)
        for sel in hits:
            if list(sel) not in selected:
                selected.append(list(sel))
    if ['full'] in selected:
        return [['full']] + [s for s in selected if s != ['full']]
    return [['smoke']] + selected


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'render'
    if mode == 'render':
        print(''.join('#   ' + prose + '\n' for _, _, prose in PATHS_RULES), end='')
    elif mode == 'select-paths':
        try:
            raw = sys.stdin.buffer.read().decode('utf-8')
            print(json.dumps(select([x for x in raw.split('\0') if x])))
        except (ValueError, UnicodeError):
            print('选路拒绝：输入路径不可用或测试未登记', file=sys.stderr)
            raise SystemExit(2)
    else:
        raise SystemExit(2)

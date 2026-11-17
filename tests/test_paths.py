#!/usr/bin/env python3
"""变更路径 → 必跑套件的唯一选路表（run-tests.sh select-paths / render-paths 的后端）。

select-paths：stdin 为 NUL 分隔路径，stdout 为 selector JSON，总含 smoke 或 full；
tests/ 下未登记的路径直接拒绝（rc=2），以免新测试永远选不到。
"""
import fnmatch
import json
import sys

PATHS_RULES = (
    (('tools/auth-call.py', 'tests/test-auth-call.py'),
     ('case', 'test-auth-call.py'), '固定认证读取 → auth'),
    (('tools/check-rules.py', 'tools/sync-targets.json',
      'tests/test-check-rules.sh'),
     ('group', 'gate'), '结构守卫或边登记 → gate'),
    (('tools/body_contract.py', 'tests/test-body-contract.py'),
     ('case', 'test-body-contract.py'), '正文契约及既有用例 → body'),
    (('skills/luno-surge/*', 'tools/package_release.py', 'tools/sync-targets.json', 'tests/test-surge-package.py'),
     ('case', 'test-surge-package.py'), 'Surge 包内文件、登记或包态测试 → surge 包态'),
    (('skills/luno-surge/scripts/*', 'tools/package_release.py', 'tests/test-surge-scripts.py'),
     ('case', 'test-surge-scripts.py'), 'Surge 脚本或脚本测试 → surge 脚本'),
    (('skills/luno-surge/scripts/_privacy.py', 'skills/luno-ops/references/service-runtime.md',
      'skills/luno-platform/references/lobehub-instance.md', 'skills/luno-platform/references/lobehub.md', 'skills/luno-platform/SKILL.md',
      'skills/luno-platform/references/minis.md',
      'skills/luno-core/references/sync.md', 'tests/test-redact.py'),
     ('case', 'test-redact.py'), '脱敏实现与读取模板 → privacy'),
    (('tools/check-commit-identities.py', 'tools/github-web-flow.gpg',
      'tests/test-commit-identities.py', 'skills/luno-core/references/review.md',
      '.github/workflows/commit-identities.yml'),
     ('group', 'identity'), '署名机械检查器、其测试与署名规则 → identity'),
    # 新消费者：验收工具自身、其依赖的固定认证读取/正文契约与对象登记变化都要跑 verify。
    (('tools/lh-verify.py', 'tests/test-lh-verify.py'),
     ('case', 'test-lh-verify.py'), 'LH 技能离线验收工具或工具测试 → verify'),
    (('tools/auth-call.py', 'tests/test-auth-call.py'),
     ('case', 'test-lh-verify.py'), '固定认证读取变更 → verify 消费者'),
    (('tools/body_contract.py', 'tests/test-body-contract.py'),
     ('case', 'test-lh-verify.py'), '正文契约变更 → verify 消费者'),
    (('tools/sync-targets.json',),
     ('case', 'test-lh-verify.py'), '对象登记变更 → verify 消费者'),
    (('tools/minis-verify.py', 'tests/test-minis-verify.py'),
     ('case', 'test-minis-verify.py'), 'Minis 本端验收工具或工具测试 → minis-verify'),
    (('tools/body_contract.py', 'tests/test-body-contract.py'),
     ('case', 'test-minis-verify.py'), '正文契约变更 → Minis 验收消费者'),
    (('tools/sync-targets.json',),
     ('case', 'test-minis-verify.py'), '对象登记变更 → Minis 验收消费者'),
    # 窄采集/部署接线（首版不默认进常跑）：各自测试 → 各自 case；collect 依赖固定认证读取。
    (('tools/lh-collect.py', 'tests/test-lh-collect.py'),
     ('case', 'test-lh-collect.py'), 'LH 窄采集工具或工具测试 → 采集'),
    (('tools/auth-call.py', 'tests/test-auth-call.py'),
     ('case', 'test-lh-collect.py'), '固定认证读取变更 → 采集消费者'),
    (('tools/lh-collect.py', 'tests/test-lh-collect.py'),
     ('case', 'test-lh-deploy.py'), '窄采集变更 → 部署消费者'),
    (('tools/sync-targets.json',),
     ('case', 'test-lh-collect.py'), '对象登记变更 → 采集消费者'),
    (('tools/lh-deploy.py', 'tests/test-lh-deploy.py'),
     ('case', 'test-lh-deploy.py'), 'LH 窄部署工具或工具测试 → 部署'),
    (('tools/lh-verify.py', 'tests/test-lh-verify.py',
      'tools/body_contract.py', 'tests/test-body-contract.py'),
     ('case', 'test-lh-deploy.py'), '离线验收或正文契约变更 → 部署消费者'),
    (('tools/sync-targets.json',),
     ('case', 'test-lh-deploy.py'), '对象登记变更 → 部署消费者'),
    # 运行器、选路表与 CI 容器自身变化：既进 full，也须跑所有把 runner 当消费者的定向组。
    (('tests/run-tests.sh', 'tests/test_paths.py', '.github/workflows/tests.yml'),
     ('group', 'auth'), '运行器、选路表或 CI 测试 workflow → auth 消费者'),
    (('tests/run-tests.sh', 'tests/test_paths.py', '.github/workflows/tests.yml'),
     ('group', 'identity'), '运行器、选路表或 CI 测试 workflow → identity 消费者'),
    (('tests/run-tests.sh', 'tests/test_paths.py', '.github/workflows/tests.yml'),
     ('group', 'verify'), '运行器、选路表或 CI 测试 workflow → verify 消费者'),
    (('tests/run-tests.sh', 'tests/test_paths.py', '.github/workflows/tests.yml'),
     ('group', 'minis-verify'), '运行器、选路表或 CI 测试 workflow → minis-verify 消费者'),
    (('tests/run-tests.sh', 'tests/test_paths.py', '.github/workflows/tests.yml'),
     ('group', 'lh-wiring'), '运行器、选路表或 CI 测试 workflow → lh-wiring 消费者'),
    # 拆出的运行器行为回归与按需包内校验入口：各自只由自身、运行器/选路表/workflow 变更命中。
    (('tests/test-runner.sh',),
     ('case', 'test-runner.sh'), '运行器、信号与选路回归 → runner'),
    (('tools/sync-all.sh', 'skills/luno-core/scripts/quick_validate.py',
      'tests/run-tests.sh', 'tests/test_paths.py', '.github/workflows/tests.yml'),
     ('case', 'sync-all.sh'), '按需包内校验（结构守卫＋技能包校验）与运行器变更 → 包内校验'),
    (('tests/run-tests.sh', 'tests/test_paths.py', '.github/workflows/tests.yml'),
     ('case', 'test-runner.sh'), '运行器、选路表或 CI 测试 workflow → runner 消费者'),
    # 退休入口的删除 diff 仍须可选路，但不再指向已删除套件。
    (('tests/run-tests.sh', 'tests/test_paths.py', '.github/workflows/tests.yml', 'tools/sync-all.sh',
      'tests/test-deploy-skill.py', 'tests/test-pack-skill-zip.py'),
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

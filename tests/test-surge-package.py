#!/usr/bin/env python3
"""luno-surge 包态回归：运行树只含登记的自有资源、命令参考等不是基线官方原件、真包打包结果
等于登记清单、文档本地链接与脚本语法通过离线验收。只读仓库；脚本行为见 test-surge-scripts.py。

从 test-surge-scripts.py 拆出的既有判据，随 surge 组照旧进 full；Surge 文档、资源或登记改动只跑本文件。
"""
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/luno-surge'
SCRIPTS = SKILL / 'scripts'
COMMAND_REFERENCE = SKILL / 'references/command-reference.md'
MANIFEST = SKILL / 'references/upstream-manifest.json'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def surge_registry():
    doc = json.loads((ROOT / 'tools/sync-targets.json').read_text())
    (obj,) = [o for o in doc['objects'] if o['id'] == 'luno-surge']
    return doc, obj


class AuthoredResourceStateTest(unittest.TestCase):
    def test_registry_resources_are_present_without_official_exceptions(self):
        doc, obj = surge_registry()
        self.assertFalse(any('officialPackageResources' in o for o in doc['objects']))
        self.assertIn('skills/luno-surge/references/plugin-authoring.md', obj['resources'])
        for name in obj['resources']:
            self.assertTrue((ROOT / name).is_file(), name)
        raw = json.loads(MANIFEST.read_text())['builds'][-1]['raw_sha256']
        for source, own in (('references/command-reference.md', COMMAND_REFERENCE),
                            ('references/plugin-authoring.md', SKILL / 'references/plugin-authoring.md'),
                            ('agents/openai.yaml', SKILL / 'agents/openai.yaml')):
            self.assertNotEqual(raw[source], hashlib.sha256(own.read_bytes()).hexdigest())
        self.assertFalse((SKILL / 'references/upstream-SKILL.md').exists())
        self.assertFalse((SKILL / 'references/upstream-command-reference.md').exists())
        self.assertFalse((SKILL / 'assets/logo.png').exists())

    def test_real_skill_package_is_self_contained(self):
        packer = load_module('surge_release_state', SCRIPTS / 'package_release.py')
        _doc, obj = surge_registry()
        expected = sorted(['SKILL.md'] + [str(Path(r).relative_to('skills/luno-surge'))
                                        for r in obj['resources']])
        with zipfile.ZipFile(io.BytesIO(packer.build(packer.collect(SKILL)))) as archive:
            self.assertEqual(expected, archive.namelist())
            for name in expected:
                self.assertEqual((SKILL / name).read_bytes(), archive.read(name))

    def test_offline_acceptance_passes_on_the_real_package(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('SURGE_')}
        r = subprocess.run(['sh', str(SCRIPTS / 'acceptance.sh'), '--offline'], env=env,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn('PASS  Offline syntax and local links\n', r.stdout)


if __name__ == '__main__':
    unittest.main()

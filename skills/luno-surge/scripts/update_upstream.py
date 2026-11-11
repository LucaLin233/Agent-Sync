#!/usr/bin/env python3
"""Read-only provenance check: hash the five official Skill files under a directory and
compare them with the manifest baseline. No download, writes, import or original text output.

The caller authenticates the app bundle and authorizes reading it; hashes and the version
label do not authenticate the source.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ('SKILL.md', 'references/command-reference.md',
         'references/plugin-authoring.md', 'agents/openai.yaml', 'assets/logo.png')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    inspect = commands.add_parser('inspect', help='hash an authorized directory; no writes')
    inspect.add_argument('--source', required=True, help='directory holding the official Skill')
    inspect.add_argument('--version', required=True, help='app version/build label; not identity proof')
    args = parser.parse_args(argv)
    source = Path(args.source)
    try:
        raw = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in FILES}
        manifest = json.loads((ROOT / 'references/upstream-manifest.json').read_text(encoding='utf-8'))
        baseline = manifest['builds'][-1]['raw_sha256']
        changed = sorted(name for name in FILES if raw[name] != baseline[name])
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        parser.exit(1, 'E_SOURCE_READ\n')
    print(json.dumps({'version_report': args.version, 'source_authentication': 'not performed',
                      'raw_sha256': raw, 'changed_from_baseline': changed,
                      'runtime_validation': 'not performed', 'imported': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

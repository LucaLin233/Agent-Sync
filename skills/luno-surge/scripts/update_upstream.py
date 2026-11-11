#!/usr/bin/env python3
"""Read-only provenance inspection. No download, staging, import or apply.

The caller must authenticate the official app bundle and authorize source access.
Hashes and a user-provided version label do not authenticate that source.
"""
import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ('SKILL.md', 'references/command-reference.md',
         'references/plugin-authoring.md', 'agents/openai.yaml', 'assets/logo.png')
RETIRED = 'E_IMPORT_RETIRED: prepare/apply removed; use inspect for provenance only.'


def directory(path):
    # Retain directory fds, refuse symlinks and ambiguous path components.
    parts = str(path).split('/')
    if parts[0] or any(x in ('', '.', '..') for x in parts[1:]):
        raise ValueError('source path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    parent = '/'
    try:
        for part in parts[1:]:
            full = os.path.normpath(os.path.join(parent, part))
            if not full.startswith(parent.rstrip('/') + '/'):
                raise ValueError('source path')
            name = os.path.relpath(full, parent)
            if name != part:
                raise ValueError('source path')
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            parent = full
        return fd
    except BaseException:
        os.close(fd)
        raise


def digest(root_fd, name):
    fd = os.dup(root_fd)
    try:
        parts = name.split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(file_fd, 'rb') as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError('not regular')
            value = hashlib.sha256()
            for block in iter(lambda: source.read(65536), b''):
                value.update(block)
            return value.hexdigest()
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    inspect = commands.add_parser('inspect', help='hash an authorized external snapshot; no writes')
    inspect.add_argument('--source', required=True, help='absolute, non-symlink directory')
    inspect.add_argument('--version', required=True, help='non-secret app version/build label; not identity proof')
    # Refuse historical verbs before parsing flags or touching source/transaction paths.
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ('prepare', 'apply'):
        parser.exit(2, RETIRED + '\n')
    args = parser.parse_args(argv)
    source = Path(args.source)
    if source == ROOT or ROOT in source.parents or not args.version.strip() or len(args.version) > 120:
        parser.exit(2, 'E_SOURCE_INPUT\n')
    fd = None
    try:
        fd = directory(args.source)
        raw = {name: digest(fd, name) for name in FILES}
        baseline = json.loads((ROOT / 'references/upstream-manifest.json').read_text())['raw_sha256']
        if not isinstance(baseline, dict):
            raise ValueError('manifest')
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, 'E_SOURCE_READ\n')
    finally:
        if fd is not None:
            os.close(fd)
    print(json.dumps({'version_report': args.version, 'source_authentication': 'not performed',
                      'raw_sha256': raw, 'changed_from_baseline': sorted(
                          name for name in FILES if raw[name] != baseline.get(name)),
                      'runtime_validation': 'not performed', 'imported': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

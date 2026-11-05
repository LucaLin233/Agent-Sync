#!/usr/bin/env python3
"""Read-only recognition of reviewed official raw and historical adapted references.

classify(digest) retains raw/adapted/unknown; neither CLI nor API writes files.
Historical hashes remain recognition evidence, not official import permission.
"""
from pathlib import Path
import sys
import hashlib

REVIEWED_SHA256 = {
    '81be46e9a4444de5af120ddac49bd18910f0a98279a1467174cd8c3b0001a7a5',
    '66f0b248fa7f696ea5f9b8511729f6c82a25c3bee23a6f5305ce4bdf6b64df4b',
    '42a0509642641dfc9cf70001997a26c4241f9d72df5c136141d763c695cd51ea',
}

ADAPTED_SHA256 = {
    '5331f03b90a1d6b21e406057b48364499b7b7a43697f566746e1ec6a0170c51f',
    '334747c73b439f65533846c0b27636948cf5a64900a71e90d7bda495559018c3',
    '515303de1d9b925fe77fe8d3a8abf6fc24a4b42e01488e59baef0a5bb98c7901',
    'd3163362737811035c5e32df531630abd1913998cdfcdad554235329007234fe',
    '5538a3ed0b010a958f4ca4ceb6d5700a152837429445a41a1d04cd9ccfe298b4',
    '34309dfb3c4e1129afdfb13ca4dfe4afbd76057546f69100eb3c5829ba855167',
    '1085f42a12ffdff913ea6c817c5efa6308bace52cd5808faa82c1f84d6d89fba',
    '48a99818a4c55698628542da447b45be05ec503872ac578c080621cfe8d77b9f',
    '8fd1defde65d83662f193d872e94af4c9afdc3a94be0c7ab3796444b68f32721',
}

def adapt_text(text):
    """Reject the retired generation API, including former no-op inputs."""
    raise SystemExit(
        'Reference generation is disabled: command-reference.md is a manually maintained '
        'overlay; use classify() or the read-only CLI.')


def classify(digest):
    """Return 'raw', 'adapted' or 'unknown' for a sha256 hex digest."""
    if digest in ADAPTED_SHA256:
        return 'adapted'
    if digest in REVIEWED_SHA256:
        return 'raw'
    return 'unknown'


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        raise SystemExit('usage: adapt_upstream_reference.py <reference.md> (read-only classification)')
    digest = hashlib.sha256(Path(argv[0]).read_bytes()).hexdigest()
    kind = classify(digest)
    if kind == 'unknown':
        raise SystemExit(
            'Unreviewed reference: neither reviewed official raw text nor a known historical '
            'adapted product; nothing was written.')
    print(kind + ' sha256=' + digest)


if __name__ == '__main__':
    main()

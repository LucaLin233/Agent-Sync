#!/usr/bin/env python3
"""Build a sanitized, reproducible-ish ZIP of the Surge Skill.

Default output: /var/minis/shared/release/surge-skill-YYYYMMDD.zip (argument overrides;
paths inside the Skill directory are rejected). Entries sit at the ZIP root, the layout
`lh skill install` consumes; no `surge/` prefix.

`collect(root)` filters entries, `build(entries)` returns archive bytes with one read per
file, so scanned bytes are archived bytes. `tools/deploy_skill.py` reuses both.
"""
from __future__ import annotations
import hashlib, io, json, os, re, stat, sys, zipfile
from datetime import datetime
from pathlib import Path

SCRIPT_DIR=Path(__file__).resolve().parent
SOURCE=SCRIPT_DIR.parent
DEFAULT=Path("/var/minis/shared/release") / f"surge-skill-{datetime.now():%Y%m%d}.zip"
OUTPUT=Path(sys.argv[1]).expanduser() if len(sys.argv)>1 else DEFAULT
EXCLUDED_PARTS={"__pycache__",".git",".DS_Store","logs","log","secrets","secret","private",".ssh"}
EXCLUDED_SUFFIXES={".pyc",".pyo",".session",".sqlite",".db",".log",".key",".pem",".conf"}
EXCLUDED_NAMES={"password","credentials",".env","secrets.env","secrets","id_rsa","id_ed25519","known_hosts",".netrc",".git-credentials"}
FORBIDDEN_RESOURCES={"references/upstream-SKILL.md", "references/upstream-command-reference.md", "assets/logo.png"}
OFFICIAL_SOURCE_KEYS={"SKILL.md", "references/command-reference.md",
                      "references/plugin-authoring.md", "agents/openai.yaml", "assets/logo.png"}
SECRET_PATTERNS=[
    re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(rb"(?i)(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{20,}"),
]


class ReleaseError(Exception):
    """消息只含相对路径与原因，不含文件内容。"""


class SecretError(ReleaseError):
    """敏感模式命中：不回显命中值。"""


def included(path:Path,root:Path|None=None)->bool:
    """排除项按大小写归一比较。"""
    rel=path.relative_to(SOURCE if root is None else root)
    parts={p.lower() for p in rel.parts}
    return not (parts&{p.lower() for p in EXCLUDED_PARTS}
                or path.suffix.lower() in {s.lower() for s in EXCLUDED_SUFFIXES}
                or path.name.lower() in {n.lower() for n in EXCLUDED_NAMES})

def digest(data:bytes)->str: return hashlib.sha256(data).hexdigest()


def _walk_error(exc):
    """遍历出错即上抛，不静默跳过目录树。"""
    raise ReleaseError(f"Traversal error while collecting release files: {exc}")


def collect(root):
    """返回按相对路径排序的 [(rel, path)]；符号链接、非常规条目、遍历错误均抛 ReleaseError。"""
    root=Path(root)
    entries=[]
    for cur,dirs,files in os.walk(root,onerror=_walk_error,followlinks=False):
        for name in dirs:
            path=Path(cur)/name
            if path.is_symlink():
                raise ReleaseError(f"Symlinks are not allowed in release packages: "
                                   f"{path.relative_to(root).as_posix()}")
        for name in files:
            path=Path(cur)/name
            if path.is_symlink():
                raise ReleaseError(f"Symlinks are not allowed in release packages: "
                                   f"{path.relative_to(root).as_posix()}")
            if not path.is_file():
                raise ReleaseError(f"Non-regular entries are not allowed in release packages: "
                                   f"{path.relative_to(root).as_posix()}")
            if included(path,root):
                entries.append((path.relative_to(root).as_posix(),path))
    if not entries: raise ReleaseError("No files to package")
    entries.sort(key=lambda entry:entry[0])
    return entries


def build(entries):
    """确定性布局构建 ZIP bytes；每个文件只读一次，同一份 bytes 先扫描再归档。"""
    # Cache only the manifest: scan and archive exactly these same bytes, read once.
    manifest_name="references/upstream-manifest.json"
    manifest_entries=[path for rel,path in entries if rel==manifest_name]
    if len(manifest_entries)!=1:
        raise ReleaseError("Invalid provenance manifest")
    try:
        manifest_data=Path(manifest_entries[0]).read_bytes()
        manifest=json.loads(manifest_data.decode("utf-8"))
        raw=manifest["raw_sha256"]
        if (not isinstance(raw,dict) or set(raw)!=OFFICIAL_SOURCE_KEYS or not all(
                isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value)
                for value in raw.values())):
            raise ValueError("hash table")
        raw_hashes=set(raw.values())
    except (OSError,ValueError,KeyError,TypeError,UnicodeError):
        raise ReleaseError("Invalid provenance manifest") from None
    # Known whole-file detection is not a general copyright/license classifier.
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for rel,path in entries:
            if rel in FORBIDDEN_RESOURCES:
                raise ReleaseError(f"Official resource is not distributable: {rel}")
            data=manifest_data if rel==manifest_name else Path(path).read_bytes()
            if digest(data) in raw_hashes:
                raise ReleaseError(f"Known whole official file is not distributable: {rel}")
            for pattern in SECRET_PATTERNS:
                if pattern.search(data):
                    raise SecretError(f"Potential secret found in {rel}")
            info=zipfile.ZipInfo(rel,date_time=(2026,1,1,0,0,0))
            mode=0o755 if Path(path).stat().st_mode & 0o111 else 0o644
            info.external_attr=(stat.S_IFREG|mode)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    return buf.getvalue()


def main():
    try:
        OUTPUT.resolve().relative_to(SOURCE.resolve())
    except ValueError:
        pass
    else:
        raise SystemExit("Output ZIP must be outside the Skill directory")
    try:
        entries=collect(SOURCE)
        blob=build(entries)
    except ReleaseError as exc:
        raise SystemExit(str(exc))
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUTPUT.with_suffix(OUTPUT.suffix+".tmp")
    try:
        tmp.write_bytes(blob)
        tmp.replace(OUTPUT)
    finally:
        tmp.unlink(missing_ok=True)
    print(OUTPUT)
    print(digest(blob))
    print(f"files={len(entries)} bytes={OUTPUT.stat().st_size}")
if __name__=="__main__": main()

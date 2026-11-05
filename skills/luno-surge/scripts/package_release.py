#!/usr/bin/env python3
"""Build a sanitized, reproducible-ish ZIP of the Surge Skill for sharing.

Default output is an out-of-directory, persistent path
(/var/minis/shared/release/surge-skill-YYYYMMDD.zip); an explicit path argument
still overrides it, but a path inside the Skill directory is always rejected.

Archive entries are rooted at the ZIP root (no top-level directory): that is the
layout `lh skill install` consumes, and the same layout used for the LobeHub
delivery package. Do not reintroduce a `surge/` prefix.

Two layers, one implementation: `collect(root)` returns the filtered entry list,
`build(entries)` returns the archive bytes in memory. The CLI (`main`) is a thin
wrapper that writes those bytes atomically. `tools/deploy_skill.py` reuses the
same two functions for the Surge path, so filtering, symlink rejection, the
secret scan and the archived bytes are **one** read per build: what is scanned
is exactly what is archived.
"""
from __future__ import annotations
import hashlib, io, os, re, stat, sys, zipfile
from datetime import datetime
from pathlib import Path

SCRIPT_DIR=Path(__file__).resolve().parent
SOURCE=SCRIPT_DIR.parent
DEFAULT=Path("/var/minis/shared/release") / f"surge-skill-{datetime.now():%Y%m%d}.zip"
OUTPUT=Path(sys.argv[1]).expanduser() if len(sys.argv)>1 else DEFAULT
EXCLUDED_PARTS={"__pycache__",".git",".DS_Store","logs","log","secrets","secret","private",".ssh"}
EXCLUDED_SUFFIXES={".pyc",".pyo",".session",".sqlite",".db",".log",".key",".pem",".conf"}
EXCLUDED_NAMES={"password","credentials",".env","secrets.env","secrets","id_rsa","id_ed25519","known_hosts",".netrc",".git-credentials"}
SECRET_PATTERNS=[
    re.compile(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(rb"(?i)(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{20,}"),
]


class ReleaseError(Exception):
    """收集／构建失败（固定类别；消息只含相对路径与原因，不含文件内容）。"""


class SecretError(ReleaseError):
    """敏感模式命中：本类只报类别与相对路径，不回显命中值。"""


def included(path:Path,root:Path|None=None)->bool:
    """排除项全部按大小写归一比较（归档仍保留原始路径）。"""
    rel=path.relative_to(SOURCE if root is None else root)
    parts={p.lower() for p in rel.parts}
    return not (parts&{p.lower() for p in EXCLUDED_PARTS}
                or path.suffix.lower() in {s.lower() for s in EXCLUDED_SUFFIXES}
                or path.name.lower() in {n.lower() for n in EXCLUDED_NAMES})

def digest(data:bytes)->str: return hashlib.sha256(data).hexdigest()


def _walk_error(exc):
    """os.walk 的 onerror 回调：遍历出错立即上抛，绝不静默跳过目录树。"""
    raise ReleaseError(f"Traversal error while collecting release files: {exc}")


def collect(root):
    """收集 root 下应归档的条目，返回按相对路径排序的 [(rel, path)]。

    先拒符号链接（目录与文件，含不跟随）、再拒非常规条目；遍历错误上抛。**无回退**：
    任一守卫命中即抛 ReleaseError，调用方据类别失败，不产出任何包。
    """
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
    """按既有确定性布局构建 ZIP 并返回内存 bytes；每个文件只读一次。

    同一次读取的 bytes 既用于敏感模式检查、也用于归档，故「被检查的」与「被归档的」
    必然是同一份内容（检查后替换源文件不会让未检 bytes 进包）。命中即抛 SecretError，
    不回显命中值。
    """
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for rel,path in entries:
            data=Path(path).read_bytes()
            for pattern in SECRET_PATTERNS:
                if pattern.search(data):
                    raise SecretError(f"Potential secret found in {rel}")
            info=zipfile.ZipInfo(rel,date_time=(2026,1,1,0,0,0))
            mode=0o755 if os.access(path,os.X_OK) else 0o644
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

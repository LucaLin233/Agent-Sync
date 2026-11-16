#!/usr/bin/env python3
"""LobeHub 窄部署：旧版验收 → 官方 CLI 写 → 合并版验收（每对象串行、首错停）。

用法（`python3 -I -B`）：
  python3 -I -B tools/lh-deploy.py --repo ABS --object ID [--object ID …] \
      --base <40位hex> --merged <40位hex> --out-dir ABS --instance-ref LABEL \
      --source-basis REF [--total-timeout 180] < target.json

顺序：无凭据阶段先核两版登记的身份/类型/kind/ID/source/installSource 相同、资源只增不减、旧 blob 完整可读，
并核安装分支 HEAD 仍等于 merged；随后新建 pre 观察（tools/lh-collect.py + tools/lh-verify.py）对 base 验收，
任意非 0 即零写；通过后紧邻执行官方 CLI 写；写后再核分支 HEAD，仍以新建 post 观察对 merged 验收。
Agent 对象因实际表列/身份绑定未核准，在 pre 阶段以 `schema_unverified` 阻断，不写。首个错误后其余对象 not_run。

退出码：0 全部 post 通过 / 1 确证差异 / 2 执行、格式、写失败、超时或清理失败 / 3 缺证或首版不支持（并存 2>3>1>0）。
stdout 一份摘要 JSON，不回显正文、资源、坐标或凭据。
"""
import argparse
import base64
import binascii
import datetime
import json
import os
import re
import subprocess
import sys

HEX40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
USER_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]{0,31}\Z")
HOST_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9.-]{0,252}\Z")
BRANCH = "refs/heads/main"
GIT_ENV = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.devnull,
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_LAZY_FETCH": "1", "GIT_ASKPASS": "/bin/false", "LC_ALL": "C",
}
BASE_ENV = {"LC_ALL": "C.UTF-8"}


class Fail(Exception):
    def __init__(self, code, exit, phase="admission", object_name=None, changed=False):
        super().__init__(code)
        self.code = code
        self.exit = exit
        self.phase = phase
        self.object_name = object_name
        self.changed = changed


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Fail("bad_args", 2)


def _env():
    """最小白名单：只沿用调用方的 PATH 与 TMPDIR，不继承其余变量。"""
    env = dict(BASE_ENV)
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    if os.environ.get("TMPDIR"):
        env["TMPDIR"] = os.environ["TMPDIR"]
    return env


def _utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(repo, args, data=None, timeout=60):
    extra = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
    try:
        proc = subprocess.run(
            ["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-C", repo] + args,
            env=dict(GIT_ENV), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, timeout=timeout, **extra)
    except (OSError, subprocess.SubprocessError):
        raise Fail("git_error", 3) from None
    return proc


def _registry(repo, version):
    proc = _git(repo, ["cat-file", "blob", "%s:tools/sync-targets.json" % version])
    if proc.returncode != 0:
        raise Fail("registry_invalid", 3)
    try:
        doc = json.loads(proc.stdout.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise Fail("registry_invalid", 3) from None
    if not isinstance(doc, dict) or doc.get("schemaVersion") != 1 \
            or not isinstance(doc.get("objects"), list):
        raise Fail("registry_invalid", 3)
    return {e["id"]: e for e in doc["objects"] if isinstance(e, dict) and isinstance(e.get("id"), str)}


def _classify(entry):
    lh = (entry.get("ends") or {}).get("lobehub") or {}
    if not isinstance(lh, dict) or lh.get("present") is not True:
        raise Fail("registry_invalid", 3)
    ident, kind = lh.get("id"), lh.get("kind")
    if not isinstance(ident, str) or not ident:
        raise Fail("registry_invalid", 3)
    if entry.get("type") == "skill" and kind == "skill":
        return "skill", ident
    if entry.get("type") in ("prompt", "subagent") and kind == "agent" \
            and lh.get("field") == "systemRole":
        return "agent", ident
    raise Fail("registry_invalid", 3)


def _target(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise Fail("bad_target", 2)
            out[key] = value
        return out
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (ValueError, UnicodeError):
        raise Fail("bad_target", 2) from None
    if not isinstance(doc, dict) or set(doc) != {"ssh", "postgres"}:
        raise Fail("bad_target", 2)
    ssh, pg = doc["ssh"], doc["postgres"]
    if not isinstance(ssh, dict) or set(ssh) != {"host", "port", "user", "knownHostsFile"}:
        raise Fail("bad_target", 2)
    if not isinstance(pg, dict) or set(pg) != {"container", "database", "port", "user"}:
        raise Fail("bad_target", 2)
    for node in (ssh, pg):
        for value in node.values():
            if isinstance(value, str) and (not value or any(ord(c) < 0x21 or ord(c) == 0x7f for c in value)):
                raise Fail("bad_target", 2)
    if not isinstance(ssh["host"], str) or not HOST_RE.match(ssh["host"]):
        raise Fail("bad_target", 2)
    if not isinstance(ssh["user"], str) or not USER_RE.match(ssh["user"]):
        raise Fail("bad_target", 2)
    if type(ssh["port"]) is not int or not 1 <= ssh["port"] <= 65535:
        raise Fail("bad_target", 2)
    if not isinstance(ssh["knownHostsFile"], str) or not ssh["knownHostsFile"].startswith("/"):
        raise Fail("bad_target", 2)
    for key in ("container", "database", "user"):
        if not isinstance(pg[key], str) or not USER_RE.match(pg[key]):
            raise Fail("bad_target", 2)
    if type(pg["port"]) is not int or not 1 <= pg["port"] <= 65535:
        raise Fail("bad_target", 2)
    return doc


def _branch_head(repo, timeout):
    """匿名核安装来源分支 HEAD：只读 ls-remote，不 fetch、不改工作树。"""
    origin = _git(repo, ["config", "--get", "remote.origin.url"], timeout=timeout)
    url = origin.stdout.decode("utf-8", "replace").strip() if origin.returncode == 0 else ""
    target = url or repo
    proc = _git(repo, ["ls-remote", target, BRANCH], timeout=timeout)
    if proc.returncode != 0:
        raise Fail("source_unverified", 3)
    try:
        rows = [ln.split("\t") for ln in proc.stdout.decode("utf-8").splitlines() if ln]
    except UnicodeDecodeError:
        raise Fail("source_unverified", 3) from None
    if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] != BRANCH:
        raise Fail("source_unverified", 3)
    if not HEX40_RE.match(rows[0][0]):
        raise Fail("source_unverified", 3)
    return rows[0][0]


def _run(argv, env, timeout, phase="write"):
    try:
        proc = subprocess.run(argv, env=dict(env), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              shell=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Fail("timeout", 2, phase) from None
    except (OSError, subprocess.SubprocessError):
        raise Fail("cli_error", 2, phase) from None
    return proc.returncode


def _collect(repo, name, version, out_dir, args, target_raw, phase):
    argv = [sys.executable or "python3", "-I", "-B",
            os.path.join(repo, "tools", "lh-collect.py"),
            "--repo", repo, "--object", name, "--git-version", version,
            "--out-dir", out_dir, "--instance-ref", args.instance_ref,
            "--source-basis", args.source_basis,
            "--total-timeout", str(args.total_timeout)]
    rc = subprocess.call
    try:
        proc = subprocess.run(argv, input=target_raw, env=_env(),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              shell=False, timeout=args.total_timeout)
    except subprocess.TimeoutExpired:
        raise Fail("timeout", 2, phase) from None
    except (OSError, subprocess.SubprocessError):
        raise Fail("cli_error", 2, phase) from None
    if proc.returncode != 0:
        raise Fail("missing_evidence" if proc.returncode == 3 else "cli_error",
                   3 if proc.returncode == 3 else 2, phase)
    return out_dir


def _verify(repo, name, version, evidence, args, phase):
    argv = [sys.executable or "python3", "-I", "-B",
            os.path.join(repo, "tools", "lh-verify.py"), "--repo", repo,
            "--git-version", version, "--object", name, "--evidence", evidence]
    try:
        proc = subprocess.run(argv, env=_env(), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              shell=False, timeout=args.total_timeout)
    except subprocess.TimeoutExpired:
        raise Fail("timeout", 2, phase) from None
    except (OSError, subprocess.SubprocessError):
        raise Fail("cli_error", 2, phase) from None
    if proc.returncode == 0:
        return
    if proc.returncode == 1:
        raise Fail("pre_difference" if phase == "pre" else "post_difference", 1, phase)
    if proc.returncode == 3:
        raise Fail("missing_evidence", 3, phase)
    raise Fail("cli_error", 2, phase)


def _cli(env_extra, argv, timeout, phase):
    env = _env()
    env.update(env_extra)
    return _run(argv, env, timeout, phase)


def main(argv=None):
    summary = {"schemaVersion": 1, "status": "failed", "objects": [], "errors": [],
               "artifacts": [], "notCovered": [
                   "无平台 CAS：不保证不存在外部并发",
                   "Agent 实际表列与身份绑定未核准，本版阻断",
                   "post 阶段尾 LF 一次性纠正例外未实现",
               ]}
    err = None
    try:
        parser = _Parser(prog="lh-deploy", add_help=True)
        parser.add_argument("--repo", required=True)
        parser.add_argument("--object", action="append", required=True, dest="objects")
        parser.add_argument("--base", required=True)
        parser.add_argument("--merged", required=True)
        parser.add_argument("--out-dir", required=True)
        parser.add_argument("--instance-ref", required=True)
        parser.add_argument("--source-basis", required=True)
        parser.add_argument("--total-timeout", type=int, default=180)
        args = parser.parse_args(argv)
        if type(args.total_timeout) is not int or args.total_timeout <= 0:
            raise Fail("bad_args", 2)
        for sha in (args.base, args.merged):
            if not isinstance(sha, str) or not HEX40_RE.match(sha):
                raise Fail("bad_args", 2)
        if not os.path.isabs(args.repo) or not os.path.isdir(args.repo):
            raise Fail("bad_args", 2)
        if not os.path.isabs(args.out_dir) or os.path.lexists(args.out_dir) \
                or not os.path.isdir(os.path.dirname(args.out_dir)):
            raise Fail("unsafe_path", 2)
        selected = list(dict.fromkeys(args.objects))
        if not selected:
            raise Fail("bad_args", 2)
        target_raw = sys.stdin.buffer.read()
        _target(target_raw)  # 只校验，不回显、不落盘
        base_reg = _registry(args.repo, args.base)
        merged_reg = _registry(args.repo, args.merged)
        plan = []
        for name in selected:
            old, new = base_reg.get(name), merged_reg.get(name)
            if old is None or new is None:
                raise Fail("registry_invalid", 3)
            kind, lh_id = _classify(old)
            kind_new, lh_new = _classify(new)
            if (kind, lh_id) != (kind_new, lh_new) or old.get("source") != new.get("source") \
                    or old.get("installSource") != new.get("installSource") \
                    or old.get("type") != new.get("type"):
                raise Fail("identity_difference", 3)
            if not set(old.get("resources") or []) <= set(new.get("resources") or []):
                raise Fail("unsupported", 3)
            plan.append((name, old, new, kind, lh_id))
        head = _branch_head(args.repo, min(60, args.total_timeout))
        if head != args.merged:
            raise Fail("branch_changed", 3)
        # 旧 blob 完整可读（源 + 全部旧资源），缺即停，不做 lazy fetch。
        blobs = []
        for name, old, _, _, _ in plan:
            blobs.append(old["source"])
            blobs.extend(old.get("resources") or [])
        if blobs:
            request = "".join("%s:%s\n" % (args.base, p) for p in dict.fromkeys(blobs)).encode("utf-8")
            proc = _git(args.repo, ["cat-file", "--batch"], request)
            if proc.returncode != 0 or proc.stdout.count(b" blob ") != len(dict.fromkeys(blobs)):
                raise Fail("source_unverified", 3)
        os.mkdir(args.out_dir, 0o700)
        os.chmod(args.out_dir, 0o700)
        api_env = {}
        for name in ("LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY"):
            if os.environ.get(name):
                api_env[name] = os.environ[name]
        if not api_env:
            # 变量缺失由 collect 报 missing_variable；这里只表示本阶段无凭据可用。
            pass
        stop = False
        for index, (name, old, new, kind, lh_id) in enumerate(plan):
            entry = {"object": name, "phase": "admission", "status": "not_run",
                     "code": None, "changed": False}
            summary["objects"].append(entry)
            if stop:
                continue
            try:
                pre_dir = os.path.join(args.out_dir, "pre-%d" % index)
                _collect(args.repo, name, args.base, pre_dir, args, target_raw, "pre")
                if kind == "agent":
                    raise Fail("unsupported", 3, "pre")
                _verify(args.repo, name, args.base,
                        os.path.join(pre_dir, "skill-evidence.json"), args, "pre")
                entry.update(phase="write", status="running")
                install = new.get("installSource")
                if not isinstance(install, str) or not install:
                    raise Fail("missing_evidence", 3, "write")
                rc = _cli(api_env, ["lh", "skill", "install", install],
                          args.total_timeout, "write")
                entry["changed"] = "unknown"
                if rc != 0:
                    raise Fail("cli_error", 2, "write", changed="unknown")
                head2 = _branch_head(args.repo, min(60, args.total_timeout))
                if head2 != args.merged:
                    raise Fail("branch_changed", 3, "post", changed="unknown")
                post_dir = os.path.join(args.out_dir, "post-%d" % index)
                _collect(args.repo, name, args.merged, post_dir, args, target_raw, "post")
                _verify(args.repo, name, args.merged,
                        os.path.join(post_dir, "skill-evidence.json"), args, "post")
                entry.update(phase="post", status="completed", code=None, changed=True)
                summary["artifacts"] += ["pre-%d/skill-evidence.json" % index,
                                         "post-%d/skill-evidence.json" % index]
            except Fail as exc:
                entry.update(phase=exc.phase, status="failed", code=exc.code,
                             changed=exc.changed if exc.changed else entry.get("changed", False))
                summary["errors"].append(exc.code)
                if exc.object_name:
                    entry["object"] = exc.object_name
                stop = True
                if err is None or {"2": 3, "3": 2}.get(str(exc.exit), 0) >= \
                        {"2": 3, "3": 2}.get(str(getattr(err, "exit", 2)), 0):
                    err = exc
        done = [e for e in summary["objects"] if e["status"] == "completed"]
        bad = [e for e in summary["objects"] if e["status"] == "failed"]
        if not bad and len(done) == len(plan):
            summary["status"] = "complete"
        elif done and bad:
            summary["status"] = "partial"
        else:
            summary["status"] = "failed"
    except Fail as exc:
        err = exc
        summary["errors"].append(exc.code)
        summary["status"] = "failed"
        if not summary["objects"]:
            summary["objects"].append({"object": "-", "phase": exc.phase,
                                       "status": "failed", "code": exc.code,
                                       "changed": False})
    except Exception:
        err = Fail("internal_error", 2)
        summary["errors"].append("internal_error")
        summary["status"] = "failed"
    sys.stdout.write(json.dumps(summary, ensure_ascii=True) + "\n")
    if err is None:
        return 0
    sys.stderr.write(json.dumps({"ok": False, "error": err.code}) + "\n")
    return err.exit


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""LobeHub 窄采集：固定只读 SQL 投影 + auth-call 原 bytes，组装既有证据 schema。

用法（Minis/iSH 已审副本，仅标准库，`python3 -I -B`）：
  python3 -I -B tools/lh-collect.py --repo ABS --object ID [--object ID …] \
      --git-version <40位小写hex> --out-dir ABS --instance-ref LABEL --source-basis REF \
      [--total-timeout 180] < target.json

范围：只采集该提交登记里 `ends.lobehub.present=true` 的技能与 Agent。技能投影五字段与资源**实际完整键**，
资源正文经 tools/auth-call.py 的 skill-resource 逐路径读取，原 stdout/stderr/exitCode 原样入证；Agent 的
实际表列与身份归属绑定尚未核准，本版在读取任何凭据前以 `schema_unverified` 停止（rc3），不猜字段。

目标 JSON 只在内存使用，不落盘、不回显：根键 ssh/postgres；不接收 query/command 或任何凭据。

退出码：0 采集完整 / 2 参数、格式、执行、不安全出口或读取错误 / 3 缺证或未核准前提（并存按 2>3>0）。
stdout 一份摘要 JSON；stderr 只固定码。正文、资源、坐标与凭据不进摘要。
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
NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
HOST_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9.-]{0,252}\Z")
USER_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]{0,31}\Z")
REL_PATH_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]{0,255}\Z")
SKILL_FIELDS = ("id", "name", "description", "identifier", "content", "resources")
MAX_TEXT = 2_000_000
MAX_SQL_OUT = 2_000_000
SSH_SECRETS = ("SSH_PRIVATE_KEY_B64",)
API_SECRETS = ("LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY")
BASE_ENV = {"LC_ALL": "C.UTF-8"}
GIT_ENV = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.devnull,
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_LAZY_FETCH": "1", "GIT_ASKPASS": "/bin/false", "LC_ALL": "C",
}
# 固定只读投影：五字段 + 资源实际完整键；文本一律 base64 传输后严格还原 UTF-8（不 strip、不归一 CRLF/尾 LF）。
SKILL_SQL = (
    "SET default_transaction_read_only = on;\n"
    "BEGIN READ ONLY;\n"
    "SELECT coalesce(json_build_object("
    "'id', id, 'name', name, 'description', description, 'identifier', identifier, "
    "'content', encode(convert_to(content, 'UTF8'), 'base64'), "
    "'resources', (SELECT coalesce(json_agg(k ORDER BY k), '[]'::json) "
    "FROM jsonb_object_keys(coalesce(resources, '{}'::jsonb)) AS k)"
    ")::text, 'MISSING') FROM skills WHERE id = :'obj_id';\n"
    "COMMIT;\n"
)


class Fail(Exception):
    """固定码 + 退出类别（2 执行/格式，3 缺证）。"""

    def __init__(self, code, exit=2):
        super().__init__(code)
        self.code = code
        self.exit = exit


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Fail("bad_args")


def _utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise Fail("bad_target")
        out[key] = value
    return out


def _git(repo, args, data=None):
    extra = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
    try:
        proc = subprocess.run(
            ["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-C", repo] + args,
            env=dict(GIT_ENV), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, timeout=60, **extra)
    except (OSError, subprocess.SubprocessError):
        raise Fail("git_error") from None
    if proc.returncode != 0:
        raise Fail("git_error")
    return proc.stdout


def _registry(repo, version):
    raw = _git(repo, ["cat-file", "blob", "%s:tools/sync-targets.json" % version])
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError):
        raise Fail("registry_invalid") from None
    if not isinstance(doc, dict) or doc.get("schemaVersion") != 1 \
            or not isinstance(doc.get("objects"), list):
        raise Fail("registry_invalid")
    by_id = {}
    for entry in doc["objects"]:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            by_id[entry["id"]] = entry
    return by_id


def _classify(entry):
    """返回 (kind, lobehub_id)；不合规抛 registry_invalid。"""
    ends = entry.get("ends") or {}
    lh = ends.get("lobehub") or {}
    if not isinstance(lh, dict) or lh.get("present") is not True:
        raise Fail("registry_invalid")
    ident, kind = lh.get("id"), lh.get("kind")
    if not isinstance(ident, str) or not ident:
        raise Fail("registry_invalid")
    if entry.get("type") == "skill" and kind == "skill":
        return "skill", ident
    if entry.get("type") in ("prompt", "subagent") and kind == "agent" \
            and lh.get("field") == "systemRole":
        return "agent", ident
    raise Fail("registry_invalid")


def _target(raw):
    """严格非秘密目标：固定键、固定类型，拒绝未知/重复键与控制字符。"""
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError):
        raise Fail("bad_target") from None
    if not isinstance(doc, dict) or set(doc) != {"ssh", "postgres"}:
        raise Fail("bad_target")
    ssh, pg = doc["ssh"], doc["postgres"]
    if not isinstance(ssh, dict) or set(ssh) != {"host", "port", "user", "knownHostsFile"}:
        raise Fail("bad_target")
    if not isinstance(pg, dict) or set(pg) != {"container", "database", "port", "user"}:
        raise Fail("bad_target")
    for node in (ssh, pg):
        for value in node.values():
            if isinstance(value, str):
                if not value or any(ord(ch) < 0x21 or ord(ch) == 0x7f for ch in value):
                    raise Fail("bad_target")
    for key, regex in (("host", HOST_RE), ("user", USER_RE)):
        if not isinstance(ssh[key], str) or not regex.match(ssh[key]):
            raise Fail("bad_target")
    if not isinstance(ssh["knownHostsFile"], str) or not ssh["knownHostsFile"].startswith("/") \
            or not NAME_RE.match(os.path.basename(ssh["knownHostsFile"])):
        raise Fail("bad_target")
    for key in ("port",):
        if type(ssh[key]) is not int or not 1 <= ssh[key] <= 65535:
            raise Fail("bad_target")
        if type(pg[key]) is not int or not 1 <= pg[key] <= 65535:
            raise Fail("bad_target")
    for key in ("container", "database", "user"):
        if not isinstance(pg[key], str) or not USER_RE.match(pg[key]):
            raise Fail("bad_target")
    return ssh, pg


def _need(name):
    """只核指定变量的存在性，不读值、不枚举、不回显。"""
    value = os.environ.get(name)
    if not value:
        raise Fail("missing_variable:" + name, 3)
    return True


class KeyRoot:
    """私钥承载：独占 700 根 / 600 文件，排他创建，退场重核身份后清理。"""

    def __init__(self):
        base = os.environ.get("TMPDIR") or "/tmp"
        self.root = tempfile_mkdtemp(base)
        self.path = os.path.join(self.root, "id")
        self.made = None
        self.root_ident = self._ident(self.root, False)

    def _ident(self, path, follow):
        try:
            st = os.stat(path) if follow else os.lstat(path)
        except OSError:
            raise Fail("cleanup_failed") from None
        return (st.st_dev, st.st_ino, st.st_mode & 0o170000)

    def write(self, material):
        try:
            material = base64.b64decode(material, validate=True)
        except (binascii.Error, ValueError):
            raise Fail("missing_variable:SSH_PRIVATE_KEY_B64", 3) from None
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError:
            raise Fail("unsafe_path") from None
        try:
            os.write(fd, material)
            os.fsync(fd)
        finally:
            os.close(fd)
        self.made = self._ident(self.path, False)
        return self.path

    def close(self):
        """重核仍是本单对象才删；任何不确定即报 cleanup_failed 并交出残留。"""
        if self.made is None:
            raise Fail("cleanup_failed")
        try:
            if self._ident(self.path, False) != self.made \
                    or self._ident(self.root, False) != self.root_ident:
                raise Fail("cleanup_failed")
            os.unlink(self.path)
            os.rmdir(self.root)
        except Fail:
            raise
        except OSError:
            raise Fail("cleanup_failed") from None
        self.made = None


def tempfile_mkdtemp(base):
    """mktemp -d 语义：独占 700 目录。"""
    import tempfile
    try:
        path = tempfile.mkdtemp(prefix="lh-collect-", dir=base)
    except OSError:
        raise Fail("unsafe_path") from None
    if (os.lstat(path).st_mode & 0o170000) != 0o040000:
        raise Fail("unsafe_path")
    return path


def _keyring():
    root = KeyRoot()
    if root.root_ident[2] != 0o040000:
        raise Fail("unsafe_path")
    return root, root.write(os.environ["SSH_PRIVATE_KEY_B64"])


def _env():
    """最小白名单：只沿用调用方的 PATH（用于 ssh）与 TMPDIR，不继承其余变量。"""
    env = dict(BASE_ENV)
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    if os.environ.get("TMPDIR"):
        env["TMPDIR"] = os.environ["TMPDIR"]
    return env


def _ssh_run(ssh, pg, keyfile, sql, variables, timeout):
    argv = [
        "ssh", "-F", "none",
        "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=" + ssh["knownHostsFile"],
        "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
        "-o", "ConnectTimeout=10", "-p", str(ssh["port"]), "-i", keyfile,
        "--", "%s@%s" % (ssh["user"], ssh["host"]), "--",
        "docker", "exec", "-i", "-e", "PGOPTIONS=-c default_transaction_read_only=on",
        "-e", "PGCONNECT_TIMEOUT=20", "-e", "PGAPPNAME=lh-collect",
        pg["container"],
    ]
    argv += ["psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1",
             "-p", str(pg["port"]), "-U", pg["user"], "-d", pg["database"], "-f", "-"]
    for name, value in variables:
        argv.append("-v")
        argv.append("%s=%s" % (name, value))
    try:
        proc = subprocess.run(argv, input=sql.encode("utf-8"), env=_env(),
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              shell=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Fail("timeout") from None
    except (OSError, subprocess.SubprocessError):
        raise Fail("source_unverified", 3) from None
    if proc.returncode != 0:
        raise Fail("source_unverified", 3)
    if len(proc.stdout) > MAX_SQL_OUT:
        raise Fail("source_unverified", 3)
    return proc.stdout


def _auth_call(repo, skill_id, path, timeout):
    argv = [sys.executable or "python3", "-I", "-B",
            os.path.join(repo, "tools", "auth-call.py"),
            "skill-resource", "--id", skill_id, "--path", path]
    env = _env()
    for name in API_SECRETS:
        if os.environ.get(name):
            env[name] = os.environ[name]
    try:
        proc = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              shell=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Fail("timeout") from None
    except (OSError, subprocess.SubprocessError):
        raise Fail("resource_read_error") from None
    try:
        out = proc.stdout.decode("utf-8")
        err = proc.stderr.decode("utf-8")
    except UnicodeDecodeError:
        raise Fail("resource_read_error") from None
    if proc.returncode not in (0, 2):
        raise Fail("resource_read_error")
    return proc.returncode, out, err


def _decode_field(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise Fail("source_unverified", 3)
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise Fail("source_unverified", 3) from None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Fail("source_unverified", 3) from None


def _projection(entry, lh_id, ssh, pg, keyfile, timeout):
    sql = SKILL_SQL
    out = _ssh_run(ssh, pg, keyfile, sql, [("obj_id", lh_id)], timeout)
    try:
        lines = [ln for ln in out.decode("utf-8").split("\n") if ln]
    except UnicodeDecodeError:
        raise Fail("source_unverified", 3) from None
    if len(lines) != 1:
        raise Fail("source_unverified", 3)
    if lines[0] == "MISSING":
        raise Fail("missing_evidence", 3)
    try:
        row = json.loads(lines[0], object_pairs_hook=_pairs)
    except (ValueError, Fail):
        raise Fail("source_unverified", 3) from None
    if not isinstance(row, dict) or set(row) != set(SKILL_FIELDS):
        raise Fail("source_unverified", 3)
    if not isinstance(row["id"], str) or row["id"] != lh_id:
        raise Fail("identity_difference", 3)
    resources = row["resources"]
    if not isinstance(resources, list) or not all(isinstance(p, str) for p in resources) \
            or len(set(resources)) != len(resources):
        raise Fail("source_unverified", 3)
    text = {"id": row["id"]}
    for key in ("name", "description", "identifier", "content"):
        text[key] = _decode_field(row[key], key)
    return text, resources


def _rel(path, source):
    prefix = source.rsplit("/", 1)[0] + "/"
    if not path.startswith(prefix):
        raise Fail("registry_invalid")
    rel = path[len(prefix):]
    if not REL_PATH_RE.match(rel) or ".." in rel or "//" in rel or rel.endswith("/"):
        raise Fail("registry_invalid")
    return rel


def main(argv=None):
    parser = _Parser(prog="lh-collect", add_help=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--object", action="append", required=True, dest="objects")
    parser.add_argument("--git-version", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--instance-ref", required=True)
    parser.add_argument("--source-basis", required=True)
    parser.add_argument("--total-timeout", type=int, default=180)
    err = None
    summary = {"schemaVersion": 1, "status": "error", "objects": [], "errors": [],
               "artifacts": [], "notCovered": [
                   "agent-evidence 源头 SQL 表列与身份绑定未核准",
                   "采集成功不表示与 Git 匹配",
               ]}
    deadline = None
    try:
        args = parser.parse_args(argv)
        if type(args.total_timeout) is not int or args.total_timeout <= 0:
            raise Fail("bad_args")
        if not HEX40_RE.match(args.git_version):
            raise Fail("bad_args")
        for value in (args.instance_ref, args.source_basis):
            if not value or any(ord(ch) < 0x20 for ch in value):
                raise Fail("bad_args")
        if not os.path.isabs(args.repo) or not os.path.isdir(args.repo):
            raise Fail("bad_args")
        if not os.path.isabs(args.out_dir) or os.path.lexists(args.out_dir):
            raise Fail("unsafe_path")
        parent = os.path.dirname(args.out_dir)
        if not os.path.isdir(parent) or os.path.islink(args.out_dir):
            raise Fail("unsafe_path")
        selected = list(dict.fromkeys(args.objects))
        if not selected:
            raise Fail("bad_args")
        registry = _registry(args.repo, args.git_version)
        plan = []
        for name in selected:
            entry = registry.get(name)
            if entry is None:
                raise Fail("registry_invalid")
            kind, lh_id = _classify(entry)
            plan.append((name, entry, kind, lh_id))
        ssh, pg = _target(sys.stdin.buffer.read())
        deadline = args.total_timeout
        # 未核准前提：Agent 实际表列/身份绑定缺证 → 读凭据前停（真实 rc3，不落空证据）。
        if any(kind == "agent" for _, _, kind, _ in plan):
            for name, _, kind, _ in plan:
                summary["objects"].append({
                    "object": name, "phase": "admission",
                    "status": "failed" if kind == "agent" else "not_run",
                    "code": "schema_unverified" if kind == "agent" else None,
                    "changed": False})
            summary["status"] = "incomplete"
            summary["errors"].append("schema_unverified")
            raise Fail("schema_unverified", 3)
        for name in SSH_SECRETS + API_SECRETS:
            _need(name)
        os.mkdir(args.out_dir, 0o700)
        os.chmod(args.out_dir, 0o700)
        started = _utc()
        obs_id = "obs-" + binascii.hexlify(os.urandom(8)).decode("ascii")
        keyroot, keyfile = _keyring()
        evidence = {"schemaVersion": 1, "observation": {
            "id": obs_id, "instanceRef": args.instance_ref,
            "sourceVersion": args.git_version, "startedAt": started,
            "finishedAt": started, "sourceBasis": args.source_basis}, "objects": []}
        projection = {"schemaVersion": 1, "observation": evidence["observation"],
                      "objects": []}
        failed = False
        try:
            for name, entry, kind, lh_id in plan:
                pre = _projection(entry, lh_id, ssh, pg, keyfile,
                                  min(60, deadline))
                text, actual = pre
                source = entry["source"]
                registered = [_rel(p, source) for p in entry.get("resources", [])]
                calls = []
                for rel in sorted(set(registered) & set(actual)):
                    rc, out, errout = _auth_call(args.repo, lh_id, rel, min(60, deadline))
                    calls.append({"observationId": obs_id, "instanceRef": args.instance_ref,
                                  "request": {"id": lh_id, "path": rel},
                                  "exitCode": rc, "stdout": out, "stderr": errout})
                evidence["objects"].append({
                    "object": name, "observationId": obs_id,
                    "instanceRef": args.instance_ref,
                    "projection": {"id": lh_id, "name": text["name"],
                                   "description": text["description"],
                                   "identifier": text["identifier"],
                                   "content": text["content"]},
                    "resourcePaths": sorted(actual), "calls": calls})
                projection["objects"].append({
                    "object": name, "id": lh_id, "name": text["name"],
                    "description": text["description"],
                    "identifier": text["identifier"], "content": text["content"],
                    "resources": sorted(actual)})
                summary["objects"].append({"object": name, "phase": "pre",
                                           "status": "collected", "code": None,
                                           "changed": False})
        finally:
            try:
                keyroot.close()
            except Fail:
                failed = True
                summary["objects"].append({"object": "-", "phase": "cleanup",
                                           "status": "failed",
                                           "code": "cleanup_failed", "changed": False})
        evidence["observation"]["finishedAt"] = _utc()
        projection["observation"] = evidence["observation"]
        _write_json(os.path.join(args.out_dir, "skill-evidence.json"), evidence)
        _write_json(os.path.join(args.out_dir, "projection-source.json"), projection)
        summary["artifacts"] = ["skill-evidence.json", "projection-source.json"]
        summary["status"] = "collected" if not failed else "incomplete"
        if failed:
            summary["errors"].append("cleanup_failed")
            err = Fail("cleanup_failed", 2)
    except Fail as exc:
        err = exc
        if not summary["errors"] or summary["errors"][-1] != exc.code:
            summary["errors"].append(exc.code)
        if summary["status"] == "error":
            summary["status"] = "incomplete" if exc.exit == 3 else "error"
    except Exception:
        err = Fail("internal_error")
        summary["errors"].append("internal_error")
        summary["status"] = "error"
    sys.stdout.write(json.dumps(summary, ensure_ascii=True) + "\n")
    if err is None:
        return 0
    sys.stderr.write(json.dumps({"ok": False, "error": err.code}) + "\n")
    return err.exit


def _write_json(path, doc):
    """600、排他创建、整份回读核对长度与结构。"""
    raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError:
        raise Fail("unsafe_path") from None
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)
    with open(path, "rb") as handle:
        back = handle.read()
    if back != raw:
        raise Fail("unsafe_path")


if __name__ == "__main__":
    sys.exit(main())

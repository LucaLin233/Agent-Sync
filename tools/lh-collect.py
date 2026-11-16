#!/usr/bin/env python3
"""LobeHub 窄采集：固定只读 SQL 投影 + auth-call 原 bytes，组装既有证据 schema。

用法（Minis/iSH 已审副本，仅标准库，`python3 -I -B`）：
  python3 -I -B tools/lh-collect.py --repo ABS --object ID [--object ID …] \
      --git-version <40位小写hex> --out-dir ABS --instance-ref LABEL --source-basis REF \
      [--total-timeout 180] < target.json

范围：只采集该提交登记里 `ends.lobehub.present=true` 的技能与 Agent。技能投影五字段与资源**实际完整键**，
资源正文经 tools/auth-call.py 的 skill-resource 逐路径读取，原 stdout/stderr/exitCode 原样入证；Agent 只按
登记 ID 取固定投影（id/user_id/workspace_id/system_role，`is_deleted IS NOT TRUE`），写入 `agent-evidence.json`，
不读默认配置、知识关联或凭据列。

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
import shlex
import signal
import subprocess
import sys
import time

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
# 每对象硬截止 D、清理保留 C=2 秒：业务只用 W=D-C，清理时间不挪用。
CLEANUP_RESERVE = 2.0
CALL_CAP = 60.0
ROOT_PARENT = "/tmp"
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
    "'id', id, 'name', name, 'identifier', identifier, "
    "'description_b64', encode(convert_to(description, 'UTF8'), 'base64'), "
    "'content_b64', encode(convert_to(content, 'UTF8'), 'base64'), "
    "'resource_keys', (SELECT coalesce(json_agg(k ORDER BY k), '[]'::json) "
    "FROM jsonb_object_keys(coalesce(resources, '{}'::jsonb)) AS k)"
    ")::text, 'MISSING') FROM agent_skills WHERE id = :'obj_id';\n"
    "COMMIT;\n"
)
SQL_KEYS = ("id", "name", "identifier", "description_b64", "content_b64", "resource_keys")
# Agent 固定只读投影：只取登记 ID 的对应有效行（is_deleted 可空，必须 IS NOT TRUE），不带当前用户/工作区。
AGENT_SQL = (
    "SET default_transaction_read_only = on;\n"
    "BEGIN READ ONLY;\n"
    "SELECT coalesce(json_build_object("
    "'id', id, 'user_id', user_id, 'workspace_id', workspace_id, "
    "'system_role_b64', encode(convert_to(system_role, 'UTF8'), 'base64')"
    ")::text, 'MISSING') FROM agents "
    "WHERE id = :'obj_id' AND is_deleted IS NOT TRUE;\n"
    "COMMIT;\n"
)
AGENT_KEYS = ("id", "user_id", "workspace_id", "system_role_b64")


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


class Cancelled(BaseException):
    """信号取消：只由外层显式映射为 timeout/rc2，不被 except Exception 吞掉。"""


_CANCEL = {"flag": False}
_ACTIVE = set()


def _check():
    if _CANCEL["flag"]:
        raise Cancelled()


def _notify(fd, doc):
    """单条固定小 JSON 记录写向继承的清理通知管道；失败只返回 False，不抛异常。"""
    if fd is None:
        return True
    data = (json.dumps(doc, ensure_ascii=True) + "\n").encode("ascii")
    try:
        off = 0
        while off < len(data):
            off += os.write(fd, data[off:])
    except OSError:
        return False
    return True


def _on_signal(signum, frame):
    """只保留取消标志并请求终止已登记的 SSH/auth-call；不在信号上下文抛异常。"""
    _CANCEL["flag"] = True
    for proc in list(_ACTIVE):
        try:
            proc.terminate()
        except OSError:
            pass


def _install_signals():
    for name in ("SIGTERM", "SIGINT"):
        number = getattr(signal, name, None)
        if number is not None:
            signal.signal(number, _on_signal)


def _spawn(argv, **kwargs):
    proc = subprocess.Popen(argv, **kwargs)
    _ACTIVE.add(proc)
    return proc


def _reap(proc, until):
    """有界收尾：terminate → 等待 → 必要时 kill；等待一律夹到 D，未回收不算已核。"""
    if proc.poll() is not None:
        _ACTIVE.discard(proc)
        return True
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=max(0.0, until - time.monotonic()))
        _ACTIVE.discard(proc)
        return True
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=max(0.0, until - time.monotonic()))
        _ACTIVE.discard(proc)
        return True
    except subprocess.TimeoutExpired:
        return False


def _stop_active(until):
    """返回是否全部回收；未回收的进程留在 _ACTIVE，不得据此声称已清。"""
    reaped = True
    for proc in list(_ACTIVE):
        if not _reap(proc, until):
            reaped = False
    return reaped


class Deadline:
    """每对象硬截止 D、工作截止 W=D-CLEANUP_RESERVE；业务取用一律只到 W。"""

    def __init__(self, hard):
        self.hard = hard
        self.work = hard - CLEANUP_RESERVE

    def left(self):
        remaining = self.work - time.monotonic()
        if remaining <= 0:
            raise Fail("timeout")
        return min(CALL_CAP, remaining)


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
    """含秘密临时物：ROOT_PARENT 下 mktemp -d 语义（700 根/600 文件），锚父 fd + nofollow 核身份。

    __init__ 只初始化状态；创建、登记身份与写钥由 create()/write() 在调用方 try/finally 内执行。
    """

    def __init__(self, notify_fd=None):
        self.notify_fd = notify_fd
        self.root = None
        self.name = None
        self.root_id = None
        self.made = None
        self.tmpfd = None
        self.closed = False
        self.residuals = []

    def create(self):
        """建根 → 同轴核身份 → 写钥前先向父通报确切根；通报失败就不写钥，直接 close。"""
        import tempfile
        try:
            self.root = tempfile.mkdtemp(prefix="lh-collect-", dir=ROOT_PARENT)
            self.tmpfd = _anchor(ROOT_PARENT)
        except OSError:
            raise Fail("unsafe_path") from None
        self.name = os.path.basename(self.root)
        fd = self.root_fd()
        try:
            self.root_id = self._id(fd)
        finally:
            os.close(fd)
        if not _notify(self.notify_fd, {"event": "key_root", "root": self.root}):
            self.close()
            raise Fail("internal_error")
        return self.root

    def _id(self, fd):
        """同一已开 FD 上 fstat 取完整身份（dev/ino/mode），不归一 dev、不混 stat。"""
        try:
            st = os.fstat(fd)
        except OSError:
            raise Fail("cleanup_failed") from None
        return (st.st_dev, st.st_ino, st.st_mode)

    def write(self, material):
        try:
            material = base64.b64decode(material, validate=True)
        except (binascii.Error, ValueError):
            self.close()
            raise Fail("missing_variable:SSH_PRIVATE_KEY_B64", 3) from None
        try:
            rfd = self.root_fd()
            try:
                fd = os.open("id", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=rfd)
                self.made = self._id(fd)
                off = 0
                while off < len(material):
                    off += os.write(fd, material[off:])
                os.fsync(fd)
            finally:
                os.close(rfd)
        except OSError:
            try:
                os.close(fd)
            except OSError:
                pass
            self.close()
            raise Fail("unsafe_path") from None
        os.close(fd)
        return os.path.join(self.root, "id")

    def root_fd(self):
        """从已锚定的父 fd 同轴重开根目录，nofollow 并核完整身份。"""
        try:
            fd = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY
                         | getattr(os, "O_NOFOLLOW", 0), dir_fd=self.tmpfd)
        except OSError:
            raise Fail("cleanup_failed") from None
        if self.root_id is not None and self._id(fd) != self.root_id:
            os.close(fd)
            raise Fail("cleanup_failed")
        return fd

    def close(self):
        """删除前重核根与文件身份；失败列本根残留并报 cleanup_failed，不删未知项。"""
        if self.closed:
            return
        ok = True
        if self.root is not None:
            try:
                self._remove()
            except (Fail, OSError):
                ok = False
                self.residuals = self._residuals()
        self.closed = True
        _notify(self.notify_fd, {"event": "cleanup", "residuals": self.residuals})
        if not ok:
            raise Fail("cleanup_failed")

    def _remove(self):
        try:
            rfd = self.root_fd()
        except Fail:
            if self.tmpfd is not None:
                os.close(self.tmpfd)
                self.tmpfd = None
            raise
        try:
            if self.made is not None:
                try:
                    fid = os.open("id", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=rfd)
                except OSError:
                    fid = None
                if fid is not None:
                    same = self._id(fid) == self.made
                    os.close(fid)
                    if not same:
                        raise Fail("cleanup_failed")
                    os.unlink("id", dir_fd=rfd)
            os.rmdir(self.name, dir_fd=self.tmpfd)
            self.made = None
        finally:
            os.close(rfd)
            if self.tmpfd is not None:
                os.close(self.tmpfd)
                self.tmpfd = None

    def _residuals(self):
        """只列本次登记的根与固定 id：删除/身份未核为 unverified，确定仍在为 remaining。"""
        status = "unverified"
        if self.root is not None and self.tmpfd is not None:
            try:
                fd = self.root_fd()
            except (Fail, OSError):
                fd = None
            if fd is not None:
                os.close(fd)
                status = "remaining"
        out = []
        if self.root is not None:
            out.append({"path": self.root, "status": status})
            if self.made is not None and status == "remaining":
                out.append({"path": os.path.join(self.root, "id"), "status": "remaining"})
        return out


def _anchor(path):
    """从 / 逐组件 nofollow 打开目录（O_DIRECTORY|O_NOFOLLOW），返回 fd。"""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    for comp in [c for c in path.split("/") if c]:
        nfd = os.open(comp, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                      dir_fd=fd)
        os.close(fd)
        fd = nfd
    return fd


def _env():
    """最小白名单：只沿用调用方的 PATH（用于 ssh）与 TMPDIR，不继承其余变量。"""
    env = dict(BASE_ENV)
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    if os.environ.get("TMPDIR"):
        env["TMPDIR"] = os.environ["TMPDIR"]
    return env


def _ssh_run(ssh, pg, keyfile, sql, variables, limits):
    """OpenSSH 只把 host 之后各参数用空格拼成一个远端命令串，故整段按 shlex.join 编成一条。"""
    remote = [
        "docker", "exec", "-i", pg["container"],
        "env", "-i", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PGPASSFILE=/dev/null", "PGOPTIONS=-c default_transaction_read_only=on",
        "PGCONNECT_TIMEOUT=20", "PGAPPNAME=lh-collect",
        "psql", "-w", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1",
        "-p", str(pg["port"]), "-U", pg["user"], "-d", pg["database"], "-f", "-",
    ]
    for name, value in variables:
        remote.append("-v")
        remote.append("%s=%s" % (name, value))
    argv = [
        "ssh", "-F", "none",
        "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=" + ssh["knownHostsFile"],
        "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
        "-o", "ConnectTimeout=10", "-p", str(ssh["port"]), "-i", keyfile,
        "--", "%s@%s" % (ssh["user"], ssh["host"]), shlex.join(remote),
    ]
    _check()
    try:
        proc = _spawn(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                      stderr=subprocess.DEVNULL, env=_env(), shell=False)
    except (OSError, subprocess.SubprocessError):
        raise Fail("source_unverified", 3) from None
    try:
        out, _ = proc.communicate(sql.encode("utf-8"), timeout=limits.left())
    except subprocess.TimeoutExpired:
        _reap(proc, limits.hard)
        _check()
        raise Fail("timeout") from None
    except (OSError, subprocess.SubprocessError):
        _reap(proc, limits.hard)
        raise Fail("source_unverified", 3) from None
    finally:
        _ACTIVE.discard(proc)
    _check()
    if proc.returncode != 0:
        raise Fail("source_unverified", 3)
    if len(out) > MAX_SQL_OUT:
        raise Fail("source_unverified", 3)
    return out


def _auth_call(repo, skill_id, path, limits):
    argv = [sys.executable or "python3", "-I", "-B",
            os.path.join(repo, "tools", "auth-call.py"),
            "skill-resource", "--id", skill_id, "--path", path]
    env = _env()
    for name in API_SECRETS:
        if os.environ.get(name):
            env[name] = os.environ[name]
    _check()
    try:
        proc = _spawn(argv, env=env, stdin=subprocess.DEVNULL,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    except (OSError, subprocess.SubprocessError):
        raise Fail("resource_read_error") from None
    try:
        out, err = proc.communicate(timeout=limits.left())
    except subprocess.TimeoutExpired:
        _reap(proc, limits.hard)
        _check()
        raise Fail("timeout") from None
    except (OSError, subprocess.SubprocessError):
        _reap(proc, limits.hard)
        raise Fail("resource_read_error") from None
    finally:
        _ACTIVE.discard(proc)
    _check()
    try:
        out = out.decode("utf-8")
        err = err.decode("utf-8")
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
    # 固定 SQL 契约：encode(...,'base64') 每 76 字节插一个换行，只允许这些换行。
    try:
        raw = base64.b64decode(value.replace("\n", ""), validate=True)
    except (binascii.Error, ValueError):
        raise Fail("source_unverified", 3) from None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Fail("source_unverified", 3) from None


def _agent_projection(entry, lh_id, ssh, pg, keyfile, limits):
    """固定投影：id 与身份列、system_role（null 与空串严格区分）。"""
    out = _ssh_run(ssh, pg, keyfile, AGENT_SQL, [("obj_id", lh_id)], limits)
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
    if not isinstance(row, dict) or set(row) != set(AGENT_KEYS):
        raise Fail("source_unverified", 3)
    if not isinstance(row["id"], str) or row["id"] != lh_id:
        raise Fail("identity_difference", 3)
    if not isinstance(row["user_id"], str) or not row["user_id"]:
        raise Fail("source_unverified", 3)
    if row["workspace_id"] is not None and not isinstance(row["workspace_id"], str):
        raise Fail("source_unverified", 3)
    return _decode_field(row["system_role_b64"], "system_role")


def _projection(entry, lh_id, ssh, pg, keyfile, limits):
    sql = SKILL_SQL
    out = _ssh_run(ssh, pg, keyfile, sql, [("obj_id", lh_id)], limits)
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
    if not isinstance(row, dict) or set(row) != set(SQL_KEYS):
        raise Fail("source_unverified", 3)
    if not isinstance(row["id"], str) or row["id"] != lh_id:
        raise Fail("identity_difference", 3)
    resources = row["resource_keys"]
    if not isinstance(resources, list) or not all(isinstance(p, str) for p in resources) \
            or len(set(resources)) != len(resources):
        raise Fail("source_unverified", 3)
    for key in ("name", "identifier"):
        if row[key] is not None and not isinstance(row[key], str):
            raise Fail("source_unverified", 3)
    text = {"id": row["id"], "name": row["name"], "identifier": row["identifier"],
            "description": _decode_field(row["description_b64"], "description"),
            "content": _decode_field(row["content_b64"], "content")}
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
    parser.add_argument("--source-version", required=True, dest="source_version")
    parser.add_argument("--total-timeout", type=int, default=180)
    parser.add_argument("--_parent-deadline", type=float, default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument("--_cleanup-fd", type=int, default=None, help=argparse.SUPPRESS)
    err = None
    summary = {"schemaVersion": 1, "status": "error", "objects": [], "errors": [],
               "artifacts": [], "cleanupResiduals": [], "notCovered": [
                   "Agent 现场有效 systemRole 与存储 system_role 的等价由负责人人工核实",
                   "采集成功不表示与 Git 匹配",
               ]}
    cleanup_fd = None
    keyroots = []
    try:
        args = parser.parse_args(argv)
        if type(args.total_timeout) is not int or args.total_timeout <= 0:
            raise Fail("bad_args")
        if args.total_timeout <= 2:
            raise Fail("timeout")
        if args._parent_deadline is not None and not (
                isinstance(args._parent_deadline, float) and args._parent_deadline > 0):
            raise Fail("bad_args")
        if args._cleanup_fd is not None:
            if args._cleanup_fd < 3:
                raise Fail("bad_args")
            try:
                os.fstat(args._cleanup_fd)
            except OSError:
                raise Fail("bad_args") from None
            cleanup_fd = args._cleanup_fd
        if not HEX40_RE.match(args.git_version):
            raise Fail("bad_args")
        for value in (args.instance_ref, args.source_basis, args.source_version):
            if not value or any(ord(ch) < 0x20 for ch in value):
                raise Fail("bad_args")
        if not os.path.isabs(args.repo) or not os.path.isdir(args.repo):
            raise Fail("bad_args")
        if not os.path.isabs(args.out_dir) or os.path.lexists(args.out_dir):
            raise Fail("unsafe_path")
        parent = os.path.dirname(args.out_dir)
        if not os.path.isdir(parent) or os.path.islink(args.out_dir):
            raise Fail("unsafe_path")
        selected = list(args.objects)
        if not selected or len(set(selected)) != len(selected):
            raise Fail("bad_args")
        _install_signals()
        if _git(args.repo, ["cat-file", "-t", args.git_version]).strip() != b"commit":
            raise Fail("source_unverified", 3)
        registry = _registry(args.repo, args.git_version)
        plan = []
        for name in selected:
            entry = registry.get(name)
            if entry is None:
                raise Fail("registry_invalid")
            kind, lh_id = _classify(entry)
            plan.append((name, entry, kind, lh_id))
        ssh, pg = _target(sys.stdin.buffer.read())
        for name in SSH_SECRETS:
            _need(name)
        if any(kind == "skill" for _, _, kind, _ in plan):
            for name in API_SECRETS:
                _need(name)
        os.mkdir(args.out_dir, 0o700)
        os.chmod(args.out_dir, 0o700)
        started = _utc()
        obs_id = "obs-" + binascii.hexlify(os.urandom(8)).decode("ascii")
        evidence = {"schemaVersion": 1, "observation": {
            "id": obs_id, "instanceRef": args.instance_ref,
            "sourceVersion": args.source_version, "startedAt": started,
            "finishedAt": started, "sourceBasis": args.source_basis}, "objects": []}
        projection = {"schemaVersion": 1, "observation": evidence["observation"],
                      "objects": []}
        agents = {"schemaVersion": 1, "observation": evidence["observation"], "objects": []}
        failed = False
        read_failed = False
        limits_last = None
        for name, entry, kind, lh_id in plan:
            # 每对象硬截止 D=now+T（父给定则取 min）；钥根与期限同域，不跨对象共享。
            hard = time.monotonic() + args.total_timeout
            if args._parent_deadline is not None:
                hard = min(hard, args._parent_deadline)
            limits = Deadline(hard)
            limits_last = limits
            _check()
            keyroot = KeyRoot(cleanup_fd)
            keyroots.append(keyroot)
            try:
                keyroot.create()
                _check()
                keyfile = keyroot.write(os.environ["SSH_PRIVATE_KEY_B64"])
                _check()
                if kind == "agent":
                    value = _agent_projection(entry, lh_id, ssh, pg, keyfile, limits)
                    agents["objects"].append({
                        "object": name, "observationId": obs_id,
                        "instanceRef": args.instance_ref, "id": lh_id,
                        "field": "systemRole", "value": value})
                    projection["objects"].append({
                        "object": name, "id": lh_id, "field": "systemRole",
                        "value": value, "resources": []})
                    summary["objects"].append({"object": name, "phase": "pre",
                                               "status": "collected", "code": None,
                                               "changed": False})
                    continue
                pre = _projection(entry, lh_id, ssh, pg, keyfile, limits)
                text, actual = pre
                source = entry["source"]
                registered = [_rel(p, source) for p in entry.get("resources", [])]
                calls = []
                for rel in sorted(set(registered) & set(actual)):
                    rc, out, errout = _auth_call(args.repo, lh_id, rel, limits)
                    calls.append({"observationId": obs_id, "instanceRef": args.instance_ref,
                                  "request": {"id": lh_id, "path": rel},
                                  "exitCode": rc, "stdout": out, "stderr": errout})
                failed_calls = [c for c in calls if c["exitCode"] == 2]
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
                summary["objects"].append({
                    "object": name, "phase": "pre",
                    "status": "failed" if failed_calls else "collected",
                    "code": "resource_read_error" if failed_calls else None,
                    "changed": False})
                if failed_calls:
                    read_failed = True
                    if "resource_read_error" not in summary["errors"]:
                        summary["errors"].append("resource_read_error")
            finally:
                # 同一路径收尾：先有界停止活动进程（未回收即未核），再关闭本对象钥根。
                stopped = _stop_active(limits.hard)
                try:
                    keyroot.close()
                except Fail:
                    failed = True
                    summary["cleanupResiduals"].extend(keyroot.residuals)
                    summary["objects"].append({"object": name, "phase": "cleanup",
                                               "status": "failed",
                                               "code": "cleanup_failed", "changed": False})
                    if "cleanup_failed" not in summary["errors"]:
                        summary["errors"].append("cleanup_failed")
                if not stopped:
                    failed = True
                    if keyroot.root is not None:
                        summary["cleanupResiduals"].append(
                            {"path": keyroot.root, "status": "unverified"})
                    summary["objects"].append({"object": name, "phase": "cleanup",
                                               "status": "failed",
                                               "code": "cleanup_failed", "changed": False})
                    if "cleanup_failed" not in summary["errors"]:
                        summary["errors"].append("cleanup_failed")
        evidence["observation"]["finishedAt"] = _utc()
        projection["observation"] = evidence["observation"]
        agents["observation"] = evidence["observation"]
        if limits_last is not None:
            limits_last.left()   # 落盘同样只用 W：耗尽即 timeout
        outfd = _anchor(args.out_dir)
        try:
            if evidence["objects"]:
                if limits_last is not None:
                    limits_last.left()
                _write_json(outfd, "skill-evidence.json", evidence)
                summary["artifacts"].append("skill-evidence.json")
            if agents["objects"]:
                if limits_last is not None:
                    limits_last.left()
                _write_json(outfd, "agent-evidence.json", agents)
                summary["artifacts"].append("agent-evidence.json")
            if limits_last is not None:
                limits_last.left()
            _write_json(outfd, "projection-source.json", projection)
            summary["artifacts"].append("projection-source.json")
        finally:
            os.close(outfd)
        summary["status"] = "collected" if not failed else "incomplete"
        if failed:
            if "cleanup_failed" not in summary["errors"]:
                summary["errors"].append("cleanup_failed")
            err = Fail("cleanup_failed", 2)
        elif read_failed:
            summary["status"] = "error"
            err = Fail("resource_read_error", 2)
    except Cancelled:
        err = Fail("timeout", 2)
        if "timeout" not in summary["errors"]:
            summary["errors"].append("timeout")
        summary["status"] = "error"
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
    if cleanup_fd is not None and not any(k.closed for k in keyroots):
        # 未创建钥根的失败出口：回报空残留，父仍能区分「已核无残留」与「缺确认」。
        _notify(cleanup_fd, {"event": "cleanup", "residuals": []})
    sys.stdout.write(json.dumps(summary, ensure_ascii=True) + "\n")
    if err is None:
        return 0
    sys.stderr.write(json.dumps({"ok": False, "error": err.code}) + "\n")
    return err.exit


def _write_json(dir_fd, name, doc):
    """600、在已锚定的 out-dir fd 上排他创建；同一 fd 回读判等（不按路径重开）。"""
    raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
    except OSError:
        raise Fail("unsafe_path") from None
    try:
        off = 0
        while off < len(raw):
            off += os.write(fd, raw[off:])
        os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        back = b""
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            back += chunk
    finally:
        os.close(fd)
    if back != raw:
        raise Fail("unsafe_path")


if __name__ == "__main__":
    sys.exit(main())

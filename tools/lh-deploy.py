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
import importlib.util
import json
import os
import re
import select
import signal
import stat
import subprocess
import sys
import time
import urllib.parse

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
# 每对象硬截止 D、清理保留 C=2 秒：业务只用 W=D-C，留给子进程清理与回报。
CLEANUP_RESERVE = 2.0


class Fail(Exception):
    def __init__(self, code, exit, phase="admission", object_name=None, changed=False):
        super().__init__(code)
        self.code = code
        self.exit = exit
        self.phase = phase
        self.object_name = object_name
        self.changed = changed
        self.residuals = []


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


class Deadline:
    """每对象硬截止 D、工作截止 W=D-CLEANUP_RESERVE；业务取用一律只到 W。"""

    def __init__(self, hard):
        self.hard = hard
        self.work = hard - CLEANUP_RESERVE

    def left(self):
        remain = self.work - time.monotonic()
        if remain <= 0:
            raise Fail("timeout", 2, "cleanup", changed="unknown")
        return remain


def _utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(repo, args, data=None, timeout=60):
    extra = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
    try:
        proc = subprocess.run(
            ["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-C", repo] + args,
            env=dict(GIT_ENV, PATH=os.environ.get("PATH", GIT_ENV["PATH"])),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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


def _outfd(path):
    """从 / 逐组件 nofollow 锚定已创建的 out 根。"""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    try:
        for component in (part for part in path.split("/") if part):
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY
                              | getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _write_raw(dir_fd, name, data, limits):
    """排他写后在同一 FD 全文回读判等；写读循环共用同一工作期限 W。"""
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
    except OSError:
        raise Fail("unsafe_path", 2) from None
    try:
        off = 0
        while off < len(data):
            limits.left()
            off += os.write(fd, data[off:])
        limits.left()
        os.fsync(fd)
        limits.left()
        os.lseek(fd, 0, os.SEEK_SET)
        back = b""
        while True:
            limits.left()
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            back += chunk
    finally:
        os.close(fd)
    limits.left()
    if back != data:
        raise Fail("unsafe_path", 2)


def _read_evidence(path):
    """out 根 FD → 子目录 FD → O_NOFOLLOW 叶 FD，在同一 FD 读全文（不跟链、不先开再查）。"""
    parent = os.path.dirname(path)
    try:
        rfd = _outfd(os.path.dirname(parent))
    except OSError:
        raise Fail("unsafe_path", 2) from None
    try:
        try:
            dfd = os.open(os.path.basename(parent), os.O_RDONLY | os.O_DIRECTORY
                          | getattr(os, "O_NOFOLLOW", 0), dir_fd=rfd)
        except OSError:
            raise Fail("unsafe_path", 2) from None
    finally:
        os.close(rfd)
    try:
        try:
            fd = os.open(os.path.basename(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                         dir_fd=dfd)
        except OSError:
            raise Fail("unsafe_path", 2) from None
    finally:
        os.close(dfd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Fail("unsafe_path", 2)
        raw = b""
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            raw += chunk
    finally:
        os.close(fd)
    return raw


def _agent_value(out_dir, name, lh_id):
    """严格核 agent-evidence.json：唯一对象、ID/field/观察关联正确；value 为 null 或 str。"""
    path = os.path.join(out_dir, "agent-evidence.json")
    try:
        doc = json.loads(_read_evidence(path).decode("utf-8"))
        if doc.get("schemaVersion") != 1:
            raise ValueError
        obs = doc["observation"]
        obs_id, inst = obs["id"], obs["instanceRef"]
        objects = doc["objects"]
    except (ValueError, UnicodeError, KeyError, TypeError):
        raise Fail("source_unverified", 3) from None
    if not isinstance(objects, list) or len(objects) != 1:
        raise Fail("source_unverified", 3)
    item = objects[0]
    if not isinstance(item, dict) or set(item) != {"object", "observationId", "instanceRef",
                                                  "id", "field", "value"}:
        raise Fail("source_unverified", 3)
    if item["object"] != name or item["id"] != lh_id or item["field"] != "systemRole" \
            or item["observationId"] != obs_id or item["instanceRef"] != inst \
            or not isinstance(obs_id, str) or not isinstance(inst, str):
        raise Fail("source_unverified", 3)
    value = item["value"]
    if value is not None and not isinstance(value, str):
        raise Fail("source_unverified", 3)
    return value


def _agent_bytes(value):
    return None if value is None else value.encode("utf-8")


def _write_artifact(path, name, data, limits):
    """在已锚定的 out-dir fd 上排他写，写完关闭 fd（不按路径重开）。"""
    fd = _outfd(path)
    try:
        _write_raw(fd, name, data, limits)
    finally:
        os.close(fd)


def _load_body():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("lh_body", os.path.join(here, "body_contract.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _body_bytes(repo, version, path, limits):
    body = _load_body()
    proc = _git(repo, ["cat-file", "blob", "%s:%s" % (version, path)],
                timeout=limits.left())
    if proc.returncode != 0:
        raise Fail("source_unverified", 3)
    try:
        return body.body_bytes(proc.stdout)
    except body.ContractError:
        raise Fail("source_unverified", 3) from None


def _tail_lf_only(verify_json, evidence_path, expected):
    """verify 原 JSON：只允许 content 一项差异（身份/元数据/资源/错误必须为空）。"""
    try:
        doc = json.loads(verify_json.decode("utf-8"))
        entry = doc["objects"][0]
    except (ValueError, UnicodeError, KeyError, IndexError, TypeError):
        return False
    if entry.get("differences") != ["content"]:
        return False
    if entry.get("errors") or entry.get("missingEvidence"):
        return False
    paths = entry.get("resourcePaths") or {}
    if paths.get("missing") or paths.get("extra"):
        return False
    try:
        ev = json.loads(_read_evidence(evidence_path).decode("utf-8"))
        content = ev["objects"][0]["projection"]["content"]
        observed = content.encode("utf-8")
    except Fail:
        raise
    except (ValueError, UnicodeError, KeyError, IndexError, TypeError, AttributeError):
        return False
    return isinstance(content, str) and expected.endswith(b"\n") and observed == expected[:-1]


def _install_source(entry, merged, timeout):
    """登记 installSource 必须是公开 repo 的单段分支子目录，且该分支 HEAD 等于 merged。"""
    url = entry.get("installSource")
    source = entry.get("source") or ""
    if not isinstance(url, str) or not url:
        raise Fail("missing_evidence", 3)
    parts = urllib.parse.urlsplit(url)
    segs = [seg for seg in parts.path.split("/") if seg]
    if parts.scheme != "https" or parts.netloc != "github.com" or parts.query or parts.fragment \
            or len(segs) < 5 or segs[2] != "tree":
        raise Fail("registry_invalid", 3)
    owner, repo_name, branch = segs[0], segs[1], segs[3]
    subdir = "/".join(segs[4:])
    for token in (owner, repo_name, branch):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", token):
            raise Fail("registry_invalid", 3)
    if source.rsplit("/", 1)[0] != subdir:
        raise Fail("registry_invalid", 3)
    proc = _git(os.getcwd(), ["ls-remote", "https://github.com/%s/%s" % (owner, repo_name),
                              "refs/heads/" + branch], timeout=timeout)
    if proc.returncode != 0:
        raise Fail("source_unverified", 3)
    rows = [ln.split("\t") for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln]
    if len(rows) != 1 or rows[0][1] != "refs/heads/" + branch or rows[0][0] != merged:
        raise Fail("branch_changed", 3)
    return url


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


SECRET_NAMES = ("SSH_PRIVATE_KEY_B64", "LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY")


def _cli_env(api_env, home):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C.UTF-8",
           "HOME": home, "XDG_CONFIG_HOME": home, "TERM": "dumb"}
    for name in ("LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY"):
        if api_env.get(name):
            env[name] = api_env[name]
    return env


def _collect_env():
    env = _env()
    for secret in SECRET_NAMES:
        value = os.environ.get(secret)
        if value:
            env[secret] = value
    return env


def _signal_group(proc, number):
    """只终止本次 start_new_session 独占的进程组；失败再退到单进程信号。"""
    try:
        os.killpg(proc.pid, number)
    except OSError:
        try:
            proc.send_signal(number)
        except OSError:
            pass


def _drain(fd, until):
    """有截止读取：先取已排队字节；仅当暂无数据且 D 未到时等剩余量，EOF 即止。"""
    os.set_blocking(fd, False)
    chunks = []
    while True:
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            chunk = None
        except OSError:
            break
        if chunk == b"":
            break                      # 写端全关
        if chunk:
            chunks.append(chunk)
            continue
        remaining = until - time.monotonic()
        if remaining <= 0:
            break                      # 到 D 且暂无数据：立即返回已收内容
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            break
    return b"".join(chunks)


def _collect(repo, name, version, out_dir, args, target_raw, phase, limits):
    """真实子进程：过 W 先 SIGTERM 等子清理至 D，仍不退才强杀本组；缺确认不报已清。"""
    read_fd, write_fd = os.pipe()
    argv = [sys.executable or "python3", "-I", "-B",
            os.path.join(repo, "tools", "lh-collect.py"),
            "--repo", repo, "--object", name, "--git-version", version,
            "--out-dir", out_dir, "--instance-ref", args.instance_ref,
            "--source-basis", args.source_basis,
            "--source-version", args.source_version,
            "--total-timeout", str(args.total_timeout),
            "--_parent-deadline", repr(float(limits.hard)),
            "--_cleanup-fd", str(write_fd)]
    try:
        if limits.work - time.monotonic() <= 0:
            raise Fail("timeout", 2, phase)
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, env=_collect_env(),
                                    pass_fds=(write_fd,), start_new_session=True,
                                    shell=False)
        except (OSError, subprocess.SubprocessError):
            raise Fail("cli_error", 2, phase) from None
        finally:
            os.close(write_fd)
            write_fd = None
        try:
            proc.stdin.write(target_raw)
            proc.stdin.close()
        except OSError:
            pass
        terminated = False
        killed = False
        unreaped = False
        try:
            proc.wait(timeout=max(0.0, limits.work - time.monotonic()))
        except subprocess.TimeoutExpired:
            terminated = True
            _signal_group(proc, signal.SIGTERM)
            try:
                proc.wait(timeout=max(0.0, limits.hard - time.monotonic()))
            except subprocess.TimeoutExpired:
                killed = True
                _signal_group(proc, signal.SIGKILL)
                try:
                    proc.wait(timeout=max(0.0, limits.hard - time.monotonic()))
                except subprocess.TimeoutExpired:
                    unreaped = True
        buf = _drain(read_fd, limits.hard)
    finally:
        os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)
    root = None
    residuals = []
    confirmed = False
    for line in buf.decode("ascii", "replace").splitlines():
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if not isinstance(doc, dict):
            continue
        if doc.get("event") == "key_root" and isinstance(doc.get("root"), str):
            root = doc["root"]
        elif doc.get("event") == "cleanup" and isinstance(doc.get("residuals"), list):
            confirmed = True
            residuals = [item for item in doc["residuals"]
                         if isinstance(item, dict) and isinstance(item.get("path"), str)
                         and item.get("status") in ("remaining", "unverified")]
    if not confirmed and root is not None:
        # 缺 cleanup 确认（如强杀）：只按先前根记录列根与固定 id，不扫描、不猜名、不补删。
        residuals = [{"path": root, "status": "unverified"},
                     {"path": os.path.join(root, "id"), "status": "unverified"}]
    if not confirmed or unreaped or terminated or killed or proc.returncode != 0 \
            or residuals:
        if terminated or killed or unreaped:
            code, exit_code = "timeout", 2
        elif proc.returncode == 3:
            code, exit_code = "missing_evidence", 3
        else:
            code, exit_code = "cli_error", 2
        if not confirmed or unreaped or residuals:
            code, exit_code = "cleanup_failed", 2
        exc = Fail(code, exit_code, phase)
        exc.residuals = residuals
        raise exc
    return out_dir


def _verify(repo, name, version, evidence, args, phase, timeout):
    argv = [sys.executable or "python3", "-I", "-B",
            os.path.join(repo, "tools", "lh-verify.py"), "--repo", repo,
            "--git-version", version, "--object", name, "--evidence", evidence]
    try:
        proc = subprocess.run(argv, env=_env(), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              shell=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Fail("timeout", 2, phase) from None
    except (OSError, subprocess.SubprocessError):
        raise Fail("cli_error", 2, phase) from None
    if proc.returncode in (0, 1):
        return proc.returncode, proc.stdout
    if proc.returncode == 3:
        raise Fail("missing_evidence", 3, phase)
    raise Fail("cli_error", 2, phase)


def _cli(env_extra, argv, timeout, phase):
    home = os.path.join(os.path.dirname(HOME_HOLDER[0]), "cli-home")
    os.makedirs(home, mode=0o700, exist_ok=True)
    return _run(argv, _cli_env(env_extra, home), timeout, phase)


HOME_HOLDER = ["/"]


def main(argv=None):
    summary = {"schemaVersion": 1, "status": "failed", "objects": [], "errors": [],
               "artifacts": [], "cleanupResiduals": [], "notCovered": [
                   "无平台 CAS：不保证不存在外部并发",
                   "Agent 现场有效 systemRole 与存储 system_role 的等价由负责人人工核实",
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
        parser.add_argument("--source-version", required=True, dest="source_version")
        parser.add_argument("--total-timeout", type=int, default=180)
        args = parser.parse_args(argv)
        if type(args.total_timeout) is not int or args.total_timeout <= 0:
            raise Fail("bad_args", 2)
        if args.total_timeout <= 2:
            raise Fail("timeout", 2)
        for sha in (args.base, args.merged):
            if not isinstance(sha, str) or not HEX40_RE.match(sha):
                raise Fail("bad_args", 2)
        for value in (args.instance_ref, args.source_basis, args.source_version):
            if not value or any(ord(ch) < 0x20 for ch in value):
                raise Fail("bad_args", 2)
        if not os.path.isabs(args.repo) or not os.path.isdir(args.repo):
            raise Fail("bad_args", 2)
        if not os.path.isabs(args.out_dir) or os.path.lexists(args.out_dir) \
                or not os.path.isdir(os.path.dirname(args.out_dir)):
            raise Fail("unsafe_path", 2)
        selected = list(args.objects)
        if not selected or len(set(selected)) != len(selected):
            raise Fail("bad_args", 2)
        target_raw = sys.stdin.buffer.read()
        _target(target_raw)  # 只校验，不回显、不落盘
        for version in (args.base, args.merged):
            if _git(args.repo, ["cat-file", "-t", version]).stdout.strip() != b"commit":
                raise Fail("source_unverified", 3)
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
        # 官方写依赖本次非空 API-key 短路：逐名核，缺者零写退出（standalone collect 仍只需 SSH）。
        for name in ("LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY"):
            if not os.environ.get(name):
                raise Fail("missing_variable:" + name, 3)
        installs = {}
        for name, old, new, kind, lh_id in plan:
            if kind == "skill":
                installs[name] = _install_source(new, args.merged, min(60, args.total_timeout))
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
        HOME_HOLDER[0] = os.path.join(args.out_dir, "cli-home")
        api_env = {name: os.environ[name]
                   for name in ("LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY")}
        stop = False
        for index, (name, old, new, kind, lh_id) in enumerate(plan):
            entry = {"object": name, "phase": "admission", "status": "not_run",
                     "code": None, "changed": False}
            summary["objects"].append(entry)
            if stop:
                continue
            limits = Deadline(time.monotonic() + args.total_timeout)

            def left():
                return limits.left()

            wrote = False
            try:
                pre_dir = os.path.join(args.out_dir, "pre-%d" % index)
                _collect(args.repo, name, args.base, pre_dir, args, target_raw, "pre",
                         limits)
                if kind == "agent":
                    value = _agent_value(pre_dir, name, lh_id)
                    expected = _body_bytes(args.repo, args.base, old["source"], limits)
                    if _agent_bytes(value) != expected:
                        raise Fail("pre_difference", 1, "pre")
                    entry.update(phase="write", status="running")
                    wrote = True
                    entry["changed"] = "unknown"
                    cfg = os.path.join(args.out_dir, "agent-%d-config.json" % index)
                    left()
                    _write_artifact(args.out_dir, os.path.basename(cfg),
                                    (json.dumps({"systemRole": _body_bytes(
                                        args.repo, args.merged, new["source"],
                                        limits).decode("utf-8")},
                                        ensure_ascii=False) + "\n").encode("utf-8"), limits)
                    rc = _cli(api_env, ["lh", "agent", "edit", lh_id,
                                        "--config-file", cfg], left(), "write")
                    if rc != 0:
                        raise Fail("cli_error", 2, "write", changed="unknown")
                    post_dir = os.path.join(args.out_dir, "post-%d" % index)
                    _collect(args.repo, name, args.merged, post_dir, args, target_raw,
                             "post", limits)
                    got = _agent_value(post_dir, name, lh_id)
                    want = _body_bytes(args.repo, args.merged, new["source"], limits)
                    if _agent_bytes(got) != want:
                        raise Fail("post_difference", 1, "post", changed="unknown")
                    left()
                    entry.update(phase="post", status="completed", code=None, changed=True)
                    summary["artifacts"] += ["pre-%d/agent-evidence.json" % index,
                                             "post-%d/agent-evidence.json" % index,
                                             "agent-%d-config.json" % index]
                    continue
                vrc, vout = _verify(args.repo, name, args.base,
                                    os.path.join(pre_dir, "skill-evidence.json"),
                                    args, "pre", left())
                left()
                _write_artifact(args.out_dir, "verify-pre-%d.json" % index, vout, limits)
                if vrc != 0:
                    raise Fail("pre_difference", 1, "pre")
                entry.update(phase="write", status="running")
                wrote = True
                entry["changed"] = "unknown"
                rc = _cli(api_env, ["lh", "skill", "install", installs[name]], left(), "write")
                if rc != 0:
                    raise Fail("cli_error", 2, "write", changed="unknown")
                if kind == "skill":
                    _install_source(new, args.merged, left())
                post_dir = os.path.join(args.out_dir, "post-%d" % index)
                _collect(args.repo, name, args.merged, post_dir, args, target_raw, "post", limits)
                vrc, vout = _verify(args.repo, name, args.merged,
                                    os.path.join(post_dir, "skill-evidence.json"),
                                    args, "post", left())
                left()
                _write_artifact(args.out_dir, "verify-post-%d.json" % index, vout, limits)
                if vrc != 0:
                    # 规格 6 唯一纠正例外：仅当 verify 原 JSON 的差异恰为 content，
                    # 且现场 content 恰等于期望正文 + 一个尾 LF，才以 argv 原样补一次全文。
                    expected = _body_bytes(args.repo, args.merged, new["source"], limits)
                    if kind == "skill" and _tail_lf_only(
                            vout, os.path.join(post_dir, "skill-evidence.json"), expected):
                        try:
                            arg = os.fsdecode(expected)
                        except (UnicodeError, ValueError):
                            raise Fail("post_difference", 1, "post", changed="unknown") from None
                        if arg.encode("utf-8", "surrogateescape") != expected:
                            raise Fail("post_difference", 1, "post", changed="unknown")
                        rc2 = _cli(api_env, ["lh", "skill", "edit", lh_id, "-c", arg],
                                   left(), "post")
                        if rc2 != 0:
                            raise Fail("cli_error", 2, "post", changed="unknown")
                        post2 = os.path.join(args.out_dir, "post-%d-fix" % index)
                        _collect(args.repo, name, args.merged, post2, args, target_raw,
                                 "post", limits)
                        vrc, vout = _verify(args.repo, name, args.merged,
                                            os.path.join(post2, "skill-evidence.json"),
                                            args, "post", left())
                        _write_artifact(args.out_dir, "verify-post-%d-fix.json" % index, vout, limits)
                        if vrc != 0:
                            raise Fail("post_difference", 1, "post", changed="unknown")
                    else:
                        raise Fail("post_difference", 1, "post", changed="unknown")
                left()
                entry.update(phase="post", status="completed", code=None, changed=True)
                summary["artifacts"] += ["pre-%d/skill-evidence.json" % index,
                                         "post-%d/skill-evidence.json" % index,
                                         "verify-pre-%d.json" % index,
                                         "verify-post-%d.json" % index]
            except Fail as exc:
                summary["cleanupResiduals"].extend(exc.residuals)
                if wrote and not exc.changed:
                    exc.changed = "unknown"
                entry.update(phase=exc.phase, status="failed", code=exc.code,
                             changed=exc.changed if exc.changed else entry.get("changed", False))
                summary["errors"].append(exc.code)
                stop = True
                rank = {2: 3, 3: 2, 1: 1, 0: 0}
                if err is None or rank.get(exc.exit, 0) > rank.get(err.exit, 0):
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
        summary["cleanupResiduals"].extend(exc.residuals)
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

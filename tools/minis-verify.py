#!/usr/bin/env python3
"""Minis 本端只读验收：所选登记对象 ↔ 同一提交的仓库原字节与生效字段安全投影。

用法（Minis/iSH 已审副本，仅标准库）：
  python3 -I -B tools/minis-verify.py --repo PATH --git-version <40位小写hex> \
      --object ID [--object ID ...] [--root /] [--projection FILE]

只核：同提交登记（tools/sync-targets.json）、Git 类型/mode、目标文件经「逐级同父单组件安全 open
＋真正重新 open 同名组件、两个仍存活 fd 的 fstat(dev,ino,S_IFMT) 全 tuple 绑定」的身份、
技能包集合、所有者执行位、SOUL 正文（body_contract.body_bytes）、子代理有限尾 LF 口径，
以及调用方提供的生效字段安全投影的结构/关联/字节。

不核：技能 App 登记、启用与实际加载、SOUL frontmatter、其他 POSIX 权限位、投影来源与记录真实性、
非原子快照（并发替换与 ABA）。--root 非 / 只表示重定位文件视图，不是真实 Minis 已验收。

退出码：0 匹配 / 1 确证差异 / 2 参数、格式、执行或输入错误 / 3 缺证或不可验证；并存按 2>3>1>0。
固定码见 CODES；stdout 只有一份 JSON，stderr 不外泄异常；不采集配置、不联网、不重试、不修复、不改权限。
"""
import argparse
import datetime
import errno
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys

HEX40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
TIME_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")

MAX_FIELD = 2000000          # SOUL 文件与投影输入的单次读取上限
MAX_ENTRIES = 10000          # 单包枚举上限
MAX_DEPTH = 64
MAX_PATH_BYTES = 1000000

CODES = {
    "file_missing": ("difference", 1), "file_type": ("difference", 1),
    "file_bytes": ("difference", 1), "file_exec": ("difference", 1),
    "file_contract": ("difference", 1), "package_set": ("difference", 1),
    "field_value": ("difference", 1),
    "bad_args": ("error", 2), "bad_json": ("error", 2), "bad_shape": ("error", 2),
    "unknown_key": ("error", 2), "duplicate_key": ("error", 2),
    "duplicate_item": ("error", 2), "unselected_object": ("error", 2),
    "field_binding": ("error", 2), "git_error": ("error", 2),
    "unsupported_git_mode": ("error", 2), "expected_contract_error": ("error", 2),
    "internal_error": ("error", 2),
    "missing_projection": ("missing_evidence", 3), "missing_field": ("missing_evidence", 3),
    "missing_object": ("missing_evidence", 3), "identity_unverifiable": ("missing_evidence", 3),
    "unsafe_path": ("missing_evidence", 3), "not_readable": ("missing_evidence", 3),
    "changed_during_read": ("missing_evidence", 3), "enumeration_limit": ("missing_evidence", 3),
    "unsupported_runtime": ("missing_evidence", 3),
}

GIT_ENV = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "HOME": os.devnull,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_ASKPASS": "/bin/false",
    "LC_ALL": "C",
}

HOOK = None    # 仅供测试的可控接缝：HOOK(stage, name)，默认不启用


class Reject(Exception):
    """固定码；class/退出级由 CODES 决定。"""

    def __init__(self, code, path=None):
        super().__init__(code)
        self.code = code
        self.path = path


class Report:
    def __init__(self):
        self.checks = []
        self.issues = []
        self.not_covered = []

    def issue(self, code, obj=None, path=None):
        cls = CODES[code][0]
        item = {"class": cls, "code": code, "object": obj, "path": path}
        if item not in self.issues:
            self.issues.append(item)
        return cls

    def check(self, obj, item, status):
        self.checks.append({"object": obj, "item": item, "status": status})

    def worst(self):
        rank = 0
        status = "match"
        for issue in self.issues:
            cls = issue["class"]
            if cls == "error":
                return 2, "error"
            if cls == "missing_evidence" and rank < 3:
                rank, status = 3, "incomplete"
            elif cls == "difference" and rank < 1:
                rank, status = 1, "different"
        return rank, status


def _load_body():
    """按工具自身可信目录加载同一提交的正文契约：不改 sys.path、不依赖 cwd。"""
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "minis_body_contract", os.path.join(here, "body_contract.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _abs_parts(path, code):
    if not isinstance(path, str) or not path.startswith("/") or "\0" in path:
        raise Reject(code)
    if path == "/":
        return []
    parts = path[1:].split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise Reject(code)
    return parts


def _tuple(st):
    return (st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode))


def _meta(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _dir_err(exc, missing_code):
    if exc.errno in (errno.ENOENT,):
        return Reject(missing_code)
    if exc.errno in (errno.ELOOP, errno.ENOTDIR):
        return Reject("unsafe_path")
    if exc.errno in (errno.EACCES, errno.EPERM):
        return Reject("not_readable")
    return Reject("unsupported_runtime")


DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class Fence:
    """从 / 起逐组件同父安全 open＋真正重 open 的双存活 fd 全 tuple 绑定；保留祖先至收尾。"""

    def __init__(self, parts, missing_code="unsafe_path"):
        self.links = []
        self.missing_code = missing_code
        try:
            self.fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        except OSError:
            raise Reject("unsupported_runtime") from None
        try:
            for part in parts:
                self.push(part)
        except Reject:
            self.close()
            raise

    def push(self, comp):
        if comp in ("", ".", "..") or "/" in comp or "\0" in comp:
            raise Reject("unsafe_path")
        try:
            fd = os.open(comp, DIR_FLAGS, dir_fd=self.fd)
        except OSError as exc:
            raise _dir_err(exc, self.missing_code) from None
        try:
            fd2 = os.open(comp, DIR_FLAGS, dir_fd=self.fd)
        except OSError as exc:
            os.close(fd)
            raise _dir_err(exc, self.missing_code) from None
        try:
            same = _tuple(os.fstat(fd)) == _tuple(os.fstat(fd2))
        except OSError:
            raise Reject("unsupported_runtime") from None
        finally:
            os.close(fd2)
        if not same:
            os.close(fd)
            raise Reject("identity_unverifiable")
        self.links.append((self.fd, comp, fd))
        self.fd = fd

    def pop(self):
        dfd, _comp, fd = self.links.pop()
        os.close(fd)
        self.fd = dfd

    def recheck(self):
        """操作后逐祖先同父重开同名组件，与原持有 fd 比全 tuple。"""
        for dfd, comp, fd in reversed(self.links):
            try:
                fd2 = os.open(comp, DIR_FLAGS, dir_fd=dfd)
            except OSError:
                raise Reject("identity_unverifiable") from None
            try:
                if _tuple(os.fstat(fd2)) != _tuple(os.fstat(fd)):
                    raise Reject("identity_unverifiable")
            finally:
                os.close(fd2)

    def close(self):
        for _dfd, _comp, fd in self.links:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.close(self.links[0][0] if self.links else self.fd)
        except OSError:
            pass
        self.links = []


def _seam(stage, name):
    if HOOK is not None:
        HOOK(stage, name)


def _reopen_same(dfd, name, fd):
    """读后从原父 fd 真正重开同名文件，两个仍存活 fd 比全 tuple。"""
    try:
        fd2 = os.open(name, FILE_FLAGS, dir_fd=dfd)
    except OSError:
        return False
    try:
        return _tuple(os.fstat(fd2)) == _tuple(os.fstat(fd))
    finally:
        os.close(fd2)


def _member(dfd, name, rep, obj, rel, expected=None):
    """安全读取一个普通文件；返回 (bytes|None, cls|None)，已记 issue。

    expected 为 None 时按 MAX_FIELD 有界读取（超限不可验证）；否则读 len(expected)+1 检超长。
    """
    def bad(code):
        return None, rep.issue(code, obj, rel)

    try:
        st0 = os.stat(name, dir_fd=dfd, follow_symlinks=False)
    except FileNotFoundError:
        return bad("file_missing")
    except OSError:
        return bad("not_readable")
    if stat.S_ISLNK(st0.st_mode):
        rep.issue("file_type", obj, rel)
        rep.issue("unsafe_path", obj, rel)
        return None, "difference"
    if not stat.S_ISREG(st0.st_mode):
        return bad("file_type")
    try:
        fd = os.open(name, FILE_FLAGS, dir_fd=dfd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            rep.issue("file_type", obj, rel)
            rep.issue("unsafe_path", obj, rel)
            return None, "difference"
        return bad("not_readable")
    try:
        try:
            st1 = os.fstat(fd)
        except OSError:
            return bad("not_readable")
        if not stat.S_ISREG(st1.st_mode):
            return bad("file_type")
        cap = MAX_FIELD if expected is None else len(expected)
        chunks, size = [], 0
        try:
            while size <= cap:
                block = os.read(fd, min(65536, cap + 1 - size))
                if not block:
                    break
                chunks.append(block)
                size += len(block)
            _seam("read", name)
            st2 = os.fstat(fd)
        except OSError:
            return bad("not_readable")
        data = b"".join(chunks)
        if _meta(st1) != _meta(st2):
            return bad("changed_during_read")
        if not _reopen_same(dfd, name, fd):
            return bad("identity_unverifiable")
        if expected is None:
            if size > MAX_FIELD:
                return bad("not_readable")
        else:
            if size > len(expected):
                return bad("file_bytes")
            if data != expected:
                return bad("file_bytes")
        return data, None
    finally:
        os.close(fd)


def _exec_status(dfd, name, want, rep, obj, rel):
    """属主执行位（Git 100644/100755 的有限映射）；只取元数据，不打开文件。"""
    try:
        st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
    except OSError:
        return "not_checked"
    if not stat.S_ISREG(st.st_mode):
        return "not_checked"
    if bool(st.st_mode & stat.S_IXUSR) == want:
        return "match"
    rep.issue("file_exec", obj, rel)
    return "different"


def _read_input(path):
    """调用方投影输入：有界读取，不施加仓库目录身份原语。"""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        raise Reject("not_readable") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Reject("not_readable")
        chunks, size = [], 0
        while size <= MAX_FIELD:
            block = os.read(fd, 65536)
            if not block:
                break
            chunks.append(block)
            size += len(block)
        if size > MAX_FIELD:
            raise Reject("not_readable")
        return b"".join(chunks)
    except OSError:
        raise Reject("not_readable") from None
    finally:
        os.close(fd)


def _git(repo_fd, args, data=None, allow=(0,)):
    extra = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
    try:
        proc = subprocess.run(
            ["git", "--no-replace-objects", "-c", "core.fsmonitor=false",
             "-c", "core.hooksPath=", "-C", "."] + args,
            cwd="/", preexec_fn=lambda: os.fchdir(repo_fd), env=dict(GIT_ENV),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, timeout=120, **extra)
    except (OSError, subprocess.SubprocessError):
        raise Reject("git_error") from None
    if proc.returncode not in allow:
        raise Reject("git_error")
    return proc.stdout, proc.returncode


def _strict_json(raw):
    """任意层重复键、NaN/Infinity、孤立代理码点、非法 UTF-8 → 固定码 bad_json/duplicate_key。"""
    def hook(pairs):
        keys = [key for key, _ in pairs]
        if len(set(keys)) != len(keys):
            raise _Dup()
        return dict(pairs)

    def constant(_text):
        raise _NonFinite()

    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=hook, parse_constant=constant)
    except _Dup:
        raise Reject("duplicate_key") from None
    except (_NonFinite, ValueError, UnicodeError):
        raise Reject("bad_json") from None
    stack = [doc]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            try:
                node.encode("utf-8")
            except UnicodeEncodeError:
                raise Reject("bad_json") from None
        elif isinstance(node, dict):
            stack.extend(node.keys())
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return doc


class _Dup(Exception):
    pass


class _NonFinite(Exception):
    pass


def _safe_rel(rel):
    return bool(isinstance(rel, str) and SAFE_REL_RE.match(rel))


def _load_registry(raw):
    doc = _strict_json(raw)
    if not isinstance(doc, dict) or not isinstance(doc.get("objects"), list):
        raise Reject("expected_contract_error")
    entries = {}
    for item in doc["objects"]:
        if not isinstance(item, dict):
            raise Reject("expected_contract_error")
        rid, src, typ, ends = item.get("id"), item.get("source"), item.get("type"), item.get("ends")
        if not (isinstance(rid, str) and rid and isinstance(src, str) and src
                and isinstance(typ, str) and isinstance(ends, dict)):
            raise Reject("expected_contract_error")
        if rid in entries:
            raise Reject("duplicate_item")
        res = item.get("resources") or []
        if not isinstance(res, list) or not all(isinstance(r, str) and r for r in res):
            raise Reject("expected_contract_error")
        mini = ends.get("minis")
        entry = {"id": rid, "type": typ, "source": src, "resources": res, "minis": None}
        if isinstance(mini, dict) and mini.get("present") is True:
            if mini.get("kind") not in ("file", "field"):
                raise Reject("expected_contract_error")
            entry["minis"] = mini
        entries[rid] = entry
    return entries


def _skill_rels(entry):
    """登记资源 → 包内相对路径；逃逸／重复／重叠／前缀冲突一律拒绝。"""
    src = entry["source"]
    if "/" not in src:
        raise Reject("expected_contract_error")
    sdir, base = src.rsplit("/", 1)
    rels = {base: src}
    for res in entry["resources"]:
        if not res.startswith(sdir + "/"):
            raise Reject("expected_contract_error")
        inner = res[len(sdir) + 1:]
        if any(part in ("", ".", "..") or "\0" in part for part in inner.split("/")):
            raise Reject("expected_contract_error")
        if inner in rels:
            raise Reject("expected_contract_error")
        rels[inner] = res
    for one in rels:
        for other in rels:
            if one != other and other.startswith(one + "/"):
                raise Reject("expected_contract_error")
    return rels


def _select(entries, wanted):
    if not wanted:
        raise Reject("bad_args")
    if len(set(wanted)) != len(wanted):
        raise Reject("duplicate_item")
    picked = []
    for rid in wanted:
        if not isinstance(rid, str) or not rid:
            raise Reject("bad_args")
        entry = entries.get(rid)
        if entry is None or entry["minis"] is None:
            raise Reject("unselected_object")
        mini = entry["minis"]
        if entry["type"] == "skill":
            if mini["kind"] != "file" or not isinstance(mini.get("path"), str):
                raise Reject("expected_contract_error")
            _abs_parts(mini["path"], "expected_contract_error")
        elif entry["type"] in ("prompt", "subagent"):
            if mini["kind"] != "field" or not isinstance(mini.get("field"), str) or not mini["field"]:
                raise Reject("expected_contract_error")
            if "alsoFile" in mini:
                _abs_parts(mini["alsoFile"], "expected_contract_error")
        else:
            raise Reject("expected_contract_error")
        picked.append(entry)
    return picked


def _tree(repo_fd, version):
    data, _rc = _git(repo_fd, ["ls-tree", "-r", "-z", "--full-tree", version])
    modes = {}
    for rec in data.split(b"\0"):
        if not rec:
            continue
        meta, sep, path = rec.partition(b"\t")
        fields = meta.split(b" ")
        if not sep or len(fields) != 3:
            raise Reject("git_error")
        try:
            modes[path.decode("utf-8")] = (fields[0].decode("ascii"), fields[1].decode("ascii"))
        except UnicodeDecodeError:
            raise Reject("expected_contract_error") from None
    return modes


def _batch(repo_fd, version, paths):
    ordered = list(dict.fromkeys(paths))
    out = {}
    if not ordered:
        return out
    request = "".join("%s:%s\n" % (version, path) for path in ordered).encode("utf-8")
    data, _rc = _git(repo_fd, ["cat-file", "--batch"], request)
    pos = 0
    for path in ordered:
        end = data.find(b"\n", pos)
        if end < 0:
            raise Reject("git_error")
        header = data[pos:end].split(b" ")
        if len(header) != 3 or header[1] != b"blob":
            raise Reject("git_error")
        try:
            size = int(header[2])
        except ValueError:
            raise Reject("git_error") from None
        start = end + 1
        if start + size + 1 > len(data) or data[start + size:start + size + 1] != b"\n":
            raise Reject("git_error")
        out[path] = data[start:start + size]
        pos = start + size + 1
    return out


def _enumerate(dfd):
    """已锚定目录 fd 的包枚举：只取元数据，超限即 rc3。"""
    files, dirs, state = {}, {}, [0, 0]

    def walk(fd, prefix, depth):
        if depth > MAX_DEPTH:
            raise Reject("enumeration_limit")
        try:
            it = os.scandir(fd)
        except OSError:
            raise Reject("not_readable") from None
        try:
            for ent in it:
                rel = prefix + ent.name
                state[0] += 1
                state[1] += len(rel.encode("utf-8", "surrogateescape")) + 1
                if state[0] > MAX_ENTRIES or state[1] > MAX_PATH_BYTES:
                    raise Reject("enumeration_limit")
                try:
                    st = ent.stat(follow_symlinks=False)
                except OSError:
                    raise Reject("not_readable") from None
                if stat.S_ISDIR(st.st_mode):
                    try:
                        sub = os.open(ent.name, DIR_FLAGS, dir_fd=fd)
                    except OSError:
                        dirs[rel] = "other"
                        continue
                    try:
                        dirs[rel] = "dir"
                        walk(sub, rel + "/", depth + 1)
                    finally:
                        os.close(sub)
                elif stat.S_ISREG(st.st_mode):
                    files[rel] = "file"
                elif stat.S_ISLNK(st.st_mode):
                    files[rel] = "link"
                else:
                    files[rel] = "special"
        finally:
            it.close()

    walk(dfd, "", 1)
    return files, dirs


def _check_skill(entry, ctx):
    rep, rid = ctx["rep"], entry["id"]
    mini = entry["minis"]
    src = entry["source"]
    rels = ctx["rels"][rid]
    base = ctx["root_parts"] + _abs_parts(mini["path"], "expected_contract_error")[:-1]
    status = {}
    reset = [False]
    f = Fence(base, missing_code="file_missing")
    try:
        files = dirs = None
        extra_bad = False
        enum_cls = None
        try:
            files, dirs = _enumerate(f.fd)
        except Reject as exc:
            rep.issue(exc.code, rid, None)
            enum_cls = CODES[exc.code][0]
        expected_dirs = set()
        for rel in rels:
            comps = rel.split("/")[:-1]
            for i in range(1, len(comps) + 1):
                expected_dirs.add("/".join(comps[:i]))
        extras = []
        if files is not None:
            extras = sorted(set(files) - set(rels)) + sorted(set(dirs) - expected_dirs)
            for rel in extras:
                rep.issue("package_set", rid, rel if _safe_rel(rel) else None)
            extra_bad = bool(extras)
        for rel, repo_path in rels.items():
            expect = ctx["blobs"].get(repo_path)
            mode = ctx["modes"].get(repo_path)
            if expect is None or mode is None:
                raise Reject("expected_contract_error")
            if mode not in ("100644", "100755"):
                raise Reject("unsupported_git_mode")
            comps = rel.split("/")
            name = comps.pop()
            path = rel if _safe_rel(rel) else None
            depth = 0
            fstatus, estatus = "not_checked", "not_checked"
            try:
                for comp in comps:
                    f.push(comp)
                    depth += 1
            except Reject as exc:
                rep.issue(exc.code, rid, path)
                fstatus = "different" if CODES[exc.code][0] == "difference" else "not_checked"
            else:
                try:
                    data, cls = _member(f.fd, name, rep, rid, path, expect)
                    estatus = _exec_status(f.fd, name, mode == "100755", rep, rid, path)
                finally:
                    for _ in range(depth):
                        f.pop()
                if cls is None:
                    fstatus = "match"
                else:
                    fstatus = "different" if cls == "difference" else "not_checked"
                    if cls == "difference":
                        extra_bad = True
            status["file:" + repo_path] = fstatus
            status["exec:" + repo_path] = estatus
        if enum_cls is not None:
            status["package-set"] = "not_checked"
        else:
            status["package-set"] = "different" if extra_bad else "match"
    finally:
        try:
            f.recheck()
        except Reject as exc:
            rep.issue(exc.code, rid, None)
            reset[0] = True
        f.close()
    if reset[0]:
        return {item: "not_checked" for item in _item_list(entry)}
    return status


def _check_field_file(entry, ctx):
    rep, rid = ctx["rep"], entry["id"]
    mini, src = entry["minis"], entry["source"]
    if "alsoFile" not in mini:
        return {}
    parts = _abs_parts(mini["alsoFile"], "expected_contract_error")
    mode, expect = ctx["modes"].get(src), ctx["blobs"].get(src)
    if mode is None or expect is None:
        raise Reject("expected_contract_error")
    if mode not in ("100644", "100755"):
        raise Reject("unsupported_git_mode")
    body = ctx["body"]
    try:
        git_body = body.body_bytes(expect)
    except body.ContractError:
        raise Reject("expected_contract_error") from None
    ctx["git_body"][rid] = git_body
    status, reset = {}, [False]
    f = Fence(ctx["root_parts"] + parts[:-1])
    try:
        data, cls = _member(f.fd, parts[-1], rep, rid, None, None)
        estatus = _exec_status(f.fd, parts[-1], mode == "100755", rep, rid, None)
    finally:
        try:
            f.recheck()
        except Reject as exc:
            rep.issue(exc.code, rid, None)
            reset[0] = True
        f.close()
    if reset[0]:
        return {"file:" + src: "not_checked", "exec:" + src: "not_checked"}
    fstatus = "not_checked"
    if cls is None:
        try:
            site_body = body.body_bytes(data)
        except body.ContractError:
            rep.issue("file_contract", rid, None)
            fstatus = "different"
        else:
            if site_body == git_body:
                fstatus = "match"
            else:
                rep.issue("file_bytes", rid, None)
                fstatus = "different"
    elif cls == "difference":
        fstatus = "different"
    return {"file:" + src: fstatus, "exec:" + src: estatus}


SAFE_REL_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]{0,255}\Z")
OBS_KEYS = ("id", "instanceRef", "sourceVersion", "startedAt", "finishedAt", "sourceBasis")
OBJ_KEYS = ("object", "observationId", "instanceRef", "field", "value")


def _item_list(entry):
    mini = entry["minis"]
    if entry["type"] == "skill":
        items = ["file:" + entry["source"], "exec:" + entry["source"]]
        for res in entry["resources"]:
            items += ["file:" + res, "exec:" + res]
        items.append("package-set")
        return items
    items = []
    if "alsoFile" in mini:
        items += ["file:" + entry["source"], "exec:" + entry["source"]]
    items.append("field:" + mini["field"])
    return items


def _time_value(rep, value):
    if not isinstance(value, str) or not TIME_RE.match(value):
        rep.issue("bad_shape")
        return None
    try:
        parsed = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        rep.issue("bad_shape")
        return None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        rep.issue("bad_shape")
        return None
    return parsed


def _projection_values(rep, raw, rid_field):
    """严格 JSON＋结构/关联检查；返回 {rid: (state, value)}，缺键不短路已给字段的类型检查。"""
    try:
        doc = _strict_json(raw)
    except Reject as exc:
        for rid in rid_field:
            rep.issue(exc.code, rid, None)
        return {}
    if not isinstance(doc, dict):
        rep.issue("bad_shape")
        return {}
    for key in ("schemaVersion", "observation", "objects"):
        if key not in doc:
            rep.issue("missing_field")
    for key in doc:
        if key not in ("schemaVersion", "observation", "objects"):
            rep.issue("unknown_key")
    if "schemaVersion" in doc:
        value = doc["schemaVersion"]
        if isinstance(value, bool) or not isinstance(value, int) or value != 1:
            rep.issue("bad_shape")
    labels = {}
    if "observation" in doc:
        obs = doc["observation"]
        if not isinstance(obs, dict):
            rep.issue("bad_shape")
        else:
            for key in OBS_KEYS:
                if key not in obs:
                    rep.issue("missing_field")
            for key in obs:
                if key not in OBS_KEYS:
                    rep.issue("unknown_key")
            for key in ("id", "instanceRef", "sourceVersion", "sourceBasis"):
                if key in obs:
                    if not isinstance(obs[key], str) or not obs[key]:
                        rep.issue("bad_shape")
                    else:
                        labels[key] = obs[key]
            start = _time_value(rep, obs["startedAt"]) if "startedAt" in obs else None
            end = _time_value(rep, obs["finishedAt"]) if "finishedAt" in obs else None
            if start is not None and end is not None and end < start:
                rep.issue("bad_shape")
    records = doc.get("objects")
    values, seen = {}, set()
    if "objects" in doc:
        if not isinstance(records, list):
            rep.issue("bad_shape")
        else:
            for rec in records:
                if not isinstance(rec, dict):
                    rep.issue("bad_shape")
                    continue
                name = rec.get("object")
                rid = name if isinstance(name, str) and name in rid_field else None
                for key in OBJ_KEYS:
                    if key not in rec:
                        rep.issue("missing_field", rid, None)
                for key in rec:
                    if key not in OBJ_KEYS:
                        rep.issue("unknown_key", rid, None)
                for key in ("object", "observationId", "instanceRef", "field"):
                    if key in rec and (not isinstance(rec[key], str) or not rec[key]):
                        rep.issue("bad_shape", rid, None)
                if rid is None:
                    rep.issue("unselected_object")
                    continue
                if rid in seen:
                    rep.issue("duplicate_item", rid, None)
                    continue
                seen.add(rid)
                if rec.get("field") != rid_field[rid]:
                    rep.issue("field_binding", rid, None)
                if "observationId" in rec and rec["observationId"] != labels.get("id"):
                    rep.issue("field_binding", rid, None)
                if "instanceRef" in rec and rec["instanceRef"] != labels.get("instanceRef"):
                    rep.issue("field_binding", rid, None)
                if "value" not in rec:
                    values[rid] = ("missing", None)
                elif rec["value"] is None:
                    values[rid] = ("null", None)
                elif isinstance(rec["value"], str):
                    values[rid] = ("value", rec["value"])
                else:
                    rep.issue("bad_shape", rid, None)
                    values[rid] = ("missing", None)
    for rid in rid_field:
        if rid not in seen:
            rep.issue("missing_object", rid, None)
    return values


def _allowed(entry, ctx):
    """字段期望字节：SOUL 用 Git 正文；子代理用全文并只允许去掉恰好一个尾 LF。"""
    rid = entry["id"]
    if rid in ctx["git_body"]:
        return {ctx["git_body"][rid]}
    expect = ctx["blobs"].get(entry["source"])
    if expect is None:
        raise Reject("expected_contract_error")
    allowed = {expect}
    if expect.endswith(b"\n"):
        allowed.add(expect[:-1])
    return allowed


def _field_status(rep, rid, state, allowed):
    if state[0] == "missing":
        rep.issue("missing_field", rid, None)
        return "not_checked"
    if state[0] == "null":
        rep.issue("field_value", rid, None)
        return "different"
    try:
        raw = state[1].encode("utf-8")
    except UnicodeEncodeError:
        rep.issue("bad_json", rid, None)
        return "not_checked"
    if raw in allowed:
        return "match"
    rep.issue("field_value", rid, None)
    return "different"


def _run(rep, args, version, repo, root_parts):
    out, _rc = _git(repo.fd, ["config", "--get-regexp",
                              r"^(extensions\.partialclone|remote\..*\.promisor)$"], allow=(0, 1))
    if out.strip():
        raise Reject("git_error")
    if _git(repo.fd, ["cat-file", "-t", version])[0].strip() != b"commit":
        raise Reject("git_error")
    reg_raw, _rc = _git(repo.fd, ["cat-file", "blob", version + ":tools/sync-targets.json"])
    entries = _load_registry(reg_raw)
    selected = _select(entries, args.objects)
    field_entries = [entry for entry in selected if entry["type"] != "skill"]
    if args.projection is not None and not field_entries:
        raise Reject("bad_args")
    paths, rels = [], {}
    for entry in selected:
        paths.append(entry["source"])
        if entry["type"] == "skill":
            rels[entry["id"]] = _skill_rels(entry)
            paths.extend(entry["resources"])
    modes = _tree(repo.fd, version)
    ctx = {"rep": rep, "root_parts": root_parts, "blobs": _batch(repo.fd, version, paths),
           "modes": {}, "body": _load_body(), "rels": rels, "git_body": {}}
    for path in dict.fromkeys(paths):
        rec = modes.get(path)
        if rec is None:
            raise Reject("expected_contract_error")
        ctx["modes"][path] = rec[0]

    for entry in selected:
        file_items = [item for item in _item_list(entry) if not item.startswith("field:")]
        statuses = {}
        try:
            statuses = (_check_skill(entry, ctx) if entry["type"] == "skill"
                        else _check_field_file(entry, ctx))
        except Reject as exc:
            rep.issue(exc.code, entry["id"], exc.path)
        for item in file_items:
            rep.check(entry["id"], item, statuses.get(item, "not_checked"))

    rid_field = {entry["id"]: entry["minis"]["field"] for entry in field_entries}
    values = {}
    if field_entries:
        if args.projection is None:
            for rid in rid_field:
                rep.issue("missing_projection", rid, None)
        else:
            try:
                raw = _read_input(args.projection)
            except Reject as exc:
                for rid in rid_field:
                    rep.issue(exc.code, rid, None)
            else:
                values = _projection_values(rep, raw, rid_field)
    for entry in field_entries:
        rid = entry["id"]
        status = "not_checked"
        if args.projection is not None and rid in values:
            try:
                allowed = _allowed(entry, ctx)
            except Reject as exc:
                rep.issue(exc.code, rid, None)
            else:
                status = _field_status(rep, rid, values[rid], allowed)
        rep.check(rid, "field:" + entry["minis"]["field"], status)

    if any(entry["type"] == "skill" for entry in selected):
        rep.not_covered.append("技能 App 登记、启用与实际加载（只核文件与包集合）")
    if any(entry["type"] == "prompt" for entry in selected):
        rep.not_covered.append("SOUL frontmatter 与 App 侧完整文件（只核 alsoFile 正文与登记字段）")
    rep.not_covered.append("Git 未表达的其他 POSIX 权限位、属主与 ACL（只映射 100644/100755 属主执行位）")
    if field_entries:
        rep.not_covered.append("生效字段安全投影的来源真实性、记录真实性与采集时点")
    rep.not_covered.append("非原子快照：并发替换、ABA 与前后复核之间的窗口")


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Reject("bad_args")


def _parse(argv):
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--git-version", dest="version", required=True)
    parser.add_argument("--object", dest="objects", action="append", default=[])
    parser.add_argument("--root", default="/")
    parser.add_argument("--projection", default=None)
    return parser.parse_args(argv)


def _emit(rep, version, view):
    code, status = rep.worst()
    sys.stdout.write(json.dumps({
        "gitVersion": version, "rootView": view, "status": status,
        "checks": rep.checks, "issues": rep.issues, "notCovered": rep.not_covered,
    }, ensure_ascii=True) + "\n")
    return code


def main(argv=None):
    rep = Report()
    version, view = None, "live"
    try:
        args = _parse(argv)
        view = "live" if args.root == "/" else "relocated"
        root_parts = _abs_parts(args.root, "bad_args")
        if not HEX40_RE.match(args.version or ""):
            raise Reject("bad_args")
        version = args.version
        repo = Fence(_abs_parts(args.repo, "bad_args"), missing_code="git_error")
        try:
            _run(rep, args, version, repo, root_parts)
        except Reject as exc:
            rep.issue(exc.code, None, exc.path)
        finally:
            try:
                repo.recheck()
            except Reject as exc:
                rep.issue(exc.code)
            repo.close()
    except Reject as exc:
        rep.issue(exc.code)
    except Exception:
        rep.issue("internal_error")
    return _emit(rep, version, view)


if __name__ == "__main__":
    sys.exit(main())

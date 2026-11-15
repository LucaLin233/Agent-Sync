#!/usr/bin/env python3
"""LH 技能专项离线验收：观察记录 ↔ 同一提交的仓库原字节（只读、无网络、无写入）。

用法（Minis/iSH 已审副本，仅标准库）：
  python3 -I -B tools/lh-verify.py --repo PATH --git-version <40位小写hex> \
      --object <ID> [--object <ID> ...] --evidence FILE

只核：结构、所给标签相等关系、登记关联、集合差异、已保存响应的结构/编码/size/hash、自洽与 Git 原 bytes。
真实实例、源端版本、源头字段投影、资源集合完整性、记录真实性、同阶段与无并发，由当次可信调用方外部核准；
`sourceBasis` 只是依据定位引用，本工具不打开、不当批准或真实性证明。标签一致的伪造记录仍可能 rc=0。

退出码：0 匹配 / 1 确证差异 / 2 参数、格式、执行或已记录读取错误 / 3 缺证；并存按 2>3>1>0。

失败码是封闭集合，不回显正文、资源、异常或外部 stderr：
  bad_args / bad_evidence_json / bad_evidence_shape / bad_evidence_encoding /
  duplicate_object / duplicate_path / duplicate_request / extra_object / extra_call /
  association_error / object_not_registered / registry_invalid / repo_unusable / git_error /
  content_contract_error
内嵌记录复用 tools/auth-call.py 的资源动作码（含 http_status_NNN 与 missing_variable:NAME／bad_credential:NAME）。
"""
import argparse
import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys

HEX40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
TIME_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
REL_PATH_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]{0,255}\Z")

TOP_KEYS = ("schemaVersion", "observation", "objects")
OBS_KEYS = ("id", "instanceRef", "sourceVersion", "startedAt", "finishedAt", "sourceBasis")
OBJ_KEYS = ("object", "observationId", "instanceRef", "projection", "resourcePaths", "calls")
PROJ_KEYS = ("id", "name", "description", "identifier", "content")
CALL_KEYS = ("observationId", "instanceRef", "request", "exitCode", "stdout", "stderr")
REQ_KEYS = ("id", "path")
FIELDS = ("id", "name", "description", "identifier", "content", "resourcePaths")

# identifier 只覆盖已确证五技能；条件不满足即 identifier_unsupported（缺证），不做通用 URL 推导。
IDENT_SUPPORTED = ("luno-core", "luno-ops", "luno-authoring", "luno-platform", "luno-surge")
INSTALL_PREFIX = "https://github.com/LucaLin233/Agent-Sync/tree/main/skills/"
IDENT_PREFIX = "lucalin233-agent-sync-"

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


class Reject(Exception):
    """固定码／缺证路径；exit 只在 2（记录无效）与 3（缺字段）之间。"""

    def __init__(self, code, paths=(), exit=2):
        super().__init__(code)
        self.code = code
        self.paths = list(paths)
        self.exit = exit


class GitError(Exception):
    """git 不可用、对象缺失或仓库不完整；文本从不外泄。"""


_CACHE = {}


def _load(name, filename):
    """按工具自身目录加载可信模块：不依赖 cwd/PYTHONPATH，不改 sys.path。"""
    if name in _CACHE:
        return _CACHE[name]
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(name, os.path.join(here, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _CACHE[name] = module
    return module


def _strict_json(raw, code="bad_evidence_json"):
    """任意层重复键、NaN/Infinity 一律拒绝（复用 auth-call 的去重钩子）。"""
    auth = _load("lh_auth_call", "auth-call.py")
    def reject_constant(_text):
        raise ValueError("non-finite")
    try:
        if isinstance(raw, str):  # 孤立代理码点等不可编码输入在这里按固定码拒绝
            raw = raw.encode("utf-8")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=auth._unique_pairs,
                          parse_constant=reject_constant)
    except (ValueError, UnicodeError, TypeError, KeyError, auth.ToolError):
        raise Reject(code) from None


def _git(repo, args, data=None):
    extra = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
    try:
        proc = subprocess.run(
            ["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-C", repo] + args,
            env=dict(GIT_ENV), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, timeout=60, **extra)
    except (OSError, subprocess.SubprocessError):
        raise GitError() from None
    if proc.returncode != 0:
        raise GitError()
    return proc.stdout


def _git_config(repo, key):
    try:
        proc = subprocess.run(
            ["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-C", repo,
             "config", "--get-regexp", key],
            env=dict(GIT_ENV), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        raise GitError() from None
    if proc.returncode == 0:
        return proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode == 1:
        return ""
    raise GitError()


def _repo_ready(repo, version):
    """完整可信本地仓：无 promisor/partial clone，禁 lazy fetch 与 replace。"""
    if not os.path.isdir(repo):
        raise GitError()
    promisor = _git_config(repo, "^(extensions\\.partialclone|remote\\..*\\.promisor)$")
    if promisor:
        raise GitError()
    _git(repo, ["rev-parse", "--git-dir"])
    # 只接受 commit 本身；不用 ^{commit} 把 tag 解引用成 commit。
    if _git(repo, ["cat-file", "-t", version]).strip() != b"commit":
        raise GitError()


def _batch(repo, version, paths):
    """一次 cat-file --batch 取全部原 bytes；任何缺对象即失败，不做 lazy fetch 兜底。"""
    blobs = {}
    ordered = [path for path in dict.fromkeys(paths)]
    if not ordered:
        return blobs
    request = "".join("%s:%s\n" % (version, path) for path in ordered).encode("utf-8")
    out = _git(repo, ["cat-file", "--batch"], request)
    pos = 0
    for path in ordered:
        end = out.find(b"\n", pos)
        if end < 0:
            raise GitError()
        header = out[pos:end].split(b" ")
        if len(header) != 3 or header[1] != b"blob":
            raise GitError()
        try:
            size = int(header[2])
        except ValueError:
            raise GitError() from None
        start = end + 1
        if start + size + 1 > len(out) or out[start + size:start + size + 1] != b"\n":
            raise GitError()
        blobs[path] = out[start:start + size]
        pos = start + size + 1
    return blobs


def _time(value):
    if not isinstance(value, str) or not TIME_RE.match(value):
        raise Reject("bad_evidence_shape")
    try:
        parsed = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise Reject("bad_evidence_shape") from None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise Reject("bad_evidence_shape")
    return parsed


def _str(value, nonempty=False):
    if not isinstance(value, str) or (nonempty and not value):
        raise Reject("bad_evidence_shape")
    return value


_MISSING = []


def _keys(node, keys, where):
    """只做容器/未知键检查并登记缺项；缺失不短路，同层其余键仍独立校验。"""
    if not isinstance(node, dict):
        raise Reject("bad_evidence_shape")
    if set(node) - set(keys):
        raise Reject("bad_evidence_shape")
    for key in keys:
        if key not in node:
            _MISSING.append(where + key)
    return node


def _validate(evidence):
    """多余键/错类型 rc2；缺必需字段全量收集后 rc3（不掩盖同层或跨对象的类型错误）。"""
    _MISSING.clear()
    _validate_all(evidence)
    if _MISSING:
        raise Reject("incomplete", list(_MISSING), exit=3)
    return evidence


def _validate_all(evidence):
    top = _keys(evidence, TOP_KEYS, "")
    if "schemaVersion" in top and (type(top["schemaVersion"]) is not int
                                   or top["schemaVersion"] != 1):
        raise Reject("bad_evidence_shape")
    obs = _keys(top["observation"], OBS_KEYS, "observation.") \
        if "observation" in top else None
    if obs is not None:
        for key in ("id", "instanceRef", "sourceVersion", "sourceBasis"):
            if key in obs:
                _str(obs[key], nonempty=True)
        start = _time(obs["startedAt"]) if "startedAt" in obs else None
        end = _time(obs["finishedAt"]) if "finishedAt" in obs else None
        if start is not None and end is not None and end < start:
            raise Reject("bad_evidence_shape")
    if "objects" in top:
        if not isinstance(top["objects"], list):
            raise Reject("bad_evidence_shape")
        seen = set()
        for i, item in enumerate(top["objects"]):
            _validate_object(item, "objects[%d]." % i, seen)


def _validate_object(item, where, seen):
    obj = _keys(item, OBJ_KEYS, where)
    if "object" in obj:
        name = _str(obj["object"], nonempty=True)
        if name in seen:
            raise Reject("duplicate_object")
        seen.add(name)
    for key in ("observationId", "instanceRef"):
        if key in obj:
            _str(obj[key], nonempty=True)
    if "projection" in obj:
        proj = _keys(obj["projection"], PROJ_KEYS, where + "projection.")
        if "id" in proj:
            _str(proj["id"], nonempty=True)
        for key in ("name", "description", "identifier", "content"):
            if key in proj and proj[key] is not None:
                _str(proj[key])
    if "resourcePaths" in obj:
        if not isinstance(obj["resourcePaths"], list):
            raise Reject("bad_evidence_shape")
        paths = set()
        for path in obj["resourcePaths"]:
            _str(path, nonempty=True)
            if path in paths:
                raise Reject("duplicate_path")
            paths.add(path)
    if "calls" in obj:
        if not isinstance(obj["calls"], list):
            raise Reject("bad_evidence_shape")
        pairs = set()
        for j, raw_call in enumerate(obj["calls"]):
            _validate_call(raw_call, where + "calls[%d]." % j, pairs)


def _validate_call(call, cw, pairs):
    node = _keys(call, CALL_KEYS, cw)
    for key in ("observationId", "instanceRef"):
        if key in node:
            _str(node[key], nonempty=True)
    req = _keys(node["request"], REQ_KEYS, cw + "request.") if "request" in node else None
    if req is not None:
        for key in ("id", "path"):
            if key in req:
                _str(req[key], nonempty=True)
    if "exitCode" in node and (type(node["exitCode"]) is not int
                               or node["exitCode"] not in (0, 2)):
        raise Reject("bad_evidence_shape")
    for key in ("stdout", "stderr"):
        if key in node:
            _str(node[key])
    if req is not None and "id" in req and "path" in req:
        pair = (req["id"], req["path"])
        if pair in pairs:
            raise Reject("duplicate_request")
        pairs.add(pair)


def _rel_path(path):
    """path 遵循 auth-call 的既有约束；非法路径不回显。"""
    if not isinstance(path, str) or not REL_PATH_RE.match(path) \
            or ".." in path or "//" in path or path.endswith("/"):
        raise Reject("bad_path")
    return path


def _record(call, auth):
    """校验一条已保存的 skill-resource 记录；返回 (状态, 解码 bytes 或 None)。"""
    if call["exitCode"] == 2:
        if call["stdout"] != "":
            raise Reject("bad_shape")
        raw = call["stderr"]
        if not raw.endswith("\n") or raw.count("\n") != 1:
            raise Reject("bad_shape")
        doc = _strict_json(raw[:-1], "bad_shape")
        if not isinstance(doc, dict) or set(doc) != {"ok", "error"} or doc["ok"] is not False:
            raise Reject("bad_shape")
        code = doc["error"]
        if not isinstance(code, str):
            raise Reject("bad_shape")
        if code in ("bad_args", "bad_json", "transport_error", "response_too_large",
                    "reflected_credential", "bad_server", "bad_skill_id", "bad_path",
                    "bad_shape", "bad_fields", "bad_integrity", "internal_error"):
            return "error", code
        if re.fullmatch(r"http_status_[0-9]{3}", code):
            return "error", code
        if re.fullmatch(r"(missing_variable|bad_credential):(LOBEHUB_SERVER|LOBEHUB_CLI_API_KEY)", code):
            return "error", code
        raise Reject("bad_shape")
    if call["stderr"] != "":
        raise Reject("bad_shape")
    raw = call["stdout"]
    if not raw.endswith("\n") or raw.count("\n") != 1:
        raise Reject("bad_shape")
    doc = _strict_json(raw[:-1], "bad_shape")
    if not isinstance(doc, dict) or set(doc) != {"ok", "action", "resource"} or doc["ok"] is not True \
            or doc["action"] != "skill-resource":
        raise Reject("bad_shape")
    data = doc["resource"]
    if not isinstance(data, dict) or set(data) != set(auth.RESOURCE_FIELDS):
        raise Reject("bad_fields")
    try:
        blob = auth.resource_bytes(data)
    except auth.ToolError as exc:
        raise Reject(str(exc)) from None
    return "ok", (data["path"], blob)


def _compare(entry, registry, blobs, auth):
    """单对象比对：先身份，再集合，再正文/元数据/资源记录；每步只记实际做过的检查。"""
    body = _load("lh_body_contract", "body_contract.py")
    lh_id = registry["ends"]["lobehub"]["id"]
    proj = entry["projection"]
    record = {"object": registry["id"], "id": proj["id"], "differences": [],
              "missingEvidence": [], "errors": [], "checked": [],
              "resourcePaths": {"missing": [], "extra": []}}
    record["checked"].append("id")
    if proj["id"] != lh_id:
        # 身份差异：写实际 ID，停止该对象的内容与集合比较。
        record["differences"].append("id")
        return record

    source = registry["source"]
    try:
        skill_md = blobs[source]
        content = body.body_bytes(skill_md)
        name = body.fm_get(skill_md, "name")
        description = body.fm_get(skill_md, "description")
    except body.ContractError:
        record["errors"].append("content_contract_error")
        return record

    prefix = source.rsplit("/", 1)[0] + "/"
    expected = set()
    for path in registry["resources"]:
        if not path.startswith(prefix) or path == source:
            raise Reject("registry_invalid")
        expected.add(_rel_path(path[len(prefix):]))
    site = {_rel_path(path) for path in entry["resourcePaths"]}

    record["checked"].append("resourcePaths")
    record["resourcePaths"]["missing"] = sorted(expected - site)
    record["resourcePaths"]["extra"] = sorted(site - expected)
    for path in record["resourcePaths"]["missing"] + record["resourcePaths"]["extra"]:
        record["differences"].append("resource:" + path)

    for field, want in (("name", name), ("description", description)):
        record["checked"].append(field)
        if want is body.MISSING:
            record["missingEvidence"].append(field)
        elif proj[field] != (None if want is None else str(want)):
            record["differences"].append(field)

    record["checked"].append("identifier")
    ident = None
    if registry["id"] in IDENT_SUPPORTED and name == registry["id"] \
            and registry.get("installSource") == INSTALL_PREFIX + registry["id"]:
        ident = IDENT_PREFIX + registry["id"]
    if ident is None:
        record["missingEvidence"].append("identifier")
    elif proj["identifier"] != ident:
        record["differences"].append("identifier")

    record["checked"].append("content")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        record["errors"].append("content_contract_error")
        record["checked"].remove("content")
    else:
        if proj["content"] != text:
            record["differences"].append("content")

    # 只为登记∩现场路径收记录；交集外的记录一律拒绝，其正文不读不比。
    required = expected & site
    calls = {}
    for call in entry["calls"]:
        try:
            path = _rel_path(call["request"]["path"])
        except Reject as exc:
            record["errors"].append(exc.code)
            continue
        if call["request"]["id"] != lh_id:
            record["errors"].append("association_error")
        elif path not in required:
            record["errors"].append("extra_call")
        else:
            calls.setdefault(path, []).append(call)
    for path in sorted(required):
        field = "resource:" + path
        hits = calls.get(path, [])
        if not hits:
            record["missingEvidence"].append(field)
            continue
        try:
            state, payload = _record(hits[0], auth)
        except Reject as exc:
            record["errors"].append(exc.code)
            continue
        if state == "error":
            record["errors"].append(payload)
            continue
        got_path, blob = payload
        if got_path != path:
            record["errors"].append("association_error")
            continue
        record["checked"].append(field)
        if blob != blobs[prefix + path]:
            record["differences"].append(field)
    return record


class _Parser(argparse.ArgumentParser):
    """参数错误只映射固定码，不向 stderr 打印 usage/原始参数。"""

    def error(self, message):
        raise Reject("bad_args")


def _empty(version, code):
    return emit({"gitVersion": version, "status": "error", "objects": [],
                 "missingEvidence": [], "errors": [code]}, 2)


def main(argv=None):
    parser = _Parser(prog="lh-verify", add_help=True, allow_abbrev=False)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--git-version", required=True)
    parser.add_argument("--object", action="append", default=[])
    parser.add_argument("--evidence", required=True)
    try:
        args = parser.parse_args(argv)
    except Reject:
        return _empty(None, "bad_args")
    except SystemExit as exc:  # --help：正常帮助，不产出结果 JSON
        return exc.code or 0
    version = args.git_version
    if not HEX40_RE.match(version or "") or not args.object \
            or len(set(args.object)) != len(args.object) or not args.evidence:
        return _empty(None, "bad_args")
    try:
        with open(args.evidence, "rb") as handle:
            evidence = _validate(_strict_json(handle.read()))
    except OSError:
        return _empty(version, "bad_evidence_json")
    except Reject as exc:
        if exc.exit == 3:
            return emit({"gitVersion": version, "status": "incomplete", "objects": [],
                         "missingEvidence": exc.paths, "errors": []}, 3)
        return _empty(version, exc.code)

    try:
        auth = _load("lh_auth_call", "auth-call.py")
        _repo_ready(args.repo, version)
        raw_registry = _batch(args.repo, version,
                              ["tools/sync-targets.json"])["tools/sync-targets.json"]
    except GitError:
        return _empty(version, "repo_unusable")
    try:
        registry = json.loads(raw_registry.decode("utf-8"))
    except (ValueError, UnicodeError):
        return _empty(version, "registry_invalid")
    if not isinstance(registry, dict) or not isinstance(registry.get("objects"), list):
        return _empty(version, "registry_invalid")

    known = {}
    for item in registry["objects"]:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            known[item["id"]] = item
    selected = []
    for name in args.object:
        item = known.get(name)
        if not item or item.get("type") != "skill" \
                or not isinstance(item.get("ends"), dict) \
                or not isinstance(item["ends"].get("lobehub"), dict) \
                or item["ends"]["lobehub"].get("present") is not True \
                or not isinstance(item["ends"]["lobehub"].get("id"), str) \
                or not item["ends"]["lobehub"]["id"] \
                or not isinstance(item.get("source"), str) \
                or not isinstance(item.get("resources"), list):
            return _empty(version, "object_not_registered")
        selected.append(item)
    try:
        blobs = _batch(args.repo, version,
                       [item["source"] for item in selected] +
                       [path for item in selected for path in item["resources"]])
    except GitError:
        return _empty(version, "repo_unusable")
    if {item["object"] for item in evidence["objects"]} - set(args.object):
        return _empty(version, "extra_object")

    by_id = {item["object"]: item for item in evidence["objects"]}
    obs = evidence["observation"]
    results, errors = [], []
    for item in selected:
        entry = by_id.get(item["id"])
        if entry is None:
            record = {"object": item["id"], "id": None, "checked": [], "differences": [],
                      "missingEvidence": ["objects[" + item["id"] + "]"], "errors": [],
                      "resourcePaths": {"missing": [], "extra": []}}
        else:
            labels_ok = entry["observationId"] == obs["id"] \
                and entry["instanceRef"] == obs["instanceRef"] \
                and all(call["observationId"] == obs["id"]
                        and call["instanceRef"] == obs["instanceRef"] for call in entry["calls"])
            try:
                record = _compare(entry, item, blobs, auth) if labels_ok \
                    else {"object": item["id"], "id": entry["projection"]["id"], "checked": [],
                          "differences": [], "missingEvidence": [],
                          "errors": ["association_error"],
                          "resourcePaths": {"missing": [], "extra": []}}
            except Reject as exc:
                # 单对象的记录问题不抹掉此前对象的结果。
                record = {"object": item["id"], "id": None, "checked": [], "differences": [],
                          "missingEvidence": exc.paths if exc.exit == 3 else [],
                          "errors": [] if exc.exit == 3 else [exc.code],
                          "resourcePaths": {"missing": [], "extra": []}}
        results.append({key: record[key] for key in
                        ("object", "id", "checked", "differences", "missingEvidence",
                         "errors", "resourcePaths")})
        for code in record["errors"]:
            if code not in errors:
                errors.append(code)

    missing = [result["object"] + ":" + path for result in results
               for path in result["missingEvidence"]]
    if errors:
        status, code = "error", 2
    elif missing:
        status, code = "incomplete", 3
    elif [result for result in results if result["differences"]]:
        status, code = "different", 1
    else:
        status, code = "match", 0
    return emit({"gitVersion": version, "status": status, "objects": results,
                 "missingEvidence": missing, "errors": errors}, code)


def emit(doc, code):
    sys.stdout.write(json.dumps(doc, ensure_ascii=True) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Authenticated read-only calls: two fixed actions; see repository README.

  pr-meta         GitHub GraphQL PR metadata (fixed query, typed variables)
  skill-resource  LobeHub agentSkills.readResource (one path, fixed fields)

No shell, arbitrary URL/query, proxy, redirect, TLS downgrade or key logging.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

GRAPHQL_URL = "https://api.github.com/graphql"
RESOURCE_SUFFIX = "/trpc/lambda/agentSkills.readResource"
USER_AGENT = "agent-sync-auth-call/1"

PR_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){"
    "repository(owner:$owner,name:$name){pullRequest(number:$number){"
    "number state merged headRefOid baseRefOid isDraft reviewDecision "
    "mergeable changedFiles}}}"
)
PR_FIELDS = (
    "number", "state", "merged", "headRefOid", "baseRefOid",
    "isDraft", "reviewDecision", "mergeable", "changedFiles",
)
RESOURCE_FIELDS = ("content", "encoding", "fileHash", "fileType", "path", "size")

NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
SKILL_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
REL_PATH_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]{0,255}\Z")
HEX64_RE = re.compile(r"\A[0-9a-f]{64}\Z")
HEX40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
MAX_BODY = 2_000_000
TIMEOUT = 20


class ToolError(Exception):
    """Fixed, non-secret error code."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError("bad_args")


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ToolError("bad_json")
        out[key] = value
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # never follow 3xx


def _env_getter(name):
    """Only by-name reads; the environment is never enumerated or copied."""
    return os.environ.get(name)


def make_opener():
    """Empty proxy map, system-trusted TLS, no redirects, no key logging.

    create_default_context() adopts SSLKEYLOGFILE and creates that file, so the
    client context is assembled explicitly instead.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    ctx.load_default_certs()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=ctx),
    )


def _fetch_json(opener, request):
    """Bounded body, fixed error codes; no body text is ever echoed."""
    try:
        with opener.open(request, timeout=TIMEOUT) as resp:
            status = resp.status
            if status != 200:
                raise ToolError("http_status_%d" % status)
            raw = resp.read(MAX_BODY + 1)
    except urllib.error.HTTPError as exc:
        exc.close()
        raise ToolError("http_status_%d" % exc.code) from None  # body never echoed
    except ToolError:
        raise
    except Exception:
        # incl. http.client ValueError, whose message carries the raw header
        raise ToolError("transport_error") from None
    if len(raw) > MAX_BODY:  # outside the handlers: never rewritten to transport_error
        raise ToolError("response_too_large")
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs)
    except ValueError:  # includes UnicodeDecodeError
        raise ToolError("bad_json") from None


def _need(getter, name):
    value = getter(name)
    if not value:
        raise ToolError("missing_variable:" + name)
    if not isinstance(value, str) or not all("\x21" <= ch <= "\x7e" for ch in value):
        # never echo it: http.client would embed the raw header in ValueError
        raise ToolError("bad_credential:" + name)
    return value


def _no_reflection(obj, token):
    """Refuse to emit this call's own credential if a peer echoes it.

    Decoded leaves are compared, so quotes/backslashes cannot slip through.
    """
    pending = [obj]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if token in item:
                raise ToolError("reflected_credential")
        elif isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def _server(value):
    parts = urllib.parse.urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment
            or parts.path not in ("", "/")):
        raise ToolError("bad_server")
    return value.rstrip("/")


def pr_meta(repo, number, getter=None, opener=None):
    getter = _env_getter if getter is None else getter
    if not isinstance(repo, str) or repo.count("/") != 1:
        raise ToolError("bad_repo")
    owner, name = repo.split("/")
    if not NAME_RE.match(owner) or not NAME_RE.match(name):
        raise ToolError("bad_repo")
    if isinstance(number, bool) or not isinstance(number, int) or not 0 < number < 10**9:
        raise ToolError("bad_number")
    token = _need(getter, "GH_TOKEN")
    body = json.dumps(
        {"query": PR_QUERY, "variables": {"owner": owner, "name": name, "number": number}},
        separators=(",", ":"),
    ).encode("utf-8")
    doc = _fetch_json(opener or make_opener(), urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": "bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    ))
    if not isinstance(doc, dict) or set(doc) != {"data"}:
        raise ToolError("graphql_error")
    try:
        data = doc["data"]
        repository = data["repository"]
        if set(data) != {"repository"} or set(repository) != {"pullRequest"}:
            raise ToolError("bad_shape")
        pr = repository["pullRequest"]
    except (KeyError, TypeError):
        raise ToolError("bad_shape") from None
    if not isinstance(pr, dict) or set(pr) != set(PR_FIELDS):
        raise ToolError("bad_fields")
    if not (type(pr["number"]) is int and pr["number"] == number  # answers our request
            and type(pr["changedFiles"]) is int
            and type(pr["merged"]) is bool and type(pr["isDraft"]) is bool
            and all(isinstance(pr[k], str) for k in ("state", "mergeable"))
            and all(isinstance(pr[k], str) and HEX40_RE.match(pr[k])
                    for k in ("headRefOid", "baseRefOid"))
            and (pr["reviewDecision"] is None
                 or isinstance(pr["reviewDecision"], str))):
        raise ToolError("bad_fields")
    out = {"action": "pr-meta", "repo": repo, "pullRequest": pr}
    _no_reflection(out, token)  # wrapper fields (repo) are output too
    return out


def resource_bytes(data, expected_path=None):
    """六字段资源校验并解码；不读取环境，不发请求。"""
    if not isinstance(data, dict) or set(data) != set(RESOURCE_FIELDS):
        raise ToolError("bad_fields")
    if (not isinstance(data["path"], str)
            or (expected_path is not None and data["path"] != expected_path)
            or data["encoding"] not in ("utf8", "base64")
            or not isinstance(data["content"], str)
            or not isinstance(data["fileType"], str)
            or isinstance(data["size"], bool) or not isinstance(data["size"], int)
            or data["size"] < 0
            or not isinstance(data["fileHash"], str) or not HEX64_RE.match(data["fileHash"])):
        raise ToolError("bad_fields")
    try:
        blob = data["content"].encode("utf-8") if data["encoding"] == "utf8" \
            else base64.b64decode(data["content"], validate=True)
    except ValueError:
        raise ToolError("bad_fields") from None
    if len(blob) != data["size"] or hashlib.sha256(blob).hexdigest() != data["fileHash"]:
        raise ToolError("bad_integrity")
    return blob


def skill_resource(skill_id, path, getter=None, opener=None):
    getter = _env_getter if getter is None else getter
    if not isinstance(skill_id, str) or not SKILL_ID_RE.match(skill_id):
        raise ToolError("bad_skill_id")
    if not isinstance(path, str) or not REL_PATH_RE.match(path) \
            or ".." in path or "//" in path or path.endswith("/"):
        raise ToolError("bad_path")
    server = _server(_need(getter, "LOBEHUB_SERVER"))
    token = _need(getter, "LOBEHUB_CLI_API_KEY")
    payload = json.dumps({"json": {"id": skill_id, "path": path}}, separators=(",", ":"))
    url = server + RESOURCE_SUFFIX + "?" + urllib.parse.urlencode({"input": payload})
    doc = _fetch_json(opener or make_opener(), urllib.request.Request(
        url,
        method="GET",
        headers={
            "X-API-Key": token,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    ))
    if not isinstance(doc, dict) or set(doc) != {"result"}:
        raise ToolError("bad_shape")
    try:
        result = doc["result"]
        if set(result) != {"data"} or set(result["data"]) != {"json"}:
            raise ToolError("bad_shape")
        data = result["data"]["json"]
    except (KeyError, TypeError):
        raise ToolError("bad_shape") from None
    blob = resource_bytes(data, path)
    if token.encode("utf-8") in blob:  # covers base64 content the leaf check cannot
        raise ToolError("reflected_credential")
    out = {"action": "skill-resource", "resource": data}
    _no_reflection(out, token)  # final output object, not just the payload
    return out


def main(argv=None):
    parser = _Parser(prog="auth-call", add_help=True)
    sub = parser.add_subparsers(dest="action", required=True)
    pr = sub.add_parser("pr-meta")
    pr.add_argument("--repo", required=True)
    pr.add_argument("--number", required=True, type=int)
    res = sub.add_parser("skill-resource")
    res.add_argument("--id", required=True)
    res.add_argument("--path", required=True)
    try:
        args = parser.parse_args(argv)
        out = (pr_meta(args.repo, args.number) if args.action == "pr-meta"
               else skill_resource(args.id, args.path))
    except ToolError as exc:
        code = str(exc)
    except Exception:
        # fixed code, no exception text and no traceback (never BaseException)
        code = "internal_error"
    else:
        sys.stdout.write(json.dumps({"ok": True, **out}, ensure_ascii=True) + "\n")
        return 0
    sys.stderr.write(json.dumps({"ok": False, "error": code}) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())

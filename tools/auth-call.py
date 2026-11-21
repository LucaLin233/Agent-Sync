#!/usr/bin/env python3
"""Authenticated read-only call: one fixed action; see repository README.

  pr-meta         GitHub GraphQL PR metadata (fixed query, typed variables)

No shell, arbitrary URL/query, proxy, redirect, TLS downgrade or key logging.
"""
import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

GRAPHQL_URL = "https://api.github.com/graphql"
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

NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
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


def main(argv=None):
    parser = _Parser(prog="auth-call", add_help=True)
    sub = parser.add_subparsers(dest="action", required=True)
    pr = sub.add_parser("pr-meta")
    pr.add_argument("--repo", required=True)
    pr.add_argument("--number", required=True, type=int)
    try:
        args = parser.parse_args(argv)
        out = pr_meta(args.repo, args.number)
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

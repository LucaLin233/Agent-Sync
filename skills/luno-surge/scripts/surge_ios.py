#!/usr/bin/env python3
"""Control Surge iOS through its localhost HTTP API."""
import argparse, errno, json, os, posixpath, secrets, ssl, stat, sys
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote, urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

# 脚本可能被 install.sh 以符号链接落到 PATH，故用 realpath 解析同级共享模块所在目录。
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _privacy import api_base_problem, dumps_redacted, redact_boundary  # noqa: E402

BASE = os.getenv("SURGE_HTTP_API_BASE", "http://127.0.0.1:6171").rstrip("/")
KEY = os.getenv("SURGE_API_KEY")


class _NoRedirect(HTTPRedirectHandler):
    """不跟随 3xx：默认 urlopen 会把 X-Key 原样转发到重定向目标（跨源泄漏认证头）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _RedactingParser(argparse.ArgumentParser):
    """`error()` 先过输出边界再写 stderr。

    `argparse` 会把取值原样拼进入参错误消息；不覆写时 `--raw password=<值>` 这类用法／取值
    错误会把凭据值写进 stderr。子解析器由 `add_subparsers()` 按父解析器类型创建，同口径生效。
    """

    def error(self, message):
        super().error(redact_boundary(str(message)))


def fail(message, code=2):
    print(redact_boundary(message), file=sys.stderr)
    raise SystemExit(code)


def validate_base():
    problem = api_base_problem(BASE)
    if problem:
        fail(problem)
    if not KEY:
        fail("SURGE_API_KEY is not set")


E_SECTION_SAFE_ENTRY = "E_SECTION_WRITE_REQUIRES_SAFE_ENTRY"


def _section_write_target(path):
    """规范化目标是否为分节写路由；大小写／百分号／点段／尾斜杠歧义写法一律归一到同一判定。"""
    try:
        probe = str(path)
        for _ in range(2):
            probe = unquote(probe)
        probe = probe.split("?")[0].split("#")[0].replace("\\", "/").lower()
        segs = [s for s in probe.split("/") if s not in ("", ".")]
        resolved = []
        for seg in segs:
            if seg == "..":
                if resolved:
                    resolved.pop()
                continue
            resolved.append(seg)
        return resolved == ["v1", "profiles", "section"]
    except Exception:
        return True


def request(method, path, body=None, dangerous=False, confirm=False):
    if str(method).upper() == "POST" and _section_write_target(path):
        fail(E_SECTION_SAFE_ENTRY)
    validate_base()
    if not path.startswith("/v1/"):
        fail("API path must start with /v1/")
    if "sensitive=1" in path and os.getenv("SURGE_ALLOW_SENSITIVE") != "1":
        fail("Sensitive profile export blocked; set SURGE_ALLOW_SENSITIVE=1 explicitly")
    if dangerous and not confirm:
        fail("This action requires --confirm-dangerous")
    data = None if body is None else json.dumps(body).encode()
    headers = {"X-Key": KEY, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with build_opener(_NoRedirect).open(req, timeout=30) as response:
            raw = response.read()
            ctype = response.headers.get("Content-Type", "")
    except HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        fail(f"HTTP {e.code}: {detail}", 1)
    except URLError as e:
        fail(f"Cannot reach Surge API at {BASE}: {e.reason}", 1)
    if "json" in ctype or raw[:1] in (b"{", b"["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def show(value):
    """成功路径与 fail() 同口径脱敏：策略/代理响应里的凭据字段不得原样进输出。"""
    if isinstance(value, (dict, list)):
        print(dumps_redacted(value, indent=2, sort_keys=True))
    else:
        print(redact_boundary(value))


# ── 安全分节写入：单节 GET → 原稿/revision 核 → 受控备份 → POST → GET 核验 ──────────
SECTION_FIELDS = ("name", "revision", "original", "content", "backup_dir")
SECTION_MAX_TEXT = 256 * 1024
SECTION_MAX_STDIN = 1024 * 1024
SECTION_MAX_RESPONSE = 1024 * 1024
_LOOPBACK_LITERAL = ("127.0.0.1", "::1")


class SectionStop(Exception):
    """固定错误 token + 退出码；消息只允许 token 与可选 HTTP 数值状态。"""

    def __init__(self, token, code, status=None):
        super().__init__(token)
        self.token, self.code, self.status = token, code, status


def _stop(token, code, status=None):
    raise SectionStop(token, code, status)


class _DupKey(ValueError):
    pass


def _strict_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise _DupKey("duplicate key")
        out[key] = value
    return out


def _reject_section_markup(value):
    for line in value.splitlines():
        probe = line.strip()
        if probe.startswith("[") and probe.endswith("]"):
            return True
        if probe.startswith("#!"):
            return True
    return False


def read_section_input(stream):
    """读一份非 TTY UTF-8 JSON 输入；任何异常都归为固定 token，不回显 argv 或片段。"""
    try:
        if stream is None or stream.isatty():
            _stop("E_INPUT", 2)
        source = getattr(stream, "buffer", stream)
        raw = source.read(SECTION_MAX_STDIN + 1)
    except (OSError, ValueError):
        _stop("E_INPUT", 2)
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > SECTION_MAX_STDIN:
        _stop("E_INPUT", 2)
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        _stop("E_INPUT", 2)
    if "\x00" in text:
        _stop("E_INPUT", 2)
    stripped = text.lstrip()
    try:
        value, end = json.JSONDecoder(object_pairs_hook=_strict_pairs).raw_decode(stripped)
    except (ValueError, RecursionError):
        _stop("E_INPUT", 2)
    if stripped[end:].strip():
        _stop("E_INPUT", 2)
    if not isinstance(value, dict) or set(value) != set(SECTION_FIELDS):
        _stop("E_INPUT", 2)
    for field in SECTION_FIELDS:
        if not isinstance(value[field], str) or "\x00" in value[field]:
            _stop("E_INPUT", 2)
        try:
            value[field].encode("utf-8")
        except UnicodeEncodeError:
            _stop("E_INPUT", 2)
    name = value["name"]
    # name 是分节名（如 Rule），不是 header 行：`[Rule]`／`#!include` 两种分隔符写法一律拒绝，
    # 否则合成入口会把它当成合法节名发出 POST。
    if not name or any(ch in name for ch in "\r\n\x00[]") or _reject_section_markup(name):
        _stop("E_INPUT", 2)
    revision = value["revision"]
    if not revision or len(revision) > 4096:
        _stop("E_INPUT", 2)
    for field in ("original", "content"):
        body = value[field]
        if not body or len(body.encode("utf-8")) > SECTION_MAX_TEXT:
            _stop("E_INPUT", 2)
        if _reject_section_markup(body):
            _stop("E_INPUT", 2)
    return value


def _section_origin():
    # urlparse 对畸形方括号 host 抛 ValueError，`.port` 对非法端口抛 ValueError：
    # 两者都在联网前发生，必须归为固定 E_BASE（否则真实入口退出 1 并以 traceback 回显 BASE）。
    try:
        parsed = urlparse(BASE)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        _stop("E_BASE", 2)
    if parsed.scheme not in ("http", "https"):
        _stop("E_BASE", 2)
    if parsed.username is not None or parsed.password is not None:
        _stop("E_BASE", 2)
    if parsed.query or parsed.fragment or parsed.params:
        _stop("E_BASE", 2)
    if parsed.path not in ("", "/"):
        _stop("E_BASE", 2)
    if not host or (port is not None and not 0 < port < 65536):
        _stop("E_BASE", 2)
    loopback = host in _LOOPBACK_LITERAL
    if parsed.scheme == "http" and not loopback:
        _stop("E_TLS_REQUIRED", 2)
    if parsed.scheme == "https" and not loopback and os.getenv("SURGE_ALLOW_REMOTE") != "1":
        _stop("E_BASE", 2)
    return parsed


def section_http(method, path, body=None, phase="read"):
    """专用传输：不支持代理环境、不跟随重定向、有界读取；错误只给固定 token（+HTTP数值状态）。"""
    _section_origin()
    if not KEY:
        _stop("E_KEY", 2)
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"X-Key": KEY, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with build_opener(ProxyHandler({}), _NoRedirect).open(req, timeout=30) as response:
            raw = response.read(SECTION_MAX_RESPONSE + 1)
    except HTTPError as exc:
        if phase == "post":
            if 400 <= exc.code < 500:
                _stop("E_REJECTED", 4, exc.code)
            _stop("E_WRITE_UNKNOWN", 5, exc.code)
        if phase == "verify":
            _stop("E_VERIFY_FAILED", 5, exc.code)
        _stop("E_READ_FAILED", 4, exc.code)
    except (URLError, OSError, ValueError):
        if phase == "post":
            _stop("E_WRITE_UNKNOWN", 5)
        if phase == "verify":
            _stop("E_VERIFY_FAILED", 5)
        _stop("E_READ_FAILED", 4)
    except HTTPException:
        # 传输层协议异常（IncompleteRead／BadStatusLine 等）不是 ValueError/OSError：
        # 写阶段一律「结果未知」且不重试，读／核验阶段按各自阶段归类，不给 traceback。
        if phase == "post":
            _stop("E_WRITE_UNKNOWN", 5)
        if phase == "verify":
            _stop("E_VERIFY_FAILED", 5)
        _stop("E_READ_FAILED", 4)
    if len(raw) > SECTION_MAX_RESPONSE:
        if phase == "post":
            _stop("E_WRITE_UNKNOWN", 5)
        if phase == "verify":
            _stop("E_VERIFY_FAILED", 5)
        _stop("E_READ_FAILED", 4)
    return raw


def decode_section(raw, phase="read"):
    """只解码已文档化的 content:string 与 revision:非空 string；未知字段不展示、不参与决策。

    写后阶段（phase="verify"）的坏响应是「写已发生但无法核验」：token/退出码须为
    E_VERIFY_FAILED/5，不得降级成读失败 4，否则调用方会误判为「没写成」。
    """
    token, code = ("E_VERIFY_FAILED", 5) if phase == "verify" else ("E_READ_DECODE", 4)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        _stop(token, code)
    if not isinstance(value, dict):
        _stop(token, code)
    content, revision = value.get("content"), value.get("revision")
    if not isinstance(content, str) or not isinstance(revision, str) or not revision:
        _stop(token, code)
    return content, revision


def _open_backup_dir(path):
    """从 `/` 起逐级 O_DIRECTORY|O_NOFOLLOW 打开，返回持有的末级目录 fd。

    逐级 lstat 后再按完整路径 open 存在祖先符号链接替换竞态（检查后换链，写入落到别处），
    故这里只沿目录 fd 逐级下降、不再按完整路径重解析，末级 fd 由调用方持有并在其上写文件。
    歧义分量（`//`、尾斜杠、`.`、`..`、NUL）拒绝；末级须为本用户所有、权限恰为 0700。
    任何不合格都在联网前抛出，故无效目录不会先 GET 再拒绝。
    """
    if not isinstance(path, str) or not path or not os.path.isabs(path) or "\x00" in path:
        _stop("E_BACKUP_DIR", 2)
    parts = path.split("/")[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        _stop("E_BACKUP_DIR", 2)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = None
    try:
        fd = os.open("/", flags)
        for part in parts:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
    except OSError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        _stop("E_BACKUP_DIR", 2)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):   # 精确 0700：0500 等只读目录也拒绝
        try:
            os.close(fd)
        except OSError:
            pass
        _stop("E_BACKUP_DIR", 2)
    return fd


def _write_all(fd, payload):
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(errno.EIO, "short write")
        view = view[written:]


def _discard_created(dir_fd, filename, ident):
    """只清理由本次创建、且身份仍匹配（dev/ino）的文件；既有文件一律不碰。"""
    try:
        info = os.stat(filename, dir_fd=dir_fd, follow_symlinks=False)
    except OSError:
        return
    if ident is not None and (info.st_dev, info.st_ino) == (ident.st_dev, ident.st_ino):
        try:
            os.unlink(filename, dir_fd=dir_fd)
        except OSError:
            pass


def save_section_backup(edit, dir_fd):
    """在调用方持有的目录 fd 上写实际 GET 原文/revision：0600、O_EXCL、fsync 后读回核对。

    `O_EXCL` 失败（EEXIST）与 fsync／读回失败都在 POST 之前抛出；清理只针对本次创建且
    dev/ino 仍匹配的文件，绝不 unlink 同名的既有文件。
    """
    payload = json.dumps({
        "format": 1,
        "name": edit["name"],
        "origin": BASE,
        "original": edit["original"],
        "revision": edit["revision"],
        "intended_content": edit["content"],
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")
    filename = "section-" + secrets.token_hex(20) + ".json"
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    fd = None
    created = False
    ident = None
    try:
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600, dir_fd=dir_fd)
        created = True
        ident = os.fstat(fd)
        _write_all(fd, payload)
        os.fsync(fd)
        info = os.fstat(fd)
        if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
            raise OSError(errno.EPERM, "bad backup mode")
        os.close(fd)
        fd = None
        os.fsync(dir_fd)
        back_fd = os.open(filename, os.O_RDONLY | nofollow, dir_fd=dir_fd)
        try:
            back = b""
            while True:
                chunk = os.read(back_fd, 65536)
                if not chunk:
                    break
                back += chunk
        finally:
            os.close(back_fd)
        if back != payload:
            raise OSError(errno.EIO, "backup readback mismatch")
        return os.path.join(edit["backup_dir"], filename)
    except OSError:
        if created:
            _discard_created(dir_fd, filename, ident)
        _stop("E_BACKUP_WRITE", 2)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def replace_section(edit):
    """真实编排：备份目录 fd 先于联网取得 → GET 核原稿/revision → 备份 → POST → 写后 GET 核验。"""
    dir_fd = _open_backup_dir(edit["backup_dir"])
    try:
        query = "/v1/profiles/section?" + urlencode({"name": edit["name"]})
        current_content, current_revision = decode_section(section_http("GET", query))
        if current_content != edit["original"]:
            _stop("E_ORIGINAL_CHANGED", 3)
        if current_revision != edit["revision"]:
            _stop("E_REVISION_CHANGED", 3)
        save_section_backup(edit, dir_fd)
        section_http("POST", "/v1/profiles/section",
                     {"name": edit["name"], "content": edit["content"],
                      "revision": current_revision}, phase="post")
        verified_content, verified_revision = decode_section(
            section_http("GET", query, phase="verify"), phase="verify")
        if verified_content != edit["content"] or not verified_revision:
            _stop("E_VERIFY_FAILED", 5)
        return {"ok": True, "changed": current_content != edit["content"], "verified": True}
    finally:
        try:
            os.close(dir_fd)
        except OSError:
            pass


def run_section_replace(confirm):
    if not confirm:
        _print_section_stop(SectionStop("E_CONFIRM", 2))
    try:
        edit = read_section_input(sys.stdin)
        result = replace_section(edit)
    except SectionStop as stop:
        _print_section_stop(stop)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


def _print_section_stop(stop):
    message = stop.token if stop.status is None else "%s %d" % (stop.token, stop.status)
    print(message, file=sys.stderr)
    raise SystemExit(stop.code)


SECTION_ENTRY_ARGV = ("section", "replace", "--input", "-")


def _is_section_entry(argv):
    """判断本次调用是否落在安全入口（`section …`）：只看首个非选项词。

    argparse 会把不合格取值原样拼进入参错误并回显（含凭据以外的合成哨兵），故安全入口
    不进 argparse：形状不合一律固定 E_INPUT，不回显任何 argv 片段。
    """
    for token in argv:
        if token.startswith("-"):
            continue
        return token == "section"
    return False


def _section_entry_confirm(argv):
    """只接受固定写法 `[--confirm-dangerous] section replace --input -`；其余 E_INPUT。"""
    confirm = False
    rest = []
    for token in argv:
        if token == "--confirm-dangerous" and not confirm:
            confirm = True
        else:
            rest.append(token)
    if rest != list(SECTION_ENTRY_ARGV):
        _print_section_stop(SectionStop("E_INPUT", 2))
    return confirm


def main():
    if _is_section_entry(sys.argv[1:]):
        run_section_replace(_section_entry_confirm(sys.argv[1:]))
        return
    p = _RedactingParser(description=__doc__)
    p.add_argument("--confirm-dangerous", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    raw = sub.add_parser("request", help="Call an API endpoint")
    raw.add_argument("method", choices=("GET", "POST"))
    raw.add_argument("path")
    raw.add_argument("json_body", nargs="?")
    sub.add_parser("status")
    outbound = sub.add_parser("outbound")
    outbound.add_argument("mode", nargs="?", choices=("direct", "proxy", "rule"))
    feature = sub.add_parser("feature")
    feature.add_argument("name", choices=("mitm", "capture", "rewrite", "scripting"))
    feature.add_argument("state", nargs="?", choices=("on", "off"))
    sub.add_parser("policies")
    sub.add_parser("groups")
    select = sub.add_parser("select")
    select.add_argument("group")
    select.add_argument("policy", nargs="?")
    recent = sub.add_parser("requests")
    recent.add_argument("kind", choices=("recent", "active"), default="recent", nargs="?")
    kill = sub.add_parser("kill")
    kill.add_argument("id", type=int)
    sub.add_parser("profile")
    sub.add_parser("reload")
    sub.add_parser("dns")
    sub.add_parser("flush-dns")
    sub.add_parser("modules")
    module = sub.add_parser("module")
    module.add_argument("name")
    module.add_argument("state", choices=("on", "off"))
    for name in ("events", "rules", "traffic"):
        sub.add_parser(name)
    sub.add_parser("metrics", help="Read Prometheus metrics from /v1/metrics")
    sub.add_parser("stop")
    section = sub.add_parser("section", help="Single-section edit through the safe entry")
    section_sub = section.add_subparsers(dest="section_command", required=True)
    section_replace = section_sub.add_parser("replace")
    section_replace.add_argument("--input", dest="input_mode")
    section_replace.add_argument("extra", nargs="*")
    args = p.parse_args()

    c = args.command
    if c == "section":
        # 正常路径已由 main() 的 argv 前置护栏截走；此处仅防御性保底。
        _print_section_stop(SectionStop("E_INPUT", 2))
    if c == "request":
        # 分节写路由必须在 json 解析、取密与联网之前拒绝：非法 JSON 也只能得到固定 token，
        # 不能先抛 JSONDecodeError 的 traceback。
        if str(args.method).upper() == "POST" and _section_write_target(args.path):
            fail(E_SECTION_SAFE_ENTRY)
        body = json.loads(args.json_body) if args.json_body else None
        show(request(args.method, args.path, body,
                     dangerous=args.path == "/v1/stop", confirm=args.confirm_dangerous))
    elif c == "status":
        result = {
            "outbound": request("GET", "/v1/outbound"),
            "features": {n: request("GET", f"/v1/features/{n}") for n in ("mitm", "capture", "rewrite", "scripting")},
        }
        show(result)
    elif c == "outbound":
        show(request("POST", "/v1/outbound", {"mode": args.mode}) if args.mode else request("GET", "/v1/outbound"))
    elif c == "feature":
        path = f"/v1/features/{args.name}"
        show(request("POST", path, {"enabled": args.state == "on"}) if args.state else request("GET", path))
    elif c == "policies": show(request("GET", "/v1/policies"))
    elif c == "groups": show(request("GET", "/v1/policy_groups"))
    elif c == "select":
        if args.policy:
            groups = request("GET", "/v1/policy_groups")
            if args.group not in groups:
                fail(f"Unknown policy group: {args.group}")
            available = {item.get("name") for item in groups[args.group] if item.get("enabled", True)}
            if args.policy not in available:
                fail(f"Policy is not an enabled option of {args.group}: {args.policy}")
            show(request("POST", "/v1/policy_groups/select", {"group_name": args.group, "policy": args.policy}))
        else:
            show(request("GET", "/v1/policy_groups/select?" + urlencode({"group_name": args.group})))
    elif c == "requests": show(request("GET", f"/v1/requests/{args.kind}"))
    elif c == "kill": show(request("POST", "/v1/requests/kill", {"id": args.id}))
    elif c == "profile": show(request("GET", "/v1/profiles/current?sensitive=0"))
    elif c == "reload": show(request("POST", "/v1/profiles/reload", {}))
    elif c == "dns": show(request("GET", "/v1/dns"))
    elif c == "flush-dns": show(request("POST", "/v1/dns/flush", {}))
    elif c == "modules": show(request("GET", "/v1/modules"))
    elif c == "module": show(request("POST", "/v1/modules", {args.name: args.state == "on"}))
    elif c in ("events", "rules", "traffic"): show(request("GET", f"/v1/{c}"))
    elif c == "metrics": show(request("GET", "/v1/metrics"))
    elif c == "stop": show(request("POST", "/v1/stop", {}, dangerous=True, confirm=args.confirm_dangerous))


if __name__ == "__main__":
    main()

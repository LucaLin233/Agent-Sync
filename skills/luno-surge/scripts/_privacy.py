#!/usr/bin/env python3
"""luno-surge 脚本共用的输出脱敏与出网凭据边界（surge_ios／surge_cli／test_policy_descriptor）。

  * `redact_obj(value)`：结构化结果按敏感键**递归整值替换**为 `"<redacted>"`；
  * `redact_text(text)`：文本路径逐条规则替换（代理行、键值、转义内层 JSON、Cookie、
    URL userinfo、PEM、JWT、长不透明串、token 前缀）；
  * `redact_boundary(text)`：输出边界入口——合法 JSON 文档按结构处理且输出仍可解析，其余走文本路径；
  * `api_base_problem(base)`：scheme／URL userinfo／非本机主机统一门禁；凭据只来自
    `SURGE_API_KEY`／`--password-stdin`，URL 内嵌 userinfo 一律拒绝。

方向一律 fail-closed（宁可多抹）。本模块只做输出兜底，不是秘密识别器，也不拦截输入或命令；
不宣称任意文本无秘密。已知残余（仅作诊断展示，不用于配置等价、回导、路径执行或机器决策）：
  * 敏感键的无引号值按逗号／分号／空白截断，`password=aaa,bbb` → `password=<redacted>,bbb`；
  * 紧贴 `=` 的 40+ 字符长串（`NAME=<长串>`）不抹，未命中键名与形态的短值不抹；
  * 身份词 `user`／`username` 只按整键命中（`USER_AGENT` 不连坐，代价是 `DB_USER` 不抹）；
  * 过抹：长路径／文件名（`_BLOB`）、未列协议代理行端口之后整段（`_PROXY_LINE_ANY`）、
    含敏感词段的元数据键（`token_count` 等）、`PUBLIC KEY` 块（`_PEM_BLOCK`）；
  * 跨物理行的敏感容器整份返回 `<redacted>`，同份普通诊断字段一并丢失。
"""
import json
import os
import re
from urllib.parse import urlparse

REDACTED = "<redacted>"

_LOOPBACK = ("127.0.0.1", "localhost", "::1")

_AUTH = r"(?:authorization|proxy-authorization|auth|authz)"
_AUTH_SCHEMES = r"(?:bearer|basic|digest|negotiate|ntlm|aws4-hmac-sha256)"
# 凭据词：可参与分隔段匹配（`POSTGRES_PASSWORD`、`AWS_SECRET_ACCESS_KEY`）。
_SEG_WORDS = (r"(?:password|passwd|pwd|psk|uuid|auth[-_]?key|private[-_]key"
              r"|token|api[-_]?key|x[-_]key|secret|credential|signature|sig"
              r"|access[-_]?key[-_]?id|base64|cookie)")
# 身份词：只按整键命中，否则 `user-agent` 会被连坐。
_PLAIN_WORDS = r"(?:username|user)"

# 前缀驼峰（`proxyPassword`）：`(?-i:)` 关掉外层 IGNORECASE，否则 `[A-Z]` 退化成任意字母。
_CAMEL = r"(?:(?-i:[A-Za-z0-9]+)(?=(?-i:[A-Z])))?"
_PLURAL = r"s?"
_KEYNUM = r"[0-9]{0,3}"            # `token1`／`password2`
_SEG_PRE = r"(?:(?-i:[A-Za-z0-9]+)[-_])*"
_SEG_POST = r"(?:[-_](?-i:[A-Za-z0-9]+))*"
_SEGMENTED = (r"(?:" + _SEG_PRE + r"(?:" + _SEG_WORDS + r")" + _PLURAL + _KEYNUM
              + _SEG_POST + r")")
_PFX = r"(?P<pfx>" + _CAMEL + r")"
_KEY = r"(?P<k>(?:" + _SEGMENTED + r"|(?:" + _PLAIN_WORDS + r")" + _PLURAL + _KEYNUM + r"))"
_AUTH_WORD = r"(?P<ak>(?:" + _AUTH + r")" + _PLURAL + r")"

# 引号可被反斜杠转义（内层 JSON 串）：键引号与值引号两侧都允许 `\`。
_QUOTE = r"(?:\\*[\"'])?"
_DQ = r'\\*"(?:[^"\\]|\\.)*\\*"'
_SQ = r"\\*'(?:[^'\\]|\\.)*\\*'"
# 值体非贪心：贪心会把尾引号前的 `\` 吃进值体，转义不对称。
_QUOTED_VALUE = re.compile(r"(?s)(?P<lead>\\*[\"'])(?P<body>.*?)(?P<tail>\\*[\"'])$")
_VALUE_TAIL_BREAK = ",}]) \t\r\n"


def _value_cut(body):
    """内层转义串里真实值的结束位置（转义引号后紧跟分隔符或值体末尾）；找不到返回 None。"""
    for index in range(len(body) - 1):
        if body[index] == "\\" and body[index + 1] in "\"'":
            after = body[index + 2:index + 3]
            if not after or after in _VALUE_TAIL_BREAK:
                return index
    return None


def _quote_swap(value):
    """只替换引号值内部，两侧引号（含转义反斜杠）与重切出的残片原样保留。"""
    matched = _QUOTED_VALUE.match(value)
    if not matched:
        return REDACTED
    lead, body, tail = matched.group("lead"), matched.group("body"), matched.group("tail")
    cut = _value_cut(body)
    if cut is not None:
        tail = body[cut:] + tail
    return lead + REDACTED + tail


def _key_label(matched):
    return matched.group("pfx") + matched.group("k")


def _quoted_marker(key_quote, text=REDACTED):
    """标记按键引号的转义形态输出，内层 JSON 串仍合法。"""
    inner = '\\"' if "\\" in key_quote else '"'
    return "%s%s%s" % (inner, text, inner)


# 1a) 认证字段的引号值；双／单引号各按自身转义规则匹配。
_AUTH_QUOTED = re.compile(
    r"(?i)(?P<qk>" + _QUOTE + r")(?:\b|(?<=\\n))" + _PFX + _AUTH_WORD + r"(?P=qk)"
    r"(?P<sep>\s*[:=]\s*)(?P<val>" + _DQ + r"|" + _SQ + r")")


def _auth_quoted(matched):
    return "%s%s%s%s%s" % (matched.group("qk"), matched.group("ak"), matched.group("qk"),
                           matched.group("sep"), _quote_swap(matched.group("val")))


# 1b) 认证字段带方案词 → 整行值。
_AUTH_SCHEME = re.compile(
    r"(?i)(?P<qk>" + _QUOTE + r")(?:\b|(?<=\\n))" + _PFX + _AUTH_WORD + r"(?P=qk)"
    r"(?P<sep>[ \t]*[:=][ \t]*)(?P<val>" + _AUTH_SCHEMES + r"\b[^\n]*)")


def _auth_scheme(matched):
    return '%s%s%s%s"<redacted>"' % (matched.group("qk"), matched.group("ak"),
                                     matched.group("qk"), matched.group("sep"))


# 1c) 其余认证值止于逗号／分号／换行（`}`／`]` 不终止，防 `SYNTH}SECRET` 后半泄漏）。
#     输入里的同形标记不可信：标记之后的残余一律丢弃，仅全是闭合符时保留。
_AUTH_BARE = re.compile(
    r"(?i)(?P<qk>" + _QUOTE + r")(?:\b|(?<=\\n))" + _PFX + _AUTH_WORD + r"(?P=qk)"
    r"(?P<sep>[ \t]*[:=][ \t]*)(?P<val>[^\n,;]+)")
_MARKERS = ('"<redacted>"', "'<redacted>'", '\\"<redacted>\\"', "\\'<redacted>\\'")


def _auth_bare(matched):
    value = matched.group("val")
    head = "%s%s%s%s" % (matched.group("qk"), matched.group("ak"), matched.group("qk"),
                         matched.group("sep"))
    for marker in _MARKERS:
        if value.startswith(marker):
            rest = value[len(marker):]
            keep = rest if rest and set(rest) <= set("}] \t\r\\") else ""
            return head + marker + keep
    return head + '"<redacted>"'

# 2) 敏感键的单层数组／对象值：整段替换。
_KEY_CONTAINER = re.compile(
    r"(?i)(?P<qk>" + _QUOTE + r")(?:\b|(?<=\\n))" + _PFX + _KEY + r"(?P=qk)"
    r"(?P<sep>\s*[:=]\s*)(?P<val>\[[^\[\]]*\]|\{[^{}]*\})")
_CONTAINER_VALUE = re.compile(r"(?s)(?P<lead>[\[{])(?P<body>.*)(?P<tail>[\]}])$")


def _container_cut(body):
    """内层转义串里容器真实闭合符的位置：其后只剩闭合符／转义／空白。"""
    for index in range(len(body) - 1, -1, -1):
        if body[index] in "}]" and (index == 0 or body[index - 1] != "\\"):
            rest = body[index:]
            if set(rest) <= set("}]{[]\"'\\ \t\r"):
                return index
    return None


def _container_swap(value):
    matched = _CONTAINER_VALUE.match(value)
    if not matched:
        return REDACTED
    lead, body, tail = matched.group("lead"), matched.group("body"), matched.group("tail")
    cut = _container_cut(body)
    if cut is not None:
        return lead + REDACTED + body[cut:] + tail
    return lead + REDACTED + tail


def _key_container(matched):
    return "%s%s%s%s[%s]" % (matched.group("qk"), _key_label(matched), matched.group("qk"),
                             matched.group("sep"),
                             _quoted_marker(matched.group("qk"), _container_swap(
                                 matched.group("val")).strip("[]{}")))


# 2b) 容器形状兜底：嵌套／未闭合容器把该逻辑行剩余整段隐藏，输出与 2) 同形（幂等）。
#     `rest` 必须从容器开头起匹配，否则同行前置裸值键会吃掉扫描位置、漏掉后续敏感键。
_KEY_CONTAINER_TAIL = re.compile(
    r"(?i)(?P<qk>" + _QUOTE + r")(?:\b|(?<=\\n))" + _PFX + _KEY + r"(?P=qk)"
    r"(?P<sep>\s*[:=]\s*)(?P<rest>[ \t]*[\[{](?:(?!\\n)[^\n])*)")
_CONTAINER_LEAD = re.compile(r"^[ \t]*[\[\{]")


def _key_container_tail(matched):
    rest = matched.group("rest")
    if _CONTAINER_LEAD.match(rest) is None:
        return matched.group(0)
    if (sum(rest.count(c) for c in "[{") > 1
            or sum(rest.count(c) for c in "]}") == 0):
        return "%s%s%s%s[%s]" % (matched.group("qk"), _key_label(matched), matched.group("qk"),
                                 matched.group("sep"), _quoted_marker(matched.group("qk")))
    return matched.group(0)


# 3) 敏感键的带引号值。
_KEY_QUOTED = re.compile(
    r"(?i)(?P<qk>" + _QUOTE + r")(?:\b|(?<=\\n))" + _PFX + _KEY + r"(?P=qk)"
    r"(?P<sep>\s*[:=]\s*)(?P<val>" + _DQ + r"|" + _SQ + r")")


def _key_quoted(matched):
    return "%s%s%s%s%s" % (matched.group("qk"), _key_label(matched), matched.group("qk"),
                           matched.group("sep"), _quote_swap(matched.group("val")))


# 3b) 引号尾段兜底（非代理行）：值以引号开头却未在本逻辑行闭合，或裸值后紧跟引号字段 → 整段隐藏。
_KEY_QUOTE_TAIL = re.compile(
    r"(?i)(?P<qk>" + _QUOTE + r")(?:\b|(?<=\\n))" + _PFX + _KEY + r"(?P=qk)"
    r"(?P<sep>[ \t]*[:=][ \t]*)(?P<rest>(?:(?!\\n)[^\n])*)")
_LEAD_QUOTED = re.compile(r"^(?P<q>\\*[\"'])")
# 只有整段即 2) 的规范标记容器才豁免；输入自带标记不得自我豁免。
_CANONICAL_MARKER_LINE = re.compile(
    r"^[ \t]*[\[{][ \t]*\\*[\"']?" + re.escape(REDACTED) + r"\\*[\"']?[ \t]*[\]}][ \t\r]*$")


def _key_quote_tail(matched, allow_container=False):
    rest = matched.group("rest")
    head = "%s%s%s%s" % (matched.group("qk"), _key_label(matched), matched.group("qk"),
                         matched.group("sep"))
    if not rest or not any(q in rest for q in "\"'"):
        return matched.group(0)
    if _CANONICAL_MARKER_LINE.match(rest):
        return matched.group(0)
    # 容器值豁免只在整份输入是合法 JSON 文档时成立（括号必配对）；非 JSON 文本里括号计数
    # 可被引号内字符骗过（`token=["x]", "S"`），故落回整段隐藏。
    if allow_container and _CONTAINER_LEAD.match(rest) is not None:
        return matched.group(0)
    lead = _LEAD_QUOTED.match(rest)
    if lead is not None:
        after = rest[len(lead.group("q")):]
        close = after.find(lead.group("q")[-1])
        if close >= 0 and (not after[close + 1:] or after[close + 1] in _VALUE_TAIL_BREAK):
            return matched.group(0)
    return head + REDACTED


# 4) 敏感键的裸值：止于逗号／分号／空白，且不跨字面 `\n`（记录边界）。
_KEY_BARE = re.compile(r"(?i)(?:\b|(?<=\\n))" + _PFX + _KEY
                       + r"\b\s*[:=]\s*(?:(?!\\n)[^\s,;])+")


def _key_bare(matched):
    return _key_label(matched) + "=<redacted>"


# 5) 已知 token 前缀（含 Google `AIza`、AWS `AKIA`／`ASIA`）。
_TOKEN_PREFIX = re.compile(r"(?i)\b(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{16,}"
                           r"|\bAIza[0-9A-Za-z_\-]{20,}"
                           r"|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")


# 6) Surge 代理行 `NAME = <type>, <host>, <port>, <凭据...>`：类型 → (端口后起始下标, 个数)。
#    http/https/socks5(-tls) 是官方可选位置式 `username, password`；其余为防御性位置兜底，
#    命名凭据由键值规则处理。未列类型交 6b) 形状兜底。
_PROXY_CREDENTIALS = {
    "http": (2, 2), "https": (2, 2), "socks5": (2, 2), "socks5-tls": (2, 2), "ssh": (2, 2),
    "trojan": (2, 1), "snell": (2, 1), "vmess": (2, 1), "hysteria2": (2, 1), "tuic": (2, 1),
}
# 行首：真行首／`\n`（内层转义串）／行内引号之后，可选 `git diff` 的 `+`／`-`。
_PROXY_LINE = re.compile(
    r"(?im)(?P<pfx>(?:^|[ \t]|\\n|[\"'])[ \t]*(?:[+-][ \t]*)?[ \t]*[\w.\-\u0080-\U0010ffff]+[ \t]*=[ \t]*)"
    r"(?P<type>" + "|".join(sorted(_PROXY_CREDENTIALS, key=len, reverse=True)) + r")"
    r"(?P<sep>[ \t]*,[ \t]*)"
    r"""(?P<fields>(?:(?!\\n)[^\n"']|"(?:\\[\s\S]|[^"\\])*(?:"|\\?$)|'(?:\\[\s\S]|[^'\\])*(?:'|\\?$))*)""")


def _redact_fields(fields, start, count):
    """按下标整值替换凭据位；不按字段外形放行（`sni=…`、`headers=Cookie:…` 都可能携密）。"""
    # 尾段含引号（官方：值含逗号须加引号）时不猜字段边界，整段抹除。
    prefix = fields.split(",", start)
    if len(prefix) > start and any(q in prefix[-1] for q in "\"'"):
        return ",".join(prefix[:-1]) + ", " + REDACTED
    parts = fields.split(",")
    if len(parts) <= start:
        return fields
    for index in range(start, min(start + count, len(parts))):
        if not parts[index].strip(" \t"):
            continue
        lead = len(parts[index]) - len(parts[index].lstrip(" \t"))
        tail = len(parts[index]) - len(parts[index].rstrip(" \t"))
        parts[index] = " " * lead + REDACTED + " " * tail
    return ",".join(parts)


def _proxy_line(matched):
    start, count = _PROXY_CREDENTIALS[matched.group("type").lower()]
    return "%s%s%s%s" % (matched.group("pfx"), matched.group("type"), matched.group("sep"),
                         _redact_fields(matched.group("fields"), start, count))


# 6b) 未列协议形状兜底：`NAME = <类型>, <host>, <端口>, …` 端口之后整段抹除。端口须为完整字段，
#     策略组／多值行不受影响；排除的是完整已列协议字段（含逗号），故 `tuic-v5` 仍落入本规则。
_UNLISTED_TYPE = (r"(?!(?:" + "|".join(sorted(_PROXY_CREDENTIALS, key=len, reverse=True))
                  + r")[ \t]*,)")
_PROXY_LINE_ANY = re.compile(
    r"(?im)(?P<pfx>(?:^|[ \t]|\\n|[\"'])[ \t]*(?:[+-][ \t]*)?[ \t]*[\w.\-\u0080-\U0010ffff]+[ \t]*=[ \t]*)"
    r"(?P<type>" + _UNLISTED_TYPE + r"[a-z][a-z0-9\-]*)(?P<sep>[ \t]*,[ \t]*)"
    r"(?P<host>[^,\n\"']+?)(?P<portsep>[ \t]*,[ \t]*)(?P<port>[0-9]{1,5})"
    r"(?=[ \t]*(?:,|\\n|$))(?P<rest>(?:(?!\\n)[^\n])*)")


def _proxy_line_any(matched):
    head = "%s%s%s%s%s%s" % (matched.group("pfx"), matched.group("type"), matched.group("sep"),
                             matched.group("host"), matched.group("portsep"),
                             matched.group("port"))
    rest = matched.group("rest")
    if not rest.strip(" \t,\r"):
        return head + rest
    return head + ", " + REDACTED


# 2c) Cookie（非代理行）：引号值按引号形态替换，其余隐藏到逻辑行末。
_COOKIE = re.compile(
    r"(?i)(?P<qk>" + _QUOTE + r")(?:\b|(?<=\\n))(?P<ck>set[-_]?cookie|cookie)(?P=qk)"
    r"(?P<sep>[ \t]*[:=][ \t]*)(?P<val>" + _DQ + r"|" + _SQ + r"|(?:(?!\\n)[^\n])*)")


def _cookie(matched):
    head = "%s%s%s%s" % (matched.group("qk"), matched.group("ck"), matched.group("qk"),
                         matched.group("sep"))
    value = matched.group("val")
    if value[:1] in ("\"", "'"):
        return head + _quote_swap(value)
    return head + REDACTED


# 7) 与键名无关的秘密形态：URL userinfo、PEM 块、JWT、长不透明串。
_USERINFO = re.compile(r"(?i)(?P<scheme>\b[a-z][a-z0-9+.\-]*://)(?P<ui>[^/\s?#@\"'\\]*@)")
_PEM_BLOCK = re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}KEY[A-Z0-9 ]{0,20}-----[\s\S]*?"
                        r"-----END [A-Z0-9 ]{0,40}-----")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{2,}")
_BLOB = re.compile(r"(?<![A-Za-z0-9+/_\-=])[A-Za-z0-9+/_\-]{40,}={0,2}(?![A-Za-z0-9+/_\-=])")


def _userinfo(matched):
    return matched.group("scheme") + REDACTED + "@"


# Keystore 段：段内值整段隐藏，键名与行结构保留；无分隔符的行整行隐藏。
_KEYSTORE_SECTION = re.compile(r"(?im)^(?P<hdr>[ \t]*\[keystore[^\]\n]*\][ \t]*(?:\r?\n|\Z))"
                               r"(?P<body>(?:(?!^[ \t]*\[)[\s\S])*)")


def _keystore_values(text):
    def hide(matched):
        hidden = []
        for line in matched.group("body").split("\n"):
            cut = min([index for index in (line.find("="), line.find(":")) if index >= 0],
                      default=-1)
            if not line.strip():
                hidden.append(line)
            elif cut < 0:
                hidden.append(REDACTED)
            else:
                hidden.append(line[:cut].rstrip() + " = " + REDACTED)
        return matched.group("hdr") + "\n".join(hidden)

    return _KEYSTORE_SECTION.sub(hide, str(text))


_RULES = (
    # 代理行先于键值规则：否则裸值规则先吞掉开引号，尾段兜底看不到引号。
    (_PROXY_LINE, _proxy_line),
    (_PROXY_LINE_ANY, _proxy_line_any),
    (_AUTH_QUOTED, _auth_quoted),
    (_AUTH_SCHEME, _auth_scheme),
    (_AUTH_BARE, _auth_bare),
    (_COOKIE, _cookie),
    (_KEY_CONTAINER, _key_container),
    (_KEY_CONTAINER_TAIL, _key_container_tail),
    (_KEY_QUOTED, _key_quoted),
    (_KEY_QUOTE_TAIL, _key_quote_tail),
    (_KEY_BARE, _key_bare),
    (_PEM_BLOCK, lambda matched: REDACTED),
    (_JWT, lambda matched: REDACTED),
    (_USERINFO, _userinfo),
    (_BLOB, lambda matched: REDACTED),
    (_TOKEN_PREFIX, lambda matched: REDACTED),
)

# 结构化路径的键名判据与文本路径同源。
_SENSITIVE_KEY = re.compile(
    r"^(?:" + _CAMEL + r"(?:" + _SEGMENTED
    + r"|(?:" + _PLAIN_WORDS + r")" + _PLURAL + _KEYNUM
    + r"|(?:" + _AUTH + r")" + _PLURAL + _KEYNUM + r"))$", re.I)


# 跨物理行敏感容器：行内「敏感键 =/: 容器开头」且括号不平衡 → 整份 fail-closed。
# `rest` 锚定容器开头，同行前置键不会吃掉扫描位置。
_CONTAINER_OPEN = re.compile(
    r"(?i)(?P<qk>" + _QUOTE + r")(?:\b|(?<=\\n))" + _PFX + _KEY + r"(?P=qk)"
    r"(?P<sep>[ \t]*[:=][ \t]*)"
    r"(?P<rest>[ \t]*(?:\\*[\"'])?[ \t]*[\[{](?:(?!\\n)[^\n])*)")
_CONTAINER_HEAD = re.compile(r"^[ \t]*(?:\\*[\"'])?[ \t]*[\[{]")


def _has_unclosed_container(text):
    for line in str(text).split("\n"):
        for matched in _CONTAINER_OPEN.finditer(line):
            rest = matched.group("rest")
            if _CONTAINER_HEAD.match(rest) is None:
                continue
            if rest.count("[") > rest.count("]") or rest.count("{") > rest.count("}"):
                return True
    return False


def redact_text(text):
    """文本路径。跨物理行敏感容器整份返回 `REDACTED`；输入是合法 JSON 文档而流水线输出
    不再合法时，改走结构化路由（抹除范围只增不减）。"""
    source = str(text)
    document = _json_document(source)
    if _has_unclosed_container(source):
        out = REDACTED
    else:
        out = _keystore_values(source)
        for pattern, replacement in _RULES:
            if document is not None and pattern is _KEY_QUOTE_TAIL:
                out = pattern.sub(
                    lambda hit: _key_quote_tail(hit, allow_container=True), out)
            else:
                out = pattern.sub(replacement, out)
    if document is not None and _json_document(out) is None:
        return _json_route(source, document)
    return out


def _is_sensitive_key(key):
    return isinstance(key, str) and _SENSITIVE_KEY.match(key) is not None


def redact_obj(value):
    """结构化路径：命中敏感键即把整个值（含嵌套）替换为 `"<redacted>"`。"""
    if isinstance(value, dict):
        return {key: (REDACTED if _is_sensitive_key(key) else redact_obj(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_obj(item) for item in value)
    if isinstance(value, str):
        # 字符串值在序列化之前过边界；序列化后再跑文本路径会吃掉 JSON 包装字符。
        return redact_boundary(value)
    return value


def dumps_redacted(value, **kwargs):
    """结构化脱敏后再 `json.dumps`；不得在 dumps 之后再跑文本路径。"""
    options = {"ensure_ascii": False}
    options.update(kwargs)
    return json.dumps(redact_obj(value), **options)


_JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_JSON_DECODER = json.JSONDecoder()


def _json_document(text):
    """整段文本是可解析 JSON 文档（含顶层字符串）时返回解析结果，否则 None。"""
    stripped = text.strip()
    if stripped[:1] not in ("{", "[", '"'):
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return None


def _json_route(text, parsed):
    """紧凑布局走结构化整文档，其它布局就地按 token 脱敏。"""
    if json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) == text.strip():
        return dumps_redacted(parsed, separators=(",", ":"))
    return _redact_json_layout(text)


def _redact_json_layout(text):
    """已确认合法的 JSON：按字符串 token 就地脱敏，保留未改变部分的字节布局。"""
    pieces = []
    cursor = 0
    while True:
        matched = _JSON_STRING.search(text, cursor)
        if matched is None:
            pieces.append(text[cursor:])
            return "".join(pieces)
        pieces.append(text[cursor:matched.start()])
        token = matched.group(0)
        value = json.loads(token)
        end = matched.end()
        following = end
        while following < len(text) and text[following].isspace():
            following += 1
        if following < len(text) and text[following] == ":":
            pieces.append(token)
            if _is_sensitive_key(value):
                value_start = following + 1
                while text[value_start].isspace():
                    value_start += 1
                _, value_end = _JSON_DECODER.raw_decode(text, value_start)
                pieces.append(text[end:value_start])
                pieces.append(json.dumps(REDACTED))
                cursor = value_end
                continue
        else:
            clean = redact_boundary(value)
            pieces.append(token if clean == value else json.dumps(clean, ensure_ascii=False))
        cursor = end


def redact_boundary(text):
    """输出边界入口：合法 JSON 文档（含顶层字符串）结构化处理，其余走 `redact_text()`。"""
    text = str(text)
    parsed = _json_document(text)
    if parsed is not None:
        return _json_route(text, parsed)
    return redact_text(text)


def api_base_problem(base, label="SURGE_HTTP_API_BASE", allow_remote_env="SURGE_ALLOW_REMOTE"):
    """返回问题描述；通过返回 None。非本机主机须 `SURGE_ALLOW_REMOTE=1`。"""
    parsed = urlparse(str(base))
    if parsed.scheme not in ("http", "https"):
        return "%s must use http or https" % label
    if parsed.username is not None or parsed.password is not None:
        return "%s must not embed URL credentials; use SURGE_API_KEY" % label
    if parsed.hostname not in _LOOPBACK and os.getenv(allow_remote_env) != "1":
        return "Remote Surge API blocked; set SURGE_ALLOW_REMOTE=1 explicitly"
    return None

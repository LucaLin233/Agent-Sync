#!/usr/bin/env python3
"""body_contract.py —— 判等契约的唯一实现（P2a 规格 §二），字节级、fail-closed、确定性。

本模块是「正文提取 / 文本入口校验 / frontmatter 字段取值 / 块标量往返」的**单一真源**：
`tools/deploy_skill.py`（判等）与其保留的部署测试都从这里取规则，禁止各自复制一份宽容实现。

契约要点（现役契约＝本节以下逐条；历史规格原件 `P2a-SPEC.md` **未入库**，其内容以本模块
的 docstring 与实现为准，历史见 `git log --follow -- tools/body_contract.py`）：
  · §2.1 正文 = 去掉「起始 `---` 行 + frontmatter 块 + 结束行自身行终止符 + 紧随的一个行终止符」后的余下部分；
         不满足起止条件 → 正文 = 整个文件。
  · §2.2 起始分隔符：前 3 字节恰为 `---` **且**第 4 字节是行终止符起始（`\\n` 或 `\\r\\n`）；
         `---` 恰为 EOF、或第 4 字节非行终止符 → 无 frontmatter。
         结束分隔符：逐行扫描，行去掉自身行终止符后的内容恰为 `---`；**位于 EOF 且无行终止符的行不算结束行**。
         扫描到 EOF 无结束行 → 无 frontmatter。结束行行终止符允许 `\\n` 或 `\\r\\n`，不要求与起始行同族。
  · §2.3 原始字节读取；UTF-8 严格校验（范围含 frontmatter 在内的整个文件）；文本入口禁止 BOM；
         CRLF 按字节比较不归一；**不做任何尾换行规范化**。
  · §2.5 frontmatter 字段用 YAML 解析取值，重复键明确拒绝，区分 缺字段 / null / 空串。

实现说明（诚实披露）：本机 `python3 -c "import yaml"` 与 `import ruamel.yaml` 均不可用，
且任务禁止安装任何包，故 §2.5 的「YAML 解析」由本模块内的**受控最小 YAML 标量解析器**承担：
只支持 frontmatter 顶层 `key: 标量` 映射（裸标量 / 单引号 / 双引号 / 字面块 `|` 与折叠块 `>`，
含 chomping 指示符 `-`/`+`），遇到流式集合、锚点、标签、序列等超出范围的构造一律
抛 ContractError（fail-closed），不猜、不降级、不静默取默认值。
"""

BOM = b"\xef\xbb\xbf"
LF = b"\n"
CRLF = b"\r\n"

#: §2.5「区分 缺字段 / null / 空串」：缺字段用本哨兵，null → None，空串 → ""
MISSING = object()

#: 本模块定义的失败类别（fail-closed：全部为「明确失败」，不存在「放过」分支）
CODES = (
    "BOM_FORBIDDEN",       # 文本入口出现 BOM
    "INVALID_UTF8",        # 非法 UTF-8（校验范围含 frontmatter）
    "DUPLICATE_KEY",       # frontmatter 重复键
    "UNSUPPORTED_YAML",    # 超出受控解析器范围的 YAML 构造
    "BAD_BLOCK_SCALAR",    # 块标量结构不合法
)


class ContractError(Exception):
    """契约违反。`code` 取 CODES 之一；`detail` 为可读原因（不含秘密）。"""

    def __init__(self, code, detail=""):
        super().__init__("%s%s" % (code, ("：" + detail) if detail else ""))
        self.code = code
        self.detail = detail


# ── §2.3 文本入口校验 ────────────────────────────────────────────────────────

def check_text_bytes(raw):
    """文本入口：BOM 禁止 + UTF-8 严格校验（**范围含 frontmatter 在内的整个文件**）。

    §2.3 明确要求 BOM 检查**早于**「无 frontmatter → 返回整体」，故本函数在提取前无条件执行。
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise ContractError("UNSUPPORTED_YAML", "文本入口要求 bytes，收到 %s" % type(raw).__name__)
    raw = bytes(raw)
    if raw.startswith(BOM):
        raise ContractError("BOM_FORBIDDEN", "文本入口前 3 字节为 UTF-8 BOM")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("INVALID_UTF8", "非法 UTF-8（字节偏移 %d）" % exc.start)
    return raw


# ── §2.2 起止识别（逐字节） ──────────────────────────────────────────────────

def _line_at(raw, i):
    """返回 (内容结束位置, 行终止符长度)：`\\n` → 1，`\\r\\n` → 2，**无行终止符 → 0**。"""
    j = raw.find(LF, i)
    if j == -1:
        return len(raw), 0
    if j > i and raw[j - 1:j] == b"\r":
        return j - 1, 2
    return j, 1


def frontmatter_span(raw):
    """定位 frontmatter。命中 → (fm_end, body_start)；视为无 frontmatter → None。

    fm_end = 结束行行终止符之后（即 frontmatter 块末尾，含结束行的行终止符）；
    body_start = fm_end 之后再跳过一个行终止符（若存在）。
    """
    if not raw.startswith(b"---"):
        return None
    if len(raw) < 4:                      # 恰为 `---`（3 字节即 EOF）
        return None
    if raw[3:4] == LF:
        term = 1
    elif raw[3:5] == CRLF:
        term = 2
    else:                                 # 第 4 字节不是行终止符的起始
        return None
    i = 3 + term
    while i <= len(raw):
        ce, tl = _line_at(raw, i)
        if tl == 0:
            # 末行无行终止符 → 不算结束行；扫描到 EOF 无结束行 → 无 frontmatter
            return None
        if raw[i:ce] == b"---":
            fm_end = ce + tl
            body = fm_end
            if raw[body:body + 2] == CRLF:      # §2.2：再跳过紧随的一个行终止符（若存在）
                body += 2
            elif raw[body:body + 1] == LF:
                body += 1
            return fm_end, body
        i = ce + tl
    return None


def frontmatter_bytes(raw):
    """frontmatter 块字节（含起始行、结束行与其行终止符）；无 frontmatter → None。"""
    raw = check_text_bytes(raw)
    span = frontmatter_span(raw)
    return None if span is None else raw[0:span[0]]


def body_bytes(raw):
    """§2.1 正文（bytes）。无 frontmatter → 整个文件。**不做任何尾换行规范化。**"""
    raw = check_text_bytes(raw)
    span = frontmatter_span(raw)
    return raw if span is None else raw[span[1]:]


def body_text(raw):
    """正文（str，UTF-8 严格解码）。"""
    return body_bytes(raw).decode("utf-8")


# ── §2.5 受控最小 YAML 标量解析器 ────────────────────────────────────────────

_KEY_END = (":", " ")


def _strip_comment(s):
    """去掉裸标量后的注释（` #` 起始），引号内的 `#` 不在此处理。"""
    out, quote = [], None
    i = 0
    while i < len(s):
        ch = s[i]
        if quote:
            out.append(ch)
            if quote == "'" and ch == "'" and s[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            if quote == '"' and ch == "\\":
                out.append(s[i + 1:i + 2])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "#" and (not out or out[-1] in " \t"):
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _scalar(s):
    """裸标量 / 引号标量 → None | str。超出范围（流式集合、锚点、标签）→ ContractError。"""
    s = _strip_comment(s).strip()
    if s == "" or s in ("~", "null", "Null", "NULL"):
        return None
    if s[0] == "[" or s[0] == "{":
        raise ContractError("UNSUPPORTED_YAML", "流式集合不在受控解析器范围内")
    if s[0] in "&*!%@`":
        raise ContractError("UNSUPPORTED_YAML", "锚点/别名/标签/保留指示符不在受控范围内")
    if s[0] == "'":
        if len(s) < 2 or not s.endswith("'"):
            raise ContractError("UNSUPPORTED_YAML", "单引号标量未闭合")
        return s[1:-1].replace("''", "'")
    if s[0] == '"':
        if len(s) < 2 or not s.endswith('"'):
            raise ContractError("UNSUPPORTED_YAML", "双引号标量未闭合")
        body, i = [], 1
        esc = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", '"': '"', "\\": "\\", "/": "/",
               "b": "\b", "f": "\f", " ": " ", "'": "'", "e": "\x1b"}
        while i < len(s) - 1:
            ch = s[i]
            if ch != "\\":
                body.append(ch)
                i += 1
                continue
            nxt = s[i + 1:i + 2]
            if nxt in esc:
                body.append(esc[nxt])
                i += 2
            elif nxt in ("u", "U", "x"):
                width = {"x": 2, "u": 4, "U": 8}[nxt]
                hexs = s[i + 2:i + 2 + width]
                if len(hexs) != width or any(c not in "0123456789abcdefABCDEF" for c in hexs):
                    raise ContractError("UNSUPPORTED_YAML", "转义序列不合法")
                try:
                    body.append(chr(int(hexs, 16)))
                except ValueError:
                    raise ContractError("UNSUPPORTED_YAML", "码点超出范围")
                i += 2 + width
            else:
                raise ContractError("UNSUPPORTED_YAML", "不支持的双引号转义 \\%s" % nxt)
        return "".join(body)
    return s


def _block_scalar(lines, start, indicator, indent_of_key):
    """读块标量。lines[start:] 为块内容行；返回 (值, 下一行索引)。

    支持 `|` `|-` `|+` `>` `>-` `>+`（含显式缩进指示符数字）。受控范围外 → ContractError。
    """
    chomp = ""
    explicit = ""
    for c in indicator[1:]:
        if c in "-+":
            chomp = c
        elif c.isdigit():
            explicit = c
        else:
            raise ContractError("UNSUPPORTED_YAML", "块标量指示符不合法：%s" % indicator)
    keep = chomp == "+"
    strip = chomp == "-"
    raw_lines, i = [], start
    content_indent = None
    while i < len(lines):
        line = lines[i]
        if line.strip() == "":
            raw_lines.append("")
            i += 1
            continue
        ind = len(line) - len(line.lstrip(" "))
        if ind <= indent_of_key:
            break
        if content_indent is None:
            content_indent = ind if not explicit else indent_of_key + int(explicit)
        raw_lines.append(line[content_indent:] if len(line) >= content_indent else line.lstrip(" "))
        i += 1
    if content_indent is None:
        content_indent = indent_of_key + (int(explicit) if explicit else 1)
    # 去掉块末尾的纯空行（它们由 chomping 决定是否保留）
    tail_empty = 0
    while raw_lines and raw_lines[-1] == "":
        raw_lines.pop()
        tail_empty += 1
    if indicator[0] == "|":
        text = "".join(l + "\n" for l in raw_lines)
    else:  # 折叠 `>`
        folded = []
        for idx, l in enumerate(raw_lines):
            if l == "":
                folded.append("\n")
            else:
                folded.append(l + (" " if idx + 1 < len(raw_lines) and raw_lines[idx + 1] != "" else "\n"))
        text = "".join(folded)
    if keep:
        text += "\n" * tail_empty
    elif strip:
        text = text.rstrip("\n")
    return text, i


def _nested_mapping(lines, start, parent_indent):
    """读一层嵌套映射。返回 (dict, 下一行索引)。

    只支持**一层**：子键必须同缩进；子层内再出现嵌套、序列、块标量一律 fail-closed。
    （真实数据触发：`skills/luno-surge/SKILL.md` 的 `metadata:` 下有两个子键。）
    """
    data, i, child_indent = {}, start, None
    while i < len(lines):
        line = lines[i]
        if line.strip() == "":
            i += 1
            continue
        ind = len(line) - len(line.lstrip(" "))
        if ind <= parent_indent:
            break
        if child_indent is None:
            child_indent = ind
        elif ind != child_indent:
            raise ContractError("UNSUPPORTED_YAML", "超过一层的嵌套不在受控范围内")
        body = line.strip()
        if body.startswith("- "):
            raise ContractError("UNSUPPORTED_YAML", "序列不在受控范围内")
        key, sep, rest = body.partition(":")
        if not sep or not key or " " in key:
            raise ContractError("UNSUPPORTED_YAML", "无法识别的子行：%s" % body[:32])
        if key in data:
            raise ContractError("DUPLICATE_KEY", "嵌套重复键：%s" % key)
        if rest.lstrip()[:1] in ("|", ">"):
            raise ContractError("UNSUPPORTED_YAML", "嵌套层内块标量不在受控范围内")
        data[key] = _scalar(rest)
        i += 1
    return data, i


def parse_fm_mapping(raw):
    """解析 frontmatter（bytes，可含起止行）为 dict。

    重复键 → ContractError(DUPLICATE_KEY)。空值无内容 → None；`""` → 空串（两者可区分）。

    行终止符：§2.2 允许起始/结束行分别为 `\\n` 或 `\\r\\n`（不要求同族），故本函数按**行**解析，
    `\\r\\n` 视作行终止符（等价于 YAML 的换行语义）。只影响 frontmatter 的**结构解析与字段值**；
    §2.1／§2.3 的正文 `body_bytes` 仍按原始 bytes 返回、不归一（两处契约不互相改写）。
    """
    text = raw.decode("utf-8").replace(CRLF.decode("ascii"), "\n")
    lines = text.split("\n")
    if lines and lines[0] == "---":
        lines = lines[1:]
    while lines and lines[-1] in ("---", ""):
        lines.pop()
    data, seen, i = {}, set(), 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "" or line.lstrip().startswith("#"):
            i += 1
            continue
        if line[0] in " \t":
            raise ContractError("UNSUPPORTED_YAML", "顶层的续行/嵌套不在受控范围内")
        if line.lstrip().startswith("- "):
            raise ContractError("UNSUPPORTED_YAML", "序列不在受控范围内")
        key, sep, rest = line.partition(":")
        if not sep or (" " in key) or key == "":
            raise ContractError("UNSUPPORTED_YAML", "无法识别的行：%s" % line[:32])
        key = key.strip()
        if key in seen:
            raise ContractError("DUPLICATE_KEY", "frontmatter 重复键：%s" % key)
        seen.add(key)
        if rest.lstrip()[:1] in ("|", ">"):
            indent_of_key = len(line) - len(line.lstrip(" "))
            value, i = _block_scalar(lines, i + 1, rest.strip(), indent_of_key)
        elif rest.strip() == "" and i + 1 < len(lines) and lines[i + 1].strip() \
                and (len(lines[i + 1]) - len(lines[i + 1].lstrip(" "))) > (len(line) - len(line.lstrip(" "))):
            # 一层嵌套映射（真实数据：skills/luno-surge 的 `metadata:`）
            indent_of_key = len(line) - len(line.lstrip(" "))
            value, i = _nested_mapping(lines, i + 1, indent_of_key)
        else:
            value = _scalar(rest)
            i += 1
        data[key] = value
    return data


def fm_fields(raw):
    """frontmatter 字段表（原始文件 bytes → dict）。**校验范围含整个文件。**"""
    raw = check_text_bytes(raw)
    fm = frontmatter_bytes(raw)
    return {} if fm is None else parse_fm_mapping(fm)


def fm_get(raw, key):
    """取字段：缺字段 → MISSING；`key:` → None；`key: ""` → ""。"""
    return fm_fields(raw).get(key, MISSING)


# ── 块标量发射（导出器用；受控、确定性） ────────────────────────────────────

def block_indicator(text):
    """按尾部换行数确定 chomping 指示符，**不强行套 `|-`**（§4.2）。

    0 个 → `|-`（strip）；恰 1 个 → `|`（clip）；≥2 个 → `|+`（keep）。
    """
    n = len(text) - len(text.rstrip("\n"))
    if n == 0:
        return "|-"
    if n == 1:
        return "|"
    return "|+"


def emit_block(text, indent):
    """把文本发射为 YAML 字面块标量行列表（不含 `key:` 本身）。确定性：无时间戳、无排序随机。

    clip(`|`) 与 keep(`|+`) 时，`split("\\n")` 产生的**最后一个空元素只是"尾随换行"的产物**，
    不发射为独立行 —— 否则读回会多出一个换行，往返不恒等（本函数与 read_block 互为对偶）。
    strip(`|-`) 保留全部元素。
    """
    if not isinstance(text, str):
        raise ContractError("UNSUPPORTED_YAML", "块标量内容必须是 str")
    parts = text.split("\n")
    if block_indicator(text) != "|-" and parts and parts[-1] == "":
        parts = parts[:-1]
    ind = " " * indent
    return [ind + line for line in parts]


def read_block(lines, start, indicator, indent_of_key):
    """读回块标量（与 emit_block 对偶，用于生成后的自校验）。"""
    return _block_scalar(lines, start, indicator, indent_of_key)

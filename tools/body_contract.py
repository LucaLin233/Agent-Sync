#!/usr/bin/env python3
"""正文判等契约的唯一实现：字节级、fail-closed、确定性（部署工具与测试共用，禁止另抄宽容版本）。

  · 正文 = 去掉「起始 `---` 行 + frontmatter + 结束 `---` 行（含其行终止符）+ 紧随的至多一个行终止符」后的余下 bytes；
    不满足起止条件则整个文件都是正文。
  · 起始：前 3 字节为 `---` 且其后是 `\n` 或 `\r\n`。结束：内容恰为 `---` 且带行终止符的行（EOF 上无终止符的行不算）；
    找不到结束行即视为无 frontmatter。两处终止符可不同族。
  · 整个文件严格 UTF-8、禁止 BOM；CRLF 不归一、尾换行不规范化。
  · frontmatter 字段交给 PyYAML 的 `yaml.safe_load` 取值（折叠、缩进、引号、嵌套、流式集合与锚点均按 YAML 语义）；
    同一层级重复键拒绝；区分缺字段（MISSING）/null（None）/空串。解析失败或根不是映射按 UNSUPPORTED_YAML 拒绝。

依赖 PyYAML（系统包 py3-yaml，与 skills/luno-core/scripts/quick_validate.py 相同）：缺失或损坏即报错退出，
不静默回退到自制解析器；正文提取只做字节切片，不走 YAML。
"""
try:
    import yaml
except ImportError:                                   # 缺依赖抛 ImportError，由各 CLI 转成自己的执行错误码
    raise ImportError("body_contract：缺少 PyYAML（系统包 py3-yaml），缺依赖即停，不静默回退") from None


BOM = b"\xef\xbb\xbf"
LF = b"\n"
CRLF = b"\r\n"

MISSING = object()   # 缺字段哨兵


class ContractError(Exception):
    """`code`：BOM_FORBIDDEN／INVALID_UTF8／DUPLICATE_KEY／UNSUPPORTED_YAML。"""

    def __init__(self, code, detail=""):
        super().__init__("%s%s" % (code, ("：" + detail) if detail else ""))
        self.code = code
        self.detail = detail


def check_text_bytes(raw):
    """BOM 禁止＋整文件严格 UTF-8；在识别 frontmatter 之前无条件执行。"""
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
            if raw[body:body + 2] == CRLF:      # 再跳过紧随的一个行终止符（若存在）
                body += 2
            elif raw[body:body + 1] == LF:
                body += 1
            return fm_end, body
        i = ce + tl
    return None


def body_bytes(raw):
    """正文 bytes；无 frontmatter → 整个文件；不做任何尾换行规范化。"""
    raw = check_text_bytes(raw)
    span = frontmatter_span(raw)
    return raw if span is None else raw[span[1]:]


_MERGE_TAG = "tag:yaml.org,2002:merge"


class _UniqueKeyLoader(yaml.SafeLoader):
    """与 safe_load 相同，但同一映射内的重复键按 DUPLICATE_KEY 拒绝（不取后值）。"""

    def construct_mapping(self, node, deep=False):
        self._reject_duplicates(node)
        return super().construct_mapping(node, deep=deep)

    @staticmethod
    def _reject_duplicates(node):
        """只用原始 key 节点判重：先于 merge(`<<`)/value 标签展开与键的哈希化。

        `<<` 是 SafeLoader 的特殊键（可多次出现，由 flatten_mapping 处理），不参与判重；
        其余键按 (tag, value) 比较，非标量键无法判重且 SafeLoader 会因不可哈希报错，这里直接归入
        UNSUPPORTED_YAML。merge 源映射本身也是映射节点，构造时同样经过本检查。
        """
        seen = set()
        for key_node, _value_node in node.value:
            if getattr(key_node, "tag", None) == _MERGE_TAG:
                continue
            if not isinstance(key_node, yaml.ScalarNode):
                raise ContractError("UNSUPPORTED_YAML", "frontmatter 键不是标量，无法判定重复")
            key = (key_node.tag, key_node.value)
            if key in seen:
                raise ContractError("DUPLICATE_KEY", "frontmatter 重复键：%s" % key_node.value)
            seen.add(key)


def _fm_inner(raw):
    """frontmatter 内层 bytes（不含起止行）；与 frontmatter_span 同口径，找不到结束行返回 None。"""
    start = 3 + (2 if raw[3:5] == CRLF else 1)
    i = start
    while i <= len(raw):
        ce, tl = _line_at(raw, i)
        if tl == 0:
            return None
        if raw[i:ce] == b"---":
            return raw[start:i]
        i = ce + tl
    return None


def _load(text):
    """safe_load 的唯一入口：解析错误与非映射根都归入 UNSUPPORTED_YAML。"""
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except ContractError:
        raise
    except yaml.YAMLError as exc:
        detail = " ".join(str(exc).split())[:120]
        raise ContractError("UNSUPPORTED_YAML", "frontmatter 不是可解析的 YAML：%s" % detail)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ContractError("UNSUPPORTED_YAML", "frontmatter 根不是映射")
    return data


def parse_fm_mapping(raw):
    """解析 frontmatter（bytes，可含起止行）为 dict；`\r\n` 只在此处视作换行，正文 bytes 不归一。"""
    raw = check_text_bytes(raw)
    if not raw.startswith(b"---") or len(raw) < 4 or raw[3:4] not in (LF, b"\r"):
        raise ContractError("UNSUPPORTED_YAML", "输入不是 frontmatter 块")
    inner = _fm_inner(raw)
    if inner is None:
        raise ContractError("UNSUPPORTED_YAML", "frontmatter 缺结束行")
    text = inner.decode("utf-8").replace(CRLF.decode("ascii"), "\n")
    return _load(text)


def fm_fields(raw):
    """frontmatter 字段表（原始文件 bytes → dict）；校验范围含整个文件。"""
    raw = check_text_bytes(raw)
    span = frontmatter_span(raw)
    return {} if span is None else parse_fm_mapping(raw[:span[0]])


def fm_get(raw, key):
    """取字段：缺字段 → MISSING；`key:` → None；`key: ""` → ""。"""
    return fm_fields(raw).get(key, MISSING)

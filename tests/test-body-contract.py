#!/usr/bin/env python3
"""body_contract 回归：正文/字段字节仍是跨端生效契约，故整套进 full。

本文件含既有回归与新增定向判据（PyYAML 取值语义、merge 重复键、不可哈希键），新增判据在用例名与
注释中逐条标明；正文提取仍只做字节切片，不 strip、不归一换行。
"""
import importlib.util
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("body_contract_for_tests",ROOT/"tools/body_contract.py")
BC=importlib.util.module_from_spec(spec)
spec.loader.exec_module(BC)

class BodyContract(unittest.TestCase):
    def code(self, func, raw):
        with self.assertRaises(BC.ContractError) as ctx:
            func(raw)
        return ctx.exception.code

    def test_body_bytes_are_exact(self):
        self.assertEqual(BC.body_bytes(b"---\nname: a\n---\n\nbody\n\n"), b"body\n\n")
        self.assertEqual(BC.body_bytes(b"---\r\nname: a\r\n---\r\n\r\nx\r\n"), b"x\r\n")
        self.assertEqual(BC.body_bytes(b"---\nname: a\r\n---\nx"), b"x", "终止符可不同族")
        self.assertEqual(BC.body_bytes(b"---\nname: a\n---"), b"---\nname: a\n---", "EOF 结束行不算")
        self.assertEqual(BC.body_bytes(b"--- x\n"), b"--- x\n")
        self.assertEqual(BC.body_bytes(b"---\nname: a\n"), b"---\nname: a\n", "无结束行即整体为正文")

    def test_field_values(self):
        raw = (b'---\r\nname: "a\\tb\\u00e9"\r\nq: \'it\'\'s\'\r\nn:\r\ne: ""\r\n'
               b'd: |\r\n  l1\r\n  l2\r\nf: >-\r\n  x\r\n  y\r\nm:\r\n  k: v\r\n---\r\nbody')
        f = BC.fm_fields(raw)
        self.assertEqual((f["name"], f["q"], f["n"], f["e"]), ("a\tb\u00e9", "it's", None, ""))
        self.assertEqual((f["d"], f["f"], f["m"]), ("l1\nl2\n", "x y", {"k": "v"}))
        self.assertIs(BC.fm_get(raw, "absent"), BC.MISSING)

    def test_fail_closed(self):
        self.assertEqual(self.code(BC.fm_fields, b"---\nname: a\r\nname: b\r\n---\nx"), "DUPLICATE_KEY")
        self.assertEqual(self.code(BC.body_bytes, b"x\xff"), "INVALID_UTF8")
        self.assertEqual(self.code(BC.fm_fields, b"---\nname: \xff\n---\n"), "INVALID_UTF8")
        self.assertEqual(self.code(BC.body_bytes, b"\xef\xbb\xbfno frontmatter"), "BOM_FORBIDDEN")
        # PyYAML 语义下真正非法的 frontmatter：根不是映射、流式/引号未闭合、未知标签都 fail-closed。
        for raw in (b"---\n- a\n---\n", b"---\nt: [a\n---\n", b'---\nt: "a\n---\n',
                    b"---\nt: !tag x\n---\n", b"---\nt: |2x\n  a\n---\n"):
            self.assertEqual(self.code(BC.fm_fields, raw), "UNSUPPORTED_YAML", raw)

    def test_folded_and_deep_indentation_follow_pyyaml(self):
        """折叠标量含空行、缩进超过一层的前置字段，取值按 YAML 语义（期望值是 yaml.safe_load 的结果）。"""
        raw = (b"---\nfolded: >\n  line one\n\n  line two\n"
               b"nested:\n  meta:\n    deeper: value\n---\nbody")
        f = BC.fm_fields(raw)
        self.assertEqual(f["folded"], "line one\nline two\n")
        self.assertEqual(f["nested"], {"meta": {"deeper": "value"}})
        self.assertEqual(BC.body_bytes(raw), b"body")

    def test_merge_keys_follow_safeloader_semantics(self):
        """`<<` 按 SafeLoader 处理：合法 merge 不误判，显式 override 合法，merge 源内重复键仍拒绝。"""
        raw = (b"---\nbase: &b\n  a: 1\n  b: two\n"
               b"skill:\n  <<: *b\n  a: 2\n---\nbody")
        f = BC.fm_fields(raw)
        self.assertEqual(f["skill"], {"a": 2, "b": "two"}, "显式键覆盖 merge 源")
        self.assertEqual(f["base"], {"a": 1, "b": "two"})
        multi = b"---\nx: &a\n  p: 1\ny: &c\n  q: 2\nm:\n  <<: [*a, *c]\n---\n"
        self.assertEqual(BC.fm_fields(multi)["m"], {"p": 1, "q": 2})
        # merge 源映射内部重复键：构造该映射时同样判重
        self.assertEqual(self.code(BC.fm_fields, b"---\nx: &b\n  a: 1\n  a: 2\n---\n"),
                         "DUPLICATE_KEY")

    def test_unhashable_key_is_a_contract_error(self):
        """不可哈希键（序列/映射键）归 UNSUPPORTED_YAML，不逸出未捕获的 TypeError。"""
        self.assertEqual(self.code(BC.fm_fields, b"---\n? [a]\n: b\n---\n"), "UNSUPPORTED_YAML")
        self.assertEqual(self.code(BC.fm_fields, b"---\n? {a: b}\n: c\n---\n"), "UNSUPPORTED_YAML")

    def test_block_scalar_chomping_follows_pyyaml(self):
        """`|`/`|+`/`|-` 的 chomping 与折叠空行都交给 PyYAML，不自制拼装。"""
        raw = b"---\na: |\n  x\n\n  y\nkeep: |+\n  k\n\nstrip: |-\n  s\n---\n"
        f = BC.fm_fields(raw)
        self.assertEqual((f["a"], f["keep"], f["strip"]), ("x\n\ny\n", "k\n\n", "s"))


if __name__ == "__main__":
    unittest.main()

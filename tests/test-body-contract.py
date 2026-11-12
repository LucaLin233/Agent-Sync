#!/usr/bin/env python3
"""Existing body_contract regressions moved intact from the retired deployment suite.
Kept in full because exact body/field bytes remain the live cross-end contract.
No new test assertions are introduced.
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
        for raw in (b"---\nt: [a]\n---\n", b"---\nt: &a x\n---\n", b"---\n- a\n---\n",
                    b"---\nm:\n  a:\n    b: c\n---\n"):
            self.assertEqual(self.code(BC.fm_fields, raw), "UNSUPPORTED_YAML", raw)


if __name__ == "__main__":
    unittest.main()

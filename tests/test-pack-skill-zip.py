#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/pack-skill-zip.py（通用打包库）的离线回归：确定性布局与源条目拒绝。

期望 ZIP 由本文件按同一布局规格独立算出，不硬编码哈希。全部在临时目录内完成。
"""
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pack-skill-zip.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("pack_skill_zip_under_test", str(TOOL))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def walk_order(root):
    return [os.path.relpath(os.path.join(cur, name), root).replace(os.sep, "/")
            for cur, _dirs, files in os.walk(root) for name in files]


def expected_pack(root):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel in sorted(walk_order(root)):
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (Path(root) / rel).read_bytes())
    return buf.getvalue()


class PackSkillZip(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="test-pack-skill-zip-")
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.pack = load_tool()
        self.root = self.work / "skill"
        for rel, data in (("SKILL.md", "---\nname: fixture\n---\n正文\n".encode("utf-8")),
                          ("zzz-top.md", b"top\n"), ("aaa/nested.md", b"nested\n"),
                          ("references/bin.dat", b"\x00\x01binary\xff"),
                          ("scripts/run.py", b"#!/usr/bin/env python3\n")):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        os.chmod(str(self.root / "scripts/run.py"), 0o755)

    def test_layout_is_deterministic_sorted_and_uniform_0644(self):
        self.assertNotEqual(walk_order(self.root), sorted(walk_order(self.root)),
                            "夹具须令遍历顺序≠排序顺序，否则排序断言空转")
        blob = self.pack.build(self.pack.collect(str(self.root)))
        self.assertEqual(blob, self.pack.build(self.pack.collect(str(self.root))), "两次构包须逐字节相同")
        self.assertEqual(blob, expected_pack(self.root), "须等于独立算出的统一 0644 布局")
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos = archive.infolist()
        self.assertEqual([i.filename for i in infos], sorted(walk_order(self.root)))
        self.assertFalse(any(i.is_dir() for i in infos))
        self.assertEqual({(i.date_time, i.compress_type, i.external_attr >> 16) for i in infos},
                         {((1980, 1, 1, 0, 0, 0), zipfile.ZIP_DEFLATED, 0o644)},
                         "0755 源文件也打成 0644")

    def test_collect_rejects_links_and_special_entries(self):
        outside = self.work / "outside"
        (outside / "dir").mkdir(parents=True)
        (outside / "file.md").write_bytes(b"x\n")
        cases = (("file link", lambda p: os.symlink(str(outside / "file.md"), str(p)), "符号链接"),
                 ("dir link", lambda p: os.symlink(str(outside / "dir"), str(p)), "符号链接"),
                 ("fifo", lambda p: os.mkfifo(str(p)), "非普通文件"))
        for label, make, needle in cases:
            with self.subTest(label):
                entry = self.root / "references" / label.replace(" ", "-")
                try:
                    make(entry)
                except (AttributeError, OSError) as exc:     # 平台不支持（如无 mkfifo）即明确跳过
                    self.skipTest("%s 不可构造：%s" % (label, exc))
                with self.assertRaises(OSError) as ctx:
                    self.pack.collect(str(self.root))
                self.assertIn(needle, str(ctx.exception))
                os.unlink(str(entry))

    def test_walk_error_propagates(self):
        def failing_walk(top, onerror=None, **kwargs):
            onerror(OSError("simulated walk failure"))
            return iter(())

        with mock.patch.object(self.pack.os, "walk", failing_walk), \
                self.assertRaises(OSError) as ctx:
            self.pack.collect(str(self.root))
        self.assertIn("遍历错误：simulated walk failure", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test-pack-skill-zip.py —— tools/pack-skill-zip.py 的离线回归。

判据（每项都断言**可复核的字节/退出码事实**）：
  1 确定性：同一输入打包两次，sha256 与 zip 字节完全相同；
  2 布局稳定性：用临时目录造 3 个文件的夹具，产物字节 == 本用例按**同一确定性布局**
    独立算出的期望值（期望值当场算出，不硬编码任何来路不明的常量）；并逐项核对 zip
    entry 名与顺序、日期、压缩方式、权限位与「无目录条目」；
  3 --expect：8 位前缀命中与 64 位全哈希命中均 rc=0；不符 rc=1 且 stderr 为固定一行差异说明；
  4 --src 缺失／不是目录／目录下无文件：rc=2、stderr 固定说明、**不产生 zip**；
  5 stdout 单行格式：files=<n> bytes=<n> sha256=<64hex>，且除 --out 外不落其他文件；
  6 源链接与非常规文件拒绝（--src 自身／其下子目录或文件是符号链接、条目非普通文件）：
    rc=2、stderr 固定说明、**不产生 zip**；
  7 遍历错误传播：进程内把 os.walk 换成抛 OSError 的实现，collect() 必须抛出、main() 返回 2
    且**未创建 zip**（不得误产出部分包）；
  8 失败不留残包：进程内把 build() 换成抛 OSError 的实现，main() 返回 2、--out 不存在，
    且 --out 所在目录**无任何残留**（含 .pack- 临时文件）；
  9 --out 位于 --src 之内（含同一路径）：rc=2、不产出；
  10 权限位统一 0644：源含 755 文件时，产物仍逐字节等于统一 0644 布局（对「继承源模式」的实现
    有区分力）。

全部离线、只在本用例的临时目录内、不联网、不调 lh／minis-config、不写仓库内文件。
"""
import ast
import contextlib
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pack-skill-zip.py"

STDOUT_RE = re.compile(r"\Afiles=(\d+) bytes=(\d+) sha256=([0-9a-f]{64})\n\Z")
MISMATCH_RE = re.compile(r"\A\[pack\] sha256 不符：expect=([0-9a-f]+) actual=([0-9a-f]{64})\n\Z")
SRC_UNAVAILABLE = "[pack] --src 不可用（不存在、不是目录或目录下无文件）：%s；不创建 zip\n"
SRC_IS_SYMLINK = "[pack] --src 自身是符号链接：%s；不创建 zip\n"
COLLECT_FAILED = "[pack] 收集 --src 失败（遍历错误／符号链接／非常规条目）：%s；不创建 zip\n"
OUT_IN_SRC = "[pack] --out 位于 --src 之内（其自身产物会被下次打包吸入）：%s；不创建 zip\n"


def symlink_entry_msg(path):
    """collect 拒绝符号链接时的固定说明（与工具同规格，但由本用例自带期望值）。"""
    return COLLECT_FAILED % ("符号链接（目录或文件）：%s" % path)


def nonregular_entry_msg(path):
    """collect 拒绝非常规条目时的固定说明。"""
    return COLLECT_FAILED % ("非普通文件（非常规条目）：%s" % path)


PACK_PREFIX = ".pack-"


def load_tool_namespace():
    """把被测工具源码**读成文本**后 ast.parse → compile → exec 到独立命名空间。

    不用 importlib／SourceFileLoader：那会走 import 机械（模块名含连字符本也不可直接 import）
    并可能读入**陈旧 .pyc**；本用例要的是一份与仓库源码逐字一致的、可安全打桩的命名空间。
    每次调用返回全新命名空间，互不串味（t8 里另作断言）。
    """
    source = TOOL.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(TOOL))
    code = compile(tree, str(TOOL), "exec")
    ns = {"__name__": "pack_skill_zip_under_test", "__file__": str(TOOL)}
    exec(code, ns)                       # noqa: S102 —— 受控加载，非不可信输入
    return ns


class OsShim:
    """把被测命名空间里的 os 换成受控代理：只替换 walk／unlink／replace，其余属性转真实 os。"""

    def __init__(self, real, walk=None, unlink=None, replace=None):
        self._real = real
        self._walk = walk
        self._unlink = unlink
        self._replace = replace

    def __getattr__(self, name):
        if name == "walk" and self._walk is not None:
            return self._walk
        if name == "unlink" and self._unlink is not None:
            return self._unlink
        if name == "replace" and self._replace is not None:
            return self._replace
        return getattr(self._real, name)


def expected_pack(root):
    """按确定性布局（relpath 用 /、排序、固定 date_time／权限位、ZIP_DEFLATED）
    独立算出期望 zip 字节。与 tools/pack-skill-zip.py 同一布局规格，但由本用例自带实现，
    期望值当场计算，不做任何硬编码。"""
    entries = []
    for cur, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(cur, name)
            entries.append((os.path.relpath(path, root).replace(os.sep, "/"), path))
    entries.sort()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel, path in entries:
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as fh:
                archive.writestr(info, fh.read())
    return buf.getvalue()


def sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


class PackSkillZip(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="test-pack-skill-zip-")
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.out_dir = self.work / "out"
        self.out_dir.mkdir()

    # ── 夹具 ──────────────────────────────────────────────────────────────
    def make_fixture(self, name="skill"):
        """3 个文件、含一层子目录与二进制字节的夹具。"""
        root = self.work / name
        (root / "references").mkdir(parents=True)
        (root / "SKILL.md").write_bytes("---\nname: fixture\n---\n正文\n".encode("utf-8"))
        (root / "references" / "notes.md").write_bytes("参考正文\n".encode("utf-8"))
        (root / "references" / "z-last.txt").write_bytes(b"\x00\x01binary\xff")
        return root

    def run_tool(self, *args):
        """最小环境（只给 PATH）运行被测工具：证明它不依赖环境变量即可工作。"""
        return subprocess.run([sys.executable, str(TOOL)] + [str(a) for a in args],
                              cwd=str(ROOT), env={"PATH": "/usr/bin:/bin"},
                              capture_output=True, text=True, timeout=60)

    def parse_stdout(self, stdout):
        m = STDOUT_RE.match(stdout)
        self.assertIsNotNone(m, "stdout 必须是唯一的固定格式行，实得：%r" % stdout)
        return int(m.group(1)), int(m.group(2)), m.group(3)

    # ── 1 确定性 ──────────────────────────────────────────────────────────
    def test_two_packs_same_bytes_and_same_sha(self):
        root = self.make_fixture()
        first = self.out_dir / "a.zip"
        second = self.out_dir / "b.zip"
        r1 = self.run_tool("--src", root, "--out", first)
        r2 = self.run_tool("--src", root, "--out", second)
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        _, _, sha1 = self.parse_stdout(r1.stdout)
        _, _, sha2 = self.parse_stdout(r2.stdout)
        self.assertEqual(sha1, sha2, "两次打包 sha256 必须相同")
        self.assertEqual(first.read_bytes(), second.read_bytes(), "两次打包字节必须相同")
        self.assertEqual(sha1, sha256_bytes(first.read_bytes()), "行内 sha256 必须等于产物 sha256")

    # ── 2 布局稳定性（对照同一实现独立算出的期望值）────────────────────────
    def test_layout_matches_independently_computed_expectation(self):
        root = self.make_fixture()
        out = self.out_dir / "fixture.zip"
        r = self.run_tool("--src", root, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        files, nbytes, sha = self.parse_stdout(r.stdout)

        blob = expected_pack(root)
        self.assertEqual(out.read_bytes(), blob, "产物字节必须等于按同一布局独立算出的期望值")
        self.assertEqual(sha, sha256_bytes(blob))
        self.assertEqual(nbytes, len(blob))
        self.assertEqual(files, 3)
        self.assertEqual(files, len(expected_zip_names(root)), "文件计数＝夹具文件数")

        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos = archive.infolist()
            self.assertEqual([i.filename for i in infos], sorted(expected_zip_names(root)))
            self.assertFalse(any(i.is_dir() for i in infos), "不得写入目录条目")
            for info in infos:
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
                self.assertEqual(info.external_attr, 0o644 << 16)
            self.assertEqual(archive.read("references/z-last.txt"), b"\x00\x01binary\xff")

    def test_order_assertion_has_discrimination_control(self):
        """负控：同一夹具若**不排序**、按 os.walk 顺序打包，字节必与产物不同——证明「排序」
        这一布局断言有区分力（os.walk 先出顶层文件、后进子目录，故 walk 顺序≠排序顺序）。"""
        root = self.make_fixture()
        (root / "zzz-top.md").write_bytes(b"top\n")
        (root / "aaa").mkdir()
        (root / "aaa" / "file.md").write_bytes(b"nested\n")
        out = self.out_dir / "ctl.zip"
        r = self.run_tool("--src", root, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        _, _, sha = self.parse_stdout(r.stdout)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            for cur, _dirs, files in os.walk(root):
                for name in files:
                    path = os.path.join(cur, name)
                    rel = os.path.relpath(path, root).replace(os.sep, "/")
                    info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    with open(path, "rb") as fh:
                        archive.writestr(info, fh.read())
        unsorted_blob = buf.getvalue()
        with zipfile.ZipFile(io.BytesIO(unsorted_blob)) as archive:
            self.assertNotEqual([i.filename for i in archive.infolist()],
                                sorted(expected_zip_names(root)),
                                "夹具必须令 walk 顺序≠排序顺序，否则本负控空转")
        self.assertNotEqual(sha256_bytes(unsorted_blob), sha, "排序断言必须能区分未排序产物")
        self.assertEqual(sha, sha256_bytes(expected_pack(root)))

    # ── 2b 权限位统一 0644（源为 755 时仍不打成 755）────────────────────────
    def test_source_mode_755_still_packs_uniform_0644(self):
        """包内权限位统一 0644、**不继承源文件模式**。

        历史例（2026-10-07 平台侧 `skill-authoring` 包；该包 2026-10-11 已退役并精选吸收进
        `luno-sync`）：当时该包 `skills/upstream/skill-authoring/scripts/` 有 2 个 755 脚本，而平台侧
        既有包的布局就是统一 0644：实测其 `zipFileHash` 只在 0644 布局下逐位相符。本用例对「改成
        继承源模式」的实现有区分力——继承后字节对照与权限位断言都会变红。
        """
        root = self.make_fixture()
        scripts = root / "scripts"
        scripts.mkdir()
        (scripts / "run.py").write_bytes(b"#!/usr/bin/env python3\n")
        os.chmod(scripts / "run.py", 0o755)
        self.assertEqual(os.stat(scripts / "run.py").st_mode & 0o777, 0o755,
                         "夹具前置：源文件必须真的是 755，否则本用例空转")
        out = self.out_dir / "mode.zip"
        r = self.run_tool("--src", root, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        blob = out.read_bytes()
        self.assertEqual(blob, expected_pack(root),
                         "含 755 源文件时产物仍须逐字节等于统一 0644 布局")
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            modes = {i.filename: i.external_attr >> 16 for i in archive.infolist()}
        self.assertEqual(set(modes.values()), {0o644},
                         "包内权限位必须统一 0644、不得继承源模式：%r" % modes)

    # ── 3 --expect 命中／不符 ─────────────────────────────────────────────
    def test_expect_prefix_and_full_hash_hit_rc0(self):
        root = self.make_fixture()
        out = self.out_dir / "c.zip"
        base = self.run_tool("--src", root, "--out", out)
        _, _, sha = self.parse_stdout(base.stdout)

        pref = self.run_tool("--src", root, "--out", self.out_dir / "d.zip", "--expect", sha[:8])
        self.assertEqual(pref.returncode, 0, pref.stderr)
        self.assertEqual(self.parse_stdout(pref.stdout)[2], sha)

        full = self.run_tool("--src", root, "--out", self.out_dir / "e.zip", "--expect", sha)
        self.assertEqual(full.returncode, 0, full.stderr)

    def test_expect_mismatch_rc1_fixed_message(self):
        root = self.make_fixture()
        out = self.out_dir / "f.zip"
        base = self.run_tool("--src", root, "--out", out)
        _, _, sha = self.parse_stdout(base.stdout)
        wrong = "0123456789abcdef"
        self.assertNotEqual(sha[:len(wrong)], wrong)
        r = self.run_tool("--src", root, "--out", self.out_dir / "g.zip", "--expect", wrong)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        m = MISMATCH_RE.match(r.stderr)
        self.assertIsNotNone(m, "stderr 必须是固定一行差异说明，实得：%r" % r.stderr)
        self.assertEqual(m.group(1), wrong)
        self.assertEqual(m.group(2), sha)
        # 不符时仍打印 stdout 指纹行（zip 已写出，可人工比对）
        self.assertEqual(self.parse_stdout(r.stdout)[2], sha)

    # ── 4 --src 不可用：rc=2 且不产生 zip ─────────────────────────────────
    def test_src_missing_rc2_and_no_zip(self):
        out = self.out_dir / "missing.zip"
        r = self.run_tool("--src", self.work / "no-such-dir", "--out", out)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr, SRC_UNAVAILABLE % (self.work / "no-such-dir"))
        self.assertFalse(out.exists(), "不得创建 zip")

    def test_src_not_a_directory_rc2_and_no_zip(self):
        plain = self.work / "plain.txt"
        plain.write_bytes(b"not a dir\n")
        out = self.out_dir / "notdir.zip"
        r = self.run_tool("--src", plain, "--out", out)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stderr, SRC_UNAVAILABLE % plain)
        self.assertFalse(out.exists())

    def test_src_without_files_rc2_and_no_zip(self):
        empty = self.work / "empty"
        (empty / "sub").mkdir(parents=True)
        out = self.out_dir / "empty.zip"
        r = self.run_tool("--src", empty, "--out", out)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stderr, SRC_UNAVAILABLE % empty)
        self.assertFalse(out.exists(), "空输入不得留下空 zip")

    # ── 5 stdout 单行格式与落盘范围 ───────────────────────────────────────
    def test_stdout_single_line_format_and_only_out_is_written(self):
        root = self.make_fixture()
        out = self.out_dir / "only.zip"
        r = self.run_tool("--src", root, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        self.assertEqual(len(r.stdout.splitlines()), 1, "stdout 必须恰好一行")
        files, nbytes, sha = self.parse_stdout(r.stdout)
        blob = out.read_bytes()
        self.assertEqual((files, nbytes, sha), (3, len(blob), sha256_bytes(blob)))
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()), ["only.zip"],
                         "除 --out 外不得在本目录落其他文件")

    def test_invalid_expect_length_rc2(self):
        root = self.make_fixture()
        out = self.out_dir / "short.zip"
        r = self.run_tool("--src", root, "--out", out, "--expect", "0123456")   # 7 位：低于下限
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(out.exists())


    # ── 6 源链接与非常规文件拒绝（固定说明、rc=2、不产出）──────────────────
    def out_dir_names(self):
        return sorted(p.name for p in self.out_dir.iterdir())

    def test_src_itself_symlink_rc2_and_no_zip(self):
        root = self.make_fixture()
        link = self.work / "src-link"
        os.symlink(str(root), str(link))
        out = self.out_dir / "selflink.zip"
        r = self.run_tool("--src", link, "--out", out)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr, SRC_IS_SYMLINK % link, "stderr 须是固定说明")
        self.assertFalse(out.exists(), "不得创建 zip")
        self.assertEqual(self.out_dir_names(), [], "除 --out 外不得落任何文件")

    def test_file_symlink_inside_src_rc2_and_no_zip(self):
        root = self.make_fixture()
        target = self.work / "outside-target.md"
        target.write_bytes(b"outside\n")
        link = root / "linked.md"
        os.symlink(str(target), str(link))
        out = self.out_dir / "filelink.zip"
        r = self.run_tool("--src", root, "--out", out)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stderr, symlink_entry_msg(link), "stderr 须是固定说明")
        self.assertFalse(out.exists())
        self.assertEqual(self.out_dir_names(), [])

    def test_dir_symlink_inside_src_rc2_and_no_zip(self):
        root = self.make_fixture()
        outsider = self.work / "outside-dir"
        outsider.mkdir()
        (outsider / "sneaky.md").write_bytes(b"sneaky\n")
        link = root / "subdir-link"
        os.symlink(str(outsider), str(link))
        out = self.out_dir / "dirlink.zip"
        r = self.run_tool("--src", root, "--out", out)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stderr, symlink_entry_msg(link), "stderr 须是固定说明")
        self.assertFalse(out.exists())
        self.assertEqual(self.out_dir_names(), [])

    def test_non_regular_entry_rc2_and_no_zip(self):
        root = self.make_fixture()
        fifo = root / "fifo-entry"
        try:
            os.mkfifo(str(fifo))
        except (AttributeError, OSError) as exc:      # 不支持的平台明确跳过，不静默通过
            self.skipTest("本平台不支持 os.mkfifo：%s" % exc)
        out = self.out_dir / "fifo.zip"
        r = self.run_tool("--src", root, "--out", out)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stderr, nonregular_entry_msg(fifo), "stderr 须是固定说明")
        self.assertFalse(out.exists())
        self.assertEqual(self.out_dir_names(), [])

    # ── 7 遍历错误传播（进程内打桩；不用权限位：本机以 root 运行 chmod 000 不生效）
    def test_walk_error_propagates_and_main_rc2_no_zip(self):
        root = self.make_fixture()
        out = self.out_dir / "walkerr.zip"
        ns = load_tool_namespace()
        calls = []

        def boom(top, topdown=True, onerror=None, followlinks=False):
            calls.append({"onerror": onerror})
            # 照 os.walk 的同一契约：把遍历错误交给 onerror，而不是自行吞掉。
            onerror(OSError("simulated walk failure"))
            return iter(())

        ns["os"] = OsShim(ns["os"], boom)
        with self.assertRaises(OSError) as raised:
            ns["collect"](str(root))
        self.assertIn("simulated walk failure", str(raised.exception), "collect 必须让遍历错误外传")
        self.assertEqual(len(calls), 1, "collect 必须走被替换的 os.walk（否则本用例空转）")
        self.assertIsNotNone(calls[0]["onerror"], "os.walk 必须传 onerror=（错误不得被静默忽略）")

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = ns["main"](["--src", str(root), "--out", str(out)])
        self.assertEqual(rc, 2, "有读取错误时 main 必须 rc=2，实得 %d：%s" % (rc, err.getvalue()))
        self.assertIn("收集 --src 失败", err.getvalue(), "stderr 须给出固定说明")
        self.assertIn("遍历错误：simulated walk failure", err.getvalue(), "须带上遍历错误详情")
        self.assertFalse(out.exists(), "有读取错误时不得产出 zip")
        self.assertEqual(self.out_dir_names(), [], "失败路径不得留下任何临时产物")

        # 负控：即便遍历实现直接抛 OSError（不走 onerror），也必须 rc=2、不产出。
        def raising(top, topdown=True, onerror=None, followlinks=False):
            raise OSError("direct walk failure")

        ns2 = load_tool_namespace()
        ns2["os"] = OsShim(ns2["os"], raising)
        out2 = self.out_dir / "walkerr2.zip"
        err2 = io.StringIO()
        with contextlib.redirect_stderr(err2):
            rc2 = ns2["main"](["--src", str(root), "--out", str(out2)])
        self.assertEqual(rc2, 2, "直接抛出的遍历错误也必须 rc=2，实得 %d：%s" % (rc2, err2.getvalue()))
        self.assertIn("收集 --src 失败", err2.getvalue())
        self.assertIn("direct walk failure", err2.getvalue())
        self.assertFalse(out2.exists())
        self.assertEqual(self.out_dir_names(), [])

    # ── 8 失败不留残包（build 抛错：临时文件必须已建且被清掉）───────────────
    def test_build_failure_rc2_and_no_residue(self):
        root = self.make_fixture()
        out = self.out_dir / "builderr.zip"
        ns = load_tool_namespace()
        seen = []

        def boom(entries):
            # 记录失败时刻 --out 所在目录的内容：若此时并无 .pack- 临时文件，
            # 「失败后无残留」这条负控就是空转，故一并断言。
            seen.append(self.out_dir_names())
            raise OSError("simulated build failure")

        ns["build"] = boom
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = ns["main"](["--src", str(root), "--out", str(out)])
        self.assertEqual(rc, 2, "build 失败必须 rc=2，实得 %d：%s" % (rc, err.getvalue()))
        self.assertIn("读取或写入失败", err.getvalue())
        self.assertEqual(len(seen), 1, "main 必须调用被替换的 build（否则本用例空转）")
        self.assertEqual(len(seen[0]), 1, "build 之前必须已建临时文件，实得 %r" % (seen[0],))
        self.assertTrue(seen[0][0].startswith(PACK_PREFIX),
                        "临时文件须是 --out 同目录下的 .pack- 前缀文件，实得 %r" % (seen[0][0],))
        self.assertFalse(out.exists(), "失败时不得写出 --out")
        self.assertEqual(self.out_dir_names(), [],
                         "失败后 --out 所在目录不得残留任何文件（含 .pack- 临时文件）")

        # 独立命名空间：上一处打桩不得渗到另一次加载。
        fresh = load_tool_namespace()
        out2 = self.out_dir / "fresh.zip"
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            rc2 = fresh["main"](["--src", str(root), "--out", str(out2)])
        self.assertEqual(rc2, 0, "重新加载的命名空间不得带上一次的打桩")
        self.assertTrue(out2.exists())

    # ── 8b 清理失败须明确报错（rc=2）─────────────────────────────────────
    def test_tmp_cleanup_failure_is_reported_and_rc2(self):
        root = self.make_fixture()
        out = self.out_dir / "cleanup.zip"
        ns = load_tool_namespace()

        def boom_build(entries):
            raise OSError("simulated build failure")

        def boom_unlink(path):
            raise OSError("simulated unlink failure")

        ns["build"] = boom_build
        ns["os"] = OsShim(ns["os"], unlink=boom_unlink)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = ns["main"](["--src", str(root), "--out", str(out)])
        self.assertEqual(rc, 2, "清理失败也必须 rc=2，实得 %d：%s" % (rc, err.getvalue()))
        self.assertIn("临时文件清理失败", err.getvalue(), "清理失败须明确报错")
        self.assertIn("simulated unlink failure", err.getvalue())
        self.assertFalse(out.exists(), "失败时不得写出 --out")

    # ── 9 --out 位于 --src 之内（含同一路径）───────────────────────────────
    def test_out_symlink_is_replaced_not_written_through(self):
        root = self.make_fixture()
        target = self.work / "real-target.zip"
        target.write_bytes(b"PRE-EXISTING-TARGET\n")
        link = self.out_dir / "linked.zip"
        os.symlink(str(target), str(link))
        r = self.run_tool("--src", root, "--out", link)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files, nbytes, sha = self.parse_stdout(r.stdout)
        self.assertEqual((files, nbytes), (3, len(expected_pack(root))))
        self.assertFalse(os.path.islink(str(link)), "os.replace 须替换符号链接本身")
        self.assertEqual(link.read_bytes(), expected_pack(root))
        self.assertEqual(target.read_bytes(), b"PRE-EXISTING-TARGET\n", "不得写穿符号链接目标")
        self.assertEqual(self.out_dir_names(), ["linked.zip"])
    def test_out_inside_src_rc2_and_no_zip(self):
        root = self.make_fixture()
        inside = root / "self.zip"
        r = self.run_tool("--src", root, "--out", inside)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stderr, OUT_IN_SRC % inside, "stderr 须是固定说明")
        self.assertFalse(inside.exists())
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["SKILL.md", "references"],
                         "源目录内不得留下产物")

        same = self.run_tool("--src", root, "--out", root)
        self.assertEqual(same.returncode, 2, same.stdout + same.stderr)
        self.assertEqual(same.stderr, OUT_IN_SRC % root, "同一路径也须拒绝")
        self.assertTrue(root.is_dir(), "同一路径不得动 --src")

        nested = self.out_dir / "nested.zip"
        r3 = self.run_tool("--src", self.work, "--out", nested)
        self.assertEqual(r3.returncode, 2, r3.stdout + r3.stderr)
        self.assertEqual(r3.stderr, OUT_IN_SRC % nested)
        self.assertFalse(nested.exists())
        self.assertEqual(self.out_dir_names(), [])

    # ── 10 源路径写法绕过（`link/.`）──────────────────────────────────────
    def test_src_symlink_with_dot_suffix_rc2(self):
        real = self.work / "real-src"
        real.mkdir()
        (real / "a.md").write_bytes(b"a\n")
        link = self.work / "link-src"
        link.symlink_to(real, target_is_directory=True)
        out = self.out_dir / "dotsuffix.zip"
        r = self.run_tool("--src", str(link) + "/.", "--out", out)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--src 自身是符号链接", r.stderr)
        self.assertFalse(out.exists(), "不得创建 zip")
        self.assertEqual(self.out_dir_names(), [])

    # ── 11 输出父目录经符号链接落进源内 ───────────────────────────────────
    def test_out_parent_symlink_into_src_rc2(self):
        root = self.make_fixture()
        link_parent = self.work / "link-parent"
        link_parent.symlink_to(root, target_is_directory=True)
        out = link_parent / "packed.zip"
        r = self.run_tool("--src", root, "--out", out)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stderr, OUT_IN_SRC % out)
        self.assertFalse((root / "packed.zip").exists(), "不得把产物落进源目录")
        self.assertEqual(expected_zip_names(root),
                         ["SKILL.md", "references/notes.md", "references/z-last.txt"],
                         "源目录内容不得变化")

    # ── 12 replace 失败：保全原有输出、不留残留 ───────────────────────────
    def test_replace_failure_keeps_old_output_and_no_residue(self):
        root = self.make_fixture()
        out = self.out_dir / "keep.zip"
        out.write_bytes(b"OLD-BYTES")

        def boom_replace(src_path, dst_path):
            raise OSError("simulated replace failure")

        ns = load_tool_namespace()
        ns["os"] = OsShim(ns["os"], replace=boom_replace)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = ns["main"](["--src", str(root), "--out", str(out)])
        self.assertEqual(rc, 2, "replace 失败必须 rc=2，实得 %d：%s" % (rc, err.getvalue()))
        self.assertIn("读取或写入失败", err.getvalue())
        self.assertEqual(out.read_bytes(), b"OLD-BYTES", "失败时不得替换原有输出")
        self.assertEqual(self.out_dir_names(), ["keep.zip"], "不得残留临时文件")

    # ── 13 清理失败：如实报告待清理路径并如实残留 ──────────────────────────
    def test_cleanup_failure_reports_pending_path_and_residue(self):
        root = self.make_fixture()
        out = self.out_dir / "cleanup2.zip"
        out.write_bytes(b"OLD-BYTES")              # 预置旧输出：失败时须原样保全

        def boom_build(entries):
            raise OSError("simulated build failure")

        def boom_unlink(path):
            raise OSError("simulated unlink failure")

        ns = load_tool_namespace()
        ns["build"] = boom_build
        ns["os"] = OsShim(ns["os"], unlink=boom_unlink)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = ns["main"](["--src", str(root), "--out", str(out)])
        self.assertEqual(rc, 2, "清理失败必须 rc=2，实得 %d：%s" % (rc, err.getvalue()))
        self.assertIn("临时文件清理失败", err.getvalue())
        self.assertIn("待清理路径", err.getvalue(), "须报告待清理路径")
        self.assertEqual(out.read_bytes(), b"OLD-BYTES", "失败时不得替换原有输出")
        residue = self.out_dir_names()
        temp_names = [n for n in residue if n.startswith(PACK_PREFIX)]
        self.assertEqual(len(temp_names), 1,
                         "残留物须含且仅含一个 .pack- 临时文件，实得 %r" % (residue,))
        self.assertIn(temp_names[0], err.getvalue(), "诊断须给出实际待清理路径（含文件名）")
        (self.out_dir / temp_names[0]).unlink()       # 手工清理，防污染后续断言
        self.assertEqual(self.out_dir_names(), ["cleanup2.zip"])

    # ── 14 临时文件创建失败：不产包、不留残留 ──────────────────────────────
    def test_tempfile_open_failure_rc2_and_no_residue(self):
        root = self.make_fixture()
        out = self.out_dir / "tmpopen.zip"

        class BadTmp:
            def __init__(self, *args, **kwargs):
                raise OSError("simulated tempfile open failure")

        ns = load_tool_namespace()
        ns["tempfile"] = type("T", (), {"NamedTemporaryFile": BadTmp})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = ns["main"](["--src", str(root), "--out", str(out)])
        self.assertEqual(rc, 2, "临时文件创建失败必须 rc=2，实得 %d：%s" % (rc, err.getvalue()))
        self.assertIn("读取或写入失败", err.getvalue())
        self.assertFalse(out.exists())
        self.assertEqual(self.out_dir_names(), [])


def expected_zip_names(root):
    """夹具中文件相对路径的排序列表（供布局断言对照）。"""
    names = []
    for cur, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(cur, name)
            names.append(os.path.relpath(path, root).replace(os.sep, "/"))
    return sorted(names)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""tools/minis-verify.py 本端纵切片（契约见 README〈Minis 本端只读验收〉）：真实 -I -B CLI、Git
双提交＋pack、字节与模式、SOUL/子代理口径、包集合与枚举上限、安全文件边界接缝、投影、聚合。"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "tools", "minis-verify.py")
SOUL = "---\nname: Other\nicon: y\n---\nSOUL 正文\n"
SKILL1 = "---\nname: alpha\ndescription: d\n---\n正文\n"
SKILL2 = SKILL1 + "更多\n"


def _w(path, data, mode=None):
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    if mode is not None:
        os.chmod(path, mode)


def _git(repo, *args):
    return subprocess.check_output(("git",) + args, cwd=repo).decode().strip()


def _commit(repo, message):
    ident = ["-c", "user.name=A", "-c", "user.email=a@x"]
    _git(repo, *ident, "add", "-A")
    _git(repo, *ident, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


def build(tmp):
    repo = os.path.join(tmp, "repo")
    for part in ("tools", "prompt", "subagents", "skills/alpha/references", "skills/alpha/scripts"):
        os.makedirs(os.path.join(repo, part))
    reg = {"schemaVersion": 1, "objects": [
        {"id": "alpha", "type": "skill", "source": "skills/alpha/SKILL.md",
         "resources": ["skills/alpha/references/a.md", "skills/alpha/references/empty.md",
                       "skills/alpha/scripts/run.sh"],
         "ends": {"repo": {"present": True},
                  "minis": {"present": True, "kind": "file", "path": "/var/minis/skills/alpha/SKILL.md"}}},
        {"id": "prompt/P.md", "type": "prompt", "source": "prompt/P.md", "resources": [],
         "ends": {"repo": {"present": True},
                  "minis": {"present": True, "kind": "field", "field": "soul.body",
                            "alsoFile": "/var/minis/memory/SOUL.md"}}},
        {"id": "subagents/S.md", "type": "subagent", "source": "subagents/S.md", "resources": [],
         "ends": {"repo": {"present": True},
                  "minis": {"present": True, "kind": "field",
                            "field": "subagents.general.instructions"}}},
        {"id": "subagents/T.md", "type": "subagent", "source": "subagents/T.md", "resources": [],
         "ends": {"repo": {"present": True},
                  "minis": {"present": True, "kind": "field",
                            "field": "subagents.t.instructions"}}}]}
    _w(os.path.join(repo, "tools/sync-targets.json"), json.dumps(reg))
    _w(os.path.join(repo, "skills/alpha/SKILL.md"), SKILL1)
    _w(os.path.join(repo, "skills/alpha/references/a.md"), b"\x00\xff\x01\r\n")
    _w(os.path.join(repo, "skills/alpha/references/empty.md"), b"")
    _w(os.path.join(repo, "skills/alpha/scripts/run.sh"), "#!/bin/sh\necho hi\n", 0o755)
    _w(os.path.join(repo, "prompt/P.md"), "---\nname: P\n---\nSOUL 正文\n")
    _w(os.path.join(repo, "subagents/S.md"), "instructions body")
    _w(os.path.join(repo, "subagents/T.md"), "instructions with tail \n")
    _git(repo, "init", "-q")
    first = _commit(repo, "one")
    _w(os.path.join(repo, "skills/alpha/SKILL.md"), SKILL2)
    _w(os.path.join(repo, "skills/alpha/scripts/run.sh"), "#!/bin/sh\necho hi\n", 0o644)
    second = _commit(repo, "two")
    _w(os.path.join(repo, "skills/alpha/SKILL.md"), "---\nname: alpha\n---\nworktree\n")
    _git(repo, "gc", "-q", "--prune=now")
    site = os.path.join(tmp, "site")
    for part in ("var/minis/skills/alpha/references", "var/minis/skills/alpha/scripts", "var/minis/memory"):
        os.makedirs(os.path.join(site, part))
    _w(os.path.join(site, "var/minis/skills/alpha/SKILL.md"), SKILL1)
    _w(os.path.join(site, "var/minis/skills/alpha/references/a.md"), b"\x00\xff\x01\r\n")
    _w(os.path.join(site, "var/minis/skills/alpha/references/empty.md"), b"")
    _w(os.path.join(site, "var/minis/skills/alpha/scripts/run.sh"), "#!/bin/sh\necho hi\n", 0o755)
    _w(os.path.join(site, "var/minis/memory/SOUL.md"), SOUL)
    return {"repo": repo, "site": site, "first": first, "second": second}


def projection(soul_body, sub_value, **override):
    doc = {"schemaVersion": 1,
           "observation": {"id": "o", "instanceRef": "i", "sourceVersion": "v", "sourceBasis": "b",
                           "startedAt": "2026-11-15T19:00:00Z",
                           "finishedAt": "2026-11-15T19:00:01Z"},
           "objects": [{"object": "prompt/P.md", "observationId": "o", "instanceRef": "i",
                        "field": "soul.body", "value": soul_body},
                       {"object": "subagents/S.md", "observationId": "o", "instanceRef": "i",
                        "field": "subagents.general.instructions", "value": sub_value}]}
    doc.update(override)
    return doc


def load_tool():
    spec = importlib.util.spec_from_file_location("mv_ut", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MinisVerify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="mv-")
        cls.fx = build(cls.tmp)
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        type(self).count += 1
        self.root = os.path.join(self.tmp, "s%d" % self.count)
        shutil.copytree(self.fx["site"], self.root, symlinks=True)
        self.dir = os.path.join(self.root, "var/minis/skills/alpha")
        self.soul = os.path.join(self.root, "var/minis/memory/SOUL.md")

    def run_cli(self, *args, version=None, objects=("alpha",), projection_path=None):
        argv = [sys.executable, "-I", "-B", TOOL, "--repo", self.fx["repo"],
                "--git-version", version or self.fx["first"], "--root", self.root]
        for obj in objects:
            argv += ["--object", obj]
        if projection_path:
            argv += ["--projection", projection_path]
        proc = subprocess.run(argv + list(args), cwd="/", capture_output=True)
        self.assertEqual(proc.stderr, b"", "stderr 必须是空")
        return proc.returncode, json.loads(proc.stdout.decode()), proc.stdout.decode()

    def status(self, doc, item):
        return next((c["status"] for c in doc["checks"] if c["item"] == item), None)

    def codes(self, doc):
        return sorted({i["code"] for i in doc["issues"]})

    def one(self, rid, field, value):
        doc = projection(self.body(), value)
        doc["objects"] = [{"object": rid, "observationId": "o", "instanceRef": "i",
                           "field": field, "value": value}]
        return doc

    def write_projection(self, doc, raw=None):
        path = os.path.join(self.root, "proj.json")
        _w(path, raw if raw is not None else json.dumps(doc))
        return path

    def body(self):
        path = os.path.join(self.fx["repo"], "prompt/P.md")
        return load_tool()._load_body().body_bytes(open(path, "rb").read()).decode("utf-8")

    # 1 正常纵切片
    def test_live_slice_and_shapes(self):
        proj = self.write_projection(projection(self.body(), "instructions body"))
        rc, doc, text = self.run_cli(objects=("alpha", "prompt/P.md", "subagents/S.md"),
                                     projection_path=proj)
        self.assertEqual(rc, 0, doc["issues"])
        self.assertEqual(doc["status"], "match")
        self.assertEqual(doc["rootView"], "relocated")
        self.assertEqual(doc["gitVersion"], self.fx["first"])
        self.assertEqual({c["status"] for c in doc["checks"]}, {"match"})
        items = [c["item"] for c in doc["checks"]]
        self.assertIn("package-set", items)
        self.assertIn("field:subagents.general.instructions", items)
        self.assertEqual(doc["issues"], [])
        self.assertTrue(any("App" in item for item in doc["notCovered"]))
        self.assertTrue(any("ABA" in item for item in doc["notCovered"]))
        self.assertNotIn("正文", text)
        rc, doc, _text = self.run_cli(objects=("alpha",))
        self.assertEqual(rc, 0)
        self.assertEqual({c["object"] for c in doc["checks"]}, {"alpha"})
        self.assertEqual(len(doc["checks"]), 9)

    # 2 Git 历史与 pack
    def test_git_history_pack_and_missing(self):
        rc, doc, _text = self.run_cli()
        self.assertEqual(rc, 0, doc["issues"])
        rc, doc, _text = self.run_cli(version=self.fx["second"])
        self.assertEqual(rc, 1)
        self.assertEqual(self.status(doc, "file:skills/alpha/SKILL.md"), "different")
        self.assertEqual(self.status(doc, "exec:skills/alpha/scripts/run.sh"), "different")
        for bad in ("HEAD", self.fx["first"][:12], self.fx["first"].upper()):
            rc, doc, _text = self.run_cli(version=bad)
            self.assertEqual(rc, 2)
            self.assertEqual(self.codes(doc), ["bad_args"])
            self.assertIsNone(doc["gitVersion"])
        rc, doc, _text = self.run_cli(version="0" * 40)
        self.assertEqual(rc, 2)
        self.assertEqual(self.codes(doc), ["git_error"])
        self.assertEqual(doc["checks"], [])

    # 3 字节、模式与字段边界
    def test_bytes_modes_and_field_edges(self):
        rc, doc, _text = self.run_cli()
        self.assertEqual(rc, 0, doc["issues"])
        os.chmod(os.path.join(self.dir, "scripts/run.sh"), 0o644)
        _w(os.path.join(self.dir, "references/a.md"), b"\x00\xff\x01\n")
        rc, doc, _text = self.run_cli()
        self.assertEqual(rc, 1)
        self.assertIn("file_exec", self.codes(doc))
        self.assertIn("file_bytes", self.codes(doc))
        self.assertEqual(self.status(doc, "file:skills/alpha/references/empty.md"), "match")
        _w(self.soul, "---\nname: Other\nicon: z\n---\nSOUL 正文\n")
        good = self.write_projection(self.one("prompt/P.md", "soul.body", self.body()))
        rc, doc, _text = self.run_cli(objects=("prompt/P.md",), projection_path=good)
        self.assertEqual(rc, 0, doc["issues"])
        _w(self.soul, "---\nname: Other\n---\nSOUL 正文改写\n")
        rc, doc, _text = self.run_cli(objects=("prompt/P.md",), projection_path=good)
        self.assertEqual(rc, 1)
        self.assertIn("file_bytes", self.codes(doc))
        self.assertNotIn("file_contract", self.codes(doc))
        # 子代理：仓库正文无尾 LF，投影多一个即不同；带一个尾 LF 的仓库文件只允许去掉恰好那一个
        plus = self.one("subagents/S.md", "subagents.general.instructions", "instructions body\n")
        rc, doc, _text = self.run_cli(objects=("subagents/S.md",),
                                      projection_path=self.write_projection(plus))
        self.assertEqual(rc, 1)
        self.assertEqual(self.status(doc, "field:subagents.general.instructions"), "different")
        one = self.one("subagents/T.md", "subagents.t.instructions", "instructions with tail ")
        rc, doc, _text = self.run_cli(objects=("subagents/T.md",),
                                      projection_path=self.write_projection(one))
        self.assertEqual(rc, 0, doc["issues"])
        one["objects"][0]["value"] = "instructions with tail"      # 多加 rstrip 即失败
        rc, doc, _text = self.run_cli(objects=("subagents/T.md",),
                                      projection_path=self.write_projection(one))
        self.assertEqual(rc, 1)
        self.assertEqual(self.status(doc, "field:subagents.t.instructions"), "different")

    # 4 完整包集合与枚举上限
    def test_package_set_and_limits(self):
        os.remove(os.path.join(self.dir, "references/empty.md"))
        _w(os.path.join(self.dir, "extra.txt"), "SYNTHETIC-MARKER")
        os.makedirs(os.path.join(self.dir, "emptydir"))
        rc, doc, text = self.run_cli()
        self.assertEqual(rc, 1)
        self.assertIn("file_missing", self.codes(doc))
        self.assertEqual(sorted(i["path"] for i in doc["issues"] if i["code"] == "package_set"),
                         ["emptydir", "extra.txt"])
        self.assertNotIn("SYNTHETIC-MARKER", text)
        shutil.rmtree(self.dir)
        os.makedirs(self.dir)
        deep = self.dir
        for _ in range(66):
            deep = os.path.join(deep, "d")
            os.mkdir(deep)
        rc, doc, _text = self.run_cli()
        self.assertEqual(rc, 3)
        self.assertIn("enumeration_limit", self.codes(doc))
        self.assertEqual(self.status(doc, "package-set"), "not_checked")

    # 5 安全文件边界（含负控）
    def test_security_boundaries(self):
        os.symlink("/tmp", os.path.join(self.root, "var/minis/skills/evil"))
        broken = os.path.join(self.dir, "references/a.md")
        os.remove(broken)
        os.symlink("/etc/hostname", broken)             # 末级软链：不打开
        os.mkfifo(os.path.join(self.dir, "fifo"))
        rc, doc, _text = self.run_cli()
        self.assertEqual(rc, 3)                 # 软链阻断内容检查，同时记不可验证
        self.assertIn("file_type", self.codes(doc))
        self.assertIn("unsafe_path", self.codes(doc))
        self.assertEqual(self.status(doc, "file:skills/alpha/references/a.md"), "different")
        self.assertIn("package_set", self.codes(doc))
        # 祖先改名：锚定链重开发现不一致 → rc3，不保留 match
        tool = load_tool()
        fence = tool.Fence(tool._abs_parts(self.root, "bad_args") + ["var", "minis", "skills", "alpha"])
        os.rename(self.dir, self.dir + "-moved")
        with self.assertRaises(tool.Reject) as caught:
            fence.recheck()
        self.assertEqual(caught.exception.code, "identity_unverifiable")
        fence.close()
        os.rename(self.dir + "-moved", self.dir)
        os.remove(os.path.join(self.dir, "fifo"))
        os.remove(broken)
        _w(broken, b"\x00\xff\x01\r\n")
        os.remove(os.path.join(self.root, "var/minis/skills/evil"))
        # 负控：去掉注入后恢复 match
        rc, doc, _text = self.run_cli()
        self.assertEqual(rc, 0, doc["issues"])
        # 接缝注入：读取前替换同名文件 → 旧 fd 与新 fd 全 tuple 不一致，不保留 match
        tool = load_tool()
        target = os.path.join(self.dir, "SKILL.md")
        with open(target, "rb") as fh:
            original = fh.read()

        def hook(stage, name):
            if stage == "read" and name == "SKILL.md":
                tool.HOOK = None
                staging = os.path.join(self.dir, ".new")
                _w(staging, b"REPLACED")
                os.replace(staging, target)

        tool.HOOK = hook
        argv = ["--repo", self.fx["repo"], "--git-version", self.fx["first"],
                "--root", self.root, "--object", "alpha"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                rc = tool.main(argv)
        finally:
            tool.HOOK = None
        doc = json.loads(out.getvalue())
        self.assertEqual(rc, 3)
        self.assertTrue({"identity_unverifiable", "changed_during_read"} & set(self.codes(doc)))
        # 原语级正控/负控：名字被替换后同父重开与仍存活旧 fd 全 tuple 不一致
        tool = load_tool()
        fence = tool.Fence(tool._abs_parts(self.root, "bad_args") + ["var", "minis", "skills", "alpha"])
        fd = os.open("SKILL.md", tool.FILE_FLAGS, dir_fd=fence.fd)
        self.assertTrue(tool._reopen_same(fence.fd, "SKILL.md", fd))
        _w(os.path.join(self.dir, ".o"), b"R")
        os.replace(os.path.join(self.dir, ".o"), os.path.join(self.dir, "SKILL.md"))
        self.assertFalse(tool._reopen_same(fence.fd, "SKILL.md", fd))
        os.close(fd)
        fence.close()
        self.assertEqual(self.status(doc, "file:skills/alpha/SKILL.md"), "not_checked")
        _w(target, original)
        rc, doc, _text = self.run_cli()                  # 负控：恢复后 match
        self.assertEqual(rc, 0, doc["issues"])

    # 6 配置投影
    def test_projection_rules(self):
        soul = self.write_projection(self.one("prompt/P.md", "soul.body", self.body()))
        rc, doc, _text = self.run_cli(objects=("prompt/P.md",))
        self.assertEqual(rc, 3)   # 未传投影仍检查独立文件
        self.assertEqual(self.codes(doc), ["missing_projection"])
        self.assertEqual(self.status(doc, "file:prompt/P.md"), "match")
        rc, doc, _text = self.run_cli(objects=("alpha",), projection_path=soul)
        self.assertEqual(rc, 2)   # 只选文件对象时投影不必要
        self.assertEqual(self.codes(doc), ["bad_args"])
        self.assertEqual(doc["checks"], [])   # 且不打开目标文件
        empty = self.write_projection(projection(self.body(), "x", objects=[]))
        rc, doc, _text = self.run_cli(objects=("prompt/P.md", "subagents/S.md"), projection_path=empty)
        self.assertEqual(rc, 3)
        self.assertEqual(self.codes(doc), ["missing_object"])
        nulls = self.write_projection(projection(None, None))
        rc, doc, _text = self.run_cli(objects=("prompt/P.md", "subagents/S.md"), projection_path=nulls)
        self.assertEqual(rc, 1)
        self.assertEqual(self.status(doc, "field:soul.body"), "different")
        blanks = self.write_projection(projection("", ""))
        rc, doc, _text = self.run_cli(objects=("prompt/P.md", "subagents/S.md"), projection_path=blanks)
        self.assertEqual(rc, 1)   # 空串是可比较值
        extra = projection(self.body(), "instructions body")
        extra["objects"].append({"object": "alpha", "observationId": "o", "instanceRef": "i",
                                 "field": "soul.body", "value": ""})
        rc, doc, _text = self.run_cli(objects=("prompt/P.md", "subagents/S.md"),
                                      projection_path=self.write_projection(extra))
        self.assertEqual(rc, 2)
        self.assertIn("unselected_object", self.codes(doc))
        bound = projection(self.body(), "instructions body")
        bound["objects"][0]["field"] = "soul.other"
        bound["objects"][1]["instanceRef"] = "other"
        rc, doc, _text = self.run_cli(objects=("prompt/P.md", "subagents/S.md"),
                                      projection_path=self.write_projection(bound))
        self.assertEqual(rc, 2)
        self.assertIn("field_binding", self.codes(doc))

    # 7 固定失败与聚合
    def test_strict_json_and_aggregation(self):
        good = json.dumps(projection(self.body(), "instructions body"))
        dup = good.replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1')
        nan = good.replace('"schemaVersion": 1', '"schemaVersion": NaN')
        lone = good.replace('"sourceBasis": "b"', '"sourceBasis": "\\ud800"')
        for raw, want in ((dup, "duplicate_key"), (nan, "bad_json"), (lone, "bad_json")):
            rc, doc, _text = self.run_cli(objects=("subagents/S.md",),
                                          projection_path=self.write_projection(None, raw))
            self.assertEqual(rc, 2, want)
            self.assertEqual(self.codes(doc), [want])
        short = {"schemaVersion": 1, "observation": {"startedAt": 5},
                 "objects": [{"object": "subagents/S.md"}], "extra": []}
        rc, doc, _text = self.run_cli(objects=("subagents/S.md",),
                                      projection_path=self.write_projection(short))
        self.assertEqual(rc, 2)
        codes = self.codes(doc)
        self.assertIn("bad_shape", codes)   # 已给错类型仍被检查
        self.assertIn("missing_field", codes)   # 缺键同时保留
        self.assertIn("unknown_key", codes)
        # 聚合：确证差异 + 缺证并存 → rc3，两者都保留
        os.chmod(os.path.join(self.dir, "scripts/run.sh"), 0o644)
        rc, doc, _text = self.run_cli(objects=("alpha", "subagents/S.md"))
        self.assertEqual(rc, 3)
        self.assertIn("file_exec", self.codes(doc))
        self.assertIn("missing_projection", self.codes(doc))
        self.assertEqual(doc["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()

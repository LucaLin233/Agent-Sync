#!/usr/bin/env python3
"""lh-deploy 离线合成用例：真实子进程假 CLI/假 collect/假 verify，不联网、无秘密。

覆盖：base 验收非 0 → 零写（含第二对象不启动）；写失败 → 不再补写、不报成功、changed=unknown；
post 非 0 → rc≠0 且不报 completed；正常路径可过（负控：去掉阻断即转绿）；argv 原样传递。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "tools", "lh-deploy.py")
PY = sys.executable or "python3"

STUB_COLLECT = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
out = args[args.index("--out-dir") + 1]
os.mkdir(out, 0o700)
with open(os.path.join(out, "skill-evidence.json"), "w", encoding="utf-8") as h:
    h.write("{}\\n")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".collect.log"), "a") as h:
    h.write(args[args.index("--git-version") + 1] + "\\n")
"""

STUB_VERIFY = """#!/usr/bin/env python3
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
phase = "pre" if "pre-" in " ".join(sys.argv) else "post"
marker = os.path.join(here, ".verdict." + phase)
sys.exit(int(open(marker).read().strip()) if os.path.exists(marker) else 0)
"""

FAKE_LH = """#!/bin/sh
printf '%s\\n' "$@" > "$(dirname "$0")/lh.argv"
cat "$(dirname "$0")/lh.rc" 2>/dev/null >/dev/null
exit "$(cat "$(dirname "$0")/lh.rc" 2>/dev/null || echo 0)"
"""

TARGET = {"ssh": {"host": "h.example", "port": 22, "user": "u",
                  "knownHostsFile": "/etc/ssh/ssh_known_hosts"},
          "postgres": {"container": "db", "database": "lob", "port": 5432, "user": "lob"}}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lh-deploy-test-")
        self.repo = os.path.join(self.tmp, "repo")
        self.bin = os.path.join(self.tmp, "bin")
        for path in (self.repo, self.bin, os.path.join(self.tmp, "tmp")):
            os.makedirs(path, exist_ok=True)
        self.out = os.path.join(self.tmp, "out")
        self.env = {"PATH": self.bin + ":/usr/bin:/bin", "TMPDIR": os.path.join(self.tmp, "tmp"),
                    "LC_ALL": "C.UTF-8", "HOME": self.tmp,
                    "LOBEHUB_SERVER": "https://example.invalid",
                    "LOBEHUB_CLI_API_KEY": "test-token-value"}
        self.write("tools/lh-collect.py", STUB_COLLECT)
        self.write("tools/lh-verify.py", STUB_VERIFY)
        self.write("skills/one/SKILL.md", "one\n")
        self.write("skills/two/SKILL.md", "two\n")
        self.write("prompt/X.md", "x\n")
        self.write("tools/sync-targets.json", json.dumps({"schemaVersion": 1, "objects": [
            self.entry("one"), self.entry("two"), self.agent_entry()]}))
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@e",
                        "commit", "-qm", "base"], check=True)
        self.base = self.git("rev-parse", "HEAD")
        self.write("note2.txt", "agent-merged\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@e",
                        "commit", "-qm", "merged"], check=True)
        self.merged = self.git("rev-parse", "HEAD")
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", self.repo], check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", "-C", self.repo] + list(args),
                              capture_output=True, text=True, check=True).stdout.strip()

    def entry(self, name):
        return {"id": name, "type": "skill", "source": "skills/%s/SKILL.md" % name,
                "resources": ["skills/%s/SKILL.md" % name],
                "installSource": "https://github.com/o/r/tree/main/skills/" + name,
                "ends": {"lobehub": {"present": True, "kind": "skill",
                                     "id": "skill-" + name}}}

    def agent_entry(self):
        return {"id": "prompt/X.md", "type": "prompt", "source": "prompt/X.md",
                "resources": [], "ends": {"lobehub": {"present": True, "kind": "agent",
                                                     "id": "agt_1", "field": "systemRole"}}}

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def lh(self, rc):
        path = os.path.join(self.bin, "lh")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(FAKE_LH)
        os.chmod(path, 0o755)
        with open(os.path.join(self.bin, "lh.rc"), "w", encoding="utf-8") as handle:
            handle.write("%d\n" % rc)

    def verdict(self, phase, rc):
        with open(os.path.join(self.repo, "tools", ".verdict." + phase), "w") as handle:
            handle.write(str(rc))

    def run_tool(self, objects=("one",)):
        argv = [PY, "-I", "-B", TOOL, "--repo", self.repo, "--base", self.base,
                "--merged", self.merged, "--out-dir", self.out,
                "--instance-ref", "inst-1", "--source-basis", "basis-ref",
                "--total-timeout", "30"]
        for item in objects:
            argv += ["--object", item]
        return subprocess.run(argv, input=json.dumps(TARGET).encode(),
                              env=dict(self.env), capture_output=True, timeout=120)

    def argv_log(self):
        with open(os.path.join(self.bin, "lh.argv"), encoding="utf-8") as handle:
            return handle.read().splitlines()

    def test_pre_difference_blocks_all_writes(self):
        self.lh(0)
        self.verdict("pre", 1)
        proc = self.run_tool(("one", "two"))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.bin, "lh.argv")))
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["objects"][0]["code"], "pre_difference")
        self.assertEqual(summary["objects"][1]["status"], "not_run")
        self.assertNotEqual(summary["status"], "complete")

    def test_write_failure_stops_without_retry(self):
        self.lh(1)
        proc = self.run_tool(("one", "two"))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        summary = json.loads(proc.stdout)
        first = summary["objects"][0]
        self.assertEqual(first["code"], "cli_error")
        self.assertEqual(first["changed"], "unknown")
        self.assertEqual(summary["objects"][1]["status"], "not_run")
        self.assertEqual(len([p for p in os.listdir(self.out) if p.startswith("post-")]), 0)

    def test_post_difference_not_reported_completed(self):
        self.lh(0)
        self.verdict("post", 1)
        proc = self.run_tool(("one",))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["objects"][0]["code"], "post_difference")
        self.assertNotEqual(summary["status"], "complete")

    def test_clean_path_completes_and_argv_exact(self):
        self.lh(0)
        proc = self.run_tool(("one",))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["objects"][0]["changed"], True)
        self.assertEqual(self.argv_log(), [
            "skill", "install", "https://github.com/o/r/tree/main/skills/one"])
        self.assertTrue(os.path.isdir(os.path.join(self.out, "post-0")))

    def test_agent_blocked_without_write(self):
        self.lh(0)
        proc = self.run_tool(("prompt/X.md",))
        self.assertEqual(proc.returncode, 3, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["objects"][0]["code"], "unsupported")
        self.assertFalse(os.path.exists(os.path.join(self.bin, "lh.argv")))


if __name__ == "__main__":
    unittest.main()

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
name = args[args.index("--object") + 1]
if name.startswith("prompt/"):
    role = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agentcontent")
    value = open(role, encoding="utf-8").read() if os.path.exists(role) else "x\\n"
    doc = {"schemaVersion": 1,
           "observation": {"id": "obs-test", "instanceRef": "inst-1"},
           "objects": [{"object": name, "observationId": "obs-test",
                        "instanceRef": "inst-1", "id": "agt_1",
                        "field": "systemRole", "value": value}]}
    with open(os.path.join(out, "agent-evidence.json"), "w", encoding="utf-8") as h:
        h.write(json.dumps(doc) + "\\n")
    sys.exit(0)
content = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".postcontent")
value = open(content, encoding="utf-8").read() if os.path.exists(content) else ""
with open(os.path.join(out, "skill-evidence.json"), "w", encoding="utf-8") as h:
    h.write(json.dumps({"objects": [{"projection": {"content": value}}]}) + "\\n")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".collect.log"), "a") as h:
    h.write(args[args.index("--git-version") + 1] + "\\n")
"""

STUB_VERIFY = """#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
phase = "pre" if "pre-" in " ".join(sys.argv) else "post"
marker = os.path.join(here, ".verdict." + phase)
rc = int(open(marker).read().strip()) if os.path.exists(marker) else 0
seen = 0
if phase == "post":
    counter = os.path.join(here, ".postcalls")
    seen = int(open(counter).read().strip()) if os.path.exists(counter) else 0
    with open(counter, "w") as h:
        h.write(str(seen + 1))
if phase == "post" and rc == 1 and seen == 0:
    sys.stdout.write(json.dumps({"gitVersion": "x", "status": "different", "objects": [
        {"object": "one", "differences": ["content"], "missingEvidence": [],
         "errors": [], "resourcePaths": {"missing": [], "extra": []}}]}) + "\\n")
    sys.exit(1)
sys.stdout.write(json.dumps({"gitVersion": "x", "status": "match", "objects": []}) + "\\n")
sys.exit(0 if (phase == "post" and seen >= 1) else rc)
"""

FAKE_GIT = """#!/bin/sh
for a in "$@"; do
  if [ "$a" = "ls-remote" ]; then
    cat "$(dirname "$0")/head" ; printf '\\trefs/heads/main\\n' 
    exit 0
  fi
done
exec REALGIT "$@"
"""

FAKE_LH = """#!/usr/bin/env python3
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "lh.argv"), "ab") as h:
    for arg in sys.argv[1:]:
        h.write(arg.encode("utf-8") + b"\\x00")
rc = 0
marker = os.path.join(here, "lh.rc")
if os.path.exists(marker):
    rc = int(open(marker).read().strip())
sys.exit(rc)
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
        realgit = shutil.which("git")
        self.assertTrue(realgit and os.path.isabs(realgit))
        with open(os.path.join(self.bin, "git"), "w", encoding="utf-8") as handle:
            handle.write(FAKE_GIT.replace("REALGIT", realgit))
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
        os.chmod(os.path.join(self.bin, "git"), 0o755)
        with open(os.path.join(self.bin, "head"), "w", encoding="utf-8") as handle:
            handle.write(self.merged)

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
        argv_file = os.path.join(self.bin, "lh.argv")
        if os.path.exists(argv_file):
            os.unlink(argv_file)
        with open(os.path.join(self.bin, "lh.rc"), "w", encoding="utf-8") as handle:
            handle.write("%d\n" % rc)

    def verdict(self, phase, rc):
        with open(os.path.join(self.repo, "tools", ".verdict." + phase), "w") as handle:
            handle.write(str(rc))

    def run_tool(self, objects=("one",)):
        argv = [PY, "-I", "-B", TOOL, "--repo", self.repo, "--base", self.base,
                "--merged", self.merged, "--out-dir", self.out,
                "--instance-ref", "inst-1", "--source-basis", "basis-ref",
                "--source-version", "2.3.3+testbuild", "--total-timeout", "30"]
        for item in objects:
            argv += ["--object", item]
        return subprocess.run(argv, input=json.dumps(TARGET).encode(),
                              env=dict(self.env), capture_output=True, timeout=120)

    def argv_log(self):
        path = os.path.join(self.bin, "lh.argv")
        if not os.path.exists(path):
            return []
        with open(path, "rb") as handle:
            raw = handle.read()
        return [item.decode("utf-8") for item in raw.split(b"\0")[:-1]]

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

    def test_tail_lf_single_correction_uses_argv(self):
        """post 仅差 content 且现场==期望去一个尾 LF：按 argv 原样补一次全文再全量重采复验。"""
        self.lh(0)
        self.verdict("post", 1)
        with open(os.path.join(self.repo, "tools", ".postcontent"), "w",
                  encoding="utf-8") as handle:
            handle.write("one")          # 期望正文 "one\\n"，现场少一个尾 LF
        proc = self.run_tool(("one",))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.argv_log(), [
            "skill", "install", "https://github.com/o/r/tree/main/skills/one",
            "skill", "edit", "skill-one", "-c", "one\n"])
        self.assertTrue(os.path.isdir(os.path.join(self.out, "post-0-fix")))
        self.assertEqual(json.loads(proc.stdout)["objects"][0]["changed"], True)

    def agent_content(self, value):
        with open(os.path.join(self.repo, "tools", ".agentcontent"), "w",
                  encoding="utf-8") as handle:
            handle.write(value)

    def test_agent_pre_difference_blocks_write(self):
        """Agent 前验 systemRole 与 base 正文不等的 bytes：判 pre_difference，写数 0。"""
        self.lh(0)
        self.agent_content("other\n")
        proc = self.run_tool(("prompt/X.md",))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["objects"][0]["code"], "pre_difference")
        self.assertEqual(summary["objects"][0]["changed"], False)
        self.assertEqual(self.argv_log(), [])
        self.assertFalse([p for p in os.listdir(self.out) if p.startswith("agent-")])

    def test_agent_clean_path_edits_with_config_file(self):
        """Agent 正常链：pre 相等 → `lh agent edit ID --config-file` 传完整 systemRole → post 严格相等。"""
        self.lh(0)
        self.agent_content("x\n")
        proc = self.run_tool(("prompt/X.md",))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["objects"][0]["changed"], True)
        argv = self.argv_log()
        self.assertEqual(argv[:3], ["agent", "edit", "agt_1"])
        self.assertEqual(argv[3], "--config-file")
        cfg = argv[4]
        with open(cfg, "rb") as handle:
            raw = handle.read()
        self.assertEqual(json.loads(raw.decode("utf-8")), {"systemRole": "x\n"})
        self.assertEqual(os.stat(cfg).st_mode & 0o777, 0o600)
        self.assertTrue(os.path.isdir(os.path.join(self.out, "post-0")))

if __name__ == "__main__":
    unittest.main()

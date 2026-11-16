#!/usr/bin/env python3
"""lh-collect 离线合成用例：不联网、无秘密、无真实实例。

覆盖：白名单投影、资源实际完整键（非登记自证）、只读交集调用、null/空串区分、尾 LF 保留、
原响应/失败调用与观察关联、Agent 未核准前提真实 rc3、缺失源行 rc3 不写证据。
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "tools", "lh-collect.py")
PY = sys.executable or "python3"

FAKE_SSH = """#!/bin/sh
cat > /dev/null
cat "$(dirname "$0")/row"
"""

FAKE_AUTH = """#!/usr/bin/env python3
import hashlib, json, sys
args = sys.argv[1:]
path = args[args.index("--path") + 1]
if path == "references/fail.md":
    sys.stdout.write("")
    sys.stderr.write(json.dumps({"ok": False, "error": "transport_error"}) + "\\n")
    sys.exit(2)
blob = b"resource:" + path.encode()
doc = {"ok": True, "action": "skill-resource", "resource": {
    "content": blob.decode(), "encoding": "utf8", "fileHash": hashlib.sha256(blob).hexdigest(),
    "fileType": "text/plain", "path": path, "size": len(blob)}}
sys.stdout.write(json.dumps(doc) + "\\n")
"""

TARGET = {"ssh": {"host": "h.example", "port": 22, "user": "u",
                  "knownHostsFile": "/etc/ssh/ssh_known_hosts"},
          "postgres": {"container": "db", "database": "lob", "port": 5432, "user": "lob"}}


def row(skill_id="skill-example", content="body\n", name=None, resources=("references/a.md",)):
    def b64(value):
        return base64.b64encode(value.encode()).decode()
    return json.dumps({"id": skill_id, "name": name, "description": "",
                       "identifier": None, "content": b64(content),
                       "resources": list(resources)}, separators=(",", ":"))


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lh-collect-test-")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "tools"))
        os.makedirs(os.path.join(self.repo, "skills", "example-skill", "references"))
        self.env = {"PATH": os.path.join(self.tmp, "bin") + ":/usr/bin:/bin",
                    "TMPDIR": os.path.join(self.tmp, "tmp"), "LC_ALL": "C.UTF-8",
                    "HOME": os.path.join(self.tmp, "home")}
        for key in ("bin", "tmp", "home"):
            os.makedirs(os.path.join(self.tmp, key), exist_ok=True)
        self._write("tools/auth-call.py", FAKE_AUTH, 0o755)
        self._write("skills/example-skill/SKILL.md", "---\nname: example-skill\n---\nbody\n")
        self._write("skills/example-skill/references/a.md", "a")
        registry = {"schemaVersion": 1, "objects": [{
            "id": "example-skill", "type": "skill", "source": "skills/example-skill/SKILL.md",
            "resources": ["skills/example-skill/SKILL.md",
                          "skills/example-skill/references/a.md"],
            "installSource": "https://github.com/o/r/tree/main/skills/example-skill",
            "ends": {"lobehub": {"present": True, "kind": "skill", "id": "skill-example"}}}]}
        self._write("tools/sync-targets.json", json.dumps(registry))
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@e",
                        "commit", "-qm", "base"], check=True)
        self.version = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                                      capture_output=True, text=True, check=True).stdout.strip()
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel, text, mode=0o644):
        path = os.path.join(self.repo, rel)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(path, mode)

    def fake_ssh(self, output):
        ssh = os.path.join(self.tmp, "bin", "ssh")
        with open(ssh, "w", encoding="utf-8") as handle:
            handle.write(FAKE_SSH)
        os.chmod(ssh, 0o755)
        with open(os.path.join(self.tmp, "bin", "row"), "w", encoding="utf-8") as handle:
            handle.write(output + "\n")

    def run_tool(self, extra_env=None, objects=("example-skill",), target=TARGET):
        argv = [PY, "-I", "-B", TOOL, "--repo", self.repo, "--git-version", self.version,
                "--out-dir", self.out, "--instance-ref", "inst-1",
                "--source-basis", "basis-ref", "--total-timeout", "30"]
        for item in objects:
            argv += ["--object", item]
        env = dict(self.env)
        env.update(extra_env or {})
        return subprocess.run(argv, input=json.dumps(target).encode(), env=env,
                              capture_output=True, timeout=120)

    def creds(self):
        return {"SSH_PRIVATE_KEY_B64": base64.b64encode(b"test-only").decode(),
                "LOBEHUB_SERVER": "https://example.invalid",
                "LOBEHUB_CLI_API_KEY": "test-token-value"}

    def test_evidence_whitelist_and_actual_keys(self):
        # 实际键含未登记的 references/extra.md：只报告、不取正文；调用只覆盖登记∩实际。
        self.fake_ssh(row(resources=("references/a.md", "references/extra.md")))
        proc = self.run_tool(self.creds())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(self.out, "skill-evidence.json"), encoding="utf-8") as handle:
            doc = json.load(handle)
        self.assertEqual(doc["schemaVersion"], 1)
        obj = doc["objects"][0]
        self.assertEqual(sorted(obj), ["calls", "instanceRef", "object", "observationId",
                                       "projection", "resourcePaths"])
        self.assertEqual(sorted(obj["projection"]),
                         ["content", "description", "id", "identifier", "name"])
        self.assertEqual(obj["resourcePaths"], ["references/a.md", "references/extra.md"])
        self.assertEqual([c["request"]["path"] for c in obj["calls"]], ["references/a.md"])
        self.assertEqual(obj["calls"][0]["stdout"].count("\n"), 1)
        self.assertTrue(obj["calls"][0]["stdout"].endswith("\n"))
        self.assertIsNone(obj["projection"]["name"])          # null 与空串区分
        self.assertEqual(obj["projection"]["description"], "")
        self.assertEqual(obj["projection"]["content"], "body\n")  # 尾 LF 保留
        with open(os.path.join(self.out, "projection-source.json"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("h.example", source)
        self.assertNotIn("test-token-value", proc.stdout.decode())

    def test_failed_call_kept_with_association(self):
        self.fake_ssh(row(resources=("references/a.md", "references/fail.md")))
        self._write("tools/sync-targets.json", json.dumps({"schemaVersion": 1, "objects": [{
            "id": "example-skill", "type": "skill",
            "source": "skills/example-skill/SKILL.md",
            "resources": ["skills/example-skill/references/a.md",
                          "skills/example-skill/references/fail.md"],
            "installSource": "https://github.com/o/r/tree/main/skills/example-skill",
            "ends": {"lobehub": {"present": True, "kind": "skill", "id": "skill-example"}}}]}))
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@e",
                        "commit", "-qm", "two"], check=True)
        self.version = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                                      capture_output=True, text=True, check=True).stdout.strip()
        proc = self.run_tool(self.creds())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(self.out, "skill-evidence.json"), encoding="utf-8") as handle:
            obj = json.load(handle)["objects"][0]
        calls = {c["request"]["path"]: c for c in obj["calls"]}
        self.assertEqual(calls["references/fail.md"]["exitCode"], 2)
        self.assertEqual(calls["references/fail.md"]["stdout"], "")
        self.assertEqual(json.loads(calls["references/fail.md"]["stderr"])["error"],
                         "transport_error")
        self.assertEqual(calls["references/fail.md"]["observationId"],
                         obj["observationId"])

    def test_agent_blocked_before_credentials(self):
        self._write("tools/sync-targets.json", json.dumps({"schemaVersion": 1, "objects": [{
            "id": "prompt/X.md", "type": "prompt", "source": "prompt/X.md", "resources": [],
            "ends": {"lobehub": {"present": True, "kind": "agent", "id": "agt_1",
                                 "field": "systemRole"}}}]}))
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@e",
                        "commit", "-qm", "agent"], check=True)
        self.version = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                                      capture_output=True, text=True, check=True).stdout.strip()
        proc = self.run_tool(objects=("prompt/X.md",))  # 无任何凭据变量
        self.assertEqual(proc.returncode, 3)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["status"], "incomplete")
        self.assertEqual(summary["objects"][0]["code"], "schema_unverified")
        self.assertFalse(os.path.exists(os.path.join(self.out, "agent-evidence.json")))

    def test_missing_row_is_rc3_without_evidence(self):
        self.fake_ssh("MISSING")
        proc = self.run_tool(self.creds())
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(os.path.exists(os.path.join(self.out, "skill-evidence.json")))

    def test_missing_variable_named(self):
        self.fake_ssh(row())
        creds = self.creds()
        del creds["LOBEHUB_CLI_API_KEY"]
        proc = self.run_tool(creds)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(json.loads(proc.stderr)["error"],
                         "missing_variable:LOBEHUB_CLI_API_KEY")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""lh-deploy 离线合成用例：真实子进程假 CLI/假 collect/假 verify，不联网、无秘密。

覆盖：base 验收非 0 → 零写（含第二对象不启动）；写失败 → 不再补写、不报成功、changed=unknown；
post 非 0 → rc≠0 且不报 completed；正常路径可过（负控：去掉阻断即转绿）；argv 原样传递；
SSH 目标默认/独立覆盖、pre/post ssh_auth_failed 的零写与写后状态。
成本：Minis/iSH 本批 runner 实测 10.29s（秒级汇总10s），直接模块9.857s；真实总截止/信号/KeyRoot清理回归及恢复正控不可用mock或删断言降级。仅opt-in，父已接受本批小幅超10秒例外；如需提速另行证明等价。
"""
import base64
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "tools", "lh-deploy.py")
TOOLS_DIR = os.path.join(os.path.dirname(HERE), "tools")
TOOL_REAL_COLLECT = os.path.join(TOOLS_DIR, "lh-collect.py")
TOOL_REAL_BODY = os.path.join(TOOLS_DIR, "body_contract.py")
TOOL_SHARED_TARGET = os.path.join(TOOLS_DIR, "ssh_target.py")
PY = sys.executable or "python3"

STUB_COLLECT = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
fd = int(args[args.index("--_cleanup-fd") + 1]) if "--_cleanup-fd" in args else None
def ack():
    if fd is not None:
        os.write(fd, b'{"event":"cleanup","residuals":[]}' + bytes([10]))
here = os.path.dirname(os.path.abspath(__file__))
raw = sys.stdin.buffer.read()
with open(os.path.join(here, ".collect.stdin"), "wb") as h:
    h.write(raw)
out = args[args.index("--out-dir") + 1]
os.mkdir(out, 0o700)
name = args[args.index("--object") + 1]
fail = os.path.join(here, ".fail-" + os.path.basename(out).split("-")[0])
if os.path.exists(fail):
    code = open(fail, encoding="utf-8").read().strip()
    ack()
    if fd is not None:
        os.write(fd, json.dumps({"event": "result", "error": code}).encode() + bytes([10]))
    sys.exit(3)
if name.startswith("prompt/"):
    role = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agentcontent")
    value = open(role, encoding="utf-8").read() if os.path.exists(role) else "x\\n"
    doc = {"schemaVersion": 1,
           "observation": {"id": "obs-test", "instanceRef": "inst-1"},
           "objects": [{"object": name, "observationId": "obs-test",
                        "instanceRef": "inst-1", "id": "agt_1",
                        "field": "systemRole", "value": value}]}
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".symlink")):
        with open(os.path.join(out, "real.json"), "w", encoding="utf-8") as h:
            h.write(json.dumps(doc) + "\\n")
        os.symlink("real.json", os.path.join(out, "agent-evidence.json"))
        ack()
        sys.exit(0)
    with open(os.path.join(out, "agent-evidence.json"), "w", encoding="utf-8") as h:
        h.write(json.dumps(doc) + "\\n")
    ack()
    sys.exit(0)
content = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".postcontent")
value = open(content, encoding="utf-8").read() if os.path.exists(content) else ""
with open(os.path.join(out, "skill-evidence.json"), "w", encoding="utf-8") as h:
    h.write(json.dumps({"objects": [{"projection": {"content": value}}]}) + "\\n")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".collect.log"), "a") as h:
    h.write(args[args.index("--git-version") + 1] + "\\n")
ack()
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

FAKE_SSH_SLOW = """#!/bin/sh
exec sleep 5
"""

FAKE_SSH_OK = """#!/bin/sh
cmd=
for a in "$@"; do cmd=$a; done
cat > /dev/null
exec /bin/sh -c "$cmd"
"""

FAKE_DOCKER = """#!/bin/sh
cat "$(dirname "$0")/row"
"""


def agent_row():
    """真实 agents 固定投影契约：只 system_role 走 base64，身份列原文。"""
    role = base64.encodebytes("x\n".encode()).decode()
    return json.dumps({"id": "agt_1", "user_id": "usr_1", "workspace_id": None,
                       "system_role_b64": role}, separators=(",", ":"))


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
        shutil.copyfile(TOOL_SHARED_TARGET, os.path.join(self.repo, "tools", "ssh_target.py"))
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

    def run_tool(self, objects=("one",), env=None, timeout="30", target=None):
        argv = [PY, "-I", "-B", TOOL, "--repo", self.repo, "--base", self.base,
                "--merged", self.merged, "--out-dir", self.out,
                "--instance-ref", "inst-1", "--source-basis", "basis-ref",
                "--source-version", "2.3.3+testbuild", "--total-timeout", timeout]
        for item in objects:
            argv += ["--object", item]
        return subprocess.run(argv, input=json.dumps(target or TARGET).encode(),
                              env=dict(env or self.env), capture_output=True, timeout=120)

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
        # 未走尾 LF 纠正路径时不得列出并不存在的 fix 产物。
        self.assertEqual(summary["artifacts"], [
            "pre-0/skill-evidence.json", "post-0/skill-evidence.json",
            "verify-pre-0.json", "verify-post-0.json"])

    def test_body_containing_blob_word_is_full_read(self):
        """正文含 ` blob ` 子串时按头部长度跳过正文，不得据此判旧 blob 不完整（source_unverified）。"""
        self.lh(0)
        self.write("skills/one/SKILL.md", "one blob inside blob\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@e",
                        "commit", "-qm", "blob word"], check=True)
        self.base = self.merged = self.git("rev-parse", "HEAD")
        with open(os.path.join(self.bin, "head"), "w", encoding="utf-8") as handle:
            handle.write(self.merged)
        proc = self.run_tool(("one",))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "complete")

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
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["objects"][0]["changed"], True)
        # 最终复核成功的 fix 产物要进摘要索引，原 pre/post 四项照旧保留并指向已生成产物。
        self.assertEqual(summary["artifacts"], [
            "pre-0/skill-evidence.json", "post-0/skill-evidence.json",
            "verify-pre-0.json", "verify-post-0.json",
            "post-0-fix/skill-evidence.json", "verify-post-0-fix.json"])
        for rel in summary["artifacts"]:
            self.assertTrue(os.path.isfile(os.path.join(self.out, rel)), rel)

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

    def test_missing_api_variable_blocks_before_cli(self):
        """Agent 部署也须先核本次两个 API 变量：缺者 missing_variable:NAME rc3，零 CLI。"""
        self.lh(0)
        self.agent_content("x\n")
        for missing in ("LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY"):
            with self.subTest(missing=missing):
                env = dict(self.env)
                del env[missing]
                proc = self.run_tool(("prompt/X.md",), env=env)
                self.assertEqual(proc.returncode, 3, proc.stderr)
                self.assertEqual(json.loads(proc.stderr)["error"], "missing_variable:" + missing)
                self.assertFalse(os.path.exists(self.out))
                self.assertEqual(self.argv_log(), [])

    def test_agent_evidence_symlink_rejected(self):
        """证据叶以 O_NOFOLLOW 在锚定 FD 上打开：软链证据直接 unsafe_path，不跟链读取。"""
        self.lh(0)
        self.agent_content("x\n")
        with open(os.path.join(self.repo, "tools", ".symlink"), "w", encoding="utf-8"):
            pass
        proc = self.run_tool(("prompt/X.md",))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["objects"][0]["code"], "unsafe_path")
        self.assertEqual(self.argv_log(), [])

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

    def test_shared_ssh_target_defaults_and_explicit_overrides(self):
        """两工具同一解析：省略逐字段补 root:9399，显式可独立覆盖，非法值 bad_target。"""
        import importlib.util

        def load(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        deploy = load("lh_deploy_target", TOOL)
        collect = load("lh_collect_target", TOOL_REAL_COLLECT)
        cases = (
            ((), "deploy", 2222),
            (("user",), "root", 2222),
            (("port",), "deploy", 9399),
            (("user", "port"), "root", 9399),
        )
        for omitted, user, port in cases:
            target = copy.deepcopy(TARGET)
            target["ssh"]["user"] = "deploy"
            target["ssh"]["port"] = 2222
            for key in omitted:
                target["ssh"].pop(key)
            raw = json.dumps(target).encode()
            normalized = deploy._target(raw)
            ssh, pg = collect._target(raw)
            self.assertEqual((normalized["ssh"]["user"], normalized["ssh"]["port"]),
                             (user, port))
            self.assertEqual((ssh["user"], ssh["port"]), (user, port))
            self.assertEqual(normalized["ssh"], ssh)
            self.assertEqual(normalized["postgres"], pg)
        bad = copy.deepcopy(TARGET)
        bad["ssh"]["port"] = "22"
        for module in (deploy, collect):
            with self.assertRaises(module.Fail) as caught:
                module._target(json.dumps(bad).encode())
            self.assertEqual(caught.exception.code, "bad_target")
            self.assertEqual(caught.exception.exit, 2)

    def test_deploy_forwards_original_target_bytes(self):
        """省略默认字段时 deploy 只共享校验，子采集器仍收到原始 stdin bytes。"""
        self.lh(0)
        target = copy.deepcopy(TARGET)
        target["ssh"].pop("user")
        target["ssh"].pop("port")
        proc = self.run_tool(("one",), target=target)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(self.repo, "tools", ".collect.stdin"), "rb") as handle:
            self.assertEqual(handle.read(), json.dumps(target).encode())

    def test_deploy_rejects_bad_target_before_child(self):
        self.lh(0)
        target = copy.deepcopy(TARGET)
        target["ssh"]["user"] = "bad user"
        proc = self.run_tool(("one",), target=target)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(json.loads(proc.stderr)["error"], "bad_target")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "tools", ".collect.stdin")))
        self.assertEqual(self.argv_log(), [])

    def test_pre_auth_failure_blocks_all_writes(self):
        with open(os.path.join(self.repo, "tools", ".fail-pre"), "w",
                  encoding="utf-8") as handle:
            handle.write("ssh_auth_failed\n")
        self.lh(0)
        proc = self.run_tool(("one",))
        self.assertEqual(proc.returncode, 3, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["objects"][0]["phase"], "pre")
        self.assertEqual(summary["objects"][0]["code"], "ssh_auth_failed")
        self.assertEqual(summary["objects"][0]["changed"], False)
        self.assertEqual(json.loads(proc.stderr)["error"], "ssh_auth_failed")
        self.assertEqual(self.argv_log(), [])

    def test_post_auth_failure_reports_unknown_write_without_retry(self):
        with open(os.path.join(self.repo, "tools", ".fail-post"), "w",
                  encoding="utf-8") as handle:
            handle.write("ssh_auth_failed\n")
        self.lh(0)
        proc = self.run_tool(("one",))
        self.assertEqual(proc.returncode, 3, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["objects"][0]["phase"], "post")
        self.assertEqual(summary["objects"][0]["code"], "ssh_auth_failed")
        self.assertEqual(summary["objects"][0]["changed"], "unknown")
        self.assertEqual(self.argv_log(), [
            "skill", "install", "https://github.com/o/r/tree/main/skills/one"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "post-0-fix")))


    def test_collect_hard_deadline_cleanup_and_recovery(self):
        """R2 唯一新增回归：真实 deploy→collect 子进程的超时清理与恢复正控。

        仅把 KeyRoot 的固定父目录改到本用例安全排他根（生产默认不变）；超时由子内 ssh 等待触发，
        外层过 W 先 SIGTERM：断言可处理终止（timeout 而非 cli_error）、登记根/id 已删、无残留；
        同用例改用正常 SSH 结果再跑一次，断言成功且同样无残留。
        """
        root = os.path.join(self.tmp, "keyroot")
        os.makedirs(root, mode=0o700, exist_ok=True)
        with open(TOOL_REAL_COLLECT, encoding="utf-8") as handle:
            code = handle.read()
        needle = 'ROOT_PARENT = "/tmp"'
        self.assertIn(needle, code, "生产默认钥根父目录契约缺失")
        self.write("tools/lh-collect.py", code.replace(needle, 'ROOT_PARENT = "%s"' % root))
        shutil.copyfile(TOOL_REAL_BODY, os.path.join(self.repo, "tools", "body_contract.py"))
        fake = os.path.join(self.bin, "ssh")
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write(FAKE_SSH_SLOW)
        os.chmod(fake, 0o755)
        with open(os.path.join(self.bin, "row"), "w", encoding="utf-8") as handle:
            handle.write(agent_row() + "\n")
        docker = os.path.join(self.bin, "docker")
        with open(docker, "w", encoding="utf-8") as handle:
            handle.write(FAKE_DOCKER)
        os.chmod(docker, 0o755)
        env = dict(self.env, SSH_PRIVATE_KEY_B64=base64.b64encode(
            b"synthetic-test-sentinel").decode())
        self.lh(0)
        proc = self.run_tool(("prompt/X.md",), env=env, timeout="3")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(json.loads(proc.stderr)["error"], "timeout")
        self.assertEqual(summary["objects"][0]["code"], "timeout")
        self.assertEqual(summary["cleanupResiduals"], [])
        self.assertEqual(os.listdir(root), [])
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write(FAKE_SSH_OK)
        os.chmod(fake, 0o755)
        self.out = os.path.join(self.tmp, "out-recovery")   # 每次运行要新建 out 根
        proc = self.run_tool(("prompt/X.md",), env=env, timeout="30")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["cleanupResiduals"], [])
        self.assertEqual(os.listdir(root), [])


    def test_collect_without_cleanup_ack_fails_before_write(self):
        """R2-A 直接回归：真实父子接缝，子 rc0 但不发任何 cleanup 事件 → cleanup_failed 且零写。"""
        self.write("tools/lh-collect.py", "import sys\nsys.exit(0)\n")
        self.lh(0)
        proc = self.run_tool(("one",))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(json.loads(proc.stderr)["error"], "cleanup_failed")
        self.assertEqual(summary["objects"][0]["code"], "cleanup_failed")
        self.assertEqual(summary["cleanupResiduals"], [])   # 无根记录：路径未知，不代表已清
        self.assertEqual(self.argv_log(), [])
        self.assertFalse(os.path.isdir(os.path.join(self.out, "pre-0")))

    def test_collect_failure_preserves_only_known_codes(self):
        """真实子进程通知保留 rc2/3 类别；旧子进程和未知内容沿用通用码，不泄漏输出。"""
        secret = "SYNTH_PRIVATE_CHILD_OUTPUT"
        for index, (code, rc, expected) in enumerate((
                ("resource_read_error", 2, "resource_read_error"),
                ("source_unverified", 3, "source_unverified"),
                ("ssh_auth_failed", 3, "ssh_auth_failed"),
                (None, 2, "cli_error"),
                (secret, 2, "cli_error"))):
            with self.subTest(code=code):
                self.out = os.path.join(self.tmp, "out-failure-%d" % index)
                program = (
                    "import json,os,sys\n"
                    "fd=int(sys.argv[sys.argv.index('--_cleanup-fd')+1])\n"
                    "os.write(fd,b'{\"event\":\"cleanup\",\"residuals\":[]}\\n')\n")
                if code is not None:
                    program += "os.write(fd,%r)\n" % (json.dumps(
                        {"event": "result", "error": code}) + "\n").encode()
                program += ("sys.stdout.write(%r * 100000)\n"
                            "sys.stderr.write(%r * 100000)\n"
                            "sys.exit(%d)\n") % (secret, secret, rc)
                self.write("tools/lh-collect.py", program)
                self.lh(0)
                proc = self.run_tool()
                self.assertEqual(proc.returncode, rc, proc.stderr)
                self.assertEqual(json.loads(proc.stdout)["objects"][0]["code"], expected)
                self.assertEqual(json.loads(proc.stderr)["error"], expected)
                self.assertNotIn(secret.encode(), proc.stdout + proc.stderr)
                self.assertEqual(self.argv_log(), [])

    def test_real_collect_reports_missing_named_variable(self):
        """真实 collect 的早期失败也带清理确认和固定错误码，不依赖假通知互证。"""
        shutil.copyfile(TOOL_REAL_COLLECT, os.path.join(self.repo, "tools/lh-collect.py"))
        self.lh(0)
        proc = self.run_tool()
        self.assertEqual(proc.returncode, 3, proc.stderr)
        expected = "missing_variable:SSH_PRIVATE_KEY_B64"
        self.assertEqual(json.loads(proc.stdout)["objects"][0]["code"], expected)
        self.assertEqual(json.loads(proc.stderr)["error"], expected)
        self.assertEqual(self.argv_log(), [])

    def test_real_collect_auth_failure_propagates_zero_write(self):
        """真实 collect 的 ssh 认证失败经固定码通道传到 deploy：pre 失败零 CLI。"""
        shutil.copyfile(TOOL_REAL_COLLECT, os.path.join(self.repo, "tools", "lh-collect.py"))
        fake = os.path.join(self.bin, "ssh")
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\ncat > /dev/null\n"
                         "printf 'u@h.example: Permission denied (publickey).\\n' >&2\n"
                         "exit 255\n")
        os.chmod(fake, 0o755)
        env = dict(self.env, SSH_PRIVATE_KEY_B64=base64.b64encode(
            b"synthetic-test-sentinel").decode())
        self.lh(0)
        proc = self.run_tool(("one",), env=env)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["objects"][0]["phase"], "pre")
        self.assertEqual(summary["objects"][0]["code"], "ssh_auth_failed")
        self.assertEqual(summary["objects"][0]["changed"], False)
        self.assertEqual(json.loads(proc.stderr)["error"], "ssh_auth_failed")
        self.assertEqual(self.argv_log(), [])

class DependencySeamTest(unittest.TestCase):
    """只注入「yaml 导入缺失」：正文契约缺依赖必须归执行错误 rc2，不得当成 source_unverified 或缺证。"""

    def test_missing_pyyaml_is_execution_error(self):
        import importlib.util
        from unittest import mock
        spec = importlib.util.spec_from_file_location("lh_deploy_dep", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.dict(sys.modules, {"yaml": None}):
            with self.assertRaises(module.Fail) as caught:
                module._load_body()
        self.assertEqual(("dependency_missing", 2), (caught.exception.code, caught.exception.exit))


if __name__ == "__main__":
    unittest.main()

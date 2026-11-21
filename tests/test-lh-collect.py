#!/usr/bin/env python3
"""lh-collect 离线合成用例：不联网、无秘密、无真实实例。

覆盖：白名单投影、资源实际完整键（非登记自证）、只读交集调用、null/空串区分、尾 LF 保留、
原响应/失败调用与观察关联、Agent 未核准前提真实 rc3、缺失源行 rc3 不写证据、
SSH 目标默认/独立覆盖及 255 认证失败与其它失败分类。
"""
import base64
import copy
import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "tools", "lh-collect.py")
SHARED = os.path.join(os.path.dirname(HERE), "tools", "ssh_target.py")
PY = sys.executable or "python3"

FAKE_SSH = """#!/bin/sh
here=$(dirname "$0")
printf '%s\n' "$@" > "$here/argv"
cat > "$here/sql"
cmd=
for a in "$@"; do cmd=$a; done
exec /bin/sh -c "$cmd"
"""

FAKE_DOCKER = """#!/bin/sh
here=$(dirname "$0")
printf '%s\n' "$@" > "$here/docker.argv"
cat "$here/row"
"""

FAKE_AUTH = """#!/usr/bin/env python3
import hashlib, json, os, sys
args = sys.argv[1:]
path = args[args.index("--path") + 1]
if path == "references/fail.md":
    sys.stdout.write("")
    sys.stderr.write(json.dumps({"ok": False, "error": "transport_error"}) + "\\n")
    sys.exit(2)
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
blob = open(os.path.join(here, "skills", "luno-ops", path), "rb").read()
doc = {"ok": True, "action": "skill-resource", "resource": {
    "content": blob.decode(), "encoding": "utf8", "fileHash": hashlib.sha256(blob).hexdigest(),
    "fileType": "text/plain", "path": path, "size": len(blob)}}
sys.stdout.write(json.dumps(doc) + "\\n")
"""

TARGET = {"ssh": {"host": "h.example", "port": 22, "user": "u",
                  "knownHostsFile": "/etc/ssh/ssh_known_hosts"},
          "postgres": {"container": "db", "database": "lob", "port": 5432, "user": "lob"}}


def row(skill_id="skl_1", content="body\n", name="luno-ops",
        description="d", identifier=None, resources=("references/a.md",)):
    """按真实 SQL 契约（agent_skills）造行：只有 *_b64 字段是 base64。"""
    def b64(value):
        # 真实 PostgreSQL encode(...,'base64') 每 76 字节插换行：夹具按同一编码契约造行。
        return base64.encodebytes(value.encode()).decode()
    return json.dumps({"id": skill_id, "name": name, "identifier": identifier,
                       "description_b64": b64(description), "content_b64": b64(content),
                       "resource_keys": list(resources)}, separators=(",", ":"))


def agent_row(agent_id="agt_1", role="hello\n", user_id="usr_1", workspace_id=None):
    """按真实 agents 契约造行：只 system_role 走 base64，身份列原文，workspace_id 可 null。"""
    def b64(value):
        return None if value is None else base64.encodebytes(value.encode()).decode()
    return json.dumps({"id": agent_id, "user_id": user_id, "workspace_id": workspace_id,
                       "system_role_b64": b64(role)}, separators=(",", ":"))


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lh-collect-test-")
        # 合成钥根只放本用例独占安全根；生产脚本默认 /tmp 不变。
        with open(TOOL, encoding="utf-8") as handle:
            code = handle.read()
        needle = 'ROOT_PARENT = "/tmp"'
        self.assertEqual(code.count(needle), 1)
        self.tool = os.path.join(self.tmp, "lh-collect.py")
        with open(self.tool, "w", encoding="utf-8") as handle:
            handle.write(code.replace(needle, 'ROOT_PARENT = ' + repr(self.tmp)))
        shutil.copyfile(SHARED, os.path.join(self.tmp, "ssh_target.py"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "tools"))
        os.makedirs(os.path.join(self.repo, "skills", "luno-ops", "references"))
        self.env = {"PATH": os.path.join(self.tmp, "bin") + ":/usr/bin:/bin",
                    "TMPDIR": os.path.join(self.tmp, "tmp"), "LC_ALL": "C.UTF-8",
                    "HOME": os.path.join(self.tmp, "home")}
        for key in ("bin", "tmp", "home"):
            os.makedirs(os.path.join(self.tmp, key), exist_ok=True)
        self._write("tools/auth-call.py", FAKE_AUTH, 0o755)
        with open(os.path.join(self.tmp, "bin", "docker"), "w", encoding="utf-8") as handle:
            handle.write(FAKE_DOCKER)
        os.chmod(os.path.join(self.tmp, "bin", "docker"), 0o755)
        self._write("skills/luno-ops/SKILL.md", "---\nname: luno-ops\ndescription: d\n---\nbody\n")
        self._write("skills/luno-ops/references/a.md", "a")
        registry = {"schemaVersion": 1, "objects": [{
            "id": "luno-ops", "type": "skill", "source": "skills/luno-ops/SKILL.md",
            "resources": ["skills/luno-ops/references/a.md"],
            "installSource": "https://github.com/LucaLin233/Agent-Sync/tree/main/skills/luno-ops",
            "ends": {"lobehub": {"present": True, "kind": "skill", "id": "skl_1"}}}]}
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

    def fake_ssh_failure(self, code, stderr):
        ssh = os.path.join(self.tmp, "bin", "ssh")
        with open(ssh, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\nhere=$(dirname \"$0\")\ncat > /dev/null\n"
                         "cat \"$here/ssh.stderr\" >&2\nexit %d\n" % code)
        os.chmod(ssh, 0o755)
        with open(os.path.join(self.tmp, "bin", "ssh.stderr"), "w",
                  encoding="utf-8") as handle:
            handle.write(stderr)

    def run_tool(self, extra_env=None, objects=("luno-ops",), target=TARGET):
        argv = [PY, "-I", "-B", self.tool, "--repo", self.repo, "--git-version", self.version,
                "--out-dir", self.out, "--instance-ref", "inst-1",
                "--source-basis", "basis-ref", "--source-version", "2.3.3+testbuild",
                "--total-timeout", "30"]
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
        self.fake_ssh(row(name=None, description="", content="正文" * 30 + "\n",
                          resources=("references/a.md", "references/extra.md")))
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
        self.assertEqual(obj["projection"]["content"], "正文" * 30 + "\n")  # 长多字节正文与尾 LF 原样还原
        self.assertEqual(obj["projection"]["identifier"], None)
        with open(os.path.join(self.tmp, "bin", "sql"), encoding="utf-8") as handle:
            sql = handle.read()
        self.assertIn("FROM agent_skills", sql)      # 真实表（probe5.sh 已核）
        for key in ("name", "identifier", "description_b64", "content_b64", "resource_keys"):
            self.assertIn(key, sql)
        self.assertNotIn("FROM skills", sql)
        with open(os.path.join(self.tmp, "bin", "argv"), encoding="utf-8") as handle:
            argv = handle.read().splitlines()
        self.assertEqual(argv.count("--"), 1)         # host 之后不再多一个 "--"
        self.assertEqual(argv[argv.index("--") + 1], "u@h.example")
        # OpenSSH 把 host 之后全部参数以空格拼成一个远端命令串：只允许一个命令串 token。
        self.assertEqual(len(argv) - argv.index("--") - 1, 2)
        self.assertEqual(shlex.split(argv[argv.index("--") + 2])[0], "docker")
        with open(os.path.join(self.tmp, "bin", "docker.argv"), encoding="utf-8") as handle:
            dock = handle.read().splitlines()
        self.assertEqual(dock[:3], ["exec", "-i", "db"])   # 经 /bin/sh 后 docker 实得 argv
        self.assertIn("PGPASSFILE=/dev/null", dock)
        self.assertIn("PGOPTIONS=-c default_transaction_read_only=on", dock)  # 单参数，未被拆开
        self.assertIn("-w", dock)
        self.assertIn("-X", dock)
        self.assertEqual(dock[dock.index("env") + 1], "-i")
        with open(os.path.join(self.out, "projection-source.json"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("h.example", source)
        self.assertNotIn("test-token-value", proc.stdout.decode())

    def test_failed_call_kept_with_association(self):
        self.fake_ssh(row(skill_id="skill-example",
                          resources=("references/a.md", "references/fail.md")))
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
        proc = self.run_tool(self.creds(), objects=("example-skill",))
        self.assertEqual(proc.returncode, 2, proc.stderr)      # 读取错误是 rc2，不是成功
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["status"], "error")
        self.assertEqual(summary["objects"][0]["status"], "failed")
        self.assertEqual(summary["objects"][0]["code"], "resource_read_error")
        self.assertIn("resource_read_error", summary["errors"])
        self.assertEqual(json.loads(proc.stderr)["error"], "resource_read_error")
        with open(os.path.join(self.out, "skill-evidence.json"), encoding="utf-8") as handle:
            obj = json.load(handle)["objects"][0]
        calls = {c["request"]["path"]: c for c in obj["calls"]}
        self.assertEqual(calls["references/fail.md"]["exitCode"], 2)
        self.assertEqual(calls["references/fail.md"]["stdout"], "")
        self.assertEqual(json.loads(calls["references/fail.md"]["stderr"])["error"],
                         "transport_error")
        self.assertEqual(calls["references/fail.md"]["observationId"],
                         obj["observationId"])

    def test_real_verify_consumes_collect_evidence(self):
        """真实 collect 输出交现役 lh-verify 消费：禁止双方恒 0 互证。"""
        tools = os.path.join(os.path.dirname(HERE), "tools")
        shutil.copyfile(os.path.join(tools, "body_contract.py"),
                        os.path.join(self.repo, "tools", "body_contract.py"))
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@e",
                        "commit", "-qm", "contract"], check=True)
        self.version = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                                      capture_output=True, text=True, check=True).stdout.strip()
        self.fake_ssh(row(identifier="lucalin233-agent-sync-luno-ops"))
        proc = self.run_tool(self.creds())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        real_verify = os.path.join(os.path.dirname(HERE), "tools", "lh-verify.py")
        argv = [PY, "-I", "-B", real_verify, "--repo", self.repo, "--git-version", self.version,
                "--object", "luno-ops", "--evidence",
                os.path.join(self.out, "skill-evidence.json")]
        out = subprocess.run(argv, capture_output=True, env={"PATH": "/usr/bin:/bin",
                                                            "HOME": self.tmp, "LC_ALL": "C.UTF-8"},
                             timeout=120)
        self.assertEqual(out.returncode, 0, (out.stdout, out.stderr))

    def test_agent_projection_and_evidence(self):
        """Agent 固定投影：agents 表 + is_deleted IS NOT TRUE，只取 systemRole 与身份列，独立证据文件。"""
        self._write("tools/sync-targets.json", json.dumps({"schemaVersion": 1, "objects": [{
            "id": "prompt/X.md", "type": "prompt", "source": "prompt/X.md", "resources": [],
            "ends": {"lobehub": {"present": True, "kind": "agent", "id": "agt_1",
                                 "field": "systemRole"}}}]}))
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@e",
                        "commit", "-qm", "agent"], check=True)
        self.version = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                                      capture_output=True, text=True, check=True).stdout.strip()
        self.fake_ssh(agent_row())
        proc = self.run_tool(self.creds(), objects=("prompt/X.md",))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(self.out, "agent-evidence.json"), encoding="utf-8") as handle:
            doc = json.load(handle)
        self.assertEqual(sorted(doc), ["objects", "observation", "schemaVersion"])
        obj = doc["objects"][0]
        self.assertEqual(sorted(obj), ["field", "id", "instanceRef", "object",
                                       "observationId", "value"])
        self.assertEqual(obj["field"], "systemRole")
        self.assertEqual(obj["id"], "agt_1")
        self.assertEqual(obj["value"], "hello\n")          # 正文原样，不加尾 LF
        self.assertEqual(obj["observationId"], doc["observation"]["id"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "skill-evidence.json")))
        with open(os.path.join(self.tmp, "bin", "sql"), encoding="utf-8") as handle:
            sql = handle.read()
        self.assertIn("FROM agents", sql)
        self.assertIn("is_deleted IS NOT TRUE", sql)        # 软删除列可空，必须 IS NOT TRUE
        for column in ("id", "user_id", "workspace_id", "system_role"):
            self.assertIn(column, sql)

    def test_missing_row_is_rc3_without_evidence(self):
        self.fake_ssh("MISSING")
        proc = self.run_tool(self.creds())
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(os.path.exists(os.path.join(self.out, "skill-evidence.json")))

    def test_ssh_target_defaults_and_overrides(self):
        """omit 字段逐字段补 root:9399；显式 user/port 可独立覆盖并原样用于 ssh。"""
        self.fake_ssh(row())
        cases = (
            ((), "deploy", 2222),
            (("user",), "root", 2222),
            (("port",), "deploy", 9399),
            (("user", "port"), "root", 9399),
        )
        for index, (omitted, user, port) in enumerate(cases):
            with self.subTest(omitted=omitted):
                target = copy.deepcopy(TARGET)
                target["ssh"]["user"] = "deploy"
                target["ssh"]["port"] = 2222
                for key in omitted:
                    target["ssh"].pop(key)
                self.out = os.path.join(self.tmp, "out-defaults-%d" % index)
                proc = self.run_tool(self.creds(), target=target)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                with open(os.path.join(self.tmp, "bin", "argv"), encoding="utf-8") as handle:
                    argv = handle.read().splitlines()
                self.assertEqual(argv[argv.index("--") + 1], user + "@h.example")
                self.assertEqual(argv[argv.index("-p") + 1], str(port))

    def test_ssh_target_rejects_invalid_explicit(self):
        """缺失必填项和显式非法 user/port 均 bad_target/rc2，不进入 ssh。"""
        self.fake_ssh(row())
        cases = []
        for missing in ("host", "knownHostsFile"):
            target = copy.deepcopy(TARGET)
            target["ssh"].pop(missing)
            cases.append(target)
        for value in ("", "bad user", None, "root\n"):
            target = copy.deepcopy(TARGET)
            target["ssh"]["user"] = value
            cases.append(target)
        for value in ("22", 0, 65536, True, 22.0):
            target = copy.deepcopy(TARGET)
            target["ssh"]["port"] = value
            cases.append(target)
        target = copy.deepcopy(TARGET)
        target["postgres"].pop("database")
        cases.append(target)
        target = copy.deepcopy(TARGET)
        target["ssh"]["extra"] = "x"
        cases.append(target)
        for index, target in enumerate(cases):
            with self.subTest(index=index):
                self.out = os.path.join(self.tmp, "out-bad-%d" % index)
                proc = self.run_tool(self.creds(), target=target)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertEqual(json.loads(proc.stderr)["error"], "bad_target")
                self.assertFalse(os.path.exists(self.out))

    def test_ssh_255_auth_failure_is_fixed_and_redacted(self):
        """仅本次目标最后的 OpenSSH 认证拒绝行映射 ssh_auth_failed/rc3 且脱敏。"""
        upper = copy.deepcopy(TARGET)
        upper["ssh"]["host"] = "H.Example"
        cases = (
            (TARGET, "u@h.example: Permission denied (publickey).\n"),
            (TARGET, "u@h.example: Permission denied ().\n"),
            (upper, "u@h.example: Permission denied (publickey,password).\n"),
        )
        for index, (target, stderr) in enumerate(cases):
            with self.subTest(index=index):
                self.fake_ssh_failure(255, stderr)
                self.out = os.path.join(self.tmp, "out-auth-%d" % index)
                proc = self.run_tool(self.creds(), target=target)
                self.assertEqual(proc.returncode, 3, proc.stderr)
                self.assertEqual(json.loads(proc.stderr)["error"], "ssh_auth_failed")
                out = proc.stdout + proc.stderr
                self.assertIn(b"ssh_auth_failed", out)
                self.assertNotIn(b"Permission denied", out)
                self.assertNotIn(b"h.example", out)

    def test_ssh_255_non_auth_stays_source_unverified(self):
        """其它诊断、非本次目标或非终止行不得冒充认证失败。"""
        for index, text in enumerate((
                "ssh: connect to host h.example port 22: Connection refused\n",
                "",
                "psql: Permission denied (container).\nConnection closed by remote host.\n",
                "root@h.example: Permission denied (publickey).\n",
                "u@other.example: Permission denied (publickey).\n",
                "u@h.example: Permission denied (publickey).\n"
                "Connection closed by remote host.\n")):
            with self.subTest(index=index):
                self.fake_ssh_failure(255, text)
                self.out = os.path.join(self.tmp, "out-255-%d" % index)
                proc = self.run_tool(self.creds())
                self.assertEqual(proc.returncode, 3, proc.stderr)
                self.assertEqual(json.loads(proc.stderr)["error"], "source_unverified")
                self.assertNotIn(b"h.example", proc.stdout + proc.stderr)

    def test_source_version_required(self):
        """调用方人工核实的来源版本必填；缺参在看凭据前 rc2。"""
        self.fake_ssh(row())
        argv = [PY, "-I", "-B", self.tool, "--repo", self.repo, "--git-version", self.version,
                "--out-dir", self.out, "--instance-ref", "inst-1",
                "--source-basis", "basis-ref", "--object", "luno-ops"]
        proc = subprocess.run(argv, input=json.dumps(TARGET).encode(), env=dict(self.env),
                              capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stderr)["error"], "bad_args")
        argv += ["--source-version", "test-build", "--total-timeout", "2"]
        proc = subprocess.run(argv, input=json.dumps(TARGET).encode(), env=dict(self.env),
                              capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stderr)["error"], "timeout")
        self.assertFalse(os.path.exists(self.out))

    def test_missing_variable_named(self):
        self.fake_ssh(row())
        creds = self.creds()
        del creds["LOBEHUB_CLI_API_KEY"]
        proc = self.run_tool(creds)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(json.loads(proc.stderr)["error"],
                         "missing_variable:LOBEHUB_CLI_API_KEY")


    def test_unreaped_child_stays_visible_to_cleanup(self):
        """未回收的子进程须留在 _ACTIVE，清理汇总才能观察失败；两调用者同一接缝。"""
        spec = importlib.util.spec_from_file_location("lh_collect_reap", self.tool)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        class Stuck:
            """假子进程：communicate/wait 立即超时、poll 仍在跑；不制造真实不可中断进程。"""
            returncode = None

            def __init__(self):
                self.entered = False

            def communicate(self, *args, **kwargs):
                self.entered = True
                raise subprocess.TimeoutExpired("child", 0.1)

            def terminate(self):
                pass

            def kill(self):
                pass

            def poll(self):
                return None

            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired("child", timeout)

        def seam(call, deadline):
            return (lambda: call(mod.Deadline(deadline)), deadline != 0)

        run = (lambda d: mod._ssh_run(TARGET["ssh"], TARGET["postgres"], "/k", "", [], d),
               lambda d: mod._auth_call(self.repo, "skl_1", "references/a.md", d))
        # 现有两条提前出口，两调用者各一：communicate 超时后 _reap 未回收；期限先抛未进 communicate。
        for call, entered in [seam(f, d) for f in run for d in (time.monotonic() + 3, 0)]:
            proc = Stuck()
            mod._ACTIVE.clear()
            mod._spawn = lambda argv, _proc=proc, **kwargs: (mod._ACTIVE.add(_proc), _proc)[1]
            with self.assertRaises(mod.Fail) as caught:
                call()
            self.assertEqual(caught.exception.code, "timeout")
            self.assertEqual(proc.entered, entered)                    # 期限先抛时未进入 communicate
            self.assertIn(proc, mod._ACTIVE)                          # 修前被 finally 无条件丢弃
            self.assertFalse(mod._stop_active(time.monotonic() + 3))  # 清理汇总可观察未回收


    def test_per_object_deadline_not_overridden_by_next_object(self):
        """首对象期限内返回、随后处理越过其 W 时，不得因下一对象换期限而 rc0/collected。"""
        self.fake_ssh(row())
        self._write("tools/sync-targets.json", json.dumps({"schemaVersion": 1, "objects": [
            {"id": "luno-ops", "type": "skill", "source": "skills/luno-ops/SKILL.md",
             "resources": ["skills/luno-ops/references/a.md"],
             "ends": {"lobehub": {"present": True, "kind": "skill", "id": "skl_1"}}},
            {"id": "prompt/A.md", "type": "prompt", "source": "prompt/A.md", "resources": [],
             "ends": {"lobehub": {"present": True, "kind": "agent", "id": "agt_2",
                                  "field": "systemRole"}}},
            {"id": "prompt/B.md", "type": "prompt", "source": "prompt/B.md", "resources": [],
             "ends": {"lobehub": {"present": True, "kind": "agent", "id": "agt_3",
                                  "field": "systemRole"}}}]}))
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@e",
                        "commit", "-qm", "mixed"], check=True)
        version = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        os.environ["SSH_PRIVATE_KEY_B64"] = base64.b64encode(b"test-only").decode()
        os.environ["LOBEHUB_SERVER"] = "https://example.invalid"
        os.environ["LOBEHUB_CLI_API_KEY"] = "test-token-value"
        resource = json.dumps({"ok": True, "action": "skill-resource", "resource": {
            "content": "a", "encoding": "utf8", "fileHash": "", "fileType": "text/plain",
            "path": "references/a.md", "size": 1}}).encode()
        try:
            runs = 0
            for first, second in (("luno-ops", "prompt/A.md"), ("prompt/A.md", "prompt/B.md")):
                for objects in ((first,), (first, second)):
                    runs += 1
                    spec = importlib.util.spec_from_file_location("lh_w%d" % runs, self.tool)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    clock = [0.0]
                    ids = {}

                    class Clock:
                        monotonic = staticmethod(lambda: clock[0])

                    class Done:
                        returncode = 0

                        def poll(self):
                            return 0

                        def communicate(self, data=None, timeout=None):
                            if data is None:
                                return resource, b""
                            if b"FROM agents" in data:
                                return (agent_row(agent_id=ids["id"]) + "\n").encode(), b""
                            return (row() + "\n").encode(), b""

                    def spawn(argv, _mod=mod, **kwargs):
                        text = " ".join(argv)
                        if "obj_id=agt" in text:
                            ids["id"] = "agt" + text.split("obj_id=agt")[1].split()[0]
                        proc = Done()
                        _mod._ACTIVE.add(proc)
                        return proc

                    def after(real):
                        def wrapper(*args, **kwargs):
                            value = real(*args, **kwargs)
                            clock[0] = 1.1          # T=3：首对象 W=1.0，处理/解码越 W
                            return value
                        return wrapper

                    mod.time = Clock
                    mod._install_signals = lambda: None
                    mod._spawn = spawn
                    if first == "luno-ops":
                        mod._auth_call = after(mod._auth_call)     # 技能：资源循环结束、组装前
                    else:
                        mod._agent_projection = after(mod._agent_projection)  # Agent 返回后
                    argv = ["--repo", self.repo, "--git-version", version,
                            "--out-dir", os.path.join(self.tmp, "out-w%d" % runs),
                            "--instance-ref", "synthetic", "--source-basis", "synthetic",
                            "--source-version", "testbuild", "--total-timeout", "3"]
                    for item in objects:
                        argv += ["--object", item]
                    keep = sys.stdin, sys.stdout, sys.stderr
                    sys.stdin = types.SimpleNamespace(buffer=io.BytesIO(json.dumps(TARGET).encode()))
                    buf, errb = io.StringIO(), io.StringIO()
                    sys.stdout, sys.stderr = buf, errb
                    try:
                        rc = mod.main(argv)
                    finally:
                        sys.stdin, sys.stdout, sys.stderr = keep
                    doc = json.loads(buf.getvalue())
                    # 单对象对照与两对象同判：首对象越 W 即 timeout/rc2，不能被下一对象期限覆盖。
                    self.assertEqual(rc, 2, (objects, doc, errb.getvalue()))
                    self.assertEqual(doc["status"], "error")
                    self.assertIn("timeout", doc["errors"])
        finally:
            for name in ("SSH_PRIVATE_KEY_B64", "LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY"):
                os.environ.pop(name, None)


if __name__ == "__main__":
    unittest.main()

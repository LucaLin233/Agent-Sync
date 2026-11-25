"""Paseo 观测台窄入口：离线、合成夹具；opt-in case，不进 full。

覆盖：子进程环境不继承秘密、dry-run 零写、写后回读成功与失败、loopback 与
CLI 版本门禁、同状态幂等。
"""
import importlib.util
import json
import os
import pathlib
import shutil
import tempfile
import unittest

TOOL = pathlib.Path(__file__).resolve().parents[1] / "tools" / "paseo-observatory.py"
spec = importlib.util.spec_from_file_location("paseo_observatory", TOOL)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

FAKE_SDK = r"""
const fs = require('node:fs');
const path = require('node:path');
const HERE = __dirname;
const readScenario = () => JSON.parse(fs.readFileSync(path.join(HERE, 'scenario.json'), 'utf8'));
const writeScenario = (s) => fs.writeFileSync(path.join(HERE, 'scenario.json'), JSON.stringify(s));
fs.writeFileSync(path.join(HERE, 'env-keys.json'), JSON.stringify(Object.keys(process.env).sort()));
fs.writeFileSync(path.join(HERE, 'argv.json'), JSON.stringify(process.argv));
exports.createHostClient = (target, config) => {
  fs.writeFileSync(path.join(HERE, 'target.json'), JSON.stringify({target, hasPassword: !!config.password}));
  return {
    async connect() {
      const s = readScenario();
      if (s.connectError) {
        const e = new Error('synthetic');
        e.name = 'DaemonAuthenticationError';
        e.reason = s.connectError;
        throw e;
      }
    },
    getLastServerInfoMessage() {
      const s = readScenario();
      return {status: 'server_info', serverId: s.serverId, version: '0.17.4'};
    },
    async invokePluginRpc(plugin, method, input) {
      const s = readScenario();
      s.calls = s.calls || [];
      s.calls.push({plugin, method, input});
      const isWrite = method === 'observatory.insights.feedback'
        || method === 'observatory.insights.action-feedback';
      if (isWrite && s.writeOutcome === 'apply') {
        const isFinding = !!input.findingId;
        const key = isFinding ? 'findingFeedback' : 'feedback';
        const id = input.findingId || input.actionId;
        const method = isFinding ? 'observatory.insights.report'
                                 : 'observatory.insights.suggestions';
        const job = ((s.response || {})[method] || {}).job;
        if (!job) { throw new Error('fixture missing job'); }
        job[key] = job[key] || {};
        job[key][id] = {status: input.status, updatedAt: '2026-11-26T00:00:00Z'};
      }
      if (isWrite && s.writeJobId) {
        const method = input.findingId ? 'observatory.insights.report'
                                       : 'observatory.insights.suggestions';
        const job = ((s.response || {})[method] || {}).job;
        if (job) job.id = s.writeJobId;
      }
      writeScenario(s);
      if (s.rpcErrors && s.rpcErrors[method]) { throw new Error('synthetic rpc failure'); }
      if (isWrite && s.writeOutcome === 'throw') { throw new Error('synthetic write failure'); }
      if (isWrite && s.writeOutcome === 'apply') {
        // 反馈接口按契约返回完整 job；readback 仍走 report/suggestions。
        const isFinding = !!input.findingId;
        const method = isFinding ? 'observatory.insights.report'
                                 : 'observatory.insights.suggestions';
        return JSON.parse(JSON.stringify(((s.response || {})[method] || {}).job));
      }
      if (isWrite) { return {}; }
      return s.response[method];
    },
    async close() {},
  };
};
"""


def make_fake_cli(root, scenario):
    cli = pathlib.Path(root) / "cli"
    sdk = cli / "node_modules" / "@getpaseo" / "client" / "dist" / "node"
    sdk.mkdir(parents=True)
    (cli / "package.json").write_text(
        json.dumps({"name": "@getpaseo/cli", "version": M.PASEO_VERSION}), encoding="utf-8")
    sdk_pkg = cli / "node_modules" / "@getpaseo" / "client"
    sdk_pkg.mkdir(parents=True, exist_ok=True)
    (sdk_pkg / "package.json").write_text(
        json.dumps({"name": "@getpaseo/client", "version": M.SDK_VERSION}), encoding="utf-8")
    (sdk / "index.js").write_text(FAKE_SDK, encoding="utf-8")
    write_scenario(sdk, scenario)
    return str(cli), sdk


def write_scenario(sdk, scenario):
    (pathlib.Path(sdk) / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")


def base_scenario(**over):
    scenario = {
        "serverId": "srv-synthetic",
        "calls": [],
        "response": {
            "observatory.insights.list": {"jobs": [
                {"id": "job-1", "agentId": "agent-1", "createdAt": "2026-11-26T00:00:00Z",
                 "findings": 6, "resolvedFindings": 0, "reportAvailable": True,
                 "summary": None, "health": "watch"}]},
            "observatory.insights.report": {"job": {
                "id": "job-1",
                "report": {"findings": [{"id": "f-1", "severity": "high"},
                                        {"id": "f-2", "severity": "low"},
                                        {"id": "f-3", "severity": "medium"},
                                        {"id": "f-4", "severity": "medium"},
                                        {"id": "f-5", "severity": "low"},
                                        {"id": "f-6", "severity": "low"}]},
                "findingFeedback": {"f-2": {"status": "false_positive"}}}},
            "observatory.insights.suggestions": {"job": {
                "id": "job-9", "report": {"actions": [{"id": "a-1"}]},
                "feedback": {}}},
        },
    }
    scenario.update(over)
    return scenario


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="obs-test-")
        self.cli, self.sdk = make_fake_cli(self.tmp, base_scenario())
        self.env_backup = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env_backup)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, *argv):
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = M.main(["--paseo-cli", self.cli, "--target", "127.0.0.1:6767",
                         "--server-id", "srv-synthetic", *argv])
        return rc, out.getvalue()

    def scenario(self):
        return json.loads((pathlib.Path(self.sdk) / "scenario.json").read_text(encoding="utf-8"))

    def calls(self):
        return self.scenario().get("calls", [])


class ChildEnvTest(Base):
    def test_secret_not_inherited(self):
        os.environ["SECRET_MARKER"] = "do-not-leak"
        os.environ["GH_TOKEN"] = "synthetic-gh"
        os.environ["PASEO_PASSWORD"] = "synthetic-pw"
        rc, out = self.run_tool("report", "list")
        self.assertEqual(rc, M.RC_OK, out)
        keys = json.loads((pathlib.Path(self.sdk) / "env-keys.json").read_text(encoding="utf-8"))
        self.assertNotIn("SECRET_MARKER", keys)
        self.assertNotIn("GH_TOKEN", keys)
        self.assertIn("PATH", keys)
        self.assertIn("PASEO_PASSWORD", keys)
        self.assertTrue(set(keys) <= {"PATH", "PASEO_PASSWORD"}, keys)

    def test_password_never_in_argv(self):
        os.environ["PASEO_PASSWORD"] = "synthetic-pw-marker"
        rc, out = self.run_tool("report", "list")
        self.assertEqual(rc, M.RC_OK, out)
        argv = (pathlib.Path(self.sdk) / "argv.json").read_text(encoding="utf-8")
        self.assertNotIn("synthetic-pw-marker", argv)
        target = json.loads((pathlib.Path(self.sdk) / "target.json").read_text(encoding="utf-8"))
        self.assertTrue(target["hasPassword"])

    def test_password_passed_only_when_present(self):
        os.environ.pop("PASEO_PASSWORD", None)
        rc, out = self.run_tool("report", "list")
        self.assertEqual(rc, M.RC_OK, out)
        target = json.loads((pathlib.Path(self.sdk) / "target.json").read_text(encoding="utf-8"))
        self.assertFalse(target["hasPassword"])


class ReportListTest(Base):
    def test_counts_come_from_summary_fields(self):
        rc, out = self.run_tool("report", "list")
        self.assertEqual(rc, M.RC_OK, out)
        job = json.loads(out)["jobs"][0]
        self.assertEqual(job["findings"], 6)
        self.assertEqual(job["resolved"], 0)
        self.assertTrue(job["reportAvailable"])
        # resolvedFindings 只计 resolved；清单不推断开放数。
        self.assertNotIn("openFindings", job)

    def test_summary_does_not_claim_open_total(self):
        # 真实形状：6 条发现、0 条 resolved、1 条 false_positive，实际开放 5。
        rc, out = self.run_tool("report", "list")
        self.assertEqual(rc, M.RC_OK, out)
        summary = json.loads(out)["jobs"][0]
        self.assertEqual(summary["findings"], 6)
        self.assertEqual(summary["resolved"], 0)
        self.assertNotIn("openFindings", summary)

        rc, out = self.run_tool("report", "show", "--job-id", "job-1")
        self.assertEqual(rc, M.RC_OK, out)
        details = json.loads(out)["findings"]
        self.assertEqual(len(details), summary["findings"])
        counts = {}
        for item in details:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        self.assertEqual(counts, {"open": 5, "false_positive": 1})
        self.assertEqual(counts.get("resolved", 0), summary["resolved"])

    def test_summary_without_counts_is_not_reported_as_zero(self):
        scenario = base_scenario()
        scenario["response"]["observatory.insights.list"]["jobs"][0].pop("findings")
        write_scenario(self.sdk, scenario)
        rc, out = self.run_tool("report", "list")
        self.assertEqual(rc, M.RC_OK, out)
        job = json.loads(out)["jobs"][0]
        self.assertIsNone(job["findings"])


class ReportShowTest(Base):
    def test_show_calls_report_directly(self):
        rc, out = self.run_tool("report", "show", "--job-id", "job-1")
        self.assertEqual(rc, M.RC_OK, out)
        payload = json.loads(out)
        self.assertEqual(payload["jobId"], "job-1")
        self.assertEqual([c["method"] for c in self.calls()], ["observatory.insights.report"])

    def test_show_missing_report_is_input_error_and_zero_write(self):
        scenario = base_scenario()
        scenario["response"]["observatory.insights.report"] = {"job": None}
        write_scenario(self.sdk, scenario)
        rc, out = self.run_tool("report", "show", "--job-id", "job-1")
        self.assertEqual(rc, M.RC_INPUT, out)
        self.assertEqual(json.loads(out)["code"], "job_not_found")
        self.assertEqual([c["method"] for c in self.calls()], ["observatory.insights.report"])

    def test_show_job_id_mismatch_stops(self):
        scenario = base_scenario()
        scenario["response"]["observatory.insights.report"]["job"]["id"] = "job-other"
        write_scenario(self.sdk, scenario)
        rc, out = self.run_tool("report", "show", "--job-id", "job-1")
        self.assertEqual(rc, M.RC_VERIFY, out)
        self.assertEqual(json.loads(out)["code"], "job_id_mismatch")


class DryRunTest(Base):
    def test_dry_run_sends_no_write(self):
        rc, out = self.run_tool("finding", "dry-run", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "resolved")
        self.assertEqual(rc, M.RC_OK, out)
        payload = json.loads(out)
        self.assertFalse(payload["write"])
        self.assertEqual(payload["plannedStatus"], "resolved")
        self.assertEqual(payload["beforeStatus"], "open")
        methods = [c["method"] for c in self.calls()]
        self.assertNotIn("observatory.insights.feedback", methods)
        self.assertEqual(methods, ["observatory.insights.report"])

    def test_dry_run_rejects_unknown_status(self):
        rc, out = self.run_tool("finding", "dry-run", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "done")
        self.assertEqual(rc, M.RC_INPUT, out)
        self.assertEqual(self.calls(), [])

    def test_no_feedback_counts_as_open(self):
        rc, out = self.run_tool("finding", "dry-run", "--job-id", "job-1",
                                "--finding-id", "f-3", "--status", "resolved")
        self.assertEqual(rc, M.RC_OK, out)
        self.assertEqual(json.loads(out)["beforeStatus"], "open")
        self.assertEqual([c["method"] for c in self.calls()], ["observatory.insights.report"])

    def test_verify_without_feedback_is_open_and_verified(self):
        rc, out = self.run_tool("finding", "verify", "--job-id", "job-1", "--finding-id", "f-3")
        self.assertEqual(rc, M.RC_OK, out)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "open")
        self.assertTrue(payload["verified"])

    def test_verify_job_id_mismatch_zero_write(self):
        scenario = base_scenario()
        scenario["response"]["observatory.insights.report"]["job"]["id"] = "job-other"
        write_scenario(self.sdk, scenario)
        rc, out = self.run_tool("finding", "verify", "--job-id", "job-1", "--finding-id", "f-1")
        self.assertEqual(rc, M.RC_VERIFY, out)
        self.assertEqual([c["method"] for c in self.calls()], ["observatory.insights.report"])

    def test_suggestion_dry_run_uses_own_status_set(self):
        rc, out = self.run_tool("suggestion", "dry-run", "--job-id", "job-9",
                                "--action-id", "a-1", "--status", "adopted")
        self.assertEqual(rc, M.RC_OK, out)
        self.assertEqual(json.loads(out)["plannedStatus"], "adopted")
        self.assertEqual([c["method"] for c in self.calls()], ["observatory.insights.suggestions"])


class WriteTest(Base):
    def test_close_writes_and_verifies(self):
        write_scenario(self.sdk, base_scenario(writeOutcome="apply"))
        rc, out = self.run_tool("finding", "close", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "resolved")
        self.assertEqual(rc, M.RC_OK, out)
        payload = json.loads(out)
        self.assertTrue(payload["verified"])
        self.assertEqual(payload["afterStatus"], "resolved")
        methods = [c["method"] for c in self.calls()]
        self.assertEqual(methods.count("observatory.insights.feedback"), 1)

    def test_verify_fails_when_readback_not_applied(self):
        write_scenario(self.sdk, base_scenario(writeOutcome="ignore"))
        rc, out = self.run_tool("finding", "close", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "resolved")
        self.assertEqual(rc, M.RC_VERIFY, out)
        payload = json.loads(out)
        self.assertFalse(payload["verified"])
        self.assertFalse(payload["ok"])
        # 回执不明只回读，不重写
        methods = [c["method"] for c in self.calls()]
        self.assertEqual(methods.count("observatory.insights.feedback"), 1)

    def test_write_throw_still_reads_back_without_rewrite(self):
        write_scenario(self.sdk, base_scenario(writeOutcome="throw"))
        rc, out = self.run_tool("finding", "close", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "false_positive")
        self.assertEqual(rc, M.RC_VERIFY, out)
        payload = json.loads(out)
        self.assertEqual(payload["writeState"], "unclear")
        methods = [c["method"] for c in self.calls()]
        self.assertEqual(methods.count("observatory.insights.feedback"), 1)

    def test_idempotent_when_already_in_target_state(self):
        scenario = base_scenario()
        scenario["response"]["observatory.insights.report"]["job"]["findingFeedback"] = {
            "f-1": {"status": "resolved"}}
        write_scenario(self.sdk, scenario)
        rc, out = self.run_tool("finding", "close", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "resolved")
        self.assertEqual(rc, M.RC_OK, out)
        payload = json.loads(out)
        self.assertTrue(payload["idempotent"])
        self.assertFalse(payload["write"])
        methods = [c["method"] for c in self.calls()]
        self.assertNotIn("observatory.insights.feedback", methods)

    def test_close_needs_no_extra_confirm_flag(self):
        write_scenario(self.sdk, base_scenario(writeOutcome="apply"))
        rc, out = self.run_tool("finding", "close", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "resolved")
        self.assertEqual(rc, M.RC_OK, out)
        self.assertTrue(json.loads(out)["verified"])

    def test_missing_report_on_close_is_input_error_and_zero_write(self):
        scenario = base_scenario()
        scenario["response"]["observatory.insights.report"] = {"job": None}
        write_scenario(self.sdk, scenario)
        rc, out = self.run_tool("finding", "close", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "resolved")
        self.assertEqual(rc, M.RC_INPUT, out)
        self.assertEqual(json.loads(out)["code"], "job_not_found")
        self.assertEqual([c["method"] for c in self.calls()], ["observatory.insights.report"])

    def test_read_job_id_mismatch_blocks_write(self):
        scenario = base_scenario(writeOutcome="apply")
        scenario["response"]["observatory.insights.report"]["job"]["id"] = "job-other"
        write_scenario(self.sdk, scenario)
        rc, out = self.run_tool("finding", "close", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "resolved")
        self.assertEqual(rc, M.RC_VERIFY, out)
        self.assertEqual(json.loads(out)["code"], "job_id_mismatch")
        self.assertEqual([c["method"] for c in self.calls()], ["observatory.insights.report"])

    def test_write_receipt_job_id_mismatch_stops_without_rewrite(self):
        scenario = base_scenario(writeOutcome="apply", writeJobId="job-other")
        write_scenario(self.sdk, scenario)
        rc, out = self.run_tool("finding", "close", "--job-id", "job-1",
                                "--finding-id", "f-1", "--status", "resolved")
        self.assertEqual(rc, M.RC_VERIFY, out)
        self.assertEqual(json.loads(out)["code"], "job_id_mismatch")
        methods = [c["method"] for c in self.calls()]
        self.assertEqual(methods.count("observatory.insights.feedback"), 1)

    def test_unknown_entry_is_input_error(self):
        rc, out = self.run_tool("finding", "verify", "--job-id", "job-1", "--finding-id", "nope")
        self.assertEqual(rc, M.RC_INPUT, out)


class WhitelistTest(Base):
    def test_only_registered_methods_reach_sdk(self):
        original = M.run_bridge

        def spy(cli, target, server_id, calls, allow, timeout, node=None):
            self.assertTrue(all(m in M.METHODS for m, _ in calls), calls)
            return original(cli, target, server_id, calls, allow, timeout, node)

        M.run_bridge = spy
        try:
            rc, out = self.run_tool("report", "list")
        finally:
            M.run_bridge = original
        self.assertEqual(rc, M.RC_OK, out)
        self.assertEqual(set(M.METHODS), {
            "observatory.insights.list", "observatory.insights.report",
            "observatory.insights.suggestions", "observatory.insights.feedback",
            "observatory.insights.action-feedback"})


class GateTest(Base):
    def test_identity_mismatch_stops_before_any_rpc(self):
        # daemon 报出的 serverId 与 --server-id 不符：必须在任何 RPC 前停止。
        write_scenario(self.sdk, base_scenario(serverId="some-other-daemon"))
        rc, out = self.run_tool("report", "list")
        self.assertEqual(rc, M.RC_IDENTITY, out)
        self.assertEqual(json.loads(out)["code"], "daemon_identity_mismatch")
        self.assertEqual(self.calls(), [])

    def test_identity_match_allows_rpc(self):
        rc, out = self.run_tool("report", "list")
        self.assertEqual(rc, M.RC_OK, out)
        self.assertEqual([c["method"] for c in self.calls()], ["observatory.insights.list"])

    def test_non_loopback_target_rejected(self):
        with self.assertRaises(M.Fail) as box:
            M.validate_target("10.1.2.3:6767")
        self.assertEqual(box.exception.code, "target_not_loopback")

    def test_loopback_forms_accepted(self):
        for target in ("127.0.0.1:6767", "[::1]:9000"):
            self.assertEqual(M.validate_target(target), target)

    def test_localhost_rejected(self):
        # localhost 可能解析到非回环地址；只接受显式回环 IP。
        with self.assertRaises(M.Fail) as box:
            M.validate_target("localhost:6767")
        self.assertEqual(box.exception.code, "target_not_loopback")

    def test_shim_not_treated_as_package(self):
        shim = pathlib.Path(self.tmp) / "paseo-shim"
        shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        with self.assertRaises(M.Fail) as box:
            M.resolve_cli(str(shim))
        self.assertEqual(box.exception.code, "paseo_cli_not_package")

    def test_version_mismatch_rejected(self):
        pkg = pathlib.Path(self.cli) / "package.json"
        pkg.write_text(json.dumps({"name": "@getpaseo/cli", "version": "0.0.0"}), encoding="utf-8")
        with self.assertRaises(M.Fail) as box:
            M.resolve_cli(self.cli)
        self.assertEqual(box.exception.code, "paseo_version_unexpected")

    def test_sdk_version_mismatch_rejected(self):
        pkg = pathlib.Path(self.cli) / "node_modules" / "@getpaseo" / "client" / "package.json"
        pkg.write_text(json.dumps({"name": "@getpaseo/client", "version": "0.0.0"}), encoding="utf-8")
        with self.assertRaises(M.Fail) as box:
            M.resolve_cli(self.cli)
        self.assertEqual(box.exception.code, "sdk_version_unexpected")

    def test_sdk_package_missing_rejected(self):
        pkg = pathlib.Path(self.cli) / "node_modules" / "@getpaseo" / "client" / "package.json"
        pkg.unlink()
        with self.assertRaises(M.Fail) as box:
            M.resolve_cli(self.cli)
        self.assertEqual(box.exception.code, "sdk_package_missing")

    def test_auth_failures_map_to_auth_rc_by_name_and_reason(self):
        for reason in ("password_required", "incorrect_password"):
            write_scenario(self.sdk, base_scenario(connectError=reason))
            rc, out = self.run_tool("report", "list")
            self.assertEqual(rc, M.RC_AUTH, out)
            self.assertEqual(json.loads(out)["code"], "daemon_auth_required")

    def test_other_connect_error_is_not_auth(self):
        write_scenario(self.sdk, base_scenario(connectError="econnrefused"))
        rc, out = self.run_tool("report", "list")
        self.assertEqual(rc, M.RC_ENV, out)


if __name__ == "__main__":
    unittest.main()

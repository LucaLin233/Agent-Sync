#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paseo 观测台（Agent Observatory）报告的固定窄入口。

只做的事：经官方 @getpaseo/client 连接已核本地 daemon，读报告、按显式选择的
finding 状态写一次反馈并回读，或对改进建议做同样的按 actionId 校验与回读。

用法：
  paseo-observatory.py report list   --server-id ID [--agent-id ID]
  paseo-observatory.py report show   --server-id ID --job-id JOB
  paseo-observatory.py finding dry-run   --server-id ID --job-id JOB --finding-id F --status S
  paseo-observatory.py finding close     --server-id ID --job-id JOB --finding-id F --status S
  paseo-observatory.py finding verify    --server-id ID --job-id JOB --finding-id F
  paseo-observatory.py suggestion dry-run --server-id ID --job-id JOB --action-id A --status S
  paseo-observatory.py suggestion close   --server-id ID --job-id JOB --action-id A --status S
  paseo-observatory.py suggestion verify  --server-id ID --job-id JOB --action-id A

设计约束（与报告 closeout-channel-friction、inline-rpc-repetition、
credential-env-inheritance 对应）：
- 固定动作与固定 RPC 方法名；无任意 URL、命令、方法名或表达式入口。
- 目标只接受显式回环 IP（127.0.0.1 或 [::1]）加端口；连接后必须核 serverId 等于
  --server-id，不符即停。不解析 localhost，避免宿主解析到非回环地址。
- 子进程环境从零重建，只给 PATH 与按名获准注入的 PASEO_PASSWORD；不继承父环境。
- 只输出稳定 JSON 一行，字段仅 ID、状态、时间、公开枚举和计数；不回显报告正文、
  证据、配置、连接信息或 SDK 错误原文。
- dry-run 只发读调用，零写；close 由显式动作、条目与目标状态表达意图，回执不明时
  先回读、不重写。
- 退出码：0 成功且已核实；1 参数/输入不合法；2 环境（CLI/SDK/Node）不合格；
  3 需要认证或认证失败；4 daemon 身份不符；5 写入后回读不符或不明。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

FINDING_STATUSES = ("open", "resolved", "false_positive")
SUGGESTION_STATUSES = ("open", "adopted", "done", "dismissed")
PASEO_VERSION = "0.17.4"
SDK_VERSION = "0.17.4"
RPC_PLUGIN = "agent-observatory"
# 固定方法白名单：run_bridge 只放行这里登记的方法，读/写分类供调用方核对。
METHODS = {
    "observatory.insights.list": "read",
    "observatory.insights.report": "read",
    "observatory.insights.suggestions": "read",
    "observatory.insights.feedback": "write",
    "observatory.insights.action-feedback": "write",
}
LOOPBACK = re.compile(r"^(?:127\.0\.0\.1|\[::1\]):\d{1,5}$")

RC_OK, RC_INPUT, RC_ENV, RC_AUTH, RC_IDENTITY, RC_VERIFY = 0, 1, 2, 3, 4, 5

NODE_BRIDGE = r"""
const fs = require('node:fs');
const path = require('node:path');
const req = JSON.parse(fs.readFileSync(0, 'utf8'));
const clientPkg = path.join(req.cliRoot, 'node_modules', '@getpaseo', 'client');
const { createHostClient } = require(path.join(clientPkg, 'dist', 'node', 'index.js'));
(async () => {
  const config = {
    clientId: 'agent-sync-paseo-observatory',
    clientType: 'cli',
    connectTimeoutMs: req.timeoutMs,
    reconnect: { enabled: false },
  };
  if (process.env.PASEO_PASSWORD) config.password = process.env.PASEO_PASSWORD;
  const client = createHostClient(req.target, config);
  const out = { stage: 'connect' };
  try {
    await client.connect();
    const info = client.getLastServerInfoMessage() || null;
    out.serverId = info && typeof info.serverId === 'string' ? info.serverId : null;
    out.daemonVersion = info && typeof info.version === 'string' ? info.version : null;
    if (!out.serverId || (req.serverId && out.serverId !== req.serverId)) {
      process.stdout.write(JSON.stringify({ ok: false, code: 'identity_mismatch', stage: 'identity',
        serverId: out.serverId, daemonVersion: out.daemonVersion }));
      return;
    }
    out.stage = 'rpc';
    const results = [];
    for (const call of req.calls) {
      if (!req.allowedMethods.includes(call.method)) {
        process.stdout.write(JSON.stringify({ ok: false, code: 'method_not_allowed', stage: 'rpc' }));
        return;
      }
      results.push(await client.invokePluginRpc(req.plugin, call.method, call.input));
    }
    process.stdout.write(JSON.stringify({ ok: true, serverId: out.serverId,
      daemonVersion: out.daemonVersion, results }));
  } catch (error) {
    // 0.17.4 的 DaemonAuthenticationError 只带 name 和 reason，没有 code。
    const name = error && typeof error === 'object' ? error.name : '';
    const reason = error && typeof error === 'object' ? error.reason : '';
    const authFailure = name === 'DaemonAuthenticationError'
      && (reason === 'password_required' || reason === 'incorrect_password');
    process.stdout.write(JSON.stringify({ ok: false,
      code: authFailure ? 'auth' : (out.stage === 'rpc' ? 'rpc_error' : 'connect_error'),
      stage: out.stage }));
  } finally {
    try { await client.close(); } catch (_) { /* 关闭失败不改变已得结论 */ }
  }
})();
"""


class Fail(Exception):
    """固定类别失败：只带类别，不带原文。"""

    def __init__(self, rc, code):
        super().__init__(code)
        self.rc, self.code = rc, code


def child_env(allow_password):
    """从零构造子进程环境：只给 PATH 与按名获准的 PASEO_PASSWORD。"""
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}
    if allow_password:
        value = os.environ.get("PASEO_PASSWORD")
        if value:
            env["PASEO_PASSWORD"] = value
    return env


def validate_target(target):
    if not LOOPBACK.match(target or ""):
        raise Fail(RC_INPUT, "target_not_loopback")
    port = int(target.rsplit(":", 1)[1])
    if port < 1 or port > 65535:
        raise Fail(RC_INPUT, "target_port_invalid")
    return target


def _read_manifest(cli_root):
    try:
        with open(os.path.join(cli_root, "package.json"), "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def resolve_cli(explicit):
    """解析已核的 Paseo CLI 包根，并同时校验 CLI 与 SDK 版本及 SDK 入口。

    只读 argv 给的路径，不读环境、配置或保存态。接受 @getpaseo/cli 包根目录，或其
    bin 下的可执行文件路径；版本管理器（如 mise）的转发 shim 不是真实入口，会
    按解析失败处理而不是被猜成包根。
    """
    if not explicit:
        raise Fail(RC_INPUT, "paseo_cli_required")
    candidate = os.path.realpath(explicit)
    candidates = [candidate]
    if os.path.isfile(candidate):
        candidates.append(os.path.realpath(os.path.join(os.path.dirname(candidate), "..")))
    for cli_root in candidates:
        pkg = _read_manifest(cli_root) if os.path.isdir(cli_root) else None
        if not pkg or pkg.get("name") != "@getpaseo/cli":
            continue
        if pkg.get("version") != PASEO_VERSION:
            raise Fail(RC_ENV, "paseo_version_unexpected")
        sdk_root = os.path.join(cli_root, "node_modules", "@getpaseo", "client")
        sdk_pkg = _read_manifest(sdk_root) if os.path.isdir(sdk_root) else None
        if not sdk_pkg or sdk_pkg.get("name") != "@getpaseo/client":
            raise Fail(RC_ENV, "sdk_package_missing")
        if sdk_pkg.get("version") != SDK_VERSION:
            raise Fail(RC_ENV, "sdk_version_unexpected")
        if not os.path.isfile(os.path.join(sdk_root, "dist", "node", "index.js")):
            raise Fail(RC_ENV, "sdk_entry_missing")
        return cli_root
    raise Fail(RC_ENV, "paseo_cli_not_package")


def run_bridge(cli_root, target, server_id, calls, allow_password, timeout_s, node=None):
    """以最小环境调用官方 SDK 桥；请求经 stdin 传递，不进 argv。"""
    node = node or shutil.which("node")
    if not node or not os.path.isfile(node):
        raise Fail(RC_ENV, "node_unresolved")
    request = json.dumps({
        "cliRoot": cli_root, "target": target, "serverId": server_id,
        "plugin": RPC_PLUGIN, "timeoutMs": min(timeout_s, 30) * 1000,
        "allowedMethods": sorted(METHODS),
        "calls": [{"method": m, "input": i} for m, i in calls],
    })
    try:
        proc = subprocess.run(
            [node, "-e", NODE_BRIDGE],
            input=request.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=child_env(allow_password), cwd="/", timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        raise Fail(RC_ENV, "bridge_timeout")
    raw = proc.stdout.decode("utf-8", "replace").strip()
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        raise Fail(RC_ENV, "bridge_unparsable")
    if not isinstance(payload, dict):
        raise Fail(RC_ENV, "bridge_unparsable")
    if payload.get("ok"):
        return payload
    code = payload.get("code")
    if code == "identity_mismatch":
        raise Fail(RC_IDENTITY, "daemon_identity_mismatch")
    if code == "method_not_allowed":
        raise Fail(RC_ENV, "rpc_method_not_allowed")
    if code == "auth":
        raise Fail(RC_AUTH, "daemon_auth_required")
    raise Fail(RC_ENV, "bridge_failed")


def expect_read(payload, index):
    results = payload.get("results") or []
    if index >= len(results) or not isinstance(results[index], dict):
        raise Fail(RC_ENV, "rpc_result_missing")
    return results[index]


JOB_ID_MAX, ENTRY_ID_MAX = 128, 80


def _feedback_status(feedback, entry_id):
    """无反馈按 open 计（正式口径），只投影公开枚举。"""
    current = feedback.get(entry_id)
    status = current.get("status") if isinstance(current, dict) else current
    return status if isinstance(status, str) and status else "open"


def project_report(job):
    """只投影已确认非秘密字段。"""
    report = job.get("report") if isinstance(job.get("report"), dict) else {}
    feedback = job.get("findingFeedback") if isinstance(job.get("findingFeedback"), dict) else {}
    items = []
    for finding in report.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        fid = finding.get("id")
        if not isinstance(fid, str):
            continue
        items.append({"findingId": fid, "status": _feedback_status(feedback, fid)})
    return {"jobId": job.get("id"), "findings": items}


def project_suggestions(job):
    report = job.get("report") if isinstance(job.get("report"), dict) else {}
    feedback = job.get("feedback") if isinstance(job.get("feedback"), dict) else {}
    items = []
    for action in report.get("actions") or []:
        if not isinstance(action, dict):
            continue
        aid = action.get("id")
        if not isinstance(aid, str):
            continue
        items.append({"actionId": aid, "status": _feedback_status(feedback, aid)})
    return {"jobId": job.get("id"), "actions": items}


def _check_id(value, limit):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise Fail(RC_INPUT, "identifier_invalid")


def _job_from(data, job_id):
    """只接受与请求 jobId 精确相等的 job；缺失或不符即停，不读写错对象。"""
    job = data.get("job") if isinstance(data, dict) and isinstance(data.get("job"), dict) else None
    if job is None:
        raise Fail(RC_INPUT, "job_not_found")
    if job.get("id") != job_id:
        raise Fail(RC_VERIFY, "job_id_mismatch")
    return job


def _count(value):
    """整数计数原样投影；字段缺失或类型不符给 None，不误报 0。"""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def cmd_report_list(args, ctx):
    payload = run_bridge(ctx["cli"], ctx["target"], args.server_id,
                         [("observatory.insights.list", {"agentId": args.agent_id} if args.agent_id else {})],
                         ctx["allow_password"], ctx["timeout"], ctx["node"])
    data = expect_read(payload, 0)
    jobs = data.get("jobs") if isinstance(data.get("jobs"), list) else []
    rows = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        findings = _count(job.get("findings"))
        resolved = _count(job.get("resolvedFindings"))
        available = job.get("reportAvailable")
        available = available if isinstance(available, bool) else None
        rows.append({"jobId": job.get("id"),
                     "agentId": job.get("agentId") if isinstance(job.get("agentId"), str) else None,
                     "createdAt": job.get("createdAt") if isinstance(job.get("createdAt"), str) else None,
                     "findings": findings, "resolved": resolved,
                     "openFindings": findings - resolved
                     if findings is not None and resolved is not None else None,
                     "reportAvailable": available})
    emit({"ok": True, "command": "report list", "serverId": payload.get("serverId"),
          "count": len(rows), "jobs": rows})
    return RC_OK


def cmd_report_show(args, ctx):
    _check_id(args.job_id, JOB_ID_MAX)
    payload = run_bridge(ctx["cli"], ctx["target"], args.server_id,
                         [("observatory.insights.report", {"jobId": args.job_id})],
                         ctx["allow_password"], ctx["timeout"], ctx["node"])
    job = _job_from(expect_read(payload, 0), args.job_id)
    emit({"ok": True, "command": "report show", "serverId": payload.get("serverId"),
          **project_report(job)})
    return RC_OK


def _read_entry(args, ctx, kind):
    method = "observatory.insights.report" if kind == "finding" else "observatory.insights.suggestions"
    payload = run_bridge(ctx["cli"], ctx["target"], args.server_id, [(method, {"jobId": args.job_id})],
                         ctx["allow_password"], ctx["timeout"], ctx["node"])
    job = _job_from(expect_read(payload, 0), args.job_id)
    return payload, (project_report(job) if kind == "finding" else project_suggestions(job))


def _entry_key(kind):
    return ("findingId", "findings") if kind == "finding" else ("actionId", "actions")


def _lookup(view, kind, entry_id):
    key, bucket = _entry_key(kind)
    for item in view.get(bucket) or []:
        if item.get(key) == entry_id:
            return item
    return None


def cmd_entry(args, ctx, kind, mode):
    valid = FINDING_STATUSES if kind == "finding" else SUGGESTION_STATUSES
    entry_id = args.finding_id if kind == "finding" else args.action_id
    _check_id(args.job_id, JOB_ID_MAX)
    _check_id(entry_id, ENTRY_ID_MAX)
    if mode != "verify" and args.status not in valid:
        raise Fail(RC_INPUT, "status_invalid")
    before_payload, before = _read_entry(args, ctx, kind)
    before_item = _lookup(before, kind, entry_id)
    if before_item is None:
        raise Fail(RC_INPUT, "entry_not_found")
    out = {"serverId": before_payload.get("serverId"), "jobId": args.job_id,
           _entry_key(kind)[0]: entry_id,
           "beforeStatus": before_item.get("status")}
    if mode == "dry-run":
        out.update({"ok": True, "command": f"{kind} dry-run", "write": False,
                    "plannedStatus": args.status, "verified": None})
        emit(out)
        return RC_OK
    if mode == "verify":
        status = before_item.get("status")
        verified = status in valid
        out.update({"ok": verified, "command": f"{kind} verify", "write": False,
                    "status": status, "verified": verified})
        emit(out)
        return RC_OK if verified else RC_VERIFY
    if before_item.get("status") == args.status:
        out.update({"ok": True, "command": f"{kind} close", "write": False,
                    "idempotent": True, "afterStatus": args.status, "verified": True})
        emit(out)
        return RC_OK
    if kind == "finding":
        write_call = ("observatory.insights.feedback",
                      {"jobId": args.job_id, "findingId": entry_id, "status": args.status})
    else:
        write_call = ("observatory.insights.action-feedback",
                      {"jobId": args.job_id, "actionId": entry_id, "status": args.status})
    write_state = "sent"
    try:
        written = run_bridge(ctx["cli"], ctx["target"], args.server_id, [write_call],
                             ctx["allow_password"], ctx["timeout"], ctx["node"])
        written_job = expect_read(written, 0)
        if isinstance(written_job.get("id"), str) and written_job.get("id") != args.job_id:
            raise Fail(RC_VERIFY, "job_id_mismatch")
    except Fail as exc:
        if exc.rc in (RC_AUTH, RC_IDENTITY):
            raise
        if exc.code == "job_id_mismatch":
            emit({"ok": False, "command": f"{kind} close", "write": True,
                  "writeState": "sent", "plannedStatus": args.status, "code": exc.code})
            return RC_VERIFY
        write_state = "unclear"
    # 无论回执如何都只回读一次实际状态；回读不明不重写，ID 不符也不改读别的对象。
    after_status = None
    read_state = "ok"
    try:
        _, after = _read_entry(args, ctx, kind)
        after_item = _lookup(after, kind, entry_id)
        after_status = after_item.get("status") if after_item else None
    except Fail as exc:
        read_state = exc.code
    verified = after_status == args.status
    out.update({"command": f"{kind} close", "write": True, "writeState": write_state,
                "plannedStatus": args.status, "afterStatus": after_status, "verified": verified,
                "ok": verified})
    if read_state != "ok":
        out["readState"] = read_state
    emit(out)
    return RC_OK if verified else RC_VERIFY


class Parser(argparse.ArgumentParser):
    """参数错误只报固定类别，不回显原始参数值。"""

    def error(self, _):
        self.exit(RC_INPUT, '{"ok": false, "code": "invalid_arguments"}\n')


def build_parser():
    parser = Parser(prog="paseo-observatory.py", add_help=True)
    parser.add_argument("--target", required=True,
                        help="现场已核的本地 loopback daemon 地址，如 127.0.0.1:<port>")
    parser.add_argument("--server-id", required=True, help="预期 daemon serverId")
    parser.add_argument("--paseo-cli", required=True,
                        help="已核的 @getpaseo/cli 包根或其 bin 文件路径")
    parser.add_argument("--timeout", type=int, default=30, help="单次桥调用上限秒")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("report", "finding", "suggestion"):
        group = sub.add_parser(name)
        actions = group.add_subparsers(dest="action", required=True)
        if name == "report":
            for action in ("list", "show"):
                cmd = actions.add_parser(action)
                if action == "list":
                    cmd.add_argument("--agent-id")
                else:
                    cmd.add_argument("--job-id", required=True)
        else:
            for action in ("dry-run", "close", "verify"):
                cmd = actions.add_parser(action)
                cmd.add_argument("--job-id", required=True)
                if name == "finding":
                    cmd.add_argument("--finding-id", required=True)
                else:
                    cmd.add_argument("--action-id", required=True)
                if action != "verify":
                    cmd.add_argument("--status", required=True)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        target = validate_target(args.target)
        ctx = {"cli": resolve_cli(args.paseo_cli), "target": target,
               "timeout": max(1, min(args.timeout, 120)), "node": shutil.which("node"),
               "allow_password": True}
        if args.command == "report":
            return cmd_report_list(args, ctx) if args.action == "list" else cmd_report_show(args, ctx)
        kind = "finding" if args.command == "finding" else "suggestion"
        return cmd_entry(args, ctx, kind, args.action)
    except Fail as exc:
        emit({"ok": False, "code": exc.code})
        return exc.rc
    except KeyboardInterrupt:
        emit({"ok": False, "code": "interrupted"})
        return RC_ENV


if __name__ == "__main__":
    sys.exit(main())

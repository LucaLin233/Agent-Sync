#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CCHP 会话复用（session.reuse_enabled）核对与对齐工具。

约定：优先级 1–19 的 provider key 在 provider_key 作用域显式设本级
session.reuse_enabled=true，其余 key 显式设本级 false；两类都写明确布尔值，不移除覆盖。
本级已正确但生效值不符（被上级覆盖或锁定）时报需人工，不强行改写。

用法：
  cchp-session-reuse.py              只读核对，输出对比表；全部一致退出码 0，有不一致 1
  cchp-session-reuse.py --dry-run    只读核对 + 打印将要发送的写请求（不发送）
  cchp-session-reuse.py --apply      仅改“本级不符”的项，逐项回读；改后一致退出码 0
  cchp-session-reuse.py --self-test  用伪造数据验证判定逻辑（不联网、不写）
  cchp-session-reuse.py -h|--help    打印简短用法并退出，不读环境变量

判定三类：一致；需写（本级缺失或值与期望不符，本工具可改）；需人工（本级已正确但生效值
不符，或被上级阻断，本工具写入无效）。有需人工项时退出码 1。

失败只输出固定诊断类别和整数退出码，不转发子进程 stderr 或服务 error.message 原文。
读调用遇到非零退出码一律失败，即使 JSON 的 ok=true；写调用遇到非零、坏 JSON 或失败包
时先回读实际状态，达到期望才继续，否则以退出码 3 停止。dry-run 的非零同样是失败。

列表只取一页（--limit 100）：partial/preparing 为 true 或仍有 nextCursor 时报错退出，
不在不完整列表上读写；已撤销（revoked_at 非空或 status=revoked）的 key 跳过并计数，
停用但未撤销的 key 照常处理。

凭据：只从环境变量 CCHP_GATEWAY_URL / CCHP_TOKEN 取，经子进程环境传给 cchp，
      不进命令行、不读保存态或文件、不写临时文件（body 走 --body-file - 的 stdin）。
范围：只读/写 session.reuse_enabled 这一个配置键；ID 全部由接口动态取得。
"""
import json
import os
import subprocess
import sys
import contextlib
import io

KEY = "session.reuse_enabled"
WANT_ON_FIRST, WANT_ON_LAST = 1, 19
ENV = {}

HELP = """CCHP 会话复用工具：核对 provider key 的 session.reuse_enabled，按约定对齐。

用法（python3 cchp-session-reuse.py [模式]）：
  （无参数）    只读核对；退出码 0=全部一致，1=有不一致或需人工，3=异常
  --dry-run     只读核对 + 打印将要发送的写请求（不发送）
  --apply       只改“本级不符”的项，逐项回读
  --self-test   离线判定逻辑自检（不联网、不写）
  -h, --help    显示本帮助（无需环境变量）

环境变量：CCHP_GATEWAY_URL、CCHP_TOKEN

调用方式：
  在仓库根目录按仓库相对路径运行：python3 tools/cchp-session-reuse.py [模式]
  上列两项环境变量由受信父进程按名注入，并以显式白名单环境启动（只给 PATH、HOME
  和这两项，不复制整份环境）；本工具只按名读取，不要把值写进命令行——任何形式的
  命令参数都会进入 argv 和进程列表。

约定：优先级 1–19 的 key 本级开启 session.reuse_enabled（true），其余 key 本级关闭（false）；
两类都写明确布尔值，不移除覆盖。写入走 saveSystemConfig 的 values，须用户明确授权；
已撤销 key 跳过，停用未撤销的 key 照常处理。"""


def diag(category, code, detail=""):
    message = "错误[%s] 退出码=%d" % (category, code)
    if detail:
        message += " " + detail
    print(message, file=sys.stderr)
    sys.exit(code)


def make_env():
    missing = [n for n in ("CCHP_GATEWAY_URL", "CCHP_TOKEN") if not os.environ.get(n)]
    if missing:
        diag("missing_env", 2, "缺少=" + ",".join(missing))
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
        "LC_ALL": "C.UTF-8",
        "CCHP_BASE_URL": os.environ["CCHP_GATEWAY_URL"],
        "CCHP_TOKEN": os.environ["CCHP_TOKEN"],
    }


def cchp(args, body=None, run=subprocess.run):
    """调用 cchp，只返回 (结果对象或 None, 退出码)；不读取或转发 stderr。"""
    try:
        p = run(["cchp"] + args, input=body, capture_output=True, text=True, env=ENV)
    except OSError:
        diag("command_error", 3)
    try:
        return json.loads(p.stdout), p.returncode
    except ValueError:
        return None, p.returncode


def result_error(obj, rc):
    """把一次调用归入固定类别；先看退出码，非零时即使 ok=true 也失败。"""
    if not isinstance(rc, int) or rc != 0:
        return "command_failed"
    if obj is None:
        return "output_not_json"
    if not isinstance(obj, dict) or obj.get("ok") is not True:
        return "api_failed"
    return None


def api(args, body=None, run=subprocess.run):
    """只读调用：任何失败都终止。"""
    o, rc = cchp(args, body, run)
    category = result_error(o, rc)
    if category:
        diag(category, 3, "action=%s cli_rc=%d" % (args[1], rc))
    return o


def skip_revoked(keys):
    """返回 (未撤销 key 列表, 跳过数)；撤销 key 的 scope 可能已不存在，约定不处理。"""
    kept, skipped = [], 0
    for k in keys:
        if k.get("revoked_at") or str(k.get("status", "")).lower() == "revoked":
            skipped += 1
        else:
            kept.append(k)
    return kept, skipped


def list_keys():
    """只取一页；不完整或未就绪的列表不用于读写。"""
    d = api(["api", "listProviderKeyPage", "--limit", "100", "--json"]).get("data")
    if not isinstance(d, dict):
        diag("bad_shape", 3, "action=listProviderKeyPage cli_rc=0")
    unready = [n for n in ("partial", "preparing") if d.get(n)]
    if unready:
        diag("list_unready", 3, "flags=%s cli_rc=0" % ",".join(unready))
    if d.get("nextCursor"):
        diag("list_incomplete", 3, "cli_rc=0")
    raw_keys = d.get("keys")
    if not isinstance(raw_keys, list):
        diag("bad_shape", 3, "action=listProviderKeyPage cli_rc=0")
    keys, skipped = skip_revoked(raw_keys)
    if skipped:
        print("跳过已撤销 key %d 个（revoked_at 非空或 status=revoked）。" % skipped)
    keys.sort(key=lambda k: (k["priority"], k["name"]))
    return keys


def read_state(scope):
    o = api(["api", "getConfigM2Page", "--scope-key", scope, "--prefix", KEY, "--json"])
    data = o.get("data")
    fields = data.get("fields") if isinstance(data, dict) else None
    if not isinstance(fields, list):
        diag("bad_shape", 3, "action=getConfigM2Page cli_rc=0")
    for f in fields:
        if isinstance(f, dict) and f.get("key") == KEY:
            return {
                "local": bool(f.get("has_published_local_assignment")),
                "local_value": f.get("published_local_value"),
                "effective": f.get("effective_value"),
                "source": f.get("source_scope_key"),
                "draft_local": bool(f.get("has_draft_local_assignment")),
                "blocked": bool(f.get("blocked")),
                "blocked_by": f.get("blocked_by_scope_key") or None,
            }
    diag("field_missing", 3, "action=getConfigM2Page cli_rc=0")


def want_local(priority):
    return WANT_ON_FIRST <= priority <= WANT_ON_LAST


def row(key, st):
    wl = want_local(key["priority"])
    local_ok = st["local"] is True and st["local_value"] is wl
    eff_ok = st["effective"] is wl
    blocked = st.get("blocked") is True
    if local_ok and eff_ok:
        fix, note = "none", "一致"
    elif blocked:
        fix = "manual"
        note = "需人工：本级被上级作用域阻断（%s），本工具写入无效" % (
            st.get("blocked_by") or st["source"] or "未知")
    elif local_ok:
        fix = "manual"
        note = ("需人工：本级已设 true，生效仍为 false（上级覆盖或锁定，来源 %s）"
                if wl else
                "需人工：本级已设 false，生效仍为 true（上级覆盖或锁定，来源 %s）") % (
                    st["source"] or "未知")
    else:
        fix = "local"
        note = "需写：设本级 true" if wl else "需写：设本级 false"
    return {
        "id": key["id"],
        "priority": key["priority"],
        "name": key["name"],
        "status": key["status"],
        "local": st["local"],
        "local_value": st["local_value"],
        "effective": st["effective"],
        "source": st["source"],
        "draft_local": st["draft_local"],
        "blocked": blocked,
        "want_local": wl,
        "want_eff": wl,
        "ok": fix == "none",
        "fix": fix,
        "note": note,
    }


def state_ok(cur, r):
    local_ok = cur["local"] is True and cur["local_value"] is r["want_local"]
    return local_ok and cur["effective"] is r["want_eff"]


def fmt_bool(v):
    if v is True:
        return "true"
    if v is False:
        return "false"
    return "null"


def fmt_local(r):
    return fmt_bool(r["local_value"]) if r["local"] else "（无）"


def fmt_want(r):
    return "本级=true 生效=true" if r["want_local"] else "本级=false 生效=false"


def print_table(rows, title):
    print(title)
    print("优先级 | 名称 | 状态 | 本级值 | 生效值 | 期望 | 判定")
    for r in rows:
        print("%s | %s | %s | %s | %s | %s | %s" % (
            r["priority"], r["name"], r["status"], fmt_local(r), fmt_bool(r["effective"]),
            fmt_want(r), r["note"]))
    bad = [r for r in rows if not r["ok"]]
    manual = [r for r in rows if r["fix"] == "manual"]
    print("合计 %d 项，一致 %d 项，需写 %d 项，需人工 %d 项" % (
        len(rows), len(rows) - len(bad), len(bad) - len(manual), len(manual)))
    return bad


def collect():
    rows = [row(k, read_state("provider_key:" + k["id"])) for k in list_keys()]
    sources = sorted({"%s=%s" % (r["source"] or "未知", fmt_bool(r["effective"]))
                      for r in rows if not r["local"]})
    print("键=%s 约定=优先级 %d–%d 本级 true，其余本级 false；无本级项观测来源=%s" % (
        KEY, WANT_ON_FIRST, WANT_ON_LAST,
        "，".join(sources) or "（本次未观测到无本级项，不推断上级默认值）"))
    return rows


def write_one(r, dry_run):
    scope = "provider_key:" + r["id"]
    body = json.dumps({"values": {KEY: r["want_local"]}}, separators=(",", ":"))
    action = "设本级 true" if r["want_local"] else "设本级 false"
    args = ["api", "saveSystemConfig", "--scope", scope, "--body-file", "-",
            "--allow-write", "--confirm", "saveSystemConfig"]
    if dry_run:
        args.append("--dry-run")
    args.append("--json")
    o, rc = cchp(args, body)
    return o, rc, body, action, scope


def apply_all(rows, dry_run):
    writable = [r for r in rows if r["fix"] == "local"]
    manual = [r for r in rows if r["fix"] == "manual"]
    if manual:
        print("需人工 %d 项（本级已正确但生效值不符，或被上级阻断；本工具写入无效）：%s" % (
            len(manual), "、".join("%s(%s)" % (r["name"], r["priority"]) for r in manual)),
            file=sys.stderr)
    if not writable:
        if manual:
            return 1
        print("无偏差，不写入。")
        return 0
    if any(r["draft_local"] for r in writable):
        diag("draft_present", 3)
    for i, r in enumerate(writable, 1):
        scope = "provider_key:" + r["id"]
        if read_state(scope)["draft_local"]:
            diag("draft_present", 3)
        o, rc, body, action, scope = write_one(r, dry_run)
        category = result_error(o, rc)
        label = "变更 #%d %s（%s）%s" % (i, r["name"], r["priority"], action)
        if dry_run:
            if category:
                print("%s\n  dry-run 失败[%s] 退出码=3 cli_rc=%d" % (label, category, rc))
                return 3
            req = o.get("dry_run") if isinstance(o.get("dry_run"), dict) else {}
            print("%s\n  scope=%s body=%s\n  method=%s path=%s" % (
                label, scope, body, req.get("method"), req.get("path")))
            continue
        print("%s\n  scope=%s operation=saveSystemConfig ok=%s body=%s" % (
            label, scope, isinstance(o, dict) and o.get("ok") is True, body))
        if category:
            print("  写调用失败[%s] 退出码=3 cli_rc=%d" % (category, rc))
            cur = read_state(scope)
            print("  重读：本级覆盖=%s 本级值=%s 生效值=%s" % (
                cur["local"], fmt_bool(cur["local_value"]), fmt_bool(cur["effective"])))
            if state_ok(cur, r):
                print("  状态已达期望，继续后续项。")
                continue
            print("  状态未达期望[write_unconfirmed] 退出码=3 cli_rc=%d，停止（不重试未知结果的写）。" % rc,
                  file=sys.stderr)
            return 3
        cur = read_state(scope)
        ok = state_ok(cur, r)
        print("  回读：本级覆盖=%s 本级值=%s 生效值=%s 来源=%s -> %s" % (
            cur["local"], fmt_bool(cur["local_value"]), fmt_bool(cur["effective"]),
            cur["source"], "一致" if ok else "不一致"))
        if not ok:
            print("  回读未达期望[readback_mismatch] 退出码=3 cli_rc=0，停止。", file=sys.stderr)
            return 3
    if dry_run:
        print("dry-run 结束：未发送任何写请求。")
        return 1 if manual else 0
    if manual:
        print("本级不符项已处理；剩余需人工项见上表。", file=sys.stderr)
        return 1
    return 0


def self_test():
    global read_state, write_one

    def k(i, p, n, s="active"):
        return {"id": i, "priority": p, "name": n, "status": s}

    def st(local, val, eff, src, draft=False, blocked=False, blocked_by=None):
        return {"local": local, "local_value": val, "effective": eff,
                "source": src, "draft_local": draft,
                "blocked": blocked, "blocked_by": blocked_by}

    def capture(fn):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = fn()
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    fail = 0

    def check(label, ok, detail=""):
        nonlocal fail
        if not ok:
            fail += 1
        print(("OK " if ok else "FAIL ") + label + ((" " + detail) if not ok and detail else ""))

    cases = [
        ("优先级1 本级true 生效true", k("k1", 1, "A"),
         st(True, True, True, "provider_key:k1"), "none"),
        ("优先级19 本级true 生效true", k("k19", 19, "B"),
         st(True, True, True, "provider_key:k19"), "none"),
        ("优先级0 本级false 生效false", k("k0", 0, "C"),
         st(True, False, False, "provider_key:k0"), "none"),
        ("优先级20 本级false 生效false", k("k20", 20, "D"),
         st(True, False, False, "provider_key:k20"), "none"),
        ("继承迁移 优先级15 无本级 继承false", k("k15", 15, "E"),
         st(False, None, False, "organization:o1"), "local"),
        ("继承迁移 优先级21 无本级 继承false", k("k21", 21, "F"),
         st(False, None, False, "organization:o1"), "local"),
        ("停用未撤销 优先级43 无本级 生效false", k("k3", 43, "G", "disabled"),
         st(False, None, False, "organization:o1"), "local"),
        ("旧策略误留本级true 优先级23", k("k4", 23, "H"),
         st(True, True, True, "provider_key:k4"), "local"),
        ("优先级14 本级false 需改true", k("k14", 14, "I"),
         st(True, False, False, "provider_key:k14"), "local"),
        ("优先级24 本级true 需改false", k("k24", 24, "J"),
         st(True, True, True, "provider_key:k24"), "local"),
        ("无本级 上级true 仍按本级false 对齐", k("k7", 31, "K"),
         st(False, None, True, "organization:o1"), "local"),
        ("本级false 生效被上级改成true", k("k8", 32, "L"),
         st(True, False, True, "organization:o1"), "manual"),
        ("本级true 被上级锁成false", k("k9", 15, "M"),
         st(True, True, False, "organization:o1"), "manual"),
        ("本级缺失 被上级阻断", k("k10", 21, "N"),
         st(False, None, False, "organization:o1", blocked=True,
            blocked_by="organization:o1"), "manual"),
        ("blocked 但本级与生效均正确", k("k11", 20, "O"),
         st(True, False, False, "provider_key:k11", blocked=True,
            blocked_by="organization:o1"), "none"),
    ]
    for title, key, state, want in cases:
        r = row(key, state)
        check("%s priority=%s 判定=%s 期望=%s（%s）" % (
            title, key["priority"], r["fix"], want, r["note"]), r["fix"] == want)
    blocked_row = row(k("k10", 21, "N"), st(False, None, False, "organization:o1",
                                            blocked=True, blocked_by="organization:o1"))
    check("blocked 提示含阻断且不留需写", "阻断" in blocked_row["note"]
          and blocked_row["fix"] == "manual")

    global cchp
    old_cchp = cchp
    seen = {}

    def fake_cchp(args, body=None, run=subprocess.run):
        seen["args"], seen["body"] = list(args), body
        return {"ok": True}, 0

    cchp = fake_cchp
    try:
        r_true = row(k("b1", 15, "P"), st(False, None, False, "organization:o1"))
        _o, _rc, body, action, scope = write_one(r_true, False)
        check("写 true：values 明确布尔且不移除覆盖",
              body == '{"values":{"session.reuse_enabled":true}}'
              and action == "设本级 true" and "removeKeys" not in body
              and seen["body"] == body and "--allow-write" in seen["args"]
              and "--body-file" in seen["args"] and scope == "provider_key:b1")
        r_false = row(k("b2", 20, "Q"), st(False, None, False, "organization:o1"))
        _o, _rc, body, action, scope = write_one(r_false, False)
        check("写 false：values 明确布尔且不移除覆盖",
              body == '{"values":{"session.reuse_enabled":false}}'
              and action == "设本级 false" and "removeKeys" not in body
              and seen["body"] == body and scope == "provider_key:b2")
        seen.clear()
        write_one(r_false, True)
        check("dry-run 传 --dry-run 且仍走 values", "--dry-run" in seen["args"]
              and '"session.reuse_enabled":false' in seen["body"])
    finally:
        cchp = old_cchp
    kept, skipped = skip_revoked([
        {"id": "r1", "priority": 51, "name": "R", "status": "active",
         "revoked_at": "2026-11-01T00:00:00Z"},
        {"id": "r2", "priority": 52, "name": "S", "status": "revoked"},
        {"id": "r3", "priority": 53, "name": "T", "status": "active"},
    ])
    check("撤销跳过 保留=%s 跳过=%d 期望=['r3']/2" % ([x["id"] for x in kept], skipped),
          [x["id"] for x in kept] == ["r3"] and skipped == 2)

    # 失败分类：先看退出码；非零时即使 ok=true 也不得成功。
    for obj, rc, want in ((None, 2, "command_failed"), ({"ok": True}, 1, "command_failed"),
                          (None, 0, "output_not_json"), ({"ok": False}, 0, "api_failed"),
                          ({"ok": "yes"}, 0, "api_failed"), ({"ok": True}, 0, None)):
        check("结果分类 rc=%r -> %s" % (rc, want), result_error(obj, rc) == want)

    marker = "SYNTHETIC_STDERR_MARKER"

    class Fake:
        def __init__(self, stdout, rc):
            self.stdout, self.returncode, self.stderr = stdout, rc, marker + "\n"

    code, out, err = capture(lambda: api(["api", "listProviderKeyPage", "--json"],
                                         run=lambda *a, **kw: Fake('{"ok": true}', 1)))
    check("读：非零退出码即使 ok=true 也失败且不回显原文",
          code == 3 and "command_failed" in err and "cli_rc=1" in err
          and marker not in out and marker not in err)
    code, out, err = capture(lambda: api(["api", "listProviderKeyPage", "--json"],
                                         run=lambda *a, **kw: Fake("not json", 0)))
    check("读：坏 JSON 失败且不回显原文",
          code == 3 and "output_not_json" in err and "cli_rc=0" in err and marker not in out + err)
    code, out, err = capture(lambda: api(
        ["api", "listProviderKeyPage", "--json"],
        run=lambda *a, **kw: Fake('{"ok": false, "error": {"message": "%s"}}' % marker, 0)))
    check("读：服务失败包固定类别且不回显 error.message",
          code == 3 and "api_failed" in err and "cli_rc=0" in err and marker not in out + err)

    def boom(*args, **kwargs):
        raise OSError("synthetic-boom")

    code, out, err = capture(lambda: api(["api", "listProviderKeyPage", "--json"], run=boom))
    check("执行错误无退出码时固定类别",
          code == 3 and "command_error" in err and "cli_rc=" not in err
          and "synthetic-boom" not in out + err)

    # 写：非零、坏 JSON、失败包都先回读，达到期望才继续；未达期望以 3 停止。
    old_read, old_write = read_state, write_one
    r = row(k("w1", 11, "W"), st(False, None, False, "organization:o1"))
    good = {"local": True, "local_value": True, "effective": True,
            "source": "provider_key:w1", "draft_local": False}
    bad = {"local": False, "local_value": None, "effective": False,
           "source": "organization:o1", "draft_local": False}
    try:
        for label, result in (("非零+ok=true", ({"ok": True}, 1)),
                              ("坏 JSON", (None, 0)),
                              ("失败包", ({"ok": False, "error": {"message": marker}}, 0))):
            read_state = lambda scope, _state=good: dict(_state)
            write_one = lambda r, dry, _result=result: (
                _result[0], _result[1], "{}", "设本级 true", "provider_key:" + r["id"])
            code, out, err = capture(lambda: apply_all([r], False))
            check("写：%s 先回读且达期望则继续" % label,
                  code == 0 and "状态已达期望" in out and marker not in out and marker not in err)
        read_state = lambda scope, _state=bad: dict(_state)
        write_one = lambda r, dry: ({"ok": False, "error": {"message": marker}}, 0, "{}",
                                    "设本级 true", "provider_key:" + r["id"])
        code, out, err = capture(lambda: apply_all([r], False))
        check("写：失败后回读未达期望以 3 停止且不回显原文",
              code == 3 and "write_unconfirmed" in err and "cli_rc=0" in err
              and marker not in out and marker not in err)
        read_state = lambda scope, _state=good: dict(_state)
        write_one = lambda r, dry: ({"ok": True}, 1, "{}", "设本级 true", "provider_key:" + r["id"])
        code, out, err = capture(lambda: apply_all([r], True))
        check("dry-run：非零退出码明确失败",
              code == 3 and "dry-run 失败[command_failed]" in out and "cli_rc=1" in out
              and marker not in out + err)
        read_state = lambda scope, _state=good: dict(_state)
        write_one = lambda r, dry: ({"ok": "yes", "error": {"message": marker}}, 0, "{}",
                                    "设本级 true", "provider_key:" + r["id"])
        code, out, err = capture(lambda: apply_all([r], False))
        check("写：ok 非 True 判失败且输出本地布尔",
              code == 0 and "ok=False" in out and "ok=yes" not in out and "api_failed" in out
              and marker not in out + err)
    finally:
        read_state, write_one = old_read, old_write

    print("self-test %s" % ("通过" if not fail else "失败 %d 项" % fail))
    return 0 if not fail else 1


def main():
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(HELP)
        return 0
    known = {"--apply", "--dry-run", "--self-test"}
    unknown = [a for a in argv if a not in known]
    if unknown:
        diag("bad_args", 2)
    if "--self-test" in argv:
        return self_test()
    if "--apply" in argv and "--dry-run" in argv:
        diag("bad_args", 2)
    global ENV
    try:
        ENV = make_env()
        dry_only = "--dry-run" in argv
        rows = collect()
        bad = print_table(rows, "\n会话复用核对（只读，来自已发布配置）：")
        if "--apply" not in argv and not dry_only:
            return 1 if bad else 0
        rc = apply_all(rows, dry_only)
        if rc == 3 or dry_only:
            return rc
        bad = print_table(collect(), "\n写后回读：")
        return 1 if bad else 0
    except (KeyError, TypeError, ValueError):
        diag("bad_shape", 3)


if __name__ == "__main__":
    sys.exit(main())

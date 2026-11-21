#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CCHP 会话复用（session.reuse_enabled）核对与对齐工具。

约定：仅优先级十位为 1（priority//10 == 1）的 provider key 在 provider_key 作用域
设本级 session.reuse_enabled=true；其余 key 移除本级覆盖、继承上级，且生效值须为 false。

用法：
  cchp-session-reuse.py              只读核对，输出对比表；全部一致退出码 0，有不一致 1
  cchp-session-reuse.py --dry-run    只读核对 + 打印将要发送的写请求（不发送）
  cchp-session-reuse.py --apply      仅改“本级不符”的项，逐项回读；改后一致退出码 0
  cchp-session-reuse.py --self-test  用伪造数据验证判定逻辑（不联网、不写）
  cchp-session-reuse.py -h|--help    打印简短用法并退出，不读环境变量

判定三类：一致；需写（本级覆盖与期望不符，本工具可改）；需人工（本级已符合但生效值
不符，例如上级开启或锁定，本工具写入无效）。有需人工项时退出码 1。

列表只取一页（--limit 100）：partial/preparing 为 true 或仍有 nextCursor 时报错退出，
不在不完整列表上读写；已撤销（revoked_at 非空或 status=revoked）的 key 跳过并计数。

凭据：只从环境变量 CCHP_GATEWAY_URL / CCHP_TOKEN 取，经子进程环境传给 cchp，
      不进命令行、不读保存态或文件、不写临时文件（body 走 --body-file - 的 stdin）。
范围：只读/写 session.reuse_enabled 这一个配置键；ID 全部由接口动态取得。
"""
import json
import os
import subprocess
import sys

KEY = "session.reuse_enabled"
GROUP_TENS = 1
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

约定：优先级十位为 1（priority//10 == 1，即 10–19）的 key 本级开启 session.reuse_enabled，
其余移除本级覆盖、继承组织（关闭）；写入走 saveSystemConfig，须用户明确授权。"""


def die(msg, code=2):
    print("错误：" + msg, file=sys.stderr)
    sys.exit(code)


def make_env():
    missing = [n for n in ("CCHP_GATEWAY_URL", "CCHP_TOKEN") if not os.environ.get(n)]
    if missing:
        die("缺少环境变量 " + "、".join(missing))
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
        "LC_ALL": "C.UTF-8",
        "CCHP_BASE_URL": os.environ["CCHP_GATEWAY_URL"],
        "CCHP_TOKEN": os.environ["CCHP_TOKEN"],
    }


def cchp(args, body=None):
    """调用 cchp，返回 (结果对象或 None, 退出码, stderr 首行)；非 JSON 时对象为 None。"""
    p = subprocess.run(["cchp"] + args, input=body, capture_output=True, text=True, env=ENV)
    first = (p.stderr.strip().splitlines() or [""])[0]
    try:
        return json.loads(p.stdout), p.returncode, first
    except ValueError:
        return None, p.returncode, first


def api(args, body=None):
    """只读调用：任何失败都终止。"""
    o, rc, first = cchp(args, body)
    if o is None:
        die("cchp 输出不是 JSON（退出码 %s）：%s" % (rc, first), 3)
    if not o.get("ok"):
        err = o.get("error") or {}
        die("接口失败 %s：%s %s（request_id=%s）" % (
            args[1], err.get("kind"), err.get("message"), o.get("request_id")), 3)
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
    d = api(["api", "listProviderKeyPage", "--limit", "100", "--json"])["data"]
    unready = [n for n in ("partial", "preparing") if d.get(n)]
    if unready:
        die("列表未就绪（%s=true），不在不完整列表上读写。" % "、".join(unready), 3)
    if d.get("nextCursor"):
        die("key 超过一页，工具未支持翻页。", 3)
    keys, skipped = skip_revoked(d["keys"])
    if skipped:
        print("跳过已撤销 key %d 个（revoked_at 非空或 status=revoked）。" % skipped)
    keys.sort(key=lambda k: (k["priority"], k["name"]))
    return keys


def read_state(scope):
    o = api(["api", "getConfigM2Page", "--scope-key", scope, "--prefix", KEY, "--json"])
    for f in o["data"]["fields"]:
        if f.get("key") == KEY:
            return {
                "local": bool(f.get("has_published_local_assignment")),
                "local_value": f.get("published_local_value"),
                "effective": f.get("effective_value"),
                "source": f.get("source_scope_key"),
                "draft_local": bool(f.get("has_draft_local_assignment")),
            }
    die("scope %s 未返回 %s" % (scope, KEY), 3)


def want_local(priority):
    return priority // 10 == GROUP_TENS


def row(key, st):
    wl = want_local(key["priority"])
    want_eff = True if wl else False
    local_ok = (st["local"] == wl) and (not wl or st["local_value"] is True)
    eff_ok = st["effective"] == want_eff
    if local_ok and eff_ok:
        fix, note = "none", "一致"
    elif local_ok:
        fix = "manual"
        if wl:
            note = "需人工：本级已设 true，生效仍为 false（上级锁定或阻止）"
        else:
            note = "需人工：本级无覆盖，生效仍为 true（来源 %s）" % (st["source"] or "未知")
    else:
        fix = "local"
        note = "需写：设本级 true" if wl else "需写：移除本级覆盖"
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
        "want_local": wl,
        "want_eff": want_eff,
        "ok": fix == "none",
        "fix": fix,
        "note": note,
    }


def state_ok(cur, r):
    local_ok = (cur["local"] == r["want_local"]) and (
        not r["want_local"] or cur["local_value"] is True)
    return local_ok and cur["effective"] == r["want_eff"]


def fmt_bool(v):
    if v is True:
        return "true"
    if v is False:
        return "false"
    return "null"


def fmt_local(r):
    return fmt_bool(r["local_value"]) if r["local"] else "（无）"


def fmt_want(r):
    if r["want_local"]:
        return "本级=true 生效=true"
    return "无本级 生效=false"


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
    org = sorted({"%s=%s" % (r["source"], fmt_bool(r["effective"]))
                  for r in rows if not r["local"] and str(r["source"]).startswith("organization:")})
    print("键=%s 分组=priority//10==%d 组织继承=%s" % (
        KEY, GROUP_TENS, "，".join(org) or "（无，按 false 判定）"))
    return rows


def write_one(r, dry_run):
    scope = "provider_key:" + r["id"]
    if r["want_local"]:
        body = json.dumps({"values": {KEY: True}}, separators=(",", ":"))
        action = "设本级 true"
    else:
        body = json.dumps({"removeKeys": [KEY]}, separators=(",", ":"))
        action = "移除本级覆盖"
    args = ["api", "saveSystemConfig", "--scope", scope, "--body-file", "-",
            "--allow-write", "--confirm", "saveSystemConfig"]
    if dry_run:
        args.append("--dry-run")
    args.append("--json")
    o, rc, first = cchp(args, body)
    return o, rc, first, body, action, scope


def apply_all(rows, dry_run):
    writable = [r for r in rows if r["fix"] == "local"]
    manual = [r for r in rows if r["fix"] == "manual"]
    if manual:
        print("需人工 %d 项（本级已符合、生效值不符，本工具写入无效）：%s" % (
            len(manual), "、".join("%s(%s)" % (r["name"], r["priority"]) for r in manual)),
            file=sys.stderr)
    if not writable:
        if manual:
            return 1
        print("无偏差，不写入。")
        return 0
    if any(r["draft_local"] for r in writable):
        print("存在未发布草稿（has_draft_local_assignment=true），按约定停止，不写入。",
              file=sys.stderr)
        return 3
    for i, r in enumerate(writable, 1):
        scope = "provider_key:" + r["id"]
        if read_state(scope)["draft_local"]:
            print("变更 #%d 前发现未发布草稿（%s），停止。" % (i, scope), file=sys.stderr)
            return 3
        o, rc, first, body, action, scope = write_one(r, dry_run)
        label = "变更 #%d %s（%s）%s" % (i, r["name"], r["priority"], action)
        if dry_run:
            if o is None:
                print("%s -> dry-run 调用未返回 JSON（退出码 %s）：%s" % (label, rc, first))
                return 3
            if not o.get("ok"):
                err = o.get("error") or {}
                print("%s -> dry-run 失败 %s：%s" % (label, err.get("kind"), err.get("message")))
                return 3
            req = o.get("dry_run") or {}
            print("%s\n  scope=%s body=%s\n  method=%s path=%s" % (
                label, scope, body, req.get("method"), req.get("path")))
            continue
        print("%s\n  scope=%s operation=saveSystemConfig ok=%s status=%s request_id=%s outcome=%s body=%s" % (
            label, scope, o.get("ok") if o else None, o.get("status") if o else None,
            o.get("request_id") if o else "-", (o or {}).get("outcome", "-"), body))
        if o is None or not o.get("ok"):
            if o is None:
                print("  写调用未返回 JSON（退出码 %s）：%s" % (rc, first))
            else:
                err = o.get("error") or {}
                print("  失败：%s %s" % (err.get("kind"), err.get("message")))
            cur = read_state(scope)
            print("  重读：本级覆盖=%s 本级值=%s 生效值=%s 来源=%s" % (
                cur["local"], fmt_bool(cur["local_value"]), fmt_bool(cur["effective"]),
                cur["source"]))
            if state_ok(cur, r):
                print("  状态已达期望，继续后续项。")
                continue
            print("  状态未达期望，停止（不重试未知结果的写）。", file=sys.stderr)
            return 3
        cur = read_state(scope)
        ok = state_ok(cur, r)
        print("  回读：本级覆盖=%s 本级值=%s 生效值=%s 来源=%s -> %s" % (
            cur["local"], fmt_bool(cur["local_value"]), fmt_bool(cur["effective"]),
            cur["source"], "一致" if ok else "不一致"))
        if not ok:
            print("  回读未达期望，停止。", file=sys.stderr)
            return 3
    if dry_run:
        print("dry-run 结束：未发送任何写请求。")
        return 1 if manual else 0
    if manual:
        print("本级不符项已处理；剩余需人工项见上表。", file=sys.stderr)
        return 1
    return 0


def self_test():
    def k(i, p, n, s="active"):
        return {"id": i, "priority": p, "name": n, "status": s}

    def st(local, val, eff, src, draft=False):
        return {"local": local, "local_value": val, "effective": eff,
                "source": src, "draft_local": draft}

    cases = [
        ("十位为1 本级true 生效true", k("k1", 11, "A"),
         st(True, True, True, "provider_key:k1"), "none"),
        ("其余 无本级 继承组织false", k("k2", 31, "B"),
         st(False, None, False, "organization:o1"), "none"),
        ("停用未撤销 无本级 生效false", k("k3", 43, "C", "disabled"),
         st(False, None, False, "organization:o1"), "none"),
        ("十位非1 留着本级true", k("k4", 23, "D"),
         st(True, True, True, "provider_key:k4"), "local"),
        ("十位为1 无本级", k("k5", 12, "E"),
         st(False, None, False, "organization:o1"), "local"),
        ("本级有覆盖但值为false", k("k6", 14, "F"),
         st(True, False, False, "provider_key:k6"), "local"),
        ("无本级 组织改成true", k("k7", 21, "G"),
         st(False, None, True, "organization:o1"), "manual"),
        ("本级true 被上级锁成false", k("k8", 15, "H"),
         st(True, True, False, "provider_key:k8"), "manual"),
    ]
    fail = 0
    for title, key, state, want in cases:
        r = row(key, state)
        got = r["fix"]
        if got != want:
            fail += 1
        print("%s %s priority=%s 本级=%s 生效=%s 判定=%s 期望=%s（%s）" % (
            "OK" if got == want else "FAIL", title, key["priority"],
            fmt_local(r), fmt_bool(state["effective"]), got, want, r["note"]))
    kept, skipped = skip_revoked([
        {"id": "r1", "priority": 51, "name": "R", "status": "active",
         "revoked_at": "2026-11-01T00:00:00Z"},
        {"id": "r2", "priority": 52, "name": "S", "status": "revoked"},
        {"id": "r3", "priority": 53, "name": "T", "status": "active"},
    ])
    rev_ok = [x["id"] for x in kept] == ["r3"] and skipped == 2
    if not rev_ok:
        fail += 1
    print("%s 撤销跳过 保留=%s 跳过=%d 期望=['r3']/2" % (
        "OK" if rev_ok else "FAIL", [x["id"] for x in kept], skipped))
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
        die("未知参数 %s（可用：%s；用 --help 查看用法）" % (" ".join(unknown), " ".join(sorted(known))))
    if "--self-test" in argv:
        return self_test()
    if "--apply" in argv and "--dry-run" in argv:
        die("--apply 与 --dry-run 不能同时使用")
    global ENV
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


if __name__ == "__main__":
    sys.exit(main())

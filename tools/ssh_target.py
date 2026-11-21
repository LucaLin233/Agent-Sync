#!/usr/bin/env python3
"""lh-collect / lh-deploy 共用的严格 target.json 解析（非秘密、仅内存）。

根键固定 `ssh`/`postgres`。`ssh` 必填 `host`、`knownHostsFile`；`user`、`port`
可省略，省略时按字段补 Agent-Sync 自有的默认 SSH 用户与端口，显式合法值原样保留。
`postgres` 四项仍全部显式。未知/重复键、控制字符、类型或范围不符均抛 TargetError，
由调用方映射为既有 `bad_target`/rc2。解析结果不回显、不落盘。
"""
import json
import os
import re

DEFAULT_SSH_USER = "root"
DEFAULT_SSH_PORT = 9399
NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
HOST_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9.-]{0,252}\Z")
USER_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]{0,31}\Z")


class TargetError(ValueError):
    """目标 JSON 违反固定契约；消息不携带输入值。"""


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise TargetError()
        out[key] = value
    return out


def _text(value):
    return isinstance(value, str) and bool(value) and all(
        ord(ch) >= 0x21 and ord(ch) != 0x7f for ch in value)


def parse(raw):
    """解析原始 stdin bytes，返回补默认值后的新 dict；不修改输入。"""
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (ValueError, UnicodeError):
        raise TargetError() from None
    if not isinstance(doc, dict) or set(doc) != {"ssh", "postgres"}:
        raise TargetError()
    ssh, pg = doc["ssh"], doc["postgres"]
    if not isinstance(ssh, dict) or not set(ssh) <= {"host", "port", "user", "knownHostsFile"}:
        raise TargetError()
    if "host" not in ssh or "knownHostsFile" not in ssh:
        raise TargetError()
    if not isinstance(pg, dict) or set(pg) != {"container", "database", "port", "user"}:
        raise TargetError()
    for node in (ssh, pg):
        for value in node.values():
            if isinstance(value, str) and not _text(value):
                raise TargetError()
    if not isinstance(ssh["host"], str) or not HOST_RE.match(ssh["host"]):
        raise TargetError()
    if not isinstance(ssh["knownHostsFile"], str) \
            or not ssh["knownHostsFile"].startswith("/") \
            or not NAME_RE.match(os.path.basename(ssh["knownHostsFile"])):
        raise TargetError()
    port = ssh.get("port", DEFAULT_SSH_PORT)
    if type(port) is not int or not 1 <= port <= 65535:
        raise TargetError()
    user = ssh.get("user", DEFAULT_SSH_USER)
    if not isinstance(user, str) or not USER_RE.match(user):
        raise TargetError()
    if type(pg["port"]) is not int or not 1 <= pg["port"] <= 65535:
        raise TargetError()
    for key in ("container", "database", "user"):
        if not isinstance(pg[key], str) or not USER_RE.match(pg[key]):
            raise TargetError()
    return {
        "ssh": {"host": ssh["host"], "port": port, "user": user,
                "knownHostsFile": ssh["knownHostsFile"]},
        "postgres": {"container": pg["container"], "database": pg["database"],
                     "port": pg["port"], "user": pg["user"]},
    }

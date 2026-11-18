#!/usr/bin/env python3
"""宿主端安装：默认列计划，--apply 安装，--check 回读；不读取登录态或配置凭据。"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

import yaml

ENDS = ("claude-code", "codex", "paseo")
ROLE_DESCRIPTIONS = {
    "lens": "LUNO 体系的 LENS：审查、规划、验收及所有领域的制稿与改稿。仅在负责人按 luno-core 派发时使用。",
    "forge": "LUNO 体系的 FORGE：实施、修复、取证及必要的规划与自验。仅在负责人按 luno-core 派发时使用。",
}


class InstallError(Exception):
    def __init__(self, code, path):
        self.code, self.path = code, str(path)


def home_path(value, home):
    """登记只使用 HOME 相对路径，不把调用方传来的 ~ 当成其他用户目录。"""
    if not value.startswith("~/") or any(p in ("", ".", "..") for p in value[2:].split("/")):
        raise InstallError("invalid_destination", value)
    return home / value[2:]


def git_value(checkout, *args):
    proc = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(checkout), *args],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        timeout=30)
    if proc.returncode:
        raise InstallError("checkout_git_error", checkout)
    return proc.stdout.decode("utf-8").strip()


def import_line(path):
    value = str(path)
    return "@" + (json.dumps(value, ensure_ascii=False) if any(c.isspace() for c in value) else value)


def text_bytes(path):
    raw = path.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        raise InstallError("invalid_utf8", path) from None
    return raw


def render(obj, renderer, checkout, home):
    source = checkout / obj["source"]
    if renderer == "claude-main":
        content = (import_line(source) + "\n@~/.luno/memory/GLOBAL.md\n").encode("utf-8")
        return home / ".luno/generated/claude-code/CLAUDE.md", content
    if renderer == "codex-main":
        memory = home / ".luno/memory/GLOBAL.md"
        if memory.is_symlink() or not memory.is_file():
            raise InstallError("missing_global_copy", memory)
        return home / ".luno/generated/codex/AGENTS.md", text_bytes(source) + b"\n" + text_bytes(memory)
    if renderer == "claude-role":
        role = source.stem.lower()
        header = ("---\nname: " + role + "\ndescription: "
                  + json.dumps(ROLE_DESCRIPTIONS[role], ensure_ascii=False)
                  + "\nskills: [luno-core]\nomitClaudeMd: true\n---\n\n")
        return home / (".luno/generated/claude-code/agents/" + role + ".md"), header.encode("utf-8") + text_bytes(source)
    raise InstallError("unknown_renderer", source)


def link_matches(path, target):
    return path.is_symlink() and os.readlink(path) == str(target)


def state(action):
    path = action["path"]
    if action["kind"] == "directory":
        if path.is_symlink():
            return "conflict"
        return "match" if path.is_dir() else "conflict" if path.exists() else "create"
    if action["kind"] == "link":
        if link_matches(path, action["target"]):
            return "match"
        return "conflict" if os.path.lexists(path) else "create"
    if not os.path.lexists(path):
        return "create"
    if path.is_symlink() or not path.is_file():
        return "conflict"
    if path.read_bytes() == action["content"] and stat.S_IMODE(path.stat().st_mode) == 0o600:
        return "match"
    # 只有公开入口已经指向本生成文件时，才把它当作可重新生成的受管文件。
    return "update" if any(link_matches(p, path) for p in action["public"]) else "conflict"


def duplicate_skills(home, names):
    legacy = home / ".codex/skills"
    errors = []
    for path in sorted(legacy.glob("*/SKILL.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != "---":
            continue
        try:
            end = lines.index("---", 1)
        except ValueError:
            continue
        try:
            metadata = yaml.safe_load("\n".join(lines[1:end]))
        except yaml.YAMLError:
            raise InstallError("invalid_legacy_skill_metadata", path) from None
        name = metadata.get("name") if isinstance(metadata, dict) else None
        if isinstance(name, str) and name in names:
            errors.append({"code": "duplicate_skill_name", "path": str(path), "name": name})
    return errors


def plan(checkout, home):
    registry = json.loads((checkout / "tools/sync-targets.json").read_text(encoding="utf-8"))
    if registry["schemaVersion"] != 1:
        raise InstallError("unsupported_registry_version", checkout / "tools/sync-targets.json")
    actions, errors = [], []
    skill_names = {o["id"] for o in registry["objects"] if o["type"] == "skill"}
    errors.extend(duplicate_skills(home, skill_names))
    for obj in registry["objects"]:
        source = checkout / obj["source"]
        if not source.is_file():
            raise InstallError("source_missing", source)
        for end in ENDS:
            target = obj["ends"][end]
            if not target["present"]:
                continue
            destinations = [home_path(p, home) for p in target["paths"]]
            if target["kind"] == "generated":
                try:
                    artifact, content = render(obj, target["renderer"], checkout, home)
                except InstallError as exc:
                    errors.append({"code": exc.code, "path": exc.path, "object": obj["id"], "end": end})
                    continue
                actions.append({"object": obj["id"], "end": end, "kind": "generated",
                                "path": artifact, "content": content, "public": destinations})
                link_target = artifact
            elif target["kind"] == "link":
                link_target = source.parent if obj["type"] == "skill" else source
            else:
                raise InstallError("invalid_end_kind", source)
            for destination in destinations:
                actions.append({"object": obj["id"], "end": end, "kind": "link",
                                "path": destination, "target": link_target})
    # 在写入前检查全部父目录；不跟随用户已有的目录软链写到其他位置。
    parents = set()
    for action in actions:
        path = action["path"].parent
        while path != home:
            parents.add(path)
            path = path.parent
    directories = [{"kind": "directory", "path": p} for p in sorted(parents, key=lambda p: (len(p.parts), str(p)))]
    actions = directories + actions
    for action in actions:
        action["state"] = state(action)
        if action["state"] == "conflict":
            errors.append({"code": "path_conflict", "path": str(action["path"])})
    return actions, errors


def write_generated(action):
    path = action["path"]
    fd, name = tempfile.mkstemp(prefix=".link-install-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(action["content"])
        if action["state"] == "create":
            os.link(temporary, path)       # 排他创建；不覆盖预检后新出现的占位文件。
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply(actions):
    for action in actions:
        current = state(action)
        if current == "conflict":
            raise InstallError("path_conflict", action["path"])
        if current == "match":
            continue
        action["state"] = current
        if action["kind"] == "directory":
            action["path"].mkdir(mode=0o700)
        elif action["kind"] == "link":
            action["path"].symlink_to(action["target"])
        else:
            write_generated(action)


def public_action(action):
    return {key: str(value) if isinstance(value, Path) else value for key, value in action.items()
            if key not in ("content", "public")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[1])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    report = {"schemaVersion": 1, "mode": "apply" if args.apply else "check" if args.check else "plan",
              "actions": [], "errors": []}
    try:
        if not args.checkout.is_absolute():
            raise InstallError("checkout_must_be_absolute", args.checkout)
        checkout, home = args.checkout.resolve(), Path.home().resolve()
        report.update(checkout=str(checkout), head=git_value(checkout, "rev-parse", "HEAD"),
                      trackedState="dirty" if git_value(checkout, "status", "--porcelain") else "clean")
        actions, errors = plan(checkout, home)
        report["actions"] = [public_action(a) for a in actions]
        report["errors"] = errors
        if errors:
            report["status"], code = "blocked", 2
        elif args.apply:
            apply(actions)
            actions, errors = plan(checkout, home)
            report["actions"] = [public_action(a) for a in actions]
            report["errors"] = errors
            matched = not errors and all(a["state"] == "match" for a in actions)
            report["status"], code = ("completed", 0) if matched else ("different", 1)
        elif args.check:
            matched = all(a["state"] == "match" for a in actions)
            report["status"], code = ("match", 0) if matched else ("different", 1)
        else:
            report["status"], code = "planned", 0
    except InstallError as exc:
        report["status"] = "blocked"
        report["errors"].append({"code": exc.code, "path": exc.path})
        code = 2
    except (OSError, ValueError, KeyError) as exc:
        report["status"] = "error"
        report["errors"].append({"code": "install_error", "errorType": type(exc).__name__})
        code = 2
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())

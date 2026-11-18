#!/usr/bin/env python3
"""宿主端安装：默认列计划，--apply 安装，--check 回读；不读取登录态或配置凭据。"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import yaml

ENDS = ("claude-code", "codex", "paseo")
ROLE_DESCRIPTIONS = {
    "lens": "LUNO 体系的 LENS：审查、规划、验收及所有领域的制稿与改稿。仅在负责人按 luno-core 派发时使用。",
    "forge": "LUNO 体系的 FORGE：实施、修复、取证及必要的规划与自验。仅在负责人按 luno-core 派发时使用。",
}


class InstallError(Exception):
    def __init__(self, code, path):
        self.code, self.path = code, str(path)


class HomeTree:
    """HOME 的目录 fd 链；用户目录只经已核父 fd 读取或写入。"""
    def __init__(self, home):
        if not home.is_absolute():
            raise InstallError("home_must_be_absolute", home)
        self.home = home
        self.fds = {Path("/"): os.open("/", os.O_RDONLY | os.O_DIRECTORY)}
        if self.directory(home) is None:
            raise InstallError("home_missing", home)

    def close(self):
        for fd in reversed(list(self.fds.values())):
            os.close(fd)

    def directory(self, path, create=False):
        if path in self.fds:
            if path != Path("/"):
                parent = self.directory(path.parent)
                info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                held = os.fstat(self.fds[path])
                if (info.st_dev, info.st_ino) != (held.st_dev, held.st_ino):
                    raise InstallError("parent_changed", path)
            return self.fds[path]
        parent = self.directory(path.parent, create)
        if parent is None:
            return None
        if create:
            os.mkdir(path.name, mode=0o700, dir_fd=parent)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        except FileNotFoundError:
            return None
        except OSError:
            raise InstallError("unsafe_parent", path) from None
        self.fds[path] = fd
        return fd

    def stat(self, path):
        parent = self.directory(path.parent)
        if parent is None:
            return None
        try:
            return os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return None

    def read(self, path):
        parent = self.directory(path.parent)
        if parent is None:
            raise InstallError("file_missing", path)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise InstallError("not_regular_file", path)
            return stream.read()

    def link_matches(self, path, target):
        info = self.stat(path)
        return info is not None and stat.S_ISLNK(info.st_mode) and os.readlink(
            path.name, dir_fd=self.directory(path.parent)) == str(target)

    def unlink(self, path):
        os.unlink(path.name, dir_fd=self.directory(path.parent))


def home_path(value, home):
    """登记只使用 HOME 相对路径，不把调用方传来的 ~ 当成其他用户目录。"""
    if not value.startswith("~/") or any(p in ("", ".", "..") for p in value[2:].split("/")):
        raise InstallError("invalid_destination", value)
    return home / value[2:]


def git_bytes(checkout, *args):
    proc = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(checkout), *args],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        timeout=30)
    if proc.returncode:
        raise InstallError("checkout_git_error", checkout)
    return proc.stdout


def git_value(checkout, *args):
    return git_bytes(checkout, *args).decode("utf-8").strip()


def revision_reader(checkout, revision):
    commit = git_value(checkout, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}")
    return commit, lambda path: git_bytes(checkout, "show", commit + ":" + str(path.relative_to(checkout)))


def import_line(path):
    value = str(path)
    return "@" + (json.dumps(value, ensure_ascii=False) if any(c.isspace() for c in value) else value)


def text_bytes(path, read=Path.read_bytes):
    raw = read(path)
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        raise InstallError("invalid_utf8", path) from None
    return raw


def private_file(info):
    return stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600


STAGING_SUFFIX = ".link-install.tmp"


def staging_path(action):
    """本次运行独占的暂存名：同目录、随机后缀，只能由排他创建得到。"""
    token = os.urandom(8).hex()
    return action["path"].with_name("." + action["path"].name + STAGING_SUFFIX + "." + token)


def staging_residue(actions, tree):
    """只按前缀报告暂存残留，不判断也不清理其归属。

    同 UID 加 0600 不证明归属，旧版安装器使用的固定名也在此列；残留一律交用户核对后处置。
    """
    residue, seen = [], set()
    for action in actions:
        if action["kind"] != "generated":
            continue
        parent = tree.directory(action["path"].parent)
        if parent is None:
            continue
        prefix = "." + action["path"].name + STAGING_SUFFIX
        for name in sorted(os.listdir(parent)):
            path = action["path"].with_name(name)
            if name.startswith(prefix) and str(path) not in seen:
                seen.add(str(path))
                residue.append(str(path))
    return residue


def render(obj, renderer, checkout, home, tree, read):
    source = checkout / obj["source"]
    if renderer == "claude-main":
        content = (import_line(source) + "\n@~/.luno/memory/GLOBAL.md\n").encode("utf-8")
        return home / ".luno/generated/claude-code/CLAUDE.md", content
    if renderer == "codex-main":
        memory = home / ".luno/memory/GLOBAL.md"
        info = tree.stat(memory)
        if info is None or not stat.S_ISREG(info.st_mode):
            raise InstallError("missing_global_copy", memory)
        return home / ".luno/generated/codex/AGENTS.md", text_bytes(source, read) + b"\n" + text_bytes(memory, tree.read)
    if renderer == "claude-role":
        role = source.stem.lower()
        header = ("---\nname: " + role + "\ndescription: "
                  + json.dumps(ROLE_DESCRIPTIONS[role], ensure_ascii=False)
                  + "\nskills: [luno-core]\nomitClaudeMd: true\n---\n\n")
        return home / (".luno/generated/claude-code/agents/" + role + ".md"), header.encode("utf-8") + text_bytes(source, read)
    raise InstallError("unknown_renderer", source)


def state(action, tree):
    path = action["path"]
    info = tree.stat(path)
    if action["kind"] == "directory":
        if info is None:
            return "create"
        if not stat.S_ISDIR(info.st_mode):
            return "conflict"
        if path.parent == tree.home / ".luno/homes" and (
                info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
            return "conflict"
        return "match"
    if action["kind"] == "link":
        if tree.link_matches(path, action["target"]):
            return "match"
        if "previousTarget" in action and tree.link_matches(path, action["previousTarget"]):
            return "update"
        return "conflict" if info is not None else "create"
    if info is None:
        return "create"
    # 归属先于正文：即使 bytes 相同，没有公开入口指向的旧文件也不是受管文件。
    if not private_file(info) or not any(
            tree.link_matches(p, path) for p in action["public"]):
        return "conflict"
    if tree.read(path) == action["content"]:
        return "match"
    return "update"


def duplicate_skills(home, names, tree):
    legacy = home / ".codex/skills"
    errors = []
    fd = tree.directory(legacy)
    if fd is None:
        return errors
    for name in sorted(os.listdir(fd)):
        path = legacy / name / "SKILL.md"
        info = tree.stat(legacy / name)
        if stat.S_ISLNK(info.st_mode):
            raise InstallError("unsafe_parent", legacy / name)
        if not stat.S_ISDIR(info.st_mode) or tree.stat(path) is None:
            continue
        lines = tree.read(path).decode("utf-8").splitlines()
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


def desired(checkout, home, tree, read):
    registry = json.loads(read(checkout / "tools/sync-targets.json"))
    if registry["schemaVersion"] != 1:
        raise InstallError("unsupported_registry_version", checkout / "tools/sync-targets.json")
    actions, errors = [], []
    skill_names = {o["id"] for o in registry["objects"] if o["type"] == "skill"}
    errors.extend(duplicate_skills(home, skill_names, tree))
    for obj in registry["objects"]:
        source = checkout / obj["source"]
        read(source)
        for end in ENDS:
            # 宿主端登记之前的旧版本没有这些键，按未登记处理；当前检出的显式登记由 check-rules 保证。
            target = obj["ends"].get(end, {"present": False})
            if not target["present"]:
                continue
            destinations = [home_path(p, home) for p in target["paths"]]
            if target["kind"] == "generated":
                try:
                    artifact, content = render(obj, target["renderer"], checkout, home, tree, read)
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
    # 先建公开软链，再写生成文件；软链也是中断后恢复时的归属依据。
    actions = directories + [a for a in actions if a["kind"] == "link"] + [a for a in actions if a["kind"] == "generated"]
    return actions, errors


def plan(checkout, home, tree, read=Path.read_bytes, previous=()):
    actions, errors = desired(checkout, home, tree, read)
    previous_links = {a["path"]: a["target"] for a in previous if a["kind"] == "link"}
    for path in (home / ".codex/AGENTS.override.md", home / ".luno/homes/lens-codex/AGENTS.override.md",
                 home / ".luno/homes/forge-codex/AGENTS.override.md"):
        if tree.stat(path) is not None:
            errors.append({"code": "agents_override_shadowing", "path": str(path)})
    for action in actions:
        if action["kind"] == "link" and action["path"] in previous_links:
            action["previousTarget"] = previous_links[action["path"]]
        action["state"] = state(action, tree)
        if action["state"] == "conflict":
            errors.append({"code": "path_conflict", "path": str(action["path"])})
    return actions, errors


def retirements(previous, current, tree):
    """两版登记的差集；目录可能含登录态，永不因退役删除。

    生成文件的归属在公开软链改指之前核实，并把 inode 记进 identity：改指之后不再靠软链
    现指判断，否则同一入口改指新文件会把旧文件误判成非受管并卡住重跑。
    """
    retained = {a["path"] for a in current}
    retired, errors = [], []
    for action in previous:
        path = action["path"]
        if action["kind"] == "directory" or path in retained or tree.stat(path) is None:
            continue
        if action["kind"] == "link":
            owned = tree.link_matches(path, action["target"])
        else:
            info = tree.stat(path)
            owned = private_file(info) and any(
                tree.link_matches(p, path) for p in action["public"])
            if owned:
                action = dict(action, identity=[info.st_dev, info.st_ino])
        if not owned:
            errors.append({"code": "retired_path_conflict", "path": str(path)})
        else:
            retired.append(action)
    # 先删生成文件，后删证明其归属的公开软链；其余入口按登记顺序。
    retired.sort(key=lambda a: a["kind"] != "generated")
    return retired, errors


def delete_retired(action, tree):
    """删除已核过归属的退役项；文件必须仍是当时核实的那个 inode，否则停止。"""
    path = action["path"]
    info = tree.stat(path)
    if info is None:
        return
    if action["kind"] == "link":
        owned = tree.link_matches(path, action["target"])
    else:
        owned = private_file(info) and [info.st_dev, info.st_ino] == action.get("identity")
    if not owned:
        raise InstallError("retired_path_conflict", path)
    tree.unlink(path)


def retire_before_repoint(actions, retired, tree):
    """改指会切断旧生成文件的归属证据：先按已核 inode 删它，中断后重跑不会撞冲突。

    删除发生在公开软链改指之前，这段窗口内该入口可能悬空，须在维护窗口内暂停新会话。
    """
    moving = {a["path"] for a in actions
              if a["kind"] == "link" and a.get("previousTarget") is not None}
    for action in retired:
        if action["kind"] == "generated" and any(p in moving for p in action["public"]):
            delete_retired(action, tree)


def write_generated(action, tree):
    path = action["path"]
    parent = tree.directory(path.parent)
    temporary = staging_path(action)
    fd = os.open(temporary.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(action["content"])
            handle.flush()
            os.fsync(handle.fileno())
        if action["state"] == "create":
            os.link(temporary.name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        else:
            os.replace(temporary.name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        discard_staging(temporary, parent, created)


def discard_staging(temporary, parent, created):
    """只清本次排他创建的那一个暂存文件：名字已不是它原本的 inode 就不动。"""
    try:
        info = os.stat(temporary.name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (info.st_dev, info.st_ino) == (created.st_dev, created.st_ino):
        os.unlink(temporary.name, dir_fd=parent)


def apply(actions, tree):
    """按计划写入，返回本次实际执行过的项（state=create/update）；未执行的项不列入。"""
    done = []
    for action in actions:
        current = state(action, tree)
        if current == "conflict":
            raise InstallError("path_conflict", action["path"])
        if current == "match":
            continue
        action["state"] = current
        if action["kind"] == "directory":
            tree.directory(action["path"], create=True)
        elif action["kind"] == "link":
            parent = tree.directory(action["path"].parent)
            if current == "create":
                os.symlink(str(action["target"]), action["path"].name, dir_fd=parent)
            else:
                # 改指用同目录临时软链改名替换，链接本身不留缺失态；生成文件改指时旧文件已先退役，见 retire_before_repoint。
                temporary = action["path"].with_name(
                    "." + action["path"].name + ".link-install.tmp." + os.urandom(8).hex())
                os.symlink(str(action["target"]), temporary.name, dir_fd=parent)
                try:
                    os.rename(temporary.name, action["path"].name, src_dir_fd=parent, dst_dir_fd=parent)
                except BaseException:
                    discard_staging(temporary, parent,
                                    os.stat(temporary.name, dir_fd=parent, follow_symlinks=False))
                    raise
        else:
            write_generated(action, tree)
        done.append(action)
    return done


def public_action(action):
    return {key: str(value) if isinstance(value, Path) else value for key, value in action.items()
            if key not in ("content", "public", "identity")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--previous", help="--apply 时清理此本地 Git 版本独有的受管入口；不删除目录或登录态")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--preflight", metavar="TARGET_REV", help="切版本前只读预检本地 Git 目标版本")
    args = parser.parse_args(argv)
    if args.previous and not args.apply:
        parser.error("--previous requires --apply")
    report = {"schemaVersion": 1, "mode": "apply" if args.apply else "check" if args.check else "preflight" if args.preflight else "plan",
              "actions": [], "errors": []}
    try:
        if not args.checkout.is_absolute():
            raise InstallError("checkout_must_be_absolute", args.checkout)
        checkout, home = args.checkout.resolve(), Path.home()
        tree = HomeTree(home)
        report.update(checkout=str(checkout), head=git_value(checkout, "rev-parse", "HEAD"),
                      trackedState="dirty" if git_value(checkout, "status", "--porcelain") else "clean")
        previous, previous_errors = [], []
        if args.previous:
            report["previousHead"], read = revision_reader(checkout, args.previous)
            previous, previous_errors = desired(checkout, home, tree, read)
        actions, errors = plan(checkout, home, tree, previous=previous)
        errors.extend(previous_errors)
        retired = []
        if args.preflight:
            if report["trackedState"] != "clean" or any(a["state"] != "match" for a in actions):
                errors.append({"code": "current_installation_not_clean", "path": str(checkout)})
            report["targetHead"], read = revision_reader(checkout, args.preflight)
            candidate, candidate_errors = plan(checkout, home, tree, read, previous=actions)
            retired, cleanup_errors = retirements(actions, candidate, tree)
            actions = candidate
            errors.extend(candidate_errors + cleanup_errors)
        elif args.previous:
            if report["trackedState"] != "clean":
                errors.append({"code": "checkout_dirty", "path": str(checkout)})
            retired, cleanup_errors = retirements(previous, actions, tree)
            errors.extend(cleanup_errors)
        report["residue"] = staging_residue(actions + previous, tree)
        report["retirements"] = [public_action(a) for a in retired]
        report["actions"] = [public_action(a) for a in actions]
        report["errors"] = errors
        if errors:
            report["status"], code = "blocked", 2
        elif args.apply:
            retire_before_repoint(actions, retired, tree)
            report["created"] = [public_action(a) for a in apply(actions, tree)]
            for action in retired:
                delete_retired(action, tree)
            actions, errors = plan(checkout, home, tree)
            report["actions"] = [public_action(a) for a in actions]
            report["errors"] = errors
            matched = not errors and all(a["state"] == "match" for a in actions)
            report["status"], code = ("completed", 0) if matched else ("different", 1)
        elif args.check:
            matched = all(a["state"] == "match" for a in actions)
            report["status"], code = ("match", 0) if matched else ("different", 1)
        else:
            report["status"], code = "ready" if args.preflight else "planned", 0
    except InstallError as exc:
        report["status"] = "blocked"
        report["errors"].append({"code": exc.code, "path": exc.path})
        code = 2
    except (OSError, ValueError, KeyError) as exc:
        report["status"] = "error"
        report["errors"].append({"code": "install_error", "errorType": type(exc).__name__})
        code = 2
    finally:
        if "tree" in locals():
            tree.close()
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())

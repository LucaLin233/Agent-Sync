#!/usr/bin/env python3
"""宿主端安装：默认列计划，--apply 安装，--check 回读；不读取登录态或配置凭据。"""
import argparse
import json
import os
from pathlib import Path
import re
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


def codex_destination(value, home, codex_home):
    destination = home_path(value, home)
    if codex_home is None:
        return destination
    if value.startswith("~/.codex/"):
        return codex_home / value[len("~/.codex/"):]
    if value.startswith("~/.agents/skills/"):
        return codex_home / "skills" / value[len("~/.agents/skills/"):]
    raise InstallError("unsupported_native_codex_destination", value)


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
        if action["kind"] not in ("generated", "link"):
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


NATIVE_ROLE_RENDERER = "codex-role"
NATIVE_ROLE_KEYS = ("description", "config_file")


def toml_string(value):
    """TOML basic string：只转义必需的字符，保留非 ASCII 与其他字节。"""
    out = []
    for char in value:
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\t":
            out.append("\\t")
        elif char == "\r":
            out.append("\\r")
        else:
            out.append(char)
    return "".join(out)


def render(obj, target, checkout, home, tree, read):
    renderer = target["renderer"]
    source = checkout / obj["source"]
    if renderer == NATIVE_ROLE_RENDERER:
        role = source.stem.lower()
        if role not in ROLE_DESCRIPTIONS:
            raise InstallError("unknown_native_role", source)
        model, effort = target.get("model"), target.get("model_reasoning_effort")
        for value in (model, effort):
            if not isinstance(value, str) or not value:
                raise InstallError("native_role_model_missing", source)
        text = "model = \"" + toml_string(model) + "\"\nmodel_reasoning_effort = \"" + toml_string(effort) \
               + "\"\ndeveloper_instructions = \"" + toml_string(text_bytes(source, read).decode("utf-8")) + "\"\n"
        return None, text.encode("utf-8")
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
        # 首版不支持链接改指：目标不同的既有入口一律冲突，不借旧目标放行。
        return "conflict" if info is not None else "create"
    if action["kind"] == "native-role":
        if info is None:
            return "create"
        if not private_file(info):
            return "conflict"
        content = tree.read(path)
        if content == action["content"]:
            return "match"
        # 只有真实旧文件等于上一登记版本渲染结果时才允许改写，其余漂移一律停止。
        return "update" if content == action.get("prior") else "conflict"
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


def desired(checkout, home, tree, read, baseline=False, ends=ENDS, codex_home=None, priors=None):
    """baseline=True 只用于读取旧基线：整版没有宿主端键时才允许返回空动作。

    当前检出与预检目标都必须证明是完整登记的宿主版本；任一对象缺键或 present 非严格布尔即停止，
    不推导可清理动作，也不把缺键当成退役依据。
    """
    registry_path = checkout / "tools/sync-targets.json"
    registry = json.loads(read(registry_path))
    if registry["schemaVersion"] != 1:
        raise InstallError("unsupported_registry_version", registry_path)
    actions, errors = [], []
    objects = registry["objects"]
    registered = any(end in (obj.get("ends") or {}) for obj in objects for end in ENDS)
    if not registered and not baseline:
        errors.append({"code": "registry_without_host_ends", "path": str(registry_path)})
        return [], errors
    skill_names = {o["id"] for o in objects if o["type"] == "skill"}
    if "codex" in ends and codex_home is None:
        errors.extend(duplicate_skills(home, skill_names, tree))
    for obj in objects:
        source = checkout / obj["source"]
        read(source)
        object_ends = obj.get("ends")
        if not isinstance(object_ends, dict):
            errors.append({"code": "registry_ends_invalid", "path": str(registry_path), "object": obj["id"]})
            continue
        missing = [end for end in ENDS if end not in object_ends]
        if missing:
            if not registered:
                continue  # 只可能是 baseline：整版没有宿主端键，按首装基线处理
            errors.append({"code": "registry_end_missing", "path": str(registry_path), "object": obj["id"]})
            continue
        for end in ENDS:
            target = object_ends[end]
            present = target.get("present") if isinstance(target, dict) else None
            if not isinstance(present, bool):
                errors.append({"code": "registry_end_invalid_present", "path": str(registry_path),
                               "object": obj["id"], "end": end})
                continue
            if not present or end not in ends:
                continue
            destinations = [codex_destination(p, home, codex_home) if end == "codex"
                            else home_path(p, home) for p in target["paths"]]
            if target["kind"] == "generated":
                try:
                    artifact, content = render(obj, target, checkout, home, tree, read)
                except InstallError as exc:
                    errors.append({"code": exc.code, "path": exc.path, "object": obj["id"], "end": end})
                    continue
                if target["renderer"] == NATIVE_ROLE_RENDERER:
                    # 原生角色是单一直接文件：没有公开软链，也不拿旧 generated 的归属证明。
                    if len(destinations) != 1:
                        errors.append({"code": "native_role_paths_invalid", "path": str(registry_path),
                                       "object": obj["id"], "end": end})
                        continue
                    actions.append({"object": obj["id"], "end": end, "kind": "native-role",
                                    "path": destinations[0], "content": content, "public": [],
                                    "prior": (priors or {}).get(str(destinations[0]))})
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


REGISTRATION_LINE = re.compile(r'^([A-Za-z0-9_-]+)[ \t]*=[ \t]*"(.*)"$')


def registration_tables(raw):
    """只切出表头与其行；顶层行和受管表内的语法不清都按无法安全定位处理。"""
    tables = {}
    current = None
    for line in raw.decode("utf-8").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):
            if not stripped.endswith("]") or stripped.startswith("[["):
                raise ValueError
            header = stripped[1:-1].strip()
            current = []
            tables.setdefault(header, []).append(current)
            continue
        if current is not None:
            current.append(stripped)
    return tables


def native_role_registration(tree, codex_home, actions):
    """只读核对两个原生角色的注册：表、字段名/类型、描述与文件末端。

    只核对登记字段名与取值是否等于真源，不取、不输出其他配置项的值。
    """
    errors = []
    config = codex_home / "config.toml"
    try:
        tables = registration_tables(tree.read(config))
    except InstallError as exc:
        return [{"code": "native_role_registration_missing", "path": exc.path}]
    except (UnicodeDecodeError, ValueError):
        return [{"code": "native_role_registration_syntax", "path": str(config)}]
    for action in actions:
        role = Path(action["object"]).stem
        header = "agents." + role
        blocks = tables.get(header) or []
        if not blocks:
            errors.append({"code": "native_role_registration_missing", "path": str(config), "role": role})
            continue
        if len(blocks) > 1:
            errors.append({"code": "native_role_registration_duplicate", "path": str(config), "role": role})
            continue
        fields = {}
        for line in blocks[0]:
            match = REGISTRATION_LINE.match(line)
            if match is None:
                errors.append({"code": "native_role_registration_type", "path": str(config), "role": role})
                break
            key, value = match.group(1), match.group(2)
            if key not in NATIVE_ROLE_KEYS:
                errors.append({"code": "native_role_registration_unknown_key", "path": str(config),
                               "role": role, "key": key})
                continue
            if key in fields:
                errors.append({"code": "native_role_registration_duplicate", "path": str(config), "role": role})
                continue
            fields[key] = value
        if set(fields) != set(NATIVE_ROLE_KEYS):
            errors.append({"code": "native_role_registration_missing_field", "path": str(config), "role": role})
            continue
        if fields["description"] != ROLE_DESCRIPTIONS[role.lower()]:
            errors.append({"code": "native_role_registration_description", "path": str(config), "role": role})
        expected = "roles/" + role.lower() + ".toml"
        if fields["config_file"] != expected:
            errors.append({"code": "native_role_registration_config_file", "path": str(config), "role": role})
            continue
        target = action["path"]
        info = tree.stat(target)
        if info is None or not stat.S_ISREG(info.st_mode) or (codex_home / expected) != target:
            errors.append({"code": "native_role_registration_target", "path": str(config), "role": role})
    return errors


def plan(checkout, home, tree, read=Path.read_bytes, ends=ENDS, codex_home=None, priors=None):
    actions, errors = desired(checkout, home, tree, read, ends=ends, codex_home=codex_home, priors=priors)
    overrides = []
    if "codex" in ends:
        overrides.append((codex_home or home / ".codex") / "AGENTS.override.md")
    if "paseo" in ends:
        overrides.extend(home / (".luno/homes/" + role + "-codex/AGENTS.override.md")
                         for role in ("lens", "forge"))
    for path in overrides:
        if tree.stat(path) is not None:
            errors.append({"code": "agents_override_shadowing", "path": str(path)})
    for action in actions:
        action["state"] = state(action, tree)
        if action["state"] == "conflict":
            errors.append({"code": "path_conflict", "path": str(action["path"])})
        elif action["kind"] == "native-role" and action["state"] == "create":
            # 首次接管不创建角色文件：文件必须已存在且与渲染结果逐字节相等。
            errors.append({"code": "native_role_missing", "path": str(action["path"])})
    native = [a for a in actions if a["kind"] == "native-role"]
    if native:
        if codex_home is None:
            errors.append({"code": "native_role_registration_unavailable", "path": str(home)})
        else:
            errors.extend(native_role_registration(tree, codex_home, native))
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


REGISTRY_ERRORS = ("registry_without_host_ends", "registry_ends_invalid",
                   "registry_end_missing", "registry_end_invalid_present")


def host_registered(read, checkout):
    """显式解析状态：整版是否声明了任一宿主端键。全端显式 false 仍算已声明。"""
    registry = json.loads(read(checkout / "tools/sync-targets.json"))
    return any(end in (obj.get("ends") or {}) for obj in registry["objects"] for end in ENDS)


def registry_invalid(errors):
    return any(e.get("code") in REGISTRY_ERRORS for e in errors)


def compatibility_errors(checkout, other_head, other_read, other_actions, current_actions):
    """首版只支持安装器与登记推导布局都相同的升级/回退；证明不了就在写入前停止。

    安装器自身改变就能改变渲染路径，而两个版本的 action 都由当前安装器算出，比对它们看不出差异；
    所以先要求两份 tools/link-install.py 的 blob 一致，再核登记推导出的共用公开入口精确目标。
    """
    if not host_registered(other_read, checkout):
        return [{"code": "previous_without_host_installation", "path": str(checkout)}]
    try:
        other_blob = git_value(checkout, "rev-parse", other_head + ":tools/link-install.py")
    except InstallError:
        return [{"code": "previous_installer_missing", "path": str(checkout)}]
    if other_blob != git_value(checkout, "rev-parse", "HEAD:tools/link-install.py"):
        return [{"code": "installer_changed", "path": str(checkout)}]
    other_links = {str(a["path"]): str(a["target"]) for a in other_actions if a["kind"] == "link"}
    for action in current_actions:
        if action["kind"] != "link":
            continue
        path = str(action["path"])
        if path in other_links and other_links[path] != str(action["target"]):
            return [{"code": "layout_changed", "path": path}]
    return []


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
            os.symlink(str(action["target"]), action["path"].name,
                       dir_fd=tree.directory(action["path"].parent))
        else:
            write_generated(action, tree)
        done.append(action)
    return done


def public_action(action):
    return {key: str(value) if isinstance(value, Path) else value for key, value in action.items()
            if key not in ("content", "public", "identity")}


def git_is_ancestor(checkout, ancestor, descendant):
    proc = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(checkout),
         "merge-base", "--is-ancestor", ancestor, descendant],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=30)
    return proc.returncode == 0


ADOPTION_SOURCES = ("skills", "subagents", "prompt")


def registry_native_present(raw):
    registry = json.loads(raw)
    return {obj["id"]: bool((obj.get("ends") or {}).get("codex", {}).get("present"))
            for obj in registry["objects"] if obj["id"] in ("subagents/LENS.md", "subagents/FORGE.md")}


def native_role_adoption(checkout, home, tree, target, codex_home):
    """只读准入：用 N 的算法与 N 的 Git reader 对同一实际目标根算计划并核新增范围。

    不写文件、不 fetch、不切版本；O 侧的真实 check 由 O 自己的安装器另行运行，作为外部证据。
    """
    errors = []
    commit, read = revision_reader(checkout, target)
    if not git_is_ancestor(checkout, "HEAD", commit):
        errors.append({"code": "target_not_descendant", "path": str(checkout)})
    actions, plan_errors = plan(checkout, home, tree, read, ends=("codex",), codex_home=codex_home)
    errors.extend(plan_errors)
    native = [a for a in actions if a["kind"] == "native-role"]
    if not native:
        errors.append({"code": "adoption_without_native_roles", "path": str(checkout)})
    if any(a["state"] != "match" for a in actions):
        errors.append({"code": "adoption_not_all_match", "path": str(checkout)})
    current = registry_native_present(Path(checkout, "tools/sync-targets.json").read_bytes())
    if any(current.get(a["object"]) for a in native):
        errors.append({"code": "adoption_not_new", "path": str(checkout)})
    if git_bytes(checkout, "diff-tree", "-r", "--raw", "--no-commit-id", "HEAD", commit, "--", *ADOPTION_SOURCES):
        errors.append({"code": "adopted_sources_changed", "path": str(checkout)})
    return actions, errors, commit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--home", type=Path, default=Path.home(), help="受管安装根；不改变 CLI 的 HOME")
    parser.add_argument("--ends", nargs="+", choices=ENDS, default=ENDS, help="只处理所选登记端，默认全部")
    parser.add_argument("--codex-home", type=Path,
                        help="仅 --ends codex：安装根内的 CODEX_HOME；技能采用 0.170.0 兼容根 skills")
    parser.add_argument("--previous", help="--apply 时清理此本地 Git 版本独有的受管入口；不删除目录或登录态")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--preflight", metavar="TARGET_REV", help="切版本前只读预检本地 Git 目标版本")
    modes.add_argument("--check-native-role-adoption", metavar="TARGET_REV",
                       help="只读：新版登记对同一实际根的全 match 与两原生角色新增范围；不写文件")
    args = parser.parse_args(argv)
    if args.previous and not args.apply:
        parser.error("--previous requires --apply")
    report = {"schemaVersion": 1, "mode": "apply" if args.apply else "check" if args.check else "preflight" if args.preflight
              else "check-native-role-adoption" if args.check_native_role_adoption else "plan",
              "actions": [], "errors": []}
    try:
        if not args.checkout.is_absolute():
            raise InstallError("checkout_must_be_absolute", args.checkout)
        checkout, home = args.checkout.resolve(), args.home
        ends, codex_home = tuple(args.ends), args.codex_home
        if not home.is_absolute() or ".." in home.parts:
            raise InstallError("home_must_be_absolute", home)
        if codex_home is not None:
            if ends != ("codex",) or not codex_home.is_absolute() or ".." in codex_home.parts:
                raise InstallError("invalid_native_codex_layout", codex_home)
            try:
                relative = codex_home.relative_to(home)
            except ValueError:
                raise InstallError("codex_home_outside_install_root", codex_home) from None
            if not relative.parts:
                raise InstallError("invalid_native_codex_layout", codex_home)
        tree = HomeTree(home)
        report.update(home=str(home), ends=list(ends), codexHome=str(codex_home) if codex_home else None)
        report.update(checkout=str(checkout), head=git_value(checkout, "rev-parse", "HEAD"),
                      trackedState="dirty" if git_value(checkout, "status", "--porcelain") else "clean")
        previous, previous_errors, priors = [], [], {}
        if args.previous:
            report["previousHead"], read = revision_reader(checkout, args.previous)
            previous, previous_errors = desired(checkout, home, tree, read, baseline=True, ends=ends, codex_home=codex_home)
            priors = {str(a["path"]): a["content"] for a in previous if a["kind"] == "native-role"}
        if args.check_native_role_adoption:
            if ends != ("codex",) or codex_home is None:
                raise InstallError("invalid_native_codex_layout", home)
            if report["trackedState"] != "clean":
                errors.append({"code": "checkout_dirty", "path": str(checkout)})
            actions, adoption_errors, report["targetHead"] = native_role_adoption(
                checkout, home, tree, args.check_native_role_adoption, codex_home)
            errors.extend(adoption_errors)
            report["previousInstallerBlob"] = git_value(checkout, "rev-parse", "HEAD:tools/link-install.py")
            report["targetInstallerBlob"] = git_value(checkout, "rev-parse", report["targetHead"] + ":tools/link-install.py")
        else:
            actions, errors = plan(checkout, home, tree, ends=ends, codex_home=codex_home, priors=priors)
        errors.extend(previous_errors)
        if args.previous:
            errors.extend(compatibility_errors(checkout, report["previousHead"], read, previous, actions))
        retired = []
        if args.preflight:
            if report["trackedState"] != "clean" or any(a["state"] != "match" for a in actions):
                errors.append({"code": "current_installation_not_clean", "path": str(checkout)})
            report["targetHead"], read = revision_reader(checkout, args.preflight)
            candidate, candidate_errors = plan(checkout, home, tree, read, ends=ends, codex_home=codex_home)
            installed = actions
            actions = candidate
            # 不可信的登记不参与兼容比较：历史基线的停止只属于 --previous，不能附到预检目标上。
            if not registry_invalid(candidate_errors):
                candidate_errors = candidate_errors + compatibility_errors(
                    checkout, report["targetHead"], read, candidate, installed)
            errors.extend(candidate_errors)
            # 双方登记都要可信才算退役：当前检出非法时不能给出退役预览。
            if not registry_invalid(errors):
                retired, cleanup_errors = retirements(installed, candidate, tree)
                errors.extend(cleanup_errors)
        elif args.previous:
            if report["trackedState"] != "clean":
                errors.append({"code": "checkout_dirty", "path": str(checkout)})
            if not registry_invalid(errors):
                retired, cleanup_errors = retirements(previous, actions, tree)
                errors.extend(cleanup_errors)
        report["residue"] = staging_residue(actions + previous, tree)
        report["retirements"] = [public_action(a) for a in retired]
        report["actions"] = [public_action(a) for a in actions]
        report["errors"] = errors
        if errors:
            report["status"], code = "blocked", 2
        elif args.apply:
            report["created"] = [public_action(a) for a in apply(actions, tree)]
            for action in retired:
                delete_retired(action, tree)
            actions, errors = plan(checkout, home, tree, ends=ends, codex_home=codex_home)
            report["actions"] = [public_action(a) for a in actions]
            report["errors"] = errors
            matched = not errors and all(a["state"] == "match" for a in actions)
            report["status"], code = ("completed", 0) if matched else ("different", 1)
        elif args.check_native_role_adoption:
            matched = not errors and all(a["state"] == "match" for a in actions)
            report["status"], code = ("match", 0) if matched else "blocked", 2 if errors else 1
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

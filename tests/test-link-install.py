#!/usr/bin/env python3
"""宿主安装器离线回归：临时 HOME、真实进程、文件与软链；不访问真实登录态。"""
import json
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/link-install.py"
SPEC = importlib.util.spec_from_file_location("link_install", TOOL)
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="link-install-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home/paseo"
        self.home.mkdir(parents=True)
        self.checkout = self.root / "checkout with space"
        self.checkout.mkdir()
        for name in ("skills", "prompt", "subagents"):
            shutil.copytree(ROOT / name, self.checkout / name)
        (self.checkout / "tools").mkdir()
        shutil.copyfile(ROOT / "tools/sync-targets.json", self.checkout / "tools/sync-targets.json")
        self.env = {"HOME": str(self.home), "PATH": os.environ["PATH"], "LC_ALL": "C.UTF-8",
                    "CLAUDE_CONFIG_DIR": str(self.home / ".claude"),
                    "CODEX_HOME": str(self.home / ".codex"),
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        for args in (("init", "-q", "-b", "main"), ("add", "."),
                     ("-c", "user.name=test", "-c", "user.email=test@local", "commit", "-qm", "fixture")):
            subprocess.run(["git", "-C", str(self.checkout), *args], env=self.env, check=True)
        self.global_file = self.home / ".luno/memory/GLOBAL.md"
        self.global_file.parent.mkdir(parents=True)
        self.global_file.write_bytes(b"private global fixture\r\n\n")
        self.global_file.chmod(0o600)

    def call(self, *args):
        proc = subprocess.run([sys.executable, "-B", str(TOOL), "--checkout", str(self.checkout), *args],
                              env=self.env, capture_output=True, check=False, timeout=30)
        self.assertEqual(proc.stderr, b"", proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def snapshot(self):
        return {str(p.relative_to(self.home)): os.readlink(p) if p.is_symlink()
                else p.read_bytes() if p.is_file() else "directory"
                for p in self.home.rglob("*")}

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.checkout), *args], env=self.env).decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=test", "-c", "user.email=test@local", "commit", "-qm", "fixture change")
        return self.git("rev-parse", "HEAD")

    def test_plan_is_read_only_and_install_is_idempotent(self):
        before = self.snapshot()
        rc, report = self.call()
        self.assertEqual((rc, report["status"]), (0, "planned"))
        self.assertEqual(self.snapshot(), before)
        expected_head = subprocess.check_output(["git", "-C", str(self.checkout), "rev-parse", "HEAD"], env=self.env).decode().strip()
        self.assertEqual(report["head"], expected_head)
        self.assertEqual(report["trackedState"], "clean")
        self.assertEqual(self.call("--check")[0], 1)
        self.assertEqual(self.call("--apply")[0], 0)
        installed = self.snapshot()
        self.assertEqual(self.call("--apply")[0], 0)
        self.assertEqual(self.snapshot(), installed)
        self.assertEqual(self.call("--check")[0], 0)
        self.assertNotIn("private global fixture", json.dumps(report))

    def test_native_layout_and_exact_generated_contents(self):
        self.assertEqual(self.call("--apply")[0], 0)
        registry = json.loads((self.checkout / "tools/sync-targets.json").read_text())
        for obj in registry["objects"]:
            if obj["type"] != "skill":
                continue
            name = obj["id"]
            for destination in (f".claude/skills/{name}", f".agents/skills/{name}",
                                f".luno/homes/lens-claude/skills/{name}",
                                f".luno/homes/forge-claude/skills/{name}"):
                self.assertEqual(os.readlink(self.home / destination), str(self.checkout / obj["source"]).rsplit("/", 1)[0])
        claude = self.home / ".claude/CLAUDE.md"
        self.assertEqual(os.readlink(claude), str(self.home / ".luno/generated/claude-code/CLAUDE.md"))
        self.assertEqual(claude.read_text(), '@"' + str(self.checkout / "prompt/LUNO.md") + '"\n@~/.luno/memory/GLOBAL.md\n')
        codex = self.home / ".codex/AGENTS.md"
        self.assertEqual(codex.read_bytes(), (self.checkout / "prompt/LUNO.md").read_bytes() + b"\n" + self.global_file.read_bytes())
        for role in ("lens", "forge"):
            wrapped = (self.home / f".claude/agents/{role}.md").read_bytes()
            header, body = wrapped.split(b"\n---\n\n", 1)
            metadata = yaml.safe_load(header[4:])
            self.assertEqual(metadata["name"], role)
            self.assertEqual(metadata["skills"], ["luno-core"])
            self.assertIs(metadata["omitClaudeMd"], True)
            self.assertEqual(body, (self.checkout / f"subagents/{role.upper()}.md").read_bytes())
            for provider, entry in (("claude", "CLAUDE.md"), ("codex", "AGENTS.md")):
                directory = self.home / f".luno/homes/{role}-{provider}"
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
                self.assertEqual(os.readlink(directory / entry), str(self.checkout / f"subagents/{role.upper()}.md"))
                for name in ("auth.json", "config.toml", "settings.json", ".credentials.json"):
                    self.assertFalse((directory / name).exists())
        self.assertFalse((self.home / ".codex/agents").exists())
        for artifact in (self.home / ".luno/generated").rglob("*.md"):
            self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o600)

    def test_global_refresh_updates_only_managed_generated_files(self):
        self.assertEqual(self.call("--apply")[0], 0)
        self.global_file.write_bytes(b"new private global\n\n")
        self.assertEqual(self.call("--check")[0], 1)
        self.assertEqual(self.call("--apply")[0], 0)
        self.assertEqual((self.home / ".codex/AGENTS.md").read_bytes(),
                         (self.checkout / "prompt/LUNO.md").read_bytes() + b"\nnew private global\n\n")
        self.assertEqual(self.call("--check")[0], 0)

    def test_missing_global_blocks_apply_before_any_writes(self):
        self.global_file.unlink()
        before = self.snapshot()
        rc, report = self.call("--apply")
        self.assertEqual(rc, 2)
        self.assertIn("missing_global_copy", [e["code"] for e in report["errors"]])
        self.assertTrue(any(a["path"].endswith(".claude/CLAUDE.md") for a in report["actions"]))
        self.assertEqual(self.snapshot(), before)

    def test_existing_public_file_and_wrong_link_are_conflicts(self):
        claude = self.home / ".claude"
        claude.mkdir()
        (claude / "CLAUDE.md").write_bytes(b"my existing instructions")
        target = self.root / "unmanaged"
        target.write_bytes(b"leave target unchanged")
        (claude / "agents").mkdir()
        (claude / "agents/lens.md").symlink_to(target)
        before = self.snapshot()
        rc, report = self.call("--apply")
        self.assertEqual(rc, 2)
        self.assertIn("path_conflict", [e["code"] for e in report["errors"]])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(target.read_bytes(), b"leave target unchanged")

    def test_existing_unowned_artifact_is_not_overwritten(self):
        artifact = self.home / ".luno/generated/codex/AGENTS.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"unowned previous artifact")
        before = self.snapshot()
        self.assertEqual(self.call("--apply")[0], 2)
        self.assertEqual(self.snapshot(), before)

    def test_identical_unowned_artifact_is_not_adopted(self):
        self.assertEqual(self.call("--apply")[0], 0)
        public = self.home / ".codex/AGENTS.md"
        public.unlink()
        before = self.snapshot()
        self.assertEqual(self.call("--apply")[0], 2)
        self.assertEqual(self.snapshot(), before)

    def test_role_home_wrong_mode_or_owner_blocks_without_repair(self):
        role = self.home / ".luno/homes/lens-codex"
        role.mkdir(parents=True, mode=0o755)
        before = self.snapshot()
        self.assertEqual(self.call("--apply")[0], 2)
        self.assertEqual(stat.S_IMODE(role.stat().st_mode), 0o755)
        self.assertEqual(self.snapshot(), before)
        role.chmod(0o700)
        tree = INSTALL.HomeTree(self.home)
        self.addCleanup(tree.close)
        with patch.object(INSTALL.os, "geteuid", return_value=os.geteuid() + 1):
            self.assertEqual(INSTALL.state({"kind": "directory", "path": role}, tree), "conflict")

    def test_codex_override_shadowing_is_reported_without_reading_or_overwriting(self):
        self.assertEqual(self.call("--apply")[0], 0)
        for relative in (".codex", ".luno/homes/lens-codex", ".luno/homes/forge-codex"):
            with self.subTest(home=relative):
                override = self.home / relative / "AGENTS.override.md"
                override.write_bytes(b"USER OVERRIDE")
                before = self.snapshot()
                for mode in ("--check", "--apply"):
                    rc, report = self.call(mode)
                    self.assertEqual(rc, 2)
                    self.assertIn({"code": "agents_override_shadowing", "path": str(override)}, report["errors"])
                    self.assertEqual(self.snapshot(), before)
                override.unlink()

    def test_global_and_legacy_parent_symlinks_are_rejected_before_reads(self):
        for relative in (".luno/memory", ".codex/skills", ".codex/skills/legacy"):
            with self.subTest(parent=relative):
                path = self.home / relative
                if path.exists():
                    shutil.rmtree(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                outside = self.root / ("outside-" + relative.replace("/", "-"))
                outside.mkdir()
                (outside / "GLOBAL.md").write_bytes(b"INVALID UTF8\xff")
                (outside / "SKILL.md").write_bytes(b"INVALID UTF8\xff")
                path.symlink_to(outside, target_is_directory=True)
                rc, report = self.call("--apply")
                self.assertEqual(rc, 2)
                self.assertIn("unsafe_parent", [e["code"] for e in report["errors"]])
                self.assertFalse((self.home / ".claude").exists())
                self.assertEqual(sorted(p.name for p in outside.iterdir()), ["GLOBAL.md", "SKILL.md"])
                path.unlink()
                if relative == ".luno/memory":
                    path.mkdir()
                    self.global_file.write_bytes(b"global fixture")

    def test_parent_replacement_after_plan_cannot_redirect_writes(self):
        parent = self.home / ".claude"
        parent.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        tree = INSTALL.HomeTree(self.home)
        self.addCleanup(tree.close)
        actions, errors = INSTALL.plan(self.checkout, self.home, tree)
        self.assertEqual(errors, [])
        parent.rename(self.home / "checked-claude")
        parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(INSTALL.InstallError) as result:
            INSTALL.apply(actions, tree)
        self.assertIn(result.exception.code, ("parent_changed", "path_conflict"))
        self.assertEqual(list(outside.iterdir()), [])

    def test_preflight_and_interrupted_upgrade_recovery_preserve_login_state(self):
        registry_file = self.checkout / "tools/sync-targets.json"
        new_registry = json.loads(registry_file.read_text())
        old_registry = json.loads(registry_file.read_text())
        old_registry["objects"] = [o for o in old_registry["objects"] if o["id"] != "subagents/FORGE.md"]
        registry_file.write_text(json.dumps(old_registry))
        old = self.commit()
        self.assertEqual(self.call("--apply")[0], 0)
        baseline = self.snapshot()
        registry_file.write_text(json.dumps(new_registry))
        prompt = self.checkout / "prompt/LUNO.md"
        prompt.write_bytes(prompt.read_bytes() + b"\nNEW_VERSION\n")
        new = self.commit()
        self.git("checkout", "-q", old)
        rc, report = self.call("--preflight", new)
        self.assertEqual((rc, report["status"], report["targetHead"]), (0, "ready", new))
        self.assertEqual(self.snapshot(), baseline)

        # 独立进程写到新版独有暂存文件的一部分时中断，重跑和回退都须能处理。
        self.git("checkout", "-q", new)
        script = self.root / "interrupt.py"
        script.write_text('''import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("installer", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def interrupt(action, tree):
    if action["path"].name == "forge.md":
        name = "." + action["path"].name + module.STAGING_SUFFIX
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600,
                     dir_fd=tree.directory(action["path"].parent))
        os.write(fd, b"INTERRUPTED_PARTIAL_CONTENT")
        os._exit(99)
    write(action, tree)
write = module.write_generated
module.write_generated = interrupt
module.main(sys.argv[2:])
''')
        proc = subprocess.run([sys.executable, "-B", str(script), str(TOOL), "--checkout", str(self.checkout),
                               "--apply", "--previous", old], env=self.env, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 99, proc.stderr)
        self.assertTrue((self.home / ".claude/agents/forge.md").is_symlink())
        artifact = self.home / ".luno/generated/claude-code/agents/forge.md"
        staging = artifact.with_name(".forge.md.link-install.tmp")
        self.assertFalse(artifact.exists())
        self.assertEqual(staging.read_bytes(), b"INTERRUPTED_PARTIAL_CONTENT")
        login = self.home / ".luno/homes/forge-codex/auth.json"
        login.write_bytes(b"SYNTH_LOGIN")
        login.chmod(0o600)
        self.git("checkout", "-q", old)
        rc, report = self.call("--apply", "--previous", new)
        self.assertEqual((rc, report["status"]), (0, "completed"), report["errors"])
        self.assertFalse((self.home / ".claude/agents/forge.md").is_symlink())
        self.assertFalse((self.home / ".luno/generated/claude-code/agents/forge.md").exists())
        # 归属不可证的暂存残留不清理，只报告：重跑与回退都不删它。
        self.assertIn(str(staging), report["residue"])
        self.assertEqual(staging.read_bytes(), b"INTERRUPTED_PARTIAL_CONTENT")
        self.assertFalse((self.home / ".luno/homes/forge-codex/AGENTS.md").is_symlink())
        self.assertEqual(login.read_bytes(), b"SYNTH_LOGIN")
        self.assertEqual(self.call("--check")[0], 0)
        self.assertEqual(self.call("--apply", "--previous", new)[0], 0)
        # 同一中断状态也允许直接重跑新版完成升级。
        self.git("checkout", "-q", new)
        proc = subprocess.run([sys.executable, "-B", str(script), str(TOOL), "--checkout", str(self.checkout),
                               "--apply", "--previous", old], env=self.env, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 99, proc.stderr)
        self.assertEqual(self.call("--apply", "--previous", old)[0], 0)
        self.assertEqual(self.call("--check")[0], 0)
        self.assertNotIn(b"INTERRUPTED_PARTIAL_CONTENT", artifact.read_bytes())
        self.assertEqual(login.read_bytes(), b"SYNTH_LOGIN")

    def test_preflight_rejects_candidate_conflict_before_git_switch(self):
        self.assertEqual(self.call("--apply")[0], 0)
        old = self.git("rev-parse", "HEAD")
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        registry["objects"][0]["ends"]["claude-code"]["paths"].append("~/.claude/user.md")
        registry_file.write_text(json.dumps(registry))
        new = self.commit()
        self.git("checkout", "-q", old)
        (self.home / ".claude/user.md").write_bytes(b"UNMANAGED")
        before = self.snapshot()
        self.assertEqual(self.call("--preflight", new)[0], 2)
        self.assertEqual(self.git("rev-parse", "HEAD"), old)
        self.assertEqual(self.snapshot(), before)

    def test_compose_build_context_excludes_env_credentials_and_workspace(self):
        compose = yaml.safe_load((ROOT / "platforms/paseo/compose.example.yaml").read_text())
        self.assertEqual(set(compose["services"]), {"paseo"})
        service = compose["services"]["paseo"]
        self.assertEqual(service["build"], {"context": "./build", "dockerfile": "Dockerfile"})
        self.assertEqual(service["env_file"], ["./paseo.env"])
        self.assertEqual(service["ports"], ["127.0.0.1:6767:6767"])
        self.assertEqual(service["volumes"], ["./paseo-home:/home/paseo", "./workspace:/workspace"])
        self.assertFalse(service.get("privileged", False))
        self.assertNotEqual(service.get("network_mode"), "host")

    def test_parent_symlink_cannot_redirect_installer_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep").write_bytes(b"untouched")
        (self.home / ".claude").symlink_to(outside)
        self.assertEqual(self.call("--apply")[0], 2)
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ["keep"])

    def test_duplicate_legacy_skill_is_reported_without_modification(self):
        legacy = self.home / ".codex/skills/managed-copy"
        legacy.mkdir(parents=True)
        (legacy / "SKILL.md").write_text('---\nname: "luno-core"\ndescription: duplicate\n---\ncopy\n')
        before = self.snapshot()
        rc, report = self.call("--apply")
        self.assertEqual(rc, 2)
        self.assertIn({"code": "duplicate_skill_name", "path": str(legacy / "SKILL.md"), "name": "luno-core"}, report["errors"])
        self.assertEqual(self.snapshot(), before)

    def test_owned_artifact_symlink_is_rejected_and_secret_files_untouched(self):
        self.assertEqual(self.call("--apply")[0], 0)
        credential = self.home / ".codex/auth.json"
        credential.write_bytes(b"SYNTH_CREDENTIAL_FILE")
        artifact = self.home / ".luno/generated/codex/AGENTS.md"
        artifact.unlink()
        artifact.symlink_to(credential)
        rc, report = self.call("--apply")
        self.assertEqual(rc, 2)
        self.assertEqual(credential.read_bytes(), b"SYNTH_CREDENTIAL_FILE")
        self.assertNotIn("SYNTH_CREDENTIAL_FILE", json.dumps(report))

    def test_atomic_update_and_unowned_staging_residue_is_reported_not_deleted(self):
        self.assertEqual(self.call("--apply")[0], 0)
        artifact = self.home / ".luno/generated/codex/AGENTS.md"
        original = artifact.read_bytes()
        self.global_file.write_bytes(b"new global fixture")
        tree = INSTALL.HomeTree(self.home)
        self.addCleanup(tree.close)
        actions, errors = INSTALL.plan(self.checkout, self.home, tree)
        self.assertEqual(errors, [])
        with patch.object(INSTALL.os, "replace", side_effect=INSTALL.InstallError("interrupted", artifact)):
            with self.assertRaises(INSTALL.InstallError):
                INSTALL.apply(actions, tree)
        self.assertEqual(artifact.read_bytes(), original)
        # 中断失败时目标文件没有被替换，本次自己的暂存也不留；正常生成仍是原子的。
        self.assertEqual([p.name for p in artifact.parent.iterdir()
                          if p.name.startswith(".AGENTS.md.link-install.tmp")], [])
        # 未知归属的残留（中断或旧版固定名留下）不属于本次创建，后续运行只报告不清理。
        residue = artifact.with_name(".AGENTS.md.link-install.tmp.0123456789abcdef")
        residue.write_bytes(b"INTERRUPTED_PARTIAL_CONTENT")
        residue.chmod(0o600)
        rc, report = self.call("--apply")
        self.assertEqual(rc, 0, report["errors"])
        self.assertIn(str(residue), report["residue"])
        self.assertEqual(residue.read_bytes(), b"INTERRUPTED_PARTIAL_CONTENT")
        self.assertNotEqual(artifact.read_bytes(), original)
        # 旧版固定名上的残留同样不清退，指向秘密时也不跟随、不删除。
        legacy = artifact.with_name(".AGENTS.md.link-install.tmp")
        credential = self.home / ".codex/auth.json"
        credential.write_bytes(b"SYNTH_SECRET")
        legacy.symlink_to(credential)
        before = self.snapshot()
        rc, report = self.call("--apply")
        self.assertEqual(rc, 0, report["errors"])
        self.assertIn(str(legacy), report["residue"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(credential.read_bytes(), b"SYNTH_SECRET")

    def test_repointed_public_entry_retires_old_artifact_without_deadlock(self):
        # 新版渲染器把同一公开入口改指另一份生成文件：旧文件必须按改指前核实的归属退役，
        # 不因软链已改指被误判成非受管，也不让改指后的重跑卡住。
        self.assertEqual(self.call("--apply")[0], 0)
        artifact = self.home / ".luno/generated/claude-code/agents/forge.md"
        public = self.home / ".claude/agents/forge.md"
        self.assertTrue(artifact.is_file())
        old = self.git("rev-parse", "HEAD")
        script = self.root / "repoint.py"
        script.write_text('''import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("installer", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
render = module.render
def repointed(obj, renderer, checkout, home, tree, read):
    artifact, content = render(obj, renderer, checkout, home, tree, read)
    if read is Path.read_bytes and artifact.name == "forge.md":
        artifact = artifact.with_name("forge-v2.md")
    return artifact, content
module.render = repointed
sys.exit(module.main(sys.argv[2:]))
''')
        run = [sys.executable, "-B", str(script), str(TOOL), "--checkout", str(self.checkout)]
        # 合成中断：旧文件已按已核 inode 退役，公开软链还没改指就退出。
        interrupt = self.root / "repoint-interrupt.py"
        interrupt.write_text('''import importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("installer", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
render = module.render
def repointed(obj, renderer, checkout, home, tree, read):
    artifact, content = render(obj, renderer, checkout, home, tree, read)
    if read is Path.read_bytes and artifact.name == "forge.md":
        artifact = artifact.with_name("forge-v2.md")
    return artifact, content
def stop(*args, **kwargs):
    os._exit(99)
module.render = repointed
module.os.symlink = stop
sys.exit(module.main(sys.argv[2:]))
''')
        proc = subprocess.run([sys.executable, "-B", str(interrupt), str(TOOL), "--checkout", str(self.checkout),
                               "--apply", "--previous", old], env=self.env, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 99, proc.stdout + proc.stderr)
        self.assertFalse(artifact.exists())
        self.assertEqual(os.readlink(public), str(artifact))  # 悬空窗口：软链尚未改指
        proc = subprocess.run(run + ["--apply", "--previous", old],
                              env=self.env, capture_output=True, timeout=30)
        report = json.loads(proc.stdout)
        self.assertEqual((proc.returncode, report["status"]), (0, "completed"), report["errors"])
        self.assertEqual(report["retirements"], [])  # 旧文件已在中断前退役，重跑无重复删除
        self.assertIn((str(artifact.with_name("forge-v2.md")), "create"),
                      {(a["path"], a["state"]) for a in report["created"]})
        self.assertEqual(os.readlink(public), str(artifact.with_name("forge-v2.md")))
        # 改指后重跑同一入口不改写已完成状态，也不残留暂存文件。
        proc = subprocess.run(run + ["--apply", "--previous", old],
                              env=self.env, capture_output=True, timeout=30)
        report = json.loads(proc.stdout)
        self.assertEqual((proc.returncode, report["status"]), (0, "completed"), report["errors"])
        self.assertEqual(report["retirements"], [])
        self.assertEqual(report["residue"], [])
        proc = subprocess.run(run + ["--check"], env=self.env, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_created_report_covers_first_install_and_existing_state_is_preserved(self):
        login = self.home / ".codex/auth.json"
        login.parent.mkdir(parents=True, exist_ok=True)
        login.write_bytes(b"SYNTH_LOGIN")
        login.chmod(0o600)
        rc, report = self.call("--apply")
        self.assertEqual(rc, 0, report["errors"])
        created = {(a["path"], a["state"]) for a in report["created"]}
        generated = str(self.home / ".luno/generated/codex/AGENTS.md")
        self.assertIn((generated, "create"), created)
        self.assertIn((str(self.home / ".codex/AGENTS.md"), "create"), created)
        # 前态已有的文件不在 created 里，也不被改写。
        self.assertNotIn(str(login), {p for p, _ in created})
        self.assertEqual(login.read_bytes(), b"SYNTH_LOGIN")
        # 重跑没有新增项：后续不能拿空报告当「本次新增」去撤回。
        rc, report = self.call("--apply")
        self.assertEqual((rc, report["created"]), (0, []))
        # 更新只报 update，不冒充新建。
        self.global_file.write_bytes(b"new global fixture")
        rc, report = self.call("--apply")
        self.assertEqual(rc, 0, report["errors"])
        self.assertEqual([(a["path"], a["state"]) for a in report["created"]], [(generated, "update")])

    def test_previous_revision_without_host_registration_retires_nothing(self):
        installed = self.call("--apply")[0]
        self.assertEqual(installed, 0)
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            for end in ("claude-code", "codex", "paseo"):
                if end in obj["ends"]:
                    obj["ends"][end] = {"present": False}
        registry_file.write_text(json.dumps(registry))
        old_without_host = self.commit()
        registry_file.write_text(json.dumps(json.loads((ROOT / "tools/sync-targets.json").read_text())))
        self.commit()
        before = self.snapshot()
        rc, report = self.call("--apply", "--previous", old_without_host)
        self.assertEqual((rc, report["status"], report["retirements"]), (0, "completed", []))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.call("--check")[0], 0)

    def test_successful_install_preserves_existing_login_and_settings_files(self):
        paths = (".claude/.credentials.json", ".claude/settings.json", ".codex/auth.json", ".codex/config.toml")
        for name in paths:
            path = self.home / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"SYNTH_EXISTING_USER_STATE")
        rc, report = self.call("--apply")
        self.assertEqual(rc, 0)
        for name in paths:
            self.assertEqual((self.home / name).read_bytes(), b"SYNTH_EXISTING_USER_STATE")
        self.assertNotIn("SYNTH_EXISTING_USER_STATE", json.dumps(report))

    def test_paseo_provider_example_matches_installed_role_homes(self):
        config = json.loads((ROOT / "platforms/paseo/config.example.json").read_text())
        self.assertNotIn("listen", config["daemon"])
        self.assertIs(config["daemon"]["mcp"]["injectIntoAgents"], True)
        self.assertEqual(self.call("--apply")[0], 0)
        for role in ("lens", "forge"):
            for provider, variable, entry in (("claude", "CLAUDE_CONFIG_DIR", "CLAUDE.md"),
                                               ("codex", "CODEX_HOME", "AGENTS.md")):
                key = role + "-" + provider
                fragment = config["agents"]["providers"][key]
                self.assertEqual(fragment["extends"], provider)
                relative = fragment["env"][variable].removeprefix("/home/paseo/")
                self.assertEqual(relative, ".luno/homes/" + key)
                self.assertEqual((self.home / relative / entry).read_bytes(),
                                 (self.checkout / f"subagents/{role.upper()}.md").read_bytes())


if __name__ == "__main__":
    unittest.main()

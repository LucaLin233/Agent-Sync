#!/usr/bin/env python3
"""宿主安装器离线回归：临时 HOME、真实进程、文件与软链；不访问真实登录态。
预算：升级/回退与真实进程、软链边界并入同族按需入口，不进 full；iSH 整套超过 10 秒，主验收留给 CI，裁定与实测记当次 PR。"""
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
        for name in ("sync-targets.json", "link-install.py"):
            shutil.copyfile(ROOT / "tools" / name, self.checkout / "tools" / name)
        gitconfig = self.root / "gitconfig"
        gitconfig.write_bytes(b"")
        self.env = {"HOME": str(self.home), "PATH": os.environ["PATH"], "LC_ALL": "C.UTF-8",
                    "CLAUDE_CONFIG_DIR": str(self.home / ".claude"),
                    "CODEX_HOME": str(self.home / ".codex"),
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(gitconfig)}
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

    def test_installer_change_stops_before_writes(self):
        # 安装器自身改变就可能改渲染路径，两个版本的 action 都由当前安装器算出，看不出差异：
        # 首版以两份 tools/link-install.py 的 blob 一致作为必要判据，不一致就在写前停止。
        self.assertEqual(self.call("--apply")[0], 0)
        baseline = self.snapshot()
        old = self.git("rev-parse", "HEAD")
        tool = self.checkout / "tools/link-install.py"
        tool.write_bytes(tool.read_bytes() + b"\n# upgraded renderer\n")
        new = self.commit()
        self.git("checkout", "-q", old)
        rc, report = self.call("--preflight", new)
        self.assertEqual((rc, report["status"]), (2, "blocked"))
        self.assertIn("installer_changed", [e["code"] for e in report["errors"]])
        self.assertEqual(self.snapshot(), baseline)
        self.git("checkout", "-q", new)
        rc, report = self.call("--apply", "--previous", old)
        self.assertEqual((rc, report["status"]), (2, "blocked"))
        self.assertIn("installer_changed", [e["code"] for e in report["errors"]])
        self.assertEqual(self.snapshot(), baseline)

    def test_registry_layout_change_stops_before_writes(self):
        # 安装器相同，但登记把同一公开入口推导到别的目标，同样不算已证明的同布局。
        self.assertEqual(self.call("--apply")[0], 0)
        baseline = self.snapshot()
        old = self.git("rev-parse", "HEAD")
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            if obj["id"] == "subagents/LENS.md":
                obj["ends"]["claude-code"]["renderer"] = "codex-main"
        registry_file.write_text(json.dumps(registry))
        new = self.commit()
        self.git("checkout", "-q", old)
        rc, report = self.call("--preflight", new)
        self.assertEqual((rc, report["status"]), (2, "blocked"))
        self.assertIn("layout_changed", [e["code"] for e in report["errors"]])
        self.assertEqual(self.snapshot(), baseline)
        self.git("checkout", "-q", new)
        rc, report = self.call("--apply", "--previous", old)
        self.assertEqual((rc, report["status"]), (2, "blocked"), report)
        self.assertIn("layout_changed", [e["code"] for e in report["errors"]])
        self.assertEqual(self.snapshot(), baseline)

    def test_preexisting_staging_items_are_reported_and_kept(self):
        # 历史遗留的链接与生成文件暂存项只报不删，也不跟随其内容。
        self.assertEqual(self.call("--apply")[0], 0)
        generated = self.home / ".luno/generated/codex/AGENTS.md"
        link_dir = self.home / ".claude/agents"
        old_staging = generated.with_name(".AGENTS.md.link-install.tmp")
        link_staging = link_dir / ".forge.md.link-install.tmp.0123456789abcdef"
        old_staging.write_bytes(b"OLD_GENERATED_RESIDUE")
        link_staging.symlink_to(self.home / ".codex/auth.json")
        before = self.snapshot()
        rc, report = self.call("--apply")
        self.assertEqual(rc, 0, report["errors"])
        self.assertIn(str(old_staging), report["residue"])
        self.assertIn(str(link_staging), report["residue"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(old_staging.read_bytes(), b"OLD_GENERATED_RESIDUE")

    def test_valid_registry_all_false_retires_managed_items(self):
        # 正控：同安装器 blob 的两版，新版本把各端显式 present:false 仍属有效完整登记，
        # 预检就绪、升级按受管项精确退役，登录态不动。
        self.assertEqual(self.call("--apply")[0], 0)
        login = self.home / ".codex/auth.json"
        login.write_bytes(b"SYNTH_LOGIN")
        login.chmod(0o600)
        public = self.home / ".claude/CLAUDE.md"
        generated = self.home / ".luno/generated/claude-code/CLAUDE.md"
        old = self.git("rev-parse", "HEAD")
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            for end in ("claude-code", "codex", "paseo"):
                if end in obj["ends"]:
                    obj["ends"][end] = {"present": False}
        registry_file.write_text(json.dumps(registry))
        new = self.commit()
        self.git("checkout", "-q", old)
        rc, report = self.call("--preflight", new)
        self.assertEqual((rc, report["status"]), (0, "ready"), report)
        self.git("checkout", "-q", new)
        rc, report = self.call("--apply", "--previous", old)
        self.assertEqual((rc, report["status"]), (0, "completed"), report["errors"])
        retired = [a["path"] for a in report["retirements"]]
        self.assertIn(str(public), retired)
        self.assertIn(str(generated), retired)
        self.assertFalse(public.is_symlink())
        self.assertFalse(generated.exists())
        self.assertEqual(login.read_bytes(), b"SYNTH_LOGIN")
        self.assertEqual(self.call("--check")[0], 0)

    def test_preflight_with_partial_current_ends_has_no_retirement_preview(self):
        # 当前检出部分缺键、目标版有效且会退役一个已知入口：必须 blocked 且不给退役预览。
        self.assertEqual(self.call("--apply")[0], 0)
        baseline = self.snapshot()
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            if obj["id"] == "subagents/LENS.md":
                obj["ends"]["claude-code"] = {"present": False}
        registry_file.write_text(json.dumps(registry))
        target = self.commit()
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            if obj["id"] == "subagents/LENS.md":
                obj["ends"].pop("codex", None)
        registry_file.write_text(json.dumps(registry))
        self.commit()
        rc, report = self.call("--preflight", target)
        self.assertEqual((rc, report["status"]), (2, "blocked"), report)
        self.assertIn("registry_end_missing", [e["code"] for e in report["errors"]])
        self.assertEqual((report["retirements"], self.snapshot()), ([], baseline))

    def test_registry_without_host_ends_stops_for_current_and_target(self):
        # 当前检出整版没有宿主端键时不能当作可写的宿主版本。
        self.assertEqual(self.call("--apply")[0], 0)
        baseline = self.snapshot()
        old = self.git("rev-parse", "HEAD")
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            for end in ("claude-code", "codex", "paseo"):
                obj["ends"].pop(end, None)
        registry_file.write_text(json.dumps(registry))
        new = self.commit()
        rc, report = self.call("--apply")
        self.assertEqual((rc, report["status"]), (2, "blocked"), report)
        self.assertIn("registry_without_host_ends", [e["code"] for e in report["errors"]])
        self.assertEqual((report["retirements"], self.snapshot()), ([], baseline))
        self.git("checkout", "-q", old)
        rc, report = self.call("--preflight", new)
        self.assertEqual((rc, report["status"]), (2, "blocked"), report)
        self.assertIn("registry_without_host_ends", [e["code"] for e in report["errors"]])
        # 无键的预检目标不假报只属于 --previous 历史基线的停止码
        self.assertNotIn("previous_without_host_installation", [e["code"] for e in report["errors"]])
        self.assertEqual(report["retirements"], [])
        self.assertEqual(self.snapshot(), baseline)

    def test_partial_host_end_keys_stop_without_writes(self):
        # 已登记宿主端时，任一对象缺三端键之一即停止，两方向都无写。
        self.assertEqual(self.call("--apply")[0], 0)
        baseline = self.snapshot()
        old = self.git("rev-parse", "HEAD")
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            if obj["id"] == "subagents/LENS.md":
                for end in ("claude-code", "codex", "paseo"):
                    if end in obj["ends"]:
                        obj["ends"].pop(end)
                        break
        registry_file.write_text(json.dumps(registry))
        new = self.commit()
        self.git("checkout", "-q", old)
        rc, report = self.call("--preflight", new)
        self.assertEqual((rc, report["status"]), (2, "blocked"), report)
        self.assertIn("registry_end_missing", [e["code"] for e in report["errors"]])
        self.assertEqual((report["retirements"], self.snapshot()), ([], baseline))
        self.git("checkout", "-q", new)
        rc, report = self.call("--apply", "--previous", old)
        self.assertEqual((rc, report["status"]), (2, "blocked"), report)
        self.assertIn("registry_end_missing", [e["code"] for e in report["errors"]])
        self.assertEqual((report["retirements"], self.snapshot()), ([], baseline))

    def test_non_boolean_present_stops_without_writes(self):
        self.assertEqual(self.call("--apply")[0], 0)
        baseline = self.snapshot()
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            if obj["id"] == "subagents/LENS.md":
                obj["ends"]["codex"] = {"present": "false", "kind": "link", "paths": []}
        registry_file.write_text(json.dumps(registry))
        rc, report = self.call("--apply")
        self.assertEqual((rc, report["status"]), (2, "blocked"), report)
        self.assertIn("registry_end_invalid_present", [e["code"] for e in report["errors"]])
        self.assertEqual(self.snapshot(), baseline)

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
                obj["ends"].pop(end, None)
        registry_file.write_text(json.dumps(registry))
        (self.checkout / "tools/link-install.py").unlink()  # 旧基线真实没有安装器
        old_without_host = self.commit()
        registry_file.write_text(json.dumps(json.loads((ROOT / "tools/sync-targets.json").read_text())))
        self.commit()
        before = self.snapshot()
        rc, report = self.call("--apply", "--previous", old_without_host)
        self.assertEqual((rc, report["status"], report["retirements"]), (2, "blocked", []))
        self.assertIn("previous_without_host_installation", [e["code"] for e in report["errors"]])
        self.assertEqual((report["retirements"], self.snapshot()), ([], before))
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

    def test_native_codex_only_relocates_without_changing_process_home(self):
        # 显式采用 0.170.0 CODEX_HOME/skills 兼容根；不冒充 CLI 行为实测。
        install_root = self.root / "native-install"
        memory = install_root / ".luno/memory/GLOBAL.md"
        memory.parent.mkdir(parents=True)
        memory.write_bytes(b"synthetic native global\r\n\n")
        memory.chmod(0o600)
        codex_home = install_root / "codex-home"
        options = ("--home", str(install_root), "--ends", "codex",
                   "--codex-home", str(codex_home))
        # 原生两角色是只读前提：已接管现场的角色文件与注册先于首次发布存在。
        registry = json.loads((self.checkout / "tools/sync-targets.json").read_text())
        entries = []
        for obj in registry["objects"]:
            if obj["id"] in ("subagents/LENS.md", "subagents/FORGE.md"):
                target = obj["ends"]["codex"]
                _, content = INSTALL.render(obj, target, self.checkout, install_root,
                                            INSTALL.HomeTree(install_root), Path.read_bytes)
                path = codex_home / target["paths"][0].removeprefix("~/.codex/")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                path.chmod(0o600)
                entries.append("[agents.%s]\ndescription = %s\nconfig_file = \"roles/%s.toml\"\n"
                               % (Path(obj["id"]).stem,
                                  json.dumps(INSTALL.ROLE_DESCRIPTIONS[Path(obj["id"]).stem.lower()],
                                             ensure_ascii=False),
                                  Path(obj["id"]).stem.lower()))
        (codex_home / "config.toml").write_text("model = \"unrelated\"\n" + "".join(entries))
        (codex_home / "config.toml").chmod(0o600)
        before = self.snapshot()
        rc, report = self.call(*options)
        self.assertEqual((rc, report["status"]), (0, "planned"))
        self.assertFalse((codex_home / "AGENTS.md").exists())
        self.assertFalse((codex_home / "skills").exists())
        self.assertEqual(self.call(*options, "--apply")[0], 0)
        self.assertEqual(self.call(*options, "--check")[0], 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(report["ends"], ["codex"])
        self.assertEqual((codex_home / "AGENTS.md").read_bytes(),
                         (self.checkout / "prompt/LUNO.md").read_bytes() + b"\n" + memory.read_bytes())
        registry = json.loads((self.checkout / "tools/sync-targets.json").read_text())
        for obj in registry["objects"]:
            if obj["type"] == "skill" and obj["ends"]["codex"]["present"]:
                self.assertEqual(os.readlink(codex_home / "skills" / obj["id"]),
                                 str((self.checkout / obj["source"]).parent))
        for relative in (".claude", ".agents", ".codex", ".luno/homes"):
            self.assertFalse((install_root / relative).exists())
        rc, report = self.call(*options, "--apply")
        self.assertEqual((rc, report["created"]), (0, []))
        memory.write_bytes(b"updated synthetic global\n")
        self.assertEqual(self.call(*options, "--check")[0], 1)
        self.assertEqual(self.call(*options, "--apply")[0], 0)
        self.assertEqual(self.call(*options, "--check")[0], 0)
        override = codex_home / "AGENTS.override.md"
        override.write_bytes(b"synthetic override")
        rc, report = self.call(*options, "--apply")
        self.assertEqual(rc, 2)
        self.assertIn({"code": "agents_override_shadowing", "path": str(override)}, report["errors"])
        self.assertEqual(override.read_bytes(), b"synthetic override")

    def test_native_codex_layout_requires_selected_end_and_contained_root(self):
        cases = ((["--ends", "codex", "--codex-home", str(self.root / "outside")],
                  "codex_home_outside_install_root"),
                 (["--codex-home", str(self.home / "custom")], "invalid_native_codex_layout"))
        before = self.snapshot()
        for options, expected in cases:
            with self.subTest(options=options):
                rc, report = self.call(*options, "--apply")
                self.assertEqual(rc, 2)
                self.assertEqual(report["errors"][0]["code"], expected)
                self.assertEqual(self.snapshot(), before)

    def test_codex_only_does_not_touch_unselected_override_or_role_homes(self):
        role = self.home / ".luno/homes/lens-codex"
        role.mkdir(parents=True)
        (role / "AGENTS.override.md").write_bytes(b"unselected override")
        rc, report = self.call("--ends", "codex", "--apply")
        self.assertEqual(rc, 0, report["errors"])
        self.assertFalse((self.home / ".claude").exists())
        self.assertEqual(sorted(p.name for p in role.iterdir()), ["AGENTS.override.md"])
        self.assertFalse((self.home / ".luno/homes/forge-codex").exists())

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


class NativeRoleTest(unittest.TestCase):
    """原生 Codex 两角色：TOML 字节、注册只读核对与只读准入；不读真实配置。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-role-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home/paseo"
        self.codex = self.home / ".codex"
        (self.codex / "roles").mkdir(parents=True)
        memory = self.home / ".luno/memory"
        memory.mkdir(parents=True)
        self.global_file = memory / "GLOBAL.md"
        self.global_file.write_bytes(b"private fixture\n")
        self.global_file.chmod(0o600)
        self.tree = INSTALL.HomeTree(self.home)
        self.addCleanup(self.tree.close)

    def target(self, role):
        for obj in json.loads((ROOT / "tools/sync-targets.json").read_bytes())["objects"]:
            if obj["id"] == "subagents/" + role.upper() + ".md":
                return obj, obj["ends"]["codex"]
        raise AssertionError(role)

    def render(self, role, raw=None, model="fixture-model", effort="fixture-effort"):
        obj, target = self.target(role)
        raw = (ROOT / obj["source"]).read_bytes() if raw is None else raw
        path, content = INSTALL.render({"id": obj["id"], "source": obj["source"], "type": "subagent"},
                                       dict(target, model=model, model_reasoning_effort=effort),
                                       self.root, self.home, self.tree, lambda _: raw)
        self.assertIsNone(path)
        return content

    @staticmethod
    def unescape(value):
        table = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
        out, index = [], 0
        while index < len(value):
            if value[index] == "\\":
                out.append(table[value[index + 1]])
                index += 2
            else:
                out.append(value[index])
                index += 1
        return "".join(out)

    def test_each_role_is_three_single_line_basic_strings_plus_lf(self):
        for role in ("lens", "forge"):
            content = self.render(role)
            lines = content.split(b"\n")
            self.assertEqual(lines[-1], b"")
            self.assertEqual(len(lines), 4)
            self.assertNotIn(b"\r", content)
            text = content.decode("utf-8")
            self.assertEqual([line.split(" = ")[0] for line in text.splitlines()],
                             ["model", "model_reasoning_effort", "developer_instructions"])
            expected = (ROOT / ("subagents/" + role.upper() + ".md")).read_bytes()
            self.assertEqual(self.unescape(text.splitlines()[2].split(' = "', 1)[1][:-1]).encode("utf-8"),
                             expected)

    def test_instruction_bytes_survive_crlf_trailing_lf_and_non_ascii(self):
        raw = "一\r\n二 \"引号\" \\反斜杠\t尾\r\n\n".encode("utf-8")
        text = self.render("lens", raw=raw).decode("utf-8")
        self.assertEqual(self.unescape(text.splitlines()[2].split(' = "', 1)[1][:-1]).encode("utf-8"), raw)
        self.assertTrue(text.endswith('"\n'))

    def registration_errors(self, role="LENS"):
        action = {"object": "subagents/" + role + ".md",
                  "path": self.codex / ("roles/" + role.lower() + ".toml")}
        return INSTALL.native_role_registration(self.tree, self.codex, [action]), action

    def test_registration_accepts_exact_fields_and_rejects_drift(self):
        descriptions = INSTALL.ROLE_DESCRIPTIONS
        for role in ("LENS", "FORGE"):
            path = self.codex / ("roles/" + role.lower() + ".toml")
            path.write_bytes(self.render(role.lower()))
            path.chmod(0o600)
        config = self.codex / "config.toml"
        config.write_text('model = "unrelated"\n[agents.LENS]\ndescription = %s\nconfig_file = "roles/lens.toml"\n'
                          '[agents.FORGE]\ndescription = %s\nconfig_file = "roles/forge.toml"\n'
                          % (json.dumps(descriptions["lens"], ensure_ascii=False),
                             json.dumps(descriptions["forge"], ensure_ascii=False)))
        config.chmod(0o600)
        self.assertEqual(self.registration_errors()[0], [])
        cases = ((("roles/lens.toml", "roles/other.toml"), "native_role_registration_config_file"),
                 ((descriptions["lens"], descriptions["lens"] + "x"), "native_role_registration_description"),
                 (("\nconfig_file", "\nextra = \"y\"\nconfig_file"), "native_role_registration_unknown_key"),
                 (('config_file = "roles/lens.toml"', "config_file = 1"), "native_role_registration_type"))
        for (old, new), code in cases:
            changed = config.read_text().replace(old, new, 1)
            config.write_text(changed)
            self.assertIn(code, [e["code"] for e in self.registration_errors()[0]], code)
            config.write_text(changed.replace(new, old, 1))

    def test_missing_registration_and_missing_file_block(self):
        config = self.codex / "config.toml"
        config.write_text("[agents.LENS]\ndescription = \"x\"\nconfig_file = \"roles/lens.toml\"\n")
        config.chmod(0o600)
        path = self.codex / "roles/lens.toml"
        path.write_bytes(self.render("lens"))
        path.chmod(0o600)
        self.assertEqual([e["code"] for e in self.registration_errors()[0]],
                         ["native_role_registration_description"])
        config.unlink()
        self.assertEqual([e["code"] for e in self.registration_errors()[0]],
                         ["native_role_registration_missing"])
        content = self.render("lens")
        action = {"object": "subagents/LENS.md", "kind": "native-role",
                  "path": self.codex / "roles/lens.toml", "content": content, "public": []}
        action["path"].unlink()
        self.assertEqual(INSTALL.state(action, self.tree), "create")
        action["path"].write_bytes(b"drifted\n")
        action["path"].chmod(0o600)
        self.assertEqual(INSTALL.state(action, self.tree), "conflict")
        action["prior"] = b"drifted\n"
        self.assertEqual(INSTALL.state(action, self.tree), "update")

    def git(self, checkout, *args):
        return subprocess.run(["git", "-C", str(checkout), *args], env=self.env,
                              capture_output=True, check=True).stdout

    def commit(self, checkout, message):
        self.git(checkout, "add", ".")
        self.git(checkout, "-c", "user.name=t", "-c", "user.email=t@local", "commit", "-qm", message)

    def make_site(self, distinct_blobs):
        """合成夹具：O 提交（旧登记）→ 已接管现场 → next 分支 N 提交（新登记）。

        distinct_blobs=True 时 N 的工具字节与 O 不同，用来演练跨 blob 绑定；不是历史快照。
        """
        checkout = self.root / "checkout"
        checkout.mkdir()
        for name in ("skills", "prompt", "subagents", "tools"):
            shutil.copytree(ROOT / name, checkout / name)
        registry = json.loads((ROOT / "tools/sync-targets.json").read_bytes())
        for obj in registry["objects"]:
            if obj["id"] in ("subagents/LENS.md", "subagents/FORGE.md"):
                obj["ends"]["codex"] = {"present": False}
        registry_path = checkout / "tools/sync-targets.json"
        registry_path.write_bytes(json.dumps(registry, ensure_ascii=False, indent=2).encode() + b"\n")
        self.env = {"HOME": str(self.home), "PATH": os.environ["PATH"], "LC_ALL": "C.UTF-8",
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig")}
        (self.root / "gitconfig").write_bytes(b"")
        self.git(checkout, "init", "-q", "-b", "main")
        self.commit(checkout, "O")
        layout = ("--ends", "codex", "--codex-home", str(self.codex))
        base = [sys.executable, "-B", str(checkout / "tools/link-install.py"),
                "--checkout", str(checkout), "--home", str(self.home), *layout]
        applied = subprocess.run([*base, "--apply"], env=self.env, capture_output=True)
        self.assertEqual(applied.returncode, 0, applied.stdout)
        entries = []
        for role in ("LENS", "FORGE"):
            path = self.codex / ("roles/" + role.lower() + ".toml")
            _, target = self.target(role.lower())
            path.write_bytes(self.render(role.lower(), model=target["model"],
                                         effort=target["model_reasoning_effort"]))
            path.chmod(0o600)
            entries.append("[agents.%s]\ndescription = %s\nconfig_file = \"roles/%s.toml\"\n"
                           % (role, json.dumps(INSTALL.ROLE_DESCRIPTIONS[role.lower()], ensure_ascii=False),
                              role.lower()))
        config = self.codex / "config.toml"
        config.write_text("model = \"unrelated\"\n" + "".join(entries))
        config.chmod(0o600)
        registry_path.write_bytes((ROOT / "tools/sync-targets.json").read_bytes())
        if distinct_blobs:
            tool = checkout / "tools/link-install.py"
            tool.write_bytes(tool.read_bytes() + b"\n# native-role candidate\n")
        self.git(checkout, "checkout", "-q", "-b", "next")
        self.commit(checkout, "N")
        new_head = self.git(checkout, "rev-parse", "HEAD").decode().strip()
        self.git(checkout, "checkout", "-q", "main")
        old_head = self.git(checkout, "rev-parse", "HEAD").decode().strip()
        blobs = [self.git(checkout, "rev-parse", c + ":tools/link-install.py").decode().strip()
                 for c in (old_head, new_head)]
        if distinct_blobs:
            copy = self.root / "next-copy"
            shutil.copytree(checkout, copy)
            self.git(copy, "checkout", "-q", "next")
        else:
            copy = checkout
        return checkout, copy, layout, old_head, new_head, blobs

    def admission(self, copy, checkout, layout, target, blobs):
        return subprocess.run(
            [sys.executable, "-B", str(copy / "tools/link-install.py"), "--checkout", str(checkout),
             "--home", str(self.home), *layout, "--check-native-role-adoption", target,
             "--adoption-blobs", ",".join(blobs)], env=self.env, capture_output=True)

    def test_admission_binds_real_old_blob_and_compares_full_projection(self):
        checkout, copy, layout, old, new, blobs = self.make_site(distinct_blobs=True)
        self.assertNotEqual(blobs[0], blobs[1])
        before = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        run = self.admission(copy, checkout, layout, new, blobs)
        report = json.loads(run.stdout)
        self.assertEqual((run.returncode, report["status"], report["errors"]), (0, "match", []))
        self.assertEqual(report["previousInstallerBlob"], blobs[0])
        self.assertEqual(report["targetInstallerBlob"], blobs[1])
        self.assertEqual(report["previousHead"], old)
        added = [a for a in report["actions"] if a.get("state") != "match"]
        self.assertEqual(added, [])
        self.assertEqual(len([a for a in report["actions"] if a["kind"] == "native-role"]), 2)
        self.assertEqual({str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}, before)
        run = self.admission(copy, checkout, layout, new, [blobs[1], blobs[1]])
        report = json.loads(run.stdout)
        self.assertEqual(run.returncode, 2)
        self.assertIn("adoption_previous_blob_mismatch", [e["code"] for e in report["errors"]])
        # 旧工具真实投影里的动作缺失（真实旧 check rc0，但新登记删掉了一个旧技能动作）：
        self.git(checkout, "checkout", "-q", "next")
        registry = json.loads((checkout / "tools/sync-targets.json").read_bytes())
        for obj in registry["objects"]:
            if obj["id"] == "luno-core":
                obj["ends"]["codex"] = {"present": False}
        (checkout / "tools/sync-targets.json").write_bytes(
            json.dumps(registry, ensure_ascii=False, indent=2).encode() + b"\n")
        self.commit(checkout, "N2")
        target = self.git(checkout, "rev-parse", "HEAD").decode().strip()
        self.git(checkout, "checkout", "-q", "main")
        run = self.admission(copy, checkout, layout, target, [blobs[0], blobs[1]])
        report = json.loads(run.stdout)
        self.assertEqual(run.returncode, 2)
        self.assertIn("adoption_lost_action", [e["code"] for e in report["errors"]])

    def test_admission_dirty_checkout_is_blocked_with_json(self):
        checkout, copy, layout, old, new, blobs = self.make_site(distinct_blobs=True)
        (checkout / "skills/luno-ops/SKILL.md").write_bytes(b"dirty\n")
        run = self.admission(copy, checkout, layout, new, blobs)
        report = json.loads(run.stdout)
        self.assertEqual((run.returncode, report["status"]), (2, "blocked"))
        self.assertIn("checkout_dirty", [e["code"] for e in report["errors"]])

    def test_same_blob_update_runs_preflight_apply_check_and_rejects_third_state(self):
        checkout, copy, layout, old, new, blobs = self.make_site(distinct_blobs=False)
        tool = str(checkout / "tools/link-install.py")

        def run(*args):
            return subprocess.run([sys.executable, "-B", tool, "--checkout", str(checkout),
                                   "--home", str(self.home), *layout, *args],
                                  env=self.env, capture_output=True)

        source = checkout / "subagents/LENS.md"
        source.write_bytes(source.read_bytes() + b"\n\xe8\xa1\xa5\xe4\xb8\x81\n")
        self.git(checkout, "checkout", "-q", "next")
        self.git(checkout, "checkout", "-q", "-b", "future")
        self.commit(checkout, "F")
        future = self.git(checkout, "rev-parse", "HEAD").decode().strip()
        self.git(checkout, "checkout", "-q", "main")
        report = json.loads(run("--preflight", future).stdout)
        self.assertEqual(report["status"], "ready", report["errors"])
        self.assertEqual([e["code"] for e in report["errors"]], [])
        self.git(checkout, "checkout", "-q", "future")
        run_apply = run("--apply", "--previous", new)
        report = json.loads(run_apply.stdout)
        self.assertEqual((run_apply.returncode, report["status"]), (0, "completed"), report["errors"])
        self.assertNotIn("prior", run_apply.stdout.decode())
        content = (self.codex / "roles/lens.toml").read_bytes()
        _, target = self.target("lens")
        expected, rendered = INSTALL.render(
            {"id": "subagents/LENS.md", "source": "subagents/LENS.md", "type": "subagent"},
            dict(target, model=target["model"], model_reasoning_effort=target["model_reasoning_effort"]),
            checkout, self.home, INSTALL.HomeTree(self.home), Path.read_bytes)
        self.assertEqual(content, rendered)
        self.assertEqual(run("--apply", "--previous", new).returncode, 0)
        self.assertEqual(json.loads(run("--apply", "--previous", new).stdout)["created"], [])
        forge = self.codex / "roles/forge.toml"
        forge.write_bytes(b"third state\n")
        forge.chmod(0o600)
        before = forge.read_bytes()
        blocked = run("--apply", "--previous", new)
        report = json.loads(blocked.stdout)
        self.assertEqual((blocked.returncode, report["status"]), (2, "blocked"))
        self.assertEqual(forge.read_bytes(), before)

    def test_registration_ignores_tables_inside_multiline_strings(self):
        config = self.codex / "config.toml"
        config.write_text('note = """\n[agents.LENS]\ndescription = "fake"\nconfig_file = "roles/lens.toml"\n'
                          '[agents.FORGE]\ndescription = "fake"\nconfig_file = "roles/forge.toml"\n"""\n'
                          '[ignored]\nkey = "SYNTHETIC-SECRET-MARKER"\n')
        config.chmod(0o600)
        for role in ("LENS", "FORGE"):
            path = self.codex / ("roles/" + role.lower() + ".toml")
            path.write_bytes(self.render(role.lower()))
            path.chmod(0o600)
        errors, _ = self.registration_errors()
        self.assertEqual([e["code"] for e in errors], ["native_role_registration_missing"])
        self.assertNotIn("SYNTHETIC-SECRET-MARKER", json.dumps(errors))

if __name__ == "__main__":
    unittest.main()

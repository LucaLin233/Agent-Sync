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
        self.home = self.root / "home/example"
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

    def commit_if_dirty(self):
        """登记已是目标形态时不再造空提交：夹具基线必须保持可提交的确定状态。"""
        if self.git("status", "--porcelain"):
            self.commit()

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
            for destination in (f".agents/skills/{name}",
                                f".luno/homes/lens-codex/skills/{name}",
                                f".luno/homes/forge-codex/skills/{name}",
                                f".luno/homes/lens-gdr/skills/{name}",
                                f".luno/homes/forge-gdr/skills/{name}"):
                self.assertEqual(os.readlink(self.home / destination), str(self.checkout / obj["source"]).rsplit("/", 1)[0])
        codex = self.home / ".codex/AGENTS.md"
        self.assertEqual(codex.read_bytes(), (self.checkout / "prompt/LUNO.md").read_bytes() + b"\n" + self.global_file.read_bytes())
        for role in ("lens", "forge"):
            for provider, entry in (("codex", "AGENTS.md"), ("gdr", "AGENTS.md")):
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
        self.assertEqual(self.snapshot(), before)

    def test_existing_public_file_and_wrong_link_are_conflicts(self):
        codex = self.home / ".codex"
        codex.mkdir()
        (codex / "AGENTS.md").write_bytes(b"my existing instructions")
        target = self.root / "unmanaged"
        target.write_bytes(b"leave target unchanged")
        (self.home / ".agents/skills").mkdir(parents=True)
        (self.home / ".agents/skills/luno-core").symlink_to(target)
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
        registry = json.loads((self.checkout / "tools/sync-targets.json").read_text())
        entries = [self.home / path.removeprefix("~/")
                   for obj in registry["objects"] for end in ("codex", "paseo")
                   for path in obj["ends"][end].get("paths", ()) if path.endswith("/AGENTS.md")]
        self.assertTrue(entries)
        for entry in entries:
            with self.subTest(home=entry.parent):
                override = entry.with_name("AGENTS.override.md")
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
                self.assertFalse((self.home / ".agents").exists())
                self.assertEqual(sorted(p.name for p in outside.iterdir()), ["GLOBAL.md", "SKILL.md"])
                path.unlink()
                if relative == ".luno/memory":
                    path.mkdir()
                    self.global_file.write_bytes(b"global fixture")

    def test_parent_replacement_after_plan_cannot_redirect_writes(self):
        parent = self.home / ".codex"
        parent.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        tree = INSTALL.HomeTree(self.home)
        self.addCleanup(tree.close)
        actions, errors = INSTALL.plan(self.checkout, self.home, tree)
        self.assertEqual(errors, [])
        parent.rename(self.home / "checked-codex")
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
    if action["path"].name == "AGENTS.md":
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
        self.assertTrue((self.home / ".luno/homes/forge-codex/AGENTS.md").is_symlink())
        artifact = self.home / ".luno/generated/codex/AGENTS.md"
        staging = artifact.with_name(".AGENTS.md.link-install.tmp")
        self.assertNotIn(b"NEW_VERSION", artifact.read_bytes())
        self.assertEqual(staging.read_bytes(), b"INTERRUPTED_PARTIAL_CONTENT")
        login = self.home / ".luno/homes/forge-codex/auth.json"
        login.write_bytes(b"SYNTH_LOGIN")
        login.chmod(0o600)
        self.git("checkout", "-q", old)
        rc, report = self.call("--apply", "--previous", new)
        self.assertEqual((rc, report["status"]), (0, "completed"), report["errors"])
        self.assertFalse((self.home / ".luno/homes/forge-gdr/AGENTS.md").is_symlink())
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
        registry["objects"][0]["ends"]["codex"]["paths"].append("~/.codex/user.md")
        registry_file.write_text(json.dumps(registry))
        new = self.commit()
        self.git("checkout", "-q", old)
        (self.home / ".codex/user.md").write_bytes(b"UNMANAGED")
        before = self.snapshot()
        self.assertEqual(self.call("--preflight", new)[0], 2)
        self.assertEqual(self.git("rev-parse", "HEAD"), old)
        self.assertEqual(self.snapshot(), before)

    def test_parent_symlink_cannot_redirect_installer_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep").write_bytes(b"untouched")
        (self.home / ".codex").symlink_to(outside)
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

    def upgrade_site(self):
        """旧版本安装器已装好的现场；目标提交换回当前工具字节。"""
        tool = self.checkout / "tools/link-install.py"
        new_bytes = tool.read_bytes()
        tool.write_bytes(new_bytes + b"\n# previous installer\n")
        old = self.commit()
        subprocess.run([sys.executable, "-B", str(tool), "--checkout", str(self.checkout),
                        "--home", str(self.home), "--apply"], env=self.env, check=True,
                       capture_output=True)
        tool.write_bytes(new_bytes)
        new = self.commit()
        self.git("checkout", "-q", old)
        return old, new

    def test_installer_upgrade_check_allows_only_identical_projection(self):
        old, new = self.upgrade_site()
        baseline = self.snapshot()
        preflight = subprocess.run(
            [sys.executable, "-B", str(self.checkout / "tools/link-install.py"),
             "--checkout", str(self.checkout), "--home", str(self.home), "--preflight", new],
            env=self.env, capture_output=True)
        report = json.loads(preflight.stdout)
        self.assertEqual((preflight.returncode, report["status"]), (2, "blocked"))
        self.assertIn("installer_changed", [e["code"] for e in report["errors"]])
        for ends in ((), ("--ends", "paseo")):
            with self.subTest(ends=ends):
                rc, report = self.call("--check-installer-upgrade", new, *ends)
                self.assertEqual((rc, report["status"], report["errors"]), (0, "match", []))
                self.assertEqual((report["previousHead"], report["targetHead"]), (old, new))
                self.assertEqual(self.snapshot(), baseline)
        self.git("checkout", "-q", new)
        self.assertEqual(self.call("--check")[0], 0)

    def test_installer_upgrade_blocks_target_only_layout_and_source_change(self):
        old, new = self.upgrade_site()
        self.git("checkout", "-q", new)
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_bytes())
        skill = next(obj for obj in registry["objects"]
                     if obj["type"] == "skill" and obj["ends"]["codex"]["present"])
        skill["ends"]["codex"]["paths"].append("~/.codex/upgrade-extra.md")
        registry_file.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
        target = self.commit()
        self.git("checkout", "-q", old)
        (self.home / ".codex/upgrade-extra.md").symlink_to(
            str((self.checkout / skill["source"]).parent))
        before = self.snapshot()
        rc, report = self.call("--check-installer-upgrade", target)
        codes = [e["code"] for e in report["errors"]]
        self.assertEqual((rc, report["status"]), (2, "blocked"))
        self.assertIn("upgrade_projection_mismatch", codes)
        self.assertIn("upgrade_sources_changed", codes)
        self.assertEqual(self.snapshot(), before)

    def test_installer_upgrade_rejects_existing_override(self):
        old, new = self.upgrade_site()
        # 旧夹具是当前工具加注释，两版都带严格 override 检查；此处只核目标模式仍拒绝。
        override = self.home / ".luno/homes/lens-gdr/AGENTS.override.md"
        override.write_bytes(b"USER OVERRIDE")
        before = self.snapshot()
        rc, report = self.call("--check-installer-upgrade", new)
        self.assertEqual((rc, report["status"]), (2, "blocked"))
        self.assertIn("agents_override_shadowing", [e["code"] for e in report["errors"]])
        self.assertEqual(self.snapshot(), before)

    def test_registry_layout_change_stops_before_writes(self):
        # 安装器相同，但登记把同一公开入口推导到别的目标，同样不算已证明的同布局。
        self.assertEqual(self.call("--apply")[0], 0)
        baseline = self.snapshot()
        old = self.git("rev-parse", "HEAD")
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            if obj["id"] == "luno-ops":
                obj["source"] = "skills/luno-authoring/SKILL.md"
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
        link_dir = self.home / ".luno/homes/lens-codex"
        old_staging = generated.with_name(".AGENTS.md.link-install.tmp")
        link_staging = link_dir / ".AGENTS.md.link-install.tmp.0123456789abcdef"
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
        public = self.home / ".codex/AGENTS.md"
        generated = self.home / ".luno/generated/codex/AGENTS.md"
        old = self.git("rev-parse", "HEAD")
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            for end in ("codex", "paseo"):
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
                obj["ends"]["paseo"] = {"present": False}
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
            for end in ("codex", "paseo"):
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
                for end in ("codex", "paseo"):
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
            for end in ("codex", "paseo"):
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
        paths = (".codex/auth.json", ".codex/config.toml")
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
        for relative in (".agents", ".codex", ".luno/homes"):
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
        self.assertEqual(sorted(p.name for p in role.iterdir()), ["AGENTS.override.md"])
        self.assertFalse((self.home / ".luno/homes/forge-codex").exists())

    def test_paseo_official_example_and_install(self):
        config = json.loads((ROOT / "platforms/paseo/config.example.json").read_text())
        self.assertNotIn("listen", config["daemon"])
        self.assertEqual(config["daemon"]["mcp"],
                         {"enabled": True, "injectIntoAgents": True})
        providers = config["agents"]["providers"]
        enabled = {name: entry for name, entry in providers.items() if entry.get("enabled", True)}
        gateways = {}
        for provider_id, fragment in enabled.items():
            self.assertRegex(provider_id, r"^(codex|claude)-[a-z0-9]+(?:-[a-z0-9]+)*$")
            runtime, gateway = provider_id.split("-", 1)
            self.assertEqual(fragment["extends"], runtime)
            gateways.setdefault(gateway, set()).add(runtime)
            if runtime == "codex":
                self.assertIn('model_provider="%s"' % gateway, fragment["command"])
                self.assertEqual(fragment["env"], {"CODEX_HOME": "/home/example/agent/codex-home"})
            else:
                self.assertEqual(fragment["env"], {
                    "CLAUDE_CONFIG_DIR": "/home/example/agent/claude-home",
                    "ANTHROPIC_BASE_URL": "https://" + gateway + ".example.invalid",
                })
        self.assertTrue(gateways)
        for runtimes in gateways.values():
            self.assertEqual(runtimes, {"codex", "claude"})
        for builtin in ("claude", "codex", "copilot", "opencode", "pi", "omp"):
            self.assertEqual(providers[builtin], {"enabled": False})

        profiles = config["daemon"]["agentProfiles"]
        # Match the provider and Profile ID contract documented under 派发通道.
        self.assertCountEqual([entry["id"] for entry in profiles],
                              [gateway + "-" + role for gateway in gateways
                               for role in ("luno", "lens", "forge")])
        for entry in profiles:
            gateway, role = entry["id"].rsplit("-", 1)
            self.assertIn(entry["provider"], enabled)
            self.assertEqual(entry["provider"], "codex-" + gateway)
            self.assertEqual(entry["model"], "deepseek-flash" if role == "forge" else "gpt-6.2-sol")
            self.assertEqual(entry["modeId"], "full-access")
            self.assertEqual(entry["thinkingOptionId"], "high")
            self.assertEqual(entry["options"], {"service_tier": "default"})

        # 角色启动段改由受管生成入口渲染：示例不再承载私人或其他正文，也不留占位路径。
        self.assertNotIn("appendSystemPrompt", config["daemon"])
        self.assertEqual(set(config["daemon"]), {"mcp", "agentProfiles"})
        self.assertNotIn("<AGENT_SYNC_CHECKOUT>", json.dumps(config))
        self.assertNotIn("paseo_role", json.dumps(config))
        self.assertNotIn("paseo_upstream", json.dumps(config))
        self.assertFalse((ROOT / "platforms/paseo/plugin").exists())
        self.assertFalse((ROOT / "platforms/paseo/codex-role-verification-v0.17.1.patch").exists())
        self.assertFalse((ROOT / "platforms/paseo/LICENSE.upstream.txt").exists())
        self.assertNotIn("/root/agent", str(config))

        self.assertEqual(self.call("--apply")[0], 0)
        registration = json.loads((self.checkout / "tools/sync-targets.json").read_text())
        registered = {obj["id"]: obj["ends"]["paseo"]["paths"] for obj in registration["objects"]
                      if obj["type"] == "subagent" and obj["ends"]["paseo"].get("present")}
        for role, key in (("LENS", "lens-codex"), ("FORGE", "forge-codex"),
                          ("LENS", "lens-gdr"), ("FORGE", "forge-gdr")):
            role_home = self.home / ".luno/homes" / key
            self.assertEqual((role_home / "AGENTS.md").read_bytes(),
                             (self.checkout / "subagents" / (role + ".md")).read_bytes())
            self.assertIn("~/.luno/homes/" + key + "/AGENTS.md", registered["subagents/" + role + ".md"])

    def test_paseo_select_runs_real_command_on_worktree_diff(self):
        tests = self.checkout / "tests"
        tests.mkdir()
        runner = (ROOT / "tests/run-tests.sh").read_text()
        start = runner.index("CASES='\n")
        end = runner.index("\n'\n", start) + 3
        rows = "check-rules.py|smoke|echo smoke:ran|1\ntest-link-install.py|host|echo host:ran|0\n"
        (tests / "run-tests.sh").write_text(runner[:start] + "CASES='\n" + rows + "'\n" + runner[end:])
        shutil.copyfile(ROOT / "tests/test_paths.py", tests / "test_paths.py")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        command = json.loads((ROOT / "paseo.json").read_text())["scripts"]["select"]["command"]

        def ran():
            proc = subprocess.run(["bash", "-c", command], cwd=self.checkout, env=self.env,
                                  capture_output=True, text=True, check=False, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return {name for name, marker in (("smoke", "smoke:ran"), ("host", "host:ran"))
                    if marker in proc.stdout}

        self.assertEqual(ran(), {"smoke"})
        link = self.checkout / "tools/link-install.py"
        link.write_text(link.read_text() + "\n# worktree edit\n")
        self.assertEqual(ran(), {"smoke", "host"})
        self.git("add", "tools/link-install.py")
        self.assertEqual(ran(), {"smoke", "host"})


    PASEO_SOURCE = ("--ends", "codex", "--codex-global-source", "paseo-append-system-prompt")

    def set_role_startup(self, value):
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        target = next(obj for obj in registry["objects"] if obj["id"] == "prompt/LUNO.md")["ends"]["codex"]
        if value is None:
            target.pop("paseoRoleStartup", None)
        else:
            target["paseoRoleStartup"] = value
        registry_file.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")

    def expected_role_startup(self):
        """需求原文独立构造的期望字节：两段启动文本、两个 LF、改写后的唯一职责段锚点。"""
        source = (self.checkout / "prompt/LUNO.md").read_bytes()
        marker = "你是 LUNO，".encode("utf-8")
        self.assertEqual(source.count(b"\n" + marker), 1)
        index = source.index(marker)
        head = (
            "首条任务正文的第一行恰为 `角色：LUNO`、`角色：LENS` 或 `角色：FORGE` 时，采用对应角色，"
            "任务正文紧随其后。没有上述角色行时按 LUNO。\n\n"
            "角色为 LENS 或 FORGE 时，须在开始任务前完整读取并遵循对应的已部署受管原文。"
            "LENS 原文位于 `" + str(self.checkout / "subagents/LENS.md") + "`，"
            "FORGE 原文位于 `" + str(self.checkout / "subagents/FORGE.md") + "`。\n\n"
        ).encode("utf-8")
        return (head + source[:index] + "仅当前会话角色为 LUNO 时适用本段。你".encode("utf-8")
                + source[index + len(marker):])

    def test_role_startup_defaults_to_unchanged_output(self):
        # A 的兼容面：缺键或显式 false 都不改默认输出，也不改既有显式模式的输出。
        for value in (None, False):
            with self.subTest(value=value):
                self.set_role_startup(value)
                self.assertEqual(self.call("--apply")[0], 0)
                self.assertEqual((self.home / ".codex/AGENTS.md").read_bytes(),
                                 (self.checkout / "prompt/LUNO.md").read_bytes() + b"\n"
                                 + self.global_file.read_bytes())
                self.assertEqual(self.call(*self.PASEO_SOURCE, "--apply")[0], 0)
                self.assertEqual((self.home / ".codex/AGENTS.md").read_bytes(),
                                 (self.checkout / "prompt/LUNO.md").read_bytes())
                self.assertEqual(self.call(*self.PASEO_SOURCE, "--check")[0], 0)

    def test_role_startup_renders_only_in_explicit_paseo_source_mode(self):
        self.set_role_startup(True)
        # 内嵌默认模式仍只拼 prompt、一个 LF 和 GLOBAL，不插入角色启动段。
        self.assertEqual(self.call("--apply")[0], 0)
        self.assertEqual((self.home / ".codex/AGENTS.md").read_bytes(),
                         (self.checkout / "prompt/LUNO.md").read_bytes() + b"\n"
                         + self.global_file.read_bytes())
        self.assertEqual(self.call(*self.PASEO_SOURCE, "--check")[0], 1)
        self.assertEqual(self.call(*self.PASEO_SOURCE, "--apply")[0], 0)
        generated = (self.home / ".codex/AGENTS.md").read_bytes()
        self.assertEqual(generated, self.expected_role_startup())
        self.assertNotIn("你是 LUNO，".encode("utf-8"), generated)
        self.assertEqual(generated.count("仅当前会话角色为 LUNO 时适用本段。".encode("utf-8")), 1)
        # 生成文件仍只经公开入口核归属，内容不含私人 GLOBAL。
        self.assertNotIn(b"private global fixture", generated)
        self.assertEqual(self.call(*self.PASEO_SOURCE, "--check")[0], 0)

    def test_role_startup_blocks_on_missing_or_duplicated_anchor(self):
        self.set_role_startup(True)
        prompt = self.checkout / "prompt/LUNO.md"
        original = prompt.read_bytes()
        cases = (("replaced", lambda raw: raw.replace("你是 LUNO，".encode("utf-8"), "你是助手，".encode("utf-8"))),
                 ("duplicated", lambda raw: raw + "\n你是 LUNO，第二处\n".encode("utf-8")))
        for label, mutate in cases:
            with self.subTest(case=label):
                prompt.write_bytes(mutate(original))
                before = self.snapshot()
                for mode in ((), ("--apply",)):
                    rc, report = self.call(*self.PASEO_SOURCE, *mode)
                    self.assertEqual(rc, 2)
                    self.assertIn("role_startup_anchor", [e["code"] for e in report["errors"]])
                    self.assertEqual(self.snapshot(), before)
        prompt.write_bytes(original)

    def test_same_blob_registry_enable_updates_only_generated_and_restores(self):
        # A→B：只改登记开关，安装器 blob 相同；预检只预期一个生成文件，回退恢复原字节。
        self.set_role_startup(None)
        self.commit_if_dirty()
        self.assertEqual(self.call(*self.PASEO_SOURCE, "--apply")[0], 0)
        generated = self.home / ".codex/AGENTS.md"
        a_bytes = generated.read_bytes()
        self.assertEqual(a_bytes, (self.checkout / "prompt/LUNO.md").read_bytes())
        baseline = self.snapshot()
        old = self.git("rev-parse", "HEAD")
        self.set_role_startup(True)
        new = self.commit()
        self.assertEqual(self.git("rev-parse", old + ":tools/link-install.py"),
                         self.git("rev-parse", new + ":tools/link-install.py"))
        self.git("checkout", "-q", old)
        rc, report = self.call(*self.PASEO_SOURCE, "--preflight", new)
        self.assertEqual((rc, report["status"]), (0, "ready"), report["errors"])
        changed = [action for action in report["actions"] if action["state"] != "match"]
        self.assertEqual([(Path(action["path"]).name, action["state"]) for action in changed],
                         [("AGENTS.md", "update")])
        self.assertEqual(self.snapshot(), baseline)
        self.git("checkout", "-q", new)
        rc, report = self.call(*self.PASEO_SOURCE, "--apply", "--previous", old)
        self.assertEqual((rc, report["status"], report["retirements"]), (0, "completed", []))
        enabled = generated.read_bytes()
        self.assertEqual(enabled, self.expected_role_startup())
        artifact = ".luno/generated/codex/AGENTS.md"
        rest = {k: v for k, v in self.snapshot().items() if k != artifact}
        self.assertEqual(rest, {k: v for k, v in baseline.items() if k != artifact})
        self.assertEqual(self.snapshot()[".codex/AGENTS.md"], baseline[".codex/AGENTS.md"])
        self.assertEqual(self.call(*self.PASEO_SOURCE, "--check")[0], 0)
        # B→A：同 blob 反向 apply --previous，唯一生成文件回到 A 的原始字节。
        self.git("checkout", "-q", old)
        rc, report = self.call(*self.PASEO_SOURCE, "--apply", "--previous", new)
        self.assertEqual((rc, report["status"], report["retirements"]), (0, "completed", []))
        self.assertEqual(generated.read_bytes(), a_bytes)
        self.assertEqual(self.snapshot(), baseline)
        self.assertEqual(self.call(*self.PASEO_SOURCE, "--check")[0], 0)

    def test_installer_upgrade_with_explicit_source_stays_match(self):
        # 旧→A：安装器自变、登记未变；显式来源现场用旧工具自己的 check 与 A 投影一致，全程不写。
        self.set_role_startup(None)
        self.commit_if_dirty()
        tool = self.checkout / "tools/link-install.py"
        new_bytes = tool.read_bytes()
        tool.write_bytes(new_bytes + b"\n# previous installer\n")
        old = self.commit()
        self.assertEqual(self.call(*self.PASEO_SOURCE, "--apply")[0], 0)
        baseline = self.snapshot()
        tool.write_bytes(new_bytes)
        new = self.commit()
        self.git("checkout", "-q", old)
        rc, report = self.call(*self.PASEO_SOURCE, "--check-installer-upgrade", new)
        self.assertEqual((rc, report["status"], report["errors"]), (0, "match", []))
        self.assertNotEqual(report["previousInstallerBlob"], report["targetInstallerBlob"])
        self.assertEqual(self.snapshot(), baseline)
        self.git("checkout", "-q", new)
        self.assertEqual(self.call(*self.PASEO_SOURCE, "--check")[0], 0)

    def test_role_startup_rejects_non_boolean_registration(self):
        self.set_role_startup("true")
        before = self.snapshot()
        rc, report = self.call(*self.PASEO_SOURCE, "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("registry_end_invalid_role_startup", [e["code"] for e in report["errors"]])
        self.assertEqual(self.snapshot(), before)

    def enable_claude(self, present=True):
        """夹具登记补 claude 端：prompt 用 claude-main 生成，skill 直接软链。"""
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        for obj in registry["objects"]:
            if obj["type"] == "prompt":
                obj["ends"]["claude"] = {"present": present, "kind": "generated",
                                         "paths": ["~/.claude/CLAUDE.md"], "renderer": "claude-main"}
            elif obj["type"] == "skill" and obj["ends"]["codex"]["present"]:
                obj["ends"]["claude"] = {"present": present, "kind": "link",
                                         "paths": ["~/.claude/skills/" + obj["id"]]}
            else:
                obj["ends"]["claude"] = {"present": False}
        registry_file.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")

    def claude_options(self):
        return ("--home", str(self.home), "--ends", "claude", "--claude-home", str(self.home / "claude-home"))

    def test_claude_end_installs_claude_md_and_skills_only_in_explicit_layout(self):
        self.enable_claude()
        options = self.claude_options()
        claude_home = self.home / "claude-home"
        # 默认全端不处理 claude：既不创建目录，也不要求 --claude-home。
        self.assertEqual(self.call("--apply")[0], 0)
        self.assertFalse(claude_home.exists())
        self.assertFalse((self.home / ".claude").exists())
        before = self.snapshot()
        rc, report = self.call(*options)
        self.assertEqual((rc, report["status"], report["claudeHome"]), (0, "planned", str(claude_home)))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.call(*options, "--check")[0], 1)
        rc, report = self.call(*options, "--apply")
        self.assertEqual((rc, report["status"]), (0, "completed"))
        self.assertEqual(self.call(*options, "--check")[0], 0)
        self.assertEqual((claude_home / "CLAUDE.md").read_bytes(), self.expected_role_startup())
        self.assertEqual(os.readlink(claude_home / "CLAUDE.md"),
                         str(self.home / ".luno/generated/claude/CLAUDE.md"))
        self.assertNotIn(b"private global fixture", (claude_home / "CLAUDE.md").read_bytes())
        registry = json.loads((self.checkout / "tools/sync-targets.json").read_text())
        for obj in registry["objects"]:
            if obj["type"] == "skill" and obj["ends"]["claude"]["present"]:
                self.assertEqual(os.readlink(claude_home / "skills" / obj["id"]),
                                 str((self.checkout / obj["source"]).parent))
        rc, report = self.call(*options, "--apply")
        self.assertEqual((rc, report["created"]), (0, []))

    def test_claude_end_without_registry_key_is_absent_not_an_error(self):
        # 旧登记没有 claude 键：显式选择该端只得到空计划，也不影响默认全端的严格校验。
        before = self.snapshot()
        rc, report = self.call(*self.claude_options(), "--apply")
        self.assertEqual((rc, report["status"], report["actions"]), (0, "completed", []))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.call("--check")[0], 1)

    def test_claude_layout_requires_selected_end_and_contained_root(self):
        self.enable_claude()
        inside = str(self.home / "claude-home")
        cases = ((["--ends", "claude"], "invalid_claude_layout"),
                 (["--claude-home", inside], "invalid_claude_layout"),
                 (["--ends", "claude", "codex", "--claude-home", inside], "invalid_claude_layout"),
                 (["--ends", "claude", "--claude-home", "relative"], "invalid_claude_layout"),
                 (["--ends", "claude", "--claude-home", str(self.home)], "invalid_claude_layout"),
                 (["--ends", "claude", "--claude-home", str(self.root / "outside")],
                  "claude_home_outside_install_root"),
                 (["--ends", "claude", "--claude-home", inside, "--codex-global-source",
                   "paseo-append-system-prompt"], "codex_global_source_requires_codex_only"))
        before = self.snapshot()
        for options, expected in cases:
            with self.subTest(options=options):
                rc, report = self.call("--home", str(self.home), *options, "--apply")
                self.assertEqual(rc, 2)
                self.assertEqual(report["errors"][0]["code"], expected)
                self.assertEqual(self.snapshot(), before)

    def test_claude_conflicts_stop_without_overwriting(self):
        self.enable_claude()
        options = self.claude_options()
        claude_home = self.home / "claude-home"
        claude_home.mkdir()
        (claude_home / "CLAUDE.md").write_bytes(b"user instructions")
        before = self.snapshot()
        rc, report = self.call(*options, "--apply")
        self.assertEqual(rc, 2)
        self.assertIn({"code": "path_conflict", "path": str(claude_home / "CLAUDE.md")}, report["errors"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((claude_home / "CLAUDE.md").read_bytes(), b"user instructions")

    def test_claude_renderer_and_end_must_match(self):
        self.enable_claude()
        registry_file = self.checkout / "tools/sync-targets.json"
        registry = json.loads(registry_file.read_text())
        prompt = next(obj for obj in registry["objects"] if obj["type"] == "prompt")
        prompt["ends"]["claude"]["renderer"] = "codex-main"
        registry_file.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
        before = self.snapshot()
        rc, report = self.call(*self.claude_options(), "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("registry_renderer_end_mismatch", [e["code"] for e in report["errors"]])
        self.assertEqual(self.snapshot(), before)


class NativeRoleTest(unittest.TestCase):
    """原生 Codex 两角色：TOML 字节、注册只读核对与只读准入；不读真实配置。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-role-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home/example"
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

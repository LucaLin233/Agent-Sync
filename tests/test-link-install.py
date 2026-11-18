#!/usr/bin/env python3
"""宿主安装器离线回归：临时 HOME、真实进程、文件与软链；不访问真实登录态。"""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/link-install.py"


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="link-install-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout with space"
        self.checkout.mkdir()
        for name in ("skills", "prompt", "subagents"):
            shutil.copytree(ROOT / name, self.checkout / name)
        (self.checkout / "tools").mkdir()
        shutil.copyfile(ROOT / "tools/sync-targets.json", self.checkout / "tools/sync-targets.json")
        self.env = {"HOME": str(self.home), "PATH": os.environ["PATH"], "LC_ALL": "C.UTF-8",
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
        self.assertIs(config["daemon"]["mcp"]["injectIntoAgents"], True)
        self.assertEqual(self.call("--apply")[0], 0)
        for role in ("lens", "forge"):
            for provider, variable, entry in (("claude", "CLAUDE_CONFIG_DIR", "CLAUDE.md"),
                                               ("codex", "CODEX_HOME", "AGENTS.md")):
                key = role + "-" + provider
                fragment = config["agents"]["providers"][key]
                self.assertEqual(fragment["extends"], provider)
                relative = fragment["env"][variable].removeprefix("/home/USER/")
                self.assertEqual(relative, ".luno/homes/" + key)
                self.assertEqual((self.home / relative / entry).read_bytes(),
                                 (self.checkout / f"subagents/{role.upper()}.md").read_bytes())


if __name__ == "__main__":
    unittest.main()

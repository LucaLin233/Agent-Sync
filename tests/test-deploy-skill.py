#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/deploy_skill.py（及其加载的 body_contract／resource_http）的离线回归。

每个测试类对应一项现役保证。两层执行：子进程跑真实入口（参数面、只打包、授权断言、受控 CLI 子进程
env）；进程内加载同一模块，只替换外部缝（`run_lh`、`open_storage`、预签名下载、HTTPS 连接）跑部署
流程。夹具仓库里的 tools 是仓库真实实现的副本，仅把 resource_http 的 origin pin 换成合成值。
全部离线、确定性；不调真 `lh`、不读真凭据、不写仓库内文件。
"""
import base64
import hashlib
import http.client
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock
from urllib.parse import unquote
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "deploy_skill.py"
BOOTSTRAP = ("import importlib.util as u, sys\n"
             "s = u.spec_from_file_location('deploy_skill_main', sys.argv[1])\n"
             "m = u.module_from_spec(s); s.loader.exec_module(m)\n"
             "m.CLI_LAUNCHERS = (sys.argv[2],)\n"     # 仅替换信任根，不复制解析算法
             "sys.exit(m.main(sys.argv[3:]))\n")
SURGE_PACKER = "skills/luno-surge/scripts/package_release.py"

MARK = "SYNTHETIC-SECRET-9f3c1a7d"   # 只出现在夹具的凭据／签名 URL／原始报文里，绝不允许外流
NAME = "fixture-skill"
EXPECT_ID = "skl_Fixture00001"
RES = "references/fixture.md"
ORIGIN = "https://deploy.invalid"
API_KEY = "synthetic-offline"
ACCOUNT, BUCKET = "fixture-account", "fixture-bucket"
SKILL = "---\nname: %s\ndescription: 夹具技能描述\n---\n\n# 夹具\n\n夹具正文。\n"
OK_BODY = json.dumps({"result": {"data": {"json": {}}}}).encode()
POISON_BOTO3 = ("import os\nopen(os.path.join(os.path.dirname(__file__), 'boto3.marker'), 'w')"
                ".write('x')\nraise ImportError('offline fixture')\n")
ORIGINALS = {"references/upstream-SKILL.md": "SKILL.md",
             "references/upstream-command-reference.md": "references/command-reference.md",
             "references/plugin-authoring.md": "references/plugin-authoring.md"}


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.chmod(str(path), mode)


def load(path, modname):
    spec = importlib.util.spec_from_file_location(modname, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BC = load(ROOT / "tools" / "body_contract.py", "body_contract_for_tests")


def key_of(name):
    return name + ".zip"


def ident_of(name):
    return "url.%s.r2.cloudflarestorage.com.%s.%s" % (ACCOUNT, BUCKET, key_of(name))


def zip_members(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        return dict((name, archive.read(name)) for name in archive.namelist())


class Repo(object):
    """自足的审定仓库＋资产目录＋记录调用的桩 `lh`＋毒化 boto3。"""

    def __init__(self, root, name=NAME, src_rel=None):
        self.root, self.name = root, name
        self.src_rel = src_rel or "skills/" + name
        self.repo, self.out, self.bin = root / "repo", root / "out", root / "bin"
        self.src = self.repo / self.src_rel
        self.out.mkdir(parents=True)
        for mod in ("pack-skill-zip.py", "body_contract.py", "resource_http.py"):
            write(self.repo / "tools" / mod, (ROOT / "tools" / mod).read_bytes())
        pin = self.repo / "tools" / "resource_http.py"
        text, count = re.subn(r"^APPROVED_ORIGIN_SHA256 = '[0-9a-f]{64}'$",
                              "APPROVED_ORIGIN_SHA256 = '%s'" % sha(ORIGIN.encode()),
                              pin.read_text(encoding="utf-8"), flags=re.M)
        assert count == 1, "夹具副本须恰有一处 origin pin"
        write(pin, text)
        write(self.bin / "lh", "#!/bin/sh\nprintf '%%s\\n' \"$*\" >> '%s'\nexit 0\n"
              % (root / "lh-calls.log"), mode=0o755)
        write(root / "poison" / "boto3.py", POISON_BOTO3)
        write(self.src / "SKILL.md", SKILL % name)
        write(self.src / RES, "夹具资源正文\n")
        self.register()

    def live(self):
        return sorted(p.relative_to(self.src).as_posix() for p in self.src.rglob("*")
                      if p.is_file() and p.name != "SKILL.md")

    def register(self, resources=None, **extra):
        obj = {"id": self.name, "type": "skill", "source": self.src_rel + "/SKILL.md",
               "resources": [self.src_rel + "/" + r
                             for r in (self.live() if resources is None else resources)],
               "ends": {"repo": {"present": True},
                        "lobehub": {"present": True, "kind": "skill", "id": EXPECT_ID,
                                    "fields": "content,name,description"}}}
        obj.update(extra)
        write(self.repo / "tools/sync-targets.json", json.dumps({"objects": [obj]}))

    def args(self, deploy=False, src=None, out=None, **over):
        argv = ["--repo", str(self.repo), "--src", src or self.src_rel,
                "--name", over.pop("name", self.name), "--key", over.pop("key", key_of(self.name)),
                "--out-dir", str(out or self.out), "--expect-id", over.pop("expect_id", EXPECT_ID)]
        for flag, value in over.items():
            argv += ["--" + flag.replace("_", "-"), value]
        return argv + (["--deploy"] if deploy else [])

    def run(self, argv, env=None):
        base = {"HOME": str(self.root), "TMPDIR": str(self.root),
                "PATH": "%s:/usr/bin:/bin" % self.bin, "PYTHONPATH": str(self.root / "poison")}
        base.update(env or {})
        cp = subprocess.run([sys.executable, "-B", "-c", BOOTSTRAP, str(TOOL), str(self.bin / "lh")]
                            + argv, cwd=str(self.repo), env=base,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        return cp.returncode, cp.stdout.decode("utf-8", "replace"), cp.stderr.decode("utf-8", "replace")

    def lh_calls(self):
        log = self.root / "lh-calls.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def sdk_imported(self):
        return (self.root / "poison" / "boto3.marker").exists()

    def artifacts(self):
        return sorted(p.name for p in self.out.iterdir())

    def candidate(self):
        return (self.out / key_of(self.name)).read_bytes()


def surge_repo(root, fetched=True, packer=True):
    """luno-surge：专用打包器＋manifest＋官方取件声明（原件为合成字节）。"""
    repo = Repo(root, name="luno-surge", src_rel="skills/luno-surge")
    if packer:
        write(repo.repo / SURGE_PACKER, (ROOT / SURGE_PACKER).read_bytes())
    repo.originals = dict((rel, ("synthetic %s\n" % key).encode()) for rel, key in ORIGINALS.items())
    write(repo.src / "references/upstream-manifest.json", json.dumps({"raw_sha256": dict(
        (key, sha(repo.originals[rel])) for rel, key in ORIGINALS.items())}))
    repo.register(resources=[r for r in repo.live() if r not in ORIGINALS],
                  officialPackageResources={"paths": sorted(repo.src_rel + "/" + r for r in ORIGINALS)})
    if fetched:
        for rel, blob in repo.originals.items():
            write(repo.src / rel, blob)
    return repo


def run_main(module, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = module.main(argv)
    return rc, out.getvalue(), err.getvalue()


def pack_inproc(repo, argv=None):
    return run_main(load(TOOL, "deploy_skill_pack"), argv if argv is not None else repo.args())


# ── 进程内部署假件 ────────────────────────────────────────────────────────────

class FakeS3(object):
    def __init__(self, key, pre_blob):
        self.objects = {key: pre_blob}
        self.gets, self.puts, self.fail, self.noisy = [], [], set(), False

    def _noise(self):
        if self.noisy:
            sys.stdout.write("SDK stdout %s\n" % MARK)
            sys.stderr.write("SDK stderr %s\n" % MARK)
            logging.getLogger("fixture.sdk").error("SDK logging %s", MARK)

    def get_object(self, Bucket=None, Key=None):
        self._noise()
        self.gets.append(Key)
        if "get" in self.fail:
            raise RuntimeError("get_object 原始报文 %s" % MARK)
        return {"Body": io.BytesIO(self.objects.get(Key, b""))}

    def put_object(self, Bucket=None, Key=None, Body=None, ContentType=None):
        self._noise()
        if "put" in self.fail:
            raise RuntimeError("put_object 原始报文 %s" % MARK)
        self.puts.append(Key)
        self.objects[Key] = Body

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self._noise()
        if "url" in self.fail:
            raise RuntimeError("presign 原始报文 %s" % MARK)
        return "https://r2.invalid/%s?X-Amz-Signature=%s" % (Params["Key"], MARK)


class Response(object):
    def __init__(self, status, headers, body):
        self.status, self.headers, self._body = status, headers, io.BytesIO(body)

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, size=-1):
        return self._body.read(size)

    read1 = read

    def close(self):
        pass


class Platform(object):
    """假 LobeHub：`view` 回放对象状态；install／edit 由写入假连接作用到状态。"""

    def __init__(self, harness, name, pre_hash):
        self.h, self.name = harness, name
        self.state = {"id": EXPECT_ID, "identifier": ident_of(name), "name": name,
                      "description": "旧描述", "content": "旧正文\n", "zipFileHash": pre_hash,
                      "resources": {}}
        self.files = {}               # readResource 回放的 bytes
        self.views, self.requests = [], []
        self.view_rc = 0
        self.view_hooks = {}          # 第 n 次 view（1 起）返回前调用
        self.on_write = None
        self.after_install, self.after_edit = {}, {}
        self.ignore_edit = False
        self.routes = {}              # kind → [(status, content_type, body) | Exception, ...]

    def view(self, args, stage, timeout):
        self.views.append((list(args), timeout))
        hook = self.view_hooks.get(len(self.views))
        if hook:
            hook(self)
        if self.view_rc:
            return self.view_rc, ("raw stderr %s" % MARK).encode()
        return 0, json.dumps({"data": self.state}).encode()

    def adopt(self, blob):
        """把一个 ZIP 设为平台现状（install 生效或未变分支的前置）。"""
        members = zip_members(blob)
        skill = members.pop("SKILL.md")
        self.state.update(zipFileHash=sha(blob), name=BC.fm_get(skill, "name"),
                          description=BC.fm_get(skill, "description"),
                          content=BC.body_bytes(skill).decode("utf-8"),
                          resources=dict((rel, {"size": len(b), "fileHash": sha(b)})
                                         for rel, b in members.items()))
        self.files = members

    def install(self, payload):
        self.adopt(self.h.s3.objects[key_of(self.name)])
        self.state.update(self.after_install)

    def edit(self, payload):
        if self.ignore_edit:
            return
        if "content" in payload:
            self.state["content"] = payload["content"]
        self.state.update(payload.get("manifest") or {})
        self.state.update(self.after_edit)

    def kinds(self, kind):
        return [r for r in self.requests if r["kind"] == kind]


class WriteConn(object):
    PATHS = {"/trpc/lambda/agentSkills.importFromUrl": "install",
             "/trpc/lambda/agentSkills.update": "edit"}

    def __init__(self, platform, host):
        self.p, self.host = platform, host

    def request(self, method, path, body=None, headers=None):
        self.kind = self.PATHS[path]
        self.payload = json.loads(body.decode("utf-8"))["json"]
        self.p.requests.append({"kind": self.kind, "method": method, "path": path, "host": self.host,
                                "headers": dict(headers), "payload": self.payload})
        if self.p.on_write:
            self.p.on_write(self.p, self.kind)

    def getresponse(self):
        routes = self.p.routes.get(self.kind) or [(200, "application/json", OK_BODY)]
        spec = routes[min(len(self.p.kinds(self.kind)) - 1, len(routes) - 1)]
        if isinstance(spec, Exception):
            raise spec
        status, ctype, body = spec
        if status == 200 and ctype.startswith("application/json") and body == OK_BODY:
            getattr(self.p, self.kind)(self.payload)
        return Response(status, {"Content-Type": ctype, "Content-Length": str(len(body))}, body)

    def close(self):
        pass


class ResourceConn(object):
    """readResource 假连接：按 path 回放 platform.files（base64 信封）。"""

    def __init__(self, harness, host, timeout=None):
        self.h, self.sock, self.timeout = harness, None, timeout

    def request(self, method, target, headers=None):
        self.path = json.loads(unquote(target.split("?input=", 1)[1]))["json"]["path"]
        self.h.resource_requests.append(self.path)

    def getresponse(self):
        data = self.h.platform.files.get(self.path, b"")
        payload = {"path": self.path, "size": len(data), "fileHash": sha(data),
                   "fileType": "text/plain", "encoding": "base64",
                   "content": base64.b64encode(data).decode("ascii")}
        body = json.dumps({"result": {"data": {"json": payload}}}).encode()
        return Response(200, {"Content-Length": str(len(body))}, body)

    def close(self):
        pass


class Harness(object):
    def __init__(self, repo, pre_blob=b"pre-deploy-zip-bytes"):
        self.repo, self.pre_blob = repo, pre_blob
        self.mod = load(TOOL, "deploy_skill_under_test")
        self.mod.CLI_LAUNCHERS = (str(repo.bin / "lh"),)   # 合成信任入口（仅测试接缝）
        self.mod.WRITE_RETRY_DELAYS = (0.0, 0.0)
        self.mod.REPAIR_POLL_DELAYS = (0.0,) * 5
        self.real_open_storage = self.mod.open_storage
        self.s3 = FakeS3(key_of(repo.name), pre_blob)
        self.platform = Platform(self, repo.name, sha(pre_blob))
        self.resource_requests, self.fetched_urls = [], []
        self.fetch_bytes, self.fetch_error = None, None
        self.env = {"LUNO_DEPLOY_AUTHORIZED": "1", "CF_ACCOUNT_ID": ACCOUNT, "R2_BUCKET": BUCKET,
                    "R2_ACCESS_KEY_ID": "fixture-key-id", "R2_SECRET_ACCESS_KEY": "secret-" + MARK,
                    "LOBEHUB_SERVER": ORIGIN, "LOBEHUB_CLI_API_KEY": API_KEY,
                    "PATH": "%s:/usr/bin:/bin" % repo.bin}
        self.mod.run_lh = self.platform.view
        self.mod.open_storage = lambda: self.mod.Storage(self.s3, BUCKET)
        self.mod.https_connection = lambda host, timeout: WriteConn(self.platform, host)

    def urlopen(self, url, timeout=None):
        self.fetched_urls.append(url)
        if self.fetch_error is not None:
            raise self.fetch_error
        blob = self.fetch_bytes if self.fetch_bytes is not None else self.s3.objects[key_of(self.repo.name)]
        return Response(200, {}, blob)

    def run(self, deploy=True, **over):
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(urllib.request, "urlopen",
                                  lambda url, timeout=None: _ctx(self.urlopen(url, timeout))), \
                mock.patch.object(http.client, "HTTPSConnection",
                                  lambda host, timeout=None: ResourceConn(self, host, timeout)):
            return run_main(self.mod, self.repo.args(deploy=deploy, **over))

    def candidate_blob(self):
        rc, out, err = pack_inproc(self.repo)
        assert rc == 0, out + err
        return self.repo.candidate()

    def zero_writes(self, case):
        case.assertEqual(self.s3.puts, [], "零上传")
        case.assertEqual(self.platform.requests, [], "零 install／edit")


class _ctx(object):
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, *exc):
        return False


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="test-deploy-")
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.n = 0

    def repo(self, **kwargs):
        self.n += 1
        return Repo(self.work / ("r%d" % self.n), **kwargs)

    def surge(self, **kwargs):
        self.n += 1
        return surge_repo(self.work / ("r%d" % self.n), **kwargs)

    def harness(self, repo=None, **kwargs):
        return Harness(repo or self.repo(), **kwargs)

    def assert_fail(self, result, rc, stage, needle=None):
        code, out, err = result
        self.assertEqual(code, rc, out + err)
        self.assertIn("阶段失败：%s｜" % stage, err)
        if needle:
            self.assertIn(needle, err)
        return out, err


# ── 参数与登记 ───────────────────────────────────────────────────────────────

class CliSurface(Case):
    """参数面：缺 --src 不回退环境变量；登记不符即拒；失败零产物、零平台访问。"""

    def test_missing_src_has_no_env_fallback(self):
        repo = self.repo()
        argv = repo.args()
        del argv[2:4]
        rc, out, err = repo.run(argv, {"DEPLOY_SRC": str(repo.src)})
        self.assertEqual(rc, 2, out + err)
        self.assertIn("缺少必填参数 --src", err)
        self.assertEqual((repo.artifacts(), repo.lh_calls(), repo.sdk_imported()), ([], [], False))

    def test_help_and_unknown_argument(self):
        repo = self.repo()
        rc, out, err = repo.run(["--help"])
        self.assertEqual(rc, 0, err)
        self.assertIn("默认只打包", out)
        self.assertFalse(repo.sdk_imported())
        rc, out, err = repo.run(repo.args() + ["--frobnicate"])
        self.assertEqual(rc, 2)
        self.assertIn("未知参数 --frobnicate", err)

    def test_registry_and_target_mismatch_is_refused(self):
        repo = self.repo(name="guessed", src_rel="skills/upstream/guessed")
        inside = repo.src / "assets"
        inside.mkdir()
        cases = (
            ("guessed src", repo.args(src="skills/guessed"), "--src 与登记源路径不一致"),
            ("expect-id", repo.args(expect_id="skl_Other"), "--expect-id 与登记的 LobeHub 平台 ID 不一致"),
            ("name", repo.args(name="other"), "不是恰好 1 个"),
            ("key form", repo.args(key="https://x/y"), "--key 须为单段对象 key"),
            ("out missing", repo.args(out=str(self.work / "nope")), "--out-dir 不是已存在目录"),
            ("out inside src", repo.args(out=str(inside)), "--out-dir 位于 --src 之内"),
        )
        for label, argv, needle in cases:
            with self.subTest(label):
                self.assert_fail(pack_inproc(repo, argv), 2, "本地校验", needle)
                self.assertEqual(repo.artifacts(), [])
        (repo.repo / "tools/sync-targets.json").unlink()
        self.assert_fail(pack_inproc(repo), 2, "本地校验", "缺登记真源")

    def test_expect_digest_parameter_forms(self):
        repo = self.repo()
        for value in ("A" * 64, "sha256:" + "a" * 64, "a" * 63, "a" * 64 + "\n", " " + "a" * 63):
            with self.subTest(value=value):
                out, err = self.assert_fail(pack_inproc(repo, repo.args(expect_zip_sha256=value)),
                                            2, "本地校验", "完整 64 位小写十六进制")
                self.assertNotIn(value.strip(), out + err, "外部值不回显")
        argv = repo.args(expect_zip_sha256="a" * 64) + ["--expect-zip-sha256", "b" * 64]
        self.assert_fail(pack_inproc(repo, argv), 2, "本地校验", "不允许重复")
        self.assertEqual(repo.artifacts(), [])


# ── 候选包 ───────────────────────────────────────────────────────────────────

class LocalPackage(Case):
    """候选包：全部校验通过才原子写出 0644 产物；只打包模式零平台／零 SDK。"""

    def test_pack_only_writes_verified_candidate(self):
        repo = self.repo()
        rc, out, err = repo.run(repo.args())
        self.assertEqual(rc, 0, out + err)
        self.assertIn("写路径：未进入", out)
        digest = re.search(r"打包：files=2 bytes=\d+ sha256=([0-9a-f]{64})", out).group(1)
        self.assertEqual(sha(repo.candidate()), digest)
        self.assertEqual(os.stat(str(repo.out / key_of(NAME))).st_mode & 0o7777, 0o644)
        self.assertEqual(sorted(zip_members(repo.candidate())), ["SKILL.md", RES])
        self.assertEqual((repo.lh_calls(), repo.sdk_imported()), ([], False))

    def test_invalid_sources_write_nothing(self):
        def empty(r):
            shutil.rmtree(str(r.src))
            r.src.mkdir()

        def symlink(r):
            os.symlink(str(r.src / "SKILL.md"), str(r.src / "linked.md"))

        def exec_bit(r):
            write(r.src / "scripts/run.sh", "#!/bin/sh\n", mode=0o755)
            r.register()

        cases = (
            ("empty", empty, "空包"),
            ("blank body", lambda r: write(r.src / "SKILL.md", "---\nname: %s\n---\n\n" % NAME), "正文为空"),
            ("name", lambda r: write(r.src / "SKILL.md", SKILL % "other"), "frontmatter name"),
            ("bom", lambda r: write(r.src / "SKILL.md", b"\xef\xbb\xbf" + (SKILL % NAME).encode()),
             "不合正文契约（BOM_FORBIDDEN）"),
            ("symlink", symlink, "源收集失败"),
            ("0755", exec_bit, "非常规权限 0755：scripts/run.sh"),
        )
        for label, mutate, needle in cases:
            with self.subTest(label):
                repo = self.repo()
                mutate(repo)
                self.assert_fail(pack_inproc(repo), 2, "打包" if label == "symlink" else "本地校验",
                                 needle)
                self.assertEqual(repo.artifacts(), [])
                if label == "0755":
                    self.assertEqual(os.stat(str(repo.src / "scripts/run.sh")).st_mode & 0o777,
                                     0o755, "不得压平源权限")

    def test_cache_members_refused_without_inventory_help(self):
        """__pycache__ 路径段与 .pyc 由候选清单内建拒绝：登记与否都拒，普通文件正控不退。"""
        # 错误文本用的是 ZIP 成员名（技能根相对名），不是 repo 相对路径
        probes = (("registered __pycache__", "__pycache__/fixture.cpython-311.pyc", True,
                   "［__pycache__/fixture.cpython-311.pyc］"),
                  ("registered .pyc", "references/stray.pyc", True, "候选清单含 Python 缓存文件"),
                  ("unregistered __pycache__", "__pycache__/orphan.cpython-311.pyc", False,
                   "候选清单含 Python 缓存文件"))
        for label, rel, register, needle in probes:
            with self.subTest(label):
                repo = self.repo()
                write(repo.src / rel, b"\x00cache")
                if register:
                    repo.register()          # live() 现读：坏成员被显式登记，不靠清单差异拦
                self.assert_fail(pack_inproc(repo), 2, "本地校验", needle)
                self.assertEqual(repo.artifacts(), [], "拒绝时不得写出候选")
                self.assertEqual((repo.lh_calls(), repo.sdk_imported()), ([], False))
        repo = self.repo()
        write(repo.src / "references/notes.txt", "普通文件\n")
        repo.register()
        rc, out, err = repo.run(repo.args())
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(sorted(zip_members(repo.candidate())),
                         ["SKILL.md", RES, "references/notes.txt"])

    def test_inventory_must_equal_package(self):
        repo = self.repo()
        repo.register(resources=[RES, "references/ghost.md"])
        self.assert_fail(pack_inproc(repo), 2, "资源完整清单",
                         "登记有、包内无［skills/%s/references/ghost.md］" % NAME)
        repo.register()
        write(repo.src / "references/extra.md", "x\n")
        self.assert_fail(pack_inproc(repo), 2, "资源完整清单",
                         "包内有、登记无［skills/%s/references/extra.md］" % NAME)
        repo.register(officialPackageResources={"paths": ["x"]})
        self.assert_fail(pack_inproc(repo), 2, "资源完整清单", "只允许 luno-surge")
        self.assertEqual(repo.artifacts(), [])
        repo.register()
        self.assertEqual(pack_inproc(repo)[0], 0)

    def test_expect_digest_gate_in_pack_mode(self):
        repo = self.repo()
        self.assert_fail(pack_inproc(repo, repo.args(expect_zip_sha256="0" * 64)), 2, "本地校验",
                         "与 --expect-zip-sha256 不一致")
        self.assertEqual(repo.artifacts(), [], "不一致即不写候选")
        self.assertEqual(pack_inproc(repo)[0], 0)
        rc, out, err = pack_inproc(repo, repo.args(expect_zip_sha256=sha(repo.candidate())))
        self.assertEqual(rc, 0, out + err)


class OfficialOriginalsGate(Case):
    """luno-surge：官方参考原件须在位、声明完整、哈希等于 manifest，否则拒绝构包。"""

    def test_surge_requires_fetched_originals(self):
        repo = self.surge(fetched=False)
        self.assert_fail(pack_inproc(repo), 2, "资源完整清单", "官方参考原件缺失")
        for rel, blob in repo.originals.items():
            write(repo.src / rel, blob)
        self.assertEqual(pack_inproc(repo)[0], 0)
        write(repo.src / "references/plugin-authoring.md", b"tampered\n")
        self.assert_fail(pack_inproc(repo), 2, "资源完整清单", "哈希不符 manifest")

    def test_surge_declaration_must_be_complete_and_exclusive(self):
        repo = self.surge()
        paths = sorted(repo.src_rel + "/" + r for r in ORIGINALS)
        resources = [r for r in repo.live() if r not in ORIGINALS]
        repo.register(resources=resources, officialPackageResources={"paths": paths[:2]})
        self.assert_fail(pack_inproc(repo), 2, "资源完整清单", "须恰好声明 3 份参考原件")
        repo.register(resources=resources + ["references/plugin-authoring.md"],
                      officialPackageResources={"paths": paths})
        self.assert_fail(pack_inproc(repo), 2, "资源完整清单", "不得同时登记为普通资源")


class DedicatedPacker(Case):
    """专用打包器：按登记源加载、不回退通用器；路径与链接先核后导入；失败只报类名。"""

    def test_surge_pack_uses_dedicated_packer(self):
        repo = self.surge()
        self.assertEqual(pack_inproc(repo)[0], 0)
        packer = load(repo.repo / SURGE_PACKER, "fixture_package_release")
        self.assertEqual(repo.candidate(), packer.build(packer.collect(repo.src)))
        with zipfile.ZipFile(io.BytesIO(repo.candidate())) as archive:
            self.assertEqual(archive.infolist()[0].date_time, (2026, 1, 1, 0, 0, 0))

    def test_missing_or_linked_packer_is_refused_before_import(self):
        marker = self.work / "poison-executed"
        poison = "open(%r, 'w').write('x')\nraise RuntimeError(%r)\n" % (str(marker), MARK)

        def module_link(repo):
            write(self.work / "poison.py", poison)
            (repo.repo / SURGE_PACKER).symlink_to(self.work / "poison.py")

        def dir_link(repo):
            shutil.rmtree(str(repo.src / "scripts"))
            write(self.work / "elsewhere/package_release.py", poison)
            (repo.src / "scripts").symlink_to(self.work / "elsewhere")

        for label, mutate in (("missing", lambda r: None), ("module link", module_link),
                              ("dir link", dir_link)):
            with self.subTest(label):
                repo = self.surge(packer=False)
                (repo.src / "scripts").mkdir(exist_ok=True)
                mutate(repo)
                out, err = self.assert_fail(pack_inproc(repo), 2, "本地校验", "专用打包器缺失或解析后不在登记源内")
                self.assertFalse(marker.exists(), "目标模块不得被执行")
                self.assertNotIn(MARK, out + err)
                self.assertEqual(repo.artifacts(), [])

    def test_deploy_requires_digest_before_loading_packer(self):
        repo = self.surge(packer=False)
        rc, out, err = repo.run(repo.args(deploy=True), {"LUNO_DEPLOY_AUTHORIZED": "1"})
        self.assertEqual(rc, 2, out + err)
        self.assertIn("必须显式给出 --expect-zip-sha256", err)
        self.assertNotIn("专用打包器缺失", err, "先决条件先于加载专用器")
        self.assertEqual((repo.artifacts(), repo.lh_calls(), repo.sdk_imported()), ([], [], False))

    def test_packer_failures_report_class_only(self):
        for body, expect in (("raise RuntimeError(%r)\n" % MARK, "导入失败（RuntimeError）"),
                             ("def (\n", "导入失败（SyntaxError）"),
                             ("raise SystemExit(%r)\n" % MARK, "导入失败（SystemExit）")):
            with self.subTest(expect):
                repo = self.surge()
                write(repo.repo / SURGE_PACKER, body)
                out, err = self.assert_fail(pack_inproc(repo), 2, "本地校验", expect)
                self.assertNotIn(MARK, out + err)
        repo = self.surge()
        leak = "ghp_" + "A" * 24                 # 合成形态
        write(repo.src / "references/leak.md", leak + "\n")
        out, err = self.assert_fail(pack_inproc(repo), 2, "打包", "SecretError")
        self.assertNotIn(leak, out + err)
        self.assertNotIn("leak.md", err, "不回显专用器消息")
        self.assertEqual(repo.artifacts(), [])

    def test_path_selection_routes_dedicated_packer_to_deploy(self):
        cp = subprocess.run([sys.executable, "-B", str(ROOT / "tests" / "test_paths.py"), "select-paths"],
                            input=(SURGE_PACKER + "\0").encode(), stdout=subprocess.PIPE)
        self.assertIn(["case", "test-deploy-skill.py"], json.loads(cp.stdout.decode("utf-8")))


# ── 授权、SDK 与同域前置 ─────────────────────────────────────────────────────

class Preconditions(Case):
    """写路径前置：授权断言先于任何写出；同域与 lh 解析不成立则零平台／零存储访问。"""

    def test_deploy_without_assertion_touches_nothing(self):
        repo = self.repo()
        write(repo.out / "existing.zip", b"PREVIOUS")
        rc, out, err = repo.run(repo.args(deploy=True))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：授权｜", err)
        self.assertEqual(repo.artifacts(), ["existing.zip"], "连候选包都不写")
        self.assertEqual((repo.out / "existing.zip").read_bytes(), b"PREVIOUS")
        self.assertEqual((repo.lh_calls(), repo.sdk_imported()), ([], False))

    def test_unprovable_same_origin_stops_before_platform(self):
        cases = (("no server", {"LOBEHUB_SERVER": None}),
                 ("no key", {"LOBEHUB_CLI_API_KEY": None}),
                 ("bad key", {"LOBEHUB_CLI_API_KEY": "bad key\n"}),
                 ("other origin", {"LOBEHUB_SERVER": "https://untrusted.invalid"}),
                 ("workspace", {"LOBEHUB_WORKSPACE_ID": "ws-1"}))
        for label, change in cases:
            with self.subTest(label):
                h = self.harness()
                for key, value in change.items():
                    if value is None:
                        h.env.pop(key)
                    else:
                        h.env[key] = value
                out, err = self.assert_fail(h.run(), 2, "平台回读", "同域前置未通过")
                self.assertEqual((h.platform.views, h.s3.gets), ([], []))
                self.assertEqual(h.repo.artifacts(), [key_of(NAME)], "只有本地候选包")
                self.assertNotIn(API_KEY, out + err)

    def test_unresolvable_or_shim_lh_stops_before_platform(self):
        shims = self.work / "mise" / "shims"
        write(shims / "lh", "#!/bin/sh\n", mode=0o755)
        for label, path in (("missing", str(self.work)), ("shim", str(shims))):
            with self.subTest(label):
                h = self.harness()
                h.env["PATH"] = path
                self.assert_fail(h.run(), 2, "平台回读", "无法解析 lh 启动器")
                self.assertEqual((h.platform.views, h.s3.gets), ([], []))

    def test_missing_sdk_or_credentials_after_platform_read(self):
        h = self.harness()
        h.mod.open_storage = h.real_open_storage
        with mock.patch.dict(sys.modules, {"boto3": None}):
            self.assert_fail(h.run(), 2, "SDK", "缺少 SDK")
        self.assertEqual(len(h.platform.views), 1, "SDK 推迟到确需存储写入之后")
        fake = type(sys)("boto3")
        fake.client = lambda *a, **k: h.s3
        config = type(sys)("botocore.config")
        config.Config = lambda **k: None
        h.env.pop("R2_ACCESS_KEY_ID")
        with mock.patch.dict(sys.modules, {"boto3": fake, "botocore": type(sys)("botocore"),
                                           "botocore.config": config}):
            out, err = self.assert_fail(h.run(), 2, "SDK", "R2_ACCESS_KEY_ID")
        self.assertNotIn("CF_ACCOUNT_ID", err, "只报缺的变量名")
        self.assertNotIn(MARK, out + err)
        self.assertEqual(h.s3.puts, [])


LH_RECORDER = """#!/bin/sh
{ printf 'ARGV0=%%s\\n' "$0"; printf 'HOME_LIST=%%s\\n' "$(ls -A "$HOME" | tr '\\n' ' ')"; env | sed 's/^/ENV /'; } >> '%(log)s'
printf '%%s' '%(view)s'
"""


class ControlledCli(Case):
    """受控 CLI：绝对 argv、白名单 env、新建空 HOME/XDG，用后删除（真实子进程）。"""

    EXPECTED = {"PATH", "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                "LOBEHUB_SERVER", "LOBEHUB_CLI_API_KEY"}

    def record(self, repo, log, env):
        view = json.dumps({"data": {"id": EXPECT_ID, "identifier": ident_of(NAME), "name": NAME,
                                    "description": "d", "content": "c", "zipFileHash": "0" * 64,
                                    "resources": {}}})
        write(repo.bin / "lh", LH_RECORDER % {"log": log, "view": view}, mode=0o755)
        subprocess.run([str(repo.bin / "lh")], env=env, stdout=subprocess.DEVNULL, check=True)
        lines = log.read_text(encoding="utf-8").splitlines()
        log.unlink()
        rec = {"env": {}}
        for line in lines:
            if line.startswith("ENV "):
                key, _, value = line[4:].partition("=")
                rec["env"][key] = value
            else:
                key, _, value = line.partition("=")
                rec[key] = value
        return rec

    def test_cli_child_env_is_whitelisted_and_home_is_empty(self):
        repo = self.repo()
        log = self.work / "lh-env.log"
        noise = set(self.record(repo, log, {"PATH": "/usr/bin:/bin", "HOME": str(self.work)})["env"])
        write(repo.root / ".config/lobehub/cli.json", '{"workspaceId": "ws-persisted"}')
        rc, out, err = repo.run(repo.args(deploy=True), {
            "LUNO_DEPLOY_AUTHORIZED": "1", "CF_ACCOUNT_ID": ACCOUNT, "R2_BUCKET": BUCKET,
            "R2_ACCESS_KEY_ID": "id", "R2_SECRET_ACCESS_KEY": MARK, "LOBEHUB_SERVER": ORIGIN,
            "LOBEHUB_CLI_API_KEY": API_KEY, "HTTP_PROXY": "http://decoy.invalid:3128",
            "LOBEHUB_JWT": "decoy"})
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：SDK｜", err, "冻结通过后推进到 SDK 边界（毒化 boto3）")
        lines = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum(1 for l in lines if l.startswith("ARGV0=")), 1, "恰一次 skill view")
        env = dict(l[4:].partition("=")[::2] for l in lines if l.startswith("ENV "))
        self.assertEqual(set(env) - (noise - self.EXPECTED), self.EXPECTED)
        self.assertEqual(lines[0], "ARGV0=%s" % os.path.realpath(str(repo.bin / "lh")))
        self.assertEqual(lines[1].split("=", 1)[1].split(), ["cache", "cfg", "data"])
        self.assertEqual(env["LOBEHUB_SERVER"], ORIGIN)
        self.assertTrue(set(env["PATH"].split(":")) <= {"/usr/local/bin", "/usr/bin", "/bin"})
        for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            self.assertTrue(env[var].startswith(env["HOME"] + "/"))
        self.assertNotEqual(env["HOME"], str(repo.root))
        self.assertFalse(os.path.exists(env["HOME"]), "收尾删除临时 HOME")
        self.assertNotIn(MARK, out + err)


# ── 临时根生命周期 ───────────────────────────────────────────────────────────

class TempLifecycle(Case):
    """D2：临时根身份、共用 close、拒删与错误优先级。"""

    LINE = re.compile(r"临时(\S+)：path=(\S+) dev=(\d+) ino=(\d+) uid=(\d+) mode=(\d+)")

    def capture(self, h):
        lines, mod, real = [], getattr(h, "mod", h), None

        def log(line):
            lines.append(line)
            real(line)

        real = mod.log
        mod.log = log
        return lines

    def created(self, lines):
        return [(m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6), 8))
                for m in map(self.LINE.match, lines) if m]

    def gone(self, lines, n=5):
        found = self.created(lines)
        self.assertEqual(len(found), n)
        for path, _d, _i, _u, _m in found:
            self.assertFalse(os.path.lexists(path))

    def sentinel(self):
        self.n += 1
        keep = self.work / ("sentinel%d" % self.n)
        keep.mkdir()
        (keep / "keep.txt").write_text("sentinel")
        return keep

    def test_creation_identity_and_cleanup(self):
        h = self.harness()
        lines = self.capture(h)
        seen, real = [], h.platform.view

        def view(args, stage, timeout):
            if not seen:
                for path, dev, ino, uid, mode in self.created(lines):
                    st = os.lstat(path)
                    seen.append((st.st_dev, st.st_ino, st.st_uid, stat.S_IMODE(st.st_mode)))
                    self.assertEqual(seen[-1], (dev, ino, uid, mode))
                    self.assertEqual(mode, 0o700)
            return real(args, stage, timeout)

        h.mod.run_lh = view
        rc, out, err = h.run()
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(seen), 5)
        self.gone(lines)

    def test_partial_construction_failure_closes(self):
        h = self.harness()
        lines = self.capture(h)
        real, calls = os.mkdir, []

        def mkdir(path, mode=0o777, **kw):
            calls.append(path)
            if len(calls) == 3:
                raise OSError(13, "denied")
            return real(path, mode, **kw)

        with mock.patch.object(h.mod.os, "mkdir", mkdir):
            rc, out, err = h.run()
        self.assertEqual(rc, 2, out + err)
        self.assertIn("无法建立受控 CLI 环境", err)
        self.gone(lines, 2)

    def test_business_failure_and_timeout_keep_primary(self):
        h = self.harness()
        lines = self.capture(h)
        h.platform.view_rc = 1
        rc, out, err = h.run()
        self.assertEqual(rc, 2, out + err)
        self.assertIn("阶段失败：平台回读｜", err)
        self.gone(lines)

        repo = self.repo()
        mod = load(TOOL, "deploy_skill_timeout")
        mod.CLI_LAUNCHERS = (str(repo.bin / "lh"),)
        lines = self.capture(mod)
        with mock.patch.dict(os.environ, {"PATH": "%s:/usr/bin:/bin" % repo.bin}, clear=True):
            mod.freeze_cli_runner(ORIGIN, "k")
        with mock.patch.object(mod.CliRunner, "call",
                               side_effect=subprocess.TimeoutExpired(["lh"], 1)):
            with self.assertRaises(mod.Fail) as ctx:
                mod.run_lh(["skill", "view"], mod.STAGE_PLATFORM, 1.0)
        self.assertEqual(ctx.exception.rc, 2)
        self.assertIn("超过剩余预算", ctx.exception.detail)
        self.assertEqual(mod.release_cli_runner(), (None, False))
        self.gone(lines)

    def test_symlink_in_tree_is_refused_and_sentinel_kept(self):
        keep = self.sentinel()
        h = self.harness()
        lines = self.capture(h)
        real, fired = h.platform.view, []

        def view(args, stage, timeout):
            if not fired:
                fired.append(1)
                os.symlink(str(keep), os.path.join(self.created(lines)[1][0], "link"))
            return real(args, stage, timeout)

        h.mod.run_lh = view
        rc, out, err = h.run()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("阶段失败：清理｜", err)
        self.assertIn("子项为软链", err)
        self.assertTrue((keep / "keep.txt").exists())
        self.assertNotIn(MARK, out + err)

    def test_rebind_after_check_keeps_replacement(self):
        for where in ("root", "home"):
            with self.subTest(where):
                keep = self.sentinel()
                h = self.harness()
                lines = self.capture(h)
                real, fired, target = h.mod.os.listdir, [], []

                def listdir(fd, _h=h, _l=lines, _f=fired, _t=target, _w=where):
                    names = real(fd)
                    if not _f and isinstance(fd, int):
                        _f.append(1)
                        _t.append(self.created(_l)[0 if _w == "root" else 1][0])
                        os.rename(_t[0], _t[0] + ".moved")
                        os.mkdir(_t[0], 0o700)
                        (Path(_t[0]) / "keep.txt").write_text("sentinel")
                    return names

                with mock.patch.object(h.mod.os, "listdir", listdir):
                    rc, out, err = h.run()
                self.assertEqual(rc, 1, out + err)
                self.assertIn("清理失败", err)
                self.assertIn(target[0], err)
                self.assertTrue((Path(target[0]) / "keep.txt").exists())
                self.assertTrue(os.path.isdir(target[0] + ".moved"))

    def test_cleanup_only_failure_rc_priority(self):
        def deny(op):
            real = getattr(os, op)

            def call(path, *a, **kw):
                if kw.get("dir_fd") is not None:
                    raise PermissionError(13, "denied")
                return real(path, *a, **kw)

            return call

        for view_rc, want in ((0, 1), (1, 2)):
            with self.subTest(view_rc):
                h = self.harness()
                h.platform.view_rc = view_rc
                with mock.patch.object(h.mod.os, "rmdir", deny("rmdir")):
                    rc, out, err = h.run()
                self.assertEqual(rc, want, out + err)
                self.assertIn("清理失败", err)
                self.assertIn("home/", err)
                if view_rc:
                    self.assertIn("阶段失败：平台回读｜", err)
                else:
                    self.assertIn("阶段失败：清理｜", err)

        h = self.harness()
        with mock.patch.object(h.mod.os.path, "lexists",
                               side_effect=PermissionError(13, "denied")):
            rc, out, err = h.run()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("核验不可达", err)


# ── 部署流程 ─────────────────────────────────────────────────────────────────

class DeployFlow(Case):
    """写路径：回滚包→上传→预签名回读→install→完整回读；写路径内失败 rc=1。"""

    def test_happy_path(self):
        h = self.harness()
        rollback = h.repo.out / (NAME + ".predeploy.zip")
        seen = []
        put = h.s3.put_object

        def watch(**kw):
            seen.append((os.stat(str(rollback)).st_mode & 0o7777, sha(rollback.read_bytes())))
            return put(**kw)

        h.s3.put_object = watch
        rc, out, err = h.run()
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(h.s3.puts, [key_of(NAME)])
        self.assertEqual(rollback.read_bytes(), h.pre_blob)
        self.assertEqual(os.stat(str(rollback)).st_mode & 0o7777, 0o600, "自动备份 0600")
        self.assertEqual(seen, [(0o600, sha(h.pre_blob))])
        installs = h.platform.kinds("install")
        self.assertEqual([r["payload"] for r in installs], [{"url": h.fetched_urls[0]}])
        self.assertEqual(installs[0]["headers"]["X-API-Key"], API_KEY)
        self.assertEqual(installs[0]["host"], "deploy.invalid")
        self.assertIn(MARK, h.fetched_urls[0], "预签名 URL 确带标记，下面的不外流断言非空转")
        self.assertEqual(h.platform.kinds("edit"), [])
        self.assertEqual(h.resource_requests, [RES], "每个资源恰一次 HTTP 读取")
        argv = h.platform.views[0][0]
        self.assertEqual(argv[:3], ["skill", "view", EXPECT_ID])
        self.assertNotIn("source", argv[4].split(","))
        self.assertIn("resources", argv[4].split(","))
        self.assertTrue(all(t and 0 < t <= 10 for _a, t in h.platform.views), "每次回读都带预算")
        self.assertIn("回读判等：", out)
        self.assertNotIn(MARK, out + err)

    def test_predeploy_guards_stop_before_any_write(self):
        cases = (
            ("view rc", lambda p: setattr(p, "view_rc", 1), "平台回读", "rc=1"),
            ("name", lambda p: p.state.update(name="other"), "平台回读", "name"),
            ("non-url identifier", lambda p: p.state.update(identifier="user.x"), "平台回读", "identifier"),
            ("other key", lambda p: p.state.update(identifier=ident_of("other")), "平台回读", "bucket／key"),
            ("signed query", lambda p: p.state.update(identifier=ident_of(NAME) + "?X-Amz-Signature=" + MARK),
             "平台回读", "bucket／key"),
            ("other account", lambda p: p.state.update(identifier=ident_of(NAME).replace(ACCOUNT, "acct2")),
             "平台回读", "identifier"),
            ("missing resources", lambda p: p.state.pop("resources"), "平台回读", "缺 resources"),
            ("pre hash form", lambda p: p.state.update(zipFileHash="deadbeef"), "回滚包", "回滚能力不成立"),
            ("r2 object", lambda p: p.state.update(zipFileHash="a" * 64), "回滚包", "同 key 现存对象"),
        )
        for label, mutate, stage, needle in cases:
            with self.subTest(label):
                h = self.harness()
                mutate(h.platform)
                out, err = self.assert_fail(h.run(), 2, stage, needle)
                self.assertNotIn(MARK, out + err)
                h.zero_writes(self)
                self.assertFalse((h.repo.out / (NAME + ".predeploy.zip")).exists())

    def test_write_path_failures_are_rc1(self):
        def route(kind, *specs):
            return lambda h: h.platform.routes.update({kind: list(specs)})

        cases = (
            ("put", lambda h: h.s3.fail.add("put"), "上传", "上传失败（RuntimeError）"),
            ("download", lambda h: setattr(h, "fetch_bytes", b"tampered"), "下载校验", "不一致"),
            ("install 5xx", route("install", (503, "application/json", b"")), "安装", "已尝试 1 次"),
            ("install 4xx", route("install", (401, "application/json", b"")), "安装", "status=401"),
            ("install html", route("install", (200, "text/html", OK_BODY)), "安装", "Content-Type"),
            ("install error envelope",
             route("install", (200, "application/json", b'{"error":{"json":{"message":"%s"}}}' % MARK.encode())),
             "安装", "错误信封"),
            ("install oversized", route("install", (200, "application/json", b" " * (64 * 1024 + 1))),
             "安装", "上限"),
            ("install transport", route("install", OSError("boom %s" % MARK)), "安装", "OSError"),
            ("post view", lambda h: h.platform.view_hooks.update({2: lambda p: setattr(p, "view_rc", 1)}),
             "回读判等", "rc=1"),
            ("post hash", lambda h: h.platform.after_install.update(zipFileHash="0" * 64),
             "回读判等", "zipFileHash"),
            ("resource set", lambda h: h.platform.after_install.update(resources={}), "回读判等",
             "资源路径集不等（平台 0 项／候选 1 项）"),
        )
        for label, mutate, stage, needle in cases:
            with self.subTest(label):
                h = self.harness()
                mutate(h)
                out, err = self.assert_fail(h.run(), 1, stage, needle)
                self.assertNotIn(MARK, out + err)
                self.assertLessEqual(len(h.platform.kinds("install")), 1, "install 不重试")

    def test_200_without_effect_is_caught_by_readback(self):
        h = self.harness()
        h.platform.install = lambda payload: None
        self.assert_fail(h.run(), 1, "回读判等", "zipFileHash")

    def test_tail_lf_and_field_repair_share_one_update(self):
        body = BC.body_bytes((SKILL % NAME).encode()).decode("utf-8")
        cases = (("tail lf", {"content": body[:-1]}, {"content": body}),
                 ("description", {"description": "别的描述"},
                  {"manifest": {"name": NAME, "description": "夹具技能描述"}}),
                 ("both", {"content": body[:-1], "name": "x"},
                  {"content": body, "manifest": {"name": NAME, "description": "夹具技能描述"}}))
        for label, drift, payload in cases:
            with self.subTest(label):
                h = self.harness()
                h.platform.after_install.update(drift)
                rc, out, err = h.run()
                self.assertEqual(rc, 0, out + err)
                edits = h.platform.kinds("edit")
                self.assertEqual([e["payload"] for e in edits], [dict(payload, id=EXPECT_ID)])
                self.assertEqual((h.platform.state["content"], h.platform.state["name"]), (body, NAME))

    def test_other_content_difference_is_not_repaired(self):
        body = BC.body_bytes((SKILL % NAME).encode()).decode("utf-8")
        for label, content in (("same length", body[:-2] + "!\n"), ("two lf", body.rstrip("\n")[:-1]),
                               ("extra lf", body + "\n")):
            with self.subTest(label):
                h = self.harness()
                h.platform.after_install["content"] = content
                self.assert_fail(h.run(), 1, "回读判等", "非恰少一个尾 LF")
                self.assertEqual(h.platform.kinds("edit"), [])

    def test_repair_must_converge(self):
        h = self.harness()
        h.platform.after_install["description"] = "别的描述"
        h.platform.ignore_edit = True
        self.assert_fail(h.run(), 1, "回读判等", "轮询 5 次仍未收敛（不等字段：description）")
        h = self.harness()
        h.platform.after_install["description"] = "别的描述"
        h.platform.after_edit["zipFileHash"] = "0" * 64
        self.assert_fail(h.run(), 1, "回读判等", "第 1 轮回读 zipFileHash")

    def test_edit_retry_policy(self):
        h = self.harness()
        h.platform.after_install["description"] = "别的描述"
        h.platform.routes["edit"] = [(503, "application/json", b""), (502, "application/json", b""),
                                     (200, "application/json", OK_BODY)]
        rc, out, err = h.run()
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(h.platform.kinds("edit")), 3, "edit 瞬时失败有界重试")
        h = self.harness()
        h.platform.after_install["description"] = "别的描述"
        h.platform.routes["edit"] = [(400, "application/json", b"")]
        self.assert_fail(h.run(), 1, "正文修补", "status=400")
        self.assertEqual(len(h.platform.kinds("edit")), 1, "4xx 不重试")
        h = self.harness()
        h.platform.after_install["description"] = "别的描述"
        h.platform.routes["edit"] = [(503, "application/json", b""), (200, "application/json", OK_BODY)]
        h.platform.view_hooks[4] = lambda p: p.state.update(description="第三方改动")
        self.assert_fail(h.run(), 1, "正文修补", "并发变更")
        self.assertEqual(len(h.platform.kinds("edit")), 1, "重试前同样写前复核")

    def test_write_guard_blocks_concurrent_change(self):
        cases = (("third value", {"description": "第三方改动"}, "并发变更（字段：description）"),
                 ("hash changed", {"zipFileHash": "1" * 64}, "zipFileHash 已变化"))
        for label, change, needle in cases:
            with self.subTest(label):
                h = self.harness()
                h.platform.after_install["description"] = "别的描述"
                # 第 2 次 view＝安装后基线；第 3 次＝update 前的写前复核
                h.platform.view_hooks[3] = lambda p, c=change: p.state.update(c)
                self.assert_fail(h.run(), 1, "正文修补", needle)
                self.assertEqual(h.platform.kinds("edit"), [], "零 update")

    def test_resource_metadata_gate_runs_before_http(self):
        good = {"size": len("夹具资源正文\n".encode()), "fileHash": sha("夹具资源正文\n".encode())}
        cases = (
            ("unknown key", {RES: dict(good, url="https://x/?sig=" + MARK)}),
            ("missing key", {RES: {"size": good["size"]}}),
            ("size", {RES: dict(good, size=1)}),
            ("bad path", {"../" + MARK: good}),
            ("not record", [RES]),
        )
        for label, value in cases:
            with self.subTest(label):
                h = self.harness()
                h.platform.after_install["resources"] = value
                out, err = self.assert_fail(h.run(), 1, "回读判等")
                self.assertEqual(h.resource_requests, [], "形态门先于资源 HTTP")
                self.assertNotIn(MARK, out + err)

    def test_resource_bytes_are_read_and_compared(self):
        h = self.harness()
        h.platform.install = lambda payload, p=h.platform: (
            Platform.install(p, payload), p.files.update({RES: b"tampered\n"}))
        self.assert_fail(h.run(), 1, "回读判等", "资源 HTTP 回读失败")
        self.assertEqual(h.resource_requests, [RES])


class UnchangedObject(Case):
    """zipFileHash 已等于候选：只读核验全部字段与资源 bytes，零写入；任一漂移 rc=2 且不修补。"""

    def unchanged(self):
        h = self.harness()
        h.platform.adopt(h.candidate_blob())
        return h

    def test_unchanged_object_verifies_and_writes_nothing(self):
        h = self.unchanged()
        rc, out, err = h.run()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("核验一致，未执行部署写入", out)
        self.assertEqual((h.s3.gets, h.s3.puts, h.platform.requests), ([], [], []))
        self.assertEqual(h.resource_requests, [RES])

    def test_unchanged_branch_drift_is_rc2_without_writes(self):
        cases = (("tail lf", lambda p: p.state.update(content=p.state["content"][:-1]), "content"),
                 ("description", lambda p: p.state.update(description="别的"), "description"),
                 ("resource bytes", lambda p: p.files.update({RES: b"x"}), "资源 HTTP 回读失败"),
                 ("resource set", lambda p: p.state.update(resources={}), "资源路径集不等"))
        for label, mutate, needle in cases:
            with self.subTest(label):
                h = self.unchanged()
                mutate(h.platform)
                out, _err = self.assert_fail(h.run(), 2, "只读核验", needle)
                self.assertNotIn("核验一致", out)
                self.assertEqual((h.s3.gets, h.s3.puts, h.platform.requests), ([], [], []))


class SourceWindow(Case):
    """打包后源目录变化：上传前发现 rc=2（零上传），写入后发现 rc=1（提示人工确认）。"""

    def test_change_before_upload_is_rc2(self):
        h = self.harness()
        h.platform.view_hooks[1] = lambda p: write(h.repo.src / RES, "changed\n")
        self.assert_fail(h.run(), 2, "源端复核", "变化文件［%s］" % RES)
        h.zero_writes(self)
        self.assertEqual(h.s3.gets, [])

    def test_change_during_install_is_rc1(self):
        h = self.harness()
        h.platform.on_write = lambda p, kind: write(h.repo.src / RES, "changed\n")
        self.assert_fail(h.run(), 1, "投后复核", "须人工确认是否重投")


class SecretFace(Case):
    """合成秘密标记（凭据、签名 URL、SDK／CLI／HTTP 原始报文）不进输出与产物。"""

    def test_marker_never_reaches_output_or_artifacts(self):
        def noisy_sdk(h):
            h.s3.noisy = True
            fake = type(sys)("boto3")
            fake.client = lambda *a, **k: h.s3
            config = type(sys)("botocore.config")
            config.Config = lambda **k: None
            h.mod.open_storage = h.real_open_storage
            h.modules = {"boto3": fake, "botocore": type(sys)("botocore"), "botocore.config": config}

        cases = (("noisy sdk", noisy_sdk, 0),
                 ("view stderr", lambda h: setattr(h.platform, "view_rc", 3), 2),
                 ("get", lambda h: h.s3.fail.add("get"), 2),
                 ("presign", lambda h: h.s3.fail.add("url"), 1),
                 ("fetch", lambda h: setattr(h, "fetch_error", RuntimeError(MARK)), 1))
        for label, mutate, rc_expected in cases:
            with self.subTest(label):
                h = self.harness()
                h.modules = {}
                mutate(h)
                with mock.patch.dict(sys.modules, h.modules):
                    rc, out, err = h.run()
                self.assertEqual(rc, rc_expected, out + err)
                self.assertNotIn(MARK, out + err)
                for path in h.repo.out.iterdir():
                    self.assertNotIn(MARK.encode(), path.read_bytes(), path.name)


# ── 单元：资源形态门、资源传输、正文契约、原子写 ────────────────────────────────

class ResourceUnits(Case):
    def test_platform_resource_map_table(self):
        mod = load(TOOL, "deploy_skill_units")
        valid = load(ROOT / "tools" / "resource_http.py", "resource_http_units").valid_path
        good = {"size": 3, "fileHash": "A" * 64}
        self.assertEqual(mod.platform_resource_map({"resources": None}, "s", valid), {})
        self.assertEqual(mod.platform_resource_map({"resources": {}}, "s", valid), {})
        self.assertEqual(mod.platform_resource_map({"resources": {"a/b.md": good}}, "s", valid),
                         {"a/b.md": (3, "a" * 64)})
        for label, raw in (("list", []), ("item", {"a": 1}), ("extra", {"a": dict(good, x=1)}),
                           ("missing", {"a": {"size": 3}}), ("dotdot", {"../a": good}),
                           ("ctrl", {"a\x00b": good}), ("bool", {"a": dict(good, size=True)}),
                           ("negative", {"a": dict(good, size=-1)}), ("str size", {"a": dict(good, size="3")}),
                           ("hash lf", {"a": dict(good, fileHash="a" * 64 + "\n")}),
                           ("hash type", {"a": dict(good, fileHash=1)})):
            with self.subTest(label), self.assertRaises(mod.Fail):
                mod.platform_resource_map({"resources": raw}, "s", valid)

    def test_resource_http_failure_classifications(self):
        rh = load(ROOT / "tools" / "resource_http.py", "resource_http_cls")
        data = b"payload\n"
        item = ("references/a.md", len(data), sha(data))

        def envelope(content=None, encoding="base64", size=len(data), digest=sha(data)):
            payload = {"path": item[0], "size": size, "fileHash": digest, "fileType": "text/plain",
                       "encoding": encoding,
                       "content": content if content is not None else base64.b64encode(data).decode()}
            return json.dumps({"result": {"data": {"json": payload}}}).encode()

        ok = envelope()
        cases = (("authentication", 401, {}, ok), ("authentication", 403, {}, ok),
                 ("rate-limit", 429, {}, ok), ("http-status", 302, {}, ok),
                 ("truncated", 200, {"Content-Length": str(len(ok) + 5)}, ok),
                 ("structure", 200, {"Content-Encoding": "gzip"}, ok),
                 ("encoding", 200, {}, envelope(content="cGF5bG9hZAo")),
                 ("integrity", 200, {}, envelope(content=base64.b64encode(b"other!!\n").decode())),
                 ("structure", 200, {}, b'{"result":{"data":{"json":{}}},"result":1}'))
        for expect, status, headers, body in cases:
            with self.subTest(expect=expect, status=status):
                conn = type("Conn", (), {"sock": None, "timeout": None,
                                         "request": lambda self, *a, **k: None, "close": lambda self: None,
                                         "getresponse": lambda self: Response(status, headers, body)})
                client = rh.ResourceClient(rh.time.monotonic() + 30, (ORIGIN, API_KEY))
                with mock.patch.object(rh.http.client, "HTTPSConnection", lambda *a, **k: conn()):
                    with self.assertRaises(rh.ResourceError) as ctx:
                        client.read(EXPECT_ID, item)
                self.assertEqual(str(ctx.exception), expect)
        client = rh.ResourceClient(rh.time.monotonic() - 1, (ORIGIN, API_KEY))
        with self.assertRaises(rh.ResourceError) as ctx:
            client.read(EXPECT_ID, item)
        self.assertEqual(str(ctx.exception), "budget")


class BodyContract(unittest.TestCase):
    def code(self, func, raw):
        with self.assertRaises(BC.ContractError) as ctx:
            func(raw)
        return ctx.exception.code

    def test_body_bytes_are_exact(self):
        self.assertEqual(BC.body_bytes(b"---\nname: a\n---\n\nbody\n\n"), b"body\n\n")
        self.assertEqual(BC.body_bytes(b"---\r\nname: a\r\n---\r\n\r\nx\r\n"), b"x\r\n")
        self.assertEqual(BC.body_bytes(b"---\nname: a\r\n---\nx"), b"x", "终止符可不同族")
        self.assertEqual(BC.body_bytes(b"---\nname: a\n---"), b"---\nname: a\n---", "EOF 结束行不算")
        self.assertEqual(BC.body_bytes(b"--- x\n"), b"--- x\n")
        self.assertEqual(BC.body_bytes(b"---\nname: a\n"), b"---\nname: a\n", "无结束行即整体为正文")

    def test_field_values(self):
        raw = (b'---\r\nname: "a\\tb\\u00e9"\r\nq: \'it\'\'s\'\r\nn:\r\ne: ""\r\n'
               b'd: |\r\n  l1\r\n  l2\r\nf: >-\r\n  x\r\n  y\r\nm:\r\n  k: v\r\n---\r\nbody')
        f = BC.fm_fields(raw)
        self.assertEqual((f["name"], f["q"], f["n"], f["e"]), ("a\tb\u00e9", "it's", None, ""))
        self.assertEqual((f["d"], f["f"], f["m"]), ("l1\nl2\n", "x y", {"k": "v"}))
        self.assertIs(BC.fm_get(raw, "absent"), BC.MISSING)

    def test_fail_closed(self):
        self.assertEqual(self.code(BC.fm_fields, b"---\nname: a\r\nname: b\r\n---\nx"), "DUPLICATE_KEY")
        self.assertEqual(self.code(BC.body_bytes, b"x\xff"), "INVALID_UTF8")
        self.assertEqual(self.code(BC.fm_fields, b"---\nname: \xff\n---\n"), "INVALID_UTF8")
        self.assertEqual(self.code(BC.body_bytes, b"\xef\xbb\xbfno frontmatter"), "BOM_FORBIDDEN")
        for raw in (b"---\nt: [a]\n---\n", b"---\nt: &a x\n---\n", b"---\n- a\n---\n",
                    b"---\nm:\n  a:\n    b: c\n---\n"):
            self.assertEqual(self.code(BC.fm_fields, raw), "UNSUPPORTED_YAML", raw)


class AtomicWrite(Case):
    def test_failed_replace_keeps_old_artifact_and_cleans_tmp(self):
        mod = load(TOOL, "deploy_skill_atomic")
        target = self.work / "a.zip"
        target.write_bytes(b"old")
        with mock.patch.object(mod.os, "replace", side_effect=OSError("nope")):
            with self.assertRaises(mod.Fail) as ctx:
                mod.write_atomic(str(target), b"new", mod.STAGE_PACK)
        self.assertEqual(ctx.exception.rc, 2)
        self.assertEqual(target.read_bytes(), b"old")
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["a.zip"])

    def test_caller_mode_before_publish_and_failure_old(self):
        mod = load(TOOL, "deploy_skill_atomic_mode")
        target = self.work / "b.zip"
        target.write_bytes(b"old")
        os.chmod(str(target), 0o640)
        mod.write_atomic(str(target), b"new", mod.STAGE_ROLLBACK, 0o600)
        self.assertEqual((target.read_bytes(), os.stat(str(target)).st_mode & 0o7777),
                         (b"new", 0o600))
        mod.write_atomic(str(target), b"pkg", mod.STAGE_PACK)
        self.assertEqual(os.stat(str(target)).st_mode & 0o7777, 0o644)
        for op in ("fchmod", "replace"):
            with mock.patch.object(mod.os, op, side_effect=OSError("nope")):
                with self.assertRaises(mod.Fail):
                    mod.write_atomic(str(target), b"x", mod.STAGE_ROLLBACK, 0o600)
            self.assertEqual((target.read_bytes(), os.stat(str(target)).st_mode & 0o7777),
                             (b"pkg", 0o644))
            self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["b.zip"])


# ── 启动器信任：PATH 只用于选择已知安装入口 ──────────────────────────────────

def resolve_with(mod, env):
    with mock.patch.dict(os.environ, env, clear=True):
        return mod.resolve_cli_argv()


class LauncherTrust(Case):
    """名单外同名可执行文件、shim／mise、非可执行目标一律固定 Fail（平台回读阶段）。"""

    def test_old_rule_accepts_but_allowlist_refuses(self):
        h = self.harness()
        rogue = self.work / "rogue-bin"
        write(rogue / "lh", "#!/bin/sh\nexit 0\n", mode=0o755)
        h.env["PATH"] = "%s:/usr/bin:/bin" % rogue
        entry = shutil.which("lh", path=h.env["PATH"])
        real = os.path.realpath(entry)
        self.assertEqual(str(rogue / "lh"), entry)
        self.assertTrue(os.path.isfile(real) and os.access(real, os.X_OK), "旧判定接受该伪 lh")
        self.assertNotIn(real, h.mod.CLI_LAUNCHERS)
        self.assert_fail(h.run(), 2, "平台回读", "无法解析 lh 启动器")
        self.assertEqual((h.platform.views, h.s3.gets, h.platform.requests), ([], [], []))
        self.assertEqual(h.repo.artifacts(), [key_of(NAME)], "只有本地候选包，伪 lh 未被执行")

    def test_non_allowlisted_path_shapes_are_refused(self):
        similar = self.work / "usr" / "local" / "bin2"
        write(similar / "lh", "#!/bin/sh\nexit 0\n", mode=0o755)
        cwd = self.work / "cwd"
        write(cwd / "rel-bin" / "lh", "#!/bin/sh\nexit 0\n", mode=0o755)
        write(cwd / "lh", "#!/bin/sh\nexit 0\n", mode=0o755)
        old = os.getcwd()
        os.chdir(cwd)
        try:
            for label, path in (("prefix", "%s:/usr/bin:/bin" % similar),
                                ("relative", "rel-bin:/usr/bin:/bin"),
                                ("empty segment", ":/usr/bin:/bin")):
                with self.subTest(label):
                    h = self.harness()
                    self.assertTrue(shutil.which("lh", path=path), "攻击入口确实能被 which 命中")
                    h.env["PATH"] = path
                    self.assert_fail(h.run(), 2, "平台回读", "无法解析 lh 启动器")
                    self.assertEqual((h.platform.views, h.s3.puts, h.s3.gets,
                                      h.platform.requests), ([], [], [], []))
        finally:
            os.chdir(old)

    def test_no_lh_on_path_is_refused(self):
        h = self.harness()
        h.env["PATH"] = "/usr/bin:/bin"
        self.assertIsNone(shutil.which("lh", path=h.env["PATH"]))
        self.assert_fail(h.run(), 2, "平台回读", "无法解析 lh 启动器")
        self.assertEqual((h.platform.views, h.s3.puts, h.s3.gets, h.platform.requests),
                         ([], [], [], []))

    def test_allowlisted_entry_and_legal_symlink_still_work(self):
        h = self.harness()
        inst = self.work / "opt" / "lobehub"
        write(inst / "cli", "#!/bin/sh\nexit 0\n", mode=0o755)
        (inst / "lh").symlink_to(inst / "cli")
        h.mod.CLI_LAUNCHERS = (str(inst / "lh"),)
        h.env["PATH"] = "%s:/usr/bin:/bin" % inst
        self.assertEqual([str(inst / "cli")], resolve_with(h.mod, h.env), "合法软链解析为真实目标")
        rc, out, err = h.run()
        self.assertNotIn("无法解析 lh 启动器", err, "名单内入口不提前拒绝")
        self.assertTrue(h.platform.views, "冻结后进入平台回读")

    def test_shim_mise_and_non_executable_reach_their_branches(self):
        h = self.harness()
        shims = self.work / "mise" / "shims"
        write(shims / "lh", "#!/bin/sh\nexit 0\n", mode=0o755)
        mise = self.work / "mise" / "bin"
        write(mise / "mise", "#!/bin/sh\nexit 0\n", mode=0o755)
        (mise / "lh").symlink_to(mise / "mise")
        for label, entry in (("shim", shims / "lh"), ("mise", mise / "lh")):
            with self.subTest(label):
                h.mod.CLI_LAUNCHERS = (str(entry),)
                h.env["PATH"] = "%s:/usr/bin:/bin" % entry.parent
                self.assertEqual(str(entry), shutil.which("lh", path=h.env["PATH"]), "命中该入口")
                self.assert_fail(h.run(), 2, "平台回读", "无法解析 lh 启动器")
                self.assertEqual((h.platform.views, h.s3.puts, h.s3.gets,
                                  h.platform.requests), ([], [], [], []))

    def test_non_executable_real_target_guard_branch(self):
        """软链入口＋真实目标不可执行：which 仍命中，走 access 守卫。"""
        h = self.harness()
        inst = self.work / "opt" / "lobehub"
        write(inst / "cli", "#!/bin/sh\nexit 0\n", mode=0o755)
        entry, target = inst / "lh", str(inst / "cli")
        entry.symlink_to(inst / "cli")
        h.mod.CLI_LAUNCHERS = (str(entry),)
        h.env["PATH"] = "%s:/usr/bin:/bin" % inst
        self.assertEqual(str(entry), shutil.which("lh", path=h.env["PATH"]), "which 选中入口")
        real_access = h.mod.os.access

        def access(path, mode):
            return False if path == target else real_access(path, mode)
        with mock.patch.object(h.mod.os, "access", access):
            self.assertEqual(str(entry), shutil.which("lh", path=h.env["PATH"]),
                             "注入不影响 which 命中")
            self.assert_fail(h.run(), 2, "平台回读", "无法解析 lh 启动器")
        self.assertEqual((h.platform.views, h.s3.puts, h.s3.gets, h.platform.requests),
                         ([], [], [], []))


if __name__ == "__main__":
    unittest.main()

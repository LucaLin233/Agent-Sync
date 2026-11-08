#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LobeHub 技能部署入口：默认只打包，`--deploy` 才上传／安装并逐项回读。

用法：
  python3 -B tools/deploy_skill.py --repo <审定仓库> --src <显式技能目录> --name <技能名> \\
      --key <既有 R2 对象 key> --out-dir <已授权资产目录> --expect-id <登记平台 ID> \\
      [--expect-zip-sha256 <64 位小写十六进制>] [--deploy]

边界：
  · 身份只认 `--repo/tools/sync-targets.json`：名称、源目录、LobeHub ID 须与参数完全一致，不按
    名称猜源目录。打包器、正文契约、资源传输模块只从 `--repo` 加载，无回退。
  · 候选 ZIP 在内存构建并校验（源文件 0644、frontmatter name、非空正文、登记资源集＝包内文件），
    全部通过才原子写出到 `--out-dir`。`--expect-zip-sha256` 给出时实构摘要须逐位相等（两种模式都核）。
    `skills/luno-surge` 走其专用打包器：`--deploy` 必须给摘要，且先核官方参考原件在位、哈希等于 manifest。
  · `--deploy` 须 `LUNO_DEPLOY_AUTHORIZED=1`：防误触断言，不是授权来源；在任何写出之前检查。
  · 部署：同域前置（受批准 origin＋指定 key、个人作用域）不成立即停；`lh` 解析为绝对 argv，子进程只拿
    白名单 env 与新建空 HOME/XDG。部署前回读核 name、来源 bucket/key、zipFileHash；zipFileHash 已等于
    候选摘要 ⇒ 只读核验全部字段与资源 bytes、不写。否则：R2 现存对象存为回滚包（实读哈希＝部署前
    zipFileHash）→ 上传 → 预签名回读比对 → importFromUrl → 完整回读。仅「恰少一个尾 LF」与
    name/description 不符可经一次 agentSkills.update 修补（每次写前重读，防覆盖并发改动），其余差异即停。
    资源逐项比 size/fileHash 与经 HTTP 取回的原始 bytes。打包后源目录变化：上传前发现 rc=2，完成后 rc=1。
  · 秘密：凭据只取环境变量、只按名报缺；预签名 URL、key、SDK/CLI/HTTP 原始报文不进日志或产物。

退出码：0 成功（含只读核验一致）；1 写路径开始后失败（不得盲重试：先回读，再按回滚包恢复）；
2 参数、输入或前置不成立，未进入写路径。
"""
import hashlib
import http.client
import importlib
import importlib.util
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from contextlib import contextmanager
from urllib.parse import urlsplit

AUTH_ENV = "LUNO_DEPLOY_AUTHORIZED"

STAGE_LOCAL = "本地校验"
STAGE_PACK = "打包"
STAGE_INVENTORY = "资源完整清单"
STAGE_AUTH = "授权"
STAGE_SDK = "SDK"
STAGE_PLATFORM = "平台回读"
STAGE_SNAPSHOT = "源端复核"
STAGE_READONLY = "只读核验"
STAGE_ROLLBACK = "回滚包"
STAGE_UPLOAD = "上传"
STAGE_DOWNLOAD = "下载校验"
STAGE_INSTALL = "安装"
STAGE_READBACK = "回读判等"
STAGE_EDIT = "正文修补"
STAGE_SNAPSHOT_AFTER = "投后复核"
# 已开始写平台／存储的阶段 ⇒ rc=1；其余 ⇒ rc=2
WRITE_STAGES = (STAGE_UPLOAD, STAGE_DOWNLOAD, STAGE_INSTALL, STAGE_READBACK, STAGE_EDIT,
                STAGE_SNAPSHOT_AFTER)

CLI_PATH_DIRS = ("/usr/local/bin", "/usr/bin", "/bin")
WRITE_PROCEDURES = {"install": "/trpc/lambda/agentSkills.importFromUrl",
                    "edit": "/trpc/lambda/agentSkills.update"}
WRITE_TIMEOUT = 30.0
WRITE_BODY_LIMIT = 64 * 1024
# 只有 edit（同 id 同载荷幂等）在传输异常／5xx 时重试；install 与 4xx／错误信封不重试
WRITE_RETRY_DELAYS = (0.25, 0.5)
REPAIR_POLL_DELAYS = (0.0, 0.5, 1.0, 2.0, 4.0)
REPAIR_POLL_BUDGET = 10.0
READBACK_BUDGET = 10.0
HTTP_WORKERS = 4
RESOURCE_HTTP_BUDGET = 300.0

SKILL_FILE = "SKILL.md"
STORAGE_ENV = ("CF_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
# 不取 source／manifest：二者可能带签名 URL
PLATFORM_FIELDS = ("id", "identifier", "name", "description", "content", "zipFileHash",
                   "resources")
RESOURCE_META_KEYS = frozenset(("fileHash", "size"))
R2_HOST = "r2.cloudflarestorage.com"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
PLATFORM_ID_RE = re.compile(r"^skl_[A-Za-z0-9]+$")
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")   # 单段 key：不接受 URL／路径
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/+-]{1,255}$")

DEDICATED_PACKERS = {"skills/luno-surge": "skills/luno-surge/scripts/package_release.py"}
# luno-surge 的官方参考原件不进公开仓库，部署 clone 取件后才在位（见其 references/SOURCE.md）
OFFICIAL_ROOT = "skills/luno-surge"
OFFICIAL_MANIFEST = "references/upstream-manifest.json"
OFFICIAL_ORIGINALS = {
    "skills/luno-surge/references/upstream-SKILL.md": "SKILL.md",
    "skills/luno-surge/references/upstream-command-reference.md": "references/command-reference.md",
    "skills/luno-surge/references/plugin-authoring.md": "references/plugin-authoring.md",
}

USAGE = ("用法：python3 -B tools/deploy_skill.py --repo <审定仓库> --src <显式技能目录> "
         "--name <技能名> --key <既有 R2 对象 key> --out-dir <已授权资产目录> "
         "--expect-id <登记平台 ID> [--expect-zip-sha256 <64位小写十六进制>] [--deploy]\n"
         "  默认只打包（不上传／不安装）；--deploy 才进入写路径，且须 %s=1（防误触断言，"
         "不是授权来源）。\n"
         "  退出码：0 成功／1 写路径已开始后失败／2 参数或输入不可用。" % AUTH_ENV)


class Fail(Exception):
    """固定阶段失败；`detail` 不含秘密。"""

    def __init__(self, stage, detail):
        Exception.__init__(self, detail)
        self.stage = stage
        self.detail = detail

    @property
    def rc(self):
        return 1 if self.stage in WRITE_STAGES else 2


def log(line):
    sys.stdout.write("[deploy] %s\n" % line)


def sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def safe_path(rel):
    return rel if isinstance(rel, str) and SAFE_PATH_RE.match(rel) else "<非法路径>"


def load_module(path, modname):
    if not os.path.isfile(path):
        raise Fail(STAGE_LOCAL, "审定仓库内缺辅助模块：%s" % path)
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise Fail(STAGE_LOCAL, "读取失败（%s）：%s" % (exc.__class__.__name__, path))


def write_atomic(path, blob, stage):
    """同目录临时文件 → 0644 → os.replace；失败不覆盖已有产物。"""
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), prefix=".deploy-",
                                         delete=False) as fh:
            tmp = fh.name
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        tmp = None
    except OSError as exc:
        raise Fail(stage, "写出产物失败（%s）：%s" % (exc.__class__.__name__, path))
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                sys.stderr.write("[deploy] 警告：临时文件残留：%s\n" % os.path.basename(tmp))


# ── 受控 CLI ─────────────────────────────────────────────────────────────────

class CliRunner(object):
    """绝对 argv＋新建空 HOME/XDG＋白名单 env：不读登录态，不继承 workspace／代理／其它凭据。"""

    def __init__(self, argv, origin, key):
        self.argv = list(argv)
        self.root = tempfile.mkdtemp(prefix="deploy-lh-")
        try:
            home = os.path.join(self.root, "home")
            os.mkdir(home)
            env = {"PATH": os.pathsep.join(d for d in CLI_PATH_DIRS if os.path.isdir(d)),
                   "HOME": home, "LOBEHUB_SERVER": origin, "LOBEHUB_CLI_API_KEY": key}
            for var, sub in (("XDG_CONFIG_HOME", "cfg"), ("XDG_DATA_HOME", "data"),
                             ("XDG_CACHE_HOME", "cache")):
                env[var] = os.path.join(home, sub)
                os.mkdir(env[var])
            self.env = env
        except BaseException:
            self.close()
            raise

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def call(self, args, timeout):
        return subprocess.run(self.argv + list(args), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=dict(self.env), timeout=timeout)


RUNNER = None


def resolve_cli_argv():
    """在原环境把 `lh` 解析为可执行绝对路径一次；shim／mise 一律拒绝。"""
    path = os.environ.get("PATH")
    entry = shutil.which("lh", path=path) if path else None
    real = os.path.realpath(entry) if entry else ""
    if (not real or "shims" in real.split(os.sep) or os.path.basename(real) == "mise"
            or not os.path.isfile(real) or not os.access(real, os.X_OK)):
        raise Fail(STAGE_PLATFORM, "无法解析 lh 启动器为可执行绝对路径（或为 shim）：同域前置未通过；"
                                   "停止本次部署，未执行平台或存储写入")
    return [real]


def freeze_cli_runner(origin, key):
    global RUNNER
    argv = resolve_cli_argv()
    try:
        RUNNER = CliRunner(argv, origin, key)
    except OSError as exc:
        raise Fail(STAGE_PLATFORM, "无法建立受控 CLI 环境（%s）：停止本次部署，未执行平台或存储写入"
                    % exc.__class__.__name__)


def release_cli_runner():
    global RUNNER
    if RUNNER is not None:
        RUNNER.close()
        RUNNER = None


def run_lh(args, stage, timeout):
    """调用冻结的 runner，返回 (rc, stdout)；stderr 丢弃。"""
    if RUNNER is None:
        raise Fail(stage, "CLI runner 未冻结：拒绝调用 lh")
    try:
        proc = RUNNER.call(args, timeout)
    except subprocess.TimeoutExpired:
        raise Fail(stage, "lh 读取超过剩余预算（%.1f s）：已中止，不判成功" % timeout)
    except OSError as exc:
        raise Fail(stage, "无法调用 lh（%s）" % exc.__class__.__name__)
    return proc.returncode, proc.stdout


# ── 对象存储（SDK 输出一律静音；预签名 URL 只在内存）─────────────────────────────

@contextmanager
def sdk_silence():
    """丢弃 SDK 自身的 stdout／stderr／logging（流级与 fd 级），防签名 URL 等外流。"""
    saved = (sys.stdout, sys.stderr, logging.root.manager.disable)
    for stream in saved[:2]:
        try:
            stream.flush()
        except Exception:
            pass
    sink = open(os.devnull, "w")
    dups = []
    sys.stdout = sys.stderr = sink
    logging.disable(logging.CRITICAL + 10)
    try:
        for fd in (1, 2):
            try:
                dup = os.dup(fd)
            except OSError:
                break
            try:
                os.dup2(sink.fileno(), fd)
            except OSError:
                os.close(dup)
                break
            dups.append((fd, dup))
        yield
    finally:
        for fd, dup in reversed(dups):
            try:
                os.dup2(dup, fd)
            except OSError:
                pass
            os.close(dup)
        sys.stdout, sys.stderr = saved[0], saved[1]
        logging.disable(saved[2])
        sink.close()


class Storage(object):
    """SDK 异常只报类名（原始报文可能含签名 URL）。"""

    def __init__(self, client, bucket):
        self._client = client
        self._bucket = bucket

    def download(self, key):
        try:
            with sdk_silence():
                return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise Fail(STAGE_ROLLBACK, "读取同 key 现存对象失败（%s）" % exc.__class__.__name__)

    def upload(self, key, blob):
        try:
            with sdk_silence():
                self._client.put_object(Bucket=self._bucket, Key=key, Body=blob,
                                        ContentType="application/zip")
        except Exception as exc:
            raise Fail(STAGE_UPLOAD, "上传失败（%s）" % exc.__class__.__name__)

    def presigned_get(self, key):
        try:
            with sdk_silence():
                return self._client.generate_presigned_url(
                    "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=600)
        except Exception as exc:
            raise Fail(STAGE_UPLOAD, "生成预签名 URL 失败（%s）" % exc.__class__.__name__)

    def fetch(self, url):
        try:
            with urllib.request.urlopen(url, timeout=120) as fh:
                return fh.read()
        except Exception as exc:
            raise Fail(STAGE_DOWNLOAD, "预签名下载失败（%s）" % exc.__class__.__name__)


def open_storage():
    """延迟加载 SDK；缺依赖／缺凭据只报告（按变量名），不自动安装。"""
    try:
        with sdk_silence():
            boto3 = importlib.import_module("boto3")
            botocore_config = importlib.import_module("botocore.config")
    except ImportError as exc:
        raise Fail(STAGE_SDK, "缺少 SDK（boto3／botocore，%s）；不自动安装" % exc.__class__.__name__)
    missing = [name for name in STORAGE_ENV if not os.environ.get(name)]
    if missing:
        raise Fail(STAGE_SDK, "缺少存储凭据环境变量（只报名）：%s" % "／".join(missing))
    env = os.environ
    try:
        with sdk_silence():
            client = boto3.client(
                "s3", endpoint_url="https://%s.%s" % (env["CF_ACCOUNT_ID"], R2_HOST),
                aws_access_key_id=env["R2_ACCESS_KEY_ID"],
                aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"], region_name="auto",
                config=botocore_config.Config(signature_version="s3v4",
                                              retries={"max_attempts": 3, "mode": "standard"}))
    except Exception as exc:
        raise Fail(STAGE_SDK, "初始化存储客户端失败（%s）" % exc.__class__.__name__)
    return Storage(client, env["R2_BUCKET"])


# ── 平台读取 ─────────────────────────────────────────────────────────────────

def _iter_dicts(node):
    if isinstance(node, dict):
        yield node
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return
    for child in children:
        for item in _iter_dicts(child):
            yield item


def platform_entry(expect_id, stage, timeout=READBACK_BUDGET):
    """按登记 ID 读白名单字段；`resources` 键缺失即失败，不当作空集。"""
    rc, out = run_lh(["skill", "view", expect_id, "--json", ",".join(PLATFORM_FIELDS)],
                     stage, timeout)
    if rc != 0:
        raise Fail(stage, "平台回读失败：lh skill view rc=%d" % rc)
    try:
        doc = json.loads(out.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise Fail(stage, "平台回读结果不是合法 JSON（%s）" % exc.__class__.__name__)
    for node in _iter_dicts(doc):
        if node.get("id") == expect_id:
            if "resources" not in node:
                raise Fail(stage, "平台回读缺 resources 字段")
            return dict((key, node.get(key)) for key in PLATFORM_FIELDS)
    raise Fail(stage, "平台回读未命中登记 ID：%s" % expect_id)


def platform_resource_map(entry, stage, valid_path):
    """`resources`（Record<path,{size,fileHash}>）→ {path: (size, fileHash)}。

    null／{} 为空集；未知或缺失的嵌套键、非法路径、类型不符一律失败。失败文案不回显外部路径与键名。
    """
    raw = entry["resources"]
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise Fail(stage, "平台 resources 不是 Record 形态（%s）" % type(raw).__name__)
    out = {}
    for rel, meta in raw.items():
        if not valid_path(rel):
            raise Fail(stage, "平台 resources 含非法路径")
        if not isinstance(meta, dict) or set(meta) != RESOURCE_META_KEYS:
            raise Fail(stage, "平台 resources 项须恰含 fileHash／size")
        size, digest = meta["size"], meta["fileHash"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise Fail(stage, "平台 resources 项 size 不是非负整数（%s）" % type(size).__name__)
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest.lower()):
            raise Fail(stage, "平台 resources 项 fileHash 不是 64 位十六进制")
        out[rel] = (size, digest.lower())
    return out


def verify_resources(expect_id, entry, members, resource_mod, context, stage):
    """路径集与 size/fileHash（取自同一次 view）及 HTTP 取回的原始 bytes 都须等于候选 ZIP。"""
    expected = sorted(rel for rel in members if rel != SKILL_FILE)
    got = platform_resource_map(entry, stage, resource_mod.valid_path)
    if sorted(got) != expected:
        raise Fail(stage, "资源路径集不等（平台 %d 项／候选 %d 项）" % (len(got), len(expected)))
    planned = []
    for rel in expected:
        item = (rel, len(members[rel]), sha256(members[rel]))
        if got[rel] != item[1:]:
            raise Fail(stage, "资源 size／fileHash 与候选不等：%s" % safe_path(rel))
        planned.append(item)
    if not planned:
        return 0
    # collect 逐项取回原始 bytes，并要求其长度与 sha256 等于 planned（即候选 ZIP 内该资源）
    try:
        client = resource_mod.ResourceClient(time.monotonic() + RESOURCE_HTTP_BUDGET, context)
        resource_mod.collect(client, expect_id, planned, HTTP_WORKERS)
    except resource_mod.ResourceError as exc:
        raise Fail(stage, "资源 HTTP 回读失败：%s" % exc)
    except Exception as exc:
        raise Fail(stage, "资源 HTTP 回读异常（%s）" % exc.__class__.__name__)
    return len(planned)


def source_identity(entry, account_id, bucket, key, stage):
    """identifier 须为 `url.<CF_ACCOUNT_ID>.r2.cloudflarestorage.com.<bucket>.<key>` 且与本次一致。

    证明所写 key 就是该对象的既有来源；不以「ZIP 相同」推定，也不回显 identifier。
    """
    ident = entry.get("identifier")
    prefix = "url.%s.%s." % (account_id, R2_HOST)
    if not isinstance(ident, str) or not account_id or not ident.startswith(prefix):
        raise Fail(stage, "平台 identifier 不是 url.<CF_ACCOUNT_ID>.%s.<bucket>.<key> 形态："
                          "无法证明既有来源，拒绝部署" % R2_HOST)
    src_bucket, sep, src_key = ident[len(prefix):].partition(".")
    if not sep or src_bucket != bucket or src_key != key:
        raise Fail(stage, "平台 identifier 的 bucket／key 与本次上传不一致：拒绝部署")


# ── 官方 HTTP 写入（install／edit）──────────────────────────────────────────────

def https_connection(host, timeout):
    """写入连接单点缝：标准库 HTTPS，不跟随重定向。"""
    return http.client.HTTPSConnection(host, timeout=timeout)


class _Transient(Exception):
    pass


def _write_once(context, kind, payload, stage):
    origin, key = context
    body = json.dumps({"json": payload}, ensure_ascii=False).encode("utf-8")
    headers = {"X-API-Key": key, "User-Agent": "curl/8.7.1", "Accept": "application/json",
               "Content-Type": "application/json", "Connection": "close",
               "Content-Length": str(len(body))}
    conn = None
    try:
        conn = https_connection(urlsplit(origin).hostname, WRITE_TIMEOUT)
        conn.request("POST", WRITE_PROCEDURES[kind], body=body, headers=headers)
        resp = conn.getresponse()
        if 500 <= resp.status <= 599:
            raise _Transient("status=%d" % resp.status)
        if resp.status != 200:
            raise Fail(stage, "官方写入未返回 200（status=%d）：不回显响应体，不重试" % resp.status)
        ctype = (resp.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            raise Fail(stage, "官方写入返回 200 但 Content-Type 非 json：不重试")
        raw = resp.read(WRITE_BODY_LIMIT + 1)
        if len(raw) > WRITE_BODY_LIMIT:
            raise Fail(stage, "官方写入响应体超过 %d B 上限：不回显" % WRITE_BODY_LIMIT)
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            doc = None
        # 200 只表示请求被接受；error 信封或非 result 形态都是失败，成功另由完整回读判定
        if not isinstance(doc, dict) or "error" in doc or not isinstance(doc.get("result"), dict):
            raise Fail(stage, "官方写入返回错误信封或非 result 形态（status=200）：不回显响应体")
    except (OSError, http.client.HTTPException) as exc:
        raise _Transient(exc.__class__.__name__)
    except ValueError as exc:
        raise Fail(stage, "官方写入请求参数异常（%s）" % exc.__class__.__name__)
    finally:
        if conn is not None:
            conn.close()


def write_skill_http(context, kind, payload, stage, guard=None):
    """POST 官方 tRPC mutation；`guard` 在每次尝试（含重试）发请求前调用，用于写前复核。"""
    attempts = len(WRITE_RETRY_DELAYS) + 1 if kind == "edit" else 1
    for attempt in range(attempts):
        if guard is not None:
            guard()
        try:
            return _write_once(context, kind, payload, stage)
        except _Transient as exc:
            if attempt + 1 == attempts:
                raise Fail(stage, "官方写入瞬时失败（%s），已尝试 %d 次：不再重试、不改用 CLI"
                            % (exc, attempts))
            log("官方写入（%s）瞬时失败（%s）；第 %d 次重试" % (kind, exc, attempt + 1))
            time.sleep(WRITE_RETRY_DELAYS[attempt])


# ── 本地包校验 ───────────────────────────────────────────────────────────────

def zip_members(blob, stage):
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            return dict((info.filename, archive.read(info)) for info in archive.infolist())
    except (zipfile.BadZipFile, OSError) as exc:
        raise Fail(stage, "ZIP 不可读（%s）" % exc.__class__.__name__)


def package_problems(entries, name, members, body_contract):
    if not entries:
        return ["空包（源内无文件）"]
    problems = []
    for rel, path in entries:
        mode = os.stat(path).st_mode & 0o7777
        if mode != 0o644:
            problems.append("非常规权限 %04o：%s（源文件须 0644，本工具不压平权限）" % (mode, rel))
    if (sorted(members) != sorted(rel for rel, _ in entries)
            or any(members[rel] != read_bytes(path) for rel, path in entries)):
        problems.append("ZIP 与源文件不等")
    raw = members.get(SKILL_FILE)
    if raw is None:
        problems.append("缺根 %s" % SKILL_FILE)
        return problems
    try:
        fm_name = body_contract.fm_get(raw, "name")
        body = body_contract.body_bytes(raw)
    except body_contract.ContractError as exc:
        problems.append("%s 不合正文契约（%s）" % (SKILL_FILE, exc.code))
        return problems
    if fm_name != name:
        problems.append("%s frontmatter name 缺失或与 --name 不等" % SKILL_FILE)
    if not body.strip():
        problems.append("%s 正文为空" % SKILL_FILE)
    return problems


def official_originals_problem(obj, members):
    """luno-surge：声明恰为 3 份参考原件，且包内原件哈希等于 manifest 的 raw_sha256。"""
    block = obj.get("officialPackageResources")
    paths = block.get("paths") if isinstance(block, dict) else None
    if not isinstance(paths, list) or sorted(map(str, paths)) != sorted(OFFICIAL_ORIGINALS):
        return "officialPackageResources 须恰好声明 3 份参考原件（缺失／损坏即拒绝，不绕过）"
    try:
        raw = json.loads(members[OFFICIAL_MANIFEST].decode("utf-8"))["raw_sha256"]
    except (KeyError, ValueError, TypeError, UnicodeDecodeError):
        return "官方原件 manifest 不可读或缺 raw_sha256"
    root = OFFICIAL_ROOT + "/"
    for rel, key in sorted(OFFICIAL_ORIGINALS.items()):
        expect = raw.get(key) if isinstance(raw, dict) else None
        if not isinstance(expect, str) or not SHA256_RE.match(expect):
            return "manifest 的 %s 哈希形态非法" % key
        data = members.get(rel[len(root):])
        if data is None:
            return "官方参考原件缺失（%s）：先按 SOURCE.md〈取件与部署〉取件并核对哈希" % rel
        if sha256(data) != expect:
            return "官方参考原件哈希不符 manifest（%s）：不换来源" % rel
    return None


def check_inventory(obj, src_rel, members):
    """登记资源（luno-surge 另加官方取件原件）须恰等于候选包内 SKILL.md 以外的文件。"""
    official = set()
    if src_rel == OFFICIAL_ROOT:
        problem = official_originals_problem(obj, members)
        if problem:
            raise Fail(STAGE_INVENTORY, "官方取件门禁未通过：%s" % problem)
        official = set(OFFICIAL_ORIGINALS)
    elif obj.get("officialPackageResources"):
        raise Fail(STAGE_INVENTORY, "登记异常：官方取件登记只允许 luno-surge")
    res = obj.get("resources")
    if not isinstance(res, list) or not all(isinstance(r, str) for r in res) \
            or len(set(res)) != len(res):
        raise Fail(STAGE_INVENTORY, "登记异常：resources 须为不重复的路径数组")
    declared = set(res)
    if declared & official:
        raise Fail(STAGE_INVENTORY, "登记异常：官方取件原件不得同时登记为普通资源")
    live = set(src_rel + "/" + rel for rel in members if rel != SKILL_FILE)
    ghost = sorted((declared | official) - live)
    extra = sorted(live - declared - official)
    if ghost or extra:
        raise Fail(STAGE_INVENTORY, "资源完整清单未通过：登记有、包内无［%s］；包内有、登记无［%s］"
                    % ("，".join(map(safe_path, ghost)), "，".join(map(safe_path, extra))))


def source_change(pack, dedicated, src_abs, members):
    """重新收集＋构包，与候选逐文件比较；只判定，不替换候选。返回问题说明或 None。"""
    try:
        now = zip_members(pack_call(pack.build, pack_call(pack.collect, src_abs, dedicated),
                                    dedicated), STAGE_LOCAL)
    except Fail as exc:
        return "源端无法复核（%s）" % exc.detail
    changed = sorted(set(now) ^ set(members)
                     | set(rel for rel in set(now) & set(members) if now[rel] != members[rel]))
    return "变化文件［%s］" % "，".join(map(safe_path, changed)) if changed else None


# ── 参数、登记与打包器 ─────────────────────────────────────────────────────────

REQUIRED_ARGS = ("--repo", "--src", "--name", "--key", "--out-dir", "--expect-id")


def parse_args(argv):
    """返回 (cfg, 错误说明)；`--help` 打印用法并退出 0。"""
    got, i = {"deploy": False}, 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            sys.stdout.write(USAGE + "\n")
            raise SystemExit(0)
        if arg == "--deploy":
            got["deploy"] = True
            i += 1
            continue
        if arg not in REQUIRED_ARGS and arg != "--expect-zip-sha256":
            return None, "未知参数 %s" % arg
        if i + 1 >= len(argv):
            return None, "参数 %s 缺值" % arg
        value = argv[i + 1]
        if arg == "--expect-zip-sha256":
            if arg in got:
                return None, "参数 %s 不允许重复给出" % arg
            if not SHA256_RE.fullmatch(value):      # 不回显外部值
                return None, "参数 %s 须为完整 64 位小写十六进制 SHA-256" % arg
        got[arg] = value
        i += 2
    if "--src" not in got:
        return None, "缺少必填参数 --src（不用环境变量、不按名称猜源目录）"
    missing = [arg for arg in REQUIRED_ARGS if arg not in got]
    if missing:
        return None, "缺少必填参数：%s" % "／".join(missing)
    return got, None


def resolve_target(cfg):
    """核参数与登记完全一致；返回 (repo, src_rel, src_abs, 登记对象)。"""
    repo = os.path.abspath(cfg["--repo"])
    name, key, expect_id = cfg["--name"], cfg["--key"], cfg["--expect-id"]
    if not NAME_RE.match(name):
        raise Fail(STAGE_LOCAL, "--name 须为小写 slug（a-z0-9-）")
    if not PLATFORM_ID_RE.match(expect_id):
        raise Fail(STAGE_LOCAL, "--expect-id 须为 skl_<字母数字> 形态")
    if not KEY_RE.match(key):
        raise Fail(STAGE_LOCAL, "--key 须为单段对象 key（A-Za-z0-9._-，≤128）；不接受 URL／路径")
    path = os.path.join(repo, "tools", "sync-targets.json")
    if not os.path.isfile(path):
        raise Fail(STAGE_LOCAL, "--repo 内缺登记真源：%s" % path)
    try:
        objects = json.loads(read_bytes(path).decode("utf-8")).get("objects")
    except (ValueError, UnicodeDecodeError, AttributeError) as exc:
        raise Fail(STAGE_LOCAL, "登记不可读（%s）" % exc.__class__.__name__)
    hits = [o for o in objects or [] if isinstance(o, dict)
            and o.get("id") == name and o.get("type") == "skill"]
    if len(hits) != 1:
        raise Fail(STAGE_LOCAL, "登记中 type=skill 且 id=%s 的对象不是恰好 1 个（%d 个）"
                    % (name, len(hits)))
    obj = hits[0]
    source = obj.get("source")
    if not isinstance(source, str) or os.path.basename(source) != SKILL_FILE:
        raise Fail(STAGE_LOCAL, "登记对象的 source 不是 <目录>/%s" % SKILL_FILE)
    src_abs = os.path.normpath(os.path.join(repo, cfg["--src"]))
    src_rel = os.path.relpath(src_abs, repo).replace(os.sep, "/")
    if src_rel != os.path.dirname(source):
        raise Fail(STAGE_LOCAL, "--src 与登记源路径不一致（不按名称猜源目录）：登记 %s ≠ 参数 %s"
                    % (os.path.dirname(source), src_rel))
    ends = obj.get("ends")
    lobe = ends.get("lobehub") if isinstance(ends, dict) else None
    if not isinstance(lobe, dict) or lobe.get("present") is not True or lobe.get("id") != expect_id:
        raise Fail(STAGE_LOCAL, "--expect-id 与登记的 LobeHub 平台 ID 不一致或该端未登记")
    if os.path.islink(src_abs) or not os.path.isdir(src_abs):
        raise Fail(STAGE_LOCAL, "--src 不是普通目录（不存在／非目录／符号链接）：%s" % src_rel)
    return repo, src_rel, src_abs, obj


def resolve_out_dir(out_dir, src_abs):
    out_abs = os.path.abspath(out_dir)
    if not os.path.isdir(out_abs):
        raise Fail(STAGE_LOCAL, "--out-dir 不是已存在目录（本工具不创建目录）：%s" % out_abs)
    src_real, out_real = os.path.realpath(src_abs), os.path.realpath(out_abs)
    if out_real == src_real or out_real.startswith(src_real + os.sep):
        raise Fail(STAGE_LOCAL, "--out-dir 位于 --src 之内（产物会被下次打包吸入）：%s" % out_abs)
    return out_abs


def load_packer(repo, src_rel):
    """返回 (打包器, 是否专用)。专用器须是登记源内的普通文件（解析链接后），先核再导入，不回退。"""
    rel = DEDICATED_PACKERS.get(src_rel)
    if rel is None:
        return load_module(os.path.join(repo, "tools", "pack-skill-zip.py"), "pack_skill_zip"), False
    path = os.path.join(repo, rel)
    real_src = os.path.realpath(os.path.join(repo, src_rel))
    if not os.path.isfile(path) or not os.path.realpath(path).startswith(real_src + os.sep):
        raise Fail(STAGE_LOCAL, "专用打包器缺失或解析后不在登记源内：拒绝加载，"
                                "不回退通用打包器（%s）" % rel)
    try:
        return load_module(path, "dedicated_package_release"), True
    except (Exception, SystemExit) as exc:
        raise Fail(STAGE_LOCAL, "专用打包器导入失败（%s）；未产出包" % exc.__class__.__name__)


def pack_call(func, arg, dedicated):
    """专用器的任何异常只报类名（其消息可能含秘密命中细节）。"""
    try:
        return func(arg)
    except OSError as exc:
        raise Fail(STAGE_PACK, "源收集失败（符号链接／非常规条目／读取错误）：%s"
                    % (exc.__class__.__name__ if dedicated else exc))
    except (Exception, SystemExit) as exc:
        if not dedicated:
            raise
        raise Fail(STAGE_PACK, "专用打包器拒绝该源（%s）；未产出包" % exc.__class__.__name__)


# ── 部署 ─────────────────────────────────────────────────────────────────────

def require_authorization():
    if os.environ.get(AUTH_ENV) != "1":
        raise Fail(STAGE_AUTH, "防误触断言未通过：--deploy 须 %s=1（不是授权来源，须先核既有部署授权）；"
                               "未产生任何写操作" % AUTH_ENV)


def hash_matches(entry, digest):
    value = entry.get("zipFileHash")
    return isinstance(value, str) and value.lower() == digest


def editable(entry):
    """可经 update 修补的三个值（content 按 bytes 比较）。"""
    return {"name": entry.get("name"), "description": entry.get("description") or "",
            "content": (entry.get("content") or "").encode("utf-8")}


def mismatched(entry, want):
    have = editable(entry)
    return [field for field in ("name", "description", "content") if have[field] != want[field]]


def poll_repaired(expect_id, digest, want):
    """修补后按等待表轮询（总预算含读取）；zipFileHash 一变即停，全部相等即返回该次回读。"""
    start, polls, problems = time.monotonic(), 0, []
    for delay in REPAIR_POLL_DELAYS:
        if delay > REPAIR_POLL_BUDGET - (time.monotonic() - start):
            break
        time.sleep(delay)
        left = REPAIR_POLL_BUDGET - (time.monotonic() - start)
        if left <= 0:
            break
        polls += 1
        entry = platform_entry(expect_id, STAGE_READBACK, timeout=left)
        if not hash_matches(entry, digest):
            raise Fail(STAGE_READBACK, "修补后第 %d 轮回读 zipFileHash 与候选不一致：停止" % polls)
        problems = mismatched(entry, want)
        if not problems:
            return entry
    raise Fail(STAGE_READBACK, "修补后轮询 %d 次仍未收敛（不等字段：%s）"
                % (polls, "／".join(problems) or "无读取"))


def readback_and_repair(after, expect_id, digest, want, context):
    """安装后：zipFileHash 不符即停；只修补 name／description 与「恰少一个尾 LF」的正文。"""
    if not hash_matches(after, digest):
        raise Fail(STAGE_READBACK, "回读 zipFileHash 与候选 ZIP sha256 不一致")
    got = editable(after)["content"]
    body = want["content"]
    if got != body and not (body.endswith(b"\n") and got == body[:-1]):
        raise Fail(STAGE_READBACK, "正文不等且非恰少一个尾 LF；停止，不自动改写")
    fields = mismatched(after, want)
    if not fields:
        return after
    payload = {"id": expect_id}
    if "content" in fields:
        payload["content"] = body.decode("utf-8")
    if "name" in fields or "description" in fields:
        payload["manifest"] = {"name": want["name"], "description": want["description"]}
    baseline = editable(after)

    def guard():
        # 平台无 CAS：每次 update 前重读，出现「既非基线也非期望」的第三个值即停，不覆盖他人改动
        now = platform_entry(expect_id, STAGE_EDIT)
        if not hash_matches(now, digest):
            raise Fail(STAGE_EDIT, "写前复核：zipFileHash 已变化，未发 update")
        current = editable(now)
        third = [f for f in ("name", "description", "content")
                 if current[f] not in (baseline[f], want[f])]
        if third:
            raise Fail(STAGE_EDIT, "写前复核发现并发变更（字段：%s）：停止，不用 update 覆盖"
                        % "／".join(third))

    write_skill_http(context, "edit", payload, STAGE_EDIT, guard)
    log("修补：agentSkills.update 已返回 200（字段：%s），待轮询回读" % "／".join(fields))
    return poll_repaired(expect_id, digest, want)


def run_deploy(cfg, repo, out_abs, src_abs, pack, dedicated, blob, digest, members, body_contract):
    name, key, expect_id = cfg["--name"], cfg["--key"], cfg["--expect-id"]
    resource_mod = load_module(os.path.join(repo, "tools", "resource_http.py"), "resource_http")
    try:
        context = resource_mod.connection_context()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, resource_mod.ResourceError) else exc.__class__.__name__
        raise Fail(STAGE_PLATFORM, "同域前置未通过（%s；须 %s 为受批准实例、LOBEHUB_CLI_API_KEY 有效、"
                                   "不设 LOBEHUB_WORKSPACE_ID）；停止本次部署，未执行平台或存储写入"
                    % (reason, resource_mod.ORIGIN_ENV))
    freeze_cli_runner(*context)

    skill_md = members[SKILL_FILE]
    desc = body_contract.fm_get(skill_md, "description")
    want = {"name": name, "content": body_contract.body_bytes(skill_md),
            "description": "" if desc is body_contract.MISSING or desc is None else desc}

    before = platform_entry(expect_id, STAGE_PLATFORM)
    if before.get("name") != name:
        raise Fail(STAGE_PLATFORM, "平台回读 name 与 --name 不符")
    source_identity(before, os.environ.get("CF_ACCOUNT_ID"), os.environ.get("R2_BUCKET"), key,
                    STAGE_PLATFORM)
    pre_hash = before.get("zipFileHash")
    if not isinstance(pre_hash, str) or not SHA256_RE.match(pre_hash.lower()):
        raise Fail(STAGE_ROLLBACK, "平台部署前 zipFileHash 不是完整 64 位十六进制；回滚能力不成立，停止部署")
    pre_hash = pre_hash.lower()
    log("平台回读（部署前）：id=%s zipFileHash=%s" % (expect_id, pre_hash))

    change = source_change(pack, dedicated, src_abs, members)
    if change:
        raise Fail(STAGE_SNAPSHOT, "打包后源端已变化（未进入写路径；未上传）：%s" % change)

    if pre_hash == digest:
        problems = mismatched(before, want)
        if problems:
            raise Fail(STAGE_READONLY, "未变对象核验未通过（未执行部署写入；本分支不修补）：%s 不等"
                        % "／".join(problems))
        count = verify_resources(expect_id, before, members, resource_mod, context, STAGE_READONLY)
        log("核验一致，未执行部署写入（资源 %d 项 bytes 相等；零上传／零 install／零 edit）" % count)
        return

    storage = open_storage()
    rollback = storage.download(key)
    if sha256(rollback) != pre_hash:
        raise Fail(STAGE_ROLLBACK, "同 key 现存对象与平台部署前 zipFileHash 不一致；回滚能力不成立，停止部署")
    rollback_path = os.path.join(out_abs, name + ".predeploy.zip")
    write_atomic(rollback_path, rollback, STAGE_ROLLBACK)
    if sha256(read_bytes(rollback_path)) != pre_hash:
        raise Fail(STAGE_ROLLBACK, "回滚包实读 sha256 与平台部署前哈希不一致")
    log("回滚包：%s（实读 sha256＝部署前 zipFileHash）" % rollback_path)

    storage.upload(key, blob)
    log("上传：key=%s bytes=%d sha256=%s" % (key, len(blob), digest))
    url = storage.presigned_get(key)
    if storage.fetch(url) != blob:
        raise Fail(STAGE_DOWNLOAD, "预签名 GET 所得 bytes 与候选 ZIP 不一致")
    write_skill_http(context, "install", {"url": url}, STAGE_INSTALL)
    log("安装：importFromUrl 已返回 200，待完整回读判等")

    after = readback_and_repair(platform_entry(expect_id, STAGE_READBACK), expect_id, digest,
                                want, context)
    count = verify_resources(expect_id, after, members, resource_mod, context, STAGE_READBACK)
    change = source_change(pack, dedicated, src_abs, members)
    if change:
        raise Fail(STAGE_SNAPSHOT_AFTER, "部署已写入完成，但源目录在部署窗口内发生变化，须人工确认是否重投"
                                         "：%s" % change)
    log("回读判等：zipFileHash／name／description／正文／资源 %d 项全部相等" % count)


def run(cfg):
    repo, src_rel, src_abs, obj = resolve_target(cfg)
    out_abs = resolve_out_dir(cfg["--out-dir"], src_abs)
    name, deploy, expect = cfg["--name"], cfg["deploy"], cfg.get("--expect-zip-sha256")
    if deploy:
        require_authorization()
        if src_rel in DEDICATED_PACKERS and expect is None:
            raise Fail(STAGE_LOCAL, "该技能（%s）走专用打包器，--deploy 必须显式给出 --expect-zip-sha256；"
                                    "未加载专用打包器、未产出包、未访问平台或存储" % src_rel)
    pack, dedicated = load_packer(repo, src_rel)
    body_contract = load_module(os.path.join(repo, "tools", "body_contract.py"), "body_contract")
    entries = pack_call(pack.collect, src_abs, dedicated)
    blob = pack_call(pack.build, entries, dedicated) if entries else b""
    digest = sha256(blob)
    members = zip_members(blob, STAGE_LOCAL) if entries else {}
    problems = package_problems(entries, name, members, body_contract)
    if problems:
        raise Fail(STAGE_LOCAL, "包有效性未通过（不上传）：%s" % "／".join(problems))
    if expect is not None and expect != digest:
        raise Fail(STAGE_LOCAL, "候选 ZIP sha256 与 --expect-zip-sha256 不一致（未上传／未安装）："
                                "预期 %s｜实构 %s" % (expect, digest))
    check_inventory(obj, src_rel, members)
    candidate = os.path.join(out_abs, name + ".zip")
    write_atomic(candidate, blob, STAGE_PACK)
    log("打包：files=%d bytes=%d sha256=%s" % (len(entries), len(blob), digest))
    log("产物：%s" % candidate)
    if not deploy:
        log("写路径：未进入（加 --deploy 才允许上传／安装）")
        return
    try:
        run_deploy(cfg, repo, out_abs, src_abs, pack, dedicated, blob, digest, members,
                   body_contract)
    finally:
        release_cli_runner()


def main(argv):
    try:
        cfg, bad = parse_args(argv)
        if bad is not None:
            raise Fail(STAGE_LOCAL, "参数无效：%s" % bad)
        run(cfg)
    except Fail as exc:
        sys.stderr.write("[deploy] 阶段失败：%s｜%s\n" % (exc.stage, exc.detail))
        return exc.rc
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

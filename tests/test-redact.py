#!/usr/bin/env python3
"""脱敏与读取形态：**输出脱敏测试** ＋ **读取模板契约测试**（离线、确定性、经真实子进程入口）。

本文件包含两类对象不同的测试，**不可互替**：

* **输出脱敏测试**（`ProjectionPositiveControlTest`／`FullDumpNegativeControlTest`／
  `NestedSecretNegativeControlTest`／`TemplateScopeNegativeControlTest`／`FailClosedEntryTest`，
  即下面第 1–5 组）：对象是 测试内 stdin 适配器（不再分发共用 CLI，委托
  `skills/luno-surge/scripts/_privacy.py`）——**整份或嵌套输入经入口后不得残留标记**。
  它只证明「输出侧抹除按契约工作」。
* **读取模板契约测试**（`ReadTemplateContractTest`／`ReadSideContractTest`）：对象是各技能里
  承载读取形态的**模板正文与命令形态**——**命令实际读取的字段面必须落在模板声明的字段面内**
  （四类来源：环境、配置、数据库、平台）。它只证明「模板正文里不出现越范围的读取示例、
  且声明面与命令实际字段面一致」这一**机械可检**部分。

两类测试都**不构成**「自由 Shell 已被机械限制」的证明：本机是自由 Shell，可直接绕过模板
（`env`／`cat`／`psql ...` 裸跑）与入口（不经测试内适配器）；本套件只在**离线夹具与模板
文本**范围内断言，不拦截任何真实命令。读取侧关口仍按 `luno-core`〈秘密面〉⑤ 与各技能模板
由执行者遵守，**不得**把本文件任一组结果当作「读取侧已受强制」的验收证据。

**预算例外（发布者裁定 2026-10-12）**：本文件新建即超过 `test-authoring.md` 的 20,480 B 单文件预算——理由＝读取侧契约与输出侧同源，拆开会割裂判据；降级路径＝**退出 `full`**、按命中 `case test-redact.py`／`group privacy` 定向运行（**不得只跑新增例替代整入口**）。实测入口 `case test-redact.py`：**28 例 PASS，约 1–2 s**（iSH 负载波动下曾见 4 s）。

输出侧判据分五组（前四组＝派发要求的口径，第五组＝入口契约）：
1. **允许投影正控**：只取声明的字段／键名与长度时，输出**不含标记**且形态不变——投影元数据
   （键名、长度、列名）必须原样保留，不能被脱敏吃掉。
2. **全量／未知字段负控**：`env` 形态全量、`SELECT *` 结果、整份配置（代理行 + keystore 段）
   经共用入口后不得残留标记（标记在**多种已覆盖形态**下逐条断言：敏感键名、URL userinfo、
   JWT、已知 token 前缀、代理行凭据位、keystore 段）。
3. **嵌套秘密负控**：JSON 嵌套对象／转义内层 JSON／数组容器／引号尾段中的标记不得残留，且
   JSON 夹具脱敏后仍可解析（形态未被破坏）。
4. **命令与声明范围不一致负控**：模板正文按**文本断言**核验——夹具从模板所在文件**现读**，
   不硬编码清单：每个反引号片段若命中禁止原语（`env`／`printenv`／`.Config.Env` 全量／
   `cat`／`SELECT *`／`row_to_json`），须处在**禁止语境**（同一分句内先出现「禁／不得／不用／
   不取／不整／勿」）；同时正向断言各模板的声明范围原语确实在文件里（防止锚点漂移后空转）。
5. **fail-closed**：内部异常时 stdout 为空、stderr 简短、非零退出；未知参数拒绝；非 UTF-8
   输入拒绝（不做 surrogateescape 兜底）。

覆盖边界的诚实口径：入口的抹除范围＝被复用模块自身的键名集与形态兜底；**未命中键名、又不属
形态兜底的取值不会被抹除**，本用例**不为这些边界背书**，也不放宽它（读取侧关口仍按
`luno-core`〈秘密面〉⑤ 与各技能模板）。2026-10-12 本机实测的两处边界，逐项状态：
  * SCREAMING_SNAKE 前缀键名（`POSTGRES_PASSWORD` 一类「以 `_`／`-` 分隔的敏感词段」）——**2026-10-12
    R2 已闭合**（键名集扩到分隔段形态；定向回归见 `tests/test-surge-scripts.py::R2JsonContractAndSegmentKeyTest`）。
    身份词（`user`／`username`）不参与该扩展，`USER_AGENT` 一类非敏感键名输出不变；本用例下方
    的 env 夹具因此**不必**改（已知名仍只用裸敏感键名，未知名仍用 JWT 与已知 token 前缀）。
  * 长不透明串规则的前视排除 `=`——紧跟在 `=` 之后的 40+ 字符不透明串不抹除（**仍为残余**：
    R2 未做，收敛改法会显著扩大误抹，代价已在模块内登记）。
故下面第 2 组的 env 夹具对**未知名**改用 JWT 与已知 token 前缀取值（形态兜底），对**已知名**
直接用敏感键名；`SELECT *` 与整份配置同样只覆盖已覆盖形态。

标记用低熵串（`ZMARK` 及由其拼接的 40+ 字符长串），全部为**合成夹具**，不是任何真实凭据。
"""
import importlib.util
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REDACT_ADAPTER = 'import importlib.util\nimport os\nimport sys\n\n_REPO_ROOT = __REPO_ROOT__\n\n# 共用实现来源（仓库相对路径，由本文件位置推导；不改名、不复制）\nPRIVACY_REL = os.path.join("skills", "luno-surge", "scripts", "_privacy.py")\nPRIVACY_PATH = os.path.join(_REPO_ROOT, PRIVACY_REL)\n\nUSAGE = "用法：测试内 stdin 适配器   # 只读 stdin、只写 stdout，无参数\\n"\n\n_MODULE = None\n\n\ndef privacy_module():\n    """按仓库相对路径加载共用脱敏模块；同一进程只加载一次。"""\n    global _MODULE\n    if _MODULE is None:\n        spec = importlib.util.spec_from_file_location("luno_shared_privacy", PRIVACY_PATH)\n        if spec is None or spec.loader is None:\n            raise RuntimeError("无法定位共用脱敏模块：%s" % PRIVACY_REL)\n        module = importlib.util.module_from_spec(spec)\n        sys.modules[spec.name] = module\n        spec.loader.exec_module(module)\n        _MODULE = module\n    return _MODULE\n\n\ndef redact_text(text):\n    """文本路径脱敏：原样委托共用模块，不追加规则、不放行任何字段。"""\n    return privacy_module().redact_text(str(text))\n\n\ndef _read_text(stdin):\n    """读 stdin：真实管道走字节缓冲并**严格** UTF-8 解码；文本流（用例注入）直接读。"""\n    buffer = getattr(stdin, "buffer", None)\n    if buffer is not None:\n        return buffer.read().decode("utf-8")\n    return stdin.read()\n\n\ndef _write_text(stdout, text):\n    """写 stdout：真实管道写 UTF-8 字节（不受 locale 编码影响）；文本流（用例注入）直接写。"""\n    buffer = getattr(stdout, "buffer", None)\n    if buffer is not None:\n        buffer.write(text.encode("utf-8"))\n        buffer.flush()\n        return\n    stdout.write(text)\n    stdout.flush()\n\n\ndef main(argv=None, stdin=None, stdout=None, stderr=None):\n    """入口：返回退出码，不自行 `sys.exit`（便于离线用例直接调用）。"""\n    argv = list(sys.argv[1:] if argv is None else argv)\n    stdin = sys.stdin if stdin is None else stdin\n    stdout = sys.stdout if stdout is None else stdout\n    stderr = sys.stderr if stderr is None else stderr\n    if argv:\n        stderr.write(USAGE)\n        return 2\n    try:\n        text = _read_text(stdin)\n        clean = redact_text(text)\n    except Exception as exc:                       # fail-closed：只报类别，不复述内容\n        stderr.write("redact: 处理失败，未输出任何内容（%s）\\n" % type(exc).__name__)\n        return 1\n    _write_text(stdout, clean)\n    return 0\n\n'.replace("__REPO_ROOT__", repr(str(ROOT)))
REDACT_COMMAND = REDACT_ADAPTER + "\nif __name__ == '__main__': sys.exit(main())\n"

M = "ZMARK"                       # 低熵标记：避开本机隐私掩码对高熵串的展示掩码
LONG = M * 9                      # 40+ 字符不透明串（模块的形态兜底面）
DBLOB = LONG + "0123456789abcdef"
# 形态兜底的另两类（未命中键名时仍应抹除）：JWT 与已知 token 前缀
JWT = "eyJ" + M + "abc." + M + "def." + M + "gh"
SKKEY = "sk-" + M + "0123456789abcdef"

OPS = ROOT / "skills/luno-ops"
HUB = ROOT / "skills/luno-lobehub"
MINIS = ROOT / "skills/luno-minis"
SYNC = ROOT / "skills/luno-sync"

# 承载读取形态模板的文件（现读；第 4 组按锚点断言，不抄内容）
TEMPLATE_FILES = {
    "ops-entry": OPS / "SKILL.md",
    "ops-runtime": OPS / "references/service-runtime.md",
    "hub-instance": HUB / "references/instance.md",
    "hub-entry": HUB / "SKILL.md",
    "minis-config": MINIS / "references/configuration.md",
    "sync-workflow": SYNC / "references/sync-workflow.md",
}

# 声明范围原语（每份模板必须真的给出可执行形态，防止用例在锚点漂移后空转）
ANCHORS = {
    "ops-entry": ["references/service-runtime.md", "声明的指定键"],
    "ops-runtime": ["docker exec", "sh -c", "len=%s", "awk -F=",
                    'length(substr($0,index($0,"=")+1))', "jq '{port: .server.port",
                    "docker compose config --quiet", "缺接口即停依赖"],
    "hub-instance": ["information_schema.columns", "SELECT", "人已确认的列白名单", "LIMIT"],
    # 平台侧投影口径：筛选／分页只缩小记录集、不替代字段投影（真源现读，防静默删除）
    "minis-config": ["筛选／分页只缩小记录集，不替代字段投影", "字段形态与路径写法"],
}

# 禁止原语（出现在反引号片段里即视为「命令示例」，除非处在禁止语境）
FORBIDDEN = (
    ("env", re.compile(r"(?<![\w./-])env(?![\w-])")),
    ("printenv", re.compile(r"printenv")),
    ("Config.Env", re.compile(r"\.Config\.Env")),
    ("cat", re.compile(r"(?<![\w./-])cat(?![\w-])")),
    ("SELECT *", re.compile(r"(?i)select\s+\*")),
    ("row_to_json", re.compile(r"row_?to_?json")),
)
PROHIBITION = re.compile(r"禁|不得|不用|不取|不整|勿|拒绝|不")
CLAUSE_SPLIT = re.compile(r"[。；，]")
BACKTICK = re.compile(r"`([^`\n]+)`")

def load_entry():
    """按路径加载入口模块（不执行 `__main__`），供 fail-closed 用例注入异常。"""
    import types
    module = types.ModuleType("redact_test_adapter")
    exec(compile(REDACT_ADAPTER, "<redact-test-adapter>", "exec"), module.__dict__)
    return module

_ENTRY = None

def entry():
    """入口模块（按路径加载一次；用例就地复用）。"""
    global _ENTRY
    if _ENTRY is None:
        _ENTRY = load_entry()
    return _ENTRY

def run_entry(text, args=()):
    """经**真实子进程入口**（stdin → stdout）脱敏，返回 (rc, stdout, stderr)。"""
    proc = subprocess.run([sys.executable, "-B", "-c", REDACT_COMMAND] + list(args),
                          input=text.encode("utf-8"), capture_output=True)
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")

def redact(fixture):
    """经入口 `main()` 脱敏（就地；真实管道路径由 ProjectionPositiveControlTest 与
    FailClosedEntryTest 的子进程用例另行覆盖）。夹具的标记由调用方先断言在输入中。"""
    out, err = io.StringIO(), io.StringIO()
    rc = entry().main([], stdin=io.StringIO(fixture), stdout=out, stderr=err)
    if rc != 0 or err.getvalue():
        raise AssertionError("入口异常退出：rc=%s stderr=%r" % (rc, err.getvalue()[:80]))
    return out.getvalue()

class ProjectionPositiveControlTest(unittest.TestCase):
    """1) 允许投影：只取声明字段／键名与长度时，输出无标记且形态不变。"""

    def test_container_env_projection_survives(self):
        # 容器内对声明的指定键取值长度（模板输出的形态：键名 + 长度 + 是否已设值）
        fixture = "ZTMP len=10 state=set\nZNOTSET len=0 state=unset\nPATH len=18 state=set\n"
        self.assertNotIn(M, fixture)
        self.assertEqual(redact(fixture), fixture)
        self.assertNotIn("<redacted>", redact(fixture))

    def test_db_projection_survives(self):
        # 列白名单 SELECT 的结果（列名 + 值；值均为已确认非秘密字段）
        fixture = "id | provider_id | enabled\n 1 | openai      | t\n"
        self.assertEqual(redact(fixture), fixture)
        self.assertNotIn("<redacted>", redact(fixture))

    def test_config_keyname_listing_survives(self):
        # 配置文件只列键名（模板形态：一行一个键名）
        fixture = "NODE_ENV\nPORT\nLOG_LEVEL\n"
        self.assertEqual(redact(fixture), fixture)
        self.assertNotIn("<redacted>", redact(fixture))

    def test_pipe_path_matches_in_process(self):
        # 真实管道入口（子进程）与就地 main() 必须同结果，且正常路径 rc=0、stderr 空
        fixture = "PATH=/usr/bin\n"
        rc, out, err = run_entry(fixture)
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, redact(fixture))
        self.assertIn("PATH=/usr/bin", out)

    def test_projection_of_secret_named_key_keeps_metadata(self):
        # 投影刻意暴露「键名 + 长度」而不暴露值：键名与长度必须原样留下
        fixture = "API_KEY len=43 state=set\n"
        out = redact(fixture)
        self.assertIn("API_KEY", out)
        self.assertIn("len=43", out)
        self.assertNotIn("<redacted>", out)

class FullDumpNegativeControlTest(unittest.TestCase):
    """2) 全量／未知字段：整份输入经共用入口后不得残留标记。"""

    def test_env_full_dump(self):
        fixture = "\n".join([
            "PATH=/usr/local/sbin",
            "HOME=/root",
            "API_KEY=" + M + "-ENV1",
            "TOKEN=" + M + "-ENV2",
            "SECRET=" + M + "-ENV3",
            "AUTH_KEY=" + M + "-ENV4",
            "DB_URL=postgres://svc:" + M + "-ENV5@db.invalid:5432/app",
            "UNKNOWN_ONE=" + JWT,
            "UNKNOWN_TWO=" + SKKEY,
            "",
        ])
        self.assertIn(M, fixture)
        out = redact(fixture)
        self.assertNotIn(M, out)
        # 非秘密字段保持可读（不是把整份输入一律抹掉）
        self.assertIn("PATH=/usr/local/sbin", out)

    def test_select_star_result(self):
        fixture = json.dumps([{
            "id": 1,
            "email": "a@example.invalid",
            "password_hash": DBLOB,
            "provider": {"apiKey": M + "-DB2", "token": M + "-DB3"},
        }], ensure_ascii=False)
        self.assertIn(M, fixture)
        self.assertIn(DBLOB, fixture)
        out = redact(fixture)
        self.assertNotIn(M, out)
        self.assertNotIn(DBLOB, out)

    def test_whole_config_file(self):
        fixture = "\n".join([
            "ProxyHK = https, hk.example.invalid, 443, deployer, " + M + "-CFG1",
            "Group = select, DIRECT, ProxyHK",
            "[Keystore]",
            "base64 = " + M + "-CFG2",
            "",
        ])
        self.assertIn(M, fixture)
        out = redact(fixture)
        self.assertNotIn(M, out)
        # 策略组行不是凭据行，不得被连带抹掉
        self.assertIn("Group = select, DIRECT, ProxyHK", out)

class NestedSecretNegativeControlTest(unittest.TestCase):
    """3) 嵌套秘密：JSON 嵌套／转义内层 JSON／数组容器／引号尾段。"""

    def test_nested_object(self):
        fixture = json.dumps({"a": {"b": {"token": M + "-N1"}}}, ensure_ascii=False)
        self.assertIn(M, fixture)
        out = redact(fixture)
        self.assertNotIn(M, out)
        self.assertIsInstance(json.loads(out), dict)
        self.assertIn("token", out)

    def test_escaped_inner_json(self):
        fixture = json.dumps({"data": json.dumps({"secret": M + "-N2"})}, ensure_ascii=False)
        self.assertIn(M, fixture)
        out = redact(fixture)
        self.assertNotIn(M, out)
        self.assertIsInstance(json.loads(out), dict)

    def test_array_container(self):
        fixture = json.dumps({"tokens": [M + "-N3a", M + "-N3b"]}, ensure_ascii=False)
        self.assertIn(M, fixture)
        out = redact(fixture)
        self.assertNotIn(M, out)
        self.assertIsInstance(json.loads(out), dict)

    def test_quote_tail(self):
        fixture = 'password="' + M + '-N4,x"\n'
        self.assertIn(M, fixture)
        self.assertNotIn(M, redact(fixture))

    def test_bare_value_then_quoted_field(self):
        fixture = 'password=' + M + '-N5,"' + M + '-N5b,y"\n'
        self.assertIn(M, fixture)
        self.assertNotIn(M, redact(fixture))

class TemplateScopeNegativeControlTest(unittest.TestCase):
    """4) 命令与声明范围不一致：模板正文的文本断言（夹具现读，不抄内容）。"""

    def read(self, key):
        path = TEMPLATE_FILES[key]
        self.assertTrue(path.is_file(), "%s 不存在：%s" % (key, path))
        return path.read_text(encoding="utf-8")

    def test_declared_scope_primitives_present(self):
        # 正向锚点：模板真的给出可执行的声明范围形态（缺锚点即失败，防止用例空转）
        for key, anchors in ANCHORS.items():
            body = self.read(key)
            for anchor in anchors:
                with self.subTest(file=key, anchor=anchor):
                    self.assertIn(anchor, body)

    def test_forbidden_primitives_only_in_prohibition_context(self):
        # 禁止原语若以反引号片段出现，其所在分句内必须已有禁止语（不得作命令示例）
        for key in TEMPLATE_FILES:
            body = self.read(key)
            spans = [(m.start(), m.group(1)) for m in BACKTICK.finditer(body)]
            for start, span in spans:
                for label, pattern in FORBIDDEN:
                    if pattern.search(span) is None:
                        continue
                    with self.subTest(file=key, span=span, primitive=label):
                        clause = CLAUSE_SPLIT.split(body[:start])[-1]
                        self.assertRegex(clause, PROHIBITION,
                                         "禁止原语 %s 出现在非禁止语境的片段：%r" % (label, span))

    def test_equivalent_pointer_removed_from_hub_entry(self):
        # `:34`（Agent 与模型）原文已含等效条款，重复指针按复审判定删除
        body = self.read("hub-entry")
        self.assertNotIn("读取形态按", body)

class FailClosedEntryTest(unittest.TestCase):
    """5) 入口契约：fail-closed 与参数面。"""

    def test_internal_error_keeps_stdout_empty(self):
        module = load_entry()
        text = "API_KEY=" + M + "-FAIL\n"
        self.assertIn(M, text)

        def boom(value):
            raise RuntimeError("synthetic")

        module.redact_text = boom
        out, err = io.StringIO(), io.StringIO()
        rc = module.main([], stdin=io.StringIO(text), stdout=out, stderr=err)
        self.assertNotEqual(rc, 0)
        self.assertEqual(out.getvalue(), "")            # 异常时绝不回写原文
        self.assertNotIn(M, out.getvalue())
        self.assertNotIn(M, err.getvalue())
        self.assertLess(len(err.getvalue()), 120)       # 简短错误

    def test_non_utf8_input_is_refused(self):
        proc = subprocess.run([sys.executable, "-B", "-c", REDACT_COMMAND],
                              input=b"\xff\xfe" + M.encode(), capture_output=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b"")
        self.assertNotIn(M.encode(), proc.stderr)

    def test_unknown_argument_is_refused(self):
        rc, out, err = run_entry("x\n", ("--version",))
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertTrue(err.strip())

    def test_normal_path_exit_zero(self):
        rc, out, err = run_entry("PATH=/usr/bin\n")
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertIn("PATH=/usr/bin", out)

# ===========================================================================
# 读取模板契约测试（读取侧）：命令**实际读取的字段面**必须落在模板**声明面**内。
# 声明面＝模板里带声明语的小句内的同类命令与占位符（现读解析，不硬编码字段清单）。
# ===========================================================================
FULL = "全量面"                  # 无字段投影（整份读）
NARROW_ONLY = "只缩小记录集"      # 筛选／分页：缩小记录集，不替代字段投影
OPAQUE = "非字段读取形态"         # 不在本检查的形态集内（计入残余，不作断言）
PLACEHOLDER = re.compile(r"^<[^>]+>$")        # <文件>／<列1>／<键名>／<fields>：参数化，非具体字段
SENTENCE = re.compile(r"[。；\n]")

def jq_aliases(cmd):
    """`jq '{port: .server.port, ...}'` 的输出字段名（别名），从命令现读。"""
    m = re.search(r"'\{([^}]*)\}'", cmd)
    return {part.split(":")[0].strip() for part in m.group(1).split(",")}

class ReadScopeError(AssertionError):
    """读取面越出声明面（类别标签供用例精确断言）。"""

    def __init__(self, category, detail=""):
        super().__init__("%s%s" % (category, ("：" + detail) if detail else ""))
        self.category = category

# 声明语（各来源类在模板里的声明小句标志；哪些文件必须仍有它们由 DECL_CUE_HOME 钉住）
DECL_CUES = {
    "env": ("声明的指定键",),
    "config": ("声明的指定键", "声明的字段路径"),
    "db": ("人已确认的列白名单", "列名与类型元数据"),
    "platform": ("按字段", "读技能的可用路径"),
    "compose": ("配置持有端已有的投影接口",),
}
# 只有这些声明语小句可以贡献**具体字段名**；其余声明语小句只声明**参数化面**（占位符）。
# 例：库模板里「列名与类型元数据」给元数据列，「人已确认的列白名单」只给 `<列1>, <列2>` 占位——
# 于是往白名单小句里塞一个 `SELECT <具体列>` 仍会被判越范围（分发模板不带实例列名）。
CONCRETE_CUES = {
    "env": ("声明的指定键",),
    "config": ("声明的指定键", "声明的字段路径"),
    "db": ("列名与类型元数据",),
    "platform": ("按字段", "读技能的可用路径"),
    "compose": ("配置持有端已有的投影接口",),
}
OPS_RUNTIME = TEMPLATE_FILES["ops-runtime"]
HUB_ENTRY = TEMPLATE_FILES["hub-entry"]
DECL_CUE_HOME = {
    "ops-runtime": ("env", "config"),
    "hub-instance": ("db",),
    "hub-entry": ("platform",),
}
# 读取形态分类：只认**字段读取形态**；其余不入检查（残余见文件头与最终报告）
CLS_PATTERNS = (
    ("compose", re.compile(r"^docker\s+compose\s+config\b")),
    ("env", re.compile(r"^docker\s+exec\b")),
    ("config", re.compile(r"^awk\s+-F=")),
    ("config", re.compile(r"^jq\b")),
    ("db", re.compile(r"^select\s", re.I)),
    ("platform", re.compile(r"^(?:lh|minis-config)\s")),
)

def _is_placeholder(token):
    return bool(PLACEHOLDER.match(token.strip()))

def _parse_env(cmd):
    m = re.search(r"\bsh((?:\s+[A-Za-z_][A-Za-z0-9_]*)+)\s*$", cmd)
    return set(m.group(1).split()) if m else FULL

def _parse_awk(cmd):
    m = re.search(r'\$1\s*==\s*"([^"]+)"', cmd)
    if m:
        return {m.group(1)}
    return {"<键名>"} if re.search(r"print\s+\$1\b", cmd) else OPAQUE

def _parse_jq(cmd):
    m = re.search(r"'\{(.*?)\}'", cmd)
    if not m:
        return FULL
    return set(re.findall(r"\.\s*[A-Za-z0-9_.]+", m.group(1))) or FULL

def _parse_select(cmd):
    m = re.match(r"(?is)^select\s+(.*?)\s+from\b", cmd.strip())
    if not m:
        return FULL
    items = [t.strip() for t in m.group(1).split(",")]
    return FULL if any(t == "*" for t in items) else set(items)

def _parse_platform(cmd):
    m = re.search(r"--json(?:\s+([A-Za-z0-9_.,*<>/-]+))?", cmd)
    if m:
        return set(m.group(1).split(",")) if m.group(1) else FULL
    m = re.search(r"\bminis-config\s+get\s+(\S+)", cmd)
    if m:
        segs = [s for s in m.group(1).split(".") if s]
        return {segs[-1]} if len(segs) >= 3 else NARROW_ONLY   # 只有对象级＝只缩小记录集
    return OPAQUE

PARSERS = {"env": _parse_env, "config": _parse_awk, "db": _parse_select,
           "platform": _parse_platform, "compose":
           lambda cmd: {"<解析性>"} if re.search(r"--(?:quiet|services|volumes|images)\b", cmd)
           else FULL}

def snippets(body):
    """模板里的反引号片段与其所在小句（小句界＝。；换行；逗号不断句）。"""
    return [(m.group(1), SENTENCE.split(body[:m.start()])[-1]) for m in BACKTICK.finditer(body)]

def classify(span):
    for cls, pattern in CLS_PATTERNS:
        if pattern.match(span.strip()):
            return cls
    return None

def parse_fields(cls, cmd):
    if cls == "config":            # 同一来源类两种形态：awk（键名／指定键长度）与 jq（字段路径）
        return _parse_jq(cmd) if cmd.lstrip().startswith("jq") else _parse_awk(cmd)
    return PARSERS[cls](cmd)

def _nearest_cue(clause, cues):
    """小句内**最近的前置**声明语（避免同句里更早的其它声明语误判归属）。"""
    best, position = None, -1
    for cue in cues:
        index = clause.rfind(cue)
        if index > position:
            best, position = cue, index
    return best

def declared_fields(cls, snips):
    """声明面：命令**最近前置声明语**属具体字段声明时的字段名（占位符＝参数化，不计）。

    这样「同一小句里既给元数据列、又给占位符白名单」的模板不会被误当成一条大声明面——
    往白名单处追加一个具体列名，仍判越范围。"""
    out = set()
    for span, clause in snips:
        if classify(span) != cls:
            continue
        if _nearest_cue(clause, DECL_CUES[cls]) not in CONCRETE_CUES[cls]:
            continue
        fields = parse_fields(cls, span)
        if isinstance(fields, set):
            out |= {t for t in fields if not _is_placeholder(t)}
    return out

def check_read_scope(cls, cmd, declared):
    """命令实际字段面 vs 声明面：越范围按类别拒绝（FULL／NARROW_ONLY／字段超出声明面）。"""
    fields = parse_fields(cls, cmd)
    if fields is FULL:
        raise ReadScopeError("全量读取", cmd.strip()[:60])
    if fields is NARROW_ONLY:
        raise ReadScopeError("只缩小记录集，未做字段投影", cmd.strip()[:60])
    if fields is OPAQUE:
        return fields
    extra = {t for t in fields if not _is_placeholder(t)} - set(declared)
    if extra:
        raise ReadScopeError("字段超出声明面", "、".join(sorted(extra)))
    return fields

class ReadTemplateContractTest(unittest.TestCase):
    """模板里的读取命令不得越出模板声明的字段面（声明面现读、不硬编码清单）。"""

    def read(self, key):
        path = TEMPLATE_FILES[key]
        self.assertTrue(path.is_file(), "%s 不存在：%s" % (key, path))
        return path.read_text(encoding="utf-8")

    def test_declaration_cues_present(self):
        # 漂移防护：声明语小句必须仍在，否则声明面退化为空、本组空转
        for key, classes in DECL_CUE_HOME.items():
            body = self.read(key)
            for cls in classes:
                for cue in DECL_CUES[cls]:
                    with self.subTest(file=key, cls=cls, cue=cue):
                        self.assertIn(cue, body)

    def test_declared_face_is_not_empty(self):
        # 防空转：每类的声明面必须真的解析出声明字段
        for key, classes in DECL_CUE_HOME.items():
            snips = snippets(self.read(key))
            for cls in classes:
                with self.subTest(file=key, cls=cls):
                    self.assertTrue(declared_fields(cls, snips),
                                    "声明面解析为空：%s／%s" % (key, cls))

    def test_read_commands_within_declared_scope(self):
        # 核心判别：命令实际字段 vs 模板声明字段——新增越范围读取示例即红
        for key in TEMPLATE_FILES:
            snips = snippets(self.read(key))
            for cls in sorted(DECL_CUES):
                declared = declared_fields(cls, snips)
                for span, clause in snips:
                    if classify(span) != cls:
                        continue
                    if parse_fields(cls, span) is FULL and PROHIBITION.search(clause):
                        continue                     # 禁止语境里的全量形态＝反例（第 4 组已覆盖）
                    with self.subTest(file=key, cls=cls, span=span[:60]):
                        check_read_scope(cls, span, declared)

class ReadSideContractTest(unittest.TestCase):
    """四类来源（环境／配置／数据库／平台）的读取侧契约：声明面 → 投影 → 输出字段与声明
    **集合相等**且标记消失；命令实际字段越出声明面时**精确断言拒绝类别**。"""

    def read(self, path):
        self.assertTrue(path.is_file(), "模板不存在：%s" % path)
        return path.read_text(encoding="utf-8")

    def snippet(self, path, needle):
        for span, _ in snippets(self.read(path)):
            if needle in span:
                return span
        raise AssertionError("模板中没有含 %r 的命令片段：%s" % (needle, path))

    def scope(self, path, cls):
        return declared_fields(cls, snippets(self.read(path)))

    def assert_rejected(self, cls, cmd, declared, category):
        with self.assertRaises(ReadScopeError) as cm:
            check_read_scope(cls, cmd, declared)
        self.assertEqual(cm.exception.category, category)

    def sh(self, cmd):
        proc = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True,
                              env={"PATH": "/usr/local/bin:/usr/bin:/bin"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def tmpfile(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_env_read_scope(self):
        declared = self.scope(OPS_RUNTIME, "env")
        self.assertTrue(declared)
        cmd = self.snippet(OPS_RUNTIME, 'for k in "$@"')          # 模板现读，不抄命令
        keys = sorted(parse_fields("env", cmd))
        self.assertEqual(set(keys), declared)                      # 命令实际字段＝模板声明面
        source = {"API_KEY": M + "-ENV1", "DB_PASSWORD": M + "-ENV2"}
        self.assertIn(M, json.dumps(source))                       # 夹具先证标记在输入中
        inner = re.search(r"'([^']*)'", cmd).group(1)
        proc = subprocess.run(["sh", "-c", inner, "sh"] + keys,
                              env=dict(source, PATH="/usr/local/bin:/usr/bin:/bin"),
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout                                          # ← 撤防点：换成 json.dumps(source)
        self.assertEqual({l.split()[0] for l in out.strip().splitlines()}, declared)  # 集合相等
        self.assertNotIn(M, out)                                   # 标记消失
        self.assert_rejected("env", "docker exec app sh -c '…' sh API_KEY DB_PASSWORD UNKNOWN_ONE",
                             declared, "字段超出声明面")

    def test_config_read_scope(self):
        # 指定键长度形态：值内含 `=` 时按第一个 `=` 之后整段计长
        length_cmd = self.snippet(OPS_RUNTIME, "length(substr(")
        self.assertEqual(parse_fields("config", length_cmd), {"KEY"})
        path = self.tmpfile("KEY=aa=bbb\nOTHER=xx\n")
        got = self.sh(length_cmd.replace("<文件>", path))
        self.assertEqual(got, "KEY 6")
        old = length_cmd.replace('length(substr($0,index($0,"=")+1))', "length($2)")
        self.assertNotEqual(self.sh(old.replace("<文件>", path)), got)   # 撤防反证：夹具能分辨
        # 嵌套字段路径投影（已确认非凭据的 JSON 配置）
        jq_cmd = self.snippet(OPS_RUNTIME, "jq '{port:")
        declared = parse_fields("config", jq_cmd)                  # 声明面＝命令逐项列出的路径
        self.assertEqual(declared, {".server.port", ".logging.level"})
        source = json.dumps({"server": {"port": 8080, "admin_key": M + "-CFG1"},
                             "logging": {"level": "info", "token": M + "-CFG2"},
                             "top": M + "-CFG3"}, ensure_ascii=False)
        self.assertIn(M, source)                                   # 夹具先证标记在输入中
        out = self.sh(jq_cmd.replace("<文件>", self.tmpfile(source + "\n")))
        self.assertEqual(set(json.loads(out)), jq_aliases(jq_cmd))  # 输出字段＝声明面（集合相等）
        self.assertNotIn(M, out)                                   # 未声明路径的值不出现在输出
        self.assert_rejected("config", "jq '.' <文件>", declared, "全量读取")
        # 越范围类别负控（补 2026-10-12 撤防取证指出的缺口：配置类此前只有「全量读取」一类）
        self.assert_rejected("config", "jq '{port: .server.port, admin_key: .server.admin_key}' <文件>",
                             declared, "字段超出声明面")

    def test_db_read_scope(self):
        path = HUB / "references/instance.md"
        declared = self.scope(path, "db")                          # 模板声明的读字段面（现读）
        self.assertTrue(declared)
        sql = self.snippet(path, "SELECT <列1>")                    # 列白名单读取形态
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.execute("CREATE TABLE providers (id INTEGER, name TEXT, api_key TEXT)")
        db.execute("INSERT INTO providers VALUES (1, 'kcne', ?)", (M + "-DB1",))
        self.assertIn(M, str(db.execute("SELECT * FROM providers").fetchall()))  # 夹具有效
        declared_cols = ("id", "name")                             # 用例声明的列白名单
        for token, value in (("<列1>", declared_cols[0]), ("<列2>", declared_cols[1]),
                             ("<表>", "providers"), ("<条件>", "1=1"), ("<n>", "10")):
            sql = sql.replace(token, value)
        cursor = db.execute(sql)
        fields = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        self.assertEqual(set(fields), set(declared_cols))          # 输出字段集合＝声明面
        self.assertNotIn(M, str(rows))                             # 标记消失
        self.assert_rejected("db", "SELECT api_key FROM providers LIMIT 1",
                             declared, "字段超出声明面")

    def test_platform_read_scope(self):
        declared = self.scope(HUB_ENTRY, "platform")
        self.assertTrue(declared)
        cmd = self.snippet(HUB_ENTRY, "--json content,name,description")
        self.assertEqual(parse_fields("platform", cmd), declared)   # 命令实际字段＝声明面
        record = {"id": "skl_1", "content": "…", "name": "n", "description": "d",
                  "raw": {"credentials": M + "-PF1"}, "extra": M + "-PF2"}
        source = json.dumps(record, ensure_ascii=False)
        self.assertIn(M, source)                                    # 夹具先证标记在输入中
        out = json.dumps({k: record[k] for k in parse_fields("platform", cmd)}, ensure_ascii=False)
        self.assertEqual(set(json.loads(out)), declared)            # 集合相等
        self.assertNotIn(M, out)                                    # 标记消失
        # 字段路径负控（未声明字段）／只缩小记录集／无字段列表
        self.assert_rejected("platform", "lh skill view skl_1 --json content,name,description,raw",
                             declared, "字段超出声明面")
        self.assert_rejected("platform", "minis-config get models --filter kcne",
                             declared, "只缩小记录集，未做字段投影")
        self.assert_rejected("platform", "lh skill view skl_1 --json", declared, "全量读取")

    def test_pagination_does_not_replace_projection(self):
        # 平台口径真源句仍在（筛选／分页只缩小记录集、不替代字段投影）
        self.assertIn("筛选／分页只缩小记录集，不替代字段投影",
                      self.read(MINIS / "references/configuration.md"))

if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把技能目录按确定性布局打成 zip（部署前回滚包与部署包共用），并可选核对 sha256。

确定性布局（与部署脚本一致，逐字沿用）：
  relpath 用 / 分隔、entries.sort() 排序、只收文件（不写目录条目）、
  ZipInfo(rel, date_time=(1980,1,1,0,0,0))、compress_type=ZIP_DEFLATED、
  external_attr=0o644<<16、z.writestr(zi, 原文件字节)。

权限位**统一 0644，不继承源文件模式**：平台侧既有包的布局就是统一 0644——历史例（2026-10-07；
该包已于 2026-10-11 退役、精选吸收进 `luno-sync`）实测：含两个 755 脚本的 `skill-authoring`
包，其平台 `zipFileHash` 只在 0644 布局下逐位相符（改成保留源模式的布局
会得到不同哈希）。因此「继承源模式」会让回滚包与部署包不再复现平台侧既有包；该行为的专项测试保留见 `tests/test-pack-skill-zip.py`。

用法：
  python3 tools/pack-skill-zip.py --src <目录> --out <zip 路径> [--expect <sha256 十六进制>]

stdout（一行，便于粘贴）：files=<n> bytes=<n> sha256=<64hex>

退出码：
  0  打包成功；若给了 --expect 则与其逐位相符
  1  给了 --expect 但不符（stderr 固定一行差异说明；zip 已写出，可用于人工比对）
  2  参数或输入不可用（缺参数／参数未知；--src 不存在、不是目录或目录下无文件；
     --src 自身是符号链接、其下任一子目录或文件是符号链接、或条目不是普通文件；
     --out 位于 --src 之内（含同一路径）；--out 所在目录不存在；遍历 --src 出错
     （错误立即上抛，绝不静默跳过）；读取或写入失败；临时文件清理失败）
     ——**不创建空 zip**

边界：不联网、不读环境变量、最终产物仅为 --out；允许同目录临时文件（失败时尝试删除），
无第三方依赖（Python 3 标准库）。写出是原子的：先写 --out 所在目录内的临时文件，成功后再
os.replace 到 --out；--out 自身是符号链接时由 os.replace 替换链接本身（不写穿其目标）。
**保证边界（不夸大）**：写出失败时**不替换原有输出**，并尝试删除临时文件；删除成功不留残留。
临时文件清理失败返回 2 并报告待清理路径——**此时可能残留临时文件**，须由发布者清理并复核后
才可宣告收尾。
"""
import hashlib
import io
import os
import sys
import tempfile
import zipfile

USAGE = ("用法：python3 tools/pack-skill-zip.py --src <目录> --out <zip 路径> "
         "[--expect <sha256 十六进制>]")
SRC_UNAVAILABLE = "[pack] --src 不可用（不存在、不是目录或目录下无文件）：%s；不创建 zip"
SRC_IS_SYMLINK = "[pack] --src 自身是符号链接：%s；不创建 zip"
COLLECT_FAILED = "[pack] 收集 --src 失败（遍历错误／符号链接／非常规条目）：%s；不创建 zip"
DETAIL_SYMLINK = "符号链接（目录或文件）：%s"
DETAIL_NONREGULAR = "非普通文件（非常规条目）：%s"
DETAIL_WALK = "遍历错误：%s"
OUT_IN_SRC = "[pack] --out 位于 --src 之内（其自身产物会被下次打包吸入）：%s；不创建 zip"
IO_ERROR = "[pack] 读取或写入失败：%s"
TMP_CLEANUP_ERROR = "[pack] 临时文件清理失败：%s"
EXPECT_MISMATCH = "[pack] sha256 不符：expect=%s actual=%s"
HEX = "0123456789abcdef"


def walk_error(exc):
    """os.walk 的 onerror 回调：遍历出错立即上抛，绝不静默跳过目录树。"""
    raise OSError(DETAIL_WALK % exc)


def collect(root):
    """递归收集 root 下的全部文件，返回按 relpath（/ 分隔）排序的 (rel, 绝对路径) 列表。

    - os.walk 传 onerror=walk_error：遍历错误立即抛出（不再静默跳过整个分支）；
    - 逐项拒绝符号链接（目录或文件）与非常规条目（非普通文件），由 main 以 rc=2 报告；
    - 目录符号链接不跟随（os.walk 默认 followlinks=False），此处直接拒绝。
    """
    entries = []
    for cur, dirs, files in os.walk(root, onerror=walk_error):
        for name in dirs:
            path = os.path.join(cur, name)
            if os.path.islink(path):
                raise OSError(DETAIL_SYMLINK % path)
        for name in files:
            path = os.path.join(cur, name)
            if os.path.islink(path):
                raise OSError(DETAIL_SYMLINK % path)
            if not os.path.isfile(path):
                raise OSError(DETAIL_NONREGULAR % path)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            entries.append((rel, path))
    entries.sort()
    return entries


def build(entries):
    """按确定性布局打包，返回 zip 字节。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel, path in entries:
            with open(path, "rb") as fh:
                data = fh.read()
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return buf.getvalue()


def parse_args(argv):
    """返回 (src, out, expect, bad)；bad 非 None 表示参数无效（原样回报触发字符串）。"""
    src = out = expect = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            print(USAGE)
            sys.exit(0)
        if arg in ("--src", "--out", "--expect"):
            if i + 1 >= len(argv):
                return None, None, None, arg
            value = argv[i + 1]
            if arg == "--src":
                src = value
            elif arg == "--out":
                out = value
            else:
                expect = value
            i += 2
            continue
        return None, None, None, arg
    return src, out, expect, None


def prefix_match(digest, expect):
    """逐位比较：expect 是 8–64 位十六进制前缀。"""
    if len(expect) > len(digest):
        return False
    for i, ch in enumerate(expect):
        if digest[i] != ch:
            return False
    return True


def main(argv):
    src, out, expect, bad = parse_args(argv)
    if bad is not None:
        sys.stderr.write("[pack] 参数无效：%s\n%s\n" % (bad, USAGE))
        return 2
    if not src or not out:
        sys.stderr.write("[pack] 缺少必填参数 --src／--out\n%s\n" % USAGE)
        return 2
    if expect is not None:
        expect = expect.lower()
        if not 8 <= len(expect) <= 64 or any(ch not in HEX for ch in expect):
            sys.stderr.write("[pack] --expect 须为 8–64 位十六进制（可前缀）：%s\n" % expect)
            return 2
    # --src 自身是符号链接即拒绝：不跟随链接判定，否则「源目录」可被无声替换。
    # 同时检查规范化后的源路径：`link/.` 这类写法下 islink(src) 为假、isdir 为真，
    # 只查原始字符串会绕过入口检查（LENS 复审 D9E1F856 发现 1）。
    if os.path.islink(src) or os.path.islink(os.path.abspath(src)):
        sys.stderr.write(SRC_IS_SYMLINK % src + "\n")
        return 2
    if not os.path.isdir(src):
        sys.stderr.write(SRC_UNAVAILABLE % src + "\n")
        return 2
    # --out 位于 --src 之内（含同一路径）：其自身产物会被下次打包吸入，直接拒绝。
    # 用 realpath 比较（源目录与输出父目录各自解析链接），末级 --out 本身**不**解析：
    # 输出路径为符号链接时由 os.replace 替换链接自身，不写穿目标（LENS 复审 D9E1F856 发现 2）。
    src_abs = os.path.realpath(src)
    out_abs = os.path.join(os.path.realpath(os.path.dirname(out) or "."),
                           os.path.basename(out))
    src_prefix = src_abs if src_abs.endswith(os.sep) else src_abs + os.sep
    if out_abs == src_abs or out_abs.startswith(src_prefix):
        sys.stderr.write(OUT_IN_SRC % out + "\n")
        return 2
    try:
        entries = collect(src)
    except OSError as exc:
        # 遍历错误／符号链接／非常规条目：统一固定说明，rc=2，**不产出 zip**。
        sys.stderr.write(COLLECT_FAILED % exc + "\n")
        return 2
    if not entries:
        sys.stderr.write(SRC_UNAVAILABLE % src + "\n")
        return 2
    out_dir = os.path.dirname(out_abs)
    if not os.path.isdir(out_dir):
        sys.stderr.write("[pack] --out 所在目录不存在：%s\n" % out_dir)
        return 2
    # 原子写出：先写 --out 同目录内的临时文件，成功后再 os.replace 到 --out。
    # 失败时不替换原有输出，并尝试删除临时文件；删除失败则报告待清理路径（可能残留）。
    err = None
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=out_dir, prefix=".pack-", delete=False) as tmp_fh:
            tmp_name = tmp_fh.name
            blob = build(entries)
            tmp_fh.write(blob)
        os.replace(tmp_name, out)
        tmp_name = None
    except OSError as exc:
        err = IO_ERROR % exc
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError as exc:
                pending = TMP_CLEANUP_ERROR % ("%s；待清理路径：%s" % (exc, tmp_name))
                sys.stderr.write(pending + "\n")
                if err is None:
                    err = pending
    if err is not None:
        sys.stderr.write(err + "\n")
        return 2
    digest = hashlib.sha256(blob).hexdigest()
    print("files=%d bytes=%d sha256=%s" % (len(entries), len(blob), digest))
    if expect is not None and not prefix_match(digest, expect):
        sys.stderr.write(EXPECT_MISMATCH % (expect, digest) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

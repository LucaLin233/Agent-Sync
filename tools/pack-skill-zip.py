#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用技能打包器（库）：deploy_skill.py 经 `collect(root)`／`build(entries)` 在内存构建候选 ZIP。

确定性布局：relpath 用 `/` 并排序、只收文件（无目录条目）、date_time=1980-01-01、ZIP_DEFLATED、
权限位统一 0o644<<16。不继承源文件模式：平台侧既有包按统一 0644 布局得出 zipFileHash，继承模式会让
同一源得到不同哈希。只打包请用 `deploy_skill.py`（不带 `--deploy`）。
"""
import io
import os
import sys
import zipfile


def _walk_error(exc):
    raise OSError("遍历错误：%s" % exc)


def collect(root):
    """root 下全部文件的 [(relpath, 路径)]（按 relpath 排序）；符号链接、非常规条目、遍历错误抛 OSError。"""
    entries = []
    for cur, dirs, files in os.walk(root, onerror=_walk_error):
        for name in dirs + files:
            if os.path.islink(os.path.join(cur, name)):
                raise OSError("符号链接（目录或文件）：%s" % os.path.join(cur, name))
        for name in files:
            path = os.path.join(cur, name)
            if not os.path.isfile(path):
                raise OSError("非普通文件（非常规条目）：%s" % path)
            entries.append((os.path.relpath(path, root).replace(os.sep, "/"), path))
    entries.sort()
    return entries


def build(entries):
    """按确定性布局打包，返回 ZIP bytes。"""
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


if __name__ == "__main__":
    sys.exit("pack-skill-zip.py 只供 deploy_skill.py 加载；只打包请运行 "
             "deploy_skill.py（不带 --deploy）")

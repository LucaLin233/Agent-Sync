#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version

本文件是技能 frontmatter 静态校验的**唯一实现**，两个入口共用、不复制判据：
  * 技能包内独立使用（可脱离仓库）：`python3 quick_validate.py <skill_directory>`；
  * 仓库侧：按本次变化技能直接调用本模块，不再提供全仓批扫包装器。

统一判据（顺序即报告顺序，见 `check_skill`）：
  1. 存在 `SKILL.md`；
  2. 文件以 `---` 开头，frontmatter 由 `---\\n…\\n---\\n` 包裹，其后是正文；
  3. frontmatter 是合法 YAML 映射（字典）；
  4. 顶层键只允许 name / description / license / allowed-tools / metadata / compatibility；
  5. name：字符串、非空白、`[a-z0-9-]`、不以连字符开头或结尾、无连续连字符、≤64 字符；
  6. name 与所在目录名一致；
  7. description：字符串、非空白、不含 `<`／`>`、≤1024 字符；
  8. 正文非空（`strip()` 后）。

只做静态检查，通过不等于可用。运行须 Python 3 与 PyYAML；依赖缺失即停并交执行方，不自动安装。
"""

import os
import re
import sys
from pathlib import Path

import yaml

MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
ALLOWED_PROPERTIES = ("allowed-tools", "compatibility", "description", "license", "metadata", "name")
ALLOWED_PROPERTIES_SET = frozenset(ALLOWED_PROPERTIES)
NAME_RE = re.compile(r"^[a-z0-9-]+$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


class Problem:
    """一条失败的判据。

    `code` 是判据标识（供用例与登记映射）；`text` 是本入口的英文短句；`zh` 是仓库门禁
    入口的中文短句。两者由**同一次判定**生成，两个入口只在输出时各取一份。
    """

    __slots__ = ("code", "text", "zh")

    def __init__(self, code, text, zh):
        self.code = code
        self.text = text
        self.zh = zh

    def __repr__(self):
        return "Problem(%r, %r, %r)" % (self.code, self.text, self.zh)


def dir_name_of(skill_path):
    """技能目录名（与 name 比较用）。normpath 使 `x/`、`x//` 与旧门禁口径一致。"""
    return os.path.basename(os.path.normpath(str(skill_path)))


def check_skill(skill_path):
    """校验一个技能目录。

    返回 `(problems, body)`：`problems` 是 `Problem` 列表，空列表即通过；`body` 是
    frontmatter 之后的正文原文（结构性失败导致无法解析时为 None）。
    """
    skill_dir = Path(skill_path)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [Problem("skill_md_missing", "SKILL.md not found", "缺少 SKILL.md")], None

    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return [Problem("frontmatter_unwrapped", "No YAML frontmatter found",
                        "frontmatter 缺失或格式不合法（需以 --- 包裹）")], None
    match = FRONTMATTER_RE.match(content)
    if not match:
        return [Problem("frontmatter_invalid", "Invalid frontmatter format",
                        "frontmatter 缺失或格式不合法（需以 --- 包裹）")], None
    frontmatter_text, body = match.group(1), match.group(2)

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        return [Problem("frontmatter_yaml_error", "Invalid YAML in frontmatter: %s" % exc,
                        "frontmatter 不是合法 YAML：%s" % exc)], None
    if not isinstance(frontmatter, dict):
        return [Problem("frontmatter_not_mapping", "Frontmatter must be a YAML dictionary",
                        "frontmatter 必须是 YAML 字典")], None

    problems = []

    unexpected = sorted(str(key) for key in set(frontmatter) - ALLOWED_PROPERTIES_SET)
    if unexpected:
        problems.append(Problem(
            "unexpected_keys",
            "Unexpected key(s) in SKILL.md frontmatter: %s. Allowed properties are: %s"
            % (", ".join(unexpected), ", ".join(ALLOWED_PROPERTIES)),
            "frontmatter 含未知键：%s（允许：%s）"
            % (", ".join(unexpected), ", ".join(ALLOWED_PROPERTIES))))

    # Agent Skills specification（2026-10-15 核对）：compatibility 可选，1–500字符。
    if "compatibility" in frontmatter:
        value = frontmatter["compatibility"]
        if not isinstance(value, str) or not 1 <= len(value) <= 500:
            problems.append(Problem("compatibility_invalid", "Compatibility must be 1-500 characters",
                                    "compatibility 须为 1–500 字符的字符串"))

    name = frontmatter.get("name")
    if "name" not in frontmatter:
        problems.append(Problem("name_missing", "Missing 'name' in frontmatter", "缺少 name"))
    elif name is None or (isinstance(name, str) and not name.strip()):
        problems.append(Problem("name_empty", "'name' must not be empty or whitespace-only",
                                "缺少 name"))
    elif not isinstance(name, str):
        kind = type(name).__name__
        problems.append(Problem("name_not_string", "Name must be a string, got %s" % kind,
                                "name 类型不是字符串：%s" % kind))
    else:
        if not NAME_RE.fullmatch(name):
            problems.append(Problem(
                "name_bad_characters",
                "Name '%s' should be hyphen-case (lowercase letters, digits, and hyphens only)" % name,
                "name 含非法字符：%s（只允许 a-z0-9-）" % name))
        if name.startswith("-") or name.endswith("-") or "--" in name:
            problems.append(Problem(
                "name_bad_hyphens",
                "Name '%s' cannot start/end with hyphen or contain consecutive hyphens" % name,
                "name 不得以连字符开头/结尾或含连续连字符：%s" % name))
        if len(name) > MAX_SKILL_NAME_LENGTH:
            problems.append(Problem(
                "name_too_long",
                "Name is too long (%d characters). Maximum is %d characters."
                % (len(name), MAX_SKILL_NAME_LENGTH),
                "name 超长：%d > %d" % (len(name), MAX_SKILL_NAME_LENGTH)))
        directory = dir_name_of(skill_path)
        if name != directory:
            problems.append(Problem(
                "name_dir_mismatch",
                "Skill directory '%s' does not match frontmatter name '%s'" % (directory, name),
                "name 与目录名不一致：name=%s dir=%s" % (name, directory)))

    description = frontmatter.get("description")
    if "description" not in frontmatter:
        problems.append(Problem("description_missing", "Missing 'description' in frontmatter",
                                "缺少 description"))
    elif description is None or (isinstance(description, str) and not description.strip()):
        # `description:` 空值（YAML null）、空串与纯空白同归「缺失」，与旧门禁短句一致。
        problems.append(Problem("description_empty", "'description' must not be empty or whitespace-only",
                                "缺少 description"))
    elif not isinstance(description, str):
        kind = type(description).__name__
        problems.append(Problem("description_not_string", "Description must be a string, got %s" % kind,
                                "description 类型不是字符串：%s" % kind))
    else:
        if "<" in description or ">" in description:
            problems.append(Problem("description_angle_brackets",
                                    "Description cannot contain angle brackets (< or >)",
                                    "description 含尖括号（< 或 >）"))
        if len(description) > MAX_DESCRIPTION_LENGTH:
            problems.append(Problem(
                "description_too_long",
                "Description is too long (%d characters). Maximum is %d characters."
                % (len(description), MAX_DESCRIPTION_LENGTH),
                "description 超长：%d > %d" % (len(description), MAX_DESCRIPTION_LENGTH)))

    if not body.strip():
        problems.append(Problem("empty_body", "Body must not be empty", "正文为空"))

    return problems, body


def validate_skill(skill_path):
    """Basic validation of a skill → `(valid, message)`；message 取首条失败判据的英文短句。"""
    problems, _body = check_skill(skill_path)
    if problems:
        return False, problems[0].text
    return True, "Skill is valid!"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)

#!/usr/bin/env python3
"""技能 frontmatter 静态校验（唯一实现）：python3 quick_validate.py <skill_directory>

检查：SKILL.md 存在；frontmatter 以 `---\\n…\\n---\\n` 包裹且为 YAML 映射；顶层键只允许
name / description / license / allowed-tools / metadata / compatibility；name 为 hyphen-case、
≤64 字符且等于目录名；description 为不含尖括号、≤1024 字符的非空字符串；compatibility 为
1–500 字符的字符串；正文非空。只做静态检查，通过不等于可用。需要 PyYAML，缺失即停，不自动安装。
源自 openai/skills skill-creator 的 quick_validate.py（Apache-2.0），已在本地修改。
"""
import os
import re
import sys
from pathlib import Path

import yaml

MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
ALLOWED_PROPERTIES = ("allowed-tools", "compatibility", "description", "license", "metadata", "name")
NAME_RE = re.compile(r"^[a-z0-9-]+$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def problems(skill_path):
    """按检查顺序返回失败判据（英文短句）；空列表即通过。"""
    skill_md = Path(skill_path) / "SKILL.md"
    if not skill_md.is_file():
        return ["SKILL.md not found"]
    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return ["No YAML frontmatter found"]
    match = FRONTMATTER_RE.match(content)
    if not match:
        return ["Invalid frontmatter format"]
    try:
        fm = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return ["Invalid YAML in frontmatter: %s" % exc]
    if not isinstance(fm, dict):
        return ["Frontmatter must be a YAML dictionary"]

    out = []
    unexpected = sorted(str(key) for key in set(fm) - set(ALLOWED_PROPERTIES))
    if unexpected:
        out.append("Unexpected key(s) in SKILL.md frontmatter: %s. Allowed properties are: %s"
                   % (", ".join(unexpected), ", ".join(ALLOWED_PROPERTIES)))
    if "compatibility" in fm:
        value = fm["compatibility"]
        if not isinstance(value, str) or not 1 <= len(value) <= 500:
            out.append("Compatibility must be 1-500 characters")

    name = fm.get("name")
    if "name" not in fm:
        out.append("Missing 'name' in frontmatter")
    elif name is None or (isinstance(name, str) and not name.strip()):
        out.append("'name' must not be empty or whitespace-only")
    elif not isinstance(name, str):
        out.append("Name must be a string, got %s" % type(name).__name__)
    else:
        if not NAME_RE.fullmatch(name):
            out.append("Name '%s' should be hyphen-case (lowercase letters, digits, and hyphens only)"
                       % name)
        if name.startswith("-") or name.endswith("-") or "--" in name:
            out.append("Name '%s' cannot start/end with hyphen or contain consecutive hyphens" % name)
        if len(name) > MAX_SKILL_NAME_LENGTH:
            out.append("Name is too long (%d characters). Maximum is %d characters."
                       % (len(name), MAX_SKILL_NAME_LENGTH))
        directory = os.path.basename(os.path.normpath(str(skill_path)))
        if name != directory:
            out.append("Skill directory '%s' does not match frontmatter name '%s'" % (directory, name))

    description = fm.get("description")
    if "description" not in fm:
        out.append("Missing 'description' in frontmatter")
    elif description is None or (isinstance(description, str) and not description.strip()):
        out.append("'description' must not be empty or whitespace-only")
    elif not isinstance(description, str):
        out.append("Description must be a string, got %s" % type(description).__name__)
    else:
        if "<" in description or ">" in description:
            out.append("Description cannot contain angle brackets (< or >)")
        if len(description) > MAX_DESCRIPTION_LENGTH:
            out.append("Description is too long (%d characters). Maximum is %d characters."
                       % (len(description), MAX_DESCRIPTION_LENGTH))

    if not match.group(2).strip():
        out.append("Body must not be empty")
    return out


def validate_skill(skill_path):
    """→ (valid, message)；message 为首条失败判据。"""
    found = problems(skill_path)
    return (False, found[0]) if found else (True, "Skill is valid!")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)
    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)

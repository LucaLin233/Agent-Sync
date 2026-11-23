/** Pure title rules shared by the daemon plugin and its tests. */

const HAN = /[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]/u;
const CONTROL = /[\u0000-\u001F\u007F\uFFFD]/u;

export function hasHan(value: string): boolean {
  return HAN.test(value);
}

/** Paseo's own first-prompt title: first non-empty line, whitespace collapsed, at most 60 chars. */
export function provisionalTitle(prompt: string): string | null {
  const line = prompt
    .split(/\r?\n/)
    .map((part) => part.trim())
    .find((part) => part.length > 0);
  return line?.replace(/\s+/g, " ").trim().slice(0, 60).trim() || null;
}

/** True only when the visible name is still Paseo's provisional prompt text. */
export function isProvisional(title: string | null | undefined, prompt: string): boolean {
  const current = title?.trim() ?? "";
  if (!current) return true;
  return current === provisionalTitle(prompt);
}

export function truncateChars(value: string, maxChars: number): string {
  const chars = Array.from(value);
  return chars.length <= maxChars ? value : chars.slice(0, maxChars).join("").trim();
}

/** The last line of defence: a truncated ASCII title still ends up with Han text. */
export function ensureHan(value: string, maxChars: number): string {
  const trimmed = truncateChars(value.trim(), maxChars);
  if (trimmed && hasHan(trimmed)) return trimmed;
  const prefix = "处理 ";
  if (maxChars <= prefix.length) return truncateChars("任务", maxChars);
  return truncateChars(`${prefix}${truncateChars(trimmed, maxChars - prefix.length)}`, maxChars);
}

function takeJsonTitle(raw: string): string | null {
  if (!raw.startsWith("{") || !raw.endsWith("}")) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const record = parsed as Record<string, unknown>;
    for (const key of ["title", "name", "名称", "标题"]) {
      const value = record[key];
      if (typeof value === "string" && value.trim()) return value;
    }
  } catch {
    return null;
  }
  return null;
}

/**
 * Removes wrappers a model commonly adds: JSON, fences, quotes, labels, lists,
 * and trailing explanations. The first line wins; the caller validates Han.
 */
export function cleanModelTitle(raw: string): string {
  let value = raw.replace(/\r\n?/g, "\n").trim();
  const json = takeJsonTitle(value);
  if (json) value = json;
  value = value.replace(/^```[a-zA-Z0-9_-]*\s*/u, "").replace(/\s*```$/u, "");
  const firstLine = value.split("\n").map((line) => line.trim()).find(Boolean) ?? "";
  value = firstLine
    .replace(/^(?:标题|名称|title|name)\s*[:：]\s*/iu, "")
    .replace(/^(?:[-*+]|\d+[.)])\s+/u, "")
    .replace(/^[`"'“”‘’「」『』]+|[`"'“”‘’「」『』]+$/gu, "")
    .replace(/\s+/g, " ")
    .trim();
  return value;
}

export function sanitizeModelTitle(raw: string | null | undefined, maxChars: number): string | null {
  if (typeof raw !== "string") return null;
  const value = cleanModelTitle(raw);
  if (!value || CONTROL.test(value) || !hasHan(value)) return null;
  const truncated = truncateChars(value, maxChars);
  return truncated && hasHan(truncated) ? truncated : null;
}

const VERB_MAP: ReadonlyArray<readonly [RegExp, string]> = [
  [/^(?:fix|repair|bugfix)\b/iu, "修复"],
  [/^(?:add|create|introduce)\b/iu, "新增"],
  [/^(?:implement|build|develop)\b/iu, "实现"],
  [/^(?:update|change|modify|edit|adjust)\b/iu, "更新"],
  [/^(?:remove|delete|drop)\b/iu, "删除"],
  [/^(?:refactor|restructure|clean\s*up)\b/iu, "重构"],
  [/^(?:test|verify|validate)\b/iu, "测试"],
  [/^(?:document|docs?)\b/iu, "文档"],
  [/^(?:review|audit|inspect)\b/iu, "审查"],
  [/^(?:deploy|release|publish)\b/iu, "发布"],
  [/^(?:investigate|debug|diagnose|triage)\b/iu, "排查"],
  [/^(?:migrate|upgrade)\b/iu, "迁移"],
  [/^(?:optimize|improve|speed\s*up)\b/iu, "优化"],
  [/^(?:merge|rebase)\b/iu, "合并"],
  [/^(?:rename|move)\b/iu, "重命名"],
  [/^(?:generate|write)\b/iu, "生成"],
  [/^(?:read|explain|summari[sz]e)\b/iu, "整理"],
];

function readableTaskLine(prompt: string): string {
  const line = prompt
    .split(/\r?\n/)
    .map((part) => part.trim())
    .find((part) => part.length > 0) ?? "";
  return line
    .replace(/^```[a-zA-Z0-9_-]*\s*/u, "")
    .replace(/^(?:please|pls|can you|could you|would you)\s+/iu, "")
    .replace(/^(?:[-*+]|\d+[.)])\s+/u, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * A deterministic Chinese fallback. It keeps product, module and issue names
 * when they are ASCII, but always adds Simplified-Chinese wording.
 */
export function fallbackTaskTitle(input: {
  prompt: string;
  baseName?: string | null;
  maxChars: number;
}): string {
  const line = readableTaskLine(input.prompt);
  if (line && hasHan(line)) return ensureHan(line, input.maxChars);

  const baseName = input.baseName?.trim() || "";
  if (line) {
    for (const [pattern, verb] of VERB_MAP) {
      if (!pattern.test(line)) continue;
      const target = line.replace(pattern, "").replace(/^[\s:：,，-]+/u, "").replace(/[.!?。！？]+$/u, "").trim();
      if (target) return ensureHan(`${verb} ${target}`, input.maxChars);
      break;
    }
    const words = line.replace(/[.!?。！？]+$/u, "").split(/\s+/).slice(0, 8).join(" ");
    if (words) return ensureHan(`处理 ${words}`, input.maxChars);
  }
  if (baseName) return ensureHan(hasHan(baseName) ? baseName : `处理 ${baseName}`, input.maxChars);
  return ensureHan("处理新任务", input.maxChars);
}

export function fallbackProjectTitle(displayName: string | null | undefined, maxChars: number): string {
  const name = displayName?.trim() || "";
  if (!name) return truncateChars("新项目", maxChars);
  if (hasHan(name)) return ensureHan(name, maxChars);
  return ensureHan(`项目 ${name}`, maxChars);
}

/** The one value used for both a workspace and its first session. */
export function titleForPair(raw: string | null | undefined, fallback: string, maxChars: number): string {
  return sanitizeModelTitle(raw, maxChars) ?? ensureHan(fallback, maxChars);
}

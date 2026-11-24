/** Pure title rules shared by the daemon plugin and its tests. */

const HAN = /[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]/u;
const CONTROL = /[\u0000-\u001F\u007F\uFFFD]/u;
const LATIN_WORD = /[A-Za-z][A-Za-z0-9_.\-/@#]*/g;

/**
 * Product and protocol names that may stay in Latin script. Generic English
 * words are intentionally absent: a title such as "修复 login bug" is not a
 * natural Chinese title and must fall back to the deterministic wording.
 */
const PRODUCT_WORDS = new Set([
  "api",
  "cchp",
  "cdn",
  "ci",
  "cli",
  "codex",
  "cors",
  "csrf",
  "css",
  "docker",
  "dom",
  "gcp",
  "gdr",
  "git",
  "github",
  "gitlab",
  "gpt",
  "graphql",
  "grpc",
  "html",
  "http",
  "https",
  "ios",
  "javascript",
  "json",
  "jwt",
  "k8s",
  "kubernetes",
  "linux",
  "llm",
  "lsp",
  "macos",
  "mcp",
  "node",
  "npm",
  "oauth",
  "openai",
  "paseo",
  "pnpm",
  "postgres",
  "pr",
  "python",
  "react",
  "redis",
  "rest",
  "rpc",
  "rust",
  "sdk",
  "sso",
  "sql",
  "sqlite",
  "ssh",
  "tls",
  "toml",
  "typescript",
  "ui",
  "url",
  "ux",
  "vitest",
  "vite",
  "web",
  "webpack",
  "windows",
  "yaml",
  "yarn",
  "zod",
]);

/** Common task nouns translated to Chinese so fallback titles read naturally. */
const TERM_WORDS = new Map<string, string>([
  ["account", "账户"],
  ["agent", "代理"],
  ["approval", "审批"],
  ["auth", "认证"],
  ["authentication", "认证"],
  ["authorization", "授权"],
  ["branch", "分支"],
  ["bug", "问题"],
  ["button", "按钮"],
  ["cache", "缓存"],
  ["callback", "回调"],
  ["change", "变更"],
  ["chat", "对话"],
  ["client", "客户端"],
  ["commit", "提交"],
  ["config", "配置"],
  ["configuration", "配置"],
  ["database", "数据库"],
  ["db", "数据库"],
  ["deploy", "部署"],
  ["deployment", "部署"],
  ["directory", "目录"],
  ["doc", "文档"],
  ["docs", "文档"],
  ["documentation", "文档"],
  ["download", "下载"],
  ["error", "错误"],
  ["export", "导出"],
  ["feature", "功能"],
  ["file", "文件"],
  ["filename", "文件名"],
  ["filter", "筛选"],
  ["folder", "目录"],
  ["generation", "生成"],
  ["image", "图片"],
  ["import", "导入"],
  ["index", "索引"],
  ["latency", "延迟"],
  ["log", "日志"],
  ["login", "登录"],
  ["loop", "循环"],
  ["manual", "手动"],
  ["merge", "合并"],
  ["message", "消息"],
  ["metadata", "元数据"],
  ["metric", "指标"],
  ["migration", "迁移"],
  ["model", "模型"],
  ["notification", "通知"],
  ["page", "页面"],
  ["panel", "面板"],
  ["path", "路径"],
  ["performance", "性能"],
  ["permission", "权限"],
  ["plugin", "插件"],
  ["price", "价格"],
  ["profile", "资料"],
  ["project", "项目"],
  ["prompt", "提示词"],
  ["provider", "提供方"],
  ["query", "查询"],
  ["queue", "队列"],
  ["quota", "配额"],
  ["race", "竞态"],
  ["rebase", "变基"],
  ["redirect", "跳转"],
  ["refactor", "重构"],
  ["release", "发布"],
  ["rename", "重命名"],
  ["repo", "仓库"],
  ["repository", "仓库"],
  ["review", "审查"],
  ["role", "角色"],
  ["sandbox", "沙箱"],
  ["schema", "模式"],
  ["search", "搜索"],
  ["server", "服务器"],
  ["session", "会话"],
  ["setting", "设置"],
  ["sort", "排序"],
  ["speed", "性能"],
  ["state", "状态"],
  ["storage", "存储"],
  ["stream", "流"],
  ["subscription", "订阅"],
  ["table", "表"],
  ["test", "测试"],
  ["theme", "主题"],
  ["thinking", "思考"],
  ["title", "标题"],
  ["token", "令牌"],
  ["upgrade", "升级"],
  ["upload", "上传"],
  ["usage", "用量"],
  ["user", "用户"],
  ["video", "视频"],
  ["worker", "工作进程"],
  ["workspace", "工作区"],
]);

function countHanChars(value: string): number {
  let count = 0;
  for (const char of value) if (HAN.test(char)) count += 1;
  return count;
}

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
  if (maxChars <= 2) return truncateChars("任务", maxChars);
  const prefix = trimmed && /[A-Za-z0-9]/.test(trimmed[0] ?? "") ? "处理 " : "处理";
  return truncateChars(`${prefix}${trimmed || "任务"}`, maxChars);
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

const TRAILING_PUNCTUATION = /[.,;:!?，。；：！？、]+$/u;

/** True only for a Latin word that identifies a product, protocol or code identifier. */
export function isAllowedLatinToken(token: string): boolean {
  const value = token.trim().replace(TRAILING_PUNCTUATION, "");
  if (!value) return false;
  if (PRODUCT_WORDS.has(value.toLowerCase())) return true;
  // Mixed-case names such as GitHub, macOS and OAuth. A merely capitalised
  // ordinary word (Login, BUG) and an all-caps ordinary word are not enough.
  if (/[a-z]/u.test(value) && /[A-Z]/u.test(value.slice(1))) return true;
  // Identifiers, versions and file names. A trailing full stop is not a
  // technical marker; it was stripped above.
  if (/[0-9_/@#]/u.test(value)) return true;
  if (/\.[A-Za-z0-9]{1,10}$/u.test(value)) return true;
  return false;
}

/**
 * Manual conversation summaries go straight into a workspace title. The model
 * is asked for Simplified Chinese, so this gate checks only that the answer is
 * usable Chinese text: at least two Han characters and no control characters.
 * Latin words are not audited one by one, because a summary may legitimately
 * name a product the automatic word list does not know. If the answer is too
 * long, cut at a word or Han boundary instead of slicing a term in half; a
 * candidate cut that no longer passes the Chinese check is skipped.
 */
function isManualTitle(value: string): boolean {
  const text = value.trim();
  return Boolean(text) && !CONTROL.test(text) && countHanChars(text) >= 2;
}

/**
 * Used by the formal manual-summary entry. A model may answer with a title that
 * is over the limit, or with a fragment that was cut mid-phrase and lost its
 * main object. Those are not silently truncated into the sidebar: the caller
 * gets a `rewrite` verdict and may ask the same helper session for one semantic
 * shortening. Anything without usable Chinese is rejected outright.
 *
 * Only shapes with direct evidence of a cut are treated as incomplete. Ending a
 * Chinese title on 地/得/和/与 is normal (本地, 应纳税所得, 趋于饱和), so those are
 * not signals on their own. What is left is either a structural 的 at the very
 * end — with the closed set of lexicalised 的-words excluded (目的, 标的) — or a
 * particle standing after a Latin/identifier token and a space, which cannot be
 * part of a Chinese word.
 */
const LEXICAL_DE_TAIL = /(?:目的|标的|端的|似的|是的|有的|别的|什么的)$/u;
const LATIN_PARTICLE_TAIL = /[A-Za-z0-9_.\-/@#)\]]\s+[的地得和与及或而但并]$/u;

function hasCutEvidence(value: string): boolean {
  if (LATIN_PARTICLE_TAIL.test(value)) return true;
  return value.endsWith("的") && !LEXICAL_DE_TAIL.test(value);
}

export type ConversationSummaryCheck =
  | { kind: "ok"; title: string }
  | { kind: "rewrite"; reason: "too_long" | "incomplete" }
  | { kind: "invalid" };

export function checkConversationSummaryTitle(
  raw: string | null | undefined,
  maxChars: number,
): ConversationSummaryCheck {
  if (typeof raw !== "string") return { kind: "invalid" };
  const value = cleanModelTitle(raw);
  if (!value || CONTROL.test(value) || !isManualTitle(value)) return { kind: "invalid" };
  if (Array.from(value).length > maxChars) return { kind: "rewrite", reason: "too_long" };
  if (hasCutEvidence(value)) return { kind: "rewrite", reason: "incomplete" };
  return { kind: "ok", title: value };
}

export function sanitizeConversationTitle(raw: string | null | undefined, maxChars: number): string | null {
  if (typeof raw !== "string") return null;
  const value = cleanModelTitle(raw);
  if (!value || CONTROL.test(value)) return null;
  const chars = Array.from(value);
  if (chars.length <= maxChars) return isManualTitle(value) ? value : null;
  for (let end = maxChars; end >= 2; end -= 1) {
    const next = chars[end] ?? "";
    const previous = chars[end - 1] ?? "";
    const cutsWord = /[A-Za-z0-9_.\-/@#]/u.test(next) && /[A-Za-z0-9_.\-/@#]/u.test(previous);
    if (cutsWord) continue;
    const candidate = chars.slice(0, end).join("").trim().replace(/[\s,;:，。；：、\-/·]+$/u, "");
    // The automatic path keeps the long-standing rule: cut at the nearest word
    // or Han boundary. The stricter judgement lives only in the manual entry.
    if (candidate && isManualTitle(candidate)) return candidate;
  }
  return null;
}

/**
 * Automatic model output must read as Chinese: at least two Han characters,
 * and every Latin word must be a product name, acronym or identifier. This
 * stricter word-by-word gate stays on the automatic naming path only.
 */
export function isAcceptableTitle(value: string): boolean {
  const text = value.trim();
  if (!text || CONTROL.test(text)) return false;
  if (countHanChars(text) < 2) return false;
  const words = text.match(LATIN_WORD) ?? [];
  return words.every((word) => isAllowedLatinToken(word));
}

export function sanitizeModelTitle(raw: string | null | undefined, maxChars: number): string | null {
  if (typeof raw !== "string") return null;
  const value = cleanModelTitle(raw);
  if (!value || CONTROL.test(value)) return null;
  const truncated = truncateChars(value, maxChars);
  return isAcceptableTitle(truncated) ? truncated : null;
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
  [/^(?:extend|expand)\b/iu, "扩展"],
  [/^(?:handle|support)\b/iu, "处理"],
  [/^(?:enable)\b/iu, "启用"],
  [/^(?:disable)\b/iu, "停用"],
];

const GENERIC_BY_VERB: Readonly<Record<string, string>> = {
  修复: "修复问题",
  新增: "新增功能",
  实现: "实现功能",
  更新: "更新内容",
  删除: "删除内容",
  重构: "重构代码",
  测试: "测试变更",
  文档: "更新文档",
  审查: "审查变更",
  发布: "发布版本",
  排查: "排查问题",
  迁移: "迁移升级",
  优化: "优化性能",
  合并: "合并变更",
  重命名: "重命名对象",
  生成: "生成内容",
  整理: "整理内容",
  扩展: "扩展功能",
  处理: "处理任务",
  启用: "启用功能",
  停用: "停用功能",
};

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

function lookupTerm(word: string): string | undefined {
  const lower = word.toLowerCase();
  const direct = TERM_WORDS.get(lower);
  if (direct) return direct;
  if (lower.endsWith("ies")) return TERM_WORDS.get(`${lower.slice(0, -3)}y`);
  if (lower.endsWith("es")) return TERM_WORDS.get(lower.slice(0, -2));
  if (lower.endsWith("s")) return TERM_WORDS.get(lower.slice(0, -1));
  return undefined;
}

/** Keeps mapped Chinese terms and technical identifiers, in source order. */
function technicalParts(target: string): string[] {
  const parts: string[] = [];
  const seen = new Set<string>();
  for (const match of target.matchAll(LATIN_WORD)) {
    const token = match[0].replace(TRAILING_PUNCTUATION, "");
    if (!token) continue;
    const term = lookupTerm(token);
    const part = term ?? (isAllowedLatinToken(token) ? token : null);
    if (!part) continue;
    const key = part.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    parts.push(part);
    if (parts.length >= 3) break;
  }
  return parts;
}

function joinParts(verb: string, parts: readonly string[]): string {
  let value = verb;
  for (const part of parts) {
    if (value && (/[A-Za-z0-9]$/u.test(value) || /^[A-Za-z0-9]/u.test(part))) value += " ";
    value += part;
  }
  return value;
}

/**
 * A deterministic Chinese fallback. It translates common task nouns and keeps
 * only products, acronyms and identifiers in Latin script; ordinary English is
 * never pasted after a Chinese verb.
 */
const LEADING_VERB = /^(?:修复|新增|实现|更新|删除|重构|测试|文档|审查|发布|排查|迁移|优化|合并|重命名|生成|整理|扩展|处理|启用|停用)/u;

function mixedHanTitle(line: string, maxChars: number): string | null {
  const hasLatin = /[A-Za-z]/u.test(line);
  const parts: string[] = [];
  const seen = new Set<string>();
  const push = (part: string) => {
    const key = part.toLowerCase();
    if (seen.has(key)) return;
    // A mapped term already contained in a Chinese run, such as 问题 after
    // 修复登录问题, must not be appended twice.
    if (hasHan(part) && parts.some((existing) => existing.includes(part))) return;
    seen.add(key);
    parts.push(part);
  };
  const pattern = /[A-Za-z][A-Za-z0-9_.\-/@#]*|[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]+/gu;
  for (const match of line.matchAll(pattern)) {
    const token = match[0];
    if (hasHan(token)) {
      push(token);
      continue;
    }
    const term = lookupTerm(token.replace(TRAILING_PUNCTUATION, ""));
    if (term) push(term);
    else if (isAllowedLatinToken(token)) push(token.replace(TRAILING_PUNCTUATION, ""));
  }
  if (parts.length === 0) return null;
  let value = joinParts("", parts);
  // A mixed line whose only Chinese is a short fragment is not a usable title.
  if (hasLatin && countHanChars(value) < 4 && !LEADING_VERB.test(value)) return null;
  if (countHanChars(value) < 2) value = `处理${value}`;
  return isAcceptableTitle(value) ? ensureHan(value, maxChars) : null;
}

export function fallbackTaskTitle(input: {
  prompt: string;
  baseName?: string | null;
  maxChars: number;
}): string {
  const line = readableTaskLine(input.prompt);
  if (line && hasHan(line)) {
    const mixed = mixedHanTitle(line, input.maxChars);
    if (mixed) return mixed;
    const parts = technicalParts(line);
    return ensureHan(parts.length ? joinParts("处理", parts) : "处理任务", input.maxChars);
  }

  if (line) {
    for (const [pattern, verb] of VERB_MAP) {
      if (!pattern.test(line)) continue;
      const target = line
        .replace(pattern, "")
        .replace(/^[\s:：,，-]+/u, "")
        .replace(/[.!?。！？]+$/u, "")
        .trim();
      const parts = technicalParts(target);
      const composed = parts.length ? joinParts(verb, parts) : (GENERIC_BY_VERB[verb] ?? "处理任务");
      return ensureHan(composed, input.maxChars);
    }
    const parts = technicalParts(line);
    if (parts.length) return ensureHan(joinParts("处理", parts), input.maxChars);
    return ensureHan("处理任务", input.maxChars);
  }

  const baseName = input.baseName?.trim() || "";
  if (baseName) {
    if (hasHan(baseName)) return ensureHan(baseName, input.maxChars);
    if (isAllowedLatinToken(baseName)) return ensureHan(`处理 ${baseName}`, input.maxChars);
  }
  return ensureHan("处理工作区", input.maxChars);
}

export function fallbackProjectTitle(displayName: string | null | undefined, maxChars: number): string {
  const name = displayName?.trim() || "";
  if (!name) return truncateChars("新项目", maxChars);
  if (hasHan(name)) return ensureHan(name, maxChars);
  // A project display name is often the directory or repository name. Keep a
  // single identifier-like token (including hyphens) instead of replacing a
  // useful name with a generic one.
  if (/^[A-Za-z0-9][A-Za-z0-9_.\-/@#]*$/u.test(name) && name.length <= 24) {
    return ensureHan(`项目 ${name}`, maxChars);
  }
  return truncateChars("新项目", maxChars);
}

/** The one value used for both a workspace and its first session. */
export function titleForPair(raw: string | null | undefined, fallback: string, maxChars: number): string {
  return sanitizeModelTitle(raw, maxChars) ?? ensureHan(fallback, maxChars);
}

/**
 * Paseo v0.17.3's native workspace auto-name only writes when the current title
 * is empty or exactly the first-prompt title. Keep our title different so the
 * native async summary cannot overwrite it later.
 */
export function distinctWorkspaceTitle(title: string, prompt: string, maxChars: number): string {
  const value = truncateChars(title.trim(), maxChars);
  const promptTitle = provisionalTitle(prompt);
  if (!promptTitle || value !== promptTitle) return ensureHan(value, maxChars);
  return ensureHan(truncateChars(`工作区 · ${value}`, maxChars), maxChars);
}

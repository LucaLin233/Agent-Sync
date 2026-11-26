#!/usr/bin/env node
// Codex model catalog bridge.
//
// One loopback listener serves a small, fixed set of catalog routes. Every route
// has its own fixed upstream and its own metadata/tier configuration, so two
// gateways never share discovered models or capability claims.
//
// Security properties, deliberate — do not relax:
//   * binds a loopback address only; any other bind address is refused at startup;
//   * serves GET on an exact configured path only; other methods and paths are
//     rejected before any outbound request is made;
//   * requires a caller Bearer and forwards it only to that route's configured
//     upstreams. The token is never logged, stored or echoed back;
//   * never uses a caller-supplied destination, query value or header. Only the
//     configured upstream URL is fetched, always with `redirect: 'error'`;
//   * every hop is time-limited and every body is size-limited.
//
// Usage: node catalog-server.mjs [--config /path/to/catalog.json]
//        CATALOG_CONFIG=/path/to/catalog.json node catalog-server.mjs
import http from 'node:http';
import { readFileSync } from 'node:fs';

const GENERIC_INSTRUCTIONS =
  'You are a coding agent. Work directly in the shared workspace with the user, follow the client tool instructions and repository conventions.';

// Codex rejects a catalog whose ids are not printable ASCII without spaces.
const ID_RE = /^[\x21-\x7E]{1,200}$/;
const LOOPBACK_HOSTS = new Set(['127.0.0.1', '::1']);

const DEFAULTS = {
  listen: { host: '127.0.0.1', port: 18923 },
  limits: {
    upstreamTimeoutMs: 4000,
    metadataTimeoutMs: 1200,
    supplementTimeoutMs: 2500,
    totalBudgetMs: 4500,
    maxBodyBytes: 524288,
    maxMetadataBytes: 131072,
    maxModels: 200,
  },
};

function fatal(message) {
  console.error(JSON.stringify({ event: 'config_invalid', error: message }));
  process.exit(2);
}

function isPositiveInt(value) {
  return Number.isInteger(value) && value > 0;
}

// https everywhere; plain http only towards a loopback literal, which keeps the
// offline tests hermetic without opening a production seam. Any fixed query has
// to live in this single validated URL, so nothing is assembled by hand later.
// Embedded credentials are refused: the caller Bearer is the only auth source.
function checkUpstream(url, label) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    fatal(`${label}: not a valid URL`);
  }
  if (parsed.username !== '' || parsed.password !== '') {
    fatal(`${label}: userinfo in the URL is not allowed`);
  }
  // A fragment is never sent upstream; accepting one would only hide a typo in
  // the fixed path or query.
  if (parsed.hash !== '') fatal(`${label}: fragments are not allowed`);
  if (parsed.protocol === 'https:') return parsed.toString();
  if (parsed.protocol === 'http:' && LOOPBACK_HOSTS.has(parsed.hostname)) return parsed.toString();
  fatal(`${label}: only https, or http towards loopback, is allowed`);
}

// Unknown keys are refused rather than ignored: a typo such as `query` or
// `url` next to a fixed URL would otherwise look accepted while doing nothing.
function checkKeys(object, allowed, label) {
  for (const key of Object.keys(object)) {
    if (!allowed.includes(key)) fatal(`${label}.${key}: unknown field`);
  }
}

function checkIdList(list, label) {
  if (!Array.isArray(list) || list.length === 0) fatal(`${label}: expected a non-empty array`);
  for (const id of list) {
    if (typeof id !== 'string' || !ID_RE.test(id)) fatal(`${label}: invalid model id`);
  }
  return [...list];
}

function checkLevels(levels, label) {
  if (!Array.isArray(levels)) fatal(`${label}: expected an array`);
  return levels.map((level, index) => {
    if (!level || typeof level !== 'object') fatal(`${label}: each level must be an object`);
    checkKeys(level, ['effort', 'description'], `${label}[${index}]`);
    if (typeof level.effort !== 'string' || typeof level.description !== 'string') {
      fatal(`${label}: each level needs effort and description`);
    }
    return { effort: level.effort, description: level.description };
  });
}

function checkTiers(tiers, label) {
  if (!Array.isArray(tiers)) fatal(`${label}: expected an array`);
  return tiers.map((tier, index) => {
    if (!tier || typeof tier !== 'object') fatal(`${label}: each tier must be an object`);
    checkKeys(tier, ['id', 'name', 'description'], `${label}[${index}]`);
    if (typeof tier.id !== 'string' || typeof tier.name !== 'string') {
      fatal(`${label}: each tier needs id and name`);
    }
    if (tier.description !== undefined && typeof tier.description !== 'string') {
      fatal(`${label}: tier description must be a string`);
    }
    // Codex schema types description as a string; an omitted one becomes "".
    return { id: tier.id, name: tier.name, description: tier.description ?? '' };
  });
}

function normalizeModelOverride(raw, label) {
  if (!raw || typeof raw !== 'object') fatal(`${label}: expected an object`);
  checkKeys(raw, ['description', 'reasoningLevels', 'defaultReasoningLevel', 'serviceTiers',
    'additionalSpeedTiers', 'defaultServiceTier'], label);
  const out = {};
  if (raw.description !== undefined) {
    if (typeof raw.description !== 'string') fatal(`${label}.description: expected a string`);
    out.description = raw.description;
  }
  if (raw.reasoningLevels !== undefined) out.reasoningLevels = checkLevels(raw.reasoningLevels, `${label}.reasoningLevels`);
  if (raw.defaultReasoningLevel !== undefined) {
    if (typeof raw.defaultReasoningLevel !== 'string') fatal(`${label}.defaultReasoningLevel: expected a string`);
    out.defaultReasoningLevel = raw.defaultReasoningLevel;
  }
  if (raw.serviceTiers !== undefined) out.serviceTiers = checkTiers(raw.serviceTiers, `${label}.serviceTiers`);
  if (raw.additionalSpeedTiers !== undefined) {
    const speed = raw.additionalSpeedTiers;
    if (!Array.isArray(speed) || speed.some((entry) => typeof entry !== 'string')) {
      fatal(`${label}.additionalSpeedTiers: expected an array of strings`);
    }
    out.additionalSpeedTiers = speed;
  }
  if (raw.defaultServiceTier !== undefined) {
    if (typeof raw.defaultServiceTier !== 'string') fatal(`${label}.defaultServiceTier: expected a string`);
    out.defaultServiceTier = raw.defaultServiceTier;
  }
  return out;
}

function normalizeRoute(path, raw, limits) {
  if (path[0] !== '/') fatal(`route ${path}: path must start with /`);
  if (!raw || typeof raw !== 'object') fatal(`route ${path}: expected an object`);
  checkKeys(raw, ['gatewayLabel', 'upstream', 'inheritBaseTiers', 'models', 'metadata', 'supplement'],
    `route ${path}`);
  if (typeof raw.gatewayLabel !== 'string' || raw.gatewayLabel === '') {
    fatal(`route ${path}: gatewayLabel is required`);
  }
  const route = {
    path,
    gatewayLabel: raw.gatewayLabel,
    upstream: checkUpstream(raw.upstream, `route ${path}.upstream`),
    // Off by default: a gateway must not publish the bundled catalog's speed
    // tiers for a model that exists in both unless the operator opts in with
    // upstream evidence. Templates like context window still flow through.
    inheritBaseTiers: raw.inheritBaseTiers === true,
    models: {},
    metadata: null,
    supplement: null,
    limits,
  };
  if (raw.models !== undefined) {
    if (!raw.models || typeof raw.models !== 'object') fatal(`route ${path}.models: expected an object`);
    for (const [id, value] of Object.entries(raw.models)) {
      if (!ID_RE.test(id)) fatal(`route ${path}.models: invalid model id`);
      route.models[id] = normalizeModelOverride(value, `route ${path}.models.${id}`);
    }
  }
  if (raw.metadata !== undefined && raw.metadata !== null) {
    if (typeof raw.metadata !== 'object') fatal(`route ${path}.metadata: expected an object`);
    checkKeys(raw.metadata, ['url', 'timeoutMs'], `route ${path}.metadata`);
    if (typeof raw.metadata.url !== 'string') fatal(`route ${path}.metadata.url: expected a string`);
    route.metadata = {
      url: checkUpstream(raw.metadata.url, `route ${path}.metadata.url`),
      timeoutMs: isPositiveInt(raw.metadata.timeoutMs) ? raw.metadata.timeoutMs : limits.metadataTimeoutMs,
    };
  }
  if (raw.supplement !== undefined && raw.supplement !== null) {
    const sup = raw.supplement;
    if (!sup || typeof sup !== 'object') fatal(`route ${path}.supplement: expected an object`);
    // `query` is called out on its own: it is a plausible typo with a specific fix.
    checkKeys(sup, ['url', 'allowIds', 'modelDescriptions', 'timeoutMs', 'query'],
      `route ${path}.supplement`);
    if (typeof sup.url !== 'string') fatal(`route ${path}.supplement.url: expected a string`);
    if (sup.query !== undefined) {
      fatal(`route ${path}.supplement.query: put the fixed query inside supplement.url instead`);
    }
    const supplementUrl = checkUpstream(sup.url, `route ${path}.supplement.url`);
    // The same caller Bearer is sent to both hops, so the supplemental catalog
    // must stay on the primary catalog's origin. Anonymous metadata may not.
    if (new URL(supplementUrl).origin !== new URL(route.upstream).origin) {
      fatal(`route ${path}.supplement.url: must share the origin of the route upstream`);
    }
    const descriptions = {};
    if (sup.modelDescriptions !== undefined) {
      if (!sup.modelDescriptions || typeof sup.modelDescriptions !== 'object') {
        fatal(`route ${path}.supplement.modelDescriptions: expected an object`);
      }
      for (const [id, value] of Object.entries(sup.modelDescriptions)) {
        if (typeof value !== 'string') fatal(`route ${path}.supplement.modelDescriptions.${id}: expected a string`);
        descriptions[id] = value;
      }
    }
    route.supplement = {
      url: supplementUrl,
      // Only these exact ids may ever be appended; nothing else is admitted,
      // even when the upstream returns more.
      allowIds: checkIdList(sup.allowIds, `route ${path}.supplement.allowIds`),
      modelDescriptions: descriptions,
      timeoutMs: isPositiveInt(sup.timeoutMs) ? sup.timeoutMs : limits.supplementTimeoutMs,
    };
  }
  return route;
}

function loadConfig(configPath) {
  let raw;
  try {
    raw = JSON.parse(readFileSync(configPath, 'utf8'));
  } catch (error) {
    fatal(`cannot read ${configPath}: ${error.code || 'parse error'}`);
  }

  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) fatal('config: expected an object');
  if (raw.listen !== undefined) {
    if (!raw.listen || typeof raw.listen !== 'object') fatal('listen: expected an object');
    checkKeys(raw.listen, ['host', 'port'], 'listen');
  }
  const listenHost = raw.listen?.host ?? DEFAULTS.listen.host;
  if (!LOOPBACK_HOSTS.has(listenHost)) {
    fatal('listen.host must be a loopback address; remote listening is not supported');
  }
  const listenPort = raw.listen?.port ?? DEFAULTS.listen.port;
  if (!Number.isInteger(listenPort) || listenPort < 0 || listenPort > 65535) {
    fatal('listen.port must be an integer between 0 and 65535');
  }

  checkKeys(raw, ['listen', 'limits', 'routes', 'baseCatalog'], 'config');
  const limits = { ...DEFAULTS.limits };
  for (const [key, value] of Object.entries(raw?.limits ?? {})) {
    if (!(key in limits)) fatal(`limits.${key}: unknown limit`);
    if (!isPositiveInt(value)) fatal(`limits.${key}: expected a positive integer`);
    limits[key] = value;
  }

  const routes = new Map();
  const rawRoutes = raw?.routes;
  if (!rawRoutes || typeof rawRoutes !== 'object' || Array.isArray(rawRoutes)
    || Object.keys(rawRoutes).length === 0) {
    fatal('routes: expected at least one route');
  }
  for (const [path, value] of Object.entries(rawRoutes)) {
    routes.set(path, normalizeRoute(path, value, limits));
  }

  const baseCatalog = new Map();
  if (raw.baseCatalog !== undefined) {
    if (typeof raw.baseCatalog !== 'string') fatal('baseCatalog: expected a path string');
    let document;
    try {
      document = JSON.parse(readFileSync(raw.baseCatalog, 'utf8'));
    } catch (error) {
      fatal(`cannot read baseCatalog: ${error.code || 'parse error'}`);
    }
    if (!Array.isArray(document?.models)) fatal('baseCatalog: expected a models array');
    for (const model of document.models) {
      if (model && typeof model.slug === 'string') baseCatalog.set(model.slug, model);
    }
  }

  return { listen: { host: listenHost, port: listenPort }, limits, routes, baseCatalog };
}

const CONFIG = loadConfig(
  process.argv.includes('--config')
    ? process.argv[process.argv.indexOf('--config') + 1]
    : process.env.CATALOG_CONFIG || '',
);

function factsLine(meta) {
  const parts = [];
  if (meta) {
    if (Number.isInteger(meta.maxInputTokens) && meta.maxInputTokens > 0) {
      parts.push(`maxInputTokens=${meta.maxInputTokens}`);
    }
    if (Number.isInteger(meta.maxOutputTokens) && meta.maxOutputTokens > 0) {
      parts.push(`maxOutputTokens=${meta.maxOutputTokens}`);
    }
    if (meta.supportsReasoning === true) parts.push('supportsReasoning=true');
  }
  return parts.length ? ` Vendor metadata: ${parts.join(', ')}.` : ' No vendor metadata available.';
}

// Structurally minimal Codex entry for an id the bundled catalog does not know.
// No inherited prompt, tools, images or context window; nothing inferred.
function minimalDescriptor(id, route, meta) {
  return {
    slug: id,
    display_name: id,
    description: `Listed by the ${route.gatewayLabel} gateway.${factsLine(meta)}`,
    supported_reasoning_levels: [],
    shell_type: 'shell_command',
    visibility: 'list',
    supported_in_api: true,
    priority: 1000,
    support_verbosity: false,
    truncation_policy: { mode: 'tokens', limit: 10000 },
    experimental_supported_tools: [],
    base_instructions: GENERIC_INSTRUCTIONS,
  };
}

function descriptor(id, meta, route) {
  const bundled = CONFIG.baseCatalog.get(id);
  const model = bundled ? { ...bundled } : minimalDescriptor(id, route, meta);

  // A route that does not declare this gateway's speed tiers (or has no
  // evidence for them) must not publish the bundled catalog's tiers either.
  if (bundled && !route.inheritBaseTiers) {
    delete model.service_tiers;
    delete model.additional_speed_tiers;
    delete model.default_service_tier;
  }

  const override = route.models[id];
  if (override?.description !== undefined) model.description = override.description;
  if (override?.reasoningLevels) model.supported_reasoning_levels = override.reasoningLevels;
  if (override?.defaultReasoningLevel !== undefined) model.default_reasoning_level = override.defaultReasoningLevel;
  if (override?.serviceTiers) model.service_tiers = override.serviceTiers;
  if (override?.additionalSpeedTiers) model.additional_speed_tiers = override.additionalSpeedTiers;
  if (override?.defaultServiceTier !== undefined) model.default_service_tier = override.defaultServiceTier;

  if (!bundled && !override?.description) {
    const supplemental = route.supplement?.modelDescriptions?.[id];
    if (supplemental) model.description = supplemental;
  }
  // Codex types every tier field as a string, and this holds for inherited
  // official templates too: a template with a missing description, a non-string
  // speed tier or an unknown shape must not leak into the response.
  if (Array.isArray(model.service_tiers)) {
    model.service_tiers = model.service_tiers
      .filter((tier) => tier && typeof tier === 'object'
        && typeof tier.id === 'string' && typeof tier.name === 'string')
      .map((tier) => ({ ...tier, description: typeof tier.description === 'string' ? tier.description : '' }));
  } else {
    delete model.service_tiers;
  }
  if (!Array.isArray(model.additional_speed_tiers)
    || model.additional_speed_tiers.some((entry) => typeof entry !== 'string')) {
    delete model.additional_speed_tiers;
  }
  if (typeof model.default_service_tier !== 'string') delete model.default_service_tier;
  return model;
}

function send(res, status, body) {
  const text = JSON.stringify(body);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(text),
  });
  res.end(text);
}

function log(status, count, meta, route) {
  // Never logs headers, tokens, upstream bodies or upstream URLs.
  const line = { t: new Date().toISOString(), status, count, meta: meta || 'none' };
  if (route) line.gateway = route.gatewayLabel;
  console.log(JSON.stringify(line));
}

async function readLimited(response, limit) {
  const chunks = [];
  let total = 0;
  for await (const chunk of response.body) {
    total += chunk.length;
    if (total > limit) throw new Error('body_too_large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

// Anonymous, credential-free metadata. Never adds or removes models: it only
// supplies vendor figures for ids the primary catalog already returned.
async function fetchMetadata(metadata) {
  try {
    const response = await fetch(metadata.url, {
      method: 'GET',
      headers: { accept: 'application/json' },
      redirect: 'error',
      signal: AbortSignal.timeout(metadata.timeoutMs),
    });
    if (!response.ok) {
      try {
        await response.body?.cancel();
      } catch {}
      return new Map();
    }
    const parsed = JSON.parse(await readLimited(response, CONFIG.limits.maxMetadataBytes));
    const list = Array.isArray(parsed?.models)
      ? parsed.models
      : Array.isArray(parsed?.data?.models)
        ? parsed.data.models
        : null;
    if (!list) return new Map();
    const map = new Map();
    for (const item of list) {
      const name = item && typeof item.modelName === 'string' ? item.modelName.trim() : '';
      if (!name || !ID_RE.test(name)) continue;
      const meta = {};
      if (Number.isInteger(item.maxInputTokens) && item.maxInputTokens > 0) meta.maxInputTokens = item.maxInputTokens;
      if (Number.isInteger(item.maxOutputTokens) && item.maxOutputTokens > 0) meta.maxOutputTokens = item.maxOutputTokens;
      if (typeof item.supportsReasoning === 'boolean') meta.supportsReasoning = item.supportsReasoning;
      if (Object.keys(meta).length) map.set(name, meta);
    }
    return map;
  } catch {
    return new Map();
  }
}

function extractIds(payload) {
  let parsed;
  try {
    parsed = JSON.parse(payload);
  } catch {
    return null;
  }
  const list = parsed && Array.isArray(parsed.data) ? parsed.data : null;
  if (!list) return null;
  const ids = [];
  const seen = new Set();
  for (const item of list) {
    const id = item && typeof item.id === 'string' ? item.id.trim() : '';
    if (!ID_RE.test(id) || seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
    if (ids.length >= CONFIG.limits.maxModels) break;
  }
  return ids;
}

// Optional second catalog for a route. Runs beside the primary call and is
// allowed to contribute only the exact ids on its allowlist; any failure,
// wrong status, redirect or unusable body simply yields nothing.
function startSupplement(route, token) {
  const controller = new AbortController();
  const promise = (async () => {
    try {
      const response = await fetch(route.supplement.url, {
        method: 'GET',
        headers: { authorization: `Bearer ${token}`, accept: 'application/json' },
        redirect: 'error',
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(route.supplement.timeoutMs)]),
      });
      if (!response.ok) {
        try {
          await response.body?.cancel();
        } catch {}
        return [];
      }
      const ids = extractIds(await readLimited(response, CONFIG.limits.maxBodyBytes));
      if (!ids) return [];
      return ids.filter((id) => route.supplement.allowIds.includes(id));
    } catch {
      return [];
    }
  })();
  return {
    abort: () => controller.abort(),
    // Never wait past the caller's shared deadline; abandon the hop instead.
    async within(deadline) {
      const left = deadline - Date.now();
      if (left <= 0) {
        controller.abort();
        return [];
      }
      let timer;
      const timeout = new Promise((resolve) => {
        timer = setTimeout(() => resolve(null), left);
      });
      const result = await Promise.race([promise, timeout]);
      clearTimeout(timer);
      if (result === null) controller.abort();
      return result || [];
    },
  };
}

const server = http.createServer(async (req, res) => {
  const path = typeof req.url === 'string' ? req.url.split('?')[0] : '';
  const route = CONFIG.routes.get(path);
  if (!route) {
    send(res, 404, { error: 'not_found' });
    return log(404, 0);
  }
  if (req.method !== 'GET') {
    send(res, 405, { error: 'method_not_allowed' });
    return log(405, 0);
  }
  const match = /^Bearer ([^\s]+)$/.exec(req.headers.authorization || '');
  if (!match) {
    send(res, 401, { error: 'unauthorized' });
    return log(401, 0);
  }
  const token = match[1];
  const startedAt = Date.now();
  // Both optional hops start only after authentication, so a rejected request
  // never produces an outbound call.
  const metadataP = route.metadata ? fetchMetadata(route.metadata) : Promise.resolve(new Map());
  const supplement = route.supplement ? startSupplement(route, token) : null;

  let upstream;
  try {
    upstream = await fetch(route.upstream, {
      method: 'GET',
      headers: { authorization: `Bearer ${token}`, accept: 'application/json' },
      redirect: 'error',
      signal: AbortSignal.timeout(CONFIG.limits.upstreamTimeoutMs),
    });
  } catch {
    supplement?.abort();
    await metadataP;
    send(res, 502, { error: 'upstream_unavailable' });
    return log(502, 0, null, route);
  }
  if (!upstream.ok) {
    supplement?.abort();
    const status = upstream.status === 401 || upstream.status === 403 ? upstream.status : 502;
    try {
      await upstream.body?.cancel();
    } catch {}
    await metadataP;
    send(res, status, { error: status === 401 ? 'unauthorized' : 'upstream_error' });
    return log(status, 0, null, route);
  }
  let payload;
  try {
    payload = await readLimited(upstream, CONFIG.limits.maxBodyBytes);
  } catch {
    supplement?.abort();
    await metadataP;
    send(res, 502, { error: 'upstream_error' });
    return log(502, 0, null, route);
  }
  const ids = extractIds(payload);
  if (!ids) {
    supplement?.abort();
    await metadataP;
    send(res, 502, { error: 'upstream_invalid' });
    return log(502, 0, null, route);
  }

  let allIds = ids;
  let extras = 0;
  if (supplement) {
    for (const id of await supplement.within(startedAt + CONFIG.limits.totalBudgetMs)) {
      if (allIds.length >= CONFIG.limits.maxModels) break;
      if (!allIds.includes(id)) {
        allIds = [...allIds, id];
        extras += 1;
      }
    }
  }

  const meta = await metadataP;
  const models = allIds.map((id) => descriptor(id, meta.get(id), route));
  const enriched = models.filter((_, index) => meta.has(allIds[index])).length;
  send(res, 200, { models });
  const label = enriched ? `metadata_matched=${enriched}` : 'metadata_none';
  log(200, models.length, extras ? `${label} supplement=${extras}` : label, route);
});

server.listen(CONFIG.listen.port, CONFIG.listen.host, () => {
  const address = server.address();
  console.log(JSON.stringify({
    t: new Date().toISOString(),
    event: 'listening',
    host: CONFIG.listen.host,
    port: typeof address === 'object' && address ? address.port : CONFIG.listen.port,
    routes: [...CONFIG.routes.keys()],
  }));
});

for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}

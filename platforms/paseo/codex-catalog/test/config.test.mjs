// Startup validation and secret hygiene — offline, synthetic inputs.
import assert from 'node:assert/strict';
import { after, describe, test } from 'node:test';
import { join } from 'node:path';
import { symlinkSync, writeFileSync } from 'node:fs';
import {
  FAKE_TOKEN, cleanupRoots, fixture, get, json, runServerExpectingExit, runServerWithConfigArg,
  startServer, tempRoot,
} from './helpers.mjs';

const SUCCESS = ['gpt-example-large', 'gpt-example-mini'];
// Synthetic stand-in for "something that looks like a credential"; asserted absent from output.
const LEAK_MARK = 'nzqk-wjvbc';

after(() => cleanupRoots());

describe('startup refusal', () => {
  const base = { listen: { host: '127.0.0.1', port: 0 } };

  async function refuse(config, pattern) {
    const result = await runServerExpectingExit({ ...base, ...config });
    assert.equal(result.code, 2, result.output);
    assert.match(result.output, pattern);
    assert.equal(result.output.includes(LEAK_MARK), false);
  }

  test('a non-loopback listen address is refused', async () => {
    const route = { gatewayLabel: 'Alpha', upstream: 'https://alpha.example.invalid/v1/models' };
    for (const host of ['0.0.0.0', '::', '192.0.2.10']) {
      await refuse({ listen: { host, port: 0 }, routes: { '/alpha/v1/models': route } }, /loopback/);
    }
  });

  test('plain http to a remote host is refused', () =>
    refuse({ routes: { '/alpha/v1/models': { gatewayLabel: 'Alpha', upstream: 'http://alpha.example.invalid/v1/models' } } },
      /only https/));

  test('userinfo in any configured URL is refused', async () => {
    const withUserinfo = `https://operator:${LEAK_MARK}@alpha.example.invalid/v1/models`;
    const routes = (patch) => ({ '/alpha/v1/models': {
      gatewayLabel: 'Alpha', upstream: 'https://alpha.example.invalid/v1/models', ...patch } });
    await refuse({ routes: routes({ upstream: withUserinfo }) }, /userinfo/);
    await refuse({ routes: routes({ supplement: { url: withUserinfo, allowIds: ['text-embedding-3-small'] } }) },
      /userinfo/);
    await refuse({ routes: routes({ metadata: { url: withUserinfo } }) }, /userinfo/);
  });

  test('a URL fragment is refused so the fixed query stays unambiguous', async () => {
    const routes = (url) => ({ '/alpha/v1/models': {
      gatewayLabel: 'Alpha', upstream: url } });
    await refuse({ routes: routes('https://alpha.example.invalid/v1/models#frag') }, /fragments/);
  });

  test('unknown config fields are refused instead of silently ignored', async () => {
    const upstream = 'https://alpha.example.invalid/v1/models';
    const routes = (route) => ({ '/alpha/v1/models': route });
    await refuse({ routes: routes({ gatewayLabel: 'Alpha', upstream, model_catalog_url: upstream }) },
      /route \/alpha\/v1\/models\.model_catalog_url: unknown field/);
    await refuse({ routes: routes({
      gatewayLabel: 'Alpha',
      upstream,
      supplement: { url: upstream, allowIds: ['text-embedding-3-small'], allow_ids: ['x'] },
    }) }, /supplement\.allow_ids: unknown field/);
    await refuse({ routes: routes({
      gatewayLabel: 'Alpha',
      upstream,
      metadata: { url: 'https://alpha-public.example.invalid/models', headers: {} },
    }) }, /metadata\.headers: unknown field/);
    await refuse({ ...{ listen: { host: '127.0.0.1', port: 0 } }, routes: routes({ gatewayLabel: 'Alpha', upstream }),
      profile: 'prod' }, /config\.profile: unknown field/);
    await refuse({ routes: routes({
      gatewayLabel: 'Alpha',
      upstream,
      models: { 'gpt-example-large': { serviceTiers: [{ id: 'priority', name: 'Fast', pririty: true }] } },
    }) }, /serviceTiers\[0\]\.pririty: unknown field/);
  });

  test('supplement must share the primary origin', () =>
    refuse({ routes: { '/alpha/v1/models': {
      gatewayLabel: 'Alpha',
      upstream: 'https://alpha.example.invalid/v1/models',
      supplement: { url: 'https://other.example.invalid/v1/models', allowIds: ['text-embedding-3-small'] },
    } } }, /share the origin/));

  test('the split supplement.query field is refused', () =>
    refuse({ routes: { '/alpha/v1/models': {
      gatewayLabel: 'Alpha',
      upstream: 'https://alpha.example.invalid/v1/models',
      supplement: {
        url: 'https://alpha.example.invalid/v1/models',
        query: 'api_type=openai',
        allowIds: ['text-embedding-3-small'],
      },
    } } }, /supplement\.url/));

  test('a tier without a description is still a legal config', async () => {
    const primary = await fixture((req, res) => json(res, { data: [{ id: 'gpt-example-large' }] }));
    const server = await startServer({
      ...base,
      routes: { '/alpha/v1/models': {
        gatewayLabel: 'Alpha',
        upstream: `${primary.url}/v1/models`,
        models: { 'gpt-example-large': { serviceTiers: [{ id: 'priority', name: 'Fast' }] } },
      } },
    });
    try {
      const result = await get(server.url);
      assert.deepEqual(result.body.models[0].service_tiers,
        [{ id: 'priority', name: 'Fast', description: '' }]);
    } finally {
      await server.stop();
      await primary.close();
    }
  });
});

describe('published example config', () => {
  test('the sample parses and declares speed tiers with string descriptions', async () => {
    const { readFileSync } = await import('node:fs');
    const { dirname, join } = await import('node:path');
    const { fileURLToPath } = await import('node:url');
    const sample = JSON.parse(readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '..', 'catalog.example.json'), 'utf8'));
    const routes = Object.values(sample.routes ?? {});
    assert.ok(routes.length >= 2, 'sample keeps more than one independent route');
    const declared = routes.flatMap((route) => Object.values(route.models ?? {}))
      .flatMap((model) => model.serviceTiers ?? []);
    // Both Fast (priority) and Ultrafast (ultrafast) are demonstrated.
    assert.ok(declared.some((tier) => tier.id === 'priority' && tier.name === 'Fast'));
    assert.ok(declared.some((tier) => tier.id === 'ultrafast' && tier.name === 'Ultrafast'));
    // Both routes declare Fast and Ultrafast for the two GPT-6.2 ids.
    const fastAndUltra = (route) => Object.entries(route.models ?? {})
      .filter(([, m]) => (m.serviceTiers ?? []).map((t) => t.id).join() === 'priority,ultrafast')
      .map(([id]) => id).sort();
    for (const [path, route] of Object.entries(sample.routes)) {
      assert.deepEqual(fastAndUltra(route), ['gpt-6.2-astra', 'gpt-6.2-sol'], path);
    }
    // Both routes pin DeepSeek Flash to its four levels with `none` as default.
    for (const [path, route] of Object.entries(sample.routes)) {
      const flash = route.models?.['deepseek-flash'];
      assert.ok(flash, `${path} declares deepseek-flash`);
      assert.deepEqual((flash.reasoningLevels ?? []).map((level) => level.effort),
        ['none', 'low', 'high', 'max'], path);
      assert.equal(flash.defaultReasoningLevel, 'none', path);
      // GPT-6.2 reasoning levels stay inherited from the base template.
      for (const id of ['gpt-6.2-sol', 'gpt-6.2-astra']) {
        assert.equal(route.models?.[id]?.reasoningLevels, undefined, `${path} ${id}`);
      }
    }
    for (const tier of declared) {
      assert.equal(typeof tier.id, 'string');
      assert.equal(typeof tier.name, 'string');
      assert.equal(typeof tier.description, 'string');
    }
    // Every sample host is a reserved documentation domain.
    const urls = [];
    for (const route of routes) {
      urls.push(route.upstream, route.metadata?.url, route.supplement?.url);
    }
    for (const url of urls.filter(Boolean)) {
      assert.match(new URL(url).hostname, /(\.example\.invalid|example\.com)$/, url);
    }
  });

  test('fixtures never hand the client a port fetch() refuses', async () => {
    const { isBadPort, listenLoopback } = await import('./helpers.mjs');
    const { createServer } = await import('node:http');
    const server = createServer((_, res) => res.end());
    try {
      for (let i = 0; i < 12; i += 1) {
        const port = await listenLoopback(server);
        assert.equal(isBadPort(port), false, `port ${port}`);
        await new Promise((done) => server.close(done));
      }
    } finally {
      if (server.listening) await new Promise((done) => server.close(done));
    }
  });
});

describe('anonymous metadata and log hygiene', () => {
  test('anonymous metadata may live on another origin and never sees the bearer', async () => {
    const primary = await fixture((req, res) => json(res, { data: SUCCESS.map((id) => ({ id })) }));
    const metadata = await fixture((req, res) =>
      json(res, { models: [{ modelName: 'gpt-example-large', maxInputTokens: 64000 }] }));
    const server = await startServer({
      listen: { host: '127.0.0.1', port: 0 },
      routes: { '/alpha/v1/models': {
        gatewayLabel: 'Alpha',
        upstream: `${primary.url}/v1/models`,
        metadata: { url: `${metadata.url}/api/public/catalog/models` },
      } },
    });
    try {
      const result = await get(server.url);
      assert.equal(result.status, 200);
      assert.equal(result.body.models[0].description,
        'Listed by the Alpha gateway. Vendor metadata: maxInputTokens=64000.');
      assert.equal(metadata.seen.at(-1).authorization, null);
      assert.equal(primary.seen.at(-1).authorization, `Bearer ${FAKE_TOKEN}`);
    } finally {
      await server.stop();
      await primary.close();
      await metadata.close();
    }
  });

  test('logs and refused output contain no token and no upstream URL', async () => {
    const upstream = await fixture((req, res) => json(res, { data: SUCCESS.map((id) => ({ id })) }));
    const server = await startServer({
      listen: { host: '127.0.0.1', port: 0 },
      routes: { '/alpha/v1/models': { gatewayLabel: 'Alpha', upstream: `${upstream.url}/v1/models` } },
    });
    try {
      await get(server.url);
      await get(server.url, { token: null });
      await get(server.url, { path: '/nope' });
      await server.stop();
      const logs = server.stdout() + server.stderr();
      for (const forbidden of [FAKE_TOKEN, upstream.url, 'authorization']) {
        assert.equal(logs.includes(forbidden), false, forbidden);
      }
    } finally {
      await server.stop();
      await upstream.close();
    }
  });
});

describe('config path boundary', () => {
  const route = { gatewayLabel: 'Alpha', upstream: 'https://alpha.example.invalid/v1/models' };
  const body = JSON.stringify({ listen: { host: '127.0.0.1', port: 0 }, routes: { '/alpha/v1/models': route } });

  test('a relative --config is refused instead of resolving against the cwd', async () => {
    const dir = tempRoot();
    writeFileSync(join(dir, 'catalog.json'), body, { mode: 0o600 });
    const result = await runServerWithConfigArg('catalog.json', { cwd: dir });
    assert.equal(result.code, 2, result.output);
    assert.match(result.output, /must be an absolute path/);
    assert.equal(result.output.includes('"event":"listening"'), false);
  });

  test('an absolute path outside the trusted directories is refused', async () => {
    const launch = tempRoot();
    const elsewhere = tempRoot();
    const outside = join(elsewhere, 'catalog.json');
    writeFileSync(outside, body, { mode: 0o600 });
    const result = await runServerWithConfigArg(outside, { cwd: launch });
    assert.equal(result.code, 2, result.output);
    assert.match(result.output, /is outside/);
    assert.equal(result.output.includes('"event":"listening"'), false);
  });

  test('a symlink inside the launch directory that escapes it is refused', async () => {
    const launch = tempRoot();
    const elsewhere = tempRoot();
    const outside = join(elsewhere, 'catalog.json');
    writeFileSync(outside, body, { mode: 0o600 });
    const link = join(launch, 'catalog.json');
    symlinkSync(outside, link);
    const result = await runServerWithConfigArg(link, { cwd: launch });
    assert.equal(result.code, 2, result.output);
    assert.match(result.output, /is outside/);
    assert.equal(result.output.includes('"event":"listening"'), false);
  });

  test('a config over the size bound is refused before parsing', async () => {
    const launch = tempRoot();
    const oversized = join(launch, 'catalog.json');
    // Valid JSON, but far above the 256 KiB bound.
    writeFileSync(oversized, `{"pad":"${'x'.repeat(300000)}"}`, { mode: 0o600 });
    const result = await runServerWithConfigArg(oversized, { cwd: launch });
    assert.equal(result.code, 2, result.output);
    assert.match(result.output, /larger than/);
    assert.equal(result.output.includes('"event":"listening"'), false);
  });
});

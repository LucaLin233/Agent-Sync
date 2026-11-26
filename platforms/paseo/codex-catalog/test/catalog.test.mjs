// Primary list, optional supplement and per-route metadata — offline, synthetic.
import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';
import { FAKE_TOKEN, cleanupRoots, fixture, get, json, respondLater, startServer } from './helpers.mjs';

const SUCCESS = ['gpt-example-large', 'gpt-example-mini'];

after(() => cleanupRoots());

describe('primary list and optional supplement error semantics', () => {
  // One origin serves both hops: the supplemental catalog receives the same
  // caller bearer, so it must share the primary origin.
  let gateway;
  let redirectTarget;
  // Handlers are fixed fields. Dispatch below is a `switch` over literal
  // paths, so the request URL never becomes a property name or method name:
  // an unexpected path can only reach the 404 branch, never stored code.
  const behaviour = {};

  before(async () => {
    redirectTarget = await fixture((req, res) => json(res, { data: [{ id: 'hijacked-model' }] }));
    gateway = await fixture((req, res) => {
      switch (req.url.split('?')[0]) {
        case '/alpha/primary': return behaviour.primary(req, res);
        case '/alpha/supplement': return behaviour.supplement(req, res);
        case '/alpha/extras': return behaviour.extras(req, res);
        case '/alpha/supplement-500': return behaviour.supplement500(req, res);
        case '/alpha/supplement-garbage': return behaviour.supplementGarbage(req, res);
        case '/alpha/supplement-slow': return behaviour.supplementSlow(req, res);
        case '/alpha/supplement-redirect': return behaviour.supplementRedirect(req, res);
        case '/alpha/primary-500': return behaviour.primary500(req, res);
        case '/alpha/primary-401': return behaviour.primary401(req, res);
        case '/alpha/primary-garbage': return behaviour.primaryGarbage(req, res);
        default: return json(res, { error: 'unexpected path' }, 404);
      }
    });
    const ids = (list) => ({ data: list.map((id) => ({ id })) });
    behaviour.primary = (req, res) => json(res, ids(SUCCESS));
    behaviour.supplement = (req, res) =>
      json(res, ids([...SUCCESS, 'text-embedding-3-small', 'unlisted-model']));
    behaviour.extras = (req, res) => json(res, ids(['extra-one', 'extra-two', 'extra-three']));
    behaviour.supplement500 = (req, res) => json(res, { error: 'boom' }, 500);
    behaviour.supplementGarbage = (req, res) => {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end('not-json');
    };
    behaviour.supplementSlow = (req, res) =>
      respondLater(res, 4000, ids(['text-embedding-3-small']));
    behaviour.supplementRedirect = (req, res) => {
      res.writeHead(302, { location: `${redirectTarget.url}/steal` });
      res.end();
    };
    behaviour.primary500 = (req, res) => json(res, { error: 'boom' }, 500);
    behaviour.primary401 = (req, res) => json(res, { error: 'nope' }, 401);
    behaviour.primaryGarbage = (req, res) => {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end('not-json');
    };
  });

  after(async () => {
    await gateway?.close();
    await redirectTarget?.close();
  });

  function boot(primaryPath, supplementPath) {
    return startServer({
      listen: { host: '127.0.0.1', port: 0 },
      limits: { supplementTimeoutMs: 1500, totalBudgetMs: 2500 },
      routes: {
        '/alpha/v1/models': {
          gatewayLabel: 'Alpha',
          upstream: `${gateway.url}${primaryPath}`,
          ...(supplementPath ? {
            supplement: {
              url: `${gateway.url}${supplementPath}?api_type=openai`,
              allowIds: ['text-embedding-3-small'],
              modelDescriptions: { 'text-embedding-3-small': 'Embedding fixture.' },
            },
          } : {}),
        },
      },
    });
  }

  test('allowlisted id is appended once and everything else is dropped', async () => {
    const server = await boot('/alpha/primary', '/alpha/supplement');
    try {
      const result = await get(server.url);
      assert.equal(result.status, 200);
      const ids = result.body.models.map((model) => model.slug);
      assert.deepEqual(ids, [...SUCCESS, 'text-embedding-3-small']);
      assert.equal(ids.filter((id) => id === 'text-embedding-3-small').length, 1);
      assert.equal(ids.includes('unlisted-model'), false);
      const embedding = result.body.models.at(-1);
      assert.equal(embedding.description, 'Embedding fixture.');
      assert.equal(Object.hasOwn(embedding, 'service_tiers'), false);
      assert.equal(Object.hasOwn(embedding, 'additional_speed_tiers'), false);
      assert.deepEqual(embedding.supported_reasoning_levels, []);
      // The configured fixed query is sent verbatim; nothing is appended again.
      // (Both hops run in parallel, so find the supplement by path, not by order.)
      const supplementCalls = gateway.seen.filter((entry) => entry.url.startsWith('/alpha/supplement'));
      assert.equal(supplementCalls.length, 1);
      assert.equal(supplementCalls[0].url, '/alpha/supplement?api_type=openai');
      assert.equal(supplementCalls[0].authorization, `Bearer ${FAKE_TOKEN}`);
    } finally {
      await server.stop();
    }
  });

  test('supplement stops at maxModels instead of growing past it', async () => {
    // Primary returns two ids and the supplement offers three more, but the cap
    // only leaves room for two of them.
    const server = await startServer({
      listen: { host: '127.0.0.1', port: 0 },
      limits: { maxModels: 4 },
      routes: {
        '/alpha/v1/models': {
          gatewayLabel: 'Alpha',
          upstream: `${gateway.url}/alpha/primary`,
          supplement: {
            url: `${gateway.url}/alpha/extras`,
            allowIds: ['extra-one', 'extra-two', 'extra-three'],
          },
        },
      },
    });
    try {
      const result = await get(server.url);
      assert.equal(result.status, 200);
      assert.deepEqual(result.body.models.map((model) => model.slug),
        [...SUCCESS, 'extra-one', 'extra-two']);
    } finally {
      await server.stop();
    }
  });

  for (const [label, path] of [
    ['upstream 500', '/alpha/supplement-500'],
    ['unparsable body', '/alpha/supplement-garbage'],
    ['redirect', '/alpha/supplement-redirect'],
    ['timeout', '/alpha/supplement-slow'],
  ]) {
    test(`supplement ${label} keeps the primary list and returns 200`, async () => {
      const server = await boot('/alpha/primary', path);
      try {
        const result = await get(server.url);
        assert.equal(result.status, 200);
        assert.deepEqual(result.body.models.map((model) => model.slug), SUCCESS);
      } finally {
        await server.stop();
      }
      assert.equal(redirectTarget.seen.length, 0);
    });
  }

  test('primary failure keeps its original status semantics', async () => {
    const server = await boot('/alpha/primary-500', '/alpha/supplement');
    try {
      const result = await get(server.url);
      assert.equal(result.status, 502);
      assert.deepEqual(result.body, { error: 'upstream_error' });
    } finally {
      await server.stop();
    }
  });

  test('primary unparsable body stays a 502', async () => {
    const server = await boot('/alpha/primary-garbage', '/alpha/supplement');
    try {
      const result = await get(server.url);
      assert.equal(result.status, 502);
      assert.deepEqual(result.body, { error: 'upstream_invalid' });
    } finally {
      await server.stop();
    }
  });

  test('upstream 401 propagates as 401 rather than 502', async () => {
    const server = await boot('/alpha/primary-401', null);
    try {
      const result = await get(server.url);
      assert.equal(result.status, 401);
      assert.deepEqual(result.body, { error: 'unauthorized' });
    } finally {
      await server.stop();
    }
  });
});

describe('per-route reasoning levels and speed tiers', () => {
  let primary;
  let catalogPath;

  before(async () => {
    primary = await fixture((req, res) => json(res, {
      data: [{ id: 'gpt-example-large' }, { id: 'gpt-example-mini' },
        { id: 'deepseek-example' }, { id: 'gpt-example-messy' }],
    }));
    const { tempRoot } = await import('./helpers.mjs');
    catalogPath = `${tempRoot()}/base-models.json`;
    const { writeFileSync } = await import('node:fs');
    writeFileSync(catalogPath, JSON.stringify({
      models: [{
        slug: 'gpt-example-large',
        display_name: 'GPT Example Large',
        description: 'Bundled description.',
        context_window: 128000,
        input_modalities: ['text', 'image'],
        supported_reasoning_levels: [{ effort: 'low', description: 'Bundled low' }],
        service_tiers: [{ id: 'priority', name: 'Bundled Fast' }, { id: 'ultrafast', name: 'Bundled Ultrafast', description: 'Bundled text' }],
        additional_speed_tiers: ['fast'],
      }, {
        // Deliberately malformed template: nothing here may reach the client.
        slug: 'gpt-example-messy',
        display_name: 'GPT Example Messy',
        service_tiers: [{ id: 'priority', name: 'Fast', description: 42 }, { name: 'no id' }, null],
        additional_speed_tiers: 'fast',
        default_service_tier: 7,
      }],
    }), { mode: 0o600 });
  });

  after(async () => { await primary.close(); });

  function boot(routes) {
    return startServer({ listen: { host: '127.0.0.1', port: 0 }, baseCatalog: catalogPath, routes });
  }

  test('routes keep independent tiers, overrides and official template fields', async () => {
    const server = await boot({
      '/alpha/v1/models': {
        gatewayLabel: 'Alpha',
        upstream: `${primary.url}/v1/models`,
        inheritBaseTiers: true,
        models: {
          'gpt-example-large': {
            serviceTiers: [
              { id: 'priority', name: 'Fast', description: 'Faster responses' },
              { id: 'ultrafast', name: 'Ultrafast', description: 'Fastest available responses' },
            ],
          },
          'deepseek-example': {
            reasoningLevels: [
              { effort: 'none', description: 'No extra reasoning' },
              { effort: 'low', description: 'Lighter reasoning' },
              { effort: 'high', description: 'Deeper reasoning' },
              { effort: 'max', description: 'Deepest reasoning' },
            ],
            defaultReasoningLevel: 'none',
          },
        },
      },
      '/beta/v1/models': {
        gatewayLabel: 'Beta',
        upstream: `${primary.url}/v1/models`,
        inheritBaseTiers: false,
        models: {
          'gpt-example-large': { serviceTiers: [{ id: 'priority', name: 'Fast' }] },
        },
      },
      '/gamma/v1/models': {
        gatewayLabel: 'Gamma',
        upstream: `${primary.url}/v1/models`,
        inheritBaseTiers: true,
      },
    });
    try {
      const alpha = await get(server.url, { path: '/alpha/v1/models' });
      const alphaLarge = alpha.body.models.find((model) => model.slug === 'gpt-example-large');
      assert.deepEqual(alphaLarge.service_tiers.map((tier) => tier.id), ['priority', 'ultrafast']);
      // Inherited template tiers keep their own descriptions; config overrides win.
      assert.deepEqual(alphaLarge.service_tiers.map((tier) => tier.description),
        ['Faster responses', 'Fastest available responses']);
      // Bundled template fields survive on the route that keeps them.
      assert.equal(alphaLarge.context_window, 128000);
      assert.deepEqual(alphaLarge.input_modalities, ['text', 'image']);

      const deepseek = alpha.body.models.find((model) => model.slug === 'deepseek-example');
      assert.deepEqual(deepseek.supported_reasoning_levels.map((level) => level.effort),
        ['none', 'low', 'high', 'max']);
      assert.equal(deepseek.default_reasoning_level, 'none');

      const beta = await get(server.url, { path: '/beta/v1/models' });
      const betaLarge = beta.body.models.find((model) => model.slug === 'gpt-example-large');
      // Missing tier descriptions are normalized so Codex's string schema holds.
      assert.deepEqual(betaLarge.service_tiers, [{ id: 'priority', name: 'Fast', description: '' }]);
      assert.equal(Object.hasOwn(betaLarge, 'additional_speed_tiers'), false);
      // Isolation: Beta inherits neither Alpha's tiers nor Alpha's levels.
      assert.deepEqual(betaLarge.supported_reasoning_levels, [{ effort: 'low', description: 'Bundled low' }]);

      // Inherited template tiers get the same string normalization as config ones.
      const gamma = await get(server.url, { path: '/gamma/v1/models' });
      const gammaLarge = gamma.body.models.find((model) => model.slug === 'gpt-example-large');
      assert.deepEqual(gammaLarge.service_tiers,
        [{ id: 'priority', name: 'Bundled Fast', description: '' },
          { id: 'ultrafast', name: 'Bundled Ultrafast', description: 'Bundled text' }]);

      // Malformed template tiers are dropped or string-normalized, never echoed.
      const messy = gamma.body.models.find((model) => model.slug === 'gpt-example-messy');
      assert.deepEqual(messy.service_tiers, [{ id: 'priority', name: 'Fast', description: '' }]);
      assert.equal(Object.hasOwn(messy, 'additional_speed_tiers'), false);
      assert.equal(Object.hasOwn(messy, 'default_service_tier'), false);
      for (const model of [...alpha.body.models, ...beta.body.models]) {
        for (const tier of model.service_tiers ?? []) {
          assert.equal(typeof tier.description, 'string');
        }
      }
    } finally {
      await server.stop();
    }
  });

  test('one route can declare Fast/Ultrafast for two ids without leaking to a sibling route', async () => {
    // Mirrors the real case: two gateways serve the same ids, only one of them
    // has confirmed speed tiers for those two models.
    const tiers = [
      { id: 'priority', name: 'Fast', description: 'Faster responses' },
      { id: 'ultrafast', name: 'Ultrafast', description: 'Fastest available responses' },
    ];
    const server = await boot({
      '/alpha/v1/models': {
        gatewayLabel: 'Alpha',
        upstream: `${primary.url}/v1/models`,
        models: { 'gpt-example-large': { serviceTiers: tiers }, 'gpt-example-mini': { serviceTiers: tiers } },
      },
      '/beta/v1/models': { gatewayLabel: 'Beta', upstream: `${primary.url}/v1/models` },
    });
    try {
      const alpha = await get(server.url, { path: '/alpha/v1/models' });
      for (const id of ['gpt-example-large', 'gpt-example-mini']) {
        const model = alpha.body.models.find((entry) => entry.slug === id);
        assert.deepEqual(model.service_tiers.map((tier) => tier.id), ['priority', 'ultrafast']);
      }
      // The sibling route shares the upstream ids but declares no tiers at all.
      const beta = await get(server.url, { path: '/beta/v1/models' });
      for (const model of beta.body.models) {
        assert.equal(Object.hasOwn(model, 'service_tiers'), false, model.slug);
        assert.equal(Object.hasOwn(model, 'additional_speed_tiers'), false, model.slug);
      }
      // Reasoning levels stay per-route as well: Alpha's tiers never bring levels.
      const alphaLarge = alpha.body.models.find((entry) => entry.slug === 'gpt-example-large');
      assert.deepEqual(alphaLarge.supported_reasoning_levels, [{ effort: 'low', description: 'Bundled low' }]);
    } finally {
      await server.stop();
    }
  });

  test('a route with no declared tiers publishes none for a bundled model', async () => {
    const server = await boot({
      '/beta/v1/models': { gatewayLabel: 'Beta', upstream: `${primary.url}/v1/models` },
    });
    try {
      const result = await get(server.url, { path: '/beta/v1/models' });
      const large = result.body.models.find((model) => model.slug === 'gpt-example-large');
      assert.equal(Object.hasOwn(large, 'service_tiers'), false);
      assert.equal(Object.hasOwn(large, 'additional_speed_tiers'), false);
      const mini = result.body.models.find((model) => model.slug === 'gpt-example-mini');
      assert.equal(mini.description, 'Listed by the Beta gateway. No vendor metadata available.');
    } finally {
      await server.stop();
    }
  });
});

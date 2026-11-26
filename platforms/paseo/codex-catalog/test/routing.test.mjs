// Routes, authentication and forwarding isolation — offline, synthetic inputs.
import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';
import { FAKE_TOKEN, cleanupRoots, fixture, get, json, startServer } from './helpers.mjs';

const SUCCESS = ['gpt-example-large', 'gpt-example-mini'];

describe('routing, authentication and forwarding isolation', () => {
  let alpha;
  let beta;
  let server;

  before(async () => {
    alpha = await fixture((req, res) => json(res, { data: SUCCESS.map((id) => ({ id })) }));
    beta = await fixture((req, res) => json(res, { data: SUCCESS.map((id) => ({ id })) }));
    server = await startServer({
      listen: { host: '127.0.0.1', port: 0 },
      routes: {
        '/alpha/v1/models': { gatewayLabel: 'Alpha', upstream: `${alpha.url}/v1/models` },
        '/beta/v1/models': { gatewayLabel: 'Beta', upstream: `${beta.url}/v1/models` },
      },
    });
  });

  after(async () => {
    await server?.stop();
    await alpha?.close();
    await beta?.close();
  });

  // Temp config dirs are process-local; remove them even when a case fails.
  after(() => cleanupRoots());

  test('each route hits only its own upstream and forwards the caller bearer', async () => {
    const result = await get(server.url, { path: '/alpha/v1/models', query: '?client_version=0.0.0' });
    assert.equal(result.status, 200);
    assert.deepEqual(result.body.models.map((model) => model.slug), SUCCESS);
    assert.equal(alpha.seen.length, 1);
    assert.equal(beta.seen.length, 0);
    // The caller's client_version is not forwarded, and no other hop is added.
    assert.equal(alpha.seen[0].url, '/v1/models');
    assert.equal(alpha.seen[0].authorization, `Bearer ${FAKE_TOKEN}`);

    const other = await get(server.url, { path: '/beta/v1/models' });
    assert.equal(other.status, 200);
    assert.equal(beta.seen.length, 1);
    assert.equal(alpha.seen.length, 1);
  });

  test('rejected requests cause no outbound call at all', async () => {
    const before = alpha.seen.length + beta.seen.length;
    assert.equal((await get(server.url, { path: '/alpha/v1/models', token: null })).status, 401);
    assert.equal((await get(server.url, { path: '/alpha/v1/models', method: 'POST' })).status, 405);
    assert.equal((await get(server.url, { path: '/alpha/v1/models', method: 'DELETE' })).status, 405);
    assert.equal((await get(server.url, { path: '/alpha/v1/other' })).status, 404);
    assert.equal((await get(server.url, { path: '/alpha/v1/modelsX' })).status, 404);
    assert.equal(alpha.seen.length + beta.seen.length, before);
  });

  test('non-Bearer credentials are rejected before any upstream call', async () => {
    const before = alpha.seen.length + beta.seen.length;
    const response = await fetch(`${server.url}/alpha/v1/models`, {
      headers: { authorization: 'Basic dXNlcjpwYXNz' },
      signal: AbortSignal.timeout(15000),
    });
    await response.text();
    assert.equal(response.status, 401);
    assert.equal(alpha.seen.length + beta.seen.length, before);
  });

  test('rejected requests never trigger the optional metadata or supplement hops', async () => {
    // Regression guard: optional hops must start after authentication, so an
    // unauthenticated request cannot make the bridge fetch anything at all.
    // The supplement shares the primary origin because it reuses the bearer.
    const gateway = await fixture((req, res) => {
      if (req.url.startsWith('/alpha/supplement')) return json(res, { data: [] });
      json(res, { data: SUCCESS.map((id) => ({ id })) });
    });
    const metadata = await fixture((req, res) => json(res, { models: [] }));
    const counts = () => [gateway.seen.length, metadata.seen.length];
    try {
      const guarded = await startServer({
        listen: { host: '127.0.0.1', port: 0 },
        routes: { '/alpha/v1/models': {
          gatewayLabel: 'Alpha',
          upstream: `${gateway.url}/alpha/primary`,
          // Anonymous metadata may live on another origin.
          metadata: { url: `${metadata.url}/api/public/models` },
          supplement: { url: `${gateway.url}/alpha/supplement?api_type=openai`, allowIds: ['x-model'] },
        } },
      });
      try {
        assert.equal((await get(guarded.url, { token: null })).status, 401);
        assert.equal((await get(guarded.url, { method: 'POST' })).status, 405);
        assert.equal((await get(guarded.url, { path: '/nope' })).status, 404);
        assert.deepEqual(counts(), [0, 0]);
        // And with a token, the same route does reach both configured hops.
        assert.equal((await get(guarded.url)).status, 200);
        assert.deepEqual(counts(), [2, 1]);
      } finally {
        await guarded.stop();
      }
    } finally {
      await gateway.close();
      await metadata.close();
    }
  });

  test('a redirecting primary upstream is refused, not followed', async () => {
    const sink = await fixture((req, res) => json(res, { data: [{ id: 'hijacked-model' }] }));
    const redirector = await fixture((req, res) => {
      res.writeHead(302, { location: `${sink.url}/steal` });
      res.end();
    });
    const redirectServer = await startServer({
      listen: { host: '127.0.0.1', port: 0 },
      routes: { '/alpha/v1/models': { gatewayLabel: 'Alpha', upstream: `${redirector.url}/v1/models` } },
    });
    try {
      const result = await get(redirectServer.url);
      // fetch with redirect:'error' rejects, which the bridge maps to 502.
      assert.equal(result.status, 502);
      assert.deepEqual(result.body, { error: 'upstream_unavailable' });
      assert.equal(sink.seen.length, 0);
    } finally {
      await redirectServer.stop();
      await redirector.close();
      await sink.close();
    }
  });

  test('a caller-supplied query cannot redirect the upstream', async () => {
    await get(server.url, { path: '/alpha/v1/models', query: '?url=https%3A%2F%2Felsewhere.example.invalid' });
    assert.equal(alpha.seen.at(-1).url, '/v1/models');
  });

  test('a fixed query in the configured URL is sent verbatim, never re-assembled', async () => {
    const upstream = await fixture((req, res) => json(res, { data: SUCCESS.map((id) => ({ id })) }));
    const fixed = await startServer({
      listen: { host: '127.0.0.1', port: 0 },
      routes: { '/alpha/v1/models': {
        gatewayLabel: 'Alpha',
        upstream: `${upstream.url}/v1/responses/models?api_type=openai`,
      } },
    });
    try {
      const result = await get(fixed.url, { query: '?client_version=9.9.9' });
      assert.equal(result.status, 200);
      // Exactly one '?' and the configured query, nothing appended.
      assert.equal(upstream.seen.length, 1);
      assert.equal(upstream.seen[0].url, '/v1/responses/models?api_type=openai');
    } finally {
      await fixed.stop();
      await upstream.close();
    }
  });
});

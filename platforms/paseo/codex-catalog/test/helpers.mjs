// Shared offline fixtures for the catalog bridge tests: loopback HTTP servers,
// a synthetic bearer, and temporary directories. No network egress.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const SERVER = join(dirname(fileURLToPath(import.meta.url)), '..', 'catalog-server.mjs');
// Obviously synthetic: this value is only ever compared against itself.
export const FAKE_TOKEN = 'offline-fixture-token-0123456789';

const roots = [];

// fetch() rejects a fixed list of "bad ports" (WHATWG URL spec). A dynamic
// loopback port can land on one of them, which would make an otherwise valid
// fixture unusable — so such a port is treated as occupied and retried.
const BAD_PORTS = new Set([1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77,
  79, 87, 95, 101, 102, 103, 104, 109, 110, 111, 113, 115, 117, 119, 123, 135, 137, 139, 143,
  161, 179, 389, 427, 465, 512, 513, 514, 515, 526, 530, 531, 532, 540, 548, 554, 556, 563,
  587, 601, 636, 989, 990, 993, 995, 1719, 1720, 1723, 2049, 3659, 4045, 5060, 5061, 6000,
  6566, 6679, 6697, 10080]);
for (let port = 6665; port <= 6669; port += 1) BAD_PORTS.add(port);

export function isBadPort(port) {
  return BAD_PORTS.has(port);
}

// Listen on an ephemeral loopback port that fetch() will accept. A port outside
// fetch's blocked list is treated as unusable here exactly like a busy one: the
// socket is closed and another ephemeral port is requested.
export async function listenLoopback(server) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const port = await new Promise((resolve, reject) => {
      const onError = (error) => { server.off('listening', onListening); reject(error); };
      const onListening = () => { server.off('error', onError); resolve(server.address().port); };
      server.once('error', onError);
      server.once('listening', onListening);
      server.listen(0, '127.0.0.1');
    });
    if (!isBadPort(port)) return port;
    await new Promise((done) => server.close(done));
  }
  throw new Error('no fetch-usable loopback port available');
}

export function tempRoot() {
  const dir = mkdtempSync(join(tmpdir(), 'codex-catalog-test-'));
  roots.push(dir);
  return dir;
}

export function cleanupRoots() {
  for (const dir of roots) rmSync(dir, { recursive: true, force: true });
  roots.length = 0;
}

export function json(res, body, status = 200) {
  if (res.writableEnded || res.destroyed) return;
  const text = JSON.stringify(body);
  res.writeHead(status, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(text) });
  res.end(text);
}

// Reply late without keeping the process alive, and stay silent if the client
// (or the fixture server) has already gone away.
export function respondLater(res, delayMs, body) {
  const timer = setTimeout(() => json(res, body), delayMs);
  timer.unref();
  return timer;
}

// Loopback HTTP fixture that records the requests it received.
export function fixture(handler) {
  const seen = [];
  const server = http.createServer((req, res) => {
    seen.push({ method: req.method, url: req.url, authorization: req.headers.authorization ?? null });
    handler(req, res);
  });
  return (async () => {
    const port = await listenLoopback(server);
    return {
      port,
      seen,
      url: `http://127.0.0.1:${port}`,
      close: () => new Promise((done) => server.close(done)),
    };
  })();
}

function spawnServer(configPath) {
  const dir = dirname(configPath);
  return spawn(process.execPath, [SERVER, '--config', configPath], {
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { PATH: '/usr/bin:/bin', HOME: dir, TMPDIR: dir },
  });
}

export async function startServer(config) {
  // A port the client cannot use is as useless as a busy one: retry a few times
  // so a dynamic port landing on fetch's blocked list never fails the suite.
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const server = await bootServer(config);
    if (!isBadPort(server.port)) return server;
    await server.stop();
  }
  throw new Error('no fetch-usable port for the catalog server');
}

async function bootServer(config) {
  const dir = tempRoot();
  const configPath = join(dir, 'catalog.json');
  writeFileSync(configPath, JSON.stringify(config), { mode: 0o600 });
  const child = spawnServer(configPath);
  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (chunk) => { stdout += chunk; });
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`server did not start: ${stdout}${stderr}`)), 10000);
    const poll = () => {
      const line = stdout.split('\n').find((entry) => entry.includes('"event":"listening"'));
      if (line) {
        clearTimeout(timer);
        resolve(JSON.parse(line).port);
      } else if (child.exitCode !== null) {
        clearTimeout(timer);
        reject(new Error(`server exited ${child.exitCode}: ${stdout}${stderr}`));
      } else {
        setTimeout(poll, 25);
      }
    };
    poll();
  });
  const exited = new Promise((done) => {
    if (child.exitCode !== null) return done();
    child.once('exit', () => done());
  });
  const stop = async () => {
    if (child.exitCode === null) child.kill('SIGTERM');
    await exited;
  };
  return { port, url: `http://127.0.0.1:${port}`, stdout: () => stdout, stderr: () => stderr, stop };
}

// Startup is expected to be refused. A config that instead starts listening is a
// failure: we kill it and report code 'started', so a missing validation cannot
// hang the suite.
export async function runServerExpectingExit(config, timeoutMs = 3000) {
  const dir = tempRoot();
  const configPath = join(dir, 'catalog.json');
  writeFileSync(configPath, JSON.stringify(config), { mode: 0o600 });
  const child = spawnServer(configPath);
  let output = '';
  child.stdout.on('data', (chunk) => { output += chunk; });
  child.stderr.on('data', (chunk) => { output += chunk; });
  const code = await new Promise((resolve) => {
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGKILL');
    }, timeoutMs);
    child.once('exit', (exitCode) => {
      clearTimeout(timer);
      resolve(timedOut ? 'started' : exitCode);
    });
  });
  return { code, output };
}

export async function get(url, { token = FAKE_TOKEN, method = 'GET', path = '/alpha/v1/models', query = '' } = {}) {
  const headers = token === null ? {} : { authorization: `Bearer ${token}` };
  const response = await fetch(`${url}${path}${query}`, {
    method: token === null ? 'GET' : method,
    headers,
    redirect: 'error',
    signal: AbortSignal.timeout(15000),
  });
  const text = await response.text();
  let body = null;
  try { body = JSON.parse(text); } catch {}
  return { status: response.status, body, text };
}

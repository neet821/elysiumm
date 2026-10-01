const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const net = require('node:net');
const path = require('node:path');
const test = require('node:test');

const { configureEnvironment, createServerOptions, registerHealthRoute } = require('../server.cjs');

test('binds the Netease API to loopback and disables duplicate unblock and browser CORS paths', () => {
  const env = {
    ELYSIUM_NETEASE_API_PORT: '9876',
    ENABLE_GENERAL_UNBLOCK: 'true',
    CORS_ALLOW_ORIGIN: '*',
  };

  configureEnvironment(env);

  assert.deepEqual(createServerOptions(env), {
    host: '127.0.0.1',
    port: 9876,
    checkVersion: false,
  });
  assert.equal(env.ENABLE_GENERAL_UNBLOCK, 'false');
  assert.equal(env.CORS_ALLOW_ORIGIN, 'elysium-internal-service-only');
});

test('permits the Docker-only private listener only with its explicit guard', () => {
  assert.deepEqual(createServerOptions({
    ELYSIUM_NETEASE_API_PORT: '8765',
    ELYSIUM_NETEASE_API_HOST: '0.0.0.0',
    ELYSIUM_NETEASE_API_DOCKER_PRIVATE: 'true',
  }), {
    host: '0.0.0.0',
    port: 8765,
    checkVersion: false,
  });
  assert.throws(
    () => createServerOptions({ ELYSIUM_NETEASE_API_HOST: '0.0.0.0' }),
    /Docker-only private listener/,
  );
});

test('rejects an invalid local service port instead of falling back to public default', () => {
  assert.throws(
    () => createServerOptions({ ELYSIUM_NETEASE_API_PORT: '0;touch /tmp/pwned' }),
    /valid TCP port/,
  );
});

test('registers a private readiness endpoint without exposing provider credentials', () => {
  const handlers = new Map();
  registerHealthRoute({ get: (path, handler) => handlers.set(path, handler) });
  const response = {
    statusCode: 0,
    body: null,
    status(code) { this.statusCode = code; return this; },
    json(body) { this.body = body; return this; },
  };

  handlers.get('/healthz')({}, response);

  assert.equal(response.statusCode, 200);
  assert.deepEqual(response.body, { status: 'ok' });
  assert.equal(JSON.stringify(response.body).includes('cookie'), false);
});

test('real Netease API package starts on loopback and exits after SIGTERM', async () => {
  const reservation = net.createServer();
  await new Promise((resolve, reject) => {
    reservation.once('error', reject);
    reservation.listen(0, '127.0.0.1', resolve);
  });
  const { port } = reservation.address();
  await new Promise((resolve, reject) => reservation.close((error) => error ? reject(error) : resolve()));

  const child = spawn(process.execPath, [path.resolve(__dirname, '../server.cjs')], {
    env: { ...process.env, ELYSIUM_NETEASE_API_PORT: String(port) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let childOutput = '';
  let childError = '';
  const appendOutput = (current, chunk) => `${current}${chunk}`.slice(-4000);
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', (chunk) => {
    childOutput = appendOutput(childOutput, chunk);
  });
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => {
    childError = appendOutput(childError, chunk);
  });
  let spawnError = '';
  child.once('error', (error) => {
    spawnError = error.message;
  });
  let health;
  try {
    for (let attempt = 0; attempt < 50 && !health; attempt += 1) {
      if (child.exitCode !== null) break;
      try {
        const response = await fetch(`http://127.0.0.1:${port}/healthz`, {
          headers: { Origin: 'https://untrusted.example' },
        });
        if (response.ok) health = response;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
    }
    assert.ok(
      health,
      [
        'service should become ready on its loopback listener',
        `child exit code: ${child.exitCode}`,
        spawnError ? `spawn error: ${spawnError}` : '',
        childError ? `stderr:\n${childError.trim()}` : '',
        childOutput ? `stdout:\n${childOutput.trim()}` : '',
      ].filter(Boolean).join('\n'),
    );
    assert.equal(health.status, 200);
    assert.deepEqual(await health.json(), { status: 'ok' });
    assert.equal(health.headers.get('access-control-allow-origin'), null);

    const preflight = await fetch(`http://127.0.0.1:${port}/cloudsearch`, {
      method: 'OPTIONS',
      headers: { Origin: 'https://untrusted.example' },
    });
    assert.equal(preflight.status, 204);
    assert.equal(preflight.headers.get('access-control-allow-origin'), null);

    child.kill('SIGTERM');
    let timeout;
    let code;
    let signal;
    try {
      [code, signal] = await Promise.race([
        new Promise((resolve) => child.once('exit', (exitCode, exitSignal) => resolve([exitCode, exitSignal]))),
        new Promise((_, reject) => {
          timeout = setTimeout(() => reject(new Error('service did not stop after SIGTERM')), 5000);
        }),
      ]);
    } finally {
      clearTimeout(timeout);
    }
    assert.equal(signal, null);
    assert.equal(code, 0);
  } finally {
    if (child.exitCode === null) child.kill('SIGKILL');
  }
});

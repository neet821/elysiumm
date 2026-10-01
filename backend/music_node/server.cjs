'use strict';

const DEFAULT_PORT = 8765;
const fs = require('node:fs');
const { once } = require('node:events');
const os = require('node:os');
const path = require('node:path');

function preparePrivateRuntimeDirectory(env = process.env) {
  const runtimeDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'elysium-netease-api-'));
  try {
    // The upstream request module reads this at import time. Match its empty
    // first-run default without depending on a token left in shared /tmp.
    fs.writeFileSync(path.join(runtimeDirectory, 'anonymous_token'), '', {
      encoding: 'utf8',
      flag: 'wx',
      mode: 0o600,
    });
    env.TMPDIR = runtimeDirectory;
    return runtimeDirectory;
  } catch (error) {
    fs.rmSync(runtimeDirectory, { recursive: true, force: true });
    throw error;
  }
}

function cleanupPrivateRuntimeDirectory(runtimeDirectory) {
  try {
    fs.rmSync(runtimeDirectory, { recursive: true, force: true });
  } catch (error) {
    console.error('Netease internal API temp cleanup failed:', error.message);
  }
}

function configureEnvironment(env = process.env) {
  // Elysium calls this API server-to-server. Do not expose its routes to
  // browser origins, and do not run a second, implicit unblock resolver.
  env.ENABLE_GENERAL_UNBLOCK = 'false';
  env.CORS_ALLOW_ORIGIN = 'elysium-internal-service-only';
}

function createServerOptions(env = process.env) {
  const rawPort = env.ELYSIUM_NETEASE_API_PORT || String(DEFAULT_PORT);
  const port = Number(rawPort);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error('ELYSIUM_NETEASE_API_PORT must be a valid TCP port');
  }
  const host = env.ELYSIUM_NETEASE_API_HOST || '127.0.0.1';
  if (host !== '127.0.0.1') {
    if (host !== '0.0.0.0' || env.ELYSIUM_NETEASE_API_DOCKER_PRIVATE !== 'true') {
      throw new Error('Docker-only private listener requires explicit ELYSIUM_NETEASE_API_DOCKER_PRIVATE=true');
    }
  }
  return { host, port, checkVersion: false };
}

function registerHealthRoute(app) {
  app.get('/healthz', (_request, response) => {
    response.status(200).json({ status: 'ok' });
  });
}

async function startMusicApi(serveNcmApi, env = process.env) {
  configureEnvironment(env);
  const app = await serveNcmApi(createServerOptions(env));
  registerHealthRoute(app);
  if (app.server && !app.server.listening) {
    await once(app.server, 'listening');
  }
  return app;
}

async function main() {
  const runtimeDirectory = preparePrivateRuntimeDirectory();
  process.once('exit', () => cleanupPrivateRuntimeDirectory(runtimeDirectory));

  // Import server.js directly so startup does not make a provider registration
  // request; the private empty token file above is the upstream first-run default.
  const { serveNcmApi } = require('@neteasecloudmusicapienhanced/api/server');
  const app = await startMusicApi(serveNcmApi);
  let closing = false;
  const close = () => {
    if (closing) return;
    closing = true;
    app.server.close((error) => {
      if (error) {
        console.error('Netease internal API shutdown failed:', error.message);
        process.exit(1);
        return;
      }
      // Upstream cache timers keep the event loop alive even after the HTTP
      // server closes, so finish shutdown once in-flight HTTP work has drained.
      process.exit(0);
    });
  };
  process.once('SIGINT', close);
  process.once('SIGTERM', close);
}

if (require.main === module) {
  main().catch((error) => {
    console.error('Netease internal API startup failed:', error.message);
    process.exitCode = 1;
  });
}

module.exports = {
  configureEnvironment,
  createServerOptions,
  registerHealthRoute,
  startMusicApi,
};

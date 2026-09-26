'use strict';

const DEFAULT_PORT = 8765;
const { once } = require('node:events');

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
  return { host: '127.0.0.1', port, checkVersion: false };
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
  // Import server.js directly: requiring the package root also runs its CLI
  // entry module, which writes a provider-side anonymous token to temp storage.
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

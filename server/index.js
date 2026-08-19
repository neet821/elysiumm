import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import { createArticleStore } from './article-store.js';
import { createHttpApp } from './http-app.js';
import { createMetadataStore } from './metadata-store.js';
import { searchMetadata } from './metadata-providers.js';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const host = process.env.HOST || '127.0.0.1';
const port = Number(process.env.PORT || 3100);
const articleRoot = process.env.ARTICLE_ROOT || join('/opt/personal-archive/state/livesync', '网站内容', '文章');
const mediaRoot = process.env.MEDIA_ROOT || dirname(articleRoot);
const publicDir = process.env.PUBLIC_DIR || join(projectRoot, 'dist');
const metadataDb = process.env.METADATA_DB || join('/opt/personal-archive/state', 'elysiumm-metadata.sqlite');

const store = createArticleStore({ rootDir: articleRoot, mediaRoot });
const metadataStore = createMetadataStore(metadataDb);
async function metadataSearch(type, query) {
  const cached = metadataStore.get(type, query);
  if (cached) return [cached.data];
  const results = await searchMetadata(type, query);
  for (const result of results.slice(0, 8)) {
    metadataStore.put({ type, query, provider: result.provider, providerId: result.providerId, data: result });
  }
  return results;
}

const server = createServer(createHttpApp({ articleStore: store, publicDir, metadataSearch }));
server.listen(port, host, () => console.log(`elysiumm articles listening on http://${host}:${port}`));

function shutdown() {
  server.close(() => {
    metadataStore.close();
    process.exit(0);
  });
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

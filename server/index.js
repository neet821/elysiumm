import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import { createArticleStore } from './article-store.js';
import { createHttpApp } from './http-app.js';
import { createCachedMetadataSearch, createMetadataStore } from './metadata-store.js';
import { searchMetadata } from './metadata-providers.js';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const host = process.env.HOST || '127.0.0.1';
const port = Number(process.env.PORT || 3100);
const articleRoot = process.env.ARTICLE_ROOT || join('/opt/personal-archive/state/livesync', '网站内容');
const mediaRoot = process.env.MEDIA_ROOT || dirname(articleRoot);
const publicDir = process.env.PUBLIC_DIR || join(projectRoot, 'dist');
const metadataDb = process.env.METADATA_DB || join('/opt/personal-archive/state', 'elysiumm-metadata.sqlite');

const store = createArticleStore({ rootDir: articleRoot, mediaRoot, includeRootFiles: false });
const metadataStore = createMetadataStore(metadataDb);
const metadataSearch = createCachedMetadataSearch(metadataStore, searchMetadata);

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

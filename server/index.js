import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import { createArticleStore } from './article-store.js';
import { createHttpApp } from './http-app.js';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const host = process.env.HOST || '127.0.0.1';
const port = Number(process.env.PORT || 3100);
const articleRoot = process.env.ARTICLE_ROOT || join('/opt/personal-archive/state/livesync', '网站内容', '文章');
const mediaRoot = process.env.MEDIA_ROOT || dirname(articleRoot);
const publicDir = process.env.PUBLIC_DIR || join(projectRoot, 'dist');

const store = createArticleStore({ rootDir: articleRoot, mediaRoot });
const server = createServer(createHttpApp({ articleStore: store, publicDir }));
server.listen(port, host, () => console.log(`elysiumm articles listening on http://${host}:${port}`));

function shutdown() {
  server.close(() => process.exit(0));
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

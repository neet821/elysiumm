import { afterEach, describe, expect, it } from 'vitest';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createArticleStore } from '../server/article-store.js';
import { createHttpApp } from '../server/http-app.js';

const roots = [];
const servers = [];

afterEach(async () => {
  await Promise.all(servers.splice(0).map((server) => new Promise((resolve) => server.close(resolve))));
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function start(options = {}) {
  const root = await mkdtemp(join(tmpdir(), 'elysiumm-http-'));
  roots.push(root);
  await writeFile(join(root, 'hello.md'), `---\ntitle: Hello\n---\n# Hello\n\nWorld.`);
  const server = (await import('node:http')).createServer(createHttpApp({ articleStore: createArticleStore({ rootDir: root }), publicDir: root, ...options }));
  servers.push(server);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return `http://127.0.0.1:${server.address().port}`;
}

describe('article HTTP app', () => {
  it('serves health, index and an article', async () => {
    const base = await start();
    const health = await fetch(`${base}/api/health`);
    const index = await fetch(`${base}/api/articles`);
    const article = await fetch(`${base}/api/articles/hello`);

    expect(health.status).toBe(200);
    expect(await health.json()).toEqual({ status: 'ok' });
    expect(index.status).toBe(200);
    expect((await index.json()).articles[0].title).toBe('Hello');
    expect(article.status).toBe(200);
    expect((await article.json()).html).toContain('<h1>Hello</h1>');
  });

  it('returns not found for an unknown article', async () => {
    const base = await start();
    const response = await fetch(`${base}/api/articles/missing`);
    expect(response.status).toBe(404);
  });

  it('serves the public content grouped by category', async () => {
    const base = await start();
    const response = await fetch(`${base}/api/content`);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(expect.objectContaining({
      categories: expect.arrayContaining([
        expect.objectContaining({ id: 'article', label: '文章' }),
        expect.objectContaining({ id: 'essay', label: '随笔' }),
        expect.objectContaining({ id: 'photo', label: '照片' }),
        expect.objectContaining({ id: 'record', label: '记录' }),
      ]),
    }));
  });
});

import { afterEach, describe, expect, it } from 'vitest';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createArticleStore } from '../server/article-store.js';

const tempRoots = [];

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function makeRoot() {
  const root = await mkdtemp(join(tmpdir(), 'elysiumm-articles-'));
  tempRoots.push(root);
  return root;
}

describe('article store', () => {
  it('parses frontmatter, title, cover and excerpt from a standard note', async () => {
    const root = await makeRoot();
    await mkdir(join(root, 'images'));
    await writeFile(join(root, 'first.md'), `---\ntitle: First note\ndate: 2026-08-19\ncover: images/cover.jpg\nexcerpt: A short introduction.\n---\n# First note\n\nBody text.`);
    await writeFile(join(root, 'images', 'cover.jpg'), 'cover');

    const store = createArticleStore({ rootDir: root });
    const [article] = await store.listArticles();

    expect(article).toMatchObject({
      title: 'First note',
      slug: 'first',
      excerpt: 'A short introduction.',
      cover: 'images/cover.jpg',
      date: '2026-08-19',
    });
  });

  it('supports YAML placed after the first Markdown title', async () => {
    const root = await makeRoot();
    await writeFile(join(root, 'second.md'), `# Second note\n\ntitle: Second note\ncover: cover.png\nsummary: Read this first.\n\n## Body\n\nHello.`);

    const store = createArticleStore({ rootDir: root });
    const [article] = await store.listArticles();

    expect(article).toMatchObject({ title: 'Second note', excerpt: 'Read this first.', cover: 'cover.png' });
  });

  it('falls back to the first body paragraph and rejects paths outside the root', async () => {
    const root = await makeRoot();
    await writeFile(join(root, 'third.md'), `---\ntitle: Third note\n---\n# Third note\n\nThis becomes the preview.`);
    const store = createArticleStore({ rootDir: root });

    expect((await store.listArticles())[0].excerpt).toBe('This becomes the preview.');
    await expect(store.resolveMedia('third', '../secret.txt')).rejects.toMatchObject({ code: 'FORBIDDEN' });
  });

  it('sorts dated articles newest first', async () => {
    const root = await makeRoot();
    await writeFile(join(root, 'old.md'), `---\ntitle: Old\ndate: 2026-01-01\n---\nOld.`);
    await writeFile(join(root, 'new.md'), `---\ntitle: New\ndate: 2026-08-01\n---\nNew.`);
    const store = createArticleStore({ rootDir: root });

    expect((await store.listArticles()).map((article) => article.slug)).toEqual(['new', 'old']);
  });
});

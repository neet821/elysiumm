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

  it('keeps the preview empty when frontmatter explicitly leaves it blank', async () => {
    const root = await makeRoot();
    await writeFile(join(root, 'no-preview.md'), `---\npreview:\n---\n\nBody text should not become a preview.`);
    const store = createArticleStore({ rootDir: root });

    expect((await store.listArticles())[0].excerpt).toBe('');
  });

  it('sorts dated articles newest first', async () => {
    const root = await makeRoot();
    await writeFile(join(root, 'old.md'), `---\ntitle: Old\ndate: 2026-01-01\n---\nOld.`);
    await writeFile(join(root, 'new.md'), `---\ntitle: New\ndate: 2026-08-01\n---\nNew.`);
    const store = createArticleStore({ rootDir: root });

    expect((await store.listArticles()).map((article) => article.slug)).toEqual(['new', 'old']);
  });

  it('normalizes collection type, link, and timestamps', async () => {
    const root = await makeRoot();
    await writeFile(join(root, 'photo.md'), `---\ntype: image\nlink: false\ncreated_at: 2026-08-19T21:30:00+08:00\nupdated_at: 2026-08-19T21:31:00+08:00\n---\n![[photo.png]]`);
    const store = createArticleStore({ rootDir: root });

    expect(await store.listArticles()).toMatchObject([{
      type: 'image',
      link: false,
      createdAt: '2026-08-19',
      updatedAt: '2026-08-19',
    }]);
  });

  it('classifies Obsidian content and only publishes opted-in writing', async () => {
    const root = await makeRoot();
    await mkdir(join(root, '文章'));
    await mkdir(join(root, '随笔'));
    await mkdir(join(root, '照片'));
    await mkdir(join(root, '记录'));
    await writeFile(join(root, '文章', '公开文章.md'), `---\ntype: article\ntitle: 公开文章\n同步到网站: 是\ncover: covers/article.jpg\npreview: 文章预览\n---\n正文。`);
    await writeFile(join(root, '文章', '私密文章.md'), `---\ntype: article\ntitle: 私密文章\n同步到网站: 否\n---\n不应公开。`);
    await writeFile(join(root, '随笔', '公开随笔.md'), `---\ntype: essay\ntitle: 公开随笔\n同步到网站: 是\n---\n随笔正文。`);
    await writeFile(join(root, '照片', '夏日.md'), `---\ntype: photo\ntitle: 夏日\ntaken_at: 2026-08-22\nlocation: 杭州\n---\n![[summer.jpg]]`);
    await writeFile(join(root, '记录', '电影.md'), `---\ntype: movie\ntitle: 电影\ncover: movie.jpg\n---\n观后感。`);

    const store = createArticleStore({ rootDir: root });
    const items = await store.listArticles();

    expect(items.map((item) => [item.contentType, item.title]).sort((a, b) => a[0].localeCompare(b[0]))).toEqual([
      ['article', '公开文章'],
      ['essay', '公开随笔'],
      ['photo', '夏日'],
      ['record', '电影'],
    ].sort((a, b) => a[0].localeCompare(b[0])));
    expect(items.find((item) => item.title === '夏日')).toMatchObject({ cover: 'summer.jpg', location: '杭州', date: '2026-08-22' });
  });
});

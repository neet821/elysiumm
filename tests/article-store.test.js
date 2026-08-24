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

  it('uses the first image in the marked cover area when no cover property is set', async () => {
    const root = await makeRoot();
    await mkdir(join(root, '文章'), { recursive: true });
    await mkdir(join(root, '资源库', '附件'), { recursive: true });
    await writeFile(join(root, '文章', 'cover-area.md'), `---\ntype: article\ntitle: Cover area\n同步到网站: 是\ncover: old-cover.png\n---\n\n## 封面\n\n<!-- elysium-cover:start -->\n![[资源库/附件/cover-area.png]]\n<!-- elysium-cover:end -->\n\n<!-- elysium-edit-panel:start -->\n<details class="elysium-edit-panel"><summary>编辑信息</summary>\nINPUT[text:cover]\n</details>\n<!-- elysium-edit-panel:end -->\n\n正文。`);
    await writeFile(join(root, '资源库', '附件', 'cover-area.png'), 'cover');
    const store = createArticleStore({ rootDir: root, mediaRoot: root });

    const article = await store.getArticle('文章/cover-area');
    expect(article.cover).toBe('资源库/附件/cover-area.png');
    expect(article.html).not.toContain('编辑信息');
    expect(article.html).not.toContain('INPUT[text:cover]');
    expect(article.html).toContain('/media/%E6%96%87%E7%AB%A0%2Fcover-area/%E8%B5%84%E6%BA%90%E5%BA%93%2F%E9%99%84%E4%BB%B6%2Fcover-area.png');
  });

  it('uses the managed note filename as the public title after a direct rename', async () => {
    const root = await makeRoot();
    await mkdir(join(root, '文章'));
    await writeFile(join(root, '文章', 'renamed-on-device.md'), `---\ntype: article\ntitle: stale-old-title\n同步到网站: 是\n---\n正文。`);
    const store = createArticleStore({ rootDir: root });

    const [article] = await store.listArticles();
    expect(article.title).toBe('renamed-on-device');
    expect((await store.getArticle('文章/renamed-on-device')).html).toContain('正文。');
  });

  it('removes the Obsidian-only edit panel from public article HTML', async () => {
    const root = await makeRoot();
    await writeFile(join(root, 'panel.md'), `---\ntitle: Panel\n---\n<!-- elysium-edit-panel:start -->\n## 编辑信息\n\n\`INPUT[text:cover]\`\n<!-- elysium-edit-panel:end -->\n\n## 正文\n\n只保留正文。`);
    const store = createArticleStore({ rootDir: root });

    const article = await store.getArticle('panel');
    expect(article.html).not.toContain('INPUT[text:cover]');
    expect(article.html).toContain('只保留正文。');
  });

  it('removes the live cover view and keeps only the final cover image public', async () => {
    const root = await makeRoot();
    await mkdir(join(root, '文章'), { recursive: true });
    await mkdir(join(root, '资源库', '附件'), { recursive: true });
    await writeFile(join(root, '文章', 'live-cover.md'), `---\ntype: article\n同步到网站: 是\ncover: 资源库/附件/live-cover.png\n---\n\n## 封面\n\n<!-- elysium-cover:start -->\n\`\`\u0060dataviewjs\nawait dv.view("资源库/Scripts/elysiumCover", { kind: "article" });\n\`\`\u0060\n<!-- elysium-cover:end -->\n\n> [!info]- 编辑信息\n>\n> INPUT[textArea:preview]\n\n正文内容。`);
    await writeFile(join(root, '资源库', '附件', 'live-cover.png'), 'cover');
    const store = createArticleStore({ rootDir: root, mediaRoot: root });

    const article = await store.getArticle('文章/live-cover');
    expect(article.cover).toBe('资源库/附件/live-cover.png');
    expect(article.html).not.toContain('elysiumCover');
    expect(article.html).not.toContain('dataviewjs');
    expect(article.html).not.toContain('编辑信息');
    expect(article.html).toContain('正文内容。');
  });

  it('normalizes legacy checkbox lines into a Markdown task list', async () => {
    const root = await makeRoot();
    await writeFile(join(root, 'tasks.md'), `---\ntype: essay\n同步到网站: 是\n---\n\n[ ] 第一项\n[x] 第二项`);
    const store = createArticleStore({ rootDir: root });

    const article = await store.getArticle('tasks');
    expect(article.html).toContain('<ul>');
    expect(article.html).toContain('第一项');
    expect(article.html).toContain('第二项');
    expect(article.html).not.toContain('[ ] 第一项');
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
    await mkdir(join(root, '资源库', '模板'), { recursive: true });
    await writeFile(join(root, '文章', '公开文章.md'), `---\ntype: article\ntitle: 公开文章\n同步到网站: 是\ncover: covers/article.jpg\npreview: 文章预览\n---\n正文。`);
    await writeFile(join(root, '文章', '私密文章.md'), `---\ntype: article\ntitle: 私密文章\n同步到网站: 否\n---\n不应公开。`);
    await writeFile(join(root, '随笔', '公开随笔.md'), `---\ntype: essay\ntitle: 公开随笔\n同步到网站: 是\n---\n随笔正文。`);
    await writeFile(join(root, '照片', '夏日.md'), `---\ntype: photo\ntitle: 夏日\ntaken_at: 2026-08-22\nlocation: 杭州\n---\n![[summer.jpg]]`);
    await writeFile(join(root, '记录', '电影.md'), `---\ntype: movie\ntitle: 电影\ncover: movie.jpg\n---\n观后感。`);
    await writeFile(join(root, '资源库', '模板', 'Elysium-电影.md'), `---\ntype: movie\n---\n模板不应出现在网站。`);

    const store = createArticleStore({ rootDir: root });
    const items = await store.listArticles();

    expect(items.map((item) => [item.contentType, item.title]).sort((a, b) => a[0].localeCompare(b[0]))).toEqual([
      ['article', '公开文章'],
      ['essay', '公开随笔'],
      ['photo', '夏日'],
      ['record', '电影'],
    ].sort((a, b) => a[0].localeCompare(b[0])));
    expect(items.find((item) => item.title === '夏日')).toMatchObject({ cover: 'summer.jpg', location: '杭州', date: '2026-08-22' });
    expect(items.find((item) => item.title === '公开随笔').excerpt).not.toMatch(/编辑信息|INPUT\[/);
    expect(items.some((item) => item.title === 'Elysium-电影')).toBe(false);
  });
});

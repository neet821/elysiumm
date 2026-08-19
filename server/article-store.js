import { readFile, readdir, stat } from 'node:fs/promises';
import { basename, dirname, extname, join, relative, resolve, sep } from 'node:path';
import matter from 'gray-matter';
import { marked } from 'marked';
import sanitizeHtml from 'sanitize-html';

const FRONTMATTER_KEYS = ['cover', 'image', 'thumbnail'];
const EXCERPT_KEYS = ['description', 'excerpt', 'summary', 'preview'];

function inside(root, candidate) {
  const rel = relative(root, candidate);
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !resolve(rel).startsWith('..'));
}

function cleanText(value) {
  return typeof value === 'string' ? value.trim() : value == null ? '' : String(value).trim();
}

function dateText(value) {
  if (value instanceof Date && !Number.isNaN(value.valueOf())) return value.toISOString().slice(0, 10);
  return cleanText(value);
}

function firstHeading(source) {
  return source.match(/^\s*#\s+(.+?)\s*$/m)?.[1]?.trim() || '';
}

function parseTitleFollowedYaml(source) {
  const match = source.match(/^\s*#\s+(.+?)\s*\n+\s*\n((?:[A-Za-z_][\w-]*\s*:\s*.*\n?)+)\s*\n/m);
  if (!match) return { data: {}, body: source };
  try {
    const parsed = matter(`---\n${match[2]}---\n`);
    return { data: parsed.data, body: source.slice(0, match.index) + source.slice(match.index + match[0].length) };
  } catch {
    return { data: {}, body: source };
  }
}

function parseNote(source, fallbackTitle = '') {
  const standard = source.trimStart().startsWith('---') ? matter(source) : parseTitleFollowedYaml(source);
  const data = standard.data || {};
  const body = standard.content || standard.body || source;
  const title = cleanText(data.title) || firstHeading(source) || fallbackTitle || 'Untitled';
  const cover = FRONTMATTER_KEYS.map((key) => cleanText(data[key])).find(Boolean) || '';
  const excerpt = EXCERPT_KEYS.map((key) => cleanText(data[key])).find(Boolean) || body
    .replace(/^---[\s\S]*?---\s*/m, '')
    .replace(/^\s*#.*$/gm, '')
    .replace(/!\[\[.*?\]\]/g, '')
    .replace(/[#>*_`\[\]]/g, '')
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .find(Boolean) || '';
  return { data, body, title, cover, excerpt: excerpt.replace(/\s+/g, ' ').trim().slice(0, 280) };
}

function slugFor(relativePath) {
  return relativePath.slice(0, -extname(relativePath).length).split(sep).join('/');
}

async function markdownFiles(root) {
  const found = [];
  async function visit(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      const path = join(directory, entry.name);
      if (entry.isDirectory()) await visit(path);
      else if (entry.isFile() && extname(entry.name).toLowerCase() === '.md') found.push(path);
    }
  }
  await visit(root);
  return found;
}

async function findByName(root, name) {
  for (const entry of await readdir(root, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue;
    const path = join(root, entry.name);
    if (entry.isFile() && entry.name === name) return path;
    if (entry.isDirectory()) {
      const found = await findByName(path, name);
      if (found) return found;
    }
  }
  return '';
}

function metadata(file, root, parsed, stats) {
  const relativePath = relative(root, file);
  return {
    slug: slugFor(relativePath),
    title: parsed.title,
    excerpt: parsed.excerpt,
    cover: parsed.cover,
    date: dateText(parsed.data.date || parsed.data.published || parsed.data.created),
    tags: Array.isArray(parsed.data.tags) ? parsed.data.tags.map(cleanText).filter(Boolean) : [],
    category: cleanText(parsed.data.category || parsed.data.type || parsed.data.content_type),
    updatedAt: stats.mtime.toISOString(),
  };
}

export function createArticleStore({ rootDir, mediaRoot = rootDir }) {
  const articleRoot = resolve(rootDir);
  const assetRoot = resolve(mediaRoot);
  const cache = new Map();

  async function readRecord(file) {
    const source = await readFile(file, 'utf8');
    const parsed = parseNote(source, basename(file, extname(file)));
    const stats = await stat(file);
    const item = metadata(file, articleRoot, parsed, stats);
    cache.set(item.slug, { ...item, file, body: parsed.body, directory: dirname(file) });
    return item;
  }

  async function listArticles() {
    const files = await markdownFiles(articleRoot);
    const items = await Promise.all(files.map(readRecord));
    return items.sort((a, b) => {
      const left = b.date || b.updatedAt;
      const right = a.date || a.updatedAt;
      return left === right ? 0 : left > right ? 1 : -1;
    });
  }

  async function getArticle(slug) {
    await listArticles();
    const record = cache.get(slug);
    if (!record) {
      const error = new Error('Article not found');
      error.code = 'NOT_FOUND';
      throw error;
    }
    const imagePattern = /!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]/g;
    const markdown = record.body
      .replace(imagePattern, (_, path) => `![image](${path.trim()})`)
      .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, path) => {
        const cleanPath = path.trim().replace(/^<|>$/g, '');
        if (/^(?:https?:|data:|#|\/)/i.test(cleanPath)) return `![${alt}](${cleanPath})`;
        return `![${alt}](/media/${encodeURIComponent(record.slug)}/${encodeURIComponent(cleanPath)})`;
      });
    const rawHtml = await marked.parse(markdown, { gfm: true, breaks: false });
    const html = sanitizeHtml(rawHtml, {
      allowedTags: sanitizeHtml.defaults.allowedTags.concat(['img', 'h1', 'h2', 'h3', 'h4', 'pre', 'code']),
      allowedAttributes: { ...sanitizeHtml.defaults.allowedAttributes, img: ['src', 'alt', 'title'], a: ['href', 'name', 'target', 'rel'] },
    });
    return { ...record, html, body: undefined, file: undefined, directory: undefined };
  }

  async function resolveMedia(slug, relativePath) {
    await listArticles();
    const record = cache.get(slug);
    if (!record || typeof relativePath !== 'string') {
      const error = new Error('Media not found');
      error.code = 'NOT_FOUND';
      throw error;
    }
    const decoded = decodeURIComponent(relativePath);
    const candidates = [resolve(record.directory, decoded), resolve(assetRoot, decoded)];
    for (const candidate of candidates) {
      if (inside(record.directory, candidate) || inside(assetRoot, candidate)) {
        try {
          const info = await stat(candidate);
          if (info.isFile()) return candidate;
      } catch {}
    }
    const fallback = await findByName(articleRoot, basename(decoded));
    if (fallback) return fallback;
    }
    const error = new Error('Media path forbidden or missing');
    error.code = 'FORBIDDEN';
    throw error;
  }

  return { listArticles, getArticle, resolveMedia };
}

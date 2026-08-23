import { createReadStream } from 'node:fs';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, resolve, relative, sep } from 'node:path';
import { pipeline } from 'node:stream/promises';

const MIME = { '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.html': 'text/html; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.pdf': 'application/pdf' };

function json(response, status, data) {
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  response.end(JSON.stringify(data));
}

function isInside(root, target) {
  const rel = relative(root, target);
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`));
}

export function createHttpApp({ articleStore, publicDir }) {
  const staticRoot = resolve(publicDir);
  const categoryLabels = { article: '文章', essay: '随笔', photo: '照片', record: '记录' };
  return async (request, response) => {
    try {
      const url = new URL(request.url, 'http://localhost');
      if (request.method !== 'GET') return json(response, 405, { error: 'method_not_allowed' });
      if (url.pathname === '/api/health') return json(response, 200, { status: 'ok' });
      if (url.pathname === '/api/articles') return json(response, 200, { articles: await articleStore.listArticles() });
      if (url.pathname === '/api/content') {
        const items = await articleStore.listArticles();
        const categories = Object.entries(categoryLabels).map(([id, label]) => ({ id, label, items: items.filter((item) => item.contentType === id) }));
        return json(response, 200, { categories, items });
      }
      if (url.pathname.startsWith('/api/content/')) {
        const remainder = decodeURIComponent(url.pathname.slice('/api/content/'.length));
        const [contentType, ...slugParts] = remainder.split('/');
        const slug = slugParts.join('/');
        if (!categoryLabels[contentType] || !slug) return json(response, 404, { error: 'not_found' });
        const article = await articleStore.getArticle(slug);
        if (article.contentType !== contentType) return json(response, 404, { error: 'not_found' });
        return json(response, 200, { article, html: article.html });
      }
      if (url.pathname.startsWith('/api/articles/')) {
        const slug = decodeURIComponent(url.pathname.slice('/api/articles/'.length));
        const article = await articleStore.getArticle(slug);
        return json(response, 200, { article, html: article.html });
      }
      if (url.pathname.startsWith('/api/')) return json(response, 404, { error: 'not_found' });
      if (url.pathname.startsWith('/media/')) {
        const remainder = url.pathname.slice('/media/'.length);
        const slash = remainder.indexOf('/');
        if (slash < 1) return json(response, 404, { error: 'not_found' });
        const slug = decodeURIComponent(remainder.slice(0, slash));
        const mediaPath = remainder.slice(slash + 1);
        const file = await articleStore.resolveMedia(slug, mediaPath);
        response.writeHead(200, { 'content-type': MIME[extname(file).toLowerCase()] || 'application/octet-stream', 'cache-control': 'public, max-age=300' });
        return pipeline(createReadStream(file), response);
      }
      const requested = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
      const staticFile = resolve(staticRoot, requested);
      if (isInside(staticRoot, staticFile)) {
        try {
          const info = await stat(staticFile);
          if (info.isFile()) {
            response.writeHead(200, { 'content-type': MIME[extname(staticFile).toLowerCase()] || 'application/octet-stream' });
            return response.end(await readFile(staticFile));
          }
        } catch {}
      }
      const index = join(staticRoot, 'index.html');
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      return response.end(await readFile(index));
    } catch (error) {
      if (error.code === 'NOT_FOUND') return json(response, 404, { error: 'not_found' });
      if (error.code === 'FORBIDDEN') return json(response, 403, { error: 'forbidden' });
      if (error.code === 'UNSUPPORTED_TYPE') return json(response, 400, { error: 'unsupported_type' });
      if (error.message?.startsWith('metadata provider returned')) return json(response, 502, { error: 'metadata_provider_unavailable' });
      return json(response, 500, { error: 'server_error' });
    }
  };
}

import './styles.css';

const app = document.querySelector('#app');

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

function coverUrl(article) {
  if (!article.cover) return '';
  if (/^(?:https?:|data:|\/)/i.test(article.cover)) return article.cover;
  return `/media/${encodeURIComponent(article.slug)}/${encodeURIComponent(article.cover)}`;
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
}

function metadataSummary(article) {
  const metadata = article.metadata;
  if (!metadata) return '';
  const parts = [metadata.year, ...(metadata.genres || []).slice(0, 3)].filter(Boolean);
  return parts.length ? ` · ${escapeHtml(parts.join(' · '))}` : '';
}

function shell(content, current = '') {
  return `<header class="site-header"><a class="site-name" href="/">elysiumm.top</a><span class="site-section">${current}</span></header><main>${content}</main>`;
}

async function enrichArticle(article) {
  if (!['movie', 'album', 'book', 'game'].includes(article.type) || article.cover || article.excerpt) return article;
  try {
    const response = await fetch(`/api/metadata/search?type=${encodeURIComponent(article.type)}&q=${encodeURIComponent(article.title)}`);
    if (!response.ok) return article;
    const result = (await response.json()).results?.[0];
    if (!result) return article;
    return { ...article, cover: result.cover || article.cover, excerpt: result.description || article.excerpt, metadata: result };
  } catch {
    return article;
  }
}

async function renderHome(articles) {
  articles = await Promise.all(articles.map(enrichArticle));
  const items = articles.map((article) => `
    <article class="article-row ${article.type === 'image' ? 'image-row' : ''}">
      ${article.cover ? (article.link === false ? `<div class="article-cover"><img src="${coverUrl(article)}" alt="" loading="lazy"></div>` : `<a class="article-cover" href="/article/${encodeURIComponent(article.slug)}"><img src="${coverUrl(article)}" alt="" loading="lazy"></a>`) : ''}
      <div class="article-info">
        <div class="article-meta">${escapeHtml(formatDate(article.date || article.updatedAt))}${article.category ? ` · ${escapeHtml(article.category)}` : ''}${metadataSummary(article)}</div>
        <h2>${article.link === false ? escapeHtml(article.title) : `<a href="/article/${encodeURIComponent(article.slug)}">${escapeHtml(article.title)}</a>`}</h2>
        ${article.excerpt ? `<p>${escapeHtml(article.excerpt)}</p>` : ''}
      </div>
    </article>`).join('');
  return shell(`<div class="intro"><h1>文章</h1><p>${articles.length} 篇</p></div><section class="article-list" aria-label="文章列表">${items || '<p class="empty">还没有文章。</p>'}</section>`);
}

function renderArticle(article) {
  return shell(`<article class="reader"><a class="back-link" href="/">← 返回文章列表</a><header class="reader-header"><div class="article-meta">${escapeHtml(formatDate(article.date || article.updatedAt))}${article.category ? ` · ${escapeHtml(article.category)}` : ''}</div><h1>${escapeHtml(article.title)}</h1>${article.excerpt ? `<p class="reader-excerpt">${escapeHtml(article.excerpt)}</p>` : ''}</header><div class="reader-body">${article.html}</div></article>`, '阅读');
}

function renderError(message) {
  return shell(`<section class="state"><h1>暂时无法打开</h1><p>${escapeHtml(message)}</p><a href="/">返回首页</a></section>`);
}

async function load(path) {
  app.innerHTML = shell('<section class="state"><p>正在读取文章……</p></section>');
  const response = await fetch(path);
  if (!response.ok) throw new Error(response.status === 404 ? '找不到这篇文章。' : '服务器没有返回文章。');
  return response.json();
}

async function render() {
  try {
    const match = window.location.pathname.match(/^\/article\/(.+)$/);
    if (match) {
      const { article } = await load(`/api/articles/${match[1]}`);
      app.innerHTML = renderArticle(article);
    } else {
      const { articles } = await load('/api/articles');
      app.innerHTML = await renderHome(articles);
    }
  } catch (error) {
    app.innerHTML = renderError(error.message);
  }
}

document.addEventListener('click', (event) => {
  const link = event.target.closest('a');
  if (!link || link.target || link.origin !== window.location.origin || !link.pathname.startsWith('/article/')) return;
  event.preventDefault();
  window.history.pushState({}, '', link.href);
  render();
});
window.addEventListener('popstate', render);
render();

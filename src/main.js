import './styles.css';

const app = document.querySelector('#app');

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

function coverUrl(article) {
  return article.cover ? `/media/${encodeURIComponent(article.slug)}/${encodeURIComponent(article.cover)}` : '';
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
}

function shell(content, current = '') {
  return `<header class="site-header"><a class="site-name" href="/">elysiumm.top</a><span class="site-section">${current}</span></header><main>${content}</main>`;
}

function renderHome(articles) {
  const items = articles.map((article) => `
    <article class="article-row">
      ${article.cover ? `<a class="article-cover" href="/article/${encodeURIComponent(article.slug)}"><img src="${coverUrl(article)}" alt="" loading="lazy"></a>` : ''}
      <div class="article-info">
        <div class="article-meta">${escapeHtml(formatDate(article.date || article.updatedAt))}${article.category ? ` · ${escapeHtml(article.category)}` : ''}</div>
        <h2><a href="/article/${encodeURIComponent(article.slug)}">${escapeHtml(article.title)}</a></h2>
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
      app.innerHTML = renderHome(articles);
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

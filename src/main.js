import './styles.css';

const app = typeof document === 'undefined' ? null : document.querySelector('#app');
const categoryLabels = { article: '文章', essay: '随笔', photo: '照片', record: '记录' };
const recordLabels = { album: '专辑', movie: '电影', book: '书籍', game: '游戏' };

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

function contentHref(item) {
  return `/content/${encodeURIComponent(item.contentType)}/${encodeURIComponent(item.slug)}`;
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

function articleTime(article) {
  return new Date(article.createdAt || article.date || article.updatedAt || 0).getTime() || 0;
}

function sortRecent(items) {
  return [...items].sort((a, b) => articleTime(b) - articleTime(a));
}

export function buildCategoryNav(categories) {
  return `<nav class="content-nav" aria-label="内容分类"><a href="/">全部</a>${categories.map((category) => `<a href="/content/${encodeURIComponent(category.id)}">${escapeHtml(category.label)} <span>${category.items.length}</span></a>`).join('')}</nav>`;
}

function imageMarkup(article, className = '') {
  if (!article.cover) return '<span class="cover-missing">暂无封面</span>';
  return `<img class="${className}" src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}" loading="lazy">`;
}

export function renderContentCard(article) {
  const coverClass = article.contentType === 'record' ? 'record-cover' : 'content-cover';
  const details = [article.author, article.year, article.location].filter(Boolean).map(escapeHtml).join(' · ');
  return `<article class="content-card content-card-${escapeHtml(article.contentType)}"><a href="${contentHref(article)}" class="content-card-link"><span class="content-card-cover ${coverClass}">${imageMarkup(article)}</span><span class="content-card-info"><strong>${escapeHtml(article.title)}</strong>${details ? `<small>${details}</small>` : ''}${article.excerpt ? `<p>${escapeHtml(article.excerpt)}</p>` : ''}</span></a></article>`;
}

function section(title, items, id) {
  return `<section class="content-section" id="${escapeHtml(id)}"><div class="section-heading"><h2>${escapeHtml(title)}</h2><a href="/content/${encodeURIComponent(id)}">查看全部 ${items.length}</a></div><div class="content-grid content-grid-${escapeHtml(id)}">${items.length ? sortRecent(items).slice(0, 8).map(renderContentCard).join('') : '<p class="empty">还没有内容。</p>'}</div></section>`;
}

function renderHome(categories) {
  return `<main><header class="intro"><h1>内容</h1><p>从 Obsidian 同步的公开内容</p></header>${buildCategoryNav(categories)}<div class="home-flow">${categories.map((category) => section(category.label, category.items, category.id)).join('')}</div></main>`;
}

function metadataDetails(article) {
  const fields = [
    ['作者', article.author], ['年份', article.year], ['国家', article.country], ['语言', article.language], ['地点', article.location], ['个人评论', article.review],
  ].filter(([, value]) => value);
  return fields.length ? `<dl class="metadata-details">${fields.map(([label, value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}</dl>` : '';
}

function renderArticle(article) {
  const cover = article.cover ? `<img class="reader-cover" src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}">` : '';
  const label = categoryLabels[article.contentType] || article.type || '';
  return `<main><article class="reader"><a class="back-link" href="/content/${encodeURIComponent(article.contentType)}">← 返回${escapeHtml(label)}</a><header class="reader-header"><div class="article-meta">${escapeHtml(formatDate(article.date || article.createdAt || article.updatedAt))}${label ? ` · ${escapeHtml(label)}` : ''}</div>${cover}<h1>${escapeHtml(article.title)}</h1>${metadataDetails(article)}${article.excerpt ? `<p class="reader-excerpt">${escapeHtml(article.excerpt)}</p>` : ''}</header><div class="reader-body">${article.html}</div></article></main>`;
}

function renderCategory(category, categories) {
  return `<main><header class="intro"><h1>${escapeHtml(category.label)}</h1><p>${category.items.length} 条内容</p></header>${buildCategoryNav(categories)}<section class="content-section"><div class="content-grid content-grid-${escapeHtml(category.id)}">${category.items.length ? sortRecent(category.items).map(renderContentCard).join('') : '<p class="empty">还没有内容。</p>'}</div></section></main>`;
}

function renderError(message) {
  return `<main><section class="state"><h1>暂时无法打开</h1><p>${escapeHtml(message)}</p><a href="/">返回首页</a></section></main>`;
}

async function load(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(response.status === 404 ? '找不到这项内容。' : '服务器没有返回内容。');
  return response.json();
}

async function render() {
  try {
    const match = window.location.pathname.match(/^\/content\/([^/]+)(?:\/(.+))?$/);
    if (match?.[2]) {
      const { article } = await load(`/api/content/${match[1]}/${match[2]}`);
      app.innerHTML = renderArticle(article);
    } else if (match?.[1]) {
      const { categories } = await load('/api/content');
      const category = categories.find((item) => item.id === decodeURIComponent(match[1]));
      if (!category) throw new Error('找不到这个分类。');
      app.innerHTML = renderCategory(category, categories);
    } else {
      const { categories } = await load('/api/content');
      app.innerHTML = renderHome(categories);
    }
  } catch (error) {
    app.innerHTML = renderError(error.message);
  }
}

if (app) {
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a');
    if (!link || link.target || link.origin !== window.location.origin || (!link.pathname.startsWith('/content/') && link.pathname !== '/')) return;
    event.preventDefault();
    window.history.pushState({}, '', link.href);
    render();
  });
  window.addEventListener('popstate', render);
  render();
}

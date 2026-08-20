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

function metadataDetails(article) {
  const metadata = article.metadata;
  if (!metadata) return '';
  const fields = [
    metadata.year && `<div><dt>年份</dt><dd>${escapeHtml(metadata.year)}</dd></div>`,
    metadata.subtitle && `<div><dt>作者 / 艺术家</dt><dd>${escapeHtml(metadata.subtitle)}</dd></div>`,
    metadata.rating && `<div><dt>评分</dt><dd>${escapeHtml(metadata.rating)}</dd></div>`,
    metadata.genres?.length && `<div><dt>类型</dt><dd>${escapeHtml(metadata.genres.join(' · '))}</dd></div>`,
  ].filter(Boolean).join('');
  return fields ? `<dl class="metadata-details">${fields}</dl>` : '';
}

const collectionTypes = ['album', 'movie', 'game', 'book'];
const collectionLabels = { album: '专辑', movie: '电影', game: '游戏', book: '书籍' };

function articleTime(article) {
  return new Date(article.createdAt || article.date || article.updatedAt || 0).getTime() || 0;
}

function sortRecent(articles) {
  return [...articles].sort((a, b) => articleTime(b) - articleTime(a));
}

function articleLink(article, content) {
  return article.link === false ? content : `<a href="/article/${encodeURIComponent(article.slug)}">${content}</a>`;
}

function writingCard(article) {
  return `<article class="writing-card"><div class="article-meta">${escapeHtml(formatDate(article.createdAt || article.date || article.updatedAt))}</div><h2>${articleLink(article, escapeHtml(article.title))}</h2>${article.excerpt ? `<p>${escapeHtml(article.excerpt)}</p>` : ''}</article>`;
}

function photoCard(article) {
  const image = article.cover ? `<img src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}" loading="lazy">` : '';
  return `<article class="photo-card">${article.link === false ? `<div class="photo-frame">${image}</div>` : `<a class="photo-frame" href="/article/${encodeURIComponent(article.slug)}">${image}</a>`}<h3>${articleLink(article, escapeHtml(article.title))}</h3></article>`;
}

function collectionCard(article) {
  const image = article.cover ? `<img src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}" loading="lazy">` : '<span class="cover-missing">暂无封面</span>';
  return `<article class="collection-card">${articleLink(article, `<span class="collection-cover">${image}</span><span class="collection-name">${escapeHtml(article.title)}</span>`)}</article>`;
}

function sectionHeading(title, count, href = '') {
  return `<div class="section-heading"><h2>${title}</h2>${href ? `<a href="${href}">查看全部</a>` : `<span>${count}</span>`}</div>`;
}

function collectionTitle(article) {
  const title = article.metadata?.title;
  return title && title !== article.title ? `<p class="metadata-title">资料名称：${escapeHtml(title)}</p>` : '';
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
  const writing = sortRecent(articles.filter((article) => !collectionTypes.includes(article.type) && article.type !== 'image'));
  const photos = sortRecent(articles.filter((article) => article.type === 'image'));
  const collectionSections = collectionTypes.map((type) => {
    const recent = sortRecent(articles.filter((article) => article.type === type)).slice(0, 2);
    return `<section class="collection-section">${sectionHeading(collectionLabels[type], recent.length)}<div class="collection-cards">${recent.length ? recent.map(collectionCard).join('') : '<p class="empty">还没有记录。</p>'}</div></section>`;
  }).join('');
  return shell(`<div class="home-flow"><section class="writing-section">${sectionHeading('随笔与文章', writing.length)}<div class="writing-list">${writing.length ? writing.map(writingCard).join('') : '<p class="empty">还没有文章。</p>'}</div></section>${photos.length ? `<section class="photos-section">${sectionHeading('照片', photos.length)}<div class="photo-grid">${photos.map(photoCard).join('')}</div></section>` : ''}<section class="collections-grid">${collectionSections}</section></div>`);
}

function renderArticle(article) {
  const cover = article.cover ? `<img class="reader-cover" src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}">` : '';
  return shell(`<article class="reader"><a class="back-link" href="/">← 返回文章列表</a><header class="reader-header"><div class="article-meta">${escapeHtml(formatDate(article.createdAt || article.date || article.updatedAt))}${article.category ? ` · ${escapeHtml(article.category)}` : ''}</div>${cover}<h1>${escapeHtml(article.title)}</h1>${collectionTitle(article)}${metadataDetails(article)}${article.excerpt ? `<p class="reader-excerpt">${escapeHtml(article.excerpt)}</p>` : ''}</header><div class="reader-body">${article.html}</div></article>`, '阅读');
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
      let { article } = await load(`/api/articles/${match[1]}`);
      article = await enrichArticle(article);
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

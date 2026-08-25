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

function formatWritingDate(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'long', day: 'numeric' }).format(date);
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

function typeIcon(type, label) {
  const icons = {
    book: '<path d="M5 4.5h10.5A2.5 2.5 0 0 1 18 7v13H7a2 2 0 0 1-2-2z"/><path d="M7 4.5v15.5M9.5 9h5.5M9.5 12.5h5.5"/>',
    movie: '<path d="M4 8h16v12H4z"/><path d="M4 8 5.5 3h15L20 8M7 3l2 5M12 3l2 5M17 3l2 5M8 12h8M8 16h5"/>',
    album: '<circle cx="11" cy="13" r="8.5"/><circle cx="11" cy="13" r="2.2"/><path d="M17 5h3v3M20 8l-5 5M15 13h-2"/>',
    game: '<path d="M7 9h10a4 4 0 0 1 3.8 5.2l-1.3 4.1a2 2 0 0 1-3.5.6L14 16H10l-2 2.9a2 2 0 0 1-3.5-.6l-1.3-4.1A4 4 0 0 1 7 9z"/><path d="M7 12v4M5 14h4M16 13h.1M18 15h.1"/>',
    photo: '<path d="M4 8.5h3l1.3-2h7.4l1.3 2h3v10.8H4z"/><circle cx="12" cy="13.5" r="3.5"/><path d="M17.5 10h.1"/>',
  };
  return `<svg class="type-icon type-icon-${type}" viewBox="0 0 24 24" role="img" aria-label="${label}" focusable="false"><title>${label}</title>${icons[type] || icons.book}</svg>`;
}

function recordIcon(article) {
  const type = article.category || article.type;
  const kinds = {
    book: ['book', '阅读'],
    movie: ['movie', '电影'],
    album: ['album', '专辑'],
    game: ['game', '游戏'],
  };
  const [icon, label] = kinds[type] || kinds.book;
  return typeIcon(icon, label);
}

function articleCard(article) {
  const image = article.cover ? `<img src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}" loading="lazy">` : '';
  return `<article class="article-card"><div class="article-card-info"><h2>${articleLink(article, escapeHtml(article.title))}</h2>${image ? `<a class="article-card-cover" href="/article/${encodeURIComponent(article.slug)}">${image}</a>` : ''}${article.excerpt ? `<p>${escapeHtml(article.excerpt)}</p>` : ''}</div><time class="card-time">${escapeHtml(formatWritingDate(article.createdAt || article.date || article.updatedAt))}</time></article>`;
}

function essayCard(article, fullArticle) {
  return `<article class="essay-card"><h2>${escapeHtml(article.title)}</h2><div class="essay-body">${fullArticle?.html || (article.excerpt ? `<p>${escapeHtml(article.excerpt)}</p>` : '')}</div><time class="card-time">${escapeHtml(formatWritingDate(article.createdAt || article.date || article.updatedAt))}</time></article>`;
}

function writingCard(article) {
  return `<article class="writing-card"><h2>${articleLink(article, escapeHtml(article.title))}</h2>${article.excerpt ? `<p>${escapeHtml(article.excerpt)}</p>` : ''}<time class="card-time">${escapeHtml(formatWritingDate(article.createdAt || article.date || article.updatedAt))}</time></article>`;
}

function photoCard(article) {
  const image = article.cover ? `<img src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}" loading="lazy">` : '';
  const date = formatDate(article.date || article.createdAt || article.updatedAt);
  const location = article.location ? ` · ${escapeHtml(article.location)}` : '';
  return `<article class="photo-card">${image ? `<a class="photo-frame" href="${escapeHtml(coverUrl(article))}" target="_blank" rel="noreferrer">${image}</a>` : '<div class="photo-frame"></div>'}<h3>${typeIcon('photo', '照片')}${escapeHtml(article.title)}</h3><div class="photo-meta">${escapeHtml(date)}${location}</div></article>`;
}

function recordCard(article) {
  const image = article.cover ? `<img src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}" loading="lazy">` : '<span class="cover-missing">暂无封面</span>';
  const fields = [
    article.author && `<div><dt>作者</dt><dd>${escapeHtml(article.author)}</dd></div>`,
    article.year && `<div><dt>年份</dt><dd>${escapeHtml(article.year)}</dd></div>`,
    article.country && `<div><dt>国家</dt><dd>${escapeHtml(article.country)}</dd></div>`,
    article.language && `<div><dt>语言</dt><dd>${escapeHtml(article.language)}</dd></div>`,
    article.createdAt && `<div><dt>添加时间</dt><dd>${escapeHtml(formatDate(article.createdAt))}</dd></div>`,
  ].filter(Boolean).join('');
  return `<article class="record-card"><div class="record-cover">${image}</div><div class="record-info"><h2>${recordIcon(article)}${articleLink(article, escapeHtml(article.title))}</h2>${fields ? `<dl class="record-details">${fields}</dl>` : ''}<div class="record-review"><span>个人评论：</span><span class="record-review-text">${article.review ? escapeHtml(article.review) : '—'}</span></div></div></article>`;
}

function photoStrip(photos) {
  const cards = photos.length ? photos.map(photoCard).join('') : '<p class="photo-strip-empty">还没有照片。</p>';
  return `<section class="photo-strip"><div class="section-heading"><h2>照片</h2><span>${photos.length}</span></div><div class="photo-strip-grid">${cards}</div></section>`;
}

function collectionCard(article) {
  const image = article.cover ? `<img src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}" loading="lazy">` : '<span class="cover-missing">暂无封面</span>';
  return `<article class="collection-card">${articleLink(article, `<span class="collection-cover">${image}</span><span class="collection-name">${escapeHtml(article.title)}</span>`)}</article>`;
}

function fixedCard(article, variant = '') {
  const image = article.cover ? `<img src="${escapeHtml(coverUrl(article))}" alt="${escapeHtml(article.title)}" loading="lazy">` : '<span class="cover-missing">暂无封面</span>';
  return `<article class="fixed-card ${variant}">${articleLink(article, `<span class="fixed-card-cover">${image}</span><span class="fixed-card-name">${escapeHtml(article.title)}</span>`)}</article>`;
}

function sectionHeading(title, count, href = '') {
  return `<div class="section-heading"><h2>${title}</h2>${href ? `<a href="${href}">查看全部</a>` : `<span>${count}</span>`}</div>`;
}

function collectionTitle(article) {
  const title = article.metadata?.title;
  return title && title !== article.title ? `<p class="metadata-title">资料名称：${escapeHtml(title)}</p>` : '';
}

function shell(content, current = '') {
  return `<main>${content}</main>`;
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
  const writing = sortRecent(articles.filter((article) => ['article', 'essay'].includes(article.contentType)));
  const essays = writing.filter((article) => article.type === 'essay');
  const fullEssays = await Promise.all(essays.map(async (article) => {
    try {
      const response = await fetch(`/api/articles/${encodeURIComponent(article.slug)}`);
      return response.ok ? response.json() : null;
    } catch {
      return null;
    }
  }));
  const fullEssayBySlug = new Map(essays.map((article, index) => [article.slug, fullEssays[index]]));
  const photos = sortRecent(articles.filter((article) => article.contentType === 'photo'));
  const records = sortRecent(articles.filter((article) => article.contentType === 'record'));
  const feed = sortRecent(articles.filter((article) => ['article', 'essay', 'record'].includes(article.contentType)));
  const renderFeedCard = (article) => article.contentType === 'record'
    ? recordCard(article)
    : article.type === 'essay'
      ? essayCard(article, fullEssayBySlug.get(article.slug))
      : articleCard(article);
  const strip = photoStrip(photos);
  const feedCards = feed.map((article, index) => `${index === 2 ? strip : ''}${renderFeedCard(article)}`).join('');
  const content = feed.length >= 3 ? feedCards : `${feedCards}${strip}`;
  return shell(`<div class="home-flow"><section class="writing-section"><div class="writing-list">${content || strip}</div></section></div>`);
}

function renderArticle(article) {
  return shell(`<article class="reader"><a class="back-link" href="/">← 返回文章列表</a><h1>${escapeHtml(article.title)}</h1><div class="reader-body">${article.html}</div></article>`, '阅读');
}

function renderError(message) {
  return shell(`<section class="state"><h1>暂时无法打开</h1><p>${escapeHtml(message)}</p><a href="/">返回首页</a></section>`);
}

function syncRecordHeights() {
  document.querySelectorAll('.record-card').forEach((card) => {
    const image = card.querySelector('.record-cover img');
    const review = card.querySelector('.record-review');
    if (!image || !review) return;
    const update = () => {
      const height = image.getBoundingClientRect().height;
      if (height > 0) review.style.setProperty('--record-review-height', `${height}px`);
    };
    if (image.complete) update();
    else image.addEventListener('load', update, { once: true });
  });
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
      syncRecordHeights();
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

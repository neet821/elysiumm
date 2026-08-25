import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { BookOpen, Clapperboard, Disc3, Gamepad2, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { useHomeSidebar } from '../contexts/HomeSidebarContext.jsx'
import './contentHome.css'

const CATEGORY_LABELS = { article: '文章', essay: '随笔', photo: '照片', record: '记录' }
const RECORD_TYPES = {
  album: { label: '专辑', Icon: Disc3 },
  movie: { label: '电影', Icon: Clapperboard },
  game: { label: '游戏', Icon: Gamepad2 },
  book: { label: '书籍', Icon: BookOpen },
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? String(value)
    : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
}

function formatWritingDate(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? String(value)
    : new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'long', day: 'numeric' }).format(date)
}

function contentHref(item) {
  return `/content/${encodeURIComponent(item.contentType)}/${encodeURIComponent(item.slug)}`
}

function coverUrl(item) {
  if (!item.cover) return ''
  if (/^(?:https?:|data:|\/)/i.test(item.cover)) return item.cover
  return `/media/${encodeURIComponent(item.slug)}/${encodeURIComponent(item.cover)}`
}

const ARTICLES_PER_PAGE = 3
const ESSAY_COLLAPSE_THRESHOLD = 120

function articleType(item) {
  return item.type || (item.contentType === 'photo' ? 'image' : item.contentType)
}

function articleHref(item) {
  return `/article/${encodeURIComponent(item.slug)}`
}

function contentTextLength(value) {
  return String(value || '')
    .replace(/<[^>]*>/g, '')
    .replace(/[`*_#>\-[\]|]/g, '')
    .replace(/\s+/g, '')
    .length
}

async function enrichArticle(article) {
  if (!['movie', 'album', 'book', 'game'].includes(article.type) || article.cover || article.excerpt) return article
  try {
    const response = await fetch(`/api/metadata/search?type=${encodeURIComponent(article.type)}&q=${encodeURIComponent(article.title)}`)
    if (!response.ok) return article
    const result = (await response.json()).results?.[0]
    if (!result) return article
    return { ...article, cover: result.cover || article.cover, excerpt: result.description || article.excerpt, metadata: result }
  } catch {
    return article
  }
}

function metadataDetails(article) {
  const metadata = article.metadata
  if (!metadata) return null
  const fields = [
    metadata.year && <div key="year"><dt>年份</dt><dd>{metadata.year}</dd></div>,
    metadata.subtitle && <div key="subtitle"><dt>作者 / 艺术家</dt><dd>{metadata.subtitle}</dd></div>,
    metadata.rating && <div key="rating"><dt>评分</dt><dd>{metadata.rating}</dd></div>,
    metadata.genres?.length && <div key="genres"><dt>类型</dt><dd>{metadata.genres.join(' · ')}</dd></div>,
  ].filter(Boolean)
  return fields.length ? <dl className="metadata-details">{fields}</dl> : null
}

function collectionTitle(article) {
  const title = article.metadata?.title
  return title && title !== article.title ? <p className="metadata-title">资料名称：{title}</p> : null
}

function MarkdownContent({ markdown, html, fallback, className, id }) {
  return (
    <div className={className} id={id}>
      {html
          ? <div dangerouslySetInnerHTML={{ __html: html }} />
          : markdown
            ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
          : fallback
            ? <p>{fallback}</p>
            : null}
    </div>
  )
}

function RecordTypeIcon({ type }) {
  const recordType = RECORD_TYPES[type] || { label: '记录', Icon: BookOpen }
  const Icon = recordType.Icon
  return (
    <span className="record-type-icon" aria-label={`${recordType.label}类型`} title={recordType.label}>
      <Icon aria-hidden="true" size={15} strokeWidth={1.8} />
    </span>
  )
}

function LegacyArticleCard({ item }) {
  return (
    <article className="article-card article-card--featured">
      <div className="article-card-info">
        <h2><Link to={articleHref(item)}>{item.title}</Link></h2>
        {item.cover && <div className="article-card-cover article-card-cover--centered article-card-cover--compact"><img src={coverUrl(item)} alt={item.title} loading="lazy" /></div>}
        <div className="article-card-preview">
          {item.excerpt && <p>{item.excerpt}</p>}
          <time className="article-card-preview-time">{formatWritingDate(item.createdAt || item.date || item.updatedAt)}</time>
        </div>
      </div>
    </article>
  )
}

function LegacyEssayCard({ item, markdown, html }) {
  const [expanded, setExpanded] = useState(false)
  const bodyId = `essay-body-${item.slug.replace(/[^a-zA-Z0-9_-]/g, '-')}`
  const source = markdown || html || item.excerpt || ''
  const collapsible = contentTextLength(source) > ESSAY_COLLAPSE_THRESHOLD
  return (
    <article className={`essay-card essay-card--compact${collapsible ? ' essay-card--collapsible' : ''}${expanded ? ' is-expanded' : ''}`}>
      <h2>{item.title}</h2>
      <MarkdownContent markdown={markdown} html={html} fallback={item.excerpt} className="essay-body" id={bodyId} />
      {collapsible && (
        <button
          className="essay-toggle"
          type="button"
          aria-controls={bodyId}
          aria-expanded={expanded}
          aria-label={expanded ? '收起随笔' : '展开随笔'}
          onClick={() => setExpanded((value) => !value)}
        >
          <span className="essay-toggle-icon" aria-hidden="true">⌄</span>
        </button>
      )}
      <time className="card-time">{formatDate(item.createdAt || item.date || item.updatedAt)}</time>
    </article>
  )
}

function LegacyPhotoCard({ item }) {
  const image = item.cover ? <img src={coverUrl(item)} alt={item.title} loading="lazy" /> : null
  return (
    <article className="photo-card">
      {image ? <div className="photo-frame">{image}</div> : <div className="photo-frame" />}
      <h3>{item.title}</h3>
      <div className="photo-meta">{formatDate(item.date || item.createdAt || item.updatedAt)}{item.location ? ` · ${item.location}` : ''}</div>
    </article>
  )
}

function RecordCard({ item }) {
  const image = item.cover
    ? <img src={coverUrl(item)} alt={item.title} loading="lazy" />
    : <span className="cover-missing">暂无封面</span>
  const fields = [
    item.author && <div key="author"><dt>作者</dt><dd>{item.author}</dd></div>,
    item.year && <div key="year"><dt>年份</dt><dd>{item.year}</dd></div>,
    item.country && <div key="country"><dt>国家</dt><dd>{item.country}</dd></div>,
    item.language && <div key="language"><dt>语言</dt><dd>{item.language}</dd></div>,
  ].filter(Boolean)
  return (
    <article className="record-card record-card--priority">
      <div className="record-cover">{image}</div>
      <div className="record-info">
        <h2><RecordTypeIcon type={item.type} /><span>{item.title}</span></h2>
        {fields.length > 0 && <dl className="record-details">{fields}</dl>}
        {item.createdAt && <div className="record-added-time">添加时间：{formatDate(item.createdAt)}</div>}
        <div className="record-review"><span>个人评论：</span><span className="record-review-text">{item.review || '—'}</span></div>
      </div>
    </article>
  )
}

function PhotoStrip({ photos }) {
  return (
    <section className="photo-strip photo-strip--bottom">
      <div className="photo-strip-grid">
        {photos.length > 0
          ? photos.map((item) => <LegacyPhotoCard key={item.slug} item={item} />)
          : <p className="photo-strip-empty">还没有照片。</p>}
      </div>
    </section>
  )
}

export function ArticleFlowHome() {
  const [searchParams] = useSearchParams()
  const [articles, setArticles] = useState(null)
  const [fullEssays, setFullEssays] = useState({})
  const [error, setError] = useState('')
  const [homeLabel, setHomeLabel] = useState('')
  const { isOpen: homeSidebarOpen, close: closeHomeSidebar } = useHomeSidebar()

  useEffect(() => {
    let active = true
    fetch('/api/articles')
      .then((response) => { if (!response.ok) throw new Error('服务器没有返回文章。'); return response.json() })
      .then((data) => Promise.all((data.articles || []).map(enrichArticle)))
      .then((items) => { if (active) setArticles(items) })
      .catch((reason) => { if (active) setError(reason.message || '暂时无法打开') })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!articles) return undefined
    let active = true
    const essays = articles.filter((item) => articleType(item) === 'essay')
    Promise.all(essays.map(async (item) => {
      try {
        const response = await fetch(`/api/articles/${encodeURIComponent(item.slug)}`)
        return [item.slug, response.ok ? ((await response.json()).article || null) : null]
      } catch { return [item.slug, null] }
    })).then((entries) => { if (active) setFullEssays(Object.fromEntries(entries)) })
    return () => { active = false }
  }, [articles])

  useEffect(() => {
    if (!articles) return undefined
    let active = true
    fetch('/api/homepage')
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => { if (active) setHomeLabel(data?.settings?.hero_prefix || '') })
      .catch(() => {})
    return () => { active = false }
  }, [articles])

  const pageParam = searchParams.get('page') || '1'
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [pageParam])

  if (error) return <section className="state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (!articles) return <section className="state" aria-busy="true"><p>正在读取文章……</p></section>

  const sorted = [...articles].sort((a, b) => new Date(b.createdAt || b.date || b.updatedAt || 0) - new Date(a.createdAt || a.date || a.updatedAt || 0))
  const contentType = (item) => item.contentType || (articleType(item) === 'image' ? 'photo' : articleType(item))
  const fullEssayBySlug = fullEssays
  const articleItems = sorted.filter((item) => contentType(item) === 'article')
  const essays = sorted.filter((item) => contentType(item) === 'essay')
  const records = sorted.filter((item) => contentType(item) === 'record')
  const photos = sorted.filter((item) => contentType(item) === 'photo')
  const totalPages = Math.max(1, Math.ceil(articleItems.length / ARTICLES_PER_PAGE))
  const requestedPage = Number.parseInt(searchParams.get('page') || '1', 10)
  const currentPage = Number.isFinite(requestedPage) ? Math.min(Math.max(requestedPage, 1), totalPages) : 1
  const visibleArticles = articleItems.slice((currentPage - 1) * ARTICLES_PER_PAGE, currentPage * ARTICLES_PER_PAGE)
  const paginationItems = Array.from(new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1].filter((page) => page >= 1 && page <= totalPages))).sort((a, b) => a - b).reduce((items, page, index, pages) => {
    if (index > 0 && page - pages[index - 1] > 1) items.push(`ellipsis-${page}`)
    items.push(page)
    return items
  }, [])

  return (
    <div className="legacy-old-home legacy-old-home--flat">
      {homeLabel && <p className="home-custom-label">{homeLabel}</p>}
      {homeSidebarOpen && <button className="home-sidebar-backdrop" type="button" aria-label="关闭记录和随笔" onClick={closeHomeSidebar} />}
      <div className="home-layout">
        <main className="home-main">
          <section className="articles-section">
            <div className="writing-list">
              {visibleArticles.length > 0
                ? visibleArticles.map((item) => <LegacyArticleCard key={item.slug} item={item} />)
                : <p className="empty">还没有文章。</p>}
            </div>
            {totalPages > 1 && (
              <nav className="home-pagination" aria-label="文章分页">
                {currentPage > 1
                  ? <Link className="home-pagination__previous" to={`/?page=${currentPage - 1}`} rel="prev">上一页</Link>
                  : <span className="home-pagination__disabled" aria-disabled="true">上一页</span>}
                {paginationItems.map((item) => typeof item === 'number'
                  ? <Link key={item} aria-current={item === currentPage ? 'page' : undefined} to={`/?page=${item}`}>{item}</Link>
                  : <span className="home-pagination__ellipsis" key={item} aria-hidden="true">…</span>)}
                {currentPage < totalPages
                  ? <Link className="home-pagination__next" to={`/?page=${currentPage + 1}`} rel="next">下一页</Link>
                  : <span className="home-pagination__disabled" aria-disabled="true">下一页</span>}
              </nav>
            )}
          </section>
        </main>
        <aside
          className={`home-sidebar${homeSidebarOpen ? ' home-sidebar--drawer-open' : ''}`}
          id="home-sidebar"
          role={homeSidebarOpen ? 'dialog' : undefined}
          aria-modal={homeSidebarOpen ? 'true' : undefined}
          aria-label={homeSidebarOpen ? '记录和随笔' : undefined}
        >
          <header className="home-sidebar__drawer-header">
            <h2>记录和随笔</h2>
            <button className="home-sidebar__drawer-close" type="button" aria-label="关闭记录和随笔" onClick={closeHomeSidebar}><X size={18} aria-hidden="true" /></button>
          </header>
          <section className="sidebar-section sidebar-section--records sidebar-section--records-scroll">
            {records.length > 0
              ? records.map((item) => <RecordCard key={item.slug} item={item} />)
              : <p className="empty">还没有记录。</p>}
          </section>
          <section className="sidebar-section sidebar-section--essays">
            {essays.length > 0
              ? essays.map((item) => <LegacyEssayCard key={item.slug} item={item} markdown={fullEssayBySlug[item.slug]?.markdown} html={fullEssayBySlug[item.slug]?.html} />)
              : <p className="empty">还没有随笔。</p>}
          </section>
        </aside>
        <PhotoStrip photos={photos} />
      </div>
    </div>
  )
}

export function LegacyArticlePage() {
  const location = useLocation()
  const rawSlug = location.pathname.slice('/article/'.length)
  const [article, setArticle] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setArticle(null)
    setError('')
    fetch(`/api/articles/${rawSlug}`)
      .then((response) => { if (!response.ok) throw new Error(response.status === 404 ? '找不到这篇文章。' : '服务器没有返回文章。'); return response.json() })
      .then((data) => { if (active) setArticle(data.article || data) })
      .catch((reason) => { if (active) setError(reason.message || '暂时无法打开') })
    return () => { active = false }
  }, [rawSlug])

  if (error) return <section className="state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (!article) return <section className="state" aria-busy="true"><p>正在读取文章……</p></section>

  const cover = article.cover ? <img className="reader-cover" src={coverUrl(article)} alt={article.title} /> : null
  return (
    <div className="legacy-old-home">
      <article className="reader">
        <Link className="back-link" to="/" aria-label="返回首页" title="返回首页">←</Link>
        <header className="reader-header">
          <div className="article-meta">{formatDate(article.createdAt || article.date || article.updatedAt)}{article.category ? ` · ${article.category}` : ''}</div>
          {cover}
          <h1>{article.title}</h1>
          {collectionTitle(article)}
          {metadataDetails(article)}
          {article.excerpt && <p className="reader-excerpt">{article.excerpt}</p>}
        </header>
        <MarkdownContent markdown={article.markdown} html={article.html} className="reader-body" />
      </article>
    </div>
  )
}

function ContentCard({ item }) {
  return (
    <article className={`content-card content-card--${item.contentType || 'article'}`}>
      <Link to={contentHref(item)} className="content-card__link">
        <span className="content-card__cover">
          {item.cover ? <img src={coverUrl(item)} alt="" loading="lazy" /> : <span>暂无封面</span>}
        </span>
        <span className="content-card__body">
          <strong>{item.title}</strong>
          {(item.author || item.year || item.location) && <small>{[item.author, item.year, item.location].filter(Boolean).join(' · ')}</small>}
          {item.excerpt && <p>{item.excerpt}</p>}
        </span>
      </Link>
    </article>
  )
}

function CategoryNav({ categories }) {
  return (
    <nav className="content-nav" aria-label="内容分类">
      <Link to="/">全部</Link>
      {categories.map((category) => <Link key={category.id} to={`/content/${encodeURIComponent(category.id)}`}>{category.label} <span>{category.items.length}</span></Link>)}
    </nav>
  )
}

function ContentListing({ categories, categoryId }) {
  const category = categoryId ? categories.find((item) => item.id === categoryId) : null
  const sections = category ? [category] : categories
  if (categoryId && !category) throw new Error('找不到这个分类。')

  return (
    <>
      <header className="content-intro"><p className="content-kicker">Elysium · Obsidian</p><h1>{category?.label || '内容'}</h1><p>{category ? `${category.items.length} 条内容` : '从 Obsidian 同步的公开内容'}</p></header>
      <CategoryNav categories={categories} />
      <div className="content-flow">
        {sections.map((section) => (
          <section className="content-section" key={section.id}>
            {!category && <div className="content-section__heading"><h2>{section.label}</h2><Link to={`/content/${encodeURIComponent(section.id)}`}>查看全部 {section.items.length}</Link></div>}
            <div className={`content-grid content-grid--${section.id}`}>
              {section.items.length ? section.items.map((item) => <ContentCard item={item} key={`${item.contentType}-${item.slug}`} />) : <p className="content-empty">还没有内容。</p>}
            </div>
          </section>
        ))}
      </div>
    </>
  )
}

function ContentDetail({ article }) {
  const label = CATEGORY_LABELS[article.contentType] || article.contentType || ''
  return (
    <article className="content-reader">
      <Link className="content-reader__back" to={`/content/${encodeURIComponent(article.contentType)}`}>← 返回{label}</Link>
      <header className="content-reader__header">
        <div className="content-reader__meta">{formatDate(article.date || article.createdAt || article.updatedAt)}{label && ` · ${label}`}</div>
        {article.cover && <img className="content-reader__cover" src={coverUrl(article)} alt="" />}
        <h1>{article.title}</h1>
        {article.excerpt && <p>{article.excerpt}</p>}
      </header>
      <MarkdownContent markdown={article.markdown} html={article.html} className="content-reader__body" />
    </article>
  )
}

export default function ContentHomePage() {
  const location = useLocation()
  const [payload, setPayload] = useState(null)
  const [article, setArticle] = useState(null)
  const [error, setError] = useState('')

  const match = location.pathname.match(/^\/content\/([^/]+)(?:\/(.+))?$/)
  const categoryId = match?.[1] ? decodeURIComponent(match[1]) : null
  const articleSlug = match?.[2] ? decodeURIComponent(match[2]) : null

  useEffect(() => {
    let active = true
    setPayload(null)
    setArticle(null)
    setError('')
    const path = articleSlug
      ? `/api/content/${encodeURIComponent(categoryId)}/${encodeURIComponent(articleSlug)}`
      : '/api/content'
    fetch(path)
      .then((response) => { if (!response.ok) throw new Error(response.status === 404 ? '找不到这项内容。' : '服务器没有返回内容。'); return response.json() })
      .then((data) => { if (!active) return; if (articleSlug) setArticle(data.article); else setPayload(data) })
      .catch((reason) => { if (active) setError(reason.message || '暂时无法打开') })
    return () => { active = false }
  }, [categoryId, articleSlug])

  if (error) return <section className="content-state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (articleSlug && article) return <ContentDetail article={article} />
  if (!payload) return <section className="content-state" aria-busy="true"><p>正在载入内容…</p></section>
  return <ContentListing categories={payload.categories || []} categoryId={categoryId} />
}

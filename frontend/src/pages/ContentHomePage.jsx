import { Fragment, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import './contentHome.css'

const CATEGORY_LABELS = { article: '文章', essay: '随笔', photo: '照片', record: '记录' }

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

const COLLECTION_TYPES = ['album', 'movie', 'game', 'book']
const COLLECTION_LABELS = { album: '专辑', movie: '电影', game: '游戏', book: '书籍' }

function articleType(item) {
  return item.type || (item.contentType === 'photo' ? 'image' : item.contentType)
}

function articleHref(item) {
  return `/article/${encodeURIComponent(item.slug)}`
}

function articleLink(item, children) {
  return item.link === false ? children : <Link to={articleHref(item)}>{children}</Link>
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

function LegacyArticleCard({ item }) {
  return (
    <article className="article-card article-card--featured">
      <div className="article-card-info">
        <h2>{articleLink(item, item.title)}</h2>
        {item.cover && <Link className="article-card-cover article-card-cover--centered" to={articleHref(item)}><img src={coverUrl(item)} alt={item.title} loading="lazy" /></Link>}
        {item.excerpt && <p>{item.excerpt}</p>}
      </div>
      <time className="card-time">{formatWritingDate(item.createdAt || item.date || item.updatedAt)}</time>
    </article>
  )
}

function LegacyEssayCard({ item, html }) {
  return (
    <article className="essay-card essay-card--compact">
      <h2>{articleLink(item, item.title)}</h2>
      <div className="essay-body" dangerouslySetInnerHTML={{ __html: html || (item.excerpt ? `<p>${item.excerpt}</p>` : '') }} />
      <time className="card-time">{formatWritingDate(item.createdAt || item.date || item.updatedAt)}</time>
    </article>
  )
}

function LegacyPhotoCard({ item }) {
  const image = item.cover ? <img src={coverUrl(item)} alt={item.title} loading="lazy" /> : null
  return (
    <article className="photo-card">
      {image ? <a className="photo-frame" href={coverUrl(item)} target="_blank" rel="noreferrer">{image}</a> : <div className="photo-frame" />}
      <h3>{articleLink(item, item.title)}</h3>
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
    item.createdAt && <div key="createdAt"><dt>添加时间</dt><dd>{formatDate(item.createdAt)}</dd></div>,
  ].filter(Boolean)
  return (
    <article className="record-card record-card--priority">
      <div className="record-cover">{image}</div>
      <div className="record-info">
        <h2>{articleLink(item, item.title)}</h2>
        {fields.length > 0 && <dl className="record-details">{fields}</dl>}
        <div className="record-review"><span>个人评论：</span><span className="record-review-text">{item.review || '—'}</span></div>
      </div>
      <time className="card-time">{formatWritingDate(item.createdAt || item.date || item.updatedAt)}</time>
    </article>
  )
}

function PhotoStrip({ photos }) {
  return (
    <section className="photo-strip">
      <LegacySectionHeading title="照片" count={photos.length} />
      <div className="photo-strip-grid">
        {photos.length > 0
          ? photos.map((item) => <LegacyPhotoCard key={item.slug} item={item} />)
          : <p className="photo-strip-empty">还没有照片。</p>}
      </div>
    </section>
  )
}

function LegacyCollectionCard({ item }) {
  return (
    <article className="collection-card">
      {articleLink(item, <><span className="collection-cover">{item.cover ? <img src={coverUrl(item)} alt={item.title} loading="lazy" /> : <span className="cover-missing">暂无封面</span>}</span><span className="collection-name">{item.title}</span></>)}
    </article>
  )
}

function LegacySectionHeading({ title, count }) {
  return <div className="section-heading"><h2>{title}</h2><span>{count}</span></div>
}

export function ArticleFlowHome() {
  const [articles, setArticles] = useState(null)
  const [fullEssays, setFullEssays] = useState({})
  const [error, setError] = useState('')

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

  if (error) return <section className="state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (!articles) return <section className="state" aria-busy="true"><p>正在读取文章……</p></section>

  const sorted = [...articles].sort((a, b) => new Date(b.createdAt || b.date || b.updatedAt || 0) - new Date(a.createdAt || a.date || a.updatedAt || 0))
  const contentType = (item) => item.contentType || (articleType(item) === 'image' ? 'photo' : articleType(item))
  const essays = sorted.filter((item) => contentType(item) === 'essay')
  const fullEssayBySlug = fullEssays
  const photos = sorted.filter((item) => contentType(item) === 'photo')
  const feed = sorted.filter((item) => ['article', 'essay', 'record'].includes(contentType(item)))
  const strip = <PhotoStrip photos={photos} />

  return (
    <div className="legacy-old-home legacy-old-home--flat">
      <div className="home-flow">
        <section className="writing-section">
          <div className="writing-list">
            {feed.length > 0
              ? feed.map((item, index) => (
                <Fragment key={item.slug}>
                  {index === 2 && strip}
                  {contentType(item) === 'record'
                    ? <RecordCard item={item} />
                    : contentType(item) === 'essay'
                      ? <LegacyEssayCard item={item} html={fullEssayBySlug[item.slug]?.html} />
                      : <LegacyArticleCard item={item} />}
                </Fragment>
              ))
              : strip}
            {feed.length > 0 && feed.length < 3 && strip}
          </div>
        </section>
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
        <Link className="back-link" to="/">← 返回文章列表</Link>
        <header className="reader-header">
          <div className="article-meta">{formatDate(article.createdAt || article.date || article.updatedAt)}{article.category ? ` · ${article.category}` : ''}</div>
          {cover}
          <h1>{article.title}</h1>
          {collectionTitle(article)}
          {metadataDetails(article)}
          {article.excerpt && <p className="reader-excerpt">{article.excerpt}</p>}
        </header>
        <div className="reader-body" dangerouslySetInnerHTML={{ __html: article.html || '' }} />
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
      <div className="content-reader__body" dangerouslySetInnerHTML={{ __html: article.html || '' }} />
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

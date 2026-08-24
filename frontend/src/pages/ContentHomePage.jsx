import { useEffect, useState } from 'react'
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
  const type = item.contentType || item.category || (articleType(item) === 'image' ? 'photo' : articleType(item)) || 'article'
  return `/content/${encodeURIComponent(type)}/${encodeURIComponent(item.slug)}`
}

function articleLink(item, children) {
  return item.link === false ? children : <Link to={articleHref(item)}>{children}</Link>
}

function ArticleMeta({ item }) {
  return <div className="legacy-article-meta">{formatDate(item.createdAt || item.date || item.updatedAt)}</div>
}

function LegacyArticleCard({ item }) {
  return (
    <article className="legacy-article-card">
      {item.cover && <Link className="legacy-article-card__cover" to={articleHref(item)}><img src={coverUrl(item)} alt={item.title} loading="lazy" /></Link>}
      <div className="legacy-article-card__info">
        <ArticleMeta item={item} />
        <h2>{articleLink(item, item.title)}</h2>
        {item.excerpt && <p>{item.excerpt}</p>}
      </div>
    </article>
  )
}

function LegacyEssayCard({ item, html }) {
  return (
    <article className="legacy-essay-card">
      <ArticleMeta item={item} />
      <h2>{articleLink(item, item.title)}</h2>
      <div className="legacy-essay-card__body" dangerouslySetInnerHTML={{ __html: html || (item.excerpt ? `<p>${item.excerpt}</p>` : '') }} />
    </article>
  )
}

function LegacyPhotoCard({ item }) {
  const image = item.cover ? <img src={coverUrl(item)} alt={item.title} loading="lazy" /> : null
  return (
    <article className="legacy-photo-card">
      {item.link === false ? <div className="legacy-photo-card__frame">{image}</div> : <Link className="legacy-photo-card__frame" to={articleHref(item)}>{image}</Link>}
      <h3>{articleLink(item, item.title)}</h3>
    </article>
  )
}

function LegacyCollectionCard({ item }) {
  return (
    <article className="legacy-collection-card">
      {articleLink(item, <><span className="legacy-collection-card__cover">{item.cover ? <img src={coverUrl(item)} alt={item.title} loading="lazy" /> : <span>暂无封面</span>}</span><span className="legacy-collection-card__name">{item.title}</span></>)}
    </article>
  )
}

function LegacySectionHeading({ title, count }) {
  return <div className="legacy-section-heading"><h2>{title}</h2><span>{count}</span></div>
}

export function ArticleFlowHome() {
  const [articles, setArticles] = useState(null)
  const [fullEssays, setFullEssays] = useState({})
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    fetch('/api/articles')
      .then((response) => { if (!response.ok) throw new Error('服务器没有返回文章。'); return response.json() })
      .then((data) => { if (active) setArticles(data.articles || []) })
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

  if (error) return <section className="legacy-home-state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (!articles) return <section className="legacy-home-state" aria-busy="true"><p>正在读取文章……</p></section>

  const sorted = [...articles].sort((a, b) => new Date(b.createdAt || b.date || b.updatedAt || 0) - new Date(a.createdAt || a.date || a.updatedAt || 0))
  const writing = sorted.filter((item) => !COLLECTION_TYPES.includes(articleType(item)) && articleType(item) !== 'image' && item.contentType !== 'photo')
  const essays = writing.filter((item) => articleType(item) === 'essay')
  const articleNotes = writing.filter((item) => articleType(item) !== 'essay')
  const photos = sorted.filter((item) => articleType(item) === 'image' || item.contentType === 'photo')

  return (
    <div className="legacy-home-flow">
      <section className="legacy-writing-section">
        <div className="legacy-writing-list">
          {[...essays.map((item) => <LegacyEssayCard key={item.slug} item={item} html={fullEssays[item.slug]?.html} />), ...articleNotes.map((item) => <LegacyArticleCard key={item.slug} item={item} />)]}
          {!writing.length && <p className="legacy-empty">还没有文章。</p>}
        </div>
      </section>
      {!!photos.length && <section className="legacy-photos-section"><LegacySectionHeading title="照片" count={photos.length} /><div className="legacy-photo-grid">{photos.map((item) => <LegacyPhotoCard key={item.slug} item={item} />)}</div></section>}
      <section className="legacy-collections-grid">
        {COLLECTION_TYPES.map((type) => {
          const items = sorted.filter((item) => articleType(item) === type).slice(0, 2)
          return <section className="legacy-collection-section" key={type}><LegacySectionHeading title={COLLECTION_LABELS[type]} count={items.length} /><div className="legacy-collection-cards">{items.length ? items.map((item) => <LegacyCollectionCard key={item.slug} item={item} />) : <p className="legacy-empty">还没有记录。</p>}</div></section>
        })}
      </section>
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

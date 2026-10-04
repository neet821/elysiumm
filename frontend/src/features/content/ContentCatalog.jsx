import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { omitDuplicateHtmlTitle, omitDuplicateMarkdownTitle } from './readerTitle.js'

const CATEGORY_LABELS = {
  article: '文章',
  essay: '随笔',
  photo: '照片',
  record: '记录',
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? String(value)
    : new Intl.DateTimeFormat('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(date)
}

function contentHref(item) {
  return `/content/${encodeURIComponent(item.contentType)}/${encodeURIComponent(item.slug)}`
}

function coverUrl(item) {
  if (!item.cover) return ''
  if (/^(?:https?:|data:|\/)/i.test(item.cover)) return item.cover
  return `/media/${encodeURIComponent(item.slug)}/${encodeURIComponent(item.cover)}`
}

export function MarkdownContent({ markdown, html, fallback, className, id, omitLeadingTitle }) {
  return (
    <div className={className} id={id}>
      {html
        ? <div dangerouslySetInnerHTML={{ __html: omitDuplicateHtmlTitle(html, omitLeadingTitle) }} />
        : markdown
          ? <ReactMarkdown remarkPlugins={omitLeadingTitle ? [remarkGfm, omitDuplicateMarkdownTitle(omitLeadingTitle)] : [remarkGfm]}>{markdown}</ReactMarkdown>
          : fallback
            ? <p>{fallback}</p>
            : null}
    </div>
  )
}

function ContentCard({ item }) {
  return (
    <article className={`content-card content-card--${item.contentType || 'article'}`}>
      <Link to={contentHref(item)} className="content-card__link">
        <span className="content-card__cover">
          {item.cover
            ? <img src={coverUrl(item)} alt="" loading="lazy" />
            : <span>暂无封面</span>}
        </span>
        <span className="content-card__body">
          <strong>{item.title}</strong>
          {(item.author || item.year || item.location) && (
            <small>{[item.author, item.year, item.location].filter(Boolean).join(' · ')}</small>
          )}
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
      {categories.map((category) => (
        <Link key={category.id} to={`/content/${encodeURIComponent(category.id)}`}>
          {category.label} <span>{category.items.length}</span>
        </Link>
      ))}
    </nav>
  )
}

export function ContentListing({ categories, categoryId }) {
  const category = categoryId ? categories.find((item) => item.id === categoryId) : null
  const sections = category ? [category] : categories
  if (categoryId && !category) throw new Error('找不到这个分类。')

  return (
    <>
      <header className="content-intro">
        <p className="content-kicker">Obsidian</p>
        <h1>{category?.label || '内容'}</h1>
        <p>{category ? `${category.items.length} 条内容` : '从 Obsidian 同步的公开内容'}</p>
      </header>
      <CategoryNav categories={categories} />
      <div className="content-flow">
        {sections.map((section) => (
          <section className="content-section" key={section.id}>
            {!category && (
              <div className="content-section__heading">
                <h2>{section.label}</h2>
                <Link to={`/content/${encodeURIComponent(section.id)}`}>
                  查看全部 {section.items.length}
                </Link>
              </div>
            )}
            <div className={`content-grid content-grid--${section.id}`}>
              {section.items.length
                ? section.items.map((item) => (
                  <ContentCard item={item} key={`${item.contentType}-${item.slug}`} />
                ))
                : <p className="content-empty">还没有内容。</p>}
            </div>
          </section>
        ))}
      </div>
    </>
  )
}

export function ContentDetail({ article }) {
  const label = CATEGORY_LABELS[article.contentType] || article.contentType || ''

  return (
    <article className="content-reader">
      <Link className="content-reader__back" to={`/content/${encodeURIComponent(article.contentType)}`}>
        ← 返回{label}
      </Link>
      <header className="content-reader__header">
        <div className="content-reader__meta">
          {formatDate(article.date || article.createdAt || article.updatedAt)}
          {label && ` · ${label}`}
        </div>
        {article.cover && <img className="content-reader__cover" src={coverUrl(article)} alt="" />}
        <h1>{article.title}</h1>
        {article.excerpt && <p>{article.excerpt}</p>}
      </header>
      <MarkdownContent
        markdown={article.markdown}
        html={article.html}
        omitLeadingTitle={article.title}
        className="content-reader__body"
      />
    </article>
  )
}

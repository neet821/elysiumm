import { useCallback, useEffect, useMemo, useState } from 'react'
import { BookOpen, ExternalLink, Library, RotateCcw } from 'lucide-react'
import { Button, Card, EmptyState, Input, Skeleton, Tag } from '../components/ui/index.js'
import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

const STATUS_LABELS = {
  completed: '已读完',
  paused: '已暂停',
  reading: '阅读中',
  unread: '未开始',
}

const emptyCatalog = {
  books: [],
  lists: [],
  reader_available: false,
  recent: [],
}

const errorDetail = (error, fallback) => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  return fallback
}

function safeCoverUrl(value) {
  if (!value || typeof value !== 'string') return null
  if (value.startsWith('/') && !value.startsWith('//') && !value.includes('\\')) return value
  try {
    const parsed = new URL(value, window.location.origin)
    return parsed.origin === window.location.origin ? parsed.href : null
  } catch {
    return null
  }
}

function safeReaderUrl(value) {
  if (!value || typeof value !== 'string') return null
  try {
    const parsed = new URL(value)
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) return null
    return parsed.href
  } catch {
    return null
  }
}

function BookCard({ book, compact = false }) {
  const coverUrl = safeCoverUrl(book.cover_url)
  const readerUrl = safeReaderUrl(book.reader_url)
  return (
    <Card as="article" className={`books-card${compact ? ' books-card--compact' : ''}`}>
      <div className="books-card__cover" aria-hidden={coverUrl ? undefined : 'true'}>
        {coverUrl ? (
          <img src={coverUrl} alt={`${book.title}的封面`} loading="lazy" />
        ) : (
          <BookOpen size={compact ? 24 : 34} aria-hidden="true" />
        )}
      </div>
      <div className="books-card__body">
        <div className="books-card__meta">
          <span>{book.category || '未分类'}</span>
          <span>{STATUS_LABELS[book.reading_status] || book.reading_status}</span>
        </div>
        <h3>{book.title}</h3>
        {book.author && <p className="books-card__author">作者：{book.author}</p>}
        {!compact && book.description && <p className="books-card__description">{book.description}</p>}
        {!compact && book.tags?.length > 0 && (
          <div className="books-card__tags" aria-label={`${book.title}的标签`}>
            {book.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}
          </div>
        )}
        <div className="books-card__action">
          {readerUrl ? (
            <a
              className="ui-button ui-button--primary ui-button--sm"
              href={readerUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`在 Kavita 中阅读${book.title}`}
            >
              在 Kavita 中阅读 <ExternalLink size={14} aria-hidden="true" />
            </a>
          ) : (
            <span className="books-card__unavailable">阅读器暂不可用</span>
          )}
        </div>
      </div>
    </Card>
  )
}

export default function BooksPage() {
  const [catalog, setCatalog] = useState(emptyCatalog)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [status, setStatus] = useState('all')

  const loadCatalog = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.BOOKS)
      setCatalog({ ...emptyCatalog, ...response.data })
    } catch (requestError) {
      setError(errorDetail(requestError, '书籍暂时无法载入。'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadCatalog()
  }, [loadCatalog])

  const categories = useMemo(() => [...new Set(
    catalog.books.map((book) => book.category).filter(Boolean),
  )], [catalog.books])

  const filteredBooks = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    return catalog.books.filter((book) => {
      const searchable = [book.title, book.author, book.description, ...(book.tags || [])]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase()
      return (
        (!normalizedQuery || searchable.includes(normalizedQuery))
        && (category === 'all' || book.category === category)
        && (status === 'all' || book.reading_status === status)
      )
    })
  }, [catalog.books, category, query, status])

  const featured = filteredBooks.filter((book) => book.is_featured)

  return (
    <section className="route-shell books-route">
      <header className="route-shell__intro books-route__intro">
        <p className="route-shell__eyebrow"><Library size={15} aria-hidden="true" /> 阅读空间</p>
        <h1>书籍</h1>
        <p>这里是整理好的个人书架；Blue Album 负责收藏，Kavita 负责打开阅读。</p>
      </header>

      {!loading && !catalog.reader_available && (
        <p className="books-route__reader-note">Kavita 阅读器尚未配置。</p>
      )}

      {loading ? (
        <div className="books-route__loading" aria-label="正在载入书籍">
          <Skeleton className="books-route__skeleton" />
          <Skeleton className="books-route__skeleton" />
          <Skeleton className="books-route__skeleton" />
        </div>
      ) : error ? (
        <div className="books-route__error" role="alert">
          <p>{error}</p>
          <Button variant="secondary" onClick={loadCatalog}><RotateCcw size={15} aria-hidden="true" /> 重试</Button>
        </div>
      ) : catalog.books.length === 0 ? (
        <EmptyState
          className="books-route__empty"
          icon={<BookOpen size={38} />}
          title="暂时没有书籍"
          description="添加第一本书后，个人书架会显示在这里。"
        />
      ) : (
        <div className="books-route__workspace">
          <div className="books-route__filters" aria-label="书籍筛选">
            <Input
              label="搜索书籍"
              value={query}
              type="search"
              onChange={(event) => setQuery(event.target.value)}
            />
            <label className="ui-field">
              <span className="ui-field__label">分类</span>
              <select className="ui-input" value={category} onChange={(event) => setCategory(event.target.value)}>
                <option value="all">全部分类</option>
                {categories.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="ui-field">
              <span className="ui-field__label">阅读状态</span>
              <select className="ui-input" value={status} onChange={(event) => setStatus(event.target.value)}>
                <option value="all">全部状态</option>
                {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          </div>

          {featured.length > 0 && (
            <section className="books-shelf books-shelf--featured" aria-labelledby="books-featured-heading">
              <div className="books-shelf__heading">
                <p>精选书架</p>
                <h2 id="books-featured-heading">推荐阅读</h2>
              </div>
              <div className="books-grid books-grid--featured">
                {featured.map((book) => <BookCard key={book.id} book={book} />)}
              </div>
            </section>
          )}

          {catalog.recent.length > 0 && (
            <section className="books-shelf" aria-labelledby="books-recent-heading">
              <div className="books-shelf__heading">
                <p>继续阅读</p>
                <h2 id="books-recent-heading">最近阅读</h2>
              </div>
              <div className="books-grid books-grid--compact">
                {catalog.recent.map((book) => <BookCard key={book.id} book={book} compact />)}
              </div>
            </section>
          )}

          {catalog.lists.map((bookList) => (
            <section
              className="books-shelf books-list"
              data-testid={`book-list-${bookList.slug}`}
              key={bookList.id}
              aria-labelledby={`book-list-heading-${bookList.id}`}
            >
              <div className="books-shelf__heading">
                <p>阅读书单</p>
                <h2 id={`book-list-heading-${bookList.id}`}>{bookList.title}</h2>
                {bookList.description && <span>{bookList.description}</span>}
              </div>
              <div className="books-grid books-grid--compact">
                {bookList.books.map((book) => (
                  <div data-testid="book-list-item" key={book.id}><BookCard book={book} compact /></div>
                ))}
              </div>
            </section>
          ))}

          <section className="books-shelf" data-testid="all-books-shelf" aria-labelledby="all-books-heading">
            <div className="books-shelf__heading">
              <p>共 {filteredBooks.length} 本</p>
              <h2 id="all-books-heading">全部书籍</h2>
            </div>
            {filteredBooks.length > 0 ? (
              <div className="books-grid">
                {filteredBooks.map((book) => <BookCard key={book.id} book={book} />)}
              </div>
            ) : (
              <p className="books-route__no-match">没有符合当前条件的书籍。</p>
            )}
          </section>
        </div>
      )}
    </section>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Camera, MapPin, PenLine, Search } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { API_ENDPOINTS } from '../config.js'
import { Button, EmptyState, Input, Skeleton, Tag } from '../components/ui/index.js'
import apiClient from '../utils/request.js'

const PAGE_SIZE = 20
const ARCHIVE_TYPES = [
  { value: 'all', label: '全部' },
  { value: 'writing', label: '文章' },
  { value: 'essay', label: '随笔' },
  { value: 'photo', label: '照片' },
  { value: 'book', label: '书籍' },
  { value: 'album', label: '专辑' },
  { value: 'movie', label: '电影' },
  { value: 'game', label: '游戏' },
]

function positivePage(value) {
  const parsed = Number.parseInt(value || '1', 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
}

function errorMessage(error) {
  return error?.response?.data?.detail || error?.message || '归档暂时无法载入。'
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '日期未知'
  return new Intl.DateTimeFormat('zh-CN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

export default function ArchivePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedType = searchParams.get('type')
  const activeType = ['all', 'writing', 'essay', 'photo', 'book', 'album', 'movie', 'game'].includes(requestedType)
    ? requestedType
    : 'all'
  const query = (searchParams.get('q') || '').trim()
  const activeTag = (searchParams.get('tag') || '').trim()
  const year = searchParams.get('year') || ''
  const month = searchParams.get('month') || ''
  const page = positivePage(searchParams.get('page'))

  const [draftQuery, setDraftQuery] = useState(query)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryVersion, setRetryVersion] = useState(0)

  useEffect(() => {
    setDraftQuery(query)
  }, [query])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    const params = {
      type: activeType,
      q: query || undefined,
      tag: activeTag || undefined,
      skip: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    }
    if (year) params.year = year
    if (month) params.month = month
    apiClient.get(API_ENDPOINTS.ARCHIVE, {
      params,
    }).then((response) => {
      if (!active) return
      setItems(Array.isArray(response.data?.items) ? response.data.items : [])
      setTotal(Number(response.data?.total) || 0)
    }).catch((requestError) => {
      if (!active) return
      setError(errorMessage(requestError))
      setItems([])
      setTotal(0)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => {
      active = false
    }
  }, [activeTag, activeType, month, page, query, retryVersion, year])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const resultSummary = useMemo(() => {
    if (loading) return '正在载入归档'
    if (error) return '归档暂时不可用'
    return `共 ${total} 项`
  }, [error, loading, total])

  const updateFilters = (updates, { keepPage = false } = {}) => {
    const next = new URLSearchParams(searchParams)
    Object.entries(updates).forEach(([key, value]) => {
      if (value === '' || value === null || value === undefined) next.delete(key)
      else next.set(key, String(value))
    })
    if (!keepPage) next.delete('page')
    setSearchParams(next)
  }

  const submitSearch = (event) => {
    event.preventDefault()
    updateFilters({ q: draftQuery.trim() })
  }

  return (
    <section className="route-shell archive-route archive-page">
      <header className="route-shell__intro">
        <p className="route-shell__eyebrow">午夜归档</p>
        <h1>归档</h1>
        <p>所有公开内容，按时间收录在同一条时间线中。</p>
      </header>

      <div className="archive-page__workspace">
        <div className="archive-page__controls">
          <div className="archive-page__types" role="group" aria-label="归档类型">
            {ARCHIVE_TYPES.map((option) => (
              <button
                key={option.value}
                type="button"
                className={activeType === option.value ? 'is-active' : undefined}
                aria-pressed={activeType === option.value}
                onClick={() => updateFilters({ type: option.value })}
              >
                {option.label}
              </button>
            ))}
          </div>

          <form className="archive-page__search" onSubmit={submitSearch}>
            <Input
              label="搜索归档"
              value={draftQuery}
              maxLength={200}
              onChange={(event) => setDraftQuery(event.target.value)}
              placeholder="标题、说明、地点或标签"
            />
            <Button type="submit" variant="secondary">
              <Search size={16} aria-hidden="true" />
              搜索
            </Button>
          </form>

          <div className="archive-page__status" aria-live="polite">
            <span>{resultSummary}</span>
            {activeTag && (
              <button
                type="button"
                className="archive-page__active-tag"
                onClick={() => updateFilters({ tag: '' })}
              >
                标签：{activeTag} <span aria-hidden="true">×</span>
              </button>
            )}
          </div>
        </div>

        {loading && (
          <div className="archive-page__loading" aria-label="正在载入归档内容">
            {[0, 1, 2].map((item) => (
              <Skeleton key={item} className="archive-page__skeleton" />
            ))}
          </div>
        )}

        {!loading && error && (
          <div className="archive-page__error" role="alert">
            <p>{error}</p>
            <Button variant="secondary" onClick={() => setRetryVersion((value) => value + 1)}>
              重试
            </Button>
          </div>
        )}

        {!loading && !error && items.length === 0 && (
          <EmptyState
            className="archive-page__empty"
            icon="⌁"
            title="没有符合筛选条件的内容"
            description="请更换类型或搜索词，也可以移除当前标签。"
          />
        )}

        {!loading && !error && items.length > 0 && (
          <ol className="archive-timeline">
            {items.map((item) => (
              <li
                key={item.id}
                className={`archive-entry archive-entry--${item.type}`}
                data-testid="archive-item"
              >
                <article>
                  {item.image_url && (
                    <div className="archive-entry__image-wrap">
                      <img
                        className="archive-entry__image"
                        src={item.image_url}
                        alt={item.title}
                        loading="lazy"
                      />
                    </div>
                  )}
                  <div className="archive-entry__body">
                    <div className="archive-entry__meta">
                      <span className="archive-entry__kind">
                        {['writing', 'article', 'essay'].includes(item.type)
                          ? <PenLine size={15} aria-hidden="true" />
                          : <Camera size={15} aria-hidden="true" />}
                        {item.content_type === 'essay' || item.type === 'essay'
                          ? '随笔'
                          : ({ writing: '文章', article: '文章', photo: '照片', book: '书籍', album: '专辑', movie: '电影', game: '游戏' }[item.type] || '内容')}
                      </span>
                      <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
                    </div>
                    <h2>
                      {item.href
                        ? <Link to={item.href}>{item.title}</Link>
                        : item.title}
                    </h2>
                    {item.excerpt && <p className="archive-entry__excerpt">{item.excerpt}</p>}
                    <div className="archive-entry__details">
                      {item.category && <span>{item.category}</span>}
                      {item.author_name && <span>作者：{item.author_name}</span>}
                      {item.location && (
                        <span><MapPin size={14} aria-hidden="true" />{item.location}</span>
                      )}
                    </div>
                    {item.tags?.length > 0 && (
                      <div className="archive-entry__tags" aria-label={`${item.title} 的标签`}>
                        {item.tags.map((tag) => (
                          <button
                            key={tag}
                            type="button"
                            aria-label={`按 ${tag} 筛选`}
                            onClick={() => updateFilters({ tag })}
                          >
                            <Tag tone={item.type === 'photo' ? 'success' : 'info'}>{tag}</Tag>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </article>
              </li>
            ))}
          </ol>
        )}

        {!loading && !error && total > 0 && (
          <nav className="archive-page__pagination" aria-label="归档分页">
            <Button
              variant="ghost"
              disabled={page <= 1}
              onClick={() => updateFilters({ page: page - 1 }, { keepPage: true })}
            >
              上一页
            </Button>
            <span>第 {page} 页，共 {pageCount} 页</span>
            <Button
              variant="ghost"
              disabled={page >= pageCount}
              onClick={() => updateFilters({ page: page + 1 }, { keepPage: true })}
            >
              下一页
            </Button>
          </nav>
        )}
      </div>
    </section>
  )
}

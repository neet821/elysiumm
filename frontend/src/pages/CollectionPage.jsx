import { Bookmark, ExternalLink, Folder, Search, Star } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { API_ENDPOINTS } from '../config.js'
import { Button, Card, EmptyState, Input, Skeleton, Tag } from '../components/ui/index.js'
import apiClient from '../utils/request.js'

function positiveIdentifier(value) {
  const parsed = Number.parseInt(value || '', 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function requestErrorMessage(error) {
  return error?.response?.data?.detail || error?.message || '公开收藏暂时无法载入。'
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

export default function CollectionPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const query = (searchParams.get('q') || '').trim()
  const folderId = positiveIdentifier(searchParams.get('folder'))
  const [draftQuery, setDraftQuery] = useState(query)
  const [bookmarks, setBookmarks] = useState([])
  const [folders, setFolders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryVersion, setRetryVersion] = useState(0)

  useEffect(() => setDraftQuery(query), [query])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    apiClient.get(API_ENDPOINTS.PUBLIC_COLLECTION, {
      params: {
        q: query || undefined,
        folder_id: folderId || undefined,
        limit: 100,
      },
    }).then((response) => {
      if (!active) return
      setBookmarks(Array.isArray(response.data?.bookmarks) ? response.data.bookmarks : [])
      setFolders(Array.isArray(response.data?.folders) ? response.data.folders : [])
    }).catch((requestError) => {
      if (!active) return
      setError(requestErrorMessage(requestError))
      setBookmarks([])
      setFolders([])
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => {
      active = false
    }
  }, [folderId, query, retryVersion])

  const updateFilters = (updates) => {
    const next = new URLSearchParams(searchParams)
    Object.entries(updates).forEach(([key, value]) => {
      if (value === '' || value === null || value === undefined) next.delete(key)
      else next.set(key, String(value))
    })
    setSearchParams(next)
  }

  const submitSearch = (event) => {
    event.preventDefault()
    updateFilters({ q: draftQuery.trim() })
  }

  return (
    <section className="route-shell collection-route public-collection">
      <header className="route-shell__intro public-collection__intro">
        <div>
          <p className="route-shell__eyebrow">公开精选</p>
          <h1>收藏</h1>
          <p>这里仅展示主动公开分享的内容，私密文件夹绝不会出现。</p>
        </div>
        <Link className="public-collection__manage" to="/account/collection">
          管理我的私人收藏
        </Link>
      </header>

      <div className="public-collection__workspace">
        <form className="public-collection__search" onSubmit={submitSearch}>
          <Input
            label="搜索公开收藏"
            value={draftQuery}
            maxLength={200}
            onChange={(event) => setDraftQuery(event.target.value)}
            placeholder="搜索标题、描述、网址或标签"
          />
          <Button type="submit" variant="secondary">
            <Search size={16} aria-hidden="true" /> 搜索
          </Button>
        </form>

        <nav className="public-collection__folders" aria-label="公开收藏文件夹">
          <button
            type="button"
            className={!folderId ? 'is-active' : undefined}
            aria-pressed={!folderId}
            onClick={() => updateFilters({ folder: '' })}
          >
            <Bookmark size={15} aria-hidden="true" /> 全部收藏
          </button>
          {folders.map((folder) => (
            <button
              key={folder.id}
              type="button"
              className={folderId === folder.id ? 'is-active' : undefined}
              aria-pressed={folderId === folder.id}
              onClick={() => updateFilters({ folder: folder.id })}
            >
              <Folder size={15} aria-hidden="true" /> {folder.name}
            </button>
          ))}
        </nav>

        {loading && (
          <div className="public-collection__loading" aria-label="正在载入公开收藏">
            {[0, 1, 2].map((item) => <Skeleton key={item} className="public-collection__skeleton" />)}
          </div>
        )}

        {!loading && error && (
          <div className="public-collection__error" role="alert">
            <p>{error}</p>
            <Button variant="secondary" onClick={() => setRetryVersion((value) => value + 1)}>
              重试
            </Button>
          </div>
        )}

        {!loading && !error && bookmarks.length === 0 && (
          <EmptyState
            className="public-collection__empty"
            icon={<Bookmark size={34} />}
            title="没有符合筛选条件的公开收藏"
            description="请更换文件夹或搜索词；私人收藏仍会保持私密。"
          />
        )}

        {!loading && !error && bookmarks.length > 0 && (
          <div className="public-collection__grid">
            {bookmarks.map((bookmark) => (
              <Card key={bookmark.id} as="article" className="public-bookmark-card">
                {bookmark.preview_url && (
                  <img
                    className="public-bookmark-card__preview"
                    src={bookmark.preview_url}
                    alt={`${bookmark.title} 的预览图`}
                    loading="lazy"
                  />
                )}
                <div className="public-bookmark-card__body">
                  <div className="public-bookmark-card__meta">
                    <span>{bookmark.folder?.name || '公开收藏'}</span>
                    <time dateTime={bookmark.created_at}>{formatDate(bookmark.created_at)}</time>
                  </div>
                  <h2>
                    <a href={bookmark.url} target="_blank" rel="noopener noreferrer">
                      {bookmark.is_pinned && <Star size={16} fill="currentColor" aria-label="精选" />}
                      {bookmark.title}
                      <ExternalLink size={15} aria-hidden="true" />
                    </a>
                  </h2>
                  {bookmark.description && <p>{bookmark.description}</p>}
                  <div className="public-bookmark-card__footer">
                    <div className="public-bookmark-card__tags">
                      {bookmark.tags?.map((tag) => <Tag key={tag} tone="info">{tag}</Tag>)}
                    </div>
                    {bookmark.visit_count !== null && bookmark.visit_count !== undefined && (
                      <span>访问 {bookmark.visit_count} 次</span>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

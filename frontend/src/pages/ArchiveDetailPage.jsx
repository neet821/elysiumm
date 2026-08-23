import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

const LABELS = { book: '书籍', album: '专辑', movie: '电影', game: '游戏', photo: '照片' }

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long' }).format(date)
}

export default function ArchiveDetailPage() {
  const { type, id } = useParams()
  const [item, setItem] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const endpoint = type === 'photo' ? API_ENDPOINTS.PHOTO_DETAIL(id) : API_ENDPOINTS.MEDIA_DETAIL(type, id)
    apiClient.get(endpoint).then(({ data }) => {
      setItem(type === 'photo' ? {
        kind: 'photo',
        title: data.caption || data.location || '照片',
        cover_url: data.url,
        summary: data.caption,
        creator: data.location,
        activity_at: data.created_at,
        tags: data.tags?.map((tag) => tag.name || tag) || [],
      } : data)
    }).catch(() => setError('内容不存在或暂未公开。'))
  }, [id, type])

  if (error) return <section className="route-shell archive-detail"><p role="alert">{error}</p><Link to="/archive">返回归档</Link></section>
  if (!item) return <section className="route-shell archive-detail" aria-busy="true"><p>正在载入…</p></section>
  return (
    <article className="route-shell archive-detail">
      <Link className="archive-detail__back" to="/archive">← 返回归档</Link>
      <header className="archive-detail__header">
        {item.cover_url && <img src={item.cover_url} alt={item.title} />}
        <div><p className="route-shell__eyebrow">{LABELS[item.kind] || item.kind}</p><h1>{item.title}</h1>{item.creator && <p>{item.creator}</p>}{item.year && <time dateTime={String(item.year)}>{item.year}</time>}</div>
      </header>
      {item.summary && <p className="archive-detail__summary">{item.summary}</p>}
      {item.activity_at && <p className="archive-detail__meta">记录于 {formatDate(item.activity_at)}</p>}
      {item.tags?.length > 0 && <div className="archive-detail__tags">{item.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
    </article>
  )
}

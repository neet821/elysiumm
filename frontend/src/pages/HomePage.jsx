import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { API_ENDPOINTS } from '../config.js'
import { useAuth } from '../contexts/AuthContext.jsx'
import apiClient from '../utils/request.js'
import './flatHome.css'

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
}

function excerpt(value, limit = 130) {
  const text = String(value || '').replace(/[#*_>`]/g, '').replace(/\s+/g, ' ').trim()
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text
}

function FlatPlayer({ tracks = [] }) {
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const track = tracks[index]
  const audioUrl = track?.audio_url || track?.playback_url

  useEffect(() => setPlaying(false), [audioUrl])

  return (
    <section className="flat-player" aria-label="首页播放器">
      <div className="flat-player__label">正在播放</div>
      <div className="flat-player__main">
        {track?.cover_url ? <img src={track.cover_url} alt="" className="flat-player__cover" /> : <div className="flat-player__cover flat-player__cover--empty" aria-hidden="true" />}
        <div className="flat-player__track">
          <strong>{track?.title || '尚未选择歌曲'}</strong>
          <span>{track?.artist || track?.creator || (track ? '未知艺术家' : '管理员可以在后台选择歌曲')}</span>
        </div>
        <button className="flat-player__button" type="button" disabled={!audioUrl} onClick={() => setPlaying((value) => !value)}>
          {playing ? '暂停' : '播放'}
        </button>
        <div className="flat-player__actions">
          <button type="button" disabled={index === 0} onClick={() => setIndex((value) => Math.max(0, value - 1))}>上一首</button>
          <button type="button" disabled={index >= tracks.length - 1} onClick={() => setIndex((value) => Math.min(tracks.length - 1, value + 1))}>下一首</button>
        </div>
      </div>
      {playing && audioUrl && <audio autoPlay controls src={audioUrl} onEnded={() => setPlaying(false)} />}
    </section>
  )
}

function FlatMessages({ messages = [] }) {
  const { isAuthenticated } = useAuth() || {}
  const [content, setContent] = useState('')
  const [items, setItems] = useState(messages.slice(0, 3))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => setItems(messages.slice(0, 3)), [messages])

  async function submit(event) {
    event.preventDefault()
    const value = content.trim()
    if (!value || saving) return
    setSaving(true)
    setError('')
    try {
      const response = await apiClient.post(API_ENDPOINTS.MESSAGE_BOARD, { content: value })
      setItems((current) => [{ ...response.data }, ...current].slice(0, 3))
      setContent('')
    } catch {
      setError('留言暂时无法发布。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="flat-panel flat-messages" id="messages" aria-label="留言板">
      <div className="flat-section-heading"><h2>留言板</h2><Link to="/messages">查看全部</Link></div>
      <div className="flat-messages__list">
        {items.length ? items.map((message) => (
          <article key={message.id} className="flat-message">
            <p>{message.content}</p>
            <small>{message.user?.username || '访客'} · {formatDate(message.created_at)}</small>
          </article>
        )) : <p className="flat-muted">还没有留言。</p>}
      </div>
      {isAuthenticated ? (
        <form onSubmit={submit} className="flat-message-form">
          <label htmlFor="homepage-message">写下留言</label>
          <textarea id="homepage-message" aria-label="写下留言" rows="2" maxLength="500" value={content} onChange={(event) => setContent(event.target.value)} />
          {error && <p className="flat-inline-error" role="alert">{error}</p>}
          <button type="submit" disabled={!content.trim() || saving}>{saving ? '发布中' : '发布留言'}</button>
        </form>
      ) : <Link className="flat-text-link" to="/login?next=%2F%23messages">登录后留言</Link>}
    </section>
  )
}

function WritingList({ posts = [] }) {
  return (
    <section className="flat-panel flat-writing">
      <div className="flat-section-heading"><h2>最近写下</h2><Link to="/archive?type=writing">查看完整归档</Link></div>
      <div className="flat-writing__list">
        {posts.length ? posts.slice(0, 5).map((post) => (
          <article className="flat-writing__item" key={post.id}>
            <div><span className="flat-kind">{post.type === 'essay' ? '随笔' : '文章'}</span><time dateTime={post.created_at}>{formatDate(post.created_at)}</time></div>
            <h3><Link to={post.href || `/posts/${post.slug || post.id}`}>{post.title}</Link></h3>
            <p>{excerpt(post.excerpt || post.content)}</p>
          </article>
        )) : <p className="flat-muted">还没有公开文字。</p>}
      </div>
    </section>
  )
}

function PhotoGrid({ photos = [] }) {
  return (
    <section className="flat-panel flat-photos">
      <div className="flat-section-heading"><h2>最近照片</h2><Link to="/archive?type=photo">查看完整归档</Link></div>
      {photos.length ? <div className="flat-photos__grid">{photos.slice(0, 6).map((photo) => <Link key={photo.id} to={photo.href || `/archive/photo/${photo.id}`} className="flat-photo"><img src={photo.url || photo.image_url} alt={photo.caption || photo.title || '照片'} loading="lazy" /><span>{photo.caption || photo.title}</span></Link>)}</div> : <p className="flat-muted">还没有公开照片。</p>}
    </section>
  )
}

function Activity({ homepage }) {
  const activities = useMemo(() => {
    if (Array.isArray(homepage.activities)) return homepage.activities
    return (homepage.scenes || []).flatMap((scene) => scene.media || []).slice(0, 5)
  }, [homepage])
  return (
    <section className="flat-panel flat-activity">
      <div className="flat-section-heading"><h2>最近动态</h2><Link to="/archive">完整归档</Link></div>
      {activities.length ? activities.slice(0, 5).map((item) => <div className="flat-activity__item" key={`${item.kind || item.type}-${item.id}`}><span>{item.kind === 'book' ? '读书' : item.kind === 'album' ? '听歌' : item.kind === 'movie' ? '观影' : '游戏'}</span><strong>{item.title || item.name}</strong><time>{formatDate(item.activity_at || item.created_at)}</time></div>) : <p className="flat-muted">还没有最近动态。</p>}
    </section>
  )
}

export default function HomePage() {
  const [homepage, setHomepage] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiClient.get(API_ENDPOINTS.HOMEPAGE)
      .then(({ data }) => setHomepage(data || {}))
      .catch(() => setError('首页暂时无法载入。'))
  }, [])

  if (error) return <section className="flat-home flat-home--error"><p role="alert">{error}</p></section>
  if (!homepage) return <section className="flat-home" aria-busy="true"><p className="flat-muted">正在载入…</p></section>

  const settings = homepage.settings || {}
  return (
    <div className="flat-home">
      <FlatPlayer tracks={homepage.player_tracks || homepage.tracks || []} />
      <section className="flat-intro"><h1>你好。</h1><p>{settings.introduction || '记录想法与生活，收藏热爱与灵感。'}</p></section>
      <div className="flat-main-grid"><WritingList posts={homepage.posts} /><PhotoGrid photos={homepage.photos} /></div>
      <div className="flat-support-grid"><Activity homepage={homepage} /><FlatMessages messages={homepage.messages} /></div>
      <div className="flat-archive-link"><Link to="/rooms/watch">进入观影房</Link></div>
      <div className="flat-archive-link"><Link to="/archive">进入完整归档 →</Link></div>
    </div>
  )
}

import { Archive, ArrowUpRight, Bookmark, Camera, Clock3, MapPin, Radio } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card, Tag } from '../ui/index.js'
import { getImageUrl } from '../../utils/imageHelper.js'

const tagClass = (name) => {
  const normalized = String(name || '').toLocaleLowerCase()
  const supported = ['photography', 'diary', 'technology', 'music', 'private', 'featured', 'location']
  const semantic = supported.find((value) => normalized.includes(value)) || 'neutral'
  return `home-tag--${semantic}`
}

export function HomeTagList({ tags = [] }) {
  const visible = tags.slice(0, 3)
  const remainder = Math.max(0, tags.length - visible.length)
  if (!visible.length) return null

  return (
    <div className="home-card__tags" aria-label="标签">
      {visible.map((tag) => {
        const name = typeof tag === 'string' ? tag : tag.name
        return <Tag className={tagClass(name)} key={name}>{name}</Tag>
      })}
      {remainder > 0 && <Tag className="home-tag--remainder">+{remainder}</Tag>}
    </div>
  )
}

export function HomeIndexCard({ postCount, photoCount }) {
  return (
    <Card as="section" className="home-index-card" aria-labelledby="home-index-title">
      <header className="home-card__header">
        <span className="home-card__eyebrow"><Archive size={14} aria-hidden="true" /> 目录</span>
        <h2 id="home-index-title">索引</h2>
      </header>
      <nav className="home-index-card__links" aria-label="首页索引">
        <Link to="/archive?type=writing"><span>文章</span><strong>{postCount}</strong></Link>
        <Link to="/archive?type=photo"><span>照片</span><strong>{photoCount}</strong></Link>
        <Link to="/collection"><span>收藏</span><strong>查看</strong></Link>
        <Link to="/account"><span>愿望</span><strong>账户</strong></Link>
      </nav>
    </Card>
  )
}

export function HomeWritingCard({ posts = [] }) {
  return (
    <Card as="section" className="home-writing-card" aria-labelledby="home-writing-title">
      <header className="home-card__header home-card__header--row">
        <div>
          <span className="home-card__eyebrow">精选文章</span>
          <h2 id="home-writing-title">随手札记</h2>
        </div>
        <Link className="home-card__icon-link" to="/archive?type=writing" aria-label="查看全部文章">
          <ArrowUpRight size={18} aria-hidden="true" />
        </Link>
      </header>
      {posts.length ? (
        <div className="home-writing-card__list">
          {posts.slice(0, 2).map((post) => (
            <article key={post.id}>
              <p className="home-card__meta">{post.category || '文章'}</p>
              <h3><Link to={`/posts/${post.slug || post.id}`}>{post.title}</Link></h3>
              {post.content && <p className="home-writing-card__excerpt">{post.content}</p>}
              <HomeTagList tags={post.tags} />
            </article>
          ))}
        </div>
      ) : (
        <p className="home-card__empty">暂时还没有选入首页的公开文章。</p>
      )}
    </Card>
  )
}

export function HomePhotoCard({ photos = [], onSelectPhoto }) {
  const photo = photos[0]
  return (
    <Card as="section" className="home-photo-card" aria-labelledby="home-photo-title">
      <header className="home-card__header home-card__header--row">
        <div>
          <span className="home-card__eyebrow"><Camera size={14} aria-hidden="true" /> 摄影</span>
          <h2 id="home-photo-title">蓝调时刻</h2>
        </div>
        <Link className="home-card__icon-link" to="/archive?type=photo" aria-label="查看全部照片">
          <ArrowUpRight size={18} aria-hidden="true" />
        </Link>
      </header>
      {photo ? (
        <>
          <button
            type="button"
            className="home-photo-card__media"
            aria-label={`查看照片 ${photo.caption || photo.id}`}
            onClick={() => onSelectPhoto?.(photo)}
          >
            <img
              className="home-photo-card__image"
              src={getImageUrl(photo.url)}
              alt={photo.caption || '精选照片'}
              loading="lazy"
            />
          </button>
          <div className="home-photo-card__caption">
            <span>{photo.caption || '未命名照片'}</span>
            {photo.location && <span><MapPin size={13} aria-hidden="true" />{photo.location}</span>}
          </div>
          <HomeTagList tags={photo.tags?.length ? photo.tags : [{ name: 'photography' }]} />
        </>
      ) : (
        <p className="home-card__empty">暂时还没有选入首页的照片。</p>
      )}
    </Card>
  )
}

export function HomeCollectionCard({ collections = [] }) {
  return (
    <Card as="section" className="home-collection-card" aria-labelledby="home-collection-title">
      <header className="home-card__header">
        <span className="home-card__eyebrow"><Bookmark size={14} aria-hidden="true" /> 公开收藏</span>
        <h2 id="home-collection-title">收藏地点</h2>
      </header>
      {collections.length ? (
        <p>已有 {collections.length} 条公开收藏可以浏览。</p>
      ) : (
        <p className="home-card__empty">暂时没有公开收藏，私人书签仍只对自己可见。</p>
      )}
      <Link className="home-card__link" to="/collection">打开收藏</Link>
    </Card>
  )
}

export function HomeHistoryCard() {
  return (
    <Card as="section" className="home-history-card" aria-labelledby="home-history-title">
      <header className="home-card__header">
        <span className="home-card__eyebrow"><Clock3 size={14} aria-hidden="true" /> 历史上的今天</span>
        <h2 id="home-history-title">相册旧事</h2>
      </header>
      <p className="home-card__empty">今天还没有选中的往日记录。</p>
    </Card>
  )
}

export function HomeQuoteCard({ quote }) {
  return (
    <Card as="blockquote" className="home-quote-card">
      <p>{quote || '给未完成的片段留一个安静的位置。'}</p>
      <footer>Blue Album 便签</footer>
    </Card>
  )
}

export function HomeStatusCard() {
  return (
    <Card as="section" className="home-status-card" aria-labelledby="home-status-title">
      <header className="home-card__header">
        <span className="home-card__eyebrow"><Radio size={14} aria-hidden="true" /> 当前状态</span>
        <h2 id="home-status-title">房间</h2>
      </header>
      <p className="home-card__empty">登录后可以查看实时房间状态。</p>
      <Link className="home-card__link" to="/music">打开听歌房</Link>
    </Card>
  )
}

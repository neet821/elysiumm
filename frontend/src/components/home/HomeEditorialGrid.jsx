import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  HomeCollectionCard,
  HomeHistoryCard,
  HomeIndexCard,
  HomeQuoteCard,
  HomeStatusCard,
  HomeTagList,
} from './HomeCards.jsx'
import MessageBoardCard from './MessageBoardCard.jsx'
import { getImageUrl } from '../../utils/imageHelper.js'

function plainExcerpt(value) {
  const text = String(value || '暂无正文。')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[#>*_`~-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return text.length > 420 ? `${text.slice(0, 420).trim()}…` : text
}

function interleaveContent(posts, photos) {
  const content = []
  const maximum = Math.max(posts.length, photos.length)
  for (let index = 0; index < maximum; index += 1) {
    if (posts[index]) content.push({ kind: 'post', key: `post-${posts[index].id}`, value: posts[index] })
    if (photos[index]) content.push({ kind: 'photo', key: `photo-${photos[index].id}`, value: photos[index] })
  }
  return content
}

function configuredItems(homepage) {
  const { settings, posts, photos } = homepage
  const mixed = interleaveContent(posts, photos)
  let contentAdded = false
  const items = []

  settings.cards.forEach((card) => {
    if (card.id === 'writing' || card.id === 'photography') {
      if (!contentAdded) items.push(...mixed)
      contentAdded = true
      return
    }
    if (card.id === 'messages' && !settings.show_messages) return
    if (card.id === 'history' && !settings.show_history) return
    items.push({ kind: card.id, key: `module-${card.id}`, value: card })
  })

  if (!contentAdded) items.unshift(...mixed)
  return items
}

function useMasonryMeasurement(ref) {
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return undefined

    const measure = () => {
      const styles = globalThis.getComputedStyle?.(element.parentElement)
      const row = Number.parseFloat(styles?.gridAutoRows || '8') || 8
      const gap = Number.parseFloat(styles?.rowGap || '16') || 16
      const height = element.getBoundingClientRect().height
      element.style.setProperty('--masonry-row-span', String(Math.max(1, Math.ceil((height + gap) / (row + gap)))))
    }

    measure()
    if (typeof globalThis.ResizeObserver !== 'function') return undefined
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
}

function useReveal(ref, revealEnabled) {
  useEffect(() => {
    const element = ref.current
    if (!element) return undefined
    if (!revealEnabled) {
      element.dataset.revealed = 'false'
      return undefined
    }
    if (typeof globalThis.IntersectionObserver !== 'function') {
      element.dataset.revealed = 'true'
      return undefined
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting || !revealEnabled) return
      element.dataset.revealed = 'true'
      observer.disconnect()
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref, revealEnabled])
}

function MasonryItem({ item, index, children, revealEnabled }) {
  const ref = useRef(null)
  useMasonryMeasurement(ref)
  useReveal(ref, revealEnabled)
  const isPhoto = item.kind === 'photo'
  return (
    <article
      ref={ref}
      className={`home-masonry-item ${isPhoto ? 'home-masonry-item--photo' : 'home-masonry-item--note'}`}
      data-masonry-key={item.key}
      data-revealed="false"
      style={{ '--reveal-delay': `${Math.min(index * 70, 420)}ms` }}
    >
      {children}
    </article>
  )
}

function PostNote({ post }) {
  return (
    <div className="home-masonry-note__body">
      <p className="home-masonry-note__meta">
        {new Date(post.created_at).toLocaleDateString('zh-CN')} · {post.category || '随笔'}
      </p>
      <h2><Link to={`/posts/${post.slug || post.id}`}>{post.title}</Link></h2>
      <p className="home-masonry-note__excerpt">{plainExcerpt(post.content)}</p>
      <HomeTagList tags={post.tags} />
    </div>
  )
}

function PhotoPolaroid({ photo, onSelectPhoto }) {
  const [imageFailed, setImageFailed] = useState(false)

  return (
    <button
      type="button"
      className="home-masonry-photo"
      aria-label={`查看照片 ${photo.caption || photo.id}`}
      onClick={() => onSelectPhoto?.(photo)}
    >
      <span className="home-polaroid__well">
        {imageFailed ? (
          <span className="home-polaroid__image-fallback" role="img" aria-label={photo.caption || '精选照片'}>
            照片暂时无法显示
          </span>
        ) : (
          <img
            className="home-masonry-photo__image"
            src={getImageUrl(photo.url)}
            alt={photo.caption || '精选照片'}
            loading="lazy"
            onError={() => setImageFailed(true)}
          />
        )}
        <span className="home-polaroid__inner-edge" aria-hidden="true" />
      </span>
      <span className="home-polaroid__caption-rail">
        <span>{photo.caption || '未命名照片'}</span>
        {photo.location ? <small>{photo.location}</small> : null}
      </span>
      <HomeTagList tags={photo.tags?.length ? photo.tags : [{ name: 'photography' }]} />
    </button>
  )
}

function ModuleCard({ kind, homepage }) {
  const { settings, posts, photos, messages, collections } = homepage
  if (kind === 'index') return <HomeIndexCard postCount={posts.length} photoCount={photos.length} />
  if (kind === 'collection') return <HomeCollectionCard collections={collections} />
  if (kind === 'messages') return <MessageBoardCard messages={messages} />
  if (kind === 'history') return <HomeHistoryCard />
  if (kind === 'quote') return <HomeQuoteCard quote={settings.short_quote} />
  if (kind === 'status') return <HomeStatusCard />
  return null
}

export default function HomeEditorialGrid({ homepage, onSelectPhoto, revealEnabled = true }) {
  const items = useMemo(() => configuredItems(homepage), [homepage])

  return (
    <div className="home-masonry-grid" aria-label="首页精选内容瀑布流">
      {items.map((item, index) => (
        <MasonryItem item={item} index={index} key={item.key} revealEnabled={revealEnabled}>
          {item.kind === 'post' && <PostNote post={item.value} />}
          {item.kind === 'photo' && <PhotoPolaroid photo={item.value} onSelectPhoto={onSelectPhoto} />}
          {!['post', 'photo'].includes(item.kind) && <ModuleCard kind={item.kind} homepage={homepage} />}
        </MasonryItem>
      ))}
    </div>
  )
}

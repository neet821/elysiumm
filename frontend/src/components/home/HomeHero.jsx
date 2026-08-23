import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Moon, Sun } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { getPrimaryNavigation } from '../../navigation.js'
import { getImageUrl } from '../../utils/imageHelper.js'
import { Drawer } from '../ui/index.js'

const DEFAULT_PHOTOS = [
  {
    src: '/home/quiet-coast-1120.webp',
    srcSet: '/home/quiet-coast-640.webp 640w, /home/quiet-coast-1120.webp 1120w',
    alt: '安静的蓝灰色海岸',
  },
  {
    src: '/home/misty-coast-1120.webp',
    srcSet: '/home/misty-coast-640.webp 640w, /home/misty-coast-1120.webp 1120w',
    alt: '晨雾中的浅蓝海浪',
  },
]

function splitTitle(title) {
  const words = String(title || 'Blue Album').trim().split(/\s+/).filter(Boolean)
  if (words.length < 2) return [words[0] || 'Blue', 'Album']
  const breakAt = Math.ceil(words.length / 2)
  return [words.slice(0, breakAt).join(' '), words.slice(breakAt).join(' ')]
}

function HeroPhoto({ photo, fallback, position, loading }) {
  const photoSrc = photo?.url ? getImageUrl(photo.url) : ''
  const [failedSource, setFailedSource] = useState('')
  const useFallback = !photoSrc || failedSource === photoSrc
  const src = useFallback ? fallback.src : photoSrc
  const alt = useFallback ? fallback.alt : (photo.caption || '精选照片')

  return (
    <figure
      className={`album-hero__photo album-hero__photo--${position}`}
      data-photo-state={loading ? 'loading' : (useFallback ? 'fallback' : 'ready')}
    >
      <span className="album-hero__tape" aria-hidden="true" />
      <div className="album-hero__photo-well">
        <img
          key={src}
          src={src}
          srcSet={useFallback ? fallback.srcSet : undefined}
          sizes={position === 'back' ? '(max-width: 900px) 68vw, 25vw' : '(max-width: 900px) 58vw, 20vw'}
          alt={alt}
          loading="eager"
          decoding="async"
          onError={() => {
            if (!useFallback) setFailedSource(photoSrc)
          }}
        />
      </div>
    </figure>
  )
}

function BranchShadow() {
  const leaves = [
    [58, 66, -28], [104, 92, 18], [146, 62, -9], [188, 116, 26], [230, 78, -32],
    [270, 134, 8], [316, 92, 36], [362, 142, -18], [406, 106, 22], [452, 168, -28],
    [96, 186, -16], [150, 220, 30], [204, 176, -36], [254, 236, 14], [312, 202, -8],
    [372, 252, 34], [432, 222, -25], [492, 286, 17], [138, 304, 22], [202, 342, -28],
    [276, 316, 34], [344, 374, -12], [416, 338, 28], [486, 402, -22], [556, 360, 14],
    [220, 454, -10], [300, 492, 24], [382, 470, -31], [470, 530, 18], [552, 484, -12],
    [360, 600, 28], [448, 622, -20], [540, 590, 32], [618, 650, -16],
  ]

  return (
    <svg className="album-hero__branch-shadow" viewBox="0 0 760 820" preserveAspectRatio="xMinYMin slice" aria-hidden="true">
      <defs>
        <filter id="album-branch-blur" x="-30%" y="-30%" width="170%" height="170%">
          <feGaussianBlur stdDeviation="17" />
        </filter>
      </defs>
      <g filter="url(#album-branch-blur)">
        <path d="M-42 34C120 126 194 238 294 388C382 520 498 632 760 786" />
        <path d="M134 170C238 178 340 150 466 66" />
        <path d="M224 340C346 354 458 326 612 232" />
        <path d="M334 512C458 512 572 474 716 392" />
        {leaves.map(([cx, cy, rotate]) => (
          <ellipse key={`${cx}-${cy}`} cx={cx} cy={cy} rx="42" ry="18" transform={`rotate(${rotate} ${cx} ${cy})`} />
        ))}
      </g>
    </svg>
  )
}

function TitleOrbit() {
  return (
    <svg className="album-hero__orbit" viewBox="0 0 820 520" preserveAspectRatio="none" aria-hidden="true">
      <path d="M682 66C566 -19 234 88 65 255C-94 412 75 474 301 399C495 334 769 228 767 323C766 389 583 410 432 433" />
      <path d="M644 311C762 247 816 255 803 304C790 349 675 365 573 383" />
    </svg>
  )
}

function CollectionStamp() {
  return (
    <svg className="album-hero__stamp" viewBox="0 0 210 210" aria-hidden="true">
      <defs>
        <path id="album-stamp-top" d="M27 110A78 78 0 0 1 183 110" />
        <path id="album-stamp-bottom" d="M183 116A78 78 0 0 1 27 116" />
      </defs>
      <text><textPath href="#album-stamp-top" startOffset="50%" textAnchor="middle">QUIET COLLECTIONS</textPath></text>
      <text><textPath href="#album-stamp-bottom" startOffset="50%" textAnchor="middle">OF REMEMBERED MOMENTS</textPath></text>
      <text className="album-hero__stamp-est" x="105" y="101" textAnchor="middle">EST.</text>
      <text className="album-hero__stamp-year" x="105" y="127" textAnchor="middle">2025</text>
    </svg>
  )
}

function Signature() {
  return (
    <svg className="album-hero__signature" viewBox="0 0 360 126" aria-hidden="true">
      <text x="8" y="55">Blue</text>
      <text x="126" y="102">Album</text>
      <path d="M6 76C91 50 152 62 218 74C268 84 309 78 351 56" />
    </svg>
  )
}

export default function HomeHero({ settings, photos = [], loading = false, isDark = false, toggleTheme }) {
  const { isAuthenticated } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const navigationItems = useMemo(() => getPrimaryNavigation(isAuthenticated), [isAuthenticated])
  const aboutDestination = isAuthenticated ? '/account' : '/login'
  const title = settings?.hero_title || 'Blue Album'
  const quote = settings?.short_quote || 'Save what makes life feel like a song.'
  const [titleLineOne, titleLineTwo] = splitTitle(title)

  const scrollToContent = (event) => {
    const content = document.getElementById('home-content')
    if (!content) return
    event.preventDefault()
    const reduceMotion = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    content.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
  }

  return (
    <section className="album-hero" aria-label="Blue Album 首页首屏">
      <BranchShadow />

      <header className="album-hero__topbar">
        <Link className="album-hero__brand" to="/" aria-label="Blue Album 首页">
          <span className="album-hero__brand-mark" aria-hidden="true" />
          <span>Blue Album</span>
        </Link>
        <nav className="album-hero__nav" aria-label="首页快捷导航">
          <Link to="/archive">Archive</Link>
          <Link to="/tools">Notebook</Link>
          <Link to={aboutDestination}>About</Link>
        </nav>
        <button
          className="album-hero__menu"
          type="button"
          aria-label="打开导航"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(true)}
        >
          <span aria-hidden="true" /><span aria-hidden="true" />
        </button>
      </header>

      <div className="album-hero__copy">
        <TitleOrbit />
        <h1 aria-label={title}>
          <span aria-hidden="true">{titleLineOne}</span>
          <span aria-hidden="true">{titleLineTwo}</span>
        </h1>
        <p className="album-hero__quote">{quote}</p>
      </div>

      <div className="album-hero__photos" aria-label="首页精选照片">
        <HeroPhoto photo={photos[0]} fallback={DEFAULT_PHOTOS[0]} position="back" loading={loading} />
        <HeroPhoto photo={photos[1]} fallback={DEFAULT_PHOTOS[1]} position="front" loading={loading} />
      </div>

      <CollectionStamp />
      <Signature />

      <a className="album-hero__scroll" href="#home-content" onClick={scrollToContent}>
        <span>Scroll to begin</span><i aria-hidden="true" />
      </a>

      <Drawer open={menuOpen} onOpenChange={setMenuOpen} side="right" title="导航">
        <nav className="album-hero__drawer-nav" aria-label="首页导航菜单">
          {navigationItems.map((item) => (
            <Link key={item.to} to={item.to} onClick={() => setMenuOpen(false)}>{item.label}</Link>
          ))}
          <button type="button" onClick={toggleTheme}>
            {isDark ? <Moon size={18} aria-hidden="true" /> : <Sun size={18} aria-hidden="true" />}
            {isDark ? '切换到浅色模式' : '切换到深色模式'}
          </button>
        </nav>
      </Drawer>
    </section>
  )
}

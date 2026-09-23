import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'

import { ArticleFlowContent } from '../features/content/ArticleFlowCards.jsx'
import { ContentDetail, ContentListing, MarkdownContent } from '../features/content/ContentCatalog.jsx'
import { useHomeSidebar } from '../contexts/HomeSidebarContext.jsx'
import HomeNavigation from '../components/layout/HomeNavigation.jsx'
import './contentHome.css'

const ARTICLES_PER_PAGE = 3
const ARTICLE_REFRESH_INTERVAL_MS = 15000
const DEFAULT_ARTICLE_TITLE_SCALE = 0.8

function normalizeArticleTitleScale(value) {
  const scale = Number(value)
  return Number.isFinite(scale) && scale >= 0.6 && scale <= 1.2 ? scale : DEFAULT_ARTICLE_TITLE_SCALE
}

function articleType(item) {
  return item.type || (item.contentType === 'photo' ? 'image' : item.contentType)
}

async function enrichArticle(article) {
  if (!['movie', 'album', 'book', 'game'].includes(article.type) || article.cover || article.excerpt) return article
  try {
    const response = await fetch(`/api/metadata/search?type=${encodeURIComponent(article.type)}&q=${encodeURIComponent(article.title)}`)
    if (!response.ok) return article
    const result = (await response.json()).results?.[0]
    if (!result) return article
    return { ...article, cover: result.cover || article.cover, excerpt: result.description || article.excerpt, metadata: result }
  } catch {
    return article
  }
}

export function ArticleFlowHome() {
  const [searchParams] = useSearchParams()
  const [articles, setArticles] = useState(null)
  const [fullEssays, setFullEssays] = useState({})
  const [homeLabel, setHomeLabel] = useState('')
  const [articleTitleScale, setArticleTitleScale] = useState(DEFAULT_ARTICLE_TITLE_SCALE)
  const homeLabelLoadedRef = useRef(false)
  const [error, setError] = useState('')
  const { isOpen: homeSidebarOpen, close: closeHomeSidebar } = useHomeSidebar()
  const homeSidebarRef = useRef(null)
  const sidebarWasOpenRef = useRef(false)

  useEffect(() => {
    let active = true
    let hasLoaded = false
    const refreshArticles = async () => {
      try {
        const response = await fetch('/api/articles')
        if (!response.ok) throw new Error('服务器没有返回文章。')
        const data = await response.json()
        const items = await Promise.all((data.articles || []).map(enrichArticle))
        if (!active) return
        setArticles(items)
        setError('')
        hasLoaded = true
      } catch (reason) {
        if (active && !hasLoaded) setError(reason.message || '暂时无法打开')
      }
    }
    const refreshIfVisible = () => {
      if (document.visibilityState !== 'hidden') void refreshArticles()
    }

    void refreshArticles()
    const intervalId = window.setInterval(refreshIfVisible, ARTICLE_REFRESH_INTERVAL_MS)
    window.addEventListener('focus', refreshIfVisible)
    document.addEventListener('visibilitychange', refreshIfVisible)
    return () => {
      active = false
      window.clearInterval(intervalId)
      window.removeEventListener('focus', refreshIfVisible)
      document.removeEventListener('visibilitychange', refreshIfVisible)
    }
  }, [])

  useEffect(() => {
    if (!articles) return undefined
    let active = true
    const essays = articles.filter((item) => articleType(item) === 'essay')
    Promise.all(essays.map(async (item) => {
      try {
        const response = await fetch(`/api/articles/${encodeURIComponent(item.slug)}`)
        return [item.slug, response.ok ? ((await response.json()).article || null) : null]
      } catch {
        return [item.slug, null]
      }
    })).then((entries) => {
      if (active) setFullEssays(Object.fromEntries(entries))
    })
    return () => { active = false }
  }, [articles])

  useEffect(() => {
    if (!articles || homeLabelLoadedRef.current) return undefined
    homeLabelLoadedRef.current = true
    let active = true
    fetch('/api/homepage')
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!active) return
        setHomeLabel(data?.settings?.hero_prefix || '')
        setArticleTitleScale(normalizeArticleTitleScale(data?.settings?.article_title_scale))
      })
      .catch(() => {})
    return () => { active = false }
  }, [articles])

  useEffect(() => {
    if (!homeSidebarOpen || !homeSidebarRef.current) {
      if (sidebarWasOpenRef.current) {
        const toggle = [...document.querySelectorAll('[aria-label="收起记录和随笔"], [aria-label="展开记录和随笔"]')].find((element) => {
          const style = getComputedStyle(element)
          const rect = element.getBoundingClientRect()
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
        })
        toggle?.focus()
        sidebarWasOpenRef.current = false
      }
      return
    }
    homeSidebarRef.current.scrollTop = 0
    homeSidebarRef.current.querySelectorAll('.sidebar-scroll-viewport').forEach((viewport) => {
      viewport.scrollTop = 0
    })
    homeSidebarRef.current.querySelector('.home-sidebar__close')?.focus()
    sidebarWasOpenRef.current = true
  }, [homeSidebarOpen])

  const pageParam = searchParams.get('page') || '1'
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [pageParam])

  if (error) return <section className="state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (!articles) return <section className="state" aria-busy="true"><p>正在读取文章……</p></section>

  const sorted = [...articles].sort((a, b) => new Date(b.createdAt || b.date || b.updatedAt || 0) - new Date(a.createdAt || a.date || a.updatedAt || 0))
  const contentType = (item) => {
    const mediaRecordTypes = ['movie', 'album', 'book', 'game']
    if (mediaRecordTypes.includes(item.type) || mediaRecordTypes.includes(item.category) || mediaRecordTypes.includes(item.contentType)) return 'record'
    if (item.contentType) return item.contentType
    return articleType(item) === 'image' ? 'photo' : articleType(item)
  }
  const articleItems = sorted.filter((item) => contentType(item) === 'article')
  const essays = sorted.filter((item) => contentType(item) === 'essay')
  const records = sorted.filter((item) => contentType(item) === 'record')
  const photos = sorted.filter((item) => contentType(item) === 'photo')
  const totalPages = Math.max(1, Math.ceil(articleItems.length / ARTICLES_PER_PAGE))
  const requestedPage = Number.parseInt(searchParams.get('page') || '1', 10)
  const currentPage = Number.isFinite(requestedPage) ? Math.min(Math.max(requestedPage, 1), totalPages) : 1
  const visibleArticles = articleItems.slice((currentPage - 1) * ARTICLES_PER_PAGE, currentPage * ARTICLES_PER_PAGE)
  const paginationItems = Array.from(new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1].filter((page) => page >= 1 && page <= totalPages))).sort((a, b) => a - b).reduce((items, page, index, pages) => {
    if (index > 0 && page - pages[index - 1] > 1) items.push(`ellipsis-${page}`)
    items.push(page)
    return items
  }, [])

  return (
    <div className="legacy-old-home legacy-old-home--flat" style={{ '--home-article-title-scale': articleTitleScale }}>
      <HomeNavigation label={homeLabel} activeView="home" className="home-nav--local" />
      <ArticleFlowContent
        currentPage={currentPage}
        essays={essays}
        fullEssayBySlug={fullEssays}
        homeSidebarOpen={homeSidebarOpen}
        homeSidebarRef={homeSidebarRef}
        paginationItems={paginationItems}
        photos={photos}
        records={records}
        totalPages={totalPages}
        visibleArticles={visibleArticles}
        closeHomeSidebar={closeHomeSidebar}
      />
    </div>
  )
}

export function LegacyArticlePage() {
  const location = useLocation()
  const rawSlug = location.pathname.slice('/article/'.length)
  const [article, setArticle] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setArticle(null)
    setError('')
    fetch(`/api/articles/${rawSlug}`)
      .then((response) => {
        if (!response.ok) throw new Error(response.status === 404 ? '找不到这篇文章。' : '服务器没有返回文章。')
        return response.json()
      })
      .then((data) => { if (active) setArticle(data.article || data) })
      .catch((reason) => { if (active) setError(reason.message || '暂时无法打开') })
    return () => { active = false }
  }, [rawSlug])

  if (error) return <section className="state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (!article) return <section className="state" aria-busy="true"><p>正在读取文章……</p></section>

  return (
    <div className="legacy-old-home">
      <article className="reader reader--article">
        <Link className="back-link" to="/" aria-label="返回首页" title="返回首页">←</Link>
        <header className="reader-header"><h1>{article.title}</h1></header>
        <MarkdownContent markdown={article.markdown} html={article.html} className="reader-body" />
      </article>
    </div>
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
      .then((response) => {
        if (!response.ok) throw new Error(response.status === 404 ? '找不到这项内容。' : '服务器没有返回内容。')
        return response.json()
      })
      .then((data) => {
        if (!active) return
        if (articleSlug) setArticle(data.article)
        else setPayload(data)
      })
      .catch((reason) => { if (active) setError(reason.message || '暂时无法打开') })
    return () => { active = false }
  }, [categoryId, articleSlug])

  if (error) return <section className="content-state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (articleSlug && article) return <ContentDetail article={article} />
  if (!payload) return <section className="content-state" aria-busy="true"><p>正在载入内容…</p></section>
  return <ContentListing categories={payload.categories || []} categoryId={categoryId} />
}

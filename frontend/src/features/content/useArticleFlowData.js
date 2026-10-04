import { useEffect, useState } from 'react'

import { articleType } from './articleFlowUtils.js'

const ARTICLE_REFRESH_INTERVAL_MS = 15000
const DEFAULT_ARTICLE_TITLE_SCALE = 0.8

function normalizeArticleTitleScale(value) {
  const scale = Number(value)
  return Number.isFinite(scale) && scale >= 0.6 && scale <= 1.2 ? scale : DEFAULT_ARTICLE_TITLE_SCALE
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

export function useArticleFlowData() {
  const [articles, setArticles] = useState(null)
  const [fullEssays, setFullEssays] = useState({})
  const [homeLabel, setHomeLabel] = useState('')
  const [articleTitleScale, setArticleTitleScale] = useState(DEFAULT_ARTICLE_TITLE_SCALE)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    let hasLoaded = false
    let inFlight = false
    let lastContent = ''
    let lastEssays = ''
    const metadataCache = new Map()
    const essayCache = new Map()
    const refreshEssays = async (items) => {
      const essays = items.filter((item) => articleType(item) === 'essay')
      const keys = new Set(essays.map((item) => JSON.stringify(item)))
      for (const key of essayCache.keys()) if (!keys.has(key)) essayCache.delete(key)
      const entries = await Promise.all(essays.map(async (item) => {
        const key = JSON.stringify(item)
        let cached = essayCache.get(key)
        if (!cached || Date.now() >= cached.retryAt) {
          let article = null
          try {
            const response = await fetch(`/api/articles/${encodeURIComponent(item.slug)}`)
            if (response.ok) article = (await response.json()).article || null
          } catch {
            // A temporary failure must not become a permanent cached miss.
          }
          cached = { article, retryAt: article ? Infinity : Date.now() + 60_000 }
          essayCache.set(key, cached)
        }
        return [item.slug, cached.article]
      }))
      const content = JSON.stringify(entries)
      if (active && content !== lastEssays) {
        lastEssays = content
        setFullEssays(Object.fromEntries(entries))
      }
    }
    const refreshArticles = async () => {
      if (inFlight) return
      inFlight = true
      try {
        const response = await fetch('/api/articles')
        if (!response.ok) throw new Error('服务器没有返回文章。')
        const data = await response.json()
        const keys = new Set()
        const items = await Promise.all((data.articles || []).map(async (item) => {
          const key = JSON.stringify(item)
          keys.add(key)
          const cached = metadataCache.get(key)
          if (cached && Date.now() < cached.retryAt) return cached.article
          const article = await enrichArticle(item)
          const needsMetadata = ['movie', 'album', 'book', 'game'].includes(item.type) && !item.cover && !item.excerpt
          metadataCache.set(key, { article, retryAt: needsMetadata && article === item ? Date.now() + 60_000 : Infinity })
          return article
        }))
        if (!active) return
        for (const key of metadataCache.keys()) if (!keys.has(key)) metadataCache.delete(key)
        const content = JSON.stringify(items)
        if (content !== lastContent) {
          lastContent = content
          setArticles(items)
        }
        setError('')
        hasLoaded = true
        await refreshEssays(items)
      } catch (reason) {
        if (active && !hasLoaded) setError(reason.message || '暂时无法打开')
      } finally {
        inFlight = false
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
  }, [])

  return { articleTitleScale, articles, error, fullEssays, homeLabel }
}

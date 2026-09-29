import { useEffect, useRef, useState } from 'react'

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
  const homeLabelLoadedRef = useRef(false)

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

  return { articleTitleScale, articles, error, fullEssays, homeLabel }
}

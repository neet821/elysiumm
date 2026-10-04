import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useArticleFlowData } from '../src/features/content/useArticleFlowData.js'

describe('useArticleFlowData', () => {
  let originalVisibilityState

  beforeEach(() => {
    originalVisibilityState = Object.getOwnPropertyDescriptor(document, 'visibilityState')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
    if (originalVisibilityState) Object.defineProperty(document, 'visibilityState', originalVisibilityState)
    else delete document.visibilityState
  })

  it('loads feed articles, full essay content, and homepage presentation settings', async () => {
    const articles = [
      { contentType: 'essay', excerpt: '预览', slug: 'essay', title: '随笔', type: 'essay' },
      { contentType: 'article', excerpt: '摘要', slug: 'story', title: '文章', type: 'article' },
    ]
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === '/api/articles') return { ok: true, json: async () => ({ articles }) }
      if (path === '/api/articles/essay') return { ok: true, json: async () => ({ article: { markdown: '完整随笔' } }) }
      if (path === '/api/homepage') return { ok: true, json: async () => ({ settings: { article_title_scale: 0.75, hero_prefix: '首页标题' } }) }
      throw new Error(`Unexpected request: ${path}`)
    })

    const { result } = renderHook(() => useArticleFlowData())

    await waitFor(() => expect(result.current.homeLabel).toBe('首页标题'))
    await waitFor(() => expect(result.current.fullEssays.essay).toEqual({ markdown: '完整随笔' }))

    expect(result.current.articles).toEqual(articles)
    expect(result.current.articleTitleScale).toBe(0.75)
    expect(result.current.error).toBe('')
  })

  it('refreshes only while visible and refreshes when focus returns', async () => {
    vi.useFakeTimers()
    let articleRequestCount = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === '/api/articles') {
        articleRequestCount += 1
        return { ok: true, json: async () => ({ articles: [] }) }
      }
      return { ok: true, json: async () => ({ settings: {} }) }
    })
    const { result, unmount } = renderHook(() => useArticleFlowData())
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(result.current.articles).toEqual([])
    expect(articleRequestCount).toBe(1)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000) })
    expect(articleRequestCount).toBe(1)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    await act(async () => { window.dispatchEvent(new Event('focus')); await Promise.resolve() })
    expect(articleRequestCount).toBe(2)

    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000) })
    expect(articleRequestCount).toBe(2)
  })

  it('shares an in-flight feed request across focus and visibility refreshes', async () => {
    let resolveFeed
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation((path) => path === '/api/articles'
      ? new Promise((resolve) => { resolveFeed = resolve })
      : Promise.resolve({ ok: true, json: async () => ({ settings: {} }) }))
    const { result } = renderHook(() => useArticleFlowData())
    act(() => {
      window.dispatchEvent(new Event('focus'))
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(fetch.mock.calls.filter(([path]) => path === '/api/articles')).toHaveLength(1)
    await act(async () => { resolveFeed({ ok: true, json: async () => ({ articles: [] }) }) })
    expect(result.current.articles).toEqual([])
  })

  it('retries a failed essay after a cooldown even when the feed is unchanged', async () => {
    vi.useFakeTimers()
    let attempts = 0
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === '/api/articles') return { ok: true, json: async () => ({ articles: [
        { slug: 'essay', title: '随笔', type: 'essay' },
      ] }) }
      if (path === '/api/articles/essay') {
        attempts += 1
        if (attempts === 1) throw new Error('temporary network failure')
        return { ok: true, json: async () => ({ article: { markdown: '恢复后的正文' } }) }
      }
      return { ok: true, json: async () => ({ settings: {} }) }
    })
    const { result } = renderHook(() => useArticleFlowData())
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    const firstArticles = result.current.articles
    expect(result.current.fullEssays.essay).toBeNull()
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    expect(attempts).toBe(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
    expect(result.current.fullEssays.essay?.markdown).toBe('恢复后的正文')
    expect(result.current.articles).toBe(firstArticles)
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
    expect(fetch.mock.calls.filter(([path]) => path === '/api/articles/essay')).toHaveLength(2)
  })

  it('reuses unchanged essays and metadata but invalidates an updated essay', async () => {
    let revision = 1
    let storyTitle = '文章'
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === '/api/articles') return { ok: true, json: async () => ({ articles: [
        { slug: 'essay', title: '随笔', type: 'essay', updatedAt: revision },
        { slug: 'movie', title: '电影', type: 'movie' },
        { slug: 'story', title: storyTitle, type: 'article' },
      ] }) }
      if (path === '/api/articles/essay') return { ok: true, json: async () => ({ article: { markdown: `正文 ${revision}` } }) }
      if (path.startsWith('/api/metadata/')) return { ok: true, json: async () => ({ results: [{ cover: '/cover.jpg', description: '电影简介' }] }) }
      return { ok: true, json: async () => ({ settings: {} }) }
    })
    const count = (path) => fetch.mock.calls.filter(([url]) => url === path).length
    const { result } = renderHook(() => useArticleFlowData())
    await waitFor(() => expect(result.current.fullEssays.essay?.markdown).toBe('正文 1'))
    const firstArticles = result.current.articles
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    expect(count('/api/articles')).toBe(2)
    expect(result.current.articles).toBe(firstArticles)
    expect(count('/api/articles/essay')).toBe(1)
    expect(count('/api/metadata/search?type=movie&q=%E7%94%B5%E5%BD%B1')).toBe(1)

    storyTitle = '另一篇文章'
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    expect(result.current.articles.find((item) => item.slug === 'story').title).toBe(storyTitle)
    expect(count('/api/articles/essay')).toBe(1)

    revision = 2
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    await waitFor(() => expect(result.current.fullEssays.essay?.markdown).toBe('正文 2'))
    expect(count('/api/articles/essay')).toBe(2)
  })
})

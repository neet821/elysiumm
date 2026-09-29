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
})

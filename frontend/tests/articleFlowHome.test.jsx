import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ArticleFlowHome, LegacyArticlePage } from '../src/pages/ContentHomePage.jsx'

describe('ArticleFlowHome', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('keeps the Git-era article links on the original /article route', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [{ slug: 'hello', title: '你好文章', type: 'article', excerpt: '摘要' }] }),
    })

    render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    const link = await screen.findByRole('link', { name: '你好文章' })
    expect(link).toHaveAttribute('href', '/article/hello')
  })

  it('keeps metadata enrichment available for non-feed records', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ articles: [{ slug: 'movie', title: '电影', type: 'movie' }] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ results: [{ cover: '/media/movie.jpg', description: '电影简介' }] }),
      })

    render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/metadata/search?type=movie&q=%E7%94%B5%E5%BD%B1'))
    expect(fetch).toHaveBeenCalledWith('/api/metadata/search?type=movie&q=%E7%94%B5%E5%BD%B1')
  })

  it('keeps the homepage writing stream in date order across essays and articles', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === '/api/articles') {
        return {
          ok: true,
          json: async () => ({ articles: [
            { slug: 'essay', title: '方便面定律', type: 'essay', createdAt: '2026-08-22', excerpt: '开始吃就不会塌' },
            { slug: 'article', title: '打瓦得分儿', type: 'article', createdAt: '2026-08-24', excerpt: '低洼地发外网' },
          ] }),
        }
      }
      return { ok: true, json: async () => ({ article: { html: '<p>开始吃就不会塌</p>' } }) }
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '打瓦得分儿' })).toBeInTheDocument())
    expect(container.querySelector('.home-main h2')).toHaveTextContent('打瓦得分儿')
    expect(container.querySelector('.home-sidebar .essay-card h2')).toHaveTextContent('方便面定律')
  })

  it('keeps the photo strip below articles and supporting content', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'one', title: '第一条', type: 'article', createdAt: '2026-08-24' },
        { slug: 'two', title: '第二条', type: 'essay', createdAt: '2026-08-23', excerpt: '第二条正文' },
        { slug: 'three', title: '第三条', type: 'article', createdAt: '2026-08-22' },
        { slug: 'photo', title: '照片一', contentType: 'photo', cover: '/photo.jpg', createdAt: '2026-08-21' },
      ] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '第三条' })).toBeInTheDocument())
    expect(container.querySelectorAll('.home-main .article-card')).toHaveLength(2)
    expect(container.querySelector('.photo-strip--bottom')).toBe(container.querySelector('.legacy-old-home').lastElementChild)
  })

  it('uses the flat priority treatment for articles, essays, and records', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'article', title: '大标题文章', type: 'article', createdAt: '2026-08-24', cover: '/cover.jpg', excerpt: '文章预览' },
        { slug: 'essay', title: '压缩随笔', type: 'essay', createdAt: '2026-08-23', excerpt: '随笔正文' },
        { slug: 'record', title: '记录者', type: 'record', createdAt: '2026-08-22', review: '记录内容' },
      ] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '大标题文章' })).toBeInTheDocument())
    expect(container.querySelector('.legacy-old-home')).toHaveClass('legacy-old-home--flat')
    expect(container.querySelector('.article-card')).toHaveClass('article-card--featured')
    expect(container.querySelector('.article-card-cover')).toHaveClass('article-card-cover--centered')
    expect(container.querySelector('.essay-card')).toHaveClass('essay-card--compact')
    expect(container.querySelector('.record-card')).toHaveClass('record-card--priority')
  })

  it('keeps only the article title as a homepage detail link', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'article', title: '可点击文章', type: 'article', createdAt: '2026-08-24', cover: '/cover.jpg' },
        { slug: 'essay', title: '不可点击随笔', type: 'essay', createdAt: '2026-08-23', excerpt: '随笔正文' },
        { slug: 'record', title: '不可点击记录', type: 'record', createdAt: '2026-08-22', cover: '/record.jpg', review: '记录内容' },
        { slug: 'photo', title: '不可点击照片', contentType: 'photo', createdAt: '2026-08-21', cover: '/photo.jpg' },
      ] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '可点击文章' })).toBeInTheDocument())
    const articleCard = container.querySelector('.article-card')
    expect(articleCard.querySelector('h2 a')).toHaveAttribute('href', '/article/article')
    expect(articleCard.querySelector('.article-card-cover').closest('a')).toBeNull()
    expect(container.querySelector('.essay-card a')).toBeNull()
    expect(container.querySelector('.record-card a')).toBeNull()
    expect(container.querySelector('.photo-card a')).toBeNull()
  })

  it('paginates articles by three and places side content below the desktop layout', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'article-1', title: '文章一', type: 'article', createdAt: '2026-08-25' },
        { slug: 'article-2', title: '文章二', type: 'article', createdAt: '2026-08-24' },
        { slug: 'article-3', title: '文章三', type: 'article', createdAt: '2026-08-23' },
        { slug: 'article-4', title: '文章四', type: 'article', createdAt: '2026-08-22' },
        { slug: 'essay', title: '侧栏随笔', type: 'essay', createdAt: '2026-08-21', excerpt: '随笔正文' },
        { slug: 'record', title: '侧栏记录', type: 'record', createdAt: '2026-08-20', review: '最近看过' },
        { slug: 'photo', title: '底部照片', contentType: 'photo', createdAt: '2026-08-19', cover: '/photo.jpg' },
      ] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '文章一' })).toBeInTheDocument())
    expect(container.querySelectorAll('.home-main .article-card')).toHaveLength(3)
    expect(screen.getByRole('navigation', { name: '文章分页' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '第 2 页' })).toHaveAttribute('href', '/?page=2')
    expect(container.querySelector('.home-layout')).toContainElement(container.querySelector('.home-sidebar'))
    expect(container.querySelector('.home-layout').nextElementSibling).toHaveClass('photo-strip', 'photo-strip--bottom')
  })

  it('loads the old article detail URL and renders its HTML body', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ article: { slug: 'hello', title: '详情文章', html: '<p>旧正文</p>' } }),
    })

    render(<MemoryRouter initialEntries={['/article/hello']}><LegacyArticlePage /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '详情文章' })).toBeInTheDocument())
    expect(screen.getByText('旧正文')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '返回首页' })).toHaveTextContent('←')
    expect(screen.queryByText('返回文章列表')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/articles/hello')
  })
})

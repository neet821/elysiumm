import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ArticleFlowContent } from '../src/features/content/ArticleFlowCards.jsx'
import { ContentDetail, ContentListing } from '../src/features/content/ContentCatalog.jsx'
import ArticleFlowHome from '../src/pages/ArticleFlowHome.jsx'

afterEach(() => vi.restoreAllMocks())

describe('content presentation boundaries', () => {
  it('keeps the content catalog links and article markdown visible outside the page controller', () => {
    const { rerender } = render(
      <MemoryRouter>
        <ContentListing categories={[{
          id: 'article',
          items: [{ contentType: 'article', excerpt: '摘要', slug: 'hello world', title: '你好文章' }],
          label: '文章',
        }]} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: /你好文章/ })).toHaveAttribute('href', '/content/article/hello%20world')
    expect(screen.getByText('摘要')).toBeInTheDocument()

    rerender(
      <MemoryRouter>
        <ContentDetail article={{ contentType: 'article', markdown: '## 正文', slug: 'hello', title: '详情文章' }} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: '详情文章' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '正文' })).toBeInTheDocument()
  })

  it('keeps article, record, essay, and photo presentation in the feature boundary', () => {
    render(
      <MemoryRouter>
        <ArticleFlowContent
          articleItems={[{ createdAt: '2026-09-22', slug: 'article', title: '首页文章', type: 'article' }]}
          currentPage={1}
          essays={[{ excerpt: '随笔摘要', slug: 'essay', title: '首页随笔' }]}
          fullEssayBySlug={{}}
          paginationItems={[1]}
          photos={[{ createdAt: '2026-09-22', slug: 'photo', title: '首页照片' }]}
          records={[{ createdAt: '2026-09-22', review: '完整评论', slug: 'record', title: '首页记录', type: 'movie' }]}
          totalPages={1}
          visibleArticles={[{ createdAt: '2026-09-22', slug: 'article', title: '首页文章', type: 'article' }]}
        />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: '首页文章' })).toHaveAttribute('href', '/article/article')
    expect(screen.getByText('首页随笔')).toBeInTheDocument()
    expect(screen.getByText('首页记录')).toBeInTheDocument()
    expect(screen.getByText('首页照片')).toBeInTheDocument()
  })

  it('composes the extracted article-flow presentation from the existing API payload', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url === '/api/articles') {
        return Response.json({ articles: [
          { contentType: 'article', createdAt: '2026-09-22', excerpt: '文章摘要', slug: 'article', title: '实页文章' },
          { contentType: 'essay', excerpt: '一段随笔', slug: 'essay', title: '实页随笔' },
          { contentType: 'photo', slug: 'photo', title: '实页照片' },
          { contentType: 'record', cover: '/cover.jpg', slug: 'record', title: '实页记录', type: 'movie' },
        ] })
      }
      if (url === '/api/articles/essay') return Response.json({ article: { markdown: '完整随笔' } })
      if (url === '/api/homepage') return Response.json({ settings: { hero_prefix: 'Elysium' } })
      throw new Error(`Unexpected request: ${url}`)
    })

    render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    expect(await screen.findByRole('link', { name: '实页文章' })).toHaveAttribute('href', '/article/article')
    expect(screen.getByText('实页随笔')).toBeInTheDocument()
    expect(screen.getByText('实页记录')).toBeInTheDocument()
    expect(screen.getByText('实页照片')).toBeInTheDocument()
  })
})

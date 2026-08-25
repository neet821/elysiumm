import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ContentHomePage from '../src/pages/ContentHomePage.jsx'

describe('ContentHomePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the Obsidian content API and renders its categories', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        categories: [{ id: 'article', label: '文章', items: [{ slug: 'hello', title: '你好文章', contentType: 'article', excerpt: '摘要' }] }],
      }),
    })

    render(<MemoryRouter><ContentHomePage /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '内容' })).toBeInTheDocument())
    expect(screen.getByText('你好文章')).toBeInTheDocument()
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/content')
  })

  it('renders a content detail from the Obsidian content API', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ article: { slug: 'hello', title: '详情文章', contentType: 'article', markdown: '## 正文\n\n- Markdown 项目' } }),
    })

    render(<MemoryRouter initialEntries={['/content/article/hello']}><ContentHomePage /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '详情文章' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: '正文' })).toBeInTheDocument()
    expect(screen.getByRole('listitem')).toHaveTextContent('Markdown 项目')
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/content/article/hello')
  })
})

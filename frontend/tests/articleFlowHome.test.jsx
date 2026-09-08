import fs from 'node:fs'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ArticleFlowHome, LegacyArticlePage } from '../src/pages/ContentHomePage.jsx'
import { HomeNavigationContext, HomeSidebarContext } from '../src/contexts/HomeSidebarContext.jsx'

vi.mock('../src/pages/SyncRoomList.jsx', () => ({
  default: ({ embedded }) => <div data-testid="watch-page" data-embedded={String(Boolean(embedded))}>观影房页面</div>,
}))

vi.mock('../src/pages/MusicLobbyPage.jsx', () => ({
  default: ({ embedded }) => <div data-testid="music-page" data-embedded={String(Boolean(embedded))}>听歌房页面</div>,
}))

vi.mock('../src/pages/LivePage.jsx', () => ({
  default: () => <div data-testid="live-page">直播页面</div>,
}))

describe('ArticleFlowHome', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
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

  it('uses a smaller title scale on the legacy article reader', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')
    expect(css).toMatch(/\.legacy-old-home \.reader-header h1\s*\{[^}]*font-size:\s*clamp\(24px,\s*3\.2vw,\s*36px\);/s)
  })

  it('gives the homepage a wider but bounded desktop canvas', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')
    expect(css).toMatch(/@media \(min-width: 1400px\)[\s\S]*?\.legacy-old-home--flat\s*\{[\s\S]*?max-width:\s*1560px;/s)
    expect(css).toMatch(/@media \(min-width: 1400px\)[\s\S]*?\.legacy-old-home--flat \.home-layout\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\) minmax\(280px, 340px\);/s)
  })

  it('keeps the reader comfortable on mobile and gives the article stream a structural base', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')
    expect(css).toMatch(/\.legacy-old-home:not\(\.legacy-old-home--flat\) \.reader-body\s*\{[\s\S]*?max-width:\s*none;/s)
    expect(css).toMatch(/@media \(max-width:\s*600px\)[\s\S]*?\.legacy-old-home:not\(\.legacy-old-home--flat\)\s*\{[\s\S]*?width:\s*min\(calc\(100% - 0\.5rem\), 960px\);/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.articles-section__end-cap\s*\{[\s\S]*?background:\s*#f5f6f7;[\s\S]*?border-block:\s*1px solid #e1e4e8;/s)
    expect(css).not.toContain('articles-section__end-mask')
  })

  it('renders homepage navigation inside the page instead of a global header', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [{ slug: 'article', title: '首页文章', type: 'article', createdAt: '2026-08-25' }] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    const navigation = await screen.findByRole('navigation', { name: '首页导航' })
    expect(navigation.closest('.legacy-old-home')).toBe(container.querySelector('.legacy-old-home'))
    expect(navigation.closest('header')).toBeNull()
    expect(within(navigation).getByRole('link', { name: '观影房' })).toHaveAttribute('href', '/rooms/watch')
    expect(within(navigation).getByRole('link', { name: '听歌房' })).toHaveAttribute('href', '/rooms/music')
    expect(within(navigation).getByRole('link', { name: '直播' })).toHaveAttribute('href', '/live')
    expect(container.querySelector('.home-header-portal')).toBeNull()
  })

  it('applies the administrator title scale to the homepage article stream', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === '/api/articles') {
        return { ok: true, json: async () => ({ articles: [{ slug: 'scaled', title: '可调字号文章', type: 'article', createdAt: '2026-08-25' }] }) }
      }
      if (path === '/api/homepage') {
        return { ok: true, json: async () => ({ settings: { article_title_scale: 0.75 } }) }
      }
      return { ok: true, json: async () => ({ status: 'waiting' }) }
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '可调字号文章' })).toBeInTheDocument())
    await waitFor(() => expect(container.querySelector('.legacy-old-home')).toHaveStyle('--home-article-title-scale: 0.75'))
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

  it('places photos after the article stream and before the sidebar in document order', async () => {
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
    const layout = container.querySelector('.home-layout')
    expect([...layout.children]).toEqual([
      container.querySelector('.home-main'),
      container.querySelector('.home-sidebar'),
      container.querySelector('.photo-strip--bottom'),
    ])
  })

  it('uses the flat priority treatment for articles, essays, and records', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'article', title: '大标题文章', type: 'article', createdAt: '2026-08-24', cover: '/cover.jpg', excerpt: '文章预览' },
        { slug: 'essay', title: '压缩随笔', type: 'essay', createdAt: '2026-08-23', excerpt: '随笔正文' },
        { slug: 'record', title: '记录者', type: 'movie', contentType: 'record', createdAt: '2026-08-22', author: '作者', year: '2026', review: '记录内容' },
      ] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '大标题文章' })).toBeInTheDocument())
    expect(container.querySelector('.legacy-old-home')).toHaveClass('legacy-old-home--flat')
    expect(container.querySelector('.article-card')).toHaveClass('article-card--featured')
    expect(container.querySelector('.article-card-cover')).toHaveClass('article-card-cover--centered', 'article-card-cover--compact')
    expect(container.querySelector('.article-card-preview')).toHaveTextContent('文章预览')
    expect(container.querySelector('.article-card-preview-time')).toHaveTextContent('August 24, 2026')
    expect(container.querySelector('.articles-section__end-cap')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('.article-card > .card-time')).toBeNull()
    expect(container.querySelector('.essay-card')).toHaveClass('essay-card--compact')
    expect(container.querySelector('.essay-card > .card-time')).toHaveTextContent('2026/08/23')
    expect(container.querySelector('.record-card')).toHaveClass('record-card--priority')
    expect(container.querySelector('.essay-toggle')).toBeNull()
    expect(container.querySelector('.record-card h2')).toHaveTextContent('记录者')
    expect(container.querySelector('.record-card .record-details')).toHaveTextContent('作者')
    expect(container.querySelector('.record-added-time')).toHaveTextContent('添加时间：2026/08/22')
    expect(container.querySelector('.record-card > .card-time')).toBeNull()
    const sidebarSections = [...container.querySelectorAll('.home-sidebar > .sidebar-section')]
    expect(sidebarSections[0]).toHaveClass('sidebar-section--records', 'sidebar-section--records-scroll')
    expect(sidebarSections[1]).toHaveClass('sidebar-section--essays')
    expect(screen.getByLabelText('电影类型')).toBeInTheDocument()
  })

  it('keeps media records visible when the feed omits the derived content type', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [{
        slug: 'movie-record',
        title: '瑞克和莫蒂 S4',
        type: 'movie',
        createdAt: '2026-08-25',
        cover: '/media/movie-cover.png',
        review: '看好啊',
      }] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByText('瑞克和莫蒂 S4')).toBeInTheDocument())
    expect(container.querySelector('.record-card')).toHaveTextContent('瑞克和莫蒂 S4')
  })

  it('normalizes media content types so records remain visible', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [{
        slug: 'movie-record-with-media-type',
        title: '接口媒体类型电影',
        type: 'movie',
        contentType: 'movie',
        createdAt: '2026-08-25',
      }] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByText('接口媒体类型电影')).toBeInTheDocument())
    expect(container.querySelector('.sidebar-section--records .record-card')).toHaveTextContent('接口媒体类型电影')
    expect(container.querySelector('.sidebar-section--essays')).toHaveTextContent('还没有随笔。')
  })

  it('shows a flat icon for each supported record type', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'album', title: '专辑记录', type: 'album', contentType: 'record', createdAt: '2026-08-24' },
        { slug: 'movie', title: '电影记录', type: 'movie', contentType: 'record', createdAt: '2026-08-23' },
        { slug: 'game', title: '游戏记录', type: 'game', contentType: 'record', createdAt: '2026-08-22' },
        { slug: 'book', title: '书籍记录', type: 'book', contentType: 'record', createdAt: '2026-08-21' },
      ] }),
    })

    render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByText('专辑记录')).toBeInTheDocument())
    for (const label of ['专辑类型', '电影类型', '游戏类型', '书籍类型']) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
  })

  it('opens a long record comment in a local popup and closes it outside the card', async () => {
    const user = userEvent.setup()
    const review = '这是完整的个人评论内容，应该在卡片内展开显示，而不是跳转到其他页面。'.repeat(4)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [{ slug: 'record', title: '长评论记录', type: 'movie', contentType: 'record', createdAt: '2026-08-22', review }] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByText('长评论记录')).toBeInTheDocument())
    const card = container.querySelector('.record-card')
    const toggle = within(card).getByRole('button', { name: '展开完整评论' })
    expect(within(card).queryByRole('region', { name: '完整评论' })).not.toBeInTheDocument()
    await user.click(toggle)
    expect(within(card).getByRole('region', { name: '完整评论' })).toHaveTextContent(review)

    await user.click(document.body)
    expect(within(card).queryByRole('region', { name: '完整评论' })).not.toBeInTheDocument()
  })

  it('keeps a full-comment control for short reviews that can still clip in a narrow card', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [{ slug: 'record', title: '窄卡片评论', type: 'album', contentType: 'record', createdAt: '2026-08-22', review: '成都的数学摇滚乐队，23年第一次听还以为是日本的。' }] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByText('窄卡片评论')).toBeInTheDocument())
    expect(within(container.querySelector('.record-card')).getByRole('button', { name: '展开完整评论' })).toBeInTheDocument()
  })

  it('keeps fixed-size record cards from letting long text escape into the next card', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')

    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar \.record-card\s*\{[^}]*overflow:\s*hidden;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar \.record-card h2 > span:last-child\s*\{[^}]*-webkit-line-clamp:\s*2;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar \.record-review-summary\s*\{[^}]*max-height:/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar \.record-card\.is-review-expanded\s*\{[^}]*overflow:\s*visible;/s)
  })

  it('keeps the full-comment toggle visible beside the clipped preview', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')

    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar \.record-review-summary\s*\{[^}]*display:\s*grid;[^}]*grid-template-columns:\s*auto\s+minmax\(0,\s*1fr\)\s+auto;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar \.record-review-summary\s*\{[^}]*max-height:\s*none;[^}]*overflow:\s*visible;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar \.record-review-toggle\s*\{[^}]*align-self:\s*start;/s)
  })

  it('refreshes record comments when the homepage regains focus', async () => {
    let requestCount = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === '/api/articles') {
        requestCount += 1
        return { ok: true, json: async () => ({ articles: [{ slug: 'record', title: '会更新的记录', type: 'movie', contentType: 'record', createdAt: '2026-08-22', review: requestCount === 1 ? '旧评论' : '新评论' }] }) }
      }
      return { ok: true, json: async () => ({ article: null }) }
    })

    render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByText('旧评论')).toBeInTheDocument())
    window.dispatchEvent(new Event('focus'))
    await waitFor(() => expect(screen.getByText('新评论')).toBeInTheDocument())
    expect(requestCount).toBeGreaterThanOrEqual(2)
  })

  it('renders Markdown for articles and essays', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === '/api/articles') {
        return {
          ok: true,
          json: async () => ({ articles: [
            { slug: 'essay', title: 'Markdown 随笔', type: 'essay', createdAt: '2026-08-23', excerpt: '预览' },
            { slug: 'article', title: 'Markdown 文章', type: 'article', createdAt: '2026-08-24', excerpt: '## 文章预览标题\n\n**文章预览加粗**' },
          ] }),
        }
      }
      if (path === '/api/articles/essay') {
        return { ok: true, json: async () => ({ article: { markdown: '## 随笔正文\n\n**加粗内容**' } }) }
      }
      return { ok: true, json: async () => ({ article: { markdown: '## 文章正文\n\n- 第一项' } }) }
    })

    render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Markdown 文章' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: '文章预览标题' })).toBeInTheDocument()
    expect(screen.getByText('文章预览加粗').tagName).toBe('STRONG')
    await waitFor(() => expect(screen.getByRole('heading', { name: '随笔正文' })).toBeInTheDocument())
    expect(screen.getByText('加粗内容').tagName).toBe('STRONG')

    render(<MemoryRouter initialEntries={['/article/article']}><LegacyArticlePage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Markdown 文章' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: '文章正文' })).toBeInTheDocument()
    expect(screen.getByRole('listitem')).toHaveTextContent('第一项')
  })

  it('collapses long essays behind an arrow toggle', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === '/api/articles') {
        return { ok: true, json: async () => ({ articles: [{ slug: 'essay', title: '可折叠随笔', type: 'essay', createdAt: '2026-08-23' }] }) }
      }
      return { ok: true, json: async () => ({ article: { markdown: '第一段内容用于测试折叠显示。\n\n第二段内容用于测试折叠显示。\n\n第三段内容用于测试折叠显示。\n\n第四段内容用于测试折叠显示。\n\n第五段内容用于测试折叠显示。\n\n第六段内容用于测试折叠显示。\n\n第七段内容用于测试折叠显示。\n\n第八段内容用于测试折叠显示。\n\n第九段内容用于测试折叠显示。\n\n第十段内容用于测试折叠显示。' } }) }
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    const button = await screen.findByRole('button', { name: '展开随笔' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(container.querySelector('.essay-card')).not.toHaveClass('is-expanded')
    await user.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(container.querySelector('.essay-card')).toHaveClass('is-expanded')
    await user.click(screen.getByRole('button', { name: '收起随笔' }))
    expect(container.querySelector('.essay-card')).not.toHaveClass('is-expanded')
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
    expect(container.querySelector('.section-heading')).toBeNull()
    expect(screen.queryByText('文章')).not.toBeInTheDocument()
    expect(screen.queryByText('随笔')).not.toBeInTheDocument()
    expect(screen.queryByText('最近记录')).not.toBeInTheDocument()
    expect(screen.queryByText('照片')).not.toBeInTheDocument()
    expect(container.querySelectorAll('.home-main .article-card')).toHaveLength(3)
    expect(screen.getByRole('navigation', { name: '文章分页' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '2' })).toHaveAttribute('href', '/?page=2')
    expect(screen.getByRole('link', { name: '下一页' })).toHaveAttribute('href', '/?page=2')
    expect(container.querySelector('.home-layout')).toContainElement(container.querySelector('.home-sidebar'))
    expect(container.querySelector('.home-layout')).toContainElement(container.querySelector('.photo-strip--bottom'))
    expect([...container.querySelector('.home-layout').children].map((node) => node.className)).toEqual([
      'home-main', 'home-sidebar', 'photo-strip photo-strip--bottom',
    ])
  })

  it('renders the records and essays as an overlay drawer when opened', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'article', title: '抽屉文章', type: 'article', createdAt: '2026-08-24' },
        { slug: 'essay', title: '抽屉随笔', type: 'essay', createdAt: '2026-08-23', excerpt: '随笔正文' },
        { slug: 'record', title: '抽屉记录', contentType: 'record', type: 'movie', createdAt: '2026-08-22' },
      ] }),
    })

    const close = vi.fn()
    const toggle = vi.fn()
    const { container } = render(
      <HomeSidebarContext.Provider value={{ isOpen: true, close, toggle }}>
        <MemoryRouter><ArticleFlowHome /></MemoryRouter>
      </HomeSidebarContext.Provider>,
    )

    await waitFor(() => expect(screen.getByRole('heading', { name: '抽屉文章' })).toBeInTheDocument())
    const drawer = screen.getByRole('dialog', { name: '侧栏内容' })
    expect(drawer).toHaveClass('home-sidebar--drawer-open')
    expect(drawer).toHaveTextContent('抽屉记录')
    expect(drawer).toHaveTextContent('抽屉随笔')
    expect(drawer.querySelector('.sidebar-section--records .record-card')).toHaveTextContent('抽屉记录')
    expect(drawer.querySelector('.sidebar-section--records').compareDocumentPosition(drawer.querySelector('.sidebar-section--essays')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(drawer.querySelector('.home-sidebar__drawer-header')).toBeNull()
    const closeButton = within(drawer).getByRole('button', { name: '收起记录和随笔' })
    await userEvent.click(closeButton)
    expect(close).toHaveBeenCalledTimes(1)
    expect(container.querySelector('.home-layout')).toContainElement(drawer)
    expect(container.querySelector('.photo-strip--bottom')).toBeInTheDocument()
  })

  it('keeps mobile overflow cues while desktop hides them', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'record-1', title: '最近记录一', type: 'movie', contentType: 'record', createdAt: '2026-08-25' },
        { slug: 'record-2', title: '最近记录二', type: 'album', contentType: 'record', createdAt: '2026-08-24' },
        { slug: 'record-3', title: '更早记录', type: 'book', contentType: 'record', createdAt: '2026-08-23' },
        { slug: 'essay-1', title: '随笔一', type: 'essay', createdAt: '2026-08-22', excerpt: '随笔内容' },
        { slug: 'essay-2', title: '随笔二', type: 'essay', createdAt: '2026-08-21', excerpt: '随笔内容' },
        { slug: 'essay-3', title: '随笔三', type: 'essay', createdAt: '2026-08-20', excerpt: '随笔内容' },
      ] }),
    })

    render(
      <HomeSidebarContext.Provider value={{ isOpen: true, close: vi.fn(), toggle: vi.fn() }}>
        <MemoryRouter><ArticleFlowHome /></MemoryRouter>
      </HomeSidebarContext.Provider>,
    )

    const drawer = await screen.findByRole('dialog', { name: '侧栏内容' })
    expect(drawer.querySelector('.sidebar-section--records')).toHaveClass('sidebar-section--has-overflow')
    expect(drawer.querySelector('.sidebar-section--essays')).toHaveClass('sidebar-section--has-overflow')
    expect(drawer.querySelectorAll('.sidebar-section--records .record-card')).toHaveLength(3)
    expect(drawer.querySelectorAll('.sidebar-scroll-cue')).toHaveLength(2)
  })

  it('gives records and essays matching independent scroll regions', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'record', title: '可滚动记录', type: 'movie', contentType: 'record', createdAt: '2026-08-25' },
        { slug: 'essay', title: '可滚动随笔', type: 'essay', createdAt: '2026-08-24', excerpt: '随笔内容' },
      ] }),
    })

    const { container } = render(<MemoryRouter><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByText('可滚动随笔')).toBeInTheDocument())
    const recordsViewport = container.querySelector('.sidebar-scroll-viewport--records')
    const essaysViewport = container.querySelector('.sidebar-scroll-viewport--essays')
    expect(recordsViewport).toHaveClass('sidebar-scroll-viewport--independent')
    expect(essaysViewport).toHaveClass('sidebar-scroll-viewport--independent')
  })

  it('fixes the homepage chrome and joins the mobile drawer to it', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')
    const indexCss = fs.readFileSync('src/index.css', 'utf8')
    expect(css).toMatch(/\.home-sidebar\.home-sidebar--drawer-open\s*\{[^}]*left:\s*0;[^}]*right:\s*auto;/s)
    expect(css).toMatch(/\.home-sidebar\.home-sidebar--drawer-open\s*\{[^}]*top:\s*0;/s)
    expect(css).toMatch(/\.home-sidebar-backdrop\s*\{[^}]*top:\s*0;/s)
    expect(css).toMatch(/\.home-sidebar\.home-sidebar--drawer-open \.record-card\s*\{[^}]*grid-template-columns:\s*64px\s+minmax\(0,\s*1fr\);/s)
    expect(css).toMatch(/\.home-sidebar\.home-sidebar--drawer-open \.record-cover\s*\{[^}]*max-width:\s*64px;[^}]*width:\s*64px;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar\s*\{[^}]*margin-top:\s*2rem;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar\.home-sidebar--drawer-open\s*\{[^}]*margin-top:\s*0;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar\.home-sidebar--drawer-open\s*\{[^}]*display:\s*flex;[^}]*overflow:\s*hidden;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar\.home-sidebar--drawer-open\s*> \.sidebar-section--essays\s*\{[^}]*min-height:\s*0;[^}]*overflow:\s*hidden;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar\.home-sidebar--drawer-open \.sidebar-scroll-viewport--records\s*\{[^}]*max-block-size:\s*calc\(var\(--record-row-height\)\s*\*\s*2\);[^}]*overflow-y:\s*auto;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar\.home-sidebar--drawer-open \.sidebar-scroll-viewport\s*\{[^}]*overflow-y:\s*auto;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar\.home-sidebar--drawer-open \.sidebar-scroll-viewport--essays\s*\{[^}]*flex:\s*1 1 auto;[^}]*overflow-y:\s*auto;/s)
    expect(css).toMatch(/\.legacy-old-home--flat \.home-sidebar\.home-sidebar--drawer-open\s*> \.sidebar-section--essays\s*\{[^}]*border-top:\s*2px\s+solid/si)
    const baseHomeCss = css.slice(
      css.indexOf('.legacy-old-home--flat .home-sidebar-backdrop'),
      css.indexOf('/* The mobile drawer'),
    )
    expect(baseHomeCss).toMatch(/\.sidebar-scroll-cue\s*\{\s*display:\s*none;\s*\}/s)
    expect(baseHomeCss).toMatch(/\.home-sidebar \.essay-card:last-child\s*\{[^}]*border-bottom:\s*1px\s+solid\s+#ddd;/s)
    expect(css).toMatch(/@media \(max-width:\s*800px\)[\s\S]*?\.home-sidebar\.home-sidebar--drawer-open \.sidebar-scroll-cue\s*\{[^}]*display:\s*flex;/s)
    expect(css).toMatch(/@media \(min-width:\s*801px\)[\s\S]*?\.legacy-old-home--flat \.home-sidebar\s*\{[^}]*align-self:\s*stretch;[^}]*overflow:\s*hidden;/s)
    expect(css).not.toMatch(/@media \(min-width:\s*801px\)[\s\S]*?\.legacy-old-home--flat \.home-sidebar\s*\{[^}]*position:\s*sticky;/s)
    expect(css).toMatch(/@media \(min-width:\s*801px\)[\s\S]*?\.home-nav__sidebar-toggle\s*\{[^}]*display:\s*none(?:\s*!important)?;/s)
    expect(css).toMatch(/@media \(min-width:\s*801px\)[\s\S]*?\.sidebar-scroll-viewport--records\s*\{[^}]*max-block-size:\s*calc\(var\(--record-row-height\)\s*\*\s*2\);[^}]*overflow-y:\s*auto;/s)
    expect(css).toMatch(/@media \(min-width:\s*801px\)[\s\S]*?\.sidebar-scroll-viewport--essays\s*\{[^}]*flex:\s*1 1 auto;[^}]*overflow-y:\s*auto;/s)
    expect(indexCss).not.toMatch(/\.home-header-portal/)
    expect(css).not.toMatch(/\.home-sidebar__drawer-header/)
    expect(css).toMatch(/\.article-card--featured h2\s*\{[^}]*overflow-wrap:\s*anywhere;/s)
    expect(css).not.toMatch(/\.legacy-old-home--flat \.article-card--featured h2\s*\{[^}]*white-space:\s*nowrap;/s)
    expect(css).toMatch(/@media \(min-width:\s*801px\)[\s\S]*?\.legacy-old-home--flat \.home-layout\s*\{[^}]*grid-template-areas:/s)
  })

  it('moves homepage actions into an always-open left rail on wide screens', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')
    expect(css).toMatch(/@media \(min-width:\s*1101px\)[\s\S]*?\.legacy-old-home--flat \.home-nav\s*\{[^}]*position:\s*fixed;[^}]*left:\s*0;[^}]*top:\s*0;[^}]*bottom:\s*0;/s)
    expect(css).toMatch(/@media \(min-width:\s*1101px\)[\s\S]*?\.legacy-old-home--flat\s*\{[^}]*margin-left:\s*var\(--home-nav-rail-width\);/s)
    expect(css).toMatch(/@media \(max-width:\s*1100px\)[\s\S]*?\.home-nav__sidebar-toggle\s*\{[^}]*display:\s*inline-flex\s*!important;/s)
    expect(css).toMatch(/\.home-nav__action-label\s*\{/s)
  })

  it('keeps the compact navigation without a home action and hides the drawer trigger at medium widths', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')
    expect(css).toMatch(/@media \(max-width:\s*800px\)[\s\S]*?\.home-nav__action--home\s*\{[^}]*display:\s*none\s*!important;/s)
    expect(css).toMatch(/@media \(min-width:\s*801px\) and \(max-width:\s*1100px\)[\s\S]*?\.home-nav__sidebar-toggle\s*\{[^}]*display:\s*none\s*!important;/s)
    expect(css).toMatch(/@media \(min-width:\s*801px\) and \(max-width:\s*1100px\)[\s\S]*?\.home-nav__action--home\s*\{[^}]*display:\s*none\s*!important;/s)
  })

  it('gives the wide rail a centered identity block and separates admin at the bottom', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')
    expect(css).toMatch(/@media \(min-width:\s*1101px\)[\s\S]*?\.legacy-old-home--flat \.home-nav__identity\s*\{[^}]*align-items:\s*center;[^}]*justify-content:\s*center;/s)
    expect(css).toMatch(/@media \(min-width:\s*1101px\)[\s\S]*?\.legacy-old-home--flat \.home-nav__identity-name\s*\{[^}]*display:\s*block;/s)
    expect(css).toMatch(/@media \(min-width:\s*1101px\)[\s\S]*?\.legacy-old-home--flat \.home-nav__admin-action\s*\{[^}]*margin-top:\s*auto;[^}]*border-top:/s)
    expect(css).toMatch(/\.home-nav__account\s*\{[^}]*display:\s*none;/s)
  })

  it('keeps room and live links as real routes instead of embedded homepage views', async () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn((query) => ({
        matches: query === '(min-width: 1101px)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [{ slug: 'article', title: '首页文章', type: 'article', createdAt: '2026-08-25' }] }),
    })

    render(
      <HomeNavigationContext.Provider value={{ isAdmin: true, isAuthenticated: true, user: { username: 'neet821', avatar: '/avatar.png' } }}>
        <MemoryRouter initialEntries={['/']}><ArticleFlowHome /></MemoryRouter>
      </HomeNavigationContext.Provider>,
    )

    const navigation = await screen.findByRole('navigation', { name: '首页导航' })
    expect(screen.getByTestId('home-identity')).toHaveTextContent('neet821')
    expect(within(navigation).getByRole('link', { name: '首页' })).toHaveAttribute('href', '/')
    expect(within(navigation.querySelector('.home-nav__leading-actions')).getByRole('link', { name: '打开管理员控制台' })).toHaveAttribute('href', '/admin/homepage')
    expect(within(navigation.querySelector('.home-nav__trailing-actions')).getByRole('link', { name: '观影房' })).toHaveAttribute('href', '/rooms/watch')
    expect(screen.queryByText('账户')).not.toBeInTheDocument()
    expect(screen.queryByTestId('wide-home-view')).not.toBeInTheDocument()

    expect(within(navigation).getByRole('link', { name: '观影房' })).toHaveAttribute('href', '/rooms/watch')
    expect(within(navigation).getByRole('link', { name: '听歌房' })).toHaveAttribute('href', '/rooms/music')
    expect(within(navigation).getByRole('link', { name: '直播' })).toHaveAttribute('href', '/live')
    expect(screen.queryByTestId('wide-home-view')).not.toBeInTheDocument()
    expect(screen.queryByTestId('watch-page')).not.toBeInTheDocument()
    expect(screen.queryByTestId('music-page')).not.toBeInTheDocument()
    expect(screen.queryByTestId('live-page')).not.toBeInTheDocument()
  })

  it('groups compact navigation into a left control cluster and a right destination cluster', () => {
    const css = fs.readFileSync('src/pages/contentHome.css', 'utf8')
    expect(css).toContain('.home-nav__leading-actions')
    expect(css).toContain('.home-nav__trailing-actions')
    expect(css).toMatch(/@media \(max-width:\s*800px\)[\s\S]*?\.home-nav__trailing-actions\s*\{[^}]*margin-left:\s*auto;/s)
    expect(css).toMatch(/@media \(min-width:\s*801px\) and \(max-width:\s*1100px\)[\s\S]*?\.home-nav__leading-actions\s*\{[^}]*margin-left:\s*auto;/s)
  })

  it('returns to the top after changing article pages', async () => {
    const user = userEvent.setup()
    const scrollTo = window.scrollTo
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ articles: [
        { slug: 'article-1', title: '第一页文章一', type: 'article', createdAt: '2026-08-25' },
        { slug: 'article-2', title: '第一页文章二', type: 'article', createdAt: '2026-08-24' },
        { slug: 'article-3', title: '第一页文章三', type: 'article', createdAt: '2026-08-23' },
        { slug: 'article-4', title: '第二页文章', type: 'article', createdAt: '2026-08-22' },
      ] }),
    })

    render(<MemoryRouter initialEntries={['/?page=1']}><ArticleFlowHome /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '第一页文章一' })).toBeInTheDocument())
    scrollTo.mockClear()
    await user.click(screen.getByRole('link', { name: '下一页' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: '第二页文章' })).toBeInTheDocument())
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: 'auto' })
  })

  it('loads the old article detail URL with its article body', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ article: { slug: 'hello', title: '详情文章', markdown: '## 旧正文\n\n兼容 Markdown' } }),
    })

    render(<MemoryRouter initialEntries={['/article/hello']}><LegacyArticlePage /></MemoryRouter>)

    await waitFor(() => expect(screen.getByRole('heading', { name: '详情文章' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: '旧正文' })).toBeInTheDocument()
    expect(screen.getByText('兼容 Markdown')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByText('article')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '返回首页' })).toHaveTextContent('←')
    expect(screen.queryByText('返回文章列表')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/articles/hello')
  })
})

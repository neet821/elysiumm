import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { authState } = vi.hoisted(() => ({
  authState: { isAuthenticated: false, user: null },
}))

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => authState,
}))

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import HomeEditorialGrid from '../src/components/home/HomeEditorialGrid.jsx'
import MessageBoardCard from '../src/components/home/MessageBoardCard.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'
import { DEFAULT_HOMEPAGE_SETTINGS } from '../src/components/home/homepageModel.js'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const post = {
  id: 11,
  slug: 'quiet-systems',
  title: 'Quiet systems',
  content: 'A compact piece of writing.',
  category: 'technology',
  created_at: '2026-07-15T10:00:00Z',
  tags: [
    { name: 'technology' },
    { name: 'diary' },
    { name: 'music' },
    { name: 'featured' },
  ],
}

const photo = {
  id: 21,
  url: '/uploads/blue-hour.jpg',
  caption: 'Blue hour',
  location: 'Hangzhou',
  created_at: '2026-07-14T10:00:00Z',
  tags: [{ name: 'photography' }],
}

const message = {
  id: 31,
  content: 'This archive feels alive.',
  likes: 2,
  created_at: '2026-07-13T10:00:00Z',
  user: { username: 'Visitor' },
  replies: [],
}

const settings = {
  ...DEFAULT_HOMEPAGE_SETTINGS,
  short_quote: 'Small notes, kept carefully.',
  cards: [
    { id: 'quote', size: 'small', theme: 'paper' },
    { id: 'index', size: 'small', theme: 'archive' },
    { id: 'writing', size: 'wide', theme: 'paper' },
    { id: 'photography', size: 'medium', theme: 'film' },
    { id: 'messages', size: 'medium', theme: 'note' },
    { id: 'history', size: 'medium', theme: 'archive' },
    { id: 'collection', size: 'medium', theme: 'archive' },
  ],
}

const homepage = {
  settings,
  posts: [post],
  photos: [photo],
  messages: [message],
  collections: [],
}

function renderGrid(props = {}) {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <HomeEditorialGrid homepage={homepage} {...props} />
    </MemoryRouter>,
  )
}

describe('natural homepage masonry', () => {
  beforeEach(() => {
    authState.isAuthenticated = false
    authState.user = null
    apiClient.get.mockReset()
    apiClient.post.mockReset()
  })

  afterEach(() => vi.unstubAllGlobals())

  it('expands every selected post and photograph into the masonry', () => {
    const { container } = renderGrid()
    expect(container.querySelector('.home-masonry-grid')).toBeInTheDocument()
    expect(container.querySelector('[data-masonry-key="post-11"]')).toBeInTheDocument()
    expect(container.querySelector('[data-masonry-key="photo-21"]')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Quiet systems' })).toHaveAttribute('href', '/posts/quiet-systems')
    expect(screen.getByRole('button', { name: '查看照片 Blue hour' })).toBeInTheDocument()
  })

  it('保持稳定的逐张弹出延迟，且所有卡片都不再生成胶带属性', () => {
    const { container, rerender } = renderGrid()
    const firstPost = container.querySelector('[data-masonry-key="post-11"]')
    const firstModule = container.querySelector('[data-masonry-key="module-quote"]')
    const firstAppearance = firstPost.getAttribute('style')

    expect(firstPost.style.getPropertyValue('--reveal-delay')).toMatch(/ms$/)
    expect(firstPost).not.toHaveAttribute('data-tape-count')
    expect(firstModule).not.toHaveAttribute('data-tape-count')
    expect(firstPost.getAttribute('style')).not.toContain('tape')

    rerender(
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <HomeEditorialGrid homepage={homepage} />
      </MemoryRouter>,
    )
    expect(container.querySelector('[data-masonry-key="post-11"]').getAttribute('style')).toBe(firstAppearance)
  })

  it('卡片初始不可见，进入约十二个百分点视口后只显现一次', () => {
    const observers = []
    class IntersectionObserverMock {
      constructor(callback, options) {
        this.callback = callback
        this.options = options
        this.disconnect = vi.fn()
        observers.push(this)
      }
      observe() {}
    }
    vi.stubGlobal('IntersectionObserver', IntersectionObserverMock)

    const { container } = renderGrid()
    const first = container.querySelector('[data-masonry-key="module-quote"]')
    expect(first).toHaveAttribute('data-revealed', 'false')
    expect(observers[0].options).toEqual({ threshold: 0.12, rootMargin: '0px 0px -8% 0px' })

    act(() => observers[0].callback([{ isIntersecting: true }]))
    expect(first).toHaveAttribute('data-revealed', 'true')
    expect(observers[0].disconnect).toHaveBeenCalledTimes(1)
  })

  it('首页尚未滚动时即使进入视口也不提前显现', () => {
    const observers = []
    class IntersectionObserverMock {
      constructor(callback) {
        this.callback = callback
        this.disconnect = vi.fn()
        observers.push(this)
      }
      observe() {}
    }
    vi.stubGlobal('IntersectionObserver', IntersectionObserverMock)

    const { container } = renderGrid({ revealEnabled: false })
    const first = container.querySelector('[data-masonry-key="module-quote"]')

    expect(first).toHaveAttribute('data-revealed', 'false')
    expect(observers).toHaveLength(0)
  })

  it('uses controlled images and limits semantically styled tags to three plus a remainder', () => {
    renderGrid()

    const image = screen.getByRole('img', { name: 'Blue hour' })
    expect(image).toHaveAttribute('loading', 'lazy')
    expect(image).toHaveClass('home-masonry-photo__image')
    expect(image.closest('.home-polaroid__well')).toBeInTheDocument()
    expect(document.querySelector('.home-polaroid__inner-edge')).toBeInTheDocument()
    expect(document.querySelector('.home-polaroid__caption-rail')).toHaveTextContent('Blue hour')
    expect(screen.getByText('photography')).toHaveClass('home-tag--photography')
    expect(screen.getAllByText('technology').find((element) => element.classList.contains('home-tag--technology'))).toBeTruthy()
    expect(screen.getByText('diary')).toHaveClass('home-tag--diary')
    expect(screen.getByText('music')).toHaveClass('home-tag--music')
    expect(screen.getByText('+1')).toBeInTheDocument()
  })

  it('keeps the polaroid frame when its image cannot load', () => {
    const { container } = renderGrid()
    fireEvent.error(screen.getByRole('img', { name: 'Blue hour' }))

    expect(screen.getByText('照片暂时无法显示')).toBeInTheDocument()
    expect(container.querySelector('[data-masonry-key="photo-21"]')).toHaveClass('home-masonry-item--photo')
    expect(container.querySelector('.home-polaroid__caption-rail')).toHaveTextContent('Blue hour')
  })

  it('shows public messages and does not expose a posting form to guests', () => {
    renderGrid()

    const card = screen.getByRole('region', { name: '留言板' })
    expect(within(card).getByText('This archive feels alive.')).toBeInTheDocument()
    expect(within(card).queryByRole('textbox', { name: '写下留言' })).not.toBeInTheDocument()
    expect(within(card).getByRole('link', { name: '登录后留言' })).toHaveAttribute(
      'href',
      '/login?next=%2F%23messages',
    )
  })

  it('lets an authenticated visitor post and immediately shows the real response', async () => {
    const user = userEvent.setup()
    authState.isAuthenticated = true
    authState.user = { id: 9, username: 'Signed in' }
    apiClient.post.mockResolvedValue({
      data: {
        id: 32,
        content: 'A new public note.',
        likes: 0,
        created_at: '2026-07-15T11:00:00Z',
        user: { username: 'Signed in' },
        replies: [],
      },
    })
    render(
      <MemoryRouter>
        <MessageBoardCard messages={[message]} />
      </MemoryRouter>,
    )

    await user.type(screen.getByRole('textbox', { name: '写下留言' }), 'A new public note.')
    await user.click(screen.getByRole('button', { name: '发布留言' }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.MESSAGE_BOARD, {
      content: 'A new public note.',
    }))
    expect(screen.getByText('A new public note.')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '写下留言' })).toHaveValue('')
  })

  it('uses measured row spans with three, two, and one responsive columns', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'styles', 'homeRebuild.css'), 'utf8')
    const source = fs.readFileSync(path.join(frontendRoot, 'src', 'components', 'home', 'HomeEditorialGrid.jsx'), 'utf8')

    expect(css).toMatch(/\.home-masonry-grid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/)
    expect(css).toMatch(/@media \(max-width:\s*960px\)[\s\S]*?repeat\(2, minmax\(0, 1fr\)\)/)
    expect(css).toMatch(/@media \(max-width:\s*640px\)[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\)/)
    expect(css).toMatch(/grid-auto-rows:\s*8px/)
    expect(css).toMatch(/\.home-masonry-item::before/)
    expect(css).toMatch(/\.home-masonry-item::after/)
    expect(css).toMatch(/\.home-masonry-item::before,[\s\S]*?content:\s*none/)
    expect(css).toMatch(/\.home-polaroid__well/)
    expect(css).toMatch(/\.home-polaroid__caption-rail/)
    expect(source).toMatch(/ResizeObserver/)
    expect(source).not.toMatch(/Math\.random/)
    expect(source).not.toMatch(/data-tape|--tape|rotate\(/)
  })
})

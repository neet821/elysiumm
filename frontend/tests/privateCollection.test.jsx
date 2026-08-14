import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: {
    delete: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

import PrivateCollectionPage from '../src/pages/PrivateCollectionPage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

const folders = [
  {
    id: 1,
    user_id: 7,
    parent_id: null,
    name: 'Work',
    icon: 'folder',
    color: '#315B7D',
    sort_order: 0,
    is_sensitive: false,
    is_public: false,
    created_at: '2026-07-01T12:00:00',
  },
  {
    id: 2,
    user_id: 7,
    parent_id: 1,
    name: 'Research',
    icon: 'book',
    color: '#557A5A',
    sort_order: 0,
    is_sensitive: false,
    is_public: true,
    created_at: '2026-07-02T12:00:00',
  },
]

const bookmarks = [
  {
    id: 11,
    user_id: 7,
    folder_id: 2,
    title: 'Docs',
    url: 'https://example.com/docs',
    description: 'Private working notes.',
    favicon: null,
    preview_url: null,
    sort_order: 0,
    is_archived: false,
    is_public: false,
    is_pinned: true,
    visit_count: 3,
    show_description: true,
    show_preview: true,
    show_visit_count: false,
    allow_indexing: false,
    tags: ['reference'],
    created_at: '2026-07-03T12:00:00',
    last_visited_at: '2026-07-04T12:00:00',
  },
  {
    id: 12,
    user_id: 7,
    folder_id: 1,
    title: 'Tracker',
    url: 'https://example.com/tracker',
    description: null,
    favicon: null,
    preview_url: null,
    sort_order: 1,
    is_archived: false,
    is_public: true,
    is_pinned: false,
    visit_count: 8,
    show_description: false,
    show_preview: false,
    show_visit_count: true,
    allow_indexing: false,
    tags: [],
    created_at: '2026-07-05T12:00:00',
    last_visited_at: '2026-07-06T12:00:00',
  },
]

const engines = [
  {
    id: 5,
    user_id: 7,
    category: 'web',
    category_label: 'Web',
    name: 'DuckDuckGo',
    url_template: 'https://duckduckgo.com/?q={query}',
    icon: 'search',
    sort_order: 0,
    is_enabled: true,
    created_at: '2026-07-01T12:00:00',
    updated_at: '2026-07-01T12:00:00',
  },
]

function renderPrivateCollection() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <PrivateCollectionPage />
    </MemoryRouter>,
  )
}

describe('private Collection workspace', () => {
  beforeEach(() => {
    apiClient.delete.mockReset().mockResolvedValue({ data: { status: 'success' } })
    apiClient.get.mockReset().mockImplementation((url) => {
      if (url === API_ENDPOINTS.BOOKMARK_FOLDERS) return Promise.resolve({ data: folders })
      if (url === API_ENDPOINTS.SEARCH_ENGINES) return Promise.resolve({ data: engines })
      if (url === API_ENDPOINTS.BOOKMARKS) return Promise.resolve({ data: bookmarks })
      if (url === API_ENDPOINTS.BOOKMARK_BACKUPS) return Promise.resolve({ data: [] })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    apiClient.post.mockReset().mockResolvedValue({ data: { matched: 1, requested: 1 } })
    apiClient.put.mockReset().mockResolvedValue({ data: {} })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(window, 'open').mockImplementation(() => null)
  })

  it('renders a nested folder tree and keeps private search and sorting server-driven', async () => {
    const user = userEvent.setup()
    renderPrivateCollection()

    expect(await screen.findByRole('heading', { name: '我的收藏' })).toBeInTheDocument()
    expect(screen.getByRole('treeitem', { name: /Work/ })).toHaveAttribute('aria-level', '1')
    expect(screen.getByRole('treeitem', { name: /Research/ })).toHaveAttribute('aria-level', '2')
    expect(screen.getByText('Docs')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('收藏排序'), 'popular')
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.BOOKMARKS, {
      params: { sort: 'popular' },
    }))

    await user.type(screen.getByLabelText('搜索我的收藏'), 'docs')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() => expect(apiClient.get).toHaveBeenLastCalledWith(API_ENDPOINTS.BOOKMARKS, {
      params: { q: 'docs', sort: 'popular' },
    }))
  })

  it('records a visit before opening a private bookmark', async () => {
    const user = userEvent.setup()
    renderPrivateCollection()
    await screen.findByText('Docs')

    await user.click(screen.getByRole('button', { name: '打开 Docs' }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.BOOKMARK_VISIT(11)))
    expect(window.open).toHaveBeenCalledWith('https://example.com/docs', '_blank', 'noopener,noreferrer')
    expect(apiClient.post.mock.invocationCallOrder[0]).toBeLessThan(window.open.mock.invocationCallOrder[0])
  })

  it('preserves a bookmark draft after a failed save and sends explicit public controls', async () => {
    const user = userEvent.setup()
    apiClient.post.mockRejectedValueOnce({ response: { data: { detail: 'Sensitive folders cannot publish bookmarks' } } })
    renderPrivateCollection()
    await screen.findByText('Docs')

    await user.click(screen.getByRole('button', { name: '新建收藏' }))
    const dialog = screen.getByRole('dialog', { name: '新建收藏' })
    await user.type(within(dialog).getByLabelText('标题'), 'Public guide')
    await user.type(within(dialog).getByLabelText('网址'), 'https://example.com/guide')
    await user.selectOptions(within(dialog).getByLabelText('文件夹'), '2')
    await user.click(within(dialog).getByLabelText('设为公开'))
    await user.click(within(dialog).getByLabelText('显示访问次数'))
    await user.click(within(dialog).getByRole('button', { name: '保存收藏' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Sensitive folders cannot publish bookmarks',
    )
    expect(within(dialog).getByLabelText('标题')).toHaveValue('Public guide')

    apiClient.post.mockResolvedValueOnce({ data: { ...bookmarks[0], id: 13, title: 'Public guide' } })
    await user.click(within(dialog).getByRole('button', { name: '保存收藏' }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.BOOKMARKS, expect.objectContaining({
      title: 'Public guide',
      url: 'https://example.com/guide',
      folder_id: 2,
      is_public: true,
      show_visit_count: true,
    })))
  })

  it('edits an existing bookmark with the same explicit visibility controls', async () => {
    const user = userEvent.setup()
    renderPrivateCollection()
    await screen.findByText('Docs')

    await user.click(screen.getByRole('button', { name: '编辑 Docs' }))
    const dialog = screen.getByRole('dialog', { name: '编辑收藏' })
    expect(within(dialog).getByLabelText('标题')).toHaveValue('Docs')
    await user.click(within(dialog).getByLabelText('设为公开'))
    await user.click(within(dialog).getByLabelText('允许搜索引擎收录'))
    await user.click(within(dialog).getByRole('button', { name: '保存收藏' }))

    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith(
      API_ENDPOINTS.BOOKMARK_DETAIL(11),
      expect.objectContaining({ is_public: true, allow_indexing: true }),
    ))
  })

  it.each([
    ['移动所选', 'move'],
    ['复制所选', 'copy'],
    ['删除所选', 'delete'],
  ])('runs %s as one bulk request', async (buttonName, action) => {
    const user = userEvent.setup()
    renderPrivateCollection()
    await screen.findByText('Docs')

    await user.click(screen.getByLabelText('选择 Docs'))
    if (action !== 'delete') {
      await user.selectOptions(screen.getByLabelText('批量操作目标'), '1')
    }
    await user.click(screen.getByRole('button', { name: buttonName }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.BOOKMARK_BULK, {
      action,
      ids: [11],
      ...(action === 'delete' ? {} : { folder_id: 1 }),
    }))
  })

  it('provides owner-only search engines and a usable start page', async () => {
    const user = userEvent.setup()
    renderPrivateCollection()
    await screen.findByText('Docs')

    await user.click(screen.getByRole('tab', { name: '搜索引擎' }))
    expect(await screen.findByText('DuckDuckGo')).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.SEARCH_ENGINES)

    await user.click(screen.getByRole('tab', { name: '起始页' }))
    await user.type(screen.getByLabelText('起始页搜索'), 'blue album')
    await user.click(screen.getByRole('button', { name: '使用 DuckDuckGo 搜索' }))
    expect(window.open).toHaveBeenCalledWith(
      'https://duckduckgo.com/?q=blue%20album',
      '_blank',
      'noopener,noreferrer',
    )
    expect(screen.getByRole('button', { name: '打开 Docs' })).toBeInTheDocument()
  })

  it('adds a validated owner-only search engine from the workspace', async () => {
    const user = userEvent.setup()
    apiClient.post.mockResolvedValueOnce({
      data: {
        ...engines[0],
        id: 6,
        name: 'Kagi',
        url_template: 'https://kagi.com/search?q={query}',
      },
    })
    renderPrivateCollection()
    await screen.findByText('Docs')

    await user.click(screen.getByRole('tab', { name: '搜索引擎' }))
    await user.click(screen.getByRole('button', { name: '添加搜索引擎' }))
    await user.type(screen.getByLabelText('搜索引擎名称'), 'Kagi')
    fireEvent.change(screen.getByLabelText('搜索网址模板'), {
      target: { value: 'https://kagi.com/search?q={query}' },
    })
    await user.click(screen.getByRole('button', { name: '保存搜索引擎' }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.SEARCH_ENGINES, expect.objectContaining({
      name: 'Kagi',
      url_template: 'https://kagi.com/search?q={query}',
      is_enabled: true,
    })))
    expect(await screen.findByText('Kagi')).toBeInTheDocument()
  })

  it('opens the protected transfer and backup workspace', async () => {
    const user = userEvent.setup()
    renderPrivateCollection()
    await screen.findByText('Docs')

    await user.click(screen.getByRole('tab', { name: '导入导出与备份' }))
    expect(await screen.findByRole('heading', { name: '导入、导出与备份' })).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.BOOKMARK_BACKUPS)
  })
})

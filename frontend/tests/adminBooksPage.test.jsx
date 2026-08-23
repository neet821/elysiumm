import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { delete: vi.fn(), get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import AdminBooksPage from '../src/pages/AdminBooksPage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

const firstBook = {
  id: 1,
  slug: 'blue-notes',
  title: 'Blue Notes',
  author: 'A. Reader',
  description: 'Reading notes.',
  cover_url: '/uploads/books/blue.webp',
  category: 'Notes',
  tags: ['blue', 'notes'],
  reading_status: 'reading',
  reader_url: 'https://books.example.test/kavita/Library/Blue/1',
  reader_path: 'Library/Blue/1',
  is_public: true,
  is_featured: true,
  display_order: 0,
  last_read_at: null,
  revision: 3,
  created_at: '2026-07-15T10:00:00Z',
  updated_at: '2026-07-15T10:00:00Z',
}

const secondBook = {
  ...firstBook,
  id: 2,
  slug: 'second-book',
  title: 'Second Book',
  tags: ['essay'],
  revision: 1,
}

const readingList = {
  id: 7,
  slug: 'start-here',
  title: 'Start here',
  description: 'A short list.',
  display_order: 0,
  books: [secondBook, firstBook],
  is_public: true,
  revision: 2,
  created_at: '2026-07-15T10:00:00Z',
  updated_at: '2026-07-15T10:00:00Z',
}

const catalog = {
  reader_available: true,
  books: [firstBook, secondBook],
  lists: [readingList],
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <AdminBooksPage />
    </MemoryRouter>,
  )
}

describe('administrator Books content', () => {
  beforeEach(() => {
    apiClient.delete.mockReset()
    apiClient.get.mockReset()
    apiClient.post.mockReset()
    apiClient.put.mockReset()
    apiClient.get.mockResolvedValue({ data: catalog })
  })

  it('loads books and lists with public preview and revision information', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByRole('heading', { name: '书籍内容' })).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_BOOKS)
    expect(screen.getByRole('link', { name: '查看公开书籍' })).toHaveAttribute('href', '/books')
    expect(await screen.findByText('修订号 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '编辑 Blue Notes' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: '书单' }))
    expect(screen.getByText('Start here')).toBeInTheDocument()
    expect(screen.getByText('2 本书')).toBeInTheDocument()
  })

  it('creates a validated book and reloads the catalog', async () => {
    const user = userEvent.setup()
    apiClient.post.mockResolvedValue({ data: { ...firstBook, id: 9, revision: 1 } })
    renderPage()
    await screen.findByText('Blue Notes')

    await user.click(screen.getByRole('button', { name: '添加书籍' }))
    await user.type(await screen.findByLabelText(/^书名/), 'A New Book')
    await user.type(screen.getByLabelText(/^网址标识/), 'a-new-book')
    await user.type(screen.getByLabelText('书籍标签'), 'new, reading')
    await user.type(screen.getByLabelText('Kavita 相对路径'), 'Library/New/9')
    await user.click(screen.getByLabelText('公开书籍'))
    await user.click(screen.getByRole('button', { name: '创建书籍' }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1))
    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_BOOKS, expect.objectContaining({
      title: 'A New Book',
      slug: 'a-new-book',
      tags: ['new', 'reading'],
      reader_path: 'Library/New/9',
      is_public: true,
    }))
    expect(apiClient.get).toHaveBeenCalledTimes(2)
    expect(await screen.findByText('书籍已创建。')).toBeInTheDocument()
  })

  it('keeps edited values and revision when a save conflicts', async () => {
    const user = userEvent.setup()
    apiClient.put.mockRejectedValue({ response: { data: { detail: 'book changed from revision 3 to 4' } } })
    renderPage()

    await user.click(await screen.findByRole('button', { name: '编辑 Blue Notes' }))
    const title = await screen.findByLabelText(/^书名/)
    await user.clear(title)
    await user.type(title, 'Blue Notes Draft')
    await user.click(screen.getByRole('button', { name: '保存书籍' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('book changed from revision 3 to 4')
    expect(title).toHaveValue('Blue Notes Draft')
    expect(apiClient.put).toHaveBeenCalledWith(
      API_ENDPOINTS.ADMIN_BOOK(1),
      expect.objectContaining({ revision: 3, title: 'Blue Notes Draft' }),
    )
  })

  it('edits ordered list membership and sends stable book ids', async () => {
    const user = userEvent.setup()
    apiClient.put.mockResolvedValue({ data: { ...readingList, revision: 3, books: [firstBook] } })
    renderPage()
    await screen.findByText('Blue Notes')

    await user.click(screen.getByRole('tab', { name: '书单' }))
    await user.click(screen.getByRole('button', { name: '编辑 Start here' }))
    const order = screen.getByTestId('book-list-order')
    expect(within(order).getAllByTestId('ordered-book').map((item) => item.textContent)).toEqual([
      expect.stringContaining('Second Book'),
      expect.stringContaining('Blue Notes'),
    ])
    await user.click(screen.getByRole('button', { name: '从书单移除 Second Book' }))
    await user.click(screen.getByRole('button', { name: '保存书单顺序' }))

    expect(apiClient.put).toHaveBeenCalledWith(
      API_ENDPOINTS.ADMIN_BOOK_LIST_ITEMS(7),
      { revision: 2, book_ids: [1] },
    )
    expect(await screen.findByText('书单顺序已保存。')).toBeInTheDocument()
  })

  it('deletes a reading list with its current revision', async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    apiClient.delete.mockResolvedValue({})
    renderPage()
    await screen.findByText('Blue Notes')

    await user.click(screen.getByRole('tab', { name: '书单' }))
    await user.click(screen.getByRole('button', { name: '删除 Start here' }))

    expect(apiClient.delete).toHaveBeenCalledWith(
      API_ENDPOINTS.ADMIN_BOOK_LIST(7),
      { params: { revision: 2 } },
    )
    expect(await screen.findByText('书单已删除。')).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledTimes(2)
    confirm.mockRestore()
  })
})

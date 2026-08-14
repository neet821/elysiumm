import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn() },
}))

import BooksPage from '../src/pages/BooksPage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

const blueNotes = {
  id: 1,
  slug: 'blue-notes',
  title: 'Blue Notes',
  author: 'A. Reader',
  description: 'Reading notes from the quiet shelf.',
  cover_url: '/uploads/books/blue.webp',
  category: 'Notes',
  tags: ['blue', 'notes'],
  reading_status: 'reading',
  reader_url: 'https://books.example.test/kavita/Library/Blue%20Notes/7',
  is_featured: true,
  display_order: 0,
  last_read_at: '2026-07-15T12:00:00Z',
}

const secondBook = {
  ...blueNotes,
  id: 2,
  slug: 'second-book',
  title: 'Second Book',
  author: null,
  category: 'Essays',
  tags: ['essay'],
  reading_status: 'completed',
  reader_url: null,
  is_featured: false,
  display_order: 1,
  last_read_at: null,
}

const catalog = {
  reader_available: true,
  books: [blueNotes, secondBook],
  lists: [{
    id: 4,
    slug: 'start-here',
    title: 'Start here',
    description: 'A short reading path.',
    display_order: 0,
    books: [secondBook, blueNotes],
  }],
  recent: [blueNotes],
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <BooksPage />
    </MemoryRouter>,
  )
}

describe('public Books portal', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
    apiClient.get.mockResolvedValue({ data: catalog })
  })

  it('renders curated shelves, ordered lists, recent reading, and safe explicit reader links', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { name: '书籍' })).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.BOOKS)
    expect(screen.getByRole('heading', { name: '推荐阅读' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '最近阅读' })).toBeInTheDocument()
    const list = screen.getByTestId('book-list-start-here')
    const listedBooks = within(list).getAllByTestId('book-list-item')
    expect(within(listedBooks[0]).getByText('Second Book')).toBeInTheDocument()
    expect(within(listedBooks[1]).getByText('Blue Notes')).toBeInTheDocument()
    const readerLinks = screen.getAllByRole('link', { name: '在 Kavita 中阅读Blue Notes' })
    expect(readerLinks[0]).toHaveAttribute(
      'href',
      'https://books.example.test/kavita/Library/Blue%20Notes/7',
    )
    expect(readerLinks[0]).toHaveAttribute('target', '_blank')
    expect(readerLinks[0]).toHaveAttribute('rel', expect.stringContaining('noopener'))
    expect(document.querySelector('iframe')).not.toBeInTheDocument()
  })

  it('filters locally without changing server order and explains unavailable reading', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Start here')

    await user.type(screen.getByLabelText('搜索书籍'), 'second')
    const allShelf = screen.getByTestId('all-books-shelf')
    expect(within(allShelf).queryByText('Blue Notes')).not.toBeInTheDocument()
    expect(within(allShelf).getByText('Second Book')).toBeInTheDocument()
    expect(within(allShelf).getByText('阅读器暂不可用')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('搜索书籍'))
    await user.selectOptions(screen.getByLabelText('阅读状态'), 'completed')
    expect(within(allShelf).queryByText('Blue Notes')).not.toBeInTheDocument()
    expect(within(allShelf).getByText('Second Book')).toBeInTheDocument()
  })

  it('shows retry, empty, and globally unconfigured reader states truthfully', async () => {
    const user = userEvent.setup()
    apiClient.get.mockRejectedValueOnce({
      response: { data: { detail: 'Books are temporarily unavailable' } },
    })
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Books are temporarily unavailable')
    apiClient.get.mockResolvedValueOnce({
      data: { reader_available: false, books: [], lists: [], recent: [] },
    })
    await user.click(screen.getByRole('button', { name: '重试' }))

    expect(await screen.findByText('暂时没有书籍')).toBeInTheDocument()
    expect(screen.getByText('Kavita 阅读器尚未配置。')).toBeInTheDocument()
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(2))
  })
})

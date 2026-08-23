import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn() },
}))

import ArchivePage from '../src/pages/ArchivePage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

const items = [
  {
    id: 'photo:7',
    source_id: 7,
    type: 'photo',
    title: 'Blue hour',
    excerpt: 'A quiet camera walk.',
    href: null,
    image_url: '/uploads/blue-hour.jpg',
    category: null,
    location: 'Shanghai',
    author_name: null,
    tags: ['travel'],
    created_at: '2026-07-03T12:00:00',
  },
  {
    id: 'writing:3',
    source_id: 3,
    type: 'writing',
    title: 'Archive systems',
    excerpt: 'A normalized timeline.',
    href: '/posts/archive-systems',
    image_url: null,
    category: 'Engineering',
    location: null,
    author_name: 'archivist',
    tags: ['technology'],
    created_at: '2026-07-02T12:00:00',
  },
]

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderArchive(path = '/archive') {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <Routes>
        <Route path="/archive" element={<ArchivePage />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('unified Archive page', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
    apiClient.get.mockResolvedValue({
      data: { items, total: 45, skip: 20, limit: 20 },
    })
  })

  it('uses URL filters and renders the API order as one mixed timeline', async () => {
    renderArchive('/archive?type=all&q=blue&tag=travel&page=2')

    expect(await screen.findByRole('heading', { name: '归档' })).toBeInTheDocument()
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(1))
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ARCHIVE, {
      params: { type: 'all', q: 'blue', tag: 'travel', skip: 20, limit: 20 },
    })

    const renderedItems = screen.getAllByTestId('archive-item')
    expect(within(renderedItems[0]).getByText('Blue hour')).toBeInTheDocument()
    expect(within(renderedItems[1]).getByText('Archive systems')).toBeInTheDocument()
    expect(within(renderedItems[0]).getByRole('img', { name: 'Blue hour' })).toHaveAttribute(
      'src',
      '/uploads/blue-hour.jpg',
    )
    expect(within(renderedItems[1]).getByRole('link', { name: 'Archive systems' })).toHaveAttribute(
      'href',
      '/posts/archive-systems',
    )
  })

  it('keeps type, search, tag, and page state in the URL', async () => {
    const user = userEvent.setup()
    renderArchive('/archive')
    await screen.findByText('Archive systems')

    await user.click(screen.getByRole('button', { name: '文章' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('type=writing'))

    const search = screen.getByLabelText('搜索归档')
    await user.type(search, '  systems  ')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('q=systems'))

    await user.click(screen.getByRole('button', { name: '按 technology 筛选' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('tag=technology'))

    await user.click(screen.getByRole('button', { name: '下一页' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('page=2'))
    expect(apiClient.get).toHaveBeenLastCalledWith(API_ENDPOINTS.ARCHIVE, {
      params: {
        type: 'writing',
        q: 'systems',
        tag: 'technology',
        skip: 20,
        limit: 20,
      },
    })
  })

  it('shows truthful error and empty states without discarding URL filters', async () => {
    const user = userEvent.setup()
    apiClient.get.mockRejectedValueOnce({
      response: { data: { detail: 'Archive is temporarily unavailable' } },
    })
    renderArchive('/archive?type=photo&q=blue')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Archive is temporarily unavailable',
    )
    expect(screen.getByLabelText('搜索归档')).toHaveValue('blue')

    apiClient.get.mockResolvedValueOnce({
      data: { items: [], total: 0, skip: 0, limit: 20 },
    })
    await user.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByText('没有符合筛选条件的内容')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('type=photo')
    expect(screen.getByTestId('location')).toHaveTextContent('q=blue')
  })
})

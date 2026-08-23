import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn() },
}))

import CollectionPage from '../src/pages/CollectionPage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

const publicPayload = {
  folders: [
    { id: 9, name: 'Research', icon: 'book', color: '#315B7D' },
  ],
  bookmarks: [
    {
      id: 4,
      title: 'Open reference',
      url: 'https://example.com/reference',
      description: 'A deliberately public description.',
      favicon: null,
      preview_url: 'https://example.com/preview.jpg',
      tags: ['reference'],
      is_pinned: true,
      visit_count: 12,
      allow_indexing: true,
      created_at: '2026-07-10T12:00:00',
      last_visited_at: '2026-07-12T12:00:00',
      folder: { id: 9, name: 'Research', icon: 'book', color: '#315B7D' },
    },
  ],
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderCollection(path = '/collection') {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <Routes>
        <Route path="/collection" element={<CollectionPage />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('public Collection catalogue', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
    apiClient.get.mockResolvedValue({ data: publicPayload })
  })

  it('always reads only the anonymous public endpoint and renders public metadata', async () => {
    renderCollection('/collection?q=open&folder=9')

    expect(await screen.findByRole('heading', { name: '收藏' })).toBeInTheDocument()
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(1))
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.PUBLIC_COLLECTION, {
      params: { q: 'open', folder_id: 9, limit: 100 },
    })
    expect(apiClient.get).not.toHaveBeenCalledWith(API_ENDPOINTS.BOOKMARKS, expect.anything())
    expect(screen.getByRole('link', { name: /Open reference/ })).toHaveAttribute(
      'href',
      'https://example.com/reference',
    )
    expect(screen.getByText('A deliberately public description.')).toBeInTheDocument()
    expect(screen.getByText('访问 12 次')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Open reference 的预览图' })).toBeInTheDocument()
  })

  it('keeps search and folder browsing in the URL and refetches the public endpoint', async () => {
    const user = userEvent.setup()
    renderCollection()
    await screen.findByText('Open reference')

    await user.click(screen.getByRole('button', { name: 'Research' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('folder=9'))

    const search = screen.getByLabelText('搜索公开收藏')
    await user.type(search, 'archive')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('q=archive'))
    expect(apiClient.get).toHaveBeenLastCalledWith(API_ENDPOINTS.PUBLIC_COLLECTION, {
      params: { q: 'archive', folder_id: 9, limit: 100 },
    })
  })

  it('shows an honest retryable error without discarding active filters', async () => {
    const user = userEvent.setup()
    apiClient.get.mockRejectedValueOnce({ response: { data: { detail: 'Public collection unavailable' } } })
    renderCollection('/collection?q=archive')

    expect(await screen.findByRole('alert')).toHaveTextContent('Public collection unavailable')
    expect(screen.getByLabelText('搜索公开收藏')).toHaveValue('archive')

    apiClient.get.mockResolvedValueOnce({ data: { bookmarks: [], folders: [] } })
    await user.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByText('没有符合筛选条件的公开收藏')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('q=archive')
  })
})

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { delete: vi.fn(), get: vi.fn(), post: vi.fn() },
}))

import AdminFilesPage from '../src/pages/AdminFilesPage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

const syncItems = [
  { name: 'notes.txt', path: 'notes.txt', size: 5 },
  { name: 'docs', path: 'docs/', size: 0 },
]

function mockLoads({ status = 'online', items = syncItems, transfers = [] } = {}) {
  apiClient.get.mockImplementation((endpoint) => {
    if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS) return Promise.resolve({ data: { status } })
    if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE) return Promise.resolve({ data: { path: '', items } })
    if (endpoint === API_ENDPOINTS.ADMIN_TRANSFERS) return Promise.resolve({ data: transfers })
    return Promise.reject(new Error(`unexpected GET ${endpoint}`))
  })
}

describe('administrator Files workspace', () => {
  beforeEach(() => {
    apiClient.delete.mockReset()
    apiClient.get.mockReset()
    apiClient.post.mockReset()
    mockLoads({ transfers: [{ id: 3, total_bytes: 1024, max_bytes: 2048, expires_at: '2026-08-28T08:00:00Z' }] })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('loads the retained file-sync and transfer workspaces', async () => {
    render(<AdminFilesPage />)

    expect(await screen.findByRole('heading', { name: '文件' })).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS)
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE, { params: { path: '' } })
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFERS)
    expect(screen.getByText('notes.txt')).toBeInTheDocument()
    expect(screen.getByText('文件同步')).toBeInTheDocument()
    expect(screen.getByText('文件中转')).toBeInTheDocument()
  })

  it('browses and downloads files from the read-only sync workspace', async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    apiClient.get.mockImplementation((endpoint, options) => {
      if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS) return Promise.resolve({ data: { status: 'online' } })
      if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE) return Promise.resolve({ data: { path: '', items: syncItems } })
      if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_DOWNLOAD) {
        expect(options).toEqual({ params: { path: 'notes.txt' }, responseType: 'blob' })
        return Promise.resolve({ data: new Blob(['hello']) })
      }
      return Promise.resolve({ data: [] })
    })
    render(<AdminFilesPage />)

    await user.click(await screen.findByRole('button', { name: 'notes.txt' }))
    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
  })

  it('creates and destroys anonymous transfer links', async () => {
    const user = userEvent.setup()
    apiClient.post.mockResolvedValue({ data: { token: 'one-time-token' } })
    apiClient.delete.mockResolvedValue({})
    render(<AdminFilesPage />)

    await user.click(await screen.findByRole('button', { name: '创建中转链接' }))
    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFERS)
    expect(await screen.findByDisplayValue(/\/transfer\/one-time-token$/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '销毁中转链接' }))
    await waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER(3)))
  })
})

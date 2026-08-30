import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { delete: vi.fn(), get: vi.fn(), post: vi.fn(), put: vi.fn() },
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
    apiClient.put.mockReset()
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

  it('uploads from the admin page and only reveals the link after upload', async () => {
    const user = userEvent.setup()
    const file = new File(['hello'], '中文资料.txt', { type: 'text/plain' })
    apiClient.post.mockResolvedValue({ data: { token: 'one-time-token' } })
    apiClient.put.mockResolvedValue({ data: { id: 4, name: 'notes.txt', size: 5 } })

    render(<AdminFilesPage />)

    expect(screen.queryByDisplayValue(/\/transfer\/one-time-token$/)).not.toBeInTheDocument()
    await user.upload(screen.getByLabelText('选择文件上传'), file)

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFERS))
    expect(apiClient.put).toHaveBeenCalledWith('/api/transfers/one-time-token', file, {
      timeout: 0,
      params: { filename: '中文资料.txt' },
      headers: { 'Content-Type': 'application/octet-stream' },
    })
    expect(await screen.findByDisplayValue(/\/transfer\/one-time-token$/)).toBeInTheDocument()
  })

  it('keeps a failed transfer available for retry without exposing its link', async () => {
    const user = userEvent.setup()
    const firstFile = new File(['first'], 'first.txt', { type: 'text/plain' })
    const retryFile = new File(['retry'], 'retry.txt', { type: 'text/plain' })
    apiClient.post.mockResolvedValue({ data: { token: 'retryable-token' } })
    apiClient.put
      .mockRejectedValueOnce({ response: { data: { detail: '上传被拒绝。' } } })
      .mockResolvedValueOnce({ data: { id: 5, name: 'retry.txt', size: 5 } })

    render(<AdminFilesPage />)

    await user.upload(screen.getByLabelText('选择文件上传'), firstFile)
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('alert')).toHaveTextContent('上传被拒绝。')
    expect(screen.queryByDisplayValue(/\/transfer\/retryable-token$/)).not.toBeInTheDocument()

    await user.upload(screen.getByLabelText('选择文件上传'), retryFile)
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(2))
    expect(apiClient.post).toHaveBeenCalledTimes(1)
    expect(apiClient.put).toHaveBeenNthCalledWith(2, '/api/transfers/retryable-token', retryFile, {
      timeout: 0,
      params: { filename: 'retry.txt' },
      headers: { 'Content-Type': 'application/octet-stream' },
    })
    expect(await screen.findByDisplayValue(/\/transfer\/retryable-token$/)).toBeInTheDocument()
  })

  it('destroys anonymous transfer links', async () => {
    const user = userEvent.setup()
    apiClient.delete.mockResolvedValue({})
    render(<AdminFilesPage />)

    await user.click(await screen.findByRole('button', { name: '销毁中转链接' }))
    await waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER(3)))
  })
})

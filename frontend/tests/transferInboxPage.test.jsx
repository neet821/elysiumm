import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import TransferInboxPage from '../src/pages/TransferInboxPage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

beforeEach(() => {
  apiClient.get.mockReset()
  apiClient.post.mockReset()
  apiClient.put.mockReset()
  localStorage.clear()
  apiClient.post.mockResolvedValue({ data: { token: 'current-token', url: '/api/transfers/current-token', files: [] } })
})

it('loads every active transfer file from the server for the admin inbox', async () => {
  apiClient.get.mockResolvedValue({ data: [{ id: 1, name: '中文资料.txt', size: 5, sha256: 'b'.repeat(64), transfer_id: 7, expires_at: '2026-08-30T03:00:00Z', download_url: '/api/admin/transfers/files/1/download' }] })

  render(<TransferInboxPage />)

  expect(await screen.findByRole('heading', { name: '全部文件' })).toBeInTheDocument()
  expect(await screen.findByText('中文资料.txt')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '复制分享链接' })).toBeInTheDocument()
  expect(screen.getByLabelText('选择文件上传')).toBeInTheDocument()
  expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER_FILES)
  expect(screen.getByRole('link', { name: /中文资料\.txt/ })).toHaveAttribute('href', '/api/admin/transfers/files/1/download')
  expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER_CURRENT_LINK)
})

it('refreshes the admin inbox from the server without losing uploaded files', async () => {
  apiClient.get
    .mockResolvedValueOnce({ data: [{ id: 1, name: 'first.txt', size: 5, sha256: 'a'.repeat(64), transfer_id: 7, expires_at: '2026-08-30T03:00:00Z', download_url: '/api/admin/transfers/files/1/download' }] })
    .mockResolvedValueOnce({ data: [{ id: 1, name: 'first.txt', size: 5, sha256: 'a'.repeat(64), transfer_id: 7, expires_at: '2026-08-30T03:00:00Z', download_url: '/api/admin/transfers/files/1/download' }, { id: 2, name: 'second.txt', size: 6, sha256: 'b'.repeat(64), transfer_id: 8, expires_at: '2026-08-30T03:00:00Z', download_url: '/api/admin/transfers/files/2/download' }] })

  render(<TransferInboxPage />)
  expect(await screen.findByText('first.txt')).toBeInTheDocument()
  await screen.findByRole('button', { name: '刷新文件' }).then((button) => button.click())

  await waitFor(() => expect(screen.getByText('second.txt')).toBeInTheDocument())
  expect(screen.getByText('first.txt')).toBeInTheDocument()
})

it('uploads from the fixed admin inbox and updates the share link after each file', async () => {
  const user = userEvent.setup()
  const file = new File(['hello'], 'new.txt', { type: 'text/plain' })
  apiClient.get.mockResolvedValue({ data: [] })
  apiClient.put.mockResolvedValue({ data: { token: 'rotated-token', url: '/api/transfers/rotated-token' } })

  render(<TransferInboxPage />)
  await user.upload(screen.getByLabelText('选择文件上传'), file)

  await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith('/api/transfers/current-token', file, expect.objectContaining({
    params: { filename: 'new.txt' },
    onUploadProgress: expect.any(Function),
  })))
  expect(await screen.findByDisplayValue('https://send.elysiumm.top/rotated-token')).toBeInTheDocument()
})

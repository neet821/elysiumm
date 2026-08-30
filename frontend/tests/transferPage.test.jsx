import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn(), put: vi.fn() },
}))

import TransferPage from '../src/pages/TransferPage.jsx'
import apiClient from '../src/utils/request.js'

beforeEach(() => {
  apiClient.get.mockReset()
  apiClient.put.mockReset()
  apiClient.get.mockResolvedValue({
    data: { expires_at: '2026-08-30T03:00:00Z', total_bytes: 0, max_bytes: 2_000_000_000, files: [] },
  })
})

it('uploads a non-ASCII filename without putting it in an HTTP header', async () => {
  const user = userEvent.setup()
  const file = new File(['hello'], '中文资料.txt', { type: 'text/plain' })
  apiClient.put.mockResolvedValue({ data: {} })

  render(
    <MemoryRouter initialEntries={['/transfer/share-token']}>
      <Routes><Route path="/transfer/:token" element={<TransferPage />} /></Routes>
    </MemoryRouter>,
  )

  await screen.findByText('0 B / 1.9 GB')
  await user.upload(screen.getByLabelText('选择文件上传'), file)

  await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith('/api/transfers/share-token', file, expect.objectContaining({
    timeout: 0,
    params: { filename: '中文资料.txt' },
    headers: { 'Content-Type': 'application/octet-stream' },
  })))
  expect(apiClient.put.mock.calls[0][2].onUploadProgress).toEqual(expect.any(Function))
})

it('shows live upload progress while a shared link upload is in flight', async () => {
  const user = userEvent.setup()
  const file = new File(['hello'], 'progress.txt', { type: 'text/plain' })
  let resolveUpload
  apiClient.put.mockImplementation(async (_url, _file, options) => {
    options.onUploadProgress({ loaded: 5, total: 10 })
    await new Promise((resolve) => { resolveUpload = resolve })
    return { data: {} }
  })

  render(
    <MemoryRouter initialEntries={['/transfer/share-token']}>
      <Routes><Route path="/transfer/:token" element={<TransferPage />} /></Routes>
    </MemoryRouter>,
  )

  await screen.findByText('0 B / 1.9 GB')
  await user.upload(screen.getByLabelText('选择文件上传'), file)
  await waitFor(() => expect(screen.getByRole('progressbar', { name: '上传进度' })).toHaveValue(50))
  resolveUpload()
  await waitFor(() => expect(screen.queryByRole('progressbar', { name: '上传进度' })).not.toBeInTheDocument())
})

it('loads already uploaded files again after the shared page is reopened', async () => {
  const uploadedFile = { id: 1, name: '已经上传.txt', size: 5, sha256: 'a'.repeat(64), download_url: '/api/transfers/share-token/files/1' }
  apiClient.get.mockResolvedValue({ data: { expires_at: '2026-08-30T03:00:00Z', total_bytes: 5, max_bytes: 2_000_000_000, files: [uploadedFile] } })

  const first = render(
    <MemoryRouter initialEntries={['/transfer/share-token']}>
      <Routes><Route path="/transfer/:token" element={<TransferPage />} /></Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText('已经上传.txt')).toBeInTheDocument()
  first.unmount()

  render(
    <MemoryRouter initialEntries={['/transfer/share-token']}>
      <Routes><Route path="/transfer/:token" element={<TransferPage />} /></Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText('已经上传.txt')).toBeInTheDocument()
  expect(apiClient.get).toHaveBeenCalledTimes(2)
})

import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../src/utils/request.js', () => ({
  default: { get: vi.fn(), put: vi.fn() },
}))

import TransferPage from '../src/pages/TransferPage.jsx'
import apiClient from '../src/utils/request.js'
import { formatTransferDate } from '../src/utils/transfer.js'

beforeEach(() => {
  apiClient.get.mockReset()
  apiClient.put.mockReset()
  apiClient.get.mockResolvedValue({
    data: { expires_at: '2026-08-30T03:00:00Z', total_bytes: 0, max_bytes: 2_000_000_000, files: [] },
  })
})

it('is a download-only receiver page', async () => {
  apiClient.get.mockResolvedValue({
    data: {
      expires_at: '2026-08-30T04:01:23Z',
      total_bytes: 5,
      max_bytes: 2_000_000_000,
      files: [{ id: 1, name: '中文资料.txt', size: 5, sha256: 'a'.repeat(64), download_url: '/api/transfers/share-token/files/1' }],
    },
  })

  render(
    <MemoryRouter initialEntries={['/transfer/share-token']}>
      <Routes><Route path="/transfer/:token" element={<TransferPage />} /></Routes>
    </MemoryRouter>,
  )

  expect(await screen.findByText('中文资料.txt')).toBeInTheDocument()
  expect(screen.queryByLabelText('选择文件上传')).not.toBeInTheDocument()
  expect(apiClient.put).not.toHaveBeenCalled()
})

it('formats transfer expiry timestamps in Beijing time', () => {
  expect(formatTransferDate('2026-08-30T04:01:23Z')).toContain('2026/8/30')
  expect(formatTransferDate('2026-08-30T04:01:23Z')).toContain('12:01:23')
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

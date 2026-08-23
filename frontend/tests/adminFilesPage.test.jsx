import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { delete: vi.fn(), get: vi.fn(), post: vi.fn() },
}))

import AdminFilesPage from '../src/pages/AdminFilesPage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

const manualFile = {
  id: 11,
  name: 'notes.txt',
  size: 5,
  content_type: 'text/plain',
  modified: '2026-07-16T08:00:00Z',
  download_url: '/api/admin/files/11/download',
}

const device = {
  id: 4,
  name: 'Arch workstation',
  token_hint: 'a1b2',
  token_expires_at: '2026-10-16T08:00:00Z',
  revoked_at: null,
  rotated_at: null,
  root_name: 'Public',
  status: 'online',
  is_paused: false,
  scan_requested: false,
  last_seen_at: '2026-07-16T08:00:00Z',
  created_at: '2026-07-16T07:00:00Z',
}

const pausedDevice = {
  ...device,
  id: 6,
  name: 'Paused laptop',
  token_hint: 'c3d4',
  is_paused: true,
  status: 'offline',
}

const dashboard = {
  devices: [device, pausedDevice],
  files: [{
    id: 21,
    device_id: 4,
    relative_path: 'docs/report.txt',
    file_name: 'report.txt',
    file_size: 6,
    mtime: '2026-07-16T08:00:00Z',
    sync_status: 'uploading',
    bytes_transferred: 3,
    expected_size: 6,
    progress_percent: 50,
    last_synced_at: '2026-07-16T08:00:00Z',
    created_at: '2026-07-16T08:00:00Z',
    updated_at: '2026-07-16T08:00:00Z',
  }],
  events: [{
    id: 31,
    device_id: 4,
    relative_path: 'docs/report.txt',
    event_type: 'upsert',
    status: 'success',
    bytes_transferred: 6,
    created_at: '2026-07-16T08:00:00Z',
  }],
}

function mockLoads({ sync = dashboard, manual = [manualFile] } = {}) {
  apiClient.get.mockImplementation((endpoint) => {
    if (endpoint === API_ENDPOINTS.ADMIN_FILES) return Promise.resolve({ data: manual })
    if (endpoint === API_ENDPOINTS.PUBLIC_SYNC_DASHBOARD) return Promise.resolve({ data: sync })
    return Promise.reject(new Error(`unexpected GET ${endpoint}`))
  })
}

describe('unified administrator Files workspace', () => {
  beforeEach(() => {
    apiClient.delete.mockReset()
    apiClient.get.mockReset()
    apiClient.post.mockReset()
    mockLoads()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('loads all four file workspace tabs', async () => {
    const user = userEvent.setup()
    render(<AdminFilesPage />)

    expect(await screen.findByRole('heading', { name: '文件' })).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_FILES)
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.PUBLIC_SYNC_DASHBOARD)
    expect(screen.getByText('notes.txt')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: '同步设备' }))
    expect(screen.getByText('Arch workstation')).toBeInTheDocument()
    expect(screen.getByText(/凭据尾号 a1b2/)).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: '同步文件' }))
    expect(screen.getByText('docs/report.txt')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'docs/report.txt 的上传进度' })).toHaveAttribute('aria-valuenow', '50')
    await user.click(screen.getByRole('tab', { name: '同步动态' }))
    expect(screen.getByText('更新文件')).toBeInTheDocument()
    expect(screen.getByText('成功')).toBeInTheDocument()
  })

  it('creates a device and clears its one-time secret when the dialog closes', async () => {
    const user = userEvent.setup()
    const clipboard = { writeText: vi.fn().mockResolvedValue(undefined) }
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: clipboard })
    apiClient.post.mockResolvedValue({
      data: { ...device, id: 5, name: 'Laptop', device_token: 'one-time-secret' },
    })
    render(<AdminFilesPage />)

    await user.click(await screen.findByRole('tab', { name: '同步设备' }))
    await user.click(screen.getByRole('button', { name: '添加设备' }))
    await user.type(screen.getByLabelText(/设备名称/), 'Laptop')
    await user.selectOptions(screen.getByLabelText('凭据有效期'), '30')
    await user.click(screen.getByRole('button', { name: '创建设备' }))

    expect(apiClient.post).toHaveBeenCalledWith(
      API_ENDPOINTS.PUBLIC_SYNC_DEVICES,
      expect.any(FormData),
    )
    const dialog = await screen.findByRole('dialog', { name: '保存设备凭据' })
    expect(within(dialog).getByText('one-time-secret')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: '复制凭据' }))
    expect(clipboard.writeText).toHaveBeenCalledWith('one-time-secret')
    await user.click(within(dialog).getByRole('button', { name: '关闭凭据窗口' }))
    expect(screen.queryByText('one-time-secret')).not.toBeInTheDocument()
  })

  it('rotates, revokes, pauses, resumes, and scans a device through stable endpoints', async () => {
    const user = userEvent.setup()
    apiClient.post.mockImplementation((endpoint) => {
      if (endpoint === API_ENDPOINTS.PUBLIC_SYNC_ROTATE(4)) {
        return Promise.resolve({ data: { ...device, device_token: 'rotated-secret' } })
      }
      return Promise.resolve({ data: device })
    })
    render(<AdminFilesPage />)
    await user.click(await screen.findByRole('tab', { name: '同步设备' }))

    await user.click(screen.getByRole('button', { name: '暂停 Arch workstation' }))
    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.PUBLIC_SYNC_PAUSE(4))
    await user.click(screen.getByRole('button', { name: '恢复 Paused laptop' }))
    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.PUBLIC_SYNC_RESUME(6))
    await user.click(screen.getByRole('button', { name: '扫描 Arch workstation' }))
    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.PUBLIC_SYNC_SCAN(4))
    await user.click(screen.getByRole('button', { name: '更新 Arch workstation 的凭据' }))
    expect(apiClient.post).toHaveBeenCalledWith(
      API_ENDPOINTS.PUBLIC_SYNC_ROTATE(4),
      expect.any(FormData),
    )
    expect(await screen.findByText('rotated-secret')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '关闭凭据窗口' }))
    await user.click(screen.getByRole('button', { name: '撤销 Arch workstation' }))
    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.PUBLIC_SYNC_REVOKE(4))
  })

  it('keeps the device draft visible when creation is rejected', async () => {
    const user = userEvent.setup()
    apiClient.post.mockRejectedValue({ response: { data: { detail: 'Device name already exists' } } })
    render(<AdminFilesPage />)

    await user.click(await screen.findByRole('tab', { name: '同步设备' }))
    await user.click(screen.getByRole('button', { name: '添加设备' }))
    const name = screen.getByLabelText(/设备名称/)
    await user.type(name, 'Draft laptop')
    await user.click(screen.getByRole('button', { name: '创建设备' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Device name already exists')
    expect(name).toHaveValue('Draft laptop')
    expect(screen.getByRole('dialog', { name: '添加同步设备' })).toBeInTheDocument()
  })

  it('uploads with progress and downloads and deletes manual files by id', async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    apiClient.post.mockImplementation((endpoint, _body, options) => {
      if (endpoint === API_ENDPOINTS.ADMIN_FILE_UPLOAD) {
        options.onUploadProgress({ loaded: 5, total: 10 })
      }
      return Promise.resolve({ data: manualFile })
    })
    apiClient.get.mockImplementation((endpoint, options) => {
      if (endpoint === API_ENDPOINTS.ADMIN_FILE_DOWNLOAD(11)) {
        expect(options).toEqual({ responseType: 'blob' })
        return Promise.resolve({ data: new Blob(['hello']) })
      }
      if (endpoint === API_ENDPOINTS.ADMIN_FILES) return Promise.resolve({ data: [manualFile] })
      return Promise.resolve({ data: dashboard })
    })
    apiClient.delete.mockResolvedValue({})
    render(<AdminFilesPage />)
    await screen.findByText('notes.txt')

    const input = screen.getByLabelText('上传手动文件')
    await user.upload(input, new File(['hello'], 'new.txt', { type: 'text/plain' }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      API_ENDPOINTS.ADMIN_FILE_UPLOAD,
      expect.any(FormData),
      expect.objectContaining({ onUploadProgress: expect.any(Function) }),
    ))
    await user.click(screen.getByRole('button', { name: '下载 notes.txt' }))
    expect(apiClient.get).toHaveBeenCalledWith(
      API_ENDPOINTS.ADMIN_FILE_DOWNLOAD(11),
      { responseType: 'blob' },
    )
    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
    await user.click(screen.getByRole('button', { name: '删除 notes.txt' }))
    expect(apiClient.delete).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_FILE(11))
  })

  it('uses bounded fallback errors and truthful empty states', async () => {
    const user = userEvent.setup()
    apiClient.get.mockImplementation((endpoint) => {
      if (endpoint === API_ENDPOINTS.ADMIN_FILES) return Promise.resolve({ data: [] })
      return Promise.reject({ response: { data: { detail: { internal: '/private/storage' } } } })
    })
    render(<AdminFilesPage />)

    expect(await screen.findByText('还没有手动文件')).toBeInTheDocument()
    expect(screen.queryByText('/private/storage')).not.toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: '同步设备' }))
    expect(screen.getByRole('alert')).toHaveTextContent('同步信息暂时无法载入。')
    expect(screen.getByText('还没有同步设备')).toBeInTheDocument()
  })
})

import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: { delete: vi.fn(), get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ logout: vi.fn() }),
}))

import AdminFilesPage from '../src/pages/AdminFilesPage.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

const syncItems = [
  { name: 'notes.txt', path: 'notes.txt', size: 5 },
  { name: 'docs', path: 'docs/', size: 0 },
]

function mockLoads({ status = 'online', items = syncItems, transferFiles = [] } = {}) {
  apiClient.get.mockImplementation((endpoint) => {
    if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS) return Promise.resolve({ data: { status } })
    if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE) return Promise.resolve({ data: { path: '', items } })
    if (endpoint === API_ENDPOINTS.ADMIN_TRANSFER_FILES) return Promise.resolve({ data: transferFiles })
    if (endpoint === API_ENDPOINTS.ADMIN_TRANSFER_NOTE) return Promise.resolve({ data: { content: '管理员保留文本' } })
    return Promise.reject(new Error(`unexpected GET ${endpoint}`))
  })
}

describe('administrator Files workspace', () => {
  beforeEach(() => {
    apiClient.delete.mockReset()
    apiClient.get.mockReset()
    apiClient.post.mockReset()
    apiClient.put.mockReset()
    apiClient.post.mockResolvedValue({ data: { token: 'current-token' } })
    mockLoads({ transferFiles: [{ id: 11, name: 'transfer.pdf', size: 1024, transfer_id: 3, expires_at: '2026-08-28T08:00:00Z', download_url: '/api/admin/transfers/files/11/download' }, { id: 12, name: 'video.mp4', size: 2048, transfer_id: 3, expires_at: '2026-08-28T08:00:00Z', download_url: '/api/admin/transfers/files/12/download' }] })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('loads the retained file-sync and transfer workspaces', async () => {
    render(<AdminFilesPage />)

    expect(await screen.findByRole('heading', { name: '文件同步' })).toBeInTheDocument()
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS)
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE, { params: { path: '' } })
    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER_CURRENT_LINK)
    expect(await screen.findByDisplayValue('https://send.elysiumm.top/current-token')).toBeInTheDocument()
    expect(screen.getByText('notes.txt')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'docs' })).not.toBeInTheDocument()
    expect(screen.getByText('transfer.pdf')).toBeInTheDocument()
    expect(screen.getByText('video.mp4')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载 transfer.pdf' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载 video.mp4' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除 transfer.pdf' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除 video.mp4' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '管理员纯文本' })).toHaveValue('管理员保留文本')
    expect(screen.getByText('文件同步')).toBeInTheDocument()
    expect(screen.getByText('文件中转')).toBeInTheDocument()
    expect(screen.queryByText('READ ONLY / FRP')).not.toBeInTheDocument()
    expect(screen.queryByText('ANONYMOUS / 5 MIN IDLE')).not.toBeInTheDocument()
    expect(screen.queryByText(/实时浏览并下载/)).not.toBeInTheDocument()
    expect(screen.queryByText(/在此页直接上传/)).not.toBeInTheDocument()
    expect(screen.queryByText('管理控制台 / 文件')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '文件', level: 2 })).not.toBeInTheDocument()
    expect(screen.queryByText(/中转 #/)).not.toBeInTheDocument()
    expect(screen.queryByText(/过期：/)).not.toBeInTheDocument()
  })

  it('downloads each transfer file from its own row', async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:transfer')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    apiClient.get.mockImplementation((endpoint, options) => {
      if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS) return Promise.resolve({ data: { status: 'online' } })
      if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE) return Promise.resolve({ data: { path: '', items: syncItems } })
      if (endpoint === API_ENDPOINTS.ADMIN_TRANSFER_CURRENT_LINK) return Promise.resolve({ data: { token: 'current-token' } })
      if (endpoint === API_ENDPOINTS.ADMIN_TRANSFER_FILES) return Promise.resolve({ data: [{ id: 11, name: 'transfer.pdf', size: 1024, transfer_id: 3, download_url: '/api/admin/transfers/files/11/download' }] })
      if (endpoint === '/api/admin/transfers/files/11/download') {
        expect(options).toEqual({ responseType: 'blob' })
        return Promise.resolve({ data: new Blob(['file']) })
      }
      return Promise.reject(new Error(`unexpected GET ${endpoint}`))
    })
    render(<AdminFilesPage />)

    await user.click(await screen.findByRole('button', { name: '下载 transfer.pdf' }))
    expect(createObjectURL).toHaveBeenCalled()
    expect(apiClient.get).toHaveBeenCalledWith('/api/admin/transfers/files/11/download', { responseType: 'blob' })
  })

  it('browses and downloads files from the read-only sync workspace', async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const timers = vi.spyOn(window, 'setTimeout')
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
    expect(revokeObjectURL).not.toHaveBeenCalled()
    const releaseBlob = timers.mock.calls.find(([callback]) => callback.toString().includes('revokeObjectURL'))[0]
    releaseBlob()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
  })

  it('does not browse or enable the sync workspace while the PC is offline', async () => {
    mockLoads({ status: 'offline' })
    render(<AdminFilesPage />)

    expect(await screen.findByText('电脑未连接')).toBeInTheDocument()
    expect(apiClient.get).not.toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE, { params: { path: '' } })
  })

  it('keeps the current link visible while uploading from the admin page', async () => {
    const user = userEvent.setup()
    const file = new File(['hello'], '中文资料.txt', { type: 'text/plain' })
    apiClient.put.mockResolvedValue({ data: { id: 4, name: 'notes.txt', size: 5, token: 'rotated-token', url: '/api/transfers/rotated-token' } })

    render(<AdminFilesPage />)

    expect(await screen.findByDisplayValue('https://send.elysiumm.top/current-token')).toBeInTheDocument()
    await user.upload(screen.getByLabelText('选择文件上传'), file)

    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER_CURRENT_LINK)
    expect(apiClient.put).toHaveBeenCalledWith('/api/transfers/current-token', file, expect.objectContaining({
      timeout: 0,
      params: { filename: '中文资料.txt' },
      headers: { 'Content-Type': 'application/octet-stream' },
    }))
    expect(apiClient.put.mock.calls[0][2].onUploadProgress).toEqual(expect.any(Function))
    expect(await screen.findByDisplayValue('https://send.elysiumm.top/rotated-token')).toBeInTheDocument()
  })

  it('keeps a failed transfer available for retry without hiding its link', async () => {
    const user = userEvent.setup()
    const firstFile = new File(['first'], 'first.txt', { type: 'text/plain' })
    const retryFile = new File(['retry'], 'retry.txt', { type: 'text/plain' })
    apiClient.put
      .mockRejectedValueOnce({ response: { data: { detail: '上传被拒绝。' } } })
      .mockResolvedValueOnce({ data: { id: 5, name: 'retry.txt', size: 5, token: 'rotated-retry-token', url: '/api/transfers/rotated-retry-token' } })

    render(<AdminFilesPage />)

    await user.upload(screen.getByLabelText('选择文件上传'), firstFile)
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('alert')).toHaveTextContent('上传被拒绝。')
    expect(screen.getByDisplayValue('https://send.elysiumm.top/current-token')).toBeInTheDocument()

    await user.upload(screen.getByLabelText('选择文件上传'), retryFile)
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(2))
    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER_CURRENT_LINK)
    expect(apiClient.put).toHaveBeenNthCalledWith(2, '/api/transfers/current-token', retryFile, expect.objectContaining({
      timeout: 0,
      params: { filename: 'retry.txt' },
      headers: { 'Content-Type': 'application/octet-stream' },
    }))
    expect(apiClient.put.mock.calls[1][2].onUploadProgress).toEqual(expect.any(Function))
    expect(await screen.findByDisplayValue('https://send.elysiumm.top/rotated-retry-token')).toBeInTheDocument()
  })

  it('shows live upload progress while the transfer request is in flight', async () => {
    const user = userEvent.setup()
    const file = new File(['hello'], 'progress.txt', { type: 'text/plain' })
    let resolveUpload
    apiClient.post.mockResolvedValue({ data: { token: 'progress-token' } })
    apiClient.put.mockImplementation(async (_url, _file, options) => {
      options.onUploadProgress({ loaded: 5, total: 10 })
      await new Promise((resolve) => { resolveUpload = resolve })
      return { data: { id: 6, name: 'progress.txt', size: 5 } }
    })

    render(<AdminFilesPage />)
    await user.upload(screen.getByLabelText('选择文件上传'), file)

    await waitFor(() => expect(screen.getByRole('progressbar', { name: '上传进度' })).toHaveValue(50))
    resolveUpload()
    await waitFor(() => expect(screen.queryByRole('progressbar', { name: '上传进度' })).not.toBeInTheDocument())
  })

  it('autosaves the administrator-only text and supports multiple transfer files', async () => {
    const user = userEvent.setup()
    const firstFile = new File(['one'], 'one.txt', { type: 'text/plain' })
    const secondFile = new File(['two'], 'two.txt', { type: 'text/plain' })
    apiClient.put.mockImplementation((endpoint) => {
      if (endpoint === API_ENDPOINTS.ADMIN_TRANSFER_NOTE) return Promise.resolve({ data: { content: '管理员新文本' } })
      if (endpoint === '/api/transfers/current-token') return Promise.resolve({ data: { id: 7, name: 'one.txt', size: 3, token: 'token-two' } })
      if (endpoint === '/api/transfers/token-two') return Promise.resolve({ data: { id: 8, name: 'two.txt', size: 3, token: 'token-three' } })
      return Promise.reject(new Error(`unexpected PUT ${endpoint}`))
    })

    render(<AdminFilesPage />)

    const note = await screen.findByRole('textbox', { name: '管理员纯文本' })
    await user.clear(note)
    await user.type(note, '管理员新文本')
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER_NOTE, { content: '管理员新文本' }))

    const picker = screen.getByLabelText('选择文件上传')
    expect(picker).toHaveAttribute('multiple')
    await user.upload(picker, [firstFile, secondFile])
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith('/api/transfers/current-token', firstFile, expect.any(Object)))
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith('/api/transfers/token-two', secondFile, expect.any(Object)))
    expect(apiClient.put.mock.calls.filter(([endpoint]) => endpoint.startsWith('/api/transfers/'))).toHaveLength(2)
  })

  it('copies the administrator-only text', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    render(<AdminFilesPage />)

    await user.click(await screen.findByRole('button', { name: '复制文本' }))
    expect(writeText).toHaveBeenCalledWith('管理员保留文本')
    expect(await screen.findByRole('button', { name: '已复制文本' })).toBeInTheDocument()
  })

  it('refreshes the administrator-only text from the server', async () => {
    const originalGet = apiClient.get.getMockImplementation()
    let refresh
    let nextNote = '管理员保留文本'
    const setIntervalSpy = vi.spyOn(window, 'setInterval').mockImplementation((callback, delay) => {
      if (delay === 5000) refresh = callback
      return 1
    })
    apiClient.get.mockImplementation((endpoint, options) => {
      if (endpoint === API_ENDPOINTS.ADMIN_TRANSFER_NOTE) return Promise.resolve({ data: { content: nextNote } })
      return originalGet(endpoint, options)
    })
    render(<AdminFilesPage />)

    expect(await screen.findByRole('textbox', { name: '管理员纯文本' })).toHaveValue('管理员保留文本')
    nextNote = '来自另一台设备的文本'
    expect(refresh).toEqual(expect.any(Function))
    const noteCallsBeforeRefresh = apiClient.get.mock.calls.filter(([endpoint]) => endpoint === API_ENDPOINTS.ADMIN_TRANSFER_NOTE).length
    await act(async () => { await refresh() })
    await waitFor(() => expect(apiClient.get.mock.calls.filter(([endpoint]) => endpoint === API_ENDPOINTS.ADMIN_TRANSFER_NOTE)).toHaveLength(noteCallsBeforeRefresh + 1))
    await waitFor(() => expect(screen.getByRole('textbox', { name: '管理员纯文本' })).toHaveValue('来自另一台设备的文本'))
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 5000)
    setIntervalSpy.mockRestore()
  })

  it('deletes individual transfer files', async () => {
    const user = userEvent.setup()
    apiClient.delete.mockResolvedValue({})
    render(<AdminFilesPage />)

    await user.click(await screen.findByRole('button', { name: '删除 transfer.pdf' }))
    await waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER_FILE(11)))
  })
})

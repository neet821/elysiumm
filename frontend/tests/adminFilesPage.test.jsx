import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const tusMocks = vi.hoisted(() => ({
  files: [],
  error: '',
  ready: true,
  manager: {
    addFiles: vi.fn(),
    pauseResume: vi.fn(),
    retryUpload: vi.fn(),
    retryResult: vi.fn(),
    removeFile: vi.fn(),
  },
  addFiles: vi.fn(),
  useAdminTusUploads: vi.fn(),
  onUploadComplete: null,
}))

vi.mock('../src/utils/request.js', () => ({
  default: { delete: vi.fn(), get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

vi.mock('../src/features/admin-files/useAdminTusUploads.js', () => ({
  useAdminTusUploads: tusMocks.useAdminTusUploads,
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

function mockLoads({ status = 'online', items = syncItems, adminFiles = [], transferFiles = [] } = {}) {
  apiClient.get.mockImplementation((endpoint) => {
    if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS) return Promise.resolve({ data: { status } })
    if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE) return Promise.resolve({ data: { path: '', items } })
    if (endpoint === API_ENDPOINTS.ADMIN_FILES) return Promise.resolve({ data: adminFiles })
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
    apiClient.post.mockResolvedValue({ data: { id: 3, token: 'current-token' } })
    tusMocks.files = []
    tusMocks.error = ''
    tusMocks.ready = true
    tusMocks.onUploadComplete = null
    Object.values(tusMocks.manager).forEach((method) => method.mockReset())
    tusMocks.addFiles = tusMocks.manager.addFiles
    tusMocks.useAdminTusUploads.mockImplementation((options) => {
      tusMocks.onUploadComplete = options.onUploadComplete
      return tusMocks
    })
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

  it('lists and downloads private administrator files', async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:private')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    apiClient.get.mockImplementation((endpoint, options) => {
      if (endpoint === API_ENDPOINTS.ADMIN_FILES) return Promise.resolve({ data: [{ id: 9, name: 'private.txt', size: 6, download_url: '/api/admin/files/9/download' }] })
      if (endpoint === '/api/admin/files/9/download') {
        expect(options).toEqual({ responseType: 'blob' })
        return Promise.resolve({ data: new Blob(['secret']) })
      }
      if (endpoint === API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS) return Promise.resolve({ data: { status: 'offline' } })
      if (endpoint === API_ENDPOINTS.ADMIN_TRANSFER_CURRENT_LINK) return Promise.resolve({ data: { id: 3, token: 'current-token' } })
      if (endpoint === API_ENDPOINTS.ADMIN_TRANSFER_FILES) return Promise.resolve({ data: [] })
      if (endpoint === API_ENDPOINTS.ADMIN_TRANSFER_NOTE) return Promise.resolve({ data: { content: '' } })
      return Promise.reject(new Error(`unexpected GET ${endpoint}`))
    })
    render(<AdminFilesPage />)

    expect(await screen.findByRole('heading', { name: '管理员文件' })).toBeInTheDocument()
    expect(await screen.findByText('private.txt')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '下载 private.txt' }))

    expect(createObjectURL).toHaveBeenCalled()
    expect(apiClient.get).toHaveBeenCalledWith('/api/admin/files/9/download', { responseType: 'blob' })
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

  it('adds transfer uploads to the resumable queue and rotates the link only after server confirmation', async () => {
    const user = userEvent.setup()
    const file = new File(['hello'], '中文资料.txt', { type: 'text/plain' })

    render(<AdminFilesPage />)

    expect(await screen.findByDisplayValue('https://send.elysiumm.top/current-token')).toBeInTheDocument()
    await user.upload(screen.getByLabelText('选择文件上传'), file)

    expect(apiClient.post).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER_CURRENT_LINK)
    expect(tusMocks.manager.addFiles).toHaveBeenCalledWith([file], { purpose: 'transfer_file', sessionId: 3 })
    expect(screen.getByDisplayValue('https://send.elysiumm.top/current-token')).toBeInTheDocument()

    await tusMocks.onUploadComplete({ token: 'rotated-token' }, { meta: { purpose: 'transfer_file', session_id: '3' } })
    expect(await screen.findByDisplayValue('https://send.elysiumm.top/rotated-token')).toBeInTheDocument()
  })

  it('uses the same resumable queue for administrator-private file uploads', async () => {
    const user = userEvent.setup()
    const file = new File(['private'], 'private.txt', { type: 'text/plain' })

    render(<AdminFilesPage />)

    await user.upload(screen.getByLabelText('选择管理员文件上传'), file)
    expect(tusMocks.manager.addFiles).toHaveBeenCalledWith([file], { purpose: 'admin_file', sessionId: 3 })
  })

  it('keeps file browsing available when the optional local tusd service is unavailable', async () => {
    tusMocks.ready = false
    tusMocks.error = '本地预览中的可续传上传服务未启动；其他文件功能仍可使用。'
    render(<AdminFilesPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/其他文件功能仍可使用/)
    expect(screen.getByLabelText('选择管理员文件上传')).toBeDisabled()
    expect(screen.getByLabelText('选择文件上传')).toBeDisabled()
    expect(screen.getByRole('button', { name: '下载 transfer.pdf' })).toBeInTheDocument()
  })

  it('autosaves the administrator-only text and supports multiple transfer files', async () => {
    const user = userEvent.setup()
    const firstFile = new File(['one'], 'one.txt', { type: 'text/plain' })
    const secondFile = new File(['two'], 'two.txt', { type: 'text/plain' })
    apiClient.put.mockResolvedValue({ data: { content: '管理员新文本' } })

    render(<AdminFilesPage />)

    const note = await screen.findByRole('textbox', { name: '管理员纯文本' })
    await user.clear(note)
    await user.type(note, '管理员新文本')
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TRANSFER_NOTE, { content: '管理员新文本' }))

    const picker = screen.getByLabelText('选择文件上传')
    expect(picker).toHaveAttribute('multiple')
    await user.upload(picker, [firstFile, secondFile])
    expect(tusMocks.manager.addFiles).toHaveBeenCalledWith([firstFile, secondFile], { purpose: 'transfer_file', sessionId: 3 })
    expect(apiClient.put.mock.calls.filter(([endpoint]) => String(endpoint).startsWith('/api/transfers/'))).toHaveLength(0)
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

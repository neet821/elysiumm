import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'

import { createAdminTusUploads } from '../src/features/admin-files/adminTusUploads.js'
import { useAdminTusUploads } from '../src/features/admin-files/useAdminTusUploads.js'
import { API_ENDPOINTS } from '../src/config.js'

class FakeUppy {
  constructor(options) {
    this.options = options
    this.files = new Map()
    this.listeners = new Map()
    this.plugins = []
    FakeUppy.lastInstance = this
  }

  use(Plugin, options) {
    this.plugins.push({ Plugin, options })
    return this
  }

  on(event, callback) {
    const callbacks = this.listeners.get(event) || []
    callbacks.push(callback)
    this.listeners.set(event, callbacks)
    return this
  }

  emit(event, ...args) {
    if (event === 'upload-progress') {
      const [file, progress] = args
      this.files.set(file.id, {
        ...file,
        progress: { ...file.progress, ...progress, percentage: Math.round((progress.bytesUploaded / progress.bytesTotal) * 100), uploadStarted: Date.now() },
      })
      args[0] = this.files.get(file.id)
    }
    if (event === 'upload-success') {
      const [file] = args
      this.files.set(file.id, { ...file, progress: { ...file.progress, percentage: 100, uploadComplete: true } })
      args[0] = this.files.get(file.id)
    }
    for (const callback of this.listeners.get(event) || []) callback(...args)
  }

  addFile(file) {
    this.files.set(file.id, { ...file, progress: { percentage: 0, bytesUploaded: 0, bytesTotal: file.data.size } })
    this.emit('file-added', this.files.get(file.id))
    return file.id
  }

  getFiles() {
    return [...this.files.values()]
  }

  getFile(id) {
    return this.files.get(id)
  }

  pauseResume(id) {
    this.pausedId = id
  }

  retryUpload(id) {
    this.retriedId = id
  }

  removeFile(id) {
    const file = this.files.get(id)
    this.files.delete(id)
    this.emit('file-removed', file)
  }

  destroy() {
    this.destroyed = true
  }
}

class FakeTus {}

const apiClient = { get: vi.fn() }

describe('admin resumable uploads', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  beforeEach(() => {
    localStorage.clear()
    apiClient.get.mockReset()
  })

  it('keeps upload controls unavailable when local preview has no tusd service', async () => {
    vi.stubEnv('VITE_TUS_UPLOADS_ENABLED', 'false')
    const { result } = renderHook(() => useAdminTusUploads({}))

    await vi.waitFor(() => expect(result.current.error).toMatch(/可续传上传服务未启动/))
    expect(result.current.ready).toBe(false)
    expect(result.current.manager).toBeNull()
  })

  it('uses same-origin admin tus, attaches the current admin token, and fetches a committed result', async () => {
    localStorage.setItem('token', 'fresh-admin-token')
    const onUploadComplete = vi.fn()
    const onChange = vi.fn()
    const onError = vi.fn()
    apiClient.get.mockResolvedValue({ data: { id: 9, name: 'private.txt', size: 5, download_url: '/api/admin/files/9/download' } })
    const queue = createAdminTusUploads({ Uppy: FakeUppy, Tus: FakeTus, apiClient, onChange, onError, onUploadComplete })
    const file = new File(['hello'], 'private.txt', { type: 'text/plain', lastModified: 100 })

    const [fileId] = queue.addFiles([file], { purpose: 'admin_file' })
    const uppy = FakeUppy.lastInstance
    const tusOptions = uppy.plugins[0].options
    expect(uppy.options).toMatchObject({ id: 'elysium-admin-file-uploads', autoProceed: true, allowMultipleUploadBatches: true })
    expect(tusOptions).toMatchObject({ endpoint: API_ENDPOINTS.ADMIN_TUS, limit: 1, allowedMetaFields: ['filename', 'filetype', 'purpose', 'session_id'] })
    expect(uppy.getFile(fileId).meta).toMatchObject({ filename: 'private.txt', filetype: 'text/plain', purpose: 'admin_file' })

    const request = { setHeader: vi.fn() }
    await tusOptions.onBeforeRequest(request, uppy.getFile(fileId))
    expect(request.setHeader).toHaveBeenCalledWith('Authorization', 'Bearer fresh-admin-token')

    uppy.emit('upload-progress', uppy.getFile(fileId), { bytesUploaded: 2, bytesTotal: 5 })
    expect(onChange).toHaveBeenLastCalledWith(expect.arrayContaining([
      expect.objectContaining({ id: fileId, name: 'private.txt', purpose: 'admin_file', progress: 40 }),
    ]))

    const uploadId = '0123456789abcdef0123456789abcdef'
    uppy.emit('upload-success', uppy.getFile(fileId), { uploadURL: `${window.location.origin}/api/admin/tus/${uploadId}` })
    await vi.waitFor(() => expect(onUploadComplete).toHaveBeenCalledWith(
      { id: 9, name: 'private.txt', size: 5, download_url: '/api/admin/files/9/download' },
      expect.objectContaining({ meta: expect.objectContaining({ purpose: 'admin_file' }) }),
    ))
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.ADMIN_TUS_RESULT(uploadId))
    expect(onError).not.toHaveBeenCalled()

    const [nextFileId] = queue.addFiles([file], { purpose: 'admin_file' })
    expect(nextFileId).not.toBe(fileId)
    queue.close()
    expect(uppy.destroyed).toBe(true)
  })

  it('reuses the same resume identity only for the same transfer session and exposes queue controls', () => {
    const file = new File(['part'], 'archive.zip', { type: 'application/zip', lastModified: 200 })
    const firstQueue = createAdminTusUploads({ Uppy: FakeUppy, Tus: FakeTus, apiClient })
    const [firstId] = firstQueue.addFiles([file], { purpose: 'transfer_file', sessionId: 41 })
    const firstUppy = FakeUppy.lastInstance
    const metadata = firstUppy.getFile(firstId).meta
    expect(metadata).toMatchObject({ filename: 'archive.zip', filetype: 'application/zip', purpose: 'transfer_file', session_id: '41' })
    expect(metadata).not.toHaveProperty('relativePath')
    firstQueue.close()

    const resumedQueue = createAdminTusUploads({ Uppy: FakeUppy, Tus: FakeTus, apiClient })
    const [resumedId] = resumedQueue.addFiles([file], { purpose: 'transfer_file', sessionId: 41 })
    const resumedUppy = FakeUppy.lastInstance
    expect(resumedId).toBe(firstId)

    const [otherSessionId] = resumedQueue.addFiles([file], { purpose: 'transfer_file', sessionId: 42 })
    expect(otherSessionId).not.toBe(firstId)
    resumedQueue.pauseResume(firstId)
    resumedQueue.retryUpload(firstId)
    expect(resumedUppy.pausedId).toBe(firstId)
    expect(resumedUppy.retriedId).toBe(firstId)

    resumedQueue.removeFile(firstId)
    const [afterCancelId] = resumedQueue.addFiles([file], { purpose: 'transfer_file', sessionId: 41 })
    expect(afterCancelId).not.toBe(firstId)
    resumedQueue.close()
  })

  it('sends a successful transfer result to the UI only after the server rotates its link token', async () => {
    const onUploadComplete = vi.fn()
    apiClient.get.mockResolvedValue({ data: { id: 12, name: 'shared.pdf', size: 8, token: 'rotated-token', url: '/api/transfers/rotated-token' } })
    const queue = createAdminTusUploads({ Uppy: FakeUppy, Tus: FakeTus, apiClient, onUploadComplete })
    const [fileId] = queue.addFiles([new File(['12345678'], 'shared.pdf', { type: 'application/pdf' })], { purpose: 'transfer_file', sessionId: 7 })
    FakeUppy.lastInstance.emit('upload-success', FakeUppy.lastInstance.getFile(fileId), {
      uploadURL: `${window.location.origin}/api/admin/tus/abcdef0123456789abcdef0123456789`,
    })

    await vi.waitFor(() => expect(onUploadComplete).toHaveBeenCalledWith(
      { id: 12, name: 'shared.pdf', size: 8, token: 'rotated-token', url: '/api/transfers/rotated-token' },
      expect.objectContaining({ meta: expect.objectContaining({ purpose: 'transfer_file', session_id: '7' }) }),
    ))
    queue.close()
  })
})

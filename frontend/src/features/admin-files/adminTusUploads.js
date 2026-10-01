import { API_ENDPOINTS } from '../../config.js'
import defaultApiClient from '../../utils/request.js'

const UPLOAD_ID = /^[0-9a-f]{32}$/
const RESUME_KEY_PREFIX = 'elysium-admin-tus-pending:'
const ALLOWED_METADATA = ['filename', 'filetype', 'purpose', 'session_id']

function resumeStorageKey(file, purpose, sessionId) {
  return RESUME_KEY_PREFIX + encodeURIComponent(JSON.stringify([
    purpose,
    sessionId || '',
    file.name,
    file.size,
    file.lastModified || 0,
    file.type || '',
  ]))
}

function newUploadIdentity() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID().replaceAll('-', '')
  const bytes = new Uint8Array(16)
  globalThis.crypto.getRandomValues(bytes)
  return [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

function uploadIdFromUrl(uploadURL) {
  let parsed
  try {
    parsed = new URL(uploadURL, window.location.origin)
  } catch {
    throw new Error('上传服务返回了无效地址。')
  }
  if (parsed.origin !== window.location.origin) throw new Error('上传服务返回了站外地址。')
  const match = parsed.pathname.match(/^\/api\/admin\/tus\/([0-9a-f]{32})$/)
  if (!match || !UPLOAD_ID.test(match[1])) throw new Error('上传服务返回了无效任务编号。')
  return match[1]
}

function fileSnapshot(file, completedIds, resultErrors) {
  const progress = file.progress || {}
  let status = 'queued'
  if (resultErrors.has(file.id)) status = 'result_error'
  else if (completedIds.has(file.id) || progress.uploadComplete) status = 'complete'
  else if (file.error) status = 'failed'
  else if (file.isPaused) status = 'paused'
  else if (progress.uploadStarted) status = 'uploading'

  return {
    id: file.id,
    name: file.name,
    purpose: file.meta?.purpose,
    status,
    progress: Number(progress.percentage) || 0,
    bytesUploaded: Number(progress.bytesUploaded) || 0,
    bytesTotal: Number(progress.bytesTotal) || Number(file.data?.size) || 0,
    error: resultErrors.get(file.id) || (typeof file.error === 'string' ? file.error : file.error?.message) || '',
  }
}

export function createAdminTusUploads({
  Uppy,
  Tus,
  apiClient = defaultApiClient,
  onChange = () => {},
  onError = () => {},
  onUploadComplete = async () => {},
}) {
  const uppy = new Uppy({
    id: 'elysium-admin-file-uploads',
    autoProceed: true,
    allowMultipleUploadBatches: true,
  })
  const pendingKeys = new Map()
  const completedIds = new Set()
  const resultErrors = new Map()
  const resultTargets = new Map()

  const publish = () => {
    onChange(uppy.getFiles().map((file) => fileSnapshot(file, completedIds, resultErrors)))
  }

  uppy.use(Tus, {
    endpoint: API_ENDPOINTS.ADMIN_TUS,
    chunkSize: 8 * 1024 * 1024,
    limit: 1,
    retryDelays: [0, 1000, 3000, 5000],
    allowedMetaFields: ALLOWED_METADATA,
    onBeforeRequest(request) {
      const token = localStorage.getItem('token')
      if (!token) throw new Error('管理员登录已失效，请重新登录后重试。')
      request.setHeader('Authorization', `Bearer ${token}`)
    },
  })

  for (const event of ['file-added', 'file-removed', 'upload-progress', 'upload-start', 'upload-pause', 'upload-retry', 'complete']) {
    uppy.on(event, publish)
  }

  uppy.on('upload-error', (file, error, response) => {
    if (response?.status === 401) {
      // Let the existing Axios auth interceptor refresh the session or redirect to login.
      void apiClient.get(API_ENDPOINTS.USER_INFO).catch(() => {})
    }
    onError(error)
    publish()
  })

  async function confirmResult(fileId) {
    const target = resultTargets.get(fileId)
    if (!target) return
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_TUS_RESULT(target.uploadId))
      const result = response.data
      await onUploadComplete(result, target.file)
      completedIds.add(fileId)
      resultErrors.delete(fileId)
      const key = pendingKeys.get(fileId) || resumeStorageKey(
        target.file.data,
        target.file.meta.purpose,
        target.file.meta.session_id,
      )
      if (localStorage.getItem(key) === fileId) localStorage.removeItem(key)
      pendingKeys.delete(fileId)
      resultTargets.delete(fileId)
    } catch (error) {
      resultErrors.set(fileId, error?.message || '上传已完成，但刷新结果失败。')
      onError(new Error(`文件“${target.file.name}”已上传，结果同步失败；可重试同步。`))
    }
    publish()
  }

  uppy.on('upload-success', (file, response) => {
    try {
      resultTargets.set(file.id, { file, uploadId: uploadIdFromUrl(response?.uploadURL) })
      void confirmResult(file.id)
    } catch (error) {
      resultErrors.set(file.id, error.message)
      onError(error)
      publish()
    }
  })

  uppy.on('file-removed', (file) => {
    if (resultTargets.has(file.id)) return
    const key = pendingKeys.get(file.id)
    if (key && localStorage.getItem(key) === file.id) localStorage.removeItem(key)
    pendingKeys.delete(file.id)
  })

  return {
    addFiles(files, { purpose, sessionId } = {}) {
      if (!['admin_file', 'transfer_file'].includes(purpose)) throw new Error('上传用途无效。')
      if (purpose === 'transfer_file' && !/^\d+$/.test(String(sessionId || ''))) {
        throw new Error('请先准备有效的文件中转链接。')
      }
      const ids = []
      for (const file of files) {
        const key = resumeStorageKey(file, purpose, sessionId)
        let id = localStorage.getItem(key)
        if (!id) {
          id = newUploadIdentity()
          localStorage.setItem(key, id)
        }
        pendingKeys.set(id, key)
        try {
          ids.push(uppy.addFile({
            id,
            name: file.name,
            type: file.type || 'application/octet-stream',
            data: file,
            meta: {
              filename: file.name,
              filetype: file.type || 'application/octet-stream',
              purpose,
              ...(purpose === 'transfer_file' ? { session_id: String(sessionId) } : {}),
            },
          }))
        } catch (error) {
          if (localStorage.getItem(key) === id) localStorage.removeItem(key)
          pendingKeys.delete(id)
          onError(error)
        }
      }
      return ids
    },
    pauseResume(fileId) {
      return uppy.pauseResume(fileId)
    },
    retryUpload(fileId) {
      return uppy.retryUpload(fileId)
    },
    retryResult(fileId) {
      return confirmResult(fileId)
    },
    removeFile(fileId) {
      uppy.removeFile(fileId)
    },
    close() {
      uppy.destroy()
    },
  }
}

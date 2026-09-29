import { useCallback, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { TRANSFER_CURRENT_TOKEN_KEY, transferPublicUrl } from '../../utils/transfer.js'
import { getAdminFilesError, saveBlob } from './adminFilesUtils.js'
import { useAdminTusUploads } from './useAdminTusUploads.js'


export function useAdminTransferWorkspace({ loadAdminFiles, setError }) {
  const [transferFiles, setTransferFiles] = useState([])
  const [transfer, setTransfer] = useState(null)
  const [copied, setCopied] = useState(false)
  const [adminNote, setAdminNote] = useState('')
  const [noteSaving, setNoteSaving] = useState(false)
  const [noteSaved, setNoteSaved] = useState(false)
  const [noteCopied, setNoteCopied] = useState(false)
  const noteSaveTimer = useRef(null)
  const noteContentRef = useRef('')
  const noteDirtyRef = useRef(false)

  const loadTransferFiles = useCallback(async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_TRANSFER_FILES)
      setTransferFiles(Array.isArray(response.data) ? response.data : [])
    } catch (reason) {
      setError(getAdminFilesError(reason, '中转文件暂时无法载入。'))
    }
  }, [setError])

  const loadCurrentTransfer = useCallback(async () => {
    try {
      const response = await apiClient.post(API_ENDPOINTS.ADMIN_TRANSFER_CURRENT_LINK)
      const token = response.data?.token
      if (!token) throw new Error('分享链接创建失败。')
      localStorage.setItem(TRANSFER_CURRENT_TOKEN_KEY, token)
      setTransfer({ id: response.data?.id, token, url: transferPublicUrl(token), ready: true })
      return token
    } catch (reason) {
      setError(getAdminFilesError(reason, '中转链接暂时无法载入。'))
      return null
    }
  }, [setError])

  const loadAdminNote = useCallback(async () => {
    if (noteDirtyRef.current) return
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_TRANSFER_NOTE)
      const content = typeof response.data?.content === 'string' ? response.data.content : ''
      noteContentRef.current = content
      setAdminNote(content)
      setNoteSaved(false)
    } catch (reason) {
      setError(getAdminFilesError(reason, '管理员文本暂时无法载入。'))
    }
  }, [setError])

  const saveAdminNote = useCallback(async (content) => {
    setNoteSaving(true)
    try {
      await apiClient.put(API_ENDPOINTS.ADMIN_TRANSFER_NOTE, { content })
      if (noteContentRef.current === content) noteDirtyRef.current = false
      setNoteSaved(true)
    } catch (reason) {
      setError(getAdminFilesError(reason, '管理员文本保存失败。'))
    } finally {
      setNoteSaving(false)
    }
  }, [setError])

  const handleTusUploadComplete = useCallback(async (result, file) => {
    if (file.meta?.purpose === 'transfer_file') {
      if (!result?.token) throw new Error('文件已上传，但中转链接尚未更新。')
      localStorage.setItem(TRANSFER_CURRENT_TOKEN_KEY, result.token)
      setTransfer((current) => ({
        ...current,
        id: Number(file.meta.session_id) || current?.id,
        token: result.token,
        url: transferPublicUrl(result.token),
        ready: true,
      }))
      await loadTransferFiles()
      return
    }
    await loadAdminFiles()
  }, [loadAdminFiles, loadTransferFiles])

  const tusUploads = useAdminTusUploads({ onUploadComplete: handleTusUploadComplete })

  function editAdminNote(event) {
    const content = event.target.value
    noteContentRef.current = content
    noteDirtyRef.current = true
    setAdminNote(content)
    setNoteSaved(false)
    if (noteSaveTimer.current) window.clearTimeout(noteSaveTimer.current)
    noteSaveTimer.current = window.setTimeout(() => saveAdminNote(content), 500)
  }

  async function copyAdminNote() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(adminNote)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = adminNote
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    setNoteCopied(true)
    window.setTimeout(() => setNoteCopied(false), 1600)
  }

  function addSelectedFiles(event, purpose) {
    const input = event.currentTarget
    const files = Array.from(input.files || [])
    if (!files.length) return
    try {
      setError('')
      tusUploads.addFiles(files, { purpose, sessionId: transfer?.id })
    } catch (reason) {
      setError(getAdminFilesError(reason, '文件上传失败。'))
    } finally {
      input.value = ''
    }
  }

  async function copyShareLink() {
    if (!transfer?.url) return
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(transfer.url)
    } catch {
      const input = document.createElement('input')
      input.value = transfer.url
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      input.remove()
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  async function deleteTransferFile(item) {
    if (!window.confirm(`删除已上传文件“${item.name}”？`)) return
    try {
      await apiClient.delete(API_ENDPOINTS.ADMIN_TRANSFER_FILE(item.id))
      await loadTransferFiles()
    } catch (reason) {
      setError(getAdminFilesError(reason, '文件删除失败。'))
    }
  }

  async function downloadTransfer(item) {
    try {
      const response = await apiClient.get(item.download_url, { responseType: 'blob' })
      saveBlob(response.data, item.name)
    } catch (reason) {
      setError(getAdminFilesError(reason, '文件下载失败。'))
    }
  }

  const clearNoteSaveTimer = useCallback(() => {
    if (noteSaveTimer.current) window.clearTimeout(noteSaveTimer.current)
    noteSaveTimer.current = null
  }, [])

  return {
    addSelectedFiles,
    adminNote,
    clearNoteSaveTimer,
    copied,
    copyAdminNote,
    copyShareLink,
    deleteTransferFile,
    downloadTransfer,
    editAdminNote,
    loadAdminNote,
    loadCurrentTransfer,
    loadTransferFiles,
    noteCopied,
    noteSaved,
    noteSaving,
    transfer,
    transferFiles,
    tusUploads,
  }
}

import { useCallback, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { getAdminFilesError } from './adminFilesUtils.js'


export function useAdminNote(setError) {
  const [adminNote, setAdminNote] = useState('')
  const [noteSaving, setNoteSaving] = useState(false)
  const [noteSaved, setNoteSaved] = useState(false)
  const [noteCopied, setNoteCopied] = useState(false)
  const noteSaveTimer = useRef(null)
  const noteContentRef = useRef('')
  const noteDirtyRef = useRef(false)

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

  const clearNoteSaveTimer = useCallback(() => {
    if (noteSaveTimer.current) window.clearTimeout(noteSaveTimer.current)
    noteSaveTimer.current = null
  }, [])

  return {
    adminNote,
    clearNoteSaveTimer,
    copyAdminNote,
    editAdminNote,
    loadAdminNote,
    noteCopied,
    noteSaved,
    noteSaving,
  }
}

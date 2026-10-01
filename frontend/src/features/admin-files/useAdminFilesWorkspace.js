import { useEffect, useState } from 'react'

import { useAdminPrivateFiles } from './useAdminPrivateFiles.js'
import { useAdminNote } from './useAdminNote.js'
import { useAdminSyncBrowser } from './useAdminSyncBrowser.js'
import { useAdminTransferWorkspace } from './useAdminTransferWorkspace.js'


export function useAdminFilesWorkspace() {
  const [error, setError] = useState('')
  const sync = useAdminSyncBrowser(setError)
  const privateFiles = useAdminPrivateFiles(setError)
  const note = useAdminNote(setError)
  const transfer = useAdminTransferWorkspace({
    loadAdminFiles: privateFiles.loadAdminFiles,
    setError,
  })
  const {
    clearNoteSaveTimer,
    loadAdminNote,
  } = note
  const { loadCurrentTransfer, loadTransferFiles } = transfer
  const { loadAdminFiles } = privateFiles
  const { loadSync } = sync

  useEffect(() => {
    loadSync('')
    loadAdminFiles()
    loadTransferFiles()
    loadCurrentTransfer()
    loadAdminNote()
  }, [
    loadAdminFiles,
    loadAdminNote,
    loadCurrentTransfer,
    loadSync,
    loadTransferFiles,
  ])

  useEffect(() => {
    const refreshTimer = window.setInterval(loadAdminNote, 5000)
    return () => window.clearInterval(refreshTimer)
  }, [loadAdminNote])

  useEffect(() => () => clearNoteSaveTimer(), [clearNoteSaveTimer])

  const refresh = () => {
    loadSync(sync.sync.path)
    loadAdminFiles()
    loadTransferFiles()
    loadCurrentTransfer()
    loadAdminNote()
  }

  return {
    ...sync,
    ...privateFiles,
    ...note,
    ...transfer,
    error,
    refresh,
  }
}

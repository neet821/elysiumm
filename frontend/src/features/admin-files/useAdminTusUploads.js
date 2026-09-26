import { useCallback, useEffect, useRef, useState } from 'react'

import { createAdminTusUploads } from './adminTusUploads.js'

const errorMessage = (error) => error?.response?.data?.detail || error?.message || '文件上传失败。'

export function useAdminTusUploads({ onUploadComplete }) {
  const [files, setFiles] = useState([])
  const [error, setError] = useState('')
  const [ready, setReady] = useState(false)
  const managerRef = useRef(null)
  const callbacksRef = useRef({ onUploadComplete })
  callbacksRef.current = { onUploadComplete }
  const enabled = import.meta.env.VITE_TUS_UPLOADS_ENABLED !== 'false'

  useEffect(() => {
    let mounted = true
    let manager

    if (!enabled) {
      setError('本地预览中的可续传上传服务未启动；其他文件功能仍可使用。')
      return () => {
        mounted = false
      }
    }

    Promise.all([import('@uppy/core'), import('@uppy/tus')])
      .then(([uppyModule, tusModule]) => {
        if (!mounted) return
        manager = createAdminTusUploads({
          Uppy: uppyModule.default,
          Tus: tusModule.default,
          onChange: setFiles,
          onError: (reason) => setError(errorMessage(reason)),
          onUploadComplete: (...args) => callbacksRef.current.onUploadComplete?.(...args),
        })
        managerRef.current = manager
        setReady(true)
      })
      .catch((reason) => {
        if (mounted) setError(errorMessage(reason))
      })

    return () => {
      mounted = false
      manager?.close()
      managerRef.current = null
    }
  }, [enabled])

  const addFiles = useCallback((selectedFiles, options) => {
    if (!managerRef.current) {
      setError('上传组件仍在准备，请稍后重试。')
      return []
    }
    setError('')
    try {
      return managerRef.current.addFiles(selectedFiles, options)
    } catch (reason) {
      setError(errorMessage(reason))
      return []
    }
  }, [])

  const clearError = useCallback(() => setError(''), [])
  const manager = managerRef.current

  return { files, error, ready, manager, addFiles, clearError }
}

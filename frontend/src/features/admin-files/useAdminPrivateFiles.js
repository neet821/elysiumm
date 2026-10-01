import { useCallback, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { getAdminFilesError, saveBlob } from './adminFilesUtils.js'


export function useAdminPrivateFiles(setError) {
  const [adminFiles, setAdminFiles] = useState([])

  const loadAdminFiles = useCallback(async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_FILES)
      setAdminFiles(Array.isArray(response.data) ? response.data : [])
    } catch (reason) {
      setError(getAdminFilesError(reason, '管理员文件暂时无法载入。'))
    }
  }, [setError])

  async function deleteAdminFile(item) {
    if (!window.confirm(`删除管理员文件“${item.name}”？`)) return
    try {
      await apiClient.delete(API_ENDPOINTS.ADMIN_FILE(item.id))
      await loadAdminFiles()
    } catch (reason) {
      setError(getAdminFilesError(reason, '管理员文件删除失败。'))
    }
  }

  async function downloadAdminFile(item) {
    try {
      const response = await apiClient.get(item.download_url, { responseType: 'blob' })
      saveBlob(response.data, item.name)
    } catch (reason) {
      setError(getAdminFilesError(reason, '管理员文件下载失败。'))
    }
  }

  return { adminFiles, deleteAdminFile, downloadAdminFile, loadAdminFiles }
}

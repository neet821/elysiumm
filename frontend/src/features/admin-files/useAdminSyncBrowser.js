import { useCallback, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { getAdminFilesError, saveBlob } from './adminFilesUtils.js'


export function useAdminSyncBrowser(setError) {
  const [sync, setSync] = useState({ status: 'loading', path: '', items: [] })

  const loadSync = useCallback(async (nextPath = '') => {
    setSync({ status: 'loading', path: nextPath, items: [] })
    try {
      const statusResponse = await apiClient.get(API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS)
      const status = statusResponse.data?.status || 'offline'
      if (status !== 'online') {
        setSync({ status, path: nextPath, items: [] })
        setError(status === 'auth_failed' ? '文件同步鉴权失败。' : '电脑未连接，文件同步暂不可用。')
        return
      }
      const browse = await apiClient.get(API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE, { params: { path: nextPath } })
      setSync({ status: 'online', path: browse.data?.path || nextPath, items: Array.isArray(browse.data?.items) ? browse.data.items.filter((item) => !item.path.endsWith('/')) : [] })
    } catch (reason) {
      const status = reason.response?.status === 502 ? 'auth_failed' : 'offline'
      setSync({ status, path: nextPath, items: [] })
      setError(status === 'auth_failed' ? '文件同步鉴权失败。' : '电脑未连接，文件同步暂不可用。')
    }
  }, [setError])

  async function downloadSync(item) {
    try {
      const itemPath = [sync.path, item.path].filter(Boolean).join('/')
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_FILE_SYNC_DOWNLOAD, { params: { path: itemPath }, responseType: 'blob' })
      saveBlob(response.data, item.name)
    } catch (reason) {
      setError(getAdminFilesError(reason, '文件下载失败，请确认电脑仍在线。'))
    }
  }

  return { downloadSync, loadSync, sync }
}

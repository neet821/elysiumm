import { useCallback, useEffect, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { fingerprintLocalVideo, localFileMatches } from './localVideo.js'

function detailMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return error?.message || fallback
}

export function useVideoRoomLocalFiles({ numericRoomId, refreshVideoDetail, setBusy, setNotice, socketRef }) {
  const [localReady, setLocalReady] = useState({})
  const [localUrls, setLocalUrls] = useState({})
  const localFilesRef = useRef({})

  const announceLocalReady = useCallback((item) => {
    if (!item || item.source_type !== 'legacy_local' || !socketRef.current) return false
    const localFile = localFilesRef.current[item.id]
    const ready = Boolean(localFile && localFileMatches(item, localFile.file, localFile.fingerprint))
    socketRef.current.emit('video_local_ready', {
      ...(ready ? { fingerprint: localFile.fingerprint } : {}),
      item_id: item.id,
      ready,
      room_id: numericRoomId,
    })
    return ready
  }, [numericRoomId, socketRef])

  const addLocalVideo = useCallback(async (file) => {
    setBusy(true)
    setNotice('正在核对本地视频…')
    try {
      const fingerprint = await fingerprintLocalVideo(file)
      const response = await apiClient.post(API_ENDPOINTS.VIDEO_LOCAL_ITEM(numericRoomId), {
        file_size: file.size,
        filename: file.name,
        fingerprint,
        title: file.name,
      })
      const item = response.data.item
      const url = URL.createObjectURL(file)
      if (localFilesRef.current[item.id]?.url) URL.revokeObjectURL(localFilesRef.current[item.id].url)
      localFilesRef.current[item.id] = { file, fingerprint, url }
      setLocalUrls((previous) => ({ ...previous, [item.id]: url }))
      announceLocalReady(item)
      await refreshVideoDetail({ quiet: true })
      setNotice('本地视频已登记，文件内容没有上传')
      return item
    } catch (error) {
      setNotice(detailMessage(error, '本地视频登记失败'))
      return null
    } finally {
      setBusy(false)
    }
  }, [announceLocalReady, numericRoomId, refreshVideoDetail, setBusy, setNotice])

  const chooseLocalVideo = useCallback(async (item, file) => {
    setBusy(true)
    setNotice('正在核对本地视频…')
    try {
      const fingerprint = await fingerprintLocalVideo(file)
      if (!localFileMatches(item, file, fingerprint)) throw new Error('所选文件与房间要求的本地视频不一致')
      const url = URL.createObjectURL(file)
      if (localFilesRef.current[item.id]?.url) URL.revokeObjectURL(localFilesRef.current[item.id].url)
      localFilesRef.current[item.id] = { file, fingerprint, url }
      setLocalUrls((previous) => ({ ...previous, [item.id]: url }))
      announceLocalReady(item)
      setNotice('本地视频已准备，可以同步播放')
      return true
    } catch (error) {
      socketRef.current?.emit('video_local_ready', { item_id: item.id, ready: false, room_id: numericRoomId })
      setNotice(error.message || '本地视频核对失败')
      return false
    } finally {
      setBusy(false)
    }
  }, [announceLocalReady, numericRoomId, setBusy, setNotice, socketRef])

  useEffect(() => () => {
    Object.values(localFilesRef.current).forEach(({ url }) => URL.revokeObjectURL(url))
  }, [])

  return {
    addLocalVideo,
    announceLocalReady,
    chooseLocalVideo,
    localReady,
    localUrls,
    setLocalReady,
  }
}

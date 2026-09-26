import { useCallback, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'

function detailMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return error?.message || fallback
}

export function useVideoRoomActions({ numericRoomId, refreshVideoDetail, setNotice, setRoom, snapshotRef }) {
  const [busy, setBusy] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(null)

  const runMutation = useCallback(async (operation, fallback) => {
    setBusy(true)
    setNotice('')
    try {
      const result = await operation()
      await refreshVideoDetail({ quiet: true })
      return result
    } catch (error) {
      setNotice(detailMessage(error, fallback))
      return null
    } finally {
      setBusy(false)
    }
  }, [refreshVideoDetail, setNotice])

  const addUrl = useCallback((sourceUrl) => runMutation(
    () => apiClient.post(API_ENDPOINTS.VIDEO_URL_ITEM(numericRoomId), {
      source_url: sourceUrl,
      title: sourceUrl,
    }),
    '视频网址添加失败',
  ), [numericRoomId, runMutation])

  const uploadVideo = useCallback((file, appendToQueue = false) => {
    const form = new FormData()
    form.append('file', file)
    form.append('title', file.name)
    form.append('append_to_queue', appendToQueue ? 'true' : 'false')
    setUploadProgress({ active: true, loaded: 0, percent: 0, total: file.size })
    return runMutation(
      () => apiClient.post(API_ENDPOINTS.VIDEO_UPLOAD(numericRoomId), form, {
        timeout: 0,
        onUploadProgress: (event) => {
          const loaded = Math.max(0, Number(event?.loaded) || 0)
          const total = Math.max(loaded, Number(event?.total) || file.size || 0)
          const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0
          setUploadProgress({ active: true, loaded, percent, total })
        },
      }),
      '视频上传失败',
    ).finally(() => setUploadProgress(null))
  }, [numericRoomId, runMutation])

  const updateRoomSettings = useCallback((values) => runMutation(
    () => apiClient.put(API_ENDPOINTS.SYNC_ROOM_DETAIL(numericRoomId), values),
    '房间设置保存失败',
  ).then((response) => {
    if (response?.data) setRoom((previous) => ({ ...previous, ...response.data }))
    return response
  }), [numericRoomId, runMutation, setRoom])

  const selectItem = useCallback((itemId, autoplay = false) => runMutation(
    () => apiClient.post(API_ENDPOINTS.VIDEO_SELECT(numericRoomId, itemId), {
      autoplay,
      expected_version: snapshotRef.current?.snapshot?.version || 0,
    }),
    '视频切换失败',
  ), [numericRoomId, runMutation, snapshotRef])

  const deleteItem = useCallback((itemId) => runMutation(
    () => apiClient.delete(API_ENDPOINTS.VIDEO_ITEM(numericRoomId, itemId), {
      params: { expected_version: snapshotRef.current?.snapshot?.version || 0 },
    }),
    '视频删除失败',
  ), [numericRoomId, runMutation, snapshotRef])

  const advance = useCallback(() => runMutation(
    () => apiClient.post(API_ENDPOINTS.VIDEO_ADVANCE(numericRoomId), {
      autoplay: true,
      expected_version: snapshotRef.current?.snapshot?.version || 0,
    }),
    '无法切换到下一项',
  ), [numericRoomId, runMutation, snapshotRef])

  const reorder = useCallback((itemIds) => runMutation(
    () => apiClient.put(API_ENDPOINTS.VIDEO_PLAYLIST(numericRoomId), { item_ids: itemIds }),
    '片单排序失败',
  ), [numericRoomId, runMutation])

  const uploadSubtitle = useCallback((itemId, file, label, language) => {
    const form = new FormData()
    form.append('file', file)
    form.append('label', label)
    form.append('language', language)
    return runMutation(
      () => apiClient.post(API_ENDPOINTS.VIDEO_SUBTITLES(numericRoomId, itemId), form),
      '字幕上传失败',
    )
  }, [numericRoomId, runMutation])

  const selectSubtitle = useCallback((subtitleId) => runMutation(
    () => apiClient.put(API_ENDPOINTS.VIDEO_SUBTITLE_SELECT(numericRoomId, subtitleId)),
    '字幕切换失败',
  ), [numericRoomId, runMutation])

  const deleteSubtitle = useCallback((subtitleId) => runMutation(
    () => apiClient.delete(API_ENDPOINTS.VIDEO_SUBTITLE(numericRoomId, subtitleId)),
    '字幕删除失败',
  ), [numericRoomId, runMutation])

  const transferHost = useCallback((targetUserId) => runMutation(
    () => apiClient.post(`${API_ENDPOINTS.SYNC_ROOMS}/${numericRoomId}/transfer-host`, {
      new_host_user_id: targetUserId,
    }),
    '房主转让失败',
  ), [numericRoomId, runMutation])

  const kickMember = useCallback((targetUserId) => runMutation(
    () => apiClient.post(`${API_ENDPOINTS.SYNC_ROOMS}/${numericRoomId}/kick`, {
      target_user_id: targetUserId,
    }),
    '成员移出失败',
  ), [numericRoomId, runMutation])

  return {
    addUrl,
    advance,
    busy,
    deleteItem,
    deleteSubtitle,
    kickMember,
    reorder,
    selectItem,
    selectSubtitle,
    setBusy,
    transferHost,
    uploadProgress,
    uploadSubtitle,
    uploadVideo,
    updateRoomSettings,
  }
}

import { useCallback, useEffect, useRef } from 'react'

const PLAYBACK_RECOVERY_COOLDOWN_MS = 1_500

export function useVideoRoomBuffering({
  adapterRef,
  beginRemoteApply,
  currentItem,
  latestSnapshotRef,
  numericRoomId,
  playbackUnlockedRef,
  requestSnapshot,
  setNeedsUserGesture,
  setNotice,
  socketRef,
}) {
  const bufferReportedRef = useRef(false)
  const lastPlaybackRecoveryRef = useRef(0)

  useEffect(() => {
    bufferReportedRef.current = false
  }, [currentItem?.id])

  const reportBuffering = useCallback((buffering) => {
    if (!currentItem || !socketRef.current || bufferReportedRef.current === buffering) return
    bufferReportedRef.current = buffering
    socketRef.current.emit('video_buffer_status', {
      buffering,
      item_id: currentItem.id,
      room_id: numericRoomId,
    })
  }, [currentItem, numericRoomId, socketRef])

  const recoverPlayback = useCallback(() => {
    const snapshot = latestSnapshotRef.current?.snapshot
    if (!currentItem) return false
    reportBuffering(true)
    if (snapshot?.state !== 'playing') return true
    const now = Date.now()
    if (now - lastPlaybackRecoveryRef.current < PLAYBACK_RECOVERY_COOLDOWN_MS) return false
    lastPlaybackRecoveryRef.current = now
    requestSnapshot()
    if (!playbackUnlockedRef.current) return true
    const adapter = adapterRef.current
    const releaseRemoteApply = beginRemoteApply()
    let recovery
    try {
      recovery = adapter?.recover ? adapter.recover() : adapter?.play()
    } catch {
      releaseRemoteApply()
      setNeedsUserGesture(true)
      setNotice('视频暂时无法继续播放，请点击播放按钮重试')
      return false
    }
    Promise.resolve(recovery).then(() => {
      setNeedsUserGesture(false)
    }).catch(() => {
      setNeedsUserGesture(true)
      setNotice('视频暂时无法继续播放，请点击播放按钮重试')
    }).finally(releaseRemoteApply)
    return true
  }, [adapterRef, beginRemoteApply, currentItem, latestSnapshotRef, playbackUnlockedRef, reportBuffering, requestSnapshot, setNeedsUserGesture, setNotice])

  return { recoverPlayback, reportBuffering }
}

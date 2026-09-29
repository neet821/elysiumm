import { attachRoomOperation } from '../player/roomRealtimeSync.js'

export function createVideoRoomMediaEvents({
  canControl,
  currentItem,
  endedKeyRef,
  handleNativePlaybackControl,
  latestSnapshotRef,
  metadataKeyRef,
  numericRoomId,
  playbackUnlockedRef,
  recoverPlayback,
  refreshMediaSource,
  reportBuffering,
  saveMetadata,
  setNotice,
  socketRef,
}) {
  return {
    onCanPlay: () => reportBuffering(false),
    onEnded: () => {
      const version = latestSnapshotRef.current?.snapshot?.version
      if (!canControl || !currentItem || !Number.isInteger(version)) return
      const key = `${currentItem.id}:${version}`
      if (endedKeyRef.current === key) return
      endedKeyRef.current = key
      socketRef.current?.emit('video_ended', attachRoomOperation({
        expected_version: version,
        item_id: currentItem.id,
        room_id: numericRoomId,
      }))
    },
    onError: () => {
      setNotice('视频源加载失败，正在刷新播放凭据…')
      refreshMediaSource()
    },
    onLoadedMetadata: (event) => {
      if (!canControl || !currentItem) return
      const duration = Number(event.currentTarget.duration)
      const width = Number(event.currentTarget.videoWidth)
      const height = Number(event.currentTarget.videoHeight)
      if (!Number.isFinite(duration) || duration < 0 || width <= 0 || height <= 0) return

      const savedDuration = Number(currentItem.duration_seconds)
      const savedWidth = Number(currentItem.resolution?.width)
      const savedHeight = Number(currentItem.resolution?.height)
      if (
        Number.isFinite(savedDuration)
        && Math.abs(savedDuration - duration) <= 0.25
        && savedWidth === width
        && savedHeight === height
      ) return

      const key = `${currentItem.id}:${duration}:${width}:${height}`
      if (metadataKeyRef.current === key) return
      metadataKeyRef.current = key
      saveMetadata({
        duration,
        height,
        itemId: currentItem.id,
        roomId: numericRoomId,
        width,
      }).catch(() => setNotice('视频信息暂时无法保存'))
    },
    onPause: () => handleNativePlaybackControl('pause'),
    onPlay: () => handleNativePlaybackControl('play'),
    onPlaying: () => {
      playbackUnlockedRef.current = true
      reportBuffering(false)
    },
    onRateChange: () => handleNativePlaybackControl('rate'),
    onSeeking: () => handleNativePlaybackControl('seek'),
    onStalled: recoverPlayback,
    onWaiting: recoverPlayback,
  }
}

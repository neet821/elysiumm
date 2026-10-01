import { useCallback, useEffect, useRef, useState } from 'react'

import { applyRoomSnapshot } from '../player/roomPlayerIntegration.js'
import {
  cancelRoomSync,
  createRoomSyncState,
} from '../player/roomSyncEngine.js'

const REMOTE_MEDIA_EVENT_GRACE_MS = 300

export function useMusicRoomPlaybackSync({
  playerTrack,
  resolvedCurrent,
  roomId,
  setNotice,
  setRoom,
  setSyncStatus,
}) {
  const playerAdapterRef = useRef(null)
  const versionRef = useRef(-1)
  const latestSnapshotRef = useRef(null)
  const syncStateRef = useRef(createRoomSyncState())
  const remoteSyncRef = useRef(0)
  const remoteSyncUntilRef = useRef(0)
  const [playerReady, setPlayerReady] = useState(false)
  const [snapshotRecord, setSnapshotRecord] = useState(null)

  useEffect(() => {
    setSnapshotRecord(null)
    versionRef.current = -1
    latestSnapshotRef.current = null
    syncStateRef.current = createRoomSyncState()
    remoteSyncRef.current = 0
    remoteSyncUntilRef.current = 0
  }, [roomId])

  const handleAdapterReady = useCallback((adapter) => {
    if (!adapter && playerAdapterRef.current) {
      cancelRoomSync(playerAdapterRef.current, syncStateRef.current)
    }
    playerAdapterRef.current = adapter
    setPlayerReady(Boolean(adapter))
  }, [])

  const acceptSnapshot = useCallback((snapshot, { conflict = false } = {}) => {
    const version = Number(snapshot?.version)
    const serverNowMs = Number(snapshot?.server_now_ms)
    const latest = latestSnapshotRef.current?.snapshot
    const olderSameVersion = version === versionRef.current
      && Number.isFinite(serverNowMs)
      && Number.isFinite(Number(latest?.server_now_ms))
      && serverNowMs < Number(latest.server_now_ms)
    if (
      !Number.isInteger(version)
      || version < 0
      || version < versionRef.current
      || olderSameVersion
    ) return false
    const receivedAtMs = Date.now()
    const record = { receivedAtMs, snapshot }
    versionRef.current = version
    latestSnapshotRef.current = record
    setSnapshotRecord(record)
    setRoom((previous) => previous ? {
      ...previous,
      current_time: Number(snapshot.position) || 0,
      is_playing: snapshot.state === 'playing',
      playback_rate: Number(snapshot.playback_rate) || 1,
      playback_version: version,
    } : previous)
    setSyncStatus('synced')
    if (conflict) setNotice('操作与房间新状态冲突，已重新同步')
    return true
  }, [setNotice, setRoom, setSyncStatus])

  const syncPlayer = useCallback(async (record = snapshotRecord, options = {}) => {
    if (!playerAdapterRef.current || !resolvedCurrent || !playerTrack || !record?.snapshot) return
    try {
      const result = await applyRoomSnapshot(playerAdapterRef.current, record.snapshot, {
        beginRemoteApply: () => {
          remoteSyncRef.current += 1
          let released = false
          return () => {
            if (released) return
            released = true
            remoteSyncRef.current = Math.max(0, remoteSyncRef.current - 1)
            remoteSyncUntilRef.current = Math.max(
              remoteSyncUntilRef.current,
              Date.now() + REMOTE_MEDIA_EVENT_GRACE_MS,
            )
          }
        },
        playerTrack,
        receivedAtMs: record.receivedAtMs,
        steadyState: options.steadyState === true,
        syncState: syncStateRef.current,
      })
      if (!result.applied && result.reason === 'track-unavailable') {
        setNotice('当前歌曲没有可安全播放的地址')
      } else if (result.applied) {
        setSyncStatus('synced')
      }
    } catch (error) {
      setNotice(error?.message || '房间播放同步失败，请点击重新同步')
      setSyncStatus('error')
    }
  }, [playerTrack, resolvedCurrent, setNotice, setSyncStatus, snapshotRecord])

  useEffect(() => {
    if (playerReady && resolvedCurrent && snapshotRecord) syncPlayer(snapshotRecord)
  }, [playerReady, resolvedCurrent, snapshotRecord, syncPlayer])

  return {
    acceptSnapshot,
    handleAdapterReady,
    latestSnapshotRef,
    playerAdapterRef,
    remoteSyncRef,
    remoteSyncUntilRef,
    syncStateRef,
    versionRef,
  }
}

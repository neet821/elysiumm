import { useEffect } from 'react'
import { io } from 'socket.io-client'

import { WS_BASE_URL } from '../../config'
import { cancelRoomSync } from '../player/roomSyncEngine.js'
import { startRoomClockProbes } from '../player/roomRealtimeSync.js'

export function useMusicRoomRealtime({
  acceptSnapshot,
  latestSnapshotRef,
  loadHistory,
  playerAdapterRef,
  remoteSyncRef,
  remoteSyncUntilRef,
  roomId,
  setMembers,
  setMessages,
  setNotice,
  setQueue,
  setRoom,
  setSyncStatus,
  socketRef,
  syncStateRef,
  userId,
  versionRef,
}) {
  useEffect(() => {
    if (!roomId || !userId) return undefined
    let active = true
    const syncState = syncStateRef.current
    const socket = io(WS_BASE_URL, {
      auth: { token: localStorage.getItem('token') },
      path: '/ws/socket.io',
      transports: ['polling', 'websocket'],
    })
    socketRef.current = socket
    const stopClockProbes = startRoomClockProbes(socket, Number(roomId), syncState)
    socket.on('connect', () => {
      setSyncStatus(latestSnapshotRef.current ? 'syncing' : 'connecting')
      socket.emit('join_room', { room_id: Number(roomId) })
    })
    socket.on('disconnect', () => {
      if (active) setSyncStatus('reconnecting')
    })
    socket.on('connect_error', () => {
      if (active) setSyncStatus('error')
    })
    const presenceTimer = window.setInterval(() => {
      if (socket.connected) {
        socket.emit('presence_heartbeat', { room_id: Number(roomId) })
      }
    }, 10_000)
    socket.on('join_success', (data) => {
      if (data.room) setRoom((previous) => ({ ...previous, ...data.room }))
      setMembers(data.members || [])
      if (data.snapshot) acceptSnapshot(data.snapshot)
      else socket.emit('request_snapshot', { room_id: Number(roomId) })
    })
    socket.on('member_joined', (member) => {
      setMembers((items) => (
        items.some((item) => item.user_id === member.user_id)
          ? items.map((item) => item.user_id === member.user_id ? { ...item, is_online: true } : item)
          : [...items, { ...member, is_online: true }]
      ))
      loadHistory({ quiet: true })
    })
    socket.on('member_left', (data) => {
      setMembers((items) => items.map((item) => (
        item.user_id === data.user_id ? { ...item, is_online: false } : item
      )))
      loadHistory({ quiet: true })
    })
    socket.on('new_message', (data) => {
      setMessages((items) => (
        items.some((item) => item.id === data.id) ? items : [...items, data]
      ))
      loadHistory({ quiet: true })
    })
    socket.on('music_queue_updated', (data) => setQueue(data.queue || []))
    socket.on('music_settings_updated', (data) => {
      if (Number(data?.room_id) !== Number(roomId)) return
      setRoom((previous) => ({ ...previous, music_skip_vote_percent: data.music_skip_vote_percent }))
    })
    socket.on('music_track_changed', (data) => {
      const eventVersion = Number(data?.playback_version)
      if (Number.isInteger(eventVersion) && eventVersion < versionRef.current) return
      if (data.track) {
        setQueue((items) => [
          { ...data.track, status: 'playing' },
          ...items.filter((item) => item.id !== data.track.id && item.status !== 'playing'),
        ])
      }
      if (!latestSnapshotRef.current) {
        socket.emit('request_snapshot', { room_id: Number(roomId) })
      }
    })
    socket.on('playback_sync', () => {
      if (!latestSnapshotRef.current) {
        socket.emit('request_snapshot', { room_id: Number(roomId) })
      }
    })
    socket.on('time_sync', () => {
      if (!latestSnapshotRef.current) {
        socket.emit('request_snapshot', { room_id: Number(roomId) })
      }
    })
    socket.on('room_snapshot', (snapshot) => {
      if (acceptSnapshot(snapshot)) loadHistory({ quiet: true })
    })
    socket.on('playback_conflict', (data) => {
      if (data?.snapshot) acceptSnapshot(data.snapshot, { conflict: true })
      else setNotice('房间状态发生冲突，正在重新同步')
    })
    socket.on('time_heartbeat', () => {
      // Presence/clock heartbeats do not recalibrate a music room. Playback
      // is corrected only by an authoritative snapshot (join, track change,
      // reconnect, page restore, or an explicit resync).
    })
    socket.on('error', (data) => {
      if (data?.message) setNotice(data.message)
    })

    return () => {
      active = false
      // The native player can detach or replace its adapter before this cleanup runs.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      cancelRoomSync(playerAdapterRef.current, syncState)
      remoteSyncRef.current = 0
      remoteSyncUntilRef.current = 0
      window.clearInterval(presenceTimer)
      stopClockProbes()
      socket.disconnect()
      socketRef.current = null
    }
  }, [
    acceptSnapshot,
    latestSnapshotRef,
    loadHistory,
    playerAdapterRef,
    remoteSyncRef,
    remoteSyncUntilRef,
    roomId,
    setMembers,
    setMessages,
    setNotice,
    setQueue,
    setRoom,
    setSyncStatus,
    socketRef,
    syncStateRef,
    userId,
    versionRef,
  ])
}

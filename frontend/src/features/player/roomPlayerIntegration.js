import { normalizePlayerTrack } from './playerTrack.js'
import {
  applyAuthoritativeSnapshot,
  createRoomSyncState,
} from './roomSyncEngine.js'

const adapterSyncStates = new WeakMap()

export function roomQueueTrackToPlayerTrack(value) {
  if (!value || typeof value !== 'object') return null
  try {
    return normalizePlayerTrack({
      album: value.album,
      artist: value.artist,
      artworkUrl: value.artwork_url,
      audioUrl: value.stream_url,
      duration: value.duration_seconds,
      id: `room:${value.id ?? `${value.provider}:${value.provider_track_id}`}`,
      lyrics: value.lyrics || [],
      title: value.title,
    })
  } catch {
    return null
  }
}

export async function applyRoomSnapshot(adapter, snapshot, options = {}) {
  if (!adapter || typeof adapter.snapshot !== 'function') {
    return { applied: false, reason: 'adapter-unavailable', trackChanged: false }
  }
  const playerTrack = options.playerTrack || roomQueueTrackToPlayerTrack(snapshot?.track)
  if (!playerTrack) return { applied: false, reason: 'track-unavailable', trackChanged: false }

  const clientNowMs = Number(options.clientNowMs ?? Date.now())
  const syncState = options.syncState
    || adapterSyncStates.get(adapter)
    || createRoomSyncState()
  adapterSyncStates.set(adapter, syncState)
  const version = Number(snapshot?.version ?? snapshot?.playback_version)
  const authoritativeSnapshot = snapshot?.state ? snapshot : {
    media_id: snapshot?.track?.id ?? null,
    playback_rate: Number(snapshot?.playbackRate ?? snapshot?.rate ?? 1),
    position: Math.max(0, Number(snapshot?.time) || 0),
    room_id: Number(snapshot?.room_id ?? 1),
    server_now_ms: clientNowMs,
    started_at_server_ms: clientNowMs,
    state: snapshot?.isPlaying ? 'playing' : 'paused',
    track_id: snapshot?.track?.canonical_track_id ?? null,
    version: Number.isInteger(version) && version >= 0
      ? version
      : Math.max(0, syncState.lastVersion),
  }
  return applyAuthoritativeSnapshot(adapter, authoritativeSnapshot, {
    ...options,
    clientNowMs,
    playerTrack,
    receivedAtMs: Number(options.receivedAtMs ?? clientNowMs),
    mediaKind: 'music',
    syncState,
  })
}

export function playerEventToRoomIntent(eventName, snapshot, context = {}) {
  if (context.suppress || !context.canControl || !context.roomId) return null
  if (eventName === 'seek' && context.mediaKind === 'music') return null
  const time = Math.max(0, Number(snapshot?.currentTime) || 0)

  if (eventName === 'ended') {
    return {
      event: 'music_ended',
      payload: {
        room_id: Number(context.roomId),
        item_id: Number(context.currentItemId || snapshot?.track?.id),
        expected_version: Number(context.version) || 0,
      },
    }
  }
  if (!['play', 'pause', 'seek'].includes(eventName)) return null
  return {
    event: 'playback_control',
    payload: {
      action: eventName,
      playback_version: Number(context.version) || 0,
      room_id: Number(context.roomId),
      time,
    },
  }
}

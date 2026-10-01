export const DRIFT_IGNORE_SECONDS = 0.75
export const DRIFT_SEEK_SECONDS = 4
export const MIN_PLAYBACK_RATE = 0.5
export const MAX_PLAYBACK_RATE = 2

export function finiteNumber(value, fallback = null) {
  if (value === null || value === undefined || value === '') return fallback
  const normalized = Number(value)
  return Number.isFinite(normalized) ? normalized : fallback
}

export function normalizeRoomSnapshot(value) {
  if (!value || typeof value !== 'object') return null
  const state = value.state
  const version = finiteNumber(value.version)
  const position = finiteNumber(value.position)
  const startedAt = finiteNumber(value.started_at_server_ms)
  const serverNow = finiteNumber(value.server_now_ms)
  const playbackRate = finiteNumber(value.playback_rate)
  const roomId = finiteNumber(value.room_id)
  const validOptionalId = (id) => id === null || (
    Number.isInteger(finiteNumber(id)) && finiteNumber(id) > 0
  )
  if (
    !['playing', 'paused'].includes(state)
    || !Number.isInteger(roomId)
    || roomId <= 0
    || !validOptionalId(value.track_id)
    || !validOptionalId(value.media_id)
    || !Number.isInteger(version)
    || version < 0
    || position === null
    || position < 0
    || !Number.isInteger(startedAt)
    || startedAt < 0
    || !Number.isInteger(serverNow)
    || serverNow < 0
    || playbackRate === null
    || playbackRate < MIN_PLAYBACK_RATE
    || playbackRate > MAX_PLAYBACK_RATE
  ) return null
  return {
    ...value,
    playback_rate: playbackRate,
    position,
    server_now_ms: serverNow,
    started_at_server_ms: startedAt,
    state,
    version,
  }
}

export function projectSnapshotPosition(snapshot, clientNowMs, serverOffsetMs = 0) {
  const normalized = normalizeRoomSnapshot(snapshot)
  const clientNow = finiteNumber(clientNowMs)
  const offset = finiteNumber(serverOffsetMs, 0)
  if (!normalized || clientNow === null) return 0
  if (normalized.state !== 'playing') return normalized.position
  const estimatedServerNow = clientNow + offset
  const elapsedMs = Math.max(0, estimatedServerNow - normalized.started_at_server_ms)
  return Math.max(0, normalized.position + elapsedMs / 1_000 * normalized.playback_rate)
}

export function classifyDrift(currentPosition, targetPosition, thresholds = {}) {
  const current = Math.max(0, finiteNumber(currentPosition, 0))
  const target = Math.max(0, finiteNumber(targetPosition, 0))
  const driftSeconds = target - current
  const absoluteDriftSeconds = Math.abs(driftSeconds)
  const ignoreSeconds = Number.isFinite(Number(thresholds.ignoreSeconds))
    ? Number(thresholds.ignoreSeconds)
    : DRIFT_IGNORE_SECONDS
  const seekSeconds = Number.isFinite(Number(thresholds.seekSeconds))
    ? Number(thresholds.seekSeconds)
    : DRIFT_SEEK_SECONDS
  return {
    absoluteDriftSeconds,
    driftSeconds,
    kind: absoluteDriftSeconds < ignoreSeconds
      ? 'none'
      : absoluteDriftSeconds <= seekSeconds
        ? 'rate'
        : 'seek',
  }
}

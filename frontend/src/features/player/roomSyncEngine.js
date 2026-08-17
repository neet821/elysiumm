export const DRIFT_IGNORE_SECONDS = 0.75
export const DRIFT_SEEK_SECONDS = 4
export const DRIFT_HARD_SEEK_CONFIRMATIONS = 2
export const TEMPORARY_RATE_MS = 1_500

const MIN_PLAYBACK_RATE = 0.5
const MAX_PLAYBACK_RATE = 2
const RATE_CORRECTION_STEP = 0.08
const VIDEO_DRIFT_IGNORE_SECONDS = 0.5
const VIDEO_DRIFT_SEEK_SECONDS = 2

function finiteNumber(value, fallback = null) {
  if (value === null || value === undefined || value === '') return fallback
  const normalized = Number(value)
  return Number.isFinite(normalized) ? normalized : fallback
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value))
}

function normalizeSnapshot(value) {
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

export function createRoomSyncState() {
  return {
    clockOffsetMs: 0,
    lastVersion: -1,
    largeDriftSamples: 0,
    rateTimer: null,
    rateToken: null,
  }
}

export function estimateServerOffset(snapshot, receivedAtMs) {
  const serverNow = finiteNumber(snapshot?.server_now_ms)
  const receivedAt = finiteNumber(receivedAtMs)
  if (serverNow === null || receivedAt === null) return 0
  return serverNow - receivedAt
}

export function projectSnapshotPosition(snapshot, clientNowMs, serverOffsetMs = 0) {
  const normalized = normalizeSnapshot(snapshot)
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

function clearRateTimer(adapter, syncState, clearTimer, restoreRate) {
  if (syncState.rateTimer === null) return
  clearTimer(syncState.rateTimer)
  syncState.rateTimer = null
  syncState.rateToken = null
  adapter.setPlaybackRate(restoreRate)
}

export function cancelRoomSync(adapter, syncState, options = {}) {
  if (!syncState || syncState.rateTimer === null) return false
  const clearTimer = options.clearTimer || clearTimeout
  clearTimer(syncState.rateTimer)
  syncState.rateTimer = null
  syncState.rateToken = null
  if (adapter && typeof adapter.setPlaybackRate === 'function') {
    try {
      adapter.setPlaybackRate(options.restoreRate ?? 1)
    } catch {
      // Adapter teardown may already have completed.
    }
  }
  return true
}

export async function applyAuthoritativeSnapshot(adapter, snapshot, options = {}) {
  if (!adapter || typeof adapter.snapshot !== 'function') {
    return { applied: false, reason: 'adapter-unavailable', trackChanged: false }
  }
  const normalized = normalizeSnapshot(snapshot)
  if (!normalized) {
    return { applied: false, reason: 'invalid-snapshot', trackChanged: false }
  }

  const syncState = options.syncState || createRoomSyncState()
  if (normalized.version < syncState.lastVersion) {
    return { applied: false, reason: 'stale-version', trackChanged: false }
  }

  const receivedAtMs = finiteNumber(options.receivedAtMs, Date.now())
  const clientNowMs = finiteNumber(options.clientNowMs, Date.now())
  const clearTimer = options.clearTimer || clearTimeout
  const setTimer = options.setTimer || setTimeout
  const beginRemoteApply = options.beginRemoteApply || (() => () => {})
  const playerTrack = options.playerTrack || null
  const steadyState = options.steadyState === true
  const mediaKind = options.mediaKind || normalized.media_kind || 'music'
  const driftThresholds = mediaKind === 'music'
    ? undefined
    : { ignoreSeconds: VIDEO_DRIFT_IGNORE_SECONDS, seekSeconds: VIDEO_DRIFT_SEEK_SECONDS }
  const hardSeekConfirmations = mediaKind === 'music' ? DRIFT_HARD_SEEK_CONFIRMATIONS : 1
  const authoritativeRate = normalized.playback_rate
  const clockOffsetMs = estimateServerOffset(normalized, receivedAtMs)
  const targetPosition = projectSnapshotPosition(
    normalized,
    clientNowMs,
    clockOffsetMs,
  )

  clearRateTimer(adapter, syncState, clearTimer, authoritativeRate)
  const release = beginRemoteApply()
  let scheduledTimer = null
  try {
    let playerState = adapter.snapshot()
    const trackChanged = Boolean(
      playerTrack && playerState.track?.id !== playerTrack.id
    )
    if (!playerTrack && !playerState.track) {
      return { applied: false, reason: 'track-unavailable', trackChanged: false }
    }
    const drift = classifyDrift(playerState.currentTime, targetPosition, driftThresholds)
    let correction = drift.kind
    let forceSeek = trackChanged || (!steadyState && drift.kind === 'seek')
    if (normalized.state === 'paused' && drift.kind !== 'none') forceSeek = true

    if (steadyState && drift.kind === 'seek' && !trackChanged) {
      syncState.largeDriftSamples += 1
      if (syncState.largeDriftSamples < hardSeekConfirmations) {
        syncState.clockOffsetMs = clockOffsetMs
        syncState.lastVersion = normalized.version
        return {
          applied: true,
          clockOffsetMs,
          correction: 'deferred',
          driftSeconds: drift.driftSeconds,
          targetPosition,
          trackChanged,
          version: normalized.version,
        }
      }
      syncState.largeDriftSamples = 0
      forceSeek = true
    } else if (drift.kind !== 'seek') {
      syncState.largeDriftSamples = 0
    }

    const temporaryRate = drift.kind === 'rate' && normalized.state === 'playing' && !forceSeek
      ? clamp(
        authoritativeRate + Math.sign(drift.driftSeconds) * RATE_CORRECTION_STEP,
        MIN_PLAYBACK_RATE,
        MAX_PLAYBACK_RATE,
      )
      : authoritativeRate

    if (typeof adapter.applyState === 'function') {
      const needsApply = trackChanged
        || forceSeek
        || drift.kind === 'rate'
        || (normalized.state === 'playing' && !playerState.isPlaying)
        || (normalized.state === 'paused' && playerState.isPlaying)
        || finiteNumber(playerState.playbackRate, 1) !== temporaryRate
      if (needsApply) {
        await adapter.applyState({
          forceSeek,
          isPlaying: normalized.state === 'playing',
          playbackRate: temporaryRate,
          time: targetPosition,
          track: playerTrack || playerState.track,
        })
        playerState = adapter.snapshot()
      }
      if (temporaryRate !== authoritativeRate) {
        const token = Symbol('room-rate-correction')
        syncState.rateToken = token
        scheduledTimer = setTimer(() => {
          if (syncState.rateToken !== token) return
          syncState.rateTimer = null
          syncState.rateToken = null
          const latest = adapter.snapshot()
          const restore = typeof adapter.applyState === 'function'
            ? adapter.applyState({
              forceSeek: false,
              isPlaying: latest.isPlaying,
              playbackRate: authoritativeRate,
              time: latest.currentTime,
              track: latest.track,
            })
            : adapter.setPlaybackRate(authoritativeRate)
          Promise.resolve(restore).catch(() => {})
        }, TEMPORARY_RATE_MS)
        syncState.rateTimer = scheduledTimer
      }
    } else {
      if (trackChanged) {
        adapter.load(playerTrack)
        playerState = adapter.snapshot()
      }
      if (forceSeek) {
        adapter.setPlaybackRate(authoritativeRate)
        adapter.seek(targetPosition)
        correction = 'seek'
        playerState = adapter.snapshot()
      } else if (drift.kind === 'rate') {
        adapter.setPlaybackRate(temporaryRate)
        const token = Symbol('room-rate-correction')
        syncState.rateToken = token
        scheduledTimer = setTimer(() => {
          if (syncState.rateToken !== token) return
          syncState.rateTimer = null
          syncState.rateToken = null
          adapter.setPlaybackRate(authoritativeRate)
        }, TEMPORARY_RATE_MS)
        syncState.rateTimer = scheduledTimer
        playerState = adapter.snapshot()
      } else if (finiteNumber(playerState.playbackRate, 1) !== authoritativeRate) {
        adapter.setPlaybackRate(authoritativeRate)
        playerState = adapter.snapshot()
      }

      if (normalized.state === 'playing' && !playerState.isPlaying) {
        await adapter.play()
      } else if (normalized.state === 'paused' && playerState.isPlaying) {
        adapter.pause()
      }
    }

    syncState.clockOffsetMs = clockOffsetMs
    syncState.lastVersion = normalized.version
    return {
      applied: true,
      clockOffsetMs,
      correction,
      driftSeconds: drift.driftSeconds,
      targetPosition,
      trackChanged,
      version: normalized.version,
    }
  } catch (error) {
    if (scheduledTimer !== null && syncState.rateTimer === scheduledTimer) {
      clearTimer(scheduledTimer)
      syncState.rateTimer = null
      syncState.rateToken = null
      adapter.setPlaybackRate(authoritativeRate)
    }
    throw error
  } finally {
    if (typeof release === 'function') release()
  }
}

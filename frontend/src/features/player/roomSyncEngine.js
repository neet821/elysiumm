import { estimateServerOffset } from './roomSyncClock.js'
import {
  classifyDrift,
  finiteNumber,
  MAX_PLAYBACK_RATE,
  MIN_PLAYBACK_RATE,
  normalizeRoomSnapshot,
  projectSnapshotPosition,
} from './roomSyncSnapshot.js'

export const DRIFT_HARD_SEEK_CONFIRMATIONS = 2
export const TEMPORARY_RATE_MS = 1_500

export {
  DRIFT_IGNORE_SECONDS,
  DRIFT_SEEK_SECONDS,
  classifyDrift,
  projectSnapshotPosition,
} from './roomSyncSnapshot.js'
export { estimateServerOffset, recordClockProbe } from './roomSyncClock.js'

const RATE_CORRECTION_STEP = 0.08
const VIDEO_DRIFT_IGNORE_SECONDS = 0.5
const VIDEO_DRIFT_SEEK_SECONDS = 2

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value))
}

export function createRoomSyncState() {
  return {
    clockOffsetMs: 0,
    clockSamples: [],
    lastVersion: -1,
    largeDriftSamples: 0,
    roundTripTimeMs: null,
    rateTimer: null,
    rateToken: null,
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
  const normalized = normalizeRoomSnapshot(snapshot)
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
  const allowPlay = options.allowPlay !== false
  const playerTrack = options.playerTrack || null
  const steadyState = options.steadyState === true
  const mediaKind = options.mediaKind || normalized.media_kind || 'music'
  const driftThresholds = mediaKind === 'music'
    ? undefined
    : { ignoreSeconds: VIDEO_DRIFT_IGNORE_SECONDS, seekSeconds: VIDEO_DRIFT_SEEK_SECONDS }
  const hardSeekConfirmations = mediaKind === 'music' ? DRIFT_HARD_SEEK_CONFIRMATIONS : 1
  const authoritativeRate = normalized.playback_rate
  const clockOffsetMs = Array.isArray(syncState.clockSamples) && syncState.clockSamples.length
    ? syncState.clockOffsetMs
    : estimateServerOffset(normalized, receivedAtMs)
  const targetPosition = projectSnapshotPosition(
    normalized,
    clientNowMs,
    clockOffsetMs,
  )

  clearRateTimer(adapter, syncState, clearTimer, authoritativeRate)
  const release = beginRemoteApply()
  let scheduledTimer = null
  let playbackBlocked = false
  try {
    let playerState = adapter.snapshot()
    const trackChanged = Boolean(
      playerTrack && playerState.track?.id !== playerTrack.id
    )
    if (!playerTrack && !playerState.track) {
      return { applied: false, reason: 'track-unavailable', trackChanged: false }
    }
    const drift = classifyDrift(playerState.currentTime, targetPosition, driftThresholds)
    const isMusic = mediaKind === 'music'
    let correction = isMusic && steadyState ? 'none' : drift.kind
    let forceSeek = trackChanged || (!steadyState && drift.kind === 'seek')
    if (normalized.state === 'paused' && drift.kind !== 'none') forceSeek = true
    if (isMusic && steadyState) forceSeek = trackChanged
    if (!allowPlay && normalized.state === 'playing' && !playerState.isPlaying) {
      playbackBlocked = true
    }

    if (!isMusic && steadyState && drift.kind === 'seek' && !trackChanged) {
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

    const temporaryRate = !isMusic && drift.kind === 'rate' && normalized.state === 'playing' && !forceSeek
      ? clamp(
        authoritativeRate + Math.sign(drift.driftSeconds) * RATE_CORRECTION_STEP,
        MIN_PLAYBACK_RATE,
        MAX_PLAYBACK_RATE,
      )
      : authoritativeRate

    if (typeof adapter.applyState === 'function') {
      const needsApply = trackChanged
        || forceSeek
        || (!isMusic && drift.kind === 'rate')
        || (normalized.state === 'playing' && !playerState.isPlaying)
        || (normalized.state === 'paused' && playerState.isPlaying)
        || finiteNumber(playerState.playbackRate, 1) !== temporaryRate
      if (needsApply) {
        await adapter.applyState({
          forceSeek,
          isPlaying: allowPlay
            ? normalized.state === 'playing'
            : normalized.state === 'playing' && playerState.isPlaying,
          playbackRate: temporaryRate,
          time: targetPosition,
          track: playerTrack || playerState.track,
        })
        playerState = adapter.snapshot()
      }
      if (!isMusic && temporaryRate !== authoritativeRate) {
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
      } else if (!isMusic && drift.kind === 'rate') {
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
        if (allowPlay) await adapter.play()
        else playbackBlocked = true
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
      playbackBlocked,
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

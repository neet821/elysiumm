import {
  applyAuthoritativeSnapshot,
  cancelRoomSync,
  createRoomSyncState,
} from '../player/roomSyncEngine.js'
import Hls from 'hls.js'


function safeMediaUrl(value, { allowBlob = false } = {}) {
  if (typeof value !== 'string' || !value.trim()) return null
  const candidate = value.trim()
  if (candidate.startsWith('/')) return candidate
  try {
    const parsed = new URL(candidate, window.location.origin)
    const allowedProtocols = allowBlob ? ['http:', 'https:', 'blob:'] : ['http:', 'https:']
    if (!allowedProtocols.includes(parsed.protocol) || parsed.username || parsed.password) {
      return null
    }
    return candidate
  } catch {
    return null
  }
}

export function videoItemToAdapterTrack(item, selectedSubtitleId = null) {
  if (!item || !Number.isInteger(Number(item.id)) || Number(item.id) <= 0) return null
  const playbackUrl = safeMediaUrl(item.playback_url, { allowBlob: true })
  if (!playbackUrl) return null
  const subtitles = (Array.isArray(item.subtitles) ? item.subtitles : [])
    .map((subtitle) => ({
      default: Number(subtitle.id) === Number(selectedSubtitleId),
      id: Number(subtitle.id),
      label: String(subtitle.label || subtitle.language || '字幕').slice(0, 80),
      language: String(subtitle.language || 'und').slice(0, 35),
      src: safeMediaUrl(subtitle.src),
    }))
    .filter((subtitle) => Number.isInteger(subtitle.id) && subtitle.id > 0 && subtitle.src)
  const subtitleSignature = subtitles
    .map((subtitle) => `${subtitle.id}:${subtitle.default ? 1 : 0}`)
    .join(',') || 'none'
  return {
    id: `video:${Number(item.id)}:${item.playback_kind === 'hls' ? 'hls' : 'file'}:subtitles:${subtitleSignature}`,
    mediaId: Number(item.id),
    playbackKind: item.playback_kind === 'hls' ? 'hls' : 'file',
    playbackUrl,
    subtitles,
    title: String(item.title || item.original_filename || '未命名视频'),
  }
}

export function createVideoPlayerAdapter(element, options = {}) {
  if (!(element instanceof HTMLMediaElement)) {
    throw new Error('需要有效的视频元素')
  }
  let currentTrack = null
  let hls = null
  const createHls = options.createHls || (() => new Hls({ enableWorker: true }))
  const isHlsSupported = options.isHlsSupported || (() => Hls.isSupported())

  const clearHls = () => {
    if (!hls) return
    hls.destroy()
    hls = null
  }

  const adapter = {
    load(track) {
      if (!track || !safeMediaUrl(track.playbackUrl, { allowBlob: true })) {
        throw new Error('视频没有可安全播放的地址')
      }
      element.pause()
      clearHls()
      element.querySelectorAll('track[data-video-room-track="true"]').forEach((node) => node.remove())
      element.removeAttribute('src')
      if (track.playbackKind === 'hls' && !element.canPlayType('application/vnd.apple.mpegurl')) {
        if (!isHlsSupported()) {
          throw new Error('当前浏览器无法播放 HLS 视频')
        }
        const nextHls = createHls()
        hls = nextHls
        nextHls.on?.(Hls.Events.ERROR, (_event, data) => {
          if (hls !== nextHls || !data?.fatal) return
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) nextHls.startLoad?.()
          else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) nextHls.recoverMediaError?.()
        })
        nextHls.loadSource(track.playbackUrl)
        nextHls.attachMedia(element)
      } else {
        element.setAttribute('src', track.playbackUrl)
      }
      for (const subtitle of track.subtitles || []) {
        const node = document.createElement('track')
        node.dataset.videoRoomTrack = 'true'
        node.kind = 'subtitles'
        node.label = subtitle.label
        node.srclang = subtitle.language
        node.src = subtitle.src
        node.default = Boolean(subtitle.default)
        element.appendChild(node)
      }
      currentTrack = track
      element.load()
      return adapter.snapshot()
    },
    async play() {
      return element.play()
    },
    recover() {
      const currentTime = Math.max(0, Number(element.currentTime) || 0)
      try {
        const duration = Number(element.duration)
        element.currentTime = Number.isFinite(duration) ? Math.min(currentTime, duration) : currentTime
      } catch {
        // The media element can reject a seek while it is replacing a source.
      }
      return element.play()
    },
    pause() {
      element.pause()
    },
    seek(seconds) {
      const value = Math.max(0, Number(seconds) || 0)
      const duration = Number(element.duration)
      element.currentTime = Number.isFinite(duration) ? Math.min(value, duration) : value
    },
    setPlaybackRate(rate) {
      const value = Number(rate)
      if (!Number.isFinite(value) || value < 0.5 || value > 2) {
        throw new Error('播放速度超出范围')
      }
      element.playbackRate = value
    },
    setVolume(volume) {
      const value = Number(volume)
      if (!Number.isFinite(value)) return
      element.volume = Math.min(1, Math.max(0, value))
    },
    snapshot() {
      return {
        currentTime: Math.max(0, Number(element.currentTime) || 0),
        duration: Number.isFinite(Number(element.duration)) ? Number(element.duration) : 0,
        isPlaying: !element.paused && !element.ended,
        playbackRate: Number(element.playbackRate) || 1,
        track: currentTrack ? { id: currentTrack.id, title: currentTrack.title } : null,
      }
    },
    destroy(options = {}) {
      cancelRoomSync(adapter, options.syncState, {
        clearTimer: options.clearTimer,
        restoreRate: 1,
      })
      element.pause()
      clearHls()
      element.querySelectorAll('track[data-video-room-track="true"]').forEach((node) => node.remove())
      element.removeAttribute('src')
      currentTrack = null
      element.load()
    },
  }
  return adapter
}

const adapterSyncStates = new WeakMap()

export function applyVideoSnapshot(adapter, snapshot, adapterTrack, options = {}) {
  if (!adapterTrack) {
    return Promise.resolve({ applied: false, reason: 'track-unavailable', trackChanged: false })
  }
  const syncState = options.syncState
    || adapterSyncStates.get(adapter)
    || createRoomSyncState()
  adapterSyncStates.set(adapter, syncState)
  return applyAuthoritativeSnapshot(adapter, {
    ...snapshot,
    media_kind: 'video',
    track_id: snapshot?.track_id ?? null,
  }, {
    ...options,
    mediaKind: 'video',
    playerTrack: adapterTrack,
    syncState,
  })
}

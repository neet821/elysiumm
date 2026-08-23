const LRC_TIMESTAMP = /\[(\d{1,3}):([0-5]?\d(?:\.\d{1,3})?)\]/g

function requiredText(value, field) {
  const normalized = String(value || '').trim()
  if (!normalized) throw new TypeError(`Player track ${field} is required`)
  return normalized
}

function optionalText(value, fallback = '') {
  if (value === null || value === undefined) return fallback
  return String(value).trim()
}

function safeResourceUrl(value, field, dataPrefix) {
  const normalized = requiredText(value, field)
  if (normalized.startsWith('/') && !normalized.startsWith('//')) return normalized
  if (/^https?:\/\/[^\s]+$/i.test(normalized)) return normalized
  if (/^blob:https?:\/\/[^\s]+$/i.test(normalized)) return normalized
  if (normalized.toLowerCase().startsWith(dataPrefix)) return normalized
  throw new TypeError(`Player track ${field} must use a safe local, data, blob, http, or https URL`)
}

function normalizedDuration(value) {
  if (value === null || value === undefined || value === '') return 0
  const duration = Number(value)
  if (!Number.isFinite(duration) || duration < 0) {
    throw new TypeError('Player track duration must be a finite non-negative number')
  }
  return duration
}

function lyricMap(lines) {
  const normalized = new Map()
  for (const line of lines) {
    const time = Number(line?.time)
    const text = optionalText(line?.text)
    if (!Number.isFinite(time) || time < 0 || !text) continue
    normalized.set(time, { text, time })
  }
  return [...normalized.values()].sort((left, right) => left.time - right.time)
}

export function parseLrc(value) {
  if (typeof value !== 'string') return []
  const lines = []
  for (const rawLine of value.split(/\r?\n/)) {
    const matches = [...rawLine.matchAll(LRC_TIMESTAMP)]
    if (matches.length === 0) continue
    const text = rawLine.replace(LRC_TIMESTAMP, '').trim()
    if (!text) continue
    for (const match of matches) {
      const minutes = Number(match[1])
      const seconds = Number(match[2])
      lines.push({ text, time: (minutes * 60) + seconds })
    }
  }
  return lyricMap(lines)
}

export function normalizeLyrics(value) {
  if (typeof value === 'string') return parseLrc(value)
  if (!Array.isArray(value)) return []
  return lyricMap(value)
}

export function activeLyricIndex(lyrics, currentTime) {
  if (!Array.isArray(lyrics) || lyrics.length === 0) return -1
  const time = Number(currentTime)
  if (!Number.isFinite(time) || time < lyrics[0].time) return -1

  let low = 0
  let high = lyrics.length - 1
  let active = -1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    if (lyrics[middle].time <= time) {
      active = middle
      low = middle + 1
    } else {
      high = middle - 1
    }
  }
  return active
}

export function normalizePlayerTrack(value) {
  if (!value || typeof value !== 'object') {
    throw new TypeError('Player track must be an object')
  }
  const artwork = optionalText(value.artworkUrl, '')
  const metadata = {}
  if (value.provider) metadata.provider = String(value.provider)
  if (value.providerTrackId || value.provider_track_id) {
    metadata.providerTrackId = String(value.providerTrackId || value.provider_track_id)
  }
  return Object.freeze({
    album: optionalText(value.album),
    artist: optionalText(value.artist, '未知音乐人') || '未知音乐人',
    artworkUrl: artwork ? safeResourceUrl(artwork, 'artworkUrl', 'data:image/') : null,
    audioUrl: safeResourceUrl(value.audioUrl, 'audioUrl', 'data:audio/'),
    duration: normalizedDuration(value.duration),
    id: requiredText(value.id, 'id'),
    lyrics: normalizeLyrics(value.lyrics),
    title: requiredText(value.title, 'title'),
    ...metadata,
  })
}

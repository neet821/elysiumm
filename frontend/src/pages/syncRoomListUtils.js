export const EMPTY_ROOM_TIMEOUT_MS = 10 * 60 * 1000

export function getOnlineMemberCount(room) {
  const count = Number(room?.member_count)
  return Number.isFinite(count) && count >= 0 ? Math.floor(count) : 0
}

function parseBackendTimestamp(value) {
  if (typeof value !== 'string') return Number.NaN

  // 后端历史字段是无时区标记的 UTC 时间，不能让浏览器按本地时区解释。
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
  const normalizedValue = !hasTimezone && /^\d{4}-\d{2}-\d{2}T/.test(value)
    ? `${value}Z`
    : value
  return Date.parse(normalizedValue)
}

export function formatEmptyRoomCountdown(lastActivityAt, nowMs = Date.now()) {
  const parsedActivityAt = parseBackendTimestamp(lastActivityAt)
  const activityAt = Number.isFinite(parsedActivityAt) ? parsedActivityAt : nowMs
  const remainingMs = activityAt + EMPTY_ROOM_TIMEOUT_MS - nowMs
  const remainingSeconds = Math.max(0, Math.ceil(remainingMs / 1000))
  const minutes = Math.floor(remainingSeconds / 60)
  const seconds = remainingSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')} 后关闭`
}
